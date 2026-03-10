"""Edge finding, arbitrage, middles, and low-holds endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from sba.config import get_settings
from sba.web.api import repo

logger = logging.getLogger(__name__)
router = APIRouter(tags=["edges"])


# ── Pydantic models ─────────────────────────────────────────────────

class EdgeResponse(BaseModel):
    event_home: str
    event_away: str
    event_id: str
    market: str
    selection: str
    line: float | None
    best_odds_american: int
    best_odds_decimal: float
    bookmaker: str
    model_prob: float
    implied_prob: float
    ev: float
    ev_pct: str
    kelly_pct: float
    recommended_stake: float
    confidence: str


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("/edges", response_model=list[EdgeResponse])
def get_edges(
    sport: str = Query(None),
    market: str = Query("h2h,spreads,totals"),
    min_ev: float = Query(None),
):
    """Scan for +EV betting opportunities."""
    settings = get_settings()
    if not settings.ODDS_API_KEY:
        raise HTTPException(400, "ODDS_API_KEY not configured")

    from sba.services.edge_finder import EdgeFinder

    finder = EdgeFinder()
    opportunities = finder.scan(sport, market, min_ev)

    return [
        EdgeResponse(
            event_home=o.event.home_team,
            event_away=o.event.away_team,
            event_id=o.event.id,
            market=o.market,
            selection=o.selection,
            line=o.line,
            best_odds_american=o.best_odds.price_american,
            best_odds_decimal=o.best_odds.price_decimal,
            bookmaker=o.bookmaker,
            model_prob=round(o.model_prob, 4),
            implied_prob=round(o.implied_prob, 4),
            ev=round(o.ev, 4),
            ev_pct=f"{o.ev * 100:+.1f}%",
            kelly_pct=round(o.kelly_pct, 4),
            recommended_stake=round(o.recommended_stake, 2),
            confidence=o.confidence,
        )
        for o in opportunities
    ]


# ── Arbitrage / Middles / Low-Hold Scanning ──────────────────────────

@router.get("/arbitrage")
def scan_arbitrage(
    sport: str = Query("basketball_nba"),
):
    """Scan live odds for arbitrage opportunities."""
    from sba.services.arbitrage import find_arbitrage
    from sba.services.edge_finder import EdgeFinder

    settings = get_settings()
    finder = EdgeFinder(api_key=settings.odds_api_key)

    try:
        events_odds = finder.fetch_odds(sport)
    except Exception as exc:
        logger.error(f"Arb scan failed: {exc}")
        return {"opportunities": [], "error": str(exc)}

    arbs = find_arbitrage(events_odds)
    return {
        "sport": sport,
        "scanned_events": len(events_odds),
        "opportunities": [
            {
                "event": f"{a.event_away} @ {a.event_home}",
                "event_id": a.event_id,
                "market": a.market,
                "outcome_a": a.outcome_a,
                "outcome_b": a.outcome_b,
                "book_a": a.book_a,
                "book_b": a.book_b,
                "odds_a": a.odds_a_american,
                "odds_b": a.odds_b_american,
                "profit_pct": a.profit_pct,
                "stake_a_pct": a.stake_a_pct,
                "stake_b_pct": a.stake_b_pct,
            }
            for a in arbs
        ],
    }


@router.get("/middles")
def scan_middles(
    sport: str = Query("basketball_nba"),
):
    """Scan for middle betting opportunities."""
    from sba.services.arbitrage import find_middles
    from sba.services.edge_finder import EdgeFinder

    settings = get_settings()
    finder = EdgeFinder(api_key=settings.odds_api_key)

    try:
        events_odds = finder.fetch_odds(sport)
    except Exception as exc:
        logger.error(f"Middle scan failed: {exc}")
        return {"opportunities": [], "error": str(exc)}

    middles = find_middles(events_odds)
    return {
        "sport": sport,
        "scanned_events": len(events_odds),
        "opportunities": [
            {
                "event": f"{m.event_away} @ {m.event_home}",
                "event_id": m.event_id,
                "market": m.market,
                "selection": m.selection,
                "book_a": m.book_a,
                "book_b": m.book_b,
                "line_a": m.line_a,
                "line_b": m.line_b,
                "odds_a": m.odds_a_american,
                "odds_b": m.odds_b_american,
                "gap": m.gap,
                "description": m.description,
            }
            for m in middles
        ],
    }


@router.get("/low-holds")
def scan_low_holds(
    sport: str = Query("basketball_nba"),
    max_hold: float = Query(3.0, description="Max hold % to include"),
):
    """Scan for low-hold/low-vig markets."""
    from sba.services.arbitrage import find_low_holds
    from sba.services.edge_finder import EdgeFinder

    settings = get_settings()
    finder = EdgeFinder(api_key=settings.odds_api_key)

    try:
        events_odds = finder.fetch_odds(sport)
    except Exception as exc:
        logger.error(f"Low-hold scan failed: {exc}")
        return {"markets": [], "error": str(exc)}

    low_holds = find_low_holds(events_odds, max_hold=max_hold / 100.0)
    return {
        "sport": sport,
        "scanned_events": len(events_odds),
        "max_hold_pct": max_hold,
        "markets": [
            {
                "event": f"{lh.event_away} @ {lh.event_home}",
                "event_id": lh.event_id,
                "market": lh.market,
                "best_book_a": lh.best_book_a,
                "best_book_b": lh.best_book_b,
                "odds_a": lh.best_odds_a_american,
                "odds_b": lh.best_odds_b_american,
                "hold_pct": lh.hold_pct,
            }
            for lh in low_holds
        ],
    }
