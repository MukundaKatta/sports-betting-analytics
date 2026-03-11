"""Reporting API routes.

Daily, weekly, and monthly performance reports with export capability.
"""

from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from sba.services.reporting import (
    export_bets,
    generate_daily_report,
    generate_monthly_report,
    generate_weekly_report,
)

router = APIRouter(tags=["reporting"])

_CSV_COLUMNS = [
    "id", "sport", "home_team", "away_team", "market", "selection", "line",
    "odds_american", "odds_decimal", "model_probability", "expected_value",
    "kelly_fraction", "recommended_stake", "bookmaker", "status",
    "profit_loss", "placed_at", "settled_at",
]


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
    fmt: str = Query("json", description="Export format: json or csv"),
    status: str = Query(None, description="Filter by status: won, lost, push, pending"),
    start_date: str = Query(None, description="Start date YYYY-MM-DD"),
    end_date: str = Query(None, description="End date YYYY-MM-DD"),
):
    """Export bet data with optional filters. Supports JSON and CSV formats."""
    data = export_bets(
        format=fmt,
        status=status,
        start_date=start_date,
        end_date=end_date,
    )

    if fmt == "csv":
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=_CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for bet in data.get("bets", []):
            writer.writerow(bet)
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=sba_bets_export.csv"},
        )

    return data
