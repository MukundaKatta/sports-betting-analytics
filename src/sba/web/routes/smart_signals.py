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
