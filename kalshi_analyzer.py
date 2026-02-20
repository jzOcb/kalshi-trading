#!/usr/bin/env python3
"""
Kalshi Market Analyzer - 统一入口

基于可验证性的预测市场分析系统：
1. 扫描全部市场（排除天气）
2. 筛选 tier 1-2 + volume > 阈值
3. LLM 收集 facts + 综合判断
4. 输出推荐报告

Author: OpenClaw
Date: 2026-02-21
"""

import os
import sys
import json
import argparse
import requests
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple
from pathlib import Path

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from source_detector import detect_sources, get_tier_label

# 加载环境变量
def load_env():
    env_file = Path.home() / "clawd" / "btc-arbitrage" / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    if key not in os.environ:
                        os.environ[key] = value

load_env()

# API 配置
API_BASE = "https://api.elections.kalshi.com/trade-api/v2"

# 默认筛选参数
DEFAULT_CONFIG = {
    "max_days": 90,           # 最长到期时间
    "min_volume": 100,        # 最小交易量（降低阈值）
    "max_tier": 2,            # 最大 tier（1-2 可研究，3 跳过）
    "exclude_categories": ["weather"],  # 排除的类别
}

# 已知有官方数据源的 series（优先扫描）
# 注意：只包含有预测 edge 的市场，排除 crypto/股指（可验证但不可预测）
VERIFIABLE_SERIES = [
    # 经济指标 (BEA/BLS) - 有 GDPNow/Cleveland Fed Nowcast
    "KXGDP", "KXCPI", "KXPCE", "KXJOBLESS", "KXUNEMPLOY",
    # 央行 (FOMC) - 有 CME FedWatch
    "KXFED", "KXRATECUTCOUNT", "KXFOMC",
    # 油价 (AAA/EIA) - 有历史趋势
    "KXAAGAS", "KXGASMAX", "KXGASAVG",
    # 政府 (官方公告)
    "KXSHUTDOWN", "KXDEBT",
    # 排除: KXBTC, KXETH, KXSP500, KXNASDAQ (无预测 edge)
]

class KalshiAnalyzer:
    """Kalshi 市场分析器"""
    
    def __init__(self, config: Dict = None):
        self.config = {**DEFAULT_CONFIG, **(config or {})}
        self.results = []
    
    def fetch_all_markets(self) -> List[Dict]:
        """获取所有市场，优先从已知可验证的 series 获取"""
        markets = []
        seen_tickers = set()
        
        # 1. 先从已知可验证的 series 获取
        print("   扫描已知可验证 series...")
        for series in VERIFIABLE_SERIES:
            try:
                resp = requests.get(f"{API_BASE}/markets", params={
                    "limit": 50,
                    "status": "open", 
                    "series_ticker": series
                }, timeout=15)
                
                if resp.status_code == 200:
                    batch = resp.json().get("markets", [])
                    for m in batch:
                        ticker = m.get("ticker", "")
                        if ticker not in seen_tickers:
                            markets.append(m)
                            seen_tickers.add(ticker)
            except:
                pass
        
        print(f"   从 {len(VERIFIABLE_SERIES)} 个 series 获取 {len(markets)} 个市场")
        
        # 2. 再获取其他市场（补充）
        cursor = None
        for page in range(10):  # 减少页数
            try:
                params = {"limit": 100, "status": "open"}
                if cursor:
                    params["cursor"] = cursor
                
                resp = requests.get(f"{API_BASE}/markets", params=params, timeout=15)
                if resp.status_code != 200:
                    break
                
                data = resp.json()
                batch = data.get("markets", [])
                
                for m in batch:
                    ticker = m.get("ticker", "")
                    if ticker not in seen_tickers:
                        markets.append(m)
                        seen_tickers.add(ticker)
                
                cursor = data.get("cursor")
                if not cursor or len(batch) < 100:
                    break
                    
            except Exception as e:
                print(f"获取市场失败: {e}")
                break
        
        return markets
    
    def filter_markets(self, markets: List[Dict]) -> List[Dict]:
        """根据配置筛选市场"""
        filtered = []
        now = datetime.now(timezone.utc)
        
        for m in markets:
            # 解析到期时间
            close_time_str = m.get("close_time") or m.get("expected_expiration_time")
            if not close_time_str:
                continue
            
            try:
                close_time = datetime.fromisoformat(close_time_str.replace("Z", "+00:00"))
                days_left = (close_time - now).days
            except:
                continue
            
            # 到期时间筛选
            if days_left < 0 or days_left > self.config["max_days"]:
                continue
            
            # Volume 筛选
            volume = m.get("volume_24h", 0) or m.get("volume", 0) or 0
            if volume < self.config["min_volume"]:
                continue
            
            # 类别筛选（排除天气等）
            ticker = m.get("ticker", "")
            title = m.get("title", "").lower()
            
            skip = False
            for cat in self.config["exclude_categories"]:
                if cat.lower() in ticker.lower() or cat.lower() in title:
                    skip = True
                    break
            
            # 更精确的天气检测
            if "KXHIGH" in ticker or "KXLOW" in ticker or "temperature" in title:
                skip = True
            
            if skip:
                continue
            
            # **先检查可验证性，跳过 tier > max_tier**
            rules = m.get("rules_primary", "")
            verify = detect_sources(rules, title)
            tier = verify.get("research_tier", 9)
            
            if tier > self.config["max_tier"]:
                continue  # 直接跳过不可验证的市场
            
            # 添加计算字段
            m["days_left"] = days_left
            m["volume"] = volume
            m["tier"] = tier
            m["sources"] = verify.get("sources", [])
            filtered.append(m)
        
        return filtered
    
    def check_verifiability(self, market: Dict) -> Dict:
        """检查市场可验证性"""
        ticker = market.get("ticker", "")
        title = market.get("title", "")
        rules = market.get("rules_primary", "")
        
        # 使用 source_detector
        result = detect_sources(rules, title)
        
        return {
            "verifiable": result.get("verifiable", False),
            "tier": result.get("research_tier", 9),
            "sources": result.get("sources", []),
            "method": result.get("research_method", ""),
        }
    
    def calculate_annualized_return(self, price: int, days: int) -> float:
        """计算年化收益率"""
        if price <= 0 or price >= 100 or days <= 0:
            return 0.0
        
        # 假设预测正确，计算收益
        profit_pct = (100 - price) / price
        annualized = profit_pct * (365 / days) * 100
        return round(annualized, 1)
    
    def analyze_market(self, market: Dict) -> Dict:
        """收集单个市场的结构化数据（LLM 分析由 OpenClaw agent 完成）"""
        ticker = market.get("ticker", "")
        title = market.get("title", "")
        rules = market.get("rules_primary", "")
        
        # tier 和 sources 已在 filter_markets 中计算
        tier = market.get("tier", 9)
        sources = market.get("sources", [])
        
        # 计算年化
        yes_price = market.get("yes_bid", 50)
        no_price = market.get("no_bid", 50)
        yes_ask = market.get("yes_ask", 50)
        no_ask = market.get("no_ask", 50)
        days = market.get("days_left", 30)
        
        ann_yes = self.calculate_annualized_return(yes_price, days)
        ann_no = self.calculate_annualized_return(no_price, days)
        
        return {
            "ticker": ticker,
            "title": title,
            "rules": rules[:500] if rules else "",  # 截断规则文本
            "days_left": days,
            "close_time": market.get("close_time"),
            "volume": market.get("volume", 0),
            "tier": tier,
            "sources": sources,
            "yes_bid": yes_price,
            "yes_ask": yes_ask,
            "no_bid": no_price,
            "no_ask": no_ask,
            "ann_yes": ann_yes,
            "ann_no": ann_no,
            "status": "READY_FOR_ANALYSIS",
        }
    
    def run(self, limit: int = 10) -> List[Dict]:
        """运行完整分析流程"""
        print("📡 获取市场数据...")
        all_markets = self.fetch_all_markets()
        print(f"   共 {len(all_markets)} 个市场")
        
        print("🔍 筛选市场...")
        filtered = self.filter_markets(all_markets)
        print(f"   筛选后 {len(filtered)} 个市场")
        
        # 按 volume 排序，取 top N
        filtered.sort(key=lambda x: -x.get("volume", 0))
        to_analyze = filtered[:limit]
        
        print(f"🧠 分析 top {len(to_analyze)} 个市场...")
        results = []
        for i, market in enumerate(to_analyze):
            print(f"   [{i+1}/{len(to_analyze)}] {market.get('ticker', '')}")
            result = self.analyze_market(market)
            results.append(result)
        
        self.results = results
        return results
    
    def format_report(self) -> str:
        """格式化输出报告（供 OpenClaw agent 分析）"""
        lines = ["# Kalshi 可分析市场", ""]
        lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append(f"市场数量: {len(self.results)}")
        lines.append("")
        lines.append("---")
        lines.append("")
        
        for r in self.results:
            lines.append(f"## {r['ticker']}")
            lines.append(f"**{r['title']}**")
            lines.append("")
            lines.append(f"- 到期: {r['days_left']} 天 ({r.get('close_time', '')[:10]})")
            lines.append(f"- 价格: YES {r['yes_bid']}¢ (ask {r['yes_ask']}¢) / NO {r['no_bid']}¢ (ask {r['no_ask']}¢)")
            lines.append(f"- 年化: YES {r['ann_yes']}% / NO {r['ann_no']}%")
            lines.append(f"- Volume: {r['volume']:,}")
            lines.append(f"- 数据源: Tier {r['tier']} ({', '.join(r['sources'])})")
            lines.append("")
            if r.get("rules"):
                lines.append(f"**规则摘要:** {r['rules'][:200]}...")
            lines.append("")
            lines.append("---")
            lines.append("")
        
        return "\n".join(lines)
    
    def save_results(self, path: str = None):
        """保存结果到 JSONL"""
        if not path:
            path = Path(__file__).parent / "data" / "analysis_results.jsonl"
        
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, "a") as f:
            for r in self.results:
                r["analyzed_at"] = datetime.now(timezone.utc).isoformat()
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        
        print(f"💾 结果已保存到 {path}")


def main():
    parser = argparse.ArgumentParser(description="Kalshi 市场分析器")
    parser.add_argument("--limit", type=int, default=10, help="分析市场数量")
    parser.add_argument("--min-volume", type=int, default=1000, help="最小交易量")
    parser.add_argument("--max-days", type=int, default=90, help="最长到期天数")
    parser.add_argument("--save", action="store_true", help="保存结果到 JSONL")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    
    args = parser.parse_args()
    
    config = {
        "min_volume": args.min_volume,
        "max_days": args.max_days,
    }
    
    analyzer = KalshiAnalyzer(config)
    results = analyzer.run(limit=args.limit)
    
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(analyzer.format_report())
    
    if args.save:
        analyzer.save_results()


if __name__ == "__main__":
    main()
