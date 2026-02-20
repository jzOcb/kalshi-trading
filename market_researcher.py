#!/usr/bin/env python3
"""
Market Researcher - 基于事实的预测市场分析框架

核心原则: 这是预测市场，不是赌场。
100% 的判断必须通过研究得出，不能靠数学公式猜测。

流程:
1. 思考: 这个问题需要什么数据来验证?
2. 研究: 获取相关数据和历史案例
3. 判断: 基于事实得出方向和置信度
4. 收益: 最后才考虑，只影响仓位大小

Author: OpenClaw
Date: 2026-02-20
"""

import os
import sys
import json
import re
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any

# For web searches
try:
    import requests
except ImportError:
    requests = None


class MarketResearcher:
    """
    对单个市场进行深度研究，返回基于事实的判断。
    """
    
    def __init__(self, llm_client=None, search_fn=None):
        """
        Args:
            llm_client: LLM客户端 (用于推理)
            search_fn: 搜索函数 (query) -> [results]
        """
        self.llm = llm_client
        self.search = search_fn or self._default_search
        self.research_log = []
    
    # 已知数据源映射
    DATA_SOURCES = {
        "gas_price": "https://gasprices.aaa.com/",
        "gdp": "https://tradingeconomics.com/united-states/gdp-growth",
        "gdp_annual": "https://tradingeconomics.com/united-states/gdp-growth-annual",
        "cpi": "https://tradingeconomics.com/united-states/inflation-cpi",
        "fed_rate": "https://tradingeconomics.com/united-states/interest-rate",
        "pboc_rate": "https://tradingeconomics.com/china/interest-rate",
        "weather_nyc": "https://api.weather.gov/gridpoints/OKX/33,37/forecast",
        "weather_lax": "https://api.weather.gov/gridpoints/LOX/154,44/forecast",
        "weather_chi": "https://api.weather.gov/gridpoints/LOT/76,73/forecast",
    }
    
    def fetch_data_source(self, source_key: str) -> Optional[Dict]:
        """直接从已知数据源获取数据，返回解析后的结果"""
        url = self.DATA_SOURCES.get(source_key)
        if not url or not requests:
            return None
        
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                return None
            
            content = resp.text
            result = {"raw": content[:2000], "url": url, "values": []}
            
            # 根据数据源类型提取数值
            if source_key == "gas_price":
                # AAA 格式: $X.XXX
                prices = re.findall(r'\$(\d+\.\d{3})', content)
                if prices:
                    result["values"] = [float(p) for p in prices[:5]]
                    result["current"] = result["values"][0]
                    result["source"] = "AAA"
            
            elif source_key in ["gdp", "gdp_annual"]:
                # Trading Economics: "expanded X.XX percent"
                matches = re.findall(r'expanded?\s+(\d+\.?\d*)\s*percent', content.lower())
                if matches:
                    result["values"] = [float(m) for m in matches[:3]]
                    result["current"] = result["values"][0]
                    result["source"] = "Trading Economics"
            
            elif source_key == "cpi":
                # Trading Economics inflation
                matches = re.findall(r'inflation.*?(\d+\.?\d*)\s*percent', content.lower())
                if matches:
                    result["values"] = [float(m) for m in matches[:3]]
                    result["current"] = result["values"][0]
                    result["source"] = "Trading Economics"
            
            elif source_key in ["fed_rate", "pboc_rate"]:
                # Interest rates
                matches = re.findall(r'(\d+\.?\d*)\s*percent', content.lower())
                if matches:
                    result["values"] = [float(m) for m in matches[:3]]
                    result["current"] = result["values"][0]
                    result["source"] = "Trading Economics"
            
            return result
            
        except Exception as e:
            self.research_log.append(f"Fetch error ({source_key}): {e}")
        return None
    
    def _default_search(self, query: str, max_results: int = 5) -> List[Dict]:
        """
        搜索实现 - 优先使用直接数据源，不依赖搜索 API
        根据 query 关键词匹配数据源
        """
        results = []
        query_lower = query.lower()
        
        # 根据关键词匹配数据源
        source_map = {
            "gas": "gas_price",
            "gasoline": "gas_price",
            "fuel": "gas_price",
            "gdp": "gdp",
            "economic growth": "gdp",
            "cpi": "cpi",
            "inflation": "cpi",
            "fed": "fed_rate",
            "federal reserve": "fed_rate",
            "interest rate": "fed_rate",
            "pboc": "pboc_rate",
            "china rate": "pboc_rate",
        }
        
        for keyword, source_key in source_map.items():
            if keyword in query_lower:
                data = self.fetch_data_source(source_key)
                if data and data.get("current"):
                    results.append({
                        "title": f"Data from {data.get('source', source_key)}",
                        "url": data.get("url", ""),
                        "snippet": f"Current value: {data['current']}",
                        "current_value": data["current"],
                        "all_values": data.get("values", []),
                        "source_key": source_key,
                    })
                    self.research_log.append(f"Fetched {source_key}: current={data['current']}")
                break
        
        return results
    
    def _log(self, msg: str):
        """记录研究过程"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.research_log.append(f"[{timestamp}] {msg}")
    
    def analyze_question(self, title: str, rules: str) -> Dict:
        """
        Step 1: 分析市场问题，确定需要什么数据
        
        Returns:
            {
                "question_type": "economic|political|weather|event|other",
                "core_question": "简化的核心问题",
                "data_needed": ["需要的数据类型"],
                "search_queries": ["建议的搜索词"],
                "verification_method": "如何验证结果",
                "historical_relevance": "历史上类似情况",
            }
        """
        self._log(f"分析问题: {title[:50]}...")
        
        # 识别问题类型
        title_lower = title.lower()
        rules_lower = rules.lower() if rules else ""
        combined = f"{title_lower} {rules_lower}"
        
        analysis = {
            "question_type": "other",
            "core_question": title,
            "data_needed": [],
            "search_queries": [],
            "verification_method": "manual",
            "key_threshold": None,
        }
        
        # 经济数据类
        if any(kw in combined for kw in ["gdp", "economic growth", "economy"]):
            analysis["question_type"] = "economic_gdp"
            analysis["data_needed"] = ["GDPNow forecast", "BEA official data", "economist consensus"]
            analysis["search_queries"] = [
                "Atlanta Fed GDPNow latest forecast",
                "US GDP Q4 2025 forecast",
                "BEA GDP release schedule"
            ]
            analysis["verification_method"] = "Compare forecast to threshold"
            # 提取阈值
            match = re.search(r"(\d+\.?\d*)%", title)
            if match:
                analysis["key_threshold"] = float(match.group(1))
        
        elif any(kw in combined for kw in ["cpi", "inflation", "price index"]):
            analysis["question_type"] = "economic_cpi"
            analysis["data_needed"] = ["Cleveland Fed Nowcast", "BLS data", "inflation expectations"]
            analysis["search_queries"] = [
                "Cleveland Fed inflation nowcast",
                "US CPI forecast February 2026",
                "BLS CPI release"
            ]
            analysis["verification_method"] = "Compare nowcast to threshold"
            match = re.search(r"(\d+\.?\d*)%", title)
            if match:
                analysis["key_threshold"] = float(match.group(1))
        
        elif any(kw in combined for kw in ["fed", "interest rate", "fomc", "federal funds"]):
            analysis["question_type"] = "central_bank"
            analysis["data_needed"] = ["Fed dot plot", "CME FedWatch", "FOMC statement"]
            analysis["search_queries"] = [
                "CME FedWatch tool probability",
                "Fed interest rate decision forecast",
                "FOMC meeting expectations"
            ]
            analysis["verification_method"] = "Check market-implied probabilities"
        
        elif any(kw in combined for kw in ["pboc", "china rate", "lpr"]):
            analysis["question_type"] = "central_bank"
            analysis["data_needed"] = ["PBOC announcement", "LPR decision"]
            analysis["search_queries"] = [
                "PBOC LPR decision February 2026",
                "China interest rate announcement",
                "PBOC monetary policy"
            ]
            analysis["verification_method"] = "Check if already announced"
        
        elif any(kw in combined for kw in ["temperature", "weather", "rain", "snow", "high", "low"]):
            analysis["question_type"] = "weather"
            analysis["data_needed"] = ["NWS forecast", "historical averages", "current conditions"]
            # 提取城市
            cities = ["nyc", "chicago", "boston", "la", "lax", "miami", "phoenix", "seattle", "denver"]
            for city in cities:
                if city in combined:
                    analysis["search_queries"].append(f"NWS {city} weather forecast")
                    analysis["search_queries"].append(f"{city} temperature forecast week")
                    break
            else:
                analysis["search_queries"] = ["NWS weather forecast"]
            analysis["verification_method"] = "Compare forecast to bracket"
        
        elif any(kw in combined for kw in ["trump", "president", "white house"]):
            if "say" in combined or "mention" in combined:
                analysis["question_type"] = "speech_event"
                analysis["data_needed"] = ["Recent transcripts", "scheduled speeches", "historical frequency"]
                # 提取关键词
                speech_keywords = ["crypto", "bitcoin", "marijuana", "golden dome", "tariff"]
                for kw in speech_keywords:
                    if kw in combined:
                        analysis["search_queries"] = [
                            f"Trump {kw} speech transcript 2026",
                            f"Trump mention {kw} recent",
                            f"White House transcript {kw}"
                        ]
                        break
                analysis["verification_method"] = "Search transcripts for keyword"
            else:
                analysis["question_type"] = "political"
                analysis["data_needed"] = ["News", "official announcements", "expert analysis"]
                analysis["search_queries"] = [f"Trump {title[:30]} news"]
        
        elif any(kw in combined for kw in ["gas price", "gasoline", "fuel"]):
            analysis["question_type"] = "commodity_price"
            analysis["data_needed"] = ["AAA gas prices", "EIA data", "price trends"]
            analysis["search_queries"] = [
                "AAA national average gas price today",
                "US gasoline price forecast",
                "EIA gas price data"
            ]
            analysis["verification_method"] = "Compare current price to threshold"
            match = re.search(r"\$(\d+\.?\d*)", title)
            if match:
                analysis["key_threshold"] = float(match.group(1))
        
        elif any(kw in combined for kw in ["shutdown", "government"]):
            analysis["question_type"] = "political"
            analysis["data_needed"] = ["Congress status", "budget negotiations", "deadline info"]
            analysis["search_queries"] = [
                "government shutdown news",
                "congress budget deadline",
                "federal funding status"
            ]
            analysis["verification_method"] = "Check current legislative status"
        
        else:
            # 通用处理
            analysis["data_needed"] = ["News articles", "expert analysis", "historical data"]
            # 从标题提取关键词作为搜索词
            words = re.findall(r'\b[A-Za-z]{4,}\b', title)
            if words:
                analysis["search_queries"] = [" ".join(words[:3]) + " prediction"]
        
        self._log(f"问题类型: {analysis['question_type']}")
        self._log(f"需要数据: {analysis['data_needed']}")
        
        return analysis
    
    def gather_data(self, analysis: Dict) -> Dict:
        """
        Step 2: 根据分析结果，收集相关数据
        
        Returns:
            {
                "search_results": [搜索结果],
                "key_facts": [提取的关键事实],
                "data_quality": "high|medium|low",
                "sources_count": int,
            }
        """
        self._log("开始收集数据...")
        
        all_results = []
        for query in analysis.get("search_queries", [])[:3]:  # 最多3个搜索
            self._log(f"搜索: {query}")
            results = self.search(query, max_results=3)
            all_results.extend(results)
        
        # 去重
        seen_urls = set()
        unique_results = []
        for r in all_results:
            url = r.get("url", "")
            if url not in seen_urls:
                seen_urls.add(url)
                unique_results.append(r)
        
        # 评估数据质量
        quality = "low"
        if len(unique_results) >= 5:
            quality = "high"
        elif len(unique_results) >= 2:
            quality = "medium"
        
        self._log(f"收集到 {len(unique_results)} 条结果，质量: {quality}")
        
        return {
            "search_results": unique_results,
            "key_facts": [],  # 会在 make_judgment 中提取
            "data_quality": quality,
            "sources_count": len(unique_results),
        }
    
    def make_judgment(self, market: Dict, analysis: Dict, data: Dict) -> Dict:
        """
        Step 3: 基于收集的数据，做出事实判断
        
        Returns:
            {
                "direction": "YES|NO|UNCERTAIN",
                "confidence": 0-100,
                "reasoning": "判断理由",
                "key_facts": ["支持判断的关键事实"],
                "risks": ["风险因素"],
                "recommendation": "BUY|WAIT|SKIP",
                "position_size": "full|half|quarter|none",
            }
        """
        self._log("开始分析判断...")
        
        title = market.get("title", "")
        price = market.get("last_price", 50)
        threshold = analysis.get("key_threshold")
        q_type = analysis.get("question_type", "other")
        results = data.get("search_results", [])
        
        judgment = {
            "direction": "UNCERTAIN",
            "confidence": 0,
            "reasoning": "",
            "key_facts": [],
            "risks": [],
            "recommendation": "SKIP",
            "position_size": "none",
        }
        
        # 从搜索结果提取关键信息
        snippets = " ".join([r.get("snippet", "") for r in results[:5]])
        
        # 根据问题类型做判断
        if q_type == "economic_gdp" and threshold:
            # 直接从结果中获取 GDP 数据
            current_gdp = None
            for r in results:
                if r.get("current_value"):
                    current_gdp = r["current_value"]
                    break
            
            if current_gdp is not None:
                judgment["key_facts"].append(f"最新GDP: {current_gdp}% (Q4 2025)")
                
                gap = current_gdp - threshold
                if gap > 1.5:
                    judgment["direction"] = "YES"
                    judgment["confidence"] = 85
                    judgment["reasoning"] = f"GDP {current_gdp}% 远高于阈值 {threshold}%"
                elif gap > 0.5:
                    judgment["direction"] = "YES"
                    judgment["confidence"] = 65
                    judgment["reasoning"] = f"GDP {current_gdp}% 高于阈值 {threshold}%"
                    judgment["risks"].append("未来季度可能变化")
                elif gap > -0.5:
                    judgment["direction"] = "UNCERTAIN"
                    judgment["confidence"] = 30
                    judgment["reasoning"] = f"GDP {current_gdp}% 与阈值 {threshold}% 接近"
                    judgment["risks"].append("边界风险")
                elif gap > -1.5:
                    judgment["direction"] = "NO"
                    judgment["confidence"] = 65
                    judgment["reasoning"] = f"GDP {current_gdp}% 低于阈值 {threshold}%"
                else:
                    judgment["direction"] = "NO"
                    judgment["confidence"] = 85
                    judgment["reasoning"] = f"GDP {current_gdp}% 远低于阈值 {threshold}%"
        
        elif q_type == "commodity_price" and threshold:
            # 直接从结果中获取当前价格
            current_price = None
            for r in results:
                if r.get("current_value"):
                    current_price = r["current_value"]
                    break
            
            if current_price:
                judgment["key_facts"].append(f"AAA当前价格: ${current_price:.3f}")
                
                gap = threshold - current_price
                gap_pct = (gap / current_price) * 100
                
                if gap_pct > 3:
                    judgment["direction"] = "NO"  # 需要涨3%+才能触及阈值
                    judgment["confidence"] = 80
                    judgment["reasoning"] = f"当前 ${current_price:.3f}，需涨 {gap_pct:.1f}% 才到 ${threshold}"
                elif gap_pct > 1:
                    judgment["direction"] = "UNCERTAIN"
                    judgment["confidence"] = 40
                    judgment["reasoning"] = f"当前 ${current_price:.3f}，距阈值只差 {gap_pct:.1f}%"
                    judgment["risks"].append("1-3% 波动在正常范围内")
                elif gap_pct > -1:
                    judgment["direction"] = "UNCERTAIN"
                    judgment["confidence"] = 25
                    judgment["reasoning"] = f"价格 ${current_price:.3f} 与阈值 ${threshold} 相差 <1%，边界风险"
                    judgment["risks"].append("太接近边界，无法预测")
                elif gap_pct > -3:
                    judgment["direction"] = "YES"
                    judgment["confidence"] = 60
                    judgment["reasoning"] = f"当前 ${current_price:.3f} 已超过阈值 ${threshold}"
                    judgment["risks"].append("价格下跌可能翻转结果")
                else:
                    judgment["direction"] = "YES"
                    judgment["confidence"] = 85
                    judgment["reasoning"] = f"当前 ${current_price:.3f} 远超阈值 ${threshold}"
        
        elif q_type == "speech_event":
            # 检查是否已经提到
            keywords = ["mention", "said", "spoke", "discuss", "talk"]
            found_mention = any(kw in snippets.lower() for kw in keywords)
            
            if "already" in snippets.lower() or "yesterday" in snippets.lower():
                judgment["direction"] = "YES"
                judgment["confidence"] = 80
                judgment["reasoning"] = "搜索结果显示可能已经提到过"
                judgment["key_facts"].append("可能已有相关发言")
            elif found_mention:
                judgment["direction"] = "UNCERTAIN"
                judgment["confidence"] = 40
                judgment["reasoning"] = "有相关讨论但不确定是否正式提到"
            else:
                judgment["direction"] = "UNCERTAIN"
                judgment["confidence"] = 30
                judgment["reasoning"] = "无法确定是否会提到，需要更多信息"
                judgment["risks"].append("speech event 难以预测")
        
        elif q_type == "central_bank":
            # 检查是否已公布
            if "maintain" in snippets.lower() or "unchanged" in snippets.lower() or "hold" in snippets.lower():
                judgment["direction"] = "YES"
                judgment["confidence"] = 75
                judgment["reasoning"] = "搜索显示倾向维持现状"
                judgment["key_facts"].append("市场预期维持利率不变")
            elif "cut" in snippets.lower() or "hike" in snippets.lower() or "raise" in snippets.lower():
                judgment["direction"] = "NO"
                judgment["confidence"] = 60
                judgment["reasoning"] = "搜索显示可能有变动"
            else:
                judgment["direction"] = "UNCERTAIN"
                judgment["confidence"] = 40
        
        # 数据质量影响置信度
        if data["data_quality"] == "low":
            judgment["confidence"] = min(judgment["confidence"], 50)
            judgment["risks"].append("数据来源不足，判断可能不准确")
        
        # 最终推荐
        if judgment["confidence"] >= 70 and judgment["direction"] != "UNCERTAIN":
            judgment["recommendation"] = "BUY"
            judgment["position_size"] = "half" if judgment["confidence"] >= 80 else "quarter"
        elif judgment["confidence"] >= 50 and judgment["direction"] != "UNCERTAIN":
            judgment["recommendation"] = "WAIT"
            judgment["position_size"] = "quarter"
        else:
            judgment["recommendation"] = "SKIP"
            judgment["position_size"] = "none"
        
        self._log(f"判断: {judgment['direction']} (置信度 {judgment['confidence']}%)")
        self._log(f"推荐: {judgment['recommendation']}")
        
        return judgment
    
    def research(self, market: Dict) -> Dict:
        """
        完整研究流程
        
        Args:
            market: {
                "ticker": str,
                "title": str,
                "rules_primary": str,
                "last_price": int (0-100),
                "yes_bid": int,
                "yes_ask": int,
                "close_time": str,
                ...
            }
        
        Returns:
            {
                "market": 原始市场数据,
                "analysis": 问题分析,
                "data": 收集的数据,
                "judgment": 事实判断,
                "research_log": 研究过程日志,
            }
        """
        self.research_log = []
        self._log(f"=== 开始研究: {market.get('ticker', 'Unknown')} ===")
        
        title = market.get("title", "")
        rules = market.get("rules_primary", "") + " " + market.get("rules_secondary", "")
        
        # Step 1: 分析问题
        analysis = self.analyze_question(title, rules)
        
        # Step 2: 收集数据
        data = self.gather_data(analysis)
        
        # Step 3: 做出判断
        judgment = self.make_judgment(market, analysis, data)
        
        # 综合报告
        report = {
            "market": market,
            "analysis": analysis,
            "data": data,
            "judgment": judgment,
            "research_log": self.research_log,
        }
        
        self._log("=== 研究完成 ===")
        
        return report
    
    def format_report(self, report: Dict) -> str:
        """格式化研究报告为可读文本"""
        market = report["market"]
        analysis = report["analysis"]
        judgment = report["judgment"]
        
        lines = []
        lines.append(f"📊 研究报告: {market.get('ticker', 'Unknown')}")
        lines.append(f"问题: {market.get('title', '')[:60]}...")
        lines.append(f"当前价格: {market.get('last_price', '?')}¢")
        lines.append("")
        lines.append(f"🔍 问题类型: {analysis.get('question_type', 'unknown')}")
        lines.append(f"📚 数据来源: {report['data'].get('sources_count', 0)} 个")
        lines.append("")
        lines.append(f"📈 判断: {judgment['direction']}")
        lines.append(f"🎯 置信度: {judgment['confidence']}%")
        lines.append(f"💡 理由: {judgment['reasoning']}")
        
        if judgment.get("key_facts"):
            lines.append(f"📋 关键事实: {', '.join(judgment['key_facts'][:3])}")
        
        if judgment.get("risks"):
            lines.append(f"⚠️ 风险: {', '.join(judgment['risks'][:3])}")
        
        lines.append("")
        lines.append(f"✅ 推荐: {judgment['recommendation']}")
        lines.append(f"📦 仓位: {judgment['position_size']}")
        
        return "\n".join(lines)


def main():
    """测试研究框架"""
    researcher = MarketResearcher()
    
    # 测试案例
    test_markets = [
        {
            "ticker": "KXGDP-26JAN30-T2.0",
            "title": "Will real GDP increase by more than 2.0%?",
            "last_price": 88,
            "rules_primary": "Based on BEA GDP data",
        },
        {
            "ticker": "KXTRUMPSAY-CRYPTO",
            "title": "Will Trump say Crypto before Feb 23?",
            "last_price": 10,
            "rules_primary": "Based on official transcripts",
        },
        {
            "ticker": "KXGASW-2.959",
            "title": "Will gas prices be above $2.959?",
            "last_price": 90,
            "rules_primary": "Based on AAA national average",
        },
    ]
    
    for market in test_markets:
        print("\n" + "="*60)
        report = researcher.research(market)
        print(researcher.format_report(report))


if __name__ == "__main__":
    main()
