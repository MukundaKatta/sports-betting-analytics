"""Named constants extracted from magic numbers throughout the codebase.

Centralizes all numeric and string constants that were previously hardcoded.
"""

from __future__ import annotations

# ── EV Confidence Thresholds ─────────────────────────────────────────
EV_CONFIDENCE_HIGH = 0.08  # 8% EV or higher → high confidence
EV_CONFIDENCE_MEDIUM = 0.04  # 4% EV or higher → medium confidence

# ── ML Pipeline ──────────────────────────────────────────────────────
ML_MIN_TRAINING_SAMPLES = 30  # Minimum game logs for ML training
ML_MIN_FEATURE_GAMES = 5  # Minimum games to build features
ML_WARMUP_GAMES = 20  # Games before backtesting starts
ML_XGBOOST_N_ESTIMATORS = 100
ML_XGBOOST_MAX_DEPTH = 5
ML_XGBOOST_LEARNING_RATE = 0.1
ML_XGBOOST_SUBSAMPLE = 0.8
ML_XGBOOST_COLSAMPLE = 0.8

# ── Feature Engineering Windows ──────────────────────────────────────
ROLLING_WINDOWS = [3, 5, 10, 20]
ACTIVITY_WINDOW_7D = 7
ACTIVITY_WINDOW_14D = 14
THRESHOLD_PERCENTILES = [0.8, 0.9, 1.0, 1.1, 1.2]

# ── API Client ───────────────────────────────────────────────────────
HTTP_TIMEOUT_SECONDS = 30.0
MAX_RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY = 5  # seconds, multiplied by 2^attempt
RETRY_BACKOFF_MULTIPLIER = 2
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

# ── Database ─────────────────────────────────────────────────────────
DB_BUSY_TIMEOUT_MS = 5000
DB_CACHE_SIZE_KB = 8000  # 8MB page cache
DB_CONNECTION_TIMEOUT = 10  # seconds
SCHEMA_VERSION = 2  # Current schema version for migrations

# ── Cache ────────────────────────────────────────────────────────────
CACHE_MAX_ENTRIES = 1000
CACHE_DEFAULT_TTL = 30.0  # seconds
CACHE_SETTLED_BETS_TTL = 120.0  # seconds
CACHE_SPORTS_TTL = 300.0  # 5 minutes

# ── Rate Limiting ────────────────────────────────────────────────────
ODDS_API_RATE_LIMIT = 10  # requests per 60s
BALLDONTLIE_RATE_LIMIT = 30  # requests per 60s
MIN_API_CREDIT_RESERVE = 50

# ── Pagination ───────────────────────────────────────────────────────
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 500

# ── Webhook ──────────────────────────────────────────────────────────
WEBHOOK_TIMEOUT_SECONDS = 10
WEBHOOK_MAX_RETRIES = 3
WEBHOOK_RETRY_DELAYS = [1, 5, 15]  # seconds between retries

# ── Audit Logging ────────────────────────────────────────────────────
AUDIT_ACTION_CREATE = "create"
AUDIT_ACTION_UPDATE = "update"
AUDIT_ACTION_DELETE = "delete"
AUDIT_ACTION_SETTLE = "settle"

# ── Poisson Model ────────────────────────────────────────────────────
POISSON_NORMAL_THRESHOLD = 20  # Use normal approximation above this mean
POISSON_MAX_GOALS = 15  # Max goals to enumerate in exact Poisson

# ── Odds Formatting ──────────────────────────────────────────────────
EVEN_ODDS_DECIMAL = 2.0  # American odds sign change threshold
ODDS_PRECISION = 3  # Decimal places for odds display
