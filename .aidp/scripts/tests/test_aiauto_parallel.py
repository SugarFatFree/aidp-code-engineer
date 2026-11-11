#!/usr/bin/env python3
"""真实 build CLI → emit → join 联动；浏览器替身独立进程，失败/超时互不取消。

只用临时 Git 和标准库，不运行本仓 /sprint 命令，不联网、不启动部署服务。
"""
import json
import hashlib
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))
from unit_report_merge import read_payload

UNIT_TEST = '''import os, time, unittest
from pathlib import Path
class BuildTest(unittest.TestCase):
 def test_committed_code(self):
  Path(os.environ['UNIT_STARTED']).write_text(str(time.time()))
  deadline = time.monotonic() + 5
  while not Path(os.environ['BROWSER_STARTED']).exists():
   if time.monotonic() >= deadline: self.fail('browser was not started concurrently')
   time.sleep(.01)
  with open(os.environ['UNIT_COUNTER'], 'a') as handle: handle.write('executed\\n')
  time.sleep(float(os.environ['UNIT_DELAY']))
  self.assertEqual(Path('value.txt').read_text(), 'deployed commit')
  self.assertNotIn('DEPLOY_DATABASE_URL', os.environ)
  if os.environ['UNIT_MODE'] == 'FAIL': self.fail('real committed unittest assertion')
 @unittest.skip('fixture skip')
 def test_skipped(self): pass
'''

BROWSER_PROCESS = '''import json, sys, time
from pathlib import Path
started, unit_started, mode, delay, version, build, commit, wait_unit = sys.argv[1:]
Path(started).write_text(str(time.time()))
if wait_unit == '1':
 deadline = time.monotonic() + 5
 while not Path(unit_started).exists():
  if time.monotonic() >= deadline: raise SystemExit('unit never started concurrently')
  time.sleep(.01)
time.sleep(float(delay))
payload = {'version':version, 'build':build, 'commit':commit,
           'summary':{'total':1,'pass':int(mode=='PASS'),'fail':int(mode=='FAIL'),
                      'block':0,'skip':0,'na':0,'passRate':int(mode=='PASS')},
           'cases':[{'id':'TC-PARALLEL-1','title':'isolated browser process fixture',
                     'result':'pass' if mode=='PASS' else 'fail'}],
           'fixtureBrowserFinishedAt':time.time()}
if mode == 'N/A':
 payload = {'version':version, 'build':build, 'commit':commit,
            'fixtureBrowserFinishedAt':time.time()}
print(json.dumps(payload), flush=True)
raise SystemExit(1 if mode == 'FAIL' else 0)
'''


class AiautoParallelIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="aidp-aiauto-parallel-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "repo"
        self.root.mkdir()
        self.version = "V1.0.0"
        self.build = "V1.0.0_build1001"
        self.browser_started = self.base / "browser.started"
        self.unit_started = self.base / "unit.started"
        self.counter = self.base / "unit-executions.txt"
        self.processes = []
        self.addCleanup(self.cleanup_processes)
        self.git("init", "-q")
        self.git("config", "user.name", "Parallel integration")
        self.git("config", "user.email", "parallel@example.invalid")
        (self.root / ".gitignore").write_text("memory/\n__pycache__/\n")
        (self.root / "value.txt").write_text("deployed commit")
        (self.root / "test_build.py").write_text(UNIT_TEST)

    def cleanup_processes(self):
        for process in self.processes:
            if process.poll() is None:
                process.terminate()
                try:
                    process.communicate(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.communicate(timeout=3)
            else:
                process.communicate()

    def git(self, *args):
        process = subprocess.run(["git", "-C", str(self.root), *args], capture_output=True, text=True,
                                 env=dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull))
        self.assertEqual(process.returncode, 0, process.stderr)
        return process.stdout.strip()

    def prepare(self, unit_mode="PASS", unit_delay=.05, opaque=False, missing=False):
        env = {"UNIT_MODE": unit_mode, "UNIT_DELAY": str(unit_delay),
               "UNIT_STARTED": str(self.unit_started), "BROWSER_STARTED": str(self.browser_started),
               "UNIT_COUNTER": str(self.counter)}
        def suite(cwd, env_id, argv):
            return {"cwd": cwd, "env_id": env_id, "inputs": [], "external_dependencies": "none", "env": env,
                    "runners": [{"suffixes": [".py"], "argv": argv, "cwd": cwd, "env_id": env_id}]}
        runner = [sys.executable, "-m", "unittest", "-v", "{tests}"]
        if missing:
            runner = ["aidp-integration-missing-unit-tool", "{tests}"]
        suites = [suite(".", "isolated-stdlib-build", runner)]
        tests = ["test_build.py"]
        if opaque:
            # 第二个真实套件放在独立 cwd/env，仍由同一份冻结清单明确列名。
            (self.root / "second/tests").mkdir(parents=True)
            (self.root / "second/tests/test_build.py").write_text(
                UNIT_TEST.replace("Path('value.txt')", "(Path(__file__).resolve().parents[2] / 'value.txt')"))
            suites.append(suite("second", "isolated-second-suite", runner))
            tests.append("second/tests/test_build.py")
        formal = self.root / "docs/testing" / self.version / "正式用例"
        formal.mkdir(parents=True)
        index = formal / "00_索引.md"
        index.write_text("# 本版本正式用例索引\nTC-PARALLEL-1\n")
        (formal / "03_cases.md").write_text("#### 用例 TC-PARALLEL-1: parallel fixture\n")
        acceptance = {"version": self.version, "acceptance_tests": tests, "dependencies": ["value.txt"],
                      "cases": [{"id": "TC-PARALLEL-1", "test_files": tests}],
                      "case_index": {"path": index.relative_to(self.root).as_posix(),
                                     "sha256": hashlib.sha256(index.read_bytes()).hexdigest()}}
        acceptance_path = formal.parent / "acceptance.json"
        acceptance_path.write_text(json.dumps(acceptance))
        config = json.dumps({"schema": 1, "suites": suites})
        # 使用部署 commit 内的真实 Markdown 契约来源，不依赖当前工作区计划。
        source = "# Full unit contract\n\n```aidp-test-plan\n" + config + "\n```\n"
        (self.root / "contract.md").write_text(source)
        self.git("add", ".")
        self.git("commit", "-qm", "real deployment fixture")
        self.commit = self.git("rev-parse", "HEAD")
        self.plan = {"schema": 1, "version": self.version, "build": self.build, "commit": self.commit,
                     "source": {"path": "contract.md", "sha256": hashlib.sha256(source.encode()).hexdigest()},
                     "suites": suites, "acceptance_tests": tests, "dependencies": ["value.txt"],
                     "acceptance_baseline": {"path": acceptance_path.relative_to(self.root).as_posix(),
                                             "sha256": hashlib.sha256(acceptance_path.read_bytes()).hexdigest()}}
        self.baseline = self.root / "memory/.sprint-autopilot-baseline.json"
        self.baseline.parent.mkdir(exist_ok=True)
        self.baseline.write_text(json.dumps({"versions": {self.version: {
            "current_build": self.build, "builds": [{"build": self.build, "push_commit": self.commit}]}}}))
        # 两种污染都应不影响已部署 commit 的单测。
        (self.root / "value.txt").write_text("dirty main workspace")
        (self.root / "contract.md").write_text("uncommitted broken plan")

    def delegate(self):
        """真实 autopilot test-only 根 + 同 version/build 子任务；测试不能直接伪造授权。"""
        sys.path.insert(0, str(SCRIPTS))
        from entry_context import resolve_autopilot_root, fork_test_build
        if not hasattr(self, "parent"):
            self.parent = resolve_autopilot_root(self.root, self.version, authorization_source={
                "kind": "explicit-command", "command": "sprint-autopilot", "request_id": "parallel-fixture",
                "options": ["--skip-dev"]})["execution_context"]
        manifest = self.root / "memory" / (self.build + "-plan.json")
        manifest.write_text(json.dumps(self.plan))
        context = fork_test_build(self.root, self.parent, self.version, self.build,
                                  manifest=manifest)["execution_context"]
        return context, manifest

    def unit_command(self, timeout=5):
        context, manifest = self.delegate()
        return [sys.executable, str(SCRIPTS / "build_unit_test.py"), "run",
                "--root", str(self.root), "--version", self.version, "--build", self.build,
                "--commit", self.commit, "--plan", str(manifest), "--execution-context", context,
                "--timeout", str(timeout)]

    def spawn(self, argv):
        process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                   start_new_session=True,
                                   env=dict(os.environ, DEPLOY_DATABASE_URL="https://must-not-inherit.invalid"))
        self.processes.append(process)
        return process

    def start_pair(self, browser_mode="PASS", browser_delay=.05, timeout=5, wait_unit=True):
        # 连续两次 Popen 之间不等待任何一方，测试代码与浏览器替身用双向文件屏障证明重叠。
        unit = self.spawn(self.unit_command(timeout))
        browser = self.spawn([sys.executable, "-c", BROWSER_PROCESS,
                              str(self.browser_started), str(self.unit_started), browser_mode,
                              str(browser_delay), self.version, self.build, self.commit, str(int(wait_unit))])
        return unit, browser

    def collect(self, process):
        stdout, stderr = process.communicate(timeout=10)
        self.assertTrue(stdout.strip(), stderr)
        return json.loads(stdout)

    def result_path(self):
        return self.root / "memory/.aidp/build-unit" / self.version / self.build / "result.json"

    def report_path(self):
        return self.root / "docs/reports" / self.version / "AI测试报告/data" / (self.build + ".js")

    def cli_json(self, command):
        process = subprocess.run(command, capture_output=True, text=True, timeout=15)
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        return json.loads(process.stdout)

    def emit_and_join(self, browser_payload, unit_result, backend=False, settle=True):
        draft = self.base / (self.build + "-browser.json")
        draft.write_text(json.dumps(browser_payload))
        command = [sys.executable, str(SCRIPTS / "emit-report.py"), "--kind", "test",
                   "--version", self.version, "--build", self.build, "--data", str(draft),
                   "--repo-root", str(self.root), "--templates-root", str(REPO / ".aidp/templates/reports"),
                   "--unit-result", str(self.result_path()), "--commit", self.commit,
                   "--record-baseline", "0", "--keep-input", "--json"]
        if backend:
            command += ["--browser-na-reason", "纯后端，无浏览器适用面"]
        emitted = self.cli_json(command)
        report = read_payload(self.report_path())
        self.assertEqual(report["unitTests"]["status"], unit_result["status"])
        self.assertEqual(report["unitTests"]["counts"], unit_result["counts"])
        self.assertEqual(report["unitTests"]["failed_cases"], unit_result["failed_cases"])
        self.assertEqual(report["unitTests"]["primary_error"], unit_result["primary_error"])
        # 跨组件原样保留真实执行器证据，不能缩成mock PASS或改成字符串命令。
        for before, after in zip(unit_result["runs"], report["unitTests"]["runs"]):
            for key in ("run_id", "command", "cwd", "env_id", "counts", "failed_cases", "primary_error", "log"):
                self.assertEqual(after[key], before[key], key)
            self.assertIsInstance(after["command"], list)
            self.assertTrue(Path(after["log"]).is_file())
        self.assertEqual(len(report["unitTests"]["runs"]), len(unit_result["runs"]))
        self.assertTrue((self.report_path().parent.parent / "index.html").is_file())
        if not settle:
            return emitted, report, None
        joined = self.cli_json([sys.executable, str(SCRIPTS / "aiauto_test_join.py"), "settle",
                                "--root", str(self.root), "--version", self.version, "--build", self.build,
                                "--report", str(self.report_path())])
        return emitted, report, joined

    def release_state(self):
        process = subprocess.run([sys.executable, str(SCRIPTS / "aiauto_test_join.py"), "release-state",
                                  "--root", str(self.root), "--version", self.version],
                                 capture_output=True, text=True, timeout=5)
        self.assertEqual(process.returncode, 0, process.stderr)
        return process.stdout.strip()

    def node(self):
        return json.loads(self.baseline.read_text())["versions"][self.version]

    def assert_not_frozen(self):
        node = self.node()
        self.assertNotIn("needs_human", node)
        self.assertNotIn("aiauto_tested_at", node)
        self.assertFalse(node["builds"][-1].get("ai_report_finalized"))

    def test_unit_failure_does_not_cancel_browser_and_real_bug_joins_once(self):
        self.prepare(unit_mode="FAIL", unit_delay=.03)
        unit, browser = self.start_pair(browser_delay=.45)
        unit_result = self.collect(unit)
        self.assertEqual(unit_result["status"], "FAIL", unit_result)
        self.assertIsNone(browser.poll(), "unit failure cancelled the independent browser")
        browser_result = self.collect(browser)
        self.assertEqual(browser.returncode, 0)
        self.assertLess(unit_result["finished_at"], browser_result["fixtureBrowserFinishedAt"])
        emitted, report, joined = self.emit_and_join(browser_result, unit_result)
        self.assertEqual(report["summary"]["browserStatus"], "PASS")
        self.assertEqual(emitted["overallStatus"], "FAIL")
        self.assertTrue(joined["unit_failed"])
        self.assertEqual(len(joined["bug_ids"]), 1)
        document = self.root / "docs/bugfix" / self.version / ("bugfix-unit-" + self.build + ".md")
        before = document.read_text()
        again = self.cli_json([sys.executable, str(SCRIPTS / "aiauto_test_join.py"), "settle",
                               "--root", str(self.root), "--version", self.version, "--build", self.build,
                               "--report", str(self.report_path())])
        self.assertEqual(joined["bug_ids"], again["bug_ids"])
        self.assertEqual(document.read_text(), before)
        self.assertIn(unit_result["runs"][0]["run_id"], before)
        self.assertIn("real committed unittest assertion", before)
        self.assertEqual(self.release_state(), "failed")

    def test_browser_failure_does_not_cancel_real_unit(self):
        self.prepare(unit_delay=.45)
        unit, browser = self.start_pair(browser_mode="FAIL", browser_delay=.03)
        browser_result = self.collect(browser)
        self.assertEqual(browser.returncode, 1)
        self.assertIsNone(unit.poll(), "browser failure cancelled the unit worker")
        unit_result = self.collect(unit)
        self.assertEqual(unit_result["status"], "PASS", unit_result)
        self.assertLess(browser_result["fixtureBrowserFinishedAt"], unit_result["finished_at"])
        browser_result['failureTriage'] = {'schema': 1, 'build': self.build, 'commit': self.commit,
            'items': [{'refs': ['case:TC-PARALLEL-1'], 'category': 'auto_fixable',
                       'reason': '已确认浏览器断言失败为代码缺陷'}]}
        _, report, joined = self.emit_and_join(browser_result, unit_result)
        self.assertEqual(report["summary"]["overallStatus"], "FAIL")
        self.assertFalse(joined["unit_failed"])
        self.assertTrue(self.node()['auto_fixable_pending'])
        self.assertEqual(joined['next_action'], 'bugfix')
        self.assertEqual(joined["bug_ids"], [])
        self.assertEqual(self.release_state(), "failed")

    def test_unit_timeout_kills_only_unit_and_browser_still_finishes(self):
        self.prepare(unit_delay=60)
        unit, browser = self.start_pair(browser_delay=3.5, timeout=2.5)
        unit_result = self.collect(unit)
        self.assertEqual(unit_result["status"], "TIMEOUT", unit_result)
        self.assertIsNone(browser.poll(), "unit timeout killed the browser process")
        browser_result = self.collect(browser)
        self.assertEqual(browser.returncode, 0)
        emitted, report, joined = self.emit_and_join(browser_result, unit_result)
        self.assertEqual(report["summary"]["browserStatus"], "PASS")
        self.assertEqual(emitted["overallStatus"], "TIMEOUT")
        self.assertEqual(joined["bug_ids"], [])
        self.assertFalse(emitted["freeze_ready"])
        self.assertEqual(self.release_state(), "pending")
        self.assert_not_frozen()

    def test_browser_timeout_does_not_cancel_unit_or_fake_browser_pass(self):
        self.prepare(unit_delay=.45)
        unit, browser = self.start_pair(browser_delay=60)
        with self.assertRaises(subprocess.TimeoutExpired):
            browser.communicate(timeout=.15)
        os.killpg(browser.pid, signal.SIGKILL)
        browser.communicate(timeout=5)
        self.assertIsNone(unit.poll(), "browser timeout cancelled the unit worker")
        unit_result = self.collect(unit)
        self.assertEqual(unit_result["status"], "PASS", unit_result)
        browser_result = {"version": self.version, "build": self.build, "commit": self.commit,
                          "browserTests": {"status": "TIMEOUT", "reason": "browser fixture exceeded its budget"},
                          "summary": {"total": 1, "pass": 0, "fail": 0, "block": 1,
                                      "skip": 0, "na": 0, "passRate": 0},
                          "cases": [{"id": "TC-PARALLEL-1", "title": "browser budget", "result": "block"}]}
        browser_result['failureTriage'] = {'schema': 1, 'build': self.build, 'commit': self.commit,
            'items': [{'refs': ['case:TC-PARALLEL-1', 'browser:status'], 'category': 'environment',
                       'reason': '浏览器进程预算耗尽，未核验业务'}]}
        emitted, report, joined = self.emit_and_join(browser_result, unit_result)
        self.assertFalse(self.node().get('auto_fixable_pending', False))
        self.assertEqual(len(self.node()['environment_unverified']), 1)
        self.assertEqual(report["summary"]["browserStatus"], "TIMEOUT")
        self.assertEqual(emitted["overallStatus"], "TIMEOUT")
        self.assertFalse(emitted["freeze_ready"])
        self.assertEqual(joined["bug_ids"], [])
        self.assertEqual(self.release_state(), "pending")
        self.assert_not_frozen()

    def test_backend_na_still_executes_real_unit_and_emits_report(self):
        self.prepare()
        unit, browser = self.start_pair(browser_mode="N/A")
        browser_result, unit_result = self.collect(browser), self.collect(unit)
        self.assertEqual(unit_result["status"], "PASS", unit_result)
        emitted, report, joined = self.emit_and_join(browser_result, unit_result, backend=True)
        self.assertEqual(report["cases"], [])
        self.assertEqual(report["summary"]["browserStatus"], "N/A")
        self.assertEqual(report["unitTests"]["counts"], {"passed": 1, "failed": 0, "skipped": 1})
        self.assertTrue(emitted["success_ready"])
        self.assertTrue(joined["converged"])
        self.assertEqual(self.release_state(), "pass")

    def test_backend_na_missing_unit_tool_keeps_null_counts_and_pending(self):
        self.prepare(missing=True)
        unit, browser = self.start_pair(browser_mode="N/A", wait_unit=False)
        browser_result, unit_result = self.collect(browser), self.collect(unit)
        self.assertEqual(unit_result["status"], "UNVERIFIED", unit_result)
        emitted, report, joined = self.emit_and_join(browser_result, unit_result, backend=True)
        self.assertIn(report["unitTests"]["runs"][0]["exit_code"], (2, 127))
        self.assertEqual(report["unitTests"]["counts"], {"passed": None, "failed": None, "skipped": None})
        self.assertFalse(emitted["success_ready"])
        self.assertTrue(joined["unverified"])
        self.assertEqual(joined["bug_ids"], [])
        self.assertEqual(self.release_state(), "pending")
        self.assert_not_frozen()

    def test_multiple_real_suites_preserve_run_ids_argv_env_and_unknown_counts(self):
        self.prepare(opaque=True)
        unit, browser = self.start_pair()
        browser_result, unit_result = self.collect(browser), self.collect(unit)
        self.assertEqual(unit_result["status"], "PASS", unit_result)
        self.assertEqual(len(unit_result["runs"]), 2)
        self.assertNotEqual(unit_result["runs"][0]["run_id"], unit_result["runs"][1]["run_id"])
        self.assertEqual(unit_result["runs"][0]["counts"], {"passed": 1, "failed": 0, "skipped": 1})
        self.assertEqual(unit_result["counts"], {"passed": 2, "failed": 0, "skipped": 2})
        _, report, joined = self.emit_and_join(browser_result, unit_result)
        self.assertEqual({r["env_id"] for r in report["unitTests"]["runs"]}, {"isolated-stdlib-build", "isolated-second-suite"})
        self.assertTrue(joined["converged"])
        self.assertEqual(len(self.counter.read_text().splitlines()), 2)

    def test_browser_finished_while_unit_running_cannot_join_until_next_tick(self):
        self.prepare(unit_delay=2)
        unit, browser = self.start_pair()
        browser_result = self.collect(browser)
        self.assertIsNone(unit.poll())
        running = self.cli_json([sys.executable, str(SCRIPTS / "build_unit_test.py"), "status",
                                 "--root", str(self.root), "--version", self.version, "--build", self.build])
        self.assertEqual(running["status"], "RUNNING")
        before = self.baseline.read_bytes()
        emitted, report, _ = self.emit_and_join(browser_result, running, settle=False)
        self.assertFalse(emitted["report_ready"])
        self.assertFalse(emitted["freeze_ready"])
        self.assertEqual(report["summary"]["overallStatus"], "RUNNING")
        rejected = subprocess.run([sys.executable, str(SCRIPTS / "aiauto_test_join.py"), "settle",
                                   "--root", str(self.root), "--version", self.version, "--build", self.build,
                                   "--report", str(self.report_path())], capture_output=True, text=True, timeout=5)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertEqual(self.baseline.read_bytes(), before)
        completed = self.collect(unit)
        self.assertEqual(completed["status"], "PASS", completed)
        emitted, _, joined = self.emit_and_join(browser_result, completed)
        self.assertTrue(emitted["report_ready"])
        self.assertTrue(joined["converged"])
        self.assertEqual(self.release_state(), "pass")

    def test_same_build_does_not_execute_again_new_build_same_commit_runs_and_joins(self):
        self.prepare()
        unit, browser = self.start_pair()
        browser_result, first = self.collect(browser), self.collect(unit)
        self.assertEqual(first["status"], "PASS", first)
        self.emit_and_join(browser_result, first)
        self.assertEqual(len(self.counter.read_text().splitlines()), 1)
        unit, browser = self.start_pair()
        browser_result, repeated = self.collect(browser), self.collect(unit)
        self.assertTrue(repeated["reused"])
        self.assertEqual(first["runs"], repeated["runs"])
        self.emit_and_join(browser_result, repeated)
        self.assertEqual(len(self.counter.read_text().splitlines()), 1)
        self.build = "V1.0.0_build1002"
        self.plan["build"] = self.build
        data = json.loads(self.baseline.read_text())
        node = data["versions"][self.version]
        node["current_build"] = self.build
        node["builds"].append({"build": self.build, "push_commit": self.commit})
        self.baseline.write_text(json.dumps(data))
        self.unit_started.unlink()
        self.browser_started.unlink()
        # 同内容证据可复用，单测进程不会再启动；浏览器不应等待单测起跑文件。
        unit, browser = self.start_pair(wait_unit=False)
        browser_result, new = self.collect(browser), self.collect(unit)
        self.assertEqual(new["status"], "PASS", new)
        # 新 build 保留独立委派/manifest，但同版本同内容证据只可信复用，不重新启动测试进程。
        self.assertFalse(new["reused"])
        self.assertTrue(new["runs"][0]["reused"])
        self.assertEqual(new["runs"][0]["source_run_id"], first["runs"][0]["run_id"])
        self.assertNotEqual(first["runs"][0]["run_id"], new["runs"][0]["run_id"])
        _, report, joined = self.emit_and_join(browser_result, new)
        self.assertEqual(report["build"], self.build)
        self.assertTrue(joined["converged"])
        self.assertEqual(len(self.counter.read_text().splitlines()), 1)
        self.assertEqual(self.release_state(), "pass")


if __name__ == "__main__":
    unittest.main()
