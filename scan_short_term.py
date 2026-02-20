#!/usr/bin/env python3
"""
Kalshi 短期市场扫描器

专注于:
1. 90天内到期
2. 有官方数据源可核查
3. 价格极端 (有套利空间)

市场类型优先级:
1. 天气 (每日结算，NWS 官方数据)
2. 经济指标 (GDP, CPI - BEA/BLS 官方数据)
3. Fed 利率 (FOMC 官方决定)

用法:
    python3 scan_short_term.py              # 默认扫描
    python3 scan_short_term.py --days 30    # 只看30天内
    python3 scan_short_term.py --weather    # 只看天气
"""

import os
import sys
import json
import argparse
import requests
from datetime import datetime, timedelta
from typing import List, Dict
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from source_detector import detect_sources, get_tier_label

API_BASE = "https://api.elections.kalshi.com/trade-api/v2"
CACHE_DIR = Path(__file__).parent / "data"
RULES_CACHE_FILE = CACHE_DIR / "rules_cache.json"


def load_rules_cache() -> Dict:
    """加载 rules_primary 缓存"""
    if RULES_CACHE_FILE.exists():
        try:
            with open(RULES_CACHE_FILE) as f:
                return json.load(f)
        except:
            pass
    return {}


def save_rules_cache(cache: Dict):
    """保存 rules_primary 缓存"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(RULES_CACHE_FILE, 'w') as f:
        json.dump(cache, f)


def fetch_market_rules(ticker: str, cache: Dict) -> str:
    """获取单个市场的 rules_primary (带缓存)"""
    if ticker in cache:
        return cache[ticker]
    
    try:
        resp = requests.get(f"{API_BASE}/markets/{ticker}", timeout=10)
        if resp.status_code == 200:
            rules = resp.json().get("market", {}).get("rules_primary", "")
            cache[ticker] = rules
            return rules
    except:
        pass
    return ""


# 已知的短期 series
WEATHER_SERIES = [
    "KXHIGHTBOS", "KXHIGHTNYC", "KXHIGHTCHI", "KXHIGHTLAX", "KXHIGHTSFO",
    "KXHIGHTMIA", "KXHIGHTPHX", "KXHIGHTDEN", "KXHIGHTSEA", "KXHIGHTAUS",
    "KXLOWTNYC", "KXLOWTCHI", "KXLOWTBOS", "KXLOWTLAX",
]

ECON_SERIES = [
    # 经济指标
    "KXGDP",           # GDP - BEA
    "KXCPI",           # CPI - BLS
    "KXPCE",           # PCE - BEA
    "KXJOBLESS",       # Jobless claims - BLS
    "KXUNEMPLOY",      # Unemployment - BLS
    # 央行
    "KXFED",           # Fed rate - FOMC
    "KXRATECUTCOUNT",  # Rate cut count
    "KXFOMC",          # FOMC decisions
    # 油价
    "KXAAGAS",         # AAA Gas price
    "KXGASMAX",        # Gas max
    "KXGASAVG",        # Gas average
    # 加密
    "KXBTC",           # Bitcoin daily
    "KXETH",           # Ethereum
    # 股指
    "KXSP500",         # S&P 500
    "KXNASDAQ",        # Nasdaq
    "INX",             # Index markets
    "INXD",            # Daily index
    "INXW",            # Weekly index
    # 政治/政府
    "KXSHUTDOWN",      # Government shutdown
    "KXDHSFUND",       # DHS funding
    "KXDEBT",          # Debt ceiling
    "KXTARIFF",        # Tariffs
]


def fetch_series_markets(series_list: List[str], max_days: int = 90, min_volume: int = 0) -> List[Dict]:
    """获取指定 series 的市场"""
    cutoff = datetime.now() + timedelta(days=max_days)
    markets = []
    
    for series in series_list:
        try:
            resp = requests.get(f"{API_BASE}/markets", 
                params={"series_ticker": series, "limit": 100, "status": "open"},
                timeout=15)
            
            if resp.status_code != 200:
                continue
            
            for m in resp.json().get("markets", []):
                exp_str = m.get("expected_expiration_time") or m.get("expiration_time")
                if not exp_str:
                    continue
                
                # 检查流动性
                volume = m.get("volume_24h", 0) or m.get("volume", 0) or 0
                open_interest = m.get("open_interest", 0) or 0
                if volume < min_volume and open_interest < 10:
                    continue  # 跳过无流动性市场
                
                try:
                    exp = datetime.fromisoformat(exp_str.replace("Z", "+00:00")).replace(tzinfo=None)
                    days_left = (exp - datetime.now()).days
                    
                    if exp > cutoff:
                        continue
                    
                    m["days_left"] = days_left
                    m["series"] = series
                    markets.append(m)
                except:
                    continue
                    
        except Exception as e:
            print(f"Error fetching {series}: {e}", file=sys.stderr)
    
    return markets


def categorize_market(market: Dict, rules_cache: Dict = None) -> Dict:
    """
    动态检测市场可研究性
    
    使用 source_detector 模块，无需白名单维护。
    """
    ticker = market.get("ticker", "")
    title = market.get("title", "")
    
    # 获取 rules_primary (带缓存)
    rules = market.get("rules_primary", "")
    if not rules and rules_cache is not None:
        rules = fetch_market_rules(ticker, rules_cache)
        market["rules_primary"] = rules
    
    # 使用 source_detector 动态检测
    detection = detect_sources(rules, title)
    
    market["verifiable"] = detection["verifiable"]
    market["data_source"] = detection["sources"][0] if detection["sources"] else "Unknown"
    market["all_sources"] = detection["sources"]
    market["research_tier"] = detection["research_tier"]
    market["research_method"] = detection["research_method"]
    market["detection_method"] = detection["detection_method"]
    
    # 分类 (用于报告分组)
    source = market["data_source"]
    if source == "NWS":
        market["category"] = "weather"
        # 提取城市
        for city, code in [("Boston", "BOS"), ("NYC", "NYC"), ("Chicago", "CHI"), 
                           ("Los Angeles", "LAX"), ("San Francisco", "SFO"),
                           ("Miami", "MIA"), ("Phoenix", "PHX"), ("Seattle", "SEA")]:
            if code in ticker:
                market["city"] = city
                break
        else:
            market["city"] = "Unknown"
    elif source in ["BLS", "BEA", "Census"]:
        market["category"] = "economic"
    elif source in ["FOMC"]:
        market["category"] = "fed"
    elif source in ["Crypto"]:
        market["category"] = "crypto"
    elif source in ["Exchange", "CME"]:
        market["category"] = "index"
    elif source in ["Congress", "Treasury", "WhiteHouse", "USTR", "DHS"]:
        market["category"] = "political"
    else:
        market["category"] = "other"
    
    return market


def score_market(market: Dict) -> int:
    """评分市场
    
    核心标准 (必须全部满足才推荐):
    1. 有官方数据源 — 能核查，不是猜
    2. 可研究预测 — 有方法论，不是纯赌
    3. 流动性够 — 能进出
    """
    score = 0
    price = market.get("last_price", 50)
    days = market.get("days_left", 999)
    
    # ═══════════════════════════════════════════════════════════
    # 🚨 强制检查: 无官方数据源 = 不推荐 (score 上限 40)
    # ═══════════════════════════════════════════════════════════
    if not market.get("verifiable"):
        market["score"] = 0
        market["skip_reason"] = "无可验证数据源"
        return 0
    
    # 有官方数据源 (+40 基础分)
    score += 40
    
    # 研究层级加分 (Tier 1 最高)
    tier = market.get("research_tier", 9)
    if tier == 1:  # 官方数据 (BLS, BEA, NWS, FOMC)
        score += 25
    elif tier == 2:  # 官方日程/公开信息
        score += 15
    elif tier == 3:  # 新闻驱动但有事实可查
        score += 5
    
    # 时间优先 (越短越好)
    if days <= 7:
        score += 15
    elif days <= 30:
        score += 10
    elif days <= 60:
        score += 5
    
    # 价格极端 (有 edge 空间)
    if price >= 85 or price <= 15:
        score += 10
    elif price >= 75 or price <= 25:
        score += 5
    
    # 流动性检查
    volume = market.get("volume_24h", 0) or market.get("volume", 0) or 0
    open_interest = market.get("open_interest", 0) or 0
    
    if volume >= 50 or open_interest >= 50:
        score += 15
    elif volume >= 10 or open_interest >= 20:
        score += 5
    else:
        # 流动性不足，降分
        score -= 20
        market["low_liquidity"] = True
    
    market["score"] = score
    return score


def format_report(markets: List[Dict]) -> str:
    """格式化报告"""
    lines = [
        "=" * 65,
        "📊 Kalshi 短期市场扫描报告",
        f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "=" * 65,
    ]
    
    # 按类别分组
    by_category = {}
    for m in markets:
        cat = m.get("category", "other")
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(m)
    
    # 天气市场
    if "weather" in by_category:
        weather = sorted(by_category["weather"], key=lambda x: (x.get("days_left", 0), -x.get("score", 0)))
        lines.append(f"\n🌡️ 天气市场 ({len(weather)} 个)")
        lines.append("-" * 50)
        
        # 按天分组
        by_day = {}
        for m in weather:
            day = m.get("days_left", 0)
            if day not in by_day:
                by_day[day] = []
            by_day[day].append(m)
        
        for day in sorted(by_day.keys())[:3]:  # 只显示前3天
            lines.append(f"\n  📅 {day}天后到期:")
            for m in sorted(by_day[day], key=lambda x: -x.get("score", 0))[:6]:
                price = m.get("last_price", 50)
                extreme = "⭐" if (price >= 80 or price <= 20) else ""
                city = m.get("city", "?")
                lines.append(f"    {m['ticker'][:30]:30s} {price:2d}¢ {extreme} | {city}")
    
    # 经济市场
    if "economic" in by_category:
        econ = sorted(by_category["economic"], key=lambda x: (x.get("days_left", 0), -x.get("score", 0)))
        lines.append(f"\n📈 经济指标市场 ({len(econ)} 个)")
        lines.append("-" * 50)
        
        for m in econ[:10]:
            price = m.get("last_price", 50)
            days = m.get("days_left", 0)
            extreme = "⭐" if (price >= 80 or price <= 20) else ""
            source = m.get("data_source", "?")
            lines.append(f"  [{days:3d}天] {price:2d}¢ {extreme} {m['ticker'][:28]} ({source})")
    
    # Fed 市场
    if "fed" in by_category:
        fed = sorted(by_category["fed"], key=lambda x: x.get("days_left", 0))
        lines.append(f"\n🏦 Fed/利率市场 ({len(fed)} 个)")
        lines.append("-" * 50)
        
        for m in fed[:5]:
            price = m.get("last_price", 50)
            days = m.get("days_left", 0)
            extreme = "⭐" if (price >= 80 or price <= 20) else ""
            lines.append(f"  [{days:3d}天] {price:2d}¢ {extreme} {m['ticker'][:28]}")
    
    # 加密市场
    if "crypto" in by_category:
        crypto = sorted(by_category["crypto"], key=lambda x: x.get("days_left", 0))
        lines.append(f"\n₿ 加密市场 ({len(crypto)} 个)")
        lines.append("-" * 50)
        
        for m in crypto[:10]:
            price = m.get("last_price", 50)
            days = m.get("days_left", 0)
            extreme = "⭐" if (price >= 80 or price <= 20) else ""
            lines.append(f"  [{days:3d}天] {price:2d}¢ {extreme} {m['ticker'][:28]}")
    
    # 股指市场
    if "index" in by_category:
        idx = sorted(by_category["index"], key=lambda x: x.get("days_left", 0))
        lines.append(f"\n📈 股指市场 ({len(idx)} 个)")
        lines.append("-" * 50)
        
        for m in idx[:10]:
            price = m.get("last_price", 50)
            days = m.get("days_left", 0)
            extreme = "⭐" if (price >= 80 or price <= 20) else ""
            lines.append(f"  [{days:3d}天] {price:2d}¢ {extreme} {m['ticker'][:28]}")
    
    # 政治市场
    if "political" in by_category:
        pol = sorted(by_category["political"], key=lambda x: x.get("days_left", 0))
        lines.append(f"\n🏛️ 政治市场 ({len(pol)} 个)")
        lines.append("-" * 50)
        
        for m in pol[:5]:
            price = m.get("last_price", 50)
            days = m.get("days_left", 0)
            extreme = "⭐" if (price >= 80 or price <= 20) else ""
            lines.append(f"  [{days:3d}天] {price:2d}¢ {extreme} {m['ticker'][:28]}")
    
    # 推荐
    lines.append("\n" + "=" * 65)
    lines.append("📋 推荐 (必须: 官方数据源 + 可研究 + 流动性)")
    lines.append("-" * 50)
    
    # 强制过滤: 必须有数据源 + 流动性
    top = [m for m in markets 
           if m.get("verifiable") 
           and not m.get("low_liquidity")
           and m.get("score", 0) >= 60]
    top = sorted(top, key=lambda x: -x.get("score", 0))[:10]
    
    if top:
        for m in top:
            price = m.get("last_price", 50)
            days = m.get("days_left", 0)
            score = m.get("score", 0)
            source = m.get("data_source", "?")
            tier = m.get("research_tier", 9)
            method = m.get("research_method", "?")
            
            tier_label = {1: "T1官方", 2: "T2日程", 3: "T3新闻"}.get(tier, "?")
            
            side = "YES" if price <= 50 else "NO"
            cost = price if side == "YES" else (100 - price)
            
            lines.append(f"  📌 {m['ticker']}")
            lines.append(f"     [{days}天] {side} @ {cost}¢ | {tier_label} | {source}")
            lines.append(f"     研究方法: {method}")
    else:
        lines.append("  ⚠️ 无符合标准的市场")
        lines.append("  (需要: 官方数据源 + 可研究预测 + 足够流动性)")
    
    # 显示被过滤掉的市场数量
    skipped = len([m for m in markets if m.get("skip_reason") or m.get("low_liquidity")])
    if skipped > 0:
        lines.append(f"\n  ℹ️ 已过滤 {skipped} 个不符合标准的市场")
    
    # 官方数据源 (用于研究预测)
    lines.append("\n📚 官方数据源 (做功课用):")
    lines.append("  • CPI Nowcast: https://www.clevelandfed.org/indicators-and-data/inflation-nowcasting")
    lines.append("  • GDP Nowcast: https://www.atlantafed.org/cqer/research/gdpnow")
    lines.append("  • 天气 NWS: https://www.weather.gov/")
    lines.append("  • Fed CME: https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html")
    
    # Kalshi 链接
    lines.append("\n🔗 Kalshi 市场:")
    lines.append("  • CPI: https://kalshi.com/markets/kxcpi")
    lines.append("  • GDP: https://kalshi.com/markets/kxgdp")
    lines.append("  • Fed: https://kalshi.com/markets/kxfed")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Kalshi 短期市场扫描")
    parser.add_argument("--days", type=int, default=90, help="最大到期天数")
    parser.add_argument("--weather", action="store_true", help="包含天气市场 (默认排除)")
    parser.add_argument("--all", action="store_true", help="扫描所有类型")
    parser.add_argument("--json", action="store_true", help="输出JSON")
    parser.add_argument("--fetch-rules", action="store_true", help="获取 rules_primary (慢但更准)")
    args = parser.parse_args()
    
    print("🔍 扫描短期市场...", file=sys.stderr)
    
    # 加载 rules 缓存
    rules_cache = load_rules_cache() if args.fetch_rules else None
    if rules_cache is not None:
        print(f"   已加载 {len(rules_cache)} 条 rules 缓存", file=sys.stderr)
    
    # 默认只扫描经济类 (天气有独立系统)
    if args.all:
        series = WEATHER_SERIES + ECON_SERIES
    elif args.weather:
        series = WEATHER_SERIES
    else:
        series = ECON_SERIES  # 默认只扫经济类
    
    # 获取市场
    markets = fetch_series_markets(series, max_days=args.days)
    print(f"   找到 {len(markets)} 个市场", file=sys.stderr)
    
    # 分类和评分
    for m in markets:
        categorize_market(m, rules_cache)
        score_market(m)
    
    # 保存 rules 缓存
    if rules_cache is not None:
        save_rules_cache(rules_cache)
        print(f"   已保存 {len(rules_cache)} 条 rules 缓存", file=sys.stderr)
    
    # 输出
    if args.json:
        output = {
            "timestamp": datetime.now().isoformat(),
            "total": len(markets),
            "markets": markets,
        }
        print(json.dumps(output, indent=2, default=str))
    else:
        print(format_report(markets))


if __name__ == "__main__":
    main()
