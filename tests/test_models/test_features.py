"""Tests for ML feature engineering."""

import pytest
import pandas as pd
from datetime import date

from sba.models.domain import PlayerGameLog
from sba.models.ml.features import (
    build_prop_features,
    build_prop_training_data,
    get_target_stat,
    _logs_to_df,
    PROP_STAT_MAP,
)


class TestLogsToDataFrame:
    def test_converts_logs_to_df(self, sample_game_logs):
        df = _logs_to_df(sample_game_logs)
        assert len(df) == 30
        assert "points" in df.columns
        assert "rebounds" in df.columns
        assert "game_date" in df.columns

    def test_empty_logs(self):
        df = _logs_to_df([])
        assert len(df) == 0

    def test_preserves_values(self):
        log = PlayerGameLog(
            player_id=1, game_date=date(2025, 1, 1),
            points=30, rebounds=10, assists=8,
        )
        df = _logs_to_df([log])
        assert df.iloc[0]["points"] == 30
        assert df.iloc[0]["rebounds"] == 10


class TestBuildPropFeatures:
    def test_returns_features_for_valid_data(self, sample_game_logs):
        features = build_prop_features(sample_game_logs, prop_market="player_points")
        assert not features.empty
        assert "avg_3" in features.columns
        assert "avg_5" in features.columns
        assert "season_avg" in features.columns
        assert "trend" in features.columns

    def test_returns_empty_for_insufficient_data(self):
        logs = [
            PlayerGameLog(player_id=1, game_date=date(2025, 1, i + 1), points=20)
            for i in range(4)
        ]
        features = build_prop_features(logs)
        assert features.empty

    def test_home_away_feature(self, sample_game_logs):
        features_home = build_prop_features(sample_game_logs, home_away="home")
        features_away = build_prop_features(sample_game_logs, home_away="away")
        assert features_home.iloc[0]["is_home"] == 1
        assert features_away.iloc[0]["is_home"] == 0

    def test_opponent_features(self, sample_game_logs):
        features = build_prop_features(sample_game_logs, opponent="Team0")
        assert "vs_opponent_avg" in features.columns
        assert "vs_opponent_games" in features.columns
        assert features.iloc[0]["vs_opponent_games"] > 0

    def test_combo_stat_market(self, sample_game_logs):
        features = build_prop_features(
            sample_game_logs, prop_market="player_points_rebounds_assists"
        )
        assert not features.empty

    def test_consistency_metrics(self, sample_game_logs):
        features = build_prop_features(sample_game_logs)
        assert "max_last_10" in features.columns
        assert "min_last_10" in features.columns
        assert "median_last_10" in features.columns

    def test_efficiency_stats(self, sample_game_logs):
        features = build_prop_features(sample_game_logs)
        assert "fg_pct_10" in features.columns
        assert 0 <= features.iloc[0]["fg_pct_10"] <= 1


class TestBuildTrainingData:
    def test_builds_training_set(self, sample_game_logs):
        X, y = build_prop_training_data(sample_game_logs)
        assert len(X) > 0
        assert len(X) == len(y)

    def test_insufficient_data(self):
        logs = [
            PlayerGameLog(player_id=1, game_date=date(2025, 1, i + 1), points=20)
            for i in range(10)
        ]
        X, y = build_prop_training_data(logs)
        assert X.empty

    def test_no_data_leakage(self, sample_game_logs):
        """Training features should only use data before the target game."""
        sorted_logs = sorted(sample_game_logs, key=lambda x: x.game_date)
        X, y = build_prop_training_data(sorted_logs)
        # With 30 games and start at index 20, we should have ~10 samples
        assert len(X) == 10


class TestGetTargetStat:
    def test_single_stat(self):
        log = PlayerGameLog(player_id=1, game_date=date(2025, 1, 1), points=30)
        assert get_target_stat(log, "player_points") == 30

    def test_combo_stat(self):
        log = PlayerGameLog(
            player_id=1, game_date=date(2025, 1, 1),
            points=30, rebounds=10, assists=8,
        )
        assert get_target_stat(log, "player_points_rebounds_assists") == 48


class TestPropStatMap:
    def test_all_markets_mapped(self):
        expected = [
            "player_points", "player_rebounds", "player_assists",
            "player_threes", "player_blocks", "player_steals",
        ]
        for market in expected:
            assert market in PROP_STAT_MAP
