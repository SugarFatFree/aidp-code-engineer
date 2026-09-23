#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sync_memory_md.py —— 下发记忆源文件 `.aidp/AIDP-AGENTS.md` → 脚手架模板 `assets/AGENTS.md.tpl`。

模板仓库有两份记忆，职责分开、互不下发：

| 文件 | 给谁 | 是否下发 |
|------|------|---------|
| 根 `AGENTS.md`（`CLAUDE.md` = `@AGENTS.md`） | 模板仓库自身的维护者 | ⛔ 不下发 |
| `.aidp/AIDP-AGENTS.md` | 下游项目（占位 `{{project}}` `{{version}}` `{{user}}` `{{date}}`） | ✅ 经本脚本进脚手架 bundle |

本脚本只做结构校验 + 原样复制（任一必需锚点缺失即报错退出，防止源文件改坏后静默下发残缺正文）。
脚手架 init / migrate 渲染该模板后写入下游项目记忆文件（只有 Claude Code → `CLAUDE.md`；
否则 `AGENTS.md`，并存时 `CLAUDE.md` 为 `@AGENTS.md` 薄壳，由 `.aidp/scripts/agent_sync.py` 装配）。

用法（在模板项目任意目录）：
    python3 skills/aidp-code-engineer/scripts/sync_memory_md.py            # 写入
    python3 skills/aidp-code-engineer/scripts/sync_memory_md.py --check    # 只比对，有漂移 exit 1

退出码：0 已一致 / 已写入 · 1 `--check` 发现漂移 · 2 源文件结构不符或环境错误
"""
import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parent
TPL_REL = "assets/AGENTS.md.tpl"
SOURCE_REL = ".aidp/AIDP-AGENTS.md"
CUSTOM_MARK = "<!-- AIDP:PROJECT-CUSTOM"

# 下游正文必须具备的锚点（脚手架渲染 / verify / memory-sync 依赖它们）
REQUIRED = (
    "# {{project}}",
    "- **当前版本**：{{version}}",
    "- **当前开发者**：{{user}}",
    "- **最后更新**：{{date}}",
    "## 当前状态",
    "## 核心约定",
    "## 项目自定义",
    CUSTOM_MARK,
)
# 模板仓库自身的维护内容不得出现在下发源里
FORBIDDEN = ("TEMPLATE-ONLY", "模板项目维护特例", "范式版本号自增策略")


class TemplateShapeError(Exception):
    pass


def render_downstream(source: str) -> str:
    missing = [a for a in REQUIRED if a not in source]
    if missing:
        raise TemplateShapeError(f"{SOURCE_REL} 缺少必需锚点：{missing}")
    leaked = [w for w in FORBIDDEN if w in source]
    if leaked:
        raise TemplateShapeError(f"{SOURCE_REL} 混入模板仓库自身的维护内容：{leaked}（应写在根 AGENTS.md）")
    return source.rstrip("\n") + "\n"


def find_template_root(start: Path) -> Path:
    cur = start.resolve()
    for _ in range(10):
        if (cur / SOURCE_REL).is_file() and (cur / "skills/aidp-code-engineer/SKILL.md").is_file():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    raise SystemExit(2)


def build(root: Path) -> str:
    return render_downstream((root / SOURCE_REL).read_text(encoding="utf-8"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=f"{SOURCE_REL} → {TPL_REL}")
    ap.add_argument("--root", default=None, help="模板项目根（缺省向上查找）")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    try:
        root = Path(a.root).resolve() if a.root else find_template_root(SKILL_DIR)
    except SystemExit:
        print(f"未找到模板项目根（需含 {SOURCE_REL} 与 skills/aidp-code-engineer/）", file=sys.stderr)
        return 2
    try:
        want = build(root)
    except (OSError, TemplateShapeError) as e:
        print(f"⛔ {e}", file=sys.stderr)
        return 2
    dst = SKILL_DIR / TPL_REL
    have = dst.read_text(encoding="utf-8") if dst.is_file() else None
    if have == want:
        print(f"✅ {TPL_REL} 已与 {SOURCE_REL} 一致")
        return 0
    if a.check:
        print(f"❌ {TPL_REL} 与 {SOURCE_REL} 不一致 → 跑 sync_memory_md.py（或 mirror_to_bundle.py）")
        return 1
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(want, encoding="utf-8")
    print(f"✅ 已写入 {TPL_REL}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
