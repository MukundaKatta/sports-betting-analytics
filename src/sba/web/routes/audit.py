"""Audit log API endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter

from sba.data.db import get_connection
from sba.data.db.audit import get_audit_log
from sba.utils.sanitize import sanitize_pagination

logger = logging.getLogger(__name__)
router = APIRouter(tags=["audit"])


@router.get("/audit-log")
def list_audit_log(
    entity_type: str | None = None,
    entity_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    """Query the audit log with optional filters.

    Returns a list of audit entries showing create/update/delete/settle actions.
    """
    limit, offset = sanitize_pagination(limit, offset)

    with get_connection() as conn:
        entries = get_audit_log(conn, entity_type, entity_id, limit, offset)

    return {
        "entries": entries,
        "count": len(entries),
        "limit": limit,
        "offset": offset,
    }
