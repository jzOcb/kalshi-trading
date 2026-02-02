"""
Kalshi Project — Official Module Registry
==========================================

These are the VALIDATED, ESTABLISHED functions. 
Any new script MUST import from here. Do NOT reimplement.

Usage:
    from kalshi import score_market, analyze_rules, scan_and_decide
    from kalshi import fetch_market_details, search_news
"""

# === Core Decision Engine (report_v2.py) ===
# This is the PRIMARY validated module. All scoring/analysis goes through here.
from .report_v2 import (
    api_get,              # Authenticated API requests to Kalshi
    fetch_market_details, # Get full market details by ticker
    kalshi_url,           # Generate Kalshi URL for a ticker
    search_news,          # Search news for market research
    format_vol,           # Format volume numbers
    analyze_rules,        # Analyze market rules text for resolution criteria
    score_market,         # Score a market opportunity (THE core scoring function)
    scan_and_decide,      # Full scan + decision pipeline
)

# === What each module does (for reference) ===
# report_v2.py    — Core decision engine: scoring, rules analysis, news search
# notify.py       — Notification delivery (MUST use report_v2 scoring)
# scanner.py      — Market scanning/discovery
# discovery.py    — Market discovery utilities
# monitor.py      — Position monitoring
# portfolio.py    — Portfolio management
# paper_trading.py — Paper trading simulation
# crosscheck.py   — Cross-platform verification

# === RULES ===
# 1. score_market() is the ONLY approved scoring function
# 2. analyze_rules() is the ONLY approved rules analyzer
# 3. New scripts that need scoring MUST call score_market(), not reimplement
# 4. If you need new analysis, EXTEND report_v2.py, don't create parallel versions
