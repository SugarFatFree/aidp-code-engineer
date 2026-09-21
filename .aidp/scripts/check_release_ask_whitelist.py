#!/usr/bin/env python3
"""check_release_ask_whitelist.py — 发布路径的 `AskUserQuestion` 是否都在白名单里。

## 这道门堵的是什么

`release-1.md` 早就写了两道明文禁令（「交互式发布 = 全量执行，中途绝不弹」
+ 点名禁止的高频误判暂停理由）。下游实测**全被绕过**：执行体自发弹出
「补完凭据后按什么顺序走？」，自辩措辞恰好就是被点名的那条（"有 4 个提交未经部署验证"）。

根因是**判据形状**：白名单是**允许清单**（告诉你哪些可以问），却没有**反向判据**
（告诉你怎么知道自己正在违规）。执行体在「我这是负责任地提示风险」的框架下，
根本不会主动去比对白名单——**一个只说"可以做什么"的规则，拦不住"我觉得这次特殊"**。

## 判据

扫 `AIDP_HOME/flows/version/**` 与 `AIDP_HOME/commands/version.md` 里每一处 `AskUserQuestion`
提及，要求其**逻辑窗口**内出现白名单锚点（`白名单第 N 处` / `白名单` / `结构化门`）
或显式豁免。指不出归属的 → ERROR。

⛔ 这只能查**文档里写下来的问询点**，查不了执行体运行时自发的那一次——那一次由
`release-1.md` 的「前置自检」条款约束（每次调用前先指名是白名单哪一项，指不出即违规）。
本门保证的是：**契约文本自己不许再长出无归属的问询点**，别让新写的步骤又埋一个。

豁免：`<!-- ask-whitelist: ignore 理由 -->`。
退出码：0 通过；1 有 ERROR；2 参数错。
"""
import sys as _aidp_sys
from pathlib import Path as _AidpPath
_aidp_scripts = str((_AidpPath(__file__).resolve().parent if _AidpPath(__file__).resolve().parent.name == "scripts" else _AidpPath(__file__).resolve().parents[1] / "scripts"))
if _aidp_scripts not in _aidp_sys.path:
    _aidp_sys.path.insert(0, _aidp_scripts)
from aidp_runtime import runtime_relpath
import argparse
import json
import os
import re
import subprocess
import sys

SCAN = [os.path.join(runtime_relpath("", __file__), "flows", "version"),
        os.path.join(runtime_relpath("", __file__), "commands", "version.md")]
ASK_RE = re.compile(r"AskUserQuestion")
# 归属锚点：指名白名单、或明确说明这是结构化门 / 明确说明禁止
ANCHOR_RE = re.compile(r"白名单|结构化门|禁止|⛔\s*不问|不得|无人值守|前置自检|反例|别再加回来")
IGNORE_RE = re.compile(r"<!--\s*ask-whitelist:\s*ignore\b")
WINDOW = 6


def _files(root):
    out = []
    for rel in SCAN:
        p = os.path.join(root, rel)
        if os.path.isfile(p):
            out.append(p)
        elif os.path.isdir(p):
            for dirpath, _dn, fns in os.walk(p):
                out += [os.path.join(dirpath, f) for f in sorted(fns) if f.endswith(".md")]
    return out


def run(root=".", window=WINDOW):
    res = {"scanned": 0, "sites": 0, "errors": []}
    for p in _files(root):
        try:
            lines = open(p, encoding="utf-8").read().splitlines()
        except OSError:
            continue
        res["scanned"] += 1
        if any(IGNORE_RE.search(x) for x in lines[:8]):
            continue
        for i, ln in enumerate(lines):
            if not ASK_RE.search(ln):
                continue
            res["sites"] += 1
            lo, hi = max(0, i - window), min(len(lines), i + window + 1)
            win = "\n".join(lines[lo:hi])
            if ANCHOR_RE.search(win) or IGNORE_RE.search(win):
                continue
            res["errors"].append({
                "file": os.path.relpath(p, root), "line": i + 1,
                "text": ln.strip()[:150],
                "msg": "发布路径出现无白名单归属的 AskUserQuestion",
                "fix": "指名它是 release-1.md 白名单第几处；不属于白名单 → 删掉该问询，"
                       "改为按「默认处置优先级」自动推进 + 记 Step 3.6 风险段",
            })
    res["passed"] = not res["errors"]
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description="发布路径 AskUserQuestion 白名单归属门")
    ap.add_argument("--root", "--repo-root", dest="root", default=".")
    ap.add_argument("--window", type=int, default=WINDOW)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-check", action="store_true")
    a = ap.parse_args(argv)
    if a.self_check:
        sc = os.path.join(os.path.dirname(os.path.abspath(__file__)), "selfcheck.py")
        return subprocess.call([sys.executable, sc, "--only", os.path.basename(__file__)])
    r = run(a.root, a.window)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print("巡检 %d 份，AskUserQuestion 提及 %d 处" % (r["scanned"], r["sites"]))
        for e in r["errors"]:
            print("❌ %s:%d %s\n   %s\n   → %s" % (e["file"], e["line"], e["msg"], e["text"], e["fix"]))
        print("结论：%s" % ("✅ 通过" if r["passed"] else "❌ 有 ERROR"))
    return 0 if r["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
