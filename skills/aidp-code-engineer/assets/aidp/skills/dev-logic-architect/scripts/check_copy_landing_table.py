#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""「文案落点表」结构性硬核回检 — dev-logic-architect 语义/口径变更类需求文案落点门
(维度 29 字段比对门·文案落点姊妹子表 Critical 子项)

背景:实测发现「口径/语义扩大」类需求(如「用量消费统计口径由『仅企业』扩为
『企业+个人』」)后端/接口/前端取数全改对,但**解释该数值的散落文案**(tooltip/
副标题/图例/导出表头/空态说明…)有遗漏未同步改——某处 tooltip 仍写"仅统计企业级、
不含员工个人消费",与实际展示值相反、误导对账(实际项目缺陷,P1)。根因:
字段改对了,但解释字段语义的文案落点没有清单化逐一落地。

对策:凡语义/口径变更类需求,以上游 ux-logic-extractor「表 E:语义变更 → 派生展示物
影响清单」(处置 ∈ 改写/保持/新增/待产品确认)为基准,追加一张与「字段实现清单」同级、
同强制度的姊妹子表「文案落点表」,列固定为:
    | # | 文件路径 | 展示位（tooltip/副标题/图例/导出表头/…）| 改前文案 | 改后文案 |

本脚本做**结构性硬核回检**(可靠判定的结构缺陷,判错、退出码非 0):检测到「文案落点表」时
核查两件事:
  1. 表头 5 列齐全 —— 表头必须含 5 列(#、文件路径、展示位、改前文案、改后文案);
     缺列 → 不通过。
  2. 改前/改后文案逐行非空无占位 —— 每行「改前文案」「改后文案」两列均须逐字填实,
     空白或占位符(待定/按实际调整/TBD/-/—/无/N/A 等)视为空 → 不通过。

「文案落点表」识别信号:markdown 表头行同时含「改前文案」列 + 「改后文案」列
(区别于「字段实现清单」的签名列「上游出处」)。

⚠️ 本脚本**不做**语义层覆盖(上游「表 E」每个处置=改写项是否都在文案落点表落地、
"不改边界"小节是否完整、改后文案是否真正对齐变更后语义)—— 那是跨产物语义比对,
由 QR 子 Agent 以上游「表 E」为基准逐项核对判定(见 SKILL.md QR 步骤 0'' / 检查项 29
A″ 第 18/19/20 项)。本脚本只做结构性兜底,与 check_field_impl_inventory.py
(「字段实现清单」结构回检)同为字段实现清单章节体系的结构性兜底、方向互补、不可互相替代。

用法:
  python check_copy_landing_table.py <设计文档文件或目录>
  python check_copy_landing_table.py <设计文档文件或目录> --json

退出码:
  0  通过(所有「文案落点表」合规)/ 跳过(未检测到「文案落点表」= 非语义变更类需求)
  1  不通过(缺列 / 改前或改后文案有空行/占位)
  2  输入错误(路径不存在 / 无 .md 文件)——非维度违规,修正参数后重跑
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

# ── 「文案落点表」5 列契约(与 SKILL.md / 上游「表 E」跨产物词表契约严格一致) ──
REQUIRED_COLUMNS = ["#", "文件路径", "展示位", "改前文案", "改后文案"]
# 需逐行非空核验的两个文案列
NONEMPTY_COLUMNS = ["改前文案", "改后文案"]

# 文案列占位/空值判定:这些取值等同"文案未落地",按空处理(违规)
EMPTY_MARKERS = {"", "-", "—", "–", "─", "无", "n/a", "na", "/", "\\", "待定",
                 "tbd", "todo", "?", "??", "待补", "待确认", "暂无", "待产品确认",
                 "按实际调整", "按实际", "视情况", "同上", "略"}

HEADING_RE = re.compile(r"^(#{2,6})\s+(.*\S)\s*$")


def find_md_files(path: Path) -> List[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(path.rglob("*.md"))
    return []


def split_row(line: str) -> List[str]:
    """切分 markdown 表格行为单元格列表(去掉首尾空管道)。"""
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
    """归一化单元格文本:去粗体/反引号/引用符/空白,全角括号→半角。"""
    s = re.sub(r"[*`>\s]", "", s)
    return s.replace("（", "(").replace("）", ")")


def cell_matches_column(cell: str, concept: str) -> bool:
    """判断某表头单元格是否承载指定列概念。"""
    c = _norm(cell)
    if concept == "#":
        # 序号列:恰为 #/序号/编号/No
        return c in ("#", "序号", "编号", "no", "no.") or "序号" in c or "编号" in c
    if concept == "文件路径":
        return ("文件路径" in c) or ("文件" in c and "路径" in c) or c in ("文件", "路径", "文件名")
    if concept == "展示位":
        return "展示位" in c or "展示位置" in c or c.startswith("展示位")
    if concept == "改前文案":
        return ("改前文案" in c) or ("改前" in c and "文案" in c) \
            or ("变更前" in c and "文案" in c) or ("原文案" in c)
    if concept == "改后文案":
        return ("改后文案" in c) or ("改后" in c and "文案" in c) \
            or ("变更后" in c and "文案" in c) or ("新文案" in c)
    return False


def col_index(cells: List[str], concept: str) -> Optional[int]:
    for idx, c in enumerate(cells):
        if cell_matches_column(c, concept):
            return idx
    return None


def header_missing_columns(cells: List[str]) -> List[str]:
    missing: List[str] = []
    for concept in REQUIRED_COLUMNS:
        if not any(cell_matches_column(c, concept) for c in cells):
            missing.append(concept)
    return missing


def is_landing_header(cells: List[str]) -> bool:
    """签名判定:表头同时含「改前文案」+「改后文案」列 = 一张「文案落点表」。"""
    return (any(cell_matches_column(c, "改前文案") for c in cells)
            and any(cell_matches_column(c, "改后文案") for c in cells))


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
    n = len(lines)
    tables: List[Dict] = []

    in_code = False
    i = 0
    while i < n:
        line = lines[i]
        st = line.strip()
        if st.startswith("```") or st.startswith("~~~"):
            in_code = not in_code
            i += 1
            continue
        if in_code or "|" not in line:
            i += 1
            continue
        cells = split_row(line)
        if is_separator_row(cells):
            i += 1
            continue
        if not is_landing_header(cells):
            i += 1
            continue

        # 命中文案落点表表头
        header_line = i + 1
        missing_cols = header_missing_columns(cells)
        empty_cells: List[Dict] = []
        idx_map = {c: col_index(cells, c) for c in NONEMPTY_COLUMNS}
        j = i + 1
        # 跳过分隔行
        if j < n and "|" in lines[j] and is_separator_row(split_row(lines[j])):
            j += 1
        row_count = 0
        while j < n:
            if "|" not in lines[j]:
                break
            rcells = split_row(lines[j])
            # ⚠️ 全空行既**不算分隔行**(见 is_separator_row 前置判)、也**不算数据行**:两个性质必须
            #    同时成立。只改前者会让 Word 转出的 `||||` 占位行变成数据行、每格报一条「为空」
            #    (真实 PRD 语料里有 35 处这种行)。
            if is_separator_row(rcells) or all(c.strip() == "" for c in rcells):
                j += 1
                continue
            if all(c == "" for c in rcells):
                break
            row_count += 1
            for concept in NONEMPTY_COLUMNS:
                ci = idx_map.get(concept)
                if ci is None:
                    continue
                val = rcells[ci].strip() if ci < len(rcells) else ""
                if _norm(val).lower() in EMPTY_MARKERS or val.strip() == "":
                    empty_cells.append({
                        "line": j + 1,
                        "column": concept,
                        "value": val[:40],
                    })
            j += 1

        tables.append({
            "header_line": header_line,
            "missing_columns": missing_cols,
            "empty_cells": empty_cells,
            "row_count": row_count,
        })
        i = j

    return {"file": rel, "landing_tables": tables}


def build_violations(results: List[Dict]) -> List[Dict]:
    violations: List[Dict] = []
    for r in results:
        if r.get("read_error"):
            continue
        f = r["file"]
        for tbl in r["landing_tables"]:
            if tbl["missing_columns"]:
                violations.append({
                    "type": "缺列",
                    "file": f,
                    "line": tbl["header_line"],
                    "detail": "文案落点表表头缺列: " + " / ".join(tbl["missing_columns"]),
                })
            for cell in tbl["empty_cells"]:
                violations.append({
                    "type": "文案空",
                    "file": f,
                    "line": cell["line"],
                    "detail": f"「{cell['column']}」为空/占位(值「{cell['value']}」),"
                              f"语义变更类需求的文案落点必须逐字填实,禁待定/按实际调整",
                })
    return violations


def render_text(results: List[Dict], violations: List[Dict], tbl_total: int) -> str:
    out: List[str] = []
    out.append("=== 「文案落点表」结构性硬核回检(维度 29·文案落点姊妹子表 Critical 子项) ===\n")
    out.append(f"检测到「文案落点表」: {tbl_total} 张\n")

    if tbl_total == 0:
        out.append("ℹ️ 未检测到「文案落点表」→ 跳过(退出码 0)。")
        out.append("   判定为非语义/口径变更类需求(上游无「表 E」或表 E 无处置=改写项)。")
        out.append("   若本次实为语义变更类需求(上游产出「表 E」含改写项)却缺「文案落点表」,")
        out.append("   QR 子 Agent 须以上游「表 E」为基准判维度 29 不通过(见检查项 29 A″)。")
        return "\n".join(out)

    for r in results:
        if r.get("read_error"):
            out.append(f"[读取失败] {r['file']}: {r['read_error']}")
            continue
        if not r["landing_tables"]:
            continue
        out.append(f"📄 {r['file']}")
        for tbl in r["landing_tables"]:
            miss = tbl["missing_columns"]
            emp = tbl["empty_cells"]
            status = "✅" if (not miss and not emp) else "❌"
            out.append(f"   {status} 文案落点表 L{tbl['header_line']} "
                       f"({tbl['row_count']} 行)"
                       + (f" 缺列: {'/'.join(miss)}" if miss else "")
                       + (f" 文案空/占位 {len(emp)} 处" if emp else ""))
        out.append("")

    if violations:
        out.append(f"❌ 不通过: 共 {len(violations)} 处结构缺陷\n")
        for v in violations:
            out.append(f"  [{v['type']}] {v['file']}:L{v['line']}  {v['detail']}")
    else:
        out.append("✅ 通过: 所有「文案落点表」5 列齐全 + 改前/改后文案逐行非空无占位")

    out.append("")
    out.append("⚠️ 本脚本只做结构性硬核回检,不做语义层覆盖。QR 子 Agent 仍须以上游「表 E」"
               "(语义变更 → 派生展示物影响清单)为基准逐项核对:")
    out.append("   - 表 E 每个处置=改写项是否都在文案落点表有对应「文件:展示位」落点行(漏落点 → 不通过);")
    out.append("   - 「文案落点表」下方是否有『不改边界』小节(形似但不受影响的文案 + 理由,防过度改写/漏改);")
    out.append("   - 改后文案是否真正对齐表 E『变更后语义』(非仍写旧口径)。")
    return "\n".join(out)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("path", type=Path, help="详细设计文档文件或目录")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    args = parser.parse_args(argv)

    if not args.path.exists():
        print(f"错误: 路径不存在 {args.path}", file=sys.stderr)
        return 2

    root = args.path if args.path.is_dir() else args.path.parent
    md_files = find_md_files(args.path)
    if not md_files:
        print("⚠️ 未发现任何 .md 文件", file=sys.stderr)
        return 2

    results: List[Dict] = []
    for f in md_files:
        # 跳过专职索引 / 待澄清清单(不承载文案落点表)
        if f.name.startswith("00_") or "99_" in f.name:
            continue
        results.append(scan_file(f, root))

    tbl_total = sum(len(r.get("landing_tables", [])) for r in results)
    violations = build_violations(results)
    passed = len(violations) == 0

    if args.json:
        print(json.dumps({
            "passed": passed,
            "landing_table_total": tbl_total,
            "violations": violations,
            "files": results,
        }, ensure_ascii=False, indent=2))
    else:
        print(render_text(results, violations, tbl_total))

    # 跳过场景:未检测到文案落点表 → 退出码 0
    if tbl_total == 0:
        return 0
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
