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
import shlex
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


def _retest_scene(root, *, once=False, target=False, finalized=True, build=True, skeleton=True,
                  root_entry='sprint-autopilot', bind_build=True, deployed_commit=None):
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
        if deployed_commit is not None:
            node['builds'][0].update(push_commit=deployed_commit, probe_passed=True,
                                     probe_commit=deployed_commit, probe_at=node['last_deployed_at'])
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
    # 与真实入口一致：formal 父任务授予职责，实际 build 经受限子任务冻结；不能靠 entry 标签伪造授权。
    sys.path.insert(0, str(REPO / '.aidp/scripts'))
    import entry_context
    source = {'kind': 'explicit-command', 'command': root_entry, 'request_id': 'report-handoff-fixture'}
    if root_entry == 'sprint-aiauto-test':
        parent = entry_context.resolve_test_root(root, version, authorization_source=source)['execution_context']
    else:
        parent = entry_context.resolve_context(root, root_entry, version=version,
                                               authorization_source=source)['execution_context']
    context = (entry_context.fork_test_build(root, parent, version, current)['execution_context']
               if build and bind_build else parent)
    data = json.loads(baseline.read_text())
    if root_entry == 'sprint-aiauto-test':
        data['versions'][version]['aiauto_execution_context'] = parent
    else:
        data['autopilot']['execution_context'] = parent
    baseline.write_text(json.dumps(data), encoding='utf-8')
    fixture = root / 'memory/.aidp/report-fixture-context.json'
    fixture.write_text(json.dumps({'parent': parent, 'execution_context': context}), encoding='utf-8')
    return baseline, current


def _fixture_environment(root, execution_context=None):
    fixture = json.loads((root / 'memory/.aidp/report-fixture-context.json').read_text(encoding='utf-8'))
    return {**os.environ, 'EXECUTION_CONTEXT': execution_context or fixture['execution_context']}


def _test_entry_flow(root, execution_context=None):
    block = _flow_block("sprint-aiauto-test/phase-0-6.md", 'BASELINE_FILE="memory/')
    # EXIT trap 同时观察正常落尾与交接 early-exit，不替换任何生产判断或脚本。
    trap = 'trap \'printf "\\n__STATE__%s|%s|%s\\n" "${NEED_HANDOFF:-0}" "${BUILD:-}" "${REPORT_ENABLED:-}"\' EXIT\n'
    result = subprocess.run(["bash", "-c", trap + block], cwd=root, capture_output=True, text=True,
                            env=_fixture_environment(root, execution_context), timeout=60)
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
            check(f"finalized={finalized}/skeleton={skeleton}: 同 run 不递归交接",
                  result.returncode != 0 and '同次交接返回后' in result.stdout)
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
                                    cwd=root, capture_output=True, text=True, env=_fixture_environment(root), timeout=60)
            lines = [line for line in result.stdout.splitlines() if line.startswith(("交接命令：", "返回参数（待换绑）："))]
            check(f"无人值守 wake={wake}: 两侧完整透传且 no-loop 不伪造唤醒源", result.returncode == 0 and
                  len(lines) == 2 and all("--unattended" in line and "--once" in line and
                                         (("--no-loop" in line) == (wake == "1")) for line in lines))


def test_real_test_only_handoff_mints_once_and_reuses_deployment(finalized=True, skeleton=True, wake=False,
                                                               root_entry='sprint-autopilot'):
    print("\n[F07] 真实 test-only 围栏往返：R-1 铸号/部署登记/新骨架/测试回调" +
          ("（旧build已定稿）" if finalized else "（旧build未定稿但缺骨架）") + f' 来源={root_entry}')
    scripts = REPO / ".aidp/scripts"
    sys.path.insert(0, str(scripts))
    import entry_context
    from execution_policy import reserve_budget

    def cli(root, *args):
        return subprocess.run([sys.executable, str(scripts / "autopilot_tick_flags.py"), *args],
                              cwd=root, capture_output=True, text=True, timeout=60)

    def bash(root, block, execution_context=None):
        return subprocess.run(["bash", "-c", block], cwd=root, capture_output=True, text=True,
                              env=_fixture_environment(root, execution_context), timeout=60)

    def context_argument(arguments):
        tokens = shlex.split(arguments)
        return tokens[tokens.index('--execution-context') + 1]

    def command_entry(root, command, marker, execution_context):
        text = (REPO / '.aidp/commands' / (command + '.md')).read_text(encoding='utf-8')
        block = next(block for block in re.findall(r'^[ \t]*```bash\n(.*?)^[ \t]*```', text, re.M | re.S)
                     if marker in block)
        block = block.replace('{{AIDP_HOME}}', str(REPO / '.aidp')).replace('{version}', 'V0.1')
        result = bash(root, 'POLICY_ARGS=()\n' + block + '\nprintf "\\n__ENTRY_CONTEXT__%s\\n" "$EXECUTION_CONTEXT"\n', execution_context)
        observed = re.findall(r'^__ENTRY_CONTEXT__(.*)$', result.stdout, re.M)
        result.handoff_route = {}
        for line in result.stdout.splitlines():
            try:
                payload = json.loads(line)
            except ValueError:
                continue
            if isinstance(payload, dict) and payload.get('report_handoff') is True:
                result.handoff_route = payload
        # 受限分支在实际围栏内结束，只能消费其真实JSON输出，不能拿输入env伪造成功观察。
        selected = observed[-1] if observed else result.handoff_route.get('execution_context')
        return result, selected

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        def fixture_git(*args):
            return subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True,
                                  check=True).stdout.strip()
        fixture_git('init', '-q')
        fixture_git('config', 'user.name', 'Fixture')
        fixture_git('config', 'user.email', 'fixture@example.invalid')
        (root / '.gitignore').write_text('memory/\ndocs/\n__pycache__/\n', encoding='utf-8')
        (root / 'app.py').write_text("VERSION = 'deployed'\n", encoding='utf-8')
        (root / 'test_deployed.py').write_text('import unittest\nimport app\nclass DeploymentTest(unittest.TestCase):\n'
                                               ' def test_deployed(self): self.assertEqual(app.VERSION, "deployed")\n', encoding='utf-8')
        unit_suites = [{'full_argv': [sys.executable, '-m', 'unittest', '-v', 'test_deployed'],
                        'cwd': '.', 'env_id': 'deployed-stdlib-fixture', 'inputs': [], 'external_dependencies': 'none'}]
        unit_source = json.dumps({'schema': 1, 'suites': unit_suites}).encode('utf-8')
        (root / 'unit-plan.json').write_bytes(unit_source)
        fixture_git('add', '-A'); fixture_git('commit', '-qm', 'deployed-code')
        deployed_commit = fixture_git('rev-parse', 'HEAD')
        (root / 'app.py').write_text("VERSION = 'unrelated-head'\n", encoding='utf-8')
        fixture_git('add', 'app.py'); fixture_git('commit', '-qm', 'new-head-not-deployed')
        current_head = fixture_git('rev-parse', 'HEAD')
        baseline, old = _retest_scene(root, once=True, finalized=finalized, skeleton=skeleton,
                                     root_entry=root_entry, bind_build=root_entry != 'sprint-aiauto-test',
                                     deployed_commit=deployed_commit)
        if wake:
            data = json.loads(baseline.read_text())
            data['autopilot']['tick']['aiauto-test'].update(LOOP_UNATTENDED='1', HAS_WAKE_SOURCE='1')
            baseline.write_text(json.dumps(data), encoding='utf-8')
        fixture = json.loads((root / 'memory/.aidp/report-fixture-context.json').read_text())
        parent = entry_context.load_context(root, fixture['parent'])
        check('真实部署commit A与当前HEAD/context起点B不同',
              deployed_commit != current_head and parent['since'] == current_head)
        if root_entry == 'sprint-aiauto-test':
            check('独立根真实entry与授权来源均为sprint-aiauto-test',
                  parent['entry'] == root_entry and parent['mode'] == 'formal'
                  and any(source.get('kind') == 'explicit-command' and source.get('command') == root_entry
                          for source in parent['authorization_source'])
                  and set(parent['allowed_actions']) == {'static', 'live-tests', 'full-regression'})
            context_files = set(Path(fixture['parent']).parent.parent.glob('*/context.json'))
            rejected = subprocess.run([sys.executable, str(scripts / 'entry_context.py'), 'resolve-autopilot-root',
                '--root', str(root), '--version', 'V0.1', '--execution-context', fixture['parent'], '--existing-only', '--json'],
                cwd=root, capture_output=True, text=True)
            check('普通autopilot selector仍拒绝aiauto错域根且不建新root',
                  rejected.returncode != 0 and 'UNAUTHORIZED' in rejected.stdout + rejected.stderr
                  and set(Path(fixture['parent']).parent.parent.glob('*/context.json')) == context_files)
        reserve_budget(root, fixture['parent'], 'processes', 3, action='static')
        if root_entry == 'sprint-aiauto-test':
            entered, initial_context = command_entry(root, 'sprint-aiauto-test', 'CONTEXT_ARGS=()', fixture['parent'])
            assert entered.returncode == 0 and initial_context, entered.stdout + entered.stderr
            pinned = entry_context.load_context(root, initial_context)
            check('独立aiauto完整首入口真实固定旧build，无夹具预造child',
                  initial_context != fixture['parent'] and pinned.get('build_id') == old
                  and pinned.get('parent_task_id') == parent['task_id'])
            fixture['execution_context'] = initial_context
            (root / 'memory/.aidp/report-fixture-context.json').write_text(json.dumps(fixture), encoding='utf-8')
        old_context = entry_context.load_context(root, fixture['execution_context'])
        old_context_bytes = Path(fixture['execution_context']).read_bytes()
        old_reports = {p: p.read_bytes() for p in (root / "docs/reports").rglob("*.js")}
        old_token = cli(root, "begin", "--command", "aiauto-test")
        assert old_token.returncode == 0, old_token.stderr
        prepared = bash(root, _flow_block("sprint-aiauto-test/phase-0-6b.md", "HANDOFF_ARGS="))
        check("正常交接准备成功，--once 不被当成失败直接冻结", prepared.returncode == 0 and
              not json.loads(baseline.read_text())["versions"]["V0.1"].get("needs_human"))
        handoff = next(line.split("/sprint-autopilot ", 1)[1] for line in prepared.stdout.splitlines()
                       if line.startswith("交接命令："))
        return_template = next(line.split('：', 1)[1] for line in prepared.stdout.splitlines()
                               if line.startswith('返回参数（待换绑）：'))
        handoff_context = context_argument(handoff)
        check('交接显式传原授权根，返回模板不冒充已换绑回调',
              handoff_context == fixture['parent'] and '--execution-context' not in return_template)
        release = cli(root, "finish", "--command", "aiauto-test", "--lock-token", old_token.stdout.strip())
        assert release.returncode == 0, release.stderr
        dev_token = cli(root, "begin", "--command", "autopilot")
        assert dev_token.returncode == 0, dev_token.stderr
        parsed = cli(root, "parse", "--command", "autopilot", "--lock-token", dev_token.stdout.strip(),
                     "--arguments=" + handoff)
        assert parsed.returncode == 0, parsed.stderr
        entry_baseline = baseline.read_bytes()
        context_files = set(Path(fixture['parent']).parent.parent.glob('*/context.json'))
        if root_entry == 'sprint-aiauto-test':
            entry_mutations = (
                ('无交接run证明', lambda d: d['versions']['V0.1'].pop('aiauto_handoff_run_id')),
                ('错交接run', lambda d: d['versions']['V0.1'].update(aiauto_handoff_run_id='other-run')),
                ('无原根来源', lambda d: d['versions']['V0.1'].pop('aiauto_handoff_root_context')),
                ('无固定child来源', lambda d: d['versions']['V0.1'].pop('aiauto_handoff_from_context')),
                ('来源build错误', lambda d: d['versions']['V0.1'].update(aiauto_handoff_from_build='V0.1_build0999')),
                ('任意build漂移', lambda d: d['versions']['V0.1'].update(current_build='V0.1_build9999')),
                ('没有skip-dev', lambda d: d['autopilot']['tick']['autopilot'].update(SKIP_DEV='0')),
                ('没有显式target', lambda d: d['autopilot']['tick']['autopilot'].update(TARGET_FLAG_VALUE='')),
            )
            for label, mutate in entry_mutations:
                data = json.loads(entry_baseline)
                mutate(data)
                baseline.write_text(json.dumps(data), encoding='utf-8')
                rejected, _ = command_entry(root, 'sprint-autopilot', 'resolve-autopilot-root', handoff_context)
                check('独立aiauto首入口' + label + '拒绝受限分支，不新建root',
                      rejected.returncode != 0 and not rejected.handoff_route
                      and set(Path(fixture['parent']).parent.parent.glob('*/context.json')) == context_files)
            baseline.write_bytes(entry_baseline)
        entered, observed_context = command_entry(root, 'sprint-autopilot', 'resolve-autopilot-root', handoff_context)
        check('真实autopilot入口接受原根，不另建root或预算',
              entered.returncode == 0 and observed_context == fixture['parent'])
        assert entered.returncode == 0, entered.stdout + entered.stderr
        if entered.handoff_route:
            before_entry, after_entry = json.loads(entry_baseline), json.loads(baseline.read_text())
            check('受限report-handoff仅持久本tick test-only，不改global或版本根',
                  after_entry['autopilot']['tick']['autopilot']['ENTRY_MODE'] == 'test-only'
                  and after_entry['autopilot'].get('execution_context') == before_entry['autopilot'].get('execution_context')
                  and all(after_entry['versions']['V0.1'].get(key) == before_entry['versions']['V0.1'].get(key)
                          for key in ('autopilot_root_context', 'execution_context'))
                  and set(Path(fixture['parent']).parent.parent.glob('*/context.json')) == context_files)
        else:
            route = bash(root, _flow_block("sprint-autopilot/phase-3-2.md", 'ENTRY_MODE="full"'), handoff_context)
            assert route.returncode == 0, route.stderr
        if root_entry == 'sprint-aiauto-test':
            current_parent = entry_context.load_context(root, fixture['parent'])
            check('独立aiauto只能走report-handoff且不扩成开发/部署/提交权限',
                  entered.handoff_route.get('report_handoff') is True
                  and current_parent['entry'] == root_entry
                  and current_parent['allowed_actions'] == parent['allowed_actions']
                  and current_parent['authorization_source'] == parent['authorization_source'])
        mint = _flow_block("sprint-autopilot/phase-3-4a.md", 'CUR_SEQ="${CUR##*_build}"')
        if root_entry == 'sprint-aiauto-test':
            mint_baseline = baseline.read_bytes()
            def old_build(data):
                return next(row for row in data['versions']['V0.1']['builds'] if row['build'] == old)
            deployment_mutations = (
                ('缺原push_commit', lambda d: old_build(d).pop('push_commit')),
                ('原push_commit变成当前HEAD', lambda d: old_build(d).update(push_commit=current_head)),
                ('无原探活通过证明', lambda d: old_build(d).update(probe_passed=False)),
                ('probe_commit与push_commit矛盾', lambda d: old_build(d).update(probe_commit=current_head)),
                ('probe时间不对应现部署', lambda d: old_build(d).update(probe_at='2026-09-15T09:00:00+08:00')),
                ('准备后部署证据变化', lambda d: d['versions']['V0.1'].update(last_deployed_at='2026-09-17T09:00:00+08:00')),
            )
            for label, mutate in deployment_mutations:
                data = json.loads(mint_baseline)
                mutate(data)
                baseline.write_text(json.dumps(data), encoding='utf-8')
                rejected = bash(root, mint, handoff_context)
                after_rejection = json.loads(baseline.read_text())['versions']['V0.1']
                check(label + '：R1拒绝且不先铸号，不取HEAD补证明',
                      rejected.returncode != 0 and after_rejection['current_build'] == old
                      and after_rejection['build_seq'] == 1001 and not after_rejection.get('aiauto_handoff_to_build'))
            baseline.write_bytes(mint_baseline)
        result = bash(root, mint, handoff_context)
        assert result.returncode == 0, result.stdout + result.stderr
        node = json.loads(baseline.read_text())["versions"]["V0.1"]
        new = node["current_build"]
        row = next(row for row in node["builds"] if row["build"] == new)
        if finalized:
            check("新号确由生产 R-1 铸造，保留 retest_of", new == "V0.1_build1002" and row.get("retest_of") == old)
        else:
            check('未定稿缺骨架也由真实R-1铸号，不伪造retest_of', new == 'V0.1_build1002' and not row.get('retest_of'))
        check("R-1 登记 test-only 部署复用证据", row.get("entry_mode") == "test-only" and
              row.get("deploy_reuse_of") == node["last_deployed_at"])
        check('R-1登记同run实际目标，callback不猜当前build',
              node.get('aiauto_handoff_to_build') == new and node.get('aiauto_handoff_from_build') == old
              and node.get('aiauto_handoff_run_id') == 'f07-run')
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
        rebind = _flow_block('sprint-aiauto-test/phase-0-6b.md', 'HANDOFF_REBOUND_CONTEXT=')
        if finalized:
            trusted = baseline.read_bytes()
            contexts_dir = Path(fixture['parent']).parent.parent
            context_files = set(contexts_dir.glob('*/context.json'))
            mutations = (
                ('缺授权根来源', lambda n: n.pop('aiauto_handoff_root_context')),
                ('缺原测试子任务来源', lambda n: n.pop('aiauto_handoff_from_context')),
                ('无R-1目标登记', lambda n: n.pop('aiauto_handoff_to_build')),
                ('不是原交接run', lambda n: n.update(aiauto_handoff_run_id='unrelated-run')),
                ('原build来源不符', lambda n: n.update(aiauto_handoff_from_build='V0.1_build0999')),
                ('旧子任务不能冒充授权根', lambda n: n.update(aiauto_handoff_root_context=fixture['execution_context'])),
                ('任意current_build漂移', lambda n: n.update(current_build='V0.1_build9999')),
                ('擅改登记目标', lambda n: n.update(aiauto_handoff_to_build=old)),
                ('新号retest_of不符', lambda n: next(r for r in n['builds'] if r['build'] == new).update(retest_of='V0.1_build0999')),
                ('新报告已定稿', lambda n: next(r for r in n['builds'] if r['build'] == new).update(ai_report_finalized=True)),
            )
            for label, mutate in mutations:
                data = json.loads(trusted)
                mutate(data['versions']['V0.1'])
                baseline.write_text(json.dumps(data), encoding='utf-8')
                rejected = bash(root, rebind, handoff_context)
                check(label + '：拒绝换绑且不创建新ctx', rejected.returncode != 0 and
                      '返回命令：' not in rejected.stdout and set(contexts_dir.glob('*/context.json')) == context_files)
            baseline.write_bytes(trusted)
            skeleton_path = root / f'docs/reports/V0.1/AI执行报告/data/{new}.js'
            skeleton_bytes = skeleton_path.read_bytes()
            skeleton_path.unlink()
            try:
                rejected = bash(root, rebind, handoff_context)
                check('缺真实新骨架：拒绝换绑且不创建新ctx', rejected.returncode != 0 and
                      '返回命令：' not in rejected.stdout and set(contexts_dir.glob('*/context.json')) == context_files)
            finally:
                skeleton_path.write_bytes(skeleton_bytes)
        rebound = bash(root, rebind, handoff_context)
        assert rebound.returncode == 0, rebound.stdout + rebound.stderr
        callback = next(line.split('/sprint-aiauto-test ', 1)[1] for line in rebound.stdout.splitlines()
                        if line.startswith('返回命令：'))
        callback_context = context_argument(callback)
        child = entry_context.load_context(root, callback_context)
        check('新build测试子任务继承原根/来源/权限，不改旧fixed ctx',
              child.get('parent_task_id') == parent['task_id'] and child.get('build_id') == new
              and child['authorization_source'] == parent['authorization_source']
              and child['allowed_actions'] == old_context['allowed_actions']
              and callback_context != fixture['execution_context']
              and Path(fixture['execution_context']).read_bytes() == old_context_bytes)
        budget = reserve_budget(root, callback_context, 'processes', 1, action='static')
        check('新子任务继续消费原根预算，不因换绑归零',
              budget['budget_task_id'] == parent['task_id'] and budget['used'] >= 4)
        check("两次调用透传 once、目标版及同一 run id", all("--once" in args and "--target V0.1" in args
              and "--preflight-run-id f07-run" in args for args in (handoff, callback)))
        if wake:
            check('真实回调保留无人值守及已有唤醒源',
                  all('--unattended' in args and '--no-loop' in args for args in (handoff, callback)))
        else:
            check("无唤醒源不伪造 no-loop", "--no-loop" not in handoff and "--no-loop" not in callback)
        test_token = cli(root, "begin", "--command", "aiauto-test")
        assert test_token.returncode == 0, test_token.stderr
        parsed = cli(root, "parse", "--command", "aiauto-test", "--lock-token", test_token.stdout.strip(),
                     "--arguments=" + callback)
        assert parsed.returncode == 0, parsed.stderr
        entered, observed_context = command_entry(root, 'sprint-aiauto-test', 'CONTEXT_ARGS=()', callback_context)
        check('真实aiauto入口继承新fixed child，不回落裸root',
              entered.returncode == 0 and observed_context == callback_context)
        assert entered.returncode == 0, entered.stdout + entered.stderr
        result, state = _test_entry_flow(root, execution_context=callback_context)
        check("同 run 回调从新 build 开测，不再交接", result.returncode == 0 and state == ["0", new, "1"])
        import build_unit_test
        plan = {'schema': 1, 'version': 'V0.1', 'build': new, 'commit': deployed_commit,
                'source': {'path': 'unit-plan.json', 'sha256': hashlib.sha256(unit_source).hexdigest()},
                'suites': unit_suites}
        tested_row = next(r for r in json.loads(baseline.read_text())['versions']['V0.1']['builds'] if r['build'] == new)
        check('新build绑定原部署SHA而非HEAD或ctx.since', tested_row.get('push_commit') == deployed_commit
              and tested_row.get('push_commit') != fixture_git('rev-parse', 'HEAD'))
        loaded_plan = build_unit_test.load_plan(root, 'V0.1', new, deployed_commit, plan)
        check('真实生产load_plan接受新build的原部署SHA与提交内契约', loaded_plan['commit'] == deployed_commit)
        import aiauto_test_join
        aiauto_test_join.begin(root, 'V0.1', new, deployed_commit)
        check('两路声明在途后新build不能继承旧测试完成时间',
              aiauto_test_join.release_state(root, 'V0.1') == 'pending')
        unit = build_unit_test.run_build(root, 'V0.1', new, deployed_commit, plan,
                                        timeout=10, execution_context=callback_context)
        check('真实全量单测从原部署commit隔离执行至PASS', unit['status'] == 'PASS' and bool(unit.get('runs')))
        check('单测不改当前HEAD并清理临时worktree', fixture_git('rev-parse', 'HEAD') == current_head
              and not (build_unit_test.build_dir(root, 'V0.1', new) / 'worktree').exists())
        repeated = bash(root, mint, handoff_context)
        node = json.loads(baseline.read_text())["versions"]["V0.1"]
        check("R-1 再进入复用活动 build，不重复铸号", repeated.returncode == 0 and node["current_build"] == new
              and node["build_seq"] == 1002 and len(node["builds"]) == 2)
        # 沿用 test_aiauto_test_join 的离线browser summary形态；case按既有emit契约补齐。
        # 此结果仅验证报告/状态消费者，不是执行过真实浏览器的验收声明。
        browser_input = root / 'offline-browser-result.json'
        browser_input.write_text(json.dumps({'build': new, 'version': 'V0.1', 'commit': deployed_commit,
            'summary': {'total': 1, 'pass': 1, 'fail': 0, 'block': 0, 'skip': 0, 'na': 0, 'passRate': 1.0},
            'cases': [{'id': 'OFFLINE-BROWSER-1', 'title': '离线浏览器结果夹具', 'result': 'pass',
                       'note': '仅验证emit/join/settle，不代表真实浏览器执行'}],
            'defects': [], 'runtimeErrors': []}, ensure_ascii=False), encoding='utf-8')
        merged = subprocess.run([sys.executable, str(scripts / 'emit-report.py'), '--kind', 'test',
            '--version', 'V0.1', '--build', new, '--commit', deployed_commit,
            '--data', str(browser_input), '--unit-result', str(build_unit_test.build_dir(root, 'V0.1', new) / 'result.json'),
            '--repo-root', str(root), '--templates-root', str(REPO / '.aidp/templates/reports'), '--json'],
            capture_output=True, text=True)
        check('真实unit结果与离线browser夹具经生产emit合并', merged.returncode == 0)
        assert merged.returncode == 0, merged.stdout + merged.stderr
        report_path = root / f'docs/reports/V0.1/AI测试报告/data/{new}.js'
        settled = subprocess.run([sys.executable, str(scripts / 'aiauto_test_join.py'), 'settle',
            '--root', str(root), '--version', 'V0.1', '--build', new, '--report', str(report_path)],
            capture_output=True, text=True)
        result = json.loads(settled.stdout) if settled.returncode == 0 else {}
        check('生产settle消费同一部署SHA的两路结果并达到收口状态',
              settled.returncode == 0 and result.get('commit') == deployed_commit
              and result.get('overall_status') == 'PASS' and result.get('converged') is True
              and aiauto_test_join.release_state(root, 'V0.1') == 'pass')
        assert settled.returncode == 0, settled.stdout + settled.stderr
        final_budget = reserve_budget(root, callback_context, 'processes', 0, action='static')
        check('报告settle后仍沿原根预算和授权来源',
              final_budget['budget_task_id'] == parent['task_id'] and final_budget['used'] >= 4
              and entry_context.load_context(root, fixture['parent'])['authorization_source'] == parent['authorization_source'])
        check("往返后旧报告字节保持不变", all(p.read_bytes() == content for p, content in old_reports.items()))
        for command, token in (("aiauto-test", test_token), ("autopilot", dev_token)):
            released = cli(root, "finish", "--command", command, "--lock-token", token.stdout.strip())
            assert released.returncode == 0, released.stderr


def test_fixed_build_context_rejects_unrelated_baseline_drift():
    print("\n[F07] 固定 build 不因无交接来源的 baseline 漂移而换目标")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        baseline, old = _retest_scene(root, once=True, finalized=False)
        fixture = json.loads((root / 'memory/.aidp/report-fixture-context.json').read_text())
        context_file = Path(fixture['execution_context'])
        frozen_context = context_file.read_bytes()
        data = json.loads(baseline.read_text())
        node = data['versions']['V0.1']
        new = 'V0.1_build1002'
        node['current_build'] = new
        node['build_seq'] = 1002
        node['builds'].append({'build': new, 'status': 'running', 'ai_report_finalized': False,
                               'started_at': '2026-09-16T08:00:00+08:00'})
        baseline.write_text(json.dumps(data), encoding='utf-8')
        _mk_reports(root, new)
        result, _ = _test_entry_flow(root)
        after = json.loads(baseline.read_text())['versions']['V0.1']
        check('无唤醒源的意外 build 漂移返回未完成', result.returncode != 0 and 'BUILD_CHANGED' in result.stdout)
        check('拒绝漂移不改写固定上下文或认领新build', context_file.read_bytes() == frozen_context
              and after['builds'] == node['builds'] and after['current_build'] == new)


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
    test_real_test_only_handoff_mints_once_and_reuses_deployment(finalized=False, skeleton=False, wake=True)
    test_real_test_only_handoff_mints_once_and_reuses_deployment(root_entry='sprint-aiauto-test')
    test_fixed_build_context_rejects_unrelated_baseline_drift()
    test_os_handoff_child_keeps_wrapper_lock()
    test_completed_test_cursor_does_not_reopen_old_build()
    test_immutability_lock_is_live()
    test_driver_truthfulness_window()
    test_render_mode_provenance()
    print(f"\n══ 结果：{_passed} passed / {_failed} failed ══")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
