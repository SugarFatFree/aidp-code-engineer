#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Agent 原生运行根与 VCS 能力层回归（stdlib only）。"""
import getpass
import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]


def _load(name: str):
    path = SCRIPTS / f"{name}.py"
    if not path.is_file():
        raise AssertionError(f"缺少生产模块: {path}")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class RuntimeRootTest(unittest.TestCase):
    def setUp(self):
        self.runtime = _load("aidp_runtime")

    def test_parses_template_claude_and_shared_layouts_without_git(self):
        cases = (
            (Path("/p/.aidp/scripts/x.py"), Path("/p/.aidp"), Path("/p")),
            (Path("/p/.claude/aidp/scripts/x.py"), Path("/p/.claude/aidp"), Path("/p")),
            (Path("/p/.agents/aidp/scripts/x.py"), Path("/p/.agents/aidp"), Path("/p")),
        )
        with mock.patch("subprocess.run", side_effect=AssertionError("运行根解析不得调用 Git")):
            for script, runtime, project in cases:
                with self.subTest(script=script):
                    self.assertEqual(self.runtime.runtime_root(script, environ={}), runtime)
                    self.assertEqual(self.runtime.project_root(script, environ={}), project)

    def test_rejects_script_outside_runtime_scripts_directory(self):
        with self.assertRaisesRegex(RuntimeError, "解析 AIDP 运行根"):
            self.runtime.runtime_root("/p/scripts/x.py", environ={})

    def test_runtime_text_expands_only_internal_token(self):
        script = Path("/p/.claude/aidp/scripts/x.py")
        self.assertEqual(
            self.runtime.runtime_text("run __AIDP_HOME__/scripts/x.py", script),
            "run .claude/aidp/scripts/x.py",
        )
        self.assertEqual(
            self.runtime.runtime_text("memory/.aidp/alerts.jsonl", script),
            "memory/.aidp/alerts.jsonl",
        )

    def test_relative_overrides_resolve_inside_project(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "project"
            runtime = project / ".claude/aidp"
            scripts = runtime / "scripts"
            scripts.mkdir(parents=True)
            script = scripts / "x.py"
            script.write_text("# fixture\n", encoding="utf-8")
            env = {"AIDP_PROJECT_ROOT": str(project), "AIDP_HOME": ".claude/aidp"}
            self.assertEqual(self.runtime.project_root(script, environ=env), project)
            self.assertEqual(self.runtime.runtime_root(script, environ=env), runtime)

    def test_rejects_runtime_override_outside_project(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            project = base / "project"
            runtime = project / ".claude/aidp"
            runtime.mkdir(parents=True)
            script = runtime / "scripts/x.py"
            script.parent.mkdir()
            script.write_text("# fixture\n", encoding="utf-8")
            outside = base / "outside"
            outside.mkdir()
            env = {"AIDP_PROJECT_ROOT": str(project), "AIDP_HOME": str(outside)}
            with self.assertRaisesRegex(RuntimeError, "项目根之外"):
                self.runtime.runtime_root(script, environ=env)

    def test_rejects_relative_dotdot_runtime_escape(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            project = base / "project"
            project.mkdir()
            script = project / ".aidp/scripts/x.py"
            script.parent.mkdir(parents=True)
            script.write_text("# fixture\n", encoding="utf-8")
            env = {
                "AIDP_PROJECT_ROOT": str(project),
                "AIDP_HOME": "nested/../../outside",
            }
            with self.assertRaisesRegex(RuntimeError, "项目根之外"):
                self.runtime.runtime_root(script, environ=env)

    def test_rejects_absolute_dotdot_runtime_escape(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            project = base / "project"
            project.mkdir()
            script = project / ".aidp/scripts/x.py"
            script.parent.mkdir(parents=True)
            script.write_text("# fixture\n", encoding="utf-8")
            escaped = project / "nested/../../outside"
            env = {"AIDP_PROJECT_ROOT": str(project), "AIDP_HOME": str(escaped)}
            with self.assertRaisesRegex(RuntimeError, "项目根之外"):
                self.runtime.runtime_root(script, environ=env)

    def test_normalizes_dotdot_overrides_that_remain_inside_project(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            project = base / "workspace/project"
            runtime = project / ".claude/aidp"
            runtime.mkdir(parents=True)
            script = runtime / "scripts/x.py"
            script.parent.mkdir()
            script.write_text("# fixture\n", encoding="utf-8")
            env = {
                "AIDP_PROJECT_ROOT": str(base / "workspace/other/../project"),
                "AIDP_HOME": ".claude/tmp/../aidp",
            }
            self.assertEqual(self.runtime.project_root(script, environ=env), project)
            self.assertEqual(self.runtime.runtime_root(script, environ=env), runtime)

    def test_rejects_symlinked_runtime_override_ancestor(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            project = base / "project"
            project.mkdir()
            outside = base / "outside"
            (outside / "aidp/scripts").mkdir(parents=True)
            link = project / ".claude"
            link.symlink_to(outside, target_is_directory=True)
            script = outside / "aidp/scripts/x.py"
            script.write_text("# fixture\n", encoding="utf-8")
            env = {"AIDP_PROJECT_ROOT": str(project), "AIDP_HOME": ".claude/aidp"}
            with self.assertRaisesRegex(RuntimeError, "symlink"):
                self.runtime.runtime_root(script, environ=env)

    def test_rejects_non_directory_runtime_override_ancestor(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "project"
            project.mkdir()
            (project / ".claude").write_text("not a directory\n", encoding="utf-8")
            template_script = project / ".aidp/scripts/x.py"
            template_script.parent.mkdir(parents=True)
            template_script.write_text("# fixture\n", encoding="utf-8")
            env = {"AIDP_PROJECT_ROOT": str(project), "AIDP_HOME": ".claude/aidp"}
            with self.assertRaisesRegex(RuntimeError, "非目录"):
                self.runtime.runtime_root(template_script, environ=env)


class VcsCapabilityTest(unittest.TestCase):
    def setUp(self):
        self.vcs = _load("vcs")

    def test_unsupported_contract_and_exit_code(self):
        self.assertEqual(self.vcs.EXIT_UNSUPPORTED, 3)
        self.assertEqual(
            self.vcs.unsupported("push"),
            {"status": "unsupported", "reason": "vcs-disabled", "capability": "push"},
        )

    def test_detects_real_git_and_non_git_roots(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            plain = base / "plain"
            repo = base / "repo"
            plain.mkdir()
            repo.mkdir()
            init = subprocess.run(["git", "init", "-q", str(repo)], capture_output=True)
            if init.returncode != 0:
                self.skipTest("测试环境无可用 git")
            self.assertEqual(self.vcs.detect_mode(plain), "none")
            self.assertEqual(self.vcs.detect_mode(repo), "git")

    def test_git_missing_timeout_and_nonzero_are_none(self):
        root = Path("/tmp/no-git-fixture")
        cases = (
            OSError("missing"),
            subprocess.TimeoutExpired(["git"], 10),
        )
        for error in cases:
            with self.subTest(error=type(error).__name__):
                with mock.patch("subprocess.run", side_effect=error):
                    self.assertEqual(self.vcs.detect_mode(root), "none")
        completed = subprocess.CompletedProcess(["git"], 128, stdout="", stderr="bad")
        with mock.patch("subprocess.run", return_value=completed):
            self.assertEqual(self.vcs.detect_mode(root), "none")

    def test_git_probe_is_noninteractive_bounded_and_shell_free(self):
        completed = subprocess.CompletedProcess(["git"], 0, stdout="true\n", stderr="")
        with mock.patch("subprocess.run", return_value=completed) as run:
            self.assertEqual(self.vcs.detect_mode(Path("/p")), "git")
        args, kwargs = run.call_args
        self.assertEqual(args[0], ["git", "-C", "/p", "rev-parse", "--is-inside-work-tree"])
        self.assertIs(kwargs["stdin"], subprocess.DEVNULL)
        self.assertTrue(kwargs["capture_output"])
        self.assertTrue(kwargs["text"])
        self.assertEqual(kwargs["timeout"], 10)
        self.assertFalse(kwargs["check"])
        self.assertNotIn("shell", kwargs)

    def test_developer_identity_precedence_is_deterministic(self):
        root = Path("/project")
        with mock.patch.dict(os.environ, {"AIDP_USER": "env-user"}, clear=False), \
                mock.patch.object(self.vcs, "detect_mode", return_value="git"), \
                mock.patch.object(self.vcs, "_git_user_name", return_value="git-user"), \
                mock.patch.object(getpass, "getuser", return_value="os-user"):
            self.assertEqual(self.vcs.developer_identity(root, " explicit "), "explicit")
            self.assertEqual(self.vcs.developer_identity(root, None), "git-user")
        with mock.patch.dict(os.environ, {"AIDP_USER": "env-user"}, clear=False), \
                mock.patch.object(self.vcs, "detect_mode", return_value="none"), \
                mock.patch.object(self.vcs, "_git_user_name", side_effect=AssertionError("none 模式不得读 Git")), \
                mock.patch.object(getpass, "getuser", return_value="os-user"):
            self.assertEqual(self.vcs.developer_identity(root, None), "env-user")
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(self.vcs, "detect_mode", return_value="none"), \
                mock.patch.object(getpass, "getuser", return_value="os-user"):
            self.assertEqual(self.vcs.developer_identity(root, None), "os-user")

    def test_blank_and_separator_only_identity_values_fall_through(self):
        root = Path("/project")
        with mock.patch.dict(os.environ, {"AIDP_USER": " ,;/| "}, clear=False), \
                mock.patch.object(self.vcs, "detect_mode", return_value="git"), \
                mock.patch.object(self.vcs, "_git_user_name", return_value="---"), \
                mock.patch.object(getpass, "getuser", return_value="fallback-user"):
            self.assertEqual(self.vcs.developer_identity(root, "  ,  "), "fallback-user")


if __name__ == "__main__":
    unittest.main()
