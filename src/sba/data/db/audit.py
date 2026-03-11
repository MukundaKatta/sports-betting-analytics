"""Audit logging for tracking data changes.

Records create, update, delete, and settle operations
with timestamps, affected entities, and change details.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def log_audit(conn, action: str, entity_type: str, entity_id: Any,
              details: dict | None = None, user: str = "system") -> None:
    """Record an audit log entry.

    Args:
        conn: SQLite connection.
        action: One of 'create', 'update', 'delete', 'settle'.
        entity_type: Type of entity (e.g., 'bet', 'event', 'notification_rule').
        entity_id: Primary key of the affected entity.
        details: Optional dict with change details (old/new values).
        user: User identifier (defaults to 'system').
    """
    conn.execute(
        """INSERT INTO audit_log (action, entity_type, entity_id, details, user, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (action, entity_type, str(entity_id),
         json.dumps(details or {}), user,
         datetime.now(timezone.utc).isoformat()),
    )


def get_audit_log(conn, entity_type: str | None = None,
                  entity_id: str | None = None,
                  limit: int = 100, offset: int = 0) -> list[dict]:
    """Query audit log entries with optional filters."""
    query = "SELECT * FROM audit_log WHERE 1=1"
    params: list = []

    if entity_type:
        query += " AND entity_type = ?"
        params.append(entity_type)
    if entity_id:
        query += " AND entity_id = ?"
        params.append(entity_id)

    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(query, params).fetchall()
    return [
        {
            "id": r["id"],
            "action": r["action"],
            "entity_type": r["entity_type"],
            "entity_id": r["entity_id"],
            "details": json.loads(r["details"]) if r["details"] else {},
            "user": r["user"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]
