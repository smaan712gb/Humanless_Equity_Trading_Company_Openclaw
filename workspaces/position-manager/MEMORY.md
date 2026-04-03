# Position Manager — Durable Memory

## Account Parameters
- Max concurrent positions: 8
- Max single position: 15% of portfolio
- Max sector exposure: 30%
- Daily drawdown limit: -2%
- Daily profit target: $20,000
- Max hold time: 120 minutes
- Trailing stop default: 1.5% (ATR-adjusted)
- Flatten deadline: 15:50 ET

## Position Tracking Template
<!-- Updated in real-time during sessions, archived to daily diary -->

## Historical Exit Performance
<!-- Track: exits at stop vs target vs time limit vs force-close -->
<!-- Used to optimize trailing stop parameters -->

## Ticker-Specific Notes
### LITE
- Typical intraday range: volatile, 3-5% swings common
- Tighter stops may get whipsawed — use ATR-based

### ASML
- Large cap, more orderly moves
- Standard trailing stop works well

### MU
- Memory cycle sensitivity — can gap on any semi news
- Watch for sector-wide moves

### APP
- High short interest → squeeze potential on up moves
- Can reverse sharply — be quick on trailing stop adjustments
