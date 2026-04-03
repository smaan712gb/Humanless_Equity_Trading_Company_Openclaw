"""Strategist agent — decision maker and position sizer."""

from __future__ import annotations

import json
import logging
import math
from typing import TYPE_CHECKING

from .base import BaseAgent
from ..models import (
    AgentMessage, AnalystReport, ScoutReport, TradePlan,
    Direction, PortfolioState, GatekeeperResult,
)

if TYPE_CHECKING:
    from ..connection import IBKRConnection
    from ..risk_gatekeeper import RiskGatekeeper
    from ..config import RiskLimits

logger = logging.getLogger(__name__)

STRATEGY_PROMPT = """You are the Strategist. Based on the Analyst report, decide whether to trade.

## Analyst Report
{analyst_report}

## Portfolio State
{portfolio_state}

## Risk Limits
- Max position: {max_position_pct}% of portfolio
- Max loss per trade: ${max_loss_usd}
- Daily P&L so far: ${daily_pnl}
- Daily target: ${daily_target}

## Instructions
If the edge is sufficient, produce a Trade Plan. Consider:
1. Which strategy fits best (momentum_breakout, mean_reversion, gap_fade, earnings_volatility)?
2. Direction (LONG or SHORT)?
3. Entry price, stop loss, take profit
4. The stop loss must produce a max loss <= ${max_loss_usd}

Output as JSON with fields:
ticker, strategy, direction (LONG/SHORT), entry_price (float), stop_loss (float),
take_profit (float), shares (int), confidence (int 1-10), reasoning (string)

If the setup is not good enough, return: {{"action": "NO_TRADE", "reasoning": "..."}}

Only return the JSON object, no other text.
"""


class StrategistAgent(BaseAgent):
    name = "strategist"
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
        # Rolling performance stats for Kelly calculation
        self._trade_history: list[dict] = []  # {strategy, won, pnl}
        self._consecutive_losses = 0

    async def evaluate(
        self, analyst_report: AnalystReport, scout_report: ScoutReport
    ) -> TradePlan | None:
        """Evaluate an opportunity and produce a Trade Plan if the edge is sufficient."""
        logger.info("[Strategist] Evaluating %s (score: %d/10)...",
                     analyst_report.ticker, analyst_report.edge_score)

        # Minimum score check
        if analyst_report.edge_score < 6:
            logger.info("[Strategist] %s score too low (%d) — SKIP",
                        analyst_report.ticker, analyst_report.edge_score)
            return None

        # Check consecutive losses
        if self._consecutive_losses >= 3:
            logger.warning("[Strategist] 3 consecutive losses — pausing 30 min")
            self.log_to_diary("STRATEGIST: Paused — 3 consecutive losses. Cooling off.")
            return None

        # Get portfolio state
        portfolio = await self.ibkr.get_portfolio_state()

        # Check if daily target already hit
        if portfolio.daily_pnl >= self.risk_limits.daily_profit_target_usd:
            logger.info("[Strategist] Daily target reached ($%.0f) — no new trades",
                        portfolio.daily_pnl)
            return None

        # Ask DeepSeek for trade decision
        prompt = STRATEGY_PROMPT.format(
            analyst_report=json.dumps(analyst_report.model_dump(mode="json"), indent=2),
            portfolio_state=json.dumps({
                "equity": portfolio.equity,
                "buying_power": portfolio.buying_power,
                "open_positions": portfolio.position_count,
                "daily_pnl": portfolio.daily_pnl,
            }, indent=2),
            max_position_pct=self.risk_limits.max_single_position_pct,
            max_loss_usd=self.risk_limits.per_trade_max_loss_usd,
            daily_pnl=f"{portfolio.daily_pnl:,.0f}",
            daily_target=f"{self.risk_limits.daily_profit_target_usd:,.0f}",
        )

        response = await self.think(prompt, use_reasoner=True)
        plan = self._parse_plan(response, analyst_report, scout_report, portfolio)

        if not plan:
            return None

        # Apply Kelly sizing
        plan = self._apply_kelly_sizing(plan, portfolio)

        # Validate through Risk Gatekeeper
        gk_result = self.gatekeeper.validate_trade(plan, portfolio)
        if not gk_result.approved:
            logger.warning("[Strategist] Gatekeeper REJECTED %s: %s",
                          plan.ticker, gk_result.message)
            self.log_to_diary(f"STRATEGIST: {plan.ticker} rejected by gatekeeper: {gk_result.message}")
            return None

        # Check if CEO approval needed
        if plan.notional > portfolio.equity * 0.10:
            plan.requires_ceo_approval = True

        self.log_to_diary(
            f"STRATEGIST: {plan.direction.value} {plan.ticker} "
            f"{plan.shares}sh @ ${plan.entry_price:.2f} "
            f"stop=${plan.stop_loss:.2f} target=${plan.take_profit:.2f} "
            f"notional=${plan.notional:,.0f}"
        )

        # Send to Compliance for pre-trade validation
        await self.send(
            to="compliance",
            message_type="trade_plan",
            payload=plan.model_dump(mode="json"),
            priority="high",
        )

        return plan

    def _apply_kelly_sizing(self, plan: TradePlan, portfolio: PortfolioState) -> TradePlan:
        """Apply Kelly Criterion position sizing."""
        # Get stats for this strategy
        strategy_trades = [t for t in self._trade_history if t["strategy"] == plan.strategy]

        if len(strategy_trades) < 20:
            # Not enough data — use conservative Quarter Kelly
            plan.kelly_fraction = "quarter"
            # Default to 2% of equity
            max_risk = portfolio.equity * 0.02
        else:
            wins = [t for t in strategy_trades if t["won"]]
            p = len(wins) / len(strategy_trades)
            q = 1 - p
            avg_win = sum(t["pnl"] for t in wins) / len(wins) if wins else 0
            losses = [t for t in strategy_trades if not t["won"]]
            avg_loss = abs(sum(t["pnl"] for t in losses) / len(losses)) if losses else 1
            b = avg_win / avg_loss if avg_loss > 0 else 1

            f_star = (b * p - q) / b if b > 0 else 0
            f_star = max(0, min(f_star, 0.25))  # cap at 25%

            plan.kelly_p = round(p, 4)
            plan.kelly_b = round(b, 4)
            plan.kelly_f_star = round(f_star, 4)

            # Half Kelly default, Quarter Kelly if volatile
            kelly_mult = 0.5 if plan.kelly_fraction == "half" else 0.25
            max_risk = portfolio.equity * f_star * kelly_mult

        # Calculate shares from risk
        if plan.direction == Direction.LONG:
            risk_per_share = plan.entry_price - plan.stop_loss
        else:
            risk_per_share = plan.stop_loss - plan.entry_price

        if risk_per_share > 0:
            kelly_shares = int(max_risk / risk_per_share)
            # Cap to max position value
            max_shares_by_value = int(self.risk_limits.max_position_value_usd / plan.entry_price)
            plan.shares = min(kelly_shares, max_shares_by_value, plan.shares)

        plan.notional = plan.shares * plan.entry_price
        return plan

    def _parse_plan(
        self, response: str,
        analyst_report: AnalystReport,
        scout_report: ScoutReport,
        portfolio: PortfolioState,
    ) -> TradePlan | None:
        try:
            text = response.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()

            data = json.loads(text)

            if data.get("action") == "NO_TRADE":
                logger.info("[Strategist] No trade: %s", data.get("reasoning", ""))
                return None

            return TradePlan(
                ticker=data["ticker"],
                strategy=data.get("strategy", "momentum_breakout"),
                direction=Direction(data["direction"]),
                entry_price=float(data["entry_price"]),
                stop_loss=float(data["stop_loss"]),
                take_profit=float(data["take_profit"]),
                shares=int(data["shares"]),
                confidence=int(data.get("confidence", 5)),
                scout_report=scout_report,
                analyst_report=analyst_report,
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            logger.error("[Strategist] Failed to parse plan: %s", e)
            return None

    def record_trade_result(self, strategy: str, won: bool, pnl: float):
        """Record a completed trade for Kelly calculation updates."""
        self._trade_history.append({"strategy": strategy, "won": won, "pnl": pnl})
        if won:
            self._consecutive_losses = 0
        else:
            self._consecutive_losses += 1

    async def on_message(self, message: AgentMessage):
        if message.message_type == "analyst_report":
            analyst = AnalystReport(**message.payload["analyst_report"])
            scout = ScoutReport(**message.payload["scout_report"])
            await self.evaluate(analyst, scout)
        elif message.message_type == "trade_result":
            self.record_trade_result(
                message.payload["strategy"],
                message.payload["won"],
                message.payload["pnl"],
            )
