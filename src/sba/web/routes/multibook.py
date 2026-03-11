"""Multi-book bankroll tracking & account limiting API endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from sba.web.errors import safe_endpoint

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

    def model_post_init(self, __context) -> None:
        from sba.web.errors import VALID_LIMIT_TYPES, VALID_SEVERITIES
        if self.limit_type not in VALID_LIMIT_TYPES:
            raise ValueError(f"limit_type must be one of: {sorted(VALID_LIMIT_TYPES)}")
        if self.severity not in VALID_SEVERITIES:
            raise ValueError(f"severity must be one of: {sorted(VALID_SEVERITIES)}")


# ── Multi-Book Bankroll Endpoints ───────────────────────────────────

@router.get("/multibook/balances")
@safe_endpoint
def get_all_balances():
    """Get balances across all tracked sportsbooks."""
    from sba.services.multibook import get_all_balances
    return get_all_balances()


@router.post("/multibook/balances")
@safe_endpoint
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
@safe_endpoint
def delete_book(sportsbook: str):
    """Remove a sportsbook from tracking."""
    from sba.services.multibook import delete_book
    return delete_book(sportsbook)


@router.get("/multibook/history")
@safe_endpoint
def get_balance_history(sportsbook: str | None = None, days: int = Query(90, ge=1, le=365)):
    """Get balance history for one or all books."""
    from sba.services.multibook import get_balance_history
    return get_balance_history(sportsbook, days)


# ── Account Limiting Endpoints ──────────────────────────────────────

@router.get("/account-limits")
@safe_endpoint
def get_account_limits():
    """Get account limiting status for all sportsbooks."""
    from sba.services.account_limits import get_all_limits
    return get_all_limits()


@router.post("/account-limits")
@safe_endpoint
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
@safe_endpoint
def delete_account_limit(sportsbook: str):
    """Remove a limiting record."""
    from sba.services.account_limits import delete_limit
    return delete_limit(sportsbook)


@router.get("/account-limits/risk")
@safe_endpoint
def get_limiting_risk():
    """Estimate limiting risk based on betting patterns."""
    from sba.services.account_limits import get_limiting_risk
    return get_limiting_risk()
