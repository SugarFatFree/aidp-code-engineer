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
    def test_installed_docs_render_runtime_links_for_each_layout(self):
        for home in (".claude/aidp", ".agents/aidp"):
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
                    agents = ["claude"] if home == ".claude/aidp" else ["codex"]
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
