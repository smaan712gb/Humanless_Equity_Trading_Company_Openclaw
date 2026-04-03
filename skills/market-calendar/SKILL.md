---
name: market-calendar
description: US equity market hours, ETH/RTH sessions, holidays, early closes, and IBKR session rules
user-invocable: false
metadata:
  openclaw:
    requires:
      bins: []
      env: []
---

# Market Calendar Skill

## Description
Provides awareness of US equity market hours, extended trading hours, holidays,
early closes, and IBKR-specific session rules. All trading agents must consult
this skill before placing orders.

## Authorized Agents
- All agents (read access)

## Trading Sessions (US Equities — Eastern Time)

### Extended Hours — Pre-Market (ETH)
- **Hours:** 04:00 - 09:30 ET
- **IBKR support:** Yes — via ARCA, ISLAND (NASDAQ)
- **Liquidity:** Thin. Wider spreads. Use LIMIT orders only.
- **Strategy notes:** Good for reacting to overnight news, earnings releases, gap setups.
  Size down to 25% of normal. No market orders ever.

### Regular Trading Hours (RTH)
- **Hours:** 09:30 - 16:00 ET
- **Primary session.** Full liquidity, tightest spreads.
- **Strategy notes:** Full position sizing. All strategies active.

### Extended Hours — After-Market (ETH)
- **Hours:** 16:00 - 20:00 ET
- **IBKR support:** Yes — via ARCA, ISLAND
- **Liquidity:** Thin after 17:00. Use LIMIT orders only.
- **Strategy notes:** React to after-hours earnings. Size down to 25%.
  Close positions before 19:30 to avoid end-of-session illiquidity.

### Session Summary
```
04:00 ─── ETH Pre-Market ──── 09:30 ─── RTH ──── 16:00 ─── ETH After-Hours ──── 20:00
  │  Thin liquidity, LIMIT only  │  Full session  │  Thin liquidity, LIMIT only  │
  │  25% position size            │  100% size     │  25% position size            │
```

## IBKR Order Types by Session
| Session | Market Orders | Limit Orders | Stop Orders | Trailing Stops |
|---------|:---:|:---:|:---:|:---:|
| ETH Pre-Market | NO | YES | YES | YES |
| RTH | YES | YES | YES | YES |
| ETH After-Hours | NO | YES | YES | YES |

**IMPORTANT:** For ETH orders, set `outsideRth=True` on all orders:
```python
order = LimitOrder('BUY', quantity, price)
order.outsideRth = True  # Required for extended hours
```

## US Market Holidays 2026 (NYSE/NASDAQ Closed)
| Date | Holiday | Market Status |
|------|---------|--------------|
| Jan 1 (Thu) | New Year's Day | CLOSED |
| Jan 19 (Mon) | Martin Luther King Jr. Day | CLOSED |
| Feb 16 (Mon) | Presidents' Day | CLOSED |
| **Apr 3 (Fri)** | **Good Friday** | **CLOSED** |
| May 25 (Mon) | Memorial Day | CLOSED |
| Jun 19 (Fri) | Juneteenth | CLOSED |
| Jul 3 (Fri) | Independence Day (observed) | CLOSED |
| Sep 7 (Mon) | Labor Day | CLOSED |
| Nov 26 (Thu) | Thanksgiving Day | CLOSED |
| Dec 25 (Fri) | Christmas Day | CLOSED |

## Early Close Days 2026 (Market closes at 13:00 ET)
| Date | Reason |
|------|--------|
| Nov 27 (Fri) | Day after Thanksgiving |
| Dec 24 (Thu) | Christmas Eve |

## Holiday Detection Logic
```python
from datetime import date

HOLIDAYS_2026 = {
    date(2026, 1, 1),   # New Year's Day
    date(2026, 1, 19),  # MLK Day
    date(2026, 2, 16),  # Presidents' Day
    date(2026, 4, 3),   # Good Friday
    date(2026, 5, 25),  # Memorial Day
    date(2026, 6, 19),  # Juneteenth
    date(2026, 7, 3),   # Independence Day observed
    date(2026, 9, 7),   # Labor Day
    date(2026, 11, 26), # Thanksgiving
    date(2026, 12, 25), # Christmas
}

EARLY_CLOSE_2026 = {
    date(2026, 11, 27), # Day after Thanksgiving
    date(2026, 12, 24), # Christmas Eve
}

def is_market_open(d: date) -> bool:
    if d.weekday() >= 5:  # Saturday/Sunday
        return False
    if d in HOLIDAYS_2026:
        return False
    return True

def get_close_time(d: date) -> str:
    if d in EARLY_CLOSE_2026:
        return "13:00"
    return "16:00"
```

## IBKR Session Rules
- Connection stays active 24/7 — IB Gateway does not disconnect between sessions
- Orders placed outside session hours are queued and submitted when session opens
- GTC (Good Till Cancelled) orders persist across sessions
- DAY orders expire at end of current session (RTH close or ETH close depending on outsideRth)
- **Auto-liquidation:** IBKR will liquidate positions if margin requirements not met at any time
