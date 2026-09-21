#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_case_ledger_pending.py — 「带着未级联的用例增量去做实测」门（约定 22 × AI 测试链路）。

⛔ **它堵的缺口**：约定 22 的用例族增量册 `_开发期用例增量.md` 里记的是**变更线索**
（一行：`- C-007 · 09-08 · 企业列表增加「已停用」筛选项 · sprint-012`），
**不是可执行用例**——auto-test-runner 要的是 `### 套件 SUITE-*` + `#### 用例 TC-*` +
四要素步骤表。把线索变成用例的是**级联**（`/sprint-selftest --ledger-cascade` 写进 `02_*.md`）。

于是有一个**全静默**的失败态：级联没跑成 → 增量册还攒着 N 条 → 正式用例册里没有对应新用例 →
AI 测试照常跑完**老用例集**、报告**全绿**。而现有的门一个都拦不住：

  · 终态门（`check_cascade_landing --ledger-closed`）判据是「文件存在 ⟺ 确有未决条目」——
    有未决 = 合法保留 = PASS，它管的是"该删没删"，不管"该级联没级联";
  · `/sprint-aiauto-test` 的用例发现只看正式用例册，从不看增量册（这是对的，见上）;
  · 报告里没有任何字段会说"本轮有 N 条变更还没变成用例"。

三处的盲区完全重合，于是「新功能压根没被测」与「新功能测过且没问题」在产物上**完全同形**。

判据（确定性）：本版用例族增量册的待级联条目数 > 0 → 判 pending。
读数复用 `commit_gate.pending_cascade()`，⛔ 不另写正则（两处读数必须一致）。

退出码：0 = 无未级联用例增量（可安心实测）；1 = 有 N 条未级联（覆盖不完整）；2 = 入参/环境错。
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
import sys


def run(root, version):
    sys.path.insert(0, os.path.join(root, runtime_relpath("", __file__), "scripts"))
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        from commit_gate import pending_cascade
    except Exception as exc:                                    # noqa: BLE001
        # fail-closed：读不出来就不能假装"没有未级联"——那正是本门要消灭的静默。
        return {"ok": False, "error": "parser-unavailable", "detail": str(exc),
                "pending": None, "passed": False}
    pc = pending_cascade(root)
    vinfo = (pc.get("versions") or {}).get(version) or {}
    fams = vinfo.get("families") or {}
    case = fams.get("case") or {}
    total = int(case.get("total") or 0)
    return {
        "ok": True, "version": version, "pending": total,
        "case_ledger": case.get("file"), "case_pending": total,
        "passed": total == 0,
    }


def main():
    ap = argparse.ArgumentParser(
        description="实测前门：本版是否还有未级联的用例增量（有 = 测的是老用例集）")
    ap.add_argument("--root", default=".")
    ap.add_argument("--version")   # --self-check 时不需要（见下方分流）
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
    if not args.version:
        print("[ERROR] 必须传 --version", file=sys.stderr)
        return 2
    res = run(root, args.version)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        if not res.get("ok"):
            print("[ERROR] 用例增量读数不可用：%s（fail-closed，不放行）"
                  % res.get("detail"), file=sys.stderr)
        elif res["passed"]:
            print("[OK   ] %s 无未级联的用例增量 —— 正式用例册即本轮完整用例集"
                  % args.version)
        else:
            print("[PEND ] %s 还有 %d 条用例增量【未级联】：%s"
                  % (args.version, res["pending"],
                     res.get("case_ledger")))
            print("        这些变更尚未变成可执行用例（增量册记的是线索、不是 SUITE/TC），")
            print("        现在实测 = 跑的是**老用例集**，全绿也不代表新功能被测过。")
            print("        正确动作：先跑用例族定向级联"
                  "（/sprint-selftest --ledger-cascade），级联完再实测；")
            print("        级联确实跑不动 → 报告须标注「覆盖不完整：N 条未级联」，"
                  "⛔ 不得据此判版本通过。")
    return 0 if res.get("passed") else (2 if not res.get("ok") else 1)


if __name__ == "__main__":
    sys.exit(main())
