"""Reporting API routes.

Daily, weekly, and monthly performance reports with export capability.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from sba.services.reporting import (
    export_bets,
    generate_daily_report,
    generate_monthly_report,
    generate_weekly_report,
)

router = APIRouter(tags=["reporting"])


@router.get("/reports/daily")
def api_daily_report(
    date: str = Query(None, description="Date in YYYY-MM-DD format (defaults to today)"),
):
    """Generate a comprehensive daily performance report."""
    return generate_daily_report(date)


@router.get("/reports/weekly")
def api_weekly_report(
    weeks_ago: int = Query(0, ge=0, le=52, description="0 = current week"),
):
    """Generate a weekly performance report."""
    return generate_weekly_report(weeks_ago)


@router.get("/reports/monthly")
def api_monthly_report(
    year: int = Query(None, ge=2020, le=2030),
    month: int = Query(None, ge=1, le=12),
):
    """Generate a monthly performance report."""
    return generate_monthly_report(year, month)


@router.get("/reports/export")
def api_export_bets(
    status: str = Query(None, description="Filter by status: won, lost, push, pending"),
    start_date: str = Query(None, description="Start date YYYY-MM-DD"),
    end_date: str = Query(None, description="End date YYYY-MM-DD"),
):
    """Export bet data with optional filters."""
    return export_bets(
        format="json",
        status=status,
        start_date=start_date,
        end_date=end_date,
    )
