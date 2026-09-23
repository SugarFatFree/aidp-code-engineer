#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""「列表页数据量级与分页策略子表」硬核回检 — dev-logic-architect 核心原则 26(折入检查项 5)

对应上下游共用的通用规则 **约定39-R13**。
⚠️ 引用一律写全称 `约定39-RNN`:本 SKILL 的 `R1/R2/R3` 已被**上游溯源三项**占用
   (见 `check_upstream_reference.py`),裸写 `R13` 必与之混淆。

立论:核心原则 26 若只有 QR 子 Agent 的语义核对,量级声明漏写时**不会有任何东西报红**。
⛔ 不要把 R13 挂到 `check_metric_spec.py` 名下——它的 REQUIRED_COLUMNS 只有 8 列口径表那套,
全文零处 R13 / 量级 / 分页判据,挂错会造成「有机器门兜着」的**假安全感**;R13 的硬门是本脚本。

本脚本做**结构性硬核回检**(只判可靠判定的结构缺陷):

【Critical(计入退出码 1)】
  S2 缺列        —— 表存在但 5 列固定契约不齐:
                    列表页 | 预期最大数据量级 | 分页策略 | 单页条数 | 大数据量用例要求
  S3 空格/占位   —— 任一格为空、占位符、或「视情况(而定)/按业务(定)」这类不可核对表述
                    (⚠️ 这类词**全串锚定**才判:「需要:按业务场景造 3000 条」是合格的)
  S4 量级不可核对 —— 量级格命中「较多/视业务而定/数据量大/按实际情况」等禁词,
                    或**整格解析不出任何数字与中文量级词**(核心原则 26 明令「须是可核对的数字或数量级」)
  S5 全量不分页超量级 —— 分页策略选「全量不分页」而解析出的量级 > 200
                    (核心原则 26 的硬性条件,纯算术、零语义)
  S6 数据行格数不符 —— 点名 `|` 未转义为 `\|`

【Important(仅 --json 可见,不占退出码)】
  S1 缺子表      —— 有列表页信号(标题级)却找不到子表
  W1 全量不分页无理由 —— 选「全量不分页」但整行找不到任何理由痕迹
  W2 量级千级以上却不要用例 —— 量级 ≥ 1000 而「大数据量用例要求」格填「不需要/否/无」

⚠️ **S1 缺表刻意判 Important、不判 Critical** —— 与 `check_upstream_call_log_spec.py` 的 U1、
   `check_column_consumer_evidence.py` 的 E1、`check_residual_assertions.py` 的 Z1 是**同一个取舍**:
   存量设计会大面积命中,一上来判死会让整个硬门被无视(本仓库既有教训:假红常驻 = 硬门被绕过)。
   表**一旦产出**,列不齐 / 格子空 / 量级写废话就是新产物自身的缺陷,那几条才判 Critical。
   ⚠️ **严重度分档是给退出码用的、不是给维度结论用的** —— 检查项 5 的结论仍按 S1 判不通过。
   ⚠️ 与之配套:**一张表都没有时只报 S1、不报 S2~S6**,否则存量设计仍被逐列判死、
   S1 降 Important 的取舍会被自己当场抵消(dmtc 的 Z1/Z6、architect 的 E1/E7 都实测踩过这个洞)。

⚠️ **信号只认标题行,刻意不扫正文散文** —— 与 `check_metric_spec.py` 同纪律。
   设计文档正文几乎必然出现「分页」「列表」二字(参数列表 / 枚举列表 / 接口列表 / 分页参数),
   扫正文会让每份合规设计满屏假红。

⚠️ 本脚本**不做**语义判定(这个量级估得准不准、该不该上虚拟滚动、用例要求写得够不够),
   那由 QR 子 Agent 按 `references/quality-review-checklist.md` 检查项 5 的
   「📊 列表页数据量级与分页策略子项」对照 PRD / 原型逐行判。**脚本全绿 ≠ 检查项 5 通过。**

与既有脚本的边界:`check_metric_spec.py`(检查项 34 / 约定39-R11+R12)管**一个数字怎么算出来**
(单位/精度/时间窗/统计范围/取数粒度);本脚本管**这一页会有多少条、怎么翻**。两者零交叠。

用法:
    python3 check_list_page_scale.py <设计文档路径或目录> [--json]

⚠️ **S1 是「一张表都没有」时才报的聚合判定** —— 只要范围内已存在 ≥1 张子表,
   哪怕还有别的列表页没登记进去,本脚本也**不会**再报 S1(它比不出「该有几行」)。
   即**「有表 + 漏页」这一类脚本查不出来**,权威判定在检查项 5 核验步骤 1 的人工逐页枚举。

退出码:
    0 = 通过,或跳过(确无列表页信号且无子表)
    1 = 检出 Critical(严重度分档读 --json,不占用退出码)
    2 = 入参或环境错(路径不存在、目录下没有 .md、**全部** .md 都读不出来)
        ⚠️ **部分**文件读不出来时不判 2:继续扫其余文件,把它们计入 `--json` 的
           `read_errors[]` 并在人读输出里告警(全仓统一口径,见 scan_file 注释)。

仅依赖 Python 3.8+ 标准库。
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

# ── 5 列固定契约(与 quality-review-checklist.md 检查项 5 子项、output-module-examples.md 严格一致) ──
REQUIRED_COLUMNS = ["列表页", "预期最大数据量级", "分页策略", "单页条数", "大数据量用例要求"]

EMPTY_MARKERS = {
    "", "-", "—", "–", "─", "n/a", "na", "/", "\\", "待定", "tbd", "todo",
    "?", "??", "待补", "待确认", "暂无", "...", "…", "xxx",
    "同上", "略", "按实际", "按实际调整", "视情况", "按业务", "视业务而定", "见上", "同前", "同左",
}

# ⚠️「单页条数」列允许「—」「不适用」——全量不分页时本就没有单页条数,
#    这是 output-module-examples.md canonical 示例里**真实存在**的写法(`| 不适用 |`)。
#    不开这个口子 = 自家模板被自家硬门判死(check_error_contract.py 踩过同型的坑)。
PAGE_SIZE_EXEMPT = {"-", "—", "–", "不适用", "n/a", "na", "无", "不涉及"}

# ⚠️ 必须**全串锚定**:只有"整格就是一个占位符"才算未填。未锚尾会把
#    「单企业 ≤ {N} 员工」这种已填实、只留槽位的写法整格判空(与 check_error_contract.py 同一个坑)。
PLACEHOLDER_RE = re.compile(r"^\{[^{}]*\}$|^<[^<>]+>$")

# ⚠️ 不可核对表述的**后缀形态**。`EMPTY_MARKERS` 是**全串精确**集合,
#    于是「视情况**而定**」「按业务**定**」「视需要**确定**」这些自然写法一个都抓不到,
#    而 docstring / `flow-qr-dispatch.md` / `quality-review-checklist.md` 三处都写着
#    S3 抓「视情况·按业务」这类表述 —— 自述与实现不符,且方向是假绿。
# ⛔ **必须全串锚定、⛔ 不许改成 `search`** —— 「需要:**按业务**场景造 3000 条」是合格的
#    大数据量用例要求,子串匹配会把它整格判空(假红)。
VAGUE_CELL_RE = re.compile(
    r"^(视情况|视业务|视需要|按业务|按实际|按需|看情况|另行确认|后续确认|再定|待评估|待定)"
    r"(而定|定|确定|调整|处理|安排|评估)?$")

# 量级不可核对禁词(核心原则 26 逐字点名的那几个 + 同族)
SCALE_BAN_RE = re.compile(
    r"较多|较少|很多|不多|视业务(而定)?|按业务|视情况|按实际情况|按实际|数据量大|数据量不大|"
    r"量大|不大|适中|一般|未知|不确定|待评估|看情况|根据实际")

# 列表页信号:**只认标题行**,且只认**字面点名了"页"**的那几种形态。
# ⚠️⚠️ 实测收窄过一次,⛔ 别再把「分页」「列表查询」「列表接口」加回来:
#   首版含「分页」,在本仓库两处当场假红 ——「8. 分页查询系统需求列表」(接口契约章节)、
#   「分页 page_size 上限」(SDK 约束文档),两者都是**接口层**而非"给用户翻的页面",
#   而 B.2 接口设计里这类标题在每份真实详设中都必然成批出现 → 合规设计满屏 S1。
# 代价是**欠覆盖**:标题写「#### 用户管理」而没写"列表页"的设计扫不到。这笔账是刻意认的 ——
#   S1 本就是 Important、且检查项 5 的核验步骤 1 要求 QR 子 Agent **从 B.1/原型/PRD 逐页枚举**,
#   存在性这一层的权威判定在人不在脚本;脚本的价值在 S2~S6(表一旦产出的结构缺陷)。
LIST_SIGNAL_RE = re.compile(r"列表页|表格页|虚拟滚动|无限滚动|列表展示")

# ⚠️ 标题级否定护栏(与 check_metric_spec.py 同款,勿删)。设计文档里
#    「问题清单 / 变更记录 / 选型对比」这类**流程性**标题极常见,与「给用户翻的列表页」无关;
#    末段是**元文档**标题——本 SKILL 自己的 checklist / 核心原则文档会大量使用,
#    不加这一段,脚本会把自家规范文档判死。
LIST_SIGNAL_NEG_RE = re.compile(
    r"确认|问题|风险|变更|评审|清单|规范|流程|附录|目录|索引|待澄清|自检|决策|选型|对比|术语|归档"
    r"|检查项|维度\s*\d|核心原则|判据|核验清单|硬门|脚本|反模式|示例|模板")

# 章节级豁免:标题命中即整节跳过(含其子标题),与 check_lock_strategy.py / check_metric_spec.py 同款。
EXEMPT_HEADING_RE = re.compile(r"不适用|未采用|备选方案|方案对比|识别清单|反模式|已废弃|作废")

# 「全量不分页」判定(归一化后比对)
FULL_LOAD_RE = re.compile(r"全量不分页|不分页|一次性全量|全量加载")
# 理由痕迹(整行任一格命中即算写了理由)。刻意宽松:两份 canonical 示例把理由放在**不同的格子**里
#   —— checklist 放 分页策略格(`全量不分页(量级 ≤ 200,理由:...)`)、
#      output-module-examples 放 量级格(`≤ 30 条(产品侧硬限定)`)。
#   按某一格判 = 判死另一份自家模板。
REASON_RE = re.compile(r"理由|原因|因为|因[^次]|限定|限制|上限|固定|硬性|产品侧|业务上限|封顶")
# 「不需要大数据量用例」判定
NO_BIG_CASE_RE = re.compile(r"^(不需要|否|无|不用|非必要|不涉及)$")

# ⚠️ 日期/年份必须在解析量级**之前**剥掉。`parse_scale` 取的是
#    整格里的**最大**数,而量级格里写采集/确认时间是本仓库的既有习惯(核心原则 23 就要求
#    「来源与采集时间」),于是合规行 `≤ 30 条(产品侧硬限定,2026-09 产品确认)` 会被解析成
#    **2026** —— 配「全量不分页」当场 S5(**Critical 假红**),配任何策略都多一条 W2 假红。
# ⛔ **只剥「明确是日期」的形态,裸 4 位数不剥** —— 「≤ 2000 条」的 2000 是真量级。
# ⚠️ `\d{1,2}(?!\d)` 的否定前瞻不可省:没有它,「预期 2000-5000 条」会被当成
#    「2000 年 50 月」剥成 `00 条` → 量级解析成 0,方向是假绿。
DATE_RE = re.compile(
    r"(?:19|20)\d{2}\s*[-/.年]\s*\d{1,2}(?!\d)(?:\s*[-/.月]\s*\d{1,2}(?!\d)\s*日?)?"
    r"|(?:19|20)\d{2}\s*年")

CN_UNIT = {"百": 100, "千": 1000, "万": 10000, "十万": 100000, "百万": 1000000, "亿": 100000000}
# 「几千」「数万」「上百」这类无阿拉伯数字但**可核对**的量级词
CN_VAGUE_RE = re.compile(r"(几|数|上|近|约)?\s*(百万|十万|亿|万|千|百)")


def find_md_files(path: Path) -> List[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(path.rglob("*.md"))
    return []


def split_row(line: str) -> List[str]:
    r"""按**未转义**的 `|` 切列。

    ⚠️ 必须用 `(?<!\\)\|` 而不是裸 `split("|")`:本表的量级/理由格里会出现
       `A \| B` 这类已按 GFM 规矩转义的内容,裸切会多出一格、合规行被自家硬门判 S6。
       ⚠️ 与 `check_fidelity_suite.py` 的 `split_row` **口径不同**(那边是裸 split),
          ⛔ 别顺手"统一"过去。
    """
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    return [c.strip() for c in re.split(r"(?<!\\)\|", s)]


def is_separator_row(cells: List[str]) -> bool:
    # ⚠️ 空行必须先判掉:split_row("") 得到 [""],过滤空格后 all() 对空序列返回 True,
    #    空行会被当成分隔行 → 「候选表头 + 空行」被识别成一张 0 行的表 → 凭空一条缺列 Critical。
    if not cells or all(c.strip() == "" for c in cells):
        return False
    return all(re.fullmatch(r":?-{1,}:?", c.replace(" ", "")) for c in cells if c != "")


def _norm(s: str) -> str:
    s = re.sub(r"[*`>\s]", "", s)
    return s.replace("（", "(").replace("）", ")")


# ⚠️ 表头单元格长度闸门:`AGENTS.md` 的 SKILL 清单表单格是几千字散文,
#    里面同时出现「列表页」「分页策略」「量级」,无长度闸门时整行被认成本表表头、一次假红数条。
#    (与 check_column_consumer_evidence.py 的 MAX_HEADER_CELL 是同一个实测坑。)
MAX_HEADER_CELL = 24


def cell_matches_column(cell: str, concept: str) -> bool:
    c = _norm(cell)
    if len(c) > MAX_HEADER_CELL:
        return False
    if concept == "列表页":
        return "列表页" in c or c in ("列表", "页面", "列表/页面") or ("列表" in c and "页" in c)
    if concept == "预期最大数据量级":
        # ⚠️ 末支必须排掉「用例」:本表两个列名**字面互相包含** ——
        #    「预期最**大数据量**级」含"大数据量"、「**大数据量**用例要求」含"数据量"。
        #    实测首版两列互认,`col_index` 左起首中把「大数据量用例要求」解析到了量级列(index 1),
        #    后果是 **S3/W2 整条静默失效**(变异 fixture 注回后零命中 = 假绿),且表头看着完全正常。
        #    两列的**唯一区分词是"用例"**,故两支各自排掉对方的专名词,⛔ 别只改一边。
        return ("量级" in c or "最大条数" in c or "预期条数" in c
                or ("数据量" in c and "用例" not in c))
    if concept == "分页策略":
        return "分页策略" in c or "分页方式" in c or c == "分页" or "加载策略" in c
    if concept == "单页条数":
        return "单页" in c or "每页" in c or "页大小" in c or "pagesize" in c.lower()
    if concept == "大数据量用例要求":
        # ⚠️ 见上一支的注释:必须以"用例"为主判据,否则会被「预期最大数据量级」抢走。
        return "用例" in c or ("大数据量" in c and "量级" not in c) or "性能验证" in c
    return False


def col_index(cells: List[str], concept: str) -> Optional[int]:
    for idx, c in enumerate(cells):
        if cell_matches_column(c, concept):
            return idx
    return None


def is_scale_table_header(cells: List[str]) -> bool:
    """签名判定:**「列表页」列 + ≥2 专有列** 或 **专有列 ≥3**(两条任一即认)。

    ⚠️ 门槛设在"能认出它想当这张表"的最低复合度上,**缺的列交给 S2 报** ——
       若要求 5 列全中,缺列的表整张不被识别,S2 永远报不出来(缺列反成假绿)。
    ⚠️ 专名列用「任一 + ≥N」而非「某两列同时在」:姊妹脚本 check_residual_assertions.py
       实测过那个洞——恰恰把被要求的那一列删掉的表整张认不出来、严重度完全反了。
    ⚠️⚠️ **`hits >= 3` 这一支 ⛔ 别删回「必须有列表页列」** ——
       首版把「列表页」写成**无条件前提**,于是把首列写成「页面名称」「页面」以外任何
       别名的表(实测 `| 页面名称 | 预期最大数据量级 | 分页策略 | 单页条数 | 大数据量用例要求 |`)
       **整张认不出来**:S2 本该报「缺列表页」,实际降级成 S1(Important) 甚至 skipped ——
       正是上一段引用的 check_residual_assertions.py C2 那个洞在本脚本里的原样复刻,
       且严重度方向完全反了(该 Critical 的反而更轻)。
       ⚠️ `>=3` 而不是 `>=2`:「大数据量用例要求」的匹配词含裸「用例」、门槛放到 2
       会让「用例 + 单页/每页」两列的**测试类表**被误认(与 MAX_HEADER_CELL 同属去噪闸门)。
    """
    hits = sum(1 for c in ("预期最大数据量级", "分页策略", "单页条数", "大数据量用例要求")
               if col_index(cells, c) is not None)
    if col_index(cells, "列表页") is not None:
        return hits >= 2
    return hits >= 3


def strip_code_fences(lines: List[str]) -> List[bool]:
    flags = [False] * len(lines)
    fence = None
    for i, ln in enumerate(lines):
        s = ln.lstrip()
        m = re.match(r"^(`{3,}|~{3,})", s)
        if m:
            tok = m.group(1)[0]
            if fence is None:
                fence, flags[i] = tok, True
                continue
            if tok == fence:
                flags[i], fence = True, None
                continue
        flags[i] = fence is not None
    return flags


def exempt_line_flags(lines: List[str], in_code: List[bool]) -> List[bool]:
    """章节级豁免:命中豁免词的标题起,到**同级或更高级**标题止,整段标 True。"""
    flags = [False] * len(lines)
    level = None
    for i, ln in enumerate(lines):
        if in_code[i]:
            flags[i] = level is not None
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", ln)
        if m:
            lv, title = len(m.group(1)), m.group(2)
            if level is not None and lv <= level:
                level = None
            if level is None and EXEMPT_HEADING_RE.search(title):
                level = lv
        flags[i] = level is not None
    return flags


def scan_scale_tables(lines: List[str], in_code: List[bool], exempt: List[bool]) -> List[Dict]:
    """扫出全部子表。**表头下一行必须是 GFM 分隔行** —— 否则散文里
    「旧版『列表页 | 量级 | 分页』三列表已作废」这类说明文字会被当成一张缺列的表。"""
    tables, i, n = [], 0, len(lines)
    while i < n:
        if in_code[i] or exempt[i] or "|" not in lines[i]:
            i += 1
            continue
        cells = split_row(lines[i])
        if len(cells) < 2 or is_separator_row(cells) or not is_scale_table_header(cells):
            i += 1
            continue
        if i + 1 >= n or not is_separator_row(split_row(lines[i + 1])):
            i += 1
            continue
        rows, j = [], i + 2
        while j < n and "|" in lines[j] and not in_code[j]:
            r = split_row(lines[j])
            if is_separator_row(r) or all(c.strip() == "" for c in r):
                j += 1
                continue
            rows.append({"line": j + 1, "cells": r})
            j += 1
        tables.append({"header_line": i + 1, "header": cells, "rows": rows})
        i = j
    return tables


def _cell(row: Dict, idx: Optional[int]) -> str:
    if idx is None:
        return ""
    cells = row["cells"]
    return cells[idx] if idx < len(cells) else ""


def _is_empty(val: str) -> bool:
    v = _norm(val)
    if v.lower() in EMPTY_MARKERS:
        return True
    if VAGUE_CELL_RE.match(v):
        return True
    return bool(PLACEHOLDER_RE.match(v))


def parse_scale(cell: str) -> Optional[int]:
    """从量级格解析出**最大**可核对量级;解析不出返回 None。

    支持:`5000` / `≤ 20000 条` / `3000+` / `2 万` / `几千条` / `上百条` / `10w`。
    ⚠️ 返回 None 即 S4(不可核对) —— 核心原则 26 明写「须是可核对的数字或数量级」。
    """
    c = DATE_RE.sub("", _norm(cell))
    best = None
    # ① 阿拉伯数字(可带 万/千/百/w/k 后缀)
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(亿|百万|十万|万|千|百|w|W|k|K)?", c):
        raw, unit = m.group(1), m.group(2)
        if raw == "" :
            continue
        val = float(raw)
        if unit:
            val *= {"亿": 100000000, "百万": 1000000, "十万": 100000, "万": 10000, "千": 1000,
                    "百": 100, "w": 10000, "W": 10000, "k": 1000, "K": 1000}[unit]
        best = val if best is None else max(best, val)
    # ② 纯中文量级词(「几千条」「数万」「上百」)
    for m in CN_VAGUE_RE.finditer(c):
        val = CN_UNIT[m.group(2)]
        best = val if best is None else max(best, val)
    return int(best) if best is not None else None


def check_table(tbl: Dict, rel: str) -> List[Dict]:
    findings = []
    header = tbl["header"]
    idx = {c: col_index(header, c) for c in REQUIRED_COLUMNS}
    missing = [c for c in REQUIRED_COLUMNS if idx[c] is None]
    if missing:
        findings.append({"code": "S2", "level": "Critical", "file": rel,
                         "line": tbl["header_line"],
                         "msg": "「列表页数据量级与分页策略子表」缺列: " + " / ".join(missing)
                                + "(5 列固定契约: " + " | ".join(REQUIRED_COLUMNS) + ")"})
    ncol = len(header)
    for row in tbl["rows"]:
        ln, cells = row["line"], row["cells"]
        if len(cells) != ncol:
            # ⚠️ S6 刻意单列、不并进 S2:表象是"列数不符",并进去只会报"表头 5 列不齐"、
            #    把排查带偏到表头上,而真因通常是正文里的 `|` 没转义。
            findings.append({"code": "S6", "level": "Critical", "file": rel, "line": ln,
                             "msg": "数据行 %d 格 ≠ 表头 %d 格;最常见真因是格内 `|` 未转义为 `\\|`"
                                    "(GFM 里 `|` 是列分隔符,**反引号代码段保护不了它**)" % (len(cells), ncol)})
            continue
        page_name = _cell(row, idx["列表页"]) or "(未命名)"
        # S3 逐格空/占位
        for c in REQUIRED_COLUMNS:
            if idx[c] is None:
                continue
            val = _cell(row, idx[c])
            if c == "单页条数" and _norm(val).lower() in PAGE_SIZE_EXEMPT:
                continue
            if _is_empty(val):
                findings.append({"code": "S3", "level": "Critical", "file": rel, "line": ln,
                                 "msg": "「%s」行的「%s」格为空或占位(值: %r);"
                                        "不可核对等于没写" % (page_name, c, val)})
        scale_cell = _cell(row, idx["预期最大数据量级"]) if idx["预期最大数据量级"] is not None else ""
        strategy = _norm(_cell(row, idx["分页策略"])) if idx["分页策略"] is not None else ""
        scale = parse_scale(scale_cell)
        # S4 量级不可核对
        if idx["预期最大数据量级"] is not None and not _is_empty(scale_cell):
            if SCALE_BAN_RE.search(_norm(scale_cell)):
                findings.append({"code": "S4", "level": "Critical", "file": rel, "line": ln,
                                 "msg": "「%s」行的量级写成不可核对表述(值: %r);"
                                        "核心原则 26 明令须是**可核对的数字或数量级**" % (page_name, scale_cell)})
            elif scale is None:
                findings.append({"code": "S4", "level": "Critical", "file": rel, "line": ln,
                                 "msg": "「%s」行的量级格里解析不出任何数字或中文量级词(值: %r);"
                                        "须写成「单企业 ≤ 5000 员工」「几千条」这类可核对形态" % (page_name, scale_cell)})
        # S5 / W1 全量不分页
        if FULL_LOAD_RE.search(strategy):
            if scale is not None and scale > 200:
                findings.append({"code": "S5", "level": "Critical", "file": rel, "line": ln,
                                 "msg": "「%s」行选「全量不分页」而量级为 %d(> 200);"
                                        "核心原则 26 的硬性条件是量级 ≤ 200" % (page_name, scale)})
            joined = " ".join(cells)
            if not REASON_RE.search(joined):
                findings.append({"code": "W1", "level": "Important", "file": rel, "line": ln,
                                 "msg": "「%s」行选「全量不分页」但整行找不到理由痕迹;"
                                        "核心原则 26 要求量级 ≤ 200 **且**写明理由" % page_name})
        # W2 千级以上却不要大数据量用例
        if idx["大数据量用例要求"] is not None and scale is not None and scale >= 1000:
            big = _norm(_cell(row, idx["大数据量用例要求"]))
            if NO_BIG_CASE_RE.match(big):
                findings.append({"code": "W2", "level": "Important", "file": rel, "line": ln,
                                 "msg": "「%s」行量级 %d 已达千级,而「大数据量用例要求」填 %r;"
                                        "核心原则 26 要求千级以上须在 Module C 留大数据量场景用例"
                                        "(下游 dev-manual-testcase 消费这一列)" % (page_name, scale, big)})
    return findings


def has_list_signal(lines: List[str], in_code: List[bool], exempt: List[bool]) -> List[Dict]:
    hits = []
    for i, ln in enumerate(lines):
        if in_code[i] or exempt[i]:
            continue
        m = re.match(r"^#{1,6}\s+(.*)$", ln)
        if not m:
            continue
        title = m.group(1)
        if LIST_SIGNAL_RE.search(title) and not LIST_SIGNAL_NEG_RE.search(title):
            hits.append({"line": i + 1, "title": title.strip()})
    return hits


def scan_file(path: Path, root: Path) -> Dict:
    try:
        rel = str(path.relative_to(root))
    except ValueError:
        rel = path.name
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        # ⚠️ 读不出来 ≠ 没有违规:记 read_error。**全部文件都不可读时** main() 判入参/环境错
        #    (exit 2);**部分不可读**时继续扫其余文件、把它们进 `read_errors` 并在
        #    人读输出与 `--json` 里告警 —— 这是全仓登记的统一口径
        #    (check_metric_spec.py / check_upstream_call_log_spec.py /
        #     check_fidelity_suite.py / check_residual_assertions.py 四个姊妹脚本同款)。
        #    ⛔ 别改回「任一文件读不出来就整体 exit 2」:那样一个断链符号链接就能让
        #    **其余文件里已检出的 Critical 被整体丢弃**,而 exit 2 按全仓约定是
        #    「入参/环境错、不计维度失败」→ 整档静默没跑,方向是假绿。
        return {"file": rel, "read_error": str(exc), "tables": 0, "signals": [], "findings": []}
    lines = text.splitlines()
    in_code = strip_code_fences(lines)
    exempt = exempt_line_flags(lines, in_code)
    tables = scan_scale_tables(lines, in_code, exempt)
    signals = has_list_signal(lines, in_code, exempt)
    findings = []
    for t in tables:
        findings.extend(check_table(t, rel))
    return {"file": rel, "tables": len(tables), "signals": signals, "findings": findings}


def main() -> int:
    ap = argparse.ArgumentParser(
        description="「列表页数据量级与分页策略子表」硬核回检(核心原则 26 / 约定39-R13)")
    ap.add_argument("target", help="设计文档路径或目录(多册拆分时**传目录**)")
    ap.add_argument("--json", action="store_true", help="输出 JSON 供 Agent 解析")
    args = ap.parse_args()

    target = Path(args.target)
    # ⚠️ exists() 与 is_dir() 必须分开判:合并成 `if not is_dir(): return 0` 会把
    #    「路径根本不存在」和「传入单个 .md = 合法的 N/A」混为一谈 → 手滑写错路径等于静默放行。
    if not target.exists():
        print("[错误] 路径不存在: %s" % target, file=sys.stderr)
        return 2
    files = find_md_files(target)
    if not files:
        print("[错误] 目标下没有 .md 文件: %s" % target, file=sys.stderr)
        return 2

    root = target if target.is_dir() else target.parent
    results = [scan_file(f, root) for f in files]
    # ⚠️ **只有全部文件都读不出来**才是环境错(exit 2)。部分不可读时继续跑完其余文件,
    #    否则一个断链符号链接 / 一个非 UTF-8 文件就能让已检出的 Critical 被整体丢弃,
    #    而 exit 2 按全仓约定会被调用方当成「不计维度失败」→ 整档静默没跑(假绿)。
    read_errors = [r for r in results if r.get("read_error")]
    if read_errors and len(read_errors) == len(results):
        for r in read_errors:
            print("[错误] 无法读取 %s: %s" % (r["file"], r["read_error"]), file=sys.stderr)
        return 2

    total_tables = sum(r["tables"] for r in results)
    all_signals = [dict(s, file=r["file"]) for r in results for s in r["signals"]]
    findings = [f for r in results for f in r["findings"]]

    # ⚠️ S1 是**跨文件聚合判定**(与 check_metric_spec.py 的 M1、
    #    check_upstream_call_log_spec.py 的 U1 同一个坑):M/L 档强制多册拆分时,
    #    子表落在库表设计册、而带「列表页/分页」字样的标题散落在详设册与接口册,
    #    逐文件判必假红。故调用方须传目录。
    if total_tables == 0 and all_signals:
        findings.append({
            "code": "S1", "level": "Important",
            "file": all_signals[0]["file"], "line": all_signals[0]["line"],
            "msg": "检出 %d 处列表页信号(如「%s」)却找不到「列表页数据量级与分页策略子表」;"
                   "核心原则 26 要求每个列表页一行。⚠️ 本条判 Important 只是为了不阻断存量设计的退出码,"
                   "**检查项 5 的结论仍按不通过处理**"
                   % (len(all_signals), all_signals[0]["title"])})

    # ⚠️ 有 read_error 时 `skipped` 必须为 false —— 「有文件没读成」与「确实什么都没有」
    #    绝不能在报告里长成同一个样子(与 check_residual_assertions.py 同款)。
    skipped = (total_tables == 0 and not all_signals and not read_errors)
    criticals = [f for f in findings if f["level"] == "Critical"]
    importants = [f for f in findings if f["level"] == "Important"]

    if args.json:
        print(json.dumps({
            "target": str(target), "scanned_files": len(files),
            "tables": total_tables, "list_signals": len(all_signals),
            "skipped": skipped,
            "critical": len(criticals), "important": len(importants),
            # ⚠️ read_errors 非空时,`tables`/`list_signals`/`findings` 是**残缺样本**上算出来的,
            #    ⛔ 不得据此判「这些文件没有违规」。
            "read_errors": [{"file": r["file"], "error": r["read_error"]} for r in read_errors],
            "findings": findings,
        }, ensure_ascii=False, indent=2))
    else:
        print("=" * 72)
        print("列表页数据量级与分页策略子表 回检(核心原则 26 / 约定39-R13)")
        print("=" * 72)
        print("扫描文件: %d  子表: %d  列表页信号: %d" % (len(files), total_tables, len(all_signals)))
        if skipped:
            print("\n[跳过] 未检出列表页信号、也没有子表 —— 本项不适用(N/A)。")
        if not findings:
            print("\n✅ 未检出结构性违规。")
            print("⚠️ 脚本全绿 ≠ 检查项 5 通过:量级估得准不准、该不该上虚拟滚动,由 QR 子 Agent 语义核对。")
        else:
            for lvl, items in (("🔴 Critical", criticals), ("🟡 Important", importants)):
                if not items:
                    continue
                print("\n%s (%d)" % (lvl, len(items)))
                for f in items:
                    print("  [%s] %s:%s  %s" % (f["code"], f["file"], f["line"], f["msg"]))
        for r in read_errors:
            print("  ⚠️ 未能读取(未参与检查,不等于干净): %s — %s" % (r["file"], r["read_error"]))
        print("\n退出码: %d" % (1 if criticals else 0))
    return 1 if criticals else 0


if __name__ == "__main__":
    sys.exit(main())
