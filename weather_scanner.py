#!/usr/bin/env python3
"""
Kalshi Weather Market Scanner v2

Compares NWS (National Weather Service) forecasts against Kalshi weather
market pricing to find mispriced opportunities.

Key improvements over v1:
- Ticker-based parsing: directly parse KXHIGHT{CITY}, KXLOWT{CITY}, KXRAIN{CITY}M, etc.
- Covers 95%+ of weather market formats
- Proper bid/ask pricing from API
- Real edge calculation: NWS probability vs Kalshi implied probability
- Filters out false positives (esports "Hurricanes", climate policy, etc.)

Usage:
    python3 kalshi/weather_scanner.py                  # Full scan
    python3 kalshi/weather_scanner.py --min-edge 10    # Only edge > 10¢
    python3 kalshi/weather_scanner.py --verbose         # Show all markets
"""

import json
import math
import os
import re
import sys
import time
import requests
from datetime import datetime, timezone, timedelta

# ── Kalshi API (same pattern as report_v2.py) ──

API_BASE = "https://api.elections.kalshi.com/trade-api/v2"

try:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from kalshi.report_v2 import api_get, kalshi_url, format_vol
    HAVE_REPORT_V2 = True
except ImportError:
    HAVE_REPORT_V2 = False

    def api_get(endpoint, params=None):
        try:
            resp = requests.get(f"{API_BASE}{endpoint}", params=params, timeout=15)
            if resp.status_code == 429:
                time.sleep(3)
                resp = requests.get(f"{API_BASE}{endpoint}", params=params, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return None

    def kalshi_url(ticker):
        return f"https://kalshi.com/markets/{ticker.lower()}"

    def format_vol(v):
        if v >= 1_000_000:
            return f"{v/1_000_000:.1f}M"
        elif v >= 1_000:
            return f"{v/1_000:.0f}K"
        return str(v)


# ── NWS Configuration ──

NWS_BASE = "https://api.weather.gov"
NWS_HEADERS = {
    "User-Agent": "(KalshiWeatherScanner, contact@example.com)",
    "Accept": "application/geo+json",
}

# City → NWS gridpoint mapping
CITY_NWS_MAP = {
    "new york": {"office": "OKX", "gridX": 33, "gridY": 37,
                 "aliases": ["nyc", "new york city", "manhattan", "brooklyn"]},
    "chicago": {"office": "LOT", "gridX": 75, "gridY": 72,
                "aliases": ["chi", "chicago"]},
    "boston": {"office": "BOX", "gridX": 71, "gridY": 90,
              "aliases": ["boston", "bos"]},
    "denver": {"office": "BOU", "gridX": 62, "gridY": 60,
               "aliases": ["denver", "den"]},
    "los angeles": {"office": "LOX", "gridX": 154, "gridY": 44,
                    "aliases": ["la", "los angeles", "lax"]},
    "miami": {"office": "MFL", "gridX": 75, "gridY": 54,
              "aliases": ["miami", "mia"]},
    "dallas": {"office": "FWD", "gridX": 84, "gridY": 108,
               "aliases": ["dallas", "dfw", "dal"]},
    "seattle": {"office": "SEW", "gridX": 124, "gridY": 67,
                "aliases": ["seattle", "sea"]},
    "detroit": {"office": "DTX", "gridX": 65, "gridY": 33,
                "aliases": ["detroit", "det"]},
    "minneapolis": {"office": "MPX", "gridX": 107, "gridY": 71,
                    "aliases": ["minneapolis", "msp", "twin cities"]},
    "atlanta": {"office": "FFC", "gridX": 50, "gridY": 86,
                "aliases": ["atlanta", "atl"]},
    "philadelphia": {"office": "PHI", "gridX": 49, "gridY": 75,
                     "aliases": ["philadelphia", "philly", "phl"]},
    "washington": {"office": "LWX", "gridX": 97, "gridY": 71,
                   "aliases": ["washington", "dc", "washington dc", "dca"]},
    "houston": {"office": "HGX", "gridX": 65, "gridY": 97,
                "aliases": ["houston", "hou"]},
    "phoenix": {"office": "PSR", "gridX": 159, "gridY": 57,
                "aliases": ["phoenix", "phx"]},
    "san francisco": {"office": "MTR", "gridX": 85, "gridY": 105,
                      "aliases": ["san francisco", "sf", "sfo"]},
    "baltimore": {"office": "LWX", "gridX": 108, "gridY": 80,
                  "aliases": ["baltimore", "bwi"]},
    "pittsburgh": {"office": "PBZ", "gridX": 76, "gridY": 65,
                   "aliases": ["pittsburgh", "pit"]},
    "st louis": {"office": "LSX", "gridX": 87, "gridY": 75,
                 "aliases": ["st louis", "stl", "saint louis"]},
    "nashville": {"office": "OHX", "gridX": 53, "gridY": 66,
                  "aliases": ["nashville", "bna"]},
    # New cities found in Kalshi tickers
    "austin": {"office": "EWX", "gridX": 116, "gridY": 75,
               "aliases": ["austin", "aus"]},
    "new orleans": {"office": "LIX", "gridX": 76, "gridY": 75,
                    "aliases": ["new orleans", "nola"]},
    "las vegas": {"office": "VEF", "gridX": 126, "gridY": 97,
                  "aliases": ["las vegas", "lv", "vegas"]},
    "salt lake city": {"office": "SLC", "gridX": 97, "gridY": 175,
                       "aliases": ["salt lake city", "slc"]},
}

# ── Ticker-based city code mapping ──
# Maps city codes found in Kalshi tickers to city keys
TICKER_CITY_CODES = {
    "NYC": "new york", "NY": "new york",
    "CHI": "chicago",
    "BOS": "boston",
    "DEN": "denver",
    "LAX": "los angeles",
    "MIA": "miami",
    "DAL": "dallas",
    "SEA": "seattle",
    "DET": "detroit",
    "MSP": "minneapolis",
    "ATL": "atlanta",
    "PHIL": "philadelphia", "PHI": "philadelphia", "PHL": "philadelphia",
    "DC": "washington",
    "HOU": "houston",
    "PHX": "phoenix",
    "SFO": "san francisco", "SF": "san francisco",
    "BAL": "baltimore", "BWI": "baltimore",
    "PIT": "pittsburgh",
    "STL": "st louis",
    "NSH": "nashville", "BNA": "nashville",
    "AUS": "austin",
    "NOLA": "new orleans",
    "LV": "las vegas",
    "SLC": "salt lake city",
    "LA": "los angeles",
}

# ── False positive filters ──
NOISE_TICKER_PREFIXES = [
    "KXMVESPORTS",  # Esports parlays (contain "Hurricanes" team name)
    "KXPRIMEENG",   # Energy consumption
    "EVSHARE",      # EV market share
]

NOISE_TITLE_KEYWORDS = [
    "esports", "nhl", "hockey", "basketball", "football", "soccer",
    "primary energy", "ev market", "electric vehicle",
]


def is_noise_market(ticker, title):
    """Filter out false positive weather markets."""
    ticker_upper = ticker.upper()
    title_lower = title.lower()
    for prefix in NOISE_TICKER_PREFIXES:
        if ticker_upper.startswith(prefix):
            return True
    for kw in NOISE_TITLE_KEYWORDS:
        if kw in title_lower:
            return True
    return False


# Known weather series tickers on Kalshi
# This is much faster than scanning all 4000+ events
WEATHER_SERIES = [
    # High temp daily
    "KXHIGHNY", "KXHIGHDEN", "KXHIGHLAX", "KXHIGHMIA", "KXHIGHPHIL", "KXHIGHAUS",
    "KXHIGHTSFO", "KXHIGHTSEA", "KXHIGHTNOLA", "KXHIGHTLV", "KXHIGHTDC",
    # Low temp daily
    "KXLOWTNYC", "KXLOWTCHI", "KXLOWTDEN", "KXLOWTLAX", "KXLOWTMIA",
    "KXLOWTPHIL", "KXLOWTAUS",
    # Monthly snow
    "KXNYCSNOWM", "KXCHISNOWM", "KXBOSSNOWM", "KXPHILSNOWM", "KXDETSNOWM",
    "KXDCSNOWM", "KXDALSNOWM", "KXDENSNOWMB", "KXHOUSNOWM", "KXLAXSNOWM",
    "KXMIASNOWM", "KXSEASNOWM", "KXSFOSNOWM", "KXSLCSNOWM", "KXAUSSNOWM",
    # Snowstorm events
    "KXSNOWSTORM",
    # Monthly rain
    "KXRAINSFOM", "KXRAINSEAM", "KXRAINMIAM", "KXRAINLAXM", "KXRAINHOUM",
    "KXRAINDENM", "KXRAINCHIM", "KXRAINAUSM", "KXRAINNYCM",
    # Tornado
    "KXTORNADO",
    # Climate/global
    "KXARCTICICEMAX", "KXGTEMP", "KXWARMING",
]


def fetch_weather_markets():
    """
    Fetch all weather-related markets from Kalshi API.
    
    Uses two fast approaches:
    1. Direct series_ticker lookup (fast, targeted)
    2. Limited keyword scan for any missed markets
    """
    all_markets = []
    seen_tickers = set()

    # ── Phase 1: Direct series fetch (fast!) ──
    print("   Phase 1: Fetching known weather series...", flush=True)
    for series in WEATHER_SERIES:
        data = api_get("/markets", {"series_ticker": series, "limit": 200, "status": "open"})
        if data:
            for m in data.get("markets", []):
                ticker = m.get("ticker", "")
                if ticker not in seen_tickers:
                    seen_tickers.add(ticker)
                    all_markets.append(m)
        time.sleep(0.05)

    print(f"   Found {len(all_markets)} from {len(WEATHER_SERIES)} series", flush=True)

    # ── Phase 2: Quick keyword scan (catch new series we don't know about) ──
    print("   Phase 2: Quick keyword scan for new series...", flush=True)
    cursor = None
    pages = 0
    max_pages = 5  # Just a quick scan

    weather_ticker_patterns = [
        "KXHIGHT", "KXHIGH", "KXLOWT", "KXLOW",
        "KXSNOW", "KXRAIN", "KXTORNADO",
        "KXARCTICICE", "KXGTEMP", "KXWARMING",
    ]

    weather_title_keywords = [
        "temperature", "snowfall", "high temp", "low temp",
        "maximum temperature", "minimum temperature",
        "rain in ", "snow in ",
    ]

    new_found = 0
    while pages < max_pages:
        params = {"limit": 200, "status": "open"}
        if cursor:
            params["cursor"] = cursor
        data = api_get("/markets", params)
        if not data:
            break

        for m in data.get("markets", []):
            ticker = m.get("ticker", "").upper()
            if ticker in seen_tickers:
                continue

            title = m.get("title", "")
            title_lower = title.lower()

            if is_noise_market(ticker, title):
                continue

            is_weather = False
            for pat in weather_ticker_patterns:
                if pat in ticker:
                    is_weather = True
                    break
            if not is_weather:
                for kw in weather_title_keywords:
                    if kw in title_lower:
                        is_weather = True
                        break

            if is_weather:
                seen_tickers.add(ticker)
                all_markets.append(m)
                new_found += 1

        cursor = data.get("cursor", "")
        if not cursor or len(data.get("markets", [])) < 200:
            break
        pages += 1
        time.sleep(0.1)

    if new_found:
        print(f"   Found {new_found} additional markets from keyword scan", flush=True)

    print(f"   Total: {len(all_markets)} weather markets", flush=True)
    return all_markets


def parse_ticker_city(ticker):
    """
    Extract city from ticker using known patterns.
    
    Patterns:
      KXHIGHT{CITY}-...  (KXHIGHTSFO, KXHIGHTSEA, KXHIGHTNOLA, KXHIGHTLV, KXHIGHTDC)
      KXHIGH{CITY}-...   (KXHIGHPHIL, KXHIGHNY, KXHIGHMIA, KXHIGHLAX, KXHIGHDEN, KXHIGHAUS)
      KXLOWT{CITY}-...   (KXLOWTPHIL, KXLOWTNYC, KXLOWTMIA, etc.)
      KXRAIN{CITY}M-...  (KXRAINSFOM, KXRAINSEAM, KXRAINCHIM, etc.)
      KX{CITY}SNOWM-...  (KXNYCSNOWM, KXCHISNOWM, KXBOSSNOWM, etc.)
      KXSNOWSTORM-{DATE}{CITY}-... (KXSNOWSTORM-26FEBNYC-...)
    """
    ticker_upper = ticker.upper()
    
    # Try longest city codes first to avoid partial matches
    sorted_codes = sorted(TICKER_CITY_CODES.keys(), key=len, reverse=True)
    
    # Pattern 1: KXHIGHT{CITY} or KXLOWT{CITY}
    for prefix in ["KXHIGHT", "KXLOWT"]:
        if ticker_upper.startswith(prefix):
            rest = ticker_upper[len(prefix):].split("-")[0]
            for code in sorted_codes:
                if rest == code:
                    return TICKER_CITY_CODES[code]
    
    # Pattern 2: KXHIGH{CITY} (no T suffix — different format)
    if ticker_upper.startswith("KXHIGH") and not ticker_upper.startswith("KXHIGHT"):
        rest = ticker_upper[6:].split("-")[0]
        for code in sorted_codes:
            if rest == code:
                return TICKER_CITY_CODES[code]
    
    # Pattern 3: KXRAIN{CITY}M
    m = re.match(r'KXRAIN(\w+?)M(?:B)?-', ticker_upper)
    if m:
        city_part = m.group(1)
        for code in sorted_codes:
            if city_part == code:
                return TICKER_CITY_CODES[code]
    
    # Pattern 4: KX{CITY}SNOWM or KX{CITY}SNOWMB
    m = re.match(r'KX(\w+?)SNOWM(?:B)?-', ticker_upper)
    if m:
        city_part = m.group(1)
        for code in sorted_codes:
            if city_part == code:
                return TICKER_CITY_CODES[code]
    
    # Pattern 5: KXSNOWSTORM-{DATE}{CITY}-
    m = re.match(r'KXSNOWSTORM-\d{2}\w{3}(\w+)-', ticker_upper)
    if m:
        city_part = m.group(1)
        for code in sorted_codes:
            if city_part == code:
                return TICKER_CITY_CODES[code]
    
    return None


def parse_ticker_metric(ticker):
    """Extract weather metric from ticker."""
    ticker_upper = ticker.upper()
    
    if "HIGHT" in ticker_upper or (ticker_upper.startswith("KXHIGH") and "SNOW" not in ticker_upper):
        return "high_temp"
    if "LOWT" in ticker_upper:
        return "low_temp"
    if "SNOWSTORM" in ticker_upper or "SNOWM" in ticker_upper:
        return "snow"
    if "RAIN" in ticker_upper:
        return "rain"
    if "TORNADO" in ticker_upper:
        return "tornado"
    if "ARCTICICE" in ticker_upper:
        return "arctic_ice"
    if "GTEMP" in ticker_upper or "WARMING" in ticker_upper:
        return "global_temp"
    
    return None


def parse_ticker_threshold(ticker):
    """
    Extract threshold and direction from ticker.
    
    Patterns:
      -T{value}  → above threshold (Temperature markets)
      -B{value}  → bracket/between (used in some markets)
      -{value}   → above threshold (Snow/Rain monthly)
    """
    ticker_upper = ticker.upper()
    
    # Pattern: -T{number} at end
    m = re.search(r'-T(\d+\.?\d*)$', ticker_upper)
    if m:
        val = float(m.group(1))
        return val, "above"
    
    # Pattern: -B{number} at end (bracket markets — treat as above for simplicity)
    m = re.search(r'-B(\d+\.?\d*)$', ticker_upper)
    if m:
        val = float(m.group(1))
        return val, "above"
    
    # Pattern: -{number} at end (snow/rain/tornado thresholds)
    m = re.search(r'-(\d+\.?\d*)$', ticker_upper)
    if m:
        val = float(m.group(1))
        return val, "above"
    
    return None, None


def parse_ticker_date(ticker):
    """
    Extract date from ticker.
    
    Patterns:
      -26FEB04-  → 2026-02-04
      -26FEB-    → February 2026 (monthly)
    """
    ticker_upper = ticker.upper()
    
    month_map = {
        "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
        "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
    }
    
    # Daily: 26FEB04
    m = re.search(r'-(\d{2})(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)(\d{2})-', ticker_upper)
    if m:
        year = 2000 + int(m.group(1))
        month = month_map[m.group(2)]
        day = int(m.group(3))
        try:
            return datetime(year, month, day, tzinfo=timezone.utc).strftime("%Y-%m-%d"), "daily"
        except ValueError:
            pass
    
    # Monthly: 26FEB (no day)
    m = re.search(r'-(\d{2})(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)(?:[A-Z]|-|$)', ticker_upper)
    if m:
        year = 2000 + int(m.group(1))
        month = month_map[m.group(2)]
        return f"{year}-{month:02d}", "monthly"
    
    return None, None


def parse_weather_market(market):
    """
    Parse a weather market using BOTH ticker-based and title-based parsing.
    Ticker-based parsing is primary (more reliable), title-based is fallback.
    """
    title = market.get("title", "")
    subtitle = market.get("subtitle", "") or ""
    ticker = market.get("ticker", "").upper()
    close_time = market.get("close_time", "")
    full_text = f"{title} {subtitle}".lower()

    parsed = {
        "city": None,
        "city_key": None,
        "metric": None,
        "threshold": None,
        "direction": None,
        "unit": None,
        "date": None,
        "date_type": None,  # "daily" or "monthly"
        "close_time": close_time,
    }

    # ── Step 1: Ticker-based parsing (primary) ──
    parsed["city_key"] = parse_ticker_city(ticker)
    parsed["city"] = parsed["city_key"]
    parsed["metric"] = parse_ticker_metric(ticker)
    parsed["threshold"], parsed["direction"] = parse_ticker_threshold(ticker)
    parsed["date"], parsed["date_type"] = parse_ticker_date(ticker)
    
    # Set unit based on metric
    if parsed["metric"] in ("high_temp", "low_temp", "temperature"):
        parsed["unit"] = "fahrenheit"
    elif parsed["metric"] in ("snow", "rain"):
        parsed["unit"] = "inches"
    elif parsed["metric"] == "tornado":
        parsed["unit"] = "count"
    
    # ── Step 2: Title-based fallback for missing fields ──
    
    # City from title
    if not parsed["city_key"]:
        for city_key, city_info in CITY_NWS_MAP.items():
            for alias in city_info["aliases"]:
                if alias in full_text:
                    parsed["city"] = city_key
                    parsed["city_key"] = city_key
                    break
            if parsed["city"]:
                break
    
    # Metric from title
    if not parsed["metric"]:
        if any(w in full_text for w in ["maximum temperature", "high temp"]):
            parsed["metric"] = "high_temp"
            parsed["unit"] = "fahrenheit"
        elif any(w in full_text for w in ["minimum temperature", "low temp"]):
            parsed["metric"] = "low_temp"
            parsed["unit"] = "fahrenheit"
        elif any(w in full_text for w in ["snow", "snowfall"]):
            parsed["metric"] = "snow"
            parsed["unit"] = "inches"
        elif any(w in full_text for w in ["rain", "rainfall", "precipitation"]):
            parsed["metric"] = "rain"
            parsed["unit"] = "inches"
        elif any(w in full_text for w in ["temperature", "degrees", "fahrenheit"]):
            parsed["metric"] = "temperature"
            parsed["unit"] = "fahrenheit"
        elif any(w in full_text for w in ["wind", "wind speed"]):
            parsed["metric"] = "wind"
            parsed["unit"] = "mph"
        elif "tornado" in full_text:
            parsed["metric"] = "tornado"
            parsed["unit"] = "count"
    
    # Direction from title (if not from ticker)
    if not parsed["direction"]:
        if any(w in full_text for w in ["more than", "above", "over", "exceed", "higher", ">", "≥"]):
            parsed["direction"] = "above"
        elif any(w in full_text for w in ["less than", "below", "under", "fewer", "lower", "<", "≤"]):
            parsed["direction"] = "below"
        else:
            parsed["direction"] = "above"
    
    # Also check title for direction override (title is more explicit)
    if ">" in title or "above" in full_text or "more than" in full_text:
        parsed["direction"] = "above"
    elif "<" in title or "below" in full_text or "less than" in full_text:
        parsed["direction"] = "below"
    
    # Threshold from title (fallback)
    if parsed["threshold"] is None:
        threshold_patterns = [
            (r'[>≥]\s*(\d+\.?\d*)°?', "above"),
            (r'[<≤]\s*(\d+\.?\d*)°?', "below"),
            (r'(?:more than|above|over|exceed|at least)\s*(\d+\.?\d*)', "above"),
            (r'(?:less than|below|under|at most)\s*(\d+\.?\d*)', "below"),
            (r'(\d+\.?\d*)\s*(?:or more|or above|\+|or higher)', "above"),
            (r'(\d+\.?\d*)\s*(?:or less|or below|or fewer|or lower)', "below"),
        ]
        for pattern, direction in threshold_patterns:
            match = re.search(pattern, full_text)
            if match:
                parsed["threshold"] = float(match.group(1))
                parsed["direction"] = direction
                break
    
    # Date from title (fallback)
    if not parsed["date"]:
        month_map = {
            "jan": 1, "january": 1, "feb": 2, "february": 2,
            "mar": 3, "march": 3, "apr": 4, "april": 4,
            "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
            "aug": 8, "august": 8, "sep": 9, "september": 9,
            "oct": 10, "october": 10, "nov": 11, "november": 11,
            "dec": 12, "december": 12,
        }
        # Try "Feb 4, 2026" or "on Feb 4"
        dm = re.search(
            r'(?:on|for|by)?\s*(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+(\d{1,2})',
            full_text
        )
        if dm:
            month_str = dm.group(1).lower()
            day = int(dm.group(2))
            month = month_map.get(month_str)
            if month:
                now = datetime.now(timezone.utc)
                year = now.year
                try:
                    target = datetime(year, month, day, tzinfo=timezone.utc)
                    if target < now - timedelta(days=30):
                        target = datetime(year + 1, month, day, tzinfo=timezone.utc)
                    parsed["date"] = target.strftime("%Y-%m-%d")
                    parsed["date_type"] = "daily"
                except ValueError:
                    pass
    
    # Fallback: use close_time
    if not parsed["date"] and close_time:
        try:
            ct = datetime.fromisoformat(close_time.replace("Z", "+00:00"))
            parsed["date"] = ct.strftime("%Y-%m-%d")
            parsed["date_type"] = "daily"
        except (ValueError, TypeError):
            pass

    return parsed


# ── NWS Forecast Fetching ──

_nws_cache = {}


def fetch_nws_forecast(city_key):
    """Fetch NWS standard forecast for a city."""
    if city_key in _nws_cache:
        return _nws_cache[city_key]

    city_info = CITY_NWS_MAP.get(city_key)
    if not city_info:
        return None

    url = f"{NWS_BASE}/gridpoints/{city_info['office']}/{city_info['gridX']},{city_info['gridY']}/forecast"

    try:
        resp = requests.get(url, headers=NWS_HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        periods = data.get("properties", {}).get("periods", [])
        _nws_cache[city_key] = periods
        return periods
    except Exception as e:
        print(f"   ⚠️ NWS forecast failed for {city_key}: {e}", flush=True)
        _nws_cache[city_key] = None
        return None


def fetch_nws_quantitative(city_key):
    """Fetch NWS quantitative gridpoint data for snow/precip amounts."""
    cache_key = f"{city_key}_quant"
    if cache_key in _nws_cache:
        return _nws_cache[cache_key]

    city_info = CITY_NWS_MAP.get(city_key)
    if not city_info:
        return None

    url = f"{NWS_BASE}/gridpoints/{city_info['office']}/{city_info['gridX']},{city_info['gridY']}"

    try:
        resp = requests.get(url, headers=NWS_HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        props = data.get("properties", {})
        _nws_cache[cache_key] = props
        return props
    except Exception as e:
        print(f"   ⚠️ NWS quantitative data failed for {city_key}: {e}", flush=True)
        _nws_cache[cache_key] = None
        return None


def get_nws_temp_for_date(city_key, target_date_str, metric):
    """Get NWS temperature forecast for a specific date."""
    try:
        target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    except ValueError:
        return None

    now = datetime.now(timezone.utc)
    days_ahead = (target_date - now.date()).days

    if days_ahead > 7 or days_ahead < -1:
        return None

    confidence = "HIGH" if days_ahead <= 2 else ("MEDIUM" if days_ahead <= 5 else "LOW")

    # Try quantitative data first (more precise)
    quant = fetch_nws_quantitative(city_key)
    if quant:
        prop_key = "maxTemperature" if metric == "high_temp" else "minTemperature"
        series = quant.get(prop_key, {}).get("values", [])
        for entry in series:
            valid_time = entry.get("validTime", "")
            if target_date_str in valid_time:
                val = entry.get("value")
                if val is not None:
                    # Convert C to F
                    val_f = val * 9/5 + 32
                    return {
                        "value": round(val_f, 1),
                        "confidence": confidence,
                        "detail": f"NWS gridpoint {metric}: {round(val_f, 1)}°F for {target_date_str}",
                    }

    # Fallback to standard forecast
    periods = fetch_nws_forecast(city_key)
    if not periods:
        return None

    for period in periods:
        start = period.get("startTime", "")
        if target_date_str in start:
            temp = period.get("temperature")
            is_daytime = period.get("isDaytime", True)
            name = period.get("name", "")
            detail = period.get("detailedForecast", "")

            if metric == "high_temp" and is_daytime:
                return {"value": temp, "confidence": confidence,
                        "detail": f"{name}: {temp}°F - {detail[:100]}"}
            elif metric == "low_temp" and not is_daytime:
                return {"value": temp, "confidence": confidence,
                        "detail": f"{name}: {temp}°F - {detail[:100]}"}
            elif metric == "temperature":
                return {"value": temp, "confidence": confidence,
                        "detail": f"{name}: {temp}°F - {detail[:100]}"}

    # Closest period fallback
    best = None
    best_diff = 999
    for period in periods:
        start = period.get("startTime", "")
        try:
            pdate = datetime.fromisoformat(start.replace("Z", "+00:00")).date()
            diff = abs((pdate - target_date).days)
            if diff < best_diff:
                is_day = period.get("isDaytime", True)
                if (metric == "high_temp" and is_day) or \
                   (metric == "low_temp" and not is_day) or \
                   metric == "temperature":
                    best = period
                    best_diff = diff
        except (ValueError, TypeError):
            continue

    if best and best_diff <= 1:
        temp = best.get("temperature")
        return {"value": temp, "confidence": "LOW",
                "detail": f"~{best.get('name','')}: {temp}°F (±1 day)"}

    return None


def get_nws_precip_for_month(city_key, year_month_str, metric):
    """
    Get NWS precipitation/snow forecast for a monthly market.
    These are harder — NWS only forecasts 7 days, not full month.
    Returns what we can for the forecast window.
    """
    quant = fetch_nws_quantitative(city_key)
    if not quant:
        return None

    prop_key = "snowfallAmount" if metric == "snow" else "quantitativePrecipitation"
    series = quant.get(prop_key, {}).get("values", [])

    if not series:
        return None

    total = 0.0
    found = False
    for entry in series:
        valid_time = entry.get("validTime", "")
        if year_month_str in valid_time:
            val = entry.get("value", 0)
            if val and isinstance(val, (int, float)):
                total += val / 25.4  # mm to inches
                found = True

    if found:
        return {
            "value": round(total, 1),
            "confidence": "LOW",  # Monthly forecasts are inherently less reliable
            "detail": f"NWS gridpoint partial month: ~{round(total, 1)} inches ({metric})",
        }

    return None


def get_nws_snow_for_date(city_key, target_date_str):
    """Get NWS snowfall forecast for a specific date."""
    try:
        target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    except ValueError:
        return None

    now = datetime.now(timezone.utc)
    days_ahead = (target_date - now.date()).days
    if days_ahead > 7 or days_ahead < -1:
        return None

    confidence = "HIGH" if days_ahead <= 2 else ("MEDIUM" if days_ahead <= 5 else "LOW")

    quant = fetch_nws_quantitative(city_key)
    if not quant:
        return None

    series = quant.get("snowfallAmount", {}).get("values", [])
    total = 0.0
    found = False
    for entry in series:
        valid_time = entry.get("validTime", "")
        if target_date_str in valid_time:
            val = entry.get("value", 0)
            if val and isinstance(val, (int, float)):
                total += val / 25.4
                found = True

    if found:
        return {
            "value": round(total, 1),
            "confidence": confidence,
            "detail": f"NWS gridpoint snowfall: {round(total, 1)} inches for {target_date_str}",
        }

    # Check forecast text as fallback
    periods = fetch_nws_forecast(city_key)
    if periods:
        for period in periods:
            if target_date_str in period.get("startTime", ""):
                detail = period.get("detailedForecast", "").lower()
                snow_match = re.search(r'(\d+\.?\d*)\s*(?:to\s*(\d+\.?\d*))?\s*inch', detail)
                if snow_match and "snow" in detail:
                    low_val = float(snow_match.group(1))
                    high_val = float(snow_match.group(2)) if snow_match.group(2) else low_val
                    avg = (low_val + high_val) / 2
                    return {"value": avg, "confidence": confidence,
                            "detail": f"Forecast text: {low_val}-{high_val} inches snow"}

    return None


def get_nws_forecast_for_date(city_key, target_date_str, metric, date_type="daily"):
    """
    Unified NWS forecast fetcher. Routes to appropriate sub-function.
    """
    if not target_date_str or not city_key:
        return None

    if date_type == "monthly":
        if metric in ("snow", "rain"):
            return get_nws_precip_for_month(city_key, target_date_str, metric)
        return None  # Can't forecast monthly temps

    if metric in ("high_temp", "low_temp", "temperature"):
        return get_nws_temp_for_date(city_key, target_date_str, metric)
    elif metric == "snow":
        return get_nws_snow_for_date(city_key, target_date_str)
    elif metric == "rain":
        return get_nws_precip_for_month(city_key, target_date_str, metric)

    return None


def norm_cdf(x):
    """Standard normal CDF approximation."""
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def estimate_probability(nws_value, threshold, direction, metric):
    """
    Estimate probability that actual value will exceed/fall below threshold.
    Uses normal distribution with typical NWS forecast errors.
    """
    if nws_value is None or threshold is None:
        return None

    # Typical NWS forecast errors (standard deviation)
    error_std = {
        "high_temp": 3.0,    # ±3°F typical
        "low_temp": 3.0,
        "temperature": 3.5,
        "snow": 2.0,         # ±2 inches for snow
        "rain": 0.5,         # ±0.5 inches for rain
        "wind": 5.0,
    }

    std = error_std.get(metric, 3.0)
    diff = nws_value - threshold
    z = diff / std if std > 0 else (10 if diff > 0 else -10)

    if direction == "above":
        prob = norm_cdf(z) * 100
    else:
        prob = (1 - norm_cdf(z)) * 100

    return round(max(1, min(99, prob)), 1)


def calculate_edge(nws_prob, market_price):
    """
    Calculate edge in cents.
    Positive = market underpriced (NWS says more likely than market).
    """
    if nws_prob is None or market_price is None:
        return None
    return round(nws_prob - market_price, 1)


def scan_weather_markets(min_edge=5, verbose=False):
    """Main scan: fetch markets, parse, get NWS data, find opportunities."""

    print("📡 Fetching weather markets from Kalshi...", flush=True)
    markets = fetch_weather_markets()
    print(f"   Found {len(markets)} weather-related markets\n", flush=True)

    if not markets:
        return [], {"total_weather_markets": 0, "parseable_markets": 0,
                     "opportunities_found": 0, "min_edge": min_edge,
                     "skipped": {}, "cities_checked": [], "all_markets_info": []}

    # Parse each market
    parsed_markets = []
    skipped = {"no_city": 0, "no_metric": 0, "no_forecast": 0, "no_threshold": 0,
               "not_actionable": 0}
    skipped_examples = {"no_city": [], "no_metric": [], "no_threshold": []}

    for m in markets:
        parsed = parse_weather_market(m)
        parsed["_market"] = m
        parsed_markets.append(parsed)

    # Count parseable
    parseable = 0
    for p in parsed_markets:
        if p["city_key"] and p["metric"] and p["threshold"] is not None:
            parseable += 1

    print(f"📊 Parsed {parseable}/{len(markets)} markets ({100*parseable//max(len(markets),1)}%)\n", flush=True)

    # Collect cities needed
    cities_needed = set()
    for p in parsed_markets:
        if p["city_key"] and p["city_key"] in CITY_NWS_MAP:
            cities_needed.add(p["city_key"])

    print(f"🌤️  Fetching NWS forecasts for {len(cities_needed)} cities...", flush=True)
    for city in cities_needed:
        fetch_nws_forecast(city)
        fetch_nws_quantitative(city)
        time.sleep(0.3)
    print(f"   Done\n", flush=True)

    # Find opportunities
    opportunities = []

    for p in parsed_markets:
        m = p["_market"]
        ticker = m.get("ticker", "")
        title = m.get("title", "")
        yes_bid = m.get("yes_bid", 0) or 0
        yes_ask = m.get("yes_ask", 0) or 0
        no_bid = m.get("no_bid", 0) or 0
        no_ask = m.get("no_ask", 0) or 0
        last_price = m.get("last_price", 0) or 0
        volume = m.get("volume_24h", 0) or m.get("volume", 0) or 0

        # Check parsing completeness
        if not p["city_key"]:
            skipped["no_city"] += 1
            if len(skipped_examples["no_city"]) < 5:
                skipped_examples["no_city"].append(f"{ticker}: {title[:50]}")
            continue

        if not p["metric"]:
            skipped["no_metric"] += 1
            if len(skipped_examples["no_metric"]) < 5:
                skipped_examples["no_metric"].append(f"{ticker}: {title[:50]}")
            continue

        if p["threshold"] is None:
            skipped["no_threshold"] += 1
            if len(skipped_examples["no_threshold"]) < 5:
                skipped_examples["no_threshold"].append(f"{ticker}: {title[:50]}")
            continue

        # Skip non-actionable metrics (can't forecast with NWS)
        if p["metric"] in ("tornado", "arctic_ice", "global_temp", "earthquake"):
            skipped["not_actionable"] += 1
            continue

        # Skip if city not in NWS map
        if p["city_key"] not in CITY_NWS_MAP:
            skipped["no_city"] += 1
            continue

        # Get NWS forecast
        forecast = get_nws_forecast_for_date(
            p["city_key"], p["date"], p["metric"], p.get("date_type", "daily")
        )
        if not forecast:
            skipped["no_forecast"] += 1
            if verbose:
                print(f"   ⏭️ {ticker}: no NWS forecast for {p['city_key']} {p['date']} {p['metric']}", flush=True)
            continue

        # Estimate probability
        nws_prob = estimate_probability(
            forecast["value"], p["threshold"], p["direction"], p["metric"]
        )
        if nws_prob is None:
            continue

        # Calculate pricing
        # Use mid of bid/ask if available, otherwise last_price
        if yes_bid > 0 and yes_ask > 0:
            mid_price = (yes_bid + yes_ask) / 2
        elif last_price > 0:
            mid_price = last_price
        else:
            mid_price = 50  # can't determine

        # YES edge and NO edge
        yes_edge = calculate_edge(nws_prob, mid_price)
        no_edge = calculate_edge(100 - nws_prob, 100 - mid_price)

        spread = (yes_ask - yes_bid) if yes_ask > 0 and yes_bid > 0 else 99

        # Best side
        if abs(no_edge or 0) > abs(yes_edge or 0) and no_edge and no_edge > 0:
            best_side = "NO"
            best_edge = no_edge
            entry_cost = no_ask if no_ask > 0 else (100 - last_price)
        else:
            best_side = "YES"
            best_edge = yes_edge
            entry_cost = yes_ask if yes_ask > 0 else last_price

        opp = {
            "ticker": ticker,
            "title": title,
            "city": (p["city_key"] or "").title(),
            "metric": p["metric"],
            "threshold": p["threshold"],
            "direction": p["direction"],
            "unit": p["unit"],
            "date": p["date"],
            "date_type": p.get("date_type", "daily"),
            "nws_value": forecast["value"],
            "nws_confidence": forecast["confidence"],
            "nws_detail": forecast["detail"],
            "nws_prob": nws_prob,
            "market_price": round(mid_price, 1),
            "yes_bid": yes_bid,
            "yes_ask": yes_ask,
            "no_bid": no_bid,
            "no_ask": no_ask,
            "spread": spread,
            "best_side": best_side,
            "edge": best_edge,
            "entry_cost": entry_cost,
            "profit_if_win": 100 - entry_cost if entry_cost else 0,
            "volume_24h": volume,
            "url": kalshi_url(ticker),
            "close_time": m.get("close_time", ""),
        }
        opportunities.append(opp)

    # Filter by minimum edge
    strong_opps = [o for o in opportunities if abs(o["edge"] or 0) >= min_edge]
    strong_opps.sort(key=lambda x: -abs(x["edge"] or 0))

    # All markets info for report
    all_markets_info = []
    for m in markets:
        all_markets_info.append({
            "ticker": m.get("ticker", ""),
            "title": m.get("title", ""),
            "price": m.get("last_price"),
            "yes_bid": m.get("yes_bid"),
            "yes_ask": m.get("yes_ask"),
            "close_time": m.get("close_time", ""),
        })

    stats = {
        "total_weather_markets": len(markets),
        "parseable_markets": parseable,
        "parse_rate": f"{100*parseable//max(len(markets),1)}%",
        "opportunities_found": len(strong_opps),
        "total_with_forecast": len(opportunities),
        "min_edge": min_edge,
        "skipped": skipped,
        "skipped_examples": skipped_examples,
        "cities_checked": sorted(list(cities_needed)),
        "all_markets_info": all_markets_info,
    }

    return strong_opps, stats


def format_report(opportunities, stats):
    """Format human-readable weather scan report."""
    now = datetime.now(timezone.utc)
    lines = []
    lines.append("=" * 65)
    lines.append(f"🌤️  WEATHER MARKET SCAN — {now.strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("=" * 65)
    lines.append(f"Markets scanned: {stats.get('total_weather_markets', 0)}")
    lines.append(f"Parseable: {stats.get('parseable_markets', 0)} ({stats.get('parse_rate', '?')})")
    lines.append(f"With NWS forecast: {stats.get('total_with_forecast', 0)}")
    lines.append(f"Min edge filter: {stats.get('min_edge', 5)}¢")

    skipped = stats.get("skipped", {})
    if skipped:
        skip_parts = []
        for key in ["no_city", "no_metric", "no_threshold", "no_forecast", "not_actionable"]:
            if skipped.get(key):
                skip_parts.append(f"{key}: {skipped[key]}")
        if skip_parts:
            lines.append(f"Skipped: {', '.join(skip_parts)}")

    lines.append(f"NWS cities: {', '.join(c.title() for c in stats.get('cities_checked', []))}")
    lines.append(f"\n🎯 Found {len(opportunities)} opportunities with edge ≥ {stats.get('min_edge', 5)}¢\n")

    if not opportunities:
        lines.append("  ✅ No significant mispricings found\n")
        return "\n".join(lines)

    # Group by confidence
    high = [o for o in opportunities if o.get("nws_confidence") == "HIGH"]
    med = [o for o in opportunities if o.get("nws_confidence") == "MEDIUM"]
    low = [o for o in opportunities if o.get("nws_confidence") == "LOW"]

    for label, group in [("🟢 HIGH CONFIDENCE (1-2 days)", high),
                         ("🟡 MEDIUM CONFIDENCE (3-5 days)", med),
                         ("🔴 LOW CONFIDENCE (6-7+ days)", low)]:
        if not group:
            continue
        lines.append(f"\n{label} — {len(group)} opportunities")
        lines.append("-" * 55)

        for opp in group:
            edge_icon = "🚨" if abs(opp["edge"]) >= 15 else ("⚠️" if abs(opp["edge"]) >= 10 else "📊")
            lines.append(f"\n  {edge_icon} {opp['ticker']}")
            lines.append(f"     {opp['title'][:70]}")
            lines.append(f"     📍 {opp['city']} | {opp['metric'].replace('_', ' ').title()} | "
                         f"{opp['direction']} {opp['threshold']}{opp.get('unit', '')}")
            lines.append(f"     🌤️  NWS: {opp['nws_value']} → prob {opp['nws_prob']}%")
            lines.append(f"     💰 Kalshi: {opp['market_price']}¢ (bid {opp['yes_bid']} / ask {opp['yes_ask']})")
            lines.append(f"     📈 {opp['best_side']}: edge {'+' if opp['edge'] > 0 else ''}{opp['edge']}¢ | "
                         f"entry {opp['entry_cost']}¢ → profit {opp['profit_if_win']}¢")
            if opp.get("nws_detail"):
                lines.append(f"     📝 {opp['nws_detail'][:80]}")
            lines.append(f"     🔗 {opp['url']}")

    lines.append("\n" + "=" * 65)
    lines.append("💡 HIGH confidence near settlement = best opportunities.")
    lines.append("   Always verify with latest NWS data before trading.")
    lines.append("=" * 65)

    return "\n".join(lines)


def save_results(opportunities, stats, path=None):
    """Save results to JSON."""
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "weather-scan-results.json")

    output = {
        "scan_time": datetime.now(timezone.utc).isoformat(),
        "stats": stats,
        "opportunities": opportunities,
    }

    with open(path, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\n💾 Results saved to {path}", flush=True)


def main():
    min_edge = 5
    verbose = False

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--min-edge" and i + 1 < len(args):
            min_edge = int(args[i + 1])
            i += 2
        elif args[i] == "--verbose":
            verbose = True
            i += 1
        else:
            i += 1

    print(f"⚙️  Min edge: {min_edge}¢ | Verbose: {verbose}\n", flush=True)

    opportunities, stats = scan_weather_markets(min_edge=min_edge, verbose=verbose)

    report = format_report(opportunities, stats)
    print(report, flush=True)

    save_results(opportunities, stats)

    return opportunities, stats


if __name__ == "__main__":
    main()
