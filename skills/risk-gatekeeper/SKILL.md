---
name: risk-gatekeeper
description: Mechanical circuit breaker enforcing hard risk limits — validates every trade before execution
user-invocable: false
metadata:
  openclaw:
    requires:
      bins: [python3]
      env: []
---

# Risk Gatekeeper Skill

## Description
A lightweight, non-reasoning validation layer that sits between the AI agents and the
IBKR API. Enforces HARD limits that no LLM can override. This is a mechanical circuit
breaker, not an intelligent agent.

## Authorized Agents
- All trading agents (mandatory pre-trade check)
- Compliance (policy validation)
- Position Manager (exit validation)

## Hard Limits (Non-Negotiable)
These limits are loaded from `paperclip/policies/risk-policy.yaml` at boot.
The Risk Gatekeeper does NOT reason about these — it enforces them mechanically.

```yaml
# From risk-policy.yaml — DO NOT MODIFY WITHOUT FOUNDER APPROVAL
max_single_position_pct: 15
max_sector_exposure_pct: 30
max_concurrent_positions: 8
max_position_value_usd: 100000
daily_max_drawdown_pct: 2.0
per_trade_max_loss_usd: 2500
max_trades_per_day: 40
max_trades_per_hour: 10
min_time_between_trades_sec: 30
max_margin_utilization: 0.60
max_hold_time_minutes: 120
```

## Validation Protocol

### Pre-Trade Check
```python
def validate_trade(trade_plan, portfolio_state):
    checks = {
        'position_size': trade_plan.notional <= portfolio_state.equity * 0.15,
        'sector_exposure': get_sector_exposure(trade_plan.sector) + trade_plan.notional
                          <= portfolio_state.equity * 0.30,
        'position_count': portfolio_state.open_positions < 8,
        'daily_trades': portfolio_state.trade_count_today < 40,
        'hourly_trades': portfolio_state.trade_count_hour < 10,
        'time_between': time_since_last_trade() >= 30,
        'margin': projected_margin(trade_plan) <= 0.60,
        'max_loss': trade_plan.stop_loss_amount <= 2500,
        'trading_hours': is_within_trading_hours(),
        'drawdown': portfolio_state.daily_pnl_pct > -2.0,
        'has_stop_loss': trade_plan.stop_loss is not None,
    }
    
    failed = {k: v for k, v in checks.items() if not v}
    if failed:
        return GatekeeperResult(approved=False, violations=failed)
    return GatekeeperResult(approved=True)
```

### Circuit Breaker Triggers
```python
def check_circuit_breakers(market_state, portfolio_state):
    if portfolio_state.daily_pnl_pct <= -2.0:
        return 'EMERGENCY_LIQUIDATE_ALL'
    if market_state.vix > 35:
        return 'REDUCE_ALL_50PCT'
    if market_state.spy_intraday_change <= -2.0:
        return 'HALT_NEW_ENTRIES'
    if portfolio_state.equity < 200000:
        return 'FULL_SHUTDOWN'
    if ib_disconnect_seconds > 30:
        return 'FLATTEN_ALL'
    return 'ALL_CLEAR'
```

## Response Format
```
GATEKEEPER: APPROVED — all checks passed
GATEKEEPER: REJECTED — violations: [list of failed checks]
GATEKEEPER: CIRCUIT BREAKER — [trigger name] — [action required]
```

## Safety
- This skill has NO reasoning capability — pure mechanical enforcement
- Cannot be overridden by any agent including CEO
- Only the Founder can modify the risk-policy.yaml parameters
- Logs every check with timestamp for audit trail
