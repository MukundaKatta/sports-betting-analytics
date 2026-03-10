"""Tests for the new store_event_odds repository method."""

from datetime import datetime

from sba.models.domain import BookmakerOdds, Event, EventOdds, Outcome


class TestStoreEventOdds:
    def test_stores_events_and_snapshots(self, db, repo, sample_event_odds):
        repo.store_event_odds(db, [sample_event_odds])
        db.commit()

        # Check event was stored
        event = repo.get_event(db, "game_001")
        assert event is not None
        assert event.home_team == "Los Angeles Lakers"

        # Check snapshots were stored
        snapshots = repo.get_latest_odds(db, "game_001", "h2h")
        assert len(snapshots) > 0

    def test_stores_multiple_events(self, db, repo):
        events_odds = []
        for i in range(3):
            events_odds.append(EventOdds(
                event=Event(
                    id=f"game_{i}", sport="nba",
                    home_team=f"Home{i}", away_team=f"Away{i}",
                    commence_time=datetime(2025, 3, 15 + i, 19, 0),
                ),
                bookmakers=[
                    BookmakerOdds(
                        bookmaker="fanduel", market="h2h",
                        outcomes=[
                            Outcome(name=f"Home{i}", price_american=-150, price_decimal=1.667),
                            Outcome(name=f"Away{i}", price_american=130, price_decimal=2.3),
                        ],
                    ),
                ],
            ))

        repo.store_event_odds(db, events_odds)
        db.commit()

        for i in range(3):
            event = repo.get_event(db, f"game_{i}")
            assert event is not None

    def test_empty_list(self, db, repo):
        repo.store_event_odds(db, [])
        db.commit()
        # Should not raise
