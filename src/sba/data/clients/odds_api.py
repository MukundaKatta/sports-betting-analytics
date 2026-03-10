"""The Odds API v4 client."""

from __future__ import annotations

from datetime import datetime

from sba.data.clients.base import BaseAPIClient
from sba.models.domain import BookmakerOdds, Event, EventOdds, Outcome, Sport
from sba.utils.odds_math import american_to_decimal, decimal_to_american


class OddsAPIClient(BaseAPIClient):
    BASE_URL = "https://api.the-odds-api.com/v4"

    def __init__(self, api_key: str):
        super().__init__(api_key=api_key, rate_limit=10, period=60.0)

    def _get_headers(self) -> dict:
        return {}

    def _params(self, **kwargs) -> dict:
        params = {"apiKey": self.api_key}
        params.update({k: v for k, v in kwargs.items() if v is not None})
        return params

    def get_sports(self) -> list[Sport]:
        data = self.fetch("/sports", self._params())
        return [Sport(key=s["key"], title=s["title"], active=s["active"]) for s in data]

    def get_events(self, sport: str) -> list[Event]:
        data = self.fetch(f"/sports/{sport}/events", self._params())
        return [self._parse_event(e, sport) for e in data]

    def get_odds(self, sport: str, regions: str = "us",
                 markets: str = "h2h", odds_format: str = "american") -> list[EventOdds]:
        params = self._params(regions=regions, markets=markets, oddsFormat=odds_format)
        data = self.fetch(f"/sports/{sport}/odds", params)
        return [self._parse_event_odds(e, sport) for e in data]

    def get_event_odds(self, sport: str, event_id: str,
                       markets: str = "player_points", regions: str = "us",
                       odds_format: str = "american") -> EventOdds | None:
        params = self._params(regions=regions, markets=markets, oddsFormat=odds_format)
        try:
            data = self.fetch(f"/sports/{sport}/events/{event_id}/odds", params)
            return self._parse_event_odds(data, sport)
        except Exception:
            return None

    def get_scores(self, sport: str, days_from: int = 1) -> list[Event]:
        params = self._params(daysFrom=days_from)
        data = self.fetch(f"/sports/{sport}/scores", params)
        results = []
        for s in data:
            event = self._parse_event(s, sport)
            event.completed = s.get("completed", False)
            scores = s.get("scores")
            if scores and event.completed:
                for score in scores:
                    if score["name"] == event.home_team:
                        event.home_score = int(score["score"]) if score["score"] else None
                    elif score["name"] == event.away_team:
                        event.away_score = int(score["score"]) if score["score"] else None
            results.append(event)
        return results

    def _parse_event(self, data: dict, sport: str) -> Event:
        return Event(
            id=data["id"],
            sport=sport,
            home_team=data["home_team"],
            away_team=data["away_team"],
            commence_time=datetime.fromisoformat(data["commence_time"].replace("Z", "+00:00")),
        )

    def _parse_event_odds(self, data: dict, sport: str) -> EventOdds:
        event = self._parse_event(data, sport)
        bookmakers = []
        for bm in data.get("bookmakers", []):
            for market_data in bm.get("markets", []):
                outcomes = []
                for o in market_data.get("outcomes", []):
                    price = o.get("price", 0)
                    point = o.get("point")
                    # We request oddsFormat="american", so prices are american integers.
                    # Fallback: if price looks like a decimal (between 1.0 and 50.0 exclusive
                    # and is a float with a fractional part), treat as decimal.
                    if isinstance(price, float) and 1.0 < price < 50.0 and price != int(price):
                        price_decimal = price
                        price_american = decimal_to_american(price)
                    else:
                        price_american = int(price)
                        price_decimal = american_to_decimal(price_american)
                    outcomes.append(Outcome(
                        name=o["name"],
                        price_american=price_american,
                        price_decimal=price_decimal,
                        point=point,
                    ))
                last_update = None
                if market_data.get("last_update"):
                    last_update = datetime.fromisoformat(
                        market_data["last_update"].replace("Z", "+00:00")
                    )
                bookmakers.append(BookmakerOdds(
                    bookmaker=bm["key"],
                    market=market_data["key"],
                    outcomes=outcomes,
                    last_update=last_update,
                ))
        return EventOdds(event=event, bookmakers=bookmakers)

    # Player prop market keys
    PROP_MARKETS = [
        "player_points", "player_rebounds", "player_assists",
        "player_threes", "player_blocks", "player_steals",
        "player_points_rebounds_assists", "player_points_rebounds",
        "player_points_assists",
    ]
