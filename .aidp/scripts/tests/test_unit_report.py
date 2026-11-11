#!/usr/bin/env python3
"""全量单测结果经真实 emit / schema / JS 消费链的定向回归。"""
import importlib.util
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))
import unit_report_merge as merge

spec = importlib.util.spec_from_file_location("unit_report_emitter", SCRIPTS / "emit-report.py")
emitter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(emitter)
BUILD = "V0.1.0_build123"
COMMIT = "a" * 40


def unit(status="PASS"):
    counts = {"passed": 2 if status == "PASS" else 1, "failed": int(status == "FAIL"), "skipped": 0}
    failed = ["test_failure<script>"] if status == "FAIL" else []
    error = "AssertionError: <expected>" if status == "FAIL" else None
    scope = {"kind": "version", "version": "V0.1.0", "build": BUILD, "manifest_hash": "d" * 64,
             "acceptance_baseline": {"path": "docs/testing/V0.1.0/acceptance.json", "sha256": "c" * 64},
             "acceptance_tests": ["test_sample.py"], "dependencies": [], "case_ids": ["TC-1"]}
    return {"schema": 1, "version": "V0.1.0", "testScope": scope, "build": BUILD, "commit": COMMIT, "status": status,
            "reason": "真实全量命令", "runs": [{"run_id": "run-123", "status": status,
                "command": ["python3", "-m", "unittest", "discover"], "cwd": "code/backend", "env_id": "local",
                "counts": counts, "failed_cases": failed, "primary_error": error, "log": "logs/unit.log"}],
            "counts": counts, "failed_cases": failed, "primary_error": error, "reused": False}


def browser_payload():
    return {"build": BUILD, "version": "V0.1.0", "buildNo": 123, "commit": COMMIT,
            "summary": {"total": 1, "pass": 1, "fail": 0, "block": 0, "skip": 0, "na": 0, "passRate": 1},
            "cases": [{"id": "TC-1", "title": "浏览器通过", "result": "pass"}]}


class UnitReportContractTests(unittest.TestCase):
    def test_browser_pass_unit_failure_is_failure_without_changing_cases(self):
        source = browser_payload()
        report = merge.merge_unit_tests(source, unit("FAIL"), BUILD, COMMIT)
        self.assertEqual(report["summary"]["overallStatus"], "FAIL")
        self.assertEqual(report["summary"]["passRate"], 1)
        self.assertEqual(report["cases"], source["cases"])
        self.assertTrue(merge.report_ready(report))
        self.assertTrue(merge.finalize_ready(report))
        self.assertFalse(merge.success_ready(report))
        self.assertEqual(emitter.validate_payload("test", report), [])

    def test_unverified_timeout_are_reportable_but_never_success_or_frozen(self):
        for status in ("UNVERIFIED", "TIMEOUT"):
            with self.subTest(status=status):
                report = merge.merge_unit_tests(browser_payload(), unit(status), BUILD, COMMIT)
                self.assertEqual(report["summary"]["overallStatus"], status)
                self.assertTrue(merge.report_ready(report))
                self.assertFalse(merge.finalize_ready(report))
                self.assertFalse(merge.success_ready(report))

    def test_running_cannot_finalize(self):
        report = merge.merge_unit_tests(browser_payload(), unit("RUNNING"), BUILD, COMMIT)
        self.assertFalse(merge.report_ready(report))
        self.assertFalse(merge.finalize_ready(report))

    def test_wrong_build_or_commit_rejected(self):
        for field in ("build", "commit"):
            result = unit()
            result[field] = "other"
            with self.assertRaisesRegex(ValueError, field):
                merge.merge_unit_tests(browser_payload(), result, BUILD, COMMIT)

    def test_pass_requires_real_completed_run(self):
        for runs in ([], unit("FAIL")["runs"], unit("RUNNING")["runs"]):
            result = unit()
            result["runs"] = runs
            self.assertTrue(merge.validate_unit_tests(result, BUILD, COMMIT))

    def test_missing_counts_remain_unknown(self):
        result = unit()
        result["counts"] = None
        result["runs"][0]["counts"] = {"passed": None, "failed": None, "skipped": None}
        report = merge.merge_unit_tests(browser_payload(), result, BUILD, COMMIT)
        self.assertIsNone(report["unitTests"]["counts"])
        self.assertEqual(emitter.validate_payload("test", report), [])

    def test_schema_refuses_false_green_and_malformed_result(self):
        report = merge.merge_unit_tests(browser_payload(), unit("FAIL"), BUILD, COMMIT)
        report["summary"]["overallStatus"] = "PASS"
        self.assertTrue(emitter.validate_payload("test", report))
        report["unitTests"]["commit"] = "other"
        self.assertTrue(emitter.validate_payload("test", report))
        report["unitTests"] = []
        self.assertTrue(emitter.validate_payload("test", report))

    def test_failed_suite_before_timeout_remains_failure_without_freezing(self):
        for status in ("TIMEOUT", "UNVERIFIED"):
            result = unit(status)
            failed = unit("FAIL")["runs"][0]
            failed["run_id"] = "earlier-failed-run"
            result["runs"].insert(0, failed)
            report = merge.merge_unit_tests(browser_payload(), result, BUILD, COMMIT)
            self.assertEqual(report["summary"]["overallStatus"], "FAIL")
            self.assertEqual(report["unitTests"]["status"], status)
            self.assertTrue(merge.report_ready(report))
            self.assertFalse(merge.success_ready(report))
            self.assertFalse(merge.finalize_ready(report))
            self.assertEqual(emitter.validate_payload("test", report), [])

    def test_browser_terminal_status_and_pending_prevent_false_completion(self):
        for status in ("UNVERIFIED", "TIMEOUT", "RUNNING"):
            source = browser_payload()
            source["browserTests"] = {"status": status, "reason": "浏览器前置条件未满足"}
            for unit_status in ("PASS", "FAIL"):
                with self.subTest(browser=status, unit=unit_status):
                    report = merge.merge_unit_tests(source, unit(unit_status), BUILD, COMMIT)
                    self.assertFalse(merge.success_ready(report))
                    self.assertEqual(merge.report_ready(report), status != "RUNNING")
                    self.assertFalse(merge.finalize_ready(report))
                    self.assertEqual(emitter.validate_payload("test", report), [])
        source = browser_payload()
        source["summary"].update(passRate=0, **{"pass": 0, "fail": 1})
        source["cases"][0]["result"] = "fail"
        report = merge.merge_unit_tests(source, unit("TIMEOUT"), BUILD, COMMIT)
        self.assertEqual(report["summary"]["overallStatus"], "FAIL")
        self.assertTrue(merge.report_ready(report))
        self.assertFalse(merge.finalize_ready(report))
        self.assertEqual(emitter.validate_payload("test", report), [])

    def test_pending_browser_prevents_report_completion_even_when_unit_failed(self):
        source = browser_payload()
        source["summary"]["pendingBrowserTest"] = True
        report = merge.merge_unit_tests(source, unit("FAIL"), BUILD, COMMIT)
        self.assertFalse(merge.report_ready(report))
        self.assertFalse(merge.finalize_ready(report))

    def test_missing_or_partial_triage_cannot_freeze_browser_failure(self):
        source = browser_payload()
        source['summary'].update({'pass': 0, 'fail': 1, 'passRate': 0})
        source['cases'][0]['result'] = 'fail'
        source['defects'] = [{'id': 'BUG-1', 'status': '待修复', 'title': '接口500'}]
        report = merge.merge_unit_tests(source, unit(), BUILD, COMMIT)
        self.assertTrue(merge.report_ready(report))
        self.assertFalse(merge.finalize_ready(report))
        self.assertEqual(report['summary']['triageMissing'], ['case:TC-1', 'defect:BUG-1'])
        source['failureTriage'] = {'schema': 1, 'build': BUILD, 'commit': COMMIT, 'items': [
            {'refs': ['defect:BUG-1'], 'category': 'auto_fixable', 'reason': '已定位空指针'}]}
        report = merge.merge_unit_tests(source, unit(), BUILD, COMMIT)
        self.assertFalse(merge.finalize_ready(report))
        source['failureTriage']['items'][0]['refs'].append('case:TC-1')
        report = merge.merge_unit_tests(source, unit(), BUILD, COMMIT)
        self.assertTrue(merge.finalize_ready(report))
        source['failureTriage']['items'][0]['category'] = 'environment'
        report = merge.merge_unit_tests(source, unit(), BUILD, COMMIT)
        self.assertFalse(merge.finalize_ready(report))
        self.assertFalse(merge.success_ready(report))

    def test_triage_invalid_or_duplicate_references_are_rejected(self):
        source = browser_payload()
        source['summary'].update({'pass': 0, 'fail': 1, 'passRate': 0})
        source['cases'][0]['result'] = 'fail'
        for refs in (['case:other'], ['case:TC-1', 'case:TC-1']):
            source['failureTriage'] = {'schema': 1, 'build': BUILD, 'commit': COMMIT, 'items': [
                {'refs': refs, 'category': 'auto_fixable', 'reason': '已定位空指针'}]}
            with self.assertRaisesRegex(ValueError, '引用'):
                merge.merge_unit_tests(source, unit(), BUILD, COMMIT)

    def test_legacy_report_is_compatible(self):
        report = browser_payload()
        self.assertEqual(emitter.validate_payload("test", report), [])
        self.assertEqual(merge.overall_status(report), "PASS")


class UnitReportEmitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="aidp-unit-report-")
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def emit(self, payload, result=None, extra=(), kind="test", explicit=True):
        draft = self.root / (kind + "-draft.json")
        draft.write_text(json.dumps(payload), encoding="utf-8")
        result_path = self.root / "unit-result.json"
        if result is not None:
            result_path.write_text(json.dumps(result), encoding="utf-8")
        args = [sys.executable, str(SCRIPTS / "emit-report.py"), "--kind", kind,
                "--version", "V0.1.0", "--build", BUILD, "--data", str(draft),
                "--repo-root", str(self.root), "--templates-root", str(ROOT / ".aidp/templates/reports"),
                "--record-baseline", "0", "--keep-input", "--json"]
        if explicit:
            args += ["--unit-result", str(result_path), "--commit", COMMIT]
        proc = subprocess.run(args + list(extra), text=True, capture_output=True)
        return proc, json.loads(proc.stdout)

    def payload_path(self, kind="AI测试报告"):
        return self.root / "docs/reports/V0.1.0" / kind / "data" / (BUILD + ".js")

    def test_cli_merge_backend_only_and_smoke(self):
        payload = {"build": BUILD, "version": "V0.1.0", "commit": COMMIT}
        proc, result = self.emit(payload, unit(), ["--browser-na-reason", "纯后端无浏览器适用面"])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        report = merge.read_payload(self.payload_path())
        self.assertEqual(report["summary"]["overallStatus"], "PASS")
        self.assertEqual(report["summary"]["browserStatus"], "N/A")
        self.assertEqual(report["cases"], [])
        self.assertTrue(result["success_ready"])
        smoke = subprocess.run(["node", str(SCRIPTS / "report_render_smoke.js"),
                                str(self.payload_path().parent.parent), BUILD], text=True, capture_output=True)
        self.assertEqual(smoke.returncode, 0, smoke.stdout + smoke.stderr)

    def test_cli_explicit_missing_result_is_unverified(self):
        proc, result = self.emit(browser_payload())
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(result["overallStatus"], "UNVERIFIED")
        self.assertTrue(result["report_ready"])
        self.assertFalse(result["freeze_ready"])

    def test_cli_legacy_does_not_invent_unit_result(self):
        proc, _ = self.emit(browser_payload(), explicit=False)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertNotIn("unitTests", merge.read_payload(self.payload_path()))

    def test_cli_rejects_pollution_even_with_schema_escape(self):
        result = unit()
        result["build"] = "V0.1.0_build999"
        proc, out = self.emit(browser_payload(), result, ["--allow-schema-warn"])
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("build", out["error"])
        self.assertFalse(self.payload_path().exists())

    def test_baseline_commit_is_authoritative(self):
        baseline = self.root / "baseline.json"
        baseline.write_text(json.dumps({"versions": {"V0.1.0": {"builds": [
            {"build": BUILD, "commit": "b" * 40}]}}}), encoding="utf-8")
        proc, out = self.emit(browser_payload(), unit(), ["--baseline", str(baseline)])
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("baseline build.commit", out["error"])

    def test_exec_derives_combined_summary_and_is_not_done(self):
        proc, _ = self.emit(browser_payload(), unit("FAIL"))
        self.assertEqual(proc.returncode, 0, proc.stdout)
        payload = {"build": BUILD, "version": "V0.1.0", "overview": {"statusKind": "done", "testPassRate": 1},
                   "steps": [], "features": [], "testSummary": {"overallStatus": "PASS"}}
        proc, _ = self.emit(payload, kind="exec", explicit=False)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        report = merge.read_payload(self.payload_path("AI执行报告"))
        self.assertEqual(report["testSummary"]["overallStatus"], "FAIL")
        self.assertEqual(report["unitTests"]["status"], "FAIL")
        self.assertEqual(report["overview"]["statusKind"], "fail")

    def test_pending_obligations_and_runtime_failures_affect_report(self):
        baseline = self.root / "memory/.sprint-autopilot-baseline.json"
        baseline.parent.mkdir(parents=True)
        state = {"versions": {"V0.1.0": {"current_build": BUILD, "case_ledger_pending": 2,
                    "builds": [{"build": BUILD, "push_commit": COMMIT}]}}}
        baseline.write_text(json.dumps(state), encoding="utf-8")
        proc, out = self.emit(browser_payload(), unit())
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(out["overallStatus"], "UNVERIFIED")
        self.assertEqual(merge.read_payload(self.payload_path())["summary"]["pendingCases"], 2)
        state["versions"]["V0.1.0"]["current_build"] = "new-build"
        baseline.write_text(json.dumps(state), encoding="utf-8")
        proc, out = self.emit(browser_payload(), unit())
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(out["overallStatus"], "PASS", "旧 build 不消费新 build 欠账")
        source = browser_payload()
        source["runtimeErrors"] = [{"id": "R-1", "desc": "真实运行时异常"}]
        proc, out = self.emit(source, unit())
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(out["overallStatus"], "FAIL")

    def test_phase3_convergence_fence_consumes_real_joint_report(self):
        baseline = self.root / "memory/.sprint-autopilot-baseline.json"
        baseline.parent.mkdir(parents=True)
        baseline.write_text(json.dumps({"versions": {"V0.1.0": {"current_build": BUILD,
            "builds": [{"build": BUILD, "push_commit": COMMIT}]}}}), encoding="utf-8")
        proc, _ = self.emit(browser_payload(), unit("FAIL"))
        self.assertEqual(proc.returncode, 0, proc.stdout)
        raw = (ROOT / ".aidp/flows/sprint-aiauto-test/phase-3-3.md").read_text(encoding="utf-8")
        block = re.search(r'> ```bash\n(.*?)> ```', raw, re.S).group(1)
        block = "\n".join(line[2:] if line.startswith("> ") else line for line in block.splitlines())
        block = "\n".join(line for line in block.splitlines() if not line.startswith('eval "$('))
        block = block.replace("{{AIDP_HOME}}", str(ROOT / ".aidp"))
        result = subprocess.run(["bash", "-c", block], cwd=self.root, text=True, capture_output=True,
            env={**os.environ, "TARGET_VERSION": "V0.1.0", "BUILD": BUILD, "REPORT_ENABLED": "1"})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        joined = json.loads((self.root / "memory/.aidp" / ("test-join-" + BUILD + ".json")).read_text())
        self.assertFalse(joined["converged"])
        self.assertEqual(joined["overall_status"], "FAIL")
        self.assertTrue(joined["bug_ids"])

    def test_phase3_notification_and_standalone_final_fences(self):
        directory = self.root / 'memory/.aidp/build-unit/V0.1.0' / BUILD
        directory.mkdir(parents=True)
        (directory / 'plan.json').write_text(json.dumps({'version': 'V0.1.0', 'build': BUILD,
            'commit': COMMIT, 'standalone': True, 'deployment': {'verified': True,
            'commit': COMMIT, 'evidence': 'verified deployment endpoint'}}))
        for status in ("PASS", "TIMEOUT", "RUNNING"):
            proc, _ = self.emit(browser_payload(), unit(status))
            self.assertEqual(proc.returncode, 0, proc.stdout)
            for name, marker, args in (
                ("phase-3-3b.md", "JOINT_CARDS", [str(self.payload_path()), "V0.1.0", BUILD, "0"]),
                ("phase-3-5.md", "JOINT_FINAL", ["V0.1.0", BUILD, "0", "0"])):
                with self.subTest(status=status, flow=name):
                    raw = (ROOT / ".aidp/flows/sprint-aiauto-test" / name).read_text(encoding="utf-8")
                    code = raw.split("<<'" + marker + "'\n", 1)[1].split("\n" + marker, 1)[0]
                    code = code.replace("{{AIDP_HOME}}", str(ROOT / ".aidp"))
                    result = subprocess.run([sys.executable, "-c", code] + args,
                        cwd=self.root, text=True, capture_output=True)
                    self.assertEqual(result.returncode == 0, status != "RUNNING", result.stdout + result.stderr)
            self.assertFalse((self.root / "memory/.sprint-autopilot-baseline.json").exists())

    def test_browser_triage_flows_from_real_phase3_fence_through_exec(self):
        baseline = self.root / 'memory/.sprint-autopilot-baseline.json'
        baseline.parent.mkdir(parents=True)
        baseline.write_text(json.dumps({'versions': {'V0.1.0': {'current_build': BUILD,
            'auto_fixable_pending': False, 'auto_retest_streak': 2,
            'builds': [{'build': BUILD, 'push_commit': COMMIT}]}}}))
        source = browser_payload()
        source['summary'].update({'pass': 0, 'fail': 1, 'passRate': 0})
        source['cases'][0]['result'] = 'fail'
        source['defects'] = [{'id': 'BUG-1', 'status': '待修复', 'title': '接口500'}]
        proc, out = self.emit(source, unit())
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(out['triage_status'], 'PENDING')
        self.assertFalse(out['freeze_ready'])
        command = [sys.executable, str(SCRIPTS / 'aiauto_test_join.py'), 'settle',
            '--root', str(self.root), '--version', 'V0.1.0', '--build', BUILD,
            '--report', str(self.payload_path())]
        proc = subprocess.run(command, text=True, capture_output=True)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertEqual(json.loads(proc.stdout)['next_action'], 'classify')
        self.assertIn('分类未完成', proc.stderr)
        for name, marker, args in (
            ('phase-3-3b.md', 'JOINT_CARDS', [str(self.payload_path()), 'V0.1.0', BUILD, '0']),
            ('phase-3-5.md', 'JOINT_FINAL', ['V0.1.0', BUILD, '1', '0'])):
            raw = (ROOT / '.aidp/flows/sprint-aiauto-test' / name).read_text()
            code = raw.split("<<'" + marker + "'\n", 1)[1].split('\n' + marker, 1)[0]
            code = code.replace('{{AIDP_HOME}}', str(ROOT / '.aidp'))
            blocked = subprocess.run([sys.executable, '-c', code] + args, cwd=self.root,
                                     text=True, capture_output=True)
            self.assertNotEqual(blocked.returncode, 0)
            self.assertIn('待分流', blocked.stderr)
        triage = {'schema': 1, 'build': BUILD, 'commit': COMMIT, 'items': [
            {'refs': ['case:TC-1', 'defect:BUG-1'], 'category': 'auto_fixable', 'reason': '已定位空指针'}]}
        triage_path = self.root / 'memory/.aidp' / ('test-triage-' + BUILD + '.json')
        triage_path.parent.mkdir(parents=True, exist_ok=True)
        triage_path.write_text(json.dumps(triage))
        raw = (ROOT / '.aidp/flows/sprint-aiauto-test/phase-3-3.md').read_text()
        block = re.search(r'> ```bash\n(.*?)> ```', raw, re.S).group(1)
        block = '\n'.join(line[2:] if line.startswith('> ') else line for line in block.splitlines())
        block = '\n'.join(line for line in block.splitlines() if not line.startswith('eval "$('))
        block = block.replace('{{AIDP_HOME}}', str(ROOT / '.aidp'))
        proc = subprocess.run(['bash', '-c', block], cwd=self.root, text=True, capture_output=True,
            env={**os.environ, 'TARGET_VERSION': 'V0.1.0', 'BUILD': BUILD, 'REPORT_ENABLED': '1'})
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        node = json.loads(baseline.read_text())['versions']['V0.1.0']
        self.assertTrue(node['auto_fixable_pending'])
        self.assertEqual(node['auto_retest_streak'], 2)
        self.assertEqual(node['aiauto_test_unconverged_streak'], 1)
        self.assertEqual(merge.read_payload(self.payload_path())['failureTriage'], triage)
        proc = subprocess.run(command + ['--triage', str(triage_path)], text=True, capture_output=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(json.loads(proc.stdout)['next_action'], 'bugfix')
        proc, out = self.emit({'build': BUILD, 'version': 'V0.1.0', 'overview': {'statusKind': 'done'},
                              'steps': [], 'features': []}, kind='exec', explicit=False)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        executed = merge.read_payload(self.payload_path('AI执行报告'))
        self.assertEqual(executed['failureTriage'], triage)
        self.assertEqual(executed['testSummary']['triageStatus'], 'COMPLETE')
        self.assertEqual(executed['testSummary']['overallStatus'], 'FAIL')
        # 已冻结报告重复恢复同一分类：不再 emit，不重置已消费的 AFP。
        data = json.loads(baseline.read_text())
        data['versions']['V0.1.0']['auto_fixable_pending'] = False
        data['versions']['V0.1.0']['builds'][0]['ai_report_finalized'] = True
        baseline.write_text(json.dumps(data))
        before = self.payload_path().read_bytes()
        repeated = subprocess.run(['bash', '-c', block], cwd=self.root, text=True, capture_output=True,
            env={**os.environ, 'TARGET_VERSION': 'V0.1.0', 'BUILD': BUILD, 'REPORT_ENABLED': '1'})
        self.assertEqual(repeated.returncode, 0, repeated.stdout + repeated.stderr)
        self.assertEqual(self.payload_path().read_bytes(), before)
        self.assertFalse(json.loads(baseline.read_text())['versions']['V0.1.0']['auto_fixable_pending'])

    def test_triage_cli_rejects_cross_build_and_cannot_use_schema_escape(self):
        path = self.root / 'triage.json'
        path.write_text(json.dumps({'schema': 1, 'build': 'old-build', 'commit': COMMIT, 'items': []}))
        proc, out = self.emit(browser_payload(), unit(), ['--failure-triage', str(path), '--allow-schema-warn'])
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn('failureTriage.build', out['error'])
        self.assertFalse(self.payload_path().exists())

    def test_js_consumer_rejects_false_green_summary(self):
        proc, _ = self.emit(browser_payload(), unit("FAIL"))
        self.assertEqual(proc.returncode, 0, proc.stdout)
        report = merge.read_payload(self.payload_path())
        report["summary"]["overallStatus"] = "PASS"
        emitter.write_data_file(str(self.payload_path().parent.parent), BUILD, report, "__BUILDS__")
        smoke = subprocess.run(["node", str(SCRIPTS / "report_render_smoke.js"),
                                str(self.payload_path().parent.parent), BUILD], text=True, capture_output=True)
        self.assertNotEqual(smoke.returncode, 0)
        self.assertIn("unitTests", smoke.stdout)


if __name__ == "__main__":
    unittest.main()
