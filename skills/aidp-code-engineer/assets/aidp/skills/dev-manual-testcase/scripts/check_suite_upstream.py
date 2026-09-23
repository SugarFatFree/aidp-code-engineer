#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试套件 + 用例步骤上游溯源覆盖率核验
对应 dev-manual-testcase 维度 13「上游溯源」+ 维度 16「自测方案对齐」grep 化硬核回检

实测发现自测用例**每个测试套件只有「功能模块」字段**,**没有 4 类来源标注**。
本脚本通过 grep 化覆盖率核验拦住此类违规。

检测项:
A. 每个 `## 套件 SUITE-NNN` 段头部 10 行内必须含 6 行:
  S0  自测方案章节 / 自测方案来源 (Critical,对应维度 16)
  S1  PRD 来源 / 研发需求来源 / 需求来源 (REQ-NNN)
  S2  原型来源 (如适用,纯后端套件可标 N/A)
  S3  详细设计来源
  S4  研发执行计划来源 / Sprint-NNN
  S5  承上启下 (前一套件 SUITE-NNN 完成的页面状态,本套件接着做什么;允许空)

B. 套件内每个用例步骤的"预期现象"行必须额外标注对应详细设计验收章节的精确锚点
  (如 `验收: docs/design/.../19_测试方案.md > §C-2.3`)
  注:入口流程 (Suite Setup, 步骤号 S1/S2…) 与清理 (Suite Teardown, T1/T2…) 行
  不计入验收锚点分母——它们是登录/导航/登出等流程步骤,不对应设计验收章节。

阈值:
  - S0+S1+S3 必填 100% 覆盖(自测方案 + PRD + 详细设计是测试用例的根基)
  - S2 ≥ 95%(纯后端套件可豁免)
  - S4 ≥ 95%(增量模式必填,全量模式可豁免标 N/A)
  - S5 不强制(辅助阅读)

使用:
  python check_suite_upstream.py <用例路径或目录>
  python check_suite_upstream.py <用例路径或目录> --json
  python check_suite_upstream.py <用例路径或目录> --check-step-acceptance
    # 启用用例步骤验收锚点核验(B 项)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List

# 套件段头识别(兼容多种约定,套件编号允许字母/数字/连字符混合):
#   ## 套件 SUITE-NNN: 标题
#   ## 测试套件 SUITE-NNN: 标题
#   ### 套件 SUITE-USER: 标题
#   ### 套件 SUITE-INC-01: 标题
#   ### 测试套件 TS-001: 标题
SUITE_HEADER_RE = re.compile(
    r"^#{2,4}\s+(?:测试)?套件\s+((?:SUITE|TS)-[A-Za-z0-9][A-Za-z0-9-]*)[:：]?\s*(.*)$",
    re.MULTILINE,
)

# 6 行来源标注关键词
S0_TEST_PLAN = re.compile(r"自测方案章节|自测方案来源|自测方案\s*[::]")
S1_PRD = re.compile(r"PRD\s*来源|研发需求来源|需求来源|关联\s*REQ|REQ-\d+")
S2_PROTOTYPE = re.compile(r"原型来源|原型文件|N/A.*纯后端|无\s*UI\s*关联")
S3_DESIGN = re.compile(r"详细设计来源|设计来源")
S4_PLAN = re.compile(r"研发执行计划来源|Sprint-\d+")
S5_CONTINUITY = re.compile(r"承上启下|承接前置|前一套件|续接")

# 链接合规度校验:套件头部来源行必须 markdown 链接 + 相对路径 + 文件后缀
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
ABSOLUTE_PATH_RE = re.compile(r"^(?:https?://|/|[A-Z]:[/\\]|~/)")
FILE_EXT_RE = re.compile(
    r"\.(md|markdown|jsx|tsx|html|htm|vue|js|ts|css|less|scss|sql|fig|sketch|xd|"
    r"png|jpg|jpeg|webp|gif|svg|docx|doc|pdf|json|yaml|yml|"
    r"java|kt|py|go|cs|rb|rs|swift|xlsx|xls|csv|excalidraw|drawio)(#|$|\?|\s)",
    re.IGNORECASE,
)


# 锚点等级排序: section(最精细) > line > component > html > none
_GRADE_ORDER = {"section": 4, "line": 3, "component": 2, "html": 1, "none": 0}
def _grade_rank(g: str) -> int:
    return _GRADE_ORDER.get(g, 0)


def check_link_quality(line: str) -> Dict:
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


HEAD_WINDOW = 10  # 套件头部 N 行内必须含 6 行来源标注


def find_suites(text: str) -> List[Dict]:
    """识别所有测试套件"""
    suites: List[Dict] = []
    for m in SUITE_HEADER_RE.finditer(text):
        suites.append({
            "id": m.group(1),
            "title": m.group(2).strip(),
            "header": m.group(0),
            "start": m.end(),
            "line": text[:m.start()].count("\n") + 1,
        })
    return suites


def check_suite_head(text: str, suite: Dict) -> Dict:
    """检查套件头部 N 行内是否含 6 行来源标注 + 链接合规度"""
    lines = text.splitlines()
    start_line = suite["line"]  # 1-indexed line of header
    # 取 header 后 N 行,但截止到下一个标题
    body_start = start_line  # 0-indexed of body = start_line(1-based) - 1 + 1 = start_line
    end = min(body_start + HEAD_WINDOW, len(lines))
    next_header_re = re.compile(r"^#{2,4}\s+")
    for i in range(body_start, end):
        if i < len(lines) and next_header_re.match(lines[i]):
            end = i
            break
    head_lines = lines[body_start:end]
    head_text = "\n".join(head_lines)

    # 链接合规度: S0/S1/S2/S3/S4 来源行必须含 markdown 链接(纯文本不合规)
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
        if not (S0_TEST_PLAN.search(line) or S1_PRD.search(line) or
                S2_PROTOTYPE.search(line) or S3_DESIGN.search(line) or S4_PLAN.search(line)):
            continue
        # 跳过 N/A / 无 / 纯后端 标记行
        if re.search(r"N/A|无\s*$|无\s*[)）]|纯后端", line):
            continue
        link_q = check_link_quality(line)
        if not link_q["has_markdown_link"]:
            link_violations.append({"line": body_start + i + 1, "snippet": line.strip()[:120],
                                    "issue": "缺 markdown 链接,使用纯文本路径"})
        elif not link_q["has_relative_path"]:
            link_violations.append({"line": body_start + i + 1, "snippet": line.strip()[:120],
                                    "issue": "链接使用绝对路径,应用相对路径"})
        elif not link_q["has_file_ext"]:
            link_violations.append({"line": body_start + i + 1, "snippet": line.strip()[:120],
                                    "issue": "链接未指向具体文件"})

    return {
        "s0_test_plan": bool(S0_TEST_PLAN.search(head_text)),
        "s1_prd": bool(S1_PRD.search(head_text)),
        "s2_prototype": bool(S2_PROTOTYPE.search(head_text)),
        "s3_design": bool(S3_DESIGN.search(head_text)),
        "s4_plan": bool(S4_PLAN.search(head_text)),
        "s5_continuity": bool(S5_CONTINUITY.search(head_text)),
        "link_violations": link_violations,
    }


def check_step_acceptance(text: str, suite: Dict, next_start: int) -> Dict:
    """检查套件内用例步骤的"预期现象"行是否含设计验收锚点

    返回 {steps_total, steps_with_acceptance}
    """
    body = text[suite["start"]:next_start]
    # 表格行: `| ... | 预期现象 | ... |` — 先查找表头
    # 简化判断:每条 markdown 表格数据行(非分隔符 / 非头) 视为一个步骤
    lines = body.splitlines()
    steps_total = 0
    steps_with_accept = 0

    in_table = False
    has_expected_col = False
    for line in lines:
        s = line.strip()
        if s.startswith("|") and "|" in s[1:]:
            if re.match(r"^\|\s*[:|\-\s]+\|", line):
                in_table = True
                continue
            if not in_table:
                # 表头
                if "预期现象" in line or "预期结果" in line:
                    has_expected_col = True
                continue
            # 表数据行
            if has_expected_col:
                # 排除套件入口流程 (Suite Setup, 步骤号 S1/S2…) 与套件清理
                # (Suite Teardown, 步骤号 T1/T2…):这类是登录/导航/登出等流程步骤,
                # 本就不对应详细设计的某个验收章节,不应计入"验收锚点覆盖率"分母,
                # 否则每个套件至少 Setup 2~5 步 + Teardown 1 步会把分母撑大、令 ≥95% 结构性不可达。
                first_cell = s.strip("|").split("|", 1)[0].strip()
                if re.match(r"^[STst]\d+$", first_cell):
                    continue
                steps_total += 1
                # 设计验收锚点关键词 + 必须是 markdown 链接
                # 关键词命中且含 markdown 链接才算合格
                has_keyword = re.search(r"docs/design.*\.md.*§|§[A-Z][-.．A-Za-z0-9]|验收\s*[::]", line)
                has_md_link = MARKDOWN_LINK_RE.search(line)
                if has_keyword and has_md_link:
                    steps_with_accept += 1
        else:
            in_table = False
            has_expected_col = False

    return {"steps_total": steps_total, "steps_with_accept": steps_with_accept}


def analyze_file(path: Path, check_steps: bool) -> Dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    suites = find_suites(text)
    if not suites:
        return {"file": str(path), "suites": 0, "results": []}

    results: List[Dict] = []
    for i, suite in enumerate(suites):
        head_check = check_suite_head(text, suite)
        next_start = suites[i + 1]["start"] if i + 1 < len(suites) else len(text)
        step_check = (check_step_acceptance(text, suite, next_start)
                      if check_steps else None)
        results.append({
            "id": suite["id"],
            "title": suite["title"],
            "line": suite["line"],
            **head_check,
            "step_check": step_check,
        })
    return {"file": str(path), "suites": len(suites), "results": results}


def main() -> int:
    ap = argparse.ArgumentParser(description="测试套件 + 用例步骤上游溯源核验")
    ap.add_argument("target", help="用例文件或目录")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--check-step-acceptance", action="store_true",
                    help="启用用例步骤'预期现象'验收锚点核验(B 项)")
    ap.add_argument("--threshold", type=float, default=0.95)
    args = ap.parse_args()

    target = Path(args.target)
    if not target.exists():
        print(f"❌ 路径不存在: {target}", file=sys.stderr)
        return 2

    md_files = [target] if target.is_file() else sorted(target.rglob("*.md"))
    # 目录模式排除非套件文档:00_索引 / 01_研发自测方案 / 98_跨系统验证清单 / 99_待澄清问题清单
    #   + aiauto-test 的 测试环境与账号 配置(均不含 `## 套件 SUITE-` 段)。
    # (显式排除与 check_case_stats.py / check_testcase_format.py 口径一致,避免误扫索引/方案/配置文件。
    #  单文件模式显式传入则不受此过滤影响。)
    def _non_suite(name):
        return (re.match(r"^00_", name) or re.match(r"^9[89]_", name)
                or "研发自测方案" in name or "测试环境与账号" in name)
    if not target.is_file():
        md_files = [f for f in md_files if not _non_suite(f.name)]
    if not md_files:
        print(f"⚠️  未发现 markdown 文件: {target}", file=sys.stderr)
        return 2

    aggregated: Dict = {
        "files": [],
        "total_suites": 0,
        "s0_hits": 0, "s1_hits": 0, "s2_hits": 0, "s3_hits": 0, "s4_hits": 0, "s5_hits": 0,
        "step_total": 0, "step_with_accept": 0,
        "total_link_violations": 0,
        "passed": True,
        "missing": [],
        "link_violations": [],
    }

    for f in md_files:
        result = analyze_file(f, args.check_step_acceptance)
        aggregated["files"].append(result)
        for r in result["results"]:
            aggregated["total_suites"] += 1
            for k, agg_key in [("s0_test_plan", "s0_hits"),
                               ("s1_prd", "s1_hits"), ("s2_prototype", "s2_hits"),
                               ("s3_design", "s3_hits"), ("s4_plan", "s4_hits"),
                               ("s5_continuity", "s5_hits")]:
                if r[k]:
                    aggregated[agg_key] += 1
            # 收集链接违规
            for lv in r.get("link_violations", []):
                aggregated["link_violations"].append({
                    "file": result["file"],
                    "suite": r["id"],
                    **lv,
                })
                aggregated["total_link_violations"] += 1
            # S0+S1+S3 必填,缺即记
            miss = []
            if not r["s0_test_plan"]:
                miss.append("S0_自测方案")
            if not r["s1_prd"]:
                miss.append("S1_PRD")
            if not r["s3_design"]:
                miss.append("S3_设计")
            if miss:
                aggregated["missing"].append({
                    "file": result["file"],
                    "line": r["line"],
                    "suite": r["id"],
                    "title": r["title"],
                    "missing": miss,
                })
            if r["step_check"]:
                aggregated["step_total"] += r["step_check"]["steps_total"]
                aggregated["step_with_accept"] += r["step_check"]["steps_with_accept"]

    n = aggregated["total_suites"]
    if n == 0:
        if args.json:
            print(json.dumps({"passed": True, "skipped": True,
                              "msg": "未发现测试套件段"}, ensure_ascii=False, indent=2))
        else:
            print("⚠️  未发现 `## 套件 SUITE-NNN` 段,跳过核验")
        return 0

    coverage = {
        "S0_自测方案": aggregated["s0_hits"] / n,
        "S1_PRD": aggregated["s1_hits"] / n,
        "S2_原型": aggregated["s2_hits"] / n,
        "S3_设计": aggregated["s3_hits"] / n,
        "S4_研发执行计划": aggregated["s4_hits"] / n,
        "S5_承上启下": aggregated["s5_hits"] / n,
    }
    aggregated["coverage"] = coverage

    # 判定: S0 + S1 + S3 必须 100%; S2 + S4 ≥ threshold; S5 不强制
    if (coverage["S0_自测方案"] < 1.0 or
            coverage["S1_PRD"] < 1.0 or coverage["S3_设计"] < 1.0):
        aggregated["passed"] = False
    if coverage["S2_原型"] < args.threshold or coverage["S4_研发执行计划"] < args.threshold:
        aggregated.setdefault("warnings", []).append(
            f"S2 / S4 覆盖率 < {args.threshold:.0%},建议补全"
        )

    # 步骤验收锚点检查
    step_coverage = None
    if args.check_step_acceptance and aggregated["step_total"] > 0:
        step_coverage = aggregated["step_with_accept"] / aggregated["step_total"]
        aggregated["step_acceptance_coverage"] = step_coverage
        if step_coverage < args.threshold:
            aggregated.setdefault("warnings", []).append(
                f"用例步骤验收锚点覆盖率 {step_coverage:.0%} < {args.threshold:.0%},QA 跑用例时双向追溯将失败"
            )

    # 链接违规即不通过
    if aggregated["total_link_violations"] > 0:
        aggregated["passed"] = False

    if args.json:
        print(json.dumps(aggregated, ensure_ascii=False, indent=2))
        return 0 if aggregated["passed"] else 1

    print(f"扫描 {len(aggregated['files'])} 个文件,共 {n} 个测试套件\n")
    print("套件头部覆盖率统计(S0/S1/S3 必须 100%,S2/S4 建议 ≥ 95%):")
    for k, v in coverage.items():
        if k.startswith(("S0", "S1", "S3")):
            marker = "✅" if v >= 1.0 else "❌"
        elif k == "S5_承上启下":
            marker = "⚠️ "
        else:
            marker = "✅" if v >= args.threshold else "❌"
        print(f"  {marker} {k}: {v:.1%}")

    if step_coverage is not None:
        marker = "✅" if step_coverage >= args.threshold else "⚠️ "
        print(f"\n用例步骤验收锚点覆盖率: {marker} {step_coverage:.1%}")

    if aggregated["total_link_violations"] > 0:
        print(f"\n链接合规度: ❌ {aggregated['total_link_violations']} 处违规"
              f"(必须 markdown 链接 [文本](相对路径#锚点),不允许纯文本/绝对路径)")
    else:
        print("\n链接合规度: ✅ 全部使用 markdown 链接 + 相对路径")

    if aggregated["passed"]:
        warnings = aggregated.get("warnings", [])
        if warnings:
            print(f"\n✅ 通过(S0/S1/S3 = 100%, 链接合规),但有 {len(warnings)} 条警告:")
            for w in warnings:
                print(f"  ⚠️  {w}")
        else:
            print(f"\n✅ 通过: S0/S1/S3 = 100%, S2/S4 ≥ {args.threshold:.0%}, 链接合规")
        return 0

    if aggregated["missing"]:
        print(f"\n❌ 不通过: S0 自测方案章节 / S1 PRD 来源 / S3 详细设计来源 必须 100% 覆盖\n")
        print(f"缺失套件(每段头部 {HEAD_WINDOW} 行内未找到必填来源):")
        for m in aggregated["missing"][:10]:
            print(f"  {m['file']}:L{m['line']}  [{m['suite']}]  缺{','.join(m['missing'])}  {m['title']}")
        if len(aggregated["missing"]) > 10:
            print(f"  ... 另 {len(aggregated['missing']) - 10} 处")
        # 提示修复方法
        print("\n  修复方法:")
        print("  - 缺 S0_自测方案 → 套件标题下方追加: > **自测方案章节:** [§X.Y 范围与通过准则](../<测试文档目录>/01_研发自测方案.md#X-Y)")
        print("  - 缺 S1_PRD     → 套件标题下方追加: > **PRD 来源:** [REQ-NNN 标题](../requirements/<version>/研发需求/xxx.md#REQ-NNN)")
        print("  - 缺 S3_详细设计 → 套件标题下方追加: > **详细设计来源:** [§X.Y 章节名](../docs/design/detail/<version>/xx.md#X-Y)")
    if aggregated["total_link_violations"] > 0:
        print(f"\n❌ 不通过: 链接违规 {aggregated['total_link_violations']} 处")
        for lv in aggregated["link_violations"][:10]:
            print(f"  {lv['file']}:L{lv['line']}  [{lv['suite']}]  [{lv['issue']}]  {lv['snippet']}")
        if len(aggregated["link_violations"]) > 10:
            print(f"  ... 另 {len(aggregated['link_violations']) - 10} 处")
    return 1


if __name__ == "__main__":
    sys.exit(main())
