"""Tests for Paperclip heartbeat monitor."""

import pytest
import asyncio
from unittest.mock import patch
from datetime import datetime, timedelta

from src.heartbeat import AgentHeartbeat, HeartbeatMonitor
from src.message_bus import MessageBus
from src.models import AgentMessage


class TestAgentHeartbeat:
    def test_initial_state(self):
        hb = AgentHeartbeat("executor", 60)
        assert hb.is_alive is False
        assert hb.consecutive_misses == 0
        assert hb.total_beats == 0

    def test_record_beat(self):
        hb = AgentHeartbeat("executor", 60)
        hb.record_beat("ok")
        assert hb.is_alive is True
        assert hb.total_beats == 1
        assert hb.last_status == "ok"

    def test_check_alive(self):
        hb = AgentHeartbeat("executor", 60)
        hb.record_beat()
        assert hb.check() is True

    def test_check_missed(self):
        hb = AgentHeartbeat("executor", 60)
        hb.last_beat = datetime.now() - timedelta(seconds=180)  # 3x interval
        hb.is_alive = True
        result = hb.check()
        assert result is False
        assert hb.consecutive_misses == 1
        assert hb.is_alive is False

    def test_consecutive_misses_accumulate(self):
        hb = AgentHeartbeat("executor", 60)
        hb.last_beat = datetime.now() - timedelta(seconds=180)
        hb.check()
        hb.check()
        hb.check()
        assert hb.consecutive_misses == 3

    def test_beat_resets_misses(self):
        hb = AgentHeartbeat("executor", 60)
        hb.last_beat = datetime.now() - timedelta(seconds=180)
        hb.check()
        hb.check()
        assert hb.consecutive_misses == 2
        hb.record_beat()
        assert hb.consecutive_misses == 0
        assert hb.is_alive is True


class TestHeartbeatMonitor:
    def test_agent_intervals_defined(self):
        """All core and specialist agents have heartbeat intervals."""
        core = ["ceo", "scout", "analyst", "strategist", "executor",
                "position_manager", "compliance", "auditor"]
        specialists = ["sector_trend_watcher", "volume_flow_analyst",
                       "twitter_sentiment", "futures_index_watcher",
                       "earnings_calendar", "options_flow_scanner",
                       "technical_analyst", "short_interest_tracker"]

        for agent in core + specialists:
            assert agent in HeartbeatMonitor.AGENT_INTERVALS, f"{agent} missing interval"
            assert HeartbeatMonitor.AGENT_INTERVALS[agent] > 0

    def test_critical_agents_have_fast_heartbeat(self):
        """Executor and Position Manager should have 60s heartbeat."""
        assert HeartbeatMonitor.AGENT_INTERVALS["executor"] == 60
        assert HeartbeatMonitor.AGENT_INTERVALS["position_manager"] == 60

    def test_record_heartbeat(self):
        bus = MessageBus()
        monitor = HeartbeatMonitor(bus)
        monitor.record_heartbeat("executor", "ok")
        status = monitor.get_status()
        assert status["agents"]["executor"]["alive"] is True
        assert status["agents"]["executor"]["total_beats"] == 1

    def test_dynamic_agent_registration(self):
        bus = MessageBus()
        monitor = HeartbeatMonitor(bus)
        # Register a new agent the CEO just hired
        monitor.record_heartbeat("custom_agent_xyz", "ok")
        status = monitor.get_status()
        assert "custom_agent_xyz" in status["agents"]
        assert status["agents"]["custom_agent_xyz"]["alive"] is True

    def test_get_summary_line(self):
        bus = MessageBus()
        monitor = HeartbeatMonitor(bus)
        monitor.record_heartbeat("executor")
        monitor.record_heartbeat("ceo")
        line = monitor.get_summary_line()
        assert "HEARTBEAT:" in line
        assert "agents alive" in line

    def test_health_percentage(self):
        bus = MessageBus()
        monitor = HeartbeatMonitor(bus)
        # Record beats for half the agents
        for name in list(HeartbeatMonitor.AGENT_INTERVALS.keys())[:8]:
            monitor.record_heartbeat(name)
        status = monitor.get_status()
        assert status["agents_alive"] == 8
        assert status["health_pct"] == 8 / len(HeartbeatMonitor.AGENT_INTERVALS) * 100


@pytest.mark.asyncio
async def test_heartbeat_via_bus():
    """Test that heartbeats flow through the message bus."""
    bus = MessageBus()
    monitor = HeartbeatMonitor(bus)
    await monitor.start()

    # Simulate an agent sending a heartbeat via the bus
    await bus.publish(AgentMessage(
        from_agent="executor",
        to_agent="heartbeat_monitor",
        message_type="heartbeat",
        payload={"status": "ok", "agent": "executor"},
    ))

    # Give it a moment to process
    await asyncio.sleep(0.1)

    status = monitor.get_status()
    assert status["agents"]["executor"]["alive"] is True
    assert status["agents"]["executor"]["total_beats"] == 1

    await monitor.stop()
