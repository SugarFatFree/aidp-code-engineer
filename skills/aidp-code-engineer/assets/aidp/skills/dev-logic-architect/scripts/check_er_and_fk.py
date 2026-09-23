#!/usr/bin/env python3
"""ER 关系图与外键约束检查脚本(对应 dev-logic-architect 维度 20)

扫描详细设计文档,验证:
1. A.3 章节(单文件)或数据域子文档(多文件)是否有 Mermaid erDiagram
2. DDL 中是否含 FOREIGN KEY / REFERENCES 约束(强制不通过)
3. 关联字段(_id 后缀,主键 id 除外)的 COMMENT 是否标注关联目标
4. 多文件模式下主文档是否有跨域全局 ER 图

退出码:
  0  全部通过
  1  存在缺失(ER 图缺失 / COMMENT 关联标注缺失)
     **或** 存在 FOREIGN KEY/REFERENCES 约束(强制不通过)
     ⚠️ 该档曾单用退出码 2,与全仓统一约定「2 = 入参错」撞码——调用方按约定把 2 当
        入参错「修正参数后重跑、不计维度失败」,就会把这条**强制不通过**静默放行(假绿)。
        已并入 1;分档改从 --json 读(见下)。严重度不占退出码,见 CLAUDE.md 全仓约定。
        分档:--json 顶层为结果数组,每项 `foreign_key_hits` 非空即「FK 强制不通过」档。
  2  输入错误(路径不存在 / 无 .md 文件)——非维度违规,修正参数后重跑

用法:
  python check_er_and_fk.py <设计文档路径>
  python check_er_and_fk.py <设计文档目录>
  python check_er_and_fk.py <路径> --json

输入接受单文件(.md)或目录(批量加载所有 .md;含主文档时识别多文件模式)。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Mermaid erDiagram 代码块
ERDIAGRAM_RE = re.compile(r"```\s*mermaid\s*\n\s*erDiagram\b", re.IGNORECASE)

# SQL DDL 块
SQL_BLOCK_RE = re.compile(r"```sql\s*\n([\s\S]*?)```", re.IGNORECASE)

# CREATE TABLE
CREATE_TABLE_RE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"\[]?(\w+)[`\"\]]?\s*\(",
    re.IGNORECASE,
)

# FOREIGN KEY / REFERENCES 检测(排除 COMMENT 中的)
# 先剥离 COMMENT '...' 字符串,再扫描
FK_PATTERNS = [
    re.compile(r"\bFOREIGN\s+KEY\b", re.IGNORECASE),
    re.compile(r"\bREFERENCES\s+[`\"\[]?\w+[`\"\]]?\s*\(", re.IGNORECASE),
]

# 关联字段命名: 以 _id 结尾,且不是 id 本身
ASSOC_FIELD_RE = re.compile(
    r"^\s*[`\"\[]?(\w+_id)[`\"\]]?\s+(BIGINT|INT|CHAR|VARCHAR|UUID)\b",
    re.IGNORECASE | re.MULTILINE,
)

# 关联标注关键词(COMMENT 中需出现)
ASSOC_COMMENT_KEYWORDS = ["关联", "关联表", "外键", "对应", "→", "->", "FK"]

# 主文档识别(多文件模式)
MAIN_DOC_PATTERNS = [
    re.compile(r"00[_-].*总览", re.IGNORECASE),
    re.compile(r"00[_-]\w*主文档", re.IGNORECASE),
    re.compile(r"00[_-]index", re.IGNORECASE),
]
# 数据域子文档识别
DATA_DOMAIN_DOC_PATTERNS = [
    re.compile(r"\d+[_-].*(?:数据表|数据域|domain|entity)", re.IGNORECASE),
    re.compile(r"\d+[_-]A\.?3", re.IGNORECASE),
]


def find_md_files(path: Path) -> List[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(path.rglob("*.md"))
    return []


def is_main_doc(path: Path) -> bool:
    name = path.name
    return any(p.search(name) for p in MAIN_DOC_PATTERNS)


def is_data_domain_doc(path: Path) -> bool:
    name = path.name
    return any(p.search(name) for p in DATA_DOMAIN_DOC_PATTERNS)


def has_a3_section(text: str) -> bool:
    """单文件模式: 检测是否有 A.3 数据表章节"""
    return bool(re.search(r"^##?\s*A\.3\b|^##?\s*A3\b", text, re.MULTILINE))


def has_create_table(text: str) -> bool:
    return bool(CREATE_TABLE_RE.search(text))


def has_erdiagram(text: str) -> bool:
    return bool(ERDIAGRAM_RE.search(text))


def strip_comments(sql: str) -> str:
    """剥离 COMMENT '...' 子句的字符串内容,保留 COMMENT 关键字位置"""
    # 简单 strip: 把 ' ... ' 和 " ... " 之间的内容替换为占位符
    sql = re.sub(r"COMMENT\s+'[^']*'", "COMMENT ''", sql)
    sql = re.sub(r"COMMENT\s+\"[^\"]*\"", 'COMMENT ""', sql)
    sql = re.sub(r"--[^\n]*", "", sql)  # 单行注释
    sql = re.sub(r"/\*[\s\S]*?\*/", "", sql)  # 块注释
    return sql


def find_foreign_keys(text: str) -> List[Dict]:
    """从所有 SQL 代码块中查找 FOREIGN KEY / REFERENCES,返回命中位置"""
    findings: List[Dict] = []
    for m in SQL_BLOCK_RE.finditer(text):
        sql = m.group(1)
        clean = strip_comments(sql)
        block_start_line = text[: m.start()].count("\n") + 1
        for pat in FK_PATTERNS:
            for hit in pat.finditer(clean):
                # 行号(在 SQL 块内)
                line_in_block = clean[: hit.start()].count("\n")
                line = block_start_line + line_in_block + 1
                snippet = clean[max(0, hit.start() - 30): hit.end() + 30].strip()
                findings.append({
                    "type": pat.pattern,
                    "line": line,
                    "snippet": snippet,
                })
    return findings


def find_assoc_fields_without_comment(text: str) -> List[Dict]:
    """查找 _id 后缀字段,但 COMMENT 中无关联标注"""
    findings: List[Dict] = []
    for m in SQL_BLOCK_RE.finditer(text):
        sql = m.group(1)
        block_start_line = text[: m.start()].count("\n") + 1
        for line in sql.splitlines():
            stripped = line.strip()
            field_match = ASSOC_FIELD_RE.match(line)
            if not field_match:
                continue
            field_name = field_match.group(1)
            if field_name.lower() == "id":
                continue
            # 检查同行是否有 COMMENT + 关联关键词
            comment_match = re.search(r"COMMENT\s+['\"]([^'\"]*)['\"]", line)
            if not comment_match:
                findings.append({
                    "field": field_name,
                    "line_text": stripped[:150],
                    "issue": "字段无 COMMENT",
                })
                continue
            comment_text = comment_match.group(1)
            if not any(kw in comment_text for kw in ASSOC_COMMENT_KEYWORDS):
                findings.append({
                    "field": field_name,
                    "line_text": stripped[:150],
                    "issue": f"COMMENT 未含关联关键词(关联/外键/对应/→): '{comment_text}'",
                })
    return findings


def analyze_file(path: Path, root: Path) -> Dict:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    try:  # Python 3.8 兼容:不用 3.9+ 的 is_relative_to
        rel = str(path.relative_to(root))
    except ValueError:
        rel = str(path)

    has_tables = has_create_table(text)
    has_a3 = has_a3_section(text)
    is_main = is_main_doc(path)
    is_domain = is_data_domain_doc(path)
    er_present = has_erdiagram(text)

    fk_hits = find_foreign_keys(text)
    assoc_issues = find_assoc_fields_without_comment(text)

    needs_er = (has_a3 and has_tables) or is_domain or is_main

    issues: List[str] = []
    if needs_er and not er_present:
        if is_main:
            issues.append("主文档缺失跨域全局 Mermaid erDiagram")
        elif is_domain:
            issues.append("数据域子文档末尾缺失 Mermaid erDiagram")
        else:
            issues.append("A.3 章节缺失 Mermaid erDiagram")

    return {
        "file": rel,
        "is_main_doc": is_main,
        "is_data_domain_doc": is_domain,
        "has_a3": has_a3,
        "has_tables": has_tables,
        "has_erdiagram": er_present,
        "foreign_key_hits": fk_hits,
        "assoc_field_issues": assoc_issues,
        "missing_er": issues,
    }


def render_text(results: List[Dict]) -> str:
    out: List[str] = []
    out.append("=== ER 关系图与外键约束检查(维度 20) ===")

    fk_total = sum(len(r["foreign_key_hits"]) for r in results)
    er_missing = [r for r in results if r["missing_er"]]
    assoc_total = sum(len(r["assoc_field_issues"]) for r in results)

    out.append(f"\n📊 扫描 {len(results)} 个文件")
    out.append(f"  - 缺失 ER 图: {len(er_missing)}")
    out.append(f"  - DDL 含 FOREIGN KEY/REFERENCES: {fk_total}")
    out.append(f"  - 关联字段 COMMENT 缺失关联标注: {assoc_total}")

    if fk_total:
        out.append("\n🔴 强制不通过 — DDL 中 FOREIGN KEY/REFERENCES 约束:")
        for r in results:
            for h in r["foreign_key_hits"]:
                out.append(f"  - {r['file']}:{h['line']}  {h['snippet']}")

    if er_missing:
        out.append("\n🟡 ER 图缺失:")
        for r in er_missing:
            for i in r["missing_er"]:
                out.append(f"  - {r['file']}: {i}")

    if assoc_total:
        out.append("\n🟡 关联字段 COMMENT 缺失关联标注(仅展示前 20 条):")
        count = 0
        for r in results:
            for issue in r["assoc_field_issues"]:
                if count >= 20:
                    break
                out.append(f"  - {r['file']}  字段 {issue['field']}: {issue['issue']}")
                count += 1
            if count >= 20:
                break

    if not fk_total and not er_missing and not assoc_total:
        out.append("\n✅ 全部通过")

    return "\n".join(out)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", type=Path, help="设计文档路径(单文件或目录)")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    args = parser.parse_args(argv)

    if not args.path.exists():
        print(f"错误: 路径不存在 {args.path}", file=sys.stderr)
        return 2

    root = args.path if args.path.is_dir() else args.path.parent
    md_files = find_md_files(args.path)
    if not md_files:
        print("⚠️ 未发现任何 .md 文件", file=sys.stderr)
        return 2

    results: List[Dict] = []
    for f in md_files:
        r = analyze_file(f, root)
        if r:
            results.append(r)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(render_text(results))

    has_fk = any(r["foreign_key_hits"] for r in results)
    has_missing_er = any(r["missing_er"] for r in results)
    has_assoc = any(r["assoc_field_issues"] for r in results)

    if has_fk:
        return 1  # 曾为 2,与入参错撞码(见 docstring),已并入 1
    if has_missing_er or has_assoc:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
