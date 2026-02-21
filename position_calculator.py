#!/usr/bin/env python3
"""
动态仓位计算器

根据置信度、账户余额、风险偏好计算建议仓位

用法:
    from position_calculator import PositionCalculator
    calc = PositionCalculator()
    position = calc.calculate("HIGH", 85)  # 置信度, 价格

Author: OpenClaw
Date: 2026-02-21
"""

import os
import json
from pathlib import Path
from typing import Dict, Optional, Tuple

# 默认风险配置
DEFAULT_RISK_CONFIG = {
    "max_single_position_pct": 0.15,    # 单笔最大仓位 (占可用余额)
    "max_portfolio_exposure_pct": 0.50,  # 总敞口上限
    "min_cash_reserve_pct": 0.20,        # 最小现金储备
    "confidence_multipliers": {
        "HIGH": 1.0,      # 高置信度用满配额
        "MEDIUM": 0.5,    # 中置信度减半
        "LOW": 0.0,       # 低置信度不开仓
    },
    "kelly_fraction": 0.25,  # Kelly criterion 缩放因子 (保守)
}

CONFIG_FILE = Path(__file__).parent / "config" / "risk_config.json"


class PositionCalculator:
    """动态仓位计算器"""
    
    def __init__(self, config: Optional[Dict] = None):
        """
        初始化计算器
        
        Args:
            config: 风险配置，None 则使用默认或从文件加载
        """
        self.config = config or self._load_config()
    
    def _load_config(self) -> Dict:
        """加载风险配置"""
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE) as f:
                    return {**DEFAULT_RISK_CONFIG, **json.load(f)}
            except:
                pass
        return DEFAULT_RISK_CONFIG.copy()
    
    def save_config(self):
        """保存当前配置"""
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(self.config, f, indent=2)
    
    def get_account_info(self) -> Dict:
        """
        获取账户信息
        
        Returns:
            {
                "balance": float,           # 可用余额 ($)
                "portfolio_value": float,   # 持仓价值 ($)
                "total": float,             # 总资产 ($)
                "exposure_pct": float,      # 当前敞口占比
            }
        """
        try:
            from get_positions import get_balance
            data = get_balance()
            
            balance = data.get("balance", 0) / 100  # cents → dollars
            portfolio = data.get("portfolio_value", 0) / 100
            total = balance + portfolio
            
            exposure_pct = portfolio / total if total > 0 else 0
            
            return {
                "balance": balance,
                "portfolio_value": portfolio,
                "total": total,
                "exposure_pct": exposure_pct,
            }
        except Exception as e:
            return {
                "balance": 0,
                "portfolio_value": 0,
                "total": 0,
                "exposure_pct": 0,
                "error": str(e),
            }
    
    def calculate_kelly(self, confidence: str, price: int) -> float:
        """
        用 Kelly Criterion 计算最优仓位比例
        
        Args:
            confidence: HIGH/MEDIUM/LOW
            price: 市场价格 (0-100)
        
        Returns:
            建议仓位比例 (0.0-1.0)
        """
        # 置信度 → 胜率估计
        win_prob_map = {
            "HIGH": 0.80,
            "MEDIUM": 0.65,
            "LOW": 0.50,
        }
        p = win_prob_map.get(confidence, 0.5)
        
        # 计算赔率
        cost = min(price, 100 - price)
        if cost <= 0 or cost >= 100:
            return 0.0
        
        # b = 净收益 / 成本
        b = (100 - cost) / cost
        
        # Kelly 公式: f* = (bp - q) / b
        # p = 胜率, q = 1 - p
        q = 1 - p
        kelly = (b * p - q) / b if b > 0 else 0
        
        # 应用 fractional Kelly (更保守)
        kelly *= self.config.get("kelly_fraction", 0.25)
        
        return max(0, min(1, kelly))
    
    def calculate(
        self,
        confidence: str,
        price: int,
        account_info: Optional[Dict] = None,
    ) -> Dict:
        """
        计算建议仓位
        
        Args:
            confidence: HIGH/MEDIUM/LOW
            price: 市场价格 (0-100)
            account_info: 账户信息，None 则自动获取
        
        Returns:
            {
                "action": "BUY" | "WATCH" | "SKIP",
                "contracts": int,           # 建议合约数
                "dollars": float,           # 建议金额 ($)
                "position_pct": float,      # 占余额比例
                "reason": str,              # 原因说明
            }
        """
        if account_info is None:
            account_info = self.get_account_info()
        
        balance = account_info.get("balance", 0)
        exposure_pct = account_info.get("exposure_pct", 0)
        
        # 检查是否有足够余额
        if balance < 10:  # 最低 $10
            return {
                "action": "SKIP",
                "contracts": 0,
                "dollars": 0,
                "position_pct": 0,
                "reason": "余额不足 (< $10)",
            }
        
        # 检查总敞口限制
        max_exposure = self.config.get("max_portfolio_exposure_pct", 0.5)
        if exposure_pct >= max_exposure:
            return {
                "action": "SKIP",
                "contracts": 0,
                "dollars": 0,
                "position_pct": 0,
                "reason": f"总敞口已达上限 ({exposure_pct:.0%} >= {max_exposure:.0%})",
            }
        
        # 置信度乘数
        conf_mult = self.config.get("confidence_multipliers", {})
        multiplier = conf_mult.get(confidence, 0)
        
        if multiplier <= 0:
            return {
                "action": "WATCH",
                "contracts": 0,
                "dollars": 0,
                "position_pct": 0,
                "reason": f"置信度 {confidence} → 观望",
            }
        
        # 计算 Kelly 仓位
        kelly_pct = self.calculate_kelly(confidence, price)
        
        # 应用单笔上限
        max_single = self.config.get("max_single_position_pct", 0.15)
        position_pct = min(kelly_pct * multiplier, max_single)
        
        # 保留现金储备
        min_reserve = self.config.get("min_cash_reserve_pct", 0.2)
        available = balance * (1 - min_reserve)
        
        # 计算最终金额
        dollars = available * position_pct
        dollars = max(10, min(200, dollars))  # 限制在 $10-$200
        
        # 计算合约数
        cost = min(price, 100 - price)
        contracts = int(dollars * 100 / cost) if cost > 0 else 0
        
        # 实际金额
        actual_dollars = contracts * cost / 100
        
        return {
            "action": "BUY",
            "contracts": contracts,
            "dollars": round(actual_dollars, 2),
            "position_pct": round(position_pct, 3),
            "reason": f"Kelly {kelly_pct:.1%} × {multiplier:.1f} → {position_pct:.1%}",
            "kelly_raw": round(kelly_pct, 3),
        }
    
    def format_recommendation(self, result: Dict) -> str:
        """格式化建议"""
        action = result.get("action", "SKIP")
        
        if action == "SKIP":
            return f"⏭️ 跳过: {result.get('reason', '')}"
        elif action == "WATCH":
            return f"👀 观望: {result.get('reason', '')}"
        else:
            contracts = result.get("contracts", 0)
            dollars = result.get("dollars", 0)
            pct = result.get("position_pct", 0)
            return f"💰 建议: {contracts} 份 (~${dollars:.0f}) | {pct:.0%} 仓位"


def main():
    """测试计算器"""
    calc = PositionCalculator()
    
    # 获取账户信息
    info = calc.get_account_info()
    print(f"账户信息:")
    print(f"  可用余额: ${info.get('balance', 0):.2f}")
    print(f"  持仓价值: ${info.get('portfolio_value', 0):.2f}")
    print(f"  总资产: ${info.get('total', 0):.2f}")
    print(f"  当前敞口: {info.get('exposure_pct', 0):.1%}")
    print()
    
    # 测试不同场景
    scenarios = [
        ("HIGH", 92),    # 高置信度，极端价格
        ("HIGH", 85),    # 高置信度，一般价格
        ("MEDIUM", 88),  # 中置信度
        ("LOW", 90),     # 低置信度
    ]
    
    print("场景测试:")
    for conf, price in scenarios:
        result = calc.calculate(conf, price, info)
        rec = calc.format_recommendation(result)
        print(f"  {conf} @ {price}¢: {rec}")


if __name__ == "__main__":
    main()
