# Kalshi Scanner Architecture

## 核心架构 (2026-02-21)

```
market_census.py ──[每周]──> data/watchlist_series.json
                                     │
                                     ▼
kalshi_pipeline.py ──[主流水线]──> 筛选 → 深度研究 → 报告
        ↑                                    │
        │                                    ▼
report_v2.py ──[hourly cron]──────────> 快速扫描报告
        ↑
        │
smart_reporter.py ──[调度]──> FULL(9AM/6PM) / DELTA / SKIP
```

**关键脚本 (26个)**:
- `market_census.py` - 每周全量发现 series
- `kalshi_pipeline.py` - 完整流水线 (筛选+深度研究+Nowcast)
- `report_v2.py` - 快速扫描 (被 cron 调用)
- `smart_reporter.py` - 智能调度
- `source_detector.py` - 数据源检测
- `market_researcher_v2.py` - 深度研究器
- `nowcast_fetcher.py` - 获取 Nowcast 数据

**备份文件** (已移至 backup/):
- generate_report.py - 被 kalshi_pipeline 取代
- deep_research_report_v2.py - 被 kalshi_pipeline 取代

---

## 问题根源

Kalshi API 特性：
1. `events` API 不按 volume 排序，高 volume 市场可能在第 1000+ 位
2. `markets` API 返回电竞市场优先（最活跃）
3. `series_ticker` 参数可以精确查询，但需要知道 series 名称

## 两层扫描策略

### Layer 1: 已知 Series 快速扫描 (每日, ≤60天)

```
KNOWN_SERIES = [
    # 经济
    "KXGDP", "KXCPI", "KXPCE", "KXFED", "KXFOMC", "KXJOBLESS",
    # 政治
    "KXEOWEEK", "KXEO", "KXEOTRUMP", "KXSHUTDOWN", "KXDEBT",
    # 其他
    "KXAAGAS", "KXGASMAX",
]
```

对每个 series 调用:
```
GET /markets?series_ticker={series}&status=open
```

优点：快速（~20 API calls）
缺点：只能发现已知 series

### Layer 2: 全量 Events 发现 (每周)

遍历所有 events，提取新的 series 前缀：
```
GET /events?limit=100&cursor={cursor}
```

对每个 event 提取 `event_ticker.split("-")[0]` 作为 series 候选。

如果发现新的 series 且有 volume，加入 KNOWN_SERIES。

优点：自动发现新市场
缺点：慢（~50 API calls，2-3 分钟）

## 数据流

```
┌─────────────────┐
│  Layer 2 Weekly │ ──发现新 series──┐
│  (Full Crawl)   │                   │
└─────────────────┘                   ▼
                              ┌──────────────┐
                              │ KNOWN_SERIES │ ← 手动维护 + 自动发现
                              │   (config)   │
                              └──────────────┘
                                      │
                                      ▼
                              ┌─────────────────┐
                              │  Layer 1 Daily  │
                              │ (Quick Scan)    │
                              └─────────────────┘
                                      │
                                      ▼
                              ┌─────────────────┐
                              │   watchlist     │
                              │ (actionable)    │
                              └─────────────────┘
```

## 实现文件

- `known_series.json` - 已知 series 列表 (手动 + 自动更新)
- `quick_scan.py` - Layer 1 快速扫描
- `discovery_crawl.py` - Layer 2 全量发现
- `watchlist_unified.json` - 输出结果

## 关键规则

1. **新 series 自动加入**: 发现 volume > 1000 的新 series 时，自动追加到 known_series.json
2. **死 series 自动移除**: 连续 30 天无活跃市场的 series 移至 inactive
3. **手动 override**: 可以手动添加/排除 series
