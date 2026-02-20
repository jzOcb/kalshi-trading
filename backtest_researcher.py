#!/usr/bin/env python3
"""
Backtest Market Researcher

用历史已结算市场验证研究框架的准确性。

核心问题: 如果我们用当时可获得的数据做判断，能预测对多少？

Author: OpenClaw
Date: 2026-02-20
"""

import os
import sys
import json
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import requests
except ImportError:
    requests = None

API_BASE = "https://api.elections.kalshi.com/trade-api/v2"


class BacktestResearcher:
    """
    回测市场研究框架
    """
    
    def __init__(self):
        self.results = []
    
    def fetch_settled_markets(self, limit=100, categories=None) -> List[Dict]:
        """
        获取已结算的市场 (通过 events API)
        """
        markets = []
        cursor = None
        skip_categories = {'Sports', 'Entertainment'}
        
        for page in range(30):
            try:
                params = {
                    'limit': 100,
                    'status': 'settled',
                    'with_nested_markets': 'true',
                }
                if cursor:
                    params['cursor'] = cursor
                    
                resp = requests.get(f"{API_BASE}/events", params=params, timeout=15)
                if resp.status_code != 200:
                    break
                    
                data = resp.json()
                for e in data.get('events', []):
                    category = e.get('category', '')
                    
                    # 跳过体育和娱乐
                    if category in skip_categories:
                        continue
                    
                    # 如果指定了类别，只看指定类别
                    if categories and category not in categories:
                        continue
                    
                    for m in e.get('markets', []):
                        if m.get('result'):
                            m['category'] = category
                            m['event_title'] = e.get('title', '')
                            markets.append(m)
                            
                            if len(markets) >= limit:
                                return markets
                
                cursor = data.get('cursor')
                if not cursor:
                    break
                    
            except Exception as e:
                print(f"Error fetching: {e}")
                break
        
        return markets[:limit]
    
    def analyze_settled_market(self, market: Dict) -> Dict:
        """
        分析一个已结算市场
        
        Returns:
            {
                "ticker": "...",
                "title": "...",
                "actual_result": "Yes/No",
                "close_price": 85,  # 结算前最后价格
                "market_correct": true/false,  # 市场价格是否预测对了
                "type": "economic/political/...",
                "had_verifiable_data": true/false,
            }
        """
        ticker = market.get('ticker', '')
        title = market.get('title', '')
        result = market.get('result', '').lower()
        
        # 结算前价格 (用 previous_price 近似)
        close_price = market.get('previous_price', market.get('last_price', 50))
        
        # 市场预测是否正确
        market_predicted_yes = close_price >= 50
        actual_yes = result == 'yes'
        market_correct = market_predicted_yes == actual_yes
        
        # 判断市场类型 (优先使用 API 返回的 category)
        api_category = market.get('category', '').lower()
        title_lower = title.lower()
        
        # 先根据 Kalshi category 分类
        if api_category == 'economics':
            market_type = "economic"
            had_verifiable_data = True
        elif api_category == 'crypto':
            market_type = "crypto"
            had_verifiable_data = True
        elif api_category == 'politics':
            market_type = "political"
            had_verifiable_data = False
        elif api_category == 'elections':
            market_type = "election"
            had_verifiable_data = False
        elif api_category == 'world':
            market_type = "world"
            had_verifiable_data = False
        elif api_category == 'financials':
            market_type = "financial"
            had_verifiable_data = False
        elif api_category == 'companies':
            market_type = "corporate"
            had_verifiable_data = False
        elif api_category == 'science and technology':
            market_type = "tech"
            had_verifiable_data = False
        # 再根据标题细分
        elif any(k in title_lower for k in ['gdp', 'unemployment', 'cpi', 'inflation', 'gas price', 'jobless']):
            market_type = "economic"
            had_verifiable_data = True
        elif any(k in title_lower for k in ['temperature', 'weather', 'high of']):
            market_type = "weather"
            had_verifiable_data = True
        elif any(k in title_lower for k in ['trump', 'biden']) and any(k in title_lower for k in ['say', 'mention', 'tweet']):
            market_type = "speech"
            had_verifiable_data = False
        elif any(k in title_lower for k in ['bitcoin', 'btc', 'ethereum', 'crypto']):
            market_type = "crypto"
            had_verifiable_data = True
        elif any(k in title_lower for k in ['ipo', 'announce']):
            market_type = "corporate"
            had_verifiable_data = False
        else:
            market_type = "other"
            had_verifiable_data = False
        
        return {
            "ticker": ticker,
            "title": title[:60],
            "actual_result": result,
            "close_price": close_price,
            "market_predicted_yes": market_predicted_yes,
            "market_correct": market_correct,
            "type": market_type,
            "had_verifiable_data": had_verifiable_data,
        }
    
    def run_backtest(self, limit=100) -> Dict:
        """
        运行回测
        
        Returns:
            {
                "total": 100,
                "market_accuracy": 0.65,  # 市场价格的准确率
                "by_type": {
                    "economic": {"total": 20, "correct": 18, "accuracy": 0.9},
                    ...
                },
                "verifiable_accuracy": 0.85,  # 可验证市场的准确率
                "unverifiable_accuracy": 0.55,  # 不可验证市场的准确率
                "details": [...]
            }
        """
        print(f"获取已结算市场...", file=sys.stderr)
        markets = self.fetch_settled_markets(limit=limit)
        print(f"找到 {len(markets)} 个已结算市场", file=sys.stderr)
        
        results = []
        for m in markets:
            analysis = self.analyze_settled_market(m)
            results.append(analysis)
        
        # 统计
        total = len(results)
        correct = sum(1 for r in results if r['market_correct'])
        
        # 按类型统计
        by_type = {}
        for r in results:
            t = r['type']
            if t not in by_type:
                by_type[t] = {"total": 0, "correct": 0}
            by_type[t]["total"] += 1
            if r['market_correct']:
                by_type[t]["correct"] += 1
        
        for t in by_type:
            by_type[t]["accuracy"] = by_type[t]["correct"] / by_type[t]["total"] if by_type[t]["total"] > 0 else 0
        
        # 可验证 vs 不可验证
        verifiable = [r for r in results if r['had_verifiable_data']]
        unverifiable = [r for r in results if not r['had_verifiable_data']]
        
        verifiable_accuracy = sum(1 for r in verifiable if r['market_correct']) / len(verifiable) if verifiable else 0
        unverifiable_accuracy = sum(1 for r in unverifiable if r['market_correct']) / len(unverifiable) if unverifiable else 0
        
        return {
            "total": total,
            "correct": correct,
            "market_accuracy": correct / total if total > 0 else 0,
            "by_type": by_type,
            "verifiable_count": len(verifiable),
            "unverifiable_count": len(unverifiable),
            "verifiable_accuracy": verifiable_accuracy,
            "unverifiable_accuracy": unverifiable_accuracy,
            "details": results,
        }
    
    def format_report(self, backtest_result: Dict) -> str:
        """格式化回测报告"""
        r = backtest_result
        
        lines = [
            "=" * 60,
            "📊 市场研究框架回测报告",
            f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "=" * 60,
            "",
            "📈 总体统计",
            f"  已结算市场: {r['total']}",
            f"  市场价格准确率: {r['market_accuracy']:.1%}",
            "",
            "🔍 按类型分析",
        ]
        
        for t, stats in sorted(r['by_type'].items(), key=lambda x: -x[1]['total']):
            lines.append(f"  {t}: {stats['correct']}/{stats['total']} ({stats['accuracy']:.0%})")
        
        lines.extend([
            "",
            "✅ 可验证 vs 不可验证",
            f"  可验证市场 ({r['verifiable_count']}): {r['verifiable_accuracy']:.1%} 准确",
            f"  不可验证市场 ({r['unverifiable_count']}): {r['unverifiable_accuracy']:.1%} 准确",
            "",
            "💡 洞察",
        ])
        
        # 洞察
        if r['verifiable_count'] > 0 and r['unverifiable_count'] > 0:
            if r['verifiable_accuracy'] > r['unverifiable_accuracy'] + 0.1:
                lines.append("  ✅ 可验证市场显著更准 → 研究框架有价值")
        
        # 找最好和最差的类型
        types_with_enough = [(t, s) for t, s in r['by_type'].items() if s['total'] >= 3]
        
        if types_with_enough:
            best_type = max(types_with_enough, key=lambda x: x[1]['accuracy'])
            if best_type[1]['accuracy'] > 0.7:
                lines.append(f"  🎯 {best_type[0]} 类市场最准 ({best_type[1]['accuracy']:.0%})")
            
            worst_type = min(types_with_enough, key=lambda x: x[1]['accuracy'])
            if worst_type[1]['accuracy'] < 0.6:
                lines.append(f"  ⚠️ {worst_type[0]} 类市场最难预测 ({worst_type[1]['accuracy']:.0%})")
        
        # 高置信度市场的表现
        high_conf = [d for d in r['details'] if d['close_price'] >= 85 or d['close_price'] <= 15]
        if high_conf:
            high_conf_correct = sum(1 for d in high_conf if d['market_correct'])
            high_conf_acc = high_conf_correct / len(high_conf)
            lines.append(f"  📌 高置信度市场 (价格>=85或<=15): {high_conf_acc:.0%} 准确 ({len(high_conf)}个)")
        
        lines.extend([
            "",
            "=" * 60,
            "📋 策略建议",
        ])
        
        if r['verifiable_accuracy'] > 0.7:
            lines.append("  1. 优先研究可验证市场 (经济、天气、加密)")
        if r.get('by_type', {}).get('speech', {}).get('accuracy', 1) < 0.6:
            lines.append("  2. 跳过不可验证市场 (演讲、公告类)")
        lines.append("  3. 使用官方数据源验证后再下单")
        
        return "\n".join(lines)


def main():
    """运行回测"""
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100, help="回测市场数量")
    parser.add_argument("--json", action="store_true", help="输出JSON")
    args = parser.parse_args()
    
    backtester = BacktestResearcher()
    result = backtester.run_backtest(limit=args.limit)
    
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(backtester.format_report(result))


if __name__ == "__main__":
    main()
