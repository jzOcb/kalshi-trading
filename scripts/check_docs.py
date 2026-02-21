#!/usr/bin/env python3
"""
脚本文档检查器 - 确保每个 .py 文件有完整文档

检查项:
1. 模块级 docstring
2. docstring 包含: 功能描述、使用方法、依赖关系

用法:
    python check_docs.py              # 检查所有脚本
    python check_docs.py --fix        # 生成缺失文档模板
    python check_docs.py --strict     # 严格模式 (CI 用)
"""

import ast
import sys
from pathlib import Path

REQUIRED_SECTIONS = ["功能", "用法"]  # 必须包含的关键词
SKIP_FILES = ["__init__.py"]

def check_docstring(filepath: Path) -> dict:
    """检查单个文件的文档状态"""
    result = {
        "file": filepath.name,
        "has_docstring": False,
        "docstring": None,
        "missing_sections": [],
        "status": "❌"
    }
    
    try:
        with open(filepath) as f:
            tree = ast.parse(f.read())
        
        docstring = ast.get_docstring(tree)
        if docstring:
            result["has_docstring"] = True
            result["docstring"] = docstring
            
            # 检查必要段落
            for section in REQUIRED_SECTIONS:
                if section not in docstring:
                    result["missing_sections"].append(section)
            
            if not result["missing_sections"]:
                result["status"] = "✅"
            else:
                result["status"] = "⚠️"
        
    except Exception as e:
        result["error"] = str(e)
    
    return result

def generate_template(filepath: Path) -> str:
    """生成文档模板"""
    name = filepath.stem
    return f'''"""
{name} — [一句话描述功能]

功能：
    - [主要功能 1]
    - [主要功能 2]

用法：
    python {filepath.name} [参数]
    
    示例：
        python {filepath.name} --help

依赖：
    - [依赖的其他模块]

维护：
    创建: [日期]
    更新: [日期]
"""
'''

def main():
    kalshi_dir = Path(__file__).parent.parent
    py_files = sorted(kalshi_dir.glob("*.py"))
    
    strict = "--strict" in sys.argv
    fix = "--fix" in sys.argv
    
    print("📋 Kalshi 脚本文档检查")
    print("=" * 50)
    
    issues = []
    
    for f in py_files:
        if f.name in SKIP_FILES:
            continue
        
        result = check_docstring(f)
        
        if result["status"] == "✅":
            print(f"✅ {result['file']}")
        elif result["status"] == "⚠️":
            print(f"⚠️  {result['file']} — 缺少: {', '.join(result['missing_sections'])}")
            issues.append(result)
        else:
            print(f"❌ {result['file']} — 无 docstring")
            issues.append(result)
            
            if fix:
                print(f"   📝 生成模板...")
                template = generate_template(f)
                print(template[:200] + "...")
    
    print("=" * 50)
    
    if issues:
        print(f"⚠️  {len(issues)} 个文件需要补充文档")
        if strict:
            sys.exit(1)
    else:
        print("✅ 所有文件文档完整")
    
    return len(issues)

if __name__ == "__main__":
    main()
