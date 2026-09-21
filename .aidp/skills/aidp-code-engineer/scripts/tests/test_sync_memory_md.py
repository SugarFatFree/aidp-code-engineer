#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sync_memory_md：下发记忆源 `.aidp/AIDP-AGENTS.md` → 下游记忆文件模板（结构校验 + 原样复制）。"""
import unittest

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


if __name__ == "__main__":
    unittest.main()
