"""Smart Signals API routes.

Pattern-based high-confidence bet triggers. Inspired by Rithmm's
Smart Signals feature.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from sba.services.smart_signals import (
    discover_patterns,
    get_pattern_detail,
    scan_signals,
)

router = APIRouter(tags=["smart-signals"])


@router.get("/signals")
def api_scan_signals():
    """Scan for active Smart Signals.

    Returns high-confidence patterns matched to current opportunities.
    """
    return scan_signals()


@router.get("/signals/patterns")
def api_discover_patterns(
    min_bets: int = Query(5, ge=3, le=50),
    min_roi: float = Query(5.0, ge=0, le=100),
):
    """Discover profitable betting patterns from history."""
    return discover_patterns(min_bets=min_bets, min_roi=min_roi)


@router.get("/signals/pattern/{pattern_key:path}")
def api_pattern_detail(pattern_key: str):
    """Get detailed breakdown of a specific pattern."""
    return get_pattern_detail(pattern_key)


@router.post("/signals/rate")
def api_rate_opportunity(
    ev_pct: float = Query(0.0),
    edge_pct: float = Query(None),
    sharp_agrees: bool = Query(False),
    line_moving_toward: bool = Query(False),
    line_moving_away: bool = Query(False),
    pattern_confidence: float = Query(None),
    pattern_roi: float = Query(None),
    ml_probability: float = Query(None),
    books_with_edge: int = Query(1),
    total_books: int = Query(1),
    odds_american: int = Query(0),
    is_live: bool = Query(False),
):
    """Rate a betting opportunity using the unified traffic light system.

    Returns green/yellow/red signal with confidence score (0-100),
    star rating (1-5), and detailed reasoning.
    """
    from sba.services.signal_rating import rate_opportunity

    rating = rate_opportunity(
        ev_pct=ev_pct,
        edge_pct=edge_pct,
        sharp_agrees=sharp_agrees,
        line_moving_toward=line_moving_toward,
        line_moving_away=line_moving_away,
        pattern_confidence=pattern_confidence,
        pattern_roi=pattern_roi,
        ml_probability=ml_probability,
        books_with_edge=books_with_edge,
        total_books=total_books,
        odds_american=odds_american,
        is_live=is_live,
    )

    return {
        "signal": rating.signal,
        "confidence": rating.confidence,
        "stars": rating.stars,
        "label": rating.label,
        "reasons": rating.reasons,
        "warnings": rating.warnings,
    }
