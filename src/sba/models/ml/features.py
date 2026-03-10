"""Feature engineering for ML models."""

from __future__ import annotations

from datetime import timedelta

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
                        home_away: str = "", prop_market: str = "player_points",
                        line: float | None = None) -> pd.DataFrame:
    """Build feature vector for a player prop prediction.

    Args:
        logs: Game logs in reverse chronological order (most recent first).
        opponent: Upcoming opponent abbreviation.
        home_away: ``"home"`` or ``"away"`` for the upcoming game.
        prop_market: Market key from :data:`PROP_STAT_MAP`.
        line: The actual betting line. When provided, hit-rate features are
            computed relative to this line instead of season-average
            percentages.

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

    features: dict[str, float] = {}

    # ---- Rolling averages ----
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

    # ---- Trend: recent vs season ----
    recent_avg = df["target_stat"].head(5).mean()
    features["trend"] = recent_avg - features["season_avg"]
    features["trend_pct"] = features["trend"] / max(features["season_avg"], 0.1)

    # ---- Minutes trend ----
    features["avg_minutes_5"] = df["minutes"].head(5).mean()
    features["avg_minutes_20"] = df["minutes"].head(20).mean() if len(df) >= 20 else df["minutes"].mean()
    features["minutes_trend"] = features["avg_minutes_5"] - features["avg_minutes_20"]

    # ---- Rest days & back-to-back detection ----
    if "game_date" in df.columns and len(df) >= 2:
        dates = pd.to_datetime(df["game_date"])
        rest_days = (dates.iloc[0] - dates.iloc[1]).days - 1
        features["rest_days"] = max(rest_days, 0)
        features["is_back_to_back"] = 1.0 if rest_days == 0 else 0.0

        # Average rest over last 5 games
        if len(dates) >= 6:
            gaps = dates.head(6).diff(-1).dt.days.dropna() - 1
            features["avg_rest_5"] = gaps.mean()
        else:
            features["avg_rest_5"] = features["rest_days"]
    else:
        features["rest_days"] = 1.0
        features["is_back_to_back"] = 0.0
        features["avg_rest_5"] = 1.0

    # ---- Activity level: games played in the last 7 / 14 days ----
    if "game_date" in df.columns and len(df) >= 2:
        most_recent = dates.iloc[0]
        features["games_last_7d"] = float((dates >= most_recent - timedelta(days=7)).sum())
        features["games_last_14d"] = float((dates >= most_recent - timedelta(days=14)).sum())
    else:
        features["games_last_7d"] = 0.0
        features["games_last_14d"] = 0.0

    # ---- Home/away splits ----
    home_games = df[df["home_away"] == "home"]
    away_games = df[df["home_away"] == "away"]
    features["home_avg"] = home_games["target_stat"].mean() if len(home_games) > 0 else features["season_avg"]
    features["away_avg"] = away_games["target_stat"].mean() if len(away_games) > 0 else features["season_avg"]
    features["is_home"] = 1.0 if home_away == "home" else 0.0

    # ---- Matchup history ----
    if opponent:
        vs_opp = df[df["opponent"] == opponent]
        features["vs_opponent_avg"] = vs_opp["target_stat"].mean() if len(vs_opp) > 0 else features["season_avg"]
        features["vs_opponent_games"] = len(vs_opp)
    else:
        features["vs_opponent_avg"] = features["season_avg"]
        features["vs_opponent_games"] = 0

    # ---- Consistency metrics ----
    recent_10 = df["target_stat"].head(10)
    features["max_last_10"] = recent_10.max()
    features["min_last_10"] = recent_10.min()
    features["median_last_10"] = recent_10.median()
    features["range_last_10"] = features["max_last_10"] - features["min_last_10"]

    # Coefficient of variation (lower = more consistent)
    if features["season_avg"] > 0:
        features["cv_season"] = features["season_std"] / features["season_avg"]
    else:
        features["cv_season"] = 0.0
    avg_5 = features["avg_5"]
    std_5 = features["std_5"]
    features["cv_5"] = std_5 / max(avg_5, 0.1)

    # ---- Hit-rate features ----
    if line is not None and line > 0:
        # Dynamic hit rates relative to the actual betting line
        for window in [5, 10, 20]:
            subset = df["target_stat"].head(window) if len(df) >= window else df["target_stat"]
            features[f"hit_rate_line_{window}"] = (subset >= line).mean()
        # How the line compares to season avg (line is high/low relative to player)
        features["line_vs_season"] = line - features["season_avg"]
        features["line_vs_recent"] = line - recent_avg
    else:
        # Fallback: threshold-based hit rates using season avg percentages
        for threshold_pct in [0.8, 0.9, 1.0, 1.1, 1.2]:
            threshold = features["season_avg"] * threshold_pct
            features[f"hit_rate_{int(threshold_pct * 100)}"] = (
                (df["target_stat"].head(20) >= threshold).mean()
                if len(df) >= 5 else 0.5
            )
        features["line_vs_season"] = 0.0
        features["line_vs_recent"] = 0.0

    # ---- Usage rate proxy (FGA per minute) ----
    if "fga" in df.columns:
        recent_min = df["minutes"].head(10)
        recent_fga = df["fga"].head(10)
        total_min = recent_min.sum()
        if total_min > 0:
            features["usage_rate_10"] = recent_fga.sum() / total_min
        else:
            features["usage_rate_10"] = 0.0

        season_min = df["minutes"].sum()
        features["usage_rate_season"] = df["fga"].sum() / max(season_min, 1.0)
    else:
        features["usage_rate_10"] = 0.0
        features["usage_rate_season"] = 0.0

    # ---- Efficiency stats ----
    if "fga" in df.columns and df["fga"].head(10).sum() > 0:
        features["fg_pct_10"] = df["fgm"].head(10).sum() / max(df["fga"].head(10).sum(), 1)
    else:
        features["fg_pct_10"] = 0.0

    if "fta" in df.columns and df["fta"].head(10).sum() > 0:
        features["ft_pct_10"] = df["ftm"].head(10).sum() / max(df["fta"].head(10).sum(), 1)
    else:
        features["ft_pct_10"] = 0.0

    # ---- Opponent-adjusted feature (placeholder) ----
    # When opponent defensive ratings are available, this can be replaced
    # with an actual adjustment factor. For now, we include the raw matchup
    # delta so downstream models have the column present.
    features["opp_matchup_delta"] = features["vs_opponent_avg"] - features["season_avg"]

    # ---- Normalize select features ----
    # Z-score the recent average relative to the player's own season distribution
    if features["season_std"] > 0:
        features["recent_zscore"] = (recent_avg - features["season_avg"]) / features["season_std"]
        features["minutes_zscore"] = (
            (features["avg_minutes_5"] - features["avg_minutes_20"])
            / max(df["minutes"].std(), 0.1)
        )
    else:
        features["recent_zscore"] = 0.0
        features["minutes_zscore"] = 0.0

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
