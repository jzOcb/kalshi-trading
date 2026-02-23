#!/usr/bin/env python3
"""
Kalshi MCP Server - Phase 1 (Read-Only)

提供 Kalshi API 的 MCP 接口，让 LLM 可以直接查询仓位、余额、市场等信息。
Phase 1 只包含读取操作，不涉及下单。

用法：
    # 直接运行
    python kalshi_mcp.py
    
    # 通过 OpenClaw 配置
    mcp.servers.kalshi:
      command: /Users/openclaw/clawd/kalshi/.venv/bin/python
      args: ["/Users/openclaw/clawd/kalshi/kalshi_mcp.py"]
"""

import os
import sys
import json
import time
import base64
from typing import Optional, List, Dict, Any
from enum import Enum

from pydantic import BaseModel, Field, ConfigDict
from mcp.server.fastmcp import FastMCP
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

# Initialize MCP Server
mcp = FastMCP("kalshi_mcp")

# Constants
API_BASE = "https://api.elections.kalshi.com"

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

# Default to main account
DEFAULT_ACCOUNT = 'main'


# ============================================================
# Shared Utilities (复用自 get_positions.py)
# ============================================================

def _load_key(key_path: str):
    """Load RSA private key from PEM file."""
    with open(key_path, 'rb') as f:
        return serialization.load_pem_private_key(f.read(), password=None)


def _kalshi_request(
    path: str,
    method: str = "GET",
    account: str = DEFAULT_ACCOUNT,
    params: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Authenticated request to Kalshi API.
    
    Args:
        path: API endpoint path (e.g., /trade-api/v2/markets)
        method: HTTP method
        account: Account name ('main' or 'weather')
        params: Query parameters for GET requests
    
    Returns:
        JSON response as dict
    """
    acct = ACCOUNTS.get(account, ACCOUNTS[DEFAULT_ACCOUNT])
    api_key = acct['api_key']
    key_path = acct['key_path']
    
    private_key = _load_key(key_path)
    timestamp = str(int(time.time() * 1000))
    
    # Build URL with query params
    if params:
        query_string = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
        full_path = f"{path}?{query_string}" if query_string else path
    else:
        full_path = path
    
    # Sign the request
    msg = f'{timestamp}{method}{full_path}'
    signature = private_key.sign(
        msg.encode('utf-8'),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256()
    )
    
    url = f'{API_BASE}{full_path}'
    req = urlrequest.Request(url, method=method)
    req.add_header('KALSHI-ACCESS-KEY', api_key)
    req.add_header('KALSHI-ACCESS-TIMESTAMP', timestamp)
    req.add_header('KALSHI-ACCESS-SIGNATURE', base64.b64encode(signature).decode())
    req.add_header('Accept', 'application/json')
    
    try:
        with urlrequest.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except HTTPError as e:
        error_body = e.read().decode() if e.fp else ""
        return {"error": f"HTTP {e.code}: {e.reason}", "details": error_body}
    except URLError as e:
        return {"error": f"Connection error: {e.reason}"}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


def _handle_error(result: Dict) -> str:
    """Format error response for MCP tools."""
    if "error" in result:
        details = result.get("details", "")
        return f"Error: {result['error']}" + (f"\nDetails: {details}" if details else "")
    return None


# ============================================================
# Pydantic Input Models
# ============================================================

class ResponseFormat(str, Enum):
    """Output format for tool responses."""
    MARKDOWN = "markdown"
    JSON = "json"


class AccountInput(BaseModel):
    """Base input with account selection."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    account: str = Field(
        default="main",
        description="Account to query: 'main' (主账号) or 'weather' (天气账号)"
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' for readable or 'json' for structured"
    )


class MarketInput(BaseModel):
    """Input for single market query."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    ticker: str = Field(
        ...,
        description="Market ticker (e.g., 'KXBTC-26FEB22-T97500' or 'KXGDP-26JAN30-T2.5')",
        min_length=3
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format"
    )


class SearchMarketsInput(BaseModel):
    """Input for market search."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    query: Optional[str] = Field(
        default=None,
        description="Search query (e.g., 'bitcoin', 'GDP', 'temperature')"
    )
    series_ticker: Optional[str] = Field(
        default=None,
        description="Filter by series ticker (e.g., 'KXBTC', 'KXGDP')"
    )
    status: Optional[str] = Field(
        default="active",
        description="Market status filter: 'active', 'settled', 'closed', or None for all"
    )
    limit: int = Field(
        default=20,
        description="Maximum results to return",
        ge=1,
        le=100
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format"
    )


class FillsInput(BaseModel):
    """Input for fills query."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    account: str = Field(default="main", description="Account: 'main' or 'weather'")
    ticker: Optional[str] = Field(default=None, description="Filter by specific ticker")
    limit: int = Field(default=50, ge=1, le=200, description="Maximum fills to return")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class SettlementsInput(BaseModel):
    """Input for settlements query."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    account: str = Field(default="main", description="Account: 'main' or 'weather'")
    limit: int = Field(default=50, ge=1, le=200, description="Maximum settlements to return")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


# ============================================================
# MCP Tools (Phase 1: Read-Only)
# ============================================================

@mcp.tool(
    name="kalshi_get_positions",
    annotations={
        "title": "Get Kalshi Positions",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def kalshi_get_positions(params: AccountInput) -> str:
    """
    获取当前持仓列表，包含市场详情。
    
    Returns positions with ticker, direction (LONG/SHORT), quantity,
    exposure, current bid/ask, and market title.
    
    Args:
        params: Account selection and output format
        
    Returns:
        Formatted positions list or JSON
    """
    result = _kalshi_request('/trade-api/v2/portfolio/positions', account=params.account)
    
    if err := _handle_error(result):
        return err
    
    positions = result.get('market_positions', [])
    
    if not positions:
        return f"No open positions in {params.account} account."
    
    # Enrich with market details
    enriched = []
    for p in positions:
        ticker = p.get('ticker', '')
        pos = {
            'ticker': ticker,
            'position': p.get('position', 0),
            'exposure_cents': p.get('market_exposure', 0),
            'exposure_dollars': f"${p.get('market_exposure', 0) / 100:.2f}",
            'realized_pnl': p.get('realized_pnl_dollars', '0'),
        }
        
        # Fetch market details
        market_result = _kalshi_request(f'/trade-api/v2/markets/{ticker}')
        if 'market' in market_result:
            m = market_result['market']
            pos['title'] = m.get('title', '')
            pos['yes_bid'] = m.get('yes_bid', 0) / 100
            pos['yes_ask'] = m.get('yes_ask', 0) / 100
            pos['status'] = m.get('status', '')
            pos['close_time'] = m.get('close_time', '')
        
        enriched.append(pos)
    
    if params.response_format == ResponseFormat.JSON:
        return json.dumps({"account": params.account, "positions": enriched}, indent=2)
    
    # Markdown format
    acct_label = ACCOUNTS.get(params.account, {}).get('label', params.account)
    lines = [f"# Positions - {acct_label}", ""]
    lines.append(f"**Total positions:** {len(enriched)}")
    lines.append("")
    
    for p in enriched:
        direction = "🟢 LONG" if p['position'] > 0 else "🔴 SHORT"
        qty = abs(p['position'])
        lines.append(f"## {p['ticker']}")
        lines.append(f"- **Direction:** {direction} × {qty}")
        lines.append(f"- **Exposure:** {p['exposure_dollars']}")
        lines.append(f"- **Bid/Ask:** {p.get('yes_bid', '?'):.0%} / {p.get('yes_ask', '?'):.0%}")
        lines.append(f"- **Title:** {p.get('title', 'N/A')}")
        lines.append(f"- **Status:** {p.get('status', 'N/A')}")
        lines.append("")
    
    return "\n".join(lines)


@mcp.tool(
    name="kalshi_get_balance",
    annotations={
        "title": "Get Kalshi Balance",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def kalshi_get_balance(params: AccountInput) -> str:
    """
    获取账户余额和投资组合价值。
    
    Returns cash balance and portfolio value for the specified account.
    
    Args:
        params: Account selection and output format
        
    Returns:
        Balance information
    """
    result = _kalshi_request('/trade-api/v2/portfolio/balance', account=params.account)
    
    if err := _handle_error(result):
        return err
    
    balance = result.get('balance', 0)
    portfolio = result.get('portfolio_value', 0)
    
    if params.response_format == ResponseFormat.JSON:
        return json.dumps({
            "account": params.account,
            "balance_cents": balance,
            "balance_dollars": balance / 100,
            "portfolio_cents": portfolio,
            "portfolio_dollars": portfolio / 100,
            "total_cents": balance + portfolio,
            "total_dollars": (balance + portfolio) / 100
        }, indent=2)
    
    acct_label = ACCOUNTS.get(params.account, {}).get('label', params.account)
    return f"""# Balance - {acct_label}

| Metric | Value |
|--------|-------|
| 💵 Cash Balance | ${balance / 100:.2f} |
| 📊 Portfolio Value | ${portfolio / 100:.2f} |
| 💰 **Total** | **${(balance + portfolio) / 100:.2f}** |
"""


@mcp.tool(
    name="kalshi_get_market",
    annotations={
        "title": "Get Market Details",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def kalshi_get_market(params: MarketInput) -> str:
    """
    获取单个市场的详细信息。
    
    Returns comprehensive market details including title, description,
    current prices, volume, and settlement info.
    
    Args:
        params: Market ticker and output format
        
    Returns:
        Market details
    """
    result = _kalshi_request(f'/trade-api/v2/markets/{params.ticker}')
    
    if err := _handle_error(result):
        return err
    
    market = result.get('market', {})
    
    if not market:
        return f"Market '{params.ticker}' not found."
    
    if params.response_format == ResponseFormat.JSON:
        return json.dumps(market, indent=2)
    
    # Markdown format
    yes_bid = market.get('yes_bid', 0) / 100
    yes_ask = market.get('yes_ask', 0) / 100
    volume = market.get('volume', 0)
    
    return f"""# {market.get('title', params.ticker)}

**Ticker:** `{params.ticker}`

## Prices
| Side | Bid | Ask |
|------|-----|-----|
| YES | {yes_bid:.0%} | {yes_ask:.0%} |
| NO | {1 - yes_ask:.0%} | {1 - yes_bid:.0%} |

## Details
- **Status:** {market.get('status', 'N/A')}
- **Volume:** {volume:,} contracts
- **Open Interest:** {market.get('open_interest', 0):,}
- **Close Time:** {market.get('close_time', 'N/A')}

## Description
{market.get('subtitle', 'No description available.')}
"""


@mcp.tool(
    name="kalshi_search_markets",
    annotations={
        "title": "Search Kalshi Markets",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def kalshi_search_markets(params: SearchMarketsInput) -> str:
    """
    搜索市场。支持关键词搜索和按 series_ticker 筛选。
    
    Use this to find markets by topic (e.g., 'bitcoin', 'GDP', 'temperature')
    or to list all markets in a series.
    
    Args:
        params: Search query, filters, and output format
        
    Returns:
        List of matching markets
    """
    api_params = {"limit": params.limit}
    
    if params.series_ticker:
        api_params["series_ticker"] = params.series_ticker
    if params.status:
        api_params["status"] = params.status
    
    result = _kalshi_request('/trade-api/v2/markets', params=api_params)
    
    if err := _handle_error(result):
        return err
    
    markets = result.get('markets', [])
    
    # Filter by query if provided
    if params.query:
        query_lower = params.query.lower()
        markets = [
            m for m in markets
            if query_lower in m.get('title', '').lower()
            or query_lower in m.get('ticker', '').lower()
            or query_lower in m.get('subtitle', '').lower()
        ]
    
    if not markets:
        return f"No markets found matching your criteria."
    
    if params.response_format == ResponseFormat.JSON:
        return json.dumps({"count": len(markets), "markets": markets}, indent=2)
    
    # Markdown format
    lines = [f"# Market Search Results", ""]
    lines.append(f"**Found:** {len(markets)} markets")
    lines.append("")
    
    for m in markets[:params.limit]:
        yes_bid = m.get('yes_bid', 0) / 100
        yes_ask = m.get('yes_ask', 0) / 100
        lines.append(f"### {m.get('ticker', 'N/A')}")
        lines.append(f"**{m.get('title', 'N/A')}**")
        lines.append(f"- Bid/Ask: {yes_bid:.0%} / {yes_ask:.0%}")
        lines.append(f"- Status: {m.get('status', 'N/A')}")
        lines.append(f"- Volume: {m.get('volume', 0):,}")
        lines.append("")
    
    return "\n".join(lines)


@mcp.tool(
    name="kalshi_get_fills",
    annotations={
        "title": "Get Trade Fills",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def kalshi_get_fills(params: FillsInput) -> str:
    """
    获取成交记录（历史交易）。
    
    Returns list of executed trades with price, quantity, and timestamps.
    
    Args:
        params: Account, optional ticker filter, limit, and format
        
    Returns:
        List of fills
    """
    api_params = {"limit": params.limit}
    if params.ticker:
        api_params["ticker"] = params.ticker
    
    result = _kalshi_request('/trade-api/v2/portfolio/fills', account=params.account, params=api_params)
    
    if err := _handle_error(result):
        return err
    
    fills = result.get('fills', [])
    
    if not fills:
        return f"No fills found."
    
    if params.response_format == ResponseFormat.JSON:
        return json.dumps({"account": params.account, "count": len(fills), "fills": fills}, indent=2)
    
    # Markdown format
    acct_label = ACCOUNTS.get(params.account, {}).get('label', params.account)
    lines = [f"# Trade Fills - {acct_label}", ""]
    lines.append(f"**Total fills:** {len(fills)}")
    lines.append("")
    lines.append("| Ticker | Side | Price | Qty | Time |")
    lines.append("|--------|------|-------|-----|------|")
    
    for f in fills[:50]:  # Limit display
        ticker = f.get('ticker', 'N/A')[:20]
        side = f.get('side', '?').upper()
        price = f.get('price', 0)
        count = f.get('count', 0)
        created = f.get('created_time', 'N/A')[:10]
        lines.append(f"| {ticker} | {side} | {price}¢ | {count} | {created} |")
    
    return "\n".join(lines)


@mcp.tool(
    name="kalshi_get_settlements",
    annotations={
        "title": "Get Settlements",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def kalshi_get_settlements(params: SettlementsInput) -> str:
    """
    获取结算记录（已结算市场的盈亏）。
    
    Returns list of settled positions with revenue and outcome.
    
    Args:
        params: Account, limit, and format
        
    Returns:
        List of settlements
    """
    api_params = {"limit": params.limit}
    
    result = _kalshi_request('/trade-api/v2/portfolio/settlements', account=params.account, params=api_params)
    
    if err := _handle_error(result):
        return err
    
    settlements = result.get('settlements', [])
    
    if not settlements:
        return f"No settlements found."
    
    if params.response_format == ResponseFormat.JSON:
        return json.dumps({"account": params.account, "count": len(settlements), "settlements": settlements}, indent=2)
    
    # Markdown format
    acct_label = ACCOUNTS.get(params.account, {}).get('label', params.account)
    lines = [f"# Settlements - {acct_label}", ""]
    
    total_revenue = sum(s.get('revenue', 0) for s in settlements)
    lines.append(f"**Total settlements:** {len(settlements)}")
    lines.append(f"**Total revenue:** ${total_revenue / 100:.2f}")
    lines.append("")
    lines.append("| Ticker | Revenue | Settled |")
    lines.append("|--------|---------|---------|")
    
    for s in settlements[:50]:
        ticker = s.get('ticker', 'N/A')[:25]
        revenue = s.get('revenue', 0)
        settled = s.get('settled_time', 'N/A')[:10]
        emoji = "🟢" if revenue > 0 else "🔴" if revenue < 0 else "⚪"
        lines.append(f"| {ticker} | {emoji} ${revenue / 100:.2f} | {settled} |")
    
    return "\n".join(lines)


# ============================================================
# Main Entry Point
# ============================================================

if __name__ == "__main__":
    mcp.run()
