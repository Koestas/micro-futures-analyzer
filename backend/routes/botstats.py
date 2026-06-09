"""Bot performance stats endpoint.
Aggregates ProjectX trade history + auto-trader internal log into
session breakdown, P&L curve, win rate, and drawdown metrics.
"""

from fastapi import APIRouter
from datetime import datetime, date, timedelta
import pytz

import providers.projectx as px
import engines.auto_trader as at

router = APIRouter(prefix="/api/bot/stats", tags=["botstats"])
NY_TZ = pytz.timezone("America/New_York")


def _session_for_time(dt: datetime) -> str:
    et = dt.astimezone(NY_TZ)
    m  = et.hour * 60 + et.minute
    if 1095 <= m or m <= 60:   return "Asia"          # 18:15–01:00
    if 60  <  m <= 180:        return "Asia-London"
    if 180 <  m <= 300:        return "London"
    if 300 <  m <= 570:        return "Pre-Market"
    if 570 <  m <= 690:        return "NY AM"
    if 690 <  m <= 810:        return "Midday"
    if 810 <  m <= 950:        return "NY PM"
    if 950 <  m <= 1095:       return "Post-Open"
    return "Unknown"


@router.get("")
async def stats(days: int = 30):
    trades = await px.get_trade_history(days_back=days)

    if not trades:
        return {
            "total_trades": 0, "wins": 0, "losses": 0, "win_rate": 0,
            "gross_pnl": 0, "total_fees": 0, "net_pnl": 0,
            "avg_win": 0, "avg_loss": 0, "profit_factor": 0,
            "max_drawdown": 0, "by_session": {}, "by_day": {},
            "pnl_curve": [], "trade_log": [],
        }

    # Build enriched trade list
    enriched = []
    for t in trades:
        ts_raw = t.get("creationTimestamp") or t.get("timestamp") or ""
        try:
            dt = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        except Exception:
            dt = datetime.now(pytz.UTC)

        pnl  = (t.get("profitAndLoss") or 0) - (t.get("fees") or 0)
        sess = _session_for_time(dt)
        side_val = t.get("side", 0)
        side_str = "Long" if side_val == 0 else "Short"
        sym  = t.get("contractId", "").split(".")[-2] if "." in t.get("contractId","") else ""

        enriched.append({
            "id":        t.get("id"),
            "symbol":    sym,
            "side":      side_str,
            "size":      t.get("size", 1),
            "price":     t.get("price"),
            "pnl":       round(pnl, 2),
            "fees":      round(t.get("fees") or 0, 2),
            "session":   sess,
            "date":      dt.astimezone(NY_TZ).strftime("%Y-%m-%d"),
            "time_et":   dt.astimezone(NY_TZ).strftime("%H:%M"),
            "timestamp": dt.isoformat(),
        })

    enriched.sort(key=lambda x: x["timestamp"])

    # Summary stats
    wins   = [t for t in enriched if t["pnl"] > 0]
    losses = [t for t in enriched if t["pnl"] < 0]
    gross  = sum(t["pnl"] for t in enriched)
    fees   = sum(t["fees"] for t in enriched)

    avg_win  = sum(t["pnl"] for t in wins)   / len(wins)   if wins   else 0
    avg_loss = sum(t["pnl"] for t in losses) / len(losses) if losses else 0
    pf = abs(avg_win * len(wins)) / abs(avg_loss * len(losses)) if losses and avg_loss != 0 else 0

    # Drawdown
    cum, peak, max_dd = 0, 0, 0
    for t in enriched:
        cum += t["pnl"]
        peak = max(peak, cum)
        max_dd = max(max_dd, peak - cum)

    # P&L curve (cumulative by trade)
    pnl_curve, cum = [], 0
    for t in enriched:
        cum += t["pnl"]
        pnl_curve.append({"date": t["date"], "time": t["time_et"], "cum_pnl": round(cum, 2), "trade_pnl": t["pnl"]})

    # By session
    by_session: dict = {}
    for t in enriched:
        s = t["session"]
        if s not in by_session:
            by_session[s] = {"trades": 0, "wins": 0, "pnl": 0}
        by_session[s]["trades"] += 1
        if t["pnl"] > 0:
            by_session[s]["wins"] += 1
        by_session[s]["pnl"] += t["pnl"]
    for s in by_session:
        n = by_session[s]["trades"]
        by_session[s]["win_rate"] = round(by_session[s]["wins"] / n * 100, 1) if n else 0
        by_session[s]["pnl"] = round(by_session[s]["pnl"], 2)

    # By day
    by_day: dict = {}
    for t in enriched:
        d = t["date"]
        if d not in by_day:
            by_day[d] = {"trades": 0, "pnl": 0}
        by_day[d]["trades"] += 1
        by_day[d]["pnl"] = round(by_day[d]["pnl"] + t["pnl"], 2)

    # Today
    today_str = str(date.today())
    today_trades = [t for t in enriched if t["date"] == today_str]
    today_pnl = sum(t["pnl"] for t in today_trades)

    return {
        "period_days":    days,
        "total_trades":   len(enriched),
        "wins":           len(wins),
        "losses":         len(losses),
        "win_rate":       round(len(wins) / len(enriched) * 100, 1) if enriched else 0,
        "gross_pnl":      round(gross, 2),
        "total_fees":     round(fees, 2),
        "net_pnl":        round(gross, 2),
        "avg_win":        round(avg_win, 2),
        "avg_loss":       round(avg_loss, 2),
        "profit_factor":  round(pf, 2),
        "max_drawdown":   round(max_dd, 2),
        "today_trades":   len(today_trades),
        "today_pnl":      round(today_pnl, 2),
        "trail_mode":     at._trail_mode,
        "trail_floor":    at._trail_floor,
        "by_session":     by_session,
        "by_day":         dict(sorted(by_day.items())[-30:]),
        "pnl_curve":      pnl_curve,
        "recent_trades":  enriched[-50:],
    }
