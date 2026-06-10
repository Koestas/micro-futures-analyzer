"""Self-learning engine — logs every signal evaluation (traded or skipped),
tracks ghost trade outcomes for missed setups, and records detailed trade
outcomes for completed trades.

Tables
------
signal_evaluations  — one row per ICT/3-bar evaluation regardless of outcome
trade_outcomes      — one row per completed trade with MAE/MFE and user rating

The ghost tracker runs as an async background task.  Every 5 minutes it checks
pending ghost trades and, once 90 minutes have elapsed since evaluation, marks
them resolved by replaying what price actually did.

Analytics
---------
win_rate_by_session()    — per-session win%, avg P&L, sample count
threshold_suggestions()  — per-session ADX/score correlations → suggested floors
"""

import asyncio
import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Optional
import pytz

logger = logging.getLogger(__name__)
NY_TZ = pytz.timezone("America/New_York")

_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "terminal.db")

# ─── Schema ──────────────────────────────────────────────────────────────────

_DDL = """
CREATE TABLE IF NOT EXISTS signal_evaluations (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ts                  TEXT NOT NULL,          -- ISO ET timestamp
    instrument          TEXT NOT NULL,
    session             TEXT NOT NULL,
    direction           TEXT NOT NULL,          -- bullish / bearish
    score               INTEGER NOT NULL,
    min_score_required  INTEGER,
    traded              INTEGER NOT NULL,        -- 1 = trade placed, 0 = skipped
    skip_reason         TEXT,                   -- score_low / news / vol_regime / halted / correlation / active_trade

    -- Price context
    price               REAL,
    atr                 REAL,
    adx                 REAL,
    rsi                 REAL,
    vwap                REAL,
    price_vs_vwap       TEXT,                   -- above / below

    -- ICT signal components (all present at evaluation)
    htf_bias            TEXT,
    sweep_detected      INTEGER,
    sweep_quality       TEXT,
    ifvg_present        INTEGER,
    fvg_present         INTEGER,
    ob_present          INTEGER,
    mss_detected        INTEGER,
    displacement        REAL,

    -- Ghost trade parameters (set for skipped evaluations)
    ghost_entry         REAL,
    ghost_sl            REAL,
    ghost_tp            REAL,
    ghost_stop_ticks    INTEGER,
    ghost_outcome       TEXT DEFAULT 'pending', -- pending / tp_hit / sl_hit / neither
    ghost_pnl           REAL,
    ghost_max_adverse   REAL,                   -- MAE: worst price vs entry
    ghost_max_favorable REAL,                   -- MFE: best price vs entry
    ghost_resolved_at   TEXT,
    ghost_mins_to_res   INTEGER,

    -- Link to trade_outcomes if actually traded
    trade_ref           TEXT
);

CREATE TABLE IF NOT EXISTS trade_outcomes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    eval_id             INTEGER REFERENCES signal_evaluations(id),
    trade_ref           TEXT UNIQUE NOT NULL,   -- auto_trader internal ID

    instrument          TEXT NOT NULL,
    session             TEXT NOT NULL,
    direction           TEXT NOT NULL,
    score               INTEGER,
    contracts           INTEGER,

    entry_price         REAL,
    exit_price          REAL,
    outcome             TEXT,                   -- tp_hit / sl_hit / manual / partial
    pnl                 REAL,
    duration_mins       INTEGER,

    max_adverse_excursion   REAL,              -- worst price seen during trade
    max_favorable_excursion REAL,              -- best price seen during trade

    -- Signal snapshot at entry
    adx_at_entry        REAL,
    rsi_at_entry        REAL,
    atr_at_entry        REAL,
    vwap_position       TEXT,
    htf_bias            TEXT,

    -- Telegram user feedback
    user_rating         INTEGER,               -- -1 bad, 0 neutral, 1 good
    user_notes          TEXT,

    opened_at           TEXT,
    closed_at           TEXT
);

CREATE INDEX IF NOT EXISTS idx_se_ts          ON signal_evaluations(ts);
CREATE INDEX IF NOT EXISTS idx_se_instrument  ON signal_evaluations(instrument);
CREATE INDEX IF NOT EXISTS idx_se_session     ON signal_evaluations(session);
CREATE INDEX IF NOT EXISTS idx_se_traded      ON signal_evaluations(traded);
CREATE INDEX IF NOT EXISTS idx_to_trade_ref   ON trade_outcomes(trade_ref);
"""


@contextmanager
def _db():
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with _db() as conn:
        conn.executescript(_DDL)
    logger.info("Learning DB schema ready")


# ─── Logging helpers ──────────────────────────────────────────────────────────

def log_evaluation(
    *,
    instrument: str,
    session: str,
    direction: str,
    score: int,
    min_score_required: int,
    traded: bool,
    skip_reason: Optional[str] = None,
    price: Optional[float] = None,
    atr: Optional[float] = None,
    adx: Optional[float] = None,
    rsi: Optional[float] = None,
    vwap: Optional[float] = None,
    htf_bias: Optional[str] = None,
    sweep_detected: bool = False,
    sweep_quality: Optional[str] = None,
    ifvg_present: bool = False,
    fvg_present: bool = False,
    ob_present: bool = False,
    mss_detected: bool = False,
    displacement: Optional[float] = None,
    ghost_entry: Optional[float] = None,
    ghost_sl: Optional[float] = None,
    ghost_tp: Optional[float] = None,
    ghost_stop_ticks: Optional[int] = None,
    trade_ref: Optional[str] = None,
) -> int:
    """Insert one evaluation row. Returns the new row id."""
    now_et = datetime.now(NY_TZ).isoformat()
    price_vs_vwap = None
    if price and vwap:
        price_vs_vwap = "above" if price > vwap else "below"

    with _db() as conn:
        cur = conn.execute("""
            INSERT INTO signal_evaluations (
                ts, instrument, session, direction, score, min_score_required,
                traded, skip_reason,
                price, atr, adx, rsi, vwap, price_vs_vwap,
                htf_bias, sweep_detected, sweep_quality,
                ifvg_present, fvg_present, ob_present, mss_detected, displacement,
                ghost_entry, ghost_sl, ghost_tp, ghost_stop_ticks,
                ghost_outcome, trade_ref
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            now_et, instrument, session, direction, score, min_score_required,
            1 if traded else 0, skip_reason,
            price, atr, adx, rsi, vwap, price_vs_vwap,
            htf_bias, 1 if sweep_detected else 0, sweep_quality,
            1 if ifvg_present else 0, 1 if fvg_present else 0,
            1 if ob_present else 0, 1 if mss_detected else 0, displacement,
            ghost_entry, ghost_sl, ghost_tp, ghost_stop_ticks,
            "pending" if not traded and ghost_entry else None,
            trade_ref,
        ))
        return cur.lastrowid


def log_outcome(
    *,
    eval_id: Optional[int],
    trade_ref: str,
    instrument: str,
    session: str,
    direction: str,
    score: int,
    contracts: int,
    entry_price: float,
    exit_price: float,
    outcome: str,
    pnl: float,
    duration_mins: int,
    max_adverse_excursion: float = 0.0,
    max_favorable_excursion: float = 0.0,
    adx_at_entry: Optional[float] = None,
    rsi_at_entry: Optional[float] = None,
    atr_at_entry: Optional[float] = None,
    vwap_position: Optional[str] = None,
    htf_bias: Optional[str] = None,
    opened_at: Optional[str] = None,
    closed_at: Optional[str] = None,
):
    closed = closed_at or datetime.now(NY_TZ).isoformat()
    with _db() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO trade_outcomes (
                eval_id, trade_ref, instrument, session, direction, score,
                contracts, entry_price, exit_price, outcome, pnl, duration_mins,
                max_adverse_excursion, max_favorable_excursion,
                adx_at_entry, rsi_at_entry, atr_at_entry, vwap_position, htf_bias,
                opened_at, closed_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            eval_id, trade_ref, instrument, session, direction, score,
            contracts, entry_price, exit_price, outcome, pnl, duration_mins,
            max_adverse_excursion, max_favorable_excursion,
            adx_at_entry, rsi_at_entry, atr_at_entry, vwap_position, htf_bias,
            opened_at, closed,
        ))


def set_user_rating(trade_ref: str, rating: int, notes: str = ""):
    with _db() as conn:
        conn.execute(
            "UPDATE trade_outcomes SET user_rating=?, user_notes=? WHERE trade_ref=?",
            (rating, notes, trade_ref)
        )


# ─── Ghost trade resolver ─────────────────────────────────────────────────────

_GHOST_WINDOW_MINS = 90   # how long to track a missed setup
_GHOST_CHECK_SECS  = 300  # how often the background task wakes up (5 min)


async def _resolve_ghost(row: sqlite3.Row):
    """Fetch price history and determine if the ghost TP or SL was hit first."""
    try:
        import yfinance as yf
        from engines.ict_signals import _INSTRUMENT_CONFIG

        SYMBOL_MAP = {"MNQ": "NQ=F", "MES": "ES=F", "MGC": "GC=F"}
        yf_sym = SYMBOL_MAP.get(row["instrument"], row["instrument"])
        cfg    = _INSTRUMENT_CONFIG.get(row["instrument"], {})
        side   = 0 if row["direction"] == "bullish" else 1  # 0=long 1=short

        entry  = row["ghost_entry"]
        sl     = row["ghost_sl"]
        tp     = row["ghost_tp"]
        eval_ts = datetime.fromisoformat(row["ts"])

        # Download 1-minute bars from evaluation time
        now = datetime.now(NY_TZ)
        df = yf.download(
            yf_sym, start=eval_ts.astimezone(pytz.UTC),
            end=min(now, eval_ts + timedelta(minutes=_GHOST_WINDOW_MINS + 5)),
            interval="1m", progress=False, auto_adjust=True
        )
        if df is None or df.empty:
            return

        highs  = df["High"].values.tolist()
        lows   = df["Low"].values.tolist()

        outcome      = "neither"
        pnl          = 0.0
        mae          = 0.0
        mfe          = 0.0
        res_mins     = _GHOST_WINDOW_MINS
        dpp          = cfg.get("dollars_per_point", 2.0)

        for i, (h, l) in enumerate(zip(highs, lows)):
            if side == 0:  # long
                adverse   = entry - l
                favorable = h - entry
                hit_sl = l <= sl
                hit_tp = h >= tp
            else:           # short
                adverse   = h - entry
                favorable = entry - l
                hit_sl = h >= sl
                hit_tp = l <= tp

            mae = max(mae, adverse)
            mfe = max(mfe, favorable)

            if hit_tp and not hit_sl:
                outcome  = "tp_hit"
                pnl      = (tp - entry if side == 0 else entry - tp) * dpp
                res_mins = i + 1
                break
            elif hit_sl and not hit_tp:
                outcome  = "sl_hit"
                pnl      = (sl - entry if side == 0 else entry - sl) * dpp
                res_mins = i + 1
                break
            elif hit_tp and hit_sl:
                # Both in same bar — assume sl hit first (conservative)
                outcome  = "sl_hit"
                pnl      = (sl - entry if side == 0 else entry - sl) * dpp
                res_mins = i + 1
                break

        resolved_at = datetime.now(NY_TZ).isoformat()
        with _db() as conn:
            conn.execute("""
                UPDATE signal_evaluations SET
                    ghost_outcome=?, ghost_pnl=?,
                    ghost_max_adverse=?, ghost_max_favorable=?,
                    ghost_resolved_at=?, ghost_mins_to_res=?
                WHERE id=?
            """, (outcome, round(pnl, 2), round(mae, 4), round(mfe, 4),
                  resolved_at, res_mins, row["id"]))

    except Exception as e:
        logger.warning(f"Ghost resolver error (id={row['id']}): {e}")


async def ghost_tracker_loop():
    """Background task — checks pending ghost evaluations every 5 minutes."""
    await asyncio.sleep(30)   # let the bot settle on startup
    while True:
        try:
            cutoff = (datetime.now(NY_TZ) - timedelta(minutes=_GHOST_WINDOW_MINS)).isoformat()
            with _db() as conn:
                rows = conn.execute("""
                    SELECT * FROM signal_evaluations
                    WHERE traded=0 AND ghost_outcome='pending' AND ts <= ?
                    LIMIT 20
                """, (cutoff,)).fetchall()

            for row in rows:
                await _resolve_ghost(row)
                await asyncio.sleep(0.5)   # be gentle with yfinance

        except Exception as e:
            logger.warning(f"Ghost tracker loop error: {e}")

        await asyncio.sleep(_GHOST_CHECK_SECS)


# ─── Analytics ───────────────────────────────────────────────────────────────

def win_rate_by_session() -> list[dict]:
    """Win rate, avg P&L, sample count per session — traded trades only."""
    with _db() as conn:
        rows = conn.execute("""
            SELECT
                t.session,
                t.instrument,
                COUNT(*)                                          AS trades,
                ROUND(100.0 * SUM(CASE WHEN t.outcome='tp_hit' THEN 1 ELSE 0 END) / COUNT(*), 1) AS win_pct,
                ROUND(AVG(t.pnl), 2)                             AS avg_pnl,
                ROUND(AVG(t.duration_mins), 0)                   AS avg_mins,
                ROUND(AVG(t.adx_at_entry), 1)                    AS avg_adx,
                ROUND(AVG(t.rsi_at_entry), 1)                    AS avg_rsi,
                ROUND(MIN(t.pnl), 2)                             AS worst_trade,
                ROUND(MAX(t.pnl), 2)                             AS best_trade
            FROM trade_outcomes t
            GROUP BY t.session, t.instrument
            ORDER BY win_pct DESC
        """).fetchall()
    return [dict(r) for r in rows]


def win_rate_by_score_band() -> list[dict]:
    """Win rate grouped in score buckets (55-60, 60-65, …)."""
    with _db() as conn:
        rows = conn.execute("""
            SELECT
                (score / 5) * 5                                   AS score_floor,
                (score / 5) * 5 + 4                               AS score_ceil,
                COUNT(*)                                           AS trades,
                ROUND(100.0 * SUM(CASE WHEN outcome='tp_hit' THEN 1 ELSE 0 END) / COUNT(*), 1) AS win_pct,
                ROUND(AVG(pnl), 2)                                 AS avg_pnl
            FROM trade_outcomes
            GROUP BY score / 5
            ORDER BY score_floor
        """).fetchall()
    return [dict(r) for r in rows]


def ghost_hit_rate_by_session() -> list[dict]:
    """What % of skipped setups would have been winners — by session."""
    with _db() as conn:
        rows = conn.execute("""
            SELECT
                session,
                instrument,
                skip_reason,
                COUNT(*)                                                AS skipped,
                SUM(CASE WHEN ghost_outcome='tp_hit' THEN 1 ELSE 0 END) AS would_win,
                SUM(CASE WHEN ghost_outcome='sl_hit' THEN 1 ELSE 0 END) AS would_lose,
                ROUND(100.0 * SUM(CASE WHEN ghost_outcome='tp_hit' THEN 1 ELSE 0 END)
                      / NULLIF(SUM(CASE WHEN ghost_outcome IN ('tp_hit','sl_hit') THEN 1 ELSE 0 END), 0), 1) AS ghost_win_pct,
                ROUND(AVG(CASE WHEN ghost_outcome IN ('tp_hit','sl_hit') THEN ghost_pnl END), 2) AS avg_ghost_pnl
            FROM signal_evaluations
            WHERE traded=0 AND ghost_outcome != 'pending'
            GROUP BY session, instrument, skip_reason
            ORDER BY ghost_win_pct DESC
        """).fetchall()
    return [dict(r) for r in rows]


def threshold_suggestions() -> list[dict]:
    """Per-session suggestions: raise/lower min_score based on actual win rates."""
    suggestions = []
    with _db() as conn:
        rows = conn.execute("""
            SELECT
                t.session,
                t.instrument,
                t.score,
                t.outcome,
                t.pnl
            FROM trade_outcomes t
            WHERE t.score IS NOT NULL
            ORDER BY t.session, t.instrument, t.score
        """).fetchall()

    # Group by session+instrument, find optimal score floor
    from collections import defaultdict
    buckets: dict = defaultdict(list)
    for r in rows:
        buckets[(r["session"], r["instrument"])].append(r)

    for (session, instrument), trades in buckets.items():
        if len(trades) < 10:
            suggestions.append({
                "session": session, "instrument": instrument,
                "note": f"Only {len(trades)} trades — need 10+ for suggestion",
                "current_min_score": None, "suggested_min_score": None,
            })
            continue

        best_floor = None
        best_wr    = 0.0
        for floor in range(55, 85, 3):
            subset = [t for t in trades if t["score"] >= floor]
            if len(subset) < 5:
                break
            wr = sum(1 for t in subset if t["outcome"] == "tp_hit") / len(subset)
            if wr > best_wr:
                best_wr    = wr
                best_floor = floor

        suggestions.append({
            "session":           session,
            "instrument":        instrument,
            "sample_trades":     len(trades),
            "current_win_pct":   round(100 * sum(1 for t in trades if t["outcome"] == "tp_hit") / len(trades), 1),
            "suggested_min_score": best_floor,
            "projected_win_pct": round(best_wr * 100, 1),
        })

    return suggestions


def pnl_heatmap() -> list[dict]:
    """P&L sum and trade count by hour-of-day (ET) and day-of-week."""
    with _db() as conn:
        rows = conn.execute("""
            SELECT
                CAST(strftime('%H', opened_at) AS INTEGER)        AS hour_et,
                CAST(strftime('%w', opened_at) AS INTEGER)        AS dow,
                COUNT(*)                                           AS trades,
                ROUND(SUM(pnl), 2)                                AS total_pnl,
                ROUND(AVG(pnl), 2)                                AS avg_pnl,
                ROUND(100.0 * SUM(CASE WHEN outcome='tp_hit' THEN 1 ELSE 0 END) / COUNT(*), 1) AS win_pct
            FROM trade_outcomes
            WHERE opened_at IS NOT NULL
            GROUP BY hour_et, dow
            ORDER BY dow, hour_et
        """).fetchall()
    return [dict(r) for r in rows]
