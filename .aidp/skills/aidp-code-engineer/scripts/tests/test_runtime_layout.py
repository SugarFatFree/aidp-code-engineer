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
    (source / "skills/demo/SKILL.md").parent.mkdir(parents=True)
    (source / "skills/demo/SKILL.md").write_text("read {{AIDP_HOME}}/reference/x.md\n", encoding="utf-8")
    (source / "plugins/chrome/skills/demo/SKILL.md").parent.mkdir(parents=True)
    (source / "plugins/chrome/skills/demo/SKILL.md").write_text("plugin\n", encoding="utf-8")
    (source / "scripts/blob.bin").write_bytes(b"\xff\x00{{AIDP_HOME}}")
    (source / "skills/aidp-code-engineer/SKILL.md").parent.mkdir(parents=True)
    (source / "skills/aidp-code-engineer/SKILL.md").write_text("self\n", encoding="utf-8")
    (source / "scripts/tests/test_x.py").parent.mkdir(parents=True)
    (source / "scripts/tests/test_x.py").write_text("pass\n", encoding="utf-8")
    (source / "scripts/design-goals-baseline.txt").write_text("baseline\n", encoding="utf-8")
    (source / "scripts/__pycache__/x.pyc").parent.mkdir(parents=True)
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
            R.render_tree(source, target, ".claude/aidp")
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
        self.assertEqual(R.render_text(TEXT, ".claude/aidp"), "run=.claude/aidp/scripts/tool.py\n")
        self.assertEqual(R.render_text(TEXT, ".agents/aidp"), "run=.agents/aidp/scripts/tool.py\n")
        for invalid in (
            "{{UNKNOWN_TOKEN}}\n",
            "python3 .aidp/scripts/tool.py\n",
            "read /iflytek/workspace/private/.aidp/x\n",
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    R.render_text(invalid, ".claude/aidp")
        self.assertIn("LEGACY_AIDP_DIR", R.render_text('LEGACY_AIDP_DIR = ".aidp"\n', ".claude/aidp"))

    def test_source_requires_every_real_runtime_directory(self):
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as outside_td:
            base = Path(td)
            source = make_source(base)
            shutil.rmtree(source / "flows")
            with self.assertRaises(RuntimeError):
                R.render_tree(source, base / "missing-output", ".claude/aidp")

            source = make_source(base / "second")
            shutil.rmtree(source / "rules")
            Path(source / "rules").symlink_to(Path(outside_td), target_is_directory=True)
            with self.assertRaises(RuntimeError):
                R.render_tree(source, base / "symlink-output", ".agents/aidp")

    def test_legacy_constant_does_not_exempt_an_illegal_runtime_path_on_same_line(self):
        self.assertEqual(
            R.render_text('LEGACY_AIDP_DIR = ".aidp"\n', ".claude/aidp"),
            'LEGACY_AIDP_DIR = ".aidp"\n',
        )
        with self.assertRaises(ValueError):
            R.render_text(
                'LEGACY_AIDP_DIR = ".aidp"; command = ".aidp/scripts/tool.py"\n',
                ".claude/aidp",
            )

    def test_templates_must_use_runtime_token_instead_of_hardcoded_homes(self):
        self.assertEqual(
            R.render_text("run={{AIDP_HOME}}/scripts/x.py\n", ".claude/aidp"),
            "run=.claude/aidp/scripts/x.py\n",
        )
        self.assertEqual(
            R.render_text("run={{AIDP_HOME}}/scripts/x.py\n", ".agents/aidp"),
            "run=.agents/aidp/scripts/x.py\n",
        )
        for text, home in (
            ("run=.claude/aidp/scripts/x.py\n", ".claude/aidp"),
            ("run=.agents/aidp/scripts/x.py\n", ".agents/aidp"),
            ("run=.agents/aidp/scripts/x.py\n", ".claude/aidp"),
            ("run=.claude/aidp/scripts/x.py\n", ".agents/aidp"),
        ):
            with self.subTest(text=text, home=home):
                with self.assertRaises(ValueError):
                    R.render_text(text, home)

    def test_render_rejects_template_root_leaks_but_allows_generic_absolute_paths(self):
        posix_root = "/workspace/template"
        windows_root = r"C:\workspace\template"
        with self.assertRaises(ValueError):
            R.render_text("read /workspace/template/.hidden/file.md\n", ".claude/aidp",
                          template_root=posix_root)
        with self.assertRaises(ValueError):
            R.render_text(r"read C:\workspace\template\rules\x.md" + "\n", ".agents/aidp",
                          template_root=windows_root)
        self.assertEqual(
            R.render_text("#!/usr/bin/env python3\npath=C:/Windows/System32\n", ".claude/aidp",
                          template_root=posix_root),
            "#!/usr/bin/env python3\npath=C:/Windows/System32\n",
        )

    def test_runtime_path_ignore_only_exempts_template_root_on_that_line(self):
        root = "/workspace/template"
        text = (
            "example=/workspace/template/demo  # runtime-path-ignore: 文档示例\n"
            "generic=/usr/bin/env\n"
        )
        self.assertEqual(R.render_text(text, ".claude/aidp", template_root=root), text)
        with self.assertRaises(ValueError):
            R.render_text(
                "bad=.aidp/scripts/x  # runtime-path-ignore: 不得豁免旧路径\n",
                ".claude/aidp", template_root=root,
            )
        with self.assertRaises(ValueError):
            R.render_text(
                "bad={{UNKNOWN_TOKEN}}  # runtime-path-ignore: 不得豁免 token\n",
                ".claude/aidp", template_root=root,
            )
        with self.assertRaises(ValueError):
            R.render_text(
                "one=/workspace/template/a  # runtime-path-ignore: 示例\n"
                "two=/workspace/template/b\n",
                ".claude/aidp", template_root=root,
            )

    def test_binary_is_copied_without_text_substitution(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = make_source(base)
            target = base / "rendered"
            R.render_tree(source, target, ".agents/aidp")
            self.assertEqual((target / "scripts/blob.bin").read_bytes(), b"\xff\x00{{AIDP_HOME}}")


class ManifestContractTest(RuntimeLayoutTestCase):
    def test_manifest_is_deterministic_sorted_and_excludes_itself(self):
        with tempfile.TemporaryDirectory() as td:
            runtime = Path(td) / "aidp"
            runtime.mkdir()
            (runtime / "b.txt").write_text("b\n", encoding="utf-8")
            (runtime / "a.txt").write_text("a\n", encoding="utf-8")
            manifest = R.build_runtime_manifest(
                runtime, version="V1.2.3", source="claude", home=".claude/aidp")
            self.assertEqual(manifest["schema"], "aidp.runtime/v1")
            self.assertEqual(manifest["version"], "V1.2.3")
            self.assertEqual(manifest["source"], "claude")
            self.assertEqual(list(manifest["files"]), ["a.txt", "b.txt"])
            self.assertNotIn(R.RUNTIME_MANIFEST, manifest["files"])
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
                            runtime, version=version, source="claude", home=".claude/aidp")

            source = make_source(Path(td) / "source-fixture")
            installed = Path(td) / ".claude/aidp"
            R.render_runtime(source, installed, ".claude/aidp", "V1.2.3", "claude")
            for version in (None, "", 1, "1.2.3", "V1.2"):
                manifest = json.loads((installed / R.RUNTIME_MANIFEST).read_text(encoding="utf-8"))
                manifest["version"] = version
                (installed / R.RUNTIME_MANIFEST).write_text(
                    json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
                with self.subTest(validate_version=version):
                    with self.assertRaises(ValueError):
                        R.validate_runtime(installed, expected_home=".claude/aidp")
            R.render_runtime(source, installed, ".claude/aidp", "V1.2.3", "claude")

    def test_source_and_home_mapping_is_enforced_at_every_layer(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = make_source(base)
            runtime = base / "runtime"
            R.render_tree(source, runtime, ".claude/aidp")
            with self.assertRaises(ValueError):
                R.build_runtime_manifest(runtime, version="V1.0.0", source="claude",
                                         home=".agents/aidp")
            with self.assertRaises(ValueError):
                R.build_runtime_manifest(runtime, version="V1.0.0", source="shared",
                                         home=".claude/aidp")
            with self.assertRaises(ValueError):
                R.render_runtime(source, base / ".claude/aidp", ".agents/aidp",
                                 "V1.0.0", "claude")
            with self.assertRaises(ValueError):
                R.render_runtime(source, base / ".agents/aidp", ".claude/aidp",
                                 "V1.0.0", "shared")
            manifest = R.build_runtime_manifest(
                runtime, version="V1.0.0", source="claude", home=".claude/aidp")
            (runtime / R.RUNTIME_MANIFEST).write_text(
                json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            with self.assertRaises(ValueError):
                R.validate_runtime(runtime, expected_home=".agents/aidp")

    def test_validate_allows_expected_home_and_rejects_other_home_or_token_even_if_rehashed(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = make_source(base)
            runtime = base / ".claude/aidp"
            R.render_runtime(source, runtime, ".claude/aidp", "V1.0.0", "claude")
            R.validate_runtime(runtime, expected_home=".claude/aidp")
            command = runtime / "commands/sprint-dev.md"
            for illegal in (
                "run=.agents/aidp/scripts/x.py\n",
                "run={{AIDP_HOME}}/scripts/x.py\n",
                "run=.aidp/scripts/x.py\n",
            ):
                command.write_text(illegal, encoding="utf-8")
                manifest = R.build_runtime_manifest(
                    runtime, version="V1.0.0", source="claude", home=".claude/aidp")
                (runtime / R.RUNTIME_MANIFEST).write_text(
                    json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
                with self.subTest(illegal=illegal):
                    with self.assertRaises(ValueError):
                        R.validate_runtime(runtime, expected_home=".claude/aidp")
            R.render_runtime(source, runtime, ".claude/aidp", "V1.0.0", "claude")

    def test_mode_is_manifested_and_permission_drift_is_detected(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = make_source(base)
            tool = source / "scripts/sample.txt"
            tool.chmod(0o755)
            claude = base / ".claude/aidp"
            shared = base / ".agents/aidp"
            R.render_runtime(source, claude, ".claude/aidp", "V1.0.0", "claude")
            R.render_runtime(source, shared, ".agents/aidp", "V1.0.0", "shared")
            manifest = json.loads((claude / R.RUNTIME_MANIFEST).read_text(encoding="utf-8"))
            self.assertEqual(manifest["files"]["scripts/sample.txt"]["mode"], "0755")
            self.assertEqual(stat.S_IMODE((claude / "scripts/sample.txt").stat().st_mode), 0o755)
            self.assertEqual(R.normalize_runtime(claude, ".claude/aidp"),
                             R.normalize_runtime(shared, ".agents/aidp"))

            (shared / "scripts/sample.txt").chmod(0o644)
            with self.assertRaises(ValueError):
                R.validate_runtime(shared, expected_home=".agents/aidp")
            self.assertNotEqual(R.normalize_runtime(claude, ".claude/aidp"),
                                R.normalize_runtime(shared, ".agents/aidp"))
            self.assertNotEqual(R.tree_digest(claude), R.tree_digest(shared))

    def test_validate_rejects_missing_required_directory_even_with_matching_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = make_source(base)
            runtime = base / ".claude/aidp"
            R.render_runtime(source, runtime, ".claude/aidp", "V1.0.0", "claude")
            shutil.rmtree(runtime / "agents")
            manifest = json.loads((runtime / R.RUNTIME_MANIFEST).read_text(encoding="utf-8"))
            manifest["files"] = {
                relative: digest for relative, digest in manifest["files"].items()
                if not relative.startswith("agents/")
            }
            (runtime / R.RUNTIME_MANIFEST).write_text(
                json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            with self.assertRaises(ValueError):
                R.validate_runtime(runtime, expected_home=".claude/aidp")

    def test_validate_detects_tampering_and_normalize_compares_homes(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = make_source(base)
            claude = base / ".claude/aidp"
            shared = base / ".agents/aidp"
            R.render_runtime(source, claude, ".claude/aidp", "V1.0.0", "claude")
            R.render_runtime(source, shared, ".agents/aidp", "V1.0.0", "shared")
            R.validate_runtime(claude, expected_home=".claude/aidp")
            R.validate_runtime(shared, expected_home=".agents/aidp")
            self.assertEqual(R.normalize_runtime(claude, ".claude/aidp"),
                             R.normalize_runtime(shared, ".agents/aidp"))
            (shared / "commands/sprint-dev.md").write_text("drift\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                R.validate_runtime(shared, expected_home=".agents/aidp")
            self.assertNotEqual(R.normalize_runtime(claude, ".claude/aidp"),
                                R.normalize_runtime(shared, ".agents/aidp"))


class AtomicInstallTest(RuntimeLayoutTestCase):
    def test_replaces_existing_valid_runtime_atomically(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = make_source(base)
            destination = base / ".claude/aidp"
            R.render_runtime(source, destination, ".claude/aidp", "V1.0.0", "claude")
            (source / "commands/sprint-dev.md").write_text("new {{AIDP_HOME}}\n", encoding="utf-8")
            R.render_runtime(source, destination, ".claude/aidp", "V1.0.1", "claude")
            manifest = json.loads((destination / R.RUNTIME_MANIFEST).read_text(encoding="utf-8"))
            self.assertEqual(manifest["version"], "V1.0.1")
            self.assertIn("new .claude/aidp", (destination / "commands/sprint-dev.md").read_text())
            self.assertFalse(destination.with_name("aidp.aidp-stage").exists())
            self.assertFalse(destination.with_name("aidp.aidp-previous").exists())

    def test_stale_lock_file_is_reusable_and_persists_after_release(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = make_source(base)
            destination = base / ".claude/aidp"
            lock = destination.parent / ".aidp-runtime.lock"
            lock.parent.mkdir(parents=True)
            lock.write_text("stale-owner\n", encoding="utf-8")
            R.render_runtime(source, destination, ".claude/aidp", "V1.0.0", "claude")
            self.assertTrue(lock.is_file())
            self.assertGreaterEqual(lock.stat().st_size, 1)
            R.render_runtime(source, destination, ".claude/aidp", "V1.0.1", "claude")

    def test_active_lock_in_independent_process_rejects_then_releases(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = make_source(base)
            destination = base / ".agents/aidp"
            destination.parent.mkdir(parents=True)
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
                    R.render_runtime(source, destination, ".agents/aidp", "V1.0.0", "shared")
                self.assertFalse(destination.exists())
            finally:
                process.terminate()
                process.communicate(timeout=10)
            R.render_runtime(source, destination, ".agents/aidp", "V1.0.0", "shared")
            self.assertTrue((destination.parent / ".aidp-runtime.lock").is_file())

    def test_invalid_lock_symlink_or_directory_is_rejected_and_preserved(self):
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as outside_td:
            base, outside = Path(td), Path(outside_td)
            source = make_source(base)
            destination = base / ".claude/aidp"
            destination.parent.mkdir(parents=True)
            lock = destination.parent / ".aidp-runtime.lock"
            sentinel = outside / "sentinel"
            sentinel.write_text("safe\n", encoding="utf-8")
            lock.symlink_to(sentinel)
            with self.assertRaises(RuntimeError):
                R.render_runtime(source, destination, ".claude/aidp", "V1.0.0", "claude")
            self.assertTrue(lock.is_symlink())
            self.assertEqual(sentinel.read_text(), "safe\n")

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = make_source(base)
            destination = base / ".claude/aidp"
            lock = destination.parent / ".aidp-runtime.lock"
            lock.mkdir(parents=True)
            with self.assertRaises(RuntimeError):
                R.render_runtime(source, destination, ".claude/aidp", "V1.0.0", "claude")
            self.assertTrue(lock.is_dir())

    def test_backup_callback_modification_after_copy_aborts_and_preserves_second_edit(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = make_source(base)
            destination = base / ".agents/aidp"
            R.render_runtime(source, destination, ".agents/aidp", "V1.0.0", "shared")
            command = destination / "commands/sprint-dev.md"
            command.write_text("first user edit\n", encoding="utf-8")

            def backup_then_modify(runtime):
                target = base / "race-backup"
                shutil.copytree(runtime, target)
                command.write_text("second concurrent edit\n", encoding="utf-8")
                return target

            with self.assertRaises(RuntimeError):
                R.render_runtime(source, destination, ".agents/aidp", "V1.0.1", "shared",
                                 backup_callback=backup_then_modify)
            self.assertEqual(command.read_text(), "second concurrent edit\n")
            self.assertTrue((destination.parent / ".aidp-runtime.lock").is_file())

    def test_preexisting_fixed_transaction_names_are_never_touched(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = make_source(base)
            destination = base / ".claude/aidp"
            fixed_stage = destination.with_name("aidp.aidp-stage")
            fixed_previous = destination.with_name("aidp.aidp-previous")
            fixed_stage.mkdir(parents=True)
            fixed_previous.mkdir(parents=True)
            (fixed_stage / "user.txt").write_text("stage-user\n", encoding="utf-8")
            (fixed_previous / "user.txt").write_text("previous-user\n", encoding="utf-8")
            R.render_runtime(source, destination, ".claude/aidp", "V1.0.0", "claude")
            self.assertEqual((fixed_stage / "user.txt").read_text(), "stage-user\n")
            self.assertEqual((fixed_previous / "user.txt").read_text(), "previous-user\n")

    def test_render_failure_keeps_old_runtime(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = make_source(base)
            destination = base / ".agents/aidp"
            R.render_runtime(source, destination, ".agents/aidp", "V1.0.0", "shared")
            before = R.tree_digest(destination)
            (source / "commands/sprint-dev.md").write_text("{{UNKNOWN_TOKEN}}\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                R.render_runtime(source, destination, ".agents/aidp", "V1.0.1", "shared")
            self.assertEqual(R.tree_digest(destination), before)

    def test_replace_failure_restores_old_runtime(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = make_source(base)
            destination = base / ".claude/aidp"
            R.render_runtime(source, destination, ".claude/aidp", "V1.0.0", "claude")
            before = R.tree_digest(destination)
            real_replace = os.replace
            calls = []

            def fail_second(src, dst):
                calls.append((Path(src), Path(dst)))
                if len(calls) == 2:
                    raise OSError("injected replace failure")
                return real_replace(src, dst)

            with self.assertRaises(OSError):
                R.render_runtime(source, destination, ".claude/aidp", "V1.0.1", "claude",
                                 replace_func=fail_second)
            self.assertEqual(R.tree_digest(destination), before)
            self.assertFalse(destination.with_name("aidp.aidp-stage").exists())

    def test_modified_runtime_requires_and_invokes_full_backup(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = make_source(base)
            destination = base / ".agents/aidp"
            R.render_runtime(source, destination, ".agents/aidp", "V1.0.0", "shared")
            (destination / "commands/sprint-dev.md").write_text("user edit\n", encoding="utf-8")
            (destination / "user-note.md").write_text("keep me\n", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                R.render_runtime(source, destination, ".agents/aidp", "V1.0.1", "shared")
            backups = []

            def backup(runtime):
                target = base / "backup"
                shutil.copytree(runtime, target)
                backups.append(target)
                return target

            R.render_runtime(source, destination, ".agents/aidp", "V1.0.1", "shared",
                             backup_callback=backup)
            self.assertEqual(len(backups), 1)
            self.assertEqual((backups[0] / "commands/sprint-dev.md").read_text(), "user edit\n")
            self.assertEqual((backups[0] / "user-note.md").read_text(), "keep me\n")

    def test_partial_or_nested_backup_is_rejected_without_changing_runtime(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = make_source(base)
            destination = base / ".agents/aidp"
            R.render_runtime(source, destination, ".agents/aidp", "V1.0.0", "shared")
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
                        R.render_runtime(source, destination, ".agents/aidp", "V1.0.1", "shared",
                                         backup_callback=callback)
                    self.assertEqual(R.tree_digest(destination), before)

    def test_existing_directory_without_manifest_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = make_source(base)
            destination = base / ".claude/aidp"
            destination.mkdir(parents=True)
            (destination / "user.txt").write_text("user\n", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                R.render_runtime(source, destination, ".claude/aidp", "V1.0.0", "claude")
            self.assertEqual((destination / "user.txt").read_text(), "user\n")

    def test_symlinked_or_outside_destinations_are_rejected_without_touching_target(self):
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as outside_td:
            base, outside = Path(td), Path(outside_td)
            source = make_source(base)
            sentinel = outside / "sentinel"
            sentinel.write_text("safe\n", encoding="utf-8")
            link = base / ".claude"
            link.symlink_to(outside, target_is_directory=True)
            with self.assertRaises(RuntimeError):
                R.render_runtime(source, link / "aidp", ".claude/aidp", "V1.0.0", "claude")
            with self.assertRaises(RuntimeError):
                R.remove_tree_safely(outside, boundary=base)
            self.assertEqual(sentinel.read_text(), "safe\n")


if __name__ == "__main__":
    unittest.main()
