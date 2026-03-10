"""Backtesting engine for player prop predictions."""

from __future__ import annotations

import logging
from collections import defaultdict

import numpy as np
import pandas as pd

from sba.config import get_settings
from sba.data.db import get_connection, init_db
from sba.data.db.repository import Repository
from sba.models.domain import BacktestResult, PlayerGameLog
from sba.models.ml.features import (
    PROP_STAT_MAP,
    build_prop_features,
    get_target_stat,
)
from sba.models.ml.xgboost_props import PropPredictionModel
from sba.models.statistical.kelly import fractional_kelly

logger = logging.getLogger(__name__)

WARMUP_GAMES = 30
SIMULATED_ODDS_DECIMAL = 1.91  # standard -110 juice


class Backtester:
    """Walk-forward backtesting engine for player prop models."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.repo = Repository()
        init_db()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def backtest_player_props(
        self,
        player_id: int,
        prop_market: str = "player_points",
        line_pct: float = 1.0,
    ) -> BacktestResult | None:
        """Run a walk-forward backtest for a single player/market.

        For each game from index ``WARMUP_GAMES`` onward, trains a model on
        all prior games, predicts the stat value, and evaluates against the
        actual result.  A hypothetical line is set at ``line_pct`` of the
        running season average at that point.

        Args:
            player_id: Database player id.
            prop_market: One of the keys in :data:`PROP_STAT_MAP`.
            line_pct: Fraction of the running season average to use as the
                hypothetical betting line (1.0 = season average).

        Returns:
            A :class:`BacktestResult`, or ``None`` if there is insufficient
            data.
        """
        with get_connection() as conn:
            player_row = conn.execute(
                "SELECT name FROM players WHERE id = ?", (player_id,)
            ).fetchone()
            logs = self.repo.get_player_logs(conn, player_id)

        if len(logs) < WARMUP_GAMES + 5:
            logger.warning(
                "Not enough game logs for player %s (%d games)",
                player_id,
                len(logs),
            )
            return None

        player_name = player_row["name"] if player_row else str(player_id)

        # Sort chronologically (oldest first) for walk-forward
        sorted_logs = sorted(logs, key=lambda g: g.game_date)

        predictions: list[dict] = []

        for idx in range(WARMUP_GAMES, len(sorted_logs)):
            history = sorted_logs[:idx]  # all games before this one
            game = sorted_logs[idx]

            actual_value = get_target_stat(game, prop_market)

            # Compute running season average for the line
            history_values = [get_target_stat(g, prop_market) for g in history]
            season_avg = float(np.mean(history_values))
            line = season_avg * line_pct

            # Build features from history (reverse-chron as expected)
            history_rev = list(reversed(history))
            features_df = build_prop_features(
                history_rev,
                opponent=game.opponent,
                home_away=game.home_away,
                prop_market=prop_market,
                line=line,
            )
            if features_df.empty:
                continue

            # Train a fresh model on the history window
            X_train, y_train = self._build_training_window(
                history, prop_market
            )
            if X_train.empty or len(X_train) < 15:
                continue

            model = PropPredictionModel()
            model.train(X_train, y_train, line=line)

            predicted_value = model.predict_value(features_df)
            over_prob = model.predict_over_prob(features_df, line)

            went_over = actual_value > line

            predictions.append(
                {
                    "predicted_value": predicted_value,
                    "actual_value": actual_value,
                    "line": line,
                    "over_prob": over_prob,
                    "predicted_over": over_prob >= 0.5,
                    "actual_over": went_over,
                    "correct": (over_prob >= 0.5) == went_over,
                }
            )

        if not predictions:
            return None

        return self._compile_result(player_name, prop_market, predictions)

    def backtest_summary(self, results: list[BacktestResult]) -> dict:
        """Aggregate statistics across multiple backtest results."""
        if not results:
            return {}

        total_preds = sum(r.total_predictions for r in results)
        total_correct = sum(r.correct_predictions for r in results)
        total_bets = sum(r.total_bets for r in results)
        total_winning = sum(r.winning_bets for r in results)
        total_profit = sum(r.total_profit for r in results)

        # Weighted ROI
        total_wagered = sum(
            r.total_bets * 1.0 for r in results
        )  # unit bets

        return {
            "players": len(results),
            "total_predictions": total_preds,
            "overall_accuracy": total_correct / max(total_preds, 1),
            "total_bets": total_bets,
            "bet_win_rate": total_winning / max(total_bets, 1),
            "total_profit": total_profit,
            "avg_roi": np.mean([r.roi for r in results]) if results else 0.0,
            "best_player": max(results, key=lambda r: r.roi).player_name
            if results
            else "",
            "worst_player": min(results, key=lambda r: r.roi).player_name
            if results
            else "",
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_training_window(
        self,
        history: list[PlayerGameLog],
        prop_market: str,
    ) -> tuple[pd.DataFrame, pd.Series]:
        """Build (X, y) from a chronological list of game logs.

        Uses the same walk-forward logic as
        :func:`build_prop_training_data` but operates on an arbitrary
        sub-sequence so the outer loop can grow the window each step.
        """
        stat_col = PROP_STAT_MAP.get(prop_market, "points")
        X_rows: list[pd.Series] = []
        y_vals: list[float] = []

        start = max(15, len(history) - 60)  # cap window to keep speed up

        for i in range(start, len(history)):
            sub_history = history[:i][::-1]  # reverse-chron
            game = history[i]

            features_df = build_prop_features(
                sub_history,
                opponent=game.opponent,
                home_away=game.home_away,
                prop_market=prop_market,
            )
            if features_df.empty:
                continue

            target = get_target_stat(game, prop_market)
            X_rows.append(features_df.iloc[0])
            y_vals.append(target)

        if not X_rows:
            return pd.DataFrame(), pd.Series(dtype=float)

        return pd.DataFrame(X_rows), pd.Series(y_vals)

    def _compile_result(
        self,
        player_name: str,
        market: str,
        predictions: list[dict],
    ) -> BacktestResult:
        """Turn raw prediction dicts into a :class:`BacktestResult`."""
        total = len(predictions)
        correct = sum(1 for p in predictions if p["correct"])
        accuracy = correct / max(total, 1)

        # Simulated betting: only bet when model sees edge (prob >= 0.55)
        bankroll = self.settings.BANKROLL
        cumulative_profit = 0.0
        profit_curve: list[float] = []
        total_bets = 0
        winning_bets = 0
        total_wagered = 0.0

        for pred in predictions:
            over_prob = pred["over_prob"]
            under_prob = 1.0 - over_prob
            best_prob = max(over_prob, under_prob)
            bet_over = over_prob >= under_prob

            # Only bet when the model has a clear edge
            ev = (best_prob * (SIMULATED_ODDS_DECIMAL - 1)) - (1 - best_prob)
            if ev <= 0:
                profit_curve.append(cumulative_profit)
                continue

            kelly_frac = fractional_kelly(
                best_prob, SIMULATED_ODDS_DECIMAL, self.settings.KELLY_FRACTION
            )
            stake = bankroll * kelly_frac
            if stake <= 0:
                profit_curve.append(cumulative_profit)
                continue

            total_bets += 1
            total_wagered += stake

            won = (bet_over and pred["actual_over"]) or (
                not bet_over and not pred["actual_over"]
            )

            if won:
                profit = stake * (SIMULATED_ODDS_DECIMAL - 1)
                winning_bets += 1
            else:
                profit = -stake

            cumulative_profit += profit
            bankroll += profit
            bankroll = max(bankroll, 1.0)  # floor to avoid negative bankroll
            profit_curve.append(cumulative_profit)

        roi = (cumulative_profit / max(total_wagered, 1.0)) * 100.0

        # Calibration: bucket predicted probabilities and compare to actuals
        calibration = self._compute_calibration(predictions)

        return BacktestResult(
            player_name=player_name,
            market=market,
            total_predictions=total,
            correct_predictions=correct,
            accuracy=accuracy,
            total_bets=total_bets,
            winning_bets=winning_bets,
            roi=roi,
            total_profit=cumulative_profit,
            profit_curve=profit_curve,
            calibration=calibration,
        )

    @staticmethod
    def _compute_calibration(predictions: list[dict]) -> dict[str, float]:
        """Bucket predictions by predicted over-probability and compute
        the actual over hit rate in each bucket."""
        buckets: dict[str, list[bool]] = defaultdict(list)

        for pred in predictions:
            prob = pred["over_prob"]
            if prob < 0.3:
                key = "0-30%"
            elif prob < 0.4:
                key = "30-40%"
            elif prob < 0.5:
                key = "40-50%"
            elif prob < 0.6:
                key = "50-60%"
            elif prob < 0.7:
                key = "60-70%"
            else:
                key = "70-100%"
            buckets[key].append(pred["actual_over"])

        return {
            k: float(np.mean(v)) for k, v in sorted(buckets.items())
        }
