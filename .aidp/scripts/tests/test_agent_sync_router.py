#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""agent_sync.py 原生命令生成、参数保真与 gitignore 托管回归（stdlib only）。

覆盖：
  · Codex 每条命令生成独立 SKILL.md + agents/openai.yaml，正文逐字保留 `$ARGUMENTS`
  · DSH 命令直接生成到 `.dsh/commands/`，公共 `.agents/skills/` 不含 `aidp-cmd`
  · 无 H1 命令使用稳定 description；命令与公共 SKILL 重名 fail closed
  · `--check` 检出命令正文漂移；新适配路径遵守 .gitignore 托管块去重

直接跑：`python3 .aidp/scripts/tests/test_agent_sync_router.py`
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
sys.path.insert(0, SCRIPTS)
SYNC_PY = os.path.join(SCRIPTS, "agent_sync.py")
REPO = Path(__file__).resolve().parents[3]
CODEX_BODY_MARKER = "## 原始命令正文（逐字保真）\n\n"

import agent_sync as AS  # noqa: E402

_passed = _failed = 0


def check(name, cond):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ✅ {name}")
    else:
        _failed += 1
        print(f"  ❌ FAIL: {name}")


def _run(*args):
    env = {k: v for k, v in os.environ.items() if k != "AIDP_AGENT"}
    cp = subprocess.run([sys.executable, SYNC_PY, *args], capture_output=True, text=True, env=env, timeout=60)
    try:
        out = json.loads(cp.stdout.strip().splitlines()[-1]) if cp.stdout.strip() else {}
    except ValueError:
        out = {}
    return cp.returncode, out, cp.stdout, cp.stderr


def _read(path):
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return ""


def _discover_codex_skills(root: Path, max_depth=6) -> set:
    skill_root = root / ".codex/skills"
    if not skill_root.is_dir():
        return set()
    discovered = set()
    for skill_file in skill_root.rglob("SKILL.md"):
        relative = skill_file.parent.relative_to(skill_root)
        if len(relative.parts) <= max_depth:
            discovered.add(relative.as_posix())
    return discovered


def _mkrepo() -> Path:
    root = Path(tempfile.mkdtemp())
    (root / ".aidp/commands").mkdir(parents=True)
    (root / ".aidp/commands/version.md").write_text(
        "# /version — 版本管理命令（★）\n\n参数：$ARGUMENTS\n", encoding="utf-8")
    (root / ".aidp/commands/sprint-dev.md").write_text(
        "---\ndescription: 执行 Sprint 开发\n---\n# /sprint-dev — 开发阶段\n\n参数：$ARGUMENTS\n",
        encoding="utf-8")
    (root / ".aidp/commands/no-title.md").write_text(
        "参数：$ARGUMENTS\n\n无标题命令正文\n", encoding="utf-8")
    (root / ".aidp/commands/README.md").write_text("# 命令索引\n", encoding="utf-8")
    (root / ".aidp/skills/demo").mkdir(parents=True)
    (root / ".aidp/skills/demo/SKILL.md").write_text(
        "---\nname: demo\ndescription: d\n---\n", encoding="utf-8")
    return root


def test_native_command_skills():
    print("\n[native commands] Codex / DSH 原生命令")
    root = _mkrepo()
    try:
        rc, _, _, _ = _run("--root", str(root), "--agents", "codex,dsh")
        codex = root / ".codex/skills/aidp/sprint-dev/SKILL.md"
        text = _read(codex)
        source = _read(root / ".aidp/commands/sprint-dev.md")
        check("装配成功", rc == 0)
        discovered = _discover_codex_skills(root)
        check("Codex 从官方 .codex/skills 根递归发现全部命令",
              {"aidp/sprint-dev", "aidp/version", "aidp/no-title"} <= discovered)
        check("Codex description 优先使用命令 frontmatter",
              text.startswith(
                  '---\nname: sprint-dev\ndescription: "执行 Sprint 开发"\n'
              ))
        check("Codex 命令适配前言声明参数与内联串联规则",
              "Codex 命令适配规则" in text
              and "$sprint-dev args" in text
              and "读取 `.agents/aidp/commands/<命令名>.md`" in text
              and "未知命令" in text and "fail closed" in text
              and "读取 `.aidp/commands/" not in text)
        check("Codex 命令正文逐字保真",
              CODEX_BODY_MARKER in text and text.split(CODEX_BODY_MARKER, 1)[1] == source)
        check("Codex explicit invocation policy",
              "allow_implicit_invocation: false" in
              _read(root / ".codex/skills/aidp/sprint-dev/agents/openai.yaml"))
        h1_fallback = _read(root / ".codex/skills/aidp/version/SKILL.md")
        check("无 frontmatter 时使用 H1 description",
              'description: "/version — 版本管理命令（★）"' in h1_fallback)
        fallback = _read(root / ".codex/skills/aidp/no-title/SKILL.md")
        check("无 H1 使用稳定 description", 'description: "AIDP command no-title"' in fallback)
        check("README 不生成命令 SKILL", not (root / ".codex/skills/aidp/README").exists())
        check("DSH 命令直接链接且正文保真",
              (root / ".dsh/commands/sprint-dev.md").is_symlink()
              and _read(root / ".dsh/commands/sprint-dev.md") == source)
        check("公共 SKILL 不含 aidp-cmd", not (root / ".agents/skills/aidp-cmd").exists())
        check("真源不生成 aidp-cmd", not (root / ".aidp/skills/aidp-cmd").exists())
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_real_command_discovery_and_chaining():
    print("\n[discovery] 真实命令递归发现与编排映射")
    root = Path(tempfile.mkdtemp())
    try:
        shutil.copytree(REPO / ".aidp/commands", root / ".aidp/commands")
        (root / ".aidp/skills/demo").mkdir(parents=True)
        (root / ".aidp/skills/demo/SKILL.md").write_text(
            "---\nname: demo\ndescription: d\n---\n", encoding="utf-8")
        rc, _, _, _ = _run("--root", str(root), "--agents", "codex")
        command_files = [path for path in (root / ".aidp/commands").glob("*.md")
                         if path.stem.upper() != "README"]
        names = {path.stem for path in command_files}
        discovered = _discover_codex_skills(root)
        check("真实命令全部位于 Codex 可发现根",
              rc == 0 and {f"aidp/{name}" for name in names} <= discovered)

        all_mapped = True
        prefaces = True
        bodies_exact = True
        for command_name in ("sprint-full", "sprint-batch", "sprint-autopilot"):
            source = _read(root / ".aidp/commands" / f"{command_name}.md")
            generated = _read(root / ".codex/skills/aidp" / command_name / "SKILL.md")
            refs = set(re.findall(r"(?<![\w.-])/(sprint-[a-z][a-z0-9-]*)", source))
            all_mapped = all_mapped and refs <= names and all(
                (root / ".aidp/commands" / f"{ref}.md").is_file() for ref in refs)
            prefaces = prefaces and all(token in generated for token in (
                "Codex 命令适配规则", f"${command_name} args", "$ARGUMENTS",
                "读取 `.agents/aidp/commands/<命令名>.md`", "当前执行链内联执行", "未知命令",
            ))
            bodies_exact = (bodies_exact and CODEX_BODY_MARKER in generated
                            and generated.split(CODEX_BODY_MARKER, 1)[1] == source)
        check("三条编排命令均带确定性 Codex 适配前言", prefaces)
        check("三条编排命令引用的 /sprint-* 均可映射到真源", all_mapped)
        check("三条编排命令原始正文逐字保真", bodies_exact)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_check_detects_command_drift():
    print("\n[check] 命令正文漂移")
    root = _mkrepo()
    try:
        _run("--root", str(root), "--agents", "codex,dsh")
        (root / ".aidp/commands/sprint-dev.md").write_text(
            "# /sprint-dev — 新正文\n\n参数：$ARGUMENTS changed\n", encoding="utf-8")
        rc, out, _, _ = _run("--root", str(root), "--agents", "codex,dsh", "--check")
        paths = {action.get("path") for action in out.get("actions", [])}
        check("--check 漂移 exit 1", rc == 1 and out.get("drift") is True)
        check("漂移指向 Codex 命令 SKILL",
              ".codex/skills/aidp/sprint-dev/SKILL.md" in paths)
        check("--check 不改写 DSH 链接目标外的生成内容",
              "changed" not in _read(root / ".codex/skills/aidp/sprint-dev/SKILL.md"))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_name_conflict_fails_closed():
    print("\n[conflict] 命令与公共 SKILL 重名")
    root = _mkrepo()
    try:
        (root / ".aidp/commands/demo.md").write_text("# /demo\n", encoding="utf-8")
        rc, _, stdout, stderr = _run("--root", str(root), "--agents", "codex,dsh")
        check("重名 exit 2", rc == 2)
        check("重名提示冲突名称", "冲突" in (stdout + stderr) and "demo" in (stdout + stderr))
        check("冲突时不生成命令入口",
              not (root / ".codex/skills/aidp/demo").exists()
              and not (root / ".dsh/commands/demo.md").exists())
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_gitignore_dedupe():
    print("\n[gitignore] 新适配路径托管与目录规则去重")
    root = _mkrepo()
    try:
        (root / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
        rc, _, _, _ = _run("--root", str(root), "--agents", "codex,dsh")
        gi = _read(root / ".gitignore")
        check("无目录规则 → 登记 Codex/DSH/公共 SKILL 入口",
              rc == 0 and AS.GITIGNORE_BEGIN in gi
              and "/.codex/skills/aidp/sprint-dev" in gi
              and "/.dsh/commands/sprint-dev.md" in gi
              and "/.agents/skills/demo" in gi)

        (root / ".gitignore").write_text(
            "/.codex/\n/.dsh/\n/.agents/\n\n" + AS.GITIGNORE_BEGIN
            + "\n/.codex/skills/aidp/sprint-dev\n/.dsh/commands/sprint-dev.md\n"
            + AS.GITIGNORE_END + "\n", encoding="utf-8")
        _run("--root", str(root), "--agents", "codex,dsh")
        gi = _read(root / ".gitignore")
        check("目录规则全覆盖 → 移除冗余托管块", AS.GITIGNORE_BEGIN not in gi)
        check("_covered_by_dir_rules 区分目录规则与通配",
              AS._covered_by_dir_rules("/.codex/\n", ".codex/skills/aidp/x")
              and not AS._covered_by_dir_rules("/.codex/*\n", ".codex/skills/aidp/x"))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main():
    test_native_command_skills()
    test_real_command_discovery_and_chaining()
    test_check_detects_command_drift()
    test_name_conflict_fails_closed()
    test_gitignore_dedupe()
    print(f"\n══ 结果：{_passed} passed / {_failed} failed ══")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
