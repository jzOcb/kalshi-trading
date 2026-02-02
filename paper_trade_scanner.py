#!/usr/bin/env python3
"""
Kalshi Paper Trade Scanner - $200 Capital
Finds opportunities, sizes positions appropriately, records as paper trades.
"""

import json
import os
import sys
from datetime import datetime, timezone
from notify import scan as run_scanner

TRADES_FILE = os.path.join(os.path.dirname(__file__), "trades.json")
MAX_TOTAL = 200
MAX_PER_TICKER = 75
MAX_PER_SERIES = 120
TARGET_POSITION_SIZE = 40  # Default position size

def load_trades():
    """Load trades"""
    with open(TRADES_FILE) as f:
        return json.load(f)

def save_trades(data):
    """Save trades"""
    with open(TRADES_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_exposure():
    """Calculate current exposure"""
    data = load_trades()
    pending = [t for t in data["trades"] if t["status"] == "PENDING"]
    
    total = sum(t.get("current_position", t["position_size"]) for t in pending)
    
    by_series = {}
    for t in pending:
        series = t["ticker"].split('-')[0]
        pos = t.get("current_position", t["position_size"])
        by_series[series] = by_series.get(series, 0) + pos
    
    by_ticker = {}
    for t in pending:
        ticker = t["ticker"]
        pos = t.get("current_position", t["position_size"])
        by_ticker[ticker] = pos
    
    return {"total": total, "by_series": by_series, "by_ticker": by_ticker}

def can_add_position(ticker, size):
    """Check if we can add this position within limits"""
    exp = get_exposure()
    series = ticker.split('-')[0]
    
    # Check total
    if exp["total"] + size > MAX_TOTAL:
        return False, f"Would exceed total (${exp['total']} + ${size} > ${MAX_TOTAL})"
    
    # Check series
    current_series = exp["by_series"].get(series, 0)
    if current_series + size > MAX_PER_SERIES:
        return False, f"Would exceed series limit for {series} (${current_series} + ${size} > ${MAX_PER_SERIES})"
    
    # Check ticker (no duplicates for initial entry)
    if ticker in exp["by_ticker"]:
        return False, f"Already have position in {ticker}"
    
    return True, "OK"

def record_paper_trade(opp):
    """Record a paper trade opportunity"""
    data = load_trades()
    
    ticker = opp["ticker"]
    side = opp["side"]
    cost = opp["cost"]
    
    # Determine position size (smaller for paper trading with $200)
    position_size = TARGET_POSITION_SIZE
    
    # Check limits
    allowed, reason = can_add_position(ticker, position_size)
    if not allowed:
        print(f"  ⚠️ SKIP {ticker}: {reason}")
        return None
    
    trade_id = len(data["trades"]) + 1
    
    trade = {
        "id": trade_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ticker": ticker,
        "title": opp["name"],
        "decision": "BUY",
        "side": side,
        "entry_price": cost,
        "position_size": position_size,
        "current_position": position_size,
        "score": 100 if opp["ann"] >= 200 else 80,
        "reasons": [
            f"Annual: {opp['ann']:.0f}%",
            f"Return: {opp['ret']:.0f}% in {opp['days']}d",
            f"Spread: {opp['spread']}¢",
            f"Volume: {opp['vol']}",
        ],
        "expiration": "unknown",  # Would need to fetch from API
        "url": f"https://kalshi.com (search {ticker})",
        "status": "PENDING",
        "result": None,
        "pnl": None,
        "settled_at": None,
        "adjustments": [],
    }
    
    data["trades"].append(trade)
    data["stats"]["total"] += 1
    data["stats"]["pending"] += 1
    
    save_trades(data)
    
    print(f"  ✅ RECORDED #{trade_id}: {ticker} - {side}@{cost}¢ (${position_size})")
    return trade_id

def scan_and_record(max_trades=5):
    """Scan for opportunities and record paper trades"""
    print("📊 Scanning Kalshi markets...")
    
    # Get current scanner output
    report = run_scanner()
    
    # Parse junk bonds from report (simplified - would need better parsing)
    print("\n🔍 Looking for junk bond opportunities...\n")
    
    # For now, manually check current exposure
    exp = get_exposure()
    
    print(f"💰 Current Exposure:")
    print(f"  Total: ${exp['total']} / ${MAX_TOTAL}")
    print(f"  Available: ${MAX_TOTAL - exp['total']}")
    print(f"  Pending trades: {len([t for t in load_trades()['trades'] if t['status'] == 'PENDING'])}")
    print()
    
    if exp['total'] >= MAX_TOTAL * 0.9:
        print("⚠️ Portfolio nearly full (>90%). Wait for settlements or exits.")
        return
    
    print("Run scanner manually to find opportunities:")
    print("  cd kalshi && python3 notify.py")
    print()
    print("Then add trades manually:")
    print("  python3 paper_trade_scanner.py add <ticker> <side> <price>")

def add_manual_trade(ticker, side, price):
    """Manually add a paper trade"""
    price = int(price)
    
    # Create opportunity object
    opp = {
        "ticker": ticker,
        "side": side.upper(),
        "cost": price,
        "name": f"Manual entry: {ticker}",
        "ret": ((100 - price) / price) * 100,
        "ann": 0,  # Would calculate
        "days": 30,  # Estimate
        "spread": 0,
        "vol": 0,
    }
    
    trade_id = record_paper_trade(opp)
    
    if trade_id:
        print(f"\n✅ Paper trade #{trade_id} recorded!")
        print(f"Run 'python3 dynamic_trader.py monitor' to track it")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        
        if cmd == "add" and len(sys.argv) >= 5:
            # add <ticker> <side> <price>
            add_manual_trade(sys.argv[2], sys.argv[3], sys.argv[4])
        elif cmd == "scan":
            scan_and_record()
        else:
            print("Usage:")
            print("  paper_trade_scanner.py scan")
            print("  paper_trade_scanner.py add <ticker> <YES|NO> <price>")
    else:
        scan_and_record()
