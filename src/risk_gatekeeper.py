"""Risk Gatekeeper — mechanical circuit breaker. No reasoning, just rules."""

from __future__ import annotations

import logging
from datetime import datetime

from .config import RiskLimits
from .market_calendar import (
    is_any_session_active, requires_outside_rth,
    can_use_market_orders, get_position_size_multiplier,
    is_market_holiday, get_current_session, Session,
)
from .models import (
    TradePlan, PortfolioState, GatekeeperResult,
    CircuitBreakerAction, Direction,
)

logger = logging.getLogger(__name__)


class RiskGatekeeper:
    """Enforces hard risk limits. Cannot be overridden by any agent."""

    def __init__(self, limits: RiskLimits):
        self.limits = limits
        self._last_trade_time: datetime | None = None
        self._trade_count_today = 0

    def validate_trade(self, plan: TradePlan, portfolio: PortfolioState) -> GatekeeperResult:
        """Run all pre-trade checks. ALL must pass."""
        violations = {}

        # 1. Market must be open
        if is_market_holiday():
            violations["market_closed_holiday"] = False

        if not is_any_session_active():
            violations["no_active_session"] = False

        # 2. Position size check
        if portfolio.equity > 0:
            position_pct = (plan.notional / portfolio.equity) * 100
            if position_pct > self.limits.max_single_position_pct:
                violations["position_size"] = False

        # 3. Max position value
        if plan.notional > self.limits.max_position_value_usd:
            violations["max_position_value"] = False

        # 4. Position count (0 = unlimited)
        if self.limits.max_concurrent_positions > 0:
            if portfolio.position_count >= self.limits.max_concurrent_positions:
                violations["position_count"] = False

        # 5. Debounce — minimum time between trades
        if self._last_trade_time and self.limits.min_time_between_trades_sec > 0:
            elapsed = (datetime.now() - self._last_trade_time).total_seconds()
            if elapsed < self.limits.min_time_between_trades_sec:
                violations["trade_debounce"] = False

        # 6. Margin check
        if portfolio.margin_used_pct >= self.limits.max_margin_utilization:
            violations["margin"] = False

        # 7. Per-trade max loss
        if plan.direction == Direction.LONG:
            risk_per_share = plan.entry_price - plan.stop_loss
        else:
            risk_per_share = plan.stop_loss - plan.entry_price
        max_loss = risk_per_share * plan.shares
        if max_loss > self.limits.per_trade_max_loss_usd:
            violations["per_trade_max_loss"] = False

        # 8. Must have stop loss
        if plan.stop_loss <= 0:
            violations["no_stop_loss"] = False

        # 9. ETH session — no market orders
        if not can_use_market_orders():
            # This is checked at order placement, but flag it early
            pass  # Executor handles this

        # 10. Drawdown check
        if portfolio.daily_pnl_pct <= -self.limits.daily_max_drawdown_pct:
            violations["drawdown_breached"] = False

        # 11. Apply session-based position size multiplier
        multiplier = get_position_size_multiplier()
        if multiplier == 0:
            violations["session_closed"] = False

        if violations:
            msg = f"REJECTED — violations: {list(violations.keys())}"
            logger.warning("Gatekeeper: %s for %s", msg, plan.ticker)
            return GatekeeperResult(approved=False, violations=violations, message=msg)

        logger.info("Gatekeeper: APPROVED trade for %s (%d shares)", plan.ticker, plan.shares)
        return GatekeeperResult(approved=True, message="All checks passed")

    def record_trade(self):
        """Call after a trade is executed to update counters."""
        self._last_trade_time = datetime.now()
        self._trade_count_today += 1

    def reset_daily(self):
        """Reset daily counters (call at start of each trading day)."""
        self._trade_count_today = 0
        self._last_trade_time = None

    def check_circuit_breakers(
        self, portfolio: PortfolioState, vix: float = 0.0, spy_change_pct: float = 0.0
    ) -> CircuitBreakerAction:
        """Check system-wide circuit breakers."""

        # Daily drawdown
        if portfolio.daily_pnl_pct <= -self.limits.daily_max_drawdown_pct:
            logger.critical("CIRCUIT BREAKER: Daily drawdown %.2f%% — LIQUIDATE ALL",
                            portfolio.daily_pnl_pct)
            return CircuitBreakerAction.EMERGENCY_LIQUIDATE_ALL

        # VIX spike
        if vix > 40:
            logger.warning("CIRCUIT BREAKER: VIX %.1f > 40 — REDUCE 50%%", vix)
            return CircuitBreakerAction.REDUCE_ALL_50PCT

        # SPY crash
        if spy_change_pct <= -3.0:
            logger.warning("CIRCUIT BREAKER: SPY %.2f%% — HALT NEW ENTRIES", spy_change_pct)
            return CircuitBreakerAction.HALT_NEW_ENTRIES

        # Equity floor
        if portfolio.equity < 100_000:
            logger.critical("CIRCUIT BREAKER: Equity $%.0f < $100K — FULL SHUTDOWN",
                            portfolio.equity)
            return CircuitBreakerAction.FULL_SHUTDOWN

        return CircuitBreakerAction.ALL_CLEAR
