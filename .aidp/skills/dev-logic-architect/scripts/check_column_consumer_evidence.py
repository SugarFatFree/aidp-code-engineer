#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""「新增列举证表」硬核回检 — dev-logic-architect 检查项 39(Critical,对应核心原则 32)

**建表的判据是「谁会读它」,不是「上游有什么」。**

实际项目中实测:需求写「某上游列表改为查本应用自己的
库表,缺字段可以加上」,执行体照着上游用户中心那个 21 字段的 VO 形状一次性加了 10 列;
复核后逐条验证——本应用源码的映射函数只映射 13 个字段,新加的 10 列里 **8 列零消费**,
其中一列是证件号码(留存一份用不上的敏感个人信息 = 凭空增加的合规负担),另有一列与既有列
是同一个事实的两份副本,且 10 列**全部无注释**。最终收敛为 2 列,**80% 的列是纯粹的浪费**。

⚠️ 根因不是判断失误,是**缺门**:上游 VO 就摆在眼前,而「谁会读它」要主动去下游仓库翻源码
   —— **阻力最小的路径是错的那条**,没有任何一道门拦住它。

本脚本核验设计期那张 6 列「新增列举证表」:

    | 列名 | 类型 | 业务含义 | 谁读它(具体到界面/判据/接口出参) | 不加会怎样 | 与既有近似列的区别 |

检查项:
【Critical(退出码 1)】
  E2 缺列                —— 6 列固定契约
  E3 逐格空或占位        —— `待定` / `TBD` / `—` / `{...}` / `同上`(与 check_render_merge_table.py 同款)
  E4 举不出消费者        —— 第 4 列命中「来源/推迟」类措辞(`上游有` / `保持一致` / `以后可能` /
                            `备用` / `预留` / `先存着`)**且剥掉这些措辞后几乎没有剩余内容**
  E5 「不加会怎样」答"没什么影响" —— 整格为「没什么影响 / 无影响 / 影响不大」这类
  E6 数据行格数与表头不符 —— 单列不并进 E2:表象是列数不符,并进去只会把排查带偏到表头上
  E7 DDL 里 ADD 的列没登记进举证表 —— **仅当至少存在一张举证表时才判**(见下方 E1 取舍)

【Important(仅告警,不占退出码,须读 --json)】
  E1 有 `ALTER TABLE ... ADD` 却一张举证表都没有(**跨文件聚合判定,须传目录**)
  W1 第 4 列命中来源类措辞但仍有实质内容 —— 疑似「只写了来源、没写消费者」,由 QR 子 Agent 判
  W2 举证表登记的列在本目录 DDL 里找不到 —— 可能分册,也可能列名写错
  W3 本版 DDL 里存在名称近似的既有列,而第 6 列填「无」—— 疑似漏做重复性对账
  W4 第 4 列一个**可核对的消费者形态**都没命中 —— E4 是关键词黑名单、换成日常口语即可绕过
     (实测「先加上,后面再说」/「和用户中心那边一样」/「参照 UserVO」一条都不命中黑名单),
     本项从正面兜一道:一句真举证总会指到某个能去核对的东西

⚠️ **E1 缺表刻意判 Important 不判 Critical**:存量设计会大面积命中,一上来判死会让整个硬门
   被无视(本仓库既有教训:假红常驻 = 硬门被绕过,同 check_upstream_call_log_spec.py 的 U1)。
   表**一旦产出**,缺列 / 格子空 / 举不出消费者 / DDL 加了列却没登记就是新产物自身的缺陷,
   那几条才判 Critical。⚠️ 与之配套:**一张表都没有时只报 E1、不报 E7** —— 否则每份存量设计
   仍被 E7 逐列判死,E1 降 Important 的取舍会被自己当场抵消(姊妹 SKILL 的
   `check_residual_assertions.py` 的 Z1/Z6 实测踩过这个洞)。
   ⚠️ `skipped=true` 只说明既没找到表、也没找到 ADD 语句,**不等于通过**。

⚠️ **本脚本不做语义判定**:「这个消费者是不是真的存在」「举证指向外部仓库时有没有附文件路径 +
   映射函数名」由 QR 子 Agent 按检查项 39 核对 —— 那需要去读下游仓库,脚本做不到。
   本脚本只拦「**一眼就能看出没举证**」的结构缺陷。

用法:
    python3 check_column_consumer_evidence.py <设计文档目录或文件> [--json]

退出码:
    0 = 通过,或 N/A 跳过(既无举证表也无 ALTER ADD 语句)
    1 = 检出违规(严重度分档读 --json,不占用退出码)
    2 = 入参或环境错(路径不存在、目录下没有 .md、文件全部不可读)

仅依赖 Python 3.8+ 标准库。
⚠️ 本 SKILL 内脚本**互不 import**(SKILL 独立性原则)。`split_row` / `is_separator_row` / `_norm` /
   `strip_code_fences` 与 `check_render_merge_table.py` 同款。
⚠️ **与 `check_ddl_column_comment.py` 须两处同改的,精确地说只有这几个**(审计订正:
   原文把 `parse_create_table_columns` 也列了进来,而**对面根本没有这个函数**——照那句去「两处同改」
   会找不到对象,或反过来以为对面已有一份而不去补):
     `IDENT_PART` / `ALTER_HEAD_RE` / `ADD_KEYWORD_RE` / `SQL_FENCE_LANGS` / `NON_COLUMN_KEYWORDS` /
     `IDENT_RE` / `sql_fence_blocks` / `_clean_ident` / `_table_name` / `_split_top_level` /
     `find_md_files` / **`split_sql_statements`** —— 以上**函数体须逐字节相同**;
     本文件的 `parse_alter_add_columns` ⟷ 对面的 `parse_alter_add_segments` 是**同口径不同签名**
     (对面多返回一个列定义片段用于找内联 COMMENT),解析口径须同改、签名本就不同。
   ⚠️ `parse_create_table_columns` / `similar_columns` / 表格解析那一族**只有本文件有**,不需要同步。
   ⚠️ `split_sql_statements` 两边的 **docstring 允许分叉**(对向引用那行必然相反、告警码举例各按本文件视角写),
      **但函数体不许分叉** —— 做 diff 时别把 docstring 差异误读成实现漂移。
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

REQUIRED_COLUMNS = ["列名", "类型", "业务含义", "谁读它", "不加会怎样", "与既有近似列的区别"]
# 「专名列」:这三个概念在本 SKILL 其它任何表的表头里都不出现
# (「列名」与「字段实现清单」的「列名/字段」撞名,故**不可**当专名列)
SIGNATURE_COLUMNS = ("谁读它", "不加会怎样", "与既有近似列的区别")

PLACEHOLDER_CELL_RE = re.compile(
    r"^(?:[-—–]+|/|N/?A|TBD|待定|待补|待填|同上|视情况|按业务|\{[^{}]*\}|<[^<>]*>)$", re.I)

# 第 4 列「谁读它」的**来源/推迟类**措辞。命中它**本身不判错** —— 「上游有该字段,本侧企业
# 列表第 3 列渲染它」是一句合格的举证。判错的是「剥掉这些措辞之后什么都不剩」的格子。
CONSUMER_BAN_RE = re.compile(
    r"以后|将来|未来|后续|可能|说不定|暂时用不到|暂未使用|暂不使用|暂时不用|"
    r"上游有|上游存在|上游VO|上游字段|上游都有|上游返回|"
    r"保持一致|与上游一致|同上游|跟上游一样|对齐上游|"
    r"先存|先留|先放|备用|预留|占位|扩展用|以防万一|不确定|万一")
# 剥掉措辞后再剥掉这些「填充字」,剩下的才算实质内容。
CONSUMER_FILLER = "的了着呢吧这那该此其它他个些字段列值数据信息内容项条和与及都也就还要用需是有" \
                  ",，。;；:：、()（）\"'`！!？?~-—…　 "
# 剩余实质内容少于该长度即判 E4。⚠️ 4 是实测取的:「要用」(2)、「保持」(2)、「有」(1) 全部落在
#    线下,而任何一句真写了消费者的话(哪怕只写「企业列表第3列」)都远在线上。
CONSUMER_MIN_RESIDUE = 4

# 第 4 列的**可核对消费者形态**信号(W4 用)。命中任一即认为「至少指到了一个能去核对的东西」。
# ⚠️ **只用于 Important 提示、⛔ 绝不可升成 Critical**:合法但用词朴素的举证确实可能一个都不命中
#    (「运营后台首页大屏」这类),按白名单判死会假红常驻,而假红常驻 = 硬门被绕过。
# ⚠️ **`VO` / `DTO` / `API` 刻意不在表内**:「参照 UserVO」是**来源**不是消费者,收了它就正好放过
#    本条要提示的那一类;真正的接口侧举证一定会带「接口 / 出参 / 入参 / 响应」中的某个词。
CONSUMER_SIGNAL_RE = re.compile(
    r"页|列|卡片|弹窗|抽屉|详情|列表|表格|表单|导出|下载|打印|tooltip|气泡|文案|"
    r"筛选|排序|搜索|查询条件|接口|出参|入参|响应|返回|判据|规则|校验|权限|鉴权|归属|"
    r"状态机|流转|定时任务|调度|报表|统计|大屏|看板|首页|菜单|按钮|通知|短信|邮件|"
    r"[A-Za-z_][\w./-]*\.(?:ts|js|vue|java|kt|go|py|tsx|jsx)|/[A-Za-z_]|\(\)", re.I)

# 第 5 列「不加会怎样」:**整格**为这些形态即 E5。⚠️ 刻意只做**整格**匹配,不做子串匹配——
#    「不加则导出列缺失,不影响页面渲染」是一句合格的回答,子串匹配会把它判死。
NO_IMPACT_RE = re.compile(
    r"^(?:没什么影响|没有影响|无影响|不影响|没影响|影响不大|影响很小|暂无影响|"
    r"无|没有|不会有影响|无所谓|都行)$")

# 第 6 列填这些 = 声明「没有近似列」(合法,但若 DDL 里真有近似列则触发 W3)
NO_SIMILAR_RE = re.compile(r"^(?:无|无近似列|没有|没有近似列|不适用|N/?A|不涉及)$", re.I)

# ── SQL 解析 ──
# ⚠️ 只在**代码围栏内**找 DDL:设计正文里「避免 ALTER TABLE 风险」这类散文不带 ADD,
#    但把判据限在围栏内可以彻底断掉散文误判(与本仓库「新判据宁可窄」一致)。
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
CREATE_HEAD_RE = re.compile(
    r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(%s(?:\.%s)?)" % (IDENT_PART, IDENT_PART), re.I)


def find_md_files(path: Path) -> List[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(path.rglob("*.md"))
    return []


def split_row(line: str) -> List[str]:
    r"""按未转义的 `|` 切列(单元格里可能出现 `A \| B` 这种写法)。"""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in re.split(r"(?<!\\)\|", s)]


def is_separator_row(cells: List[str]) -> bool:
    # ⚠️ 空行必须先判掉:split_row("") 得到 [""],过滤空格后 all() 对空序列返回 True,
    #    于是空行被当成分隔行——「候选表头 + 紧跟一个空行」会被识别成一张 0 行的表。
    if not cells or all(c.strip() == "" for c in cells):
        return False
    return all(re.fullmatch(r":?-{1,}:?", c.replace(" ", "")) for c in cells if c != "")


def _norm(s: str) -> str:
    s = re.sub(r"[*`>\s]", "", s)
    return s.replace("（", "(").replace("）", ")")


# 表头单元格长度上限。⚠️ **实测必须有**:本仓库 `AGENTS.md` 的 SKILL 清单表里,
#    单个格子是几千字的散文,里面同时出现「类型」「含义」「消费者」等词,
#    没有长度闸门时整行被认成本表表头 → 缺列 + 格数不符,一次假红 5 条。
#    列名是短词,24 字符足够宽松。
MAX_HEADER_CELL = 24


def cell_matches_column(cell: str, concept: str) -> bool:
    c = _norm(cell)
    if len(c) > MAX_HEADER_CELL:
        return False
    if concept == "列名":
        # ⚠️ 排除「列名/字段」——那是「字段实现清单」的首列,两张表不可混
        return ("列名" in c and "字段" not in c) or c in ("新增列", "新增字段", "列")
    if concept == "类型":
        return "类型" in c or "字段类型" in c
    if concept == "业务含义":
        # ⚠️ 刻意不认「说明」——它在任何表的表头里都可能出现,认了必假红
        return "业务含义" in c or "含义" in c
    if concept == "谁读它":
        # ⚠️ 刻意不写成「含「谁」且含「读」」——那个组合在散文里太容易同时出现
        return "谁读它" in c or "消费者" in c or "谁来读" in c
    if concept == "不加会怎样":
        return "不加会怎样" in c or ("不加" in c and "怎样" in c) or "不加的后果" in c
    if concept == "与既有近似列的区别":
        return ("近似列" in c) or ("既有列" in c and "区别" in c)
    return False


def col_index(cells: List[str], concept: str) -> Optional[int]:
    for idx, c in enumerate(cells):
        if cell_matches_column(c, concept):
            return idx
    return None


def is_table_header(cells: List[str]) -> bool:
    """签名判定:命中任一专名列 + 至少 3 个契约列。

    ⚠️ **不要改回「几个指定列同时在」的写法**:那样一来,恰恰是把其中一列删掉的表会整张
       认不出来 —— 表被跳过 → 数据行一行不解析 → E2~E7 全部够不着,只剩一个「没找到表」,
       而删掉一列本该是 E2 Critical。姊妹 SKILL 的 `check_residual_assertions.py`
       实测踩过这个洞(严重度完全反了),此处直接按修好的形态写。
    """
    if not any(col_index(cells, c) is not None for c in SIGNATURE_COLUMNS):
        return False
    return sum(1 for c in REQUIRED_COLUMNS if col_index(cells, c) is not None) >= 3


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


def strip_code_fences(lines: List[str]) -> List[bool]:
    flags = [False] * len(lines)
    inside = False
    for i, ln in enumerate(lines):
        if ln.lstrip().startswith("```"):
            flags[i] = True
            inside = not inside
            continue
        flags[i] = inside
    return flags


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
          (E7 够不着、D1 也够不着)。实测 `ADD COLUMN a INT COMMENT 'x;y', ADD COLUMN b INT`
          只解析出 `a`。
    ⚠️ **SQL 注释必须剥**:设计文档常把「已否决的方案」「历史脚本留档」「达梦环境另行执行」
       写成 `--` / `/* */`,不剥则
       ① **假红** —— 注释里的 `ALTER ... ADD` 被当成真新增列,E7 / D1 判 Critical,
          作者除了删掉那段留档没有别的改法;
       ② **假绿** —— 被注释掉的 `COMMENT ON COLUMN`(= 根本不会执行)照样被认成「配对注释」,
          而「注释语句整段没跑」正是本门立论那次事故的**直接现场**。
    ⚠️ 剥注释必须在**引号外**进行:`COMMENT '价格--折后'` 里的 `--` 不是注释。
    ⚠️ 已知边界(不追求消灭):`'it''s'` 这类 SQL 转义引号会被当成「闭合后又开一个」,
       净效果上引号状态仍正确闭合,只有中间那一小段被当作引号外——那里出现 `;` / `--`
       的概率可忽略,与 `_split_top_level` 的口径一致。
    ⚠️ 与 `check_ddl_column_comment.py` 里的同名函数是**刻意的重复实现**
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


def parse_alter_add_columns(sql: str) -> List[Tuple[str, str]]:
    """从 SQL 文本里解析出全部 `ALTER TABLE ... ADD` 的列,返回 [(表名, 列名)](均小写)。

    ⚠️ **方言必须同时认两种形态**,只认 `ADD COLUMN` 会在国产库项目上静默失效
       (达梦等国产库即此形态):
         MySQL      : ALTER TABLE t ADD COLUMN `c` VARCHAR(64) COMMENT '...';
         达梦/Oracle: ALTER TABLE t ADD (C1 VARCHAR2(64), C2 NUMBER);
                      ALTER TABLE t ADD C1 VARCHAR2(64);
    ⚠️ 与 `check_ddl_column_comment.py` 里的同名函数是**刻意的重复实现**
       (SKILL 独立性原则:同一 SKILL 内脚本也互不 import),改一处须两处同改。
    """
    out: List[Tuple[str, str]] = []
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
                        out.append((table, col.lower()))
                continue
            col = _clean_ident(tail)
            if col and col.lower() not in NON_COLUMN_KEYWORDS:
                out.append((table, col.lower()))
    return out


def parse_create_table_columns(sql: str) -> Dict[str, Set[str]]:
    """从 SQL 文本里解析出 `CREATE TABLE` 的列,返回 {表名: {列名}}(均小写)。

    ⚠️ 与 `check_ddl_column_comment.py` 里的同名函数是刻意的重复实现,改一处须两处同改。
    """
    out: Dict[str, Set[str]] = {}
    # ⚠️ 同样走剥注释后的文本:被 `--` / `/* */` 注释掉的 `CREATE TABLE` 是留档不是基线,
    #    算进来会给 W3 的近似列池混入不存在的列。
    sql = "\n".join(split_sql_statements(sql))
    for m in CREATE_HEAD_RE.finditer(sql):
        table = _table_name(m.group(1))
        rest = sql[m.end():]
        lp = rest.find("(")
        if lp < 0:
            continue
        cols = out.setdefault(table, set())
        for seg in _split_top_level(rest[lp + 1:]):
            first = seg.strip()
            if not first:
                continue
            kw = first.split()[0].strip('`"[]').lower() if first.split() else ""
            if kw in NON_COLUMN_KEYWORDS:
                continue
            col = _clean_ident(first)
            if col:
                cols.add(col.lower())
    return out


def consumer_residue(cell: str) -> str:
    """剥掉「来源/推迟」类措辞与填充字后的实质内容。"""
    s = _norm(cell)
    s = CONSUMER_BAN_RE.sub("", s)
    return "".join(ch for ch in s if ch not in CONSUMER_FILLER)


def norm_col(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def similar_columns(col: str, pool: Set[str]) -> List[str]:
    """名称近似判定:归一化后互为子串,且**较短的那个 ≥ 4 字符**。

    ⚠️ ≥4 的下限不能去掉:否则 `id` 会与仓库里几乎每个列都「近似」。
       真实样本 `ADMIN_USER_ID` vs 既有 `SUPER_ADMIN_USER_ID`、`ADMIN_STATUS` vs `STATUS`
       都由这一条命中。
    """
    a = norm_col(col)
    hits: List[str] = []
    for other in pool:
        b = norm_col(other)
        if not b or b == a:
            continue
        short, long_ = (a, b) if len(a) <= len(b) else (b, a)
        if len(short) >= 4 and short in long_:
            hits.append(other)
    return sorted(hits)


def check_file(path: Path) -> dict:
    """扫描单文件,返回 {issues, rows, tables, ddl_add, ddl_cols}。"""
    issues: List[dict] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        # ⚠️ 读失败绝不可静默计为通过(全仓退出码约定第 3 条)。
        issues.append({"level": "Important", "code": "read_error", "file": str(path),
                       "line": 0, "msg": "文件读不出来(%s),已跳过——⛔ 不得据此判该文件无违规" % e})
        return {"issues": issues, "rows": [], "tables": 0, "ddl_add": [], "ddl_cols": {}}

    lines = text.split("\n")
    in_fence = strip_code_fences(lines)

    # ── DDL 采集(只看 SQL 方言代码围栏内,逐块解析) ──
    ddl_add: List[Tuple[str, str]] = []
    ddl_cols: Dict[str, Set[str]] = {}
    for block in sql_fence_blocks(lines):
        ddl_add.extend(parse_alter_add_columns(block))
        for t, cs in parse_create_table_columns(block).items():
            ddl_cols.setdefault(t, set()).update(cs)

    # ── 举证表采集 ──
    tables = 0
    rows: List[dict] = []
    header: Optional[List[str]] = None
    hidx: Dict[str, int] = {}

    for i, ln in enumerate(lines):
        if in_fence[i] or not ln.lstrip().startswith("|"):
            header = None
            continue
        cells = split_row(ln)
        if is_separator_row(cells):
            continue
        if header is None:
            if is_table_header(cells):
                tables += 1
                header = cells
                hidx = {}
                for concept in REQUIRED_COLUMNS:
                    j = col_index(cells, concept)
                    if j is None:
                        issues.append({"level": "Critical", "code": "E2", "file": str(path),
                                       "line": i + 1,
                                       "msg": "缺列「%s」(6 列固定契约:%s)"
                                              % (concept, " | ".join(REQUIRED_COLUMNS))})
                    else:
                        hidx[concept] = j
            continue

        if len(cells) != len(header):
            issues.append({"level": "Critical", "code": "E6", "file": str(path), "line": i + 1,
                           "msg": "数据行 %d 格、表头 %d 格——若格子里写了 `|`,须转义为 `\\|`"
                                  "(GFM 里 `|` 是列分隔符,反引号保护不了它)"
                                  % (len(cells), len(header))})
            continue

        row = {c: cells[j] for c, j in hidx.items() if j < len(cells)}

        # E3 逐格空或占位
        for concept, v in row.items():
            if v.strip() == "" or PLACEHOLDER_CELL_RE.match(_norm(v)):
                issues.append({"level": "Critical", "code": "E3", "file": str(path), "line": i + 1,
                               "msg": "「%s」格空或只有占位(`%s`)——不可核对等于没写" % (concept, v)})

        who = row.get("谁读它", "")
        impact = row.get("不加会怎样", "")
        diff = row.get("与既有近似列的区别", "")
        colname = row.get("列名", "")

        # E4 / W1 举不出消费者
        if who and CONSUMER_BAN_RE.search(_norm(who)):
            residue = consumer_residue(who)
            if len(residue) < CONSUMER_MIN_RESIDUE:
                issues.append({"level": "Critical", "code": "E4", "file": str(path), "line": i + 1,
                               "msg": "「谁读它」写的是「%s」——这是**来源**不是**消费者**。"
                                      "「以后可能要用 / 上游有这个字段 / 保持与上游一致 / 先存着」"
                                      "一律不算;写不出具体读取方(界面/判据/接口出参)的列不得进入 DDL"
                                      % who.strip()})
            else:
                issues.append({"level": "Important", "code": "W1", "file": str(path), "line": i + 1,
                               "msg": "「谁读它」里出现了来源类措辞(「%s」)——请确认它确实点到了"
                                      "具体读取方,而不只是在说「上游有」" % who.strip()[:60]})
        # W4 一个可核对的消费者形态都没命中(E4 没抓到、但很可能同样不是举证)
        # ⚠️ **本项存在的理由**:E4 是**关键词黑名单**,换成日常口语就绕过去了——实测
        #    「先加上,后面再说」/「和用户中心那边一样」/「参照 UserVO」三条**正是本门要拦的
        #    非举证**,却一条都不命中 CONSUMER_BAN_RE。黑名单补不完,故改从正面提示:
        #    一句真举证总会指到某个**能去核对的东西**(某页某列 / 某条判据 / 某个接口出参 /
        #    某个文件路径)。判 Important 而非 Critical 的理由见 CONSUMER_SIGNAL_RE 注释。
        elif who and not CONSUMER_SIGNAL_RE.search(who):
            issues.append({"level": "Important", "code": "W4", "file": str(path), "line": i + 1,
                           "msg": "「谁读它」写的是「%s」,里面没有任何可核对的消费者形态"
                                  "(某页/某列/某条判据/某个接口出参/某个文件路径)——"
                                  "请确认这是**读取方**而不是**来源**或一句口语"
                                  % who.strip()[:60]})

        # E5 「不加会怎样」答"没什么影响"
        if impact and NO_IMPACT_RE.match(_norm(impact)):
            issues.append({"level": "Critical", "code": "E5", "file": str(path), "line": i + 1,
                           "msg": "「不加会怎样」答「%s」——答「没什么影响」的列同样不得进入 DDL"
                                  % impact.strip()})

        rows.append({"file": str(path), "line": i + 1, "col": colname,
                     "diff": diff, "who": who})

    return {"issues": issues, "rows": rows, "tables": tables,
            "ddl_add": ddl_add, "ddl_cols": ddl_cols}


def main() -> int:
    ap = argparse.ArgumentParser(
        description="新增列举证表硬核回检(dev-logic-architect 检查项 39)")
    ap.add_argument("path", help="设计文档目录或单个 .md 文件")
    ap.add_argument("--json", action="store_true", help="输出 JSON(供 Agent 解析)")
    args = ap.parse_args()

    target = Path(args.path)
    # ⚠️ exists() 与 is_dir() 必须分开判(全仓退出码约定第 2 条):合并写会把「路径根本不存在」
    #    和「传入单个文件=合法」混为一谈,手滑写错路径等于整个检查静默放行。
    if not target.exists():
        print("路径不存在: %s" % target, file=sys.stderr)
        return 2
    files = find_md_files(target)
    if not files:
        print("未找到任何 .md 文件: %s" % target, file=sys.stderr)
        return 2

    issues: List[dict] = []
    rows: List[dict] = []
    tables = 0
    ddl_add: List[Tuple[str, str]] = []
    ddl_cols: Dict[str, Set[str]] = {}
    read_ok = 0
    for f in files:
        r = check_file(f)
        issues.extend(r["issues"])
        rows.extend(r["rows"])
        tables += r["tables"]
        ddl_add.extend(r["ddl_add"])
        for t, cs in r["ddl_cols"].items():
            ddl_cols.setdefault(t, set()).update(cs)
        if not any(x["code"] == "read_error" and x["file"] == str(f) for x in r["issues"]):
            read_ok += 1
    if read_ok == 0:
        print("全部 .md 文件不可读: %s" % target, file=sys.stderr)
        return 2

    # ── 跨文件对账(E1 / E7 / W2 / W3) ──
    registered: Dict[str, dict] = {}
    for row in rows:
        for tok in re.findall(r"[A-Za-z_][A-Za-z0-9_$]*", row["col"]):
            registered[tok.lower()] = row

    added_by_table: Dict[str, Set[str]] = {}
    for t, c in ddl_add:
        added_by_table.setdefault(t, set()).add(c)
    # ⚠️ **本门按裸列名匹配、不区分表**:6 列契约里
    #    **没有「表名」列**,`registered` 只能按列名建 key,于是「A 表的 status 已举证」
    #    会连带把「B 表未举证的 status」一起放行 —— 方向是**假绿**。
    #    ⚠️ 顺带修掉一个会掩盖它的显示问题:人读那行原先打 `len(added_all)`(**去重后的列名集合**),
    #    同名跨表的两列会被数成一个,读者连「有两列」都看不出来。现改打真实的 (表, 列) 对数。
    #    ⛔ 真正的修法是给 6 列契约加一列表名,那要同步改 8 处落点,属**契约变更、留给维护者定夺**,
    #    此处只做到「不隐瞒」:计数照实、E7 文案就地声明该边界。
    added_pairs = sorted(set(ddl_add))
    added_all = {c for _t, c in ddl_add}

    if ddl_add and tables == 0:
        # ⚠️ 一张表都没有 → 只报 E1,**不报 E7**。见文件头注释。
        issues.append({"level": "Important", "code": "E1", "file": str(target), "line": 0,
                       "msg": "检测到 %d 处 `ALTER TABLE ... ADD`(%s)却没有任何「新增列举证表」"
                              "——每个新增列都必须逐行举证「谁读它」与「不加会怎样」"
                              % (len(ddl_add), ", ".join(sorted(added_all))[:200])})
    elif tables:
        for t, cols in sorted(added_by_table.items()):
            for c in sorted(cols):
                if c not in registered:
                    issues.append({"level": "Critical", "code": "E7", "file": str(target),
                                   "line": 0,
                                   "msg": "DDL 给 `%s` 加了列 `%s`,却没有登记进「新增列举证表」"
                                          "——加了列就必须举证,漏登记等于绕过本门。"
                                          "⚠️ 本门**按裸列名匹配、不区分表**(6 列契约里没有表名列):"
                                          "若同一列名被加到多张表上,只要其中一张已举证,其余表的同名列"
                                          "**本门查不出来**,须由 QR 子 Agent 按检查项 39 逐表核对"
                                          % (t, c)})
        for name, row in sorted(registered.items()):
            if added_all and name not in added_all:
                issues.append({"level": "Important", "code": "W2", "file": row["file"],
                               "line": row["line"],
                               "msg": "举证表登记了列 `%s`,但本目录 DDL 里没有对应的 ADD 语句"
                                      "——可能是分册(DDL 在另一册),也可能列名写错了" % name})

    # W3 重复性对账:第 6 列填「无」而 DDL 里确实有名称近似的列
    for name, row in sorted(registered.items()):
        if not row["diff"] or not NO_SIMILAR_RE.match(_norm(row["diff"])):
            continue
        pool: Set[str] = set()
        for t, cols in added_by_table.items():
            if name in cols:
                pool |= (ddl_cols.get(t, set()) | cols)
        hits = [h for h in similar_columns(name, pool) if h != name]
        if hits:
            issues.append({"level": "Important", "code": "W3", "file": row["file"],
                           "line": row["line"],
                           "msg": "列 `%s` 的「与既有近似列的区别」填「%s」,但同表里存在名称近似的列"
                                  "(%s)——请判定是重复(复用既有列)还是确实不同(把区别写进列注释)"
                                  % (name, row["diff"].strip(), ", ".join(hits))})

    read_errors = [x for x in issues if x["code"] == "read_error"]
    skipped = tables == 0 and not ddl_add and not read_errors
    criticals = [x for x in issues if x["level"] == "Critical"]
    warns = [x for x in issues if x["level"] != "Critical"]

    if args.json:
        print(json.dumps({
            "path": str(target), "skipped": skipped, "files": read_ok,
            # ⚠️ `ddl_added_columns` 是**去重后的列名集合**(既有字段,口径不动以免破坏调用方);
            #    `ddl_added_column_pairs` 才是真实的 (表, 列) 全集 —— 同名跨表时两者条数不同,
            #    判「本次到底加了几列」一律读后者。
            "tables": tables, "ddl_added_columns": sorted(added_all),
            "ddl_added_column_pairs": ["%s.%s" % (t, c) for t, c in added_pairs],
            "read_errors": len(read_errors),
            "critical": len(criticals), "important": len(warns),
            "findings": issues,
        }, ensure_ascii=False, indent=2))
        return 1 if criticals else 0

    if skipped:
        print("⏭  跳过:既没有「新增列举证表」,也没有 `ALTER TABLE ... ADD` 语句。")
        print("   ⚠️ 跳过 ≠ 通过——本次设计若确实新增了库表列,表该不该有由 QR 子 Agent 按检查项 39 判。")
        return 0

    # ⚠️ 这里数的是 (表, 列) 对、⛔ 不是 `len(added_all)`:后者去重列名,同名跨表的两列会被数成一个,
    #    读者连「有两列」都看不出来(审计实测:两张表各加一个 `status`,原先打「DDL 新增列 1 个」)。
    print("扫描 %d 个文件 · 新增列举证表 %d 张 · DDL 新增列 %d 个(按表.列计)"
          % (read_ok, tables, len(added_pairs)))
    if not issues:
        print("✅ 新增列举证表检查通过(Critical 0 / Important 0)")
    else:
        for x in issues:
            loc = "%s:%d" % (x["file"], x["line"]) if x["line"] else x["file"]
            print("  [%s] %s  %s — %s" % (x["level"], x["code"], loc, x["msg"]))
        print("\n结论:Critical %d / Important %d" % (len(criticals), len(warns)))
    return 1 if criticals else 0


if __name__ == "__main__":
    sys.exit(main())
