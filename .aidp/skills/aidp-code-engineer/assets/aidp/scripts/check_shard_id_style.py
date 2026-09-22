#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_shard_id_style.py — 同一命令 flow 目录内的编号标题风格一致性（脚手架契约脚本）。

## 为什么需要本脚本

同一个命令的 flow 分片里，**同一层级**的标题编号写法可能出现两种形态并存——
`#### Step 3.3.7.1：` 与 `#### 3.3.7.1：` 混在一个目录里（实测 `version/` 曾是 17 vs 13）。

⚠️ **注意区分"分层"与"混用"**：`### Step 3.3.7：`（主步带前缀）+ `#### 3.3.7.1：`（子步裸编号）
是**有规律的分层**、完全正常——本脚本按标题层级分组统计，只有**同一层级内**并存才判问题。
一刀切不分层会把合理设计报成缺陷（初版正是如此，实测把 version/ 的正常分层误报了）。

后果不是"看着乱"，而是**跨片引用无法被任何锚点检查覆盖**：文档里写「见 Phase 3.1.5」时，
锚点检查器要么按 `Phase 3.1.5` 找、要么按 `3.1.5` 找，两种写法并存就必然有一半找不到，
于是这类引用只能靠人读——而人读正是漂移的来源。统一之后，`check_md_anchors` 与
`check_step_index_coverage` 才能真正覆盖跨片引用。

## 判据（纯词法，零主观）

对每个 `flows/<cmd>/` 目录，统计其分片里编号标题的**前缀形态**：

  - `with-prefix`  —— `### Phase 3.1：…` / `### Step 2.7：…`（编号前带 Phase/Step 关键词）
  - `bare`         —— `### 3.1：…`（编号直接跟在 `#` 后）

**同一目录、同一标题层级内两种形态并存 → WARN**，给出占比与少数派所在文件，
供决定统一到哪一种（多数派通常就是该目录的既定风格）。

判 **WARN 而非 ERROR**：统一风格要动大量标题，且改标题会连带影响所有指向它的引用——
属需要一次性集中整改的事，不适合当成阻断提交的硬门。附属文件
（`rationale.md` / `invariants.md` / `usage-guard.md` / `README.md`）不计入。

豁免：分片里加 `<!-- shardstyle-check: ignore-file <理由> -->`。

## 用法

    python3 AIDP_HOME/scripts/check_shard_id_style.py [--root <仓库根>] [--json]

退出码：`0`（本检查恒为提示性，不阻断）/ `2`=用法或读取错误。
"""
import sys as _aidp_sys
from pathlib import Path as _AidpPath
_aidp_scripts = str(_AidpPath(__file__).resolve().parent)
if _aidp_scripts not in _aidp_sys.path:
    _aidp_sys.path.insert(0, _aidp_scripts)
from aidp_runtime import runtime_relpath, runtime_text
import argparse
import json
import os
import re
import sys

ATTACH = {"rationale.md", "invariants.md", "usage-guard.md", "README.md"}
IGNORE_FILE = re.compile(r"<!--\s*shardstyle-check:\s*ignore-file\b[^>]*-->")
# ★ 必须**按标题层级分组**统计：`### Step 3.3.7：` 主步带前缀 + `#### 3.3.7.1：` 子步裸编号
#   是**有规律的分层**、不是混排（实测本仓 version/ 正是如此，一刀切会把合理设计报成缺陷）。
#   只有**同一层级内**两种形态并存才是真混用——那才让跨片引用无法被同一套锚点规则覆盖。
WITH_PREFIX = re.compile(r"^(#{2,4})\s+(?:★\s*)?(?:Phase|Step)\s+[0-9]")
# ⚠️ 分隔符**必须含空格**：原实现要求编号后紧跟 `：`/`:`/`·`，而本仓主流写法是空格分隔
#   （`### 0.1 chrome-devtools-mcp 检测 + 智能启动`）。那类标题既不匹配 WITH_PREFIX 也不匹配
#   BARE，在统计里**完全隐身** —— 于是「同层级两种形态并存」的真混用被判成一致（实测
#   sprint-autopilot 的 `###` 层：裸+空格 20 个 vs Phase/Step 前缀 6 个，脚本报 OK）。
BARE = re.compile(r"^(#{2,4})\s+(?:★\s*)?[0-9]+(?:\.[0-9]+)*[a-zA-Z]*(?:\s*[：:·]|\s+\S)")


def _read(p):
    try:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def run(root):
    flows = os.path.join(root, runtime_relpath("", __file__), "flows")
    if not os.path.isdir(flows):
        return {"applicable": False, "reason": runtime_text('无 __AIDP_HOME__/flows，跳过', __file__),
                "findings": [], "passed": True}
    findings, scanned = [], 0
    for cmd in sorted(os.listdir(flows)):
        d = os.path.join(flows, cmd)
        if not os.path.isdir(d):
            continue
        stat = {}          # 标题层级（# 数）→ {"with-prefix": [...], "bare": [...]}
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".md") or fn in ATTACH:
                continue
            text = _read(os.path.join(d, fn))
            if not text or IGNORE_FILE.search(text):
                continue
            scanned += 1
            for line in text.split("\n"):
                m = WITH_PREFIX.match(line)
                kind = "with-prefix"
                if not m:
                    m = BARE.match(line)
                    kind = "bare"
                if not m:
                    continue
                lvl = len(m.group(1))
                stat.setdefault(lvl, {"with-prefix": [], "bare": []})[kind].append(fn)
        for lvl in sorted(stat):
            a, b = len(stat[lvl]["with-prefix"]), len(stat[lvl]["bare"])
            if not (a and b):
                continue
            major = "with-prefix" if a >= b else "bare"
            minor = "bare" if major == "with-prefix" else "with-prefix"
            findings.append({
                "level": "WARN", "command": cmd, "heading_level": lvl,
                "with_prefix": a, "bare": b, "suggest": major,
                "minor_files": sorted(set(stat[lvl][minor]))[:5],
                "detail": f"`flows/{cmd}/` 的 {'#' * lvl} 级标题内两种形态并存："
                          f"`Phase/Step N` {a} 处、裸 `N` {b} 处 —— 同一层级混用会让跨片引用"
                          f"「见 Phase 3.1.5」与「见 3.1.5」无法被同一套锚点检查覆盖。"
                          f"建议该层级统一为多数派 `{major}`",
            })
    return {"applicable": scanned > 0, "reason": "", "scanned": scanned,
            "findings": findings, "passed": True}


def main():
    ap = argparse.ArgumentParser(description="flow 分片编号标题风格一致性（提示性）")
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-check", action="store_true",
                    help="阳性对照自检：注入必然命中的探针，验证本检查确实生效"
                         "（骨架与探针登记表见 selfcheck.py）")
    args = ap.parse_args()
    if args.self_check:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from selfcheck import run_self_check
        sys.exit(run_self_check(os.path.basename(__file__),
                                json_out=getattr(args, "json", False)))
    try:
        res = run(args.root)
    except Exception as e:
        if args.json:
            print(json.dumps({"error": str(e)}, ensure_ascii=False))
        else:
            print(f"[ERROR] 检查执行失败：{e}")
        return 2
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    if not res["applicable"]:
        print(f"[SKIP] {res.get('reason') or '无可扫描分片'}")
        return 0
    if not res["findings"]:
        print(f"[OK] 各 flow 目录内编号标题风格一致（巡检 {res['scanned']} 份分片）。")
        return 0
    print(f"[WARN] {len(res['findings'])} 个 flow 目录存在编号标题风格混用（提示性，不阻断）：")
    for f in res["findings"]:
        print(f"  · /{f['command']} {'#' * f['heading_level']} 级：Phase/Step 前缀 {f['with_prefix']} 处 vs 裸编号 {f['bare']} 处"
              f" → 建议统一为 `{f['suggest']}`")
        if f["minor_files"]:
            print(f"      少数派所在：{', '.join(f['minor_files'])}")
    print("  统一后，跨片引用（「见 Phase 3.1.5」）才能被 check_md_anchors / "
          "check_step_index_coverage 覆盖。整改会动大量标题及其引用，建议单独一轮集中做。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
