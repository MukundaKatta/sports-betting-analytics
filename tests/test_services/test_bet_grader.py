"""Tests for bet grading/rating system."""

import pytest

from sba.services.bet_grader import grade_bet, grade_bets_batch


class TestGradeBet:
    def test_high_edge_gets_high_stars(self):
        grade = grade_bet("Lakers", "h2h", "Lakers vs Celtics", edge_pct=10.0, best_odds_american=-110)
        assert grade.stars >= 4

    def test_low_edge_gets_low_stars(self):
        grade = grade_bet("Lakers", "h2h", "Lakers vs Celtics", edge_pct=0.5, best_odds_american=-110)
        assert grade.stars <= 2

    def test_sharp_agreement_boosts_stars(self):
        without = grade_bet("Lakers", "h2h", "Test", edge_pct=3.0, best_odds_american=-110)
        with_sharp = grade_bet("Lakers", "h2h", "Test", edge_pct=3.0, best_odds_american=-110, sharp_book_agrees=True)
        assert with_sharp.stars >= without.stars

    def test_line_moving_toward_positive(self):
        grade = grade_bet("Lakers", "h2h", "Test", edge_pct=5.0, best_odds_american=-110, line_moving_toward=True)
        assert grade.movement_score > 50

    def test_line_moving_away_warning(self):
        grade = grade_bet("Lakers", "h2h", "Test", edge_pct=5.0, best_odds_american=-110, line_moving_away=True)
        assert grade.movement_score < 50
        assert len(grade.warnings) > 0

    def test_reverse_line_movement_strong_signal(self):
        grade = grade_bet("Lakers", "h2h", "Test", edge_pct=5.0, best_odds_american=-110,
                         line_moving_away=True, sharp_book_agrees=True)
        assert grade.movement_score > 80

    def test_confidence_levels(self):
        low = grade_bet("X", "h2h", "T", edge_pct=0.5, best_odds_american=-110)
        high = grade_bet("X", "h2h", "T", edge_pct=8.0, best_odds_american=-110, sharp_book_agrees=True)
        assert low.confidence in ("low", "medium")
        assert high.confidence in ("high", "very_high")

    def test_grade_labels(self):
        grade = grade_bet("X", "h2h", "T", edge_pct=10.0, best_odds_american=-110)
        assert grade.grade_label == "Strong Play"

    def test_live_market_warning(self):
        grade = grade_bet("X", "h2h", "T", edge_pct=5.0, best_odds_american=-110, is_live=True)
        assert any("Live" in w for w in grade.warnings)

    def test_stale_line_warning(self):
        grade = grade_bet("X", "h2h", "T", edge_pct=5.0, best_odds_american=-110, books_with_edge=1, total_books=8)
        assert any("1 book" in w for w in grade.warnings)

    def test_historical_hit_rate(self):
        grade = grade_bet("X", "h2h", "T", edge_pct=5.0, best_odds_american=-110, historical_hit_rate=70)
        assert grade.consistency_score == 70

    def test_overall_score_range(self):
        grade = grade_bet("X", "h2h", "T", edge_pct=5.0, best_odds_american=-110)
        assert 0 <= grade.overall_score <= 100

    def test_reasons_populated_for_good_bets(self):
        grade = grade_bet("X", "h2h", "T", edge_pct=6.0, best_odds_american=-110, sharp_book_agrees=True)
        assert len(grade.reasons) >= 2


class TestGradeBetsBatch:
    def test_batch_sorts_by_score(self):
        bets = [
            {"selection": "A", "market": "h2h", "event": "T", "edge_pct": 2.0, "best_odds_american": -110},
            {"selection": "B", "market": "h2h", "event": "T", "edge_pct": 8.0, "best_odds_american": -110},
            {"selection": "C", "market": "h2h", "event": "T", "edge_pct": 5.0, "best_odds_american": -110},
        ]
        grades = grade_bets_batch(bets)
        assert grades[0].overall_score >= grades[1].overall_score >= grades[2].overall_score

    def test_empty_batch(self):
        assert grade_bets_batch([]) == []
