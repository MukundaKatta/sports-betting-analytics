"""Situation splits and bet import API endpoints."""

from __future__ import annotations

import csv
import io
import json
import logging

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from sba.data.db import get_connection
from sba.web.api import repo

logger = logging.getLogger(__name__)
router = APIRouter(tags=["splits"])


# ── Situation Splits ────────────────────────────────────────────────

@router.get("/splits/{player_name}")
def get_player_splits(
    player_name: str,
    stat: str = Query("points"),
    line: float = Query(0.0),
):
    """Get situation splits for a player's stat performance."""
    from sba.services.situation_splits import get_situation_splits
    result = get_situation_splits(player_name, stat, line)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


# ── Bet Import ──────────────────────────────────────────────────────

class BetImportItem(BaseModel):
    date: str = ""
    event_id: str = ""
    market: str = ""
    selection: str = ""
    odds_american: int = 0
    stake: float = 0
    bookmaker: str = "import"
    status: str = "pending"
    profit_loss: float = 0


class BetImportRequest(BaseModel):
    bets: list[BetImportItem]


@router.post("/bets/import")
def import_bets(req: BetImportRequest):
    """Import bets from JSON payload."""
    from sba.models.domain import TrackedBet
    from sba.utils.odds_math import american_to_decimal

    imported = 0
    errors = []

    with get_connection() as conn:
        # Disable FK checks for imported bets (they won't have matching events)
        conn.execute("PRAGMA foreign_keys = OFF")
        for i, bet_data in enumerate(req.bets):
            try:
                if not bet_data.selection or bet_data.odds_american == 0:
                    errors.append(f"Row {i + 1}: Missing selection or odds")
                    continue

                odds_dec = american_to_decimal(bet_data.odds_american)
                bet = TrackedBet(
                    event_id=bet_data.event_id or f"import_{i}",
                    market=bet_data.market or "unknown",
                    selection=bet_data.selection,
                    line=None,
                    odds_american=bet_data.odds_american,
                    odds_decimal=odds_dec,
                    model_probability=0,
                    expected_value=0,
                    kelly_fraction=0,
                    recommended_stake=bet_data.stake,
                    bookmaker=bet_data.bookmaker or "import",
                    status=bet_data.status,
                    profit_loss=bet_data.profit_loss,
                )
                repo.insert_bet(conn, bet)

                # If bet has a result, update it
                if bet_data.status in ("won", "lost", "push"):
                    last_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                    repo.update_bet_result(conn, last_id, bet_data.status, bet_data.profit_loss)

                imported += 1
            except Exception as exc:
                errors.append(f"Row {i + 1}: {exc}")

    return {
        "imported": imported,
        "errors": errors,
        "total_submitted": len(req.bets),
    }


@router.post("/bets/import/csv")
async def import_bets_csv(file: UploadFile = File(...)):
    """Import bets from a CSV file.

    Expected columns: date, event_id, market, selection, odds_american, stake, bookmaker, status, profit_loss
    """
    from sba.models.domain import TrackedBet
    from sba.utils.odds_math import american_to_decimal

    content = await file.read()
    text = content.decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))

    imported = 0
    errors = []

    with get_connection() as conn:
        # Disable FK checks for imported bets (they won't have matching events)
        conn.execute("PRAGMA foreign_keys = OFF")
        for i, row in enumerate(reader):
            try:
                odds_am = int(row.get("odds_american", 0) or 0)
                if odds_am == 0:
                    errors.append(f"Row {i + 1}: Missing odds_american")
                    continue

                selection = row.get("selection", "").strip()
                if not selection:
                    errors.append(f"Row {i + 1}: Missing selection")
                    continue

                odds_dec = american_to_decimal(odds_am)
                stake = float(row.get("stake", 0) or 0)
                status = row.get("status", "pending").strip().lower()
                pnl = float(row.get("profit_loss", 0) or 0)

                bet = TrackedBet(
                    event_id=row.get("event_id", f"csv_import_{i}").strip(),
                    market=row.get("market", "unknown").strip(),
                    selection=selection,
                    line=None,
                    odds_american=odds_am,
                    odds_decimal=odds_dec,
                    model_probability=0,
                    expected_value=0,
                    kelly_fraction=0,
                    recommended_stake=stake,
                    bookmaker=row.get("bookmaker", "import").strip(),
                    status=status if status in ("pending", "won", "lost", "push") else "pending",
                    profit_loss=pnl,
                )
                repo.insert_bet(conn, bet)

                if status in ("won", "lost", "push"):
                    last_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                    repo.update_bet_result(conn, last_id, status, pnl)

                imported += 1
            except Exception as exc:
                errors.append(f"Row {i + 1}: {exc}")

    return {
        "imported": imported,
        "errors": errors,
        "filename": file.filename,
    }


# ── Confidence Calibration ──────────────────────────────────────────

@router.get("/analytics/calibration")
def get_calibration():
    """Get model prediction calibration data.

    Compares predicted probabilities against actual win rates
    to show how well-calibrated the model is.
    """
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT model_probability, status
            FROM bets
            WHERE status IN ('won', 'lost') AND model_probability > 0
            ORDER BY model_probability
        """).fetchall()

    if len(rows) < 5:
        return {
            "calibration": [],
            "total_bets": len(rows),
            "message": "Need at least 5 settled bets with model probabilities for calibration.",
        }

    # Bucket by predicted probability ranges
    buckets = {}
    for prob_min in range(0, 100, 10):
        prob_max = prob_min + 10
        bucket_key = f"{prob_min}-{prob_max}%"
        bucket_bets = [
            r for r in rows
            if prob_min / 100 <= r["model_probability"] < prob_max / 100
        ]
        if bucket_bets:
            wins = sum(1 for b in bucket_bets if b["status"] == "won")
            actual_rate = wins / len(bucket_bets)
            predicted_avg = sum(b["model_probability"] for b in bucket_bets) / len(bucket_bets)
            buckets[bucket_key] = {
                "range": bucket_key,
                "predicted_prob": round(predicted_avg * 100, 1),
                "actual_win_rate": round(actual_rate * 100, 1),
                "sample_size": len(bucket_bets),
                "deviation": round((actual_rate - predicted_avg) * 100, 1),
            }

    calibration_list = list(buckets.values())

    # Overall calibration score (lower is better, 0 = perfect)
    if calibration_list:
        weighted_error = sum(
            abs(c["deviation"]) * c["sample_size"]
            for c in calibration_list
        ) / sum(c["sample_size"] for c in calibration_list)
        calibration_score = round(100 - weighted_error, 1)
    else:
        calibration_score = 0

    # Brier Score: mean of (forecast - outcome)^2 — gold standard calibration metric
    brier_sum = sum(
        (r["model_probability"] - (1.0 if r["status"] == "won" else 0.0)) ** 2
        for r in rows
    )
    brier_score = round(brier_sum / len(rows), 4) if rows else None

    return {
        "calibration": calibration_list,
        "total_bets": len(rows),
        "calibration_score": max(0, calibration_score),
        "brier_score": brier_score,
        "interpretation": (
            "Excellent" if calibration_score >= 90 else
            "Good" if calibration_score >= 75 else
            "Fair" if calibration_score >= 60 else
            "Needs improvement"
        ),
    }
