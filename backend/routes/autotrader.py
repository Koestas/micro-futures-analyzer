"""Auto-trader control routes — start/stop/status."""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

import engines.auto_trader as at
import providers.projectx as px

router = APIRouter(prefix="/api/bot", tags=["autotrader"])


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
