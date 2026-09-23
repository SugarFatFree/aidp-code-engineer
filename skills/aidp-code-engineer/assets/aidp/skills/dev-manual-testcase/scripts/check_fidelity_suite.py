#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""「通用还原度覆盖表」硬核回检 — dev-manual-testcase 维度 21(Critical)

落地上下游共用的通用规则集(AIDP 约定 39)在用例侧的部分。
⚠️ 编号消歧:**本 SKILL 的 `R1~R12` 已被反向覆盖矩阵占用**(见 check_case_stats.py 的
   REVERSE_DIMS,`R12` = 依赖/数据源故障注入)。通用规则一律写全称 `约定39-RNN`,
   本脚本的输出与文档也照此,勿写裸 `RNN`。

背景(下游实测):71 条已关闭缺陷里 96%(68/71)属「正常发现」——走一遍正常流程就会碰到,
却全部漏到 QA 侧。**问题不是测得不够狠,是测得太晚。** 这批缺陷与业务领域无关,
可由**固定模板用例**覆盖,生成时只需知道页面类型(列表页/详情页/表单页/含数字的页),
不需要理解业务。本脚本核验那批模板用例有没有真的生成出来。

检查项:
【Critical(退出码 1)】
  F1 缺覆盖表      —— 文档里有用例,却找不到「通用还原度覆盖表」
  F2 覆盖表缺列    —— 4 列固定契约:页面 | 页面类型 | 还原度用例数 | 用例编号
  F3 列表页不足    —— 任一「列表页」行的还原度用例 < 10(上游给出的明确验收基线;标 na 的条目照常计数)
  F4 编号是空头支票 —— 表里声明的用例编号在文档里找不到同编号且标 `[还原度]` 的用例

【Important(仅告警,不影响退出码)】
  W1 详情页 < 4 / 表单页 < 2 / 含数字的页 < 6(按模板条目数派生的基线,不当硬门)
  W2 页面类型不在四类枚举内(列表页/详情页/表单页/含数字的页)
  W3 「还原度用例数」与「用例编号」解析出的条数不一致
  W5 标记「不适用」但标题缺少非空理由,或理由缺少需求/设计/裁剪决策追溯线索

⚠️ 本脚本只做**结构性核验**。「那 10 条模板项是不是都真写了」属语义层,由 QR 子 Agent
   对照 `references/flow-fidelity-suite.md` 第三节模板表逐页核对——**脚本全绿 ≠ 维度 21 通过**。

用法:
    python3 check_fidelity_suite.py <用例目录或文件> [--json]

退出码:
    0 = 通过,或跳过(文档显式声明「本轮无 UI 页面用例」/ 目录里根本没有用例)
    1 = 检出违规(严重度分档读 --json,不占用退出码)
    2 = 入参或环境错(路径不存在、目录下没有 .md、文件全部不可读)

仅依赖 Python 3.8+ 标准库。
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

FIDELITY_TAG = "[还原度]"

# 覆盖表 4 列固定契约(与 references/flow-fidelity-suite.md 第四节严格一致)
REQUIRED_COLUMNS = ["页面", "页面类型", "还原度用例数", "用例编号"]

# 页面类型枚举 → (基线条数, 是否 Critical)
PAGE_TYPE_BASELINE = {
    "列表页": (10, True),      # ★上游给出的明确验收基线,唯一 Critical 档
    "详情页": (4, False),
    "表单页": (2, False),
    "含数字的页": (6, False),   # ⚠️ 由 5 条增至 6 条(新增「两位点数值自洽」)
}

# 用例存在信号:有用例才要求有覆盖表(纯方案文档 / 索引文档 / 规范文档不判)。
# ⚠️ **只认结构性信号**(用例标题行 / 套件标题行),**不认散文里提到的 TC-ID**——
#    规范类文档正文常写「拆成 `TC-LOGIN-001 登录成功` + `TC-LOGIN-002 密码错误`」这类举例,
#    按子串扫会把规范文档当成用例文档、判它缺覆盖表(实测假红:flow-output-format.md)。
CASE_SIGNAL_RE = re.compile(
    r"^#{2,6}\s*(?:用例\s*)?TC-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*"
    r"|^#{2,6}\s*(?:测试)?套件\s*SUITE-")
# 用例编号形态(与本 SKILL 既有编号规范一致:TC-<模块>-<序号>)
CASE_ID_RE = re.compile(r"\bTC-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*\b")
# 连号区间 TC-XX-F01~F10 / TC-XX-F01-F10
RANGE_RE = re.compile(r"\b(TC-[A-Za-z0-9-]*?)([A-Za-z]*)(\d+)\s*[~～—–-]\s*(?:TC-[A-Za-z0-9-]*?)?([A-Za-z]*)(\d+)\b")
# 用例标题行(与 check_testcase_format.py 的 TESTCASE_HEADER 同宽),用于把 `[还原度]` 归属到用例块
CASE_HEADING_RE = re.compile(r"^#{3,6}\s*(?:用例\s*)?(TC-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)")
# 模板占位单元格(`{模块}` / `{页面名}` / `<页面名>`)
PLACEHOLDER_CELL_RE = re.compile(r"\{[^{}]*\}|<[^<>]+>")
# 不适用用例标题必须是统一后缀「（不适用：理由）」,理由还要带需求/设计/处置追溯线索。
NA_SUFFIX_RE = re.compile(r"[（(]\s*不适用\s*[：:]\s*([^）)]*?)\s*[）)]")
NA_TRACE_RE = re.compile(r"REQ[-_]?\d+|PRD|Q[-_]?\d+|D[-_]?\d+|需求|设计|原型|产品|裁剪|延期|处置|确认")

# 显式跳过声明。⚠️ 必须是**独立成句的声明行** + 否定护栏,且跳过代码围栏。
# 实测教训(与 check_metric_spec.py 的 NO_METRIC_DECLARE_RE 同源):模板/规范里必然要写下
# 「本轮确实没有 UI 页面用例时,写明『本轮无 UI 页面用例』+ 原因」这类**指引**,
# 无差别的 `search(text)` 会把整档检查关掉 —— 照模板产出的文档全部静默 skipped、假绿。
# 允许后面接原因(「本轮无 UI 页面用例,仅做接口连通性核验」是合规写法),但必须**行首起句**——
# 指引句「本轮确实没有 UI 页面用例时,写明『本轮无 UI 页面用例』+ 原因」不以该短语起句,且被下面的护栏拦住。
NO_UI_DECLARE_RE = re.compile(
    r"^\s*[>*\-\s]*\**\s*(?:本轮|本次|本版)?\s*无\s*UI\s*(?:页面)?用例\**\s*(?:[,，:：。.].*)?$")
# 命中即视为"这一行是引用/指引、不是声明"
DECLARE_GUARD_RE = re.compile(r"须|应|时[,，]|不得|禁止|例如|如[:：]|见|参见|模板|判据|硬门|写明")

TABLE_HEADING_RE = re.compile(r"通用还原度覆盖表|还原度覆盖表")


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
    s = re.sub(r"[*`>\s]", "", s)
    return s.replace("（", "(").replace("）", ")")


def cell_matches_column(cell: str, concept: str) -> bool:
    c = _norm(cell)
    if concept == "页面":
        return c == "页面" or "页面名" in c
    if concept == "页面类型":
        # ⚠️ 刻意不认裸「类型」:PRD 功规点覆盖矩阵常见 `| 功规点 | 类型 | 用例编号 | 优先级 |`,
        #    「类型」+「用例编号」两列会让 is_coverage_header 把它误认成还原度覆盖表,
        #    随即 F2(缺列)+ 逐行 F4 全部触发(实测假红)。只认正名。
        return "页面类型" in c
    if concept == "还原度用例数":
        return "用例数" in c or "条数" in c
    if concept == "用例编号":
        return "用例编号" in c or "编号" == c or "用例ID" in c.replace("Id", "ID")
    return False


def col_index(cells: List[str], concept: str) -> Optional[int]:
    for idx, c in enumerate(cells):
        if cell_matches_column(c, concept):
            return idx
    return None


def is_coverage_header(cells: List[str]) -> bool:
    """签名判定:同时含「页面类型」与「用例编号」两列 = 还原度覆盖表。

    ⚠️ 不靠标题识别:标题写法会漂(「通用还原度覆盖表」/「还原度覆盖」/带序号前缀),
       靠列签名更稳;而「页面类型 + 用例编号」这对组合在本 SKILL 其它表里不出现,不会误认。
    """
    return col_index(cells, "页面类型") is not None and col_index(cells, "用例编号") is not None


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


def parse_case_ids(cell: str) -> List[str]:
    """解析用例编号格:支持逗号/顿号/空格分隔的列表 + 同前缀连号区间 TC-XX-F01~F10。"""
    ids: List[str] = []
    text = cell.replace("`", "")
    for m in RANGE_RE.finditer(text):
        prefix, a_alpha, a_num, b_alpha, b_num = m.groups()
        if a_alpha != b_alpha:      # 区间两端字母段不同 → 不当区间处理,退回逐个匹配
            continue
        width = len(a_num)
        try:
            lo, hi = int(a_num), int(b_num)
        except ValueError:
            continue
        if hi < lo or hi - lo > 500:  # 反常区间不展开,避免笔误炸内存
            continue
        for n in range(lo, hi + 1):
            ids.append("%s%s%0*d" % (prefix, a_alpha, width, n))
        text = text.replace(m.group(0), " ")
    for m in CASE_ID_RE.finditer(text):
        if m.group(0) not in ids:
            ids.append(m.group(0))
    return ids


def scan_docs(files: List[Path], root: Path) -> Tuple[Dict, List[Dict]]:
    """一次性读全部文档,返回 (全局事实, 读失败清单)。"""
    facts = {
        "has_case_signal": False,
        "declared_no_ui": False,
        "coverage_rows": [],      # {file,line,page,ptype,count_cell,ids_cell}
        "coverage_tables": 0,
        "coverage_missing_cols": [],   # {file,line,missing[]}
        "fidelity_case_ids": set(),    # 文档里真实存在的、标了 [还原度] 的用例编号
        "fidelity_tag_lines": 0,
        "na_fidelity_cases": [],       # 标了不适用的 [还原度] 用例,供 W5 核对理由与追溯
    }
    read_errors = []
    for f in files:
        rel = str(f.relative_to(root)) if f != root else f.name
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            # ⚠️ 读不出来 ≠ 没问题:记下来,不静默当通过
            read_errors.append({"file": rel, "error": str(exc)})
            continue
        lines = text.splitlines()
        in_code = strip_code_fences(lines)

        for i, ln in enumerate(lines):
            if in_code[i]:
                continue
            if NO_UI_DECLARE_RE.match(ln) and not DECLARE_GUARD_RE.search(ln):
                facts["declared_no_ui"] = True
                break

        # ⚠️ `[还原度]` **按用例块归属**认定,不要求与 TC-ID 同一行。
        #    分片明写「每条用例都标 `[还原度]`(元信息「类型」字段 + 标题标注)」,
        #    按"标在元信息类型字段"这一读法产出的用例,若只认同行会被 F4 整族判死(实测假红);
        #    姊妹脚本 check_case_stats.py 也是 type + title 两处都认,口径须一致。
        current_case: Optional[str] = None
        current_case_line = 0
        current_case_title = ""
        current_case_lines: List[str] = []

        def finish_case() -> None:
            if not current_case or FIDELITY_TAG not in "\n".join(current_case_lines):
                return
            block = "\n".join(current_case_lines)
            if "不适用" in block:
                suffix = NA_SUFFIX_RE.search(current_case_title)
                reason = suffix.group(1).strip() if suffix else ""
                if not suffix or not reason or not NA_TRACE_RE.search(reason):
                    facts["na_fidelity_cases"].append({
                        "case_id": current_case,
                        "file": rel,
                        "line": current_case_line,
                        "title": current_case_title,
                        "reason": reason,
                    })

        for i, ln in enumerate(lines):
            if in_code[i]:
                continue
            if not facts["has_case_signal"] and CASE_SIGNAL_RE.match(ln):
                facts["has_case_signal"] = True
            m = CASE_HEADING_RE.match(ln)
            if m:
                finish_case()
                current_case = m.group(1)
                current_case_line = i + 1
                current_case_title = ln
                current_case_lines = [ln]
            elif current_case:
                current_case_lines.append(ln)
            if FIDELITY_TAG in ln:
                facts["fidelity_tag_lines"] += 1
                hit = CASE_ID_RE.findall(ln)
                if hit:
                    facts["fidelity_case_ids"].update(hit)
                elif current_case:
                    facts["fidelity_case_ids"].add(current_case)
        finish_case()

        i, n = 0, len(lines)
        while i < n:
            if in_code[i] or "|" not in lines[i]:
                i += 1
                continue
            cells = split_row(lines[i])
            if len(cells) < 2 or is_separator_row(cells) or not is_coverage_header(cells):
                i += 1
                continue
            if i + 1 >= n or not is_separator_row(split_row(lines[i + 1])):
                # GFM 表头必须紧跟分隔行,否则散文里提到列名会被当成一张表
                i += 1
                continue
            facts["coverage_tables"] += 1
            idx = {c: col_index(cells, c) for c in REQUIRED_COLUMNS}
            missing = [c for c in REQUIRED_COLUMNS if idx[c] is None]
            if missing:
                facts["coverage_missing_cols"].append(
                    {"file": rel, "line": i + 1, "missing": missing})
            j = i + 2
            while j < n and "|" in lines[j] and not in_code[j]:
                r = split_row(lines[j])
                # ⚠️ 全空行既**不算分隔行**(见 is_separator_row 前置判)、也**不算数据行**:两个性质必须
                #    同时成立。只改前者会让 Word 转出的 `||||` 占位行变成数据行、每格报一条「为空」
                #    (真实 PRD 语料里有 35 处这种行)。
                if is_separator_row(r) or all(c.strip() == "" for c in r):
                    j += 1
                    continue

                def cell(concept):
                    k = idx.get(concept)
                    return r[k] if k is not None and k < len(r) else ""

                facts["coverage_rows"].append({
                    "file": rel, "line": j + 1,
                    "page": cell("页面"), "ptype": _norm(cell("页面类型")),
                    "count_cell": cell("还原度用例数"), "ids_cell": cell("用例编号"),
                })
                j += 1
            i = j
    return facts, read_errors


def evaluate(facts: Dict) -> Tuple[List[Dict], List[Dict], bool]:
    criticals: List[Dict] = []
    warns: List[Dict] = []

    # 已解析到覆盖表本身就是"这是一份用例文档"的信号——多文件模式下总览文件可能只有表、
    # 用例散在子文件里,若只认用例标题会让「表在、用例一个都没有」这种空头支票整档跳过。
    has_signal = facts["has_case_signal"] or facts["coverage_tables"] > 0
    skipped = facts["declared_no_ui"] or not has_signal
    if skipped:
        return criticals, warns, True

    if facts["coverage_tables"] == 0:
        criticals.append({"rule": "F1", "file": "-", "line": 0,
                          "msg": "文档里有用例,却找不到「通用还原度覆盖表」"
                                 "(4 列:页面|页面类型|还原度用例数|用例编号)"})
        return criticals, warns, False

    for na in facts["na_fidelity_cases"]:
        warns.append({
            "rule": "W5", "file": na["file"], "line": na["line"],
            "msg": "用例 %s 标记「不适用」但标题必须使用「（不适用：一句话理由）」且理由需含"
                   "需求/设计/裁剪决策追溯线索(如 Q-102、D-204、产品未要求、详见设计);"
                   "不得用 na 逃避模板项" % na["case_id"]
        })

    for mc in facts["coverage_missing_cols"]:
        criticals.append({"rule": "F2", "file": mc["file"], "line": mc["line"],
                          "msg": "还原度覆盖表缺列: " + " / ".join(mc["missing"])})

    for row in facts["coverage_rows"]:
        ptype = row["ptype"]
        ids = parse_case_ids(row["ids_cell"])
        declared = len(ids)
        m = re.search(r"\d+", row["count_cell"] or "")
        stated = int(m.group(0)) if m else None
        # ⚠️ **不回落 stated**:早期写成 `actual = declared or stated`,只要「用例编号」列写成
        #    散文(「见下方套件 SUITE-01」)或留空,F3 就用作者自己填的数字过关、F4 无编号可回查、
        #    W3 也因 declared 为假而不报 —— 整行零告警,而实际 [还原度] 用例是 0 条。
        #    这恰好把「防空头支票」的 F4 从后门放掉,故改为只认真实解析出的编号。
        actual = declared
        # 模板占位行(`TC-{模块}-F01~F10` / `{页面名}`)——**本 SKILL 自带的三份 assets 模板与
        # flow-output-format 的章节结构必然长这样**。判 Critical 会让「照模板产出」这件事本身
        # 变成违规(自家模板被自家硬门判死,本仓库反复踩过);判 0 告警又会让"忘了填"静默通过。
        # 折中:降为 W4 Important 并跳过本行的 F3/F4/F5,QR 流程要求子 Agent 读 warns,看得见。
        if PLACEHOLDER_CELL_RE.search(row["ids_cell"] or "") or PLACEHOLDER_CELL_RE.search(row["page"] or ""):
            warns.append({"rule": "W4", "file": row["file"], "line": row["line"],
                          "msg": "本行仍是**模板占位**(%r)——落盘前必须替换为真实页面名与用例编号,"
                                 "或整行删除;占位行不参与 F3/F4/F5 判定"
                                 % ((row["ids_cell"] or row["page"] or "")[:30])})
            continue
        if not ids:
            criticals.append({"rule": "F5", "file": row["file"], "line": row["line"],
                              "msg": "页面「%s」的「用例编号」列解析不出任何用例编号(为空或非编号文本: %r)"
                                     "——无法回查,视同空头支票"
                                     % (row["page"] or "?", (row["ids_cell"] or "")[:30])})

        if ptype not in PAGE_TYPE_BASELINE:
            warns.append({"rule": "W2", "file": row["file"], "line": row["line"],
                          "msg": "页面类型「%s」不在四类枚举内(列表页/详情页/表单页/含数字的页);"
                                 "一页多类请拆成多行" % (row["ptype"] or "(空)")})
        else:
            baseline, is_critical = PAGE_TYPE_BASELINE[ptype]
            if actual < baseline:
                item = {"file": row["file"], "line": row["line"],
                        "msg": "页面「%s」(%s)还原度用例 %d 条 < 基线 %d 条"
                               % (row["page"] or "?", ptype, actual, baseline)}
                if is_critical:
                    item["rule"] = "F3"
                    criticals.append(item)
                else:
                    item["rule"] = "W1"
                    warns.append(item)

        if stated is not None and declared and stated != declared:
            warns.append({"rule": "W3", "file": row["file"], "line": row["line"],
                          "msg": "页面「%s」声明 %d 条,但「用例编号」列解析出 %d 个编号"
                                 % (row["page"] or "?", stated, declared)})

        missing_ids = [cid for cid in ids if cid not in facts["fidelity_case_ids"]]
        if missing_ids:
            criticals.append({"rule": "F4", "file": row["file"], "line": row["line"],
                              "msg": "页面「%s」声明的编号在文档里找不到同编号且标 `%s` 的用例: %s"
                                     % (row["page"] or "?", FIDELITY_TAG,
                                        ", ".join(missing_ids[:8])
                                        + (" …" if len(missing_ids) > 8 else ""))})
    return criticals, warns, False


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="通用还原度覆盖表结构性核验(维度 21)")
    ap.add_argument("target", help="用例目录或文件")
    ap.add_argument("--json", action="store_true", help="输出 JSON 供 Agent 解析")
    args = ap.parse_args(argv)

    target = Path(args.target)
    # ⚠️ exists() 与 is_dir() 分开判:合并写会把"路径写错"混成"合法的 N/A 跳过",等于静默放行
    if not target.exists():
        print("[错误] 路径不存在: %s" % target, file=sys.stderr)
        return 2
    files = find_md_files(target)
    if not files:
        print("[错误] 未发现任何 .md 文件: %s" % target, file=sys.stderr)
        return 2

    root = target if target.is_dir() else target.parent
    facts, read_errors = scan_docs(files, root)
    if read_errors and len(read_errors) == len(files):
        for r in read_errors:
            print("[错误] 无法读取 %s: %s" % (r["file"], r["error"]), file=sys.stderr)
        return 2

    criticals, warns, skipped = evaluate(facts)

    if args.json:
        print(json.dumps({
            "target": str(target),
            "passed": not criticals,
            "skipped": skipped,
            # ⚠️ 跳过时 passed 仍为 true(无 criticals),**但跳过 ≠ 通过**。只读 passed 会判绿,
            #    故显式给一条 note;QR 流程要求同时读 skipped。
            "note": ("skipped ≠ passed:整档未跑,须在报告里如实标「跳过(原因)」"
                     if skipped else ""),
            "scanned_files": len(files),
            "coverage_tables": facts["coverage_tables"],
            "coverage_rows": len(facts["coverage_rows"]),
            "fidelity_cases_found": len(facts["fidelity_case_ids"]),
            "na_reason_issues": len(facts["na_fidelity_cases"]),
            "declared_no_ui": facts["declared_no_ui"],
            "read_errors": read_errors,
            "criticals": criticals,
            "warns": warns,
        }, ensure_ascii=False, indent=2))
        return 1 if criticals else 0

    print("通用还原度覆盖表核验(维度 21) — %s" % target)
    print("  扫描文件: %d   覆盖表: %d 张 / %d 行   文档内 [还原度] 用例: %d 条"
          % (len(files), facts["coverage_tables"], len(facts["coverage_rows"]),
             len(facts["fidelity_case_ids"])))
    if skipped:
        why = "文档显式声明「本轮无 UI 页面用例」" if facts["declared_no_ui"] else "未发现任何用例信号"
        print("  ⏭️  跳过(%s) — exit 0,**不等于通过**" % why)
        return 0
    if criticals:
        print("  ❌ Critical: %d" % len(criticals))
        for c in criticals:
            print("    [%s] %s:%s  %s" % (c["rule"], c["file"], c["line"], c["msg"]))
    else:
        print("  ✅ 结构性检查通过(覆盖表齐全、列表页 ≥10、编号逐个回查命中)")
    if warns:
        print("  🟡 Important(不影响退出码): %d" % len(warns))
        for w in warns:
            print("    [%s] %s:%s  %s" % (w["rule"], w["file"], w["line"], w["msg"]))
    for r in read_errors:
        print("  ⚠️ 未能读取(未参与检查,不等于干净): %s — %s" % (r["file"], r["error"]))
    print("  ⚠️ 「10 条模板项是不是都真写了」属语义层,须 QR 子 Agent 对照 flow-fidelity-suite.md 第三节逐页核")
    return 1 if criticals else 0


if __name__ == "__main__":
    sys.exit(main())
