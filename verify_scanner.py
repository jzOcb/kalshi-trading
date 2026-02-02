#!/usr/bin/env python3
"""
Kalshi Scanner Verification System
Automatically tracks recommendations and analyzes profitability.
"""

import json
import os
from datetime import datetime, timezone, timedelta
import requests

API_BASE = "https://api.elections.kalshi.com/trade-api/v2"
TRADES_FILE = os.path.join(os.path.dirname(__file__), "trades.json")

def api_get(endpoint, params=None):
    """API request"""
    try:
        resp = requests.get(f"{API_BASE}{endpoint}", params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"⚠️ API error: {e}")
        return None

def load_trades():
    """Load trades"""
    if not os.path.exists(TRADES_FILE):
        return {"trades": [], "stats": {"total": 0, "wins": 0, "losses": 0, "pending": 0}}
    with open(TRADES_FILE) as f:
        return json.load(f)

def save_trades(data):
    """Save trades"""
    with open(TRADES_FILE, "w") as f:
        json.dump(data, f, indent=2)

def check_settlements():
    """Check if any pending trades have settled"""
    data = load_trades()
    pending = [t for t in data["trades"] if t["status"] == "PENDING"]
    
    if not pending:
        print("No pending trades to check")
        return
    
    print(f"Checking {len(pending)} pending trades...")
    updates = 0
    
    for trade in pending:
        ticker = trade["ticker"]
        
        # Fetch current market state
        market_data = api_get(f"/markets/{ticker}")
        if not market_data or "market" not in market_data:
            continue
        
        market = market_data["market"]
        status = market.get("status")
        result_value = market.get("result")
        
        # Check if settled
        if status == "closed" and result_value:
            print(f"\n🔔 Trade #{trade['id']} SETTLED: {ticker}")
            
            # Determine win/loss
            side = trade["side"]
            entry_price = trade["entry_price"]
            position = trade["position_size"]
            
            won = (side == "YES" and result_value == "yes") or (side == "NO" and result_value == "no")
            
            if won:
                pnl = position * (100 - entry_price) / 100
                result = "WIN"
                print(f"   ✅ WIN! P&L: ${pnl:.2f}")
            else:
                pnl = -position * entry_price / 100
                result = "LOSS"
                print(f"   ❌ LOSS! P&L: ${pnl:.2f}")
            
            # Update trade
            trade["status"] = "SETTLED"
            trade["result"] = result
            trade["pnl"] = pnl
            trade["settled_at"] = datetime.now(timezone.utc).isoformat()
            trade["final_price"] = 100 if won else 0
            
            # Update stats
            data["stats"]["pending"] -= 1
            if won:
                data["stats"]["wins"] += 1
            else:
                data["stats"]["losses"] += 1
            
            updates += 1
    
    if updates > 0:
        save_trades(data)
        print(f"\n✅ Updated {updates} trades")
        generate_report()
    else:
        print("No new settlements")

def generate_report():
    """Generate profitability report"""
    data = load_trades()
    stats = data["stats"]
    
    print("\n" + "="*70)
    print("📊 KALSHI SCANNER VERIFICATION REPORT")
    print("="*70)
    
    settled = [t for t in data["trades"] if t["status"] == "SETTLED"]
    pending = [t for t in data["trades"] if t["status"] == "PENDING"]
    
    print(f"\n**Overall Stats:**")
    print(f"  Total trades: {stats['total']}")
    print(f"  Settled: {len(settled)}")
    print(f"  Pending: {stats['pending']}")
    
    if len(settled) > 0:
        wins = stats['wins']
        losses = stats['losses']
        win_rate = (wins / len(settled)) * 100
        
        print(f"\n**Performance:**")
        print(f"  Wins: {wins}")
        print(f"  Losses: {losses}")
        print(f"  Win rate: {win_rate:.1f}%")
        
        total_pnl = sum(t['pnl'] for t in settled)
        avg_win = sum(t['pnl'] for t in settled if t['result'] == 'WIN') / wins if wins > 0 else 0
        avg_loss = sum(t['pnl'] for t in settled if t['result'] == 'LOSS') / losses if losses > 0 else 0
        
        print(f"\n**P&L:**")
        print(f"  Total: ${total_pnl:.2f}")
        print(f"  Avg win: ${avg_win:.2f}")
        print(f"  Avg loss: ${avg_loss:.2f}")
        
        total_capital = sum(t['position_size'] for t in settled)
        roi = (total_pnl / total_capital) * 100 if total_capital > 0 else 0
        print(f"  ROI: {roi:.1f}%")
        
        # Calculate hold period and annualized return
        hold_days = []
        for t in settled:
            entry = datetime.fromisoformat(t['timestamp'].replace('Z', '+00:00'))
            settle = datetime.fromisoformat(t['settled_at'].replace('Z', '+00:00'))
            days = (settle - entry).days
            hold_days.append(days)
        
        avg_hold = sum(hold_days) / len(hold_days) if hold_days else 0
        ann_return = (roi / avg_hold) * 365 if avg_hold > 0 else 0
        
        print(f"  Avg hold: {avg_hold:.1f} days")
        print(f"  Annualized: {ann_return:.1f}%")
    
    print(f"\n**Pending Trades ({len(pending)}):**")
    for t in pending:
        print(f"  {t['ticker']} - {t['side']}@{t['entry_price']}¢ | ${t['position_size']}")
        exp = datetime.fromisoformat(t['expiration'].replace('Z', '+00:00'))
        days_left = (exp - datetime.now(timezone.utc)).days
        print(f"    Expires in {days_left} days ({exp.strftime('%Y-%m-%d')})")
    
    print("="*70 + "\n")

def backtest_historical(days=30):
    """Backtest scanner against historical data"""
    print(f"🔍 Running backtest for last {days} days...")
    print("⚠️ This requires historical market data - not yet implemented")
    print("Will need to:")
    print("  1. Fetch historical prices for all markets")
    print("  2. Simulate scanner recommendations at each timestamp")
    print("  3. Calculate what would have happened")
    print("  4. Generate win rate & P&L metrics")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "check":
            check_settlements()
        elif cmd == "report":
            generate_report()
        elif cmd == "backtest":
            days = int(sys.argv[2]) if len(sys.argv) > 2 else 30
            backtest_historical(days)
        else:
            print(f"Unknown command: {cmd}")
            print("Usage: verify_scanner.py [check|report|backtest]")
    else:
        # Default: check settlements and show report
        check_settlements()
