"""Advanced ICT / Smart Money signals: MSS, CHoCH, sweeps, OTE, IPDA, SMT, PO3."""
from typing import Optional
from datetime import datetime, timedelta
import pytz

NY_TZ = pytz.timezone("America/New_York")


def _minutes_ago(time_str: Optional[str]) -> Optional[float]:
    """Return how many minutes ago this bar timestamp is, or None if unparseable."""
    if not time_str:
        return None
    try:
        from datetime import timezone
        s = time_str
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 60
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Swing point detection
# ---------------------------------------------------------------------------

def detect_swings(bars: list, lookback: int = 3) -> dict:
    """Identify pivot highs and pivot lows."""
    highs, lows = [], []
    n = len(bars)
    for i in range(lookback, n - lookback):
        h = bars[i].get("high")
        l = bars[i].get("low")
        if h is None or l is None:
            continue
        # Swing high: highest in window
        window_highs = [bars[j].get("high", 0) for j in range(i - lookback, i + lookback + 1) if j != i]
        if all(h >= wh for wh in window_highs if wh):
            highs.append({"index": i, "price": round(h, 2), "time": bars[i].get("time")})
        # Swing low
        window_lows = [bars[j].get("low", float("inf")) for j in range(i - lookback, i + lookback + 1) if j != i]
        if all(l <= wl for wl in window_lows if wl != float("inf")):
            lows.append({"index": i, "price": round(l, 2), "time": bars[i].get("time")})
    return {"swing_highs": highs[-10:], "swing_lows": lows[-10:]}


# ---------------------------------------------------------------------------
# MSS / CHoCH detection
# ---------------------------------------------------------------------------

def detect_mss_choch(bars: list, swings: Optional[dict] = None) -> dict:
    """
    Detect Market Structure Shift and Change of Character.

    CHoCH: price closes beyond a recent swing in opposite direction (lower TF signal)
    MSS: CHoCH confirmed with strong displacement (higher confidence reversal)
    """
    if swings is None:
        swings = detect_swings(bars)

    swing_highs = swings.get("swing_highs", [])
    swing_lows = swings.get("swing_lows", [])
    events = []

    if len(bars) < 5 or not swing_highs or not swing_lows:
        return {"events": events, "last_structure": "unknown", "bias": "neutral"}

    # Look at the most recent swing high and low
    last_high = swing_highs[-1] if swing_highs else None
    last_low = swing_lows[-1] if swing_lows else None

    # Check recent bars for structure breaks
    for i in range(max(1, len(bars) - 20), len(bars)):
        b = bars[i]
        close = b.get("close")
        if close is None:
            continue

        # Bearish CHoCH: close below the most recent swing low
        if last_low and close < last_low["price"] and i > last_low["index"]:
            prev_bar = bars[i - 1]
            displacement = abs(close - (prev_bar.get("open") or close))
            is_mss = displacement > 0.3  # strong displacement = MSS
            events.append({
                "type": "MSS_bearish" if is_mss else "CHoCH_bearish",
                "label": "MSS ↓" if is_mss else "CHoCH ↓",
                "price": round(close, 2),
                "broken_level": last_low["price"],
                "time": b.get("time"),
                "description": (
                    f"Bearish MSS — strong close below swing low {last_low['price']:.2f}. "
                    f"Structure shifted bearish." if is_mss else
                    f"Bearish CHoCH — close below swing low {last_low['price']:.2f}. "
                    f"Watch for distribution."
                ),
                "color": "red",
            })

        # Bullish CHoCH: close above the most recent swing high
        if last_high and close > last_high["price"] and i > last_high["index"]:
            prev_bar = bars[i - 1]
            displacement = abs(close - (prev_bar.get("open") or close))
            is_mss = displacement > 0.3
            events.append({
                "type": "MSS_bullish" if is_mss else "CHoCH_bullish",
                "label": "MSS ↑" if is_mss else "CHoCH ↑",
                "price": round(close, 2),
                "broken_level": last_high["price"],
                "time": b.get("time"),
                "description": (
                    f"Bullish MSS — strong close above swing high {last_high['price']:.2f}. "
                    f"Structure shifted bullish." if is_mss else
                    f"Bullish CHoCH — close above swing high {last_high['price']:.2f}. "
                    f"Watch for accumulation."
                ),
                "color": "green",
            })

    # Overall structure bias from last few swings
    last_structure = "neutral"
    if len(swing_highs) >= 2 and len(swing_lows) >= 2:
        hh = swing_highs[-1]["price"] > swing_highs[-2]["price"]
        hl = swing_lows[-1]["price"] > swing_lows[-2]["price"]
        lh = swing_highs[-1]["price"] < swing_highs[-2]["price"]
        ll = swing_lows[-1]["price"] < swing_lows[-2]["price"]
        if hh and hl:
            last_structure = "bullish"
        elif lh and ll:
            last_structure = "bearish"
        elif hh or hl:
            last_structure = "bullish_lean"
        elif lh or ll:
            last_structure = "bearish_lean"

    return {
        "events": events[-5:],
        "last_structure": last_structure,
        "bias": last_structure,
    }


# ---------------------------------------------------------------------------
# Liquidity sweep detector
# ---------------------------------------------------------------------------

def detect_liquidity_sweeps(bars: list, session_levels: dict, equal_hl: Optional[dict] = None) -> list:
    """
    Detect when price wicked through a key level but closed back inside (sweep/stop hunt).
    """
    sweeps = []
    if len(bars) < 3:
        return sweeps

    # Build level list to check
    levels = []
    for key, label in [
        ("asia_high", "Asia High"), ("asia_low", "Asia Low"),
        ("london_high", "London High"), ("london_low", "London Low"),
        ("premarket_high", "Pre-Market High"), ("premarket_low", "Pre-Market Low"),
        ("prev_day_high", "Prev Day High"), ("prev_day_low", "Prev Day Low"),
        ("today_high", "Today's High"), ("today_low", "Today's Low"),
    ]:
        v = session_levels.get(key)
        if v:
            levels.append({"level": v, "label": label, "is_high": "high" in key})

    if equal_hl:
        for eh in equal_hl.get("equal_highs", []):
            levels.append({"level": eh["level"], "label": f"EQH {eh['level']:.2f}", "is_high": True})
        for el in equal_hl.get("equal_lows", []):
            levels.append({"level": el["level"], "label": f"EQL {el['level']:.2f}", "is_high": False})

    # Check recent bars for wick-through + body-close-back
    for i in range(max(1, len(bars) - 30), len(bars)):
        b = bars[i]
        high, low = b.get("high"), b.get("low")
        open_, close = b.get("open"), b.get("close")
        if None in (high, low, open_, close):
            continue

        body_high = max(open_, close)
        body_low = min(open_, close)

        for lvl in levels:
            lv = lvl["level"]
            label = lvl["label"]
            is_high_level = lvl["is_high"]

            # Bullish sweep: wick below level, body closes above
            if is_high_level is False and low < lv and body_low >= lv:
                sweeps.append({
                    "type": "bullish_sweep",
                    "label": f"Swept {label}",
                    "level": lv,
                    "wick_low": round(low, 2),
                    "close": round(close, 2),
                    "time": b.get("time"),
                    "minutes_ago": round(_minutes_ago(b.get("time")) or 0),
                    "is_fresh": (_minutes_ago(b.get("time")) or 999) <= 90,
                    "description": (
                        f"Bullish sweep of {label} ({lv:.2f}) — wick below, closed above. "
                        f"Stop-hunt complete. Look for bullish iFVG entry targeting higher draws."
                    ),
                    "direction": "bullish",
                })

            # Bearish sweep: wick above level, body closes below
            if is_high_level is True and high > lv and body_high <= lv:
                sweeps.append({
                    "type": "bearish_sweep",
                    "label": f"Swept {label}",
                    "level": lv,
                    "wick_high": round(high, 2),
                    "close": round(close, 2),
                    "time": b.get("time"),
                    "minutes_ago": round(_minutes_ago(b.get("time")) or 0),
                    "is_fresh": (_minutes_ago(b.get("time")) or 999) <= 90,
                    "description": (
                        f"Bearish sweep of {label} ({lv:.2f}) — wick above, closed below. "
                        f"Stop-hunt complete. Look for bearish iFVG entry targeting lower draws."
                    ),
                    "direction": "bearish",
                })

    return sweeps[-10:]


# ---------------------------------------------------------------------------
# OTE Zone (Optimal Trade Entry 0.618–0.786 Fib)
# ---------------------------------------------------------------------------

def calc_ote_zone(bars: list, swings: Optional[dict] = None, direction: str = "bullish") -> Optional[dict]:
    """
    Calculate the OTE retracement zone from the most recent impulse leg.

    For a bullish setup: measure from the sweep low to the subsequent high.
    OTE = 0.618 to 0.786 retracement into that leg (discount zone for entry).
    """
    if swings is None:
        swings = detect_swings(bars)

    highs = swings.get("swing_highs", [])
    lows = swings.get("swing_lows", [])

    if not highs or not lows:
        return None

    if direction == "bullish":
        # Impulse: from most recent low to most recent high (after that low)
        anchor_low = lows[-1]
        # Find highest high AFTER the anchor low
        highs_after = [h for h in highs if h["index"] > anchor_low["index"]]
        if not highs_after:
            return None
        anchor_high = max(highs_after, key=lambda x: x["price"])
        leg_low, leg_high = anchor_low["price"], anchor_high["price"]
        leg_range = leg_high - leg_low
        if leg_range <= 0:
            return None
        ote_top = round(leg_high - 0.618 * leg_range, 2)   # 0.618 retrace
        ote_bot = round(leg_high - 0.786 * leg_range, 2)   # 0.786 retrace
        eq = round((ote_top + ote_bot) / 2, 2)
        return {
            "direction": "bullish",
            "leg_high": round(leg_high, 2),
            "leg_low": round(leg_low, 2),
            "ote_top": ote_top,
            "ote_bottom": ote_bot,
            "equilibrium": eq,
            "description": (
                f"Bullish OTE {ote_bot:.2f}–{ote_top:.2f} (0.786–0.618 retrace of "
                f"{leg_low:.2f}→{leg_high:.2f}). Price entering this zone = optimal long entry."
            ),
        }
    else:
        anchor_high = highs[-1]
        lows_after = [l for l in lows if l["index"] > anchor_high["index"]]
        if not lows_after:
            return None
        anchor_low = min(lows_after, key=lambda x: x["price"])
        leg_high, leg_low = anchor_high["price"], anchor_low["price"]
        leg_range = leg_high - leg_low
        if leg_range <= 0:
            return None
        ote_bot = round(leg_low + 0.618 * leg_range, 2)
        ote_top = round(leg_low + 0.786 * leg_range, 2)
        eq = round((ote_top + ote_bot) / 2, 2)
        return {
            "direction": "bearish",
            "leg_high": round(leg_high, 2),
            "leg_low": round(leg_low, 2),
            "ote_top": ote_top,
            "ote_bottom": ote_bot,
            "equilibrium": eq,
            "description": (
                f"Bearish OTE {ote_bot:.2f}–{ote_top:.2f} (0.618–0.786 retrace of "
                f"{leg_high:.2f}→{leg_low:.2f}). Price entering this zone = optimal short entry."
            ),
        }


# ---------------------------------------------------------------------------
# IPDA Levels (20 / 40 / 60 day rolling highs and lows)
# ---------------------------------------------------------------------------

def calc_ipda_levels(bars: list) -> dict:
    """
    IPDA draw levels: 20, 40, 60 trading-day rolling highs and lows.
    Approximated from available intraday bars (5m → group by day).
    """
    if not bars:
        return {}

    # Group bars by trading date (ET)
    days: dict = {}
    for b in bars:
        t_raw = b.get("time", "")
        try:
            if t_raw.endswith("Z"):
                t_raw = t_raw[:-1] + "+00:00"
            dt_et = datetime.fromisoformat(t_raw).astimezone(NY_TZ)
            day_key = dt_et.date().isoformat()
        except Exception:
            continue
        h, l = b.get("high"), b.get("low")
        if h is None or l is None:
            continue
        if day_key not in days:
            days[day_key] = {"high": h, "low": l}
        else:
            days[day_key]["high"] = max(days[day_key]["high"], h)
            days[day_key]["low"] = min(days[day_key]["low"], l)

    sorted_days = sorted(days.keys())
    result = {}
    for period in [20, 40, 60]:
        recent = sorted_days[-period:] if len(sorted_days) >= period else sorted_days
        if not recent:
            continue
        period_high = max(days[d]["high"] for d in recent)
        period_low = min(days[d]["low"] for d in recent)
        result[f"ipda_{period}d_high"] = round(period_high, 2)
        result[f"ipda_{period}d_low"] = round(period_low, 2)
        result[f"ipda_{period}d_range"] = round(period_high - period_low, 2)

    return result


# ---------------------------------------------------------------------------
# SMT Divergence (QQQ vs SPY non-confirmation)
# ---------------------------------------------------------------------------

def detect_smt_divergence(
    bars_primary: list,
    bars_secondary: list,
    lookback: int = 10,
) -> dict:
    """
    Detect SMT divergence between two correlated instruments.

    Bearish SMT: primary makes higher high, secondary does NOT confirm.
    Bullish SMT: primary makes lower low, secondary does NOT confirm.
    """
    if len(bars_primary) < lookback + 2 or len(bars_secondary) < lookback + 2:
        return {"detected": False, "type": None, "description": "Insufficient data for SMT"}

    def recent_extremes(bars, n):
        recent = bars[-n:]
        highs = [b.get("high") for b in recent if b.get("high")]
        lows = [b.get("low") for b in recent if b.get("low")]
        return (max(highs) if highs else None), (min(lows) if lows else None)

    p_high, p_low = recent_extremes(bars_primary, lookback)
    s_high, s_low = recent_extremes(bars_secondary, lookback)
    pp_high, pp_low = recent_extremes(bars_primary, lookback * 2)
    ps_high, ps_low = recent_extremes(bars_secondary, lookback * 2)

    if None in (p_high, p_low, s_high, s_low, pp_high, pp_low, ps_high, ps_low):
        return {"detected": False, "type": None, "description": "Missing price data"}

    # Bearish SMT: primary new high, secondary fails to confirm
    bearish_smt = (p_high > pp_high) and (s_high < ps_high)
    # Bullish SMT: primary new low, secondary fails to confirm
    bullish_smt = (p_low < pp_low) and (s_low > ps_low)

    if bearish_smt:
        return {
            "detected": True,
            "type": "bearish_smt",
            "label": "Bearish SMT",
            "description": (
                f"Bearish SMT divergence — primary made new high ({p_high:.2f}) "
                f"but secondary failed to confirm. Weakness signal. "
                f"Watch for reversal / bearish iFVG setup."
            ),
            "color": "red",
        }
    if bullish_smt:
        return {
            "detected": True,
            "type": "bullish_smt",
            "label": "Bullish SMT",
            "description": (
                f"Bullish SMT divergence — primary made new low ({p_low:.2f}) "
                f"but secondary failed to confirm. Strength signal. "
                f"Watch for reversal / bullish iFVG setup."
            ),
            "color": "green",
        }

    return {"detected": False, "type": None, "description": "No SMT divergence detected"}


# ---------------------------------------------------------------------------
# PO3 / AMD Phase (Accumulation → Manipulation → Distribution)
# ---------------------------------------------------------------------------

def detect_po3_phase(bars: list, session_levels: dict) -> dict:
    """
    Detect which AMD phase the current NY session is in.

    Accumulation: low volatility range before sweep
    Manipulation: sweep of a key level (stop hunt)
    Distribution: price delivers away from the sweep toward the target
    """
    if not bars or not session_levels:
        return {"phase": "unknown", "description": "Insufficient data"}

    now_et = datetime.now(NY_TZ)
    session_open_m = 9 * 60 + 30
    current_m = now_et.hour * 60 + now_et.minute
    minutes_since_open = current_m - session_open_m

    # Get today's bars only (from 9:30 onward)
    today_et = now_et.date()
    today_bars = []
    for b in bars:
        t_raw = b.get("time", "")
        try:
            if t_raw.endswith("Z"):
                t_raw = t_raw[:-1] + "+00:00"
            dt_et = datetime.fromisoformat(t_raw).astimezone(NY_TZ)
            bar_m = dt_et.hour * 60 + dt_et.minute
            if dt_et.date() == today_et and bar_m >= session_open_m:
                today_bars.append(b)
        except Exception:
            continue

    if not today_bars:
        return {"phase": "pre_market", "description": "Market not yet open or no today bars"}

    if minutes_since_open < 0:
        return {"phase": "pre_market", "description": "Pre-market: mark your levels, don't trade yet"}

    today_highs = [b.get("high") for b in today_bars if b.get("high")]
    today_lows = [b.get("low") for b in today_bars if b.get("low")]
    today_closes = [b.get("close") for b in today_bars if b.get("close")]

    if not today_highs or not today_lows:
        return {"phase": "accumulation", "description": "Waiting for opening range to form"}

    session_high = max(today_highs)
    session_low = min(today_lows)
    current_price = today_closes[-1] if today_closes else None
    session_range = session_high - session_low

    # Check if a key level was swept
    key_levels = []
    for key in ["asia_high", "asia_low", "london_high", "london_low", "prev_day_high", "prev_day_low"]:
        v = session_levels.get(key)
        if v:
            key_levels.append(v)

    swept_level = None
    for lv in key_levels:
        if session_low < lv < session_high:
            swept_level = lv
            break

    # Determine phase based on time + price action
    if minutes_since_open <= 15:
        phase = "accumulation"
        desc = "Opening range forming (first 15 min). Mark highs/lows — do NOT trade yet."
    elif swept_level and session_range < 1.5 and minutes_since_open <= 45:
        phase = "manipulation"
        desc = (
            f"Manipulation phase — price swept level at {swept_level:.2f}. "
            f"Watch for iFVG forming. If price displaces away, distribution may begin."
        )
    elif swept_level and current_price and session_range >= 1.5:
        # Price moved away from sweep
        if current_price > swept_level:
            phase = "distribution_bullish"
            desc = (
                f"Distribution (bullish) — price swept {swept_level:.2f} low, now delivering UP. "
                f"Longs valid. Look for iFVG re-entries on pullbacks."
            )
        else:
            phase = "distribution_bearish"
            desc = (
                f"Distribution (bearish) — price swept {swept_level:.2f} high, now delivering DOWN. "
                f"Shorts valid. Look for iFVG re-entries on retests."
            )
    elif minutes_since_open <= 45:
        phase = "manipulation"
        desc = (
            f"Manipulation phase — waiting for a key level to be swept. "
            f"Key levels: {', '.join(f'{l:.2f}' for l in key_levels[:4])}."
        )
    else:
        phase = "late_session"
        desc = "Past prime window. Only take A+ setups. Reduce size."

    return {
        "phase": phase,
        "phase_label": {
            "accumulation": "Accumulation",
            "manipulation": "Manipulation",
            "distribution_bullish": "Distribution ↑",
            "distribution_bearish": "Distribution ↓",
            "late_session": "Late Session",
            "pre_market": "Pre-Market",
        }.get(phase, phase.replace("_", " ").title()),
        "minutes_since_open": minutes_since_open,
        "swept_level": swept_level,
        "session_range": round(session_range, 2),
        "description": desc,
    }


# ---------------------------------------------------------------------------
# Combined advanced analysis
# ---------------------------------------------------------------------------

def get_advanced_signals(
    bars: list,
    session_levels: dict,
    equal_hl: Optional[dict] = None,
    bars_secondary: Optional[list] = None,  # e.g. SPY bars for SMT
    bias_direction: str = "neutral",
) -> dict:
    """Run all advanced ICT signals and return combined result."""
    swings = detect_swings(bars)
    mss = detect_mss_choch(bars, swings)
    sweeps = detect_liquidity_sweeps(bars, session_levels, equal_hl)
    po3 = detect_po3_phase(bars, session_levels)
    ipda = calc_ipda_levels(bars)

    # OTE: use bias direction to determine which leg to measure
    ote_direction = "bullish" if bias_direction in ("bullish", "bullish_lean") else "bearish"
    ote = calc_ote_zone(bars, swings, direction=ote_direction)

    # SMT only if secondary bars provided
    smt = {"detected": False, "type": None, "description": "No secondary instrument"}
    if bars_secondary:
        smt = detect_smt_divergence(bars, bars_secondary)

    # Current price
    current_price = None
    for b in reversed(bars):
        if b.get("close"):
            current_price = b["close"]
            break

    # Price in OTE?
    in_ote = False
    if ote and current_price:
        in_ote = ote["ote_bottom"] <= current_price <= ote["ote_top"]

    # Recent sweep (last 10 bars)?
    recent_sweep = sweeps[-1] if sweeps else None
    has_recent_sweep = bool(recent_sweep)

    # Setup quality boost from advanced signals
    advanced_score_bonus = 0
    if has_recent_sweep:
        advanced_score_bonus += 15
    if in_ote:
        advanced_score_bonus += 10
    if smt.get("detected"):
        advanced_score_bonus += 10
    if mss.get("last_structure") in ("bullish", "bearish"):
        advanced_score_bonus += 5

    return {
        "swing_points": swings,
        "mss_choch": mss,
        "liquidity_sweeps": sweeps,
        "ote_zone": ote,
        "in_ote": in_ote,
        "ipda_levels": ipda,
        "smt_divergence": smt,
        "po3_phase": po3,
        "advanced_score_bonus": advanced_score_bonus,
        "current_price": current_price,
        "has_recent_sweep": has_recent_sweep,
        "recent_sweep": recent_sweep,
        "summary": {
            "structure": mss.get("last_structure", "unknown"),
            "phase": po3.get("phase_label", "unknown"),
            "sweep_detected": has_recent_sweep,
            "in_ote": in_ote,
            "smt": smt.get("type"),
        }
    }


# ---------------------------------------------------------------------------
# Auto Trade Setup — entry / stop / target / sizing in instrument-native units
# ---------------------------------------------------------------------------

_INSTRUMENT_CONFIG = {
    # stop_buffer: points beyond sweep wick/iFVG boundary
    # min_stop_pts: absolute floor — a tighter stop isn't executable on fast futures
    # max_contracts: hard cap for this account size (Lucid 25k Pro, $1k daily limit)
    # max_contracts tuned for 50K DLL combine: $2k trailing drawdown, $1k daily loss limit
    "MNQ": {"multiplier": 1.0, "dollars_per_point": 2.0, "tick_size": 0.25,
            "stop_buffer": 25.0, "min_stop_pts": 50.0, "max_contracts": 2, "name": "Micro NQ"},
    "MES": {"multiplier": 1.0, "dollars_per_point": 5.0, "tick_size": 0.25,
            "stop_buffer": 15.0, "min_stop_pts": 30.0, "max_contracts": 1, "name": "Micro ES"},
    "MGC": {"multiplier": 1.0, "dollars_per_point": 10.0, "tick_size": 0.1,
            "stop_buffer": 6.0,  "min_stop_pts": 8.0,  "max_contracts": 1, "name": "Micro Gold"},
}


def calc_auto_trade_setup(
    bars: list,
    fvgs: list,
    advanced_signals: dict,
    dol: dict,
    instrument: str,
    account_status: dict,
    bias_direction: str = "neutral",
) -> dict:
    """
    Derive a complete trade setup from ICT signals and size it against the account.

    All levels returned in both proxy (QQQ/SPY) and instrument-native (MNQ/MES/MGC) units.
    """
    config = _INSTRUMENT_CONFIG.get(instrument.upper())
    if not config:
        return {"error": f"Unknown instrument: {instrument}"}

    multiplier    = config["multiplier"]
    usd_per_pt    = config["dollars_per_point"]
    tick          = config["tick_size"]
    stop_buffer   = config["stop_buffer"]
    min_stop_pts  = config["min_stop_pts"]
    max_contracts = config["max_contracts"]

    def to_ticks(v):
        return round(round(v / tick) * tick, 4)

    # Current price in proxy units
    current_price = advanced_signals.get("current_price")
    if not current_price:
        return {"error": "No current price data"}

    # ---- Direction ----
    sweeps = advanced_signals.get("liquidity_sweeps", [])
    fresh_sweeps = [s for s in sweeps if s.get("is_fresh", True)]
    recent_sweep = fresh_sweeps[-1] if fresh_sweeps else (sweeps[-1] if sweeps else None)
    direction = recent_sweep.get("direction", bias_direction) if recent_sweep else bias_direction

    if direction == "neutral":
        return {
            "setup": None,
            "direction": "neutral",
            "note": "No directional bias — wait for a sweep or MSS before sizing",
            "current_inst": to_ticks(current_price * multiplier),
            "current_price": current_price,
            "pts_to_entry": None,
        }

    # ---- Entry from iFVG (proxy price units) ----
    ifvgs = [f for f in fvgs if f.get("type") == "ifvg"]
    entry_fvg = None
    if direction == "bullish":
        aligned = [f for f in ifvgs if f.get("base_type") == "bullish_fvg"]
        if aligned:
            entry_fvg = min(aligned, key=lambda f: abs(f["mid"] - current_price))
            entry_proxy = entry_fvg["bottom"]
            entry_note = f"iFVG zone {entry_fvg['bottom']:.2f}–{entry_fvg['top']:.2f} (enter at bottom)"
    else:
        aligned = [f for f in ifvgs if f.get("base_type") == "bearish_fvg"]
        if aligned:
            entry_fvg = min(aligned, key=lambda f: abs(f["mid"] - current_price))
            entry_proxy = entry_fvg["top"]
            entry_note = f"iFVG zone {entry_fvg['bottom']:.2f}–{entry_fvg['top']:.2f} (enter at top)"

    if entry_fvg is None:
        ote = advanced_signals.get("ote_zone")
        if ote:
            entry_proxy = ote["ote_top"] if direction == "bullish" else ote["ote_bottom"]
            entry_note = f"OTE zone entry ({entry_proxy:.2f}) — no iFVG available"
        else:
            entry_proxy = current_price
            entry_note = "Using current price — no iFVG or OTE identified yet"

    # ---- Stop placement ----
    # LONG:  stop must be strictly BELOW entry — use min(sweep_wick_low, iFVG_bottom) - buffer
    # SHORT: stop must be strictly ABOVE entry — use max(sweep_wick_high, iFVG_top) + buffer
    if direction == "bullish":
        candidates = []
        if recent_sweep:
            w = recent_sweep.get("wick_low") or recent_sweep.get("level")
            if w is not None:
                candidates.append(w)
        if entry_fvg:
            candidates.append(entry_fvg["bottom"])
        raw_stop = min(candidates) if candidates else entry_proxy
        stop_proxy = round(raw_stop - stop_buffer, 2)
        # Safety: must be below entry
        if stop_proxy >= entry_proxy:
            stop_proxy = round(entry_proxy - stop_buffer, 2)
    else:
        candidates = []
        if recent_sweep:
            w = recent_sweep.get("wick_high") or recent_sweep.get("level")
            if w is not None:
                candidates.append(w)
        if entry_fvg:
            candidates.append(entry_fvg["top"])
        raw_stop = max(candidates) if candidates else entry_proxy
        stop_proxy = round(raw_stop + stop_buffer, 2)
        # Safety: must be above entry
        if stop_proxy <= entry_proxy:
            stop_proxy = round(entry_proxy + stop_buffer, 2)

    stop_dist_proxy = round(abs(entry_proxy - stop_proxy), 4)
    # Enforce minimum stop distance — a tighter stop isn't executable on fast futures
    if stop_dist_proxy < min_stop_pts:
        stop_dist_proxy = min_stop_pts
        if direction == "bullish":
            stop_proxy = round(entry_proxy - min_stop_pts, 2)
        else:
            stop_proxy = round(entry_proxy + min_stop_pts, 2)

    # ---- Target from DOL (proxy price units) ----
    dol_target = dol.get("target") if dol else None
    if dol_target and abs(dol_target - entry_proxy) > stop_dist_proxy:
        target_proxy = dol_target
        target_note = dol.get("reason", "Draw on liquidity")
    else:
        target_proxy = round(
            entry_proxy + 2.5 * stop_dist_proxy if direction == "bullish"
            else entry_proxy - 2.5 * stop_dist_proxy,
            2
        )
        target_note = "2.5R fallback target (no DOL identified)"

    reward_dist_proxy = round(abs(target_proxy - entry_proxy), 4)
    rr_ratio = round(reward_dist_proxy / stop_dist_proxy, 2) if stop_dist_proxy > 0 else 0

    # ---- Convert to instrument-native points ----
    entry_inst  = to_ticks(entry_proxy  * multiplier)
    stop_inst   = to_ticks(stop_proxy   * multiplier)
    target_inst = to_ticks(target_proxy * multiplier)
    stop_dist_inst   = round(stop_dist_proxy   * multiplier, 2)
    reward_dist_inst = round(reward_dist_proxy  * multiplier, 2)

    if direction == "bullish":
        be_trigger_inst  = to_ticks(entry_inst + stop_dist_inst)
    else:
        be_trigger_inst  = to_ticks(entry_inst - stop_dist_inst)

    # ---- Position sizing ----
    daily_risk_remaining = account_status.get("daily_risk_remaining", 0)
    if daily_risk_remaining <= 0:
        contracts, risk_amount = 0, 0.0
        size_note = "No daily risk remaining — stop trading today"
    else:
        # Risk 10% of remaining daily limit per trade, hard cap at $150
        # This leaves room for 5-8 trade attempts before hitting the daily loss limit
        budget = min(daily_risk_remaining * 0.10, 150.0)
        risk_per_contract = stop_dist_inst * usd_per_pt
        raw_contracts = int(budget / risk_per_contract) if risk_per_contract > 0 else 1
        contracts = max(1, min(raw_contracts, max_contracts))
        risk_amount = round(contracts * risk_per_contract, 2)
        size_note = f"{contracts} {instrument.upper()} · ${risk_amount:.0f} risk · {stop_dist_inst:.0f} pt stop"

    # ---- TP grid ----
    tp_levels = {}
    for r_val, label in [(1.5, "1.5R"), (2.0, "2R"), (2.5, "2.5R"), (3.0, "3R")]:
        tp_pts = round(stop_dist_inst * r_val, 2)
        if direction == "bullish":
            tp_price_inst  = to_ticks(entry_inst + tp_pts)
            tp_price_proxy = round(entry_proxy + stop_dist_proxy * r_val, 2)
        else:
            tp_price_inst  = to_ticks(entry_inst - tp_pts)
            tp_price_proxy = round(entry_proxy - stop_dist_proxy * r_val, 2)
        tp_levels[label] = {
            "pts": tp_pts,
            "price_inst": tp_price_inst,
            "price_proxy": tp_price_proxy,
            "gain_per_contract": round(tp_pts * usd_per_pt, 2),
            "total_gain": round(tp_pts * usd_per_pt * max(contracts, 1), 2),
        }

    current_inst = to_ticks(current_price * multiplier)
    pts_to_entry = round(entry_inst - current_inst, 2)  # + = above current, - = below

    return {
        "direction": direction,
        "instrument": instrument.upper(),
        "instrument_name": config["name"],
        "usd_per_point": usd_per_pt,
        "multiplier": multiplier,
        # Proxy prices (QQQ / SPY / GC=F)
        "entry_proxy": round(entry_proxy, 2),
        "stop_proxy": round(stop_proxy, 2),
        "target_proxy": round(target_proxy, 2),
        "stop_dist_proxy": round(stop_dist_proxy, 2),
        # Instrument-native levels
        "current_inst": current_inst,
        "pts_to_entry": pts_to_entry,
        "entry_inst": entry_inst,
        "stop_inst": stop_inst,
        "target_inst": target_inst,
        "stop_dist_inst": stop_dist_inst,
        "target_dist_inst": reward_dist_inst,
        "breakeven_trigger_inst": be_trigger_inst,
        # Risk & sizing
        "rr_ratio": rr_ratio,
        "contracts": contracts,
        "risk_amount": risk_amount,
        "size_note": size_note,
        # TP levels
        "tp_levels": tp_levels,
        # Context
        "entry_note": entry_note,
        "target_note": target_note,
        "sweep_detected": bool(recent_sweep),
        "fvg_zone": {"top": entry_fvg["top"], "bottom": entry_fvg["bottom"]} if entry_fvg else None,
        "trade_note": (
            f"{direction.upper()} {instrument.upper()} · "
            f"Entry {entry_inst} · SL {stop_inst} · TP {target_inst} · "
            f"{contracts} contract{'s' if contracts != 1 else ''} · "
            f"${risk_amount:.0f} risk · {rr_ratio:.1f}R"
        ),
    }
