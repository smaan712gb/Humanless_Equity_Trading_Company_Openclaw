---
name: position-monitor
description: Query real-time open positions, P&L, account equity, and margin from IBKR
user-invocable: false
metadata:
  openclaw:
    requires:
      bins: [python3]
      env: [IBKR_HOST, IBKR_PORT]
---

# Position Monitor Skill

## Description
Provides real-time visibility into all open positions, P&L, and account state via
IBKR TWS API. This is the firm's portfolio awareness layer.

## Authorized Agents
- Position Manager (full access — primary consumer)
- Strategist (read-only — position awareness for decisions)
- Compliance (read-only — exposure monitoring)
- CEO (read-only — aggregate P&L)
- Auditor (read-only — historical review)

## Capabilities
- Query all open positions with real-time prices
- Query per-position unrealized P&L
- Query aggregate daily P&L (realized + unrealized)
- Query account equity, buying power, margin utilization
- Subscribe to real-time P&L updates via event handlers
- Query trade history for the current session

## Data Queries

### All Open Positions
```python
positions = ib.positions()
# Returns: [Position(account, contract, position, avgCost)]
for pos in positions:
    print(f"{pos.contract.symbol}: {pos.position} shares @ ${pos.avgCost:.2f}")
```

### Real-Time P&L (Aggregate)
```python
pnl = ib.pnl(account)
# Returns: PnL(dailyPnL, unrealizedPnL, realizedPnL)
```

### Real-Time P&L (Per Position)
```python
pnl_single = ib.pnlSingle(account, modelCode='', conId=contract.conId)
# Returns: PnLSingle(dailyPnL, unrealizedPnL, realizedPnL, position, value)
```

### Account Summary
```python
summary = ib.accountSummary()
# Key fields: NetLiquidation, BuyingPower, MaintMarginReq, AvailableFunds
```

### Today's Executions
```python
fills = ib.fills()
# Returns all fills for current session
for fill in fills:
    print(f"{fill.contract.symbol}: {fill.execution.shares} @ ${fill.execution.price}")
```

## Event Handlers
```python
# Subscribe to real-time P&L updates
def on_pnl_update(pnl):
    if pnl.dailyPnL <= -drawdown_limit:
        trigger_emergency_liquidation()
    elif pnl.dailyPnL >= profit_target:
        trigger_scale_down()

ib.pnlEvent += on_pnl_update
```

## Refresh Cycle
- Position data: every 60 seconds (Position Manager's heartbeat)
- P&L data: real-time via event subscription
- Account summary: every 5 minutes
- Trade history: on-demand after each fill

## Safety
- This skill provides READ-ONLY data to most agents
- Only Position Manager and Executor can act on this data
- Stale data (> 2 min old) must be flagged as potentially unreliable
