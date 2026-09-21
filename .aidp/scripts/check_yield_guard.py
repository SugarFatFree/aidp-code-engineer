#!/usr/bin/env python3
"""check_yield_guard.py — 「让位（yield）前必须确认有下一 tick」的契约门。

## 这道门堵的是什么

无人值守链路里有一类退出叫 **yield**：本 tick 干不完，让位给下一 tick 接着跑
（`UNATTENDED_YIELD` / `让位本 tick` / `退本 tick`）。它成立的前提只有一个——
**真的会有下一 tick**。

`HAS_WAKE_SOURCE` 就是这个前提的判据，两条链路都在 Phase 0 派生并落盘，
消费口径也白纸黑字写着：`0` → **不许 yield**，本轮内重试/降级并如实回传 `tested:false`。

但派生 ≠ 消费。实测形态：`/sprint-aiauto-test --once --unattended`（autopilot 的补测
与自愈交接反向 invoke 都走这条）满足 `LOOP_UNATTENDED=1` 却 **没有下一 tick**；
而各 yield 点只判 `LOOP_UNATTENDED` → 直接 exit → 测试半途而废，
**且无任何结构级拦截**（Stop hook 只读 autopilot 的 run_state，测试链路根本不写）。
上游拿到 `tested:false` 降级静态-only 收尾——用户以为跑了全链路实测，拿到的是静态结论。

## 判据

对每个 **yield 站点**（含 `UNATTENDED_YIELD` 或「让位本 tick / 退本 tick」的行），
在其**逻辑窗口**（前后各 N 行）内必须出现 `HAS_WAKE_SOURCE`（或 `wake_source_this_tick`）。
找不到 → ERROR。

⛔ 用「窗口内出现」而不是「同一行」：yield 与守卫天然分行写（守卫在 if、yield 在 then）。
豁免：行内或同段 `<!-- yield-guard: ignore 理由 -->`。

退出码：0 通过；1 有 ERROR；2 参数错。
"""
import sys as _aidp_sys
from pathlib import Path as _AidpPath
if "__file__" not in globals():
    __file__ = str(_AidpPath.cwd() / ".aidp" / "scripts" / "check_yield_guard.py")
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

SCAN_DIRS = (os.path.join(runtime_relpath("", __file__), "flows"),)
# ⛔ 只认**围栏内的真实退出动作**：`exit 0` 且同行注释说明它是让位。
#   散文里谈论"让位本 tick"的句子不是动作 —— 把它们算进来，这道门第一天就红几十条，
#   而一道恒红的门只会被关掉，比没有更糟（`check_chain_unattended.py` 的 docstring 记的是同一课）。
YIELD_RE = re.compile(r"^\s*>?\s*exit\s+0\b.*(?:让位|yield)")
# ★ 第二形态：`exit 0` 不在行首、而是与协议信号 `UNATTENDED_YIELD` 写在同一行，如
#   `[ -n "$REMAIN" ] && { echo "UNATTENDED_YIELD"; exit 0; }`。只认「同行既发信号又退出」，
#   不认散文里单独提到 UNATTENDED_YIELD 的句子 —— 恒红的门会被关掉，比没有更糟。
#   ⛔ 少了这一条，autopilot **唯一**的可执行让位点（phase-3-5 的逐 tick 单 Sprint 分支）
#   整个落在巡检面之外，而门照报「9 站点 / 0 ERROR / 通过」。
YIELD_RE2 = re.compile(r"UNATTENDED_YIELD.*\bexit\s+0\b|\bexit\s+0\b.*UNATTENDED_YIELD")
# ★ `autopilot_fail_handle.py` 本身就是守卫：它内建「无唤醒源 = 等价已达阈」
#   （`freeze = streak >= threshold or wake == "0"`），无唤醒源时会**当场冻结 + 发 #4**，
#   于是随后的 `exit 0` 不是「静默半途而废」而是「已止损并让位」。
#   ⛔ 不认它，把手抄守卫收敛进脚本这件**修复**会被本门报成 ERROR —— 一条精确描述了
#   反面事实的假红，而假红常驻 = 硬门被绕过。
GUARD_RE = re.compile(r"HAS_WAKE_SOURCE|wake_source_this_tick|autopilot_fail_handle\.py")
IGNORE_RE = re.compile(r"<!--\s*yield-guard:\s*ignore\b")
# 定义/说明站点：派生 HAS_WAKE_SOURCE 与陈述消费口径的地方本身不是 yield 点
DEFINE_RE = re.compile(r"HAS_WAKE_SOURCE=|消费口径|第三步")
WINDOW = 12

# ★ 已知未修站点（**待修，不是豁免**）：登记在此的 yield 点当前缺守卫，WARN 可见、不阻断；
#   **新出现的站点一律 ERROR**。⛔ 只能变短：修好一个删一个，⛔ 不许往里加新条目。
#   ⚠️ 本门分不清「让位、等下一 tick 接着跑」与「已冻结/已终结的终态退出」——后者本就该退，
#   用行内 `<!-- yield-guard: ignore 理由 -->` 标注即可。
#   ★ 2026-09-11 全部 9 处已逐条判完并清空：8 处带 streak 阈值的门补了
#   `|| [ "${HAS_WAKE_SOURCE:-0}" = "0" ]`（无唤醒源时阈值恒不可达 ⇒ 当场按达阈冻结）；
#   phase-0-7 那处是冻结后的终态退出，标 ignore。**本集合从此应恒为空**。
KNOWN_OPEN = set()


def _is_known_open(rel):
    key = rel.replace(os.sep, "/")
    return any(key.endswith(f) for f, _why in KNOWN_OPEN)


def run(root=".", window=WINDOW):
    res = {"scanned": 0, "sites": 0, "errors": [], "warnings": []}
    for d in SCAN_DIRS:
        base = os.path.join(root, d)
        if not os.path.isdir(base):
            continue
        for dirpath, _dn, fns in os.walk(base):
            for fn in sorted(fns):
                if not fn.endswith(".md") or fn in ("rationale.md",):
                    continue
                p = os.path.join(dirpath, fn)
                try:
                    lines = open(p, encoding="utf-8").read().splitlines()
                except OSError:
                    continue
                res["scanned"] += 1
                if any(IGNORE_RE.search(x) for x in lines[:8]):
                    continue
                in_fence, fence_start = False, 0
                for i, ln in enumerate(lines):
                    st = ln.strip().lstrip("> ").strip()
                    if st.startswith("```"):
                        if st == "```":
                            in_fence = False
                        else:
                            in_fence, fence_start = True, i + 1
                        continue
                    if not in_fence or DEFINE_RE.search(ln):
                        continue
                    if not (YIELD_RE.search(ln) or YIELD_RE2.search(ln)):
                        continue
                    # ★ 检查面 = **本围栏整体**，不是行窗口：shell state 不跨 Bash 调用，
                    #   守卫必须与 exit 在同一个围栏里才真的生效。
                    win = "\n".join(lines[fence_start:i + 1])
                    res["sites"] += 1
                    if GUARD_RE.search(win) or IGNORE_RE.search(win):
                        continue
                    rel = os.path.relpath(p, root)
                    bucket = "warnings" if _is_known_open(rel) else "errors"
                    res.setdefault(bucket, []).append({
                        "file": rel, "line": i + 1,
                        "text": ln.strip()[:160],
                        "msg": "yield 站点 ±%d 行内找不到 HAS_WAKE_SOURCE 守卫 → "
                               "没有下一 tick 时会静默半途而废，上游还以为跑过了" % window,
                        "fix": "让位前先判 `HAS_WAKE_SOURCE`：为 0 时本轮内重试/降级 + 如实回传 "
                               "`tested:false + reason`，⛔ 不 exit；确属误报加 "
                               "`<!-- yield-guard: ignore 理由 -->`",
                    })
    res["passed"] = not res["errors"]
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description="yield 前必须确认有下一 tick（HAS_WAKE_SOURCE 守卫）")
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
        print("巡检 %d 份分片，yield 站点 %d 个" % (r["scanned"], r["sites"]))
        for e in r.get("warnings") or []:
            print("🟡 [待修] %s:%d %s" % (e["file"], e["line"], e["msg"]))
        for e in r["errors"]:
            print("❌ %s:%d %s" % (e["file"], e["line"], e["msg"]))
            print("   %s" % e["text"])
            print("   → %s" % e["fix"])
        nw = len(r.get("warnings") or [])
        tail = "（KNOWN_OPEN 待修 %d 处，不阻断）" % nw if nw else "（KNOWN_OPEN 为空）"
        print("结论：%s%s" % ("✅ 通过" if r["passed"] else "❌ 有 ERROR", tail))
    return 0 if r["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
