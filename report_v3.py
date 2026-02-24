#!/usr/bin/env python3
"""
report_v3 - Kalshi 报告 v3 (新格式)

格式：
1. Hero 数字 (总资产, 现金, 持仓)
2. 今日结算 (当天到期的持仓)
3. 持仓分析 (简化单行格式)
4. 汇总 (P&L)

用法：
    python report_v3.py              # 生成报告
    python report_v3.py --json       # JSON 输出
"""
import warnings; warnings.filterwarnings("ignore", message="urllib3 v2")

import sys
import os
import re
from datetime import datetime, date
from zoneinfo import ZoneInfo
from typing import Optional

# Add current dir to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from get_positions import ACCOUNTS, get_positions, get_balance

ET = ZoneInfo("America/New_York")


def get_settlement_date(ticker: str, close_time: str) -> Optional[date]:
    """Extract settlement date from ticker (for weather) or close_time"""
    # Weather markets: ticker contains the date like KXHIGHLAX-26FEB24-B69.5
    # Pattern: -YYMMMDD- where DD is the day (01-31)
    # Only apply this to weather tickers (KXHIGH)
    if 'KXHIGH' in ticker:
        match = re.search(r'-(\d{2})([A-Z]{3})(\d{2})-B', ticker)  # Must end with -B for bracket
        if match:
            year = 2000 + int(match.group(1))
            month_str = match.group(2)
            day = int(match.group(3))
            months = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,
                      'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
            month = months.get(month_str, 1)
            return date(year, month, day)
    
    # Fallback to close_time for non-weather markets
    if not close_time:
        return None
    try:
        dt = datetime.fromisoformat(close_time.replace('Z', '+00:00'))
        return dt.date()
    except:
        return None


def days_until(d: date) -> int:
    """Days until a date"""
    return (d - date.today()).days


def format_days(days: int) -> str:
    """Format days until settlement"""
    if days <= 0:
        return "今天"
    elif days == 1:
        return "明天"
    else:
        return f"{days}天"


def short_name(ticker: str, title: str = "") -> str:
    """Get short readable name from ticker"""
    
    # Weather - extract city and bracket
    if 'KXHIGH' in ticker:
        city_match = re.search(r'KXHIGH[T]?([A-Z]+)-', ticker)
        bracket_match = re.search(r'-B(\d+\.?\d*)', ticker)
        if city_match and bracket_match:
            city = city_match.group(1)
            low = float(bracket_match.group(1))
            return f"{city} {int(low)}-{int(low)+1}°F"
    
    # Fed mentions
    if 'FEDMENTION' in ticker:
        if 'QE' in ticker:
            return "Fed QE"
        if 'STAG' in ticker:
            return "Fed Stagflation"
    
    # Government shutdown
    if 'GOVTSHUT' in ticker:
        return "Shutdown 50天"
    
    # Fallback
    parts = ticker.split('-')
    return parts[0].replace('KX', '')[:12]


def generate_report() -> str:
    """Generate the v3 format report"""
    now = datetime.now(ET)
    today = date.today()
    
    lines = []
    lines.append(f"💰 **Kalshi · {now.strftime('%b %d, %I:%M %p')}**")
    lines.append("")
    
    total_balance = 0
    total_portfolio = 0
    all_positions = []
    
    for name, acct in ACCOUNTS.items():
        try:
            bal = get_balance(acct['api_key'], acct['key_path'])
            balance_cents = bal.get('balance', 0)
            balance = balance_cents / 100
            
            positions = get_positions(acct['api_key'], acct['key_path'], acct['label'])
            portfolio = sum(p.get('exposure', 0) for p in positions) / 100
            
            total_balance += balance
            total_portfolio += portfolio
            
            for p in positions:
                p['account_name'] = name
                all_positions.append(p)
        except Exception as e:
            lines.append(f"⚠️ {name}: {e}")
    
    total = total_balance + total_portfolio
    cash_pct = (total_balance / total * 100) if total > 0 else 0
    
    # Hero numbers
    lines.append(f"```")
    lines.append(f"${total:.2f} 总资产")
    lines.append(f"├─ 现金: ${total_balance:.2f} ({cash_pct:.0f}%)")
    lines.append(f"└─ 持仓: ${total_portfolio:.2f}")
    lines.append(f"```")
    lines.append("")
    
    # Separate today's settlements
    today_positions = []
    other_positions = []
    
    for p in all_positions:
        ticker = p.get('ticker', '')
        close_time = p.get('close_time', '')
        settlement = get_settlement_date(ticker, close_time)
        days = days_until(settlement) if settlement else 999
        p['_days'] = days
        p['_settlement'] = settlement
        
        if days <= 0:
            today_positions.append(p)
        else:
            other_positions.append(p)
    
    if today_positions:
        lines.append("🔔 **今日结算**")
        lines.append("```")
        for p in today_positions:
            ticker = p.get('ticker', '')
            title = p.get('title', '')
            name = short_name(ticker, title)
            
            position = p.get('position', 0)
            qty = abs(position)
            side = "NO" if position < 0 else "YES"
            
            # Current price (from yes_bid/yes_ask)
            if side == "NO":
                current = int((1 - p.get('yes_ask', 0)) * 100)
            else:
                current = int(p.get('yes_bid', 0) * 100)
            
            status = "✅" if current > 70 else "👀"
            
            lines.append(f"{name:<14} {side}×{qty}  当前{current}¢ {status}")
        lines.append("```")
        lines.append("")
    
    # Position analysis
    lines.append("📊 **持仓分析**")
    lines.append("```")
    
    # Sort by days until settlement
    all_sorted = sorted(all_positions, key=lambda p: p.get('_days', 999))
    
    for p in all_sorted:
        ticker = p.get('ticker', '')
        title = p.get('title', '')
        name = short_name(ticker, title)
        
        position = p.get('position', 0)
        qty = abs(position)
        side = "NO" if position < 0 else "YES"
        
        # Current price
        if side == "NO":
            current_price = 1 - p.get('yes_ask', 0)
        else:
            current_price = p.get('yes_bid', 0)
        
        # Win probability (simplified: current price is market's view)
        win_prob = int(current_price * 100)
        
        # EV calculation (simplified)
        exposure_cents = p.get('exposure', 0)
        potential_win = qty * 100 - exposure_cents  # if we win, get $1 per contract minus cost
        ev = (win_prob / 100) * potential_win - ((100 - win_prob) / 100) * exposure_cents
        ev_dollars = ev / 100
        
        days = p.get('_days', 999)
        days_str = format_days(days)
        
        sleep = " 💤" if days > 30 else ""
        
        line = f"{name:<14} {side}×{qty} | 胜率{win_prob}% | EV {'+' if ev_dollars >= 0 else ''}{ev_dollars:.2f} | {days_str}{sleep}"
        
        lines.append(line)
    
    lines.append("```")
    
    return "\n".join(lines)


if __name__ == "__main__":
    report = generate_report()
    print(report)
