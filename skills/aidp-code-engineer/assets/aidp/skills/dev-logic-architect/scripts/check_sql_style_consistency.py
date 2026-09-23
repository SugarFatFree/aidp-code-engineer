#!/usr/bin/env python3
"""历史 SQL 风格沿用核验脚本(对应 dev-logic-architect 维度 18)

扫描代码仓中的历史 SQL 文件,归纳 8 维度风格(命名/公共字段/主键/索引/字符集等),
再扫描本次设计文档,核验新表是否沿用同一风格。

退出码:
  0  无历史 SQL(无需检查) 或 全部沿用一致
  1  存在风格违规(Critical) **或** 设计文档缺"📜 历史 SQL 风格沿用说明"章节
        两者区分改从 --json 的 verification.has_history_note 读。
  2  输入错误(代码仓/设计文档路径不存在)——非维度违规,修正参数后重跑

用法:
  python check_sql_style_consistency.py <代码仓根目录> <设计文档路径>
  python check_sql_style_consistency.py <代码仓根目录> <设计文档路径> --json
  python check_sql_style_consistency.py <代码仓根目录> <设计文档路径> --history-only  # 仅归纳历史,不核验

设计文档接受单文件(.md)或目录(批量加载所有 .md)。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# ---------- 历史 SQL 检测 ----------
SQL_SCAN_PATTERNS = ["**/*.sql"]
SQL_SCAN_DIRS_HINT = ["migrations", "migration", "flyway", "liquibase", "sql", "db", "database", "scripts/sql"]
SQL_EXCLUDED_DIRS = {"node_modules", ".git", "dist", "build", "target", "out", "__pycache__", "vendor"}

CREATE_TABLE_RE = re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"\[]?(\w+)[`\"\]]?\s*\(", re.IGNORECASE)
# 公共审计字段候选词
AUDIT_FIELDS = {
    "create_time": "create_time/update_time 风格",
    "update_time": "create_time/update_time 风格",
    "created_at": "created_at/updated_at 风格",
    "updated_at": "created_at/updated_at 风格",
    "gmt_create": "gmt_create/gmt_modified 风格",
    "gmt_modified": "gmt_create/gmt_modified 风格",
    "create_by": "create_by/update_by 命名",
    "created_by": "created_by/updated_by 命名",
    "creator": "creator 命名",
    "deleted": "deleted 标记",
    "is_deleted": "is_deleted 标记",
    "del_flag": "del_flag 标记",
}
TABLE_PREFIXES = ["t_", "tb_", "biz_", "sys_", "ums_", "oms_", "pms_", "sms_", "esm_"]


def find_sql_files(root: Path) -> List[Path]:
    files: List[Path] = []
    if not root.exists():
        return files
    for path in root.rglob("*.sql"):
        if any(p in SQL_EXCLUDED_DIRS for p in path.parts):
            continue
        files.append(path)
    return files


# ---------- 风格归纳 ----------

def detect_naming_style(name: str) -> str:
    """识别 snake_case / camelCase / PascalCase"""
    if "_" in name and name.islower():
        return "snake_case"
    if name[0].isupper() and any(c.isupper() for c in name[1:]):
        return "PascalCase"
    if name[0].islower() and any(c.isupper() for c in name):
        return "camelCase"
    if name.islower():
        return "snake_case"  # 全小写无下划线,归为 snake
    return "unknown"


def detect_table_prefix(name: str) -> Optional[str]:
    lower = name.lower()
    for p in TABLE_PREFIXES:
        if lower.startswith(p):
            return p
    return None


def parse_table_body(create_stmt: str) -> Tuple[List[str], str, str, str, List[str]]:
    """从 CREATE TABLE 完整语句中提取: 字段名列表 + 字符集 + 排序规则 + 引擎 + 索引命名"""
    field_names: List[str] = []
    # 仅取括号内的部分
    m = re.search(r"\(([\s\S]*)\)\s*(?:ENGINE|COMMENT|;|$)", create_stmt, re.IGNORECASE)
    body = m.group(1) if m else create_stmt
    # 字段定义行(粗略: 行首是 `name` 或 name 后跟类型)
    for line in body.splitlines():
        s = line.strip().rstrip(",")
        if not s:
            continue
        # 跳过 PRIMARY KEY / KEY / INDEX / UNIQUE 等约束行
        if re.match(r"^(?:PRIMARY\s+KEY|UNIQUE\s+KEY|UNIQUE|KEY|INDEX|CONSTRAINT|FOREIGN)\b", s, re.IGNORECASE):
            continue
        fm = re.match(r"[`\"\[]?(\w+)[`\"\]]?\s+\w", s)
        if fm:
            field_names.append(fm.group(1))

    charset_m = re.search(r"CHARACTER\s+SET\s+(\w+)|CHARSET\s*=\s*(\w+)", create_stmt, re.IGNORECASE)
    charset = (charset_m.group(1) or charset_m.group(2)) if charset_m else ""
    collate_m = re.search(r"COLLATE\s*=?\s*(\w+)", create_stmt, re.IGNORECASE)
    collate = collate_m.group(1) if collate_m else ""
    engine_m = re.search(r"ENGINE\s*=\s*(\w+)", create_stmt, re.IGNORECASE)
    engine = engine_m.group(1) if engine_m else ""

    # 索引命名前缀
    index_names: List[str] = []
    for line in body.splitlines():
        s = line.strip()
        im = re.match(r"(?:UNIQUE\s+)?KEY\s+[`\"\[]?(\w+)[`\"\]]?", s, re.IGNORECASE)
        if im:
            index_names.append(im.group(1))

    return field_names, charset, collate, engine, index_names


def extract_create_statements(text: str) -> List[str]:
    """从 SQL 文本中粗略切分出每段 CREATE TABLE 语句(到 `;` 或下一个 CREATE)"""
    stmts: List[str] = []
    pos = 0
    while True:
        m = CREATE_TABLE_RE.search(text, pos)
        if not m:
            break
        start = m.start()
        # 找下一个分号或下一个 CREATE TABLE
        rest = text[start:]
        end_m = re.search(r";\s*$", rest, re.MULTILINE)
        if end_m:
            end = start + end_m.end()
        else:
            next_m = CREATE_TABLE_RE.search(text, m.end())
            end = next_m.start() if next_m else len(text)
        stmts.append(text[start:end])
        pos = end
    return stmts


def aggregate_history(sql_files: List[Path]) -> Dict:
    """从历史 SQL 文件聚合 8 维度风格"""
    table_naming_styles: Counter = Counter()
    field_naming_styles: Counter = Counter()
    prefixes: Counter = Counter()
    audit_field_styles: Counter = Counter()
    primary_key_patterns: Counter = Counter()
    index_prefixes: Counter = Counter()
    charsets: Counter = Counter()
    engines: Counter = Counter()
    table_count = 0

    for sf in sql_files:
        try:
            text = sf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for stmt in extract_create_statements(text):
            tm = CREATE_TABLE_RE.search(stmt)
            if not tm:
                continue
            table_name = tm.group(1)
            table_count += 1
            table_naming_styles[detect_naming_style(table_name)] += 1
            prefix = detect_table_prefix(table_name)
            if prefix:
                prefixes[prefix] += 1
            else:
                prefixes["(无前缀)"] += 1

            fields, charset, collate, engine, idxs = parse_table_body(stmt)
            for f in fields:
                field_naming_styles[detect_naming_style(f)] += 1
                if f in AUDIT_FIELDS:
                    audit_field_styles[AUDIT_FIELDS[f]] += 1

            # 主键: 检测 id 类型
            pkm = re.search(r"[`\"\[]?id[`\"\]]?\s+(BIGINT|INT|CHAR\(\d+\)|VARCHAR\(\d+\))\s+([^,]*)", stmt, re.IGNORECASE)
            if pkm:
                pk_type = pkm.group(1).upper()
                pk_attrs = pkm.group(2).upper()
                if "AUTO_INCREMENT" in pk_attrs:
                    primary_key_patterns[f"{pk_type} AUTO_INCREMENT(id)"] += 1
                else:
                    primary_key_patterns[f"{pk_type}(id)"] += 1

            for ix in idxs:
                ix_lower = ix.lower()
                for pre in ["idx_", "uk_", "fk_", "uniq_", "ix_", "key_"]:
                    if ix_lower.startswith(pre):
                        index_prefixes[pre] += 1
                        break
                else:
                    index_prefixes["(无前缀)"] += 1

            if charset:
                charsets[charset.lower()] += 1
            if engine:
                engines[engine.lower()] += 1

    def top(c: Counter) -> Optional[str]:
        return c.most_common(1)[0][0] if c else None

    return {
        "table_count": table_count,
        "table_naming_dominant": top(table_naming_styles),
        "table_naming_distribution": dict(table_naming_styles),
        "table_prefix_dominant": top(prefixes),
        "table_prefix_distribution": dict(prefixes),
        "field_naming_dominant": top(field_naming_styles),
        "field_naming_distribution": dict(field_naming_styles),
        "audit_field_style_dominant": top(audit_field_styles),
        "audit_field_style_distribution": dict(audit_field_styles),
        "primary_key_dominant": top(primary_key_patterns),
        "primary_key_distribution": dict(primary_key_patterns),
        "index_prefix_dominant": top(index_prefixes),
        "index_prefix_distribution": dict(index_prefixes),
        "charset_dominant": top(charsets),
        "engine_dominant": top(engines),
    }


# ---------- 设计文档核验 ----------

DESIGN_FENCE_RE = re.compile(r"```sql\s*\n([\s\S]*?)```", re.IGNORECASE)
HISTORY_NOTE_RE = re.compile(r"📜\s*历史\s*SQL\s*风格\s*沿用\s*说明")


def load_design_text(path: Path) -> str:
    if path.is_file():
        return path.read_text(encoding="utf-8", errors="replace")
    chunks: List[str] = []
    for md in sorted(path.rglob("*.md")):
        chunks.append(md.read_text(encoding="utf-8", errors="replace"))
    return "\n\n".join(chunks)


def verify_design(design_text: str, history: Dict) -> Dict:
    has_note = bool(HISTORY_NOTE_RE.search(design_text))
    new_stmts: List[str] = []
    for m in DESIGN_FENCE_RE.finditer(design_text):
        new_stmts.extend(extract_create_statements(m.group(1)))

    violations: List[Dict] = []
    new_summary = aggregate_history([])  # 默认空容器(无新增 SQL 时下方 render 仍引用)
    if new_stmts:
        # 把新语句当作"小型历史"内联聚合一次,得到新风格
        new_summary = _aggregate_inline(new_stmts)

    def cmp(dim: str, hist_key: str, new_key: str, label: str) -> None:
        h = history.get(hist_key)
        n = new_summary.get(new_key) if new_stmts else None
        if h and n and h != n:
            violations.append({
                "dimension": dim,
                "label": label,
                "history": h,
                "new": n,
            })

    cmp("18.1", "table_naming_dominant", "table_naming_dominant", "表名命名风格")
    cmp("18.1", "table_prefix_dominant", "table_prefix_dominant", "表名前缀")
    cmp("18.2", "field_naming_dominant", "field_naming_dominant", "字段命名风格")
    cmp("18.3", "audit_field_style_dominant", "audit_field_style_dominant", "公共审计字段命名")
    cmp("18.4", "primary_key_dominant", "primary_key_dominant", "主键风格")
    cmp("18.5", "index_prefix_dominant", "index_prefix_dominant", "索引命名前缀")
    cmp("18.6", "charset_dominant", "charset_dominant", "字符集")
    cmp("18.6", "engine_dominant", "engine_dominant", "存储引擎")

    return {
        "has_history_note": has_note,
        "new_table_count": new_summary.get("table_count", 0),
        "violations": violations,
        "new_summary": new_summary,
    }


def _aggregate_inline(stmts: List[str]) -> Dict:
    """直接对一批 CREATE TABLE 语句聚合(不读文件)"""
    table_naming_styles: Counter = Counter()
    field_naming_styles: Counter = Counter()
    prefixes: Counter = Counter()
    audit_field_styles: Counter = Counter()
    primary_key_patterns: Counter = Counter()
    index_prefixes: Counter = Counter()
    charsets: Counter = Counter()
    engines: Counter = Counter()
    table_count = 0
    for stmt in stmts:
        tm = CREATE_TABLE_RE.search(stmt)
        if not tm:
            continue
        table_name = tm.group(1)
        table_count += 1
        table_naming_styles[detect_naming_style(table_name)] += 1
        prefix = detect_table_prefix(table_name)
        prefixes[prefix or "(无前缀)"] += 1
        fields, charset, collate, engine, idxs = parse_table_body(stmt)
        for f in fields:
            field_naming_styles[detect_naming_style(f)] += 1
            if f in AUDIT_FIELDS:
                audit_field_styles[AUDIT_FIELDS[f]] += 1
        pkm = re.search(r"[`\"\[]?id[`\"\]]?\s+(BIGINT|INT|CHAR\(\d+\)|VARCHAR\(\d+\))\s+([^,]*)", stmt, re.IGNORECASE)
        if pkm:
            pk_type = pkm.group(1).upper()
            pk_attrs = pkm.group(2).upper()
            if "AUTO_INCREMENT" in pk_attrs:
                primary_key_patterns[f"{pk_type} AUTO_INCREMENT(id)"] += 1
            else:
                primary_key_patterns[f"{pk_type}(id)"] += 1
        for ix in idxs:
            ix_lower = ix.lower()
            for pre in ["idx_", "uk_", "fk_", "uniq_", "ix_", "key_"]:
                if ix_lower.startswith(pre):
                    index_prefixes[pre] += 1
                    break
            else:
                index_prefixes["(无前缀)"] += 1
        if charset:
            charsets[charset.lower()] += 1
        if engine:
            engines[engine.lower()] += 1

    def top(c: Counter) -> Optional[str]:
        return c.most_common(1)[0][0] if c else None

    return {
        "table_count": table_count,
        "table_naming_dominant": top(table_naming_styles),
        "table_prefix_dominant": top(prefixes),
        "field_naming_dominant": top(field_naming_styles),
        "audit_field_style_dominant": top(audit_field_styles),
        "primary_key_dominant": top(primary_key_patterns),
        "index_prefix_dominant": top(index_prefixes),
        "charset_dominant": top(charsets),
        "engine_dominant": top(engines),
    }


# ---------- 输出 ----------

def render_text(history: Dict, result: Dict) -> str:
    out: List[str] = []
    out.append("=== 历史 SQL 风格沿用核验(维度 18) ===")
    out.append(f"\n📊 历史归纳(共 {history['table_count']} 张表):")
    out.append(f"  表名命名: {history['table_naming_dominant']} ({history['table_naming_distribution']})")
    out.append(f"  表名前缀: {history['table_prefix_dominant']} ({history['table_prefix_distribution']})")
    out.append(f"  字段命名: {history['field_naming_dominant']}")
    out.append(f"  公共审计字段: {history['audit_field_style_dominant']}")
    out.append(f"  主键风格: {history['primary_key_dominant']}")
    out.append(f"  索引前缀: {history['index_prefix_dominant']}")
    out.append(f"  字符集: {history['charset_dominant']}")
    out.append(f"  引擎: {history['engine_dominant']}")

    out.append(f"\n📋 本次设计核验(新表 {result['new_table_count']} 张):")
    out.append(f"  📜 历史 SQL 风格沿用说明章节: {'✅ 存在' if result['has_history_note'] else '❌ 缺失'}")
    if not result["violations"]:
        out.append("  ✅ 所有维度沿用一致")
    else:
        out.append(f"  ❌ 风格违规: {len(result['violations'])} 项")
        for v in result["violations"]:
            out.append(f"    - [{v['dimension']}] {v['label']}: 历史={v['history']} vs 本次={v['new']}")
    return "\n".join(out)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("repo_root", type=Path, help="代码仓根目录(扫描历史 SQL)")
    parser.add_argument("design_path", type=Path, help="详细设计文档路径(.md 文件或目录)")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    parser.add_argument("--history-only", action="store_true", help="仅归纳历史,不核验设计")
    args = parser.parse_args(argv)

    if not args.repo_root.exists():
        print(f"错误: 代码仓目录不存在 {args.repo_root}", file=sys.stderr)
        return 2
    if not args.design_path.exists() and not args.history_only:
        print(f"错误: 设计文档不存在 {args.design_path}", file=sys.stderr)
        return 2

    sql_files = find_sql_files(args.repo_root)
    if not sql_files:
        msg = {"history_sql_found": False, "message": "无历史 SQL,跳过维度 18 检查"}
        if args.json:
            print(json.dumps(msg, ensure_ascii=False, indent=2))
        else:
            print("⚠️ 未发现历史 SQL(*.sql),按维度 18 例外处理,跳过检查")
        return 0

    history = aggregate_history(sql_files)
    history["history_sql_found"] = True
    scanned_rel = []  # Python 3.8 兼容:不用 3.9+ 的 is_relative_to
    for p in sql_files:
        try:
            scanned_rel.append(str(p.relative_to(args.repo_root)))
        except ValueError:
            scanned_rel.append(str(p))
    history["scanned_files"] = scanned_rel

    if args.history_only:
        if args.json:
            print(json.dumps(history, ensure_ascii=False, indent=2))
        else:
            print(render_text(history, {"has_history_note": False, "new_table_count": 0, "violations": [], "new_summary": {}}))
        return 0

    design_text = load_design_text(args.design_path)
    result = verify_design(design_text, history)

    if args.json:
        print(json.dumps({"history": history, "verification": result}, ensure_ascii=False, indent=2))
    else:
        print(render_text(history, result))

    if not result["has_history_note"]:
        # 曾用 2 表示本档,与「2 = 入参错」的全仓统一约定撞码 → 已并入 1(判错)。
        # 严重度分档改从 --json 的 verification.has_history_note 读,不再靠退出码区分。
        return 1
    if result["violations"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
