"""Scout agent — market scanner and ticker discovery."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from .base import BaseAgent
from ..models import AgentMessage, ScoutReport

if TYPE_CHECKING:
    from ..connection import IBKRConnection

logger = logging.getLogger(__name__)

SCAN_PROMPT = """You are the Scout. Analyze the following market data and produce Scout Reports.

## Current Watchlist
Core tickers to always check: LITE, ASML, MU, APP

## Market Data
{market_data}

## Instructions
For each ticker that passes your filters (beta > 1.5, volume > 2M, price $20-$500, ATR > 2%):
1. Assess the setup quality
2. Identify any catalyst
3. Rate as INVESTIGATE, WATCH, or SKIP

Output your findings as a JSON array of objects with these fields:
ticker, beta, volume_ratio, atr_pct, catalyst, sector, recommendation

If nothing passes filters, return an empty array [].
Only return the JSON array, no other text.
"""


class ScoutAgent(BaseAgent):
    name = "scout"
    model = "deepseek-chat"
    temperature = 0.3

    def __init__(self, deepseek, bus, ibkr: IBKRConnection):
        super().__init__(deepseek, bus)
        self.ibkr = ibkr
        self._hot_of_day_count = 0
        self._max_hot_of_day = 3

    async def scan_market(self) -> list[ScoutReport]:
        """Run a full market scan and produce Scout Reports."""
        logger.info("[Scout] Running market scan...")

        # Gather market data for core watchlist
        market_data = await self._gather_market_data()

        # Ask DeepSeek to analyze
        prompt = SCAN_PROMPT.format(market_data=json.dumps(market_data, indent=2))
        response = await self.think(prompt)

        # Parse response
        reports = self._parse_reports(response)

        # Apply hot-of-day limit
        investigate_reports = [r for r in reports if r.recommendation == "INVESTIGATE"]
        non_core = [r for r in investigate_reports if r.ticker not in ("LITE", "ASML", "MU", "APP")]

        if len(non_core) > self._max_hot_of_day - self._hot_of_day_count:
            non_core = non_core[:self._max_hot_of_day - self._hot_of_day_count]

        self._hot_of_day_count += len(non_core)

        # Log and send to Analyst
        for report in reports:
            if report.recommendation in ("INVESTIGATE", "WATCH"):
                self.log_to_diary(
                    f"SCOUT: {report.ticker} β={report.beta:.1f} "
                    f"vol={report.volume_ratio:.1f}x ATR={report.atr_pct:.1f}% "
                    f"→ {report.recommendation}"
                )
                await self.send(
                    to="analyst",
                    message_type="scout_report",
                    payload=report.model_dump(mode="json"),
                )

        logger.info("[Scout] Scan complete. %d tickers surfaced.", len(reports))
        return reports

    async def _gather_market_data(self) -> list[dict]:
        """Gather real-time data for core watchlist from IBKR."""
        tickers = ["LITE", "ASML", "MU", "APP"]
        data = []
        for ticker in tickers:
            price = await self.ibkr.get_market_price(ticker)
            data.append({
                "ticker": ticker,
                "price": price,
                "note": "Core watchlist",
            })
        return data

    def _parse_reports(self, response: str) -> list[ScoutReport]:
        """Parse DeepSeek's JSON response into ScoutReport objects."""
        try:
            # Strip markdown code fences if present
            text = response.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()

            items = json.loads(text)
            reports = []
            for item in items:
                reports.append(ScoutReport(
                    ticker=item.get("ticker", ""),
                    beta=float(item.get("beta", 0)),
                    volume_ratio=float(item.get("volume_ratio", 0)),
                    atr_pct=float(item.get("atr_pct", 0)),
                    catalyst=item.get("catalyst", ""),
                    sector=item.get("sector", ""),
                    recommendation=item.get("recommendation", "SKIP"),
                ))
            return reports
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.error("[Scout] Failed to parse response: %s", e)
            return []

    async def on_message(self, message: AgentMessage):
        if message.message_type == "request_scan":
            await self.scan_market()

    def reset_daily(self):
        self._hot_of_day_count = 0
