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
import re
import sys
from pathlib import Path
from datetime import datetime


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
    # 延后生成的 Sprint 记录是第二份防丢证据：台账被误删也不能把未生成读成已生成。
    deferred = []
    path = Path(root) / "memory/.sprint-autopilot-baseline.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        sprints = ((data.get("versions") or {}).get(version) or {}).get("sprints") or {}
        deferred = [n for n, s in sprints.items()
                    if isinstance(s, dict) and s.get("case_generation", {}).get("status") == "deferred"]
    except (OSError, ValueError, AttributeError) as exc:
        return {"ok": False, "passed": False, "pending": None, "detail": str(exc)}
    total = max(total, len(deferred))
    return {
        "ok": True, "version": version, "pending": total,
        "case_ledger": case.get("file"), "case_pending": total, "deferred_sprints": deferred,
        "passed": total == 0,
    }


def record_generation(root, version, sprint, reason, complete=False):
    """暂缓时原子登记 baseline + 用例族条目，生成完成须先证明台账已收口且存在用例。"""
    from baseline_edit import LockedBaseline
    from commit_gate import cascade_ledger_paths
    if not re.fullmatch(r"\d{3}", sprint) or not reason.strip():
        raise ValueError("需要三位 Sprint 编号和非空原因")
    ledger = next(Path(p) for fam, p in cascade_ledger_paths(root, version) if fam == "case")
    baseline = Path(root) / "memory/.sprint-autopilot-baseline.json"
    with LockedBaseline(str(baseline), write=True) as b:
        node = b.data.setdefault("versions", {}).setdefault(version, {})
        item = node.setdefault("sprints", {}).setdefault(sprint, {})
        previous = item.get("case_generation") or {}
        if complete:
            pc = __import__("commit_gate").pending_cascade(root)
            case = ((pc.get("versions", {}).get(version) or {}).get("families") or {}).get("case") or {}
            directory = Path(root) / "docs/testing" / version / "研发自测"
            sources = [p for p in directory.glob("*.md") if not p.name.startswith(("_", "00_", "99_"))]
            if case.get("total") or any("TC-" in p.read_text(encoding="utf-8") for p in sources) is False:
                raise ValueError("用例台账尚有待办或正式用例未生成，不得清除欠账")
        elif previous.get("status") == "deferred":
            return previous
        else:
            ledger.parent.mkdir(parents=True, exist_ok=True)
            texts = [Path(p).read_text(encoding="utf-8") for _, p in cascade_ledger_paths(root, version) if Path(p).exists()]
            numbers = [int(n) for text in texts for n in re.findall(r"C-(\d+)", text)]
            cid = "C-%03d" % (max(numbers, default=0) + 1)
            body = ledger.read_text(encoding="utf-8") if ledger.exists() else "# 开发期用例增量\n\n## 待级联\n"
            clean_reason = " ".join(reason.splitlines())
            body += "\n- %s · %s · 延后生成 Sprint-%s 用例：%s · sprint-%s\n" % (
                cid, datetime.now().strftime("%m-%d %H:%M"), sprint, clean_reason, sprint)
            tmp = ledger.with_suffix(".md.tmp")
            tmp.write_text(body, encoding="utf-8")
            os.replace(tmp, ledger)
        item["case_generation"] = {"status": "generated" if complete else "deferred", "reason": reason,
                                   "at": datetime.now().astimezone().isoformat()}
        item["aiauto_test_required"] = bool(complete)
        # 版本级汇总给测试入口消费：任一 Sprint 显式要求实测即要求本版测试；
        # 只有所有已登记 Sprint 都明确 deferred 才能安全跳过。
        sprint_values = [s.get("aiauto_test_required") for s in (node.get("sprints") or {}).values()
                         if isinstance(s, dict) and "aiauto_test_required" in s]
        node["aiauto_test_required"] = any(sprint_values) if sprint_values else bool(complete)
        return item["case_generation"]


def main():
    ap = argparse.ArgumentParser(
        description="实测前门：本版是否还有未级联的用例增量（有 = 测的是老用例集）")
    ap.add_argument("--root", default=".")
    ap.add_argument("--version")   # --self-check 时不需要（见下方分流）
    ap.add_argument("--defer", action="store_true", help="登记暂缓生成和用例族欠账")
    ap.add_argument("--complete", action="store_true", help="正式用例生成且台账收口后清除暂缓标记")
    ap.add_argument("--sprint", default="")
    ap.add_argument("--reason", default="")
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
    if args.defer and args.complete:
        ap.error("--defer 与 --complete 互斥")
    if args.defer or args.complete:
        try:
            result = record_generation(root, args.version, args.sprint, args.reason, args.complete)
        except (OSError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(json.dumps(result, ensure_ascii=False))
        return 0
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
