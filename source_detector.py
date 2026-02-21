#!/usr/bin/env python3
"""
官方数据源检测模块

从 rules_primary 动态识别可研究性，无需白名单维护。
Scanner 和 Researcher 都调用这个。
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
}


def detect_sources(rules_primary: str, title: str = "") -> Dict:
    """
    从 rules_primary 和 title 检测官方数据源
    
    Returns:
        {
            "verifiable": bool,
            "sources": ["BLS", "BEA", ...],
            "research_tier": 1-3 (1=最高),
            "research_method": "具体研究方法",
            "detection_method": "regex|keyword|none"
        }
    """
    text = f"{rules_primary} {title}".lower()
    
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
