from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
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
    SHARP_BOOKS: list[str] = ["pinnacle", "circa"]

    # API rate limits
    ODDS_API_CREDIT_RESERVE: int = 50
    BALLDONTLIE_RATE_LIMIT: int = 30  # requests per minute

    # CORS — comma-separated origins, configurable for production deployments
    CORS_ORIGINS: str = "http://localhost:8000,http://127.0.0.1:8000"

    # Rate limiting — configurable via env
    RATE_LIMIT_MAX_REQUESTS: int = 120
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    # API authentication — set to enable key-based auth on /api/* endpoints
    # When empty, API is unauthenticated (development mode)
    API_KEY: str = ""

    @field_validator("KELLY_FRACTION")
    @classmethod
    def kelly_fraction_range(cls, v: float) -> float:
        if not 0 < v <= 1.0:
            raise ValueError("KELLY_FRACTION must be between 0 (exclusive) and 1.0 (inclusive)")
        return v

    @field_validator("BANKROLL")
    @classmethod
    def bankroll_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("BANKROLL must be positive")
        return v

    @field_validator("EV_THRESHOLD")
    @classmethod
    def ev_threshold_range(cls, v: float) -> float:
        if not 0 <= v < 1.0:
            raise ValueError("EV_THRESHOLD must be between 0 and 1.0")
        return v

    @field_validator("REFRESH_INTERVAL_SECONDS")
    @classmethod
    def refresh_interval_positive(cls, v: int) -> int:
        if v < 10:
            raise ValueError("REFRESH_INTERVAL_SECONDS must be at least 10")
        return v

    @field_validator("LOG_LEVEL")
    @classmethod
    def valid_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid:
            raise ValueError(f"LOG_LEVEL must be one of {valid}")
        return v.upper()


@lru_cache
def get_settings() -> Settings:
    return Settings()
