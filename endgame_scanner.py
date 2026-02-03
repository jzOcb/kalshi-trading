#!/usr/bin/env python3
"""
Kalshi Endgame Strategy Scanner

Finds markets settling within 1-7 days where outcome is near-certain (>95%
probability) but price hasn't fully caught up. These are low-risk, high
annualized return opportunities.

Based on: RESEARCH-V2.md Strategy 4 (High-Probability Auto-Compounding)
- Chinese community: "尾盘扫单也是鲸鱼和机器人的常用策略"
- PolyTrack guide: "buying near-certain outcomes (95-99% probability)"

Uses existing validated functions from report_v2.py (per __init__.py registry).

Usage:
    python3 kalshi/endgame_scanner.py                # Full scan (1-7 days)
    python3 kalshi/endgame_scanner.py --max-days 3   # Only 1-3 days
    python3 kalshi/endgame_scanner.py --min-prob 90  # Lower probability threshold
"""

import json
import os
import sys
import time
import requests
from datetime import datetime, timezone, timedelta

# ── Kalshi API (same pattern as report_v2.py) ──

API_BASE = "https://api.elections.kalshi.com/trade-api/v2"

# Import validated functions from the project registry
try:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from kalshi.report_v2 import (
        api_get, fetch_market_details, kalshi_url, format_vol,
        analyze_rules, score_market, search_news,
    )
    HAVE_REPORT_V2 = True
except ImportError:
    HAVE_REPORT_V2 = False
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

    def search_news(query, max_results=5):
        import re
        from urllib.parse import quote
        results = []
        try:
            url = f"https://news.google.com/rss/search?q={quote(query)}&hl=en-US&gl=US&ceid=US:en"
            r = requests.get(url, timeout=10)
            titles = re.findall(r'<title>(.*?)</title>', r.text)
            dates = re.findall(r'<pubDate>(.*?)</pubDate>', r.text)
            for i, title in enumerate(titles[1:max_results + 1]):
                results.append({"title": title, "date": dates[i] if i < len(dates) else ""})
        except Exception:
            pass
        return results


# Skip categories that are unpredictable
SKIP_CATEGORIES = {"Sports", "Entertainment"}

# Known upcoming economic data releases (manually maintained)
# These help estimate "near-certain" probability for economic indicators
KNOWN_RELEASES = {
    "CPI": {
        "description": "Consumer Price Index",
        "source": "BLS",
        "keywords": ["cpi", "consumer price", "inflation"],
    },
    "GDP": {
        "description": "Gross Domestic Product",
        "source": "BEA",
        "keywords": ["gdp", "gross domestic", "economic growth"],
    },
    "JOBS": {
        "description": "Employment / Jobs Report",
        "source": "BLS",
        "keywords": ["unemployment", "jobs", "nonfarm", "payroll"],
    },
    "FED": {
        "description": "Federal Reserve Rate Decision",
        "source": "Fed",
        "keywords": ["federal reserve", "fomc", "interest rate", "fed rate"],
    },
}


def fetch_settling_soon_markets(max_days=7):
    """Fetch ALL open markets settling within max_days."""
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=max_days)
    
    all_markets = []
    cursor = None
    
    while True:
        params = {"limit": 200, "status": "open"}
        if cursor:
            params["cursor"] = cursor
        data = api_get("/markets", params)
        if not data:
            break
        
        for m in data.get("markets", []):
            close_str = m.get("close_time", "")
            if not close_str:
                continue
            try:
                close = datetime.fromisoformat(close_str.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue
            
            days = (close - now).total_seconds() / 86400
            if 0 < days <= max_days:
                m["_days_to_settle"] = round(days, 1)
                m["_close_dt"] = close
                all_markets.append(m)
        
        cursor = data.get("cursor", "")
        if not cursor or len(data.get("markets", [])) < 200:
            break
        time.sleep(0.15)
    
    return all_markets


def estimate_probability_from_price(market):
    """
    Estimate implied probability from current market price.
    
    On Kalshi, last_price ≈ implied probability in cents.
    YES at 95¢ ≈ 95% implied probability of YES outcome.
    """
    price = market.get("last_price", 50) or 50
    yes_bid = market.get("yes_bid", 0) or 0
    yes_ask = market.get("yes_ask", 0) or 0
    
    # Use mid-price if available, else last_price
    if yes_bid > 0 and yes_ask > 0:
        mid = (yes_bid + yes_ask) / 2
    else:
        mid = price
    
    return mid  # Already in cents ≈ probability percentage


def estimate_actual_probability(market, news_data=None):
    """
    Estimate the ACTUAL probability of the outcome, independent of market price.
    
    Uses:
    1. Market price as baseline (efficient markets assumption)
    2. News sentiment boost/reduction
    3. Time decay (closer to settlement → more certainty)
    4. Official data source availability
    
    Returns estimated probability (0-100) and confidence level.
    """
    price = estimate_probability_from_price(market)
    days = market.get("_days_to_settle", 7)
    title = market.get("title", "").lower()
    
    # Start with market-implied probability
    est_prob = price
    confidence = "MEDIUM"
    factors = []
    
    # Time decay bonus: markets settling very soon have less uncertainty
    if days <= 1:
        # Within 24 hours — if price is already >90, actual prob is likely higher
        if price >= 90:
            est_prob = min(99, price + 2)
            factors.append(f"⏰ <1 day to settle, time decay +2")
    elif days <= 3:
        if price >= 90:
            est_prob = min(99, price + 1)
            factors.append(f"⏰ <3 days to settle, time decay +1")
    
    # Check for official data source (higher confidence)
    for release_key, release_info in KNOWN_RELEASES.items():
        if any(kw in title for kw in release_info["keywords"]):
            factors.append(f"📊 {release_info['source']} data ({release_info['description']})")
            confidence = "HIGH"
            break
    
    # News sentiment adjustment
    if news_data:
        news_items = news_data if isinstance(news_data, list) else []
        if len(news_items) >= 3:
            factors.append(f"📰 {len(news_items)} news articles found")
            # More news = more information = price should be more accurate
            # But if price is extreme, news confirms it
            if price >= 92:
                est_prob = min(99, est_prob + 1)
    
    # Spread-based confidence
    yes_bid = market.get("yes_bid", 0) or 0
    yes_ask = market.get("yes_ask", 0) or 0
    spread = yes_ask - yes_bid if yes_ask > 0 and yes_bid > 0 else 99
    if spread <= 3:
        factors.append("💧 Tight spread (good liquidity)")
        confidence = "HIGH" if confidence != "LOW" else "MEDIUM"
    elif spread > 10:
        factors.append("⚠️ Wide spread (poor liquidity)")
        confidence = "LOW"
    
    return est_prob, confidence, factors


def find_endgame_opportunities(markets, min_probability=95, max_price=95):
    """
    Find endgame opportunities: markets where actual probability is high
    but price hasn't fully caught up.
    
    An endgame opportunity exists when:
    - Estimated probability > min_probability (default 95%)
    - Current price < max_price (default 95¢)
    - The gap = estimated_probability - current_price > 0
    
    Also looks for the inverse: markets where NO is near-certain
    (YES price < 5¢ but should be even lower).
    """
    opportunities = []
    
    for m in markets:
        ticker = m.get("ticker", "")
        title = m.get("title", "")
        price = m.get("last_price", 50) or 50
        days = m.get("_days_to_settle", 7)
        yes_ask = m.get("yes_ask", 0) or 0
        no_ask = m.get("no_ask", 0) or 0
        spread = (yes_ask - (m.get("yes_bid", 0) or 0)) if yes_ask > 0 else 99
        
        # Skip markets with wide spreads (untradeable)
        if spread > 15:
            continue
        
        # Check YES side: high probability, price not yet reflecting it
        if price >= 85 and price <= max_price:
            est_prob, confidence, factors = estimate_actual_probability(m)
            
            if est_prob > min_probability and est_prob > price:
                edge = est_prob - price
                cost = yes_ask if yes_ask > 0 else price
                profit_if_yes = 100 - cost
                ann_yield = ((profit_if_yes / cost) / max(days, 0.1)) * 365 * 100 if cost > 0 else 0
                
                opportunities.append({
                    "ticker": ticker,
                    "title": title,
                    "side": "YES",
                    "current_price": price,
                    "entry_cost": cost,
                    "estimated_probability": round(est_prob, 1),
                    "edge": round(edge, 1),
                    "profit_if_win": profit_if_yes,
                    "annualized_yield": round(ann_yield, 0),
                    "days_to_settlement": days,
                    "spread": spread,
                    "volume_24h": m.get("volume_24h", 0) or 0,
                    "confidence": confidence,
                    "factors": factors,
                    "close_time": m.get("close_time", ""),
                    "url": kalshi_url(ticker),
                })
        
        # Check NO side: price < 5 means NO is likely (>95% NO probability)
        elif price <= 15 and price >= 1:
            no_prob = 100 - price  # NO implied probability
            est_prob, confidence, factors = estimate_actual_probability(m)
            est_no_prob = 100 - est_prob  # Flip for NO side
            
            # Actually re-estimate from NO perspective
            if no_prob >= min_probability:
                no_cost = no_ask if no_ask > 0 else (100 - price)
                if no_cost <= 0 or no_cost > max_price:
                    continue
                profit_if_no = 100 - no_cost
                ann_yield = ((profit_if_no / no_cost) / max(days, 0.1)) * 365 * 100 if no_cost > 0 else 0
                
                opportunities.append({
                    "ticker": ticker,
                    "title": title,
                    "side": "NO",
                    "current_price": price,
                    "entry_cost": no_cost,
                    "estimated_probability": round(no_prob, 1),
                    "edge": round(max(0, no_prob - (100 - price)), 1),
                    "profit_if_win": profit_if_no,
                    "annualized_yield": round(ann_yield, 0),
                    "days_to_settlement": days,
                    "spread": spread,
                    "volume_24h": m.get("volume_24h", 0) or 0,
                    "confidence": confidence,
                    "factors": factors,
                    "close_time": m.get("close_time", ""),
                    "url": kalshi_url(ticker),
                })
    
    # Sort by annualized yield (highest first)
    opportunities.sort(key=lambda x: (-x["annualized_yield"], -x["edge"]))
    
    return opportunities


def enrich_with_decision_engine(opportunities):
    """
    Cross-reference opportunities with the validated decision engine (score_market).
    Only runs if report_v2 is importable.
    """
    if not HAVE_REPORT_V2:
        return opportunities
    
    enriched = []
    for opp in opportunities[:20]:  # Limit API calls
        ticker = opp["ticker"]
        detailed = fetch_market_details(ticker)
        if detailed:
            # Run through the validated scoring engine
            result = score_market(detailed)
            if result:
                opp["decision_score"] = result.get("score", 0)
                opp["decision"] = result.get("decision", "N/A")
                opp["decision_reasons"] = result.get("reasons", [])
        enriched.append(opp)
        time.sleep(0.2)  # Rate limit
    
    return enriched


def enrich_with_news(opportunities):
    """Cross-reference top opportunities with news data."""
    for opp in opportunities[:10]:  # Only top 10
        title = opp.get("title", "")
        # Extract key search terms
        import re
        clean = re.sub(r'[^\w\s]', ' ', title)
        terms = [t for t in clean.split() if len(t) > 2][:4]
        query = " ".join(terms)
        
        if query:
            news = search_news(query, max_results=3)
            if news:
                opp["news"] = [n.get("title", "") for n in news]
                opp["news_count"] = len(news)
            time.sleep(0.3)  # Rate limit news API
    
    return opportunities


def format_report(opportunities, stats):
    """Format human-readable endgame report."""
    now = datetime.now(timezone.utc)
    lines = []
    lines.append("=" * 65)
    lines.append(f"🎯 ENDGAME STRATEGY SCAN — {now.strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("=" * 65)
    lines.append(f"Scanned: {stats.get('total_markets', 0)} markets settling in "
                 f"1-{stats.get('max_days', 7)} days")
    lines.append(f"Found: {len(opportunities)} endgame opportunities\n")
    
    if not opportunities:
        lines.append("  ✅ No endgame opportunities found")
        lines.append("  (Markets are efficiently priced near settlement)\n")
        return "\n".join(lines)
    
    # Group by confidence
    high_conf = [o for o in opportunities if o.get("confidence") == "HIGH"]
    med_conf = [o for o in opportunities if o.get("confidence") == "MEDIUM"]
    low_conf = [o for o in opportunities if o.get("confidence") == "LOW"]
    
    for label, group in [("🟢 HIGH CONFIDENCE", high_conf),
                         ("🟡 MEDIUM CONFIDENCE", med_conf),
                         ("🔴 LOW CONFIDENCE", low_conf)]:
        if not group:
            continue
        lines.append(f"\n{label} ({len(group)} opportunities)")
        lines.append("-" * 55)
        
        for opp in group[:10]:
            decision_tag = ""
            if "decision_score" in opp:
                decision_tag = f" [Score:{opp['decision_score']}]"
            
            lines.append(f"\n  {'🚨' if opp['edge'] > 3 else '⚠️'} "
                         f"{opp['title'][:60]}{decision_tag}")
            lines.append(f"     👉 {opp['side']} @ {opp['entry_cost']}¢ "
                         f"(market price: {opp['current_price']}¢)")
            lines.append(f"     📊 Est. prob: {opp['estimated_probability']}% | "
                         f"Edge: +{opp['edge']}¢ | "
                         f"Profit: {opp['profit_if_win']}¢")
            lines.append(f"     📈 Ann. yield: {opp['annualized_yield']:.0f}% | "
                         f"Settles in {opp['days_to_settlement']:.1f}d | "
                         f"Spread: {opp['spread']}¢")
            
            if opp.get("factors"):
                for f in opp["factors"]:
                    lines.append(f"     {f}")
            
            if opp.get("news"):
                lines.append(f"     📰 News:")
                for n in opp["news"][:2]:
                    lines.append(f"        • {n[:70]}")
            
            if opp.get("decision_reasons"):
                lines.append(f"     🧠 Decision: {' | '.join(opp['decision_reasons'][:3])}")
            
            lines.append(f"     🔗 {opp['url']}")
    
    lines.append("\n" + "=" * 65)
    lines.append("💡 Endgame strategy: buy near-certain outcomes for guaranteed small profit")
    lines.append("   Risk: outcome uncertainty. Always verify with latest data/news.")
    lines.append("=" * 65)
    
    return "\n".join(lines)


def save_results(opportunities, stats, path=None):
    """Save results to JSON."""
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "endgame-scan-results.json")
    
    output = {
        "scan_time": datetime.now(timezone.utc).isoformat(),
        "stats": stats,
        "opportunities": opportunities,
    }
    
    with open(path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\n💾 Results saved to {path}")


def main():
    max_days = 7
    min_prob = 95
    
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--max-days" and i + 1 < len(args):
            max_days = int(args[i + 1])
            i += 2
        elif args[i] == "--min-prob" and i + 1 < len(args):
            min_prob = int(args[i + 1])
            i += 2
        else:
            i += 1
    
    print(f"⚙️  Max days: {max_days} | Min probability: {min_prob}%\n")
    
    # Step 1: Fetch markets settling soon
    print("📡 Fetching markets settling within", max_days, "days...")
    markets = fetch_settling_soon_markets(max_days)
    print(f"   Found {len(markets)} markets\n")
    
    stats = {
        "total_markets": len(markets),
        "max_days": max_days,
        "min_probability": min_prob,
    }
    
    # Step 2: Find endgame opportunities
    print("🔍 Scanning for endgame opportunities...")
    opportunities = find_endgame_opportunities(markets, min_probability=min_prob)
    print(f"   Found {len(opportunities)} opportunities\n")
    
    # Step 3: Enrich with decision engine (if available)
    if HAVE_REPORT_V2 and opportunities:
        print("🧠 Running decision engine on top opportunities...")
        opportunities = enrich_with_decision_engine(opportunities)
    
    # Step 4: Enrich with news
    if opportunities:
        print("📰 Checking news for top opportunities...")
        opportunities = enrich_with_news(opportunities)
    
    # Step 5: Report
    report = format_report(opportunities, stats)
    print(report)
    
    save_results(opportunities, stats)
    
    return opportunities, stats


if __name__ == "__main__":
    main()
