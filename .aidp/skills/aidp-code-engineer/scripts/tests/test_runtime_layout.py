#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Agent 原生运行包渲染、manifest 与原子替换回归。"""
import json
import os
import shutil
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
            manifest = R.build_runtime_manifest(runtime, version="V1.2.3", source="claude")
            self.assertEqual(manifest["schema"], "aidp.runtime/v1")
            self.assertEqual(manifest["version"], "V1.2.3")
            self.assertEqual(manifest["source"], "claude")
            self.assertEqual(list(manifest["files"]), ["a.txt", "b.txt"])
            self.assertNotIn(R.RUNTIME_MANIFEST, manifest["files"])
            for digest in manifest["files"].values():
                self.assertRegex(digest, r"^[0-9a-f]{64}$")

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
