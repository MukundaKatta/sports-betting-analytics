"""Multi-book bankroll tracking service.

Tracks balances across multiple sportsbooks in a unified dashboard.
Addresses the #1 user pain point: bankroll fragmentation across 5-15 books.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sba.data.db import get_connection

logger = logging.getLogger(__name__)

# Well-known sportsbook metadata for deep links and display
SPORTSBOOK_INFO = {
    "draftkings": {
        "name": "DraftKings",
        "short": "DK",
        "color": "#53d337",
        "url": "https://sportsbook.draftkings.com",
    },
    "fanduel": {
        "name": "FanDuel",
        "short": "FD",
        "color": "#1493ff",
        "url": "https://sportsbook.fanduel.com",
    },
    "betmgm": {
        "name": "BetMGM",
        "short": "MGM",
        "color": "#c4a952",
        "url": "https://sports.betmgm.com",
    },
    "caesars": {
        "name": "Caesars",
        "short": "CZR",
        "color": "#00573f",
        "url": "https://www.caesars.com/sportsbook-and-casino",
    },
    "pointsbet": {
        "name": "PointsBet",
        "short": "PB",
        "color": "#e94560",
        "url": "https://pointsbet.com",
    },
    "betrivers": {
        "name": "BetRivers",
        "short": "BR",
        "color": "#ffc72c",
        "url": "https://www.betrivers.com",
    },
    "espnbet": {
        "name": "ESPN BET",
        "short": "ESPN",
        "color": "#cc0000",
        "url": "https://espnbet.com",
    },
    "fanatics": {
        "name": "Fanatics",
        "short": "FAN",
        "color": "#0053a0",
        "url": "https://sportsbook.fanatics.com",
    },
    "pinnacle": {
        "name": "Pinnacle",
        "short": "PIN",
        "color": "#e81f2e",
        "url": "https://www.pinnacle.com",
    },
    "circa": {
        "name": "Circa Sports",
        "short": "CIR",
        "color": "#d4af37",
        "url": "https://circasports.com",
    },
    "bovada": {
        "name": "Bovada",
        "short": "BOV",
        "color": "#cc2127",
        "url": "https://www.bovada.lv",
    },
    "bet365": {
        "name": "bet365",
        "short": "365",
        "color": "#027b5b",
        "url": "https://www.bet365.com",
    },
    "hard_rock": {
        "name": "Hard Rock Bet",
        "short": "HR",
        "color": "#ff6b00",
        "url": "https://www.hardrock.bet",
    },
    "fliff": {
        "name": "Fliff",
        "short": "FLF",
        "color": "#6c5ce7",
        "url": "https://www.getfliff.com",
    },
}


def get_all_balances() -> dict:
    """Get all sportsbook balances with aggregate stats."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM book_balances ORDER BY balance DESC"
        ).fetchall()

    books = []
    total_balance = 0.0
    total_deposited = 0.0
    total_withdrawn = 0.0
    limited_count = 0

    for r in rows:
        key = r["sportsbook"].lower().replace(" ", "_")
        info = SPORTSBOOK_INFO.get(key, {})
        balance = r["balance"]
        total_balance += balance
        total_deposited += r["deposited"]
        total_withdrawn += r["withdrawn"]
        if r["is_limited"]:
            limited_count += 1

        books.append({
            "id": r["id"],
            "sportsbook": r["sportsbook"],
            "display_name": info.get("name", r["sportsbook"]),
            "short": info.get("short", r["sportsbook"][:3].upper()),
            "color": info.get("color", "#888"),
            "balance": round(balance, 2),
            "bonus_balance": round(r["bonus_balance"], 2),
            "deposited": round(r["deposited"], 2),
            "withdrawn": round(r["withdrawn"], 2),
            "net_profit": round(balance + r["withdrawn"] - r["deposited"], 2),
            "roi_pct": round(
                (balance + r["withdrawn"] - r["deposited"]) / max(r["deposited"], 0.01) * 100, 2
            ),
            "is_limited": bool(r["is_limited"]),
            "notes": r["notes"],
            "updated_at": r["updated_at"],
        })

    total_profit = total_balance + total_withdrawn - total_deposited
    overall_roi = round(total_profit / max(total_deposited, 0.01) * 100, 2)

    return {
        "total_balance": round(total_balance, 2),
        "total_deposited": round(total_deposited, 2),
        "total_withdrawn": round(total_withdrawn, 2),
        "total_profit": round(total_profit, 2),
        "overall_roi": overall_roi,
        "book_count": len(books),
        "limited_count": limited_count,
        "books": books,
    }


def upsert_balance(sportsbook: str, balance: float,
                    deposited: float | None = None,
                    withdrawn: float | None = None,
                    bonus_balance: float = 0.0,
                    notes: str = "") -> dict:
    """Add or update a sportsbook balance."""
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT * FROM book_balances WHERE sportsbook = ?", (sportsbook,)
        ).fetchone()

        if existing:
            dep = deposited if deposited is not None else existing["deposited"]
            wd = withdrawn if withdrawn is not None else existing["withdrawn"]
            change = balance - existing["balance"]
            conn.execute(
                """UPDATE book_balances SET balance=?, deposited=?, withdrawn=?,
                   bonus_balance=?, notes=?, updated_at=CURRENT_TIMESTAMP
                   WHERE sportsbook=?""",
                (balance, dep, wd, bonus_balance, notes, sportsbook),
            )
        else:
            dep = deposited or 0.0
            wd = withdrawn or 0.0
            change = balance
            conn.execute(
                """INSERT INTO book_balances (sportsbook, balance, deposited, withdrawn,
                   bonus_balance, notes) VALUES (?, ?, ?, ?, ?, ?)""",
                (sportsbook, balance, dep, wd, bonus_balance, notes),
            )

        # Log history
        conn.execute(
            "INSERT INTO book_balance_history (sportsbook, balance, change, reason) VALUES (?,?,?,?)",
            (sportsbook, balance, change, "update"),
        )

    return {"sportsbook": sportsbook, "balance": balance, "status": "saved"}


def delete_book(sportsbook: str) -> dict:
    """Remove a sportsbook from tracking."""
    with get_connection() as conn:
        conn.execute("DELETE FROM book_balances WHERE sportsbook = ?", (sportsbook,))
        conn.execute("DELETE FROM book_balance_history WHERE sportsbook = ?", (sportsbook,))
    return {"sportsbook": sportsbook, "status": "deleted"}


def get_balance_history(sportsbook: str | None = None, days: int = 90) -> list[dict]:
    """Get balance history for a book or all books."""
    with get_connection() as conn:
        if sportsbook:
            rows = conn.execute(
                """SELECT * FROM book_balance_history
                   WHERE sportsbook = ? AND created_at >= datetime('now', ?)
                   ORDER BY created_at""",
                (sportsbook, f"-{days} days"),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT DATE(created_at) as day, SUM(balance) as total_balance
                   FROM (
                       SELECT sportsbook, balance, created_at,
                              ROW_NUMBER() OVER (PARTITION BY sportsbook, DATE(created_at)
                                                 ORDER BY created_at DESC) as rn
                       FROM book_balance_history
                       WHERE created_at >= datetime('now', ?)
                   ) sub WHERE rn = 1
                   GROUP BY DATE(created_at) ORDER BY day""",
                (f"-{days} days",),
            ).fetchall()

    return [dict(r) for r in rows]
