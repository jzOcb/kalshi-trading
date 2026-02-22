#!/usr/bin/env python3
"""
insight_logger - Kalshi 交易洞察自动记录

功能：
    - 从结算数据提取模式
    - 写入 memory/insights/
    - 重大教训同步到 MEMORY.md

用法：
    python insight_logger.py                    # 分析今日结算
    python insight_logger.py --date 2026-02-20  # 分析指定日期
"""

import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
MEMORY_DIR = Path.home() / "clawd" / "memory"
INSIGHTS_DIR = MEMORY_DIR / "insights"
LESSONS_FILE = MEMORY_DIR / "lessons" / "operational-lessons.jsonl"

SHADOW_LOG = SCRIPT_DIR.parent / "btc-arbitrage" / "data" / "weather_shadow_trades.jsonl"
SETTLED_FILE = SCRIPT_DIR / "settled_trades.json"


def load_recent_settlements(days: int = 7) -> list:
    """Load recently settled trades."""
    if not SETTLED_FILE.exists():
        return []
    
    with open(SETTLED_FILE) as f:
        data = json.load(f)
    
    cutoff = datetime.now() - timedelta(days=days)
    recent = []
    
    for ticker, info in data.items():
        settled_at = info.get("settled_at", "")
        if settled_at:
            try:
                dt = datetime.fromisoformat(settled_at.replace("Z", "+00:00"))
                if dt.replace(tzinfo=None) > cutoff:
                    recent.append({
                        "ticker": ticker,
                        "result": info.get("result"),
                        "pnl_cents": info.get("pnl_cents", 0),
                        "settled_at": settled_at
                    })
            except:
                pass
    
    return recent


def load_shadow_trades(days: int = 7) -> list:
    """Load shadow trades from weather bot."""
    if not SHADOW_LOG.exists():
        return []
    
    cutoff = datetime.now() - timedelta(days=days)
    trades = []
    
    with open(SHADOW_LOG) as f:
        for line in f:
            try:
                trade = json.loads(line.strip())
                ts = trade.get("timestamp", "")
                if ts:
                    # Handle timezone-aware timestamps
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    dt_naive = dt.replace(tzinfo=None)
                    if dt_naive > cutoff:
                        # Map shadow fields to common format
                        pnl = 100 if trade.get("shadow_outcome") == "win" else -50
                        trade["pnl"] = pnl
                        trade["ticker"] = trade.get("ticker", "")
                        trades.append(trade)
            except Exception as e:
                pass
    
    return trades


def extract_patterns(trades: list) -> dict:
    """Extract patterns from trades."""
    if not trades:
        return {}
    
    patterns = {
        "total": len(trades),
        "wins": 0,
        "losses": 0,
        "total_pnl": 0,
        "by_type": {},
        "by_city": {},
        "lessons": []
    }
    
    for t in trades:
        pnl = t.get("pnl_cents", 0) or t.get("pnl", 0)
        if pnl > 0:
            patterns["wins"] += 1
        elif pnl < 0:
            patterns["losses"] += 1
        patterns["total_pnl"] += pnl
        
        # Categorize by type
        ticker = t.get("ticker", "")
        if "HIGHNY" in ticker or "HIGHLA" in ticker:
            t_type = "weather"
        elif "GDP" in ticker or "CPI" in ticker:
            t_type = "economic"
        else:
            t_type = "other"
        
        if t_type not in patterns["by_type"]:
            patterns["by_type"][t_type] = {"count": 0, "pnl": 0}
        patterns["by_type"][t_type]["count"] += 1
        patterns["by_type"][t_type]["pnl"] += pnl
        
        # City for weather
        if t_type == "weather":
            city = "unknown"
            for c in ["NYC", "LAX", "CHI", "BOS", "MIA", "PHX", "SEA", "SFO", "AUS", "DEN", "LAS"]:
                if c in ticker:
                    city = c
                    break
            if city not in patterns["by_city"]:
                patterns["by_city"][city] = {"count": 0, "pnl": 0, "wins": 0}
            patterns["by_city"][city]["count"] += 1
            patterns["by_city"][city]["pnl"] += pnl
            if pnl > 0:
                patterns["by_city"][city]["wins"] += 1
    
    # Generate lessons
    win_rate = patterns["wins"] / patterns["total"] if patterns["total"] > 0 else 0
    
    if win_rate < 0.5:
        patterns["lessons"].append(f"Win rate {win_rate:.1%} below 50% - review strategy")
    
    for city, stats in patterns["by_city"].items():
        city_wr = stats["wins"] / stats["count"] if stats["count"] > 0 else 0
        if stats["count"] >= 3 and city_wr < 0.4:
            patterns["lessons"].append(f"{city}: {city_wr:.0%} WR over {stats['count']} trades - consider excluding")
    
    return patterns


def write_insight(date: str, patterns: dict):
    """Write insight to memory/insights/."""
    INSIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    
    month = date[:7]  # YYYY-MM
    insight_file = INSIGHTS_DIR / f"{month}.md"
    
    entry = f"""
## {date} Kalshi 交易洞察

- **总交易**: {patterns['total']} | **胜率**: {patterns['wins']}/{patterns['total']} ({patterns['wins']/patterns['total']*100:.0f}%)
- **P&L**: ${patterns['total_pnl']/100:.2f}
"""
    
    if patterns["by_type"]:
        entry += "\n**按类型:**\n"
        for t, stats in patterns["by_type"].items():
            entry += f"- {t}: {stats['count']} trades, ${stats['pnl']/100:.2f}\n"
    
    if patterns["lessons"]:
        entry += "\n**教训:**\n"
        for lesson in patterns["lessons"]:
            entry += f"- ⚠️ {lesson}\n"
    
    # Append to file
    with open(insight_file, "a") as f:
        f.write(entry + "\n")
    
    print(f"✅ Insight written to {insight_file}")
    return insight_file


def log_lesson(lesson: str, category: str = "trading"):
    """Log lesson to operational-lessons.jsonl."""
    LESSONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    entry = {
        "date": datetime.now().isoformat(),
        "category": category,
        "lesson": lesson,
        "source": "kalshi-insight-logger"
    }
    
    with open(LESSONS_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")
    
    print(f"📝 Lesson logged: {lesson[:50]}...")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()
    
    print(f"📊 Analyzing trades from last {args.days} days...")
    
    # Load trades from both sources
    settlements = load_recent_settlements(args.days)
    shadow = load_shadow_trades(args.days)
    
    all_trades = settlements + shadow
    
    if not all_trades:
        print("No trades found")
        return
    
    print(f"Found {len(all_trades)} trades")
    
    # Extract patterns
    patterns = extract_patterns(all_trades)
    
    # Write insight
    write_insight(args.date, patterns)
    
    # Log critical lessons
    for lesson in patterns.get("lessons", []):
        log_lesson(lesson)
    
    print("✅ Done")


if __name__ == "__main__":
    main()
