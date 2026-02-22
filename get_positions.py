#!/usr/bin/env python3
"""
get_positions - 获取 Kalshi 当前仓位

功能：
    - 通过认证 API 获取当前持仓
    - 返回 JSON 格式的仓位详情
    - 可作为模块导入或独立运行
    - 支持查询多个账号

用法：
    python get_positions.py              # 打印仓位 JSON (默认账号)
    python get_positions.py --summary    # 打印摘要
    python get_positions.py --all-accounts  # 查询所有账号
    
依赖：
    - cryptography (签名)
    - KALSHI_API_KEY 和 KALSHI_PRIVATE_KEY_PATH 环境变量
"""
import warnings; warnings.filterwarnings("ignore", message="urllib3 v2")
import os, sys, json, time, base64
from urllib import request as urlrequest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

# Account definitions
ACCOUNTS = {
    'main': {
        'api_key': '5a61e197-6c14-40dc-a386-b26f261a1199',
        'key_path': '/Users/openclaw/clawd/kalshi/kalshi_private_key_main.pem',
        'label': '主账号'
    },
    'weather': {
        'api_key': '1d585efc-4fc0-4627-919f-6a109868e495',
        'key_path': '/Users/openclaw/clawd/kalshi/kalshi_private_key_weather.pem',
        'label': '天气账号'
    }
}

# Load credentials from env vars or .env file (default account)
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

# If still no credentials, use main account
if not API_KEY or not PRIVATE_KEY_PATH:
    API_KEY = ACCOUNTS['main']['api_key']
    PRIVATE_KEY_PATH = ACCOUNTS['main']['key_path']

def _load_key(key_path=None):
    path = key_path or PRIVATE_KEY_PATH
    with open(path, 'rb') as f:
        return serialization.load_pem_private_key(f.read(), password=None)

def kalshi_get(path, api_key=None, key_path=None):
    """Authenticated GET to Kalshi API."""
    use_api_key = api_key or API_KEY
    use_key_path = key_path or PRIVATE_KEY_PATH
    private_key = _load_key(use_key_path)
    timestamp = str(int(time.time() * 1000))
    msg = f'{timestamp}GET{path}'
    signature = private_key.sign(
        msg.encode('utf-8'),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256()
    )
    url = f'https://api.elections.kalshi.com{path}'
    req = urlrequest.Request(url)
    req.add_header('KALSHI-ACCESS-KEY', use_api_key)
    req.add_header('KALSHI-ACCESS-TIMESTAMP', timestamp)
    req.add_header('KALSHI-ACCESS-SIGNATURE', base64.b64encode(signature).decode())
    req.add_header('Accept', 'application/json')
    with urlrequest.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

def get_positions(api_key=None, key_path=None, account_label=None):
    """Return list of current position dicts with market details."""
    data = kalshi_get('/trade-api/v2/portfolio/positions', api_key, key_path)
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
            'account': account_label or '主账号',
        }
        # Get current market price (use default creds - market info is public)
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

def get_balance(api_key=None, key_path=None):
    """Return balance info (calculated from fills & settlements if API fails)."""
    # Try the balance endpoint first
    result = kalshi_get('/trade-api/v2/portfolio/balance', api_key, key_path)
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

def get_all_accounts_summary():
    """Get positions and balances from all accounts."""
    all_positions = []
    total_balance = 0
    total_portfolio = 0
    
    for name, acct in ACCOUNTS.items():
        try:
            balance = get_balance(acct['api_key'], acct['key_path'])
            positions = get_positions(acct['api_key'], acct['key_path'], acct['label'])
            
            bal = balance.get('balance', 0)
            port = balance.get('portfolio_value', 0)
            total_balance += bal
            total_portfolio += port
            
            print(f"\n{'='*50}")
            print(f"📊 {acct['label']} ({name})")
            print(f"{'='*50}")
            print(f"Balance: ${bal/100:.2f} | Portfolio: ${port/100:.2f}")
            print(f"Total: ${(bal+port)/100:.2f}")
            print()
            print(f"Open positions: {len(positions)}")
            for p in positions:
                direction = "LONG" if p['position'] > 0 else "SHORT"
                qty = abs(p['position'])
                print(f"  {p['ticker']}: {direction} {qty} | ${p['exposure_dollars']} | bid/ask: {p.get('yes_bid','?')}/{p.get('yes_ask','?')}")
                print(f"    {p.get('title', '?')}")
            
            all_positions.extend(positions)
        except Exception as e:
            print(f"\n❌ {acct['label']}: Error - {e}")
    
    print(f"\n{'='*50}")
    print(f"💰 TOTAL ALL ACCOUNTS")
    print(f"{'='*50}")
    print(f"Balance: ${total_balance/100:.2f} | Portfolio: ${total_portfolio/100:.2f}")
    print(f"Total: ${(total_balance+total_portfolio)/100:.2f}")
    print(f"Positions: {len(all_positions)}")
    
    return all_positions, total_balance, total_portfolio

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--summary', action='store_true', help='Print summary')
    parser.add_argument('--all-accounts', action='store_true', help='Query all accounts')
    parser.add_argument('--json', action='store_true', help='Output JSON')
    args = parser.parse_args()
    
    if args.all_accounts:
        all_pos, _, _ = get_all_accounts_summary()
        if args.json:
            print(json.dumps(all_pos, indent=2))
    else:
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
