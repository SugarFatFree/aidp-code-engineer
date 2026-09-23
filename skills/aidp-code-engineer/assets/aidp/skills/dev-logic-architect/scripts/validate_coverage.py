#!/usr/bin/env python3
"""
功规点覆盖率校验脚本

用法:
  python validate_coverage.py <PRD文件路径> <设计文档路径> [--json]

从 PRD 中提取功规点编号，在设计文档中检查每个编号是否出现，
输出覆盖率报告。支持 --json 参数输出 JSON 格式结果。

支持的编号格式:
  - FR-001, REQ-01, FUN-1, UC-1, US-001
  - 层级编号: 1.1, 1.1.1, 2.3.4 (需为独立编号，不匹配版本号等)
  - 中文编号: 功能点1, 需求-01

跨平台支持: Linux / macOS / Windows (Python 3.6+)

退出码(遵全仓统一约定,见 CLAUDE.md「全仓脚本退出码统一约定」):
  0 = 通过(功规点 100% 覆盖) / N/A 跳过(PRD 里一个功规点编号都没提取到)
  1 = 检出违规(存在未覆盖的功规点)
  2 = 入参或环境错(位置参数不足 / PRD 或设计文档路径不存在)

⚠️ **入参错必须是 2、不是 1**:1 已被「有未覆盖功规点」占用,撞码时调用方会把
   「路径打错一个字」读成「维度 9 PRD 功能点覆盖不通过」,反复去改设计文档也修不好。
⚠️ **N/A 跳过必须能被区分**:提取不到功规点编号时 `--json` 会输出
   `{"skipped": true, "reason": ...}`,调用方据此判定「没跑」而非「通过」——
   PRD 用纯中文标题式功规点(常见的功能规格说明书正是这种)
   时会走到这一支,没有标记就会被读成「覆盖率检查通过」= 假绿。
"""

import json
import re
import sys
from pathlib import Path


def extract_requirement_ids(prd_text: str) -> list:
    """从 PRD 文本中提取功规点编号"""
    ids = set()

    # 模式1: 标准前缀编号 (FR-001, REQ_01, FUN-1, UC-1, US-001)
    pattern_prefix = r'\b((?:FR|REQ|FUN|UC|US|FEAT|BUG|CR)[-_]\d+(?:\.\d+)*)\b'
    for m in re.finditer(pattern_prefix, prd_text, re.IGNORECASE):
        ids.add(m.group(1).upper())

    # 模式2: 层级编号 (1.1, 1.1.1, 2.3.4)
    # 要求: 行首或前面是空白/标点，后面是空白/标点/行尾
    # 排除: 版本号(v1.0, V2.1)、IP地址、小数
    pattern_hierarchy = r'(?:^|(?<=[\s\-\|：:•·]))(\d+\.\d+(?:\.\d+)*)\b'
    for m in re.finditer(pattern_hierarchy, prd_text, re.MULTILINE):
        candidate = m.group(1)
        # 排除版本号上下文
        start = max(0, m.start() - 5)
        prefix_ctx = prd_text[start:m.start()].lower()
        if any(v in prefix_ctx for v in ['v', 'ver', 'version', '版本']):
            continue
        # 排除只有一级的纯数字 (如 "1." 开头的列表项不算)
        if '.' in candidate:
            ids.add(candidate)

    return sorted(ids)


def check_coverage(design_text: str, req_ids: list) -> dict:
    """检查设计文档中是否覆盖了所有功规点，使用精确匹配避免误判"""
    covered = []
    missing = []

    for rid in req_ids:
        # 使用词边界匹配，避免 "1.1" 匹配到 "v1.1" 或 "11.1"
        escaped = re.escape(rid)
        pattern = r'(?<![.\w])' + escaped + r'(?![.\d\w])'
        if re.search(pattern, design_text, re.IGNORECASE):
            covered.append(rid)
        else:
            missing.append(rid)

    total = len(req_ids)
    return {
        "total": total,
        "covered": len(covered),
        "covered_ids": covered,
        "missing": missing,
        "coverage_rate": round(len(covered) / total * 100, 1) if total else 0,
    }


def main():
    # 解析参数
    if '-h' in sys.argv[1:] or '--help' in sys.argv[1:]:
        print("用法: python validate_coverage.py <PRD文件路径> <设计文档路径> [--json]")
        sys.exit(0)
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    flags = [a for a in sys.argv[1:] if a.startswith('--')]
    output_json = '--json' in flags

    if len(args) < 2:
        print("用法: python validate_coverage.py <PRD文件路径> <设计文档路径> [--json]",
              file=sys.stderr)
        sys.exit(2)  # 入参错,不是「检出违规」

    prd_path = Path(args[0])
    design_path = Path(args[1])

    if not prd_path.exists():
        msg = f"错误: PRD 文件不存在 - {prd_path}"
        if output_json:
            print(json.dumps({"error": msg}, ensure_ascii=False))
        print(msg, file=sys.stderr)
        sys.exit(2)  # 环境/入参错,不是「检出违规」

    if not design_path.exists():
        msg = f"错误: 设计文档不存在 - {design_path}"
        if output_json:
            print(json.dumps({"error": msg}, ensure_ascii=False))
        print(msg, file=sys.stderr)
        sys.exit(2)  # 环境/入参错,不是「检出违规」

    prd_text = prd_path.read_text(encoding="utf-8")
    design_text = design_path.read_text(encoding="utf-8")

    req_ids = extract_requirement_ids(prd_text)

    if not req_ids:
        msg = "警告: 未从 PRD 中提取到功规点编号，请检查 PRD 格式。"
        if output_json:
            # ⚠️ `skipped` 必须在:没有它,调用方分不出「真通过」与「整档没跑」
            print(json.dumps({"skipped": True, "reason": "PRD 未提取到任何功规点编号",
                              "warning": msg, "supported_formats": [
                "FR-001, REQ-01, FUN-1, UC-1, US-001",
                "层级编号: 1.1, 1.1.1, 2.3.4"
            ]}, ensure_ascii=False))
        else:
            print(msg)
            print("支持的编号格式: FR-001, REQ-01, UC-1, 1.1.1 等")
        sys.exit(0)

    result = check_coverage(design_text, req_ids)

    if output_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"\n{'='*50}")
        print("功规点覆盖率报告")
        print(f"{'='*50}")
        print(f"PRD 文件: {prd_path.name}")
        print(f"设计文档: {design_path.name}")
        print(f"功规点总数: {result['total']}")
        print(f"已覆盖: {result['covered']}")
        print(f"覆盖率: {result['coverage_rate']}%")

        if result["missing"]:
            print(f"\n未覆盖的功规点 ({len(result['missing'])} 项):")
            for mid in result["missing"]:
                print(f"  - {mid}")
        else:
            print("\n所有功规点均已覆盖!")

        print(f"{'='*50}")

    sys.exit(0 if not result["missing"] else 1)


if __name__ == "__main__":
    main()
