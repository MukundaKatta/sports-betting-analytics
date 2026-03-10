"""Server-Sent Events (SSE) endpoint for real-time odds streaming."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import AsyncGenerator

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from sba.data.db import get_connection

logger = logging.getLogger(__name__)

router = APIRouter()


def _fetch_latest_odds() -> list[dict]:
    """Fetch the most recent odds snapshots from the database."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT os.id, os.event_id, os.bookmaker, os.market,
                   os.outcome_name, os.outcome_point, os.price_american,
                   os.price_decimal, os.snapshot_time,
                   e.home_team, e.away_team, e.sport
            FROM odds_snapshots os
            JOIN events e ON e.id = os.event_id
            WHERE os.snapshot_time >= datetime('now', '-1 hour')
            ORDER BY os.snapshot_time DESC
            LIMIT 100
            """
        ).fetchall()
    return [dict(r) for r in rows]


async def _odds_event_generator(
    interval: float,
) -> AsyncGenerator[str, None]:
    """Yield SSE data events with latest odds, or heartbeat comments."""
    last_id: int | None = None
    try:
        while True:
            try:
                snapshots = _fetch_latest_odds()
                if snapshots:
                    newest_id = snapshots[0].get("id")
                    if newest_id != last_id:
                        last_id = newest_id
                        payload = json.dumps(
                            {"type": "odds_update", "data": snapshots, "ts": time.time()},
                            default=str,
                        )
                        yield f"data: {payload}\n\n"
                    else:
                        # No new data -- send heartbeat
                        yield f": heartbeat {time.time():.0f}\n\n"
                else:
                    yield f": heartbeat {time.time():.0f}\n\n"
            except Exception:
                logger.exception("Error in SSE odds generator")
                yield f": error {time.time():.0f}\n\n"

            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        logger.debug("SSE odds stream cancelled")
        return


@router.get("/stream/odds")
async def stream_odds(
    interval: float = Query(default=30.0, description="Poll interval in seconds"),
):
    """Stream real-time odds updates via Server-Sent Events."""
    # Clamp interval between 5 and 120 seconds
    clamped = max(5.0, min(120.0, interval))

    return StreamingResponse(
        _odds_event_generator(clamped),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
