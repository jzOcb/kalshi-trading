#!/usr/bin/env python3
"""
LLM-based Data Source Identifier

用 LLM 分析市场问题，识别需要查询的数据源。
比硬编码规则更灵活，能处理各种类型的市场。

Author: OpenClaw
Date: 2026-02-20
"""

import os
import json
import re
from typing import List, Dict, Optional

# 尝试导入 LLM 客户端
try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

try:
    import google.generativeai as genai
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False


SYSTEM_PROMPT = """你是一个预测市场研究助手。

给定一个市场的标题和结算规则，你需要：
1. 识别这个市场结算时会用到的官方数据源
2. 识别可以帮助预测结果的辅助数据源
3. 判断这个市场是否可以在结算前验证

对于每个数据源，提供：
- name: 数据源名称
- type: official (官方结算源) 或 auxiliary (辅助参考)
- url: 数据源 URL（如果知道）
- data_to_fetch: 需要获取什么具体数据
- verifiable_before_settlement: 是否可以在结算前验证（true/false）

重要：
- "Trump/Biden 将说什么" 类市场 → verifiable_before_settlement: false
- 历史数据/已发布数据 → verifiable_before_settlement: true
- 未来事件 → 取决于是否有预测指标

输出格式（JSON）：
{
  "market_type": "economic|political|weather|crypto|other",
  "verifiable": true/false,
  "reason": "简短解释",
  "sources": [
    {
      "name": "...",
      "type": "official|auxiliary",
      "url": "...",
      "data_to_fetch": "...",
      "verifiable_before_settlement": true/false
    }
  ],
  "recommended_action": "research|skip|wait"
}
"""


class LLMSourceIdentifier:
    """用 LLM 识别市场所需的数据源"""
    
    def __init__(self, provider="gemini"):
        """
        Args:
            provider: "anthropic" 或 "gemini"
        """
        self.provider = provider
        self._init_client()
    
    def _init_client(self):
        """初始化 LLM 客户端"""
        if self.provider == "anthropic" and HAS_ANTHROPIC:
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if api_key:
                self.client = anthropic.Anthropic(api_key=api_key)
            else:
                self.client = None
        elif self.provider == "gemini" and HAS_GEMINI:
            api_key = os.environ.get("GEMINI_API_KEY")
            if api_key:
                genai.configure(api_key=api_key)
                self.client = genai.GenerativeModel('gemini-1.5-flash')
            else:
                self.client = None
        else:
            self.client = None
    
    def identify_sources(self, market: Dict) -> Dict:
        """
        使用 LLM 识别市场所需的数据源
        
        Args:
            market: 市场信息 dict，包含 title, rules_primary, rules_secondary
            
        Returns:
            {
                "market_type": "...",
                "verifiable": bool,
                "sources": [...],
                "recommended_action": "research|skip|wait"
            }
        """
        if not self.client:
            return self._fallback_identify(market)
        
        title = market.get('title', '')
        rules = market.get('rules_primary', '') + '\n' + market.get('rules_secondary', '')
        
        prompt = f"""分析这个预测市场：

标题: {title}

结算规则:
{rules}

识别所需的数据源并输出 JSON。"""

        try:
            if self.provider == "anthropic":
                response = self.client.messages.create(
                    model="claude-3-haiku-20240307",
                    max_tokens=1000,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": prompt}]
                )
                text = response.content[0].text
            else:  # gemini
                response = self.client.generate_content(
                    f"{SYSTEM_PROMPT}\n\n{prompt}",
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.2,
                        max_output_tokens=1000,
                    )
                )
                text = response.text
            
            # 提取 JSON
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                result = json.loads(json_match.group())
                return result
            else:
                return self._fallback_identify(market)
                
        except Exception as e:
            print(f"LLM error: {e}")
            return self._fallback_identify(market)
    
    def _fallback_identify(self, market: Dict) -> Dict:
        """LLM 不可用时的回退逻辑"""
        title = market.get('title', '').lower()
        rules = (market.get('rules_primary', '') + ' ' + market.get('rules_secondary', '')).lower()
        
        sources = []
        market_type = "other"
        verifiable = True
        
        # 经济指标
        if any(k in title or k in rules for k in ['gdp', 'economic growth']):
            market_type = "economic"
            sources.append({
                "name": "BEA",
                "type": "official",
                "url": "https://www.bea.gov/data/gdp",
                "data_to_fetch": "GDP growth rate",
                "verifiable_before_settlement": True
            })
            sources.append({
                "name": "Atlanta Fed GDPNow",
                "type": "auxiliary",
                "url": "https://www.atlantafed.org/cqer/research/gdpnow",
                "data_to_fetch": "Real-time GDP forecast",
                "verifiable_before_settlement": True
            })
        
        elif any(k in title or k in rules for k in ['unemployment', 'jobless', 'u-3']):
            market_type = "economic"
            sources.append({
                "name": "BLS",
                "type": "official",
                "url": "https://www.bls.gov/news.release/empsit.nr0.htm",
                "data_to_fetch": "U-3 unemployment rate",
                "verifiable_before_settlement": True
            })
        
        elif any(k in title or k in rules for k in ['cpi', 'inflation', 'consumer price']):
            market_type = "economic"
            sources.append({
                "name": "BLS CPI",
                "type": "official",
                "url": "https://www.bls.gov/cpi/",
                "data_to_fetch": "CPI inflation rate",
                "verifiable_before_settlement": True
            })
        
        elif any(k in title or k in rules for k in ['gas price', 'gasoline', 'aaa']):
            market_type = "economic"
            sources.append({
                "name": "AAA",
                "type": "official",
                "url": "https://gasprices.aaa.com/",
                "data_to_fetch": "National average gas price",
                "verifiable_before_settlement": True
            })
        
        elif any(k in title or k in rules for k in ['fed', 'fomc', 'rate cut', 'interest rate']):
            market_type = "economic"
            sources.append({
                "name": "Federal Reserve",
                "type": "official",
                "url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
                "data_to_fetch": "Fed funds rate decision",
                "verifiable_before_settlement": True
            })
            sources.append({
                "name": "CME FedWatch",
                "type": "auxiliary",
                "url": "https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html",
                "data_to_fetch": "Rate cut probability",
                "verifiable_before_settlement": True
            })
        
        # 政治/发言类
        elif any(k in title for k in ['trump', 'biden', 'president']) and any(k in title for k in ['say', 'mention', 'tweet', 'speech']):
            market_type = "political"
            verifiable = False
            sources.append({
                "name": "White House",
                "type": "official",
                "url": "https://www.whitehouse.gov/briefing-room/",
                "data_to_fetch": "Presidential remarks",
                "verifiable_before_settlement": False
            })
        
        # 天气
        elif any(k in title or k in rules for k in ['temperature', 'weather', 'high of', 'low of']):
            market_type = "weather"
            sources.append({
                "name": "NWS",
                "type": "official",
                "url": "https://api.weather.gov/",
                "data_to_fetch": "Temperature forecast/observation",
                "verifiable_before_settlement": True
            })
        
        # 加密货币
        elif any(k in title or k in rules for k in ['bitcoin', 'btc', 'ethereum', 'crypto']):
            market_type = "crypto"
            sources.append({
                "name": "CoinMarketCap",
                "type": "official",
                "url": "https://coinmarketcap.com/",
                "data_to_fetch": "Crypto price",
                "verifiable_before_settlement": True
            })
        
        # IPO/公司事件
        elif any(k in title for k in ['ipo', 'announce', 'acquisition']):
            market_type = "corporate"
            sources.append({
                "name": "SEC EDGAR",
                "type": "official",
                "url": "https://www.sec.gov/cgi-bin/browse-edgar",
                "data_to_fetch": "IPO filings",
                "verifiable_before_settlement": True
            })
            sources.append({
                "name": "Company news",
                "type": "auxiliary",
                "url": None,
                "data_to_fetch": "Official announcements",
                "verifiable_before_settlement": False
            })
        
        recommended = "research" if verifiable and sources else "skip"
        if not verifiable:
            recommended = "skip"
        
        return {
            "market_type": market_type,
            "verifiable": verifiable,
            "reason": "Fallback rule-based identification",
            "sources": sources,
            "recommended_action": recommended
        }


def test():
    """测试 LLM 数据源识别"""
    identifier = LLMSourceIdentifier(provider="gemini")
    
    test_markets = [
        {
            "title": "Will unemployment go above 5% by December 2026?",
            "rules_primary": "Resolves Yes if U-3 unemployment rate exceeds 5%."
        },
        {
            "title": "Will Trump say 'tariff' in his next speech?",
            "rules_primary": "Resolves Yes if Trump says the word tariff."
        },
        {
            "title": "Will gas prices exceed $4.00 by summer?",
            "rules_primary": "Based on AAA national average gas price."
        },
        {
            "title": "Will OpenAI announce IPO before April 2026?",
            "rules_primary": "Resolves Yes if OpenAI officially announces IPO."
        }
    ]
    
    for market in test_markets:
        print(f"\n=== {market['title'][:50]}... ===")
        result = identifier.identify_sources(market)
        print(f"Type: {result['market_type']}")
        print(f"Verifiable: {result['verifiable']}")
        print(f"Action: {result['recommended_action']}")
        print("Sources:")
        for s in result.get('sources', []):
            print(f"  - {s['name']} ({s['type']}): {s['data_to_fetch']}")


if __name__ == "__main__":
    test()
