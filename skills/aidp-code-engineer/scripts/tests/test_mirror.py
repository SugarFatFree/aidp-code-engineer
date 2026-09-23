#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mirror_to_bundle：在合成的模板项目上验证「镜像 → --check 归零 → 改源 → 检出漂移 → 再镜像归零」闭环。"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import _helpers as H
import scaffold_lib as L
from test_sync_memory_md import SAMPLE

MEMORY_README = """# memory

<!-- TEMPLATE-ONLY:BEGIN MEMORY_TREE -->
模板目录树
<!-- TEMPLATE-ONLY:END -->

`_facts/` 事实清单
"""
CONFIG = """project:
  name: tpl
  name_cn: 模板

scaffold:
  version: null
  pending: null
"""


def make_template(root: Path):
    (root / ".aidp/commands").mkdir(parents=True)
    (root / ".aidp/commands/sprint-dev.md").write_text("# dev\n", encoding="utf-8")
    (root / ".aidp/scripts/__pycache__").mkdir(parents=True)
    (root / ".aidp/scripts/tool.py").write_text("print(1)\n", encoding="utf-8")
    (root / ".aidp/scripts/__pycache__/tool.cpython-312.pyc").write_bytes(b"x")
    (root / ".aidp/scripts/tests").mkdir()
    (root / ".aidp/scripts/tests/test_tool.py").write_text("pass\n", encoding="utf-8")
    (root / ".aidp/scripts/design-goals-baseline.txt").write_text("baseline\n", encoding="utf-8")
    (root / ".aidp/skills/demo").mkdir(parents=True)
    (root / ".aidp/skills/demo/SKILL.md").write_text("---\nname: demo\n---\n", encoding="utf-8")
    (root / ".aidp/skills/demo/config.json").write_text('{"token": "secret"}', encoding="utf-8")
    (root / ".aidp/skills/demo/auth.alice.json").write_text("{}", encoding="utf-8")
    # 遗留下游形态：`.aidp/skills/` 下若残留同名脚手架副本，镜像必须跳过它（不得镜像自身）
    (root / ".aidp/skills/aidp-code-engineer").mkdir(parents=True)
    (root / ".aidp/skills/aidp-code-engineer/SKILL.md").write_text("legacy\n", encoding="utf-8")
    skill = root / "skills/aidp-code-engineer"
    shutil.copytree(H.SCRIPTS, skill / "scripts", ignore=shutil.ignore_patterns("__pycache__", "tests"))
    (skill / "SKILL.md").write_text("---\nname: aidp-code-engineer\n---\n", encoding="utf-8")
    (skill / "sources/root").mkdir(parents=True)
    for name in ("gitignore.tpl", "README.md.tpl", "env.tpl"):
        (skill / "sources/root" / name).write_text(f"{name}\n", encoding="utf-8")
    (skill / "sources/memory").mkdir(parents=True)
    for tpl, _ in L.MEMORY_TEMPLATES:
        (skill / "sources/memory" / tpl).write_text("# {{project}}\n", encoding="utf-8")
    (root / "docs/init").mkdir(parents=True)
    (root / "docs/init/README.md").write_text("# init\n", encoding="utf-8")
    (root / "docs/README.md").write_text("# docs\n", encoding="utf-8")
    (root / "docs/requirements/V0.1.0").mkdir(parents=True)
    (root / "docs/requirements/V0.1.0/README.md").write_text("版本产出\n", encoding="utf-8")
    (root / "memory").mkdir()
    (root / "memory/README.md").write_text(MEMORY_README, encoding="utf-8")
    (root / "memory/aidp-config.yaml").write_text(CONFIG, encoding="utf-8")
    (root / "AGENTS.md").write_text("# tpl — 模板仓库维护记忆\n", encoding="utf-8")
    (root / ".aidp/AIDP-AGENTS.md").write_text(SAMPLE, encoding="utf-8")
    (root / "版本变更历史.md").write_text("## 当前范式版本\n\n**AIDP V2.3.4**（最后更新：2026-01-01）\n", encoding="utf-8")
    return skill


class MirrorLoopTest(unittest.TestCase):
    def test_loop(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skill = make_template(root)
            mirror = skill / "scripts/mirror_to_bundle.py"

            def run(*args):
                import subprocess
                import sys
                return subprocess.run([sys.executable, str(mirror), "--root", str(root), *args],
                                      capture_output=True, text=True)

            self.assertEqual(run("--check").returncode, 1, "空 bundle 必须报漂移")
            self.assertEqual(run().returncode, 0)
            p = run("--check")
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

            a = skill / "assets"
            self.assertEqual((a / "SCAFFOLD_VERSION").read_text().strip(), "V2.3.4")
            self.assertTrue((a / "aidp/commands/sprint-dev.md").is_file())
            self.assertTrue((a / "aidp/skills/demo/SKILL.md").is_file())
            self.assertFalse((a / "aidp/skills/demo/config.json").exists(), "凭证不得进 bundle")
            self.assertFalse((a / "aidp/skills/demo/auth.alice.json").exists(), "凭证不得进 bundle")
            self.assertFalse((a / "aidp/scripts/__pycache__").exists())
            self.assertFalse((a / "aidp/skills/aidp-code-engineer").exists(), "脚手架不得镜像自身")
            self.assertFalse((skill / "references/init").exists(), "docs/init 只镜像一份到 assets/docs/init")
            self.assertFalse((a / "aidp/scripts/tests").exists(), "模板回归单测不下发")
            self.assertFalse((a / "aidp/scripts/design-goals-baseline.txt").exists(), "设计目标 baseline 不下发")
            self.assertFalse((a / "aidp/skills/aidp-cmd").exists(), "命令路由不进入 bundle")
            self.assertFalse(hasattr(L, "FINGERPRINT_EXEMPT"), "原生命令不需要路由指纹豁免常量")
            self.assertFalse(hasattr(L, "is_fingerprint_exempt"), "原生命令不需要路由指纹豁免辅助函数")
            self.assertTrue((a / "docs/init/README.md").is_file())
            self.assertFalse((a / "docs/requirements/V0.1.0").exists(), "版本目录不进 bundle")
            self.assertIn("{{project}}", (a / "aidp-config.yaml.tpl").read_text())
            self.assertNotIn("模板目录树", (a / "memory/README.md").read_text())
            self.assertIn("{{project}}", (a / "AGENTS.md.tpl").read_text())
            manifest = json.loads((a / "CONTRACT_MANIFEST.json").read_text())
            self.assertEqual(manifest["scaffold_version"], "V2.3.4")
            self.assertIn("commands/sprint-dev.md", manifest["files"])
            self.assertNotIn("scripts/tool.py", manifest["files"], "scripts 不受版本门控，不进指纹")
            self.assertFalse(any(k.startswith("skills/aidp-cmd/") for k in manifest["files"]),
                             "原生命令适配不应保留路由指纹")
            self.assertEqual((a / "root/gitignore.tpl").read_text(), "gitignore.tpl\n", "根文件模板由 sources/ 派生")
            self.assertTrue((a / "memory/projectBrief.md.tpl").is_file(), "memory 模板由 sources/ 派生")

            (root / ".aidp/commands/sprint-dev.md").write_text("# dev v2\n", encoding="utf-8")
            (root / ".aidp/commands/new.md").write_text("# new\n", encoding="utf-8")
            (a / "aidp/commands/retired.md").write_text("old\n", encoding="utf-8")
            (a / "root/stray.tpl").write_text("?\n", encoding="utf-8")
            p = run("--check", "--json")
            self.assertEqual(p.returncode, 1)
            data = json.loads(p.stdout)
            self.assertIn("assets/aidp/commands/new.md", data["create"])
            self.assertIn("assets/aidp/commands/sprint-dev.md", data["update"])
            self.assertIn("assets/aidp/commands/retired.md", data["delete"])
            self.assertIn("assets/root/stray.tpl", data["delete"])
            (skill / "sources/root/env.tpl").write_text("A=1\n", encoding="utf-8")
            self.assertIn("assets/root/env.tpl", json.loads(run("--check", "--json").stdout)["update"], "改真源即检出漂移")
            self.assertEqual(run().returncode, 0)
            self.assertEqual(run("--check").returncode, 0)
            self.assertFalse((a / "aidp/commands/retired.md").exists())


if __name__ == "__main__":
    unittest.main()
