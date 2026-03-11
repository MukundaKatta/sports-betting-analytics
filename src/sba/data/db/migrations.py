"""Database schema versioning and migrations.

Tracks schema version in the database and applies incremental migrations
to bring older databases up to the current version without data loss.
"""

from __future__ import annotations

import logging
import sqlite3

from sba.config.constants import SCHEMA_VERSION

logger = logging.getLogger(__name__)


def get_schema_version(conn: sqlite3.Connection) -> int:
    """Get the current schema version from the database."""
    try:
        row = conn.execute(
            "SELECT value FROM schema_version ORDER BY version DESC LIMIT 1"
        ).fetchone()
        return int(row["value"]) if row else 0
    except sqlite3.OperationalError:
        # Table doesn't exist yet — this is a fresh database
        return 0


def _ensure_version_table(conn: sqlite3.Connection) -> None:
    """Create the schema_version table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            value INTEGER NOT NULL,
            applied_at TEXT DEFAULT CURRENT_TIMESTAMP,
            description TEXT DEFAULT ''
        )
    """)


def _set_schema_version(conn: sqlite3.Connection, version: int,
                        description: str = "") -> None:
    """Record a schema version upgrade."""
    conn.execute(
        "INSERT OR REPLACE INTO schema_version (version, value, description) VALUES (?, ?, ?)",
        (version, version, description),
    )


# ── Migration Functions ──────────────────────────────────────────────

def _migrate_v1(conn: sqlite3.Connection) -> None:
    """v1: Add audit_log table."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            details TEXT DEFAULT '{}',
            user TEXT DEFAULT 'system',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_entity
            ON audit_log(entity_type, entity_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_created
            ON audit_log(created_at)
    """)


def _migrate_v2(conn: sqlite3.Connection) -> None:
    """v2: Add webhook_deliveries table for retry tracking."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS webhook_deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_id INTEGER REFERENCES notification_rules(id),
            webhook_url TEXT NOT NULL,
            payload TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER DEFAULT 0,
            last_attempt_at TEXT,
            last_error TEXT DEFAULT '',
            response_code INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_webhook_status
            ON webhook_deliveries(status, created_at)
    """)


# ── Migration Registry ───────────────────────────────────────────────

MIGRATIONS: dict[int, tuple[callable, str]] = {
    1: (_migrate_v1, "Add audit_log table"),
    2: (_migrate_v2, "Add webhook_deliveries table"),
}


def run_migrations(conn: sqlite3.Connection) -> int:
    """Apply pending migrations to bring the database up to SCHEMA_VERSION.

    Returns the number of migrations applied.
    """
    _ensure_version_table(conn)
    current = get_schema_version(conn)

    if current >= SCHEMA_VERSION:
        return 0

    applied = 0
    for version in range(current + 1, SCHEMA_VERSION + 1):
        if version not in MIGRATIONS:
            logger.warning("Missing migration for version %d", version)
            continue

        migrate_fn, description = MIGRATIONS[version]
        logger.info("Applying migration v%d: %s", version, description)

        try:
            migrate_fn(conn)
            _set_schema_version(conn, version, description)
            applied += 1
            logger.info("Migration v%d applied successfully", version)
        except Exception:
            logger.error("Migration v%d failed", version, exc_info=True)
            raise

    return applied
