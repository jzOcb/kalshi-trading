# Kalshi Trading System

> AI-Powered Prediction Market Scanner with Decision Engine + Paper Trading

📖 [中文文档 / Chinese Documentation](README_CN.md)

[![GitHub](https://img.shields.io/badge/GitHub-jzOcb%2Fkalshi--trading-blue?logo=github)](https://github.com/jzOcb/kalshi-trading)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**Stop gambling, start analyzing.** Automatically scan 500+ Kalshi markets and identify high-confidence opportunities backed by official data sources, news verification, and rigorous risk analysis.

---

## 🎯 What It Does

Scans Kalshi political and economic prediction markets to find data-driven trading opportunities based on:

- ✅ **Official Data Sources** — BEA (GDP), BLS (CPI), Federal Reserve
- ✅ **News Verification** — Google News RSS validation
- ✅ **Rules Analysis** — No ambiguity, no procedural risks
- ✅ **Risk/Reward Scoring** — 0-100 point system

**This is not gambling.** Every recommendation is backed by objective data and validated through paper trading before any real money is risked.

---

## 📊 Features

### Decision Engine
- **Smart Filtering** — Focuses on extreme-priced markets (≥85¢ or ≤12¢) with asymmetric risk/reward
- **Official Source Detection** — Automatically identifies BEA, BLS, Fed data dependencies
- **News Validation** — Requires 3+ recent news articles for confidence
- **Risk Scoring** — 100-point system weighing yield, liquidity, data sources, and risks

### Paper Trading System
- **Trade Tracking** — Auto-logs all BUY recommendations to `trades.json`
- **Settlement Monitoring** — Tracks pending positions and calculates P&L
- **Accuracy Validation** — Only move to real trading after >70% win rate over 20+ trades

### 🆕 Real-Time WebSocket Streaming
- **Live Ticker Updates** — Real-time price changes, spreads, volume
- **Orderbook Streaming** — Full depth + incremental updates
- **Trade Notifications** — All market executions as they happen
- **Fill Alerts** — Your own order executions (authenticated)
- **Auto-Reconnection** — Resilient connection with exponential backoff
- **Data Persistence** — SQLite storage for historical analysis
- **See:** [WEBSOCKET-README.md](WEBSOCKET-README.md) for details


### Automation Ready
- **Cron Integration** — Daily scans with isolated sessions
- **Heartbeat Mode** — Integrated checks in your main agent session
- **Report Archive** — Historical scan results in `reports/`

---

## 🚀 Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/jzOcb/kalshi-trading.git
cd kalshi-trading

# Install dependencies
pip3 install requests beautifulsoup4 lxml

# Run first scan
python3 report_v2.py
```

### View Results

```bash
# See today's recommendations
cat reports/report-$(date +%Y-%m-%d).txt

# Check paper trading status
python3 paper_trading.py summary
```

---

## 📖 How It Works

### 1. Market Scanning
Fetches all open markets from Kalshi API and filters for "Junk Bond" opportunities (extreme prices = high potential return if correct).

### 2. Rules Analysis
- Fetches full market rules via API
- Detects official data sources (BEA, BLS, Fed, Census)
- Flags procedural risks (requires Congress approval, subjective judgment)
- Identifies ambiguous language

### 3. News Validation
- Extracts keywords from market title
- Searches Google News RSS
- Requires 3+ recent articles for confidence boost (+20 points)

### 4. Scoring & Decision

**Scoring Formula:**
```
Base Score = Annual Yield * 10
+ 10 if spread ≤3¢ (good liquidity)
+ 30 if official data source exists
+ 20 if no procedural risk
+ 20 if 3+ news articles
- 10 if ambiguous rules
```

**Decision Thresholds:**
- **≥70** → 🟢 **BUY** (high confidence)
- **50-69** → 🟡 **WAIT** (needs validation)
- **<50** → 🔴 **SKIP** (too risky)

### 5. Paper Trading
All BUY recommendations are automatically logged. Track performance before risking real capital.

---

## 🛠️ Usage Examples

### Daily Scan
```bash
python3 report_v2.py
```

**Sample Output:**
```
🟢 BUY #1 (Score: 100/100)
Will real GDP increase by more than 2.5% in Q4 2025?
YES @ 89¢ → 251% APY (18 days)
✅ BEA data source | ✅ 5 news articles | $200 position
```

### Analyze Specific Market
```bash
python3 decision.py KXGDP-26JAN30-T2.5
```

### Update Paper Trading
```bash
# Mark a trade as won/lost
python3 paper_trading.py update 1 WIN 100

# View all pending trades
python3 paper_trading.py list

# Check overall performance
python3 paper_trading.py summary
```

---

## ⚙️ Automation

### Option 1: Cron (Recommended)
Run daily scans in isolated sessions:

```bash
# Add to crontab
0 9 * * * cd ~/kalshi-trading && python3 report_v2.py >> logs/daily.log 2>&1
```

### Option 2: Clawdbot Heartbeat
For Clawdbot users, add to `HEARTBEAT.md`:

```markdown
## Kalshi Market Scan
- Every day at 9 AM
- Execute: `cd ~/kalshi-trading && python3 report_v2.py`
- Report BUY recommendations (score ≥70)
```

---

## 📂 Project Structure

```
kalshi-trading/
├── README.md             # This file
├── README_CN.md          # Chinese documentation
├── SKILL.md              # Agent instructions (Clawdbot format)
├── report_v2.py          # Main scanner + decision engine
├── decision.py           # Single market analysis
├── paper_trading.py      # Trade tracker
├── trades.json           # Paper trading database
├── research.py           # Deep research tool
├── scripts/
│   ├── install.sh        # Automated installation
│   └── daily_scan.sh     # Automation wrapper
├── examples/
│   └── cron-setup.md     # Automation examples
└── reports/              # Historical scan reports
```

---

## 📈 Paper Trading Results

**Current Status** (as of 2026-02-01):
- **Total Trades**: 6
- **Pending**: 6
- **Win Rate**: TBD (waiting for settlements)

**Settlement Schedule:**
- **Feb 11, 2026** — CPI markets (2 trades)
- **Feb 20, 2026** — GDP markets (4 trades)

**Validation Goal:** >70% accuracy over 20+ trades before considering real capital.

---

## 🧪 Example Recommendations

### Trade #1 (Score: 100/100)
```yaml
Market: Will real GDP increase by more than 2.5% in Q4 2025?
Position: YES @ 89¢
Reasoning:
  - 251% annualized return (18 days to settlement)
  - BEA official data source
  - 5 recent news articles
  - No procedural risk
  - Tight spread (1¢)
Status: PENDING (settles Feb 20)
```

### Trade #2 (Score: 100/100)
```yaml
Market: Will CPI increase by more than 0.0% in January 2026?
Position: YES @ 95¢
Reasoning:
  - 213% annualized return (9 days)
  - BLS official data source
  - 4 recent news articles
  - Historical precedent (only 2 negative months since 2009)
Status: PENDING (settles Feb 11)
```

---

## 🔧 Configuration

### API Access
No API key required for scanning (uses public Kalshi API).

For future real trading integration:
```bash
export KALSHI_API_KEY=your_key_here
```

### Customization
Edit scoring weights in `decision.py`:
```python
YIELD_WEIGHT = 10
SPREAD_THRESHOLD = 0.03
DATA_SOURCE_BONUS = 30
NEWS_THRESHOLD = 3
```

---

## 🚨 Troubleshooting

### No BUY Recommendations?
**This is normal.** Most extreme-price markets fail validation:
- No official data source
- Ambiguous rules
- No recent news

The system correctly rejects risky bets. Review SKIP reasons in the report.

### Markets Already Expired?
Check `close_time` (trading deadline), not `expected_expiration_time` (data release date).

Kalshi has 3 time fields:
- `expected_expiration_time` — When data is expected to be released
- **`close_time`** — Trading deadline ← **Use this!**
- `latest_expiration_time` — Latest possible settlement date

### News Search Fails?
Google News RSS may rate-limit requests. Solutions:
- Add delays between requests
- Reduce scan frequency
- Cache news results

---

## 🗺️ Roadmap

- [ ] Integrate deeper research (`research.py`)
- [ ] Cross-market arbitrage detection
- [ ] Historical accuracy dashboard
- [ ] Position sizing / Kelly criterion
- [ ] Real Kalshi API trading integration
- [ ] Sentiment analysis from news content
- [ ] Market correlation analysis

---

## 🤝 Contributing

Contributions welcome! Areas of interest:
- Improve data source detection algorithms
- Add more news sources (Twitter, Reddit, etc.)
- Better natural language rule parsing
- Risk management strategies
- Backtesting framework

---

## 📜 License

MIT License - see [LICENSE](LICENSE) for details

---

## 🙏 Credits

Built by **Jason Zuo** (@jzOcb) + AI Assistant

Inspired by the legendary "$50 → $248K overnight" prediction market story.

---

## ⚠️ Disclaimer

**This is not financial advice.** This project is for educational purposes only. Prediction markets involve substantial risk. Always conduct your own research and never risk more than you can afford to lose. Past performance does not guarantee future results.

Paper trading first. Real money later. And only after validation.

---

**Questions?** Open an issue on [GitHub](https://github.com/jzOcb/kalshi-trading/issues)
