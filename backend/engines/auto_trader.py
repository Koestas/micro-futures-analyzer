"""Live ICT auto-trader — ProjectX/TopstepX.

Trading window: 6:15 PM – 3:50 PM ET (all CME hours, skip 4–6 PM close).
8 sessions cover the full window; instruments and score floors vary by session quality.

Progressive daily profit protection:
  • $500 hit  → floor locked at $500 (if P&L retreats to $500 → stop for day)
  • $600 hit  → floor raised to $600, size reduced to 80%
  • $750 hit  → floor raised to $750, size reduced to 70%
  • $1000 hit → floor raised to $1000, size reduced to 50%
  • $1500 hit → done for the day (max profit ceiling)
  • Hard loss: $1000 max daily loss — locked immediately

Position management:
  • Entry: market order with stop+TP brackets (Auto OCO must be ON in TopstepX)
  • At +1R floating: partial close 60% of contracts (lock partial gain)
  • Remaining 40% = runners with trailing stop (every $50 above first target)
"""

import asyncio
import logging
import os
from datetime import datetime, date, timedelta
from typing import Optional
import pytz

import providers.projectx as px
import providers.telegram as tg
from engines.ict import get_ict_analysis, get_htf_bias
from engines.ict_signals import _INSTRUMENT_CONFIG
from routes.backtest import (
    _bar_dt, _calc_atr, _calc_sma, _calc_rsi, _calc_adx, _calc_vwap_at,
)

logger = logging.getLogger(__name__)
NY_TZ = pytz.timezone("America/New_York")
UTC   = pytz.UTC

# ─── Constants ──────────────────────────────────────────────────────────────

DAILY_MAX_LOSS   = 1000.0    # hard floor — locked for the day if hit
DAILY_MAX_PROFIT = 1500.0    # hard ceiling — done for the day
TRAIL_INCREMENT  = 50.0      # trail individual position stop every $50
PARTIAL_RATIO    = 0.60      # close this fraction at +1R (60% → lock gain, 40% runners)
MAX_DAILY_TRADES = 12        # ICT swing trades across all sessions

# Progressive profit locks: (pnl_threshold, new_floor, size_factor)
# Once P&L crosses threshold the floor is locked in — if P&L falls back to floor → stop.
PROFIT_LOCKS = [
    (500,   500,  1.00),
    (600,   600,  0.80),
    (750,   750,  0.70),
    (1000, 1000,  0.50),
    (1500, 1500,  0.00),   # max hit → stop trading
]

# Scalp layer — runs every 60s alongside the ICT loop
MAX_SCALP_PER_DAY   = 4      # conservative cap until strategy is validated

# Market closed 4:00–6:00 PM ET (CME daily break)
MARKET_CLOSED_START = 16 * 60
MARKET_CLOSED_END   = 18 * 60

# ─── Session definitions (6:15 PM → 3:50 PM ET next day) ────────────────────

SESSIONS = [
    {   # Market reopens at 6 PM ET — scan immediately for structure setups
        "name": "Post-Open",
        "instruments": ["MGC", "MNQ"],
        "start_et": (18, 0), "end_et": (21, 0),
        "wraps_midnight": False,
        "min_score": 62, "contracts": 2, "max_trades": 1,
        "vol_regime_pct": 3.5, "sweep_max_age_mins": 240,
    },
    {   # Asia session — Gold prime time, NQ gets structure from US levels
        "name": "Asia",
        "instruments": ["MGC", "MNQ"],
        "start_et": (21, 0), "end_et": (1, 0),
        "wraps_midnight": True,
        "min_score": 58, "contracts": 2, "max_trades": 2,
        "vol_regime_pct": 2.5, "sweep_max_age_mins": 300,
    },
    {   # Asia–London handoff — NQ/MES taking over, Gold done for the night
        "name": "Asia-London",
        "instruments": ["MNQ", "MES"],
        "start_et": (1, 0), "end_et": (3, 0),
        "wraps_midnight": False,
        "min_score": 60, "contracts": 2, "max_trades": 1,
        "vol_regime_pct": 3.0, "sweep_max_age_mins": 240,
    },
    {   # London open — NQ/ES at their most predictable overnight
        "name": "London",
        "instruments": ["MNQ", "MES"],
        "start_et": (3, 0), "end_et": (5, 0),
        "wraps_midnight": False,
        "min_score": 62, "contracts": 2, "max_trades": 2,
        "vol_regime_pct": 4.0, "sweep_max_age_mins": 180,
    },
    {   # Pre-market — London close to NY open, decent volume building
        "name": "Pre-Market",
        "instruments": ["MNQ", "MES"],
        "start_et": (5, 0), "end_et": (9, 30),
        "wraps_midnight": False,
        "min_score": 64, "contracts": 2, "max_trades": 1,
        "vol_regime_pct": 3.5, "sweep_max_age_mins": 300,
    },
    {   # NY AM killzone — highest quality, prime session
        "name": "NY AM",
        "instruments": ["MNQ", "MES"],
        "start_et": (9, 30), "end_et": (11, 30),
        "wraps_midnight": False,
        "min_score": 65, "contracts": 3, "max_trades": 2,
        "vol_regime_pct": 4.0, "sweep_max_age_mins": 90,
    },
    {   # Midday lull — lower quality, smaller size, high bar
        "name": "Midday",
        "instruments": ["MNQ"],
        "start_et": (11, 30), "end_et": (13, 30),
        "wraps_midnight": False,
        "min_score": 70, "contracts": 1, "max_trades": 1,
        "vol_regime_pct": 3.5, "sweep_max_age_mins": 300,
    },
    {   # NY PM — strong momentum setups into close
        "name": "NY PM",
        "instruments": ["MNQ", "MES"],
        "start_et": (13, 30), "end_et": (15, 50),
        "wraps_midnight": False,
        "min_score": 67, "contracts": 3, "max_trades": 2,
        "vol_regime_pct": 4.0, "sweep_max_age_mins": 330,
    },
]

# ─── State ──────────────────────────────────────────────────────────────────

_running               = False
_task                  = None
_monitor_task          = None
_ghost_task            = None
_trade_log             : list = []
_bot_log               : list = []
_daily_pnl             : float = 0.0
_session_start_balance : float = 0.0
_trades_today    : int = 0
_session_trades  : dict = {}
_last_signal     : dict = {}
_current_session_name: str = ""
_last_check      : str = ""
_trail_mode      : bool = False
_trail_locked_pnl: float = 0.0
_trail_floor     : float = 0.0

# Progressive profit protection state (reset each trading day)
_daily_floor        : float = -DAILY_MAX_LOSS   # retreating to this level stops trading
_daily_size_factor  : float = 1.0               # scales contracts down as profits lock in

# Active trade tracking for position management
_active_trade: dict = {}  # {symbol, entry_price, side, total_contracts, remaining_contracts,
                           #  stop_price, stop_order_id, partial_done, direction, config}

# Scalp layer state
_scalp_task         = None
_scalp_today        : int = 0
_last_scalp_time    : dict = {}   # symbol → datetime of last scalp entry

# End-of-day summary tracking
_eod_sent           : bool = False   # reset each trading day


def _log(msg: str, level: str = "info"):
    ts = datetime.now(NY_TZ).strftime("%H:%M:%S ET")
    entry = {"ts": ts, "msg": msg, "level": level}
    _bot_log.append(entry)
    if len(_bot_log) > 300:
        _bot_log.pop(0)
    getattr(logger, level)(f"[AutoTrader] {msg}")


def get_state() -> dict:
    return {
        "running":          _running,
        "daily_pnl":        _daily_pnl,
        "trades_today":     _trades_today,
        "scalp_today":      _scalp_today,
        "trail_mode":       _trail_mode,
        "trail_floor":      _trail_floor,
        "daily_floor":      _daily_floor,
        "daily_size_factor": _daily_size_factor,
        "daily_max_profit": DAILY_MAX_PROFIT,
        "daily_max_loss":   DAILY_MAX_LOSS,
        "last_signal":      _last_signal,
        "current_session":  _current_session_name,
        "last_check":       _last_check,
        "active_trade":          _active_trade,
        "trade_log":             _trade_log[-30:],
        "bot_log":               _bot_log[-60:],
        "session_start_balance": _session_start_balance,
    }


# ─── Market / session helpers ─────────────────────────────────────────────────

def _market_open() -> bool:
    mins = datetime.now(NY_TZ).hour * 60 + datetime.now(NY_TZ).minute
    return not (MARKET_CLOSED_START <= mins < MARKET_CLOSED_END)


def _current_session() -> Optional[dict]:
    if not _market_open():
        return None
    now  = datetime.now(NY_TZ)
    mins = now.hour * 60 + now.minute
    for s in SESSIONS:
        sh, sm = s["start_et"]
        eh, em = s["end_et"]
        start_m = sh * 60 + sm
        end_m   = eh * 60 + em
        if s["wraps_midnight"]:
            if mins >= start_m or mins <= end_m:
                return s
        else:
            if start_m <= mins <= end_m:
                return s
    return None


# ─── Bar helpers ──────────────────────────────────────────────────────────────

async def _bars(symbol: str, n: int = 300) -> list:
    raw = await px.get_bars(symbol, interval="5m", limit=n)
    if raw and raw[0]["time"] > raw[-1]["time"]:
        raw = list(reversed(raw))
    return raw


async def _daily_bars(symbol: str) -> list:
    raw = await px.get_bars(symbol, interval="1d", limit=30)
    if raw and raw[0]["time"] > raw[-1]["time"]:
        raw = list(reversed(raw))
    return raw


# ─── Vol regime ───────────────────────────────────────────────────────────────

def _vol_ok(bars: list, pct_limit: float) -> bool:
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
            _log(f"Vol regime {d}: {(hi-lo)/lo*100:.1f}% > {pct_limit}% → skip")
            return False
    return True


# ─── Dakota 3-Bar Reversal engine ────────────────────────────────────────────

def _analyze_3bar_reversal(bars: list, instrument: str, interval_mins: int = 5) -> Optional[dict]:
    """
    Coach Dakota's 3-bar reversal setup.
    Validated: 46% WR / PF 1.26x on 5m, 50% WR / PF 1.18x on 15m (14-day backtest).

    Setup:
      - 3 consecutive bars one direction (establishes trend / sweeps liquidity)
      - 4th bar displaces strongly in opposite direction (body > 1.5× avg prior body)
      - VWAP aligned, vol regime clear
    Conservative sizing: 2 contracts, structure-based stop.
    """
    if len(bars) < 8:
        return None

    config  = _INSTRUMENT_CONFIG.get(instrument.upper(), _INSTRUMENT_CONFIG["MNQ"])
    usd_pt  = config["dollars_per_point"]
    tick    = config["tick_size"]
    buf     = config["stop_buffer"]

    b1, b2, b3, rev = bars[-4], bars[-3], bars[-2], bars[-1]

    def body(b): return abs(b["close"] - b["open"])

    avg_prior = (body(b1) + body(b2) + body(b3)) / 3
    if avg_prior == 0:
        return None

    rev_body = body(rev)
    # Reversal must show displacement: body > 1.5× average of the 3 prior bars
    if rev_body < avg_prior * 1.5:
        return None

    b1_bear = b1["close"] < b1["open"]; b2_bear = b2["close"] < b2["open"]; b3_bear = b3["close"] < b3["open"]
    b1_bull = b1["close"] > b1["open"]; b2_bull = b2["close"] > b2["open"]; b3_bull = b3["close"] > b3["open"]
    rev_bull = rev["close"] > rev["open"]
    rev_bear = rev["close"] < rev["open"]

    if b1_bear and b2_bear and b3_bear and rev_bull:
        direction, side = "bullish", 0
        swing_low  = min(b2["low"], b3["low"], rev["low"])
        stop_dist  = max(rev["close"] - swing_low + buf, config["min_stop_pts"])
        entry      = rev["close"]
        sl_price   = round(entry - stop_dist, 2)
        tp_price   = round(entry + stop_dist * 2, 2)
    elif b1_bull and b2_bull and b3_bull and rev_bear:
        direction, side = "bearish", 1
        swing_hi   = max(b2["high"], b3["high"], rev["high"])
        stop_dist  = max(swing_hi - rev["close"] + buf, config["min_stop_pts"])
        entry      = rev["close"]
        sl_price   = round(entry + stop_dist, 2)
        tp_price   = round(entry - stop_dist * 2, 2)
    else:
        return None

    # ── VWAP filter ───────────────────────────────────────────────────────
    now_et = _bar_dt(rev)
    vwap   = _calc_vwap_at(bars, now_et)
    if vwap:
        if direction == "bullish" and entry < vwap * 0.995:
            return None  # reversal from too deep below VWAP
        if direction == "bearish" and entry > vwap * 1.005:
            return None

    # ── ADX: market must have some trend ─────────────────────────────────
    recent = bars[-20:]
    adx = _calc_adx(recent)
    if adx < 12:
        return None

    # ── Vol regime ────────────────────────────────────────────────────────
    if not _vol_ok(bars, pct_limit=4.0):
        return None

    contracts  = 2   # conservative — validated with smaller size
    stop_ticks = max(1, round(stop_dist / tick))
    tp_ticks   = stop_ticks * 2
    usd_risk   = stop_dist * usd_pt * contracts
    usd_target = stop_dist * 2 * usd_pt * contracts

    return {
        "type":          "3bar_reversal",
        "instrument":    instrument.upper(),
        "interval":      f"{interval_mins}m",
        "direction":     direction,
        "side":          side,
        "entry_price":   round(entry, 2),
        "sl_price":      sl_price,
        "tp_price":      tp_price,
        "stop_ticks":    stop_ticks,
        "tp_ticks":      tp_ticks,
        "stop_dist":     round(stop_dist, 2),
        "contracts":     contracts,
        "usd_risk":      round(usd_risk, 2),
        "usd_target":    round(usd_target, 2),
        "displacement":  round(rev_body / avg_prior, 2),
        "adx":           round(adx, 1),
        "vwap":          round(vwap, 2) if vwap else None,
        "timestamp":     datetime.now(NY_TZ).isoformat(),
        "session":       _current_session_name,
    }


async def _scalp_loop():
    """
    Runs every 60 seconds — scans for Dakota 3-bar reversals on 5m/15m.
    Validated: PF 1.26x (5m), 50% WR (15m) on 14-day ProjectX backtest.
    Conservative: 2 contracts, 30-min cooldown, max 4/day.
    Bracket orders manage exit. Separate from ICT swing loop.
    """
    global _scalp_today, _last_scalp_time

    _log("3-Bar Reversal engine started — scanning every 60s on 5m/15m bars")

    while _running:
        await asyncio.sleep(60)

        if not _market_open():
            continue

        # Don't scalp if daily limits hit
        halted, _ = _is_daily_halted()
        if halted:
            continue
        if _scalp_today >= MAX_SCALP_PER_DAY:
            continue
        if (_trades_today + _scalp_today) >= (MAX_DAILY_TRADES + MAX_SCALP_PER_DAY):
            continue

        # Don't scalp if already in a position
        positions = await px.get_positions()
        if positions:
            continue

        # News filter
        clear, ev, mins_away = _news_clear(_current_session_name)
        if not clear:
            continue

        # 3-Bar Reversal scan (Dakota) — validated edge: PF 1.26x on 5m, 50% WR on 15m
        # Conservative sizing: 2 contracts, max 2/day, vol-regime gated
        for instrument in ["MNQ"]:
            try:
                # Cool-down: 30 minutes between 3-bar setups (let position resolve)
                last_t = _last_scalp_time.get(instrument)
                if last_t and (datetime.now(NY_TZ) - last_t).total_seconds() < 1800:
                    continue

                # Fetch 5m and 15m bars for the reversal check
                bars_5m  = await px.get_bars(instrument, interval="5m",  limit=20)
                bars_15m = await px.get_bars(instrument, interval="15m", limit=10)
                for b in [bars_5m, bars_15m]:
                    if b and b[0]["time"] > b[-1]["time"]:
                        b.reverse()

                # Check 5m first, then 15m if no 5m setup
                setup = None
                for bar_set, mins in [(bars_5m, 5), (bars_15m, 15)]:
                    if not bar_set or len(bar_set) < 6:
                        continue
                    candidate = _analyze_3bar_reversal(bar_set, instrument, interval_mins=mins)
                    if candidate:
                        setup = candidate
                        break

                if not setup:
                    continue

                _log(
                    f"↩ 3-BAR REVERSAL {instrument} {setup['direction'].upper()} "
                    f"{setup['interval']} x{setup['contracts']} | "
                    f"entry={setup['entry_price']:.2f} SL={setup['sl_price']:.2f} TP={setup['tp_price']:.2f} "
                    f"displacement={setup['displacement']}x ADX={setup['adx']} "
                    f"risk=${setup['usd_risk']:.0f} target=${setup['usd_target']:.0f}",
                    "warning"
                )

                result = await px.place_order(
                    symbol=instrument,
                    side=setup["side"],
                    size=setup["contracts"],
                    order_type=2,
                    stop_loss_ticks=setup["stop_ticks"],
                    take_profit_ticks=setup["tp_ticks"],
                )

                if result.get("success"):
                    _scalp_today += 1
                    _last_scalp_time[instrument] = datetime.now(NY_TZ)
                    _trade_log.append({**setup, "order_id": result.get("orderId")})

                    side_str = "🟢 LONG" if setup["side"] == 0 else "🔴 SHORT"
                    asyncio.create_task(tg.send(
                        f"↩ <b>3-Bar Reversal</b> {side_str} <b>{instrument}</b> ({setup['interval']}) ×{setup['contracts']}\n"
                        f"Entry: <code>{setup['entry_price']:.2f}</code>\n"
                        f"SL: <code>{setup['sl_price']:.2f}</code>  TP: <code>{setup['tp_price']:.2f}</code>\n"
                        f"Displacement: <b>{setup['displacement']}×</b> | Risk: ${setup['usd_risk']:.0f} → Target: ${setup['usd_target']:.0f}"
                    ))
                    _log(f"3-bar order placed — ID {result.get('orderId')}")
                    break
                else:
                    _log(f"3-bar order rejected: {result.get('errorMessage')}", "error")

            except Exception as e:
                _log(f"3-bar error {instrument}: {e}", "error")

    _log("Scalp engine stopped")


# ─── News filter ─────────────────────────────────────────────────────────────

# Phrases that always halt trading when found in a <20-min-old headline
_HALT_PHRASES = [
    "tariff", "trade war", "trade deal",
    "rate cut", "rate hike",
    "executive order",
    "emergency meeting", "emergency rate",
    "government shutdown", "debt ceiling", "debt default",
    "sanctions",
    "nuclear",
]

# Halt if an anchor word appears together with any of its trigger words
_HALT_CONTEXT = {
    "trump":       ["tariff", "trade", "ban", "order", "market", "announce", "tax", "sanction", "deal"],
    "powell":      ["rate", "cut", "hike", "emergency", "surprise", "hawkish", "dovish"],
    "white house": ["tariff", "trade", "order", "announce", "sanction", "ban"],
    "fed ":        ["emergency", "unscheduled", "surprise", "intervene"],
}

_HEADLINE_CACHE: dict = {"data": [], "at": None}
_HEADLINE_TTL   = 300   # seconds — refresh every 5 min


def _breaking_news_halt() -> tuple[bool, str]:
    """Check Yahoo Finance headlines for market-moving breaking news (< 20 min old).
    Returns (halted, headline_snippet)."""
    global _HEADLINE_CACHE
    from datetime import timezone as _utc_tz
    now_et  = datetime.now(NY_TZ)
    now_utc = datetime.now(_utc_tz.utc)

    # Refresh cache if stale
    cache_age = (now_et - _HEADLINE_CACHE["at"]).total_seconds() if _HEADLINE_CACHE["at"] else 9999
    if cache_age > _HEADLINE_TTL:
        try:
            from providers.yahoo import get_news
            _HEADLINE_CACHE = {"data": get_news("QQQ"), "at": now_et}
        except Exception:
            pass

    for item in _HEADLINE_CACHE["data"]:
        ts = item.get("timestamp")
        if not ts:
            continue
        try:
            ts_clean = ts.replace("Z", "+00:00")
            pub = datetime.fromisoformat(ts_clean)
            if pub.tzinfo is None:
                from datetime import timezone as _utc_tz2
                pub = pub.replace(tzinfo=_utc_tz2.utc)
            age_mins = (now_utc - pub).total_seconds() / 60
            if age_mins > 20:   # only care about very recent headlines
                continue
        except Exception:
            continue

        title_lower = item["title"].lower()

        # Exact phrase match
        for phrase in _HALT_PHRASES:
            if phrase in title_lower:
                return True, item["title"][:70]

        # Contextual match — anchor + at least one trigger
        for anchor, triggers in _HALT_CONTEXT.items():
            if anchor in title_lower and any(t in title_lower for t in triggers):
                return True, item["title"][:70]

    return False, ""


def _news_clear(session_name: str) -> tuple[bool, str, int]:
    """Returns (clear, event_name, minutes_away).
    Blocks if: scheduled High-impact USD event within 30 min window,
    OR breaking news headline < 20 min old with market-moving keywords."""

    # 1 — Scheduled economic calendar (ForexFactory)
    try:
        from providers.calendar import get_calendar
        cal = get_calendar()
        events = cal.get("events", [])
        now_et = datetime.now(NY_TZ)
        for ev in events:
            if ev.get("impact") != "High":
                continue
            currencies = ev.get("currencies", ev.get("currency", ""))
            if "USD" not in str(currencies):
                continue
            ev_time_str = ev.get("time", "")
            ev_date_str = ev.get("date", str(now_et.date()))
            try:
                ev_dt = NY_TZ.localize(datetime.strptime(
                    f"{ev_date_str} {ev_time_str}", "%Y-%m-%d %I:%M%p"
                ))
            except Exception:
                continue
            diff_mins = (ev_dt - now_et).total_seconds() / 60
            if -5 <= diff_mins <= 30:
                return False, ev.get("event", "High-impact event"), int(diff_mins)
    except Exception:
        pass

    # 2 — Breaking news / unscheduled events (Trump, surprise Fed, tariff tweet, etc.)
    try:
        halted, headline = _breaking_news_halt()
        if halted:
            return False, f"Breaking news: {headline}", 0
    except Exception:
        pass

    return True, "", 0


# ─── P&L sync ─────────────────────────────────────────────────────────────────

async def _sync_pnl():
    global _daily_pnl
    # Use the currently active account (px._account_id, set to the live PRAC account on startup)
    trades = await px.get_trade_history(days_back=2, account_id=px._account_id)
    # Futures day starts at 6 PM ET — only count trades from this session's open
    now_et = datetime.now(NY_TZ)
    if now_et.hour >= 18:
        session_open_et = now_et.replace(hour=18, minute=0, second=0, microsecond=0)
    else:
        yesterday_et = now_et - timedelta(days=1)
        session_open_et = yesterday_et.replace(hour=18, minute=0, second=0, microsecond=0)
    cutoff = session_open_et.astimezone(UTC).strftime("%Y-%m-%dT%H:%M")
    _daily_pnl = round(sum(
        (t.get("profitAndLoss") or 0) - (t.get("fees") or 0)
        for t in trades
        if t.get("creationTimestamp", "")[:16] >= cutoff
    ), 2)


def _update_profit_locks():
    """Advance daily floor and size factor as P&L crosses thresholds. Returns True if newly locked."""
    global _daily_floor, _daily_size_factor
    newly_locked = False
    for threshold, new_floor, new_factor in PROFIT_LOCKS:
        if _daily_pnl >= threshold and _daily_floor < new_floor:
            _daily_floor       = new_floor
            _daily_size_factor = new_factor
            _log(f"PROFIT LOCK ${threshold:.0f} — floor ${new_floor:.0f} locked | size {new_factor:.0%}", "warning")
            asyncio.create_task(tg.send(
                f"🔒 <b>Profit Lock</b>  P&L <b>${_daily_pnl:.0f}</b>\n"
                f"Floor locked at <b>${new_floor:.0f}</b> | Size → {new_factor:.0%}"
            ))
            newly_locked = True
    return newly_locked


def _is_daily_halted() -> tuple[bool, str]:
    """Returns (halted, reason). Called before placing each trade."""
    if _daily_pnl >= DAILY_MAX_PROFIT:
        return True, f"Max profit ${DAILY_MAX_PROFIT:.0f} reached — done for the day 🎯"
    if _daily_pnl <= -DAILY_MAX_LOSS:
        return True, f"Max daily loss ${DAILY_MAX_LOSS:.0f} hit — locked 🛑"
    if _daily_floor > 0 and _daily_pnl <= _daily_floor:
        return True, f"P&L ${_daily_pnl:.0f} retreated to floor ${_daily_floor:.0f} — locking gains 🔒"
    if _daily_size_factor == 0.0:
        return True, "Daily max profit ceiling — done"
    return False, ""


# ─── Setup analysis ───────────────────────────────────────────────────────────

def _analyze(bars: list, instrument: str, session: dict) -> tuple[Optional[dict], dict]:
    """Returns (setup_or_none, signal_data).
    signal_data is always populated for learning logging even when setup is None."""
    _empty_sig = {"score": 0, "direction": None, "adx": 0, "rsi": 50, "vwap": None, "instrument": instrument}

    if len(bars) < 30:
        return None, _empty_sig

    recent   = bars[-150:]
    last_bar = bars[-1]
    price    = last_bar["close"]
    config   = _INSTRUMENT_CONFIG.get(instrument.upper(), _INSTRUMENT_CONFIG["MNQ"])

    analysis = get_ict_analysis(recent, current_price=price)
    long_sc  = analysis.get("long_setup",  {}).get("score", 0) or 0
    short_sc = analysis.get("short_setup", {}).get("score", 0) or 0
    best_dir = "bullish" if long_sc >= short_sc else "bearish"
    best_sc  = max(long_sc, short_sc)

    adx  = _calc_adx(recent[-60:])
    rsi  = _calc_rsi(recent[-60:])
    now_et = _bar_dt(last_bar)
    vwap = _calc_vwap_at(bars, now_et)

    # Collect ICT signal components for learning
    ict_sig  = analysis.get("long_setup" if best_dir == "bullish" else "short_setup", {}) or {}
    obs_list = analysis.get("order_blocks") or []
    ob_type  = "bullish_ob" if best_dir == "bullish" else "bearish_ob"
    sig_data = {
        "score":          round(best_sc),
        "direction":      best_dir,
        "adx":            round(adx, 1),
        "rsi":            round(rsi, 1),
        "vwap":           round(vwap, 2) if vwap else None,
        "instrument":     instrument,
        "sweep_detected": False,
        "sweep_quality":  None,
        "ifvg_present":   bool(analysis.get("ifvgs")),
        "fvg_present":    bool(analysis.get("fair_value_gaps")),
        "ob_present":     any(o.get("type") == ob_type for o in obs_list),
        "mss_detected":   False,
        "displacement":   ict_sig.get("displacement"),
    }

    if best_sc < session["min_score"]:
        return None, {**sig_data, "skip_reason": "score_low"}

    direction = best_dir
    score     = best_sc

    if adx < 10:
        return None, {**sig_data, "skip_reason": "adx_low"}

    if direction == "bullish" and rsi > 80:
        return None, {**sig_data, "skip_reason": "rsi_extreme"}
    if direction == "bearish" and rsi < 20:
        return None, {**sig_data, "skip_reason": "rsi_extreme"}

    tol = 0.005 if instrument == "MGC" else 0.004
    if vwap:
        if direction == "bullish" and price < vwap * (1 - tol):
            return None, {**sig_data, "skip_reason": "vwap_filter"}
        if direction == "bearish" and price > vwap * (1 + tol):
            return None, {**sig_data, "skip_reason": "vwap_filter"}

    sma = _calc_sma(recent, 200)
    if sma:
        if direction == "bullish" and price < sma * 0.994:
            return None, {**sig_data, "skip_reason": "sma_filter"}
        if direction == "bearish" and price > sma * 1.006:
            return None, {**sig_data, "skip_reason": "sma_filter"}

    # Stop & target
    atr       = _calc_atr(recent[-20:])
    stop_dist = max(atr * 1.5, config["min_stop_pts"], config["stop_buffer"])
    caps      = {"MNQ": 120, "MES": 60, "MGC": 20}
    stop_dist = min(stop_dist, caps.get(instrument, 120))

    tick       = config["tick_size"]
    stop_ticks = max(1, round(stop_dist / tick))
    side       = 0 if direction == "bullish" else 1

    # Volatility-adjusted sizing: target ~$80 risk per contract
    usd_per_pt  = config["dollars_per_point"]
    TARGET_RISK = 80.0
    vol_cts = max(1, round(TARGET_RISK / max(stop_dist * usd_per_pt, 1)))
    # Blend with session contracts (vol floor, session ceiling)
    contracts = min(max(vol_cts, 1), session["contracts"], config["max_contracts"])
    if _trail_mode:
        contracts = max(1, contracts // 2)

    usd_risk = stop_dist * usd_per_pt * contracts
    usd_1r   = usd_risk
    usd_2r   = usd_risk * 2

    if direction == "bullish":
        sl_price = price - stop_dist
        tp_price = price + stop_dist * 2
    else:
        sl_price = price + stop_dist
        tp_price = price - stop_dist * 2

    return {
        "instrument":   instrument,
        "direction":    direction,
        "side":         side,
        "score":        round(score),
        "entry_price":  price,
        "sl_price":     round(sl_price, 2),
        "tp_price":     round(tp_price, 2),
        "stop_ticks":   stop_ticks,
        "stop_dist":    round(stop_dist, 2),
        "contracts":    contracts,
        "atr":          round(atr, 2),
        "adx":          round(adx, 1),
        "rsi":          round(rsi, 1),
        "usd_risk":     round(usd_risk, 2),
        "usd_1r":       round(usd_1r, 2),
        "usd_2r":       round(usd_2r, 2),
        "session":      session["name"],
        "timestamp":    datetime.now(NY_TZ).isoformat(),
        "config":       config,
    }, sig_data


# ─── Position monitoring (partial close + trailing) ──────────────────────────

def _log_trade_outcome(trade: dict, exit_price: float, outcome: str, float_pnl: float):
    """Write completed trade outcome to the learning DB."""
    try:
        import engines.learning as _lrn
        opened = trade.get("opened_at") or datetime.now(NY_TZ).isoformat()
        try:
            dur = int((datetime.fromisoformat(datetime.now(NY_TZ).isoformat()) -
                       datetime.fromisoformat(opened)).total_seconds() / 60)
        except Exception:
            dur = 0
        cfg = trade.get("config") or {}
        trade_ref = trade.get("trade_ref") or f"unknown_{datetime.now(NY_TZ).strftime('%H%M%S')}"
        _lrn.log_outcome(
            eval_id=trade.get("eval_id"),
            trade_ref=trade_ref,
            instrument=trade.get("symbol", ""),
            session=trade.get("session", ""),
            direction=trade.get("direction", ""),
            score=trade.get("score", 0),
            contracts=trade.get("remaining_contracts", trade.get("total_contracts", 1)),
            entry_price=trade.get("entry_price", 0),
            exit_price=exit_price,
            outcome=outcome,
            pnl=round(float_pnl, 2),
            duration_mins=dur,
            max_adverse_excursion=trade.get("mae", 0.0),
            max_favorable_excursion=trade.get("mfe", 0.0),
            adx_at_entry=trade.get("adx"),
            rsi_at_entry=trade.get("rsi"),
            atr_at_entry=trade.get("atr"),
            vwap_position=None,
            htf_bias=trade.get("htf_direction"),
            opened_at=opened,
        )
        # Send Telegram rating prompt
        asyncio.create_task(tg.alert_trade_rating_prompt(
            trade_ref, trade.get("symbol",""), trade.get("direction",""), float_pnl
        ))
    except Exception as e:
        logger.warning(f"_log_trade_outcome error: {e}")


async def _find_stop_order_id(account_id: int, contract_id: str) -> Optional[int]:
    """Find the stop-loss bracket order ID for an open position."""
    orders = await px.get_open_orders(account_id)
    for o in orders:
        if o.get("contractId") == contract_id and o.get("type") in (3, 4, 5):  # Stop/StopLimit/Trail
            return o.get("id")
    return None


async def _monitor_positions():
    """Runs every 5s — manages partial closes and trailing stops."""
    global _active_trade, _trail_mode, _trail_floor, _trail_locked_pnl, _daily_pnl

    while _running:
        await asyncio.sleep(5)
        if not _active_trade or not _running:
            continue

        try:
            sym      = _active_trade.get("symbol")
            config   = _active_trade.get("config", {})
            entry    = _active_trade.get("entry_price", 0)
            side     = _active_trade.get("side", 0)   # 0=long 1=short
            rem_ct   = _active_trade.get("remaining_contracts", 0)
            stop_d   = _active_trade.get("stop_dist", 20)
            usd_pt   = config.get("dollars_per_point", 2)
            tick     = config.get("tick_size", 0.25)

            if rem_ct <= 0:
                _active_trade = {}
                continue

            # Current price
            positions = await px.get_positions()
            if not positions:
                _log(f"Position closed — trade complete")
                closed_trade = dict(_active_trade)
                _active_trade = {}
                await _sync_pnl()
                asyncio.create_task(tg.alert_trade_closed(
                    closed_trade.get("symbol", sym), closed_trade.get("direction",""),
                    0, _daily_pnl, closed_trade.get("session","")
                ))
                _log_trade_outcome(closed_trade, closed_trade.get("entry_price", 0), "manual", 0)
                continue

            pos = next((p for p in positions if sym in (p.get("symbol", ""), p.get("contractId", ""))), None)
            if not pos:
                _active_trade = {}
                await _sync_pnl()
                continue

            quote = px.get_quote(sym)
            if not quote:
                continue
            cur_price = quote.get("lastPrice", entry)

            # Floating P&L on remaining contracts
            if side == 0:   # long
                float_pnl = (cur_price - entry) * usd_pt * rem_ct
                adverse   = max(0.0, entry - cur_price)
                favorable = max(0.0, cur_price - entry)
            else:           # short
                float_pnl = (entry - cur_price) * usd_pt * rem_ct
                adverse   = max(0.0, cur_price - entry)
                favorable = max(0.0, entry - cur_price)

            # Track MAE/MFE in points
            if "mae" in _active_trade:
                _active_trade["mae"] = max(_active_trade["mae"], adverse)
                _active_trade["mfe"] = max(_active_trade["mfe"], favorable)

            # ── Hard stop loss ────────────────────────────────────────────
            sl_price = _active_trade.get("stop_price")
            if sl_price and rem_ct > 0:
                hit_sl = (side == 0 and cur_price <= sl_price) or \
                         (side == 1 and cur_price >= sl_price)
                if hit_sl:
                    _log(f"SL HIT — closing {sym} @ {cur_price:.2f} (SL={sl_price:.2f})", "error")
                    await px.close_position(sym)
                    closed_trade = dict(_active_trade)
                    _active_trade = {}
                    await _sync_pnl()
                    asyncio.create_task(tg.alert_trade_closed(sym, closed_trade.get("direction",""), float_pnl, _daily_pnl, closed_trade.get("session","")))
                    _log_trade_outcome(closed_trade, cur_price, "sl_hit", float_pnl)
                    continue

            # ── Take profit at 2R ─────────────────────────────────────────
            tp_price = _active_trade.get("tp_price") or (
                (entry + stop_d * 2) if side == 0 else (entry - stop_d * 2)
            )
            hit_tp = (side == 0 and cur_price >= tp_price) or \
                     (side == 1 and cur_price <= tp_price)
            if hit_tp:
                _log(f"TP HIT — closing {sym} @ {cur_price:.2f} (TP={tp_price:.2f})", "warning")
                await px.close_position(sym)
                closed_trade = dict(_active_trade)
                _active_trade = {}
                await _sync_pnl()
                asyncio.create_task(tg.alert_trade_closed(sym, closed_trade.get("direction",""), float_pnl, _daily_pnl, closed_trade.get("session","")))
                _log_trade_outcome(closed_trade, cur_price, "tp_hit", float_pnl)
                continue

            # ── Partial close at +1R ──────────────────────────────────────
            if not _active_trade.get("partial_done") and rem_ct > 2:
                threshold_1r = stop_d * usd_pt * rem_ct  # 1R in $
                if float_pnl >= threshold_1r * 0.85:     # 85% of 1R triggers
                    close_ct = max(1, int(rem_ct * PARTIAL_RATIO))
                    if close_ct >= rem_ct:
                        close_ct = rem_ct - 1  # always leave at least 1 runner

                    _log(f"Partial close {close_ct}/{rem_ct} @ +${float_pnl:.0f} (1R hit)", "warning")
                    data = await px.partial_close_position(sym, close_ct)
                    if data.get("success"):
                        _active_trade["remaining_contracts"] = rem_ct - close_ct
                        _active_trade["partial_done"] = True
                        runners = rem_ct - close_ct
                        _log(f"Partial close OK — {runners} runners left")
                        asyncio.create_task(tg.alert_partial_close(sym, close_ct, runners, _daily_pnl + float_pnl * PARTIAL_RATIO))
                    else:
                        _log(f"Partial close failed: {data.get('errorMessage')}", "error")

            # ── Total P&L sync ────────────────────────────────────────────
            await _sync_pnl()
            total_pnl = _daily_pnl + float_pnl

            # ── Trail mode entry ──────────────────────────────────────────
            if total_pnl >= DAILY_TARGET and not _trail_mode:
                _trail_mode       = True
                _trail_locked_pnl = DAILY_TARGET
                _trail_floor      = DAILY_TARGET
                _log(f"Trail mode activated — P&L ${total_pnl:.0f} >= target ${DAILY_TARGET:.0f} ✓", "warning")
                asyncio.create_task(tg.alert_trail_activated(total_pnl, DAILY_TARGET))
                asyncio.create_task(tg.alert_daily_target(total_pnl))

            # ── Trail stop management ─────────────────────────────────────
            if _trail_mode and _active_trade.get("stop_order_id"):
                # Raise trail floor every $50 of gain above current floor
                new_floor = _trail_floor + TRAIL_INCREMENT * int(
                    (total_pnl - _trail_floor) / TRAIL_INCREMENT
                )
                if new_floor > _trail_floor + TRAIL_INCREMENT * 0.9:
                    gain_to_protect = new_floor - _daily_pnl  # how much floating we must keep
                    pts_to_protect  = gain_to_protect / (usd_pt * rem_ct) if rem_ct > 0 else 0

                    # New stop price: moves in direction of trade to lock in gains
                    if side == 0:   # long — stop moves UP
                        new_stop_price = round(cur_price - pts_to_protect, 2)
                        new_stop_ticks = max(4, round(pts_to_protect / tick))
                    else:           # short — stop moves DOWN
                        new_stop_price = round(cur_price + pts_to_protect, 2)
                        new_stop_ticks = max(4, round(pts_to_protect / tick))

                    data = await px.modify_order(
                        _active_trade["stop_order_id"],
                        stop_price=new_stop_price,
                    )
                    if data.get("success"):
                        _trail_floor = new_floor
                        _active_trade["stop_price"] = new_stop_price
                        _log(f"Stop trailed → {new_stop_price:.2f} | floor ${new_floor:.0f} locked", "warning")
                        asyncio.create_task(tg.alert_stop_trailed(sym, new_stop_price, new_floor))

        except Exception as e:
            _log(f"Monitor error: {e}", "error")


# ─── Main trading loop ────────────────────────────────────────────────────────

async def _loop():
    global _running, _last_signal, _current_session_name, _last_check
    global _daily_pnl, _trades_today, _trail_mode, _trail_floor
    global _daily_floor, _daily_size_factor, _scalp_today, _eod_sent

    _log("Auto-trader started ✓  |  Target $800/day  |  22-hr coverage")
    asyncio.create_task(tg.alert_bot_started())

    while _running:
        try:
            now_et = datetime.now(NY_TZ)
            _last_check = now_et.strftime("%H:%M:%S ET")

            # Daily reset at midnight
            if now_et.hour == 0 and now_et.minute < 2:
                _trades_today       = 0
                _scalp_today        = 0
                _session_trades.clear()
                _last_scalp_time.clear()
                _trail_mode         = False
                _trail_floor        = 0.0
                _daily_floor        = -DAILY_MAX_LOSS
                _daily_size_factor  = 1.0
                _eod_sent           = False
                _log("New trading day — all counters reset")

            # ── End-of-day summary at 3:50 PM ET ─────────────────────────
            if now_et.hour == 15 and now_et.minute == 50 and not _eod_sent:
                _eod_sent = True
                today_log = [t for t in _trade_log if t.get("timestamp", "")[:10] == str(now_et.date())]
                wins_log  = [t for t in today_log if t.get("pnl", 0) > 0]
                loss_log  = [t for t in today_log if t.get("pnl", 0) <= 0]
                best  = max((t.get("pnl",0) for t in today_log), default=0)
                worst = min((t.get("pnl",0) for t in today_log), default=0)
                asyncio.create_task(tg.alert_daily_summary(
                    pnl=_daily_pnl, trades=_trades_today, scalps=_scalp_today,
                    wins=len(wins_log), losses=len(loss_log),
                    best=best, worst=worst,
                ))

            # Market closed?
            if not _market_open():
                _current_session_name = "Closed (4–6 PM ET)"
                _log("Market closed — waiting for 6 PM ET reopen")
                await asyncio.sleep(120)
                continue

            # Progressive profit locks + daily halt check
            await _sync_pnl()
            _update_profit_locks()
            halted, halt_reason = _is_daily_halted()
            if halted:
                _current_session_name = f"HALTED — {halt_reason}"
                _log(halt_reason, "warning" if _daily_pnl > 0 else "error")
                if _daily_pnl <= -DAILY_MAX_LOSS:
                    asyncio.create_task(tg.alert_daily_halt(_daily_pnl, DAILY_MAX_LOSS))
                await asyncio.sleep(600)
                continue

            if _trades_today >= MAX_DAILY_TRADES:
                _log(f"Max {MAX_DAILY_TRADES} trades reached — resting until next session")
                await asyncio.sleep(300)
                continue

            session = _current_session()
            _current_session_name = session["name"] if session else "Between sessions"

            if not session:
                await asyncio.sleep(15)
                continue

            sess_count = _session_trades.get(session["name"], 0)
            if sess_count >= session["max_trades"]:
                await asyncio.sleep(30)
                continue

            # Already in a position? Monitor handles it, just wait
            positions = await px.get_positions()
            if positions:
                await asyncio.sleep(5)
                continue

            # News filter — skip if high-impact USD event within 30 min
            news_clear, news_event, news_mins = _news_clear(session["name"])
            if not news_clear:
                _log(f"NEWS BLOCK: {news_event} in {news_mins}min — skipping scan", "warning")
                asyncio.create_task(tg.alert_news_block(news_event, news_mins, session["name"]))
                await asyncio.sleep(30)
                continue

            # Scan all instruments — collect candidates, pick highest score (correlation filter)
            all_candidates: list[tuple] = []  # (candidate, sig_data, htf_dir, instrument)
            for instrument in session["instruments"]:
                try:
                    bars_15m = await px.get_bars(instrument, interval="15m", limit=30)
                    if bars_15m:
                        if bars_15m[0]["time"] > bars_15m[-1]["time"]:
                            bars_15m = list(reversed(bars_15m))
                        closes_15m = [b["close"] for b in bars_15m[-10:]]
                        sma_15m = sum(closes_15m) / len(closes_15m) if closes_15m else None
                        last_close_15m = bars_15m[-1]["close"] if bars_15m else None
                    else:
                        sma_15m = last_close_15m = None
                except Exception:
                    sma_15m = last_close_15m = None

                bar_data = await _bars(instrument)
                if not bar_data:
                    continue

                if not _vol_ok(bar_data, session.get("vol_regime_pct", 4.0)):
                    continue

                daily   = await _daily_bars(instrument)
                htf     = get_htf_bias(daily) if daily else {}
                htf_dir = htf.get("direction", "neutral")

                candidate, sig_data = _analyze(bar_data, instrument, session)
                if not candidate:
                    reason = sig_data.get("skip_reason", "no_setup")
                    # Only log skips that are worth knowing about (not routine score_low noise)
                    if reason not in ("score_low", "no_setup"):
                        _log(f"{session['name']} | {instrument}: skip ({reason}, HTF={htf_dir})")
                    # Log below-threshold evaluations as ghost trades when score was close
                    if sig_data.get("score", 0) >= session["min_score"] - 8:
                        try:
                            import engines.learning as _lrn
                            _lrn.log_evaluation(
                                instrument=instrument, session=session["name"],
                                direction=sig_data.get("direction") or "bullish",
                                score=sig_data.get("score", 0),
                                min_score_required=session["min_score"],
                                traded=False, skip_reason=reason,
                                price=sig_data.get("price"), atr=sig_data.get("atr"),
                                adx=sig_data.get("adx"), rsi=sig_data.get("rsi"),
                                vwap=sig_data.get("vwap"), htf_bias=htf_dir,
                                sweep_detected=sig_data.get("sweep_detected", False),
                                sweep_quality=sig_data.get("sweep_quality"),
                                ifvg_present=sig_data.get("ifvg_present", False),
                                fvg_present=sig_data.get("fvg_present", False),
                                ob_present=sig_data.get("ob_present", False),
                                mss_detected=sig_data.get("mss_detected", False),
                                displacement=sig_data.get("displacement"),
                            )
                        except Exception:
                            pass
                    continue

                d = candidate["direction"]

                # HTF alignment check
                if htf_dir in ("strong_bullish","bullish","bullish_lean") and d == "bearish":
                    _log(f"{instrument}: contra HTF {htf_dir} — skip")
                    try:
                        import engines.learning as _lrn
                        _lrn.log_evaluation(
                            instrument=instrument, session=session["name"],
                            direction=d, score=candidate["score"],
                            min_score_required=session["min_score"],
                            traded=False, skip_reason="htf_contra",
                            price=candidate["entry_price"], atr=candidate["atr"],
                            adx=candidate["adx"], rsi=candidate["rsi"],
                            vwap=sig_data.get("vwap"), htf_bias=htf_dir,
                            sweep_detected=sig_data.get("sweep_detected", False),
                            sweep_quality=sig_data.get("sweep_quality"),
                            ifvg_present=sig_data.get("ifvg_present", False),
                            fvg_present=sig_data.get("fvg_present", False),
                            ob_present=sig_data.get("ob_present", False),
                            mss_detected=sig_data.get("mss_detected", False),
                            ghost_entry=candidate["entry_price"],
                            ghost_sl=candidate["sl_price"],
                            ghost_tp=candidate["tp_price"],
                            ghost_stop_ticks=candidate["stop_ticks"],
                        )
                    except Exception:
                        pass
                    continue
                if htf_dir in ("strong_bearish","bearish","bearish_lean") and d == "bullish":
                    _log(f"{instrument}: contra HTF {htf_dir} — skip")
                    try:
                        import engines.learning as _lrn
                        _lrn.log_evaluation(
                            instrument=instrument, session=session["name"],
                            direction=d, score=candidate["score"],
                            min_score_required=session["min_score"],
                            traded=False, skip_reason="htf_contra",
                            price=candidate["entry_price"], atr=candidate["atr"],
                            adx=candidate["adx"], rsi=candidate["rsi"],
                            vwap=sig_data.get("vwap"), htf_bias=htf_dir,
                            sweep_detected=sig_data.get("sweep_detected", False),
                            sweep_quality=sig_data.get("sweep_quality"),
                            ifvg_present=sig_data.get("ifvg_present", False),
                            fvg_present=sig_data.get("fvg_present", False),
                            ob_present=sig_data.get("ob_present", False),
                            mss_detected=sig_data.get("mss_detected", False),
                            ghost_entry=candidate["entry_price"],
                            ghost_sl=candidate["sl_price"],
                            ghost_tp=candidate["tp_price"],
                            ghost_stop_ticks=candidate["stop_ticks"],
                        )
                    except Exception:
                        pass
                    continue

                # 15m confirmation
                if sma_15m and last_close_15m:
                    if d == "bullish" and last_close_15m < sma_15m * 0.997:
                        _log(f"{instrument}: 15m below SMA — skip long")
                        continue
                    if d == "bearish" and last_close_15m > sma_15m * 1.003:
                        _log(f"{instrument}: 15m above SMA — skip short")
                        continue

                # Apply daily size factor
                raw_cts = candidate["contracts"]
                scaled  = max(1, round(raw_cts * _daily_size_factor))
                if scaled != raw_cts:
                    candidate["contracts"] = scaled
                    cfg2 = _INSTRUMENT_CONFIG.get(instrument.upper(), _INSTRUMENT_CONFIG["MNQ"])
                    candidate["usd_risk"] = round(candidate["stop_dist"] * cfg2["dollars_per_point"] * scaled, 2)

                candidate["htf_direction"] = htf_dir
                all_candidates.append((candidate, sig_data, htf_dir, instrument))

            # Correlation filter: if multiple instruments pass, pick the highest score
            # (avoids taking correlated long MNQ + long MES simultaneously)
            setup = None
            if all_candidates:
                all_candidates.sort(key=lambda x: x[0]["score"], reverse=True)
                best_cand, best_sig, best_htf, best_inst = all_candidates[0]
                setup = best_cand
                # Log skipped correlated instruments
                for cand, sig, htf, inst in all_candidates[1:]:
                    _log(f"{inst}: skipped — {best_inst} has higher score ({best_cand['score']} vs {cand['score']})")
                    try:
                        import engines.learning as _lrn
                        _lrn.log_evaluation(
                            instrument=inst, session=session["name"],
                            direction=cand["direction"], score=cand["score"],
                            min_score_required=session["min_score"],
                            traded=False, skip_reason="correlation",
                            price=cand["entry_price"], atr=cand["atr"],
                            adx=cand["adx"], rsi=cand["rsi"],
                            vwap=sig.get("vwap"), htf_bias=htf,
                            ghost_entry=cand["entry_price"],
                            ghost_sl=cand["sl_price"],
                            ghost_tp=cand["tp_price"],
                            ghost_stop_ticks=cand["stop_ticks"],
                        )
                    except Exception:
                        pass
                _log(
                    f"✓ {session['name']} | {best_inst} {best_cand['direction'].upper()} "
                    f"score={best_cand['score']} ADX={best_cand['adx']} RSI={best_cand['rsi']} "
                    f"x{best_cand['contracts']} risk=${best_cand['usd_risk']:.0f} "
                    f"HTF={best_htf} | floor=${_daily_floor:.0f} size={_daily_size_factor:.0%}"
                )

            _last_signal = setup or {"session": session["name"],
                                     "timestamp": now_et.isoformat(), "result": "no setup"}
            if not setup:
                await asyncio.sleep(5)
                continue

            _log(
                f"PLACING: {setup['instrument']} {setup['direction'].upper()} "
                f"x{setup['contracts']} @ {setup['entry_price']:.2f} | "
                f"SL={setup['sl_price']:.2f}  2R_TP={setup['tp_price']:.2f}"
            )

            sl_ticks = setup["stop_ticks"]
            tp_ticks = sl_ticks * 2
            result = await px.place_order(
                symbol=setup["instrument"],
                side=setup["side"],
                size=setup["contracts"],
                order_type=2,
                stop_loss_ticks=sl_ticks,
                take_profit_ticks=tp_ticks,
            )

            if result.get("success"):
                order_id  = result.get("orderId")
                trade_ref = f"{setup['instrument']}_{datetime.now(NY_TZ).strftime('%Y%m%d_%H%M%S')}"
                _log(f"ORDER PLACED — ID {order_id}", "warning")
                asyncio.create_task(tg.alert_trade_opened(setup))

                # Log to learning DB
                try:
                    import engines.learning as _lrn
                    _eval_id = _lrn.log_evaluation(
                        instrument=setup["instrument"], session=session["name"],
                        direction=setup["direction"], score=setup["score"],
                        min_score_required=session["min_score"],
                        traded=True,
                        price=setup["entry_price"], atr=setup["atr"],
                        adx=setup["adx"], rsi=setup["rsi"],
                        vwap=best_sig.get("vwap") if all_candidates else None,
                        htf_bias=setup.get("htf_direction"),
                        sweep_detected=best_sig.get("sweep_detected", False) if all_candidates else False,
                        sweep_quality=best_sig.get("sweep_quality") if all_candidates else None,
                        ifvg_present=best_sig.get("ifvg_present", False) if all_candidates else False,
                        fvg_present=best_sig.get("fvg_present", False) if all_candidates else False,
                        ob_present=best_sig.get("ob_present", False) if all_candidates else False,
                        mss_detected=best_sig.get("mss_detected", False) if all_candidates else False,
                        displacement=setup.get("atr"),
                        trade_ref=trade_ref,
                    )
                except Exception as _le:
                    _eval_id = None
                    _log(f"Learning log error: {_le}", "error")

                # Mirror to additional accounts if configured
                mirror_ids = px.get_mirror_account_ids()
                for mirror_id in mirror_ids:
                    try:
                        mr = await px.place_order(
                            symbol=setup["instrument"],
                            side=setup["side"],
                            size=setup["contracts"],
                            order_type=2,
                            stop_loss_ticks=sl_ticks,
                            take_profit_ticks=tp_ticks,
                            account_id=mirror_id,
                        )
                        if mr.get("success"):
                            _log(f"Mirror account {mirror_id}: order {mr.get('orderId')} placed")
                        else:
                            _log(f"Mirror account {mirror_id}: {mr.get('errorMessage')}", "error")
                    except Exception as e:
                        _log(f"Mirror account {mirror_id} error: {e}", "error")

                # Wait briefly then find the stop bracket order ID
                await asyncio.sleep(3)
                contract_id = px._contract_cache.get(setup["instrument"])
                stop_oid = await _find_stop_order_id(px._account_id, contract_id)

                global _active_trade
                _active_trade = {
                    "symbol":              setup["instrument"],
                    "direction":           setup["direction"],
                    "side":                setup["side"],
                    "entry_price":         setup["entry_price"],
                    "total_contracts":     setup["contracts"],
                    "remaining_contracts": setup["contracts"],
                    "stop_price":          setup["sl_price"],
                    "tp_price":            setup["tp_price"],
                    "stop_order_id":       stop_oid,
                    "partial_done":        False,
                    "stop_dist":           setup["stop_dist"],
                    "order_id":            order_id,
                    "config":              setup["config"],
                    "usd_1r":              setup["usd_1r"],
                    "session":             session["name"],
                    "timestamp":           setup["timestamp"],
                    # Learning tracking
                    "eval_id":             _eval_id,
                    "trade_ref":           trade_ref,
                    "opened_at":           datetime.now(NY_TZ).isoformat(),
                    "score":               setup["score"],
                    "adx":                 setup["adx"],
                    "rsi":                 setup["rsi"],
                    "atr":                 setup["atr"],
                    "mae":                 0.0,   # max adverse excursion (points)
                    "mfe":                 0.0,   # max favorable excursion (points)
                }

                _trade_log.append({**setup, "order_id": order_id, "stop_order_id": stop_oid})
                _trades_today += 1
                _session_trades[session["name"]] = sess_count + 1
                _log(f"Trade tracked | stop_order_id={stop_oid} | 1R=${setup['usd_1r']:.0f}")

                # Auto-journal entry
                try:
                    from database import save_trade
                    asyncio.create_task(save_trade({
                        "symbol":       setup["instrument"],
                        "direction":    "long" if setup["side"] == 0 else "short",
                        "entry":        setup["entry_price"],
                        "exit":         None,
                        "result":       None,
                        "r_multiple":   None,
                        "setup_type":   f"ICT-{session['name']}",
                        "bias_at_entry": setup.get("htf_direction", ""),
                        "confidence":   setup["score"],
                        "notes":        (
                            f"Bot auto-entry | score={setup['score']} "
                            f"ADX={setup['adx']} RSI={setup['rsi']} "
                            f"contracts={setup['contracts']} risk=${setup['usd_risk']:.0f}"
                        ),
                        "mistake_tag":  None,
                        "lesson":       None,
                    }))
                except Exception as je:
                    _log(f"Journal write failed: {je}", "error")
                await asyncio.sleep(45)  # brief wait after order before next scan
            else:
                err = result.get("errorMessage", "unknown")
                _log(f"ORDER REJECTED: {err}", "error")
                await asyncio.sleep(5)

        except asyncio.CancelledError:
            break
        except Exception as e:
            import traceback as _tb
            _log(f"Loop error: {e} | {_tb.format_exc().splitlines()[-2]}", "error")
            await asyncio.sleep(5)

    _log("Auto-trader stopped")
    asyncio.create_task(tg.alert_bot_stopped())


# ─── Start / Stop ─────────────────────────────────────────────────────────────

async def start():
    global _running, _task, _monitor_task, _scalp_task, _session_start_balance, _ghost_task
    if _running:
        return False
    # Init learning DB and start ghost tracker
    try:
        import engines.learning as _lrn
        _lrn.init_db()
        _ghost_task = asyncio.create_task(_lrn.ghost_tracker_loop())
    except Exception as e:
        logger.warning(f"Learning engine init failed: {e}")
    # Snapshot balance at session start so frontend can show true session P&L
    try:
        accounts = await px.get_accounts()
        primary = next((a for a in accounts if a.get("id") == px._account_id), accounts[0] if accounts else {})
        _session_start_balance = float(primary.get("balance", 0))
    except Exception:
        _session_start_balance = 0.0
    _running      = True
    _task         = asyncio.create_task(_loop())
    _monitor_task = asyncio.create_task(_monitor_positions())
    _scalp_task   = asyncio.create_task(_scalp_loop())
    # Poll Telegram for trade ratings every 60s
    async def _rating_poll_loop():
        while _running:
            await asyncio.sleep(60)
            await tg.poll_ratings()
    asyncio.create_task(_rating_poll_loop())
    return True


async def stop():
    global _running, _task, _monitor_task, _scalp_task, _ghost_task
    _running = False
    for t in (_task, _monitor_task, _scalp_task, _ghost_task):
        if t:
            t.cancel()
    _task = _monitor_task = _scalp_task = _ghost_task = None
    return True


def reset_daily_pnl():
    """Zero out the daily P&L counter — use after resetting/switching to a fresh account."""
    global _daily_pnl, _daily_floor, _daily_size_factor, _trades_today, _session_trades
    _daily_pnl        = 0.0
    _daily_floor      = -DAILY_MAX_LOSS
    _daily_size_factor = 1.0
    _trades_today     = 0
    _session_trades   = {}
    _log("Daily P&L reset to 0 — fresh start ✓", "warning")
