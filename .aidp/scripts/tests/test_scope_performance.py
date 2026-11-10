#!/usr/bin/env python3
"""范围性能与真实变化专项：临时 Git/子模块、真实进程、锁后失效及预算。"""
from contextlib import contextmanager
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import test_scope as scope
import test_ledger as ledger
from project_inventory import git_worktree_inventory, default_excluded, InventoryError


def git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True, check=True).stdout.strip()


class ScopePerformanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='aidp-scope-performance-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'repo'
        self.root.mkdir()
        self.init(self.root)
        self.write('.gitignore', '__pycache__/\nmemory/.aidp/\n')
        self.write('src/app.py', 'value = 1\n')
        self.write('tests/__init__.py', '')
        self.write('tests/test_app.py', 'import unittest\nfrom src.app import value\nclass App(unittest.TestCase):\n def test_app(self): self.assertGreater(value, 0)\n')
        git(self.root, 'add', '-A'); git(self.root, 'commit', '-qm', 'base')
        self.base = git(self.root, 'rev-parse', 'HEAD')
        self.runners = [{'suffixes': ['.py'], 'argv': [sys.executable, '-B', '-m', 'unittest', '{tests}']}]

    def init(self, root):
        git(root, 'init', '-q'); git(root, 'config', 'user.name', 'test')
        git(root, 'config', 'user.email', 'test@example.invalid')

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        return target

    def plan(self, runners=None, context=None):
        plan = scope.derive(self.root, '' if context else self.base, runners or self.runners,
                            execution_context=context)
        path = self.write('memory/.aidp/scope.json', json.dumps(plan))
        return path, plan

    def context(self, grants=('related-test',), budget=None):
        import entry_context
        return entry_context.resolve_context(self.root, 'sprint-dev', version='V1',
            additional_grants=list(grants), execution_budget=budget,
            authorization_source={'kind': 'user-text', 'request_id': 'performance-test', 'text': '仅运行授权专项测试'})['execution_context']

    def module(self):
        other = Path(self.tmp.name) / 'other'
        other.mkdir(); self.init(other)
        (other / 'src').mkdir(); (other / 'tests').mkdir()
        (other / 'src/lib.py').write_text('value = 1\n')
        (other / 'tests/test_lib.py').write_text('pass\n')
        (other / 'docs').mkdir(); (other / 'docs/state.json').write_text('{}\n')
        git(other, 'add', '-A'); git(other, 'commit', '-qm', 'module')
        git(self.root, '-c', 'protocol.file.allow=always', 'submodule', 'add', '-q', str(other), 'backend')
        git(self.root, 'commit', '-qam', 'add-module')
        self.base = git(self.root, 'rev-parse', 'HEAD')
        return self.root / 'backend'

    def test_batch_and_frozen_analysis_have_bounded_calls(self):
        for i in range(12):
            self.write(f'src/m{i}.py', 'value = 2\n')
            self.write(f'tests/test_m{i}.py', f'import unittest\nfrom src.m{i} import value\nclass T(unittest.TestCase):\n def test_value(self): self.assertEqual(value, 2)\n')
        with patch.object(scope, 'derive', wraps=scope.derive) as derive, patch.object(scope, 'dependency_analysis', wraps=scope.dependency_analysis) as analysis:
            path, plan = self.plan()
            out, code = ledger.run_scope(self.root, path, 'fixture')
        self.assertEqual(code, 0); self.assertEqual(out['status'], 'PASS')
        self.assertEqual(len(plan['tests']), 12)
        self.assertEqual(len(plan['runs']), 1)
        self.assertEqual(derive.call_count, 2)
        self.assertEqual(analysis.call_count, 1)
        raw = [json.loads(line) for line in Path(ledger.ledger_path(self.root)).read_text().splitlines()]
        self.assertEqual(sum(row['kind'] == 'plan' for row in raw), 1)
        self.assertFalse(any('plan' in row.get('scope_binding', {}) for row in raw))
        self.assertEqual(ledger.verify_scope(self.root, path, plan['scope_hash'], out['run_ids'], 'fixture')['status'], 'PASS')

    def test_script_runner_remains_per_file_and_plan_stored_once(self):
        for i in range(4):
            self.write(f'tests/test_script{i}.py', 'pass\n')
        path, plan = self.plan([{'suffixes': ['.py'], 'argv': [sys.executable, '-B', '{tests}']}])
        self.assertEqual(len(plan['runs']), 4)
        out, code = ledger.run_scope(self.root, path, 'scripts')
        self.assertEqual(code, 0)
        raw = [json.loads(line) for line in Path(ledger.ledger_path(self.root)).read_text().splitlines()]
        self.assertEqual(sum(r['kind'] == 'plan' for r in raw), 1)
        self.assertEqual(len(out['run_ids']), 4)
        self.assertTrue(all(len(r['selection']['tests']) == 1 for r in out['runs']))

    def test_same_size_and_mtime_change_invalidates_frozen_plan(self):
        self.write('src/app.py', 'value = 2\n')
        path, plan = self.plan()
        source = self.root / 'src/app.py'; before = source.stat()
        source.write_text('value = 3\n'); os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns))
        with self.assertRaises(scope.ScopeError):
            ledger.run_scope(self.root, path, 'fixture')
        self.assertNotEqual(self.plan()[1]['tree_hash'], plan['tree_hash'])

    def test_resource_mapping_and_unmapped_resources_remain_visible(self):
        self.write('config/settings.yaml', 'value: 2\n')
        self.write('config/unmapped.json', '{}\n')
        self.write('db/migrate.sql', 'select 1;\n')
        runners = copy.deepcopy(self.runners)
        runners[0]['resources'] = {'config/settings.yaml': ['src/app.py']}
        _, plan = self.plan(runners)
        self.assertIn('tests/test_app.py', plan['tests'])
        self.assertIn('config/settings.yaml', plan['dependencies']['tests']['tests/test_app.py']['files'])
        self.assertIn('config/unmapped.json', plan['unmapped'])
        self.assertIn('db/migrate.sql', plan['unmapped'])
        self.assertIn('config/unmapped.json', plan['changed'])
        self.assertNotIn('config/settings.yaml', plan['unmapped'])

    def test_unmapped_resource_has_empty_minor_not_pass(self):
        self.write('config/only.json', '{}\n')
        path, plan = self.plan()
        out, code = ledger.run_scope(self.root, path, 'resource')
        self.assertEqual(out['status'], 'EMPTY'); self.assertTrue(out['minor'])
        self.assertEqual(out['run_ids'], []); self.assertEqual(plan['runs'], [])

    def test_submodule_formal_discovery_head_dirty_runtime_and_inputs(self):
        child = self.module()
        before = ledger.tree_snapshot(self.root)
        (child / 'src/lib.py').write_text('value = 2\n')
        _, plan = self.plan([{'cwd': 'backend', 'suffixes': ['.py'], 'argv': [sys.executable, '-B', '{tests}']}])
        self.assertIn('backend/src/lib.py', plan['changed'])
        self.assertIn('backend/tests/test_lib.py', plan['tests'])
        changed = ledger.tree_snapshot(self.root)
        self.assertNotEqual(before['hash'], changed['hash'])
        self.write('backend/memory/.aidp/test-ledger.jsonl', 'runtime\n')
        self.write('backend/.aidp/runtime/scope.json', '{}\n')
        self.write('backend/docs/state.json', '{"new":true}\n')
        self.assertEqual(changed['hash'], ledger.tree_snapshot(self.root)['hash'])
        self.assertNotEqual(ledger.tree_snapshot(self.root, ['backend/docs/state.json'])['hash'], changed['hash'])
        # memory 位于业务包内部，不是仓库边界，必须作为源码指纹。
        self.write('backend/src/memory/value.json', '{}\n')
        self.assertNotEqual(changed['hash'], ledger.tree_snapshot(self.root)['hash'])
        git(child, '-c', 'user.name=test', '-c', 'user.email=t@example.invalid', 'commit', '--allow-empty', '-qm', 'head-only')
        self.assertNotEqual(ledger.tree_snapshot(self.root)['files']['backend/@gitlink'], changed['files']['backend/@gitlink'])

    def test_nested_gitlink_and_missing_checkout_are_fail_closed(self):
        child = self.module()
        leaf = Path(self.tmp.name) / 'leaf'; leaf.mkdir(); self.init(leaf)
        (leaf / 'leaf.py').write_text('x=1\n'); git(leaf, 'add', '-A'); git(leaf, 'commit', '-qm', 'leaf')
        git(child, '-c', 'protocol.file.allow=always', 'submodule', 'add', '-q', str(leaf), 'nested')
        observed = git_worktree_inventory(self.root)
        self.assertIn('backend/nested/leaf.py', observed['files'])
        self.assertIn('backend/nested', observed['gitlinks'])
        git(child, 'submodule', 'deinit', '-f', '--', 'nested')
        with self.assertRaisesRegex(InventoryError, 'UNVERIFIED'):
            ledger.tree_snapshot(self.root)

    def test_runtime_only_write_during_real_process_stays_pass_source_write_does_not(self):
        self.module()
        command = [sys.executable, '-c', "from pathlib import Path; p=Path('backend/memory/.aidp/scope.json'); p.parent.mkdir(parents=True,exist_ok=True); p.write_text('{}')"]
        out, code = ledger.run(self.root, '.', 'targeted', 'runtime', command)
        self.assertEqual(out['status'], 'PASS')
        command = [sys.executable, '-c', "from pathlib import Path; Path('backend/src/lib.py').write_text('value = 3\\n')"]
        out, code = ledger.run(self.root, '.', 'targeted', 'runtime', command)
        self.assertEqual(out['status'], 'TREE_CHANGED'); self.assertNotEqual(code, 0)

    def test_lock_waiter_rechecks_content_before_reuse_or_execution(self):
        self.write('src/app.py', 'value = 2\n')
        path, _ = self.plan()
        first, _ = ledger.run_scope(self.root, path, 'lock')
        key = first['runs'][0]['key']
        marker = self.root / 'memory/waiting'
        code = '''import sys,json
from pathlib import Path
from contextlib import contextmanager
sys.path.insert(0,sys.argv[1]); import test_ledger as ledger
original=ledger.lock
@contextmanager
def observed(root,name):
 if name != 'write': Path(sys.argv[4]).write_text('waiting')
 with original(root,name) as fd: yield fd
ledger.lock=observed
out,status=ledger.run_scope(Path(sys.argv[2]),sys.argv[3],'lock')
print(json.dumps(out)); sys.exit(status)
'''
        with ledger.lock(self.root, key):
            process = subprocess.Popen([sys.executable, '-c', code, str(SCRIPTS), str(self.root), str(path), str(marker)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            deadline = time.monotonic() + 10
            while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertTrue(marker.exists())
            source = self.root / 'src/app.py'; state = source.stat()
            source.write_text('value = 3\n'); os.utime(source, ns=(state.st_atime_ns, state.st_mtime_ns))
        stdout, stderr = process.communicate(timeout=10)
        self.assertEqual(process.returncode, 2, stdout + stderr)
        out = json.loads(stdout.splitlines()[-1])
        self.assertEqual(out['status'], 'UNVERIFIED'); self.assertEqual(out['run_ids'], [])
        self.assertIn('TREE_CHANGED', out['interruption']['reason'])

    def test_tampered_plan_or_reference_checksums_are_rejected_and_legacy_loads(self):
        self.write('src/app.py', 'value = 2\n')
        path, _ = self.plan(); ledger.run_scope(self.root, path, 'fixture')
        location = Path(ledger.ledger_path(self.root))
        raw = [json.loads(line) for line in location.read_text().splitlines()]
        loaded = ledger.load(self.root)
        # 原格式完整计划仍可加载，必须保留其原有 checksum 验证。
        for row in loaded:
            row['checksum'] = ledger.digest({k:v for k,v in row.items() if k != 'checksum'})
        location.write_text(''.join(json.dumps(row)+'\n' for row in loaded))
        self.assertEqual(ledger.load(self.root)[0]['status'], 'PASS')
        for kind in ('plan', 'run'):
            broken = copy.deepcopy(raw)
            row = next(r for r in broken if r['kind'] == kind)
            if kind == 'plan': row['plan']['tests'] = []
            else: row['scope_binding']['item_id'] = '0' * 64
            row['checksum'] = ledger.digest({k:v for k,v in row.items() if k != 'checksum'})
            location.write_text(''.join(json.dumps(r)+'\n' for r in broken))
            with self.assertRaises(ledger.LedgerError): ledger.load(self.root)

    def test_static_default_cannot_execute_even_direct_run(self):
        context = self.context(grants=())
        self.write('src/app.py', 'value = 2\n')
        path, _ = self.plan(context=context)
        from execution_policy import PolicyError
        with self.assertRaises(PolicyError): ledger.run_scope(self.root, path, 'fixture', execution_context=context)
        with self.assertRaises(PolicyError): ledger.run(self.root, '.', 'targeted', 'fixture', [sys.executable, '-c', 'pass'], execution_context=context)
        self.assertFalse(Path(ledger.ledger_path(self.root)).exists())

    def test_selection_and_process_budgets_block_whole_batch(self):
        from execution_policy import PolicyError
        for resource in ('selected_tests', 'processes'):
            with self.subTest(resource=resource):
                context = self.context(budget={resource: 0})
                self.write('src/app.py', 'value = 3\n' if resource == 'processes' else 'value = 2\n')
                path, _ = self.plan(context=context)
                with self.assertRaisesRegex(PolicyError, 'BUDGET_EXCEEDED'):
                    ledger.run_scope(self.root, path, 'budget', execution_context=context)
                self.assertFalse(Path(ledger.ledger_path(self.root)).exists())

    def test_unknown_dependencies_are_candidates_and_budgeted(self):
        for i in range(4):
            self.write(f'tests/test_dynamic{i}.py', 'import importlib\n')
        git(self.root, 'add', '-A'); git(self.root, 'commit', '-qm', 'dynamic-tests')
        context = self.context(budget={'selected_tests': 2})
        self.write('src/app.py', 'value = 2\n')
        path, plan = self.plan(context=context)
        self.assertTrue(plan['selection']['conservative'])
        from execution_policy import PolicyError
        with self.assertRaisesRegex(PolicyError, 'BUDGET_EXCEEDED'):
            ledger.run_scope(self.root, path, 'budget', execution_context=context)
        self.assertFalse(Path(ledger.ledger_path(self.root)).exists())

    def test_tool_failure_preserves_exit_and_stops_same_input_retry(self):
        context = self.context()
        self.write('src/app.py', 'value = 2\n')
        runner = [{'suffixes': ['.py'], 'argv': ['aidp-nonexistent-runner', '{tests}']}]
        path, _ = self.plan(runner, context=context)
        out, code = ledger.run_scope(self.root, path, 'missing', execution_context=context)
        self.assertEqual(out['status'], 'UNVERIFIED'); self.assertEqual(out['runs'][0]['exit_code'], 127)
        self.assertEqual(out['runs'][0]['failure_kind'], 'ENV_UNAVAILABLE')
        from execution_policy import PolicyError
        with self.assertRaisesRegex(PolicyError, 'ENV_UNAVAILABLE'):
            ledger.run_scope(self.root, path, 'missing', execution_context=context)
        self.assertEqual(len(ledger.load(self.root)), 1)

    def test_cached_analysis_is_bound_to_content_inputs_and_environment(self):
        self.write('src/app.py', 'value = 2\n')
        self.write('docs/fixture.json', '{}\n')
        runners = copy.deepcopy(self.runners); runners[0]['inputs'] = ['docs/fixture.json']
        with patch.object(scope, 'dependency_analysis', wraps=scope.dependency_analysis) as analysis:
            self.plan(runners)
            scope._ANALYSIS_CACHE.clear()
            self.plan(runners)
            self.assertEqual(analysis.call_count, 1, '持久缓存应复用相同内容的依赖分析')
            self.write('docs/fixture.json', '{"value":2}\n')
            self.plan(runners)
            self.assertEqual(analysis.call_count, 2)
            with patch.dict(os.environ, {'AIDP_FIXTURE_ENV': 'changed'}):
                self.plan(runners)
            self.assertEqual(analysis.call_count, 3)
            self.write('src/app.py', 'value = 3\n')
            self.plan(runners)
            self.assertEqual(analysis.call_count, 4)

    def test_mutation_during_dependency_analysis_never_freezes_mixed_tree(self):
        self.write('src/app.py', 'value = 2\n')
        original = scope.dependency_analysis
        def mutate(*args, **kwargs):
            result = original(*args, **kwargs)
            self.write('src/app.py', 'value = 3\n')
            return result
        with patch.object(scope, 'dependency_analysis', side_effect=mutate):
            with self.assertRaisesRegex(scope.ScopeError, 'TREE_CHANGED'):
                self.plan()
        self.assertEqual(list((self.root / 'memory/.aidp/scope-analysis').glob('*.json')), [],
                         '混合树证明不能写入缓存供恢复后的原树复用')

    def test_scan_and_time_budget_reject_before_dependency_analysis(self):
        for budget in ({'scanned_files': 0}, {'elapsed_seconds': 0}):
            with self.subTest(budget=budget):
                # resolve 的初始发现也有扫描上限；两条入口都不得扩大预算。
                with patch.object(scope, 'dependency_analysis', wraps=scope.dependency_analysis) as analysis:
                    with self.assertRaisesRegex(ValueError, 'BUDGET_EXCEEDED|UNVERIFIED'):
                        context = self.context(budget=budget)
                        self.plan(context=context)
                    self.assertEqual(analysis.call_count, 0)

    def test_shared_change_categories_preserve_business_memory_and_explicit_docs(self):
        from project_inventory import classify_changes
        result = classify_changes(['backend/docs/state.json', 'backend/memory/.aidp/scope.json',
                                   'backend/src/memory/state.json', 'docs/input.json'],
                                  ['docs/input.json'], ['.', 'backend'])
        self.assertEqual(result['source'], ['backend/src/memory/state.json'])
        self.assertEqual(result['input'], ['docs/input.json'])
        self.assertEqual(result['runtime_only'], ['backend/docs/state.json', 'backend/memory/.aidp/scope.json'])

    def test_material_scope_revision_invalidates_scope_and_prior_acceptance(self):
        import entry_context
        context = self.context()
        self.write('src/app.py', 'value = 2\n')
        path, old = self.plan(context=context)
        first, _ = ledger.run_scope(self.root, path, 'policy', execution_context=context)
        entry_context.revise_context(self.root, context, write_set=['src/app.py', 'tests/test_app.py'])
        with self.assertRaises(scope.ScopeError):
            ledger.run_scope(self.root, path, 'policy', execution_context=context)
        path, current = self.plan(context=context)
        self.assertNotEqual(old['scope_hash'], current['scope_hash'])
        with self.assertRaises(ledger.LedgerError):
            ledger.verify_scope(self.root, path, current['scope_hash'], first['run_ids'], 'policy', execution_context=context)
        second, _ = ledger.run_scope(self.root, path, 'policy', execution_context=context)
        self.assertFalse(second['runs'][0]['reused'])

    def test_parallel_scope_commands_share_one_process_budget(self):
        context = self.context(budget={'processes': 1})
        self.write('src/app.py', 'value = 2\n')
        path, _ = self.plan(context=context)
        command = [sys.executable, str(SCRIPTS / 'test_ledger.py'), 'run-scope', '--root', str(self.root),
                   '--scope-file', str(path), '--execution-context', context, '--env-id', 'parallel-budget']
        processes = [subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
        outputs = [p.communicate(timeout=15) for p in processes]
        self.assertEqual(sorted(p.returncode for p in processes), [0, 2], str(outputs))
        results = [json.loads(stdout.splitlines()[-1]) for stdout, _ in outputs]
        self.assertEqual({r['status'] for r in results}, {'PASS', 'BUDGET_EXCEEDED'})
        self.assertEqual(len(ledger.load(self.root)), 1)

    def test_review_recording_requires_review_grant_but_verify_is_read_only(self):
        from execution_policy import PolicyError
        context = self.context()
        self.write('src/app.py', 'value = 2\n')
        path, plan = self.plan(context=context)
        result, _ = ledger.run_scope(self.root, path, 'review', execution_context=context)
        self.assertEqual(ledger.verify_scope(self.root, path, plan['scope_hash'], result['run_ids'], 'review',
                                            execution_context=context)['status'], 'PASS')
        with self.assertRaises(PolicyError):
            ledger.record_review(self.root, 'review', result['run_ids'], 'review', 'docs/report.json',
                                 scope_file=path, scope_hash=plan['scope_hash'], execution_context=context)

    def test_release_grant_reuses_test_review_and_completed_verification(self):
        import entry_context
        context = self.context(grants=('related-test', 'review'))
        self.write('src/app.py', 'value = 2\n')
        static = entry_context.run_static(self.root, context,
            [sys.executable, '-B', '-c', "import ast; ast.parse(open('src/app.py').read())"], ['src/app.py'])
        path, plan = self.plan(context=context)
        first, _ = ledger.run_scope(self.root, path, 'release', execution_context=context)
        report = self.write('memory/.aidp/review.json', json.dumps({
            'schema': 1, 'kind': 'code-review', 'status': 'PASS', 'scope_hash': plan['scope_hash'],
            'execution_context': plan['execution_context'], 'reviewer': 'fixture-reviewer', 'findings': [],
            'checks': [{'kind': 'code-review', 'status': 'PASS', 'evidence': ['src/app.py:1 positive integer value']}]}))
        review = ledger.record_review(self.root, 'release', first['run_ids'], 'release', report,
            scope_file=path, scope_hash=plan['scope_hash'], execution_context=context)
        kwargs = dict(scope_file=path, scope_hash=plan['scope_hash'], env_id='release', run_ids=first['run_ids'],
                      review_name='release', static_evidence=static['evidence_file'])
        before = entry_context.check_completion(self.root, context, **kwargs)
        self.assertTrue(before['ready'], before)
        entry_context.revise_context(self.root, context, additional_grants=['commit'],
            authorization_source={'kind': 'user-text', 'request_id': 'commit-grant', 'text': '提交已验证改动'})
        second, _ = ledger.run_scope(self.root, path, 'release', execution_context=context)
        self.assertEqual(second['run_ids'], first['run_ids'])
        self.assertTrue(second['runs'][0]['reused'])
        self.assertEqual(ledger.review_delta(self.root, 'release', 'release', execution_context=context)['review_id'], review['review_id'])
        after = entry_context.check_completion(self.root, context, **kwargs)
        self.assertTrue(after['ready'], after)

    def test_added_review_grant_preserves_existing_related_test_evidence(self):
        import entry_context
        context = self.context()
        self.write('src/app.py', 'value = 2\n')
        path, plan = self.plan(context=context)
        first, _ = ledger.run_scope(self.root, path, 'review-grant', execution_context=context)
        entry_context.revise_context(self.root, context, additional_grants=['review'],
            authorization_source={'kind': 'user-text', 'request_id': 'review-grant', 'text': '增加独立审查'})
        second, _ = ledger.run_scope(self.root, path, 'review-grant', execution_context=context)
        self.assertEqual(second['run_ids'], first['run_ids'])
        self.assertTrue(second['runs'][0]['reused'])

    def test_explicit_full_grant_allows_light_full_with_separate_build_ledger(self):
        from execution_policy import PolicyError
        context = self.context(grants=('full-regression',))
        build = Path(self.tmp.name) / 'build-ledger'
        result, code = ledger.run(self.root, '.', 'full', 'build', [sys.executable, '-B', '-c', 'pass'],
                                  ledger_root=build, execution_context=context)
        self.assertEqual(code, 0); self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['scope'], 'full')
        self.assertEqual(result['execution_context']['mode'], 'light')
        self.assertFalse(Path(ledger.ledger_path(self.root)).exists())
        self.assertEqual(ledger.load(self.root, build)[0]['run_id'], result['run_id'])
        denied = self.context(grants=('related-test',))
        with self.assertRaises(PolicyError):
            ledger.run(self.root, '.', 'full', 'build', [sys.executable, '-B', '-c', 'pass'],
                       ledger_root=build, execution_context=denied)
        with self.assertRaises(ledger.LedgerError):
            ledger.run(self.root, '.', 'sprint', 'build', [sys.executable, '-B', '-c', 'pass'], execution_context=denied)

    def test_aba_analysis_read_is_rejected_even_with_equal_tree_hashes(self):
        self.write('src/app.py', 'value = 2\n')
        target = self.root / 'tests/test_app.py'
        original = target.read_bytes()
        transient = original.replace(b'from src.app import value', b'from src.hidden import value')
        before = ledger.tree_snapshot(self.root)['hash']
        read_bytes = Path.read_bytes
        observed = []
        def aba_read(path):
            if path != target:
                return read_bytes(path)
            target.write_bytes(transient)
            try:
                content = read_bytes(path)
                observed.append(content)
            finally:
                target.write_bytes(original)
            return content
        with patch.object(Path, 'read_bytes', new=aba_read):
            with self.assertRaisesRegex(scope.ScopeError, '实际解析字节与冻结快照不一致'):
                self.plan()
        self.assertEqual(observed, [transient])
        self.assertEqual(before, ledger.tree_snapshot(self.root)['hash'], '夹具必须确实完成A→B→A')
        self.assertEqual(list((self.root / 'memory/.aidp/scope-analysis').glob('*.json')), [])
        _, valid = self.plan()
        proof = valid['dependencies']['tests']['tests/test_app.py']
        self.assertIn('src/app.py', proof['files'])
        self.assertFalse(any('hidden' in reason for reason in proof['unknown']))

    def test_java_selector_aba_read_is_rejected_before_plan_publication(self):
        target = self.write('tests/AppTest.java', 'package original; class AppTest {}\n')
        original = target.read_bytes()
        before = ledger.tree_snapshot(self.root)['hash']
        read_bytes = Path.read_bytes
        def aba_read(path):
            if path != target:
                return read_bytes(path)
            target.write_bytes(b'package transient; class AppTest {}\n')
            try:
                return read_bytes(path)
            finally:
                target.write_bytes(original)
        with patch.object(Path, 'read_bytes', new=aba_read):
            with self.assertRaisesRegex(scope.ScopeError, '实际解析字节与冻结快照不一致'):
                self.plan([{'suffixes': ['.java'], 'argv': ['mvn', '-Dtest={test_classes}', 'test']}])
        self.assertEqual(before, ledger.tree_snapshot(self.root)['hash'])
        self.assertEqual(list((self.root / 'memory/.aidp/scope-analysis').glob('*.json')), [])

    def test_light_lazy_baseline_reads_only_actual_change_candidates(self):
        import entry_context
        for index in range(64):
            self.write(f'src/clean{index}.py', f'value = {index}\n')
        git(self.root, 'add', '-A'); git(self.root, 'commit', '-qm', 'clean-files')
        context = self.context()
        frozen = entry_context.load_context(self.root, context)
        self.assertTrue(frozen['initial_git_files'])
        self.write('src/app.py', 'value = 2\n')
        with patch.object(entry_context, 'initial_hash', wraps=entry_context.initial_hash) as initial:
            _, plan = self.plan(context=context)
        self.assertEqual(plan['changed'], ['src/app.py'])
        self.assertEqual(plan['tests'], ['tests/test_app.py'])
        self.assertEqual({call.args[2] for call in initial.call_args_list}, {'src/app.py'})
        self.assertEqual(initial.call_count, 1, '干净源码不得逐文件读取冻结Git blob')

    def test_light_lazy_baseline_detects_committed_submodule_head_change(self):
        import entry_context
        child = self.module()
        expected = entry_context.initial_file_hash(child / 'src/lib.py')
        context = self.context()
        frozen = entry_context.load_context(self.root, context)
        (child / 'src/lib.py').write_text('value = 2\n')
        git(child, '-c', 'user.name=test', '-c', 'user.email=t@example.invalid', 'commit', '-qam', 'changed-child-head')
        self.assertEqual(git(child, 'status', '--porcelain'), '')
        _, plan = self.plan([{'cwd': 'backend', 'suffixes': ['.py'], 'argv': [sys.executable, '-B', '{tests}']}], context=context)
        self.assertEqual(plan['changed'], ['backend/src/lib.py'])
        self.assertEqual(plan['tests'], ['backend/tests/test_lib.py'])
        self.assertEqual(entry_context.initial_hash(self.root, frozen, 'backend/src/lib.py'), expected)
        self.assertNotEqual(expected, entry_context.initial_file_hash(child / 'src/lib.py'))

    def test_light_lazy_baseline_detects_permission_changes_git_does_not_report(self):
        context = self.context()
        (self.root / 'src/app.py').chmod(0o640)
        self.assertEqual(git(self.root, 'diff', '--name-only'), '')
        _, plan = self.plan(context=context)
        self.assertEqual(plan['changed'], ['src/app.py'])
        self.assertEqual(plan['tests'], ['tests/test_app.py'])

    def test_light_baseline_detects_clean_symlink_target_content_change(self):
        target = Path(self.tmp.name) / 'linked-source.py'
        target.write_text('value = 1\n')
        source = self.root / 'src/app.py'
        source.unlink(); source.symlink_to(target)
        git(self.root, 'add', '-A'); git(self.root, 'commit', '-qm', 'linked-source')
        context = self.context()
        target.write_text('value = 2\n')
        self.assertEqual(git(self.root, 'diff', '--name-only'), '')
        _, plan = self.plan(context=context)
        self.assertEqual(plan['changed'], ['src/app.py'])
        self.assertEqual(plan['tests'], ['tests/test_app.py'])

    def test_missing_requested_python_runner_is_environment_error(self):
        for module in ('aidp_fixture_missing_runner', 'aidp_fixture_missing_runner.child'):
            with self.subTest(module=module):
                row, code = ledger.run(self.root, '.', 'targeted', 'missing-runner',
                    [sys.executable, '-B', '-m', module])
                self.assertEqual(code, 1)
                self.assertEqual(row['exit_code'], 1, '保留解释器真实退出码')
                self.assertEqual(row['status'], 'ERROR')
                self.assertEqual(row['failure_kind'], 'ENV_UNAVAILABLE')

    def test_deleted_business_module_import_is_test_failure(self):
        self.write('src/app_missing.py', 'value = 1\n')
        self.write('tests/test_app_missing.py', 'import unittest\nfrom src.app_missing import value\nclass AppMissing(unittest.TestCase):\n def test_value(self): self.assertEqual(value, 1)\n')
        git(self.root, 'add', '-A'); git(self.root, 'commit', '-qm', 'business-module')
        self.base = git(self.root, 'rev-parse', 'HEAD')
        (self.root / 'src/app_missing.py').unlink()
        path, plan = self.plan()
        self.assertIn('src/app_missing.py', plan['changed'])
        result, code = ledger.run_scope(self.root, path, 'deleted-business')
        self.assertEqual(code, 1)
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['runs'][0]['exit_code'], 1)
        self.assertEqual(result['runs'][0]['failure_kind'], 'TEST_FAILURE')

    def test_real_pytest_collection_errors_are_unverified_not_tool_errors(self):
        from importlib.util import find_spec
        if find_spec('pytest') is None:
            self.skipTest('需要真实pytest；可在独立pytest临时环境定向执行')
        self.write('src/pytest_deleted.py', 'value = 1\n')
        git(self.root, 'add', '-A'); git(self.root, 'commit', '-qm', 'pytest-business-module')
        (self.root / 'src/pytest_deleted.py').unlink()
        for content in ('def test_invalid(:\n pass\n', 'from src.pytest_deleted import value\ndef test_value(): assert value == 1\n'):
            with self.subTest(content=content):
                self.write('tests/test_collection_error.py', content)
                row, code = ledger.run(self.root, '.', 'targeted', 'pytest-collection',
                    [sys.executable, '-B', '-m', 'pytest', '-q', 'tests/test_collection_error.py'])
                self.assertEqual(code, 2)
                self.assertEqual(row['exit_code'], 2)
                self.assertEqual(row['status'], 'ERROR')
                self.assertEqual(row['failure_kind'], 'COLLECTION_OR_INTERRUPTION')
                self.assertNotIn(row['failure_kind'], ('TOOL_ERROR', 'ENV_UNAVAILABLE'))

    def test_real_pytest_assertion_is_actual_test_failure(self):
        from importlib.util import find_spec
        if find_spec('pytest') is None:
            self.skipTest('需要真实pytest；可在独立pytest临时环境定向执行')
        self.write('tests/test_assertion_error.py', 'def test_value(): assert 1 == 2\n')
        row, code = ledger.run(self.root, '.', 'targeted', 'pytest-assertion',
            [sys.executable, '-B', '-m', 'pytest', '-q', 'tests/test_assertion_error.py'])
        self.assertEqual(code, 1)
        self.assertEqual(row['exit_code'], 1)
        self.assertEqual(row['status'], 'FAIL')
        self.assertEqual(row['failure_kind'], 'TEST_FAILURE')

    def test_full_default_uses_shared_hour_budget_and_reuses_after_settlement(self):
        import entry_context
        from execution_policy import reserve_budget
        context = self.context(grants=('full-regression',), budget={'elapsed_seconds': 7200})
        frozen = entry_context.load_context(self.root, context)
        reserve_budget(self.root, frozen, 'elapsed_seconds', 3600, action='full-regression')
        build = Path(self.tmp.name) / 'hour-build-ledger'
        command = [sys.executable, '-B', '-c', 'pass']
        first, code = ledger.run(self.root, '.', 'full', 'hour-build', command,
                                 ledger_root=build, execution_context=context)
        self.assertEqual(code, 0)
        self.assertGreater(first['execution_timeout'], 3500)
        self.assertLessEqual(first['execution_timeout'], 3600)
        second, code = ledger.run(self.root, '.', 'full', 'hour-build', command,
                                  ledger_root=build, execution_context=context)
        self.assertEqual(code, 0)
        self.assertEqual(first['run_id'], second['run_id'])
        self.assertTrue(second['reused'], '剩余时间预算变化不能迫使同树已通过证据重跑')
        explicit, code = ledger.run(self.root, '.', 'full', 'hour-build', command, timeout=5,
                                    ledger_root=build, execution_context=context)
        self.assertEqual(code, 0)
        self.assertEqual(explicit['execution_timeout'], 5)


if __name__ == '__main__':
    unittest.main(verbosity=2)
