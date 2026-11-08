#!/usr/bin/env python3
"""真实进程验证测试账本：内容指纹、稳定 PASS 复用、失败关闭及并发。"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "test_ledger.py"


class TestLedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="aidp-test-ledger-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "src").mkdir()
        (self.root / "src/app.py").write_text("answer = 1\n")
        (self.root / "memory").mkdir()
        self.count = self.root / "memory/count"
        self.scoped = False
        self.scope_multi = False
        self.last_scope = None
        self.command = [sys.executable, "-c", (
            "from pathlib import Path; "
            f"p=Path({str(self.count)!r}); "
            "p.write_text(str(int(p.read_text())+1) if p.exists() else '1')"
        )]

    def enable_scopes(self):
        if self.scoped:
            return
        self.scoped = True
        self.git("init", "-q")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "test")
        (self.root / ".gitignore").write_text("memory/\ndocs/\n__pycache__/\n")
        (self.root / "tests").mkdir(exist_ok=True)
        (self.root / "tests/test_app.py").write_text("import unittest\nfrom pathlib import Path\nclass AppTest(unittest.TestCase):\n def test_app(self): self.assertIn('answer', Path('src/app.py').read_text())\n")
        self.git("add", "src", "tests", ".gitignore")
        self.git("commit", "-qm", "scope baseline")
        self.scope_base = subprocess.run(["git", "-C", str(self.root), "rev-parse", "HEAD"],
                                         check=True, text=True, capture_output=True).stdout.strip()

    def scope_path(self, plan):
        rel = "memory/scopes/" + plan["scope_hash"] + ".json"
        target = self.root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(plan))
        self.last_scope = (rel, plan["scope_hash"])
        return rel, plan["scope_hash"]

    def scope_for_run(self, command, options):
        if str(SCRIPT.parent) not in sys.path:
            sys.path.insert(0, str(SCRIPT.parent))
        import test_scope
        inputs = [options[i + 1] for i, value in enumerate(options) if value == "--input"]
        cwd = next((options[i + 1] for i, value in enumerate(options) if value == "--cwd"), ".")
        if self.scope_multi:
            runners = [{"cwd": "suite-" + name, "suffixes": [".py"], "inputs": [f"docs/{name}.json"],
                        "argv": [*command, "{tests}"]} for name in ("a", "b")]
            selected = "a" if "docs/a.json" in inputs else "b"
            cwd = "suite-" + selected
            write_set = [f"suite-{name}/src/app.py" for name in ("a", "b")]
        else:
            runners = [{"cwd": cwd, "suffixes": [".py"], "inputs": inputs, "argv": [*command, "{tests}"]}]
            write_set = ["src/app.py"]
        plan = test_scope.derive(self.root, self.scope_base, runners, write_set)
        rel, hash_value = self.scope_path(plan)
        item = next(item for item in plan["runs"] if item["cwd"] == cwd)
        return ["--cwd", cwd, "--scope-file", rel, "--scope-hash", hash_value], item["argv"]

    def scope_for_ids(self, ids):
        rows = [json.loads(line) for line in self.ledger().read_text().splitlines()] if self.ledger().exists() else []
        for run_id in ids:
            row = next((r for r in rows if r.get("run_id") == run_id and r["kind"] == "run"), None)
            if row and row.get("scope_binding"):
                return self.scope_path(row["scope_binding"]["plan"])
        return self.last_scope or ("memory/no-scope.json", "missing")

    def argv(self, action="run", options=(), command=None):
        argv = [sys.executable, str(SCRIPT), action, "--root", str(self.root),
                "--env-id", "local-test"]
        if action == "run":
            command = command or self.command
            scope = next((options[i + 1] for i, value in enumerate(options) if value == "--scope"), "sprint")
            binding = []
            if self.scoped and scope == "sprint":
                binding, command = self.scope_for_run(command, options)
            argv += ["--scope", "sprint", *options, *binding, "--", *command]
        else:
            argv += list(options)
            if action == "record-review" and "--scope-file" not in options:
                ids = [options[i + 1] for i, value in enumerate(options) if value == "--run-id"]
                rel, hash_value = self.scope_for_ids(ids)
                argv += ["--scope-file", rel, "--scope-hash", hash_value]
        return argv

    def invoke(self, options=(), command=None, action="run", expected=0, env=None):
        p = subprocess.run(self.argv(action, options, command), text=True,
                           capture_output=True, timeout=15, env=env)
        self.assertEqual(p.returncode, expected, p.stdout + p.stderr)
        lines = p.stdout.splitlines()
        self.assertTrue(lines, p.stderr)
        return json.loads(lines[-1])

    def count_value(self):
        return int(self.count.read_text()) if self.count.exists() else 0

    def ledger(self):
        return self.root / "memory/.aidp/test-ledger.jsonl"

    def git(self, *args):
        p = subprocess.run(["git", "-C", str(self.root), *args],
                           capture_output=True, text=True, timeout=10)
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_unchanged_pass_reused_without_forcing_a_third_execution(self):
        results = [self.invoke() for _ in range(5)]
        self.assertEqual([r["reused"] for r in results], [False, True, True, True, True])
        self.assertEqual([r["reuse_count"] for r in results], [0, 1, 2, 3, 4])
        self.assertEqual(self.count_value(), 1)
        first = results[0]
        self.assertEqual(first["status"], "PASS")
        self.assertEqual(first["exit_code"], 0)
        self.assertEqual(first["before_hash"], first["after_hash"])
        self.assertGreaterEqual(first["duration_seconds"], 0)
        self.assertEqual(results[1]["run_id"], first["run_id"])
        rows = [json.loads(line) for line in self.ledger().read_text().splitlines()]
        self.assertEqual(len([r for r in rows if r["kind"] == "run"]), 1)

    def test_acceptance_close_fix_deploy_replay_executes_two_full_runs(self):
        # 回放执行次数，不用合成脚本耗时冒充真实业务开发时效。
        first = self.invoke()
        (self.root / "docs").mkdir()
        (self.root / "docs/report.md").write_text("验收与归档记录")
        (self.root / "AGENTS.md").write_text("整体进度：最近两轮")
        self.assertTrue(self.invoke()["reused"])
        (self.root / "src/app.py").write_text("answer = 2\n")
        targeted = [sys.executable, "-c", "from pathlib import Path; assert '2' in Path('src/app.py').read_text()"]
        self.assertFalse(self.invoke(options=("--scope", "targeted"), command=targeted)["reused"])
        self.assertTrue(self.invoke(options=("--scope", "targeted"), command=targeted)["reused"])
        final = self.invoke()
        self.assertFalse(final["reused"])
        self.assertNotEqual(first["run_id"], final["run_id"])
        self.assertTrue(self.invoke()["reused"])
        self.assertEqual(self.count_value(), 2)

    def test_content_change_with_same_mtime_and_size_invalidates(self):
        first = self.invoke()
        src = self.root / "src/app.py"
        original = src.stat()
        src.write_text("answer = 2\n")
        os.utime(src, ns=(original.st_atime_ns, original.st_mtime_ns))
        after = self.invoke()
        self.assertFalse(after["reused"])
        self.assertNotEqual(first["after_hash"], after["before_hash"])

    def test_added_deleted_tests_lockfiles_and_config_invalidate(self):
        self.invoke()
        for name in ("tests/test_app.py", "package-lock.json", ".env", "config.yaml"):
            with self.subTest(name=name):
                p = self.root / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("new input\n")
                self.assertFalse(self.invoke()["reused"])
                p.unlink()
                self.assertFalse(self.invoke()["reused"])

    def test_git_tracked_untracked_and_ignored_files(self):
        self.git("init", "-q")
        (self.root / ".gitignore").write_text("ignored/\nmemory/\n")
        self.git("add", "src/app.py", ".gitignore")
        first = self.invoke()
        (self.root / "ignored").mkdir()
        (self.root / "ignored/cache.py").write_text("not input")
        self.assertTrue(self.invoke()["reused"])
        (self.root / "src/new.py").write_text("untracked")
        self.assertFalse(self.invoke()["reused"])
        self.assertEqual(first["vcs_mode"], "git")
        (self.root / "src/app.py").unlink()
        self.assertFalse(self.invoke()["reused"])

    def test_docs_memory_excluded_but_explicit_test_inputs_included(self):
        (self.root / "docs").mkdir()
        fixture = self.root / "docs/config.json"
        fixture.write_text('{"value":1}')
        self.invoke()
        fixture.write_text('{"value":2}')
        (self.root / "memory/notes.md").write_text("documentation")
        self.assertTrue(self.invoke()["reused"])
        args = ("--input", "docs/config.json")
        self.assertFalse(self.invoke(options=args)["reused"])
        fixture.write_text('{"value":3}')
        self.assertFalse(self.invoke(options=args)["reused"])
        self.assertTrue(self.invoke(options=args)["reused"])

    def test_explicit_directory_detects_new_files_and_runtime_is_excluded(self):
        (self.root / "docs").mkdir()
        args = ("--input", "docs", "--input", "memory")
        self.invoke(options=args, command=[sys.executable, "-c", "pass"])
        (self.root / "docs/new.sql").write_text("SELECT 1;")
        self.assertFalse(self.invoke(options=args, command=[sys.executable, "-c", "pass"])["reused"])
        self.assertTrue(self.invoke(options=args, command=[sys.executable, "-c", "pass"])["reused"])

    def test_scope_cwd_command_environment_are_separate_keys(self):
        self.invoke()
        variants = [("--scope", "targeted"), ("--cwd", "src"), ("--env-id", "uat")]
        for options in variants:
            self.assertFalse(self.invoke(options=options)["reused"])
        self.assertFalse(self.invoke(command=self.command + ["literal"])["reused"])
        env = dict(os.environ, LEDGER_TEST_ENV="changed")
        self.assertFalse(self.invoke(env=env)["reused"])

    def test_failed_run_invalidates_earlier_pass(self):
        flag = self.root / "memory/exit"
        flag.write_text("0")
        cmd = self.command.copy()
        cmd[2] += f"; raise SystemExit(int(Path({str(flag)!r}).read_text()))"
        self.invoke(command=cmd)
        flag.write_text("7")
        result = self.invoke(options=("--force",), command=cmd, expected=7)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["exit_code"], 7)
        self.assertFalse(self.invoke(command=cmd, expected=7)["reused"])
        flag.write_text("0")
        self.assertFalse(self.invoke(command=cmd)["reused"])
        self.assertEqual(self.count_value(), 4)

    def test_success_with_changed_tree_is_not_pass_or_reusable(self):
        cmd = [sys.executable, "-c", "from pathlib import Path; p=Path('src/app.py'); p.write_text(p.read_text()+'# changed\\n')"]
        for _ in range(2):
            result = self.invoke(command=cmd, expected=1)
            self.assertFalse(result["reused"])
            self.assertEqual(result["status"], "TREE_CHANGED")
            self.assertEqual(result["exit_code"], 0)
            self.assertNotEqual(result["before_hash"], result["after_hash"])

    def test_spawn_error_and_timeout_never_reused(self):
        for _ in range(2):
            result = self.invoke(command=["/aidp-does-not-exist"], expected=127)
            self.assertEqual(result["status"], "ERROR")
            self.assertFalse(result["reused"])
        for _ in range(2):
            result = self.invoke(options=("--timeout", "0.1"),
                                 command=[sys.executable, "-c", "import time; time.sleep(3)"], expected=124)
            self.assertEqual(result["status"], "ERROR")
            self.assertEqual(result["exit_code"], 124)

    def test_argv_is_literal_not_shell(self):
        payload = "$(touch INJECTED); `touch INJECTED` & 'quoted argument'"
        cmd = [sys.executable, "-c", "import sys; from pathlib import Path; Path('memory/argv').write_text(sys.argv[1])", payload]
        self.invoke(command=cmd)
        self.assertEqual((self.root / "memory/argv").read_text(), payload)
        self.assertFalse((self.root / "INJECTED").exists())

    def test_corrupt_ledger_fails_closed_without_running_command(self):
        self.invoke()
        for content in ("{truncated\n", "[]\n", '{"kind":"run","status":"PASS"}\n'):
            self.ledger().write_text(content)
            self.invoke(expected=2)
            self.assertEqual(self.count_value(), 1)
            self.assertEqual(self.ledger().read_text(), content)

    def test_pending_run_does_not_reuse_old_pass(self):
        self.invoke()
        rows = [json.loads(line) for line in self.ledger().read_text().splitlines()]
        pending = dict(rows[-1], run_id="interrupted-run", status="RUNNING", exit_code=None,
                       after_hash=None, duration_seconds=0, reuse_count=0)
        unsigned = {key: value for key, value in pending.items() if key != "checksum"}
        pending["checksum"] = hashlib.sha256(json.dumps(unsigned, sort_keys=True, separators=(",", ":"),
                                                       ensure_ascii=True).encode()).hexdigest()
        rows.append(pending)
        self.ledger().write_text("".join(json.dumps(row) + "\n" for row in rows))
        self.assertFalse(self.invoke()["reused"])

    def test_two_simultaneous_same_commands_execute_once(self):
        command = self.command.copy()
        command[2] += "; import time; time.sleep(0.3)"
        ps = [subprocess.Popen(self.argv(command=command), text=True, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE) for _ in range(2)]
        results = []
        for p in ps:
            stdout, stderr = p.communicate(timeout=15)
            self.assertEqual(p.returncode, 0, stdout + stderr)
            results.append(json.loads(stdout.splitlines()[-1]))
        self.assertEqual(self.count_value(), 1)
        self.assertEqual(sorted(r["reused"] for r in results), [False, True])

    def test_killed_wrapper_keeps_command_locked_until_child_exits(self):
        import signal
        command = self.command.copy()
        command[2] += ("\nimport os, time\n"
                       "Path('memory/child-pid').write_text(str(os.getpid()))\n"
                       "deadline=time.monotonic()+5\n"
                       "while not Path('memory/release').exists():\n"
                       " if time.monotonic()>deadline: raise SystemExit(8)\n"
                       " time.sleep(0.02)\n")
        first = subprocess.Popen(self.argv(command=command), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        second = None
        child_pid = None
        try:
            deadline = time.monotonic() + 5
            while not (self.root / "memory/child-pid").exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue((self.root / "memory/child-pid").exists())
            child_pid = int((self.root / "memory/child-pid").read_text())
            first.kill()
            first.wait(timeout=5)
            second = subprocess.Popen(self.argv(command=command), text=True, stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE)
            time.sleep(0.4)
            self.assertEqual(self.count_value(), 1, "旧测试仍运行时不得再启动同键命令")
            (self.root / "memory/release").touch()
            stdout, stderr = second.communicate(timeout=10)
            self.assertEqual(second.returncode, 0, stdout + stderr)
            self.assertFalse(json.loads(stdout.splitlines()[-1])["reused"])
            self.assertEqual(self.count_value(), 2)
        finally:
            (self.root / "memory/release").touch()
            if first.poll() is None:
                first.kill()
            first.wait(timeout=5)
            if second is not None:
                if second.poll() is None:
                    second.kill()
                second.communicate(timeout=5)
            if child_pid is not None:
                try:
                    os.kill(child_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def test_different_commands_do_not_hold_global_execution_lock(self):
        ps = []
        for mine, other in (("a", "b"), ("b", "a")):
            code = ("from pathlib import Path\nimport time\n"
                    f"Path('memory/{mine}').touch()\n"
                    "deadline=time.monotonic()+3\n"
                    f"while not Path('memory/{other}').exists():\n"
                    " if time.monotonic()>deadline: raise SystemExit(9)\n"
                    " time.sleep(0.02)\n")
            ps.append(subprocess.Popen(self.argv(command=[sys.executable, "-c", code]),
                                       text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE))
        for p in ps:
            stdout, stderr = p.communicate(timeout=15)
            self.assertEqual(p.returncode, 0, stdout + stderr)
        rows = [json.loads(line) for line in self.ledger().read_text().splitlines()]
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["status"] == "PASS" for row in rows))

    def test_review_requires_scoped_sprint_evidence_and_nonempty_report(self):
        self.enable_scopes()
        run = self.invoke(options=("--scope", "targeted"))
        report = self.root / "memory/review.md"
        report.write_text("Reviewed code and tests; no blocking findings.")
        args = ("--name", "acceptance", "--run-id", run["run_id"], "--report", "memory/review.md")
        self.invoke(action="record-review", options=args, expected=2)
        full = self.invoke()
        args = ("--name", "acceptance", "--run-id", full["run_id"], "--report", "memory/review.md")
        report.write_text("")
        self.invoke(action="record-review", options=args, expected=2)
        report.write_text("Reviewed code and tests; no blocking findings.")
        self.assertEqual(self.invoke(action="record-review", options=args)["kind"], "review")

    def make_review(self, command=None, options=(), name="acceptance"):
        self.enable_scopes()
        run = self.invoke(command=command, options=options)
        (self.root / "memory/review.md").write_text("Reviewed this tree with no blocking findings.")
        self.invoke(action="record-review", options=("--name", name, "--run-id", run["run_id"],
                                                     "--report", "memory/review.md"))
        return run

    def test_review_delta_rejects_new_failed_error_or_tree_changed_run(self):
        mode = self.root / "memory/mode"
        command = [sys.executable, "-c", (
            "from pathlib import Path\nimport time\n"
            "mode = Path('memory/mode').read_text()\n"
            "if mode == 'FAIL': raise SystemExit(7)\n"
            "if mode == 'ERROR': time.sleep(10)\n"
            "if mode == 'TREE_CHANGED': Path('src/app.py').write_text('answer = 2\\n')\n"
        )]
        options = ("--timeout", "1")
        for status, exit_code in (("FAIL", 7), ("ERROR", 124), ("TREE_CHANGED", 1)):
            with self.subTest(status=status):
                mode.write_text("PASS")
                baseline = self.make_review(command=command, options=(*options, "--force"))
                mode.write_text(status)
                latest = self.invoke(command=command, options=(*options, "--force"), expected=exit_code)
                self.assertEqual(latest["key"], baseline["key"])
                self.assertEqual(latest["before_hash"], baseline["after_hash"])
                self.assertEqual(latest["status"], status)
                # 恢复原树，确保拒绝来自最新运行状态，而非内容差异。
                (self.root / "src/app.py").write_text("answer = 1\n")
                self.invoke(action="review-delta", options=("--name", "acceptance"), expected=2)

    def test_review_delta_rejects_running_and_interrupted_same_key_run(self):
        mode = self.root / "memory/mode"
        ready = self.root / "memory/child-pid"
        command = [sys.executable, "-c", (
            "from pathlib import Path\nimport os, time\n"
            "if Path('memory/mode').read_text() == 'WAIT':\n"
            " Path('memory/child-pid').write_text(str(os.getpid()))\n"
            " time.sleep(30)\n"
        )]
        for interruption in (signal.SIGINT, signal.SIGKILL):
            mode.write_text("PASS")
            ready.unlink(missing_ok=True)
            baseline = self.make_review(command=command, options=("--force",))
            mode.write_text("WAIT")
            process = subprocess.Popen(self.argv(options=("--force",), command=command),
                                       text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            child_pid = None
            try:
                deadline = time.monotonic() + 5
                while not ready.exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(ready.exists(), "测试子进程未就绪")
                child_pid = int(ready.read_text())
                rows = [json.loads(line) for line in self.ledger().read_text().splitlines()]
                latest = rows[-1]
                self.assertEqual(latest["status"], "RUNNING")
                self.assertEqual(latest["key"], baseline["key"])
                self.assertEqual(latest["before_hash"], baseline["after_hash"])
                with self.subTest(interruption=interruption, state="RUNNING"):
                    self.invoke(action="review-delta", options=("--name", "acceptance"), expected=2)
                process.send_signal(interruption)
                process.wait(timeout=5)
                if interruption == signal.SIGINT:
                    stdout, stderr = process.communicate(timeout=5)
                    self.assertEqual(process.returncode, 130, stdout + stderr)
                    self.assertEqual(json.loads(stdout.splitlines()[-1])["status"], "ERROR")
                else:
                    self.assertEqual(process.returncode, -signal.SIGKILL)
                    rows = [json.loads(line) for line in self.ledger().read_text().splitlines()]
                    self.assertEqual(rows[-1]["status"], "RUNNING")
                with self.subTest(interruption=interruption, state="interrupted"):
                    self.invoke(action="review-delta", options=("--name", "acceptance"), expected=2)
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)
                if child_pid is None and ready.exists():
                    child_pid = int(ready.read_text())
                if child_pid is not None:
                    try:
                        os.killpg(child_pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                process.communicate(timeout=5)

    def test_review_delta_new_pass_requires_explicit_reregistration(self):
        baseline = self.make_review()
        latest = self.invoke(options=("--force",))
        self.assertEqual(latest["key"], baseline["key"])
        self.assertEqual(latest["after_hash"], baseline["after_hash"])
        self.assertNotEqual(latest["run_id"], baseline["run_id"])
        error = self.invoke(action="review-delta", options=("--name", "acceptance"), expected=2)
        self.assertIn("record-review", error["error"])
        self.invoke(action="record-review", expected=2, options=("--name", "acceptance",
                    "--run-id", baseline["run_id"], "--report", "memory/review.md"))
        review = self.invoke(action="record-review", options=("--name", "acceptance",
                    "--run-id", latest["run_id"], "--report", "memory/review.md"))
        delta = self.invoke(action="review-delta", options=("--name", "acceptance"))
        self.assertEqual(delta["run_id"], latest["run_id"])
        self.assertEqual(delta["review_id"], review["review_id"])
        self.assertFalse(delta["code_changed"])
        self.assertEqual(self.count_value(), 2)

    def test_review_delta_unchanged_reused_run_preserves_baseline(self):
        baseline = self.make_review()
        before = self.invoke(action="review-delta", options=("--name", "acceptance"))
        self.assertFalse(before["code_changed"])
        for _ in range(3):
            reused = self.invoke()
            self.assertTrue(reused["reused"])
            self.assertEqual(reused["run_id"], baseline["run_id"])
            delta = self.invoke(action="review-delta", options=("--name", "acceptance"))
            self.assertEqual(delta, before)
        self.assertEqual(self.count_value(), 1)

    def test_review_delta_checks_each_full_input_key_independently(self):
        (self.root / "docs").mkdir()
        for name in ("a", "b"):
            (self.root / f"docs/{name}.json").write_text(name)
        flag = self.root / "memory/exit"
        flag.write_text("0")
        command = [sys.executable, "-c", "from pathlib import Path; raise SystemExit(int(Path('memory/exit').read_text()))"]
        baselines = {name: self.make_review(command=command, options=("--input", f"docs/{name}.json"),
                                           name=name) for name in ("a", "b")}
        self.assertNotEqual(baselines["a"]["key"], baselines["b"]["key"])
        flag.write_text("7")
        failed = self.invoke(command=command, options=("--input", "docs/a.json", "--force"), expected=7)
        self.assertEqual(failed["key"], baselines["a"]["key"])
        flag.write_text("0")
        # 后面的另一套 full PASS 不能掩盖 a 的失败，也不能取代 a 的证据。
        self.make_review(command=command, options=("--input", "docs/b.json", "--force"), name="b")
        self.assertFalse(self.invoke(action="review-delta", options=("--name", "b"))["code_changed"])
        self.invoke(action="review-delta", options=("--name", "a"), expected=2)

    def full_suites(self):
        self.enable_scopes()
        self.scope_multi = True
        (self.root / "docs").mkdir(exist_ok=True)
        (self.root / "memory/exit").write_text("0")
        (self.root / "memory/review.md").write_text("Reviewed Sprint suites A and B.")
        command = [sys.executable, "-c", f"from pathlib import Path; raise SystemExit(int(Path({str(self.root / 'memory/exit')!r}).read_text()))"]
        for name in ("a", "b"):
            (self.root / f"docs/{name}.json").write_text(name)
            module = self.root / ("suite-" + name)
            (module / "src").mkdir(parents=True, exist_ok=True)
            (module / "tests").mkdir(exist_ok=True)
            (module / "src/app.py").write_text("answer = 1\n")
            (module / "tests/test_app.py").write_text((self.root / "tests/test_app.py").read_text())
        self.git("add", "suite-a", "suite-b")
        self.git("commit", "-qm", "suite baseline")
        self.scope_base = subprocess.run(["git", "-C", str(self.root), "rev-parse", "HEAD"],
                                         check=True, text=True, capture_output=True).stdout.strip()
        runs = [self.invoke(command=command, options=("--input", f"docs/{name}.json")) for name in ("a", "b")]
        return command, runs

    def review_options(self, runs):
        return ("--name", "acceptance", "--report", "memory/review.md",
                *(arg for run in runs for arg in ("--run-id", run["run_id"])))

    def test_multi_full_review_rejects_first_suite_failure_and_requires_reregistration(self):
        command, runs = self.full_suites()
        self.invoke(action="record-review", options=self.review_options(runs))
        self.assertFalse(self.invoke(action="review-delta", options=("--name", "acceptance"))["code_changed"])
        (self.root / "memory/exit").write_text("7")
        failed = self.invoke(command=command, options=("--input", "docs/a.json", "--force"), expected=7)
        self.assertEqual(failed["key"], runs[0]["key"])
        self.assertEqual(failed["before_hash"], runs[0]["after_hash"])
        self.assertEqual(failed["status"], "FAIL")
        # B 未重跑；A 的新失败必须阻断整个审查基线。
        self.invoke(action="review-delta", options=("--name", "acceptance"), expected=2)
        self.invoke(action="record-review", options=self.review_options(runs), expected=2)
        (self.root / "memory/exit").write_text("0")
        runs[0] = self.invoke(command=command, options=("--input", "docs/a.json"))
        self.invoke(action="review-delta", options=("--name", "acceptance"), expected=2)
        review = self.invoke(action="record-review", options=self.review_options(runs))
        delta = self.invoke(action="review-delta", options=("--name", "acceptance"))
        self.assertFalse(delta["code_changed"])
        self.assertEqual(delta["run_ids"], [run["run_id"] for run in runs])
        self.assertEqual(delta["review_id"], review["review_id"])

    def test_multi_full_review_inherits_all_inputs_and_preserves_legacy_run_id(self):
        _, runs = self.full_suites()
        review = self.invoke(action="record-review", options=self.review_options(runs))
        self.assertEqual(review["run_ids"], [run["run_id"] for run in runs])
        self.assertEqual(review["run_id"], runs[-1]["run_id"])
        self.assertEqual(review["inputs"], ["docs/a.json", "docs/b.json"])
        for name in ("a", "b"):
            (self.root / f"docs/{name}.json").write_text("changed")
        delta = self.invoke(action="review-delta", options=("--name", "acceptance"))
        self.assertEqual(delta["changed"], ["docs/a.json", "docs/b.json"])
        self.assertEqual(delta["run_ids"], review["run_ids"])

    def test_multi_full_record_review_checks_each_suite_tree_scope_and_environment(self):
        command, runs = self.full_suites()
        (self.root / "docs/a.json").write_text("changed")
        with self.subTest(reason="first suite stale tree"):
            self.invoke(action="record-review", options=self.review_options(runs), expected=2)
        (self.root / "docs/a.json").write_text("a")
        for options in (("--scope", "targeted"), ("--env-id", "other")):
            with self.subTest(options=options):
                invalid = self.invoke(command=command, options=options)
                self.invoke(action="record-review", options=self.review_options([invalid, runs[1]]), expected=2)
        with self.subTest(reason="first suite different process environment"):
            invalid = self.invoke(command=command, env=dict(os.environ, LEDGER_TEST_ENV="other"))
            self.invoke(action="record-review", options=self.review_options([invalid, runs[1]]), expected=2)

    def test_multi_full_record_review_rejects_duplicate_empty_and_unknown_ids(self):
        _, runs = self.full_suites()
        for first_id in (runs[1]["run_id"], "", "missing-run"):
            with self.subTest(first_id=first_id):
                self.invoke(action="record-review", options=self.review_options([
                    {"run_id": first_id}, runs[1]]), expected=2)

    def test_record_review_api_accepts_string_or_list_and_rejects_malformed_ids(self):
        spec = importlib.util.spec_from_file_location("ledger_api_test", SCRIPT)
        ledger = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ledger)
        self.enable_scopes()
        first = self.invoke()
        (self.root / "memory/review.md").write_text("Reviewed selected Sprint test.")
        scope_file, scope_hash = self.scope_for_ids([first["run_id"]])
        single = ledger.record_review(self.root, "single", first["run_id"], "local-test", "memory/review.md",
                                      scope_file=scope_file, scope_hash=scope_hash)
        self.assertEqual(single["run_ids"], [first["run_id"]])
        _, runs = self.full_suites()
        ids = [run["run_id"] for run in runs]
        scope_file, scope_hash = self.scope_for_ids(ids)
        multi = ledger.record_review(self.root, "multi", ids, "local-test", "memory/review.md",
                                     scope_file=scope_file, scope_hash=scope_hash)
        self.assertEqual(multi["run_ids"], ids)
        for invalid in (None, [], "", [ids[0], ids[0]], ["", ids[1]], [42, ids[1]], [{}, ids[1]]):
            with self.subTest(invalid=invalid), self.assertRaises(ledger.LedgerError):
                ledger.record_review(self.root, "invalid", invalid, "local-test", "memory/review.md",
                                     scope_file=scope_file, scope_hash=scope_hash)
        with self.assertRaises(ledger.LedgerError):
            ledger.record_review(self.root, "unbound", ids, "local-test", "memory/review.md")

    def test_review_delta_rejects_corrupt_run_ids_and_reads_legacy_single_baseline(self):
        _, runs = self.full_suites()
        self.invoke(action="record-review", options=self.review_options(runs))
        original = [json.loads(line) for line in self.ledger().read_text().splitlines()]
        ids = [run["run_id"] for run in runs]

        def save_review(review):
            rows = [*original[:-1], review]
            for row in rows:
                unsigned = {key: value for key, value in row.items() if key != "checksum"}
                row["checksum"] = hashlib.sha256(json.dumps(unsigned, sort_keys=True, separators=(",", ":"),
                                                            ensure_ascii=True).encode()).hexdigest()
            self.ledger().write_text("".join(json.dumps(row) + "\n" for row in rows))

        for invalid in (None, [], ids[-1], [ids[-1], ids[-1]], ["", ids[-1]],
                        [123, ids[-1]], [{}, ids[-1]], ["missing-run", ids[-1]], ids[:1]):
            with self.subTest(invalid=invalid):
                save_review(dict(original[-1], run_ids=invalid))
                self.invoke(action="review-delta", options=("--name", "acceptance"), expected=2)
        legacy = dict(original[-1])
        legacy.pop("run_ids", None)
        legacy.pop("scope_hash", None)
        legacy.pop("scope_file", None)
        save_review(legacy)
        delta = self.invoke(action="review-delta", options=("--name", "acceptance"))
        self.assertEqual(delta["run_ids"], ids[-1:])
        self.assertEqual(delta["run_id"], ids[-1])
        self.assertFalse(delta["code_changed"])
        self.assertTrue(delta["legacy"])
        self.assertTrue(delta["requires_verification"])

    def test_review_delta_uses_accepted_snapshot_not_head(self):
        self.make_review()
        options = ("--name", "acceptance")
        self.assertFalse(self.invoke(action="review-delta", options=options)["code_changed"])
        (self.root / "src/app.py").write_text("answer = 2\n")
        (self.root / "src/new.py").write_text("new code")
        delta = self.invoke(action="review-delta", options=options)
        self.assertEqual(delta["changed"], ["src/app.py"])
        self.assertEqual(delta["added"], ["src/new.py"])
        self.assertTrue(delta["code_changed"])
        (self.root / "src/app.py").unlink()
        delta = self.invoke(action="review-delta", options=options)
        self.assertEqual(delta["removed"], ["src/app.py"])

    def test_review_fails_closed_for_missing_stale_report_or_environment(self):
        args = ("--name", "acceptance")
        self.invoke(action="review-delta", options=args, expected=2)
        self.make_review()
        self.invoke(action="review-delta", options=(*args, "--env-id", "other"), expected=2)
        (self.root / "memory/review.md").write_text("Report was replaced.")
        self.invoke(action="review-delta", options=args, expected=2)

    def test_changed_tree_cannot_be_recorded_against_old_test_pass(self):
        run = self.make_review()
        (self.root / "src/app.py").write_text("answer = 9\n")
        self.invoke(action="record-review", expected=2,
                    options=("--name", "new-review", "--run-id", run["run_id"], "--report", "memory/review.md"))

    def test_review_inherits_test_inputs_and_additional_contract_inputs(self):
        self.enable_scopes()
        (self.root / "docs").mkdir()
        (self.root / "docs/fixture.json").write_text("fixture1")
        (self.root / "docs/contract.md").write_text("contract1")
        (self.root / "memory/review.md").write_text("Reviewed both contract and code.")
        run = self.invoke(options=("--input", "docs/fixture.json"))
        self.invoke(action="record-review", options=("--name", "contracts", "--run-id", run["run_id"],
                    "--report", "memory/review.md", "--input", "docs/contract.md"))
        (self.root / "docs/contract.md").write_text("contract2")
        (self.root / "docs/fixture.json").write_text("fixture2")
        delta = self.invoke(action="review-delta", options=("--name", "contracts"))
        self.assertEqual(delta["changed"], ["docs/contract.md", "docs/fixture.json"])

    def test_review_cannot_ignore_later_failure_of_same_test_command(self):
        run = self.make_review()
        flag = self.root / "memory/exit"
        flag.write_text("0")
        cmd = [sys.executable, "-c", f"from pathlib import Path; raise SystemExit(int(Path({str(flag)!r}).read_text()))"]
        passed = self.invoke(command=cmd)
        flag.write_text("3")
        self.invoke(options=("--force",), command=cmd, expected=3)
        self.invoke(action="record-review", expected=2, options=("--name", "new", "--run-id", passed["run_id"],
                    "--report", "memory/review.md"))
        self.assertEqual(self.invoke(action="review-delta", options=("--name", "acceptance"))["run_id"], run["run_id"])

    def test_file_mode_and_symlink_target_content_affect_hash(self):
        first = self.invoke()
        source = self.root / "src/app.py"
        source.chmod(0o755)
        self.assertNotEqual(self.invoke()["after_hash"], first["after_hash"])
        target = self.root / "memory/target.py"
        target.write_text("value=1")
        (self.root / "src/link.py").symlink_to(target)
        linked = self.invoke()
        target.write_text("value=2")
        changed = self.invoke()
        self.assertFalse(changed["reused"])
        self.assertNotEqual(linked["after_hash"], changed["after_hash"])

    def test_tracked_ignored_file_still_changes_fingerprint(self):
        self.git("init", "-q")
        (self.root / ".gitignore").write_text("ignored.py\nmemory/\n")
        (self.root / "ignored.py").write_text("value=1")
        self.git("add", "-f", "ignored.py")
        self.invoke()
        (self.root / "ignored.py").write_text("value=2")
        self.assertFalse(self.invoke()["reused"])

    def test_force_runs_again_but_default_reuses(self):
        self.invoke()
        self.assertTrue(self.invoke()["reused"])
        self.assertFalse(self.invoke(options=("--force",))["reused"])
        self.assertTrue(self.invoke()["reused"])
        self.assertEqual(self.count_value(), 2)

    def test_other_project_cannot_reuse_copied_ledger(self):
        import shutil
        self.invoke()
        other = self.root / "other"
        shutil.copytree(self.root / "src", other / "src")
        (other / "memory/.aidp").mkdir(parents=True)
        shutil.copy2(self.ledger(), other / "memory/.aidp/test-ledger.jsonl")
        self.invoke(options=("--root", str(other)), expected=2)
        self.assertEqual(self.count_value(), 1)

    def test_invalid_input_cwd_directory_symlink_and_empty_environment_fail_closed(self):
        for options in (("--input", "absent"), ("--cwd", ".."), ("--env-id", " "),
                        ("--timeout", "nan")):
            self.invoke(options=options, expected=2)
        (self.root / "src/link").symlink_to(self.root / "memory", target_is_directory=True)
        self.invoke(expected=2)
        self.assertEqual(self.count_value(), 0)

    def test_broken_git_worktree_does_not_silently_fall_back_and_reuse(self):
        self.invoke()
        (self.root / ".git").write_text("gitdir: /missing-aidp-worktree-admin-dir\n")
        self.invoke(expected=2)
        self.assertEqual(self.count_value(), 1)

    def test_close_root_memory_and_navigation_changes_preserve_pass(self):
        names = ("CLAUDE.md", "AGENTS.md", "README.md")
        for git_enabled in (False, True):
            with self.subTest(git=git_enabled):
                for name in names:
                    (self.root / name).write_text("current sprint: active\n")
                if git_enabled:
                    self.git("init", "-q")
                    self.git("add", *names)
                self.invoke()
                for name in names:
                    (self.root / name).write_text("current sprint: closed\n")
                    self.assertTrue(self.invoke()["reused"], name)
                # 只排除三个根文件；其它 Markdown 和嵌套同名文件仍进入代码树。
                for name in ("contract.md", "src/README.md"):
                    path = self.root / name
                    path.write_text("new contract" + str(git_enabled))
                    self.assertFalse(self.invoke()["reused"], name)

    def test_explicit_root_memory_inputs_override_default_exclusion(self):
        for git_enabled in (False, True):
            with self.subTest(git=git_enabled):
                if git_enabled:
                    self.git("init", "-q")
                for name in ("CLAUDE.md", "AGENTS.md", "README.md"):
                    path = self.root / name
                    path.write_text("test input v1")
                    if git_enabled:
                        self.git("add", name)
                    options = ("--input", name)
                    self.invoke(options=options)
                    path.write_text("test input v2")
                    self.assertFalse(self.invoke(options=options)["reused"], name)
                    self.assertTrue(self.invoke(options=options)["reused"], name)

    def test_shell_noise_does_not_break_reuse_but_other_environment_still_does(self):
        self.invoke()
        noise = dict(os.environ, SHLVL="111", _="/other/shell", PWD="/other/pwd", OLDPWD="/other/oldpwd")
        self.assertTrue(self.invoke(env=noise)["reused"])
        changed = dict(noise, LEDGER_SESSION_TOKEN="another-session")
        self.assertFalse(self.invoke(env=changed)["reused"])

    def test_full_api_uses_dedicated_build_ledger_across_worktree_paths(self):
        spec = importlib.util.spec_from_file_location("ledger_full_api_test", SCRIPT)
        ledger = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ledger)
        self.git("init", "-q")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "test")
        self.git("add", "src/app.py")
        self.git("commit", "-qm", "build")
        main_run = self.invoke()
        with tempfile.TemporaryDirectory(prefix="aidp-build-cache-") as temp:
            cache = Path(temp) / "build-ledger"
            original = None
            for index in range(2):
                wt = Path(temp) / f"wt-{index}"
                self.git("worktree", "add", "--detach", str(wt), "HEAD")
                try:
                    output, exit_code = ledger.run(root=wt, cwd=".", scope="full", env_id="build-1",
                                                   command=[sys.executable, "-c", "pass"], ledger_root=cache)
                    self.assertEqual(exit_code, 0)
                    self.assertEqual(output["status"], "PASS")
                    self.assertEqual(output["reused"], bool(index))
                    if original is None:
                        original = output
                    else:
                        self.assertEqual(output["run_id"], original["run_id"])
                        self.assertEqual(output["root"], original["root"], "复用保留原执行 worktree 位置")
                finally:
                    self.git("worktree", "remove", "--force", str(wt))
            self.assertTrue((cache / "memory/.aidp/test-ledger.jsonl").is_file())
            main_again = self.invoke()
            self.assertTrue(main_again["reused"])
            self.assertEqual(main_again["run_id"], main_run["run_id"])
            self.assertEqual(len(ledger.load(self.root)), 1, "独立 build 账本不得混入主仓 Sprint 记录")

    def test_tool_wrapper_exit_127_is_unverified_not_code_failure(self):
        out = self.invoke(command=[sys.executable, "-c", "raise SystemExit(127)"], expected=127)
        self.assertEqual(out["status"], "ERROR")
        self.assertIn("未核验", out["error"])

    def test_run_api_validates_timeout_and_environment(self):
        spec = importlib.util.spec_from_file_location("ledger_validation_api_test", SCRIPT)
        ledger = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ledger)
        for extra in ({"timeout": float("nan")}, {"timeout": 0}, {"env_id": " "}):
            options = {"root": self.root, "cwd": ".", "scope": "full", "env_id": "build",
                       "command": [sys.executable, "-c", "pass"], **extra}
            with self.subTest(extra=extra), self.assertRaises(ledger.LedgerError):
                ledger.run(**options)
        self.assertFalse(self.ledger().exists())

    def test_loading_carried_rows_rechecks_dependencies_and_rejects_legacy_proof(self):
        self.enable_scopes()
        sys.path.insert(0, str(SCRIPT.parent))
        import test_scope
        import test_ledger
        for name, text in {
            "src/b.py": "value = 1\n",
            "src/a.py": "from src.b import value\n",
            "tests/__init__.py": "",
            "tests/test_a.py": "import unittest\nfrom src.a import value\nclass A(unittest.TestCase):\n def test_a(self): self.assertEqual(value, 1)\n",
            "tests/test_b.py": "import unittest\nfrom src.b import value\nclass B(unittest.TestCase):\n def test_b(self): self.assertGreater(value, 0)\n",
        }.items():
            (self.root / name).write_text(text)
        runners = [{"suffixes": [".py"], "argv": [sys.executable, "-B", "-m", "unittest", "{tests}"]}]
        plan = test_scope.derive(self.root, self.scope_base, runners)
        rel, _ = self.scope_path(plan)
        command = [sys.executable, str(SCRIPT), "run-scope", "--root", str(self.root),
                   "--scope-file", rel, "--env-id", "local-test"]
        first = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        original = test_ledger.load(self.root)
        source = next(r for r in original if r["command"][-1] == "tests/test_a.py")
        (self.root / "src/b.py").write_text("value = 2\n")
        plan = test_scope.derive(self.root, self.scope_base, runners)
        rel, _ = self.scope_path(plan)
        snapshot = test_ledger.tree_snapshot(self.root)
        item = next(r for r in plan["runs"] if r["tests"] == ["tests/test_a.py"])
        # 按旧实现会接受的结构保存真实来源 PASS + 错误 CARRIED；校验和全部合法。
        carried = dict(source, run_id="historical-bad-carry", status="CARRIED", exit_code=None,
                       before_hash=snapshot["hash"], after_hash=None, assessment_hash=snapshot["hash"],
                       files=snapshot["files"], source_run_id=source["run_id"], parent_run_id=source["run_id"],
                       source_tree_hash=source["after_hash"], scope_binding={"plan": plan, "item": item},
                       scope_hash=plan["scope_hash"], delta=["src/b.py"])
        for legacy in (False, True):
            with self.subTest(legacy=legacy):
                rows = json.loads(json.dumps([*original, carried]))
                if legacy:
                    for row in rows:
                        historical = row["scope_binding"]["plan"]
                        historical.pop("dependencies", None)
                        historical["scope_hash"] = test_scope.digest({k: v for k, v in historical.items() if k != "scope_hash"})
                        row["scope_hash"] = historical["scope_hash"]
                test_ledger.save(self.root, rows)
                with self.assertRaisesRegex(test_ledger.LedgerError, "carry-forward"):
                    test_ledger.load(self.root)
                for action in ("run-scope", "verify"):
                    args = [sys.executable, str(SCRIPT), action, "--root", str(self.root),
                            "--scope-file", rel, "--env-id", "local-test"]
                    if action == "verify":
                        args += ["--scope-hash", plan["scope_hash"], "--run-id", carried["run_id"]]
                    rejected = subprocess.run(args, capture_output=True, text=True)
                    self.assertEqual(rejected.returncode, 2, rejected.stdout + rejected.stderr)
                    self.assertIn("carry-forward", rejected.stdout)

    def test_self_check_has_positive_and_negative_cases(self):
        p = subprocess.run([sys.executable, str(SCRIPT), "--self-check"],
                           capture_output=True, text=True, timeout=20)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        data = json.loads(p.stdout.splitlines()[-1])
        self.assertTrue(data["ok"])
        self.assertGreaterEqual(data["checks"], 4)


if __name__ == "__main__":
    unittest.main()
