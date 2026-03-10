"""Smart Signals — pattern-based high-confidence bet triggers.

Inspired by Rithmm's Smart Signals. Identifies historically outperforming
conditions (specific player + bet type + odds range + situation) and
triggers high-confidence alerts when those conditions recur.
"""

from __future__ import annotations

import logging
import statistics
from collections import defaultdict

from sba.data.db import get_connection

logger = logging.getLogger(__name__)


def scan_signals() -> dict:
    """Scan historical bets for recurring profitable patterns and check
    if any current opportunities match those patterns.

    Returns active signals and the patterns that back them.
    """
    patterns = discover_patterns()
    active_signals = match_patterns_to_current(patterns)

    return {
        "patterns_found": len(patterns),
        "active_signals": active_signals,
        "patterns": patterns[:20],  # top 20
    }


def discover_patterns(min_bets: int = 5, min_roi: float = 5.0) -> list[dict]:
    """Mine historical bets for profitable patterns.

    Groups bets by (market, bookmaker, odds_range, sport) and identifies
    combinations that have historically outperformed.
    """
    with get_connection() as conn:
        settled = conn.execute("""
            SELECT b.market, b.bookmaker, b.odds_american, b.odds_decimal,
                   b.status, b.profit_loss, b.recommended_stake,
                   b.selection, b.placed_at, e.sport
            FROM bets b
            LEFT JOIN events e ON e.id = b.event_id
            WHERE b.status IN ('won', 'lost', 'push')
            ORDER BY b.placed_at DESC
        """).fetchall()

    if len(settled) < min_bets:
        return []

    # Group into pattern buckets
    buckets: dict[str, list] = defaultdict(list)

    for bet in settled:
        odds = bet["odds_american"] or 0
        odds_range = _odds_to_range(odds)
        sport = bet["sport"] or "unknown"

        # Pattern keys at multiple granularity levels
        keys = [
            f"market:{bet['market']}|sport:{sport}",
            f"market:{bet['market']}|odds:{odds_range}",
            f"market:{bet['market']}|book:{bet['bookmaker']}",
            f"sport:{sport}|odds:{odds_range}",
            f"market:{bet['market']}|sport:{sport}|odds:{odds_range}",
        ]

        for key in keys:
            buckets[key].append(bet)

    # Analyze each bucket
    patterns = []
    for key, bets in buckets.items():
        if len(bets) < min_bets:
            continue

        total_stake = sum(abs(b["recommended_stake"] or 1) for b in bets)
        total_pnl = sum(b["profit_loss"] or 0 for b in bets)
        wins = sum(1 for b in bets if b["status"] == "won")
        roi = (total_pnl / total_stake * 100) if total_stake > 0 else 0
        win_rate = (wins / len(bets) * 100)

        if roi < min_roi:
            continue

        # Check if pattern is consistent (not just one big win)
        pnls = [b["profit_loss"] or 0 for b in bets]
        consistency = 1 - (statistics.stdev(pnls) / (abs(statistics.mean(pnls)) + 0.01)) if len(pnls) > 1 else 0
        consistency = max(0, min(1, consistency))

        # Confidence: weighted by sample size, roi, and consistency
        confidence = min(100, (
            min(len(bets), 30) / 30 * 40 +  # sample size (up to 40 pts)
            min(roi, 30) / 30 * 35 +          # roi (up to 35 pts)
            consistency * 25                   # consistency (up to 25 pts)
        ))

        patterns.append({
            "pattern": key,
            "bets": len(bets),
            "wins": wins,
            "win_rate": round(win_rate, 1),
            "roi": round(roi, 1),
            "total_profit": round(total_pnl, 2),
            "consistency": round(consistency, 2),
            "confidence": round(confidence, 1),
            "last_bet": bets[0]["placed_at"],
        })

    patterns.sort(key=lambda p: p["confidence"], reverse=True)
    return patterns


def match_patterns_to_current(patterns: list[dict]) -> list[dict]:
    """Check if any current pending bets or edges match discovered patterns.

    This is where we surface 'Smart Signals' — current opportunities
    that match historically profitable patterns.
    """
    if not patterns:
        return []

    high_confidence = [p for p in patterns if p["confidence"] >= 60]
    if not high_confidence:
        return []

    with get_connection() as conn:
        # Check pending bets
        pending = conn.execute("""
            SELECT b.id, b.market, b.bookmaker, b.odds_american,
                   b.selection, b.expected_value, e.sport
            FROM bets b
            LEFT JOIN events e ON e.id = b.event_id
            WHERE b.status = 'pending'
        """).fetchall()

    signals = []
    for bet in pending:
        odds_range = _odds_to_range(bet["odds_american"] or 0)
        sport = bet["sport"] or "unknown"

        bet_keys = {
            f"market:{bet['market']}|sport:{sport}",
            f"market:{bet['market']}|odds:{odds_range}",
            f"market:{bet['market']}|book:{bet['bookmaker']}",
            f"sport:{sport}|odds:{odds_range}",
            f"market:{bet['market']}|sport:{sport}|odds:{odds_range}",
        }

        for pattern in high_confidence:
            if pattern["pattern"] in bet_keys:
                signals.append({
                    "bet_id": bet["id"],
                    "selection": bet["selection"],
                    "market": bet["market"],
                    "bookmaker": bet["bookmaker"],
                    "odds": bet["odds_american"],
                    "pattern": pattern["pattern"],
                    "pattern_roi": pattern["roi"],
                    "pattern_win_rate": pattern["win_rate"],
                    "pattern_bets": pattern["bets"],
                    "confidence": pattern["confidence"],
                    "signal": "strong_play" if pattern["confidence"] >= 80 else "good_play",
                })
                break  # one signal per bet

    signals.sort(key=lambda s: s["confidence"], reverse=True)
    return signals


def get_pattern_detail(pattern_key: str) -> dict:
    """Get detailed breakdown of a specific pattern's history."""
    with get_connection() as conn:
        settled = conn.execute("""
            SELECT b.market, b.bookmaker, b.odds_american, b.status,
                   b.profit_loss, b.recommended_stake, b.selection,
                   b.placed_at, e.sport, e.home_team, e.away_team
            FROM bets b
            LEFT JOIN events e ON e.id = b.event_id
            WHERE b.status IN ('won', 'lost', 'push')
            ORDER BY b.placed_at DESC
        """).fetchall()

    # Parse pattern key
    parts = dict(p.split(":") for p in pattern_key.split("|"))

    matching = []
    for bet in settled:
        odds_range = _odds_to_range(bet["odds_american"] or 0)
        sport = bet["sport"] or "unknown"

        match = True
        if "market" in parts and bet["market"] != parts["market"]:
            match = False
        if "sport" in parts and sport != parts["sport"]:
            match = False
        if "odds" in parts and odds_range != parts["odds"]:
            match = False
        if "book" in parts and bet["bookmaker"] != parts["book"]:
            match = False

        if match:
            matching.append({
                "selection": bet["selection"],
                "odds": bet["odds_american"],
                "status": bet["status"],
                "profit": bet["profit_loss"],
                "date": bet["placed_at"],
                "matchup": f"{bet['away_team']} @ {bet['home_team']}" if bet["home_team"] else "",
            })

    wins = sum(1 for m in matching if m["status"] == "won")
    total_pnl = sum(m["profit"] or 0 for m in matching)

    return {
        "pattern": pattern_key,
        "total_bets": len(matching),
        "wins": wins,
        "win_rate": round(wins / max(len(matching), 1) * 100, 1),
        "total_profit": round(total_pnl, 2),
        "bets": matching[:50],
    }


def _odds_to_range(odds: int) -> str:
    """Bucket American odds into ranges for pattern matching."""
    if odds >= 200:
        return "longshot_200+"
    elif odds >= 100:
        return "plus_100_200"
    elif odds >= -120:
        return "even_-120_+100"
    elif odds >= -200:
        return "favorite_-200_-120"
    else:
        return "heavy_fav_-200"
