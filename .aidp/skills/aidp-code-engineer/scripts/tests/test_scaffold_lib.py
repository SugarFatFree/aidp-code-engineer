#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scaffold_lib / scaffold_marker / finalize_upgrade 的单元测试。"""
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import _helpers as H
import scaffold_lib as L
import scaffold_marker


class GitignoreTest(unittest.TestCase):
    TPL = f"{L.GITIGNORE_BEGIN}\n# === Node ===\nnode_modules/\ndist/\n{L.GITIGNORE_END}\n"

    def test_fresh(self):
        self.assertEqual(L.merge_gitignore(None, self.TPL), self.TPL)

    def test_adopt_existing_keeps_custom_rules(self):
        out = L.merge_gitignore("# === Node ===\nnode_modules\n\n# mine\nsecret.txt\n", self.TPL)
        self.assertTrue(out.startswith(L.GITIGNORE_BEGIN))
        self.assertIn("secret.txt", out)
        self.assertEqual(out.count("node_modules"), 1)

    def test_managed_block_replaced_outside_untouched(self):
        existing = f"top.txt\n{L.GITIGNORE_BEGIN}\nold-rule/\n{L.GITIGNORE_END}\nbottom.txt\n"
        out = L.merge_gitignore(existing, self.TPL)
        self.assertNotIn("old-rule", out)
        self.assertTrue(out.startswith("top.txt\n"))
        self.assertTrue(out.rstrip().endswith("bottom.txt"))
        self.assertEqual(L.merge_gitignore(out, self.TPL), out)


class BackupPruneTest(unittest.TestCase):
    def test_keep_last_union_days(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            now = datetime(2026, 9, 17, 12, 0, 0)
            for days in (0, 3, 20, 40):
                ts = (now - timedelta(days=days)).strftime("%Y%m%d%H%M%S")
                (root / f".aidp-backup-{ts}").mkdir()
            (root / ".aidp-backup-manual").mkdir()
            res = L.prune_backups(root, keep_last=1, keep_days=7, now=now)
            self.assertEqual(len(res["removed"]), 2)
            self.assertEqual(len(res["kept"]), 2)
            self.assertTrue((root / ".aidp-backup-manual").is_dir(), "名字不严格匹配的目录绝不删除")

    def test_disabled(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / ".aidp-backup-20200101000000").mkdir()
            self.assertTrue(L.prune_backups(Path(td), keep_last=0)["disabled"])
            self.assertTrue((Path(td) / ".aidp-backup-20200101000000").is_dir())


class UserFillableTest(unittest.TestCase):
    def test_baseline_decides(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            label = "reference/子Agent必读.md"
            old, new = b"# a\n<fill>\n", b"# a\n<fill>\n## new\n"
            self.assertEqual(L.decide_user_fillable(root, label, new, new), "uptodate")
            L.uf_record(root, label, old)
            self.assertEqual(L.decide_user_fillable(root, label, old, new), "refresh")
            self.assertEqual(L.decide_user_fillable(root, label, old + b"filled\n", new), "keep")

    def test_no_baseline_protects(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(L.decide_user_fillable(Path(td), "x", b"# a\nmine\n", b"# a\n"), "keep")
            self.assertEqual(L.decide_user_fillable(Path(td), "x", b"# a\n", b"# a\n## b\n"), "refresh")


class MemoryShapeTest(unittest.TestCase):
    def test_is_shell(self):
        self.assertTrue(L.is_shell("@AGENTS.md\n"))
        self.assertTrue(L.is_shell("# CLAUDE\n<!-- x -->\n@AGENTS.md\n"))
        self.assertFalse(L.is_shell("@AGENTS.md\n正文\n"))
        self.assertFalse(L.is_shell(""))

    def test_placeholder_render(self):
        ctx = {"project": "p", "project_cn": "项目", "user": "u", "version": "V1.0.0", "date": "2026-01-01"}
        self.assertEqual(L.render("{{project}}/{{user}}/{{version}}/{{date}}/{{project_cn}}", ctx),
                         "p/u/V1.0.0/2026-01-01/项目")


class MarkerAndFinalizeTest(unittest.TestCase):
    def test_marker_self_check(self):
        self.assertEqual(H.run_script("scaffold_marker.py", "--self-check", check=False).returncode, 0)

    def test_finalize_verifies_each_entry(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            scaffold_marker.write_version(root, "V1.0.0")
            scaffold_marker.write_pending(root, "V1.1.0")
            (root / "docs").mkdir()
            (root / "docs/README.md").write_text("# docs\n项目改过\n", encoding="utf-8")
            (root / "tpl").mkdir()
            (root / "tpl/README.md").write_text("# docs\n新骨架\n", encoding="utf-8")
            L.enqueue(root, "docs/README.md", root / "tpl/README.md")
            entry = L.parse_queue_entry(L.queue_entries(root)[0])
            self.assertEqual(entry["template"], "tpl/README.md", "队列只写仓库相对路径")
            self.assertEqual(entry["before"], L.sha256((root / "docs/README.md").read_bytes()))

            p = H.run_script("finalize_upgrade.py", "--root", root, check=False)
            self.assertEqual(p.returncode, 1, "目标未改写不得收口")
            self.assertEqual(scaffold_marker.read_version(root), "V1.0.0")

            queue_text = (root / L.REWRITE_QUEUE_FILE).read_text(encoding="utf-8")
            os.remove(root / L.REWRITE_QUEUE_FILE)
            p = H.run_script("finalize_upgrade.py", "--root", root, check=False)
            self.assertEqual(p.returncode, 1, "手工删除队列不得绕过核验")
            self.assertIn("不存在", p.stdout)

            (root / L.REWRITE_QUEUE_FILE).write_text(queue_text, encoding="utf-8")
            p = H.run_script("finalize_upgrade.py", "--root", root, "--accept", "docs/README.md", "--status", check=False)
            self.assertEqual(p.returncode, 0, p.stdout)
            self.assertEqual(scaffold_marker.read_pending(root), "V1.1.0", "--status 不写入")

            (root / "docs/README.md").write_text("# docs\n新骨架\n项目改过\n", encoding="utf-8")
            p = H.run_script("finalize_upgrade.py", "--root", root, check=False)
            self.assertEqual(p.returncode, 0, p.stdout)
            self.assertEqual(scaffold_marker.read_version(root), "V1.1.0")
            self.assertIsNone(scaffold_marker.read_pending(root))
            self.assertFalse((root / L.REWRITE_QUEUE_FILE).exists())
            ledger = json.loads((root / L.USER_FILLABLE_BASELINE).read_text(encoding="utf-8"))
            self.assertEqual(ledger["docs/README.md"], L.sha256((root / "tpl/README.md").read_bytes()),
                             "收口时台账推进到新骨架")


class MemoryMergeTest(unittest.TestCase):
    OLD = ("# p\n\n## 当前状态\n\n- **当前版本**：V0.3.0\n- **当前开发者**：bob\n- **当前 Sprint**：Sprint-007\n"
           "- **Sprint 目标**：登录\n- **整体进度**：40%\n- **最后更新**：2026-01-01\n- **当前 build**：B3\n\n---\n\n"
           "## 旧正文\n\n旧约定\n\n## 项目自定义\n\n<!-- AIDP:PROJECT-CUSTOM x -->\n- 团队约定 A\n")
    NEW = ("# p\n\n## 当前状态\n\n- **当前版本**：V0.1.0\n- **当前开发者**：t\n- **当前 Sprint**：无\n"
           "- **Sprint 目标**：-\n- **整体进度**：0%\n- **最后更新**：2026-09-17\n\n---\n\n"
           "## 新正文\n\n新约定\n\n## 项目自定义\n\n<!-- AIDP:PROJECT-CUSTOM x -->\n")

    def test_merge_keeps_status_and_custom(self):
        out = L.merge_memory_upgrade(self.OLD, self.NEW)
        for kept in ("V0.3.0", "bob", "Sprint-007", "登录", "40%", "2026-01-01", "当前 build**：B3", "团队约定 A", "新约定"):
            self.assertIn(kept, out)
        self.assertNotIn("旧约定", out)
        self.assertEqual(out.count("## 项目自定义"), 1)
        self.assertEqual(L.merge_memory_upgrade(out, self.NEW), out, "幂等")

    def test_merge_without_custom_section_uses_template(self):
        old = self.OLD.split("## 项目自定义")[0]
        out = L.merge_memory_upgrade(old, self.NEW)
        self.assertIn("<!-- AIDP:PROJECT-CUSTOM", out)
        self.assertIn("V0.3.0", out)


class TemplateGitignoreTplTest(unittest.TestCase):
    def test_root_rules_must_reach_downstream_tpl(self):
        import verify
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".gitignore").write_text("node_modules/\n/.claude/\n", encoding="utf-8")
            r = verify.VerifyResult()
            verify.check_template_gitignore_tpl(root, r)
            self.assertEqual(r.errors, [], "模板专用规则与已覆盖规则不报")
            (root / ".gitignore").write_text("node_modules/\nsecret-only-in-template/\n", encoding="utf-8")
            r = verify.VerifyResult()
            verify.check_template_gitignore_tpl(root, r)
            self.assertTrue(any("secret-only-in-template/" in e for e in r.errors), r.errors)


class HelpTest(unittest.TestCase):
    def test_help_is_help(self):
        for name in ("reverse_generate.py", "scaffold_marker.py", "verify.py", "finalize_upgrade.py", "scaffold.py"):
            p = H.run_script(name, "--help", check=False)
            self.assertEqual(p.returncode, 0, name)
            self.assertNotIn("不存在", p.stdout, name)


if __name__ == "__main__":
    unittest.main()
