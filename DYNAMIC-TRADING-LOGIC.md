# Dynamic Trading Logic - News-Verified Signals

## Core Principle
**Price moves alone don't tell the full story. Always verify WHY before acting.**

## Signal Types

### 1. TAKE PROFIT ✅
**Trigger:** Unrealized gain ≥30% OR ≥70% of max possible gain

**Logic:**
- No news check needed
- Lock in profit rather than wait for settlement
- Quick gains compound better than waiting

**Example:**
- Entry: 95¢ → Current: 98¢
- Profit: 60% of max (5¢ gain out of 5¢ possible)
- **Action:** SELL_ALL

---

### 2. STOP LOSS (News-Verified) ⚠️
**Trigger:** Unrealized loss ≥40%

**Logic - 3 Outcomes:**

**A) News CONFIRMS fundamental change → SELL**
- Fed changed policy
- Data release contradicts thesis
- Regulatory change affects outcome
- **Action:** SELL_ALL (cut losses)

**B) NO news found → BUY MORE (Contrarian)**
- Price dropped but no fundamental change
- Market overreaction / panic selling
- Opportunity to average down cheaper
- **Action:** BUY_MORE (double down on thesis)

**C) Uncertain → MANUAL REVIEW**
- Some news but unclear impact
- Can't verify credibility
- Mixed signals
- **Action:** MANUAL_REVIEW (human decides)

**Example:**
```
Entry: 95¢ → Current: 52¢ (43% loss)

News check:
✅ NO major news about CPI methodology
✅ NO Fed policy changes
✅ NO BLS announcement changes

Conclusion: Market noise, not fundamentals
→ BUY_MORE at 52¢ (average down)
```

---

### 3. ADD POSITION (News-Verified) 📈
**Trigger:** Price improved by ≥5¢ AND position < 2x original

**Logic:**

**A) NO adverse news → ADD**
- Thesis still valid
- Getting better price
- **Action:** BUY_MORE

**B) Adverse news found → WARNING**
- Don't average into losing thesis
- Something fundamentally changed
- **Action:** WARNING (don't add)

**Example:**
```
Entry: 95¢ → Current: 88¢ (7¢ improvement)

News check:
✅ Recent CPI came in at 0.2% (supports YES>0%)
✅ No methodology changes

Conclusion: Safe to add
→ BUY_MORE at 88¢
```

---

### 4. TRIM POSITION 📉
**Trigger:** Price worsened by ≥5¢ AND position > 50% original

**Logic:**
- Reduce exposure if deteriorating
- Lock in partial loss before it worsens
- Keep some position if thesis still valid

---

### 5. WARNING ⚠️
**Non-actionable alerts:**
- Wide spread (>10¢) - illiquid market
- Adverse news detected
- Uncertainty flags

---

## News Verification Process

### Data Sources Checked:
1. Market-specific news scanner
2. Keywords by market type:
   - **CPI:** inflation, consumer price, BLS
   - **GDP:** economic growth, BEA
   - **Fed:** interest rate, monetary policy
   - **Shutdown:** government funding, budget

### News Evaluation:
- **≥3 recent articles** → Confirmed news (justified move)
- **1-2 articles** → Uncertain (manual review)
- **0 articles** → No news (likely noise)

### Confidence Levels:
- **HIGH:** Clear news confirmation or clear absence
- **MEDIUM:** Some uncertainty, but lean one way
- **NEEDS_VERIFICATION:** Manual review required

---

## Workflow

```
1. Monitor runs every 2 hours
2. For each position:
   a. Fetch current price
   b. Calculate P&L
   c. Check signal thresholds
   
3. If STOP_LOSS threshold hit:
   → Run news check
   → Determine action based on news
   
4. If BUY_MORE opportunity:
   → Run news check
   → Verify no adverse news
   
5. Generate recommendations
6. DM Jason with signals
7. Jason reviews and executes
```

---

## Key Differences from Traditional Stop-Loss

**Traditional:**
```
Price drops 40% → Auto-sell
```

**Our Approach:**
```
Price drops 40% → Check news first
  ↓
News confirms? → Sell
No news? → BUY MORE (it's noise)
Uncertain? → Manual review
```

**Why Better:**
- Avoids panic selling on noise
- Captures contrarian opportunities
- Only exits on fundamental changes
- Higher win rate on junk bonds

---

## Position Limits (Risk Management) 🛡️

**Problem without limits:**
```
Great trade → Buy $200
Price drops, no news → Buy $200 more
Still good, add more → Buy $200 more
...
Result: $1000 in ONE ticker = concentration risk!
```

**Solution - 4 Layer Protection:**

### 1. Max Position Per Ticker
```python
MAX_POSITION_PER_TICKER = $500
```
- **Prevents:** Too much in one market
- **Example:** Can't have >$500 in KXCPI-26JAN-T0.0
- Even if it looks amazing, diversify!

### 2. Max Position Per Series
```python
MAX_POSITION_PER_SERIES = $1000
```
- **Prevents:** Too much in one topic
- **Example:** All CPI trades combined ≤ $1000
- Spreads risk across different data sources

### 3. Max Total Exposure
```python
MAX_TOTAL_EXPOSURE = $3000
```
- **Prevents:** Over-leveraging
- **Example:** Total capital at risk across ALL trades
- Keeps reserves for new opportunities

### 4. Max Single Add
```python
MAX_SINGLE_ADD = $200
```
- **Prevents:** One reckless buy
- **Example:** Can't add >$200 in one action
- Forces gradual position building

---

## How Limits Work

### Before BUY_MORE:
```python
1. Check news (is it safe to add?)
2. Check ticker limit (already have $400 of $500 max)
3. Check series limit (KXCPI at $900 of $1000 max)
4. Check total limit ($2800 of $3000 max)
5. Check single add ($100 < $200 max)

All pass? → BUY_MORE allowed
Any fail? → WARNING issued instead
```

### Example - Limit Blocks Buy:
```
Signal: BUY_MORE KXCPI-26JAN-T0.0 for $100

Checks:
✅ News: No adverse news
✅ Ticker: $200 current + $100 = $300 (< $500 max)
❌ Series: KXCPI at $950 + $100 = $1050 (> $1000 max)

Result: WARNING - Would exceed series limit
```

---

## Exposure Dashboard

Monitor shows real-time limits:
```
💰 EXPOSURE SUMMARY:
  Total: $1100 / $3000 (36.7%)

  By Series:
    KXCPI: $300 / $1000 (30.0%)  ← Room to add
    KXGDP: $800 / $1000 (80.0%)  ← Near limit!

  By Ticker:
    KXCPI-26JAN-T0.0: $200 / $500 (40.0%)
    KXGDP-26JAN30-T5: $200 / $500 (40.0%)
    ...
```

**Interpretation:**
- **<50% = Safe** - Plenty of room
- **50-80% = Caution** - Watch closely
- **>80% = Alert** - Near limit, diversify!

---

## Configuration

Current thresholds (adjustable):
```python
# Signal thresholds
TAKE_PROFIT_PCT = 30    # Exit at 30% profit
STOP_LOSS_PCT = 40      # Stop loss at 40% down (but news-verified)
ADD_THRESHOLD = 5       # Add if price improves 5¢
TRIM_THRESHOLD = 5      # Trim if price worsens 5¢

# Position limits
MAX_POSITION_PER_TICKER = 500    # Max $500 per ticker
MAX_POSITION_PER_SERIES = 1000   # Max $1000 per series
MAX_TOTAL_EXPOSURE = 3000        # Max $3000 total
MAX_SINGLE_ADD = 200             # Max $200 per buy
```

Adjust these in `dynamic_trader.py` based on:
- Your total capital
- Risk tolerance
- Market conditions

---

## Examples

### Scenario 1: CPI Market
```
Position: YES@95¢ on "CPI > 0%"
Current: 91¢ (4¢ drop, 4.2% loss)

Status: HOLD (below 40% threshold)
No action needed yet.
```

### Scenario 2: With News
```
Position: YES@95¢ on "CPI > 0%"
Current: 55¢ (40¢ drop, 42% loss)

News check:
→ BLS announced CPI -0.1% (deflation)
→ Multiple sources confirm

Signal: SELL_ALL - News confirms thesis wrong
```

### Scenario 3: Without News
```
Position: YES@95¢ on "CPI > 0%"
Current: 55¢ (40¢ drop, 42% loss)

News check:
→ No BLS announcement yet
→ No policy changes
→ No methodology updates

Signal: BUY_MORE - Market overreaction, thesis still valid
```

---

## Future Enhancements

1. **Auto-news integration** - API feeds for real-time alerts
2. **Sentiment analysis** - Gauge market mood from social
3. **Order book analysis** - Detect informed vs uninformed trades
4. **Correlation tracking** - Related markets moving together
5. **ML prediction** - Learn which signals work best

---

**Remember:** The goal is to trade on INFORMATION, not just PRICE.
