#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""详细设计「字段实现清单」采集脚本
(对应 code-verification-loop 维度 4「字段集与设计双向比对」🔴 Critical)

从 dev-logic-architect 产出的详细设计 md 里,抽取所有「**字段实现清单**」表
(字段级表,典型表头:`列名/字段 | 顺序 | 数据来源（接口字段） | 展示规则 | 上游出处`),
逐行采集 `列名/字段`、`顺序`、`上游出处`,输出
`文件:行号 + 页面/表名 + 列名 + 顺序 + 上游出处` 清单。

本清单为**设计侧集合**,供验收 Agent 与 `scan_field_columns.py` 采集的
**实现侧集合**(前端表格列/表单项)做**双向比对**,并按三档判定:
  · 设计有、实现无 → 🔴 Critical(漏实现)
  · 实现有、设计无 → 🟡 Important(未经确认增列,须补登记或移除)
  · 顺序不一致     → 🔵 Info(提示,不阻断)

⚠️ 重要:本脚本只负责"采集设计侧字段集合",**不判定是否违规**、**不做跨产物比对**。
   两侧集合的双向比对与三档(Critical/Important/Info)判定,均由验收 Agent 完成
   (跨产物的顺序/语义比对脚本无法可靠承担)。因此本脚本退出码恒为 0(仅报告)。

   本行检查与维度 4 既有「字段/列对账」行**互补不替代**:
     · 「字段/列对账」比对上游 ux-logic-extractor 的**需求字段清单(语义)**;
     · 「字段集与设计双向比对」(本脚本)比对上游 dev-logic-architect 的
        详细设计「**字段实现清单**」。

表识别规则(内联自包含,不跨 SKILL 引用):
   将 md 里的每个 Markdown 表格视作候选,满足下列任一即判为「字段实现清单」表:
     (a) 表头同时含【名称列(含「列名」或「字段」)】+【「顺序」列】+【「上游出处」/「上游」列】; 或
     (b) 表格上方 ≤8 行内出现字样「字段实现清单」,且表头含【名称列】。
   页面/表名取表格上方最近的 Markdown 标题(`#`..`######`);无标题时取
   最近的「字段实现清单」字样所在行文本;都没有则留空。

扫描文件类型: .md .markdown
豁免目录:     node_modules .git dist build target out
              .next .nuxt vendor __pycache__ coverage .idea .vscode

退出码:
  0 = 始终(仅报告,采到与否都不判错;双向比对与判定交给 Agent)
  2 = 用法错误或设计目录不存在

用法:
  python scan_design_field_inventory.py <详细设计目录>
  python scan_design_field_inventory.py <详细设计目录> --json

JSON 输出:
  {"inventory": [{"file":..,"line":..,"page":..,"column":..,"order":..,"upstream":..}],
   "total": N,
   "tables": M}
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# 扫描的文档后缀
SCAN_SUFFIXES = {".md", ".markdown"}

# 豁免目录段
EXCLUDED_DIRS = {
    "node_modules", ".git", "dist", "build", "target", "out",
    ".next", ".nuxt", "vendor", "__pycache__", ".idea", ".vscode",
    "coverage", ".nyc_output", "tmp", ".cache",
}

# 「字段实现清单」锚点字样
INVENTORY_CAPTION = "字段实现清单"
CAPTION_LOOKBACK = 8  # 表格上方回看多少行找锚点字样

# Markdown 标题
HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*\S)\s*$")


def is_excluded(path: Path, root: Path) -> bool:
    """仅基于 root 以内的相对路径判断排除,避免项目位于含排除名祖先目录时被整体跳过。"""
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = path
    parts = set(rel.parts)
    return bool(parts & EXCLUDED_DIRS)


def _is_table_row(line: str) -> bool:
    s = line.strip()
    return s.startswith("|") and s.count("|") >= 2


def _is_separator_row(line: str) -> bool:
    s = line.strip()
    if not s.startswith("|"):
        return False
    # 去掉首尾管道后,每个单元格仅由 - : 空格 组成,且至少含一个 -
    inner = s.strip("|")
    cells = inner.split("|")
    saw_dash = False
    for c in cells:
        c = c.strip()
        if not re.fullmatch(r":?-{1,}:?", c):
            return False
        saw_dash = True
    return saw_dash


def _split_cells(line: str) -> List[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _col_index(headers: List[str], *needles: str) -> int:
    for i, h in enumerate(headers):
        for n in needles:
            if n in h:
                return i
    return -1


def _classify_header(headers: List[str]) -> Tuple[int, int, int]:
    """返回 (名称列 idx, 顺序列 idx, 上游出处列 idx),缺失为 -1。"""
    name_idx = _col_index(headers, "列名", "字段")
    order_idx = _col_index(headers, "顺序")
    upstream_idx = _col_index(headers, "上游出处", "上游")
    return name_idx, order_idx, upstream_idx


def _nearest_context(lines: List[str], header_line_no: int) -> str:
    """表格上方最近的 Markdown 标题;无则取 ≤CAPTION_LOOKBACK 行内的锚点字样所在行。"""
    # header_line_no 为 1-based
    idx = header_line_no - 1  # 0-based header line
    # 先找最近标题(向上不限行,但遇到另一个表格分隔就停)
    for j in range(idx - 1, -1, -1):
        m = HEADING.match(lines[j])
        if m:
            return m.group(1).strip()
    # 再退回锚点字样所在行
    start = max(0, idx - CAPTION_LOOKBACK)
    for j in range(idx - 1, start - 1, -1):
        if INVENTORY_CAPTION in lines[j]:
            return lines[j].strip().lstrip("#").strip()
    return ""


def scan_file(path: Path, root: Path) -> Tuple[List[Dict], int]:
    rows: List[Dict] = []
    tables = 0
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return rows, tables
    try:
        rel = str(path.relative_to(root))
    except ValueError:
        rel = str(path)

    lines = text.splitlines()
    n = len(lines)
    i = 0
    while i < n:
        # 寻找表头行 + 分隔行
        if _is_table_row(lines[i]) and i + 1 < n and _is_separator_row(lines[i + 1]):
            headers = _split_cells(lines[i])
            name_idx, order_idx, upstream_idx = _classify_header(headers)

            # 表头签名判定
            sig_match = name_idx >= 0 and order_idx >= 0 and upstream_idx >= 0
            # 锚点字样判定
            caption_match = False
            if name_idx >= 0 and not sig_match:
                start = max(0, i - CAPTION_LOOKBACK)
                for j in range(i - 1, start - 1, -1):
                    if INVENTORY_CAPTION in lines[j]:
                        caption_match = True
                        break

            if sig_match or caption_match:
                tables += 1
                page = _nearest_context(lines, i + 1)  # header 行号 1-based
                # 数据行从 i+2 起
                k = i + 2
                while k < n and _is_table_row(lines[k]) and not _is_separator_row(lines[k]):
                    cells = _split_cells(lines[k])

                    def cell(idx: int) -> str:
                        return cells[idx] if 0 <= idx < len(cells) else ""

                    column = cell(name_idx)
                    order = cell(order_idx)
                    upstream = cell(upstream_idx)
                    # 跳过整行空的行
                    if column or order or upstream:
                        rows.append({
                            "file": rel,
                            "line": k + 1,
                            "page": page,
                            "column": column,
                            "order": order,
                            "upstream": upstream,
                        })
                    k += 1
                i = k
                continue
        i += 1

    return rows, tables


def scan(root: Path) -> Dict:
    inventory: List[Dict] = []
    tables = 0
    scanned = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SCAN_SUFFIXES:
            continue
        if is_excluded(path, root):
            continue
        scanned += 1
        rows, t = scan_file(path, root)
        inventory.extend(rows)
        tables += t
    inventory.sort(key=lambda h: (h["file"], h["line"]))
    # ⚠️ 「0 命中」必须能与「0 文件被扫(路径给错)」区分开(见姊妹脚本同款注释),故补 scanned_files
    return {"inventory": inventory, "total": len(inventory), "tables": tables,
            "scanned_files": scanned, "skipped": scanned == 0}


def render_text(result: Dict) -> str:
    out: List[str] = []
    out.append("=== 详细设计「字段实现清单」采集 (维度 4: 字段集与设计双向比对) ===")
    total = result["total"]
    tables = result["tables"]
    out.append(f"\n采集设计侧字段: {total} 处  (来自 {tables} 张「字段实现清单」表)")
    if total == 0:
        out.append(
            "\n⚠️ 未采集到「字段实现清单」表"
            "(可能详细设计未产出该表,或使用了脚本未覆盖的写法,需 Agent 人工核对)。"
        )
        return "\n".join(out)
    cur_file = None
    for h in result["inventory"]:
        if h["file"] != cur_file:
            cur_file = h["file"]
            out.append(f"\n📄 {cur_file}")
        page = h["page"] or "(无页面/表名)"
        column = h["column"] or "(无列名)"
        order = h["order"] or "-"
        upstream = h["upstream"] or "-"
        out.append(
            f"  - L{h['line']:<5} [{page}]  列名={column}  顺序={order}  上游出处={upstream}"
        )
    out.append("\n⚠️ 以上仅为**设计侧**集合采集;是否违规须由 Agent 与实现侧集合")
    out.append("   (scan_field_columns.py 采集的前端表格列/表单项)做**双向比对**后判定:")
    out.append("   · 设计有、实现无 → 🔴 Critical(漏实现)")
    out.append("   · 实现有、设计无 → 🟡 Important(未经确认增列,须补登记或移除)")
    out.append("   · 顺序不一致     → 🔵 Info(提示,不阻断)")
    out.append("   (本行与既有「字段/列对账」互补:那行比需求字段清单(语义),本行比详设「字段实现清单」)")
    return "\n".join(out)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("root", type=Path, help="详细设计文档根目录")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出供 Agent 解析")
    args = parser.parse_args(argv)

    if not args.root.exists() or not args.root.is_dir():
        print(f"错误: 设计目录不存在或不是目录: {args.root}", file=sys.stderr)
        return 2

    result = scan(args.root)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_text(result))

    # 仅报告:采到与否都返回 0,双向比对与判定交给 Agent
    return 0


if __name__ == "__main__":
    sys.exit(main())
