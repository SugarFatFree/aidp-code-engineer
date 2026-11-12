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
from entry_context import resolve_context

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
                      'push_at': '2020-01-01T00:00:00Z'}],
                      'cicd_run': {'pipeline': 'web', 'run_id': 'r1', 'run_commit': SHA, 'env': 'test'},
                      'cicd_unreachable_streak': 2, 'cicd_cli_fail_streak': 2}}}))
        self.initial_baseline = self.baseline.read_text()
        self.config(auto=True)
        self.execution_context = None

    def context(self, grants, **kwargs):
        return resolve_context(self.root, 'sprint-dev', version=VERSION,
            additional_grants=grants, authorization_source={'kind': 'user-text',
            'request_id': 'offline-cicd-test', 'text': '本次测试授权动作：' + ', '.join(grants)},
            **kwargs)['execution_context']

    def config(self, auto=True, push_auto=True, explicit=False):
        (self.root / 'memory/aidp-config.yaml').write_text(
            'cicd:\n  provider: command\n  auto_trigger: ' + str(auto).lower() +
            '\n  push_auto_deploy: ' + str(push_auto).lower() +
            '\n  push_deploy_min_wait_seconds: 0\n  pipelines: {test: web}\n'
            '  command: {list: list, view: view, trigger: trigger, retry: retry}\n' +
            ('  auto_trigger_source: {kind: project-policy, user_selected: true, request_id: choice-1, '
             'text: 禁止自动触发部署}\n' if explicit else ''))

    def node(self):
        return json.loads(self.baseline.read_text())['versions'][VERSION]

    def go(self, args, execute=None, context='default'):
        if context == 'default' and self.execution_context is None:
            self.execution_context = self.context(['push', 'deploy'])
        ctx = self.execution_context if context == 'default' else context
        if ctx:
            args = args + ['--execution-context', str(ctx)]
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(io.StringIO()):
            with patch.object(providers, 'EXEC', execute or providers.EXEC):
                rc = watch.run(args + ['--root', str(self.root), '--baseline', str(self.baseline),
                                       '--version', VERSION, '--post-push-wait', '0', '--min-wait', '0'])
        return rc, json.loads(stream.getvalue().splitlines()[-1])

    def test_unconfigured_modes_never_construct_or_call_provider(self):
        for provider, pipelines in (('none', '{test: web}'), ('github-actions', '{}'),
                                    ('gitlab-ci', '{}'), ('command', '{test: "  "}')):
            (self.root / 'memory/aidp-config.yaml').write_text(
                f'cicd:\n  provider: {provider}\n  pipelines: {pipelines}\n')
            for mode in ('detect', 'watch', 'poll', 'trigger', 'retry'):
                with self.subTest(provider=provider, mode=mode):
                    with patch.object(providers, 'get_provider') as factory:
                        rc, result = self.go(['--mode', mode, '--commit', SHA, '--run-id', 'r1'])
                        factory.assert_not_called()
                    self.assertEqual((rc, result['next_action']), (3, 'none'))
                    self.assertFalse(result['ok'])
                    self.assertFalse(result['commit_verified'])
                    self.assertEqual(result['execution_status'], 'UNVERIFIED')
                    self.assertTrue(result['configuration_degraded'])
                    self.assertNotIn('run_id', result)
            # 既有 baseline 中的旧 pipeline=web 不能绕过未配置判定。
            self.assertEqual(self.node()['cicd_run']['pipeline'], 'web')

    def test_config_degrade_consumes_once_without_probe_freeze_or_success(self):
        for grants in (['push', 'deploy'], ['push']):
            self.baseline.write_text(self.initial_baseline)
            self.execution_context = self.context(grants)
            (self.root / 'memory/aidp-config.yaml').write_text('cicd:\n  provider: command\n  pipelines: {}\n')
            rc, result = self.go(['--mode', 'detect', '--commit', SHA])
            consumed_rc, consumed = self.consume(rc, result)
            self.assertEqual((consumed_rc, consumed['next_action']), (0, 'none'))
            self.assertFalse(consumed['ok'])
            node = self.node()
            self.assertEqual(node['run_state']['next_phase'], '3.3-audit')
            self.assertEqual(node['cicd_run']['status'], 'unverified' if 'deploy' in grants else 'not_requested')
            self.assertFalse(node.get('last_deployed_at'))
            self.assertFalse(node.get('phase_beta_done_at'))
            self.assertFalse(node.get('needs_human'))
            self.assertEqual(node['cicd_unreachable_streak'], 2)
            self.assertEqual(node['cicd_cli_fail_streak'], 2)

    def test_explicit_pipeline_works_without_environment_mapping(self):
        (self.root / 'memory/aidp-config.yaml').write_text(
            'cicd:\n  provider: command\n  pipelines: {}\n  command: {list: list, view: view}\n')
        calls = []
        def execute(command, cwd, timeout, shell=False):
            calls.append(command)
            return 0, json.dumps([{'id': 'r1', 'status': 'running', 'commit': SHA}]), ''
        rc, result = self.go(['--mode', 'detect', '--commit', SHA, '--pipeline', 'web'], execute)
        self.assertEqual((rc, result['next_action'], result['pipeline']), (0, 'poll', 'web'))
        self.assertIn('list', calls)
        self.assertNotIn('configuration_degraded', result)
        (self.root / 'memory/aidp-config.yaml').write_text('cicd:\n  provider: none\n')
        with patch.object(providers, 'get_provider') as factory:
            rc, result = self.go(['--mode', 'detect', '--commit', SHA, '--pipeline', 'web'])
            factory.assert_not_called()
        self.assertEqual((rc, result['verdict']), (3, 'disabled'))

    def test_configuration_degrade_rejected_if_config_or_commit_changed(self):
        (self.root / 'memory/aidp-config.yaml').write_text('cicd:\n  provider: command\n  pipelines: {}\n')
        rc, result = self.go(['--mode', 'detect', '--commit', SHA])
        result['expected_commit'] = 'f' * 40
        self.assertEqual(self.consume(rc, result)[0], 2)
        result['expected_commit'] = SHA
        self.config()
        self.assertEqual(self.consume(rc, result)[0], 2)
        self.assertFalse(self.node().get('needs_human'))
        self.assertFalse(self.node().get('last_deployed_at'))

    def test_missing_context_never_writes_with_config_true(self):
        for mode in ('trigger', 'retry'):
            with self.subTest(mode=mode):
                calls = []
                def execute(command, cwd, timeout, shell=False):
                    calls.append(command)
                    return 0, json.dumps({'id': 'r1', 'status': 'failed', 'commit': SHA}), ''
                rc, result = self.go(['--mode', mode, '--commit', SHA, '--run-id', 'r1'],
                                     execute, context=None)
                self.assertEqual(calls, [], '缺上下文不得进入 provider 写路径')
                self.assertEqual((rc, result['verdict'], result['next_action']),
                                 (0, 'NOT_REQUESTED', 'none'))
                self.assertFalse(result['ok'])

    def test_push_only_context_never_writes(self):
        ctx = self.context(['push'])
        for mode in ('trigger', 'retry'):
            with self.subTest(mode=mode):
                def forbidden(*args, **kwargs):
                    self.fail('push grant 不得调用 provider 写路径')
                rc, result = self.go(['--mode', mode, '--commit', SHA, '--run-id', 'r1'], forbidden, ctx)
                self.assertEqual((rc, result['verdict'], result['next_action']),
                                 (0, 'NOT_REQUESTED', 'none'))

    def test_readonly_observation_never_suggests_write_or_probe(self):
        ctx = self.context(['push'])
        self.config(push_auto=False)
        cases = [('detect', [], 'not-triggered', 0),
                 ('poll', {'id': 'r1', 'commit': SHA, 'status': 'success'}, 'success', 0),
                 ('poll', {'id': 'r1', 'commit': SHA, 'status': 'failed'}, 'failed', 2)]
        for mode, response, observed, expected_rc in cases:
            with self.subTest(observed=observed):
                calls = []
                def execute(command, cwd, timeout, shell=False):
                    calls.append(command)
                    return 0, json.dumps(response), ''
                rc, result = self.go(['--mode', mode, '--commit', SHA, '--run-id', 'r1'], execute, ctx)
                self.assertEqual((rc, result['verdict'], result['next_action']),
                                 (expected_rc, 'NOT_REQUESTED', 'none'))
                self.assertEqual(result['observed_verdict'], observed)
                self.assertTrue(result['readonly'])
                self.assertFalse(result['ok'])
                self.assertNotIn('trigger_cmd', result)
                self.assertNotIn('retry_cmd', result)
                self.assertFalse(set(calls) & {'trigger', 'retry'})

    def test_readonly_provider_accept_request_never_becomes_authorization_prompt(self):
        ctx = self.context(['push'])
        def execute(command, cwd, timeout, shell=False):
            return 4, json.dumps({'need_accept': True, 'reason': 'platform approval needed'}), ''
        rc, result = self.go(['--mode', 'poll', '--commit', SHA, '--run-id', 'r1'], execute, ctx)
        self.assertEqual((rc, result['verdict'], result['next_action']), (0, 'NOT_REQUESTED', 'none'))
        self.assertEqual(result['observed_verdict'], 'need-accept')
        self.assertIn('platform approval needed', json.dumps(result))
        self.execution_context = ctx
        rc, consumed = self.consume(rc, result)
        self.assertEqual((rc, consumed['next_action']), (0, 'none'))
        self.assertFalse(self.node().get('needs_human'))

    def test_consume_not_requested_does_not_freeze_or_succeed(self):
        self.execution_context = self.context(['push'])
        data = json.loads(self.initial_baseline)
        data['versions'][VERSION]['run_state'] = {
            'current_phase': '3.2.1-deploy', 'next_phase': '3.2.1-probe',
            'status': 'done', 'pending_actions': ['deploy-probe']}
        self.baseline.write_text(json.dumps(data))
        rc, result = self.consume(0, self.result(verdict='NOT_REQUESTED', next_action='none',
            readonly=True, observed_verdict='success', degraded=False))
        self.assertEqual((rc, result['next_action']), (0, 'none'))
        node = self.node()
        self.assertFalse(node.get('needs_human'))
        self.assertNotEqual(node['cicd_run'].get('status'), 'success')
        self.assertNotEqual(node['run_state'].get('next_phase'), '3.2.1-probe')
        self.assertNotIn('cicd-watch', node['run_state'].get('pending_actions', []))
        self.assertNotIn('deploy-probe', node['run_state'].get('pending_actions', []))
        self.assertNotIn('last_deployed_at', node)
        self.assertEqual(node['cicd_unreachable_streak'], 2)

    def test_explicit_deploy_grant_triggers_and_records_budget(self):
        calls = []
        def execute(command, cwd, timeout, shell=False):
            calls.append(command)
            return 0, json.dumps({'run_id': 'r2'}), ''
        rc, result = self.go(['--mode', 'trigger', '--commit', SHA, '--ref', 'main'], execute)
        self.assertEqual((rc, result['verdict']), (0, 'triggered'))
        self.assertEqual(calls, ['trigger'])
        budget = json.loads(Path(self.execution_context).with_name('budget.json').read_text())
        self.assertEqual(budget['used']['processes'], 1)
        self.assertEqual(budget['outcomes'][-1]['status'], 'PASS')

    def test_same_input_tool_failure_stops_before_second_provider_write(self):
        calls = []
        def execute(command, cwd, timeout, shell=False):
            calls.append(command)
            return 1, '', 'provider original offline error'
        args = ['--mode', 'trigger', '--commit', SHA, '--ref', 'main']
        rc, result = self.go(args, execute)
        self.assertEqual((rc, result['verdict']), (2, 'trigger-failed'))
        rc, result = self.go(args, execute)
        self.assertEqual((rc, result['next_action']), (2, 'abort'))
        self.assertEqual(result['execution_status'], 'TOOL_ERROR')
        self.assertIn('provider original offline error', json.dumps(result))
        self.assertEqual(calls, ['trigger'])
        budget = json.loads(Path(self.execution_context).with_name('budget.json').read_text())
        self.assertEqual(budget['used']['processes'], 1)
        self.assertEqual(budget['outcomes'][-1]['status'], 'TOOL_ERROR')

    def test_deploy_grant_works_with_default_or_legacy_false_capability(self):
        for omitted in (True, False):
            with self.subTest(omitted=omitted):
                self.config(auto=False)
                path = self.root / 'memory/aidp-config.yaml'
                if omitted:
                    path.write_text(path.read_text().replace('  auto_trigger: false\n', ''))
                before = path.read_text()
                calls = []
                def execute(command, cwd, timeout, shell=False):
                    calls.append(command)
                    return 0, json.dumps({'run_id': 'r2'}), ''
                rc, result = self.go(['--mode', 'trigger', '--commit', SHA], execute)
                self.assertEqual((rc, result['verdict']), (0, 'triggered'))
                self.assertEqual(calls, ['trigger'])
                self.assertEqual(path.read_text(), before)

    def test_shared_retry_budget_cannot_be_reset_by_new_run_id(self):
        ctx = self.context(['deploy'], execution_budget={'retries': 1})
        calls = []
        def execute(command, cwd, timeout, shell=False):
            calls.append(command)
            return 0, json.dumps({'id': 'r2', 'status': 'failed', 'commit': SHA}), ''
        rc, result = self.go(['--mode', 'retry', '--commit', SHA, '--run-id', 'r1'], execute, ctx)
        self.assertEqual((rc, result['verdict']), (0, 'retried'))
        rc, result = self.go(['--mode', 'retry', '--commit', SHA, '--run-id', 'r2'], execute, ctx)
        self.assertEqual((rc, result['execution_status']), (2, 'BUDGET_EXCEEDED'))
        self.assertEqual(calls, ['view', 'retry'])
        budget = json.loads(Path(ctx).with_name('budget.json').read_text())
        self.assertEqual(budget['used']['retries'], 1)

    def test_process_budget_stops_before_provider_check(self):
        ctx = self.context(['deploy'], execution_budget={'processes': 0})
        cfg = self.root / 'memory/aidp-config.yaml'
        cfg.write_text(cfg.read_text().replace('list: list', 'check: check, list: list'))
        def forbidden(*args, **kwargs):
            self.fail('预算用尽后不得再探 CLI')
        rc, result = self.go(['--mode', 'trigger', '--commit', SHA], forbidden, ctx)
        self.assertEqual((rc, result['execution_status']), (2, 'BUDGET_EXCEEDED'))

    def test_retry_requires_known_commit(self):
        for commit in ('', 'f' * 40):
            with self.subTest(commit=commit):
                calls = []
                def execute(command, cwd, timeout, shell=False):
                    calls.append(command)
                    return 0, json.dumps({'id': 'r1', 'status': 'failed', 'commit': commit}), ''
                rc, result = self.go(['--mode', 'retry', '--commit', SHA, '--run-id', 'r1'], execute)
                self.assertEqual((rc, result['verdict']), (2, 'commit-mismatch'))
                self.assertEqual(calls, ['view'])

    def test_consume_does_not_trust_stale_deploy_result_for_push_only_task(self):
        self.execution_context = self.context(['push'])
        rc, result = self.consume(0, self.result(verdict='success', next_action='probe',
                                                run_commit=SHA, degraded=False))
        self.assertEqual(result['verdict'], 'NOT_REQUESTED')
        self.assertNotEqual(self.node()['run_state']['next_phase'], '3.2.1-probe')
        self.assertFalse(self.node().get('needs_human'))
        self.assertNotEqual(self.node()['cicd_run']['status'], 'success')

    def test_readonly_failed_consumption_preserves_failure_without_freeze(self):
        self.execution_context = self.context(['push'])
        rc, result = self.consume(2, self.result(verdict='NOT_REQUESTED', next_action='none',
                observed_verdict='failed', readonly=True, degraded=False))
        self.assertEqual((rc, result['observed_verdict']), (2, 'failed'))
        self.assertFalse(result['ok'])
        self.assertFalse(self.node().get('needs_human'))
        self.assertNotIn('cicd_retry_count', self.node()['cicd_run'])

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
        # 无 push_base_ref（分类缺失）→ fail-closed 监听，绝不 skip。
        rc, result = self.consume(4, self.result())
        self.assertNotEqual(result.get('next_action'), 'skip')
        # 有 push_base_ref + push_commit 且为纯文档推送 → 只读分类 skip，且不改工作区。
        def git(*a):
            return subprocess.run(['git', '-C', str(self.root), '-c', 'user.email=a@b.c', '-c', 'user.name=t', *a],
                                  check=True, capture_output=True, text=True).stdout.strip()
        (self.root / 'package.json').write_text('{}\n')
        git('add', 'package.json'); git('commit', '-qm', 'base')
        base = git('rev-parse', 'HEAD')
        (self.root / 'docs').mkdir()
        (self.root / 'docs/g.md').write_text('# g\n')
        git('add', 'docs/g.md'); git('commit', '-qm', 'docs')
        head = git('rev-parse', 'HEAD')
        data = json.loads(self.initial_baseline)
        data['versions'][VERSION]['builds'][0].update(push_commit=head, push_base_ref=base)
        self.baseline.write_text(json.dumps(data))
        rc, result = self.consume(4, self.result())
        self.assertEqual((rc, result['next_action']), (0, 'skip'))
        self.assertNotIn('run_state', self.node())
        # 同一区间含正式代码 → 不 skip。
        (self.root / 'src').mkdir()
        (self.root / 'src/App.ts').write_text('export {}\n')
        git('add', 'src/App.ts'); git('commit', '-qm', 'code')
        data['versions'][VERSION]['builds'][0]['push_commit'] = git('rev-parse', 'HEAD')
        self.baseline.write_text(json.dumps(data))
        rc, result = self.consume(4, self.result())
        self.assertNotEqual(result.get('next_action'), 'skip')

    def test_write_authorization_and_retry_cap(self):
        for mode, auto, count, expected in [('trigger', False, 0, 'auto-trigger-off'),
                                            ('retry', False, 0, 'auto-trigger-off'),
                                            ('retry', True, 3, 'failed')]:
            with self.subTest(mode=mode, auto=auto):
                self.config(auto=auto, explicit=not auto)
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

    def fence(self, block, output, code, wake=1):
        """只替换平台 watch 和 tick flags；consume/baseline/fail_handle 均跑生产脚本。"""
        if self.execution_context is None:
            self.execution_context = self.context(['push', 'deploy'])
        data = json.loads(self.baseline.read_text())
        data['versions'][VERSION]['execution_context'] = self.execution_context
        self.baseline.write_text(json.dumps(data))
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
        prefix = prefix.replace('HAS_WAKE_SOURCE=1', 'HAS_WAKE_SOURCE=' + str(wake))
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

    def test_readonly_running_fence_without_wake_does_not_freeze_optional_deploy(self):
        self.execution_context = self.context(['push'])
        block = next(b for b in self.blocks('phase-3-6b.md') if '--mode poll' in b)
        output = self.result(verdict='running', next_action='poll', readonly=True, degraded=False)
        outcome = self.fence(block, output, 0, wake=0)
        self.assertEqual(outcome.returncode, 0, outcome.stdout + outcome.stderr)
        self.assertFalse(self.node().get('needs_human'))
        self.assertNotEqual(self.node()['cicd_run']['status'], 'success')

    def test_not_requested_retry_fence_never_counts_success_or_freezes(self):
        self.execution_context = self.context(['push'])
        block = next(b for b in self.blocks('phase-3-6b.md') if '--mode retry' in b)
        output = self.result(mode='retry', verdict='NOT_REQUESTED', next_action='none',
                             readonly=True, degraded=False)
        outcome = self.fence(block, output, 0)
        self.assertEqual(outcome.returncode, 0, outcome.stdout + outcome.stderr)
        node = self.node()
        self.assertNotIn('cicd_retry_count', node['cicd_run'])
        self.assertFalse(node.get('needs_human'))
        self.assertNotEqual(node['cicd_run']['status'], 'success')
        self.assertEqual(node['run_state']['pending_actions'], [])
        self.assertNotEqual(node['run_state']['next_phase'], '3.2.1-probe')

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
                self.config(auto=auto, explicit=not auto)
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
