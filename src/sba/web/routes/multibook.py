"""Multi-book bankroll tracking & account limiting API endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(tags=["multibook"])


# ── Pydantic models ─────────────────────────────────────────────────

class BookBalanceRequest(BaseModel):
    sportsbook: str
    balance: float
    deposited: float | None = None
    withdrawn: float | None = None
    bonus_balance: float = 0.0
    notes: str = ""


class AccountLimitRequest(BaseModel):
    sportsbook: str
    limit_type: str = "none"
    severity: str = "none"
    max_stake: float | None = None
    notes: str = ""


# ── Multi-Book Bankroll Endpoints ───────────────────────────────────

@router.get("/multibook/balances")
def get_all_balances():
    """Get balances across all tracked sportsbooks."""
    from sba.services.multibook import get_all_balances
    return get_all_balances()


@router.post("/multibook/balances")
def upsert_balance(req: BookBalanceRequest):
    """Add or update a sportsbook balance."""
    from sba.services.multibook import upsert_balance
    return upsert_balance(
        sportsbook=req.sportsbook,
        balance=req.balance,
        deposited=req.deposited,
        withdrawn=req.withdrawn,
        bonus_balance=req.bonus_balance,
        notes=req.notes,
    )


@router.delete("/multibook/balances/{sportsbook}")
def delete_book(sportsbook: str):
    """Remove a sportsbook from tracking."""
    from sba.services.multibook import delete_book
    return delete_book(sportsbook)


@router.get("/multibook/history")
def get_balance_history(sportsbook: str | None = None, days: int = 90):
    """Get balance history for one or all books."""
    from sba.services.multibook import get_balance_history
    return get_balance_history(sportsbook, days)


# ── Account Limiting Endpoints ──────────────────────────────────────

@router.get("/account-limits")
def get_account_limits():
    """Get account limiting status for all sportsbooks."""
    from sba.services.account_limits import get_all_limits
    return get_all_limits()


@router.post("/account-limits")
def upsert_account_limit(req: AccountLimitRequest):
    """Add or update account limiting status."""
    from sba.services.account_limits import upsert_limit
    return upsert_limit(
        sportsbook=req.sportsbook,
        limit_type=req.limit_type,
        severity=req.severity,
        max_stake=req.max_stake,
        notes=req.notes,
    )


@router.delete("/account-limits/{sportsbook}")
def delete_account_limit(sportsbook: str):
    """Remove a limiting record."""
    from sba.services.account_limits import delete_limit
    return delete_limit(sportsbook)


@router.get("/account-limits/risk")
def get_limiting_risk():
    """Estimate limiting risk based on betting patterns."""
    from sba.services.account_limits import get_limiting_risk
    return get_limiting_risk()
