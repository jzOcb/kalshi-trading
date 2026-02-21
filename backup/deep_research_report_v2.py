#!/usr/bin/env python3
"""
Deep Research Report V2 - 基于事实核查的 Kalshi 市场分析

⚠️ 强制执行 RESEARCH_WORKFLOW.md 流程 ⚠️

每个市场必须通过:
1. 官方数据源提取 (rules_primary)
2. 可验证性检查 (不可验证→SKIP)
3. 数据获取 (AAA/BLS/BEA...)
4. 阈值对比 (边界风险→SKIP)
5. 置信度计算 (无官方数据→SKIP)

用法:
    python deep_research_report_v2.py [--top N] [--verbose] [--category CAT]
    
流程文档: ~/clawd/kalshi/RESEARCH_WORKFLOW.md
"""

import os
import sys
import json
import time
import argparse
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from market_researcher_v2 import MarketResearcherV2

try:
    import requests
except ImportError:
    print("Error: requests module required")
    sys.exit(1)

API_BASE = "https://api.elections.kalshi.com/trade-api/v2"


def fetch_candidate_markets(min_volume=100, max_candidates=30, categories=None):
    """
    扫描市场，找出值得研究的候选
    
    候选条件:
    - 价格极端 (>=80 或 <=20)
    - 有一定流动性
    - 非体育/娱乐 (除非指定)
    """
    print("🔍 扫描候选市场...", file=sys.stderr)
    
    candidates = []
    cursor = None
    skip_categories = {'Sports', 'Entertainment'} if not categories else set()
    
    for page in range(15):
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
                
                if categories and category not in categories:
                    continue
                if category in skip_categories:
                    continue
                
                for market in event.get('markets', []):
                    price = market.get('last_price', 50)
                    volume = market.get('volume_24h', 0) or market.get('volume', 0)
                    
                    # 候选条件: 价格极端 + 有流动性
                    if volume < min_volume:
                        continue
                    if not (price >= 80 or price <= 20):
                        continue
                    
                    market['event_title'] = event.get('title', '')
                    market['category'] = category
                    candidates.append(market)
            
            cursor = data.get('cursor')
            if not cursor:
                break
                
        except Exception as e:
            print(f"Error fetching: {e}", file=sys.stderr)
            break
    
    # 按流动性排序
    candidates.sort(key=lambda x: x.get('volume_24h', 0) or x.get('volume', 0), reverse=True)
    candidates = candidates[:max_candidates]
    
    print(f"  找到 {len(candidates)} 个候选", file=sys.stderr)
    return candidates


def fetch_market_rules(ticker):
    """获取市场详细规则"""
    try:
        resp = requests.get(f"{API_BASE}/markets/{ticker}", timeout=10)
        if resp.status_code == 200:
            return resp.json().get('market', {})
    except:
        pass
    return {}


def research_all(candidates, verbose=False):
    """对所有候选进行研究"""
    researcher = MarketResearcherV2()
    results = []
    
    for i, market in enumerate(candidates):
        ticker = market.get('ticker', '')
        print(f"\n📊 [{i+1}/{len(candidates)}] {ticker}", file=sys.stderr)
        
        # 获取详细规则
        details = fetch_market_rules(ticker)
        market['rules_primary'] = details.get('rules_primary', '')
        market['rules_secondary'] = details.get('rules_secondary', '')
        
        # 研究
        report = researcher.research(market)
        results.append(report)
        
        if verbose:
            print(researcher.format_report(report))
        
        time.sleep(0.3)  # Rate limiting
    
    return results


def format_final_report(results):
    """格式化最终报告"""
    lines = []
    lines.append("=" * 60)
    lines.append("📋 Kalshi 深度研究报告 V2")
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
        lines.append("-" * 50)
        for r in sorted(buy_list, key=lambda x: x['judgment']['confidence'], reverse=True):
            m = r['market']
            j = r['judgment']
            
            # 确定买入方向
            price = m.get('last_price', 50)
            if j['direction'] == 'YES':
                side = "YES" if price <= 50 else "NO"  # 如果预测YES但价格>50，可能是做空
            else:
                side = "NO" if price >= 50 else "YES"
            
            actual_cost = price if side == "YES" else (100 - price)
            
            lines.append(f"\n  📌 {m.get('ticker', '')}")
            lines.append(f"     {m.get('title', '')[:55]}...")
            lines.append(f"     价格: {price}¢ | 方向: {j['direction']} | 置信度: {j['confidence']}%")
            
            # 数据源
            official = [s['source'] for s in r.get('official_sources', [])]
            if official:
                lines.append(f"     ✅ 官方源: {', '.join(official)}")
            
            # 关键事实
            if j.get('key_facts'):
                lines.append(f"     📋 事实: {j['key_facts'][0]}")
            
            lines.append(f"     💡 理由: {j['reasoning'][:60]}...")
            
            if j.get('risks'):
                lines.append(f"     ⚠️ 风险: {j['risks'][0]}")
            
            lines.append(f"     👉 操作: {side} @ {actual_cost}¢ | 仓位: {j['position_size']}")
    
    # WAIT 观望
    if wait_list:
        lines.append(f"\n🟡 观望 ({len(wait_list)})")
        lines.append("-" * 50)
        for r in wait_list[:8]:
            m = r['market']
            j = r['judgment']
            lines.append(f"  {m.get('ticker', '')[:25]} | {j['direction']} {j['confidence']}% | {j['reasoning'][:35]}...")
    
    # SKIP 统计
    lines.append(f"\n🔴 跳过 ({len(skip_list)})")
    lines.append("-" * 50)
    
    skip_reasons = {}
    for r in skip_list:
        reason = r['judgment'].get('reasoning', '无法核查') or '无法核查'
        # 简化原因
        if '不可核查' in reason:
            key = '不可核查'
        elif '无法获取' in reason or '无数据' in reason:
            key = '数据源不可用'
        elif '边界' in reason or '接近' in reason:
            key = '边界风险'
        else:
            key = reason[:25]
        skip_reasons[key] = skip_reasons.get(key, 0) + 1
    
    for reason, count in sorted(skip_reasons.items(), key=lambda x: -x[1]):
        lines.append(f"  • {reason}: {count}个")
    
    # 总结
    lines.append("\n" + "=" * 60)
    lines.append("📊 总结")
    lines.append(f"  研究市场: {len(results)}")
    lines.append(f"  推荐买入: {len(buy_list)}")
    lines.append(f"  建议观望: {len(wait_list)}")
    lines.append(f"  跳过: {len(skip_list)}")
    
    if buy_list:
        total_capital = sum(
            r['market'].get('last_price', 50) if r['judgment']['direction'] == 'YES' 
            else (100 - r['market'].get('last_price', 50))
            for r in buy_list
        )
        lines.append(f"\n💰 如果全买需要: ${total_capital/100:.2f}")
        
        lines.append("\n⚡ 立即行动:")
        for r in buy_list[:3]:
            m = r['market']
            j = r['judgment']
            price = m.get('last_price', 50)
            side = "YES" if j['direction'] == 'YES' and price <= 50 else "NO"
            cost = price if side == "YES" else (100 - price)
            lines.append(f"  • {m.get('ticker', '')} → {side} @ {cost}¢")
    else:
        lines.append("\n📭 今天没有高置信度推荐")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Kalshi Deep Research Report V2")
    parser.add_argument("--top", type=int, default=15, help="研究多少个候选")
    parser.add_argument("--verbose", "-v", action="store_true", help="显示详细研究过程")
    parser.add_argument("--min-volume", type=int, default=100, help="最小24h交易量")
    parser.add_argument("--category", type=str, help="只看特定类别 (Economics, Politics...)")
    parser.add_argument("--json", action="store_true", help="输出JSON格式")
    args = parser.parse_args()
    
    print("🚀 Kalshi 深度研究系统 V2", file=sys.stderr)
    print("原则: 官方数据源优先，事实核查，不猜测", file=sys.stderr)
    print("", file=sys.stderr)
    
    categories = [args.category] if args.category else None
    
    # Step 1: 扫描候选
    candidates = fetch_candidate_markets(
        min_volume=args.min_volume,
        max_candidates=args.top,
        categories=categories
    )
    
    if not candidates:
        print("没有找到符合条件的候选市场")
        return
    
    # Step 2: 深度研究
    results = research_all(candidates, verbose=args.verbose)
    
    # Step 3: 输出
    if args.json:
        # JSON 输出
        output = {
            "timestamp": datetime.now().isoformat(),
            "total": len(results),
            "buy": [r for r in results if r['judgment']['recommendation'] == 'BUY'],
            "wait": [r for r in results if r['judgment']['recommendation'] == 'WAIT'],
            "skip": [r for r in results if r['judgment']['recommendation'] == 'SKIP'],
        }
        print(json.dumps(output, indent=2, default=str))
    else:
        print(format_final_report(results))


if __name__ == "__main__":
    main()
