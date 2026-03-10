"""Tests for the BallDontLie _parse_minutes helper."""

from sba.data.clients.balldontlie import _parse_minutes


class TestParseMinutes:
    def test_string_minutes_colon(self):
        assert abs(_parse_minutes("35:30") - 35.5) < 0.01

    def test_string_minutes_plain(self):
        assert _parse_minutes("35") == 35.0

    def test_integer(self):
        assert _parse_minutes(35) == 35.0

    def test_float(self):
        assert _parse_minutes(35.5) == 35.5

    def test_none(self):
        assert _parse_minutes(None) == 0.0

    def test_empty_string(self):
        assert _parse_minutes("") == 0.0

    def test_zero(self):
        assert _parse_minutes("0") == 0.0

    def test_invalid_string(self):
        assert _parse_minutes("N/A") == 0.0

    def test_colon_format_zero_seconds(self):
        assert _parse_minutes("30:00") == 30.0
