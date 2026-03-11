"""SQLite connection management with transaction support and migrations."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from sba.config import get_settings
from sba.config.constants import DB_BUSY_TIMEOUT_MS, DB_CACHE_SIZE_KB, DB_CONNECTION_TIMEOUT
from sba.data.db.schema import SCHEMA_SQL


def _get_db_path() -> Path:
    settings = get_settings()
    path = settings.DB_PATH
    if not path.is_absolute():
        path = Path(__file__).parents[3] / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def get_connection():
    path = _get_db_path()
    conn = sqlite3.connect(str(path), timeout=DB_CONNECTION_TIMEOUT)
    conn.row_factory = sqlite3.Row
    # Performance pragmas
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(f"PRAGMA cache_size=-{DB_CACHE_SIZE_KB}")
    conn.execute(f"PRAGMA busy_timeout={DB_BUSY_TIMEOUT_MS}")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def atomic(conn):
    """Execute a block of operations as an atomic transaction.

    Use this for multi-table operations that must succeed or fail together.

    Usage:
        with get_connection() as conn:
            with atomic(conn):
                repo.insert_bet(conn, bet)
                repo.update_bankroll(conn, amount)
    """
    conn.execute("SAVEPOINT atomic_op")
    try:
        yield conn
        conn.execute("RELEASE SAVEPOINT atomic_op")
    except Exception:
        conn.execute("ROLLBACK TO SAVEPOINT atomic_op")
        raise


def init_db():
    with get_connection() as conn:
        conn.executescript(SCHEMA_SQL)
        # Run migrations for schema upgrades
        from sba.data.db.migrations import run_migrations
        run_migrations(conn)
