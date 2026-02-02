# Credits & Acknowledgments

This project builds upon the work of several open-source projects and public data sources.

## Open Source Projects

### Fuzzy Market Matching Algorithm
**Source:** [prediction-market-arbitrage-bot](https://github.com/realfishsam/prediction-market-arbitrage-bot) by [@realfishsam](https://github.com/realfishsam)  
**Used in:** `crossplatform.py`  
**Implementation:** Jaccard + Levenshtein similarity (60/40 weighted) for cross-platform market matching  
**License:** MIT

Our implementation in `crossplatform.py` adapts their fuzzy matching logic to compare Kalshi and Polymarket markets.

### Inspiration & Research

**pmxt** (⭐440+) - [pmxt.dev](https://pmxt.dev)  
Unified API for prediction markets. Inspired our cross-platform data fetching approach.

**dr-manhattan** (⭐129+) - [github.com/guzus/dr-manhattan](https://github.com/guzus/dr-manhattan)  
CCXT-style interface for prediction markets. Reference for API abstraction patterns.

## Data Sources

### Official Government Data
- **Bureau of Economic Analysis (BEA)** - GDP data and GDPNow forecasts
- **Bureau of Labor Statistics (BLS)** - CPI, unemployment, and economic indicators
- **Federal Reserve** - Interest rate decisions and economic data

### News Verification
- **Google News RSS** - News article search and validation
- Used for cross-referencing market events with real-world news

### Market Data APIs
- **Kalshi API** - [api.elections.kalshi.com](https://api.elections.kalshi.com/trade-api/v2)  
  Public market data, rules, and pricing
  
- **Polymarket Gamma API** - [gamma-api.polymarket.com](https://gamma-api.polymarket.com)  
  Public market events and pricing for cross-platform comparison

## Methodology Inspiration

The "Junk Bond" strategy (focusing on extreme-priced markets with official data sources) was inspired by discussions in the prediction market trading community and the legendary "$50 → $248K overnight" Kalshi story that circulated online.

## Community

Thanks to the prediction markets community on:
- r/algotrading
- r/wallstreetbets  
- Kalshi Discord
- Various trading Discord servers

## Disclaimer

This project is for educational purposes. We are not affiliated with Kalshi, Polymarket, or any prediction market platform. All data is accessed through public APIs.

---

If we've missed any attribution, please open an issue or PR. Proper credit matters.
