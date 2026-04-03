"""Tests for config loading — verify defaults and env loading."""

import pytest
from tools.config import load_config, RiskLimits, AppConfig


class TestConfigDefaults:
    def test_risk_limits_defaults(self):
        r = RiskLimits()
        assert r.max_single_position_pct == 25.0
        assert r.max_margin_utilization == 1.00
        assert r.daily_max_drawdown_pct == 3.0
        assert r.per_trade_max_loss_usd == 5000.0
        assert r.max_trades_per_day == 0
        assert r.max_trades_per_hour == 0
        assert r.min_time_between_trades_sec == 5
        assert r.max_hold_time_minutes == 0
        assert r.daily_profit_target_usd == 20_000.0

    def test_app_config_defaults(self):
        c = AppConfig()
        assert c.trading_mode == "paper"
        assert c.ibkr.port == 4002
        assert c.ibkr.host == "127.0.0.1"


class TestConfigFromEnv:
    def test_load_config(self):
        config = load_config()
        assert config.risk.max_single_position_pct == 25.0
        assert config.risk.max_margin_utilization == 1.00
        assert config.risk.daily_max_drawdown_pct == 3.0
        assert config.ibkr.host == "127.0.0.1"
        assert config.ibkr.port > 0
