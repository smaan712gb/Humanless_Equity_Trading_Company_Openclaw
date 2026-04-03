#!/bin/bash
# backtest.sh — Run strategy backtests via Microsoft Qlib
# Usage: ./scripts/backtest.sh [strategy_name] [start_date] [end_date]

set -euo pipefail

STRATEGY="${1:-all}"
START="${2:-2025-01-01}"
END="${3:-2026-03-31}"

echo "=== Backtesting: ${STRATEGY} (${START} to ${END}) ==="

python3 -c "
import sys
# Qlib backtest runner
# This script validates strategy parameters against historical data
# before they are deployed to the live system.

strategy = '${STRATEGY}'
start = '${START}'
end = '${END}'

print(f'Strategy: {strategy}')
print(f'Period: {start} to {end}')
print()

# Minimum acceptance criteria (from factor-mining SKILL.md)
CRITERIA = {
    'sharpe_ratio': 1.5,
    'max_drawdown': 0.15,  # 15%
    'min_trades': 100,
    'profit_factor': 1.5,
}

strategies = {
    'momentum_breakout': {
        'min_win_rate': 0.40,
        'universe': ['LITE', 'ASML', 'MU', 'APP'],
        'timeframe': '5min',
    },
    'mean_reversion': {
        'min_win_rate': 0.55,
        'universe': ['LITE', 'ASML', 'MU', 'APP'],
        'timeframe': '1min',
    },
    'gap_fade': {
        'min_win_rate': 0.50,
        'universe': ['LITE', 'ASML', 'MU', 'APP'],
        'timeframe': '30min',
    },
    'earnings_volatility': {
        'min_win_rate': 0.45,
        'universe': ['LITE', 'ASML', 'MU', 'APP'],
        'timeframe': 'daily',
    },
}

if strategy == 'all':
    targets = strategies.keys()
else:
    targets = [strategy]

for s in targets:
    if s not in strategies:
        print(f'ERROR: Unknown strategy {s}')
        sys.exit(1)
    print(f'--- Backtesting {s} ---')
    print(f'  Universe: {strategies[s][\"universe\"]}')
    print(f'  Timeframe: {strategies[s][\"timeframe\"]}')
    print(f'  Min win rate: {strategies[s][\"min_win_rate\"]}')
    print(f'  Acceptance: Sharpe >= {CRITERIA[\"sharpe_ratio\"]}, MaxDD <= {CRITERIA[\"max_drawdown\"]*100}%')
    print(f'  [TODO: Connect to Qlib engine]')
    print()

print('=== Backtest framework ready. Connect Qlib for live results. ===')
"
