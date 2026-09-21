#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
REQ/功规点段头部上游溯源覆盖率核验
对应 ux-logic-extractor 维度 5「数据一致性与上游溯源」grep 化硬核回检

实测发现 PRD 多文件拆分模式下,功规点段(`### REQ-NNN` 或 `#### 5.{N} 页面名`)
的头部完全没有 PRD 来源 / 原型来源 标注,9 份分册 6 份"原型引用关键词命中 = 0"。
本脚本通过 grep 化覆盖率核验拦住此类违规。

检测项(每段头部 8 行内必须含 4 类来源标注):
  H1  PRD 来源 / 产品需求文档来源 / 原型文件
  H2  原型来源 / 原型文件 / 原型路由
  H3  高保真来源 / 高保真设计 (如有)
  H4  关联功规点 / 关联 REQ / 依赖 / 参考本文档(如有)

覆盖率阈值:
  - 强制要求 H1 + H2 必须各 100%(原型必填,即便原型仅 mock 数据展示也要标),不足即不通过
  - H3 高保真 / H4 关联功规点 建议 ≥ 95%(阈值可 --threshold 调整),不足仅告警不阻塞
  - 链接违规(非 markdown 链接 / 绝对路径 / 缺文件后缀)即不通过 —— 仅对 H1/H2/H3
    三类"外部文件来源"行强制;H4 关联功规点是本文档内部交叉引用(裸 #锚点 / "参考本文档 > 五-N"),
    天然无外部文件后缀,不参与 file-link 强制校验

使用:
  python check_req_upstream.py <PRD路径或目录>
  python check_req_upstream.py <PRD路径或目录> --json
  python check_req_upstream.py <PRD路径或目录> --threshold 0.95

退出码: 0 = 通过 / 1 = 不通过 / 2 = 路径错误
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List

# 段头识别 — 兼容两种约定:
# 1. `### REQ-NNN: 标题`(新约定)
# 2. `#### 5.N 标题` / `#### 5.N. 标题`(老约定,五、页面交互明细)
# 3. `### 五-N 标题` / `### 五·N 标题`(章节编号)
# ⚠️ 段头形态漏一种就整档静默跳过：只认 `### REQ-NNN` / `### 五-N` / `#### 5.N` 时，
#    生成的 PRD 标题层级一漂到 `### 5.1`（三井号 + 阿拉伯数字，实际最常见），
#    三条都不匹配 → 打印「未发现功规点段,跳过核验」exit 0 —— 维度 5（Critical、不可豁免）
#    对整份 PRD 零覆盖。故补第 4 条。
SECTION_PATTERNS = [
    re.compile(r"^###\s+REQ-(\d+)[:：]?\s*(.*)$"),
    re.compile(r"^###\s+(?:五[-·\.](\d+(?:\.\d+)*))\s*[:：]?\s*(.*)$"),
    re.compile(r"^####\s+(?:五[-·\.])?(\d+(?:\.\d+)*)\s+(.*)$"),
    re.compile(r"^###\s+(\d+(?:\.\d+)+)\s+(.*)$"),
]

# 4 类来源标注关键词(在段头部 N 行内 grep)
# H1: PRD/产品需求文档
H1_PRD_SOURCE = re.compile(r"PRD\s*来源|产品需求文档来源|研发需求来源|需求来源|产品文档来源")
# H2: 原型来源
H2_PROTOTYPE_SOURCE = re.compile(r"原型(?:文件|来源|路径)")
# H3: 高保真来源(可选)
H3_MOCKUP_SOURCE = re.compile(r"高保真(?:设计|来源|文件)")
# H4: 关联功规点 / 关联 REQ / 依赖
H4_REL_REQ = re.compile(r"关联功规点|关联\s*REQ|依赖|关联需求|前置条件")

# 链接合规度校验:行内必须含 markdown 链接 [文本](相对路径#锚点)
# 1. 必须有 [...](...) 链接语法
# 2. 链接路径必须是相对路径(不以 http://、https://、/、C:\ 等开头)
# 3. 链接路径必须指向文件类型(.md/.jsx/.tsx/.html/.vue/.js/.ts/.fig/.png/.docx 等)
MARKDOWN_LINK_RE = re.compile(
    r"\[[^\]]+\]\(([^)]+)\)"
)
# 绝对路径模式(违规)
ABSOLUTE_PATH_RE = re.compile(r"^(?:https?://|/|[A-Z]:[/\\]|~/)")
# 文件后缀(链接路径必须含至少一种)
FILE_EXT_RE = re.compile(
    r"\.(md|markdown|jsx|tsx|html|htm|vue|js|ts|css|less|scss|sql|fig|sketch|xd|"
    r"png|jpg|jpeg|webp|gif|svg|docx|doc|pdf|json|yaml|yml|"
    r"java|kt|py|go|cs|rb|rs|swift|xlsx|xls|csv|excalidraw|drawio)(#|$|\?|\s)",
    re.IGNORECASE,
)

HEAD_WINDOW = 8  # 段头部 N 行内必须含来源标注


def check_link_quality(line: str) -> Dict:
    """检查行内 markdown 链接合规度

    返回:
      has_markdown_link: 是否含 [text](path) 链接
      has_relative_path: 链接路径是否为相对路径
      has_file_ext: 链接路径是否含文件后缀
      has_anchor: 链接是否含 #锚点(精细引用)
      anchor_grade: section / line / component / html / none(精细等级)
    """
    matches = MARKDOWN_LINK_RE.findall(line)
    if not matches:
        return {
            "has_markdown_link": False,
            "has_relative_path": False,
            "has_file_ext": False,
            "has_anchor": False,
            "anchor_grade": "none",
        }
    # 取首个链接的 url 部分判定
    paths = matches  # group(1) 列表
    has_relative = all(not ABSOLUTE_PATH_RE.match(p.strip()) for p in paths)
    has_ext = any(FILE_EXT_RE.search(p) for p in paths)
    has_anchor = any("#" in p for p in paths)
    # 锚点精细等级判定: section > line > component > html > none
    grade = "none"
    for p in paths:
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
    return {
        "has_markdown_link": True,
        "has_relative_path": has_relative,
        "has_file_ext": has_ext,
        "has_anchor": has_anchor,
        "anchor_grade": grade,
    }


# 锚点等级排序: section(最精细) > line > component > html > none
_GRADE_ORDER = {"section": 4, "line": 3, "component": 2, "html": 1, "none": 0}
def _grade_rank(g: str) -> int:
    return _GRADE_ORDER.get(g, 0)


def find_sections(text: str) -> List[Dict]:
    """识别所有功规点段"""
    sections: List[Dict] = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        for pat in SECTION_PATTERNS:
            m = pat.match(line)
            if m:
                sections.append({
                    "line": i + 1,
                    "id": m.group(1),
                    "title": m.group(2).strip() if m.lastindex >= 2 else "",
                    "header": line,
                    "body_start": i + 1,
                })
                break
    return sections


def check_section_head(text: str, section: Dict) -> Dict:
    """检查段头部 N 行内是否含 4 类来源标注 + 链接合规度

    窗口截止到下一个 `^##` 或 `^###` 或 `^####` 标题之前,
    避免穿透到下一个元素的来源标注。
    """
    lines = text.splitlines()
    start = section["body_start"]
    end = min(start + HEAD_WINDOW, len(lines))
    next_header_re = re.compile(r"^#{2,4}\s+")
    for i in range(start, end):
        if i < len(lines) and next_header_re.match(lines[i]):
            end = i
            break
    head_lines = lines[start:end]
    head_text = "\n".join(head_lines)

    # 4 类来源命中
    h1 = bool(H1_PRD_SOURCE.search(head_text))
    h2 = bool(H2_PROTOTYPE_SOURCE.search(head_text))
    h3 = bool(H3_MOCKUP_SOURCE.search(head_text))
    h4 = bool(H4_REL_REQ.search(head_text))

    # 链接合规度: 命中的来源行必须含 markdown 链接(纯文本路径不合规)
    # 从段头每行检测,对 ❌/反例/代码块内行豁免
    link_violations: List[Dict] = []
    counterexample_remaining = 0  # ❌/反例 标记后的豁免窗口
    in_code_block = False
    for i, line in enumerate(head_lines):
        stripped = line.strip()
        # 代码块围栏切换
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        # ❌/反例/错误示例 标记触发豁免窗口(后续 3 行)
        if re.search(r"❌|反例|错误示例|严禁的格式|严禁示例", line):
            counterexample_remaining = 3
            continue
        if counterexample_remaining > 0:
            counterexample_remaining -= 1
            continue
        # 仅对 H1 PRD / H2 原型 / H3 高保真 三类"外部文件来源"行强制 file-link 格式。
        # H4 关联功规点/依赖 是本文档内部/可选交叉引用 —— SKILL.md 允许其写成裸 #锚点
        # (如 `[REQ-005](#req-005)`,指向同文档 REQ)或"参考本文档 > 五-N"这类内部引用,
        # 天然无外部文件后缀,不应被"缺文件后缀"误判。故内部 H4 行不参与 file-link 强制校验。
        is_external_source = (H1_PRD_SOURCE.search(line) or H2_PROTOTYPE_SOURCE.search(line)
                              or H3_MOCKUP_SOURCE.search(line))
        if not is_external_source:
            continue
        # 跳过 N/A / 无 标记行,以及模式 A「逆向无产品文档」声明行
        # (模式 A 仅有原型、无产品需求文档,SKILL.md 规定 H1 PRD 来源行写
        #  "模式 A 逆向无产品文档",此为合法占位、非纯文本路径引用,豁免链接合规度检查)
        if re.search(r"N/A|无\s*$|无\s*[)）]|纯后端|模式\s*A\s*逆向|逆向无产品文档|无产品文档|无产品需求文档", line):
            continue
        link_q = check_link_quality(line)
        if not link_q["has_markdown_link"]:
            link_violations.append({"line": start + i + 1, "snippet": line.strip()[:120],
                                    "issue": "缺 markdown 链接,使用纯文本路径"})
        elif not link_q["has_relative_path"]:
            link_violations.append({"line": start + i + 1, "snippet": line.strip()[:120],
                                    "issue": "链接使用绝对路径(http:// / /home / C:\\),应用相对路径"})
        elif not link_q["has_file_ext"]:
            link_violations.append({"line": start + i + 1, "snippet": line.strip()[:120],
                                    "issue": "链接未指向具体文件(缺 .md/.jsx/.html 等后缀)"})

    return {
        "h1_prd": h1,
        "h2_prototype": h2,
        "h3_mockup": h3,
        "h4_rel_req": h4,
        "link_violations": link_violations,
    }


def analyze_file(path: Path) -> Dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    sections = find_sections(text)
    if not sections:
        return {"file": str(path), "sections": 0, "coverage": {}, "missing": [],
                "link_violations": []}

    h1_hits = h2_hits = h3_hits = h4_hits = 0
    missing: List[Dict] = []
    all_link_violations: List[Dict] = []
    for sec in sections:
        result = check_section_head(text, sec)
        if result["h1_prd"]:
            h1_hits += 1
        if result["h2_prototype"]:
            h2_hits += 1
        if result["h3_mockup"]:
            h3_hits += 1
        if result["h4_rel_req"]:
            h4_hits += 1
        # H1 + H2 必填 — 任一缺失即记为 missing
        if not result["h1_prd"] or not result["h2_prototype"]:
            missing.append({
                "section_id": sec["id"],
                "header": sec["header"],
                "line": sec["line"],
                "missing_h1_prd": not result["h1_prd"],
                "missing_h2_prototype": not result["h2_prototype"],
            })
        # 链接违规聚合(关联到段)
        for lv in result["link_violations"]:
            all_link_violations.append({
                "section_id": sec["id"],
                "header": sec["header"],
                **lv,
            })

    n = len(sections)
    return {
        "file": str(path),
        "sections": n,
        "coverage": {
            "H1_PRD来源": h1_hits / n,
            "H2_原型来源": h2_hits / n,
            "H3_高保真来源": h3_hits / n,
            "H4_关联功规点": h4_hits / n,
        },
        "missing": missing,
        "link_violations": all_link_violations,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="REQ/功规点段头部上游溯源覆盖率核验")
    ap.add_argument("target", help="PRD 文件或目录")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--threshold", type=float, default=0.95,
                    help="覆盖率阈值(默认 0.95);H1/H2 强制 1.0")
    args = ap.parse_args()

    target = Path(args.target)
    if not target.exists():
        print(f"❌ 路径不存在: {target}", file=sys.stderr)
        return 2

    md_files = [target] if target.is_file() else sorted(target.rglob("*.md"))
    if not md_files:
        print(f"⚠️  未发现 markdown 文件: {target}", file=sys.stderr)
        return 2

    aggregated = {
        "files": [],
        "total_sections": 0,
        "h1_hits": 0, "h2_hits": 0, "h3_hits": 0, "h4_hits": 0,
        "total_link_violations": 0,
        "passed": True,
    }

    for f in md_files:
        # 跳过待澄清清单 / 专职索引 / README(非功规点正文,不承载 5.N/REQ- 段)
        # 现行规范 00_索引.md 只汇总清单与全局索引,历史 00_*-总览.md grandfather 一并豁免
        if ("99_" in f.name or "README" in f.name.upper()
                or f.name == "00_索引.md" or re.match(r"^00_.*(总览|索引)\.md$", f.name)):
            continue
        result = analyze_file(f)
        aggregated["files"].append(result)
        aggregated["total_sections"] += result["sections"]
        n = result["sections"]
        if n:
            # 用 round 还原命中数:coverage=hits/n 为浮点,int(coverage*n) 会因浮点误差
            # 把 2/3*3=1.9999… 截断成 1,导致跨文件聚合覆盖率被低估
            aggregated["h1_hits"] += round(result["coverage"]["H1_PRD来源"] * n)
            aggregated["h2_hits"] += round(result["coverage"]["H2_原型来源"] * n)
            aggregated["h3_hits"] += round(result["coverage"]["H3_高保真来源"] * n)
            aggregated["h4_hits"] += round(result["coverage"]["H4_关联功规点"] * n)
        aggregated["total_link_violations"] += len(result.get("link_violations", []))

    if aggregated["total_sections"] == 0:
        if args.json:
            print(json.dumps({"passed": True, "skipped": True,
                              "msg": "未发现功规点段(### REQ-NNN / #### 5.N 等)"},
                             ensure_ascii=False, indent=2))
        else:
            print("⚠️  未发现功规点段,跳过核验")
        return 0

    n = aggregated["total_sections"]
    overall = {
        "H1_PRD来源": aggregated["h1_hits"] / n,
        "H2_原型来源": aggregated["h2_hits"] / n,
        "H3_高保真来源": aggregated["h3_hits"] / n,
        "H4_关联功规点": aggregated["h4_hits"] / n,
    }
    aggregated["overall_coverage"] = overall

    # 判定:H1+H2 必须 100%, H3+H4 ≥ threshold
    if overall["H1_PRD来源"] < 1.0 or overall["H2_原型来源"] < 1.0:
        aggregated["passed"] = False
    if overall["H3_高保真来源"] < args.threshold or overall["H4_关联功规点"] < args.threshold:
        # H3/H4 仅警告,不阻塞(高保真 / 依赖 允许部分缺失)
        aggregated.setdefault("warnings", []).append(
            f"H3/H4 覆盖率 < {args.threshold:.0%},建议补全"
        )
    # 链接违规:有违规即不通过(强制 markdown 链接 + 相对路径 + 文件后缀)
    if aggregated["total_link_violations"] > 0:
        aggregated["passed"] = False

    if args.json:
        print(json.dumps(aggregated, ensure_ascii=False, indent=2))
        return 0 if aggregated["passed"] else 1

    print(f"扫描 {len(aggregated['files'])} 个文件,共 {n} 个功规点段\n")
    print("覆盖率统计(H1/H2 必须 100%,H3/H4 建议 ≥ 95%):")
    for k, v in overall.items():
        marker = "✅" if v >= (1.0 if k.startswith(("H1", "H2")) else args.threshold) else "❌"
        print(f"  {marker} {k}: {v:.1%}")

    if aggregated["total_link_violations"] > 0:
        print(f"\n链接合规度: ❌ {aggregated['total_link_violations']} 处违规"
              f"(必须 markdown 链接 [文本](相对路径#锚点),不允许纯文本/绝对路径)")
    else:
        print("\n链接合规度: ✅ 全部使用 markdown 链接 + 相对路径")

    for w in aggregated.get("warnings", []):
        print(f"\n⚠️  {w}(H3 高保真 / H4 关联功规点 非阻塞,如有则应补全)")

    if not aggregated["passed"]:
        if overall["H1_PRD来源"] < 1.0 or overall["H2_原型来源"] < 1.0:
            print(f"\n❌ 不通过: H1 PRD 来源 / H2 原型来源 必须 100% 覆盖")
            print(f"缺失功规点段(每段头部 {HEAD_WINDOW} 行内未找到必填来源):")
            for r in aggregated["files"]:
                for m in r["missing"][:5]:
                    miss_tag = []
                    if m["missing_h1_prd"]:
                        miss_tag.append("H1_PRD")
                    if m["missing_h2_prototype"]:
                        miss_tag.append("H2_原型")
                    print(f"  {r['file']}:L{m['line']}  [{','.join(miss_tag)}]  {m['header']}")
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

    h34_ok = (overall["H3_高保真来源"] >= args.threshold
              and overall["H4_关联功规点"] >= args.threshold)
    h34_note = (f"H3/H4 ≥ {args.threshold:.0%}" if h34_ok
                else f"H3/H4 未达 {args.threshold:.0%}(非阻塞警告,见上)")
    print(f"\n✅ 通过: H1/H2 = 100%(强制项达标), {h34_note}, 链接合规")
    return 0


if __name__ == "__main__":
    sys.exit(main())
