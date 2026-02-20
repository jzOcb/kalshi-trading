#!/usr/bin/env python3
import warnings; warnings.filterwarnings("ignore", message="urllib3 v2")
"""Kalshi Position Monitor — 实时监控持仓盈亏"""

import json
import os
import sys
import requests
from datetime import datetime, timezone

API_BASE = "https://api.elections.kalshi.com/trade-api/v2"
POSITIONS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "positions.json")
LAST_PRICES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "last_prices.json")

ALERT_FLAG = "/tmp/kalshi_position_alert.flag"
ALERT_TEXT = "/tmp/kalshi_position_alert.txt"
REPORT_FLAG = "/tmp/kalshi_position_report.flag"
REPORT_TEXT = "/tmp/kalshi_position_report.txt"

ALERT_THRESHOLD = 5  # cents


def load_positions():
    with open(POSITIONS_FILE, "r") as f:
        return json.load(f)["positions"]


def load_last_prices():
    if os.path.exists(LAST_PRICES_FILE):
        with open(LAST_PRICES_FILE, "r") as f:
            return json.load(f)
    return {}


def save_last_prices(prices):
    with open(LAST_PRICES_FILE, "w") as f:
        json.dump(prices, f, indent=2)


def fetch_market(ticker):
    """Fetch market data from Kalshi public API."""
    try:
        resp = requests.get(f"{API_BASE}/markets/{ticker}", timeout=15)
        resp.raise_for_status()
        data = resp.json()
        market = data.get("market", {})
        return {
            "last_price": market.get("last_price", 0),
            "yes_bid": market.get("yes_bid", 0),
            "yes_ask": market.get("yes_ask", 0),
            "status": market.get("status", "unknown"),
            "title": market.get("title", ticker),
        }
    except Exception as e:
        print(f"⚠️ Error fetching {ticker}: {e}", file=sys.stderr)
        return None


def get_current_price(market_data, side):
    """Get relevant price for a position side."""
    if not market_data:
        return None
    last = market_data["last_price"]
    if side == "YES":
        return last
    else:
        # NO price = 100 - YES price
        return 100 - last if last else None


def get_short_name(ticker):
    """Extract readable name from ticker."""
    if "GDP" in ticker:
        # e.g. KXGDP-26JAN30-T2.5 → GDP >2.5%
        threshold = ticker.split("-T")[-1]
        return f"GDP >{threshold}%"
    elif "CPI" in ticker:
        threshold = ticker.split("-T")[-1]
        return f"CPI >{threshold}%"
    elif "INFL" in ticker:
        threshold = ticker.split("-T")[-1]
        return f"Inflation >{threshold}%"
    return ticker


def days_until(date_str):
    """Calculate days until settlement."""
    try:
        settle_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = (settle_date - now).days
        return max(0, delta)
    except:
        return -1


def format_price_change(change):
    """Format price change with emoji."""
    if change > 0:
        return f"+{change}¢ ✅"
    elif change < 0:
        return f"{change}¢ 🔻"
    else:
        return "0¢"


def format_pnl(pnl):
    """Format P&L with sign."""
    if pnl > 0:
        return f"+${pnl:.2f}"
    elif pnl < 0:
        return f"-${abs(pnl):.2f}"
    else:
        return "$0.00"


def main():
    positions = load_positions()
    last_prices = load_last_prices()
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%m/%d %H:%M UTC")

    total_cost = 0
    total_value = 0
    lines = []
    alerts = []
    new_prices = {}
    has_error = False

    # Find nearest settlement
    nearest_settle = None
    nearest_days = 9999
    nearest_name = ""

    for i, pos in enumerate(positions, 1):
        ticker = pos["ticker"]
        side = pos["side"]
        entry_price = pos["entry_price"]
        contracts = pos["contracts"]
        cost = pos["cost"]
        settles = pos["settles"]
        short_name = get_short_name(ticker)

        # For NO side, entry_price in config is the NO price (100 - yes_price_at_entry)
        # So for NO: entry = 100 - entry_price means the YES entry was entry_price
        # Actually: entry_price for NO means we paid (100 - entry_price) per NO contract
        # Let me reconsider: entry_price=89 for NO side means the YES was at 89, NO was at 11
        # cost=19.58 for 22 contracts → 19.58/22 = 0.89 per contract = 89¢
        # Wait, that's 89¢ per NO contract? That's expensive for NO.
        # Actually looking at the data: NO entry_price=89 means we bought NO at 89¢ per contract
        # But that seems high. Let me check: cost=19.58, contracts=22 → 19.58/22=0.89 = 89¢
        # So yes, we bought NO at 89¢. That means YES was at 11¢.
        # Current value for NO position = contracts * (100 - current_yes_price) / 100

        market = fetch_market(ticker)
        if not market:
            has_error = True
            lines.append(f"{i}. {short_name} {side}\n   ⚠️ API获取失败\n")
            continue

        current_yes = market["last_price"]
        if side == "YES":
            current_price = current_yes  # in cents
        else:
            current_price = 100 - current_yes  # NO price in cents

        new_prices[ticker] = current_yes  # always store YES price

        # Calculate values
        current_value = contracts * current_price / 100  # in dollars
        price_change = current_price - entry_price
        position_pnl = current_value - cost

        total_cost += cost
        total_value += current_value

        # Check for alert
        old_yes = last_prices.get(ticker)
        if old_yes is not None:
            if side == "YES":
                price_move = current_yes - old_yes
            else:
                price_move = (100 - current_yes) - (100 - old_yes)
            if abs(price_move) >= ALERT_THRESHOLD:
                alerts.append(f"🚨 {short_name} {side}: {abs(price_move)}¢ {'上涨' if price_move > 0 else '下跌'}! "
                             f"({entry_price}¢ → {current_price}¢)")

        # Settlement tracking
        days = days_until(settles)
        if 0 <= days < nearest_days:
            nearest_days = days
            settle_dt = datetime.strptime(settles, "%Y-%m-%d")
            nearest_settle = f"{settle_dt.month}月{settle_dt.day}日"
            nearest_name = short_name

        # Format line
        change_str = format_price_change(price_change)
        pnl_str = format_pnl(position_pnl)
        lines.append(
            f"{i}. {short_name} {side}\n"
            f"   入场{entry_price}¢ → 现在{current_price}¢ ({change_str})\n"
            f"   市值 ${current_value:.2f} / 成本 ${cost:.2f} | {pnl_str}\n"
        )

    # Save prices for next comparison
    save_last_prices(new_prices)

    # Build report
    total_pnl = total_value - total_cost
    pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0
    total_pnl_str = format_pnl(total_pnl)

    report = f"📊 Kalshi 持仓监控 — {timestamp}\n\n"
    report += f"💰 总投入: ${total_cost:.2f} | 当前市值: ${total_value:.2f} | P&L: {total_pnl_str} ({pnl_pct:+.1f}%)\n\n"
    report += "\n".join(lines)

    if nearest_settle:
        report += f"\n⏰ 下次结算: {nearest_name} {nearest_settle} ({nearest_days}天后)"

    if has_error:
        report += "\n\n⚠️ 部分数据获取失败，价格可能不完整"

    print(report)

    # Write output files
    if alerts:
        alert_msg = f"🚨 Kalshi 仓位价格警报 — {timestamp}\n\n"
        alert_msg += "\n".join(alerts)
        alert_msg += "\n\n" + report

        with open(ALERT_TEXT, "w") as f:
            f.write(alert_msg)
        with open(ALERT_FLAG, "w") as f:
            f.write(datetime.now(timezone.utc).isoformat())
        print("\n⚠️ ALERT written!", file=sys.stderr)
    else:
        # Normal report
        with open(REPORT_TEXT, "w") as f:
            f.write(report)
        with open(REPORT_FLAG, "w") as f:
            f.write(datetime.now(timezone.utc).isoformat())


if __name__ == "__main__":
    main()
