"""Tests for config loading — verify YAML parsing and defaults."""

import pytest
from src.config import load_config, RiskLimits, AppConfig


class TestConfigDefaults:
    def test_risk_limits_defaults(self):
        r = RiskLimits()
        assert r.max_single_position_pct == 25.0
        assert r.max_margin_utilization == 1.00  # full buying power
        assert r.daily_max_drawdown_pct == 3.0
        assert r.per_trade_max_loss_usd == 5000.0
        assert r.max_trades_per_day == 0  # unlimited
        assert r.max_trades_per_hour == 0  # unlimited
        assert r.min_time_between_trades_sec == 5  # debounce only
        assert r.max_hold_time_minutes == 0  # no limit
        assert r.daily_profit_target_usd == 20_000.0

    def test_app_config_defaults(self):
        c = AppConfig()
        assert c.trading_mode == "paper"
        assert c.ibkr.port == 7497
        assert c.ibkr.host == "127.0.0.1"


class TestConfigFromYAML:
    def test_load_config_reads_yaml(self):
        config = load_config()
        # Should read from paperclip/policies/risk-policy.yaml
        assert config.risk.max_single_position_pct == 25.0
        assert config.risk.max_margin_utilization == 1.00
        assert config.risk.daily_max_drawdown_pct == 3.0
        assert config.risk.per_trade_max_loss_usd == 5000.0
        assert config.risk.max_concurrent_positions == 20
        assert config.risk.max_position_value_usd == 500_000.0

    def test_env_overrides(self):
        config = load_config()
        # Should pick up from .env or defaults
        assert config.ibkr.host == "127.0.0.1"
        assert config.ibkr.port in (7496, 7497)
