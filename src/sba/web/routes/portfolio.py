"""Daily portfolio builder API endpoint."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from sba.config import get_settings

logger = logging.getLogger(__name__)
from sba.web.errors import safe_endpoint

router = APIRouter(tags=["portfolio"])


@router.get("/portfolio")
@safe_endpoint
def get_daily_portfolio(
    sport: str = Query(None),
    max_bets: int = Query(20, ge=1, le=100),
    max_exposure: float = Query(15.0, ge=1.0, le=50.0),
    min_ev: float = Query(None, ge=0, le=1),
):
    """Build a diversified daily betting portfolio from available edges."""
    settings = get_settings()
    if not settings.ODDS_API_KEY:
        raise HTTPException(400, "ODDS_API_KEY not configured")

    from sba.services.edge_finder import EdgeFinder
    from sba.services.portfolio import build_portfolio

    finder = EdgeFinder()
    edges = finder.scan(sport, "h2h,spreads,totals", min_ev or settings.EV_THRESHOLD)

    return build_portfolio(
        edges=edges,
        bankroll=settings.BANKROLL,
        max_bets=max_bets,
        max_exposure_pct=max_exposure,
        min_ev=min_ev or settings.EV_THRESHOLD,
    )


@router.get("/portfolio/preview")
@safe_endpoint
def preview_portfolio(
    sport: str = Query(None),
    max_bets: int = Query(20),
):
    """Preview portfolio without fetching live odds — uses cached edges."""
    return {
        "info": "Use GET /api/portfolio to build a live portfolio from current odds.",
        "settings": {
            "max_bets": max_bets,
            "sport": sport or get_settings().DEFAULT_SPORT,
        },
    }
