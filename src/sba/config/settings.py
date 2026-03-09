from pathlib import Path
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="SBA_")

    ODDS_API_KEY: str = ""
    BALLDONTLIE_API_KEY: str = ""
    DB_PATH: Path = Path("data/sba.db")
    LOG_LEVEL: str = "INFO"
    DEFAULT_SPORT: str = "basketball_nba"
    DEFAULT_REGION: str = "us"
    REFRESH_INTERVAL_SECONDS: int = 300
    EV_THRESHOLD: float = 0.02
    KELLY_FRACTION: float = 0.25
    BANKROLL: float = 1000.0

    # Sharp bookmakers for consensus probability
    SHARP_BOOKS: List[str] = ["pinnacle", "circa"]

    # API rate limits
    ODDS_API_CREDIT_RESERVE: int = 50
    BALLDONTLIE_RATE_LIMIT: int = 30  # requests per minute


@lru_cache
def get_settings() -> Settings:
    return Settings()
