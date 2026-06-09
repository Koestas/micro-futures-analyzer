"""
Scalp + ICT strategy backtest on real ProjectX historical bars.

Scalp: 1m momentum burst (3 consec bars) + VWAP + volume surge + ADX
ICT:   5m bar analysis with full scoring engine (same as live bot)

Walks bar-by-bar, simulates entries, tracks outcomes.
Results show win rate, avg gain/loss, daily P&L projection toward $600 target.
"""

from fastapi import APIRouter
from datetime import datetime, timedelta, timezone
import pytz

import providers.projectx as px
from routes.backtest import _bar_dt, _calc_atr, _calc_rsi, _calc_adx, _calc_vwap_at, _calc_sma
from engines.ict import get_ict_analysis, get_htf_bias
from engines.ict_signals import _INSTRUMENT_CONFIG

router = APIRouter(prefix="/api/backtest/scalp", tags=["scalp_backtest"])
NY_TZ = pytz.timezone("America/New_York")


# ── helpers ──────────────────────────────────────────────────────────────────

def _sort_asc(bars):
    if bars and bars[0]["time"] > bars[-1]["time"]:
        return list(reversed(bars))
    return bars


def _to_dt(b):
    ts = b["time"].replace("Z", "+00:00")
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(NY_TZ)


def _calc_avg_vol(bars, period=20):
    vols = [b.get("volume", 0) for b in bars]
    if len(vols) < period:
        return sum(vols) / max(len(vols), 1)
    return sum(vols[-period:]) / period


# ── scalp sim ────────────────────────────────────────────────────────────────

def _sim_scalp(bars_1m: list, instrument: str) -> dict:
    """
    Walk 1m bars, fire scalp entries when criteria trigger,
    simulate bracket exit (TP or SL), track stats.
    """
    config    = _INSTRUMENT_CONFIG.get(instrument, _INSTRUMENT_CONFIG["MNQ"])
    usd_pt    = config["dollars_per_point"]
    tick      = config["tick_size"]
    stop_tks  = 8 if instrument != "MGC" else 6
    tp_tks    = stop_tks * 2
    stop_pts  = stop_tks * tick
    tp_pts    = tp_tks   * tick
    usd_tp    = tp_pts * usd_pt
    # contracts to hit $50 target
    contracts = max(1, int(50 / usd_tp) + 1)
    usd_win   = usd_tp * contracts
    usd_loss  = stop_pts * usd_pt * contracts
    max_hold  = 5   # bars before force-close

    trades        = []
    last_entry_i  = -10  # cooldown: 10 min = 10 bars after last entry

    # Build 1-hour 5m bars inline for VWAP (use 1m bars grouped)
    # For simplicity, calculate rolling VWAP from 1m bars directly

    for i in range(20, len(bars_1m) - max_hold - 1):
        if i - last_entry_i < 3:
            continue

        ctx  = bars_1m[max(0, i-20):i+1]
        last = bars_1m[i]
        dt   = _to_dt(last)
        mins = dt.hour * 60 + dt.minute

        # Only during market hours (skip 4-6 PM ET)
        if 16 * 60 <= mins < 18 * 60:
            continue

        # ── Momentum: 4 consecutive same-direction 1m bars ──────────────
        last4 = bars_1m[i-3:i+1]
        bull  = all(b["close"] > b["open"] for b in last4)
        bear  = all(b["close"] < b["open"] for b in last4)
        if not bull and not bear:
            continue
        direction = "bullish" if bull else "bearish"

        # ── Each bar has real body ≥ 0.05% of price ──────────────────────
        price    = last["close"]
        min_body = price * 0.0005
        if any(abs(b["close"] - b["open"]) < min_body for b in last4):
            continue

        # ── Volume surge: last bar 1.5× average ──────────────────────────
        avg_vol  = _calc_avg_vol(bars_1m[max(0,i-20):i])
        last_vol = last.get("volume", 0)
        if avg_vol > 0 and last_vol < avg_vol * 1.5:
            continue

        # ── ADX > 18 ──────────────────────────────────────────────────────
        adx = _calc_adx(ctx)
        if adx < 18:
            continue

        # ── RSI in momentum zone ──────────────────────────────────────────
        rsi = _calc_rsi(ctx)
        if direction == "bullish" and (rsi > 80 or rsi < 40):
            continue
        if direction == "bearish" and (rsi < 20 or rsi > 60):
            continue

        # ── VWAP alignment ────────────────────────────────────────────────
        day_bars = [b for b in bars_1m if _to_dt(b).date() == dt.date()]
        vwap = _calc_vwap_at(day_bars, dt) if day_bars else None
        if vwap:
            if direction == "bullish" and price < vwap * 0.997:
                continue
            if direction == "bearish" and price > vwap * 1.003:
                continue

        # ── Simulate bracket exit ──
        entry = price
        sl    = entry - stop_pts if direction == "bullish" else entry + stop_pts
        tp    = entry + tp_pts   if direction == "bullish" else entry - tp_pts

        outcome = "timeout"
        exit_price = None
        for j in range(1, max_hold + 1):
            if i + j >= len(bars_1m):
                break
            fut = bars_1m[i + j]
            if direction == "bullish":
                if fut["low"]  <= sl:
                    outcome, exit_price = "loss", sl;  break
                if fut["high"] >= tp:
                    outcome, exit_price = "win",  tp;  break
            else:
                if fut["high"] >= sl:
                    outcome, exit_price = "loss", sl;  break
                if fut["low"]  <= tp:
                    outcome, exit_price = "win",  tp;  break

        if exit_price is None:
            exit_price = bars_1m[min(i + max_hold, len(bars_1m)-1)]["close"]

        pnl = (
            (exit_price - entry if direction == "bullish" else entry - exit_price)
            * usd_pt * contracts
        )
        pnl = round(pnl, 2)

        trades.append({
            "i":         i,
            "date":      dt.strftime("%Y-%m-%d"),
            "time_et":   dt.strftime("%H:%M"),
            "direction": direction,
            "entry":     round(entry, 2),
            "exit":      round(exit_price, 2),
            "outcome":   outcome,
            "pnl":       pnl,
            "adx":       round(adx, 1),
            "rsi":       round(rsi, 1),
        })
        last_entry_i = i

    return {
        "instrument": instrument,
        "contracts":  contracts,
        "usd_win":    round(usd_win, 2),
        "usd_loss":   round(usd_loss, 2),
        "stop_pts":   stop_pts,
        "tp_pts":     tp_pts,
        "trades":     trades,
    }


# ── Dakota 3-Bar Reversal sim ────────────────────────────────────────────────

def _sim_3bar_reversal(bars: list, instrument: str, interval_mins: int = 5) -> dict:
    """
    Coach Dakota's 3-bar reversal:
      3 consecutive bars in one direction →
      reversal bar displaces strongly opposite (body > 1.5× avg of prior 3)
      Enter at close of reversal bar.
      Stop: beyond the swing extreme of bars 2-3 + small buffer.
      Target: 2R (2× the stop distance).
    Works on 5m and 15m.
    """
    config   = _INSTRUMENT_CONFIG.get(instrument, _INSTRUMENT_CONFIG["MNQ"])
    usd_pt   = config["dollars_per_point"]
    tick     = config["tick_size"]
    buf      = config["stop_buffer"]
    trades   = []
    cooldown = max(6, int(60 / interval_mins))   # 1-hour cooldown
    last_entry_i = -cooldown
    max_hold     = max(6, int(90 / interval_mins))  # 90-min max hold

    for i in range(8, len(bars) - max_hold - 1):
        if i - last_entry_i < cooldown:
            continue

        dt   = _to_dt(bars[i])
        mins = dt.hour * 60 + dt.minute
        # Skip market close window
        if 16 * 60 <= mins < 18 * 60:
            continue

        b1, b2, b3, rev = bars[i-3], bars[i-2], bars[i-1], bars[i]

        def body(b):
            return abs(b["close"] - b["open"])

        avg_prior_body = (body(b1) + body(b2) + body(b3)) / 3
        if avg_prior_body == 0:
            continue

        rev_body = body(rev)
        # Reversal must be a displacement bar (1.5× larger than the prior trend)
        if rev_body < avg_prior_body * 1.5:
            continue

        b1_bear = b1["close"] < b1["open"]
        b2_bear = b2["close"] < b2["open"]
        b3_bear = b3["close"] < b3["open"]
        rev_bull = rev["close"] > rev["open"]

        b1_bull = b1["close"] > b1["open"]
        b2_bull = b2["close"] > b2["open"]
        b3_bull = b3["close"] > b3["open"]
        rev_bear = rev["close"] < rev["open"]

        if b1_bear and b2_bear and b3_bear and rev_bull:
            direction = "bullish"
            entry     = rev["close"]
            swing_low = min(b2["low"], b3["low"], rev["low"])
            stop      = swing_low - buf
            stop_dist = max(entry - stop, config["min_stop_pts"])
            stop      = entry - stop_dist
            tp        = entry + stop_dist * 2
            side      = 0
        elif b1_bull and b2_bull and b3_bull and rev_bear:
            direction = "bearish"
            entry     = rev["close"]
            swing_hi  = max(b2["high"], b3["high"], rev["high"])
            stop      = swing_hi + buf
            stop_dist = max(stop - entry, config["min_stop_pts"])
            stop      = entry + stop_dist
            tp        = entry - stop_dist * 2
            side      = 1
        else:
            continue

        # ── VWAP filter ───────────────────────────────────────────────────
        day_bars = [b for b in bars if _to_dt(b).date() == dt.date()]
        vwap = _calc_vwap_at(day_bars, dt) if day_bars else None
        if vwap:
            if direction == "bullish" and entry < vwap * 0.995:
                continue
            if direction == "bearish" and entry > vwap * 1.005:
                continue

        contracts = min(5, config["max_contracts"])

        # ── Simulate exit ─────────────────────────────────────────────────
        outcome    = "timeout"
        exit_price = None
        for j in range(1, max_hold + 1):
            if i + j >= len(bars):
                break
            fut = bars[i + j]
            if direction == "bullish":
                if fut["low"]  <= stop: outcome, exit_price = "loss", stop; break
                if fut["high"] >= tp:   outcome, exit_price = "win",  tp;   break
            else:
                if fut["high"] >= stop: outcome, exit_price = "loss", stop; break
                if fut["low"]  <= tp:   outcome, exit_price = "win",  tp;   break

        if exit_price is None:
            exit_price = bars[min(i + max_hold, len(bars)-1)]["close"]

        pnl = (
            (exit_price - entry if direction == "bullish" else entry - exit_price)
            * usd_pt * contracts
        )
        trades.append({
            "date":      dt.strftime("%Y-%m-%d"),
            "time_et":   dt.strftime("%H:%M"),
            "direction": direction,
            "entry":     round(entry, 2),
            "exit":      round(exit_price, 2),
            "outcome":   outcome,
            "pnl":       round(pnl, 2),
            "stop_dist": round(stop_dist, 2),
            "rev_body":  round(rev_body, 2),
            "displacement": round(rev_body / avg_prior_body, 2),
        })
        last_entry_i = i

    return {"instrument": instrument, "interval": f"{interval_mins}m", "trades": trades}


# ── ICT 5m sim ────────────────────────────────────────────────────────────────

def _sim_ict(bars_5m: list, instrument: str) -> dict:
    """
    Simulate ICT swing setups on 5m bars.
    Uses live scoring engine — same logic as auto_trader.
    """
    config  = _INSTRUMENT_CONFIG.get(instrument, _INSTRUMENT_CONFIG["MNQ"])
    usd_pt  = config["dollars_per_point"]
    tick    = config["tick_size"]
    trades  = []
    cooldown = 12   # 1hr (12 × 5m) between ICT trades

    last_entry_i = -cooldown

    for i in range(50, len(bars_5m) - 13):
        if i - last_entry_i < cooldown:
            continue

        ctx   = bars_5m[max(0, i-150):i+1]
        last  = bars_5m[i]
        price = last["close"]
        dt    = _to_dt(last)
        mins  = dt.hour * 60 + dt.minute

        # Only during active sessions
        in_session = (
            (570 <= mins <= 690) or   # NY AM 9:30-11:30
            (810 <= mins <= 950) or   # NY PM 1:30-3:50
            (180 <= mins <= 300) or   # London 3-5 AM
            (mins >= 1080 or mins <= 60)  # Asia/Post-Open
        )
        if not in_session:
            continue

        try:
            analysis = get_ict_analysis(ctx, current_price=price)
        except Exception:
            continue

        long_sc  = analysis.get("long_setup",  {}).get("score", 0) or 0
        short_sc = analysis.get("short_setup", {}).get("score", 0) or 0

        if max(long_sc, short_sc) < 58:
            continue

        direction = "bullish" if long_sc >= short_sc else "bearish"
        score     = long_sc if direction == "bullish" else short_sc

        # ADX + RSI filter
        adx = _calc_adx(ctx[-60:])
        rsi = _calc_rsi(ctx[-60:])
        if adx < 10:
            continue
        if direction == "bullish" and rsi > 80:
            continue
        if direction == "bearish" and rsi < 20:
            continue

        # Stop/target
        atr       = _calc_atr(ctx[-20:])
        stop_dist = max(atr * 1.5, config["min_stop_pts"])
        stop_dist = min(stop_dist, {"MNQ": 120, "MES": 60, "MGC": 20}.get(instrument, 120))
        tp_dist   = stop_dist * 2
        contracts = min(5, config["max_contracts"])

        if direction == "bullish":
            sl = price - stop_dist;  tp = price + tp_dist
        else:
            sl = price + stop_dist;  tp = price - tp_dist

        # Simulate exit (walk next 12 bars = 1hr max hold)
        outcome = "timeout"
        exit_price = None
        for j in range(1, 13):
            if i + j >= len(bars_5m):
                break
            fut = bars_5m[i + j]
            if direction == "bullish":
                if fut["low"]  <= sl: outcome, exit_price = "loss", sl;  break
                if fut["high"] >= tp: outcome, exit_price = "win",  tp;  break
            else:
                if fut["high"] >= sl: outcome, exit_price = "loss", sl;  break
                if fut["low"]  <= tp: outcome, exit_price = "win",  tp;  break

        if exit_price is None:
            exit_price = bars_5m[min(i+12, len(bars_5m)-1)]["close"]

        pnl = (
            (exit_price - price if direction == "bullish" else price - exit_price)
            * usd_pt * contracts
        )
        pnl = round(pnl, 2)

        trades.append({
            "date":      dt.strftime("%Y-%m-%d"),
            "time_et":   dt.strftime("%H:%M"),
            "direction": direction,
            "score":     score,
            "entry":     round(price, 2),
            "exit":      round(exit_price, 2),
            "outcome":   outcome,
            "pnl":       pnl,
            "adx":       round(adx, 1),
        })
        last_entry_i = i

    return {"instrument": instrument, "contracts": contracts, "trades": trades}


# ── Aggregate stats ───────────────────────────────────────────────────────────

def _stats(trades: list, label: str) -> dict:
    if not trades:
        return {"label": label, "total": 0}
    wins   = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    gross  = sum(t["pnl"] for t in trades)

    # By day
    by_day: dict = {}
    for t in trades:
        d = t["date"]
        by_day.setdefault(d, []).append(t["pnl"])
    daily_pnls = [sum(v) for v in by_day.values()]
    avg_daily  = sum(daily_pnls) / len(daily_pnls) if daily_pnls else 0
    days_profitable = sum(1 for d in daily_pnls if d > 0)

    avg_win  = sum(t["pnl"] for t in wins)   / len(wins)   if wins   else 0
    avg_loss = sum(t["pnl"] for t in losses) / len(losses) if losses else 0
    pf = abs(avg_win * len(wins)) / abs(avg_loss * len(losses)) if losses and avg_loss else 0

    # Drawdown
    cum, peak, max_dd = 0, 0, 0
    pnl_curve = []
    for t in trades:
        cum  += t["pnl"]
        peak  = max(peak, cum)
        max_dd = max(max_dd, peak - cum)
        pnl_curve.append({"date": t["date"], "time": t.get("time_et",""), "cum": round(cum, 2)})

    return {
        "label":           label,
        "total":           len(trades),
        "wins":            len(wins),
        "losses":          len(losses),
        "win_rate":        round(len(wins) / len(trades) * 100, 1),
        "gross_pnl":       round(gross, 2),
        "avg_daily_pnl":   round(avg_daily, 2),
        "days_profitable": days_profitable,
        "total_days":      len(by_day),
        "avg_win":         round(avg_win, 2),
        "avg_loss":        round(avg_loss, 2),
        "profit_factor":   round(pf, 2),
        "max_drawdown":    round(max_dd, 2),
        "pnl_curve":       pnl_curve,
        "daily_pnls":      [{"date": d, "pnl": round(sum(v), 2)} for d, v in sorted(by_day.items())],
        "sample_trades":   trades[:20],
    }


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.get("")
async def run_scalp_backtest(days: int = 14):
    """
    Run scalp + ICT backtest on real ProjectX 1m/5m historical bars.
    Returns per-strategy stats + combined daily P&L projection.
    """
    end   = datetime.now(timezone.utc)
    start = end - timedelta(days=days + 1)

    results = {}

    # ── MNQ scalp ──
    bars_1m_mnq = await px.get_bars("MNQ", interval="1m", limit=19000,
                                    start_time=start, end_time=end)
    bars_1m_mnq = _sort_asc(bars_1m_mnq)

    if bars_1m_mnq:
        raw = _sim_scalp(bars_1m_mnq, "MNQ")
        results["mnq_scalp"] = _stats(raw["trades"], "MNQ Scalp 1m")
        results["mnq_scalp"]["params"] = {
            "contracts": raw["contracts"], "stop_pts": raw["stop_pts"],
            "tp_pts": raw["tp_pts"], "usd_win": raw["usd_win"], "usd_loss": raw["usd_loss"],
        }

    # ── MGC scalp (Asia hours only) ──
    bars_1m_mgc = await px.get_bars("MGC", interval="1m", limit=19000,
                                    start_time=start, end_time=end)
    bars_1m_mgc = _sort_asc(bars_1m_mgc)

    if bars_1m_mgc:
        # Filter to Asia hours only (6 PM – 1 AM ET)
        asia_bars = [b for b in bars_1m_mgc if (
            _to_dt(b).hour >= 18 or _to_dt(b).hour <= 1
        )]
        raw = _sim_scalp(asia_bars, "MGC")
        results["mgc_scalp"] = _stats(raw["trades"], "MGC Scalp 1m (Asia)")
        results["mgc_scalp"]["params"] = {
            "contracts": raw["contracts"], "stop_pts": raw["stop_pts"],
            "tp_pts": raw["tp_pts"], "usd_win": raw["usd_win"], "usd_loss": raw["usd_loss"],
        }

    # ── MNQ ICT 5m swings ──
    bars_5m_mnq = await px.get_bars("MNQ", interval="5m", limit=5000,
                                    start_time=start, end_time=end)
    bars_5m_mnq = _sort_asc(bars_5m_mnq)
    if bars_5m_mnq:
        raw = _sim_ict(bars_5m_mnq, "MNQ")
        results["mnq_ict"] = _stats(raw["trades"], "MNQ ICT 5m Swings (simplified)")

    # ── Dakota 3-Bar Reversal — 5m ──
    if bars_5m_mnq:
        raw = _sim_3bar_reversal(bars_5m_mnq, "MNQ", interval_mins=5)
        results["mnq_3bar_5m"] = _stats(raw["trades"], "MNQ 3-Bar Reversal 5m")

    # ── Dakota 3-Bar Reversal — 15m ──
    bars_15m_mnq = await px.get_bars("MNQ", interval="15m", limit=2000,
                                     start_time=start, end_time=end)
    bars_15m_mnq = _sort_asc(bars_15m_mnq)
    if bars_15m_mnq:
        raw = _sim_3bar_reversal(bars_15m_mnq, "MNQ", interval_mins=15)
        results["mnq_3bar_15m"] = _stats(raw["trades"], "MNQ 3-Bar Reversal 15m")

    # ── Combined daily projection ──
    all_daily: dict = {}
    for key, r in results.items():
        for entry in r.get("daily_pnls", []):
            d = entry["date"]
            all_daily.setdefault(d, 0)
            all_daily[d] += entry["pnl"]

    daily_list = sorted(all_daily.items())
    combined_pnls = [p for _, p in daily_list]
    avg_combined  = sum(combined_pnls) / len(combined_pnls) if combined_pnls else 0
    days_over_600 = sum(1 for p in combined_pnls if p >= 600)
    days_over_400 = sum(1 for p in combined_pnls if p >= 400)

    return {
        "period_days":      days,
        "bars_fetched": {
            "mnq_1m": len(bars_1m_mnq) if bars_1m_mnq else 0,
            "mgc_1m": len(bars_1m_mgc) if bars_1m_mgc else 0,
            "mnq_5m": len(bars_5m_mnq) if bars_5m_mnq else 0,
        },
        "strategies":       results,
        "combined": {
            "avg_daily_pnl":   round(avg_combined, 2),
            "days_over_600":   days_over_600,
            "days_over_400":   days_over_400,
            "total_days":      len(daily_list),
            "daily":           [{"date": d, "pnl": round(p, 2)} for d, p in daily_list],
        },
    }
