"""Compliance Officer — pre-trade validation and regulatory guard."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from .base import BaseAgent
from ..models import (
    AgentMessage, TradePlan, ComplianceResult,
    PortfolioState,
)

if TYPE_CHECKING:
    from ..connection import IBKRConnection
    from ..risk_gatekeeper import RiskGatekeeper
    from ..config import RiskLimits

logger = logging.getLogger(__name__)


class ComplianceAgent(BaseAgent):
    name = "compliance"
    model = "deepseek-reasoner"
    temperature = 0.0  # deterministic

    def __init__(
        self,
        deepseek, bus,
        ibkr: IBKRConnection,
        gatekeeper: RiskGatekeeper,
        risk_limits: RiskLimits,
    ):
        super().__init__(deepseek, bus)
        self.ibkr = ibkr
        self.gatekeeper = gatekeeper
        self.risk_limits = risk_limits

        # Compliance tracking
        self._day_trades: list[dict] = []  # {date, ticker}
        self._wash_sale_log: list[dict] = []  # {ticker, loss_close_date, reentry_date}
        self._veto_count = 0
        self._approval_count = 0

    async def validate_trade(self, plan: TradePlan) -> ComplianceResult:
        """Run full compliance check on a Trade Plan."""
        logger.info("[Compliance] Validating %s %s %s...",
                     plan.direction.value, plan.ticker, plan.shares)

        portfolio = await self.ibkr.get_portfolio_state()

        result = ComplianceResult(
            trade_plan_id=plan.id,
            approved=True,
        )

        # 1. PDT check
        result.pdt_ok = self._check_pdt(portfolio)

        # 2. Wash sale check
        result.wash_sale_ok = self._check_wash_sale(plan.ticker)

        # 3. Margin check
        result.margin_ok = portfolio.margin_used_pct < self.risk_limits.max_margin_utilization

        # 4. Risk policy via gatekeeper
        gk = self.gatekeeper.validate_trade(plan, portfolio)
        result.risk_policy_ok = gk.approved

        # 5. Sector exposure (simplified)
        result.sector_ok = portfolio.position_count < self.risk_limits.max_concurrent_positions

        # 6. Position count
        result.position_count_ok = portfolio.position_count < self.risk_limits.max_concurrent_positions

        # 7. Trading hours
        result.time_ok = self.gatekeeper._is_trading_hours()

        # 8. Restricted list (placeholder — would check halted/blackout tickers)
        result.restricted_ok = True

        # Determine overall approval
        checks = [
            ("PDT", result.pdt_ok),
            ("Wash Sale", result.wash_sale_ok),
            ("Margin", result.margin_ok),
            ("Risk Policy", result.risk_policy_ok),
            ("Sector", result.sector_ok),
            ("Position Count", result.position_count_ok),
            ("Time", result.time_ok),
            ("Restricted", result.restricted_ok),
        ]

        failed = [name for name, ok in checks if not ok]

        if failed:
            result.approved = False
            result.violation_detail = f"Failed checks: {', '.join(failed)}"
            self._veto_count += 1
            logger.warning("[Compliance] VETO %s: %s", plan.ticker, result.violation_detail)
            self.log_to_diary(f"COMPLIANCE: VETO {plan.ticker} — {result.violation_detail}")

            # Notify strategist of rejection
            await self.send(
                to="strategist",
                message_type="compliance_veto",
                payload={
                    "trade_plan_id": plan.id,
                    "ticker": plan.ticker,
                    "violations": failed,
                },
            )
        else:
            self._approval_count += 1
            logger.info("[Compliance] APPROVED %s", plan.ticker)
            self.log_to_diary(f"COMPLIANCE: APPROVED {plan.ticker}")

            # Forward to Executor for execution
            await self.send(
                to="executor",
                message_type="execute_trade",
                payload=plan.model_dump(mode="json"),
                priority="high",
            )

        return result

    def _check_pdt(self, portfolio: PortfolioState) -> bool:
        """Check Pattern Day Trader rules."""
        # If equity > $25K, PDT doesn't restrict
        if portfolio.equity >= 25_000:
            return True

        # Count day trades in rolling 5 business days
        cutoff = datetime.now() - timedelta(days=7)  # ~5 business days
        recent = [t for t in self._day_trades if t["date"] >= cutoff]
        return len(recent) < 3

    def _check_wash_sale(self, ticker: str) -> bool:
        """Check 30-day wash sale window."""
        cutoff = datetime.now() - timedelta(days=30)
        for entry in self._wash_sale_log:
            if entry["ticker"] == ticker and entry["loss_close_date"] >= cutoff:
                logger.warning("[Compliance] Wash sale risk for %s (closed at loss on %s)",
                              ticker, entry["loss_close_date"])
                return False
        return True

    def record_day_trade(self, ticker: str):
        """Record a completed day trade for PDT tracking."""
        self._day_trades.append({"date": datetime.now(), "ticker": ticker})

    def record_loss_close(self, ticker: str):
        """Record a position closed at a loss for wash sale tracking."""
        self._wash_sale_log.append({
            "ticker": ticker,
            "loss_close_date": datetime.now(),
            "reentry_date": datetime.now() + timedelta(days=30),
        })

    async def on_message(self, message: AgentMessage):
        if message.message_type == "trade_plan":
            plan = TradePlan(**message.payload)
            await self.validate_trade(plan)
        elif message.message_type == "day_trade_recorded":
            self.record_day_trade(message.payload["ticker"])
        elif message.message_type == "loss_close_recorded":
            self.record_loss_close(message.payload["ticker"])
