#!/usr/bin/env python3
"""test_command_guard.py：测试范围机器强制（目录/无参数/白名单/授权 fail closed/git stash/wrap）。"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
for p in (str(SCRIPTS), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)
import entry_context as entry
import test_command_guard as guard
import test_execution_policy as policy_tests

SCRIPT = SCRIPTS / "test_command_guard.py"


class GuardBase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aidp-guard-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for args in (("init", "-q"), ("config", "user.name", "G"), ("config", "user.email", "g@example.test")):
            self.git(*args)
        (self.root / ".gitignore").write_text("memory/.aidp/\n")
        (self.root / "app.py").write_text("value = 1\n")
        for name in ("tests/unit/test_a.py", "tests/unit/test_b.py", "tests/test_c.py"):
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
            (self.root / name).write_text("def test_x(): pass\n")
        self.git("add", ".")
        self.git("commit", "-qm", "initial")
        self.old_env = os.environ.pop("AIDP_EXECUTION_CONTEXT", None)

    def tearDown(self):
        if self.old_env is not None:
            os.environ["AIDP_EXECUTION_CONTEXT"] = self.old_env

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True, text=True).stdout

    def ev(self, command, **kw):
        return guard.evaluate(command, str(self.root), **kw)

    def allowlist(self, tests, key="default"):
        path = self.root / guard.ALLOWLIST_DIR / f"{key}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"task_id": key, "tests": tests}))
        return path

    def context(self):
        return entry.resolve_context(self.root, "sprint-dev", version="V1", write_set=["app.py"],
            authorization_source={"kind": "user-text", "request_id": "r1", "text": "跑相关测试"})


class RuleTests(GuardBase):
    def test_denied_when_no_args_or_directory(self):
        for cmd in ("pytest", "python3 -m pytest -x", "pytest tests", "pytest tests/unit/", "pytest .",
                    "bash scripts/run_tests.sh tests/unit", "./run_tests.sh", "timeout 300 pytest -q",
                    "cd tests && pytest", "FOO=1 pytest -n 4", "uv run pytest", "pytest -k foo",
                    "bash -c 'pytest tests'", "npm test", "npx jest", "vitest run", "mvn test", "mvn verify -pl core",
                    "./gradlew test", "go test ./...", "go test", "cargo test", "make test",
                    "git diff --name-only | xargs pytest"):
            res = self.ev(cmd)
            self.assertFalse(res["allowed"], cmd)
            self.assertTrue(res["hint"], cmd)

    def test_explicit_file_allowed_without_allowlist_with_warning(self):
        res = self.ev("pytest tests/unit/test_a.py")
        self.assertTrue(res["allowed"])
        self.assertEqual(res["kind"], "pytest")
        self.assertIn("白名单", res["hint"])
        for cmd in ("python -m pytest -x -k foo tests/unit/test_a.py::T::test_x 2>&1 | tail -5",
                    "cd tests && pytest unit/test_a.py", "FOO=1 timeout 60 pytest tests/test_c.py -q",
                    "npx vitest run tests/test_c.py"):
            self.assertTrue(self.ev(cmd)["allowed"], cmd)

    def test_allowlist_subset_enforced(self):
        self.allowlist(["tests/unit/test_a.py"])
        self.assertTrue(self.ev("pytest tests/unit/test_a.py")["allowed"])
        self.assertTrue(self.ev("pytest tests/unit/test_a.py::T::test_x")["allowed"])
        self.assertTrue(self.ev("cd tests/unit && pytest test_a.py")["allowed"])
        out = self.ev("pytest tests/unit/test_a.py tests/test_c.py")
        self.assertFalse(out["allowed"])
        self.assertIn("select_related_tests", out["hint"])
        self.assertFalse(self.ev("bash scripts/run_tests.sh tests/test_c.py")["allowed"])
        self.assertFalse(self.ev("mvn test -Dtest=FooTest")["allowed"])
        self.allowlist(["src/test/java/FooTest.java"])
        self.assertTrue(self.ev("mvn test -Dtest=FooTest#bar")["allowed"])
        self.assertFalse(self.ev("mvn test -Dtest=*Test")["allowed"])
        self.assertTrue(self.ev("mvn package -DskipTests")["allowed"])

    def test_python_test_script_uses_same_task_allowlist(self):
        ctx = self.context()
        self.allowlist(["tests/unit/test_a.py"], ctx["task_id"])
        self.assertTrue(self.ev("python3 -B tests/unit/test_a.py", execution_context=ctx["execution_context"])["allowed"])
        self.assertFalse(self.ev("python3 -B tests/test_c.py", execution_context=ctx["execution_context"])["allowed"])

    def test_node_and_package_script_runners_enforce_scope(self):
        self.allowlist(["tests/one.test.js"])
        for command in ("node --test", "node --test tests", "node --test tests/two.test.js",
                        "node --test --test-name-pattern x tests/two.test.js",
                        "yarn run test", "npm run test", "pnpm run test",
                        "yarn run test tests/two.test.js", "npm run test -- tests/two.test.js",
                        "pnpm run test tests/two.test.js"):
            with self.subTest(command=command):
                self.assertFalse(self.ev(command)["allowed"], command)
        for command in ("node --test tests/one.test.js", "node --test --test-name-pattern x tests/one.test.js",
                        "yarn run test tests/one.test.js", "npm run test -- tests/one.test.js",
                        "pnpm run test tests/one.test.js"):
            with self.subTest(command=command):
                self.assertTrue(self.ev(command)["allowed"], command)
                self.assertNotEqual(self.ev(command)["kind"], "none")
        self.assertEqual(self.ev("node scripts/build.js")["kind"], "none")
        self.assertEqual(self.ev("yarn run build")["kind"], "none")

    def test_context_key_selects_allowlist(self):
        ctx = self.context()
        self.allowlist(["tests/test_c.py"], "default")
        self.allowlist(["tests/unit/test_a.py"], ctx["task_id"])
        self.assertTrue(self.ev("pytest tests/unit/test_a.py", execution_context=ctx["execution_context"])["allowed"])
        self.assertFalse(self.ev("pytest tests/test_c.py", execution_context=ctx["execution_context"])["allowed"])

    def test_context_never_borrows_default_or_other_task_allowlist(self):
        ctx = self.context()
        self.allowlist(["tests/test_c.py"], "default")
        self.allowlist(["tests/test_c.py"], "other-task")
        self.assertFalse(self.ev("pytest tests/test_c.py", execution_context=ctx["execution_context"])["allowed"])
        own = self.allowlist(["tests/unit/test_a.py"], ctx["task_id"])
        own.write_text("{bad")
        self.assertFalse(self.ev("pytest tests/test_c.py", execution_context=ctx["execution_context"])["allowed"])
        own.write_text(json.dumps({"task_id": "other-task", "tests": ["tests/test_c.py"]}))
        self.assertFalse(self.ev("pytest tests/test_c.py", execution_context=ctx["execution_context"])["allowed"])

    def test_no_context_does_not_load_latest_task_record(self):
        self.allowlist(["tests/test_c.py"], "other-task")
        self.assertEqual(guard.load_allowlist(self.root, None), (None, None))

    def test_invalid_context_cannot_use_default_allowlist(self):
        self.allowlist(["tests/test_c.py"])
        bogus = self.root / "bogus.json"
        bogus.write_text(json.dumps({"task_id": "bogus"}))
        for context in (str(bogus), str(self.root / "missing.json")):
            self.assertFalse(self.ev("pytest tests/test_c.py", execution_context=context)["allowed"])
        self.assertTrue(self.ev("git status", execution_context=str(bogus))["allowed"])

    def test_ruff_scoped_to_changed_files_only(self):
        self.assertFalse(self.ev("ruff check .")["allowed"])
        self.assertFalse(self.ev("ruff check")["allowed"])
        self.assertFalse(self.ev("ruff check tests --select E")["allowed"])
        self.assertFalse(self.ev("python -m ruff format")["allowed"])
        self.assertTrue(self.ev("ruff check app.py")["allowed"])
        self.assertTrue(self.ev("ruff check --select E app.py tests/test_c.py")["allowed"])
        self.assertTrue(self.ev("ruff --version")["allowed"])

    def test_git_stash_denied_but_restore_allowed(self):
        for cmd in ("git stash", "git stash push -m x", "git stash save x", "git stash -u", "git -C . stash -u",
                    "git stash --include-untracked && pytest tests/test_c.py"):
            res = self.ev(cmd)
            self.assertFalse(res["allowed"], cmd)
            self.assertIn("worktree", res["hint"])
        for cmd in ("git stash pop", "git stash list", "git status", "echo git stash"):
            self.assertTrue(self.ev(cmd)["allowed"], cmd)

    def test_non_test_commands_pass_through(self):
        for cmd in ("ls -la", "grep pytest README.md", "python3 scripts/foo.py", "git diff | head", "echo pytest",
                    "python3 test_command_guard.py wrap -- pytest"):
            res = self.ev(cmd)
            self.assertTrue(res["allowed"], cmd)
            self.assertEqual(res["kind"], "none")

    def test_bootstrap_and_metadata_never_require_test_allowlist(self):
        import re
        from unittest.mock import patch
        ctx = self.context()
        bogus = str(self.root / "missing-context.json")
        text = (SCRIPTS.parent / "flows/sprint-autopilot/phase-3-5b.md").read_text()
        fences = re.findall(r"```bash\n(.*?)```", text, re.S)[:3]
        commands = ["git status", "git rev-parse HEAD", "python3 scripts/foo.py",
                    f"python3 {SCRIPTS}/build_unit_test.py plan-init --root . --version V1",
                    *[fence.replace("{{AIDP_HOME}}", str(SCRIPTS.parent)) for fence in fences]]
        for context in (ctx["execution_context"], bogus):
            for command in commands:
                with self.subTest(context=context, command=command):
                    with patch.object(guard, "load_allowlist", wraps=guard.load_allowlist) as loader:
                        result = self.ev(command, execution_context=context)
                    self.assertTrue(result["allowed"], result)
                    self.assertEqual(result["kind"], "none")
                    loader.assert_not_called()

    def test_only_exact_build_metadata_subcommands_are_exempt(self):
        from unittest.mock import patch
        ctx = self.context()["execution_context"]
        local = SCRIPTS / "build_unit_test.py"
        external = self.root / "build_unit_test.py"
        external.write_text("raise AssertionError('not executed')\n")
        for subcommand in ("plan-init", "freeze", "status"):
            with self.subTest(subcommand=subcommand):
                with patch.object(guard, "load_allowlist", wraps=guard.load_allowlist) as loader:
                    result = self.ev(f"python3 -B {local} {subcommand} --root .", execution_context=ctx)
                self.assertTrue(result["allowed"], result)
                self.assertEqual(result["kind"], "none")
                loader.assert_not_called()
                self.assertFalse(self.ev(f"python3 {external} {subcommand}", execution_context=ctx)["allowed"])
        for tail in ("run", "--self-check", "", "run --version status"):
            with self.subTest(tail=tail):
                result = self.ev(f"python3 {local} {tail}", execution_context=ctx)
                self.assertFalse(result["allowed"], result)
                self.assertEqual(result["kind"], "other-test")
        result = self.ev(f"python3 {local} status && pytest tests/test_c.py", execution_context=ctx)
        self.assertFalse(result["allowed"], result)

    def test_allow_full_without_authorization_fails_closed(self):
        for cmd in ("pytest --allow-full", "bash scripts/run_tests.sh --allow-full", "pytest tests --allow-full"):
            res = self.ev(cmd)
            self.assertFalse(res["allowed"], cmd)
            self.assertIn("allow-full", res["reason"])
        self.assertFalse(self.ev("pytest", allow_full=True)["allowed"])
        # 伪造的上下文路径/普通 sprint-dev 上下文都不能放行
        bogus = self.root / "bogus.json"
        bogus.write_text(json.dumps({"task_id": "x", "root": str(self.root)}))
        self.assertFalse(self.ev("pytest --allow-full", execution_context=str(bogus))["allowed"])
        dev = entry.resolve_context(self.root, "sprint-dev", version="V1", write_set=["app.py"],
            authorization_source={"kind": "user-text", "request_id": "r1", "text": "跑全量"})
        res = self.ev("pytest --allow-full", execution_context=dev["execution_context"])
        self.assertFalse(res["allowed"])

    def test_allow_full_with_real_autopilot_authorization(self):
        helper = type("H", (), {})()
        helper.root, helper.git = self.root, self.git
        manifest_path, _ = policy_tests.ExecutionPolicyTests.version_manifest(helper)
        parent = entry.resolve_context(self.root, "sprint-autopilot", version="V1", write_set=["app.py"],
            authorization_source={"kind": "explicit-command", "command": "/sprint-autopilot",
                                  "request_id": "delegate", "options": ["--skip-dev"]})
        # 根上下文持有委派资格但不得直接执行 full-regression
        self.assertFalse(self.ev("pytest --allow-full", execution_context=parent["execution_context"])["allowed"])
        child = entry.fork_test_build(self.root, parent["execution_context"], "V1", "build-007", manifest=manifest_path)
        ctx = child["execution_context"]
        for cmd in ("pytest --allow-full", "bash scripts/run_tests.sh --allow-full", "pytest tests --allow-full"):
            res = self.ev(cmd, execution_context=ctx)
            self.assertTrue(res["allowed"], (cmd, res))
        os.environ["AIDP_EXECUTION_CONTEXT"] = ctx
        self.assertTrue(self.ev("pytest --allow-full")["allowed"])
        del os.environ["AIDP_EXECUTION_CONTEXT"]
        # 授权不覆盖 git stash
        self.assertFalse(self.ev("git stash --allow-full", execution_context=ctx)["allowed"])


class CliTests(GuardBase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, cwd=self.root)

    def test_check_exit_codes_and_json(self):
        bad = self.run_cli("check", "--command", "pytest tests", "--root", str(self.root), "--json")
        self.assertEqual(bad.returncode, 2)
        self.assertFalse(json.loads(bad.stdout)["allowed"])
        good = self.run_cli("check", "--command", "pytest tests/test_c.py", "--root", str(self.root), "--json")
        self.assertEqual(good.returncode, 0)

    def test_wrap_refuses_then_runs_and_background_marker(self):
        denied = self.run_cli("wrap", "--root", str(self.root), "--", "pytest", "tests")
        self.assertEqual(denied.returncode, 2)
        self.assertIn("拒绝", denied.stderr)
        # 用一个被放行的显式文件命令验证实际执行（python -m pytest 对 unittest 风格无关：检查退出码透传）
        (self.root / "tests/test_ok.py").write_text("def test_ok():\n    assert True\n")
        ran = self.run_cli("wrap", "--root", str(self.root), "--", sys.executable, "-m", "pytest", "-q", "tests/test_ok.py")
        self.assertIn(ran.returncode, (0, 1, 2, 4, 5))  # 环境可能无 pytest；关键是进入了执行而非护栏拒绝
        self.assertNotIn("拒绝", ran.stderr)
        log = self.root / "out" / "bg.log"
        started = self.run_cli("wrap", "--background", "--log", str(log), "--root", str(self.root),
                               "--", sys.executable, "-m", "pytest", "--version")
        self.assertEqual(started.returncode, 0, started.stderr)
        marker = Path(str(log) + ".exit")
        for _ in range(100):
            if marker.exists():
                break
            time.sleep(0.1)
        self.assertTrue(marker.exists())
        self.assertRegex(marker.read_text().strip(), r"^\d+$")
        self.assertTrue(log.exists())

    def test_wrap_allow_full_without_authorization_is_refused(self):
        res = self.run_cli("wrap", "--allow-full", "--root", str(self.root), "--", "pytest")
        self.assertEqual(res.returncode, 2)
        self.assertIn("allow-full", res.stderr)

    def test_changed_lists_modified_and_untracked(self):
        (self.root / "app.py").write_text("value = 2\n")
        (self.root / "new_mod.py").write_text("x = 1\n")
        (self.root / "notes.md").write_text("n\n")
        out = self.run_cli("changed", "--root", str(self.root), "--ext", ".py")
        self.assertEqual(out.stdout.split(), ["app.py", "new_mod.py"])


class BuildRunnerFenceTests(unittest.TestCase):
    def test_real_unit_fence_requires_delegation_and_runs_frozen_manifest(self):
        import re
        from test_build_unit_test import BuildUnitTests, build_unit
        from test_pretool_guard import run_hook
        fixture = BuildUnitTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        plan = fixture.freeze()
        ctx = fixture.delegate(plan)
        manifest = fixture.root / 'memory' / (plan['build'] + '-manifest.json')
        text = (SCRIPTS.parent / 'flows/sprint-aiauto-test/phase-2-unit.md').read_text()
        block = next(b for b in re.findall(r'```bash\n(.*?)```', text, re.S) if 'build_unit_test.py run' in b)
        block = block.replace('{{AIDP_HOME}}', str(SCRIPTS.parent))
        checked = guard.evaluate(block, fixture.root, execution_context=ctx)
        self.assertTrue(checked['allowed'], checked)
        payload = {'tool_name': 'Bash', 'cwd': str(fixture.root), 'tool_input': {'command': block}}
        hooked = run_hook(fixture.root, payload, env_extra={'AIDP_EXECUTION_CONTEXT': ctx})
        self.assertEqual(0, hooked.returncode, hooked.stderr)
        ordinary = entry.resolve_context(fixture.root, 'sprint-dev', version=fixture.version)['execution_context']
        env = dict(os.environ, AIAUTO_UNIT_TIMEOUT_SECONDS='10')
        env.pop('AIDP_EXECUTION_CONTEXT', None)
        missing = subprocess.run([sys.executable, str(SCRIPT), 'wrap', '--allow-full',
                                  '--root', str(fixture.root), '--', *fixture.cli(plan)],
                                 cwd=fixture.root, env=env, capture_output=True, text=True)
        self.assertEqual(2, missing.returncode, missing.stdout + missing.stderr)
        self.assertIn('allow-full', missing.stderr)
        self.assertFalse(build_unit.build_dir(fixture.root, fixture.version, fixture.build).exists())
        # 同一真实围栏先走普通任务/未委派父任务，必须在执行 build 前拒绝。
        for denied_ctx in (ordinary, fixture.parent):
            rejected = subprocess.run(['bash', '-e', '-c', block, '--', str(manifest), denied_ctx],
                                      cwd=fixture.root, env=env, capture_output=True, text=True)
            self.assertEqual(2, rejected.returncode, rejected.stdout + rejected.stderr)
            self.assertIn('allow-full', rejected.stderr)
            self.assertFalse(build_unit.build_dir(fixture.root, fixture.version, fixture.build).exists())
        passed = subprocess.run(['bash', '-e', '-c', block, '--', str(manifest), ctx],
                                cwd=fixture.root, env=env, capture_output=True, text=True)
        self.assertEqual(0, passed.returncode, passed.stdout + passed.stderr)
        result = json.loads(passed.stdout)
        self.assertEqual('PASS', result['status'], result)
        self.assertTrue(result['runs'])
        self.assertEqual(plan['commit'], result['commit'])
        self.assertFalse((fixture.root / guard.ALLOWLIST_DIR).exists())
        fixture.assert_cleaned()


if __name__ == "__main__":
    unittest.main()
