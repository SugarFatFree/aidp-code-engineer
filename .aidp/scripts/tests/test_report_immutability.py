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
import re
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


def _flow_block(relative, marker):
    text = (REPO / ".aidp/flows" / relative).read_text(encoding="utf-8")
    return next(block for block in re.findall(r"^[ \t]*```bash\n(.*?)^[ \t]*```", text, re.M | re.S)
                if marker in block).replace("{{AIDP_HOME}}", str(REPO / ".aidp"))


def _retest_scene(root, *, once=False, target=False, finalized=True, build=True, skeleton=True):
    version, current = "V0.1", "V0.1_build1001"
    node = {"last_deployed_at": "2026-09-16T09:00:00+08:00",
            "phase_beta_done_at": "2026-09-16T09:00:00+08:00",
            "aiauto_tested_at": "2026-09-16T10:00:00+08:00",
            "driver_actual_pending": "cli", "build_seq": 1001,
            "pending_clarifications": [{"raised_build": current, "question": "旧轮待确认"}]}
    if build:
        node["current_build"] = current
        node["builds"] = [{"build": current, "status": "closed" if finalized else "running",
                           "started_at": "2026-09-16T08:00:00+08:00",
                           "ai_report_finalized": finalized}]
    flags = {"TARGET_FLAG_VALUE": version if target else "", "HAS_ONCE_FLAG": "1" if once else "0",
             "TARGET_VERSION": version, "LOOP_UNATTENDED": "0", "HAS_WAKE_SOURCE": "0",
             "PREFLIGHT_RUN_ID": "f07-run"}
    data = {"versions": {version: node}, "autopilot": {"target_version": version, "tick": {
        "aiauto-test": flags, "autopilot": {"TARGET_VERSION": version, "ENTRY_MODE": "test-only"}}}}
    baseline = root / "memory/.sprint-autopilot-baseline.json"
    baseline.parent.mkdir(parents=True)
    baseline.write_text(json.dumps(data), encoding="utf-8")
    prd = root / "docs/requirements/V0.1/产品提供/PRD.md"
    prd.parent.mkdir(parents=True)
    prd.write_text("---\ndeployment:\n  mode: local\n---\n", encoding="utf-8")
    if build and skeleton:
        _mk_reports(root, current)
    return baseline, current


def _test_entry_flow(root):
    block = _flow_block("sprint-aiauto-test/phase-0-6.md", 'BASELINE_FILE="memory/')
    # EXIT trap 同时观察正常落尾与交接 early-exit，不替换任何生产判断或脚本。
    trap = 'trap \'printf "\\n__STATE__%s|%s|%s\\n" "${NEED_HANDOFF:-0}" "${BUILD:-}" "${REPORT_ENABLED:-}"\' EXIT\n'
    result = subprocess.run(["bash", "-c", trap + block], cwd=root, capture_output=True, text=True, timeout=60)
    state = result.stdout.rsplit("__STATE__", 1)[-1].strip().split("|")
    return result, state


def test_finalized_build_routes_to_handoff_before_testing():
    print("\n[F07] 实际 Phase 0.2 围栏：定稿 build 的显式复测必须先交接")
    for flag in ("once", "target"):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            baseline, old = _retest_scene(root, **{flag: True})
            before = json.loads(baseline.read_text())["versions"]["V0.1"]
            result, state = _test_entry_flow(root)
            after = json.loads(baseline.read_text())["versions"]["V0.1"]
            check(f"--{flag}: 已定稿且骨架齐全仍触发交接", result.returncode == 0 and state == ["1", old, "1"])
            check(f"--{flag}: 开测前不认领旧 build 驱动或归档旧待确认项",
                  after["builds"] == before["builds"] and
                  after.get("pending_clarifications") == before["pending_clarifications"])
            check(f"--{flag}: 测试侧不自行铸号/清除定稿标记", after["current_build"] == old and
                  after["build_seq"] == 1001 and after["builds"][0]["ai_report_finalized"])
            payload = root / "input.json"
            payload.write_text("{}", encoding="utf-8")
            emit = subprocess.run([sys.executable, str(REPO / ".aidp/scripts/emit-report.py"),
                                   "--kind", "test", "--version", "V0.1", "--build", old,
                                   "--data", str(payload), "--repo-root", str(root), "--json"],
                                  capture_output=True, text=True)
            check(f"--{flag}: 旧报告真实 emit 仍受不可变锁保护", emit.returncode == 2 and '"frozen": true' in emit.stdout)

    for label, options, expected_handoff in (
        ("未定稿续跑", {"once": True, "finalized": False}, "0"),
        ("骨架缺失", {"target": True, "finalized": False, "skeleton": False}, "1"),
        ("standalone", {"once": True, "build": False}, "0"),
    ):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            baseline, old = _retest_scene(root, **options)
            result, state = _test_entry_flow(root)
            node = json.loads(baseline.read_text())["versions"]["V0.1"]
            check(f"{label}: 交接判定正确", result.returncode == 0 and state[0] == expected_handoff)
            check(f"{label}: 不产生额外 build", node.get("current_build", "") == ("" if options.get("build") is False else old)
                  and node["build_seq"] == 1001)
            if options.get("build") is False:
                check("standalone: 仅截图命名，不启用官方报告", state[2] == "0" and not node.get("builds"))


def test_handoff_callback_cannot_recursively_remint():
    print("\n[F07] 同一次交接回调若仍无可测 build 必须失败返回")
    for finalized, skeleton in ((True, True), (False, False)):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            baseline, old = _retest_scene(root, once=True, finalized=finalized, skeleton=skeleton)
            data = json.loads(baseline.read_text())
            data["versions"]["V0.1"]["aiauto_handoff_run_id"] = "f07-run"
            baseline.write_text(json.dumps(data), encoding="utf-8")
            result, state = _test_entry_flow(root)
            check(f"finalized={finalized}/skeleton={skeleton}: 同 run 不递归交接", result.returncode != 0)
            node = json.loads(baseline.read_text())["versions"]["V0.1"]
            check("回调失败仍保留原 build", node["current_build"] == old and node["build_seq"] == 1001)
            data = json.loads(baseline.read_text())
            data["autopilot"]["tick"]["aiauto-test"]["PREFLIGHT_RUN_ID"] = "f07-next-run"
            baseline.write_text(json.dumps(data), encoding="utf-8")
            retried, state = _test_entry_flow(root)
            check("新外部 run 可重试，不被旧交接标记锁死", retried.returncode == 0 and state[0] == "1")


def test_handoff_preserves_unattended_wake_semantics():
    for wake in ("0", "1"):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            baseline, _ = _retest_scene(root, once=True)
            data = json.loads(baseline.read_text())
            data["autopilot"]["tick"]["aiauto-test"].update(LOOP_UNATTENDED="1", HAS_WAKE_SOURCE=wake)
            baseline.write_text(json.dumps(data), encoding="utf-8")
            result = subprocess.run(["bash", "-c", _flow_block("sprint-aiauto-test/phase-0-6b.md", "HANDOFF_ARGS=")],
                                    cwd=root, capture_output=True, text=True, timeout=60)
            lines = [line for line in result.stdout.splitlines() if line.startswith(("交接命令：", "返回命令："))]
            check(f"无人值守 wake={wake}: 两侧完整透传且 no-loop 不伪造唤醒源", result.returncode == 0 and
                  len(lines) == 2 and all("--unattended" in line and "--once" in line and
                                         (("--no-loop" in line) == (wake == "1")) for line in lines))


def test_real_test_only_handoff_mints_once_and_reuses_deployment():
    print("\n[F07] 真实 test-only 围栏往返：R-1 铸号/部署登记/新骨架/测试回调")
    scripts = REPO / ".aidp/scripts"
    def cli(root, *args):
        return subprocess.run([sys.executable, str(scripts / "autopilot_tick_flags.py"), *args],
                              cwd=root, capture_output=True, text=True, timeout=60)
    def bash(root, block):
        return subprocess.run(["bash", "-c", block], cwd=root, capture_output=True, text=True, timeout=60)
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        baseline, old = _retest_scene(root, once=True)
        old_reports = {p: p.read_bytes() for p in (root / "docs/reports").rglob("*.js")}
        old_token = cli(root, "begin", "--command", "aiauto-test")
        assert old_token.returncode == 0, old_token.stderr
        prepared = bash(root, _flow_block("sprint-aiauto-test/phase-0-6b.md", "HANDOFF_ARGS="))
        check("正常交接准备成功，--once 不被当成失败直接冻结", prepared.returncode == 0 and
              not json.loads(baseline.read_text())["versions"]["V0.1"].get("needs_human"))
        handoff = next(line.split("/sprint-autopilot ", 1)[1] for line in prepared.stdout.splitlines()
                       if line.startswith("交接命令："))
        callback = next(line.split("/sprint-aiauto-test ", 1)[1] for line in prepared.stdout.splitlines()
                       if line.startswith("返回命令："))
        check("两次调用透传 once、目标版及同一 run id", all("--once" in args and "--target V0.1" in args
              and "--preflight-run-id f07-run" in args for args in (handoff, callback)))
        check("无唤醒源不伪造 no-loop", "--no-loop" not in handoff and "--no-loop" not in callback)
        release = cli(root, "finish", "--command", "aiauto-test", "--lock-token", old_token.stdout.strip())
        assert release.returncode == 0, release.stderr
        dev_token = cli(root, "begin", "--command", "autopilot")
        assert dev_token.returncode == 0, dev_token.stderr
        parsed = cli(root, "parse", "--command", "autopilot", "--lock-token", dev_token.stdout.strip(),
                     "--arguments=" + handoff)
        assert parsed.returncode == 0, parsed.stderr
        route = bash(root, _flow_block("sprint-autopilot/phase-3-2.md", 'ENTRY_MODE="full"'))
        assert route.returncode == 0, route.stderr
        mint = _flow_block("sprint-autopilot/phase-3-4.md", 'CUR_SEQ="${CUR##*_build}"')
        result = bash(root, mint)
        assert result.returncode == 0, result.stderr
        node = json.loads(baseline.read_text())["versions"]["V0.1"]
        new = node["current_build"]
        row = next(row for row in node["builds"] if row["build"] == new)
        check("新号确由生产 R-1 铸造，保留 retest_of", new == "V0.1_build1002" and row.get("retest_of") == old)
        check("R-1 登记 test-only 部署复用证据", row.get("entry_mode") == "test-only" and
              row.get("deploy_reuse_of") == node["last_deployed_at"])
        payload = root / "skeleton.json"
        payload.write_text(json.dumps({"build": new, "version": "V0.1", "overview": {"statusKind": "pend"},
                                       "steps": [], "features": []}), encoding="utf-8")
        emitted = subprocess.run([sys.executable, str(scripts / "emit-report.py"), "--kind", "exec",
                                  "--version", "V0.1", "--build", new, "--data", str(payload),
                                  "--repo-root", str(root), "--templates-root", str(REPO / ".aidp/templates/reports"),
                                  "--record-baseline", "0", "--json"], capture_output=True, text=True)
        check("生产 emit 生成新 build 骨架，不使用 force-amend", emitted.returncode == 0)
        if emitted.returncode:
            raise AssertionError(emitted.stdout + emitted.stderr)
        test_token = cli(root, "begin", "--command", "aiauto-test")
        assert test_token.returncode == 0, test_token.stderr
        parsed = cli(root, "parse", "--command", "aiauto-test", "--lock-token", test_token.stdout.strip(),
                     "--arguments=" + callback)
        assert parsed.returncode == 0, parsed.stderr
        result, state = _test_entry_flow(root)
        check("同 run 回调从新 build 开测，不再交接", result.returncode == 0 and state == ["0", new, "1"])
        repeated = bash(root, mint)
        node = json.loads(baseline.read_text())["versions"]["V0.1"]
        check("R-1 再进入复用活动 build，不重复铸号", repeated.returncode == 0 and node["current_build"] == new
              and node["build_seq"] == 1002 and len(node["builds"]) == 2)
        check("往返后旧报告字节保持不变", all(p.read_bytes() == content for p, content in old_reports.items()))
        for command, token in (("aiauto-test", test_token), ("autopilot", dev_token)):
            released = cli(root, "finish", "--command", command, "--lock-token", token.stdout.strip())
            assert released.returncode == 0, released.stderr


def test_os_handoff_child_keeps_wrapper_lock():
    """OS 链同步调用依靠现有 wrapper 身份，不强释锁或伪造下次唤醒。"""
    import fcntl
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        path = root / "memory/.aidp/locks/loop-sprint-aiauto-test.lock"
        path.parent.mkdir(parents=True)
        record = json.dumps({"owner": "agent_loop", "token": "fixture-wrapper"})
        with path.open("w+") as handle:
            handle.write(record)
            handle.flush()
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            env = dict(os.environ, AIDP_TICK_COMMAND="sprint-aiauto-test", AIDP_TICK_TOKEN="fixture-wrapper")
            result = subprocess.run([sys.executable, str(REPO / ".aidp/scripts/autopilot_tick_flags.py"),
                                     "begin", "--command", "aiauto-test"], cwd=root, env=env,
                                    capture_output=True, text=True)
            check("OS 同步子链继承 wrapper 身份即可重入，未释放原锁",
                  result.returncode == 0 and result.stdout.strip() == "agent_loop" and path.read_text() == record)


def test_completed_test_cursor_does_not_reopen_old_build():
    print("\n[F07] 实际阶段入口：complete/done 必须短路；新 build 不继承旧终态")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        baseline, old_build = _retest_scene(root)
        data = json.loads(baseline.read_text())
        data["versions"]["V0.1"]["aiauto_run_state"] = {
            "current_phase": "3-audit", "phase_status": "complete", "next_phase": "done",
            "phase_token": old_build, "phase_enter_count": 1,
        }
        baseline.write_text(json.dumps(data), encoding="utf-8")
        original = baseline.read_bytes()
        def enter(build):
            return subprocess.run([sys.executable, str(REPO / ".aidp/scripts/aiauto_phase_entry.py"),
                                   "--version", "V0.1", "--phase", "1-probe", "--next-phase", "2-exec",
                                   "--build", build, "--baseline", str(baseline), "--no-card"],
                                  capture_output=True, text=True)
        result = enter(old_build)
        output = json.loads(result.stdout) if result.stdout.strip() else {}
        check("同 build 的 complete/done 不再进入探测", result.returncode == 0 and output.get("skip_phase")
              and output.get("resume_phase") == "done")
        check("终态短路不重写旧游标/停滞计数", baseline.read_bytes() == original)
        baseline.write_bytes(original)
        result = enter("V0.1_build1002")
        check("不同 build 可从 Phase 1 开始", result.returncode == 0 and
              not json.loads(result.stdout).get("skip_phase"))
        data["versions"]["V0.1"].pop("aiauto_run_state")
        baseline.write_text(json.dumps(data), encoding="utf-8")
        original = baseline.read_bytes()
        result = enter(old_build)
        check("定稿但游标缺失也不得重新实测", result.returncode != 0 and baseline.read_bytes() == original)
        data["versions"]["V0.1"]["aiauto_run_state"] = {
            "current_phase": "3-audit", "phase_status": "running", "next_phase": "done",
            "phase_token": old_build,
        }
        baseline.write_text(json.dumps(data), encoding="utf-8")
        result = subprocess.run([sys.executable, str(REPO / ".aidp/scripts/aiauto_phase_entry.py"),
                                 "--version", "V0.1", "--phase", "3-audit", "--next-phase", "done",
                                 "--build", old_build, "--baseline", str(baseline), "--no-card", "--complete"],
                                capture_output=True, text=True)
        check("正常审计先 finalize 再 complete 的出口不受影响", result.returncode == 0 and
              json.loads(baseline.read_text())["versions"]["V0.1"]["aiauto_run_state"]["phase_status"] == "complete")


def main():
    test_finalized_build_routes_to_handoff_before_testing()
    test_handoff_callback_cannot_recursively_remint()
    test_handoff_preserves_unattended_wake_semantics()
    test_real_test_only_handoff_mints_once_and_reuses_deployment()
    test_os_handoff_child_keeps_wrapper_lock()
    test_completed_test_cursor_does_not_reopen_old_build()
    test_immutability_lock_is_live()
    test_driver_truthfulness_window()
    test_render_mode_provenance()
    print(f"\n══ 结果：{_passed} passed / {_failed} failed ══")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
