"""CLV (Closing Line Value) tracking and analysis endpoints.

Extracted from performance.py for maintainability.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, field_validator

from sba.data.db import get_connection, init_db
from sba.web.api import repo
from sba.web.errors import safe_endpoint

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
@safe_endpoint
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
@safe_endpoint
def clv_summary():
    """Get aggregate CLV stats across all tracked bets."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT cl.*, b.market, b.bookmaker, b.status, b.odds_american as placed_odds
            FROM closing_lines cl
            JOIN bets b ON cl.bet_id = b.id
            ORDER BY cl.captured_at DESC
            LIMIT 5000
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


# ── CLV Calculate (standalone) ───────────────────────────────────────


class CLVCalculateRequest(BaseModel):
    opening_odds: int
    closing_odds: int

    @field_validator("opening_odds", "closing_odds")
    @classmethod
    def non_zero(cls, v: int) -> int:
        if v == 0:
            raise ValueError("Odds cannot be zero")
        return v


@router.post("/clv/calculate")
@safe_endpoint
def clv_calculate(req: CLVCalculateRequest):
    """Calculate CLV between opening and closing odds."""
    from sba.services.clv_tracker import calculate_clv
    return calculate_clv(req.opening_odds, req.closing_odds)


@router.get("/clv/dashboard")
@safe_endpoint
def clv_dashboard():
    """CLV tracking dashboard with comprehensive metrics."""
    from sba.services.clv_tracker import analyze_clv_history, calculate_clv

    init_db()
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT cl.bet_id, b.odds_american AS opening_odds,
                   cl.closing_odds_american AS closing_odds,
                   b.market, b.bookmaker, b.placed_at
            FROM closing_lines cl
            LEFT JOIN bets b ON b.id = cl.bet_id
            ORDER BY b.placed_at
        """).fetchall()

    clv_records = []
    for r in rows:
        opening = r["opening_odds"] or -110
        closing = r["closing_odds"] or -110
        result = calculate_clv(opening, closing)
        result["market"] = r["market"] or "unknown"
        result["bookmaker"] = r["bookmaker"] or "unknown"
        result["bet_id"] = r["bet_id"]
        result["placed_at"] = r["placed_at"]
        clv_records.append(result)

    analysis = analyze_clv_history(clv_records)
    analysis["records"] = clv_records[-50:]
    return analysis


# ── Bonus Bet Conversion Tool ────────────────────────────────────────


class BonusBetRequest(BaseModel):
    bonus_amount: float
    conversion_pct: float = 70.0
    min_odds: int = 200

    @field_validator("bonus_amount")
    @classmethod
    def positive_amount(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Bonus amount must be positive")
        return v

    @field_validator("conversion_pct")
    @classmethod
    def valid_pct(cls, v: float) -> float:
        if v < 10 or v > 100:
            raise ValueError("Conversion percentage must be 10-100")
        return v


@router.post("/bonus/convert")
@safe_endpoint
def bonus_convert(req: BonusBetRequest):
    """Calculate optimal bonus bet conversion strategy."""
    bonus = req.bonus_amount
    target_pct = req.conversion_pct / 100

    strategies = []
    for odds in [200, 300, 400, 500, 600, 700]:
        decimal_odds = odds / 100 + 1
        free_bet_payout = (decimal_odds - 1) * bonus
        hedge_decimal = 1.909  # -110 hedge
        hedge_amount = free_bet_payout / (1 + hedge_decimal - 1)
        hedge_payout = hedge_amount * hedge_decimal
        guaranteed_profit = hedge_payout - hedge_amount
        conversion_rate = guaranteed_profit / bonus * 100

        strategies.append({
            "free_bet_odds": f"+{odds}",
            "free_bet_decimal": round(decimal_odds, 3),
            "free_bet_payout": round(free_bet_payout, 2),
            "hedge_amount": round(hedge_amount, 2),
            "hedge_odds": "-110",
            "guaranteed_profit": round(guaranteed_profit, 2),
            "conversion_rate": round(conversion_rate, 1),
        })

    risk_free_profit = bonus * target_pct
    best_strategy = max(strategies, key=lambda s: s["conversion_rate"])

    return {
        "bonus_amount": bonus,
        "target_conversion": req.conversion_pct,
        "strategies": strategies,
        "best_strategy": best_strategy,
        "risk_free_expected_value": round(risk_free_profit, 2),
        "tips": [
            "Always check terms — some bonuses have rollover requirements",
            "Use odds +300 to +500 for optimal free bet conversion",
            "Place hedge bets on a sharp book with tight lines",
            "Time your hedges close to game start for the best closing lines",
            "Track all bonus conversions to measure your actual conversion rate",
        ],
    }
