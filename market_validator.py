#!/usr/bin/env python3
"""
market_validator.py - Kalshi Market Validation System

Classifies markets by type, enforces checklist completion,
and blocks recommendations when validation is incomplete.

Usage:
    from market_validator import classify_market, validate_output, get_checklist_prompt

    market_type = classify_market("KXHIGHTEMP-26FEB23-BOS-B42")
    prompt = get_checklist_prompt(market_type)
    # ... run LLM analysis with prompt ...
    validated = validate_output(analysis_text, market_type)
"""

import re
import yaml
from pathlib import Path
from typing import Optional

CHECKLISTS_PATH = Path(__file__).parent / "market_checklists.yaml"

_checklists_cache: Optional[dict] = None


def _load_checklists() -> dict:
    """Load and cache checklists from YAML."""
    global _checklists_cache
    if _checklists_cache is None:
        with open(CHECKLISTS_PATH) as f:
            _checklists_cache = yaml.safe_load(f)
    return _checklists_cache


def classify_market(ticker: str) -> str:
    """Classify a Kalshi market ticker into a type.
    
    Args:
        ticker: Kalshi ticker string (e.g. "KXHIGHTEMP-26FEB23-BOS-B42")
    
    Returns:
        One of: "economic", "event", "weather", "other"
    """
    checklists = _load_checklists()
    ticker_upper = ticker.upper()
    
    # Check each type's keywords (order matters: more specific first)
    for market_type in ["weather", "economic", "event"]:
        config = checklists.get(market_type, {})
        keywords = config.get("keywords", [])
        for kw in keywords:
            if kw in ticker_upper:
                return market_type
    
    return "other"


def get_checklist_prompt(market_type: str) -> str:
    """Generate a mandatory checklist prompt for LLM analysis.
    
    Args:
        market_type: One of "economic", "event", "weather", "other"
    
    Returns:
        Prompt text that forces LLM to answer all checklist questions
    """
    checklists = _load_checklists()
    config = checklists.get(market_type, checklists["other"])
    items = config.get("checklist", [])
    
    lines = [
        f"## 强制验证 ({market_type} 类市场)",
        "",
        "⚠️ 你必须逐项回答以下问题。答不上来的写 'UNKNOWN'。",
        "有任何 UNKNOWN 且该项标记为必填 → 最终建议必须是 SKIP。",
        "",
    ]
    
    for i, item in enumerate(items, 1):
        required = " [必填]" if item.get("fail_if_empty", False) else " [可选]"
        lines.append(f"{i}. **{item['id']}**{required}: {item['question']}")
    
    lines.extend([
        "",
        "---",
        "回答完以上问题后，在 `### 验证结果` 部分汇总：",
        "- 每项标 ✅ (已回答) 或 ❌ (UNKNOWN)",
        "- 有任何必填项 ❌ → 建议必须为 SKIP",
    ])
    
    return "\n".join(lines)


def validate_output(analysis_text: str, market_type: str) -> dict:
    """Check if LLM output contains required validation sections.
    
    Args:
        analysis_text: The LLM's analysis output
        market_type: Market classification
    
    Returns:
        dict with:
            - valid: bool (all required checks present)
            - missing: list of missing required check IDs
            - has_validation_block: bool
            - recommendation_allowed: bool
    """
    checklists = _load_checklists()
    config = checklists.get(market_type, checklists["other"])
    items = config.get("checklist", [])
    
    text_upper = analysis_text.upper()
    
    # Check for validation block
    has_validation = bool(re.search(r'###?\s*验证结果|###?\s*VALIDATION', analysis_text, re.IGNORECASE))
    
    # Check each required item
    missing = []
    for item in items:
        if not item.get("fail_if_empty", False):
            continue
        item_id = item["id"]
        # Check if the item ID appears in the output with a non-UNKNOWN answer
        pattern = rf'{item_id}.*?[:：]\s*(.+?)(?:\n|$)'
        match = re.search(pattern, analysis_text, re.IGNORECASE)
        if not match or "UNKNOWN" in match.group(1).upper():
            missing.append(item_id)
    
    return {
        "valid": len(missing) == 0 and has_validation,
        "missing": missing,
        "has_validation_block": has_validation,
        "recommendation_allowed": len(missing) == 0,
    }


def enforce_output(analysis_text: str, market_type: str) -> str:
    """Post-process LLM output: append warning if validation is incomplete.
    
    This is the final gate. If validation is missing or incomplete,
    the recommendation is forcibly replaced with SKIP.
    
    Args:
        analysis_text: The LLM's analysis output
        market_type: Market classification
    
    Returns:
        Original text (if valid) or text with appended warning + forced SKIP
    """
    result = validate_output(analysis_text, market_type)
    
    if result["valid"]:
        return analysis_text
    
    warning_lines = [
        "",
        "---",
        "⚠️ **验证未通过 — 建议强制改为 SKIP**",
    ]
    
    if not result["has_validation_block"]:
        warning_lines.append("- 缺少验证结果块")
    
    if result["missing"]:
        warning_lines.append(f"- 必填项未回答: {', '.join(result['missing'])}")
    
    warning_lines.extend([
        "",
        "### 建议",
        "**SKIP** — 验证不完整，不给交易建议",
    ])
    
    return analysis_text + "\n".join(warning_lines)


# --- CLI for testing ---
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python market_validator.py <ticker> [--prompt] [--test-output <file>]")
        print("\nExamples:")
        print("  python market_validator.py KXCPI-26MAR25 --prompt")
        print("  python market_validator.py KXSHUTDOWN-26MAR25 --prompt")
        print("  python market_validator.py KXHIGHTEMP-26FEB23-BOS-B42 --prompt")
        sys.exit(0)
    
    ticker = sys.argv[1]
    market_type = classify_market(ticker)
    print(f"Ticker: {ticker}")
    print(f"Type: {market_type}")
    
    if "--prompt" in sys.argv:
        print(f"\n{get_checklist_prompt(market_type)}")
    
    if "--test-output" in sys.argv:
        idx = sys.argv.index("--test-output") + 1
        if idx < len(sys.argv):
            with open(sys.argv[idx]) as f:
                text = f.read()
            result = validate_output(text, market_type)
            print(f"\nValidation: {result}")
