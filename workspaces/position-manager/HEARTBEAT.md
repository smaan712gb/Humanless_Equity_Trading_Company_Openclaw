# Position Manager Heartbeat Checklist (Every 60 seconds)

- [ ] Query all open positions via IBKR — update current prices
- [ ] Check each position: stop hit? target hit? 2:1 R/R for breakeven move?
- [ ] Calculate aggregate daily P&L (realized + unrealized)
- [ ] Check drawdown: if approaching -3%, prepare to flatten all
- [ ] Check session: if ETH, are any positions too risky for thin liquidity?
- [ ] If 15:30+ ET on RTH day, begin wind-down (close losers first)
- [ ] If early close day, flatten by 12:45 ET
- [ ] Send position update to Strategist (every 5th beat)
- [ ] Send portfolio summary to CEO (every 30th beat)
- [ ] Log any closes, stops, or target hits to daily diary
