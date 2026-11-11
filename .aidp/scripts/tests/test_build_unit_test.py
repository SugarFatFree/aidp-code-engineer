#!/usr/bin/env python3
"""build 全量单测执行器：真实临时 Git 仓库、进程及 worktree 回归（无网络）。"""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "build_unit_test.py"
spec = importlib.util.spec_from_file_location("build_unit_test_under_test", SCRIPT)
build_unit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_unit)

PASS_TEST = """import unittest
class Example(unittest.TestCase):
    def test_pass(self): self.assertEqual(2 + 2, 4)
    @unittest.skip('fixture')
    def test_skip(self): pass
"""
FAIL_TEST = """import unittest
class Example(unittest.TestCase):
    def test_fail(self): self.assertEqual(2 + 2, 5, 'actual assertion failure')
"""


class BuildUnitTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="aidp-build-unit-test-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "repo"
        self.root.mkdir()
        self.git("init", "-q")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "user.name", "Fixture")
        (self.root / ".gitignore").write_text("memory/\n__pycache__/\nreports/\n")
        (self.root / "test_sample.py").write_text(PASS_TEST)
        self.version = "V1.0.0"
        self.build = "V1.0.0_build1"

    def git(self, *args):
        return build_unit.git(self.root, *args).decode().strip()

    def suite(self, argv=None, **fields):
        result = {"full_argv": argv or [sys.executable, "-m", "unittest", "-v", "test_sample"],
                  "cwd": ".", "env_id": "stdlib-fixture", "inputs": [], "external_dependencies": "none"}
        result.update(fields)
        return result

    def freeze(self, suites=None, markdown=False, baseline=False, tests=None, dependencies=None, extra_case=None):
        tests = tests or ['test_sample.py']
        dependencies = dependencies or []
        suites = suites or [self.suite()]
        for i, suite in enumerate(suites):
            suite['env_id'] = suite.get('env_id', 'stdlib') + str(i)
            argv = [arg if arg != 'test_sample' else '{tests}' for arg in suite['full_argv']]
            if '{tests}' not in argv:
                argv.append('{tests}')
            suite['runners'] = [{'suffixes': ['.py'], 'argv': argv,
                                 'cwd': suite['cwd'], 'env_id': suite['env_id']}]
        formal = self.root / 'docs/testing' / self.version / '正式用例'
        formal.mkdir(parents=True, exist_ok=True)
        index = formal / '00_索引.md'
        index.write_text('# 本版本正式用例索引\nTC-ONE\n')
        (formal / '03_cases.md').write_text('#### 用例 TC-ONE: sample\n')
        acceptance = {'version': self.version, 'acceptance_tests': tests, 'dependencies': dependencies,
                      'cases': [{'id': 'TC-ONE', 'test_files': tests}] + ([{'id': extra_case, 'test_files': tests}] if extra_case else []),
                      'case_index': {'path': index.relative_to(self.root).as_posix(),
                                     'sha256': hashlib.sha256(index.read_bytes()).hexdigest()}}
        acceptance_path = formal.parent / 'acceptance.json'
        acceptance_path.write_text(json.dumps(acceptance))
        config = {"schema": 1, "suites": suites}
        payload = json.dumps(config)
        source = "contract.md" if markdown else "unit-plan.json"
        if markdown:
            payload = "# Test contract\n\n```aidp-test-plan\n" + payload + "\n```\n"
        (self.root / source).write_text(payload)
        self.git("add", ".")
        self.git("commit", "-q", "--allow-empty", "-m", "fixture")
        self.commit = self.git("rev-parse", "HEAD")
        plan = {"schema": 1, "version": self.version, "build": self.build, "commit": self.commit,
                "source": {"path": source, "sha256": hashlib.sha256(payload.encode()).hexdigest()},
                "suites": suites, 'acceptance_tests': tests, 'dependencies': dependencies,
                'acceptance_baseline': {'path': acceptance_path.relative_to(self.root).as_posix(),
                                        'sha256': hashlib.sha256(acceptance_path.read_bytes()).hexdigest()}}
        if baseline:
            path = Path(build_unit.baseline(self.root))
            path.parent.mkdir(exist_ok=True)
            path.write_text(json.dumps({"versions": {self.version: {"builds": [
                {"build": self.build, "push_commit": self.commit}]}}}))
        else:
            plan.update(standalone=True, deployment={"commit": self.commit, "verified": True,
                                                    "evidence": "deployment fixture verified by test"})
        self.delegate(plan)
        return plan

    def delegate(self, plan):
        from entry_context import resolve_autopilot_root, fork_test_build
        if not hasattr(self, 'parent'):
            self.parent = resolve_autopilot_root(self.root, self.version, authorization_source={
                'kind': 'explicit-command', 'command': 'sprint-autopilot', 'request_id': 'offline-fixture',
                'options': ['--skip-dev']})['execution_context']
            self.contexts = {}
        if plan['build'] not in self.contexts:
            path = self.root / 'memory' / (plan['build'] + '-manifest.json')
            path.write_text(json.dumps(plan))
            self.contexts[plan['build']] = fork_test_build(self.root, self.parent, self.version, plan['build'],
                                                         manifest=path)['execution_context']
        return self.contexts[plan['build']]

    def run_plan(self, plan, **kwargs):
        if 'execution_context' not in kwargs:
            kwargs['execution_context'] = self.delegate(plan)
        return build_unit.run_build(self.root, self.version, plan["build"], plan["commit"], plan, **kwargs)

    def cli(self, plan, *extra):
        context = self.delegate(plan)
        path = self.root / 'memory' / (plan['build'] + '-manifest.json')
        return [sys.executable, str(SCRIPT), "run", "--root", str(self.root),
                "--version", self.version, "--build", plan["build"], "--commit", plan["commit"],
                "--plan", str(path), '--execution-context', context, *extra]

    def assert_cleaned(self, build=None):
        directory = build_unit.build_dir(self.root, self.version, build or self.build)
        self.assertFalse((directory / "worktree").exists())
        registered = self.git("worktree", "list", "--porcelain")
        self.assertNotIn(str(directory / "worktree"), registered)

    def test_parent_authorization_is_rechecked_before_full_test(self):
        from entry_context import resolve_context
        from execution_policy import PolicyError
        plan = self.freeze()
        ordinary = resolve_context(self.root, 'sprint-dev', version=self.version)
        result = self.run_plan(plan, execution_context=ordinary['execution_context'])
        self.assertEqual(result['status'], 'UNVERIFIED')
        self.assertEqual(result['authorization_status'], 'NOT_REQUESTED')
        self.assertEqual(result['runs'], [])
        self.assertFalse(build_unit.build_dir(self.root, self.version, self.build).exists())
        # 用户文本/--grant 不能直接授予版本全量：resolve 阶段即拒绝，也不会留下 build 目录。
        with self.assertRaisesRegex(PolicyError, 'autopilot'):
            resolve_context(self.root, 'sprint-dev', version=self.version,
                additional_grants=['full-regression'], authorization_source={
                    'kind': 'user-text', 'request_id': 'fixture-full', 'text': '运行完整单元测试'})
        self.assertFalse(build_unit.build_dir(self.root, self.version, self.build).exists())
        delegated = self.run_plan(plan, timeout=10)
        self.assertEqual(delegated['status'], 'PASS', delegated)
        again = self.run_plan(plan, timeout=10)
        self.assertTrue(again['reused'])
        self.assert_cleaned()

    def version_case_fence(self, plan):
        """执行 phase-2-1.md 里真实的版本用例围栏内联脚本，返回 (退出码, 选中的册, 输出)。"""
        import re as _re
        text = (Path(__file__).resolve().parents[2] / 'flows/sprint-aiauto-test/phase-2-1.md').read_text(encoding='utf-8')
        body = _re.search(r"<<'VERSION_CASES'\n(.*?)\nVERSION_CASES", text, _re.S).group(1)
        body = body.replace('{{AIDP_HOME}}', str(SCRIPT.parent.parent))
        context = self.delegate(plan)
        done = subprocess.run([sys.executable, '-c', body, context, self.version, plan['build']],
                              cwd=self.root, capture_output=True, text=True)
        return done.returncode, done.stdout.split(), done.stdout + done.stderr

    def test_version_case_fence_uses_frozen_manifest_only(self):
        plan = self.freeze()
        formal = self.root / 'docs/testing' / self.version / '正式用例'
        code, selected, output = self.version_case_fence(plan)
        self.assertEqual(code, 0, output)
        self.assertEqual(selected, ['docs/testing/%s/正式用例/03_cases.md' % self.version])
        # 下划线开头的增量册即使含清单内 ID 也不是用例。
        (formal / '_开发期用例增量.md').write_text('#### 用例 TC-ONE: 增量线索\n')
        code, selected, output = self.version_case_fence(plan)
        self.assertEqual(code, 0, output)
        self.assertNotIn('_开发期用例增量.md', ' '.join(selected))
        # 更旧版本目录里的 [回归] 册不会被自动并入。
        old = self.root / 'docs/testing/V0.0.1/研发自测'
        old.mkdir(parents=True)
        (old / '02_回归用例.md').write_text('[回归]\n#### 用例 TC-OLD: 历史\n')
        code, selected, output = self.version_case_fence(plan)
        self.assertEqual(code, 0, output)
        self.assertFalse([item for item in selected if 'V0.0.1' in item], selected)

    def test_version_case_fence_rejects_book_with_ids_outside_frozen_list(self):
        plan = self.freeze()
        formal = self.root / 'docs/testing' / self.version / '正式用例'
        (formal / '04_mixed.md').write_text('#### 用例 TC-ONE: 清单内\n#### 用例 TC-OTHER: 清单外\n')
        code, selected, output = self.version_case_fence(plan)
        self.assertNotEqual(code, 0, output)
        # 册内含清单外 ID 时，基线与完整正式清单不一致，先由 validate_case_index 具体拒绝。
        self.assertIn('不一致', output)
        self.assertIn('BuildError', output)
        self.assertFalse(selected)

    def test_validate_case_index_ignores_underscore_incremental_books(self):
        plan = self.freeze()
        formal = self.root / 'docs/testing' / self.version / '正式用例'
        baseline = build_unit.validate_case_index(self.root, plan)
        self.assertEqual(baseline, ['TC-ONE'])
        (formal / '_开发期用例增量.md').write_text('#### 用例 TC-ONE: 清单内线索\n')
        self.assertEqual(build_unit.validate_case_index(self.root, plan), baseline)
        (formal / '_另一增量.md').write_text('#### 用例 TC-OTHER: 清单外线索\n')
        self.assertEqual(build_unit.validate_case_index(self.root, plan), baseline)
        # 非下划线册里的清单外 ID 仍必须拒绝。
        (formal / '04_real.md').write_text('#### 用例 TC-OTHER: 真实册\n')
        with self.assertRaisesRegex(build_unit.BuildError, '不一致'):
            build_unit.validate_case_index(self.root, plan)

    def test_case_book_exclusion_rule_is_single_source(self):
        for name in ('_a.md', '00_索引.md', '98_x.md', '99_待澄清.md', '01_研发自测方案.md', '测试环境与账号.md', '总览.md'):
            self.assertFalse(build_unit.is_case_book(name), name)
        self.assertTrue(build_unit.is_case_book('03_cases.md'))

    def test_dirty_main_and_config_do_not_affect_commit_worktree(self):
        plan = self.freeze(baseline=True)
        (self.root / "test_sample.py").write_text("raise RuntimeError('dirty main')\n")
        (self.root / "unit-plan.json").write_text("not JSON; must read committed object")
        (self.root / "untracked.py").write_text("raise RuntimeError('untracked')\n")
        result = self.run_plan(plan)
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(result["counts"], {"passed": 1, "failed": 0, "skipped": 1})
        self.assertEqual(result["runs"][0]["command"], [sys.executable, '-m', 'unittest', '-v', 'test_sample.py'])
        self.assertIn("test_pass", Path(result["runs"][0]["log"]).read_text())
        self.assertIn("dirty main", (self.root / "test_sample.py").read_text())
        self.assert_cleaned()

    def test_main_change_during_execution_and_environment_are_isolated(self):
        (self.root / "test_sample.py").write_text("""import unittest, time, os
class Example(unittest.TestCase):
 def test_fixed(self):
  print('TEST_READY', flush=True)
  time.sleep(.5)
  self.assertNotIn('DEPLOY_DATABASE_URL', os.environ)
  self.assertNotIn('PYTHONPATH', os.environ)
  self.assertEqual(open('value.txt').read(), 'committed')
""")
        (self.root / "value.txt").write_text("committed")
        plan = self.freeze(dependencies=['value.txt'])
        env = dict(os.environ, DEPLOY_DATABASE_URL="https://deployment.invalid", PYTHONPATH=str(self.root))
        process = subprocess.Popen(self.cli(plan), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        self.addCleanup(lambda: process.kill() if process.poll() is None else None)
        directory = build_unit.build_dir(self.root, self.version, self.build)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            logs = list(directory.glob("suite-*.log"))
            if logs and "TEST_READY" in logs[0].read_text():
                break
            time.sleep(.01)
        else:
            self.fail("runner never started")
        (self.root / "value.txt").write_text("changed while running")
        (self.root / "test_sample.py").unlink()
        stdout, stderr = process.communicate(timeout=10)
        self.assertEqual(process.returncode, 0, stderr)
        self.assertEqual(json.loads(stdout)["status"], "PASS", stdout)
        self.assert_cleaned()

    def test_same_build_pass_reused_new_build_same_commit_reruns(self):
        plan = self.freeze()
        first = self.run_plan(plan)
        repeated = self.run_plan(plan, retry=True)
        self.assertEqual(first["status"], "PASS", first)
        self.assertTrue(repeated["reused"])
        self.assertEqual(first["runs"], repeated["runs"])
        plan["build"] = "V1.0.0_build2"
        other = self.run_plan(plan)
        self.assertFalse(other["reused"])
        self.assertEqual(other["status"], "PASS", other)
        self.assertNotEqual(first["runs"][0]["run_id"], other["runs"][0]["run_id"])
        self.assert_cleaned(plan["build"])

    def test_concurrent_same_build_executes_once_status_is_lightweight(self):
        (self.root / "test_sample.py").write_text(PASS_TEST.replace("self.assertEqual(2 + 2, 4)",
                                                                 "__import__('time').sleep(.5)"))
        plan = self.freeze()
        command = self.cli(plan)
        first = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(lambda: first.kill() if first.poll() is None else None)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            state = build_unit.read_status(self.root, self.version, self.build)
            if state["status"] == "RUNNING":
                break
            time.sleep(.01)
        else:
            self.fail("no RUNNING state")
        self.assertIn("deadline_at", state)
        self.assertEqual(state["pid"], first.pid)
        second = subprocess.run(command, capture_output=True, text=True, timeout=5)
        self.assertEqual(json.loads(second.stdout)["status"], "RUNNING", second.stdout)
        stdout, stderr = first.communicate(timeout=10)
        result = json.loads(stdout)
        self.assertEqual(result["status"], "PASS", (result, stderr))
        again = subprocess.run(command, capture_output=True, text=True, timeout=5)
        self.assertEqual(json.loads(again.stdout)["runs"], result["runs"])
        directory = build_unit.build_dir(self.root, self.version, self.build)
        self.assertEqual(len(list(directory.glob("suite-*.log"))), 1)
        rows = build_unit.test_ledger.load(directory / "worktree", directory.parent / "ledger")
        self.assertEqual(len([row for row in rows if row["kind"] == "run"]), 1)
        self.assertEqual(rows[0]["scope"], "version")
        self.assert_cleaned()

    def test_real_failure_counts_and_error(self):
        (self.root / "test_sample.py").write_text(FAIL_TEST)
        result = self.run_plan(self.freeze())
        self.assertEqual(result["status"], "FAIL", result)
        self.assertEqual(result["counts"], {"passed": 0, "failed": 1, "skipped": 0})
        self.assertIn("test_fail", result["failed_cases"][0])
        self.assertIn("AssertionError", result["primary_error"])
        self.assert_cleaned()

    def test_missing_tool_and_module_are_unverified(self):
        for index, argv in enumerate((["missing-build-unit-executable"],
                                      [sys.executable, "-m", "no_such_build_unit_module"])):
            self.build = f'build{index}'
            plan = self.freeze([self.suite(argv)])
            result = self.run_plan(plan)
            self.assertEqual(result["status"], "UNVERIFIED", result)
            self.assertEqual([run["status"] for run in result["runs"]], ["UNVERIFIED"])
            self.assertEqual(result["counts"], build_unit.NULL_COUNTS)
        self.assert_cleaned()

    def test_missing_import_in_unittest_is_not_product_bug(self):
        (self.root / "test_sample.py").write_text("import no_such_dependency\n")
        result = self.run_plan(self.freeze())
        self.assertEqual(result["status"], "UNVERIFIED", result)
        self.assertIn("未解析导入", result["primary_error"])

    def test_unknown_runner_counts_are_null_nonzero_is_unverified(self):
        (self.root / "runner.py").write_text("print('opaque custom runner output')\n")
        plan = self.freeze([self.suite([sys.executable, "runner.py"])])
        result = self.run_plan(plan)
        self.assertEqual(result["status"], "UNVERIFIED", result)
        self.assertEqual(result["runs"][0]["reason"], "test-coverage-unverified")
        self.assertEqual(result["counts"], build_unit.NULL_COUNTS)
        (self.root / "runner.py").write_text("raise SystemExit(8)\n")
        self.build = "build2"
        plan = self.freeze([self.suite([sys.executable, "runner.py"])])
        self.assertEqual(self.run_plan(plan)["status"], "UNVERIFIED")

    def test_total_budget_shared_across_suites(self):
        (self.root / "test_sample.py").write_text(PASS_TEST.replace("self.assertEqual(2 + 2, 4)",
                                                                 "__import__('time').sleep(.35)"))
        for name in ('first', 'second'):
            (self.root / name / 'tests').mkdir(parents=True)
            (self.root / name / 'tests' / 'test_sample.py').write_text((self.root / 'test_sample.py').read_text())
        plan = self.freeze([self.suite(cwd='first'), self.suite(cwd='second')],
                           tests=['first/tests/test_sample.py', 'second/tests/test_sample.py'])
        started = time.monotonic()
        result = self.run_plan(plan, timeout=.95)
        self.assertEqual(result["status"], "TIMEOUT", result)
        self.assertLess(time.monotonic() - started, 2)
        self.assertEqual(result["runs"][0]["status"], "PASS", result)
        self.assertLess(len(result["runs"]), 3)
        self.assert_cleaned()

    def test_timeout_kills_descendant_process_group(self):
        (self.root / "runner.py").write_text("""import subprocess, sys, time
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
print('CHILD_PID=' + str(child.pid), flush=True)
time.sleep(60)
""")
        result = self.run_plan(self.freeze([self.suite([sys.executable, "runner.py"])]), timeout=3)
        self.assertEqual(result["status"], "TIMEOUT", result)
        text = Path(result["runs"][0]["log"]).read_text()
        pid = int(text.split("CHILD_PID=")[1].splitlines()[0])
        status = Path(f"/proc/{pid}/status")
        if status.exists():
            self.assertRegex(status.read_text(), r"State:\s+[ZX]")
        self.assert_cleaned()

    def test_retry_after_tool_restored_preserves_original_log(self):
        tool = self.base / "unit-tool"
        plan = self.freeze([self.suite([str(tool)])])
        missing = self.run_plan(plan)
        self.assertEqual(missing["status"], "UNVERIFIED", missing)
        # 执行器目录不是 cwd，直接脚本 runner 显式从 worktree 载入测试。
        tool.write_text("#!" + sys.executable + "\nimport os, sys, unittest\nsys.path.insert(0, os.getcwd())\nunittest.main(module='test_sample', verbosity=2, argv=['unit-tool'])\n")
        tool.chmod(0o755)
        self.assertTrue(self.run_plan(plan)["reused"])
        retried = self.run_plan(plan, retry=True)
        self.assertEqual(retried["status"], "PASS", retried)
        self.assertEqual(retried["attempt"], 2)
        self.assertNotEqual(retried["runs"][0]["log"], missing["runs"][0]["log"])
        self.assertTrue(Path(missing["runs"][0]["log"]).exists())
        self.assert_cleaned()

    def test_baseline_commit_binding_rejects_override_even_standalone(self):
        plan = self.freeze(baseline=True)
        path = Path(build_unit.baseline(self.root))
        data = json.loads(path.read_text())
        data["versions"][self.version]["builds"][0]["push_commit"] = "0" * 40
        path.write_text(json.dumps(data))
        # manifest 先于 push_commit 校验是新顺序；此处 manifest 保持与委派一致，必须由 push_commit 单独拦截。
        result = self.run_plan(plan)
        self.assertEqual(result["status"], "UNVERIFIED", result)
        self.assertIn("push_commit", result["primary_error"])
        self.assertFalse(result["runs"])

    def test_changed_manifest_after_delegation_is_refused_before_push_commit_check(self):
        plan = self.freeze(baseline=True)
        self.delegate(plan)
        plan["standalone"] = True
        result = self.run_plan(plan, execution_context=self.contexts[plan["build"]])
        self.assertEqual(result["status"], "UNVERIFIED", result)
        self.assertIn("manifest", result["primary_error"])
        self.assertEqual(result["runs"], [])

    def test_full_commit_required_standalone_evidence_required(self):
        plan = self.freeze()
        short = copy.deepcopy(plan)
        short["commit"] = self.commit[:12]
        self.assertEqual(self.run_plan(short)["status"], "UNVERIFIED")
        plan["build"] = "build2"
        plan["deployment"]["verified"] = False
        result = self.run_plan(plan)
        self.assertEqual(result["status"], "UNVERIFIED", result)
        self.assertIn("standalone", result["primary_error"])

    def test_markdown_unique_source_and_dirty_plan_rejected(self):
        plan = self.freeze(markdown=True)
        self.assertEqual(self.run_plan(plan)["status"], "PASS")
        plan["build"] = "build2"
        plan["suites"][0]["full_argv"] = [sys.executable, "-m", "unittest", "-v"]
        result = self.run_plan(plan)
        self.assertEqual(result["status"], "UNVERIFIED", result)
        self.assertIn("suites", result["primary_error"])

    def test_source_sha_missing_input_and_cwd_escape_fail_closed(self):
        plan = self.freeze([self.suite(inputs=["does-not-exist"])])
        result = self.run_plan(plan)
        self.assertEqual(result["status"], "UNVERIFIED", result)
        self.assert_cleaned()
        plan["build"] = "build2"
        plan["source"]["sha256"] = "0" * 64
        self.assertIn("SHA256", self.run_plan(plan)["primary_error"])
        self.build = "build3"
        plan = self.freeze([self.suite(cwd="../")])
        self.assertIn("worktree", self.run_plan(plan)["primary_error"])

    def test_outside_symlink_is_not_a_test_input(self):
        (self.root / "external.py").symlink_to(self.base / "outside.py")
        (self.base / "outside.py").write_text("VALUE=1\n")
        plan = self.freeze()
        result = self.run_plan(plan)
        self.assertEqual(result["status"], "UNVERIFIED", result)
        self.assertIn("符号链接", result["primary_error"])
        self.assert_cleaned()

    def test_existing_directory_never_removed(self):
        plan = self.freeze()
        directory = build_unit.build_dir(self.root, self.version, self.build) / "worktree"
        directory.mkdir(parents=True)
        sentinel = directory / "keep.txt"
        sentinel.write_text("belongs to someone else")
        result = self.run_plan(plan)
        self.assertEqual(result["status"], "UNVERIFIED", result)
        self.assertEqual(sentinel.read_text(), "belongs to someone else")
        self.assertIn("拒绝接管", result["primary_error"])

    def test_status_stale_running_not_permanent_and_corrupt_not_pass(self):
        directory = build_unit.build_dir(self.root, self.version, self.build)
        stale = build_unit.blank(self.version, self.build, "1" * 40, "RUNNING")
        build_unit.save_result(directory, stale)
        result = build_unit.read_status(self.root, self.version, self.build)
        self.assertEqual(result["status"], "UNVERIFIED")
        self.assertEqual(result["reason"], "executor-interrupted")
        (directory / "result.json").write_text('{"schema": 1, "status": "PASS"}')
        self.assertEqual(build_unit.read_status(self.root, self.version, self.build)["status"], "UNVERIFIED")

    def test_junit_counts_failure_and_malformed_report(self):
        xml = '<testsuites><testsuite><testcase name="ok"/><testcase classname="Example" name="bad"><failure message="real mismatch"/></testcase><testcase name="skip"><skipped/></testcase></testsuite></testsuites>'
        (self.root / "runner.py").write_text("from pathlib import Path\np=Path('reports/result.xml')\np.parent.mkdir(exist_ok=True)\np.write_text(" + repr(xml) + ")\nraise SystemExit(1)\n")
        plan = self.freeze([self.suite([sys.executable, "runner.py"], junit_xml="reports/result.xml")])
        result = self.run_plan(plan)
        self.assertEqual(result["status"], "FAIL", result)
        self.assertEqual(result["counts"], {"passed": 1, "failed": 1, "skipped": 1})
        self.assertEqual(result["failed_cases"], ["Example.bad"])
        self.assertEqual(result["primary_error"], "real mismatch")
        self.assert_cleaned()

    def test_unittest_expected_and_unexpected_successes(self):
        text = "Ran 5 tests in 0.1s\n\nFAILED (failures=1, skipped=1, expected failures=1, unexpected successes=1)\n"
        counts, _, _ = build_unit.parse_output(text)
        self.assertEqual(counts, {"passed": 1, "failed": 2, "skipped": 2})

    def test_zero_test_suite_is_unverified(self):
        (self.root / "test_sample.py").write_text("import unittest\n")
        result = self.run_plan(self.freeze())
        self.assertEqual(result["status"], "UNVERIFIED", result)
        self.assertEqual(result["runs"][0]["reason"], "no-tests-executed")

    def test_cli_failure_returns_json_and_does_not_abort_browser(self):
        (self.root / "test_sample.py").write_text(FAIL_TEST)
        plan = self.freeze()
        process = subprocess.run(self.cli(plan), capture_output=True, text=True, timeout=10)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout)["status"], "FAIL")
        status = subprocess.run([sys.executable, str(SCRIPT), "status", "--root", str(self.root),
                                 "--version", self.version, "--build", self.build],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(json.loads(status.stdout)["status"], "FAIL")

    def test_same_build_changed_plan_cannot_reuse_pass(self):
        plan = self.freeze()
        self.assertEqual(self.run_plan(plan)["status"], "PASS")
        changed = copy.deepcopy(plan)
        changed["suites"][0]["env_id"] = "different"
        self.assertEqual(self.run_plan(changed)["status"], "UNVERIFIED")
        self.assertEqual(build_unit.read_status(self.root, self.version, self.build)["status"], "PASS")

    def test_reuse_rechecks_baseline_binding(self):
        plan = self.freeze(baseline=True)
        self.assertEqual(self.run_plan(plan)["status"], "PASS")
        path = Path(build_unit.baseline(self.root))
        data = json.loads(path.read_text())
        data["versions"][self.version]["builds"][0]["push_commit"] = "0" * 40
        path.write_text(json.dumps(data))
        self.assertEqual(self.run_plan(plan)["status"], "UNVERIFIED")

    def test_missing_and_malformed_junit_report_are_unverified(self):
        (self.root / "runner.py").write_text("print('runner completed without promised XML')\n")
        plan = self.freeze([self.suite([sys.executable, "runner.py"], junit_xml="reports/result.xml")])
        self.assertEqual(self.run_plan(plan)["status"], "UNVERIFIED")
        self.build = "build2"
        (self.root / "runner.py").write_text("from pathlib import Path\np=Path('reports/result.xml')\np.parent.mkdir(exist_ok=True)\np.write_text('invalid xml')\n")
        plan = self.freeze([self.suite([sys.executable, "runner.py"], junit_xml="reports/result.xml")])
        self.assertEqual(self.run_plan(plan)["status"], "UNVERIFIED")
        self.assert_cleaned()

    def test_markdown_ambiguous_source_and_invalid_json_are_unverified(self):
        plan = self.freeze(markdown=True)
        path = self.root / "contract.md"
        path.write_text(path.read_text() * 2)
        self.git("add", ".")
        self.git("commit", "-qm", "duplicate source")
        plan["commit"] = plan["deployment"]["commit"] = self.git("rev-parse", "HEAD")
        plan["source"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertEqual(self.run_plan(plan)["status"], "UNVERIFIED")
        self.build = "build2"
        plan = self.freeze()
        path = self.root / "unit-plan.json"
        path.write_text("[]")
        self.git("add", ".")
        self.git("commit", "-qm", "invalid schema")
        plan["commit"] = plan["deployment"]["commit"] = self.git("rev-parse", "HEAD")
        plan["source"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertEqual(self.run_plan(plan)["status"], "UNVERIFIED")

    def test_registered_missing_worktree_not_removed(self):
        plan = self.freeze()
        directory = build_unit.build_dir(self.root, self.version, self.build) / "worktree"
        directory.parent.mkdir(parents=True)
        self.git("worktree", "add", "--detach", str(directory), self.commit)
        import shutil
        shutil.rmtree(directory)
        result = self.run_plan(plan)
        self.assertEqual(result["status"], "UNVERIFIED")
        self.assertIn(str(directory), self.git("worktree", "list", "--porcelain"))

    def test_sigterm_reports_unverified_and_cleans(self):
        (self.root / "test_sample.py").write_text(PASS_TEST.replace("self.assertEqual(2 + 2, 4)",
                                                                 "__import__('time').sleep(60)"))
        plan = self.freeze()
        process = subprocess.Popen(self.cli(plan), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(lambda: process.kill() if process.poll() is None else None)
        directory = build_unit.build_dir(self.root, self.version, self.build)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            logs = list(directory.glob("suite-*.log"))
            if logs and "test_pass" in logs[0].read_text():
                break
            time.sleep(.01)
        else:
            self.fail("runner never started")
        process.send_signal(signal.SIGTERM)
        stdout, stderr = process.communicate(timeout=10)
        result = json.loads(stdout)
        self.assertEqual(result["status"], "UNVERIFIED", (result, stderr))
        self.assert_cleaned()

    def test_environment_cannot_escape_worktree_via_parent_path(self):
        plan = self.freeze([self.suite(env={"PYTHONPATH": "../../../../../"})])
        result = self.run_plan(plan)
        self.assertEqual(result["status"], "UNVERIFIED", result)
        self.assertIn("父目录", result["primary_error"])
        self.assertFalse(result["runs"])

    def test_missing_or_non_autopilot_context_never_runs(self):
        from entry_context import resolve_context
        plan = self.freeze()
        for context in (None, resolve_context(self.root, 'sprint-aiauto-test', version=self.version)['execution_context']):
            result = build_unit.run_build(self.root, self.version, plan['build'], plan['commit'], plan, execution_context=context)
            self.assertEqual(result['status'], 'UNVERIFIED', result)
            self.assertEqual(result['runs'], [])
            self.assertFalse(build_unit.build_dir(self.root, self.version, plan['build']).exists())

    def test_manifest_without_formal_case_mapping_is_refused(self):
        plan = self.freeze(extra_case='TC-HISTORICAL')
        result = self.run_plan(plan)
        self.assertEqual(result['status'], 'UNVERIFIED', result)
        self.assertEqual(result['runs'], [])
        self.assertIn('正式用例', result['primary_error'])

    def test_filtered_runner_and_system_wide_runner_are_refused(self):
        for index, argv in enumerate(([sys.executable, '-m', 'pytest', '-k', 'one', '{tests}'],
                                      [sys.executable, '-m', 'unittest', 'discover'])):
            self.build = f'filter{index}'
            plan = self.freeze([self.suite(argv)])
            if index:
                plan['suites'][0]['runners'][0]['argv'] = argv
            result = self.run_plan(plan)
            self.assertEqual(result['status'], 'UNVERIFIED', result)
            self.assertEqual(result['runs'], [])

    def test_unchanged_evidence_is_carried_across_builds_and_changed_inputs_rerun(self):
        first_plan = self.freeze()
        first = self.run_plan(first_plan, timeout=20)
        self.assertEqual(first['status'], 'PASS', first)
        self.build = 'V1.0.0_build2'
        second = self.run_plan(self.freeze(), timeout=20)
        self.assertEqual(second['status'], 'PASS', second)
        self.assertTrue(second['runs'][0]['reused'])
        self.assertEqual(second['runs'][0]['source_run_id'], first['runs'][0]['run_id'])
        self.assertEqual(second['runs'][0]['counts'], first['runs'][0]['counts'])
        self.assertNotEqual(second['runs'][0]['run_id'], first['runs'][0]['run_id'])
        self.assertEqual(second['build'], 'V1.0.0_build2')
        (self.root / 'test_sample.py').write_text(PASS_TEST + '\n# actual code change\n')
        self.build = 'V1.0.0_build3'
        third = self.run_plan(self.freeze(), timeout=20)
        self.assertEqual(third['status'], 'PASS', third)
        self.assertFalse(third['runs'][0].get('reused'))

    def test_scheduler_inherits_only_traceable_current_build_delegation(self):
        import aidp_scheduler
        plan = self.freeze(baseline=True)
        baseline = Path(build_unit.baseline(self.root))
        with self.assertRaisesRegex(ValueError, '委派'):
            aidp_scheduler.test_handoff_context(self.root)
        context = self.delegate(plan)
        data = json.loads(baseline.read_text())
        node = data['versions'][self.version]
        node['current_build'] = plan['build']
        data['aiauto'] = {'execution_context': context}
        baseline.write_text(json.dumps(data))
        self.assertEqual(aidp_scheduler.test_handoff_context(self.root)[0], context)
        # 旧 activeContext / 命令名 / 历史 build 都不是授权。
        node['current_build'] = 'V1.0.0_older_build'
        baseline.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, '当前版本当前 build'):
            aidp_scheduler.test_handoff_context(self.root)
        from entry_context import resolve_context
        ordinary = resolve_context(self.root, 'sprint-aiauto-test', version=self.version)['execution_context']
        data['aiauto'] = {'execution_context': ordinary}
        node['current_build'] = plan['build']
        baseline.write_text(json.dumps(data))
        with self.assertRaises(Exception):
            aidp_scheduler.test_handoff_context(self.root)

    def test_test_only_context_cannot_start_other_actions(self):
        from execution_policy import require_action, PolicyError
        context = self.delegate(self.freeze())
        for action in ('implement', 'commit', 'push', 'deploy'):
            with self.assertRaises(PolicyError):
                require_action(context, action)

    def test_self_check_real_git(self):
        result = build_unit.self_check()
        self.assertTrue(result["ok"], result)


if __name__ == "__main__":
    unittest.main()
