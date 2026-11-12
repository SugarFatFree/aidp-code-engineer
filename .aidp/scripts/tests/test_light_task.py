#!/usr/bin/env python3
"""light_task.py：resolve → 选测 → 执行 → 汇总 单一入口的回归测试（临时 git 仓库夹具）。"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import light_task  # noqa: E402

TEST_SRC = ('import sys, unittest\nsys.path.insert(0, ".")\nimport app\n'
            'class T(unittest.TestCase):\n def test_x(self): self.assertEqual(app.x, 2)\n'
            'if __name__ == "__main__": unittest.main()\n')
RUNNERS = json.dumps([{"cwd": ".", "suffixes": [".py"], "argv": [sys.executable, "-B", "{tests}"]}])


class LightTaskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-q")
        self.git("config", "user.name", "fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        (self.root / ".gitignore").write_text("__pycache__/\nmemory/.aidp/\n")
        (self.root / "memory").mkdir()
        (self.root / "memory/aidp-config.yaml").write_text("development:\n  branch_policy: current\n")
        (self.root / "app.py").write_text("x = 1\n")
        (self.root / "tests").mkdir()
        (self.root / "tests/test_app.py").write_text(TEST_SRC)
        self.git("add", "-A")
        self.git("commit", "-qm", "base")

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], text=True,
                              capture_output=True, check=True).stdout.strip()

    def cli(self, step, *args, expected=0, runners=True):
        cmd = [sys.executable, "-B", str(SCRIPTS / "light_task.py"), step, "--root", str(self.root), *args]
        if runners:
            cmd += ["--runners-json", RUNNERS]
        proc = subprocess.run(cmd, text=True, capture_output=True)
        self.assertEqual(proc.returncode, expected, proc.stdout + proc.stderr)
        return json.loads(proc.stdout.strip().splitlines()[-1])

    def start(self, *extra):
        return self.cli("start", "--version", "V1", "--write-set", "app.py",
                        "--acceptance", "x 为 2", *extra, runners=False)

    def test_start_resolves_light_and_reads_branch_policy(self):
        out = self.start()
        self.assertEqual(out["mode"], "light")
        self.assertEqual(out["route"], "light")
        self.assertIn("related-test", out["allowed_actions"])
        self.assertTrue(Path(out["execution_context"]).is_file())
        self.assertIn("branch_policy", out)
        # 嵌套继承：同一路径再 start 得到同一任务
        again = self.cli("start", "--execution-context", out["execution_context"], runners=False)
        self.assertEqual(again["task_id"], out["task_id"])

    def test_repeated_write_set_and_acceptance_keep_all_values(self):
        out = self.cli("start", "--version", "V1", "--write-set", "app.py", "--write-set", "code/b.py",
                       "--acceptance", "first", "--acceptance", "second", runners=False)
        context = json.loads(Path(out["execution_context"]).read_text())
        self.assertEqual(context["write_set"], ["app.py", "code/b.py"])
        self.assertEqual(context["acceptance"], ["first", "second"])

    def test_start_binds_current_task(self):
        out = self.start()
        marker = json.loads((self.root / "memory/.aidp/entry-task.json").read_text())
        self.assertIn(out["execution_context"], json.dumps(marker))
        self.assertTrue(out["entry_bound"])

    def test_analysis_only_start_does_not_require_edit_binding(self):
        source = json.dumps({"kind": "user-text", "request_id": "read-only-task", "text": "只分析，不改代码",
                             "restriction": "analysis-only"}, ensure_ascii=False)
        result = self.start("--authorization-source", source)
        self.assertNotIn("implement", result["allowed_actions"])
        self.assertFalse(result["entry_bound"])
        marker = json.loads((self.root / "memory/.aidp/entry-task.json").read_text())
        self.assertEqual(marker["execution_context"], result["execution_context"])

    def test_readonly_task_replaces_previous_writable_session_identity(self):
        source = json.dumps({"kind": "user-text", "request_id": "readonly-next", "text": "只分析",
                             "restriction": "analysis-only"}, ensure_ascii=False)
        first = self.cli("start", "--version", "V1", "--write-set", "code/a.py", "--acceptance", "code change",
                         "--session-id", "same-session", runners=False)
        second = self.cli("start", "--version", "V1", "--write-set", "code/a.py", "--acceptance", "analysis",
                          "--session-id", "same-session", "--authorization-source", source, runners=False)
        self.assertNotEqual(first["execution_context"], second["execution_context"])
        payload = {"tool_name": "Write", "session_id": "same-session", "cwd": str(self.root),
                   "tool_input": {"file_path": str(self.root / "code/a.py"), "content": "x=1"}}
        result = subprocess.run([sys.executable, "-B", str(SCRIPTS.parent / "hooks/pretool-guard.py")],
                                input=json.dumps(payload), text=True, capture_output=True,
                                env={"PATH": "/usr/bin:/bin"})
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("implement", result.stderr)

    def test_start_needs_choice_does_not_bind(self):
        (self.root / "memory/aidp-config.yaml").write_text("development:\n  branch_policy: null\n")
        out = self.start()
        self.assertTrue(out["branch_needs_choice"])
        self.assertFalse(out["entry_bound"])
        self.assertFalse((self.root / "memory/.aidp/entry-task.json").exists())

    def test_start_rejects_invalid_branch_policy(self):
        (self.root / "memory/aidp-config.yaml").write_text("development:\n  branch_policy: invalid\n")
        out = self.cli("start", "--version", "V1", "--write-set", "app.py", "--acceptance", "x",
                       runners=False, expected=2)
        self.assertIn("branch-policy", out["error"])
        self.assertFalse((self.root / "memory/.aidp/entry-task.json").exists())

    def test_session_binding_is_required_by_edit_hook(self):
        hook = SCRIPTS.parent / "hooks/pretool-guard.py"
        payload = {"tool_name": "Write", "session_id": "light-session", "cwd": str(self.root),
                   "tool_input": {"file_path": str(self.root / "code/a.py"), "content": "x=1"}}
        def run_hook():
            return subprocess.run([sys.executable, "-B", str(hook)], input=json.dumps(payload),
                                  text=True, capture_output=True, env={"PATH": "/usr/bin:/bin"})
        self.assertEqual(run_hook().returncode, 2)
        self.cli("start", "--version", "V1", "--write-set", "code/a.py", "--acceptance", "x",
                 "--session-id", "light-session", runners=False)
        self.assertEqual(run_hook().returncode, 0)
        payload["session_id"] = "different-session"
        self.assertEqual(run_hook().returncode, 2)

    def test_start_requires_inputs_for_new_task(self):
        out = self.cli("start", expected=2, runners=False)
        self.assertIn("--version", out["error"])

    def test_select_and_run_pass_then_report(self):
        ctx = self.start()["execution_context"]
        (self.root / "app.py").write_text("x = 2\n")
        sel = self.cli("select", "--execution-context", ctx)
        self.assertEqual(sel["tests"], ["tests/test_app.py"])
        self.assertEqual(sel["unmapped"], [])
        run = self.cli("run", "--execution-context", ctx)
        self.assertEqual(run["status"], "PASS")
        self.assertTrue(run["run_ids"])
        rep = self.cli("report", "--execution-context", ctx)
        self.assertEqual(rep["verdict"], "PASS")
        self.assertEqual(rep["passed"], ["tests/test_app.py"])
        self.assertEqual(rep["failed"], [])
        self.assertEqual(rep["changed"], ["app.py"])

    def test_input_change_between_execution_and_verify_cannot_report_pass(self):
        ctx = self.start()["execution_context"]
        (self.root / "app.py").write_text("x = 2\n")
        args = light_task.build_parser().parse_args([
            "all", "--root", str(self.root), "--execution-context", ctx,
            "--runners-json", RUNNERS])
        original = light_task._call
        def call_with_edit(name, *values, **kwargs):
            result = original(name, *values, **kwargs)
            if name == "test_ledger.py" and values[0] == "run-scope":
                (self.root / "app.py").write_text("x = 3\n")
            return result
        with mock.patch.object(light_task, "_call", side_effect=call_with_edit):
            result = light_task.step_all(args)
        self.assertEqual(result["steps"]["run"]["status"], "UNVERIFIED")
        self.assertEqual(result["steps"]["report"]["verdict"], "UNVERIFIED")
        self.assertEqual(result["exit_code"], 2)
        self.assertEqual(light_task.step_report(args)["exit_code"], 2)
        self.assertTrue(any("范围" in text for text in result["steps"]["run"]["warnings"]))

    def test_rejected_rerun_cannot_reuse_previous_pass_summary(self):
        ctx = self.start()["execution_context"]
        (self.root / "app.py").write_text("x = 2\n")
        self.cli("run", "--execution-context", ctx)
        args = light_task.build_parser().parse_args([
            "all", "--root", str(self.root), "--execution-context", ctx,
            "--runners-json", RUNNERS])
        with mock.patch.object(light_task, "_guard_check", return_value=([{"reason": "scope-invalid"}], [])):
            result = light_task.step_all(args)
        self.assertEqual(result["exit_code"], 2)
        self.assertEqual(result["verdict"], "UNVERIFIED")
        self.assertEqual(light_task.step_report(args)["exit_code"], 2)

    def test_scope_and_allowlist_keep_all_proven_related_files(self):
        for count in (4, 31):
            with self.subTest(count=count):
                for file in (self.root / "tests").glob("test_*.py"):
                    file.unlink()
                for index in range(count):
                    (self.root / "tests" / f"test_{index}.py").write_text(TEST_SRC)
                (self.root / "app.py").write_text("x = 1\n")
                self.git("add", "-A")
                self.git("commit", "-qm", f"related fixture {count}")
                ctx = self.start()["execution_context"]
                (self.root / "app.py").write_text("x = 2\n")
                selected = self.cli("select", "--execution-context", ctx)
                self.assertEqual(len(selected["tests"]), count)
                allowlist_path = Path(selected["allowlist_file"])
                if not allowlist_path.is_absolute():
                    allowlist_path = self.root / allowlist_path
                allowlist = json.loads(allowlist_path.read_text())
                self.assertEqual(set(selected["tests"]), set(allowlist["tests"]))
                scope = json.loads(Path(selected["scope_file"]).read_text())
                args = light_task.build_parser().parse_args(["run", "--root", str(self.root)])
                blocked, _ = light_task._guard_check(args, ctx, scope)
                self.assertEqual(blocked, [])

    def test_failure_exit_1_and_new_failure_diff(self):
        ctx = self.start()["execution_context"]
        (self.root / "app.py").write_text("x = 3\n")
        self.cli("select", "--execution-context", ctx)
        run = self.cli("run", "--execution-context", ctx, expected=1)
        self.assertEqual(run["status"], "FAIL")
        rep = self.cli("report", "--execution-context", ctx, expected=1)
        self.assertEqual(rep["verdict"], "FAIL")
        self.assertEqual(rep["known_failure_diff"]["new_failures"], ["tests/test_app.py"])

    def test_document_only_change_preserves_verified_not_applicable(self):
        ctx = self.cli("start", "--version", "V1", "--write-set", "docs/guide.md",
                       "--acceptance", "文档更新", runners=False)["execution_context"]
        (self.root / "docs").mkdir()
        (self.root / "docs/guide.md").write_text("# Guide\n")
        result = self.cli("all", "--execution-context", ctx)
        self.assertEqual(result["verdict"], "NOT_APPLICABLE")
        self.assertEqual(result["steps"]["run"]["status"], "NOT_APPLICABLE")
        self.assertEqual(result["steps"]["run"]["verify"]["exit"], 0)
        self.assertEqual(result["steps"]["run"]["run_ids"], [])
        self.assertEqual(result["steps"]["report"]["selected_tests"], [])

    def test_unmapped_change_is_reported_with_disposition(self):
        out = self.cli("start", "--version", "V1", "--write-set", "schema.sql",
                       "--acceptance", "DDL", runners=False)
        (self.root / "schema.sql").write_text("select 1;\n")
        sel = self.cli("select", "--execution-context", out["execution_context"])
        self.assertIn("schema.sql", sel["unmapped"])
        self.assertIn("UNVERIFIED", sel["unmapped_disposition"])
        run = self.cli("run", "--execution-context", out["execution_context"], expected=2)
        self.assertEqual(run["status"], "UNVERIFIED")
        rep = self.cli("report", "--execution-context", out["execution_context"], expected=2)
        self.assertEqual(rep["verdict"], "UNVERIFIED")

    def test_all_runs_whole_flow_and_never_uses_full_command(self):
        (self.root / "app.py").write_text("x = 2\n")
        out = self.cli("all", "--version", "V1", "--write-set", "app.py", "--acceptance", "x")
        self.assertEqual(out["verdict"], "PASS")
        self.assertEqual(list(out["steps"]), ["start", "select", "run", "report"])
        ctx = Path(out["execution_context"])
        run_set = json.loads((ctx.parent / "run-set.json").read_text().splitlines()[-1])
        for item in run_set["runs"]:
            self.assertTrue(item["command"][-1].endswith(".py"), item["command"])

    def test_select_denied_without_related_test_grant(self):
        source = json.dumps({"kind": "user-text", "request_id": "r1", "text": "只改不测",
                             "restriction": "modify-only"}, ensure_ascii=False)
        ctx = self.start("--authorization-source", source)["execution_context"]
        out = self.cli("select", "--execution-context", ctx, expected=2)
        self.assertIn("error", out)

    def test_missing_runners_and_context_are_input_errors(self):
        ctx = self.start()["execution_context"]
        env = {"PATH": "/usr/bin:/bin"}
        proc = subprocess.run([sys.executable, "-B", str(SCRIPTS / "light_task.py"), "select", "--root",
                               str(self.root), "--execution-context", ctx],
                              text=True, capture_output=True, env=env)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("运行器", json.loads(proc.stdout)["error"])
        out = self.cli("report", expected=2, runners=False)
        self.assertIn("execution-context", out["error"])


class GuardWiringTests(unittest.TestCase):
    """守卫拒绝即终止：不依赖真实 guard 的行为，只验证 light_task 的接线。"""

    def args(self, root):
        return mock.Mock(root=str(root))

    def test_guard_rejection_blocks_run(self):
        scope = {"runs": [{"argv": ["pytest", "tests"], "cwd": "."}]}
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(light_task, "_call", return_value=(2, "", "", {"allowed": False, "reason": "目录参数"})):
            blocked, warns = light_task._guard_check(self.args(tmp), "ctx.json", scope)
        if (SCRIPTS / "test_command_guard.py").is_file():
            self.assertEqual(blocked[0]["reason"], "目录参数")
        else:
            self.assertTrue(warns)

    def test_guard_allows(self):
        scope = {"runs": [{"argv": ["pytest", "tests/test_a.py"], "cwd": "."}]}
        with mock.patch.object(light_task, "_call", return_value=(0, "", "", {"allowed": True})):
            blocked, _ = light_task._guard_check(mock.Mock(root="."), "ctx.json", scope)
        self.assertEqual(blocked, [])

    def test_missing_guard_fails_closed(self):
        with mock.patch.object(light_task, "_script", return_value=Path("/missing/guard.py")):
            with self.assertRaises(light_task.StepError):
                light_task._guard_check(mock.Mock(root="."), "ctx.json", {"runs": []})

    def test_guard_uses_runner_working_directory(self):
        scope = {"runs": [{"argv": ["pytest", "tests/test_a.py"], "cwd": "code/backend"}]}
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(light_task, "_call", return_value=(0, "", "", {"allowed": True})) as call:
            light_task._guard_check(self.args(tmp), "ctx.json", scope)
        command = call.call_args.args[call.call_args.args.index("--command") + 1]
        self.assertIn("cd code/backend", command)
        self.assertIn("pytest tests/test_a.py", command)

    def test_guard_rejects_invalid_success_payload(self):
        scope = {"runs": [{"argv": ["pytest", "tests/test_a.py"], "cwd": "."}]}
        with mock.patch.object(light_task, "_call", return_value=(0, "", "", None)):
            blocked, _ = light_task._guard_check(mock.Mock(root="."), "ctx.json", scope)
        self.assertEqual(len(blocked), 1)

    def test_failed_tests_extraction(self):
        run = {"runs": [{"status": "FAIL", "selection": {"tests": ["t/a.py"]}},
                        {"status": "PASS", "selection": {"tests": ["t/b.py"]}}]}
        self.assertEqual(light_task._failed_tests(run), ["t/a.py"])


class BaselineTrackingTests(unittest.TestCase):
    def test_repository_and_scaffold_ignore_rules_keep_shared_baseline(self):
        repo = SCRIPTS.parents[1]
        for source in (repo / ".gitignore", repo / "skills/aidp-code-engineer/sources/root/gitignore.tpl"):
            with self.subTest(source=source), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                subprocess.run(["git", "init", "-q", str(root)], check=True)
                (root / ".gitignore").write_text(source.read_text())
                (root / "memory").mkdir()
                (root / "memory/.sprint-autopilot-baseline.json").write_text("{}\n")
                result = subprocess.run(["git", "-C", str(root), "check-ignore", "memory/.sprint-autopilot-baseline.json"],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                subprocess.run(["git", "-C", str(root), "add", "memory/.sprint-autopilot-baseline.json"], check=True)
                tracked = subprocess.check_output(["git", "-C", str(root), "ls-files"], text=True)
                self.assertIn("memory/.sprint-autopilot-baseline.json", tracked)


if __name__ == "__main__":
    unittest.main()
