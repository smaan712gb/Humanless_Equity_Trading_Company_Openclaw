"""Main orchestrator — boots the trading system and runs the daily lifecycle."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from datetime import datetime, time

from .config import load_config, AppConfig
from .connection import IBKRConnection
from .deepseek_client import DeepSeekClient
from .heartbeat import HeartbeatMonitor
from .market_calendar import (
    is_market_holiday, is_any_session_active, get_current_session,
    Session, next_trading_day, get_session_info,
)
from .message_bus import MessageBus
from .risk_gatekeeper import RiskGatekeeper
from .agents.ceo import CEOAgent
from .agents.scout import ScoutAgent
from .agents.analyst import AnalystAgent
from .agents.strategist import StrategistAgent
from .agents.executor import ExecutorAgent
from .agents.position_manager import PositionManagerAgent
from .agents.compliance import ComplianceAgent
from .agents.auditor import AuditorAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f"logs/{datetime.now().strftime('%Y-%m-%d')}.log"),
    ],
)
logger = logging.getLogger(__name__)


class TradingOrchestrator:
    """Boots and coordinates all agents through the daily trading lifecycle."""

    def __init__(self, config: AppConfig):
        self.config = config
        self._running = False

        # Core infrastructure
        self.bus = MessageBus()
        self.ibkr = IBKRConnection(config.ibkr)
        self.deepseek = DeepSeekClient(config.deepseek)
        self.gatekeeper = RiskGatekeeper(config.risk)
        self.heartbeat = HeartbeatMonitor(self.bus)

        # Agents
        self.ceo = CEOAgent(self.deepseek, self.bus, self.ibkr)
        self.scout = ScoutAgent(self.deepseek, self.bus, self.ibkr)
        self.analyst = AnalystAgent(self.deepseek, self.bus, self.ibkr)
        self.strategist = StrategistAgent(
            self.deepseek, self.bus, self.ibkr, self.gatekeeper, config.risk,
        )
        self.executor = ExecutorAgent(self.deepseek, self.bus, self.ibkr, self.gatekeeper)
        self.position_manager = PositionManagerAgent(
            self.deepseek, self.bus, self.ibkr, self.gatekeeper, config.risk,
        )
        self.compliance = ComplianceAgent(
            self.deepseek, self.bus, self.ibkr, self.gatekeeper, config.risk,
        )
        self.auditor = AuditorAgent(self.deepseek, self.bus)

        self._all_agents = [
            self.ceo, self.scout, self.analyst, self.strategist,
            self.executor, self.position_manager, self.compliance, self.auditor,
        ]

    async def start(self) -> bool:
        """Boot the entire system."""
        logger.info("=" * 60)
        logger.info("HUMANLESS TRADING OPERATIONS — Starting up")
        logger.info("Mode: %s | Date: %s",
                     self.config.trading_mode, datetime.now().strftime("%Y-%m-%d"))
        logger.info("=" * 60)

        # Check market calendar
        session_info = get_session_info()
        logger.info("Market status: %s", session_info)

        if is_market_holiday():
            next_day = next_trading_day()
            logger.warning("TODAY IS A MARKET HOLIDAY. Next trading day: %s", next_day)
            logger.warning("System will wait for next trading day.")

        # 1. Start DeepSeek client
        await self.deepseek.start()
        logger.info("DeepSeek client ready")

        # 2. Connect to IBKR
        connected = await self.ibkr.connect()
        if not connected:
            logger.critical("Cannot connect to IBKR — aborting startup")
            return False

        # Log account info
        summary = await self.ibkr.get_account_summary()
        equity = summary.get("NetLiquidation", 0)
        buying_power = summary.get("BuyingPower", 0)
        logger.info("Account equity: $%s | Buying power: $%s",
                     f"{equity:,.2f}", f"{buying_power:,.2f}")

        # 3. Start heartbeat monitor
        await self.heartbeat.start()
        logger.info("Paperclip heartbeat monitor started")

        # 4. Start all agents
        for agent in self._all_agents:
            await agent.start()

        # 5. Reset daily counters
        self.gatekeeper.reset_daily()
        self.scout.reset_daily()

        self._running = True
        logger.info("All %d agents started. System ready.", len(self._all_agents))
        return True

    async def stop(self):
        """Graceful shutdown."""
        logger.info("Shutting down...")
        self._running = False

        # Log final heartbeat status
        logger.info(self.heartbeat.get_summary_line())

        await self.heartbeat.stop()
        for agent in self._all_agents:
            await agent.stop()

        await self.ibkr.disconnect()
        await self.deepseek.stop()
        logger.info("Shutdown complete.")

    async def run(self):
        """Main run loop — handles holidays, ETH, RTH, and overnight."""
        if not self._running:
            return

        while self._running:
            today = datetime.now().date()

            # If holiday, wait until next trading day
            if is_market_holiday(today):
                next_day = next_trading_day(today)
                logger.info("Market closed today. Next trading day: %s. Sleeping...", next_day)
                # Sleep until 03:50 ET on next trading day (10 min before ETH opens)
                await self._sleep_until_date(next_day, time(3, 50))
                self.gatekeeper.reset_daily()
                self.scout.reset_daily()
                continue

            # Run the full trading day (ETH + RTH + ETH)
            await self._run_trading_day()

            # After trading day, run audit
            await self._run_post_market()

            # Sleep until next day's pre-market
            next_day = next_trading_day(today)
            logger.info("Trading day complete. Next session: %s 04:00 ET", next_day)
            await self._sleep_until_date(next_day, time(3, 50))
            self.gatekeeper.reset_daily()
            self.scout.reset_daily()

    async def _run_trading_day(self):
        """Execute a full trading day: ETH pre-market → RTH → ETH after-hours."""

        # ── ETH Pre-Market (04:00 - 09:30) ───────────────────────
        await self._wait_until(time(4, 0), "ETH pre-market")

        if self._running:
            logger.info("=== ETH PRE-MARKET SESSION ===")
            await self.ceo.morning_briefing()

            # Scout scans every 15 min during pre-market
            while self._running and datetime.now().time() < time(9, 25):
                session = get_current_session()
                if session == Session.ETH_PRE_MARKET:
                    await self.scout.scan_market()
                await asyncio.sleep(900)  # 15 min

        # ── RTH (09:30 - 16:00) ──────────────────────────────────
        await self._wait_until(time(9, 30), "RTH market open")

        if self._running:
            logger.info("=== REGULAR TRADING HOURS ===")

            # Continuous scanning during RTH
            while self._running:
                session = get_current_session()
                if session != Session.RTH:
                    break
                await self.scout.scan_market()
                await asyncio.sleep(600)  # 10 min during RTH (more frequent)

        # ── ETH After-Hours (16:00 - 20:00) ──────────────────────
        if self._running:
            logger.info("=== ETH AFTER-HOURS SESSION ===")

            while self._running:
                session = get_current_session()
                if session != Session.ETH_AFTER_HOURS:
                    break
                # Scan for after-hours earnings reactions
                await self.scout.scan_market()
                await asyncio.sleep(900)  # 15 min

    async def _run_post_market(self):
        """Post-market review and audit."""
        if not self._running:
            return

        logger.info("=== POST-MARKET REVIEW ===")
        await self.ceo.end_of_day_review()

        # Wait for audit to complete
        await asyncio.sleep(120)

        daily_pnl = await self.ibkr.get_daily_pnl()
        logger.info("=== TRADING DAY COMPLETE === Daily P&L: $%s", f"{daily_pnl:,.2f}")

    async def _wait_until(self, target: time, label: str):
        """Wait until a specific time of day."""
        while self._running:
            now = datetime.now().time()
            if now >= target:
                return
            now_secs = now.hour * 3600 + now.minute * 60 + now.second
            target_secs = target.hour * 3600 + target.minute * 60 + target.second
            wait = target_secs - now_secs
            if wait <= 0:
                return
            logger.info("Waiting %d seconds for %s (%s)...", min(wait, 300), label, target)
            await asyncio.sleep(min(wait, 300))

    async def _sleep_until_date(self, target_date, target_time: time):
        """Sleep until a specific date and time."""
        while self._running:
            now = datetime.now()
            target = datetime.combine(target_date, target_time)
            delta = (target - now).total_seconds()
            if delta <= 0:
                return
            logger.info("Sleeping %.0f seconds until %s %s...",
                        min(delta, 3600), target_date, target_time)
            await asyncio.sleep(min(delta, 3600))

    async def emergency_shutdown(self):
        """Emergency: flatten everything and shut down."""
        logger.critical("!!! EMERGENCY SHUTDOWN !!!")
        await self.executor.flatten_all()
        await self.stop()


async def main():
    """Entry point."""
    import os
    os.makedirs("logs", exist_ok=True)

    config = load_config()
    orchestrator = TradingOrchestrator(config)

    # Handle SIGINT/SIGTERM
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(orchestrator.stop()))
        except NotImplementedError:
            pass  # Windows

    if not await orchestrator.start():
        logger.critical("Startup failed — exiting")
        sys.exit(1)

    try:
        await orchestrator.run()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.critical("Unhandled exception: %s", e, exc_info=True)
        await orchestrator.emergency_shutdown()
    finally:
        await orchestrator.stop()


if __name__ == "__main__":
    asyncio.run(main())
