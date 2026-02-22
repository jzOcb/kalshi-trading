#!/usr/bin/env python3
"""
market_census - Kalshi 市场普查工具

功能：
    - 扫描所有 Kalshi 市场
    - 按 series 分类
    - 生成 watchlist_series.json
    - 识别 Tier 1/2 市场

用法：
    python market_census.py                      # 运行普查
    python market_census.py --output watchlist.json
    
依赖：
    - requests
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

# 已知的重要 series (优先扫描)
# 分层: Tier 1 有 Nowcast, Tier 2 有官方数据源
PRIORITY_SERIES = [
    # Tier 1 - 有 Nowcast 数据
    "KXGDP",           # GDP - Atlanta Fed GDPNow
    "KXCPI",           # CPI - Cleveland Fed Nowcast
    "KXPCE",           # PCE - BEA
    "KXFED",           # Fed rate - CME FedWatch
    "KXFOMC",          # FOMC decisions
    "KXRATECUTCOUNT",  # Rate cut count
    "KXJOBLESS",       # Jobless claims - DOL
    "KXUNEMPLOY",      # Unemployment - BLS
    # Tier 2 - 有官方数据源
    "KXAAGAS",         # AAA Gas price
    "KXGASMAX",        # Gas max
    "KXGASAVG",        # Gas average
    "KXSHUTDOWN",      # Government shutdown
    "KXDHSFUND",       # DHS funding
    "KXDEBT",          # Debt ceiling
    "KXTARIFF",        # Tariffs
    "KXRECESSION",     # Recession
    "KXCR",            # Continuing resolution
    # Tier 2 - 政治 (可验证)
    "KXEOWEEK",        # Executive orders (weekly)
    "KXEOTRUMPTERM",   # Executive orders (term)
    "KXBILLSIGNED",    # Bills signed
    "KXCABINET",       # Cabinet confirmations
    "KXSCOTUS",        # Supreme Court
    # Tier 2 - Powell Mentions (历史记录分析)
    "KXFEDMENTION",    # Powell says X at press conference
]


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
    
    def fetch_markets_by_series(self, series_ticker: str) -> List[Dict]:
        """获取特定 series 的所有市场"""
        markets = []
        cursor = None
        
        for page in range(50):  # 每个 series 最多 5000 个市场
            try:
                params = {
                    "limit": 100,
                    "series_ticker": series_ticker,
                    "status": "open"
                }
                if cursor:
                    params["cursor"] = cursor
                
                resp = requests.get(f"{API_BASE}/markets", params=params, timeout=15)
                
                if resp.status_code == 429:
                    time.sleep(3)
                    continue
                
                if resp.status_code != 200:
                    break
                
                data = resp.json()
                batch = data.get("markets", [])
                markets.extend(batch)
                
                cursor = data.get("cursor")
                if not cursor or len(batch) < 100:
                    break
                
                time.sleep(0.15)  # 限流保护
                    
            except Exception as e:
                print(f"      ⚠️ {series_ticker} error: {e}")
                break
        
        return markets
    
    def scan_priority_series(self) -> Dict[str, Dict]:
        """扫描优先 series 列表"""
        print("📡 扫描优先 Series...")
        results = {}
        
        for i, series in enumerate(PRIORITY_SERIES):
            markets = self.fetch_markets_by_series(series)
            
            if not markets:
                continue
            
            # 获取第一个市场的 rules 来检测 tier
            rules = markets[0].get("rules_primary", "")
            title = markets[0].get("title", "")
            result = detect_sources(rules, title)
            
            # 计算统计
            total_volume = sum(m.get("volume_24h", 0) or 0 for m in markets)
            close_times = [m.get("close_time") for m in markets if m.get("close_time")]
            earliest = min(close_times) if close_times else None
            
            # 计算天数
            days_left = None
            if earliest:
                try:
                    close_dt = datetime.fromisoformat(earliest.replace("Z", "+00:00"))
                    days_left = (close_dt - datetime.now(timezone.utc)).days
                except:
                    pass
            
            results[series] = {
                "series_ticker": series,
                "market_count": len(markets),
                "tier": result.get("research_tier", 9),
                "sources": result.get("sources", []),
                "research_method": result.get("research_method", ""),
                "total_volume": total_volume,
                "days_left": days_left,
                "earliest_close": earliest,
                "sample_title": title[:80] if title else "",
            }
            
            tier_icon = "🟢" if result.get("research_tier", 9) <= 2 else "🟡" if result.get("research_tier", 9) <= 4 else "⚪"
            print(f"   {tier_icon} {series}: {len(markets)} markets, tier {result.get('research_tier', 9)}")
            
            time.sleep(0.2)
        
        print(f"   ✅ 扫描完成: {len(results)} 个活跃 series")
        return results
    
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
        
        # 1. 扫描优先 series (经济/政治)
        priority_results = self.scan_priority_series()
        
        # 2. 生成报告
        report = self.generate_priority_report(priority_results)
        
        # 3. 保存
        self.save_priority_census(report)
        
        # 4. 打印摘要
        self.print_summary(report)
        
        return report
    
    def generate_priority_report(self, results: Dict[str, Dict]) -> Dict:
        """从优先扫描结果生成报告"""
        now = datetime.now(timezone.utc)
        
        report = {
            "generated_at": now.isoformat(),
            "total_series": len(results),
            "total_markets": sum(r["market_count"] for r in results.values()),
            "by_tier": defaultdict(list),
            "by_category": defaultdict(list),
            "recommended_watchlist": [],
            "series": results,
        }
        
        for series, info in results.items():
            tier = info.get("tier", 9)
            
            series_info = {
                "series_ticker": series,
                "tier": tier,
                "sources": info.get("sources", []),
                "research_method": info.get("research_method", ""),
                "market_count": info.get("market_count", 0),
                "total_volume": info.get("total_volume", 0),
                "days_left": info.get("days_left"),
                "earliest_close": info.get("earliest_close"),
                "sample_title": info.get("sample_title", ""),
            }
            
            # 分类 (基于 series 名称推断)
            category = "Unknown"
            if series.startswith("KX"):
                s_lower = series.lower()
                if any(x in s_lower for x in ["gdp", "cpi", "pce", "job", "unemp", "gas"]):
                    category = "Economics"
                elif any(x in s_lower for x in ["fed", "fomc", "rate"]):
                    category = "Fed"
                elif any(x in s_lower for x in ["shutdown", "debt", "dhs", "tariff", "cr", "bill", "eo"]):
                    category = "Government"
                elif any(x in s_lower for x in ["trump", "cabinet", "scotus"]):
                    category = "Politics"
            
            series_info["category"] = category
            
            report["by_tier"][f"tier_{tier}"].append(series_info)
            report["by_category"][category].append(series_info)
            
            # 推荐: tier 1-2
            if tier <= 2:
                report["recommended_watchlist"].append(series_info)
        
        # 排序
        report["recommended_watchlist"].sort(key=lambda x: (x["tier"], -(x.get("total_volume") or 0)))
        
        return report
    
    def save_priority_census(self, report: Dict):
        """保存优先扫描结果"""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        
        # 保存完整报告
        with open(CENSUS_FILE, "w") as f:
            json.dump(report, f, indent=2, ensure_ascii=False, default=str)
        print(f"💾 普查结果已保存: {CENSUS_FILE}")
        
        # 保存 watchlist (供 report_v2.py 使用)
        watchlist = {
            "updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "description": "Tier 1-2 可研究市场 watchlist (自动生成)",
            "series": [s["series_ticker"] for s in report["recommended_watchlist"]],
            "short_term": [
                s for s in report["recommended_watchlist"] 
                if s.get("days_left") is not None and s["days_left"] <= 90
            ],
            "long_term": [
                s for s in report["recommended_watchlist"]
                if s.get("days_left") is None or s["days_left"] > 90
            ],
        }
        with open(WATCHLIST_FILE, "w") as f:
            json.dump(watchlist, f, indent=2, ensure_ascii=False, default=str)
        print(f"💾 Watchlist 已保存: {WATCHLIST_FILE}")
        
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
