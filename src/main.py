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

    async def start(self):
        """Boot the entire system."""
        logger.info("=" * 60)
        logger.info("HUMANLESS TRADING OPERATIONS — Starting up")
        logger.info("Mode: %s | Date: %s", self.config.trading_mode, datetime.now().strftime("%Y-%m-%d"))
        logger.info("=" * 60)

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
        logger.info("Account equity: $%s", f"{equity:,.2f}")

        if equity < 200_000 and self.config.trading_mode == "live":
            logger.critical("Equity $%.0f below $200K minimum — aborting", equity)
            return False

        # 3. Start all agents
        for agent in self._all_agents:
            await agent.start()

        # 4. Reset daily counters
        self.gatekeeper.reset_daily()
        self.scout.reset_daily()

        self._running = True
        logger.info("All agents started. System ready.")
        return True

    async def stop(self):
        """Graceful shutdown."""
        logger.info("Shutting down...")
        self._running = False

        # Stop all agents
        for agent in self._all_agents:
            await agent.stop()

        # Disconnect
        await self.ibkr.disconnect()
        await self.deepseek.stop()
        logger.info("Shutdown complete.")

    async def run_trading_day(self):
        """Execute the full daily trading lifecycle."""
        if not self._running:
            return

        # ── Pre-Market (08:00 - 09:25) ───────────────────────────
        logger.info("=== PRE-MARKET PHASE ===")
        await self._wait_until(time(8, 0), "pre-market")

        # CEO morning briefing (triggers Scout scan)
        await self.ceo.morning_briefing()

        # Wait for scanning/analysis pipeline
        await asyncio.sleep(60)

        # ── Market Open (09:30) ───────────────────────────────────
        logger.info("=== MARKET OPEN ===")
        await self._wait_until(time(9, 30), "market open")

        # Position Manager monitoring loop is already running from start()
        # Scout, Analyst, Strategist, Compliance, Executor are all event-driven via bus

        # ── Active Trading (09:30 - 15:30) ────────────────────────
        logger.info("=== ACTIVE TRADING ===")
        scan_interval = 15 * 60  # 15 minutes

        while self._running:
            now = datetime.now().time()

            # Past entry cutoff?
            if now >= time(15, 30):
                logger.info("=== WIND-DOWN PHASE ===")
                break

            # Periodic scan
            await self.scout.scan_market()

            # Wait for next scan cycle
            await asyncio.sleep(scan_interval)

        # ── Wind-Down (15:30 - 15:50) ────────────────────────────
        # Position Manager handles this automatically via its monitoring loop
        await self._wait_until(time(15, 55), "post-close")

        # ── Post-Market (16:00+) ─────────────────────────────────
        logger.info("=== POST-MARKET ===")
        await self.ceo.end_of_day_review()

        # Wait for audit to complete
        await asyncio.sleep(120)

        logger.info("=== TRADING DAY COMPLETE ===")
        daily_pnl = await self.ibkr.get_daily_pnl()
        logger.info("Daily P&L: $%s", f"{daily_pnl:,.2f}")

    async def _wait_until(self, target: time, label: str):
        """Wait until a specific time of day."""
        while self._running:
            now = datetime.now().time()
            if now >= target:
                return
            # Calculate seconds to wait
            now_secs = now.hour * 3600 + now.minute * 60 + now.second
            target_secs = target.hour * 3600 + target.minute * 60 + target.second
            wait = target_secs - now_secs
            if wait <= 0:
                return
            logger.info("Waiting %d seconds for %s (%s)...", min(wait, 60), label, target)
            await asyncio.sleep(min(wait, 60))

    async def emergency_shutdown(self):
        """Emergency: flatten everything and shut down."""
        logger.critical("!!! EMERGENCY SHUTDOWN !!!")
        await self.executor.flatten_all()
        await self.stop()


async def main():
    """Entry point."""
    config = load_config()

    # Create logs directory
    import os
    os.makedirs("logs", exist_ok=True)

    orchestrator = TradingOrchestrator(config)

    # Handle SIGINT/SIGTERM for graceful shutdown
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(orchestrator.stop()))
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass

    # Start the system
    if not await orchestrator.start():
        logger.critical("Startup failed — exiting")
        sys.exit(1)

    try:
        await orchestrator.run_trading_day()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.critical("Unhandled exception: %s", e, exc_info=True)
        await orchestrator.emergency_shutdown()
    finally:
        await orchestrator.stop()


if __name__ == "__main__":
    asyncio.run(main())
