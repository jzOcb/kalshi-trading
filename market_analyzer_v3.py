#!/usr/bin/env python3
"""
market_analyzer_v3 - 多角色分析框架
"""

import sys
import os
# Ensure user site-packages is in path
user_site = os.path.expanduser("~/Library/Python/3.9/lib/python/site-packages")
if user_site not in sys.path:
    sys.path.insert(0, user_site)

"""

4个角色强制质疑讨论：
1. 分析师 - 初始判断
2. 事实核查员 - 验证数据和历史
3. 魔鬼代言人 - 挑战结论
4. 风控官 - 评估风险收益

Author: OpenClaw
Date: 2026-02-22
"""

import os
import json
import re
from typing import Dict, Optional
from datetime import datetime

# Use requests for API calls (simpler, no SDK dependency issues)
import requests

MULTI_ROLE_PROMPT = """你要扮演4个角色分析这个预测市场。每个角色必须发言，不能跳过。

## 市场信息
标题: {title}
当前价格: {price}¢ ({direction} 方向)
结算规则: {rules}
到期天数: {days_left}

---

【分析师】
你是乐观的初始分析者。回答：
1. 这个市场本质在问什么？用一句话概括
2. 结算数据源是什么？（具体机构/网站）
3. 我的初步判断是：___（YES/NO 会赢）
4. 理由：___

【事实核查员】
你专门验证分析师说的对不对。回答：
1. 分析师提到的数据源正确吗？
2. 历史先例：这件事发生过吗？
   - 如果是发言类市场 → 搜过去的 transcript/记录吗？
   - 如果是经济数据 → 历史均值是多少？
3. 阈值检验：市场设的门槛是高是低？对比历史数据
4. 核查结论：分析师的判断 [可靠/存疑/错误]，因为___

【魔鬼代言人】
你专门唱反调，挑战分析师。回答：
1. 分析师可能错在哪里？
2. 什么情况下这个判断会翻车？
3. 有没有被忽略的风险因素？
4. 我的反对意见：___
5. 反对意见的可信度：[高/中/低]

【风控官】
你是最后把关的人，只看数字。回答：
1. 价格 {price}¢ 意味着：
   - 如果对了，$50 仓位赚 ${profit:.2f}
   - 如果错了，$50 仓位亏 ${loss:.2f}
   - 赔率 = 1:{odds:.1f}（对你不利/有利）
2. 综合以上三位的讨论：
   - 分析师的判断可信度：___
   - 事实核查是否通过：___
   - 魔鬼代言人的反对是否有效：___
3. 最终建议：[强烈买入/买入/观望/跳过]
4. 如果买入，建议仓位：$___
5. 核心风险一句话：___

---

最后，输出 JSON 格式的结论：
```json
{{
  "market_summary": "一句话总结",
  "recommendation": "BUY/WATCH/SKIP",
  "direction": "YES/NO",
  "confidence": 0.0-1.0,
  "position_size": 0-100,
  "key_risk": "主要风险",
  "fact_check_passed": true/false,
  "devil_advocate_concern": "魔鬼代言人的主要担忧",
  "risk_reward_favorable": true/false
}}
```
"""


class MarketAnalyzerV3:
    """多角色分析器 - 使用 HTTP 直接调用 Claude API"""
    
    def __init__(self):
        self.api_key = os.environ.get("ANTHROPIC_API_KEY")
        self.api_url = "https://api.anthropic.com/v1/messages"
    
    def _call_claude(self, prompt: str) -> Optional[str]:
        """直接调用 Claude API"""
        if not self.api_key:
            return None
        
        headers = {
            "x-api-key": self.api_key,
            "content-type": "application/json",
            "anthropic-version": "2023-06-01"
        }
        
        data = {
            "model": "claude-3-haiku-20240307",
            "max_tokens": 2500,
            "messages": [{"role": "user", "content": prompt}]
        }
        
        try:
            resp = requests.post(self.api_url, headers=headers, json=data, timeout=60)
            if resp.status_code == 200:
                return resp.json()["content"][0]["text"]
            else:
                print(f"API error: {resp.status_code} - {resp.text[:200]}")
                return None
        except Exception as e:
            print(f"Request error: {e}")
            return None
    
    def analyze(self, market: Dict) -> Dict:
        """
        分析市场
        
        Args:
            market: 包含 title, rules_primary, last_price 等字段
            
        Returns:
            分析结果 dict
        """
        if not self.api_key:
            return {"error": "ANTHROPIC_API_KEY not set"}
        
        # 提取信息
        title = market.get('title', '')
        rules = market.get('rules_primary', '') + '\n' + market.get('rules_secondary', '')
        price = market.get('last_price', 50)
        
        # 计算方向和风险收益
        if price >= 50:
            direction = "YES"
            cost = price
        else:
            direction = "NO"
            cost = 100 - price
        
        profit = (100 - cost) * 0.50  # $50 仓位的收益
        loss = cost * 0.50  # $50 仓位的亏损
        odds = loss / profit if profit > 0 else 99
        
        # 计算天数
        days_left = 30
        close_time = market.get('close_time', '')
        if close_time:
            try:
                from datetime import timezone
                close_dt = datetime.fromisoformat(close_time.replace("Z", "+00:00"))
                days_left = max(1, (close_dt - datetime.now(timezone.utc)).days)
            except:
                pass
        
        # 构建 prompt
        prompt = MULTI_ROLE_PROMPT.format(
            title=title,
            price=price,
            direction=direction,
            rules=rules[:1500],  # 限制长度
            days_left=days_left,
            profit=profit,
            loss=loss,
            odds=odds
        )
        
        text = self._call_claude(prompt)
        if not text:
            return {"error": "API call failed"}
        
        try:
            # 提取 JSON
            json_match = re.search(r'```json\s*([\s\S]*?)\s*```', text)
            if json_match:
                result = json.loads(json_match.group(1))
            else:
                # 尝试直接找 JSON
                json_match = re.search(r'\{[\s\S]*"recommendation"[\s\S]*\}', text)
                if json_match:
                    result = json.loads(json_match.group())
                else:
                    result = {"error": "Failed to parse JSON", "raw": text[:500]}
            
            # 添加完整分析文本
            result["full_analysis"] = text
            result["market_ticker"] = market.get("ticker", "")
            
            return result
            
        except Exception as e:
            return {"error": str(e), "raw": text[:500] if text else ""}
    
    def format_report(self, result: Dict) -> str:
        """格式化分析报告"""
        if "error" in result:
            return f"❌ 分析失败: {result['error']}"
        
        rec = result.get("recommendation", "SKIP")
        direction = result.get("direction", "?")
        conf = result.get("confidence", 0)
        position = result.get("position_size", 0)
        risk = result.get("key_risk", "未知")
        summary = result.get("market_summary", "")
        devil = result.get("devil_advocate_concern", "")
        fact_check = result.get("fact_check_passed", False)
        rr_favorable = result.get("risk_reward_favorable", False)
        
        emoji = "🟢" if rec == "BUY" else "🟡" if rec == "WATCH" else "🔴"
        
        lines = [
            f"{emoji} **{rec}** — {direction} @ {conf*100:.0f}% 置信度",
            f"📌 {summary}",
            "",
            f"✅ 事实核查: {'通过' if fact_check else '未通过'}",
            f"⚖️ 风险收益: {'有利' if rr_favorable else '不利'}",
            f"😈 魔鬼代言人: {devil}",
            "",
            f"💰 建议仓位: ${position}",
            f"⚠️ 核心风险: {risk}",
        ]
        
        return "\n".join(lines)


def test():
    """测试分析器"""
    analyzer = MarketAnalyzerV3()
    
    if not analyzer.api_key:
        print("❌ ANTHROPIC_API_KEY not set")
        return
    
    # 测试 Powell stagflation 市场
    test_market = {
        "ticker": "KXFEDMENTION-26MAR-STAG",
        "title": "Will Powell say Stagflation at his Mar 2026 press conference?",
        "rules_primary": "Resolves Yes if Powell says the word 'stagflation' during the FOMC press conference.",
        "last_price": 12,  # NO @ 88¢
        "close_time": "2026-03-18T18:00:00Z"
    }
    
    print("分析中...")
    result = analyzer.analyze(test_market)
    
    print("\n" + "="*60)
    print("📊 分析报告")
    print("="*60)
    print(analyzer.format_report(result))
    
    print("\n" + "-"*60)
    print("📝 完整分析:")
    print("-"*60)
    print(result.get("full_analysis", "N/A")[:2000])


if __name__ == "__main__":
    test()
