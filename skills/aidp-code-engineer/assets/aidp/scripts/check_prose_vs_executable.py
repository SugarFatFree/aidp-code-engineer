#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""散文承诺 ↔ 可执行语句对账门。

## 它堵的是哪一类失效

本仓反复出现同一个形状：**契约把某个动作说得很清楚、校验侧也建好了确定性硬门，
唯独动作本身从头到尾只存在于散文里**。三次实测：

  · `notify.py` 在 autopilot 侧出现 7 次，**全部在散文**（引用块 / 表格 / 说明），
    bash 围栏内 0 处；而收尾门对通知台账的核验是**无条件**的（`notify.enabled` 开启即必查），
    台账的唯一自动登记者又正是 `notify.py` —— 发送侧不真跑 = 台账恒空 = 收尾门恒 FAIL。
  · `ai_report_finalized` / `phase_beta_done_at` / `last_deployed_at` 等状态位曾同样
    「此时应把 X 标记为 Y」写在散文里、没有任何 `baseline_edit.py set`。
  · 冻结三件套曾有分支只 `echo` 不写 `needs_human`。

共同点是**读起来完全正确**：句子在、理由在、判据在，只有执行不在。而它对应的失败形态
不是报错，是「门恒 FAIL」或「状态永不更新」，都要跑几个 tick 才显形。

## 判据（刻意只查确定性强、误报低的那几个动作词）

对每个 flow 目录：若该目录的**散文**里承诺了下列动作，则该目录的 ```bash 围栏里
**必须至少出现一次**同一个动作；否则报 ERROR。⛔ 只做"整个目录有没有"，不做逐处配对——
逐处配对必然满屏假红（一个动作被说明三次、执行一次是完全正常的写法）。

  notify.py              发里程碑通知（台账唯一登记者）
  record-card            通知台账登记
  needs_human            冻结上浮（必须真写进 baseline，不能只 echo）
  run-state              Phase 出口游标推进

## 豁免

  · 目录里**根本没提**该动作 → 不适用，不报。
  · 行尾 `<!-- proseexec-check: ignore 理由 -->` 豁免该行。
  · `EXEMPT_DIRS` 里的目录整体跳过（纯说明性目录，如 usage-guard 所在的引导面）。

退出码：`0`=全部有可执行落点（或不适用）/ `1`=检出只说不做 / `2`=用法错。
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

FLOW_ROOT = runtime_text('__AIDP_HOME__/flows', __file__)
ACTIONS = {
    "notify.py": "发里程碑通知（通知台账的唯一自动登记者）",
    "record-card": "通知台账登记",
    "needs_human": "冻结上浮（须真写进 baseline，不能只 echo）",
    "run-state": "Phase 出口游标推进",
}
IGNORE_LINE_RE = re.compile(r"<!--\s*proseexec-check:\s*ignore\b")
# 整体跳过：这些目录本就是"讲用法/讲理由"的说明面，不承载执行
EXEMPT_BASENAMES = {"rationale.md", "usage-guard.md", "README.md", "invariants.md"}


_PLACEHOLDER_LINE = re.compile(r"#N\b|<[^>\n]{1,24}>|(?<!\{)\{[A-Za-z_]+\}(?!\})|\.\.\.|…")

# ★ 第二类判据：**围栏内 `echo` 承诺发通知、同围栏零调用**。
#   为什么 ACTIONS 词表抓不到它：承诺是用中文写的（`echo "→ 已冻结，发 #4 后让位本 tick"`），
#   整行不含 `notify.py` 这个 token ⇒ prose 与 fence 两个计数器都是 0，门恒绿。
#   而这恰是最坏的一种形态——分支把版本冻住了，通知渠道一个字都没有。
#   ⛔ 收得比"全文提到发卡"窄是刻意的：跨分片交叉引用（"#4 由收尾门发"）合法且大量存在，
#   一律判死会淹掉真信号；只有**可执行围栏里的那一句 echo 就是该分支的全部动作**才是缺陷。
_PROMISE_CARD = re.compile(r"(?<![已未不别无])(?<!禁止)(?<!不要)(?<!不准)(?<!不得)(?<!无需)发\s*(?:出\s*)?#[0-9A-Za-z]")
_ECHO_LINE = re.compile(r"^\s*(?:echo|print|printf)\b")


def scan_echo_promises(d):
    """返回 [(文件名, 那行 echo)]：围栏内 echo 承诺发 #N，而该围栏没有真 `notify.py`。"""
    hits = []
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".md") or fn in EXEMPT_BASENAMES:
            continue
        try:
            text = open(os.path.join(d, fn), encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        in_fence, block, blocks = False, [], []
        for raw in text.split("\n"):
            line = re.sub(r"^\s*(?:>\s?)+", "", raw)
            if line.lstrip().startswith("```"):
                if in_fence:
                    blocks.append(block)
                    block = []
                in_fence = not in_fence
                continue
            if in_fence:
                block.append(line)
        for b in blocks:
            if any("notify.py" in l and not _PLACEHOLDER_LINE.search(l) for l in b):
                continue
            for l in b:
                if IGNORE_LINE_RE.search(l) or not _ECHO_LINE.search(l):
                    continue
                if _PROMISE_CARD.search(l):
                    hits.append((fn, l.strip()[:120]))
    return hits


def scan_dir(d):
    """返回 {动作: {"prose": n, "fence": n}}（已排除豁免行与说明性文件）。"""
    stat = {a: {"prose": 0, "fence": 0, "template": 0} for a in ACTIONS}
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".md") or fn in EXEMPT_BASENAMES:
            continue
        try:
            text = open(os.path.join(d, fn), encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        in_fence = False
        for raw in text.split("\n"):
            # ★ 围栏可能被包在引用块里（`> ```bash`）——本仓大量模板就是这么写的。
            #   只 lstrip 不剥 `>` 会把这类围栏整个看成散文，于是"已经写成可执行语句"的
            #   模板仍被判成「只说不做」（本门自己第一次跑就踩到）。
            line = re.sub(r"^\s*(?:>\s?)+", "", raw)
            if line.lstrip().startswith("```"):
                in_fence = not in_fence
                continue
            if IGNORE_LINE_RE.search(line):
                continue
            for a in ACTIONS:
                if a in line:
                    if in_fence:
                        # ⛔ 含占位符的**模板行**不算可执行落点：`--node '#N'` / `<版本>` 这类
                        #   是教怎么写，不是真调用。实测代价：`phase-0-4.md` 一条 `#N` 模板
                        #   把整个 sprint-autopilot/ 目录喂饱 → 33 处「发 #4」全是注释、
                        #   这道门却全绿，而 #4 恰是冻结时刻唯一对外可见的信号。
                        if _PLACEHOLDER_LINE.search(line):
                            stat[a]["template"] += 1
                        else:
                            stat[a]["fence"] += 1
                    else:
                        stat[a]["prose"] += 1
    return stat


def run(root="."):
    base = os.path.join(root, FLOW_ROOT)
    if not os.path.isdir(base):
        return {"applicable": False, "reason": f"无 {FLOW_ROOT}/", "findings": []}
    findings, scanned = [], 0
    for name in sorted(os.listdir(base)):
        d = os.path.join(base, name)
        if not os.path.isdir(d):
            continue
        scanned += 1
        for a, stat in scan_dir(d).items():
            if stat["prose"] > 0 and stat["fence"] == 0:
                findings.append({
                    "level": "ERROR", "flow": name, "action": a,
                    "prose": stat["prose"],
                    "detail": (f"`{a}`（{ACTIONS[a]}）在 flows/{name}/ 的散文里出现 "
                               f"{stat['prose']} 次，**bash 围栏里 0 次** —— "
                               f"承诺在、执行不在。这类缺陷不报错，只表现为"
                               f"「对应硬门恒 FAIL」或「状态永不更新」，要跑几个 tick 才显形"),
                })
        for fn, line in scan_echo_promises(d):
            findings.append({
                "level": "ERROR", "flow": name, "action": "notify.py",
                "file": fn, "prose": 1,
                "detail": (f"flows/{name}/{fn} 的 bash 围栏里有一句 `{line}` —— "
                           f"**承诺发通知只是 echo 的字符串，同一围栏没有任何 `notify.py` 调用**。"
                           f"这类分支通常正是冻结/熔断出口：版本被挡住而通知渠道零消息，"
                           f"净效果是把「静默空转」换成「静默永冻」"),
            })
    return {"applicable": True, "reason": "", "scanned": scanned,
            "findings": findings, "passed": not findings}


def main():
    ap = argparse.ArgumentParser(description="散文承诺 ↔ 可执行语句对账")
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
    res = run(args.root)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res.get("passed", True) else 1
    if not res["applicable"]:
        print(f"[SKIP] {res['reason']}")
        return 0
    if res["passed"]:
        print(f"[OK] 散文承诺均有可执行落点（巡检 {res['scanned']} 个 flow 目录，"
              f"{len(ACTIONS)} 类动作）")
        return 0
    print(f"[FAIL] 检出 {len(res['findings'])} 处「只说不做」：")
    for f in res["findings"]:
        print(f"  · flows/{f['flow']}/{f.get('file', '')} — {f['detail']}")
    print("  修复：把该动作写成真正的 ```bash 围栏语句（照抄对应模板，别删模板首行的 "
          "`eval \"$(autopilot_tick_flags.py --shell)\"`）；确属纯说明 → 行尾加 "
          "`<!-- proseexec-check: ignore 理由 -->`")
    return 1


if __name__ == "__main__":
    sys.exit(main())
