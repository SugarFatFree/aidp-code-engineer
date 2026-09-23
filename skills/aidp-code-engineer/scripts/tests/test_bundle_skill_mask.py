#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bundle 内 SKILL.md 遮名（`SKILL.md.in`）的往返不变量。

## 为什么需要本套件

脚手架自带的契约 bundle 里有 13 份 SKILL.md（7 个下发 SKILL + 6 个插件内嵌 SKILL）。
有的 Agent 会**递归**发现 SKILL.md —— 于是脚手架还没初始化，它旗下的 skill 就先被注册进去了。
故 bundle 内一律存为 `SKILL.md.in`，读出 / 渲染 / 安装时还原。

这层遮名横跨四个读写点（mirror 写、scaffold 铺契约、runtime_layout 渲染运行包、verify 比对清单），
**漏掉任何一个，症状都不是报错而是"少一个文件"或"多一个 .in"** —— 下游要到真去读那份 SKILL 时才发现。
故这里钉死往返不变量，而不是只测单个函数。
"""
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import scaffold_lib as L          # noqa: E402
import runtime_layout as RL       # noqa: E402


class BundleMaskTest(unittest.TestCase):
    def test_mask_unmask_roundtrip(self):
        for installed in ("skills/x/SKILL.md", "plugins/p/skills/y/SKILL.md"):
            masked = L.bundle_mask(installed)
            self.assertEqual(masked, installed + ".in")
            self.assertEqual(L.bundle_unmask(masked), installed)

    def test_unmask_is_noop_on_real_tree(self):
        # ★ 调用方无条件调 unmask，靠的就是这条：真实 .aidp/ 树里不存在遮名，对它必须是空操作。
        for rel in ("skills/x/SKILL.md", "commands/a.md", "scripts/b.py",
                    "reference/SKILL.md.in.md", "notes.in"):
            self.assertEqual(L.bundle_unmask(rel), rel, rel)

    def test_bundle_holds_no_bare_skill_md(self):
        # ★ 本套件的核心断言：bundle 里一份 SKILL.md 都不能有，否则递归发现的 Agent 会提前注册。
        bare = sorted(p.relative_to(L.ASSETS).as_posix() for p in L.ASSETS.rglob("SKILL.md"))
        self.assertEqual(bare, [], f"bundle 内仍有未遮名的 SKILL.md：{bare}")
        masked = list(L.ASSETS.rglob("SKILL.md.in"))
        self.assertTrue(masked, "bundle 内一个遮名文件都没有 —— 镜像器八成没跑或遮名失效")

    def test_render_tree_restores_installed_names(self):
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / ".agents"
            RL.render_tree(L.BUNDLE_AIDP, dest, ".agents")
            leftover = sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*.in"))
            self.assertEqual(leftover, [], f"运行包残留遮名文件：{leftover}")
            restored = sorted(p.relative_to(dest).as_posix() for p in dest.rglob("SKILL.md"))
            self.assertTrue(restored, "运行包里一份 SKILL.md 都没有 —— 还原漏了")

    def test_manifest_keys_use_installed_paths(self):
        # ★ 指纹键必须是安装路径：键一旦带上 `.in`，同版本下游会被整批判成契约漂移。
        import json
        files = json.loads((L.SKILL_DIR / L.MANIFEST_REL).read_text(encoding="utf-8"))["files"]
        bad = [k for k in files if k.endswith(L.BUNDLE_MASK_SUFFIX)]
        self.assertEqual(bad, [], f"CONTRACT_MANIFEST 键混入了 bundle 遮名：{bad}")
        self.assertTrue(any(k.endswith("/SKILL.md") for k in files),
                        "指纹里一个 SKILL.md 键都没有 —— 键被遮名替换掉了")


class ConsumersTolerateMaskTest(unittest.TestCase):
    """遮名之后，所有「靠 SKILL.md 存在与否识别 SKILL」的消费方都必须还认得出来。"""

    def test_agent_sync_discovers_skills_in_masked_bundle(self):
        # ★ scaffold 的适配层预检会把 RUNTIME_ROOT 临时指向 bundle（_preflight_native_adapter）。
        #   只认裸 SKILL.md 时这里会返回 0 个 —— 命令 / SKILL / 插件的重名冲突检测当场空跑，
        #   而且**不报错**，只是什么都没查。
        import tempfile
        sys.path.insert(0, str(SCRIPTS.parents[2] / ".aidp/scripts"))
        import agent_sync as A
        saved = A.RUNTIME_ROOT
        try:
            A.RUNTIME_ROOT = L.BUNDLE_AIDP
            with tempfile.TemporaryDirectory() as td:
                found = A._base_skill_dirs(Path(td))
            self.assertTrue(found, "bundle 作运行根时一个公共 SKILL 都没发现 —— 遮名把识别打瞎了")
            self.assertNotIn("aidp-code-engineer", found)
            self.assertEqual(set(A._declared_skill_names(found)), set(found),
                             "frontmatter name 读不出来（多半是仍在硬读 SKILL.md）")
        finally:
            A.RUNTIME_ROOT = saved

    def test_rollback_journal_uses_installed_names(self):
        # ★ 回滚日志按源树推算「本次会创建哪些路径」。源是 bundle 时它拿到的是遮名，
        #   而落盘是安装名 —— 不还原就会登记一个不存在的路径、漏掉真正被创建的那个，
        #   失败回滚时运行包删不干净（回归见 test_downstream_portability 的原子替换注入用例）。
        import scaffold as S
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".agents").mkdir()
            journal = S._NativeInstallJournal(root, {".agents"})
            src = root / "src"
            (src / "skills/demo").mkdir(parents=True)
            (src / "skills/demo/SKILL.md.in").write_text("x\n", encoding="utf-8")
            journal.expect_tree(root / ".agents", src)
            created = {p.as_posix() for p in journal.created}
            self.assertIn(".agents/skills/demo/SKILL.md", created)
            self.assertNotIn(".agents/skills/demo/SKILL.md.in", created)


if __name__ == "__main__":
    unittest.main()
