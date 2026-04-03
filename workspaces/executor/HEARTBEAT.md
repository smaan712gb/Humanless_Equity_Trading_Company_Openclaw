# Executor Heartbeat Checklist (Every 60 seconds)

- [ ] Verify IBKR Gateway connection is alive
- [ ] Check for pending trade plans from Compliance (approved, waiting execution)
- [ ] Check for emergency close requests from Position Manager
- [ ] Monitor open order statuses — any fills, partial fills, rejections?
- [ ] If any order pending > 30s unfilled, alert Strategist for re-pricing
- [ ] Confirm outsideRth flag is correct for current session
- [ ] Log all fills with slippage calculation to daily diary
