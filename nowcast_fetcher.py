#!/usr/bin/env python3
"""
Nowcast Data Fetcher - 获取实时预测数据

支持的数据源:
1. Atlanta Fed GDPNow - GDP 实时预测
2. Cleveland Fed Inflation Nowcast - CPI 预测
3. CME FedWatch - Fed 利率预测概率

Author: OpenClaw
Date: 2026-02-21
"""

import os
import re
import json
from datetime import datetime, timezone
from typing import Optional, Dict, List
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None

CACHE_DIR = Path(__file__).parent / "cache"
CACHE_TTL = 3600 * 2  # 2 hours


class NowcastFetcher:
    """获取各类 Nowcast 数据"""
    
    def __init__(self, use_cache: bool = True):
        self.use_cache = use_cache
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
    
    def _get_cache(self, key: str) -> Optional[Dict]:
        """获取缓存"""
        if not self.use_cache:
            return None
        
        cache_file = CACHE_DIR / f"nowcast_{key}.json"
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                # 检查是否过期
                cached_at = data.get("cached_at", 0)
                if datetime.now().timestamp() - cached_at < CACHE_TTL:
                    return data
            except:
                pass
        return None
    
    def _set_cache(self, key: str, data: Dict):
        """设置缓存"""
        if not self.use_cache:
            return
        
        cache_file = CACHE_DIR / f"nowcast_{key}.json"
        data["cached_at"] = datetime.now().timestamp()
        with open(cache_file, "w") as f:
            json.dump(data, f)
    
    def get_gdpnow(self) -> Optional[Dict]:
        """
        获取 Atlanta Fed GDPNow 预测
        
        Returns:
            {
                "value": 2.3,        # 当前预测值 (%)
                "quarter": "Q1 2026",
                "updated": "2026-02-19",
                "source": "Atlanta Fed GDPNow"
            }
        """
        cached = self._get_cache("gdpnow")
        if cached:
            return cached
        
        try:
            # GDPNow XML feed
            url = "https://www.atlantafed.org/-/media/documents/cqer/researchcq/gdpnow/gdpnow-forecast-evolution.xml"
            resp = requests.get(url, timeout=15)
            
            if resp.status_code == 200:
                # 解析 XML (简单正则)
                text = resp.text
                
                # 查找最新预测值
                # <GDPNow>2.3</GDPNow> 或类似格式
                match = re.search(r'<Forecast[^>]*>([0-9.]+)</Forecast>', text)
                if not match:
                    match = re.search(r'>([0-9.]+)%?\s*</', text)
                
                if match:
                    value = float(match.group(1))
                    data = {
                        "value": value,
                        "quarter": "Q1 2026",  # TODO: 动态获取
                        "updated": datetime.now().strftime("%Y-%m-%d"),
                        "source": "Atlanta Fed GDPNow"
                    }
                    self._set_cache("gdpnow", data)
                    return data
        except Exception as e:
            print(f"GDPNow fetch error: {e}")
        
        # Fallback: 使用已知的最新值
        return {
            "value": 2.3,  # 需要手动更新
            "quarter": "Q1 2026",
            "updated": "2026-02-20",
            "source": "Atlanta Fed GDPNow (cached)",
            "is_fallback": True
        }
    
    def get_cpi_nowcast(self) -> Optional[Dict]:
        """
        获取 Cleveland Fed Inflation Nowcast
        
        Returns:
            {
                "value": 0.3,        # 月度 CPI 预测 (%)
                "annual": 2.8,       # 年化 CPI 预测 (%)
                "month": "February 2026",
                "source": "Cleveland Fed"
            }
        """
        cached = self._get_cache("cpi_nowcast")
        if cached:
            return cached
        
        try:
            # Cleveland Fed Nowcast 页面
            url = "https://www.clevelandfed.org/indicators-and-data/inflation-nowcasting"
            resp = requests.get(url, timeout=15, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
            })
            
            if resp.status_code == 200:
                text = resp.text
                
                # 查找月度 CPI 预测
                # 通常格式: "0.3%" 或 "0.30%"
                match = re.search(r'CPI[^0-9]*([0-9]+\.[0-9]+)%', text, re.IGNORECASE)
                if match:
                    value = float(match.group(1))
                    data = {
                        "value": value,
                        "month": datetime.now().strftime("%B %Y"),
                        "source": "Cleveland Fed Inflation Nowcast"
                    }
                    self._set_cache("cpi_nowcast", data)
                    return data
        except Exception as e:
            print(f"CPI Nowcast fetch error: {e}")
        
        # Fallback
        return {
            "value": 0.3,  # 典型值
            "month": "February 2026",
            "source": "Cleveland Fed (estimated)",
            "is_fallback": True
        }
    
    def get_fedwatch(self) -> Optional[Dict]:
        """
        获取 CME FedWatch 利率预测概率
        
        Returns:
            {
                "next_meeting": "March 2026",
                "current_rate": 4.25,
                "probabilities": {
                    "cut_50": 5.0,     # 降息 50bp 概率
                    "cut_25": 20.0,    # 降息 25bp 概率
                    "hold": 70.0,      # 维持不变概率
                    "hike_25": 5.0,    # 加息 25bp 概率
                },
                "source": "CME FedWatch"
            }
        """
        cached = self._get_cache("fedwatch")
        if cached:
            return cached
        
        # CME FedWatch 需要 API key 或复杂爬虫
        # 这里返回 fallback 值
        return {
            "next_meeting": "March 2026",
            "current_rate": 4.25,
            "probabilities": {
                "cut_50": 5.0,
                "cut_25": 25.0,
                "hold": 65.0,
                "hike_25": 5.0,
            },
            "source": "CME FedWatch (estimated)",
            "is_fallback": True
        }
    
    def get_for_market(self, series: str, threshold: float = None) -> Optional[Dict]:
        """
        根据市场 series 获取相关 Nowcast
        
        Args:
            series: 市场 series (如 KXGDP, KXCPI, KXFED)
            threshold: 市场阈值 (如 GDP > 2.0%)
        
        Returns:
            {
                "nowcast_value": 2.3,
                "threshold": 2.0,
                "direction": "above",  # 预测值 > 阈值
                "confidence": 0.8,     # 距离阈值的置信度
                "source": "..."
            }
        """
        series_upper = series.upper()
        
        if "GDP" in series_upper:
            data = self.get_gdpnow()
            if data and threshold is not None:
                nowcast = data["value"]
                direction = "above" if nowcast > threshold else "below"
                # 简单置信度: 距离阈值越远越高
                distance = abs(nowcast - threshold)
                confidence = min(1.0, distance / 1.0)  # 1% 距离 = 100% 置信
                return {
                    "nowcast_value": nowcast,
                    "threshold": threshold,
                    "direction": direction,
                    "confidence": confidence,
                    "z_score": distance / 0.5,  # σ ≈ 0.5% for GDP
                    "source": data["source"],
                }
            return data
        
        elif "CPI" in series_upper:
            data = self.get_cpi_nowcast()
            if data and threshold is not None:
                nowcast = data["value"]
                direction = "above" if nowcast > threshold else "below"
                distance = abs(nowcast - threshold)
                confidence = min(1.0, distance / 0.2)  # 0.2% 距离 = 100% 置信
                return {
                    "nowcast_value": nowcast,
                    "threshold": threshold,
                    "direction": direction,
                    "confidence": confidence,
                    "z_score": distance / 0.1,  # σ ≈ 0.1% for CPI
                    "source": data["source"],
                }
            return data
        
        elif "FED" in series_upper or "FOMC" in series_upper:
            data = self.get_fedwatch()
            if data and threshold is not None:
                # Fed 市场: 预测利率是否高于阈值
                current = data["current_rate"]
                probs = data["probabilities"]
                
                # 简化: 如果维持不变概率高，预测利率不变
                if probs["hold"] > 60:
                    predicted_rate = current
                elif probs["cut_25"] + probs["cut_50"] > 50:
                    predicted_rate = current - 0.25
                else:
                    predicted_rate = current + 0.25
                
                direction = "above" if predicted_rate > threshold else "below"
                confidence = max(probs.values()) / 100
                
                return {
                    "nowcast_value": predicted_rate,
                    "threshold": threshold,
                    "direction": direction,
                    "confidence": confidence,
                    "z_score": confidence * 2,  # 简化
                    "source": data["source"],
                    "probabilities": probs,
                }
            return data
        
        return None


def test():
    """测试 Nowcast 获取"""
    fetcher = NowcastFetcher(use_cache=False)
    
    print("=== GDP Now ===")
    gdp = fetcher.get_gdpnow()
    print(json.dumps(gdp, indent=2))
    
    print("\n=== CPI Nowcast ===")
    cpi = fetcher.get_cpi_nowcast()
    print(json.dumps(cpi, indent=2))
    
    print("\n=== FedWatch ===")
    fed = fetcher.get_fedwatch()
    print(json.dumps(fed, indent=2))
    
    print("\n=== GDP Market (threshold 2.0%) ===")
    gdp_market = fetcher.get_for_market("KXGDP", threshold=2.0)
    print(json.dumps(gdp_market, indent=2))


if __name__ == "__main__":
    test()
