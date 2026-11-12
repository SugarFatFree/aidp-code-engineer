#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sync_memory_md：下发记忆源 `.aidp/AIDP-AGENTS.md` → 下游记忆文件模板（结构校验 + 原样复制）。"""
import unittest
import re
import sys
import tempfile
from pathlib import Path

import _helpers as H
import scaffold_lib as L
import sync_memory_md as S

SAMPLE = """<!--
  {{project}} 项目记忆正文
-->

# {{project}}

**{{project}}** 基于 AIDP 范式。

## 当前状态

- **当前版本**：{{version}}
- **当前开发者**：{{user}}
- **当前 Sprint**：无活跃 Sprint（项目初始化阶段）
- **最后更新**：{{date}}

## 核心约定

1. **约定一**：内容。

---

## 项目自定义

<!-- AIDP:PROJECT-CUSTOM 本段由项目团队维护 -->
"""


class RenderTest(unittest.TestCase):
    def test_sample_copied_verbatim(self):
        self.assertEqual(S.render_downstream(SAMPLE), SAMPLE)

    def test_missing_anchor_raises(self):
        for anchor in ("- **当前版本**：{{version}}\n", "## 核心约定\n", "## 项目自定义\n"):
            with self.assertRaises(S.TemplateShapeError, msg=anchor):
                S.render_downstream(SAMPLE.replace(anchor, ""))

    def test_template_maintenance_content_rejected(self):
        """模板仓库自身的维护内容混进下发源 → 拒绝（它们只该在根 AGENTS.md）。"""
        for leak in ("<!-- TEMPLATE-ONLY:BEGIN X -->", "## 模板项目维护特例", "### 范式版本号自增策略"):
            with self.assertRaises(S.TemplateShapeError, msg=leak):
                S.render_downstream(SAMPLE + leak + "\n")

    def test_real_source_renders_clean(self):
        out = S.build(H.REPO)
        ctx = {"project": "demo", "project_cn": "演示", "user": "tester", "version": "V0.1.0", "date": "2026-01-01"}
        rendered = L.render(out, ctx)
        unresolved = rendered.replace("{{AIDP_HOME}}", "")
        self.assertNotIn("{{", unresolved)
        self.assertIn("{{AIDP_HOME}}", rendered)
        self.assertIn("# demo", rendered)
        self.assertIn("- **当前版本**：V0.1.0", rendered)
        self.assertTrue(L.looks_like_aidp_body(rendered))
        self.assertIn(L.CUSTOM_HEADING, rendered)

    def test_template_own_memory_not_distributed(self):
        """根 AGENTS.md（模板自身维护记忆）的内容不得出现在下发模板里。"""
        own = (H.REPO / "AGENTS.md").read_text(encoding="utf-8") if hasattr(H.REPO, "joinpath") \
            else open(f"{H.REPO}/AGENTS.md", encoding="utf-8").read()
        self.assertNotIn("## 核心约定", own)
        tpl = S.build(H.REPO)
        self.assertNotIn("模板仓库维护记忆", tpl)
        self.assertNotIn("范式版本号自增铁律", tpl)

    def test_bundle_tpl_in_sync(self):
        p = H.run_script("sync_memory_md.py", "--check", "--root", H.REPO, check=False)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)


class CompactMemoryTest(unittest.TestCase):
    def test_resident_budget_and_external_numbering(self):
        resident = S.build(H.REPO)
        self.assertLessEqual(len(resident.encode("utf-8")), 8192)
        self.assertIn("reference/light-entry.md", resident)
        self.assertIn("reference/core-conventions.md", resident)
        self.assertNotRegex(resident, r"(?m)^\d+\. \*\*")
        core = (H.REPO / ".aidp/reference/core-conventions.md").read_text(encoding="utf-8")
        self.assertEqual([int(n) for n in re.findall(r"(?m)^(\d+)\. \*\*", core)], list(range(1, 42)))
        routing = (H.REPO / ".aidp/reference/task-routing.md").read_text(encoding="utf-8")
        for skill in (H.REPO / ".aidp/skills").iterdir():
            if (skill / "SKILL.md").is_file():
                self.assertIn(f"`{skill.name}`", routing)

    def test_external_reference_missing_or_number_gap_blocks_sync(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / S.SOURCE_REL
            source.parent.mkdir(parents=True)
            source.write_text(SAMPLE.replace("1. **约定一**：内容。", "见 `{{AIDP_HOME}}/reference/core-conventions.md`。"))
            with self.assertRaises(S.TemplateShapeError):
                S.build(root)
            ref = root / ".aidp/reference/core-conventions.md"
            ref.parent.mkdir()
            ref.write_text("## 核心约定\n1. **第一条**：示例。\n3. **第三条**：示例。\n")
            with self.assertRaises(S.TemplateShapeError):
                S.build(root)

    def test_loss_guard_tracks_relocated_sections_but_still_protects_custom(self):
        sys.path.insert(0, str(H.REPO / ".aidp/scripts"))
        import check_memory_loss as loss
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ref = root / ".claude/reference"
            ref.mkdir(parents=True)
            old = ("## 当前状态\n- **当前版本**：V0.9.0\n\n## 核心约定（必须遵守）\n"
                   + "\n".join(f"{n}. **规则{n}**：保留正文。" for n in range(1, 12))
                   + "\n\n## 项目自定义\n### 联调记录\n手写内容。\n")
            main = root / "CLAUDE.md"
            main.write_text(old)
            loss.take_snapshot(td, files=["CLAUDE.md"])
            core = old[old.index("## 核心约定"):old.index("## 项目自定义")]
            (ref / "core-conventions.md").write_text(core)
            new = old.replace(core, "## 核心约定\n见 `.claude/reference/core-conventions.md`。\n\n")
            main.write_text(new)
            self.assertFalse(loss.run(td, files=["CLAUDE.md"])["errors"])
            main.write_text(new.replace("### 联调记录\n手写内容。", ""))
            self.assertTrue(loss.run(td, files=["CLAUDE.md"])["errors"])
            main.write_text(new)
            (ref / "core-conventions.md").unlink()
            self.assertTrue(loss.run(td, files=["CLAUDE.md"])["errors"])

    def test_loss_guard_protects_external_sources_after_migration(self):
        sys.path.insert(0, str(H.REPO / ".aidp/scripts"))
        import check_memory_loss as loss
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ref = root / ".agents/reference/core-conventions.md"
            ref.parent.mkdir(parents=True)
            ref.write_text("## 核心约定\n1. **甲**：规则。\n")
            self.assertIn(".agents/reference/core-conventions.md", loss.protected_files(td))
            loss.take_snapshot(td)
            ref.unlink()
            self.assertTrue(loss.run(td)["errors"])

    def test_verify_counts_external_conventions(self):
        import verify
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ref = root / ".agents/reference"
            ref.mkdir(parents=True)
            (ref / "core-conventions.md").write_text("## 核心约定\n1. **甲**\n2. **乙**\n")
            (root / "AGENTS.md").write_text("核心约定 1–3\n")
            result = verify.VerifyResult()
            verify.check_convention_anchor_consistency(root, result)
            self.assertTrue(result.warnings, result.to_dict() if hasattr(result, "to_dict") else result.__dict__)

    def test_native_runtime_guards_use_external_truth(self):
        sys.path.insert(0, str(H.REPO / ".aidp/scripts"))
        import check_count_claims as counts
        import check_convention_dup as dup
        for home in (".aidp", ".claude", ".agents"):
            with self.subTest(home=home), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                ref = root / home / "reference"
                ref.mkdir(parents=True)
                main = "1. **规则一**：完整正文。\n2. **规则二**：另一个正文。\n"
                (ref / "core-conventions.md").write_text("## 核心约定\n" + main)
                (ref / "约定细则-1.md").write_text("### 约定 1\n**规则一**：完整正文。\n")
                (root / "AGENTS.md").write_text("## 核心约定\n见 reference/core-conventions.md。\n")
                self.assertEqual(counts.truth_max_convention(str(root)), 2)
                result = dup.run(str(root))
                self.assertTrue(result["applicable"], result)
                self.assertEqual(result["main_file"], f"{home}/reference/core-conventions.md")
                self.assertEqual([x["convention"] for x in result["duplicates"]], [1])


if __name__ == "__main__":
    unittest.main()
