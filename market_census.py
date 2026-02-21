#!/usr/bin/env python3
"""
Kalshi 市场普查工具

全面扫描所有市场，分类并生成 watchlist。
每周/双周运行一次更新。

用法:
    python3 market_census.py              # 完整扫描
    python3 market_census.py --summary    # 只看摘要
    python3 market_census.py --update     # 更新现有 watchlist

Author: OpenClaw
Date: 2026-02-21
"""

import os
import sys
import json
import argparse
import requests
import time
import re
from datetime import datetime, timezone
from typing import List, Dict, Set
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from source_detector import detect_sources

API_BASE = "https://api.elections.kalshi.com/trade-api/v2"
DATA_DIR = Path(__file__).parent / "data"
CENSUS_FILE = DATA_DIR / "market_census.json"
WATCHLIST_FILE = DATA_DIR / "watchlist_series.json"


class MarketCensus:
    """Kalshi 市场普查"""
    
    def __init__(self):
        self.markets = []
        self.events = []
        self.series = defaultdict(lambda: {
            "markets": [],
            "category": "",
            "tier": 9,
            "sources": [],
            "total_volume": 0,
            "earliest_close": None,
            "latest_close": None,
        })
    
    def fetch_all_events(self) -> List[Dict]:
        """获取所有 events"""
        events = []
        cursor = None
        
        print("📡 获取 Events...")
        for page in range(100):
            try:
                params = {"limit": 100, "status": "open"}
                if cursor:
                    params["cursor"] = cursor
                
                resp = requests.get(f"{API_BASE}/events", params=params, timeout=15)
                if resp.status_code != 200:
                    print(f"   ⚠️ Events API error: {resp.status_code}")
                    break
                
                data = resp.json()
                batch = data.get("events", [])
                events.extend(batch)
                
                cursor = data.get("cursor")
                if not cursor or len(batch) < 100:
                    break
                
                print(f"   已获取 {len(events)} 个 events...")
                    
            except Exception as e:
                print(f"   ❌ Error: {e}")
                break
        
        print(f"   ✅ 共 {len(events)} 个 events")
        return events
    
    def fetch_all_markets(self) -> List[Dict]:
        """获取所有 markets（带限流处理）"""
        markets = []
        cursor = None
        
        print("📡 获取 Markets...")
        for page in range(200):  # 最多 20000 个市场
            try:
                params = {"limit": 100, "status": "open"}
                if cursor:
                    params["cursor"] = cursor
                
                resp = requests.get(f"{API_BASE}/markets", params=params, timeout=15)
                
                # 处理限流
                if resp.status_code == 429:
                    print(f"   ⚠️ 限流，等待 5 秒...")
                    time.sleep(5)
                    continue
                
                if resp.status_code != 200:
                    print(f"   ⚠️ Markets API error: {resp.status_code}")
                    break
                
                data = resp.json()
                batch = data.get("markets", [])
                markets.extend(batch)
                
                cursor = data.get("cursor")
                if not cursor or len(batch) < 100:
                    break
                
                if page % 10 == 0:
                    print(f"   已获取 {len(markets)} 个 markets...")
                
                # 限流保护
                time.sleep(0.2)
                    
            except Exception as e:
                print(f"   ❌ Error: {e}")
                break
        
        print(f"   ✅ 共 {len(markets)} 个 markets")
        return markets
    
    def extract_series(self, ticker: str, event_ticker: str = "") -> str:
        """从 ticker 或 event_ticker 提取 series"""
        # 优先用 event_ticker 的前缀
        if event_ticker:
            # KXMVESPORTSMULTIGAMEEXTENDED-S2026... -> KXMVESPORTSMULTIGAMEEXTENDED
            match = re.match(r'^([A-Z]+)', event_ticker)
            if match:
                return match.group(1)
        
        # 从 ticker 提取
        # KXGDP-26APR30-T4.0 -> KXGDP
        match = re.match(r'^([A-Z]+)', ticker)
        if match:
            return match.group(1)
        
        return ticker.split("-")[0] if "-" in ticker else ticker
    
    def analyze_markets(self, markets: List[Dict]):
        """分析所有市场，按 series 分组"""
        print("🔍 分析市场...")
        
        # 先获取 events 以获取 category
        event_categories = {}
        print("   获取 event 分类信息...")
        for page in range(10):
            try:
                resp = requests.get(f"{API_BASE}/events", params={
                    "limit": 100, "status": "open", "cursor": None
                }, timeout=15)
                if resp.status_code == 200:
                    for e in resp.json().get("events", []):
                        event_categories[e.get("event_ticker", "")] = e.get("category", "Unknown")
                time.sleep(0.2)
            except:
                break
        
        for m in markets:
            ticker = m.get("ticker", "")
            title = m.get("title", "")
            rules = m.get("rules_primary", "")
            event_ticker = m.get("event_ticker", "")
            series_ticker = self.extract_series(ticker, event_ticker)
            category = event_categories.get(event_ticker, m.get("category", "Unknown") or "Unknown")
            volume = m.get("volume_24h", 0) or m.get("volume", 0) or 0
            close_time = m.get("close_time", "")
            
            # 检测 tier
            result = detect_sources(rules, title)
            tier = result.get("research_tier", 9)
            sources = result.get("sources", [])
            
            # 更新 series 信息
            s = self.series[series_ticker]
            s["markets"].append({
                "ticker": ticker,
                "title": title[:100],
                "volume": volume,
                "close_time": close_time,
                "tier": tier,
            })
            s["category"] = category
            s["total_volume"] += volume
            
            # 保留最好的 tier
            if tier < s["tier"]:
                s["tier"] = tier
                s["sources"] = sources
            
            # 更新到期时间范围
            if close_time:
                if not s["earliest_close"] or close_time < s["earliest_close"]:
                    s["earliest_close"] = close_time
                if not s["latest_close"] or close_time > s["latest_close"]:
                    s["latest_close"] = close_time
        
        print(f"   ✅ 分析完成，共 {len(self.series)} 个 series")
    
    def generate_report(self) -> Dict:
        """生成报告"""
        now = datetime.now(timezone.utc)
        
        report = {
            "generated_at": now.isoformat(),
            "total_markets": sum(len(s["markets"]) for s in self.series.values()),
            "total_series": len(self.series),
            "by_tier": defaultdict(list),
            "by_category": defaultdict(list),
            "recommended_watchlist": [],
        }
        
        for series_ticker, s in self.series.items():
            tier = s["tier"]
            category = s["category"]
            
            # 计算到期天数
            days_to_earliest = None
            if s["earliest_close"]:
                try:
                    close_time = datetime.fromisoformat(s["earliest_close"].replace("Z", "+00:00"))
                    days_to_earliest = (close_time - now).days
                except:
                    pass
            
            series_info = {
                "series_ticker": series_ticker,
                "category": category,
                "tier": tier,
                "sources": s["sources"],
                "market_count": len(s["markets"]),
                "total_volume": s["total_volume"],
                "days_to_earliest": days_to_earliest,
                "earliest_close": s["earliest_close"],
            }
            
            report["by_tier"][f"tier_{tier}"].append(series_info)
            report["by_category"][category].append(series_info)
            
            # 推荐 watchlist: tier 1-2，有 volume
            if tier <= 2 and s["total_volume"] > 0:
                report["recommended_watchlist"].append(series_info)
        
        # 排序
        report["recommended_watchlist"].sort(key=lambda x: (-x["total_volume"]))
        
        return report
    
    def save_census(self, report: Dict):
        """保存普查结果"""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        
        # 保存完整报告
        with open(CENSUS_FILE, "w") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"💾 普查结果已保存: {CENSUS_FILE}")
        
        # 保存 watchlist
        watchlist = {
            "updated_at": report["generated_at"],
            "series": [s["series_ticker"] for s in report["recommended_watchlist"]],
            "details": report["recommended_watchlist"],
        }
        with open(WATCHLIST_FILE, "w") as f:
            json.dump(watchlist, f, indent=2, ensure_ascii=False)
        print(f"💾 Watchlist 已保存: {WATCHLIST_FILE}")
    
    def print_summary(self, report: Dict):
        """打印摘要"""
        print("\n" + "=" * 60)
        print("📊 KALSHI 市场普查报告")
        print("=" * 60)
        print(f"生成时间: {report['generated_at'][:19]}")
        print(f"总市场数: {report['total_markets']}")
        print(f"总 Series: {report['total_series']}")
        
        print("\n### 按 Tier 分布")
        for tier in sorted(report["by_tier"].keys()):
            count = len(report["by_tier"][tier])
            print(f"  {tier}: {count} 个 series")
        
        print("\n### 按类别分布 (Top 10)")
        sorted_cats = sorted(report["by_category"].items(), key=lambda x: -len(x[1]))
        for cat, series_list in sorted_cats[:10]:
            print(f"  {cat}: {len(series_list)} 个 series")
        
        print("\n### 推荐 Watchlist (Tier 1-2, 有交易量)")
        watchlist = report["recommended_watchlist"]
        if watchlist:
            print(f"共 {len(watchlist)} 个 series:\n")
            for s in watchlist[:20]:
                days = s.get("days_to_earliest")
                days_str = f"{days}天" if days else "?"
                print(f"  ✅ {s['series_ticker']:<25} | Tier {s['tier']} | {s['category']:<15} | vol={s['total_volume']:>6} | {days_str}")
                print(f"     Sources: {', '.join(s['sources']) if s['sources'] else '-'}")
        else:
            print("  (无)")
        
        print("\n" + "=" * 60)
    
    def fetch_events_by_category(self) -> Dict[str, List[Dict]]:
        """获取所有 events 并按 category 分类"""
        events_by_cat = defaultdict(list)
        cursor = None
        
        print("📡 获取所有 Events...")
        for page in range(50):
            try:
                params = {"limit": 100, "status": "open"}
                if cursor:
                    params["cursor"] = cursor
                
                resp = requests.get(f"{API_BASE}/events", params=params, timeout=15)
                
                if resp.status_code == 429:
                    time.sleep(5)
                    continue
                
                if resp.status_code != 200:
                    break
                
                data = resp.json()
                batch = data.get("events", [])
                
                for e in batch:
                    cat = e.get("category", "Unknown")
                    events_by_cat[cat].append(e)
                
                cursor = data.get("cursor")
                if not cursor or len(batch) < 100:
                    break
                
                time.sleep(0.2)
                
            except Exception as e:
                print(f"   ❌ Error: {e}")
                break
        
        total = sum(len(v) for v in events_by_cat.values())
        print(f"   ✅ 共 {total} 个 events")
        return dict(events_by_cat)
    
    def fetch_markets_for_events(self, events: List[Dict]) -> List[Dict]:
        """获取指定 events 的所有 markets"""
        markets = []
        
        for i, e in enumerate(events):
            try:
                event_ticker = e.get("event_ticker", "")
                if not event_ticker:
                    continue
                
                resp = requests.get(f"{API_BASE}/markets", params={
                    "event_ticker": event_ticker,
                    "status": "open",
                    "limit": 50
                }, timeout=15)
                
                if resp.status_code == 429:
                    time.sleep(5)
                    continue
                
                if resp.status_code == 200:
                    batch = resp.json().get("markets", [])
                    # 添加 category 信息
                    for m in batch:
                        m["_category"] = e.get("category", "Unknown")
                        m["_event_title"] = e.get("title", "")
                        m["_series_ticker"] = e.get("series_ticker", "")
                    markets.extend(batch)
                
                time.sleep(0.15)  # 限流
                
                if i % 50 == 0 and i > 0:
                    print(f"   已处理 {i}/{len(events)} 个 events, {len(markets)} 个 markets...")
                
            except Exception as ex:
                pass
        
        return markets
    
    def run(self, summary_only: bool = False):
        """运行完整普查"""
        if summary_only and CENSUS_FILE.exists():
            with open(CENSUS_FILE) as f:
                report = json.load(f)
            self.print_summary(report)
            return report
        
        # 1. 获取所有 events
        events_by_cat = self.fetch_events_by_category()
        
        print("\n📊 Events 分布:")
        for cat, evts in sorted(events_by_cat.items(), key=lambda x: -len(x[1])):
            print(f"   {cat}: {len(evts)}")
        
        # 2. 优先处理有意义的类别
        priority_categories = ["Economics", "Politics", "Financials", "Elections", "World"]
        other_categories = [c for c in events_by_cat.keys() if c not in priority_categories]
        
        all_events = []
        for cat in priority_categories:
            all_events.extend(events_by_cat.get(cat, []))
        # 其他类别也加入
        for cat in other_categories:
            all_events.extend(events_by_cat.get(cat, []))
        
        print(f"\n📡 获取 {len(all_events)} 个 events 的 markets...")
        self.markets = self.fetch_markets_for_events(all_events)
        print(f"   ✅ 共获取 {len(self.markets)} 个 markets")
        
        # 3. 分析
        self.analyze_markets_v2(self.markets)
        
        # 4. 生成报告
        report = self.generate_report()
        
        # 5. 保存
        self.save_census(report)
        
        # 6. 打印摘要
        self.print_summary(report)
        
        return report
    
    def analyze_markets_v2(self, markets: List[Dict]):
        """分析市场 V2 - 使用预置的 category 信息"""
        print("🔍 分析市场...")
        
        for m in markets:
            ticker = m.get("ticker", "")
            title = m.get("title", "")
            rules = m.get("rules_primary", "")
            series_ticker = m.get("_series_ticker") or self.extract_series(ticker, m.get("event_ticker", ""))
            category = m.get("_category", "Unknown")
            volume = m.get("volume_24h", 0) or m.get("volume", 0) or 0
            close_time = m.get("close_time", "")
            
            # 检测 tier
            result = detect_sources(rules, title)
            tier = result.get("research_tier", 9)
            sources = result.get("sources", [])
            
            # 更新 series 信息
            s = self.series[series_ticker]
            s["markets"].append({
                "ticker": ticker,
                "title": title[:100],
                "volume": volume,
                "close_time": close_time,
                "tier": tier,
            })
            s["category"] = category
            s["total_volume"] += volume
            
            # 保留最好的 tier
            if tier < s["tier"]:
                s["tier"] = tier
                s["sources"] = sources
            
            # 更新到期时间范围
            if close_time:
                if not s["earliest_close"] or close_time < s["earliest_close"]:
                    s["earliest_close"] = close_time
                if not s["latest_close"] or close_time > s["latest_close"]:
                    s["latest_close"] = close_time
        
        print(f"   ✅ 分析完成，共 {len(self.series)} 个 series")


def main():
    parser = argparse.ArgumentParser(description="Kalshi 市场普查")
    parser.add_argument("--summary", action="store_true", help="只显示现有报告摘要")
    parser.add_argument("--update", action="store_true", help="更新 watchlist")
    
    args = parser.parse_args()
    
    census = MarketCensus()
    census.run(summary_only=args.summary)


if __name__ == "__main__":
    main()
