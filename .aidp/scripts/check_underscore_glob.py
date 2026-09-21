#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_underscore_glob.py — 「发现型 glob 漏排 `_` 前缀」门（约定 22 族增量册配套）。

四族增量册（`_开发期{族}增量.md`）与该族交付文档**同住一个目录**，因此每一处
"找用例 / 找文档"的 glob 都必须排除 `_` 前缀文件。

⛔ **为什么必须有这道门**：这些 glob 用的是**黑名单**——`-not -name "00_索引.md"
-not -name "99_*" …` 逐个点名排除。新来的 `_开发期*.md` **一条都不命中**，于是被当成
交付文档收进去，而失败形态**完全静默**：

  · `/sprint-aiauto-test` 的 `DEV_CASES` 把增量册喂给 auto-test-runner —— 它解析不出
    任何 `SUITE-*`/`TC-*`，静静地贡献 0 条用例，没有任何一处会说"这文件不是用例册"；
  · `/sprint-batch` Step 6 的 `DEV_HAS` 是**存在性判据**（`head -1`）——增量册一在，
    "有没有用例册"就恒真，**零用例也判成用例齐备**；
  · `/sprint-test` 同族问题。

三处都是"看着正常、其实测了个空"的形态，与本仓反复栽的那类失效同族。

判据（确定性，零语义推断）：flow / command 正文里对四族目录做的 `find … -name "*.md"`，
若**未**带 `-not -name "_*"` → 报违规。白名单式 glob（只点名具体文件名，如
`-name "02_*自测用例*.md"`）天然收不到 `_` 前缀，不在管辖内。

退出码：0 = 全部合规；1 = 有漏排；2 = 入参/环境错。
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

# 四族目录的特征片段——glob 命中其一即视为"发现型扫描"
FAMILY_HINTS = ("研发自测", "研发需求", "docs/design/detail", "docs/plans",
                "正式用例", "测试验收", "测试执行")
# 通配式 .md 扫描（白名单式如 `-name "02_*自测用例*.md"` 不算）
_WILDCARD_MD = re.compile(r'-name\s+"\*\.md"')
_HAS_GUARD = re.compile(r'-not\s+-name\s+"_\*"')
SCAN_DIRS = (runtime_text('__AIDP_HOME__/flows', __file__), runtime_text('__AIDP_HOME__/commands', __file__))


def _iter_md(root):
    for base in SCAN_DIRS:
        d = os.path.join(root, base)
        if not os.path.isdir(d):
            continue
        for dirpath, _dn, fns in os.walk(d):
            for fn in sorted(fns):
                if fn.endswith(".md"):
                    yield os.path.join(dirpath, fn)


def run(root):
    violations = []
    scanned = 0
    for path in _iter_md(root):
        scanned += 1
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()
        except OSError:
            continue
        # find 可能跨多行续行，折叠反斜杠续行后按 `find` 起点切段
        text = "\n".join(lines)
        folded = re.sub(r"\\\s*\n\s*", " ", text)
        for m in re.finditer(r"find\s+[^\n]*", folded):
            seg = m.group(0)
            if not _WILDCARD_MD.search(seg):
                continue
            if not any(h in seg for h in FAMILY_HINTS):
                continue
            if _HAS_GUARD.search(seg):
                continue
            # 行号取原文里该 find 首次出现处（折叠后偏移不可用）
            ln = next((i + 1 for i, l in enumerate(lines) if "find " in l
                       and any(h in l for h in FAMILY_HINTS)), 0)
            violations.append({
                "file": os.path.relpath(path, root).replace(os.sep, "/"),
                "line": ln,
                "excerpt": seg[:180],
                "reason": ("四族目录的通配式 `.md` 扫描漏排 `_` 前缀 —— "
                           "`_开发期{族}增量.md` 会被当成交付文档/用例源收进去。"
                           "补 `-not -name \"_*\"`"),
            })
    return {"scanned_files": scanned, "violations": violations,
            "passed": not violations}


def main():
    ap = argparse.ArgumentParser(description="发现型 glob 漏排 `_` 前缀门")
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-check", action="store_true",
                    help="阳性对照自检：注入必然命中的探针，验证本检查确实生效")
    args = ap.parse_args()
    if args.self_check:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from selfcheck import run_self_check
        return run_self_check(os.path.basename(__file__), json_out=args.json)
    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print("[ERROR] --root 不是目录: %s" % root, file=sys.stderr)
        return 2
    res = run(root)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        for v in res["violations"]:
            print("[ERROR] %s:%d %s" % (v["file"], v["line"], v["reason"]))
            print("        %s" % v["excerpt"])
        print("扫描 %d 份 flow/command：%d 处漏排"
              % (res["scanned_files"], len(res["violations"])))
    return 0 if res["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
