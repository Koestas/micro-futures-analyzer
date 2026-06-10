"""ProjectX / TopstepX live data provider.

Handles auth (JWT), REST calls (accounts, bars, orders, positions),
and a SignalR WebSocket for real-time quotes on MNQ/MES/MGC.
"""

import os
import asyncio
import logging
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

import httpx
from signalrcore.hub_connection_builder import HubConnectionBuilder

logger = logging.getLogger(__name__)

BASE_URL = "https://api.topstepx.com"
MARKET_HUB = "https://rtc.topstepx.com/hubs/market"
USER_HUB   = "https://rtc.topstepx.com/hubs/user"

# --- Shared state ---
_token: Optional[str] = None
_token_expires: Optional[datetime] = None
_account_id: Optional[int] = None
_accounts: list = []
_contract_cache: Dict[str, str] = {}   # "MNQ" → "CON.F.US.MENQ.M26"
_quote_cache: Dict[str, dict] = {}     # "MNQ" → latest GatewayQuote
_ws_market = None                      # SignalR connection (market hub)
_ws_running = False


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

async def authenticate() -> Optional[str]:
    global _token, _token_expires
    api_key  = os.getenv("PROJECTX_API_KEY", "")
    username = os.getenv("PROJECTX_USERNAME", "")
    if not api_key or not username:
        logger.error("PROJECTX_API_KEY / PROJECTX_USERNAME not set in .env")
        return None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{BASE_URL}/api/Auth/loginKey",
                json={"userName": username, "apiKey": api_key},
            )
            data = resp.json()
            if data.get("success") and data.get("token"):
                _token = data["token"]
                _token_expires = datetime.now(timezone.utc) + timedelta(hours=23)
                logger.info("ProjectX authenticated ✓")
                return _token
            logger.error(f"ProjectX auth failed: {data.get('errorMessage')} | code {data.get('errorCode')}")
    except Exception as e:
        logger.error(f"ProjectX auth exception: {e}")
    return None


async def _ensure_token() -> Optional[str]:
    global _token, _token_expires
    if not _token or (
        _token_expires and datetime.now(timezone.utc) >= _token_expires
    ):
        await authenticate()
    return _token


def is_connected() -> bool:
    return _token is not None and (
        _token_expires is None or datetime.now(timezone.utc) < _token_expires
    )


def get_mirror_account_ids() -> list[int]:
    """
    Returns all account IDs to mirror trades to (from PROJECTX_MIRROR_ACCOUNTS env var).
    Format: comma-separated IDs, e.g. "23115763,23413210"
    Primary account (PROJECTX_ACCOUNT_ID) is always excluded — it places first.
    """
    raw = os.getenv("PROJECTX_MIRROR_ACCOUNTS", "")
    if not raw:
        return []
    primary = _account_id
    ids = []
    for part in raw.split(","):
        try:
            aid = int(part.strip())
            if aid != primary:
                ids.append(aid)
        except ValueError:
            pass
    return ids


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------

async def get_accounts() -> list:
    global _account_id, _accounts
    token = await _ensure_token()
    if not token:
        return []
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{BASE_URL}/api/Account/search",
                json={"onlyActiveAccounts": True},
                headers={"Authorization": f"Bearer {token}"},
            )
            data = resp.json()
            if data.get("success"):
                all_accts = data.get("accounts", [])
                # Only expose tradeable accounts — filters out dead practice and ineligible combines
                eligible = [a for a in all_accts if a.get("canTrade")]
                # If an allowlist is configured, only show those accounts
                allowed_env = os.getenv("PROJECTX_ALLOWED_ACCOUNTS", "")
                if allowed_env:
                    allowed_names = {n.strip() for n in allowed_env.split(",")}
                    eligible = [a for a in eligible if a.get("name") in allowed_names]
                _accounts = eligible
                if _account_id is None:
                    # Priority 1: any active PRAC account (practice — always prefer over combine)
                    prac = next((a for a in _accounts if "PRAC" in (a.get("name") or "").upper()), None)
                    if prac:
                        _account_id = prac["id"]
                    else:
                        # Priority 2: env-specified account if it's still tradeable
                        preferred = os.getenv("PROJECTX_ACCOUNT_ID")
                        if preferred:
                            preferred_id = int(preferred)
                            match = next((a for a in _accounts if a["id"] == preferred_id), None)
                            if match:
                                _account_id = preferred_id
                        # Priority 3: first tradeable account
                        if _account_id is None and _accounts:
                            _account_id = _accounts[0]["id"]
                return _accounts
    except Exception as e:
        logger.error(f"get_accounts: {e}")
    return []


async def _resolve_account(account_id: Optional[int] = None) -> Optional[int]:
    if account_id:
        return account_id
    if _account_id:
        return _account_id
    await get_accounts()
    return _account_id


# ---------------------------------------------------------------------------
# Contracts
# ---------------------------------------------------------------------------

def _use_live() -> bool:
    return os.getenv("PROJECTX_LIVE", "false").lower() == "true"


async def search_contracts(search_text: str) -> list:
    token = await _ensure_token()
    if not token:
        return []
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{BASE_URL}/api/Contract/search",
                json={"searchText": search_text, "live": _use_live()},
                headers={"Authorization": f"Bearer {token}"},
            )
            data = resp.json()
            if data.get("success"):
                return data.get("contracts", [])
    except Exception as e:
        logger.error(f"search_contracts: {e}")
    return []


async def get_contract_id(symbol: str) -> Optional[str]:
    if symbol in _contract_cache:
        return _contract_cache[symbol]
    contracts = await search_contracts(symbol)
    active = [c for c in contracts if c.get("activeContract")]
    chosen = active[0] if active else (contracts[0] if contracts else None)
    if chosen:
        _contract_cache[symbol] = chosen["id"]
        return chosen["id"]
    return None


# ---------------------------------------------------------------------------
# Bars (OHLCV)
# ---------------------------------------------------------------------------

_INTERVAL_MAP = {
    "1m":  (2, 1),
    "5m":  (2, 5),
    "15m": (2, 15),
    "30m": (2, 30),
    "1h":  (3, 1),
    "4h":  (3, 4),
    "1d":  (4, 1),
}

_HOURS_PER_BAR = {
    "1m": 1/60, "5m": 5/60, "15m": 0.25, "30m": 0.5,
    "1h": 1,    "4h": 4,    "1d":  24,
}


async def get_bars(
    symbol: str,
    interval: str = "5m",
    limit: int = 500,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
) -> list:
    token = await _ensure_token()
    if not token:
        return []

    contract_id = await get_contract_id(symbol)
    if not contract_id:
        logger.warning(f"No contract found for {symbol}")
        return []

    unit, unit_number = _INTERVAL_MAP.get(interval, (2, 5))
    now = datetime.now(timezone.utc)
    if end_time is None:
        end_time = now
    if start_time is None:
        hours = _HOURS_PER_BAR.get(interval, 1) * limit * 1.5
        start_time = end_time - timedelta(hours=max(hours, 2))

    payload = {
        "contractId": contract_id,
        "live": _use_live(),
        "startTime": start_time.isoformat(),
        "endTime": end_time.isoformat(),
        "unit": unit,
        "unitNumber": unit_number,
        "limit": limit,
        "includePartialBar": True,
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{BASE_URL}/api/History/retrieveBars",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )
            data = resp.json()
            if data.get("success"):
                return [
                    {
                        "time": b["t"],
                        "open": b["o"],
                        "high": b["h"],
                        "low":  b["l"],
                        "close": b["c"],
                        "volume": b.get("v", 0),
                    }
                    for b in data.get("bars", [])
                ]
            logger.warning(f"get_bars failed: {data.get('errorMessage')}")
    except Exception as e:
        logger.error(f"get_bars {symbol}: {e}")
    return []


# ---------------------------------------------------------------------------
# Positions & Orders
# ---------------------------------------------------------------------------

async def get_positions(account_id: Optional[int] = None) -> list:
    token = await _ensure_token()
    if not token:
        return []
    aid = await _resolve_account(account_id)
    if not aid:
        return []
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{BASE_URL}/api/Position/searchOpen",
                json={"accountId": aid},
                headers={"Authorization": f"Bearer {token}"},
            )
            data = resp.json()
            if data.get("success"):
                return data.get("positions", [])
    except Exception as e:
        logger.error(f"get_positions: {e}")
    return []


async def get_open_orders(account_id: Optional[int] = None) -> list:
    token = await _ensure_token()
    if not token:
        return []
    aid = await _resolve_account(account_id)
    if not aid:
        return []
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{BASE_URL}/api/Order/searchOpen",
                json={"accountId": aid},
                headers={"Authorization": f"Bearer {token}"},
            )
            data = resp.json()
            if data.get("success"):
                return data.get("orders", [])
    except Exception as e:
        logger.error(f"get_open_orders: {e}")
    return []


async def get_trade_history(days_back: int = 30, account_id: Optional[int] = None) -> list:
    token = await _ensure_token()
    if not token:
        return []
    aid = await _resolve_account(account_id)
    if not aid:
        return []
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days_back)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{BASE_URL}/api/Trade/search",
                json={
                    "accountId": aid,
                    "startTimestamp": start.isoformat(),
                    "endTimestamp": end.isoformat(),
                },
                headers={"Authorization": f"Bearer {token}"},
            )
            data = resp.json()
            if data.get("success"):
                return data.get("trades", [])
    except Exception as e:
        logger.error(f"get_trade_history: {e}")
    return []


# ---------------------------------------------------------------------------
# Order execution
# ---------------------------------------------------------------------------

async def place_order(
    symbol: str,
    side: int,              # 0=Buy, 1=Sell
    size: int = 1,
    order_type: int = 2,    # 2=Market
    limit_price: Optional[float] = None,
    stop_price: Optional[float] = None,
    stop_loss_ticks: Optional[int] = None,
    take_profit_ticks: Optional[int] = None,
    account_id: Optional[int] = None,
) -> dict:
    token = await _ensure_token()
    if not token:
        return {"success": False, "errorMessage": "Not authenticated"}

    aid = await _resolve_account(account_id)
    if not aid:
        return {"success": False, "errorMessage": "No account ID"}

    contract_id = await get_contract_id(symbol)
    if not contract_id:
        return {"success": False, "errorMessage": f"No contract for {symbol}"}

    payload: Dict[str, Any] = {
        "accountId": aid,
        "contractId": contract_id,
        "type": order_type,
        "side": side,
        "size": size,
    }
    if limit_price is not None:
        payload["limitPrice"] = limit_price
    if stop_price is not None:
        payload["stopPrice"] = stop_price
    if stop_loss_ticks is not None:
        # Long (side=0): SL is below entry → negative ticks
        # Short (side=1): SL is above entry → positive ticks
        sl_sign = -1 if side == 0 else 1
        payload["stopLossBracket"] = {"ticks": sl_sign * abs(stop_loss_ticks), "type": 4}
    if take_profit_ticks is not None:
        # Long (side=0): TP is above entry → positive ticks
        # Short (side=1): TP is below entry → negative ticks
        tp_sign = 1 if side == 0 else -1
        payload["takeProfitBracket"] = {"ticks": tp_sign * abs(take_profit_ticks), "type": 1}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{BASE_URL}/api/Order/place",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )
            return resp.json()
    except Exception as e:
        return {"success": False, "errorMessage": str(e)}


async def cancel_order(order_id: int, account_id: Optional[int] = None) -> dict:
    token = await _ensure_token()
    if not token:
        return {"success": False, "errorMessage": "Not authenticated"}
    aid = await _resolve_account(account_id)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{BASE_URL}/api/Order/cancel",
                json={"accountId": aid, "orderId": order_id},
                headers={"Authorization": f"Bearer {token}"},
            )
            return resp.json()
    except Exception as e:
        return {"success": False, "errorMessage": str(e)}


async def partial_close_position(symbol: str, size: int, account_id: Optional[int] = None) -> dict:
    token = await _ensure_token()
    if not token:
        return {"success": False, "errorMessage": "Not authenticated"}
    aid = await _resolve_account(account_id)
    contract_id = await get_contract_id(symbol)
    if not contract_id:
        return {"success": False, "errorMessage": f"No contract for {symbol}"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{BASE_URL}/api/Position/partialCloseContract",
                json={"accountId": aid, "contractId": contract_id, "size": size},
                headers={"Authorization": f"Bearer {token}"},
            )
            return resp.json()
    except Exception as e:
        return {"success": False, "errorMessage": str(e)}


async def modify_order(order_id: int, stop_price: Optional[float] = None,
                       limit_price: Optional[float] = None, size: Optional[int] = None,
                       account_id: Optional[int] = None) -> dict:
    token = await _ensure_token()
    if not token:
        return {"success": False, "errorMessage": "Not authenticated"}
    aid = await _resolve_account(account_id)
    payload = {"accountId": aid, "orderId": order_id}
    if stop_price  is not None: payload["stopPrice"]  = stop_price
    if limit_price is not None: payload["limitPrice"] = limit_price
    if size        is not None: payload["size"]       = size
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{BASE_URL}/api/Order/modify",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )
            return resp.json()
    except Exception as e:
        return {"success": False, "errorMessage": str(e)}


async def close_position(symbol: str, account_id: Optional[int] = None) -> dict:
    token = await _ensure_token()
    if not token:
        return {"success": False, "errorMessage": "Not authenticated"}
    aid = await _resolve_account(account_id)
    contract_id = await get_contract_id(symbol)
    if not contract_id:
        return {"success": False, "errorMessage": f"No contract for {symbol}"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{BASE_URL}/api/Position/closeContract",
                json={"accountId": aid, "contractId": contract_id},
                headers={"Authorization": f"Bearer {token}"},
            )
            return resp.json()
    except Exception as e:
        return {"success": False, "errorMessage": str(e)}


# ---------------------------------------------------------------------------
# Quote cache (populated by WebSocket or REST fallback)
# ---------------------------------------------------------------------------

def get_quote(symbol: str) -> Optional[dict]:
    return _quote_cache.get(symbol)


def get_all_quotes() -> dict:
    return dict(_quote_cache)


def _store_quote(raw: dict):
    """Normalize a GatewayQuote from SignalR into the cache."""
    # SignalR delivers lists; first element is the payload
    if isinstance(raw, list):
        raw = raw[0] if raw else {}
    sym = raw.get("symbolName") or raw.get("symbol", "")
    # Map full symbol name to short name
    name_map = {
        "MNQ": "MNQ", "MES": "MES", "MGC": "MGC",
        "MNQM26": "MNQ", "MESM26": "MES", "MGCM26": "MGC",
    }
    key = None
    for k, v in name_map.items():
        if k in sym.upper():
            key = v
            break
    if not key:
        key = sym
    _quote_cache[key] = {
        "symbol": key,
        "rawSymbol": sym,
        "lastPrice":  raw.get("lastPrice"),
        "bestBid":    raw.get("bestBid"),
        "bestAsk":    raw.get("bestAsk"),
        "change":     raw.get("change"),
        "changePct":  raw.get("changePercent"),
        "open":       raw.get("open"),
        "high":       raw.get("high"),
        "low":        raw.get("low"),
        "volume":     raw.get("volume"),
        "timestamp":  raw.get("timestamp") or datetime.now(timezone.utc).isoformat(),
        "source":     "websocket",
    }


# ---------------------------------------------------------------------------
# SignalR WebSocket — Market Hub
# ---------------------------------------------------------------------------

def _start_market_hub(token: str):
    """Connect to ProjectX Market Hub in a background thread."""
    global _ws_market, _ws_running

    symbols_to_subscribe = ["MNQ", "MES", "MGC"]

    def on_open():
        logger.info("ProjectX Market Hub connected")
        for sym in symbols_to_subscribe:
            cid = _contract_cache.get(sym)
            if cid:
                try:
                    _ws_market.send("SubscribeContractQuotes", [cid])
                    logger.info(f"  → subscribed quotes: {sym} ({cid})")
                except Exception as e:
                    logger.error(f"  subscribe {sym}: {e}")

    def on_error(data):
        logger.error(f"ProjectX Market Hub error: {data}")

    def on_close():
        global _ws_running
        logger.warning("ProjectX Market Hub disconnected")
        _ws_running = False

    url = f"{MARKET_HUB}?access_token={token}"
    try:
        conn = (
            HubConnectionBuilder()
            .with_url(url, options={"verify_ssl": True})
            .with_automatic_reconnect(
                {"type": "raw", "keep_alive_interval": 10, "reconnect_interval": 5, "max_attempts": 5}
            )
            .build()
        )
        conn.on_open(on_open)
        conn.on_error(on_error)
        conn.on_close(on_close)
        conn.on("GatewayQuote", _store_quote)
        conn.start()
        _ws_market = conn
        _ws_running = True
        logger.info("ProjectX Market Hub started")
    except Exception as e:
        logger.error(f"Market Hub start failed: {e}")


async def start_websocket():
    """Authenticate, resolve contract IDs, then start the SignalR WebSocket."""
    global _ws_running
    if _ws_running:
        return

    token = await _ensure_token()
    if not token:
        logger.warning("ProjectX WebSocket skipped — no token")
        return

    # Pre-populate contract cache so the on_open handler can subscribe immediately
    for sym in ["MNQ", "MES", "MGC"]:
        await get_contract_id(sym)

    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _start_market_hub, token)


async def refresh_quotes_rest():
    """REST fallback: fetch the latest 1-min bar for each symbol to populate quote cache."""
    for sym in ["MNQ", "MES", "MGC"]:
        try:
            bars = await get_bars(sym, interval="1m", limit=2)
            if bars:
                last = bars[-1]
                contract_id = _contract_cache.get(sym, "")
                _quote_cache[sym] = {
                    "symbol": sym,
                    "contractId": contract_id,
                    "lastPrice": last["close"],
                    "open":   last["open"],
                    "high":   last["high"],
                    "low":    last["low"],
                    "volume": last["volume"],
                    "source": "rest_bars",
                    "timestamp": last["time"],
                }
        except Exception as e:
            logger.error(f"refresh_quotes_rest {sym}: {e}")


# ---------------------------------------------------------------------------
# Background keep-alive (called from main.py lifespan)
# ---------------------------------------------------------------------------

async def background_task():
    """Authenticate, start WS, refresh quotes every 60s, renew token every 23h."""
    await authenticate()
    if not _token:
        logger.warning("ProjectX background task: auth failed, skipping WS")
        return

    await get_accounts()
    await start_websocket()

    while True:
        await asyncio.sleep(60)
        # If WS is down fall back to REST for quote data
        if not _ws_running:
            await refresh_quotes_rest()
        # Renew token before 24h expiry
        if _token_expires and (
            _token_expires - datetime.now(timezone.utc)
        ).total_seconds() < 3600:
            await authenticate()
            if _ws_market:
                try:
                    _ws_market.stop()
                except Exception:
                    pass
            await start_websocket()
