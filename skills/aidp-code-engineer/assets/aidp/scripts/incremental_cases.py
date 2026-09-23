#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""incremental_cases.py — 算出「本轮相对上一轮新增了哪些用例」（TC-ID 集合）。

## 它解决什么

AI 自动化测试**每轮跑全量**（每定一个新轮次就从整个用例集重建 tasks.md），这是对的——
增量改动最容易打破的恰恰是既有功能，只测增量会把回归缺陷整类漏掉。

但**报告里分不清增量**：约定 22 的用例增量级联之后，新用例写进 `02_*.md`，
在文件里和三个月前那批长得一模一样。于是报告说「114 条、通过率 100%」，
而你**无法验证本轮那 5 条新功能到底有没有对应用例、跑没跑、结果如何**——
全绿看着安心，却证明不了增量被覆盖过。

（报告模板里本就有一行 `| 测试类型 | 全量 / 增量 |`，但全库**没有任何生产方**——
字段在、无人写，看着有其实没有。本脚本就是那个生产方。）

## 判据：不靠标记，靠 git

⛔ **刻意不在用例册里打 `[增量]` 标记**：那要改上游 `dev-manual-testcase` 的产出格式
（约定 16 不可直接改），且标记漏打就永久失真。改用 git 确定性地算——
**新增的用例标题行**（`#### 用例 TC-XXX:` / `#### TC-XXX`，「用例」二字可省，
标题层级 3~6 级都识别，对齐 auto-test-runner 的解析契约）即本轮增量。

只认**标题行**、不认正文里的顺带提及：后者会把"某条用例的步骤里引用了 TC-013"
误算成新增，而那类误算的方向是**虚报覆盖**（说测了其实没测），比漏报更危险。

## 基准点（anchor）

`--since <ref>` 显式指定；否则读 baseline `versions.{V}.case_scan_sha`（上一轮的扫描点）。
两者都没有 → 判 `no-anchor`、增量集为空、报告标「全量」并**明说无增量基准**
——⛔ 不拿"版本起点"顶上：那会让第一轮把全部用例都报成"增量"，是虚假的精确。

退出码：0 = 已算出（含 no-anchor 的诚实空集）；2 = 入参 / git 不可用（fail-closed，不假装空集）。
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

# 新增的**用例标题行**；「用例」二字可省、标题 3~6 级（对齐 auto-test-runner usecase-format）
_ADDED_TC = re.compile(r"^\+\s*#{3,6}\s*(?:用例\s*)?(TC-[A-Za-z0-9_\-]+)")


def _git(root, *args):
    # ⛔ `-c core.quotepath=false` 不可省：用例册路径含中文，git 默认转义成 \345\274... → 路径匹配不上
    try:
        cp = subprocess.run(["git", "-C", root, "-c", "core.quotepath=false", *args],
                            capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, str(exc)
    if cp.returncode != 0:
        return None, (cp.stderr or "").strip() or ("git %s 失败" % " ".join(args))
    return cp.stdout, None


def _baseline(root):
    p = os.path.join(root, "memory", ".sprint-autopilot-baseline.json")
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:                                            # noqa: BLE001
        return {}


def run(root, version, since=None, build=None):
    res = {"version": version, "build": build, "since": since,
           "status": "", "ids": [], "count": 0, "head": None, "error": None}
    head, err = _git(root, "rev-parse", "HEAD")
    if err:
        res["status"] = "git-unavailable"
        res["error"] = err
        return res
    res["head"] = (head or "").strip()

    if not since:
        bl = _baseline(root)
        since = (((bl.get("versions") or {}).get(version) or {}).get("case_scan_sha")) or None
        res["since"] = since
    if not since:
        # 诚实空集：没有基准就说不出增量，⛔ 不拿版本起点顶上（那会把首轮全部用例报成增量）
        res["status"] = "no-anchor"
        return res

    scope = "docs/testing/%s/" % version
    out, err = _git(root, "diff", "%s..HEAD" % since, "--unified=0", "--", scope)
    if err:
        res["status"] = "diff-failed"
        res["error"] = err
        return res
    ids = []
    for line in (out or "").splitlines():
        m = _ADDED_TC.match(line)
        if m and m.group(1) not in ids:
            ids.append(m.group(1))
    res["ids"] = ids
    res["count"] = len(ids)
    res["status"] = "computed"
    return res


def _record(root, version, build, res):
    """写 baseline：本 build 的增量集 + 推进版本级扫描锚点。

    ★ 锚点**只在该 build 首次记录时推进**：同一 build 的复测轮不能把锚点推到 HEAD，
    否则第二轮起增量集恒空——而复测轮恰恰最需要知道"本 build 的增量是哪几条"。
    """
    edit = os.path.join(root, runtime_relpath("", __file__), "scripts", "baseline_edit.py")
    if not os.path.isfile(edit):
        return False, "baseline_edit.py 不存在"
    bl = _baseline(root)
    vnode = ((bl.get("versions") or {}).get(version) or {})
    blds = vnode.get("builds") or []
    entry = next((b for b in blds if isinstance(b, dict) and b.get("build") == build), None)
    first_time = not (entry or {}).get("incremental_case_ids_at")
    try:
        if build:
            subprocess.run(
                [sys.executable, edit, "--version", version, "--build", build, "set",
                 "incremental_case_ids", json.dumps(res["ids"], ensure_ascii=False),
                 "incremental_case_ids_at", "@now"],
                capture_output=True, text=True, timeout=60)
        if first_time and res.get("head") and res["status"] == "computed":
            subprocess.run(
                [sys.executable, edit, "--version", version, "set",
                 "case_scan_sha", res["head"]],
                capture_output=True, text=True, timeout=60)
        return True, "已落盘（锚点%s推进）" % ("已" if first_time else "未")
    except Exception as exc:                                     # noqa: BLE001
        return False, str(exc)


def main():
    ap = argparse.ArgumentParser(description="算本轮相对上一轮新增的用例 TC-ID 集合")
    ap.add_argument("--root", default=".")
    ap.add_argument("--version")
    ap.add_argument("--build", help="落盘到该 build 的 incremental_case_ids")
    ap.add_argument("--since", help="基准 git ref；缺省读 baseline case_scan_sha")
    ap.add_argument("--record", action="store_true", help="写回 baseline")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-check", action="store_true",
                    help="阳性对照自检：注入必然命中的探针，验证本检查确实生效")
    args = ap.parse_args()
    if args.self_check:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from selfcheck import run_self_check
        return run_self_check(os.path.basename(__file__), json_out=args.json)

    root = os.path.abspath(args.root)
    if not os.path.isdir(root) or not args.version:
        print("[ERROR] 需要有效 --root 与 --version", file=sys.stderr)
        return 2
    res = run(root, args.version, args.since, args.build)
    if args.record and res["status"] == "computed":
        ok, why = _record(root, args.version, args.build, res)
        res["recorded"] = ok
        res["record_detail"] = why

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        if res["status"] == "no-anchor":
            print("[INFO ] %s 无增量基准（baseline 无 case_scan_sha 且未传 --since）"
                  "→ 报告标「全量」，不虚报增量" % args.version)
        elif res["status"] == "computed":
            print("[OK   ] %s 本轮增量用例 %d 条：%s"
                  % (args.version, res["count"], ", ".join(res["ids"]) or "（无）"))
            print("        测试类型 = %s"
                  % ("全量（含本轮增量 %d 条）" % res["count"] if res["count"] else "全量"))
        else:
            print("[ERROR] %s：%s" % (res["status"], res.get("error")), file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
