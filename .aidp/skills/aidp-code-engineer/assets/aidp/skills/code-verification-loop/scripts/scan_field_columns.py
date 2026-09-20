#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""表格列 / 表单字段集合采集脚本
(对应 code-verification-loop 维度 4「字段/列对账」——视觉还原支柱① 字段一致性)

从前端代码里采集「列表表格列」与「表单字段」的集合,输出
`文件:行号 + 种类 + 列标签 + 字段名 + 代码片段`,供验收 Agent 与研发需求的
「需求字段 → 处置」对照表(上游单一信源)逐项比对,核查是否存在
**缺列 / 多列 / 改名 / 换序** 且未登记处置的差异。

⚠️ 对账主键:采集到的列 **label/title(展示名,即语义级)** 为对账主键,
   `prop/dataIndex` 仅作辅助参考;最终以**展示语义名**与上游「需求字段清单(语义)」
   (纯业务语义名,无代码级字段名)对账——而非用代码级 prop/dataIndex 比对。

⚠️ 重要:本脚本只负责"采集字段/列集合",**不判定是否违规**。
   是否违规需 Agent 拿采集清单(以展示语义名为主键)与「需求字段 → 处置」对照表逐项比对:
     - 实现可见列展示名与需求字段(语义)存在差异(缺/多/改名/换序)且对照表未登记 → 🔴 Critical(回修复团队 Agent1)
     - 差异已在对照表登记为「裁剪 / 前端计算还原 / 请第三方补」 → 不阻塞(合规放行)
     - 实现可见列展示名与需求字段(语义)一致 → ✅ 通过
   跨产物完整比对(尤其换序、改名的语义判断)脚本无法可靠完成,故退出码恒为 0(仅报告)。

采集来源(内联自包含,不跨 SKILL 引用):
   ① 模板标签列   —— <el-table-column> / <a-table-column> / <vxe-column> /
                     <vxe-table-column> / <n-data-table-column> / <table-column>
                     抽取 label/title(列标签) + prop/dataIndex/key/field(字段名)
   ② 模板表单项   —— <el-form-item> / <a-form-item> / <n-form-item> / <van-field> /
                     <form-item>  抽取 label/title(标签) + prop/name/field(字段名)
   ③ JS/TS 列定义 —— columns 数组对象字面量 { title|label|header: '..',
                     dataIndex|prop|key|field: '..' }(Ant Design / 自定义 columns)

扫描文件类型: .vue .ts .js .tsx .jsx .html
豁免目录:     node_modules .git dist build target out
              .next .nuxt vendor __pycache__ coverage .idea .vscode

退出码:
  0 = 始终(仅报告,命中与否都不判错;违规判定交给 Agent 比对「需求字段→处置」对照表)
  2 = 用法错误或目录不存在

用法:
  python scan_field_columns.py <前端目录>
  python scan_field_columns.py <前端目录> --json

JSON 输出:
  {"fields": [{"file":..,"line":..,"kind":..,"label":..,"field":..,"snippet":..}],
   "total": N,
   "by_kind": {"table-column": n1, "form-item": n2, "columns-array-item": n3}}
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

# 扫描的源码后缀
SCAN_SUFFIXES = {".vue", ".ts", ".js", ".tsx", ".jsx", ".html"}

# 豁免目录段
EXCLUDED_DIRS = {
    "node_modules", ".git", "dist", "build", "target", "out",
    ".next", ".nuxt", "vendor", "__pycache__", ".idea", ".vscode",
    "coverage", ".nyc_output", "tmp", ".cache",
}

# ── 模板标签:表格列 ────────────────────────────────────────────────
TABLE_COL_TAG = re.compile(
    r"<((?:el|a|vxe|n|s|t)-(?:table-)?column"
    r"|vxe-table-column|n-data-table-column|table-column)\b([^>]*?)/?>",
    re.IGNORECASE | re.DOTALL,
)
# ── 模板标签:表单项 ────────────────────────────────────────────────
FORM_ITEM_TAG = re.compile(
    r"<((?:el|a|n|s|t)-form-item|van-field|form-item)\b([^>]*?)/?>",
    re.IGNORECASE | re.DOTALL,
)

# 标签属性抽取(支持静态 attr="x" 与动态 :attr="'x'")
LABEL_ATTR = re.compile(
    r"""(?::|v-bind:)?\b(?:label|title|header)\s*=\s*["']([^"']*)["']""",
    re.IGNORECASE,
)
FIELD_ATTR = re.compile(
    r"""(?::|v-bind:)?\b(?:prop|data-?index|field|name|key)\s*=\s*["']([^"']*)["']""",
    re.IGNORECASE,
)

# ── JS/TS columns 数组对象字面量(取最内层 { ... },无嵌套花括号) ──────
JS_OBJECT = re.compile(r"\{[^{}]*\}", re.DOTALL)
JS_LABEL = re.compile(
    r"""\b(?:title|label|header)\s*:\s*["']([^"']+)["']""", re.IGNORECASE
)
JS_FIELD = re.compile(
    r"""\b(?:dataIndex|prop|field|key)\s*:\s*["']([^"']+)["']""", re.IGNORECASE
)


def is_excluded(path: Path, root: Path) -> bool:
    """仅基于 root 以内的相对路径判断排除,避免项目位于含排除名祖先目录时被整体跳过。"""
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = path
    parts = set(rel.parts)
    return bool(parts & EXCLUDED_DIRS)


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _first(pattern: re.Pattern, s: str) -> str:
    m = pattern.search(s)
    return m.group(1).strip() if m else ""


def scan_file(path: Path, root: Path) -> List[Dict]:
    hits: List[Dict] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return hits
    try:
        rel = str(path.relative_to(root))
    except ValueError:
        rel = str(path)

    def add(kind: str, label: str, field: str, offset: int, raw: str) -> None:
        hits.append({
            "file": rel,
            "line": _line_of(text, offset),
            "kind": kind,
            "label": label,
            "field": field,
            "snippet": " ".join(raw.split())[:200],
        })

    # ① 表格列标签
    for m in TABLE_COL_TAG.finditer(text):
        attrs = m.group(2) or ""
        label = _first(LABEL_ATTR, attrs)
        field = _first(FIELD_ATTR, attrs)
        if label or field:
            add("table-column", label, field, m.start(), m.group(0))

    # ② 表单项标签
    for m in FORM_ITEM_TAG.finditer(text):
        attrs = m.group(2) or ""
        label = _first(LABEL_ATTR, attrs)
        field = _first(FIELD_ATTR, attrs)
        if label or field:
            add("form-item", label, field, m.start(), m.group(0))

    # ③ JS/TS columns 数组对象(要求同时含标签键与字段键,过滤普通对象噪声)
    for m in JS_OBJECT.finditer(text):
        body = m.group(0)
        label = _first(JS_LABEL, body)
        field = _first(JS_FIELD, body)
        if label and field:
            add("columns-array-item", label, field, m.start(), body)

    return hits


def scan(root: Path) -> Dict:
    fields: List[Dict] = []
    scanned = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SCAN_SUFFIXES:
            continue
        if is_excluded(path, root):
            continue
        scanned += 1
        fields.extend(scan_file(path, root))
    # 稳定排序: 文件 → 行号
    fields.sort(key=lambda h: (h["file"], h["line"]))
    by_kind: Dict[str, int] = {}
    for h in fields:
        by_kind[h["kind"]] = by_kind.get(h["kind"], 0) + 1
        # ⚠️ 「0 命中」必须能与「0 文件被扫(路径给错)」区分开:早期二者都输出 total=0 → 报告照抄
    #    「✅ 无残留 / ✅ 一致」,而把 `src/` 误写成后端源码根这类**路径给错**属最常见形态,
    #    本脚本又正是 Critical 档的采集侧 → 假绿。故补 scanned_files,为 0 时置 skipped=true。
    return {"fields": fields, "total": len(fields), "by_kind": by_kind, "scanned_files": scanned, "skipped": scanned == 0}


def render_text(result: Dict) -> str:
    out: List[str] = []
    out.append("=== 表格列 / 表单字段采集 (维度 4: 字段/列对账·视觉还原支柱① 字段一致性) ===")
    total = result["total"]
    bk = result["by_kind"]
    out.append(
        f"\n采集字段/列: {total} 处"
        f"  (表格列 {bk.get('table-column', 0)} / 表单项 {bk.get('form-item', 0)}"
        f" / JS columns {bk.get('columns-array-item', 0)})"
    )
    if total == 0:
        out.append("\n✅ 未采集到表格列/表单字段(可能无列表/表单页,或使用了脚本未覆盖的写法,需 Agent 人工核对)。")
        return "\n".join(out)
    cur_file = None
    for h in result["fields"]:
        if h["file"] != cur_file:
            cur_file = h["file"]
            out.append(f"\n📄 {cur_file}")
        label = h["label"] or "(无标签)"
        field = h["field"] or "(无字段名)"
        out.append(f"  - L{h['line']:<5} [{h['kind']}]  标签={label}  字段={field}")
    out.append("\n⚠️ 对账主键为列 label/title(展示语义名),prop/dataIndex 仅辅助参考;")
    out.append("   以上仅为采集清单,是否违规由 Agent 以展示语义名与「需求字段 → 处置」对照表逐项比对决定:")
    out.append("   · 实现可见列展示名与需求字段(语义)存在差异(缺/多/改名/换序)且对照表未登记 → 🔴 Critical(回修复团队 Agent1)")
    out.append("   · 差异已在对照表登记为「裁剪/前端计算还原/请第三方补」     → 不阻塞(合规放行)")
    out.append("   · 实现可见列展示名与需求字段(语义)一致                     → ✅ 通过")
    out.append("   (对齐 AIDP 约定 4 字段裁剪三件套 / 约定 22 需求字段(语义)⟷接口字段漂移)")
    return "\n".join(out)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("root", type=Path, help="前端代码根目录")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出供 Agent 解析")
    args = parser.parse_args(argv)

    if not args.root.exists() or not args.root.is_dir():
        print(f"错误: 目录不存在或不是目录: {args.root}", file=sys.stderr)
        return 2

    result = scan(args.root)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_text(result))

    # 仅报告:命中与否都返回 0,违规判定交给 Agent 以展示语义名比对「需求字段 → 处置」对照表
    return 0


if __name__ == "__main__":
    sys.exit(main())
