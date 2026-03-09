"""SQLite connection management."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from sba.config import get_settings
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
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_connection() as conn:
        conn.executescript(SCHEMA_SQL)
