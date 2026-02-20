#!/usr/bin/env python3
"""
Full Kalshi Opportunity Scanner — 扫描所有非体育市场找高确定性机会
"""
import requests
import sys
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

API = "https://api.elections.kalshi.com/trade-api/v2"
MIN_VOLUME = 200
MIN_YIELD = 100  # 100% annualized minimum

def api_get(endpoint, params=None):
    try:
        resp = requests.get(f"{API}{endpoint}", params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except:
        return None

def fetch_all_non_sports_markets():
    """Fetch all non-sports markets via events API"""
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
                    m['category'] = cat  # Add category to market
                    m['event_title'] = e.get('title', '')
                    all_markets.append(m)
        cursor = data.get('cursor')
        if not cursor or len(data.get('events', [])) < 100:
            break
    return all_markets

def score_opportunity(m):
    """Score a market opportunity"""
    price = m.get('last_price', 50)
    volume = m.get('volume', 0) or m.get('volume_24h', 0)
    spread = (m.get('yes_ask', 100) - m.get('yes_bid', 0))
    
    # Must have volume
    if volume < MIN_VOLUME:
        return None
    
    # Extreme prices only (high confidence)
    if not (price <= 15 or price >= 85):
        return None
    
    # Calculate yield
    close_str = m.get('close_time', '')
    if not close_str:
        return None
    try:
        close = datetime.fromisoformat(close_str.replace('Z', '+00:00'))
        days = max((close - datetime.now(timezone.utc)).days, 1)
    except:
        return None
    
    side = "YES" if price >= 85 else "NO"
    cost = price if price >= 85 else (100 - price)
    ret = ((100 - cost) / cost) * 100 if cost > 0 else 0
    ann_yield = (ret / days) * 365
    
    if ann_yield < MIN_YIELD:
        return None
    
    score = int(ann_yield / 100) * 10
    if spread <= 3:
        score += 20
    elif spread <= 5:
        score += 10
    if volume >= 10000:
        score += 20
    elif volume >= 1000:
        score += 10
    
    return {
        'ticker': m.get('ticker', ''),
        'title': m.get('title', ''),
        'event': m.get('event_title', ''),
        'category': m.get('category', ''),
        'side': side,
        'price': price,
        'cost': cost,
        'volume': volume,
        'spread': spread,
        'days': days,
        'ann_yield': ann_yield,
        'score': score,
        'url': f"https://kalshi.com/markets/{m.get('ticker', '').lower()}"
    }

def main():
    print("📡 Fetching all non-sports markets...", file=sys.stderr)
    markets = fetch_all_non_sports_markets()
    print(f"   {len(markets)} markets loaded", file=sys.stderr)
    
    print("🔍 Scoring opportunities...", file=sys.stderr)
    opportunities = []
    for m in markets:
        opp = score_opportunity(m)
        if opp:
            opportunities.append(opp)
    
    opportunities.sort(key=lambda x: -x['score'])
    
    # Format output
    now = datetime.now(timezone.utc)
    print(f"⚡ Kalshi Full Opportunity Scan — {now.strftime('%m/%d %H:%M UTC')}")
    print(f"扫描了 {len(markets)} 个市场，找到 {len(opportunities)} 个高确定性机会\n")
    
    if not opportunities:
        print("😴 暂无符合标准的机会")
        return
    
    print(f"🟢 推荐买入 ({len(opportunities)})\n")
    
    for i, o in enumerate(opportunities[:20], 1):
        print(f"#{i} 🟢 BUY — 评分 {o['score']}/100")
        print(f"   {o['title'][:60]}...")
        print(f"   👉 {o['side']} @ {o['cost']}¢ | 仓位 $200")
        print(f"   📊 {o['ann_yield']:.0f}% 年化 ({o['days']}天) | spread {o['spread']}¢ | 量 {o['volume']:,}")
        print(f"   📁 {o['category']}")
        print(f"   🔗 {o['url']}")
        print()

if __name__ == "__main__":
    main()
