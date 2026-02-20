#!/usr/bin/env python3
"""
Deep Research Report - 基于事实核查的 Kalshi 市场分析

这不是数学评分，是真正的研究。

流程:
1. 扫描市场，找出候选 (价格极端 + 流动性可)
2. 对每个候选做深度研究 (不是打分)
3. 基于事实给出判断
4. 收益率只用来决定仓位大小

用法:
    python deep_research_report.py [--top N] [--verbose]
"""

import os
import sys
import json
import time
from datetime import datetime, timezone

# 本地模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from market_researcher import MarketResearcher

# API 基础
try:
    import requests
except ImportError:
    print("Error: requests module required")
    sys.exit(1)

API_BASE = "https://api.elections.kalshi.com/trade-api/v2"


def fetch_candidate_markets(min_volume=200, max_candidates=20):
    """
    扫描市场，找出值得研究的候选
    
    候选条件:
    - 价格极端 (>=85 或 <=15)
    - 有一定流动性 (volume >= min_volume)
    - 非体育/娱乐
    """
    print("🔍 扫描候选市场...", file=sys.stderr)
    
    candidates = []
    cursor = None
    
    for page in range(10):  # 最多10页
        params = {'limit': 100, 'status': 'open', 'with_nested_markets': 'true'}
        if cursor:
            params['cursor'] = cursor
        
        try:
            resp = requests.get(f"{API_BASE}/events", params=params, timeout=15)
            if resp.status_code != 200:
                break
            data = resp.json()
            
            for event in data.get('events', []):
                category = event.get('category', '')
                if category in ['Sports', 'Entertainment']:
                    continue
                
                for market in event.get('markets', []):
                    price = market.get('last_price', 50)
                    volume = market.get('volume_24h', 0) or market.get('volume', 0)
                    
                    # 候选条件
                    if volume < min_volume:
                        continue
                    if not (price >= 85 or price <= 15):
                        continue
                    
                    # 添加事件信息
                    market['event_title'] = event.get('title', '')
                    market['category'] = category
                    candidates.append(market)
            
            cursor = data.get('cursor')
            if not cursor:
                break
                
        except Exception as e:
            print(f"Error fetching: {e}", file=sys.stderr)
            break
    
    # 按流动性排序，取 top N
    candidates.sort(key=lambda x: x.get('volume_24h', 0), reverse=True)
    candidates = candidates[:max_candidates]
    
    print(f"  找到 {len(candidates)} 个候选", file=sys.stderr)
    return candidates


def fetch_market_details(ticker):
    """获取市场详细规则"""
    try:
        resp = requests.get(f"{API_BASE}/markets/{ticker}", timeout=10)
        if resp.status_code == 200:
            return resp.json().get('market', {})
    except:
        pass
    return {}


def research_candidates(candidates, verbose=False):
    """
    对每个候选进行深度研究
    """
    researcher = MarketResearcher()
    results = []
    
    for i, market in enumerate(candidates):
        ticker = market.get('ticker', '')
        print(f"\n📊 研究 [{i+1}/{len(candidates)}]: {ticker}", file=sys.stderr)
        
        # 获取详细规则
        details = fetch_market_details(ticker)
        market['rules_primary'] = details.get('rules_primary', '')
        market['rules_secondary'] = details.get('rules_secondary', '')
        
        # 深度研究
        report = researcher.research(market)
        results.append(report)
        
        if verbose:
            print(researcher.format_report(report))
        
        # 避免 rate limiting
        time.sleep(0.5)
    
    return results


def format_final_report(results):
    """格式化最终报告"""
    lines = []
    lines.append("=" * 60)
    lines.append("📋 Kalshi 深度研究报告")
    lines.append(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("=" * 60)
    
    # 分类
    buy_list = []
    wait_list = []
    skip_list = []
    
    for r in results:
        rec = r['judgment']['recommendation']
        if rec == "BUY":
            buy_list.append(r)
        elif rec == "WAIT":
            wait_list.append(r)
        else:
            skip_list.append(r)
    
    # BUY 推荐
    if buy_list:
        lines.append(f"\n🟢 推荐买入 ({len(buy_list)})")
        lines.append("-" * 40)
        for r in sorted(buy_list, key=lambda x: x['judgment']['confidence'], reverse=True):
            m = r['market']
            j = r['judgment']
            lines.append(f"\n  {m.get('ticker', '')}")
            lines.append(f"  问题: {m.get('title', '')[:50]}...")
            lines.append(f"  价格: {m.get('last_price', '?')}¢ | 方向: {j['direction']}")
            lines.append(f"  置信度: {j['confidence']}% | 理由: {j['reasoning'][:60]}...")
            if j.get('key_facts'):
                lines.append(f"  事实: {j['key_facts'][0]}")
            if j.get('risks'):
                lines.append(f"  风险: {j['risks'][0]}")
            lines.append(f"  👉 仓位: {j['position_size']}")
    
    # WAIT 观望
    if wait_list:
        lines.append(f"\n🟡 观望 ({len(wait_list)})")
        lines.append("-" * 40)
        for r in wait_list[:5]:  # 只显示前5个
            m = r['market']
            j = r['judgment']
            lines.append(f"  {m.get('ticker', '')} | {j['direction']} {j['confidence']}% | {j['reasoning'][:40]}...")
    
    # SKIP 跳过
    lines.append(f"\n🔴 跳过 ({len(skip_list)})")
    lines.append("-" * 40)
    skip_reasons = {}
    for r in skip_list:
        reason = r['judgment'].get('reasoning', '无法核查') or '无法核查'
        reason_short = reason[:30]
        skip_reasons[reason_short] = skip_reasons.get(reason_short, 0) + 1
    for reason, count in sorted(skip_reasons.items(), key=lambda x: -x[1])[:5]:
        lines.append(f"  {reason}... ({count}个)")
    
    # 总结
    lines.append("\n" + "=" * 60)
    lines.append("📊 总结")
    lines.append(f"  研究了 {len(results)} 个市场")
    lines.append(f"  推荐买入: {len(buy_list)}")
    lines.append(f"  建议观望: {len(wait_list)}")
    lines.append(f"  跳过: {len(skip_list)}")
    
    if buy_list:
        lines.append("\n⚡ 行动建议:")
        for r in buy_list[:3]:
            m = r['market']
            j = r['judgment']
            side = "YES" if m.get('last_price', 50) >= 85 else "NO"
            cost = m.get('last_price') if side == "YES" else (100 - m.get('last_price', 50))
            lines.append(f"  • {m.get('ticker', '')} → {side} @ {cost}¢ ({j['position_size']})")
    
    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Kalshi Deep Research Report")
    parser.add_argument("--top", type=int, default=10, help="Number of candidates to research")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed research logs")
    parser.add_argument("--min-volume", type=int, default=200, help="Minimum 24h volume")
    args = parser.parse_args()
    
    print("🚀 Kalshi 深度研究系统", file=sys.stderr)
    print("原则: 事实核查优先，收益率次要", file=sys.stderr)
    print("", file=sys.stderr)
    
    # Step 1: 扫描候选
    candidates = fetch_candidate_markets(
        min_volume=args.min_volume,
        max_candidates=args.top
    )
    
    if not candidates:
        print("没有找到符合条件的候选市场")
        return
    
    # Step 2: 深度研究
    results = research_candidates(candidates, verbose=args.verbose)
    
    # Step 3: 输出报告
    print(format_final_report(results))


if __name__ == "__main__":
    main()
