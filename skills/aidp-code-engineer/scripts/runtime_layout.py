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
# 运行根下**唯一**归脚手架所有的顶层条目。⛔ 这是所有权边界：枚举、比对、替换、删除
# 一律只在这个集合内进行；集合之外的东西（运行根降到 `.claude` / `.agents` 之后，那里还住着
# Claude Code 的 settings.json、git 的 worktrees/、项目自有的 skill 与命令）**一律不碰**。
OWNED_TOPLEVEL = tuple(RUNTIME_DIRS) + (RUNTIME_MANIFEST,)


def owned_entries(root: Path):
    """运行根下受管的**直接子条目**（`commands/<file>`、`skills/<name>` 这一层）。

    替换粒度定在这一层而不是顶层目录：`commands/`、`skills/`、`agents/` 里可能混着项目自有的
    条目，整目录换掉等于把用户的东西删了。定在这一层，脚手架只换自己那几个、其余原地不动。
    """
    for dirname in RUNTIME_DIRS:
        base = root / dirname
        if not base.is_dir():
            continue
        for child in sorted(base.iterdir()):
            if L.is_ignored((dirname, child.name)):
                continue
            yield f"{dirname}/{child.name}", child


_TOKEN_RE = re.compile(r"\{\{AIDP_[A-Z0-9_]+\}\}")
_VERSION_RE = re.compile(r"^V\d+\.\d+\.\d+$")
_IGNORE_PATH_RE = re.compile(r"runtime-path-ignore:\s*\S+")
_OLD_RUNTIME_RE = re.compile(r"(?<!memory/)(?<![\w{])\.aidp/")


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
        if _OLD_RUNTIME_RE.search(line):
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
            # bundle 里 SKILL.md 被遮名成 SKILL.md.in，运行包必须落回安装名；
            # 真源是模板 `.aidp/` 时本调用为空操作（那边不存在遮名）。
            target = destination / L.bundle_unmask(relative)
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
                # 必须走字节写：manifest 指纹 / bundle 逐字比对 / 双包规范化三处都按 LF 字节算账，
                # 用 write_text 会在 Windows 上被翻成 CRLF，整包假漂移。
                L.write_text_lf(target, render_text(data.decode("utf-8"), home,
                                                    template_root=source_root))
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
    """运行包内受管文件。

    ⛔ 只走 `RUNTIME_DIRS`，不 rglob 整个运行根：运行根降到 `.claude` / `.agents` 之后，
    整根 rglob 会把 `settings.json`、`worktrees/` 这些**别人的东西**算进 manifest，
    于是它们既会被写进指纹、又会在下次替换时被当成"受管但已消失"删掉。
    """
    runtime = Path(runtime)
    candidates = []
    for dirname in RUNTIME_DIRS:
        base = runtime / dirname
        if base.is_dir():
            candidates.extend(sorted(base.rglob("*")))
    for path in candidates:
        relative = path.relative_to(runtime)
        if path.is_symlink():
            raise ValueError(f"运行包不得包含 symlink: {path}")
        if path.is_file() and path.stat().st_nlink != 1:
            raise ValueError(f"运行包不得包含 hardlink: {path}")
        if L.is_ignored(relative.parts):
            continue
        if path.is_file() and path.name != RUNTIME_MANIFEST:
            yield relative.as_posix(), path


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


def _user_owned_path(relative: str) -> bool:
    """这个相对路径**可以**归用户所有（因而要在重装时原样带过去）。

    ⛔ 这里只做"路径形状合法 + 落在受管目录内"的判定，**不再是白名单**。
    原先只认 `reference/`、`skills/custom/` 与 user-fillable 契约三类；运行根降到
    `.claude` / `.agents` 之后，`commands/`、`skills/`、`agents/` 里会混着项目自有的
    条目（参照项目 `.claude/skills/` 的 16 个里多数是项目自有），白名单一个都不覆盖 ——
    它们会在重装时被当成"受管但已消失"删掉。

    真正区分"谁的"不靠路径前缀，靠 manifest：`_user_overlay` 只把**不在 manifest 里**
    的条目当用户物。路径判定在这里只负责挡掉越界形状（`..`、反斜杠、空段）。
    """
    parts = relative.split("/")
    if not parts or any(part in {"", ".", ".."} or "\\" in part for part in parts):
        return False
    return parts[0] in RUNTIME_DIRS


def _manifest_user_files(manifest: dict, contract: Optional[set] = None) -> set:
    expected = manifest.get("files")
    if not isinstance(expected, dict):
        raise ValueError("运行包 manifest files 必须是对象")
    for relative, metadata in expected.items():
        if not isinstance(relative, str) or not isinstance(metadata, dict) \
                or set(metadata) != {"sha256", "mode"} \
                or not isinstance(metadata.get("sha256"), str) \
                or not re.fullmatch(r"[0-9a-f]{64}", metadata["sha256"]) \
                or not isinstance(metadata.get("mode"), str) \
                or not re.fullmatch(r"[0-7]{4}", metadata["mode"]):
            raise ValueError(f"运行包 manifest 文件元数据非法: {relative}")
    user_files = manifest.get("user_files", [])
    if not isinstance(user_files, list) or any(
            not isinstance(name, str) or not _user_owned_path(name)
            or name not in expected for name in user_files) \
            or len(user_files) != len(set(user_files)):
        raise ValueError("运行包 manifest user_files 非法")
    # ★ 真正的判据是「真源提不提供这个文件」，不是路径前缀：
    #   把契约文件谎称成用户文件，等于让它跨版本**被钉死**（新版内容永远盖不上去）。
    #   user-fillable 契约是例外 —— 它们按设计就是"发骨架、项目填内容"。
    if contract is not None:
        stolen = sorted(name for name in user_files
                        if name in contract and name not in L.USER_FILLABLE_CONTRACTS)
        if stolen:
            raise ValueError(f"运行包 manifest user_files 声称契约文件归用户所有：{stolen}")
    return set(user_files)


def _user_overlay(runtime: Path, home: str, source: str,
                  contract: Optional[set] = None) -> Dict[str, dict]:
    manifest = _read_manifest(runtime)
    if manifest.get("schema") != "aidp.runtime/v1" or manifest.get("source") != source:
        raise ValueError(f"运行包 manifest 身份非法: {runtime}")
    _validate_version(manifest.get("version"))
    user_files = _manifest_user_files(manifest, contract)
    expected = manifest["files"]
    actual = dict(_runtime_files(runtime))
    overlay = {}
    for relative, path in actual.items():
        if not _user_owned_path(relative):
            continue
        if relative in user_files or relative not in expected \
                or (relative in L.USER_FILLABLE_CONTRACTS
                    and _file_metadata(path) != expected[relative]):
            data = path.read_bytes()
            if _is_text(data):
                data = data.decode("utf-8").replace(home, "{{AIDP_HOME}}").encode("utf-8")
            overlay[relative] = {"content": data, "mode": _file_mode(path)}
    return overlay


def validate_runtime(runtime: Path, expected_home: Optional[str] = None) -> dict:
    runtime = Path(runtime)
    _validate_required_dirs(runtime, "运行包", ValueError)
    manifest = _read_manifest(runtime)
    if manifest.get("schema") != "aidp.runtime/v1":
        raise ValueError("运行包 manifest schema 非法")
    if manifest.get("source") not in RUNTIME_HOME:
        raise ValueError("运行包 manifest source 非法")
    _validate_version(manifest.get("version"))
    _manifest_user_files(manifest)
    expected_files = manifest["files"]
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
            if _OLD_RUNTIME_RE.search(line):
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
    L.write_text_lf(runtime / RUNTIME_MANIFEST,
                    json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


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


class _RuntimeLock:
    """进程级 advisory lock；锁文件持久存在，内核锁随 fd/进程释放。"""

    def __init__(self, path: Path, fd: int, backend: str):
        self.path = path
        self.fd = fd
        self.backend = backend
        self._released = False

    def release(self) -> None:
        if self._released:
            return
        try:
            if self.backend == "fcntl":
                import fcntl
                fcntl.flock(self.fd, fcntl.LOCK_UN)
            else:
                import msvcrt
                os.lseek(self.fd, 0, os.SEEK_SET)
                msvcrt.locking(self.fd, msvcrt.LK_UNLCK, 1)
        finally:
            os.close(self.fd)
            self._released = True

    def __enter__(self):
        return self

    def __exit__(self, _type, _value, _traceback):
        self.release()


def _verify_open_lock_identity(lock: Path, fd: int) -> os.stat_result:
    """打开后以 lstat/fstat 核实同一普通文件，避免 Windows symlink 竞态。"""
    descriptor = os.fstat(fd)
    try:
        pathname = os.lstat(str(lock))
    except OSError as exc:
        raise RuntimeError(f"运行包锁在打开后消失: {lock}") from exc
    if stat.S_ISLNK(pathname.st_mode) or not stat.S_ISREG(pathname.st_mode):
        raise RuntimeError(f"运行包锁路径非法: {lock}")
    if not stat.S_ISREG(descriptor.st_mode):
        raise RuntimeError(f"运行包锁 fd 不是普通文件: {lock}")
    if getattr(descriptor, "st_nlink", 0) != 1 or getattr(pathname, "st_nlink", 0) != 1:
        raise RuntimeError(f"运行包锁不得是 hardlink: {lock}")
    fd_identity = (getattr(descriptor, "st_dev", 0), getattr(descriptor, "st_ino", 0))
    path_identity = (getattr(pathname, "st_dev", 0), getattr(pathname, "st_ino", 0))
    if all(fd_identity) and all(path_identity) and fd_identity != path_identity:
        raise RuntimeError(f"运行包锁路径在打开期间被替换: {lock}")
    return descriptor


def _acquire_runtime_lock(parent: Path, boundary: Path,
                          _after_lock_precheck=None) -> _RuntimeLock:
    lock = _assert_contained(parent / ".aidp-runtime.lock", boundary)
    if _lexists(lock):
        info = os.lstat(str(lock))
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise RuntimeError(f"运行包锁路径非法: {lock}")
    if _after_lock_precheck is not None:
        _after_lock_precheck(lock)
    flags = os.O_CREAT | os.O_RDWR
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(str(lock), flags, 0o600)
    except OSError as exc:
        raise RuntimeError(f"运行包锁路径不可用: {lock}: {exc}") from exc
    backend = "msvcrt" if os.name == "nt" else "fcntl"
    try:
        info = _verify_open_lock_identity(lock, fd)
        if info.st_size < 1:
            _verify_open_lock_identity(lock, fd)
            os.lseek(fd, 0, os.SEEK_SET)
            os.write(fd, b"\0")
            os.fsync(fd)
        try:
            if backend == "fcntl":
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                import msvcrt
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except (BlockingIOError, OSError) as exc:
            raise RuntimeError(f"运行包事务锁正被其他进程持有: {lock}") from exc
        _verify_open_lock_identity(lock, fd)
        payload = f"pid={os.getpid()} time={time.time():.6f}\n".encode("ascii")
        os.ftruncate(fd, 0)
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, payload)
        os.fsync(fd)
        os.lseek(fd, 0, os.SEEK_SET)
        return _RuntimeLock(lock, fd, backend)
    except Exception:
        os.close(fd)
        raise


def _source_contract_files(source_root: Path):
    """真源提供的受管相对路径（安装名，已还原 bundle 遮名）。"""
    for dirname in RUNTIME_DIRS:
        base = source_root / dirname
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(source_root).as_posix()
            if L.is_ignored(path.relative_to(source_root).parts) or _excluded(relative):
                continue
            yield L.bundle_unmask(relative), path


def _owned_names(root: Path):
    """运行根下实际存在的受管条目名（`commands/a.md` 这一层 + manifest 自身）。"""
    names = [relative for relative, _path in owned_entries(root)]
    if (root / RUNTIME_MANIFEST).is_file():
        names.append(RUNTIME_MANIFEST)
    return names


def _park_owned(destination: Path, previous: Path, replace_func) -> None:
    """把旧运行包的**受管条目**挪到事务目录待命。

    ⛔ 不整目录搬走：运行根降到 `.claude` / `.agents` 之后，那里还住着 Claude Code 的
    `settings.json`、git 的 `worktrees/`、项目自有的 skill 与命令 —— 整目录搬走再换上新的，
    等于把它们一起删了。
    """
    previous.mkdir(parents=True, exist_ok=True)
    for relative in _owned_names(destination):
        src = destination / relative
        dst = previous / relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        replace_func(src, dst)


def _install_owned(stage: Path, destination: Path, replace_func) -> None:
    """把新运行包的受管条目搬到运行根；同样只碰受管条目。"""
    destination.mkdir(parents=True, exist_ok=True)
    for relative in _owned_names(stage):
        src = stage / relative
        dst = destination / relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        if _lexists(dst):
            raise RuntimeError(f"受管条目落点已被占用，拒绝覆盖: {dst}")
        replace_func(src, dst)


def _restore_owned(previous: Path, destination: Path, replace_func) -> None:
    """回滚：把待命区里的旧条目搬回原位，逐条覆盖本次已搬入的同名条目。

    ⛔ 只能按 `previous` 的条目逐个覆盖，**不得**先把运行根里所有受管条目清空再搬回：
    搬移到一半失败时，运行根里还留着**尚未搬走的幸存条目**，而它们并不在 `previous` 里 ——
    清空再搬回就把这批幸存者永久删掉了（回归 `test_replace_failure_restores_old_runtime`）。
    """
    destination.mkdir(parents=True, exist_ok=True)
    for relative in _owned_names(previous):
        src = previous / relative
        dst = destination / relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        if _lexists(dst):
            remove_tree_safely(dst, boundary=destination)
        replace_func(src, dst)


def render_runtime(source_root: Path, destination: Path, home: str, version: str,
                   source: str, backup_callback: Optional[Callable[[Path], Path]] = None,
                   replace_func: Callable[[object, object], None] = os.replace) -> dict:
    """在同父唯一事务目录内渲染并原子替换；失败恢复旧包。"""
    _validate_source_home(source, home)
    destination = Path(destination)
    boundary = _default_boundary(destination)
    destination = _assert_contained(destination, boundary)
    destination.parent.mkdir(parents=True, exist_ok=True)
    runtime_lock = _acquire_runtime_lock(destination.parent, boundary)
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

            contract = {relative for relative, _p in _source_contract_files(Path(source_root))}
            overlay = (_user_overlay(destination, home, source, contract)
                       if _lexists(destination) else {})
            counterpart = None
            counterpart_digest = None
            if destination == boundary / RUNTIME_HOME[source]:
                other_source = "shared" if source == "claude" else "claude"
                candidate = _assert_contained(boundary / RUNTIME_HOME[other_source], boundary)
                if _lexists(candidate):
                    if not candidate.is_dir() or not (candidate / RUNTIME_MANIFEST).is_file():
                        raise RuntimeError(f"双包运行目录未受管: {candidate}")
                    counterpart = candidate
                    counterpart_digest = tree_digest(candidate)
                    other_overlay = _user_overlay(candidate, RUNTIME_HOME[other_source],
                                                  other_source, contract)
                    for relative, entry in other_overlay.items():
                        if relative in overlay and overlay[relative] != entry:
                            raise RuntimeError(f"双包用户文件冲突: {relative}")
                        overlay[relative] = entry

            stage.mkdir(parents=True, exist_ok=False)
            render_tree(Path(source_root), stage, home)
            for relative, entry in sorted(overlay.items()):
                target = stage / relative
                if target.exists() and relative not in L.USER_FILLABLE_CONTRACTS:
                    rendered = target.read_bytes()
                    if _is_text(rendered):
                        rendered = rendered.decode("utf-8").replace(
                            home, "{{AIDP_HOME}}").encode("utf-8")
                    if entry != {"content": rendered, "mode": _file_mode(target)}:
                        raise RuntimeError(f"私有文件与新受管真源冲突: {relative}")
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    data = entry["content"]
                    if _is_text(data):
                        data = data.replace(b"{{AIDP_HOME}}", home.encode("utf-8"))
                    target.write_bytes(data)
                    target.chmod(int(entry["mode"], 8))
            manifest = build_runtime_manifest(
                stage, version=version, source=source, home=home)
            if overlay:
                manifest["user_files"] = sorted(overlay)
            _write_manifest(stage, manifest)
            validate_runtime(stage, expected_home=home)
            if counterpart is not None and tree_digest(counterpart) != counterpart_digest:
                raise RuntimeError("安装前另一运行包发生并发修改，拒绝替换")
            if _lexists(destination):
                if tree_digest(destination) != expected_destination_digest:
                    raise RuntimeError("安装前运行包发生并发修改，拒绝替换")
                # ⛔ 先置位再搬：逐条目搬移是**多步**的，搬到一半炸掉时运行根已经半空，
                #    此时必须让 finally 的回滚接手。置位放在搬完之后 = 中途失败无人兜底。
                moved_old = True
                _park_owned(destination, previous, replace_func)
            try:
                _install_owned(stage, destination, replace_func)
            except Exception:
                if moved_old:
                    _restore_owned(previous, destination, replace_func)
                    moved_old = False
                raise
            if _lexists(previous):
                remove_tree_safely(previous, boundary=transaction)
                moved_old = False
            return manifest
        finally:
            if moved_old and _lexists(previous):
                _restore_owned(previous, destination, replace_func)
                moved_old = False
            if _lexists(transaction):
                remove_tree_safely(transaction, boundary=destination.parent)
    finally:
        runtime_lock.release()
