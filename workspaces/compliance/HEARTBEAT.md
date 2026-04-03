# Compliance Heartbeat Checklist (Every 5 minutes)

- [ ] Check for pending Trade Plans awaiting validation
- [ ] For each pending plan: run PDT, wash sale, margin, risk policy checks
- [ ] Monitor aggregate portfolio exposure vs risk limits
- [ ] Check margin utilization — alert if approaching 100%
- [ ] Update wash sale tracker — any tickers now eligible for re-entry?
- [ ] Update PDT day trade counter (rolling 5-day window)
- [ ] If any check fails: VETO and notify Strategist
- [ ] If all checks pass: approve and forward to Executor
