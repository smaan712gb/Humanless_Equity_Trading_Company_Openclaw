"""Configuration loader — reads from environment variables.
Risk limits are hardcoded defaults matching the risk-gatekeeper skill.
Paperclip handles budgets and governance; this is for Python tools only."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).parent.parent


@dataclass
class IBKRConfig:
    host: str = "127.0.0.1"
    port: int = 4002
    client_id: int = 1
    timeout: int = 30


@dataclass
class DeepSeekConfig:
    api_key: str = ""
    chat_model: str = "deepseek-chat"
    reasoner_model: str = "deepseek-reasoner"
    api_base: str = "https://api.deepseek.com"
    max_tokens: int = 8192
    timeout: int = 60


@dataclass
class RiskLimits:
    max_single_position_pct: float = 25.0
    max_sector_exposure_pct: float = 50.0
    max_concurrent_positions: int = 20
    max_position_value_usd: float = 500_000.0
    daily_max_drawdown_pct: float = 3.0
    per_trade_max_loss_usd: float = 5000.0
    max_trades_per_day: int = 0
    max_trades_per_hour: int = 0
    min_time_between_trades_sec: int = 5
    max_margin_utilization: float = 1.00
    max_hold_time_minutes: int = 0
    daily_profit_target_usd: float = 20_000.0
    trailing_stop_pct: float = 1.5
    take_profit_ratio: float = 2.0


@dataclass
class AppConfig:
    ibkr: IBKRConfig = field(default_factory=IBKRConfig)
    deepseek: DeepSeekConfig = field(default_factory=DeepSeekConfig)
    risk: RiskLimits = field(default_factory=RiskLimits)
    trading_mode: str = "paper"
    log_level: str = "INFO"


def load_config() -> AppConfig:
    config = AppConfig()
    config.trading_mode = os.getenv("TRADING_MODE", "paper")
    config.ibkr.host = os.getenv("IBKR_HOST", "127.0.0.1")
    config.ibkr.port = int(os.getenv("IBKR_PORT", "4002"))
    config.ibkr.client_id = int(os.getenv("IBKR_CLIENT_ID", "1"))
    config.deepseek.api_key = os.getenv("DEEPSEEK_API_KEY", "")
    return config
