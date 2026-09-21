#!/usr/bin/env python3
"""
check_enum_contract.py — A.4 字典/枚举强制枚举类合规扫描

扫描详细设计文档(单文件或目录),验证 A.4 章节中每个字典/枚举条目是否包含
完整的"代码契约"小节(8 项必填字段),并核验 A.3 数据表枚举字段 COMMENT
是否反向引用枚举类。

输出:
- 文本模式: 结构化检查报告
- --json 模式: JSON 报告供 Quality Review Agent 解析

退出码:
- 0: 全部通过
- 1: 有未通过项
- 2: 输入错误

用法:
  python check_enum_contract.py <设计文档路径>
  python check_enum_contract.py <设计目录>
  python check_enum_contract.py <设计文档路径> --json
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# 注:「后端文件路径」是 output-module-examples.md A.4.3 代码契约表的列名,
# 「后端枚举类文件路径」是 quality-review-checklist.md 检查项 11（= SKILL.md 自检 12，
# 两套编号是不同清单、不可换算）/
# stack-java-spring.md 的写法 —— 两种表述在本 SKILL 文档族中并存,均须识别,
# 否则按 checklist 措辞写的设计会被误判为"缺字段"。前端侧同理。
CONTRACT_FIELD_PATTERNS = [
    ("backend_class_name", r"后端枚举类名"),
    ("backend_file_path", r"后端(?:枚举类)?文件路径"),
    ("frontend_class_name", r"前端枚举(?:/常量)?类名"),
    ("frontend_file_path", r"前端(?:枚举(?:/常量)?类)?文件路径"),
    ("frontend_definition", r"前端定义方式"),
    ("db_mapping", r"数据库映射(?:方式)?"),
    ("orm_reference", r"Mapper/?ORM\s*引用"),
    ("front_back_alignment", r"前后端\s*code/?label\s*对齐"),
]

# A.4 条目标题。canonical 形态见 output-module-examples.md A.4.3:
#   `### {字典/枚举名称} ({类型: 枚举 | 字典 | 混合})`
# 该模板的「名称」占位在真实设计里通常是**中文**(订单状态 / 行业分类 / 用户类型,
# 见 A.4.2 的全部示例)。原实现要求名称必须以 ASCII 字母开头,中文命名的条目**一个都匹配不上**
# → `枚举条目总数` 恒为 0 → 8 项代码契约(Critical)检查恒不执行(空转)。
# 故形态①放开名称字符集,只以「括号内含 枚举/字典/混合」为锚;形态②保留原 ASCII 名 + 描述
# (无类型括号)的写法,不丢既有覆盖。
ENUM_HEADING_PATTERN = re.compile(
    r"^(#{2,4})[ \t]+"
    r"(?:"
    # 形态①:任意名称(中/英/混合) + (枚举|字典|混合) 类型括号,半角全角均可
    r"(?P<named>[^\n(（]*?)[ \t]*[(（][^)）\n]*?(?:枚举|字典|混合)[^)）\n]*?[)）][ \t]*"
    r"|"
    # 形态②:ASCII 名 + 描述,无类型括号(如 `### OrderStatusEnum 订单状态`)
    r"(?P<ascii>[A-Za-z][A-Za-z0-9_]*(?:Enum)?)[ \t]+[^\n]*?"
    r")$",
    re.MULTILINE,
)
A3_ENUM_FIELD_PATTERN = re.compile(
    # 长度括号可选:既匹配 `status TINYINT(1) ... COMMENT '...'` 也匹配无括号的 `status TINYINT NOT NULL COMMENT '...'`
    # ★列名的引号包裹可选(MySQL 反引号 / ANSI 双引号 / SQL Server 方括号):
    #   本 SKILL 自家 canonical DDL 写的就是 `` `gender` TINYINT ... `` 这种反引号形态,
    #   原先 `^\s*(\w+)` 在反引号处就断了 —— A.3 里**所有**规范写法的枚举列都扫不到,
    #   反向引用率只统计到零星未加引号的列,报出来的百分比是假的。
    r"^\s*[`\"\[]?(\w+)[`\"\]]?\s+"
    r"(?:TINYINT|SMALLINT|INT|BIGINT|VARCHAR|CHAR)(?:\s*\([^)]*\))?.*?COMMENT\s+'([^']*)'",
    re.MULTILINE | re.IGNORECASE,
)
# A.3 字段 COMMENT 的「反向引用枚举类」写法。本 SKILL 文档族里并存四种形态,必须全认——
# 原实现只认前两种,导致 canonical 模板自己的写法(output-module-examples.md A.3 DDL 里的
# `COMMENT '性别:...(参考 A.4 GenderEnum)'`)匹配不上 → 反向引用率恒报 0.0%,
# QR Agent 会照着这个假数据去要求"补引用",而设计里其实早就写了。
ENUM_REF_PATTERN = re.compile(
    # ① 参考 OrderStatusEnum  ② 参考 A.4 GenderEnum  ③ 参考 A.4 > OrderStatusEnum
    r"参考\s+(?:A\.4\s*>?\s*)?(\w+Enum)\b"
    # ④ 参考 A.4 > UserStatus / 参考 07_订单域枚举 > OrderStatus(拆分模式跨文档短引用)
    r"|参考\s+[^\s>]+\s*>\s*(\w+)"
    # ⑤ 参考 A.4 OrderStatus(索引里的短引用,无 Enum 后缀、无 `>`)
    r"|参考\s+A\.4\s+([A-Za-z]\w*)"
)


def find_md_files(target: Path) -> List[Path]:
    if target.is_file():
        return [target] if target.suffix == ".md" else []
    if target.is_dir():
        return sorted(target.rglob("*.md"))
    return []


def extract_a4_section(text: str) -> str:
    """Extract content under A.4 / 字典与枚举 / 字典/枚举定义 heading."""
    pattern = re.compile(
        r"^#{2,4}\s+(?:A\.4|##? A\.4|.*字典.*枚举.*|.*枚举.*字典.*).*$",
        re.MULTILINE,
    )
    match = pattern.search(text)
    if not match:
        return ""
    start = match.end()
    next_section = re.search(r"^#{2,3}\s+(?:A\.5|B\.|C\.|D\.|Module\s+B)", text[start:], re.MULTILINE)
    return text[start : start + next_section.start()] if next_section else text[start:]


def split_enum_blocks(a4_text: str) -> List[Tuple[str, str]]:
    """Split A.4 content into enum blocks. Returns [(name, body)]."""
    blocks: List[Tuple[str, str]] = []
    matches = list(ENUM_HEADING_PATTERN.finditer(a4_text))
    for i, m in enumerate(matches):
        name = (m.group("named") or m.group("ascii") or "").strip()
        if not name or name in {"A", "PRD", "Module"}:
            continue
        # 跳过模板占位标题(如 `### {字典/枚举名称} ({类型: 枚举 | 字典 | 混合})`),
        # 只统计真实设计条目。
        if "{" in name or "}" in name:
            continue
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(a4_text)
        body = a4_text[start:end]
        if "code" in body.lower() and ("label" in body.lower() or "显示文本" in body):
            blocks.append((name, body))
    return blocks


def check_contract_section(block_body: str) -> Dict[str, bool]:
    """Check whether the enum block has all 8 contract fields."""
    contract_match = re.search(
        r"\*?\*?代码契约[^\n]*\n([\s\S]+?)(?=\n#{2,5}\s|\n\*\*[^代]|\Z)",
        block_body,
    )
    contract_text = contract_match.group(1) if contract_match else block_body
    return {
        key: bool(re.search(pat, contract_text))
        for key, pat in CONTRACT_FIELD_PATTERNS
    }


def check_a3_enum_comment_refs(text: str) -> List[Dict]:
    """Find A.3 enum fields and check if their COMMENT references an Enum class."""
    findings = []
    for m in A3_ENUM_FIELD_PATTERN.finditer(text):
        field_name = m.group(1)
        comment = m.group(2)
        lname = field_name.lower()
        if lname in {"id", "version", "deleted"}:
            continue
        # SKILL.md 自检 12(j)（= checklist 检查项 11）步骤 4 举的正是 `status`/`type`/`category`
        # 这几个**裸名**;原实现只匹配 `_status`/`Status` 等带前缀形态,导致最常见的裸名字段
        # 被整体漏检(反向引用率恒为 N/A)。此处同时覆盖裸名与带前缀两种形态。
        is_enum_field = (
            lname in {"status", "type", "category"}
            or lname.endswith(("_status", "_type", "_category"))
            or field_name.endswith(("Status", "Type", "Category"))
        )
        if is_enum_field:
            has_ref = bool(ENUM_REF_PATTERN.search(comment))
            findings.append(
                {"field": field_name, "comment": comment, "references_enum": has_ref}
            )
    return findings


def analyze_file(md_file: Path) -> Dict:
    text = md_file.read_text(encoding="utf-8", errors="replace")
    a4 = extract_a4_section(text)
    if not a4:
        return {"file": str(md_file), "has_a4": False, "enums": [], "a3_findings": []}
    blocks = split_enum_blocks(a4)
    enum_results = []
    for name, body in blocks:
        contract = check_contract_section(body)
        missing = [k for k, v in contract.items() if not v]
        enum_results.append(
            {
                "name": name,
                "contract_fields": contract,
                "missing_fields": missing,
                "passed": not missing,
            }
        )
    return {
        "file": str(md_file),
        "has_a4": True,
        "enums": enum_results,
        "a3_findings": check_a3_enum_comment_refs(text),
    }


def aggregate(file_results: List[Dict]) -> Dict:
    total = sum(len(r["enums"]) for r in file_results)
    passed = sum(sum(1 for e in r["enums"] if e["passed"]) for r in file_results)
    a3_total = sum(len(r["a3_findings"]) for r in file_results)
    a3_with_ref = sum(
        sum(1 for f in r["a3_findings"] if f["references_enum"]) for r in file_results
    )
    return {
        "total_enums": total,
        "passed_enums": passed,
        "failed_enums": total - passed,
        "pass_rate": f"{(passed / total * 100):.1f}%" if total else "N/A",
        "a3_enum_fields_total": a3_total,
        "a3_enum_fields_with_ref": a3_with_ref,
        "a3_ref_rate": f"{(a3_with_ref / a3_total * 100):.1f}%" if a3_total else "N/A",
    }


def print_text_report(file_results: List[Dict], summary: Dict) -> None:
    print("=" * 78)
    print("A.4 字典/枚举代码契约合规扫描报告")
    print("=" * 78)
    print(f"\n枚举条目总数: {summary['total_enums']}")
    print(f"  通过: {summary['passed_enums']}")
    print(f"  未通过: {summary['failed_enums']}")
    print(f"  通过率: {summary['pass_rate']}")
    print(f"\nA.3 枚举字段总数: {summary['a3_enum_fields_total']}")
    print(f"  COMMENT 已引用枚举类: {summary['a3_enum_fields_with_ref']}")
    print(f"  反向引用率: {summary['a3_ref_rate']}")

    for r in file_results:
        if not r["has_a4"]:
            continue
        print(f"\n文件: {r['file']}")
        for e in r["enums"]:
            status = "✅" if e["passed"] else "❌"
            print(f"  {status} {e['name']}")
            if e["missing_fields"]:
                print(f"     缺失字段: {', '.join(e['missing_fields'])}")
        for f in r["a3_findings"]:
            if not f["references_enum"]:
                print(f"  ⚠️  A.3 字段 {f['field']} COMMENT 未引用枚举类: '{f['comment'][:60]}...'")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="A.4 字典/枚举代码契约合规扫描(8 项必填字段 + A.3 反向引用)"
    )
    parser.add_argument("path", help="详细设计文档路径或目录")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
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

    return 0 if summary["failed_enums"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
