#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Agent 原生运行包渲染、manifest 与原子替换回归。"""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import scaffold_lib as L

try:
    import runtime_layout as R
except ImportError:
    R = None


TEXT = "run={{AIDP_HOME}}/scripts/tool.py\n"


def make_source(root: Path) -> Path:
    source = root / "source"
    for dirname in L.RUNTIME_DIRS:
        (source / dirname).mkdir(parents=True, exist_ok=True)
        (source / dirname / "sample.txt").write_text(TEXT, encoding="utf-8")
    (source / "commands/sprint-dev.md").write_text(
        "python3 {{AIDP_HOME}}/scripts/tool.py\n", encoding="utf-8")
    (source / "skills/demo/SKILL.md").parent.mkdir(parents=True, exist_ok=True)
    (source / "skills/demo/SKILL.md").write_text("read {{AIDP_HOME}}/reference/x.md\n", encoding="utf-8")
    (source / "plugins/chrome/skills/demo/SKILL.md").parent.mkdir(parents=True, exist_ok=True)
    (source / "plugins/chrome/skills/demo/SKILL.md").write_text("plugin\n", encoding="utf-8")
    (source / "scripts/blob.bin").write_bytes(b"\xff\x00{{AIDP_HOME}}")
    (source / "skills/aidp-code-engineer/SKILL.md").parent.mkdir(parents=True, exist_ok=True)
    (source / "skills/aidp-code-engineer/SKILL.md").write_text("self\n", encoding="utf-8")
    (source / "scripts/tests/test_x.py").parent.mkdir(parents=True, exist_ok=True)
    (source / "scripts/tests/test_x.py").write_text("pass\n", encoding="utf-8")
    (source / "scripts/design-goals-baseline.txt").write_text("baseline\n", encoding="utf-8")
    (source / "scripts/__pycache__/x.pyc").parent.mkdir(parents=True, exist_ok=True)
    (source / "scripts/__pycache__/x.pyc").write_bytes(b"cache")
    (source / "memory").mkdir()
    (source / "memory/should-not-copy.md").write_text("memory\n", encoding="utf-8")
    return source


def all_files(root: Path):
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


class RuntimeLayoutTestCase(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(R, "runtime_layout.py 尚未实现")


class RenderContractTest(RuntimeLayoutTestCase):
    def test_runtime_tree_contains_contract_sources_and_excludes_template_owned(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = make_source(base)
            target = base / "rendered"
            R.render_tree(source, target, ".claude")
            for dirname in L.RUNTIME_DIRS:
                self.assertTrue((target / dirname).is_dir(), dirname)
            self.assertTrue((target / "commands/sprint-dev.md").is_file())
            self.assertTrue((target / "skills/demo/SKILL.md").is_file())
            self.assertTrue((target / "plugins/chrome/skills/demo/SKILL.md").is_file())
            self.assertFalse((target / "skills/aidp-code-engineer").exists())
            self.assertFalse((target / "scripts/tests").exists())
            self.assertFalse((target / "scripts/design-goals-baseline.txt").exists())
            self.assertFalse((target / "scripts/__pycache__").exists())
            self.assertFalse((target / "memory").exists())

    def test_render_text_supports_both_homes_and_rejects_bad_contracts(self):
        self.assertEqual(R.render_text(TEXT, ".claude"), "run=.claude/scripts/tool.py\n")
        self.assertEqual(R.render_text(TEXT, ".agents"), "run=.agents/scripts/tool.py\n")
        for invalid in (
            "{{AIDP_UNKNOWN_TOKEN}}\n",
            "python3 .aidp/scripts/tool.py\n",
            "read /srv/workspace/private/.aidp/x\n",   # 绝对路径里的旧运行根同样要拦
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    R.render_text(invalid, ".claude")
        self.assertIn("LEGACY_AIDP_DIR", R.render_text('LEGACY_AIDP_DIR = ".aidp"\n', ".claude"))

    def test_source_requires_every_real_runtime_directory(self):
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as outside_td:
            base = Path(td)
            source = make_source(base)
            shutil.rmtree(source / "flows")
            with self.assertRaises(RuntimeError):
                R.render_tree(source, base / "missing-output", ".claude")

            source = make_source(base / "second")
            shutil.rmtree(source / "rules")
            Path(source / "rules").symlink_to(Path(outside_td), target_is_directory=True)
            with self.assertRaises(RuntimeError):
                R.render_tree(source, base / "symlink-output", ".agents")

    def test_legacy_constant_does_not_exempt_an_illegal_runtime_path_on_same_line(self):
        self.assertEqual(
            R.render_text('LEGACY_AIDP_DIR = ".aidp"\n', ".claude"),
            'LEGACY_AIDP_DIR = ".aidp"\n',
        )
        with self.assertRaises(ValueError):
            R.render_text(
                'LEGACY_AIDP_DIR = ".aidp"; command = ".aidp/scripts/tool.py"\n',
                ".claude",
            )

    def test_templates_must_use_runtime_token_instead_of_hardcoded_homes(self):
        self.assertEqual(
            R.render_text("run={{AIDP_HOME}}/scripts/x.py\n", ".claude"),
            "run=.claude/scripts/x.py\n",
        )
        self.assertEqual(
            R.render_text("run={{AIDP_HOME}}/scripts/x.py\n", ".agents"),
            "run=.agents/scripts/x.py\n",
        )
        # ★ 判据是「不得烙进**别的 Agent 的**运行根」。运行根降层后就是 `.claude` / `.agents`
        #   本身，写死本 Agent 的根与 `{{AIDP_HOME}}` 渲染结果逐字相同、无害；真正会出错的是
        #   把另一个 Agent 的根烙进来（`.agents/...` 进了 Claude 包），那才是这道门的理由。
        for text, home in (
            ("run=.agents/scripts/x.py\n", ".claude"),
            ("run=.claude/scripts/x.py\n", ".agents"),
        ):
            with self.subTest(text=text, home=home):
                with self.assertRaises(ValueError):
                    R.render_text(text, home)
        # 阴性：同名运行根的字面量、以及非受管目录的落点（settings.json / 用户级路径）都放行
        for text, home in (
            ("run=.claude/scripts/x.py\n", ".claude"),
            ("run=.agents/scripts/x.py\n", ".agents"),
            ("hook 写进 .claude/settings.json\n", ".claude"),
            ("缓存在 ~/.agents/skills/x/\n", ".claude"),
        ):
            with self.subTest(negative=text, home=home):
                R.render_text(text, home)
        # 豁免标记：适配位对照表要逐字写出各 Agent 的目录
        R.render_text(".agents/skills/ 与 .claude/skills/  <!-- runtime-path-ignore: 对照 -->\n",
                      ".claude")

    def test_render_rejects_template_root_leaks_but_allows_generic_absolute_paths(self):
        posix_root = "/workspace/template"
        windows_root = r"C:\workspace\template"
        with self.assertRaises(ValueError):
            R.render_text("read /workspace/template/.hidden/file.md\n", ".claude",
                          template_root=posix_root)
        with self.assertRaises(ValueError):
            R.render_text(r"read C:\workspace\template\rules\x.md" + "\n", ".agents",
                          template_root=windows_root)
        self.assertEqual(
            R.render_text("#!/usr/bin/env python3\npath=C:/Windows/System32\n", ".claude",
                          template_root=posix_root),
            "#!/usr/bin/env python3\npath=C:/Windows/System32\n",
        )

    def test_runtime_path_ignore_only_exempts_template_root_on_that_line(self):
        root = "/workspace/template"
        text = (
            "example=/workspace/template/demo  # runtime-path-ignore: 文档示例\n"
            "generic=/usr/bin/env\n"
        )
        self.assertEqual(R.render_text(text, ".claude", template_root=root), text)
        with self.assertRaises(ValueError):
            R.render_text(
                "bad=.aidp/scripts/x  # runtime-path-ignore: 不得豁免旧路径\n",
                ".claude", template_root=root,
            )
        with self.assertRaises(ValueError):
            R.render_text(
                "bad={{AIDP_UNKNOWN_TOKEN}}  # runtime-path-ignore: 不得豁免 token\n",
                ".claude", template_root=root,
            )
        with self.assertRaises(ValueError):
            R.render_text(
                "one=/workspace/template/a  # runtime-path-ignore: 示例\n"
                "two=/workspace/template/b\n",
                ".claude", template_root=root,
            )

    def test_binary_is_copied_without_text_substitution(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = make_source(base)
            target = base / "rendered"
            R.render_tree(source, target, ".agents")
            self.assertEqual((target / "scripts/blob.bin").read_bytes(), b"\xff\x00{{AIDP_HOME}}")


class ManifestContractTest(RuntimeLayoutTestCase):
    def test_manifest_is_deterministic_sorted_and_excludes_itself(self):
        with tempfile.TemporaryDirectory() as td:
            runtime = Path(td) / "aidp"
            runtime.mkdir()
            (runtime / "commands").mkdir()
            (runtime / "commands/b.md").write_text("b\n", encoding="utf-8")
            (runtime / "commands/a.md").write_text("a\n", encoding="utf-8")
            # ★ 运行根**根级**的外来文件必须不进 manifest：运行根降到 `.claude` / `.agents`
            #   之后，这里住的是 settings.json / settings.local.json 这类别人的东西。
            #   进了 manifest 就会被算进指纹，并在下次替换时当成"受管但已消失"删掉。
            (runtime / "settings.json").write_text("{}\n", encoding="utf-8")
            (runtime / "worktrees").mkdir()
            (runtime / "worktrees/keep.txt").write_text("k\n", encoding="utf-8")
            manifest = R.build_runtime_manifest(
                runtime, version="V1.2.3", source="claude", home=".claude")
            self.assertEqual(manifest["schema"], "aidp.runtime/v1")
            self.assertEqual(manifest["version"], "V1.2.3")
            self.assertEqual(manifest["source"], "claude")
            self.assertEqual(list(manifest["files"]), ["commands/a.md", "commands/b.md"])
            self.assertNotIn(R.RUNTIME_MANIFEST, manifest["files"])
            self.assertNotIn("settings.json", manifest["files"])
            self.assertNotIn("worktrees/keep.txt", manifest["files"])
            for metadata in manifest["files"].values():
                self.assertEqual(set(metadata), {"sha256", "mode"})
                self.assertRegex(metadata["sha256"], r"^[0-9a-f]{64}$")
                self.assertRegex(metadata["mode"], r"^[0-7]{4}$")

    def test_manifest_version_is_required_and_strict_semver(self):
        with tempfile.TemporaryDirectory() as td:
            runtime = Path(td) / "aidp"
            runtime.mkdir()
            (runtime / "a.txt").write_text("a\n", encoding="utf-8")
            for version in (None, "", 1, "1.2.3", "V1.2", "V1.2.3.4", "V1.x.3"):
                with self.subTest(version=version):
                    with self.assertRaises(ValueError):
                        R.build_runtime_manifest(
                            runtime, version=version, source="claude", home=".claude")

            source = make_source(Path(td) / "source-fixture")
            installed = Path(td) / ".claude"
            R.render_runtime(source, installed, ".claude", "V1.2.3", "claude")
            original_manifest = (installed / R.RUNTIME_MANIFEST).read_text(encoding="utf-8")
            for version in (None, "", 1, "1.2.3", "V1.2"):
                manifest = json.loads((installed / R.RUNTIME_MANIFEST).read_text(encoding="utf-8"))
                manifest["version"] = version
                (installed / R.RUNTIME_MANIFEST).write_text(
                    json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
                with self.subTest(validate_version=version):
                    with self.assertRaises(ValueError):
                        R.validate_runtime(installed, expected_home=".claude")
                    with self.assertRaises(ValueError):
                        R.render_runtime(source, installed, ".claude", "V1.2.3", "claude")
            (installed / R.RUNTIME_MANIFEST).write_text(original_manifest, encoding="utf-8")
            R.render_runtime(source, installed, ".claude", "V1.2.3", "claude")

    def test_source_and_home_mapping_is_enforced_at_every_layer(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = make_source(base)
            runtime = base / "runtime"
            R.render_tree(source, runtime, ".claude")
            with self.assertRaises(ValueError):
                R.build_runtime_manifest(runtime, version="V1.0.0", source="claude",
                                         home=".agents")
            with self.assertRaises(ValueError):
                R.build_runtime_manifest(runtime, version="V1.0.0", source="shared",
                                         home=".claude")
            with self.assertRaises(ValueError):
                R.render_runtime(source, base / ".claude", ".agents",
                                 "V1.0.0", "claude")
            with self.assertRaises(ValueError):
                R.render_runtime(source, base / ".agents", ".claude",
                                 "V1.0.0", "shared")
            manifest = R.build_runtime_manifest(
                runtime, version="V1.0.0", source="claude", home=".claude")
            (runtime / R.RUNTIME_MANIFEST).write_text(
                json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            with self.assertRaises(ValueError):
                R.validate_runtime(runtime, expected_home=".agents")

    def test_validate_allows_expected_home_and_rejects_other_home_or_token_even_if_rehashed(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = make_source(base)
            runtime = base / ".claude"
            R.render_runtime(source, runtime, ".claude", "V1.0.0", "claude")
            R.validate_runtime(runtime, expected_home=".claude")
            command = runtime / "commands/sprint-dev.md"
            for illegal in (
                "run=.agents/scripts/x.py\n",
                "run={{AIDP_HOME}}/scripts/x.py\n",
                "run=.aidp/scripts/x.py\n",
            ):
                command.write_text(illegal, encoding="utf-8")
                manifest = R.build_runtime_manifest(
                    runtime, version="V1.0.0", source="claude", home=".claude")
                (runtime / R.RUNTIME_MANIFEST).write_text(
                    json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
                with self.subTest(illegal=illegal):
                    with self.assertRaises(ValueError):
                        R.validate_runtime(runtime, expected_home=".claude")
            R.render_runtime(source, runtime, ".claude", "V1.0.0", "claude")

    def test_mode_is_manifested_and_permission_drift_is_detected(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = make_source(base)
            tool = source / "scripts/sample.txt"
            tool.chmod(0o755)
            claude = base / ".claude"
            shared = base / ".agents"
            R.render_runtime(source, claude, ".claude", "V1.0.0", "claude")
            R.render_runtime(source, shared, ".agents", "V1.0.0", "shared")
            manifest = json.loads((claude / R.RUNTIME_MANIFEST).read_text(encoding="utf-8"))
            self.assertEqual(manifest["files"]["scripts/sample.txt"]["mode"], "0755")
            self.assertEqual(stat.S_IMODE((claude / "scripts/sample.txt").stat().st_mode), 0o755)
            self.assertEqual(R.normalize_runtime(claude, ".claude"),
                             R.normalize_runtime(shared, ".agents"))

            (shared / "scripts/sample.txt").chmod(0o644)
            with self.assertRaises(ValueError):
                R.validate_runtime(shared, expected_home=".agents")
            self.assertNotEqual(R.normalize_runtime(claude, ".claude"),
                                R.normalize_runtime(shared, ".agents"))
            self.assertNotEqual(R.tree_digest(claude), R.tree_digest(shared))

    def test_validate_rejects_missing_required_directory_even_with_matching_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = make_source(base)
            runtime = base / ".claude"
            R.render_runtime(source, runtime, ".claude", "V1.0.0", "claude")
            shutil.rmtree(runtime / "agents")
            manifest = json.loads((runtime / R.RUNTIME_MANIFEST).read_text(encoding="utf-8"))
            manifest["files"] = {
                relative: digest for relative, digest in manifest["files"].items()
                if not relative.startswith("agents/")
            }
            (runtime / R.RUNTIME_MANIFEST).write_text(
                json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            with self.assertRaises(ValueError):
                R.validate_runtime(runtime, expected_home=".claude")

    def test_validate_detects_tampering_and_normalize_compares_homes(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = make_source(base)
            claude = base / ".claude"
            shared = base / ".agents"
            R.render_runtime(source, claude, ".claude", "V1.0.0", "claude")
            R.render_runtime(source, shared, ".agents", "V1.0.0", "shared")
            R.validate_runtime(claude, expected_home=".claude")
            R.validate_runtime(shared, expected_home=".agents")
            self.assertEqual(R.normalize_runtime(claude, ".claude"),
                             R.normalize_runtime(shared, ".agents"))
            (shared / "commands/sprint-dev.md").write_text("drift\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                R.validate_runtime(shared, expected_home=".agents")
            self.assertNotEqual(R.normalize_runtime(claude, ".claude"),
                                R.normalize_runtime(shared, ".agents"))


class AtomicInstallTest(RuntimeLayoutTestCase):
    def test_upgrade_preserves_user_reference_and_private_files_across_both_homes(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = make_source(base)
            reference = "reference/子Agent必读.md"
            (source / reference).write_text("skeleton\n", encoding="utf-8")
            homes = [("claude", ".claude"), ("shared", ".agents")]
            for kind, home in homes:
                R.render_runtime(source, base / home, home, "V1.0.0", kind)
            first = base / homes[0][1]
            (first / reference).write_text("project-specific\n", encoding="utf-8")
            (first / "skills/custom/my-tool/SKILL.md").parent.mkdir(parents=True, exist_ok=True)
            (first / "skills/custom/my-tool/SKILL.md").write_text("custom\n", encoding="utf-8")
            (first / "reference/private.md").write_text("private\n", encoding="utf-8")
            (source / reference).write_text("new skeleton\n", encoding="utf-8")
            (source / "commands/sprint-dev.md").write_text("new {{AIDP_HOME}}\n", encoding="utf-8")

            for version in ("V1.0.1", "V1.0.2"):
                for kind, home in homes:
                    R.render_runtime(source, base / home, home, version, kind,
                                     backup_callback=lambda runtime: shutil.copytree(
                                         runtime, base / ("backup-" + kind + "-" + version)))
                    self.assertEqual(R.validate_runtime(base / home, home)["version"], version)
                    self.assertEqual((base / home / reference).read_text(), "project-specific\n")
                    self.assertEqual((base / home / "skills/custom/my-tool/SKILL.md").read_text(), "custom\n")
                    self.assertEqual((base / home / "reference/private.md").read_text(), "private\n")
                    self.assertEqual((base / home / "commands/sprint-dev.md").read_text(),
                                     "new " + home + "\n")
                self.assertEqual(R.normalize_runtime(base / homes[0][1], homes[0][1]),
                                 R.normalize_runtime(base / homes[1][1], homes[1][1]))

    def test_user_overlay_requires_full_backup_and_keeps_original_copy(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = make_source(base)
            reference = "reference/子Agent必读.md"
            (source / reference).write_text("skeleton\n", encoding="utf-8")
            runtime = base / ".agents"
            R.render_runtime(source, runtime, ".agents", "V1.0.0", "shared")
            (runtime / reference).write_text("project entry\n", encoding="utf-8")
            before = R.tree_digest(runtime)
            with self.assertRaisesRegex(RuntimeError, "完整备份"):
                R.render_runtime(source, runtime, ".agents", "V1.0.1", "shared")
            self.assertEqual(R.tree_digest(runtime), before)
            R.render_runtime(source, runtime, ".agents", "V1.0.1", "shared",
                             backup_callback=lambda old: shutil.copytree(old, base / "backup"))
            self.assertEqual((base / "backup" / reference).read_text(), "project entry\n")
            self.assertEqual((runtime / reference).read_text(), "project entry\n")
            self.assertEqual(R.validate_runtime(runtime, ".agents")["version"], "V1.0.1")

    def test_invalid_user_provenance_in_manifest_rejects_upgrade(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = make_source(base)
            runtime = base / ".agents"
            R.render_runtime(source, runtime, ".agents", "V1.0.0", "shared")
            manifest_path = runtime / R.RUNTIME_MANIFEST
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["user_files"] = ["commands/sprint-dev.md"]
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            before = R.tree_digest(runtime)
            with self.assertRaises(ValueError):
                R.render_runtime(source, runtime, ".agents", "V1.0.1", "shared")
            self.assertEqual(R.tree_digest(runtime), before)

    def test_user_overlay_conflict_fails_without_replacing_either_runtime(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = make_source(base)
            reference = "reference/子Agent必读.md"
            (source / reference).write_text("skeleton\n", encoding="utf-8")
            claude, shared = base / ".claude", base / ".agents"
            R.render_runtime(source, claude, ".claude", "V1.0.0", "claude")
            R.render_runtime(source, shared, ".agents", "V1.0.0", "shared")
            (claude / reference).write_text("claude edit\n", encoding="utf-8")
            (shared / reference).write_text("shared edit\n", encoding="utf-8")
            before = (R.tree_digest(claude), R.tree_digest(shared))
            with self.assertRaisesRegex(RuntimeError, "冲突"):
                R.render_runtime(source, claude, ".claude", "V1.0.1", "claude",
                                 backup_callback=lambda runtime: shutil.copytree(runtime, base / "backup"))
            self.assertEqual((R.tree_digest(claude), R.tree_digest(shared)), before)

    def test_private_overlay_collision_with_new_managed_source_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = make_source(base)
            runtime = base / ".agents"
            R.render_runtime(source, runtime, ".agents", "V1.0.0", "shared")
            private = runtime / "reference/private.md"
            private.write_text("project data\n", encoding="utf-8")
            (source / "reference/private.md").write_text("new managed data\n", encoding="utf-8")
            before = R.tree_digest(runtime)
            with self.assertRaisesRegex(RuntimeError, "冲突"):
                R.render_runtime(source, runtime, ".agents", "V1.0.1", "shared",
                                 backup_callback=lambda old: shutil.copytree(old, base / "backup"))
            self.assertEqual(R.tree_digest(runtime), before)

    def test_user_overlay_hardlink_and_symlink_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = make_source(base)
            runtime = base / ".agents"
            R.render_runtime(source, runtime, ".agents", "V1.0.0", "shared")
            external = base / "external"
            external.write_text("external content\n", encoding="utf-8")
            private = runtime / "reference/private.md"
            try:
                os.link(external, private)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"当前平台不支持 hardlink: {exc}")
            with self.assertRaisesRegex((RuntimeError, ValueError), "hardlink"):
                R.render_runtime(source, runtime, ".agents", "V1.0.1", "shared",
                                 backup_callback=lambda old: shutil.copytree(old, base / "backup-hardlink"))
            self.assertEqual(external.read_text(), "external content\n")
            private.unlink()
            private.symlink_to(external)
            with self.assertRaisesRegex((RuntimeError, ValueError), "symlink"):
                R.render_runtime(source, runtime, ".agents", "V1.0.1", "shared",
                                 backup_callback=lambda old: shutil.copytree(old, base / "backup-symlink"))
            self.assertEqual(external.read_text(), "external content\n")

    def test_replaces_existing_valid_runtime_atomically(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = make_source(base)
            destination = base / ".claude"
            R.render_runtime(source, destination, ".claude", "V1.0.0", "claude")
            (source / "commands/sprint-dev.md").write_text("new {{AIDP_HOME}}\n", encoding="utf-8")
            R.render_runtime(source, destination, ".claude", "V1.0.1", "claude")
            manifest = json.loads((destination / R.RUNTIME_MANIFEST).read_text(encoding="utf-8"))
            self.assertEqual(manifest["version"], "V1.0.1")
            self.assertIn("new .claude", (destination / "commands/sprint-dev.md").read_text())
            self.assertFalse(destination.with_name("aidp.aidp-stage").exists())
            self.assertFalse(destination.with_name("aidp.aidp-previous").exists())

    def test_stale_lock_file_is_reusable_and_persists_after_release(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = make_source(base)
            destination = base / ".claude"
            lock = destination.parent / ".aidp-runtime.lock"
            lock.parent.mkdir(parents=True, exist_ok=True)
            lock.write_text("stale-owner\n", encoding="utf-8")
            R.render_runtime(source, destination, ".claude", "V1.0.0", "claude")
            self.assertTrue(lock.is_file())
            self.assertGreaterEqual(lock.stat().st_size, 1)
            R.render_runtime(source, destination, ".claude", "V1.0.1", "claude")

    def test_active_lock_in_independent_process_rejects_then_releases(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = make_source(base)
            destination = base / ".agents"
            destination.parent.mkdir(parents=True, exist_ok=True)
            child_code = (
                "import sys,time; from pathlib import Path; "
                "sys.path.insert(0,sys.argv[1]); import runtime_layout as r; "
                "h=r._acquire_runtime_lock(Path(sys.argv[2]),Path(sys.argv[3])); "
                "print('READY',flush=True); time.sleep(60)"
            )
            process = subprocess.Popen(
                [sys.executable, "-c", child_code, str(SCRIPTS),
                 str(destination.parent), str(base)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            try:
                self.assertEqual(process.stdout.readline().strip(), "READY")
                with self.assertRaises(RuntimeError):
                    R.render_runtime(source, destination, ".agents", "V1.0.0", "shared")
                self.assertFalse(destination.exists())
            finally:
                process.terminate()
                process.communicate(timeout=10)
            R.render_runtime(source, destination, ".agents", "V1.0.0", "shared")
            self.assertTrue((destination.parent / ".aidp-runtime.lock").is_file())

    def test_lock_swap_to_symlink_between_precheck_and_open_never_writes_target(self):
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as outside_td:
            base, outside = Path(td), Path(outside_td)
            parent = base / ".claude"
            parent.mkdir()
            lock = parent / ".aidp-runtime.lock"
            lock.write_bytes(b"stale-lock\n")
            sentinel = outside / "sentinel"
            sentinel.write_bytes(b"external-bytes-must-not-change\n")
            before = sentinel.read_bytes()

            def swap_to_symlink(_lock_path):
                lock.unlink()
                lock.symlink_to(sentinel)

            with self.assertRaises(RuntimeError):
                R._acquire_runtime_lock(parent, base, _after_lock_precheck=swap_to_symlink)
            self.assertTrue(lock.is_symlink())
            self.assertEqual(sentinel.read_bytes(), before)

    def test_hard_linked_lock_is_rejected_without_writing_external_sentinel(self):
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as outside_td:
            base, outside = Path(td), Path(outside_td)
            parent = base / ".claude"
            parent.mkdir()
            lock = parent / ".aidp-runtime.lock"
            sentinel = outside / "sentinel"
            sentinel.write_bytes(b"hard-link-target-must-not-change\n")
            before = sentinel.read_bytes()
            try:
                os.link(str(sentinel), str(lock))
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"当前平台不支持 hardlink: {exc}")
            before_links = sentinel.stat().st_nlink
            with self.assertRaises(RuntimeError):
                R._acquire_runtime_lock(parent, base)
            self.assertEqual(sentinel.read_bytes(), before)
            self.assertEqual(lock.read_bytes(), before)
            self.assertEqual(sentinel.stat().st_nlink, before_links)
            self.assertTrue(lock.exists())

    def test_invalid_lock_symlink_or_directory_is_rejected_and_preserved(self):
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as outside_td:
            base, outside = Path(td), Path(outside_td)
            source = make_source(base)
            destination = base / ".claude"
            destination.parent.mkdir(parents=True, exist_ok=True)
            lock = destination.parent / ".aidp-runtime.lock"
            sentinel = outside / "sentinel"
            sentinel.write_text("safe\n", encoding="utf-8")
            lock.symlink_to(sentinel)
            with self.assertRaises(RuntimeError):
                R.render_runtime(source, destination, ".claude", "V1.0.0", "claude")
            self.assertTrue(lock.is_symlink())
            self.assertEqual(sentinel.read_text(), "safe\n")

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = make_source(base)
            destination = base / ".claude"
            lock = destination.parent / ".aidp-runtime.lock"
            lock.mkdir(parents=True, exist_ok=True)
            with self.assertRaises(RuntimeError):
                R.render_runtime(source, destination, ".claude", "V1.0.0", "claude")
            self.assertTrue(lock.is_dir())

    def test_backup_callback_modification_after_copy_aborts_and_preserves_second_edit(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = make_source(base)
            destination = base / ".agents"
            R.render_runtime(source, destination, ".agents", "V1.0.0", "shared")
            command = destination / "commands/sprint-dev.md"
            command.write_text("first user edit\n", encoding="utf-8")

            def backup_then_modify(runtime):
                target = base / "race-backup"
                shutil.copytree(runtime, target)
                command.write_text("second concurrent edit\n", encoding="utf-8")
                return target

            with self.assertRaises(RuntimeError):
                R.render_runtime(source, destination, ".agents", "V1.0.1", "shared",
                                 backup_callback=backup_then_modify)
            self.assertEqual(command.read_text(), "second concurrent edit\n")
            self.assertTrue((destination.parent / ".aidp-runtime.lock").is_file())

    def test_preexisting_fixed_transaction_names_are_never_touched(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = make_source(base)
            destination = base / ".claude"
            fixed_stage = destination.with_name("aidp.aidp-stage")
            fixed_previous = destination.with_name("aidp.aidp-previous")
            fixed_stage.mkdir(parents=True, exist_ok=True)
            fixed_previous.mkdir(parents=True, exist_ok=True)
            (fixed_stage / "user.txt").write_text("stage-user\n", encoding="utf-8")
            (fixed_previous / "user.txt").write_text("previous-user\n", encoding="utf-8")
            R.render_runtime(source, destination, ".claude", "V1.0.0", "claude")
            self.assertEqual((fixed_stage / "user.txt").read_text(), "stage-user\n")
            self.assertEqual((fixed_previous / "user.txt").read_text(), "previous-user\n")

    def test_render_failure_keeps_old_runtime(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = make_source(base)
            destination = base / ".agents"
            R.render_runtime(source, destination, ".agents", "V1.0.0", "shared")
            before = R.tree_digest(destination)
            (source / "commands/sprint-dev.md").write_text("{{AIDP_UNKNOWN_TOKEN}}\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                R.render_runtime(source, destination, ".agents", "V1.0.1", "shared")
            self.assertEqual(R.tree_digest(destination), before)

    def test_foreign_root_entries_survive_reinstall_and_are_not_owned(self):
        """★ 本次改造的目的：运行根里**别人的东西**必须活过重装、且不被算作"运行包被改过"。

        运行根降到 `.claude` / `.agents` 之后，那里住着 Claude Code 的 settings.json、
        settings.local.json 和 git 的 worktrees/。整目录替换会把它们一起删掉（毁数据），
        把它们算进 manifest 则会让每次升级都误判成"运行包被用户改过、必须先完整备份"。
        两种后果都不可接受，所以钉在这里。

        ⚠️ 受管目录**内部**的项目自有条目（如 `skills/project-own/`）不在本用例范围：
        那条路径归 `_user_overlay` 机制管，随运行根真正降层时一并处理。
        """
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = make_source(base)
            destination = base / ".claude"
            R.render_runtime(source, destination, ".claude", "V1.0.0", "claude")

            foreign = {
                "settings.json": '{"hooks": {}}\n',
                "settings.local.json": '{"local": true}\n',
                "worktrees/wt/keep.txt": "worktree payload\n",
            }
            for relative, body in foreign.items():
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(body, encoding="utf-8")

            # ★ 不传 backup_callback：外来条目不得把运行包判成"被改过"，否则每次升级都要求备份。
            R.render_runtime(source, destination, ".claude", "V1.0.1", "claude")

            for relative, body in foreign.items():
                target = destination / relative
                self.assertTrue(target.is_file(), f"重装后外来条目丢失：{relative}")
                self.assertEqual(target.read_text(encoding="utf-8"), body, relative)

            manifest = json.loads((destination / R.RUNTIME_MANIFEST).read_text(encoding="utf-8"))
            for relative in foreign:
                self.assertNotIn(relative, manifest["files"],
                                 f"运行根根级的外来条目不该进 manifest：{relative}")

    def test_credential_named_user_files_survive_and_trigger_backup(self):
        """★ 被下发忽略集命中的用户文件（`config.json` / `.env` / `auth.*.json`）必须活过重装。

        `scaffold_lib.is_ignored` 是**镜像 / 下发**口径——排除这批名字是为了不把凭据打进
        bundle。把同一口径套到**已安装运行包**上，语义正好反过来：它们恰恰是用户自己填的
        凭据（`{{AIDP_HOME}}/skills/*/config.json` 就是范式内的落点）。沿用下发口径会让
        它们对重装完全隐形——既不进 manifest 指纹（`_runtime_modified` 看不见 → 不触发
        备份），也不进 `_user_overlay`（→ 随 previous 一起被丢弃）。凭据 + gitignore +
        无备份 = 不可恢复。本用例同时钉住「活下来」与「触发备份」两件事。
        """
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = make_source(base)
            destination = base / ".claude"
            R.render_runtime(source, destination, ".claude", "V1.0.0", "claude")

            own = {
                "skills/project-own/SKILL.md": "---\nname: project-own\n---\n",
                "skills/project-own/config.json": '{"token": "USER-SECRET"}\n',
                "skills/project-own/.env": "API_KEY=USER-SECRET\n",
                "skills/project-own/auth.github.json": '{"pat": "USER-SECRET"}\n',
            }
            for relative, body in own.items():
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(body, encoding="utf-8")

            backups = []

            def _backup(old):
                backups.append(old)
                return shutil.copytree(old, base / "bk")

            R.render_runtime(source, destination, ".claude", "V1.0.1", "claude",
                             backup_callback=_backup)

            self.assertTrue(backups, "运行包内有用户文件却没触发完整备份")
            for relative, body in own.items():
                target = destination / relative
                self.assertTrue(target.is_file(), f"重装后用户文件丢失：{relative}")
                self.assertEqual(target.read_text(encoding="utf-8"), body, relative)

            manifest = json.loads((destination / R.RUNTIME_MANIFEST).read_text(encoding="utf-8"))
            for relative in own:
                self.assertIn(relative, manifest.get("user_files", []),
                              f"用户文件应登记为 user_files：{relative}")

            # 第二轮：已登记进 manifest 之后仍须携带（走 `relative in user_files` 那一支）。
            R.render_runtime(source, destination, ".claude", "V1.0.2", "claude",
                             backup_callback=_backup)
            for relative, body in own.items():
                self.assertEqual((destination / relative).read_text(encoding="utf-8"), body,
                                 f"第二轮重装后用户文件丢失：{relative}")

    def test_pure_derivatives_stay_out_of_runtime_manifest(self):
        """阴性对照：纯派生物（`__pycache__/`、`*.pyc`）仍不得进 manifest。

        上一条把运行包的忽略口径收窄到「只排除纯派生物」。这条钉住收窄没有过头——
        否则每次跑完脚本产生的 `__pycache__` 都会被算成用户文件跨版本携带。
        """
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = make_source(base)
            destination = base / ".claude"
            R.render_runtime(source, destination, ".claude", "V1.0.0", "claude")

            cache = destination / "scripts/__pycache__"
            cache.mkdir(parents=True, exist_ok=True)
            (cache / "x.cpython-312.pyc").write_bytes(b"\x00derived")
            (destination / "scripts/y.pyc").write_bytes(b"\x00derived")

            R.render_runtime(source, destination, ".claude", "V1.0.1", "claude")

            manifest = json.loads((destination / R.RUNTIME_MANIFEST).read_text(encoding="utf-8"))
            for relative in ("scripts/__pycache__/x.cpython-312.pyc", "scripts/y.pyc"):
                self.assertNotIn(relative, manifest["files"], relative)
                self.assertNotIn(relative, manifest.get("user_files", []), relative)

    def test_project_own_entries_inside_owned_dirs_survive(self):
        """★ 受管目录**内部**的项目自有条目必须活过重装。

        运行根降到 `.claude` / `.agents` 之后，`commands/`、`skills/`、`agents/` 里会混着
        项目自有的东西（参照项目 `.claude/skills/` 的 16 个里多数是项目自有、
        `.claude/commands/` 的 21 个里也有非 AIDP 的）。原先的用户物白名单只认
        `reference/` 与 `skills/custom/`，这些一个都不覆盖 —— 重装时会被当成
        "受管但已消失"删掉。
        """
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = make_source(base)
            destination = base / ".claude"
            R.render_runtime(source, destination, ".claude", "V1.0.0", "claude")

            own = {
                "commands/project-own.md": "# 项目自有命令\n",
                "skills/project-own/SKILL.md": "---\nname: project-own\n---\n",
                "agents/project-own.md": "# 项目自有 Agent\n",
            }
            for relative, body in own.items():
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(body, encoding="utf-8")

            backups = []
            R.render_runtime(source, destination, ".claude", "V1.0.1", "claude",
                             backup_callback=lambda old: (backups.append(base / "bk"),
                                                          shutil.copytree(old, base / "bk"))[1])

            for relative, body in own.items():
                target = destination / relative
                self.assertTrue(target.is_file(), f"重装后项目自有条目丢失：{relative}")
                self.assertEqual(target.read_text(encoding="utf-8"), body, relative)

            manifest = json.loads((destination / R.RUNTIME_MANIFEST).read_text(encoding="utf-8"))
            for relative in own:
                self.assertIn(relative, manifest.get("user_files", []),
                              f"项目自有条目应登记为 user_files：{relative}")

    def test_contract_file_cannot_be_claimed_as_user_file(self):
        """⛔ 阳性对照：把契约文件谎称成 user_files 必须被拒。

        放宽用户物判定之后，光看路径已经分不出"谁的"了 —— 判据换成"真源提不提供这个文件"。
        没有这条拦截，篡改 manifest 就能让某个契约文件**跨版本被钉死**：新版内容永远盖不上去。
        """
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = make_source(base)
            runtime = base / ".agents"
            R.render_runtime(source, runtime, ".agents", "V1.0.0", "shared")
            manifest_path = runtime / R.RUNTIME_MANIFEST
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            contract_file = next(name for name in manifest["files"]
                                 if name.startswith("commands/"))
            manifest["user_files"] = [contract_file]
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            before = R.tree_digest(runtime)
            with self.assertRaises(ValueError):
                R.render_runtime(source, runtime, ".agents", "V1.0.1", "shared")
            self.assertEqual(R.tree_digest(runtime), before)

    def test_replace_failure_restores_old_runtime(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = make_source(base)
            destination = base / ".claude"
            R.render_runtime(source, destination, ".claude", "V1.0.0", "claude")
            before = R.tree_digest(destination)
            real_replace = os.replace
            calls = []

            def fail_second(src, dst):
                calls.append((Path(src), Path(dst)))
                if len(calls) == 2:
                    raise OSError("injected replace failure")
                return real_replace(src, dst)

            with self.assertRaises(OSError):
                R.render_runtime(source, destination, ".claude", "V1.0.1", "claude",
                                 replace_func=fail_second)
            self.assertEqual(R.tree_digest(destination), before)
            self.assertFalse(destination.with_name("aidp.aidp-stage").exists())

    def test_modified_runtime_requires_and_invokes_full_backup(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = make_source(base)
            destination = base / ".agents"
            R.render_runtime(source, destination, ".agents", "V1.0.0", "shared")
            (destination / "commands/sprint-dev.md").write_text("user edit\n", encoding="utf-8")
            (destination / "user-note.md").write_text("keep me\n", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                R.render_runtime(source, destination, ".agents", "V1.0.1", "shared")
            backups = []

            def backup(runtime):
                target = base / "backup"
                shutil.copytree(runtime, target)
                backups.append(target)
                return target

            R.render_runtime(source, destination, ".agents", "V1.0.1", "shared",
                             backup_callback=backup)
            self.assertEqual(len(backups), 1)
            self.assertEqual((backups[0] / "commands/sprint-dev.md").read_text(), "user edit\n")
            self.assertEqual((backups[0] / "user-note.md").read_text(), "keep me\n")

    def test_partial_or_nested_backup_is_rejected_without_changing_runtime(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = make_source(base)
            destination = base / ".agents"
            R.render_runtime(source, destination, ".agents", "V1.0.0", "shared")
            (destination / "commands/sprint-dev.md").write_text("user edit\n", encoding="utf-8")
            nested_target = destination / "nested-backup"
            nested_target.mkdir()
            (nested_target / "note.txt").write_text("not independent\n", encoding="utf-8")
            before = R.tree_digest(destination)

            callbacks = [lambda runtime: runtime]

            def empty_backup(runtime):
                target = base / "empty-backup"
                target.mkdir()
                return target
            callbacks.append(empty_backup)

            def partial_backup(runtime):
                target = base / "partial-backup"
                target.mkdir()
                (target / "one.txt").write_text("partial\n", encoding="utf-8")
                return target
            callbacks.append(partial_backup)

            def nested_backup(runtime):
                return nested_target
            callbacks.append(nested_backup)

            def wrong_mode_backup(runtime):
                target = base / "wrong-mode-backup"
                shutil.copytree(runtime, target)
                candidate = target / "commands/sprint-dev.md"
                candidate.chmod(0o600)
                return target
            callbacks.append(wrong_mode_backup)

            for callback in callbacks:
                with self.subTest(callback=callback.__name__):
                    with self.assertRaises(RuntimeError):
                        R.render_runtime(source, destination, ".agents", "V1.0.1", "shared",
                                         backup_callback=callback)
                    self.assertEqual(R.tree_digest(destination), before)

    def test_unmanaged_runtime_tree_is_rejected(self):
        """⛔ 来路不明的**同名运行包**必须拒绝接管：有受管目录却没有 manifest。

        ★ 判据不能是"目录存在即拒绝"：运行根降层后就是 `.claude` / `.agents` 本身，
        它们作为 Agent 标记目录在首次安装前**本来就存在**（里面常已有 settings.json）。
        按"存在即拒"会让 init 在任何用过 Claude Code 的项目上直接失败。
        """
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = make_source(base)
            destination = base / ".claude"
            (destination / "commands").mkdir(parents=True)
            (destination / "commands/squatter.md").write_text("squat\n", encoding="utf-8")
            (destination / "user.txt").write_text("user\n", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                R.render_runtime(source, destination, ".claude", "V1.0.0", "claude")
            self.assertEqual((destination / "user.txt").read_text(), "user\n")
            self.assertEqual((destination / "commands/squatter.md").read_text(), "squat\n")

    def test_first_install_takes_over_existing_agent_marker_dir(self):
        """阴性对照：只有 Agent 自有内容（无受管目录）的目录可以首次接管，且那些内容留存。"""
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = make_source(base)
            destination = base / ".claude"
            destination.mkdir(parents=True)
            (destination / "settings.json").write_text('{"hooks": {}}\n', encoding="utf-8")
            R.render_runtime(source, destination, ".claude", "V1.0.0", "claude")
            self.assertTrue((destination / R.RUNTIME_MANIFEST).is_file())
            self.assertEqual((destination / "settings.json").read_text(), '{"hooks": {}}\n')

    def test_symlinked_or_outside_destinations_are_rejected_without_touching_target(self):
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as outside_td:
            base, outside = Path(td), Path(outside_td)
            source = make_source(base)
            sentinel = outside / "sentinel"
            sentinel.write_text("safe\n", encoding="utf-8")
            link = base / ".claude"
            link.symlink_to(outside, target_is_directory=True)
            with self.assertRaises(RuntimeError):
                R.render_runtime(source, link / "aidp", ".claude", "V1.0.0", "claude")
            with self.assertRaises(RuntimeError):
                R.remove_tree_safely(outside, boundary=base)
            self.assertEqual(sentinel.read_text(), "safe\n")


if __name__ == "__main__":
    unittest.main()
