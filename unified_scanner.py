#!/usr/bin/env python3
"""
Kalshi Unified Scanner — Runs all strategies in one pass.

Strategies:
1. Parity Arbitrage (parity_scanner.py) — YES+NO < $1.00
2. Endgame Strategy (endgame_scanner.py) — Near-certain outcomes near settlement
3. Cross-Platform (cross_platform_monitor.py) — Kalshi vs Polymarket price gaps
4. NO Farming (report_v2.py) — Existing high-confidence NO positions

Based on: RESEARCH-V2.md combined strategy recommendations

Usage:
    python3 kalshi/unified_scanner.py           # Run all strategies
    python3 kalshi/unified_scanner.py --quick   # Skip slow strategies
    python3 kalshi/unified_scanner.py --json    # JSON output
"""

import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run_parity_scan():
    """Run parity arbitrage scanner."""
    try:
        from kalshi.parity_scanner import scan_all_parity, format_report
        opportunities, stats = scan_all_parity()
        report = format_report(opportunities, stats)
        return {
            "strategy": "parity_arbitrage",
            "status": "success",
            "opportunities": len(opportunities),
            "report": report,
            "data": opportunities[:20],  # Top 20
            "stats": stats,
        }
    except Exception as e:
        return {
            "strategy": "parity_arbitrage",
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc(),
        }


def run_endgame_scan():
    """Run endgame strategy scanner."""
    try:
        from kalshi.endgame_scanner import (
            fetch_settling_soon_markets, find_endgame_opportunities,
            enrich_with_news, format_report,
        )
        markets = fetch_settling_soon_markets(max_days=7)
        opportunities = find_endgame_opportunities(markets, min_probability=95)
        if opportunities:
            opportunities = enrich_with_news(opportunities)
        stats = {"total_markets": len(markets), "max_days": 7, "min_probability": 95}
        report = format_report(opportunities, stats)
        return {
            "strategy": "endgame",
            "status": "success",
            "opportunities": len(opportunities),
            "report": report,
            "data": opportunities[:20],
            "stats": stats,
        }
    except Exception as e:
        return {
            "strategy": "endgame",
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc(),
        }


def run_cross_platform_scan(auto=False):
    """Run cross-platform price comparison."""
    try:
        from kalshi.cross_platform_monitor import (
            fetch_polymarket_events, compare_known_pairs,
            auto_discover_matches, format_report,
        )
        poly_events = fetch_polymarket_events(limit=200)
        known_results = compare_known_pairs(poly_events)
        auto_results = auto_discover_matches(poly_events) if auto else None
        report = format_report(known_results, auto_results)
        
        arb_count = len([r for r in known_results if r.get("arb_us")])
        
        return {
            "strategy": "cross_platform",
            "status": "success",
            "opportunities": arb_count,
            "comparisons": len(known_results),
            "auto_matches": len(auto_results) if auto_results else 0,
            "report": report,
            "data": known_results[:20],
        }
    except Exception as e:
        return {
            "strategy": "cross_platform",
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc(),
        }


def run_no_farming_scan():
    """Run existing NO farming / decision engine scan."""
    try:
        from kalshi.report_v2 import scan_and_decide
        report = scan_and_decide()
        return {
            "strategy": "no_farming",
            "status": "success",
            "report": report,
        }
    except Exception as e:
        return {
            "strategy": "no_farming",
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc(),
        }


def format_combined_report(results):
    """Combine all strategy reports into one unified output."""
    now = datetime.now(timezone.utc)
    lines = []
    
    lines.append("╔" + "═" * 68 + "╗")
    lines.append("║" + "  🎯 KALSHI UNIFIED SCANNER — COMBINED REPORT".center(68) + "║")
    lines.append("║" + f"  {now.strftime('%Y-%m-%d %H:%M UTC')}".center(68) + "║")
    lines.append("╚" + "═" * 68 + "╝")
    
    # Summary table
    lines.append("\n📋 STRATEGY SUMMARY")
    lines.append("─" * 60)
    total_opps = 0
    for r in results:
        status = "✅" if r["status"] == "success" else "❌"
        opps = r.get("opportunities", "N/A")
        if isinstance(opps, int):
            total_opps += opps
        lines.append(f"  {status} {r['strategy']:<25} — {opps} opportunities")
    lines.append(f"  {'─'*40}")
    lines.append(f"  Total: {total_opps} opportunities across all strategies")
    
    # Individual reports
    for r in results:
        lines.append("\n\n" + "▓" * 70)
        lines.append(f"▓ Strategy: {r['strategy'].upper().replace('_', ' ')}")
        lines.append("▓" * 70)
        
        if r["status"] == "error":
            lines.append(f"\n  ❌ ERROR: {r.get('error', 'Unknown')}")
            if r.get("traceback"):
                for tb_line in r["traceback"].split("\n")[-4:]:
                    lines.append(f"     {tb_line}")
        elif r.get("report"):
            lines.append("")
            lines.append(r["report"])
    
    # Footer
    lines.append("\n\n" + "═" * 70)
    lines.append("🏁 SCAN COMPLETE")
    lines.append(f"   Time: {now.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append(f"   Strategies run: {len(results)}")
    lines.append(f"   Total opportunities: {total_opps}")
    lines.append("═" * 70)
    
    return "\n".join(lines)


def save_combined_results(results, path=None):
    """Save combined results to JSON."""
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "unified-scan-results.json")
    
    output = {
        "scan_time": datetime.now(timezone.utc).isoformat(),
        "strategies": [],
    }
    
    for r in results:
        entry = {
            "strategy": r["strategy"],
            "status": r["status"],
            "opportunities": r.get("opportunities"),
        }
        if r.get("data"):
            entry["data"] = r["data"]
        if r.get("stats"):
            entry["stats"] = r["stats"]
        if r.get("error"):
            entry["error"] = r["error"]
        output["strategies"].append(entry)
    
    with open(path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\n💾 Combined results saved to {path}")


def main():
    quick = "--quick" in sys.argv
    json_out = "--json" in sys.argv
    
    results = []
    
    # 1. Parity Arbitrage
    print("\n" + "=" * 50)
    print("🔄 Strategy 1/4: PARITY ARBITRAGE")
    print("=" * 50)
    if quick:
        print("  ⏭️ Skipped (--quick mode)")
        results.append({"strategy": "parity_arbitrage", "status": "skipped"})
    else:
        results.append(run_parity_scan())
    
    # 2. Endgame
    print("\n" + "=" * 50)
    print("🎯 Strategy 2/4: ENDGAME")
    print("=" * 50)
    results.append(run_endgame_scan())
    
    # 3. Cross-Platform
    print("\n" + "=" * 50)
    print("🔄 Strategy 3/4: CROSS-PLATFORM")
    print("=" * 50)
    results.append(run_cross_platform_scan(auto=not quick))
    
    # 4. NO Farming (existing)
    print("\n" + "=" * 50)
    print("📈 Strategy 4/4: NO FARMING (Decision Engine)")
    print("=" * 50)
    results.append(run_no_farming_scan())
    
    # Combined report
    if json_out:
        save_combined_results(results)
    else:
        report = format_combined_report(results)
        print("\n\n")
        print(report)
        save_combined_results(results)
    
    return results


if __name__ == "__main__":
    main()
