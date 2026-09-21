#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Agent 原生 AIDP 运行包的确定性渲染、校验与原子安装。"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from pathlib import Path
from typing import Callable, Dict, Optional

import scaffold_lib as L

RUNTIME_MANIFEST = ".aidp-runtime.json"
RUNTIME_HOME = {"claude": ".claude/aidp", "shared": ".agents/aidp"}
RUNTIME_DIRS = L.RUNTIME_DIRS
RUNTIME_EXCLUDES = L.RUNTIME_EXCLUDES
_TOKEN_RE = re.compile(r"\{\{[^{}]+\}\}")


def _lexical(path: Path) -> Path:
    return Path(os.path.abspath(os.path.normpath(str(path.expanduser()))))


def _lexists(path: Path) -> bool:
    return os.path.lexists(str(path))


def _assert_contained(path: Path, boundary: Path) -> Path:
    target, root = _lexical(path), _lexical(boundary)
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise RuntimeError(f"路径越出受管边界: {target}（边界 {root}）") from exc
    current = Path(root.anchor)
    for part in root.parts[1:]:
        current /= part
        if current.is_symlink():
            raise RuntimeError(f"受管边界包含 symlink: {current}")
        if current.exists() and not current.is_dir():
            raise RuntimeError(f"受管边界包含非目录: {current}")
    relative = target.relative_to(root)
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise RuntimeError(f"受管路径包含 symlink: {current}")
        if current.exists() and current != target and not current.is_dir():
            raise RuntimeError(f"受管路径祖先不是目录: {current}")
    return target


def _default_boundary(destination: Path) -> Path:
    parent = destination.parent
    if parent.name in {".claude", ".agents"}:
        return parent.parent
    return parent


def _excluded(relative: str) -> bool:
    return any(relative == item.rstrip("/") or
               (item.endswith("/") and relative.startswith(item))
               for item in RUNTIME_EXCLUDES)


def _is_text(data: bytes) -> bool:
    if b"\x00" in data:
        return False
    try:
        data.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def render_text(text: str, home: str) -> str:
    """渲染一个 UTF-8 契约文件，并拒绝未解析或旧运行路径。"""
    if home not in RUNTIME_HOME.values():
        raise ValueError(f"未知 AIDP_HOME: {home}")
    rendered = text.replace("{{AIDP_HOME}}", home)
    unknown = sorted(set(_TOKEN_RE.findall(rendered)))
    if unknown:
        raise ValueError(f"存在未解析运行占位符: {', '.join(unknown)}")
    for line_no, line in enumerate(rendered.splitlines(), 1):
        if ".aidp/" in line and "LEGACY_AIDP_DIR" not in line:
            raise ValueError(f"存在旧运行路径 .aidp/（第 {line_no} 行）")
    return rendered


def render_tree(source_root: Path, destination: Path, home: str) -> None:
    """把模板真源渲染到空目标目录。"""
    source_root, destination = Path(source_root), Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for dirname in RUNTIME_DIRS:
        source_dir = source_root / dirname
        if not source_dir.is_dir():
            continue
        (destination / dirname).mkdir(parents=True, exist_ok=True)
        for source in sorted(source_dir.rglob("*")):
            relative = source.relative_to(source_root).as_posix()
            if L.is_ignored(source.relative_to(source_root).parts) or _excluded(relative):
                continue
            target = destination / relative
            if source.is_symlink():
                raise RuntimeError(f"运行包真源不得包含 symlink: {source}")
            if source.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not source.is_file():
                raise RuntimeError(f"运行包真源包含异常类型: {source}")
            target.parent.mkdir(parents=True, exist_ok=True)
            data = source.read_bytes()
            if _is_text(data):
                target.write_text(render_text(data.decode("utf-8"), home), encoding="utf-8")
                shutil.copymode(source, target)
            else:
                shutil.copy2(source, target)


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _runtime_files(runtime: Path):
    for path in sorted(runtime.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"运行包不得包含 symlink: {path}")
        if path.is_file() and path.name != RUNTIME_MANIFEST:
            yield path.relative_to(runtime).as_posix(), path


def build_runtime_manifest(runtime: Path, version: str, source: str) -> dict:
    if source not in RUNTIME_HOME:
        raise ValueError(f"非法运行包 source: {source}")
    files = {relative: _file_hash(path) for relative, path in _runtime_files(Path(runtime))}
    return {
        "schema": "aidp.runtime/v1",
        "version": version,
        "source": source,
        "files": dict(sorted(files.items())),
    }


def _read_manifest(runtime: Path) -> dict:
    path = runtime / RUNTIME_MANIFEST
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"运行包 manifest 不可读: {path}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"运行包 manifest 必须是对象: {path}")
    return data


def validate_runtime(runtime: Path, expected_home: Optional[str] = None) -> dict:
    runtime = Path(runtime)
    manifest = _read_manifest(runtime)
    if manifest.get("schema") != "aidp.runtime/v1":
        raise ValueError("运行包 manifest schema 非法")
    if manifest.get("source") not in RUNTIME_HOME:
        raise ValueError("运行包 manifest source 非法")
    expected_files = manifest.get("files")
    if not isinstance(expected_files, dict):
        raise ValueError("运行包 manifest files 必须是对象")
    actual = {relative: _file_hash(path) for relative, path in _runtime_files(runtime)}
    if dict(sorted(expected_files.items())) != dict(sorted(actual.items())):
        raise ValueError("运行包文件指纹漂移")
    home = expected_home or RUNTIME_HOME[manifest["source"]]
    for relative, path in _runtime_files(runtime):
        data = path.read_bytes()
        if not _is_text(data):
            continue
        text = data.decode("utf-8")
        if _TOKEN_RE.search(text):
            raise ValueError(f"运行包含未解析占位符: {relative}")
        for line in text.splitlines():
            if ".aidp/" in line and "LEGACY_AIDP_DIR" not in line:
                raise ValueError(f"运行包含旧路径: {relative}")
        if "{{AIDP_HOME}}" in text:
            raise ValueError(f"运行包含未解析 AIDP_HOME: {relative}")
    if home not in RUNTIME_HOME.values():
        raise ValueError(f"非法 expected_home: {home}")
    return manifest


def normalize_runtime(runtime: Path, home: str) -> Dict[str, bytes]:
    """把运行根反向规范化为 token，供 Claude/shared 运行包比较。"""
    normalized = {}
    for relative, path in _runtime_files(Path(runtime)):
        data = path.read_bytes()
        if _is_text(data):
            data = data.decode("utf-8").replace(home, "{{AIDP_HOME}}").encode("utf-8")
        normalized[relative] = data
    return normalized


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    root = Path(root)
    if not _lexists(root):
        return digest.hexdigest()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(relative + b"\0")
        if path.is_symlink():
            digest.update(b"L" + os.readlink(path).encode("utf-8"))
        elif path.is_file():
            digest.update(b"F" + path.read_bytes())
        elif path.is_dir():
            digest.update(b"D")
    return digest.hexdigest()


def remove_tree_safely(path: Path, boundary: Optional[Path] = None) -> None:
    path = Path(path)
    root = Path(boundary) if boundary is not None else path.parent
    target = _assert_contained(path, root)
    if not _lexists(target):
        return
    if target.is_symlink():
        raise RuntimeError(f"拒绝删除 symlink: {target}")
    if target.is_dir():
        shutil.rmtree(target)
    elif target.is_file():
        target.unlink()
    else:
        raise RuntimeError(f"拒绝删除异常路径: {target}")


def _runtime_modified(destination: Path) -> bool:
    manifest = _read_manifest(destination)
    expected = manifest.get("files")
    if not isinstance(expected, dict):
        return True
    actual = {relative: _file_hash(path) for relative, path in _runtime_files(destination)}
    return dict(sorted(expected.items())) != dict(sorted(actual.items()))


def _write_manifest(runtime: Path, manifest: dict) -> None:
    (runtime / RUNTIME_MANIFEST).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def render_runtime(source_root: Path, destination: Path, home: str, version: str,
                   source: str, backup_callback: Optional[Callable[[Path], Path]] = None,
                   replace_func: Callable[[object, object], None] = os.replace) -> dict:
    """在同父目录 staging 后原子替换运行包；失败恢复旧包。"""
    destination = Path(destination)
    boundary = _default_boundary(destination)
    destination = _assert_contained(destination, boundary)
    stage = destination.with_name(destination.name + ".aidp-stage")
    previous = destination.with_name(destination.name + ".aidp-previous")
    for transient in (stage, previous):
        remove_tree_safely(transient, boundary=boundary)

    if _lexists(destination):
        if destination.is_symlink() or not destination.is_dir():
            raise RuntimeError(f"运行包目标不是受管目录: {destination}")
        if not (destination / RUNTIME_MANIFEST).is_file():
            raise RuntimeError(f"同名目录缺少运行包 manifest，拒绝覆盖: {destination}")
        if _runtime_modified(destination):
            if backup_callback is None:
                raise RuntimeError(f"运行包含用户修改，必须先完整备份: {destination}")
            backup = backup_callback(destination)
            if backup is None or not Path(backup).exists():
                raise RuntimeError(f"运行包备份失败: {destination}")

    stage.mkdir(parents=True, exist_ok=False)
    moved_old = False
    try:
        render_tree(Path(source_root), stage, home)
        manifest = build_runtime_manifest(stage, version=version, source=source)
        _write_manifest(stage, manifest)
        validate_runtime(stage, expected_home=home)
        if _lexists(destination):
            replace_func(destination, previous)
            moved_old = True
        try:
            replace_func(stage, destination)
        except Exception:
            if moved_old and _lexists(previous) and not _lexists(destination):
                replace_func(previous, destination)
                moved_old = False
            raise
        if _lexists(previous):
            remove_tree_safely(previous, boundary=boundary)
        return manifest
    finally:
        if _lexists(stage):
            remove_tree_safely(stage, boundary=boundary)
        if moved_old and _lexists(previous) and not _lexists(destination):
            replace_func(previous, destination)
