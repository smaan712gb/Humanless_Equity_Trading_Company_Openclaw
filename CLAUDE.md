# Humanless Trading Operations

## Overview
Autonomous AI-driven trading firm. Multi-agent architecture targeting $20,000 daily profit
on high-beta momentum stocks (long/short). IBKR is the sole execution venue.

## Architecture
- **Paperclip** — Governance layer (org chart, budgets, policies, approvals)
- **OpenClaw** — Agent runtime (skills, memory, cron, hooks, session routing)
- **DeepSeek** — Primary reasoning brain for ALL agents (deepseek-chat / deepseek-reasoner)
- **Claude** — Optional specialist for code review and complex debugging ONLY

## Trading Focus
- Long/short high-beta equities: semiconductors, momentum tech, hot-of-day
- Core watchlist: LITE, ASML, MU, APP, and dynamically discovered tickers
- Strategies: momentum breakout, mean reversion, gap fade, earnings volatility
- Position sizing: Half Kelly default, Quarter Kelly in high-vol regimes

## Key Conventions
- All agent configs live in `agents/<role>/` with SOUL.md, AGENTS.md, MEMORY.md
- All skills live in `skills/<name>/SKILL.md`
- Daily diaries: `memory/YYYY-MM-DD.md`
- Paperclip governance: `paperclip/`
- DeepSeek is the default model. Do not substitute Claude unless explicitly instructed.

## IBKR Integration
- Execution via `ib_async` library (Python 3.10+)
- TWS API socket connection (port 7497 paper, 7496 live)
- IB Gateway with 4096 MB Java heap
- Risk gatekeeper sits between all agents and the API — non-negotiable
