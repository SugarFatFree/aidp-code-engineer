#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""「统计指标口径表」硬核回检 — dev-logic-architect 检查项 34(Critical,对应核心原则 25)

对应上下游共用的通用规则 **约定39-R11**(五要素)与 **约定39-R12**(同一指标跨页面同源)。
⚠️ 引用一律写全称 `约定39-RNN`:本 SKILL 的 `R1/R2/R3` 已被**上游溯源三项**占用
   (见 `check_upstream_reference.py`),裸写 `R11` 必与之混淆。

背景(下游实测):同一项目两个月内 12 条已关闭缺陷出自同一根因——**详细设计根本没写数值口径**:
  · 预付费明细金额单位写「元」实为积分;
  · 同一指标三处小数位互不一致;
  · 趋势图漏统计某日期之前的数据;积分统计漏掉「已回收」;
  · 「最近购买时间」误用 SKU 级首次购买时间冒充订单级购买时间;
  · 同一指标在总览页 / 商品管理页 / 用量监控页三者互不一致。
没有口径就没有预期值——开发各自默认,测试也无从判对错。对策:把口径前移到设计期定死。

本脚本做**结构性硬核回检**(只判可靠判定的结构缺陷):

【Critical(退出码 1)】
  M1 缺表        —— 有数值展示信号(标题级)却找不到「统计指标口径表」
  M2 缺列        —— 表存在但 8 列固定契约不齐:
                    指标/字段 | 展示位 | 单位 | 小数精度 | 时间窗 | 统计范围 | 取数粒度 | 权威取数口径
  M3 空格/占位   —— 任一格为空、占位符、或「同上/视情况/按业务」这类不可核对表述
  M4 权威口径不一 —— 同名指标出现多行,而「权威取数口径」不逐字一致(约定39-R12)

⚠️ **M1 与 M4 都是「按本次扫描范围聚合」判定,不是逐文件/逐表判定** —— 两个方向都实测翻过车:
   · M1 若逐文件判:本 SKILL 在 M/L 档**强制多册拆分**,口径表落在接口设计册,而带「统计/用量/趋势」
     字样的标题必然散落在详设册与库表册 → 合规多册设计**必假红**;
   · M4 若逐表判:同名指标一旦分散在两张表(多册下几乎必然)冲突不触发,而它要治的原始缺陷正是
     「总览页/商品管理页/用量监控页同一指标三者互不一致」→ **必假绿**,且人读输出还会主动断言
     「同名指标权威口径一致」。
   **因此调用方应传目录**;传单个 `.md` 只判该文件范围,多册场景会误判。

⚠️ 本脚本**不做**语义判定(时间窗写得对不对、统计范围该不该含已回收、粒度选得合不合理),
   那由 QR 子 Agent 按 `references/quality-review-checklist.md` 检查项 34 对照 PRD 逐行判。
   **脚本全绿 ≠ 检查项 34 通过。**

与既有脚本的边界:`check_unit_field.py`(检查项 28 / 核心原则 21)管**存储侧**——A.3 DDL 数值字段
COMMENT 的单位声明与全链路一致;本脚本管**展示/统计侧**——那个数字按什么口径算出来。
二者只有「单位」一项交叠,时间窗 / 统计范围 / 取数粒度三项 28 完全不覆盖。

用法:
    python3 check_metric_spec.py <设计文档路径或目录> [--json]

退出码:
    0 = 通过,或跳过(确无数值展示信号 / 已显式声明「本次无数值展示物」)
    1 = 检出违规(严重度分档读 --json,不占用退出码)
    2 = 入参或环境错(路径不存在、目录下没有 .md)

仅依赖 Python 3.8+ 标准库。
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ── 8 列固定契约(与 quality-review-checklist.md 检查项 34 严格一致) ──
REQUIRED_COLUMNS = ["指标/字段", "展示位", "单位", "小数精度", "时间窗", "统计范围", "取数粒度", "权威取数口径"]

# 逐格非空核验:8 列全部要填实(本表不存在"可留空的列")
EMPTY_MARKERS = {
    "", "-", "—", "–", "─", "n/a", "na", "/", "\\", "待定", "tbd", "todo",
    "?", "??", "待补", "待确认", "暂无", "...", "…", "xxx",
    # ↓ 不可核对表述:能写但等于没写,检查项 34「五要素落字面」明令禁止
    "同上", "略", "按实际", "按实际调整", "视情况", "按业务", "视业务而定",
    "前端处理", "前端自行处理", "见上", "同前", "同左",
}

# ⚠️ 必须**全串锚定**:只有"整格就是一个占位符"才算未填。若写成未锚尾的 `\{[^{}]*\}`,
#    「近 30 天(含今日,{T-29 00:00} 起)」这种**已填实、只留一个槽位**的合规写法会被整格判空——
#    本仓库 check_error_contract.py 就因这一处把自家模板判死过,勿改回。
PLACEHOLDER_RE = re.compile(r"^\{[^{}]*\}$|^<[^<>]+>$")

# 数值展示信号:**只认标题行**(`# ~ ######`)。刻意不扫正文散文——
# 设计文档正文几乎必然出现「统计」二字(如"统计范围""本次统计"),扫正文会让合规文档满屏假红。
METRIC_SIGNAL_RE = re.compile(r"统计|汇总|趋势|排行|榜单|占比|报表|看板|概览|仪表盘|指标|用量")

# ⚠️ 标题级否定护栏(实测必需,勿删)。首版只有上面那条正词表,在本 SKILL 自己的
#    `tech-stack-options.md` 上就假红了——标题「确认汇总」命中「汇总」被判成"有统计展示物却缺表"。
#    设计文档里「确认汇总 / 问题汇总 / 变更清单 / 选型对比」这类**流程性**标题极常见,
#    它们与"给用户看的数字"毫无关系。命中即整行不作为信号。
METRIC_SIGNAL_NEG_RE = re.compile(
    r"确认|问题|风险|变更|评审|清单|规范|流程|附录|目录|索引|待澄清|自检|决策|选型|对比|术语|归档"
    # ↓ 元文档标题(质量检查清单/维度/核心原则/检查项)。设计文档不会用这些做章节名,
    #   但本 SKILL 自己的 checklist 会——不加这一段,脚本会把自家 checklist 判死。
    r"|检查项|维度\s*\d|核心原则|判据|核验清单")

# 章节级豁免:标题命中即整节跳过(含其子标题),与 check_lock_strategy.py 同款。
# Why:设计文档必然要写出「不适用」「备选方案(未采用)」「方案对比」这类章节,
#      逐行护栏挡不住整节列举,合规文档会被判死。
EXEMPT_HEADING_RE = re.compile(r"不适用|未采用|备选方案|方案对比|识别清单|反模式|已废弃|作废")

# 显式声明"本设计确无数值展示物"——命中即跳过 M1(仍校验已存在的表)。
# ⚠️ 必须是**独立成句的声明行** + 否定护栏:`output-module-examples.md` 里恰恰教作者写
#    「**确无数值展示物时**须就地写明『本次无数值展示物』」——把这句**指引**原样抄进设计文档,
#    无差别的 `search(text)` 就会把 M1(本维度唯一的存在性判据)整份关掉(实测假绿)。
NO_METRIC_DECLARE_RE = re.compile(
    r"^\s*[>*\-\s]*\**\s*(?:本次|本设计|本版)?\s*(?:确)?无(?:数值展示物|统计指标(?:展示)?)\s*\**\s*[。.:：]?\s*$")
# 命中即视为"这一行是引用/指引、不是声明"
DECLARE_GUARD_RE = re.compile(r"须|应|时[,，]|不得|禁止|例如|如[:：]|见|参见|模板|判据|硬门")


def find_md_files(path: Path) -> List[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(path.rglob("*.md"))
    return []


def split_row(line: str) -> List[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def is_separator_row(cells: List[str]) -> bool:
    # ⚠️ 空行必须先判掉:split_row("") 得到 [""],把空单元格过滤后 all() 对空序列返回 True,
    #    于是**空行被当成分隔行** ——「候选表头 + 紧跟一个空行」会被识别成一张 0 行的表,
    #    对按表头签名判列的检查器就是一条凭空的「缺列 Critical」。
    #    实测复现:`output-module-examples.md` B.7 的键值表末行 + 空行 → 假红。勿改回。
    if not cells or all(c.strip() == "" for c in cells):
        return False
    return all(re.fullmatch(r":?-{1,}:?", c.replace(" ", "")) for c in cells if c != "")


def _norm(s: str) -> str:
    """归一化:去粗体/反引号/引用符/空白,全角括号→半角。"""
    s = re.sub(r"[*`>\s]", "", s)
    return s.replace("（", "(").replace("）", ")")


def cell_matches_column(cell: str, concept: str) -> bool:
    c = _norm(cell).lower()
    if concept == "指标/字段":
        return "指标" in c or "字段" in c or "数值" in c
    if concept == "展示位":
        return "展示位" in c or "展示位置" in c or "落点" in c or ("页面" in c and "展示" in c)
    if concept == "单位":
        return "单位" in c
    if concept == "小数精度":
        return "精度" in c or "小数" in c or "位数" in c
    if concept == "时间窗":
        return "时间窗" in c or "时间范围" in c or "统计周期" in c or "时间口径" in c
    if concept == "统计范围":
        # ⚠️ 刻意不收宽泛的 `"范围" in c`:A.3 字段规格表 / B.2 出参说明表常见
        #    `| 字段 | 类型 | 单位 | 取值范围 | 说明 |`,「取值范围」会命中它 → 复合签名凑够 2 个
        #    → 普通字段表被当成口径表 → 直接 M2 缺 5 列 Critical(实测假红)。只认这两个正名。
        return "统计范围" in c or "范围口径" in c
    if concept == "取数粒度":
        return "粒度" in c or "取数粒度" in c or "聚合粒度" in c
    if concept == "权威取数口径":
        return "权威" in c or "取数口径" in c or "唯一信源" in c or "数据来源" in c
    return False


def col_index(cells: List[str], concept: str) -> Optional[int]:
    for idx, c in enumerate(cells):
        if cell_matches_column(c, concept):
            return idx
    return None


def is_metric_table_header(cells: List[str]) -> bool:
    """签名判定:含「指标/字段」列 + 至少 2 个五要素专有列 = 一张统计指标口径表。

    ⚠️ 只靠单列(如「单位」)会误认 A.3 字段表(那些表也有「单位」列),故要求复合签名;
       只要求"全 8 列命中"又会让**缺列的表**整张不被识别、M2 永远报不出来(缺列反而变成假绿),
       所以门槛设在"能认出它想当口径表"的最低复合度上,缺的列交给 M2 报。
    """
    if col_index(cells, "指标/字段") is None:
        return False
    hits = sum(1 for c in ("单位", "小数精度", "时间窗", "统计范围", "取数粒度")
               if col_index(cells, c) is not None)
    return hits >= 2


def strip_code_fences(lines: List[str]) -> List[bool]:
    """逐行标记「是否位于代码围栏内」(围栏行本身标 True)。"""
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


def scan_metric_tables(lines: List[str], in_code: List[bool], exempt: List[bool]) -> List[Dict]:
    """扫出全部统计指标口径表。**表头下一行必须是 GFM 分隔行**——否则散文里
    「旧版『指标 | 单位 | 精度』三列表已作废」这类**说明文字**会被当成一张缺列的表。"""
    tables, i, n = [], 0, len(lines)
    while i < n:
        if in_code[i] or exempt[i] or "|" not in lines[i]:
            i += 1
            continue
        cells = split_row(lines[i])
        if len(cells) < 2 or is_separator_row(cells) or not is_metric_table_header(cells):
            i += 1
            continue
        if i + 1 >= n or not is_separator_row(split_row(lines[i + 1])):
            i += 1
            continue
        rows, j = [], i + 2
        while j < n and "|" in lines[j] and not in_code[j]:
            r = split_row(lines[j])
            # ⚠️ 全空行既**不算分隔行**(见 is_separator_row 前置判)、也**不算数据行**:两个性质必须
            #    同时成立。只改前者会让 Word 转出的 `||||` 占位行变成数据行、每格报一条「为空」
            #    (真实 PRD 语料里有 35 处这种行)。
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


def has_metric_signal(lines: List[str], in_code: List[bool], exempt: List[bool]) -> List[Dict]:
    """数值展示信号:只认**标题行**,且跳过豁免章节与代码块。"""
    hits = []
    for i, ln in enumerate(lines):
        if in_code[i] or exempt[i]:
            continue
        m = re.match(r"^#{1,6}\s+(.*)$", ln)
        if not m:
            continue
        title = m.group(1)
        if METRIC_SIGNAL_RE.search(title) and not METRIC_SIGNAL_NEG_RE.search(title):
            hits.append({"line": i + 1, "title": title.strip()})
    return hits


def scan_file(path: Path, root: Path) -> Dict:
    rel = str(path.relative_to(root)) if root in path.parents or path == root else path.name
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        # ⚠️ 读不出来 ≠ 没有违规:记为 read_error 由 main() 判入参/环境错(退出码 2),
        #    绝不静默计为通过(那是最危险的假绿方向)。
        return {"file": rel, "read_error": str(exc), "tables": 0,
                "signals": [], "criticals": [], "declared_none": False,
                "metric_rows": []}

    lines = text.splitlines()
    in_code = strip_code_fences(lines)
    exempt = exempt_line_flags(lines, in_code)

    tables = scan_metric_tables(lines, in_code, exempt)
    signals = has_metric_signal(lines, in_code, exempt)
    declared_none = False
    for i, ln in enumerate(lines):
        if in_code[i] or exempt[i]:
            continue
        if NO_METRIC_DECLARE_RE.match(ln) and not DECLARE_GUARD_RE.search(ln):
            declared_none = True
            break
    criticals: List[Dict] = []
    metric_rows: List[Dict] = []   # 供 main() 做**跨表跨文件**的 M4 聚合

    for tb in tables:
        idx = {c: col_index(tb["header"], c) for c in REQUIRED_COLUMNS}
        missing = [c for c in REQUIRED_COLUMNS if idx[c] is None]
        if missing:
            criticals.append({"rule": "M2", "file": rel, "line": tb["header_line"],
                              "msg": "统计指标口径表缺列: " + " / ".join(missing)})
        # M3 逐格非空(只查识别到的列)
        for row in tb["rows"]:
            for c in REQUIRED_COLUMNS:
                if idx[c] is None:
                    continue
                val = _cell(row, idx[c])
                if _is_empty(val):
                    criticals.append({"rule": "M3", "file": rel, "line": row["line"],
                                      "msg": "「%s」列为空或占位/不可核对表述: %r" % (c, val[:40])})
        # M4 的数据只在这里**采集**,判定放到 main() 做跨表跨文件聚合(见下方 Why)
        ni, ai = idx["指标/字段"], idx["权威取数口径"]
        if ni is not None and ai is not None:
            for row in tb["rows"]:
                name = _norm(_cell(row, ni))
                if not name or _is_empty(name):
                    continue
                metric_rows.append({"key": name, "display": _cell(row, ni)[:30],
                                    "auth": _norm(_cell(row, ai)),
                                    "file": rel, "line": row["line"]})

    return {"file": rel, "tables": len(tables), "signals": signals,
            "criticals": criticals, "declared_none": declared_none,
            "metric_rows": metric_rows}


def render_text(results: List[Dict], criticals: List[Dict], skipped: bool, target: Path) -> None:
    # ⚠️ criticals 由 main() 传入(已含跨文件聚合的 M1/M4)。**勿改回在本函数里从
    #    results 重算**——那样人读输出会与退出码打架:退出码 1、屏幕上却打印「✅ 通过」。
    n_tables = sum(r["tables"] for r in results)
    print("统计指标口径表核验(检查项 34 / 约定39-R11+R12) — %s" % target)
    print("  扫描文件: %d   识别到口径表: %d 张" % (len(results), n_tables))
    if skipped:
        print("  ⏭️  跳过:未发现数值展示信号,且无口径表(exit 0,**不等于通过**——"
              "若本设计确有统计展示物而标题里没出现统计类词,请人工确认)")
        return
    if not criticals:
        print("  ✅ 通过:口径表 8 列齐全、逐格填实、同名指标权威口径一致")
        print("  ⚠️ 脚本只做结构性核验;时间窗/统计范围/取数粒度**写得对不对**须 QR 子 Agent 对照 PRD 判")
        return
    print("  ❌ Critical: %d" % len(criticals))
    for c in criticals:
        print("    [%s] %s:%s  %s" % (c["rule"], c["file"], c["line"], c["msg"]))


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="统计指标口径表结构性核验(检查项 34)")
    ap.add_argument("target", help="详细设计文档路径或目录")
    ap.add_argument("--json", action="store_true", help="输出 JSON 供 Agent 解析")
    args = ap.parse_args(argv)

    target = Path(args.target)
    # ⚠️ exists() 与 is_dir() 必须分开判:合并写成 `if not is_dir(): return 0` 会把
    #    "路径根本不存在"和"传入单个文件=合法"混为一谈,手滑写错路径等于整档静默放行。
    if not target.exists():
        print("[错误] 路径不存在: %s" % target, file=sys.stderr)
        return 2
    files = find_md_files(target)
    if not files:
        print("[错误] 未发现任何 .md 文件: %s" % target, file=sys.stderr)
        return 2

    root = target if target.is_dir() else target.parent
    results = [scan_file(f, root) for f in files]

    read_errors = [r for r in results if r.get("read_error")]
    if read_errors and len(read_errors) == len(results):
        for r in read_errors:
            print("[错误] 无法读取 %s: %s" % (r["file"], r["read_error"]), file=sys.stderr)
        return 2

    criticals = [c for r in results for c in r["criticals"]]
    n_tables = sum(r["tables"] for r in results)
    n_signals = sum(len(r["signals"]) for r in results)
    skipped = (n_tables == 0 and n_signals == 0)

    # ── M1 / M4 一律做**跨文件聚合**判定,勿改回 per-file(两个方向都实测翻过车)──
    # M1 per-file:本 SKILL 在 M/L 档**强制多册拆分**,口径表落在接口设计册,而带
    #   「统计/用量/趋势」字样的标题必然散落在详设册与库表册 → 合规多册设计**必假红**。
    # M4 per-table:同名指标一旦分散在两张表(多册下几乎必然),冲突完全不触发,
    #   而它要治的原始缺陷正是「总览页/商品管理页/用量监控页同一指标三者互不一致」→ **必假绿**。
    declared_none_any = any(r["declared_none"] for r in results)
    if n_signals and not n_tables and not declared_none_any:
        first = next(r for r in results if r["signals"])
        sig = first["signals"][0]
        criticals.append({"rule": "M1", "file": first["file"], "line": sig["line"],
                          "msg": "本次扫描范围内存在数值展示信号(标题「%s」)却找不到任何"
                                 "「统计指标口径表」" % sig["title"][:40]})
    seen: Dict[str, Dict] = {}
    for r in results:
        for row in r.get("metric_rows", []):
            prev = seen.get(row["key"])
            if prev is None:
                seen[row["key"]] = row
            elif prev["auth"] != row["auth"]:
                criticals.append({
                    "rule": "M4", "file": row["file"], "line": row["line"],
                    "msg": "指标「%s」的「权威取数口径」不一致:%s:%d 与 %s:%d "
                           "(约定39-R12:同一指标跨页面必须同源)"
                           % (row["display"], prev["file"], prev["line"],
                              row["file"], row["line"])})

    if args.json:
        print(json.dumps({
            "target": str(target),
            "passed": not criticals,
            "skipped": skipped,
            "scanned_files": len(files),
            "metric_tables": n_tables,
            "metric_signals": n_signals,
            "declared_none": any(r["declared_none"] for r in results),
            "read_errors": [{"file": r["file"], "error": r["read_error"]} for r in read_errors],
            "criticals": criticals,
        }, ensure_ascii=False, indent=2))
    else:
        render_text(results, criticals, skipped, target)
        for r in read_errors:
            print("  ⚠️ 未能读取(未参与检查,不等于干净): %s — %s" % (r["file"], r["read_error"]))

    return 1 if criticals else 0


if __name__ == "__main__":
    sys.exit(main())
