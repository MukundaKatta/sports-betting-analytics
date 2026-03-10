"""Feature engineering for ML models."""

from __future__ import annotations

import pandas as pd

from sba.models.domain import PlayerGameLog

# Map prop market names to stat column names
PROP_STAT_MAP = {
    "player_points": "points",
    "player_rebounds": "rebounds",
    "player_assists": "assists",
    "player_threes": "threes",
    "player_blocks": "blocks",
    "player_steals": "steals",
    "player_points_rebounds_assists": ["points", "rebounds", "assists"],
    "player_points_rebounds": ["points", "rebounds"],
    "player_points_assists": ["points", "assists"],
}


def build_prop_features(logs: list[PlayerGameLog], opponent: str = "",
                        home_away: str = "", prop_market: str = "player_points") -> pd.DataFrame:
    """Build feature vector for a player prop prediction.

    Uses only historical data (no leakage). Returns a single-row DataFrame.
    """
    if len(logs) < 5:
        return pd.DataFrame()

    df = _logs_to_df(logs)
    stat_col = PROP_STAT_MAP.get(prop_market, "points")

    # Handle combo stats
    if isinstance(stat_col, list):
        df["target_stat"] = sum(df[c] for c in stat_col)
    else:
        df["target_stat"] = df[stat_col]

    features = {}

    # Rolling averages
    for window in [3, 5, 10, 20]:
        if len(df) >= window:
            features[f"avg_{window}"] = df["target_stat"].head(window).mean()
            features[f"std_{window}"] = df["target_stat"].head(window).std()
        else:
            features[f"avg_{window}"] = df["target_stat"].mean()
            features[f"std_{window}"] = df["target_stat"].std()

    # Season average
    features["season_avg"] = df["target_stat"].mean()
    features["season_std"] = df["target_stat"].std()
    features["games_played"] = len(df)

    # Trend: recent vs season
    recent_avg = df["target_stat"].head(5).mean()
    features["trend"] = recent_avg - features["season_avg"]
    features["trend_pct"] = features["trend"] / max(features["season_avg"], 0.1)

    # Minutes trend
    features["avg_minutes_5"] = df["minutes"].head(5).mean()
    features["avg_minutes_20"] = df["minutes"].head(20).mean() if len(df) >= 20 else df["minutes"].mean()
    features["minutes_trend"] = features["avg_minutes_5"] - features["avg_minutes_20"]

    # Home/away splits
    home_games = df[df["home_away"] == "home"]
    away_games = df[df["home_away"] == "away"]
    features["home_avg"] = home_games["target_stat"].mean() if len(home_games) > 0 else features["season_avg"]
    features["away_avg"] = away_games["target_stat"].mean() if len(away_games) > 0 else features["season_avg"]
    features["is_home"] = 1 if home_away == "home" else 0

    # Matchup history
    if opponent:
        vs_opp = df[df["opponent"] == opponent]
        features["vs_opponent_avg"] = vs_opp["target_stat"].mean() if len(vs_opp) > 0 else features["season_avg"]
        features["vs_opponent_games"] = len(vs_opp)
    else:
        features["vs_opponent_avg"] = features["season_avg"]
        features["vs_opponent_games"] = 0

    # Consistency metrics
    features["max_last_10"] = df["target_stat"].head(10).max()
    features["min_last_10"] = df["target_stat"].head(10).min()
    features["median_last_10"] = df["target_stat"].head(10).median()

    # Hit rate at various lines (how often exceeds thresholds)
    for threshold_pct in [0.8, 0.9, 1.0, 1.1, 1.2]:
        threshold = features["season_avg"] * threshold_pct
        features[f"hit_rate_{int(threshold_pct*100)}"] = (
            (df["target_stat"].head(20) > threshold).mean()
            if len(df) >= 5 else 0.5
        )

    # Efficiency stats
    if "fga" in df.columns and df["fga"].head(10).sum() > 0:
        features["fg_pct_10"] = df["fgm"].head(10).sum() / max(df["fga"].head(10).sum(), 1)
    else:
        features["fg_pct_10"] = 0.0

    return pd.DataFrame([features])


def build_prop_training_data(logs: list[PlayerGameLog],
                             prop_market: str = "player_points") -> tuple[pd.DataFrame, pd.Series]:
    """Build training dataset from game logs.

    For each game, features are built from games BEFORE that date (no leakage).
    Returns (X, y) pair.
    """
    stat_col = PROP_STAT_MAP.get(prop_market, "points")
    sorted_logs = sorted(logs, key=lambda x: x.game_date)

    X_rows = []
    y_vals = []

    for i in range(20, len(sorted_logs)):
        # Use only games before this one
        history = sorted_logs[:i][::-1]  # Reverse chronological
        game = sorted_logs[i]

        features_df = build_prop_features(
            history, opponent=game.opponent,
            home_away=game.home_away, prop_market=prop_market,
        )
        if features_df.empty:
            continue

        if isinstance(stat_col, list):
            target = sum(getattr(game, c) for c in stat_col)
        else:
            target = getattr(game, stat_col)

        X_rows.append(features_df.iloc[0])
        y_vals.append(target)

    if not X_rows:
        return pd.DataFrame(), pd.Series(dtype=float)

    return pd.DataFrame(X_rows), pd.Series(y_vals)


def get_target_stat(log: PlayerGameLog, prop_market: str) -> float:
    stat_col = PROP_STAT_MAP.get(prop_market, "points")
    if isinstance(stat_col, list):
        return sum(getattr(log, c) for c in stat_col)
    return getattr(log, stat_col)


def _logs_to_df(logs: list[PlayerGameLog]) -> pd.DataFrame:
    """Convert game logs to DataFrame. Assumes logs are in reverse chronological order."""
    return pd.DataFrame([
        {
            "game_date": log.game_date,
            "opponent": log.opponent,
            "home_away": log.home_away,
            "minutes": log.minutes,
            "points": log.points,
            "rebounds": log.rebounds,
            "assists": log.assists,
            "threes": log.threes,
            "steals": log.steals,
            "blocks": log.blocks,
            "turnovers": log.turnovers,
            "fga": log.fga,
            "fgm": log.fgm,
            "fta": log.fta,
            "ftm": log.ftm,
            "plus_minus": log.plus_minus,
        }
        for log in logs
    ])
