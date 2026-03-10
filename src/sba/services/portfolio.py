"""Daily portfolio builder service.

Inspired by OddsShopper's Portfolio EV — constructs a diversified "portfolio"
of +EV bets for the day. Like a robo-advisor for sports betting.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime

from sba.config import get_settings
from sba.models.domain import EdgeOpportunity

logger = logging.getLogger(__name__)


def build_portfolio(
    edges: list[EdgeOpportunity],
    bankroll: float | None = None,
    max_bets: int = 20,
    max_exposure_pct: float = 15.0,
    min_ev: float = 0.02,
    diversify: bool = True,
) -> dict:
    """Build a diversified daily portfolio from available edges.

    Args:
        edges: Available edge opportunities (pre-scanned).
        bankroll: Total bankroll. Uses settings default if not provided.
        max_bets: Maximum number of bets in the portfolio.
        max_exposure_pct: Maximum % of bankroll to risk in total.
        min_ev: Minimum EV threshold to include a bet.
        diversify: If True, limit bets per event and per book.
    """
    settings = get_settings()
    bankroll = bankroll or settings.BANKROLL

    # Filter to edges meeting threshold
    eligible = [e for e in edges if e.ev >= min_ev]

    # Sort by EV descending
    eligible.sort(key=lambda e: e.ev, reverse=True)

    portfolio = []
    total_stake = 0.0
    max_total_stake = bankroll * (max_exposure_pct / 100)
    events_used: set[str] = set()
    books_count: dict[str, int] = {}

    for edge in eligible:
        if len(portfolio) >= max_bets:
            break

        if total_stake >= max_total_stake:
            break

        # Diversification rules
        if diversify:
            # Max 2 bets per event
            if events_used.count(edge.event.id) if hasattr(events_used, 'count') else list(events_used).count(edge.event.id) >= 2:
                continue
            # Max 5 bets per bookmaker
            if books_count.get(edge.bookmaker, 0) >= 5:
                continue

        # Calculate stake (capped Kelly)
        stake = min(edge.recommended_stake, max_total_stake - total_stake)
        # Minimum $1 bet
        if stake < 1.0:
            continue

        portfolio.append({
            "event_id": edge.event.id,
            "event_name": f"{edge.event.away_team} @ {edge.event.home_team}",
            "commence_time": edge.event.commence_time.isoformat(),
            "market": edge.market,
            "selection": edge.selection,
            "line": edge.line,
            "bookmaker": edge.bookmaker,
            "odds_american": edge.best_odds.price_american,
            "odds_decimal": round(edge.best_odds.price_decimal, 3),
            "ev_pct": round(edge.ev * 100, 2),
            "model_prob": round(edge.model_prob, 4),
            "kelly_pct": round(edge.kelly_pct, 4),
            "stake": round(stake, 2),
            "confidence": edge.confidence,
            "expected_profit": round(stake * edge.ev, 2),
        })

        total_stake += stake
        events_used.add(edge.event.id)
        books_count[edge.bookmaker] = books_count.get(edge.bookmaker, 0) + 1

    # Portfolio summary stats
    if portfolio:
        avg_ev = sum(b["ev_pct"] for b in portfolio) / len(portfolio)
        avg_odds = sum(b["odds_decimal"] for b in portfolio) / len(portfolio)
        expected_profit = sum(b["expected_profit"] for b in portfolio)
        unique_events = len(set(b["event_id"] for b in portfolio))
        unique_books = len(set(b["bookmaker"] for b in portfolio))
    else:
        avg_ev = avg_odds = expected_profit = 0
        unique_events = unique_books = 0

    return {
        "portfolio": portfolio,
        "summary": {
            "total_bets": len(portfolio),
            "total_stake": round(total_stake, 2),
            "expected_profit": round(expected_profit, 2),
            "expected_roi": round(expected_profit / max(total_stake, 0.01) * 100, 2),
            "avg_ev_pct": round(avg_ev, 2),
            "avg_odds": round(avg_odds, 3),
            "bankroll_exposure": round(total_stake / max(bankroll, 0.01) * 100, 2),
            "unique_events": unique_events,
            "unique_books": unique_books,
            "bankroll": round(bankroll, 2),
        },
        "generated_at": datetime.now().isoformat(),
    }
