#!/usr/bin/env python3
"""轻量任务真实入口→命令继承→测试修复→收尾，核对在途Sprint不被改写。"""
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]


class LightTaskFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git('init', '-q')
        self.git('config', 'user.name', 'fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        (self.root / '.gitignore').write_text('__pycache__/\nmemory/.aidp/\n')
        (self.root / 'app.py').write_text('button = False\n')
        tests = self.root / 'tests'
        tests.mkdir()
        (tests / 'test_app.py').write_text('import unittest\nfrom pathlib import Path\n'
            'class ButtonTest(unittest.TestCase):\n'
            ' def test_button(self): self.assertEqual(Path("app.py").read_text(), "button = True\\n")\n'
            'if __name__ == "__main__": unittest.main()\n')
        self.protected = {
            'memory/V1/alice/activeContext.md': 'current sprint: 007\n',
            'memory/V1/alice/progress.md': 'Sprint-007 running\n',
            'memory/V1/alice/sprints/sprint-006.md': 'closed\n',
            'docs/plans/V1/01_研发执行计划.md': 'Sprint-007\n',
            'CLAUDE.md': 'current sprint: 007\n',
            'memory/.sprint-autopilot-baseline.json': json.dumps({'versions': {'V1': {
                'current_build': 'build7', 'sprints': {'007': {'status': 'running'}}, 'aiauto_test_required': True}}}),
        }
        for rel, text in self.protected.items():
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        self.git('add', '-A'); self.git('commit', '-qm', 'base')

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args], text=True,
                              capture_output=True, check=True).stdout.strip()

    def cli(self, script, *args, expected=0):
        root_flag = '--repo-root' if script == 'commit_gate.py' else '--root'
        command = [sys.executable, '-B', str(SCRIPTS / script)]
        if script in ('entry_context.py', 'test_ledger.py'):
            command += [args[0], root_flag, str(self.root), *args[1:]]
        else:
            command += [root_flag, str(self.root), *args]
        proc = subprocess.run(command, text=True, capture_output=True)
        self.assertEqual(proc.returncode, expected, proc.stdout + proc.stderr)
        return json.loads(proc.stdout.strip().splitlines()[-1])

    def resolve(self, entry='sprint-dev', grants=(), **extra):
        args = ['resolve', '--entry', entry, '--version', 'V1', '--write-set', 'app.py', '--acceptance', '按钮可见']
        for action in grants: args.extend(['--grant', action])
        if grants:
            args.extend(['--authorization-source', json.dumps({'kind':'user-text','request_id':'fixture-user-request',
                'text':'本次明确要求：' + ','.join(grants)}, ensure_ascii=False)])
        for key, value in extra.items(): args.extend(['--' + key.replace('_', '-'), value])
        return self.cli('entry_context.py', *args)

    def assert_protected(self):
        for rel, expected in self.protected.items():
            self.assertEqual((self.root / rel).read_text(), expected, rel)
        self.assertEqual(list(self.root.rglob('_sprint-*')), [])
        self.assertEqual([p.name for p in (self.root / 'memory/V1/alice/sprints').iterdir()], ['sprint-006.md'])

    def test_authorized_tests_review_retry_and_completion_keep_sprint_unchanged(self):
        resolved = self.resolve(grants=['related-test', 'review'])
        ctx = resolved['execution_context']
        self.assertEqual(resolved['identity']['mode'], 'light')
        for entry, phase in [('sprint-start','prepare'),('sprint-dev','dev'),('sprint-test','test'),
                             ('sprint-bugfix','repair'),('sprint-dev','dev'),('sprint-close','close')]:
            nested = self.cli('entry_context.py', 'resolve', '--entry', entry, '--execution-context', ctx)
            self.assertEqual(nested['identity'], resolved['identity'])
            route = self.cli('entry_context.py', 'route', '--entry', entry, '--phase', phase, '--execution-context', ctx)
            self.assertIn('allocate-sprint', route['forbidden_actions'])
        runners = [{'cwd':'.','suffixes':['.py'],'argv':[sys.executable,'-B','{tests}']}]
        directory = Path(ctx).parent
        scope_path = directory / 'scope.json'
        (self.root / 'app.py').write_text('button = None\n')
        def run(expected):
            scope = self.cli('test_scope.py', '--execution-context', ctx, '--runners-json', json.dumps(runners), '--json')
            scope_path.write_text(json.dumps(scope))
            output = self.cli('test_ledger.py', 'run-scope', '--execution-context', ctx, '--scope-file', str(scope_path),
                              '--env-id', 'fixture', expected=expected)
            return scope, output
        scope, failed = run(1)
        self.assertEqual(failed['status'], 'FAIL')
        (self.root / 'app.py').write_text('button = True\n')
        scope, passed = run(0)
        self.assertEqual(passed['status'], 'PASS')
        report = directory / 'review.json'
        report.write_text(json.dumps({'schema':1,'kind':'code-review','task_id':resolved['identity']['task_id'],
            'version':'V1','status':'PASS','scope_hash':scope['scope_hash'],'execution_context':resolved['identity'],
            'reviewer':'test-fixture-reviewer','checks':[{'kind':'code-review','status':'PASS',
                'evidence':['fixture inspected app.py:1 button=True and test assertion']}],'findings':[]}))
        ids = [arg for value in passed['run_ids'] for arg in ('--run-id',value)]
        evidence = ['--execution-context',ctx,'--scope-file',str(scope_path),'--scope-hash',scope['scope_hash'],
                    '--env-id','fixture',*ids]
        self.cli('test_ledger.py','record-review',*evidence,'--name','light-review','--report',str(report))
        static = self.cli('entry_context.py','static','--execution-context',ctx,'--input','app.py','--',
            sys.executable,'-B','-c','import ast; ast.parse(open("app.py").read())')
        complete = self.cli('entry_context.py','complete',*evidence,'--review-name','light-review',
                            '--static-evidence',static['evidence_file'])
        self.assertTrue(complete['completed'])
        self.assert_protected()

    def test_ordinary_feature_completes_with_only_real_static_check(self):
        resolved = self.resolve()
        ctx = resolved['execution_context']
        (self.root / 'app.py').write_text('button = True\n')
        static = self.cli('entry_context.py','static','--execution-context',ctx,'--input','app.py','--',
            sys.executable,'-B','-c','import ast; ast.parse(open("app.py").read())')
        done = self.cli('entry_context.py','complete','--execution-context',ctx,'--static-evidence',static['evidence_file'])
        self.assertTrue(done['completed'])
        for action in ('related-test','review','full-cvl','docs-audit','full-regression','migration-rehearsal','deployment-tool-development'):
            self.assertEqual(done['checks'][action], 'NOT_REQUESTED')
        self.assertFalse(Path(ctx).with_name('scope.json').exists())
        self.assert_protected()

    def test_explicit_commit_grant_keeps_gate_without_extra_tests(self):
        resolved = self.resolve(grants=['commit'])
        out = self.cli('commit_gate.py','--quiet','--context','aidp-command',
                       '--execution-context',resolved['execution_context'])
        self.assertFalse(out['offchain']['actions']['unit_test'])
        self.assertFalse(out['offchain']['deploy'])
        self.assert_protected()

    def test_actual_five_entry_fences_preserve_context_without_sprint_artifacts(self):
        context = ''
        for name in ('sprint-dev', 'sprint-start', 'sprint-test', 'sprint-bugfix', 'sprint-dev', 'sprint-close'):
            text = (SCRIPTS.parent / 'commands' / (name + '.md')).read_text()
            block = re.search(r'```bash\n(.*?)\n```', text, re.S).group(1)
            self.assertIn('entry_context.py resolve', block)
            block = block.replace('{{AIDP_HOME}}', str(SCRIPTS.parent)).replace('{version}', 'V1')
            run = subprocess.run(['bash', '-e', '-c', block], cwd=self.root,
                env=dict(os.environ, EXECUTION_CONTEXT=context, EXPLICIT_SPRINT=''), capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            route = json.loads(run.stdout.strip().splitlines()[-1])
            self.assertEqual(route['route'], 'light')
            if context:
                self.assertEqual(route['execution_context'], context)
            context = route['execution_context']
        self.assert_protected()

    def test_actual_entry_fence_explicit_sprint_preserves_formal_gate(self):
        text = (SCRIPTS.parent / 'commands/sprint-start.md').read_text()
        block = re.search(r'```bash\n(.*?)\n```', text, re.S).group(1)
        block = block.replace('{{AIDP_HOME}}', str(SCRIPTS.parent)).replace('{version}', 'V1')
        run = subprocess.run(['bash', '-e', '-c', block], cwd=self.root,
            env=dict(os.environ, EXECUTION_CONTEXT='', EXPLICIT_SPRINT='008'), capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual(json.loads(run.stdout.strip().splitlines()[-1])['route'], 'formal')
        self.assert_protected()

    def test_commit_gate_keeps_light_identity_inside_command(self):
        ctx = self.resolve()['execution_context']
        result = self.cli('commit_gate.py','--quiet','--context','aidp-command','--execution-context',ctx, expected=5)
        self.assertTrue(result['offchain']['applies'])
        self.assertEqual(result['execution_context']['mode'], 'light')
        self.assertFalse(result['offchain']['actions']['sprint_archive'])
        self.assert_protected()

    def test_light_case_prepare_does_not_create_unaffected_family_ledgers(self):
        ctx = self.resolve()['execution_context']
        result = self.cli('check_case_ledger_pending.py','--version','V1','--execution-context',ctx,
                          '--prepare','--reason','只检查实际影响')
        self.assertFalse(result['required'])
        requested = self.cli('check_case_ledger_pending.py','--version','V1','--execution-context',ctx,
                             '--prepare','--require','--reason','显式实测')
        self.assertTrue(requested['required'])
        self.assertEqual(requested['status'], 'required')
        self.assertEqual(list(self.root.glob('docs/**/_开发期*增量.md')), [])
        self.assert_protected()

    def test_explicit_sprint_and_formal_entry_keep_original_identity(self):
        for entry, extra in [('sprint-dev', {'sprint':'008'}), ('sprint-full', {}), ('sprint-autopilot', {})]:
            with self.subTest(entry=entry):
                resolved = self.resolve(entry, **extra)
                self.assertEqual(resolved['identity']['mode'],'formal')
                self.cli('entry_context.py','complete','--execution-context',resolved['execution_context'],expected=2)
        self.assert_protected()


class PrereleaseContextFlowTests(unittest.TestCase):
    """执行文档中的真实 Bash，覆盖仅准发布及同版尾段的合法选版。"""

    setUp = LightTaskFlowTests.setUp
    git = LightTaskFlowTests.git
    cli = LightTaskFlowTests.cli

    def phase_fence(self):
        text = (SCRIPTS.parent / 'flows/sprint-autopilot/phase-2.md').read_text()
        blocks = re.findall(r'^[ \t]*```bash\n(.*?)\n[ \t]*```[ \t]*$', text, re.S | re.M)
        return next(block for block in blocks if 'entry_context.py fork-version' in block)

    def prepare_selection(self, target, explicit=True, persistent=False):
        previous = 'V1.0.0'
        source = {'kind': 'explicit-command', 'request_id': 'current-prerelease-request',
                  'command': '/sprint-autopilot'}
        if persistent:
            source.update(persistent=True, text='持续处理后续版本，每版沿用已授权开发交付流程')
        args = ['resolve', '--entry', 'sprint-autopilot', '--version', target or previous]
        if explicit:
            args += ['--authorization-source', json.dumps(source)]
        root_ctx = self.cli('entry_context.py', *args)
        historical = self.cli('entry_context.py', 'resolve', '--entry', 'version',
                              '--version', previous)['execution_context']
        baseline_path = self.root / 'memory/.sprint-autopilot-baseline.json'
        baseline = json.loads(baseline_path.read_text())
        baseline.setdefault('autopilot', {})['execution_context'] = root_ctx['execution_context']
        baseline['versions'][previous] = {'execution_context': historical}
        if target and target != previous:
            baseline['versions'][target] = {'execution_context': root_ctx['execution_context']}
        baseline_path.write_text(json.dumps(baseline))
        for name, value in [('TARGET_VERSION', target), ('PRE_RELEASE_VERSION', previous)]:
            proc = subprocess.run([sys.executable, str(SCRIPTS / 'autopilot_tick_flags.py'),
                'set', '--command', 'autopilot', name, value], cwd=self.root,
                capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return root_ctx, historical

    def run_phase_fence(self):
        block = self.phase_fence().replace('{{AIDP_HOME}}', str(SCRIPTS.parent))
        return subprocess.run(['bash', '-e', '-c', block], cwd=self.root,
                              capture_output=True, text=True)

    def assert_selection_reaches_release(self, target):
        parent, historical = self.prepare_selection(target)
        proc = self.run_phase_fence()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        child_path = proc.stdout.strip().splitlines()[-1]
        child = json.loads(Path(child_path).read_text())
        self.assertEqual(child['version'], 'V1.0.0')
        self.assertEqual(child['parent_task_id'], parent['identity']['task_id'])
        self.assertEqual(child['task_scope']['kind'], 'release')
        self.assertEqual(set(child['allowed_actions']),
                         {'document', 'static', 'docs-audit', 'commit', 'push'})
        baseline = json.loads((self.root / 'memory/.sprint-autopilot-baseline.json').read_text())
        self.assertEqual(baseline['versions']['V1.0.0']['execution_context'], historical)
        shell = subprocess.run([sys.executable, str(SCRIPTS / 'autopilot_tick_flags.py'),
            '--command', 'autopilot', '--shell'], cwd=self.root, capture_output=True, text=True)
        self.assertEqual(shell.returncode, 0, shell.stderr)
        selected = subprocess.run(['bash', '-c', shell.stdout + '\nprintf "%s" "$TARGET_VERSION"'],
                                  cwd=self.root, capture_output=True, text=True)
        self.assertEqual(selected.stdout, target)
        self.assertEqual(self.run_phase_fence().stdout.strip().splitlines()[-1], child_path)
        reserve = subprocess.run([sys.executable, str(SCRIPTS / 'execution_policy.py'),
            'reserve-budget', '--root', str(self.root), '--execution-context', child_path,
            '--action', 'document', '--resource', 'agents', '--cost', '1',
            '--input-hash', hashlib.sha256((self.root / 'app.py').read_bytes()).hexdigest()], capture_output=True, text=True)
        self.assertEqual(reserve.returncode, 0, reserve.stdout + reserve.stderr)
        budget = json.loads(Path(parent['execution_context']).with_name('budget.json').read_text())
        self.assertEqual(budget['used']['agents'], 1)
        self.assertFalse(Path(child_path).with_name('budget.json').exists())

    def test_actual_autopilot_entry_pre_only_creates_authorized_current_root(self):
        parent, historical = self.prepare_selection('')
        baseline_path = self.root / 'memory/.sprint-autopilot-baseline.json'
        baseline = json.loads(baseline_path.read_text())
        baseline['autopilot'].pop('execution_context')
        baseline_path.write_text(json.dumps(baseline))
        text = (SCRIPTS.parent / 'commands/sprint-autopilot.md').read_text()
        block = re.search(r'```bash\n(.*?)\n```', text, re.S).group(1)
        block = block.replace('{{AIDP_HOME}}', str(SCRIPTS.parent))
        source = json.dumps({'kind': 'explicit-command', 'request_id': 'fresh-pre-only',
                             'command': '/sprint-autopilot'})
        def execute():
            proc = subprocess.run(['bash', '-e', '-c',
                'POLICY_ARGS=(--authorization-source "$SOURCE_JSON")\n' + block], cwd=self.root,
                env=dict(os.environ, SOURCE_JSON=source, EXECUTION_CONTEXT=''), capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            return json.loads(proc.stdout.strip().splitlines()[-1])
        resolved = execute()
        current = json.loads(Path(resolved['execution_context']).read_text())
        self.assertEqual(current['version'], 'V1.0.0')
        self.assertIn('document', current['allowed_actions'])
        self.assertNotEqual(resolved['execution_context'], historical)
        self.assertEqual(execute()['execution_context'], resolved['execution_context'])
        baseline = json.loads(baseline_path.read_text())
        self.assertEqual(baseline['autopilot']['execution_context'], resolved['execution_context'])
        self.assertEqual(baseline['versions']['V1.0.0']['execution_context'], historical)
        self.assertEqual(baseline['versions']['V1.0.0']['autopilot_root_context'], resolved['execution_context'])
        self.assertNotEqual(resolved['execution_context'], parent['execution_context'])

    def test_actual_autopilot_target_switch_returns_to_existing_version_budget(self):
        parent, _ = self.prepare_selection('V1.1.0', persistent=True)
        reserve = subprocess.run([sys.executable, str(SCRIPTS / 'execution_policy.py'),
            'reserve-budget', '--root', str(self.root), '--execution-context', parent['execution_context'],
            '--action', 'document', '--resource', 'agents', '--cost', '1',
            '--input-hash', hashlib.sha256((self.root / 'app.py').read_bytes()).hexdigest()], capture_output=True, text=True)
        self.assertEqual(reserve.returncode, 0, reserve.stdout + reserve.stderr)
        text = (SCRIPTS.parent / 'commands/sprint-autopilot.md').read_text()
        block = re.search(r'```bash\n(.*?)\n```', text, re.S).group(1).replace('{{AIDP_HOME}}', str(SCRIPTS.parent))
        def select_and_run(version):
            subprocess.run([sys.executable, str(SCRIPTS / 'autopilot_tick_flags.py'), 'set',
                '--command', 'autopilot', 'TARGET_VERSION', version], cwd=self.root, check=True, capture_output=True)
            proc = subprocess.run(['bash', '-e', '-c',
                'POLICY_ARGS=()\n' + block], cwd=self.root,
                env=dict(os.environ, EXECUTION_CONTEXT=''), capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            return json.loads(proc.stdout.strip().splitlines()[-1])['execution_context']
        newer = select_and_run('V1.2.0')
        self.assertNotEqual(newer, parent['execution_context'])
        old = select_and_run('V1.1.0')
        self.assertEqual(old, parent['execution_context'])
        budget = json.loads(Path(old).with_name('budget.json').read_text())
        self.assertEqual(budget['used']['agents'], 1)

    def test_actual_autopilot_once_root_resumes_same_version_without_new_grant(self):
        source = {'kind': 'explicit-command', 'request_id': 'active-once-root',
                  'command': '/sprint-autopilot', 'options': ['--once']}
        parent = self.cli('entry_context.py', 'resolve-autopilot-root', '--version', 'V1.1.0',
                          '--authorization-source', json.dumps(source))
        baseline_path = self.root / 'memory/.sprint-autopilot-baseline.json'
        baseline = json.loads(baseline_path.read_text())
        baseline.setdefault('autopilot', {})['execution_context'] = parent['execution_context']
        baseline['versions']['V1.1.0'] = {'execution_context': parent['execution_context']}
        baseline_path.write_text(json.dumps(baseline))
        subprocess.run([sys.executable, str(SCRIPTS / 'autopilot_tick_flags.py'), 'set', '--command',
            'autopilot', 'TARGET_VERSION', 'V1.1.0'], cwd=self.root, capture_output=True, check=True)
        text = (SCRIPTS.parent / 'commands/sprint-autopilot.md').read_text()
        block = re.search(r'```bash\n(.*?)\n```', text, re.S).group(1).replace('{{AIDP_HOME}}', str(SCRIPTS.parent))
        proc = subprocess.run(['bash', '-e', '-c', 'POLICY_ARGS=()\n' + block], cwd=self.root,
            env=dict(os.environ, EXECUTION_CONTEXT=parent['execution_context']), capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(json.loads(proc.stdout.strip().splitlines()[-1])['execution_context'], parent['execution_context'])

    def test_actual_same_version_skip_narrows_root_without_resetting_used(self):
        source = {'kind': 'explicit-command', 'request_id': 'initial-full-root', 'command': '/sprint-autopilot'}
        parent = self.cli('entry_context.py', 'resolve-autopilot-root', '--version', 'V1.1.0',
                          '--authorization-source', json.dumps(source))
        baseline_path = self.root / 'memory/.sprint-autopilot-baseline.json'
        baseline = json.loads(baseline_path.read_text())
        baseline.setdefault('autopilot', {})['execution_context'] = parent['execution_context']
        baseline['versions']['V1.1.0'] = {'autopilot_root_context': parent['execution_context']}
        baseline_path.write_text(json.dumps(baseline))
        subprocess.run([sys.executable, str(SCRIPTS / 'autopilot_tick_flags.py'), 'set', '--command',
            'autopilot', 'TARGET_VERSION', 'V1.1.0'], cwd=self.root, capture_output=True, check=True)
        reserve = subprocess.run([sys.executable, str(SCRIPTS / 'execution_policy.py'), 'reserve-budget',
            '--root', str(self.root), '--execution-context', parent['execution_context'], '--action', 'document',
            '--resource', 'agents', '--cost', '1', '--input-hash',
            hashlib.sha256((self.root / 'app.py').read_bytes()).hexdigest()], capture_output=True, text=True)
        self.assertEqual(reserve.returncode, 0, reserve.stdout + reserve.stderr)
        text = (SCRIPTS.parent / 'commands/sprint-autopilot.md').read_text()
        block = re.search(r'```bash\n(.*?)\n```', text, re.S).group(1).replace('{{AIDP_HOME}}', str(SCRIPTS.parent))
        source = dict(source, request_id='now-skip-tests', options=['--skip-aiauto-test'])
        proc = subprocess.run(['bash', '-e', '-c',
            'POLICY_ARGS=(--authorization-source "$SOURCE_JSON")\n' + block], cwd=self.root,
            env=dict(os.environ, EXECUTION_CONTEXT='', SOURCE_JSON=json.dumps(source)), capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        result = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertEqual(result['execution_context'], parent['execution_context'])
        self.assertFalse({'live-tests', 'full-regression'} & set(result['authorized_actions']))
        self.assertEqual(json.loads(Path(parent['execution_context']).with_name('budget.json').read_text())['used']['agents'], 1)

    def test_actual_phase2_pre_only_reaches_release_without_next_version(self):
        self.assert_selection_reaches_release('')

    def test_actual_phase2_same_version_tail_reaches_release(self):
        self.assert_selection_reaches_release('V1.0.0')

    def test_actual_phase2_two_versions_preserves_historical_context(self):
        self.assert_selection_reaches_release('V1.1.0')

    def assert_sprint_dispatch_keeps_delivery_on_parent(self, relative):
        parent, _ = self.prepare_selection('V1.1.0')
        baseline_path = self.root / 'memory/.sprint-autopilot-baseline.json'
        baseline = json.loads(baseline_path.read_text())
        baseline['versions']['V1.1.0']['run_state'] = {'next_sprint': '008'}
        baseline_path.write_text(json.dumps(baseline))
        text = (SCRIPTS.parent / relative).read_text()
        blocks = re.findall(r'^[ \t]*```bash\n(.*?)\n[ \t]*```[ \t]*$', text, re.S | re.M)
        block = next(block for block in blocks if 'entry_context.py fork --root' in block)
        block = block.replace('{{AIDP_HOME}}', str(SCRIPTS.parent)).replace('{NNN}', '008')
        proc = subprocess.run(['bash', '-e', '-c', block + '\nprintf "%s" "$SPRINT_EXECUTION_CONTEXT"'],
            cwd=self.root, env=dict(os.environ, EXECUTION_CONTEXT=parent['execution_context']),
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        child = json.loads(Path(proc.stdout.strip().splitlines()[-1]).read_text())
        self.assertEqual(set(child['allowed_actions']),
            {'implement', 'static', 'document', 'related-test', 'review', 'full-cvl', 'docs-audit'})
        self.assertEqual(child['parent_task_id'], parent['identity']['task_id'])
        root = json.loads(Path(parent['execution_context']).read_text())
        self.assertTrue({'commit', 'push', 'deploy', 'live-tests', 'full-regression'} <= set(root['allowed_actions']))
        self.assertEqual(child['execution_budget'], root['execution_budget'])

    def test_actual_batch_sprint_dispatch_excludes_parent_delivery_actions(self):
        self.assert_sprint_dispatch_keeps_delivery_on_parent('commands/sprint-batch.md')

    def test_actual_autopilot_sprint_dispatch_excludes_parent_delivery_actions(self):
        self.assert_sprint_dispatch_keeps_delivery_on_parent('flows/sprint-autopilot/phase-3-5.md')

    def test_actual_incremental_dev_fork_narrows_without_breaking_bind(self):
        parent, _ = self.prepare_selection('V1.1.0')
        full = self.cli('entry_context.py', 'resolve', '--entry', 'sprint-full', '--version', 'V1.1.0',
            '--authorization-source', json.dumps({'kind': 'explicit-command', 'request_id': 'one-full',
                                                'command': '/sprint-full'}))
        text = (SCRIPTS.parent / 'commands/sprint-dev.md').read_text()
        blocks = re.findall(r'^[ \t]*```bash\n(.*?)\n[ \t]*```[ \t]*$', text, re.S | re.M)
        block = next(block for block in blocks if 'CONTEXT_OPERATION=fork' in block)
        block = block.replace('{{AIDP_HOME}}', str(SCRIPTS.parent))
        for source in (parent, full):
            with self.subTest(entry=source['identity']['entry']):
                proc = subprocess.run(['bash', '-e', '-c', block + '\nprintf "%s" "$EXECUTION_CONTEXT"'],
                    cwd=self.root, env=dict(os.environ, EXECUTION_CONTEXT=source['execution_context'], NEXT='008'),
                    capture_output=True, text=True)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                child = json.loads(Path(proc.stdout.strip().splitlines()[-1]).read_text())
                self.assertEqual(child['sprint'], '008')
                self.assertFalse({'commit', 'push', 'deploy', 'live-tests', 'full-regression'} & set(child['allowed_actions']))
                if source is full:
                    self.assertEqual(child['task_id'], full['identity']['task_id'])

    def test_actual_policy_fence_settles_short_work_against_long_reservation(self):
        import hashlib
        parent, _ = self.prepare_selection('V1.1.0')
        text = (SCRIPTS.parent / 'flows/sprint-dev/light-context.md').read_text()
        blocks = re.findall(r'^[ \t]*```bash\n(.*?)\n[ \t]*```[ \t]*$', text, re.S | re.M)
        block = next(block for block in blocks if 'execution_policy.py reserve-budget' in block)
        marker = '# 实际动作结束后据真实结果登记；不是用登记替代执行。'
        self.assertIn(marker, block)
        actual_work = "ACTUAL_SECONDS=$(python3 -c 'import time;t=time.monotonic();time.sleep(0.02);print(time.monotonic()-t)')"
        block = block.replace(marker, actual_work + '\n' + marker).replace('{{AIDP_HOME}}', str(SCRIPTS.parent))
        digest = hashlib.sha256((self.root / 'app.py').read_bytes()).hexdigest()
        proc = subprocess.run(['bash', '-e', '-c', block], cwd=self.root, capture_output=True, text=True,
            env=dict(os.environ, EXECUTION_CONTEXT=parent['execution_context'], ACTION='document',
                     RESOURCE='elapsed_seconds', COST='7200', INPUT_HASH=digest, STATUS='PASS',
                     EVIDENCE_JSON='{"source":"fixture timed tool completed"}'))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        budget = json.loads(Path(parent['execution_context']).with_name('budget.json').read_text())
        self.assertGreater(budget['used']['elapsed_seconds'], 0)
        self.assertLess(budget['used']['elapsed_seconds'], 1)
        self.assertTrue(budget['outcomes'])

    def test_actual_phase2_missing_current_grant_cannot_borrow_history(self):
        parent, historical = self.prepare_selection('', explicit=False)
        before = set((self.root / 'memory/.aidp/entry-contexts').glob('*/context.json'))
        proc = self.run_phase_fence()
        self.assertNotEqual(proc.returncode, 0)
        after = set((self.root / 'memory/.aidp/entry-contexts').glob('*/context.json'))
        self.assertEqual(before, after)
        self.assertNotEqual(parent['execution_context'], historical)


class ScheduledAiautoContextFlowTests(unittest.TestCase):
    """使用scheduler真实argv与agent_loop执行入口围栏，LLM进程仅替换为围栏驱动。"""

    setUp = LightTaskFlowTests.setUp
    git = LightTaskFlowTests.git
    cli = LightTaskFlowTests.cli
    prepare_selection = PrereleaseContextFlowTests.prepare_selection

    def prepare_build(self, skip=False):
        parent, _ = self.prepare_selection('V1.1.0')
        if skip:
            parent = self.cli('entry_context.py', 'resolve', '--entry', 'sprint-autopilot',
                '--version', 'V1.1.0', '--authorization-source', json.dumps({
                    'kind': 'explicit-command', 'request_id': 'skip-browser-request',
                    'command': '/sprint-autopilot', 'options': ['--skip-aiauto-test']}))
        baseline_path = self.root / 'memory/.sprint-autopilot-baseline.json'
        baseline = json.loads(baseline_path.read_text())
        baseline['autopilot']['execution_context'] = parent['execution_context']
        baseline['versions']['V1.1.0'].update(execution_context=parent['execution_context'],
            phase_beta_done_at='2026-01-01T00:00:00Z', last_deployed_at='2026-01-01T00:00:00Z',
            current_build='V1.1.0_build1001', builds=[{'build': 'V1.1.0_build1001',
                'push_commit': self.git('rev-parse', 'HEAD')}])
        baseline_path.write_text(json.dumps(baseline))
        return parent

    def entry_block(self):
        text = (SCRIPTS.parent / 'commands/sprint-aiauto-test.md').read_text()
        block = re.search(r'```bash\n(.*?)\n```', text, re.S).group(1)
        return block.replace('{{AIDP_HOME}}', str(getattr(self, 'runtime', SCRIPTS.parent))).replace('{version}', 'V1.1.0')

    def run_scheduled_entry(self):
        # 本机env文件可覆盖执行模板；不允许夹具意外调用真实模型/外部通知。
        if (Path.home() / '.config/aidp/env').is_file():
            self.skipTest('本机存在调度凭据文件，不让集成夹具载入用户环境')
        import shlex
        import shutil
        self.runtime = self.root / '.agents'
        if not self.runtime.exists():
            shutil.copytree(SCRIPTS, self.runtime / 'scripts', ignore=shutil.ignore_patterns('tests', '__pycache__'))
        runner = self.root / 'fixture-aiauto-entry.sh'
        output = self.root / 'fixture-aiauto-output.txt'
        runner.write_text('#!/bin/bash\nset -e\nexec > ' + shlex.quote(str(output)) + '\n' + self.entry_block())
        env = dict(os.environ, AIDP_PROJECT_ROOT=str(self.root), AIDP_HOME=str(self.runtime),
                   AIDP_AGENT='claude', AIDP_AGENT_EXEC='bash ' + shlex.quote(str(runner)) + ' {prompt}',
                   EXECUTION_CONTEXT='')
        argv = subprocess.run([sys.executable, '-c',
            'import json,sys;sys.path.insert(0,sys.argv[1]);from aidp_scheduler import chain_argv;'
            'print(json.dumps(chain_argv(sys.argv[2],"test")))', str(self.runtime / 'scripts'), str(self.root)],
            cwd=self.root, env=env, capture_output=True, text=True, check=True)
        proc = subprocess.run(json.loads(argv.stdout), cwd=self.root, env=env,
                              text=True, capture_output=True, timeout=45)
        log = self.root / 'memory/.aidp/logs/sprint-aiauto-test.log'
        detail = proc.stdout + proc.stderr + (log.read_text() if log.is_file() else '')
        self.assertEqual(proc.returncode, 0, detail)
        self.assertTrue(output.is_file())
        return output.read_text()

    def test_natural_browser_entry_stays_light_despite_deployed_build(self):
        self.prepare_build()
        source = json.dumps({'kind': 'user-text', 'request_id': 'one-page-only',
                             'text': '只查看当前页面，不做全量回归'})
        proc = subprocess.run(['bash', '-e', '-c',
            'POLICY_ARGS=(--task-scope test --grant live-tests --authorization-source "$SOURCE_JSON")\n' + self.entry_block()],
            cwd=self.root, env=dict(os.environ, SOURCE_JSON=source, EXECUTION_CONTEXT='', AIDP_TICK_COMMAND=''),
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        route = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertEqual(route['route'], 'light')
        self.assertEqual(set(route['authorized_actions']), {'static', 'live-tests'})

    def test_actual_scheduler_same_build_reuses_formal_context_and_root_budget(self):
        parent = self.prepare_build()
        first = json.loads(self.run_scheduled_entry().strip().splitlines()[-1])
        self.assertEqual(first['route'], 'formal')
        self.assertEqual(set(first['authorized_actions']), {'static', 'live-tests', 'full-regression'})
        child_path = first['execution_context']
        reserve = subprocess.run([sys.executable, str(SCRIPTS / 'execution_policy.py'),
            'reserve-budget', '--root', str(self.root), '--execution-context', child_path,
            '--action', 'full-regression', '--resource', 'agents', '--cost', '1',
            '--input-hash', hashlib.sha256((self.root / 'app.py').read_bytes()).hexdigest()], capture_output=True, text=True)
        self.assertEqual(reserve.returncode, 0, reserve.stdout + reserve.stderr)
        second = json.loads(self.run_scheduled_entry().strip().splitlines()[-1])
        self.assertEqual(second['execution_context'], child_path)
        budget = json.loads(Path(parent['execution_context']).with_name('budget.json').read_text())
        self.assertEqual(budget['used']['agents'], 1)
        self.assertFalse(Path(child_path).with_name('budget.json').exists())

    def assert_pinned_build_drift(self, wake_source):
        parent = self.prepare_build()
        child = self.cli('entry_context.py', 'fork-test-build', '--execution-context', parent['execution_context'],
            '--version', 'V1.1.0', '--build-id', 'V1.1.0_build1001')
        baseline_path = self.root / 'memory/.sprint-autopilot-baseline.json'
        baseline = json.loads(baseline_path.read_text())
        baseline['versions']['V1.1.0']['current_build'] = 'V1.1.0_build1002'
        baseline['versions']['V1.1.0']['builds'].append({'build': 'V1.1.0_build1002',
            'push_commit': self.git('rev-parse', 'HEAD')})
        baseline_path.write_text(json.dumps(baseline))
        subprocess.run([sys.executable, str(SCRIPTS / 'autopilot_tick_flags.py'), 'set',
            '--command', 'aiauto-test', 'HAS_WAKE_SOURCE', str(wake_source)], cwd=self.root, check=True, capture_output=True)
        text = (SCRIPTS.parent / 'flows/sprint-aiauto-test/phase-0-6.md').read_text()
        block = re.search(r'```bash\n(.*?)\n```', text, re.S).group(1).replace('{{AIDP_HOME}}', str(SCRIPTS.parent))
        proc = subprocess.run(['bash', '-e', '-c', block], cwd=self.root,
            env=dict(os.environ, EXECUTION_CONTEXT=child['execution_context']), capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0 if wake_source else 2, proc.stdout + proc.stderr)
        self.assertIn('BUILD_CHANGED', proc.stdout)
        self.assertNotIn('NEED_HANDOFF=1', proc.stdout)

    def test_actual_baseline_flow_refuses_retargeting_pinned_test_build(self):
        self.assert_pinned_build_drift(1)

    def test_manual_build_drift_returns_incomplete_without_imaginary_next_tick(self):
        self.assert_pinned_build_drift(0)

    def test_idle_scheduled_tick_keeps_real_watchdog_healthy(self):
        from datetime import datetime, timedelta, timezone
        from types import SimpleNamespace
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        from aidp_scheduler import do_watchdog
        flags = SimpleNamespace(scheduled=True)
        do_watchdog(str(self.root), flags,
                    now=datetime.now(timezone.utc) - timedelta(seconds=1300), send_notify=False)
        self.assertIn('NO_TARGET', self.run_scheduled_entry())
        _, result = do_watchdog(str(self.root), flags, now=datetime.now(timezone.utc), send_notify=False)
        self.assertEqual(result['chains']['test']['state'], 'fresh')
        self.assertNotIn('test', result['alerted'])

    def test_scheduler_uses_current_pre_only_root_instead_of_historical_planning(self):
        parent, historical = self.prepare_selection('')
        baseline_path = self.root / 'memory/.sprint-autopilot-baseline.json'
        baseline = json.loads(baseline_path.read_text())
        baseline['versions']['V1.0.0'].update(phase_beta_done_at='2026-01-01T00:00:00Z',
            last_deployed_at='2026-01-01T00:00:00Z', current_build='V1.0.0_build1001',
            builds=[{'build': 'V1.0.0_build1001', 'push_commit': self.git('rev-parse', 'HEAD')}])
        baseline_path.write_text(json.dumps(baseline))
        output = self.run_scheduled_entry().strip().splitlines()[-1]
        self.assertTrue(output.startswith('{'), output)
        route = json.loads(output)
        self.assertEqual(route['route'], 'formal')
        child = json.loads(Path(route['execution_context']).read_text())
        self.assertEqual(child['parent_task_id'], parent['identity']['task_id'])
        self.assertEqual(child['version'], 'V1.0.0')
        baseline = json.loads(baseline_path.read_text())
        self.assertEqual(baseline['versions']['V1.0.0']['execution_context'], historical)

    def test_pre_only_test_root_remains_discoverable_after_global_target_advances(self):
        parent, historical = self.prepare_selection('')
        newer = self.cli('entry_context.py', 'resolve-autopilot-root', '--version', 'V1.1.0',
            '--authorization-source', json.dumps({'kind': 'explicit-command', 'request_id': 'next-version',
                                                 'command': '/sprint-autopilot'}))
        baseline_path = self.root / 'memory/.sprint-autopilot-baseline.json'
        baseline = json.loads(baseline_path.read_text())
        baseline['autopilot']['execution_context'] = newer['execution_context']
        baseline['versions']['V1.0.0'].update(autopilot_root_context=parent['execution_context'],
            phase_beta_done_at='2026-01-01T00:00:00Z', last_deployed_at='2026-01-01T00:00:00Z',
            current_build='V1.0.0_build1001', builds=[{'build': 'V1.0.0_build1001',
                'push_commit': self.git('rev-parse', 'HEAD')}])
        baseline_path.write_text(json.dumps(baseline))
        output = self.run_scheduled_entry().strip().splitlines()[-1]
        self.assertTrue(output.startswith('{'), output)
        route = json.loads(output)
        child = json.loads(Path(route['execution_context']).read_text())
        self.assertEqual(child['parent_task_id'], parent['identity']['task_id'])
        baseline = json.loads(baseline_path.read_text())
        self.assertEqual(baseline['versions']['V1.0.0']['execution_context'], historical)

    def test_current_skip_root_cannot_fall_back_to_older_wider_version_root(self):
        old = self.prepare_build()
        current = self.cli('entry_context.py', 'resolve', '--entry', 'sprint-autopilot',
            '--version', 'V1.1.0', '--authorization-source', json.dumps({
                'kind': 'explicit-command', 'request_id': 'current-skip-tests',
                'command': '/sprint-autopilot', 'options': ['--skip-aiauto-test']}))
        baseline_path = self.root / 'memory/.sprint-autopilot-baseline.json'
        baseline = json.loads(baseline_path.read_text())
        baseline['autopilot']['execution_context'] = current['execution_context']
        self.assertEqual(baseline['versions']['V1.1.0']['execution_context'], old['execution_context'])
        baseline_path.write_text(json.dumps(baseline))
        before = set((self.root / 'memory/.aidp/entry-contexts').glob('*/context.json'))
        self.assertIn('NOT_REQUESTED', self.run_scheduled_entry())
        self.assertEqual(before, set((self.root / 'memory/.aidp/entry-contexts').glob('*/context.json')))

    def test_actual_scheduler_no_deployed_target_creates_no_task(self):
        before = set((self.root / 'memory/.aidp/entry-contexts').glob('*/context.json'))
        output = self.run_scheduled_entry()
        self.assertIn('NO_TARGET', output)
        self.assertEqual(before, set((self.root / 'memory/.aidp/entry-contexts').glob('*/context.json')))

    def test_actual_scheduler_explicit_skip_cannot_gain_test_bundle(self):
        self.prepare_build(skip=True)
        before = set((self.root / 'memory/.aidp/entry-contexts').glob('*/context.json'))
        output = self.run_scheduled_entry()
        self.assertIn('NOT_REQUESTED', output)
        self.assertEqual(before, set((self.root / 'memory/.aidp/entry-contexts').glob('*/context.json')))


if __name__ == '__main__':
    unittest.main()
