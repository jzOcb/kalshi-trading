#!/usr/bin/env python3
"""
Kalshi Weather Paper Trading System

Automatically selects weather market opportunities with sufficient edge,
records paper trades, and tracks results through settlement.

Usage:
    python3 kalshi/weather_paper_trader.py                    # Run scan + select trades
    python3 kalshi/weather_paper_trader.py --check            # Check existing trade results
    python3 kalshi/weather_paper_trader.py --min-edge 10      # Custom edge threshold (cents)
    python3 kalshi/weather_paper_trader.py --report           # Generate report only
"""

import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta

# Import from our scanner
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kalshi.weather_scanner import (
    scan_weather_markets, format_report, save_results,
    api_get, kalshi_url, format_vol, CITY_NWS_MAP,
    fetch_nws_forecast, fetch_nws_quantitative,
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TRADES_FILE = os.path.join(SCRIPT_DIR, "weather-paper-trades.json")
REPORT_FILE = os.path.join(SCRIPT_DIR, "weather-scan-report.md")
RESULTS_FILE = os.path.join(SCRIPT_DIR, "weather-scan-results.json")

# Paper trading config
DEFAULT_MIN_EDGE = 10      # cents
DEFAULT_POSITION_SIZE = 100  # contracts (hypothetical)
MAX_TRADES_PER_SCAN = 10
CONFIDENCE_MULTIPLIER = {
    "HIGH": 1.0,
    "MEDIUM": 0.7,
    "LOW": 0.4,
}


def load_trades():
    """Load existing paper trades."""
    if os.path.exists(TRADES_FILE):
        with open(TRADES_FILE) as f:
            return json.load(f)
    return {"trades": [], "summary": {}}


def save_trades(data):
    """Save paper trades."""
    with open(TRADES_FILE, "w") as f:
        json.dump(data, f, indent=2, default=str)


def select_paper_trades(opportunities, min_edge=DEFAULT_MIN_EDGE):
    """
    Select opportunities for paper trading based on criteria:
    1. Edge >= min_edge cents
    2. Has actual bid/ask pricing (spread < 20)
    3. HIGH or MEDIUM confidence preferred
    4. Not already in open trades
    """
    # Load existing trades
    trade_data = load_trades()
    existing_tickers = set()
    for t in trade_data.get("trades", []):
        if t.get("status") == "open":
            existing_tickers.add(t["ticker"])

    candidates = []
    for opp in opportunities:
        ticker = opp.get("ticker", "")
        edge = abs(opp.get("edge", 0))
        confidence = opp.get("nws_confidence", "LOW")
        spread = opp.get("spread", 99)
        yes_bid = opp.get("yes_bid", 0)
        yes_ask = opp.get("yes_ask", 0)

        # Skip if already trading
        if ticker in existing_tickers:
            continue

        # Minimum edge
        if edge < min_edge:
            continue

        # Must have real pricing
        if yes_bid <= 0 or yes_ask <= 0:
            continue

        # Reasonable spread
        if spread > 20:
            continue

        # Score: edge * confidence multiplier
        conf_mult = CONFIDENCE_MULTIPLIER.get(confidence, 0.3)
        score = edge * conf_mult

        candidates.append({
            "opp": opp,
            "score": score,
            "confidence": confidence,
        })

    # Sort by score descending
    candidates.sort(key=lambda x: -x["score"])

    # Take top N
    selected = candidates[:MAX_TRADES_PER_SCAN]
    return selected


def create_paper_trade(opp):
    """Create a paper trade record from an opportunity."""
    now = datetime.now(timezone.utc)
    side = opp.get("best_side", "YES")
    
    if side == "YES":
        entry_price = opp.get("yes_ask", 0)
        exit_price_if_win = 100
    else:
        entry_price = opp.get("no_ask", 0) or (100 - opp.get("yes_bid", 100))
        exit_price_if_win = 100

    trade = {
        "id": f"WT-{now.strftime('%Y%m%d%H%M%S')}-{opp['ticker'][:10]}",
        "ticker": opp["ticker"],
        "title": opp["title"],
        "city": opp["city"],
        "metric": opp["metric"],
        "threshold": opp["threshold"],
        "direction": opp["direction"],
        "date": opp.get("date"),
        "side": side,
        "entry_price": entry_price,
        "entry_time": now.isoformat(),
        "nws_value": opp["nws_value"],
        "nws_prob": opp["nws_prob"],
        "nws_confidence": opp["nws_confidence"],
        "nws_detail": opp.get("nws_detail", ""),
        "edge": opp["edge"],
        "market_price_at_entry": opp["market_price"],
        "yes_bid_at_entry": opp["yes_bid"],
        "yes_ask_at_entry": opp["yes_ask"],
        "spread_at_entry": opp["spread"],
        "position_size": DEFAULT_POSITION_SIZE,
        "max_loss": entry_price * DEFAULT_POSITION_SIZE / 100,  # in dollars
        "max_profit": (100 - entry_price) * DEFAULT_POSITION_SIZE / 100,
        "close_time": opp.get("close_time", ""),
        "url": opp["url"],
        "status": "open",
        "result": None,       # "win" or "loss"
        "settlement_price": None,
        "pnl": None,
        "settled_time": None,
        "notes": "",
    }
    return trade


def check_trade_results(trade_data):
    """
    Check if any open trades have settled.
    Queries Kalshi API for market status.
    """
    updated = 0
    for trade in trade_data.get("trades", []):
        if trade.get("status") != "open":
            continue

        ticker = trade.get("ticker", "")
        # Query market status
        data = api_get(f"/markets/{ticker}")
        if not data:
            continue

        market = data.get("market", {})
        status = market.get("status", "")
        result = market.get("result", "")

        if status in ("settled", "closed") and result:
            trade["status"] = "settled"
            trade["settled_time"] = datetime.now(timezone.utc).isoformat()

            if result == "yes":
                trade["settlement_price"] = 100
                if trade["side"] == "YES":
                    trade["result"] = "win"
                    trade["pnl"] = (100 - trade["entry_price"]) * trade["position_size"] / 100
                else:
                    trade["result"] = "loss"
                    trade["pnl"] = -trade["entry_price"] * trade["position_size"] / 100
            elif result == "no":
                trade["settlement_price"] = 0
                if trade["side"] == "NO":
                    trade["result"] = "win"
                    trade["pnl"] = (100 - trade["entry_price"]) * trade["position_size"] / 100
                else:
                    trade["result"] = "loss"
                    trade["pnl"] = -trade["entry_price"] * trade["position_size"] / 100

            updated += 1
            print(f"   ✅ Settled: {ticker} → {result.upper()} | "
                  f"Trade {trade['result']} | PnL: ${trade['pnl']:.2f}", flush=True)

        time.sleep(0.2)

    return updated


def compute_summary(trade_data):
    """Compute trading summary statistics."""
    trades = trade_data.get("trades", [])
    if not trades:
        return {}

    total = len(trades)
    open_trades = [t for t in trades if t["status"] == "open"]
    settled = [t for t in trades if t["status"] == "settled"]
    wins = [t for t in settled if t["result"] == "win"]
    losses = [t for t in settled if t["result"] == "loss"]

    total_pnl = sum(t.get("pnl", 0) or 0 for t in settled)
    avg_edge = sum(abs(t.get("edge", 0)) for t in trades) / max(total, 1)

    summary = {
        "total_trades": total,
        "open_trades": len(open_trades),
        "settled_trades": len(settled),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": f"{100*len(wins)/max(len(settled),1):.1f}%",
        "total_pnl": round(total_pnl, 2),
        "avg_edge_at_entry": round(avg_edge, 1),
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }

    # By confidence level
    for conf in ["HIGH", "MEDIUM", "LOW"]:
        conf_trades = [t for t in settled if t.get("nws_confidence") == conf]
        conf_wins = [t for t in conf_trades if t["result"] == "win"]
        if conf_trades:
            summary[f"{conf.lower()}_confidence_win_rate"] = \
                f"{100*len(conf_wins)/len(conf_trades):.0f}% ({len(conf_wins)}/{len(conf_trades)})"

    return summary


def generate_report(opportunities, stats, trade_data):
    """Generate comprehensive markdown report."""
    now = datetime.now(timezone.utc)
    lines = []

    lines.append(f"# 🌤️ Weather Market Scan Report")
    lines.append(f"**Generated:** {now.strftime('%Y-%m-%d %H:%M UTC')}\n")

    # ── Scan Statistics ──
    lines.append("## 📊 Scan Statistics\n")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Total weather markets | {stats.get('total_weather_markets', 0)} |")
    lines.append(f"| Successfully parsed | {stats.get('parseable_markets', 0)} ({stats.get('parse_rate', '?')}) |")
    lines.append(f"| With NWS forecast | {stats.get('total_with_forecast', 0)} |")
    lines.append(f"| Opportunities (edge ≥ {stats.get('min_edge', 5)}¢) | {len(opportunities)} |")
    lines.append(f"| Cities checked | {len(stats.get('cities_checked', []))} |")
    lines.append("")

    skipped = stats.get("skipped", {})
    if skipped:
        lines.append("### Skipped Breakdown\n")
        for key, val in skipped.items():
            if val:
                lines.append(f"- **{key}**: {val}")
        lines.append("")

    # ── Top Opportunities ──
    lines.append("## 🎯 Top Opportunities\n")
    if not opportunities:
        lines.append("No significant mispricings found.\n")
    else:
        for i, opp in enumerate(opportunities[:20], 1):
            conf_emoji = {"HIGH": "🟢", "MEDIUM": "🟡", "LOW": "🔴"}.get(
                opp.get("nws_confidence", ""), "⚪")
            lines.append(f"### {i}. {opp['ticker']} {conf_emoji}\n")
            lines.append(f"**{opp['title']}**\n")
            lines.append(f"- 📍 City: {opp['city']} | Metric: {opp['metric']} | "
                         f"Threshold: {opp['direction']} {opp['threshold']}")
            lines.append(f"- 🌤️ NWS forecast: **{opp['nws_value']}** → probability: **{opp['nws_prob']}%**")
            lines.append(f"- 💰 Kalshi: {opp['market_price']}¢ "
                         f"(bid {opp['yes_bid']} / ask {opp['yes_ask']})")
            lines.append(f"- 📈 **{opp['best_side']}** edge: **{'+' if opp['edge'] > 0 else ''}{opp['edge']}¢** | "
                         f"Entry: {opp['entry_cost']}¢ → Profit: {opp['profit_if_win']}¢")
            lines.append(f"- 📝 {opp.get('nws_detail', '')[:100]}")
            lines.append(f"- 🔗 [{opp['ticker']}]({opp['url']})")
            lines.append("")

    # ── Paper Trading Summary ──
    summary = trade_data.get("summary", {})
    trades = trade_data.get("trades", [])
    if trades:
        lines.append("## 📋 Paper Trading Summary\n")
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        for key, val in summary.items():
            if key != "last_updated":
                lines.append(f"| {key.replace('_', ' ').title()} | {val} |")
        lines.append("")

        # Open trades
        open_trades = [t for t in trades if t["status"] == "open"]
        if open_trades:
            lines.append("### Open Trades\n")
            for t in open_trades:
                lines.append(f"- **{t['ticker']}** | {t['side']} @ {t['entry_price']}¢ | "
                             f"Edge: {t['edge']}¢ | NWS: {t['nws_prob']}% | "
                             f"Conf: {t['nws_confidence']}")
            lines.append("")

        # Recent settled
        settled = [t for t in trades if t["status"] == "settled"]
        if settled:
            lines.append("### Recent Settled Trades\n")
            for t in settled[-10:]:
                result_emoji = "✅" if t["result"] == "win" else "❌"
                lines.append(f"- {result_emoji} **{t['ticker']}** | {t['side']} @ {t['entry_price']}¢ | "
                             f"PnL: ${t.get('pnl', 0):.2f} | Edge: {t['edge']}¢")
            lines.append("")

    # ── NWS Reliability Notes ──
    lines.append("## 📖 NWS Forecast Reliability\n")
    lines.append("Based on published NWS verification studies:\n")
    lines.append("| Timeframe | Temp Accuracy | Precip Accuracy |")
    lines.append("|-----------|---------------|-----------------|")
    lines.append("| Day 1 (today) | ±2-3°F | 80-85% |")
    lines.append("| Day 2-3 | ±3-4°F | 75-80% |")
    lines.append("| Day 4-5 | ±4-6°F | 65-70% |")
    lines.append("| Day 6-7 | ±5-8°F | 55-60% |")
    lines.append("")
    lines.append("**Strategy:** Focus on HIGH confidence (1-2 day) trades where NWS accuracy is highest.\n")

    lines.append("---")
    lines.append(f"*Report generated by weather_paper_trader.py at {now.isoformat()}*")

    return "\n".join(lines)


def run_full_scan_and_trade(min_edge=DEFAULT_MIN_EDGE, verbose=False):
    """Full pipeline: scan → select → record → report."""

    print("🌤️  WEATHER PAPER TRADING SYSTEM", flush=True)
    print("=" * 50, flush=True)
    print(f"Min edge: {min_edge}¢ | Position size: {DEFAULT_POSITION_SIZE} contracts\n", flush=True)

    # Step 1: Scan
    opportunities, stats = scan_weather_markets(min_edge=min_edge, verbose=verbose)

    # Save scan results
    save_results(opportunities, stats, RESULTS_FILE)

    # Step 2: Check existing trade results
    trade_data = load_trades()
    open_count = len([t for t in trade_data.get("trades", []) if t["status"] == "open"])
    if open_count > 0:
        print(f"\n📋 Checking {open_count} open trades for settlement...", flush=True)
        updated = check_trade_results(trade_data)
        if updated:
            print(f"   Updated {updated} trades", flush=True)

    # Step 3: Select new paper trades
    print(f"\n📊 Selecting paper trades (edge ≥ {min_edge}¢)...", flush=True)
    selected = select_paper_trades(opportunities, min_edge=min_edge)

    new_trades = []
    for sel in selected:
        opp = sel["opp"]
        trade = create_paper_trade(opp)
        trade_data.setdefault("trades", []).append(trade)
        new_trades.append(trade)
        print(f"   📝 New trade: {trade['ticker']} | {trade['side']} @ {trade['entry_price']}¢ | "
              f"Edge: {trade['edge']}¢ | Conf: {trade['nws_confidence']}", flush=True)

    if not new_trades:
        print("   No new trades selected", flush=True)

    # Step 4: Update summary
    trade_data["summary"] = compute_summary(trade_data)
    save_trades(trade_data)
    print(f"\n💾 Saved {len(trade_data['trades'])} total trades to {TRADES_FILE}", flush=True)

    # Step 5: Generate report
    report_md = generate_report(opportunities, stats, trade_data)
    with open(REPORT_FILE, "w") as f:
        f.write(report_md)
    print(f"📄 Report saved to {REPORT_FILE}", flush=True)

    # Also print console report
    console_report = format_report(opportunities, stats)
    print(f"\n{console_report}", flush=True)

    return opportunities, stats, trade_data


def main():
    min_edge = DEFAULT_MIN_EDGE
    verbose = False
    check_only = False
    report_only = False

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--min-edge" and i + 1 < len(args):
            min_edge = int(args[i + 1])
            i += 2
        elif args[i] == "--verbose":
            verbose = True
            i += 1
        elif args[i] == "--check":
            check_only = True
            i += 1
        elif args[i] == "--report":
            report_only = True
            i += 1
        else:
            i += 1

    if check_only:
        print("📋 Checking open trade results...", flush=True)
        trade_data = load_trades()
        updated = check_trade_results(trade_data)
        trade_data["summary"] = compute_summary(trade_data)
        save_trades(trade_data)
        summary = trade_data["summary"]
        print(f"\nSummary: {json.dumps(summary, indent=2)}", flush=True)
        return

    if report_only:
        trade_data = load_trades()
        # Load last scan results
        if os.path.exists(RESULTS_FILE):
            with open(RESULTS_FILE) as f:
                scan_data = json.load(f)
            opps = scan_data.get("opportunities", [])
            stats = scan_data.get("stats", {})
        else:
            opps, stats = [], {}
        report_md = generate_report(opps, stats, trade_data)
        with open(REPORT_FILE, "w") as f:
            f.write(report_md)
        print(f"📄 Report saved to {REPORT_FILE}", flush=True)
        print(report_md[:2000], flush=True)
        return

    run_full_scan_and_trade(min_edge=min_edge, verbose=verbose)


if __name__ == "__main__":
    main()
