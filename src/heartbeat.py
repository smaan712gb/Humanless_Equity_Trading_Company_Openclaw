"""Paperclip Heartbeat System — monitors agent health and enforces operational cadence."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from .market_calendar import get_current_session, Session, is_market_holiday

if TYPE_CHECKING:
    from .message_bus import MessageBus

logger = logging.getLogger(__name__)


class AgentHeartbeat:
    """Tracks a single agent's heartbeat state."""

    def __init__(self, agent_name: str, interval_seconds: int):
        self.agent_name = agent_name
        self.interval = interval_seconds
        self.last_beat: datetime | None = None
        self.last_status: str = "unknown"
        self.consecutive_misses: int = 0
        self.total_beats: int = 0
        self.is_alive: bool = False

    def record_beat(self, status: str = "ok"):
        self.last_beat = datetime.now()
        self.last_status = status
        self.consecutive_misses = 0
        self.total_beats += 1
        self.is_alive = True

    def check(self) -> bool:
        """Check if the agent missed its heartbeat."""
        if self.last_beat is None:
            return False
        elapsed = (datetime.now() - self.last_beat).total_seconds()
        if elapsed > self.interval * 2:  # 2x grace period
            self.consecutive_misses += 1
            self.is_alive = False
            return False
        return True

    @property
    def overdue_seconds(self) -> float:
        if self.last_beat is None:
            return 0
        return max(0, (datetime.now() - self.last_beat).total_seconds() - self.interval)


class HeartbeatMonitor:
    """Paperclip heartbeat monitor — tracks all agent health and escalates failures."""

    # Heartbeat intervals from paperclip/org-chart.yaml
    AGENT_INTERVALS = {
        # Core team
        "ceo": 1800,              # 30 min
        "scout": 900,             # 15 min
        "analyst": 900,           # 15 min
        "strategist": 300,        # 5 min
        "executor": 60,           # 1 min
        "position_manager": 60,   # 1 min
        "compliance": 300,        # 5 min
        "auditor": 86400,         # daily
        # Specialist team
        "sector_trend_watcher": 900,      # 15 min
        "volume_flow_analyst": 300,       # 5 min
        "twitter_sentiment": 600,         # 10 min
        "futures_index_watcher": 300,     # 5 min
        "earnings_calendar": 3600,        # 1 hour
        "options_flow_scanner": 600,      # 10 min
        "technical_analyst": 900,         # 15 min
        "short_interest_tracker": 3600,   # 1 hour
    }

    def __init__(self, bus: MessageBus):
        self.bus = bus
        self._heartbeats: dict[str, AgentHeartbeat] = {}
        self._running = False
        self._monitor_task: asyncio.Task | None = None
        self._alerts: list[dict] = []

        # Initialize heartbeats for all known agents
        for agent_name, interval in self.AGENT_INTERVALS.items():
            self._heartbeats[agent_name] = AgentHeartbeat(agent_name, interval)

    async def start(self):
        """Start the heartbeat monitor."""
        self._running = True

        # Subscribe to heartbeat messages from all agents
        self.bus.subscribe("heartbeat_monitor", self._on_message)

        # Start the monitoring loop
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("Heartbeat monitor started — tracking %d agents", len(self._heartbeats))

    async def stop(self):
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

    def record_heartbeat(self, agent_name: str, status: str = "ok"):
        """Record a heartbeat from an agent."""
        if agent_name not in self._heartbeats:
            # Dynamic agent registration (CEO hired a new specialist)
            self._heartbeats[agent_name] = AgentHeartbeat(agent_name, 900)  # default 15min

        self._heartbeats[agent_name].record_beat(status)

    async def _monitor_loop(self):
        """Check all agent heartbeats every 30 seconds."""
        while self._running:
            try:
                session = get_current_session()

                # Only monitor during active sessions
                if session in (Session.ETH_PRE_MARKET, Session.RTH, Session.ETH_AFTER_HOURS):
                    await self._check_all()

                await asyncio.sleep(30)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("Heartbeat monitor error: %s", e)
                await asyncio.sleep(10)

    async def _check_all(self):
        """Check every agent's heartbeat status."""
        from .models import AgentMessage

        for name, hb in self._heartbeats.items():
            if not hb.check():
                if hb.consecutive_misses == 1:
                    # First miss — warning
                    logger.warning("HEARTBEAT: Agent '%s' missed beat (overdue %.0fs)",
                                   name, hb.overdue_seconds)
                    alert = {
                        "timestamp": datetime.now().isoformat(),
                        "agent": name,
                        "severity": "WARNING",
                        "message": f"Missed heartbeat (overdue {hb.overdue_seconds:.0f}s)",
                    }
                    self._alerts.append(alert)

                elif hb.consecutive_misses == 3:
                    # Three misses — critical, notify CEO
                    logger.critical("HEARTBEAT: Agent '%s' UNRESPONSIVE — %d consecutive misses",
                                    name, hb.consecutive_misses)
                    alert = {
                        "timestamp": datetime.now().isoformat(),
                        "agent": name,
                        "severity": "CRITICAL",
                        "message": f"Unresponsive — {hb.consecutive_misses} consecutive misses",
                    }
                    self._alerts.append(alert)

                    # Escalate to CEO
                    await self.bus.publish(AgentMessage(
                        from_agent="heartbeat_monitor",
                        to_agent="ceo",
                        message_type="agent_unresponsive",
                        payload={"agent": name, "misses": hb.consecutive_misses},
                        priority="urgent",
                    ))

                    # If it's a critical agent, escalate further
                    if name in ("executor", "position_manager", "compliance"):
                        logger.critical("HEARTBEAT: CRITICAL agent '%s' down — "
                                        "escalating to emergency protocol", name)
                        await self.bus.publish(AgentMessage(
                            from_agent="heartbeat_monitor",
                            to_agent="ceo",
                            message_type="critical_agent_down",
                            payload={
                                "agent": name,
                                "action": "Consider flattening all positions",
                            },
                            priority="urgent",
                        ))

    async def _on_message(self, message):
        """Handle heartbeat messages from agents."""
        if message.message_type == "heartbeat":
            self.record_heartbeat(
                message.from_agent,
                message.payload.get("status", "ok"),
            )

    def get_status(self) -> dict:
        """Get a complete health dashboard."""
        alive = sum(1 for hb in self._heartbeats.values() if hb.is_alive)
        total = len(self._heartbeats)
        return {
            "timestamp": datetime.now().isoformat(),
            "agents_alive": alive,
            "agents_total": total,
            "health_pct": (alive / total * 100) if total > 0 else 0,
            "agents": {
                name: {
                    "alive": hb.is_alive,
                    "last_beat": hb.last_beat.isoformat() if hb.last_beat else None,
                    "status": hb.last_status,
                    "consecutive_misses": hb.consecutive_misses,
                    "total_beats": hb.total_beats,
                    "overdue_seconds": hb.overdue_seconds if not hb.is_alive else 0,
                }
                for name, hb in self._heartbeats.items()
            },
            "recent_alerts": self._alerts[-20:],
        }

    def get_summary_line(self) -> str:
        """One-line health summary for logging."""
        alive = sum(1 for hb in self._heartbeats.values() if hb.is_alive)
        total = len(self._heartbeats)
        down = [n for n, hb in self._heartbeats.items() if not hb.is_alive and hb.last_beat]
        line = f"HEARTBEAT: {alive}/{total} agents alive"
        if down:
            line += f" | DOWN: {', '.join(down)}"
        return line
