"""Data models for the trading system."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Direction(str, enum.Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class OrderType(str, enum.Enum):
    LIMIT = "LIMIT"
    MARKET = "MARKET"
    STOP = "STOP"
    TRAILING_STOP = "TRAIL"


class TradeStatus(str, enum.Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    PARTIAL = "PARTIAL"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class Severity(str, enum.Enum):
    CRITICAL = "CRITICAL"
    MAJOR = "MAJOR"
    MINOR = "MINOR"


class CircuitBreakerAction(str, enum.Enum):
    ALL_CLEAR = "ALL_CLEAR"
    HALT_NEW_ENTRIES = "HALT_NEW_ENTRIES"
    REDUCE_ALL_50PCT = "REDUCE_ALL_50PCT"
    EMERGENCY_LIQUIDATE_ALL = "EMERGENCY_LIQUIDATE_ALL"
    FULL_SHUTDOWN = "FULL_SHUTDOWN"
    FLATTEN_ALL = "FLATTEN_ALL"


class ScoutReport(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.now)
    ticker: str
    beta: float
    volume_ratio: float  # today vs 20d avg
    atr_pct: float
    catalyst: str = "None — pure momentum"
    sector: str = ""
    recommendation: str = "INVESTIGATE"  # INVESTIGATE / WATCH / SKIP


class AnalystReport(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.now)
    ticker: str
    edge_score: int = Field(ge=1, le=10)
    catalyst: str = ""
    catalyst_quality: str = "None"  # Strong / Moderate / Weak / None
    support: float = 0.0
    resistance: float = 0.0
    vwap: float = 0.0
    atr: float = 0.0
    atr_pct: float = 0.0
    fundamental_flags: str = ""
    historical_comparables: str = ""
    recommendation: str = "PASS"  # TRADEABLE / MARGINAL / PASS
    reasoning: str = ""


class TradePlan(BaseModel):
    id: str = ""
    timestamp: datetime = Field(default_factory=datetime.now)
    ticker: str
    strategy: str
    direction: Direction
    entry_price: float
    stop_loss: float
    take_profit: float
    shares: int
    notional: float = 0.0
    kelly_p: float = 0.0
    kelly_b: float = 0.0
    kelly_f_star: float = 0.0
    kelly_fraction: str = "half"  # half / quarter
    confidence: int = Field(default=5, ge=1, le=10)
    requires_ceo_approval: bool = False
    scout_report: Optional[ScoutReport] = None
    analyst_report: Optional[AnalystReport] = None

    def model_post_init(self, __context):
        if not self.notional:
            self.notional = self.shares * self.entry_price
        if not self.id:
            self.id = f"TP-{self.ticker}-{self.timestamp.strftime('%H%M%S')}"


class ExecutionReport(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.now)
    trade_plan_id: str
    order_id: int = 0
    ticker: str
    direction: Direction
    shares_requested: int
    shares_filled: int = 0
    order_type: OrderType = OrderType.LIMIT
    intended_price: float = 0.0
    fill_price: float = 0.0
    slippage_pct: float = 0.0
    slippage_usd: float = 0.0
    stop_loss_placed: bool = False
    take_profit_placed: bool = False
    status: TradeStatus = TradeStatus.PENDING


class OpenPosition(BaseModel):
    ticker: str
    direction: Direction
    shares: int
    entry_price: float
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
    time_held_minutes: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    entry_time: datetime = Field(default_factory=datetime.now)
    order_id: int = 0
    contract_id: int = 0

    @property
    def risk_reward_ratio(self) -> float:
        if self.direction == Direction.LONG:
            risk = self.entry_price - self.stop_loss
            reward = self.current_price - self.entry_price
        else:
            risk = self.stop_loss - self.entry_price
            reward = self.entry_price - self.current_price
        return reward / risk if risk > 0 else 0.0


class PortfolioState(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.now)
    equity: float = 0.0
    buying_power: float = 0.0
    margin_used_pct: float = 0.0
    daily_realized_pnl: float = 0.0
    daily_unrealized_pnl: float = 0.0
    daily_pnl: float = 0.0
    daily_pnl_pct: float = 0.0
    open_positions: list[OpenPosition] = Field(default_factory=list)
    position_count: int = 0
    trade_count_today: int = 0
    trade_count_hour: int = 0
    consecutive_losses: int = 0

    @property
    def total_exposure(self) -> float:
        return sum(abs(p.shares * p.current_price) for p in self.open_positions)


class GatekeeperResult(BaseModel):
    approved: bool
    violations: dict[str, bool] = Field(default_factory=dict)
    circuit_breaker: CircuitBreakerAction = CircuitBreakerAction.ALL_CLEAR
    message: str = ""


class ComplianceResult(BaseModel):
    approved: bool
    trade_plan_id: str
    pdt_ok: bool = True
    wash_sale_ok: bool = True
    margin_ok: bool = True
    risk_policy_ok: bool = True
    sector_ok: bool = True
    position_count_ok: bool = True
    time_ok: bool = True
    restricted_ok: bool = True
    violation_detail: str = ""


class AgentMessage(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.now)
    from_agent: str
    to_agent: str
    message_type: str  # scout_report, analyst_report, trade_plan, execution_report, alert, etc.
    payload: dict = Field(default_factory=dict)
    priority: str = "normal"  # low / normal / high / urgent


class AuditFinding(BaseModel):
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)
    agent: str
    issue: str
    evidence: str = ""
    defense: str = ""
    ruling: str = ""
    recommendation: str = ""
    rsi_candidate: bool = False
