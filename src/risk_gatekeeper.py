"""Risk Gatekeeper — mechanical circuit breaker. No reasoning, just rules."""

from __future__ import annotations

import logging
from datetime import datetime, time

from .config import RiskLimits
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
        self._trade_times_hour: list[datetime] = []

    def validate_trade(self, plan: TradePlan, portfolio: PortfolioState) -> GatekeeperResult:
        """Run all pre-trade checks. ALL must pass."""
        violations = {}

        # 1. Position size check
        if portfolio.equity > 0:
            position_pct = (plan.notional / portfolio.equity) * 100
            if position_pct > self.limits.max_single_position_pct:
                violations["position_size"] = False

        # 2. Max position value
        if plan.notional > self.limits.max_position_value_usd:
            violations["max_position_value"] = False

        # 3. Position count
        if portfolio.position_count >= self.limits.max_concurrent_positions:
            violations["position_count"] = False

        # 4. Daily trade count
        if self._trade_count_today >= self.limits.max_trades_per_day:
            violations["daily_trades"] = False

        # 5. Hourly trade count
        now = datetime.now()
        self._trade_times_hour = [
            t for t in self._trade_times_hour
            if (now - t).total_seconds() < 3600
        ]
        if len(self._trade_times_hour) >= self.limits.max_trades_per_hour:
            violations["hourly_trades"] = False

        # 6. Time between trades
        if self._last_trade_time:
            elapsed = (now - self._last_trade_time).total_seconds()
            if elapsed < self.limits.min_time_between_trades_sec:
                violations["time_between_trades"] = False

        # 7. Margin check
        if portfolio.margin_used_pct >= self.limits.max_margin_utilization:
            violations["margin"] = False

        # 8. Per-trade max loss
        if plan.direction == Direction.LONG:
            risk_per_share = plan.entry_price - plan.stop_loss
        else:
            risk_per_share = plan.stop_loss - plan.entry_price
        max_loss = risk_per_share * plan.shares
        if max_loss > self.limits.per_trade_max_loss_usd:
            violations["per_trade_max_loss"] = False

        # 9. Must have stop loss
        if plan.stop_loss <= 0:
            violations["no_stop_loss"] = False

        # 10. Trading hours
        if not self._is_trading_hours():
            violations["trading_hours"] = False

        # 11. No new entries after cutoff
        if self._past_entry_cutoff():
            violations["past_entry_cutoff"] = False

        # 12. Drawdown check
        if portfolio.daily_pnl_pct <= -self.limits.daily_max_drawdown_pct:
            violations["drawdown_breached"] = False

        # 13. Sector exposure (simplified — would need sector data in production)
        # TODO: implement sector tracking

        if violations:
            msg = f"REJECTED — violations: {list(violations.keys())}"
            logger.warning("Gatekeeper: %s for %s", msg, plan.ticker)
            return GatekeeperResult(approved=False, violations=violations, message=msg)

        logger.info("Gatekeeper: APPROVED trade for %s (%d shares)", plan.ticker, plan.shares)
        return GatekeeperResult(approved=True, message="All checks passed")

    def record_trade(self):
        """Call after a trade is executed to update counters."""
        now = datetime.now()
        self._last_trade_time = now
        self._trade_count_today += 1
        self._trade_times_hour.append(now)

    def reset_daily(self):
        """Reset daily counters (call at start of each trading day)."""
        self._trade_count_today = 0
        self._trade_times_hour.clear()
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
        if vix > 35:
            logger.warning("CIRCUIT BREAKER: VIX %.1f > 35 — REDUCE 50%%", vix)
            return CircuitBreakerAction.REDUCE_ALL_50PCT

        # SPY crash
        if spy_change_pct <= -2.0:
            logger.warning("CIRCUIT BREAKER: SPY %.2f%% — HALT NEW ENTRIES", spy_change_pct)
            return CircuitBreakerAction.HALT_NEW_ENTRIES

        # Equity floor
        if portfolio.equity < 200_000:
            logger.critical("CIRCUIT BREAKER: Equity $%.0f < $200K — FULL SHUTDOWN",
                            portfolio.equity)
            return CircuitBreakerAction.FULL_SHUTDOWN

        return CircuitBreakerAction.ALL_CLEAR

    def _is_trading_hours(self) -> bool:
        """Check if current time is within active trading hours (09:30-15:45 ET)."""
        now = datetime.now().time()
        return time(9, 30) <= now <= time(15, 45)

    def _past_entry_cutoff(self) -> bool:
        """Check if past the no-new-entries cutoff."""
        h, m = map(int, self.limits.no_new_entries_after.split(":"))
        cutoff = time(h, m)
        return datetime.now().time() > cutoff
