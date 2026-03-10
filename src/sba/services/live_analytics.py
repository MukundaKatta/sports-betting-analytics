"""Live/in-play betting analytics service.

Inspired by Outlier React Live (March 2026). Provides real-time
momentum tracking, pace analysis, live edge detection, and
performance-vs-baseline comparisons during active games.

In-play betting now accounts for 53% of all online betting activity.
"""

from __future__ import annotations

import logging
import statistics
from datetime import datetime

from sba.data.db import get_connection

logger = logging.getLogger(__name__)


def get_live_game_analysis(event_id: str) -> dict:
    """Analyze a live game with momentum, pace, and edge signals.

    Combines latest odds movement with historical patterns to surface
    real-time actionable insights.
    """
    with get_connection() as conn:
        # Get event info
        event = conn.execute(
            "SELECT * FROM events WHERE id = ?", (event_id,)
        ).fetchone()
        if not event:
            return {"error": f"Event '{event_id}' not found"}

        # Get all odds snapshots for this event, ordered by time
        snapshots = conn.execute("""
            SELECT bookmaker, market, outcome_name, outcome_point,
                   price_american, price_decimal, snapshot_time
            FROM odds_snapshots
            WHERE event_id = ?
            ORDER BY snapshot_time ASC
        """, (event_id,)).fetchall()

    if not snapshots:
        return {
            "event": dict(event),
            "status": "no_odds_data",
            "momentum": None,
            "line_movements": [],
            "signals": [],
        }

    # Group snapshots by market + outcome for line movement analysis
    movements = _analyze_line_movements(snapshots)

    # Detect momentum shifts
    momentum = _detect_momentum(snapshots, event)

    # Generate live signals
    signals = _generate_live_signals(movements, momentum)

    return {
        "event": {
            "id": event["id"],
            "sport": event["sport"],
            "home_team": event["home_team"],
            "away_team": event["away_team"],
            "commence_time": event["commence_time"],
        },
        "snapshot_count": len(snapshots),
        "momentum": momentum,
        "line_movements": movements[:20],  # top 20 most significant
        "signals": signals,
        "last_update": snapshots[-1]["snapshot_time"] if snapshots else None,
    }


def _analyze_line_movements(snapshots: list) -> list[dict]:
    """Track how lines have moved across all markets and bookmakers."""
    # Group by (market, outcome_name, bookmaker)
    groups: dict[tuple, list] = {}
    for s in snapshots:
        key = (s["market"], s["outcome_name"], s["bookmaker"])
        groups.setdefault(key, []).append(s)

    movements = []
    for (market, outcome, book), snaps in groups.items():
        if len(snaps) < 2:
            continue

        first = snaps[0]
        last = snaps[-1]
        odds_change = last["price_american"] - first["price_american"]
        point_change = None
        if first["outcome_point"] is not None and last["outcome_point"] is not None:
            point_change = last["outcome_point"] - first["outcome_point"]

        # Direction: shortening = market moving toward this outcome
        if odds_change < 0 and last["price_american"] > 0:
            direction = "shortening"  # becoming more likely
        elif odds_change > 0 and last["price_american"] < 0:
            direction = "shortening"
        elif odds_change > 0 and last["price_american"] > 0:
            direction = "drifting"  # becoming less likely
        elif odds_change < 0 and last["price_american"] < 0:
            direction = "drifting"
        else:
            direction = "stable"

        movements.append({
            "market": market,
            "outcome": outcome,
            "bookmaker": book,
            "opening_odds": first["price_american"],
            "current_odds": last["price_american"],
            "odds_change": odds_change,
            "point_change": point_change,
            "direction": direction,
            "snapshots": len(snaps),
            "first_seen": first["snapshot_time"],
            "last_seen": last["snapshot_time"],
        })

    # Sort by absolute magnitude of odds change
    movements.sort(key=lambda m: abs(m["odds_change"]), reverse=True)
    return movements


def _detect_momentum(snapshots: list, event: dict) -> dict:
    """Detect which team has momentum based on odds movements.

    Uses spread and moneyline movements as proxy for in-game momentum.
    """
    home = event["home_team"]
    away = event["away_team"]

    # Focus on moneyline / h2h market
    ml_snaps = [s for s in snapshots if s["market"] in ("h2h", "moneyline")]

    home_snaps = [s for s in ml_snaps if home.lower() in s["outcome_name"].lower()]
    away_snaps = [s for s in ml_snaps if away.lower() in s["outcome_name"].lower()]

    home_trend = _calculate_trend(home_snaps)
    away_trend = _calculate_trend(away_snaps)

    # Determine momentum
    if home_trend["direction"] == "shortening" and home_trend["magnitude"] > 10:
        momentum_team = home
        momentum_strength = min(home_trend["magnitude"], 100)
    elif away_trend["direction"] == "shortening" and away_trend["magnitude"] > 10:
        momentum_team = away
        momentum_strength = min(away_trend["magnitude"], 100)
    else:
        momentum_team = "neutral"
        momentum_strength = 0

    return {
        "team": momentum_team,
        "strength": round(momentum_strength, 1),
        "home_trend": home_trend,
        "away_trend": away_trend,
    }


def _calculate_trend(snaps: list) -> dict:
    """Calculate price trend direction and magnitude."""
    if len(snaps) < 2:
        return {"direction": "stable", "magnitude": 0, "data_points": len(snaps)}

    prices = [s["price_american"] for s in snaps]
    first_price = prices[0]
    last_price = prices[-1]
    change = last_price - first_price

    if change < -5:
        direction = "shortening"
    elif change > 5:
        direction = "drifting"
    else:
        direction = "stable"

    return {
        "direction": direction,
        "magnitude": abs(change),
        "first_price": first_price,
        "last_price": last_price,
        "data_points": len(snaps),
    }


def _generate_live_signals(movements: list, momentum: dict) -> list[dict]:
    """Generate actionable signals from live data."""
    signals = []

    # Signal 1: Steam move (rapid, large odds shift)
    for m in movements[:10]:
        if abs(m["odds_change"]) >= 30:
            signals.append({
                "type": "steam_move",
                "severity": "high" if abs(m["odds_change"]) >= 50 else "medium",
                "market": m["market"],
                "outcome": m["outcome"],
                "detail": (
                    f"{m['outcome']} moved {m['odds_change']:+d} at {m['bookmaker']} "
                    f"({m['opening_odds']} → {m['current_odds']})"
                ),
                "action": "Consider following sharp money" if m["direction"] == "shortening" else "Potential value on the other side",
            })

    # Signal 2: Line movement disagreement (one book moves, others don't)
    market_groups: dict[str, list] = {}
    for m in movements:
        market_groups.setdefault(m["market"], []).append(m)

    for market, mvs in market_groups.items():
        if len(mvs) >= 2:
            changes = [m["odds_change"] for m in mvs]
            if max(changes) - min(changes) > 40:
                signals.append({
                    "type": "book_disagreement",
                    "severity": "medium",
                    "market": market,
                    "detail": f"Books disagree on {market}: changes range from {min(changes):+d} to {max(changes):+d}",
                    "action": "Potential middle or arbitrage opportunity",
                })

    # Signal 3: Momentum-based signal
    if momentum and momentum.get("strength", 0) > 30:
        team = momentum["team"]
        signals.append({
            "type": "momentum_shift",
            "severity": "medium",
            "market": "h2h",
            "detail": f"Strong momentum toward {team} (strength: {momentum['strength']})",
            "action": f"Live bet on {team} may have value if market hasn't fully adjusted",
        })

    return signals


# ── Live Dashboard Data ─────────────────────────────────────────────

def get_live_games_summary() -> dict:
    """Get summary of all currently active games with live signals."""
    with get_connection() as conn:
        # Active (not completed) events
        active = conn.execute("""
            SELECT e.id, e.sport, e.home_team, e.away_team, e.commence_time,
                   COUNT(os.id) as snapshot_count,
                   MAX(os.snapshot_time) as last_odds_update
            FROM events e
            LEFT JOIN odds_snapshots os ON os.event_id = e.id
            WHERE e.completed = 0
              AND e.commence_time <= datetime('now')
            GROUP BY e.id
            ORDER BY e.commence_time DESC
            LIMIT 50
        """).fetchall()

    games = []
    for g in active:
        games.append({
            "event_id": g["id"],
            "sport": g["sport"],
            "matchup": f"{g['away_team']} @ {g['home_team']}",
            "commence_time": g["commence_time"],
            "odds_snapshots": g["snapshot_count"],
            "last_update": g["last_odds_update"],
        })

    return {
        "active_games": len(games),
        "games": games,
    }


def get_odds_velocity(event_id: str, window_minutes: int = 15) -> dict:
    """Measure how fast odds are changing for an event.

    Higher velocity = more market activity = sharper attention.
    """
    with get_connection() as conn:
        snaps = conn.execute("""
            SELECT market, outcome_name, price_american, snapshot_time
            FROM odds_snapshots
            WHERE event_id = ?
              AND snapshot_time >= datetime('now', ? || ' minutes')
            ORDER BY snapshot_time ASC
        """, (event_id, f"-{window_minutes}")).fetchall()

    if len(snaps) < 2:
        return {"velocity": 0, "window_minutes": window_minutes, "changes": 0}

    # Count meaningful price changes
    changes = 0
    total_magnitude = 0
    groups: dict[tuple, list] = {}
    for s in snaps:
        key = (s["market"], s["outcome_name"])
        groups.setdefault(key, []).append(s["price_american"])

    for key, prices in groups.items():
        for i in range(1, len(prices)):
            diff = abs(prices[i] - prices[i - 1])
            if diff > 0:
                changes += 1
                total_magnitude += diff

    velocity = round(total_magnitude / window_minutes, 2) if window_minutes > 0 else 0

    return {
        "velocity": velocity,
        "window_minutes": window_minutes,
        "changes": changes,
        "avg_magnitude": round(total_magnitude / max(changes, 1), 1),
        "intensity": "high" if velocity > 5 else "medium" if velocity > 1 else "low",
    }
