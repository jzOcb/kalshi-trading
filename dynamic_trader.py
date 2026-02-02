#!/usr/bin/env python3
"""
Kalshi Dynamic Position Manager
Real-time monitoring and position adjustments based on market changes.
"""

import json
import os
import time
from datetime import datetime, timezone
import requests

API_BASE = "https://api.elections.kalshi.com/trade-api/v2"
TRADES_FILE = os.path.join(os.path.dirname(__file__), "trades.json")
STATE_FILE = os.path.join(os.path.dirname(__file__), "dynamic_state.json")

# Trading parameters
TAKE_PROFIT_PCT = 30  # Exit if 30% profit available
STOP_LOSS_PCT = 40    # Exit if 40% of capital at risk
ADD_THRESHOLD = 5     # Add if price improves by 5¢
TRIM_THRESHOLD = 5    # Trim if price worsens by 5¢

# Position sizing limits (for $200 total capital)
MAX_POSITION_PER_TICKER = 75     # Max $75 per ticker (~37% max, allows 3+ positions)
MAX_POSITION_PER_SERIES = 120    # Max $120 per series (60% max of total)
MAX_TOTAL_EXPOSURE = 200         # Max $200 total across all trades
MAX_SINGLE_ADD = 40              # Max $40 per buy-more action

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
        return {"trades": [], "stats": {}}
    with open(TRADES_FILE) as f:
        return json.load(f)

def save_trades(data):
    """Save trades"""
    with open(TRADES_FILE, "w") as f:
        json.dump(data, f, indent=2)

def load_state():
    """Load dynamic trading state"""
    if not os.path.exists(STATE_FILE):
        return {"positions": {}, "actions": []}
    with open(STATE_FILE) as f:
        return json.load(f)

def get_position_limits():
    """Calculate current exposure across all positions"""
    data = load_trades()
    pending = [t for t in data["trades"] if t["status"] == "PENDING"]
    
    # Total exposure
    total_exposure = sum(t.get("current_position", t["position_size"]) for t in pending)
    
    # Per-ticker exposure
    ticker_exposure = {}
    for t in pending:
        ticker = t["ticker"]
        pos = t.get("current_position", t["position_size"])
        ticker_exposure[ticker] = pos
    
    # Per-series exposure
    series_exposure = {}
    for t in pending:
        series = t["ticker"].split('-')[0]  # e.g., KXCPI
        pos = t.get("current_position", t["position_size"])
        series_exposure[series] = series_exposure.get(series, 0) + pos
    
    return {
        "total": total_exposure,
        "by_ticker": ticker_exposure,
        "by_series": series_exposure,
    }

def check_position_limit(ticker, add_size):
    """
    Check if adding position would exceed limits.
    Returns: (allowed: bool, reason: str)
    """
    limits = get_position_limits()
    series = ticker.split('-')[0]
    
    # Check max single add
    if add_size > MAX_SINGLE_ADD:
        return False, f"Exceeds max single add (${MAX_SINGLE_ADD})"
    
    # Check total exposure
    new_total = limits["total"] + add_size
    if new_total > MAX_TOTAL_EXPOSURE:
        return False, f"Would exceed max total exposure (${MAX_TOTAL_EXPOSURE}). Current: ${limits['total']}"
    
    # Check per-ticker limit
    current_ticker = limits["by_ticker"].get(ticker, 0)
    new_ticker_pos = current_ticker + add_size
    if new_ticker_pos > MAX_POSITION_PER_TICKER:
        return False, f"Would exceed max per ticker (${MAX_POSITION_PER_TICKER}). Current in {ticker}: ${current_ticker}"
    
    # Check per-series limit
    current_series = limits["by_series"].get(series, 0)
    new_series_pos = current_series + add_size
    if new_series_pos > MAX_POSITION_PER_SERIES:
        return False, f"Would exceed max per series (${MAX_POSITION_PER_SERIES}). Current in {series}: ${current_series}"
    
    return True, "Within limits"

def save_state(state):
    """Save state"""
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def get_current_price(ticker):
    """Fetch current market price"""
    data = api_get(f"/markets/{ticker}")
    if not data or "market" not in data:
        return None
    
    market = data["market"]
    return {
        "last_price": market.get("last_price", 0),
        "yes_bid": market.get("yes_bid", 0),
        "yes_ask": market.get("yes_ask", 0),
        "no_bid": market.get("no_bid", 0),
        "no_ask": market.get("no_ask", 0),
        "spread": (market.get("yes_ask", 0) - market.get("yes_bid", 0)),
        "volume_24h": market.get("volume_24h", 0),
        "status": market.get("status", "unknown"),
    }

def check_news_justification(ticker, price_change_pct):
    """
    Verify if price movement is justified by news/fundamentals.
    Returns: (justified: bool, news_summary: str)
    """
    if abs(price_change_pct) < 10:
        return None, "Price change too small for news check"
    
    # Extract market topic from ticker
    series = ticker.split('-')[0]  # e.g., KXCPI → KXCPI
    
    # Map series to news keywords
    NEWS_KEYWORDS = {
        "KXCPI": ["inflation", "CPI", "consumer price"],
        "KXGDP": ["GDP", "economic growth", "economy"],
        "KXFED": ["Federal Reserve", "Fed", "interest rate"],
        "KXRECESSION": ["recession", "economic downturn"],
        "KXBITCOIN": ["bitcoin", "BTC", "crypto"],
        "KXSP500": ["S&P 500", "stock market", "equities"],
        "KXSHUTDOWN": ["government shutdown", "funding bill"],
        "KXSCOTUS": ["Supreme Court", "SCOTUS"],
    }
    
    keywords = NEWS_KEYWORDS.get(series, [series.replace("KX", "")])
    
    try:
        # Try to use news_scanner.py
        import subprocess
        result = subprocess.run(
            ["python3", os.path.join(os.path.dirname(__file__), "news_scanner.py"), 
             "--ticker", ticker, "--keywords"] + keywords,
            capture_output=True, text=True, timeout=10
        )
        
        if result.returncode == 0 and result.stdout:
            news_data = json.loads(result.stdout)
            recent_news = news_data.get("articles", [])
            
            if len(recent_news) >= 3:
                # Significant news found
                headlines = [n.get("title", "") for n in recent_news[:3]]
                return True, f"Recent news found:\n" + "\n".join(f"• {h}" for h in headlines)
            elif len(recent_news) > 0:
                # Some news but not major
                return None, f"Limited news: {recent_news[0].get('title', 'check manually')}"
            else:
                # No news
                return False, "No recent news found - likely market noise"
        else:
            # News check failed
            return None, f"⚠️ Could not verify news - manual review needed"
            
    except Exception as e:
        # Fallback: manual review
        return None, f"⚠️ News check failed: {str(e)} - verify manually"

def analyze_position(trade, current_price):
    """Analyze position and generate trading signals"""
    if not current_price:
        return None
    
    ticker = trade["ticker"]
    side = trade["side"]
    entry_price = trade["entry_price"]
    position = trade.get("current_position", trade["position_size"])
    
    # Determine current market price for our side
    if side == "YES":
        # We'd sell at bid, buy at ask
        sell_price = current_price["yes_bid"]
        buy_price = current_price["yes_ask"]
    else:
        sell_price = current_price["no_bid"]
        buy_price = current_price["no_ask"]
    
    # Calculate unrealized P&L
    if sell_price > 0:
        pnl = position * (sell_price - entry_price) / 100
        pnl_pct = ((sell_price - entry_price) / entry_price) * 100
    else:
        pnl = 0
        pnl_pct = 0
    
    # Generate signals
    signals = []
    
    # Take profit signal
    max_gain = (100 - entry_price) / entry_price * 100
    if pnl_pct >= TAKE_PROFIT_PCT or pnl_pct >= max_gain * 0.7:
        signals.append({
            "action": "SELL_ALL",
            "reason": f"Take profit: {pnl_pct:.1f}% gain available",
            "price": sell_price,
            "expected_pnl": pnl,
            "confidence": "HIGH",
        })
    
    # NEWS-VERIFIED Stop loss signal
    loss_pct = ((entry_price - sell_price) / entry_price) * 100
    if loss_pct >= STOP_LOSS_PCT:
        # Check if news justifies the move
        news_justified, news_summary = check_news_justification(ticker, -loss_pct)
        
        if news_justified is True:
            # Confirmed bad news → sell
            signals.append({
                "action": "SELL_ALL",
                "reason": f"Stop loss: {loss_pct:.1f}% loss - NEWS CONFIRMED",
                "price": sell_price,
                "expected_pnl": pnl,
                "confidence": "HIGH",
                "news": news_summary,
            })
        elif news_justified is False:
            # No news → likely noise → BUY THE DIP (if within limits)
            suggested_size = min(100, trade["position_size"])
            allowed, limit_reason = check_position_limit(ticker, suggested_size)
            
            if not allowed:
                signals.append({
                    "action": "WARNING",
                    "reason": f"Contrarian opportunity but POSITION LIMIT - {limit_reason}",
                    "price": None,
                    "news": "No fundamental change but can't add due to limits",
                })
            else:
                signals.append({
                    "action": "BUY_MORE",
                    "reason": f"Contrarian buy: {loss_pct:.1f}% drop with NO news - likely noise",
                    "price": buy_price,
                    "suggested_size": suggested_size,
                    "confidence": "MEDIUM",
                    "news": "No fundamental change detected",
                    "limits_ok": True,
                })
        else:
            # Uncertain → manual review needed
            signals.append({
                "action": "MANUAL_REVIEW",
                "reason": f"Stop loss threshold hit: {loss_pct:.1f}% loss",
                "price": sell_price,
                "expected_pnl": pnl,
                "confidence": "NEEDS_VERIFICATION",
                "news": news_summary,
            })
    
    # Add position signal (price improved + verify no bad news + check limits)
    if buy_price < entry_price - ADD_THRESHOLD:
        price_improvement = entry_price - buy_price
        
        # Verify no bad news before adding
        news_justified, news_summary = check_news_justification(ticker, -price_improvement)
        
        if news_justified is True:
            # Bad news caused price drop → don't add
            signals.append({
                "action": "WARNING",
                "reason": f"Price improved but NEWS ADVERSE - don't add",
                "price": None,
                "news": news_summary,
            })
        else:
            # No bad news → check position limits
            suggested_size = min(100, trade["position_size"])
            allowed, limit_reason = check_position_limit(ticker, suggested_size)
            
            if not allowed:
                # Hit position limit
                signals.append({
                    "action": "WARNING",
                    "reason": f"Price improved but POSITION LIMIT - {limit_reason}",
                    "price": None,
                    "suggested_size": 0,
                })
            else:
                # All checks passed → safe to add
                confidence = "HIGH" if news_justified is False else "MEDIUM"
                signals.append({
                    "action": "BUY_MORE",
                    "reason": f"Price improved: {entry_price}¢ → {buy_price}¢ ({price_improvement}¢ cheaper)",
                    "price": buy_price,
                    "suggested_size": suggested_size,
                    "confidence": confidence,
                    "news": news_summary if news_summary else "No adverse news",
                    "limits_ok": True,
                })
    
    # Trim position signal (price worsened)
    if sell_price < entry_price - TRIM_THRESHOLD and position > trade["position_size"] * 0.5:
        signals.append({
            "action": "SELL_HALF",
            "reason": f"Price deteriorated: {entry_price}¢ → {sell_price}¢",
            "price": sell_price,
            "expected_pnl": pnl * 0.5,
        })
    
    # Spread warning
    if current_price["spread"] > 10:
        signals.append({
            "action": "WARNING",
            "reason": f"Wide spread: {current_price['spread']}¢ - illiquid",
            "price": None,
        })
    
    return {
        "ticker": ticker,
        "current_price": sell_price,
        "entry_price": entry_price,
        "position": position,
        "unrealized_pnl": pnl,
        "unrealized_pnl_pct": pnl_pct,
        "signals": signals,
        "market_data": current_price,
    }

def monitor_positions():
    """Monitor all open positions and generate trading signals"""
    data = load_trades()
    pending = [t for t in data["trades"] if t["status"] == "PENDING"]
    
    if not pending:
        print("No open positions to monitor")
        return
    
    # Show position limits summary
    limits = get_position_limits()
    
    print(f"\n{'='*80}")
    print(f"📊 MONITORING {len(pending)} POSITIONS")
    print(f"{'='*80}")
    print(f"\n💰 EXPOSURE SUMMARY:")
    print(f"  Total: ${limits['total']} / ${MAX_TOTAL_EXPOSURE} ({limits['total']/MAX_TOTAL_EXPOSURE*100:.1f}%)")
    print(f"\n  By Series:")
    for series, amount in sorted(limits['by_series'].items()):
        pct = amount / MAX_POSITION_PER_SERIES * 100
        print(f"    {series}: ${amount} / ${MAX_POSITION_PER_SERIES} ({pct:.1f}%)")
    print(f"\n  By Ticker (top 5):")
    top_tickers = sorted(limits['by_ticker'].items(), key=lambda x: -x[1])[:5]
    for ticker, amount in top_tickers:
        pct = amount / MAX_POSITION_PER_TICKER * 100
        print(f"    {ticker}: ${amount} / ${MAX_POSITION_PER_TICKER} ({pct:.1f}%)")
    print(f"\n{'='*80}\n")
    
    recommendations = []
    
    for trade in pending:
        ticker = trade["ticker"]
        print(f"Checking {ticker}...")
        
        current = get_current_price(ticker)
        analysis = analyze_position(trade, current)
        
        if not analysis:
            print(f"  ⚠️ Could not fetch current price")
            continue
        
        print(f"  Entry: {analysis['entry_price']}¢ | Current: {analysis['current_price']}¢")
        print(f"  P&L: ${analysis['unrealized_pnl']:.2f} ({analysis['unrealized_pnl_pct']:.1f}%)")
        print(f"  Position: ${analysis['position']}")
        
        if analysis["signals"]:
            print(f"  🔔 {len(analysis['signals'])} SIGNALS:")
            for sig in analysis["signals"]:
                action = sig["action"]
                reason = sig["reason"]
                if action == "WARNING":
                    print(f"     ⚠️ {reason}")
                else:
                    print(f"     → {action}: {reason}")
                    recommendations.append({
                        "trade_id": trade["id"],
                        "ticker": ticker,
                        **sig,
                    })
        else:
            print(f"  ✅ HOLD - no signals")
        
        print()
    
    # Save state
    state = load_state()
    state["last_scan"] = datetime.now(timezone.utc).isoformat()
    state["recommendations"] = recommendations
    save_state(state)
    
    # Summary
    print(f"{'='*80}")
    if recommendations:
        print(f"🎯 {len(recommendations)} TRADING RECOMMENDATIONS:")
        for rec in recommendations:
            print(f"  {rec['ticker']}: {rec['action']} - {rec['reason']}")
    else:
        print("✅ All positions HOLD")
    print(f"{'='*80}\n")
    
    return recommendations

def execute_manual_adjustment(trade_id, action, price, size=None):
    """Manually record a position adjustment"""
    data = load_trades()
    trade = None
    
    for t in data["trades"]:
        if t["id"] == trade_id:
            trade = t
            break
    
    if not trade:
        print(f"❌ Trade #{trade_id} not found")
        return
    
    timestamp = datetime.now(timezone.utc).isoformat()
    
    if action == "SELL_ALL":
        # Close position
        position = trade.get("current_position", trade["position_size"])
        pnl = position * (price - trade["entry_price"]) / 100
        
        trade["status"] = "CLOSED"
        trade["exit_price"] = price
        trade["exit_time"] = timestamp
        trade["pnl"] = pnl
        trade["result"] = "WIN" if pnl > 0 else "LOSS"
        
        print(f"✅ Closed position: ${pnl:.2f} P&L")
        
    elif action == "SELL_HALF":
        # Reduce position by 50%
        current = trade.get("current_position", trade["position_size"])
        sold = current * 0.5
        realized_pnl = sold * (price - trade["entry_price"]) / 100
        
        trade["current_position"] = current - sold
        trade["realized_pnl"] = trade.get("realized_pnl", 0) + realized_pnl
        
        # Record adjustment
        if "adjustments" not in trade:
            trade["adjustments"] = []
        trade["adjustments"].append({
            "timestamp": timestamp,
            "action": "SELL_HALF",
            "price": price,
            "size": sold,
            "pnl": realized_pnl,
        })
        
        print(f"✅ Reduced position by 50%: ${realized_pnl:.2f} realized")
        
    elif action == "BUY_MORE":
        # Add to position
        current = trade.get("current_position", trade["position_size"])
        add_size = size or trade["position_size"] * 0.5
        
        # Recalculate average entry price
        total_cost = (current * trade["entry_price"] + add_size * price) / 100
        new_position = current + add_size
        new_avg_entry = (total_cost / new_position) * 100
        
        trade["current_position"] = new_position
        trade["entry_price"] = new_avg_entry
        
        if "adjustments" not in trade:
            trade["adjustments"] = []
        trade["adjustments"].append({
            "timestamp": timestamp,
            "action": "BUY_MORE",
            "price": price,
            "size": add_size,
        })
        
        print(f"✅ Added ${add_size} position at {price}¢")
        print(f"   New avg entry: {new_avg_entry:.1f}¢ | Total position: ${new_position}")
    
    save_trades(data)

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        
        if cmd == "monitor":
            monitor_positions()
            
        elif cmd == "execute":
            # execute <trade_id> <action> <price> [size]
            if len(sys.argv) < 5:
                print("Usage: dynamic_trader.py execute <trade_id> <action> <price> [size]")
                print("Actions: SELL_ALL, SELL_HALF, BUY_MORE")
                sys.exit(1)
            
            trade_id = int(sys.argv[2])
            action = sys.argv[3]
            price = int(sys.argv[4])
            size = int(sys.argv[5]) if len(sys.argv) > 5 else None
            
            execute_manual_adjustment(trade_id, action, price, size)
            
        else:
            print(f"Unknown command: {cmd}")
            print("Usage: dynamic_trader.py [monitor|execute]")
    else:
        # Default: monitor positions
        monitor_positions()
