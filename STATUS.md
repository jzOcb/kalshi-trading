# STATUS.md — Kalshi Trading System
Last updated: 2026-02-01T23:10Z

## 当前状态: 完成 - 准备发布

## 最后做了什么
重构为ClawdHub skill格式，准备分享给社区：
- 创建SKILL.md（agent使用说明）
- 创建README_CLAWDHUB.md（人类文档）
- 创建scripts/install.sh（一键安装）
- 创建examples/cron-setup.md（完整cron配置示例）

## Blockers
无

## 下一步
1. 创建GitHub repo并推送
2. 测试install.sh脚本
3. 发布到ClawdHub
4. 写发布公告

## 技术架构

### 核心文件
- `report_v2.py` - 主扫描引擎（扫描554市场→规则分析→新闻验证→评分决策）
- `decision.py` - 单市场深入分析
- `paper_trading.py` - 交易追踪系统
- `trades.json` - 交易数据库（6笔pending）

### 决策引擎评分系统（0-100分）
- 年化收益/100%: +10分
- Spread≤3¢: +10分
- 官方数据源(BEA/BLS/Fed): +30分
- 无程序性风险: +20分
- 3+条新闻: +20分
- 规则模糊: -10分

**决策门槛:**
- ≥70 → BUY
- 50-69 → WAIT
- <50 → SKIP

### Bug修复记录
1. ✅ BLS/BEA数据源隐式识别（CPI→BLS, GDP→BEA）
2. ✅ 新闻搜索URL编码
3. ✅ _Response.text属性（urllib fallback）
4. ✅ 时间字段混淆（expected_expiration vs close_time）

## Paper Trading状态

**总计:** 6笔推荐  
**待结算:** 6笔  
**投入:** $1,200（模拟）

**Top 3推荐:**
1. GDP > 5% Q4 2025 → NO@88¢ (100分, 277%年化, Feb 20结算)
2. GDP > 2.5% Q4 2025 → YES@89¢ (100分, 251%年化, Feb 20结算)
3. CPI > 0.0% Jan 2026 → YES@95¢ (100分, 213%年化, Feb 11结算)

**验证时间表:**
- 2月11日: 2个CPI市场结算
- 2月20日: 4个GDP市场结算

## 调度方案

支持两种方式（用户选择）：

**方式1: Cron（推荐用于分享）**
```bash
clawdbot cron add --name "Kalshi scan" \
  --cron "0 9 * * *" --session isolated \
  --message "cd ~/clawd/kalshi && python3 report_v2.py" \
  --channel telegram --deliver
```

**方式2: Heartbeat（集成到主session）**
在HEARTBEAT.md添加：
```
## Kalshi Daily Scan
- 每天9am: cd ~/clawd/kalshi && python3 report_v2.py
```

## ClawdHub发布准备

**文件清单:**
- [x] SKILL.md（ClawdHub标准格式）
- [x] README_CLAWDHUB.md（安装使用文档）
- [x] scripts/install.sh（一键安装）
- [x] examples/cron-setup.md（配置示例）
- [x] 所有核心py文件
- [x] trades.json模板

**待做:**
- [ ] 创建GitHub repo
- [ ] 测试install.sh
- [ ] 写LICENSE
- [ ] 写发布公告
- [ ] clawdhub publish

## 关键决策记录

**2026-02-01 23:08** - 选择方案2（ClawdHub skill）而非独立repo  
原因：标准化、一键安装、自动调度配置

**2026-02-01 22:53** - Heartbeat改为10分钟+Haiku  
原因：Haiku成本低（$0.25/1M tokens），10分钟频率提高responsiveness

**2026-02-01 20:00** - 决策引擎整合新闻验证  
原因：没有新闻验证=赌博，需要数据支撑

**2026-02-01 16:00** - 确定Paper Trading优先  
原因：先验证系统准确性，再考虑真实交易

## 已知问题

- [ ] 新闻搜索可能被rate limit（需要缓存）
- [ ] 完整报告只显示5个BUY，应该有7个（截断问题）
- [ ] 未整合research.py深度分析
- [ ] 缺少市场规则LLM推理（复杂情况需要Opus）

## 性能数据

**最近一次扫描（2026-02-01 21:58 UTC）:**
- 扫描市场: 554个
- 极端价格候选: 387个
- 获取详细规则: 387次API调用
- 新闻搜索: ~387次
- 总耗时: ~3分钟
- 找到机会: 9个（7 BUY, 1 WAIT, 1 SKIP）

---

**项目状态:** ✅ 核心功能完成，准备社区发布  
**验证阶段:** Paper trading中，等待2月11日/20日结算结果  
**下一里程碑:** ClawdHub发布
