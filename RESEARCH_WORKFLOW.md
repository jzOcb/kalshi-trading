# Kalshi Market Research Workflow

## 核心原则

**这是预测市场，不是赌场。**

每一个推荐必须通过事实核查，不能靠数学公式猜测。

## 强制执行流程

```
市场 → 到期检查 → 提取官方源 → 获取数据 → 核查事实 → 判断 → 推荐
      ↓
      到期 >90天 → 直接 SKIP (资金时间成本)
      无法核查 → 直接 SKIP
```

### 时间过滤 (第一道门)

| 到期时间 | 处理 |
|----------|------|
| ≤30天 | ✅ 优先研究 |
| 31-90天 | 🟡 可以研究 |
| >90天 | 🔴 SKIP (年化回报太低) |

### Step 1: 提取官方结算源

从 `rules_primary` 提取 Kalshi 认可的数据源：

| 关键词 | 官方源 | URL |
|--------|--------|-----|
| AAA, gas | AAA | gasprices.aaa.com |
| BLS, U-3, unemployment | BLS | bls.gov |
| BEA, GDP | BEA | bea.gov |
| CPI, inflation | BLS CPI | bls.gov/cpi |
| Fed, FOMC | Federal Reserve | federalreserve.gov |
| NWS, weather | NWS | weather.gov |

### Step 2: 检查可验证性

**不可验证 → 直接 SKIP:**
- "Trump/Biden 将说什么"
- "X 将宣布什么"
- 任何未来发言/公告类

### Step 3: 获取数据

优先顺序：
1. 官方结算源 (AAA, BLS, BEA...)
2. 第三方验证源 (Trading Economics, GDPNow)

### Step 4: 对比阈值

```python
gap = current_value - threshold
gap_pct = gap / threshold * 100

if |gap_pct| < 3%:
    → SKIP (边界风险)
elif current supports YES:
    → 置信度 = 50 + |gap_pct| * 2 (max 90)
else:
    → 置信度 = 50 + |gap_pct| * 2 (max 90)
```

### Step 5: 输出判断

```
推荐 = BUY   if 置信度 >= 70 AND 有官方数据
推荐 = WAIT  if 置信度 >= 50
推荐 = SKIP  otherwise
```

## 使用方法

```bash
# 📊 完整市场报告 (推荐)
python3 ~/clawd/kalshi/generate_report.py

# 快速扫描
python3 ~/clawd/kalshi/scan_short_term.py

# 指定天数
python3 ~/clawd/kalshi/generate_report.py --days 90

# 单个市场深度研究
python3 -c "
from market_researcher_v2 import MarketResearcherV2
r = MarketResearcherV2()
report = r.research({'ticker': 'XXX', 'title': '...', 'rules_primary': '...'})
print(r.format_report(report))
"
```

## 工具架构

```
source_detector.py      # 共享检测模块 (正则+关键词)
       ↑
scan_short_term.py     # 快速扫描
generate_report.py     # 完整报告 (推荐)
       ↑
market_researcher_v2.py # 单市场深度研究
```

## 事件类市场 (Event-Driven) — 强制步骤

**适用于**: Government shutdown, 选举, 政策, 任何非数据发布类市场

### ⚠️ 必须先回答这些问题

```
1. 事件是什么类型？
   - 全面 vs 部分影响？
   - 哪些部门/人群受影响？

2. 开始日期是什么？
   - 从官方源确认 (Wikipedia, 政府公告)
   - 不要从 Kalshi ticker 推断

3. 当前状态？
   - 已经进行多少天？
   - 有没有谈判进展？

4. 触发原因是什么？
   - 具体争议点
   - 各方诉求
   - 解决条件

5. 历史先例适用吗？
   - 同类事件 vs 不同类
   - 部分 vs 全面
```

### 信息获取顺序 (不可跳过)

```
1. Kalshi rules_primary (结算规则)
2. Wikipedia 当前事件页面 (不是历史页面!)
3. 新闻确认日期和状态
4. 然后才看市场定价
```

### 红线 (直接 SKIP)

- 无法确认事件类型 → SKIP
- 日期来源不可靠 → SKIP
- 部分影响但用全面影响历史 → SKIP
- 触发原因不明 → SKIP

### Government Shutdown 教训 (2026-02-22)

| 错误 | 正确做法 |
|------|----------|
| 以为 Feb 7 开始 | 查 Wikipedia → Feb 14 |
| 以为全面 shutdown | 查新闻 → 仅 DHS |
| 用历史 35/43 天类比 | 部分 shutdown 动态不同 |
| 先给建议后查事实 | **必须先完成 5 个问题** |

---

## 历史教训

### Government Shutdown 误判 - 2026-02-22

- 以为全面 shutdown，实际只影响 DHS
- 日期算错 (以为 15 天，实际 8-9 天)
- 没查触发原因 (CBP 事件)
- **教训**: 事件类市场必须先查背景，不能只看数字

### GDP 亏损 ($179) - 2026-02-20

- GDPNow 预测 4.2%，实际 1.4%
- 误差 2.8pp，所有 YES 持仓爆仓
- **教训**: Nowcast ≠ 事实，必须等实际数据

### 规则

1. 经济指标市场：等官方数据发布后再下单
2. 高价入场 (>85¢)：自动降低置信度
3. 边界风险 (<3% 差距)：直接 SKIP

## 文件结构

```
~/clawd/kalshi/
├── RESEARCH_WORKFLOW.md          # 本文件 (流程文档)
├── market_researcher_v2.py       # 核心框架
├── deep_research_report_v2.py    # 报告入口
├── llm_source_identifier.py      # LLM 数据源识别
└── backtest_researcher.py        # 历史回测验证
```

## Kalshi URL 格式

**正确格式** (可点击打开):
```
https://kalshi.com/markets/{series}/{slug}/{event_ticker}
```

**例子**:
- CPI: `https://kalshi.com/markets/kxcpi/cpi/kxcpi-26feb`
- GDP: `https://kalshi.com/markets/kxgdp/us-gdp-growth/kxgdp-26apr30`
- Jobs: `https://kalshi.com/markets/kxpayrolls/jobs-numbers/kxpayrolls-26feb`
- Fed Decision: `https://kalshi.com/markets/kxfeddecision/fed-meeting/kxfeddecision-26mar`

**Slug 映射** (API 不返回，需要查表):

| Series | Slug |
|--------|------|
| KXCPI | cpi |
| KXCPICORE | cpi-core |
| KXCPIYOY | inflation |
| KXGDP | us-gdp-growth |
| KXPAYROLLS | jobs-numbers |
| KXFEDDECISION | fed-meeting |
| KXFED | fed-funds-rate |
| KXU3 | unemployment |
| KXFEDMENTION | fed-mention |
| KXHIGH | high-temperature |
| KXLOW | low-temperature |

**代码**: `~/clawd/kalshi/url_mapping.py`

**Fallback**: 如果 series 不在映射表里，用 search:
```
https://kalshi.com/search?query={ticker}
```

---

**最后更新**: 2026-02-22
**维护者**: OpenClaw
