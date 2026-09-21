#!/usr/bin/env python3
"""索引列 NOT NULL 强制检查脚本(对应 dev-logic-architect 维度 21)

扫描详细设计文档中的 SQL DDL,提取所有索引(普通/唯一/联合/主键)涉及的列,
核验每列是否 NOT NULL 且有 DEFAULT 哨兵值。

退出码:
  0  全部通过
  1  存在普通索引列允许 NULL / 索引列缺 DEFAULT
     **或** 唯一索引/联合索引列允许 NULL(强制不通过,MySQL NULL!=NULL 陷阱)
     ⚠️ 该档曾单用退出码 2,与全仓统一约定「2 = 入参错」撞码——调用方按约定把 2 当
        入参错「修正参数后重跑、不计维度失败」,就会把这条**强制不通过**静默放行(假绿)。
        已并入 1;分档改从 --json 读(见下)。严重度不占退出码,见 CLAUDE.md 全仓约定。
        分档:--json 顶层为结果数组,`violations[].severity` 为 2 即「强制不通过」档、1 为警告。
  2  输入错误(路径不存在 / 无 .md 文件)——非维度违规,修正参数后重跑

用法:
  python check_index_not_null.py <设计文档路径>
  python check_index_not_null.py <设计文档目录>
  python check_index_not_null.py <路径> --json

输入接受单文件(.md)或目录(批量加载所有 .md)。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# SQL 代码块
SQL_BLOCK_RE = re.compile(r"```sql\s*\n([\s\S]*?)```", re.IGNORECASE)

# CREATE TABLE 表头(仅定位表名与表体起始括号;表体改用括号配对提取)
CREATE_TABLE_HEAD_RE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"\[]?(\w+)[`\"\]]?\s*\(",
    re.IGNORECASE,
)


def iter_create_tables(sql_text):
    """逐表产出 (表名, 表体, CREATE 起始偏移)。

    表体用括号配对(并跳过引号内字符)定位真正的结束括号,避免列内
    `VARCHAR(20) COMMENT '...'` 这类「) 紧跟 COMMENT」把表体提前截断——
    旧的非贪婪正则会在第一个「) 紧跟 COMMENT」处收尾,漏掉其后所有字段与索引,
    使维度检查静默失效(可空列 + 行内 COMMENT 是最常见的触发写法)。
    """
    for m in CREATE_TABLE_HEAD_RE.finditer(sql_text):
        name = m.group(1)
        open_idx = m.end() - 1  # 表体起始 '(' 下标
        depth = 0
        quote = None
        for j in range(open_idx, len(sql_text)):
            c = sql_text[j]
            if quote is not None:
                if c == quote:
                    quote = None
                continue
            if c in ("'", '"', "`"):
                quote = c
            elif c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    yield name, sql_text[open_idx + 1:j], m.start()
                    break

# 索引声明匹配
PRIMARY_KEY_INLINE_RE = re.compile(r"\bPRIMARY\s+KEY\b", re.IGNORECASE)
PRIMARY_KEY_TABLE_RE = re.compile(
    r"PRIMARY\s+KEY\s*\(([^)]+)\)", re.IGNORECASE
)
UNIQUE_KEY_RE = re.compile(
    r"UNIQUE\s+(?:KEY|INDEX)\s+(?:`?\w+`?\s+)?\(([^)]+)\)", re.IGNORECASE
)
UNIQUE_INLINE_RE = re.compile(
    r"UNIQUE\s*\(([^)]+)\)", re.IGNORECASE
)
NORMAL_KEY_RE = re.compile(
    r"^\s*(?:KEY|INDEX)\s+(?:`?\w+`?\s+)?\(([^)]+)\)", re.IGNORECASE | re.MULTILINE
)
# 表外的 CREATE INDEX
CREATE_INDEX_RE = re.compile(
    r"CREATE\s+(UNIQUE\s+)?INDEX\s+`?\w+`?\s+ON\s+`?(\w+)`?\s*\(([^)]+)\)",
    re.IGNORECASE,
)

# 时间戳/自增等免除显式 DEFAULT 的关键字
EXEMPT_DEFAULT_KEYWORDS = ["AUTO_INCREMENT", "CURRENT_TIMESTAMP", "GENERATED ALWAYS"]


def find_md_files(path: Path) -> List[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(path.rglob("*.md"))
    return []


def extract_create_tables(text: str) -> List[Tuple[str, str, int]]:
    """从全文提取所有 CREATE TABLE 块: (table_name, body, start_line)"""
    tables: List[Tuple[str, str, int]] = []
    for m in SQL_BLOCK_RE.finditer(text):
        sql = m.group(1)
        sql_start_line = text[: m.start()].count("\n") + 2
        for table_name, body, head_start in iter_create_tables(sql):
            line_in_sql = sql[:head_start].count("\n")
            tables.append((table_name, body, sql_start_line + line_in_sql))
    return tables


def parse_columns(body: str) -> Dict[str, Dict]:
    """解析表体,返回 {列名: {nullable, has_default, comment, raw_line}}"""
    columns: Dict[str, Dict] = {}
    # 按逗号 + 换行分行,但要注意括号内的逗号不切分
    depth = 0
    current = []
    parts: List[str] = []
    for ch in body:
        if ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        parts.append("".join(current).strip())

    for part in parts:
        stripped = part.strip().rstrip(",")
        if not stripped:
            continue
        # 跳过约束行(PRIMARY KEY/KEY/INDEX/UNIQUE/CONSTRAINT/FOREIGN)
        if re.match(
            r"^\s*(?:PRIMARY\s+KEY|UNIQUE(?:\s+KEY|\s+INDEX)?|KEY|INDEX|CONSTRAINT|FOREIGN|FULLTEXT|SPATIAL)\b",
            stripped,
            re.IGNORECASE,
        ):
            continue
        col_match = re.match(r"^\s*[`\"\[]?(\w+)[`\"\]]?\s+([\w()]+)", stripped)
        if not col_match:
            continue
        col_name = col_match.group(1)
        upper = stripped.upper()
        # NULL 性
        is_not_null = bool(re.search(r"\bNOT\s+NULL\b", stripped, re.IGNORECASE))
        # MySQL 默认: 未声明 NOT NULL 视为允许 NULL
        nullable = not is_not_null
        # DEFAULT
        has_default = bool(re.search(r"\bDEFAULT\b", stripped, re.IGNORECASE))
        # 是否豁免(AUTO_INCREMENT / 列定义为主键自增)
        is_exempt = any(kw in upper for kw in EXEMPT_DEFAULT_KEYWORDS)
        # 内联主键
        is_inline_pk = bool(PRIMARY_KEY_INLINE_RE.search(stripped))
        # 关于 inline pk: PRIMARY KEY 隐含 NOT NULL
        if is_inline_pk:
            nullable = False
        # COMMENT
        comment_m = re.search(r"COMMENT\s+['\"]([^'\"]*)['\"]", stripped)
        comment = comment_m.group(1) if comment_m else ""

        columns[col_name] = {
            "name": col_name,
            "nullable": nullable,
            "has_default": has_default,
            "is_exempt": is_exempt,
            "is_inline_pk": is_inline_pk,
            "comment": comment,
            "raw": stripped[:200],
        }
    return columns


def extract_indexes(body: str, table_name: str) -> List[Dict]:
    """从表体提取所有索引声明"""
    indexes: List[Dict] = []
    # 行内主键(单列)
    for line in body.splitlines():
        col_match = re.match(r"^\s*[`\"\[]?(\w+)[`\"\]]?\s+\w", line)
        if col_match and PRIMARY_KEY_INLINE_RE.search(line):
            indexes.append({
                "name": "PRIMARY",
                "type": "primary",
                "columns": [col_match.group(1)],
            })
    # 表级主键
    for m in PRIMARY_KEY_TABLE_RE.finditer(body):
        cols = [c.strip().strip("`\"[]") for c in m.group(1).split(",")]
        indexes.append({"name": "PRIMARY", "type": "primary", "columns": cols})
    # 唯一键
    for m in UNIQUE_KEY_RE.finditer(body):
        cols = [c.strip().strip("`\"[]") for c in m.group(1).split(",")]
        # 名字
        full = m.group(0)
        name_m = re.search(r"UNIQUE\s+(?:KEY|INDEX)\s+`?(\w+)`?", full, re.IGNORECASE)
        name = name_m.group(1) if name_m else "UNIQUE"
        indexes.append({"name": name, "type": "unique", "columns": cols})
    # 普通 KEY/INDEX (排除 UNIQUE KEY)
    for m in NORMAL_KEY_RE.finditer(body):
        # 排除 PRIMARY KEY 和 UNIQUE KEY
        line_start = body.rfind("\n", 0, m.start()) + 1
        line_text = body[line_start: m.end()]
        if re.search(r"\b(PRIMARY|UNIQUE|FOREIGN)\b", line_text, re.IGNORECASE):
            continue
        cols = [c.strip().strip("`\"[]") for c in m.group(1).split(",")]
        name_m = re.search(r"(?:KEY|INDEX)\s+`?(\w+)`?", line_text, re.IGNORECASE)
        name = name_m.group(1) if name_m else "INDEX"
        indexes.append({"name": name, "type": "index", "columns": cols})
    return indexes


def extract_external_indexes(text: str) -> List[Dict]:
    """提取 CREATE INDEX 语句"""
    indexes: List[Dict] = []
    for m in CREATE_INDEX_RE.finditer(text):
        is_unique = bool(m.group(1))
        table = m.group(2)
        cols = [c.strip().strip("`\"[]") for c in m.group(3).split(",")]
        # 列名可能带 (length) 后缀,去掉
        cols = [re.sub(r"\(\d+\)$", "", c) for c in cols]
        indexes.append({
            "name": "EXTERNAL_INDEX",
            "type": "unique" if is_unique else "index",
            "columns": cols,
            "table": table,
        })
    return indexes


def analyze_table(table_name: str, body: str) -> List[Dict]:
    """分析单张表,返回违规列表"""
    columns = parse_columns(body)
    indexes = extract_indexes(body, table_name)

    violations: List[Dict] = []
    for idx in indexes:
        for col_name in idx["columns"]:
            # 列名可能带 (长度) 后缀
            col_name_clean = re.sub(r"\(\d+\)$", "", col_name).strip()
            col = columns.get(col_name_clean)
            if not col:
                # 列未在解析中找到,跳过(可能是注释或解析失败)
                continue
            # 主键单列内联且 AUTO_INCREMENT 直接通过
            if col["is_exempt"] and col["is_inline_pk"]:
                continue
            # 检查 NOT NULL
            if col["nullable"]:
                severity = (
                    2 if idx["type"] in ("unique", "primary") or len(idx["columns"]) > 1
                    else 1
                )
                violations.append({
                    "table": table_name,
                    "index_name": idx["name"],
                    "index_type": idx["type"],
                    "is_composite": len(idx["columns"]) > 1,
                    "column": col_name_clean,
                    "issue": "允许 NULL",
                    "severity": severity,
                })
                continue
            # NOT NULL 但缺 DEFAULT(豁免: AUTO_INCREMENT / CURRENT_TIMESTAMP / inline PK)
            # ⚠️ 主键列一律免除，不限 AUTO_INCREMENT：检查项 21 的口径是「除时间戳/自增/**主键 ID 类型**
            #    默认免除」，而雪花 ID / UUID 主键（`id BIGINT PRIMARY KEY`，无 AUTO_INCREMENT）同样
            #    必须由应用显式赋值、给 DEFAULT 反而有害。此前只认 AUTO_INCREMENT，导致本 SKILL 自家
            #    A.4 字典表示例被自家硬门判违规（假红灯）。
            if idx["type"] == "primary":
                continue
            if not col["has_default"] and not col["is_exempt"]:
                violations.append({
                    "table": table_name,
                    "index_name": idx["name"],
                    "index_type": idx["type"],
                    "is_composite": len(idx["columns"]) > 1,
                    "column": col_name_clean,
                    "issue": "NOT NULL 但缺 DEFAULT 哨兵值",
                    "severity": 1,
                })
    return violations


def analyze_file(path: Path, root: Path) -> Dict:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    try:  # Python 3.8 兼容:不用 3.9+ 的 is_relative_to
        rel = str(path.relative_to(root))
    except ValueError:
        rel = str(path)

    all_violations: List[Dict] = []
    table_count = 0
    index_count = 0

    # 收集所有 CREATE TABLE 的列定义,供表外 CREATE INDEX 复用
    table_columns: Dict[str, Dict[str, Dict]] = {}

    for table_name, body, _ in extract_create_tables(text):
        table_count += 1
        cols = parse_columns(body)
        table_columns[table_name] = cols
        violations = analyze_table(table_name, body)
        all_violations.extend(violations)
        index_count += len(extract_indexes(body, table_name))

    # 处理表外 CREATE INDEX / CREATE UNIQUE INDEX
    for ext_idx in extract_external_indexes(text):
        index_count += 1
        table = ext_idx.get("table")
        cols_def = table_columns.get(table)
        if not cols_def:
            continue
        for col_name in ext_idx["columns"]:
            col_name_clean = re.sub(r"\(\d+\)$", "", col_name).strip()
            col = cols_def.get(col_name_clean)
            if not col:
                continue
            if col["is_exempt"] and col["is_inline_pk"]:
                continue
            if col["nullable"]:
                severity = (
                    2 if ext_idx["type"] == "unique" or len(ext_idx["columns"]) > 1
                    else 1
                )
                all_violations.append({
                    "table": table,
                    "index_name": "EXTERNAL_INDEX",
                    "index_type": ext_idx["type"],
                    "is_composite": len(ext_idx["columns"]) > 1,
                    "column": col_name_clean,
                    "issue": "允许 NULL(表外 CREATE INDEX)",
                    "severity": severity,
                })
                continue
            if not col["has_default"] and not col["is_exempt"]:
                all_violations.append({
                    "table": table,
                    "index_name": "EXTERNAL_INDEX",
                    "index_type": ext_idx["type"],
                    "is_composite": len(ext_idx["columns"]) > 1,
                    "column": col_name_clean,
                    "issue": "NOT NULL 但缺 DEFAULT 哨兵值(表外 CREATE INDEX)",
                    "severity": 1,
                })

    return {
        "file": rel,
        "table_count": table_count,
        "index_count": index_count,
        "violations": all_violations,
    }


def render_text(results: List[Dict]) -> str:
    out: List[str] = []
    out.append("=== 索引列 NOT NULL 强制检查(维度 21) ===")

    total_tables = sum(r["table_count"] for r in results)
    total_indexes = sum(r["index_count"] for r in results)
    all_violations = [v for r in results for v in r["violations"]]
    critical = [v for v in all_violations if v["severity"] == 2]
    warning = [v for v in all_violations if v["severity"] == 1]

    out.append(f"\n📊 扫描 {len(results)} 个文件 / {total_tables} 张表 / {total_indexes} 个索引")
    out.append(f"  - 🔴 唯一索引/联合索引列允许 NULL: {len(critical)}")
    out.append(f"  - 🟡 普通索引列允许 NULL 或缺 DEFAULT: {len(warning)}")

    if critical:
        out.append("\n🔴 强制不通过 — 唯一索引/联合索引列允许 NULL(MySQL NULL!=NULL 陷阱):")
        for v in critical:
            composite = "(联合)" if v["is_composite"] else ""
            out.append(
                f"  - {v['table']}.{v['column']}  "
                f"[{v['index_type']} {composite} {v['index_name']}]  {v['issue']}"
            )

    if warning:
        out.append("\n🟡 普通索引列违规:")
        for v in warning:
            out.append(
                f"  - {v['table']}.{v['column']}  "
                f"[{v['index_type']} {v['index_name']}]  {v['issue']}"
            )

    if not all_violations:
        out.append("\n✅ 全部通过")

    out.append("\n💡 修复指引:")
    out.append("  - 索引列改为 NOT NULL + DEFAULT 哨兵值")
    out.append("    (空字符串 '' / 0 / -1 / 'N/A' / '9999-12-31',按列类型选)")
    out.append("  - 业务语义可空但被强制 NOT NULL 的列,COMMENT 标注'索引列,空值用 X 表示'")
    out.append("  - 时间戳类索引列可用 DEFAULT CURRENT_TIMESTAMP,自增主键用 AUTO_INCREMENT")
    return "\n".join(out)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
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

    all_violations = [v for r in results for v in r["violations"]]
    has_critical = any(v["severity"] == 2 for v in all_violations)
    has_warning = any(v["severity"] == 1 for v in all_violations)

    if has_critical:
        return 1  # 曾为 2,与入参错撞码(见 docstring),已并入 1
    if has_warning:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
