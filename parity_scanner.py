#!/usr/bin/env python3
"""
parity_scanner - Kalshi 套利扫描

功能：
    - 扫描价格偏差
    - 识别套利机会
    - 计算无风险收益

用法：
    python parity_scanner.py               # 扫描套利机会
    
依赖：
    - requests
"""

import json
import os
import sys
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta

# ── Kalshi API (same pattern as report_v2.py) ──

API_BASE = "https://api.elections.kalshi.com/trade-api/v2"

# Import validated functions from the project registry
try:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from kalshi.report_v2 import api_get, kalshi_url, format_vol
except ImportError:
    # Standalone fallback — replicate minimal API helper
    def api_get(endpoint, params=None):
        try:
            resp = requests.get(f"{API_BASE}{endpoint}", params=params, timeout=15)
            if resp.status_code == 429:
                time.sleep(3)
                resp = requests.get(f"{API_BASE}{endpoint}", params=params, timeout=15)
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


# Kalshi fee: ~0.7% per contract side
KALSHI_FEE_RATE = 0.007
# Default: total cost must be < $0.993 for profit after fees
DEFAULT_THRESHOLD = 0.993


def calculate_risk_score(profit_pct, volume, num_legs=2, is_bracket=False):
    """
    Risk score for arbitrage opportunity. Lower = safer.
    Adapted from Polymarket Arbitrage skill (community), tuned for Kalshi.
    
    Factors:
    - Volume (higher = lower risk, better liquidity)
    - Edge size (very high edge = likely stale data)
    - Number of legs (more legs = more execution risk)
    - Type (bracket arb has more legs than single-market)
    """
    score = 50  # Base

    # Volume factor
    if volume > 100_000:
        score -= 15
    elif volume > 10_000:
        score -= 5
    elif volume < 1_000:
        score += 20  # Low liquidity = risky

    # Edge factor (suspiciously high = stale data)
    if profit_pct > 5.0:
        score += 25  # Almost certainly stale/wrong
    elif profit_pct > 3.0:
        score += 15  # Suspicious
    elif profit_pct > 1.0:
        score += 5
    elif profit_pct < 0.3:
        score -= 5  # Tight, might close fast

    # Leg count (more legs = more execution risk)
    if num_legs > 4:
        score += 15
    elif num_legs > 2:
        score += 5

    # Bracket arbs slightly riskier (need all legs to fill)
    if is_bracket:
        score += 10

    return max(0, min(100, score))


def fetch_all_events(status="open", limit=200, fast_mode=False):
    """Fetch all open events from Kalshi."""
    events = []
    cursor = None
    while True:
        params = {"limit": limit, "status": status}
        if cursor:
            params["cursor"] = cursor
        data = api_get("/events", params)
        if not data:
            break
        batch = data.get("events", [])
        
        # Filter low-volume events in fast mode
        if fast_mode:
            filtered_batch = []
            for event in batch:
                # Estimate volume from event title or skip filtering here (do it later at market level)
                filtered_batch.append(event)
            batch = filtered_batch
        
        events.extend(batch)
        cursor = data.get("cursor", "")
        if not cursor or len(batch) < limit:
            break
        time.sleep(0.05)  # Reduced from 0.15 to 0.05 (50ms)
    return events


def fetch_markets_for_event(event_ticker, status="open"):
    """Fetch all markets under a specific event."""
    markets = []
    cursor = None
    while True:
        params = {"limit": 200, "status": status, "event_ticker": event_ticker}
        if cursor:
            params["cursor"] = cursor
        data = api_get("/markets", params)
        if not data:
            break
        batch = data.get("markets", [])
        markets.extend(batch)
        cursor = data.get("cursor", "")
        if not cursor or len(batch) < 200:
            break
    return markets


def fetch_markets_for_series(series_ticker, status="open"):
    """Fetch all markets for a series."""
    markets = []
    cursor = None
    while True:
        params = {"limit": 200, "status": status, "series_ticker": series_ticker}
        if cursor:
            params["cursor"] = cursor
        data = api_get("/markets", params)
        if not data:
            break
        batch = data.get("markets", [])
        markets.extend(batch)
        cursor = data.get("cursor", "")
        if not cursor or len(batch) < 200:
            break
        time.sleep(0.05)  # Reduced from 0.15 to 0.05 (50ms)
    return markets


def fetch_markets_for_event_parallel(event_ticker, status="open"):
    """Fetch markets for a single event - optimized for parallel execution."""
    try:
        markets = []
        cursor = None
        while True:
            params = {"limit": 200, "status": status, "event_ticker": event_ticker}
            if cursor:
                params["cursor"] = cursor
            data = api_get("/markets", params)
            if not data:
                break
            batch = data.get("markets", [])
            markets.extend(batch)
            cursor = data.get("cursor", "")
            if not cursor or len(batch) < 200:
                break
        return event_ticker, markets
    except Exception as e:
        print(f"    ⚠️ Error fetching markets for {event_ticker}: {e}", flush=True)
        return event_ticker, []


def check_single_market_parity(market):
    """
    Check YES/NO parity on a SINGLE market.
    
    On Kalshi, every market has YES and NO sides.
    If YES_ask + NO_ask < $1.00 (minus fees), buying both guarantees profit.
    
    Returns opportunity dict or None.
    """
    ticker = market.get("ticker", "")
    yes_ask = market.get("yes_ask", 0) or 0  # in cents
    no_ask = market.get("no_ask", 0) or 0    # in cents
    
    # Need both sides to have asks
    if yes_ask <= 0 or no_ask <= 0:
        return None
    
    # Total cost in cents
    total_cost_cents = yes_ask + no_ask
    total_cost_dollars = total_cost_cents / 100.0
    
    # Settlement always pays $1.00 for the winning side
    payout = 1.00
    
    # Fee on each leg (on winnings, not on cost)
    # Kalshi charges fee on profit: fee = max(0, payout - cost) * fee_rate
    # For parity arb: one side wins $1, one loses. Net payout = $1.00
    # Fee applies to the winning side's profit
    # Winning side profit = $1.00 - cost_of_winning_side
    # But we don't know which wins, so worst case fee:
    fee_yes_wins = max(0, (100 - yes_ask)) * KALSHI_FEE_RATE / 100  # fee if YES wins
    fee_no_wins = max(0, (100 - no_ask)) * KALSHI_FEE_RATE / 100    # fee if NO wins
    max_fee = max(fee_yes_wins, fee_no_wins)
    
    # Net profit (worst case)
    net_profit = payout - total_cost_dollars - max_fee
    
    if net_profit <= 0:
        return None
    
    profit_pct = (net_profit / total_cost_dollars) * 100
    
    vol = market.get("volume_24h", 0) or 0
    risk = calculate_risk_score(profit_pct, vol, num_legs=2)
    
    return {
        "type": "SINGLE_MARKET_PARITY",
        "ticker": ticker,
        "title": market.get("title", ""),
        "yes_ask": yes_ask,
        "no_ask": no_ask,
        "total_cost_cents": total_cost_cents,
        "total_cost_dollars": total_cost_dollars,
        "net_profit": round(net_profit, 4),
        "profit_pct": round(profit_pct, 2),
        "max_fee": round(max_fee, 4),
        "volume_24h": vol,
        "yes_bid": market.get("yes_bid", 0) or 0,
        "no_bid": market.get("no_bid", 0) or 0,
        "close_time": market.get("close_time", ""),
        "url": kalshi_url(ticker),
        "risk_score": risk,
        "stale_warning": profit_pct > 3.0,  # Edge >3% likely stale data
    }


def check_event_bracket_parity(markets, threshold=DEFAULT_THRESHOLD):
    """
    Check parity across multiple brackets within the same event.
    
    For exhaustive bracket events (e.g., GDP ranges that cover all possibilities),
    buying all YES positions should cost exactly $1.00. If total < $1.00, profit.
    
    Example: GDP brackets [<2%, 2-2.5%, 2.5-3%, >3%] should sum to 100%.
    If their YES asks sum to < 99.3¢, buying all is profitable.
    """
    if len(markets) < 2:
        return None
    
    # Get YES ask prices for all brackets
    brackets = []
    for m in markets:
        yes_ask = m.get("yes_ask", 0) or 0
        if yes_ask <= 0:
            continue
        brackets.append({
            "ticker": m.get("ticker", ""),
            "title": m.get("title", ""),
            "yes_ask": yes_ask,
            "volume": m.get("volume_24h", 0) or m.get("volume", 0) or 0,
        })
    
    if len(brackets) < 2:
        return None
    
    total_yes_cents = sum(b["yes_ask"] for b in brackets)
    total_yes_dollars = total_yes_cents / 100.0
    
    # For bracket events, exactly ONE bracket pays $1.00
    payout = 1.00
    
    # Fee: winning bracket pays fee on profit
    # Worst case: cheapest bracket wins (highest profit margin)
    min_cost = min(b["yes_ask"] for b in brackets)
    max_fee = max(0, (100 - min_cost)) * KALSHI_FEE_RATE / 100
    
    net_profit = payout - total_yes_dollars - max_fee
    
    if net_profit <= 0:
        return None
    
    profit_pct = (net_profit / total_yes_dollars) * 100
    
    total_vol = sum(b["volume"] for b in brackets)
    risk = calculate_risk_score(profit_pct, total_vol, num_legs=len(brackets), is_bracket=True)
    
    return {
        "type": "BRACKET_PARITY",
        "brackets": brackets,
        "num_brackets": len(brackets),
        "total_yes_cents": total_yes_cents,
        "total_yes_dollars": round(total_yes_dollars, 4),
        "net_profit": round(net_profit, 4),
        "profit_pct": round(profit_pct, 2),
        "max_fee": round(max_fee, 4),
        "event_title": markets[0].get("title", "").split("—")[0].strip() if markets else "",
        "risk_score": risk,
        "stale_warning": profit_pct > 3.0,
    }


def check_adjacent_bracket_parity(markets):
    """
    Check pairs of adjacent brackets for complementary parity.
    
    For two adjacent brackets that together cover a range,
    check if buying YES on both is cheaper than $1.00.
    This works when two brackets are the only possible outcomes
    for a subset of the probability space.
    """
    opportunities = []
    
    # Sort by title to get adjacent brackets
    sorted_markets = sorted(markets, key=lambda m: m.get("title", ""))
    
    for i in range(len(sorted_markets)):
        for j in range(i + 1, len(sorted_markets)):
            m1 = sorted_markets[i]
            m2 = sorted_markets[j]
            
            # Check single-market parity for each
            opp1 = check_single_market_parity(m1)
            if opp1:
                opportunities.append(opp1)
            opp2 = check_single_market_parity(m2)
            if opp2:
                opportunities.append(opp2)
    
    # Deduplicate by ticker
    seen = set()
    unique = []
    for opp in opportunities:
        if opp["ticker"] not in seen:
            seen.add(opp["ticker"])
            unique.append(opp)
    
    return unique


def scan_all_parity(threshold=DEFAULT_THRESHOLD, series_filter=None, fast_mode=False):
    """
    Main scanner: find all parity arbitrage opportunities.
    
    1. Fetch all events (or filtered by series)
    2. For each event, fetch markets IN PARALLEL
    3. Check single-market YES+NO parity
    4. Check bracket-level parity (all brackets sum < $1)
    5. Return sorted opportunities
    
    Args:
        fast_mode: Skip events with total volume <$1000 for faster scanning
    """
    now = datetime.now(timezone.utc)
    
    all_opportunities = []
    stats = {
        "events_scanned": 0,
        "markets_scanned": 0,
        "single_parity_found": 0,
        "bracket_parity_found": 0,
        "events_skipped_low_volume": 0,
        "scan_time": now.isoformat(),
    }
    
    if series_filter:
        # Scan specific series
        print(f"📡 Fetching markets for series {series_filter}...", flush=True)
        markets = fetch_markets_for_series(series_filter)
        stats["markets_scanned"] = len(markets)
        
        # Group by event
        events_map = {}
        for m in markets:
            evt = m.get("event_ticker", "unknown")
            events_map.setdefault(evt, []).append(m)
        
        print(f"   Found {len(markets)} markets across {len(events_map)} events", flush=True)
        
        for evt_ticker, evt_markets in events_map.items():
            stats["events_scanned"] += 1
            
            # Fast mode: skip low volume events
            if fast_mode:
                total_volume = sum(m.get("volume_24h", 0) or m.get("volume", 0) or 0 for m in evt_markets)
                if total_volume < 1000:  # Skip events <$1000 total volume
                    stats["events_skipped_low_volume"] += 1
                    continue
            
            # Check single-market parity for each
            for m in evt_markets:
                opp = check_single_market_parity(m)
                if opp:
                    all_opportunities.append(opp)
                    stats["single_parity_found"] += 1
            
            # Check bracket parity
            if len(evt_markets) >= 2:
                bracket_opp = check_event_bracket_parity(evt_markets, threshold)
                if bracket_opp:
                    all_opportunities.append(bracket_opp)
                    stats["bracket_parity_found"] += 1
    else:
        # Scan ALL events with parallel market fetching
        print("📡 Fetching all open events...", flush=True)
        events = fetch_all_events(fast_mode=fast_mode)
        print(f"   Found {len(events)} events", flush=True)
        print("🚀 Starting parallel market fetching...", flush=True)
        
        # Parallel market fetching with ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=6) as executor:
            # Submit all event market fetch tasks
            future_to_event = {
                executor.submit(fetch_markets_for_event_parallel, event.get("event_ticker", "")): event 
                for event in events if event.get("event_ticker")
            }
            
            processed_events = 0
            for future in as_completed(future_to_event):
                event = future_to_event[future]
                evt_ticker, markets = future.result()
                
                processed_events += 1
                stats["events_scanned"] += 1
                stats["markets_scanned"] += len(markets)
                
                # Fast mode: skip low volume events
                if fast_mode:
                    total_volume = sum(m.get("volume_24h", 0) or m.get("volume", 0) or 0 for m in markets)
                    if total_volume < 1000:  # Skip events <$1000 total volume
                        stats["events_skipped_low_volume"] += 1
                        continue
                
                # Check single-market parity for each
                for m in markets:
                    opp = check_single_market_parity(m)
                    if opp:
                        all_opportunities.append(opp)
                        stats["single_parity_found"] += 1
                
                # Check bracket parity (events with multiple markets)
                if len(markets) >= 2:
                    bracket_opp = check_event_bracket_parity(markets, threshold)
                    if bracket_opp:
                        all_opportunities.append(bracket_opp)
                        stats["bracket_parity_found"] += 1
                
                # Progress with flush
                if processed_events % 50 == 0:
                    skip_info = f" ({stats['events_skipped_low_volume']} skipped low vol)" if fast_mode else ""
                    print(f"   Progress: {processed_events}/{len(events)} events, "
                          f"{stats['markets_scanned']} markets, "
                          f"{len(all_opportunities)} opportunities{skip_info}", flush=True)
    
    # Sort by profit potential
    all_opportunities.sort(key=lambda x: -x.get("profit_pct", 0))
    stats["total_opportunities"] = len(all_opportunities)
    
    print(f"✅ Scan complete: {stats['events_scanned']} events, {stats['markets_scanned']} markets processed", flush=True)
    if fast_mode:
        print(f"   Fast mode: {stats['events_skipped_low_volume']} low-volume events skipped", flush=True)
    
    return all_opportunities, stats


def format_report(opportunities, stats):
    """Format human-readable report."""
    now = datetime.now(timezone.utc)
    lines = []
    lines.append("=" * 65)
    lines.append(f"🔄 PARITY ARBITRAGE SCAN — {now.strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("=" * 65)
    lines.append(f"Scanned: {stats['events_scanned']} events, {stats['markets_scanned']} markets")
    lines.append(f"Found: {stats['single_parity_found']} single-market + "
                 f"{stats['bracket_parity_found']} bracket opportunities\n")
    
    if not opportunities:
        lines.append("  ✅ No parity violations found — markets are efficiently priced")
        lines.append("  (This is normal; true parity arb is fleeting)\n")
        return "\n".join(lines)
    
    # Single-market parity
    singles = [o for o in opportunities if o.get("type") == "SINGLE_MARKET_PARITY"]
    brackets = [o for o in opportunities if o.get("type") == "BRACKET_PARITY"]
    
    if singles:
        lines.append(f"🎯 SINGLE-MARKET PARITY ({len(singles)} found)")
        lines.append("-" * 55)
        for opp in singles[:15]:
            emoji = "🚨" if opp["profit_pct"] > 1.0 else "⚠️"
            lines.append(f"\n  {emoji} {opp['title'][:60]}")
            lines.append(f"     YES@{opp['yes_ask']}¢ + NO@{opp['no_ask']}¢ = "
                         f"{opp['total_cost_cents']}¢ (${opp['total_cost_dollars']:.2f})")
            stale = " ⚠️ STALE DATA?" if opp.get('stale_warning') else ""
            lines.append(f"     💰 Profit: ${opp['net_profit']:.4f} ({opp['profit_pct']:.2f}%) "
                         f"after {opp['max_fee']:.4f} fee{stale}")
            lines.append(f"     📊 vol24h: {opp['volume_24h']} | "
                         f"risk: {opp.get('risk_score', '?')}/100 | "
                         f"bid spread: YES {opp['yes_bid']}¢ / NO {opp['no_bid']}¢")
            lines.append(f"     🔗 {opp['url']}")
    
    if brackets:
        lines.append(f"\n🏗️ BRACKET PARITY ({len(brackets)} found)")
        lines.append("-" * 55)
        for opp in brackets[:10]:
            emoji = "🚨" if opp["profit_pct"] > 1.0 else "⚠️"
            lines.append(f"\n  {emoji} {opp.get('event_title', 'Event')[:60]}")
            lines.append(f"     {opp['num_brackets']} brackets, "
                         f"total YES asks: {opp['total_yes_cents']}¢ "
                         f"(${opp['total_yes_dollars']:.2f})")
            stale = " ⚠️ STALE DATA?" if opp.get('stale_warning') else ""
            lines.append(f"     💰 Profit: ${opp['net_profit']:.4f} ({opp['profit_pct']:.2f}%){stale}"
                         f" | risk: {opp.get('risk_score', '?')}/100")
            for b in opp.get("brackets", [])[:6]:
                lines.append(f"       • {b['ticker']}: YES@{b['yes_ask']}¢ — "
                             f"{b['title'][:45]}")
    
    lines.append("\n" + "=" * 65)
    lines.append("⚠️  Use FOK (fill-or-kill) orders to avoid one-leg risk!")
    lines.append("    Verify both legs fill before counting as success.")
    lines.append("=" * 65)
    
    return "\n".join(lines)


def save_results(opportunities, stats, path=None):
    """Save results to JSON file."""
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "parity-scan-results.json")
    
    output = {
        "scan_time": stats.get("scan_time", datetime.now(timezone.utc).isoformat()),
        "stats": stats,
        "opportunities": opportunities,
    }
    
    with open(path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\n💾 Results saved to {path}")


def main():
    threshold = DEFAULT_THRESHOLD
    series_filter = None
    fast_mode = False
    
    # Parse args
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--threshold" and i + 1 < len(args):
            threshold = float(args[i + 1])
            i += 2
        elif args[i] == "--series" and i + 1 < len(args):
            series_filter = args[i + 1]
            i += 2
        elif args[i] == "--fast":
            fast_mode = True
            i += 1
        else:
            i += 1
    
    fast_info = " | Fast mode: skip <$1K volume events" if fast_mode else ""
    print(f"⚙️  Threshold: ${threshold:.3f} | Series: {series_filter or 'ALL'}{fast_info}\n", flush=True)
    
    start_time = time.time()
    opportunities, stats = scan_all_parity(threshold=threshold, series_filter=series_filter, fast_mode=fast_mode)
    scan_duration = time.time() - start_time
    
    print(f"\n⏱️  Scan completed in {scan_duration:.1f}s", flush=True)
    
    report = format_report(opportunities, stats)
    print(report)
    
    save_results(opportunities, stats)
    
    return opportunities, stats


if __name__ == "__main__":
    main()
