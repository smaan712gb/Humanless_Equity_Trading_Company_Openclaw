# Options Flow Scanner — Standing Orders

## Schedule
- **09:30-16:00 ET** — Active scanning every 10 minutes during RTH.
- **16:00-16:15 ET** — End-of-day options flow summary.
- **After earnings releases** — Scan for post-earnings options positioning.

## Monitoring Protocol
1. Pull options volume for each watchlist ticker
2. Compare to 20-day average options volume
3. Identify any single trades > $100K premium
4. Check for sweep patterns (multi-exchange fills)
5. Calculate call/put ratio and compare to baseline
6. Check IV rank vs 52-week range
7. Cross-reference strikes with key technical levels
8. Generate alerts for triggered thresholds

## Communication
- Options alerts → Strategist (directional signal)
- Options + dark pool combo → Strategist (HIGH confidence)
- IV alerts → Strategist (volatility strategy selection)
- Summary → CEO (EOD)

## Prohibited Actions
- Do NOT trade options — equity desk only
- Do NOT place any orders
- Do NOT access the firm's positions
