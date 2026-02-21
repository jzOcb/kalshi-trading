#!/usr/bin/env python3
"""
get_positions - 获取 Kalshi 当前仓位

功能：
    - 通过认证 API 获取当前持仓
    - 返回 JSON 格式的仓位详情
    - 可作为模块导入或独立运行

用法：
    python get_positions.py              # 打印仓位 JSON
    python get_positions.py --summary    # 打印摘要
    
依赖：
    - cryptography (签名)
    - KALSHI_API_KEY 和 KALSHI_PRIVATE_KEY_PATH 环境变量
"""
import warnings; warnings.filterwarnings("ignore", message="urllib3 v2")
import os, sys, json, time, base64
from urllib import request as urlrequest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

# Load credentials from env vars or .env file
API_KEY = os.environ.get('KALSHI_API_KEY', '')
PRIVATE_KEY_PATH = os.environ.get('KALSHI_PRIVATE_KEY_PATH', '')

# If not in env, try loading from .env file
if not API_KEY or not PRIVATE_KEY_PATH:
    env_file = '/Users/openclaw/clawd/btc-arbitrage/.env'
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                if line.startswith('KALSHI_API_KEY='):
                    API_KEY = line.strip().split('=', 1)[1]
                elif line.startswith('KALSHI_PRIVATE_KEY_PATH='):
                    PRIVATE_KEY_PATH = line.strip().split('=', 1)[1]

def _load_key():
    with open(PRIVATE_KEY_PATH, 'rb') as f:
        return serialization.load_pem_private_key(f.read(), password=None)

def kalshi_get(path):
    """Authenticated GET to Kalshi API."""
    private_key = _load_key()
    timestamp = str(int(time.time() * 1000))
    msg = f'{timestamp}GET{path}'
    signature = private_key.sign(
        msg.encode('utf-8'),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256()
    )
    url = f'https://api.elections.kalshi.com{path}'
    req = urlrequest.Request(url)
    req.add_header('KALSHI-ACCESS-KEY', API_KEY)
    req.add_header('KALSHI-ACCESS-TIMESTAMP', timestamp)
    req.add_header('KALSHI-ACCESS-SIGNATURE', base64.b64encode(signature).decode())
    req.add_header('Accept', 'application/json')
    with urlrequest.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

def get_positions():
    """Return list of current position dicts with market details."""
    data = kalshi_get('/trade-api/v2/portfolio/positions')
    positions = data.get('market_positions', [])
    
    enriched = []
    for p in positions:
        ticker = p.get('ticker', '')
        pos = {
            'ticker': ticker,
            'series': ticker.rsplit('-', 1)[0] if '-' in ticker else ticker,
            'position': p.get('position', 0),
            'exposure': p.get('market_exposure', 0),
            'exposure_dollars': p.get('market_exposure_dollars', '0'),
            'realized_pnl': p.get('realized_pnl_dollars', '0'),
        }
        # Get current market price
        try:
            market = kalshi_get(f'/trade-api/v2/markets/{ticker}')
            m = market.get('market', {})
            pos['title'] = m.get('title', '')
            pos['yes_bid'] = m.get('yes_bid', 0) / 100
            pos['yes_ask'] = m.get('yes_ask', 0) / 100
            pos['status'] = m.get('status', '')
            pos['close_time'] = m.get('close_time', '')
        except:
            pass
        enriched.append(pos)
    
    return enriched

def get_position_tickers():
    """Return set of tickers we currently hold."""
    data = kalshi_get('/trade-api/v2/portfolio/positions')
    return {p.get('ticker', '') for p in data.get('market_positions', [])}

def get_position_series():
    """Return set of series prefixes we currently hold (e.g. KXGDP-26JAN30)."""
    tickers = get_position_tickers()
    series = set()
    for t in tickers:
        # Extract series: KXGDP-26JAN30-T2.5 → KXGDP-26JAN30
        parts = t.split('-')
        if len(parts) >= 2:
            series.add('-'.join(parts[:2]))
    return series

def get_balance():
    """Return balance info (calculated from fills & settlements if API fails)."""
    # Try the balance endpoint first
    result = kalshi_get('/trade-api/v2/portfolio/balance')
    if result and 'balance' in result:
        return result
    
    # Fallback: calculate from fills and settlements
    try:
        fills = kalshi_get('/trade-api/v2/portfolio/fills') or {}
        settlements = kalshi_get('/trade-api/v2/portfolio/settlements') or {}
        positions = kalshi_get('/trade-api/v2/portfolio/positions') or {}
        
        # Calculate total spent on positions
        total_cost = 0
        for f in fills.get('fills', []):
            price = f.get('price', 0)
            count = f.get('count', 0)
            side = f.get('side', 'yes')
            cost = price * count if side == 'yes' else (100 - price) * count
            total_cost += cost
        
        # Calculate settlement revenue
        total_revenue = sum(s.get('revenue', 0) for s in settlements.get('settlements', []))
        
        # Calculate current portfolio value from positions
        portfolio_value = 0
        for p in positions.get('market_positions', []):
            qty = abs(p.get('position', 0))
            # Use 50 as estimate if no price available (will be corrected by position_monitor)
            price = p.get('last_price', 50)
            portfolio_value += qty * price
        
        # Estimate cash (this is approximate - actual cash needs deposit info)
        # For now, return what we can calculate
        return {
            'balance': max(0, total_revenue - total_cost + 37928),  # ~$379 initial deposit estimate
            'portfolio_value': portfolio_value,
            'calculated': True  # Flag that this is calculated, not from API
        }
    except:
        return {'balance': 0, 'portfolio_value': 0, 'error': True}

if __name__ == '__main__':
    balance = get_balance()
    print(f"Balance: ${balance['balance']/100:.2f} | Portfolio: ${balance['portfolio_value']/100:.2f}")
    print(f"Total: ${(balance['balance']+balance['portfolio_value'])/100:.2f}")
    print()
    
    positions = get_positions()
    print(f"Open positions: {len(positions)}")
    for p in positions:
        direction = "LONG" if p['position'] > 0 else "SHORT"
        qty = abs(p['position'])
        print(f"  {p['ticker']}: {direction} {qty} | ${p['exposure_dollars']} | bid/ask: {p.get('yes_bid','?')}/{p.get('yes_ask','?')}")
        print(f"    {p.get('title', '?')}")
    
    print(f"\nPosition tickers: {get_position_tickers()}")
    print(f"Position series: {get_position_series()}")
