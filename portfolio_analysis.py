#!/usr/bin/env python3
"""
portfolio_analysis - Kalshi 持仓综合分析

功能：
    - 持仓健康度（胜率、EV、Kelly）
    - 实时 P&L（入场价 vs 现价）
    - 结算倒计时
    - 仓位占比

用法：
    python portfolio_analysis.py         # 生成综合报告
    from portfolio_analysis import main  # 被 pipeline 调用
    
依赖：
    - kalshi.client.KalshiClient
"""
import warnings; warnings.filterwarnings("ignore", message="urllib3 v2")
import sys
import os
import math
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../btc-arbitrage/src"))
from kalshi.client import KalshiClient

# 账户配置
ACCOUNTS = [
    ("main", "主账号"),
    ("weather", "副账号"),
]


def get_all_positions():
    """获取所有账户的持仓和市场数据"""
    all_positions = []
    total_cash = 0
    total_portfolio = 0
    market_cache = {}  # 缓存市场数据避免重复请求
    
    for account_id, account_label in ACCOUNTS:
        try:
            client = KalshiClient(account=account_id)
            
            # 获取余额
            balance = client.get_balance()
            total_cash += balance.get('balance', 0)
            total_portfolio += balance.get('portfolio_value', 0)
            
            # 获取持仓
            result = client.get_positions()
            positions = result.get("market_positions", [])
            
            for p in positions:
                if p.get('position', 0) != 0:
                    p['_account'] = account_label
                    
                    # 获取市场数据 (带缓存)
                    ticker = p.get('ticker', '')
                    if ticker and ticker not in market_cache:
                        try:
                            market_data = client.get_market(ticker)
                            market_cache[ticker] = market_data.get('market', {})
                        except:
                            market_cache[ticker] = {}
                    
                    p['_market'] = market_cache.get(ticker, {})
                    all_positions.append(p)
        except Exception as e:
            print(f"  ⚠️ {account_label}: {e}", file=sys.stderr)
    
    return all_positions, total_cash / 100, total_portfolio / 100


def estimate_win_prob(ticker, yes_bid):
    """Estimate win probability based on market type."""
    GDP_NOW = 2.0
    GDP_SIGMA = 1.5
    
    if "GDP" in ticker:
        threshold = float(ticker.split("-T")[-1])
        z = (GDP_NOW - threshold) / GDP_SIGMA
        prob = 0.5 * (1 + math.erf(z / math.sqrt(2)))
        return min(max(prob, 0.05), 0.90)
    
    elif "CPI" in ticker:
        threshold = float(ticker.split("-T")[-1])
        if threshold <= 0.0:
            return 0.99
        elif threshold >= 0.5:
            return 0.15
        elif threshold >= 0.4:
            return 0.30
        elif threshold >= 0.3:
            return 0.55
        else:
            return 0.80
    
    return yes_bid if yes_bid else 0.5


def kelly_fraction(prob, odds):
    """Kelly criterion: f* = (p*b - q) / b"""
    if odds <= 0:
        return 0
    q = 1 - prob
    f = (prob * odds - q) / odds
    return max(0, f)


def days_until(date_str):
    """Calculate days until settlement."""
    try:
        if 'T' in date_str:
            settle_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        else:
            settle_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = (settle_date - now).days
        return max(0, delta)
    except:
        return -1


def format_settlement(days):
    """Format settlement countdown."""
    if days == 0:
        return "今天"
    elif days == 1:
        return "明天"
    elif days < 0:
        return "已结算"
    else:
        return f"{days}天后"


def get_short_name(ticker, title=""):
    """Get short display name."""
    if "HIGHNY" in ticker:
        return "NYC高温"
    elif "HIGHAUS" in ticker:
        return "Austin高温"
    elif "GDP" in ticker:
        return f"GDP >{ticker.split('-T')[-1]}%"
    elif "CPI" in ticker:
        return f"CPI >{ticker.split('-T')[-1]}%"
    return ticker[:15]


def main():
    """Generate unified position report."""
    try:
        active_positions, cash, portfolio_val = get_all_positions()
        total_val = cash + portfolio_val
    except Exception as e:
        print(f"⚠️ API error: {e}")
        return

    if not active_positions:
        print("📐 持仓分析")
        print(f"  (无持仓) | 现金: ${cash:.2f}")
        return

    print("📐 持仓分析")
    
    total_cost = 0
    total_value = 0
    
    for p in active_positions:
        ticker = p.get('ticker', '')
        market = p.get('_market', {})
        title = market.get('title', '')
        position_count = p.get('position', 0)  # negative = NO, positive = YES
        total_traded_cents = p.get('total_traded', 0)
        
        # 确定方向
        side = "NO" if position_count < 0 else "YES"
        count = abs(position_count)
        
        # 价格数据 (API返回cents，除以100转换)
        yes_bid = market.get('yes_bid', 50) / 100
        yes_ask = market.get('yes_ask', 50) / 100
        no_bid = 1 - yes_ask  # NO bid = 1 - YES ask
        no_ask = 1 - yes_bid  # NO ask = 1 - YES bid
        
        current_price = no_bid if side == "NO" else yes_bid
        
        # 入场价 (从 total_traded 反推)
        cost = total_traded_cents / 100
        entry_price = cost / count if count > 0 else current_price
        
        # 当前市值
        value = current_price * count
        pnl = value - cost
        pnl_pct = (pnl / cost * 100) if cost > 0 else 0
        
        total_cost += cost
        total_value += value
        
        # 仓位占比
        position_pct = (value / total_val * 100) if total_val > 0 else 0
        
        # 策略指标
        prob = estimate_win_prob(ticker, yes_bid)
        if side == "NO":
            prob = 1 - prob
        
        potential_return = (1 - current_price) / current_price if current_price > 0 else 0
        ev = prob * potential_return * value - (1 - prob) * value
        kelly = kelly_fraction(prob, 1/current_price - 1) if current_price > 0 else 0
        kelly_dollars = kelly * cash
        
        # 结算时间
        close_time = market.get('close_time', '') or market.get('expiration_time', '')
        days = days_until(close_time)
        settle_str = format_settlement(days)
        
        # 输出
        price_change = int((current_price - entry_price) * 100)
        change_emoji = "✅" if pnl > 0 else ("🔻" if pnl < 0 else "")
        
        short_name = get_short_name(ticker, title)
        account_label = p.get('_account', '')
        acct_tag = f" [{account_label}]" if account_label else ""
        print(f"  {short_name} {side}{acct_tag} ({position_pct:.0f}%仓位)")
        print(f"    💰 {entry_price*100:.0f}¢ → {current_price*100:.0f}¢ ({price_change:+d}¢) | P&L: ${pnl:+.2f} ({pnl_pct:+.1f}%) {change_emoji}")
        print(f"    📊 胜率{prob*100:.0f}% | EV: ${ev:+.2f} | Kelly: ${kelly_dollars:.0f}")
        print(f"    ⏰ 结算: {settle_str}")
        print()
    
    # 汇总
    total_pnl = total_value - total_cost
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0
    cash_pct = (cash / total_val * 100) if total_val > 0 else 100
    
    print(f"  💼 总计: 市值 ${total_value:.2f} | P&L: ${total_pnl:+.2f} ({total_pnl_pct:+.1f}%) | 现金: ${cash:.2f} ({cash_pct:.0f}%)")


if __name__ == "__main__":
    main()
