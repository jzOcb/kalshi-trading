#!/usr/bin/env python3
"""
Kalshi 统一扫描器

两层扫描策略：
1. Events 层 - 获取所有 open events，按 category 过滤
2. Markets 层 - 获取每个 event 的市场，检测 tier

不依赖硬编码 series 列表，自动发现新市场。

Author: OpenClaw
Date: 2026-02-20
"""

import os
import sys
import json
import requests
import time
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from source_detector import detect_sources

API_BASE = "https://api.elections.kalshi.com/trade-api/v2"
DATA_DIR = Path(__file__).parent / "data"

# 关注的类别 (排除 Sports, Entertainment, Esports)
TARGET_CATEGORIES = {"Economics", "Politics", "Financials", "Elections", "World", "Companies"}

# 排除的 series 前缀 (有独立系统处理)
EXCLUDE_PREFIXES = {"KXHIGH", "KXLOW"}  # 天气市场


class UnifiedScanner:
    """统一扫描器"""
    
    def __init__(self, min_volume: int = 100, max_days: int = 90, min_tier: int = 3):
        self.min_volume = min_volume
        self.max_days = max_days
        self.min_tier = min_tier  # 最高接受的 tier (1=最好, 9=最差)
        self.now = datetime.now(timezone.utc)
    
    def fetch_all_events(self) -> list:
        """获取所有 open events"""
        events = []
        cursor = None
        
        for _ in range(50):  # 最多 5000 个 events
            params = {"limit": 100, "status": "open"}
            if cursor:
                params["cursor"] = cursor
            
            try:
                resp = requests.get(f"{API_BASE}/events", params=params, timeout=15)
                if resp.status_code == 429:
                    time.sleep(3)
                    continue
                if resp.status_code != 200:
                    break
                
                data = resp.json()
                events.extend(data.get("events", []))
                
                cursor = data.get("cursor")
                if not cursor:
                    break
                
                time.sleep(0.1)
            except Exception as e:
                print(f"Error fetching events: {e}")
                break
        
        return events
    
    def filter_events(self, events: list) -> list:
        """按类别过滤 events"""
        filtered = []
        for e in events:
            category = e.get("category", "")
            series = e.get("series_ticker") or e.get("event_ticker", "").split("-")[0]
            
            # 跳过非目标类别
            if category not in TARGET_CATEGORIES:
                continue
            
            # 跳过天气市场
            if any(series.startswith(prefix) for prefix in EXCLUDE_PREFIXES):
                continue
            
            filtered.append(e)
        
        return filtered
    
    def analyze_event(self, event: dict) -> dict | None:
        """分析单个 event，返回市场信息"""
        event_ticker = event.get("event_ticker", "")
        
        try:
            resp = requests.get(f"{API_BASE}/markets", params={
                "event_ticker": event_ticker,
                "status": "open",
                "limit": 10
            }, timeout=10)
            
            if resp.status_code != 200:
                return None
            
            markets = resp.json().get("markets", [])
            if not markets:
                return None
            
            # 汇总所有市场
            total_volume = sum(m.get("volume", 0) for m in markets)
            
            # 检查第一个市场的 tier
            m = markets[0]
            rules = m.get("rules_primary", "")
            title = m.get("title", "")
            
            result = detect_sources(rules, title)
            tier = result.get("research_tier", 9)
            sources = result.get("sources", [])
            
            # 计算到期天数
            close_time_str = m.get("close_time", "")
            try:
                close_time = datetime.fromisoformat(close_time_str.replace("Z", "+00:00"))
                days_left = (close_time - self.now).days
            except:
                days_left = 9999
            
            return {
                "event_ticker": event_ticker,
                "series": event.get("series_ticker") or event_ticker.split("-")[0],
                "category": event.get("category", ""),
                "title": event.get("title", "")[:60],
                "tier": tier,
                "sources": sources,
                "volume": total_volume,
                "days_left": days_left,
                "market_count": len(markets),
                "markets": [m.get("ticker") for m in markets[:5]],
            }
            
        except Exception as e:
            return None
    
    def scan(self, verbose: bool = True) -> dict:
        """执行完整扫描"""
        if verbose:
            print("📡 获取所有 Events...")
        
        events = self.fetch_all_events()
        if verbose:
            print(f"   共 {len(events)} 个 events")
        
        # 过滤
        filtered = self.filter_events(events)
        if verbose:
            print(f"   目标类别: {len(filtered)} 个 events")
        
        # 分析每个 event
        results = []
        for i, e in enumerate(filtered):
            info = self.analyze_event(e)
            if info:
                # 应用过滤条件
                if info["volume"] >= self.min_volume and \
                   info["days_left"] <= self.max_days and \
                   info["tier"] <= self.min_tier:
                    results.append(info)
            
            if verbose and i % 50 == 0 and i > 0:
                print(f"   已分析 {i}/{len(filtered)}...")
            
            time.sleep(0.08)
        
        # 按 tier 和 volume 排序
        results.sort(key=lambda x: (x["tier"], -x["volume"]))
        
        # 生成报告
        report = {
            "scan_time": self.now.isoformat(),
            "filters": {
                "min_volume": self.min_volume,
                "max_days": self.max_days,
                "min_tier": self.min_tier,
            },
            "total_events": len(events),
            "filtered_events": len(filtered),
            "matched_markets": len(results),
            "results": results,
        }
        
        return report
    
    def print_report(self, report: dict):
        """打印报告"""
        print("\n" + "=" * 70)
        print("📊 KALSHI 市场扫描报告")
        print("=" * 70)
        print(f"扫描时间: {report['scan_time'][:19]}")
        print(f"过滤条件: volume≥{report['filters']['min_volume']}, "
              f"days≤{report['filters']['max_days']}, tier≤{report['filters']['min_tier']}")
        print(f"总 Events: {report['total_events']} → 目标类别: {report['filtered_events']} → 匹配: {report['matched_markets']}")
        
        results = report["results"]
        
        # 分组显示
        tier_1_2 = [r for r in results if r["tier"] <= 2]
        tier_3 = [r for r in results if r["tier"] == 3]
        
        print(f"\n### ✅ Tier 1-2 可研究 ({len(tier_1_2)} 个)\n")
        for r in tier_1_2:
            print(f"  Tier {r['tier']} | {r['days_left']:>3}天 | vol={r['volume']:>7} | {r['series']}")
            print(f"       {r['title']}")
            print(f"       Sources: {r['sources']}, Markets: {r['market_count']}")
            print()
        
        if tier_3:
            print(f"\n### ⚠️ Tier 3 需判断 ({len(tier_3)} 个)\n")
            for r in tier_3[:5]:
                print(f"  {r['days_left']:>3}天 | vol={r['volume']:>7} | {r['series']}: {r['title'][:40]}")
        
        print("\n" + "=" * 70)
    
    def save_watchlist(self, report: dict, path: Path = None):
        """保存 watchlist"""
        path = path or (DATA_DIR / "watchlist_unified.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        
        watchlist = {
            "updated": report["scan_time"],
            "filters": report["filters"],
            "tier_1_2": [r for r in report["results"] if r["tier"] <= 2],
            "tier_3": [r for r in report["results"] if r["tier"] == 3],
        }
        
        with open(path, "w") as f:
            json.dump(watchlist, f, indent=2, ensure_ascii=False)
        
        print(f"💾 Watchlist 已保存: {path}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Kalshi 统一扫描器")
    parser.add_argument("--min-volume", type=int, default=100, help="最小 volume")
    parser.add_argument("--max-days", type=int, default=90, help="最大到期天数")
    parser.add_argument("--min-tier", type=int, default=3, help="最高接受的 tier")
    parser.add_argument("--save", action="store_true", help="保存 watchlist")
    
    args = parser.parse_args()
    
    scanner = UnifiedScanner(
        min_volume=args.min_volume,
        max_days=args.max_days,
        min_tier=args.min_tier
    )
    
    report = scanner.scan()
    scanner.print_report(report)
    
    if args.save:
        scanner.save_watchlist(report)


if __name__ == "__main__":
    main()
