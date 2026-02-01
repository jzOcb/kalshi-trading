exec(open('/tmp/sandbox_bootstrap.py').read())

"""
Kalshi Paper Trading Tracker
Records recommendations and tracks results for validation.
"""

import json
import os
from datetime import datetime, timezone

TRADES_FILE = os.path.join(os.path.dirname(__file__), "trades.json")

def load_trades():
    """Load existing trades"""
    if not os.path.exists(TRADES_FILE):
        return {"trades": [], "stats": {"total": 0, "wins": 0, "losses": 0, "pending": 0}}
    try:
        with open(TRADES_FILE) as f:
            return json.load(f)
    except:
        return {"trades": [], "stats": {"total": 0, "wins": 0, "losses": 0, "pending": 0}}

def save_trades(data):
    """Save trades to file"""
    with open(TRADES_FILE, "w") as f:
        json.dump(data, f, indent=2)

def record_recommendation(ticker, title, decision, side, price, position, score, reasons, expiration, url):
    """Record a new recommendation"""
    data = load_trades()
    
    trade = {
        "id": len(data["trades"]) + 1,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ticker": ticker,
        "title": title,
        "decision": decision,
        "side": side,
        "entry_price": price,
        "position_size": position,
        "score": score,
        "reasons": reasons,
        "expiration": expiration,
        "url": url,
        "status": "PENDING",
        "result": None,
        "pnl": None,
        "settled_at": None,
    }
    
    data["trades"].append(trade)
    data["stats"]["total"] += 1
    data["stats"]["pending"] += 1
    save_trades(data)
    
    print(f"✅ Recorded trade #{trade['id']}: {ticker} - {decision}")
    return trade["id"]

def update_result(trade_id, result, settled_price):
    """Update trade result when market settles"""
    data = load_trades()
    
    for trade in data["trades"]:
        if trade["id"] == trade_id:
            trade["status"] = "SETTLED"
            trade["result"] = result  # "WIN" or "LOSS"
            trade["settled_at"] = datetime.now(timezone.utc).isoformat()
            
            # Calculate P&L
            if result == "WIN":
                trade["pnl"] = trade["position_size"] * (100 - trade["entry_price"]) / 100
                data["stats"]["wins"] += 1
            else:
                trade["pnl"] = -trade["position_size"] * trade["entry_price"] / 100
                data["stats"]["losses"] += 1
            
            data["stats"]["pending"] -= 1
            save_trades(data)
            
            print(f"✅ Updated trade #{trade_id}: {result} (P&L: ${trade['pnl']:.2f})")
            return
    
    print(f"❌ Trade #{trade_id} not found")

def show_summary():
    """Display summary of all trades"""
    data = load_trades()
    
    print("\n" + "="*70)
    print("📊 PAPER TRADING SUMMARY")
    print("="*70)
    
    stats = data["stats"]
    print(f"\nTotal Trades: {stats['total']}")
    print(f"Wins: {stats['wins']}")
    print(f"Losses: {stats['losses']}")
    print(f"Pending: {stats['pending']}")
    
    if stats['wins'] + stats['losses'] > 0:
        win_rate = stats['wins'] / (stats['wins'] + stats['losses']) * 100
        print(f"Win Rate: {win_rate:.1f}%")
    
    total_pnl = sum(t.get('pnl', 0) for t in data['trades'] if t.get('pnl'))
    print(f"Total P&L: ${total_pnl:.2f}")
    
    print(f"\n{'='*70}")
    print("PENDING TRADES:")
    print(f"{'='*70}\n")
    
    pending = [t for t in data['trades'] if t['status'] == 'PENDING']
    if not pending:
        print("No pending trades\n")
    else:
        for t in pending:
            print(f"#{t['id']} {t['ticker']} - {t['decision']}")
            print(f"   {t['title']}")
            print(f"   {t['side']} @ {t['entry_price']}¢ | Position: ${t['position_size']} | Score: {t['score']}/100")
            print(f"   Expires: {t['expiration'][:10]}")
            print(f"   {t['url']}\n")
    
    print(f"{'='*70}")
    print("RECENT SETTLED TRADES:")
    print(f"{'='*70}\n")
    
    settled = [t for t in data['trades'] if t['status'] == 'SETTLED'][-5:]
    if not settled:
        print("No settled trades yet\n")
    else:
        for t in settled:
            emoji = "✅" if t['result'] == 'WIN' else "❌"
            print(f"{emoji} #{t['id']} {t['ticker']} - {t['result']}")
            print(f"   P&L: ${t['pnl']:.2f}")
            print(f"   Settled: {t['settled_at'][:10]}\n")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        show_summary()
    elif sys.argv[1] == "record":
        # Example: python paper_trading.py record KXCPI-26JAN-T0.0 "CPI > 0%" BUY YES 95 100 80 "reasons" "2026-02-11" "url"
        if len(sys.argv) < 11:
            print("Usage: paper_trading.py record <ticker> <title> <decision> <side> <price> <position> <score> <reasons> <expiration> <url>")
            sys.exit(1)
        record_recommendation(
            sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5],
            int(sys.argv[6]), int(sys.argv[7]), int(sys.argv[8]),
            sys.argv[9], sys.argv[10], sys.argv[11]
        )
    elif sys.argv[1] == "update":
        # Example: python paper_trading.py update 1 WIN 100
        if len(sys.argv) < 5:
            print("Usage: paper_trading.py update <trade_id> <WIN|LOSS> <settled_price>")
            sys.exit(1)
        update_result(int(sys.argv[2]), sys.argv[3], int(sys.argv[4]))
    elif sys.argv[1] == "summary":
        show_summary()
    else:
        print("Unknown command. Use: record, update, or summary")
