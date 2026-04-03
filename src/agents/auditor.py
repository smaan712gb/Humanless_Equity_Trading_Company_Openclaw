"""Auditor agent — post-session review using Attacker-Defender-Judge pattern."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING

from .base import BaseAgent
from ..models import AgentMessage, AuditFinding, Severity

if TYPE_CHECKING:
    from ..message_bus import MessageBus

logger = logging.getLogger(__name__)

AUDIT_PROMPT = """You are the Auditor. Review today's trading session using the Attacker-Defender-Judge pattern.

## Today's Message Log
{message_log}

## Daily P&L
${daily_pnl}

## Instructions

PHASE 1 — ATTACK: Find every potential error, missed signal, rule violation, or suboptimal decision.
PHASE 2 — DEFEND: For each finding, consider if the agent's action was reasonable given available information.
PHASE 3 — JUDGE: Issue a ruling with severity and confidence.

Output as a JSON array of findings, each with:
- severity: "CRITICAL" / "MAJOR" / "MINOR"
- confidence: float 0.0-1.0
- agent: the agent name
- issue: what went wrong
- evidence: specific data points
- defense: the agent's likely justification
- ruling: your final assessment
- recommendation: specific action to fix
- rsi_candidate: true/false (should this trigger a code/prompt change?)

If the session was clean, return an empty array [].
Only return the JSON array.
"""


class AuditorAgent(BaseAgent):
    name = "auditor"
    model = "deepseek-reasoner"
    temperature = 0.0  # deterministic

    def __init__(self, deepseek, bus: MessageBus):
        super().__init__(deepseek, bus)
        self._findings_history: list[list[AuditFinding]] = []

    async def run_audit(self, daily_pnl: float = 0.0) -> list[AuditFinding]:
        """Run the full Attacker-Defender-Judge audit on today's session."""
        logger.info("[Auditor] Running daily audit...")

        # Get today's message log
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        messages = self.bus.get_log(since=today_start)

        # Summarize messages for the prompt (limit to avoid token overflow)
        msg_summaries = []
        for msg in messages[-200:]:  # last 200 messages
            msg_summaries.append({
                "time": msg.timestamp.strftime("%H:%M:%S"),
                "from": msg.from_agent,
                "to": msg.to_agent,
                "type": msg.message_type,
                "priority": msg.priority,
            })

        prompt = AUDIT_PROMPT.format(
            message_log=json.dumps(msg_summaries, indent=2),
            daily_pnl=f"{daily_pnl:,.0f}",
        )

        response = await self.think(prompt, use_reasoner=True)
        findings = self._parse_findings(response)

        # Log findings
        critical = [f for f in findings if f.severity == Severity.CRITICAL]
        major = [f for f in findings if f.severity == Severity.MAJOR]
        minor = [f for f in findings if f.severity == Severity.MINOR]

        self.log_to_diary(
            f"AUDITOR: Audit complete — "
            f"{len(critical)} Critical, {len(major)} Major, {len(minor)} Minor findings"
        )

        # Escalate critical findings to Founder (via CEO for now)
        for finding in critical:
            logger.critical("[Auditor] CRITICAL: %s — %s", finding.agent, finding.issue)
            await self.send(
                to="ceo",
                message_type="audit_critical",
                payload=finding.model_dump(mode="json"),
                priority="urgent",
            )

        # Send full report to CEO
        await self.send(
            to="ceo",
            message_type="audit_report",
            payload={
                "date": datetime.now().strftime("%Y-%m-%d"),
                "daily_pnl": daily_pnl,
                "findings_count": {"critical": len(critical), "major": len(major), "minor": len(minor)},
                "findings": [f.model_dump(mode="json") for f in findings],
                "rsi_candidates": [f.model_dump(mode="json") for f in findings if f.rsi_candidate],
            },
        )

        self._findings_history.append(findings)
        return findings

    def _parse_findings(self, response: str) -> list[AuditFinding]:
        try:
            text = response.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()

            items = json.loads(text)
            findings = []
            for item in items:
                findings.append(AuditFinding(
                    severity=Severity(item.get("severity", "MINOR")),
                    confidence=float(item.get("confidence", 0.5)),
                    agent=item.get("agent", "unknown"),
                    issue=item.get("issue", ""),
                    evidence=item.get("evidence", ""),
                    defense=item.get("defense", ""),
                    ruling=item.get("ruling", ""),
                    recommendation=item.get("recommendation", ""),
                    rsi_candidate=bool(item.get("rsi_candidate", False)),
                ))
            return findings
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            logger.error("[Auditor] Failed to parse audit response: %s", e)
            return []

    async def on_message(self, message: AgentMessage):
        if message.message_type == "request_audit":
            await self.run_audit(message.payload.get("daily_pnl", 0))
