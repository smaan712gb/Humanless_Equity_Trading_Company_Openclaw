"""Configuration loader — reads YAML configs and environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).parent.parent


@dataclass
class IBKRConfig:
    host: str = "127.0.0.1"
    port: int = 7497
    client_id: int = 1
    timeout: int = 10


@dataclass
class DeepSeekConfig:
    api_key: str = ""
    chat_model: str = "deepseek-chat"
    reasoner_model: str = "deepseek-reasoner"
    api_base: str = "https://api.deepseek.com/v1"
    max_tokens: int = 8192
    timeout: int = 60


@dataclass
class RiskLimits:
    max_single_position_pct: float = 15.0
    max_sector_exposure_pct: float = 30.0
    max_concurrent_positions: int = 8
    max_position_value_usd: float = 100_000.0
    daily_max_drawdown_pct: float = 2.0
    per_trade_max_loss_usd: float = 2500.0
    max_trades_per_day: int = 40
    max_trades_per_hour: int = 10
    min_time_between_trades_sec: int = 30
    max_margin_utilization: float = 0.60
    max_hold_time_minutes: int = 120
    daily_profit_target_usd: float = 20_000.0
    trailing_stop_pct: float = 1.5
    take_profit_ratio: float = 2.0
    force_flatten_time: str = "15:50"
    no_new_entries_after: str = "15:30"


@dataclass
class AppConfig:
    ibkr: IBKRConfig = field(default_factory=IBKRConfig)
    deepseek: DeepSeekConfig = field(default_factory=DeepSeekConfig)
    risk: RiskLimits = field(default_factory=RiskLimits)
    trading_mode: str = "paper"
    log_level: str = "INFO"


def load_config() -> AppConfig:
    config = AppConfig()

    # Environment overrides
    config.trading_mode = os.getenv("TRADING_MODE", "paper")
    config.ibkr.host = os.getenv("IBKR_HOST", "127.0.0.1")
    config.ibkr.port = int(os.getenv("IBKR_PORT", "7497"))
    config.ibkr.client_id = int(os.getenv("IBKR_CLIENT_ID", "1"))
    config.deepseek.api_key = os.getenv("DEEPSEEK_API_KEY", "")

    # Load risk policy from YAML
    risk_path = PROJECT_ROOT / "paperclip" / "policies" / "risk-policy.yaml"
    if risk_path.exists():
        with open(risk_path) as f:
            risk_yaml = yaml.safe_load(f)

        pl = risk_yaml.get("position_limits", {})
        config.risk.max_single_position_pct = pl.get("max_single_position_pct", 15.0)
        config.risk.max_sector_exposure_pct = pl.get("max_sector_exposure_pct", 30.0)
        config.risk.max_concurrent_positions = pl.get("max_concurrent_positions", 8)
        config.risk.max_position_value_usd = pl.get("max_position_value_usd", 100_000.0)

        ll = risk_yaml.get("loss_limits", {})
        config.risk.daily_max_drawdown_pct = ll.get("daily_max_drawdown_pct", 2.0)
        config.risk.per_trade_max_loss_usd = ll.get("per_trade_max_loss_usd", 2500.0)

        el = risk_yaml.get("execution_limits", {})
        config.risk.max_trades_per_day = el.get("max_trades_per_day", 40)
        config.risk.max_trades_per_hour = el.get("max_trades_per_hour", 10)
        config.risk.min_time_between_trades_sec = el.get("min_time_between_trades_sec", 30)

        pt = risk_yaml.get("profit_targets", {})
        config.risk.daily_profit_target_usd = pt.get("daily_profit_target_usd", 20_000.0)

        hb = risk_yaml.get("high_beta_specific", {})
        config.risk.max_hold_time_minutes = hb.get("max_hold_time_minutes", 120)
        config.risk.trailing_stop_pct = hb.get("trailing_stop_pct", 1.5)
        config.risk.take_profit_ratio = hb.get("take_profit_ratio", 2.0)

    return config
