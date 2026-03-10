"""Tests for settings validation."""

import pytest
from pydantic import ValidationError

from sba.config.settings import Settings


class TestSettingsValidation:
    def test_default_settings_valid(self):
        s = Settings()
        assert s.KELLY_FRACTION == 0.25
        assert s.BANKROLL == 1000.0

    def test_kelly_fraction_zero_rejected(self):
        with pytest.raises(ValidationError):
            Settings(KELLY_FRACTION=0)

    def test_kelly_fraction_negative_rejected(self):
        with pytest.raises(ValidationError):
            Settings(KELLY_FRACTION=-0.5)

    def test_kelly_fraction_over_one_rejected(self):
        with pytest.raises(ValidationError):
            Settings(KELLY_FRACTION=1.5)

    def test_kelly_fraction_one_accepted(self):
        s = Settings(KELLY_FRACTION=1.0)
        assert s.KELLY_FRACTION == 1.0

    def test_bankroll_negative_rejected(self):
        with pytest.raises(ValidationError):
            Settings(BANKROLL=-100)

    def test_bankroll_zero_rejected(self):
        with pytest.raises(ValidationError):
            Settings(BANKROLL=0)

    def test_ev_threshold_negative_rejected(self):
        with pytest.raises(ValidationError):
            Settings(EV_THRESHOLD=-0.01)

    def test_ev_threshold_zero_accepted(self):
        s = Settings(EV_THRESHOLD=0.0)
        assert s.EV_THRESHOLD == 0.0

    def test_refresh_interval_too_low_rejected(self):
        with pytest.raises(ValidationError):
            Settings(REFRESH_INTERVAL_SECONDS=5)

    def test_invalid_log_level_rejected(self):
        with pytest.raises(ValidationError):
            Settings(LOG_LEVEL="VERBOSE")

    def test_log_level_case_normalized(self):
        s = Settings(LOG_LEVEL="debug")
        assert s.LOG_LEVEL == "DEBUG"
