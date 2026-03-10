"""Server-Sent Events (SSE) and WebSocket endpoints for real-time odds streaming."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import AsyncGenerator

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from sba.data.db import get_connection

logger = logging.getLogger(__name__)

router = APIRouter()

# Track active WebSocket connections
_ws_connections: list[WebSocket] = []


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


# ── WebSocket Live Odds ─────────────────────────────────────────────

@router.websocket("/ws/odds")
async def websocket_odds(websocket: WebSocket):
    """WebSocket endpoint for real-time odds updates.

    Clients receive JSON messages with odds updates. Supports commands:
    - {"subscribe": "basketball_nba"} - filter by sport
    - {"interval": 15} - set update interval (5-120s)
    """
    await websocket.accept()
    _ws_connections.append(websocket)
    logger.info(f"WebSocket client connected ({len(_ws_connections)} active)")

    interval = 15.0
    sport_filter: str | None = None
    last_id: int | None = None

    try:
        # Background task to send updates
        async def send_updates():
            nonlocal last_id
            while True:
                try:
                    snapshots = _fetch_latest_odds()
                    if sport_filter:
                        snapshots = [s for s in snapshots if s.get("sport") == sport_filter]

                    if snapshots:
                        newest_id = snapshots[0].get("id")
                        if newest_id != last_id:
                            last_id = newest_id
                            await websocket.send_json({
                                "type": "odds_update",
                                "data": snapshots,
                                "ts": time.time(),
                                "count": len(snapshots),
                            })
                except WebSocketDisconnect:
                    break
                except Exception as exc:
                    logger.warning(f"WebSocket send error: {exc}")
                    break
                await asyncio.sleep(interval)

        send_task = asyncio.create_task(send_updates())

        # Listen for client commands
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_json(), timeout=interval * 2)
                if "subscribe" in data:
                    sport_filter = data["subscribe"] or None
                    await websocket.send_json({
                        "type": "subscribed",
                        "sport": sport_filter,
                    })
                if "interval" in data:
                    interval = max(5.0, min(120.0, float(data["interval"])))
                    await websocket.send_json({
                        "type": "interval_set",
                        "interval": interval,
                    })
            except asyncio.TimeoutError:
                continue
            except WebSocketDisconnect:
                break

    except WebSocketDisconnect:
        pass
    finally:
        send_task.cancel()
        if websocket in _ws_connections:
            _ws_connections.remove(websocket)
        logger.info(f"WebSocket client disconnected ({len(_ws_connections)} active)")
