---
name: factor-mining
description: Discover and backtest quantitative trading factors using RD-Agent and Microsoft Qlib
user-invocable: false
metadata:
  openclaw:
    requires:
      bins: [python3]
      env: []
---

# Factor Mining Skill

## Description
Automates the hypothesis-code-test loop for discovering and validating quantitative
trading factors. Uses Microsoft RD-Agent for factor generation and Microsoft Qlib
for backtesting.

## Authorized Agents
- Scout (factor discovery and screening)
- Analyst (factor validation and scoring)
- Auditor (RSI backtest validation)

## Capabilities
- Generate factor hypotheses from market data and research
- Code factor implementations automatically (RD-Agent)
- Backtest factors against historical data (Qlib)
- Score factors by IC (Information Coefficient), Sharpe, and turnover
- Iterate: propose → test → refine → validate loop

## Factor Categories
- **Momentum**: price momentum, volume momentum, earnings momentum
- **Mean Reversion**: RSI extremes, Bollinger Band deviation, VWAP reversion
- **Volatility**: ATR breakout, IV rank, realized vs implied vol
- **Fundamental**: earnings surprise, revenue growth, margin expansion
- **Flow**: unusual options activity, dark pool prints, short interest changes

## Backtest Requirements
```yaml
minimum_backtest_period: 252 trading days (1 year)
minimum_trade_count: 100
metrics_required:
  - sharpe_ratio: >= 1.5
  - information_coefficient: >= 0.05
  - max_drawdown: <= 15%
  - win_rate: >= 40% (for momentum) / >= 55% (for mean reversion)
  - profit_factor: >= 1.5
out_of_sample_validation: true
walk_forward_windows: 4
```

## Output Format
```
FACTOR REPORT — [factor_name] — [timestamp]
Hypothesis: [description]
Category: [momentum / mean_reversion / volatility / fundamental / flow]
Backtest Period: [start] to [end]
Sharpe Ratio: [X]
IC: [X]
Win Rate: [X]%
Max Drawdown: [X]%
Profit Factor: [X]
Status: VALIDATED / MARGINAL / REJECTED
Recommendation: [deploy / paper_test / reject]
```

## Safety
- All factors must pass out-of-sample validation
- No factor goes live without Auditor review
- Overfitting detection: if in-sample Sharpe > 2x out-of-sample, flag as overfit
- Maximum 2 new factors deployed per week (prevent strategy bloat)
