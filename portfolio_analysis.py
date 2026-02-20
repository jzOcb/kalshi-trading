#!/usr/bin/env python3
import warnings; warnings.filterwarnings("ignore", message="urllib3 v2")
"""
Kalshi Portfolio Analysis — sizing, risk, Kelly, recommendations
Runs as part of hourly report. Reads live positions from API.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from get_positions import get_positions, get_balance


def estimate_win_prob(ticker, yes_bid):
    """Estimate win probability based on market type and fundamentals.
    
    ⚠️ GDP LESSON (2026-02-20): GDPNow predicted 4.2%, actual was 1.4%
    Error was 2.8pp! Use WIDE confidence intervals (σ=1.5, not 0.8)
    """
    # GDPNow is a ROUGH ESTIMATE, not truth
    # Q4 2025: GDPNow said 4.2%, actual was 1.4% (2.8pp error!)
    # Use conservative σ=1.5 to account for policy shocks (shutdown, tariffs)
    GDP_NOW = 2.0  # More conservative baseline (don't trust nowcast)
    GDP_SIGMA = 1.5  # Wide uncertainty (was 0.8, too narrow!)
    
    if "GDP" in ticker:
        threshold = float(ticker.split("-T")[-1])
        # Use WIDE normal distribution to reflect model uncertainty
        import math
        z = (GDP_NOW - threshold) / GDP_SIGMA
        prob = 0.5 * (1 + math.erf(z / math.sqrt(2)))
        # Cap probability - never assume >90% certainty for Nowcast-based markets
        return min(max(prob, 0.05), 0.90)  # Was 0.02-0.99, now 0.05-0.90
    
    elif "CPI" in ticker:
        threshold = float(ticker.split("-T")[-1])
        if threshold <= 0.0:
            return 0.99  # CPI almost always positive
        elif threshold >= 0.5:
            return 0.15  # High CPI unlikely
        elif threshold >= 0.4:
            return 0.30
        elif threshold >= 0.3:
            return 0.55
        else:
            return 0.80
    
    # Default: use market price as probability
    return yes_bid if yes_bid else 0.5


def kelly_fraction(prob, odds):
    """Kelly criterion: f* = (p*b - q) / b where b = odds, q = 1-p"""
    if odds <= 0:
        return 0
    q = 1 - prob
    f = (prob * odds - q) / odds
    return max(0, f)


def get_short_name(ticker):
    if "GDP" in ticker:
        return f"GDP >{ticker.split('-T')[-1]}%"
    elif "CPI" in ticker:
        return f"CPI >{ticker.split('-T')[-1]}%"
    return ticker


def main():
    try:
        balance = get_balance()
        cash = balance.get('balance', 0) / 100
        portfolio_val = balance.get('portfolio_value', 0) / 100
        total_val = cash + portfolio_val
    except Exception as e:
        print(f"⚠️ API error: {e}")
        return

    try:
        positions = get_positions()
    except Exception as e:
        print(f"⚠️ Position fetch error: {e}")
        return

    if not positions:
        return

    lines = []
    lines.append("📐 持仓分析")
    
    total_exposure = 0
    total_expected_profit = 0
    issues = []
    
    for p in positions:
        ticker = p['ticker']
        name = get_short_name(ticker)
        pos_count = p.get('position', 0)
        exposure = float(p.get('exposure_dollars', '0'))
        yes_bid = p.get('yes_bid', 0)
        yes_ask = p.get('yes_ask', 0)
        
        total_exposure += exposure
        
        # Determine side and entry
        if pos_count > 0:
            side = "YES"
            qty = pos_count
            entry_price = exposure / qty if qty else 0
            current_price = yes_bid
            max_payout = qty  # $1 per contract
        else:
            side = "NO"
            qty = abs(pos_count)
            entry_price = exposure / qty if qty else 0
            current_price = 1 - yes_ask if yes_ask else 0
            max_payout = qty

        max_profit = max_payout - exposure
        
        # Win probability
        raw_prob = estimate_win_prob(ticker, yes_bid)
        win_prob = raw_prob if side == "YES" else (1 - raw_prob)
        
        # Expected value
        ev = win_prob * max_profit - (1 - win_prob) * exposure
        total_expected_profit += ev
        
        # Kelly optimal sizing
        if win_prob > 0 and max_profit > 0:
            odds = max_profit / exposure  # net odds
            kelly = kelly_fraction(win_prob, odds)
            kelly_dollars = kelly * total_val * 0.25  # quarter-Kelly
        else:
            kelly = 0
            kelly_dollars = 0
        
        # Concentration
        pct = (exposure / total_val * 100) if total_val > 0 else 0
        
        # Return
        ret_pct = (max_profit / exposure * 100) if exposure > 0 else 0
        
        lines.append(f"  {name} {side}: {pct:.0f}%仓位 | 回报{ret_pct:.0f}% | 胜率{win_prob*100:.0f}% | EV ${ev:+.2f} | Kelly建议${kelly_dollars:.0f}")
        
        # Flag issues
        if pct > 40:
            issues.append(f"⚠️ {name}占{pct:.0f}%，过于集中（建议<40%）")
        if ret_pct < 10 and pct > 20:
            issues.append(f"💡 {name}回报{ret_pct:.0f}%但占{pct:.0f}%仓位，性价比低")
        
        # ====== GDP LESSON (2026-02-20) ======
        # GDPNow predicted 4.2%, actual was 1.4% = $179 loss
        is_nowcast_market = "GDP" in ticker or "CPI" in ticker
        high_entry = entry_price >= 0.85 if entry_price else False
        
        if is_nowcast_market and high_entry:
            issues.append(f"🔴 {name}: Nowcast市场+高价入场=GDP教训！模型误差可达2-3pp")
        elif is_nowcast_market:
            issues.append(f"⚠️ {name}: 依赖Nowcast模型，实际数据可能大幅偏离")
        elif high_entry and pct > 10:
            issues.append(f"⚠️ {name}: 高价入场({entry_price*100:.0f}¢)，错了亏损大")

    # Cash analysis
    cash_pct = (cash / total_val * 100) if total_val > 0 else 0
    if cash_pct < 5:
        issues.append(f"⚠️ 现金仅${cash:.2f}（{cash_pct:.0f}%），无加仓余地")

    lines.append(f"\n  总EV: ${total_expected_profit:+.2f} | 现金: ${cash:.2f} ({cash_pct:.0f}%)")
    
    if issues:
        lines.append("\n🔍 建议:")
        for issue in issues:
            lines.append(f"  {issue}")

    print("\n".join(lines))


if __name__ == "__main__":
    main()
