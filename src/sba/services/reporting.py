"""Reporting service — generate structured performance reports.

Produces session summaries, daily/weekly/monthly reports, and
exportable data snapshots for portfolio review.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from sba.data.db import get_connection

logger = logging.getLogger(__name__)


def generate_daily_report(report_date: str | None = None) -> dict:
    """Generate a comprehensive daily performance report."""
    target = report_date or date.today().isoformat()

    with get_connection() as conn:
        # Settled bets for this day
        bets = conn.execute("""
            SELECT b.id, b.market, b.selection, b.odds_american, b.status,
                   b.profit_loss, b.recommended_stake, b.bookmaker,
                   b.placed_at, e.sport, e.home_team, e.away_team
            FROM bets b
            LEFT JOIN events e ON e.id = b.event_id
            WHERE DATE(b.placed_at) = ?
            ORDER BY b.placed_at DESC
        """, (target,)).fetchall()

        # Summary stats
        stats = conn.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN status='won' THEN 1 ELSE 0 END) as wins,
                   SUM(CASE WHEN status='lost' THEN 1 ELSE 0 END) as losses,
                   SUM(CASE WHEN status='push' THEN 1 ELSE 0 END) as pushes,
                   SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) as pending,
                   ROUND(SUM(CASE WHEN status IN ('won','lost','push') THEN profit_loss ELSE 0 END), 2) as profit,
                   ROUND(SUM(CASE WHEN status IN ('won','lost','push') THEN ABS(recommended_stake) ELSE 0 END), 2) as staked
            FROM bets WHERE DATE(placed_at) = ?
        """, (target,)).fetchone()

        # By market breakdown
        by_market = conn.execute("""
            SELECT market,
                   COUNT(*) as bets,
                   SUM(CASE WHEN status='won' THEN 1 ELSE 0 END) as wins,
                   ROUND(SUM(profit_loss), 2) as profit
            FROM bets
            WHERE DATE(placed_at) = ? AND status IN ('won', 'lost', 'push')
            GROUP BY market ORDER BY profit DESC
        """, (target,)).fetchall()

        # By bookmaker
        by_book = conn.execute("""
            SELECT bookmaker,
                   COUNT(*) as bets,
                   ROUND(SUM(profit_loss), 2) as profit
            FROM bets
            WHERE DATE(placed_at) = ? AND status IN ('won', 'lost', 'push')
            GROUP BY bookmaker ORDER BY profit DESC
        """, (target,)).fetchall()

    total = stats["total"] or 0
    profit = stats["profit"] or 0
    staked = stats["staked"] or 0
    roi = round(profit / staked * 100, 1) if staked > 0 else 0

    return {
        "report_type": "daily",
        "date": target,
        "summary": {
            "total_bets": total,
            "wins": stats["wins"] or 0,
            "losses": stats["losses"] or 0,
            "pushes": stats["pushes"] or 0,
            "pending": stats["pending"] or 0,
            "profit": profit,
            "staked": staked,
            "roi": roi,
        },
        "by_market": [dict(r) for r in by_market],
        "by_bookmaker": [dict(r) for r in by_book],
        "bets": [dict(r) for r in bets],
    }


def generate_weekly_report(weeks_ago: int = 0) -> dict:
    """Generate a weekly performance report."""
    end_date = date.today() - timedelta(weeks=weeks_ago)
    start_date = end_date - timedelta(days=6)

    with get_connection() as conn:
        stats = conn.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN status='won' THEN 1 ELSE 0 END) as wins,
                   SUM(CASE WHEN status='lost' THEN 1 ELSE 0 END) as losses,
                   ROUND(SUM(profit_loss), 2) as profit,
                   ROUND(SUM(ABS(recommended_stake)), 2) as staked
            FROM bets
            WHERE status IN ('won', 'lost', 'push')
              AND DATE(placed_at) BETWEEN ? AND ?
        """, (start_date.isoformat(), end_date.isoformat())).fetchone()

        # Daily breakdown
        daily = conn.execute("""
            SELECT DATE(placed_at) as day,
                   COUNT(*) as bets,
                   SUM(CASE WHEN status='won' THEN 1 ELSE 0 END) as wins,
                   ROUND(SUM(profit_loss), 2) as profit
            FROM bets
            WHERE status IN ('won', 'lost', 'push')
              AND DATE(placed_at) BETWEEN ? AND ?
            GROUP BY DATE(placed_at) ORDER BY day
        """, (start_date.isoformat(), end_date.isoformat())).fetchall()

        # Best and worst day
        best_day = max(daily, key=lambda d: d["profit"]) if daily else None
        worst_day = min(daily, key=lambda d: d["profit"]) if daily else None

        # Top market
        top_market = conn.execute("""
            SELECT market, ROUND(SUM(profit_loss), 2) as profit, COUNT(*) as bets
            FROM bets
            WHERE status IN ('won', 'lost', 'push')
              AND DATE(placed_at) BETWEEN ? AND ?
            GROUP BY market ORDER BY profit DESC LIMIT 1
        """, (start_date.isoformat(), end_date.isoformat())).fetchone()

    total = stats["total"] or 0
    profit = stats["profit"] or 0
    staked = stats["staked"] or 0
    roi = round(profit / staked * 100, 1) if staked > 0 else 0

    return {
        "report_type": "weekly",
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "summary": {
            "total_bets": total,
            "wins": stats["wins"] or 0,
            "losses": stats["losses"] or 0,
            "profit": profit,
            "staked": staked,
            "roi": roi,
        },
        "daily_breakdown": [dict(d) for d in daily],
        "best_day": dict(best_day) if best_day else None,
        "worst_day": dict(worst_day) if worst_day else None,
        "top_market": dict(top_market) if top_market else None,
    }


def generate_monthly_report(year: int | None = None, month: int | None = None) -> dict:
    """Generate a monthly performance report."""
    today = date.today()
    y = year or today.year
    m = month or today.month

    start_date = date(y, m, 1)
    if m == 12:
        end_date = date(y + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = date(y, m + 1, 1) - timedelta(days=1)

    with get_connection() as conn:
        stats = conn.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN status='won' THEN 1 ELSE 0 END) as wins,
                   SUM(CASE WHEN status='lost' THEN 1 ELSE 0 END) as losses,
                   ROUND(SUM(profit_loss), 2) as profit,
                   ROUND(SUM(ABS(recommended_stake)), 2) as staked,
                   ROUND(AVG(odds_american), 0) as avg_odds
            FROM bets
            WHERE status IN ('won', 'lost', 'push')
              AND DATE(placed_at) BETWEEN ? AND ?
        """, (start_date.isoformat(), end_date.isoformat())).fetchone()

        # Weekly breakdown
        weekly = conn.execute("""
            SELECT strftime('%W', placed_at) as week,
                   COUNT(*) as bets,
                   ROUND(SUM(profit_loss), 2) as profit
            FROM bets
            WHERE status IN ('won', 'lost', 'push')
              AND DATE(placed_at) BETWEEN ? AND ?
            GROUP BY week ORDER BY week
        """, (start_date.isoformat(), end_date.isoformat())).fetchall()

        # By sport
        by_sport = conn.execute("""
            SELECT e.sport,
                   COUNT(*) as bets,
                   ROUND(SUM(b.profit_loss), 2) as profit,
                   ROUND(SUM(CASE WHEN b.status='won' THEN 1.0 ELSE 0.0 END) / COUNT(*) * 100, 1) as wr
            FROM bets b
            LEFT JOIN events e ON e.id = b.event_id
            WHERE b.status IN ('won', 'lost', 'push')
              AND DATE(b.placed_at) BETWEEN ? AND ?
            GROUP BY e.sport ORDER BY profit DESC
        """, (start_date.isoformat(), end_date.isoformat())).fetchall()

    total = stats["total"] or 0
    profit = stats["profit"] or 0
    staked = stats["staked"] or 0
    roi = round(profit / staked * 100, 1) if staked > 0 else 0

    return {
        "report_type": "monthly",
        "year": y,
        "month": m,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "summary": {
            "total_bets": total,
            "wins": stats["wins"] or 0,
            "losses": stats["losses"] or 0,
            "profit": profit,
            "staked": staked,
            "roi": roi,
            "avg_odds": int(stats["avg_odds"] or 0),
        },
        "weekly_breakdown": [dict(w) for w in weekly],
        "by_sport": [dict(s) for s in by_sport],
    }


def export_bets(format: str = "json", status: str | None = None,
                start_date: str | None = None, end_date: str | None = None) -> dict:
    """Export bet data with optional filters.

    Returns structured data ready for JSON or CSV serialization.
    """
    conditions = ["1=1"]
    params: list = []

    if status:
        conditions.append("b.status = ?")
        params.append(status)
    if start_date:
        conditions.append("DATE(b.placed_at) >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("DATE(b.placed_at) <= ?")
        params.append(end_date)

    where = " AND ".join(conditions)

    with get_connection() as conn:
        rows = conn.execute(f"""
            SELECT b.id, b.market, b.selection, b.line, b.odds_american,
                   b.odds_decimal, b.model_probability, b.expected_value,
                   b.kelly_fraction, b.recommended_stake, b.bookmaker,
                   b.status, b.profit_loss, b.placed_at, b.settled_at,
                   e.sport, e.home_team, e.away_team
            FROM bets b
            LEFT JOIN events e ON e.id = b.event_id
            WHERE {where}
            ORDER BY b.placed_at DESC
        """, params).fetchall()

    bets = [dict(r) for r in rows]

    # Summary
    settled = [b for b in bets if b["status"] in ("won", "lost", "push")]
    total_profit = sum(b["profit_loss"] or 0 for b in settled)
    total_staked = sum(abs(b["recommended_stake"] or 0) for b in settled)

    return {
        "format": format,
        "total_bets": len(bets),
        "filters": {
            "status": status,
            "start_date": start_date,
            "end_date": end_date,
        },
        "summary": {
            "profit": round(total_profit, 2),
            "staked": round(total_staked, 2),
            "roi": round(total_profit / total_staked * 100, 1) if total_staked > 0 else 0,
        },
        "bets": bets,
    }
