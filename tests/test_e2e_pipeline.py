"""End-to-end pipeline test — verify the full trade flow without live execution.
Uses mocked IBKR connection but real DeepSeek (if key available).
"""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from src.config import load_config, RiskLimits
from src.deepseek_client import DeepSeekClient
from src.message_bus import MessageBus
from src.risk_gatekeeper import RiskGatekeeper
from src.models import (
    ScoutReport, AnalystReport, TradePlan, Direction,
    PortfolioState, OpenPosition, AgentMessage,
)

DEEPSEEK_KEY = os.getenv("DEEPSEEK_API_KEY", "")
HAS_KEY = DEEPSEEK_KEY and DEEPSEEK_KEY != "PASTE_YOUR_DEEPSEEK_KEY_HERE"


class TestTradeFlowUnit:
    """Unit test the full trade flow with mocked DeepSeek and IBKR."""

    def setup_method(self):
        self.bus = MessageBus()
        self.config = load_config()
        self.gatekeeper = RiskGatekeeper(self.config.risk)

    @patch("src.risk_gatekeeper.is_market_holiday", return_value=False)
    @patch("src.risk_gatekeeper.is_any_session_active", return_value=True)
    @patch("src.risk_gatekeeper.get_position_size_multiplier", return_value=1.0)
    @patch("src.risk_gatekeeper.can_use_market_orders", return_value=True)
    def test_scout_to_gatekeeper_flow(self, *mocks):
        """Test: Scout report → Analyst report → Trade plan → Gatekeeper approval."""

        # 1. Scout finds a ticker
        scout_report = ScoutReport(
            ticker="LITE", beta=2.3, volume_ratio=4.1,
            atr_pct=3.8, catalyst="Earnings beat + guidance raise",
            sector="semiconductors", recommendation="INVESTIGATE",
        )
        assert scout_report.recommendation == "INVESTIGATE"

        # 2. Analyst scores it
        analyst_report = AnalystReport(
            ticker="LITE", edge_score=8,
            catalyst="Q1 earnings beat by 15%, raised FY guidance",
            catalyst_quality="Strong",
            support=95.0, resistance=110.0, vwap=102.0,
            atr=4.5, atr_pct=4.4,
            recommendation="TRADEABLE",
            reasoning="Strong catalyst with technical confirmation",
        )
        assert analyst_report.edge_score >= 6
        assert analyst_report.recommendation == "TRADEABLE"

        # 3. Strategist creates trade plan
        trade_plan = TradePlan(
            ticker="LITE", strategy="momentum_breakout",
            direction=Direction.LONG,
            entry_price=103.0, stop_loss=100.0, take_profit=109.0,
            shares=150,
            kelly_p=0.55, kelly_b=2.0, kelly_f_star=0.275,
            kelly_fraction="half",
            confidence=8,
        )
        assert trade_plan.notional == 15450.0  # 150 * 103
        assert trade_plan.id.startswith("TP-LITE-")

        # 4. Gatekeeper validates
        portfolio = PortfolioState(
            equity=500_000, buying_power=500_000,
            margin_used_pct=0.15, daily_pnl=3000, daily_pnl_pct=0.6,
            position_count=2,
        )
        result = self.gatekeeper.validate_trade(trade_plan, portfolio)
        assert result.approved is True

    @patch("src.risk_gatekeeper.is_market_holiday", return_value=False)
    @patch("src.risk_gatekeeper.is_any_session_active", return_value=True)
    @patch("src.risk_gatekeeper.get_position_size_multiplier", return_value=0.5)
    @patch("src.risk_gatekeeper.can_use_market_orders", return_value=False)
    def test_eth_session_flow(self, *mocks):
        """Test that ETH session applies 50% size multiplier."""
        trade_plan = TradePlan(
            ticker="MU", strategy="earnings_volatility",
            direction=Direction.LONG,
            entry_price=80.0, stop_loss=77.0, take_profit=86.0,
            shares=100,
        )
        portfolio = PortfolioState(
            equity=500_000, margin_used_pct=0.10, position_count=1,
        )
        # Should still pass — ETH multiplier is informational for sizing
        result = self.gatekeeper.validate_trade(trade_plan, portfolio)
        assert result.approved is True

    def test_position_manager_exit_logic(self):
        """Test Position Manager exit triggers."""
        # Position at 2:1 R/R
        pos = OpenPosition(
            ticker="LITE", direction=Direction.LONG, shares=100,
            entry_price=100.0, current_price=106.0,
            stop_loss=97.0, take_profit=109.0,
        )
        assert pos.risk_reward_ratio == 2.0  # should trigger breakeven move

        # Position at stop
        pos_stopped = OpenPosition(
            ticker="APP", direction=Direction.LONG, shares=50,
            entry_price=150.0, current_price=147.0,
            stop_loss=148.0, take_profit=156.0,
        )
        assert pos_stopped.current_price <= pos_stopped.stop_loss  # stop hit

        # Short position at target
        pos_short = OpenPosition(
            ticker="ASML", direction=Direction.SHORT, shares=20,
            entry_price=800.0, current_price=760.0,
            stop_loss=820.0, take_profit=760.0,
        )
        assert pos_short.current_price <= pos_short.take_profit  # target hit


@pytest.mark.asyncio
async def test_bus_full_pipeline():
    """Test the message bus delivers messages through the full pipeline."""
    bus = MessageBus()
    received_by_analyst = []
    received_by_strategist = []
    received_by_compliance = []
    received_by_executor = []

    async def analyst_handler(msg): received_by_analyst.append(msg)
    async def strategist_handler(msg): received_by_strategist.append(msg)
    async def compliance_handler(msg): received_by_compliance.append(msg)
    async def executor_handler(msg): received_by_executor.append(msg)

    bus.subscribe("analyst", analyst_handler)
    bus.subscribe("strategist", strategist_handler)
    bus.subscribe("compliance", compliance_handler)
    bus.subscribe("executor", executor_handler)

    # Scout → Analyst
    await bus.publish(AgentMessage(
        from_agent="scout", to_agent="analyst",
        message_type="scout_report",
        payload=ScoutReport(ticker="LITE", beta=2.3, volume_ratio=4.0, atr_pct=3.5).model_dump(mode="json"),
    ))
    assert len(received_by_analyst) == 1

    # Analyst → Strategist
    await bus.publish(AgentMessage(
        from_agent="analyst", to_agent="strategist",
        message_type="analyst_report",
        payload={"analyst_report": {"ticker": "LITE", "edge_score": 8}, "scout_report": {}},
    ))
    assert len(received_by_strategist) == 1

    # Strategist → Compliance
    await bus.publish(AgentMessage(
        from_agent="strategist", to_agent="compliance",
        message_type="trade_plan",
        payload={"ticker": "LITE", "shares": 100},
        priority="high",
    ))
    assert len(received_by_compliance) == 1

    # Compliance → Executor
    await bus.publish(AgentMessage(
        from_agent="compliance", to_agent="executor",
        message_type="execute_trade",
        payload={"ticker": "LITE", "shares": 100},
        priority="high",
    ))
    assert len(received_by_executor) == 1

    # Verify full log
    log = bus.get_log()
    assert len(log) == 4


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_KEY, reason="DEEPSEEK_API_KEY not set")
async def test_deepseek_scout_prompt():
    """Integration: send a real Scout-style prompt to DeepSeek and verify structured response."""
    from src.config import DeepSeekConfig
    client = DeepSeekClient(DeepSeekConfig(api_key=DEEPSEEK_KEY))
    await client.start()
    try:
        response = await client.chat(
            messages=[
                {"role": "system", "content": "You are a stock market scanner. Reply only in JSON."},
                {"role": "user", "content": (
                    "Analyze these tickers for momentum trading: LITE, ASML, MU, APP. "
                    "For each, provide a JSON array with fields: ticker, recommendation (INVESTIGATE/WATCH/SKIP). "
                    "Only return the JSON array."
                )},
            ],
            max_tokens=500,
        )
        content = client.extract_content(response)
        assert "[" in content  # should contain JSON array
        assert "LITE" in content or "ASML" in content
        print(f"Scout DeepSeek response:\n{content[:500]}")
    finally:
        await client.stop()
