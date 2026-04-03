"""CEO agent — orchestrator and daily P&L owner."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from .base import BaseAgent
from ..models import AgentMessage

if TYPE_CHECKING:
    from ..connection import IBKRConnection

logger = logging.getLogger(__name__)


class CEOAgent(BaseAgent):
    name = "ceo"
    model = "deepseek-reasoner"
    temperature = 0.1

    def __init__(self, deepseek, bus, ibkr: IBKRConnection):
        super().__init__(deepseek, bus)
        self.ibkr = ibkr
        self._daily_pnl = 0.0
        self._approved_tickers: set[str] = {"LITE", "ASML", "MU", "APP"}
        self._trading_active = True
        self._alerts: list[dict] = []

    async def morning_briefing(self):
        """Run the morning briefing — review yesterday's audit, approve today's plan."""
        logger.info("[CEO] Morning briefing starting...")

        portfolio = await self.ibkr.get_portfolio_state()
        self._daily_pnl = portfolio.daily_pnl

        prompt = f"""Morning briefing. Today is {datetime.now().strftime('%Y-%m-%d')}.

Portfolio state:
- Equity: ${portfolio.equity:,.0f}
- Yesterday's P&L: ${portfolio.daily_pnl:,.0f}
- Open positions: {portfolio.position_count}
- Margin used: {portfolio.margin_used_pct:.1%}

Approved watchlist: {', '.join(sorted(self._approved_tickers))}

Provide your assessment and any adjustments to today's trading parameters.
Keep it under 200 words. Focus on: risk stance, position sizing preference, any tickers to add/remove."""

        assessment = await self.think(prompt, use_reasoner=True)
        self.log_to_diary(f"CEO BRIEFING: {assessment[:500]}")
        logger.info("[CEO] Briefing: %s", assessment[:200])

        # Signal Scout to begin scanning
        await self.send(to="scout", message_type="request_scan", payload={})

    async def approve_ticker(self, ticker: str) -> bool:
        """Approve a new ticker for the active watchlist."""
        if ticker in self._approved_tickers:
            return True

        prompt = f"""The Scout has proposed adding {ticker} to the active watchlist.
Current approved list: {', '.join(sorted(self._approved_tickers))}

Should we approve this ticker? Consider: diversification, correlation with existing tickers,
and our focus on high-beta momentum names.

Reply with just APPROVE or REJECT and a one-sentence reason."""

        response = await self.think(prompt, use_reasoner=True)
        approved = "APPROVE" in response.upper()

        if approved:
            self._approved_tickers.add(ticker)
            self.log_to_diary(f"CEO: Approved {ticker} for watchlist")
        else:
            self.log_to_diary(f"CEO: Rejected {ticker} — {response[:100]}")

        return approved

    async def handle_daily_target_hit(self, daily_pnl: float):
        """Handle when the daily profit target is reached."""
        logger.info("[CEO] Daily target hit: $%.0f", daily_pnl)
        self.log_to_diary(f"CEO: Daily target HIT — P&L ${daily_pnl:,.0f}. Scaling down.")
        # Position Manager and Strategist handle the mechanical response
        # CEO logs and confirms
        await self.send(
            to="broadcast",
            message_type="ceo_directive",
            payload={"directive": "SCALE_DOWN", "reason": "Daily target reached"},
        )

    async def handle_drawdown_warning(self, daily_pnl_pct: float):
        """Handle approaching drawdown limit."""
        logger.warning("[CEO] Drawdown warning: %.2f%%", daily_pnl_pct)
        self.log_to_diary(f"CEO: Drawdown warning {daily_pnl_pct:.2f}%. Halting new entries.")
        self._trading_active = False
        await self.send(
            to="broadcast",
            message_type="ceo_directive",
            payload={"directive": "HALT_NEW_ENTRIES", "reason": "Approaching drawdown limit"},
            priority="urgent",
        )

    async def end_of_day_review(self):
        """End-of-day review and summary."""
        portfolio = await self.ibkr.get_portfolio_state()
        summary = (
            f"EOD Summary — P&L: ${portfolio.daily_pnl:,.0f} "
            f"({portfolio.daily_pnl_pct:+.2f}%) | "
            f"Equity: ${portfolio.equity:,.0f} | "
            f"Positions: {portfolio.position_count}"
        )
        self.log_to_diary(f"CEO: {summary}")
        logger.info("[CEO] %s", summary)

        # Request audit
        await self.send(to="auditor", message_type="request_audit", payload={
            "daily_pnl": portfolio.daily_pnl,
            "equity": portfolio.equity,
        })

    async def on_message(self, message: AgentMessage):
        if message.message_type == "daily_target_hit":
            await self.handle_daily_target_hit(message.payload["daily_pnl"])
        elif message.message_type == "drawdown_warning":
            await self.handle_drawdown_warning(message.payload["daily_pnl_pct"])
        elif message.message_type == "positions_flattened":
            self.log_to_diary(f"CEO: All positions flattened — {message.payload.get('reason', '')}")
        elif message.message_type == "portfolio_summary":
            self._daily_pnl = message.payload.get("daily_pnl", 0)
        elif message.message_type == "ticker_approval_request":
            approved = await self.approve_ticker(message.payload["ticker"])
            await self.send(
                to=message.from_agent,
                message_type="ticker_approval_response",
                payload={"ticker": message.payload["ticker"], "approved": approved},
            )
