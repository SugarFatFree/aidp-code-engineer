#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""研发执行计划「验收标准」列的确定性初筛（G-PLAN-1 的机器一侧）。

只做**形式**判定，抓三类一眼可见的不可验收单元格：
  ① 空白 / 占位（`-` `—` `TBD` `待定` `无`）；
  ② 无任何可核验落点（无 markdown 链接、无反引号命令或标识符、无 `§` 锚点）且是纯套话
     （「完成开发」「功能正常」「按设计实现」「符合要求」等）；
  ③ 无可核验落点且过短（≤8 个可见字符）。
「验收标准是否真的可判真假、是否与代码同向」是语义判断，仍归 `dev-execution-planner` 的 QR 与 `/sprint-plan` 4b/4c，
本脚本通过**不代表**可验收，只保证最明显的空话不放行。

用法：`python3 check_plan_ac.py <计划.md>... [--json] [--count] [--strict] [--self-check]`
  默认：逐条打印命中行（WARN），退出码 0；`--strict` 命中时退出码 1；`--count` 只输出命中总数。
  表识别：表头含「Task」与「验收标准」列（列序不限）。退出码 2 = 文件不存在 / 无参数。
"""
import argparse
import json
import os
import re
import sys

EVIDENCE_RE = re.compile(r"\[[^\]]+\]\([^)]+\)|`[^`]+`|§")
PLACEHOLDER_RE = re.compile(r"^(?:[-—–_/.\s]*|tbd|todo|n/?a|待定|待补充|待确认|无|暂无)$", re.I)
VAGUE_RE = re.compile(
    r"^(?:完成(?:开发|编码|实现)?|开发完成|功能正常|正常(?:运行|使用|工作)?|按(?:设计|需求|文档|计划)(?:实现|开发|完成)?|"
    r"符合(?:设计|需求|要求|预期)|满足(?:设计|需求|要求|预期)|实现(?:功能|需求)?|通过(?:测试|验收)?|ok|done)[。.;；!！\s]*$", re.I)
SHORT_LIMIT = 8


def _cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _is_sep(line):
    return bool(re.match(r"^\s*\|?\s*:?-+", line)) and set(line.strip()) <= set("|-: ")


def judge(cell):
    """返回命中原因；合格返回 None。"""
    text = cell.strip()
    if PLACEHOLDER_RE.match(text):
        return "空白或占位"
    if EVIDENCE_RE.search(text):
        return None
    visible = re.sub(r"\s+", "", text)
    if VAGUE_RE.match(visible):
        return "纯套话，无可核验落点"
    if len(visible) <= SHORT_LIMIT:
        return "过短且无可核验落点（链接 / 反引号命令 / § 锚点）"
    return None


def scan(path):
    findings = []
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    ac_idx, task_idx = None, 0
    for no, ln in enumerate(lines, 1):
        if not ln.strip().startswith("|"):
            ac_idx = None
            continue
        if _is_sep(ln):
            continue
        cells = _cells(ln)
        if ac_idx is None:
            heads = [c.replace(" ", "") for c in cells]
            if any(h.lower().startswith(("task", "任务")) for h in heads) and "验收标准" in heads:
                ac_idx = heads.index("验收标准")
                task_idx = next(i for i, h in enumerate(heads) if h.lower().startswith(("task", "任务")))
            continue
        if ac_idx >= len(cells):
            findings.append({"file": path, "line": no, "task": cells[task_idx] if task_idx < len(cells) else "",
                             "reason": "列数不足，缺验收标准单元格"})
            continue
        reason = judge(cells[ac_idx])
        if reason:
            findings.append({"file": path, "line": no, "task": cells[task_idx], "reason": reason})
    return findings


def self_check():
    """内置样例：合格 / 套话 / 空白 / 过短各一行，命中集合必须精确匹配。"""
    import tempfile
    body = ("| Task | 验收标准 |\n|---|---|\n"
            "| T1 | 运行 `pytest tests/test_x.py` 全绿 |\n"
            "| T2 | 功能正常 |\n"
            "| T3 | TBD |\n"
            "| T4 | 能用 |\n")
    with tempfile.TemporaryDirectory(prefix="aidp-plan-ac-") as d:
        path = os.path.join(d, "plan.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
        got = sorted(x["task"] for x in scan(path))
    return got == ["T2", "T3", "T4"]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("files", nargs="*")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--count", action="store_true")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--self-check", action="store_true")
    args = ap.parse_args(argv)
    if args.self_check:
        ok = self_check()
        print(json.dumps({"self_check": "pass" if ok else "fail"}, ensure_ascii=False))
        return 0 if ok else 1
    if not args.files:
        ap.error("需要至少一个计划文件（或 --self-check）")
    findings = []
    for p in args.files:
        if not os.path.isfile(p):
            print("文件不存在：%s" % p, file=sys.stderr)
            return 2
        findings.extend(scan(p))
    if args.count:
        print(len(findings))
    elif args.json:
        print(json.dumps({"count": len(findings), "findings": findings}, ensure_ascii=False, indent=2))
    else:
        for x in findings:
            print("[WARN ] %s:%d %s 验收标准不可验收：%s" % (x["file"], x["line"], x["task"], x["reason"]))
        if not findings:
            print("[OK] 验收标准形式初筛通过（语义可验收性仍由 QR 判定）")
    return 1 if (findings and args.strict) else 0


if __name__ == "__main__":
    sys.exit(main())
