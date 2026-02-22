#!/usr/bin/env python3
"""
scan_for_analysis.py — 筛选候选市场，输出给 Agent 分析

只做筛选，不做判断。深度分析交给 OpenClaw Agent (Opus)。

用法:
    python3 scan_for_analysis.py              # 输出候选
    python3 scan_for_analysis.py --top 10     # 限制数量
    python3 scan_for_analysis.py --notify     # 发送 Telegram 触发分析
"""

import os
import sys
import json
import argparse
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

API_BASE = "https://api.elections.kalshi.com/trade-api/v2"
WATCHLIST_FILE = Path(__file__).parent / "data" / "watchlist_series.json"
OUTPUT_FILE = Path(__file__).parent / "data" / "candidates.json"

# 默认 watchlist
DEFAULT_SERIES = [
    "KXGDP", "KXCPI", "KXFED", "KXPAYROLLS", "KXUNEMPLOYMENT",
    "KXFEDMENTION", "KXGASPRICES", "KXHIGH", "KXLOW"
]


def load_watchlist():
    try:
        if WATCHLIST_FILE.exists():
            with open(WATCHLIST_FILE) as f:
                return json.load(f).get("series", DEFAULT_SERIES)
    except:
        pass
    return DEFAULT_SERIES


def fetch_markets(series):
    """获取某个 series 的所有开放市场"""
    markets = []
    cursor = None
    
    for _ in range(5):
        params = {"limit": 100, "series_ticker": series, "status": "open"}
        if cursor:
            params["cursor"] = cursor
        
        try:
            resp = requests.get(f"{API_BASE}/markets", params=params, timeout=15)
            if resp.status_code != 200:
                break
            data = resp.json()
            markets.extend(data.get("markets", []))
            cursor = data.get("cursor")
            if not cursor:
                break
        except:
            break
    
    return markets


def filter_candidates(markets, min_volume=50):
    """
    筛选候选
    
    条件:
    - 价格极端 (>=85 或 <=15)
    - 有一定流动性
    - 未过期
    """
    candidates = []
    now = datetime.now(timezone.utc)
    
    for m in markets:
        price = m.get("last_price", 50)
        volume = m.get("volume_24h", 0) or m.get("volume", 0)
        
        # 价格不极端 → 跳过
        if not (price >= 85 or price <= 15):
            continue
        
        # 低流动性 → 跳过 (但保留 0 volume 的新市场)
        if volume < min_volume and volume != 0:
            continue
        
        # 已过期 → 跳过
        close_time = m.get("close_time", "")
        if close_time:
            try:
                close_dt = datetime.fromisoformat(close_time.replace("Z", "+00:00"))
                if close_dt < now:
                    continue
                days_left = (close_dt - now).days
            except:
                days_left = 30
        else:
            days_left = 30
        
        # 计算基础信息
        if price >= 50:
            direction = "YES"
            cost = price
        else:
            direction = "NO"
            cost = 100 - price
        
        profit_per_50 = (100 - cost) * 0.50
        loss_per_50 = cost * 0.50
        odds = loss_per_50 / profit_per_50 if profit_per_50 > 0 else 99
        
        candidates.append({
            "ticker": m.get("ticker"),
            "title": m.get("title"),
            "rules_primary": m.get("rules_primary", ""),
            "price": price,
            "direction": direction,
            "cost": cost,
            "volume": volume,
            "days_left": days_left,
            "profit_per_50": round(profit_per_50, 2),
            "loss_per_50": round(loss_per_50, 2),
            "odds": round(odds, 1),
            "link": f"https://kalshi.com/markets/{m.get('ticker', '').lower()}",
        })
    
    # 按潜在收益排序 (价格越极端越好)
    candidates.sort(key=lambda x: x["cost"])
    
    return candidates


def format_for_agent(candidates):
    """格式化为 Agent 可以分析的文本"""
    lines = [
        "# Kalshi 候选市场分析请求",
        f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')} ET",
        f"候选数量: {len(candidates)}",
        "",
        "请对每个市场进行多角色深度分析（分析师→事实核查员→魔鬼代言人→风控官）",
        "",
        "---",
        ""
    ]
    
    for i, c in enumerate(candidates, 1):
        lines.extend([
            f"## #{i}: {c['ticker']}",
            f"**问题**: {c['title']}",
            f"**方向**: {c['direction']} @ {c['cost']}¢",
            f"**赔率**: 1:{c['odds']} ({'不利' if c['odds'] > 1 else '有利'})",
            f"**到期**: {c['days_left']} 天",
            f"**流动性**: {c['volume']}",
            f"**规则**: {c['rules_primary'][:300]}..." if len(c.get('rules_primary', '')) > 300 else f"**规则**: {c.get('rules_primary', 'N/A')}",
            f"**链接**: {c['link']}",
            "",
            "---",
            ""
        ])
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--notify", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    print("🔍 扫描市场...", file=sys.stderr)
    
    series_list = load_watchlist()
    all_markets = []
    
    for series in series_list:
        markets = fetch_markets(series)
        all_markets.extend(markets)
        print(f"  {series}: {len(markets)}", file=sys.stderr)
    
    print(f"📊 共 {len(all_markets)} 个市场", file=sys.stderr)
    
    candidates = filter_candidates(all_markets)
    candidates = candidates[:args.top]
    
    print(f"🎯 筛选出 {len(candidates)} 个候选", file=sys.stderr)
    
    # 保存 JSON
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "candidates": candidates
        }, f, indent=2)
    
    if args.json:
        print(json.dumps(candidates, indent=2))
    else:
        print(format_for_agent(candidates))
    
    if args.notify:
        # TODO: 触发 OpenClaw 分析
        print("📨 TODO: 发送到 OpenClaw 触发分析", file=sys.stderr)


if __name__ == "__main__":
    main()
