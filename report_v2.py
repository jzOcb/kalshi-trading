import warnings; warnings.filterwarnings("ignore", message="urllib3 v2")
"""
Kalshi Enhanced Report with Decision Engine
Scans markets → Analyzes rules → Makes BUY/WAIT/SKIP recommendations
"""
import sys

try:
    import requests
except ImportError:
    import urllib.request
    import urllib.parse
    import json as _json
    print("⚠️ requests not available, using urllib fallback", file=sys.stderr)
    
    class _Response:
        def __init__(self, status, body):
            self.status_code = status
            self._body = body
            self.text = body.decode('utf-8')  # Add .text attribute
        def json(self):
            return _json.loads(self._body.decode('utf-8'))
        def raise_for_status(self):
            if not (200 <= self.status_code < 300):
                raise Exception(f"HTTP {self.status_code}")
    
    class requests:
        @staticmethod
        def get(url, params=None, timeout=15):
            if params:
                url = url + "?" + urllib.parse.urlencode(params)
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                body = response.read()
                return _Response(response.status, body)
import json
import os
import re
import time
from datetime import datetime, timezone, timedelta

API_BASE = "https://api.elections.kalshi.com/trade-api/v2"
WATCHLIST_FILE = os.path.join(os.path.dirname(__file__), "data", "watchlist_series.json")

# Fallback 硬编码列表 (当 watchlist 不存在时使用)
FALLBACK_SERIES = [
    "KXGDP", "KXCPI", "KXFED", "KXPCE", "KXJOBLESS", "KXUNEMPLOY",
    "KXFOMC", "KXRATECUTCOUNT", "KXAAGAS", "KXGASMAX", "KXGASAVG",
    "KXSHUTDOWN", "KXDHSFUND", "KXDEBT", "KXTARIFF", "KXRECESSION",
    "KXCR", "KXEOWEEK", "KXEOTRUMPTERM", "KXBILLSIGNED", "KXCABINET",
]

def load_watchlist_series():
    """从 watchlist_series.json 加载 series 列表"""
    try:
        if os.path.exists(WATCHLIST_FILE):
            with open(WATCHLIST_FILE) as f:
                data = json.load(f)
            series = data.get("series", [])
            if series:
                print(f"📋 从 watchlist 加载 {len(series)} 个 series", file=sys.stderr)
                return series
    except Exception as e:
        print(f"⚠️ 读取 watchlist 失败: {e}", file=sys.stderr)
    
    print(f"📋 使用 fallback series ({len(FALLBACK_SERIES)} 个)", file=sys.stderr)
    return FALLBACK_SERIES

def api_get(endpoint, params=None):
    try:
        resp = requests.get(f"{API_BASE}{endpoint}", params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        # print(f"API error on {endpoint}: {e}")  # Suppress noise
        return None

def fetch_market_details(ticker):
    """Fetch complete market details including rules"""
    data = api_get(f"/markets/{ticker}")
    if not data:
        return None
    return data.get("market", {})

def kalshi_url(ticker):
    return f"https://kalshi.com/markets/{ticker.lower()}"

def search_polymarket(query, max_results=3):
    """Search Polymarket for matching markets, return YES probability (0-1) or None"""
    try:
        r = requests.get("https://gamma-api.polymarket.com/events",
                        params={"active": "true", "closed": "false", "limit": 20},
                        timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()
        events = data if isinstance(data, list) else []
        # Fuzzy match by title keywords
        query_lower = query.lower()
        for event in events:
            title = event.get("title", "").lower()
            # Check if 2+ keywords match
            keywords = [w for w in query_lower.split() if len(w) > 3]
            matches = sum(1 for kw in keywords if kw in title)
            if matches >= 2:
                markets = event.get("markets", [])
                if markets:
                    # Get the main market price (0-1 range)
                    prices = json.loads(markets[0].get("outcomePrices", "[]"))
                    if prices:
                        return float(prices[0])
        return None
    except:
        return None


def search_news(query, max_results=5):
    """Search Google News RSS for recent articles"""
    results = []
    try:
        import urllib.parse
        query_encoded = urllib.parse.quote(query)
        url = f"https://news.google.com/rss/search?q={query_encoded}&hl=en-US&gl=US&ceid=US:en"
        
        if hasattr(requests, 'get'):
            # Using requests
            r = requests.get(url, timeout=10)
            text = r.text
        else:
            # Using urllib fallback
            import urllib.request
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as resp:
                text = resp.read().decode('utf-8')
        
        import re
        titles = re.findall(r'<title>(.*?)</title>', text)
        dates = re.findall(r'<pubDate>(.*?)</pubDate>', text)
        
        for i, title in enumerate(titles[1:max_results+1]):  # skip feed title
            results.append({
                "title": title,
                "date": dates[i] if i < len(dates) else "",
            })
    except Exception as e:
        # Fail silently, don't block on news errors
        pass
    return results

def format_vol(v):
    if v >= 1_000_000:
        return f"{v/1_000_000:.1f}M"
    elif v >= 1_000:
        return f"{v/1_000:.0f}K"
    return str(v)

def analyze_rules(rules_text):
    """Parse resolution rules"""
    analysis = {
        "official_source": None,
        "procedural_risk": False,
        "time_window": None,
        "ambiguity": False,
    }
    
    if not rules_text:
        analysis["ambiguity"] = True
        return analysis
    
    text_lower = rules_text.lower()
    
    # Official data sources
    sources = {
        "BEA": ["bureau of economic analysis", "bea.gov", "bea's", " bea ", "gdp release"],
        "BLS": ["bureau of labor statistics", "bls.gov", "bls's", " bls ", "cpi release"],
        "Fed": ["federal reserve", "fomc", "fed.gov", "interest rate decision"],
        "Congress": ["congress.gov", "congressional", "legislative", "house.gov", "senate.gov"],
        "White House": ["whitehouse.gov", "executive order", "presidential", "president signs"],
        "Treasury": ["treasury.gov", "treasury department"],
    }
    
    for source, keywords in sources.items():
        if any(kw in text_lower for kw in keywords):
            analysis["official_source"] = source
            break
    
    # Implicit sources (inferred from indicators mentioned in rules)
    if not analysis["official_source"]:
        # CPI → BLS
        if "consumer price index" in text_lower or " cpi " in text_lower:
            analysis["official_source"] = "BLS"
        # GDP → BEA
        elif " gdp " in text_lower or "gross domestic product" in text_lower or "real gdp" in text_lower:
            analysis["official_source"] = "BEA"
        # Unemployment → BLS
        elif "unemployment" in text_lower or "jobs report" in text_lower:
            analysis["official_source"] = "BLS"
        # Interest rate → Fed
        elif "interest rate" in text_lower or "federal funds rate" in text_lower:
            analysis["official_source"] = "Fed"
    
    # Procedural complexity
    procedural_keywords = [
        "pass both", "senate and house", "signed into law",
        "confirmed by", "ratified", "approved by congress",
    ]
    if any(kw in text_lower for kw in procedural_keywords):
        analysis["procedural_risk"] = True
    
    # Ambiguous terms
    ambiguous_terms = ["may", "could", "might", "approximately", "around"]
    if any(term in text_lower for term in ambiguous_terms):
        analysis["ambiguity"] = True
    
    return analysis

def score_market(m):
    """
    Score and decide on a market.
    
    NEW PHILOSOPHY (2026-02-20 GDP lesson):
    事实核查优先，收益率是次要的。
    
    Tier 1: 可核查性 (GATE - 不通过直接跳过)
    Tier 2: 方向确定性 (决定是否推荐)
    Tier 3: 收益率 (只影响仓位大小)
    """
    reasons = []
    warnings = []
    
    price = m.get("last_price", 50)
    spread = (m.get("yes_ask", 0) - m.get("yes_bid", 0)) if m.get("yes_ask") else 99
    ticker = m.get("ticker", "").upper()
    title_raw = m.get("title", "")
    title = title_raw.lower()
    
    rules_primary = m.get("rules_primary", "")
    rules_secondary = m.get("rules_secondary", "")
    rules = f"{rules_primary} {rules_secondary}"
    text_lower = f"{title} {rules}".lower()
    
    close_str = m.get("close_time", "")
    if not close_str:
        return None
    
    try:
        close = datetime.fromisoformat(close_str.replace("Z", "+00:00"))
        days = (close - datetime.now(timezone.utc)).days
    except:
        return None
    
    if days <= 0:
        return None
    
    side = "YES" if price >= 85 else "NO"
    cost = price if price >= 85 else (100 - price)
    ret = ((100 - cost) / cost) * 100 if cost > 0 else 0
    ann_yield = (ret / max(days, 1)) * 365
    
    if ann_yield < 100:
        return None
    
    # ================================================================
    # TIER 1: 可核查性 (VERIFIABILITY GATE)
    # 问题：这个市场的结果能否被客观数据验证？
    # 不能验证 = 纯赌博 = 直接跳过
    # ================================================================
    
    verifiability_score = 0  # 0-100
    rule_analysis = analyze_rules(rules)
    
    # 有官方数据源 = 可核查
    if rule_analysis["official_source"]:
        verifiability_score += 50
        reasons.append(f"✅ {rule_analysis['official_source']} 数据源")
    else:
        # 检查是否有其他可核查性指标
        verifiable_keywords = [
            ("price", "stock", "index", "s&p", "nasdaq", "dow"),  # 金融数据
            ("temperature", "weather", "rain", "snow"),  # 天气数据
            ("rate", "fed", "central bank", "pboc", "ecb"),  # 央行决策
            ("election", "vote", "poll"),  # 选举结果
        ]
        for keywords in verifiable_keywords:
            if any(kw in text_lower for kw in keywords):
                verifiability_score += 30
                reasons.append("⚠️ 有客观数据但非官方源")
                break
        else:
            reasons.append("❌ 无可核查数据源")
    
    # "Trump 说 X" 类市场 - 难以提前核查
    if "trump" in text_lower and "say" in text_lower:
        verifiability_score -= 40
        warnings.append("🔴 'Trump说'类市场无法提前核查")
    
    # 规则模糊 = 核查困难
    if rule_analysis["ambiguity"]:
        verifiability_score -= 20
        warnings.append("⚠️ 规则模糊，核查困难")
    
    # 程序性风险 = 结果不确定
    if rule_analysis["procedural_risk"]:
        verifiability_score -= 15
        warnings.append("⚠️ 有程序性障碍")
    
    # ================================================================
    # GATE CHECK: 可核查性太低 = 跳过
    # ================================================================
    if verifiability_score < 20:
        return {
            "decision": "🔴 SKIP",
            "score": verifiability_score,
            "confidence": "UNVERIFIABLE",
            "position": 0,
            "side": side,
            "cost": cost,
            "ann_yield": ann_yield,
            "days": days,
            "reasons": reasons + warnings,
            "warnings": warnings,
            "spread": spread,
            "vol": m.get("volume_24h", 0),
            "ticker": ticker,
            "title": title_raw,
            "sub": m.get("yes_sub_title", "") or m.get("no_sub_title", ""),
            "pm_price": None,
            "skip_reason": "无法事实核查",
        }
    
    # ================================================================
    # TIER 2: 方向确定性 (DIRECTION CONFIDENCE)
    # 问题：我们能否判断结果更可能是 YES 还是 NO？
    # ================================================================
    
    direction_score = 0  # 0-100
    
    # Nowcast/模型依赖 = 方向不确定
    is_nowcast_market = False
    if "GDP" in ticker or "gdp" in title:
        is_nowcast_market = True
        direction_score -= 30
        warnings.append("⚠️ GDP依赖GDPNow(Q4误差2.8pp)")
    if "CPI" in ticker or "cpi" in title or "inflation" in title:
        is_nowcast_market = True
        direction_score -= 20
        warnings.append("⚠️ CPI依赖Nowcast模型")
    
    # 政策事件风险 = 方向不确定
    policy_keywords = ["shutdown", "tariff", "trade war", "debt ceiling", "impeach"]
    for kw in policy_keywords:
        if kw in text_lower:
            direction_score -= 25
            warnings.append(f"⚠️ 政策事件({kw})影响方向")
            break
    
    # 高价入场 = 容错空间小
    if cost >= 90:
        direction_score -= 30
        warnings.append(f"🔴 入场{cost}¢，错了亏95%+")
    elif cost >= 85:
        direction_score -= 15
        warnings.append(f"⚠️ 入场{cost}¢，容错空间小")
    
    # Nowcast + 高价 = GDP教训组合
    if is_nowcast_market and cost >= 85:
        direction_score -= 40
        warnings.append("🔴 Nowcast+高价=GDP教训(亏$179)")
    
    # ================================================================
    # TIER 3: 收益率 (YIELD - 只影响仓位)
    # 只有通过 Tier 1 & 2 才考虑收益率
    # ================================================================
    
    # 流动性检查
    liquidity_ok = spread <= 5
    if spread <= 2:
        reasons.append("流动性优")
    elif spread <= 5:
        reasons.append("流动性可")
    else:
        warnings.append("⚠️ 流动性差")
        liquidity_ok = False
    
    reasons.append(f"年化 {ann_yield:.0f}%")
    
    # ================================================================
    # 综合决策
    # ================================================================
    
    # 计算最终得分 (事实核查为主)
    # 权重: 可核查性 60% + 方向确定性 40%
    final_score = (verifiability_score * 0.6) + (direction_score * 0.4) + 50  # +50 baseline
    
    # 收益率只加少量分数 (最多+20)
    yield_bonus = min(ann_yield / 100, 20)
    final_score += yield_bonus
    
    # 决策
    if final_score >= 70 and liquidity_ok and direction_score >= -20:
        decision = "🟢 BUY"
        confidence = "HIGH"
        position = 100 if final_score >= 85 else 50
    elif final_score >= 50 and direction_score >= -40:
        decision = "🟡 WAIT"
        confidence = "MEDIUM"
        position = 25
    else:
        decision = "🔴 SKIP"
        confidence = "LOW"
        position = 0
    
    # News validation (only for promising candidates)
    news_count = 0
    pm_price_val = None
    if final_score >= 50:  # Only search news for candidates worth considering
        title_for_search = m.get("title", "")
        subtitle = m.get("yes_sub_title", "") or m.get("no_sub_title", "")
        
        # Build search query from title keywords
        query_terms = []
        # Extract key terms from title
        import re
        # Clean markdown and special characters first
        title_clean = re.sub(r'\*\*', '', title)  # Remove markdown bold
        title_clean = re.sub(r'[^\w\s]', ' ', title_clean)  # Remove punctuation
        # Remove common words and extract important terms
        title_clean = re.sub(r'\b(will|the|a|an|in|on|at|to|for|of|by|more|than|less|increase|decrease)\b', '', title_clean.lower())
        terms = [t.strip() for t in title_clean.split() if len(t.strip()) > 2][:3]
        query_terms.extend(terms)
        
        if query_terms:
            query = " ".join(query_terms)
            news_results = search_news(query, max_results=5)
            news_count = len([n for n in news_results if n.get("title")])
            
            if news_count >= 3:
                direction_score += 10  # 新闻验证增加方向确定性
                reasons.append(f"✅ {news_count}条新闻佐证")
            elif news_count > 0:
                reasons.append(f"⚠️ 仅{news_count}条新闻")
            else:
                direction_score -= 10
                warnings.append("❌ 无相关新闻佐证")
        
        time.sleep(0.1)

        # Polymarket cross-validation
        if query_terms:
            pm_price_val = search_polymarket(query)
            if pm_price_val is not None:
                kalshi_prob = price / 100
                gap = abs(pm_price_val - kalshi_prob)
                if gap < 0.05:
                    direction_score += 15  # 市场共识增加方向确定性
                    reasons.append(f"✅ Polymarket {pm_price_val:.0%} 一致")
                elif gap > 0.15:
                    warnings.append(f"⚠️ Polymarket {pm_price_val:.0%} 偏差大")

    # 重新计算最终得分（包含新闻/Polymarket验证后的direction_score）
    final_score = (verifiability_score * 0.6) + (direction_score * 0.4) + 50
    final_score += min(ann_yield / 100, 20)  # 收益率只加少量分
    
    # 最终决策
    if final_score >= 70 and liquidity_ok and direction_score >= -20:
        decision = "🟢 BUY"
        confidence = "HIGH"
        position = 100 if final_score >= 85 else 50
    elif final_score >= 50 and direction_score >= -40:
        decision = "🟡 WAIT"
        confidence = "MEDIUM"
        position = 25
    else:
        decision = "🔴 SKIP"
        confidence = "LOW"
        position = 0
    
    all_reasons = reasons + warnings
    
    return {
        "decision": decision,
        "score": int(final_score),
        "confidence": confidence,
        "position": position,
        "side": side,
        "cost": cost,
        "ann_yield": ann_yield,
        "days": days,
        "reasons": all_reasons,
        "warnings": warnings,  # Separate for filtering
        "spread": spread,
        "vol": m.get("volume_24h", 0),
        "ticker": m.get("ticker", ""),
        "title": m.get("title", ""),
        "sub": m.get("yes_sub_title", "") or m.get("no_sub_title", ""),
        "pm_price": pm_price_val,
    }

def scan_and_decide():
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    now = datetime.now(timezone.utc)
    
    # === OPTIMIZATION CONFIG ===
    MIN_VOLUME = 200  # Skip low liquidity markets
    MAX_WORKERS_SERIES = 3   # Conservative: Kalshi rate-limits at 8+ concurrent (429)
    MAX_WORKERS_DETAILS = 5  # Parallel detail fetches
    
    # Step 1: Fetch ALL non-sports markets via Events API (expanded coverage)
    print(f"Scanning ALL non-sports markets via Events API...", file=sys.stderr, flush=True)
    all_markets = []
    
    def fetch_all_events():
        """Fetch all non-sports markets via events API"""
        import requests as _req
        markets = []
        cursor = None
        for page in range(30):
            params = {'limit': 100, 'status': 'open', 'with_nested_markets': 'true'}
            if cursor:
                params['cursor'] = cursor
            try:
                resp = _req.get(f"{API_BASE}/events", params=params, timeout=15)
                if resp.status_code == 429:
                    time.sleep(2)
                    continue
                if resp.status_code != 200:
                    break
                data = resp.json()
                for e in data.get('events', []):
                    cat = e.get('category', '')
                    if cat not in ['Sports', 'Entertainment']:
                        markets.extend(e.get('markets', []))
                cursor = data.get('cursor')
                if not cursor or len(data.get('events', [])) < 100:
                    break
                if page % 5 == 0:
                    print(f"  Page {page}: {len(markets)} markets so far...", file=sys.stderr, flush=True)
            except Exception as ex:
                print(f"  Events API error: {ex}", file=sys.stderr)
                break
        return markets
    
    all_markets = fetch_all_events()
    print(f"  Loaded {len(all_markets)} non-sports markets", file=sys.stderr, flush=True)
    
    # Step 2: Filter candidates (extreme price + volume filter)
    candidates = []
    filtered_low_vol = 0
    for m in all_markets:
        price = m.get("last_price", 50)
        volume = m.get("volume_24h", 0) or m.get("volume", 0)
        
        # Skip low volume markets (optimization)
        if volume < MIN_VOLUME:
            filtered_low_vol += 1
            continue
            
        if (price >= 85 or price <= 12):
            candidates.append(m)
    
    print(f"Found {len(candidates)} candidates from {len(all_markets)} markets (filtered {filtered_low_vol} low-vol)", file=sys.stderr)
    
    # Step 3: Fetch detailed rules (PARALLEL)
    print(f"Analyzing {len(candidates)} candidates (parallel)...", file=sys.stderr, flush=True)
    
    def analyze_candidate(m):
        ticker = m.get("ticker", "")
        detailed = fetch_market_details(ticker)
        if detailed:
            m["rules_primary"] = detailed.get("rules_primary", "")
            m["rules_secondary"] = detailed.get("rules_secondary", "")
            return score_market(m)
        return None
    
    opportunities = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS_DETAILS) as executor:
        futures = {executor.submit(analyze_candidate, m): m for m in candidates}
        done = 0
        for future in as_completed(futures):
            result = future.result()
            if result:
                opportunities.append(result)
            done += 1
            if done % 20 == 0 or done == len(candidates):
                print(f"  Progress: {done}/{len(candidates)} analyzed", file=sys.stderr, flush=True)
    
    # Sort by score
    opportunities.sort(key=lambda x: -x["score"])
    
    # Load existing positions from both accounts
    positions_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "positions.json")
    existing_positions = {}  # ticker -> {side, qty, account}
    try:
        with open(positions_file, "r") as f:
            pos_data = json.load(f)
            for p in pos_data.get("positions", []):
                ticker = p.get("ticker", "")
                existing_positions[ticker] = {
                    "side": p.get("side"),
                    "qty": p.get("contracts", 0),
                    "account": p.get("account", "主账号"),
                    "entry": p.get("entry_price", 0)
                }
    except Exception as e:
        print(f"⚠️ Could not load positions: {e}", file=sys.stderr)
    
    # Format report
    lines = []
    lines.append(f"⚡ Kalshi Decision Report — {now.strftime('%m/%d %H:%M UTC')}")
    lines.append(f"扫描了 {len(all_markets)} 个市场，找到 {len(opportunities)} 个高确定性机会\n")
    
    if not opportunities:
        lines.append("😴 暂无符合标准的机会")
        return "\n".join(lines)
    
    # Categorize
    buys = [o for o in opportunities if "BUY" in o["decision"]]
    waits = [o for o in opportunities if "WAIT" in o["decision"]]
    skips = [o for o in opportunities if "SKIP" in o["decision"]]
    
    # BUY recommendations
    if buys:
        lines.append(f"🟢 推荐买入 ({len(buys)})\n")
        for i, o in enumerate(buys[:5], 1):
            full_name = f"{o['title']} → {o['sub']}" if o['sub'] else o['title']
            ticker = o['ticker']
            
            # Check if already have position
            pos_info = existing_positions.get(ticker)
            pos_tag = ""
            if pos_info:
                pos_tag = f" 📌 已持有 {pos_info['qty']}张{pos_info['side']}@{pos_info['entry']}¢ ({pos_info['account']})"
            
            pm_tag = f" | PM {o['pm_price']:.0%}" if o.get("pm_price") is not None else ""
            lines.append(f"#{i} {o['decision']} — 评分 {o['score']}/100{pos_tag}")
            lines.append(f"   {full_name}")
            lines.append(f"   👉 {o['side']} @ {o['cost']:.0f}¢ | 仓位 ${o['position']}{pm_tag}")
            lines.append(f"   📊 {o['ann_yield']:.0f}% 年化 ({o['days']}天) | spread {o['spread']}¢ | 量 {format_vol(o['vol'])}")
            lines.append(f"   💡 {' | '.join(o['reasons'])}")
            lines.append(f"   🔗 {kalshi_url(o['ticker'])}\n")
    
    # WAIT candidates
    if waits:
        lines.append(f"🟡 观望中 ({len(waits)})\n")
        for o in waits[:3]:
            full_name = f"{o['title']} → {o['sub']}" if o['sub'] else o['title']
            pm_tag = f" | PM {o['pm_price']:.0%}" if o.get("pm_price") is not None else ""
            lines.append(f"   {o['decision']} ({o['score']}/100) — {full_name}")
            lines.append(f"   {o['side']} @ {o['cost']:.0f}¢ | {o['ann_yield']:.0f}% ann{pm_tag}")
            lines.append(f"   💡 {' | '.join(o['reasons'])}")
            lines.append(f"   {kalshi_url(o['ticker'])}\n")
    
    # SKIP (show why they were rejected)
    if skips and not buys and not waits:
        lines.append(f"🔴 已拒绝 ({len(skips)}) — 高收益但风险不可控\n")
        for o in skips[:3]:
            full_name = f"{o['title']} → {o['sub']}" if o['sub'] else o['title']
            lines.append(f"   SKIP ({o['score']}/100) — {full_name}")
            lines.append(f"   {o['side']} @ {o['cost']:.0f}¢ | {o['ann_yield']:.0f}% ann")
            lines.append(f"   ❌ 拒绝原因: {' | '.join(o['reasons'])}")
            lines.append(f"   {kalshi_url(o['ticker'])}\n")
    
    if not buys and not waits:
        lines.append("\n⚠️ 本轮扫描无推荐标的 — 所有高收益机会都因规则/数据源问题被拒绝")
    
    return "\n".join(lines)

if __name__ == "__main__":
    report = scan_and_decide()
    print(report)
