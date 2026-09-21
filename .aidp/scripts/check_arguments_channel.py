#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`$ARGUMENTS` 接收通道完整性门。

## 它堵的是哪一类失效

`$ARGUMENTS` 是**斜杠命令正文的 runtime 文本替换**——只有 `AIDP_HOME/commands/<cmd>.md` 里
真的写了这个字样，宿主才会把用户输入替换进去。而 flow 分片是被 `Read` 进来的**普通文本**，
`${ARGUMENTS:-}` 在那里只是一个未设置的 shell 变量。

于是形成一个**恰好落在最要命处**的缺口：某命令把入参解析放在 flow 分片里做
（`autopilot_tick_flags.py parse --arguments "${ARGUMENTS:-}"`），命令正文却没写 `$ARGUMENTS`
→ 解析器恒收空串 → **全部 flag 落 0**。实测两条 7×24 loop 命令曾同时踩中：
`--unattended` 收不到 → `LOOP_UNATTENDED=0` → Phase 1 输出引导文案后退出，
**每 tick 刷一屏引导、永不开工**；而全仓另外 13 个命令都写了这一行。

失败形态是「读起来完全正确」：flow 里那句解析写得一丝不苟，只是它拿到的永远是空串。

## 判据

对每个 `AIDP_HOME/commands/<cmd>.md`：若 `<cmd>` 自己或它的 `AIDP_HOME/flows/<cmd>/**` 里
出现了 `$ARGUMENTS` / `${ARGUMENTS`，则**命令正文**必须也出现 `$ARGUMENTS` —— 否则 ERROR。

⛔ 只查「用了却没声明」，不查反向（命令正文声明了但没人用是无害的）。

## 豁免

行尾 `<!-- argch-check: ignore 理由 -->`。

退出码：`0`=通道齐备（或不适用）/ `1`=有命令用了却没声明 / `2`=用法错。
"""
import sys as _aidp_sys
from pathlib import Path as _AidpPath
_aidp_scripts = str(_AidpPath(__file__).resolve().parent)
if _aidp_scripts not in _aidp_sys.path:
    _aidp_sys.path.insert(0, _aidp_scripts)
from aidp_runtime import runtime_text
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
import sys

CMD_DIR = os.path.join(runtime_relpath("", __file__), "commands")
FLOW_DIR = os.path.join(runtime_relpath("", __file__), "flows")
ARG_RE = re.compile(r"\$\{?ARGUMENTS\b")
IGNORE_RE = re.compile(r"<!--\s*argch-check:\s*ignore\b")


def _read(p):
    try:
        return open(p, encoding="utf-8", errors="replace").read()
    except OSError:
        return ""


def _uses(text):
    return any(ARG_RE.search(ln) and not IGNORE_RE.search(ln)
               for ln in text.split("\n"))


def run(root="."):
    cmd_base = os.path.join(root, CMD_DIR)
    if not os.path.isdir(cmd_base):
        return {"applicable": False, "reason": f"无 {CMD_DIR}/", "findings": []}
    findings, scanned = [], 0
    for fn in sorted(os.listdir(cmd_base)):
        if not fn.endswith(".md") or fn == "README.md":
            continue
        cmd = fn[:-3]
        scanned += 1
        body = _read(os.path.join(cmd_base, fn))
        declared = _uses(body)

        flow_uses, where = False, []
        fd = os.path.join(root, FLOW_DIR, cmd)
        if os.path.isdir(fd):
            for dp, _dn, fns in os.walk(fd):
                for f in sorted(fns):
                    if not f.endswith(".md"):
                        continue
                    t = _read(os.path.join(dp, f))
                    if _uses(t):
                        flow_uses = True
                        where.append(os.path.relpath(os.path.join(dp, f), root))
        if (flow_uses or declared) and not declared:
            findings.append({
                "level": "ERROR", "command": cmd, "used_in": where[:4],
                "detail": (runtime_text(f"`/{cmd}'` 的 flow 分片里读了 `$ARGUMENTS`，但**命令正文没有声明它** —— `$ARGUMENTS` 只在 `__AIDP_HOME__/commands/*.md` 里被 runtime 文本替换，flow 是 Read 进来的普通文本 → 解析器恒收空串 → **全部 flag 落 0**'", __file__)),
            })
    return {"applicable": True, "reason": "", "scanned": scanned,
            "findings": findings, "passed": not findings}


def main():
    ap = argparse.ArgumentParser(description="$ARGUMENTS 接收通道完整性")
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
        print(f"[OK] `$ARGUMENTS` 接收通道齐备（巡检 {res['scanned']} 个命令）")
        return 0
    print(f"[FAIL] 检出 {len(res['findings'])} 个命令用了 `$ARGUMENTS` 却没在命令正文声明：")
    for f in res["findings"]:
        print(f"  · /{f['command']} — 使用处：{', '.join(f['used_in']) or '命令正文自身'}")
        print(f"    {f['detail']}")
    print("  修复：在命令正文加一行 `参数：$ARGUMENTS`（照抄其它命令的写法）")
    return 1


if __name__ == "__main__":
    sys.exit(main())
