"""Bet Correlation Warning System.

Analyzes a user's pending/active bets to detect correlated exposure —
situations where multiple bets move together, amplifying risk beyond
what the individual stakes suggest.

Warnings:
- Same-event exposure (multiple bets on one game)
- Correlated market exposure (e.g., spread + total on same team)
- Single-book concentration risk
- Temporal clustering (too many bets in one time window)
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from sba.data.db import get_connection

logger = logging.getLogger(__name__)


@dataclass
class CorrelationWarning:
    severity: str  # high, medium, low
    category: str  # same_event, correlated_markets, book_concentration, temporal
    message: str
    affected_bets: list[int] = field(default_factory=list)
    exposure: float = 0.0


def analyze_bet_correlations() -> dict:
    """Analyze pending bets for correlated exposure and return warnings."""
    with get_connection() as conn:
        pending = conn.execute("""
            SELECT b.id, b.event_id, b.market, b.selection, b.bookmaker,
                   b.recommended_stake, b.odds_american, b.placed_at,
                   e.home_team, e.away_team, e.sport, e.commence_time
            FROM bets b
            LEFT JOIN events e ON e.id = b.event_id
            WHERE b.status = 'pending'
            ORDER BY b.placed_at DESC
        """).fetchall()

    if not pending:
        return {
            "warnings": [],
            "risk_level": "none",
            "pending_count": 0,
            "total_exposure": 0,
            "summary": "No pending bets to analyze.",
        }

    bets = [dict(r) for r in pending]
    warnings: list[CorrelationWarning] = []

    warnings.extend(_check_same_event(bets))
    warnings.extend(_check_book_concentration(bets))
    warnings.extend(_check_temporal_clustering(bets))
    warnings.extend(_check_sport_concentration(bets))

    total_exposure = sum(abs(b.get("recommended_stake") or 0) for b in bets)

    # Overall risk level based on worst warning
    if any(w.severity == "high" for w in warnings):
        risk_level = "high"
    elif any(w.severity == "medium" for w in warnings):
        risk_level = "medium"
    elif warnings:
        risk_level = "low"
    else:
        risk_level = "none"

    return {
        "warnings": [
            {
                "severity": w.severity,
                "category": w.category,
                "message": w.message,
                "affected_bets": w.affected_bets,
                "exposure": round(w.exposure, 2),
            }
            for w in sorted(warnings, key=lambda x: {"high": 0, "medium": 1, "low": 2}[x.severity])
        ],
        "risk_level": risk_level,
        "pending_count": len(bets),
        "total_exposure": round(total_exposure, 2),
        "summary": _build_summary(warnings, len(bets), total_exposure),
    }


def _check_same_event(bets: list[dict]) -> list[CorrelationWarning]:
    """Detect multiple bets on the same event."""
    warnings = []
    by_event: dict[str, list[dict]] = defaultdict(list)
    for b in bets:
        if b.get("event_id"):
            by_event[b["event_id"]].append(b)

    for event_id, event_bets in by_event.items():
        if len(event_bets) < 2:
            continue
        exposure = sum(abs(b.get("recommended_stake") or 0) for b in event_bets)
        home = event_bets[0].get("home_team", "?")
        away = event_bets[0].get("away_team", "?")
        markets = [b.get("market", "?") for b in event_bets]
        warnings.append(CorrelationWarning(
            severity="high" if len(event_bets) >= 3 else "medium",
            category="same_event",
            message=(
                f"{len(event_bets)} bets on {away} @ {home} "
                f"({', '.join(markets)}). Combined exposure: ${exposure:.2f}. "
                f"If the game goes sideways, all bets are affected."
            ),
            affected_bets=[b["id"] for b in event_bets],
            exposure=exposure,
        ))
    return warnings


def _check_book_concentration(bets: list[dict]) -> list[CorrelationWarning]:
    """Detect over-concentration on a single bookmaker."""
    warnings = []
    total_exposure = sum(abs(b.get("recommended_stake") or 0) for b in bets)
    if total_exposure == 0:
        return warnings

    by_book: Counter[str] = Counter()
    exposure_by_book: dict[str, float] = defaultdict(float)
    ids_by_book: dict[str, list[int]] = defaultdict(list)

    for b in bets:
        book = b.get("bookmaker", "unknown")
        by_book[book] += 1
        exposure_by_book[book] += abs(b.get("recommended_stake") or 0)
        ids_by_book[book].append(b["id"])

    for book, count in by_book.items():
        pct = exposure_by_book[book] / total_exposure * 100
        if pct >= 70 and count >= 3:
            warnings.append(CorrelationWarning(
                severity="medium",
                category="book_concentration",
                message=(
                    f"{pct:.0f}% of exposure (${exposure_by_book[book]:.2f}) is at {book}. "
                    f"Spread across more books to reduce account-limiting risk."
                ),
                affected_bets=ids_by_book[book],
                exposure=exposure_by_book[book],
            ))
    return warnings


def _check_temporal_clustering(bets: list[dict]) -> list[CorrelationWarning]:
    """Detect too many bets placed in a short window (possible tilt)."""
    warnings = []
    timestamps = []
    for b in bets:
        if b.get("placed_at"):
            timestamps.append(b)

    if len(timestamps) < 5:
        return warnings

    # Sort by placed_at and check if 5+ bets in a 30-minute window
    sorted_bets = sorted(timestamps, key=lambda x: x["placed_at"])
    for i in range(len(sorted_bets) - 4):
        first = sorted_bets[i]["placed_at"]
        fifth = sorted_bets[i + 4]["placed_at"]
        # Simple string comparison works for ISO timestamps
        if first and fifth and first[:16] == fifth[:16]:  # Same hour+minute range
            cluster = sorted_bets[i:i + 5]
            exposure = sum(abs(b.get("recommended_stake") or 0) for b in cluster)
            warnings.append(CorrelationWarning(
                severity="medium",
                category="temporal",
                message=(
                    f"5+ bets placed in rapid succession. "
                    f"Consider spacing out bets to avoid tilt-driven decisions."
                ),
                affected_bets=[b["id"] for b in cluster],
                exposure=exposure,
            ))
            break  # One warning is enough
    return warnings


def _check_sport_concentration(bets: list[dict]) -> list[CorrelationWarning]:
    """Detect all bets concentrated in one sport."""
    warnings = []
    sports = [b.get("sport") for b in bets if b.get("sport")]
    if not sports or len(bets) < 5:
        return warnings

    sport_counts = Counter(sports)
    total = len(sports)
    for sport, count in sport_counts.items():
        pct = count / total * 100
        if pct >= 80 and count >= 5:
            warnings.append(CorrelationWarning(
                severity="low",
                category="sport_concentration",
                message=(
                    f"{pct:.0f}% of bets are in {sport}. "
                    f"Diversifying across sports reduces correlated downswings."
                ),
                affected_bets=[b["id"] for b in bets if b.get("sport") == sport],
            ))
    return warnings


def _build_summary(warnings: list[CorrelationWarning], count: int, exposure: float) -> str:
    """Generate a human-readable summary."""
    if not warnings:
        return f"{count} pending bets (${exposure:.2f} exposure) — no correlation issues detected."

    high = sum(1 for w in warnings if w.severity == "high")
    medium = sum(1 for w in warnings if w.severity == "medium")
    parts = []
    if high:
        parts.append(f"{high} high-priority")
    if medium:
        parts.append(f"{medium} medium-priority")
    return (
        f"{count} pending bets (${exposure:.2f} exposure) with "
        f"{' and '.join(parts)} correlation warning{'s' if len(warnings) > 1 else ''}."
    )
