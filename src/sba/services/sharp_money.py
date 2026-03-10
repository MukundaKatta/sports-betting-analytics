"""Sharp money detection and line movement analysis service."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sba.models.domain import OddsSnapshot, SharpMove

logger = logging.getLogger(__name__)

# Thresholds for detecting sharp action
STEAM_MOVE_THRESHOLD = 15  # points of American odds movement
REVERSE_LINE_THRESHOLD = 10  # odds moving opposite to public action
SHARP_BOOKS = {"pinnacle", "circa", "bookmaker", "betcris"}


@dataclass
class LineMovementSignal:
    """A detected line movement signal indicating possible sharp action."""

    event_id: str
    market: str
    outcome: str
    signal_type: str  # steam_move, reverse_line_movement, sharp_book_origin
    bookmaker: str
    odds_open: int
    odds_current: int
    line_open: float | None
    line_current: float | None
    movement: int  # American odds change
    confidence: str  # low, medium, high
    description: str


def detect_sharp_moves(
    snapshots: list[OddsSnapshot],
) -> list[SharpMove]:
    """Analyze odds snapshots to detect sharp money movements.

    Looks for:
    1. Steam moves: rapid line changes across multiple books
    2. Reverse line movement: line moving opposite to expected public action
    3. Sharp book origination: moves that start at sharp books first
    """
    if not snapshots:
        return []

    # Group snapshots by (bookmaker, outcome_name)
    by_book_outcome: dict[str, list[OddsSnapshot]] = {}
    for s in snapshots:
        key = f"{s.bookmaker}|{s.outcome_name}"
        by_book_outcome.setdefault(key, []).append(s)

    # Sort each group by time
    for key in by_book_outcome:
        by_book_outcome[key].sort(key=lambda x: x.snapshot_time or "")

    moves = []

    for key, snaps in by_book_outcome.items():
        if len(snaps) < 2:
            continue

        bookmaker = snaps[0].bookmaker
        outcome = snaps[0].outcome_name
        event_id = snaps[0].event_id
        market = snaps[0].market

        # Compare first and last snapshot
        opening = snaps[0]
        current = snaps[-1]
        odds_change = current.price_american - opening.price_american

        if abs(odds_change) < STEAM_MOVE_THRESHOLD:
            continue

        # Detect move type
        if bookmaker.lower() in SHARP_BOOKS:
            move_type = "sharp_book_origin"
        elif abs(odds_change) >= STEAM_MOVE_THRESHOLD * 2:
            move_type = "steam_move"
        else:
            move_type = "line_movement"

        # Check for line changes (spreads/totals)
        line_before = opening.outcome_point
        line_after = current.outcome_point
        line_change = 0.0
        if line_before is not None and line_after is not None:
            line_change = abs(line_after - line_before)

        magnitude = abs(odds_change) + (line_change * 20)

        moves.append(SharpMove(
            event_id=event_id,
            market=market,
            outcome=outcome,
            move_type=move_type,
            bookmaker=bookmaker,
            odds_before=opening.price_american,
            odds_after=current.price_american,
            line_before=line_before,
            line_after=line_after,
            magnitude=round(magnitude, 1),
        ))

    # Sort by magnitude descending
    moves.sort(key=lambda x: x.magnitude, reverse=True)
    logger.info(f"Detected {len(moves)} sharp moves")
    return moves


def analyze_line_signals(
    snapshots: list[OddsSnapshot],
) -> list[LineMovementSignal]:
    """Higher-level analysis returning human-readable signals."""
    if not snapshots:
        return []

    by_book_outcome: dict[str, list[OddsSnapshot]] = {}
    for s in snapshots:
        key = f"{s.bookmaker}|{s.outcome_name}"
        by_book_outcome.setdefault(key, []).append(s)

    for key in by_book_outcome:
        by_book_outcome[key].sort(key=lambda x: x.snapshot_time or "")

    signals = []

    for key, snaps in by_book_outcome.items():
        if len(snaps) < 2:
            continue

        bookmaker = snaps[0].bookmaker
        outcome = snaps[0].outcome_name
        event_id = snaps[0].event_id
        market = snaps[0].market
        opening = snaps[0]
        current = snaps[-1]
        odds_change = current.price_american - opening.price_american

        if abs(odds_change) < 5:
            continue

        # Determine signal type and confidence
        is_sharp = bookmaker.lower() in SHARP_BOOKS
        big_move = abs(odds_change) >= STEAM_MOVE_THRESHOLD * 2
        moderate_move = abs(odds_change) >= STEAM_MOVE_THRESHOLD

        if is_sharp and big_move:
            signal_type = "sharp_book_origin"
            confidence = "high"
        elif big_move:
            signal_type = "steam_move"
            confidence = "high"
        elif is_sharp and moderate_move:
            signal_type = "sharp_book_origin"
            confidence = "medium"
        elif moderate_move:
            signal_type = "line_movement"
            confidence = "medium"
        else:
            signal_type = "line_movement"
            confidence = "low"

        # Build description
        direction = "shortened" if odds_change < 0 else "lengthened"
        desc = (
            f"{outcome} odds {direction} by {abs(odds_change)} pts at {bookmaker} "
            f"({opening.price_american:+d} -> {current.price_american:+d})"
        )

        line_open = opening.outcome_point
        line_current = current.outcome_point
        if line_open is not None and line_current is not None and line_open != line_current:
            desc += f" | Line: {line_open} -> {line_current}"

        signals.append(LineMovementSignal(
            event_id=event_id,
            market=market,
            outcome=outcome,
            signal_type=signal_type,
            bookmaker=bookmaker,
            odds_open=opening.price_american,
            odds_current=current.price_american,
            line_open=line_open,
            line_current=line_current,
            movement=odds_change,
            confidence=confidence,
            description=desc,
        ))

    # Sort high-confidence first, then by magnitude
    signals.sort(key=lambda s: (
        {"high": 0, "medium": 1, "low": 2}.get(s.confidence, 3),
        -abs(s.movement),
    ))

    logger.info(f"Generated {len(signals)} line movement signals")
    return signals


def calculate_clv(placed_odds_american: int, closing_odds_american: int) -> dict:
    """Calculate Closing Line Value (CLV).

    CLV measures whether you got a better price than the closing line.
    Positive CLV indicates long-term profitable betting.
    """
    from sba.utils.odds_math import american_to_decimal, decimal_to_implied_prob

    placed_dec = american_to_decimal(placed_odds_american)
    closing_dec = american_to_decimal(closing_odds_american)

    placed_prob = decimal_to_implied_prob(placed_dec)
    closing_prob = decimal_to_implied_prob(closing_dec)

    # CLV as probability difference (positive = you got better odds)
    clv_prob = closing_prob - placed_prob
    # CLV as percentage of edge
    clv_pct = round(clv_prob * 100, 2)
    # CLV as American odds difference
    clv_american = placed_odds_american - closing_odds_american

    return {
        "placed_odds": placed_odds_american,
        "closing_odds": closing_odds_american,
        "clv_american": clv_american,
        "clv_percentage": clv_pct,
        "beat_closing": clv_pct > 0,
    }
