#!/usr/bin/env python3
r"""
check_3p_capability.py — 七·4 第三方对接清单合规扫描

扫描 PRD 文档(单文件或目录),验证 七·4 章节:
  1. 编号唯一性 (CAP-OUT/CAP-IN/REQ-3P/REQ-3P-CB)
  2. 编号格式严格匹配 3 位数字 (^CAP-OUT-\d{3}$ 等)
  3. 七·4.4 各场景引用的编号 ⊆ 七·4.2/4.3 清单
  4. 七·4.2/4.3 清单中的每个编号在 七·4.4 至少出现一次
  5. (可选) 同一调用动作的双向编号互引检查
  6. 七·4.2 / 七·4.3 章节存在性

输出:
- 文本模式: 结构化检查报告
- --json 模式: JSON 报告

退出码:
- 0: 通过
- 1: 不通过
- 2: 输入错误
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set


# 严格的编号格式
ID_PATTERNS = {
    "CAP-OUT": re.compile(r"\bCAP-OUT-\d{3}\b"),
    "CAP-IN": re.compile(r"\bCAP-IN-\d{3}\b"),
    "REQ-3P": re.compile(r"\bREQ-3P-(?!CB)\d{3}\b"),
    "REQ-3P-CB": re.compile(r"\bREQ-3P-CB-\d{3}\b"),
}
# 不严格(用于检测格式错误)
LOOSE_PATTERNS = {
    "CAP-OUT": re.compile(r"\bCAP-OUT-\d+\b"),
    "CAP-IN": re.compile(r"\bCAP-IN-\d+\b"),
    "REQ-3P": re.compile(r"\bREQ-3P-(?!CB)\d+\b"),
    "REQ-3P-CB": re.compile(r"\bREQ-3P-CB-\d+\b"),
}

# 章节标题正则
# 编号后允许接空白、中文顿号/逗号或英文逗号(本项目标题惯用 "七·4.2、xxx" 顿号写法),
# 以免 "七·4.2、本系统…" 这类合法标题被漏识别为"章节缺失"。字符类避免匹配 "4.20" 等。
SECTION_42_PATTERN = re.compile(r"^#{2,5}\s+七[·\-．\.]4\.2[\s、，,]", re.MULTILINE)
SECTION_43_PATTERN = re.compile(r"^#{2,5}\s+七[·\-．\.]4\.3[\s、，,]", re.MULTILINE)
SECTION_44_PATTERN = re.compile(r"^#{2,5}\s+七[·\-．\.]4\.4[\s、，,]", re.MULTILINE)
SECTION_45_PATTERN = re.compile(r"^#{2,5}\s+七[·\-．\.]4\.5[\s、，,]", re.MULTILINE)


def find_md_files(target: Path) -> List[Path]:
    if target.is_file():
        return [target] if target.suffix == ".md" else []
    if target.is_dir():
        return sorted(target.rglob("*.md"))
    return []


def extract_section(text: str, start_pat: re.Pattern, *next_pats: re.Pattern) -> str:
    m = start_pat.search(text)
    if not m:
        return ""
    start = m.end()
    end = len(text)
    for npat in next_pats:
        nm = npat.search(text, start)
        if nm and nm.start() < end:
            end = nm.start()
    return text[start:end]


def collect_ids(text: str, strict: bool = True) -> Dict[str, List[str]]:
    patterns = ID_PATTERNS if strict else LOOSE_PATTERNS
    return {kind: pat.findall(text) for kind, pat in patterns.items()}


def find_duplicates(ids: List[str]) -> List[str]:
    seen: Dict[str, int] = defaultdict(int)
    for x in ids:
        seen[x] += 1
    return sorted([k for k, v in seen.items() if v > 1])


def find_format_violations(text: str) -> List[str]:
    """Find IDs that don't match strict 3-digit format."""
    violations: List[str] = []
    for kind, loose in LOOSE_PATTERNS.items():
        strict = ID_PATTERNS[kind]
        for m in loose.finditer(text):
            if not strict.fullmatch(m.group()):
                violations.append(m.group())
    return sorted(set(violations))


def analyze_file(md_file: Path) -> Dict:
    text = md_file.read_text(encoding="utf-8", errors="replace")

    has_42 = bool(SECTION_42_PATTERN.search(text))
    has_43 = bool(SECTION_43_PATTERN.search(text))
    has_44 = bool(SECTION_44_PATTERN.search(text))
    has_45 = bool(SECTION_45_PATTERN.search(text))

    sec_42 = extract_section(text, SECTION_42_PATTERN, SECTION_43_PATTERN, SECTION_44_PATTERN, SECTION_45_PATTERN)
    sec_43 = extract_section(text, SECTION_43_PATTERN, SECTION_44_PATTERN, SECTION_45_PATTERN)
    sec_44 = extract_section(text, SECTION_44_PATTERN, SECTION_45_PATTERN)

    ids_42 = collect_ids(sec_42)
    ids_43 = collect_ids(sec_43)
    ids_44 = collect_ids(sec_44)

    cap_set = set(ids_42["CAP-OUT"]) | set(ids_42["CAP-IN"])
    req_set = set(ids_43["REQ-3P"]) | set(ids_43["REQ-3P-CB"])
    catalog_set = cap_set | req_set
    referenced_in_44: Set[str] = set()
    for kind in ID_PATTERNS:
        referenced_in_44.update(ids_44[kind])

    orphans_in_44 = sorted(referenced_in_44 - catalog_set)
    orphans_in_catalog = sorted(catalog_set - referenced_in_44)

    # 重复编号只统计"定义区"(CAP-* 定义于 七·4.2,REQ-* 定义于 七·4.3);
    # 编号在 七·4.4 场景中被引用是双向追溯的强制要求,不算重复
    duplicates: Dict[str, List[str]] = {}
    for kind in ID_PATTERNS:
        catalog_ids = ids_42[kind] if kind.startswith("CAP") else ids_43[kind]
        dups = find_duplicates(catalog_ids)
        if dups:
            duplicates[kind] = dups

    format_violations = find_format_violations(text)

    return {
        "file": str(md_file),
        "structure": {
            "has_section_42": has_42,
            "has_section_43": has_43,
            "has_section_44": has_44,
            "has_section_45": has_45,
        },
        "id_counts": {
            "CAP-OUT": len(set(ids_42["CAP-OUT"])),
            "CAP-IN": len(set(ids_42["CAP-IN"])),
            "REQ-3P": len(set(ids_43["REQ-3P"])),
            "REQ-3P-CB": len(set(ids_43["REQ-3P-CB"])),
        },
        "duplicates": duplicates,
        "format_violations": format_violations,
        "orphan_refs_in_44": orphans_in_44,
        "unused_in_catalog": orphans_in_catalog,
    }


def aggregate(file_results: List[Dict]) -> Dict:
    return {
        "files_total": len(file_results),
        "files_with_3p_section": sum(
            1 for r in file_results if r["structure"]["has_section_42"] or r["structure"]["has_section_43"]
        ),
        "files_passed": sum(
            1
            for r in file_results
            if not r["duplicates"]
            and not r["format_violations"]
            and not r["orphan_refs_in_44"]
            and not r["unused_in_catalog"]
            and (
                not r["structure"]["has_section_44"]
                or (r["structure"]["has_section_42"] and r["structure"]["has_section_43"])
            )
        ),
    }


def print_text_report(file_results: List[Dict], summary: Dict) -> None:
    print("=" * 78)
    print("七·4 第三方对接清单合规扫描报告")
    print("=" * 78)
    print(f"\n扫描文件总数: {summary['files_total']}")
    print(f"  含 七·4 章节: {summary['files_with_3p_section']}")
    print(f"  全项通过: {summary['files_passed']}")

    for r in file_results:
        s = r["structure"]
        if not (s["has_section_42"] or s["has_section_43"]):
            continue
        print(f"\n文件: {r['file']}")
        print(f"  章节存在: 42={s['has_section_42']} 43={s['has_section_43']} 44={s['has_section_44']} 45={s['has_section_45']}")
        print(f"  编号统计: {r['id_counts']}")
        if r["duplicates"]:
            print(f"  ❌ 重复编号: {r['duplicates']}")
        if r["format_violations"]:
            print(f"  ❌ 格式违规(应为 3 位数字): {r['format_violations']}")
        if r["orphan_refs_in_44"]:
            print(f"  ❌ 七·4.4 引用了清单未定义的编号: {r['orphan_refs_in_44']}")
        if r["unused_in_catalog"]:
            print(f"  ❌ 七·4.2/4.3 清单中未在 七·4.4 出现的编号(反向追溯断链): {r['unused_in_catalog']}")
        if not r["duplicates"] and not r["format_violations"] and not r["orphan_refs_in_44"] and not r["unused_in_catalog"]:
            print("  ✅ 全项通过")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="七·4 第三方对接清单编号唯一性 + 双向追溯 + 格式合规扫描"
    )
    parser.add_argument("path", help="PRD 文档路径或目录")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = parser.parse_args()

    target = Path(args.path)
    if not target.exists():
        print(f"错误: 路径不存在: {target}", file=sys.stderr)
        return 2

    md_files = find_md_files(target)
    if not md_files:
        print(f"错误: 未找到 .md 文件: {target}", file=sys.stderr)
        return 2

    file_results = [analyze_file(p) for p in md_files]
    summary = aggregate(file_results)

    if args.json:
        print(json.dumps({"summary": summary, "files": file_results}, ensure_ascii=False, indent=2))
    else:
        print_text_report(file_results, summary)

    failures = sum(
        1
        for r in file_results
        if r["duplicates"] or r["format_violations"] or r["orphan_refs_in_44"]
        # 反向追溯断链: 七·4.2/4.3 清单中的编号未在 七·4.4 任一场景出现(维度8 双向追溯强制,与 docstring 检查项 4 对齐)
        or r["unused_in_catalog"]
        # 七·4.4 明细存在但 4.2/4.3 汇总清单缺失 = 维度8 不通过(与 aggregate.files_passed 口径对齐)
        or (r["structure"]["has_section_44"]
            and not (r["structure"]["has_section_42"] and r["structure"]["has_section_43"]))
    )
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
