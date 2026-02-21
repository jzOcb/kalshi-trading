#!/usr/bin/env python3
"""
Kalshi Discovery Scanner (Layer 2)

全量扫描发现新的高 volume series/events。
每周运行一次，~10-15 分钟。

逻辑：
1. 获取所有 events → 提取 unique prefixes
2. 对每个 prefix，获取 1 个 market 检查 volume
3. 发现新的高 volume prefix → 自动加入 known_series.json

用法:
    python3 discovery_scan.py              # 全量扫描
    python3 discovery_scan.py --min-vol 1000  # 最小 volume
    python3 discovery_scan.py --dry-run    # 只显示，不更新配置

Author: OpenClaw
Date: 2026-02-20
"""

import os
import sys
import json
import argparse
import requests
import time
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from source_detector import detect_sources

API_BASE = "https://api.elections.kalshi.com/trade-api/v2"
DATA_DIR = Path(__file__).parent / "data"
KNOWN_SERIES_FILE = DATA_DIR / "known_series.json"

TARGET_CATEGORIES = {"Economics", "Politics", "Financials", "Elections", "World", "Companies"}
EXCLUDE_PREFIXES = {"KXHIGH", "KXLOW", "KXMVESPORTS", "KXESPORTS"}


def fetch_all_events() -> list:
    """获取所有 open events"""
    events = []
    cursor = None
    
    for _ in range(60):
        try:
            resp = requests.get(f"{API_BASE}/events", params={
                "limit": 100, "status": "open", "cursor": cursor
            }, timeout=15)
            
            if resp.status_code == 429:
                time.sleep(5)
                continue
            
            if resp.status_code != 200:
                break
            
            data = resp.json()
            events.extend(data.get("events", []))
            cursor = data.get("cursor")
            
            if not cursor:
                break
            
            time.sleep(0.1)
        except:
            break
    
    return events


def extract_prefixes(events: list) -> dict:
    """提取 unique prefixes"""
    prefixes = defaultdict(lambda: {
        "count": 0, 
        "categories": set(), 
        "example_event": "",
        "example_title": "",
    })
    
    for e in events:
        event_ticker = e.get("event_ticker", "")
        category = e.get("category", "")
        title = e.get("title", "")
        
        # 提取前缀
        prefix = event_ticker.split("-")[0] if "-" in event_ticker else event_ticker
        
        # 跳过排除的
        if any(prefix.startswith(ex) for ex in EXCLUDE_PREFIXES):
            continue
        
        # 只保留目标类别
        if category not in TARGET_CATEGORIES:
            continue
        
        prefixes[prefix]["count"] += 1
        prefixes[prefix]["categories"].add(category)
        if not prefixes[prefix]["example_event"]:
            prefixes[prefix]["example_event"] = event_ticker
            prefixes[prefix]["example_title"] = title[:60]
    
    return dict(prefixes)


def check_prefix_volume(prefix: str, example_event: str) -> dict:
    """检查单个 prefix 的 volume"""
    try:
        # 先尝试用 series_ticker
        resp = requests.get(f"{API_BASE}/markets", params={
            "series_ticker": prefix,
            "status": "open",
            "limit": 5
        }, timeout=10)
        
        if resp.status_code == 200:
            markets = resp.json().get("markets", [])
            if markets:
                total_volume = sum(m.get("volume", 0) for m in markets)
                
                # 检测 tier
                m = markets[0]
                result = detect_sources(m.get("rules_primary", ""), m.get("title", ""))
                
                return {
                    "volume": total_volume,
                    "tier": result.get("research_tier", 9),
                    "sources": result.get("sources", []),
                    "market_count": len(markets),
                }
        
        # 如果 series_ticker 没结果，用 event_ticker
        resp = requests.get(f"{API_BASE}/markets", params={
            "event_ticker": example_event,
            "status": "open",
            "limit": 5
        }, timeout=10)
        
        if resp.status_code == 200:
            markets = resp.json().get("markets", [])
            if markets:
                total_volume = sum(m.get("volume", 0) for m in markets)
                
                m = markets[0]
                result = detect_sources(m.get("rules_primary", ""), m.get("title", ""))
                
                return {
                    "volume": total_volume,
                    "tier": result.get("research_tier", 9),
                    "sources": result.get("sources", []),
                    "market_count": len(markets),
                }
        
        return {"volume": 0, "tier": 9, "sources": [], "market_count": 0}
        
    except:
        return {"volume": 0, "tier": 9, "sources": [], "market_count": 0}


def load_known_series() -> set:
    """加载已知 series"""
    if KNOWN_SERIES_FILE.exists():
        with open(KNOWN_SERIES_FILE) as f:
            data = json.load(f)
            return {s["series"] for s in data.get("active", [])}
    return set()


def update_known_series(new_series: list):
    """更新 known_series.json"""
    if not KNOWN_SERIES_FILE.exists():
        data = {"updated": "", "active": [], "exclude": [], "inactive": []}
    else:
        with open(KNOWN_SERIES_FILE) as f:
            data = json.load(f)
    
    data["updated"] = datetime.now().strftime("%Y-%m-%d")
    
    existing = {s["series"] for s in data.get("active", [])}
    
    for s in new_series:
        if s["series"] not in existing:
            data["active"].append(s)
    
    with open(KNOWN_SERIES_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def discovery_scan(min_volume: int = 1000, dry_run: bool = False) -> dict:
    """执行发现扫描"""
    now = datetime.now(timezone.utc)
    
    print("📡 Phase 1: 获取所有 events...", flush=True)
    events = fetch_all_events()
    print(f"   共 {len(events)} 个 events", flush=True)
    
    print("\n📊 Phase 2: 提取 unique prefixes...", flush=True)
    prefixes = extract_prefixes(events)
    print(f"   目标类别 prefixes: {len(prefixes)} 个", flush=True)
    
    print(f"\n🔍 Phase 3: 检查 volume (min={min_volume})...", flush=True)
    
    known = load_known_series()
    print(f"   已知 series: {len(known)} 个", flush=True)
    
    discoveries = []
    checked = 0
    
    for prefix, info in prefixes.items():
        vol_info = check_prefix_volume(prefix, info["example_event"])
        
        checked += 1
        if checked % 50 == 0:
            print(f"   已检查 {checked}/{len(prefixes)}...", flush=True)
        
        if vol_info["volume"] >= min_volume:
            is_new = prefix not in known
            
            discoveries.append({
                "series": prefix,
                "category": list(info["categories"])[0],
                "source": vol_info["sources"][0] if vol_info["sources"] else "",
                "volume": vol_info["volume"],
                "tier": vol_info["tier"],
                "event_count": info["count"],
                "is_new": is_new,
                "example": info["example_title"],
            })
        
        time.sleep(0.08)
    
    # 排序
    discoveries.sort(key=lambda x: (-x["volume"]))
    
    # 分类
    new_discoveries = [d for d in discoveries if d["is_new"]]
    existing = [d for d in discoveries if not d["is_new"]]
    
    result = {
        "scan_time": now.isoformat(),
        "total_events": len(events),
        "total_prefixes": len(prefixes),
        "checked": checked,
        "min_volume": min_volume,
        "discoveries": len(discoveries),
        "new_discoveries": new_discoveries,
        "existing_high_volume": existing,
    }
    
    # 更新配置 (如果不是 dry run)
    if new_discoveries and not dry_run:
        new_entries = [{
            "series": d["series"],
            "category": d["category"],
            "source": d["source"],
            "note": f"auto-discovered {datetime.now().strftime('%Y-%m-%d')}",
        } for d in new_discoveries if d["tier"] <= 3]
        
        if new_entries:
            update_known_series(new_entries)
            result["added_to_config"] = len(new_entries)
    
    return result


def print_report(result: dict):
    """打印报告"""
    print("\n" + "=" * 70)
    print("📊 KALSHI 发现扫描 (Layer 2)")
    print("=" * 70)
    print(f"扫描时间: {result['scan_time'][:19]}")
    print(f"Events: {result['total_events']} → Prefixes: {result['total_prefixes']} → 高Volume: {result['discoveries']}")
    
    new = result["new_discoveries"]
    existing = result["existing_high_volume"]
    
    if new:
        print(f"\n### 🆕 新发现 ({len(new)} 个)\n")
        for d in new[:20]:
            tier_icon = "✅" if d["tier"] <= 2 else "⚠️" if d["tier"] == 3 else "❓"
            print(f"  {tier_icon} {d['series']:<25} | vol={d['volume']:>7,} | Tier {d['tier']} | {d['category']}")
            print(f"       {d['example']}")
    else:
        print("\n### 🆕 新发现: 无")
    
    print(f"\n### 📋 已知高 Volume ({len(existing)} 个)")
    for d in existing[:10]:
        print(f"  {d['series']:<25} | vol={d['volume']:>7,}")
    
    if result.get("added_to_config"):
        print(f"\n💾 已添加 {result['added_to_config']} 个到 known_series.json")
    
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Kalshi Discovery Scanner")
    parser.add_argument("--min-vol", type=int, default=1000, help="最小 volume")
    parser.add_argument("--dry-run", action="store_true", help="只显示，不更新配置")
    
    args = parser.parse_args()
    
    result = discovery_scan(min_volume=args.min_vol, dry_run=args.dry_run)
    print_report(result)


if __name__ == "__main__":
    main()
