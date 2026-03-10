"""Tests for sharp money detection service."""

import pytest
from datetime import datetime

from sba.models.domain import OddsSnapshot
from sba.services.sharp_money import (
    analyze_line_signals,
    calculate_clv,
    detect_sharp_moves,
)


def _snap(bookmaker, outcome, american, decimal, point=None, time="2025-03-15T12:00:00"):
    return OddsSnapshot(
        event_id="test_1", bookmaker=bookmaker, market="h2h",
        outcome_name=outcome, outcome_point=point,
        price_american=american, price_decimal=decimal,
        snapshot_time=datetime.fromisoformat(time),
    )


class TestDetectSharpMoves:
    def test_detects_large_movement(self):
        """A 30+ point American odds move should be detected."""
        snaps = [
            _snap("fanduel", "Lakers", -110, 1.909, time="2025-03-15T10:00:00"),
            _snap("fanduel", "Lakers", -145, 1.69, time="2025-03-15T14:00:00"),
        ]
        moves = detect_sharp_moves(snaps)
        assert len(moves) == 1
        assert moves[0].odds_before == -110
        assert moves[0].odds_after == -145

    def test_ignores_small_movement(self):
        """Small movements under threshold should be ignored."""
        snaps = [
            _snap("fanduel", "Lakers", -110, 1.909, time="2025-03-15T10:00:00"),
            _snap("fanduel", "Lakers", -115, 1.87, time="2025-03-15T14:00:00"),
        ]
        moves = detect_sharp_moves(snaps)
        assert len(moves) == 0

    def test_detects_sharp_book_origin(self):
        """Moves at sharp books (Pinnacle) should be flagged as sharp_book_origin."""
        snaps = [
            _snap("pinnacle", "Lakers", -105, 1.95, time="2025-03-15T10:00:00"),
            _snap("pinnacle", "Lakers", -130, 1.77, time="2025-03-15T14:00:00"),
        ]
        moves = detect_sharp_moves(snaps)
        assert len(moves) == 1
        assert moves[0].move_type == "sharp_book_origin"

    def test_empty_snapshots(self):
        assert detect_sharp_moves([]) == []

    def test_single_snapshot_no_moves(self):
        snaps = [_snap("fanduel", "Lakers", -110, 1.909)]
        assert detect_sharp_moves(snaps) == []

    def test_sorted_by_magnitude(self):
        """Results should be sorted by magnitude descending."""
        snaps = [
            _snap("fanduel", "Lakers", -110, 1.909, time="2025-03-15T10:00:00"),
            _snap("fanduel", "Lakers", -145, 1.69, time="2025-03-15T14:00:00"),
            _snap("draftkings", "Celtics", 100, 2.0, time="2025-03-15T10:00:00"),
            _snap("draftkings", "Celtics", 160, 2.6, time="2025-03-15T14:00:00"),
        ]
        moves = detect_sharp_moves(snaps)
        if len(moves) >= 2:
            assert moves[0].magnitude >= moves[1].magnitude


class TestAnalyzeLineSignals:
    def test_generates_signals_for_movement(self):
        snaps = [
            _snap("fanduel", "Lakers", -110, 1.909, time="2025-03-15T10:00:00"),
            _snap("fanduel", "Lakers", -140, 1.71, time="2025-03-15T14:00:00"),
        ]
        signals = analyze_line_signals(snaps)
        assert len(signals) == 1
        assert signals[0].signal_type in ("steam_move", "line_movement", "sharp_book_origin")
        assert "Lakers" in signals[0].description

    def test_empty_snapshots(self):
        assert analyze_line_signals([]) == []

    def test_confidence_levels(self):
        """Big moves at sharp books should be high confidence."""
        snaps = [
            _snap("pinnacle", "Lakers", -100, 2.0, time="2025-03-15T10:00:00"),
            _snap("pinnacle", "Lakers", -160, 1.625, time="2025-03-15T14:00:00"),
        ]
        signals = analyze_line_signals(snaps)
        assert len(signals) == 1
        assert signals[0].confidence == "high"


class TestCalculateCLV:
    def test_positive_clv(self):
        """Getting better odds than closing = positive CLV."""
        result = calculate_clv(placed_odds_american=150, closing_odds_american=120)
        assert result["beat_closing"] is True
        assert result["clv_percentage"] > 0

    def test_negative_clv(self):
        """Getting worse odds than closing = negative CLV."""
        result = calculate_clv(placed_odds_american=-150, closing_odds_american=-130)
        assert result["beat_closing"] is False
        assert result["clv_percentage"] < 0

    def test_same_odds_zero_clv(self):
        """Same odds = zero CLV."""
        result = calculate_clv(placed_odds_american=-110, closing_odds_american=-110)
        assert result["clv_percentage"] == 0
        assert result["clv_american"] == 0

    def test_returns_all_fields(self):
        result = calculate_clv(200, 150)
        assert "placed_odds" in result
        assert "closing_odds" in result
        assert "clv_american" in result
        assert "clv_percentage" in result
        assert "beat_closing" in result
