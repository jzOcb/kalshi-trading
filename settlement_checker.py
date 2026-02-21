#!/usr/bin/env python3
"""
settlement_checker - Kalshi 结算检查

功能：
    - Paper trading 结算验证
    - 预测 vs 实际对比
    - 生成结算报告

用法：
    python settlement_checker.py           # 检查结算
    
依赖：
    - get_positions.py
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

SCRIPT_DIR = Path(__file__).parent
TRADES_FILE = SCRIPT_DIR / "paper_trades.json"
SETTLED_FILE = SCRIPT_DIR / "settled_trades.json"  # track already-reported settlements

FLAG_FILE = Path("/tmp/kalshi_settlement_report.flag")
REPORT_FILE = Path("/tmp/kalshi_settlement_report.txt")

API_BASE = "https://api.elections.kalshi.com/trade-api/v2/markets"

def load_trades():
    with open(TRADES_FILE) as f:
        return json.load(f)["trades"]

def load_settled():
    if SETTLED_FILE.exists():
        with open(SETTLED_FILE) as f:
            return json.load(f)
    return {}

def save_settled(settled):
    with open(SETTLED_FILE, "w") as f:
        json.dump(settled, f, indent=2)

def fetch_market(ticker: str) -> dict:
    """Fetch market data from Kalshi API."""
    url = f"{API_BASE}/{ticker}"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        return resp.json().get("market", {})
    except requests.RequestException as e:
        print(f"⚠️  API error for {ticker}: {e}")
        return {}

def calc_pnl(side: str, entry_cents: int, result: str) -> tuple:
    """
    Calculate P&L per contract in cents.
    
    YES side:
      - result=yes → payout 100¢, profit = 100 - entry
      - result=no  → payout 0¢,   profit = -entry
    NO side:
      - result=no  → payout 100¢, profit = 100 - entry
      - result=yes → payout 0¢,   profit = -entry
    """
    side_upper = side.upper()
    result_lower = result.lower() if result else None
    
    if side_upper == "YES":
        won = (result_lower == "yes")
    else:  # NO
        won = (result_lower == "no")
    
    if won:
        pnl_cents = 100 - entry_cents
    else:
        pnl_cents = -entry_cents
    
    return won, pnl_cents

def check_settlements(force=False):
    trades = load_trades()
    settled_history = load_settled()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    new_settlements = []
    pending = []
    
    for trade in trades:
        ticker = trade["ticker"]
        
        # Skip already reported
        if ticker in settled_history:
            continue
        
        print(f"Checking {ticker}...", end=" ")
        market = fetch_market(ticker)
        
        if not market:
            print("API error, skipping")
            continue
        
        status = market.get("status", "unknown")
        result = market.get("result")  # "yes", "no", or None
        
        print(f"status={status}, result={result}")
        
        if status in ("settled", "finalized") and result and result in ("yes", "no"):
            won, pnl_cents = calc_pnl(trade["side"], trade["entry_cents"], result)
            settlement = {
                "ticker": ticker,
                "side": trade["side"],
                "entry_cents": trade["entry_cents"],
                "result": result,
                "won": won,
                "pnl_cents": pnl_cents,
                "settled_date": today,
                "description": trade.get("description", "")
            }
            new_settlements.append(settlement)
            settled_history[ticker] = settlement
        else:
            pending.append({
                "ticker": ticker,
                "status": status,
                "settles": trade["settles"]
            })
        
        time.sleep(0.3)  # rate limit courtesy
    
    # Generate report if we have new settlements
    if new_settlements:
        report = generate_report(new_settlements, pending)
        print("\n" + report)
        
        # Write flag + report for heartbeat
        REPORT_FILE.write_text(report)
        FLAG_FILE.write_text(f"new_settlements={len(new_settlements)}\ntime={today}")
        
        # Save settled history
        save_settled(settled_history)
        
        print(f"\n✅ Report written to {REPORT_FILE}")
        print(f"✅ Flag written to {FLAG_FILE}")
        return True
    else:
        remaining = len(pending)
        print(f"\n📋 No new settlements. {remaining} trades still pending.")
        if pending:
            for p in pending:
                print(f"   • {p['ticker']} — {p['status']} (settles {p['settles']})")
        return False

def generate_report(settlements: list, pending: list) -> str:
    lines = ["🏁 Kalshi Paper Trading 结算报告", f"📅 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}", ""]
    
    wins = 0
    losses = 0
    total_pnl = 0
    
    for s in settlements:
        ticker = s["ticker"]
        side = s["side"]
        entry = s["entry_cents"]
        result = s["result"].upper()
        won = s["won"]
        pnl = s["pnl_cents"]
        
        if won:
            wins += 1
            icon = "✅"
            pnl_str = f"+{pnl}¢/份"
        else:
            losses += 1
            icon = "❌"
            pnl_str = f"{pnl}¢/份"
        
        result_text = "赢！" if won else "输"
        lines.append(f"{icon} {ticker} {side}@{entry}¢ → 结果{result} → {result_text} {pnl_str}")
        total_pnl += pnl
    
    total = wins + losses
    win_rate = (wins / total * 100) if total > 0 else 0
    pnl_dollars = total_pnl / 100
    pnl_sign = "+" if pnl_dollars >= 0 else ""
    
    lines.append("")
    lines.append(f"总计: {wins}胜/{losses}负 | 胜率{win_rate:.0f}% | 净P&L: {pnl_sign}${abs(pnl_dollars):.2f}/份")
    
    if pending:
        lines.append("")
        lines.append(f"⏳ 还有 {len(pending)} 笔待结算:")
        for p in pending:
            lines.append(f"   • {p['ticker']} (settles {p['settles']})")
    
    return "\n".join(lines)

if __name__ == "__main__":
    force = "--force" in sys.argv
    check_settlements(force=force)
