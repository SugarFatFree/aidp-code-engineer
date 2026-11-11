# -*- coding: utf-8 -*-
"""下游 docs/init 链接使用已安装的 Agent 运行目录。"""
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parents[2]
sys.path.insert(0, str(SCRIPTS))

import scaffold as S


class InstalledInitDocsTest(unittest.TestCase):
    def sync_tools_fixture(self, root, assets, was_aidp):
        report = S.Report()
        dirs = [d for d in S.L.skeleton_dirs(root, "V1.0.0", "alice", include_version=False)
                if d.startswith("docs/")]
        for rel in dirs:
            (root / rel).mkdir(parents=True, exist_ok=True)
        with mock.patch.object(S.L, "ASSETS", assets):
            S.sync_docs(root, was_aidp, report, S.Backup(root, report), ["claude"])
        S.ensure_nav_readmes(root, report)
        S.manage_gitkeep(root, dirs, report)
        return report

    def tools_assets(self, assets):
        target = assets / "docs/deployment/tools"
        target.mkdir(parents=True)
        (target / "README.md").write_text("模板占位，不应下发")
        (target / "本应用").mkdir()
        (target / "本应用/README.md").write_text("子索引占位，不应下发")

    def test_install_and_upgrade_do_not_seed_empty_tools(self):
        for was_aidp in (False, True):
            with self.subTest(was_aidp=was_aidp), tempfile.TemporaryDirectory() as td:
                base = Path(td)
                root, assets = base / "project", base / "assets"
                root.mkdir()
                self.tools_assets(assets)
                self.sync_tools_fixture(root, assets, was_aidp)
                self.assertTrue((root / "docs/deployment").is_dir())
                self.assertFalse((root / "docs/deployment/tools").exists())

    def test_tools_navigation_follows_actual_structure_and_existing_anchor(self):
        for layout, needed in (("flat", False), ("hub", True), ("anchor", False)):
            with self.subTest(layout=layout), tempfile.TemporaryDirectory() as td:
                base = Path(td)
                root, assets = base / "project", base / "assets"
                tools = root / "docs/deployment/tools"
                tools.mkdir(parents=True)
                self.tools_assets(assets)
                sql = tools / ("本应用/fix.sql" if layout != "flat" else "fix.sql")
                sql.parent.mkdir(parents=True, exist_ok=True)
                sql.write_text("-- existing project tool")
                if layout == "anchor":
                    (tools / "建表说明.md").write_text("现有操作入口")
                self.sync_tools_fixture(root, assets, True)
                self.assertEqual((tools / "README.md").exists(), needed)
                self.assertFalse((tools / "本应用/README.md").exists())
                self.assertEqual(sql.read_text(), "-- existing project tool")
                if needed:
                    text = (tools / "README.md").read_text()
                    self.assertIn("本应用/", text)
                    self.assertNotIn("模板占位", text)

    def test_upgrade_preserves_user_tools_index_without_queue_or_rewrite(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            root, assets = base / "project", base / "assets"
            tools = root / "docs/deployment/tools"
            tools.mkdir(parents=True)
            self.tools_assets(assets)
            existing = tools / "README.md"
            existing.write_text("用户维护的实际工具操作说明")
            before = existing.read_bytes()
            report = self.sync_tools_fixture(root, assets, True)
            self.assertEqual(existing.read_bytes(), before)
            self.assertFalse((tools / "本应用").exists())
            self.assertFalse((root / ".aidp-rewrite-queue.txt").exists())

    def test_installed_docs_render_runtime_links_for_each_layout(self):
        for home in (".claude", ".agents"):
            with self.subTest(home=home), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                source = REPO / ".aidp"
                runtime = root / home
                for kind in ("agents", "commands"):
                    (runtime / kind).mkdir(parents=True)
                    for item in (source / kind).glob("*.md"):
                        (runtime / kind / item.name).touch()
                report = S.Report()
                with mock.patch.object(S.L, "ASSETS", REPO):
                    agents = ["claude"] if home == ".claude" else ["codex"]
                    S.sync_docs(root, False, report, S.Backup(root, report), agents)
                for doc in (root / "docs/init").rglob("*.md"):
                    text = doc.read_text(encoding="utf-8")
                    self.assertNotIn("{{AIDP_HOME}}", text, str(doc))
                    self.assertNotIn("../../.aidp/", text, str(doc))
                    self.assertNotIn("python3 .aidp/scripts/", text, str(doc))
                    for href in re.findall(r"\]\(([^)#]+\.md)\)", text):
                        if href.startswith("http"):
                            continue
                        self.assertTrue((doc.parent / href).is_file(), f"{doc}: {href}")


if __name__ == "__main__":
    unittest.main()
