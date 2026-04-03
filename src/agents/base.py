"""Base agent class — all agents inherit from this."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from ..config import PROJECT_ROOT
from ..models import AgentMessage

if TYPE_CHECKING:
    from ..deepseek_client import DeepSeekClient
    from ..message_bus import MessageBus

logger = logging.getLogger(__name__)


class BaseAgent:
    """Base class for all trading agents."""

    name: str = "base"
    model: str = "deepseek-chat"  # or "deepseek-reasoner"
    temperature: float = 0.3

    def __init__(self, deepseek: DeepSeekClient, bus: MessageBus):
        self.deepseek = deepseek
        self.bus = bus
        self._running = False
        self._system_prompt = ""
        self._load_config_files()

    def _load_config_files(self):
        """Load SOUL.md and AGENTS.md to form the system prompt."""
        agent_dir = self._find_agent_dir()
        if not agent_dir:
            logger.warning("No config directory found for agent '%s'", self.name)
            return

        parts = []

        soul_path = agent_dir / "SOUL.md"
        if soul_path.exists():
            parts.append(soul_path.read_text(encoding="utf-8"))

        agents_path = agent_dir / "AGENTS.md"
        if agents_path.exists():
            parts.append(agents_path.read_text(encoding="utf-8"))

        memory_path = agent_dir / "MEMORY.md"
        if memory_path.exists():
            parts.append(f"## Durable Memory\n{memory_path.read_text(encoding='utf-8')}")

        self._system_prompt = "\n\n---\n\n".join(parts)

    def _find_agent_dir(self) -> Path | None:
        """Locate the agent's config directory."""
        # Direct match: agents/<name>/
        direct = PROJECT_ROOT / "agents" / self.name
        if direct.exists():
            return direct

        # Nested match: agents/trader/<name>/
        trader = PROJECT_ROOT / "agents" / "trader" / self.name
        if trader.exists():
            return trader

        # Specialist match: agents/specialist/<name>/
        specialist = PROJECT_ROOT / "agents" / "specialist" / self.name
        if specialist.exists():
            return specialist

        return None

    async def think(self, prompt: str, use_reasoner: bool = False) -> str:
        """Send a prompt to DeepSeek and get a response."""
        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": prompt},
        ]

        if use_reasoner or self.model == "deepseek-reasoner":
            response = await self.deepseek.reason(
                messages=messages,
                temperature=self.temperature,
            )
        else:
            response = await self.deepseek.chat(
                messages=messages,
                temperature=self.temperature,
            )

        return self.deepseek.extract_content(response)

    async def send(self, to: str, message_type: str, payload: dict, priority: str = "normal"):
        """Send a message to another agent via the bus."""
        msg = AgentMessage(
            from_agent=self.name,
            to_agent=to,
            message_type=message_type,
            payload=payload,
            priority=priority,
        )
        await self.bus.publish(msg)

    async def send_and_wait(
        self, to: str, message_type: str, payload: dict,
        response_type: str, timeout: float = 60.0,
    ) -> AgentMessage | None:
        """Send a message and wait for a response."""
        msg = AgentMessage(
            from_agent=self.name,
            to_agent=to,
            message_type=message_type,
            payload=payload,
        )
        return await self.bus.publish_and_wait(msg, response_type, timeout)

    async def on_message(self, message: AgentMessage):
        """Handle an incoming message. Override in subclasses."""
        logger.debug("[%s] Received %s from %s", self.name, message.message_type, message.from_agent)

    async def start(self):
        """Start the agent, subscribe to bus, and begin heartbeat."""
        self.bus.subscribe(self.name, self.on_message)
        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info("Agent '%s' started (model: %s)", self.name, self.model)

    async def stop(self):
        """Stop the agent and its heartbeat."""
        self._running = False
        if hasattr(self, '_heartbeat_task') and self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        logger.info("Agent '%s' stopped", self.name)

    async def _heartbeat_loop(self):
        """Send periodic heartbeats to the Paperclip heartbeat monitor."""
        from ..heartbeat import HeartbeatMonitor
        interval = HeartbeatMonitor.AGENT_INTERVALS.get(self.name, 900)
        while self._running:
            try:
                await self.send(
                    to="heartbeat_monitor",
                    message_type="heartbeat",
                    payload={"status": "ok", "agent": self.name},
                )
            except Exception:
                pass  # heartbeat failure shouldn't crash the agent
            await asyncio.sleep(interval)

    def log_to_diary(self, entry: str):
        """Append an entry to today's daily diary."""
        diary_dir = PROJECT_ROOT / "memory"
        diary_dir.mkdir(exist_ok=True)
        diary_path = diary_dir / f"{datetime.now().strftime('%Y-%m-%d')}.md"

        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"- **{timestamp}** [{self.name}] {entry}\n"

        with open(diary_path, "a", encoding="utf-8") as f:
            f.write(line)
