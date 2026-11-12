#!/usr/bin/env python3
"""entry_gate.py：改 code/** 前入口协议（resolve + branch-policy 读取标记）判定。"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]
GATE = SCRIPTS / 'entry_gate.py'
CONFIG = SCRIPTS / 'aidp_config.py'
sys.path.insert(0, str(SCRIPTS))
import entry_gate  # noqa: E402


class EntryGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='aidp-entry-gate-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / 'memory').mkdir()
        self.runtime = self.root / 'memory/.aidp'

    def context(self, name='t1', **fields):
        from entry_context import resolve_context
        result = resolve_context(self.root, fields.pop('entry', 'sprint-dev'), version='V1.0.0',
                                 write_set=fields.pop('write_set', ['code']), acceptance=['fixture'])
        path = Path(result['execution_context'])
        data = result['context']
        data.update(fields)
        path.write_text(json.dumps(data))
        (self.runtime / 'entry-task.json').write_text(json.dumps({
            'root': str(self.root), 'task_id': data['task_id'], 'execution_context': str(path)}))
        return path

    def marker(self, **fields):
        self.runtime.mkdir(parents=True, exist_ok=True)
        import aidp_config
        data = dict(aidp_config.branch_policy(str(self.root)), root=str(self.root), read_at=time.time())
        data.update(fields)
        (self.runtime / 'branch-policy-read.json').write_text(json.dumps(data), encoding='utf-8')

    def check(self, target='code/app.py', env=None):
        return entry_gate.check(self.root, target, env={} if env is None else env)

    def test_nothing_done_reports_both_steps_with_commands(self):
        res = self.check()
        self.assertFalse(res['ok'])
        self.assertEqual({'entry-context', 'branch-policy'}, set(res['missing']))
        joined = '\n'.join(res['hints'])
        self.assertIn('entry_context.py resolve', joined)
        self.assertIn('aidp_config.py branch-policy', joined)

    def test_resolved_and_branch_policy_read_passes(self):
        self.context()
        self.marker()
        res = self.check()
        self.assertTrue(res['ok'], res)
        self.assertTrue(res['context'].endswith('context.json'))

    def test_only_branch_policy_missing(self):
        self.context()
        self.assertEqual(['branch-policy'], self.check()['missing'])

    def test_only_resolve_missing(self):
        self.marker()
        self.assertEqual(['entry-context'], self.check()['missing'])

    def test_non_code_target_not_applicable(self):
        res = self.check('docs/readme.md')
        self.assertTrue(res['ok'])
        self.assertFalse(res['applies'])
        self.assertTrue(self.check('memory/aidp-config.yaml')['ok'])
        self.assertTrue(self.check('/elsewhere/code/app.py')['ok'], '项目外路径不受约束')

    def test_absolute_and_nested_code_paths_are_guarded(self):
        self.assertFalse(self.check(str(self.root / 'code/backend/x.java'))['ok'])
        self.assertFalse(self.check('code/frontend/src/a.vue')['ok'])
        self.assertTrue(self.check('src/code/x.py')['ok'], '只有项目根下的 code/ 受约束')

    def test_completed_foreign_and_stale_contexts_do_not_count(self):
        self.marker()
        self.context('done', status='completed')
        self.context('foreign', root='/somewhere/else')
        stale = self.context('stale')
        old = time.time() - 3 * 24 * 3600
        os.utime(stale, (old, old))
        res = self.check()
        self.assertEqual(['entry-context'], res['missing'])

    def test_explicit_env_context_must_be_fresh(self):
        self.marker()
        path = self.context('mine')
        old = time.time() - 3 * 24 * 3600
        os.utime(path, (old, old))
        self.assertFalse(self.check(env={'AIDP_EXECUTION_CONTEXT': str(path)})['ok'])

    def test_stale_marker_requires_reread(self):
        self.context()
        self.marker()
        marker = self.runtime / 'branch-policy-read.json'
        old = time.time() - 3 * 24 * 3600
        os.utime(marker, (old, old))
        self.assertEqual(['branch-policy'], self.check()['missing'])

    def test_formal_context_requires_branch_policy(self):
        self.context(mode='formal', entry='sprint-autopilot')
        self.assertEqual(['branch-policy'], self.check()['missing'])

    def test_tick_without_context_is_rejected(self):
        res = self.check(env={'AIDP_TICK_COMMAND': 'sprint-autopilot'})
        self.assertFalse(res['ok'])
        self.assertEqual({'entry-context', 'branch-policy'}, set(res['missing']))

    def test_marker_needs_choice_blocks_until_policy_saved(self):
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        self.context()
        out = subprocess.run([sys.executable, str(CONFIG), '--root', str(self.root), 'branch-policy'],
                             capture_output=True, text=True)
        self.assertEqual(3, out.returncode, out.stdout + out.stderr)
        marker = json.loads((self.runtime / 'branch-policy-read.json').read_text())
        self.assertTrue(marker['needs_choice'])
        self.assertEqual(['branch-policy-choice'], self.check()['missing'])
        saved = subprocess.run([sys.executable, str(CONFIG), '--root', str(self.root),
                                'set', 'development.branch_policy', 'current'], capture_output=True, text=True)
        self.assertEqual(0, saved.returncode, saved.stderr)
        self.assertFalse(self.check()['ok'], '偏好变化后必须重读')
        self.marker()
        self.assertTrue(self.check()['ok'])

    def test_branch_policy_command_writes_marker_without_git(self):
        out = subprocess.run([sys.executable, str(CONFIG), '--root', str(self.root), 'branch-policy'],
                             capture_output=True, text=True)
        self.assertEqual(0, out.returncode, out.stdout + out.stderr)
        marker = json.loads((self.runtime / 'branch-policy-read.json').read_text())
        self.assertEqual('not-applicable', marker['status'])
        self.assertIn('read_at', marker)
        self.context()
        self.assertTrue(self.check()['ok'])

    def test_cli_exit_codes_and_json(self):
        bad = subprocess.run([sys.executable, str(GATE), 'check', '--root', str(self.root),
                              '--target', 'code/a.py', '--json'], capture_output=True, text=True, env={
                                  k: v for k, v in os.environ.items()
                                  if k not in ('AIDP_TICK_COMMAND', 'AIDP_EXECUTION_CONTEXT')})
        self.assertEqual(2, bad.returncode)
        self.assertFalse(json.loads(bad.stdout)['ok'])
        ok = subprocess.run([sys.executable, str(GATE), 'check', '--root', str(self.root),
                             '--target', 'docs/a.md'], capture_output=True, text=True)
        self.assertEqual(0, ok.returncode)

    def test_unbound_context_is_not_discovered(self):
        self.context()
        self.marker()
        (self.runtime / 'entry-task.json').unlink()
        self.assertEqual(['entry-context'], self.check()['missing'])

    def test_wrong_explicit_context_never_falls_back(self):
        self.context()
        self.marker()
        self.assertFalse(self.check(env={'AIDP_EXECUTION_CONTEXT': 'missing.json'})['ok'])

    def test_write_set_enforced(self):
        self.context(write_set=['code/service'])
        self.marker()
        self.assertTrue(self.check('code/service/a.py')['ok'])
        self.assertIn('write-set', self.check('code/other.py')['missing'])

    def test_session_marker_does_not_fallback_to_project_marker(self):
        self.context()
        self.marker()
        self.assertFalse(self.check(env={'AIDP_SESSION_ID': 'different'})['ok'])

    def test_changed_branch_policy_requires_fresh_read(self):
        import aidp_config
        self.context()
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        (self.root / 'memory/aidp-config.yaml').write_text('development:\n  branch_policy: current\n')
        self.marker(**aidp_config.branch_policy(str(self.root)))
        self.assertTrue(self.check()['ok'])
        (self.root / 'memory/aidp-config.yaml').write_text('development:\n  branch_policy: new\n')
        self.assertIn('branch-policy', self.check()['missing'])

    def test_invalid_git_and_wrong_branch_marker_root_denied(self):
        self.context()
        self.marker()
        (self.root / '.git').write_text('gitdir: /missing/repository')
        self.assertIn('branch-policy', self.check()['missing'])
        (self.root / '.git').unlink()
        self.marker(root='/wrong/project')
        self.assertIn('branch-policy', self.check()['missing'])

    def test_bind_is_session_specific_and_context_close_revokes(self):
        path = self.context()
        self.marker()
        bound = entry_gate.bind_context(self.root, path, 'session-one')
        self.assertTrue(bound['ok'], bound)
        self.assertTrue(self.check(env={'AIDP_SESSION_ID': 'session-one'})['ok'])
        self.assertFalse(self.check(env={'AIDP_SESSION_ID': 'session-two'})['ok'])
        ctx = json.loads(path.read_text())
        ctx['status'] = 'completed'
        path.write_text(json.dumps(ctx))
        self.assertFalse(self.check(env={'AIDP_SESSION_ID': 'session-one'})['ok'])

    def test_session_hint_contains_real_session_identifier(self):
        result = self.check(env={'AIDP_SESSION_ID': 'session-real-123'})
        self.assertIn('--session-id session-real-123', '\n'.join(result['hints']))

    def test_test_context_and_empty_scope_do_not_authorize_implementation(self):
        self.context(entry='sprint-test')
        self.marker()
        self.assertFalse(self.check()['ok'])
        path = self.context(write_set=[])
        self.assertFalse(entry_gate.bind_context(self.root, path)['ok'])

    def test_symlink_cannot_extend_write_set(self):
        self.context(write_set=['code/allowed'])
        self.marker()
        (self.root / 'code/allowed').mkdir(parents=True)
        (self.root / 'code/other').mkdir()
        (self.root / 'code/allowed/link').symlink_to(self.root / 'code/other', target_is_directory=True)
        self.assertFalse(self.check('code/allowed/link/app.py')['ok'])

    def test_bind_if_writable_selects_readonly_identity_without_granting_writes(self):
        from entry_context import resolve_context
        self.context()
        self.marker()
        marker = entry_gate.task_marker_path(self.root)
        original = marker.read_bytes()
        for fields in ({'write_set': [], 'task_scope': 'development'},
                       {'write_set': ['code'], 'task_scope': 'review'}):
            with self.subTest(fields=fields):
                context = resolve_context(self.root, 'sprint-dev', version='V1.0.0',
                                          acceptance=['fixture'], **fields)['execution_context']
                strict = entry_gate.bind_context(self.root, context)
                self.assertFalse(strict['ok'])
                self.assertNotIn('skipped', strict)
                out = subprocess.run([sys.executable, str(GATE), 'bind', '--root', str(self.root),
                    '--execution-context', context, '--session-id', 'readonly', '--if-writable', '--json'],
                    capture_output=True, text=True)
                self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
                result = json.loads(out.stdout)
                self.assertTrue(result['skipped'])
                self.assertFalse(result['ok'])
                self.assertEqual(marker.read_bytes(), original)
                selected = json.loads(entry_gate.task_marker_path(self.root, 'readonly').read_text())
                self.assertEqual(selected['execution_context'], context)
                self.assertFalse(self.check(env={'AIDP_SESSION_ID': 'readonly'})['ok'])
                self.assertFalse(self.check(env={'AIDP_EXECUTION_CONTEXT': context})['ok'])

    def test_bind_if_writable_does_not_skip_identity_or_branch_errors(self):
        path = self.context(write_set=[])
        missing_policy = entry_gate.bind_context(self.root, path, if_writable=True)
        self.assertFalse(missing_policy['ok'])
        self.assertIn('branch-policy', missing_policy['missing'])
        self.assertNotIn('skipped', missing_policy)
        self.marker()
        missing_context = entry_gate.bind_context(self.root, self.root / 'missing.json', if_writable=True)
        self.assertFalse(missing_context['ok'])
        self.assertIn('entry-context', missing_context['missing'])
        self.assertNotIn('skipped', missing_context)

    def test_self_check(self):
        self.assertEqual(0, subprocess.run([sys.executable, str(GATE), '--self-check'],
                                           capture_output=True).returncode)


if __name__ == '__main__':
    unittest.main()
