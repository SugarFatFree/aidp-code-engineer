#!/usr/bin/env python3
"""入口上下文真实 CLI 回归：临时 Git、冻结身份与轻量动作边界。"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]
SCRIPT = SCRIPTS / "entry_context.py"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


class EntryContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aidp-entry-context-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.git("init", "-q")
        self.git("config", "user.name", "Entry Test")
        self.git("config", "user.email", "entry@example.test")
        (self.root / ".gitignore").write_text("memory/.aidp/\n")
        (self.root / "app.py").write_text("answer = 1\n")
        self.git("add", ".")
        self.git("commit", "-qm", "initial")
        self.head = self.git("rev-parse", "HEAD").strip()

    def git(self, *args):
        proc = subprocess.run(["git", "-C", str(self.root), *args], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout

    def cli(self, action, *args, expected=0, root=None):
        proc = subprocess.run([sys.executable, str(SCRIPT), action,
                               "--root", str(root or self.root), "--json", *args],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, expected, proc.stdout + proc.stderr)
        return json.loads(proc.stdout)

    def resolve(self, *args):
        return self.cli("resolve", "--entry", "sprint-dev", "--version", "V1.0.0", *args)

    def context(self, result):
        return json.loads(Path(result["execution_context"]).read_text())

    def resolve_static_only(self, *args):
        return self.resolve("--authorization-source", json.dumps({"kind": "user-text", "request_id": "static-exception",
            "text": "仅实现与静态检查，本次明确跳过相关测试", "skip_actions": ["related-test"]}), *args)

    def test_light_all_phases_without_sprint_files(self):
        resolved = self.resolve("--write-set", "app.py", "--acceptance", "answer updated")
        ctx = self.context(resolved)
        self.assertEqual(ctx["mode"], "light")
        self.assertNotIn("sprint", ctx)
        self.assertEqual(ctx["since"], self.head)
        self.assertEqual(ctx["revision"], 1)
        before = Path(resolved["execution_context"]).read_bytes()
        for phase in ("route", "prepare", "dev", "test", "repair", "close"):
            routed = self.cli("route", "--execution-context", resolved["execution_context"], "--phase", phase)
            self.assertEqual(routed["mode"], "light")
            self.assertTrue(routed["actions"])
            self.assertIn("allocate-sprint", routed["forbidden_actions"])
            self.assertEqual(routed["identity_hash"], resolved["identity_hash"])
        self.assertEqual(before, Path(resolved["execution_context"]).read_bytes())
        self.assertFalse((self.root / "docs").exists())
        self.assertFalse((self.root / "memory/activeContext.md").exists())

    def test_existing_formal_state_is_not_adopted_or_changed(self):
        paths = ("memory/activeContext.md", "memory/progress.md", "memory/.sprint-autopilot-baseline.json")
        for rel in paths:
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("existing Sprint 007\n")
        before = {rel: (self.root / rel).read_bytes() for rel in paths}
        resolved = self.resolve()
        self.assertEqual(self.context(resolved)["mode"], "light")
        for phase in ("prepare", "dev", "test", "repair", "close"):
            self.cli("route", "--execution-context", resolved["execution_context"], "--phase", phase)
        self.assertEqual(before, {rel: (self.root / rel).read_bytes() for rel in paths})

    def test_explicit_sprint_and_formal_entries(self):
        explicit = self.resolve("--sprint", "007")
        self.assertEqual(self.context(explicit)["sprint"], "007")
        for entry in ("version", "sprint-full", "sprint-batch", "sprint-autopilot"):
            result = self.cli("resolve", "--entry", entry, "--version", "V1.0.0")
            ctx = self.context(result)
            self.assertEqual(ctx["mode"], "formal")
            self.assertIsNone(ctx["sprint"])

    def test_nested_formal_stays_formal_without_allocation(self):
        resolved = self.resolve("--sprint", "007")
        nested = self.cli("resolve", "--entry", "bugfix", "--execution-context", resolved["execution_context"])
        self.assertEqual(nested["identity_hash"], resolved["identity_hash"])
        self.assertEqual(self.context(nested)["sprint"], "007")
        route = self.cli("route", "--entry", "test", "--execution-context", nested["execution_context"], "--phase", "prepare")
        self.assertTrue(route["preserve_formal_gates"])
        self.assertNotIn("allocate-sprint", route["actions"])
        self.assertFalse((self.root / "memory/.aidp/id-alloc.jsonl").exists())

    def test_light_cannot_upgrade_through_nested_entry_or_explicit_sprint(self):
        resolved = self.resolve()
        for entry in ("version", "sprint-full", "sprint-batch", "sprint-autopilot"):
            self.cli("resolve", "--entry", entry, "--execution-context", resolved["execution_context"], expected=2)
            self.cli("route", "--entry", entry, "--execution-context", resolved["execution_context"], expected=2)
        self.cli("resolve", "--entry", "start", "--execution-context", resolved["execution_context"], "--sprint", "008", expected=2)
        for action in ("allocate-sprint", "create-contract", "start-sprint", "close-sprint", "archive", "reset-active", "cascade"):
            self.cli("route", "--execution-context", resolved["execution_context"], "--phase", "close", "--action", action, expected=2)

    def test_resume_keeps_start_commit_and_independent_tasks(self):
        first = self.resolve()
        (self.root / "app.py").write_text("answer = 2\n")
        self.git("add", "app.py")
        self.git("commit", "-qm", "next")
        resumed = self.cli("resolve", "--entry", "test", "--execution-context", first["execution_context"])
        second = self.resolve()
        self.assertEqual(resumed["identity_hash"], first["identity_hash"])
        self.assertEqual(self.context(resumed)["since"], self.head)
        self.assertNotEqual(second["task_id"], first["task_id"])
        self.assertNotEqual(self.context(second)["since"], self.head)
        self.cli("resolve", "--entry", "test", "--execution-context", first["execution_context"], "--since", "HEAD", expected=2)

    def test_snapshot_captures_preexisting_dirty_and_deleted_files(self):
        (self.root / "app.py").write_text("answer = 9\n")
        (self.root / "notes.txt").write_text("old unrelated edits\n")
        (self.root / ".gitignore").unlink()
        resolved = self.resolve()
        ctx = self.context(resolved)
        self.assertIn("app.py", ctx["preexisting_dirty"])
        self.assertIn("notes.txt", ctx["preexisting_dirty"])
        self.assertIn(".gitignore", ctx["preexisting_dirty"])
        self.assertIsNone(ctx["initial_files"][".gitignore"])
        self.assertTrue(ctx["initial_files"]["app.py"])
        self.assertFalse(any("entry-contexts/" in path for path in ctx["initial_files"]))

    def add_submodule(self, name="modules/service", parent=None):
        parent = parent or self.root
        source = tempfile.TemporaryDirectory(prefix="aidp-entry-submodule-source-")
        self.addCleanup(source.cleanup)
        seed = Path(source.name)
        for args in (("init", "-q"), ("config", "user.name", "Entry Test"),
                     ("config", "user.email", "entry@example.test")):
            subprocess.run(["git", "-C", str(seed), *args], check=True, capture_output=True)
        (seed / "feature.py").write_text("answer = 1\n")
        (seed / "unrelated.py").write_text("existing = 1\n")
        (seed / "tests").mkdir()
        (seed / "tests/test_feature.py").write_text(
            "import unittest\nfrom pathlib import Path\n"
            "class FeatureTest(unittest.TestCase):\n"
            " def test_answer(self): self.assertEqual(Path('feature.py').read_text(), 'answer = 2\\n')\n"
            "if __name__ == '__main__': unittest.main()\n")
        for args in (("add", "."), ("commit", "-qm", "seed")):
            subprocess.run(["git", "-C", str(seed), *args], check=True, capture_output=True)
        self.git("-C", str(parent), "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(seed), name)
        self.git("-C", str(parent), "commit", "-qam", "add submodule")
        self.git("-C", str(parent / name), "config", "user.name", "Entry Test")
        self.git("-C", str(parent / name), "config", "user.email", "entry@example.test")
        return parent / name

    def test_submodule_initial_snapshot_preserves_dirty_and_formal_entry_works(self):
        module = self.add_submodule()
        pin = self.git("-C", str(module), "rev-parse", "HEAD").strip()
        (module / "unrelated.py").write_text("existing = 9\n")
        (module / "old_untracked.py").write_text("old = 1\n")
        (module / "tests/test_feature.py").unlink()
        resolved = self.resolve()
        ctx = self.context(resolved)
        self.assertEqual(ctx["initial_gitlinks"]["modules/service"], {"index": pin, "committed": pin, "head": pin})
        self.assertIn("modules/service/feature.py", ctx["initial_files"])
        self.assertIsNone(ctx["initial_files"]["modules/service/tests/test_feature.py"])
        self.assertNotIn("modules/service", ctx["initial_files"])
        self.assertNotIn("modules/service/.git", ctx["initial_files"])
        for path in ("unrelated.py", "old_untracked.py", "tests/test_feature.py"):
            self.assertIn("modules/service/" + path, ctx["preexisting_dirty"])
        formal = self.resolve("--sprint", "007")
        routed = self.cli("route", "--execution-context", formal["execution_context"], "--entry", "start", "--phase", "prepare")
        self.assertEqual(routed["mode"], "formal")
        (module / "feature.py").write_text("answer = 2\n")
        resumed = self.cli("resolve", "--entry", "test", "--execution-context", resolved["execution_context"])
        self.assertEqual(resumed["identity_hash"], resolved["identity_hash"])

    def test_submodule_existing_committed_pin_drift_is_preexisting_dirty(self):
        module = self.add_submodule()
        pin = self.git("-C", str(module), "rev-parse", "HEAD").strip()
        (module / "unrelated.py").write_text("existing = 8\n")
        self.git("-C", str(module), "add", "unrelated.py")
        self.git("-C", str(module), "commit", "-qm", "preexisting submodule commit")
        head = self.git("-C", str(module), "rev-parse", "HEAD").strip()
        self.git("add", "modules/service")
        resolved = self.resolve()
        ctx = self.context(resolved)
        self.assertEqual(ctx["initial_gitlinks"]["modules/service"], {"index": head, "committed": pin, "head": head})
        self.assertIn("modules/service/unrelated.py", ctx["preexisting_dirty"])
        self.assertNotIn("modules/service/feature.py", ctx["preexisting_dirty"])

    def test_nested_submodule_snapshot_expands_dirty_and_tracks_each_pin(self):
        module = self.add_submodule()
        nested = self.add_submodule("vendor/library", parent=module)
        self.git("add", "modules/service")
        self.git("commit", "-qm", "update module pin")
        (nested / "unrelated.py").write_text("existing = 7\n")
        self.git("-C", str(nested), "add", "unrelated.py")
        self.git("-C", str(nested), "commit", "-qm", "nested preexisting change")
        (nested / "feature.py").write_text("answer = 3\n")
        resolved = self.resolve()
        ctx = self.context(resolved)
        nested_prefix = "modules/service/vendor/library/"
        self.assertEqual(set(ctx["initial_gitlinks"]), {"modules/service", nested_prefix.rstrip("/")})
        self.assertIn(nested_prefix + "feature.py", ctx["initial_files"])
        self.assertIn(nested_prefix + "feature.py", ctx["preexisting_dirty"])
        self.assertIn(nested_prefix + "unrelated.py", ctx["preexisting_dirty"])
        self.assertNotIn("modules/service/feature.py", ctx["preexisting_dirty"])

    def test_uninitialized_submodule_is_explicitly_unverified(self):
        self.add_submodule()
        self.git("submodule", "deinit", "-f", "--", "modules/service")
        result = self.cli("resolve", "--entry", "sprint-dev", "--version", "V1", expected=2)
        self.assertIn("UNVERIFIED", result["error"])
        self.assertIn("modules/service", result["error"])
        self.assertFalse((self.root / "memory/.aidp/entry-contexts").exists())

    def test_submodule_task_scope_excludes_existing_dirty_and_runs_real_tests(self):
        module = self.add_submodule()
        (module / "unrelated.py").write_text("existing = 9\n")
        resolved = self.resolve()
        (module / "feature.py").write_text("answer = 2\n")
        self.authorize_verification(resolved)
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        from test_scope import derive
        plan = derive(self.root, None, [{"cwd": "modules/service", "suffixes": [".py"],
                      "argv": [sys.executable, "-B", "{tests}"]}], execution_context=resolved["execution_context"])
        self.assertIn("modules/service/feature.py", plan["changed"])
        self.assertNotIn("modules/service/unrelated.py", plan["changed"])
        self.assertIn("modules/service/tests/test_feature.py", plan["tests"])
        self.assertTrue(plan["runs"])
        scope = Path(resolved["execution_context"]).with_name("scope.json")
        scope.write_text(json.dumps(plan))
        args = ["--scope-file", str(scope), "--scope-hash", plan["scope_hash"]]
        runs = self.ledger_cli("run-scope", resolved, *args[:2])
        self.assertEqual(runs["status"], "PASS")
        evidence = self.review(resolved, plan, args, runs["run_ids"])
        completed = self.cli("complete", "--execution-context", resolved["execution_context"], *evidence)
        self.assertTrue(completed["completed"])
        self.assertEqual((module / "unrelated.py").read_text(), "existing = 9\n")

    def test_write_set_expansion_is_explicit_revision(self):
        initial = self.resolve("--write-set", "app.py")
        self.cli("resolve", "--entry", "test", "--execution-context", initial["execution_context"], "--write-set", "other.py", expected=2)
        revised = self.cli("revise", "--execution-context", initial["execution_context"], "--write-set", "other.py")
        self.assertEqual(revised["task_id"], initial["task_id"])
        self.assertNotEqual(revised["identity_hash"], initial["identity_hash"])
        ctx = self.context(revised)
        self.assertEqual(ctx["revision"], 2)
        self.assertEqual(ctx["write_set"], ["app.py", "other.py"])
        repeated = self.cli("revise", "--execution-context", initial["execution_context"], "--write-set", "other.py")
        self.assertEqual(repeated["identity_hash"], revised["identity_hash"])

    def test_static_directory_excludes_677_cache_files_and_unrelated_toolkit(self):
        import entry_context as entry
        from unittest.mock import patch
        sources = [f'pkg/source{i}.py' for i in range(19)]
        tests = [f'pkg/tests/test_source{i}.py' for i in range(10)]
        for name in sources + tests + [f'pkg/__pycache__/cached{i}.pyc' for i in range(677)] + ['pkg/node_modules/tool/index.js']:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('pass\n')
        resolved = self.resolve('--write-set', 'pkg')
        ctx = self.context(resolved)
        with patch.object(entry, 'initial_file_hash', wraps=entry.initial_file_hash) as hashed:
            inputs = entry._input_files(self.root, ctx, ['pkg'])
        self.assertEqual(set(inputs), set(sources + tests))
        self.assertLessEqual(hashed.call_count, 29)
        explicit = entry._input_files(self.root, ctx, ['pkg', 'pkg/__pycache__/cached0.pyc'])
        self.assertIn('pkg/__pycache__/cached0.pyc', explicit)

    def test_verification_refinement_preserves_authorization_and_changed_rename_members(self):
        import entry_context as entry
        for name in ('a.py', 'b.py', 'deleted.py'):
            target = self.root / 'pkg' / name
            target.parent.mkdir(exist_ok=True)
            target.write_text('value = 1\n')
        self.git('add', 'pkg'); self.git('commit', '-qm', 'package')
        resolved = self.resolve('--write-set', 'pkg')
        original = self.context(resolved)
        (self.root / 'pkg/a.py').write_text('value = 2\n')
        (self.root / 'pkg/deleted.py').rename(self.root / 'pkg/renamed.py')
        revised = self.cli('revise', '--execution-context', resolved['execution_context'],
                           '--verification-input', 'pkg/a.py')
        ctx = self.context(revised)
        self.assertEqual(ctx['write_set'], ['pkg'])
        self.assertEqual(ctx['verification_inputs'], ['pkg/a.py'])
        for key in ('task_id', 'since', 'initial_files', 'authorization_source', 'execution_budget'):
            self.assertEqual(ctx[key], original[key])
        with self.assertRaisesRegex(ValueError, '覆盖|改动'):
            entry._input_files(self.root, ctx, ['pkg/a.py'])
        inputs = entry._input_files(self.root, ctx, ['pkg/a.py', 'pkg/deleted.py', 'pkg/renamed.py'])
        self.assertEqual(set(inputs), {'pkg/a.py', 'pkg/deleted.py', 'pkg/renamed.py'})
        self.assertIsNone(inputs['pkg/deleted.py'])

    def test_repeated_static_completion_does_not_reread_unchanged_inputs(self):
        import entry_context as entry
        from unittest.mock import patch
        resolved = self.resolve_static_only('--write-set', 'app.py')
        result = entry.run_static(self.root, resolved['execution_context'],
            [sys.executable, '-B', '-c', "import ast; ast.parse(open('app.py').read())"], ['app.py'])
        with patch.object(entry, 'initial_file_hash', wraps=entry.initial_file_hash) as hashed:
            for _ in range(2):
                check = entry.check_completion(self.root, resolved['execution_context'], static_evidence=result['evidence_file'])
                self.assertTrue(check['ready'], check)
        self.assertEqual(hashed.call_count, 0, '重复收尾必须减少真实内容读取，不能只去重计费')

    def test_replace_write_set_keeps_original_authorization_and_actual_changes(self):
        import entry_context as entry
        for name in ('a.py', 'b.py', 'c.py'):
            target = self.root / 'pkg' / name
            target.parent.mkdir(exist_ok=True)
            target.write_text('pass\n')
        self.git('add', 'pkg'); self.git('commit', '-qm', 'package')
        resolved = self.resolve('--write-set', 'pkg')
        (self.root / 'pkg/b.py').unlink()
        revised = self.cli('revise', '--execution-context', resolved['execution_context'],
            '--replace-write-set', '--write-set', 'pkg/a.py')
        ctx = self.context(revised)
        self.assertEqual(ctx['write_set'], ['pkg/a.py', 'pkg/b.py'])
        self.assertEqual(ctx['authorization_scope'], ['pkg', 'pkg/a.py'])
        self.assertEqual(ctx['task_id'], resolved['task_id'])
        self.assertTrue(ctx['scope_history'])
        self.assertEqual(ctx['task_scope']['paths'], ctx['write_set'])
        before = ctx['revision']
        repeated = entry.revise_context(self.root, resolved['execution_context'], write_set=['pkg/a.py'], replace_write_set=True)
        self.assertEqual(repeated['revision'], before, '幂等细化不能反复使证据失效')

    def test_static_budget_reserves_post_evidence_before_starting_process(self):
        import entry_context as entry
        from unittest.mock import patch
        resolved = self.resolve('--write-set', 'app.py', '--execution-budget', '{"scanned_files": 2}')
        with patch.object(entry.subprocess, 'run', wraps=entry.subprocess.run) as process:
            with self.assertRaisesRegex(ValueError, 'BUDGET_EXCEEDED'):
                entry.run_static(self.root, resolved['execution_context'],
                    [sys.executable, '-B', '-c', "import ast; ast.parse(open('app.py').read())"], ['app.py'])
        self.assertFalse(any(call.args[0][0] == sys.executable for call in process.call_args_list))

    def test_static_preserves_process_result_when_post_evidence_fails(self):
        import entry_context as entry
        from unittest.mock import patch
        resolved = self.resolve('--write-set', 'app.py')
        original = entry._input_snapshot
        calls = []
        def failing(*args, **kwargs):
            calls.append(1)
            if len(calls) > 1:
                raise OSError('fixture post evidence unreadable')
            return original(*args, **kwargs)
        with patch.object(entry, '_input_snapshot', side_effect=failing):
            result = entry.run_static(self.root, resolved['execution_context'],
                [sys.executable, '-B', '-c', "import ast; ast.parse(open('app.py').read()); print('checked')"], ['app.py'])
        self.assertEqual(result['status'], 'UNVERIFIED')
        self.assertTrue(result['executed'])
        self.assertEqual(result['result']['returncode'], 0)
        self.assertIn('checked', result['result']['stdout'])
        row = json.loads(Path(result['evidence_file']).read_text())
        self.assertIn('post evidence unreadable', row['evidence_missing_reason'])
        self.assertEqual(row['process_status'], 'PASS')

    def test_static_aba_during_execution_never_reuses_pass(self):
        import entry_context as entry
        from unittest.mock import patch
        resolved = self.resolve('--write-set', 'app.py')
        original_run = entry.subprocess.run
        def aba(command, **kwargs):
            if command[0] == sys.executable:
                target = self.root / 'app.py'
                original = target.read_bytes()
                target.write_text('answer = 9\n')
                result = original_run(command, **kwargs)
                target.write_bytes(original)
                return result
            return original_run(command, **kwargs)
        with patch.object(entry.subprocess, 'run', side_effect=aba):
            result = entry.run_static(self.root, resolved['execution_context'],
                [sys.executable, '-B', '-c', "import ast; ast.parse(open('app.py').read())"], ['app.py'])
        self.assertEqual(result['status'], 'UNVERIFIED')
        self.assertEqual(result['process_status'], 'PASS')

    def test_plan_validation_is_readonly_and_distinguishes_syntax_from_tests(self):
        resolved = self.resolve('--write-set', 'app.py')
        before = Path(resolved['execution_context']).read_bytes()
        result = self.cli('plan-validation', '--execution-context', resolved['execution_context'])
        self.assertTrue(result['candidates'])
        self.assertFalse(result['executed'])
        self.assertEqual(result['candidates'][0]['category'], 'syntax')
        self.assertTrue(result['candidates'][0]['syntax_only'])
        self.assertEqual(before, Path(resolved['execution_context']).read_bytes())
        self.assertIn('cleanup', result['budget_estimate'])

    def test_delivery_receipt_reuses_input_reference_and_preserves_delivered_fact(self):
        import entry_context as entry
        resolved = self.resolve_static_only('--write-set', 'app.py')
        static = entry.run_static(self.root, resolved['execution_context'],
            [sys.executable, '-B', '-c', "import ast; ast.parse(open('app.py').read())"], ['app.py'])
        self.assertIn('inputs_ref', static)
        updated = entry.revise_context(self.root, resolved['execution_context'], additional_grants=['deploy'],
            authorization_source={'kind': 'user-text', 'request_id': 'delivery', 'text': '部署当前变更'})
        receipt = Path(resolved['execution_context']).with_name('deploy-receipt.json')
        receipt.write_text(json.dumps({'execution_context': entry.evidence_identity(updated['context']),
            'action': 'deploy', 'status': 'PASS', 'inputs_ref': static['inputs_ref'],
            'checks': [{'kind': 'delivery', 'status': 'PASS', 'evidence': ['provider delivery-123 succeeded']}],
            'receipt': {'id': 'delivery-123', 'status': 'succeeded'}}))
        done = entry.check_completion(self.root, resolved['execution_context'], static_evidence=static['evidence_file'],
                                      action_evidence={'deploy': str(receipt)})
        self.assertTrue(done['ready'], done)
        self.assertTrue(done['delivery_facts']['deploy']['delivered'])
        (self.root / 'app.py').write_text('answer = 5\n')
        stale = entry.check_completion(self.root, resolved['execution_context'], static_evidence=static['evidence_file'],
                                      action_evidence={'deploy': str(receipt)})
        self.assertFalse(stale['ready'])
        self.assertTrue(stale['delivery_facts']['deploy']['delivered'])
        self.assertEqual(stale['finalization_status'], 'UNVERIFIED')

    def test_static_reuse_needs_no_new_process_budget_and_tracks_configuration_creation(self):
        import entry_context as entry
        from unittest.mock import patch
        resolved = self.resolve('--write-set', 'app.py', '--execution-budget', '{"processes":1}')
        argv = [sys.executable, '-B', '-c', "import ast; ast.parse(open('app.py').read())"]
        first = entry.run_static(self.root, resolved['execution_context'], argv, ['app.py'])
        with patch.object(entry, 'initial_file_hash', wraps=entry.initial_file_hash) as hashed:
            repeated = entry.run_static(self.root, resolved['execution_context'], argv, ['app.py'])
        self.assertTrue(repeated['reused'])
        self.assertEqual(repeated['evidence_file'], first['evidence_file'])
        self.assertEqual(hashed.call_count, 0)
        (self.root / 'pyproject.toml').write_text('[tool.ruff]\nline-length = 100\n')
        self.assertFalse(entry.check_completion(self.root, resolved['execution_context'],
                                               static_evidence=first['evidence_file'])['ready'])

    def test_another_static_command_cannot_hide_failed_check_after_refinement(self):
        import entry_context as entry
        resolved = self.resolve('--write-set', 'app.py')
        (self.root / 'app.py').write_text('def broken(:\n')
        failed = entry.run_static(self.root, resolved['execution_context'],
            [sys.executable, '-B', '-c', "import ast; ast.parse(open('app.py').read())"], ['app.py'])
        self.assertEqual(failed['status'], 'FAIL')
        entry.revise_context(self.root, resolved['execution_context'], write_set=['app.py'], replace_write_set=True)
        (self.root / 'app.py').write_text('answer = 1\n')
        alternative = entry.run_static(self.root, resolved['execution_context'],
            [sys.executable, '-B', '-c', "import ast; ast.parse(open('app.py').read()); print('other command')"], ['app.py'])
        self.assertEqual(alternative['status'], 'PASS')
        gate = entry.check_completion(self.root, resolved['execution_context'], static_evidence=alternative['evidence_file'])
        self.assertFalse(gate['ready'])
        self.assertIn('失败', gate['error'])

    def test_static_unreliable_filesystem_reads_content_and_accounts_real_cost(self):
        import entry_context as entry
        import project_inventory as inventory
        from unittest.mock import patch
        resolved = self.resolve('--write-set', 'app.py')
        argv = [sys.executable, '-B', '-c', "import ast; ast.parse(open('app.py').read())"]
        with patch.object(inventory, 'fingerprint_token', return_value=None):
            first = entry.run_static(self.root, resolved['execution_context'], argv, ['app.py'])
            repeated = entry.run_static(self.root, resolved['execution_context'], argv, ['app.py'])
        self.assertEqual(first['status'], 'PASS')
        self.assertTrue(repeated['reused'])
        self.assertGreater(repeated['read_cost']['content_reads'], 0)
        budget = json.loads(Path(resolved['execution_context']).with_name('budget.json').read_text())
        self.assertEqual(budget['used']['scanned_files'], resolved['snapshot_cost']['hashed_files'] +
                         first['read_cost']['content_reads'] + repeated['read_cost']['content_reads'])
        self.assertEqual(budget['used']['processes'], 1)

    def test_static_broad_scope_skips_unchanged_installed_skill_but_keeps_changed_or_explicit(self):
        import entry_context as entry
        for name, content in {'skills/helper/SKILL.md': '# helper\n', 'skills/helper/tool.py': 'pass\n',
                              'skills/business.py': 'value = 1\n'}.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        self.git('add', 'skills'); self.git('commit', '-qm', 'tools')
        resolved = self.resolve('--write-set', 'skills')
        ctx = self.context(resolved)
        self.assertEqual(resolved['snapshot_cost']['hashed_files'], 1, '宽授权不得物化未改安装包')
        self.assertEqual(set(entry._input_files(self.root, ctx, ['skills'])), {'skills/business.py'})
        cache = self.root / 'skills/helper/__pycache__/tool.pyc'
        cache.parent.mkdir(); cache.write_bytes(b'bytecode')
        self.assertEqual(set(entry._input_files(self.root, ctx, ['skills'])), {'skills/business.py'})
        explicit = entry._input_files(self.root, ctx, ['skills/business.py', 'skills/helper'])
        self.assertIn('skills/helper/tool.py', explicit)
        (self.root / 'skills/helper/tool.py').write_text('value = 2\n')
        self.assertIn('skills/helper/tool.py', entry._input_files(self.root, ctx, ['skills']))

    def test_static_executor_does_not_run_tests_even_when_related_tests_are_authorized(self):
        import entry_context as entry
        from unittest.mock import patch
        (self.root / 'test_app.py').write_text('pass\n')
        resolved = self.resolve('--write-set', 'app.py', '--grant', 'related-test', '--authorization-source',
            json.dumps({'kind': 'user-text', 'request_id': 'test-also-allowed', 'text': '运行相关测试'}))
        with patch.object(entry.subprocess, 'run', wraps=entry.subprocess.run) as process:
            for argv in ([sys.executable, '-m', 'unittest', 'test_app'],
                         [sys.executable, '-m', 'pytest', 'test_app.py']):
                with self.assertRaisesRegex(ValueError, 'UNAUTHORIZED|测试'):
                    entry.run_static(self.root, resolved['execution_context'], argv, ['app.py'])
        self.assertFalse(any(call.args[0][0] == sys.executable for call in process.call_args_list))

    def test_static_failure_retry_uses_real_content_not_metadata_prediction(self):
        import entry_context as entry
        config = self.root / 'pyproject.toml'
        config.write_text('[project]\nname = "fixture"\n')
        resolved = self.resolve('--write-set', 'app.py')
        command = ['aidp_missing_static_tool_fixture']
        first = entry.run_static(self.root, resolved['execution_context'], command, ['app.py'])
        self.assertEqual(first['status'], 'ENV_UNAVAILABLE')
        # 只改ctime，内容和命令都没变，不能伪造新的输入身份绕过失败终止。
        config.write_bytes(config.read_bytes())
        with self.assertRaisesRegex(ValueError, 'ENV_UNAVAILABLE'):
            entry.run_static(self.root, resolved['execution_context'], command, ['app.py'])
        self.assertEqual(len(list(Path(resolved['execution_context']).parent.glob('static-*.json'))), 1)
        budget = json.loads(Path(resolved['execution_context']).with_name('budget.json').read_text())
        self.assertEqual(budget['used']['processes'], 0)

    def test_tool_selection_reads_are_budgeted_and_not_repeated_on_reuse(self):
        import entry_context as entry
        from unittest.mock import patch
        readme = self.root / 'README.md'
        readme.write_text('# Development\nCheck Python syntax for changed files.\n')
        self.git('add', 'README.md'); self.git('commit', '-qm', 'instructions')
        resolved = self.resolve('--write-set', 'app.py')
        argv = [sys.executable, '-B', '-c', "import ast; ast.parse(open('app.py').read())"]
        first = entry.run_static(self.root, resolved['execution_context'], argv, ['app.py'])
        self.assertGreater(first.get('selection_read_cost', {}).get('content_reads', 0), 0)
        budget = json.loads(Path(resolved['execution_context']).with_name('budget.json').read_text())
        self.assertEqual(budget['used']['scanned_files'], resolved['snapshot_cost']['hashed_files'] + first['read_cost']['content_reads'])
        with patch('verification_tools.inspect_command', side_effect=AssertionError('unchanged tool selection must not run again')):
            repeated = entry.run_static(self.root, resolved['execution_context'], argv, ['app.py'])
        self.assertTrue(repeated['reused'])
        self.assertEqual(repeated['read_cost']['content_reads'], 0)
        planned = entry.plan_validation(self.root, resolved['execution_context'])
        self.assertGreater(planned['selection_read_cost']['content_reads'], 0)

    def test_tool_disappearing_after_selection_does_not_consume_process_budget(self):
        import entry_context as entry
        from unittest.mock import patch
        resolved = self.resolve('--write-set', 'app.py')
        actual_run = entry.subprocess.run
        def disappeared(argv, **kwargs):
            if argv[0] == sys.executable:
                raise FileNotFoundError('tool disappeared after selection')
            return actual_run(argv, **kwargs)
        with patch.object(entry.subprocess, 'run', side_effect=disappeared):
            result = entry.run_static(self.root, resolved['execution_context'],
                [sys.executable, '-B', '-c', "import ast; ast.parse(open('app.py').read())"], ['app.py'])
        self.assertEqual(result['status'], 'ENV_UNAVAILABLE')
        self.assertFalse(result['executed'])
        budget = json.loads(Path(resolved['execution_context']).with_name('budget.json').read_text())
        self.assertEqual(budget['used']['processes'], 0)
        self.assertIn('disappeared', result['result']['stderr'])

    def test_module_tool_new_members_invalidate_precise_file_evidence(self):
        import entry_context as entry
        (self.root / 'src').mkdir()
        (self.root / 'src/app.ts').write_text('export const answer = 1;\n')
        (self.root / 'tsconfig.json').write_text('{"include":["src/**/*.ts"]}')
        tool = self.root / 'bin/tsc'
        tool.parent.mkdir(); tool.write_text('#!/bin/sh\nexit 0\n'); tool.chmod(0o755)
        self.git('add', '.'); self.git('commit', '-qm', 'typescript fixture')
        resolved = self.resolve('--write-set', 'src/app.ts')
        result = entry.run_static(self.root, resolved['execution_context'], ['bin/tsc', '--noEmit'], ['src/app.ts'])
        self.assertEqual(result['status'], 'PASS')
        (self.root / 'src/added.ts').write_text('export const additional = 2;\n')
        checked = entry.check_completion(self.root, resolved['execution_context'], static_evidence=result['evidence_file'])
        self.assertFalse(checked['ready'])

    def test_validator_rule_change_invalidates_old_static_pass_without_reinspection(self):
        import entry_context as entry
        import verification_tools
        from unittest.mock import patch
        rule = self.root / 'checker_rule.py'
        rule.write_text('# validator policy one\n')
        resolved = self.resolve('--write-set', 'app.py')
        with patch.object(verification_tools, '__file__', str(rule)):
            first = entry.run_static(self.root, resolved['execution_context'],
                [sys.executable, '-B', '-c', "import ast; ast.parse(open('app.py').read())"], ['app.py'])
            rule.write_text('# validator policy two\n')
            with patch.object(verification_tools, 'inspect_command', side_effect=AssertionError('check must not rerun selection')):
                checked = entry.check_completion(self.root, resolved['execution_context'], static_evidence=first['evidence_file'])
        self.assertFalse(checked['ready'])

    def test_plan_validation_zero_scan_budget_stops_before_reading_project_text(self):
        import entry_context as entry
        from unittest.mock import patch
        readme = self.root / 'README.md'
        readme.write_text('# Development\nCheck Python files.\n')
        self.git('add', 'README.md'); self.git('commit', '-qm', 'readme')
        resolved = self.resolve('--execution-budget', '{"scanned_files":0}')
        read_bytes = Path.read_bytes
        reads = []
        def observed(path):
            if path == readme:
                reads.append(path)
            return read_bytes(path)
        with patch.object(Path, 'read_bytes', new=observed):
            with self.assertRaisesRegex(ValueError, 'BUDGET_EXCEEDED'):
                entry.plan_validation(self.root, resolved['execution_context'])
        self.assertEqual(reads, [])

    def test_invalid_context_paths_and_corruption_fail_closed(self):
        resolved = self.resolve()
        path = Path(resolved["execution_context"])
        outside = self.root / "context.json"
        outside.write_bytes(path.read_bytes())
        self.cli("route", "--execution-context", str(outside), expected=2)
        self.cli("route", "--execution-context", "../context.json", expected=2)
        ctx = self.context(resolved)
        ctx["mode"] = "formal"
        path.write_text(json.dumps(ctx))
        self.cli("route", "--execution-context", str(path), expected=2)

    def test_illegal_write_paths_and_symlink_runtime_rejected(self):
        for path in ("../escape", "/tmp/escape", ".git/config", "memory/.aidp/x", "."):
            self.cli("resolve", "--entry", "sprint-dev", "--version", "V1", "--write-set", path, expected=2)
        with tempfile.TemporaryDirectory() as outside:
            (self.root / "escape").symlink_to(outside, target_is_directory=True)
            self.cli("resolve", "--entry", "sprint-dev", "--version", "V1", "--write-set", "escape/file", expected=2)
            (self.root / "memory").symlink_to(outside, target_is_directory=True)
            self.cli("resolve", "--entry", "sprint-dev", "--version", "V1", expected=2)

    def test_no_git_records_unsupported_without_fabricating_since(self):
        with tempfile.TemporaryDirectory() as outside:
            result = self.cli("resolve", "--entry", "sprint-dev", "--version", "V1", root=outside)
            ctx = self.context(result)
            self.assertIsNone(ctx["since"])
            self.assertEqual(ctx["git_status"], "unsupported")
            self.cli("resolve", "--entry", "sprint-dev", "--version", "V1", "--since", self.head, root=outside, expected=2)

    def test_formal_fork_freezes_per_sprint_start_and_reuses_child(self):
        parent = self.cli("resolve", "--entry", "sprint-batch", "--version", "V1")
        before = Path(parent["execution_context"]).read_bytes()
        (self.root / "app.py").write_text("answer = 3\n")
        self.git("add", "app.py")
        self.git("commit", "-qm", "before sprint")
        start = self.git("rev-parse", "HEAD").strip()
        child = self.cli("fork", "--execution-context", parent["execution_context"], "--sprint", "003")
        ctx = self.context(child)
        self.assertEqual(ctx["since"], start)
        self.assertEqual(ctx["parent_task_id"], parent["task_id"])
        self.assertEqual(ctx["mode"], "formal")
        self.assertEqual(before, Path(parent["execution_context"]).read_bytes())
        (self.root / "app.py").write_text("answer = 4\n")
        self.git("add", "app.py")
        self.git("commit", "-qm", "after sprint")
        retry = self.cli("fork", "--execution-context", parent["execution_context"], "--sprint", "003")
        self.assertEqual(retry["identity_hash"], child["identity_hash"])
        second = self.cli("fork", "--execution-context", parent["execution_context"], "--sprint", "004", "--since", start)
        self.assertNotEqual(second["task_id"], child["task_id"])
        self.cli("fork", "--execution-context", parent["execution_context"], "--sprint", "003", "--since", self.head, expected=2)

    def test_formal_bind_is_explicit_and_light_cannot_bind_or_fork(self):
        light = self.resolve()
        for command in ("fork", "bind-sprint"):
            self.cli(command, "--execution-context", light["execution_context"], "--sprint", "001", expected=2)
        formal = self.cli("resolve", "--entry", "sprint-full", "--version", "V1")
        bound = self.cli("bind-sprint", "--execution-context", formal["execution_context"], "--sprint", "001", "--since", self.head)
        self.assertEqual(bound["task_id"], formal["task_id"])
        self.assertEqual(bound["revision"], 2)
        retry = self.cli("bind-sprint", "--execution-context", formal["execution_context"], "--sprint", "001")
        self.assertEqual(retry["identity_hash"], bound["identity_hash"])
        self.cli("bind-sprint", "--execution-context", formal["execution_context"], "--sprint", "002", expected=2)

    def ledger_cli(self, action, resolved, *args, expected=0):
        command = [sys.executable, str(SCRIPTS / "test_ledger.py"), action,
                   "--root", str(self.root), "--execution-context", resolved["execution_context"],
                   "--env-id", "entry-test", *args]
        proc = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(proc.returncode, expected, proc.stdout + proc.stderr)
        return json.loads(proc.stdout.splitlines()[-1])

    def install_test(self):
        (self.root / "tests").mkdir()
        (self.root / "tests/test_app.py").write_text(
            "import unittest\nfrom pathlib import Path\n"
            "class AppTest(unittest.TestCase):\n"
            " def test_answer(self): self.assertEqual(Path('app.py').read_text(), 'answer = 2\\n')\n"
            "if __name__ == '__main__': unittest.main()\n")
        self.git("add", "tests")
        self.git("commit", "-qm", "add test")

    def authorize_verification(self, resolved):
        resolved.update(self.cli("revise", "--execution-context", resolved["execution_context"],
            "--grant", "related-test", "--grant", "review", "--authorization-source",
            json.dumps({"kind": "user-text", "request_id": "fixture-related-review",
                        "text": "本测试明确执行相关测试并代码审查"})))

    def scope(self, resolved, with_runner=True):
        self.authorize_verification(resolved)
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        from test_scope import derive
        runners = [{"cwd": ".", "suffixes": [".py"], "argv": [sys.executable, "-B", "{tests}"]}] if with_runner else []
        plan = derive(self.root, None, runners, execution_context=resolved["execution_context"])
        path = Path(resolved["execution_context"]).with_name("scope.json")
        path.write_text(json.dumps(plan))
        return plan, ["--scope-file", str(path), "--scope-hash", plan["scope_hash"]]

    def review(self, resolved, plan, scope_args, run_ids):
        report = Path(resolved["execution_context"]).with_name("review.json")
        report.write_text(json.dumps({"schema": 1, "kind": "code-review", "status": "PASS",
            "scope_hash": plan["scope_hash"], "execution_context": resolved["identity"],
            "reviewer": "entry-context-test-fixture", "checks": [
                {"kind": "code-review", "status": "PASS", "evidence": ["test fixture: inspected app.py answer assignment"]}],
            "findings": []}))
        ids = [arg for run_id in run_ids for arg in ("--run-id", run_id)]
        self.ledger_cli("record-review", resolved, "--name", "task-close", "--report", str(report), *scope_args, *ids)
        inputs = sorted(set(self.context(resolved)["write_set"]) | set(plan["changed"])) or ["app.py"]
        # 实际只读解析/读取任务输入，运行状态不污染范围快照。
        static = self.cli("static", "--execution-context", resolved["execution_context"],
            *[argument for name in inputs for argument in ("--input", name)], "--", sys.executable, "-B", "-c",
            "import ast; from pathlib import Path; [ast.parse(Path(p).read_text()) for p in " + repr(inputs) + " if Path(p).is_file() and Path(p).suffix == '.py']")
        return [*scope_args, "--env-id", "entry-test", "--review-name", "task-close", *ids,
                "--static-evidence", static["evidence_file"]]

    def test_real_tests_review_and_completion_need_same_task_and_current_revision(self):
        self.install_test()
        resolved = self.resolve("--write-set", "app.py")
        (self.root / "app.py").write_text("answer = 2\n")
        plan, args = self.scope(resolved)
        runs = self.ledger_cli("run-scope", resolved, *args[:2])
        self.assertEqual(runs["status"], "PASS")
        evidence = self.review(resolved, plan, args, runs["run_ids"])
        ready = self.cli("check", "--execution-context", resolved["execution_context"], *evidence)
        self.assertTrue(ready["ready"])
        self.assertFalse(ready["completed"])
        other = self.resolve("--write-set", "app.py")
        self.cli("complete", "--execution-context", other["execution_context"], *evidence, expected=2)
        completed = self.cli("complete", "--execution-context", resolved["execution_context"], *evidence)
        self.assertTrue(completed["completed"])
        self.assertEqual(completed["status"], "PASS")
        self.assertEqual(self.context(resolved)["status"], "completed")
        self.assertEqual(self.context(resolved)["identity_hash"], resolved["identity_hash"])
        self.assertFalse((self.root / "docs").exists())
        self.cli("revise", "--execution-context", resolved["execution_context"], "--write-set", "other.py")
        self.cli("complete", "--execution-context", resolved["execution_context"], *evidence, expected=2)
        self.assertEqual(self.context(resolved)["status"], "active")

    def test_real_failed_test_and_unexecuted_scope_never_complete(self):
        self.install_test()
        resolved = self.resolve("--write-set", "app.py")
        (self.root / "app.py").write_text("answer = 0\n")
        plan, args = self.scope(resolved)
        self.cli("complete", "--execution-context", resolved["execution_context"], *args,
                 "--env-id", "entry-test", "--review-name", "task-close", expected=2)
        runs = self.ledger_cli("run-scope", resolved, *args[:2], expected=1)
        self.assertEqual(runs["status"], "FAIL")
        ids = [arg for run_id in runs["run_ids"] for arg in ("--run-id", run_id)]
        result = self.cli("complete", "--execution-context", resolved["execution_context"], *args,
                          "--env-id", "entry-test", "--review-name", "task-close", *ids, expected=2)
        self.assertFalse(result["completed"])
        self.assertEqual(self.context(resolved)["status"], "active")

    def test_no_related_tests_cannot_complete_or_fabricate_pass_or_run(self):
        resolved = self.resolve("--write-set", "app.py")
        (self.root / "app.py").write_text("answer = 2\n")
        plan, args = self.scope(resolved, with_runner=False)
        self.assertFalse(plan["runs"])
        static = self.cli("static", "--execution-context", resolved["execution_context"], "--input", "app.py", "--",
            sys.executable, "-B", "-c", "import ast; ast.parse(open('app.py').read())")
        completed = self.cli("complete", "--execution-context", resolved["execution_context"], *args,
            "--env-id", "entry-test", "--static-evidence", static["evidence_file"], expected=2)
        self.assertFalse(completed["completed"])
        self.assertEqual(completed["status"], "UNVERIFIED")
        self.assertFalse(completed["development_completed"])
        self.assertEqual(completed["run_ids"], [])
        self.assertEqual(completed["unmapped"], ["app.py"])
        self.assertEqual(self.context(resolved)["status"], "active")

    def test_completed_evidence_goes_stale_and_revokes_completed_status(self):
        self.install_test()
        resolved = self.resolve("--write-set", "app.py")
        (self.root / "app.py").write_text("answer = 2\n")
        plan, args = self.scope(resolved)
        runs = self.ledger_cli("run-scope", resolved, *args[:2])
        evidence = self.review(resolved, plan, args, runs["run_ids"])
        self.cli("complete", "--execution-context", resolved["execution_context"], *evidence)
        (self.root / "app.py").write_text("answer = 0\n")
        self.cli("complete", "--execution-context", resolved["execution_context"], *evidence, expected=2)
        self.assertEqual(self.context(resolved)["status"], "active")
        self.assertEqual(self.context(resolved)["identity_hash"], resolved["identity_hash"])

    def test_formal_test_evidence_does_not_replace_formal_close_gates(self):
        self.install_test()
        resolved = self.resolve("--sprint", "007", "--write-set", "app.py")
        (self.root / "app.py").write_text("answer = 2\n")
        plan, args = self.scope(resolved)
        runs = self.ledger_cli("run-scope", resolved, *args[:2])
        evidence = self.review(resolved, plan, args, runs["run_ids"])
        self.cli("check", "--execution-context", resolved["execution_context"], *evidence)
        completed = self.cli("complete", "--execution-context", resolved["execution_context"], *evidence, expected=2)
        self.assertEqual(completed["status"], "FORMAL_GATES_REQUIRED")
        self.assertEqual(self.context(resolved)["status"], "active")

    def test_loaded_dict_cannot_bypass_revision_or_frozen_checksum(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        from entry_context import validate_context, ContextError, _digest
        resolved = self.resolve("--write-set", "app.py")
        original = self.context(resolved)
        altered = dict(original, since="0" * 40)
        altered["checksum"] = _digest({k: v for k, v in altered.items() if k != "checksum"})
        with self.assertRaises(ContextError):
            validate_context(self.root, altered)
        self.cli("revise", "--execution-context", resolved["execution_context"], "--write-set", "other.py")
        with self.assertRaises(ContextError):
            validate_context(self.root, original)

    def test_completion_preserves_existing_sprint_artifacts_byte_for_byte(self):
        state_paths = ("memory/activeContext.md", "memory/progress.md", "memory/.sprint-autopilot-baseline.json")
        for rel in state_paths:
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("Sprint 007 in progress\n")
        before = {rel: (self.root / rel).read_bytes() for rel in state_paths}
        self.install_test()
        resolved = self.resolve("--write-set", "app.py")
        (self.root / "app.py").write_text("answer = 2\n")
        plan, args = self.scope(resolved)
        runs = self.ledger_cli("run-scope", resolved, *args[:2])
        evidence = self.review(resolved, plan, args, runs["run_ids"])
        self.cli("complete", "--execution-context", resolved["execution_context"], *evidence)
        self.assertEqual(before, {rel: (self.root / rel).read_bytes() for rel in state_paths})
        self.assertFalse((self.root / "docs").exists())

    def test_completion_reuses_family_gate_without_cascading_normal_pending(self):
        self.install_test()
        resolved = self.resolve("--write-set", "app.py")
        (self.root / "app.py").write_text("answer = 2\n")
        ledger = self.root / "docs/design/detail/V1.0.0/_开发期设计增量.md"
        ledger.parent.mkdir(parents=True)
        ledger.write_text("<!-- task:" + resolved["task_id"] + " -->\n## 待级联\n- C-001 · 11-09 · answer调整 · task\n")
        original = ledger.read_bytes()
        plan, args = self.scope(resolved)
        runs = self.ledger_cli("run-scope", resolved, *args[:2])
        evidence = self.review(resolved, plan, args, runs["run_ids"])
        result = self.cli("complete", "--execution-context", resolved["execution_context"], *evidence)
        self.assertTrue(result["completed"])
        self.assertEqual(result["blocking_obligations"], [])
        self.assertEqual(result["version_obligations"]["cascade"]["total"], 1)
        self.assertEqual(ledger.read_bytes(), original)

    def test_current_family_damage_blocks_but_old_other_version_debt_is_reported(self):
        self.install_test()
        resolved = self.resolve("--write-set", "app.py")
        (self.root / "app.py").write_text("answer = 2\n")
        old = self.root / "docs/design/detail/V0.0.1/_开发期设计增量.md"
        old.parent.mkdir(parents=True)
        old.write_text("## 待级联\nunrecognized entry one\nunrecognized entry two\n")
        plan, args = self.scope(resolved)
        runs = self.ledger_cli("run-scope", resolved, *args[:2])
        evidence = self.review(resolved, plan, args, runs["run_ids"])
        allowed = self.cli("check", "--execution-context", resolved["execution_context"], *evidence)
        self.assertTrue(allowed["ready"])
        self.assertEqual(allowed["external_obligations"], [])  # 普通任务不扫描其他版本历史册。
        current = self.root / "docs/design/detail/V1.0.0/_开发期设计增量.md"
        current.parent.mkdir(parents=True)
        for body, code in (("first unknown\nsecond unknown\n", "cascade-unparsed"),
                           ("- C-001 · 11-09 · 已级联\n", "cascade-not-cleaned"),
                           ("<!-- LEDGER-ARCHIVED -->\n- C-001 · 11-09 · change\n", "cascade-archived-not-deleted"),
                           ("- C-001 · 11-09 · \\U0001f534 breaking contract\n", "cascade-destructive-unregistered")):
            current.write_text("<!-- task:" + resolved["task_id"] + " -->\n## 待级联\n" + body.replace("\\U0001f534", chr(0x1F534)))
            before = current.read_bytes()
            blocked = self.cli("complete", "--execution-context", resolved["execution_context"], *evidence, expected=2)
            self.assertEqual(blocked["status"], "BLOCKED_OBLIGATIONS")
            self.assertIn(code, blocked["blocking_obligations"])
            self.assertEqual(current.read_bytes(), before)
            self.assertEqual(self.context(resolved)["status"], "active")

    def test_missing_evidence_and_pending_authorization_never_complete(self):
        resolved = self.resolve()
        result = self.cli("complete", "--execution-context", resolved["execution_context"], expected=2)
        self.assertFalse(result["completed"])
        self.assertEqual(self.context(resolved)["status"], "active")
        result = self.cli("complete", "--execution-context", resolved["execution_context"], "--pending-authorization", "deploy production", expected=2)
        self.assertEqual(result["status"], "UNVERIFIED")  # 未授权deploy不阻塞；此处仍缺真实static证据。
        self.assertEqual(self.context(resolved)["status"], "active")


if __name__ == "__main__":
    unittest.main()
