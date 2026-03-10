"""Responsible gambling service — behavioral monitoring, limits, and interventions.

Tracks session duration, loss velocity, deposit frequency, and betting patterns
to detect early signs of problem gambling. Provides configurable deposit limits,
loss limits, cooldown periods, and self-exclusion.

2026 regulatory trend: predictive analytics for problem gambling detection
is becoming mandatory in CO, MA, NJ, NC. This module implements those patterns.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from sba.data.db import get_connection

logger = logging.getLogger(__name__)


# ── Limit Management ────────────────────────────────────────────────

def get_limits() -> dict:
    """Return all configured responsible gambling limits."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM rg_limits ORDER BY limit_type"
        ).fetchall()
    return {r["limit_type"]: dict(r) for r in rows}


def set_limit(limit_type: str, amount: float, period: str = "daily") -> dict:
    """Set or update a responsible gambling limit.

    limit_type: 'deposit', 'loss', 'wager', 'session_minutes'
    period: 'daily', 'weekly', 'monthly'
    """
    valid_types = ("deposit", "loss", "wager", "session_minutes")
    valid_periods = ("daily", "weekly", "monthly")

    if limit_type not in valid_types:
        return {"error": f"Invalid limit type. Use: {valid_types}"}
    if period not in valid_periods:
        return {"error": f"Invalid period. Use: {valid_periods}"}
    if amount <= 0:
        return {"error": "Limit amount must be positive"}

    with get_connection() as conn:
        conn.execute("""
            INSERT INTO rg_limits (limit_type, amount, period, updated_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(limit_type, period) DO UPDATE SET
                amount = excluded.amount,
                updated_at = excluded.updated_at
        """, (limit_type, amount, period))

    return {"limit_type": limit_type, "amount": amount, "period": period, "status": "set"}


def remove_limit(limit_type: str, period: str = "daily") -> dict:
    """Remove a responsible gambling limit."""
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM rg_limits WHERE limit_type = ? AND period = ?",
            (limit_type, period),
        )
    return {"status": "removed", "limit_type": limit_type, "period": period}


# ── Limit Checking ──────────────────────────────────────────────────

def check_limits() -> dict:
    """Check current usage against all configured limits.

    Returns limit status with remaining allowance.
    """
    limits = get_limits()
    if not limits:
        return {"limits_configured": False, "checks": []}

    checks = []
    with get_connection() as conn:
        for key, lim in limits.items():
            limit_type = lim["limit_type"]
            period = lim["period"]
            amount = lim["amount"]

            date_filter = _period_to_date_filter(period)

            if limit_type == "deposit":
                used = _sum_deposits(conn, date_filter)
            elif limit_type == "loss":
                used = _sum_losses(conn, date_filter)
            elif limit_type == "wager":
                used = _sum_wagers(conn, date_filter)
            elif limit_type == "session_minutes":
                used = _sum_session_minutes(conn, date_filter)
            else:
                continue

            remaining = max(0, amount - used)
            pct_used = round(min(used / amount * 100, 100), 1) if amount > 0 else 0

            checks.append({
                "limit_type": limit_type,
                "period": period,
                "limit": amount,
                "used": round(used, 2),
                "remaining": round(remaining, 2),
                "pct_used": pct_used,
                "exceeded": used >= amount,
            })

    return {"limits_configured": True, "checks": checks}


def _period_to_date_filter(period: str) -> str:
    """Convert period name to SQLite date filter."""
    if period == "daily":
        return "DATE('now')"
    elif period == "weekly":
        return "DATE('now', '-7 days')"
    elif period == "monthly":
        return "DATE('now', '-30 days')"
    return "DATE('now')"


def _sum_deposits(conn, date_filter: str) -> float:
    row = conn.execute(f"""
        SELECT COALESCE(SUM(change), 0) as total
        FROM bankroll_log
        WHERE change > 0 AND reason = 'deposit'
          AND DATE(created_at) >= {date_filter}
    """).fetchone()
    return row["total"] if row else 0


def _sum_losses(conn, date_filter: str) -> float:
    row = conn.execute(f"""
        SELECT COALESCE(ABS(SUM(profit_loss)), 0) as total
        FROM bets
        WHERE status = 'lost'
          AND DATE(placed_at) >= {date_filter}
    """).fetchone()
    return row["total"] if row else 0


def _sum_wagers(conn, date_filter: str) -> float:
    row = conn.execute(f"""
        SELECT COALESCE(SUM(ABS(recommended_stake)), 0) as total
        FROM bets
        WHERE DATE(placed_at) >= {date_filter}
    """).fetchone()
    return row["total"] if row else 0


def _sum_session_minutes(conn, date_filter: str) -> float:
    row = conn.execute(f"""
        SELECT COALESCE(SUM(duration_minutes), 0) as total
        FROM rg_sessions
        WHERE DATE(started_at) >= {date_filter}
    """).fetchone()
    return row["total"] if row else 0


# ── Session Tracking ────────────────────────────────────────────────

def start_session() -> dict:
    """Start a new betting session for time tracking."""
    with get_connection() as conn:
        # Close any unclosed sessions
        conn.execute("""
            UPDATE rg_sessions SET ended_at = datetime('now'),
                   duration_minutes = ROUND(
                       (JULIANDAY(datetime('now')) - JULIANDAY(started_at)) * 1440
                   )
            WHERE ended_at IS NULL
        """)
        cursor = conn.execute(
            "INSERT INTO rg_sessions (started_at) VALUES (datetime('now'))"
        )
        session_id = cursor.lastrowid

    return {"session_id": session_id, "started_at": datetime.now().isoformat()}


def end_session() -> dict:
    """End the current betting session."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, started_at FROM rg_sessions WHERE ended_at IS NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not row:
            return {"error": "No active session found"}

        conn.execute("""
            UPDATE rg_sessions SET ended_at = datetime('now'),
                   duration_minutes = ROUND(
                       (JULIANDAY(datetime('now')) - JULIANDAY(started_at)) * 1440
                   )
            WHERE id = ?
        """, (row["id"],))

    return {"session_id": row["id"], "status": "ended"}


def get_session_stats() -> dict:
    """Get session history and statistics."""
    with get_connection() as conn:
        # Today's sessions
        today_rows = conn.execute("""
            SELECT COUNT(*) as sessions,
                   COALESCE(SUM(duration_minutes), 0) as total_minutes,
                   COALESCE(MAX(duration_minutes), 0) as longest
            FROM rg_sessions
            WHERE DATE(started_at) = DATE('now') AND ended_at IS NOT NULL
        """).fetchone()

        # Week's sessions
        week_rows = conn.execute("""
            SELECT COUNT(*) as sessions,
                   COALESCE(SUM(duration_minutes), 0) as total_minutes,
                   COALESCE(AVG(duration_minutes), 0) as avg_minutes
            FROM rg_sessions
            WHERE started_at >= DATE('now', '-7 days') AND ended_at IS NOT NULL
        """).fetchone()

        # Active session
        active = conn.execute(
            "SELECT id, started_at FROM rg_sessions WHERE ended_at IS NULL LIMIT 1"
        ).fetchone()

    return {
        "active_session": {
            "id": active["id"],
            "started_at": active["started_at"],
        } if active else None,
        "today": {
            "sessions": today_rows["sessions"],
            "total_minutes": round(today_rows["total_minutes"], 1),
            "longest_minutes": round(today_rows["longest"], 1),
        },
        "week": {
            "sessions": week_rows["sessions"],
            "total_minutes": round(week_rows["total_minutes"], 1),
            "avg_minutes": round(week_rows["avg_minutes"], 1),
        },
    }


# ── Behavioral Analysis ────────────────────────────────────────────

def get_behavioral_report() -> dict:
    """Analyze betting behavior for problem gambling indicators.

    Checks: chasing losses, increasing stakes after losses, late-night betting,
    deposit frequency spikes, loss velocity.
    """
    with get_connection() as conn:
        # Recent bets for pattern analysis
        recent = conn.execute("""
            SELECT status, profit_loss, recommended_stake, odds_american,
                   placed_at, bookmaker
            FROM bets WHERE placed_at >= DATE('now', '-30 days')
            ORDER BY placed_at DESC
        """).fetchall()

        # Deposits last 30 days
        deposits = conn.execute("""
            SELECT change, created_at FROM bankroll_log
            WHERE change > 0 AND reason = 'deposit'
              AND created_at >= DATE('now', '-30 days')
            ORDER BY created_at DESC
        """).fetchall()

    if not recent:
        return {
            "risk_level": "low",
            "score": 0,
            "indicators": [],
            "recommendations": ["Not enough data for behavioral analysis"],
        }

    indicators = []
    risk_score = 0

    # 1. Chasing losses: increasing stakes after consecutive losses
    chase_count = 0
    for i in range(1, min(20, len(recent))):
        if (recent[i]["status"] == "lost" and
                recent[i - 1]["status"] != "won" and
                (recent[i - 1]["recommended_stake"] or 0) >
                (recent[i]["recommended_stake"] or 0) * 1.3):
            chase_count += 1
    if chase_count >= 3:
        indicators.append({
            "type": "chasing_losses",
            "severity": "high",
            "detail": f"Increased stakes after losses {chase_count} times in recent bets",
        })
        risk_score += 30

    # 2. Loss velocity: losing too fast
    last_7 = [r for r in recent if r["placed_at"] and r["placed_at"] >= (
        datetime.now() - timedelta(days=7)).isoformat()]
    week_losses = sum(abs(r["profit_loss"] or 0) for r in last_7 if r["status"] == "lost")
    prev_7 = [r for r in recent if r["placed_at"] and
              (datetime.now() - timedelta(days=14)).isoformat() <= r["placed_at"] <
              (datetime.now() - timedelta(days=7)).isoformat()]
    prev_losses = sum(abs(r["profit_loss"] or 0) for r in prev_7 if r["status"] == "lost")

    if prev_losses > 0 and week_losses > prev_losses * 2:
        indicators.append({
            "type": "loss_acceleration",
            "severity": "medium",
            "detail": f"Losses doubled: ${week_losses:.0f} this week vs ${prev_losses:.0f} last week",
        })
        risk_score += 20

    # 3. Bet frequency spike
    today_count = sum(1 for r in recent if r["placed_at"] and
                      r["placed_at"][:10] == date.today().isoformat())
    avg_daily = len(recent) / 30
    if avg_daily > 0 and today_count > avg_daily * 3:
        indicators.append({
            "type": "frequency_spike",
            "severity": "medium",
            "detail": f"{today_count} bets today vs {avg_daily:.1f} daily average",
        })
        risk_score += 15

    # 4. Deposit frequency
    if len(deposits) >= 5:
        # More than 5 deposits in 30 days
        indicators.append({
            "type": "frequent_deposits",
            "severity": "medium",
            "detail": f"{len(deposits)} deposits in the last 30 days",
        })
        risk_score += 15

    # 5. Longshot chasing: increasingly risky odds
    settled = [r for r in recent if r["status"] in ("won", "lost")]
    if len(settled) >= 10:
        recent_odds = [abs(r["odds_american"] or 0) for r in settled[:5]]
        older_odds = [abs(r["odds_american"] or 0) for r in settled[5:10]]
        avg_recent = sum(recent_odds) / len(recent_odds) if recent_odds else 0
        avg_older = sum(older_odds) / len(older_odds) if older_odds else 0
        if avg_recent > avg_older * 1.5 and avg_recent > 200:
            indicators.append({
                "type": "longshot_chasing",
                "severity": "medium",
                "detail": f"Average odds shifting to longshots: {avg_recent:.0f} vs {avg_older:.0f}",
            })
            risk_score += 15

    # Determine risk level
    if risk_score >= 60:
        risk_level = "high"
        recommendations = [
            "Consider taking a break from betting",
            "Review and lower your loss limits",
            "Consider self-exclusion if this continues",
        ]
    elif risk_score >= 30:
        risk_level = "moderate"
        recommendations = [
            "Review your staking strategy",
            "Consider setting tighter loss limits",
            "Take a 24-hour break if on a losing streak",
        ]
    else:
        risk_level = "low"
        recommendations = [
            "Betting patterns appear healthy",
            "Continue following your staking plan",
        ]

    return {
        "risk_level": risk_level,
        "score": min(risk_score, 100),
        "indicators": indicators,
        "recommendations": recommendations,
        "stats": {
            "bets_last_30d": len(recent),
            "deposits_last_30d": len(deposits),
            "losses_this_week": round(week_losses, 2),
        },
    }


# ── Self-Exclusion ──────────────────────────────────────────────────

def set_cooldown(hours: int) -> dict:
    """Set a mandatory cooldown period. Cannot bet until it expires."""
    if hours < 1 or hours > 8760:  # max 1 year
        return {"error": "Cooldown must be between 1 and 8760 hours"}

    with get_connection() as conn:
        conn.execute("""
            INSERT INTO rg_limits (limit_type, amount, period, updated_at)
            VALUES ('cooldown', ?, 'daily', datetime('now'))
            ON CONFLICT(limit_type, period) DO UPDATE SET
                amount = excluded.amount,
                updated_at = excluded.updated_at
        """, (hours,))

    expires_at = datetime.now() + timedelta(hours=hours)
    return {
        "status": "cooldown_set",
        "hours": hours,
        "expires_at": expires_at.isoformat(),
    }


def check_cooldown() -> dict:
    """Check if a cooldown is currently active."""
    with get_connection() as conn:
        row = conn.execute("""
            SELECT amount, updated_at FROM rg_limits
            WHERE limit_type = 'cooldown'
            ORDER BY updated_at DESC LIMIT 1
        """).fetchone()

    if not row:
        return {"active": False}

    hours = row["amount"]
    set_at = datetime.fromisoformat(row["updated_at"])
    expires_at = set_at + timedelta(hours=hours)

    if datetime.now() < expires_at:
        remaining = expires_at - datetime.now()
        return {
            "active": True,
            "expires_at": expires_at.isoformat(),
            "remaining_hours": round(remaining.total_seconds() / 3600, 1),
        }

    return {"active": False}
