#!/usr/bin/env python3
"""
Kalshi Quick Scanner (Layer 1)

快速扫描已知 series，生成 actionable watchlist。
每日运行，~20 API calls，<30 秒。

用法:
    python3 quick_scan.py              # 扫描所有已知 series
    python3 quick_scan.py --days 30    # 只看 30 天内
    python3 quick_scan.py --json       # JSON 输出

Author: OpenClaw
Date: 2026-02-20
"""

import os
import sys
import json
import argparse
import requests
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from source_detector import detect_sources

API_BASE = "https://api.elections.kalshi.com/trade-api/v2"
DATA_DIR = Path(__file__).parent / "data"
KNOWN_SERIES_FILE = DATA_DIR / "known_series.json"


def load_known_series() -> list:
    """加载已知 series 列表"""
    if KNOWN_SERIES_FILE.exists():
        with open(KNOWN_SERIES_FILE) as f:
            data = json.load(f)
            return data.get("active", [])
    return []


def scan_series(series_info: dict, max_days: int = 90) -> list:
    """扫描单个 series，返回符合条件的市场"""
    series = series_info.get("series", "")
    
    try:
        resp = requests.get(f"{API_BASE}/markets", params={
            "series_ticker": series,
            "status": "open",
            "limit": 20
        }, timeout=10)
        
        if resp.status_code != 200:
            return []
        
        markets = resp.json().get("markets", [])
        if not markets:
            return []
        
        now = datetime.now(timezone.utc)
        results = []
        
        for m in markets:
            ticker = m.get("ticker", "")
            title = m.get("title", "")
            volume = m.get("volume", 0)
            rules = m.get("rules_primary", "")
            
            # 计算到期天数
            close_time_str = m.get("close_time", "")
            try:
                close_time = datetime.fromisoformat(close_time_str.replace("Z", "+00:00"))
                days_left = (close_time - now).days
            except:
                days_left = 9999
            
            if days_left > max_days:
                continue
            
            # 检测 tier
            result = detect_sources(rules, title)
            tier = result.get("research_tier", 9)
            sources = result.get("sources", [])
            
            results.append({
                "ticker": ticker,
                "series": series,
                "title": title[:60],
                "category": series_info.get("category", ""),
                "tier": tier,
                "sources": sources or [series_info.get("source", "")],
                "volume": volume,
                "days_left": days_left,
            })
        
        return results
        
    except Exception as e:
        return []


def quick_scan(max_days: int = 90, min_volume: int = 0) -> dict:
    """执行快速扫描"""
    known = load_known_series()
    now = datetime.now(timezone.utc)
    
    all_markets = []
    
    for series_info in known:
        markets = scan_series(series_info, max_days)
        all_markets.extend(markets)
    
    # 过滤和排序
    if min_volume > 0:
        all_markets = [m for m in all_markets if m["volume"] >= min_volume]
    
    all_markets.sort(key=lambda x: (x["tier"], -x["volume"]))
    
    # 分组
    tier_1_2 = [m for m in all_markets if m["tier"] <= 2]
    tier_3 = [m for m in all_markets if m["tier"] == 3]
    
    return {
        "scan_time": now.isoformat(),
        "filters": {
            "max_days": max_days,
            "min_volume": min_volume,
        },
        "series_scanned": len(known),
        "total_markets": len(all_markets),
        "tier_1_2": tier_1_2,
        "tier_3": tier_3,
    }


def print_report(report: dict):
    """打印报告"""
    print("=" * 70)
    print("📊 KALSHI 快速扫描 (Layer 1)")
    print("=" * 70)
    print(f"扫描时间: {report['scan_time'][:19]}")
    print(f"扫描 series: {report['series_scanned']} 个")
    print(f"符合条件市场: {report['total_markets']} 个")
    
    tier_1_2 = report["tier_1_2"]
    tier_3 = report["tier_3"]
    
    print(f"\n### ✅ Tier 1-2 可研究 ({len(tier_1_2)} 个)\n")
    for m in tier_1_2:
        print(f"  Tier {m['tier']} | {m['days_left']:>3}天 | vol={m['volume']:>7,} | {m['series']}")
        print(f"       {m['title']}")
        print(f"       Sources: {m['sources']}")
        print()
    
    if tier_3:
        print(f"\n### ⚠️ Tier 3 ({len(tier_3)} 个)\n")
        for m in tier_3[:5]:
            print(f"  {m['days_left']:>3}天 | vol={m['volume']:>7,} | {m['ticker'][:30]}")
    
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Kalshi Quick Scanner")
    parser.add_argument("--days", type=int, default=90, help="最大到期天数")
    parser.add_argument("--min-volume", type=int, default=0, help="最小 volume")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    parser.add_argument("--save", action="store_true", help="保存结果")
    
    args = parser.parse_args()
    
    report = quick_scan(max_days=args.days, min_volume=args.min_volume)
    
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_report(report)
    
    if args.save:
        output_path = DATA_DIR / "quick_scan_result.json"
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"\n💾 已保存: {output_path}")


if __name__ == "__main__":
    main()
