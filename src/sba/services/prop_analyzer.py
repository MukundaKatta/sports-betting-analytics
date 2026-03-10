"""Player prop value finder using ML predictions."""

from __future__ import annotations

import logging

from sba.config import get_settings
from sba.data.clients.odds_api import OddsAPIClient
from sba.data.db import get_connection, init_db
from sba.data.db.repository import Repository
from sba.models.domain import PropPrediction
from sba.models.ml.pipeline import MLPipeline
from sba.models.statistical.ev import calculate_ev

logger = logging.getLogger(__name__)


class PropAnalyzer:
    def __init__(self):
        self.settings = get_settings()
        self.odds_client = OddsAPIClient(self.settings.ODDS_API_KEY)
        self.repo = Repository()
        self.ml = MLPipeline()
        init_db()

    def analyze(self, sport: str | None = None,
                event_id: str | None = None,
                prop_markets: list[str] | None = None) -> list[PropPrediction]:
        """Analyze player props for upcoming games.

        Fetches prop odds, runs ML predictions, surfaces +EV props.
        """
        sport = sport or self.settings.DEFAULT_SPORT
        if prop_markets is None:
            prop_markets = ["player_points", "player_rebounds", "player_assists"]

        predictions = []

        if event_id:
            event_ids = [event_id]
        else:
            events = self.odds_client.get_events(sport)
            event_ids = [e.id for e in events[:5]]  # Limit to save API credits

        for eid in event_ids:
            for market in prop_markets:
                event_preds = self._analyze_event_props(sport, eid, market)
                predictions.extend(event_preds)

        # Filter to +EV and sort
        predictions = [p for p in predictions if p.over_ev > 0 or p.under_ev > 0]
        predictions.sort(key=lambda p: max(p.over_ev, p.under_ev), reverse=True)

        return predictions

    def player_profile(self, player_name: str) -> dict | None:
        """Get player stats summary and recent trends."""
        with get_connection() as conn:
            player = self.repo.get_player_by_name(conn, player_name)
            if not player:
                return None

            logs = self.repo.get_player_logs(conn, player.id, last_n=20)
            if not logs:
                return None

        from sba.models.ml.features import _logs_to_df

        df = _logs_to_df(logs)

        profile = {
            "player": player,
            "games": len(logs),
            "last_5": {
                "points": df["points"].head(5).mean(),
                "rebounds": df["rebounds"].head(5).mean(),
                "assists": df["assists"].head(5).mean(),
                "minutes": df["minutes"].head(5).mean(),
            },
            "last_20": {
                "points": df["points"].mean(),
                "rebounds": df["rebounds"].mean(),
                "assists": df["assists"].mean(),
                "minutes": df["minutes"].mean(),
            },
            "trends": {
                "points_trend": df["points"].head(5).mean() - df["points"].mean(),
                "rebounds_trend": df["rebounds"].head(5).mean() - df["rebounds"].mean(),
                "assists_trend": df["assists"].head(5).mean() - df["assists"].mean(),
            },
            "recent_games": logs[:10],
        }
        return profile

    def _analyze_event_props(self, sport: str, event_id: str,
                             market: str) -> list[PropPrediction]:
        """Analyze props for a single event/market combo."""
        event_odds = self.odds_client.get_event_odds(
            sport, event_id, markets=market
        )
        if not event_odds:
            return []

        predictions = []
        # Group outcomes by player
        player_odds: dict[str, dict] = {}

        for bm in event_odds.bookmakers:
            if bm.market != market:
                continue
            for outcome in bm.outcomes:
                name = outcome.name
                key = name.split(" ")[0] if " " in name else name
                player_odds.setdefault(key, {"over": [], "under": []})

                if "Over" in name or outcome.point is not None:
                    player_odds[key]["over"].append((bm.bookmaker, outcome))
                if "Under" in name:
                    player_odds[key]["under"].append((bm.bookmaker, outcome))

        for player_name, odds_data in player_odds.items():
            pred = self._predict_player_prop(player_name, market, odds_data)
            if pred:
                predictions.append(pred)

        return predictions

    def _predict_player_prop(self, player_name: str, market: str,
                             odds_data: dict) -> PropPrediction | None:
        """Generate prediction for a single player prop."""
        with get_connection() as conn:
            player = self.repo.get_player_by_name(conn, player_name)

        if not player:
            return None

        # Get the line from odds
        over_odds = odds_data.get("over", [])
        under_odds = odds_data.get("under", [])

        if not over_odds:
            return None

        # Best over/under odds
        best_over = max(over_odds, key=lambda x: x[1].price_decimal) if over_odds else None
        best_under = max(under_odds, key=lambda x: x[1].price_decimal) if under_odds else None

        line = best_over[1].point if best_over and best_over[1].point else None
        if line is None:
            return None

        # ML prediction
        pred = self.ml.predict_prop(player.id, market, line)
        if not pred:
            return None

        # Calculate EV against best available odds
        if best_over:
            pred.best_over_odds = best_over[1]
            pred.over_ev = calculate_ev(pred.over_prob, best_over[1].price_decimal)

        if best_under:
            pred.best_under_odds = best_under[1]
            pred.under_ev = calculate_ev(pred.under_prob, best_under[1].price_decimal)

        # Set recommendation
        if pred.over_ev > self.settings.EV_THRESHOLD:
            pred.recommendation = f"OVER {line}"
        elif pred.under_ev > self.settings.EV_THRESHOLD:
            pred.recommendation = f"UNDER {line}"
        else:
            pred.recommendation = "PASS"

        return pred
