#!/usr/bin/env python3
"""
Kalshi vs Polymarket Arbitrage Finder
Enhanced version of crossplatform.py focused on actionable arbitrage opportunities.
"""

import requests
import json
import sys
from datetime import datetime, timezone

KALSHI_API = "https://api.elections.kalshi.com/trade-api/v2"
POLY_API = "https://gamma-api.polymarket.com"

# Known equivalent markets (manual pairs)
KNOWN_PAIRS = [
    # Format: ("Kalshi series", "Polymarket slug")
    ("KXPRES", "presidential-election-winner-2024"),
    ("KXGOVSHUTLENGTH", "government-shutdown"),
    # Add more as discovered
]

def get_kalshi_price(ticker):
    """Get current Kalshi market price"""
    try:
        resp = requests.get(f"{KALSHI_API}/markets/{ticker}", timeout=10)
        if resp.status_code == 200:
            data = resp.json().get("market", {})
            return {
                "yes_price": data.get("last_price", 0),
                "yes_bid": data.get("yes_bid", 0),
                "yes_ask": data.get("yes_ask", 0),
                "volume": data.get("volume_24h", 0),
            }
    except:
        pass
    return None

def get_poly_price(slug):
    """Get current Polymarket price"""
    try:
        resp = requests.get(f"{POLY_API}/events/{slug}", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            markets = data.get("markets", [])
            if markets:
                return {
                    "yes_price": int(markets[0].get("lastTradePrice", 0) * 100),
                    "volume": markets[0].get("volume24hr", 0),
                }
    except:
        pass
    return None

def calculate_arbitrage(k_price, p_price):
    """
    Calculate arbitrage opportunity.
    
    Returns:
    - spread: price difference (%)
    - direction: "buy_kalshi" or "buy_poly"
    - profit_potential: rough estimate
    """
    
    if not k_price or not p_price:
        return None
    
    k_yes = k_price["yes_price"]
    p_yes = p_price["yes_price"]
    
    spread = abs(k_yes - p_yes)
    
    if spread < 5:  # Less than 5¢ difference
        return None
    
    # Simple arbitrage (ignoring fees for now)
    if k_yes < p_yes:
        direction = "buy_kalshi"
        profit_pct = ((p_yes - k_yes) / k_yes) * 100
    else:
        direction = "buy_poly"
        profit_pct = ((k_yes - p_yes) / p_yes) * 100
    
    return {
        "spread": spread,
        "direction": direction,
        "k_price": k_yes,
        "p_price": p_yes,
        "profit_pct": profit_pct,
        "confidence": "HIGH" if spread >= 10 else "MEDIUM",
    }

def scan_arbitrage():
    """Scan known pairs for arbitrage opportunities"""
    
    print("🔍 Scanning Kalshi vs Polymarket arbitrage...\n")
    
    opportunities = []
    
    for k_series, p_slug in KNOWN_PAIRS:
        print(f"Checking {k_series} vs {p_slug}...")
        
        # TODO: Fetch actual tickers for series
        # For now, placeholder
        
        print(f"  ⚠️ Need to map series to specific tickers")
    
    print("\n" + "="*80)
    print("📊 ARBITRAGE OPPORTUNITIES")
    print("="*80)
    
    if not opportunities:
        print("\nNone found (need more market pairs)\n")
        print("To improve:")
        print("1. Add more KNOWN_PAIRS")
        print("2. Use crossplatform.py auto-matching")
        print("3. Monitor top Polymarket markets and find Kalshi equivalents")
    else:
        for opp in opportunities:
            print(f"\n🔥 {opp['direction'].upper()}")
            print(f"   Kalshi: {opp['k_price']}¢ | Polymarket: {opp['p_price']}¢")
            print(f"   Spread: {opp['spread']}¢ ({opp['profit_pct']:.1f}% profit)")
            print(f"   Confidence: {opp['confidence']}")

if __name__ == "__main__":
    scan_arbitrage()
