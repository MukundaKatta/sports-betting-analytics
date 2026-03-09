"""Database schema definitions."""

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    sport TEXT NOT NULL,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    commence_time TEXT NOT NULL,
    completed INTEGER DEFAULT 0,
    home_score INTEGER,
    away_score INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS odds_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT REFERENCES events(id),
    bookmaker TEXT NOT NULL,
    market TEXT NOT NULL,
    outcome_name TEXT NOT NULL,
    outcome_point REAL,
    price_american INTEGER NOT NULL,
    price_decimal REAL NOT NULL,
    snapshot_time TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_odds_event_market
    ON odds_snapshots(event_id, market, snapshot_time);

CREATE TABLE IF NOT EXISTS players (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    team TEXT,
    position TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS player_game_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER REFERENCES players(id),
    game_date TEXT NOT NULL,
    opponent TEXT,
    home_away TEXT,
    minutes REAL,
    points INTEGER,
    rebounds INTEGER,
    assists INTEGER,
    threes INTEGER,
    steals INTEGER,
    blocks INTEGER,
    turnovers INTEGER,
    fga INTEGER,
    fgm INTEGER,
    fta INTEGER,
    ftm INTEGER,
    plus_minus INTEGER,
    UNIQUE(player_id, game_date)
);

CREATE INDEX IF NOT EXISTS idx_player_logs
    ON player_game_logs(player_id, game_date);

CREATE TABLE IF NOT EXISTS bets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT REFERENCES events(id),
    market TEXT NOT NULL,
    selection TEXT NOT NULL,
    line REAL,
    odds_american INTEGER,
    odds_decimal REAL,
    model_probability REAL,
    expected_value REAL,
    kelly_fraction REAL,
    recommended_stake REAL,
    bookmaker TEXT,
    status TEXT DEFAULT 'pending',
    profit_loss REAL DEFAULT 0,
    placed_at TEXT DEFAULT CURRENT_TIMESTAMP,
    settled_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_bets_status ON bets(status, placed_at);

CREATE TABLE IF NOT EXISTS model_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_type TEXT NOT NULL,
    sport TEXT NOT NULL,
    version TEXT NOT NULL,
    metrics TEXT,
    file_path TEXT NOT NULL,
    trained_at TEXT DEFAULT CURRENT_TIMESTAMP,
    is_active INTEGER DEFAULT 1
);
"""
