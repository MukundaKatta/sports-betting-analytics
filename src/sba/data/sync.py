"""Data synchronization orchestrator."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from sba.config import get_settings
from sba.data.clients.balldontlie import BallDontLieClient
from sba.data.clients.odds_api import OddsAPIClient
from sba.data.db import get_connection, init_db
from sba.data.db.repository import Repository

logger = logging.getLogger(__name__)


class DataSyncer:
    def __init__(self):
        self.settings = get_settings()
        self.odds_client = OddsAPIClient(self.settings.ODDS_API_KEY)
        self.stats_client = BallDontLieClient(self.settings.BALLDONTLIE_API_KEY)
        self.repo = Repository()
        init_db()

    def sync_odds(self, sport: str, markets: str = "h2h,spreads,totals") -> int:
        """Fetch and store current odds. Returns number of events synced."""
        events_odds = self.odds_client.get_odds(
            sport=sport,
            regions=self.settings.DEFAULT_REGION,
            markets=markets,
        )
        with get_connection() as conn:
            self.repo.store_event_odds(conn, events_odds)
        logger.info(f"Synced odds for {len(events_odds)} events")
        return len(events_odds)

    def sync_scores(self, sport: str) -> int:
        """Fetch scores and update completed events. Returns count updated."""
        events = self.odds_client.get_scores(sport, days_from=3)
        count = 0
        with get_connection() as conn:
            for event in events:
                if event.completed:
                    self.repo.upsert_event(conn, event)
                    count += 1
        logger.info(f"Updated {count} completed events")
        return count

    def sync_player_stats(self, player_ids: list[int], seasons: list[int]) -> int:
        """Backfill player game logs. Returns total logs inserted."""
        total = 0
        with get_connection() as conn:
            for pid in player_ids:
                for season in seasons:
                    logs = self.stats_client.get_player_stats(pid, season)
                    for log in logs:
                        self.repo.insert_game_log(conn, log)
                    total += len(logs)
                    logger.info(f"Synced {len(logs)} games for player {pid}, season {season}")
        return total

    def search_and_sync_player(self, name: str, seasons: list[int]) -> int:
        """Search for a player and sync their stats."""
        players = self.stats_client.get_players(search=name)
        if not players:
            logger.warning(f"No player found matching '{name}'")
            return 0

        player = players[0]
        with get_connection() as conn:
            self.repo.upsert_player(conn, player)

        return self.sync_player_stats([player.id], seasons)

    # ── Async methods (for web endpoints) ───────────────────────────

    async def async_sync_odds(self, sport: str, markets: str = "h2h,spreads,totals") -> int:
        """Async version of sync_odds for use from web endpoints."""
        events_odds = await self.odds_client.aget_odds(
            sport=sport,
            regions=self.settings.DEFAULT_REGION,
            markets=markets,
        )
        with get_connection() as conn:
            self.repo.store_event_odds(conn, events_odds)
        logger.info(f"Async synced odds for {len(events_odds)} events")
        return len(events_odds)

    async def async_sync_multi_sport(
        self, sports: list[str], markets: str = "h2h,spreads,totals",
    ) -> dict[str, int]:
        """Fetch odds for multiple sports concurrently."""
        tasks = [self.async_sync_odds(sport, markets) for sport in sports]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        summary = {}
        for sport, result in zip(sports, results):
            if isinstance(result, Exception):
                logger.error(f"Failed to sync {sport}: {result}")
                summary[sport] = 0
            else:
                summary[sport] = result
        return summary

    async def aclose(self) -> None:
        """Close async HTTP clients."""
        await self.odds_client.aclose()
        await self.stats_client.aclose()

    def get_status(self) -> dict:
        return {
            "odds_api_credits_remaining": self.odds_client.remaining_credits,
            "timestamp": datetime.now().isoformat(),
        }
