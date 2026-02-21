#!/usr/bin/env python3
"""
nowcast_fetcher - 实时经济数据获取

功能：
    - GDPNow: Atlanta Fed RSS
    - CPI: Cleveland Fed JSON API
    - 统一接口 get_for_market()

用法：
    from nowcast_fetcher import NowcastFetcher
    fetcher = NowcastFetcher()
    result = fetcher.get_for_market("KXGDP", 2.5)
    
依赖：
    - urllib.request
"""

import json
import re
import urllib.request
from datetime import datetime
from typing import Optional, Dict, Any


def fetch_gdpnow() -> Dict[str, Any]:
    """
    Fetch GDPNow GDP growth forecast from Atlanta Fed RSS feed.
    
    Returns:
        Dict with 'value' (float), 'date' (str), 'quarter' (str), 'source' (str)
    """
    url = "https://www.atlantafed.org/rss/GDPNow"
    
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode('utf-8')
        
        # Parse RSS content for latest GDPNow estimate
        # Look for pattern like "3.1 percent" in description
        match = re.search(r'([+-]?\d+\.?\d*)\s*percent', content, re.IGNORECASE)
        if match:
            value = float(match.group(1))
            
            # Extract date from pubDate
            date_match = re.search(r'<pubDate>([^<]+)</pubDate>', content)
            pub_date = date_match.group(1) if date_match else datetime.now().strftime('%Y-%m-%d')
            
            # Extract quarter info
            quarter_match = re.search(r'(Q[1-4]\s*\d{4}|\d{4}:Q[1-4])', content)
            quarter = quarter_match.group(1) if quarter_match else "Current"
            
            return {
                'value': value,
                'date': pub_date,
                'quarter': quarter,
                'source': 'Atlanta Fed GDPNow RSS',
                'url': url
            }
    except Exception as e:
        print(f"[GDPNow] Error fetching RSS: {e}")
    
    # Fallback: scrape the main page
    try:
        page_url = "https://www.atlantafed.org/cqer/research/gdpnow"
        req = urllib.request.Request(page_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode('utf-8')
        
        # Look for the estimate value
        match = re.search(r'([+-]?\d+\.?\d*)\s*percent', content, re.IGNORECASE)
        if match:
            return {
                'value': float(match.group(1)),
                'date': datetime.now().strftime('%Y-%m-%d'),
                'quarter': 'Current',
                'source': 'Atlanta Fed GDPNow Page',
                'url': page_url
            }
    except Exception as e:
        print(f"[GDPNow] Error fetching page: {e}")
    
    return {
        'value': None,
        'error': 'Failed to fetch GDPNow data',
        'source': 'Atlanta Fed GDPNow'
    }


def fetch_cleveland_fed_cpi(recent_only: bool = True, num_quarters: int = 4) -> Dict[str, Any]:
    """
    Fetch CPI inflation nowcast from Cleveland Fed JSON API.
    
    Args:
        recent_only: If True, only return the most recent quarters
        num_quarters: Number of recent quarters to return
    
    Returns:
        Dict with CPI, Core CPI, PCE, Core PCE nowcasts and metadata
    """
    url = "https://www.clevelandfed.org/-/media/files/webcharts/inflationnowcasting/nowcast_quarter.json"
    
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode('utf-8')
        
        # Parse JSON - it's an array of quarters
        data = json.loads(content)
        
        # Get only recent quarters if requested
        if recent_only:
            data = data[-num_quarters:]
        
        result = {
            'quarters': [],
            'source': 'Cleveland Fed Inflation Nowcasting',
            'url': url,
            'fetched_at': datetime.now().isoformat()
        }
        
        for quarter_data in data:
            chart = quarter_data.get('chart', {})
            quarter_name = chart.get('subcaption', 'Unknown')
            
            quarter_result = {
                'quarter': quarter_name,
                'cpi': None,
                'core_cpi': None,
                'pce': None,
                'core_pce': None
            }
            
            # Parse dataset to extract latest values
            dataset = quarter_data.get('dataset', [])
            for series in dataset:
                series_name = series.get('seriesname', '').lower()
                data_points = series.get('data', [])
                
                # Get the last non-empty value
                for point in reversed(data_points):
                    value = point.get('value', '')
                    if value and value.strip():
                        try:
                            val = float(value)
                            if 'core cpi' in series_name and 'actual' not in series_name:
                                quarter_result['core_cpi'] = val
                            elif 'cpi' in series_name and 'actual' not in series_name:
                                quarter_result['cpi'] = val
                            elif 'core pce' in series_name and 'actual' not in series_name:
                                quarter_result['core_pce'] = val
                            elif 'pce' in series_name and 'actual' not in series_name:
                                quarter_result['pce'] = val
                            break
                        except ValueError:
                            continue
            
            result['quarters'].append(quarter_result)
        
        return result
        
    except Exception as e:
        print(f"[Cleveland Fed] Error: {e}")
        return {
            'error': str(e),
            'source': 'Cleveland Fed Inflation Nowcasting'
        }


def get_latest_cpi_nowcast() -> Optional[float]:
    """Get the latest CPI inflation nowcast value."""
    data = fetch_cleveland_fed_cpi()
    if 'quarters' in data and data['quarters']:
        # Return the most recent quarter's CPI
        for q in reversed(data['quarters']):
            if q.get('cpi') is not None:
                return q['cpi']
    return None


def get_latest_gdp_nowcast() -> Optional[float]:
    """Get the latest GDP nowcast value."""
    data = fetch_gdpnow()
    return data.get('value')


def fetch_all_nowcasts() -> Dict[str, Any]:
    """Fetch all nowcasts and return combined data."""
    return {
        'gdp': fetch_gdpnow(),
        'inflation': fetch_cleveland_fed_cpi(),
        'timestamp': datetime.now().isoformat()
    }


class NowcastFetcher:
    """Wrapper class for compatibility with kalshi_pipeline.py"""
    
    def __init__(self):
        self._gdp_cache = None
        self._cpi_cache = None
        self._cache_time = None
    
    def _refresh_cache(self):
        """Refresh cache if older than 5 minutes."""
        now = datetime.now()
        if self._cache_time and (now - self._cache_time).seconds < 300:
            return
        
        self._gdp_cache = fetch_gdpnow()
        self._cpi_cache = fetch_cleveland_fed_cpi(recent_only=True, num_quarters=4)
        self._cache_time = now
    
    def get_for_market(self, series: str, threshold: float) -> Optional[Dict[str, Any]]:
        """
        Get nowcast data for a specific market.
        
        Args:
            series: Series ticker (e.g., "KXGDP", "KXCPI")
            threshold: Market threshold (e.g., 2.5 for "above 2.5%")
        
        Returns:
            Dict with nowcast_value, threshold, direction, z_score, confidence, source
        """
        self._refresh_cache()
        
        series_upper = series.upper()
        
        if "GDP" in series_upper:
            return self._get_gdp_nowcast(threshold)
        elif "CPI" in series_upper:
            return self._get_cpi_nowcast(threshold)
        elif "FED" in series_upper:
            # Fed rate decisions - would need CME FedWatch
            return None
        
        return None
    
    def _get_gdp_nowcast(self, threshold: float) -> Optional[Dict[str, Any]]:
        """Get GDP nowcast signal."""
        if not self._gdp_cache or self._gdp_cache.get('value') is None:
            return None
        
        nowcast_value = self._gdp_cache['value']
        
        # Calculate z-score (assuming ~0.5% historical std)
        historical_std = 0.5
        z_score = (nowcast_value - threshold) / historical_std
        
        direction = "yes" if nowcast_value > threshold else "no"
        confidence = min(1.0, abs(z_score) / 2)
        
        return {
            "nowcast_value": nowcast_value,
            "threshold": threshold,
            "direction": direction,
            "z_score": z_score,
            "confidence": confidence,
            "source": "Atlanta Fed GDPNow"
        }
    
    def _get_cpi_nowcast(self, threshold: float) -> Optional[Dict[str, Any]]:
        """Get CPI nowcast signal."""
        if not self._cpi_cache or 'quarters' not in self._cpi_cache:
            return None
        
        # Get most recent quarter with CPI data
        for q in reversed(self._cpi_cache['quarters']):
            if q.get('cpi') is not None:
                nowcast_value = q['cpi']
                
                # Calculate z-score (assuming ~0.3% historical std for CPI)
                historical_std = 0.3
                z_score = (nowcast_value - threshold) / historical_std
                
                direction = "yes" if nowcast_value > threshold else "no"
                confidence = min(1.0, abs(z_score) / 2)
                
                return {
                    "nowcast_value": round(nowcast_value, 2),
                    "threshold": threshold,
                    "direction": direction,
                    "z_score": z_score,
                    "confidence": confidence,
                    "source": f"Cleveland Fed ({q['quarter']})"
                }
        
        return None


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == '--json':
        print(json.dumps(fetch_all_nowcasts(), indent=2))
    else:
        print("=" * 60)
        print("ECONOMIC NOWCAST REPORT")
        print("=" * 60)
        print(f"Fetched: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        
        # GDP
        gdp = fetch_gdpnow()
        print("📊 GDP NOWCAST (Atlanta Fed GDPNow)")
        if gdp.get('value') is not None:
            print(f"   Value: {gdp['value']:.1f}%")
            print(f"   Quarter: {gdp.get('quarter', 'N/A')}")
            print(f"   Date: {gdp.get('date', 'N/A')}")
        else:
            print(f"   Error: {gdp.get('error', 'Unknown error')}")
        print()
        
        # Inflation
        inflation = fetch_cleveland_fed_cpi()
        print("📈 INFLATION NOWCAST (Cleveland Fed)")
        if 'quarters' in inflation:
            for q in inflation['quarters']:
                print(f"\n   {q['quarter']}:")
                if q.get('cpi') is not None:
                    print(f"     CPI: {q['cpi']:.2f}%")
                if q.get('core_cpi') is not None:
                    print(f"     Core CPI: {q['core_cpi']:.2f}%")
                if q.get('pce') is not None:
                    print(f"     PCE: {q['pce']:.2f}%")
                if q.get('core_pce') is not None:
                    print(f"     Core PCE: {q['core_pce']:.2f}%")
        else:
            print(f"   Error: {inflation.get('error', 'Unknown error')}")
        
        print()
        print("=" * 60)
