"""Natural Language Query (NLQ) service for conversational betting data access.

Inspired by Gambly and Action Network Playbook AI. Parses natural language
queries about betting data and returns structured results. No external LLM
dependency — uses pattern matching and SQL generation.

Examples:
  "How did I do last week?"
  "Show my best market"
  "What's my ROI on NBA props?"
  "Am I profitable at DraftKings?"
  "Show bets over +150 odds"
"""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta

from sba.data.db import get_connection

logger = logging.getLogger(__name__)

# ── Query Patterns ──────────────────────────────────────────────────

_PATTERNS: list[tuple[str, str, list[str]]] = [
    # (intent, regex pattern, SQL-related params)
    # Order matters — more specific patterns first
    ("performance_period", r"(?:how|what).+(?:do|did|going|perform).+(?:today|yesterday|this week|last week|this month|last month)", []),
    ("best_market", r"(?:best|top|most profitable)\s+(?:market|bet type|sport)", []),
    ("worst_market", r"(?:worst|least profitable|losing)\s+(?:market|bet type|sport)", []),
    ("streak", r"(?:streak|hot|cold|momentum|on a (?:streak|run))", []),
    ("pending", r"(?:pending|open|active|unsettled)", []),
    ("sport_performance", r"(?:roi|profit|record|how).+(?:on|in|for)\s+(?:nba|nfl|mlb|nhl|soccer|ncaa|college)", ["sport"]),
    ("bookmaker_performance", r"(?:how|am i|performance|roi|profit).+(?:at|with)\s+(\w+)", ["bookmaker"]),
    ("odds_filter", r"(?:show|list|find|get).+(?:bets?|plays?).+(?:over|above|greater)\s+\+?(\d+)", ["min_odds"]),
    ("win_rate", r"(?:win rate|winning|record|w-l|win.?loss)", []),
    ("roi", r"(?:roi|return|profit.?loss|p.?l|bankroll)", []),
    ("recent_bets", r"(?:recent|last|latest|show).+(?:bets?|plays?|picks?)", []),
    ("summary", r"(?:summary|overview|dashboard|status|how.?am.?i)", []),
]


def query(text: str) -> dict:
    """Parse a natural language query and return structured results.

    Returns:
        {
            "intent": str,
            "query": str (original),
            "answer": str (human-readable),
            "data": dict (structured data),
        }
    """
    text_lower = text.strip().lower()

    if not text_lower or len(text_lower) < 3:
        return {
            "intent": "unknown",
            "query": text,
            "answer": "Please ask a question about your betting data.",
            "data": {},
            "suggestions": _get_suggestions(),
        }

    # Match against patterns
    for intent, pattern, params in _PATTERNS:
        match = re.search(pattern, text_lower)
        if match:
            return _execute_intent(intent, text, text_lower, match)

    # Fallback: try keyword matching
    return _keyword_fallback(text, text_lower)


def _execute_intent(intent: str, original: str, text_lower: str, match: re.Match) -> dict:
    """Execute a matched intent and return results."""
    handlers = {
        "performance_period": _handle_performance_period,
        "best_market": _handle_best_worst_market,
        "worst_market": _handle_best_worst_market,
        "bookmaker_performance": _handle_bookmaker,
        "sport_performance": _handle_sport,
        "odds_filter": _handle_odds_filter,
        "win_rate": _handle_win_rate,
        "roi": _handle_roi,
        "streak": _handle_streak,
        "recent_bets": _handle_recent,
        "pending": _handle_pending,
        "summary": _handle_summary,
    }

    handler = handlers.get(intent, _handle_summary)
    data = handler(text_lower, match)

    return {
        "intent": intent,
        "query": original,
        "answer": data.pop("answer", ""),
        "data": data,
    }


def _handle_performance_period(text: str, match: re.Match) -> dict:
    """Handle 'How did I do [period]?' queries."""
    period = _extract_period(text)
    date_filter = _period_to_sql(period)

    with get_connection() as conn:
        row = conn.execute(f"""
            SELECT COUNT(*) as bets,
                   SUM(CASE WHEN status='won' THEN 1 ELSE 0 END) as wins,
                   SUM(CASE WHEN status='lost' THEN 1 ELSE 0 END) as losses,
                   ROUND(SUM(profit_loss), 2) as profit,
                   ROUND(SUM(profit_loss) / NULLIF(SUM(ABS(recommended_stake)), 0) * 100, 1) as roi
            FROM bets
            WHERE status IN ('won', 'lost', 'push')
              AND placed_at >= {date_filter}
        """).fetchone()

    bets = row["bets"] or 0
    profit = row["profit"] or 0
    wins = row["wins"] or 0
    losses = row["losses"] or 0
    roi = row["roi"] or 0

    if bets == 0:
        answer = f"No settled bets found for {period}."
    elif profit > 0:
        answer = f"Great {period}! You went {wins}-{losses} for +${profit:.2f} ({roi}% ROI)."
    else:
        answer = f"Tough {period}. You went {wins}-{losses} for -${abs(profit):.2f} ({roi}% ROI)."

    return {
        "answer": answer,
        "period": period,
        "bets": bets, "wins": wins, "losses": losses,
        "profit": profit, "roi": roi,
    }


def _handle_best_worst_market(text: str, match: re.Match) -> dict:
    """Handle best/worst market queries."""
    order = "DESC" if "best" in text or "top" in text or "most" in text else "ASC"

    with get_connection() as conn:
        rows = conn.execute(f"""
            SELECT market,
                   COUNT(*) as bets,
                   SUM(CASE WHEN status='won' THEN 1 ELSE 0 END) as wins,
                   ROUND(SUM(profit_loss), 2) as profit,
                   ROUND(SUM(profit_loss) / NULLIF(SUM(ABS(recommended_stake)), 0) * 100, 1) as roi
            FROM bets WHERE status IN ('won', 'lost', 'push')
            GROUP BY market HAVING COUNT(*) >= 3
            ORDER BY roi {order}
            LIMIT 5
        """).fetchall()

    if not rows:
        return {"answer": "Not enough data to determine best/worst markets.", "markets": []}

    top = rows[0]
    label = "Best" if order == "DESC" else "Worst"
    answer = (f"{label} market: {top['market']} with {top['roi']}% ROI "
              f"({top['wins']}/{top['bets']} wins, ${top['profit']:.2f} profit).")

    return {
        "answer": answer,
        "markets": [dict(r) for r in rows],
    }


def _handle_bookmaker(text: str, match: re.Match) -> dict:
    """Handle 'How am I doing at [bookmaker]?' queries."""
    book = match.group(1) if match.lastindex else ""

    with get_connection() as conn:
        # Try to find the bookmaker (fuzzy match)
        books = conn.execute(
            "SELECT DISTINCT bookmaker FROM bets WHERE bookmaker IS NOT NULL"
        ).fetchall()

        matched_book = None
        for b in books:
            if book.lower() in b["bookmaker"].lower():
                matched_book = b["bookmaker"]
                break

        if not matched_book:
            return {"answer": f"No bets found at '{book}'.", "bookmaker": book}

        row = conn.execute("""
            SELECT COUNT(*) as bets,
                   SUM(CASE WHEN status='won' THEN 1 ELSE 0 END) as wins,
                   ROUND(SUM(profit_loss), 2) as profit,
                   ROUND(SUM(profit_loss) / NULLIF(SUM(ABS(recommended_stake)), 0) * 100, 1) as roi
            FROM bets WHERE bookmaker = ? AND status IN ('won', 'lost', 'push')
        """, (matched_book,)).fetchone()

    profit = row["profit"] or 0
    emoji_word = "profitable" if profit > 0 else "down"
    answer = (f"At {matched_book}: {row['wins']}/{row['bets']} wins, "
              f"${profit:.2f} profit ({row['roi']}% ROI). You're {emoji_word} there.")

    return {
        "answer": answer,
        "bookmaker": matched_book,
        "bets": row["bets"], "wins": row["wins"],
        "profit": profit, "roi": row["roi"],
    }


def _handle_sport(text: str, match: re.Match) -> dict:
    """Handle sport-specific performance queries."""
    sport_map = {
        "nba": "basketball_nba",
        "nfl": "americanfootball_nfl",
        "mlb": "baseball_mlb",
        "nhl": "icehockey_nhl",
        "soccer": "soccer",
        "ncaa": "basketball_ncaab",
        "college": "basketball_ncaab",
    }

    sport_key = None
    for keyword, key in sport_map.items():
        if keyword in text:
            sport_key = key
            break

    if not sport_key:
        return {"answer": "Couldn't identify the sport. Try: NBA, NFL, MLB, NHL.", "sport": None}

    with get_connection() as conn:
        row = conn.execute("""
            SELECT COUNT(*) as bets,
                   SUM(CASE WHEN b.status='won' THEN 1 ELSE 0 END) as wins,
                   ROUND(SUM(b.profit_loss), 2) as profit,
                   ROUND(SUM(b.profit_loss) / NULLIF(SUM(ABS(b.recommended_stake)), 0) * 100, 1) as roi
            FROM bets b
            JOIN events e ON e.id = b.event_id
            WHERE e.sport LIKE ? AND b.status IN ('won', 'lost', 'push')
        """, (f"%{sport_key}%",)).fetchone()

    bets = row["bets"] or 0
    if bets == 0:
        return {"answer": f"No settled bets found for {sport_key}.", "sport": sport_key}

    profit = row["profit"] or 0
    answer = (f"{sport_key}: {row['wins']}/{bets} wins, "
              f"${profit:.2f} profit ({row['roi']}% ROI).")

    return {
        "answer": answer,
        "sport": sport_key,
        "bets": bets, "wins": row["wins"],
        "profit": profit, "roi": row["roi"],
    }


def _handle_odds_filter(text: str, match: re.Match) -> dict:
    """Handle 'Show bets over +150' queries."""
    min_odds = int(match.group(1)) if match.lastindex else 100

    with get_connection() as conn:
        rows = conn.execute("""
            SELECT selection, odds_american, status, profit_loss, bookmaker, placed_at
            FROM bets
            WHERE odds_american >= ? AND status IN ('won', 'lost', 'push')
            ORDER BY placed_at DESC LIMIT 20
        """, (min_odds,)).fetchall()

    if not rows:
        return {"answer": f"No settled bets found with odds above +{min_odds}.", "bets": []}

    wins = sum(1 for r in rows if r["status"] == "won")
    profit = sum(r["profit_loss"] or 0 for r in rows)
    answer = (f"Found {len(rows)} bets above +{min_odds}: "
              f"{wins} wins, ${profit:.2f} total P/L.")

    return {
        "answer": answer,
        "min_odds": min_odds,
        "bets": [dict(r) for r in rows],
    }


def _handle_win_rate(text: str, match: re.Match) -> dict:
    with get_connection() as conn:
        row = conn.execute("""
            SELECT COUNT(*) as bets,
                   SUM(CASE WHEN status='won' THEN 1 ELSE 0 END) as wins,
                   SUM(CASE WHEN status='lost' THEN 1 ELSE 0 END) as losses,
                   SUM(CASE WHEN status='push' THEN 1 ELSE 0 END) as pushes
            FROM bets WHERE status IN ('won', 'lost', 'push')
        """).fetchone()

    bets = row["bets"] or 0
    if bets == 0:
        return {"answer": "No settled bets yet.", "win_rate": 0}

    wr = round(row["wins"] / bets * 100, 1)
    answer = f"Overall record: {row['wins']}-{row['losses']}-{row['pushes']} ({wr}% win rate)."

    return {"answer": answer, "wins": row["wins"], "losses": row["losses"],
            "pushes": row["pushes"], "win_rate": wr}


def _handle_roi(text: str, match: re.Match) -> dict:
    with get_connection() as conn:
        row = conn.execute("""
            SELECT ROUND(SUM(profit_loss), 2) as profit,
                   ROUND(SUM(ABS(recommended_stake)), 2) as staked,
                   ROUND(SUM(profit_loss) / NULLIF(SUM(ABS(recommended_stake)), 0) * 100, 1) as roi
            FROM bets WHERE status IN ('won', 'lost', 'push')
        """).fetchone()

    profit = row["profit"] or 0
    staked = row["staked"] or 0
    roi = row["roi"] or 0
    status = "profitable" if profit > 0 else "down"
    answer = f"You're {status}: ${profit:.2f} on ${staked:.2f} staked ({roi}% ROI)."

    return {"answer": answer, "profit": profit, "staked": staked, "roi": roi}


def _handle_streak(text: str, match: re.Match) -> dict:
    from sba.services.momentum import get_streak_analysis
    result = get_streak_analysis()
    streak = result.get("current_streak", {})
    momentum = result.get("momentum", {})

    stype = streak.get("type", "none")
    slen = streak.get("length", 0)
    label = momentum.get("label", "Neutral")

    answer = f"Current streak: {slen} {stype}. Momentum: {label} ({momentum.get('score', 0)})."
    return {"answer": answer, **result}


def _handle_recent(text: str, match: re.Match) -> dict:
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT selection, market, odds_american, status, profit_loss,
                   bookmaker, placed_at
            FROM bets ORDER BY placed_at DESC LIMIT 10
        """).fetchall()

    answer = f"Last {len(rows)} bets:" if rows else "No bets found."
    return {"answer": answer, "bets": [dict(r) for r in rows]}


def _handle_pending(text: str, match: re.Match) -> dict:
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT selection, market, odds_american, bookmaker, placed_at
            FROM bets WHERE status = 'pending'
            ORDER BY placed_at DESC
        """).fetchall()

    answer = f"You have {len(rows)} pending bets." if rows else "No pending bets."
    return {"answer": answer, "bets": [dict(r) for r in rows]}


def _handle_summary(text: str, match: re.Match) -> dict:
    from sba.services.momentum import get_daily_summary
    summary = get_daily_summary()
    today = summary.get("today", {})
    profit = today.get("profit", 0)

    if profit > 0:
        answer = f"Today: {today['wins']}/{today['bets']} wins, +${profit:.2f}. Looking good!"
    elif profit < 0:
        answer = f"Today: {today['wins']}/{today['bets']} wins, -${abs(profit):.2f}. Hang in there."
    else:
        answer = f"Today: {today.get('bets', 0)} bets settled, breakeven."

    return {"answer": answer, **summary}


# ── Helpers ─────────────────────────────────────────────────────────

def _extract_period(text: str) -> str:
    if "today" in text:
        return "today"
    if "yesterday" in text:
        return "yesterday"
    if "last week" in text:
        return "last week"
    if "this week" in text:
        return "this week"
    if "last month" in text:
        return "last month"
    if "this month" in text:
        return "this month"
    return "today"


def _period_to_sql(period: str) -> str:
    mapping = {
        "today": "DATE('now')",
        "yesterday": "DATE('now', '-1 day')",
        "this week": "DATE('now', '-7 days')",
        "last week": "DATE('now', '-14 days')",
        "this month": "DATE('now', '-30 days')",
        "last month": "DATE('now', '-60 days')",
    }
    return mapping.get(period, "DATE('now')")


def _keyword_fallback(original: str, text: str) -> dict:
    """Try keyword matching as a fallback."""
    keywords = {
        "profit": _handle_roi,
        "money": _handle_roi,
        "bankroll": _handle_roi,
        "record": _handle_win_rate,
        "bet": _handle_recent,
        "play": _handle_recent,
        "streak": _handle_streak,
        "hot": _handle_streak,
        "cold": _handle_streak,
    }

    for keyword, handler in keywords.items():
        if keyword in text:
            data = handler(text, re.match("", ""))
            return {"intent": "keyword_match", "query": original,
                    "answer": data.pop("answer", ""), "data": data}

    return {
        "intent": "unknown",
        "query": original,
        "answer": "I'm not sure what you're asking. Try questions like:",
        "data": {},
        "suggestions": _get_suggestions(),
    }


def _get_suggestions() -> list[str]:
    return [
        "How did I do this week?",
        "What's my best market?",
        "Am I profitable at DraftKings?",
        "Show my win rate",
        "What's my ROI on NBA?",
        "Show recent bets",
        "Am I on a streak?",
    ]
