"""Structured error handling for consistent API error responses."""

from __future__ import annotations

import logging
import sqlite3
from functools import wraps
from typing import Any

from fastapi import HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class APIError(Exception):
    """Base API error with structured response."""

    def __init__(self, message: str, status_code: int = 400, details: Any = None):
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(message)


class NotFoundError(APIError):
    def __init__(self, resource: str, identifier: str | int):
        super().__init__(
            message=f"{resource} '{identifier}' not found",
            status_code=404,
        )


class ValidationError(APIError):
    def __init__(self, message: str, details: Any = None):
        super().__init__(message=message, status_code=422, details=details)


class ServiceUnavailableError(APIError):
    """Raised when an external service (API, database) is unavailable."""
    def __init__(self, service: str, details: Any = None):
        super().__init__(
            message=f"{service} is temporarily unavailable",
            status_code=503,
            details=details,
        )


def api_error_response(exc: APIError) -> JSONResponse:
    """Convert APIError to a consistent JSON response."""
    content: dict[str, Any] = {"error": exc.message}
    if exc.details:
        content["details"] = exc.details
    return JSONResponse(status_code=exc.status_code, content=content)


def safe_endpoint(func):
    """Decorator that catches common exceptions and returns structured errors.

    Replaces bare `except Exception` blocks with typed error handling.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except APIError:
            raise
        except HTTPException:
            raise
        except sqlite3.IntegrityError as exc:
            logger.warning("Integrity error in %s: %s", func.__name__, exc)
            raise HTTPException(409, f"Conflict: {exc}") from exc
        except sqlite3.OperationalError as exc:
            logger.error("Database error in %s: %s", func.__name__, exc, exc_info=True)
            raise HTTPException(503, "Database temporarily unavailable") from exc
        except ValueError as exc:
            logger.warning("Validation error in %s: %s", func.__name__, exc)
            raise HTTPException(422, str(exc)) from exc
        except Exception as exc:
            logger.error("Unexpected error in %s: %s", func.__name__, exc, exc_info=True)
            raise HTTPException(500, "Internal server error") from exc

    return wrapper


def safe_async_endpoint(func):
    """Async version of safe_endpoint for async route handlers."""

    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except APIError:
            raise
        except HTTPException:
            raise
        except sqlite3.IntegrityError as exc:
            logger.warning("Integrity error in %s: %s", func.__name__, exc)
            raise HTTPException(409, f"Conflict: {exc}") from exc
        except sqlite3.OperationalError as exc:
            logger.error("Database error in %s: %s", func.__name__, exc, exc_info=True)
            raise HTTPException(503, "Database temporarily unavailable") from exc
        except ValueError as exc:
            logger.warning("Validation error in %s: %s", func.__name__, exc)
            raise HTTPException(422, str(exc)) from exc
        except Exception as exc:
            logger.error("Unexpected error in %s: %s", func.__name__, exc, exc_info=True)
            raise HTTPException(500, "Internal server error") from exc

    return wrapper


# ── Valid parameter values ───────────────────────────────────────────

VALID_SPORTS = {
    "basketball_nba", "basketball_ncaab", "basketball_wnba",
    "americanfootball_nfl", "americanfootball_ncaaf",
    "baseball_mlb", "icehockey_nhl",
    "soccer_epl", "soccer_usa_mls", "soccer_uefa_champs_league",
    "mma_mixed_martial_arts", "tennis_atp", "tennis_wta",
}

VALID_MARKETS = {
    "h2h", "spreads", "totals",
    "player_points", "player_rebounds", "player_assists",
    "player_threes", "player_blocks", "player_steals",
    "player_points_rebounds_assists", "player_doubles",
}

VALID_RULE_TYPES = {"ev_threshold", "arb_alert", "line_move", "clv_alert"}
VALID_LIMIT_TYPES = {"none", "stake_reduced", "partial", "promo_banned", "full", "closed"}
VALID_SEVERITIES = {"none", "low", "medium", "high", "banned"}
VALID_BET_STATUSES = {"won", "lost", "push"}


def validate_sport(sport: str | None) -> str | None:
    """Validate sport parameter, return None if empty/None."""
    if not sport:
        return None
    sport = sport.strip().lower()
    if sport not in VALID_SPORTS:
        raise HTTPException(400, f"Invalid sport '{sport}'. Valid: {sorted(VALID_SPORTS)}")
    return sport


def validate_markets(markets: str) -> list[str]:
    """Validate and split comma-separated market string."""
    market_list = [m.strip().lower() for m in markets.split(",") if m.strip()]
    invalid = [m for m in market_list if m not in VALID_MARKETS]
    if invalid:
        raise HTTPException(400, f"Invalid markets: {invalid}. Valid: {sorted(VALID_MARKETS)}")
    return market_list


def validate_min_ev(min_ev: float | None) -> float | None:
    """Validate min_ev is within reasonable bounds."""
    if min_ev is None:
        return None
    if not -1.0 <= min_ev <= 1.0:
        raise HTTPException(400, "min_ev must be between -1.0 and 1.0 (e.g., 0.03 for 3%)")
    return min_ev
