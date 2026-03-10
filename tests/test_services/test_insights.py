"""Tests for the insights engine and bet rating system."""

from datetime import datetime

from sba.services.insights import Insight, generate_insights, rate_bet


def _bet(status="won", sport="basketball_nba", market="h2h", bookmaker="fanduel",
         odds=-150, stake=100, profit=66.67, placed_at=None):
    return {
        "status": status,
        "sport": sport,
        "market": market,
        "bookmaker": bookmaker,
        "odds_american": odds,
        "stake": stake,
        "profit_loss": profit if status == "won" else -stake,
        "placed_at": placed_at or datetime(2025, 3, 15, 14, 0),
    }


class TestGenerateInsights:
    def test_empty_bets(self):
        insights = generate_insights([])
        assert len(insights) == 1
        assert insights[0].id == "no_data"

    def test_returns_insights(self):
        bets = [_bet(status="won") for _ in range(5)] + [_bet(status="lost") for _ in range(5)]
        insights = generate_insights(bets)
        assert len(insights) >= 0
        assert all(isinstance(i, Insight) for i in insights)

    def test_hot_streak_detected(self):
        bets = [_bet(status="won") for _ in range(6)]
        insights = generate_insights(bets)
        ids = [i.id for i in insights]
        assert "hot_streak" in ids

    def test_cold_streak_detected(self):
        bets = [_bet(status="won")] + [_bet(status="lost") for _ in range(6)]
        insights = generate_insights(bets)
        ids = [i.id for i in insights]
        assert "cold_streak" in ids

    def test_single_book_insight(self):
        bets = [_bet(bookmaker="fanduel") for _ in range(5)]
        insights = generate_insights(bets)
        ids = [i.id for i in insights]
        assert "single_book" in ids

    def test_sorted_by_severity(self):
        bets = [_bet(status="won")] + [_bet(status="lost") for _ in range(6)]
        insights = generate_insights(bets)
        severity_order = {"critical": 0, "warning": 1, "success": 2, "info": 3}
        severities = [severity_order.get(i.severity, 99) for i in insights]
        assert severities == sorted(severities)

    def test_great_roi_insight(self):
        bets = [_bet(status="won", stake=100, profit=66.67) for _ in range(20)]
        insights = generate_insights(bets)
        ids = [i.id for i in insights]
        assert "great_roi" in ids


class TestRateBet:
    def test_high_ev_gets_high_stars(self):
        rating = rate_bet(-110, ev_pct=12.0, kelly=0.06)
        assert rating["stars"] >= 4
        assert rating["label"] in ("Strong", "Elite")

    def test_no_edge_gets_low_stars(self):
        rating = rate_bet(-110)
        assert rating["stars"] <= 2

    def test_moderate_ev(self):
        rating = rate_bet(-110, ev_pct=5.0, kelly=0.02)
        assert rating["stars"] >= 3

    def test_returns_required_fields(self):
        rating = rate_bet(-110, ev_pct=3.0)
        assert "stars" in rating
        assert "score" in rating
        assert "label" in rating
        assert "color" in rating
        assert "factors" in rating
        assert isinstance(rating["factors"], list)

    def test_model_probability_edge(self):
        rating = rate_bet(-150, model_prob=0.75, ev_pct=8.0)
        assert rating["stars"] >= 3
        assert any("model edge" in f.lower() for f in rating["factors"])

    def test_clv_bonus(self):
        r1 = rate_bet(-110, ev_pct=5.0)
        r2 = rate_bet(-110, ev_pct=5.0, clv=6.0)
        assert r2["score"] > r1["score"]
