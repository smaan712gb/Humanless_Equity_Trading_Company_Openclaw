"""Inter-agent message bus — all agent communication flows through here."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import datetime
from typing import Callable, Coroutine, Any

from tools.models import AgentMessage

logger = logging.getLogger(__name__)

Callback = Callable[[AgentMessage], Coroutine[Any, Any, None]]


class MessageBus:
    """Async pub/sub message bus for inter-agent communication."""

    def __init__(self):
        self._subscribers: dict[str, list[Callback]] = defaultdict(list)
        self._message_log: list[AgentMessage] = []
        self._lock = asyncio.Lock()

    def subscribe(self, agent_name: str, callback: Callback):
        """Subscribe an agent to receive messages addressed to it."""
        self._subscribers[agent_name].append(callback)
        logger.info("Agent '%s' subscribed to message bus", agent_name)

    async def publish(self, message: AgentMessage):
        """Send a message to a specific agent or broadcast."""
        async with self._lock:
            self._message_log.append(message)

        log_line = (
            f"[MSG] {message.from_agent} → {message.to_agent} "
            f"({message.message_type}) priority={message.priority}"
        )
        logger.info(log_line)

        if message.to_agent == "broadcast":
            for agent_name, callbacks in self._subscribers.items():
                if agent_name != message.from_agent:
                    for cb in callbacks:
                        await cb(message)
        else:
            for cb in self._subscribers.get(message.to_agent, []):
                await cb(message)

    async def publish_and_wait(
        self, message: AgentMessage, response_type: str, timeout: float = 60.0
    ) -> AgentMessage | None:
        """Publish a message and wait for a specific response type."""
        response_event = asyncio.Event()
        response_holder: list[AgentMessage] = []

        async def catch_response(msg: AgentMessage):
            if msg.message_type == response_type and msg.to_agent == message.from_agent:
                response_holder.append(msg)
                response_event.set()

        self._subscribers[message.from_agent].append(catch_response)
        await self.publish(message)

        try:
            await asyncio.wait_for(response_event.wait(), timeout=timeout)
            return response_holder[0] if response_holder else None
        except asyncio.TimeoutError:
            logger.warning(
                "Timeout waiting for %s response from %s",
                response_type,
                message.to_agent,
            )
            return None
        finally:
            self._subscribers[message.from_agent].remove(catch_response)

    def get_log(
        self, since: datetime | None = None, agent: str | None = None
    ) -> list[AgentMessage]:
        """Retrieve message log, optionally filtered."""
        msgs = self._message_log
        if since:
            msgs = [m for m in msgs if m.timestamp >= since]
        if agent:
            msgs = [m for m in msgs if m.from_agent == agent or m.to_agent == agent]
        return msgs
