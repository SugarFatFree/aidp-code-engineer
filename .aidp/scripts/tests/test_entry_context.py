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

    def test_empty_minor_can_complete_without_fabricating_pass_or_run(self):
        resolved = self.resolve("--write-set", "app.py")
        (self.root / "app.py").write_text("answer = 2\n")
        plan, args = self.scope(resolved, with_runner=False)
        self.assertFalse(plan["runs"])
        evidence = self.review(resolved, plan, args, [])
        completed = self.cli("complete", "--execution-context", resolved["execution_context"], *evidence)
        self.assertTrue(completed["completed"])
        self.assertEqual(completed["status"], "EMPTY")
        self.assertTrue(completed["minor"])
        self.assertEqual(completed["run_ids"], [])
        self.assertEqual(completed["unmapped"], ["app.py"])

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
        resolved = self.resolve("--write-set", "app.py")
        (self.root / "app.py").write_text("answer = 2\n")
        plan, args = self.scope(resolved, with_runner=False)
        evidence = self.review(resolved, plan, args, [])
        self.cli("complete", "--execution-context", resolved["execution_context"], *evidence)
        self.assertEqual(before, {rel: (self.root / rel).read_bytes() for rel in state_paths})
        self.assertFalse((self.root / "docs").exists())

    def test_completion_reuses_family_gate_without_cascading_normal_pending(self):
        resolved = self.resolve("--write-set", "app.py")
        (self.root / "app.py").write_text("answer = 2\n")
        ledger = self.root / "docs/design/detail/V1.0.0/_开发期设计增量.md"
        ledger.parent.mkdir(parents=True)
        ledger.write_text("<!-- task:" + resolved["task_id"] + " -->\n## 待级联\n- C-001 · 11-09 · answer调整 · task\n")
        original = ledger.read_bytes()
        plan, args = self.scope(resolved, with_runner=False)
        evidence = self.review(resolved, plan, args, [])
        result = self.cli("complete", "--execution-context", resolved["execution_context"], *evidence)
        self.assertTrue(result["completed"])
        self.assertEqual(result["blocking_obligations"], [])
        self.assertEqual(result["version_obligations"]["cascade"]["total"], 1)
        self.assertEqual(ledger.read_bytes(), original)

    def test_current_family_damage_blocks_but_old_other_version_debt_is_reported(self):
        resolved = self.resolve("--write-set", "app.py")
        (self.root / "app.py").write_text("answer = 2\n")
        old = self.root / "docs/design/detail/V0.0.1/_开发期设计增量.md"
        old.parent.mkdir(parents=True)
        old.write_text("## 待级联\nunrecognized entry one\nunrecognized entry two\n")
        plan, args = self.scope(resolved, with_runner=False)
        evidence = self.review(resolved, plan, args, [])
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
