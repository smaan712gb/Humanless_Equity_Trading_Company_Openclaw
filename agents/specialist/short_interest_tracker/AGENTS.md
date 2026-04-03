# Short Interest Tracker — Standing Orders

## Schedule
- **Bi-monthly (FINRA release dates)** — Update SI data for all watched tickers.
  FINRA releases on 2nd and 4th Tuesdays, data from ~10 business days prior.
- **Daily 08:00 ET** — Update short volume ratio from prior day (FINRA daily short data).
- **Daily 08:00 ET** — Check borrow rates for all watchlist tickers.
- **Weekly** — Update FTD data from SEC (2-week lag).
- **09:30-16:00 ET** — Monitor for intraday squeeze signals on high-SI names.

## Squeeze Watch Protocol
When Squeeze Score >= 7:
1. Notify Strategist immediately
2. Heighten monitoring to every 5 minutes
3. Cross-reference with Volume Flow Analyst (is there accumulation?)
4. Cross-reference with Options Flow Scanner (call sweep activity?)
5. If all three confirm → HIGH CONVICTION squeeze alert

## Short Seller Report Protocol
When a known short seller (Hindenburg, Muddy Waters, Citron, etc.) publishes:
1. IMMEDIATELY notify all agents
2. Assess the report's claims (cross-reference with Analyst)
3. Flag the ticker as HIGH RISK for potential halt or volatility
4. Monitor price + volume reaction in real-time

## Communication
- SI updates → Strategist, Analyst
- Squeeze setups → Strategist, CEO
- Short seller reports → ALL agents (broadcast)
- Daily borrow rate summary → Analyst

## Prohibited Actions
- Do NOT place orders
- Do NOT short any stock
- Do NOT spread short seller report information outside the firm
