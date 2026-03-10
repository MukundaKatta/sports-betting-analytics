"""Shared test fixtures."""

import sqlite3
from datetime import date, datetime

import pytest

from sba.data.db.repository import Repository
from sba.data.db.schema import SCHEMA_SQL
from sba.models.domain import (
    BookmakerOdds,
    Event,
    EventOdds,
    Outcome,
    Player,
    PlayerGameLog,
)


@pytest.fixture
def db():
    """In-memory SQLite database with schema applied."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    yield conn
    conn.close()


@pytest.fixture
def repo():
    """Repository instance."""
    return Repository()


@pytest.fixture
def sample_event():
    """A sample NBA event."""
    return Event(
        id="game_001",
        sport="basketball_nba",
        home_team="Los Angeles Lakers",
        away_team="Boston Celtics",
        commence_time=datetime(2025, 3, 15, 19, 0),
    )


@pytest.fixture
def sample_player():
    """A sample NBA player."""
    return Player(id=1, name="LeBron James", team="Lakers", position="F")


@pytest.fixture
def sample_game_logs():
    """30 sample game logs for ML training."""
    logs = []
    for i in range(30):
        logs.append(PlayerGameLog(
            player_id=1,
            game_date=date(2025, 1, 1 + i),
            opponent=f"Team{i % 5}",
            home_away="home" if i % 2 == 0 else "away",
            minutes=32.0 + (i % 5),
            points=25 + (i % 10) - 5,
            rebounds=7 + (i % 4),
            assists=6 + (i % 3),
            threes=2 + (i % 3),
            steals=1 + (i % 2),
            blocks=1,
            turnovers=3,
            fga=18 + (i % 4),
            fgm=8 + (i % 4),
            fta=6 + (i % 3),
            ftm=5 + (i % 3),
            plus_minus=5 - (i % 10),
        ))
    return logs


@pytest.fixture
def sample_event_odds(sample_event):
    """Sample event with bookmaker odds."""
    return EventOdds(
        event=sample_event,
        bookmakers=[
            BookmakerOdds(
                bookmaker="fanduel",
                market="h2h",
                outcomes=[
                    Outcome(name="Los Angeles Lakers", price_american=-150, price_decimal=1.667),
                    Outcome(name="Boston Celtics", price_american=130, price_decimal=2.3),
                ],
            ),
            BookmakerOdds(
                bookmaker="draftkings",
                market="h2h",
                outcomes=[
                    Outcome(name="Los Angeles Lakers", price_american=-145, price_decimal=1.69),
                    Outcome(name="Boston Celtics", price_american=125, price_decimal=2.25),
                ],
            ),
            BookmakerOdds(
                bookmaker="pinnacle",
                market="h2h",
                outcomes=[
                    Outcome(name="Los Angeles Lakers", price_american=-140, price_decimal=1.714),
                    Outcome(name="Boston Celtics", price_american=120, price_decimal=2.2),
                ],
            ),
        ],
    )
