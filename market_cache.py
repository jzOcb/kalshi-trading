#!/usr/bin/env python3
"""
Kalshi Market Cache — 两层扫描系统

每日全量扫描: python3 market_cache.py --full
每小时增量扫描: python3 market_cache.py --delta
"""
import json
import os
import sys
import time
import requests
from datetime import datetime, timezone
from pathlib import Path

API_BASE = "https://api.elections.kalshi.com/trade-api/v2"
CACHE_FILE = Path(__file__).parent / "data" / "market_cache.json"
CACHE_FILE.parent.mkdir(exist_ok=True)

MIN_VOLUME = 200

def api_get(endpoint, params=None, retries=3):
    """API request with retry on 429"""
    for attempt in range(retries):
        try:
            resp = requests.get(f"{API_BASE}{endpoint}", params=params, timeout=15)
            if resp.status_code == 429:
                time.sleep(2 * (attempt + 1))
                continue
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            if attempt == retries - 1:
                print(f"API error: {e}", file=sys.stderr)
            time.sleep(1)
    return None


def fetch_all_markets():
    """Fetch all non-sports markets via Events API"""
    print("📡 Fetching all non-sports markets...", file=sys.stderr)
    all_markets = []
    cursor = None
    
    for page in range(30):
        params = {'limit': 100, 'status': 'open', 'with_nested_markets': 'true'}
        if cursor:
            params['cursor'] = cursor
        
        data = api_get('/events', params)
        if not data:
            break
            
        for e in data.get('events', []):
            cat = e.get('category', '')
            if cat not in ['Sports', 'Entertainment']:
                for m in e.get('markets', []):
                    m['category'] = cat
                    m['event_title'] = e.get('title', '')
                    all_markets.append(m)
        
        cursor = data.get('cursor')
        if not cursor or len(data.get('events', [])) < 100:
            break
        
        if page % 5 == 0:
            print(f"  Page {page}: {len(all_markets)} markets", file=sys.stderr)
    
    print(f"  Total: {len(all_markets)} markets", file=sys.stderr)
    return all_markets


def filter_candidates(markets):
    """Filter to high-edge candidates: extreme price + volume + short-term + high yield"""
    from datetime import datetime, timezone
    
    candidates = []
    now = datetime.now(timezone.utc)
    
    for m in markets:
        price = m.get('last_price', 50)
        volume = m.get('volume', 0) or m.get('volume_24h', 0)
        
        # Must have minimum volume
        if volume < MIN_VOLUME:
            continue
        
        # Must be extreme price
        if not (price <= 15 or price >= 85):
            continue
        
        # Check time to expiry (skip markets > 60 days out)
        close_str = m.get('close_time', '')
        if close_str:
            try:
                close = datetime.fromisoformat(close_str.replace('Z', '+00:00'))
                days = (close - now).days
                if days <= 0 or days > 60:
                    continue
            except:
                continue
        else:
            continue
        
        # Calculate annualized yield (skip if < 100%)
        side = "YES" if price >= 85 else "NO"
        cost = price if price >= 85 else (100 - price)
        ret = ((100 - cost) / cost) * 100 if cost > 0 else 0
        ann_yield = (ret / max(days, 1)) * 365
        
        if ann_yield < 100:
            continue
        
        candidates.append({
            'ticker': m.get('ticker', ''),
            'title': m.get('title', ''),
            'event': m.get('event_title', ''),
            'category': m.get('category', ''),
            'price': price,
            'volume': volume,
            'close_time': close_str,
            'days': days,
            'ann_yield': ann_yield,
            'side': side,
            'cost': cost,
            'yes_bid': m.get('yes_bid', 0),
            'yes_ask': m.get('yes_ask', 100),
        })
    
    # Sort by annualized yield (best opportunities first)
    candidates.sort(key=lambda x: -x['ann_yield'])
    return candidates


def save_cache(candidates):
    """Save candidates to cache file"""
    cache = {
        'updated': datetime.now(timezone.utc).isoformat(),
        'count': len(candidates),
        'markets': {c['ticker']: c for c in candidates}
    }
    with open(CACHE_FILE, 'w') as f:
        json.dump(cache, f, indent=2)
    print(f"💾 Cached {len(candidates)} candidates", file=sys.stderr)
    return cache


def load_cache():
    """Load cache from file"""
    if not CACHE_FILE.exists():
        return None
    with open(CACHE_FILE) as f:
        return json.load(f)


def fetch_current_prices(tickers, max_markets=100):
    """Fetch current prices for top N tickers (prioritize by extreme price)"""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    # Only check top N markets to keep it fast
    tickers = tickers[:max_markets]
    prices = {}
    
    def fetch_one(ticker):
        data = api_get(f'/markets/{ticker}')
        if data and 'market' in data:
            m = data['market']
            return ticker, {
                'price': m.get('last_price', 0),
                'yes_bid': m.get('yes_bid', 0),
                'yes_ask': m.get('yes_ask', 100),
                'volume': m.get('volume', 0) or m.get('volume_24h', 0),
            }
        return ticker, None
    
    # Parallel fetch with 5 workers
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(fetch_one, t): t for t in tickers}
        for future in as_completed(futures):
            ticker, data = future.result()
            if data:
                prices[ticker] = data
    
    return prices


def run_full_scan():
    """Daily full scan - fetch all markets, analyze, cache"""
    from report_v2 import scan_and_decide
    
    # Run full analysis
    result = scan_and_decide()
    
    # Also update cache for delta scans
    markets = fetch_all_markets()
    candidates = filter_candidates(markets)
    save_cache(candidates)
    
    return result


def run_delta_scan():
    """Hourly delta scan - use full analysis on cached candidates"""
    cache = load_cache()
    if not cache:
        print("⚠️ No cache found, running full scan instead", file=sys.stderr)
        return run_full_scan()
    
    cached_markets = cache.get('markets', {})
    if not cached_markets:
        return run_full_scan()
    
    # Import analysis functions from report_v2
    from report_v2 import score_market, fetch_market_details
    
    # Sort by most extreme prices first (best opportunities)
    sorted_markets = sorted(
        cached_markets.items(),
        key=lambda x: min(x[1].get('price', 50), 100 - x[1].get('price', 50))
    )
    
    # Only analyze top 50 most extreme (keeps it fast but thorough)
    top_markets = sorted_markets[:50]
    
    print(f"📊 Delta scan: analyzing top {len(top_markets)} candidates (of {len(cached_markets)} cached)...", file=sys.stderr)
    
    # Fetch details and score each market (with full analysis)
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    scored = []
    
    def analyze_one(item):
        ticker, cached = item
        # Fetch fresh market details
        m = fetch_market_details(ticker)
        if not m:
            return None
        # Add cached metadata
        m['category'] = cached.get('category', '')
        m['event_title'] = cached.get('event', '')
        # Run full scoring (includes news, data source, etc.)
        return score_market(m)
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(analyze_one, item): item for item in top_markets}
        done = 0
        for future in as_completed(futures):
            result = future.result()
            if result and result.get('score', 0) >= 50:
                scored.append(result)
            done += 1
            if done % 10 == 0:
                print(f"  Progress: {done}/{len(top_markets)} analyzed", file=sys.stderr)
    
    # Sort by score
    scored.sort(key=lambda x: -x.get('score', 0))
    
    # Format output (same style as full report)
    now = datetime.now(timezone.utc)
    lines = [f"⚡ Kalshi Delta Report — {now.strftime('%m/%d %H:%M UTC')}"]
    lines.append(f"分析了 {len(top_markets)} 个热门候选，找到 {len(scored)} 个机会\n")
    
    if scored:
        lines.append(f"🟢 推荐买入 ({len(scored)})\n")
        for i, s in enumerate(scored[:10], 1):
            lines.append(f"#{i} 🟢 BUY — 评分 {s['score']}/100")
            lines.append(f"   {s['title'][:60]}...")
            lines.append(f"   👉 {s['side']} @ {s['cost']}¢ | 仓位 $200")
            lines.append(f"   📊 {s['ann_yield']:.0f}% 年化 ({s['days']}天) | spread {s['spread']}¢ | 量 {s['vol']:,}")
            lines.append(f"   💡 {' | '.join(s['reasons'])}")
            lines.append(f"   🔗 https://kalshi.com/markets/{s['ticker'].lower()}")
            lines.append("")
    else:
        lines.append("😴 暂无符合标准的新机会")
    
    # Update cache timestamps
    cache['updated'] = now.isoformat()
    with open(CACHE_FILE, 'w') as f:
        json.dump(cache, f, indent=2)
    
    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 market_cache.py --full|--delta")
        sys.exit(1)
    
    mode = sys.argv[1]
    
    if mode == '--full':
        result = run_full_scan()
        print(result)
    elif mode == '--delta':
        result = run_delta_scan()
        print(result)
    else:
        print(f"Unknown mode: {mode}")
        sys.exit(1)


if __name__ == "__main__":
    main()
