#!/usr/bin/env python3
"""
cross_platform_monitor - Kalshi vs Polymarket 比价

功能：
    - 跨平台价格比较
    - 识别平台间套利
    - 监控价差变化

用法：
    python cross_platform_monitor.py       # 运行比价监控
    
依赖：
    - requests
"""

import json
import os
import re
import sys
import time
import requests
from datetime import datetime, timezone

# ── APIs ──

KALSHI_API = "https://api.elections.kalshi.com/trade-api/v2"
POLY_GAMMA_API = "https://gamma-api.polymarket.com"
POLY_CLOB_API = "https://clob.polymarket.com"

# Fee structure (from RESEARCH-V2.md)
KALSHI_FEE = 0.007      # ~0.7%
POLY_FEE_US = 0.0001    # ~0.01% (US users)
POLY_FEE_INTL = 0.02    # ~2% (international)

# Import existing fuzzy matching from crossplatform.py
try:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from kalshi.crossplatform import (
        similarity, jaccard, levenshtein_ratio,
        auto_match_markets, PAIRS as KNOWN_PAIRS,
    )
    HAVE_CROSSPLATFORM = True
except ImportError:
    HAVE_CROSSPLATFORM = False
    # Minimal fallback
    def tokenize(text):
        text = re.sub(r'[^a-z0-9\s]', '', text.lower())
        return set(text.split())

    def jaccard(a, b):
        sa, sb = tokenize(a), tokenize(b)
        if not sa or not sb: return 0.0
        return len(sa & sb) / len(sa | sb)

    def levenshtein_ratio(a, b):
        a, b = a.lower(), b.lower()
        if not a or not b: return 0.0
        n, m = len(a), len(b)
        if n > m: a, b, n, m = b, a, m, n
        prev = list(range(n + 1))
        for j in range(1, m + 1):
            curr = [j] + [0] * n
            for i in range(1, n + 1):
                cost = 0 if a[i-1] == b[j-1] else 1
                curr[i] = min(curr[i-1] + 1, prev[i] + 1, prev[i-1] + cost)
            prev = curr
        return 1.0 - prev[n] / max(n, m)

    def similarity(a, b):
        return 0.6 * jaccard(a, b) + 0.4 * levenshtein_ratio(a, b)

    KNOWN_PAIRS = []

# Import Kalshi API helper
try:
    from kalshi.report_v2 import api_get, kalshi_url, format_vol
except ImportError:
    def api_get(endpoint, params=None):
        try:
            resp = requests.get(f"{KALSHI_API}{endpoint}", params=params, timeout=15)
            if resp.status_code == 429:
                time.sleep(3)
                resp = requests.get(f"{KALSHI_API}{endpoint}", params=params, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return None

    def kalshi_url(ticker):
        return f"https://kalshi.com/markets/{ticker.lower()}"

    def format_vol(v):
        if v >= 1_000_000: return f"{v/1_000_000:.1f}M"
        elif v >= 1_000: return f"{v/1_000:.0f}K"
        return str(v)


# ── Extended market pairs (Kalshi series → Polymarket search terms) ──

EXTENDED_PAIRS = [
    {
        "name": "📈 GDP Q4 2025",
        "kalshi_series": "KXGDP",
        "poly_search": ["gdp", "gross domestic product", "economic growth"],
        "notes": "GDPNow tracking 4.2%. Key thresholds: >3%, >3.5%, >4%",
    },
    {
        "name": "📊 CPI / Inflation",
        "kalshi_series": "KXCPI",
        "poly_search": ["cpi", "consumer price index", "inflation"],
        "notes": "Monthly CPI data. Tariffs could push higher.",
    },
    {
        "name": "🏦 Fed Rate Decision",
        "kalshi_series": "KXFEDRATE",
        "poly_search": ["federal reserve", "fed rate", "interest rate", "fomc"],
        "notes": "Rate cut/hold probabilities.",
    },
    {
        "name": "₿ Bitcoin Price",
        "kalshi_series": "KXBITCOIN",
        "poly_search": ["bitcoin", "btc price", "btc above", "btc below"],
        "notes": "BTC price bracket markets.",
    },
    {
        "name": "📉 S&P 500",
        "kalshi_series": "KXSP500",
        "poly_search": ["s&p 500", "sp500", "stock market"],
        "notes": "S&P 500 price level markets.",
    },
    {
        "name": "🏛️ Government Shutdown",
        "kalshi_series": "KXGOVSHUTLENGTH",
        "poly_search": ["government shutdown", "shutdown"],
        "notes": "Shutdown duration and resolution markets.",
    },
    {
        "name": "📦 Tariffs",
        "kalshi_series": "KXTARIFFS",
        "poly_search": ["tariff", "trade war", "import tax"],
        "notes": "Tariff implementation markets.",
    },
    {
        "name": "🐕 DOGE Spending Cuts",
        "kalshi_series": "KXGOVTCUTS",
        "poly_search": ["doge", "spending cuts", "government efficiency"],
        "notes": "Government spending reduction markets.",
    },
    {
        "name": "🟢 Greenland",
        "kalshi_series": "KXGREENLAND",
        "poly_search": ["greenland", "trump greenland"],
        "notes": "Greenland acquisition markets.",
    },
    {
        "name": "🇮🇷 Iran",
        "kalshi_series": "KXIRAN",
        "poly_search": ["iran", "strikes iran"],
        "notes": "US-Iran conflict markets.",
    },
]


def fetch_kalshi_series_markets(series_ticker):
    """Fetch open Kalshi markets for a series."""
    data = api_get("/markets", {
        "series_ticker": series_ticker,
        "limit": 50,
        "status": "open",
    })
    if not data:
        return []
    return [m for m in data.get("markets", []) if (m.get("volume", 0) or 0) > 0]


def fetch_polymarket_events(limit=100):
    """Fetch active Polymarket events from Gamma API."""
    try:
        r = requests.get(f"{POLY_GAMMA_API}/events", params={
            "limit": limit,
            "active": "true",
            "closed": "false",
            "order": "volume24hr",
            "ascending": "false",
        }, timeout=15)
        if r.status_code == 200:
            return r.json() if isinstance(r.json(), list) else []
    except Exception as e:
        print(f"  ⚠️ Polymarket API error: {e}")
    return []


def search_polymarket_events(search_terms, all_events):
    """Find Polymarket events matching search terms."""
    matches = []
    for event in all_events:
        title = (event.get("title", "") or "").lower()
        desc = (event.get("description", "") or "").lower()
        combined = f"{title} {desc}"
        
        for term in search_terms:
            if term.lower() in combined:
                matches.append(event)
                break
    
    return matches


def parse_poly_price(market):
    """Extract YES price from a Polymarket market object."""
    prices = market.get("outcomePrices", "")
    if isinstance(prices, str):
        try:
            prices = json.loads(prices)
        except (json.JSONDecodeError, TypeError):
            prices = []
    
    if isinstance(prices, list) and len(prices) > 0:
        try:
            return float(prices[0]) * 100  # Convert to cents
        except (ValueError, TypeError):
            pass
    return None


def calculate_arb_profit(k_price, p_price, fee_mode="us"):
    """
    Calculate cross-platform arbitrage profit.
    
    Scenarios:
    1. Buy Kalshi YES + sell Polymarket YES (or buy Poly NO)
    2. Buy Polymarket YES + sell Kalshi YES (or buy Kalshi NO)
    
    Returns dict with direction, spread, and profit after fees.
    """
    if k_price is None or p_price is None:
        return None
    if k_price <= 0 or p_price <= 0:
        return None
    
    spread = abs(k_price - p_price)
    
    poly_fee = POLY_FEE_US if fee_mode == "us" else POLY_FEE_INTL
    
    if k_price < p_price:
        # Buy Kalshi YES (cheaper), sell Polymarket YES (more expensive)
        direction = "BUY_KALSHI_SELL_POLY"
        entry_cost = k_price
        exit_price = p_price
        kalshi_fee_cost = entry_cost * KALSHI_FEE / 100
        poly_fee_cost = exit_price * poly_fee / 100
        net_profit = (exit_price - entry_cost) - kalshi_fee_cost - poly_fee_cost
    else:
        # Buy Polymarket YES (cheaper), sell Kalshi YES (more expensive)
        direction = "BUY_POLY_SELL_KALSHI"
        entry_cost = p_price
        exit_price = k_price
        poly_fee_cost = entry_cost * poly_fee / 100
        kalshi_fee_cost = exit_price * KALSHI_FEE / 100
        net_profit = (exit_price - entry_cost) - kalshi_fee_cost - poly_fee_cost
    
    if net_profit <= 0:
        return None
    
    profit_pct = (net_profit / min(entry_cost, exit_price)) * 100 if min(entry_cost, exit_price) > 0 else 0
    
    return {
        "direction": direction,
        "spread_cents": round(spread, 1),
        "net_profit_cents": round(net_profit, 2),
        "profit_pct": round(profit_pct, 2),
        "kalshi_fee": round(kalshi_fee_cost, 2),
        "poly_fee": round(poly_fee_cost, 2),
        "k_price": round(k_price, 1),
        "p_price": round(p_price, 1),
    }


def match_kalshi_to_poly(k_market, poly_events, threshold=0.35):
    """
    Try to match a single Kalshi market to a Polymarket market using fuzzy matching.
    Returns best match or None.
    """
    k_title = k_market.get("title", "")
    best_score = 0
    best_match = None
    
    for event in poly_events:
        for pm in event.get("markets", []):
            p_title = pm.get("question", "") or event.get("title", "")
            score = similarity(k_title, p_title)
            if score > best_score:
                best_score = score
                best_match = {
                    "event": event,
                    "market": pm,
                    "score": score,
                }
    
    if best_score >= threshold and best_match:
        return best_match
    return None


def compare_known_pairs(poly_events):
    """Compare prices for known Kalshi-Polymarket pairs."""
    results = []
    
    for pair in EXTENDED_PAIRS:
        series = pair["kalshi_series"]
        
        # Fetch Kalshi markets
        k_markets = fetch_kalshi_series_markets(series)
        if not k_markets:
            continue
        
        # Find matching Polymarket events
        p_matches = search_polymarket_events(pair["poly_search"], poly_events)
        if not p_matches:
            continue
        
        # Compare each Kalshi market to best Polymarket match
        for km in k_markets[:10]:
            k_title = km.get("title", "")
            k_yes = km.get("yes_ask", 0) or km.get("last_price", 0) or 0
            
            if k_yes <= 0:
                continue
            
            # Find best Polymarket match for this specific market
            best_poly = None
            best_score = 0
            
            for pe in p_matches:
                for pm in pe.get("markets", []):
                    p_title = pm.get("question", "") or pe.get("title", "")
                    score = similarity(k_title, p_title)
                    if score > best_score:
                        best_score = score
                        best_poly = {
                            "event": pe,
                            "market": pm,
                            "score": score,
                        }
            
            if not best_poly or best_score < 0.25:
                continue
            
            p_price = parse_poly_price(best_poly["market"])
            if p_price is None:
                continue
            
            # Calculate arb opportunity
            arb_us = calculate_arb_profit(k_yes, p_price, "us")
            arb_intl = calculate_arb_profit(k_yes, p_price, "intl")
            
            p_title = (best_poly["market"].get("question", "") or 
                       best_poly["event"].get("title", ""))
            p_vol = float(best_poly["market"].get("volume", 0) or 0)
            
            results.append({
                "pair_name": pair["name"],
                "kalshi_ticker": km.get("ticker", ""),
                "kalshi_title": k_title[:60],
                "kalshi_yes": k_yes,
                "kalshi_volume": km.get("volume", 0) or 0,
                "poly_title": p_title[:60],
                "poly_yes": round(p_price, 1),
                "poly_volume": p_vol,
                "match_score": round(best_score, 3),
                "spread_cents": round(abs(k_yes - p_price), 1),
                "arb_us": arb_us,
                "arb_intl": arb_intl,
                "notes": pair.get("notes", ""),
                "kalshi_url": kalshi_url(km.get("ticker", "")),
            })
        
        time.sleep(0.2)  # Rate limit
    
    # Sort by spread (largest first)
    results.sort(key=lambda x: -x["spread_cents"])
    return results


def auto_discover_matches(poly_events):
    """Auto-discover cross-platform matches using fuzzy matching."""
    matches = []
    
    # Filter out sports from Polymarket
    sports_kw = ['nba', 'nfl', 'nhl', 'mlb', 'epl', 'serie', 'ufc', 'lol:', 'ncaa',
                 'cricket', 'soccer', 'rugby', 'tennis', 'golf']
    poly_filtered = [e for e in poly_events
                     if not any(kw in e.get('title', '').lower() for kw in sports_kw)]
    
    # Kalshi series to scan
    series_list = [
        "KXGDP", "KXCPI", "KXFEDRATE", "KXBITCOIN", "KXSP500",
        "KXGOVSHUTLENGTH", "KXTARIFFS", "KXGOVTCUTS", "KXRECESSION",
        "KXGREENLAND", "KXIRAN", "KXUKRAINE", "KXDOGE",
    ]
    
    kalshi_markets = []
    for series in series_list:
        data = api_get("/markets", {
            "series_ticker": series,
            "limit": 15,
            "status": "open",
        })
        if data:
            for m in data.get("markets", []):
                yes = m.get("yes_ask", 0) or 0
                if 5 <= yes <= 95 and (m.get("volume", 0) or 0) > 100:
                    kalshi_markets.append(m)
        time.sleep(0.15)
    
    print(f"  📊 Kalshi: {len(kalshi_markets)} markets | "
          f"Polymarket: {len(poly_filtered)} events")
    
    # Match each Kalshi market to Polymarket
    for km in kalshi_markets:
        best = match_kalshi_to_poly(km, poly_filtered, threshold=0.35)
        if not best:
            continue
        
        k_yes = km.get("yes_ask", 0) or km.get("last_price", 0) or 0
        p_price = parse_poly_price(best["market"])
        
        if p_price is None or k_yes <= 0:
            continue
        
        spread = abs(k_yes - p_price)
        arb_us = calculate_arb_profit(k_yes, p_price, "us")
        
        p_title = (best["market"].get("question", "") or
                   best["event"].get("title", ""))
        
        matches.append({
            "kalshi_ticker": km.get("ticker", ""),
            "kalshi_title": km.get("title", "")[:55],
            "kalshi_yes": k_yes,
            "poly_title": p_title[:55],
            "poly_yes": round(p_price, 1),
            "match_score": round(best["score"], 3),
            "spread_cents": round(spread, 1),
            "arb_us": arb_us,
            "kalshi_url": kalshi_url(km.get("ticker", "")),
        })
    
    # Sort by spread
    matches.sort(key=lambda x: -x["spread_cents"])
    return matches


def format_report(known_results, auto_results=None):
    """Format human-readable cross-platform report."""
    now = datetime.now(timezone.utc)
    lines = []
    lines.append("=" * 70)
    lines.append(f"🔄 CROSS-PLATFORM MONITOR — {now.strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("   Kalshi vs Polymarket Price Comparison")
    lines.append("=" * 70)
    
    # Known pairs
    if known_results:
        # Separate arb opportunities from just comparisons
        arb_opps = [r for r in known_results if r.get("arb_us")]
        no_arb = [r for r in known_results if not r.get("arb_us")]
        
        if arb_opps:
            lines.append(f"\n🚨 ARBITRAGE OPPORTUNITIES ({len(arb_opps)} found)")
            lines.append("-" * 60)
            
            for r in arb_opps[:15]:
                arb = r["arb_us"]
                lines.append(f"\n  🔥 {r['pair_name']}")
                lines.append(f"     K: {r['kalshi_yes']:>5.1f}¢ | {r['kalshi_title']}")
                lines.append(f"     P: {r['poly_yes']:>5.1f}¢ | {r['poly_title']}")
                lines.append(f"     📊 Spread: {r['spread_cents']:.1f}¢ | "
                             f"Match: {r['match_score']:.2f}")
                lines.append(f"     💰 US: {arb['direction']} → "
                             f"+{arb['net_profit_cents']:.1f}¢ "
                             f"({arb['profit_pct']:.1f}%) "
                             f"[fees: K:{arb['kalshi_fee']:.1f}¢ P:{arb['poly_fee']:.1f}¢]")
                if r.get("arb_intl"):
                    intl = r["arb_intl"]
                    lines.append(f"     💰 Intl: +{intl['net_profit_cents']:.1f}¢ "
                                 f"({intl['profit_pct']:.1f}%)")
                lines.append(f"     🔗 {r['kalshi_url']}")
        
        lines.append(f"\n📊 ALL COMPARISONS ({len(known_results)} pairs)")
        lines.append("-" * 60)
        lines.append(f"  {'Pair':<20} {'Kalshi':>7} {'Poly':>7} {'Spread':>7} {'Match':>6}")
        lines.append(f"  {'─'*20} {'─'*7} {'─'*7} {'─'*7} {'─'*6}")
        
        for r in known_results[:25]:
            flag = "🔥" if r["spread_cents"] > 5 else "  "
            lines.append(f"  {flag}{r['pair_name'][:18]:<18} "
                         f"{r['kalshi_yes']:>5.1f}¢ "
                         f"{r['poly_yes']:>5.1f}¢ "
                         f"{r['spread_cents']:>5.1f}¢ "
                         f"{r['match_score']:>5.2f}")
    else:
        lines.append("\n  ⚠️ No known pair comparisons available")
    
    # Auto-discovery
    if auto_results:
        lines.append(f"\n\n🤖 AUTO-DISCOVERED MATCHES ({len(auto_results)} found)")
        lines.append("-" * 60)
        
        for m in auto_results[:15]:
            flag = "🚨" if m["spread_cents"] > 5 else "  "
            arb_info = ""
            if m.get("arb_us"):
                arb_info = f" → +{m['arb_us']['net_profit_cents']:.1f}¢"
            
            lines.append(f"\n  {flag}[{m['match_score']:.2f}] "
                         f"K:{m['kalshi_yes']:>3.0f}¢ vs P:{m['poly_yes']:>5.1f}¢ "
                         f"(spread: {m['spread_cents']:.1f}¢){arb_info}")
            lines.append(f"     K: {m['kalshi_title']}")
            lines.append(f"     P: {m['poly_title']}")
    
    # Fee reference
    lines.append(f"\n{'='*70}")
    lines.append("📋 FEE REFERENCE:")
    lines.append(f"   Kalshi: ~{KALSHI_FEE*100:.1f}% | "
                 f"Polymarket US: ~{POLY_FEE_US*100:.2f}% | "
                 f"Polymarket Intl: ~{POLY_FEE_INTL*100:.0f}%")
    lines.append("⚠️  Cross-platform arb requires accounts on BOTH platforms")
    lines.append("    Execution risk: prices may change between leg entries")
    lines.append("=" * 70)
    
    return "\n".join(lines)


def save_results(known_results, auto_results, path=None):
    """Save results to JSON."""
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "cross-platform-results.json")
    
    output = {
        "scan_time": datetime.now(timezone.utc).isoformat(),
        "known_pairs": known_results,
        "auto_discovered": auto_results or [],
        "fee_structure": {
            "kalshi": KALSHI_FEE,
            "polymarket_us": POLY_FEE_US,
            "polymarket_intl": POLY_FEE_INTL,
        },
    }
    
    with open(path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\n💾 Results saved to {path}")


def main():
    do_auto = "--auto" in sys.argv
    json_only = "--json" in sys.argv
    
    print("📡 Fetching Polymarket events...")
    poly_events = fetch_polymarket_events(limit=200)
    print(f"   Found {len(poly_events)} active events\n")
    
    # Known pairs comparison
    print("🔍 Comparing known Kalshi-Polymarket pairs...")
    known_results = compare_known_pairs(poly_events)
    print(f"   {len(known_results)} comparisons made\n")
    
    # Auto-discovery
    auto_results = None
    if do_auto:
        print("🤖 Running auto-discovery...")
        auto_results = auto_discover_matches(poly_events)
        print(f"   {len(auto_results)} auto-matches found\n")
    
    if json_only:
        output = {
            "known_pairs": known_results,
            "auto_discovered": auto_results or [],
        }
        print(json.dumps(output, indent=2, default=str))
    else:
        report = format_report(known_results, auto_results)
        print(report)
    
    save_results(known_results, auto_results)
    
    return known_results, auto_results


if __name__ == "__main__":
    main()
