#!/usr/bin/env python3
"""check_testdata_prereq.py — 用例前置资源对账门（约定 38 产物 ↔ 用例册声明）。

**它回答的唯一问题**：本版用例册声明需要的「前置账号 / 前置数据 / 环境入口」，
在约定 38 的产物 `docs/testing/{V}/研发自测/01_测试环境与账号.md` 里到底有没有？

⛔ **为什么必须有这道门（实际项目中的实测根因）**：autopilot Phase 0 的
「字段缺失统一收集」只管 baseline 与 autopilot_decisions 的配置字段（deployment 等必填段），
**不管用例册声明的前置账号与数据**（批 6 已显式把测试账号划给 `/sprint-aiauto-test`）。
于是执行体可以跑到部署完成、就绪探针都过了，才凭感觉宣称"我需要第二个测试企业账号"
把 AI 测试半环丢回给人——**而那个账号本来就写在 01_测试环境与账号.md 里**，
同一会话里它还读过那个文件。没有任何一步会去做这次对账。

**判据是确定性的，不做模糊解析**：上游 `dev-manual-testcase` 已规定占位符标准格式
`{待用户填写: <字段中文名>}`（其 SKILL.md「入口信息缺失的处理」+ flow-steps.md，全文档统一）。
所以「声明了但没填」= 用例册里残留的占位符，逐个可数、可定位，无需猜测语义。

**它刻意不做的事**：不收集凭据、不改用例册。敏感凭据仍归 `/sprint-aiauto-test` Phase 0.4
（autopilot 0.6 批 6 的既定边界）；本门只产出「对账结论」，把缺口在 Phase 0 就摆出来。

退出码：0 = 对账通过 / 尚无用例册（INFO，规划期未到）；1 = 有缺口；2 = 参数或环境错误。
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

# 上游 dev-manual-testcase 的标准占位符（全文档统一格式）
PLACEHOLDER_RE = re.compile(r"\{待用户填写[:：]\s*([^}]{1,60})\}")
# 约定 38 的机器消费权威文件（/sprint-aiauto-test Phase 0.0.5 与 auto-test-runner 从此读）
ACCOUNT_DOC = "01_测试环境与账号.md"


def _casebook_dir(root, version):
    return os.path.join(root, "docs", "testing", version, "研发自测")


def run(root, version):
    d = _casebook_dir(root, version)
    res = {
        "version": version,
        "casebook_dir": os.path.relpath(d, root),
        "status": "",
        "account_doc_present": False,
        "scanned_files": 0,
        "gaps": [],        # [{file, line, field}] —— 声明了却没填的前置项
        "passed": False,
    }
    if not os.path.isdir(d):
        # 规划期尚未产出用例册（/version Step 2.4.3.5 才生成）——这不是缺陷。
        res["status"] = "no-casebook"
        res["passed"] = True
        return res

    # ⛔ 跳过 `_` 前缀：那是**开发期过程文件**（约定 22 的族增量册），不是用例册。
    #    与上游 check_doc_split.py `collect_sub_docs()` 同口径。扫它会把变更条目里的
    #    占位符当成"用例声明的前置项"，而它压根不是用例。
    files = sorted(f for f in os.listdir(d)
                   if f.endswith(".md") and not f.startswith("_"))
    res["scanned_files"] = len(files)
    # ★ 目录存在但一份用例册都没有（典型：开发期先落了 `_开发期用例增量.md`，规划尚未产出用例）
    #    → 与"目录不存在"同义，判 no-casebook 放行。⛔ 判成 gap 会让 Phase 0 在
    #    规划期之前恒红，而那个红是无从修复的（还没到产用例的时候）。
    if not files:
        res["status"] = "no-casebook"
        res["passed"] = True
        return res
    res["account_doc_present"] = os.path.isfile(os.path.join(d, ACCOUNT_DOC))

    for fn in files:
        p = os.path.join(d, fn)
        try:
            with open(p, encoding="utf-8") as fh:
                lines = fh.read().splitlines()
        except OSError as e:
            res["gaps"].append({"file": fn, "line": 0,
                                "field": "读取失败: %s" % e})
            continue
        for i, line in enumerate(lines, 1):
            for m in PLACEHOLDER_RE.finditer(line):
                res["gaps"].append({"file": fn, "line": i,
                                    "field": m.group(1).strip()})

    if not res["account_doc_present"]:
        # 有用例册却没有约定 38 的账号文件 = 对账无基准，等同全缺
        res["gaps"].append({"file": ACCOUNT_DOC, "line": 0,
                            "field": "约定 38 产物缺失（测试环境与账号文件不存在）"})

    res["status"] = "gaps" if res["gaps"] else "reconciled"
    res["passed"] = not res["gaps"]
    return res


def _record(root, version, res):
    """把对账结论写进 baseline（必须走 baseline_edit.py：两条 /loop 并发写，见 memory/README.md 并发写铁律）。"""
    edit = os.path.join(root, runtime_relpath("", __file__), "scripts", "baseline_edit.py")
    if not os.path.isfile(edit):
        return False
    payload = json.dumps({
        "status": res["status"],
        "gap_count": len(res["gaps"]),
        "gaps": res["gaps"][:20],
        "account_doc_present": res["account_doc_present"],
    }, ensure_ascii=False)
    try:
        # ⛔ 必须走 `--version <V>` 前缀而非拼 `versions.<V>.xxx` 点号路径：
        #    版本号自身含点（V0.14.0），拼进点号路径会被 baseline_edit 的路径解析拆散。
        #    值走 JSON 字面量：parse_value 先 json.loads、失败才当裸字符串。
        r = subprocess.run(
            [sys.executable, edit, "--version", version,
             "set", "testdata_prereq", payload],
            capture_output=True, text=True, timeout=60)
        return r.returncode == 0
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser(description="用例前置资源对账门（约定 38 产物 ↔ 用例册声明）")
    ap.add_argument("--root", default=".")
    ap.add_argument("--version", help="目标版本号，如 V0.14.0")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--record", action="store_true",
                    help="把对账结论写入 baseline versions.{V}.testdata_prereq")
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
    if not args.version:
        print("[ERROR] 必须传 --version", file=sys.stderr)
        return 2

    res = run(root, args.version)
    if args.record:
        res["recorded"] = _record(root, args.version, res)

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        if res["status"] == "no-casebook":
            print("[INFO ] %s 尚无用例册（%s）——规划期未到，本门跳过"
                  % (args.version, res["casebook_dir"]))
        elif res["passed"]:
            print("[OK   ] %s 前置资源对账通过：%d 个用例册文件、0 处未填占位"
                  % (args.version, res["scanned_files"]))
        else:
            for g in res["gaps"]:
                print("[GAP  ] %s:%d 前置项未落账：%s" % (g["file"], g["line"], g["field"]))
            print("对账未通过：%d 处前置项声明了却没填。"
                  "→ 交互式：现在一次性问清并写回 %s；无人值守：保留占位、"
                  "相关用例执行时标 block 继续，⛔ 不得以此为由暂停整轮"
                  % (len(res["gaps"]), ACCOUNT_DOC))
    return 0 if res["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
