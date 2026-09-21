#!/usr/bin/env python3
"""
check_ddl_consistency.py — DDL 与详细设计 A.3 数据表设计一致性检查

对比 SQL DDL 文件中的字段定义与详细设计文档中对应表的字段表,检查:
  - 字段是否缺失/多出(error)
  - 字段类型基础名是否一致(error;忽略长度差异,仅比对基础类型名)
  - NOT NULL 约束是否一致(warn,不硬失败)

说明: DEFAULT 值与索引定义的逐项比对暂未实现(设计文档侧多不提供结构化 DEFAULT/索引描述,
      逐项比对易误报),本脚本仅核验字段清单/类型/NOT NULL;DEFAULT 与索引一致性以人工对照设计
      A.3 为准(见 quality-review-checklist.md 检查项 9.1)。

用法:
  python check_ddl_consistency.py <ddl_file.sql> <design_doc.md>
  python check_ddl_consistency.py <ddl_file.sql> <design_doc.md> --table biz_work_order
  python check_ddl_consistency.py <ddl_file.sql> <design_doc.md> --json

说明:
  设计文档中表的字段定义可以是 markdown 表格(首列为字段名,表前有 `### biz_xxx` 之类的表名标题),
  也可以是 ```sql 围栏里的 CREATE TABLE DDL(dev-logic-architect A.3 的 canonical 形态);
  两种都取不到时才判「未找到可对比的表」。
  字段名匹配大小写不敏感;类型对比仅检查基础类型名(忽略长度差异除非完全不同)。

退出码:
  0 = 一致
  1 = 存在差异
  2 = 用法错误或文件不存在
"""

from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path


CREATE_TABLE_HEAD_PATTERN = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"\[]?(\w+)[`\"\]]?\s*\(",
    re.IGNORECASE,
)


def iter_create_tables(sql_text):
    """逐表产出 (表名, 表体, CREATE 起始偏移)。

    表体用括号配对(并跳过引号内字符)定位真正的结束括号,避免列内
    `VARCHAR(20) COMMENT '...'` 这类「) 紧跟 COMMENT」把表体提前截断——
    旧的非贪婪正则会在第一个「) 紧跟 COMMENT」处收尾,漏掉其后所有字段与索引,
    使一致性对比静默失效(可空列 + 行内 COMMENT 是最常见的触发写法)。
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


def parse_ddl(sql_text: str) -> dict[str, dict]:
    """解析 CREATE TABLE 语句,返回 {table_name: {fields: {name: {type, not_null, default}}, indexes: [...]}}"""
    tables: dict[str, dict] = {}
    for table_name, body, _ in iter_create_tables(sql_text):
        fields: dict[str, dict] = {}
        indexes: list[str] = []
        for line in body.splitlines():
            line = line.strip().rstrip(',')
            if not line:
                continue
            low = line.lower()
            if low.startswith(('primary key', 'unique key', 'unique index', 'key ', 'index ', 'constraint ', 'foreign key')):
                idx_match = re.search(r'(?:key|index)\s+[`"]?(\w+)[`"]?', line, re.IGNORECASE)
                if idx_match:
                    indexes.append(idx_match.group(1).lower())
                continue
            fld = re.match(r'[`"]?(\w+)[`"]?\s+(\w+(?:\([^)]+\))?)', line)
            if not fld:
                continue
            name = fld.group(1).lower()
            ftype = fld.group(2).lower()
            not_null = 'not null' in low
            default_match = re.search(r"default\s+([^,\s]+(?:\s*'[^']*')?)", line, re.IGNORECASE)
            default = default_match.group(1) if default_match else None
            fields[name] = {'type': ftype, 'not_null': not_null, 'default': default}
        tables[table_name.lower()] = {'fields': fields, 'indexes': indexes}
    return tables


def parse_design_doc(md_text: str, target_table: str | None) -> dict[str, dict]:
    """从设计文档中提取表字段定义。返回 {table_name: {fields: {name: {type, not_null}}}}"""
    tables: dict[str, dict] = {}
    # 切分 markdown 章节,每个 ### 或更高级标题作为一个段
    sections = re.split(r'(^#{2,4}\s+.+$)', md_text, flags=re.MULTILINE)
    current_table = None
    for i, sec in enumerate(sections):
        if re.match(r'^#{2,4}\s+', sec):
            m = re.search(r'(biz_\w+|sys_\w+|t_\w+|\w+_\w+)', sec)
            if m:
                current_table = m.group(1).lower()
            else:
                current_table = None
            continue
        if not current_table:
            continue
        if target_table and current_table != target_table.lower():
            continue
        # 在段内查找 markdown 表格(以 | 开头的连续行)
        rows = re.findall(r'^\|([^\n]+)\|\s*$', sec, re.MULTILINE)
        if len(rows) < 2:
            continue
        header_cells = [c.strip().lower() for c in rows[0].split('|') if c.strip()]
        if not header_cells:
            continue
        if '字段' not in header_cells[0] and 'field' not in header_cells[0] and '列名' not in header_cells[0]:
            continue
        fields: dict[str, dict] = {}
        for row in rows[2:]:  # skip header + separator
            cells = [c.strip() for c in row.split('|') if c.strip()]
            if len(cells) < 2:
                continue
            name = cells[0].strip('`').lower()
            if not re.match(r'^[a-z_][a-z0-9_]*$', name):
                continue
            ftype = cells[1].lower() if len(cells) > 1 else ''
            row_text = ' | '.join(cells).lower()
            not_null = ('not null' in row_text) or ('必填' in ' | '.join(cells))
            fields[name] = {'type': ftype, 'not_null': not_null}
        if fields:
            tables[current_table] = {'fields': fields}

    # ── 兜底:设计文档以 CREATE TABLE DDL(```sql 围栏)描述 A.3 数据表 ──────────────
    # 上游详细设计的 A.3「数据定义」通常直接给 SQL 围栏里的 CREATE TABLE,而非 markdown
    # 字段表。若只认 markdown 表格,对这类(最常见的)设计文档会恒判「未找到可对比的表」
    # 而静默失效。故此处对未从 markdown 表格取到的表,回退用同一套 DDL 解析器从设计
    # 文档的 SQL 围栏中提取。
    # ⚠️ info-string 必填（`sql`/`ddl`），**不可写成 `(?:sql|ddl)?` 可选**：
    # 可选形态会让空 info-string 也能开围栏，于是遇到文档里任何一个非 sql 围栏
    # （architect 的 A.2 ER 图是 Critical 强制产出的 ```mermaid，必然存在）时，
    # 正则改从它的**闭**围栏起配对，此后全文错位 —— A.3 的 CREATE TABLE 永远抓不到，
    # 整个脚本恒判「未找到可对比的表」。实测自家 canonical output-module-examples.md
    # 71 个围栏只捞出 1 个含 CREATE TABLE、且首块内容是「启动类：」。
    # 同 SKILL 的 check_index_not_null.py:34 / check_er_and_fk.py:40 一直是正确写法，照抄即可。
    for fence in re.findall(r'```(?:sql|ddl)\s*\n([\s\S]*?)```', md_text, re.IGNORECASE):
        if 'create table' not in fence.lower():
            continue
        for tname, tinfo in parse_ddl(fence).items():
            if target_table and tname != target_table.lower():
                continue
            if tname in tables or not tinfo.get('fields'):
                continue
            tables[tname] = {'fields': {
                f: {'type': v['type'], 'not_null': v['not_null']}
                for f, v in tinfo['fields'].items()
            }}
    return tables


def base_type(t: str) -> str:
    return re.sub(r'\(.*\)', '', t).strip().lower()


def compare(ddl_tables: dict, design_tables: dict, target: str | None) -> list[dict]:
    issues: list[dict] = []
    table_names = set(ddl_tables) & set(design_tables)
    if target:
        table_names = {t for t in table_names if t == target.lower()}
    if not table_names:
        issues.append({'level': 'error', 'msg': f'未找到可对比的表(DDL: {list(ddl_tables)}; 设计: {list(design_tables)})'})
        return issues

    for tname in sorted(table_names):
        ddl_fields = ddl_tables[tname]['fields']
        design_fields = design_tables[tname]['fields']
        only_ddl = set(ddl_fields) - set(design_fields)
        only_design = set(design_fields) - set(ddl_fields)
        common = set(ddl_fields) & set(design_fields)
        for f in sorted(only_ddl):
            issues.append({'level': 'error', 'table': tname, 'field': f, 'msg': f'DDL 多出字段 {f}(设计中未定义)'})
        for f in sorted(only_design):
            issues.append({'level': 'error', 'table': tname, 'field': f, 'msg': f'DDL 缺少字段 {f}(设计中已定义)'})
        for f in sorted(common):
            d = ddl_fields[f]; s = design_fields[f]
            if base_type(d['type']) != base_type(s['type']) and s['type']:
                issues.append({'level': 'error', 'table': tname, 'field': f,
                               'msg': f'字段 {f} 类型不一致: DDL={d["type"]} vs 设计={s["type"]}'})
            if d['not_null'] != s['not_null']:
                issues.append({'level': 'warn', 'table': tname, 'field': f,
                               'msg': f'字段 {f} NOT NULL 不一致: DDL={d["not_null"]} vs 设计={s["not_null"]}'})
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description='DDL 与详细设计 A.3 一致性检查')
    parser.add_argument('ddl_file', help='SQL DDL 文件路径')
    parser.add_argument('design_doc', help='详细设计文档路径(.md)')
    parser.add_argument('--table', help='只检查指定表名(可选)')
    parser.add_argument('--json', action='store_true', help='以 JSON 格式输出')
    args = parser.parse_args()

    ddl_path = Path(args.ddl_file)
    # 容错:允许第二参数携带 `#章节锚点`(如 设计.md#A.3),自动剥离锚点定位到文件本体
    design_arg = args.design_doc
    if '#' in design_arg and not Path(design_arg).is_file():
        design_arg = design_arg.split('#', 1)[0]
    design_path = Path(design_arg)
    if not ddl_path.is_file():
        print(f'DDL 文件不存在: {ddl_path}', file=sys.stderr); return 2
    if not design_path.is_file():
        print(f'设计文档不存在: {design_path}', file=sys.stderr); return 2

    ddl_text = ddl_path.read_text(encoding='utf-8', errors='replace')
    design_text = design_path.read_text(encoding='utf-8', errors='replace')

    ddl_tables = parse_ddl(ddl_text)
    design_tables = parse_design_doc(design_text, args.table)
    issues = compare(ddl_tables, design_tables, args.table)

    has_error = any(i['level'] == 'error' for i in issues)
    status = 'fail' if has_error else 'pass'
    result = {
        'status': status,
        'ddl_tables': list(ddl_tables),
        'design_tables': list(design_tables),
        'compared_tables': sorted(set(ddl_tables) & set(design_tables)),
        'issues': issues,
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f'状态: {"✅ PASS" if not has_error else "❌ FAIL"}  '
              f'(对比表: {result["compared_tables"]})')
        for i in issues:
            icon = '❌' if i['level'] == 'error' else '⚠️'
            t = f'[{i.get("table", "-")}.{ i.get("field", "-")}]' if 'table' in i else ''
            print(f'  {icon} {t} {i["msg"]}')
        if not issues:
            print('  无差异')

    return 0 if not has_error else 1


if __name__ == '__main__':
    sys.exit(main())
