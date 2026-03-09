"""Balldontlie API client for NBA player stats."""

from __future__ import annotations

from datetime import date

from sba.data.clients.base import BaseAPIClient
from sba.models.domain import Player, PlayerGameLog


class BallDontLieClient(BaseAPIClient):
    BASE_URL = "https://api.balldontlie.io/v1"

    def __init__(self, api_key: str = ""):
        super().__init__(api_key=api_key, rate_limit=30, period=60.0)

    def _get_headers(self) -> dict:
        if self.api_key:
            return {"Authorization": self.api_key}
        return {}

    def get_players(self, search: str = "", per_page: int = 25) -> list[Player]:
        params = {"per_page": per_page}
        if search:
            params["search"] = search
        data = self.fetch("/players", params)
        return [
            Player(
                id=p["id"],
                name=f"{p['first_name']} {p['last_name']}",
                team=p.get("team", {}).get("full_name", "") if isinstance(p.get("team"), dict) else "",
                position=p.get("position", ""),
            )
            for p in data.get("data", [])
        ]

    def get_player_stats(self, player_id: int, season: int) -> list[PlayerGameLog]:
        all_logs = []
        cursor = None

        while True:
            params = {
                "player_ids[]": player_id,
                "seasons[]": season,
                "per_page": 100,
            }
            if cursor:
                params["cursor"] = cursor

            data = self.fetch("/stats", params)
            for s in data.get("data", []):
                game = s.get("game", {})
                game_date_str = game.get("date", "")[:10]
                if not game_date_str:
                    continue

                home_id = game.get("home_team_id")
                player_team_id = s.get("team", {}).get("id") if isinstance(s.get("team"), dict) else None
                home_away = "home" if player_team_id == home_id else "away"

                opponent = ""
                if isinstance(s.get("team"), dict):
                    # Determine opponent from game data
                    if home_away == "home":
                        opponent = game.get("visitor_team_id", "")
                    else:
                        opponent = game.get("home_team_id", "")
                    opponent = str(opponent)

                all_logs.append(PlayerGameLog(
                    player_id=player_id,
                    game_date=date.fromisoformat(game_date_str),
                    opponent=opponent,
                    home_away=home_away,
                    minutes=_parse_minutes(s.get("min", "0")),
                    points=s.get("pts", 0) or 0,
                    rebounds=s.get("reb", 0) or 0,
                    assists=s.get("ast", 0) or 0,
                    threes=s.get("fg3m", 0) or 0,
                    steals=s.get("stl", 0) or 0,
                    blocks=s.get("blk", 0) or 0,
                    turnovers=s.get("turnover", 0) or 0,
                    fga=s.get("fga", 0) or 0,
                    fgm=s.get("fgm", 0) or 0,
                    fta=s.get("fta", 0) or 0,
                    ftm=s.get("ftm", 0) or 0,
                    plus_minus=0,
                ))

            meta = data.get("meta", {})
            cursor = meta.get("next_cursor")
            if not cursor:
                break

        return all_logs

    def get_season_averages(self, player_id: int, season: int) -> dict:
        data = self.fetch("/season_averages", {
            "player_ids[]": player_id,
            "season": season,
        })
        avgs = data.get("data", [])
        return avgs[0] if avgs else {}


def _parse_minutes(min_str) -> float:
    if not min_str:
        return 0.0
    if isinstance(min_str, (int, float)):
        return float(min_str)
    try:
        if ":" in str(min_str):
            parts = str(min_str).split(":")
            return float(parts[0]) + float(parts[1]) / 60.0
        return float(min_str)
    except (ValueError, IndexError):
        return 0.0
