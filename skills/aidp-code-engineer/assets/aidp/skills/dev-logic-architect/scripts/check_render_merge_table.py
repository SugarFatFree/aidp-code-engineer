#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""「渲染层归并声明表」硬核回检 — dev-logic-architect 检查项 37(Critical,对应核心原则 29)

把「**上游集合 → 页面条目**」这一层转换固定在设计期。下游实测该类单类发作 3 次、是那一轮
最高频的根因,两例都**不报错、静态检查全绿、只有人眼在页面上才能发现**:

  ① 去重「功能没生效」—— 去重判据取的是「订单台账」,而页面展示集合是
     「台账 ∪ 平台预约单」,**预约单那一整类从未进入去重**。
  ② 4 人订阅显示 4,页面只有 1 张卡 —— 头部统计数取「上游订阅记录数」,
     而页面按 skuId 归并成卡片,**统计数与页面条目不是同一个集合**。

⚠️ **与检查项 34「统计指标口径表」不同层,⛔ 勿合并**:34 第 8 列管「同一指标别在 N 处各算一遍」,
   而上面两例里**取数口径本身完全正确**——错的是判据与渲染表达式挂在不同的集合上。

检查项:
【Critical(退出码 1)】
  R1 列不齐 / 数据行格数不符 —— 5 列固定契约
  R2 逐格空或占位          —— `待定` / `TBD` / `—` / `{...}` / `同上`(与 check_count_claim_table.py 同款)
  R3 第 4 列非二选一        —— 只能填「是」/「否」;填「视情况」= 这一层根本没想清楚
  R4 多来源未逐字点名      —— 「数据来源」写成 `A ∪ B` 时,第 5 列必须**逐字点名它覆盖的每一个来源**
                              (失效①的形态)。★ 为什么是「逐字点名」而不是别的:来源是中文业务名、
                              表达式是代码标识符,两者天然对不上,**只有要求作者把覆盖面写出来才可判**
  R5 归并后仍引上游记录数  —— 第 4 列填「否」时,第 5 列出现 `total` / `totalCount` / `count(*)` /
                              `记录数` 这类**无歧义的上游侧计数**(失效②的形态)
  R6 第 3 列「无」与第 4 列「否」自相矛盾 —— 既不归并也不过滤,记录数不可能 ≠ 条目数

【Important(仅告警,不影响退出码)】
  W1 第 4 列「否」+ 第 5 列用 `.length` / `.size()`,而标识符**没有归并痕迹**
     (`merged` / `grouped` / `cards` / `dedup` / `distinct` / `unique` / `归并` / `去重`)。
     ⚠️ 刻意判 Important 不判 Critical:`mergedCards.length` 是**完全正确**的写法,
     `.length` 本身不区分上游还是归并后——把它一律判死会让本硬门在合规设计上假红常驻,
     而假红常驻 = 硬门被绕过(本仓库既有教训)。R5 只收无歧义的那几个 token。
  W2 第 3 列有归并键 / 过滤条件,第 4 列却填「是」 —— 可能成立(1:1 的归并)但值得复核

⚠️ **本脚本刻意不做「缺表判定」**——「列表」「卡片」这类词在设计正文里几乎必然出现,
   扫正文必满屏假红(与 `check_count_claim_table.py`、`check_metric_spec.py` 同一条纪律)。
   故 `skipped=true` **只说明没找到表、不等于通过**,表该不该有由 QR 子 Agent 按检查项 37 判。

用法:
    python3 check_render_merge_table.py <设计文档目录或文件> [--json]

退出码:
    0 = 通过,或 N/A 跳过(未找到「渲染层归并声明表」)
    1 = 检出违规(严重度分档读 --json,不占用退出码)
    2 = 入参或环境错(路径不存在、目录下没有 .md、文件全部不可读)

仅依赖 Python 3.8+ 标准库。
⚠️ 本 SKILL 内脚本**互不 import**(SKILL 独立性原则)。`split_row` / `is_separator_row` / `_norm` /
   `strip_code_fences` 与 `check_count_claim_table.py` 同款,属刻意重复,改一处须两处同改。
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REQUIRED_COLUMNS = ["列表位点", "数据来源", "渲染层是否归并/过滤",
                    "上游记录数 == 页面条目数?", "该位点的计数与判据表达式"]
# 「专名列」:这三个概念在本 SKILL 其它任何表的表头里都不出现
SIGNATURE_COLUMNS = ("列表位点", "渲染层是否归并/过滤", "上游记录数 == 页面条目数?")

PLACEHOLDER_CELL_RE = re.compile(
    r"^(?:[-—–]+|/|N/?A|TBD|待定|待补|待填|同上|视情况|按业务|\{[^{}]*\}|<[^<>]*>)$", re.I)
# 多来源分隔符。⚠️ 刻意**不认**中文顿号「、」——业务名里本就常带顿号式罗列
# (「台账、预约单」与「台账 ∪ 预约单」意思一样,但顿号也可能只是一个名字里的标点),
# 只认这几个**明确表示集合并**的符号,宁可漏判也不误判。
MULTI_SOURCE_SEP = re.compile(r"[∪⋃+＋]|\bUNION\b|\bunion\b")
YES_NO = {"是", "否"}
# 无歧义的上游侧计数 token(R5)。⚠️ `.length` / `.size()` **刻意不在这里**,见 W1 注释。
UPSTREAM_COUNT_RE = re.compile(
    r"\btotalCount\b|\btotal_count\b|\btotal\b|count\s*\(\s*\*\s*\)|记录数|\browCount\b|\btotalElements\b")
MERGE_HINT_RE = re.compile(
    r"merged|grouped|group|cards|card|dedup|distinct|unique|归并|去重|聚合|合并")
LEN_CALL_RE = re.compile(r"([A-Za-z_$][\w$]*)\s*\.\s*(?:length\b|size\s*\(\s*\))")
NO_MERGE_RE = re.compile(r"^(?:无|none|—|-)$", re.I)
# 禁令语境护栏(R5 专用)。⚠️ **实测第一次就会踩到**:本 SKILL 自己的模板示例里写着
#    「复用归并后的 mergedCards.length,⛔ **不用**上游订阅记录数」——这是**合规写法**,
#    却因为句子里出现「记录数」被 R5 判死。设计文档必然要写出反模式本身才能禁止它,
#    与 `check_error_contract.py` 的 C6/C7 护栏是同一条经验。
#    处置:**只剥掉禁令那一小段**(从禁令词到下一个分句边界),⛔ 不整格跳过——
#    整格跳过会让「一边写 ⛔ 一边真在用」的行蒙混过关。
# ⚠️⚠️ **`非` 曾在这个词表里,已删除,⛔ 不要加回来**:
#    `非` 是单字、且是「非空 / 非法 / 非试用 / 除非」等词的构词成分,它一进词表,
#    `统计非试用企业的订阅记录数` 整段被当禁令剥掉 → **R5 静默漏判、exit 0**;
#    而把「非」去掉的同一句 `统计试用企业的订阅记录数` 立刻判 R5 Critical
#    —— 同一个违规,只因多了一个字就消失,这正是本硬门最不该有的失效方向(假绿)。
#    留在表里的都是**多字、且几乎只作禁令用**的词。
PROHIBITION_SPAN_RE = re.compile(r"(?:⛔|严禁|禁止|不得|不用|不能|不再|勿用)[^;；,，。\n]*")


def find_md_files(path: Path) -> List[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(path.rglob("*.md"))
    return []


def split_row(line: str) -> List[str]:
    r"""按未转义的 `|` 切列(表达式列里可能出现 `A \| B` 这种写法)。"""
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
    if concept == "列表位点":
        return "列表位点" in c or "位点" in c
    if concept == "数据来源":
        return "数据来源" in c or c == "来源"
    if concept == "渲染层是否归并/过滤":
        return "归并" in c and ("过滤" in c or "渲染" in c or "是否" in c)
    if concept == "上游记录数 == 页面条目数?":
        return "上游记录数" in c and "页面条目数" in c
    if concept == "该位点的计数与判据表达式":
        return "判据表达式" in c or ("计数" in c and "表达式" in c)
    return False


def col_index(cells: List[str], concept: str) -> Optional[int]:
    for idx, c in enumerate(cells):
        if cell_matches_column(c, concept):
            return idx
    return None


def is_table_header(cells: List[str]) -> bool:
    """签名判定:命中任一专名列 + 至少 3 个契约列。

    ⚠️ **不要改回「两个指定列同时在」的写法**:那样一来,恰恰是把其中一列删掉的表会整张
       认不出来 —— 表被跳过 → 数据行一行不解析 → R1~R6 全部够不着,只剩一个「没找到表」的
       skipped,而删掉一列本该是 R1 Critical。姊妹 SKILL 的
       `check_residual_assertions.py` 实测踩过这个洞(严重度完全反了),此处直接按修好的形态写。
    """
    if not any(col_index(cells, c) is not None for c in SIGNATURE_COLUMNS):
        return False
    return sum(1 for c in REQUIRED_COLUMNS if col_index(cells, c) is not None) >= 3


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


def split_sources(cell: str) -> List[str]:
    """把「A ∪ B」拆成来源名列表;单来源返回单元素。"""
    raw = re.sub(r"[`*]", "", cell)
    parts = [p.strip(" 　「」()（）") for p in MULTI_SOURCE_SEP.split(raw)]
    return [p for p in parts if p]


def check_file(path: Path) -> Tuple[List[dict], int]:
    """返回 (问题列表, 见到的表张数)。"""
    issues: List[dict] = []
    tables = 0
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        # ⚠️ 读失败绝不可静默计为通过(全仓退出码约定第 3 条)。
        issues.append({"level": "Important", "code": "read_error", "file": str(path),
                       "line": 0, "msg": "文件读不出来(%s),已跳过——⛔ 不得据此判该文件无违规" % e})
        return issues, 0

    lines = text.split("\n")
    in_fence = strip_code_fences(lines)
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
                        issues.append({"level": "Critical", "code": "R1", "file": str(path),
                                       "line": i + 1,
                                       "msg": "缺列「%s」(5 列固定契约:%s)"
                                              % (concept, " | ".join(REQUIRED_COLUMNS))})
                    else:
                        hidx[concept] = j
            continue

        if len(cells) != len(header):
            issues.append({"level": "Critical", "code": "R1", "file": str(path), "line": i + 1,
                           "msg": "数据行 %d 格、表头 %d 格——若表达式里写了 `|`,须转义为 `\\|`"
                                  "(GFM 里 `|` 是列分隔符,反引号保护不了它)"
                                  % (len(cells), len(header))})
            continue

        row = {c: cells[j] for c, j in hidx.items() if j < len(cells)}

        # R2 逐格空或占位
        for concept, v in row.items():
            if v.strip() == "" or PLACEHOLDER_CELL_RE.match(_norm(v)):
                issues.append({"level": "Critical", "code": "R2", "file": str(path), "line": i + 1,
                               "msg": "「%s」格空或只有占位(`%s`)——不可核对等于没写" % (concept, v)})

        equal = _norm(row.get("上游记录数 == 页面条目数?", ""))
        merge = row.get("渲染层是否归并/过滤", "")
        expr = row.get("该位点的计数与判据表达式", "")
        src = row.get("数据来源", "")

        # R3 第 4 列二选一
        if equal and not PLACEHOLDER_CELL_RE.match(equal) and equal not in YES_NO:
            issues.append({"level": "Critical", "code": "R3", "file": str(path), "line": i + 1,
                           "msg": "「上游记录数 == 页面条目数?」填的是「%s」,只能填「是」/「否」"
                                  "——填别的等于这一层还没想清楚" % row.get("上游记录数 == 页面条目数?")})

        # R4 多来源逐字点名
        sources = split_sources(src)
        if len(sources) > 1 and expr:
            missing = [s for s in sources if _norm(s) and _norm(s) not in _norm(expr)]
            if missing:
                issues.append({"level": "Critical", "code": "R4", "file": str(path), "line": i + 1,
                               "msg": "「数据来源」是多来源(%s),但判据表达式没有逐字点名:%s"
                                      "——判据只覆盖其中一个子集,正是「那一整类从未进入去重」的形态"
                                      % (" ∪ ".join(sources), " / ".join(missing))})

        # R5 / W1 归并后仍引上游记录数
        if equal == "否" and expr:
            expr_pos = PROHIBITION_SPAN_RE.sub("", expr)   # 剥掉禁令小段再判,见 PROHIBITION_SPAN_RE 注释
            if UPSTREAM_COUNT_RE.search(expr_pos):
                issues.append({"level": "Critical", "code": "R5", "file": str(path), "line": i + 1,
                               "msg": "第 4 列已声明「否」(上游记录数 ≠ 页面条目数),判据表达式却仍在用"
                                      "上游侧计数(`%s`)——这正是「4 人订阅显示 4、页面只有 1 张卡」的形态"
                                      % expr})
            else:
                for m in LEN_CALL_RE.finditer(expr_pos):
                    if not MERGE_HINT_RE.search(m.group(1)):
                        issues.append({"level": "Important", "code": "W1", "file": str(path),
                                       "line": i + 1,
                                       "msg": "第 4 列为「否」,而 `%s` 的名字看不出是归并后的集合"
                                              "——请确认它不是上游集合(`mergedCards.length` 这类是合规的)"
                                              % m.group(0)})
                        break

        # R6 / W2 第 3 列与第 4 列一致性
        if merge and equal:
            no_merge = bool(NO_MERGE_RE.match(_norm(merge)))
            if no_merge and equal == "否":
                issues.append({"level": "Critical", "code": "R6", "file": str(path), "line": i + 1,
                               "msg": "「渲染层是否归并/过滤」填「无」,却声明上游记录数 ≠ 页面条目数"
                                      "——既不归并也不过滤,两者不可能不等,这一行自相矛盾"})
            elif (not no_merge) and equal == "是":
                issues.append({"level": "Important", "code": "W2", "file": str(path), "line": i + 1,
                               "msg": "声明了归并/过滤(`%s`)却填「是」——1:1 的归并是可能的,"
                                      "但值得复核是不是把这一格填反了" % merge})

    return issues, tables


def main() -> int:
    ap = argparse.ArgumentParser(
        description="渲染层归并声明表硬核回检(dev-logic-architect 检查项 37)")
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
    tables = 0
    read_ok = 0
    for f in files:
        iss, n = check_file(f)
        issues.extend(iss)
        tables += n
        if not any(x["code"] == "read_error" and x["file"] == str(f) for x in iss):
            read_ok += 1
    if read_ok == 0:
        print("全部 .md 文件不可读: %s" % target, file=sys.stderr)
        return 2

    read_errors = [x for x in issues if x["code"] == "read_error"]
    skipped = tables == 0 and not read_errors
    criticals = [x for x in issues if x["level"] == "Critical"]
    warns = [x for x in issues if x["level"] != "Critical"]

    if args.json:
        print(json.dumps({
            "path": str(target), "skipped": skipped, "files": read_ok,
            "tables": tables, "read_errors": len(read_errors),
            "critical": len(criticals), "important": len(warns),
            "findings": issues,
        }, ensure_ascii=False, indent=2))
        return 1 if criticals else 0

    if skipped:
        print("⏭  跳过:未找到「渲染层归并声明表」。")
        print("   ⚠️ 跳过 ≠ 通过——本脚本刻意不做缺表判定(「列表」「卡片」在设计正文里几乎必然出现,")
        print("      扫正文必满屏假红);表该不该有由 QR 子 Agent 按检查项 37 判。")
        return 0

    print("扫描 %d 个文件 · 渲染层归并声明表 %d 张" % (read_ok, tables))
    if not issues:
        print("✅ 渲染层归并声明表检查通过(Critical 0 / Important 0)")
    else:
        for x in issues:
            loc = "%s:%d" % (x["file"], x["line"]) if x["line"] else x["file"]
            print("  [%s] %s  %s — %s" % (x["level"], x["code"], loc, x["msg"]))
        print("\n结论:Critical %d / Important %d" % (len(criticals), len(warns)))
    return 1 if criticals else 0


if __name__ == "__main__":
    sys.exit(main())
