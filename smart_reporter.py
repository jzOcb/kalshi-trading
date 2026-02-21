#!/usr/bin/env python3
"""
smart_reporter - 智能 Kalshi 报告

功能：
    - 全量报告 2x/天
    - 增量报告按需
    - 智能跳过无变化

用法：
    python smart_reporter.py               # 生成智能报告
    python smart_reporter.py --full        # 强制全量
    
依赖：
    - report_v2.py
"""

import json
import os
import sys
import re
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

STATE_FILE = Path(__file__).parent / "reporter_state.json"
PRICE_CHANGE_THRESHOLD = 5  # cents
FULL_REPORT_HOURS_ET = [9, 18]  # 9 AM and 6 PM Eastern

def load_previous_state() -> dict:
    """Load the previous report state."""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {"series": [], "positions": {}, "timestamp": None}

def save_state(series: list, positions: dict):
    """Save current state for next comparison."""
    state = {
        "series": series,
        "positions": positions,
        "timestamp": datetime.utcnow().isoformat()
    }
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def extract_market_series(url: str) -> str:
    """Extract market series from URL, ignoring threshold variations.
    
    Examples:
    - kxgdp-26jan30-t2.0 → kxgdp-26jan30
    - kxgdp-26jan30-t1.25 → kxgdp-26jan30
    - kxkhameneiout-akha-26mar01 → kxkhameneiout-akha-26mar01
    """
    # Extract the market ID from URL
    match = re.search(r'markets/([^/\s]+)', url)
    if not match:
        return url
    
    market_id = match.group(1)
    
    # Remove threshold suffix like -t2.0, -t1.25, etc.
    series = re.sub(r'-t\d+\.?\d*$', '', market_id)
    return series

def extract_opportunity_series(scan_output: str) -> list:
    """Extract unique market series from scan output."""
    series_set = set()
    for line in scan_output.split('\n'):
        if 'kalshi.com/markets/' in line:
            url = line.strip().split()[-1] if line.strip() else ""
            if url:
                series = extract_market_series(url)
                series_set.add(series)
    return list(series_set)

def extract_positions(positions_output: str) -> dict:
    """Extract position prices from monitor output."""
    positions = {}
    lines = positions_output.split('\n')
    for i, line in enumerate(lines):
        # Look for lines with price info like "入场92¢ → 现在93¢"
        if '入场' in line and '现在' in line:
            try:
                # Extract ticker from previous lines
                for j in range(i-1, max(0, i-5), -1):
                    if lines[j].strip().startswith(('1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.')):
                        ticker_line = lines[j]
                        # Parse current price
                        current = line.split('现在')[1].split('¢')[0].strip()
                        positions[ticker_line[:50]] = int(current)
                        break
            except:
                pass
    return positions

def is_full_report_hour() -> bool:
    """Check if current hour is a full report hour (ET timezone)."""
    et_now = datetime.now(ZoneInfo("America/New_York"))
    return et_now.hour in FULL_REPORT_HOURS_ET

def check_for_changes(prev_state: dict, current_series: list, current_positions: dict) -> tuple:
    """
    Check if there are meaningful changes.
    Returns: (mode: str, reason: str)
    - mode: "FULL", "DELTA", or "SKIP"
    """
    # Full report hours: always send full
    if is_full_report_hour():
        return "FULL", "Scheduled full report"
    
    prev_series = set(prev_state.get("series", []))
    curr_series = set(current_series)
    prev_positions = prev_state.get("positions", {})
    
    changes = []
    
    # Check for new market series
    new_series = curr_series - prev_series
    if new_series:
        changes.append(f"🆕 {len(new_series)} new market series: {', '.join(new_series)}")
    
    # Check for disappeared market series
    gone_series = prev_series - curr_series
    if gone_series:
        changes.append(f"📤 {len(gone_series)} series removed")
    
    # Check for significant price changes in positions
    price_changes = []
    for key, current_price in current_positions.items():
        prev_price = prev_positions.get(key)
        if prev_price is not None:
            change = current_price - prev_price
            if abs(change) >= PRICE_CHANGE_THRESHOLD:
                direction = "📈" if change > 0 else "📉"
                price_changes.append(f"{direction} {key[:20]}: {change:+d}¢")
    
    if price_changes:
        changes.append(f"💰 Price moves: {'; '.join(price_changes[:3])}")
    
    if changes:
        return "DELTA", " | ".join(changes)
    
    return "SKIP", "No significant changes"

def main():
    """Main entry point.
    
    Exit codes:
    - 0: FULL report (send everything)
    - 2: DELTA report (send changes only) 
    - 1: SKIP (nothing to send)
    """
    # Get current data from environment or stdin
    positions_output = os.environ.get("POSITIONS", "")
    scan_output = os.environ.get("SCAN", "")
    
    # If passed as arguments
    if len(sys.argv) > 2:
        positions_output = sys.argv[1]
        scan_output = sys.argv[2]
    
    # Load previous state
    prev_state = load_previous_state()
    
    # Extract current data (using series, not full URLs)
    current_series = extract_opportunity_series(scan_output)
    current_positions = extract_positions(positions_output)
    
    # Check for changes
    mode, reason = check_for_changes(prev_state, current_series, current_positions)
    
    # Save current state
    save_state(current_series, current_positions)
    
    # Output mode and reason
    print(f"{mode}: {reason}")
    
    if mode == "FULL":
        sys.exit(0)
    elif mode == "DELTA":
        sys.exit(2)
    else:  # SKIP
        sys.exit(1)

if __name__ == "__main__":
    main()
