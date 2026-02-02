# Kalshi Trading System

🤖 AI-Powered Prediction Market Trading with Decision Engine + Paper Trading

## What It Does

Automatically scans 500+ Kalshi political/economic markets, identifies high-confidence opportunities based on:
- ✅ Official data sources (BEA, BLS, Fed)
- ✅ News verification (Google News)
- ✅ Rules analysis (no ambiguity, no procedural risks)
- ✅ Risk/reward scoring (0-100 scale)

**Not gambling** — data-driven decisions with paper trading validation.

## Installation

### 1. Via ClawdHub (Recommended)
```bash
clawdhub install kalshi-trading
```

### 2. Manual Installation
```bash
cd ~/clawd
git clone https://github.com/yourusername/kalshi-trading kalshi
cd kalshi
chmod +x scripts/install.sh
./scripts/install.sh
```

## Quick Start

### Run Daily Scan
```bash
cd ~/clawd/kalshi
python3 report_v2.py
```

### View Results
```bash
# See today's recommendations
cat reports/report-$(date +%Y-%m-%d).txt

# Check paper trading status
python3 paper_trading.py
```

## Automation Setup

### Option A: Cron (Isolated Sessions)
Best for scheduled scans with dedicated sessions:

```bash
clawdbot cron add \
  --name "Kalshi daily scan" \
  --cron "0 9 * * *" \
  --session isolated \
  --message "cd ~/clawd/kalshi && python3 report_v2.py" \
  --channel telegram \
  --deliver
```

### Option B: Heartbeat (Main Session)
Best for periodic checks in your main agent session:

Add to `~/clawd/HEARTBEAT.md`:
```markdown
## Kalshi Daily Scan
- 每天早上跑一次（查 heartbeat-state.json 的 lastChecks.kalshi_daily_scan）
- 执行: `cd ~/clawd/kalshi && python3 report_v2.py`
- 如果有🟢 BUY推荐（评分≥70） → 简短汇报
```

## How It Works

### 1. Market Scanning
- Fetches all open markets from Kalshi API
- Filters extreme prices (≥85¢ or ≤12¢ = "Junk Bonds")
- High potential return but need validation

### 2. Rules Analysis
- Fetches full market rules from API
- Identifies official data sources (BEA for GDP, BLS for CPI, etc.)
- Detects procedural risks (requires Congress approval, etc.)
- Flags ambiguous language

### 3. News Validation
- Extracts keywords from market title
- Searches Google News RSS
- Counts recent relevant articles
- +20 points for 3+ news articles

### 4. Scoring & Decision
**Scoring System:**
- Annual yield per 100%: +10 points
- Spread ≤3¢: +10 points (good liquidity)
- Official data source: +30 points
- No procedural risk: +20 points
- 3+ news articles: +20 points
- Ambiguous rules: -10 points

**Decision Thresholds:**
- ≥70 → 🟢 BUY (high confidence)
- 50-69 → 🟡 WAIT (needs more validation)
- <50 → 🔴 SKIP (too risky)

### 5. Paper Trading
- Auto-records all BUY recommendations to `trades.json`
- Tracks entry price, position size, reasoning
- Updates with WIN/LOSS when markets settle
- Calculates P&L and accuracy stats

## File Structure

```
kalshi/
├── SKILL.md              # Agent instructions (ClawdHub format)
├── README.md             # This file (human docs)
├── report_v2.py          # Main scan + decision engine
├── decision.py           # Single market analysis
├── paper_trading.py      # Trade tracker
├── trades.json           # Trade database
├── research.py           # Deep research tool
├── scripts/
│   ├── install.sh        # Installation script
│   └── daily_scan.sh     # Automation wrapper
├── examples/
│   └── cron-setup.md     # Cron configuration examples
└── reports/              # Historical scan reports
```

## Usage Examples

### Daily Workflow
```bash
# Morning: Run scan
python3 report_v2.py

# Review BUY recommendations
cat trades.json | python3 -m json.tool | grep -A10 "PENDING"

# Settlement day: Update results
python3 paper_trading.py update 1 WIN 100
python3 paper_trading.py summary
```

### Manual Deep Dive
```bash
# Analyze specific market
python3 decision.py KXGDP-26JAN30-T2.5

# Output:
# ============================================================
# 📊 Will real GDP increase by more than 2.5% in Q4 2025?
# 🎯 KXGDP-26JAN30-T2.5
# ============================================================
# 
# 决策: BUY (HIGH confidence)
# 评分: 100/100
# 推荐: YES @ 89¢
# 回报: +251% 年化 (18天)
# 仓位: $200
#
# 理由:
#   • 年化 251%
#   • 流动性好 (spread 1¢)
#   • ✅ BEA 数据源
#   • ✅ 无程序性风险
#   • ✅ 5 条相关新闻
```

## Configuration

No API key needed for scanning (uses public Kalshi API).

For real trading (future):
- Get API key from kalshi.com
- Export: `export KALSHI_API_KEY=your_key`

## Paper Trading Validation

**This is paper trading** — testing the system before real money.

Current status:
- **Total trades**: 6
- **Pending**: 6
- **Win rate**: TBD (waiting for settlements)

Settlement schedule:
- Feb 11: CPI markets
- Feb 20: GDP markets

Only move to real trading after:
- ✅ >70% accuracy over 20+ trades
- ✅ Consistent profitability
- ✅ Understanding failure modes

## Roadmap

- [ ] Integrate deeper research (research.py)
- [ ] Cross-market arbitrage detection
- [ ] Historical accuracy tracker
- [ ] Position sizing / risk management
- [ ] Kalshi API real trading integration
- [ ] Sentiment analysis from news content
- [ ] Market correlation analysis

## Troubleshooting

### No BUY recommendations?
**Normal!** Most extreme-price markets fail verification:
- No official data source
- Ambiguous rules
- No news validation

The system correctly rejects risky bets. Check SKIP reasons.

### Markets already expired?
Check `close_time` (trading deadline), not `expected_expiration_time` (data release).

Kalshi has 3 time fields:
- `expected_expiration_time`: When data is expected
- **`close_time`**: Trading deadline ← Use this!
- `latest_expiration_time`: Latest settlement

### News search fails?
Google News might rate-limit. Add delays or reduce scan frequency.

## Contributing

PRs welcome! Areas:
- Improve data source detection
- Add more news sources
- Better rule parsing
- Risk management strategies

## License

MIT

## Credits

Built by JZ + AI Assistant  
Inspired by the $50→$248K overnight story (X article)  
Paper trading first, real money later

---

**Disclaimer**: Not financial advice. This is an educational AI project. Prediction markets involve risk. Always do your own research.
