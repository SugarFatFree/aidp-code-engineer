#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scaffold.py 三模式端到端：init 冒烟（三种 Agent 组合）、upgrade 覆盖与用户填充型保护、migrate 保留用户内容。"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

import _helpers as H
import scaffold as S
import scaffold_lib as L
import scaffold_marker
import runtime_layout
import verify as V

BUNDLE_VERSION = L.bundle_version()


def scaffold(root, *args, env=None):
    p = subprocess.run(
        [sys.executable, str(H.SCRIPTS / "scaffold.py"), str(root), "--json", *map(str, args)],
        capture_output=True, text=True, env=env or H.clean_env(), stdin=subprocess.DEVNULL)
    if p.returncode != 0:
        raise AssertionError(f"scaffold.py → exit {p.returncode}\n{p.stdout}\n{p.stderr}")
    return json.loads(p.stdout)


# 假 dsh：**带状态**的 CLI —— 新实现先探测（--version / plugin list）再决定是否 add，
# 一个「记下 argv 就退出」的哑桩已经不够用了。每次调用把 argv 追加进日志，便于断言「是否真的 add 过」。
FAKE_DSH_SH = """#!/bin/sh
argv="$*"
printf '%s\n' "$argv" >> "$DSH_TEST_LOG"
if [ "$1" = "--version" ]; then printf '0.1.5-rc.2\n'; exit 0; fi
case "$argv" in
  *"list --json"*)
      printf 'error: unexpected argument --json\n' >&2
      exit 2 ;;
  *"list"*)
      printf 'NAME                       VERSION   PROFILE\n'
      printf -- '-------------------------  --------  -------\n'
      # ⛔ 只用 shell 内建：用例把 PATH 收窄到只剩假 dsh，`cat` 这类外部命令根本不在
      if [ -f "$DSH_TEST_STATE" ]; then
        while IFS= read -r line; do printf '%s\n' "$line"; done < "$DSH_TEST_STATE"
      fi
      exit 0 ;;
  *" add "*)
      if [ "${DSH_TEST_EXIT:-0}" -ne 0 ]; then
        printf '%s\n' "${DSH_TEST_MESSAGE:-plugin install failed}" >&2
        exit "${DSH_TEST_EXIT}"
      fi
      if [ "${DSH_TEST_ADD_EFFECT:-install}" = "install" ]; then
        printf 'dsh-agent-extension@0.1.4  0.1.4  web\n' >> "$DSH_TEST_STATE"
      fi
      exit 0 ;;
esac
printf 'dsh: unknown command\n' >&2
exit 2
"""


def fake_dsh_env(root, exit_code=0, preinstalled=False, add_effect="install"):
    """隔离 DSH 调用；PATH 只暴露假 dsh 与真实 git。"""
    bindir = root.parent / ".test-bin"
    bindir.mkdir(exist_ok=True)
    log = root.parent / ".dsh-plugin-argv"
    state = root.parent / ".dsh-plugin-state"
    state.write_text("dsh-agent-extension@0.1.4  0.1.4  web\n" if preinstalled else "",
                     encoding="utf-8")
    dsh = bindir / "dsh"
    dsh.write_text(FAKE_DSH_SH, encoding="utf-8")
    dsh.chmod(0o755)
    git = shutil.which("git")
    if not git:
        raise AssertionError("测试环境缺 git")
    if not (bindir / "git").exists():
        (bindir / "git").symlink_to(git)
    env = H.clean_env()
    env["PATH"] = str(bindir)
    env["DSH_TEST_LOG"] = str(log)
    env["DSH_TEST_STATE"] = str(state)
    env["DSH_TEST_EXIT"] = str(exit_code)
    env["DSH_TEST_ADD_EFFECT"] = add_effect
    return env, log


def dsh_calls(log):
    return [line for line in log.read_text(encoding="utf-8").splitlines() if line] \
        if log.is_file() else []


def dsh_add_calls(log):
    return [c for c in dsh_calls(log) if " add " in f" {c} "]


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
    runtime = root / ".agents"
    if not runtime.is_dir():
        runtime = root / ".claude"
    p = subprocess.run([sys.executable, str(runtime / "scripts/agent_sync.py"),
                        "--root", str(root), "--check"],
                       capture_output=True, text=True, env=H.clean_env())
    return p.returncode, p.stdout




def _runtime_source_for(_root):
    """测试里渲染运行包所用的真源（与 scaffold 同一口径）。"""
    import scaffold as _s
    return _s._runtime_source()

def assert_no_runtime(case, root, home, allow=()):
    """回滚 / 未安装时的正确断言：**运行包不存在**，而不是"整个目录不存在"。

    ⛔ 运行根降层后就是 `.claude` / `.agents` 本身 —— 它们是 Agent 标记目录，
    往往由项目（或夹具）先建好，回滚绝不该把它删掉。真正该断言的是：
    受管 manifest 不在、且我们铺的受管目录一个都没剩下。
    """
    import runtime_layout as _rl
    base = root / home
    case.assertFalse((base / _rl.RUNTIME_MANIFEST).exists(), f"{home} 仍有运行包 manifest")
    left = []
    for name in _rl.RUNTIME_DIRS:
        directory = base / name
        if not directory.is_dir():
            continue
        # `skills/` 里可能只剩**安装器自身** —— 它按 RUNTIME_EXCLUDES 就不属于运行包，
        # 与"运行包是否装上"无关，不该让这条断言判红。
        # `allow` 收用例明确要求**保留**的用户文件：回滚保住用户数据是对的，
        # 不能被"没装上运行包"这条断言当成残留判红。
        rest = sorted(x.name for x in directory.iterdir()
                      if x.name != L.SKILL_NAME and x.name not in allow)
        # 空目录不算残留：用户自己建的容器目录（或 allow 掉内容后剩下的空壳）本就该留着。
        if rest:
            left.append(f"{name}({'、'.join(rest)})")
    case.assertEqual(left, [], f"{home} 残留受管内容：{left}")

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
        # ★ 安装器与运行契约的边界改由 **manifest** 划，不再由目录位置划：
        #   运行根降层后 `<运行根>/skills/` 既放公共 SKILL、也放安装器自身（Agent 的发现位
        #   就是这里）。所以它**存在是正常的**，真正要守的是"它不进运行包清单"。
        manifest_path = runtime / runtime_layout.RUNTIME_MANIFEST
        if manifest_path.is_file():
            files = json.loads(manifest_path.read_text(encoding="utf-8"))["files"]
            leaked = sorted(k for k in files if k.startswith("skills/aidp-code-engineer/"))
            self.assertEqual(leaked, [], f"安装器不得进运行包清单：{leaked[:3]}")
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
            self.assertTrue((root / ".claude/scripts/agent_sync.py").is_file())
            self.assertTrue((root / ".claude/commands/sprint-dev.md").is_file())
            self.assertTrue((root / ".claude/skills/bugfix/SKILL.md").is_file())
            self.assertTrue((root / ".claude/plugins/chrome-devtools-mcp/.claude-plugin/plugin.json").is_file())
            self.assertTrue((root / ".claude/commands/sprint-dev.md").is_file())
            claude_command = (root / ".claude/commands/sprint-test.md").read_text(encoding="utf-8")
            self._assert_target_runtime_paths(claude_command, ".claude")
            self.assertTrue((root / ".claude/skills/aidp-code-engineer/SKILL.md").is_file())
            self.assertTrue((root / ".claude/skills/bugfix/SKILL.md").is_file())
            self.assertTrue((root / ".claude/plugins/chrome-devtools-mcp/.claude-plugin/plugin.json").is_file())
            self._assert_absent(root / ".agents")
            self._assert_roots_absent(root, ".codex/skills/aidp", ".dsh/commands")
            self._assert_fully_materialized(
                root, ".claude", ".claude/commands", ".claude/skills", ".claude/plugins",
            )
            self._assert_runtime_contract(root, Path(".claude"))
            manifest = self._manifest(root, Path(".claude"))
            self.assertEqual(manifest["schema"], "aidp.runtime/v1")
            self.assertEqual(manifest["source"], "claude")
            self.assertEqual(res["agents"], ["claude"])

    def test_installed_skill_renders_home_without_changing_bundle(self):
        source = (L.SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("{{AIDP_HOME}}", source)
        for agent, home, skill_dir in (
            ("claude", ".claude", ".claude/skills"),
            ("codex", ".agents", ".agents/skills"),
        ):
            with self.subTest(agent=agent), H.TempRepo() as root:
                scaffold(root, "--agent", agent)
                installed = (root / skill_dir / "aidp-code-engineer/SKILL.md").read_text(encoding="utf-8")
                self.assertNotIn("{{AIDP_HOME}}", installed)
                self.assertEqual(installed, source.replace("{{AIDP_HOME}}", home))
                bundled = (root / skill_dir / "aidp-code-engineer/assets/docs/init/README.md").read_text(
                    encoding="utf-8")
                self.assertIn("{{AIDP_HOME}}", bundled)

    def test_codex_and_dsh_share_native_runtime_and_nested_plugin_skills(self):
        with H.TempRepo() as root:
            env, _ = fake_dsh_env(root)
            scaffold(root, "--version", "V0.1.0", "--agent", "codex,dsh", env=env)
            self._assert_absent(root / ".aidp")
            self.assertTrue((root / ".agents/scripts/agent_sync.py").is_file())
            self.assertTrue((root / ".agents/commands/sprint-dev.md").is_file())
            self.assertTrue((root / ".agents/skills/bugfix/SKILL.md").is_file())
            self.assertTrue((root / ".agents/plugins/chrome-devtools-mcp/.claude-plugin/plugin.json").is_file())
            self.assertTrue((root / ".agents/skills/aidp-code-engineer/SKILL.md").is_file())
            self.assertTrue((root / ".agents/skills/bugfix/SKILL.md").is_file())
            self.assertTrue((root / ".codex/skills/aidp/sprint-dev/SKILL.md").is_file())
            codex_skill = (root / ".codex/skills/aidp/sprint-test/SKILL.md").read_text(encoding="utf-8")
            marker = "## 原始命令正文（逐字保真）\n\n"
            self.assertIn(marker, codex_skill)
            self._assert_target_runtime_paths(codex_skill.split(marker, 1)[1], ".agents")
            self.assertTrue((root / ".dsh/commands/sprint-dev.md").is_file())
            dsh_command = (root / ".dsh/commands/sprint-test.md").read_text(encoding="utf-8")
            self._assert_target_runtime_paths(dsh_command, ".agents")
            self.assertTrue((root / ".agents/skills/chrome-devtools-mcp/skills/chrome-devtools/SKILL.md").is_file())
            self._assert_absent(root / ".codex/skills/chrome-devtools-mcp")
            self._assert_tree_equal(
                root / ".agents/skills/chrome-devtools-mcp/skills",
                root / ".agents/plugins/chrome-devtools-mcp/skills",
            )
            self.assertEqual(len(list(root.glob(".agents/.aidp-runtime.json"))), 1)
            self._assert_roots_absent(
                root, ".claude", ".claude/commands", ".claude/skills", ".claude/plugins",
            )
            self._assert_fully_materialized(
                root, ".agents", ".agents/skills", ".codex/skills/aidp", ".dsh/commands",
            )
            self._assert_runtime_contract(root, Path(".agents"))
            manifest = self._manifest(root, Path(".agents"))
            self.assertEqual(manifest["source"], "shared")

    def test_codex_only_uses_one_shared_runtime(self):
        with H.TempRepo() as root:
            scaffold(root, "--version", "V0.1.0", "--agent", "codex")
            self._assert_absent(root / ".aidp")
            self.assertTrue((root / ".agents/.aidp-runtime.json").is_file())
            self._assert_roots_absent(
                root, ".claude", ".claude/commands", ".claude/skills", ".claude/plugins",
                ".dsh/commands",
            )
            self.assertTrue((root / ".codex/skills/aidp/sprint-dev/SKILL.md").is_file())
            codex_skill = (root / ".codex/skills/aidp/sprint-test/SKILL.md").read_text(encoding="utf-8")
            marker = "## 原始命令正文（逐字保真）\n\n"
            self.assertIn(marker, codex_skill)
            self._assert_target_runtime_paths(codex_skill.split(marker, 1)[1], ".agents")
            self._assert_absent(root / ".dsh/commands")
            self.assertTrue((root / ".agents/skills/chrome-devtools-mcp/skills/chrome-devtools/SKILL.md").is_file())
            self._assert_absent(root / ".codex/skills/chrome-devtools-mcp")
            self._assert_tree_equal(
                root / ".agents/skills/chrome-devtools-mcp/skills",
                root / ".agents/plugins/chrome-devtools-mcp/skills",
            )
            self._assert_fully_materialized(
                root, ".agents", ".agents/skills", ".codex/skills/aidp",
            )
            self._assert_runtime_contract(root, Path(".agents"))

    def test_dsh_only_uses_one_shared_runtime(self):
        with H.TempRepo() as root:
            env, _ = fake_dsh_env(root)
            scaffold(root, "--version", "V0.1.0", "--agent", "dsh", env=env)
            self._assert_absent(root / ".aidp")
            self.assertTrue((root / ".agents/.aidp-runtime.json").is_file())
            self._assert_roots_absent(
                root, ".claude", ".claude/commands", ".claude/skills", ".claude/plugins",
                ".codex/skills/aidp",
            )
            self.assertTrue((root / ".dsh/commands/sprint-dev.md").is_file())
            dsh_command = (root / ".dsh/commands/sprint-test.md").read_text(encoding="utf-8")
            self._assert_target_runtime_paths(dsh_command, ".agents")
            self._assert_absent(root / ".codex/skills/aidp")
            self._assert_absent(root / ".codex/skills/chrome-devtools-mcp")
            self.assertTrue((root / ".agents/skills/chrome-devtools-mcp/skills/chrome-devtools/SKILL.md").is_file())
            self._assert_tree_equal(
                root / ".agents/skills/chrome-devtools-mcp/skills",
                root / ".agents/plugins/chrome-devtools-mcp/skills",
            )
            self._assert_fully_materialized(
                root, ".agents", ".agents/skills", ".dsh/commands",
            )
            self._assert_runtime_contract(root, Path(".agents"))

    def test_dangling_legacy_root_symlink_is_cleaned_before_init(self):
        with H.TempRepo() as root:
            legacy = root / ".aidp"
            legacy.symlink_to(root / "missing-legacy-runtime", target_is_directory=True)
            scaffold(root, "--version", "V0.1.0", "--agent", "claude")
            self._assert_absent(legacy)
            self.assertTrue((root / ".claude/.aidp-runtime.json").is_file())

    def test_all_agents_render_equivalent_runtime_packages(self):
        with H.TempRepo() as root:
            env, _ = fake_dsh_env(root)
            scaffold(root, "--version", "V0.1.0", "--agent", "claude,codex,dsh", env=env)
            claude_rel = Path(".claude")
            shared_rel = Path(".agents")
            self._assert_runtime_contract(root, claude_rel)
            self._assert_runtime_contract(root, shared_rel)
            self._assert_fully_materialized(
                root,
                ".claude", ".claude/commands", ".claude/skills", ".claude/plugins",
                ".agents", ".agents/skills", ".codex/skills/aidp", ".dsh/commands",
            )
            self._assert_absent(root / ".codex/skills/chrome-devtools-mcp")
            self._assert_tree_equal(
                root / ".agents/skills/chrome-devtools-mcp/skills",
                root / ".agents/plugins/chrome-devtools-mcp/skills",
            )
            self.assertTrue((root / claude_rel / ".aidp-runtime.json").is_file())
            self.assertTrue((root / shared_rel / ".aidp-runtime.json").is_file())
            for family, skill_dir in ((".claude", ".claude/skills"),
                                      (".agents", ".agents/skills")):
                text = (root / skill_dir / "aidp-code-engineer/SKILL.md").read_text(encoding="utf-8")
                self.assertNotIn("{{AIDP_HOME}}", text)
                self.assertIn(family + "/reference/agent-tools.md", text)
            claude = self._manifest(root, claude_rel)
            shared = self._manifest(root, shared_rel)
            self.assertEqual(claude["version"], shared["version"])
            claude_command = (root / ".claude/commands/sprint-test.md").read_text(encoding="utf-8")
            shared_command = (root / ".dsh/commands/sprint-test.md").read_text(encoding="utf-8")
            self._assert_target_runtime_paths(claude_command, ".claude")
            self.assertNotIn(".agents/", claude_command)
            self._assert_target_runtime_paths(shared_command, ".agents")
            self.assertNotIn(".claude/", shared_command)
            rc, output = agent_sync_check(root)
            self.assertEqual(rc, 0, output)
            self.assertEqual(set(claude["files"]), set(shared["files"]))
            # ★ 双包一致性按**真源**判，不按"各自反解回 token 再比"：运行根降层后运行根
            #   字符串与 Agent 自有路径同名，契约正文里的字面量无法与渲染产物区分（结构性
            #   不可判定，见 runtime_layout._restore_home_token）。
            self.assertTrue(runtime_layout.packages_share_one_source(
                [(root / claude_rel, claude_rel.as_posix()),
                 (root / shared_rel, shared_rel.as_posix())],
                _runtime_source_for(root)), "双包与真源不一致")

    def test_link_mode_is_normalized_to_managed_copy(self):
        with H.TempRepo() as root:
            env, _ = fake_dsh_env(root)
            res = scaffold(
                root, "--version", "V0.1.0", "--agent", "claude,codex,dsh",
                "--adapter-mode", "link", env=env,
            )
            generated = (
                root / ".claude",
                root / ".claude/commands/sprint-dev.md",
                root / ".claude/skills/bugfix",
                root / ".claude/plugins/chrome-devtools-mcp",
                root / ".agents",
                root / ".agents/skills/aidp-code-engineer",
                root / ".agents/skills/bugfix",
                root / ".agents/skills/chrome-devtools-mcp",
                root / ".codex/skills/aidp/sprint-dev",
                root / ".dsh/commands/sprint-dev.md",
            )
            self.assertTrue(all(path.exists() and not path.is_symlink() for path in generated))
            self._assert_fully_materialized(
                root,
                ".claude", ".claude/commands", ".claude/skills", ".claude/plugins",
                ".agents", ".agents/skills", ".codex/skills/aidp", ".dsh/commands",
            )
            self._assert_absent(root / ".codex/skills/chrome-devtools-mcp")
            self._assert_tree_equal(
                root / ".agents/skills/chrome-devtools-mcp/skills",
                root / ".agents/plugins/chrome-devtools-mcp/skills",
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
            self.assertTrue((root / ".claude/.aidp-runtime.json").is_file())
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
            self.assertTrue((root / ".claude/.aidp-runtime.json").is_file())


class NativeIdempotencyTest(unittest.TestCase):
    def test_same_version_second_run_keeps_runtime_and_entries(self):
        with H.TempRepo() as root:
            first = scaffold(root, "--agent", "claude")
            before = (root / ".claude/.aidp-runtime.json").read_bytes()
            again = scaffold(root)
            self.assertEqual(first["mode"], "init")
            self.assertEqual(again["mode"], "upgrade")
            self.assertEqual(again["contract_decision"], "fill")
            self.assertEqual((root / ".claude/.aidp-runtime.json").read_bytes(), before)
            self.assertFalse([action for action in again["actions"]
                              if action["op"] in {"create", "update", "backup", "install"}],
                             again["actions"])

    def test_dual_runtime_user_overlay_syncs_from_either_family(self):
        for origin in (".claude", ".agents"):
            with self.subTest(origin=origin), H.TempRepo() as root:
                scaffold(root, "--agent", "claude,codex")
                other = ".agents" if origin == ".claude" else ".claude"
                private = root / origin / "reference/team-only.md"
                private.write_text(f"see {origin}/reference\n", encoding="utf-8")
                result = scaffold(root)
                self.assertEqual(result["mode"], "upgrade")
                self.assertEqual((root / other / "reference/team-only.md").read_text(encoding="utf-8"),
                                 f"see {other}/reference\n")
                self.assertTrue(runtime_layout.packages_share_one_source(
                    [(root / origin, origin), (root / other, other)], _runtime_source_for(root)),
                    "双包与真源不一致")
                for home in (origin, other):
                    manifest = runtime_layout.validate_runtime(root / home, expected_home=home)
                    self.assertIn("reference/team-only.md", manifest["user_files"])
                again = scaffold(root)
                self.assertFalse([action for action in again["actions"] if action["op"] == "install"
                                  and action["path"] in {origin + "/", other + "/"}],
                                 again["actions"])

    def test_dual_runtime_filled_reference_syncs_from_either_family(self):
        for origin in (".claude", ".agents"):
            with self.subTest(origin=origin), H.TempRepo() as root:
                scaffold(root, "--agent", "claude,codex")
                other = ".agents" if origin == ".claude" else ".claude"
                relative = "reference/子Agent必读.md"
                (root / origin / relative).write_text("# 已填写\n团队要求\n", encoding="utf-8")
                scaffold(root)
                self.assertEqual((root / other / relative).read_text(encoding="utf-8"),
                                 "# 已填写\n团队要求\n")
                self.assertTrue(runtime_layout.packages_share_one_source(
                    [(root / origin, origin), (root / other, other)], _runtime_source_for(root)),
                    "双包与真源不一致")

    def test_dual_runtime_conflicting_user_files_leave_both_unchanged(self):
        with H.TempRepo() as root:
            scaffold(root, "--agent", "claude,codex")
            for home, text in ((".claude", "Claude private\n"),
                               (".agents", "Shared private\n")):
                (root / home / "reference/team-only.md").write_text(text, encoding="utf-8")
            before = {home: runtime_layout.tree_digest(root / home)
                      for home in (".claude", ".agents")}
            with self.assertRaisesRegex(RuntimeError, "双包用户文件冲突"):
                S.run(root, LegacyRuntimeMigrationTest._options("upgrade", "claude,codex"))
            self.assertEqual({home: runtime_layout.tree_digest(root / home) for home in before}, before)


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
            assert_no_runtime(self, root, ".claude")

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
            # 用户自己的 `commands/sprint-dev.md` 正是本用例要保住的东西，不算残留。
            assert_no_runtime(self, root, ".claude", allow={"sprint-dev.md"})
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
            assert_no_runtime(self, root, ".claude")
            self.assertFalse(os.path.lexists(root / "memory"))

    def test_new_agent_collision_preserves_existing_runtime(self):
        with H.TempRepo() as root:
            scaffold(root, "--agent", "claude", "--user", "alice")
            manifest = root / ".claude/.aidp-runtime.json"
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
            assert_no_runtime(self, root, ".agents")

    def test_install_failure_restores_existing_project_tree(self):
        with H.TempRepo() as root:
            user_file = root / "docs/private/notes.md"
            user_file.parent.mkdir(parents=True)
            user_file.write_text("keep\n", encoding="utf-8")

            def snapshot():
                return {p.relative_to(root).as_posix():
                        ("link", os.readlink(p)) if p.is_symlink() else
                        ("dir", None) if p.is_dir() else ("file", p.read_bytes())
                        for p in root.rglob("*")
                        if ".git" not in p.relative_to(root).parts
                        # 运行包互斥锁是**本机运行态**：按设计在释放后保留供下次复用，
                        # 不属于"项目树被改动"。运行根降层后它落在项目根，必须显式排除，
                        # 否则每条回滚断言都会因为它判红。
                        and p.name != runtime_layout.RUNTIME_LOCK}

            before = snapshot()
            options = Namespace(mode="auto", agent="claude", user="alice", json=True,
                                version="V0.1.0", name_cn=None, force=False,
                                adapter_mode="copy", no_agent_sync=False,
                                keep_backups=5, keep_days=30)
            with mock.patch.object(S, "_install_native_skill", side_effect=OSError("injected failure")):
                with self.assertRaises(OSError):
                    S.run(root, options)
            self.assertEqual(snapshot(), before)

    def test_business_directory_symlink_rejected_before_writes(self):
        for dirname in ("memory", "docs", "docs/init", "docs/custom"):
            with self.subTest(dirname=dirname), H.TempRepo() as root, tempfile.TemporaryDirectory() as external:
                target = Path(external)
                sentinel = target / "sentinel.txt"
                sentinel.write_text("keep\n", encoding="utf-8")
                (root / dirname).parent.mkdir(parents=True, exist_ok=True)
                (root / dirname).symlink_to(target, target_is_directory=True)
                options = Namespace(mode="auto", agent="claude", user="alice", json=True,
                                    version="V0.1.0", name_cn=None, force=False,
                                    adapter_mode="copy", no_agent_sync=False,
                                    keep_backups=5, keep_days=30)
                with self.assertRaisesRegex(ValueError, "symlink"):
                    S.run(root, options)
                self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep\n")
                self.assertEqual(sorted(p.name for p in target.iterdir()), ["sentinel.txt"])
                assert_no_runtime(self, root, ".claude")

    def test_rollback_preserves_unrelated_concurrent_file(self):
        with H.TempRepo() as root:
            options = Namespace(mode="auto", agent="claude", user="alice", json=True,
                                version="V0.1.0", name_cn=None, force=False,
                                adapter_mode="copy", no_agent_sync=False,
                                keep_backups=5, keep_days=30)
            concurrent = root / "concurrent-user-file.txt"

            def fail_after_user_write(*_args, **_kwargs):
                concurrent.write_text("keep\n", encoding="utf-8")
                raise OSError("injected failure")

            with mock.patch.object(S, "_install_native_skill", side_effect=fail_after_user_write):
                with self.assertRaisesRegex(OSError, "injected failure"):
                    S.run(root, options)
            self.assertEqual(concurrent.read_text(encoding="utf-8"), "keep\n")
            assert_no_runtime(self, root, ".claude", allow={"concurrent-user-file.txt"})

    def test_rollback_preserves_concurrent_file_in_existing_docs(self):
        with H.TempRepo() as root:
            (root / "docs").mkdir()
            options = Namespace(mode="auto", agent="claude", user="alice", json=True,
                                version="V0.1.0", name_cn=None, force=False,
                                adapter_mode="copy", no_agent_sync=False,
                                keep_backups=5, keep_days=30)
            concurrent = root / "docs/concurrent-user-file.txt"

            def fail_after_user_write(*_args, **_kwargs):
                concurrent.write_text("keep\n", encoding="utf-8")
                raise OSError("injected failure")

            with mock.patch.object(S, "_install_native_skill", side_effect=fail_after_user_write):
                with self.assertRaisesRegex(OSError, "injected failure"):
                    S.run(root, options)
            self.assertEqual(concurrent.read_text(encoding="utf-8"), "keep\n")
            assert_no_runtime(self, root, ".claude", allow={"concurrent-user-file.txt"})

    def test_rollback_preserves_concurrent_skill_file(self):
        with H.TempRepo() as root:
            skills = root / ".claude/skills"
            skills.mkdir(parents=True)
            concurrent = skills / "concurrent-user-file.txt"
            options = Namespace(mode="auto", agent="claude", user="alice", json=True,
                                version="V0.1.0", name_cn=None, force=False,
                                adapter_mode="copy", no_agent_sync=False,
                                keep_backups=5, keep_days=30)

            def fail_after_user_write(*_args, **_kwargs):
                concurrent.write_text("keep\n", encoding="utf-8")
                raise OSError("injected failure")

            with mock.patch.object(S, "_install_native_skill", side_effect=fail_after_user_write):
                with self.assertRaisesRegex(OSError, "injected failure"):
                    S.run(root, options)
            self.assertEqual(concurrent.read_text(encoding="utf-8"), "keep\n")
            assert_no_runtime(self, root, ".claude", allow={"concurrent-user-file.txt"})

    def test_rollback_preserves_concurrent_private_readme(self):
        with H.TempRepo() as root:
            private = root / "docs/private"
            private.mkdir(parents=True)
            concurrent = private / "README.md"
            options = Namespace(mode="auto", agent="claude", user="alice", json=True,
                                version="V0.1.0", name_cn=None, force=False,
                                adapter_mode="copy", no_agent_sync=False,
                                keep_backups=5, keep_days=30)

            def fail_after_user_write(*_args, **_kwargs):
                concurrent.write_text("keep\n", encoding="utf-8")
                raise OSError("injected failure")

            with mock.patch.object(S, "_install_native_skill", side_effect=fail_after_user_write):
                with self.assertRaisesRegex(OSError, "injected failure"):
                    S.run(root, options)
            self.assertEqual(concurrent.read_text(encoding="utf-8"), "keep\n")
            assert_no_runtime(self, root, ".claude", allow={"concurrent-user-file.txt"})

    def test_rollback_preserves_user_file_added_during_successful_skill_stage(self):
        with H.TempRepo() as root:
            (root / ".claude/skills").mkdir(parents=True)
            concurrent = root / ".claude/skills/concurrent-user-file.txt"
            options = Namespace(mode="auto", agent="claude", user="alice", json=True,
                                version="V0.1.0", name_cn=None, force=False,
                                adapter_mode="copy", no_agent_sync=False,
                                keep_backups=5, keep_days=30)
            install = S._install_native_skill

            def install_with_user_write(*args, **kwargs):
                concurrent.write_text("keep\n", encoding="utf-8")
                return install(*args, **kwargs)

            with mock.patch.object(S, "_install_native_skill", side_effect=install_with_user_write), \
                    mock.patch.object(S, "run_agent_sync", side_effect=OSError("injected failure")):
                with self.assertRaisesRegex(OSError, "injected failure"):
                    S.run(root, options)
            self.assertEqual(concurrent.read_text(encoding="utf-8"), "keep\n")
            assert_no_runtime(self, root, ".claude", allow={"concurrent-user-file.txt"})

    def test_rollback_preserves_user_readme_added_during_successful_docs_stage(self):
        with H.TempRepo() as root:
            (root / "docs/private").mkdir(parents=True)
            concurrent = root / "docs/private/README.md"
            options = Namespace(mode="auto", agent="claude", user="alice", json=True,
                                version="V0.1.0", name_cn=None, force=False,
                                adapter_mode="copy", no_agent_sync=False,
                                keep_backups=5, keep_days=30)
            sync = S.sync_docs

            def sync_with_user_write(*args, **kwargs):
                concurrent.write_text("keep\n", encoding="utf-8")
                return sync(*args, **kwargs)

            with mock.patch.object(S, "sync_docs", side_effect=sync_with_user_write), \
                    mock.patch.object(S, "_install_native_skill", side_effect=OSError("injected failure")):
                with self.assertRaisesRegex(OSError, "injected failure"):
                    S.run(root, options)
            self.assertEqual(concurrent.read_text(encoding="utf-8"), "keep\n")
            assert_no_runtime(self, root, ".claude", allow={"concurrent-user-file.txt"})

    def test_runtime_written_then_error_rolls_back_without_user_loss(self):
        with H.TempRepo() as root:
            options = Namespace(mode="auto", agent="claude", user="alice", json=True,
                                version="V0.1.0", name_cn=None, force=False,
                                adapter_mode="copy", no_agent_sync=False,
                                keep_backups=5, keep_days=30)
            concurrent = root / ".claude/concurrent-user-file.txt"
            render = S.runtime_layout.render_runtime

            def render_then_fail(*args, **kwargs):
                result = render(*args, **kwargs)
                concurrent.write_text("keep\n", encoding="utf-8")
                raise OSError("render interrupted")

            with mock.patch.object(S.runtime_layout, "render_runtime", side_effect=render_then_fail):
                with self.assertRaisesRegex(OSError, "render interrupted"):
                    S.run(root, options)
            self.assertEqual(concurrent.read_text(encoding="utf-8"), "keep\n")
            assert_no_runtime(self, root, ".claude", allow={"concurrent-user-file.txt"})

    def test_agent_entries_written_then_error_roll_back_without_user_loss(self):
        with H.TempRepo() as root:
            options = Namespace(mode="auto", agent="claude", user="alice", json=True,
                                version="V0.1.0", name_cn=None, force=False,
                                adapter_mode="copy", no_agent_sync=False,
                                keep_backups=5, keep_days=30)
            concurrent = root / ".claude/skills/concurrent-user-file.txt"
            sync = S.run_agent_sync

            def sync_then_fail(*args, **kwargs):
                sync(*args, **kwargs)
                concurrent.write_text("keep\n", encoding="utf-8")
                raise OSError("adapter interrupted")

            with mock.patch.object(S, "run_agent_sync", side_effect=sync_then_fail):
                with self.assertRaisesRegex(OSError, "adapter interrupted"):
                    S.run(root, options)
            self.assertEqual(concurrent.read_text(encoding="utf-8"), "keep\n")
            assert_no_runtime(self, root, ".claude", allow={"concurrent-user-file.txt"})
            self.assertFalse(os.path.lexists(root / ".claude/commands/sprint-dev.md"))

    def test_upgrade_failure_restores_runtime_and_user_document(self):
        with H.TempRepo() as root:
            scaffold(root, "--agent", "claude", "--user", "alice")
            document = root / "docs/private/notes.md"
            document.parent.mkdir(parents=True)
            document.write_text("keep\n", encoding="utf-8")
            runtime_manifest = root / ".claude/.aidp-runtime.json"
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
            manifest = runtime_layout.validate_runtime(root / ".claude",
                                                       expected_home=".claude")
            self.assertEqual(manifest["schema"], "aidp.runtime/v1")
            cache = root / ".claude/scripts/__pycache__"
            if cache.exists():
                shutil.rmtree(cache)
            cache.symlink_to(root / "memory", target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlink"):
                runtime_layout.validate_runtime(root / ".claude",
                                                expected_home=".claude")


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
            self.assertEqual(dsh_add_calls(log), [" ".join(self.COMMAND)])
            # ★ add 之后必须再 list 一次复查，否则「返回 0 但其实没装上」会被当成可用
            self.assertGreaterEqual(len([c for c in dsh_calls(log) if "list" in c]), 2, dsh_calls(log))
            self.assertEqual(res["dsh_extensions"], "installed")
            self.assertIn(res["dsh_extensions"], S.DSH_STATE_READY)
            self.assertFalse([w for w in res["warnings"] if "dsh-agent-extension" in w], res["warnings"])
            ops = [a["op"] for a in res["actions"]]
            self.assertEqual(ops.count("dsh-plugin"), 1, ops)
            self.assertLess(ops.index("dsh-plugin"), ops.index("agent-sync"), ops)

    def test_already_installed_skips_add(self):
        """⛔ 已装就不该再 add：那是一次多余的写动作，也是下游误报的源头。"""
        with H.TempRepo() as root:
            env, log = fake_dsh_env(root, preinstalled=True)
            res = scaffold(root, "--version", "V0.1.0", "--agent", "dsh", env=env)
            self.assertEqual(res["dsh_extensions"], "already-installed")
            self.assertEqual(dsh_add_calls(log), [], dsh_calls(log))
            self.assertFalse([w for w in res["warnings"] if "dsh" in w.lower()], res["warnings"])
            self.assertFalse(any(a["op"] == "dsh-plugin" for a in res["actions"]), res["actions"])

    def test_add_succeeds_but_recheck_misses_is_not_available(self):
        with H.TempRepo() as root:
            env, log = fake_dsh_env(root, add_effect="noop")
            res = scaffold(root, "--version", "V0.1.0", "--agent", "dsh", env=env)
            self.assertEqual(res["dsh_extensions"], "not-installed")
            self.assertNotIn(res["dsh_extensions"], S.DSH_STATE_READY)
            self.assertEqual(len(dsh_add_calls(log)), 1)
            self.assertIn("仍看不到", "\n".join(res["warnings"]))

    def test_nonzero_install_warns_and_scaffold_continues(self):
        with H.TempRepo() as root:
            env, log = fake_dsh_env(root, exit_code=7)
            res = scaffold(root, "--version", "V0.1.0", "--agent", "dsh", env=env)
            self.assertEqual(dsh_add_calls(log), [" ".join(self.COMMAND)])
            warning = "\n".join(res["warnings"])
            self.assertIn("DSH 命令插件安装失败", warning)
            self.assertIn("exit 7", warning)
            self.assertIn("plugin install failed", warning)
            self.assertIn(self.RETRY, warning)
            self.assertEqual(res["dsh_extensions"], "install-failed")
            self.assertTrue((root / ".agents").is_dir(), "插件安装失败不得回滚脚手架文件")
            self.assertTrue(any(a["op"] == "agent-sync" for a in res["actions"]), res["actions"])

    def test_missing_dsh_is_unverified_not_absent(self):
        """⛔ 「本进程定位不到 dsh」既不是「安装失败」也不是「未安装」，只是**未验证**。"""
        with H.TempRepo() as root:
            res = scaffold(root, "--version", "V0.1.0", "--agent", "dsh", env=missing_dsh_env(root))
            warning = "\n".join(res["warnings"])
            self.assertEqual(res["dsh_extensions"], "cli-unavailable")
            self.assertIn("未验证", warning)
            self.assertNotIn("未安装", warning)
            self.assertNotIn("安装失败", warning)
            self.assertIn("which(dsh)=", warning)
            self.assertIn(self.RETRY, warning)
            self.assertTrue((root / ".agents").is_dir())
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
                # 探测阶段照常放行：先 --version、再 list（清单为空 = 确实没装，才轮到 add）
                if tuple(cmd) == S.DSH_PLUGIN_VERSION:
                    return subprocess.CompletedProcess(cmd, 0, "0.1.5-rc.2\n", "")
                if tuple(cmd) in (S.DSH_PLUGIN_LIST_JSON, S.DSH_PLUGIN_LIST):
                    return subprocess.CompletedProcess(cmd, 0, "NAME  VERSION\n", "")
                return real_run(cmd, *args, **kwargs)

            options = Namespace(
                mode="auto", agent="dsh", json=True, user=None, name_cn=None,
                version="V0.1.0", force=False, keep_backups=L.PRUNE_KEEP_LAST_DEFAULT,
                keep_days=L.PRUNE_KEEP_DAYS_DEFAULT, no_agent_sync=False, adapter_mode="link")
            with mock.patch.object(S.subprocess, "run", side_effect=run_with_timeout), \
                 mock.patch.object(S.shutil, "which",
                                   side_effect=lambda name: "/usr/bin/dsh" if name == "dsh"
                                   else shutil.which(name)):
                res = S.run(root, options)

            self.assertIs(install_kwargs["stdin"], subprocess.DEVNULL)
            self.assertEqual(install_kwargs["timeout"], 120)
            self.assertEqual(res["dsh_extensions"], "install-failed")
            warning = "\n".join(res["warnings"])
            self.assertIn("超时 120 秒", warning)
            self.assertIn("plugin timed out still running", warning)
            self.assertIn(self.RETRY, warning)
            self.assertTrue(any(a["op"] == "agent-sync" for a in res["actions"]), res["actions"])

    def test_nonzero_detail_is_single_line_and_bounded(self):
        with H.TempRepo() as root:
            env, _ = fake_dsh_env(root, exit_code=9)
            env["DSH_TEST_MESSAGE"] = "first line " + ("x" * 600) + " last line"
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
            self.assertEqual(dsh_add_calls(log), [" ".join(self.COMMAND)])
            self.assertEqual(res["dsh_extensions"], "installed")

        with H.TempRepo() as root:
            scaffold(root, "--version", "V0.1.0", "--agent", "claude")
            (root / ".dsh").mkdir(exist_ok=True)
            env, log = fake_dsh_env(root)
            res = scaffold(root, env=env)
            self.assertEqual(res["mode"], "upgrade")
            self.assertIn("dsh", res["agents"])
            self.assertEqual(dsh_add_calls(log), [" ".join(self.COMMAND)])
            self.assertEqual(res["dsh_extensions"], "installed")


class LegacyRuntimeMigrationTest(unittest.TestCase):
    @staticmethod
    def _legacy(root):
        command = root / ".aidp/commands/sprint-dev.md"
        command.parent.mkdir(parents=True)
        command.write_text("旧命令正文\n", encoding="utf-8")
        extra = root / ".aidp/reference/team-notes.md"
        extra.parent.mkdir(parents=True)
        extra.write_text("团队自定义内容\n", encoding="utf-8")
        scaffold_marker.write_version(root, BUNDLE_VERSION)
        return command, extra

    def test_same_version_migrate_backs_up_modified_legacy_tree(self):
        with H.TempRepo() as root:
            self._legacy(root)
            result = scaffold(root, "--mode", "migrate", "--agent", "claude,codex")
            self.assertFalse(os.path.lexists(root / ".aidp"))
            self.assertTrue((root / ".claude/commands/sprint-dev.md").is_file())
            self.assertTrue((root / ".agents/commands/sprint-dev.md").is_file())
            self.assertEqual((root / result["backup"] / ".aidp/commands/sprint-dev.md").read_text(),
                             "旧命令正文\n")
            self.assertEqual((root / result["backup"] / ".aidp/reference/team-notes.md").read_text(),
                             "团队自定义内容\n")
            entries = {item["source"]: item for item in result["legacy_backup_files"]}
            for rel in ("commands/sprint-dev.md", "reference/team-notes.md"):
                self.assertEqual(entries[rel]["backup"], f"{result['backup']}/.aidp/{rel}")
                self.assertEqual(entries[rel]["classification"], "unclassified")
            self.assertTrue(any("reference/team-notes.md" in note for note in result["notes"]))
            self.assertEqual(scaffold_marker.read_version(root), BUNDLE_VERSION)
            self.assertEqual(agent_sync_check(root)[0], 0)

    def test_legacy_backup_classifies_changes_with_old_manifest(self):
        with H.TempRepo() as root:
            self._legacy(root)
            manifest = root / ".aidp/skills/aidp-code-engineer/assets/CONTRACT_MANIFEST.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(json.dumps({"files": {
                "commands/sprint-dev.md": L.sha256("旧版受管正文\n".encode("utf-8"))
            }}), encoding="utf-8")
            result = scaffold(root, "--mode", "migrate", "--agent", "claude")
            entries = {item["source"]: item for item in result["legacy_backup_files"]}
            self.assertEqual(entries["commands/sprint-dev.md"]["classification"], "modified")
            self.assertEqual(entries["reference/team-notes.md"]["classification"], "added")
            for rel in ("commands/sprint-dev.md", "reference/team-notes.md"):
                self.assertTrue((root / entries[rel]["backup"]).is_file())

    def test_legacy_manifest_does_not_classify_scripts_as_user_added(self):
        with H.TempRepo() as root:
            self._legacy(root)
            script = root / ".aidp/scripts/baseline_edit.py"
            script.parent.mkdir(parents=True)
            script.write_text("# Generated script\n", encoding="utf-8")
            manifest = root / ".aidp/skills/aidp-code-engineer/assets/CONTRACT_MANIFEST.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(json.dumps({"files": {
                "commands/sprint-dev.md": L.sha256("旧命令正文\n".encode("utf-8"))
            }}), encoding="utf-8")
            result = scaffold(root, "--mode", "migrate", "--agent", "claude")
            entries = {item["source"]: item for item in result["legacy_backup_files"]}
            self.assertEqual(entries["scripts/baseline_edit.py"]["classification"], "unclassified")
            self.assertEqual(entries["reference/team-notes.md"]["classification"], "added")
            self.assertNotIn("commands/sprint-dev.md", entries)
            self.assertEqual((root / entries["scripts/baseline_edit.py"]["backup"]).read_bytes(),
                             b"# Generated script\n")

    def test_legacy_change_after_backup_is_not_lost(self):
        with H.TempRepo() as root:
            command, extra = self._legacy(root)
            real_run = S.subprocess.run
            changed = False

            def modify_after_check(args, *positional, **kwargs):
                nonlocal changed
                result = real_run(args, *positional, **kwargs)
                if (not changed and isinstance(args, list) and "--check" in args
                        and any("agent_sync.py" in str(arg) for arg in args)):
                    command.write_text("备份后的新修改\n", encoding="utf-8")
                    changed = True
                return result

            with mock.patch.object(S.subprocess, "run", side_effect=modify_after_check):
                with self.assertRaisesRegex(RuntimeError, "备份后发生变化"):
                    S.run(root, self._options("migrate", "claude"))
            self.assertTrue(changed)
            self.assertEqual(command.read_text(encoding="utf-8"), "备份后的新修改\n")
            self.assertEqual(extra.read_text(encoding="utf-8"), "团队自定义内容\n")
            assert_no_runtime(self, root, ".claude")

    def test_failed_migration_with_verified_backup_is_warned_and_success_clears_record(self):
        with H.TempRepo() as root:
            scaffold(root, "--agent", "claude", "--user", "alice")
            self._legacy(root)
            options = self._options("migrate", "claude")
            options.force = True
            with mock.patch.object(S.runtime_layout, "render_runtime", side_effect=RuntimeError("probe")):
                with self.assertRaisesRegex(RuntimeError, "probe"):
                    S.run(root, options)
            record = root / ".aidp-migration-failure.json"
            self.assertTrue(record.is_file())
            evidence = json.loads(record.read_text(encoding="utf-8"))
            self.assertEqual(evidence["status"], "failed")
            self.assertTrue((root / evidence["backup_path"]).is_dir())
            result = V.VerifyResult()
            V.check_native_runtime(root, result)
            self.assertFalse(any("旧运行目录 .aidp/" in error for error in result.errors))
            self.assertTrue(any("旧运行目录 .aidp/" in warning for warning in result.warnings))
            S.run(root, self._options("migrate", "claude"))
            self.assertFalse(os.path.lexists(root / ".aidp"))
            self.assertFalse(os.path.lexists(record))

    def test_legacy_only_failure_record_is_visible_to_verify(self):
        with H.TempRepo() as root:
            self._legacy(root)
            with mock.patch.object(S.runtime_layout, "render_runtime", side_effect=RuntimeError("probe")):
                with self.assertRaisesRegex(RuntimeError, "probe"):
                    S.run(root, self._options("migrate", "claude"))
            assert_no_runtime(self, root, ".claude")
            _rc, _errors, output = H.verify(root)
            self.assertIn("迁移失败保留", output)
            self.assertIn("完整备份", output)

    def test_failed_migration_record_requires_matching_safe_backup(self):
        with H.TempRepo() as root:
            scaffold(root, "--agent", "claude", "--user", "alice")
            self._legacy(root)
            options = self._options("migrate", "claude")
            options.force = True
            with mock.patch.object(S.runtime_layout, "render_runtime", side_effect=RuntimeError("probe")):
                with self.assertRaisesRegex(RuntimeError, "probe"):
                    S.run(root, options)
            record = root / ".aidp-migration-failure.json"
            original = record.read_text(encoding="utf-8")
            for change in ({"backup_path": "../outside"}, {"legacy_digest": "0" * 64},
                           {"version": "V99.0.0"}):
                evidence = json.loads(original)
                evidence.update(change)
                record.write_text(json.dumps(evidence), encoding="utf-8")
                result = V.VerifyResult()
                V.check_native_runtime(root, result)
                self.assertTrue(any("旧运行目录 .aidp/" in error for error in result.errors), change)
            record.write_text(original, encoding="utf-8")
            backup = root / json.loads(original)["backup_path"]
            (backup / "commands/sprint-dev.md").write_text("tampered\n", encoding="utf-8")
            result = V.VerifyResult()
            V.check_native_runtime(root, result)
            self.assertTrue(any("旧运行目录 .aidp/" in error for error in result.errors))

    def test_nonregular_legacy_file_invalidates_failure_evidence(self):
        if not hasattr(os, "mkfifo"):
            self.skipTest("此平台不支持 FIFO")
        with H.TempRepo() as root:
            scaffold(root, "--agent", "claude", "--user", "alice")
            self._legacy(root)
            options = self._options("migrate", "claude")
            options.force = True
            with mock.patch.object(S.runtime_layout, "render_runtime", side_effect=RuntimeError("probe")):
                with self.assertRaisesRegex(RuntimeError, "probe"):
                    S.run(root, options)
            self.assertTrue((root / ".aidp-migration-failure.json").is_file())
            os.mkfifo(root / ".aidp/unsafe-pipe")
            result = V.VerifyResult()
            V.check_native_runtime(root, result)
            self.assertTrue(any("旧运行目录 .aidp/" in error for error in result.errors))
            self.assertFalse(any("旧运行目录 .aidp/" in warning for warning in result.warnings))

    def test_unowned_failure_record_is_not_replaced(self):
        with H.TempRepo() as root:
            self._legacy(root)
            record = root / ".aidp-migration-failure.json"
            record.write_text("user note\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "失败台账"):
                S.run(root, self._options("migrate", "claude"))
            self.assertEqual(record.read_text(encoding="utf-8"), "user note\n")
            assert_no_runtime(self, root, ".claude")

    def test_migration_backup_failure_cannot_claim_verified_warning(self):
        with H.TempRepo() as root:
            scaffold(root, "--agent", "claude", "--user", "alice")
            self._legacy(root)
            with mock.patch.object(S.Backup, "save_tree", return_value=None):
                result = S.run(root, self._options("migrate", "claude"))
            self.assertEqual(result["reason"], "legacy-backup-failed")
            self.assertFalse(os.path.lexists(root / ".aidp-migration-failure.json"))
            check = V.VerifyResult()
            V.check_native_runtime(root, check)
            self.assertTrue(any("旧运行目录 .aidp/" in error for error in check.errors))

    def test_legacy_remains_when_agent_entries_are_disabled(self):
        with H.TempRepo() as root:
            self._legacy(root)
            options = self._options("migrate", "claude")
            options.no_agent_sync = True
            result = S.run(root, options)
            self.assertEqual(result["status"], "blocked")
            self.assertTrue((root / ".aidp/commands/sprint-dev.md").is_file())
            assert_no_runtime(self, root, ".claude")
            command = H.run_script("scaffold.py", root, "--mode", "migrate", "--agent", "claude",
                                   "--user", "alice", "--no-agent-sync", "--json", check=False)
            self.assertEqual(command.returncode, 3)
            self.assertEqual(json.loads(command.stdout)["reason"], "agent-sync-disabled")

    def test_non_git_migrate_does_not_initialize_git(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "project"
            root.mkdir()
            self._legacy(root)
            result = scaffold(root, "--mode", "migrate", "--agent", "dsh", "--user", "alice",
                              env=missing_dsh_env(root))
            self.assertEqual(result["vcs_mode"], "none")
            self.assertFalse((root / ".git").exists())
            self.assertFalse(os.path.lexists(root / ".aidp"))
            self.assertTrue((root / ".agents/scripts/agent_sync.py").is_file())
            self.assertEqual(result["dsh_extensions"], "cli-unavailable")

    def test_non_git_native_upgrade_without_git_binary(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "project"
            root.mkdir()
            env = H.clean_env()
            env["PATH"] = str(root / "missing-bin")
            initial = scaffold(root, "--agent", "claude", "--user", "alice", env=env)
            self.assertEqual(initial["vcs_mode"], "none")
            scaffold_marker.write_version(root, "V0.0.1")
            result = scaffold(root, "--mode", "upgrade", "--user", "alice", env=env)
            self.assertEqual(result["vcs_mode"], "none")
            self.assertEqual(result["contract_decision"], "overwrite")
            self.assertFalse((root / ".git").exists())
            self.assertTrue((root / ".claude/.aidp-runtime.json").is_file())

    def test_backup_failure_preserves_legacy_without_native_runtime(self):
        with H.TempRepo() as root:
            command, extra = self._legacy(root)
            with mock.patch.object(S.Backup, "save_tree", side_effect=OSError("backup unavailable")):
                result = S.run(root, self._options("migrate", "claude"))
            self.assertEqual(command.read_text(), "旧命令正文\n")
            self.assertEqual(extra.read_text(), "团队自定义内容\n")
            assert_no_runtime(self, root, ".claude")
            self.assertTrue(any("backup unavailable" in warning for warning in result["warnings"]))

    def test_adapter_verification_failure_keeps_legacy_tree(self):
        with H.TempRepo() as root:
            command, extra = self._legacy(root)
            with mock.patch.object(S, "run_agent_sync", return_value={}):
                with self.assertRaises(RuntimeError):
                    S.run(root, self._options("migrate", "claude"))
            self.assertEqual(command.read_text(), "旧命令正文\n")
            self.assertEqual(extra.read_text(), "团队自定义内容\n")
            assert_no_runtime(self, root, ".claude")

    def test_second_runtime_failure_restores_legacy_and_project_files(self):
        with H.TempRepo() as root:
            command, extra = self._legacy(root)
            original_config = (root / "memory/aidp-config.yaml").read_bytes()
            render = S.runtime_layout.render_runtime
            calls = 0

            def fail_second(*args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("second runtime unavailable")
                return render(*args, **kwargs)

            with mock.patch.object(S.runtime_layout, "render_runtime", side_effect=fail_second):
                with self.assertRaises((OSError, RuntimeError)):
                    S.run(root, self._options("migrate", "claude,codex"))
            self.assertEqual(command.read_text(), "旧命令正文\n")
            self.assertEqual(extra.read_text(), "团队自定义内容\n")
            self.assertEqual((root / "memory/aidp-config.yaml").read_bytes(), original_config)
            assert_no_runtime(self, root, ".claude")
            assert_no_runtime(self, root, ".agents")

    def test_partial_legacy_removal_restores_deleted_user_file(self):
        with H.TempRepo() as root:
            command, extra = self._legacy(root)
            real_remove = S.shutil.rmtree

            def fail_after_partial_removal(path, *args, **kwargs):
                if Path(path) == root / ".aidp":
                    extra.unlink()
                    raise OSError("partial removal")
                return real_remove(path, *args, **kwargs)

            with mock.patch.object(S.shutil, "rmtree", side_effect=fail_after_partial_removal):
                with self.assertRaises(OSError):
                    S.run(root, self._options("migrate", "claude"))
            self.assertTrue(command.is_file())
            self.assertEqual(extra.read_text(), "团队自定义内容\n")
            assert_no_runtime(self, root, ".claude")

    def test_legacy_removal_failure_restores_everything(self):
        with H.TempRepo() as root:
            command, extra = self._legacy(root)
            original = (root / "memory/aidp-config.yaml").read_bytes()
            real_remove = S.shutil.rmtree

            def reject_legacy(path, *args, **kwargs):
                if Path(path) == root / ".aidp":
                    raise OSError("legacy removal failed")
                return real_remove(path, *args, **kwargs)

            with mock.patch.object(S.shutil, "rmtree", side_effect=reject_legacy):
                with self.assertRaises(OSError):
                    S.run(root, self._options("upgrade", "claude"))
            self.assertEqual(command.read_text(), "旧命令正文\n")
            self.assertEqual(extra.read_text(), "团队自定义内容\n")
            self.assertEqual((root / "memory/aidp-config.yaml").read_bytes(), original)
            assert_no_runtime(self, root, ".claude")

    def test_newer_native_scaffold_version_is_protected(self):
        with H.TempRepo() as root:
            scaffold(root, "--agent", "claude", "--user", "alice")
            scaffold_marker.write_version(root, "V99.0.0")
            original = (root / ".claude/commands/sprint-dev.md").read_bytes()
            skill = root / ".claude/skills/aidp-code-engineer/SKILL.md"
            skill.write_text("新版脚手架正文\n", encoding="utf-8")
            result = scaffold(root, "--mode", "upgrade", "--agent", "claude")
            self.assertEqual(result["contract_decision"], "protect")
            self.assertEqual(scaffold_marker.read_version(root), "V99.0.0")
            self.assertEqual((root / ".claude/commands/sprint-dev.md").read_bytes(), original)
            self.assertEqual(skill.read_text(), "新版脚手架正文\n")
            self.assertFalse(any(action["op"] == "install" for action in result["actions"]))

    def test_upgrade_backs_up_modified_native_runtime(self):
        with H.TempRepo() as root:
            scaffold(root, "--agent", "claude", "--user", "alice")
            command = root / ".claude/commands/sprint-dev.md"
            command.write_text("团队修改\n", encoding="utf-8")
            result = scaffold(root, "--mode", "upgrade", "--agent", "claude")
            self.assertNotEqual(command.read_text(), "团队修改\n")
            self.assertEqual((root / result["backup"] / ".claude/commands/sprint-dev.md").read_text(),
                             "团队修改\n")

    def test_agent_set_change_removes_only_unused_managed_runtime(self):
        with H.TempRepo() as root:
            scaffold(root, "--agent", "claude", "--user", "alice")
            self.assertTrue((root / ".claude").is_dir())
            result = scaffold(root, "--mode", "upgrade", "--agent", "codex")
            self.assertEqual(result["agents"], ["codex"])
            assert_no_runtime(self, root, ".claude")
            self.assertTrue((root / ".agents").is_dir())
            check = subprocess.run([sys.executable, str(root / ".agents/scripts/agent_sync.py"),
                                    "--root", str(root), "--agents", "codex", "--check"],
                                   capture_output=True, text=True)
            self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
            self.assertEqual(scaffold(root)["agents"], ["codex"],
                             "后续升级应以实际受管运行包发现 Agent，不因旧标记目录误启用 Claude")

    def test_upgrade_refreshes_managed_skill_and_preserves_user_edit(self):
        with H.TempRepo() as root:
            scaffold(root, "--agent", "claude", "--user", "alice")
            skill = root / ".claude/skills/aidp-code-engineer"
            custom = skill / "team-notes.txt"
            custom.write_text("团队修改\n", encoding="utf-8")
            (skill / "SKILL.md").write_text("旧脚手架正文\n", encoding="utf-8")
            result = scaffold(root, "--mode", "upgrade", "--agent", "claude")
            self.assertEqual((skill / "SKILL.md").read_text(encoding="utf-8"),
                             (L.SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
                             .replace("{{AIDP_HOME}}", ".claude"))
            self.assertTrue(result["backup"])
            backed_up = root / result["backup"] / ".claude/skills/aidp-code-engineer"
            self.assertEqual((backed_up / "team-notes.txt").read_text(), "团队修改\n")
            self.assertEqual((backed_up / "SKILL.md").read_text(), "旧脚手架正文\n")

    @staticmethod
    def _options(mode, agents):
        return Namespace(mode=mode, agent=agents, json=True, user="alice", name_cn=None,
                         version="V0.1.0", force=False, keep_backups=L.PRUNE_KEEP_LAST_DEFAULT,
                         keep_days=L.PRUNE_KEEP_DAYS_DEFAULT, no_agent_sync=False,
                         adapter_mode="copy")


class UpgradeTest(unittest.TestCase):
    def test_native_upgrade_keeps_project_content(self):
        with H.TempRepo() as root:
            scaffold(root, "--version", "V0.1.0", "--agent", "claude")
            custom = root / "docs/private/team.md"
            custom.parent.mkdir(parents=True)
            custom.write_text("团队规则\n", encoding="utf-8")
            scaffold_marker.write_version(root, "V0.0.1")
            result = scaffold(root, "--mode", "upgrade", "--agent", "claude")
            self.assertEqual(result["contract_decision"], "overwrite")
            self.assertEqual(custom.read_text(), "团队规则\n")
            self.assertFalse(os.path.lexists(root / ".aidp"))
            self.assertTrue((root / ".claude/.aidp-runtime.json").is_file())
            self.assertEqual(scaffold_marker.read_version(root), BUNDLE_VERSION)

    def test_newer_project_is_protected(self):
        with H.TempRepo() as root:
            scaffold(root, "--agent", "codex")
            scaffold_marker.write_version(root, "V99.0.0")
            skill = root / ".agents/skills/aidp-code-engineer/SKILL.md"
            skill.write_text("新版脚手架正文\n", encoding="utf-8")
            result = scaffold(root, "--mode", "upgrade", "--agent", "codex")
            self.assertEqual(result["contract_decision"], "protect")
            self.assertEqual(skill.read_text(), "新版脚手架正文\n")
            self.assertEqual(scaffold_marker.read_version(root), "V99.0.0")


class DeliveredFilesTest(unittest.TestCase):
    def test_new_root_readme_uses_installed_runtime_home(self):
        for agents, home in (("claude", ".claude"), ("codex", ".agents"),
                             ("claude,codex", ".agents")):
            with self.subTest(agents=agents), H.TempRepo() as root:
                scaffold(root, "--agent", agents)
                readme = (root / "README.md").read_text(encoding="utf-8")
                self.assertIn(f"python3 {home}/scripts/aidp_scheduler.py install", readme)
                self.assertIn(f"├── {home}/", readme)
                self.assertNotIn("python3 .aidp/scripts/aidp_scheduler.py", readme)
                self.assertNotIn("├── .aidp/", readme)
                self.assertNotIn("{{AIDP_HOME}}", readme)
                if "codex" in agents:
                    self.assertIn("$sprint-dev", readme)

    def test_switch_to_shared_keeps_readme_custom_content(self):
        with H.TempRepo() as root:
            scaffold(root, "--agent", "claude")
            readme = root / "README.md"
            note = "\n## 项目自定义\n保留 .claude/ 作为历史说明。\n"
            readme.write_text(readme.read_text(encoding="utf-8") + note, encoding="utf-8")
            scaffold(root, "--mode", "upgrade", "--agent", "codex")
            text = readme.read_text(encoding="utf-8")
            self.assertIn("python3 .agents/scripts/aidp_scheduler.py install", text)
            self.assertIn("├── .agents/", text)
            self.assertNotIn("python3 .claude/scripts/aidp_scheduler.py", text)
            self.assertIn(note, text)

    def test_switch_to_claude_renders_docs_to_target_home(self):
        with H.TempRepo() as root:
            scaffold(root, "--agent", "codex")
            readme = root / "README.md"
            readme.write_text(readme.read_text(encoding="utf-8") + "\n## 项目自定义\n保留这段说明。\n",
                              encoding="utf-8")
            scaffold(root, "--mode", "upgrade", "--agent", "claude")
            root_doc = readme.read_text(encoding="utf-8")
            self.assertIn("python3 .claude/scripts/aidp_scheduler.py install", root_doc)
            self.assertIn("├── .claude/", root_doc)
            self.assertNotIn("python3 .agents/scripts/aidp_scheduler.py", root_doc)
            self.assertIn("保留这段说明。", root_doc)
            assert_no_runtime(self, root, ".agents")
            doc = (root / "docs/init/README.md").read_text(encoding="utf-8")
            self.assertRegex(doc, r"(?m)^├── \.claude/\s+#")
            self.assertNotRegex(doc, r"(?m)^├── \.agents/\s+#")
            self.assertNotIn("{{AIDP_HOME}}", doc)
            result = V.VerifyResult()
            V.check_docs_init_sync(root, False, result)
            self.assertFalse(result.warnings, result.warnings)

    def test_rejects_hardlinked_files_before_any_write(self):
        for relative in (".gitignore", "memory/projectBrief.md", "docs/init/README.md",
                         L.USER_FILLABLE_BASELINE):
            with self.subTest(relative=relative), H.TempRepo() as root:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.TemporaryDirectory() as outside:
                    sentinel = Path(outside) / "sentinel"
                    sentinel.write_text("{{project}} external sentinel\n", encoding="utf-8")
                    os.link(sentinel, path)
                    with self.assertRaisesRegex(ValueError, "硬链接"):
                        S.run(root, LegacyRuntimeMigrationTest._options("init", "claude"))
                    self.assertEqual(sentinel.read_text(encoding="utf-8"), "{{project}} external sentinel\n")
                    assert_no_runtime(self, root, ".claude")

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
            LegacyRuntimeMigrationTest._legacy(root)
            old_tpl, installed = root / ".aidp" / tpl_rel, root / ".aidp" / inst_rel
            old_tpl.parent.mkdir(parents=True, exist_ok=True)
            installed.parent.mkdir(parents=True, exist_ok=True)
            old_tpl.write_text("旧版可选规则\n", encoding="utf-8")
            installed.write_text("项目改过的可选规则\n", encoding="utf-8")
            result = scaffold(root, "--mode", "upgrade", "--agent", "claude")
            backup = root / result["backup"] / ".aidp"
            self.assertEqual((backup / tpl_rel).read_text(), "旧版可选规则\n")
            self.assertEqual((backup / inst_rel).read_text(), "项目改过的可选规则\n")
            self.assertFalse(os.path.lexists(root / ".aidp"))


class NativeRuntimeVerifyTest(unittest.TestCase):
    def test_manifest_validation_on_minimal_native_runtime(self):
        with H.TempRepo() as root:
            home = root / ".claude"
            for dirname in runtime_layout.RUNTIME_DIRS:
                (home / dirname).mkdir(parents=True)
            target = home / "commands/example.md"
            target.write_text("valid\n", encoding="utf-8")
            manifest = runtime_layout.build_runtime_manifest(home, "V0.0.1", "claude", ".claude")
            (home / ".aidp-runtime.json").write_text(json.dumps(manifest), encoding="utf-8")
            scaffold_marker.write_version(root, "V0.0.1")
            result = V.VerifyResult()
            V.check_native_runtime(root, result)
            self.assertEqual(result.errors, [])
            self.assertTrue(any("完整" in note for note in result.info))
            target.chmod(target.stat().st_mode ^ 0o100)
            result = V.VerifyResult()
            V.check_native_runtime(root, result)
            self.assertTrue(any("指纹漂移" in error for error in result.errors))

    def test_native_runtime_variants_verify_cleanly(self):
        for agents in ("claude", "codex", "dsh", "claude,codex,dsh"):
            with self.subTest(agents=agents), H.TempRepo() as root:
                env = fake_dsh_env(root)[0] if "dsh" in agents else None
                scaffold(root, "--version", "V0.1.0", "--agent", agents, env=env)
                rc, errors, output = H.verify(root)
                self.assertEqual((rc, errors), (0, []), output)
                self.assertIn("Agent 原生运行包", output)

    def test_manifest_hash_and_mode_drift_are_errors(self):
        for change in ("content", "mode"):
            with self.subTest(change=change), H.TempRepo() as root:
                scaffold(root, "--version", "V0.1.0", "--agent", "claude")
                target = root / ".claude/commands/sprint-dev.md"
                if change == "content":
                    target.write_bytes(target.read_bytes() + b"\nchanged\n")
                else:
                    target.chmod(target.stat().st_mode ^ 0o100)
                rc, errors, output = H.verify(root)
                self.assertEqual(rc, 1, output)
                self.assertTrue(any("运行包" in error for error in errors), output)

    def test_manifest_source_and_version_are_errors(self):
        for field, value in (("source", "shared"), ("version", "V0.0.1")):
            with self.subTest(field=field), H.TempRepo() as root:
                scaffold(root, "--version", "V0.1.0", "--agent", "claude")
                path = root / ".claude/.aidp-runtime.json"
                manifest = json.loads(path.read_text(encoding="utf-8"))
                manifest[field] = value
                path.write_text(json.dumps(manifest), encoding="utf-8")
                rc, errors, output = H.verify(root)
                self.assertEqual(rc, 1, output)
                self.assertTrue(any("运行包" in error for error in errors), output)

    def test_dual_runtime_normalized_mismatch_is_error(self):
        with H.TempRepo() as root:
            scaffold(root, "--version", "V0.1.0", "--agent", "claude,codex")
            home = root / ".agents"
            target = home / "commands/sprint-dev.md"
            target.write_bytes(target.read_bytes() + b"\nshared-only\n")
            manifest = runtime_layout.build_runtime_manifest(home, BUNDLE_VERSION, "shared", ".agents")
            (home / ".aidp-runtime.json").write_text(json.dumps(manifest), encoding="utf-8")
            rc, errors, output = H.verify(root)
            self.assertEqual(rc, 1, output)
            self.assertTrue(any("双包" in error for error in errors), output)

    def test_runtime_unresolved_token_and_old_path_are_errors(self):
        for leak in ("{{AIDP_UNKNOWN}}", ".aidp/commands/sprint-dev.md"):
            with self.subTest(leak=leak), H.TempRepo() as root:
                scaffold(root, "--version", "V0.1.0", "--agent", "claude")
                home = root / ".claude"
                target = home / "commands/sprint-dev.md"
                target.write_bytes(target.read_bytes() + leak.encode())
                manifest = runtime_layout.build_runtime_manifest(home, BUNDLE_VERSION, "claude", ".claude")
                (home / ".aidp-runtime.json").write_text(json.dumps(manifest), encoding="utf-8")
                rc, errors, output = H.verify(root)
                self.assertEqual(rc, 1, output)
                self.assertTrue(any("运行包" in error for error in errors), output)

    def test_legacy_root_residue_is_error(self):
        with H.TempRepo() as root:
            scaffold(root, "--version", "V0.1.0", "--agent", "claude")
            (root / ".aidp").mkdir()
            rc, errors, output = H.verify(root)
            self.assertEqual(rc, 1, output)
            self.assertTrue(any(".aidp/" in error for error in errors), output)

    def test_forged_migration_failure_ledger_cannot_downgrade_legacy_residue(self):
        with H.TempRepo() as root:
            scaffold(root, "--version", "V0.1.0", "--agent", "claude")
            (root / ".aidp").mkdir()
            (root / ".aidp-migration-failure.json").write_text(
                json.dumps({"status": "failed", "version": BUNDLE_VERSION, "legacy_path": ".aidp"}),
                encoding="utf-8")
            result = V.VerifyResult()
            V.check_native_runtime(root, result)
            self.assertTrue(any(".aidp/" in error for error in result.errors), result.errors)

    def test_native_user_files_survive_upgrade_without_inventory_error(self):
        for agents, relative in (("claude", ".claude"), ("codex", ".agents")):
            with self.subTest(agents=agents), H.TempRepo() as root:
                scaffold(root, "--version", "V0.1.0", "--agent", agents)
                home = root / relative
                filled = home / "reference/子Agent必读.md"
                filled.write_text("# 项目约定\n保留本地填写内容\n", encoding="utf-8")
                private_reference = home / "reference/team-only.md"
                private_reference.write_text("# 项目参考\n", encoding="utf-8")
                private_skill = home / "skills/custom/local/SKILL.md"
                private_skill.parent.mkdir(parents=True)
                private_skill.write_text("---\nname: local\n---\n", encoding="utf-8")
                scaffold(root, "--mode", "upgrade", "--agent", agents, "--force")
                manifest = json.loads((home / ".aidp-runtime.json").read_text(encoding="utf-8"))
                self.assertEqual(
                    set(manifest["user_files"]),
                    {"reference/子Agent必读.md", "reference/team-only.md",
                     "skills/custom/local/SKILL.md"},
                )
                self.assertIn("保留本地填写内容", filled.read_text(encoding="utf-8"))
                result = V.VerifyResult()
                V.check_native_runtime(root, result)
                self.assertEqual(result.errors, [], result.errors)

    def test_user_files_cannot_hide_modified_template_reference(self):
        with H.TempRepo() as root:
            scaffold(root, "--version", "V0.1.0", "--agent", "claude")
            home = root / ".claude"
            target = home / "reference/skills.md"
            target.write_bytes(target.read_bytes() + b"\nchanged\n")
            manifest = runtime_layout.build_runtime_manifest(
                home, BUNDLE_VERSION, "claude", ".claude")
            manifest["user_files"] = ["reference/skills.md"]
            (home / ".aidp-runtime.json").write_text(json.dumps(manifest), encoding="utf-8")
            result = V.VerifyResult()
            V.check_native_runtime(root, result)
            self.assertTrue(any("文件与当前脚手架" in error for error in result.errors),
                            result.errors)

    def test_native_manifest_cannot_hide_deleted_file_at_current_version(self):
        with H.TempRepo() as root:
            scaffold(root, "--version", "V0.1.0", "--agent", "claude")
            home = root / ".claude"
            target = home / "commands/sprint-dev.md"
            target.unlink()
            manifest_path = home / ".aidp-runtime.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            del manifest["files"]["commands/sprint-dev.md"]
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            result = V.VerifyResult()
            V.check_native_runtime(root, result)
            self.assertTrue(any("文件清单" in error for error in result.errors), result.errors)

    def test_native_manifest_recomputed_after_tampering_is_still_error(self):
        with H.TempRepo() as root:
            scaffold(root, "--version", "V0.1.0", "--agent", "claude")
            home = root / ".claude"
            target = home / "commands/sprint-dev.md"
            target.write_bytes(target.read_bytes() + b"\nmodified\n")
            manifest = runtime_layout.build_runtime_manifest(home, BUNDLE_VERSION, "claude", ".claude")
            (home / ".aidp-runtime.json").write_text(json.dumps(manifest), encoding="utf-8")
            result = V.VerifyResult()
            V.check_native_runtime(root, result)
            self.assertTrue(any("文件与当前脚手架" in error for error in result.errors), result.errors)

    def test_older_native_runtime_warns_about_upgrade_without_inventory_error(self):
        with H.TempRepo() as root:
            scaffold(root, "--version", "V0.1.0", "--agent", "claude")
            home = root / ".claude"
            manifest_path = home / ".aidp-runtime.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["version"] = "V0.0.1"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            scaffold_marker.write_version(root, "V0.0.1")
            result = V.VerifyResult()
            V.check_native_runtime(root, result)
            V.check_contract_drift(root, result)
            self.assertEqual(result.errors, [])
            self.assertTrue(any("低于当前脚手架" in warning for warning in result.warnings), result.warnings)

    def test_pending_upgrade_runtime_version_matches_pending(self):
        with H.TempRepo() as root:
            scaffold(root, "--version", "V0.1.0", "--agent", "claude")
            scaffold_marker.write_version(root, "V0.0.1")
            scaffold_marker.write_pending(root, BUNDLE_VERSION)
            result = V.VerifyResult()
            V.check_native_runtime(root, result)
            self.assertEqual(result.errors, [])

    def test_guard_runner_uses_native_runtime_script(self):
        with H.TempRepo() as root:
            scaffold(root, "--version", "V0.1.0", "--agent", "claude")
            data, error = V._run_guard(root, "check_ghost_flags")
            self.assertIsNone(error)
            self.assertIsInstance(data, dict)
            self.assertIn("undefined", data)

    def test_native_flow_size_guard_checks_runtime_flows(self):
        with H.TempRepo() as root:
            scaffold(root, "--version", "V0.1.0", "--agent", "claude")
            (root / ".claude/flows/oversized.md").write_text("x" * 20481, encoding="utf-8")
            result = V.VerifyResult()
            V.check_flow_slice_size(root, result)
            self.assertTrue(any("flows 分片超" in error for error in result.errors), result.errors)

    def test_native_scripts_readme_guard_checks_runtime_scripts(self):
        with H.TempRepo() as root:
            scaffold(root, "--version", "V0.1.0", "--agent", "codex")
            (root / ".agents/scripts/unlisted_probe.py").write_text("pass\n", encoding="utf-8")
            result = V.VerifyResult()
            V.check_scripts_readme_coverage(root, result)
            self.assertTrue(any("unlisted_probe.py" in warning for warning in result.warnings), result.warnings)

    def test_native_contract_drift_keeps_old_version_warning(self):
        with H.TempRepo() as root:
            scaffold(root, "--version", "V0.1.0", "--agent", "claude")
            scaffold_marker.write_version(root, "V0.0.1")
            result = V.VerifyResult()
            V.check_contract_drift(root, result)
            self.assertTrue(any("低于当前脚手架" in warning for warning in result.warnings), result.warnings)

    def test_plain_directory_vcs_mode_is_none(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(V._vcs_mode(Path(temp)), "none")

    def test_non_git_verify_marks_tracking_unsupported(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "plain"
            root.mkdir()
            scaffold(root, "--version", "V0.1.0", "--agent", "claude", "--user", "alice")
            rc, errors, output = H.verify(root, user="alice")
            self.assertEqual((rc, errors), (0, []), output)
            self.assertIn("vcs_mode=none", output)
            self.assertIn("unsupported:vcs-disabled", output)
            self.assertNotIn("运行时产物入库策略一致", output)


class NativeAdapterVerifyTest(unittest.TestCase):
    def test_copy_mode_detects_native_runtime_without_legacy_source(self):
        with H.TempRepo() as root:
            scaffold(root, "--version", "V0.1.0", "--agent", "claude")
            self.assertEqual(V._adapter_mode(root, None), "copy")

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
            keep_days=L.PRUNE_KEEP_DAYS_DEFAULT, no_agent_sync=False, adapter_mode="link")

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
            self.assertEqual(len(L.scan_backups(root)), before + 1)
            self.assertTrue((root / res["backup"] / ".aidp/skills/aidp-cmd/SKILL.md").is_file())
            self.assertTrue(any(a["op"] == "remove" and a["path"] == ".aidp/"
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
            self.assertTrue((root / res["backup"] / ".aidp/skills/aidp-cmd/agents/openai.yaml").is_file())

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
            self.assertFalse(os.path.lexists(root / ".aidp"))

    def test_backup_failure_preserves_modified_router(self):
        with H.TempRepo() as root:
            scaffold(root, "--version", "V0.1.0", "--agent", "claude", "--no-agent-sync")
            router = self._router(root, modified=True)
            original = (router / "SKILL.md").read_text(encoding="utf-8")
            with mock.patch.object(S.Backup, "save_tree", side_effect=OSError("disk full")):
                res = S.run(root, self._options())
            self.assertTrue(router.is_dir())
            self.assertEqual((router / "SKILL.md").read_text(encoding="utf-8"), original)
            self.assertTrue(any("旧运行目录备份失败" in w and "disk full" in w for w in res["warnings"]),
                            res["warnings"])
            self.assertEqual(res["status"], "blocked")

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
