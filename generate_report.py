#!/usr/bin/env python3
"""
Kalshi 短期市场完整分析报告生成器 v2

基于 z-score 信号强度框架：
- z = (nowcast - threshold) / σ
- |z| < 0.5 → 无信号 (噪音)
- |z| >= 0.5 → 有信号
- edge > 5¢ + 信号 → 推荐

用法:
    python3 generate_report.py           # 生成报告
    python3 generate_report.py --days 90 # 指定天数
"""

import os
import sys
import argparse
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
from math import erf, sqrt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from source_detector import detect_sources, get_tier_label

API_BASE = "https://api.elections.kalshi.com/trade-api/v2"

# 市场参数
MARKET_PARAMS = {
    "GDP": {
        "sigma": 1.0,  # pp, 基于历史回测
        "bias": 0.3,   # pp, GDPNow 系统性高估
        "tx_cost": 5,  # cents
    },
    "CPI": {
        "sigma": 0.15,  # %, Cleveland Fed 历史误差 (待验证)
        "bias": 0.0,
        "tx_cost": 5,
    },
    "FED": {
        "sigma": 0.25,  # %, 利率预测误差
        "bias": 0.0,
        "tx_cost": 5,
    },
}

# 所有经济类 series
ECON_SERIES = [
    "KXGDP", "KXCPI", "KXFED", "KXRATECUTCOUNT", "KXFOMC",
    "KXBTC", "KXETH", "KXSHUTDOWN", "KXDEBT", "KXTARIFF",
]


def norm_cdf(x: float) -> float:
    """标准正态分布 CDF"""
    return 0.5 * (1 + erf(x / sqrt(2)))


def calculate_signal(nowcast: float, threshold: float, sigma: float, bias: float = 0) -> Dict:
    """
    计算 z-score 和信号强度
    
    Args:
        nowcast: 预测值 (e.g., GDPNow = 3.1%)
        threshold: 市场阈值 (e.g., 2.5%)
        sigma: 预测误差标准差
        bias: 系统性偏差 (正=高估)
    
    Returns:
        {z_score, signal_strength, p_yes, fair_yes, fair_no}
    """
    # 调整偏差
    adjusted_nowcast = nowcast - bias
    
    # z-score: 预测值高于阈值多少个标准差
    z = (adjusted_nowcast - threshold) / sigma
    
    # 信号强度
    abs_z = abs(z)
    if abs_z < 0.5:
        signal = "NO_SIGNAL"
    elif abs_z < 1.0:
        signal = "WEAK"
    elif abs_z < 2.0:
        signal = "MODERATE"
    else:
        signal = "STRONG"
    
    # 概率和公平价
    p_yes = norm_cdf(z)
    fair_yes = int(p_yes * 100)
    fair_no = 100 - fair_yes
    
    return {
        "z_score": z,
        "signal": signal,
        "p_yes": p_yes,
        "fair_yes": fair_yes,
        "fair_no": fair_no,
    }


def calculate_edge(signal_data: Dict, market_price: int, side: str, tx_cost: int = 5) -> Dict:
    """
    计算 edge 和交易建议
    
    Args:
        signal_data: calculate_signal() 的返回值
        market_price: 市场 YES 价格 (cents)
        side: 'YES' or 'NO'
        tx_cost: 交易成本 (cents)
    
    Returns:
        {gross_edge, net_edge, position_size, recommendation}
    """
    fair_yes = signal_data["fair_yes"]
    fair_no = signal_data["fair_no"]
    signal = signal_data["signal"]
    z = signal_data["z_score"]
    
    if side == "YES":
        gross_edge = fair_yes - market_price
    else:  # NO
        market_no = 100 - market_price
        gross_edge = fair_no - market_no
    
    net_edge = gross_edge - tx_cost
    
    # 决策逻辑
    if signal == "NO_SIGNAL":
        rec = "SKIP (噪音)"
        position = 0
    elif net_edge <= 0:
        rec = "SKIP (无edge)"
        position = 0
    elif net_edge < 5:
        rec = "⚠️ 小仓"
        position = 0.25
    elif net_edge < 10:
        rec = "✅ 中仓"
        position = 0.5
    else:
        rec = "⭐ 重仓"
        position = 1.0
    
    return {
        "gross_edge": gross_edge,
        "net_edge": net_edge,
        "position": position,
        "recommendation": rec,
    }


def fetch_markets(max_days: int = 120) -> List[Dict]:
    """获取所有短期市场"""
    markets = []
    cutoff = datetime.now() + timedelta(days=max_days)
    
    for series in ECON_SERIES:
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
                
                exp = datetime.fromisoformat(exp_str.replace("Z", "+00:00")).replace(tzinfo=None)
                days = (exp - datetime.now()).days
                
                if exp > cutoff or days < 0:
                    continue
                
                # 流动性检查
                volume = m.get("volume_24h", 0) or m.get("volume", 0) or 0
                oi = m.get("open_interest", 0) or 0
                if volume < 5 and oi < 10:
                    continue
                
                # 检测数据源
                title = m.get("title", "")
                detection = detect_sources("", title)
                
                # 提取阈值
                ticker = m.get("ticker", "")
                threshold = None
                if "-T" in ticker:
                    try:
                        threshold = float(ticker.split("-T")[1])
                    except:
                        pass
                
                markets.append({
                    "ticker": ticker,
                    "title": title,
                    "price": m.get("last_price", 50),
                    "yes_bid": m.get("yes_bid", 0),
                    "yes_ask": m.get("yes_ask", 100),
                    "volume_24h": volume,
                    "open_interest": oi,
                    "days": days,
                    "exp_date": exp.strftime("%Y-%m-%d"),
                    "series": series,
                    "threshold": threshold,
                    "verifiable": detection["verifiable"],
                    "source": detection["sources"][0] if detection["sources"] else "Unknown",
                    "tier": detection["research_tier"],
                })
        except Exception as e:
            print(f"Error {series}: {e}", file=sys.stderr)
    
    return markets


def fetch_gdpnow() -> Optional[float]:
    """获取 GDPNow 预测值"""
    try:
        # 使用重定向后的 URL
        resp = requests.get("https://www.atlantafed.org/research-and-data/data/gdpnow", timeout=10)
        import re
        
        # 匹配 "3.1%" 后面跟着 "Latest GDPNow"
        # 页面格式: "3.1%\n\n Latest GDPNow Estimate"
        match = re.search(r'(\d+\.\d+)%\s*\n\s*Latest GDPNow', resp.text)
        if match:
            return float(match.group(1))
        
        # 备用: 匹配独立的百分比 (在合理范围内)
        matches = re.findall(r'(\d+\.\d+)%', resp.text)
        for m in matches:
            val = float(m)
            if 0 < val < 10:  # GDP 增长率在 0-10% 范围
                return val
    except:
        pass
    return None


def generate_report(markets: List[Dict], gdpnow: Optional[float]):
    """生成完整报告"""
    
    print("=" * 80)
    print("📊 KALSHI 短期市场分析报告 (z-score 框架)")
    print(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')} EST")
    print("=" * 80)
    print()
    print("📐 决策框架:")
    print("   z = (nowcast - threshold) / σ")
    print("   |z| < 0.5 → 无信号 (噪音)")
    print("   |z| >= 0.5 + edge > 5¢ → 有机会")
    print("=" * 80)
    
    # GDP 市场
    gdp_markets = [m for m in markets if m["series"] == "KXGDP"]
    if gdp_markets and gdpnow:
        params = MARKET_PARAMS["GDP"]
        
        print("\n" + "─" * 80)
        print("## 🏦 GDP 市场 (Q1 2026)")
        print("─" * 80)
        print(f"📊 GDPNow: {gdpnow}%")
        print(f"📐 σ = {params['sigma']}pp, bias = +{params['bias']}pp")
        print(f"🔗 https://www.atlantafed.org/cqer/research/gdpnow")
        print()
        
        print(f"{'Ticker':<25} {'阈值':>6} {'z':>6} {'信号':<10} {'YES市场':>7} {'YES公平':>7} {'NO公平':>6} {'推荐':<15}")
        print("-" * 95)
        
        recommendations = []
        
        for m in sorted(gdp_markets, key=lambda x: -(x["threshold"] or 0)):
            if m["threshold"] is None:
                continue
            
            signal_data = calculate_signal(
                gdpnow, m["threshold"], 
                params["sigma"], params["bias"]
            )
            
            # 检查 YES 和 NO 两个方向
            yes_edge = calculate_edge(signal_data, m["price"], "YES", params["tx_cost"])
            no_edge = calculate_edge(signal_data, m["price"], "NO", params["tx_cost"])
            
            # 选择更好的方向
            if yes_edge["net_edge"] > no_edge["net_edge"]:
                best_side = "YES"
                best_edge = yes_edge
            else:
                best_side = "NO"
                best_edge = no_edge
            
            z = signal_data["z_score"]
            signal = signal_data["signal"]
            fair_yes = signal_data["fair_yes"]
            fair_no = signal_data["fair_no"]
            
            rec_str = f"{best_side} {best_edge['recommendation']}"
            
            print(f"{m['ticker']:<25} >{m['threshold']}%{'':<2} {z:>+5.1f} {signal:<10} {m['price']:>6}¢ {fair_yes:>6}¢ {fair_no:>5}¢ {rec_str:<15}")
            
            if best_edge["position"] > 0:
                recommendations.append({
                    "ticker": m["ticker"],
                    "side": best_side,
                    "price": m["price"] if best_side == "YES" else 100 - m["price"],
                    "edge": best_edge["gross_edge"],
                    "z": z,
                    "rec": best_edge["recommendation"],
                })
        
        print()
        print("🔗 https://kalshi.com/markets/kxgdp")
        
        if recommendations:
            print("\n### ✅ GDP 推荐:")
            for r in recommendations:
                print(f"   • {r['ticker']} {r['side']} @ {r['price']}¢ (z={r['z']:+.1f}, edge={r['edge']:+.0f}¢)")
    
    # CPI 市场
    cpi_markets = [m for m in markets if m["series"] == "KXCPI"]
    if cpi_markets:
        print("\n" + "─" * 80)
        print("## 📈 CPI 市场")
        print("─" * 80)
        print("📊 数据源: BLS")
        print("🔬 研究方法: Cleveland Fed Inflation Nowcast")
        print("⚠️ 需要获取 Cleveland Fed 数据才能计算 z-score")
        print()
        
        # 按月份分组
        by_month = {}
        for m in cpi_markets:
            parts = m["ticker"].split("-")
            month = parts[1][:5] if len(parts) > 1 else "Unknown"
            if month not in by_month:
                by_month[month] = []
            by_month[month].append(m)
        
        for month in sorted(by_month.keys()):
            markets_in_month = by_month[month]
            days = markets_in_month[0]["days"]
            print(f"\n### {month} CPI ({days}天后)")
            print(f"{'Ticker':<25} {'条件':<12} {'价格':>6} {'OI':>6}")
            print("-" * 55)
            
            for m in sorted(markets_in_month, key=lambda x: -(x["threshold"] or 0)):
                t = m["threshold"]
                t_str = f">{t}%" if t else "?"
                print(f"{m['ticker']:<25} MoM {t_str:<6} {m['price']:>5}¢ {m['open_interest']:>6}")
        
        print()
        print("🔗 https://kalshi.com/markets/kxcpi")
    
    # 推荐汇总
    print("\n" + "=" * 80)
    print("## 📋 决策总结")
    print("=" * 80)
    
    print("""
### 框架参数
| 市场 | σ | bias | 最小信号 (0.5σ) | 交易成本 |
|------|---|------|-----------------|----------|
| GDP | 1.0pp | +0.3pp | 0.5pp | 5¢ |
| CPI | 0.15% | 0 | 0.075% | 5¢ |

### 决策流程
1. 计算 z = (nowcast - bias - threshold) / σ
2. |z| < 0.5 → SKIP (噪音)
3. 计算公平价: P(YES) = Φ(z)
4. 计算 edge = 公平价 - 市场价
5. net_edge = edge - 5¢
6. net_edge > 0 → 交易，仓位 = f(edge)

### 来源
• GDPNow: https://www.atlantafed.org/cqer/research/gdpnow
• CPI Nowcast: https://www.clevelandfed.org/indicators-and-data/inflation-nowcasting
""")
    
    print("=" * 80)
    print("📋 报告生成完毕")
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="Kalshi 短期市场分析报告 (z-score 框架)")
    parser.add_argument("--days", type=int, default=120, help="最大到期天数")
    args = parser.parse_args()
    
    print("🔍 获取市场数据...", file=sys.stderr)
    markets = fetch_markets(max_days=args.days)
    print(f"   找到 {len(markets)} 个符合条件的市场", file=sys.stderr)
    
    print("📊 获取 GDPNow...", file=sys.stderr)
    gdpnow = fetch_gdpnow()
    if gdpnow:
        print(f"   GDPNow: {gdpnow}%", file=sys.stderr)
    else:
        print("   ⚠️ 无法获取 GDPNow，使用默认值 3.1%", file=sys.stderr)
        gdpnow = 3.1
    
    generate_report(markets, gdpnow)


if __name__ == "__main__":
    main()
