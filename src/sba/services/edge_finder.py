"""Core +EV detection engine."""

from __future__ import annotations

import logging

from sba.config import get_settings
from sba.data.clients.odds_api import OddsAPIClient
from sba.data.db import get_connection, init_db
from sba.data.db.repository import Repository
from sba.models.domain import ArbOpportunity, EdgeOpportunity, EventOdds, OddsSnapshot
from sba.models.statistical.arbitrage import scan_arbitrage
from sba.models.statistical.ev import find_ev_opportunities
from sba.models.statistical.implied_prob import consensus_probability, sharp_probability
from sba.models.statistical.poisson import over_under_prob
from sba.utils.odds_math import decimal_to_implied_prob

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

        events_odds = self.odds_client.get_odds(
            sport=sport,
            regions=self.settings.DEFAULT_REGION,
            markets=markets,
        )

        self._store_snapshots(events_odds)
        return self._find_opportunities(events_odds, threshold)

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

    def scan_arbs(self, sport: str | None = None,
                   markets: str = "h2h") -> list[ArbOpportunity]:
        """Scan for arbitrage opportunities across all upcoming events.

        Fetches live odds and detects sure-bet arbs where the best odds
        on each side of a market sum to < 100% implied probability.
        """
        sport = sport or self.settings.DEFAULT_SPORT
        market_list = [m.strip() for m in markets.split(",")]

        events_odds = self.odds_client.get_odds(
            sport=sport,
            regions=self.settings.DEFAULT_REGION,
            markets=markets,
        )

        self._store_snapshots(events_odds)

        arbs = scan_arbitrage(events_odds, market_list)
        logger.info(f"Found {len(arbs)} arbitrage opportunities")
        return arbs

    def calculate_clv(self, bet_id: int) -> float | None:
        """Calculate Closing Line Value for a tracked bet.

        Looks up the bet's event_id and market, finds the last odds
        snapshot before the event's commence_time, and compares the
        bet's taken odds vs closing odds.

        Returns:
            CLV as a percentage (positive = beat the close), or None if
            closing odds are not available.
        """
        with get_connection() as conn:
            bet = self.repo.get_bet_by_id(conn, bet_id)
            if bet is None:
                logger.warning(f"Bet {bet_id} not found")
                return None

            closing = self.repo.get_closing_odds(
                conn, bet.event_id, bet.market, bet.selection,
            )
            if closing is None:
                logger.info(f"No closing odds found for bet {bet_id}")
                return None

            # CLV = (taken_implied - closing_implied) / closing_implied * 100
            # A positive value means the bettor got better odds than the
            # closing line (i.e. the line moved in their favour).
            taken_implied = decimal_to_implied_prob(bet.odds_decimal)
            closing_implied = decimal_to_implied_prob(closing.price_decimal)

            if closing_implied == 0:
                return None

            clv = ((closing_implied - taken_implied) / closing_implied) * 100.0
            return round(clv, 3)

    def _store_snapshots(self, events_odds: list[EventOdds]):
        with get_connection() as conn:
            self.repo.store_event_odds(conn, events_odds)

    def _group_by_market(self, event_odds: EventOdds) -> dict:
        markets = {}
        for bm in event_odds.bookmakers:
            markets.setdefault(bm.market, []).append(bm)
        return markets

    async def async_scan(self, sport: str | None = None,
                         markets: str = "h2h,spreads,totals",
                         min_ev: float | None = None) -> list[EdgeOpportunity]:
        """Async version of scan() for use in FastAPI endpoints.

        Uses async API client to avoid blocking the event loop.
        """
        sport = sport or self.settings.DEFAULT_SPORT
        threshold = min_ev if min_ev is not None else self.settings.EV_THRESHOLD

        events_odds = await self.odds_client.aget_odds(
            sport=sport,
            regions=self.settings.DEFAULT_REGION,
            markets=markets,
        )

        self._store_snapshots(events_odds)
        return self._find_opportunities(events_odds, threshold)

    async def async_scan_arbs(self, sport: str | None = None,
                               markets: str = "h2h") -> list[ArbOpportunity]:
        """Async version of scan_arbs() for use in FastAPI endpoints."""
        sport = sport or self.settings.DEFAULT_SPORT
        market_list = [m.strip() for m in markets.split(",")]

        events_odds = await self.odds_client.aget_odds(
            sport=sport,
            regions=self.settings.DEFAULT_REGION,
            markets=markets,
        )

        self._store_snapshots(events_odds)
        arbs = scan_arbitrage(events_odds, market_list)
        logger.info("Found %d arbitrage opportunities", len(arbs))
        return arbs

    def _find_opportunities(self, events_odds: list[EventOdds],
                            threshold: float) -> list[EdgeOpportunity]:
        """Shared logic for finding +EV opportunities from fetched odds."""
        all_opportunities = []

        for event_odds in events_odds:
            markets_data = self._group_by_market(event_odds)

            for market, bm_odds_list in markets_data.items():
                model_probs = sharp_probability(bm_odds_list, self.settings.SHARP_BOOKS)
                if not model_probs:
                    model_probs = consensus_probability(bm_odds_list)
                if not model_probs:
                    continue

                if market == "totals":
                    model_probs = self._enhance_with_poisson(model_probs, event_odds)

                opps = find_ev_opportunities(event_odds, model_probs, market, threshold)
                all_opportunities.extend(opps)

        all_opportunities.sort(key=lambda x: x.ev, reverse=True)
        logger.info("Found %d +EV opportunities", len(all_opportunities))
        return all_opportunities

    def _enhance_with_poisson(self, model_probs: dict, event_odds: EventOdds) -> dict:
        """For totals: blend consensus probs with Poisson model if we have enough info."""
        return model_probs
