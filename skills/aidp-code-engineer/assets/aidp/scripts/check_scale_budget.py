#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""规划产物规模 ↔ 档位 对账（软预算，Important 不阻断）。

## 为什么需要

档位判定已有数量区间（S 25~40 / M 60~100 用例），但**没有任何东西回头核对
「实际产出有没有落在区间里」**。实测某版判 M 档、产出 **2266 行用例册 / 86 条用例 /
799 行执行计划 / 748 行需求 / 535 行详设**，而该版 **零建表、零 DDL、零新增接口、
零新增页面**，实际代码改动面 = 后端 9 文件 + 前端 1 文件。
86 条确实落在 M 的 60~100 内 —— 问题不在区间，在**判据太粗**：
`REQ≤15 或 PAGE≤5` 就判 M，而「12 条口径调整」与「12 条新功能」的工作量差一个数量级。

## 两件事

### ① 口径调整型子档（`M⁻`）

REQ 超过 S 的上限、但**新增接口 = 0 且 新增页面 = 0 且 无 DDL** ⇒ 这是**口径调整型**需求：
按 S 档的产出目标走（用例 25~40、设计 1 册合并），而不是 M 的 60~100。
⛔ 判据只看**变更面**（有没有新增接口/页面/表），不看 REQ 条数 ——
条数反映的是"说了几件事"，变更面反映的是"要做几件事"。

### ② 软预算告警

产出超出档位目标区间 ⇒ 报 Important。**⛔ 刻意不硬截断**：
真需要 90 条用例的版本被砍到 40 条，损失的是测试覆盖；而一个告警足以让人回头看一眼
「这版真要这么多吗」。超限不是错误，**超限且没人看过**才是。

退出码：0 = 在预算内 / 不适用；1 = 有超限项（Important）；2 = 入参错。
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aidp_collect import from_result  # noqa: E402

# 档位 → 产出目标（用例数区间 / 设计册数上限 / Task 数上限 / 四族总行数软上限）
BUDGET = {
    "S":  {"cases": (25, 40),  "design_docs": 1, "tasks": 10, "lines": 1200},
    "M-": {"cases": (25, 40),  "design_docs": 1, "tasks": 10, "lines": 1500},
    "M":  {"cases": (60, 100), "design_docs": 3, "tasks": 20, "lines": 3000},
    "L":  {"cases": None,      "design_docs": None, "tasks": None, "lines": None},
}

_CASE_RE = re.compile(r"^\s*#{3,6}\s*(?:用例\s+)?(TC-[A-Za-z0-9_\-]+)", re.M)
_TASK_RE = re.compile(r"^\s*(?:#{1,6}\s+|\|\s*)?(?:Task|任务)\s*[-#]?\s*\d+(?:\.\d+)*", re.M | re.I)


def effective_tier(tier, new_endpoints, new_pages, has_ddl):
    """把「口径调整型」从 M 里分出来。

    ⛔ 只看变更面：新增接口 / 新增页面 / DDL 全为零 ⇒ 不管 REQ 多少条，
      要做的事就是改既有实现的口径，产出目标该按 S 走。
    """
    if tier != "M":
        return tier, ""
    if new_endpoints == 0 and new_pages == 0 and has_ddl is False:
        return "M-", ("零新增接口 + 零新增页面 + 无 DDL ⇒ 口径调整型，"
                      "产出目标按 S 档（REQ 条数反映「说了几件事」，"
                      "变更面才反映「要做几件事」）")
    return "M", ""


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read(800_000)
    except OSError:
        return None


def measure(root, version):
    """量四族产出：用例数 / 设计册数 / Task 数 / 总行数。"""
    base = os.path.join(root, "docs")
    fams = {
        "req": os.path.join(base, "requirements", version, "研发需求"),
        "design": os.path.join(base, "design", "detail", version),
        "plan": os.path.join(base, "plans", version),
        "cases": os.path.join(base, "testing", version, "研发自测"),
    }
    out = {"cases": 0, "design_docs": 0, "tasks": 0, "lines": 0,
           "files": 0, "files_failed": 0, "dirs_present": []}
    for fam, d in fams.items():
        if not os.path.isdir(d):
            continue
        out["dirs_present"].append(fam)
        for dp, _dn, fns in os.walk(d):
            for fn in sorted(fns):
                if not fn.endswith(".md") or fn == "README.md" or fn.startswith(("_", "00_", "99_")):
                    continue
                text = _read(os.path.join(dp, fn))
                if text is None:
                    out["files_failed"] += 1
                    continue
                out["files"] += 1
                out["lines"] += text.count("\n") + 1
                if fam == "cases":
                    out["cases"] += len(set(_CASE_RE.findall(text)))
                elif fam == "plan":
                    out["tasks"] += len(_TASK_RE.findall(text))
                elif fam == "design" and not fn.startswith(("00_", "_", "9")):
                    out["design_docs"] += 1
    return out


def run(root, version, tier, new_endpoints, new_pages, has_ddl):
    eff, why = effective_tier(tier, new_endpoints, new_pages, has_ddl)
    got = measure(root, version)
    budget = BUDGET.get(eff) or BUDGET["L"]
    findings = []

    if not got["dirs_present"]:
        res = {"applicable": False,
               "reason": "docs/{requirements,design,plans,testing}/%s 四族目录均不存在，"
                         "规划产物尚未产出" % version}
        res.update(from_result(res).as_json())
        return res

    if got["files_failed"]:
        findings.append({"item": "采集失败", "got": got["files_failed"], "budget": "0",
                         "detail": "有文件未读到，本轮产出规模未完整核验"})
    rng = budget["cases"]
    if rng and "cases" in got["dirs_present"] and not got["cases"]:
        findings.append({"item": "用例数", "got": 0, "budget": "%d~%d" % rng,
                         "detail": "未识别出任何用例，本项未核验；检查用例生成和标题形态"})
    if rng and got["cases"] and not (rng[0] <= got["cases"] <= rng[1]):
        findings.append({
            "item": "用例数", "got": got["cases"], "budget": "%d~%d" % rng,
            "detail": "%s 档目标 %d~%d 条，实际 %d 条 —— %s"
                      % (eff, rng[0], rng[1], got["cases"],
                         "超出：确需这么多请在审计里写明理由，否则考虑降档"
                         if got["cases"] > rng[1] else "偏少：确认覆盖是否完整")})
    for key, label in (("design_docs", "设计册数"), ("tasks", "Task 数"), ("lines", "四族总行数")):
        cap = budget[key]
        if cap and got[key] > cap:
            findings.append({
                "item": label, "got": got[key], "budget": "≤%d" % cap,
                "detail": "%s 档上限 %d，实际 %d —— 超限不是错误，"
                          "**超限且没人看过**才是；回头确认这版真要这么多"
                          % (eff, cap, got[key])})

    res = {
        "applicable": True, "reason": "",
        "version": version, "tier": tier, "effective_tier": eff,
        "tier_note": why,
        "measured": got, "budget": budget,
        "findings": findings,
        "severity": "Important",      # ⛔ 不阻断：硬截断会砍掉真需要的覆盖
        "files": got["files"], "checked": got["cases"] + got["tasks"],
    }
    res.update(from_result(res, targets=got["files"],
                           items=got["cases"] + got["tasks"]).as_json())
    return res


def self_check():
    """阳性对照：造一个必然超限的 M⁻ 档产出 → 必须报。"""
    import shutil
    import tempfile
    d = tempfile.mkdtemp()
    try:
        cases_dir = os.path.join(d, "docs/testing/V9.9.9/研发自测")
        os.makedirs(cases_dir)
        body = "\n".join("#### 用例 TC-X-%03d\n正文\n" % i for i in range(1, 90))
        with open(os.path.join(cases_dir, "02_全量自测用例.md"), "w", encoding="utf-8") as f:
            f.write(body)
        res = run(d, "V9.9.9", "M", new_endpoints=0, new_pages=0, has_ddl=False)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    hit = [f for f in res.get("findings") or [] if f["item"] == "用例数"]
    ok = res.get("effective_tier") == "M-" and bool(hit)
    print(json.dumps({"self_check": "pass" if ok else "fail",
                      "effective_tier": res.get("effective_tier"),
                      "findings": res.get("findings")}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".")
    ap.add_argument("--version")
    ap.add_argument("--tier", default=None, choices=sorted(BUDGET))
    ap.add_argument("--from-baseline", action="store_true", help="读取本版本 req_scale 的整版档位与结构事实")
    ap.add_argument("--new-endpoints", type=int, default=None)
    ap.add_argument("--new-pages", type=int, default=None)
    ddl = ap.add_mutually_exclusive_group()
    ddl.add_argument("--has-ddl", action="store_true", dest="has_ddl", default=None)
    ddl.add_argument("--no-ddl", action="store_false", dest="has_ddl")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-check", action="store_true")
    a = ap.parse_args()
    if a.self_check:
        return self_check()
    if not a.version:
        print("[check_scale_budget] 必须传 --version", file=sys.stderr)
        return 2

    tier = a.tier or "M"
    if a.from_baseline:
        from aidp_paths import baseline
        try:
            with open(baseline(a.root), encoding="utf-8") as fh:
                facts = json.load(fh)["versions"][a.version]["req_scale"]
            tier = a.tier or facts["tier"]
            if tier not in BUDGET:
                raise ValueError("未知档位：%s" % tier)
            # 只使用明确的新增数量，不把受影响页面数当作新增页面数。
            a.new_endpoints = facts.get("new_endpoints", a.new_endpoints)
            a.new_pages = facts.get("new_pages", a.new_pages)
            a.has_ddl = facts.get("has_ddl", a.has_ddl)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print("规模事实不可用：%s" % exc, file=sys.stderr)
            return 2
    res = run(os.path.abspath(a.root), a.version, tier,
              a.new_endpoints, a.new_pages, a.has_ddl)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        if not res.get("applicable"):
            print("[SKIP] %s" % res.get("reason"))
        else:
            if res.get("tier_note"):
                print("ℹ️ 档位细化：%s → %s（%s）"
                      % (res["tier"], res["effective_tier"], res["tier_note"]))
            m = res["measured"]
            print("[规模对账] %s %s 档：用例 %d / 设计册 %d / Task %d / 四族 %d 行"
                  % (res["version"], res["effective_tier"],
                     m["cases"], m["design_docs"], m["tasks"], m["lines"]))
            for f in res["findings"]:
                print("  [Important] %s：%s（目标 %s）—— %s"
                      % (f["item"], f["got"], f["budget"], f["detail"]))
            if not res["findings"]:
                print("  ✅ 各项均在档位目标内")
    return 1 if res.get("findings") else 0


if __name__ == "__main__":
    sys.exit(main())
