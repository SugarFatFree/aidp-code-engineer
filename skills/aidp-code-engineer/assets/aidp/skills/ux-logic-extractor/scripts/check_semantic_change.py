#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""语义/口径变更类需求 硬核回检 — ux-logic-extractor 维度 14(命令 10)

对研发 PRD 文档(.md)做**语义/口径变更类需求**识别 + 表 E/F 完整性硬核回检。

背景(实际项目缺陷):用量消费统计口径由「仅企业」扩为「企业+个人」,后端/接口/前端取数全改
对,但 6 处解释该数值的 tooltip 有 1 处未改、仍写"仅统计企业级、不含员工个人消费",与实际展示值相反、
误导对账。根因两缺口:① 现有级联是"新增/删除实体"驱动,覆盖不到"同一实体语义/口径/范围变更、页面零
新增元素"的场景;② 级联只版本内单向向下,无环节回头作废被本版推翻的历史需求。本脚本堵这两个缺口。

判据(判错型,三档退出码):
  语义变更信号命中 = 强信号词(口径/全口径/改为/扩展为/不再只/反转/默认开启/默认关闭/由…改成/由仅…改为/
                    含…消耗 等)任一命中,或弱信号词(范围/单位/默认值)与变更动词同行命中;
  笼统豁免命中     = "版式.*保持不变"/"仅数值变化"/"UI 不变"/"页面版式全部保持不变"/"指标项.*不变"/
                    "图表类型.*不变" 等笼统表述命中;
  表 E 存在        = 命中 6 列表头「变更项 | 变更前语义 | 变更后语义 | 受影响展示物 | 处置 | 新文案」;
  表 F 存在        = 命中表头「历史版本 | 需求编号 | 原结论 | 本版处置 | 理由」(report-only,不判错)。

  不通过(退出码 1) 当且仅当:表 E 缺失 且 (语义变更信号命中 或 笼统豁免命中)。
  即:① 判定为语义变更类需求却缺表 E → 判不通过;
      ② 出现笼统豁免表述("页面版式全部保持不变"等)却无表 E → 判不通过(严禁用笼统表述覆盖说明性文案)。
  表 F 存在性仅在命中语义变更时 report 提示(跨版本历史扫描超出本脚本能力,由 QR Agent 语义核验硬门)。

触发条件(grandfather):既无语义变更信号、又无笼统豁免表述 → 无可检项,退出码 0 放行。

用法:
  python check_semantic_change.py <PRD 文件或目录>
  python check_semantic_change.py <PRD 文件或目录> --json

退出码:
  0  通过(命中语义变更且表 E 齐备;或既无语义变更信号又无笼统豁免的 grandfather 放行)
  1  不通过(表 E 缺失 且 命中语义变更信号 或 命中笼统豁免表述)
  2  输入错误(路径不存在 / 无 .md 文件)——非维度违规,修正参数后重跑
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

# ── ① 语义变更信号词 ──────────────────────────────────────────────
# 强信号词:任一裸命中即判定为语义变更类需求(特征鲜明,误报低)
# ⚠️ 裸「改为」「改成」**刻意不在此列**:本 SKILL 自己的表 C 处置枚举就含「改为X」
#    (SKILL.md「处置取值 ∈ {实现/裁剪/延期/改为X}」),任何一张普通表 C 都会命中;
#    「按钮文案改为『保存中』」这类纯文案调整同样命中。实测本 SKILL 自带的 PRD 样本
#    与表 C 示例统统被判成「语义变更类需求缺表 E」→ exit 1。
#    现降级为 CONTEXTUAL_CHANGE_RE:须与语义类名词同行同现才算数;
#    带上下文的「由…改为」「由仅…改为」保留为强信号(它们本就指向口径变化)。
STRONG_SIGNAL_PATTERNS = [
    # ⚠️ 裸「口径」「默认开启/默认关闭」「反转」**已从强信号降级**:
    #    · 「数据口径」常是 PRD 表格的**列名**,不是变更;
    #    · 「新增『邮件通知』开关,默认开启」是**纯新增需求**,零语义变更。
    #    实测本 SKILL 自带 8 份参考样本被这三类裸命中判死 3 份,而这是 Critical 硬门——
    #    使用者最可能的反应是把它当噪声关掉,那正好放过同一维度另一侧的假绿。
    #    现改由 CONTEXTUAL_STRONG_RE 通道处理:须与变更动词同行同现才算数。
    r"全口径",
    r"扩展为",
    r"扩为",
    r"不再只",
    # ⚠️ 只有**带「仅」的**保留为裸强信号——「由仅 X 改为 Y」天然指向口径放宽。
    #    泛化的「由 X 改为/改成 Y」已移入下方 GENERIC_CHANGE_RE:实测自带样本
    #    功能规格说明书样本里「由"变更"改为"核减"」是**纯状态/流程名替换**,被判死。
    r"由仅[^\n。；]{0,30}改为",
    r"含[^\n，。；、]{0,10}消耗",
]
# 泛化的「由 X 改为/改成 Y」:须与语义类名词同行同现才算数
GENERIC_CHANGE_RE = re.compile(r"由[^\n。；]{0,30}改[为成]")
# 降级下来的三类:本身指向语义,但**必须与变更动词同行同现**才判定
CONTEXTUAL_STRONG_RE = re.compile(r"口径|默认开启|默认关闭|反转")
# 弱信号词:天然高频(数据范围/权限范围/存储单位/字段默认值等),仅当与「变更动词」同行同现才计为语义变更,
# 避免误伤含「六、字段规格表」单位三列 / 权限范围 的普通 PRD
# 语义类名词:裸「改为/改成/调整为/变更为」须与其同行同现,才判为语义/口径变更
SEMANTIC_NOUN_RE = re.compile(
    r"口径|统计|语义|含义|计量|取数|维度|权限|状态机|计算方式|统计对象|数据范围|适用范围|默认值|"
    # 下面这批覆盖真实 PRD 的常见口径变更写法:「触发条件由…改为…」「按在职状态过滤后的人数」。
    # 不收裸「状态」:「状态改为『停售』」是纯状态机流转描述、不是口径变更(会假红);
    #    要抓的是状态**语义**变化,故只收下面三个复合词。
    r"定义|条件|规则|过滤|去重|计费|阈值|归属|口径范围|状态语义|状态含义|状态口径")
CONTEXTUAL_CHANGE_RE = re.compile(r"改为|改成|调整为|变更为")

WEAK_SIGNAL_WORDS = ["范围", "单位", "默认值"]
# 「单位」是同音异义高发词(组织单位/本单位/单位名称),须与量纲词同行同现才算数
UNIT_DIMENSION_RE = re.compile(r"分|元|角|秒|毫秒|小时|天|条|次|个|%|百分比|字节|KB|MB|GB|千克|克|米")
CHANGE_VERB_PATTERN = re.compile(
    r"(改为|改成|调整为|变更为|扩展为|扩为|反转|不再只|由[^\n，。；、]{1,12}(改|变|调))"
)

STRONG_SIGNAL_RE = re.compile("|".join(STRONG_SIGNAL_PATTERNS))
WEAK_SIGNAL_RE = re.compile("|".join(WEAK_SIGNAL_WORDS))

# ── ③ 笼统豁免表述(严禁用其覆盖说明性文案)──────────────────────────
BLANKET_EXEMPTION_PATTERNS = [
    r"版式[^\n]{0,10}(全部)?保持不变",
    r"版式[^\n]{0,10}不变",
    r"页面版式[^\n]{0,10}不变",
    r"指标项[^\n]{0,10}(保持)?不变",
    r"指标构成[^\n]{0,10}(保持)?不变",
    r"图表类型[^\n]{0,10}(保持)?不变",
    r"仅[^\n]{0,4}数值变化",
    r"仅数值变化",
    r"UI\s*不变",
    r"界面[^\n]{0,6}不变",
    r"全部保持不变",
]
BLANKET_EXEMPTION_RE = re.compile("|".join(BLANKET_EXEMPTION_PATTERNS))
# 显式声明豁免(写了「版式不变」但同时声明不覆盖口径说明文案 + 文案同步见表 E)→ 合规声明
BLANKET_DECLARATION_RE = re.compile(r"不覆盖[^\n]{0,8}(口径|说明)[^\n]{0,8}文案")

# ── 表 E / 表 F 表头特征 ─────────────────────────────────────────
# 表 E 6 列:变更项 | 变更前语义 | 变更后语义 | 受影响展示物 | 处置 | 新文案
TABLE_E_COLS = ["变更前语义", "变更后语义", "受影响展示物", "新文案"]
# 表 F 5 列:历史版本 | 需求编号 | 原结论 | 本版处置 | 理由
TABLE_F_COLS_PRIMARY = ["历史版本", "需求编号"]
TABLE_F_COLS_SECONDARY = ["本版处置", "原结论"]


def find_md_files(path: Path) -> List[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(path.rglob("*.md"))
    return []


# GFM 里 `\|` 是**单元格内的字面竖线**,不是列分隔符。不认它会整行列错位——
# 表 E 的「受影响展示物」常写成 导出文件表头「A \| B」、处置列有「改为X」,一旦错位,
# `disposition` 会取到展示物、`new_copy` 取到处置,而这份数据要被下游当契约消费。
_ESCAPED_PIPE = "\x00PIPE\x00"


def split_row(line: str) -> List[str]:
    s = line.strip().replace("\\|", _ESCAPED_PIPE)
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip().replace(_ESCAPED_PIPE, "|") for c in s.split("|")]


# ⚠️ GFM 表头必须**紧跟分隔行**（`|---|---|`），且表体至少要有一行数据。
# 不校验这两条时，判据可被**一句散文**满足 —— 实测：
#   「说明:按规范,表 E 需要包含 变更项 | 变更前语义 | … 六列。(本文档并没有真的产出表 E)」
#   → 判「✅ 表 E 已产出,维度 14 通过」exit 0。空表（只有表头+分隔行、零数据行）同样放行。
# 这道教训 architect 的 check_error_contract.py:298 早就写进注释了（「散文里出现 `|`
# 就会被当成一张表」），只是没搬到 ux 这几个表格脚本上来。
def is_separator_row(cells: List[str]) -> bool:
    # ⚠️ 连字符是 `-+` 不是 `-{2,}`：GFM 只要求至少一个，而 `| :- |` 正是本仓库最主流的
    # 写法（实测 plugins/ 下 378 处，多于 `|---|` 的 105 处）。写成 `{2,}` 会把每一张
    # 真表都判成「没有表 E」→ 每份合规 PRD 必判死，是比原假绿更糟的假红。
    return bool(cells) and all(re.fullmatch(r":?-+:?", c or "") for c in cells)


def table_starts_at(lines: List[str], i: int) -> bool:
    """第 i 行是表头 → 紧跟分隔行、且分隔行之后还有至少一行数据行。"""
    if i + 1 >= len(lines) or "|" not in lines[i + 1]:
        return False
    if not is_separator_row(split_row(lines[i + 1])):
        return False
    j = i + 2
    return j < len(lines) and "|" in lines[j] and not is_separator_row(split_row(lines[j]))


# 文案列占位/空值判定:这些取值等同"文案未落地",按空处理(违规)。
# ★与下游 dev-logic-architect `check_copy_landing_table.py` 的 EMPTY_MARKERS 同源同口径——
#   那边治「文案落点表」,这边治「表 E」,两张表是同一条语义变更链路的上下游,判据必须一致。
# ⚠️ 额外拒绝「同上」:跨行复制的典型偷懒形态,表 E 一旦逐行「同上」等于什么都没写。
TABLE_E_EMPTY_MARKERS = {
    "", "-", "—", "–", "─", "无", "n/a", "na", "/", "\\", "待定", "tbd", "todo",
    "?", "??", "待补", "待确认", "暂无", "待产品确认", "...", "…", "xxx",
    "同上", "见上", "同前", "略", "按实际", "按实际调整", "视情况",
}
TABLE_E_PLACEHOLDER_RE = re.compile(r"^\{[^{}]*\}$|^<[^<>]+>$")


# ⚠️ **一处登记在案的已知假红**:本 SKILL 自家的 `references/quality-review-checklist.md`
#    在加了围栏护栏后 exit 1 —— 它在**正文**里描述判据(必然出现「口径/默认值/改为」),
#    而它的表 E 只以**围栏内示例**形态存在,于是命中「有信号却缺表 E」。
#    **刻意不为它加护栏**:本脚本的输入契约是 **PRD 路径或目录**(见 SKILL.md 命令 10),
#    不是判据文档;为「拿判据文档当 fixture」这种非真实场景加豁免,只会扩大漏检真 PRD 的面。
#    净收益已实测:全仓 185 份 .md,围栏护栏**修掉 2 处旧假红**(dmtc 的两份 flow-*.md)、新增这 1 处。
FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")


def fence_mask(lines: List[str]) -> List[bool]:
    """标出每一行是否落在 markdown 代码围栏内(含围栏行本身)。

    ⚠️ **为什么必须有它**:表 E/F 的**模板示例**几乎必然写在 ```markdown 围栏里
       (本 SKILL 自家 `references/flow-upstream-refs.md` 与 `quality-review-checklist.md` 就是),
       不排除围栏,示例表会被当成真表——① 判定侧:满足「有表 E」而放行(**旧版就有这个假绿**);
       ② 抽取侧(--emit-json):示例文案被写进机器可读副本,而表 E 是 architect 文案落点表 /
       dmtc [文案一致性] 用例 / cvl 文案核验三个下游的跨产物契约,污染它比没有更糟。
       同款护栏在 architect 的 check_error_contract.py 已有先例(GFM 表头护栏),此处补齐。
    """
    mask, inside, marker = [], False, ""
    for line in lines:
        m = FENCE_RE.match(line)
        if m and not inside:
            inside, marker = True, m.group(1)[0]
            mask.append(True)
            continue
        if m and inside and m.group(1)[0] == marker:
            inside = False
            mask.append(True)
            continue
        mask.append(inside)
    return mask


def _norm_cell(s: str) -> str:
    return re.sub(r"[*`>\s]", "", s)


def _scan_table_e_rows(lines: List[str], header_idx: int, header: List[str]) -> List[Dict]:
    """校验表 E 的**内容**,不只表头存在性。

    ⚠️ 早期只判表头是否出现 → 一张逐行「同上 / — / 待定 / 按实际调整」的空壳表全绿放行,
       而 `references/quality-review-checklist.md` 明写「`改写` 必须给出**具体新文案**,
       **不接受**『待定 / 按实际调整』」。判据在文档里,机检里没有 = 假绿。
    """
    idx_map = {}
    for k, cell in enumerate(header):
        n = _norm_cell(cell)
        for col in TABLE_E_COLS:
            if col in n:
                idx_map[col] = k
    bad: List[Dict] = []
    j = header_idx + 2
    while j < len(lines) and "|" in lines[j]:
        cells = split_row(lines[j])
        if is_separator_row(cells):
            j += 1
            continue
        empties = []
        for col, k in idx_map.items():
            v = _norm_cell(cells[k]) if k < len(cells) else ""
            if v.lower() in TABLE_E_EMPTY_MARKERS or TABLE_E_PLACEHOLDER_RE.match(v):
                empties.append(col)
        if empties:
            bad.append({"line": j + 1, "cols": empties,
                        "text": lines[j].strip()[:100]})
        j += 1
    return bad


def is_table_e_header(cells: List[str]) -> bool:
    joined = " ".join(cells)
    return all(col in joined for col in TABLE_E_COLS)


def is_table_f_header(cells: List[str]) -> bool:
    joined = " ".join(cells)
    if not all(col in joined for col in TABLE_F_COLS_PRIMARY):
        return False
    return any(col in joined for col in TABLE_F_COLS_SECONDARY)


# ── 表 E / 表 F 的机器可读副本(--emit-json) ────────────────────────────────
# **为什么由脚本抽取,而不是让 PRD 同时手写一份 JSON:**
# 下游希望表 E/F 有结构化副本(它们要消费表 F 做跨版本清算,而实测同一仓库 18 个版本
# 出现过 REQ-001 / REQ-3 / REQ-V0.10-A02 / 纯数字 四种编号写法,正则很脆)。
# 但「markdown 一份 + JSON 一份」= **同一数据两份手写**,是本仓库最高频的漂移源
# (与「同一判据两份实现」同类)。所以这里改成:**markdown 表仍是唯一信源,JSON 由本脚本
# 确定性抽取生成**——人只写一处,机器派生一处,天然不可能对不上。
REQ_ID_RE = re.compile(
    r"(?P<prefix>[A-Za-z]+[-_]?)?"          # REQ- / FR_ / 无前缀
    r"(?:(?P<version>[Vv]\d+(?:\.\d+)*)[-_]?)?"  # V0.10 段(可选)
    r"(?P<seq>[A-Za-z]?\d+)$"               # A02 / 001 / 3
)


def normalize_req_id(raw: str) -> Dict:
    """把四种编号写法拆成结构,**原文一并保留**。

    ⚠️ 认不出来时 `parsed: false` + 原文照传,**绝不猜** —— 猜错编号会让跨版本清算
       张冠李戴,比认不出更糟。
    """
    txt = _norm_cell(raw)
    m = REQ_ID_RE.match(txt)
    if not m:
        return {"raw": raw.strip(), "parsed": False}
    seq = m.group("seq")
    digits = re.sub(r"\D", "", seq)
    return {
        "raw": raw.strip(),
        "parsed": True,
        "prefix": (m.group("prefix") or "").rstrip("-_") or None,
        "version": m.group("version"),
        "seq": seq,
        "number": int(digits) if digits else None,
    }


def _extract_rows(lines: List[str], header_idx: int, header: List[str],
                  colmap: Dict[str, str]) -> List[Dict]:
    """按 colmap(表列关键字 → 输出字段名)抽取表格数据行。

    列匹配用「关键字包含」而非全等——表头常写成 `**变更前语义**` 或带说明后缀。
    """
    idx_map = {}
    for k, cell in enumerate(header):
        n = _norm_cell(cell)
        for key, field in colmap.items():
            if key in n and field not in idx_map:
                idx_map[field] = k
    rows: List[Dict] = []
    j = header_idx + 2
    while j < len(lines) and "|" in lines[j]:
        cells = split_row(lines[j])
        # 空行既不是分隔行也不是数据行(Word 转出的 |||| 占位行实测存在)
        if is_separator_row(cells) or all(c.strip() == "" for c in cells):
            j += 1
            continue
        row = {"_line": j + 1}
        for field, k in idx_map.items():
            row[field] = cells[k].strip() if k < len(cells) else ""
        rows.append(row)
        j += 1
    return rows


TABLE_E_COLMAP = {
    "变更项": "change_item", "变更前语义": "semantics_before",
    "变更后语义": "semantics_after", "受影响展示物": "affected_display",
    "处置": "disposition", "新文案": "new_copy",
}
TABLE_F_COLMAP = {
    "历史版本": "history_version", "需求编号": "req_id",
    "原结论": "original_conclusion", "本版处置": "disposition", "理由": "reason",
}


def _co_occurs(line: str, m, other_re, window: int = 40) -> bool:
    """判断 other_re 是否出现在 m 命中点的 ±window 字符窗口内。

    ⚠️ 不能用「同行共现」:本 SKILL 的 PRD 样本里,**一整张表格行就是一行**(动辄数百字),
    同行共现等于全表共现、几乎恒真。实测规格说明书样本的「单位」(组织单位)与量纲词
    「个/次」就是这样在同一超长行里凑到一起的。
    """
    s = max(0, m.start() - window)
    return bool(other_re.search(line[s:m.end() + window]))


def find_signal_lines(lines: List[str], in_fence: Optional[List[bool]] = None) -> Dict:
    strong: List[Dict] = []
    weak: List[Dict] = []
    blanket: List[Dict] = []
    for idx, line in enumerate(lines):
        # ⚠️ 代码围栏内整体跳过:围栏里的一切都是**示例**(模板、正反例、判据引文),
        #    信号侧不跳会与表侧的围栏护栏打架——判据类文档正文提一句「口径」就命中信号,
        #    而它的表 E 只存在于围栏示例里,于是被判成「命中语义变更却缺表 E」= 假红。
        #    实测:只给表侧加护栏时,本 SKILL 自家 quality-review-checklist.md 立刻 0→1。
        if in_fence is not None and in_fence[idx]:
            continue
        # 跳过代码/表格分隔无意义行不必要;信号词在正文与表格皆可命中
        m = STRONG_SIGNAL_RE.search(line)
        if not m:
            # 裸「改为/改成/调整为/变更为」+ 同行语义类名词 = 等效强信号
            cm = CONTEXTUAL_CHANGE_RE.search(line)
            if cm and _co_occurs(line, cm, SEMANTIC_NOUN_RE):
                m = cm
        if not m:
            # 降级下来的三类(口径 / 默认开启 / 默认关闭 / 反转):须与变更动词同行同现
            sm = CONTEXTUAL_STRONG_RE.search(line)
            if sm and (CONTEXTUAL_CHANGE_RE.search(line) or CHANGE_VERB_PATTERN.search(line)):
                m = sm
        if not m:
            # 泛化「由 X 改为 Y」:须与语义类名词同行同现
            gm = GENERIC_CHANGE_RE.search(line)
            if gm and _co_occurs(line, gm, SEMANTIC_NOUN_RE):
                m = gm
        if m:
            strong.append({"line": idx + 1, "hit": m.group(0), "text": line.strip()[:120]})
        if WEAK_SIGNAL_RE.search(line) and CHANGE_VERB_PATTERN.search(line):
            wm = WEAK_SIGNAL_RE.search(line)
            # 「单位」须同行有量纲词,否则是「组织单位」类同音异义,不计
            if not (wm.group(0) == "单位" and not _co_occurs(line, wm, UNIT_DIMENSION_RE)):
                weak.append({"line": idx + 1, "hit": wm.group(0), "text": line.strip()[:120]})
        bm = BLANKET_EXEMPTION_RE.search(line)
        if bm:
            has_decl = bool(BLANKET_DECLARATION_RE.search(line))
            blanket.append({
                "line": idx + 1,
                "hit": bm.group(0),
                "declared_safe": has_decl,
                "text": line.strip()[:120],
            })
    return {"strong": strong, "weak": weak, "blanket": blanket}


def scan_file(path: Path, root: Path) -> Dict:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"file": str(path), "read_error": str(exc)}
    try:
        rel = str(path.relative_to(root))
    except ValueError:
        rel = str(path)

    lines = text.splitlines()
    in_fence = fence_mask(lines)
    sig = find_signal_lines(lines, in_fence)

    has_table_e = False
    has_table_f = False
    table_e_lines: List[int] = []
    table_e_placeholder_rows: List[Dict] = []
    table_f_lines: List[int] = []
    table_e_rows: List[Dict] = []
    table_f_rows: List[Dict] = []
    for idx, line in enumerate(lines):
        if "|" not in line or in_fence[idx]:
            continue
        cells = split_row(line)
        if is_table_e_header(cells) and table_starts_at(lines, idx):
            has_table_e = True
            table_e_lines.append(idx + 1)
            table_e_placeholder_rows.extend(_scan_table_e_rows(lines, idx, cells))
            table_e_rows.extend(_extract_rows(lines, idx, cells, TABLE_E_COLMAP))
        if is_table_f_header(cells) and table_starts_at(lines, idx):
            has_table_f = True
            table_f_lines.append(idx + 1)
            table_f_rows.extend(_extract_rows(lines, idx, cells, TABLE_F_COLMAP))

    # ⚠️ **只有强/上下文信号才让本硬门判不通过;弱信号(范围/单位/默认值 + 变更动词)只报不判。**
    #    弱信号词天然高频且同音异义多:实测自带样本里「影响**范围**:资源申请…」(变更日志散文)、
    #    「质量评估**单位**」(组织单位,却因同行有「三个步骤」的『个』满足了量纲护栏)双双命中,
    #    把一份纯功能规格说明书判成「语义变更类需求缺表 E」。Critical 硬门一旦持续假红就会被整体忽略,
    #    故弱信号降为提示;真正的口径变更几乎必然同时产生强/上下文信号(实测 5 份变更 fixture 全命中)。
    has_semantic_signal = bool(sig["strong"])
    has_weak_only = (not sig["strong"]) and bool(sig["weak"])
    # 笼统豁免:命中且未在同行做合规声明的才算"裸豁免"
    bare_blanket = [b for b in sig["blanket"] if not b["declared_safe"]]
    has_bare_blanket = bool(bare_blanket)

    return {
        "file": rel,
        "strong_signals": sig["strong"],
        "weak_signals": sig["weak"],
        "blanket_hits": sig["blanket"],
        "bare_blanket_hits": bare_blanket,
        "has_semantic_signal": has_semantic_signal,
        "has_weak_only": has_weak_only,
        "has_bare_blanket": has_bare_blanket,
        "has_table_e": has_table_e,
        "table_e_placeholder_rows": table_e_placeholder_rows,
        "has_table_f": has_table_f,
        "table_e_lines": table_e_lines,
        "table_f_lines": table_f_lines,
        "table_e_rows": table_e_rows,
        "table_f_rows": table_f_rows,
    }


def evaluate(results: List[Dict]) -> bool:
    """返回 failed 布尔。任一文件命中语义变更或裸笼统豁免而缺表 E,即整体不通过。

    注:表 E/F 可能与信号词分布在多文件(多文件拆分模式)。凡任一 .md 出现表 E 即视为已产出表 E。
    """
    any_table_e = any(r.get("has_table_e") for r in results if not r.get("read_error"))
    any_semantic = any(r.get("has_semantic_signal") for r in results if not r.get("read_error"))
    any_bare_blanket = any(r.get("has_bare_blanket") for r in results if not r.get("read_error"))
    any_placeholder = any(r.get("table_e_placeholder_rows") for r in results
                          if not r.get("read_error"))
    # 表 E 存在但整行/关键列是占位 = 等同没写,同样判不通过(治的是「表头一挂就绿」的假绿)
    failed = ((any_semantic or any_bare_blanket) and not any_table_e) or any_placeholder
    return failed


def render_text(results: List[Dict], failed: bool) -> str:
    out: List[str] = []
    out.append("=== 语义/口径变更类需求 硬核回检(维度 14·命令 10) ===\n")

    valid = [r for r in results if not r.get("read_error")]
    any_semantic = any(r.get("has_semantic_signal") for r in valid)
    any_bare_blanket = any(r.get("has_bare_blanket") for r in valid)
    any_table_e = any(r.get("has_table_e") for r in valid)
    any_table_f = any(r.get("has_table_f") for r in valid)

    any_weak_only = any(r.get("has_weak_only") for r in valid)
    if not any_semantic and not any_bare_blanket and any_weak_only:
        out.append("ℹ️ 仅命中**弱信号词**(范围/单位/默认值 + 变更动词),未命中强/上下文信号。")
        out.append("   → **只提示、不判错**(弱信号词天然高频且同音异义多,详见脚本内注释);"
                   "若本次确为语义/口径变更,请人工确认并补表 E。")
        for r in valid:
            for w in r.get("weak_hits", [])[:5]:
                out.append(f"      - {r['file']}:L{w['line']} 「{w['hit']}」: {w['text'][:80]}")
        return "\n".join(out)
    if not any_semantic and not any_bare_blanket:
        out.append("ℹ️ 未命中任何语义变更信号词,也无笼统豁免表述。")
        out.append("   → 非语义/口径变更类需求(或纯新增/纯逆向):退出码 0 grandfather 放行,不判错。")
        return "\n".join(out)

    for r in valid:
        if not (r["has_semantic_signal"] or r["blanket_hits"] or r.get("has_weak_only")):
            continue
        out.append(f"📄 {r['file']}")
        if r["strong_signals"]:
            out.append(f"   🔸 强信号词命中 {len(r['strong_signals'])} 处:")
            for s in r["strong_signals"][:12]:
                out.append(f"      - L{s['line']} 「{s['hit']}」: {s['text']}")
            if len(r["strong_signals"]) > 12:
                out.append(f"      ... 另有 {len(r['strong_signals']) - 12} 处")
        if r["weak_signals"]:
            out.append(f"   🔸 弱信号词(与变更动词同行)命中 {len(r['weak_signals'])} 处:")
            for s in r["weak_signals"][:8]:
                out.append(f"      - L{s['line']} 「{s['hit']}」: {s['text']}")
        if r["bare_blanket_hits"]:
            out.append(f"   🔻 裸笼统豁免表述命中 {len(r['bare_blanket_hits'])} 处(未声明「不覆盖口径说明文案」):")
            for b in r["bare_blanket_hits"][:8]:
                out.append(f"      - L{b['line']} 「{b['hit']}」: {b['text']}")
        blanket_declared = [b for b in r["blanket_hits"] if b["declared_safe"]]
        if blanket_declared:
            out.append(f"   ✅ 另有 {len(blanket_declared)} 处「版式不变」已同行声明「不覆盖口径说明文案」,合规")
        if r["has_table_e"]:
            out.append(f"   ✅ 表 E(6 列)命中,表头行 {r['table_e_lines']}")
        if r["has_table_f"]:
            out.append(f"   ✅ 表 F(历史需求作废清单)命中,表头行 {r['table_f_lines']}")
        out.append("")

    # ── 判定 ──
    if failed:
        out.append("❌ 判定:命中语义/口径变更类需求(或笼统豁免表述)但**缺「表 E:语义变更 → 派生展示物影响清单」**。")
        out.append("   → 语义变更类需求必须逐行产出表 E(6 列:变更项 | 变更前语义 | 变更后语义 | 受影响展示物 | 处置 | 新文案),")
        out.append("     枚举全部受影响说明性展示物(tooltip/副标题/图例/空态/导出表头/报表标题/帮助文档/单位标注/筛选项标签/告警),")
        out.append("     处置 ∈ {改写/保持/新增/待产品确认},「改写」须给具体新文案、「保持」须写明理由。")
        out.append("   → 严禁用「页面版式全部保持不变/仅数值变化/UI 不变」等笼统表述覆盖说明性文案;")
        out.append("     确要写「版式不变」须同行声明「本条约束版式与指标构成,不覆盖口径说明文案;文案同步见表 E」。维度 14 不通过(退出码 1)。")
    else:
        out.append("✅ 判定:表 E 已产出,语义变更类需求的派生展示物影响清单完整,维度 14 通过(退出码 0)。")

    # ── 表 F report-only 提示(仅命中语义变更时)──
    if any_semantic and not any_table_f:
        out.append("")
        out.append("🟡[report-only] 命中语义/口径变更类需求,但未发现「表 F:历史需求作废清单」表头。")
        out.append("   → 请把本版变更的关键语义词检索历史版本 docs/requirements/{历史版本}/研发需求/*.md,")
        out.append("     命中的历史需求条目逐条产出表 F(历史版本 | 需求编号 | 原结论 | 本版处置 | 理由;「本版处置」取值 ∈ 沿用/作废/修订),")
        out.append("     防「历史需求被本版推翻却无人回头作废」。跨版本历史扫描超出本脚本能力,由 QR Agent 语义核验硬门。")
    elif any_semantic and any_table_f:
        out.append("")
        out.append("🟢[report-only] 已发现表 F(历史需求作废清单);请 QR Agent 复核历史命中条目是否逐条判定(沿用/作废/修订)。")

    return "\n".join(out)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("path", type=Path, help="PRD 文件或目录")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    parser.add_argument(
        "--emit-json", metavar="PATH", type=str, default=None,
        help="把表 E/表 F 抽取成机器可读副本写到 PATH(传 - 输出到 stdout)。"
             "markdown 表仍是唯一信源,本副本是**派生产物**——人只写一处,机器派生一处,不会漂移。"
             "需求编号同时给 raw 原文与解析结构(四种历史写法免正则)。")
    args = parser.parse_args(argv)

    if not args.path.exists():
        print(f"错误: 路径不存在 {args.path}", file=sys.stderr)
        return 2

    root = args.path if args.path.is_dir() else args.path.parent
    md_files = find_md_files(args.path)
    if not md_files:
        print("⚠️ 未发现任何 .md 文件", file=sys.stderr)
        return 2

    results = [scan_file(f, root) for f in md_files]

    # ⚠️ 读不出来 ≠ 没有违规:全部文件都读失败时判**环境错(2)**,绝不静默计为通过。
    #    (同 skill 的 check_technical_content.py 已做对,此处对齐;全仓退出码约定同款。)
    _read_errs = [r for r in results if isinstance(r, dict) and r.get("read_error")]
    if _read_errs and len(_read_errs) == len(results):
        for _r in _read_errs:
            print(f"错误: 无法读取 {_r['file']}: {_r['read_error']}", file=sys.stderr)
        return 2
    failed = evaluate(results)
    exit_code = 1 if failed else 0

    if args.emit_json is not None:
        # ⚠️ `--emit-json ""`(常见于 `--emit-json "$OUT"` 而 OUT 未设置)此前静默无操作 + exit 0,
        #    调用方会以为副本已生成 —— 假绿。空串按入参错处理。
        if not args.emit_json.strip():
            print("错误: --emit-json 的取值为空(是否 shell 变量未设置?)", file=sys.stderr)
            return 2
        valid = [r for r in results if not r.get("read_error")]
        payload = {
            "schema": "ux-logic-extractor/semantic-change@1",
            "source_docs": [r["file"] for r in valid],
            "table_e": [
                {**{k: v for k, v in row.items() if k != "_line"},
                 "source": {"file": r["file"], "line": row["_line"]}}
                for r in valid for row in r.get("table_e_rows", [])
            ],
            "table_f": [
                {**{k: v for k, v in row.items() if k not in ("_line", "req_id")},
                 "req_id": normalize_req_id(row.get("req_id", "")),
                 "source": {"file": r["file"], "line": row["_line"]}}
                for r in valid for row in r.get("table_f_rows", [])
            ],
            # ⚠️ 副本可能派生自**没过门**的 PRD(表 E 有「待定/同上」等占位时脚本判 exit 1,
            #    但副本照写)。只读 JSON 的下游必须能看出这一点,否则会把占位当真文案落地。
            "gate": {
                "failed": failed,
                "exit_code": exit_code,
                "placeholder_rows": [
                    {"file": r["file"], "line": b["line"], "cols": b["cols"]}
                    for r in valid for b in r.get("table_e_placeholder_rows", [])
                ],
            },
        }
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        if args.emit_json == "-":
            print(text)
        else:
            try:
                Path(args.emit_json).write_text(text + "\n", encoding="utf-8")
            except OSError as exc:
                # 写不出来是**环境错**,不是产物违规——绝不用 1 顶替(会被读成「PRD 有问题」)
                print(f"错误: 无法写出 {args.emit_json}: {exc}", file=sys.stderr)
                return 2

    # `--emit-json -` 时 stdout 归副本独占,人读报告/`--json` 让位到 stderr——
    # 否则两段内容首尾相接,调用方 json.load 直接 "Extra data" 报错(实测踩到)。
    rpt = sys.stderr if args.emit_json == "-" else sys.stdout

    if args.json:
        valid = [r for r in results if not r.get("read_error")]
        print(json.dumps({
            "command": "check_semantic_change",
            "has_semantic_signal": any(r.get("has_semantic_signal") for r in valid),
            "has_bare_blanket": any(r.get("has_bare_blanket") for r in valid),
            "has_table_e": any(r.get("has_table_e") for r in valid),
            "has_table_f": any(r.get("has_table_f") for r in valid),
            "failed": failed,
            "exit_code": exit_code,
            # 内部字段 _line 只服务 --emit-json 的行号溯源,不进公开 --json schema
            "files": [
                {k: ([{kk: vv for kk, vv in row.items() if kk != "_line"} for row in v]
                     if k in ("table_e_rows", "table_f_rows") else v)
                 for k, v in r.items()}
                for r in results
            ],
        }, ensure_ascii=False, indent=2), file=rpt)
    else:
        print(render_text(results, failed), file=rpt)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
