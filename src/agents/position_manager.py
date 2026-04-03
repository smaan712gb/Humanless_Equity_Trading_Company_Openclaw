"""Position Manager — the critical open-position monitor and exit decision maker."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING

from .base import BaseAgent
from ..market_calendar import (
    is_any_session_active, get_current_session, Session,
    is_early_close, get_flatten_time, is_market_holiday,
)
from ..models import (
    AgentMessage, OpenPosition, PortfolioState, TradePlan,
    Direction, CircuitBreakerAction,
)

if TYPE_CHECKING:
    from ..connection import IBKRConnection
    from ..risk_gatekeeper import RiskGatekeeper
    from ..config import RiskLimits

logger = logging.getLogger(__name__)


class PositionManagerAgent(BaseAgent):
    name = "position_manager"
    model = "deepseek-reasoner"
    temperature = 0.1

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

        # Position tracking
        self._positions: dict[str, OpenPosition] = {}  # ticker -> position
        self._trade_plans: dict[str, TradePlan] = {}   # ticker -> original plan
        self._monitoring = False
        self._monitor_task: asyncio.Task | None = None
        self._cycle_count = 0

    async def start(self):
        await super().start()
        self._monitoring = True
        self._monitor_task = asyncio.create_task(self._monitoring_loop())
        logger.info("[PositionManager] Monitoring loop started")

    async def stop(self):
        self._monitoring = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        await super().stop()

    # ── Core Monitoring Loop ──────────────────────────────────────────

    async def _monitoring_loop(self):
        """Main loop — runs every 60 seconds during any active session."""
        while self._monitoring:
            try:
                session = get_current_session()

                # Monitor during ANY active session (ETH + RTH)
                if session in (Session.ETH_PRE_MARKET, Session.RTH, Session.ETH_AFTER_HOURS):
                    await self._monitor_cycle()
                    self._cycle_count += 1

                    # Send updates at intervals
                    if self._cycle_count % 5 == 0:  # every 5 min
                        await self._send_strategist_update()
                    if self._cycle_count % 30 == 0:  # every 30 min
                        await self._send_ceo_update()

                # Check early close flatten deadline
                if is_early_close():
                    flatten_time = get_flatten_time()
                    if datetime.now().time() >= flatten_time and self._positions:
                        await self._force_flatten_all("Early close day — flatten deadline")

                # Check ETH after-hours wind-down (19:30 for non-overnight positions)
                if session == Session.ETH_AFTER_HOURS:
                    if datetime.now().time() >= datetime.strptime("19:30", "%H:%M").time():
                        # Close positions NOT marked as overnight holds
                        for ticker, pos in list(self._positions.items()):
                            plan = self._trade_plans.get(ticker)
                            is_overnight = plan and plan.strategy == "overnight_swing"
                            if not is_overnight:
                                await self._close_position(pos, "ETH wind-down — not overnight hold")

                await asyncio.sleep(60)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("[PositionManager] Monitor cycle error: %s", e)
                await asyncio.sleep(10)

    async def _monitor_cycle(self):
        """Single monitoring cycle — check every open position."""
        # Sync positions from IBKR
        await self._sync_positions()

        if not self._positions:
            return

        portfolio = await self.ibkr.get_portfolio_state()

        # Check circuit breakers first
        cb = self.gatekeeper.check_circuit_breakers(portfolio)
        if cb == CircuitBreakerAction.EMERGENCY_LIQUIDATE_ALL:
            await self._force_flatten_all("CIRCUIT BREAKER: Daily drawdown limit hit")
            return
        elif cb == CircuitBreakerAction.FULL_SHUTDOWN:
            await self._force_flatten_all("CIRCUIT BREAKER: Equity below minimum")
            return

        # Check each position
        for ticker, pos in list(self._positions.items()):
            await self._check_position(pos, portfolio)

        # Check daily target (informational — keep trading per new rules)
        if portfolio.daily_pnl >= self.risk_limits.daily_profit_target_usd:
            if self._cycle_count % 30 == 0:  # only log every 30 min
                logger.info("[PositionManager] Daily target $%.0f reached! Continuing to trade.",
                           portfolio.daily_pnl)
                self.log_to_diary(f"POSITION_MANAGER: Daily target HIT — P&L ${portfolio.daily_pnl:,.0f}. Continuing.")

        # Check approaching drawdown
        if portfolio.daily_pnl_pct <= -(self.risk_limits.daily_max_drawdown_pct * 0.75):
            logger.warning("[PositionManager] Approaching drawdown limit: %.2f%%",
                          portfolio.daily_pnl_pct)
            await self.send(
                to="ceo",
                message_type="drawdown_warning",
                payload={"daily_pnl_pct": portfolio.daily_pnl_pct},
                priority="urgent",
            )

    async def _check_position(self, pos: OpenPosition, portfolio: PortfolioState):
        """Check a single position against all exit rules."""
        now = datetime.now()
        pos.time_held_minutes = (now - pos.entry_time).total_seconds() / 60

        # Update current price
        price = await self.ibkr.get_market_price(pos.ticker)
        if price:
            pos.current_price = price
            if pos.direction == Direction.LONG:
                pos.unrealized_pnl = (price - pos.entry_price) * pos.shares
            else:
                pos.unrealized_pnl = (pos.entry_price - price) * pos.shares
            pos.unrealized_pnl_pct = (pos.unrealized_pnl / (pos.entry_price * pos.shares)) * 100

        # ── Exit Checks (in priority order) ──

        # 1. Stop loss hit
        if self._stop_hit(pos):
            logger.warning("[PositionManager] STOP HIT on %s @ $%.2f (loss: $%.0f)",
                          pos.ticker, pos.current_price, pos.unrealized_pnl)
            await self._close_position(pos, "Stop loss triggered")
            return

        # 2. Take profit hit
        if self._target_hit(pos):
            logger.info("[PositionManager] TARGET HIT on %s @ $%.2f (gain: $%.0f)",
                       pos.ticker, pos.current_price, pos.unrealized_pnl)
            await self._close_position(pos, "Take profit reached")
            return

        # 3. Move stop to breakeven at 2:1 R/R
        if pos.risk_reward_ratio >= 2.0 and not self._at_breakeven(pos):
            old_stop = pos.stop_loss
            pos.stop_loss = pos.entry_price
            logger.info("[PositionManager] %s stop moved to breakeven $%.2f (was $%.2f)",
                       pos.ticker, pos.stop_loss, old_stop)
            self.log_to_diary(
                f"POSITION_MANAGER: {pos.ticker} stop → breakeven ${pos.stop_loss:.2f} (2:1 R/R)"
            )

        # 4. Session-aware checks
        session = get_current_session()

        # In ETH sessions, use DeepSeek to evaluate if position should be held
        if session in (Session.ETH_PRE_MARKET, Session.ETH_AFTER_HOURS):
            # If position is significantly negative in thin liquidity, consider closing
            if pos.unrealized_pnl_pct < -2.0:
                logger.warning("[PositionManager] %s down %.1f%% in ETH — closing",
                              pos.ticker, pos.unrealized_pnl_pct)
                await self._close_position(pos, f"ETH session loss > 2% ({pos.unrealized_pnl_pct:.1f}%)")
                return

    def _stop_hit(self, pos: OpenPosition) -> bool:
        if pos.direction == Direction.LONG:
            return pos.current_price <= pos.stop_loss and pos.stop_loss > 0
        else:
            return pos.current_price >= pos.stop_loss and pos.stop_loss > 0

    def _target_hit(self, pos: OpenPosition) -> bool:
        if pos.direction == Direction.LONG:
            return pos.current_price >= pos.take_profit and pos.take_profit > 0
        else:
            return pos.current_price <= pos.take_profit and pos.take_profit > 0

    def _at_breakeven(self, pos: OpenPosition) -> bool:
        return abs(pos.stop_loss - pos.entry_price) < 0.01

    # ── Position Actions ──────────────────────────────────────────────

    async def _close_position(self, pos: OpenPosition, reason: str):
        """Close a position via the Executor."""
        logger.info("[PositionManager] Closing %s: %s", pos.ticker, reason)
        self.log_to_diary(
            f"POSITION_MANAGER: CLOSE {pos.ticker} {pos.direction.value} "
            f"{pos.shares}sh P&L=${pos.unrealized_pnl:,.0f} — {reason}"
        )

        await self.send(
            to="executor",
            message_type="emergency_close",
            payload={
                "ticker": pos.ticker,
                "shares": pos.shares,
                "direction": pos.direction.value,
            },
            priority="urgent",
        )

        # Record result for Strategist
        plan = self._trade_plans.get(pos.ticker)
        if plan:
            await self.send(
                to="strategist",
                message_type="trade_result",
                payload={
                    "strategy": plan.strategy,
                    "won": pos.unrealized_pnl > 0,
                    "pnl": pos.unrealized_pnl,
                },
            )

        # Notify compliance if closed at loss (wash sale tracking)
        if pos.unrealized_pnl < 0:
            await self.send(
                to="compliance",
                message_type="loss_close_recorded",
                payload={"ticker": pos.ticker},
            )

        # Remove from tracking
        self._positions.pop(pos.ticker, None)
        self._trade_plans.pop(pos.ticker, None)

    async def _force_flatten_all(self, reason: str):
        """Close ALL positions immediately."""
        logger.critical("[PositionManager] FORCE FLATTEN ALL: %s", reason)
        self.log_to_diary(f"POSITION_MANAGER: *** FORCE FLATTEN ALL — {reason} ***")

        await self.send(
            to="executor",
            message_type="flatten_all",
            payload={"reason": reason},
            priority="urgent",
        )

        # Clear tracking
        self._positions.clear()
        self._trade_plans.clear()

        # Notify CEO
        await self.send(
            to="ceo",
            message_type="positions_flattened",
            payload={"reason": reason},
            priority="urgent",
        )

    # ── Sync & Updates ────────────────────────────────────────────────

    async def _sync_positions(self):
        """Sync internal state with IBKR's actual position data."""
        ibkr_positions = await self.ibkr.get_positions()
        ibkr_tickers = {p.ticker for p in ibkr_positions}

        # Add any positions we don't know about (manual or from reconnect)
        for pos in ibkr_positions:
            if pos.ticker not in self._positions:
                logger.warning("[PositionManager] Found untracked position: %s", pos.ticker)
                self._positions[pos.ticker] = pos

        # Remove positions that IBKR no longer shows
        closed = set(self._positions.keys()) - ibkr_tickers
        for ticker in closed:
            logger.info("[PositionManager] Position %s closed (confirmed by IBKR)", ticker)
            self._positions.pop(ticker, None)

    async def _send_strategist_update(self):
        """Send position summary to Strategist every 5 minutes."""
        if not self._positions:
            return
        payload = {
            "positions": {
                t: p.model_dump(mode="json") for t, p in self._positions.items()
            },
            "total_unrealized": sum(p.unrealized_pnl for p in self._positions.values()),
        }
        await self.send(to="strategist", message_type="position_update", payload=payload)

    async def _send_ceo_update(self):
        """Send portfolio summary to CEO every 30 minutes."""
        portfolio = await self.ibkr.get_portfolio_state()
        session = get_current_session()
        await self.send(
            to="ceo",
            message_type="portfolio_summary",
            payload={
                "daily_pnl": portfolio.daily_pnl,
                "daily_pnl_pct": portfolio.daily_pnl_pct,
                "equity": portfolio.equity,
                "position_count": portfolio.position_count,
                "margin_used_pct": portfolio.margin_used_pct,
                "session": session.value,
            },
        )

    # ── Message Handler ───────────────────────────────────────────────

    async def on_message(self, message: AgentMessage):
        if message.message_type == "new_position":
            plan = TradePlan(**message.payload["trade_plan"])
            pos = OpenPosition(
                ticker=plan.ticker,
                direction=plan.direction,
                shares=plan.shares,
                entry_price=plan.entry_price,
                stop_loss=plan.stop_loss,
                take_profit=plan.take_profit,
                order_id=message.payload.get("order_id", 0),
            )
            self._positions[plan.ticker] = pos
            self._trade_plans[plan.ticker] = plan
            logger.info("[PositionManager] Tracking new position: %s %s %dsh",
                       plan.direction.value, plan.ticker, plan.shares)

    def get_position_summary(self) -> dict:
        """Get a snapshot of all tracked positions."""
        return {
            ticker: {
                "direction": pos.direction.value,
                "shares": pos.shares,
                "entry": pos.entry_price,
                "current": pos.current_price,
                "pnl": pos.unrealized_pnl,
                "pnl_pct": pos.unrealized_pnl_pct,
                "held_min": pos.time_held_minutes,
                "stop": pos.stop_loss,
                "target": pos.take_profit,
            }
            for ticker, pos in self._positions.items()
        }
