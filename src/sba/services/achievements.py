"""Achievements & badges gamification system.

Inspired by Pikkit, BetConstruct, and Smartico - the leading gamification
platforms in sports betting. Tracks milestones, awards badges, and drives
engagement through progression.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AchievementDef:
    """Definition of an unlockable achievement."""
    id: str
    name: str
    description: str
    icon: str  # SVG icon name
    category: str  # betting, analytics, community, streak, bankroll
    tier: str  # bronze, silver, gold, diamond
    threshold: int  # numeric threshold to unlock
    points: int  # points awarded


# ── Achievement Catalog ──────────────────────────────────────────────
ACHIEVEMENTS: list[AchievementDef] = [
    # Betting volume
    AchievementDef("first_bet", "First Blood", "Place your first bet", "target", "betting", "bronze", 1, 10),
    AchievementDef("bets_10", "Getting Started", "Place 10 bets", "trending-up", "betting", "bronze", 10, 25),
    AchievementDef("bets_50", "Serious Bettor", "Place 50 bets", "trending-up", "betting", "silver", 50, 50),
    AchievementDef("bets_100", "Centurion", "Place 100 bets", "trending-up", "betting", "gold", 100, 100),
    AchievementDef("bets_500", "High Roller", "Place 500 bets", "trending-up", "betting", "diamond", 500, 250),

    # Win streaks
    AchievementDef("streak_3", "Hat Trick", "Win 3 bets in a row", "zap", "streak", "bronze", 3, 20),
    AchievementDef("streak_5", "On Fire", "Win 5 bets in a row", "zap", "streak", "silver", 5, 50),
    AchievementDef("streak_10", "Untouchable", "Win 10 bets in a row", "zap", "streak", "gold", 10, 150),
    AchievementDef("streak_20", "Legendary Run", "Win 20 bets in a row", "zap", "streak", "diamond", 20, 500),

    # Profit milestones
    AchievementDef("profit_100", "In the Green", "Reach $100 total profit", "dollar-sign", "bankroll", "bronze", 100, 30),
    AchievementDef("profit_500", "Bankroll Builder", "Reach $500 total profit", "dollar-sign", "bankroll", "silver", 500, 75),
    AchievementDef("profit_1000", "Four Figures", "Reach $1,000 total profit", "dollar-sign", "bankroll", "gold", 1000, 150),
    AchievementDef("profit_5000", "Big Winner", "Reach $5,000 total profit", "dollar-sign", "bankroll", "diamond", 5000, 500),

    # ROI excellence
    AchievementDef("roi_5", "Edge Finder", "Maintain 5%+ ROI over 20+ bets", "percent", "analytics", "bronze", 5, 40),
    AchievementDef("roi_10", "Sharp Mind", "Maintain 10%+ ROI over 50+ bets", "percent", "analytics", "silver", 10, 100),
    AchievementDef("roi_15", "Market Beater", "Maintain 15%+ ROI over 100+ bets", "percent", "analytics", "gold", 15, 250),

    # Diversity
    AchievementDef("sports_3", "Multi-Sport", "Bet on 3 different sports", "globe", "betting", "bronze", 3, 25),
    AchievementDef("sports_5", "Polymath", "Bet on 5 different sports", "globe", "betting", "silver", 5, 60),
    AchievementDef("books_3", "Line Shopper", "Use 3 different bookmakers", "shopping-cart", "betting", "bronze", 3, 20),
    AchievementDef("books_5", "Sharp Shopper", "Use 5 different bookmakers", "shopping-cart", "betting", "silver", 5, 50),

    # Community
    AchievementDef("picks_1", "Contributor", "Submit your first public pick", "share", "community", "bronze", 1, 10),
    AchievementDef("picks_10", "Community Leader", "Submit 10 public picks", "share", "community", "silver", 10, 50),
    AchievementDef("picks_50", "Influencer", "Submit 50 public picks", "share", "community", "gold", 50, 150),

    # Special
    AchievementDef("underdog_win", "Giant Slayer", "Win a bet at +300 or longer odds", "award", "betting", "silver", 300, 40),
    AchievementDef("perfect_week", "Perfect Week", "Win 5+ bets in a single week with 0 losses", "star", "streak", "gold", 5, 200),
    AchievementDef("comeback", "Comeback King", "Recover from a 5+ loss streak to profit", "refresh-cw", "streak", "gold", 5, 150),
    AchievementDef("analyzer", "Data Nerd", "View analytics page 10 times", "bar-chart-2", "analytics", "bronze", 10, 15),
]

ACHIEVEMENT_MAP = {a.id: a for a in ACHIEVEMENTS}
TIER_ORDER = {"bronze": 0, "silver": 1, "gold": 2, "diamond": 3}


def evaluate_achievements(stats: dict) -> list[dict]:
    """Evaluate which achievements are unlocked based on user stats.

    Args:
        stats: dict with keys like total_bets, longest_win_streak, total_profit,
               roi_pct, unique_sports, unique_books, total_picks, biggest_underdog_win,
               analytics_views, perfect_weeks, comeback_count.

    Returns:
        List of dicts with achievement info and unlocked status.
    """
    results = []
    for ach in ACHIEVEMENTS:
        unlocked = False
        progress = 0

        if ach.id.startswith("bets_") or ach.id == "first_bet":
            progress = stats.get("total_bets", 0)
            unlocked = progress >= ach.threshold

        elif ach.id.startswith("streak_"):
            progress = stats.get("longest_win_streak", 0)
            unlocked = progress >= ach.threshold

        elif ach.id.startswith("profit_"):
            progress = max(0, stats.get("total_profit", 0))
            unlocked = progress >= ach.threshold

        elif ach.id.startswith("roi_"):
            min_bets = {5: 20, 10: 50, 15: 100}.get(ach.threshold, 20)
            roi = stats.get("roi_pct", 0)
            total = stats.get("total_bets", 0)
            progress = roi if total >= min_bets else 0
            unlocked = progress >= ach.threshold and total >= min_bets

        elif ach.id.startswith("sports_"):
            progress = stats.get("unique_sports", 0)
            unlocked = progress >= ach.threshold

        elif ach.id.startswith("books_"):
            progress = stats.get("unique_books", 0)
            unlocked = progress >= ach.threshold

        elif ach.id.startswith("picks_"):
            progress = stats.get("total_picks", 0)
            unlocked = progress >= ach.threshold

        elif ach.id == "underdog_win":
            biggest = stats.get("biggest_underdog_win", 0)
            progress = biggest
            unlocked = biggest >= ach.threshold

        elif ach.id == "perfect_week":
            progress = stats.get("perfect_weeks", 0)
            unlocked = progress >= 1

        elif ach.id == "comeback":
            progress = stats.get("comeback_count", 0)
            unlocked = progress >= 1

        elif ach.id == "analyzer":
            progress = stats.get("analytics_views", 0)
            unlocked = progress >= ach.threshold

        pct = min(100, round(progress / ach.threshold * 100)) if ach.threshold > 0 else 0

        results.append({
            "id": ach.id,
            "name": ach.name,
            "description": ach.description,
            "icon": ach.icon,
            "category": ach.category,
            "tier": ach.tier,
            "tier_rank": TIER_ORDER[ach.tier],
            "points": ach.points,
            "threshold": ach.threshold,
            "progress": progress,
            "progress_pct": pct,
            "unlocked": unlocked,
        })

    return results


def get_achievement_summary(achievements: list[dict]) -> dict:
    """Summarize achievements for profile display."""
    unlocked = [a for a in achievements if a["unlocked"]]
    total_points = sum(a["points"] for a in unlocked)

    by_tier = {}
    for tier in ["bronze", "silver", "gold", "diamond"]:
        tier_all = [a for a in achievements if a["tier"] == tier]
        tier_unlocked = [a for a in tier_all if a["unlocked"]]
        by_tier[tier] = {"total": len(tier_all), "unlocked": len(tier_unlocked)}

    by_category = {}
    for cat in ["betting", "streak", "bankroll", "analytics", "community"]:
        cat_all = [a for a in achievements if a["category"] == cat]
        cat_unlocked = [a for a in cat_all if a["unlocked"]]
        by_category[cat] = {"total": len(cat_all), "unlocked": len(cat_unlocked)}

    # Determine rank title based on points
    if total_points >= 2000:
        rank = "Legend"
    elif total_points >= 1000:
        rank = "Master"
    elif total_points >= 500:
        rank = "Expert"
    elif total_points >= 200:
        rank = "Advanced"
    elif total_points >= 50:
        rank = "Intermediate"
    else:
        rank = "Rookie"

    return {
        "total_unlocked": len(unlocked),
        "total_achievements": len(achievements),
        "total_points": total_points,
        "rank": rank,
        "by_tier": by_tier,
        "by_category": by_category,
        "next_unlock": next(
            (a for a in sorted(achievements, key=lambda x: x["progress_pct"], reverse=True)
             if not a["unlocked"]),
            None
        ),
    }
