"""Auto-trader control routes — start/stop/status/thinking."""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import pytz

import engines.auto_trader as at
import providers.projectx as px
from engines.ict import get_ict_analysis
from engines.ict_signals import _INSTRUMENT_CONFIG
from routes.backtest import _calc_adx, _calc_rsi, _calc_atr, _calc_vwap_at, _bar_dt

router = APIRouter(prefix="/api/bot", tags=["autotrader"])
NY_TZ = pytz.timezone("America/New_York")


@router.get("/status")
async def status():
    state = at.get_state()
    # Merge live account info
    positions = await px.get_positions()
    orders    = await px.get_open_orders()
    quotes    = px.get_all_quotes()
    state["positions"]   = positions
    state["open_orders"] = orders
    state["quotes"]      = quotes
    state["account_id"]  = px._account_id
    state["accounts"]    = px._accounts
    return state


@router.post("/start")
async def start_bot():
    ok = await at.start()
    return {"success": ok, "running": at._running}


@router.post("/stop")
async def stop_bot():
    ok = await at.stop()
    return {"success": ok, "running": at._running}


@router.post("/force-trade")
async def force_trade(symbol: str = "MNQ", side: int = 0, size: int = 1,
                      stop_ticks: int = 40, tp_ticks: int = 80):
    """Manually fire a market order for testing."""
    result = await px.place_order(
        symbol=symbol.upper(),
        side=side,
        size=size,
        order_type=2,
        stop_loss_ticks=stop_ticks,
        take_profit_ticks=tp_ticks,
    )
    return result


@router.post("/close-all")
async def close_all():
    """Emergency: close all open positions."""
    positions = await px.get_positions()
    results = []
    for pos in positions:
        cid = pos.get("contractId", "")
        # Reverse lookup symbol
        sym = next((k for k, v in px._contract_cache.items() if v == cid), None)
        if sym:
            r = await px.close_position(sym)
            results.append({"symbol": sym, **r})
    orders = await px.get_open_orders()
    for o in orders:
        r = await px.cancel_order(o["id"])
        results.append({"order_id": o["id"], **r})
    return {"closed": results}


@router.get("/thinking")
async def bot_thinking():
    """
    What is the bot seeing right now?
    Returns live ICT scores for all instruments, what filter is blocking,
    how close each is to firing a trade.
    """
    instruments = ["MNQ", "MES", "MGC"]
    results = {}

    for sym in instruments:
        try:
            bars = await px.get_bars(sym, interval="5m", limit=150)
            if not bars:
                results[sym] = {"status": "no_data"}
                continue
            if bars[0]["time"] > bars[-1]["time"]:
                bars = list(reversed(bars))

            bars_1m = await px.get_bars(sym, interval="1m", limit=30)
            if bars_1m and bars_1m[0]["time"] > bars_1m[-1]["time"]:
                bars_1m = list(reversed(bars_1m))

            price    = bars[-1]["close"]
            config   = _INSTRUMENT_CONFIG.get(sym, _INSTRUMENT_CONFIG["MNQ"])
            analysis = get_ict_analysis(bars, current_price=price)
            long_sc  = analysis.get("long_setup",  {}).get("score", 0) or 0
            short_sc = analysis.get("short_setup", {}).get("score", 0) or 0
            adx      = _calc_adx(bars[-60:])
            rsi      = _calc_rsi(bars[-60:])
            atr      = _calc_atr(bars[-20:])
            now_et   = _bar_dt(bars[-1])
            vwap     = _calc_vwap_at(bars, now_et)
            quote    = px.get_quote(sym)

            # Determine which session min_score applies
            sess     = at._current_session()
            min_score = sess["min_score"] if sess else 65
            best_score = max(long_sc, short_sc)
            direction  = "bullish" if long_sc >= short_sc else "bearish"

            # Identify blockers
            blockers = []
            if best_score < min_score:
                blockers.append(f"score {best_score} < {min_score} needed")
            if adx < 10:
                blockers.append(f"ADX {adx:.1f} < 10 (ranging)")
            if direction == "bullish" and rsi > 80:
                blockers.append(f"RSI {rsi:.1f} overbought")
            if direction == "bearish" and rsi < 20:
                blockers.append(f"RSI {rsi:.1f} oversold")
            if vwap and direction == "bullish" and price < vwap * 0.996:
                blockers.append(f"price below VWAP ({vwap:.2f})")
            if vwap and direction == "bearish" and price > vwap * 1.004:
                blockers.append(f"price above VWAP ({vwap:.2f})")

            # Scalp 1m check
            scalp_ready = False
            if bars_1m and len(bars_1m) >= 3:
                last3 = bars_1m[-3:]
                scalp_bull = all(b["close"] > b["open"] for b in last3)
                scalp_bear = all(b["close"] < b["open"] for b in last3)
                scalp_ready = scalp_bull or scalp_bear

            results[sym] = {
                "price":       price,
                "bid":         quote.get("bestBid") if quote else None,
                "ask":         quote.get("bestAsk") if quote else None,
                "long_score":  long_sc,
                "short_score": short_sc,
                "best_score":  best_score,
                "min_score":   min_score,
                "score_gap":   max(0, min_score - best_score),
                "direction":   direction,
                "adx":         round(adx, 1),
                "rsi":         round(rsi, 1),
                "atr":         round(atr, 2),
                "vwap":        round(vwap, 2) if vwap else None,
                "blockers":    blockers,
                "ready":       len(blockers) == 0 and best_score >= min_score,
                "scalp_ready": scalp_ready,
                "status":      "READY 🔥" if (len(blockers) == 0 and best_score >= min_score) else (f"{min_score - best_score} pts short" if best_score < min_score else f"{len(blockers)} blocker(s)"),
            }
        except Exception as e:
            results[sym] = {"status": f"error: {e}"}

    session = at._current_session()
    return {
        "session":     session["name"] if session else "Between sessions",
        "market_open": at._market_open(),
        "daily_pnl":   at._daily_pnl,
        "trail_mode":  at._trail_mode,
        "trail_floor": at._trail_floor,
        "instruments": results,
        "timestamp":   datetime.now(NY_TZ).isoformat(),
    }


@router.post("/switch-account")
async def switch_account(account_id: int):
    """Switch bot to a different TopstepX account."""
    import os
    # Validate account exists
    accounts = await px.get_accounts()
    match = next((a for a in accounts if a["id"] == account_id), None)
    if not match:
        return {"success": False, "error": "Account not found"}
    if not match.get("canTrade"):
        return {"success": False, "error": "Account cannot trade"}
    px._account_id = account_id
    return {
        "success":    True,
        "account_id": account_id,
        "name":       match["name"],
        "balance":    match["balance"],
    }
