"""Executor agent — order placement and fill management."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from .base import BaseAgent
from ..models import (
    AgentMessage, TradePlan, ExecutionReport, Direction,
    OrderType, TradeStatus,
)

if TYPE_CHECKING:
    from ..connection import IBKRConnection
    from ..risk_gatekeeper import RiskGatekeeper

logger = logging.getLogger(__name__)


class ExecutorAgent(BaseAgent):
    name = "executor"
    model = "deepseek-chat"
    temperature = 0.2

    def __init__(self, deepseek, bus, ibkr: IBKRConnection, gatekeeper: RiskGatekeeper):
        super().__init__(deepseek, bus)
        self.ibkr = ibkr
        self.gatekeeper = gatekeeper
        self._execution_log: list[ExecutionReport] = []

    async def execute_trade(self, plan: TradePlan) -> ExecutionReport:
        """Execute a validated Trade Plan via IBKR."""
        logger.info("[Executor] Executing %s %s: %d shares @ $%.2f",
                     plan.direction.value, plan.ticker, plan.shares, plan.entry_price)

        report = ExecutionReport(
            trade_plan_id=plan.id,
            ticker=plan.ticker,
            direction=plan.direction,
            shares_requested=plan.shares,
            intended_price=plan.entry_price,
        )

        # Verify connection
        if not self.ibkr.is_connected:
            logger.error("[Executor] IBKR not connected — cannot execute")
            report.status = TradeStatus.REJECTED
            self.log_to_diary(f"EXECUTOR: FAILED {plan.ticker} — IBKR disconnected")
            return report

        try:
            # Determine action
            if plan.direction == Direction.LONG:
                action = "BUY"
            else:
                action = "SELL"

            # Place bracket order
            order_ids = await self.ibkr.place_bracket_order(
                ticker=plan.ticker,
                action=action,
                quantity=plan.shares,
                limit_price=plan.entry_price,
                take_profit_price=plan.take_profit,
                stop_loss_price=plan.stop_loss,
            )

            report.order_id = order_ids[0] if order_ids else 0
            report.order_type = OrderType.LIMIT
            report.stop_loss_placed = True
            report.take_profit_placed = True
            report.status = TradeStatus.SUBMITTED

            # Record the trade in gatekeeper
            self.gatekeeper.record_trade()

            self.log_to_diary(
                f"EXECUTOR: {action} {plan.ticker} {plan.shares}sh "
                f"@ ${plan.entry_price:.2f} bracket placed (ID: {report.order_id})"
            )

            # Notify Position Manager about the new position
            await self.send(
                to="position_manager",
                message_type="new_position",
                payload={
                    "trade_plan": plan.model_dump(mode="json"),
                    "order_id": report.order_id,
                    "execution_report": report.model_dump(mode="json"),
                },
                priority="high",
            )

        except Exception as e:
            logger.error("[Executor] Order failed for %s: %s", plan.ticker, e)
            report.status = TradeStatus.REJECTED
            self.log_to_diary(f"EXECUTOR: FAILED {plan.ticker} — {e}")

        self._execution_log.append(report)
        return report

    async def emergency_close(self, ticker: str, shares: int, direction: Direction) -> int:
        """Emergency market close for a position."""
        action = "SELL" if direction == Direction.LONG else "BUY"
        logger.warning("[Executor] EMERGENCY CLOSE: %s %s %d shares", action, ticker, shares)

        try:
            order_id = await self.ibkr.place_market_close(ticker, action, shares)
            self.log_to_diary(f"EXECUTOR: EMERGENCY {action} {ticker} {shares}sh (ID: {order_id})")
            return order_id
        except Exception as e:
            logger.error("[Executor] Emergency close failed for %s: %s", ticker, e)
            return -1

    async def flatten_all(self):
        """Emergency: close ALL positions."""
        logger.critical("[Executor] FLATTEN ALL — closing every open position")
        self.log_to_diary("EXECUTOR: *** FLATTEN ALL TRIGGERED ***")
        await self.ibkr.flatten_all()

    async def on_message(self, message: AgentMessage):
        if message.message_type == "execute_trade":
            plan = TradePlan(**message.payload)
            report = await self.execute_trade(plan)
            await self.send(
                to=message.from_agent,
                message_type="execution_report",
                payload=report.model_dump(mode="json"),
            )
        elif message.message_type == "emergency_close":
            await self.emergency_close(
                message.payload["ticker"],
                message.payload["shares"],
                Direction(message.payload["direction"]),
            )
        elif message.message_type == "flatten_all":
            await self.flatten_all()

    @property
    def todays_executions(self) -> list[ExecutionReport]:
        today = datetime.now().date()
        return [r for r in self._execution_log if r.timestamp.date() == today]
