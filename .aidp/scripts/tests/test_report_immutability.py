#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试链三处缺口回归：第三重锁空转 / renderMode 零校验 / 3i 触发窗口。

三条的共同形态是**门存在但走不到**（或存在但从没被调用）：
· 报告不可变的第三重锁只判**当前 build** 且只在 `--stage final` 跑，而唯一的 final 门
  跑在 R-4 finalize **之前** ⇒ 判据每次都走「尚未 finalize，无可篡改」跳过，一次都没真判过；
· `renderMode` 契约写着「严禁回落成模板示例值」，`emit-report.py` 里 grep 命中 0；
· 3i（报告 driver 如实性）只在 final 跑，而 Phase 3.7 在未收敛轮整步跳过 ⇒ 中间报告不过比对。
"""
import json
import os
import subprocess
import sys
import tempfile
import shutil
import datetime
import hashlib
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
GATE = str(REPO / ".aidp/scripts/autopilot-ceremony-gate.py")

_passed = _failed = 0


def check(name, cond):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ✅ {name}")
    else:
        _failed += 1
        print(f"  ❌ FAIL: {name}")


def _gate(root, build, stage, browser=1, extra=()):
    cp = subprocess.run([sys.executable, GATE, "check", "--version", "V0.1", "--build", build,
                         "--stage", stage, "--will-browser-test", str(browser),
                         "--repo-root", str(root), "--notify", "0",
                         "--no-advance-run-state", *extra],
                        capture_output=True, text=True)
    return cp.stdout + cp.stderr


def _digest(payload):
    core = {k: v for k, v in payload.items() if k != "_integrity"}
    return "sha256:" + hashlib.sha256(json.dumps(core, ensure_ascii=False, sort_keys=True,
                                                 separators=(",", ":")).encode("utf-8")).hexdigest()


def _mk_reports(root, build, *, finalized_at=None, tamper=False, amend=False,
                driver_claim=None, driver_actual=None, cases=None, no_integrity=False,
                deliveries=None):
    """tamper = 定稿后改内容未同步摘要；amend = 定稿后改内容并重算摘要 + amendments 留痕。"""
    for cn in ("AI执行报告", "AI测试报告"):
        (root / f"docs/reports/V0.1/{cn}/data").mkdir(parents=True, exist_ok=True)
    payload = {"cases": cases or [], "defects": []}
    if driver_claim:
        payload["driver"] = driver_claim
    if not no_integrity:
        payload["_integrity"] = _digest(payload)
    if deliveries is not None:
        deliveries[build] = {"exec_report": {"delivery": "local", "integrity": payload.get("_integrity")},
                             "test_report": {"delivery": "local", "integrity": payload.get("_integrity")}}
    if tamper:
        payload["defects"] = [{"id": "X"}]
    if amend:
        payload["defects"] = [{"id": "X"}]
        payload["amendments"] = [{"at": "2026-09-16T11:00:00+08:00", "reason": "修笔误"}]
        payload["_integrity"] = _digest(payload)
    for cn in ("AI执行报告", "AI测试报告"):
        f = root / f"docs/reports/V0.1/{cn}/data/{build}.js"
        f.write_text("window.__A__=window.__A__||[];window.__A__.push("
                     + json.dumps(payload, ensure_ascii=False) + ");", encoding="utf-8")
        if finalized_at:
            # 文件 mtime 恒晚于定稿（模拟新 clone / 切分支）：判据与 mtime 无关
            ts = datetime.datetime.fromisoformat(finalized_at).timestamp()
            os.utime(f, (ts + 7200,) * 2)
    entry = {"build": build}
    if finalized_at:
        entry.update(ai_report_finalized=True, ai_report_finalized_at=finalized_at)
    if driver_actual:
        entry["driver_actual"] = driver_actual
    return entry


def test_immutability_lock_is_live():
    """第三重锁必须扫本版全部已 finalize 的 build，而不是只看 current_build。"""
    print("\n[T2] 报告不可变第三重锁（此前近乎空转）")
    FIN = "2026-09-16T10:00:00+08:00"

    def scene(tamper, amend=False, stage="skeleton", no_integrity=False, rehash=False):
        root = Path(tempfile.mkdtemp())
        dl = {}
        old = _mk_reports(root, "V0.1_build1001", finalized_at=FIN, tamper=tamper, amend=amend,
                          no_integrity=no_integrity, deliveries=dl)
        if rehash:      # 改内容并重算内嵌摘要，但无 amendments 留痕 → 与交付台账摘要不符
            for cn in ("AI执行报告", "AI测试报告"):
                f = root / f"docs/reports/V0.1/{cn}/data/V0.1_build1001.js"
                pl = {"cases": [], "defects": [{"id": "Y"}]}
                pl["_integrity"] = _digest(pl)
                f.write_text("window.__A__=window.__A__||[];window.__A__.push(" + json.dumps(pl) + ");",
                             encoding="utf-8")
        cur = _mk_reports(root, "V0.1_build1002")
        (root / "memory").mkdir()
        (root / "memory/.sprint-autopilot-baseline.json").write_text(json.dumps(
            {"versions": {"V0.1": {"current_build": "V0.1_build1002", "builds": [old, cur]}},
             "report_deliveries": dl}),
            encoding="utf-8")
        out = _gate(root, "V0.1_build1002", stage)
        shutil.rmtree(root, ignore_errors=True)
        return "\n".join(l for l in out.splitlines() if "报告不可变性" in l)

    check("★ 阳性：历史 build 已 finalize 后 data 被改 → FAIL（当前 build 是另一个）",
          "❌" in scene(True))
    check("★ 阳性：在 skeleton 阶段就能抓到（改前只有 final 判、而 final 跑在 finalize 之前）",
          "❌" in scene(True, stage="skeleton"))
    check("★ 阴性：未改动但文件 mtime 晚于定稿（新 clone / 切分支）→ 放行", "✅" in scene(False))
    check("★ 阳性：缺 _integrity 摘要 → FAIL", "❌" in scene(False, no_integrity=True))
    check("★ 阳性：改内容并重算内嵌摘要、无 amendments → 与交付台账摘要不符 → FAIL",
          "❌" in scene(False, rehash=True))
    check("★ 阴性：改动但有晚于 finalize 的 amendments 留痕 → 放行（合法修订）",
          "✅" in scene(False, amend=True))

    # 零误报：本版没有任何已 finalize 的 build 时，本项整段不出现
    root = Path(tempfile.mkdtemp())
    cur = _mk_reports(root, "V0.1_build1001")
    (root / "memory").mkdir()
    (root / "memory/.sprint-autopilot-baseline.json").write_text(json.dumps(
        {"versions": {"V0.1": {"current_build": "V0.1_build1001", "builds": [cur]}}}), encoding="utf-8")
    out = _gate(root, "V0.1_build1001", "skeleton")
    shutil.rmtree(root, ignore_errors=True)
    check("★ 零误报：无已 finalize 的 build → 本项不出现（不恒红也不假绿报通过）",
          "报告不可变性" not in out)


def test_driver_truthfulness_window():
    """3i 前移到 skeleton，但以「第二信源已存在」为前提。"""
    print("\n[T3] 报告 driver 如实性的触发窗口")

    def scene(stage, actual, claim):
        root = Path(tempfile.mkdtemp())
        e = _mk_reports(root, "V0.1_build1001", driver_claim=claim, driver_actual=actual)
        (root / "memory").mkdir()
        (root / "memory/.sprint-autopilot-baseline.json").write_text(json.dumps(
            {"versions": {"V0.1": {"current_build": "V0.1_build1001", "builds": [e]}}}), encoding="utf-8")
        out = _gate(root, "V0.1_build1001", stage)
        shutil.rmtree(root, ignore_errors=True)
        return "\n".join(l for l in out.splitlines() if "如实" in l)

    check("★ 阳性：skeleton 阶段抓到「自述 cli / 实际 mcp」（下游真实事故形态；改前只有 final 能判）",
          "❌" in scene("skeleton", "mcp", "cli") and "报告失真" in scene("skeleton", "mcp", "cli"))
    check("对照：同样数据在 final 阶段同样抓到（前移未改变原有行为）",
          "❌" in scene("final", "mcp", "cli"))
    check("★ 阴性：skeleton 且无 driver_actual → 整项跳过（⛔ 不假红、不 DEGRADE 刷屏）",
          scene("skeleton", None, "cli") == "")
    check("阴性：自述与实际一致 → 放行", "✅" in scene("skeleton", "cli", "cli"))

    g = (REPO / ".aidp/scripts/autopilot-ceremony-gate.py").read_text(encoding="utf-8")
    check("★ 3p/3q 刻意不前移（骨架期 cases[] 恒空，3q 会必然假红）",
          "3p/3q **刻意不前移**" in g)


def test_render_mode_provenance():
    """renderMode 有值必须带取证来源——此前 emit-report.py 对它零校验。"""
    print("\n[T4] renderMode 取证来源校验")
    import importlib.util
    spec = importlib.util.spec_from_file_location("er", REPO / ".aidp/scripts/emit-report.py")
    er = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(er)
    base = {"build": "b", "version": "v", "buildNo": 1,
            "summary": {"total": 1, "pass": 1, "passRate": 1.0},
            "cases": [{"id": "TC-1", "title": "t", "result": "pass"}]}

    def errs(extra):
        p = dict(base)
        p.update(extra)
        return [e for e in er.validate_payload("test", p) if "renderMode" in e]

    check("★ 阳性：模板示例值被原样留下（有值却无来源）→ 报错",
          bool(errs({"renderMode": "headless"})))
    check("阳性：枚举非法 → 报错",
          bool(errs({"renderMode": "headfull", "renderModeSource": "运行取证(ps)"})))
    check("★ 阳性：来源不在契约四选一内 → 报错（防随手写一句糊弄）",
          bool(errs({"renderMode": "headless", "renderModeSource": "就是无头"})))
    check("阴性：值 + 合规来源 → 通过",
          not errs({"renderMode": "headless", "renderModeSource": "运行取证(ps 查 --headless)"}))
    check("★ 阴性：取不到写 null → 通过（契约要求的正确姿势，⛔ 不得因此报错逼人编值）",
          not errs({"renderMode": None}))


def main():
    test_immutability_lock_is_live()
    test_driver_truthfulness_window()
    test_render_mode_provenance()
    print(f"\n══ 结果：{_passed} passed / {_failed} failed ══")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
