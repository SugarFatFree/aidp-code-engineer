#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查项 40 / 核心原则 33:权限与可见范围约束落地(Critical)。

**判据只判「有无」,不判「对不对」。** 「这个权限设计得合不合理」要连业务才知道,那是人的活;
但「需求写了某条可见范围约束、设计里一个字没提」是确定性可判的。

立论(下游实测):需求文档里「该列表仅本部门可见」「只有管理员能导出」「按角色过滤数据范围」
这类约束,是**加在既有字段/页面上的限定,不新增任何实体**。而规划期既有的四道基准全是
「元素/字段存不存在」——PRD 条目级 / 需求字段级 / 原型元素级 / 语义变更派生——**一条都命不中它**:
  · 检查项 3「UI 交互的技术实现方案」是**原型驱动**的(判据形态是「编辑按钮置灰,置灰条件是什么」),
    而本类约束在原型上**看不出来**(加了部门过滤的列表和没加的长得一模一样);
  · 检查项 29「字段实现清单」查的是**字段有没有落地**,约束不是字段;
  · 检查项 31 的 fail-closed 管的是**取不到值时怎么办**,不管**约束本身有没有落地**。
结果是:需求写了、详细设计整条不落地,而规划期审计照样报 ✅ 通过。
权限缺失是**安全面**缺陷——漏了不会白屏、不会报错,只会让不该看见的人看见。

强制产出 4 列「权限与可见范围约束落点表」:
    | 约束原文(引 PRD 位置) | 约束类型 | 约束主体来源 | 落点(可指认) |

⚠️ **第 3 列「约束主体来源」是本表最容易被忽略、却最致命的一列。**
   「本部门」的部门 ID 从哪来:登录态 / token / 会话,还是**请求参数**?若来自请求参数,
   等于「客户端自称是哪个部门就是哪个部门」,过滤代码写得再对也等于没有。
   这一条**不需要懂业务**即可判定,故做成 G5(Critical)。

⚠️ **第 5 列「取不到主体时的行为」刻意不设**——那是**检查项 31 的 fail-closed**,
   同一条纪律只登记一处,⛔ 不在本表再要一遍(同判据两份实现是本仓库最高频漂移源)。

判据:
  G1 表存在但 4 列不齐                                   Critical
  G2 逐格空或占位                                         Critical
  G3 数据行格数不符(点名 `|` 未转义)                      Critical
  G4 「约束类型」不在四档枚举内                            Critical
  G5 「约束主体来源」来自请求参数/前端传入(客户端自称身份)  Critical
  G6 「落点」不可指认(见上/按业务/框架自动处理/同上)        Critical
  P0 (仅 --requirements 传入时)上游有约束句、设计无落点     Critical
  W1 有权限约束信号却整个缺表                              Important(不占退出码)
  W2 (仅 --requirements 传入时)登记了上游找不到的约束        Important

⚠️ **W1 缺表刻意判 Important 不判 Critical**:存量设计会大面积命中,一上来判死会让整个硬门
   被无视(本仓库既有教训:假红常驻 = 硬门被绕过,同 U1/E1/Z1 三处先例)。
   **但检查项 40 的维度结论仍按不通过判**——严重度分档是给退出码用的、不是给维度结论用的。
   与之配套:**一张表都没有时只报 W1、不报 G1~G6**,否则该取舍会被自己当场抵消
   (dmtc 的 Z1/Z6、architect 的 E1/E7 都踩过这个洞)。

⚠️ **`--requirements` 是可选参数,不是必填。**
   全仓 31 个姊妹脚本一律单入参(设计文档路径),QR 步骤 0 的 bash 块也传不了 PRD 路径
   (子 Agent 未必知道 PRD 在哪)。若做成必填,漏传会被 argparse 判用法错 → exit 2,
   而 exit 2 按全仓约定是「入参/环境错、不计维度失败」→ 这一档**既不算过也不算不过,
   实际是静默没跑**(维度 13 的 `--version` 就是这么栽的)。
   故:没传时只做设计侧判据,并在 `--json` 出 `requirements_scanned: false`
   **显式标明「PRD→设计 这一半没查」**,⛔ 不得读成通过。

退出码:0 = 无 Critical(含 N/A 跳过);1 = 检出 Critical;2 = 入参或环境错。
严重度分档走 --json,不占用退出码。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REQUIRED_COLUMNS = ["约束原文", "约束类型", "约束主体来源", "落点"]

# 约束类型四档枚举。⚠️ 四档按「落点该在哪一层」划分,不是按业务分类:
#   数据行过滤→服务层/SQL where;字段脱敏→出参组装;操作准入→接口层鉴权;页面可见性→前端+后端双侧。
CONSTRAINT_KINDS = ["数据行过滤", "字段脱敏", "操作准入", "页面可见性"]

EMPTY_MARKERS = {"", "-", "—", "--", "n/a", "na", "无", "待定", "tbd", "同上", "略"}
# ⚠️ 占位正则必须**全串锚定**:否则「仅 {部门ID} 可见」这种已填实、只留槽位的合规写法
#    会被整格判空(check_error_contract.py / check_metric_spec.py 都踩过同一个坑)。
PLACEHOLDER_RE = re.compile(r"^\{[^{}]*\}$|^<[^<>]+>$|^\[[^\[\]]*\]$")

# 「落点」不可指认的表述。⚠️ 全串锚定,⛔ 不可改 search——
#    「服务层 OrderService#listByDept 按业务线再收窄一次」是合格填写,子串匹配会假红。
VAGUE_LANDING_RE = re.compile(
    r"^(?:见上|如上|同上|参见上文|按业务|视情况(?:而定)?|由?权限框架(?:自动)?(?:处理|控制)?"
    r"|框架自动(?:处理|控制)?|后续补充|待补充|统一处理|走通用逻辑)[。.\s]*$")

# G5:主体来源来自客户端。⚠️ 这一列的格子极短(就填「登录态」「token」「请求参数」这类),
#    故用 search 而非全串锚定——「由前端在查询参数里传 deptId」必须抓到。
CLIENT_SUPPLIED_RE = re.compile(
    r"请求参数|入参传(?:入|递)?|前端传|由前端|客户端传|调用方传|URL\s*参数|query\s*参数|表单传")
# 反向豁免:明写了「前端传但服务端以登录态为准 / 服务端校验归属」的,不算违规。
CLIENT_SUPPLIED_OK_RE = re.compile(
    r"以登录态为准|服务端(?:再)?(?:校验|覆盖|以.*为准)|后端(?:再)?(?:校验|覆盖)|仅用于展示|不作为鉴权依据")

# 权限/可见范围信号(用于 W1 缺表判定)。
# ⚠️ **刻意不认裸「权限」「角色」「只读」**:全仓 SKILL 文档**标题行**命中「权限」29 处、
#    「角色」19 处,绝大多数是「权限校验模块」「角色定义」这类非约束语境,
#    用它们做信号会让合规文档满屏假红(与 check_metric_spec.py 的 M1 同一条教训)。
#    ⚠️ **口径**(⛔ 别只写数字不写怎么数的):
#      grep -rn '^#\{1,6\} .*<词>' plugins/*/skills/*/ --include='*.md' | wc -l   # 不排代码围栏
#    该数字是 **的实测值,**会随仓库演进而变**
#    —— 本次改动落地后同口径即变成 35/20。引用时请用上面的命令**现算**,⛔ 别照抄。
#    结论(裸词做信号会满屏假红)不依赖具体数值,只依赖「量级是几十处而非几处」。
#    只认**带限定语义的句式与组合词**。
PERM_SIGNAL_RE = re.compile(
    # ⚠️ `无权(?!限)` 的否定前瞻不可省:裸 `无权` 会命中「无权限」,而实测
    #    「本版**无权限**约束」「该模块**无权限**校验需求」这类**否定句/名词化用法**
    #    正是「没有约束」的意思 —— 当成信号会让 P0 对着一句「本版没有权限约束」判 Critical。
    #    收窄后仍认「用户**无权**访问」这类「无权+动词」的真约束。
    #    代价:漏掉「无权限访问」的写法(方向是 W1/P0 少报一次),可接受 ——
    #    其余信号词(仅…可见/只有…才能/本部门/数据范围/可见范围)已覆盖绝大多数约束表述,
    #    且「无权时返回 403」本就属**检查项 31 错误契约**的地盘,不是「约束有没有落地」。
    r"仅[^。;；\n]{0,12}可见|只有[^。;；\n]{0,12}(?:才)?能|无权(?!限)|越权|不可见"
    r"|本部门|本企业|本机构|本人只能|仅本人"
    r"|数据范围|可见范围|数据隔离|数据权限|行级权限|字段级权限"
    r"|按角色(?:过滤|区分|控制)|按部门(?:过滤|隔离)|权限过滤")
# ⚠️ 标题级否定护栏(实测必需,勿删):规范/清单/对比类章节必然要点名这些词才能把规则讲清楚。
PERM_SIGNAL_NEG_RE = re.compile(
    r"不适用|未采用|备选|方案对比|识别清单|反模式|示例|样例|模板|规范|流程|判据|硬门"
    r"|检查项|维度|变更|评审|风险|问题|确认|术语|索引|目录")
EXEMPT_HEADING_RE = re.compile(r"不适用|未采用|备选方案|方案对比|识别清单|反模式")


def find_md_files(path: Path) -> List[Path]:
    if path.is_file():
        # ⚠️ 单文件也必须是 .md:否则手滑把 `01_详细设计.md` 打成 `.txt` 时
        #    files=[那个txt] → 扫不到表 → rc=0「通过」,而**只含 .txt 的目录**却是 rc=2。
        #    同一类输入错,一个静默放行一个报错 —— 静默放行的那侧正是假绿。
        return [path] if path.suffix.lower() == ".md" else []
    if path.is_dir():
        return sorted(path.rglob("*.md"))
    return []


def split_row(line: str) -> List[str]:
    """按**未转义**的 `|` 切列。
    ⚠️ 与同 SKILL 的 `check_metric_spec.py` 的裸 `split("|")` **刻意不同**,⛔ 别顺手统一:
       本表第 1 列要抄 PRD 约束原文,原文含 `|` 时作者必须按 GFM 规矩写成 `\\|`,
       裸 split 会把**已正确转义**的合规行多切一格、当场判 G3。
       反过来,那边的表不抄原文、统一过去反而会漏掉真正的未转义。"""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in re.split(r"(?<!\\)\|", s)]


def is_separator_row(cells: List[str]) -> bool:
    # ⚠️ 空行必须先判掉:split_row("") 得到 [""],过滤空格后 all() 对空序列返回 True,
    #    于是空行被当成分隔行 →「表头 + 空行」被识别成 0 行的表 → 一条凭空的缺列 Critical。
    if not cells or all(c.strip() == "" for c in cells):
        return False
    return all(re.fullmatch(r":?-{1,}:?", c.replace(" ", "")) for c in cells if c != "")


def _norm(s: str) -> str:
    s = re.sub(r"[*`>\s]", "", s)
    return s.replace("（", "(").replace("）", ")").replace("：", ":")


def cell_matches_column(cell: str, concept: str) -> bool:
    c = _norm(cell)
    if concept == "约束原文":
        return "约束原文" in c or ("原文" in c and "约束" in c) or "需求原文" in c
    if concept == "约束类型":
        return "约束类型" in c or ("类型" in c and "约束" in c) or "限定类型" in c
    if concept == "约束主体来源":
        # ⚠️ 末支必须排掉「原文」:「约束**原文**(引 PRD 位置)」含"约束",
        #    若写成裸 `"约束" in c`,两列互认、col_index 会把主体来源解析到第 1 列,
        #    G5 整条静默失效(变异 fixture 零命中 = 假绿)而表头看着完全正常。
        #    这正是 check_list_page_scale.py 踩过的「两个列名字面互相包含」那个坑。
        return ("主体" in c and "来源" in c) or "主体来源" in c or (
            "来源" in c and "原文" not in c and "落点" not in c)
    if concept == "落点":
        return "落点" in c or "实现位置" in c or ("落地" in c and "位置" in c)
    return False


def col_index(cells: List[str], concept: str) -> Optional[int]:
    for i, c in enumerate(cells):
        if cell_matches_column(c, concept):
            return i
    return None


def is_perm_table_header(cells: List[str]) -> bool:
    """⚠️ 判据是「专名列任一 + ≥3 契约列」,⛔ 别改回「某一列必须在」:
       姊妹脚本 check_residual_assertions.py 的 C2 实测过那个洞——恰恰把作为
       无条件前提的那一列删掉的表**整张认不出来**,于是缺列最严重的反而最轻(严重度完全反了)。"""
    if len(cells) < 3:
        return False
    hit = [c for c in REQUIRED_COLUMNS if col_index(cells, c) is not None]
    named = ("约束主体来源" in hit) or ("约束原文" in hit) or ("落点" in hit)
    # ⚠️ 单元格长度上限(预防性护栏,**已实测确认不是死代码**):
    #    触发形态是「一行长散文表格行 + 紧跟 GFM 分隔行」——实测拆掉本闸门后该形态假红 1 条
    #    Critical、留着则 0。
    #    ⚠️ **订正一条曾照搬姊妹脚本、但在本脚本上不成立的说法**:
    #    `AGENTS.md` 的 SKILL 清单表单格虽是几千字散文、且四个列名**全都出现在里面**,
    #    但它是**数据行**、后面不跟分隔行,真正挡住它的是 scan_perm_tables 里
    #    「表头必须紧跟分隔行」那道闸门,**不是本闸门**(实测:拆掉本闸门,CLAUDE.md 仍 0 命中)。
    #    照搬未实测的教训写注释,本身就是核心原则 30 要消灭的那种「断言没有证据来源」。
    if any(len(c) > 80 for c in cells):
        return False
    return named and len(hit) >= 3


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
    """章节级豁免:命中豁免词的标题起,到**同级或更高级**标题止,整段标 True。
    ⚠️ 章节级而非逐行:「识别清单」「方案对比」类章节整节在**列举**被禁形态,
       被列举的表格行本身不含任何禁令词,逐行护栏一个都挡不住
       (check_lock_strategy.py 实测被自家文档判死 4 处)。"""
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


def scan_perm_tables(lines: List[str], in_code: List[bool], exempt: List[bool]) -> List[Dict]:
    """⚠️ GFM 表头必须校验**紧跟分隔行**——否则散文里
       「旧版『约束 | 类型 | 落点』三列表已作废」这类**说明文字**会被当成一张缺列的表,
       SKILL 自带模板被自家硬门判死(check_error_contract.py 实测踩过)。"""
    tables, i, n = [], 0, len(lines)
    while i < n:
        if in_code[i] or exempt[i] or "|" not in lines[i]:
            i += 1
            continue
        cells = split_row(lines[i])
        if len(cells) < 3 or is_separator_row(cells) or not is_perm_table_header(cells):
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
    return bool(PLACEHOLDER_RE.match(v))


def has_perm_signal(lines: List[str], in_code: List[bool], exempt: List[bool]) -> List[Dict]:
    """权限约束信号:只认**标题行**,跳过豁免章节与代码块。
    ⚠️ **刻意不扫正文散文**:详细设计正文里出现「数据权限」四字几乎是必然的,
       扫正文会让每份合规设计满屏假红(与 check_metric_spec.py 同一条纪律)。"""
    hits = []
    for i, ln in enumerate(lines):
        if in_code[i] or exempt[i]:
            continue
        m = re.match(r"^#{1,6}\s+(.*)$", ln)
        if not m:
            continue
        title = m.group(1)
        if PERM_SIGNAL_RE.search(title) and not PERM_SIGNAL_NEG_RE.search(title):
            hits.append({"line": i + 1, "title": title.strip()[:80]})
    return hits


def scan_requirement_constraints(path: Path) -> Tuple[List[Dict], List[Dict]]:
    """从上游需求文档里抓约束句。返回 (命中, 读取错误)。
    ⚠️ 这一侧**扫正文**(与设计侧只扫标题刻意不同):约束句天生写在正文里
       (「该列表仅本部门可见」不会是个标题)。假红代价由「只认强句式」这道闸门承担。"""
    hits, errs = [], []
    for f in find_md_files(path):
        try:
            lines = f.read_text(encoding="utf-8", errors="strict").splitlines()
        except Exception as e:  # noqa: BLE001
            errs.append({"file": str(f), "error": f"{type(e).__name__}: {e}"})
            continue
        in_code = strip_code_fences(lines)
        exempt = exempt_line_flags(lines, in_code)
        for i, ln in enumerate(lines):
            if in_code[i] or exempt[i]:
                continue
            if ln.lstrip().startswith("#"):
                continue
            m = PERM_SIGNAL_RE.search(ln)
            if m and not PERM_SIGNAL_NEG_RE.search(ln):
                hits.append({"file": str(f), "line": i + 1,
                             "matched": m.group(0), "text": ln.strip()[:120]})
    return hits, errs


def scan_file(path: Path, root: Path) -> Dict:
    rel = str(path.relative_to(root)) if root in path.parents or path == root else str(path)
    try:
        text = path.read_text(encoding="utf-8", errors="strict")
    except Exception as e:  # noqa: BLE001
        return {"file": rel, "read_error": f"{type(e).__name__}: {e}",
                "tables": [], "signals": [], "findings": []}
    lines = text.splitlines()
    in_code = strip_code_fences(lines)
    exempt = exempt_line_flags(lines, in_code)
    tables = scan_perm_tables(lines, in_code, exempt)
    signals = has_perm_signal(lines, in_code, exempt)
    findings: List[Dict] = []

    for tb in tables:
        idx = {c: col_index(tb["header"], c) for c in REQUIRED_COLUMNS}
        missing = [c for c in REQUIRED_COLUMNS if idx[c] is None]
        if missing:
            findings.append({"code": "G1", "level": "Critical", "line": tb["header_line"],
                             "msg": f"权限与可见范围约束落点表缺列: {'、'.join(missing)}"})
        width = len(tb["header"])
        for row in tb["rows"]:
            ln = row["line"]
            if len(row["cells"]) != width:
                findings.append({"code": "G3", "level": "Critical", "line": ln,
                                 "msg": f"数据行 {len(row['cells'])} 格,表头 {width} 格——"
                                        f"最常见原因是格内 `|` 未按 GFM 转义为 `\\|`"})
                continue
            for c in REQUIRED_COLUMNS:
                if idx[c] is None:
                    continue
                v = _cell(row, idx[c])
                if _is_empty(v):
                    findings.append({"code": "G2", "level": "Critical", "line": ln,
                                     "msg": f"「{c}」为空或占位: {v!r}"})
            kind = _norm(_cell(row, idx["约束类型"])) if idx["约束类型"] is not None else ""
            if kind and not _is_empty(kind) and not any(k in kind for k in CONSTRAINT_KINDS):
                findings.append({"code": "G4", "level": "Critical", "line": ln,
                                 "msg": f"「约束类型」{kind!r} 不在四档枚举内"
                                        f"({'/'.join(CONSTRAINT_KINDS)})"})
            src = _cell(row, idx["约束主体来源"]) if idx["约束主体来源"] is not None else ""
            if src and not _is_empty(src) and CLIENT_SUPPLIED_RE.search(src) \
                    and not CLIENT_SUPPLIED_OK_RE.search(src):
                findings.append({"code": "G5", "level": "Critical", "line": ln,
                                 "msg": f"「约束主体来源」取自客户端: {src!r}——"
                                        f"客户端自称是谁就是谁,过滤写得再对也等于没有;"
                                        f"须取自登录态/token/会话,或写明服务端以登录态为准"})
            land = _cell(row, idx["落点"]) if idx["落点"] is not None else ""
            if land and not _is_empty(land) and VAGUE_LANDING_RE.match(_norm(land)):
                findings.append({"code": "G6", "level": "Critical", "line": ln,
                                 "msg": f"「落点」不可指认: {land!r}——须给出具体的层与位置"
                                        f"(接口/服务方法/SQL 条件/前端组件)"})
    return {"file": rel, "tables": tables, "signals": signals, "findings": findings}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="检查项 40:权限与可见范围约束落地(强制产出落点表)")
    ap.add_argument("path", type=Path, help="详细设计文档文件或目录")
    ap.add_argument("--requirements", type=Path, default=None,
                    help="可选:上游研发需求文档(PRD)文件或目录。传入后额外做"
                         "「PRD 有约束句 → 设计无落点」对账(P0)。不传则这一半不查。")
    ap.add_argument("--json", action="store_true", help="JSON 格式输出")
    ap.add_argument("--strict", action="store_true", help="Important 也计入失败")
    args = ap.parse_args(argv)

    target: Path = args.path
    # ⚠️ exists() 与 is_dir() 必须分开判:合并写成 `if not is_dir(): return 0` 会把
    #    「路径根本不存在」和「传入单个文件=合法 N/A」混为一谈 → 手滑写错路径等于静默放行。
    if not target.exists():
        print(f"错误: 路径不存在: {target}", file=sys.stderr)
        return 2
    files = find_md_files(target)
    if not files:
        print(f"错误: 未找到任何 .md 文件: {target}", file=sys.stderr)
        return 2

    root = target if target.is_dir() else target.parent
    results = [scan_file(f, root) for f in files]

    read_errors = [r for r in results if r.get("read_error")]
    # 全仓登记口径:**部分**不可读 → 继续 + read_errors[] 进 --json;**全部**不可读才 exit 2。
    # ⚠️ 单个文件读不出就 exit 2 会让 --json stdout 为空、调用方 json.load 崩,
    #    其余文件已检出的 Critical 被整体丢弃,而 exit 2 按约定是「不计维度失败」
    #    → 一个断链符号链接就能让整档静默不跑(check_list_page_scale.py 修过同一条)。
    if read_errors and len(read_errors) == len(results):
        for r in read_errors:
            print(f"错误: 无法读取 {r['file']}: {r['read_error']}", file=sys.stderr)
        return 2

    n_tables = sum(len(r["tables"]) for r in results)
    n_signals = sum(len(r["signals"]) for r in results)
    findings: List[Dict] = []
    for r in results:
        for f in r["findings"]:
            findings.append({**f, "file": r["file"]})

    # W1:有信号却一张表都没有。⚠️ 一张表都没有时**只报 W1、不报 G1~G6**
    #    (逐条见 docstring;不这么做,W1 降 Important 的取舍会被自己当场抵消)。
    if n_tables == 0 and n_signals > 0:
        for r in results:
            for s in r["signals"]:
                findings.append({"code": "W1", "level": "Important", "file": r["file"],
                                 "line": s["line"],
                                 "msg": f"出现权限/可见范围约束信号「{s['title']}」"
                                        f"但全文无「权限与可见范围约束落点表」"})

    # P0/W2:仅在传了 --requirements 时做。
    req_hits: List[Dict] = []
    req_errors: List[Dict] = []
    requirements_scanned = args.requirements is not None
    if requirements_scanned:
        if not args.requirements.exists():
            print(f"错误: --requirements 路径不存在: {args.requirements}", file=sys.stderr)
            return 2
        req_hits, req_errors = scan_requirement_constraints(args.requirements)
        # ⚠️ 口径对齐:设计侧 findings 的 file 是**相对 root** 的路径,需求侧原样用 str(f)
        #    会在传绝对路径时产出绝对路径,同一份 --json 里两种口径并存、调用方难以拼接。
        _rq_root = args.requirements if args.requirements.is_dir() else args.requirements.parent
        for _h in req_hits:
            try:
                _h["file"] = str(Path(_h["file"]).relative_to(_rq_root))
            except ValueError:
                pass
        registered = []
        for r in results:
            for tb in r["tables"]:
                i0 = col_index(tb["header"], "约束原文")
                if i0 is None:
                    continue
                for row in tb["rows"]:
                    registered.append(_norm(_cell(row, i0)))
        # ⚠️ 按「约束片段 + 出处」去重:同一句约束在 PRD 里重复出现(或同一文件被扫两次)
        #    不该产出 N 条指向同一条约束的 Critical —— 那会让报告噪声淹没真问题。
        _p0_seen = set()
        for h in req_hits:
            key = _norm(h["matched"])
            # 只要有任一登记行提到了这条约束的关键片段,即认为已落点。
            # ⚠️ 判据刻意宽松(只判「有没有被提到」):本维度的立论是「设计里一个字没提」,
            #    ⛔ 不做语义等价证明——那要连业务才知道,是人的活。
            # ⚠️ **已登记的局限(不是 bug,是取舍)**:比对是**字面子串**,同义改写会误报
            #    (需求「只有管理员能导出」↔ 表里「仅管理员可导出」)。
            #    之所以不放宽:放宽的方向是同义词/语义匹配,那必然滑向「猜」,失败方向是**假绿**;
            #    而本形态的假红有一个**明确且正当**的改法——把第 1 列改成逐字引用 PRD 原文,
            #    那本就是检查项 40 第 1 列的硬性要求(引 PRD 位置 + 原文摘要)。
            #    故:宁可要这个「改法即合规」的假红,不要一个会漏报的宽匹配。
            if not any(key and key in reg for reg in registered):
                if key in _p0_seen:
                    continue
                _p0_seen.add(key)
                findings.append({
                    "code": "P0", "level": "Critical",
                    "file": h["file"], "line": h["line"],
                    "msg": f"上游需求存在约束「{h['matched']}」但设计的落点表未登记: {h['text']}"
                           f"(⚠️ 若已登记但措辞不同——如需求写「只有管理员能导出」、"
                           f"表里写成「仅管理员可导出」——本判据按**字面**比对,会误报;"
                           f"改法是把第 1 列改成**逐字引用 PRD 原文**,而那本就是检查项 40 的要求)"})
        if n_tables > 0 and not req_hits:
            # ⚠️ 只报一条即可(它是「入参可能指错了」的提示,不是逐表缺陷),
            #    但**必须扫完所有文件**才能找到那张表。
            #    ⛔ 别写成外层 `for r in results:` 末尾无条件 `break` —— 那等于只看 results[0],
            #    而 find_md_files 是 sorted(rglob),本仓库强制的输出命名恰是
            #    `00_索引.md` + `01_详细设计.md`,落点表在 `01_`、results[0] 是没有表的索引页,
            #    于是 **W2 在标准多文件拆分态下恒不触发**(实测:表在第 1 个文件时报、
            #    挪到第 2 个文件即一条都不报)。
            _w2_done = False
            for r in results:
                if _w2_done:
                    break
                for tb in r["tables"]:
                    if tb["rows"]:
                        findings.append({
                            "code": "W2", "level": "Important", "file": r["file"],
                            "line": tb["header_line"],
                            "msg": "落点表有登记行,但上游需求里未抓到任何约束句——"
                                   "请确认 --requirements 是否指向了正确的需求文档"})
                        _w2_done = True
                        break

    criticals = [f for f in findings if f["level"] == "Critical"]
    importants = [f for f in findings if f["level"] == "Important"]
    skipped = (n_tables == 0 and n_signals == 0 and not req_hits)

    if args.json:
        print(json.dumps({
            "target": str(target), "files": len(files),
            "tables": n_tables, "signals": n_signals,
            "skipped": skipped,
            # ⚠️ false 表示「PRD→设计 这一半根本没查」,⛔ 不得读成通过。
            "requirements_scanned": requirements_scanned,
            "requirement_constraints": len(req_hits),
            "critical": len(criticals), "important": len(importants),
            "findings": findings,
            "read_errors": [{"file": r["file"], "error": r["read_error"]} for r in read_errors]
                           + req_errors,
        }, ensure_ascii=False, indent=2))
    else:
        print(f"检查项 40 · 权限与可见范围约束落地 | 目标: {target}")
        print(f"扫描 {len(files)} 个 .md | 落点表 {n_tables} 张 | 权限信号 {n_signals} 处")
        if requirements_scanned:
            print(f"上游需求约束句 {len(req_hits)} 条（--requirements 已传入）")
        else:
            print("⚠️ 未传 --requirements：「PRD 有约束、设计无落点」这一半**没有检查**，"
                  "权威判定在核验步骤 1 的人工逐条枚举")
        if skipped:
            print("→ 未发现权限约束信号，也无落点表：本档不适用（N/A 跳过）")
            print("⚠️ skipped 不等于通过——该不该有表由 QR 子 Agent 判")
        for f in criticals:
            print(f"  🔴 [{f['code']}] {f['file']}:{f.get('line','?')} {f['msg']}")
        for f in importants:
            print(f"  🟡 [{f['code']}] {f['file']}:{f.get('line','?')} {f['msg']}")
        for r in read_errors:
            print(f"  ⚠️ 无法读取 {r['file']}: {r['read_error']}", file=sys.stderr)
        print(f"Critical {len(criticals)} · Important {len(importants)}")
        # ⚠️ skipped 时**不得再打「✅ 通过」**:同一段输出先说「这不是通过」、两行后又说
        #    「✅ 通过」,读者只会记住后一句。N/A 的结论归 QR 子 Agent 判,不在这里下。
        if not criticals and not importants and not skipped:
            print("✅ 通过")

    if criticals:
        return 1
    if args.strict and importants:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
