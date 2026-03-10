"""ML pipeline orchestrator: train, evaluate, predict."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from sba.config import get_settings
from sba.data.db import get_connection
from sba.data.db.repository import Repository
from sba.models.domain import Player, PlayerGameLog, PropPrediction
from sba.models.ml.features import build_prop_features, build_prop_training_data
from sba.models.ml.xgboost_props import PropPredictionModel

logger = logging.getLogger(__name__)


class MLPipeline:
    def __init__(self):
        self.settings = get_settings()
        self.repo = Repository()
        self._model_cache: dict[str, PropPredictionModel] = {}

    def train_prop_model(self, player_id: int, prop_market: str = "player_points") -> dict:
        """Train a prop prediction model for a specific player/market."""
        with get_connection() as conn:
            logs = self.repo.get_player_logs(conn, player_id)

        if len(logs) < 30:
            logger.warning(f"Not enough data for player {player_id}: {len(logs)} games")
            return {"error": "insufficient_data", "games": len(logs)}

        X, y = build_prop_training_data(logs, prop_market)
        if X.empty:
            return {"error": "feature_engineering_failed"}

        model = PropPredictionModel()
        metrics = model.train(X, y)

        # Save model
        version = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_dir = Path(self.settings.DB_PATH).parent / "models"
        model_path = model_dir / f"props_{prop_market}_{player_id}_{version}.joblib"
        model.save(model_path)

        with get_connection() as conn:
            self.repo.save_model_version(
                conn, f"props_{prop_market}", f"player_{player_id}",
                version, metrics, str(model_path),
            )

        logger.info(f"Trained prop model: {prop_market} for player {player_id}, MAE={metrics.get('cv_mae', 'N/A')}")
        return metrics

    def predict_prop(self, player_id: int, prop_market: str, line: float,
                     opponent: str = "", home_away: str = "") -> PropPrediction | None:
        """Generate a prop prediction for a player."""
        with get_connection() as conn:
            logs = self.repo.get_player_logs(conn, player_id)
            player_row = conn.execute("SELECT * FROM players WHERE id = ?", (player_id,)).fetchone()

        if len(logs) < 5:
            return None

        player = Player(
            id=player_id,
            name=player_row["name"] if player_row else str(player_id),
            team=player_row["team"] if player_row else "",
            position=player_row["position"] if player_row else "",
        )

        features = build_prop_features(logs, opponent, home_away, prop_market)
        if features.empty:
            return None

        # Try to load trained model, otherwise use features directly
        model = self._get_or_create_model(player_id, prop_market, logs)
        if model is None:
            return None

        predicted_value = model.predict_value(features)
        over_prob = model.predict_over_prob(features, line)
        under_prob = 1.0 - over_prob

        top_features = [f"{name}: {imp:.3f}" for name, imp in model.feature_importance()[:5]]

        return PropPrediction(
            player=player,
            market=prop_market,
            predicted_value=predicted_value,
            line=line,
            over_prob=over_prob,
            under_prob=under_prob,
            recommendation="OVER" if over_prob > 0.55 else "UNDER" if under_prob > 0.55 else "PASS",
            top_features=top_features,
        )

    def _get_or_create_model(self, player_id: int, prop_market: str,
                             logs: list[PlayerGameLog]) -> PropPredictionModel | None:
        """Load cached model or train a quick one."""
        cache_key = f"{prop_market}_{player_id}"

        if cache_key in self._model_cache:
            return self._model_cache[cache_key]

        # Try loading from DB
        with get_connection() as conn:
            model_info = self.repo.get_active_model(conn, f"props_{prop_market}", f"player_{player_id}")

        model = PropPredictionModel()

        if model_info:
            try:
                model.load(Path(model_info["file_path"]))
                self._model_cache[cache_key] = model
                return model
            except Exception:
                logger.warning(f"Failed to load model from {model_info['file_path']}, training new one")

        # Quick train
        if len(logs) < 25:
            return None

        X, y = build_prop_training_data(logs, prop_market)
        if X.empty:
            return None

        model.train(X, y)
        self._model_cache[cache_key] = model
        return model
