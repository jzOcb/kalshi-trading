#!/usr/bin/env python3
"""
sync_positions - 同步 Kalshi 账户仓位

功能：
    - 从多个 Kalshi 账户获取仓位
    - 更新 positions.json 供报告系统使用
    - 支持主账户和天气账户

用法：
    python sync_positions.py
    
依赖：
    - kalshi.client.KalshiClient
"""
import warnings; warnings.filterwarnings("ignore", message="urllib3 v2")

import json
import os
import sys

# Add path for kalshi module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../btc-arbitrage/src"))

from kalshi.client import KalshiClient

POSITIONS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "positions.json")


def fetch_all_positions():
    """Fetch positions from both accounts."""
    all_positions = []
    
    accounts = [
        ("main", "主账号"),
        ("weather", "副账号"),
    ]
    
    for account_id, account_label in accounts:
        try:
            client = KalshiClient(account=account_id)
            result = client.get_positions()
            positions = result.get("market_positions", [])
            
            for p in positions:
                ticker = p.get("ticker", "")
                # position: positive = YES, negative = NO
                position = p.get("position", 0)
                
                if position == 0:
                    continue
                
                if position > 0:
                    side = "YES"
                    qty = position
                else:
                    side = "NO"
                    qty = abs(position)
                
                # Calculate average entry price from total_traded / qty
                total_traded = p.get("total_traded", 0)  # in cents
                avg_price = int(total_traded / qty) if qty > 0 else 0
                
                # Calculate cost for position_monitor.py compatibility
                cost = qty * avg_price / 100  # in dollars
                
                # Extract settlement date from ticker (e.g., KXGDP-26JAN30 -> 2026-01-30)
                settles = "unknown"
                try:
                    import re
                    date_match = re.search(r'-(\d{2})([A-Z]{3})(\d{2})', ticker)
                    if date_match:
                        year = "20" + date_match.group(1)
                        month_map = {"JAN":"01","FEB":"02","MAR":"03","APR":"04","MAY":"05","JUN":"06",
                                     "JUL":"07","AUG":"08","SEP":"09","OCT":"10","NOV":"11","DEC":"12"}
                        month = month_map.get(date_match.group(2), "01")
                        day = date_match.group(3)
                        settles = f"{year}-{month}-{day}"
                except:
                    pass
                
                all_positions.append({
                    "ticker": ticker,
                    "side": side,
                    "contracts": qty,
                    "entry_price": avg_price,
                    "cost": round(cost, 2),
                    "payout": qty,  # Each contract pays $1 if wins
                    "settles": settles,
                    "account": account_label,
                    "account_id": account_id,
                })
            
            print(f"✅ {account_label}: {len(positions)} positions fetched", file=sys.stderr)
            
        except Exception as e:
            print(f"❌ {account_label}: Error - {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
    
    return all_positions


def save_positions(positions):
    """Save positions to JSON file."""
    data = {
        "positions": positions,
        "updated_at": __import__("datetime").datetime.now().isoformat()
    }
    with open(POSITIONS_FILE, "w") as f:
        json.dump(data, f, indent=2)
    print(f"💾 Saved {len(positions)} positions to {POSITIONS_FILE}", file=sys.stderr)


def main():
    positions = fetch_all_positions()
    save_positions(positions)
    
    # Print summary
    print("\n📊 当前持仓:", file=sys.stderr)
    for p in positions:
        print(f"  {p['ticker']}: {p['contracts']}x {p['side']} @ {p['entry_price']}¢ ({p['account']})", file=sys.stderr)


if __name__ == "__main__":
    main()
