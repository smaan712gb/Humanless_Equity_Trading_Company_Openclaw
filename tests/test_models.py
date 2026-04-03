"""Tests for data models — verify all models instantiate and validate correctly."""

import pytest
from datetime import datetime
from src.models import (
    Direction, OrderType, TradeStatus, Severity, CircuitBreakerAction,
    ScoutReport, AnalystReport, TradePlan, ExecutionReport,
    OpenPosition, PortfolioState, GatekeeperResult, ComplianceResult,
    AgentMessage, AuditFinding,
)


class TestScoutReport:
    def test_create_basic(self):
        r = ScoutReport(ticker="LITE", beta=2.1, volume_ratio=3.5, atr_pct=4.2)
        assert r.ticker == "LITE"
        assert r.beta == 2.1
        assert r.recommendation == "INVESTIGATE"

    def test_defaults(self):
        r = ScoutReport(ticker="MU", beta=1.8, volume_ratio=2.0, atr_pct=2.5)
        assert r.catalyst == "None — pure momentum"
        assert r.sector == ""


class TestAnalystReport:
    def test_create(self):
        r = AnalystReport(ticker="ASML", edge_score=8, recommendation="TRADEABLE")
        assert r.edge_score == 8
        assert r.recommendation == "TRADEABLE"

    def test_edge_score_bounds(self):
        with pytest.raises(Exception):
            AnalystReport(ticker="X", edge_score=0)  # min is 1
        with pytest.raises(Exception):
            AnalystReport(ticker="X", edge_score=11)  # max is 10


class TestTradePlan:
    def test_create_with_auto_id(self):
        p = TradePlan(
            ticker="APP", strategy="momentum_breakout",
            direction=Direction.LONG, entry_price=150.0,
            stop_loss=147.0, take_profit=156.0, shares=100,
        )
        assert p.id.startswith("TP-APP-")
        assert p.notional == 15000.0
        assert p.direction == Direction.LONG

    def test_notional_auto_calculated(self):
        p = TradePlan(
            ticker="MU", strategy="mean_reversion",
            direction=Direction.SHORT, entry_price=100.0,
            stop_loss=103.0, take_profit=94.0, shares=200,
        )
        assert p.notional == 20000.0


class TestOpenPosition:
    def test_risk_reward_long(self):
        pos = OpenPosition(
            ticker="LITE", direction=Direction.LONG, shares=100,
            entry_price=100.0, current_price=106.0,
            stop_loss=97.0, take_profit=109.0,
        )
        # Risk = 100 - 97 = 3, Reward = 106 - 100 = 6
        assert pos.risk_reward_ratio == 2.0

    def test_risk_reward_short(self):
        pos = OpenPosition(
            ticker="ASML", direction=Direction.SHORT, shares=50,
            entry_price=800.0, current_price=780.0,
            stop_loss=820.0, take_profit=760.0,
        )
        # Risk = 820 - 800 = 20, Reward = 800 - 780 = 20
        assert pos.risk_reward_ratio == 1.0


class TestPortfolioState:
    def test_total_exposure(self):
        p = PortfolioState(
            equity=500000,
            open_positions=[
                OpenPosition(ticker="A", direction=Direction.LONG, shares=100,
                             entry_price=100.0, current_price=105.0),
                OpenPosition(ticker="B", direction=Direction.SHORT, shares=50,
                             entry_price=200.0, current_price=195.0),
            ],
        )
        # 100 * 105 + 50 * 195 = 10500 + 9750 = 20250
        assert p.total_exposure == 20250.0

    def test_empty_portfolio(self):
        p = PortfolioState(equity=500000)
        assert p.total_exposure == 0.0
        assert p.position_count == 0


class TestGatekeeperResult:
    def test_approved(self):
        r = GatekeeperResult(approved=True, message="All checks passed")
        assert r.approved
        assert r.circuit_breaker == CircuitBreakerAction.ALL_CLEAR

    def test_rejected(self):
        r = GatekeeperResult(
            approved=False,
            violations={"position_size": False, "margin": False},
        )
        assert not r.approved
        assert len(r.violations) == 2


class TestAgentMessage:
    def test_create(self):
        m = AgentMessage(
            from_agent="scout", to_agent="analyst",
            message_type="scout_report", payload={"ticker": "LITE"},
        )
        assert m.from_agent == "scout"
        assert m.priority == "normal"


class TestAuditFinding:
    def test_create(self):
        f = AuditFinding(
            severity=Severity.CRITICAL, confidence=0.95,
            agent="executor", issue="Slippage exceeded 0.5%",
        )
        assert f.severity == Severity.CRITICAL
        assert f.rsi_candidate is False
