"""XGBoost model for player prop predictions."""

from __future__ import annotations

import logging
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, mean_absolute_error, mean_squared_error
from sklearn.model_selection import TimeSeriesSplit

logger = logging.getLogger(__name__)


class PropPredictionModel:
    """Dual model: regressor for stat value + classifier for over/under."""

    def __init__(self):
        self.regressor = None
        self.classifier = None
        self.feature_names: list[str] = []

    def train(self, X: pd.DataFrame, y: pd.Series,
              line: float | None = None) -> dict:
        """Train both regressor and classifier.

        Args:
            X: Feature matrix
            y: Target stat values (continuous)
            line: If provided, trains classifier on over/under this line
        """
        from xgboost import XGBClassifier, XGBRegressor

        self.feature_names = list(X.columns)

        # Handle NaN/inf
        X = X.fillna(0).replace([np.inf, -np.inf], 0)

        # Train regressor
        self.regressor = XGBRegressor(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
        )

        # Time series cross-validation
        tscv = TimeSeriesSplit(n_splits=min(5, len(X) // 10))
        cv_mae = []
        cv_rmse = []

        for train_idx, test_idx in tscv.split(X):
            X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
            y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]

            self.regressor.fit(X_train, y_train)
            preds = self.regressor.predict(X_test)

            cv_mae.append(mean_absolute_error(y_test, preds))
            cv_rmse.append(np.sqrt(mean_squared_error(y_test, preds)))

        # Final fit on all data
        self.regressor.fit(X, y)

        metrics = {
            "cv_mae": float(np.mean(cv_mae)),
            "cv_rmse": float(np.mean(cv_rmse)),
            "n_samples": len(X),
        }

        # Train classifier if line provided
        if line is not None:
            y_binary = (y > line).astype(int)
            if y_binary.sum() > 5 and (1 - y_binary).sum() > 5:
                self.classifier = XGBClassifier(
                    n_estimators=100,
                    max_depth=4,
                    learning_rate=0.1,
                    subsample=0.8,
                    random_state=42,
                )
                self.classifier.fit(X, y_binary)

                cv_acc = []
                for train_idx, test_idx in tscv.split(X):
                    X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
                    yb_train, yb_test = y_binary.iloc[train_idx], y_binary.iloc[test_idx]
                    self.classifier.fit(X_train, yb_train)
                    preds = self.classifier.predict(X_test)
                    cv_acc.append(accuracy_score(yb_test, preds))

                self.classifier.fit(X, y_binary)
                metrics["classifier_cv_accuracy"] = float(np.mean(cv_acc))

        return metrics

    def predict_value(self, X: pd.DataFrame) -> float:
        """Predict the stat value."""
        if self.regressor is None:
            raise RuntimeError("Model not trained")
        X = X.fillna(0).replace([np.inf, -np.inf], 0)
        return float(self.regressor.predict(X)[0])

    def predict_over_prob(self, X: pd.DataFrame, line: float) -> float:
        """Predict probability of going over the line."""
        X = X.fillna(0).replace([np.inf, -np.inf], 0)

        if self.classifier is not None:
            proba = self.classifier.predict_proba(X)[0]
            # Class 1 = over
            return float(proba[1]) if len(proba) > 1 else 0.5

        # Fallback: use regressor prediction + assumed normal distribution
        if self.regressor is not None:
            predicted = self.predict_value(X)
            # Rough estimate using typical prop variance
            std = max(abs(predicted) * 0.2, 1.0)
            z = (line - predicted) / std
            from sba.models.statistical.poisson import _normal_cdf
            return 1.0 - _normal_cdf(z)

        return 0.5

    def feature_importance(self) -> list[tuple[str, float]]:
        """Return top features by importance."""
        if self.regressor is None:
            return []
        importances = self.regressor.feature_importances_
        pairs = sorted(zip(self.feature_names, importances),
                       key=lambda x: x[1], reverse=True)
        return pairs[:10]

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({
            "regressor": self.regressor,
            "classifier": self.classifier,
            "feature_names": self.feature_names,
        }, path)

    def load(self, path: Path):
        data = joblib.load(path)
        self.regressor = data["regressor"]
        self.classifier = data.get("classifier")
        self.feature_names = data.get("feature_names", [])
