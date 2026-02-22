"""
Kalshi URL Mapping

The Kalshi website uses URLs like:
  https://kalshi.com/markets/{series}/{slug}/{event_ticker}

But the API doesn't return the slug. This module provides the mapping.

Usage:
    from url_mapping import get_market_url
    url = get_market_url("KXCPI-26FEB", "KXCPI-26FEB-T0.3")
"""

# Series ticker -> (series_slug, event_slug)
# Discovered by browsing kalshi.com
SERIES_SLUGS = {
    # Economics
    "KXCPI": ("kxcpi", "cpi"),
    "KXCPICORE": ("kxcpicore", "cpi-core"),
    "KXCPIYOY": ("kxcpiyoy", "inflation"),
    "KXGDP": ("kxgdp", "us-gdp-growth"),
    "KXPAYROLLS": ("kxpayrolls", "jobs-numbers"),
    "KXFEDDECISION": ("kxfeddecision", "fed-meeting"),
    "KXFED": ("kxfed", "fed-funds-rate"),
    "KXU3": ("kxu3", "unemployment"),
    "KXAAAGASW": ("kxaaagasw", "us-gas-price-up"),
    "KXAAAGASM": ("kxaaagasm", "us-gas-price"),
    
    # Fed Mentions
    "KXFEDMENTION": ("kxfedmention", "fed-mention"),
    
    # Weather
    "KXHIGH": ("kxhigh", "high-temperature"),
    "KXLOW": ("kxlow", "low-temperature"),
}


def get_series_from_event(event_ticker: str) -> str:
    """Extract series from event ticker (e.g., KXCPI-26FEB -> KXCPI)"""
    parts = event_ticker.upper().split("-")
    if len(parts) >= 2:
        # Try progressively shorter prefixes
        for i in range(len(parts), 0, -1):
            candidate = "-".join(parts[:i])
            if candidate in SERIES_SLUGS:
                return candidate
        # Fallback: first part
        return parts[0]
    return event_ticker


def get_market_url(event_ticker: str, ticker: str = None) -> str:
    """
    Get the correct Kalshi market URL.
    
    Args:
        event_ticker: e.g., "KXCPI-26FEB"
        ticker: e.g., "KXCPI-26FEB-T0.3" (optional, for specific bracket)
    
    Returns:
        URL string
    """
    series = get_series_from_event(event_ticker)
    
    if series in SERIES_SLUGS:
        series_slug, event_slug = SERIES_SLUGS[series]
        return f"https://kalshi.com/markets/{series_slug}/{event_slug}/{event_ticker.lower()}"
    else:
        # Fallback to search
        query = ticker or event_ticker
        return f"https://kalshi.com/search?query={query}"


def get_event_url(event_ticker: str) -> str:
    """Get URL for event page (shows all brackets)"""
    return get_market_url(event_ticker)


if __name__ == "__main__":
    # Test
    examples = [
        ("KXCPI-26FEB", "KXCPI-26FEB-T0.3"),
        ("KXGDP-26APR30", "KXGDP-26APR30-T2.0"),
        ("KXFEDMENTION-26MAR", "KXFEDMENTION-26MAR-STAG"),
        ("KXPAYROLLS-26FEB", None),
    ]
    
    for event, ticker in examples:
        print(f"{event}: {get_market_url(event, ticker)}")
