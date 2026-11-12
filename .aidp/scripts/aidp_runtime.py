#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AIDP 运行包根与项目根解析，不依赖 Git。"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping


def _is_scaffold_bundle(root: Path) -> bool:
    """`<skill>/assets/aidp/` —— 脚手架 skill 自带的契约 bundle（模板副本，不是已安装的运行包）。

    只认「三件套齐全」的严格形态：`assets/SCAFFOLD_VERSION`、`assets/CONTRACT_MANIFEST.json`
    与 skill 自身的 `SKILL.md`。上面两支认的真实运行根（模板维护目录、Agent 原生运行包）都不会
    命中这一支，所以不放松真实运行根的解析。
    """
    assets = root.parent
    if root.name != "aidp" or assets.name != "assets":
        return False
    return ((assets / "SCAFFOLD_VERSION").is_file()
            and (assets / "CONTRACT_MANIFEST.json").is_file()
            and (assets.parent / "SKILL.md").is_file())


def _natural_layout(script_file: Path | str) -> tuple[Path, Path]:
    path = Path(script_file).expanduser()
    if path.parent.name != "scripts":
        raise RuntimeError(f"无法从脚本位置解析 AIDP 运行根: {path}")
    root = path.parent.parent
    if root.name == ".aidp":
        return root, root.parent
    if root.name in {".claude", ".agents"}:
        return root, root.parent
    # 历史嵌套形态 `<root>/.claude/aidp/scripts`：留着，未迁移的项目还在用。
    if root.name == "aidp" and root.parent.name in {".claude", ".agents"}:
        return root, root.parent.parent
    # 脚手架 bundle：被 scaffold.py / verify.py 以库的形式 import —— 下游装好的项目里没有模板
    # 维护目录，bundle 是唯一来源。边界取 `assets/`（bundle 自身的容器）；调用方使用运行根前
    # 会自行改写 RUNTIME_ROOT，这里只保证 import 期不炸。
    if _is_scaffold_bundle(root):
        return root, root.parent
    raise RuntimeError(f"无法从脚本位置解析 AIDP 运行根: {path}")


def _normalize_lexical(path: Path | str | os.PathLike[str]) -> Path:
    """Collapse `.`/`..` without resolving symlinks."""
    expanded = os.path.expanduser(os.fspath(path))
    return Path(os.path.abspath(os.path.normpath(expanded)))


def _absolute(value: str | os.PathLike[str], base: Path) -> Path:
    path = Path(value).expanduser()
    combined = path if path.is_absolute() else base / path
    return _normalize_lexical(combined)


def _reject_symlinked_path(path: Path, label: str) -> None:
    """Reject an existing symlink/non-directory in a directory path.

    Missing trailing components are allowed because scaffold callers may resolve a
    destination before creating it. Every existing component is checked without
    following symlinks.
    """
    absolute = path.absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.is_symlink():
            raise RuntimeError(f"{label} 包含 symlink: {current}")
        if current.exists() and not current.is_dir():
            raise RuntimeError(f"{label} 包含非目录路径: {current}")


def _contained(path: Path, project: Path) -> Path:
    lexical_path = _normalize_lexical(path)
    lexical_project = _normalize_lexical(project)
    try:
        lexical_path.relative_to(lexical_project)
    except ValueError as exc:
        raise RuntimeError(f"AIDP_HOME 位于项目根之外: {lexical_path}") from exc
    _reject_symlinked_path(lexical_project, "项目根")
    _reject_symlinked_path(lexical_path, "AIDP_HOME")
    return lexical_path


def _roots(script_file: Path | str, environ: Mapping[str, str] | None) -> tuple[Path, Path]:
    env = os.environ if environ is None else environ
    project_value = (env.get("AIDP_PROJECT_ROOT") or "").strip()
    home_value = (env.get("AIDP_HOME") or "").strip()

    if project_value and home_value:
        natural_runtime = natural_project = None
    else:
        natural_runtime, natural_project = _natural_layout(script_file)

    project = (_absolute(project_value, Path.cwd()) if project_value
               else _normalize_lexical(natural_project))
    assert project is not None
    _reject_symlinked_path(project, "项目根")

    runtime = (_absolute(home_value, project) if home_value
               else _normalize_lexical(natural_runtime))
    assert runtime is not None
    runtime = _contained(runtime, project)
    return runtime, project.absolute()


def runtime_root(script_file: Path | str = __file__, *,
                 environ: Mapping[str, str] | None = None) -> Path:
    """Return the template, Claude, or shared AIDP runtime root for a script."""
    return _roots(script_file, environ)[0]


def project_root(script_file: Path | str = __file__, *,
                 environ: Mapping[str, str] | None = None) -> Path:
    """Return the project root without invoking Git."""
    return _roots(script_file, environ)[1]


def runtime_path(relative: str | os.PathLike[str], script_file: Path | str = __file__) -> Path:
    """Return an absolute path inside the current AIDP runtime."""
    root = runtime_root(script_file)
    target = _normalize_lexical(root / Path(relative))
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise RuntimeError(f"运行包相对路径越界: {relative}") from exc
    return target


def runtime_relpath(relative: str | os.PathLike[str] = "", script_file: Path | str = __file__) -> str:
    """Return a project-relative POSIX path inside the current runtime."""
    target = runtime_path(relative, script_file)
    return target.relative_to(project_root(script_file)).as_posix()


def contract_root(root: Path | str) -> Path:
    """定位被检查项目的契约根，兼容维护源、共享根与 Claude 单独安装。

    检查器可从模板仓库对另一个项目运行，不能拿检查器自身的目录当目标根。
    共享根优先于 Claude 装配副本；空 Agent 标记目录不视为已安装契约。
    """
    project = Path(root)
    for relative in (".aidp", ".agents", ".claude", ".agents/aidp", ".claude/aidp"):
        home = project / relative
        if (home / "reference").is_dir() or (home / "scripts").is_dir():
            return home
    return project / ".aidp"


def convention_candidates(root: Path | str) -> tuple[Path, ...]:
    """约定主行单一信源优先，兼容仍使用完整项目记忆的旧安装。"""
    project = Path(root)
    home = contract_root(project)
    return (home / "reference/core-conventions.md", home / "AIDP-AGENTS.md",
            project / "AGENTS.md", project / "CLAUDE.md")


def convention_source(root: Path | str) -> Path | None:
    """返回约定正文；外置文件存在即权威，损坏时不回退到陈旧正文。"""
    import re
    candidates = convention_candidates(root)
    for index, candidate in enumerate(candidates):
        if candidate.is_file():
            if index == 0 or re.search(r"(?m)^\d+\.\s+\*\*", candidate.read_text(encoding="utf-8")):
                return candidate
    return None


def runtime_text(text: str, script_file: Path | str = __file__) -> str:
    """Expand legacy source-tree path literals for template and native runtimes."""
    home = runtime_relpath("", script_file).rstrip("/")
    return text.replace("__AIDP_HOME__", home)
