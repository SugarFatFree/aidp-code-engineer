#!/usr/bin/env python3
"""select_related_tests.py：改动 → 相关测试白名单，不得得出全量/整目录。"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import entry_context as entry
import test_command_guard as guard

SCRIPT = SCRIPTS / "select_related_tests.py"


class SelectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aidp-select-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for args in (("init", "-q"), ("config", "user.name", "S"), ("config", "user.email", "s@example.test")):
            self.git(*args)
        (self.root / ".gitignore").write_text("memory/.aidp/\n")

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True, text=True).stdout

    def write(self, name, text="x = 1\n"):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def commit(self):
        self.git("add", "-A")
        self.git("commit", "-qm", "c")

    def run_select(self, *args, expect=0):
        out = subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.root), "--json", *args],
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, expect, out.stderr)
        return json.loads(out.stdout) if expect == 0 else out

    def test_python_without_runner_uses_naming_and_writes_allowlist(self):
        self.write("src/foo.py"); self.write("src/bar.py")
        self.write("tests/test_foo.py", "from src import foo\n"); self.write("tests/test_bar.py", "from src import bar\n")
        self.commit()
        self.write("src/foo.py", "x = 2\n")
        res = self.run_select()
        self.assertEqual(res["tests"], ["tests/test_foo.py"])
        self.assertEqual(res["allowed_args"], res["tests"])
        self.assertEqual(res["unmapped"], [])
        self.assertEqual(res["allowlist_file"], "memory/.aidp/test-allowlist/default.json")
        stored = json.loads((self.root / res["allowlist_file"]).read_text())
        self.assertEqual(stored["tests"], ["tests/test_foo.py"])
        # 与护栏联动：白名单内放行，白名单外拒绝
        self.assertTrue(guard.evaluate("pytest tests/test_foo.py", str(self.root))["allowed"])
        self.assertFalse(guard.evaluate("pytest tests/test_bar.py", str(self.root))["allowed"])

    def test_untracked_new_source_and_new_test_are_included(self):
        self.write("tests/test_old.py"); self.write("old.py"); self.commit()
        self.write("newmod.py"); self.write("tests/test_newmod.py")
        res = self.run_select()
        self.assertIn("tests/test_newmod.py", res["tests"])
        self.assertNotIn("tests/test_old.py", res["tests"])

    def test_source_without_test_is_unmapped_and_docs_only_is_empty(self):
        self.write("lonely.py"); self.write("tests/test_other.py"); self.commit()
        self.write("lonely.py", "y = 2\n")
        res = self.run_select()
        self.assertEqual(res["tests"], [])
        self.assertEqual(res["unmapped"], ["lonely.py"])
        self.git("checkout", "lonely.py")
        self.write("docs/readme.md", "hi\n")
        res = self.run_select()
        self.assertEqual(res["tests"], [])
        self.assertTrue(res["basis"]["note"])

    def import_fixture(self, count, unrelated=False):
        if unrelated:
            self.write("tests/test_unrelated.py", "x = 1\n")
        self.write("app.py")
        self.write("tests/__init__.py", "")
        tests = [f"tests/test_m{i:02}.py" for i in range(count)]
        for test in tests:
            self.write(test, "import app\nimport unittest\nclass AppTest(unittest.TestCase):\n"
                             "    def test_value(self):\n        self.assertEqual(app.x, 2)\n")
        self.commit()
        ctx = entry.resolve_context(self.root, "sprint-dev", version="V1", write_set=["app.py"],
            authorization_source={"kind": "user-text", "request_id": "r1", "text": "跑相关测试"})
        self.write("app.py", "x = 2\n")
        return ctx["execution_context"], tests

    def assert_scope_allowed(self, ctx, tests, *args):
        res = self.run_select("--execution-context", ctx, *args)
        self.assertEqual(res["tests"], tests)
        self.assertEqual(res["allowed_args"], tests)
        self.assertTrue(guard.evaluate("pytest " + " ".join(tests), self.root,
                                      execution_context=ctx)["allowed"])
        for command in ("pytest", "pytest tests", "pytest --allow-full"):
            self.assertFalse(guard.evaluate(command, self.root, execution_context=ctx)["allowed"])
        executed = subprocess.run([sys.executable, str(SCRIPTS / "test_command_guard.py"), "wrap",
            "--root", str(self.root), "--execution-context", ctx, "--", sys.executable,
            "-m", "unittest", *tests], capture_output=True, text=True)
        self.assertEqual(executed.returncode, 0, executed.stderr)
        self.assertIn(f"Ran {len(tests)} tests", executed.stderr)
        return res

    def test_all_four_import_related_files_are_kept(self):
        ctx, tests = self.import_fixture(4)
        self.assert_scope_allowed(ctx, tests)

    def test_more_than_thirty_import_related_files_are_kept(self):
        # 额外无关测试使“全仓测试”分支不触发，单独验证原默认 30 截断。
        ctx, tests = self.import_fixture(32, unrelated=True)
        self.assert_scope_allowed(ctx, tests)

    def test_explicit_budget_failure_does_not_publish_partial_allowlist(self):
        ctx, _ = self.import_fixture(4)
        out = self.run_select("--execution-context", ctx, "--max-tests", "2", expect=2)
        self.assertIn("BUDGET_EXCEEDED", out.stderr)
        self.assertFalse(list((self.root / "memory/.aidp/test-allowlist").glob("*.json")))

    def test_invalid_context_and_runner_errors_never_fall_back_to_naming(self):
        self.write("app.py"); self.write("tests/test_app.py"); self.commit()
        self.write("app.py", "x = 2\n")
        bogus = self.root / "memory/.aidp/bogus.json"
        bogus.parent.mkdir(parents=True, exist_ok=True)
        bogus.write_text(json.dumps({"task_id": "bogus", "since": self.git("rev-parse", "HEAD").strip(),
                                     "write_set": ["app.py"]}))
        self.run_select("--execution-context", str(bogus), expect=2)
        self.run_select("--runners-json", json.dumps([{"suffixes": [".py"], "argv": ["pytest"]}]), expect=2)
        self.assertFalse(list((self.root / "memory/.aidp/test-allowlist").glob("*.json")))

    def test_derive_budget_failure_does_not_fall_back_to_naming(self):
        self.write("app.py"); self.write("tests/test_app.py"); self.commit()
        ctx = entry.resolve_context(self.root, "sprint-dev", version="V1", write_set=["app.py"],
            execution_budget={"elapsed_seconds": 0},
            authorization_source={"kind": "user-text", "request_id": "budget", "text": "跑相关测试"})
        self.write("app.py", "x = 2\n")
        out = self.run_select("--execution-context", ctx["execution_context"], expect=2)
        self.assertIn("BUDGET_EXCEEDED", out.stderr)
        self.assertFalse(list((self.root / "memory/.aidp/test-allowlist").glob("*.json")))

    def test_scope_with_changed_inputs_is_rejected(self):
        import test_scope
        ctx, _ = self.import_fixture(4)
        scope = test_scope.derive(self.root, "", [], execution_context=ctx)
        scope_path = self.root / "memory/.aidp/scope.json"
        scope_path.write_text(json.dumps(scope))
        self.write("app.py", "x = 3\n")
        out = self.run_select("--execution-context", ctx, "--scope", str(scope_path), expect=2)
        self.assertIn("当前树", out.stderr)
        self.assertFalse(list((self.root / "memory/.aidp/test-allowlist").glob("*.json")))

    def test_context_write_set_conflict_is_rejected(self):
        ctx, _ = self.import_fixture(4)
        self.run_select("--execution-context", ctx, "--write-set", "other.py", expect=2)

    def test_existing_scope_is_exact_allowlist_and_wrong_task_is_rejected(self):
        import test_scope
        ctx, tests = self.import_fixture(4)
        scope = test_scope.derive(self.root, "", [{"suffixes": [".py"],
            "argv": [sys.executable, "-m", "unittest", "{tests}"]}], execution_context=ctx)
        scope_path = self.root / "memory/.aidp/scope.json"
        scope_path.write_text(json.dumps(scope))
        self.assert_scope_allowed(ctx, tests, "--scope", str(scope_path))
        other = entry.resolve_context(self.root, "sprint-dev", version="V1", write_set=["app.py"],
            authorization_source={"kind": "user-text", "request_id": "r2", "text": "另一个任务"})
        self.run_select("--execution-context", other["execution_context"], "--scope", str(scope_path), expect=2)
        scope["tests"] = tests[:1]
        scope_path.write_text(json.dumps(scope))
        self.run_select("--execution-context", ctx, "--scope", str(scope_path), expect=2)

    def test_other_ecosystems_by_naming_convention(self):
        self.write("src/main/java/a/Foo.java"); self.write("src/test/java/a/FooTest.java")
        self.write("src/main/java/a/Baz.java"); self.write("src/test/java/a/BazTest.java")
        self.write("pkg/util.go"); self.write("pkg/util_test.go"); self.write("pkg/other_test.go")
        self.write("web/src/x.ts"); self.write("web/src/x.test.ts"); self.write("web/package.json", "{}")
        self.commit()
        for f in ("src/main/java/a/Foo.java", "pkg/util.go", "web/src/x.ts"):
            self.write(f, "// changed\n")
        res = self.run_select()
        self.assertEqual(sorted(res["tests"]), ["pkg/util_test.go", "src/test/java/a/FooTest.java", "web/src/x.test.ts"])
        self.assertEqual(res["unmapped"], [])

    def test_execution_context_names_allowlist_by_task_id(self):
        self.write("app.py"); self.write("tests/test_app.py"); self.commit()
        ctx = entry.resolve_context(self.root, "sprint-dev", version="V1", write_set=["app.py"],
            authorization_source={"kind": "user-text", "request_id": "r1", "text": "跑相关测试"})
        self.write("app.py", "x = 3\n")
        res = self.run_select("--execution-context", ctx["execution_context"])
        self.assertEqual(res["tests"], ["tests/test_app.py"])
        self.assertEqual(res["allowlist_file"], f"memory/.aidp/test-allowlist/{ctx['task_id']}.json")
        self.assertTrue((self.root / res["allowlist_file"]).is_file())

    def test_input_errors_exit_2(self):
        out = subprocess.run([sys.executable, str(SCRIPT), "--root", self.temp.name + "/nope", "--json"], capture_output=True, text=True)
        self.assertEqual(out.returncode, 2)
        self.write("a.py"); self.commit()
        self.run_select("--execution-context", str(self.root / "missing.json"), expect=2)
        self.run_select("--runners-json", "{bad", expect=2)
        self.run_select("--since", "no-such-ref", expect=2)


if __name__ == "__main__":
    unittest.main()
