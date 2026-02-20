#!/usr/bin/env python3
"""
Market Researcher V2 - 基于 Kalshi 官方结算源的事实核查框架

核心改进:
1. 从市场规则提取官方结算数据源
2. LLM 动态识别需要查询的额外数据源
3. 优先使用官方源，次要使用辅助源

Author: OpenClaw
Date: 2026-02-20
"""

import os
import sys
import json
import re
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any, Tuple

try:
    import requests
except ImportError:
    requests = None

# 导入 LLM 数据源识别器
try:
    from llm_source_identifier import LLMSourceIdentifier
    HAS_LLM_IDENTIFIER = True
except ImportError:
    HAS_LLM_IDENTIFIER = False


class MarketResearcherV2:
    """
    V2: 官方结算源优先 + LLM 动态数据源识别
    """
    
    # 已知的官方数据源 URL 映射
    OFFICIAL_SOURCES = {
        # 经济指标
        "bea": "https://www.bea.gov/data/gdp/gross-domestic-product",
        "bls": "https://www.bls.gov/",
        "u-3": "https://www.bls.gov/news.release/empsit.nr0.htm",
        "cpi": "https://www.bls.gov/cpi/",
        "pce": "https://www.bea.gov/data/personal-consumption-expenditures-price-index",
        
        # 油价
        "aaa": "https://gasprices.aaa.com/",
        "eia": "https://www.eia.gov/petroleum/gasdiesel/",
        
        # 天气
        "nws": "https://api.weather.gov/",
        "noaa": "https://www.weather.gov/",
        
        # 利率
        "fed": "https://www.federalreserve.gov/monetarypolicy/openmarket.htm",
        "fomc": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
        "pboc": "http://www.pbc.gov.cn/",
        
        # 加密货币
        "coinmarketcap": "https://coinmarketcap.com/",
        "coingecko": "https://www.coingecko.com/",
        
        # 新闻/演讲
        "whitehouse": "https://www.whitehouse.gov/briefing-room/",
        "c-span": "https://www.c-span.org/",
    }
    
    # 第三方数据源 (用于交叉验证)
    THIRD_PARTY_SOURCES = {
        "gdp": "https://tradingeconomics.com/united-states/gdp-growth",
        "cpi_te": "https://tradingeconomics.com/united-states/inflation-cpi", 
        "unemployment": "https://tradingeconomics.com/united-states/unemployment-rate",
        "fed_rate": "https://tradingeconomics.com/united-states/interest-rate",
        "gas_te": "https://tradingeconomics.com/commodity/gasoline",
    }
    
    def __init__(self, use_llm=True):
        self.research_log = []
        self.use_llm = use_llm and HAS_LLM_IDENTIFIER
        if self.use_llm:
            self.llm_identifier = LLMSourceIdentifier(provider="gemini")
        else:
            self.llm_identifier = None
        
    def log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.research_log.append(f"[{ts}] {msg}")
    
    def extract_official_sources(self, market: Dict) -> List[Dict]:
        """
        从市场规则中提取官方结算数据源
        
        Returns:
            [{"source": "BLS", "url": "...", "data_type": "unemployment"}, ...]
        """
        rules = market.get('rules_primary', '') + ' ' + market.get('rules_secondary', '')
        rules_lower = rules.lower()
        
        sources = []
        
        # 模式匹配官方数据源
        patterns = [
            (r'u-3\s*unemployment', 'BLS', 'u-3', 'unemployment'),
            (r'bls|bureau of labor', 'BLS', 'bls', 'labor'),
            (r'bea|bureau of economic', 'BEA', 'bea', 'gdp'),
            (r'gdp|gross domestic', 'BEA', 'bea', 'gdp'),
            (r'cpi|consumer price', 'BLS', 'cpi', 'inflation'),
            (r'pce|personal consumption', 'BEA', 'pce', 'inflation'),
            (r'aaa.*gas|gas.*aaa', 'AAA', 'aaa', 'gas_price'),
            (r'eia.*gas|gas.*eia', 'EIA', 'eia', 'gas_price'),
            (r'nws|national weather|weather\.gov', 'NWS', 'nws', 'weather'),
            (r'federal reserve|fomc|fed fund', 'Fed', 'fed', 'interest_rate'),
            (r'pboc|people.s bank', 'PBOC', 'pboc', 'interest_rate'),
        ]
        
        for pattern, name, key, data_type in patterns:
            if re.search(pattern, rules_lower):
                url = self.OFFICIAL_SOURCES.get(key, '')
                sources.append({
                    "source": name,
                    "url": url,
                    "data_type": data_type,
                    "is_official": True,
                })
        
        self.log(f"从规则提取到 {len(sources)} 个官方数据源: {[s['source'] for s in sources]}")
        return sources
    
    def identify_additional_sources(self, market: Dict, official_sources: List[Dict]) -> List[Dict]:
        """
        LLM 动态识别需要查询的额外数据源
        
        优先使用 LLM，回退到规则
        """
        # 尝试使用 LLM
        if self.use_llm and self.llm_identifier:
            try:
                llm_result = self.llm_identifier.identify_sources(market)
                additional = []
                
                # 转换 LLM 输出格式
                for s in llm_result.get('sources', []):
                    # 跳过已经在 official_sources 中的
                    if any(s['name'].lower() in os.get('source', '').lower() for os in official_sources):
                        continue
                    
                    source = {
                        "source": s['name'],
                        "url": s.get('url'),
                        "data_type": s.get('data_to_fetch', ''),
                        "is_official": s.get('type') == 'official',
                        "purpose": s.get('data_to_fetch', ''),
                    }
                    
                    if not s.get('verifiable_before_settlement', True):
                        source["warning"] = True
                    
                    additional.append(source)
                
                # 如果 LLM 说不可验证，添加警告
                if not llm_result.get('verifiable', True):
                    additional.append({
                        "source": "⚠️ LLM判断不可核查",
                        "url": None,
                        "data_type": "unverifiable",
                        "is_official": False,
                        "purpose": llm_result.get('reason', '无法提前验证'),
                        "warning": True,
                    })
                
                self.log(f"LLM识别到 {len(additional)} 个额外数据源")
                return additional
                
            except Exception as e:
                self.log(f"LLM识别失败: {e}，使用规则回退")
        
        # 规则回退
        title = market.get('title', '').lower()
        additional = []
        
        # 基于问题类型识别额外数据源
        if any(k in title for k in ['gdp', 'economic growth']):
            # GDP 需要 GDPNow 预测 + 历史数据
            additional.append({
                "source": "Atlanta Fed GDPNow",
                "url": "https://www.atlantafed.org/cqer/research/gdpnow",
                "data_type": "gdp_forecast",
                "is_official": False,
                "purpose": "实时预测参考 (注意误差风险)",
            })
            additional.append({
                "source": "Trading Economics",
                "url": self.THIRD_PARTY_SOURCES.get('gdp'),
                "data_type": "gdp_history",
                "is_official": False,
                "purpose": "历史数据 + 预测",
            })
        
        elif any(k in title for k in ['unemployment', 'jobless']):
            additional.append({
                "source": "Trading Economics",
                "url": self.THIRD_PARTY_SOURCES.get('unemployment'),
                "data_type": "unemployment",
                "is_official": False,
                "purpose": "历史趋势 + 预测",
            })
        
        elif any(k in title for k in ['gas price', 'gasoline']):
            additional.append({
                "source": "Trading Economics",
                "url": self.THIRD_PARTY_SOURCES.get('gas_te'),
                "data_type": "gas_commodity",
                "is_official": False,
                "purpose": "期货价格趋势",
            })
        
        elif any(k in title for k in ['trump', 'biden', 'president']) and any(k in title for k in ['say', 'mention', 'tweet']):
            additional.append({
                "source": "White House",
                "url": self.OFFICIAL_SOURCES.get('whitehouse'),
                "data_type": "speeches",
                "is_official": True,
                "purpose": "官方讲话记录",
            })
            additional.append({
                "source": "⚠️ 无法提前核查",
                "url": None,
                "data_type": "future_speech",
                "is_official": False,
                "purpose": "未来发言无法预测",
                "warning": True,
            })
        
        self.log(f"识别到 {len(additional)} 个额外数据源")
        return additional
    
    def fetch_source(self, source: Dict) -> Optional[Dict]:
        """
        获取单个数据源的数据
        """
        url = source.get('url')
        if not url or not requests:
            return None
        
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                self.log(f"获取失败 {source['source']}: HTTP {resp.status_code}")
                return None
            
            content = resp.text
            result = {
                "source": source['source'],
                "url": url,
                "data_type": source.get('data_type'),
                "is_official": source.get('is_official', False),
                "raw_length": len(content),
                "content": content[:3000],
            }
            
            # 尝试提取数值
            result["extracted"] = self._extract_values(content, source.get('data_type'))
            
            self.log(f"获取成功 {source['source']}: {len(content)} chars, extracted={result['extracted']}")
            return result
            
        except Exception as e:
            self.log(f"获取错误 {source['source']}: {e}")
            return None
    
    def _extract_values(self, content: str, data_type: str) -> Dict:
        """
        从内容中提取数值
        """
        result = {}
        
        if data_type == "gas_price":
            # AAA 格式
            prices = re.findall(r'\$(\d+\.\d{3})', content)
            if prices:
                result["current"] = float(prices[0])
                result["values"] = [float(p) for p in prices[:5]]
        
        elif data_type in ["gdp", "gdp_history"]:
            # Trading Economics 格式
            match = re.search(r'expanded?\s+(\d+\.?\d*)\s*percent', content.lower())
            if match:
                result["current"] = float(match.group(1))
        
        elif data_type == "unemployment":
            # BLS 格式
            match = re.search(r'unemployment rate.*?(\d+\.?\d*)\s*percent', content.lower())
            if match:
                result["current"] = float(match.group(1))
        
        elif data_type == "inflation":
            match = re.search(r'inflation.*?(\d+\.?\d*)\s*percent', content.lower())
            if match:
                result["current"] = float(match.group(1))
        
        return result
    
    def research(self, market: Dict) -> Dict:
        """
        对市场进行完整研究
        
        Returns:
            {
                "market": {...},
                "official_sources": [...],
                "additional_sources": [...],
                "data": [...],
                "judgment": {...},
                "research_log": [...]
            }
        """
        self.research_log = []
        self.log(f"=== 开始研究: {market.get('ticker', '?')} ===")
        self.log(f"问题: {market.get('title', '')[:60]}...")
        
        # Step 1: 提取官方数据源
        official = self.extract_official_sources(market)
        
        # Step 2: 识别额外数据源
        additional = self.identify_additional_sources(market, official)
        
        # Step 3: 检查是否可核查
        all_sources = official + additional
        warnings = [s for s in all_sources if s.get('warning')]
        
        if warnings:
            self.log(f"⚠️ 发现不可核查项: {[w['source'] for w in warnings]}")
        
        # Step 4: 获取数据
        data = []
        for source in all_sources:
            if source.get('warning'):
                continue
            fetched = self.fetch_source(source)
            if fetched:
                data.append(fetched)
        
        # Step 5: 做出判断
        judgment = self._make_judgment(market, data, warnings)
        
        self.log(f"=== 研究完成 ===")
        
        return {
            "market": market,
            "official_sources": official,
            "additional_sources": additional,
            "data": data,
            "judgment": judgment,
            "research_log": self.research_log.copy(),
        }
    
    def _make_judgment(self, market: Dict, data: List[Dict], warnings: List[Dict]) -> Dict:
        """
        基于收集的数据做出判断
        """
        judgment = {
            "direction": "UNCERTAIN",
            "confidence": 0,
            "reasoning": "",
            "key_facts": [],
            "risks": [],
            "recommendation": "SKIP",
            "position_size": "none",
            "data_sources_used": len(data),
            "has_official_data": any(d.get('is_official') for d in data),
        }
        
        # 如果有不可核查警告，直接跳过
        if warnings:
            judgment["reasoning"] = f"存在不可核查项: {[w['source'] for w in warnings]}"
            judgment["risks"].append("无法提前验证")
            self.log("判断: SKIP (不可核查)")
            return judgment
        
        # 如果没有数据，跳过
        if not data:
            judgment["reasoning"] = "无法获取数据"
            judgment["risks"].append("数据源不可用")
            self.log("判断: SKIP (无数据)")
            return judgment
        
        # 提取阈值
        title = market.get('title', '')
        threshold = None
        
        # 尝试提取数值阈值
        thresh_match = re.search(r'(?:above|below|more than|less than|over|under)[^\d]*(\d+\.?\d*)', title.lower())
        if thresh_match:
            threshold = float(thresh_match.group(1))
            judgment["key_facts"].append(f"阈值: {threshold}")
        
        # 获取当前值
        current_value = None
        for d in data:
            if d.get('extracted', {}).get('current'):
                current_value = d['extracted']['current']
                judgment["key_facts"].append(f"当前值: {current_value} (来源: {d['source']})")
                break
        
        # 如果有阈值和当前值，进行比较
        if threshold is not None and current_value is not None:
            gap = current_value - threshold
            gap_pct = (gap / threshold) * 100 if threshold != 0 else 0
            
            # 判断逻辑
            if 'above' in title.lower() or 'more than' in title.lower() or 'over' in title.lower():
                # 问的是是否超过阈值
                if gap > 0:
                    judgment["direction"] = "YES"
                    judgment["confidence"] = min(90, 50 + abs(gap_pct) * 2)
                    judgment["reasoning"] = f"当前 {current_value} > 阈值 {threshold}"
                elif gap > -abs(threshold * 0.05):  # 5%以内
                    judgment["direction"] = "UNCERTAIN"
                    judgment["confidence"] = 30
                    judgment["reasoning"] = f"当前 {current_value} 接近阈值 {threshold}"
                    judgment["risks"].append("边界风险")
                else:
                    judgment["direction"] = "NO"
                    judgment["confidence"] = min(90, 50 + abs(gap_pct) * 2)
                    judgment["reasoning"] = f"当前 {current_value} < 阈值 {threshold}"
            else:
                # 问的是是否低于阈值 (below/less than/under)
                if gap < 0:
                    judgment["direction"] = "YES"
                    judgment["confidence"] = min(90, 50 + abs(gap_pct) * 2)
                    judgment["reasoning"] = f"当前 {current_value} < 阈值 {threshold}"
                else:
                    judgment["direction"] = "NO"
                    judgment["confidence"] = min(90, 50 + abs(gap_pct) * 2)
                    judgment["reasoning"] = f"当前 {current_value} > 阈值 {threshold}"
        else:
            judgment["reasoning"] = "无法提取阈值或当前值进行比较"
            judgment["risks"].append("需要人工分析")
        
        # 设置推荐
        if judgment["confidence"] >= 70 and judgment["has_official_data"]:
            judgment["recommendation"] = "BUY"
            judgment["position_size"] = "half" if judgment["confidence"] < 80 else "full"
        elif judgment["confidence"] >= 50:
            judgment["recommendation"] = "WAIT"
            judgment["position_size"] = "quarter"
        else:
            judgment["recommendation"] = "SKIP"
            judgment["position_size"] = "none"
        
        self.log(f"判断: {judgment['direction']} ({judgment['confidence']}%) → {judgment['recommendation']}")
        return judgment
    
    def format_report(self, report: Dict) -> str:
        """格式化研究报告"""
        m = report['market']
        j = report['judgment']
        
        lines = [
            f"📊 研究报告: {m.get('ticker', '?')}",
            f"问题: {m.get('title', '')[:60]}...",
            f"当前价格: {m.get('last_price', '?')}¢",
            "",
            "🔍 数据源:",
        ]
        
        # 官方数据源
        for s in report['official_sources']:
            lines.append(f"  ✅ {s['source']} (官方) - {s['data_type']}")
        
        # 额外数据源
        for s in report['additional_sources']:
            if s.get('warning'):
                lines.append(f"  ⚠️ {s['source']} - {s.get('purpose', '')}")
            else:
                lines.append(f"  📎 {s['source']} - {s.get('purpose', '')}")
        
        lines.extend([
            "",
            f"📈 判断: {j['direction']}",
            f"🎯 置信度: {j['confidence']}%",
            f"💡 理由: {j['reasoning']}",
        ])
        
        if j['key_facts']:
            lines.append(f"📋 关键事实: {', '.join(j['key_facts'])}")
        
        if j['risks']:
            lines.append(f"⚠️ 风险: {', '.join(j['risks'])}")
        
        lines.extend([
            "",
            f"✅ 推荐: {j['recommendation']}",
            f"📦 仓位: {j['position_size']}",
        ])
        
        return "\n".join(lines)


def test():
    """测试函数"""
    researcher = MarketResearcherV2()
    
    # 测试失业率市场
    unemployment_market = {
        'ticker': 'KXU3MAX-30-10',
        'title': 'Will unemployment go above 10% before 2030?',
        'last_price': 37,
        'rules_primary': 'If the U-3 unemployment rate is above 10%, the market resolves to Yes.',
    }
    
    print("=== 测试失业率市场 ===")
    report = researcher.research(unemployment_market)
    print(researcher.format_report(report))
    print()
    
    # 测试 Trump 说话市场 (不可核查)
    trump_market = {
        'ticker': 'KXTRUMPSAY-CRYPTO',
        'title': 'Will Trump say "crypto" in his next speech?',
        'last_price': 65,
        'rules_primary': 'Resolves Yes if Trump says the word crypto in a speech.',
    }
    
    print("=== 测试 Trump 说话市场 ===")
    report2 = researcher.research(trump_market)
    print(researcher.format_report(report2))


if __name__ == "__main__":
    test()
