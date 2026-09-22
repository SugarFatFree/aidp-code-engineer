#!/usr/bin/env python3
"""check_banned_terminology.py — AIDP 术语一致性守卫（脚手架契约脚本）。

## 这道门堵的是什么

AIDP 的需求模型是 **EPIC × Sprint × Task 三层，没有 User Story 层**。这条规则不是措辞洁癖：
`agents/version-auditor.md` 的详细设计越界检查 **B-02** 把「用户故事 / US-NNN」列为**命中即标**的
违规项。于是当契约文档自己写着「映射今日任务到 Sprint / User Story」「PM 负责用户故事拆分」时，
下游 AI 照着产出带 US 标注的设计文档，**再被同一套范式里的审计 Agent 判违规**——规则自己和自己打架，
而这类冲突现有守卫一个都看不见（`check_md_anchors` 只管链接、`check_count_claims` 只管数字）。

同类问题还有目录改名后的旧名残留（`测试执行/`·`测试验收/` → `正式用例/`）：旧名在 migrate
期仍需识别，但**新文档不该再产出**它们。

## 判据

维护一张「禁用词 → 正确词」表，扫全部契约 `.md`。**豁免靠显式清单**，不靠正则猜——
那些「正在定义该禁令」的行（version-auditor 的 B-02 判据行、模板里的 ⚠️ 警示行、
migrate 的改名说明）必须原样保留禁用词，它们是规则本身。

新增豁免：把 `文件:行内容特征` 加进 `EXEMPT`，或在行尾写 `<!-- term-check: ignore 理由 -->`。

退出码：0 通过；1 有命中；2 参数错。
"""
import sys as _aidp_sys
from pathlib import Path as _AidpPath
_aidp_scripts = str(_AidpPath(__file__).resolve().parent)
if _aidp_scripts not in _aidp_sys.path:
    _aidp_sys.path.insert(0, _aidp_scripts)
from aidp_runtime import runtime_text
import argparse
import json
import os
import re
import sys

SCAN_DIRS = (runtime_text('__AIDP_HOME__/commands', __file__), runtime_text('__AIDP_HOME__/agents', __file__), runtime_text('__AIDP_HOME__/flows', __file__), runtime_text('__AIDP_HOME__/reference', __file__),
             runtime_text('__AIDP_HOME__/rules', __file__), runtime_text('__AIDP_HOME__/templates', __file__), "docs/init")
SCAN_ROOT_FILES = ("README.md", "AGENTS.md", "CLAUDE.md", runtime_text('__AIDP_HOME__/AIDP-AGENTS.md', __file__),
                   "memory/README.md")

# 禁用词 → (正确词, 为什么)
BANNED = {
    "User Story": ("EPIC / Task", "AIDP 无 User Story 层；version-auditor B-02 命中即判违规"),
    "用户故事": ("研发需求 / EPIC / Task", "同上"),
    # ⚠️ `US-NNN` 是**字面量**、匹配不到真实编号 `US-001`；真实产物里出现的恰恰是后者。
    #   故另立一条正则式禁用项（见 BANNED_RE），本行只保留占位写法本身。
    "US-NNN": ("T-NNN（Task 编号）", "同上"),
    # ★ docstring 第二段（「目录改名后的旧名残留」）此前**只写在说明里、没进这张表**——
    #   于是任何新文档写 `测试执行/` 都不会被拦。补上；存量兼容说明走 EXEMPT_MARKERS。
    "测试执行/": ("正式用例/", "目录已改名；旧名仅 migrate 期识别，新文档不得再产出"),
    "测试验收/": ("正式用例/", "同上"),
}

# 正则式禁用项（字面量表达不了的形态）
BANNED_RE = {
    re.compile(r"\bUS-\d{2,}\b"): ("T-NNN（Task 编号）",
                                    "AIDP 无 User Story 层；version-auditor B-02 命中即判违规"),
}

# 豁免：这些行【正在定义禁令本身】或【是存量兼容说明】，必须原样保留禁用词
EXEMPT_MARKERS = (
    "命中即标",            # version-auditor B-02 判据行
    "AIDP 无",             # 模板/文档里的 ⚠️ 警示行
    "无「User Story」层",
    "无 User Story 层",
    "历史锚",              # 目录改名的存量兼容说明
    "整目录重命名",
    "仅存量兼容",
)
IGNORE_RE = re.compile(r"<!--\s*term-check:\s*ignore\b")


def _iter_files(root):
    for d in SCAN_DIRS:
        base = os.path.join(root, d)
        for dirpath, _dn, fns in os.walk(base):
            if "__pycache__" in dirpath:
                continue
            for fn in sorted(fns):
                if fn.endswith(".md"):
                    yield os.path.join(dirpath, fn)
    for f in SCAN_ROOT_FILES:
        p = os.path.join(root, f)
        if os.path.isfile(p):
            yield p


def run(root="."):
    findings, scanned = [], 0
    for fp in _iter_files(root):
        rel = os.path.relpath(fp, root).replace(os.sep, "/")
        scanned += 1
        for i, ln in enumerate(open(fp, encoding="utf-8").read().splitlines(), 1):
            if IGNORE_RE.search(ln) or any(m in ln for m in EXEMPT_MARKERS):
                continue
            for bad, (good, why) in BANNED.items():
                if bad in ln:
                    findings.append({
                        "level": "ERROR", "file": rel, "line": i, "term": bad,
                        "detail": f"用了禁用术语「{bad}」→ 应为「{good}」（{why}）",
                        "excerpt": ln.strip()[:100],
                    })
            for rx, (good, why) in BANNED_RE.items():
                m = rx.search(ln)
                if m:
                    findings.append({
                        "level": "ERROR", "file": rel, "line": i, "term": m.group(0),
                        "detail": f"用了禁用术语「{m.group(0)}」→ 应为「{good}」（{why}）",
                        "excerpt": ln.strip()[:100],
                    })
    return {"applicable": scanned > 0, "scanned": scanned,
            "findings": findings, "passed": not findings}


def main():
    ap = argparse.ArgumentParser(description="AIDP 术语一致性检查")
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-check", action="store_true",
                    help="阳性对照自检：注入必然命中的探针，验证本检查确实生效"
                         "（骨架与探针登记表见 selfcheck.py）")
    a = ap.parse_args()
    if a.self_check:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from selfcheck import run_self_check
        sys.exit(run_self_check(os.path.basename(__file__),
                                json_out=getattr(a, "json", False)))
    r = run(a.root)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0 if r["passed"] else 1
    for f in r["findings"]:
        print(f"  [{f['level']}] {f['file']}:{f['line']} — {f['detail']}")
        print(f"        > {f['excerpt']}")
    print(f"术语一致性：巡检 {r['scanned']} 份 .md（{len(r['findings'])} 处命中）")
    if r["findings"]:
        print("豁免：行尾加 `<!-- term-check: ignore 理由 -->`；"
              "或把「正在定义该禁令」的特征词加进脚本 EXEMPT_MARKERS")
    return 0 if r["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
