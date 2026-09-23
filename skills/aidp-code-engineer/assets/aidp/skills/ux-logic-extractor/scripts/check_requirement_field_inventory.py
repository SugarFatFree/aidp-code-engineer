#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""需求字段去向登记 结构性存在性检查 — ux-logic-extractor 维度 13

对研发 PRD 文档(.md)做「需求字段清单(六·4)」的**结构性存在性采集**,供 QR Agent 据此
+ 原型/产品需求逐项比对判定维度 13。主体为「采集不判错 / report-only」:表 B/C 疑点只列出交 Agent 判定;
唯一判错项是表 A「字段语义名称」混入代码级标识(Critical,可确定性机检,退出码 1)。

采集项:
  1. 是否存在「表 A 需求字段清单」——以表头特征列识别(主键列「字段语义名称」+ 辅助列
     展示形态 / 展示顺序 / 是否筛选项 / 业务含义 任一同行表头)。
  2. 是否存在「表 B 处置对照表」——以表头特征列识别(需求字段(语义) + 处置 + 说明)。
  3. 表 B 各数据行「处置」取值是否 ∈ 固定枚举 {保留, 裁剪, 前端计算还原, 请第三方补};
     越界取值列为疑点。
  4. 处置=裁剪 的行,「说明」是否带「待产品确认」字样;缺失列为疑点。
  5. 是否存在「表 C 原型元素·操作逻辑 → 处置对照表」——以表头特征列识别(层 + 原型元素/操作逻辑
     + 处置 + 说明)。表 C 覆盖「原型对齐三层原则」的内容层 + 操作逻辑层(非字段可见元素与操作逻辑)。
  6. 表 C 各数据行「处置」取值是否 ∈ 固定枚举 {实现, 裁剪, 延期, 改为X}(实现可带「(默认)」,改为X 为
     「改为 …」前缀);越界取值列为疑点。
  7. 表 C 非实现项(裁剪 / 延期 / 改为X)的「说明」是否带「待产品确认」字样;缺失列为疑点。

注意:本脚本**无法**判断"原型/产品需求可见数据项是否 100% 登记"(表 A 漏列)、"原型 code/(或上游
`原型内容基线.md`/`DESIGN-MANIFEST.json`)可见非字段元素/操作逻辑是否 100% 登记"(表 C 漏项)、
"上游基线『实现』项是否都在 PRD 落地",也无法判断表 A 是否混入代码级标识——那需要读原型/上游基线
逐项盘点,只能由 QR Agent 完成。脚本只做结构性兜底。

用法:
  python check_requirement_field_inventory.py <PRD 文件或目录>
  python check_requirement_field_inventory.py <PRD 文件或目录> --json

退出码:
  0  未发现表 A 代码级标识(其余采集项 report-only,不影响退出码)
  1  表 A「字段语义名称」混入代码级标识(Critical)
  2  输入错误(路径不存在 / 无 .md 文件)——非维度违规,修正参数后重跑
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

# 处置固定枚举(与 SKILL.md 六·4 / 维度 13 严格一致)
DISPOSITION_ENUM = ["保留", "裁剪", "前端计算还原", "请第三方补"]
# 表 C 处置固定枚举(与 SKILL.md 六·4 表 C / 原型对齐三层原则严格一致)
DISPOSITION_ENUM_C = ["实现", "裁剪", "延期", "改为X"]
PENDING_CONFIRM_RE = re.compile(r"待产品确认")

# ── 表 A「字段语义名称」列的代码级标识判定（SKILL.md:1286/:1307 的 Critical 铁律） ──
# 该列必须是**纯业务语义中文名**，严禁英文变量名 / 拼音 / 列表 prop/dataIndex /
# 表单 v-model/name/id / 数据库列名。表 A 是下游 architect / cvl / dmtc 三个 SKILL
# 字段对账的**单一信源**，代码级命名混进来等于把职责边界污染直接注入整条对账链。
# ⚠️ 这条铁律此前**零机检**：check_technical_content 的 R2 要求「camelCase + 同行类型词」，
#    而表 A 的「展示形态」列写的是中文形态词，故永不命中；本脚本自己也只 report-only。
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
# 纯 ASCII 标识符：userName / dept_id / createTime / id
CODE_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
# 允许的例外：纯数字、纯符号、单个大写字母（如表头占位）、常见业务缩写全大写（ID/URL/PDF）
CODE_IDENT_ALLOW = {"ID", "URL", "PDF", "IP", "PC", "APP", "API", "SN", "QR"}


def is_code_level_field_name(name: str) -> bool:
    """字段语义名称是否为代码级标识（True = 违规）。"""
    s = re.sub(r"[*`>\s]", "", name or "")
    if not s:
        return False
    if CJK_RE.search(s):          # 含中文即认为是业务语义名
        return False
    if s.upper() in CODE_IDENT_ALLOW:
        return False
    return bool(CODE_IDENT_RE.match(s))

# 表 A 表头特征:同一表头行含主键列「字段语义名称」+ 任一辅助列(纯业务语义,不含代码级标识列)
TABLE_A_PRIMARY = ["字段语义名称"]
TABLE_A_AUX = ["展示形态", "展示顺序", "是否筛选项", "业务含义"]
# 表 B 表头特征:同一表头行同时含「需求字段」(语义)「处置」「说明」
TABLE_B_HEADER = ["需求字段", "处置", "说明"]
# 表 C 表头特征:同一表头行含「层」+「原型元素」或「操作逻辑」+「处置」+「说明」
TABLE_C_REQUIRED = ["处置", "说明"]
TABLE_C_LAYER = ["层"]
TABLE_C_ITEM = ["原型元素", "操作逻辑"]


def is_table_c_disposition_in_enum(disp_clean: str) -> bool:
    """表 C 处置枚举判定:实现(可带「(默认)」) / 裁剪 / 延期 / 改为…(改为X 前缀)。"""
    if disp_clean.startswith("实现"):
        return True
    if disp_clean in ("裁剪", "延期"):
        return True
    if disp_clean.startswith("改为"):
        return True
    return False


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
    """识别 markdown 表格分隔行(如 :- / :-: / ---)。"""
    # ⚠️ 空行必须先判掉:split_row("") 得到 [""],把空单元格过滤后 all() 对空序列返回 True,
    #    于是**空行被当成分隔行** ——「候选表头 + 紧跟一个空行」会被识别成一张 0 行的表,
    #    对按表头签名判列的检查器就是一条凭空的「缺列 Critical」。
    #    实测复现:`output-module-examples.md` B.7 的键值表末行 + 空行 → 假红。勿改回。
    if not cells or all(c.strip() == "" for c in cells):
        return False
    return all(re.fullmatch(r":?-{1,}:?", c.replace(" ", "")) for c in cells if c != "")


def is_table_a_header(cells: List[str]) -> bool:
    joined = " ".join(cells)
    if not all(k in joined for k in TABLE_A_PRIMARY):
        return False
    return any(k in joined for k in TABLE_A_AUX)


def is_table_b_header(cells: List[str]) -> bool:
    joined = " ".join(cells)
    return all(k in joined for k in TABLE_B_HEADER)


def is_table_c_header(cells: List[str]) -> bool:
    joined = " ".join(cells)
    if not all(k in joined for k in TABLE_C_REQUIRED):
        return False
    if not any(k in joined for k in TABLE_C_LAYER):
        return False
    return any(k in joined for k in TABLE_C_ITEM)


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
    table_a_headers: List[int] = []
    table_a_code_names: List[Dict] = []
    table_b_blocks: List[Dict] = []
    table_c_blocks: List[Dict] = []

    def collect_block(start: int, header_cells: List[str], kind: str) -> int:
        """从表头行 start(0-based)收集数据行,返回下一未处理行索引。kind ∈ {'B','C'}。"""
        disp_idx = next((k for k, c in enumerate(header_cells) if "处置" in c), None)
        note_idx = next((k for k, c in enumerate(header_cells) if "说明" in c), None)
        block = {"header_line": start + 1, "rows": []}
        j = start + 1
        # 跳过分隔行
        if j < n and "|" in lines[j] and is_separator_row(split_row(lines[j])):
            j += 1
        while j < n and "|" in lines[j]:
            rcells = split_row(lines[j])
            # ⚠️ 全空行既**不算分隔行**(见 is_separator_row 前置判)、也**不算数据行**:两个性质必须
            #    同时成立。只改前者会让 Word 转出的 `||||` 占位行变成数据行、每格报一条「为空」
            #    (真实 PRD 语料里有 35 处这种行)。
            if is_separator_row(rcells) or all(c.strip() == "" for c in rcells):
                j += 1
                continue
            disp = rcells[disp_idx].strip() if (disp_idx is not None and disp_idx < len(rcells)) else ""
            note = rcells[note_idx].strip() if (note_idx is not None and note_idx < len(rcells)) else ""
            disp_clean = re.sub(r"[*`>\s]", "", disp)
            if disp_clean == "" and note == "":
                j += 1
                continue
            if kind == "B":
                in_enum = disp_clean in DISPOSITION_ENUM
                is_non_default = disp_clean == "裁剪"  # 表 B 需带待产品确认的项 = 裁剪
            else:  # kind == "C"
                in_enum = is_table_c_disposition_in_enum(disp_clean)
                # 表 C 非实现项(裁剪/延期/改为X)须带待产品确认
                is_non_default = in_enum and not disp_clean.startswith("实现")
            row = {
                "line": j + 1,
                "disposition_raw": disp,
                "disposition": disp_clean,
                "in_enum": in_enum,
                "needs_confirm": is_non_default,
                "has_pending_confirm": bool(PENDING_CONFIRM_RE.search(note)),
            }
            block["rows"].append(row)
            j += 1
        block_target = table_b_blocks if kind == "B" else table_c_blocks
        block_target.append(block)
        return j

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if "|" not in line:
            i += 1
            continue
        cells = split_row(line)
        if is_table_a_header(cells):
            table_a_headers.append(i + 1)
            name_idx = next((k for k, c in enumerate(cells) if "字段语义名称" in c), None)
            j = i + 1
            if j < n and "|" in lines[j] and is_separator_row(split_row(lines[j])):
                j += 1
            while j < n and "|" in lines[j]:
                rcells = split_row(lines[j])
                # ⚠️ 全空行既**不算分隔行**(见 is_separator_row 前置判)、也**不算数据行**:两个性质必须
                #    同时成立。只改前者会让 Word 转出的 `||||` 占位行变成数据行、每格报一条「为空」
                #    (真实 PRD 语料里有 35 处这种行)。
                if is_separator_row(rcells) or all(c.strip() == "" for c in rcells):
                    j += 1
                    continue
                if name_idx is not None and name_idx < len(rcells):
                    nm = rcells[name_idx].strip()
                    if is_code_level_field_name(nm):
                        table_a_code_names.append({"line": j + 1, "value": nm})
                j += 1
            i = j
            continue
        if is_table_c_header(cells):
            i = collect_block(i, cells, "C")
            continue
        if is_table_b_header(cells):
            i = collect_block(i, cells, "B")
            continue
        i += 1

    # 汇总疑点(表 B)
    enum_violations = []
    cut_missing_confirm = []
    for blk in table_b_blocks:
        for r in blk["rows"]:
            if not r["in_enum"]:
                enum_violations.append({"line": r["line"], "value": r["disposition_raw"]})
            if r["needs_confirm"] and not r["has_pending_confirm"]:
                cut_missing_confirm.append({"line": r["line"]})

    # 汇总疑点(表 C)
    c_enum_violations = []
    c_nonimpl_missing_confirm = []
    for blk in table_c_blocks:
        for r in blk["rows"]:
            if not r["in_enum"]:
                c_enum_violations.append({"line": r["line"], "value": r["disposition_raw"]})
            if r["needs_confirm"] and not r["has_pending_confirm"]:
                c_nonimpl_missing_confirm.append({"line": r["line"], "value": r["disposition_raw"]})

    return {
        "file": rel,
        "table_a_count": len(table_a_headers),
        "table_a_header_lines": table_a_headers,
        "table_a_code_names": table_a_code_names,
        "table_b_count": len(table_b_blocks),
        "table_b_row_count": sum(len(b["rows"]) for b in table_b_blocks),
        "enum_violations": enum_violations,
        "cut_missing_confirm": cut_missing_confirm,
        "table_c_count": len(table_c_blocks),
        "table_c_row_count": sum(len(b["rows"]) for b in table_c_blocks),
        "c_enum_violations": c_enum_violations,
        "c_nonimpl_missing_confirm": c_nonimpl_missing_confirm,
    }


def render_text(results: List[Dict]) -> str:
    out: List[str] = []
    out.append("=== 需求字段去向登记 + 原型内容基线覆盖 结构性采集(维度 13,report-only) ===\n")
    total_a = sum(r.get("table_a_count", 0) for r in results)
    total_b = sum(r.get("table_b_count", 0) for r in results)
    total_c = sum(r.get("table_c_count", 0) for r in results)
    if total_a == 0 and total_b == 0 and total_c == 0:
        out.append("ℹ️ 未在任何 .md 中发现「表 A 需求字段清单」/「表 B 处置对照表」/「表 C 原型元素·操作逻辑对照表」表头。")
        out.append("   → 若该 PRD 含列表/表格/表单或任何原型可见元素/操作逻辑,QR Agent 应判维度 13 不通过(缺六·4 清单/表 C);")
        out.append("   → 若该 PRD 为无任何页面元素展示的纯说明类,维度 13 标 N/A。")
        return "\n".join(out)

    for r in results:
        if r.get("read_error"):
            out.append(f"[读取失败] {r['file']}: {r['read_error']}")
            continue
        if r["table_a_count"] == 0 and r["table_b_count"] == 0 and r.get("table_c_count", 0) == 0:
            continue
        out.append(f"📄 {r['file']}")
        out.append(f"   表 A 需求字段清单: {r['table_a_count']} 张 (表头行 {r['table_a_header_lines']})")
        out.append(f"   表 B 处置对照表: {r['table_b_count']} 张 / 共 {r['table_b_row_count']} 行")
        if r["enum_violations"]:
            out.append(f"   🟡 表 B 处置取值越界(应 ∈ {DISPOSITION_ENUM}): {len(r['enum_violations'])} 处")
            for v in r["enum_violations"]:
                out.append(f"      - L{v['line']}: 「{v['value']}」")
        if r["cut_missing_confirm"]:
            out.append(f"   🟡 表 B 裁剪项缺「待产品确认」: {len(r['cut_missing_confirm'])} 处")
            for v in r["cut_missing_confirm"]:
                out.append(f"      - L{v['line']}")
        if not r["enum_violations"] and not r["cut_missing_confirm"] and r["table_b_count"] > 0:
            out.append("   ✅ 表 B 处置取值均在枚举内,裁剪项均带「待产品确认」(结构性层面)")
        # 表 C
        out.append(f"   表 C 原型元素·操作逻辑对照表: {r.get('table_c_count', 0)} 张 / 共 {r.get('table_c_row_count', 0)} 行")
        c_enum = r.get("c_enum_violations", [])
        c_conf = r.get("c_nonimpl_missing_confirm", [])
        if c_enum:
            out.append(f"   🟡 表 C 处置取值越界(应 ∈ {DISPOSITION_ENUM_C},实现可带(默认)/改为X 为「改为…」前缀): {len(c_enum)} 处")
            for v in c_enum:
                out.append(f"      - L{v['line']}: 「{v['value']}」")
        if c_conf:
            out.append(f"   🟡 表 C 非实现项(裁剪/延期/改为X)缺「待产品确认」: {len(c_conf)} 处")
            for v in c_conf:
                out.append(f"      - L{v['line']}: 「{v['value']}」")
        if not c_enum and not c_conf and r.get("table_c_count", 0) > 0:
            out.append("   ✅ 表 C 处置取值均在枚举内,非实现项均带「待产品确认」(结构性层面)")
        # 表 A 字段语义名称：代码级标识（Critical，判错）
        a_code = r.get("table_a_code_names", [])
        if a_code:
            out.append(f"   🔴 表 A「字段语义名称」混入代码级标识(Critical,严禁): {len(a_code)} 处")
            for v in a_code:
                out.append(f"      - L{v['line']}: 「{v['value']}」")
            out.append("      → 表 A 是下游字段对账的单一信源,须改为纯业务语义中文名")
        elif r.get("table_a_count", 0) > 0:
            out.append("   ✅ 表 A「字段语义名称」未见代码级标识")
        out.append("")

    out.append("⚠️ 提示: 本脚本只做结构性存在性采集,无法判断:")
    out.append("   - 「原型/产品需求可见数据项是否 100% 以语义名登记」(表 A 漏列);")
    out.append("   - 「原型 code/(或上游 原型内容基线.md/DESIGN-MANIFEST.json)可见非字段元素/操作逻辑是否 100% 登记表 C」(表 C 漏项);")
    out.append("   - 「上游基线『实现』项是否都在 PRD 落地」。")
    out.append("   以上须由 QR Agent 读原型/上游基线逐项盘点后比对表 A/C 判定。")
    return "\n".join(out)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("path", type=Path, help="PRD 文件或目录")
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

    results = [scan_file(f, root) for f in md_files]

    # ⚠️ 读不出来 ≠ 没有违规:全部文件都读失败时判**环境错(2)**,绝不静默计为通过。
    #    (同 skill 的 check_technical_content.py 已做对,此处对齐;全仓退出码约定同款。)
    _read_errs = [r for r in results if isinstance(r, dict) and r.get("read_error")]
    if _read_errs and len(_read_errs) == len(results):
        for _r in _read_errs:
            print(f"错误: 无法读取 {_r['file']}: {_r['read_error']}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({"report_only": True, "files": results}, ensure_ascii=False, indent=2))
    else:
        print(render_text(results))

    # 主体 report-only（表 B/C 疑点交 Agent 判定），但表 A「字段语义名称混入代码级标识」
    # 是 SKILL 的 Critical 铁律且**可确定性机检**，故单独判错。
    # check_technical_content 的 R2 需「camelCase + 同行类型词」，而表 A 的「展示形态」列是中文形态词、
    # 命中不了，这条铁律只能由本脚本兜住。
    code_hits = sum(len(r.get("table_a_code_names", [])) for r in results)
    if code_hits:
        print(f"\n❌ 不通过: 表 A「字段语义名称」混入代码级标识 {code_hits} 处(Critical)",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
