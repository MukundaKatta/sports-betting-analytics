"""Account limiting tracker service.

The #1 pain point for profitable sports bettors: sportsbook account limiting.
This service tracks limiting status across all books and provides actionable advice.
No competitor currently addresses this — this is a unique differentiator.
"""

from __future__ import annotations

import logging

from sba.data.db import get_connection

logger = logging.getLogger(__name__)

# Limiting severity levels
SEVERITY_LEVELS = {
    "none": {"label": "No Limits", "color": "#00e68a", "score": 0},
    "low": {"label": "Slightly Limited", "color": "#ffc234", "score": 1},
    "medium": {"label": "Moderately Limited", "color": "#ff9f43", "score": 2},
    "high": {"label": "Heavily Limited", "color": "#ff6b6b", "score": 3},
    "banned": {"label": "Banned/Closed", "color": "#ff4d6a", "score": 4},
}

LIMIT_TYPES = {
    "none": "No restrictions",
    "stake_reduced": "Max stake reduced (can still bet smaller amounts)",
    "partial": "Some markets restricted (e.g., props banned, only pre-game)",
    "promo_banned": "Excluded from promotions and bonuses",
    "full": "All limits applied (minimal or no betting possible)",
    "closed": "Account closed or self-excluded",
}

# Tips for avoiding or managing limits
LIMITING_TIPS = [
    "Round bet amounts to common increments ($25, $50, $100) to look recreational",
    "Mix in some -EV bets on popular markets to blend in",
    "Avoid betting immediately after line moves — wait a few minutes",
    "Don't max-bet early lines — sharp action on openers gets flagged fastest",
    "Use props and player markets sparingly — these have the lowest limits",
    "Spread action across multiple books instead of hammering one",
    "Avoid withdrawing too frequently — keep funds in the account",
    "Bet on popular sports/events that have higher liquidity",
    "Consider using a separate book for high-EV plays vs. recreational bets",
]


def get_all_limits() -> dict:
    """Get account limiting status for all tracked sportsbooks."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM account_limits ORDER BY severity DESC, sportsbook"
        ).fetchall()

    limits = []
    severity_counts = {"none": 0, "low": 0, "medium": 0, "high": 0, "banned": 0}

    for r in rows:
        sev = r["severity"]
        severity_counts[sev] = severity_counts.get(sev, 0) + 1
        sev_info = SEVERITY_LEVELS.get(sev, SEVERITY_LEVELS["none"])
        limits.append({
            "id": r["id"],
            "sportsbook": r["sportsbook"],
            "limit_type": r["limit_type"],
            "limit_description": LIMIT_TYPES.get(r["limit_type"], r["limit_type"]),
            "max_stake": r["max_stake"],
            "severity": sev,
            "severity_label": sev_info["label"],
            "severity_color": sev_info["color"],
            "notes": r["notes"],
            "detected_at": r["detected_at"],
        })

    # Health score: 100 = no limits, 0 = all banned
    total = len(limits) or 1
    health_score = round(
        100 - sum(
            SEVERITY_LEVELS.get(l["severity"], {}).get("score", 0) * 25
            for l in limits
        ) / total,
        0,
    )
    health_score = max(0, min(100, health_score))

    active_books = sum(1 for l in limits if l["severity"] not in ("banned", "high"))

    return {
        "limits": limits,
        "total_books": len(limits),
        "active_books": active_books,
        "health_score": health_score,
        "severity_counts": severity_counts,
        "tips": LIMITING_TIPS[:5],
    }


def upsert_limit(sportsbook: str, limit_type: str = "none",
                  severity: str = "none", max_stake: float | None = None,
                  notes: str = "") -> dict:
    """Add or update limiting status for a sportsbook."""
    if severity not in SEVERITY_LEVELS:
        severity = "none"
    if limit_type not in LIMIT_TYPES:
        limit_type = "none"

    with get_connection() as conn:
        conn.execute(
            """INSERT INTO account_limits (sportsbook, limit_type, severity, max_stake, notes)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(sportsbook) DO UPDATE SET
                 limit_type=excluded.limit_type, severity=excluded.severity,
                 max_stake=excluded.max_stake, notes=excluded.notes,
                 detected_at=CURRENT_TIMESTAMP""",
            (sportsbook, limit_type, severity, max_stake, notes),
        )

    # Also update is_limited flag on book_balances if it exists
    with get_connection() as conn:
        is_limited = severity not in ("none", "low")
        conn.execute(
            "UPDATE book_balances SET is_limited = ? WHERE sportsbook = ?",
            (int(is_limited), sportsbook),
        )

    return {
        "sportsbook": sportsbook,
        "limit_type": limit_type,
        "severity": severity,
        "status": "saved",
    }


def delete_limit(sportsbook: str) -> dict:
    """Remove limiting record for a sportsbook."""
    with get_connection() as conn:
        conn.execute("DELETE FROM account_limits WHERE sportsbook = ?", (sportsbook,))
        conn.execute(
            "UPDATE book_balances SET is_limited = 0 WHERE sportsbook = ?", (sportsbook,),
        )
    return {"sportsbook": sportsbook, "status": "deleted"}


def get_limiting_risk(bet_count_by_book: dict[str, int] | None = None) -> list[dict]:
    """Estimate limiting risk for each book based on betting patterns.

    Higher bet volume + higher win rate + prop-heavy = higher risk.
    """
    with get_connection() as conn:
        # Analyze bet patterns by bookmaker
        rows = conn.execute("""
            SELECT bookmaker,
                   COUNT(*) as total_bets,
                   SUM(CASE WHEN status='won' THEN 1 ELSE 0 END) as wins,
                   SUM(CASE WHEN status IN ('won','lost') THEN 1 ELSE 0 END) as settled,
                   SUM(profit_loss) as total_profit,
                   AVG(recommended_stake) as avg_stake,
                   SUM(CASE WHEN market LIKE '%prop%' OR market LIKE '%player%' THEN 1 ELSE 0 END) as prop_bets
            FROM bets
            WHERE bookmaker != 'manual'
            GROUP BY bookmaker
            HAVING settled > 0
        """).fetchall()

    risks = []
    for r in rows:
        win_rate = r["wins"] / max(r["settled"], 1)
        prop_ratio = r["prop_bets"] / max(r["total_bets"], 1)

        # Risk factors (each 0-1, summed and normalized)
        risk_score = 0.0
        risk_factors = []

        # High win rate is the biggest flag
        if win_rate > 0.60:
            risk_score += 0.35
            risk_factors.append(f"High win rate ({win_rate:.0%})")
        elif win_rate > 0.55:
            risk_score += 0.15
            risk_factors.append(f"Above-average win rate ({win_rate:.0%})")

        # Heavy prop betting
        if prop_ratio > 0.5:
            risk_score += 0.25
            risk_factors.append(f"Heavy prop betting ({prop_ratio:.0%} of bets)")
        elif prop_ratio > 0.25:
            risk_score += 0.10

        # High volume
        if r["total_bets"] > 200:
            risk_score += 0.20
            risk_factors.append(f"High volume ({r['total_bets']} bets)")
        elif r["total_bets"] > 100:
            risk_score += 0.10

        # Profitability
        if r["total_profit"] > 500:
            risk_score += 0.20
            risk_factors.append(f"Profitable (${r['total_profit']:.0f})")

        risk_level = "low"
        if risk_score > 0.6:
            risk_level = "high"
        elif risk_score > 0.3:
            risk_level = "medium"

        risks.append({
            "sportsbook": r["bookmaker"],
            "total_bets": r["total_bets"],
            "win_rate": round(win_rate * 100, 1),
            "total_profit": round(r["total_profit"], 2),
            "risk_score": round(risk_score * 100, 0),
            "risk_level": risk_level,
            "risk_factors": risk_factors,
        })

    risks.sort(key=lambda x: x["risk_score"], reverse=True)
    return risks
