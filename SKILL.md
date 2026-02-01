---
name: kalshi-trading
description: AI-powered prediction market trading system with decision engine and paper trading validation.
homepage: https://github.com/yourusername/kalshi-trading
metadata:
  clawdbot:
    emoji: "💰"
    requires:
      bins: ["python3", "curl"]
---

# Kalshi Trading System

AI驱动的预测市场决策引擎 + Paper Trading验证系统。

自动扫描Kalshi政治/经济市场，基于官方数据源、新闻验证和规则分析做出BUY/WAIT/SKIP决策。

## Quick Start

### Run Daily Scan
```bash
cd ~/clawd/kalshi
python3 report_v2.py
```

### Check Paper Trading Status
```bash
python3 paper_trading.py
```

### View Trades
```bash
cat trades.json | python3 -m json.tool
```

## Core Commands

### 1. Market Scanning
扫描所有政治/经济市场，找出高确定性机会（Junk Bonds）：

```bash
python3 report_v2.py
```

输出：
- 🟢 BUY推荐（评分≥70）：有官方数据源、新闻验证、规则明确
- 🟡 WAIT候选（50-69分）：需要更多验证
- 报告保存到 `reports/report-YYYY-MM-DD.txt`

### 2. Deep Market Analysis
单个市场深入分析（需要时手动调用）：

```bash
python3 decision.py KXGDP-26JAN30-T2.5
```

### 3. Paper Trading Management

记录新推荐：
```bash
python3 paper_trading.py record <ticker> <title> <BUY> <side> <price> <position> <score> <reasons> <expiration> <url>
```

更新结算结果：
```bash
python3 paper_trading.py update <trade_id> <WIN|LOSS> <settled_price>
```

查看统计：
```bash
python3 paper_trading.py summary
```

## Decision Criteria

### Scoring System (0-100分)
- 年化收益每100%: +10分
- Spread ≤3¢: +10分，≤5¢: +5分
- 官方数据源(BEA/BLS/Fed): +30分
- 无程序性风险: +20分
- 3+条相关新闻: +20分
- 规则模糊: -10分

### Decision Thresholds
- **≥70分 → BUY** (高信心推荐)
- **50-69分 → WAIT** (需要更多验证)
- **<50分 → SKIP** (拒绝)

### Core Principles
- 没有新闻验证 = 赌博
- 没有官方数据源 = 太主观
- 规则模糊 = 拒绝
- Edge小(<5%) = 不值得

## Automation

### Daily Scan via Cron

Add to cron (runs every morning at 9 AM):
```bash
clawdbot cron add \
  --name "Kalshi daily scan" \
  --cron "0 9 * * *" \
  --session isolated \
  --message "cd ~/clawd/kalshi && python3 report_v2.py && python3 paper_trading.py summary" \
  --channel telegram \
  --deliver
```

Or via heartbeat (add to HEARTBEAT.md):
```markdown
## Kalshi Daily Scan
- 每天早上跑一次（查 heartbeat-state.json 的 lastChecks.kalshi_daily_scan）
- 执行: `cd ~/clawd/kalshi && python3 report_v2.py`
- 如果有🟢 BUY推荐（评分≥70） → 简短汇报
```

## Files Overview

- `report_v2.py` - Main scan + decision engine
- `decision.py` - Single market analysis
- `paper_trading.py` - Trade tracking tool
- `trades.json` - Trade database
- `research.py` - Deep research (news, data sources)
- `README.md` - Full documentation

## Usage Examples

### Example 1: Daily Morning Scan
```bash
# In your morning routine (via cron or heartbeat)
cd ~/clawd/kalshi && python3 report_v2.py

# Agent will:
# 1. Scan 500+ markets
# 2. Find extreme-price candidates
# 3. Fetch rules + news for each
# 4. Score and decide (BUY/WAIT/SKIP)
# 5. Auto-record BUY recommendations to paper trading
```

### Example 2: Manual Research
```bash
# Deep dive into a specific market
python3 decision.py KXCPI-26FEB-T0.0

# Output:
# - Full rules analysis
# - Data source identification
# - Procedural risk assessment
# - News validation
# - BUY/WAIT/SKIP decision with reasoning
```

### Example 3: Settlement Day
```bash
# Feb 11: CPI data released, market settled
python3 paper_trading.py update 1 WIN 100

# Update trade #1 as WIN (settled at 100¢)
# System calculates P&L and updates stats
```

## Kalshi Market Timing

Markets have 3 time fields:
- `expected_expiration_time`: Data expected release date
- `close_time`: **Trading deadline** ← Use this for "days remaining"
- `latest_expiration_time`: Latest settlement date

**Always use close_time to calculate trading window!**

## Safety & Validation

This is **paper trading** — validation phase before real money.

Goals:
1. Test if scoring system is reasonable
2. Verify data source detection accuracy
3. Validate news verification effectiveness
4. Build historical track record

Only consider real trading after:
- ✅ Accuracy rate >70%
- ✅ Consistent profitability over 20+ trades
- ✅ Understanding of edge cases and failure modes

## Troubleshooting

### "No BUY recommendations"
- Normal! Most high-yield markets fail verification (no data source, ambiguous rules)
- The system correctly rejects risky bets
- Check WAIT/SKIP reasons to understand why

### "Market already expired"
- Check `close_time` not `expected_expiration_time`
- Data release delays are common

### "News validation fails"
- Google News might rate-limit
- News search extracts keywords from title - check if title is too generic

## Next Steps

After validating with paper trading:
1. Integrate research.py for deeper analysis
2. Add cross-market arbitrage detection
3. Build historical accuracy tracker
4. Implement position sizing / risk management
5. Connect to Kalshi API for real trading

---

**Created**: 2026-02-01  
**Status**: ✅ Paper Trading Validation Phase  
**Author**: JZ + AI Assistant
