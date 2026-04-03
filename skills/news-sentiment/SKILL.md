# News Sentiment Skill

## Description
Provides real-time news scanning and sentiment analysis for market-moving headlines.
Uses browser automation and NLP to assess catalyst quality for trading decisions.

## Authorized Agents
- Scout (headline scanning, breaking news alerts)
- Analyst (deep article analysis, catalyst validation)

## Capabilities
- Scan financial news headlines in real-time
- Score sentiment: Strong Positive / Positive / Neutral / Negative / Strong Negative
- Identify catalyst type: earnings, M&A, analyst upgrade/downgrade, FDA, macro, etc.
- Cross-reference headlines with ticker watchlist
- Detect "no news" moves (volume without catalyst — often institutional flow)

## Sentiment Scoring
```
Score Range:
  0.8 - 1.0: Strong Positive (upgrade, beat, M&A premium)
  0.5 - 0.8: Positive (good earnings, sector tailwind)
  0.3 - 0.5: Neutral (noise, already priced in)
  0.1 - 0.3: Negative (miss, downgrade, sector headwind)
  0.0 - 0.1: Strong Negative (fraud, delisting risk, black swan)
```

## Catalyst Classification
- **Earnings**: beat/miss, guidance, revision
- **Analyst Action**: upgrade, downgrade, initiation, price target change
- **Corporate Action**: M&A, buyback, offering, insider transaction
- **Regulatory**: FDA, antitrust, trade policy
- **Macro**: rate decision, employment, CPI/PPI
- **Technical**: short squeeze, gamma exposure, options expiry

## Output Format
```
NEWS ALERT — [ticker] — [timestamp]
Headline: "[headline text]"
Source: [source]
Sentiment: [score] ([label])
Catalyst Type: [type]
Relevance: HIGH / MEDIUM / LOW
Impact Assessment: [1-2 sentences]
```

## Safety
- Always verify headline source credibility
- Flag unverified or single-source breaking news as LOW confidence
- Do NOT trade on rumors — only on confirmed catalyst
- Cross-reference multiple sources before upgrading to HIGH relevance
