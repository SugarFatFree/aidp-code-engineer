#!/usr/bin/env python3
"""两路测试终态汇合：失败登记、待核验不冻结、旧 build 不污染当前版。"""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import aiauto_test_join as join
from unit_report_merge import merge_unit_tests


class JoinTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.version, self.build, self.commit = 'V1.0.0', 'V1.0.0_build1001', 'a' * 40
        self.baseline = self.root / 'memory/.sprint-autopilot-baseline.json'
        self.baseline.parent.mkdir()
        self.baseline.write_text(json.dumps({'versions': {self.version: {
            'current_build': self.build, 'aiauto_tested_at': 'old',
            'builds': [{'build': self.build, 'push_commit': self.commit}]}}}))

    def payload(self, state='PASS', browser=True):
        run = {'run_id': 'run-1', 'status': state, 'command': ['python3', '-m', 'unittest'],
               'cwd': '.', 'env_id': 'unit', 'counts': {'passed': 1, 'failed': 0, 'skipped': 0},
               'failed_cases': [], 'primary_error': None, 'log': None}
        if state == 'FAIL':
            run.update(failed_cases=['test_calc'], primary_error='AssertionError: 1 != 2')
            run['counts'] = {'passed': 0, 'failed': 1, 'skipped': 0}
        unit = dict(schema=1, build=self.build, commit=self.commit, status=state, reason='',
                    runs=[run] if state in ('PASS', 'FAIL') else [], counts=run['counts'],
                    failed_cases=run['failed_cases'], primary_error=run['primary_error'], reused=False)
        scope = {'kind': 'version', 'version': self.version, 'build': self.build, 'manifest_hash': 'f' * 64,
                 'acceptance_baseline': {'path': 'docs/testing/V1.0.0/acceptance.json', 'sha256': 'e' * 64},
                 'acceptance_tests': ['test_sample.py'], 'dependencies': [], 'case_ids': ['TC-1']}
        unit.update(version=self.version, testScope=scope)
        result = dict(version=self.version, testScope=scope, build=self.build, commit=self.commit, unitTests=unit,
                      summary={'total': int(browser), 'pass': int(browser), 'fail': 0, 'block': 0,
                               'skip': 0, 'na': 0, 'passRate': 1 if browser else None})
        if browser:
            result['cases'] = [{'id': 'TC-1', 'title': '正式用例', 'result': 'pass'}]
        if not browser:
            result['browserTests'] = {'status': 'N/A', 'reason': '纯后端无浏览器适用面'}
        return result

    def settle(self, payload):
        rendered = merge_unit_tests(payload, payload['unitTests'], self.build, self.commit)
        return join.settle(self.root, self.version, self.build, rendered)

    def node(self):
        return json.loads(self.baseline.read_text())['versions'][self.version]

    def test_begin_prevents_old_timestamp_release_and_is_idempotent(self):
        join.begin(self.root, self.version, self.build, self.commit)
        self.assertNotIn('aiauto_tested_at', self.node())
        self.assertEqual(join.release_state(self.root, self.version), 'pending')
        self.settle(self.payload())
        join.begin(self.root, self.version, self.build, self.commit)
        self.assertEqual(join.release_state(self.root, self.version), 'pass')

    def test_ceremony_accepts_terminal_unverified_and_rejects_running(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('ceremony',
            Path(__file__).resolve().parents[1] / 'autopilot-ceremony-gate.py')
        gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate)
        path = self.root / 'docs/reports' / self.version / 'AI测试报告/data' / (self.build + '.js')
        path.parent.mkdir(parents=True)
        for state, valid in [('PASS', True), ('FAIL', True), ('UNVERIFIED', True), ('TIMEOUT', True), ('RUNNING', False)]:
            payload = self.payload(state)
            merged = merge_unit_tests(payload, payload['unitTests'], self.build, self.commit)
            path.write_text('window.__BUILDS__.push(' + json.dumps(merged) + ');')
            self.assertEqual(gate.check_unit_report(str(self.root), self.version, self.build, self.commit)[0], valid)
        self.assertFalse(gate.check_unit_report(str(self.root), self.version, self.build, 'b' * 40)[0])

    def test_standalone_target_run_cannot_settle_version_scope(self):
        payload = self.payload(browser=False)
        merged = merge_unit_tests(payload, payload['unitTests'], self.build, self.commit)
        with self.assertRaisesRegex(ValueError, '独立目标实测'):
            join.settle(self.root, self.version, self.build, merged, standalone=True)
        self.assertNotIn('test_join', json.loads(self.baseline.read_text())['versions'][self.version]['builds'][0])

    def test_legacy_or_other_version_report_cannot_settle(self):
        payload = self.payload()
        for mutate in (lambda p: (p.pop('testScope'), p['unitTests'].pop('testScope')),
                       lambda p: p.update(version='V9.9.9')):
            candidate = copy.deepcopy(payload)
            mutate(candidate)
            with self.assertRaises(ValueError):
                join.settle(self.root, self.version, self.build, candidate)

    def test_report_cases_must_equal_formal_version_case_ids(self):
        payload = self.payload()
        payload['cases'] = [{'id': 'TC-HISTORY', 'title': '历史', 'result': 'pass'}]
        with self.assertRaises(ValueError):
            self.settle(payload)

    def test_new_case_debt_after_report_requires_regeneration(self):
        data = json.loads(self.baseline.read_text())
        data['versions'][self.version]['case_ledger_pending'] = 1
        self.baseline.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, '欠账'):
            self.settle(self.payload())
        payload = self.payload()
        payload['summary']['pendingCases'] = 1
        out = self.settle(payload)
        self.assertFalse(out['converged'])
        self.assertNotIn('needs_human', self.node())

    def test_failed_suite_before_timeout_still_registers_bug(self):
        payload = self.payload('FAIL')
        payload['unitTests']['status'] = 'TIMEOUT'
        out = self.settle(payload)
        self.assertEqual(out['overall_status'], 'FAIL')
        self.assertEqual(len(out['bug_ids']), 1)
        self.assertTrue(self.node()['auto_fixable_pending'])
        self.assertNotIn('needs_human', self.node())

    def browser_failure(self, category=None):
        payload = self.payload()
        payload['summary'].update({'pass': 0, 'fail': 1, 'passRate': 0})
        payload['defects'] = [{'id': 'BUG-1', 'status': '待修复', 'title': '接口500'}]
        if category:
            item = {'refs': ['defect:BUG-1', 'summary:fail'], 'category': category,
                    'reason': '接口响应与已确认契约不符'}
            if category == 'clarification':
                item.update(question='是否允许该入口？', affected_cases=['TC-1'], interim_verdict='BLOCK')
            payload['failureTriage'] = {'schema': 1, 'build': self.build, 'commit': self.commit,
                                        'items': [item]}
        return payload

    def test_browser_code_failure_sets_auto_fixable_and_is_idempotent(self):
        data = json.loads(self.baseline.read_text())
        data['versions'][self.version]['auto_fixable_pending'] = False
        self.baseline.write_text(json.dumps(data))
        payload = self.browser_failure('auto_fixable')
        first = self.settle(payload)
        self.assertEqual(first['overall_status'], 'FAIL')
        self.assertTrue(self.node()['auto_fixable_pending'])
        before = self.baseline.read_bytes()
        self.assertEqual(self.settle(payload), first)
        self.assertEqual(self.baseline.read_bytes(), before)

    def test_success_clears_retest_cycle_fields(self):
        data = json.loads(self.baseline.read_text())
        data['versions'][self.version].update(auto_retest_streak=3,
            auto_fix_in_progress_since='yesterday', auto_fixable_pending=True)
        self.baseline.write_text(json.dumps(data))
        self.settle(self.payload())
        self.assertNotIn('auto_retest_streak', self.node())
        self.assertNotIn('auto_fix_in_progress_since', self.node())

    def test_browser_missing_triage_is_explicitly_pending(self):
        result = self.settle(self.browser_failure())
        self.assertEqual(result.get('triage_status'), 'PENDING')
        self.assertEqual(result.get('next_action'), 'classify')
        self.assertFalse(result['converged'])
        self.assertEqual(join.release_state(self.root, self.version), 'pending')
        self.assertTrue(self.node()['triage_pending'])

    def test_clarification_and_environment_do_not_create_auto_fix_bug(self):
        for category in ('clarification', 'environment'):
            with self.subTest(category=category):
                result = self.settle(self.browser_failure(category))
                node = self.node()
                self.assertFalse(node.get('auto_fixable_pending', False))
                self.assertEqual(result['bug_ids'], [])
                key = 'pending_clarifications' if category == 'clarification' else 'environment_unverified'
                self.assertEqual(len(node.get(key, [])), 1)
                self.settle(self.browser_failure(category))
                self.assertEqual(len(self.node()[key]), 1)

    def test_triage_preserves_other_build_and_manual_clarifications(self):
        data = json.loads(self.baseline.read_text())
        history = [{'source': 'aiauto_test_join', 'raised_build': 'old-build', 'question': '旧问题'},
                   {'raised_build': self.build, 'question': '人工已有问题'}]
        data['versions'][self.version]['pending_clarifications'] = history
        self.baseline.write_text(json.dumps(data))
        payload = self.browser_failure('clarification')
        self.settle(payload)
        self.settle(payload)
        self.assertEqual(self.node()['pending_clarifications'][:2], history)
        self.assertEqual(len(self.node()['pending_clarifications']), 3)

    def test_unit_failure_still_registers_when_browser_triage_is_pending(self):
        payload = self.browser_failure()
        payload['unitTests'] = self.payload('FAIL')['unitTests']
        result = self.settle(payload)
        self.assertEqual(result['triage_status'], 'PENDING')
        self.assertEqual(len(result['bug_ids']), 1)
        self.assertTrue(self.node()['auto_fixable_pending'])
        self.assertEqual(self.node()['aiauto_test_unconverged_streak'], 1)
        payload['failureTriage'] = self.browser_failure('auto_fixable')['failureTriage']
        completed = self.settle(payload)
        self.assertEqual(completed['bug_ids'], result['bug_ids'])
        self.assertEqual(self.node()['aiauto_test_unconverged_streak'], 1)

    def test_successor_build_does_not_inherit_old_triage_or_rearm_from_history(self):
        old_payload = self.browser_failure('auto_fixable')
        old_build = self.build
        self.settle(old_payload)
        data = json.loads(self.baseline.read_text())
        self.build = 'V1.0.0_build1002'
        node = data['versions'][self.version]
        node['current_build'] = self.build
        node['builds'].append({'build': self.build, 'push_commit': self.commit})
        self.baseline.write_text(json.dumps(data))
        result = self.settle(self.browser_failure('environment'))
        self.assertFalse(self.node()['auto_fixable_pending'])
        self.assertEqual(result['next_action'], 'verify')
        self.assertEqual(self.node()['environment_unverified'][0]['raised_build'], self.build)
        before = copy.deepcopy(self.node())
        report = merge_unit_tests(old_payload, old_payload['unitTests'], old_build, self.commit)
        join.settle(self.root, self.version, old_build, report)
        self.assertEqual(self.node(), before)

    def test_missing_current_classification_does_not_inherit_stale_afp(self):
        data = json.loads(self.baseline.read_text())
        data['versions'][self.version].update(auto_fixable_pending=True, auto_retest_streak=2)
        self.baseline.write_text(json.dumps(data))
        result = self.settle(self.browser_failure())
        self.assertEqual(result['next_action'], 'classify')
        self.assertFalse(self.node()['auto_fixable_pending'])
        self.assertEqual(self.node()['auto_retest_streak'], 2)

    def test_replay_does_not_rearm_consumed_auto_fix(self):
        payload = self.browser_failure('auto_fixable')
        self.settle(payload)
        data = json.loads(self.baseline.read_text())
        node = data['versions'][self.version]
        node.update(auto_fixable_pending=False, auto_retest_streak=1, auto_fix_in_progress_since='now')
        self.baseline.write_text(json.dumps(data))
        self.settle(payload)
        self.assertFalse(self.node()['auto_fixable_pending'])
        self.assertEqual(self.node()['auto_retest_streak'], 1)
        self.assertEqual(self.node()['auto_fix_in_progress_since'], 'now')

    def test_only_current_success_can_clear_retest_budget(self):
        for state in ('PASS', 'FAIL', 'UNVERIFIED', 'TIMEOUT'):
            with self.subTest(state=state):
                data = json.loads(self.baseline.read_text())
                node = data['versions'][self.version]
                node.update(current_build='new-build', auto_retest_streak=2,
                            auto_fix_in_progress_since='current-fix', auto_fixable_pending=True)
                node['builds'][0].pop('test_join', None)
                self.baseline.write_text(json.dumps(data))
                before = copy.deepcopy(node)
                self.settle(self.payload(state))
                after = self.node()
                self.assertEqual({k: v for k, v in after.items() if k != 'builds'},
                                 {k: v for k, v in before.items() if k != 'builds'})

    def test_failure_or_unverified_retains_retest_budget(self):
        for state in ('FAIL', 'UNVERIFIED', 'TIMEOUT'):
            data = json.loads(self.baseline.read_text())
            data['versions'][self.version].update(auto_retest_streak=2, auto_fix_in_progress_since='active')
            self.baseline.write_text(json.dumps(data))
            self.settle(self.payload(state))
            self.assertEqual(self.node()['auto_retest_streak'], 2)
            self.assertEqual(self.node()['auto_fix_in_progress_since'], 'active')

    def test_triage_identity_and_explicit_input_must_match_report(self):
        for field in ('build', 'commit'):
            payload = self.browser_failure('auto_fixable')
            payload['failureTriage'][field] = 'other'
            before = self.baseline.read_bytes()
            with self.assertRaisesRegex(ValueError, 'failureTriage'):
                self.settle(payload)
            self.assertEqual(self.baseline.read_bytes(), before)
        payload = self.browser_failure('auto_fixable')
        report = merge_unit_tests(payload, payload['unitTests'], self.build, self.commit)
        other = copy.deepcopy(report['failureTriage'])
        other['items'][0]['category'] = 'environment'
        with self.assertRaisesRegex(ValueError, '--triage'):
            join.settle(self.root, self.version, self.build, report, triage=other)

    def test_finalized_build_rejects_changed_classification(self):
        self.settle(self.browser_failure('auto_fixable'))
        data = json.loads(self.baseline.read_text())
        data['versions'][self.version]['builds'][0]['ai_report_finalized'] = True
        self.baseline.write_text(json.dumps(data))
        before = self.baseline.read_bytes()
        with self.assertRaisesRegex(ValueError, '定稿'):
            self.settle(self.browser_failure('environment'))
        self.assertEqual(self.baseline.read_bytes(), before)

    def test_other_open_bug_or_case_debt_cannot_clear_budget_or_pass(self):
        docs = self.root / 'docs/testing' / self.version / '测试执行'
        docs.mkdir(parents=True)
        (docs / 'bugs.md').write_text('| BUG-OLD | 待修复 | 他人未关闭缺陷 |')
        data = json.loads(self.baseline.read_text())
        data['versions'][self.version].update(case_ledger_pending=1, auto_retest_streak=2,
            auto_fix_in_progress_since='active')
        self.baseline.write_text(json.dumps(data))
        payload = self.payload()
        payload['summary'].update(pendingCases=1, openBugs=1)
        out = self.settle(payload)
        self.assertFalse(out['converged'])
        self.assertEqual(out['triage_status'], 'PENDING')
        self.assertEqual(self.node()['auto_retest_streak'], 2)
        self.assertEqual(self.node()['auto_fix_in_progress_since'], 'active')
        self.assertNotIn('aiauto_tested_at', self.node())

    def test_pass_sets_verified_timestamp(self):
        result = self.settle(self.payload())
        self.assertTrue(result['converged'])
        self.assertEqual(self.node()['aiauto_test_result']['overall_status'], 'PASS')
        self.assertNotEqual(self.node()['aiauto_tested_at'], 'old')

    def test_unit_failure_is_bug_and_not_browser_pass(self):
        payload = self.payload('FAIL')
        first = self.settle(payload)
        again = self.settle(payload)
        self.assertFalse(first['converged'])
        self.assertEqual(first['bug_ids'], again['bug_ids'])
        self.assertEqual(len(first['bug_ids']), 1)
        self.assertEqual(self.node()['aiauto_test_unconverged_streak'], 1)
        self.assertTrue(self.node()['auto_fixable_pending'])
        documents = list((self.root / 'docs/bugfix').rglob('*.md'))
        self.assertEqual(len(documents), 1)
        self.assertIn('test_calc', documents[0].read_text())
        self.assertIn('待修复', documents[0].read_text())

    def test_unverified_and_timeout_do_not_freeze_or_claim_pass(self):
        for state in ('UNVERIFIED', 'TIMEOUT'):
            with self.subTest(state=state):
                self.settle(self.payload(state))
                node = self.node()
                self.assertNotIn('aiauto_tested_at', node)
                self.assertNotIn('needs_human', node)
                self.assertEqual(node.get('aiauto_test_unconverged_streak', 0), 0)
                self.assertTrue(node['aiauto_test_result']['unverified'])
                self.assertEqual(join.release_state(self.root, self.version), 'pending')

    def test_backend_only_has_real_unit_conclusion(self):
        out = self.settle(self.payload(browser=False))
        self.assertTrue(out['converged'])
        self.assertEqual(self.node()['aiauto_test_result']['browser_status'], 'N/A')

    def test_running_never_writes_completion(self):
        before = self.baseline.read_bytes()
        with self.assertRaises(ValueError):
            self.settle(self.payload('RUNNING'))
        self.assertEqual(before, self.baseline.read_bytes())

    def test_mismatched_build_or_commit_rejected(self):
        for key in ('build', 'commit'):
            payload = self.payload()
            payload[key] = 'wrong'
            with self.assertRaises(ValueError):
                self.settle(payload)

    def test_previous_build_does_not_overwrite_current_status(self):
        data = json.loads(self.baseline.read_text())
        node = data['versions'][self.version]
        node['current_build'] = 'V1.0.0_build1002'
        node['aiauto_test_result'] = {'build': 'V1.0.0_build1002', 'overall_status': 'PASS'}
        self.baseline.write_text(json.dumps(data))
        self.settle(self.payload('FAIL'))
        self.assertEqual(self.node()['aiauto_test_result']['overall_status'], 'PASS')
        self.assertEqual(self.node()['aiauto_tested_at'], 'old')

    def test_failure_not_masked_by_unit_unverified(self):
        payload = self.browser_failure('auto_fixable')
        payload['unitTests'] = self.payload('UNVERIFIED')['unitTests']
        self.settle(payload)
        self.assertEqual(self.node()['aiauto_test_result']['overall_status'], 'FAIL')
        self.assertEqual(join.release_state(self.root, self.version), 'failed')


if __name__ == '__main__':
    unittest.main()
