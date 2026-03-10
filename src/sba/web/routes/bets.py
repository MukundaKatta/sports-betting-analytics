"""Bet tracking, settling, deleting, export, tags, and notes endpoints."""

from __future__ import annotations

import csv
import io
import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from sba.data.db import get_connection
from sba.web.api import repo

logger = logging.getLogger(__name__)
router = APIRouter(tags=["bets"])


# ── Pydantic models ─────────────────────────────────────────────────

class BetResponse(BaseModel):
    id: int | None
    event_id: str
    market: str
    selection: str
    line: float | None
    odds_american: int
    odds_decimal: float | None = None
    model_probability: float | None = None
    expected_value: float | None = None
    kelly_fraction: float | None = None
    recommended_stake: float | None = None
    bookmaker: str
    status: str
    profit_loss: float
    placed_at: str | None


class BetSummaryResponse(BaseModel):
    total_bets: int
    wins: int
    losses: int
    pushes: int
    pending: int
    win_rate: float
    total_staked: float
    total_profit: float
    roi: float
    bets: list[BetResponse]


class TrackBetRequest(BaseModel):
    event_id: str
    market: str
    selection: str
    odds_american: int
    stake: float = 0
    line: float | None = None
    bookmaker: str = "manual"


class SettleBetRequest(BaseModel):
    status: str
    profit_loss: float


class AddTagRequest(BaseModel):
    tag: str


class AddNoteRequest(BaseModel):
    note: str


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("/bets", response_model=BetSummaryResponse)
def get_bets():
    """Get bet history and summary stats."""
    with get_connection() as conn:
        bets = repo.get_bet_history(conn)

    settled = [b for b in bets if b.status in ("won", "lost", "push")]
    pending = [b for b in bets if b.status == "pending"]
    wins = sum(1 for b in settled if b.status == "won")
    losses = sum(1 for b in settled if b.status == "lost")
    pushes = sum(1 for b in settled if b.status == "push")
    total_staked = sum(b.recommended_stake for b in settled)
    total_profit = sum(b.profit_loss for b in settled)
    roi = (total_profit / total_staked * 100) if total_staked > 0 else 0

    return BetSummaryResponse(
        total_bets=len(settled),
        wins=wins,
        losses=losses,
        pushes=pushes,
        pending=len(pending),
        win_rate=wins / max(len(settled), 1),
        total_staked=round(total_staked, 2),
        total_profit=round(total_profit, 2),
        roi=round(roi, 2),
        bets=[
            BetResponse(
                id=b.id, event_id=b.event_id, market=b.market,
                selection=b.selection, line=b.line,
                odds_american=b.odds_american, odds_decimal=b.odds_decimal,
                model_probability=b.model_probability,
                expected_value=b.expected_value,
                kelly_fraction=b.kelly_fraction,
                recommended_stake=b.recommended_stake,
                bookmaker=b.bookmaker, status=b.status,
                profit_loss=b.profit_loss,
                placed_at=b.placed_at.isoformat() if b.placed_at else None,
            )
            for b in bets
        ],
    )


@router.post("/bets/track")
def track_bet(req: TrackBetRequest):
    """Track a new bet."""
    from sba.models.domain import TrackedBet
    from sba.utils.odds_math import american_to_decimal

    bet = TrackedBet(
        event_id=req.event_id, market=req.market, selection=req.selection,
        line=req.line, odds_american=req.odds_american,
        odds_decimal=american_to_decimal(req.odds_american),
        model_probability=0, expected_value=0,
        kelly_fraction=0, recommended_stake=req.stake,
        bookmaker=req.bookmaker,
    )
    with get_connection() as conn:
        bet_id = repo.insert_bet(conn, bet)
    return {"id": bet_id, "status": "tracked"}


@router.put("/bets/{bet_id}/settle")
def settle_bet(bet_id: int, req: SettleBetRequest):
    """Settle a bet with result."""
    if req.status not in ("won", "lost", "push"):
        raise HTTPException(400, "Status must be 'won', 'lost', or 'push'")

    with get_connection() as conn:
        repo.update_bet_result(conn, bet_id, req.status, req.profit_loss)
    return {"id": bet_id, "status": req.status, "profit_loss": req.profit_loss}


@router.delete("/bets/{bet_id}")
def delete_bet(bet_id: int):
    """Delete a tracked bet."""
    with get_connection() as conn:
        conn.execute("DELETE FROM bets WHERE id = ?", (bet_id,))
    return {"id": bet_id, "deleted": True}


@router.get("/bets/export")
def export_bets_csv():
    """Export bet history as CSV file."""
    with get_connection() as conn:
        bets = repo.get_bet_history(conn)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID", "Date", "Event", "Market", "Selection", "Line",
        "Odds (American)", "Odds (Decimal)", "Stake", "Bookmaker",
        "Status", "P/L", "Model Prob", "EV", "Kelly %",
    ])
    for b in bets:
        writer.writerow([
            b.id,
            b.placed_at.isoformat() if b.placed_at else "",
            b.event_id, b.market, b.selection, b.line or "",
            b.odds_american, f"{b.odds_decimal:.3f}" if b.odds_decimal else "",
            f"{b.recommended_stake:.2f}" if b.recommended_stake else "", b.bookmaker,
            b.status, f"{b.profit_loss:.2f}",
            f"{b.model_probability:.4f}" if b.model_probability else "",
            f"{b.expected_value:.4f}" if b.expected_value else "",
            f"{b.kelly_fraction:.4f}" if b.kelly_fraction else "",
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=sba_bets_export.csv"},
    )


@router.get("/bets/export/json")
def export_bets_json():
    """Export bet history as JSON."""
    with get_connection() as conn:
        bets = repo.get_bet_history(conn)

    return [
        {
            "id": b.id,
            "date": b.placed_at.isoformat() if b.placed_at else None,
            "event_id": b.event_id,
            "market": b.market,
            "selection": b.selection,
            "line": b.line,
            "odds_american": b.odds_american,
            "odds_decimal": round(b.odds_decimal, 3) if b.odds_decimal else None,
            "stake": round(b.recommended_stake, 2) if b.recommended_stake else None,
            "bookmaker": b.bookmaker,
            "status": b.status,
            "profit_loss": round(b.profit_loss, 2),
            "model_probability": round(b.model_probability, 4) if b.model_probability else None,
            "expected_value": round(b.expected_value, 4) if b.expected_value else None,
            "kelly_fraction": round(b.kelly_fraction, 4) if b.kelly_fraction else None,
        }
        for b in bets
    ]


# ── Tags ─────────────────────────────────────────────────────────────

@router.post("/bets/{bet_id}/tags")
def add_bet_tag(bet_id: int, req: AddTagRequest):
    """Add a tag to a bet."""
    with get_connection() as conn:
        try:
            conn.execute(
                "INSERT INTO bet_tags (bet_id, tag) VALUES (?, ?)",
                (bet_id, req.tag),
            )
        except Exception:
            return {"status": "already_exists"}
    return {"bet_id": bet_id, "tag": req.tag, "status": "added"}


@router.get("/bets/{bet_id}/tags")
def get_bet_tags(bet_id: int):
    """Get all tags for a bet."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT tag FROM bet_tags WHERE bet_id = ?", (bet_id,)
        ).fetchall()
    return [r["tag"] for r in rows]


@router.delete("/bets/{bet_id}/tags/{tag}")
def remove_bet_tag(bet_id: int, tag: str):
    """Remove a tag from a bet."""
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM bet_tags WHERE bet_id = ? AND tag = ?", (bet_id, tag),
        )
    return {"bet_id": bet_id, "tag": tag, "status": "removed"}


# ── Notes ────────────────────────────────────────────────────────────

@router.post("/bets/{bet_id}/notes")
def add_bet_note(bet_id: int, req: AddNoteRequest):
    """Add a note to a bet."""
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO bet_notes (bet_id, note) VALUES (?, ?)",
            (bet_id, req.note),
        )
    return {"id": cursor.lastrowid, "bet_id": bet_id, "status": "added"}


@router.get("/bets/{bet_id}/notes")
def get_bet_notes(bet_id: int):
    """Get all notes for a bet."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM bet_notes WHERE bet_id = ? ORDER BY created_at DESC",
            (bet_id,),
        ).fetchall()
    return [
        {"id": r["id"], "note": r["note"], "created_at": r["created_at"]}
        for r in rows
    ]
