"""CLV (Closing Line Value) tracking and analysis endpoints.

Extracted from performance.py for maintainability.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from sba.data.db import get_connection
from sba.web.api import repo

logger = logging.getLogger(__name__)
router = APIRouter(tags=["clv"])


class CLVRequest(BaseModel):
    bet_id: int
    closing_odds_american: int


class CLVRecordResponse(BaseModel):
    placed_odds: int
    closing_odds: int
    clv_american: int
    clv_percentage: float
    beat_closing: bool


class CLVEntry(BaseModel):
    bet_id: int
    placed_odds: int
    closing_odds: int
    clv_american: int
    clv_percentage: float
    market: str
    bookmaker: str
    status: str


class CLVSummaryResponse(BaseModel):
    total_tracked: int
    avg_clv: float
    beat_closing_pct: float
    clv_by_market: dict[str, float]
    clv_by_bookmaker: dict[str, float]
    entries: list[CLVEntry]


@router.post("/clv/record")
def record_closing_line(req: CLVRequest):
    """Record the closing line for a bet to calculate CLV."""
    from sba.services.sharp_money import calculate_clv
    from sba.utils.odds_math import american_to_decimal

    with get_connection() as conn:
        bet_row = conn.execute("SELECT odds_american FROM bets WHERE id = ?", (req.bet_id,)).fetchone()
        if not bet_row:
            raise HTTPException(404, "Bet not found")

        clv = calculate_clv(bet_row["odds_american"], req.closing_odds_american)
        closing_dec = american_to_decimal(req.closing_odds_american)

        conn.execute("""
            INSERT INTO closing_lines (bet_id, closing_odds_american, closing_odds_decimal,
                                       clv_american, clv_percentage)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(bet_id) DO UPDATE SET
                closing_odds_american=excluded.closing_odds_american,
                closing_odds_decimal=excluded.closing_odds_decimal,
                clv_american=excluded.clv_american,
                clv_percentage=excluded.clv_percentage,
                captured_at=CURRENT_TIMESTAMP
        """, (req.bet_id, req.closing_odds_american, round(closing_dec, 4),
              clv["clv_american"], clv["clv_percentage"]))

    return clv


@router.get("/clv/summary", response_model=CLVSummaryResponse)
def clv_summary():
    """Get aggregate CLV stats across all tracked bets."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT cl.*, b.market, b.bookmaker, b.status, b.odds_american as placed_odds
            FROM closing_lines cl
            JOIN bets b ON cl.bet_id = b.id
            ORDER BY cl.captured_at DESC
        """).fetchall()

    if not rows:
        return {
            "total_tracked": 0, "avg_clv": 0, "beat_closing_pct": 0,
            "clv_by_market": {}, "clv_by_bookmaker": {}, "entries": [],
        }

    entries = []
    by_market: dict[str, list] = {}
    by_book: dict[str, list] = {}

    for r in rows:
        entry = {
            "bet_id": r["bet_id"],
            "placed_odds": r["placed_odds"],
            "closing_odds": r["closing_odds_american"],
            "clv_american": r["clv_american"],
            "clv_percentage": r["clv_percentage"],
            "market": r["market"],
            "bookmaker": r["bookmaker"],
            "status": r["status"],
        }
        entries.append(entry)
        by_market.setdefault(r["market"], []).append(r["clv_percentage"])
        by_book.setdefault(r["bookmaker"], []).append(r["clv_percentage"])

    avg_clv = round(sum(r["clv_percentage"] for r in rows) / len(rows), 2)
    beat_pct = round(sum(1 for r in rows if r["clv_percentage"] > 0) / len(rows) * 100, 1)

    clv_by_market = {
        m: round(sum(vals) / len(vals), 2) for m, vals in by_market.items()
    }
    clv_by_book = {
        b: round(sum(vals) / len(vals), 2) for b, vals in by_book.items()
    }

    return {
        "total_tracked": len(rows),
        "avg_clv": avg_clv,
        "beat_closing_pct": beat_pct,
        "clv_by_market": clv_by_market,
        "clv_by_bookmaker": clv_by_book,
        "entries": entries[:50],
    }
