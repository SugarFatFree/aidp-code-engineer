#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""「零残留断言登记表」硬核回检 — dev-manual-testcase 维度 18 子条

**零残留断言** = 一切 `断言(反向):不存在文本"X"` 形态的反向断言,含 `[反向-残留]`(裁剪/延期项
该删没删)与 `[文案一致性]` 的反向用例(旧口径字样残留)。它们**只增不退**:下游实测规划期 20 条、
两个 Sprint 后 33 条,而规矩是「每条写完当场实跑两个方向」+「每轮收尾原则上重跑」,
成本线性增长且不可逆。本脚本核验**登记面**的形态,让「哪条断言、守护哪些文件、跑没跑过两个方向、
有没有退役」变成可机检的东西。

⚠️ **本脚本只判登记表的形态,判不了「那两个方向是不是真跑过」**——那属语义层,由 QR 子 Agent
   对照实跑记录核。**脚本全绿 ≠ 维度 18 零残留子条通过。**

检查项(7 类):
【Critical(退出码 1)】
  Z2 登记表缺列   —— 7 列固定契约:# | 断言 | 守护面 | 实跑命令 | 方向一·现状命中 | 方向二·阳性对照 | 退役状态
  Z3 逐格空或占位 —— 任一必填格空 / 只有 `-`、`TBD`、`待补`、`同上`、`{占位}`(已退役行的两个方向列除外)
  Z4 实跑记录缺失 —— 「方向二」格里读不到 `N 命中`(N ≥ 1),或「方向一」格里读不到 `N 命中`
                     (「已验证通过」这类结论无法与「根本没跑」区分)。★ 本项是本脚本的核心:
                     只跑方向一的断言可能是「式子写错、永远不会命中」的**恒 0 假绿**,
                     而它在报告里与真正的零残留长得一模一样(下游实测:一条断言全绿交付,
                     后来额外手工补一条对照才证明它不是恒 0)
  Z5 退役理由非法 —— 以「多轮未红 / 没红过 / 一直常绿」为由退役,或 `已退役` 未写依据。
                     ⛔ 常绿正是这类断言的**正常状态**,按它退役等于专挑还在生效的断言删
  Z6 漏登记       —— 文档里出现的零残留断言在登记表里找不到对应行
  Z7 数据行格数不符 —— 最常见根因是**实跑命令里的 `|` 未转义为 `\|`**(GFM 里 `|` 是列分隔符,
                     **反引号代码段保护不了它**)。⚠️ 刻意不并进 Z2:并进去只会报「表头列不齐」、
                     把排查带偏到表头上(与 `check_count_claim_table.py` 的 C5 同一取舍)

【Important(仅告警,不影响退出码)】
  Z1 缺登记表 —— 有零残留断言却找不到登记表。⚠️ **刻意判 Important 不判 Critical**:
                 存量用例文档会大面积命中,一上来判死会让整个硬门被无视(本仓库既有教训:
                 假红常驻 = 硬门被绕过),与 `check_upstream_call_log_spec.py` 的 U1 同一取舍。
                 表**一旦产出**,Z2~Z7 那几条才是新产物自身的缺陷、才判 Critical
  W2 实跑命令缺前置声明 —— 既没写 `默认前置` / `grep -v`,也没写明为何关闭注释前置
                          (实跑口径见 `references/test-design-methodology.md` 八之二)
  W3 方向一命中 > 0 —— 现状仍有残留(是测试结论不是文档缺陷,故只告警)
  read_error —— 某个 `.md` 读不出来,已跳过其内容。⛔ **不得据此判该文件无违规**:
                只要有一条 read_error,`skipped` 恒为 false、`--json` 的 `read_errors` 计数 > 0,
                而 `assertions` / `rows` 是**残缺样本**上的结果

⚠️ **Z1 / Z6 是跨文件聚合判定,调用方须传目录。** 多册拆分时登记表常落在总览册、而断言散在各模块册,
   逐文件判必假红(与 `check_metric_spec.py` 的 M1、`check_upstream_call_log_spec.py` 的 U1 同一个坑)。
   传单文件时脚本打作用域告警并在 `--json` 出 `scope: "single-file"`,见到即按「未全范围核验」处理。

已知局限(登记在案,**不是可以放宽的理由**):
  ① **断言只在标题式用例块内收集** —— 用 `**用例 TC-A-001**` 这类**加粗非标题**承载的用例,
     其断言扫不到 → Z6 漏判(实测 skip=True、asrt=0)。放宽即触碰「⛔ 不扫章节散文」那条护栏
     (规范/方法论文档必然写举例,扫散文会满屏假红);两个模板与既有产物一律用
     `##### 用例 TC-xxx` 标题,故维持现状。
  ② **表格必须带首尾竖线** —— GFM 允许省略 `|`,省了则整张表认不出来、只剩一条 Z1(实测)。
     与本 SKILL 其余表格类脚本(`check_fidelity_suite.py` 等)同一约定,不单独放宽。

用法:
    python3 check_residual_assertions.py <用例目录或文件> [--json]

退出码:
    0 = 通过,或跳过(整个扫描范围里一条零残留断言、一张登记表都没有,且无 read_error)
    1 = 检出违规(严重度分档读 --json,不占用退出码)
    2 = 入参或环境错(路径不存在、目录下没有 .md、文件全部不可读)

⚠️ `skipped=true` 表示整档没跑,**不等于通过**;表该不该有由 QR 子 Agent 判。

仅依赖 Python 3.8+ 标准库。
⚠️ 本 SKILL 内的脚本**互不 import**(SKILL 独立性原则)。`is_separator_row` / `_norm` /
   `strip_code_fences` 与 `check_fidelity_suite.py` **逐字同款**,属刻意重复,改一处须两处同改。
   ⚠️ **`split_row` 刻意与它不同、⛔ 别"顺手统一"**:那边是裸 `s.split("|")`,本脚本必须按
   `(?<!\\)\|` 切——本表的「实跑命令」列会出现 ``grep … \| grep -vE …`` 这类**已按 GFM 规矩转义**
   的管道,裸切会把合规行多切一格、当场判 Z7(自家模板被自家硬门判死)。反向也成立:
   把本脚本这版搬去 `check_fidelity_suite.py` 会改变那边对含 `\|` 单元格的解析,须另行实测。
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ── 断言识别 ────────────────────────────────────────────────────────────────
# `断言(反向):不存在文本"X"` — 括号/冒号/引号的全角半角都认。
ASSERT_RE = re.compile(
    r"断言\s*[(（]\s*反向\s*[)）]\s*[:：]\s*不存在(?:未标注作废的)?文本\s*"
    r"[\"“「']([^\"”」']+)[\"”」']")
# 占位文本:单个拉丁字母 / {…} / <…>。规范与模板必然要写 `不存在文本"X"` 这类**指引**,
# 无差别收集会把指引句当成一条未登记的断言(实测:本 SKILL 自家模板与 checklist 都会命中)。
PLACEHOLDER_TEXT_RE = re.compile(r"^(?:[A-Za-z]|\{[^{}]*\}|<[^<>]*>)$")
# 行级指引护栏:命中即视为「这一行在解释 DSL 形态」,不作断言来源
GUIDE_GUARD_RE = re.compile(r"形态|DSL|例\s*[:：]|例如|示范|复用同一")
# 任意标题行 / 用例块标题行。断言**只在用例块内收集**(标题命中 CASE_HEADING_RE 之后、
# 下一个标题之前),⛔ 不扫章节散文。
# ⚠️ 这不是可有可无的收窄:规范/方法论类文档正文**必然**要写出
#    `断言(反向):不存在文本"旧口径字样"` 这类**举例**才能把规则讲清楚,按整篇扫会逐条判它
#    「漏登记」(实测假红:`quality-review-checklist.md` 维度 18 讲 `[文案一致性]` 反向用例那一行;
#    而按**文件级**信号挡不住——同一份 checklist 的 ✅/❌ 示例里就带着 `#### 用例 TC-USER-001` 标题)。
#    与 `check_metric_spec.py` 刻意不扫正文散文、`check_count_claim_table.py` 刻意不做缺表判定同一条纪律。
ANY_HEADING_RE = re.compile(r"^#{1,6}\s")
CASE_HEADING_RE = re.compile(
    r"^#{2,6}\s*(?:用例\s*)?TC-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*"
    r"|^#{2,6}\s*(?:测试)?套件\s*SUITE-")

# ── 登记表 ──────────────────────────────────────────────────────────────────
REQUIRED_COLUMNS = ["#", "断言", "守护面", "实跑命令", "方向一", "方向二", "退役状态"]
PLACEHOLDER_CELL_RE = re.compile(r"^(?:[-—–]+|/|N/?A|TBD|待补|待填|同上|视情况|按业务|"
                                 r"\{[^{}]*\}|<[^<>]*>)$", re.IGNORECASE)
RETIRED_RE = re.compile(r"已退役")
# 「多轮未红」类非法退役理由
BAD_RETIRE_RE = re.compile(r"(?:多轮|很多轮|一直|从来|从未|始终)[^。;；]{0,8}(?:未红|没红|没有红|常绿)"
                           r"|没红过|未红过|一直是绿|恒绿")
# 「已退役」这个标记本身 + 纯标点。把它从格子里剔干净后**还剩什么都没有** = 一条依据都没写。
# ⚠️ 首版判据是「格子里没有 `;` `:` `(` 之类标点 → Z5」,实测假红:
#    `已退役 Sprint-046 守护对象已消失整个页面已删除` 这种**轮次与依据都写全了、只是没用标点**
#    的格子被判 Critical。Z5 是 Critical,而判据实际测的是标点习惯、不是「有没有写依据」。
#    改为「剔掉标记与标点后是否为空」——只覆盖「光秃秃一个 `已退役`」这一种明确形态,
#    符合本仓库「新判据宁可窄到只覆盖一种明确形态」。至于依据够不够格(是不是那两条合法路径),
#    属语义层、由 QR 子 Agent 判;BAD_RETIRE_RE 仍兜住最高频的那种非法依据。
RETIRE_DETAIL_RE = re.compile(r"已退役|[-—–()（）\[\]【】:：;；,，。、/\\.]")
# 命中数:`3 命中` / `3 处命中`(模板规定形态)与 `命中 3 处` / `命中 3`(中文里同样自然的语序)都认。
# ⚠️ 只认一种语序实测会假红:`→ 命中 1 处` 被判成「读不到 N 命中」→ Z4 Critical,
#    而那格明明填实了。Z4 是 Critical,假红的代价远高于多认一种写法。
HIT_RE = re.compile(r"(\d+)\s*(?:处)?\s*命中|命中\s*(\d+)\s*(?:处|次)?")
# 实跑命令的前置声明
# ⚠️ 「默认取材方式」已由行级 grep 前置改为**块级剥离** `strip_comments.py`(它把行级方案的
#    三个漏面——块中间行 / 跨行块中间行 / 行尾注释——一次关掉),故此处必须认它;
#    行级前置保留为退路,仍认。`--only-comments` 是「断言目标本身就是注释」的合法形态。
PREFIX_OK_RE = re.compile(
    r"strip_comments|块级剥离|默认前置|默认取材|grep\s+-v|only-comments|关闭注释前置|关闭前置|只扫注释|行级前置|不加前置")


def hit_counts(cell: str) -> List[int]:
    """从一个方向格里读出全部命中数。

    ⚠️ `HIT_RE` 有两个候选组(两种语序),`findall` 会返回 `('3', '')` 这样的元组 ——
       必须按组取非空的那个,⛔ 不能直接 `int(x)`(会在空串上抛 ValueError)。
    """
    out: List[int] = []
    for m in HIT_RE.finditer(cell):
        raw = m.group(1) or m.group(2)
        if raw:
            out.append(int(raw))
    return out


def find_md_files(path: Path) -> List[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(path.rglob("*.md"))
    return []


def split_row(line: str) -> List[str]:
    r"""按未转义的 `|` 切列。

    ⚠️ 必须用 `(?<!\\)\|` 而不是裸 `split('|')`:登记表的「实跑命令」列会出现
       ``grep ... \| grep -vE ...`` 这类**已按 GFM 规矩转义**的管道,裸切会把合规行切多一格、
       当场判成 Z7(自家模板被自家硬门判死)。
    """
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


def cell_matches_column(cell: str, concept: str) -> bool:
    c = _norm(cell)
    if concept == "#":
        return c in ("#", "序号", "编号", "No", "no")
    if concept == "断言":
        return "断言" in c and "方向" not in c
    if concept == "守护面":
        return "守护面" in c or "守护范围" in c
    if concept == "实跑命令":
        return "实跑命令" in c or "命令" in c or "式子" in c
    if concept == "方向一":
        return "方向一" in c or "现状命中" in c
    if concept == "方向二":
        return "方向二" in c or "阳性对照" in c
    if concept == "退役状态":
        return "退役" in c
    return False


def col_index(cells: List[str], concept: str) -> Optional[int]:
    for idx, c in enumerate(cells):
        if cell_matches_column(c, concept):
            return idx
    return None


# 「专名列」:这三个概念在本 SKILL 其它任何表的**表头**里都不出现,命中任一即认定这是登记表
SIGNATURE_COLUMNS = ("守护面", "退役状态", "方向二")


def is_registry_header(cells: List[str]) -> bool:
    """签名判定:命中任一「专名列」+ 至少 3 个契约列 = 零残留断言登记表。

    ⚠️ 不靠标题识别(标题写法会漂:带序号前缀 / 「零残留断言登记」/「残留断言表」)。

    ⚠️ **首版要求「守护面 AND 退役」两列同时在,实测是个洞、勿改回**:那样一来,
       **恰恰是把这两列之一删掉**的表会整张认不出来 —— 表被跳过 → 数据行一行不解析 →
       Z2/Z3/Z4/Z5/Z7 全部够不着、Z6 又因 `has_table=False` 被抑制,最终只剩一条
       Z1(Important)、**exit 0**。而「守护面」正是本子条口口声声「必须导出、不得手写」的那一列:
       删掉它反而比删掉「实跑命令」(Z2 Critical)判得更轻,严重度完全反了。
       实测:缺【守护面】→ exit 0 只报 Z1;缺【退役状态】→ exit 0 只报 Z1;
       缺【实跑命令】→ exit 1 报 Z2 Critical。改为「专名列任一 + ≥3 契约列」后三者一致判 Z2。

    ⚠️ 「≥3 个契约列」这道下限是**防误认**,不是防漏:真有别的表只带一个「退役」字样的列时
       (概念上不该有,留个兜底),不会因此被整张当成登记表逐格判空。
    """
    if not any(col_index(cells, c) is not None for c in SIGNATURE_COLUMNS):
        return False
    hits = sum(1 for c in REQUIRED_COLUMNS if col_index(cells, c) is not None)
    return hits >= 3


def strip_code_fences(lines: List[str]) -> List[bool]:
    """返回逐行的「在代码围栏内」标记(围栏行本身也算 True)。"""
    flags = [False] * len(lines)
    inside = False
    for i, ln in enumerate(lines):
        if ln.lstrip().startswith("```"):
            flags[i] = True
            inside = not inside
            continue
        flags[i] = inside
    return flags


def collect(path: Path) -> Tuple[Dict[str, dict], List[dict], List[dict], int, int]:
    """返回 (断言键 -> 出处, 登记行, 结构性问题, 已读文件数, 见到的登记表张数)。"""
    assertions: Dict[str, dict] = {}
    rows: List[dict] = []
    issues: List[dict] = []
    read_ok = 0
    tables_seen = 0

    for f in find_md_files(path):
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            issues.append({"level": "Important", "code": "read_error",
                           "file": str(f), "line": 0,
                           "msg": "文件读不出来(%s),已跳过——⛔ 不得据此判该文件无违规" % e})
            continue
        read_ok += 1
        lines = text.split("\n")
        in_fence = strip_code_fences(lines)
        in_case_block = False

        header: Optional[List[str]] = None
        hidx: Dict[str, int] = {}
        for i, ln in enumerate(lines):
            if in_fence[i]:
                continue
            if ANY_HEADING_RE.match(ln):
                in_case_block = bool(CASE_HEADING_RE.match(ln))
            # ① 收集断言(仅用例块内;章节散文里的举例不算)
            if in_case_block and not GUIDE_GUARD_RE.search(ln):
                for m in ASSERT_RE.finditer(ln):
                    key = _norm(m.group(1))
                    if PLACEHOLDER_TEXT_RE.match(m.group(1).strip()):
                        continue
                    assertions.setdefault(key, {"text": m.group(1),
                                                "file": str(f), "line": i + 1})
            # ② 解析登记表
            if not ln.lstrip().startswith("|"):
                header = None
                continue
            cells = split_row(ln)
            if is_separator_row(cells):
                continue
            if header is None:
                if is_registry_header(cells):
                    header = cells
                    tables_seen += 1
                    hidx = {}
                    for concept in REQUIRED_COLUMNS:
                        j = col_index(cells, concept)
                        if j is None:
                            issues.append({
                                "level": "Critical", "code": "Z2", "file": str(f),
                                "line": i + 1,
                                "msg": "登记表缺列「%s」(7 列固定契约:%s)"
                                       % (concept, " | ".join(REQUIRED_COLUMNS))})
                        else:
                            hidx[concept] = j
                continue
            # 数据行
            if len(cells) != len(header):
                issues.append({
                    "level": "Critical", "code": "Z7", "file": str(f), "line": i + 1,
                    "msg": "数据行 %d 格、表头 %d 格——最常见根因是「实跑命令」里的 `|` "
                           "未转义为 `\\|`(GFM 里 `|` 是列分隔符,反引号保护不了它)"
                           % (len(cells), len(header))})
                continue
            row = {"file": str(f), "line": i + 1, "cells": cells}
            for concept, j in hidx.items():
                row[concept] = cells[j] if j < len(cells) else ""
            rows.append(row)
        # 文件结束
    return assertions, rows, issues, read_ok, tables_seen


def judge(assertions: Dict[str, dict], rows: List[dict],
          issues: List[dict], has_table: bool) -> List[dict]:
    out = list(issues)
    # ⚠️ 整个扫描范围里**一张登记表都没有**时不报 Z6:那是 Z1(Important,存量文档会大面积命中)
    #    要表达的事。若此处照报 Z6(Critical),**每一份存量文档都会被判死**——
    #    Z1 刻意降 Important 的取舍当场被自己抵消掉,与「假红常驻 = 硬门被绕过」是同一个坑。
    # ⚠️ 同理,某文件出现 Z7(行格数不符)时该行已被丢弃,再报它「漏登记」是**同一根因的第二条噪声**,
    #    只会把排查从「管道没转义」带偏到「是不是忘了登记」,故一并抑制。
    z7_seen = any(f.get("code") == "Z7" for f in issues)
    registered: Dict[str, dict] = {}

    for row in rows:
        retired = bool(RETIRED_RE.search(row.get("退役状态", "")))
        # Z3 逐格空或占位(已退役行的两个方向列豁免)
        for concept in REQUIRED_COLUMNS:
            if concept not in row:
                continue
            if retired and concept in ("方向一", "方向二"):
                continue
            v = row[concept].strip()
            if v == "" or PLACEHOLDER_CELL_RE.match(_norm(v)):
                out.append({"level": "Critical", "code": "Z3", "file": row["file"],
                            "line": row["line"],
                            "msg": "「%s」格空或只有占位(`%s`)——不可核对等于没写" % (concept, v)})
        # Z4 阳性对照
        if not retired and "方向二" in row:
            hits = hit_counts(row["方向二"])
            if not hits:
                out.append({"level": "Critical", "code": "Z4", "file": row["file"],
                            "line": row["line"],
                            "msg": "「方向二·阳性对照」读不到 `N 命中`——只跑方向一的断言"
                                   "可能是「式子写错、永远不会命中」的恒 0 假绿"})
            elif max(hits) < 1:
                out.append({"level": "Critical", "code": "Z4", "file": row["file"],
                            "line": row["line"],
                            "msg": "「方向二·阳性对照」命中数为 0——必然命中的样本却没命中,"
                                   "说明这条式子根本红不了"})
        # Z4(方向一) + W3 方向一 > 0
        if not retired and "方向一" in row:
            h1 = hit_counts(row["方向一"])
            if not h1:
                out.append({"level": "Critical", "code": "Z4", "file": row["file"],
                            "line": row["line"],
                            "msg": "「方向一·现状命中」读不到 `N 命中`——「已验证通过」这类结论"
                                   "无法与「根本没跑」区分,须记下实跑得到的命中数(通常是 0)"})
            elif max(h1) > 0:
                out.append({"level": "Important", "code": "W3", "file": row["file"],
                            "line": row["line"],
                            "msg": "「方向一·现状命中」为 %d,现状仍有残留(是测试结论不是文档缺陷)"
                                   % max(h1)})
        # Z5 退役理由
        if retired:
            reason = row.get("退役状态", "")
            if BAD_RETIRE_RE.search(reason):
                out.append({"level": "Critical", "code": "Z5", "file": row["file"],
                            "line": row["line"],
                            "msg": "以「多轮未红」类理由退役——常绿正是这类断言的正常状态,"
                                   "按它退役等于专挑还在生效的断言删"})
            elif not RETIRE_DETAIL_RE.sub("", _norm(reason)):
                out.append({"level": "Critical", "code": "Z5", "file": row["file"],
                            "line": row["line"],
                            "msg": "`已退役` 后没有任何依据——形态须为 `已退役(轮次 + 依据)`,"
                                   "依据只有「守护对象已消失」「判据已移交常设机制」两条合法路径"})
        # W2 前置声明
        if "实跑命令" in row and not PREFIX_OK_RE.search(row["实跑命令"]):
            out.append({"level": "Important", "code": "W2", "file": row["file"],
                        "line": row["line"],
                        "msg": "「实跑命令」既没写 `默认前置` / `grep -v`,也没写明为何关闭注释前置"
                               "——与「忘了加」无法区分(口径见方法论八之二)"})
        # 建索引(⚠️ 这里曾跟一句 `if "断言" not in row: continue` —— 它是循环体最后一句、
        #   等价于什么都不做的死代码,已删)
        for m in ASSERT_RE.finditer(row.get("断言", "")):
            registered[_norm(m.group(1))] = row

    # Z6 跨文件聚合比对
    for key, meta in sorted(assertions.items()):
        if not has_table or z7_seen:
            break
        if key not in registered:
            out.append({"level": "Critical", "code": "Z6", "file": meta["file"],
                        "line": meta["line"],
                        "msg": "零残留断言「不存在文本\"%s\"」未登记进「零残留断言登记表」"
                               % meta["text"]})
    # ⚠️ 刻意**不做**反向的「登记表里有、文档里找不到」检查:增量模式下登记表是**累积表**
    #    (历史版本的断言逐条抄进来、其用例留在上一版文档里),那种状态是**正常工作流**而非缺陷,
    #    做成告警等于每轮固定刷一批噪声,而噪声常驻 = 整个硬门被无视(本仓库既有教训)。
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="零残留断言登记表硬核回检(dev-manual-testcase 维度 18 子条)")
    ap.add_argument("path", help="用例目录或单个 .md 文件")
    ap.add_argument("--json", action="store_true", help="输出 JSON(供 Agent 解析)")
    args = ap.parse_args()

    target = Path(args.path)
    # ⚠️ exists() 与 is_dir() 必须分开判:合并写会把「路径根本不存在」和「传入单个文件=合法」
    #    混为一谈,手滑写错路径等于整个检查静默放行(全仓退出码约定第 2 条)。
    if not target.exists():
        print("路径不存在: %s" % target, file=sys.stderr)
        return 2
    files = find_md_files(target)
    if not files:
        print("未找到任何 .md 文件: %s" % target, file=sys.stderr)
        return 2

    scope = "single-file" if target.is_file() else "directory"
    assertions, rows, issues, read_ok, tables_seen = collect(target)
    if read_ok == 0:
        print("全部 .md 文件不可读: %s" % target, file=sys.stderr)
        return 2

    # ⚠️ 读不出来的文件**必须一路带到输出**,⛔ 不能因为「剩下的文件里没有断言」就随 skipped 一起丢掉。
    #    实测:一个可读的无关 .md + 一个不可读的用例册 → 首版打「⏭ 跳过:扫描范围里
    #    没有零残留断言」+ exit 0,而那册里可能正躺着 8 条断言 —— 这正是全仓退出码约定第 3 条
    #    「读失败绝不可静默计为通过」要消灭的形态。姊妹脚本 `check_fidelity_suite.py` 也是无条件
    #    输出 `read_errors`,口径须一致。
    read_errors = [f for f in issues if f.get("code") == "read_error"]
    skipped = not assertions and not rows and not tables_seen and not read_errors
    findings: List[dict] = []
    if not skipped:
        findings = judge(assertions, rows, issues, tables_seen > 0)
        if assertions and not tables_seen:
            findings.insert(0, {
                "level": "Important", "code": "Z1",
                "file": str(target), "line": 0,
                "msg": "扫描范围里有 %d 条零残留断言,却找不到「零残留断言登记表」"
                       "(7 列:%s)" % (len(assertions), " | ".join(REQUIRED_COLUMNS))})

    criticals = [f for f in findings if f["level"] == "Critical"]
    warns = [f for f in findings if f["level"] != "Critical"]
    note = None
    if scope == "single-file":
        note = ("传入的是单个文件:Z1(缺表)与 Z6(漏登记)是跨文件聚合判定,"
                "多册拆分时登记表常落在总览册、断言散在模块册——本次结论按「未全范围核验」看待")

    if args.json:
        print(json.dumps({
            "path": str(target), "scope": scope, "skipped": skipped,
            "files": read_ok, "assertions": len(assertions), "rows": len(rows),
            # ⚠️ read_errors > 0 时,`assertions`/`rows` 是**残缺样本**上算出来的,
            #    「0 条断言」不代表真没有断言;调用方须先看这一项再读结论。
            "read_errors": len(read_errors),
            "critical": len(criticals), "important": len(warns),
            "aggregation_scope_note": note,
            "findings": findings,
        }, ensure_ascii=False, indent=2))
        return 1 if criticals else 0

    if skipped:
        print("⏭  跳过:扫描范围里没有零残留断言(`断言(反向):不存在文本\"X\"`)。")
        print("   ⚠️ 跳过 ≠ 通过——表该不该有由 QR 子 Agent 判。")
        return 0

    print("扫描 %d 个文件 · 零残留断言 %d 条 · 登记行 %d 行"
          % (read_ok, len(assertions), len(rows)))
    if not findings:
        print("✅ 零残留断言登记表检查通过(Critical 0 / Important 0)")
    else:
        for f in findings:
            loc = "%s:%d" % (f["file"], f["line"]) if f["line"] else f["file"]
            print("  [%s] %s  %s — %s" % (f["level"], f["code"], loc, f["msg"]))
        print("\n结论:Critical %d / Important %d" % (len(criticals), len(warns)))
    # ⚠️ 作用域告警打在结论**之后**:读者的视线停在最后一行,写在前面等于没写。
    if note:
        print("⚠️ %s" % note)
    return 1 if criticals else 0


if __name__ == "__main__":
    sys.exit(main())
