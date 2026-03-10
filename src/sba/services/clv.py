"""CLV (Closing Line Value) tracking service.

CLV measures whether you beat the closing line -- the #1 metric serious
sports bettors use to evaluate long-term edge.
"""

from __future__ import annotations

from sba.data.db import get_connection


def american_to_decimal(american: int) -> float:
    """Convert American odds to decimal odds."""
    if american > 0:
        return 1.0 + american / 100.0
    else:
        return 1.0 + 100.0 / abs(american)


def decimal_to_implied(decimal_odds: float) -> float:
    """Convert decimal odds to implied probability (0-1)."""
    if decimal_odds <= 0:
        return 0.0
    return 1.0 / decimal_odds


def compute_clv(placed_decimal: float, closing_decimal: float) -> float:
    """Compute CLV as (closing_implied / placed_implied) - 1.

    A positive CLV means you beat the closing line.
    """
    placed_implied = decimal_to_implied(placed_decimal)
    closing_implied = decimal_to_implied(closing_decimal)
    if placed_implied == 0:
        return 0.0
    return (closing_implied / placed_implied) - 1.0


def record_clv(
    bet_id: int,
    closing_odds_american: int,
    best_closing_american: int | None = None,
) -> dict:
    """Record closing line value for a bet.

    Looks up the bet's placed odds, computes CLV, and stores the record.
    Returns the created clv_records row as a dict.
    """
    with get_connection() as conn:
        bet = conn.execute(
            "SELECT odds_american, odds_decimal FROM bets WHERE id = ?",
            (bet_id,),
        ).fetchone()
        if not bet:
            raise ValueError(f"Bet {bet_id} not found")

        placed_american = bet["odds_american"]
        placed_decimal = bet["odds_decimal"]
        closing_decimal = american_to_decimal(closing_odds_american)
        clv_placed = compute_clv(placed_decimal, closing_decimal)

        best_closing_decimal = None
        clv_best = None
        if best_closing_american is not None:
            best_closing_decimal = american_to_decimal(best_closing_american)
            clv_best = compute_clv(placed_decimal, best_closing_decimal)

        conn.execute(
            """
            INSERT INTO clv_records (
                bet_id, placed_odds_american, placed_odds_decimal,
                closing_odds_american, closing_odds_decimal,
                best_closing_odds_american, best_closing_odds_decimal,
                clv_placed, clv_best
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(bet_id) DO UPDATE SET
                closing_odds_american = excluded.closing_odds_american,
                closing_odds_decimal = excluded.closing_odds_decimal,
                best_closing_odds_american = excluded.best_closing_odds_american,
                best_closing_odds_decimal = excluded.best_closing_odds_decimal,
                clv_placed = excluded.clv_placed,
                clv_best = excluded.clv_best,
                recorded_at = datetime('now')
            """,
            (
                bet_id, placed_american, placed_decimal,
                closing_odds_american, closing_decimal,
                best_closing_american, best_closing_decimal,
                clv_placed, clv_best,
            ),
        )
        conn.commit()

    return {
        "bet_id": bet_id,
        "placed_odds_american": placed_american,
        "placed_odds_decimal": placed_decimal,
        "closing_odds_american": closing_odds_american,
        "closing_odds_decimal": closing_decimal,
        "best_closing_odds_american": best_closing_american,
        "best_closing_odds_decimal": best_closing_decimal,
        "clv_placed": round(clv_placed, 6),
        "clv_best": round(clv_best, 6) if clv_best is not None else None,
    }


def get_clv_summary() -> dict:
    """Return summary statistics for all CLV records.

    Returns dict with: total_bets, avg_clv_pct, positive_clv_pct,
    avg_clv_winners, avg_clv_losers, recent (last 20 records).
    """
    with get_connection() as conn:
        # Total bets with CLV
        total = conn.execute(
            "SELECT COUNT(*) AS cnt FROM clv_records WHERE clv_placed IS NOT NULL"
        ).fetchone()["cnt"]

        if total == 0:
            return {
                "total_bets": 0,
                "avg_clv_pct": 0.0,
                "positive_clv_pct": 0.0,
                "avg_clv_winners": 0.0,
                "avg_clv_losers": 0.0,
                "recent": [],
            }

        # Average CLV %
        avg_clv = conn.execute(
            "SELECT AVG(clv_placed) AS avg_clv FROM clv_records WHERE clv_placed IS NOT NULL"
        ).fetchone()["avg_clv"] or 0.0

        # Positive CLV %
        positive = conn.execute(
            "SELECT COUNT(*) AS cnt FROM clv_records WHERE clv_placed > 0"
        ).fetchone()["cnt"]
        positive_pct = (positive / total * 100.0) if total > 0 else 0.0

        # Average CLV for winners
        avg_winners = conn.execute(
            """
            SELECT AVG(c.clv_placed) AS avg_clv
            FROM clv_records c
            JOIN bets b ON b.id = c.bet_id
            WHERE b.status = 'won' AND c.clv_placed IS NOT NULL
            """
        ).fetchone()["avg_clv"] or 0.0

        # Average CLV for losers
        avg_losers = conn.execute(
            """
            SELECT AVG(c.clv_placed) AS avg_clv
            FROM clv_records c
            JOIN bets b ON b.id = c.bet_id
            WHERE b.status = 'lost' AND c.clv_placed IS NOT NULL
            """
        ).fetchone()["avg_clv"] or 0.0

        # Recent 20 records
        rows = conn.execute(
            """
            SELECT c.*, b.market, b.selection, b.status, b.profit_loss
            FROM clv_records c
            JOIN bets b ON b.id = c.bet_id
            ORDER BY c.recorded_at DESC
            LIMIT 20
            """
        ).fetchall()
        recent = [dict(r) for r in rows]

    return {
        "total_bets": total,
        "avg_clv_pct": round(avg_clv * 100.0, 2),
        "positive_clv_pct": round(positive_pct, 2),
        "avg_clv_winners": round(avg_winners * 100.0, 2),
        "avg_clv_losers": round(avg_losers * 100.0, 2),
        "recent": recent,
    }
