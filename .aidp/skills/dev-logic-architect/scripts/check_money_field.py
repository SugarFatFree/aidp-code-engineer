#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_money_field.py — 货币金额字段整数化合规扫描

对照 dev-logic-architect SKILL「💰 货币金额字段设计规则」与质量检查清单维度 17,
扫描详细设计文档(.md)中的 SQL DDL,识别疑似金额字段并核验:
  1. 类型必须是 BIGINT(或 64 位整数等价类型)
  2. COMMENT 必须含"单位:..."声明
  3. 严禁 FLOAT/DOUBLE/REAL 浮点类型
  4. DECIMAL/NUMERIC 视为"降级",需同章节内有降级理由文字

用法:
    python check_money_field.py <详细设计文档或目录> [--json]

仅依赖 Python 3.6+ 标准库。
"""

import argparse
import json
import re
import sys
from pathlib import Path

# 疑似金额字段识别(中英文关键词,与维度 17 检查项保持一致)
MONEY_COMMENT_KEYWORDS_CN = [
    "金额", "价格", "余额", "收入", "支出", "费用", "费率", "工资",
    "佣金", "折扣", "退款", "充值", "提现", "抵扣", "应付", "实付",
    "税", "补贴", "奖金", "保证金", "押金", "利息", "贷款",
]
MONEY_FIELD_KEYWORDS_EN = [
    "amount", "price", "balance", "cost", "fee", "salary", "discount",
    "refund", "payment", "total", "subtotal", "revenue", "profit",
    "tax", "bonus", "deposit", "interest", "loan", "charge", "commission",
]
# 字段名误报排除(明显非金额)
EXCLUDE_FIELD_PATTERNS = [
    re.compile(r"^(id|.*_id)$", re.IGNORECASE),
    re.compile(r"^count_.+|.+_count$", re.IGNORECASE),
    re.compile(r"^(create|update|delete)_(time|by|at)$", re.IGNORECASE),
]

# 整数类型(合规)
INTEGER_TYPES = {"BIGINT", "INT8", "LONG", "INT64", "NUMBER(19,0)", "NUMBER(19)"}
# 浮点类型(严禁)
FLOAT_TYPES = {"FLOAT", "DOUBLE", "REAL", "DOUBLE PRECISION"}
# 降级类型(需理由)
DECIMAL_TYPES_PATTERN = re.compile(r"^(DECIMAL|NUMERIC|NUMBER)\s*\(", re.IGNORECASE)
# 32 位整数(对金额不够,警告)
INT32_TYPES = {"INT", "INTEGER", "INT4", "MEDIUMINT", "SMALLINT", "TINYINT"}

UNIT_PATTERN = re.compile(r"单位\s*[:：]")

# Markdown 中 ```sql 代码块匹配
SQL_BLOCK_PATTERN = re.compile(
    r"```sql\s*\n(.*?)\n```",
    re.DOTALL | re.IGNORECASE,
)

# Markdown 字段表格匹配(如 | 字段名 | 类型 | 说明 |)
# 表头行至少含"字段"或"field"关键词,后续行为数据行
MD_TABLE_HEADER_PATTERN = re.compile(
    r"^\|[^|]*(?:字段|field|列名|column)[^|]*\|",
    re.IGNORECASE,
)

# CREATE TABLE 表头(仅定位表名与表体起始括号;表体改用括号配对提取)
CREATE_TABLE_HEAD_PATTERN = re.compile(
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
    for m in CREATE_TABLE_HEAD_PATTERN.finditer(sql_text):
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

# 字段定义行匹配:字段名 类型(...) 修饰 COMMENT '...'
FIELD_LINE_PATTERN = re.compile(
    r"^\s*[`\"]?(\w+)[`\"]?\s+"  # 字段名
    r"([A-Z][A-Z0-9_]*(?:\s*\([^)]*\))?(?:\s+UNSIGNED)?)"  # 类型
    r"(.*?)"  # 中间修饰
    r"(?:COMMENT\s+['\"]([^'\"]*)['\"])?"  # COMMENT
    r"\s*,?\s*$",
    re.IGNORECASE,
)


def is_excluded_field(field_name):
    for p in EXCLUDE_FIELD_PATTERNS:
        if p.match(field_name):
            return True
    return False


def _tokenize_field_name(field_name):
    """拆分 snake_case 与 camelCase 为小写词元,供整词匹配,避免子串误命中
    (如 fee∈coffee、tax∈syntax/taxonomy、cost∈costume)"""
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", field_name)  # camelCase → snake
    return [t for t in re.split(r"[_\s]+", s.lower()) if t]


def looks_like_money(field_name, comment):
    tokens = _tokenize_field_name(field_name)
    for kw in MONEY_FIELD_KEYWORDS_EN:
        if kw in tokens:  # 整词匹配,不再用子串(子串会把 coffee/syntax 误判为金额字段)
            if is_excluded_field(field_name):
                return False
            return True
    if comment:
        for kw in MONEY_COMMENT_KEYWORDS_CN:
            if kw in comment:
                if is_excluded_field(field_name):
                    return False
                return True
    return False


def classify_type(raw_type):
    t = raw_type.strip().upper()
    base = re.split(r"[\s(]", t, maxsplit=1)[0]
    if base in INTEGER_TYPES or t in INTEGER_TYPES:
        return "INTEGER_OK"
    if base in FLOAT_TYPES or t in FLOAT_TYPES:
        return "FLOAT_FORBIDDEN"
    if DECIMAL_TYPES_PATTERN.match(t):
        return "DECIMAL_NEEDS_REASON"
    if base in INT32_TYPES:
        return "INT32_RISK"
    return "UNKNOWN"


# 降级理由关键词。⚠️ 刻意**不含**「沿用 / 保持一致 / 兼容」这三个泛词：
#    核心原则 12 **强制要求** A.3 写「📜 历史 SQL 风格沿用说明」，其标准措辞必含它们，
#    于是任何合规设计文档都自带一张"金额降级通行证"——实测一份全文无任何金额降级理由、
#    只有历史 SQL 沿用说明的文档，DECIMAL 字段被判 0 问题、rc=0（假绿灯）。
#    要表达"沿用已有金额约定"请写「已有项目金额沿用 DECIMAL」等**金额语境共现**的措辞。
DOWNGRADE_KEYWORDS = ["遗留", "对接", "降级", "外部银行", "统计快照", "ISO 标准 2 位",
                      "已有表", "现有约定", "已有项目"]
# 金额**业务**语境词。⚠️ 刻意不含 DECIMAL / BIGINT —— 那是类型名，任何金额 DDL 里必然出现，
#    放进来会让「共现」条件形同虚设（实测：泛词只要落在表附近就通行，假绿灯照旧）。
MONEY_CTX_RE = re.compile(r"金额|money|amount|price|fee|balance|余额|价格|费用|单位\s*[:：]?\s*分",
                          re.IGNORECASE)
WEAK_KEYWORDS = ["沿用", "保持一致", "兼容"]


def has_downgrade_reason(file_text, table_name, field_name):
    """判断该字段是否已写明金额类型降级理由。

    ⚠️ 窗口必须**限定在该字段所属表的 DDL 段内**，不能用 file_text.find(field_name) 取全文首次
       出现——同名字段跨表串味：`rpt_snapshot.amount` 写了合法降级理由，`biz_order.amount`
       什么都没写，全文 find 命中前者的窗口，后者被判合规（实测 rc=0，假绿灯）。
       这与 check_lock_strategy.py 已踩过并写进注释的两个假绿灯同类，勿改回全文 find。
    """
    # 先把窗口收敛到该表的 DDL 段
    scope = file_text
    if table_name:
        tm = re.search(r"CREATE\s+TABLE\s+`?" + re.escape(str(table_name)) + r"`?",
                       file_text, re.IGNORECASE)
        if tm:
            nxt = re.search(r"CREATE\s+TABLE\s+", file_text[tm.end():], re.IGNORECASE)
            end = tm.end() + (nxt.start() if nxt else len(file_text) - tm.end())
            # ⚠️ 窗口起点回退到 DDL **上方最近的 markdown 标题行**，而不是固定字数。
            #    · 「不向前扩展」会误伤合规写法：checklist 检查项 17 明写降级理由可写在
            #      「该表所在**章节**」，而设计文档的常规排布正是「### rpt_daily_snapshot 表 /
            #      本表为统计快照，金额降级为 DECIMAL / ```sql CREATE TABLE …」——理由在 DDL 之上。
            #    · 「向前固定 300 字」又会跨到上一张表的说明段（跨表串味假绿灯）。
            #    回退到最近标题正好两头都对：同章节的说明覆盖得到，而上一张表的说明位于
            #    **它自己的标题之后、本标题之前**，被标题天然隔开。
            #    ⚠️ 用 MULTILINE 行首锚定，不要写成 rfind("\n#")——那样**文件首行就是标题**时
            #    （`### xxx 表` 在第 1 行，前面没有换行）匹配不到，窗口退化回"不向前扩展"。
            heads = [m.start() for m in re.finditer(r"^#{1,6}\s", file_text[:tm.start()], re.M)]
            start = heads[-1] if heads else 0
            scope = file_text[start: min(len(file_text), end + 400)]
    idx = scope.find(field_name)
    if idx < 0:
        return False
    window = scope[max(0, idx - 500): idx + 500]
    if any(k in window for k in DOWNGRADE_KEYWORDS):
        return True
    # 泛词须与金额业务词**同行**共现，避免被「历史 SQL 风格沿用说明」自我洗白。
    # 同行是必要的：整窗口共现太松——DDL 里本就有金额字段，说明段里本就有"沿用"，
    # 二者在窗口内必然同时存在，等于不设条件。
    for ln in window.splitlines():
        if any(k in ln for k in WEAK_KEYWORDS) and MONEY_CTX_RE.search(ln):
            return True
    return False


def scan_file(path):
    text = path.read_text(encoding="utf-8", errors="replace")
    issues = []
    money_fields = []

    # === 模式 1: 扫描 SQL DDL 代码块 ===
    for sql_match in SQL_BLOCK_PATTERN.finditer(text):
        sql = sql_match.group(1)
        for table_name, body, _ in iter_create_tables(sql):
            for raw_line in body.splitlines():
                line = raw_line.strip().rstrip(",")
                if not line or line.startswith("--") or line.upper().startswith(
                    ("PRIMARY KEY", "KEY ", "INDEX ", "UNIQUE", "CONSTRAINT", "FOREIGN")
                ):
                    continue
                m = FIELD_LINE_PATTERN.match(line)
                if not m:
                    continue
                field_name, raw_type, _modifiers, comment = m.groups()
                comment = comment or ""
                if not looks_like_money(field_name, comment):
                    continue

                category = classify_type(raw_type)
                has_unit = bool(UNIT_PATTERN.search(comment)) if comment else False
                entry = {
                    "file": str(path),
                    "table": table_name,
                    "field": field_name,
                    "type": raw_type.strip(),
                    "comment": comment,
                    "category": category,
                    "has_unit_declaration": has_unit,
                    "source": "DDL",
                }
                money_fields.append(entry)
                _check_entry(entry, text, table_name, field_name, issues)

    # === 模式 2: 扫描 Markdown 字段表格 ===
    _scan_markdown_tables(text, path, money_fields, issues)

    return money_fields, issues


def _check_entry(entry, text, table_name, field_name, issues):
    """对单个金额字段条目执行合规检查"""
    category = entry["category"]
    raw_type = entry["type"]
    has_unit = entry["has_unit_declaration"]

    if category == "FLOAT_FORBIDDEN":
        issues.append({
            **entry,
            "severity": "Critical",
            "rule": "禁止浮点类型存储金额",
            "hint": "改为 BIGINT 按最小货币单位存储",
        })
    elif category == "DECIMAL_NEEDS_REASON":
        if not has_downgrade_reason(text, table_name, field_name):
            issues.append({
                **entry,
                "severity": "Critical",
                "rule": "DECIMAL 金额字段需标注降级理由",
                "hint": "改为 BIGINT 单位:分;或在章节内显式标注降级理由(遗留系统/统计快照)",
            })
    elif category == "INT32_RISK":
        issues.append({
            **entry,
            "severity": "Important",
            "rule": "32 位整数金额字段有溢出风险",
            "hint": f"将 {raw_type} 改为 BIGINT",
        })
    elif category == "INTEGER_OK" and not has_unit:
        issues.append({
            **entry,
            "severity": "Important",
            "rule": "金额字段 COMMENT 缺单位声明",
            "hint": "COMMENT 增加 '单位:分(CNY)' 或 '单位:对应币种最小单位'",
        })


def _scan_markdown_tables(text, path, money_fields, issues):
    """扫描 Markdown 表格中的字段定义(如 | 字段名 | 类型 | 说明 |)"""
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not MD_TABLE_HEADER_PATTERN.search(line):
            i += 1
            continue
        # 找到表头行,解析列索引
        headers = [h.strip().lower() for h in line.split("|")]
        # 跳过分隔行
        if i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|$", lines[i + 1].strip()):
            i += 2
        else:
            i += 1
            continue
        # 确定列索引
        field_col = _find_col(headers, ["字段", "字段名", "field", "column", "列名"])
        type_col = _find_col(headers, ["类型", "type", "数据类型", "字段类型"])
        desc_col = _find_col(headers, ["说明", "描述", "备注", "comment", "description", "含义"])
        table_col = _find_col(headers, ["表名", "table", "所属表"])
        if field_col < 0 or type_col < 0:
            continue
        # 尝试从上文找表名
        context_table = _find_context_table(lines, i - 2)
        # 解析数据行
        while i < len(lines):
            row = lines[i]
            if not row.strip().startswith("|"):
                break
            cells = [c.strip() for c in row.split("|")]
            if len(cells) <= max(field_col, type_col):
                i += 1
                continue
            field_name = re.sub(r"[`\"]", "", cells[field_col]).strip()
            raw_type = re.sub(r"[`\"]", "", cells[type_col]).strip()
            comment = cells[desc_col] if desc_col >= 0 and desc_col < len(cells) else ""
            table_name = cells[table_col] if table_col >= 0 and table_col < len(cells) else context_table
            if not field_name or not raw_type:
                i += 1
                continue
            if not looks_like_money(field_name, comment):
                i += 1
                continue
            category = classify_type(raw_type)
            has_unit = bool(UNIT_PATTERN.search(comment)) if comment else False
            entry = {
                "file": str(path),
                "table": table_name or "(markdown表格)",
                "field": field_name,
                "type": raw_type,
                "comment": comment,
                "category": category,
                "has_unit_declaration": has_unit,
                "source": "MarkdownTable",
            }
            money_fields.append(entry)
            _check_entry(entry, text, table_name or "", field_name, issues)
            i += 1


def _find_col(headers, keywords):
    """在表头列表中找到包含关键词的列索引"""
    for idx, h in enumerate(headers):
        for kw in keywords:
            if kw in h:
                return idx
    return -1


def _find_context_table(lines, start_idx):
    """从表格上方 5 行内寻找表名(如 ### biz_order 表 或 ### biz_order)"""
    for j in range(max(0, start_idx - 5), start_idx + 1):
        m = re.search(r"(?:###?\s+)[`\"]?(\w+)[`\"]?\s*(?:表)?", lines[j])
        if m:
            return m.group(1)
    return ""


def iter_targets(target):
    p = Path(target)
    if p.is_file():
        yield p
        return
    if not p.is_dir():
        return
    for md in p.rglob("*.md"):
        if any(part.startswith(".") for part in md.parts):
            continue
        yield md


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", help="详细设计 .md 文件或目录")
    parser.add_argument("--json", action="store_true", help="JSON 输出供 Agent 解析")
    args = parser.parse_args()

    if not Path(args.target).exists():  # 路径写错时显式报错,避免静默 0 文件→误判"全部合规"
        print(f"错误: 路径不存在: {args.target}", file=sys.stderr)
        sys.exit(2)

    all_fields, all_issues = [], []
    files_scanned = 0
    for path in iter_targets(args.target):
        files_scanned += 1
        fields, issues = scan_file(path)
        all_fields.extend(fields)
        all_issues.extend(issues)

    summary = {
        "files_scanned": files_scanned,
        "money_field_count": len(all_fields),
        "issue_count": len(all_issues),
        "critical": sum(1 for i in all_issues if i["severity"] == "Critical"),
        "important": sum(1 for i in all_issues if i["severity"] == "Important"),
        "passed": len(all_issues) == 0,
    }

    if args.json:
        print(json.dumps({
            "summary": summary,
            "money_fields": all_fields,
            "issues": all_issues,
        }, ensure_ascii=False, indent=2))
        sys.exit(0 if summary["passed"] else 1)

    print(f"扫描文件数: {files_scanned}")
    print(f"识别金额字段: {len(all_fields)}")
    print(f"问题总数: {len(all_issues)} (Critical: {summary['critical']}, Important: {summary['important']})")
    print()
    if not all_issues:
        print("✅ 全部金额字段合规")
        sys.exit(0)

    for issue in all_issues:
        sev = issue["severity"]
        icon = "🔴" if sev == "Critical" else "🟡"
        print(f"{icon} [{sev}] {issue['file']}")
        print(f"   表 {issue['table']} 字段 {issue['field']} ({issue['type']})")
        print(f"   规则: {issue['rule']}")
        print(f"   建议: {issue['hint']}")
        if issue["comment"]:
            print(f"   现 COMMENT: {issue['comment']}")
        print()
    sys.exit(1)


if __name__ == "__main__":
    main()
