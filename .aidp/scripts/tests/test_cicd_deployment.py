#!/usr/bin/env python3
"""CI/CD 主部署出口：真实命令提供方、baseline 与独立流程围栏，全部离线。"""
import contextlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[3]
SCRIPTS = REPO / '.aidp/scripts'
FLOW = REPO / '.aidp/flows/sprint-autopilot'
sys.path.insert(0, str(SCRIPTS))
import cicd_providers as providers
import cicd_watch as watch

SHA = '0123456789abcdef0123456789abcdef01234567'
VERSION = 'V0.1.0'
BUILD = VERSION + '_build1001'


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'memory/.aidp').mkdir(parents=True)
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        self.baseline = self.root / 'memory/.sprint-autopilot-baseline.json'
        self.baseline.write_text(json.dumps({'autopilot': {'wake_source_this_tick': 'loop'}, 'versions': {
            VERSION: {'current_build': BUILD, 'builds': [{'build': BUILD, 'push_commit': SHA,
                      'push_at': '2020-01-01T00:00:00Z', 'change_classification': {'cicd_skipped': False}}],
                      'cicd_run': {'pipeline': 'web', 'run_id': 'r1', 'run_commit': SHA, 'env': 'test'},
                      'cicd_unreachable_streak': 2, 'cicd_cli_fail_streak': 2}}}))
        self.initial_baseline = self.baseline.read_text()
        self.config(auto=True)

    def config(self, auto=True, push_auto=True):
        (self.root / 'memory/aidp-config.yaml').write_text(
            'cicd:\n  provider: command\n  auto_trigger: ' + str(auto).lower() +
            '\n  push_auto_deploy: ' + str(push_auto).lower() +
            '\n  push_deploy_min_wait_seconds: 0\n  pipelines: {test: web}\n'
            '  command: {list: list, view: view, trigger: trigger, retry: retry}\n')

    def node(self):
        return json.loads(self.baseline.read_text())['versions'][VERSION]

    def go(self, args, execute=None):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(io.StringIO()):
            with patch.object(providers, 'EXEC', execute or providers.EXEC):
                rc = watch.run(args + ['--root', str(self.root), '--baseline', str(self.baseline),
                                       '--version', VERSION, '--post-push-wait', '0', '--min-wait', '0'])
        return rc, json.loads(stream.getvalue().splitlines()[-1])

    def test_command_need_accept_all_actions(self):
        for action in ('check', 'list', 'view', 'trigger', 'retry'):
            with self.subTest(action=action):
                cfg = self.root / 'memory/aidp-config.yaml'
                self.config()
                if action == 'check':
                    cfg.write_text(cfg.read_text().replace('list: list', 'check: check, list: list'))
                calls = []
                def execute(command, cwd, timeout, shell=False):
                    calls.append(command)
                    if command == action:
                        return 4, json.dumps({'need_accept': True, 'reason': 'explicit approval required'}), ''
                    if command == 'list':
                        return 0, json.dumps([{'id': 'r1', 'status': 'running', 'commit': SHA}]), ''
                    return 0, json.dumps({'id': 'r1', 'status': 'success', 'commit': SHA}), ''
                mode = {'check': 'detect', 'list': 'detect', 'view': 'poll'}.get(action, action)
                rc, result = self.go(['--mode', mode, '--commit', SHA, '--run-id', 'r1'], execute)
                self.assertEqual((rc, result['verdict'], result['next_action']), (4, 'need-accept', 'accept'))
                self.assertFalse(result.get('degraded', False))
                self.assertIn('explicit approval required', result['reason'])
                self.assertFalse(any('--accept' in call for call in calls))

    def consume(self, code, result):
        path = self.root / 'memory/.aidp/result.json'
        path.write_text(json.dumps(result))
        return self.go(['--mode', 'consume', '--result', str(path), '--result-code', str(code)])

    def result(self, **changes):
        return dict({'mode': 'poll', 'verdict': 'unreachable', 'next_action': 'probe', 'degraded': True,
                     'push_auto_deploy': True, 'expected_commit': SHA, 'run_id': 'r1',
                     'pipeline': 'web', 'reason': 'platform timeout', 'degraded_reason': 'platform timeout'}, **changes)

    def test_degraded_handoff_keeps_unknown(self):
        rc, result = self.consume(4, self.result())
        self.assertEqual(rc, 0)
        node = self.node()
        self.assertEqual(node['run_state']['next_phase'], '3.2.1-probe')
        self.assertEqual(node['cicd_run']['status'], 'unknown')
        self.assertEqual(node['cicd_run']['degraded_reason'], 'platform timeout')
        self.assertEqual(node['cicd_unreachable_streak'], 2)
        self.assertFalse(node.get('last_deployed_at'))
        self.assertFalse(node.get('needs_human'))

    def test_invalid_degraded_never_advances(self):
        for changes in ({'next_action': 'accept', 'verdict': 'need-accept'}, {'expected_commit': 'f' * 40},
                        {'degraded': False}, {'verdict': 'failed'}, {'push_auto_deploy': False}):
            with self.subTest(changes=changes):
                self.baseline.write_text(self.initial_baseline)
                rc, _ = self.consume(4, self.result(**changes))
                self.assertNotEqual(self.node().get('run_state', {}).get('next_phase'), '3.2.1-probe')
                self.assertNotEqual(rc, 0)

    def test_immediate_freeze_and_recovery_reason(self):
        cases = [('trigger-failed', 2, 'pipeline-unknown'), ('retry-failed', 2, 'cicd-unreachable'),
                 ('unknown-status', 2, 'pipeline-unknown'), ('auto-trigger-off', 2, 'cicd-auto-trigger-off'),
                 ('need-accept', 4, 'cicd-auto-trigger-off'), ('failed', 2, 'deploy-unreachable')]
        for verdict, code, expected in cases:
            with self.subTest(verdict=verdict):
                self.baseline.write_text(self.initial_baseline)
                original_run = subprocess.run
                with patch.object(watch.subprocess, 'run', wraps=original_run) as invoked:
                    rc, result = self.consume(code, self.result(verdict=verdict, next_action='abort', degraded=False))
                freezes = [c.args[0] for c in invoked.call_args_list if 'autopilot_fail_handle.py' in c.args[0][1]]
                self.assertTrue(freezes)
                self.assertTrue(all('--freeze-now' in command for command in freezes))
                node = self.node()
                self.assertEqual(rc, 3, result)
                self.assertIs(node.get('needs_human'), True)
                self.assertEqual(node.get('freeze_reason'), expected)
                self.assertIn('platform timeout', node.get('needs_human_reason', ''))
                self.assertTrue(node.get('aiauto_frozen_at'))
                self.assertFalse(node.get('builds', [{}])[0].get('dev_fail_streak'))
                self.assertNotEqual(node['run_state']['next_phase'], '3.2.1-probe')

    def test_success_resets_matching_scope_only(self):
        data = json.loads(self.baseline.read_text())
        node = data['versions'][VERSION]
        node.update(dev_fail_phase='3.2.1-cicd', dev_fail_reason='cicd-run-vanished', dev_fail_streak=2)
        node['builds'][0].update(dev_fail_phase='3.2.1-deploy', dev_fail_reason='deploy-unreachable', dev_fail_streak=2)
        self.baseline.write_text(json.dumps(data))
        rc, result = self.consume(0, self.result(verdict='success', run_commit=SHA, degraded=False))
        self.assertEqual(rc, 0, result)
        node = self.node()
        self.assertEqual(node['dev_fail_streak'], 0)
        self.assertEqual(node['builds'][0]['dev_fail_streak'], 0)
        self.assertNotIn('dev_fail_reason', node['builds'][0])
        self.assertEqual(node['cicd_run']['status'], 'success')
        self.assertNotIn('cicd_unreachable_streak', node)
        self.assertNotIn('last_deployed_at', node)

    def test_success_binding_and_classification(self):
        for changes in ({'run_commit': 'f' * 40}, {'expected_commit': 'f' * 40}, {'run_id': 'old'},
                        {'run_commit': None}, {'pipeline': 'other'}):
            with self.subTest(changes=changes):
                self.baseline.write_text(self.initial_baseline)
                value = self.result(verdict='success', run_commit=SHA, degraded=False)
                value.update(changes)
                rc, _ = self.consume(0, value)
                self.assertNotEqual(rc, 0)
                self.assertNotEqual(self.node()['run_state']['next_phase'], '3.2.1-probe')
        data = json.loads(self.initial_baseline)
        data['versions'][VERSION]['builds'][0]['change_classification']['cicd_skipped'] = True
        self.baseline.write_text(json.dumps(data))
        rc, result = self.consume(4, self.result())
        self.assertEqual((rc, result['next_action']), (0, 'skip'))
        self.assertNotIn('run_state', self.node())

    def test_write_authorization_and_retry_cap(self):
        for mode, auto, count, expected in [('trigger', False, 0, 'auto-trigger-off'),
                                            ('retry', False, 0, 'auto-trigger-off'),
                                            ('retry', True, 3, 'failed')]:
            with self.subTest(mode=mode, auto=auto):
                self.config(auto=auto)
                def forbidden(*args, **kwargs):
                    self.fail('未授权或重试满额时不应调用 Command')
                rc, result = self.go(['--mode', mode, '--commit', SHA, '--run-id', 'r1',
                                      '--retry-count', str(count)], forbidden)
                self.assertEqual((rc, result['verdict']), (2, expected))

    def test_retry_rejects_wrong_commit_before_write(self):
        calls = []
        def execute(command, cwd, timeout, shell=False):
            calls.append(command)
            return 0, json.dumps({'id': 'r1', 'status': 'failed', 'commit': 'f' * 40}), ''
        rc, result = self.go(['--mode', 'retry', '--run-id', 'r1', '--commit', SHA], execute)
        self.assertEqual((rc, result['verdict']), (2, 'commit-mismatch'))
        self.assertEqual(calls, ['view'])

    def test_pipeline_failure_never_degrades(self):
        def execute(command, cwd, timeout, shell=False):
            return 0, json.dumps({'id': 'r1', 'status': 'failed', 'commit': SHA}), ''
        rc, result = self.go(['--mode', 'poll', '--run-id', 'r1', '--commit', SHA], execute)
        self.assertEqual((rc, result['verdict'], result['next_action']), (1, 'failed', 'retry'))
        self.assertFalse(result.get('degraded'))

    def blocks(self, filename):
        return [textwrap.dedent(b).replace('{{AIDP_HOME}}', str(REPO / '.aidp'))
                for b in re.findall(r'^[ \t]*```bash\n(.*?)\n[ \t]*```',
                                    (FLOW / filename).read_text(), re.M | re.S)]

    def fence(self, block, output, code):
        """只替换平台 watch 和 tick flags；consume/baseline/fail_handle 均跑生产脚本。"""
        result_file = self.root / 'fake-result.json'
        result_file.write_text(json.dumps(output))
        prefix = '''python3() {
  case "$1" in
    */autopilot_tick_flags.py) printf 'TARGET_VERSION=V0.1.0\\nHAS_WAKE_SOURCE=1\\n';;
    */cicd_watch.py)
      if [ "$3" = consume ]; then command "$REAL_PYTHON" "$@";
      else command "$REAL_PYTHON" -c 'import os,pathlib;print(pathlib.Path(os.environ["FAKE_RESULT"]).read_text())'; return "$FAKE_RC"; fi;;
    *) command "$REAL_PYTHON" "$@";;
  esac
}
'''
        return subprocess.run(['bash', '-c', prefix + block], cwd=self.root, capture_output=True, text=True,
                              env={**os.environ, 'REAL_PYTHON': sys.executable, 'FAKE_RESULT': str(result_file),
                                   'FAKE_RC': str(code)}, timeout=30)

    def test_a0_real_fence_handoff(self):
        block = next(b for b in self.blocks('phase-3-6.md') if '--mode detect' in b)
        outcome = self.fence(block, self.result(mode='detect', verdict='not-observed', run_id=None), 4)
        self.assertEqual(outcome.returncode, 0, outcome.stderr)
        self.assertEqual(self.node().get('run_state', {}).get('next_phase'), '3.2.1-probe')
        self.assertEqual(self.node()['cicd_run'].get('status'), 'unknown')
        # 留存旧 poll success，也不能覆盖 A0 本轮的 unknown/probe 证据。
        (self.root / 'memory/.aidp/cicd-poll.json').write_text(json.dumps(
            self.result(verdict='success', run_commit=SHA, degraded=False)))
        exit_block = self.blocks('phase-3-6b.md')[-1]
        outcome = self.fence(exit_block, {}, 0)
        self.assertEqual(outcome.returncode, 0, outcome.stderr)
        self.assertEqual(self.node()['cicd_run']['status'], 'unknown')
        self.assertEqual(self.node()['run_state']['next_phase'], '3.2.1-probe')

    def test_retry_acceptance_only_counts_real_retry(self):
        block = next(b for b in self.blocks('phase-3-6b.md') if '--mode retry' in b)
        result = self.result(mode='retry', verdict='retried', next_action='poll', run_id='r2',
                             run_commit=None, degraded=False)
        outcome = self.fence(block, result, 0)
        self.assertEqual(outcome.returncode, 0, outcome.stdout + outcome.stderr)
        self.assertEqual(self.node()['cicd_run']['cicd_retry_count'], 1)
        self.assertEqual(self.node()['cicd_run']['run_id'], 'r2')
        self.assertFalse(self.node()['cicd_run']['commit_verified'])
        self.assertNotEqual(self.node()['run_state']['next_phase'], '3.2.1-probe')

    def test_real_fence_immediate_freeze(self):
        trigger = next(b for b in self.blocks('phase-3-6.md') if '--mode trigger' in b)
        retry = next(b for b in self.blocks('phase-3-6b.md') if '--mode retry' in b)
        poll = next(b for b in self.blocks('phase-3-6b.md') if '--mode poll' in b)
        for block, verdict, auto, reason in (
            (trigger, 'trigger-failed', True, 'pipeline-unknown'),
            (retry, 'retry-failed', True, 'cicd-unreachable'),
            (poll, 'unknown-status', True, 'pipeline-unknown'),
            (trigger, 'auto-trigger-off', False, 'cicd-auto-trigger-off'),
            (retry, 'auto-trigger-off', False, 'cicd-auto-trigger-off'),
            (trigger, 'need-accept', True, 'cicd-auto-trigger-off'),
            (retry, 'need-accept', True, 'cicd-auto-trigger-off')):
            with self.subTest(verdict=verdict, auto=auto, retry=block == retry):
                self.baseline.write_text(self.initial_baseline)
                self.config(auto=auto)
                outcome = self.fence(block, self.result(verdict=verdict, next_action='abort', degraded=False),
                                     4 if verdict == 'need-accept' else 2)
                self.assertNotEqual(outcome.returncode, 0, outcome.stderr)
                self.assertEqual(self.node().get('freeze_reason'), reason, outcome.stdout + outcome.stderr)
                self.assertTrue(self.node().get('needs_human'))
                self.assertNotIn('cicd_retry_count', self.node()['cicd_run'])

    def test_c_real_fence_handoff(self):
        block = next(b for b in self.blocks('phase-3-6b.md') if '--mode poll' in b)
        outcome = self.fence(block, self.result(), 4)
        self.assertEqual(outcome.returncode, 0, outcome.stderr)
        self.assertEqual(self.node().get('run_state', {}).get('next_phase'), '3.2.1-probe')
        self.assertEqual(self.node().get('cicd_unreachable_streak'), 2)


if __name__ == '__main__':
    unittest.main()
