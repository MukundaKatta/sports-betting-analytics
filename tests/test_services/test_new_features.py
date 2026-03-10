"""Tests for new v2.1 features: multibook, account limits, portfolio, splits, deep links."""

from __future__ import annotations

import pytest

from sba.utils.deep_links import get_deep_link, get_book_display_info


class TestDeepLinks:
    def test_known_book_returns_link(self):
        link = get_deep_link("draftkings", "Los Angeles Lakers", "Boston Celtics")
        assert link is not None
        assert "draftkings" in link
        assert "Boston+Celtics" in link or "Celtics" in link

    def test_fanduel_link(self):
        link = get_deep_link("fanduel", "Miami Heat", "Golden State Warriors")
        assert link is not None
        assert "fanduel" in link

    def test_unknown_book_returns_none(self):
        link = get_deep_link("unknown_book_xyz", "Team A", "Team B")
        assert link is None

    def test_empty_teams_returns_base_url(self):
        link = get_deep_link("draftkings")
        assert link is not None
        assert "draftkings" in link

    def test_book_display_info(self):
        info = get_book_display_info("draftkings")
        assert info["name"] == "DraftKings"
        assert info["has_deep_link"] is True

    def test_unknown_book_display_info(self):
        info = get_book_display_info("unknownbook")
        assert info["has_deep_link"] is False


class TestPortfolioBuilder:
    def test_empty_edges_returns_empty(self):
        from sba.services.portfolio import build_portfolio
        result = build_portfolio(edges=[], bankroll=1000)
        assert result["portfolio"] == []
        assert result["summary"]["total_bets"] == 0

    def test_portfolio_respects_max_bets(self):
        from sba.services.portfolio import build_portfolio
        result = build_portfolio(edges=[], bankroll=1000, max_bets=5)
        assert len(result["portfolio"]) <= 5

    def test_portfolio_has_generated_at(self):
        from sba.services.portfolio import build_portfolio
        result = build_portfolio(edges=[], bankroll=1000)
        assert "generated_at" in result


class TestAccountLimits:
    def test_severity_levels_exist(self):
        from sba.services.account_limits import SEVERITY_LEVELS
        assert "none" in SEVERITY_LEVELS
        assert "banned" in SEVERITY_LEVELS
        assert SEVERITY_LEVELS["banned"]["score"] > SEVERITY_LEVELS["none"]["score"]

    def test_limit_types_exist(self):
        from sba.services.account_limits import LIMIT_TYPES
        assert "none" in LIMIT_TYPES
        assert "stake_reduced" in LIMIT_TYPES
        assert "closed" in LIMIT_TYPES

    def test_tips_not_empty(self):
        from sba.services.account_limits import LIMITING_TIPS
        assert len(LIMITING_TIPS) > 0


class TestMultibook:
    def test_sportsbook_info_exists(self):
        from sba.services.multibook import SPORTSBOOK_INFO
        assert "draftkings" in SPORTSBOOK_INFO
        assert "fanduel" in SPORTSBOOK_INFO
        assert "pinnacle" in SPORTSBOOK_INFO
        for key, info in SPORTSBOOK_INFO.items():
            assert "name" in info
            assert "color" in info

    def test_sportsbook_info_has_urls(self):
        from sba.services.multibook import SPORTSBOOK_INFO
        for key, info in SPORTSBOOK_INFO.items():
            assert "url" in info
            assert info["url"].startswith("https://")


class TestSituationSplits:
    def test_stat_fields_defined(self):
        from sba.services.situation_splits import STAT_FIELDS
        assert "points" in STAT_FIELDS
        assert "rebounds" in STAT_FIELDS
        assert "assists" in STAT_FIELDS
        assert "threes" in STAT_FIELDS

    def test_invalid_stat_returns_error(self):
        from sba.services.situation_splits import get_situation_splits
        result = get_situation_splits("Nonexistent Player", "invalid_stat")
        assert "error" in result


class TestDomainModels:
    def test_book_balance_model(self):
        from sba.models.domain import BookBalance
        b = BookBalance(sportsbook="draftkings", balance=500.0, deposited=400.0)
        assert b.sportsbook == "draftkings"
        assert b.balance == 500.0
        assert b.is_limited is False

    def test_account_limit_model(self):
        from sba.models.domain import AccountLimit
        l = AccountLimit(sportsbook="fanduel", limit_type="stake_reduced",
                         severity="medium", max_stake=50.0)
        assert l.sportsbook == "fanduel"
        assert l.max_stake == 50.0

    def test_portfolio_bet_model(self):
        from sba.models.domain import PortfolioBet
        p = PortfolioBet(
            event_id="test", event_name="Test Game",
            market="h2h", selection="Team A",
            bookmaker="dk", odds_american=150, odds_decimal=2.5,
            ev_pct=5.0, kelly_pct=0.03, recommended_stake=25.0,
        )
        assert p.ev_pct == 5.0

    def test_situation_split_model(self):
        from sba.models.domain import SituationSplit
        s = SituationSplit(
            situation="home", label="Home Games",
            games=20, avg_value=25.5, hit_rate=65.0,
        )
        assert s.trend == "flat"
