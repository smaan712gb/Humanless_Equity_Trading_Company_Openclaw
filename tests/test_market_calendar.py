"""Tests for market calendar — holidays, sessions, and trading hours."""

import pytest
from datetime import date, datetime, time
from src.market_calendar import (
    is_market_holiday, is_early_close, get_close_time,
    get_current_session, Session, is_any_session_active,
    requires_outside_rth, get_position_size_multiplier,
    can_use_market_orders, next_trading_day, get_session_info,
)


class TestHolidays:
    def test_good_friday_2026(self):
        assert is_market_holiday(date(2026, 4, 3)) is True

    def test_christmas_2026(self):
        assert is_market_holiday(date(2026, 12, 25)) is True

    def test_regular_trading_day(self):
        # Monday April 6, 2026
        assert is_market_holiday(date(2026, 4, 6)) is False

    def test_saturday(self):
        assert is_market_holiday(date(2026, 4, 4)) is True

    def test_sunday(self):
        assert is_market_holiday(date(2026, 4, 5)) is True

    def test_all_2026_holidays(self):
        holidays = [
            date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16),
            date(2026, 4, 3), date(2026, 5, 25), date(2026, 6, 19),
            date(2026, 7, 3), date(2026, 9, 7), date(2026, 11, 26),
            date(2026, 12, 25),
        ]
        for h in holidays:
            assert is_market_holiday(h) is True, f"{h} should be a holiday"


class TestEarlyClose:
    def test_day_after_thanksgiving(self):
        assert is_early_close(date(2026, 11, 27)) is True

    def test_christmas_eve(self):
        assert is_early_close(date(2026, 12, 24)) is True

    def test_regular_day(self):
        assert is_early_close(date(2026, 4, 6)) is False

    def test_close_time_early(self):
        assert get_close_time(date(2026, 11, 27)) == time(13, 0)

    def test_close_time_normal(self):
        assert get_close_time(date(2026, 4, 6)) == time(16, 0)


class TestSessions:
    def test_eth_pre_market(self):
        # Monday 7:00 AM ET
        dt = datetime(2026, 4, 6, 7, 0, 0)
        assert get_current_session(dt) == Session.ETH_PRE_MARKET

    def test_rth(self):
        # Monday 10:30 AM ET
        dt = datetime(2026, 4, 6, 10, 30, 0)
        assert get_current_session(dt) == Session.RTH

    def test_eth_after_hours(self):
        # Monday 5:00 PM ET
        dt = datetime(2026, 4, 6, 17, 0, 0)
        assert get_current_session(dt) == Session.ETH_AFTER_HOURS

    def test_overnight(self):
        # Monday 11:00 PM ET
        dt = datetime(2026, 4, 6, 23, 0, 0)
        assert get_current_session(dt) == Session.OVERNIGHT

    def test_holiday_closed(self):
        # Good Friday 10:00 AM
        dt = datetime(2026, 4, 3, 10, 0, 0)
        assert get_current_session(dt) == Session.CLOSED

    def test_eth_boundary_start(self):
        dt = datetime(2026, 4, 6, 4, 0, 0)
        assert get_current_session(dt) == Session.ETH_PRE_MARKET

    def test_rth_boundary_start(self):
        dt = datetime(2026, 4, 6, 9, 30, 0)
        assert get_current_session(dt) == Session.RTH

    def test_eth_ah_boundary_start(self):
        dt = datetime(2026, 4, 6, 16, 0, 0)
        assert get_current_session(dt) == Session.ETH_AFTER_HOURS

    def test_early_close_day_session(self):
        # Nov 27, 2026 at 14:00 — market closed at 13:00, so this is ETH after-hours
        dt = datetime(2026, 11, 27, 14, 0, 0)
        assert get_current_session(dt) == Session.ETH_AFTER_HOURS


class TestSessionProperties:
    def test_active_during_rth(self):
        dt = datetime(2026, 4, 6, 11, 0, 0)
        assert is_any_session_active(dt) is True

    def test_active_during_eth(self):
        dt = datetime(2026, 4, 6, 5, 0, 0)
        assert is_any_session_active(dt) is True

    def test_not_active_overnight(self):
        dt = datetime(2026, 4, 6, 2, 0, 0)
        assert is_any_session_active(dt) is False

    def test_outside_rth_pre_market(self):
        dt = datetime(2026, 4, 6, 7, 0, 0)
        assert requires_outside_rth(dt) is True

    def test_not_outside_rth_during_rth(self):
        dt = datetime(2026, 4, 6, 11, 0, 0)
        assert requires_outside_rth(dt) is False

    def test_size_multiplier_rth(self):
        dt = datetime(2026, 4, 6, 11, 0, 0)
        assert get_position_size_multiplier(dt) == 1.0

    def test_size_multiplier_eth(self):
        dt = datetime(2026, 4, 6, 7, 0, 0)
        assert get_position_size_multiplier(dt) == 0.5

    def test_size_multiplier_overnight(self):
        dt = datetime(2026, 4, 6, 2, 0, 0)
        assert get_position_size_multiplier(dt) == 0.0

    def test_market_orders_rth_only(self):
        assert can_use_market_orders(datetime(2026, 4, 6, 11, 0)) is True
        assert can_use_market_orders(datetime(2026, 4, 6, 7, 0)) is False
        assert can_use_market_orders(datetime(2026, 4, 6, 17, 0)) is False


class TestNextTradingDay:
    def test_friday_to_monday(self):
        # Good Friday 2026 → skip weekend → Monday
        assert next_trading_day(date(2026, 4, 3)) == date(2026, 4, 6)

    def test_thursday_to_friday_skip_holiday(self):
        # Thursday April 2 → skip Good Friday → Monday April 6
        assert next_trading_day(date(2026, 4, 2)) == date(2026, 4, 6)

    def test_regular_day(self):
        # Monday → Tuesday
        assert next_trading_day(date(2026, 4, 6)) == date(2026, 4, 7)

    def test_friday_to_monday_normal(self):
        # Friday April 10 → Monday April 13
        assert next_trading_day(date(2026, 4, 10)) == date(2026, 4, 13)


class TestSessionInfo:
    def test_returns_dict(self):
        info = get_session_info()
        assert "date" in info
        assert "session" in info
        assert "can_trade" in info
        assert "size_multiplier" in info
        assert "next_trading_day" in info
