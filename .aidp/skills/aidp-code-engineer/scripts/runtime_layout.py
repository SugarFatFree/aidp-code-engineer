#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Agent 原生 AIDP 运行包的确定性渲染、校验与原子安装。"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import time
from pathlib import Path
from typing import Callable, Dict, Optional

import scaffold_lib as L

RUNTIME_MANIFEST = ".aidp-runtime.json"
RUNTIME_HOME = {"claude": ".claude/aidp", "shared": ".agents/aidp"}
RUNTIME_DIRS = L.RUNTIME_DIRS
RUNTIME_EXCLUDES = L.RUNTIME_EXCLUDES
_TOKEN_RE = re.compile(r"\{\{[^{}]+\}\}")
_VERSION_RE = re.compile(r"^V\d+\.\d+\.\d+$")
_IGNORE_PATH_RE = re.compile(r"runtime-path-ignore:\s*\S+")


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


def _template_path_leaks(line: str, template_root: object) -> bool:
    if template_root is None:
        return False
    root = str(template_root).rstrip("/\\")
    if not root:
        return False
    normalized_line = line.replace("\\", "/")
    normalized_root = root.replace("\\", "/").rstrip("/")
    pattern = re.compile(
        r"(?<![A-Za-z0-9_.-])" + re.escape(normalized_root) + r"(?=$|/)",
        re.IGNORECASE if re.match(r"^[A-Za-z]:/", normalized_root) else 0,
    )
    return bool(pattern.search(normalized_line))


def render_text(text: str, home: str, template_root: object = None) -> str:
    """渲染 UTF-8 契约，并拒绝 token、旧路径和模板绝对路径泄露。"""
    if home not in RUNTIME_HOME.values():
        raise ValueError(f"未知 AIDP_HOME: {home}")
    for hardcoded_home in RUNTIME_HOME.values():
        if hardcoded_home in text:
            raise ValueError(f"模板必须使用 {{{{AIDP_HOME}}}}，不得硬编码 {hardcoded_home}")
    rendered = text.replace("{{AIDP_HOME}}", home)
    unknown = sorted(set(_TOKEN_RE.findall(rendered)))
    if unknown:
        raise ValueError(f"存在未解析运行占位符: {', '.join(unknown)}")
    for line_no, line in enumerate(rendered.splitlines(), 1):
        if ".aidp/" in line:
            raise ValueError(f"存在旧运行路径 .aidp/（第 {line_no} 行）")
        if _template_path_leaks(line, template_root) and not _IGNORE_PATH_RE.search(line):
            raise ValueError(f"存在模板根绝对路径泄露（第 {line_no} 行）")
    return rendered


def _validate_required_dirs(root: Path, label: str, error_type) -> None:
    if root.is_symlink() or not root.is_dir():
        raise error_type(f"{label}不是有效目录: {root}")
    for dirname in RUNTIME_DIRS:
        path = root / dirname
        if path.is_symlink() or not path.is_dir():
            raise error_type(f"{label}缺少真实目录: {dirname}")


def render_tree(source_root: Path, destination: Path, home: str) -> None:
    """把模板真源渲染到空目标目录。"""
    source_root, destination = Path(source_root), Path(destination)
    _validate_required_dirs(source_root, "运行包真源", RuntimeError)
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
                target.write_text(
                    render_text(data.decode("utf-8"), home, template_root=source_root),
                    encoding="utf-8",
                )
                shutil.copymode(source, target)
            else:
                shutil.copy2(source, target)


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _file_mode(path: Path) -> str:
    return format(stat.S_IMODE(path.stat().st_mode), "04o")


def _entry_mode(path: Path) -> str:
    return format(stat.S_IMODE(path.lstat().st_mode), "04o")


def _file_metadata(path: Path) -> dict:
    return {"sha256": _file_hash(path), "mode": _file_mode(path)}


def _runtime_files(runtime: Path):
    for path in sorted(runtime.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"运行包不得包含 symlink: {path}")
        if path.is_file() and path.name != RUNTIME_MANIFEST:
            yield path.relative_to(runtime).as_posix(), path


def _validate_source_home(source: str, home: str) -> None:
    expected = RUNTIME_HOME.get(source)
    if expected is None:
        raise ValueError(f"非法运行包 source: {source}")
    if home != expected:
        raise ValueError(f"运行包 source/home 不匹配: {source} 要求 {expected}，实际 {home}")


def _validate_version(version: object) -> str:
    if not isinstance(version, str) or not _VERSION_RE.fullmatch(version):
        raise ValueError(f"非法运行包版本: {version!r}")
    return version


def build_runtime_manifest(runtime: Path, version: str, source: str, home: str) -> dict:
    _validate_source_home(source, home)
    version = _validate_version(version)
    files = {relative: _file_metadata(path) for relative, path in _runtime_files(Path(runtime))}
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
    _validate_required_dirs(runtime, "运行包", ValueError)
    manifest = _read_manifest(runtime)
    if manifest.get("schema") != "aidp.runtime/v1":
        raise ValueError("运行包 manifest schema 非法")
    if manifest.get("source") not in RUNTIME_HOME:
        raise ValueError("运行包 manifest source 非法")
    _validate_version(manifest.get("version"))
    expected_files = manifest.get("files")
    if not isinstance(expected_files, dict):
        raise ValueError("运行包 manifest files 必须是对象")
    for relative, metadata in expected_files.items():
        if not isinstance(relative, str) or not isinstance(metadata, dict) \
                or set(metadata) != {"sha256", "mode"} \
                or not isinstance(metadata.get("sha256"), str) \
                or not re.fullmatch(r"[0-9a-f]{64}", metadata["sha256"]) \
                or not isinstance(metadata.get("mode"), str) \
                or not re.fullmatch(r"[0-7]{4}", metadata["mode"]):
            raise ValueError(f"运行包 manifest 文件元数据非法: {relative}")
    actual = {relative: _file_metadata(path) for relative, path in _runtime_files(runtime)}
    if dict(sorted(expected_files.items())) != dict(sorted(actual.items())):
        raise ValueError("运行包文件指纹漂移")
    home = expected_home or RUNTIME_HOME[manifest["source"]]
    _validate_source_home(manifest["source"], home)
    for relative, path in _runtime_files(runtime):
        data = path.read_bytes()
        if not _is_text(data):
            continue
        text = data.decode("utf-8")
        if _TOKEN_RE.search(text):
            raise ValueError(f"运行包含未解析占位符: {relative}")
        for line in text.splitlines():
            if ".aidp/" in line:
                raise ValueError(f"运行包含旧路径: {relative}")
        if "{{AIDP_HOME}}" in text:
            raise ValueError(f"运行包含未解析 AIDP_HOME: {relative}")
        for configured_home in RUNTIME_HOME.values():
            if configured_home != home and configured_home in text:
                raise ValueError(f"运行包含其他目标的 AIDP_HOME: {relative}")
    if home not in RUNTIME_HOME.values():
        raise ValueError(f"非法 expected_home: {home}")
    return manifest


def normalize_runtime(runtime: Path, home: str) -> Dict[str, dict]:
    """把运行根反向规范化为 token，并保留权限模式供双包比较。"""
    normalized = {}
    for relative, path in _runtime_files(Path(runtime)):
        data = path.read_bytes()
        if _is_text(data):
            data = data.decode("utf-8").replace(home, "{{AIDP_HOME}}").encode("utf-8")
        normalized[relative] = {"content": data, "mode": _file_mode(path)}
    return normalized


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    root = Path(root)
    if not _lexists(root):
        return digest.hexdigest()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(relative + b"\0")
        digest.update(_entry_mode(path).encode("ascii") + b"\0")
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
    actual = {relative: _file_metadata(path) for relative, path in _runtime_files(destination)}
    return dict(sorted(expected.items())) != dict(sorted(actual.items()))


def _write_manifest(runtime: Path, manifest: dict) -> None:
    (runtime / RUNTIME_MANIFEST).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _validate_backup(backup: Path, destination: Path, transaction: Path,
                     expected_digest: str) -> Path:
    backup = _lexical(Path(backup))
    destination = _lexical(destination)
    transaction = _lexical(transaction)
    if not _lexists(backup) or backup.is_symlink() or not backup.is_dir():
        raise RuntimeError(f"运行包备份不存在或不是独立目录: {backup}")
    try:
        backup.relative_to(destination)
        raise RuntimeError(f"运行包备份不得位于原运行包内部: {backup}")
    except ValueError:
        pass
    try:
        backup.relative_to(transaction)
        raise RuntimeError(f"运行包备份不得位于事务目录内部: {backup}")
    except ValueError:
        pass
    if backup == destination or backup == transaction:
        raise RuntimeError(f"运行包备份路径不独立: {backup}")
    if tree_digest(backup) != expected_digest:
        raise RuntimeError(f"运行包备份不完整: {backup}")
    return backup


def _acquire_runtime_lock(parent: Path, boundary: Path):
    lock = _assert_contained(parent / ".aidp-runtime.lock", boundary)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    try:
        fd = os.open(str(lock), flags, 0o600)
    except FileExistsError as exc:
        raise RuntimeError(f"运行包事务锁已存在: {lock}") from exc
    try:
        identity = os.fstat(fd)
        payload = f"pid={os.getpid()} time={time.time():.6f}\n".encode("ascii")
        os.write(fd, payload)
        os.fsync(fd)
        return lock, fd, (identity.st_dev, identity.st_ino)
    except Exception:
        os.close(fd)
        try:
            lock.unlink()
        except OSError:
            pass
        raise


def _release_runtime_lock(lock: Path, fd: int, identity) -> None:
    try:
        os.close(fd)
    finally:
        try:
            current = lock.lstat()
        except OSError:
            return
        if not lock.is_symlink() and (current.st_dev, current.st_ino) == identity:
            lock.unlink()


def render_runtime(source_root: Path, destination: Path, home: str, version: str,
                   source: str, backup_callback: Optional[Callable[[Path], Path]] = None,
                   replace_func: Callable[[object, object], None] = os.replace) -> dict:
    """在同父唯一事务目录内渲染并原子替换；失败恢复旧包。"""
    _validate_source_home(source, home)
    destination = Path(destination)
    boundary = _default_boundary(destination)
    destination = _assert_contained(destination, boundary)
    destination.parent.mkdir(parents=True, exist_ok=True)
    lock, lock_fd, lock_identity = _acquire_runtime_lock(destination.parent, boundary)
    try:
        transaction = Path(tempfile.mkdtemp(
            prefix=f".{destination.name}.aidp-txn-", dir=str(destination.parent)))
        transaction = _assert_contained(transaction, boundary)
        stage = transaction / "stage"
        previous = transaction / "previous"
        moved_old = False
        expected_destination_digest = None
        try:
            if _lexists(destination):
                if destination.is_symlink() or not destination.is_dir():
                    raise RuntimeError(f"运行包目标不是受管目录: {destination}")
                if not (destination / RUNTIME_MANIFEST).is_file():
                    raise RuntimeError(f"同名目录缺少运行包 manifest，拒绝覆盖: {destination}")
                expected_destination_digest = tree_digest(destination)
                if _runtime_modified(destination):
                    if backup_callback is None:
                        raise RuntimeError(f"运行包含用户修改，必须先完整备份: {destination}")
                    backup = backup_callback(destination)
                    if backup is None:
                        raise RuntimeError(f"运行包备份失败: {destination}")
                    _validate_backup(
                        Path(backup), destination, transaction, expected_destination_digest)
                    if tree_digest(destination) != expected_destination_digest:
                        raise RuntimeError("备份期间运行包发生并发修改，拒绝替换")

            stage.mkdir(parents=True, exist_ok=False)
            render_tree(Path(source_root), stage, home)
            manifest = build_runtime_manifest(
                stage, version=version, source=source, home=home)
            _write_manifest(stage, manifest)
            validate_runtime(stage, expected_home=home)
            if _lexists(destination):
                if tree_digest(destination) != expected_destination_digest:
                    raise RuntimeError("安装前运行包发生并发修改，拒绝替换")
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
                remove_tree_safely(previous, boundary=transaction)
                moved_old = False
            return manifest
        finally:
            if moved_old and _lexists(previous) and not _lexists(destination):
                replace_func(previous, destination)
                moved_old = False
            if _lexists(transaction):
                remove_tree_safely(transaction, boundary=destination.parent)
    finally:
        _release_runtime_lock(lock, lock_fd, lock_identity)
