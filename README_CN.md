# Kalshi Trading System

🤖 AI驱动的预测市场扫描系统 | 决策引擎 + Paper Trading

## 功能介绍

自动扫描 500+ Kalshi 政治/经济市场，基于以下标准识别高确定性机会：
- ✅ 官方数据源（BEA, BLS, 美联储）
- ✅ 新闻验证（Google News）
- ✅ 规则分析（无歧义、无程序性风险）
- ✅ 风险/收益评分（0-100分系统）

**这不是赌博** — 每个推荐都基于客观数据，并通过 paper trading 验证后才考虑真实资金。

## 安装

### 方法 1: 从 GitHub 安装
```bash
git clone https://github.com/jzOcb/kalshi-trading.git
cd kalshi-trading

# 安装依赖
pip3 install requests beautifulsoup4 lxml

# 首次扫描
python3 report_v2.py
```

### 方法 2: 一键安装脚本
```bash
cd kalshi-trading
chmod +x scripts/install.sh
./scripts/install.sh
```

## 快速开始

### 运行每日扫描
```bash
python3 report_v2.py
```

### 查看结果
```bash
# 查看今日推荐
cat reports/report-$(date +%Y-%m-%d).txt

# 检查 paper trading 状态
python3 paper_trading.py summary
```

## 工作原理

### 1. 市场扫描
从 Kalshi API 获取所有开放市场，筛选极端价格市场（≥85¢ 或 ≤12¢）— "垃圾债券"策略，高潜在回报。

### 2. 规则分析
- 通过 API 获取完整市场规则
- 检测官方数据源（BEA GDP、BLS CPI、美联储等）
- 标记程序性风险（需要国会批准、主观判断等）
- 识别歧义语言

### 3. 新闻验证
- 从市场标题提取关键词
- 搜索 Google News RSS
- 要求 3+ 篇近期新闻文章才加分（+20分）

### 4. 评分与决策

**评分公式:**
```
基础分 = 年化收益 × 10
+ 10 (如果 spread ≤3¢，流动性好)
+ 30 (如果有官方数据源)
+ 20 (如果无程序性风险)
+ 20 (如果有3+篇新闻)
- 10 (如果规则歧义)
```

**决策阈值:**
- **≥70** → 🟢 **BUY** (高信心)
- **50-69** → 🟡 **WAIT** (需要验证)
- **<50** → 🔴 **SKIP** (太冒险)

### 5. Paper Trading
所有 BUY 推荐自动记录到 `trades.json`。在投入真实资金前先验证准确性。

## 使用示例

### 每日扫描
```bash
python3 report_v2.py
```

**输出示例:**
```
🟢 BUY #1 (评分: 100/100)
Q4 2025年实际GDP增长是否超过2.5%?
YES @ 89¢ → 251% 年化收益 (18天)
✅ BEA 数据源 | ✅ 5 条新闻 | $200 仓位
```

### 分析特定市场
```bash
python3 decision.py KXGDP-26JAN30-T2.5
```

### 更新 Paper Trading
```bash
# 标记交易结果
python3 paper_trading.py update 1 WIN 100

# 查看所有待结算交易
python3 paper_trading.py list

# 查看整体表现
python3 paper_trading.py summary
```

## 自动化设置

### 方案 1: Cron（推荐）
每日定时扫描：

```bash
# 添加到 crontab
0 9 * * * cd ~/kalshi-trading && python3 report_v2.py >> logs/daily.log 2>&1
```

### 方案 2: Clawdbot Heartbeat
如果使用 Clawdbot，添加到 `HEARTBEAT.md`:

```markdown
## Kalshi 市场扫描
- 每天早上9点执行
- 命令: `cd ~/kalshi-trading && python3 report_v2.py`
- 有 BUY 推荐（评分≥70）时通知
```

## 项目结构

```
kalshi-trading/
├── README.md             # 英文文档
├── README_CN.md          # 本文档（中文）
├── SKILL.md              # Agent 指令（Clawdbot 格式）
├── report_v2.py          # 主扫描引擎 + 决策引擎
├── decision.py           # 单市场分析
├── paper_trading.py      # 交易追踪器
├── trades.json           # Paper trading 数据库
├── research.py           # 深度研究工具
├── scripts/
│   ├── install.sh        # 安装脚本
│   └── daily_scan.sh     # 自动化包装器
├── examples/
│   └── cron-setup.md     # Cron 配置示例
└── reports/              # 历史扫描报告
```

## Paper Trading 结果

**当前状态** (截至 2026-02-01):
- **总交易数**: 6
- **待结算**: 6
- **胜率**: 待定（等待结算）

**结算时间表:**
- **2026年2月11日** — CPI 市场（2笔交易）
- **2026年2月20日** — GDP 市场（4笔交易）

**验证目标:** 20+ 笔交易后胜率 >70% 才考虑真实资金。

## 示例推荐

### 交易 #1 (评分: 100/100)
```yaml
市场: Q4 2025年实际GDP增长是否超过2.5%?
仓位: YES @ 89¢
推理:
  - 年化回报 251%（18天到期）
  - BEA 官方数据源
  - 5篇近期新闻
  - 无程序性风险
  - 窄价差（1¢）
状态: 待结算（2月20日）
```

### 交易 #2 (评分: 100/100)
```yaml
市场: 2026年1月CPI是否增长超过0.0%?
仓位: YES @ 95¢
推理:
  - 年化回报 213%（9天）
  - BLS 官方数据源
  - 4篇近期新闻
  - 历史先例（2009年以来仅2次负增长）
状态: 待结算（2月11日）
```

## 配置

### API 访问
扫描不需要 API key（使用公开 Kalshi API）。

未来真实交易集成:
```bash
export KALSHI_API_KEY=your_key_here
```

### 自定义
编辑 `decision.py` 中的评分权重:
```python
YIELD_WEIGHT = 10
SPREAD_THRESHOLD = 0.03
DATA_SOURCE_BONUS = 30
NEWS_THRESHOLD = 3
```

## 故障排除

### 没有 BUY 推荐？
**这是正常的。** 大多数极端价格市场无法通过验证：
- 无官方数据源
- 规则歧义
- 无近期新闻

系统正确拒绝了风险赌注。查看报告中的 SKIP 原因。

### 市场已过期？
检查 `close_time`（交易截止时间），不是 `expected_expiration_time`（数据发布日期）。

Kalshi 有3个时间字段：
- `expected_expiration_time` — 预期数据发布时间
- **`close_time`** — 交易截止时间 ← **用这个！**
- `latest_expiration_time` — 最晚结算日期

### 新闻搜索失败？
Google News RSS 可能有速率限制。解决方案：
- 增加请求间隔
- 降低扫描频率
- 缓存新闻结果

## 路线图

- [ ] 整合深度研究（`research.py`）
- [ ] 跨市场套利检测
- [ ] 历史准确率仪表板
- [ ] 仓位管理 / Kelly 准则
- [ ] 真实 Kalshi API 交易集成
- [ ] 新闻内容情感分析
- [ ] 市场相关性分析

## 贡献

欢迎 PR！感兴趣的领域：
- 改进数据源检测算法
- 添加更多新闻源（Twitter、Reddit 等）
- 更好的自然语言规则解析
- 风险管理策略
- 回测框架

## 许可证

MIT License

## 致谢

由 **Jason Zuo** (@jzOcb) + AI Assistant 开发

灵感来自传奇的 "$50 → $248K 一夜暴富" 预测市场故事。

## 免责声明

**这不是财务建议。** 本项目仅供教育目的。预测市场有重大风险。请务必自行研究，切勿投入超过承受能力的资金。过往表现不代表未来结果。

先 Paper trading，后真金白银。而且只在验证后。

---

**问题？** 在 [GitHub](https://github.com/jzOcb/kalshi-trading/issues) 提 issue
