#!/usr/bin/env python3
"""
Kalshi Longshot Scanner
Find underpriced <20¢ opportunities (like DOGE Cabinet example)
"""

import requests
import json
from datetime import datetime, timezone

API_BASE = "https://api.elections.kalshi.com/trade-api/v2"

def api_get(endpoint, params=None):
    try:
        resp = requests.get(f"{API_BASE}{endpoint}", params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except:
        return None

def fetch_longshots(max_price=20, min_volume=10):
    """Find markets priced <20¢ with decent volume"""
    print(f"🔍 Scanning for longshots (≤{max_price}¢, vol≥{min_volume})...")
    
    all_markets = []
    cursor = None
    
    while True:
        params = {"limit": 200, "status": "open"}
        if cursor:
            params["cursor"] = cursor
        
        data = api_get("/markets", params)
        if not data:
            break
        
        markets = data.get("markets", [])
        all_markets.extend(markets)
        
        cursor = data.get("cursor", "")
        if not cursor or len(markets) < 200:
            break
    
    print(f"   Scanned {len(all_markets)} markets")
    
    # Filter longshots
    longshots = []
    
    for m in all_markets:
        yes_price = m.get("last_price", 50)
        no_price = 100 - yes_price
        vol_24h = m.get("volume_24h", 0)
        vol_total = m.get("volume", 0)
        
        # Check YES side
        if yes_price <= max_price and yes_price > 0 and vol_total >= min_volume:
            gain_pct = ((100-yes_price)/yes_price)*100
            longshots.append({
                "ticker": m.get("ticker", ""),
                "title": m.get("title", ""),
                "side": "YES",
                "price": yes_price,
                "potential": f"{yes_price}¢ → 100¢ ({gain_pct:.0f}% gain)",
                "vol_24h": vol_24h,
                "vol_total": vol_total,
                "close": m.get("close_time", "")[:10],
            })
        
        # Check NO side
        if no_price <= max_price and no_price > 0 and vol_total >= min_volume:
            gain_pct = ((100-no_price)/no_price)*100
            longshots.append({
                "ticker": m.get("ticker", ""),
                "title": m.get("title", ""),
                "side": "NO",
                "price": no_price,
                "potential": f"{no_price}¢ → 100¢ ({gain_pct:.0f}% gain)",
                "vol_24h": vol_24h,
                "vol_total": vol_total,
                "close": m.get("close_time", "")[:10],
            })
    
    # Sort by price (cheapest first)
    longshots.sort(key=lambda x: x["price"])
    
    return longshots

def analyze_longshot(ls):
    """
    AI-powered analysis: Is this underpriced?
    
    For now, simple heuristics:
    - Very cheap (<5¢) = lottery ticket
    - Some volume = market interest
    - Check if fundamentally possible
    """
    
    price = ls["price"]
    vol = ls["vol_total"]
    
    if price <= 3:
        score = 30  # Lottery ticket territory
    elif price <= 10:
        score = 50  # Long shot but possible
    elif price <= 20:
        score = 70  # Underdog
    else:
        score = 0
    
    # Volume boost
    if vol >= 1000:
        score += 20
    elif vol >= 100:
        score += 10
    
    # TODO: Add AI analysis
    # - Check news sentiment
    # - Compare to Polymarket
    # - Historical pattern matching
    
    return {
        **ls,
        "score": min(score, 100),
        "rating": "🎰" if price <= 5 else "🎲" if price <= 15 else "🎯",
    }

if __name__ == "__main__":
    longshots = fetch_longshots(max_price=20, min_volume=10)
    
    print(f"\n{'='*80}")
    print(f"🎲 LONGSHOT OPPORTUNITIES ({len(longshots)} found)")
    print(f"{'='*80}\n")
    
    if not longshots:
        print("No longshots found matching criteria")
    else:
        analyzed = [analyze_longshot(ls) for ls in longshots[:20]]
        analyzed.sort(key=lambda x: -x["score"])
        
        for ls in analyzed[:10]:
            print(f"{ls['rating']} {ls['side']}@{ls['price']}¢ - {ls['title'][:60]}")
            print(f"   {ls['potential']} | Vol: {ls['vol_total']} | Score: {ls['score']}/100")
            print(f"   {ls['ticker']} | Closes: {ls['close']}")
            print()
