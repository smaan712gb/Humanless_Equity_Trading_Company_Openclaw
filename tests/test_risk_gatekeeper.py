"""Tests for risk gatekeeper — verify all checks and circuit breakers."""

import pytest
from unittest.mock import patch
from datetime import datetime, time

from src.config import RiskLimits
from src.risk_gatekeeper import RiskGatekeeper
from src.models import (
    TradePlan, PortfolioState, Direction, CircuitBreakerAction,
)


def _limits():
    return RiskLimits(
        max_single_position_pct=25.0,
        max_sector_exposure_pct=50.0,
        max_concurrent_positions=20,
        max_position_value_usd=500_000.0,
        daily_max_drawdown_pct=3.0,
        per_trade_max_loss_usd=5000.0,
        min_time_between_trades_sec=5,
        max_margin_utilization=1.00,
        daily_profit_target_usd=20_000.0,
        trailing_stop_pct=1.5,
        take_profit_ratio=2.0,
    )


def _gatekeeper():
    return RiskGatekeeper(_limits())


def _portfolio():
    return PortfolioState(
        equity=500_000, buying_power=500_000,
        margin_used_pct=0.20, daily_pnl=5000, daily_pnl_pct=1.0,
        position_count=3,
    )


def _valid_plan():
    return TradePlan(
        ticker="LITE", strategy="momentum_breakout",
        direction=Direction.LONG, entry_price=100.0,
        stop_loss=97.0, take_profit=106.0, shares=100,
    )


# Shared mock context for "market is open" state
_MARKET_OPEN_PATCHES = {
    "src.risk_gatekeeper.is_market_holiday": False,
    "src.risk_gatekeeper.is_any_session_active": True,
    "src.risk_gatekeeper.get_position_size_multiplier": 1.0,
    "src.risk_gatekeeper.can_use_market_orders": True,
}


def _with_market_open(func):
    """Decorator to mock market as open for a test function."""
    for target, value in _MARKET_OPEN_PATCHES.items():
        func = patch(target, return_value=value)(func)
    return func


class TestValidateTrade:
    @_with_market_open
    def test_valid_trade_approved(self, *mocks):
        result = _gatekeeper().validate_trade(_valid_plan(), _portfolio())
        assert result.approved is True
        assert result.message == "All checks passed"

    @_with_market_open
    def test_position_too_large(self, *mocks):
        big_plan = TradePlan(
            ticker="ASML", strategy="momentum_breakout",
            direction=Direction.LONG, entry_price=800.0,
            stop_loss=780.0, take_profit=840.0, shares=200,
        )
        result = _gatekeeper().validate_trade(big_plan, _portfolio())
        assert result.approved is False
        assert "position_size" in result.violations

    @_with_market_open
    def test_no_stop_loss_rejected(self, *mocks):
        no_stop = TradePlan(
            ticker="MU", strategy="scalp",
            direction=Direction.LONG, entry_price=100.0,
            stop_loss=0, take_profit=103.0, shares=50,
        )
        result = _gatekeeper().validate_trade(no_stop, _portfolio())
        assert result.approved is False
        assert "no_stop_loss" in result.violations

    @patch("src.risk_gatekeeper.is_market_holiday", return_value=True)
    @patch("src.risk_gatekeeper.is_any_session_active", return_value=False)
    @patch("src.risk_gatekeeper.get_position_size_multiplier", return_value=0.0)
    def test_holiday_rejected(self, *mocks):
        result = _gatekeeper().validate_trade(_valid_plan(), _portfolio())
        assert result.approved is False
        assert "market_closed_holiday" in result.violations

    @_with_market_open
    def test_per_trade_max_loss(self, *mocks):
        risky = TradePlan(
            ticker="LITE", strategy="momentum_breakout",
            direction=Direction.LONG, entry_price=100.0,
            stop_loss=80.0, take_profit=140.0, shares=300,
        )
        result = _gatekeeper().validate_trade(risky, _portfolio())
        assert result.approved is False
        assert "per_trade_max_loss" in result.violations

    @_with_market_open
    def test_drawdown_breached(self, *mocks):
        bad_day = PortfolioState(equity=500_000, daily_pnl=-16000, daily_pnl_pct=-3.2)
        result = _gatekeeper().validate_trade(_valid_plan(), bad_day)
        assert result.approved is False
        assert "drawdown_breached" in result.violations

    @_with_market_open
    def test_max_positions_reached(self, *mocks):
        limits = _limits()
        limits.max_concurrent_positions = 5
        gk = RiskGatekeeper(limits)
        full = PortfolioState(equity=500_000, position_count=5)
        result = gk.validate_trade(_valid_plan(), full)
        assert result.approved is False
        assert "position_count" in result.violations

    @_with_market_open
    def test_full_margin_rejected(self, *mocks):
        maxed = PortfolioState(equity=500_000, margin_used_pct=1.01)
        result = _gatekeeper().validate_trade(_valid_plan(), maxed)
        assert result.approved is False
        assert "margin" in result.violations


class TestCircuitBreakers:
    def test_drawdown_liquidate(self):
        portfolio = PortfolioState(equity=500_000, daily_pnl_pct=-3.5)
        assert _gatekeeper().check_circuit_breakers(portfolio) == CircuitBreakerAction.EMERGENCY_LIQUIDATE_ALL

    def test_equity_floor_shutdown(self):
        portfolio = PortfolioState(equity=90_000, daily_pnl_pct=0)
        assert _gatekeeper().check_circuit_breakers(portfolio) == CircuitBreakerAction.FULL_SHUTDOWN

    def test_vix_spike_reduce(self):
        portfolio = PortfolioState(equity=500_000, daily_pnl_pct=0)
        assert _gatekeeper().check_circuit_breakers(portfolio, vix=42) == CircuitBreakerAction.REDUCE_ALL_50PCT

    def test_spy_crash_halt(self):
        portfolio = PortfolioState(equity=500_000, daily_pnl_pct=0)
        assert _gatekeeper().check_circuit_breakers(portfolio, spy_change_pct=-3.5) == CircuitBreakerAction.HALT_NEW_ENTRIES

    def test_all_clear(self):
        portfolio = PortfolioState(equity=500_000, daily_pnl_pct=1.0)
        assert _gatekeeper().check_circuit_breakers(portfolio, vix=20, spy_change_pct=-0.5) == CircuitBreakerAction.ALL_CLEAR


class TestTradeRecording:
    def test_record_and_reset(self):
        gk = _gatekeeper()
        gk.record_trade()
        assert gk._trade_count_today == 1
        gk.record_trade()
        assert gk._trade_count_today == 2
        gk.reset_daily()
        assert gk._trade_count_today == 0

    @_with_market_open
    def test_debounce(self, *mocks):
        gk = _gatekeeper()
        gk.record_trade()
        result = gk.validate_trade(_valid_plan(), _portfolio())
        assert result.approved is False
        assert "trade_debounce" in result.violations
