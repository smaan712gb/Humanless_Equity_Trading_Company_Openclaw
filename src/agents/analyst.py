"""Analyst agent — deep research and due diligence."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from .base import BaseAgent
from ..models import AgentMessage, AnalystReport, ScoutReport

if TYPE_CHECKING:
    from ..connection import IBKRConnection

logger = logging.getLogger(__name__)

ANALYSIS_PROMPT = """You are the Analyst. Perform deep research on this ticker.

## Scout Report
{scout_report}

## Current Price Data
{price_data}

## Instructions
Analyze the setup and produce a structured research report. Score the edge from 1-10.
Consider: catalyst quality, technical levels, fundamental flags, historical comparables.

If edge score < 6, recommend PASS.

Output as JSON with these fields:
ticker, edge_score (int 1-10), catalyst, catalyst_quality (Strong/Moderate/Weak/None),
support (float), resistance (float), vwap (float), atr (float), atr_pct (float),
fundamental_flags (string), historical_comparables (string),
recommendation (TRADEABLE/MARGINAL/PASS), reasoning (string)

Only return the JSON object, no other text.
"""


class AnalystAgent(BaseAgent):
    name = "analyst"
    model = "deepseek-reasoner"
    temperature = 0.1

    def __init__(self, deepseek, bus, ibkr: IBKRConnection):
        super().__init__(deepseek, bus)
        self.ibkr = ibkr

    async def analyze(self, scout_report: ScoutReport) -> AnalystReport | None:
        """Perform deep analysis on a ticker surfaced by the Scout."""
        logger.info("[Analyst] Researching %s...", scout_report.ticker)

        # Get current price
        price = await self.ibkr.get_market_price(scout_report.ticker)
        price_data = {"ticker": scout_report.ticker, "current_price": price}

        prompt = ANALYSIS_PROMPT.format(
            scout_report=json.dumps(scout_report.model_dump(mode="json"), indent=2),
            price_data=json.dumps(price_data, indent=2),
        )

        response = await self.think(prompt, use_reasoner=True)
        report = self._parse_report(response)

        if report:
            self.log_to_diary(
                f"ANALYST: {report.ticker} score={report.edge_score}/10 "
                f"catalyst={report.catalyst_quality} → {report.recommendation}"
            )

            # Only forward TRADEABLE and MARGINAL to Strategist
            if report.recommendation in ("TRADEABLE", "MARGINAL"):
                await self.send(
                    to="strategist",
                    message_type="analyst_report",
                    payload={
                        "analyst_report": report.model_dump(mode="json"),
                        "scout_report": scout_report.model_dump(mode="json"),
                    },
                )
            else:
                logger.info("[Analyst] %s scored %d/10 — PASS", report.ticker, report.edge_score)

        return report

    def _parse_report(self, response: str) -> AnalystReport | None:
        try:
            text = response.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()

            data = json.loads(text)
            return AnalystReport(
                ticker=data.get("ticker", ""),
                edge_score=int(data.get("edge_score", 0)),
                catalyst=data.get("catalyst", ""),
                catalyst_quality=data.get("catalyst_quality", "None"),
                support=float(data.get("support", 0)),
                resistance=float(data.get("resistance", 0)),
                vwap=float(data.get("vwap", 0)),
                atr=float(data.get("atr", 0)),
                atr_pct=float(data.get("atr_pct", 0)),
                fundamental_flags=data.get("fundamental_flags", ""),
                historical_comparables=data.get("historical_comparables", ""),
                recommendation=data.get("recommendation", "PASS"),
                reasoning=data.get("reasoning", ""),
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            logger.error("[Analyst] Failed to parse response: %s", e)
            return None

    async def on_message(self, message: AgentMessage):
        if message.message_type == "scout_report":
            report = ScoutReport(**message.payload)
            await self.analyze(report)
