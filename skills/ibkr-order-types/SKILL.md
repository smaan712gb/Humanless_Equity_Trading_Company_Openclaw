# IBKR Order Types — Complete Reference

## Description
Complete reference of all Interactive Brokers order types available via the TWS API.
Agents MUST consult this skill when constructing orders to choose the optimal type
for the current session, strategy, and liquidity conditions.

## Authorized Agents
- Executor (primary — places all orders)
- Strategist (order type selection in trade plans)
- Position Manager (exit order type selection)

---

## Core Order Types

| # | Order Type | `orderType` | Description | ETH | Use Case |
|---|-----------|------------|-------------|:---:|----------|
| 1 | **Market** | `MKT` | Execute immediately at best available price | No | Emergency exits in RTH only |
| 2 | **Limit** | `LMT` | Execute at specified price or better | **Yes** | Default for all entries and ETH trades |
| 3 | **Stop** | `STP` | Market order triggered when stop price hit | No | Avoid — use STP LMT instead |
| 4 | **Stop Limit** | `STP LMT` | Limit order triggered at stop price | **Yes** | Preferred stop-loss type |
| 5 | **Trailing Stop** | `TRAIL` | Stop that trails by fixed amount/% | No | Use TRAIL LIMIT for ETH |
| 6 | **Trailing Stop Limit** | `TRAIL LIMIT` | Trailing stop that triggers limit order | **Yes** | Preferred trailing stop for all sessions |
| 7 | **Market if Touched** | `MIT` | Market order when price reaches trigger | No | Mean reversion entries at support/resistance |
| 8 | **Limit if Touched** | `LIT` | Limit order when price reaches trigger | **Yes** | ETH-safe conditional entries |
| 9 | **Market to Limit** | `MTL` | Market, unfilled becomes limit | No | Opening bell entries in RTH |
| 10 | **Midprice** | `MIDPRICE` | Fills at NBBO midpoint or better | **Yes** | Price improvement on entries |

## Auction / Open / Close Orders

| # | Order Type | `orderType` | Description | ETH | Use Case |
|---|-----------|------------|-------------|:---:|----------|
| 11 | **Market on Open** | `MOO` | Execute at market open (TIF=`OPG`) | No | Gap strategies at open |
| 12 | **Limit on Open** | `LOO` | Limit at open (TIF=`OPG`) | No | Price-controlled open entries |
| 13 | **Market on Close** | `MOC` | Execute at closing price | No | EOD flatten |
| 14 | **Limit on Close** | `LOC` | Limit at close | No | Price-controlled EOD exit |
| 15 | **Auction** | `AUC` | Execute at auction price | No | Opening/closing auctions |

## Advanced / Pegged Orders

| # | Order Type | `orderType` | Description | ETH | Use Case |
|---|-----------|------------|-------------|:---:|----------|
| 16 | **Relative** | `REL` | Pegs to best bid/ask | Yes* | Aggressive price improvement |
| 17 | **Pegged to Midpoint** | `PEG MID` | Pegs to NBBO midpoint | Yes* | Best price improvement |
| 18 | **Pegged to Best** | `PEG BEST` | Competes against best bid/ask (IBKRATS) | Yes* | IBKRATS dark pool |
| 19 | **Snap to Midpoint** | `SNAP MID` | Snaps to midpoint | Yes* | Smart routing improvement |
| 20 | **Discretionary** | `DIS` | Limit with hidden discretionary amount | No | Large orders, hidden intent |

*Exchange-dependent — primarily on IBKRATS venue.

## IB Algo Orders

Set via `algoStrategy` parameter (orderType is typically `LMT`):

| Algo | `algoStrategy` | Description | ETH | Use Case |
|------|---------------|-------------|:---:|----------|
| **Adaptive** | `Adaptive` | Smart price improvement via LMT/MKT | **Yes** | Default for entries — best fill quality |
| **TWAP** | `Twap` | Time-weighted avg price over period | **Yes** | Large position builds |
| **VWAP** | `Vwap` | Volume-weighted avg price over period | **Yes** | Minimize market impact |
| **Arrival Price** | `ArrivalPx` | Targets arrival price | **Yes** | Urgent large orders |
| **Dark Ice** | `DarkIce` | Hidden iceberg for large orders | **Yes** | Stealth accumulation |
| **% of Volume** | `PctVol` | Execute at % of market volume | No | Patient accumulation |
| **Close Price** | `ClosePx` | Targets closing price | No | EOD positioning |

---

## Order Type Selection Matrix (Agent Decision Guide)

### By Session

| Session | Entry Orders | Exit Orders | Stop-Loss | Emergency Close |
|---------|-------------|-------------|-----------|-----------------|
| **ETH Pre-Market** | `LMT`, `MIDPRICE` | `LMT`, `STP LMT` | `STP LMT` | `LMT` (aggressive) |
| **RTH Open (first 5 min)** | `MTL`, `LMT`, `Adaptive` | `LMT`, `MKT` | `STP LMT`, `TRAIL LIMIT` | `MKT` |
| **RTH Active** | `LMT`, `Adaptive`, `MIDPRICE` | `LMT`, `MKT`, `TRAIL LIMIT` | `TRAIL LIMIT`, `STP LMT` | `MKT` |
| **RTH Close (last 10 min)** | `LOC`, `MOC` | `MOC`, `MKT` | `STP LMT` | `MKT` |
| **ETH After-Hours** | `LMT`, `MIDPRICE` | `LMT`, `STP LMT` | `STP LMT` | `LMT` (aggressive) |

### By Strategy

| Strategy | Entry Type | Stop Type | Target Type | Notes |
|----------|-----------|-----------|-------------|-------|
| **Momentum Breakout** | `STP LMT` (buy above resistance) | `TRAIL LIMIT` 1.5% | `LMT` at target | Use `outsideRth=True` in ETH |
| **Mean Reversion** | `LIT` at support/resistance | `STP LMT` fixed | `LMT` at mean | RTH only — needs liquidity |
| **Gap Fade** | `LMT` / `Adaptive` at open | `STP LMT` above gap high | `LMT` at 50% fill | First 30 min of RTH |
| **Scalp** | `LMT` / `MIDPRICE` | `STP LMT` tight | `LMT` quick exit | RTH only |
| **Earnings Volatility** | `LMT` in ETH after earnings | `STP LMT` wide | `LMT` | `outsideRth=True` |
| **Overnight Swing** | `LMT` in after-hours | `STP LMT` 3% wide | `LMT` next day | `outsideRth=True`, GTC |

---

## Implementation Examples (ib_async)

### Limit Order (Default Entry)
```python
from ib_async import LimitOrder
order = LimitOrder('BUY', quantity, limit_price)
order.outsideRth = True  # for ETH
order.tif = 'DAY'        # or 'GTC' for overnight
```

### Stop Limit Order (Preferred Stop-Loss)
```python
from ib_async import Order
order = Order(
    action='SELL',
    orderType='STP LMT',
    totalQuantity=quantity,
    auxPrice=stop_trigger_price,  # trigger price
    lmtPrice=stop_limit_price,   # limit price (slightly below trigger)
)
order.outsideRth = True
```

### Trailing Stop Limit (ETH-Safe Trailing)
```python
order = Order(
    action='SELL',
    orderType='TRAIL LIMIT',
    totalQuantity=quantity,
    trailingPercent=1.5,
    lmtPriceOffset=0.10,  # limit offset from trail
)
order.outsideRth = True
```

### Bracket Order (Entry + Stop + Target)
```python
bracket = ib.bracketOrder(
    action='BUY',
    quantity=100,
    limitPrice=entry_price,
    takeProfitPrice=target_price,
    stopLossPrice=stop_price,
)
for o in bracket:
    o.outsideRth = True  # ETH support
ib.placeOrder(contract, bracket[0])  # parent
ib.placeOrder(contract, bracket[1])  # take profit
ib.placeOrder(contract, bracket[2])  # stop loss
```

### Adaptive Algo (Best Fill Quality)
```python
order = Order(
    action='BUY',
    orderType='LMT',
    totalQuantity=quantity,
    lmtPrice=limit_price,
    algoStrategy='Adaptive',
    algoParams=[TagValue('adaptivePriority', 'Normal')],
    # adaptivePriority: 'Urgent', 'Normal', or 'Patient'
)
```

### Midprice Order (Price Improvement)
```python
order = Order(
    action='BUY',
    orderType='MIDPRICE',
    totalQuantity=quantity,
    lmtPrice=max_price,  # cap price (won't pay more than this)
)
order.outsideRth = True
```

### Market on Close (EOD Flatten)
```python
from ib_async import MarketOrder
order = MarketOrder('SELL', quantity)
order.orderType = 'MOC'
```

### Limit on Open (Gap Strategy)
```python
order = LimitOrder('BUY', quantity, limit_price)
order.tif = 'OPG'  # makes it a Limit on Open
```

---

## Time in Force (TIF) Options

| TIF | Meaning | Use Case |
|-----|---------|----------|
| `DAY` | Expires at end of trading day | Default for intraday |
| `GTC` | Good Till Cancelled | Overnight holds, swing trades |
| `OPG` | At the Opening | MOO/LOO orders |
| `IOC` | Immediate or Cancel | Fill what you can, cancel rest |
| `FOK` | Fill or Kill | All or nothing |
| `GTD` | Good Till Date | Specific expiry date |
| `DTC` | Day Till Cancelled | Extended hours day order |

---

## Key Rules for Agents

1. **NEVER use `MKT` orders in ETH** — use `LMT` with aggressive price instead
2. **NEVER use `STP` (market stop) — always use `STP LMT`** to avoid slippage disasters
3. **NEVER use `TRAIL` in ETH — use `TRAIL LIMIT`** instead
4. **Always set `outsideRth=True`** when placing orders during ETH sessions
5. **Use `Adaptive` algo for entries > $25K** — better fill quality than raw `LMT`
6. **Use `MIDPRICE` for non-urgent entries** — free price improvement
7. **Use `MOC` for EOD flatten** only during RTH and before exchange cutoff
8. **Bracket orders** should always be the default — never enter without stop + target
