"""Events, live-odds, odds-screen, odds-comparison, line-movement, consensus, sports endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from sba.config import get_settings
from sba.data.db import get_connection
from sba.utils.cache import cached_response
from sba.web.api import repo

logger = logging.getLogger(__name__)
router = APIRouter(tags=["odds"])


# ── Pydantic models ─────────────────────────────────────────────────

class EventResponse(BaseModel):
    id: str
    sport: str
    home_team: str
    away_team: str
    commence_time: str
    completed: bool
    home_score: int | None = None
    away_score: int | None = None


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("/events", response_model=list[EventResponse])
def get_events(sport: str = Query(None)):
    """Get upcoming events from the database."""
    settings = get_settings()
    sport = sport or settings.DEFAULT_SPORT
    with get_connection() as conn:
        events = repo.get_upcoming_events(conn, sport)
    return [
        EventResponse(
            id=e.id, sport=e.sport,
            home_team=e.home_team, away_team=e.away_team,
            commence_time=e.commence_time.isoformat(),
            completed=e.completed,
            home_score=e.home_score, away_score=e.away_score,
        )
        for e in events
    ]


@router.get("/line-movement/{event_id}")
def get_line_movement(event_id: str, market: str = Query("h2h")):
    """Get line movement history for an event."""
    with get_connection() as conn:
        snapshots = repo.get_odds_history(conn, event_id, market)
    return [
        {
            "time": str(s.snapshot_time)[:19] if s.snapshot_time else "",
            "bookmaker": s.bookmaker,
            "outcome": s.outcome_name,
            "line": s.outcome_point,
            "odds_american": s.price_american,
            "odds_decimal": s.price_decimal,
        }
        for s in snapshots
    ]


@router.get("/odds-comparison/{event_id}")
def get_odds_comparison(event_id: str, market: str = Query("h2h")):
    """Get latest odds from all bookmakers for an event, grouped by outcome."""
    with get_connection() as conn:
        snapshots = repo.get_odds_history(conn, event_id, market)

    # Group by bookmaker+outcome, keep only latest snapshot per group
    latest: dict[str, dict] = {}
    for s in snapshots:
        key = f"{s.bookmaker}|{s.outcome_name}"
        latest[key] = {
            "bookmaker": s.bookmaker,
            "outcome": s.outcome_name,
            "line": s.outcome_point,
            "odds_american": s.price_american,
            "odds_decimal": s.price_decimal,
            "time": str(s.snapshot_time)[:19] if s.snapshot_time else "",
        }

    # Organize into matrix: outcomes as rows, bookmakers as columns
    outcomes: dict[str, list] = {}
    bookmakers = set()
    for entry in latest.values():
        outcome = entry["outcome"]
        bk = entry["bookmaker"]
        bookmakers.add(bk)
        if outcome not in outcomes:
            outcomes[outcome] = []
        outcomes[outcome].append(entry)

    return {
        "bookmakers": sorted(bookmakers),
        "outcomes": outcomes,
        "total_snapshots": len(snapshots),
    }


@router.get("/live-odds")
def get_live_odds(limit: int = Query(20, ge=1, le=500)):
    """Get most recent odds snapshots as a live feed."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT os.bookmaker, os.outcome_name, os.price_american, os.price_decimal,
                   os.outcome_point, os.snapshot_time,
                   e.home_team, e.away_team, e.sport, os.market
            FROM odds_snapshots os
            JOIN events e ON os.event_id = e.id
            ORDER BY os.snapshot_time DESC
            LIMIT ?
        """, (limit,)).fetchall()

    return [
        {
            "bookmaker": r["bookmaker"],
            "outcome": r["outcome_name"],
            "odds_american": r["price_american"],
            "odds_decimal": round(r["price_decimal"], 3),
            "line": r["outcome_point"],
            "time": str(r["snapshot_time"])[:19] if r["snapshot_time"] else "",
            "home_team": r["home_team"],
            "away_team": r["away_team"],
            "sport": r["sport"],
            "market": r["market"],
        }
        for r in rows
    ]


@router.get("/odds-screen")
def odds_screen(
    sport: str = Query("basketball_nba"),
    market: str = Query("h2h"),
):
    """Get a comprehensive odds screen showing all events with best odds.

    Like OddsJam's main screen: every game, every book, best price highlighted.
    Uses a single JOIN query instead of N+1 queries per event.
    """
    with get_connection() as conn:
        # Single query: events + their latest odds per bookmaker/outcome
        rows = conn.execute("""
            SELECT e.id as event_id, e.home_team, e.away_team,
                   e.commence_time, e.sport,
                   os.bookmaker, os.outcome_name, os.outcome_point,
                   os.price_american, os.price_decimal,
                   MAX(os.snapshot_time) as latest_time
            FROM events e
            INNER JOIN odds_snapshots os ON os.event_id = e.id
            WHERE e.completed = 0 AND os.market = ?
            GROUP BY e.id, os.bookmaker, os.outcome_name
            ORDER BY e.commence_time, os.bookmaker
            LIMIT 500
        """, (market,)).fetchall()

    # Group rows by event
    events_map: dict[str, dict] = {}
    for r in rows:
        eid = r["event_id"]
        if eid not in events_map:
            events_map[eid] = {
                "event_id": eid,
                "home_team": r["home_team"],
                "away_team": r["away_team"],
                "commence_time": r["commence_time"],
                "sport": r["sport"],
                "market": market,
                "outcomes": {},
                "bookmakers": set(),
            }
        ev = events_map[eid]
        outcome = r["outcome_name"]
        ev["outcomes"].setdefault(outcome, []).append({
            "bookmaker": r["bookmaker"],
            "odds_american": r["price_american"],
            "odds_decimal": round(r["price_decimal"], 3),
            "line": r["outcome_point"],
        })
        ev["bookmakers"].add(r["bookmaker"])

    # Build response with best odds
    odds_screen_data = []
    for ev in events_map.values():
        best_odds = {}
        for outcome, books in ev["outcomes"].items():
            best = max(books, key=lambda b: b["odds_decimal"])
            best_odds[outcome] = {
                "bookmaker": best["bookmaker"],
                "odds_american": best["odds_american"],
            }
        odds_screen_data.append({
            "event_id": ev["event_id"],
            "home_team": ev["home_team"],
            "away_team": ev["away_team"],
            "commence_time": ev["commence_time"],
            "sport": ev["sport"],
            "market": market,
            "outcomes": ev["outcomes"],
            "best_odds": best_odds,
            "num_books": len(ev["bookmakers"]),
        })

    return {
        "sport": sport,
        "market": market,
        "events": odds_screen_data,
        "total_events": len(odds_screen_data),
    }


@router.get("/consensus/{event_id}")
def get_consensus(event_id: str):
    """Get consensus odds and implied probabilities across all books.

    Like BettingPros' consensus feature - aggregates all bookmaker opinions.
    """
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT bookmaker, market, outcome_name, outcome_point,
                   price_american, price_decimal,
                   MAX(snapshot_time) as latest
            FROM odds_snapshots
            WHERE event_id = ?
            GROUP BY bookmaker, market, outcome_name
            ORDER BY market, outcome_name, bookmaker
        """, (event_id,)).fetchall()

    if not rows:
        return {"event_id": event_id, "markets": {}}

    from sba.utils.odds_math import decimal_to_implied_prob

    markets: dict[str, dict] = {}
    for r in rows:
        mkt = r["market"]
        outcome = r["outcome_name"]
        if mkt not in markets:
            markets[mkt] = {}
        if outcome not in markets[mkt]:
            markets[mkt][outcome] = {"books": [], "line": r["outcome_point"]}

        dec = r["price_decimal"]
        imp = decimal_to_implied_prob(dec)

        markets[mkt][outcome]["books"].append({
            "bookmaker": r["bookmaker"],
            "odds_american": r["price_american"],
            "odds_decimal": round(dec, 3),
            "implied_prob": round(imp, 4),
        })

    # Calculate consensus for each outcome
    for mkt in markets:
        for outcome in markets[mkt]:
            books = markets[mkt][outcome]["books"]
            if books:
                avg_prob = sum(b["implied_prob"] for b in books) / len(books)
                best = max(books, key=lambda b: b["odds_decimal"])
                worst = min(books, key=lambda b: b["odds_decimal"])

                markets[mkt][outcome]["consensus_prob"] = round(avg_prob, 4)
                markets[mkt][outcome]["best_odds"] = best["odds_american"]
                markets[mkt][outcome]["best_book"] = best["bookmaker"]
                markets[mkt][outcome]["worst_odds"] = worst["odds_american"]
                markets[mkt][outcome]["num_books"] = len(books)
                markets[mkt][outcome]["spread"] = best["odds_american"] - worst["odds_american"]

    return {"event_id": event_id, "markets": markets}


@router.get("/sports")
@cached_response(ttl=300, prefix="sports")
def get_available_sports():
    """Get all available sports with event counts."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT sport, COUNT(*) as event_count,
                   SUM(CASE WHEN completed = 0 THEN 1 ELSE 0 END) as upcoming
            FROM events
            GROUP BY sport
            ORDER BY event_count DESC
        """).fetchall()

    sports = [
        {
            "key": r["sport"],
            "name": r["sport"].replace("_", " ").title(),
            "event_count": r["event_count"],
            "upcoming": r["upcoming"],
        }
        for r in rows
    ]

    # Add known sports that might not have data yet
    known_sports = [
        {"key": "basketball_nba", "name": "NBA"},
        {"key": "basketball_ncaab", "name": "NCAAB"},
        {"key": "americanfootball_nfl", "name": "NFL"},
        {"key": "baseball_mlb", "name": "MLB"},
        {"key": "icehockey_nhl", "name": "NHL"},
        {"key": "soccer_epl", "name": "EPL Soccer"},
        {"key": "soccer_usa_mls", "name": "MLS"},
        {"key": "mma_mixed_martial_arts", "name": "UFC/MMA"},
        {"key": "tennis_atp", "name": "ATP Tennis"},
    ]

    existing_keys = {s["key"] for s in sports}
    for ks in known_sports:
        if ks["key"] not in existing_keys:
            sports.append({**ks, "event_count": 0, "upcoming": 0})

    return sports


@router.get("/line-movement/timeline/{event_id}")
def line_movement_timeline(event_id: str, market: str = Query("h2h")):
    """Enhanced line movement timeline with bookmaker comparison.

    Returns timestamped odds changes across all bookmakers for visual timeline.
    """
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT bookmaker, outcome_name, price_american, price_decimal,
                   snapshot_time
            FROM odds_snapshots
            WHERE event_id = ? AND market = ?
            ORDER BY snapshot_time
        """, (event_id, market)).fetchall()

        event = conn.execute(
            "SELECT * FROM events WHERE id = ?", (event_id,)
        ).fetchone()

    if not rows:
        return {"event_id": event_id, "timeline": [], "bookmakers": [], "outcomes": []}

    bookmakers = sorted(set(r["bookmaker"] for r in rows))
    outcomes = sorted(set(r["outcome_name"] for r in rows))

    # Build timeline entries
    timeline = []
    prev_odds = {}
    for r in rows:
        key = f"{r['bookmaker']}_{r['outcome_name']}"
        prev = prev_odds.get(key)
        change = 0
        direction = "none"
        if prev is not None:
            change = r["price_american"] - prev
            direction = "up" if change > 0 else "down" if change < 0 else "none"

        timeline.append({
            "time": r["snapshot_time"],
            "bookmaker": r["bookmaker"],
            "outcome": r["outcome_name"],
            "odds_american": r["price_american"],
            "odds_decimal": round(r["price_decimal"], 3),
            "change": change,
            "direction": direction,
        })
        prev_odds[key] = r["price_american"]

    return {
        "event_id": event_id,
        "event": {
            "home_team": event["home_team"] if event else "Unknown",
            "away_team": event["away_team"] if event else "Unknown",
            "sport": event["sport"] if event else "Unknown",
        },
        "bookmakers": bookmakers,
        "outcomes": outcomes,
        "timeline": timeline,
        "total_snapshots": len(timeline),
    }
