"""Tests for the achievements & gamification service."""

from sba.services.achievements import (
    ACHIEVEMENTS,
    ACHIEVEMENT_MAP,
    evaluate_achievements,
    get_achievement_summary,
)


class TestAchievementCatalog:
    def test_has_achievements(self):
        assert len(ACHIEVEMENTS) > 20

    def test_all_have_unique_ids(self):
        ids = [a.id for a in ACHIEVEMENTS]
        assert len(ids) == len(set(ids))

    def test_map_matches_list(self):
        assert len(ACHIEVEMENT_MAP) == len(ACHIEVEMENTS)

    def test_all_have_required_fields(self):
        for a in ACHIEVEMENTS:
            assert a.name
            assert a.description
            assert a.category in ("betting", "streak", "bankroll", "analytics", "community")
            assert a.tier in ("bronze", "silver", "gold", "diamond")
            assert a.threshold > 0
            assert a.points > 0


class TestEvaluateAchievements:
    def test_empty_stats(self):
        results = evaluate_achievements({})
        assert len(results) == len(ACHIEVEMENTS)
        assert all(not a["unlocked"] for a in results)

    def test_first_bet_unlocked(self):
        results = evaluate_achievements({"total_bets": 1})
        first = next(a for a in results if a["id"] == "first_bet")
        assert first["unlocked"] is True
        assert first["progress"] == 1
        assert first["progress_pct"] == 100

    def test_streak_achievement(self):
        results = evaluate_achievements({"longest_win_streak": 5})
        streak5 = next(a for a in results if a["id"] == "streak_5")
        assert streak5["unlocked"] is True
        streak10 = next(a for a in results if a["id"] == "streak_10")
        assert streak10["unlocked"] is False
        assert streak10["progress_pct"] == 50

    def test_profit_achievement(self):
        results = evaluate_achievements({"total_profit": 500})
        p500 = next(a for a in results if a["id"] == "profit_500")
        assert p500["unlocked"] is True
        p1000 = next(a for a in results if a["id"] == "profit_1000")
        assert p1000["unlocked"] is False

    def test_roi_requires_minimum_bets(self):
        results = evaluate_achievements({"roi_pct": 10, "total_bets": 5})
        roi10 = next(a for a in results if a["id"] == "roi_10")
        assert roi10["unlocked"] is False  # need 50 bets

    def test_roi_with_enough_bets(self):
        results = evaluate_achievements({"roi_pct": 10, "total_bets": 50})
        roi10 = next(a for a in results if a["id"] == "roi_10")
        assert roi10["unlocked"] is True

    def test_sports_diversity(self):
        results = evaluate_achievements({"unique_sports": 3})
        s3 = next(a for a in results if a["id"] == "sports_3")
        assert s3["unlocked"] is True

    def test_underdog_win(self):
        results = evaluate_achievements({"biggest_underdog_win": 350})
        dog = next(a for a in results if a["id"] == "underdog_win")
        assert dog["unlocked"] is True

    def test_community_picks(self):
        results = evaluate_achievements({"total_picks": 10})
        p10 = next(a for a in results if a["id"] == "picks_10")
        assert p10["unlocked"] is True


class TestGetAchievementSummary:
    def test_empty_summary(self):
        results = evaluate_achievements({})
        summary = get_achievement_summary(results)
        assert summary["total_unlocked"] == 0
        assert summary["total_points"] == 0
        assert summary["rank"] == "Rookie"

    def test_with_unlocked(self):
        results = evaluate_achievements({"total_bets": 100, "longest_win_streak": 10, "total_profit": 1000})
        summary = get_achievement_summary(results)
        assert summary["total_unlocked"] > 0
        assert summary["total_points"] > 0
        assert summary["rank"] != "Rookie"

    def test_tier_breakdown(self):
        results = evaluate_achievements({"total_bets": 1})
        summary = get_achievement_summary(results)
        assert "bronze" in summary["by_tier"]
        assert "diamond" in summary["by_tier"]
        assert summary["by_tier"]["bronze"]["unlocked"] >= 1

    def test_category_breakdown(self):
        results = evaluate_achievements({})
        summary = get_achievement_summary(results)
        assert "betting" in summary["by_category"]
        assert "streak" in summary["by_category"]

    def test_next_unlock_present(self):
        results = evaluate_achievements({})
        summary = get_achievement_summary(results)
        assert summary["next_unlock"] is not None
