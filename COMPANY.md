---
name: Humanless Equity Trading Company
description: Autonomous AI-driven equity trading firm targeting $20K daily profit on high-beta stocks via IBKR
slug: humanless-trading
version: 1.0.0
goals:
  - Generate $20,000 daily profit through autonomous high-beta equity trading (long/short)
  - Trade core universe (LITE, ASML, MU, APP) plus dynamically discovered tickers
  - Operate across ETH pre-market, RTH, and ETH after-hours sessions via IBKR
  - Maintain strict risk discipline (3% max daily drawdown, stop-loss on every position)
  - Build persistent memory of market patterns, levels, and institutional flow
includes:
  - agents/*
  - skills/*
---

# Humanless Equity Trading Company

An autonomous trading firm operated entirely by AI agents, governed by Paperclip,
running on OpenClaw, powered by DeepSeek.

## Architecture

```
Paperclip (governance) → OpenClaw (runtime) → DeepSeek (brain) → IBKR (execution)
```

- **Paperclip** decides WHAT should happen (org chart, budgets, approvals, tasks, audit)
- **OpenClaw** RUNS the agents (workspaces, skills, memory, cron, sessions)
- **DeepSeek** THINKS and chooses actions (deepseek-chat + deepseek-reasoner)
- **IBKR** EXECUTES trades (IB Gateway on port 4002 via ib_async)

## Trading Focus

- Long/short high-beta equities: semiconductors, momentum tech, software
- Core watchlist: LITE, ASML, MU, APP + up to 10 dynamic discoveries per day
- Strategies: momentum breakout, mean reversion, gap fade, scalp, earnings vol, overnight swing
- Position sizing: Half Kelly default, Quarter Kelly in high-vol regimes
- Full buying power authorized, unlimited trades per day

## Team

- 8 core agents (CEO, Scout, Analyst, Strategist, Executor, Position Manager, Compliance, Auditor)
- 7 specialist agents (Sector Trends, Volume Flow, Twitter, Futures/NQ/ES, Earnings, Options Flow, Technicals, Short Interest)
- CEO can hire additional specialists at runtime via the hire-agent skill
