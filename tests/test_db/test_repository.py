"""Tests for database repository."""

import sqlite3
from datetime import date, datetime

import pytest

from sba.data.db.repository import Repository
from sba.data.db.schema import SCHEMA_SQL
from sba.models.domain import Event, OddsSnapshot, Player, PlayerGameLog, TrackedBet


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    yield conn
    conn.close()


@pytest.fixture
def repo():
    return Repository()


class TestEventCRUD:
    def test_upsert_and_get_event(self, db, repo):
        event = Event(
            id="test1", sport="basketball_nba",
            home_team="Lakers", away_team="Celtics",
            commence_time=datetime(2025, 3, 15, 19, 0),
        )
        repo.upsert_event(db, event)
        result = repo.get_event(db, "test1")
        assert result is not None
        assert result.home_team == "Lakers"
        assert result.away_team == "Celtics"

    def test_upsert_updates_score(self, db, repo):
        event = Event(
            id="test1", sport="basketball_nba",
            home_team="Lakers", away_team="Celtics",
            commence_time=datetime(2025, 3, 15, 19, 0),
        )
        repo.upsert_event(db, event)

        event.completed = True
        event.home_score = 110
        event.away_score = 105
        repo.upsert_event(db, event)

        result = repo.get_event(db, "test1")
        assert result.completed is True
        assert result.home_score == 110

    def test_get_upcoming_events(self, db, repo):
        for i in range(3):
            repo.upsert_event(db, Event(
                id=f"game{i}", sport="basketball_nba",
                home_team=f"Home{i}", away_team=f"Away{i}",
                commence_time=datetime(2025, 3, 15 + i, 19, 0),
            ))
        events = repo.get_upcoming_events(db, "basketball_nba")
        assert len(events) == 3


class TestOddsCRUD:
    def test_insert_and_get_snapshot(self, db, repo):
        repo.upsert_event(db, Event(
            id="g1", sport="nba", home_team="A", away_team="B",
            commence_time=datetime(2025, 1, 1),
        ))
        repo.insert_odds_snapshot(db, OddsSnapshot(
            event_id="g1", bookmaker="fanduel", market="h2h",
            outcome_name="A", outcome_point=None,
            price_american=-150, price_decimal=1.667,
        ))
        db.commit()
        snapshots = repo.get_latest_odds(db, "g1", "h2h")
        assert len(snapshots) == 1
        assert snapshots[0].price_american == -150


class TestPlayerCRUD:
    def test_upsert_and_find_player(self, db, repo):
        repo.upsert_player(db, Player(id=1, name="LeBron James", team="Lakers", position="F"))
        found = repo.get_player_by_name(db, "LeBron")
        assert found is not None
        assert found.name == "LeBron James"

    def test_insert_game_log(self, db, repo):
        repo.upsert_player(db, Player(id=1, name="Test Player"))
        log = PlayerGameLog(
            player_id=1, game_date=date(2025, 1, 15),
            opponent="Boston", home_away="home", minutes=35,
            points=28, rebounds=8, assists=6, threes=3,
        )
        repo.insert_game_log(db, log)
        logs = repo.get_player_logs(db, 1)
        assert len(logs) == 1
        assert logs[0].points == 28


class TestBetCRUD:
    def test_insert_and_get_bet(self, db, repo):
        repo.upsert_event(db, Event(
            id="g1", sport="nba", home_team="A", away_team="B",
            commence_time=datetime(2025, 1, 1),
        ))
        bet = TrackedBet(
            event_id="g1", market="h2h", selection="A", line=None,
            odds_american=150, odds_decimal=2.5,
            model_probability=0.55, expected_value=0.05,
            kelly_fraction=0.025, recommended_stake=25.0,
            bookmaker="fanduel",
        )
        bet_id = repo.insert_bet(db, bet)
        db.commit()
        pending = repo.get_pending_bets(db)
        assert len(pending) == 1
        assert pending[0].odds_american == 150

    def test_settle_bet(self, db, repo):
        repo.upsert_event(db, Event(
            id="g1", sport="nba", home_team="A", away_team="B",
            commence_time=datetime(2025, 1, 1),
        ))
        bet = TrackedBet(
            event_id="g1", market="h2h", selection="A", line=None,
            odds_american=150, odds_decimal=2.5,
            model_probability=0.55, expected_value=0.05,
            kelly_fraction=0.025, recommended_stake=25.0,
            bookmaker="fanduel",
        )
        bet_id = repo.insert_bet(db, bet)
        db.commit()
        repo.update_bet_result(db, bet_id, "won", 37.50)
        db.commit()
        history = repo.get_bet_history(db)
        assert history[0].status == "won"
        assert history[0].profit_loss == 37.50
