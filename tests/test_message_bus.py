"""Tests for the inter-agent message bus."""

import pytest
import asyncio
from src.message_bus import MessageBus
from src.models import AgentMessage


@pytest.fixture
def bus():
    return MessageBus()


@pytest.mark.asyncio
async def test_publish_to_subscriber(bus):
    received = []

    async def handler(msg: AgentMessage):
        received.append(msg)

    bus.subscribe("analyst", handler)

    await bus.publish(AgentMessage(
        from_agent="scout", to_agent="analyst",
        message_type="scout_report", payload={"ticker": "LITE"},
    ))

    assert len(received) == 1
    assert received[0].payload["ticker"] == "LITE"


@pytest.mark.asyncio
async def test_message_not_delivered_to_wrong_agent(bus):
    received = []

    async def handler(msg: AgentMessage):
        received.append(msg)

    bus.subscribe("compliance", handler)

    await bus.publish(AgentMessage(
        from_agent="scout", to_agent="analyst",
        message_type="scout_report", payload={},
    ))

    assert len(received) == 0


@pytest.mark.asyncio
async def test_broadcast(bus):
    received_a = []
    received_b = []

    async def handler_a(msg): received_a.append(msg)
    async def handler_b(msg): received_b.append(msg)

    bus.subscribe("analyst", handler_a)
    bus.subscribe("strategist", handler_b)

    await bus.publish(AgentMessage(
        from_agent="ceo", to_agent="broadcast",
        message_type="ceo_directive", payload={"directive": "HALT"},
    ))

    assert len(received_a) == 1
    assert len(received_b) == 1


@pytest.mark.asyncio
async def test_broadcast_excludes_sender(bus):
    received = []

    async def handler(msg): received.append(msg)

    bus.subscribe("ceo", handler)

    await bus.publish(AgentMessage(
        from_agent="ceo", to_agent="broadcast",
        message_type="ceo_directive", payload={},
    ))

    # CEO should NOT receive its own broadcast
    assert len(received) == 0


@pytest.mark.asyncio
async def test_message_log(bus):
    await bus.publish(AgentMessage(
        from_agent="scout", to_agent="analyst",
        message_type="report", payload={},
    ))
    await bus.publish(AgentMessage(
        from_agent="analyst", to_agent="strategist",
        message_type="analysis", payload={},
    ))

    log = bus.get_log()
    assert len(log) == 2

    scout_log = bus.get_log(agent="scout")
    assert len(scout_log) == 1


@pytest.mark.asyncio
async def test_multiple_subscribers(bus):
    received_1 = []
    received_2 = []

    async def h1(msg): received_1.append(msg)
    async def h2(msg): received_2.append(msg)

    bus.subscribe("executor", h1)
    bus.subscribe("executor", h2)

    await bus.publish(AgentMessage(
        from_agent="compliance", to_agent="executor",
        message_type="execute_trade", payload={},
    ))

    assert len(received_1) == 1
    assert len(received_2) == 1
