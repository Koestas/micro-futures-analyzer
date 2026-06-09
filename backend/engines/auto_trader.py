"""Live ICT auto-trader — runs against the ProjectX/TopstepX practice account.

Sessions:
  Asia    21:00–01:00 ET   MGC (Gold)
  London  03:00–05:00 ET   MNQ / MES
  NY AM   09:30–11:30 ET   MNQ / MES  (primary)
  NY PM   13:30–15:30 ET   MNQ        (secondary, higher score bar)

Each session allows up to 2 trades. Max daily loss $3K on the 150K practice account.
Runs as an asyncio background task started from main.py lifespan.
"""

import asyncio
import logging
from datetime import datetime, date, timedelta
from typing import Optional
import pytz

import providers.projectx as px
from engines.ict import get_ict_analysis, extract_session_levels, get_htf_bias
from engines.ict_signals import _INSTRUMENT_CONFIG
from routes.backtest import (
    _bar_dt, _calc_atr, _calc_sma, _calc_rsi, _calc_adx,
    _calc_vwap_at, _get_30min_vwap_bias,
)

logger = logging.getLogger(__name__)
NY_TZ = pytz.timezone("America/New_York")
UTC   = pytz.UTC

# ─── Session definitions ────────────────────────────────────────────────────

SESSIONS = [
    {
        "name": "Asia",
        "instruments": ["MGC"],
        "start_et": (21, 0),
        "end_et":   (1,  0),     # wraps midnight
        "wraps_midnight": True,
        "min_score": 58,
        "contracts": 5,
        "vol_regime_pct": 2.5,
        "require_mss": False,
        "sweep_max_age_mins": 300,
        "max_trades": 2,
    },
    {
        "name": "London",
        "instruments": ["MNQ", "MES"],
        "start_et": (3, 0),
        "end_et":   (5, 0),
        "wraps_midnight": False,
        "min_score": 62,
        "contracts": 5,
        "vol_regime_pct": 4.0,
        "require_mss": False,
        "sweep_max_age_mins": 180,
        "max_trades": 2,
    },
    {
        "name": "NY AM",
        "instruments": ["MNQ", "MES"],
        "start_et": (9, 30),
        "end_et":   (11, 30),
        "wraps_midnight": False,
        "min_score": 65,
        "contracts": 5,
        "vol_regime_pct": 4.0,
        "require_mss": True,
        "sweep_max_age_mins": 90,
        "max_trades": 2,
    },
    {
        "name": "NY PM",
        "instruments": ["MNQ"],
        "start_et": (13, 30),
        "end_et":   (15, 30),
        "wraps_midnight": False,
        "min_score": 68,
        "contracts": 4,
        "vol_regime_pct": 4.0,
        "require_mss": False,
        "sweep_max_age_mins": 330,
        "max_trades": 1,
    },
]

# ─── State ──────────────────────────────────────────────────────────────────

_running    = False
_task       = None
_trade_log  : list = []          # all trades taken this session
_bot_log    : list = []          # status / signal messages
_daily_pnl  : float = 0.0
_trades_today: int = 0
_session_trades: dict = {}       # session_name → count today
_last_signal: dict = {}
_current_session_name: str = ""
_last_check: str = ""

MAX_DAILY_LOSS = 3000.0          # hard stop for 150K practice account
MAX_DAILY_TRADES = 6             # across all sessions


def _log(msg: str, level: str = "info"):
    ts = datetime.now(NY_TZ).strftime("%H:%M:%S ET")
    entry = {"ts": ts, "msg": msg, "level": level}
    _bot_log.append(entry)
    if len(_bot_log) > 200:
        _bot_log.pop(0)
    getattr(logger, level)(f"[AutoTrader] {msg}")


def get_state() -> dict:
    return {
        "running":       _running,
        "daily_pnl":     _daily_pnl,
        "trades_today":  _trades_today,
        "last_signal":   _last_signal,
        "current_session": _current_session_name,
        "last_check":    _last_check,
        "trade_log":     _trade_log[-20:],
        "bot_log":       _bot_log[-50:],
    }


# ─── Session detection ───────────────────────────────────────────────────────

def _current_session() -> Optional[dict]:
    now = datetime.now(NY_TZ)
    mins = now.hour * 60 + now.minute

    for s in SESSIONS:
        sh, sm = s["start_et"]
        eh, em = s["end_et"]
        start_m = sh * 60 + sm
        end_m   = eh * 60 + em

        if s["wraps_midnight"]:
            # e.g. 21:00–01:00 → active if mins >= 1260 OR mins <= 60
            if mins >= start_m or mins <= end_m:
                return s
        else:
            if start_m <= mins <= end_m:
                return s
    return None


# ─── Bar helpers ─────────────────────────────────────────────────────────────

async def _fetch_live_bars(symbol: str, n: int = 300) -> list:
    """Get n 5-min bars from ProjectX. Returns newest-to-oldest, sorted ascending."""
    bars = await px.get_bars(symbol, interval="5m", limit=n)
    if bars and bars[0]["time"] > bars[-1]["time"]:
        bars = list(reversed(bars))   # ensure ascending time
    return bars


async def _fetch_daily_bars(symbol: str) -> list:
    bars = await px.get_bars(symbol, interval="1d", limit=30)
    if bars and bars[0]["time"] > bars[-1]["time"]:
        bars = list(reversed(bars))
    return bars


# ─── Vol regime check (last 3 trading days) ──────────────────────────────────

def _vol_ok(bars: list, pct_limit: float = 4.0) -> bool:
    """Return False if any of the last 3 days had an intraday range > pct_limit%."""
    if not bars:
        return True
    by_day: dict = {}
    for b in bars:
        d = _bar_dt(b).date()
        by_day.setdefault(d, []).append(b)
    recent = sorted(by_day.keys())[-3:]
    for d in recent:
        day = by_day[d]
        hi = max(b["high"] for b in day)
        lo = min(b["low"]  for b in day)
        if lo > 0 and (hi - lo) / lo * 100 > pct_limit:
            _log(f"Vol regime: {d} range {(hi-lo)/lo*100:.1f}% > {pct_limit}% — skipping", "warning")
            return False
    return True


# ─── Setup analysis ──────────────────────────────────────────────────────────

def _analyze_bars(bars: list, instrument: str, session: dict) -> Optional[dict]:
    """
    Run ICT analysis on live bars. Return a setup dict or None.
    Uses the same logic as the backtest engine but on live data.
    """
    if len(bars) < 30:
        return None

    recent   = bars[-150:]   # last 12.5 hours of 5m bars for context
    last_bar = bars[-1]
    price    = last_bar["close"]

    # ── ICT analysis ────────────────────────────────────────────────────────
    analysis = get_ict_analysis(recent, current_price=price)
    long_sc  = analysis.get("long_setup",  {}).get("score", 0) or 0
    short_sc = analysis.get("short_setup", {}).get("score", 0) or 0

    if max(long_sc, short_sc) < session["min_score"]:
        return None

    direction = "bullish" if long_sc >= short_sc else "bearish"
    score     = long_sc if direction == "bullish" else short_sc

    # ── Quality filters (mirrors backtest _find_killzone_setup) ─────────────
    config = _INSTRUMENT_CONFIG.get(instrument.upper(), _INSTRUMENT_CONFIG["MNQ"])

    # 1. ADX: skip ranging markets
    adx = _calc_adx(recent[-60:])
    if adx < 10:
        _log(f"{instrument} ADX {adx:.1f} < 10 — ranging, skip")
        return None

    # 2. RSI: don't chase extremes
    rsi = _calc_rsi(recent[-60:])
    if direction == "bullish" and rsi > 78:
        _log(f"{instrument} RSI {rsi:.1f} overbought — skip long")
        return None
    if direction == "bearish" and rsi < 22:
        _log(f"{instrument} RSI {rsi:.1f} oversold — skip short")
        return None

    # 3. VWAP position
    now_et  = _bar_dt(last_bar)
    vwap    = _calc_vwap_at(bars, now_et)
    if vwap:
        tol = 0.004 if instrument == "MGC" else 0.003  # gold wider tolerance
        if direction == "bullish" and price < vwap * (1 - tol):
            _log(f"{instrument} price {price} below VWAP {vwap:.2f} — skip long")
            return None
        if direction == "bearish" and price > vwap * (1 + tol):
            _log(f"{instrument} price {price} above VWAP {vwap:.2f} — skip short")
            return None

    # 4. 200 SMA trend filter
    sma200 = _calc_sma(recent, 200)
    if sma200:
        if direction == "bullish" and price < sma200 * 0.996:
            _log(f"{instrument} price below 200 SMA — skip long")
            return None
        if direction == "bearish" and price > sma200 * 1.004:
            _log(f"{instrument} price above 200 SMA — skip short")
            return None

    # ── Stop & target calculation ────────────────────────────────────────────
    atr        = _calc_atr(recent[-20:])
    stop_dist  = max(atr * 1.5, config["min_stop_pts"], config["stop_buffer"])
    # Hard cap per instrument
    caps = {"MNQ": 120, "MES": 60, "MGC": 18}
    stop_dist  = min(stop_dist, caps.get(instrument, 120))

    tick       = config["tick_size"]
    stop_ticks = round(stop_dist / tick)
    tp_ticks   = round(stop_ticks * 2)   # 2R target

    entry_price = price
    if direction == "bullish":
        sl_price = round(entry_price - stop_dist, 2)
        tp_price = round(entry_price + stop_dist * 2, 2)
        side = 0   # Buy
    else:
        sl_price = round(entry_price + stop_dist, 2)
        tp_price = round(entry_price - stop_dist * 2, 2)
        side = 1   # Sell

    # Contracts: use session config but cap at instrument max
    contracts = min(session["contracts"], config["max_contracts"])
    usd_risk  = stop_dist * config["dollars_per_point"] * contracts

    return {
        "instrument":   instrument,
        "direction":    direction,
        "side":         side,
        "score":        score,
        "entry_price":  entry_price,
        "sl_price":     sl_price,
        "tp_price":     tp_price,
        "stop_ticks":   stop_ticks,
        "tp_ticks":     tp_ticks,
        "contracts":    contracts,
        "atr":          round(atr, 2),
        "adx":          round(adx, 1),
        "rsi":          round(rsi, 1),
        "usd_risk":     round(usd_risk, 2),
        "session":      session["name"],
        "timestamp":    datetime.now(NY_TZ).isoformat(),
    }


# ─── Daily P&L sync ──────────────────────────────────────────────────────────

async def _sync_daily_pnl():
    global _daily_pnl
    trades = await px.get_trade_history(days_back=1)
    today  = date.today()
    gross  = sum(
        (t.get("profitAndLoss") or 0) - (t.get("fees") or 0)
        for t in trades
        if t.get("creationTimestamp", "")[:10] == str(today)
    )
    _daily_pnl = round(gross, 2)


# ─── Main loop ───────────────────────────────────────────────────────────────

async def _loop():
    global _running, _last_signal, _current_session_name, _last_check
    global _daily_pnl, _trades_today

    _log("Auto-trader started ✓")

    while _running:
        try:
            now_et = datetime.now(NY_TZ)
            _last_check = now_et.strftime("%H:%M:%S ET")

            # Daily reset at midnight
            if now_et.hour == 0 and now_et.minute < 2:
                _trades_today = 0
                _session_trades.clear()
                _log("New trading day — counters reset")

            # Hard daily loss limit
            await _sync_daily_pnl()
            if _daily_pnl <= -MAX_DAILY_LOSS:
                _log(f"Daily loss ${abs(_daily_pnl):.0f} >= ${MAX_DAILY_LOSS:.0f} limit — trading paused", "warning")
                await asyncio.sleep(300)
                continue

            if _trades_today >= MAX_DAILY_TRADES:
                _log(f"Max daily trades ({MAX_DAILY_TRADES}) reached — resting")
                await asyncio.sleep(300)
                continue

            # Identify current session
            session = _current_session()
            _current_session_name = session["name"] if session else "Off"

            if not session:
                _log("No active session — waiting")
                await asyncio.sleep(60)
                continue

            # Session trade cap
            sess_count = _session_trades.get(session["name"], 0)
            if sess_count >= session["max_trades"]:
                _log(f"{session['name']}: max trades ({session['max_trades']}) reached — waiting for next session")
                await asyncio.sleep(120)
                continue

            # Skip if already in a position
            positions = await px.get_positions()
            if positions:
                pos_info = positions[0]
                _log(f"Position open: {pos_info.get('contractId')} size={pos_info.get('size')} — monitoring")
                await asyncio.sleep(30)
                continue

            # Try each instrument in the session until we find a setup
            setup = None
            for instrument in session["instruments"]:
                bars = await _fetch_live_bars(instrument, n=300)
                if not bars:
                    _log(f"No bars for {instrument}", "warning")
                    continue

                # Vol regime check
                if not _vol_ok(bars, pct_limit=session["vol_regime_pct"]):
                    continue

                daily_bars = await _fetch_daily_bars(instrument)
                htf = get_htf_bias(daily_bars) if daily_bars else {}
                htf_dir = htf.get("direction", "neutral") if htf else "neutral"

                candidate = _analyze_bars(bars, instrument, session)
                if not candidate:
                    _log(f"{session['name']} | {instrument}: no A/A+ setup (HTF={htf_dir})")
                    continue

                # HTF alignment check
                cand_dir = candidate["direction"]
                if htf_dir in ("strong_bullish", "bullish", "bullish_lean") and cand_dir == "bearish":
                    _log(f"{instrument}: contra-trend bearish vs HTF {htf_dir} — skip")
                    continue
                if htf_dir in ("strong_bearish", "bearish", "bearish_lean") and cand_dir == "bullish":
                    _log(f"{instrument}: contra-trend bullish vs HTF {htf_dir} — skip")
                    continue

                setup = candidate
                setup["htf_direction"] = htf_dir
                _log(
                    f"✓ Setup: {instrument} {cand_dir.upper()} | "
                    f"score={candidate['score']} ADX={candidate['adx']} RSI={candidate['rsi']} "
                    f"risk=${candidate['usd_risk']:.0f}"
                )
                break

            _last_signal = setup or {
                "session": session["name"],
                "timestamp": now_et.isoformat(),
                "result": "no setup",
            }

            if not setup:
                await asyncio.sleep(60)
                continue

            # ── Place order ───────────────────────────────────────────────────
            _log(
                f"PLACING: {setup['instrument']} {setup['direction'].upper()} "
                f"x{setup['contracts']} @ {setup['entry_price']:.2f} | "
                f"SL={setup['sl_price']:.2f} TP={setup['tp_price']:.2f}"
            )

            result = await px.place_order(
                symbol=setup["instrument"],
                side=setup["side"],
                size=setup["contracts"],
                order_type=2,                    # Market
                stop_loss_ticks=setup["stop_ticks"],
                take_profit_ticks=setup["tp_ticks"],
            )

            if result.get("success"):
                order_id = result.get("orderId")
                _log(f"ORDER FILLED — ID {order_id} | {setup['instrument']} {setup['direction']} x{setup['contracts']}", "warning")
                _trade_log.append({**setup, "order_id": order_id, "status": "open"})
                _trades_today += 1
                _session_trades[session["name"]] = sess_count + 1
                # Give time for fill, then next check
                await asyncio.sleep(120)
            else:
                err = result.get("errorMessage", "unknown error")
                _log(f"ORDER REJECTED: {err}", "error")
                await asyncio.sleep(60)

        except asyncio.CancelledError:
            break
        except Exception as e:
            _log(f"Loop error: {e}", "error")
            await asyncio.sleep(30)

    _log("Auto-trader stopped")


# ─── Start / Stop ─────────────────────────────────────────────────────────────

async def start():
    global _running, _task
    if _running:
        return False
    _running = True
    _task = asyncio.create_task(_loop())
    return True


async def stop():
    global _running, _task
    _running = False
    if _task:
        _task.cancel()
        _task = None
    return True
