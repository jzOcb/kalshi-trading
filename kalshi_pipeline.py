#!/usr/bin/env python3
"""
kalshi_pipeline - Kalshi 完整分析流水线

功能：
    - 从 watchlist 获取市场
    - 快速筛选候选
    - 深度研究 (MarketResearcherV2)
    - Nowcast 数据获取
    - 置信度计算
    - 仓位建议
    - 格式化报告

用法：
    python kalshi_pipeline.py                    # 运行完整流水线
    python kalshi_pipeline.py --dry-run          # 只列出候选
    python kalshi_pipeline.py --top 5            # 只分析前 5 个
    python kalshi_pipeline.py --notify           # 发送 Telegram 通知
    
依赖：
    - market_researcher_v2.py
    - nowcast_fetcher.py
    - source_detector.py
    - position_calculator.py
"""

import os
import sys
import json
import time
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import requests
except ImportError:
    print("Error: requests module required", file=sys.stderr)
    sys.exit(1)

from source_detector import detect_sources
from market_researcher_v2 import MarketResearcherV2
from nowcast_fetcher import NowcastFetcher
from market_validator import classify_market, get_checklist_prompt, validate_output, enforce_output

API_BASE = "https://api.elections.kalshi.com/trade-api/v2"
WATCHLIST_FILE = Path(__file__).parent / "data" / "watchlist_series.json"
RESULTS_FILE = Path(__file__).parent / "data" / "pipeline_results.json"

# 置信度分级 (动态仓位由 position_calculator 计算)
CONFIDENCE_THRESHOLDS = {
    "HIGH": {"z_min": 1.0, "tier_max": 1},
    "MEDIUM": {"z_min": 0.5, "tier_max": 2},
    "LOW": {"z_min": 0.0, "tier_max": 9},
}

# 动态仓位计算器 (懒加载)
_position_calculator = None

def get_position_calculator():
    """获取仓位计算器实例"""
    global _position_calculator
    if _position_calculator is None:
        from position_calculator import PositionCalculator
        _position_calculator = PositionCalculator()
    return _position_calculator


def load_watchlist() -> List[str]:
    """加载 watchlist series"""
    try:
        if WATCHLIST_FILE.exists():
            with open(WATCHLIST_FILE) as f:
                data = json.load(f)
            return data.get("series", [])
    except Exception as e:
        print(f"⚠️ 加载 watchlist 失败: {e}", file=sys.stderr)
    return []


def fetch_markets_by_series(series: str) -> List[Dict]:
    """获取特定 series 的市场"""
    markets = []
    cursor = None
    
    for page in range(10):
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
            
            time.sleep(0.15)
        except Exception as e:
            break
    
    return markets


def quick_filter(markets: List[Dict], min_volume: int = 100) -> List[Dict]:
    """
    快速筛选候选
    
    条件:
    - 价格极端 (>=85 或 <=15)
    - 有流动性 (volume > min_volume)
    - Tier 1-2 (有官方数据源)
    """
    candidates = []
    
    for m in markets:
        price = m.get("last_price", 50)
        volume = m.get("volume_24h", 0) or m.get("volume", 0)
        
        # 价格不极端 → 跳过
        if not (price >= 85 or price <= 15):
            continue
        
        # 低流动性 → 跳过
        if volume < min_volume:
            continue
        
        # 检测数据源
        rules = m.get("rules_primary", "")
        title = m.get("title", "")
        result = detect_sources(rules, title)
        
        tier = result.get("research_tier", 9)
        if tier > 2:  # 只要 Tier 1-2
            continue
        
        # 添加检测结果
        m["_tier"] = tier
        m["_sources"] = result.get("sources", [])
        m["_research_method"] = result.get("research_method", "")
        
        candidates.append(m)
    
    # 按潜在收益排序 (价格越极端收益越高)
    candidates.sort(key=lambda x: min(x.get("last_price", 50), 100 - x.get("last_price", 50)))
    
    return candidates


def calculate_annualized_return(price: int, days: int) -> float:
    """计算年化收益率"""
    if price <= 0 or price >= 100 or days <= 0:
        return 0.0
    
    # 假设预测正确
    cost = min(price, 100 - price)
    profit = 100 - cost
    profit_pct = (profit - cost) / cost
    annualized = profit_pct * (365 / days) * 100
    return round(annualized, 1)


def extract_threshold(title: str) -> Optional[float]:
    """从标题提取阈值"""
    # "Will real GDP increase by more than 2.0%..." → 2.0
    # "Will CPI increase by more than 0.3%..." → 0.3
    # "Will the upper bound... above 4.25%..." → 4.25
    match = re.search(r'(?:more than|above|over|below|under)\s*([0-9]+\.?[0-9]*)\s*%?', title, re.IGNORECASE)
    if match:
        return float(match.group(1))
    return None


def calculate_confidence_with_nowcast(market: Dict, nowcast_data: Optional[Dict]) -> Tuple[str, Optional[Dict]]:
    """计算置信度等级 (使用 Nowcast 数据)"""
    tier = market.get("_tier", 9)
    
    if not nowcast_data:
        return "LOW", None
    
    z_score = nowcast_data.get("z_score", 0)
    
    # 高置信度条件
    if z_score >= 1.0 and tier <= 1:
        return "HIGH", nowcast_data
    elif z_score >= 0.5 and tier <= 2:
        return "MEDIUM", nowcast_data
    else:
        return "LOW", nowcast_data


def calculate_confidence(research_result: Dict) -> str:
    """计算置信度等级 (旧版，用于兼容)"""
    judgment = research_result.get("judgment", {})
    
    # 无判断 → LOW
    if not judgment:
        return "LOW"
    
    confidence = judgment.get("confidence", 0)
    tier = research_result.get("market", {}).get("_tier", 9)
    
    # 高置信度条件
    if confidence >= 0.8 and tier <= 1:
        return "HIGH"
    elif confidence >= 0.6 and tier <= 2:
        return "MEDIUM"
    else:
        return "LOW"


def format_recommendation(market: Dict, research: Dict) -> str:
    """
    格式化单个推荐
    
    必须包含:
    1. 下单链接
    2. 标的名称
    3. 推荐方向
    4. 推荐原因 (事实核查)
    5. 潜在收益
    6. 其他指标
    """
    ticker = market.get("ticker", "")
    title = market.get("title", "")
    price = market.get("last_price", 50)
    volume = market.get("volume_24h", 0) or market.get("volume", 0)
    
    # 计算天数
    close_time = market.get("close_time", "")
    days_left = 30
    if close_time:
        try:
            close_dt = datetime.fromisoformat(close_time.replace("Z", "+00:00"))
            days_left = max(1, (close_dt - datetime.now(timezone.utc)).days)
        except:
            pass
    
    # 方向和成本
    if price >= 85:
        direction = "YES"
        cost = price
    else:
        direction = "NO"
        cost = 100 - price
    
    # 收益
    ann_return = calculate_annualized_return(price, days_left)
    
    # 置信度
    confidence = calculate_confidence(research)
    conf_emoji = "🟢" if confidence == "HIGH" else "🟡" if confidence == "MEDIUM" else "🔴"
    
    # 动态计算建议仓位
    try:
        calc = get_position_calculator()
        pos_result = calc.calculate(confidence, price)
        position = calc.format_recommendation(pos_result)
    except Exception as e:
        # 降级到默认值
        position = {"HIGH": "$100-200", "MEDIUM": "$50-100", "LOW": "观望"}.get(confidence, "观望")
    
    # 数据源
    sources = market.get("_sources", [])
    sources_str = ", ".join(sources) if sources else "未知"
    
    # 推荐原因
    judgment = research.get("judgment", {})
    reason = judgment.get("reason", "需要进一步研究")
    data_points = research.get("data", [])
    
    # Spread
    yes_ask = market.get("yes_ask", 0)
    yes_bid = market.get("yes_bid", 0)
    spread = yes_ask - yes_bid if yes_ask and yes_bid else 0
    
    # 链接
    link = f"https://kalshi.com/markets/{ticker.lower()}"
    
    # 格式化输出
    lines = [
        f"{conf_emoji} {'BUY' if confidence != 'LOW' else 'WATCH'} — 置信度 {confidence}",
        "",
        f"📌 {title}",
        f"👉 {direction} @ {cost}¢",
        f"{position}",
        "",
        f"📊 {ann_return}% 年化 ({days_left}天) | spread {spread}¢ | 量 {volume//1000}K",
        "",
        f"💡 推荐原因:",
    ]
    
    # 添加 Nowcast 数据
    nowcast = market.get("_nowcast")
    if nowcast:
        nowcast_val = nowcast.get("nowcast_value")
        threshold_val = nowcast.get("threshold")
        direction = nowcast.get("direction")
        z = nowcast.get("z_score", 0)
        source = nowcast.get("source", "")
        lines.append(f"  • ✅ {source}: {nowcast_val}% vs 阈值 {threshold_val}% → {direction.upper()}")
        lines.append(f"  • 📈 z-score: {z:.2f}")
    
    # 添加其他数据点
    if data_points:
        for dp in data_points[:2]:
            source = dp.get("source", "")
            value = dp.get("value", "")
            if value:
                lines.append(f"  • ✅ {source}: {value}")
    
    lines.append(f"  • 📊 数据源: {sources_str}")
    
    if judgment.get("warning"):
        lines.append(f"  • ⚠️ {judgment['warning']}")
    
    lines.append("")
    lines.append(f"🔗 {link}")
    
    return "\n".join(lines)


def run_pipeline(top_n: int = 10, dry_run: bool = False, verbose: bool = False) -> List[Dict]:
    """
    运行完整流水线
    
    1. 加载 watchlist
    2. 获取市场数据
    3. 快速筛选
    4. 深度研究
    5. 格式化报告
    """
    print("🚀 启动 Kalshi 分析流水线", file=sys.stderr)
    
    # Step 1: 加载 watchlist
    series_list = load_watchlist()
    if not series_list:
        print("⚠️ 无 watchlist，使用默认 series", file=sys.stderr)
        series_list = ["KXGDP", "KXCPI", "KXFED"]
    
    print(f"📋 Watchlist: {len(series_list)} 个 series", file=sys.stderr)
    
    # Step 2: 获取所有市场
    all_markets = []
    for series in series_list:
        markets = fetch_markets_by_series(series)
        # 添加 rules_primary (需要单独获取)
        for m in markets:
            if not m.get("rules_primary"):
                m["rules_primary"] = ""  # 会在后面获取
        all_markets.extend(markets)
        print(f"  {series}: {len(markets)} 个市场", file=sys.stderr)
    
    print(f"📊 共 {len(all_markets)} 个市场", file=sys.stderr)
    
    # Step 3: 快速筛选
    candidates = quick_filter(all_markets)
    print(f"🎯 筛选出 {len(candidates)} 个候选", file=sys.stderr)
    
    if not candidates:
        print("❌ 无符合条件的候选", file=sys.stderr)
        return []
    
    # 只取 top N
    candidates = candidates[:top_n]
    
    if dry_run:
        print("\n📋 候选列表 (dry-run):", file=sys.stderr)
        for c in candidates:
            price = c.get("last_price", 50)
            print(f"  {c['ticker']}: {price}¢ | Tier {c.get('_tier')} | {c.get('_sources')}", file=sys.stderr)
        return candidates
    
    # Step 4: 深度研究 + Nowcast 数据
    print(f"\n🔬 深度研究 {len(candidates)} 个候选...", file=sys.stderr)
    researcher = MarketResearcherV2()
    nowcast_fetcher = NowcastFetcher()
    results = []
    
    for i, market in enumerate(candidates):
        ticker = market.get("ticker", "")
        print(f"  [{i+1}/{len(candidates)}] {ticker}...", file=sys.stderr)
        
        # 获取详细规则
        try:
            resp = requests.get(f"{API_BASE}/markets/{ticker}", timeout=15)
            if resp.status_code == 200:
                details = resp.json().get("market", {})
                market["rules_primary"] = details.get("rules_primary", "")
                market["rules_secondary"] = details.get("rules_secondary", "")
        except:
            pass
        
        # 提取 series 和阈值
        series = ticker.split("-")[0] if "-" in ticker else ticker
        threshold = extract_threshold(market.get("title", ""))
        
        # 获取 Nowcast 数据
        nowcast_data = None
        if threshold is not None:
            nowcast_data = nowcast_fetcher.get_for_market(series, threshold)
            if nowcast_data:
                market["_nowcast"] = nowcast_data
                print(f"    📊 Nowcast: {nowcast_data.get('nowcast_value')} vs {threshold} → {nowcast_data.get('direction')}", file=sys.stderr)
        
        # 研究
        research = researcher.research(market)
        
        # 用 Nowcast 数据更新置信度
        if nowcast_data:
            confidence, _ = calculate_confidence_with_nowcast(market, nowcast_data)
            if "judgment" not in research:
                research["judgment"] = {}
            research["judgment"]["confidence"] = nowcast_data.get("confidence", 0)
            research["judgment"]["z_score"] = nowcast_data.get("z_score", 0)
            research["judgment"]["nowcast_direction"] = nowcast_data.get("direction")
        
        results.append({
            "market": market,
            "research": research,
            "nowcast": nowcast_data,
        })
        
        time.sleep(0.3)
    
    # Step 5: 生成报告
    print("\n" + "=" * 60)
    print("📊 KALSHI 每日报告")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)
    
    # 5a: 持仓分析
    try:
        from portfolio_analysis import main as portfolio_main
        import io
        import contextlib
        
        # 捕获 portfolio_analysis 输出
        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            portfolio_main()
        portfolio_output = f.getvalue().strip()
        
        if portfolio_output:
            print("\n" + portfolio_output)
            print("\n" + "-" * 40)
    except Exception as e:
        print(f"\n⚠️ 持仓分析跳过: {e}")
    
    # 5b: 新机会
    print("\n🎯 新机会")
    
    for r in results:
        market = r["market"]
        research = r["research"]
        
        recommendation = format_recommendation(market, research)
        print("\n" + recommendation)
        print("\n" + "-" * 40)
    
    # 保存结果
    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_FILE, "w") as f:
        json.dump({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "results": [
                {
                    "ticker": r["market"].get("ticker"),
                    "confidence": calculate_confidence(r["research"]),
                    "direction": "YES" if r["market"].get("last_price", 50) >= 85 else "NO",
                }
                for r in results
            ]
        }, f, indent=2)
    
    return results


def send_telegram(message: str) -> bool:
    """发送 Telegram 通知"""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID") or os.environ.get("CHAT_ID")
    
    if not bot_token or not chat_id:
        print("⚠️ Telegram 凭证未配置 (需要 TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID)", file=sys.stderr)
        return False
    
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        resp = requests.post(url, data={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "",  # 纯文本
        }, timeout=15)
        
        if resp.status_code == 200:
            print("✅ Telegram 通知已发送", file=sys.stderr)
            return True
        else:
            print(f"⚠️ Telegram API 错误: {resp.status_code}", file=sys.stderr)
            return False
    except Exception as e:
        print(f"⚠️ Telegram 发送失败: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="Kalshi 完整分析流水线")
    parser.add_argument("--top", type=int, default=5, help="分析前 N 个候选")
    parser.add_argument("--dry-run", action="store_true", help="只筛选不研究")
    parser.add_argument("--verbose", action="store_true", help="详细输出")
    parser.add_argument("--notify", action="store_true", help="发送 Telegram 通知")
    args = parser.parse_args()
    
    results = run_pipeline(top_n=args.top, dry_run=args.dry_run, verbose=args.verbose)
    
    if args.notify and results:
        # 生成简洁通知
        lines = ["📊 Kalshi 分析报告", f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}", ""]
        
        for r in results:
            market = r["market"]
            nowcast = r.get("nowcast")
            
            ticker = market.get("ticker", "")
            price = market.get("last_price", 50)
            direction = "YES" if price >= 85 else "NO"
            cost = min(price, 100 - price)
            tier = market.get("_tier", 9)
            
            # 置信度
            if nowcast and nowcast.get("z_score", 0) >= 1.0 and tier <= 1:
                conf = "🟢 HIGH"
            elif nowcast and nowcast.get("z_score", 0) >= 0.5 and tier <= 2:
                conf = "🟡 MEDIUM"
            else:
                conf = "🔴 LOW"
            
            title = market.get("title", "")[:60]
            link = f"https://kalshi.com/markets/{ticker.lower()}"
            
            lines.append(f"{conf}")
            lines.append(f"📌 {title}...")
            lines.append(f"👉 {direction} @ {cost}¢")
            if nowcast:
                lines.append(f"📊 z={nowcast.get('z_score', 0):.1f} | {nowcast.get('direction', '?').upper()}")
            lines.append(f"🔗 {link}")
            lines.append("")
        
        message = "\n".join(lines)
        send_telegram(message)


if __name__ == "__main__":
    main()
