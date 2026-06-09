"""ProjectX / TopstepX API routes.

Exposes auth status, live quotes, OHLCV bars, accounts,
positions, trade history, and order execution to the frontend.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone, timedelta

import providers.projectx as px

router = APIRouter(prefix="/api/projectx", tags=["projectx"])


# ---------------------------------------------------------------------------
# Status / connection
# ---------------------------------------------------------------------------

@router.get("/status")
async def status():
    connected = px.is_connected()
    accounts = px._accounts or []
    positions = await px.get_positions() if connected else []
    orders    = await px.get_open_orders() if connected else []

    total_pnl = None
    if connected:
        trades = await px.get_trade_history(days_back=1)
        total_pnl = round(
            sum(t.get("profitAndLoss") or 0 for t in trades) -
            sum(t.get("fees") or 0 for t in trades),
            2,
        )

    return {
        "connected":       connected,
        "ws_live":         px._ws_running,
        "account_id":      px._account_id,
        "accounts":        accounts,
        "open_positions":  positions,
        "open_orders":     orders,
        "today_pnl":       total_pnl,
        "quote_symbols":   list(px._quote_cache.keys()),
        "token_expires":   px._token_expires.isoformat() if px._token_expires else None,
    }


@router.post("/connect")
async def connect():
    """Re-authenticate and restart WebSocket."""
    token = await px.authenticate()
    if not token:
        raise HTTPException(401, "Authentication failed — check PROJECTX_API_KEY and PROJECTX_USERNAME in .env")
    await px.get_accounts()
    await px.start_websocket()
    return {"success": True, "account_id": px._account_id}


# ---------------------------------------------------------------------------
# Market data
# ---------------------------------------------------------------------------

@router.get("/quotes")
async def quotes():
    """Live quotes for MNQ, MES, MGC."""
    q = px.get_all_quotes()
    if not q:
        # Try REST fallback if WS not up yet
        await px.refresh_quotes_rest()
        q = px.get_all_quotes()
    return {"quotes": q, "source": "websocket" if px._ws_running else "rest_fallback"}


@router.get("/bars")
async def bars(
    symbol: str = "MNQ",
    interval: str = "5m",
    limit: int = 500,
):
    """
    OHLCV bars from ProjectX.
    interval: 1m | 5m | 15m | 30m | 1h | 4h | 1d
    """
    valid = {"1m", "5m", "15m", "30m", "1h", "4h", "1d"}
    if interval not in valid:
        raise HTTPException(400, f"interval must be one of {sorted(valid)}")

    bar_data = await px.get_bars(symbol.upper(), interval=interval, limit=limit)
    contract_id = px._contract_cache.get(symbol.upper(), "")
    return {
        "symbol":     symbol.upper(),
        "contractId": contract_id,
        "interval":   interval,
        "count":      len(bar_data),
        "bars":       bar_data,
    }


@router.get("/contracts")
async def contracts(search: str = "MNQ"):
    results = await px.search_contracts(search.upper())
    return {"contracts": results}


@router.get("/ict")
async def live_ict(symbol: str = "MNQ", interval: str = "5m"):
    """
    Run full ICT analysis on live ProjectX bars.
    Same response shape as /api/ict/analysis — drop-in replacement with real futures data.
    """
    from engines.ict import get_ict_analysis, extract_session_levels, detect_equal_highs_lows
    from engines.ict_signals import get_advanced_signals
    from datetime import timezone as tz

    bar_data = await px.get_bars(symbol.upper(), interval=interval, limit=300)
    if not bar_data:
        raise HTTPException(503, f"No bars available for {symbol}")

    # Sort ascending
    if bar_data and bar_data[0]["time"] > bar_data[-1]["time"]:
        bar_data = list(reversed(bar_data))

    price = bar_data[-1]["close"] if bar_data else 0
    now   = datetime.now(tz.utc)

    analysis    = get_ict_analysis(bar_data, current_price=price)
    sess_levels = extract_session_levels(bar_data)
    ehl         = detect_equal_highs_lows(bar_data)
    adv         = get_advanced_signals(bar_data, session_levels=sess_levels, equal_hl=ehl)

    quote = px.get_quote(symbol.upper())

    result = dict(analysis)   # base: ICT analysis
    result.update({
        "symbol":         symbol.upper(),
        "price":          price,
        "bid":            quote.get("bestBid")  if quote else None,
        "ask":            quote.get("bestAsk")  if quote else None,
        "source":         "projectx_live",
        "timestamp":      now.isoformat(),
        "bars_count":     len(bar_data),
        "session_levels": sess_levels,
        "equal_hl":       ehl,
        "advanced":       adv,
    })
    return result


# ---------------------------------------------------------------------------
# Account
# ---------------------------------------------------------------------------

@router.get("/accounts")
async def accounts():
    return {"accounts": await px.get_accounts()}


@router.get("/positions")
async def positions():
    pos = await px.get_positions()
    # Enrich with contract name from cache (reverse lookup)
    id_to_sym = {v: k for k, v in px._contract_cache.items()}
    for p in pos:
        p["symbol"] = id_to_sym.get(p.get("contractId"), p.get("contractId", ""))
    return {"positions": pos}


@router.get("/orders")
async def open_orders():
    return {"orders": await px.get_open_orders()}


@router.get("/trades")
async def trade_history(days: int = 30):
    trades = await px.get_trade_history(days_back=days)
    gross   = sum(t.get("profitAndLoss") or 0 for t in trades)
    fees    = sum(t.get("fees") or 0 for t in trades)
    wins    = [t for t in trades if (t.get("profitAndLoss") or 0) > 0]
    losses  = [t for t in trades if (t.get("profitAndLoss") or 0) < 0]
    return {
        "trades":     trades,
        "count":      len(trades),
        "wins":       len(wins),
        "losses":     len(losses),
        "win_rate":   round(len(wins) / len(trades) * 100, 1) if trades else 0,
        "gross_pnl":  round(gross, 2),
        "total_fees": round(fees, 2),
        "net_pnl":    round(gross - fees, 2),
    }


# ---------------------------------------------------------------------------
# Order execution
# ---------------------------------------------------------------------------

class OrderRequest(BaseModel):
    symbol:             str   = "MNQ"
    side:               int             # 0=Buy  1=Sell
    size:               int   = 1
    order_type:         int   = 2       # 2=Market
    limit_price:        Optional[float] = None
    stop_price:         Optional[float] = None
    stop_loss_ticks:    Optional[int]   = None   # bracket SL in ticks
    take_profit_ticks:  Optional[int]   = None   # bracket TP in ticks


@router.post("/order")
async def place_order(req: OrderRequest):
    """
    Place an order on the TopstepX practice account.

    MNQ tick = 0.25 pts ($0.50).  40 ticks = 10 pts = $20 (typical 1R).
    Bracket example: stop_loss_ticks=40, take_profit_ticks=80 → 1R:2R.
    """
    result = await px.place_order(
        symbol=req.symbol.upper(),
        side=req.side,
        size=req.size,
        order_type=req.order_type,
        limit_price=req.limit_price,
        stop_price=req.stop_price,
        stop_loss_ticks=req.stop_loss_ticks,
        take_profit_ticks=req.take_profit_ticks,
    )
    if not result.get("success"):
        raise HTTPException(400, result.get("errorMessage", "Order rejected"))
    return result


class CancelRequest(BaseModel):
    order_id: int


@router.post("/order/cancel")
async def cancel_order(req: CancelRequest):
    result = await px.cancel_order(req.order_id)
    if not result.get("success"):
        raise HTTPException(400, result.get("errorMessage", "Cancel failed"))
    return result


class CloseRequest(BaseModel):
    symbol: str = "MNQ"


@router.post("/position/close")
async def close_position(req: CloseRequest):
    result = await px.close_position(req.symbol.upper())
    if not result.get("success"):
        raise HTTPException(400, result.get("errorMessage", "Close failed"))
    return result
