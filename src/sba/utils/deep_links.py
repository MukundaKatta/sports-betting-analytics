"""Sportsbook deep-link generator.

Generates links to open specific events on sportsbook websites,
reducing friction from finding an edge to placing a bet.
Inspired by OddsJam's one-click bet placement feature.
"""

from __future__ import annotations

# Mapping from odds API bookmaker keys to deep link templates
# These point to the sportsbook's event/search pages
SPORTSBOOK_LINKS: dict[str, dict] = {
    "draftkings": {
        "name": "DraftKings",
        "base": "https://sportsbook.draftkings.com",
        "search": "https://sportsbook.draftkings.com/search?q={query}",
    },
    "fanduel": {
        "name": "FanDuel",
        "base": "https://sportsbook.fanduel.com",
        "search": "https://sportsbook.fanduel.com/search?q={query}",
    },
    "betmgm": {
        "name": "BetMGM",
        "base": "https://sports.betmgm.com",
        "search": "https://sports.betmgm.com/en/sports?query={query}",
    },
    "caesars": {
        "name": "Caesars",
        "base": "https://www.caesars.com/sportsbook-and-casino",
        "search": "https://www.caesars.com/sportsbook-and-casino/search/{query}",
    },
    "pointsbet": {
        "name": "PointsBet",
        "base": "https://pointsbet.com",
        "search": "https://pointsbet.com/search/{query}",
    },
    "betrivers": {
        "name": "BetRivers",
        "base": "https://www.betrivers.com",
        "search": "https://www.betrivers.com/search?q={query}",
    },
    "espnbet": {
        "name": "ESPN BET",
        "base": "https://espnbet.com",
        "search": "https://espnbet.com/search?q={query}",
    },
    "pinnacle": {
        "name": "Pinnacle",
        "base": "https://www.pinnacle.com",
        "search": "https://www.pinnacle.com/en/search/{query}",
    },
    "bovada": {
        "name": "Bovada",
        "base": "https://www.bovada.lv",
        "search": "https://www.bovada.lv/search?query={query}",
    },
    "bet365": {
        "name": "bet365",
        "base": "https://www.bet365.com",
        "search": "https://www.bet365.com/#/IP/",
    },
    "hard_rock": {
        "name": "Hard Rock Bet",
        "base": "https://www.hardrock.bet",
        "search": "https://www.hardrock.bet/search?q={query}",
    },
    "fanatics": {
        "name": "Fanatics",
        "base": "https://sportsbook.fanatics.com",
        "search": "https://sportsbook.fanatics.com/search?q={query}",
    },
}


def get_deep_link(bookmaker: str, home_team: str = "", away_team: str = "") -> str | None:
    """Generate a deep link to a sportsbook for a given event.

    Returns a search URL that will find the event on the sportsbook site.
    """
    key = bookmaker.lower().replace(" ", "_").replace("-", "_")
    info = SPORTSBOOK_LINKS.get(key)
    if not info:
        return None

    # Use team names as search query
    query = f"{away_team} {home_team}".strip()
    if not query:
        return info["base"]

    # URL-encode the query
    query_encoded = query.replace(" ", "+")
    return info["search"].format(query=query_encoded)


def get_book_display_info(bookmaker: str) -> dict:
    """Get display information for a bookmaker."""
    key = bookmaker.lower().replace(" ", "_").replace("-", "_")
    info = SPORTSBOOK_LINKS.get(key, {})
    return {
        "name": info.get("name", bookmaker.title()),
        "url": info.get("base", ""),
        "has_deep_link": key in SPORTSBOOK_LINKS,
    }
