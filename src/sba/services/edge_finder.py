"""Core +EV detection engine."""

from __future__ import annotations

import logging
from sba.config import get_settings
from sba.data.clients.odds_api import OddsAPIClient
from sba.data.db import get_connection, init_db
from sba.data.db.repository import Repository
from sba.models.domain import EventOdds, EdgeOpportunity
from sba.models.statistical.implied_prob import consensus_probability, sharp_probability
from sba.models.statistical.ev import find_ev_opportunities
from sba.models.statistical.poisson import over_under_prob

logger = logging.getLogger(__name__)


class EdgeFinder:
    def __init__(self):
        self.settings = get_settings()
        self.odds_client = OddsAPIClient(self.settings.ODDS_API_KEY)
        self.repo = Repository()
        init_db()

    def scan(self, sport: str | None = None,
             markets: str = "h2h,spreads,totals",
             min_ev: float | None = None) -> list[EdgeOpportunity]:
        """Scan for +EV opportunities across all upcoming events.

        Fetches live odds, computes consensus/sharp probabilities,
        and surfaces edges vs soft books.
        """
        sport = sport or self.settings.DEFAULT_SPORT
        threshold = min_ev if min_ev is not None else self.settings.EV_THRESHOLD

        # Fetch live odds
        events_odds = self.odds_client.get_odds(
            sport=sport,
            regions=self.settings.DEFAULT_REGION,
            markets=markets,
        )

        # Store snapshots
        self._store_snapshots(events_odds)

        all_opportunities = []

        for event_odds in events_odds:
            # Group bookmaker odds by market
            markets_data = self._group_by_market(event_odds)

            for market, bm_odds_list in markets_data.items():
                # Get model probabilities (consensus from sharp books)
                model_probs = sharp_probability(bm_odds_list, self.settings.SHARP_BOOKS)

                if not model_probs:
                    # Fallback to full consensus
                    model_probs = consensus_probability(bm_odds_list)

                if not model_probs:
                    continue

                # For totals, also run Poisson model as additional signal
                if market == "totals":
                    model_probs = self._enhance_with_poisson(model_probs, event_odds)

                # Find edges
                opps = find_ev_opportunities(event_odds, model_probs, market, threshold)
                all_opportunities.extend(opps)

        all_opportunities.sort(key=lambda x: x.ev, reverse=True)
        logger.info(f"Found {len(all_opportunities)} +EV opportunities")
        return all_opportunities

    def scan_market(self, sport: str, market: str,
                    min_ev: float | None = None) -> list[EdgeOpportunity]:
        """Scan a specific market only."""
        return self.scan(sport, markets=market, min_ev=min_ev)

    def get_line_movement(self, event_id: str, market: str = "h2h") -> list[OddsSnapshot]:
        """Get historical odds snapshots for an event."""
        with get_connection() as conn:
            return self.repo.get_odds_history(conn, event_id, market)

    def credits_remaining(self) -> int | None:
        return self.odds_client.remaining_credits

    def _store_snapshots(self, events_odds: list[EventOdds]):
        with get_connection() as conn:
            self.repo.store_event_odds(conn, events_odds)

    def _group_by_market(self, event_odds: EventOdds) -> dict:
        markets = {}
        for bm in event_odds.bookmakers:
            markets.setdefault(bm.market, []).append(bm)
        return markets

    def _enhance_with_poisson(self, model_probs: dict, event_odds: EventOdds) -> dict:
        """For totals: blend consensus probs with Poisson model if we have enough info."""
        # This is a simplified version - in production you'd use team offensive/defensive ratings
        # For now, just use the consensus probabilities as-is
        return model_probs
