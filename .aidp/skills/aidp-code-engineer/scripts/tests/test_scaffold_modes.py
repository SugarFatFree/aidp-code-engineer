#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scaffold.py 三模式端到端：init 冒烟（三种 Agent 组合）、upgrade 覆盖与用户填充型保护、migrate 保留用户内容。"""
import json
import os
import shutil
import subprocess
import sys
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

import _helpers as H
import scaffold as S
import scaffold_lib as L
import scaffold_marker
import verify as V

BUNDLE_VERSION = L.bundle_version()


def scaffold(root, *args, env=None):
    p = subprocess.run(
        [sys.executable, str(H.SCRIPTS / "scaffold.py"), str(root), "--json", *map(str, args)],
        capture_output=True, text=True, env=env or H.clean_env(), stdin=subprocess.DEVNULL)
    if p.returncode != 0:
        raise AssertionError(f"scaffold.py → exit {p.returncode}\n{p.stdout}\n{p.stderr}")
    return json.loads(p.stdout)


def fake_dsh_env(root, exit_code=0):
    """隔离 DSH 调用；PATH 只暴露假 dsh 与真实 git。"""
    bindir = root.parent / ".test-bin"
    bindir.mkdir(exist_ok=True)
    log = root.parent / ".dsh-plugin-argv"
    dsh = bindir / "dsh"
    dsh.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$@\" > \"$DSH_TEST_LOG\"\n"
        "if [ \"${DSH_TEST_EXIT:-0}\" -ne 0 ]; then "
        "printf '%s\\n' \"${DSH_TEST_MESSAGE:-plugin install failed}\" >&2; fi\n"
        "exit \"${DSH_TEST_EXIT:-0}\"\n",
        encoding="utf-8")
    dsh.chmod(0o755)
    git = shutil.which("git")
    if not git:
        raise AssertionError("测试环境缺 git")
    (bindir / "git").symlink_to(git)
    env = H.clean_env()
    env["PATH"] = str(bindir)
    env["DSH_TEST_LOG"] = str(log)
    env["DSH_TEST_EXIT"] = str(exit_code)
    return env, log


def missing_dsh_env(root):
    bindir = root.parent / ".test-bin-missing"
    bindir.mkdir(exist_ok=True)
    git = shutil.which("git")
    if not git:
        raise AssertionError("测试环境缺 git")
    (bindir / "git").symlink_to(git)
    env = H.clean_env()
    env["PATH"] = str(bindir)
    return env


def agent_sync_check(root):
    runtime = root / ".agents/aidp"
    if not runtime.is_dir():
        runtime = root / ".claude/aidp"
    p = subprocess.run([sys.executable, str(runtime / "scripts/agent_sync.py"),
                        "--root", str(root), "--check"],
                       capture_output=True, text=True, env=H.clean_env())
    return p.returncode, p.stdout


class InitSmokeTest(unittest.TestCase):
    def _init(self, agents):
        with H.TempRepo() as root:
            env = fake_dsh_env(root)[0] if "dsh" in agents.split(",") else None
            res = scaffold(root, "--version", "V0.1.0", "--agent", agents, env=env)
            self.assertEqual(res["mode"], "init")
            self.assertEqual(res["agent_source"], "argument")
            self.assertFalse(res["pending"], res["rewrite_queue"])
            self.assertEqual(scaffold_marker.read_version(root), BUNDLE_VERSION)
            for ag in agents.split(","):
                self.assertTrue((root / {"claude": ".claude", "codex": ".codex", "dsh": ".dsh"}[ag]).is_dir())
            rc, errors, out = H.verify(root)
            self.assertEqual(errors, [], out)
            self.assertEqual(rc, 0, out)
            rc, out = agent_sync_check(root)
            self.assertEqual(rc, 0, out)
            skill_root = root / (".claude/skills" if agents == "claude" else ".agents/skills")
            self.assertTrue((skill_root / "aidp-code-engineer/scripts/verify.py").is_file())
            self.assertTrue((root / ".gitignore").read_text().startswith(L.GITIGNORE_BEGIN))
            self.assertIn("name: demo", (root / "memory/aidp-config.yaml").read_text())
            # 幂等：同版本再跑不产生契约写入、不备份
            again = scaffold(root)
            self.assertEqual(again["mode"], "upgrade")
            self.assertEqual(again["contract_decision"], "fill")
            self.assertFalse([a for a in again["actions"] if a["op"] in ("create", "update", "backup", "queue")],
                             again["actions"])
            return {n: (root / n).read_text(encoding="utf-8") if (root / n).exists() else None
                    for n in ("CLAUDE.md", "AGENTS.md")}

    def test_claude_only(self):
        files = self._init("claude")
        self.assertIsNone(files["AGENTS.md"])
        self.assertIn("# demo", files["CLAUDE.md"])
        self.assertIn(L.CUSTOM_HEADING, files["CLAUDE.md"])
        self.assertNotIn("{{", files["CLAUDE.md"])

    def test_codex_only(self):
        files = self._init("codex")
        self.assertIsNone(files["CLAUDE.md"])
        self.assertIn("# demo", files["AGENTS.md"])

    def test_all_agents(self):
        files = self._init("claude,codex,dsh")
        self.assertIn("# demo", files["AGENTS.md"])
        self.assertTrue(L.is_shell(files["CLAUDE.md"]))


class NativeRuntimeLayoutContractTest(unittest.TestCase):
    RUNTIME_DIRS = (
        "agents", "commands", "flows", "hooks", "plugins", "reference", "rules",
        "scripts", "skills", "templates",
    )

    def _assert_runtime_contract(self, root, rel):
        runtime = root / rel
        for dirname in self.RUNTIME_DIRS:
            self.assertTrue((runtime / dirname).is_dir(), f"runtime 缺目录: {rel}/{dirname}")
        self.assertFalse((runtime / "skills/aidp-code-engineer").exists())
        self.assertFalse((runtime / "memory").exists())
        self.assertFalse((runtime / "scripts/tests").exists())
        self.assertFalse((runtime / "scripts/design-goals-baseline.txt").exists())

    def _assert_fully_materialized(self, root, *relative_roots):
        for relative in relative_roots:
            managed_root = root / relative
            self.assertTrue(managed_root.exists(), f"受管根必须存在: {relative}")
            self.assertFalse(managed_root.is_symlink(), f"受管根不得为 symlink: {relative}")
            for descendant in managed_root.rglob("*"):
                self.assertFalse(
                    descendant.is_symlink(),
                    f"受管树后代不得为 symlink: {descendant.relative_to(root)}",
                )

    def _assert_tree_equal(self, left, right):
        left_files = {
            path.relative_to(left).as_posix(): path.read_bytes()
            for path in left.rglob("*") if path.is_file() and path.name != ".aidp-generated"
        }
        right_files = {
            path.relative_to(right).as_posix(): path.read_bytes()
            for path in right.rglob("*") if path.is_file() and path.name != ".aidp-generated"
        }
        self.assertEqual(left_files, right_files)

    def _assert_absent(self, path):
        self.assertFalse(os.path.lexists(path), f"路径必须完全不存在（含悬空 symlink）: {path}")

    def _assert_roots_absent(self, root, *relative_roots):
        for relative in relative_roots:
            self._assert_absent(root / relative)

    def _assert_target_runtime_paths(self, text, expected_home):
        self.assertIn(expected_home + "/", text)
        self.assertNotIn("{{AIDP_HOME}}", text)
        self.assertNotIn(".aidp/", text)

    @staticmethod
    def _manifest(root, rel):
        return json.loads((root / rel / ".aidp-runtime.json").read_text(encoding="utf-8"))

    @staticmethod
    def _normalized_runtime(root, rel, manifest):
        normalized = {}
        home = rel.as_posix()
        for name in manifest["files"]:
            path = root / rel / name
            data = path.read_bytes()
            try:
                normalized[name] = data.decode("utf-8").replace(home, "{{AIDP_HOME}}")
            except UnicodeDecodeError:
                normalized[name] = data
        return normalized

    def test_claude_only_uses_native_runtime_without_root_aidp(self):
        with H.TempRepo() as root:
            res = scaffold(root, "--version", "V0.1.0", "--agent", "claude")
            self._assert_absent(root / ".aidp")
            self.assertTrue((root / ".claude/aidp/scripts/agent_sync.py").is_file())
            self.assertTrue((root / ".claude/aidp/commands/sprint-dev.md").is_file())
            self.assertTrue((root / ".claude/aidp/skills/bugfix/SKILL.md").is_file())
            self.assertTrue((root / ".claude/aidp/plugins/chrome-devtools-mcp/.claude-plugin/plugin.json").is_file())
            self.assertTrue((root / ".claude/commands/sprint-dev.md").is_file())
            claude_command = (root / ".claude/commands/sprint-test.md").read_text(encoding="utf-8")
            self._assert_target_runtime_paths(claude_command, ".claude/aidp")
            self.assertTrue((root / ".claude/skills/aidp-code-engineer/SKILL.md").is_file())
            self.assertTrue((root / ".claude/skills/bugfix/SKILL.md").is_file())
            self.assertTrue((root / ".claude/plugins/chrome-devtools-mcp/.claude-plugin/plugin.json").is_file())
            self._assert_absent(root / ".agents")
            self._assert_roots_absent(root, ".codex/skills/aidp", ".dsh/commands")
            self._assert_fully_materialized(
                root, ".claude/aidp", ".claude/commands", ".claude/skills", ".claude/plugins",
            )
            self._assert_runtime_contract(root, Path(".claude/aidp"))
            manifest = self._manifest(root, Path(".claude/aidp"))
            self.assertEqual(manifest["schema"], "aidp.runtime/v1")
            self.assertEqual(manifest["source"], "claude")
            self.assertEqual(res["agents"], ["claude"])

    def test_codex_and_dsh_share_native_runtime_and_nested_plugin_skills(self):
        with H.TempRepo() as root:
            env, _ = fake_dsh_env(root)
            scaffold(root, "--version", "V0.1.0", "--agent", "codex,dsh", env=env)
            self._assert_absent(root / ".aidp")
            self.assertTrue((root / ".agents/aidp/scripts/agent_sync.py").is_file())
            self.assertTrue((root / ".agents/aidp/commands/sprint-dev.md").is_file())
            self.assertTrue((root / ".agents/aidp/skills/bugfix/SKILL.md").is_file())
            self.assertTrue((root / ".agents/aidp/plugins/chrome-devtools-mcp/.claude-plugin/plugin.json").is_file())
            self.assertTrue((root / ".agents/skills/aidp-code-engineer/SKILL.md").is_file())
            self.assertTrue((root / ".agents/skills/bugfix/SKILL.md").is_file())
            self.assertTrue((root / ".codex/skills/aidp/sprint-dev/SKILL.md").is_file())
            codex_skill = (root / ".codex/skills/aidp/sprint-test/SKILL.md").read_text(encoding="utf-8")
            marker = "## 原始命令正文（逐字保真）\n\n"
            self.assertIn(marker, codex_skill)
            self._assert_target_runtime_paths(codex_skill.split(marker, 1)[1], ".agents/aidp")
            self.assertTrue((root / ".dsh/commands/sprint-dev.md").is_file())
            dsh_command = (root / ".dsh/commands/sprint-test.md").read_text(encoding="utf-8")
            self._assert_target_runtime_paths(dsh_command, ".agents/aidp")
            self.assertTrue((root / ".agents/skills/chrome-devtools-mcp/skills/chrome-devtools/SKILL.md").is_file())
            self._assert_absent(root / ".codex/skills/chrome-devtools-mcp")
            self._assert_tree_equal(
                root / ".agents/skills/chrome-devtools-mcp/skills",
                root / ".agents/aidp/plugins/chrome-devtools-mcp/skills",
            )
            self.assertEqual(len(list(root.glob(".agents/aidp/.aidp-runtime.json"))), 1)
            self._assert_roots_absent(
                root, ".claude/aidp", ".claude/commands", ".claude/skills", ".claude/plugins",
            )
            self._assert_fully_materialized(
                root, ".agents/aidp", ".agents/skills", ".codex/skills/aidp", ".dsh/commands",
            )
            self._assert_runtime_contract(root, Path(".agents/aidp"))
            manifest = self._manifest(root, Path(".agents/aidp"))
            self.assertEqual(manifest["source"], "shared")

    def test_codex_only_uses_one_shared_runtime(self):
        with H.TempRepo() as root:
            scaffold(root, "--version", "V0.1.0", "--agent", "codex")
            self._assert_absent(root / ".aidp")
            self.assertTrue((root / ".agents/aidp/.aidp-runtime.json").is_file())
            self._assert_roots_absent(
                root, ".claude/aidp", ".claude/commands", ".claude/skills", ".claude/plugins",
                ".dsh/commands",
            )
            self.assertTrue((root / ".codex/skills/aidp/sprint-dev/SKILL.md").is_file())
            codex_skill = (root / ".codex/skills/aidp/sprint-test/SKILL.md").read_text(encoding="utf-8")
            marker = "## 原始命令正文（逐字保真）\n\n"
            self.assertIn(marker, codex_skill)
            self._assert_target_runtime_paths(codex_skill.split(marker, 1)[1], ".agents/aidp")
            self._assert_absent(root / ".dsh/commands")
            self.assertTrue((root / ".agents/skills/chrome-devtools-mcp/skills/chrome-devtools/SKILL.md").is_file())
            self._assert_absent(root / ".codex/skills/chrome-devtools-mcp")
            self._assert_tree_equal(
                root / ".agents/skills/chrome-devtools-mcp/skills",
                root / ".agents/aidp/plugins/chrome-devtools-mcp/skills",
            )
            self._assert_fully_materialized(
                root, ".agents/aidp", ".agents/skills", ".codex/skills/aidp",
            )
            self._assert_runtime_contract(root, Path(".agents/aidp"))

    def test_dsh_only_uses_one_shared_runtime(self):
        with H.TempRepo() as root:
            env, _ = fake_dsh_env(root)
            scaffold(root, "--version", "V0.1.0", "--agent", "dsh", env=env)
            self._assert_absent(root / ".aidp")
            self.assertTrue((root / ".agents/aidp/.aidp-runtime.json").is_file())
            self._assert_roots_absent(
                root, ".claude/aidp", ".claude/commands", ".claude/skills", ".claude/plugins",
                ".codex/skills/aidp",
            )
            self.assertTrue((root / ".dsh/commands/sprint-dev.md").is_file())
            dsh_command = (root / ".dsh/commands/sprint-test.md").read_text(encoding="utf-8")
            self._assert_target_runtime_paths(dsh_command, ".agents/aidp")
            self._assert_absent(root / ".codex/skills/aidp")
            self._assert_absent(root / ".codex/skills/chrome-devtools-mcp")
            self.assertTrue((root / ".agents/skills/chrome-devtools-mcp/skills/chrome-devtools/SKILL.md").is_file())
            self._assert_tree_equal(
                root / ".agents/skills/chrome-devtools-mcp/skills",
                root / ".agents/aidp/plugins/chrome-devtools-mcp/skills",
            )
            self._assert_fully_materialized(
                root, ".agents/aidp", ".agents/skills", ".dsh/commands",
            )
            self._assert_runtime_contract(root, Path(".agents/aidp"))

    def test_dangling_legacy_root_symlink_is_cleaned_before_init(self):
        with H.TempRepo() as root:
            legacy = root / ".aidp"
            legacy.symlink_to(root / "missing-legacy-runtime", target_is_directory=True)
            scaffold(root, "--version", "V0.1.0", "--agent", "claude")
            self._assert_absent(legacy)
            self.assertTrue((root / ".claude/aidp/.aidp-runtime.json").is_file())

    def test_all_agents_render_equivalent_runtime_packages(self):
        with H.TempRepo() as root:
            env, _ = fake_dsh_env(root)
            scaffold(root, "--version", "V0.1.0", "--agent", "claude,codex,dsh", env=env)
            claude_rel = Path(".claude/aidp")
            shared_rel = Path(".agents/aidp")
            self._assert_runtime_contract(root, claude_rel)
            self._assert_runtime_contract(root, shared_rel)
            self._assert_fully_materialized(
                root,
                ".claude/aidp", ".claude/commands", ".claude/skills", ".claude/plugins",
                ".agents/aidp", ".agents/skills", ".codex/skills/aidp", ".dsh/commands",
            )
            self._assert_absent(root / ".codex/skills/chrome-devtools-mcp")
            self._assert_tree_equal(
                root / ".agents/skills/chrome-devtools-mcp/skills",
                root / ".agents/aidp/plugins/chrome-devtools-mcp/skills",
            )
            self.assertTrue((root / claude_rel / ".aidp-runtime.json").is_file())
            self.assertTrue((root / shared_rel / ".aidp-runtime.json").is_file())
            claude = self._manifest(root, claude_rel)
            shared = self._manifest(root, shared_rel)
            self.assertEqual(claude["version"], shared["version"])
            claude_command = (root / ".claude/commands/sprint-test.md").read_text(encoding="utf-8")
            shared_command = (root / ".dsh/commands/sprint-test.md").read_text(encoding="utf-8")
            self._assert_target_runtime_paths(claude_command, ".claude/aidp")
            self.assertNotIn(".agents/aidp/", claude_command)
            self._assert_target_runtime_paths(shared_command, ".agents/aidp")
            self.assertNotIn(".claude/aidp/", shared_command)
            rc, output = agent_sync_check(root)
            self.assertEqual(rc, 0, output)
            self.assertEqual(set(claude["files"]), set(shared["files"]))
            self.assertEqual(
                self._normalized_runtime(root, claude_rel, claude),
                self._normalized_runtime(root, shared_rel, shared),
            )

    def test_link_mode_is_normalized_to_managed_copy(self):
        with H.TempRepo() as root:
            env, _ = fake_dsh_env(root)
            res = scaffold(
                root, "--version", "V0.1.0", "--agent", "claude,codex,dsh",
                "--adapter-mode", "link", env=env,
            )
            generated = (
                root / ".claude/aidp",
                root / ".claude/commands/sprint-dev.md",
                root / ".claude/skills/bugfix",
                root / ".claude/plugins/chrome-devtools-mcp",
                root / ".agents/aidp",
                root / ".agents/skills/aidp-code-engineer",
                root / ".agents/skills/bugfix",
                root / ".agents/skills/chrome-devtools-mcp",
                root / ".codex/skills/aidp/sprint-dev",
                root / ".dsh/commands/sprint-dev.md",
            )
            self.assertTrue(all(path.exists() and not path.is_symlink() for path in generated))
            self._assert_fully_materialized(
                root,
                ".claude/aidp", ".claude/commands", ".claude/skills", ".claude/plugins",
                ".agents/aidp", ".agents/skills", ".codex/skills/aidp", ".dsh/commands",
            )
            self._assert_absent(root / ".codex/skills/chrome-devtools-mcp")
            self._assert_tree_equal(
                root / ".agents/skills/chrome-devtools-mcp/skills",
                root / ".agents/aidp/plugins/chrome-devtools-mcp/skills",
            )
            self.assertTrue(any(
                action.get("action") == "normalized"
                and action.get("from") == "link"
                and action.get("to") == "managed-copy"
                for action in res["actions"]
            ), res["actions"])


class NonGitInitTest(unittest.TestCase):
    def test_plain_directory_initializes_without_git(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "plain"
            root.mkdir()
            res = scaffold(root, "--version", "V0.1.0", "--agent", "claude", "--user", "alice")
            self.assertEqual(res["vcs_mode"], "none")
            self.assertFalse(os.path.lexists(root / ".aidp"))
            self.assertTrue((root / ".claude/aidp/.aidp-runtime.json").is_file())
            self.assertFalse((root / ".git").exists())

    def test_missing_git_executable_does_not_block_init(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "plain"
            root.mkdir()
            bindir = Path(temp) / "empty-bin"
            bindir.mkdir()
            env = H.clean_env()
            env["PATH"] = str(bindir)
            res = scaffold(root, "--agent", "claude", "--user", "alice", env=env)
            self.assertEqual(res["vcs_mode"], "none")
            self.assertTrue((root / ".claude/aidp/.aidp-runtime.json").is_file())


class NativeIdempotencyTest(unittest.TestCase):
    def test_same_version_second_run_keeps_runtime_and_entries(self):
        with H.TempRepo() as root:
            first = scaffold(root, "--agent", "claude")
            before = (root / ".claude/aidp/.aidp-runtime.json").read_bytes()
            again = scaffold(root)
            self.assertEqual(first["mode"], "init")
            self.assertEqual(again["mode"], "upgrade")
            self.assertEqual(again["contract_decision"], "fill")
            self.assertEqual((root / ".claude/aidp/.aidp-runtime.json").read_bytes(), before)
            self.assertFalse([action for action in again["actions"]
                              if action["op"] in {"create", "update", "backup", "install"}],
                             again["actions"])


class NativePreflightTest(unittest.TestCase):
    def test_live_legacy_symlink_is_rejected_before_writes(self):
        import tempfile
        with H.TempRepo() as root, tempfile.TemporaryDirectory() as outside:
            external = Path(outside)
            (external / "sentinel").write_text("keep\n", encoding="utf-8")
            (root / ".aidp").symlink_to(external, target_is_directory=True)
            p = subprocess.run([sys.executable, str(H.SCRIPTS / "scaffold.py"), str(root),
                                "--agent", "claude", "--user", "alice", "--json"],
                               capture_output=True, text=True, env=H.clean_env())
            self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
            self.assertEqual((external / "sentinel").read_text(encoding="utf-8"), "keep\n")
            self.assertFalse((root / "memory").exists())
            self.assertFalse((root / ".claude/aidp").exists())

    def test_user_command_collision_has_no_partial_install(self):
        with H.TempRepo() as root:
            command = root / ".claude/commands/sprint-dev.md"
            command.parent.mkdir(parents=True)
            command.write_text("user command\n", encoding="utf-8")
            p = subprocess.run([sys.executable, str(H.SCRIPTS / "scaffold.py"), str(root),
                                "--agent", "claude", "--user", "alice", "--json"],
                               capture_output=True, text=True, env=H.clean_env())
            self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
            self.assertEqual(command.read_text(encoding="utf-8"), "user command\n")
            self.assertFalse((root / ".claude/aidp").exists())
            self.assertFalse((root / "memory").exists())


    def test_invalid_settings_rejected_without_partial_init(self):
        with H.TempRepo() as root:
            settings = root / ".claude/settings.json"
            settings.parent.mkdir(parents=True)
            settings.write_text("{invalid", encoding="utf-8")
            before = settings.read_bytes()
            p = subprocess.run([sys.executable, str(H.SCRIPTS / "scaffold.py"), str(root),
                                "--agent", "claude", "--user", "alice", "--json"],
                               capture_output=True, text=True, env=H.clean_env())
            self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
            self.assertEqual(settings.read_bytes(), before)
            self.assertFalse(os.path.lexists(root / ".claude/aidp"))
            self.assertFalse(os.path.lexists(root / "memory"))

    def test_new_agent_collision_preserves_existing_runtime(self):
        with H.TempRepo() as root:
            scaffold(root, "--agent", "claude", "--user", "alice")
            manifest = root / ".claude/aidp/.aidp-runtime.json"
            before = manifest.read_bytes()
            command = root / ".dsh/commands/sprint-dev.md"
            command.parent.mkdir(parents=True)
            command.write_text("user command\n", encoding="utf-8")
            p = subprocess.run([sys.executable, str(H.SCRIPTS / "scaffold.py"), str(root),
                                "--agent", "claude,dsh", "--user", "alice", "--json"],
                               capture_output=True, text=True, env=H.clean_env())
            self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
            self.assertEqual(manifest.read_bytes(), before)
            self.assertEqual(command.read_text(encoding="utf-8"), "user command\n")
            self.assertFalse(os.path.lexists(root / ".agents/aidp"))

    def test_install_failure_restores_existing_project_tree(self):
        with H.TempRepo() as root:
            user_file = root / "docs/private/notes.md"
            user_file.parent.mkdir(parents=True)
            user_file.write_text("keep\n", encoding="utf-8")

            def snapshot():
                return {p.relative_to(root).as_posix():
                        ("link", os.readlink(p)) if p.is_symlink() else
                        ("dir", None) if p.is_dir() else ("file", p.read_bytes())
                        for p in root.rglob("*") if ".git" not in p.relative_to(root).parts}

            before = snapshot()
            options = Namespace(mode="auto", agent="claude", user="alice", json=True,
                                version="V0.1.0", name_cn=None, force=False,
                                adapter_mode="copy", no_agent_sync=False,
                                keep_backups=5, keep_days=30)
            with mock.patch.object(S, "_install_native_skill", side_effect=OSError("injected failure")):
                with self.assertRaises(OSError):
                    S.run(root, options)
            self.assertEqual(snapshot(), before)

    def test_upgrade_failure_restores_runtime_and_user_document(self):
        with H.TempRepo() as root:
            scaffold(root, "--agent", "claude", "--user", "alice")
            document = root / "docs/private/notes.md"
            document.parent.mkdir(parents=True)
            document.write_text("keep\n", encoding="utf-8")
            runtime_manifest = root / ".claude/aidp/.aidp-runtime.json"
            command = root / ".claude/commands/sprint-dev.md"
            before = (runtime_manifest.read_bytes(), command.read_bytes(), document.read_bytes())
            options = Namespace(mode="auto", agent="claude", user="alice", json=True,
                                version="V0.1.0", name_cn=None, force=False,
                                adapter_mode="copy", no_agent_sync=False,
                                keep_backups=5, keep_days=30)
            with mock.patch.object(S, "run_agent_sync", side_effect=OSError("injected failure")):
                with self.assertRaises(OSError):
                    S.run(root, options)
            self.assertEqual((runtime_manifest.read_bytes(), command.read_bytes(), document.read_bytes()),
                             before)
            self.assertFalse(list(root.glob(".aidp-backup-*")))


class RuntimeCacheTest(unittest.TestCase):
    def test_agent_sync_bytecode_does_not_drift_runtime_manifest(self):
        import runtime_layout
        with H.TempRepo() as root:
            scaffold(root, "--agent", "claude")
            manifest = runtime_layout.validate_runtime(root / ".claude/aidp",
                                                       expected_home=".claude/aidp")
            self.assertEqual(manifest["schema"], "aidp.runtime/v1")
            cache = root / ".claude/aidp/scripts/__pycache__"
            if cache.exists():
                shutil.rmtree(cache)
            cache.symlink_to(root / "memory", target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlink"):
                runtime_layout.validate_runtime(root / ".claude/aidp",
                                                expected_home=".claude/aidp")


class AgentResolutionTest(unittest.TestCase):
    def test_markers_win_over_argument(self):
        with H.TempRepo() as root:
            (root / ".dsh").mkdir()
            res = scaffold(root, "--agent", "claude", "--no-agent-sync")
            self.assertEqual(res["agents"], ["dsh"])
            self.assertEqual(res["agent_source"], "markers")

    def test_env_then_default(self):
        with H.TempRepo() as root:
            env = H.clean_env()
            env["AIDP_AGENT"] = "codex"
            p = subprocess.run([sys.executable, str(H.SCRIPTS / "scaffold.py"), str(root), "--json", "--no-agent-sync"],
                               capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL)
            self.assertEqual(json.loads(p.stdout)["agents"], ["codex"])
        with H.TempRepo() as root:
            res = scaffold(root, "--no-agent-sync")
            self.assertEqual((res["agents"], res["agent_source"]), (["claude"], "default"))


class DshCommandPluginInstallTest(unittest.TestCase):
    COMMAND = ["plugin", "--profile", "web", "add", "github:SugarFatFree/dsh-agent-extension"]
    RETRY = "dsh plugin --profile web add github:SugarFatFree/dsh-agent-extension"

    def test_dsh_init_installs_plugin_once_before_agent_sync(self):
        with H.TempRepo() as root:
            env, log = fake_dsh_env(root)
            res = scaffold(root, "--version", "V0.1.0", "--agent", "dsh", env=env)
            self.assertEqual(log.read_text(encoding="utf-8").splitlines(), self.COMMAND)
            self.assertEqual(res["dsh_extensions"], "available")
            self.assertFalse([w for w in res["warnings"] if "dsh-agent-extension" in w], res["warnings"])
            ops = [a["op"] for a in res["actions"]]
            self.assertEqual(ops.count("dsh-plugin"), 1, ops)
            self.assertLess(ops.index("dsh-plugin"), ops.index("agent-sync"), ops)

    def test_nonzero_install_warns_and_scaffold_continues(self):
        with H.TempRepo() as root:
            env, log = fake_dsh_env(root, exit_code=7)
            res = scaffold(root, "--version", "V0.1.0", "--agent", "dsh", env=env)
            self.assertEqual(log.read_text(encoding="utf-8").splitlines(), self.COMMAND)
            warning = "\n".join(res["warnings"])
            self.assertIn("DSH 命令插件安装失败", warning)
            self.assertIn("exit 7", warning)
            self.assertIn("plugin install failed", warning)
            self.assertIn(self.RETRY, warning)
            self.assertEqual(res["dsh_extensions"], "unavailable")
            self.assertTrue((root / ".agents/aidp").is_dir(), "插件安装失败不得回滚脚手架文件")
            self.assertTrue(any(a["op"] == "agent-sync" for a in res["actions"]), res["actions"])

    def test_missing_dsh_warns_and_scaffold_continues(self):
        with H.TempRepo() as root:
            res = scaffold(root, "--version", "V0.1.0", "--agent", "dsh", env=missing_dsh_env(root))
            warning = "\n".join(res["warnings"])
            self.assertIn("DSH 命令插件安装失败", warning)
            self.assertIn(self.RETRY, warning)
            self.assertEqual(res["dsh_extensions"], "unavailable")
            self.assertTrue((root / ".agents/aidp").is_dir())
            self.assertTrue(any(a["op"] == "agent-sync" for a in res["actions"]), res["actions"])

    def test_timeout_is_bounded_warns_and_agent_sync_continues(self):
        with H.TempRepo() as root:
            real_run = subprocess.run
            install_kwargs = {}

            def run_with_timeout(cmd, *args, **kwargs):
                if tuple(cmd) == S.DSH_COMMAND_PLUGIN:
                    install_kwargs.update(kwargs)
                    raise subprocess.TimeoutExpired(cmd, kwargs["timeout"],
                                                    stderr="plugin timed out\nstill running")
                return real_run(cmd, *args, **kwargs)

            options = Namespace(
                mode="auto", agent="dsh", json=True, user=None, name_cn=None,
                version="V0.1.0", force=False, keep_backups=L.PRUNE_KEEP_LAST_DEFAULT,
                keep_days=L.PRUNE_KEEP_DAYS_DEFAULT, no_agent_sync=False, adapter_mode="link")
            with mock.patch.object(S.subprocess, "run", side_effect=run_with_timeout):
                res = S.run(root, options)

            self.assertIs(install_kwargs["stdin"], subprocess.DEVNULL)
            self.assertEqual(install_kwargs["timeout"], 120)
            warning = "\n".join(res["warnings"])
            self.assertIn("超时 120 秒", warning)
            self.assertIn("plugin timed out still running", warning)
            self.assertIn(self.RETRY, warning)
            self.assertTrue(any(a["op"] == "agent-sync" for a in res["actions"]), res["actions"])

    def test_nonzero_detail_is_single_line_and_bounded(self):
        with H.TempRepo() as root:
            env, _ = fake_dsh_env(root, exit_code=9)
            env["DSH_TEST_MESSAGE"] = "first line\n" + ("x" * 600) + "\nlast line"
            res = scaffold(root, "--version", "V0.1.0", "--agent", "dsh", env=env)
            warning = next(w for w in res["warnings"] if "DSH 命令插件安装失败" in w)
            self.assertNotIn("\n", warning)
            self.assertIn("exit 9", warning)
            self.assertIn("first line", warning)
            self.assertIn(self.RETRY, warning)
            detail = warning.split("：", 1)[1].split("；请手工重试", 1)[0]
            self.assertLessEqual(len(detail), 300)

    def test_non_dsh_init_does_not_install(self):
        for agent in ("claude", "codex"):
            with self.subTest(agent=agent), H.TempRepo() as root:
                env, log = fake_dsh_env(root)
                res = scaffold(root, "--version", "V0.1.0", "--agent", agent, env=env)
                self.assertFalse(log.exists())
                self.assertFalse(any(a["op"] == "dsh-plugin" for a in res["actions"]))

    def test_migrate_and_upgrade_ensure_extension(self):
        with H.TempRepo() as root:
            (root / "app.py").write_text("print('demo')\n", encoding="utf-8")
            env, log = fake_dsh_env(root)
            res = scaffold(root, "--version", "V0.1.0", "--agent", "dsh", env=env)
            self.assertEqual(res["mode"], "migrate")
            self.assertEqual(log.read_text(encoding="utf-8").splitlines(), self.COMMAND)

        with H.TempRepo() as root:
            scaffold(root, "--version", "V0.1.0", "--agent", "claude")
            (root / ".dsh").mkdir(exist_ok=True)
            env, log = fake_dsh_env(root)
            res = scaffold(root, env=env)
            self.assertEqual(res["mode"], "upgrade")
            self.assertIn("dsh", res["agents"])
            self.assertEqual(log.read_text(encoding="utf-8").splitlines(), self.COMMAND)


class UpgradeTest(unittest.TestCase):
    def test_overwrite_protect_and_finalize(self):
        with H.TempRepo() as root:
            scaffold(root, "--version", "V0.1.0", "--agent", "claude")
            subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(root), "commit", "-qm", "init"], check=True, capture_output=True)

            scaffold_marker.write_version(root, "V0.0.1")
            cmd = root / ".aidp/commands/sprint-dev.md"
            original = cmd.read_bytes()
            cmd.write_text("本地改动\n", encoding="utf-8")
            (root / ".aidp/agents/qa.md").unlink()
            (root / ".aidp/commands/retired-cmd.md").write_text("旧命令\n", encoding="utf-8")
            (root / ".aidp/skills/my-skill").mkdir()
            (root / ".aidp/skills/my-skill/SKILL.md").write_text("私有\n", encoding="utf-8")
            fill = root / ".aidp/reference/子Agent必读.md"
            fill.write_text(fill.read_text(encoding="utf-8") + "\n- 项目踩坑：接口 A 必须带租户头\n", encoding="utf-8")
            # 模拟上一版下发的骨架与新版不同（新版骨架有变化才需要语义合并）
            ledger = json.loads((root / L.USER_FILLABLE_BASELINE).read_text(encoding="utf-8"))
            ledger["reference/子Agent必读.md"] = L.sha256(b"previous skeleton\n")
            (root / L.USER_FILLABLE_BASELINE).write_text(json.dumps(ledger), encoding="utf-8")
            claude_md = root / "CLAUDE.md"
            claude_md.write_text(claude_md.read_text(encoding="utf-8") + "\n- 团队约定：分支名带工单号\n",
                                 encoding="utf-8")

            claude_md.write_text(claude_md.read_text(encoding="utf-8").replace("- **当前版本**：V0.1.0",
                                                                               "- **当前版本**：V0.3.0")
                                 .replace("## 核心约定", "旧版正文残留行 OLD_BODY_MARK\n\n## 核心约定", 1),
                                 encoding="utf-8")
            res = scaffold(root)
            self.assertEqual(res["mode"], "upgrade")
            self.assertEqual(res["contract_decision"], "overwrite")
            self.assertEqual(cmd.read_bytes(), original, "低版本升级必须覆盖契约文件")
            self.assertIn(".aidp/commands/sprint-dev.md", res["local_overwritten"], "本地改过的契约须逐个列出")
            self.assertTrue(any("本地改过" in w and res["backup"] in w for w in res["warnings"]), res["warnings"])
            self.assertEqual((root / res["backup"] / ".aidp/commands/sprint-dev.md").read_text(encoding="utf-8"),
                             "本地改动\n", "被覆盖的本地改动可从备份找回")
            self.assertTrue((root / ".aidp/agents/qa.md").is_file())
            self.assertIn("项目踩坑：接口 A 必须带租户头", fill.read_text(encoding="utf-8"), "已填写的用户填充型契约不得覆盖")
            self.assertEqual((root / ".aidp/skills/my-skill/SKILL.md").read_text(), "私有\n")
            self.assertIn(".aidp/commands/retired-cmd.md", res["orphans"])
            self.assertTrue((root / ".aidp/commands/retired-cmd.md").is_file(), "孤儿只报告不删除")
            queued = {e.split("\t")[0] for e in res["rewrite_queue"]}
            self.assertEqual(queued, {".aidp/reference/子Agent必读.md"}, "记忆文件按锚点确定性合并，不进队列")
            for e in res["rewrite_queue"]:
                self.assertFalse(os.path.isabs(e.split("\t")[1]), "队列模板路径必须是仓库相对路径")
                self.assertTrue((root / e.split("\t")[1]).is_file(), e)
            body = claude_md.read_text(encoding="utf-8")
            self.assertIn("团队约定：分支名带工单号", body)
            self.assertIn("- **当前版本**：V0.3.0", body, "「当前状态」字段值保留")
            self.assertNotIn("OLD_BODY_MARK", body, "「项目自定义」之前的正文取新模板")
            self.assertTrue(any(a["op"] == "merge" and a["path"] == "CLAUDE.md" for a in res["actions"]))
            self.assertFalse((root / ".aidp/skills/aidp-code-engineer/scripts/tests").exists(), "模板单测不随安装下发")
            self.assertEqual(scaffold_marker.read_pending(root), BUNDLE_VERSION)
            self.assertEqual(scaffold_marker.read_version(root), "V0.0.1", "未收口不得推进正式版本")
            self.assertTrue(L.scan_backups(root))
            rc, errors, out = H.verify(root)
            self.assertTrue(any("语义改写队列" in e for e in errors), out)

            self.assertEqual(H.run_script("finalize_upgrade.py", "--root", root, check=False).returncode, 1)
            fill.write_text(fill.read_text(encoding="utf-8") + "\n<!-- 已按新骨架合并 -->\n", encoding="utf-8")
            H.run_script("finalize_upgrade.py", "--root", root)
            self.assertEqual(scaffold_marker.read_version(root), BUNDLE_VERSION)
            self.assertIsNone(scaffold_marker.read_pending(root))
            self.assertFalse((root / L.REWRITE_QUEUE_FILE).exists())

            # 收口后再跑（同版本 fill / 低版本 overwrite）：骨架未变，已填写的用户填充型契约不得再入队
            again = scaffold(root)
            self.assertEqual(again["contract_decision"], "fill")
            self.assertEqual(again["rewrite_queue"], [])
            self.assertIsNone(scaffold_marker.read_pending(root))
            scaffold_marker.write_version(root, "V0.0.1")
            again = scaffold(root)
            self.assertEqual(again["contract_decision"], "overwrite")
            self.assertEqual(again["rewrite_queue"], [], again["actions"])
            self.assertEqual(scaffold_marker.read_version(root), BUNDLE_VERSION)
            self.assertEqual(again["local_overwritten"], [], "无本地改动时不误报")

            # 同版本：只补缺失、不覆盖已有正文
            cmd.write_text("同版本本地改动\n", encoding="utf-8")
            (root / ".aidp/agents/qa.md").unlink()
            res = scaffold(root)
            self.assertEqual(res["contract_decision"], "fill")
            self.assertEqual(cmd.read_text(encoding="utf-8"), "同版本本地改动\n")
            self.assertTrue((root / ".aidp/agents/qa.md").is_file())

    def test_newer_project_is_protected(self):
        with H.TempRepo() as root:
            scaffold(root, "--agent", "codex")
            scaffold_marker.write_version(root, "V99.0.0")
            cmd = root / ".aidp/commands/sprint-dev.md"
            cmd.write_text("更新版本的内容\n", encoding="utf-8")
            res = scaffold(root)
            self.assertEqual(res["contract_decision"], "protect")
            self.assertEqual(cmd.read_text(encoding="utf-8"), "更新版本的内容\n")
            self.assertEqual(scaffold_marker.read_version(root), "V99.0.0")


class DeliveredFilesTest(unittest.TestCase):
    def test_docs_readme_and_memory_templates(self):
        with H.TempRepo() as root:
            scaffold(root, "--version", "V0.1.0", "--agent", "codex")
            readme = root / "docs/testing/README.md"
            pristine_other = root / "docs/plans/README.md"
            want_other = pristine_other.read_bytes()
            readme.write_text(readme.read_text(encoding="utf-8") + "\n- 团队补充：回归用例放 regression/\n",
                              encoding="utf-8")
            pristine_other.write_text("旧版骨架\n", encoding="utf-8")
            brief = root / "memory/projectBrief.md"
            brief.write_text("# {{project}}\n\n## 项目简介\n\n团队已填写的简介\n", encoding="utf-8")
            # 模拟：上一版下发的 plans README 就是「旧版骨架」、testing README 是当前版（项目改过）
            ledger = json.loads((root / L.USER_FILLABLE_BASELINE).read_text(encoding="utf-8"))
            ledger["docs/plans/README.md"] = L.sha256(b"\xe6\x97\xa7\xe7\x89\x88\xe9\xaa\xa8\xe6\x9e\xb6\n")
            ledger["docs/testing/README.md"] = L.sha256(b"old skeleton\n")
            (root / L.USER_FILLABLE_BASELINE).write_text(json.dumps(ledger), encoding="utf-8")

            scaffold_marker.write_version(root, "V0.0.1")
            res = scaffold(root)
            self.assertIn("团队补充", readme.read_text(encoding="utf-8"), "项目改过的 docs README 不得覆盖")
            self.assertIn("docs/testing/README.md", {e.split("\t")[0] for e in res["rewrite_queue"]})
            self.assertEqual(pristine_other.read_bytes(), want_other, "未改过的 docs README 随新版刷新")
            body = brief.read_text(encoding="utf-8")
            self.assertIn("团队已填写的简介", body, "残留占位符只替换占位符本身")
            self.assertIn("# demo", body)

    def test_same_version_writes_are_backed_up(self):
        with H.TempRepo() as root:
            scaffold(root, "--version", "V0.1.0", "--agent", "claude")
            init_doc = root / "docs/init/README.md"
            init_doc.write_text("本地误改\n", encoding="utf-8")
            res = scaffold(root)
            self.assertEqual(res["contract_decision"], "fill")
            self.assertTrue(res["backup"], res["actions"])
            self.assertEqual((root / res["backup"] / "docs/init/README.md").read_text(encoding="utf-8"), "本地误改\n")


class OptionalRuleRefreshTest(unittest.TestCase):
    def test_optional_rule_refresh(self):
        tpl_rel, inst_rel = L.OPTIONAL_RULES[0]
        with H.TempRepo() as root:
            scaffold(root, "--version", "V0.1.0", "--agent", "claude")
            old_tpl, inst = root / ".aidp" / tpl_rel, root / ".aidp" / inst_rel
            old_tpl.write_text("旧版可选规则\n", encoding="utf-8")
            inst.write_text("旧版可选规则\n", encoding="utf-8")
            scaffold_marker.write_version(root, "V0.0.1")
            scaffold(root)
            self.assertEqual(inst.read_bytes(), (L.BUNDLE_AIDP / tpl_rel).read_bytes(), "未改过的安装位随模板升级刷新")

            old_tpl.write_text("旧版可选规则\n", encoding="utf-8")
            inst.write_text("项目改过的可选规则\n", encoding="utf-8")
            scaffold_marker.write_version(root, "V0.0.1")
            res = scaffold(root)
            self.assertEqual(inst.read_text(encoding="utf-8"), "项目改过的可选规则\n", "反例：本地改过的安装位不覆盖")
            self.assertTrue(any(inst_rel in w for w in res["warnings"]), res["warnings"])
            self.assertNotIn(f".aidp/{inst_rel}", res["orphans"], "已安装的可选规则不算孤儿")


class NativeAdapterVerifyTest(unittest.TestCase):
    def test_copy_mode_detects_codex_and_dsh_native_entries(self):
        with H.TempRepo() as root:
            source = root / ".aidp/commands/sprint-dev.md"
            source.parent.mkdir(parents=True)
            source.write_text("# sprint-dev\n", encoding="utf-8")
            codex = root / ".codex/skills/aidp/sprint-dev"
            codex.mkdir(parents=True)
            (codex / "SKILL.md").write_text("---\nname: sprint-dev\n---\n", encoding="utf-8")
            (codex / ".aidp-generated").write_text("native-command\n", encoding="utf-8")
            self.assertEqual(V._adapter_mode(root, None), "copy")

        with H.TempRepo() as root:
            source = root / ".aidp/commands/sprint-dev.md"
            source.parent.mkdir(parents=True)
            source.write_text("# sprint-dev\n", encoding="utf-8")
            dsh = root / ".dsh/commands"
            dsh.mkdir(parents=True)
            (dsh / "sprint-dev.md").write_text("# sprint-dev\n", encoding="utf-8")
            self.assertEqual(V._adapter_mode(root, None), "copy")

        with H.TempRepo() as root:
            source = root / ".aidp/plugins/chrome-devtools-mcp/skills/chrome-devtools"
            source.mkdir(parents=True)
            (source / "SKILL.md").write_text("---\nname: chrome-devtools\n---\n", encoding="utf-8")
            plugin = root / ".agents/skills/chrome-devtools-mcp/skills"
            plugin.mkdir(parents=True)
            (plugin / "chrome-devtools").mkdir()
            (plugin / "chrome-devtools/SKILL.md").write_text("---\nname: chrome-devtools\n---\n", encoding="utf-8")
            self.assertEqual(V._adapter_mode(root, None), "copy")

    def test_copy_mode_ignores_user_owned_symlink(self):
        with H.TempRepo() as root:
            source = root / ".aidp/commands/sprint-dev.md"
            source.parent.mkdir(parents=True)
            source.write_text("# sprint-dev\n", encoding="utf-8")
            generated = root / ".codex/skills/aidp/sprint-dev"
            generated.mkdir(parents=True)
            (generated / "SKILL.md").write_text("---\nname: sprint-dev\n---\n", encoding="utf-8")
            (generated / ".aidp-generated").write_text("native-command\n", encoding="utf-8")
            user_source = root / "user-skill"
            user_source.mkdir()
            (user_source / "SKILL.md").write_text("---\nname: user\n---\n", encoding="utf-8")
            user_link = root / ".codex/skills/user"
            user_link.parent.mkdir(parents=True, exist_ok=True)
            user_link.symlink_to(user_source)
            self.assertEqual(V._adapter_mode(root, None), "copy")

    def test_template_verify_has_no_router_source_check(self):
        self.assertFalse(hasattr(V, "check_router_source"))

    def test_navigation_check_excludes_maintenance_plan_subtree_only(self):
        with H.TempRepo() as root:
            for rel in (
                "docs/superpowers/specs/designs",
                "docs/superpowers/specs/decisions",
                "docs/superpowers/specs/reviews",
                "docs/init/guides",
                "docs/init/contracts",
                "docs/init/examples",
            ):
                (root / rel).mkdir(parents=True)
            result = V.VerifyResult()
            V.check_code_readme(root, result)
            self.assertFalse(
                any("docs/superpowers" in warning for warning in result.warnings),
                result.warnings,
            )
            self.assertTrue(
                any("docs/init" in warning for warning in result.warnings),
                result.warnings,
            )


class ObsoleteRouterMigrationTest(unittest.TestCase):
    MARKER = "<!-- 命令表由 .aidp/scripts/agent_sync.py 按 .aidp/commands/ 维护 -->\n"

    @staticmethod
    def _options(mode="upgrade"):
        return Namespace(
            mode=mode, agent="claude", json=True, user=None, name_cn=None,
            version="V0.1.0", force=False, keep_backups=L.PRUNE_KEEP_LAST_DEFAULT,
            keep_days=L.PRUNE_KEEP_DAYS_DEFAULT, no_agent_sync=True, adapter_mode="link")

    @classmethod
    def _router(cls, root, modified=False):
        router = root / ".aidp/skills/aidp-cmd"
        (router / "agents").mkdir(parents=True, exist_ok=True)
        body = S._legacy_router_skill(root)
        if modified:
            body += "\n项目自定义路由内容\n"
        (router / "SKILL.md").write_text(body, encoding="utf-8")
        (router / "agents/openai.yaml").write_text(S.LEGACY_ROUTER_OPENAI_YAML, encoding="utf-8")
        return router

    def test_upgrade_removes_generated_router_without_extra_backup(self):
        with H.TempRepo() as root:
            scaffold(root, "--version", "V0.1.0", "--agent", "claude", "--no-agent-sync")
            router = self._router(root)
            before = len(L.scan_backups(root))
            res = S.run(root, self._options())
            self.assertFalse(router.exists())
            self.assertEqual(len(L.scan_backups(root)), before)
            self.assertTrue(any(a["op"] == "remove" and a["path"] == ".aidp/skills/aidp-cmd/"
                                for a in res["actions"]), res["actions"])

    def test_modified_router_is_backed_up_then_removed(self):
        with H.TempRepo() as root:
            scaffold(root, "--version", "V0.1.0", "--agent", "claude", "--no-agent-sync")
            router = self._router(root, modified=True)
            res = S.run(root, self._options())
            self.assertFalse(router.exists())
            self.assertTrue(res["backup"], res)
            saved = root / res["backup"] / ".aidp/skills/aidp-cmd/SKILL.md"
            self.assertIn("项目自定义路由内容", saved.read_text(encoding="utf-8"))
            self.assertTrue(any("旧命令路由已备份" in w and res["backup"] in w for w in res["warnings"]),
                            res["warnings"])

    def test_generated_router_with_extra_content_is_backed_up_completely(self):
        with H.TempRepo() as root:
            scaffold(root, "--version", "V0.1.0", "--agent", "claude", "--no-agent-sync")
            router = self._router(root)
            (router / "notes.md").write_text("用户补充说明\n", encoding="utf-8")
            (router / "custom").mkdir()
            (router / "custom/rule.txt").write_text("用户规则\n", encoding="utf-8")
            res = S.run(root, self._options())
            self.assertFalse(router.exists())
            backup = root / res["backup"] / ".aidp/skills/aidp-cmd"
            self.assertEqual((backup / "notes.md").read_text(encoding="utf-8"), "用户补充说明\n")
            self.assertEqual((backup / "custom/rule.txt").read_text(encoding="utf-8"), "用户规则\n")
            self.assertTrue(any("旧命令路由已备份" in w for w in res["warnings"]), res["warnings"])

    def test_backup_failure_preserves_modified_router(self):
        with H.TempRepo() as root:
            scaffold(root, "--version", "V0.1.0", "--agent", "claude", "--no-agent-sync")
            router = self._router(root, modified=True)
            original = (router / "SKILL.md").read_text(encoding="utf-8")
            with mock.patch.object(S.shutil, "copytree", side_effect=OSError("disk full")):
                res = S.run(root, self._options())
            self.assertTrue(router.is_dir())
            self.assertEqual((router / "SKILL.md").read_text(encoding="utf-8"), original)
            self.assertTrue(any("旧命令路由备份失败" in w and "disk full" in w for w in res["warnings"]),
                            res["warnings"])

    def test_missing_router_is_noop_and_init_does_not_migrate(self):
        with H.TempRepo() as root:
            scaffold(root, "--version", "V0.1.0", "--agent", "claude", "--no-agent-sync")
            shutil.rmtree(root / ".aidp/skills/aidp-cmd", ignore_errors=True)
            res = S.run(root, self._options())
            self.assertFalse(any("旧命令路由" in w for w in res["warnings"]), res["warnings"])

        with H.TempRepo() as root:
            router = self._router(root, modified=True)
            S.cleanup_obsolete_router(root, "init", S.Backup(root, S.Report()), S.Report())
            self.assertTrue(router.is_dir())

    def test_explicit_migrate_cleans_generated_router(self):
        with H.TempRepo() as root:
            router = self._router(root)
            res = S.run(root, self._options("migrate"))
            self.assertEqual(res["mode"], "migrate")
            self.assertFalse(router.exists())


class VerifyIsolationTest(unittest.TestCase):
    def test_foreign_version_user_dirs_not_created(self):
        with H.TempRepo() as root:
            scaffold(root, "--version", "V0.1.0", "--agent", "claude")
            p = H.run_script("verify.py", root, "V0.0.1", "alice", "--no-guards", check=False)
            self.assertFalse((root / "docs/implementation/V0.0.1").exists(), p.stdout)
            self.assertFalse((root / "memory/V0.0.1").exists(), p.stdout)
            (root / "docs/plans/V0.1.0").rmdir() if not any((root / "docs/plans/V0.1.0").iterdir()) else None
            H.run_script("verify.py", root, "V0.1.0", "tester", "--no-guards", check=False)
            self.assertTrue((root / "docs/plans/V0.1.0").is_dir(), "当前版本 × 本机开发者仍发现即修")


class MigrateTest(unittest.TestCase):
    def test_existing_project_content_is_kept(self):
        with H.TempRepo(name="shop") as root:
            user_md = "# 商城项目\n\n## 团队规则\n\n- 自定义规则 XYZ\n- 开发时用 pnpm build 看效果\n"
            (root / "CLAUDE.md").write_text(user_md, encoding="utf-8")
            (root / "web").mkdir()
            (root / "web/package.json").write_text('{"dependencies": {"vue": "^3"}}', encoding="utf-8")
            (root / "backend").mkdir()
            (root / "backend/pom.xml").write_text("<project/>", encoding="utf-8")
            (root / "PRD-用户中心.md").write_text("# PRD\n", encoding="utf-8")
            (root / "原型").mkdir()
            (root / "原型/index.html").write_text("<html/>", encoding="utf-8")

            det = H.run_json("scaffold.py", root, "--detect")
            self.assertEqual(det["mode"], "migrate")
            units = {u["path"]: u for u in det["code_units"]}
            self.assertEqual(units["web"]["suggested"], "code/frontend/web")
            self.assertEqual(units["backend"]["suggested"], "code/backend/shop-server")
            self.assertEqual(det["inputs"], {"prd": ["PRD-用户中心.md"], "prototype": ["原型"]})
            self.assertEqual(det["memory_files"], ["CLAUDE.md"])

            res = scaffold(root, "--version", "V1.0.0", "--agent", "claude")
            self.assertEqual(res["mode"], "migrate")
            body = (root / "CLAUDE.md").read_text(encoding="utf-8")
            self.assertTrue(L.looks_like_aidp_body(body))
            custom = L.custom_section(body)
            self.assertIn("自定义规则 XYZ", custom)
            self.assertIn("### 原 CLAUDE.md 内容", custom)
            self.assertNotIn("{{project}}", body)
            self.assertIn("CLAUDE.md", {e.split("\t")[0] for e in res["rewrite_queue"]})
            backup = L.scan_backups(root)[0][0]
            self.assertEqual((backup / "CLAUDE.md").read_text(encoding="utf-8"), user_md)
            self.assertTrue((root / "web/package.json").is_file(), "已有代码不得移动")
            self.assertTrue((root / "backend/pom.xml").is_file(), "已有代码不得移动")

            rc, errors, out = H.verify(root, "V1.0.0")
            self.assertTrue(any("pnpm build" in l for l in out.splitlines() if "[WARN]" in l), out)

            H.run_script("migrate.py", "place-inputs", root, "--version", "V1.0.0")
            self.assertTrue((root / "docs/requirements/V1.0.0/产品提供/PRD-用户中心.md").is_file())
            self.assertTrue((root / "docs/prototype/V1.0.0/code/原型/index.html").is_file())
            self.assertFalse((root / "PRD-用户中心.md").exists())

    def test_template_project_is_refused(self):
        p = H.run_script("scaffold.py", H.REPO, "--no-agent-sync", check=False)
        self.assertEqual(p.returncode, 2)


if __name__ == "__main__":
    unittest.main()
