#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查项 41 / 核心原则 34:同族增量项的公共单元与排序规则必须在设计期声明(Important 档)。

**★ 判据是「有没有兄弟」,不是「我写了几遍」。**

立论(下游实测):一个页面承载「每版各加一个同构成员」的家族(隐藏运维页的历史数据处理入口,
六个版本各一个,外观相同、只有标题与说明不同)。**同一形态连续复发 3 个版本**,每次都是同样两条:
  ① 新成员**没有公共外壳** —— 家族没抽公共单元,父页样式是 `scoped` 传不进子组件,
     于是每个成员各自复制一份样式,**漏抄即失效**;
  ② 新成员**插错顺序** —— 顺序靠在模板里手工插位 + 一行注释提醒,**无任何机器约束**。

**根因在设计期就已埋下**:设计只写了「每版加一个 X」,没说这个家族的**外壳住在哪**、
**顺序由谁决定**,于是开发期只能照着隔壁成员复制——而「照着隔壁复制一份」是执行体
**最自然**的动作。失败形态是「看起来正常」:类型检查 / lint / 单测全绿、构建通过,
**只有人打开页面并排比对才看得出来**,到测试期才发现的代价远高于设计期补两行声明。

强制产出 5 列「同族增量项声明表」:
    | 家族名 | 公共单元位置 | 成员 glob | 注册表/排序数据源 | 排序规则 |

⚠️ **第 5 列「排序规则」是本表最容易敷衍、也最该卡死的一列**(S4):
   ⛔ 不接受「按代码里的书写顺序」「新增时插到对应位置」这类表述 —— 那等于**把顺序交给物理位置**,
   而物理位置不是数据、没有任何机器能校验它,正是复发那两条里的第 ②。
   须给出**能算出来的东西**:注册表文件 / 排序键字段 / 排序函数。

⚠️ **第 2 列「公共单元位置」对应第 ①**:外观与结构由**哪个唯一单元**产出(组件路径 / 基类 / 模板),
   以及差异量如何参数化。「各成员自行实现」「见上」一律不算 —— 不可指认等于没声明。

判据:
  S1 表存在但 5 列不齐                                      Critical
  S2 逐格空或占位                                            Critical
  S3 数据行格数不符(点名 `|` 未转义)                          Critical
  S4 「排序规则」交给物理位置(书写顺序/插到对应位置/…)          Critical
  S5 「公共单元位置」不可指认(各自实现/见上/框架自动处理/…)      Critical
  S6 同名家族的「公共单元位置」跨表跨文件不一致                 Critical
  W1 「成员 glob」不像一个 glob(无路径分隔、无通配、无扩展名)    Important(不占退出码)

⚠️⚠️ **本脚本刻意不做「缺表」判定,`skipped: true` 不等于通过。**
   触发信号(「每个版本新增一个 X」「每次迭代追加一项 Y」)天生是**正文散文**、不会是个标题,
   而本仓库既有两条相反的教训把两条路都堵死了:
     · 扫正文散文 —— `check_metric_spec.py` / `check_permission_constraint.py` 实测的结论是
       「合规文档满屏假红」,且**本 SKILL 自己的检查项 41 正文必然逐字写出这些触发词**
       (要讲清规则就得把它举出来),等于每轮固定一条打在自家文档上的假红;
     · 只扫标题行 —— 真实设计里没人会把「每版新增一个运维入口」写成标题,
       于是这条判据**永远不会触发**,却在报告里占着一个「查过了」的位置,方向是**假绿**。
   故按 `check_count_claim_table.py` 的同款取舍:**脚本只管「表一旦产出,它自身合不合格」**,
   「**这份设计该不该有这张表**」由**检查项 41 核验步骤 1 的人工逐条枚举**判,
   ⛔ 不得因为脚本 `skipped`/`exit 0` 就跳过那一步。

⚠️ **缺表判 Important、表一旦产出则缺列/空格判 Critical** 是本仓库既有先例(U1/E1/Z1/W1);
   本脚本因不做缺表判定,Critical 全部落在「已产出的表自身的缺陷」上,与该先例同向。
   **检查项 41 的维度结论按 Important 判** —— 严重度分档是给**退出码**用的、
   不是给**维度结论**用的(同维度 35 的 U2/U3 与「Important 档」并存)。

★ **去重边界**:本脚本只管**设计期这张声明表**。
  「开发期成员有没有真的用上那个公共单元 / 有没有进排序数据源」由**被测项目侧**的
  `AIDP_HOME/scripts/check_sibling_family.py`(F0~F4)承担、并由 `code-verification-loop` 维度 15 派发,
  ⛔ 本 SKILL 严禁重写那五条(与核心原则 27 对 `check_upstream_call_log.py` 是同一条纪律)。
  ⚠️ **两个脚本名字只差一个 `_spec` 后缀,别看串**:本脚本在本仓 architect 的 `scripts/` 下、
  吃**设计文档**;那个在**被测项目**的运行契约 `scripts/` 下、吃**源码**。

退出码:0 = 无 Critical(含 N/A 跳过);1 = 检出 Critical;2 = 入参或环境错。
严重度分档走 --json,不占用退出码。
用法:
  python3 check_sibling_family_spec.py <设计文档文件或目录> --json
  python3 check_sibling_family_spec.py --self-check  # 独立模式,不可与 path/--json/--strict 组合
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

REQUIRED_COLUMNS = ["家族名", "公共单元位置", "成员glob", "排序数据源", "排序规则"]

EMPTY_MARKERS = {"", "-", "—", "--", "n/a", "na", "无", "待定", "tbd", "同上", "略", "见上"}
# ⚠️ 占位正则必须**全串锚定**:否则「`src/views/ops/entries/{名称}Entry.vue`」这种
#    已填实、只留一个槽位的合规写法会被整格判空
#    (check_error_contract.py / check_metric_spec.py / check_permission_constraint.py 都踩过同一个坑)。
PLACEHOLDER_RE = re.compile(r"^\{[^{}]*\}$|^<[^<>]+>$|^\[[^\[\]]*\]$")

# S4:把顺序交给**物理位置**的表述。⚠️ 这一条是本表的核心判据,词表宁可窄不可宽。
PHYSICAL_ORDER_RE = re.compile(
    r"书写顺序|代码(里|中)?的?顺序|出现顺序|声明顺序|排版顺序|文件顺序|自上而下|"
    r"模板(里|中)的?位置|手工插位|手动插(入|位)|插到(对应|相应)位置|按位置|照位置")

# S5:「公共单元位置」不可指认的表述。
# ⚠️ 只用**否定清单**,⛔ 不加「必须含路径/标识符」这类正向要求 ——
#    「运维入口公共卡片组件」这种纯中文但唯一可指认的写法会被正向要求判死,方向是假红,
#    而 S5 是 Critical,假红的代价比欠覆盖大得多(见 G6 的同款取舍)。
VAGUE_UNIT_RE = re.compile(
    r"各(成员|自)(自行|自己)?实现|各自(实现|复制)|由各成员|成员自带|"
    r"框架自动|自动处理|按业务|视(情况|业务)|参见上文|见上文|详见上|待定|暂无")
PARAMETER_CONTEXT_RE = re.compile(
    r"title|desc|label|action|slot|prop|props|参数|配置|变量|文案|数据项", re.IGNORECASE)
FAMILY_TABLE_HEADING_RE = re.compile(r"同族增量项.*声明表|同族.*增量.*表")

# W1:「成员 glob」像不像一个 glob —— 至少要有路径分隔 / 通配 / 扩展名之一。
GLOB_SHAPE_RE = re.compile(r"[/\\*?]|\.[A-Za-z0-9]{1,6}\b")

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
       本表第 3 列是 glob、第 5 列可能写「`order` 升序 \\| 同序按 `key` 字典序」,
       含 `|` 时作者必须按 GFM 规矩转义,裸 split 会把**已正确转义**的合规行多切一格、当场判 S3。"""
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
    """⚠️⚠️ **本表有两组列名字面互相包含,是本脚本最容易静默失效的地方:**
       ①「排序数据源」与「排序规则」**都含「排序」** —— 任一支写成裸 `"排序" in c`,
         两列即互认,`col_index` 会把后者解析到前者的位置,**S4(本表核心判据)整条静默失效**
         (变异 fixture 零命中 = 假绿)而表头看着完全正常;
       ②「公共单元位置」含「位置」,而「成员 glob」在真实写法里常被写成「成员文件位置」。
       **两支必须各自排掉对方的专名词,⛔ 别只改一边**
       —— 与 check_list_page_scale.py / check_permission_constraint.py 是同一个坑,第三次了。"""
    c = _norm(cell)
    if concept == "家族名":
        return "家族名" in c or "族名" in c or (
            "家族" in c and "成员" not in c and "位置" not in c and "单元" not in c)
    if concept == "公共单元位置":
        return "公共单元" in c or "外壳" in c or (
            "公共" in c and ("位置" in c or "单元" in c or "组件" in c))
    if concept == "成员glob":
        return "glob" in c.lower() or (
            "成员" in c and "排序" not in c and "数据源" not in c and "公共" not in c)
    if concept == "排序数据源":
        # ⚠️ 必须排掉「规则」(见上 ①)。
        return "注册表" in c or ("数据源" in c and "规则" not in c)
    if concept == "排序规则":
        # ⚠️ 必须排掉「数据源」「注册表」(见上 ①)。
        return "排序规则" in c or (
            "规则" in c and "数据源" not in c and "注册表" not in c and "成员" not in c)
    return False


def col_index(cells: List[str], concept: str) -> Optional[int]:
    for i, c in enumerate(cells):
        if cell_matches_column(c, concept):
            return i
    return None


def is_family_table_header(cells: List[str]) -> bool:
    """⚠️ 判据是「专名列任一 + ≥3 契约列」,⛔ 别改回「某一列必须在」:
       姊妹脚本 check_residual_assertions.py 的 C2 实测过那个洞——恰恰把作为
       无条件前提的那一列删掉的表**整张认不出来**,于是缺列最严重的反而最轻(严重度完全反了)。"""
    if len(cells) < 3:
        return False
    hit = [c for c in REQUIRED_COLUMNS if col_index(cells, c) is not None]
    named = any(c in hit for c in ("公共单元位置", "成员glob", "排序规则"))
    # ⚠️ 单元格长度上限,**预防性护栏,已实测确认它不是挡住 CLAUDE.md 的那一道**:
    #    `AIDP_HOME/../AIDP-AGENTS.md` 的 SKILL 清单表单格是几千字散文、本表的列名也确实出现在里面,
    #    但实测把本闸门改成恒 False 后,CLAUDE.md 仍是 **0 张表** —— 真正挡住它的是
    #    scan_family_tables 里「表头必须紧跟 GFM 分隔行」那道闸门(它是**数据行**、后面不跟分隔行)。
    #    ⛔ 别照搬姊妹脚本那句「无长度闸门时整行被认成表头」——那是**没实测就抄过来的断言**,
    #    正是核心原则 30 要消灭的形态(check_permission_constraint.py 就地订正过同一句)。
    #    保留本闸门的理由只有一条,且**已实测**:「一行长散文 + 紧跟 GFM 分隔行」这种形态
    #    拆掉闸门后 `tables` 由 **0 变 1**(整行被认成表头),其数据行随即进入 S1~S6 判定面。
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


def _near_family_table_heading(lines: List[str], row_index: int, in_code: List[bool]) -> bool:
    """识别 canonical 标题后的严重残缺表，避免只剩 2 列时整张表降成 skipped。"""
    for j in range(row_index - 1, max(-1, row_index - 8), -1):
        if in_code[j]:
            continue
        text = lines[j].strip()
        if not text:
            continue
        m = re.match(r"^#{1,6}\s+(.*)$", text)
        if m:
            return bool(FAMILY_TABLE_HEADING_RE.search(_norm(m.group(1))))
    return False


def unit_is_vague(unit: str) -> bool:
    """S5 只判公共外壳本身不可指认，不误伤成员差异参数各自维护。"""
    normalized = _norm(unit)
    if VAGUE_UNIT_RE.search(normalized):
        return True
    if re.search(r"各自维护|各成员各自维护|由各成员维护", normalized):
        return not bool(PARAMETER_CONTEXT_RE.search(normalized))
    return False


def scan_family_tables(lines: List[str], in_code: List[bool], exempt: List[bool]) -> List[Dict]:
    """⚠️ GFM 表头必须校验**紧跟分隔行**——否则散文里
       「旧版『家族名 | 公共单元位置 | 排序规则』三列表已作废」这类**说明文字**
       会被当成一张缺列的表,SKILL 自带模板被自家硬门判死(check_error_contract.py 实测踩过)。"""
    tables, i, n = [], 0, len(lines)
    while i < n:
        if in_code[i] or exempt[i] or "|" not in lines[i]:
            i += 1
            continue
        cells = split_row(lines[i])
        titled_family_table = _near_family_table_heading(lines, i, in_code)
        if (len(cells) < 2 or is_separator_row(cells)
                or (not is_family_table_header(cells) and not titled_family_table)):
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


def strip_prohibition(val: str) -> str:
    """剥掉格内的**禁令段**再判 S4。

    ⚠️ 必须剥、且**只剥那一小段**,⛔ 不整格跳过:
       合规写法常是「按注册表 `order` 升序,⛔ 不按代码书写顺序」——
       不剥则整格被 S4 判死(**把明确写对的人判成写错**,而他没有别的改法);
       整格跳过则「一边写 ⛔ 一边真在用物理位置」蒙混过关
       (check_render_merge_table.py 的 R5 是同一条取舍,已实测过两个方向)。
    剥的范围:禁令词起,到**下一个分句边界**(,、;。/ 或 ) 或串尾)止。"""
    return re.sub(r"[⛔✅]?\s*(严禁|禁止|不得|不是|不按|不用|不走|非|而非|勿)[^,、;。,;)）]*",
                  "", val)


def scan_file(path: Path, root: Path) -> Dict:
    rel = str(path.relative_to(root)) if root in path.parents or path == root else str(path)
    try:
        text = path.read_text(encoding="utf-8", errors="strict")
    except Exception as e:  # noqa: BLE001
        return {"file": rel, "read_error": f"{type(e).__name__}: {e}",
                "tables": [], "declarations": [], "findings": []}
    lines = text.splitlines()
    in_code = strip_code_fences(lines)
    exempt = exempt_line_flags(lines, in_code)
    tables = scan_family_tables(lines, in_code, exempt)
    findings: List[Dict] = []
    declarations: List[Dict] = []

    for tb in tables:
        idx = {c: col_index(tb["header"], c) for c in REQUIRED_COLUMNS}
        missing = [c for c in REQUIRED_COLUMNS if idx[c] is None]
        if missing:
            findings.append({"code": "S1", "level": "Critical", "line": tb["header_line"],
                             "msg": f"同族增量项声明表缺列: {'、'.join(missing)}"})
        width = len(tb["header"])
        for row in tb["rows"]:
            ln = row["line"]
            if len(row["cells"]) != width:
                findings.append({"code": "S3", "level": "Critical", "line": ln,
                                 "msg": f"数据行 {len(row['cells'])} 格,表头 {width} 格——"
                                        f"最常见原因是格内 `|` 未按 GFM 转义为 `\\|`"})
                continue
            for c in REQUIRED_COLUMNS:
                if idx[c] is None:
                    continue
                v = _cell(row, idx[c])
                if _is_empty(v):
                    findings.append({"code": "S2", "level": "Critical", "line": ln,
                                     "msg": f"「{c}」为空或占位: {v!r}"})

            order = _cell(row, idx["排序规则"]) if idx["排序规则"] is not None else ""
            if order and not _is_empty(order):
                judged = strip_prohibition(order)
                if PHYSICAL_ORDER_RE.search(_norm(judged)):
                    findings.append({"code": "S4", "level": "Critical", "line": ln,
                                     "msg": f"「排序规则」把顺序交给了物理位置: {order!r}——"
                                            f"物理位置不是数据、没有任何机器能校验它;"
                                            f"须给出能算出来的东西(注册表文件/排序键字段/排序函数)"})

            unit = _cell(row, idx["公共单元位置"]) if idx["公共单元位置"] is not None else ""
            if unit and not _is_empty(unit) and unit_is_vague(unit):
                findings.append({"code": "S5", "level": "Critical", "line": ln,
                                 "msg": f"「公共单元位置」不可指认: {unit!r}——"
                                        f"须给出唯一产出外观/结构的那一个单元"
                                        f"(组件路径/基类/模板),并说明差异量如何参数化"})

            glob_v = _cell(row, idx["成员glob"]) if idx["成员glob"] is not None else ""
            if glob_v and not _is_empty(glob_v) and not GLOB_SHAPE_RE.search(glob_v):
                findings.append({"code": "W1", "level": "Important", "line": ln,
                                 "msg": f"「成员 glob」不像一个 glob: {glob_v!r}——"
                                        f"下游机器门要拿它去匹配文件,须含路径分隔/通配/扩展名"})

            fam = _norm(_cell(row, idx["家族名"])) if idx["家族名"] is not None else ""
            if fam and not _is_empty(fam) and unit and not _is_empty(unit):
                declarations.append({"family": fam, "unit": _norm(unit), "line": ln})

    return {"file": rel, "tables": tables, "declarations": declarations, "findings": findings}


def run_self_check() -> int:
    """端到端回归 S1~S6/W1/合规/N/A；不依赖第三方测试框架。"""
    header = "| 家族名 | 公共单元位置 | 成员 glob | 注册表/排序数据源 | 排序规则 |\n"
    separator = "| :- | :- | :- | :- | :- |\n"
    good_row = ("| 运维入口 | `src/Card.vue` 唯一外壳；差异由 title prop 参数化 | "
                "`src/entries/*.vue` | `src/entries/registry.ts` | 按 `order` 升序 |\n")
    cases = []

    def add(name: str, files: Dict[str, str], expected_rc: int,
            code: Optional[str] = None, skipped: Optional[bool] = None,
            critical: Optional[int] = None, important: Optional[int] = None) -> None:
        cases.append({"name": name, "files": files, "rc": expected_rc, "code": code,
                      "skipped": skipped, "critical": critical, "important": important})

    add("S1", {"01.md": "## 同族增量项声明表\n\n"
        "| 家族名 | 公共单元位置 |\n"
        "| :- | :- |\n"
        "| 运维入口 | `src/Card.vue` |\n"}, 1, "S1")
    add("S2", {"01.md": "## 同族增量项声明表\n\n" + header + separator
        + "| 运维入口 | {待定} | `src/entries/*.vue` | `registry.ts` | 按 `order` 升序 |\n"}, 1, "S2")
    add("S3", {"01.md": "## 同族增量项声明表\n\n" + header + separator
        + "| 运维入口 | `src/Card.vue` | `src/entries/*.vue` | `registry.ts` | 按 `order` | 同序按 key |\n"}, 1, "S3")
    add("S4", {"01.md": "## 同族增量项声明表\n\n" + header + separator
        + "| 运维入口 | `src/Card.vue` | `src/entries/*.vue` | `registry.ts` | 按代码里的书写顺序 |\n"}, 1, "S4")
    add("S5", {"01.md": "## 同族增量项声明表\n\n" + header + separator
        + "| 运维入口 | 各成员自行实现 | `src/entries/*.vue` | `registry.ts` | 按 `order` 升序 |\n"}, 1, "S5")
    add("S6", {
        "01.md": "## 同族增量项声明表\n\n" + header + separator + good_row,
        "02.md": "## 同族增量项声明表\n\n" + header + separator
            + "| 运维入口 | `src/OtherCard.vue` | `src/entries/*.vue` | `registry.ts` | 按 `order` 升序 |\n",
    }, 1, "S6")
    add("W1", {"01.md": "## 同族增量项声明表\n\n" + header + separator
        + "| 运维入口 | `src/Card.vue` | Entry | `registry.ts` | 按 `order` 升序 |\n"},
        0, "W1", critical=0, important=1)
    add("合规", {"01.md": "## 同族增量项声明表\n\n" + header + separator + good_row},
        0, skipped=False, critical=0, important=0)
    add("禁令合规", {"01.md": "## 同族增量项声明表\n\n" + header + separator
        + "| 运维入口 | `src/Card.vue` | `src/entries/*.vue` | `registry.ts` | 按 `order` 升序，⛔ 不按代码书写顺序 |\n"},
        0, skipped=False, critical=0, important=0)
    add("禁令夹带", {"01.md": "## 同族增量项声明表\n\n" + header + separator
        + "| 运维入口 | `src/Card.vue` | `src/entries/*.vue` | `registry.ts` | 按代码书写顺序，⛔ 不按文件顺序 |\n"},
        1, "S4")
    add("转义管道", {"01.md": "## 同族增量项声明表\n\n" + header + separator
        + "| 运维入口 | `src/Card.vue` | `src/entries/*.vue` | `registry.ts` | 按 `order` 升序 \\| 同序按 `key` 字典序 |\n"},
        0, skipped=False, critical=0, important=0)
    add("N/A", {"01.md": "# 详细设计\n\n本版本不涉及持续增长的同构成员。\n"},
        0, skipped=True, critical=0, important=0)

    failures = []
    try:
        with tempfile.TemporaryDirectory(prefix="sibling-family-selfcheck-") as td:
            root = Path(td)
            for case in cases:
                case_dir = root / case["name"].replace("/", "-")
                case_dir.mkdir()
                for filename, content in case["files"].items():
                    (case_dir / filename).write_text(content, encoding="utf-8")
                proc = subprocess.run(
                    [sys.executable, str(Path(__file__).resolve()), str(case_dir), "--json"],
                    text=True, capture_output=True, check=False, timeout=15)
                try:
                    payload = json.loads(proc.stdout)
                except json.JSONDecodeError:
                    failures.append(f"{case['name']}: stdout 非 JSON: {proc.stdout!r} {proc.stderr!r}")
                    continue
                rules = {f["code"] for f in payload.get("findings", [])}
                ok = proc.returncode == case["rc"]
                if case["code"] is not None:
                    ok = ok and case["code"] in rules
                for key in ("skipped", "critical", "important"):
                    if case[key] is not None:
                        ok = ok and payload.get(key) == case[key]
                if case["name"] == "N/A":
                    ok = ok and "不得读成通过" in str(payload.get("skip_reason"))
                print(f"SELF-CHECK {case['name']}: {'PASS' if ok else 'FAIL'}")
                if not ok:
                    failures.append(f"{case['name']}: rc={proc.returncode}, payload={payload}")
    except OSError as exc:
        print(f"SELF-CHECK 环境错误: {exc}", file=sys.stderr)
        return 2
    except subprocess.TimeoutExpired as exc:
        # 子进程超时是**环境问题**(机器负载/被挂起),不是产物违规。按全仓退出码约定
        # 归 2(与同段 OSError 一致);返 1 会让调用方把它读成「自检检出缺陷」。
        print(f"SELF-CHECK 超时失败: {exc}", file=sys.stderr)
        return 2
    if failures:
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1
    print(f"SELF-CHECK 通过: {len(cases)}/{len(cases)}")
    print("N/A skipped=true，明确不等于通过")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="检查项 41:同族增量项的公共单元与排序规则设计期声明(强制产出声明表)")
    ap.add_argument("path", nargs="?", type=Path, help="详细设计文档文件或目录")
    ap.add_argument("--json", action="store_true", help="JSON 格式输出")
    ap.add_argument("--strict", action="store_true", help="Important 也计入失败")
    ap.add_argument("--self-check", action="store_true", help="运行 S1~S6/W1/合规/N/A 内建回归")
    args = ap.parse_args(argv)

    if args.self_check:
        if args.path is not None or args.json or args.strict:
            print("错误: --self-check 不能与 path / --json / --strict 同时使用", file=sys.stderr)
            return 2
        return run_self_check()
    if args.path is None:
        print("错误: 缺少详细设计文档文件或目录(或使用 --self-check)", file=sys.stderr)
        return 2

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
    findings: List[Dict] = []
    for r in results:
        for f in r["findings"]:
            findings.append({**f, "file": r["file"]})

    # S6:同名家族的「公共单元位置」跨表跨文件不一致。
    # ⚠️ **跨文件聚合判定,须传目录**:多册拆分是 M/L 档强制行为、增量按「增量/补充生成约定」
    #    必落新 `NN_` 文件,同一家族被第二张表再声明一次是**正常工作流**;
    #    不可退让的是**公共单元唯一**、不是**表唯一**(与 check_count_claim_table.py 的 C7 同形态)。
    by_family: Dict[str, List[Dict]] = {}
    for r in results:
        for d in r["declarations"]:
            by_family.setdefault(d["family"], []).append({**d, "file": r["file"]})
    for fam, decls in by_family.items():
        units = {d["unit"] for d in decls}
        if len(units) > 1:
            for d in decls:
                findings.append({
                    "code": "S6", "level": "Critical", "file": d["file"], "line": d["line"],
                    "msg": f"家族「{fam}」的「公共单元位置」跨表不一致: {sorted(units)}——"
                           f"公共单元必须唯一,两份声明必然各自演进"})

    # ⚠️ 一张表都没有 = **本脚本不适用**,⛔ **不等于通过**。
    #    「该不该有这张表」由检查项 41 核验步骤 1 的人工枚举判(理由见 docstring)。
    skipped = (n_tables == 0)

    criticals = [f for f in findings if f["level"] == "Critical"]
    importants = [f for f in findings if f["level"] == "Important"]

    if args.json:
        print(json.dumps({
            "target": str(target),
            "files_scanned": len(files),
            "tables": n_tables,
            "families": sorted(by_family.keys()),
            "skipped": skipped,
            "skip_reason": "未找到「同族增量项声明表」——本脚本不判缺表,"
                           "表该不该有由检查项 41 核验步骤 1 人工枚举判,⛔ 不得读成通过"
                           if skipped else None,
            "critical": len(criticals),
            "important": len(importants),
            "read_errors": [{"file": r["file"], "error": r["read_error"]} for r in read_errors],
            "findings": findings,
        }, ensure_ascii=False, indent=2))
    else:
        print("=" * 78)
        print(f"检查项 41 · 同族增量项的公共单元与排序规则声明 | 目标: {target}")
        print("=" * 78)
        print(f"扫描 .md: {len(files)} 个 | 声明表: {n_tables} 张 | "
              f"家族: {len(by_family)} 个 | Critical {len(criticals)} · Important {len(importants)}")
        if read_errors:
            print(f"⚠️  {len(read_errors)} 个文件读不出来,其结论是残缺样本:")
            for r in read_errors:
                print(f"     {r['file']}: {r['read_error']}")
        if skipped:
            print("\n⏭️  未找到「同族增量项声明表」——本脚本**不判缺表**。")
            print("    ⛔ 这**不等于通过**:该不该有这张表,由检查项 41 核验步骤 1 的人工枚举判。")
        # ⚠️ Important 明细必须打全:只打计数等于给出一份「说有问题却不说是什么」的报告
        #    (cvl 的 scan_third_party_mock_antipatterns.py 实测踩过 E)。
        for f in findings:
            tag = "🔴" if f["level"] == "Critical" else "🟡"
            print(f"  {tag} [{f['code']}] {f['file']}:{f['line']}\n       {f['msg']}")
        if not findings and not skipped:
            print("\n✅ 声明表结构性检查通过")

    if criticals:
        return 1
    if args.strict and importants:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
