#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
详细设计三类元素上游溯源覆盖率核验
对应 dev-logic-architect 维度 15「上游引用完整性」grep 化硬核回检

实测发现详细设计多文件拆分模式下,2 份核心子文档(数据库设计/接口设计)
完全 0 引用研发需求章节 + 0 引用原型文件;每个数据表/API 段头部完全没有
「PRD 来源 / 原型来源 / 关联 REQ」三件套。本脚本通过 grep 化覆盖率核验
按三类元素分别计算引用密度。

三类元素识别(按 markdown 标题/SQL 关键词):
  E1  数据表元素 — `## 表 XXX` / `## XXX 表` / `## biz_xxx` /
                   `CREATE TABLE` 紧前 2 行内的 `##` 标题
  E2  API 元素   — `## .*接口` / `## .*API` / `### POST/GET/PUT/DELETE /xxx`
  E3  功规点元素 — `## B\.1\.\d+` / `### B\.1\.\d+` / `## 功规点 \w+`

每个元素段头部 8 行内必须含:
  R1 研发需求来源 / PRD 来源 / 需求来源 (REQ-NNN 引用)
  R2 原型来源(纯后端表标 N/A,但字段不能省略)
  R3 字段规格对齐 / 接口契约对齐(标注引用研发需求字段表行号)

阈值: 每类元素覆盖率 < 95% 即不通过

使用:
  python check_upstream_reference.py <设计目录或文件>
  python check_upstream_reference.py <设计目录或文件> --json
  python check_upstream_reference.py <设计目录或文件> --threshold 0.95
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# 三类元素识别正则
# ⚠️ 标题层级一律 #{2,6}，**不要锚死 ^##**：
#    本 SKILL 自家 B.2 接口模板是 `### [接口编号] 接口名称` + `- **Method:**`，A.3 数据表小节在
#    `#### A.3 数据定义` 之下自然落 `#####`。锚死 H2 时三类元素全部「未发现，跳过」，脚本随即
#    打印「✅ 通过」exit 0 —— 维度 15（Critical）对照模板产出的设计**恒判通过**。
#    同一内容仅把标题降到 H2 就报 0% 覆盖率，是纯形态导致的假绿灯。
TABLE_HEADER_RE = re.compile(
    r"^#{2,6}\s+(?:表\s*[:：]?\s*)?([a-z][a-z0-9_]+|biz_\w+|sys_\w+|t_\w+)\s+表",
    re.IGNORECASE,
)
TABLE_HEADER_SIMPLE_RE = re.compile(
    r"^#{2,6}\s+(?:数据表|表)\s*[:：]?\s*\S+",
)
TABLE_HEADER_BACKTICK_RE = re.compile(r"^#{2,6}\s+`?(biz_\w+|sys_\w+|t_\w+)`?\b")
# CREATE TABLE 兜底：docstring 早就声称支持，实际 find_elements() 里从来没有这条扫描
TABLE_DDL_RE = re.compile(r"^\s*CREATE\s+TABLE\s+`?(\w+)`?", re.IGNORECASE)
API_HEADER_RE = re.compile(
    r"^#{2,6}\s+(?:API|接口|.*接口|.*API).*$|^#{2,6}\s+\b(GET|POST|PUT|DELETE|PATCH)\s+/",
    re.IGNORECASE,
)
# 与 check_error_contract.py 同源的接口识别信号：模板用的是 `- **Method:**` 而非裸 METHOD /path
# 只认 Method，**不认 Path**：二者在模板里成对出现，都认会让同一接口计两次
API_METHOD_LINE_RE = re.compile(r"^\s*[-*]?\s*\*\*(?:Method|接口路径)\s*[:：]?\*\*", re.IGNORECASE)
FEATURE_HEADER_RE = re.compile(
    r"^#{2,6}\s+(?:B\.1\.\d+(?:\.\d+)*|功规点\s+\w+)",
)

# 必填来源关键词
R1_REQ_SOURCE = re.compile(
    r"研发需求来源|PRD\s*来源|需求来源|功规点来源|REQ-\d+|关联\s*REQ"
)
R2_PROTOTYPE_SOURCE = re.compile(
    r"原型(?:来源|文件|路径|引用)"
)
# R2 豁免关键词:纯后端可标 N/A
R2_BACKEND_ONLY = re.compile(
    r"N/A.*纯后端|纯后端.*N/A|无\s*UI\s*关联"
)
# R3 字段对齐 / 接口契约对齐(数据表+API 必填,功规点不强制)
R3_ALIGN = re.compile(
    r"字段规格对齐|接口契约对齐|字段对齐|对齐\s*[::]?\s*.*L\d+|引用.*字段表\s*L\d+"
)

# 链接合规度校验(对应"引用必须用 markdown 可点击链接 + 相对路径"要求)
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
ABSOLUTE_PATH_RE = re.compile(r"^(?:https?://|/|[A-Z]:[/\\]|~/)")
FILE_EXT_RE = re.compile(
    r"\.(md|markdown|jsx|tsx|html|htm|vue|js|ts|css|less|scss|sql|fig|sketch|xd|"
    r"png|jpg|jpeg|webp|gif|svg|docx|doc|pdf|json|yaml|yml|"
    r"java|kt|py|go|cs|rb|rs|swift|xlsx|xls|csv|excalidraw|drawio)(#|$|\?|\s)",
    re.IGNORECASE,
)

HEAD_WINDOW = 8  # 段头部 N 行内必须含来源标注

# 锚点等级排序: section(最精细) > line > component > html > none
_GRADE_ORDER = {"section": 4, "line": 3, "component": 2, "html": 1, "none": 0}
def _grade_rank(g: str) -> int:
    return _GRADE_ORDER.get(g, 0)


def check_link_quality(line: str) -> Dict:
    """检查行内 markdown 链接合规度

    返回 has_markdown_link / has_relative_path / has_file_ext / has_anchor / anchor_grade
    """
    matches = MARKDOWN_LINK_RE.findall(line)
    if not matches:
        return {"has_markdown_link": False, "has_relative_path": False,
                "has_file_ext": False, "has_anchor": False, "anchor_grade": "none"}
    has_relative = all(not ABSOLUTE_PATH_RE.match(p.strip()) for p in matches)
    has_ext = any(FILE_EXT_RE.search(p) for p in matches)
    has_anchor = any("#" in p for p in matches)
    grade = "none"
    for p in matches:
        if "#" not in p:
            continue
        anchor = p.split("#", 1)[1]
        if re.search(r"L\d+", anchor):
            grade = max(grade, "line", key=_grade_rank); continue
        if re.search(r"^[一二三四五六七八九十0-9]+[-\.·]", anchor) or re.search(r"§|REQ-|FR-|B-\d|A-\d|C-\d", anchor):
            grade = max(grade, "section", key=_grade_rank); continue
        if re.search(r"<\w+[A-Z]\w*>|^[A-Z]\w*Page$|^[A-Z]\w*Component$", anchor):
            grade = max(grade, "component", key=_grade_rank); continue
        if anchor:
            grade = max(grade, "html", key=_grade_rank)
    return {"has_markdown_link": True, "has_relative_path": has_relative,
            "has_file_ext": has_ext, "has_anchor": has_anchor, "anchor_grade": grade}


def find_elements(text: str) -> List[Dict]:
    """识别三类元素的所有段"""
    elements: List[Dict] = []
    lines = text.splitlines()
    # ⚠️ **DDL / Method 行只作"无标题时的兜底"，绝不与标题并列计数**。
    #    放宽标题层级时同时加了 TABLE_DDL_RE 与 API_METHOD_LINE_RE 三个信号源却没去重，于是
    #    一张表被计 2 次（`## biz_user 表` + `CREATE TABLE biz_user (`）、
    #    一个接口被计 3 次（`### GET /x` + `- **Method:**` + `- **Path:**`），
    #    而多出来的那些"元素"**物理上无处安放溯源块**——总不能把 4 行引用写进 `CREATE TABLE (` 里。
    #    结果是照本 SKILL 自家模板写的合规设计必判死、且不可修，QR 3 轮不过直接卡死流水线。
    #    规则：同一「标题段」内，标题已产生过该类元素时，后续 DDL/Method 行不再重复建元素。
    seen_kind_in_section = set()
    for i, line in enumerate(lines):
        kind: Optional[str] = None
        is_fallback = False
        if line.startswith("#"):
            seen_kind_in_section.clear()   # 进入新标题段
        if (TABLE_HEADER_RE.match(line) or
                TABLE_HEADER_SIMPLE_RE.match(line) or
                TABLE_HEADER_BACKTICK_RE.match(line)):
            kind = "E1_数据表"
        elif TABLE_DDL_RE.match(line):
            kind, is_fallback = "E1_数据表", True
        elif API_HEADER_RE.match(line):
            kind = "E2_API"
        elif API_METHOD_LINE_RE.match(line):
            kind, is_fallback = "E2_API", True
        elif FEATURE_HEADER_RE.match(line):
            kind = "E3_功规点"
        if kind and is_fallback and kind in seen_kind_in_section:
            continue    # 本段标题已建过同类元素，兜底信号不重复计
        if kind:
            seen_kind_in_section.add(kind)
            elements.append({
                "kind": kind,
                "line": i + 1,
                "header": line,
                "body_start": i + 1,
            })
    return elements


def check_element_head(text: str, element: Dict) -> Dict:
    """检查段头部 N 行内是否含 3 类来源标注

    窗口截止到下一个 `^##` 或 `^###` 标题之前,避免穿透到下一个元素的来源标注。
    """
    lines = text.splitlines()
    start = element["body_start"]
    end = min(start + HEAD_WINDOW, len(lines))
    # 截止到下一个标题前
    # ⚠️ 必须与元素识别**同宽**（`#{2,6}`）：元素放宽到 H6 而终止符仍停在 H4 时，
    #    H5/H6 标题不终止窗口，前一个元素会直接读到后一个元素的溯源块 ——
    #    实测两张 `##### xx 表`、第一张零溯源，却被判 100% 覆盖率（Critical 维度上的漏报）。
    next_header_re = re.compile(r"^#{2,6}\s+")
    for i in range(start, end):
        if i < len(lines) and next_header_re.match(lines[i]):
            end = i
            break
    head_lines = lines[start:end]
    head_text = "\n".join(head_lines)

    r1_req = bool(R1_REQ_SOURCE.search(head_text))
    r2_proto = bool(R2_PROTOTYPE_SOURCE.search(head_text))
    r2_backend_na = bool(R2_BACKEND_ONLY.search(head_text))
    r3_align = bool(R3_ALIGN.search(head_text))

    # 链接合规度: 命中的来源行必须含 markdown 链接(纯文本路径不合规)
    # 对 ❌/反例/代码块内行豁免
    link_violations: List[Dict] = []
    counterexample_remaining = 0
    in_code_block = False
    for i, line in enumerate(head_lines):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        if re.search(r"❌|反例|错误示例|严禁的格式|严禁示例", line):
            counterexample_remaining = 3
            continue
        if counterexample_remaining > 0:
            counterexample_remaining -= 1
            continue
        if not (R1_REQ_SOURCE.search(line) or R2_PROTOTYPE_SOURCE.search(line) or
                R3_ALIGN.search(line)):
            continue
        # 跳过 N/A / 无 / 纯后端 标记行
        if re.search(r"N/A|无\s*$|无\s*[)）]|纯后端", line):
            continue
        link_q = check_link_quality(line)
        if not link_q["has_markdown_link"]:
            link_violations.append({"line": start + i + 1, "snippet": line.strip()[:120],
                                    "issue": "缺 markdown 链接,使用纯文本路径"})
        elif not link_q["has_relative_path"]:
            link_violations.append({"line": start + i + 1, "snippet": line.strip()[:120],
                                    "issue": "链接使用绝对路径,应用相对路径"})
        elif not link_q["has_file_ext"]:
            link_violations.append({"line": start + i + 1, "snippet": line.strip()[:120],
                                    "issue": "链接未指向具体文件(缺 .md/.jsx/.html 等后缀)"})

    return {
        "r1_req": r1_req,
        "r2_proto_or_na": r2_proto or r2_backend_na,
        "r2_backend_na": r2_backend_na,
        "r3_align": r3_align,
        "link_violations": link_violations,
    }


def analyze_file(path: Path) -> Dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    elements = find_elements(text)
    if not elements:
        return {"file": str(path), "elements": 0, "by_kind": {}, "missing": [],
                "link_violations": []}

    by_kind: Dict[str, Dict] = {
        "E1_数据表": {"total": 0, "r1_hits": 0, "r2_hits": 0, "r3_hits": 0},
        "E2_API": {"total": 0, "r1_hits": 0, "r2_hits": 0, "r3_hits": 0},
        "E3_功规点": {"total": 0, "r1_hits": 0, "r2_hits": 0, "r3_hits": 0},
    }
    missing: List[Dict] = []
    all_link_violations: List[Dict] = []

    for elem in elements:
        kind = elem["kind"]
        by_kind[kind]["total"] += 1
        result = check_element_head(text, elem)
        if result["r1_req"]:
            by_kind[kind]["r1_hits"] += 1
        if result["r2_proto_or_na"]:
            by_kind[kind]["r2_hits"] += 1
        if result["r3_align"]:
            by_kind[kind]["r3_hits"] += 1

        # 必填: R1 研发需求 + R2 原型/或 N/A
        # R3 字段对齐对 E1/E2 必填,E3 功规点不强制
        miss_tags: List[str] = []
        if not result["r1_req"]:
            miss_tags.append("R1_研发需求")
        if not result["r2_proto_or_na"]:
            miss_tags.append("R2_原型")
        if kind in ("E1_数据表", "E2_API") and not result["r3_align"]:
            miss_tags.append("R3_字段对齐")
        if miss_tags:
            missing.append({
                "kind": kind,
                "header": elem["header"],
                "line": elem["line"],
                "missing": miss_tags,
            })
        # 聚合链接违规
        for lv in result.get("link_violations", []):
            all_link_violations.append({
                "kind": kind,
                "header": elem["header"],
                **lv,
            })

    return {
        "file": str(path),
        "elements": len(elements),
        "by_kind": by_kind,
        "missing": missing,
        "link_violations": all_link_violations,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="详细设计三类元素上游溯源覆盖率核验")
    ap.add_argument("target", help="设计文档文件或目录")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--threshold", type=float, default=0.95,
                    help="覆盖率阈值(默认 0.95)")
    args = ap.parse_args()

    target = Path(args.target)
    if not target.exists():
        print(f"❌ 路径不存在: {target}", file=sys.stderr)
        return 2

    md_files = [target] if target.is_file() else sorted(target.rglob("*.md"))
    if not md_files:
        print(f"⚠️  未发现 markdown 文件: {target}", file=sys.stderr)
        return 2

    aggregated: Dict = {
        "files": [],
        "by_kind": {
            "E1_数据表": {"total": 0, "r1_hits": 0, "r2_hits": 0, "r3_hits": 0},
            "E2_API": {"total": 0, "r1_hits": 0, "r2_hits": 0, "r3_hits": 0},
            "E3_功规点": {"total": 0, "r1_hits": 0, "r2_hits": 0, "r3_hits": 0},
        },
        "total_link_violations": 0,
        "passed": True,
    }

    for f in md_files:
        # 跳过待澄清/总览类文件
        if "99_" in f.name or f.name.startswith("00_"):
            continue
        result = analyze_file(f)
        aggregated["files"].append(result)
        for k, stat in result["by_kind"].items():
            for key in ("total", "r1_hits", "r2_hits", "r3_hits"):
                aggregated["by_kind"][k][key] += stat[key]
        aggregated["total_link_violations"] += len(result.get("link_violations", []))

    # 计算覆盖率
    coverage_summary: Dict = {}
    for kind, stat in aggregated["by_kind"].items():
        total = stat["total"]
        if total == 0:
            coverage_summary[kind] = {"total": 0, "skipped": True}
            continue
        cov = {
            "total": total,
            "R1_研发需求来源": stat["r1_hits"] / total,
            "R2_原型来源": stat["r2_hits"] / total,
            "R3_字段对齐": stat["r3_hits"] / total,
        }
        coverage_summary[kind] = cov

        # E1/E2: R1 + R2 必填,R3 必填
        # E3: R1 + R2 必填,R3 不强制
        if kind == "E3_功规点":
            req_keys = ("R1_研发需求来源", "R2_原型来源")
        else:
            req_keys = ("R1_研发需求来源", "R2_原型来源", "R3_字段对齐")
        for k in req_keys:
            if cov[k] < args.threshold:
                aggregated["passed"] = False

    aggregated["coverage"] = coverage_summary

    # 链接违规即不通过
    if aggregated["total_link_violations"] > 0:
        aggregated["passed"] = False

    # ⚠️ 三类元素一个都没识别到 ≠ 通过：那是「没扫到东西」，不是「扫过且干净」。
    #    按全仓约定第 3 条输出可区分标记，避免调用方把空转读成通过。
    all_skipped = all(c.get("skipped") for c in coverage_summary.values()) if coverage_summary else True
    aggregated["skipped"] = all_skipped

    if args.json:
        print(json.dumps(aggregated, ensure_ascii=False, indent=2))
        return 0 if aggregated["passed"] else 1

    print(f"扫描 {len(aggregated['files'])} 个文件\n")
    print("三类元素覆盖率统计(阈值 {:.0%}):\n".format(args.threshold))
    for kind, cov in coverage_summary.items():
        if cov.get("skipped"):
            print(f"  [{kind}] 未发现该类元素,跳过")
            continue
        print(f"  [{kind}] (共 {cov['total']} 个)")
        for key in ("R1_研发需求来源", "R2_原型来源", "R3_字段对齐"):
            v = cov[key]
            if kind == "E3_功规点" and key == "R3_字段对齐":
                marker = "⚠️ "  # 功规点 R3 不强制
            else:
                marker = "✅" if v >= args.threshold else "❌"
            print(f"    {marker} {key}: {v:.1%}")
        print()

    if aggregated["total_link_violations"] > 0:
        print(f"\n链接合规度: ❌ {aggregated['total_link_violations']} 处违规"
              f"(必须 markdown 链接 [文本](相对路径#锚点),不允许纯文本/绝对路径)")
    else:
        print("\n链接合规度: ✅ 全部使用 markdown 链接 + 相对路径")

    if not aggregated["passed"]:
        any_coverage_fail = any(
            cov.get("R1_研发需求来源", 1) < args.threshold or
            cov.get("R2_原型来源", 1) < args.threshold or
            (kind != "E3_功规点" and cov.get("R3_字段对齐", 1) < args.threshold)
            for kind, cov in coverage_summary.items() if not cov.get("skipped")
        )
        if any_coverage_fail:
            print(f"\n❌ 不通过: 三类元素中至少一类的必填项覆盖率 < {args.threshold:.0%}\n")
            print("缺失元素(每段头部 {} 行内未找到必填来源):".format(HEAD_WINDOW))
            for r in aggregated["files"]:
                for m in r["missing"][:5]:
                    print(f"  {r['file']}:L{m['line']}  [{m['kind']}]  缺{','.join(m['missing'])}")
                    print(f"    {m['header']}")
                if len(r["missing"]) > 5:
                    print(f"    ... 另 {len(r['missing']) - 5} 处")
        if aggregated["total_link_violations"] > 0:
            print(f"\n❌ 不通过: 链接违规 {aggregated['total_link_violations']} 处")
            for r in aggregated["files"]:
                for lv in r.get("link_violations", [])[:5]:
                    print(f"  {r['file']}:L{lv['line']}  [{lv['issue']}]  {lv['snippet']}")
                if len(r.get("link_violations", [])) > 5:
                    print(f"    ... 另 {len(r['link_violations']) - 5} 处")
        return 1

    if all_skipped:
        print("⚠️ 未识别到任何数据表/API/功规点元素 —— 本次**未做实质核验**,不等于通过。")
        print("   请确认设计文档标题形态,或转 QR 子 Agent 人工核验维度 15。")
        return 0
    print(f"✅ 通过: 三类元素覆盖率均 ≥ {args.threshold:.0%}, 链接合规")
    return 0


if __name__ == "__main__":
    sys.exit(main())
