#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AIDP 运行包根与项目根解析，不依赖 Git。"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping


def _natural_layout(script_file: Path | str) -> tuple[Path, Path]:
    path = Path(script_file).expanduser()
    if path.parent.name != "scripts":
        raise RuntimeError(f"无法从脚本位置解析 AIDP 运行根: {path}")
    root = path.parent.parent
    if root.name == ".aidp":
        return root, root.parent
    if root.name == "aidp" and root.parent.name in {".claude", ".agents"}:
        return root, root.parent.parent
    raise RuntimeError(f"无法从脚本位置解析 AIDP 运行根: {path}")


def _absolute(value: str | os.PathLike[str], base: Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else base / path


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
    lexical_path = path.absolute()
    lexical_project = project.absolute()
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
               else natural_project)
    assert project is not None
    _reject_symlinked_path(project, "项目根")

    runtime = (_absolute(home_value, project) if home_value
               else natural_runtime)
    assert runtime is not None
    runtime = _contained(runtime, project)
    return runtime, project.absolute()


def runtime_root(script_file: Path | str = __file__, *,
                 environ: Mapping[str, str] | None = None) -> Path:
    """Return `.aidp`, `.claude/aidp`, or `.agents/aidp` for a script."""
    return _roots(script_file, environ)[0]


def project_root(script_file: Path | str = __file__, *,
                 environ: Mapping[str, str] | None = None) -> Path:
    """Return the project root without invoking Git."""
    return _roots(script_file, environ)[1]
