#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""「字段实现清单」结构性硬核回检 — dev-logic-architect 反向覆盖门(维度 29 字段比对门 Critical 子项)

背景:实测发现「研发需求 → 详细设计」段字段粒度静默衰减 —— 研发需求列了具体列
(如「已购商品数 purchasedCount」),后端也返回了,但详细设计把字段清单**概括成一句话**
(如"按 PRD 重建为企业管理视角"),导致下游前端漏渲染该列、又自造出需求里没有的列
(如「总浏览时长」)。根因:缺**反向覆盖校验**。

本脚本做**结构性硬核回检**(可靠判定的结构缺陷,判错、退出码非 0):凡列表/表单/详情类
页面必须各产出一张「字段实现清单」表,列固定为:
    | 列名/字段 | 顺序 | 数据来源（接口字段） | 展示规则 | 上游出处 |
核查三件事:
  1. 存在性 —— 检测到的列表/表单/详情**页**必须有一张「字段实现清单」;缺 → 不通过。
  2. 表头 5 列齐全 —— 「字段实现清单」表头必须含 5 列(列名/字段、顺序、
     数据来源（接口字段）、展示规则、上游出处);缺列 → 不通过。
  3. 「上游出处」逐行非空 —— 每行「上游出处」必须可追溯(研发需求/PRD 具体位置),
     空白或占位符(-/—/无/N/A//待定/TBD)视为空 → 不通过。

「字段实现清单」表识别信号:markdown 表头行含唯一签名列「上游出处」。

⚠️ 本脚本**不做**语义层反向覆盖(研发需求每个字段是否都在字段实现清单出现、是否漏字段、
是否出现研发需求+PRD 均无的字段)—— 那是跨文档语义比对,由 QR 子 Agent 以研发需求
「需求字段清单」为基准逐字段核对判定(见 SKILL.md QR 步骤 0 / 检查项 29)。本脚本只做
结构性兜底,与 check_upstream_reference.py(**正向**溯源:详设元素段头部有无引用上游)
方向相反、并存互补、不可互相替代。

用法:
  python check_field_impl_inventory.py <设计文档文件或目录>
  python check_field_impl_inventory.py <设计文档文件或目录> --json

退出码:
  0  通过(所有页均有合规「字段实现清单」)/ 跳过(未检测到列表/表单/详情页 且无字段实现清单)
  1  不通过(缺清单 / 缺列 / 上游出处有空行)
  2  输入错误(路径不存在 / 无 .md 文件)——非维度违规,修正参数后重跑
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ── 「字段实现清单」5 列契约(与 SKILL.md 跨段词表契约严格一致) ──
# 每个概念给一组关键词;表头某单元格命中该概念的关键词即算该列存在。
SIGNATURE_COL = "上游出处"  # 唯一签名列:表头含此列 = 这是一张「字段实现清单」表
REQUIRED_COLUMNS = [
    "列名/字段",
    "顺序",
    "数据来源（接口字段）",
    "展示规则",
    "上游出处",
]

# 「上游出处」占位/空值判定:这些取值等同"无追溯来源",按空处理(违规)
EMPTY_MARKERS = {"", "-", "—", "–", "─", "无", "n/a", "na", "/", "\\", "待定",
                 "tbd", "todo", "?", "??", "待补", "待确认", "暂无"}

# 列表/表单/详情**页**标题识别:标题含页类关键词 + 明确"页/页面"锚,且不落在
# 排除集(接口/数据表/状态机 等非页面章节),以降低误报。
PAGE_TYPE_RE = re.compile(r"(列表|详情|表单|清单|录入|新增|编辑)")
PAGE_ANCHOR_RE = re.compile(r"页|页面")
PAGE_EXCLUDE_RE = re.compile(
    r"接口|API|数据表|表结构|状态机|DDL|枚举|字典|ER\b|索引|时序|异常|"
    r"缓存|依赖|归档|架构|字段实现清单|部署|配置"
)
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
    """归一化单元格文本用于列名匹配:去粗体/反引号/空白,全角括号→半角。"""
    s = re.sub(r"[*`>\s]", "", s)
    return s.replace("（", "(").replace("）", ")")


def cell_matches_column(cell: str, concept: str) -> bool:
    """判断某表头单元格是否承载指定列概念。"""
    c = _norm(cell)
    if concept == "列名/字段":
        if "列名" in c:
            return True
        # 纯"字段"列,排除"接口字段/数据来源"等
        return ("字段" in c) and ("接口" not in c) and ("数据来源" not in c) \
            and ("语义" in c or c in ("字段", "字段名", "列名/字段") or "列" in c or "字段名称" in c)
    if concept == "顺序":
        return "顺序" in c
    if concept == "数据来源（接口字段）":
        return ("数据来源" in c) or ("接口字段" in c)
    if concept == "展示规则":
        return ("展示规则" in c) or (("展示" in c) and ("顺序" not in c))
    if concept == "上游出处":
        return "上游出处" in c or ("上游" in c and "出处" in c)
    return False


def header_missing_columns(cells: List[str]) -> List[str]:
    """返回表头缺失的列概念清单(按 REQUIRED_COLUMNS 顺序)。"""
    missing: List[str] = []
    for concept in REQUIRED_COLUMNS:
        if not any(cell_matches_column(c, concept) for c in cells):
            missing.append(concept)
    return missing


def is_inventory_header(cells: List[str]) -> bool:
    """签名判定:表头单元格含「上游出处」列 = 一张「字段实现清单」表。"""
    return any(cell_matches_column(c, "上游出处") for c in cells)


def upstream_col_index(cells: List[str]) -> Optional[int]:
    for idx, c in enumerate(cells):
        if cell_matches_column(c, "上游出处"):
            return idx
    return None


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

    inventory_tables: List[Dict] = []   # 每张字段实现清单表:含表头行/缺列/空上游出处行
    inventory_line_set = set()          # 字段实现清单表头所在行号(1-based),用于页覆盖判定
    pages: List[Dict] = []             # 检测到的列表/表单/详情页:含标题行 + 章节范围

    # ── 1. 定位页(章节)── 收集 heading 及其层级
    headings: List[Tuple[int, int, str]] = []  # (line0, level, title)
    in_code = False
    for i, line in enumerate(lines):
        st = line.strip()
        if st.startswith("```") or st.startswith("~~~"):
            in_code = not in_code
            continue
        if in_code:
            continue
        m = HEADING_RE.match(line)
        if m:
            headings.append((i, len(m.group(1)), m.group(2)))

    for hi, (h_line0, level, title) in enumerate(headings):
        if not (PAGE_TYPE_RE.search(title) and PAGE_ANCHOR_RE.search(title)):
            continue
        if PAGE_EXCLUDE_RE.search(title):
            continue
        # 章节范围:到下一个同级或更高级标题前
        end0 = n
        for (h2_line0, level2, _t) in headings[hi + 1:]:
            if level2 <= level:
                end0 = h2_line0
                break
        pages.append({
            "title": title,
            "line": h_line0 + 1,
            "start0": h_line0,
            "end0": end0,
            "has_inventory": False,  # 稍后回填
        })

    # ── 2. 扫描所有 markdown 表格,挑出「字段实现清单」表并校验 ──
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
        if not is_inventory_header(cells):
            i += 1
            continue

        # 命中字段实现清单表头
        header_line = i + 1
        inventory_line_set.add(header_line)
        missing_cols = header_missing_columns(cells)
        up_idx = upstream_col_index(cells)
        empty_upstream_rows: List[Dict] = []
        j = i + 1
        # 跳过分隔行
        if j < n and "|" in lines[j] and is_separator_row(split_row(lines[j])):
            j += 1
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
            # 全空行终止
            if all(c == "" for c in rcells):
                break
            if up_idx is not None:
                val = rcells[up_idx].strip() if up_idx < len(rcells) else ""
                if _norm(val).lower() in EMPTY_MARKERS or val.strip() == "":
                    empty_upstream_rows.append({
                        "line": j + 1,
                        "field": rcells[0].strip()[:40] if rcells else "",
                        "value": val[:40],
                    })
            j += 1

        inventory_tables.append({
            "header_line": header_line,
            "missing_columns": missing_cols,
            "empty_upstream_rows": empty_upstream_rows,
            "row_count": (j - i - 2) if j > i + 1 else 0,
        })
        i = j

    # ── 3. 回填页是否含字段实现清单(表头行落在页章节范围内) ──
    for pg in pages:
        s0, e0 = pg["start0"], pg["end0"]
        # 页含 inventory 表头,或页正文出现「字段实现清单」字样
        has_tbl = any(s0 < (hl - 1) < e0 for hl in inventory_line_set)
        has_label = any("字段实现清单" in lines[k] for k in range(s0, min(e0, n)))
        pg["has_inventory"] = has_tbl or has_label

    return {
        "file": rel,
        "pages": pages,
        "inventory_tables": inventory_tables,
    }


def build_violations(results: List[Dict]) -> List[Dict]:
    violations: List[Dict] = []
    for r in results:
        if r.get("read_error"):
            continue
        f = r["file"]
        # 缺列 / 上游出处空行(逐张字段实现清单表)
        for tbl in r["inventory_tables"]:
            if tbl["missing_columns"]:
                violations.append({
                    "type": "缺列",
                    "file": f,
                    "line": tbl["header_line"],
                    "detail": "字段实现清单表头缺列: " + " / ".join(tbl["missing_columns"]),
                })
            for row in tbl["empty_upstream_rows"]:
                violations.append({
                    "type": "上游出处空",
                    "file": f,
                    "line": row["line"],
                    "detail": f"「上游出处」为空/占位(字段「{row['field']}」),必须可追溯到"
                              f"研发需求或 PRD 具体位置",
                })
        # 缺清单(检测到页但页内无字段实现清单)
        for pg in r["pages"]:
            if not pg["has_inventory"]:
                violations.append({
                    "type": "缺清单",
                    "file": f,
                    "line": pg["line"],
                    "detail": f"列表/表单/详情页「{pg['title']}」缺「字段实现清单」表"
                              f"(应逐列产出,禁一句话概括)",
                })
    return violations


def render_text(results: List[Dict], violations: List[Dict],
                page_total: int, inv_total: int) -> str:
    out: List[str] = []
    out.append("=== 「字段实现清单」结构性硬核回检(维度 29 字段比对门 Critical 子项) ===\n")
    out.append(f"检测到列表/表单/详情页: {page_total} 个")
    out.append(f"检测到「字段实现清单」表: {inv_total} 张\n")

    if page_total == 0 and inv_total == 0:
        out.append("ℹ️ 未检测到列表/表单/详情页,也无「字段实现清单」表 → 跳过(退出码 0)。")
        out.append("   若该设计实际含列表/表单/详情页却未被识别(标题未带「页/页面」锚),")
        out.append("   QR 子 Agent 仍须以研发需求「需求字段清单」为基准做语义层反向覆盖核对。")
        return "\n".join(out)

    for r in results:
        if r.get("read_error"):
            out.append(f"[读取失败] {r['file']}: {r['read_error']}")
            continue
        if not r["pages"] and not r["inventory_tables"]:
            continue
        out.append(f"📄 {r['file']}")
        for pg in r["pages"]:
            mark = "✅" if pg["has_inventory"] else "❌"
            out.append(f"   {mark} 页 L{pg['line']} 「{pg['title']}」"
                       f"{'含字段实现清单' if pg['has_inventory'] else '缺字段实现清单'}")
        for tbl in r["inventory_tables"]:
            miss = tbl["missing_columns"]
            emp = tbl["empty_upstream_rows"]
            status = "✅" if (not miss and not emp) else "❌"
            out.append(f"   {status} 字段实现清单表 L{tbl['header_line']} "
                       f"({tbl['row_count']} 行)"
                       + (f" 缺列: {'/'.join(miss)}" if miss else "")
                       + (f" 上游出处空 {len(emp)} 行" if emp else ""))
        out.append("")

    if violations:
        out.append(f"❌ 不通过: 共 {len(violations)} 处结构缺陷\n")
        for v in violations:
            out.append(f"  [{v['type']}] {v['file']}:L{v['line']}  {v['detail']}")
    else:
        out.append("✅ 通过: 所有列表/表单/详情页均有合规「字段实现清单」"
                   "(5 列齐全 + 上游出处逐行非空)")

    out.append("")
    out.append("⚠️ 本脚本只做结构性硬核回检,不做语义层反向覆盖。QR 子 Agent 仍须以研发需求"
               "「需求字段清单」(语义)为基准逐字段核对:")
    out.append("   - 研发需求已列字段是否都在字段实现清单出现(漏字段 → 判不通过);")
    out.append("   - 是否出现研发需求 + PRD 均无的字段(须补登记来源与理由或移除)。")
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
        # 跳过专职索引 / 待澄清清单(不承载字段实现清单)
        if f.name.startswith("00_") or "99_" in f.name:
            continue
        results.append(scan_file(f, root))

    page_total = sum(len(r.get("pages", [])) for r in results)
    inv_total = sum(len(r.get("inventory_tables", [])) for r in results)
    violations = build_violations(results)
    passed = len(violations) == 0

    if args.json:
        print(json.dumps({
            "passed": passed,
            "page_total": page_total,
            "inventory_table_total": inv_total,
            "violations": violations,
            "files": results,
        }, ensure_ascii=False, indent=2))
    else:
        print(render_text(results, violations, page_total, inv_total))

    # 跳过场景:未检测到页也无清单表 → 退出码 0
    if page_total == 0 and inv_total == 0:
        return 0
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
