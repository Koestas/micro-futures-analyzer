"""Analytics routes — learning engine insights."""
from fastapi import APIRouter
from engines.learning import (
    win_rate_by_session,
    win_rate_by_score_band,
    ghost_hit_rate_by_session,
    threshold_suggestions,
    pnl_heatmap,
)

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/win-rates")
def get_win_rates():
    return {
        "by_session":    win_rate_by_session(),
        "by_score_band": win_rate_by_score_band(),
    }


@router.get("/ghost-trades")
def get_ghost_trades():
    return {"missed_setups": ghost_hit_rate_by_session()}


@router.get("/suggestions")
def get_suggestions():
    return {"threshold_suggestions": threshold_suggestions()}


@router.get("/heatmap")
def get_heatmap():
    return {"heatmap": pnl_heatmap()}


@router.get("/summary")
def get_summary():
    return {
        "win_rates":    win_rate_by_session(),
        "score_bands":  win_rate_by_score_band(),
        "ghost_trades": ghost_hit_rate_by_session(),
        "suggestions":  threshold_suggestions(),
        "heatmap":      pnl_heatmap(),
    }
