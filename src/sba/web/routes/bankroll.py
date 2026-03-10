"""Bankroll management (initialize, deposit, withdraw, daily) endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

from sba.config import get_settings
from sba.data.db import get_connection

logger = logging.getLogger(__name__)
router = APIRouter(tags=["bankroll"])


# ── Pydantic models ─────────────────────────────────────────────────

class BankrollActionRequest(BaseModel):
    amount: float
    reason: str = ""


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("/bankroll")
def get_bankroll():
    """Get bankroll history and current balance."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM bankroll_log ORDER BY created_at DESC LIMIT 200"
        ).fetchall()
    if not rows:
        settings = get_settings()
        return {
            "current_balance": settings.BANKROLL,
            "starting_balance": settings.BANKROLL,
            "total_deposited": settings.BANKROLL,
            "total_withdrawn": 0,
            "total_profit": 0,
            "roi_pct": 0,
            "history": [],
        }

    entries = [
        {
            "id": r["id"],
            "amount": r["amount"],
            "change": r["change"],
            "reason": r["reason"],
            "bet_id": r["bet_id"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]
    current = entries[0]["amount"]
    deposits = sum(e["change"] for e in entries if e["reason"] in ("deposit", "initial"))
    withdrawals = abs(sum(e["change"] for e in entries if e["reason"] == "withdrawal"))
    starting = entries[-1]["amount"] - entries[-1]["change"]
    total_profit = current - starting - deposits + withdrawals
    roi = round(total_profit / max(starting + deposits, 0.01) * 100, 2)

    return {
        "current_balance": round(current, 2),
        "starting_balance": round(starting, 2),
        "total_deposited": round(deposits, 2),
        "total_withdrawn": round(withdrawals, 2),
        "total_profit": round(total_profit, 2),
        "roi_pct": roi,
        "history": entries[:100],
    }


@router.post("/bankroll/deposit")
def bankroll_deposit(req: BankrollActionRequest):
    """Record a bankroll deposit."""
    with get_connection() as conn:
        last = conn.execute(
            "SELECT amount FROM bankroll_log ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        current = last["amount"] if last else get_settings().BANKROLL
        new_balance = current + req.amount
        conn.execute(
            "INSERT INTO bankroll_log (amount, change, reason) VALUES (?, ?, ?)",
            (round(new_balance, 2), round(req.amount, 2), req.reason or "deposit"),
        )
    return {"balance": round(new_balance, 2), "deposited": req.amount}


@router.post("/bankroll/withdraw")
def bankroll_withdraw(req: BankrollActionRequest):
    """Record a bankroll withdrawal."""
    with get_connection() as conn:
        last = conn.execute(
            "SELECT amount FROM bankroll_log ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        current = last["amount"] if last else get_settings().BANKROLL
        new_balance = current - req.amount
        conn.execute(
            "INSERT INTO bankroll_log (amount, change, reason) VALUES (?, ?, ?)",
            (round(new_balance, 2), round(-req.amount, 2), "withdrawal"),
        )
    return {"balance": round(new_balance, 2), "withdrawn": req.amount}


@router.post("/bankroll/initialize")
def bankroll_initialize(req: BankrollActionRequest):
    """Initialize bankroll tracking with a starting balance."""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO bankroll_log (amount, change, reason) VALUES (?, ?, ?)",
            (req.amount, req.amount, "initial"),
        )
    return {"balance": req.amount, "status": "initialized"}


@router.get("/bankroll/daily")
def bankroll_daily_pnl():
    """Get daily P&L summary from bankroll log."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT DATE(created_at) as day, SUM(change) as daily_change,
                   MAX(amount) as end_balance, COUNT(*) as transactions
            FROM bankroll_log
            GROUP BY DATE(created_at)
            ORDER BY day
        """).fetchall()
    return [
        {
            "date": r["day"],
            "daily_change": round(r["daily_change"], 2),
            "end_balance": round(r["end_balance"], 2),
            "transactions": r["transactions"],
        }
        for r in rows
    ]
