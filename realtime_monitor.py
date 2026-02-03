#!/usr/bin/env python3
"""
Kalshi Realtime Position Monitor
Polls REST API for price updates on Jason's positions.
Falls back to REST polling since WebSocket requires API key auth.

Features:
- Reads positions from positions.json
- Polls prices every 60 seconds
- Alerts on price changes >= 3¢
- Logs status every 5 minutes
- Writes alert flags to alerts.json

Usage:
    python3 realtime_monitor.py              # Run once (for cron)
    python3 realtime_monitor.py --daemon     # Run continuously
    python3 realtime_monitor.py --check      # Quick check, print and exit
"""

import json
import os
import sys
import time
import logging
from datetime import datetime, timezone

# Setup
KALSHI_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KALSHI_DIR)

API_BASE = "https://api.elections.kalshi.com/trade-api/v2"
POSITIONS_FILE = os.path.join(KALSHI_DIR, "positions.json")
ALERTS_FILE = os.path.join(KALSHI_DIR, "alerts.json")
LAST_PRICES_FILE = os.path.join(KALSHI_DIR, "monitor_last_prices.json")
LOG_FILE = os.path.join(KALSHI_DIR, "data", "monitor.log")

POLL_INTERVAL = 60       # seconds between polls
STATUS_INTERVAL = 300    # seconds between status logs (5 min)
ALERT_THRESHOLD = 3      # cents change to trigger alert

# Setup logging
os.makedirs(os.path.join(KALSHI_DIR, "data"), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE)
    ]
)
logger = logging.getLogger(__name__)

# HTTP client (use requests if available, else urllib)
try:
    import requests as _requests
    def api_get(endpoint, params=None):
        try:
            resp = _requests.get(f"{API_BASE}{endpoint}", params=params, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"API error on {endpoint}: {e}")
            return None
except ImportError:
    import urllib.request
    import urllib.parse
    def api_get(endpoint, params=None):
        try:
            url = f"{API_BASE}{endpoint}"
            if params:
                url += "?" + urllib.parse.urlencode(params)
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=15) as response:
                return json.loads(response.read().decode('utf-8'))
        except Exception as e:
            logger.error(f"API error on {endpoint}: {e}")
            return None


def load_positions():
    """Load positions from positions.json"""
    try:
        with open(POSITIONS_FILE) as f:
            data = json.load(f)
        return data.get("positions", [])
    except Exception as e:
        logger.error(f"Failed to load positions: {e}")
        return []


def load_last_prices():
    """Load last known prices"""
    try:
        with open(LAST_PRICES_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_last_prices(prices):
    """Save current prices for comparison"""
    with open(LAST_PRICES_FILE, 'w') as f:
        json.dump(prices, f, indent=2)


def load_alerts():
    """Load existing alerts"""
    try:
        with open(ALERTS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"alerts": [], "last_updated": None}


def save_alerts(alerts_data):
    """Save alerts"""
    alerts_data["last_updated"] = datetime.now(timezone.utc).isoformat()
    with open(ALERTS_FILE, 'w') as f:
        json.dump(alerts_data, f, indent=2)


def fetch_market_price(ticker):
    """Fetch current market price for a ticker"""
    data = api_get(f"/markets/{ticker}")
    if not data:
        return None
    market = data.get("market", {})
    return {
        "ticker": ticker,
        "yes_bid": market.get("yes_bid"),
        "yes_ask": market.get("yes_ask"),
        "last_price": market.get("last_price"),
        "volume": market.get("volume"),
        "open_interest": market.get("open_interest"),
        "status": market.get("status"),
        "result": market.get("result"),
        "close_time": market.get("close_time"),
    }


def check_prices_once(positions):
    """Poll prices once and check for alerts"""
    now = datetime.now(timezone.utc).isoformat()
    last_prices = load_last_prices()
    alerts_data = load_alerts()
    current_prices = {}
    new_alerts = []
    
    for pos in positions:
        ticker = pos["ticker"]
        price_data = fetch_market_price(ticker)
        
        if not price_data:
            logger.warning(f"Could not fetch price for {ticker}")
            continue
        
        last_price = price_data.get("last_price")
        yes_bid = price_data.get("yes_bid")
        yes_ask = price_data.get("yes_ask")
        
        current_prices[ticker] = {
            "last_price": last_price,
            "yes_bid": yes_bid,
            "yes_ask": yes_ask,
            "timestamp": now,
            "status": price_data.get("status"),
        }
        
        # Check for price change alert
        if ticker in last_prices and last_price is not None:
            prev_price = last_prices[ticker].get("last_price")
            if prev_price is not None:
                change = last_price - prev_price
                if abs(change) >= ALERT_THRESHOLD:
                    direction = "📈" if change > 0 else "📉"
                    side = pos.get("side", "?")
                    # For YES positions, price up is good; for NO, price down is good
                    if side == "YES":
                        sentiment = "✅ favorable" if change > 0 else "⚠️ unfavorable"
                    else:
                        sentiment = "✅ favorable" if change < 0 else "⚠️ unfavorable"
                    
                    alert = {
                        "ticker": ticker,
                        "side": side,
                        "prev_price": prev_price,
                        "new_price": last_price,
                        "change": change,
                        "sentiment": sentiment,
                        "timestamp": now,
                    }
                    new_alerts.append(alert)
                    logger.warning(f"{direction} ALERT: {ticker} ({side}) moved {change:+d}¢ "
                                   f"({prev_price}→{last_price}) — {sentiment}")
        
        # Log current state
        spread = (yes_ask or 0) - (yes_bid or 0) if yes_ask and yes_bid else "?"
        entry = pos.get("entry_price", "?")
        pnl = (last_price - entry) if last_price and entry != "?" else "?"
        side = pos.get("side", "?")
        if side == "NO" and pnl != "?":
            pnl = -pnl  # For NO positions, we profit when price drops
        
        logger.info(f"  {ticker} ({side}): last={last_price}¢ bid/ask={yes_bid}/{yes_ask} "
                     f"spread={spread} entry={entry}¢ PnL={pnl:+d}¢" if isinstance(pnl, int) 
                     else f"  {ticker} ({side}): last={last_price}¢ bid/ask={yes_bid}/{yes_ask} "
                     f"spread={spread} entry={entry}¢")
    
    # Save state
    save_last_prices(current_prices)
    
    if new_alerts:
        alerts_data["alerts"].extend(new_alerts)
        # Keep last 100 alerts
        alerts_data["alerts"] = alerts_data["alerts"][-100:]
        save_alerts(alerts_data)
        logger.info(f"🔔 {len(new_alerts)} new alert(s) written to {ALERTS_FILE}")
    
    return current_prices, new_alerts


def run_once(positions):
    """Single check cycle"""
    logger.info("=" * 50)
    logger.info(f"Position Monitor — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    logger.info(f"Monitoring {len(positions)} positions")
    
    prices, alerts = check_prices_once(positions)
    
    # Summary
    logger.info(f"Fetched {len(prices)} prices, {len(alerts)} alerts")
    return prices, alerts


def run_daemon(positions):
    """Continuous monitoring daemon"""
    logger.info("🚀 Starting realtime monitor daemon")
    logger.info(f"Poll interval: {POLL_INTERVAL}s, Status interval: {STATUS_INTERVAL}s")
    logger.info(f"Alert threshold: {ALERT_THRESHOLD}¢")
    
    last_status_time = 0
    cycle = 0
    
    try:
        while True:
            cycle += 1
            now = time.time()
            
            # Status log every 5 minutes
            if now - last_status_time >= STATUS_INTERVAL:
                logger.info(f"\n{'='*50}")
                logger.info(f"📊 Status Report — Cycle #{cycle}")
                last_status_time = now
            
            prices, alerts = check_prices_once(positions)
            
            if alerts:
                for a in alerts:
                    print(f"🔔 ALERT: {a['ticker']} {a['change']:+d}¢ — {a['sentiment']}")
            
            time.sleep(POLL_INTERVAL)
    
    except KeyboardInterrupt:
        logger.info("Monitor stopped by user")


def main():
    positions = load_positions()
    if not positions:
        logger.error("No positions found! Check positions.json")
        sys.exit(1)
    
    logger.info(f"Loaded {len(positions)} positions:")
    for p in positions:
        logger.info(f"  {p['ticker']} — {p['side']} @ {p['entry_price']}¢ x{p['contracts']}")
    
    if "--daemon" in sys.argv:
        run_daemon(positions)
    elif "--check" in sys.argv:
        prices, alerts = run_once(positions)
        # Print compact summary
        print(f"\n{'='*50}")
        print("POSITION MONITOR — Quick Check")
        print(f"{'='*50}")
        for p in positions:
            t = p["ticker"]
            if t in prices:
                lp = prices[t].get("last_price", "?")
                entry = p.get("entry_price", "?")
                side = p.get("side", "?")
                pnl = ""
                if isinstance(lp, int) and isinstance(entry, int):
                    change = lp - entry if side == "YES" else entry - lp
                    pnl = f" PnL: {change:+d}¢/contract"
                print(f"  {t} ({side}): {lp}¢{pnl}")
        if alerts:
            print(f"\n🔔 {len(alerts)} alerts triggered!")
        else:
            print(f"\nNo alerts (threshold: {ALERT_THRESHOLD}¢)")
    else:
        run_once(positions)


if __name__ == "__main__":
    main()
