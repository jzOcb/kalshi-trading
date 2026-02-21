#!/usr/bin/env python3
"""
source_detector - 官方数据源检测

功能：
    - 检测市场使用的官方数据源
    - 支持 30+ 正则模式
    - 返回数据源列表和 Tier 级别

用法：
    from source_detector import detect_sources
    sources, tier = detect_sources(market_dict)
    
依赖：
    - re
"""

import re
from typing import Dict, List, Tuple, Optional

# 官方数据源模式 (正则 + 元数据)
OFFICIAL_SOURCE_PATTERNS: List[Tuple[str, str, int, str]] = [
    # (regex_pattern, source_name, research_tier, research_method)
    
    # Tier 1: 官方统计数据
    (r'bls\.gov|bureau of labor statistics', 'BLS', 1, 'Cleveland Fed Nowcast / BLS releases'),
    (r'bea\.gov|bureau of economic analysis', 'BEA', 1, 'Atlanta Fed GDPNow / BEA releases'),
    (r'weather\.gov|national weather service|nws', 'NWS', 1, 'NWS forecast API'),
    (r'federalreserve\.gov|federal reserve|fomc', 'FOMC', 1, 'CME FedWatch + FOMC dots'),
    (r'census\.gov|census bureau', 'Census', 1, 'Census Bureau releases'),
    
    # Tier 2: 官方日程/公开记录
    (r'treasury\.gov|department of treasury', 'Treasury', 2, 'Treasury statements + debt data'),
    (r'congress\.gov|house\.gov|senate\.gov', 'Congress', 2, '国会日程 + 投票记录'),
    (r'sec\.gov|securities and exchange', 'SEC', 2, 'SEC filings + announcements'),
    (r'cbo\.gov|congressional budget office', 'CBO', 2, 'CBO projections'),
    (r'eia\.gov|energy information', 'EIA', 2, 'EIA energy data'),
    (r'usda\.gov|department of agriculture', 'USDA', 2, 'USDA crop reports'),
    
    # Tier 2: 交易所/市场数据
    (r'cme\s?group|chicago mercantile', 'CME', 2, 'CME settlement prices'),
    # Crypto/股指: 可验证但不可预测（无 edge），降为 Tier 4 排除
    (r'coinmarketcap|coingecko|binance|coinbase', 'Crypto', 4, '无预测 edge'),
    (r'nyse|nasdaq|s&p\s*500|dow jones', 'Exchange', 4, '无预测 edge'),
    
    # Tier 2: 可验证的官方行为 (Executive Orders, 签署法案等)
    (r'executive order|sign.*(order|bill|act)|federal register', 'WhiteHouse', 2, '白宫公告 + Federal Register'),
    
    # Tier 3: 官方公告/新闻驱动
    (r'whitehouse\.gov|white house', 'WhiteHouse', 3, '白宫公告 + 新闻'),
    (r'ustr\.gov|trade representative', 'USTR', 3, 'USTR 贸易公告'),
    (r'state\.gov|department of state', 'State', 3, '国务院声明'),
    (r'dhs\.gov|homeland security', 'DHS', 3, 'DHS 公告'),
    
    # Tier 3: 新闻可研究的政治事件 (有明确结算条件 + 可追踪新闻)
    # 提名/任命
    (r'nominat|appoint.*(chair|secretary|justice|director|ambassador)', 'Nomination', 3, '官方提名 + 新闻追踪'),
    (r'fed\s*chair|federal reserve chair', 'FedChair', 3, '白宫提名 + 参议院确认'),
    (r'supreme court|scotus', 'SCOTUS', 3, '法院公告 + 新闻'),
    (r'cabinet\s*(member|secretary|position)', 'Cabinet', 3, '白宫提名 + 参议院确认'),
    
    # 外交/领土
    (r'greenland|territory|annex|acqui(re|sition)', 'ForeignPolicy', 3, '外交新闻 + 官方声明'),
    (r'tariff.*\d+%|import\s*dut', 'Tariff', 3, 'USTR 公告 + 贸易新闻'),
    (r'sanction|embargo', 'Sanctions', 3, 'Treasury OFAC + 新闻'),
    (r'treaty|agreement.*(sign|ratif)', 'Treaty', 3, '国务院 + 新闻'),
    
    # 国会/弹劾
    (r'impeach|article.*impeachment', 'Impeachment', 3, '国会投票记录 + 新闻'),
    (r'vote.*pass|pass.*vote|floor vote', 'CongressVote', 3, '国会日程 + 投票追踪'),
    (r'veto|override', 'Veto', 3, '白宫声明 + 国会记录'),
    
    # 领导人变动 (可追踪)
    (r'resign|step down|leave office|out as (president|governor|ceo|leader)', 'LeaderChange', 3, '官方声明 + 新闻'),
    (r'recall|special election', 'Recall', 3, '选举委员会 + 新闻'),
    (r'(khamenei|xi jinping|putin|kim jong|erdogan|modi|netanyahu).*(out|leave|die|replace|succeed)', 'ForeignLeader', 3, '国际新闻 + 情报分析'),
    (r'(supreme leader|prime minister|president of).*(iran|china|russia|north korea)', 'ForeignLeader', 3, '国际新闻 + 情报分析'),
    (r'successor.*(xi|putin|khamenei|kim)', 'ForeignLeader', 3, '国际新闻 + 情报分析'),
    (r'(xi|putin|khamenei|kim).*successor', 'ForeignLeader', 3, '国际新闻 + 情报分析'),
    
    # 选举 (有明确结果)
    (r'primary|caucus|runoff', 'Primary', 3, '选举结果 + 民调追踪'),
    (r'midterm|general election.*\d{4}', 'Election', 3, '选举结果 + 民调'),
    (r'electoral vote|winner.*state', 'ElectionResult', 3, '选举结果'),
]

# Tier 9 排除模式 (纯猜测，无法有效研究)
SPECULATION_PATTERNS = [
    r'first\s*(trillionaire|quadrillionaire)',  # 财富猜测
    r'(203\d|204\d).*become.*president',  # 远期总统预测 (2030+)
    r'who will be.*president.*(203|204|205)',  # 远期总统预测
    r'next\s*pope',  # 教皇
    r'alien|ufo|extraterrestrial',  # UFO
    r'world\s*war\s*(3|iii|three)',  # 世界大战
]

# 关键词到数据源的映射 (备用，当正则不匹配时)
KEYWORD_HINTS: Dict[str, Tuple[str, int, str]] = {
    'gdp': ('BEA', 1, 'Atlanta Fed GDPNow'),
    'gross domestic product': ('BEA', 1, 'Atlanta Fed GDPNow'),
    'cpi': ('BLS', 1, 'Cleveland Fed Nowcast'),
    'consumer price index': ('BLS', 1, 'Cleveland Fed Nowcast'),
    'inflation': ('BLS', 1, 'Cleveland Fed Nowcast'),
    'unemployment': ('BLS', 1, 'BLS Employment Report'),
    'jobless claims': ('BLS', 1, 'Weekly DOL Report'),
    'nonfarm payroll': ('BLS', 1, 'BLS Employment Report'),
    'interest rate': ('FOMC', 1, 'CME FedWatch'),
    'federal funds': ('FOMC', 1, 'CME FedWatch'),
    'rate cut': ('FOMC', 1, 'CME FedWatch'),
    'rate hike': ('FOMC', 1, 'CME FedWatch'),
    'temperature': ('NWS', 1, 'NWS forecast API'),
    'high of': ('NWS', 1, 'NWS forecast API'),
    'low of': ('NWS', 1, 'NWS forecast API'),
    'government shutdown': ('Congress', 2, '国会日程 + 预算截止日'),
    'debt ceiling': ('Treasury', 2, 'Treasury X-date + CBO'),
    'tariff': ('USTR', 3, 'USTR 公告 + 贸易新闻'),
    'bitcoin': ('Crypto', 4, '无预测 edge'),
    'ethereum': ('Crypto', 4, '无预测 edge'),
    'btc': ('Crypto', 4, '无预测 edge'),
    'eth': ('Crypto', 4, '无预测 edge'),
    
    # Tier 3: 政治/新闻可研究
    'nominate': ('Nomination', 3, '官方提名 + 新闻'),
    'fed chair': ('FedChair', 3, '白宫提名 + 参议院确认'),
    'impeach': ('Impeachment', 3, '国会记录 + 新闻'),
    'greenland': ('ForeignPolicy', 3, '外交新闻 + 官方声明'),
    'resign': ('LeaderChange', 3, '官方声明 + 新闻'),
    'primary': ('Primary', 3, '选举结果 + 民调'),
    'midterm': ('Election', 3, '选举结果 + 民调'),
    'supreme court': ('SCOTUS', 3, '法院公告 + 新闻'),
}


def detect_sources(rules_primary: str, title: str = "") -> Dict:
    """
    从 rules_primary 和 title 检测官方数据源
    
    Returns:
        {
            "verifiable": bool,
            "sources": ["BLS", "BEA", ...],
            "research_tier": 1-3 (1=最高, 9=纯猜测),
            "research_method": "具体研究方法",
            "detection_method": "regex|keyword|speculation|none"
        }
    """
    text = f"{rules_primary} {title}".lower()
    
    # 0. 先检查是否是纯猜测市场 (强制 Tier 9)
    for pattern in SPECULATION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return {
                "verifiable": True,  # 结算时可验证
                "sources": [],
                "research_tier": 9,
                "research_method": "纯猜测，无有效研究方法",
                "detection_method": "speculation",
            }
    
    found_sources = []
    best_tier = 9
    best_method = ""
    detection = "none"
    
    # 1. 正则匹配官方源
    for pattern, source, tier, method in OFFICIAL_SOURCE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            if source not in found_sources:
                found_sources.append(source)
                if tier < best_tier:
                    best_tier = tier
                    best_method = method
                detection = "regex"
    
    # 2. 关键词匹配 (如果正则没匹配到)
    if not found_sources:
        for keyword, (source, tier, method) in KEYWORD_HINTS.items():
            if keyword in text:
                if source not in found_sources:
                    found_sources.append(source)
                    if tier < best_tier:
                        best_tier = tier
                        best_method = method
                    detection = "keyword"
    
    return {
        "verifiable": len(found_sources) > 0,
        "sources": found_sources,
        "research_tier": best_tier if found_sources else 9,
        "research_method": best_method if found_sources else "无明确数据源",
        "detection_method": detection,
    }


def get_tier_label(tier: int) -> str:
    """获取 tier 的显示标签"""
    return {
        1: "T1官方",
        2: "T2日程", 
        3: "T3新闻",
    }.get(tier, "未知")


# 测试
if __name__ == "__main__":
    test_cases = [
        ("The settlement will be based on data from bls.gov", "CPI January"),
        ("As reported by the Bureau of Economic Analysis", "GDP Q1"),
        ("Based on National Weather Service observations", "Temperature Boston"),
        ("If Congress passes a continuing resolution", "Government Shutdown"),
        ("Bitcoin price at 4pm ET from CoinGecko", "BTC Daily"),
        ("Some random market with no clear source", "Unknown Event"),
    ]
    
    print("=== Source Detection Tests ===\n")
    for rules, title in test_cases:
        result = detect_sources(rules, title)
        print(f"Title: {title}")
        print(f"  Verifiable: {result['verifiable']}")
        print(f"  Sources: {result['sources']}")
        print(f"  Tier: {get_tier_label(result['research_tier'])}")
        print(f"  Method: {result['research_method']}")
        print(f"  Detection: {result['detection_method']}")
        print()
