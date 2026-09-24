#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_script_callers.py — 「确定性脚本没有调用方」门（护栏必须有调用方）。

本仓的铁律是 **没有调用方的护栏等于不存在**。既有的
`check_skill_ref_freshness.py::unreferenced_scripts` 只管 **SKILL 自带的**
`{{AIDP_HOME}}/skills/*/scripts/`（见其 docstring），而 `{{AIDP_HOME}}/scripts/` 下的
上百个脚本**一个都不在它的巡检面内**——于是一个脚本可以写完、进 README 目录、
然后永远不被任何命令/流程/门调用，而全仓所有检查都是绿的。

⚠️ **失效形态是「写了就等于接了」**：脚本的 docstring 写着自己是「唯一实现」，
README 里也有它的条目，读者据此以为它在跑。实测代价：`aiauto_readiness.py`
自称是客户端 MCP 运行期前置的判定者，从落地到本门上线**零调用方**——
非 Web 项目的四态前置从来没有被评估过，而报告全绿。

## 判据（确定性，零语义推断）

对 `{{AIDP_HOME}}/scripts/` 下每个顶层 `*.py`（不含 `tests/`、`__pycache__`），
只要命中下列任一即视为**已接线**：

1. 被**契约正文**按名提到：`commands/` `flows/` `agents/` `rules/` `reference/`
   `hooks/` `templates/` `skills/` 下任一 `.md`；
2. 被同仓任一 `.py` **import 或以子进程调起**（含脚手架 `verify.py` 的门登记表、
   `{{AIDP_HOME}}/scripts/tests/` 的单测）；
3. 被 `.github/workflows/` 下的 CI 配置调起；
4. 登记在同目录 `script-callers-baseline.txt`（**人工裁定一次、落盘留痕**）。

⛔ **`selfcheck.py` 的探针登记表【不算】调用方**——探针证明的是「这个检查抓得到东西」，
不是「有人在生产路径上跑它」；只登记探针而没接进 `verify.py` 的门，正是本门要抓的形态。
⛔ **`{{AIDP_HOME}}/scripts/README.md` 里的条目【不算】调用方**——它是目录索引，
「在目录里有一行」恰恰是孤儿脚本最典型的伪装。⛔ 脚本自己的文件内容也不算
（否则每个脚本都自证已接线，与 `check_skill_ref_freshness` 当年踩的是同一个坑：
让被检查方自己出具合格证明）。

退出码：0 = 全部有调用方；1 = 有孤儿；2 = 入参/环境错。
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

BASELINE_NAME = "script-callers-baseline.txt"
SCRIPTS_DIR = runtime_text('__AIDP_HOME__/scripts', __file__)
# 契约正文面：这些目录里的 .md 提到脚本名 = 真实接线
DOC_DIRS = tuple(runtime_text('__AIDP_HOME__/%s' % d, __file__) for d in (
    "commands", "flows", "agents", "rules", "reference", "hooks", "templates", "skills"))
# ⛔ README 是目录索引，不是调用方 —— 孤儿脚本最典型的伪装就是「README 里有一行」
DOC_EXCLUDE_BASENAMES = {"README.md"}
# ⛔ `selfcheck.py` 的探针登记表**不算调用方**：探针证明的是「这个检查确实抓得到东西」，
#   不是「有人在生产路径上跑它」。把它算进来，一个只登记了探针、却没接进 verify.py 的门
#   会被判成已接线 —— 而那正是本门要抓的形态。
PY_EXCLUDE_BASENAMES = {"selfcheck.py"}
# .py 调用面：全仓（脚本互相 import / 子进程调起 / 单测 / 脚手架探针注册）
PY_DIRS = (SCRIPTS_DIR, os.path.join("skills", "aidp-code-engineer", "scripts"))
CI_DIRS = (os.path.join(".github", "workflows"),)
SKIP_DIRNAMES = {"__pycache__", "assets"}


def _baseline(root):
    fp = os.path.join(root, SCRIPTS_DIR, BASELINE_NAME)
    out = {}
    if not os.path.isfile(fp):
        return out
    for ln in open(fp, encoding="utf-8", errors="replace").read().splitlines():
        body, _, why = ln.partition("#")
        body = body.strip()
        if body:
            out[body] = why.strip()
    return out


def _walk(root, base, suffixes):
    d = os.path.join(root, base)
    if not os.path.isdir(d):
        return
    for dirpath, dn, fns in os.walk(d):
        dn[:] = [x for x in dn if x not in SKIP_DIRNAMES]
        for fn in sorted(fns):
            if fn.endswith(suffixes):
                yield os.path.join(dirpath, fn)


def run(root="."):
    scripts = sorted(
        fn for fn in os.listdir(os.path.join(root, SCRIPTS_DIR))
        if fn.endswith(".py") and os.path.isfile(os.path.join(root, SCRIPTS_DIR, fn))
    ) if os.path.isdir(os.path.join(root, SCRIPTS_DIR)) else []

    corpus = []
    for base in DOC_DIRS:
        for p in _walk(root, base, (".md",)):
            if os.path.basename(p) in DOC_EXCLUDE_BASENAMES:
                continue
            corpus.append((p, _read(p)))
    for base in PY_DIRS:
        for p in _walk(root, base, (".py",)):
            if os.path.basename(p) in PY_EXCLUDE_BASENAMES:
                continue
            corpus.append((p, _read(p)))
    for base in CI_DIRS:
        for p in _walk(root, base, (".yml", ".yaml")):
            corpus.append((p, _read(p)))

    waived = _baseline(root)
    orphans, wired = [], 0
    for scr in scripts:
        stem = scr[:-3]
        # ⚠️ 必须同时认**裸模块名**：`verify.py` 的门登记表用的是字符串 `"check_xxx"`（动态 import），
        #   只认 `check_xxx.py` 会把一批真实接线的门误判成孤儿 —— 假红常驻 = 硬门迟早被关掉。
        pat = re.compile(r"\b%s(?:\.py)?\b" % re.escape(stem))
        hit = None
        for p, text in corpus:
            if os.path.basename(p) == scr and os.path.dirname(p).endswith(SCRIPTS_DIR):
                continue  # ⛔ 自证不算
            if pat.search(text):
                hit = p
                break
        if hit:
            wired += 1
        elif scr in waived:
            wired += 1
        else:
            orphans.append({
                "script": "%s/%s" % (SCRIPTS_DIR, scr),
                "reason": "无任何调用方（契约正文 / .py / CI 均未提及；README 条目不算）",
                "fix": "把它接进真实调用方（命令 Step / flow 分片 / verify.py 的门 / "
                       "selfcheck 探针），或在 %s/%s 登记并写明理由" % (SCRIPTS_DIR, BASELINE_NAME),
            })
    # ⚠️ `findings` 是骨架 `selfcheck.py::_run` 认得的计数键；只出 `orphans` 会让阳性对照
    #   数不出增量、探针永远"没变红"。`orphans` 保留为别名供人读。
    return {"scanned_scripts": len(scripts), "wired": wired,
            "findings": orphans, "orphans": orphans, "passed": not orphans}


def _read(p):
    try:
        return open(p, encoding="utf-8", errors="replace").read()
    except OSError:
        return ""


def main():
    ap = argparse.ArgumentParser(description="确定性脚本没有调用方门")
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
        for o in res["orphans"]:
            print("[ERROR] %s %s" % (o["script"], o["reason"]))
            print("        → %s" % o["fix"])
        print("巡检 %d 个脚本：%d 个已接线，%d 个孤儿"
              % (res["scanned_scripts"], res["wired"], len(res["orphans"])))
    return 0 if res["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
