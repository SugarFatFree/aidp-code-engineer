#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""命令端写死「SKILL 阻断/不可豁免名单」的棘轮门。

## 它堵的是哪一类失效

SKILL 与命令端各自独立迭代（约定 16）。它们**改一份名单**——比如把
「不可豁免 = 维度 1/3/5/7」改成「凡标 `Critical` 的一律不可豁免，判据就是标记本身」——
本仓这边不会有任何人想起来去改。而命令端那份写死的编号名单**只会比新规则窄**，
窄掉的那几档就此静默放过。

实测（2026-09-06 `auto-test-runner` 升级）：SKILL 把不可豁免集合从 4 条扩到 9 条
（新增维度 2 标题级 Critical + 4 条「折入本维度，Critical」的子核查），命令端
`flows/sprint-aiauto-test/phase-3-1.md` 仍写「维度 1 / 3 / 5 / 7 任一不通过 → 阻断」，
于是**维度 2「驱动适配层四能力完备」失败只告警不阻断**——驱动四能力残缺时那一轮的
"全绿"结论根本无效，build 却被当成通过关闭；「值级断言硬约束」（专拦"仅凭页面加载就判 pass"
这一全绿式漏测主形态）同样被降为告警。

⚠️ **这一次两道既有 SKILL 引用门（`check_skill_ref_drift` / `check_skill_ref_freshness`）
都返回 0 findings**：它们查的是「编号是否存在」「计数是否等于最大编号」「脚本是否还在」，
查不出「一份语义名单已经不再是权威」。本门补这块。

## 判据（**由上游自己的声明驱动**，不靠本脚本猜哪些编号属于谁）

⚠️ 先说清**为什么不能只按编号形态判**：本仓自己也有大量编号命名空间——
`aidp-compliance` 的 4 个语义维度、`/health-check` 的 10 个检查项、
`/sprint-design` step-1.7 那张自有回检表（其「检查项 2 / 4 / 6」与 `dev-logic-architect`
的检查项 2/4/6 是完全不同的东西）。按「出现 `维度 N/M/K` 就报」必然满屏误报，
而按「同行有 SKILL 名才报」又会漏掉真正的判定行（它往往只写编号、不写归属）。
两种收窄都不成立，**所以判据必须来自上游自己**。

**驱动信号**：某个 SKILL 在自己的文件里**显式声明了「不另立名单」**
（`不另立名单` / `此处不另列名单` / `判据就是标记本身` 等字样）——这是上游在说
「我的这份集合会变，谁也别抄」。凡声明过的 SKILL，本仓契约正文里就**不得**再出现
归属于它的编号枚举。

**命中条件**（同一行三者齐备）：
1. 该行出现**已声明「不另立名单」的 SKILL** 的归属标识（目录名或其自带文件名）；
2. 该行出现 **≥2 个编号的枚举**：`维度 1 / 3 / 5 / 7`、`检查项 34、35` 等；
3. 未被行尾豁免注释放行。

命中即 ERROR。正确写法是**指向 SKILL 的判据本身**（"凡在 <清单> 中标 Critical 的
一律不可豁免，以标记为准"），而不是把那一刻的名单抄过来。

## 豁免

行尾 `<!-- skillgate-check: ignore 理由 -->`。**原因必须写**——豁免本身要可被审计。
真正需要豁免的只有一种：本仓自己**就是**那份名单的权威（目前不存在这种情况）。

退出码：`0`=无写死名单 / `1`=检出 / `2`=用法错。
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

SCAN_DIRS = (runtime_text('__AIDP_HOME__/commands', __file__), runtime_text('__AIDP_HOME__/agents', __file__), runtime_text('__AIDP_HOME__/flows', __file__),
             runtime_text('__AIDP_HOME__/reference', __file__), runtime_text('__AIDP_HOME__/rules', __file__))
SKILLS_DIR = runtime_text('__AIDP_HOME__/skills', __file__)
IGNORE_RE = re.compile(r"<!--\s*skillgate-check:\s*ignore\b")
# 上游「我的集合会变、别抄名单」的自我声明
NO_LIST_RE = re.compile(r"(不另立名单|不另列名单|判据就是标记本身)")
# 「维度 1 / 3 / 5」「检查项 34、35」，以及**编号后带括注**的写法
# 「维度 1（两层解耦）/ 3（状态机无残留）/ 5（证据达标）」——真实的名单几乎都是后者，
# ⛔ 不允许括注就会漏掉它自己要抓的那个形态（本门首次自测即被这一点证伪）。
_ANNO = r"(?:\s*[（(][^)）]{0,24}[)）])?"
ENUM_RE = re.compile(r"(维度|检查项|核心原则)\s*\d+" + _ANNO +
                     r"\s*(?:[/、,，]\s*\d+" + _ANNO + r"\s*){1,}")


def _declared_skills(root):
    """{归属标识: SKILL 名} —— 仅收**显式声明过「不另立名单」**的 SKILL。

    归属标识 = SKILL 目录名 + 该 SKILL 内有辨识度的 .md 文件名（`SKILL.md` /
    `README.md` 太通用，会把无关行拉进来）。
    """
    out = {}
    base = os.path.join(root, SKILLS_DIR)
    if not os.path.isdir(base):
        return out
    for name in sorted(os.listdir(base)):
        d = os.path.join(base, name)
        if not os.path.isdir(d):
            continue
        declared, names = False, {name}
        for dp, _dn, fns in os.walk(d):
            if "__pycache__" in dp:
                continue
            for f in fns:
                if not f.endswith(".md"):
                    continue
                if f not in ("SKILL.md", "README.md") and len(f) > 12:
                    names.add(f)
                try:
                    if NO_LIST_RE.search(open(os.path.join(dp, f),
                                              encoding="utf-8", errors="replace").read()):
                        declared = True
                except OSError:
                    pass
        if declared:
            for n in names:
                out[n] = name
    return out


def run(root="."):
    toks = _declared_skills(root)
    if not toks:
        return {"applicable": False,
                "reason": "无 SKILL 声明过「不另立名单」，本门不适用", "findings": []}
    findings, scanned = [], 0
    for d in SCAN_DIRS:
        for dp, _dn, fns in os.walk(os.path.join(root, d)):
            if "__pycache__" in dp:
                continue
            for fn in sorted(fns):
                if not fn.endswith(".md"):
                    continue
                fp = os.path.join(dp, fn)
                rel = os.path.relpath(fp, root).replace(os.sep, "/")
                scanned += 1
                try:
                    text = open(fp, encoding="utf-8", errors="replace").read()
                except OSError:
                    continue
                for i, ln in enumerate(text.split("\n"), 1):
                    if IGNORE_RE.search(ln):
                        continue
                    m = ENUM_RE.search(ln)
                    if not m:
                        continue
                    owner = next((toks[k] for k in toks if k in ln), None)
                    if not owner:
                        continue
                    findings.append({
                        "level": "ERROR", "file": rel, "line": i,
                        "skill": owner, "enum": m.group(0).strip(),
                        "context": ln.strip()[:140],
                    })
    return {"applicable": True, "reason": "", "scanned": scanned,
            "findings": findings, "passed": not findings}


def main():
    ap = argparse.ArgumentParser(description="命令端写死 SKILL 阻断名单的棘轮门")
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
        print(f"[OK] 未写死已声明「不另立名单」的 SKILL 的编号名单（巡检 {res['scanned']} 份 .md，受保护 SKILL {len(set(res.get('declared', []) or [])) or '见 --json'}）")
        return 0
    print(f"[FAIL] 检出 {len(res['findings'])} 处写死的 SKILL 阻断/不可豁免名单"
          f"——SKILL 改了名单这边不会有人想起来改，而写死的那份只会比新规则**窄**：")
    for f in res["findings"]:
        print(f"  · {f['file']}:{f['line']}  归属 `{f['skill']}` · 枚举「{f['enum']}」")
        print(f"      {f['context']}")
    print("  修复：改成**指向 SKILL 判据本身**的写法（如「凡在 <清单> 中标 Critical 的一律不可豁免，"
          "以标记为准」），⛔ 别抄那一刻的名单；确属本仓自有名单 → 行尾加 "
          "`<!-- skillgate-check: ignore 理由 -->`")
    return 1


if __name__ == "__main__":
    sys.exit(main())
