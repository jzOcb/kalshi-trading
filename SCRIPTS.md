# Kalshi 脚本清单

> 每个脚本必须有标准文档。修改前先更新此文件。

## 核心流水线

| 脚本 | 功能 | 调用方式 | 状态 |
|------|------|----------|------|
| kalshi_pipeline.py | 完整分析流水线：筛选→研究→Nowcast→报告 | cron / 手动 | ✅ |
| market_census.py | 市场发现，生成 watchlist_series.json | 每周手动 | ✅ |
| market_researcher_v2.py | 深度研究，基于官方结算源的事实核查 | 被 pipeline 调用 | ✅ |
| nowcast_fetcher.py | 实时经济数据：GDPNow, CPI, FedWatch | 被 pipeline 调用 | ✅ |
| source_detector.py | 检测市场的官方数据源 | 被 pipeline 调用 | ✅ |
| position_calculator.py | Kelly Criterion 动态仓位计算 | 被 pipeline 调用 | ✅ |

## 报告系统

| 脚本 | 功能 | 调用方式 | 状态 |
|------|------|----------|------|
| report_v2.py | 快速扫描报告，hourly cron | cron | ✅ |
| smart_reporter.py | 智能报告：全量 2x/天，增量按需 | cron | ✅ |
| notify.py | Telegram 格式化输出 | 被其他脚本调用 | ✅ |

## 专项扫描器

| 脚本 | 功能 | 调用方式 | 状态 |
|------|------|----------|------|
| endgame_scanner.py | 临期策略扫描（到期前机会） | 手动 | ✅ |
| parity_scanner.py | 套利扫描（价格偏差） | 手动 | ✅ |
| cross_platform_monitor.py | Kalshi vs Polymarket 比价 | 手动 | ✅ |

## 仓位管理

| 脚本 | 功能 | 调用方式 | 状态 |
|------|------|----------|------|
| get_positions.py | 获取当前仓位 | 手动 / API | ✅ |
| position_monitor.py | 仓位监控和告警 | 待配置 cron | ⚠️ |
| sync_positions.py | 同步仓位数据 | 手动 | ⚠️ |
| portfolio_analysis.py | 组合分析和风险评估 | 手动 | ⚠️ |

## 回测和研究

| 脚本 | 功能 | 调用方式 | 状态 |
|------|------|----------|------|
| backtest_researcher.py | 策略回测 | 手动 | ⚠️ |
| settlement_checker.py | 结算检查（paper trading） | 手动 | ✅ |

## 模块注册

| 脚本 | 功能 |
|------|------|
| __init__.py | 模块注册表，定义公开 API |

---

## 文档标准

每个 .py 文件开头必须有：

```python
"""
脚本名 — 一句话描述

功能：
    - 功能点 1
    - 功能点 2

用法：
    python 脚本.py [参数]
    
依赖：
    - 依赖模块 1
"""
```

## 状态说明

- ✅ 完整可用
- ⚠️ 功能可用但需要完善
- ❌ 已废弃，待删除

---

*最后更新: 2026-02-21*
