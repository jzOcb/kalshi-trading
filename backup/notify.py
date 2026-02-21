"""
notify - Telegram 格式化通知

功能：
    - 格式化市场报告为 Telegram 消息
    - 支持 emoji 和格式化
    - 发送到指定 chat
    - 铁律：每个推荐必须查证底层事实

用法：
    from notify import send_telegram
    send_telegram("消息内容")
    
依赖：
    - TELEGRAM_BOT_TOKEN 环境变量
    - TELEGRAM_CHAT_ID 环境变量
    - report_v2.py
"""

import requests
import json
import os
import sys
import time
from datetime import datetime, timezone

# Import decision engine from report_v2
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from report_v2 import (
    fetch_market_details, analyze_rules, score_market,
    search_news, format_vol, kalshi_url
)

API_BASE = "https://api.elections.kalshi.com/trade-api/v2"

POLITICAL_SERIES = [
    "KXGDP", "KXCPI", "KXFED", "KXGOVSHUTLENGTH",
    "KXTRUMPMEETING", "KXGREENLAND", "KXSCOTUS", "KXRECESSION",
    "KXUKRAINE", "KXIRAN", "KXBITCOIN", "KXSP500", "KXDOGE",
    "KXGOVTCUTS", "KXGOVTSPEND", "KXDEBT", "KXCR",
    "KXSHUTDOWNBY", "KXTARIFF", "KXFEDRATE",
    "KXCABINET", "KXTERMINALRATE", "KXLOWESTRATE",
]

# --- Fact Verification (official sources) ---
def verify_facts():
    """Fetch key data points from official sources."""
    facts = {}
    
    # GDP - BEA
    try:
        r = requests.get("https://www.bea.gov/data/gdp/gross-domestic-product", timeout=10)
        text = r.text.lower()
        import re
        if "fourth quarter" in text or "4th quarter" in text:
            facts["gdp_q4_status"] = "✅ Released"
        else:
            facts["gdp_q4_status"] = "⏳ Not yet (Feb 20)"
        pct = re.findall(r'(\d+\.\d+)\s*percent', text)
        if pct:
            facts["gdp_latest_pct"] = pct[0]
        if "third quarter" in text:
            facts["gdp_latest_q"] = "Q3 2025"
        elif "fourth quarter" in text:
            facts["gdp_latest_q"] = "Q4 2025"
    except:
        facts["gdp_q4_status"] = "⚠️ Could not verify"
    
    # CPI - BLS
    try:
        r = requests.get("https://www.bls.gov/cpi/", timeout=10)
        text = r.text.lower()
        if "january 2026" in text:
            facts["cpi_jan_status"] = "✅ Jan 2026 released"
        elif "december 2025" in text:
            facts["cpi_jan_status"] = "⏳ Jan CPI not yet (Feb ~12)"
        else:
            facts["cpi_jan_status"] = "⚠️ Check bls.gov/cpi"
    except:
        facts["cpi_jan_status"] = "⚠️ Could not verify"
    
    # Govt shutdown - OPM
    try:
        r = requests.get("https://www.opm.gov/policy-data-oversight/snow-dismissal-procedures/current-status/", timeout=10)
        text = r.text.lower()
        if "shut down" in text or "shutdown" in text or "lapse" in text:
            facts["shutdown"] = "✅ Shutdown active"
        elif "open" in text:
            facts["shutdown"] = "✅ Govt open"
        else:
            facts["shutdown"] = "⚠️ Check opm.gov"
    except:
        facts["shutdown"] = "⚠️ Could not verify"
    
    return facts

def fact_tag(ticker, facts):
    """Return fact verification line for a ticker."""
    t = ticker.upper()
    if "KXGDP" in t:
        s = facts.get("gdp_q4_status", "⚠️")
        q = facts.get("gdp_latest_q", "?")
        p = facts.get("gdp_latest_pct", "?")
        return f"📋 {s} | Latest: {q} @ {p}%"
    elif "KXCPI" in t:
        return f"📋 {facts.get('cpi_jan_status', '⚠️')}"
    elif "KXGOVSHUT" in t:
        return f"📋 {facts.get('shutdown', '⚠️')}"
    elif "KXFED" in t:
        return "📋 ⏳ Check federalreserve.gov"
    return None


def api_get(endpoint, params=None):
    try:
        resp = requests.get(f"{API_BASE}{endpoint}", params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except:
        return None

def scan():
    now = datetime.now(timezone.utc)
    
    # Load previous state
    state_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")
    prev_state = {}
    try:
        with open(state_path) as f:
            prev_state = json.load(f)
    except:
        pass
    prev_prices = prev_state.get("prices", {})
    
    # Step 1: Quick scan all markets
    all_markets = []
    for series in POLITICAL_SERIES:
        data = api_get("/markets", {"limit": 50, "status": "open", "series_ticker": series})
        if data:
            all_markets.extend(data.get("markets", []))
    
    # Step 2: Verify facts from official sources
    facts = verify_facts()
    
    # Step 3: Find junk bond candidates + movers
    junk_candidates = []
    movers = []
    current_prices = {}
    
    for m in all_markets:
        close_str = m.get("close_time", "")
        if not close_str:
            continue
        try:
            close = datetime.fromisoformat(close_str.replace("Z", "+00:00"))
        except:
            continue
        days = (close - now).days
        if days <= 0:
            continue
        
        ticker = m.get("ticker", "")
        price = m.get("last_price", 50)
        prev = m.get("previous_price", price)
        vol = m.get("volume_24h", 0)
        spread = (m.get("yes_ask", 0) - m.get("yes_bid", 0)) if m.get("yes_ask") else 99
        title = m.get("title", "").replace("**", "")
        
        current_prices[ticker] = price
        name = title if title else (m.get("yes_sub_title", "") or m.get("no_sub_title", ""))
        if len(name) > 60:
            name = name[:57] + "..."
        
        # Junk bond candidate
        if (price >= 85 or price <= 12) and days <= 60 and spread <= 15:
            side = "YES" if price >= 85 else "NO"
            cost = price if price >= 85 else (100 - price)
            ret = ((100 - cost) / cost) * 100 if cost > 0 else 0
            ann = (ret / max(days, 1)) * 365
            if ret >= 3:
                junk_candidates.append({
                    "market": m, "name": name, "side": side, "cost": cost,
                    "ret": ret, "ann": ann, "days": days,
                    "spread": spread, "vol": vol, "ticker": ticker,
                })
        
        # 24h movers
        if abs(price - prev) >= 5 and vol >= 10:
            d = "📈" if price > prev else "📉"
            movers.append({
                "name": name, "old": prev, "new": price,
                "delta": abs(price - prev), "icon": d,
                "vol": vol, "ticker": ticker,
            })
    
    # Step 4: Deep verify top junk bonds using report_v2 scoring
    junk_candidates.sort(key=lambda x: -x["ann"])
    scored_junks = []
    for jc in junk_candidates[:15]:  # Only deep-analyze top 15
        m = jc["market"]
        ticker = jc["ticker"]
        # Fetch rules
        detailed = fetch_market_details(ticker)
        if detailed:
            m["rules_primary"] = detailed.get("rules_primary", "")
            m["rules_secondary"] = detailed.get("rules_secondary", "")
        result = score_market(m)
        if result:
            jc["score"] = result["score"]
            jc["decision"] = result["decision"]
            jc["reasons"] = result["reasons"]
        else:
            jc["score"] = 0
            jc["decision"] = "🔴 SKIP"
            jc["reasons"] = ["未通过评分"]
        scored_junks.append(jc)
        time.sleep(0.15)  # Rate limit
    
    movers.sort(key=lambda x: -x["delta"])
    
    # Step 5: Format report
    lines = []
    lines.append(f"⚡ Kalshi Scan — {now.strftime('%m/%d %H:%M UTC')}")
    lines.append(f"Markets: {len(all_markets)} | Analyzed: {len(scored_junks)}")
    lines.append("")
    
    # Group by decision
    buys = [j for j in scored_junks if "BUY" in j.get("decision", "")]
    waits = [j for j in scored_junks if "WAIT" in j.get("decision", "")]
    skips = [j for j in scored_junks if "SKIP" in j.get("decision", "")]
    
    if buys:
        lines.append(f"🟢 BUY ({len(buys)})")
        lines.append("")
        for jb in buys[:5]:
            ticker = jb['ticker']
            event_ticker = '-'.join(ticker.rsplit('-', 1)[0:1]) if '-' in ticker else ticker
            lines.append(f"🟢 {jb['name']}")
            lines.append(f"   {jb['side']}@{jb['cost']}¢ → +{jb['ret']:.0f}% / {jb['days']}d ({jb['ann']:.0f}%ann)")
            lines.append(f"   Score: {jb['score']}/100 | {' | '.join(jb['reasons'][:3])}")
            ft = fact_tag(ticker, facts)
            if ft:
                lines.append(f"   {ft}")
            lines.append(f"   vol:{jb['vol']} | 🔗 https://kalshi.com/events/{event_ticker}")
            lines.append("")
    
    if waits:
        lines.append(f"🟡 WAIT ({len(waits)})")
        lines.append("")
        for jb in waits[:5]:
            ticker = jb['ticker']
            event_ticker = '-'.join(ticker.rsplit('-', 1)[0:1]) if '-' in ticker else ticker
            lines.append(f"🟡 {jb['name']}")
            lines.append(f"   {jb['side']}@{jb['cost']}¢ → +{jb['ret']:.0f}% / {jb['days']}d ({jb['ann']:.0f}%ann)")
            lines.append(f"   Score: {jb['score']}/100 | {' | '.join(jb['reasons'][:3])}")
            ft = fact_tag(ticker, facts)
            if ft:
                lines.append(f"   {ft}")
            lines.append(f"   vol:{jb['vol']} | 🔗 https://kalshi.com/events/{event_ticker}")
            lines.append("")
    
    if not buys and not waits:
        # Show top skips so user knows what was rejected and why
        lines.append(f"🔴 No recommendations — top candidates rejected:")
        lines.append("")
        for jb in skips[:5]:
            ticker = jb['ticker']
            event_ticker = '-'.join(ticker.rsplit('-', 1)[0:1]) if '-' in ticker else ticker
            lines.append(f"🔴 {jb['name']}")
            lines.append(f"   {jb['side']}@{jb['cost']}¢ → +{jb['ret']:.0f}% / {jb['days']}d ({jb['ann']:.0f}%ann)")
            lines.append(f"   Score: {jb['score']}/100 | {' | '.join(jb['reasons'][:3])}")
            ft = fact_tag(ticker, facts)
            if ft:
                lines.append(f"   {ft}")
            lines.append(f"   🔗 https://kalshi.com/events/{event_ticker}")
            lines.append("")
    
    # 24h movers
    if movers:
        lines.append(f"🔥 24H MOVERS ({len(movers)})")
        lines.append("")
        for mv in movers[:5]:
            event_ticker = '-'.join(mv['ticker'].rsplit('-', 1)[0:1]) if '-' in mv['ticker'] else mv['ticker']
            lines.append(f"{mv['icon']} {mv['name']}")
            lines.append(f"   {mv['old']}¢→{mv['new']}¢ (Δ{mv['delta']}¢) vol:{mv['vol']}")
            lines.append(f"   🔗 https://kalshi.com/events/{event_ticker}")
            lines.append("")
    
    if not scored_junks and not movers:
        lines.append("😴 Nothing notable right now")
    
    report = "\n".join(lines)
    
    # Save state
    new_state = {
        "last_scan": now.isoformat(),
        "prices": current_prices,
        "markets_count": len(all_markets),
    }
    try:
        with open(state_path, "w") as f:
            json.dump(new_state, f, indent=2)
    except:
        pass
    
    return report

if __name__ == "__main__":
    print(scan())
