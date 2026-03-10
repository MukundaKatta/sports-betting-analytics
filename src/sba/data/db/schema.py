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

CREATE TABLE IF NOT EXISTS watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    label TEXT DEFAULT '',
    added_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_type TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT DEFAULT '',
    data TEXT DEFAULT '{}',
    read INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_alerts_read ON alerts(read, created_at);

CREATE TABLE IF NOT EXISTS bankroll_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    amount REAL NOT NULL,
    change REAL NOT NULL DEFAULT 0,
    reason TEXT DEFAULT '',
    bet_id INTEGER REFERENCES bets(id),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_bankroll_log_date ON bankroll_log(created_at);

CREATE TABLE IF NOT EXISTS bet_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bet_id INTEGER NOT NULL REFERENCES bets(id),
    tag TEXT NOT NULL,
    UNIQUE(bet_id, tag)
);

CREATE TABLE IF NOT EXISTS bet_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bet_id INTEGER NOT NULL REFERENCES bets(id),
    note TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS closing_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bet_id INTEGER NOT NULL UNIQUE REFERENCES bets(id),
    closing_odds_american INTEGER NOT NULL,
    closing_odds_decimal REAL NOT NULL,
    clv_american INTEGER DEFAULT 0,
    clv_percentage REAL DEFAULT 0,
    captured_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sharp_moves (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL,
    market TEXT NOT NULL,
    outcome TEXT NOT NULL,
    move_type TEXT NOT NULL,
    bookmaker TEXT NOT NULL,
    odds_before INTEGER NOT NULL,
    odds_after INTEGER NOT NULL,
    line_before REAL,
    line_after REAL,
    magnitude REAL DEFAULT 0,
    detected_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_sharp_moves_event ON sharp_moves(event_id, detected_at);

CREATE TABLE IF NOT EXISTS leaderboard (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    display_name TEXT DEFAULT '',
    total_bets INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    total_profit REAL DEFAULT 0,
    roi_pct REAL DEFAULT 0,
    win_rate REAL DEFAULT 0,
    avg_odds INTEGER DEFAULT 0,
    best_streak INTEGER DEFAULT 0,
    rank_score REAL DEFAULT 0,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS public_picks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    event_id TEXT NOT NULL,
    market TEXT NOT NULL,
    selection TEXT NOT NULL,
    odds_american INTEGER NOT NULL,
    line REAL,
    confidence TEXT DEFAULT 'medium',
    analysis TEXT DEFAULT '',
    status TEXT DEFAULT 'pending',
    profit_loss REAL DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_public_picks_user ON public_picks(username, created_at);

CREATE TABLE IF NOT EXISTS alert_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_type TEXT NOT NULL,
    condition_json TEXT NOT NULL DEFAULT '{}',
    enabled INTEGER DEFAULT 1,
    last_triggered TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_achievements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    achievement_id TEXT NOT NULL UNIQUE,
    unlocked_at TEXT DEFAULT CURRENT_TIMESTAMP,
    points INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_achievements_id ON user_achievements(achievement_id);

CREATE INDEX IF NOT EXISTS idx_odds_bookmaker ON odds_snapshots(bookmaker);
CREATE INDEX IF NOT EXISTS idx_odds_time ON odds_snapshots(snapshot_time);
CREATE INDEX IF NOT EXISTS idx_bets_placed ON bets(placed_at);
CREATE INDEX IF NOT EXISTS idx_bets_status ON bets(status);
CREATE INDEX IF NOT EXISTS idx_events_sport ON events(sport);
CREATE INDEX IF NOT EXISTS idx_events_time ON events(commence_time);

CREATE TABLE IF NOT EXISTS user_stats (
    key TEXT PRIMARY KEY,
    value REAL DEFAULT 0,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS clv_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bet_id INTEGER NOT NULL REFERENCES bets(id) ON DELETE CASCADE,
    placed_odds_american INTEGER NOT NULL,
    placed_odds_decimal REAL NOT NULL,
    closing_odds_american INTEGER,
    closing_odds_decimal REAL,
    best_closing_odds_american INTEGER,
    best_closing_odds_decimal REAL,
    clv_placed REAL,
    clv_best REAL,
    recorded_at TEXT DEFAULT (datetime('now')),
    UNIQUE(bet_id)
);
CREATE INDEX IF NOT EXISTS idx_clv_bet ON clv_records(bet_id);

CREATE TABLE IF NOT EXISTS book_balances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sportsbook TEXT NOT NULL,
    balance REAL NOT NULL DEFAULT 0,
    deposited REAL NOT NULL DEFAULT 0,
    withdrawn REAL NOT NULL DEFAULT 0,
    bonus_balance REAL NOT NULL DEFAULT 0,
    notes TEXT DEFAULT '',
    is_limited INTEGER DEFAULT 0,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(sportsbook)
);

CREATE TABLE IF NOT EXISTS book_balance_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sportsbook TEXT NOT NULL,
    balance REAL NOT NULL,
    change REAL NOT NULL DEFAULT 0,
    reason TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_book_balance_history ON book_balance_history(sportsbook, created_at);

CREATE TABLE IF NOT EXISTS account_limits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sportsbook TEXT NOT NULL,
    limit_type TEXT NOT NULL DEFAULT 'none',
    max_stake REAL,
    severity TEXT NOT NULL DEFAULT 'none',
    notes TEXT DEFAULT '',
    detected_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(sportsbook)
);

CREATE INDEX IF NOT EXISTS idx_account_limits_book ON account_limits(sportsbook);

-- Performance indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_bets_market ON bets(market);
CREATE INDEX IF NOT EXISTS idx_bets_bookmaker ON bets(bookmaker);
CREATE INDEX IF NOT EXISTS idx_bets_settled ON bets(status, profit_loss) WHERE status IN ('won', 'lost', 'push');
CREATE INDEX IF NOT EXISTS idx_bets_placed_date ON bets(DATE(placed_at));
CREATE INDEX IF NOT EXISTS idx_odds_event_book ON odds_snapshots(event_id, bookmaker);
CREATE INDEX IF NOT EXISTS idx_odds_market_time ON odds_snapshots(market, snapshot_time);
CREATE INDEX IF NOT EXISTS idx_events_active ON events(completed, commence_time) WHERE completed = 0;
CREATE INDEX IF NOT EXISTS idx_player_logs_opponent ON player_game_logs(player_id, opponent);
CREATE INDEX IF NOT EXISTS idx_clv_recorded ON clv_records(recorded_at);

CREATE TABLE IF NOT EXISTS notification_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    rule_type TEXT NOT NULL,
    sport TEXT DEFAULT '',
    min_ev REAL DEFAULT 0,
    min_odds INTEGER DEFAULT -1000,
    max_odds INTEGER DEFAULT 1000,
    bookmakers TEXT DEFAULT '',
    webhook_url TEXT DEFAULT '',
    enabled INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Responsible gambling: configurable limits
CREATE TABLE IF NOT EXISTS rg_limits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    limit_type TEXT NOT NULL,
    amount REAL NOT NULL,
    period TEXT NOT NULL DEFAULT 'daily',
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(limit_type, period)
);

-- Responsible gambling: session tracking
CREATE TABLE IF NOT EXISTS rg_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT DEFAULT CURRENT_TIMESTAMP,
    ended_at TEXT,
    duration_minutes REAL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_rg_sessions_date ON rg_sessions(DATE(started_at));

-- v2.5: Composite indexes for optimized JOIN queries
CREATE INDEX IF NOT EXISTS idx_odds_event_market_book ON odds_snapshots(event_id, market, bookmaker, outcome_name);
CREATE INDEX IF NOT EXISTS idx_bets_event ON bets(event_id, status);
CREATE INDEX IF NOT EXISTS idx_bets_placed ON bets(placed_at);
CREATE INDEX IF NOT EXISTS idx_events_sport ON events(sport);
CREATE INDEX IF NOT EXISTS idx_bankroll_date ON bankroll_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_closing_lines_bet ON closing_lines(bet_id);
CREATE INDEX IF NOT EXISTS idx_players_name ON players(name COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_bets_status_settled ON bets(status, settled_at);
CREATE INDEX IF NOT EXISTS idx_odds_event_time ON odds_snapshots(event_id, market, snapshot_time DESC);
CREATE INDEX IF NOT EXISTS idx_sharp_moves_event ON sharp_moves(event_id, detected_at);
CREATE INDEX IF NOT EXISTS idx_public_picks_user ON public_picks(username, created_at);
"""
