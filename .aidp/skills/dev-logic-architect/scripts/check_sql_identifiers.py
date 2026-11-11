#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SQL 标识符通用性核验(折入 dev-logic-architect 检查项 18「历史 SQL 风格沿用」·计数不变)

口径:设计文档里的 SQL(DDL 与 DML)**一律不给表名、字段名加引号**,同一个名字**只有一种拼写**,
且不用保留字作标识符。

立论:达梦/Oracle 对未加引号的标识符折成大写、加引号则保留原样,PostgreSQL 反向折成小写,
MySQL 的表名是否区分大小写取决于 lower_case_table_names。于是「小写加引号建表、不加引号查询」
在达梦上查不到,而不加引号建表则大小写写法都能查到。加引号 = 把标识符绑死在某个库的折叠规则上。

判据(对照表):
  Q1 quoted_identifier          Critical  标识符被双引号 / 反引号包裹
  Q2 table_spelling_drift       Critical  同一表名出现多种大小写拼写(MySQL/Linux 表名区分大小写,且换库即坏)
  Q3 column_spelling_drift      Important 同一列名出现多种大小写拼写(风格漂移,不一定出错)
  Q4 reserved_word_identifier   Important 表名/列名使用保留字(不加引号就无法规避,须改名)
  Q5 dameng_identifier_not_upper Critical  达梦:建表/改表/引用的表名、字段名必须全大写(仍不加引号;未加引号被折成大写,
                                           按大写建表则大小写写法都能查到)。由 `--db dameng` 或围栏标签 ```dm / ```dameng 触发

只扫 Markdown 里的 ```sql 等围栏(及含 CREATE TABLE 的无标签围栏);注释与单引号字符串先剥掉;
含 ❌ / 反例 / 错误示例 / 禁止 / 不要 字样的行视为「写出反模式本身以便禁止它」,整行跳过。
未发现任何 SQL 围栏 → skipped(exit 0,⚠️ 不等于通过)。

退出码: 0 无 Critical(或 N/A 跳过) / 1 有 Critical / 2 入参错(路径不存在、无法读取)。
用法: check_sql_identifiers.py <设计文档.md | 目录> [--json] [--strict]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

FENCE_RE = re.compile(r'^```(\w*)\s*$')
SQL_TAGS = {'sql', 'mysql', 'dm', 'dameng', 'oracle', 'postgresql', 'postgres', 'pgsql', 'ddl', 'plsql'}
GUARD_RE = re.compile(r'❌|反例|错误示例|禁止|不要|不得|严禁|避免')
IDENT = r'[A-Za-z_][\w$]*'
TABLE_CTX_RE = re.compile(
    r'\b(?P<kw>create\s+table(?:\s+if\s+not\s+exists)?|alter\s+table|drop\s+table(?:\s+if\s+exists)?|'
    r'truncate\s+table|from|join|into|update|references)\s+(?P<name>' + IDENT + r'(?:\.' + IDENT + r')?)',
    re.IGNORECASE)
NOT_TABLE_WORDS = {'select', 'set', 'values', 'dual', 'only', 'lateral', 'if', 'table', 'where', 'as',
                   'on', 'using', 'unnest', 'generate_series'}
CONSTRAINT_START = {'primary', 'unique', 'key', 'index', 'constraint', 'foreign', 'check', 'fulltext', 'spatial'}
ADD_COL_RE = re.compile(r'\badd\s+(?:column\s+)?(' + IDENT + r')\b', re.IGNORECASE)
# 跨库都会在不加引号时出问题的保留字(刻意保守:只列几乎所有主流库都保留的;命中判 Important)
RESERVED = {'order', 'group', 'user', 'level', 'key', 'desc', 'table', 'index', 'select', 'from', 'where',
            'check', 'default', 'rowid', 'rownum', 'union', 'having', 'limit', 'offset', 'by', 'to',
            'comment', 'session', 'system', 'mode', 'size', 'number', 'date', 'timestamp'}
# 上面这些里 date/timestamp/comment/size/number/mode 作列名在部分库合法但不通用,同样判 Important。


def strip_sql(text: str) -> str:
    """剥掉 `--` / `/* */` 注释与单引号字符串(保留换行,行号不变)。"""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c == "'":
            j = i + 1
            while j < n:
                if text[j] == "'" and j + 1 < n and text[j + 1] == "'":
                    j += 2
                    continue
                if text[j] == "'":
                    break
                j += 1
            out.append("''" + ''.join('\n' for ch in text[i:j + 1] if ch == '\n'))
            i = j + 1
        elif text.startswith('--', i):
            j = text.find('\n', i)
            i = n if j < 0 else j
        elif text.startswith('/*', i):
            j = text.find('*/', i + 2)
            j = n if j < 0 else j + 2
            out.append(''.join('\n' for ch in text[i:j] if ch == '\n'))
            i = j
        else:
            out.append(c)
            i += 1
    return ''.join(out)


def sql_blocks(md: str):
    """yield (起始行号, 去掉守卫行后的 sql 文本, 是否显式 sql 标签)。无标签围栏常混着 Java/JSON,只用反引号规则。"""
    lines = md.split('\n')
    i = 0
    while i < len(lines):
        m = FENCE_RE.match(lines[i].strip())
        if m:
            tag = m.group(1).lower()
            j = i + 1
            body = []
            while j < len(lines) and not lines[j].strip().startswith('```'):
                body.append(lines[j])
                j += 1
            text = '\n'.join(body)
            if tag in SQL_TAGS or (tag == '' and re.search(r'create\s+table', text, re.IGNORECASE)):
                # 守卫须在剥注释之前判(反例标记常写在 `-- ❌` 注释里),命中的行整行清空
                guarded = ['' if GUARD_RE.search(b) else b for b in body]
                yield i + 2, '\n'.join(guarded), tag in SQL_TAGS, tag
            i = j
        i += 1


def split_top(s: str):
    parts, depth, cur = [], 0, []
    for ch in s:
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        if ch == ',' and depth == 0:
            parts.append(''.join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append(''.join(cur))
    return parts


def create_table_columns(clean: str):
    """CREATE TABLE ( ... ) 里每个列定义的 (列名, 偏移)。"""
    for m in re.finditer(r'create\s+table(?:\s+if\s+not\s+exists)?\s+' + IDENT + r'(?:\.' + IDENT + r')?\s*\(',
                         clean, re.IGNORECASE):
        depth, i = 1, m.end()
        while i < len(clean) and depth:
            depth += {'(': 1, ')': -1}.get(clean[i], 0)
            i += 1
        body = clean[m.end():i - 1]
        base = m.end()
        pos = 0
        for item in split_top(body):
            stripped = item.strip()
            tok = re.match(IDENT, stripped)
            if tok and tok.group(0).lower() not in CONSTRAINT_START:
                yield tok.group(0), base + pos + (len(item) - len(item.lstrip()))
            pos += len(item) + 1


def table_refs(clean: str):
    for m in TABLE_CTX_RE.finditer(clean):
        kw = m.group('kw').lower()
        name = m.group('name').split('.')[-1]
        if name.lower() in NOT_TABLE_WORDS:
            continue
        before = clean[max(0, m.start() - 24):m.start()]
        if kw == 'update' and re.search(r'(key|for)\s*$', before, re.IGNORECASE):
            continue
        if kw == 'from':
            head = clean[max(0, m.start() - 80):m.start()]
            if re.search(r'(extract|substring|trim|overlay)\s*\([^)]*$', head, re.IGNORECASE):
                continue
        yield name, m.start('name')


def line_of(text: str, off: int, base: int) -> int:
    return base + text.count('\n', 0, off)


def scan_file(path: Path, md: str, db: str = ''):
    issues, tables, columns = [], defaultdict(list), defaultdict(list)
    found_sql = False
    for base, text, tagged, tag in sql_blocks(md):
        found_sql = True
        dameng = db == 'dameng' or tag in ('dm', 'dameng')
        clean = strip_sql(text)
        quote_re = r'"([^"\n]+)"|`([^`\n]+)`' if tagged else r'()`([^`\n]+)`'
        for m in re.finditer(quote_re, clean):
            name = m.group(1) or m.group(2)
            issues.append({'level': 'Critical', 'rule': 'quoted_identifier',
                           'file': str(path), 'line': line_of(clean, m.start(), base),
                           'msg': f'标识符 `{name}` 被引号包裹;SQL 一律不给表名/字段名加引号(加引号会绑死某个库的大小写折叠规则)'})
        # 引号内的内容不再参与后续拼写/保留字判定(已按 Q1 报过)
        unq = re.sub(r'"[^"\n]*"|`[^`\n]*`', ' ', clean)
        for name, off in table_refs(unq):
            tables[name.lower()].append((name, str(path), line_of(unq, off, base)))
            if dameng and name != name.upper():
                issues.append({'level': 'Critical', 'rule': 'dameng_identifier_not_upper', 'file': str(path),
                               'line': line_of(unq, off, base),
                               'msg': f'达梦:表名 `{name}` 必须全大写(`{name.upper()}`),且不加引号'})
            if name.lower() in RESERVED:
                issues.append({'level': 'Important', 'rule': 'reserved_word_identifier', 'file': str(path),
                               'line': line_of(unq, off, base),
                               'msg': f'表名 `{name}` 是保留字/易冲突词;不加引号无法规避,请改名(如加业务前缀)'})
        for name, off in create_table_columns(unq):
            columns[name.lower()].append((name, str(path), line_of(unq, off, base)))
            if dameng and name != name.upper():
                issues.append({'level': 'Critical', 'rule': 'dameng_identifier_not_upper', 'file': str(path),
                               'line': line_of(unq, off, base),
                               'msg': f'达梦:字段名 `{name}` 必须全大写(`{name.upper()}`),且不加引号'})
            if name.lower() in RESERVED:
                issues.append({'level': 'Important', 'rule': 'reserved_word_identifier', 'file': str(path),
                               'line': line_of(unq, off, base),
                               'msg': f'字段名 `{name}` 是保留字/易冲突词;不加引号无法规避,请改名(如 user_level、order_no)'})
        for m in ADD_COL_RE.finditer(unq):
            name = m.group(1)
            if name.lower() in CONSTRAINT_START | {'column', 'constraint'}:
                continue
            columns[name.lower()].append((name, str(path), line_of(unq, m.start(1), base)))
            if dameng and name != name.upper():
                issues.append({'level': 'Critical', 'rule': 'dameng_identifier_not_upper', 'file': str(path),
                               'line': line_of(unq, m.start(1), base),
                               'msg': f'达梦:字段名 `{name}` 必须全大写(`{name.upper()}`),且不加引号'})
    return found_sql, issues, tables, columns


def drift(groups, rule, level, what):
    out = []
    for key, occ in groups.items():
        spellings = sorted({o[0] for o in occ})
        if len(spellings) > 1:
            f, ln = occ[0][1], occ[0][2]
            out.append({'level': level, 'rule': rule, 'file': f, 'line': ln,
                        'msg': f'{what} `{key}` 出现多种拼写 {spellings};同一名字全设计只保留一种(推荐小写蛇形),'
                               f'DDL / DML / Mapper 逐字一致'})
    return out


def main():
    ap = argparse.ArgumentParser(description='SQL 标识符通用性核验:不加引号 / 单一拼写 / 不用保留字')
    ap.add_argument('target', help='设计文档(.md)或目录')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--db', default='', choices=['', 'dameng'], help='目标库;dameng = 标识符必须全大写(```dm 围栏自动视为达梦)')
    ap.add_argument('--strict', action='store_true', help='Important 也计入失败')
    args = ap.parse_args()
    t = Path(args.target)
    if not t.exists():
        print(f'错误:路径不存在 {t}', file=sys.stderr)
        return 2
    files = [t] if t.is_file() else sorted(t.rglob('*.md'))
    issues, tables, columns, found, read_errors = [], defaultdict(list), defaultdict(list), False, []
    for f in files:
        try:
            md = f.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError) as e:
            read_errors.append(f'{f}: {e}')
            continue
        fs, iss, tb, cl = scan_file(f, md, args.db)
        found = found or fs
        issues += iss
        for k, v in tb.items():
            tables[k] += v
        for k, v in cl.items():
            columns[k] += v
    if read_errors and not files:
        print('错误:无法读取任何文件', file=sys.stderr)
        return 2
    issues += drift(tables, 'table_spelling_drift', 'Critical', '表名')
    issues += drift(columns, 'column_spelling_drift', 'Important', '字段名')
    crit = [i for i in issues if i['level'] == 'Critical']
    imp = [i for i in issues if i['level'] == 'Important']
    skipped = not found and not issues
    passed = not crit and (not imp if args.strict else True)
    if args.json:
        print(json.dumps({'skipped': skipped, 'passed': passed, 'critical': len(crit), 'important': len(imp),
                          'read_errors': read_errors, 'issues': issues}, ensure_ascii=False, indent=2))
    else:
        if skipped:
            print('⏭️ 未发现 SQL 围栏,本项未执行(skipped,不等于通过)')
        for i in issues:
            print(f"[{i['level']}] {i['rule']} {i['file']}:{i['line']} {i['msg']}")
        if not skipped:
            print(f'Critical {len(crit)} / Important {len(imp)}' + (' ✅' if passed else ' ❌'))
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
