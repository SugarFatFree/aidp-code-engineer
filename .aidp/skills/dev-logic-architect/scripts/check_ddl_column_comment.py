#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""DDL 新增列注释配对硬核回检 — dev-logic-architect 检查项 39-C(Critical,对应核心原则 32)

实际项目中实测:一次给既有表加了 10 列,
**10 列全部无注释**(数据字典实查 10/10 无)。半年后没有任何人能从库里看出这些列是干什么的,
而「与既有近似列的区别」这类**只可能写在注释里**的结论就此永久丢失。

本脚本只回答一个问题:**DDL 里每个 `ADD COLUMN` 有没有配对的列注释**。两种方言形态都认:

    MySQL       : ALTER TABLE t ADD COLUMN `c` VARCHAR(64) ... COMMENT '业务含义...';
    达梦/Oracle : ALTER TABLE t ADD (C VARCHAR2(64));
                  COMMENT ON COLUMN t.C IS '业务含义...';       ← 配对语句可以在别处

⚠️ **只认 `ADD COLUMN` 会在国产库项目上静默失效**(达梦等国产库即此形态:它的批量形态是 `ADD (COL TYPE)`,
   且**根本不支持**在 ALTER 里内联 COMMENT,必须另起 `COMMENT ON COLUMN`)。
   故本脚本:① 两种 ADD 形态都解析;② 配对既认**内联 COMMENT**,也认**同一批文档里任意位置**的
   `COMMENT ON COLUMN`(⚠️ 因此**须传目录**——DDL 与注释语句常分册)。

检查项:
【Critical(退出码 1)】
  D1 `ADD COLUMN` 无配对注释 —— 内联 COMMENT 与 `COMMENT ON COLUMN` 都没有
  D2 注释存在但为空串或占位 —— `COMMENT ''` / `IS '待补'` / `IS 'TODO'`

⚠️ **本脚本刻意只管 `ADD COLUMN`,不管 `CREATE TABLE` 的列**,与检查项 39 正文口径一致
   (「本项只管 `ADD COLUMN`,不重复覆盖建表列」)。
   ⚠️ **别把这句读成「建表列的注释已被别人覆盖」** —— 独立审计实测:`CREATE TABLE` 里
   一个**完全没有 COMMENT** 的普通列,八个姊妹脚本合计 Critical 0(检查项 13 只管**自由文本列**的
   长度冗余标注、21 只管**索引列**的哨兵说明、`check_unit_field.py` 只管**数值列**的单位),
   即**建表普通列的 COMMENT 存在性全仓无门**,这是一个**已知且刻意保留**的缺口。
   ⛔ **不要为此在本脚本里加一道建表列注释门** —— 那会与上面三个脚本在同一批列上重叠开火,
   正好变成本仓库最高频的「同判据两份实现」。要补应当单开一道、并先在全仓量假红率。

⚠️ **本门只是必要条件、不充分**:下游那次事故里**脚本是对的、执行漏了**
   (只跑了 `ALTER TABLE ADD` 那段循环,注释语句整段没跑)。
   「执行后回库实查列注释」那一半由**被测项目侧**的 SQL 执行台账 / 发布基线核查承担,
   ⛔ **本 SKILL 不承担、也不重写那一半**(同核心原则 27 / 28 的去重边界纪律)。

用法:
    python3 check_ddl_column_comment.py <设计文档目录或文件> [--json]

退出码:
    0 = 通过,或 N/A 跳过(没有 `ALTER TABLE ... ADD` 语句)
    1 = 检出违规(严重度分档读 --json,不占用退出码)
    2 = 入参或环境错(路径不存在、目录下没有 .md、文件全部不可读)

仅依赖 Python 3.8+ 标准库。
⚠️ 本 SKILL 内脚本**互不 import**(SKILL 独立性原则)。本文件的 `parse_alter_add_segments` 与
   `check_column_consumer_evidence.py` 的 `parse_alter_add_columns` **同口径不同签名**
   (本文件多返回一个列定义片段用于找内联 COMMENT),解析口径须两处同改。
   ⚠️ 审计订正:此处原写「`parse_alter_add_columns` 的解析口径……」,而
   **本文件里根本没有叫这个名字的函数** —— 从本文件 grep 该名字零命中,定位不到东西。
⚠️ **与对面须两处同改、且函数体逐字节相同的**:`IDENT_PART` / `ALTER_HEAD_RE` / `ADD_KEYWORD_RE` /
   `SQL_FENCE_LANGS` / `NON_COLUMN_KEYWORDS` / `IDENT_RE` / `sql_fence_blocks` / `_clean_ident` /
   `_table_name` / `_split_top_level` / `find_md_files` / **`split_sql_statements`**。
   ⚠️ `parse_comment_on` / `_unquote` / `line_of` **只有本文件有**,不需要同步。
   ⚠️ `split_sql_statements` 两边的 **docstring 允许分叉**(对向引用那行必然相反、告警码举例各按
      本文件视角写),**但函数体不许分叉** —— 做 diff 时别把 docstring 差异误读成实现漂移。
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ⚠️ 表名**必须以标识符起头**,⛔ 不可写成 `[`"\[\]\w.]+`:那样 `.` 也在字符类里,
#    于是散文里的占位写法 `ALTER TABLE ... ADD` 会被当成一条真语句(表名解析成空串),
#    再把后文任意一个 `ADD` 后的词认成列名——实测在本 SKILL 自家 `flow-qr-dispatch.md`
#    的**无语言标记围栏**里凭空造出一个叫 `column` 的新增列。
IDENT_PART = r"[`\"\[]?[A-Za-z_][A-Za-z0-9_$]*[`\"\]]?"
ALTER_HEAD_RE = re.compile(r"\bALTER\s+TABLE\s+(%s(?:\.%s)?)" % (IDENT_PART, IDENT_PART), re.I)
ADD_KEYWORD_RE = re.compile(r"\bADD\s+(?:COLUMN\b\s*)?(?:IF\s+NOT\s+EXISTS\s+)?", re.I)
# ⚠️ `IF NOT EXISTS` 必须吃掉:MySQL 8 / MariaDB 的 `ADD COLUMN IF NOT EXISTS c` 会让
#    「ADD 之后的第一个标识符」变成 `IF`,于是凭空多出一个叫 `if` 的列(实测在本 SKILL
#    自家的 `output-module-examples.md` 上假红)。`ADD INDEX IF NOT EXISTS` 不受影响
#    ——那条被 NON_COLUMN_KEYWORDS 的 `index` 挡住。
# SQL 围栏白名单:带语言标记且不是 SQL 方言的围栏一律不当 DDL 看(Java 里的字符串不是 DDL)。
SQL_FENCE_LANGS = {"", "sql", "ddl", "mysql", "oracle", "dm", "dameng", "plsql",
                   "pgsql", "postgres", "postgresql", "sqlite", "text", "plain"}
NON_COLUMN_KEYWORDS = {"constraint", "index", "key", "primary", "unique", "foreign",
                       "check", "fulltext", "spatial", "partition"}
IDENT_RE = re.compile(r"[`\"\[]?([A-Za-z_][A-Za-z0-9_$]*)[`\"\]]?")
# 内联注释:MySQL 的 `... COMMENT '文本'`
INLINE_COMMENT_RE = re.compile(r"\bCOMMENT\s+('(?:[^']|'')*'|\"(?:[^\"]|\"\")*\")", re.I)
# 独立注释语句:达梦 / Oracle / PostgreSQL 的 `COMMENT ON COLUMN t.c IS '文本'`
COMMENT_ON_RE = re.compile(
    r"\bCOMMENT\s+ON\s+COLUMN\s+([`\"\[\]\w\.]+)\s+IS\s+('(?:[^']|'')*'|\"(?:[^\"]|\"\")*\")", re.I)
PLACEHOLDER_COMMENT_RE = re.compile(
    r"^(?:|[-—–\s]*|/|N/?A|TBD|TODO|待补|待定|待填|占位|xxx+|\?+|同上)$", re.I)


def find_md_files(path: Path) -> List[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(path.rglob("*.md"))
    return []


def sql_fence_blocks(lines):
    """返回全部 **SQL 方言** 代码围栏块的内容列表(每块一个字符串)。

    ⚠️ **必须按块返回、⛔ 不可把所有围栏拼成一整段**:SQL 语句是按 `;` 切的,拼接后
       「fence A 里的 `ALTER TABLE t`(没写分号)」会和「fence B 里的 `ADD ...`」被当成同一条
       语句,凭空造出一个不存在的新增列。
    ⚠️ 带语言标记且不在 SQL_FENCE_LANGS 里的围栏整块跳过(```java 里的字符串不是 DDL)。
    """
    blocks = []
    inside = False
    keep = False
    buf = []
    for ln in lines:
        st = ln.lstrip()
        if st.startswith("```"):
            if inside:
                if keep and buf:
                    blocks.append("\n".join(buf))
                buf = []
                inside = False
            else:
                lang = st[3:].strip().split()[0].lower() if st[3:].strip() else ""
                keep = lang in SQL_FENCE_LANGS
                inside = True
            continue
        if inside and keep:
            buf.append(ln)
    if inside and keep and buf:
        blocks.append("\n".join(buf))
    return blocks


def _clean_ident(tok: str) -> str:
    m = IDENT_RE.match(tok.strip())
    return m.group(1) if m else ""


def _table_name(raw: str) -> str:
    n = raw.strip().strip('`"[]')
    return n.split(".")[-1].lower()


def _split_top_level(s: str) -> List[str]:
    r"""按顶层逗号切分;遇到未配对的 `)` 即止。

    ⚠️ **必须同时跳过括号与字符串字面量**,两者缺一不可:
       ① 括号 —— `VARCHAR(10,2)` 里的逗号不是列分隔;
       ② 字符串 —— `COMMENT '用户ID,关联 biz_user.id'` 里的逗号更不是。
       ②实测踩过:本 SKILL 自家 `output-module-examples.md` 的
       `ADD COLUMN ... COMMENT '用户ID,关联 ...'` 被从注释正中间切断,
       于是「有注释」被判成「无注释」——失效方向是**假红**,而且看不出原因。
    """
    parts: List[str] = []
    depth = 0
    quote = ""
    cur: List[str] = []
    for ch in s:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = ""
            continue
        if ch in ("'", '"'):
            quote = ch
            cur.append(ch)
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            if depth == 0:
                break
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
            continue
        cur.append(ch)
    if cur:
        parts.append("".join(cur))
    return parts


def _unquote(lit: str) -> str:
    body = lit[1:-1] if len(lit) >= 2 else ""
    return body.replace("''", "'").replace('""', '"').strip()


def split_sql_statements(sql: str) -> List[str]:
    r"""按**顶层** `;` 切语句,同时剥掉 SQL 注释(`--` 行注释 / `/* */` 块注释)。

    ⚠️⚠️ ⛔ **不可退回 `sql.split(";")`** —— 两个方向都实测踩过:
       ① **假红** —— `COMMENT '结算状态:0-未结算;1-已结算(参考 A.4 SettleStatusEnum;区别于 status)'`
          里的 `;` 会把语句**从注释正中间**切断,内联 `COMMENT '...'` 的闭合引号落到下一段,
          `INLINE_COMMENT_RE` 匹配不上 → 「明明写了注释」被判成 D1「没有配对注释」。
          ⚠️ 本 SKILL 自家 `output-module-examples.md` 那份「照此填写即合规」的 canonical
          示例**正是这个形态**(它在真文件里只因下方一条**被注释掉**的 `COMMENT ON COLUMN`
          恰好补位才没红 —— 两个 bug 互相抵消)。
       ② **假绿** —— 同一条 `ALTER` 里该 `;` **之后**的 `ADD COLUMN b ...` 整段落进
          「没有 ALTER 头」的碎片、被 `continue` 丢弃,那一列**从此对本门完全隐形**
          (D1 够不着,姊妹脚本的 E7 也够不着)。实测
          `ADD COLUMN a INT COMMENT 'x;y', ADD COLUMN b INT` 只解析出 `a`。
    ⚠️ **SQL 注释必须剥**:设计文档常把「已否决的方案」「历史脚本留档」「达梦环境另行执行」
       写成 `--` / `/* */`,不剥则
       ① **假红** —— 注释里的 `ALTER ... ADD` 被当成真新增列,D1 判 Critical,
          作者除了删掉那段留档没有别的改法;
       ② **假绿** —— 被注释掉的 `COMMENT ON COLUMN`(= 根本不会执行)照样被认成「配对注释」,
          而「注释语句整段没跑」正是本门立论那次事故的**直接现场**(见本文件头注释)。
    ⚠️ 剥注释必须在**引号外**进行:`COMMENT '价格--折后'` 里的 `--` 不是注释。
    ⚠️ 已知边界(不追求消灭):`'it''s'` 这类 SQL 转义引号会被当成「闭合后又开一个」,
       净效果上引号状态仍正确闭合,只有中间那一小段被当作引号外——那里出现 `;` / `--`
       的概率可忽略,与 `_split_top_level` 的口径一致。
    ⚠️ 与 `check_column_consumer_evidence.py` 里的同名函数是**刻意的重复实现**
       (SKILL 独立性原则:同一 SKILL 内脚本也互不 import),改一处须两处同改。
    """
    stmts: List[str] = []
    cur: List[str] = []
    quote = ""
    i, n = 0, len(sql)
    while i < n:
        ch = sql[i]
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = ""
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            cur.append(ch)
            i += 1
            continue
        if ch == "-" and sql.startswith("--", i):
            j = sql.find("\n", i)
            i = n if j < 0 else j      # 停在换行上,下一轮把它原样带上,不打乱行结构
            continue
        if ch == "/" and sql.startswith("/*", i):
            j = sql.find("*/", i + 2)
            i = n if j < 0 else j + 2
            cur.append(" ")            # 用空格占位,免得把前后两个标识符黏成一个
            continue
        if ch == ";":
            stmts.append("".join(cur))
            cur = []
            i += 1
            continue
        cur.append(ch)
        i += 1
    if cur:
        stmts.append("".join(cur))
    return stmts


def parse_alter_add_segments(sql: str) -> List[Tuple[str, str, str]]:
    """解析 `ALTER TABLE ... ADD`,返回 [(表名, 列名, 该列的定义片段)](表列名均小写)。

    ⚠️ 与 `check_column_consumer_evidence.py` 的 `parse_alter_add_columns` 是**刻意的重复实现**
       (SKILL 独立性原则:同一 SKILL 内脚本也互不 import),本文件多返回一个「定义片段」
       用于找内联 COMMENT。改一处须两处同改。
    """
    out: List[Tuple[str, str, str]] = []
    for stmt in split_sql_statements(sql):
        head = ALTER_HEAD_RE.search(stmt)
        if not head:
            continue
        table = _table_name(head.group(1))
        rest = stmt[head.end():]
        for m in ADD_KEYWORD_RE.finditer(rest):
            tail = rest[m.end():].lstrip()
            if not tail:
                continue
            if tail.startswith("("):          # 达梦/Oracle 括号批量形态
                for seg in _split_top_level(tail[1:]):
                    col = _clean_ident(seg)
                    if col and col.lower() not in NON_COLUMN_KEYWORDS:
                        out.append((table, col.lower(), seg))
                continue
            seg = _split_top_level(tail)[0] if _split_top_level(tail) else tail
            col = _clean_ident(seg)
            if col and col.lower() not in NON_COLUMN_KEYWORDS:
                out.append((table, col.lower(), seg))
    return out


def parse_comment_on(sql: str) -> Dict[Tuple[str, str], str]:
    """解析 `COMMENT ON COLUMN t.c IS '...'`,返回 {(表名, 列名): 注释文本}。

    ⚠️ 表名可能不带库前缀、也可能只写 `t.c`,一律取最后两段。
    ⚠️⚠️ **必须走 `split_sql_statements` 剥掉 SQL 注释后再匹配**:被 `--` / `/* */` 注释掉的
       `COMMENT ON COLUMN` **根本不会执行**,认它作「配对注释」就是本门立论那次事故的
       原样复刻(「脚本是对的、执行漏了」)。实测:ALTER 真执行 + COMMENT 语句被注释掉,
       修复前 D1 全绿 exit 0 —— **最高优先级的假绿**。
    """
    out: Dict[Tuple[str, str], str] = {}
    sql = "\n".join(split_sql_statements(sql))
    for m in COMMENT_ON_RE.finditer(sql):
        raw = m.group(1).strip().strip('`"[]')
        parts = [p.strip('`"[]') for p in raw.split(".") if p.strip('`"[]')]
        if len(parts) < 2:
            continue
        out[(parts[-2].lower(), parts[-1].lower())] = _unquote(m.group(2))
    return out


def line_of(lines: List[str], col: str) -> int:
    """尽力给出该列名在文中的首个出现行(仅用于报错定位)。

    ⚠️ 只在**代码围栏内**找:不然像 `user_id` 这种词会先命中正文散文,
       报出的行号与真正的 DDL 差了上千行、完全失去可定位性(实测踩过)。
    """
    pat = re.compile(r"\b%s\b" % re.escape(col), re.I)
    inside = False
    for i, ln in enumerate(lines):
        if ln.lstrip().startswith("```"):
            inside = not inside
            continue
        if inside and pat.search(ln):
            return i + 1
    return 0


def check_file(path: Path) -> dict:
    issues: List[dict] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        # ⚠️ 读失败绝不可静默计为通过(全仓退出码约定第 3 条)。
        issues.append({"level": "Important", "code": "read_error", "file": str(path),
                       "line": 0, "msg": "文件读不出来(%s),已跳过——⛔ 不得据此判该文件无违规" % e})
        return {"issues": issues, "adds": [], "comments": {}, "lines": [], "file": str(path)}

    lines = text.split("\n")
    adds: List[Tuple[str, str, str]] = []
    comments: Dict[Tuple[str, str], str] = {}
    for block in sql_fence_blocks(lines):
        adds.extend(parse_alter_add_segments(block))
        comments.update(parse_comment_on(block))
    return {"issues": issues, "adds": adds, "comments": comments,
            "lines": lines, "file": str(path)}


def main() -> int:
    ap = argparse.ArgumentParser(
        description="DDL 新增列注释配对硬核回检(dev-logic-architect 检查项 39-C)")
    ap.add_argument("path", help="设计文档目录或单个 .md 文件")
    ap.add_argument("--json", action="store_true", help="输出 JSON(供 Agent 解析)")
    args = ap.parse_args()

    target = Path(args.path)
    # ⚠️ exists() 与 is_dir() 必须分开判(全仓退出码约定第 2 条)。
    if not target.exists():
        print("路径不存在: %s" % target, file=sys.stderr)
        return 2
    files = find_md_files(target)
    if not files:
        print("未找到任何 .md 文件: %s" % target, file=sys.stderr)
        return 2

    issues: List[dict] = []
    per_file: List[dict] = []
    comments: Dict[Tuple[str, str], str] = {}
    read_ok = 0
    for f in files:
        r = check_file(f)
        issues.extend(r["issues"])
        if not r["issues"]:
            read_ok += 1
            per_file.append(r)
            # ⚠️ 跨文件合并:`COMMENT ON COLUMN` 常与 ALTER 分册(数据库设计册 / 迁移脚本册)
            comments.update(r["comments"])
    if read_ok == 0:
        print("全部 .md 文件不可读: %s" % target, file=sys.stderr)
        return 2

    total_adds = 0
    for r in per_file:
        for table, col, seg in r["adds"]:
            total_adds += 1
            inline = INLINE_COMMENT_RE.search(seg)
            body: Optional[str] = None
            where = ""
            if inline:
                body = _unquote(inline.group(1))
                where = "内联 COMMENT"
            elif (table, col) in comments:
                body = comments[(table, col)]
                where = "COMMENT ON COLUMN"
            if body is None:
                issues.append({"level": "Critical", "code": "D1", "file": r["file"],
                               "line": line_of(r["lines"], col),
                               "msg": "`%s.%s` 是新增列,却没有配对的列注释——"
                                      "MySQL 用内联 `COMMENT '...'`,达梦/Oracle 用 "
                                      "`COMMENT ON COLUMN %s.%s IS '...'`;"
                                      "注释须写清业务含义 + 取值域(枚举列全)+ 与近似列的区别"
                                      % (table, col, table, col)})
            elif PLACEHOLDER_COMMENT_RE.match(body.strip()):
                issues.append({"level": "Critical", "code": "D2", "file": r["file"],
                               "line": line_of(r["lines"], col),
                               "msg": "`%s.%s` 的%s是空串或占位(`%s`)——不可核对等于没写"
                                      % (table, col, where, body)})

    read_errors = [x for x in issues if x["code"] == "read_error"]
    skipped = total_adds == 0 and not read_errors
    criticals = [x for x in issues if x["level"] == "Critical"]
    warns = [x for x in issues if x["level"] != "Critical"]

    if args.json:
        print(json.dumps({
            "path": str(target), "skipped": skipped, "files": read_ok,
            "add_columns": total_adds, "comment_on_statements": len(comments),
            "read_errors": len(read_errors),
            "critical": len(criticals), "important": len(warns),
            "findings": issues,
        }, ensure_ascii=False, indent=2))
        return 1 if criticals else 0

    if skipped:
        print("⏭  跳过:代码围栏里没有 `ALTER TABLE ... ADD` 语句。")
        print("   ⚠️ 跳过 ≠ 通过——本次若确实新增了库表列而 DDL 未落到设计文档里,")
        print("      那本身就是检查项 39 要判的缺口。")
        return 0

    print("扫描 %d 个文件 · 新增列 %d 个 · COMMENT ON COLUMN 语句 %d 条"
          % (read_ok, total_adds, len(comments)))
    if not issues:
        print("✅ DDL 新增列注释配对检查通过(Critical 0 / Important 0)")
    else:
        for x in issues:
            loc = "%s:%d" % (x["file"], x["line"]) if x["line"] else x["file"]
            print("  [%s] %s  %s — %s" % (x["level"], x["code"], loc, x["msg"]))
        print("\n结论:Critical %d / Important %d" % (len(criticals), len(warns)))
    return 1 if criticals else 0


if __name__ == "__main__":
    sys.exit(main())
