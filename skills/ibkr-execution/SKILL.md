# IBKR Execution Skill

## Description
Provides order placement and management capabilities through Interactive Brokers
TWS API via the `ib_async` Python library. This is the firm's primary execution interface.

## Authorized Agents
- Executor (full access: place, modify, cancel orders)
- Position Manager (close/reduce orders only)
- Risk Gatekeeper (emergency liquidation only)

## Capabilities
- Place bracket orders (entry + stop-loss + take-profit)
- Place limit orders, stop orders, trailing stop orders
- Cancel and modify open orders
- Query order status and fill details
- Query account summary and buying power
- Subscribe to real-time execution reports

## Connection Parameters
```python
from ib_async import IB, Stock, LimitOrder, StopOrder, BracketOrder

ib = IB()
# Live: ib.connect('127.0.0.1', 7496, clientId=1)
# Paper: ib.connect('127.0.0.1', 7497, clientId=1)
```

## Order Templates

### Bracket Order (Primary)
```python
contract = Stock(symbol, 'SMART', 'USD')
bracket = ib.bracketOrder(
    action='BUY',           # or 'SELL' for short
    quantity=shares,
    limitPrice=entry_price,
    takeProfitPrice=target_price,
    stopLossPrice=stop_price
)
for order in bracket:
    ib.placeOrder(contract, order)
```

### Trailing Stop
```python
from ib_async import Order
trailing = Order(
    action='SELL',
    orderType='TRAIL',
    totalQuantity=shares,
    trailingPercent=1.5
)
ib.placeOrder(contract, trailing)
```

### Emergency Market Close
```python
close_order = MarketOrder('SELL', shares)  # or 'BUY' to cover short
ib.placeOrder(contract, close_order)
```

## Pre-Flight Checks
Before every order:
1. Verify API connection is alive: `ib.isConnected()`
2. Verify contract is valid: `ib.qualifyContracts(contract)`
3. Check buying power: `ib.accountSummary()`
4. Validate through Risk Gatekeeper skill

## Error Codes
- 201: Order rejected (insufficient margin)
- 202: Order cancelled
- 110: Price out of range
- 103: Duplicate order
- 504: Not connected

## Safety
- NEVER place MARKET orders for entries — LIMIT only
- ALWAYS include stop-loss in bracket — no naked entries
- ALWAYS verify position state after fill before placing new orders
- Log every order with timestamp, details, and result
