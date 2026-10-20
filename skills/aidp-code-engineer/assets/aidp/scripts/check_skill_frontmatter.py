#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""下发 SKILL 的 frontmatter 合法性门。

## 为什么需要这道门

每个 `SKILL.md` 开头的 `---` 块是**元数据**（`name` / `description`），加载器按 YAML 解析。
一旦正文被插进去（编辑时把一整节 Markdown 粘在 `---` 与 `name:` 之间），整个 frontmatter
就不是合法 YAML 了 —— 而**文件本身读起来完全正常**：标题在、段落通顺、目录能点。

失败方向是最坏的那种：`Skill` 调用找不到该 SKILL，或 Codex / DSH 的发现根直接跳过它，
于是「有这一节」和「这一节从未生效」在产物上同形。这类破坏零成本可检，只是此前没有门。

## 判据

对 `{{AIDP_HOME}}/skills/*/SKILL.md`（以及下发给下游的 bundle 副本）：

  1. 文件以一个**完整**的 `---` … `---` 块开头；
  2. 该块能被 YAML 解析成 mapping；
  3. `name` 存在且等于所在目录名（名字对不上时加载器按名字注册，等于装错位）；
  4. `description` 存在且非空。

任一条不满足即 ERROR，并打印**第一处**偏离的行号与原因。
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

_scripts = str(Path(__file__).resolve().parent)
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)
from aidp_runtime import runtime_relpath

RUNTIME_REL = runtime_relpath("", __file__)


def _frontmatter_block(text: str):
    """→ (块正文, 结束行号) 或 (None, 原因)。"""
    if not text.startswith("---"):
        return None, "文件不是以 `---` 开头（缺 frontmatter）"
    lines = text.splitlines()
    if lines[0].strip() != "---":
        return None, "首行不是独立的 `---` 分隔符"
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[1:i]), i + 1
    return None, "找不到闭合的 `---`（frontmatter 未结束）"


def check_one(path: Path) -> list[dict]:
    import yaml
    problems = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [{"path": str(path), "line": 0, "reason": f"读不出：{exc}"}]
    block, end = _frontmatter_block(text)
    if block is None:
        return [{"path": str(path), "line": 1, "reason": end}]
    # 正文混进 frontmatter 的典型形态：块内出现 Markdown 标题。先单独报它，
    # 因为 YAML 解析器的报错信息（"found character '`'"）指向的是第 4 行而不是真因。
    for offset, line in enumerate(block.splitlines(), 1):
        if line.lstrip().startswith("#"):
            problems.append({
                "path": str(path), "line": offset + 1,
                "reason": f"frontmatter 里出现 Markdown 标题「{line.strip()[:40]}」"
                          f" —— 正文被插进了元数据块（闭合 `---` 在 {end} 行）",
            })
            break
    try:
        data = yaml.safe_load(block)
    except Exception as exc:  # noqa: BLE001 —— YAML 的异常类型随实现而异
        first = str(exc).splitlines()[0]
        detail = ""
        for piece in str(exc).splitlines()[1:]:
            if "line" in piece:
                detail = piece.strip()
                break
        problems.append({"path": str(path), "line": 0,
                         "reason": f"frontmatter 不是合法 YAML：{first} {detail}".strip()})
        return problems
    if not isinstance(data, dict):
        problems.append({"path": str(path), "line": 0,
                         "reason": f"frontmatter 不是 mapping（实际 {type(data).__name__}）"})
        return problems
    name = data.get("name")
    if not name:
        problems.append({"path": str(path), "line": 0, "reason": "frontmatter 缺 `name`"})
    elif path.parent.name and str(name) != path.parent.name:
        problems.append({"path": str(path), "line": 0,
                         "reason": f"`name: {name}` 与目录名 `{path.parent.name}` 不一致"
                                   f"（加载器按 name 注册，装好后会找不到）"})
    desc = data.get("description")
    if not desc or not str(desc).strip():
        problems.append({"path": str(path), "line": 0, "reason": "frontmatter 缺 `description`"})
    return problems


def scan(root: Path) -> list[dict]:
    findings = []
    bases = [root / RUNTIME_REL / "skills"]
    bundle = root / "skills" / "aidp-code-engineer" / "assets" / "aidp" / "skills"
    if bundle.is_dir():
        bases.append(bundle)
    for base in bases:
        if not base.is_dir():
            continue
        for skill_md in sorted(base.glob("*/SKILL.md*")):
            if not skill_md.is_file() or skill_md.is_symlink():
                continue
            for item in check_one(skill_md):
                try:
                    item["path"] = skill_md.relative_to(root).as_posix()
                except ValueError:
                    pass
                findings.append(item)
    return findings


def self_check() -> bool:
    root = Path(tempfile.mkdtemp(prefix="aidp-skill-fm-"))
    try:
        good = root / RUNTIME_REL / "skills" / "good-skill"
        good.mkdir(parents=True)
        (good / "SKILL.md").write_text(
            "---\nname: good-skill\ndescription: 一句话\n---\n\n# 正文\n", encoding="utf-8")
        # 阳性 1：正文整节插进 frontmatter（本次抓到的真实形态）
        bad = root / RUNTIME_REL / "skills" / "bad-skill"
        bad.mkdir(parents=True)
        (bad / "SKILL.md").write_text(
            "---\n\n## 客户端 MCP 的 Task 边界\n\n`client_mcp.enabled` 默认关闭。\n"
            "name: bad-skill\ndescription: x\n---\n", encoding="utf-8")
        # 阳性 2：name 与目录名不一致
        wrong = root / RUNTIME_REL / "skills" / "dir-name"
        wrong.mkdir(parents=True)
        (wrong / "SKILL.md").write_text(
            "---\nname: other-name\ndescription: x\n---\n", encoding="utf-8")
        found = scan(root)
        by_dir = {}
        for x in found:
            by_dir.setdefault(Path(x["path"]).parent.name, []).append(x["reason"])
        # bad-skill 应报**两条**：先点破「正文被插进元数据」，再报 YAML 解析失败 ——
        # 只报后者的话，报错行号指向的是第 4 行的反引号，而真因是第 2 行那一整个标题。
        return (sorted(by_dir) == ["bad-skill", "dir-name"]
                and len(by_dir["bad-skill"]) == 2
                and any("Markdown 标题" in r for r in by_dir["bad-skill"])
                and any("YAML" in r for r in by_dir["bad-skill"])
                and "good-skill" not in by_dir)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="下发 SKILL 的 frontmatter 合法性门")
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-check", action="store_true")
    args = ap.parse_args(argv)
    if args.self_check:
        ok = self_check()
        print(json.dumps({"self_check": "pass" if ok else "fail"}, ensure_ascii=False))
        return 0 if ok else 1
    root = Path(args.root).resolve()
    if not root.is_dir():
        ap.error("--root 必须是目录")
    findings = scan(root)
    if args.json:
        print(json.dumps({"ok": not findings, "findings": findings}, ensure_ascii=False, indent=2))
    elif findings:
        for item in findings:
            loc = f"{item['path']}:{item['line']}" if item["line"] else item["path"]
            print(f"[ERROR] skill-frontmatter {loc} — {item['reason']}")
    else:
        print("[OK] SKILL frontmatter 全部合法")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
