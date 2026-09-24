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
# 运行包互斥锁：本机运行态（0 字节载体，按设计释放后保留供下次复用），不入库。
RUNTIME_LOCK = ".aidp-runtime.lock"
# 运行根即 Agent 自己的目录，契约平铺其下（对齐 Claude Code 原生发现路径：
# .claude/agents|commands|skills|hooks 都是官方位置，套一层 aidp/ 等于谁也发现不了）。
# 所有权边界见 OWNED_TOPLEVEL：运行根里还住着 settings.json / worktrees/ 与项目自有条目。
RUNTIME_HOME = {"claude": ".claude", "shared": ".agents"}
RUNTIME_DIRS = L.RUNTIME_DIRS
RUNTIME_EXCLUDES = L.RUNTIME_EXCLUDES
# 运行根下**唯一**归脚手架所有的顶层条目。⛔ 这是所有权边界：枚举、比对、替换、删除
# 一律只在这个集合内进行；集合之外的东西（运行根降到 `.claude` / `.agents` 之后，那里还住着
# Claude Code 的 settings.json、git 的 worktrees/、项目自有的 skill 与命令）**一律不碰**。
OWNED_TOPLEVEL = tuple(RUNTIME_DIRS) + (RUNTIME_MANIFEST,)


def _runtime_ignored(rel_parts) -> bool:
    """**已安装运行包内**的忽略口径：只排除纯派生物（`__pycache__/`、`*.pyc`）。

    ⛔ 这里绝不能复用 `scaffold_lib.is_ignored` —— 那是**镜像 / 下发**口径，它额外排除
    `config.json`、`.env`、`auth.*.json`，为的是不把凭据打进 bundle。在已安装的运行包里
    这批名字的含义正好**相反**：它们是用户自己填的凭据，`{{AIDP_HOME}}/skills/*/config.json`
    本就是范式内的落点（见 `scripts/autopilot_unfreeze.py` 的解冻扫描）。
    沿用下发口径的后果是它们对重装**完全隐形**：既不进 manifest 指纹（于是
    `_runtime_modified` 看不见、不触发备份），也不进 `_user_overlay`（于是重装时
    随 `previous` 一起被丢弃）——凭据 + gitignore + 无备份 = 不可恢复，直接违反
    「升级不丢项目自有内容」。
    """
    parts = list(rel_parts)
    if any(part in L.IGNORE_DIRS for part in parts):
        return True
    name = parts[-1] if parts else ""
    return Path(name).suffix in L.IGNORE_SUFFIX


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
            relative = f"{dirname}/{child.name}"
            if _runtime_ignored((dirname, child.name)) or _excluded(relative):
                continue
            yield relative, child


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
    # 运行根就是 `.claude` / `.agents` 本身，其父目录即项目根 = 受管边界。
    # （历史嵌套形态 `.claude/aidp` 的父目录是 `.claude`，需再上一级，故两支都留。）
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


def _reject_hardcoded_home(text: str, home: str) -> None:
    """契约正文不得把**别的 Agent 的**运行根写死（该用 `{{AIDP_HOME}}`）。

    判据有四层收窄，缺一不可：
    1. **只查非本次渲染目标的那个运行根** —— 运行根降层后就是 `.claude` / `.agents` 本身，
       渲染进 `.claude` 的包里出现 `.claude/commands/` 与 `{{AIDP_HOME}}/commands/` 渲染结果
       逐字相同、无害；真正会出错的是把**另一个** Agent 的根烙进去（`.agents/...` 进了
       Claude 包），那才是这道门存在的理由。
    2. **只认「运行根 + 受管目录」**，不认运行根裸串 —— 正文里合法地提到
       `.claude/settings.json`、`.claude/skills/aidp-code-engineer` 这类非运行契约的落点。
    3. **排除 `~/` 前缀** —— `~/.claude/plugins/cache/…` 是用户级路径，与项目运行根无关；
       `reference/skills.md` 正是靠"项目级 vs 用户级"的对比在讲清楚一件事。
    4. **认 `runtime-path-ignore:` 豁免** —— 适配位对照表要逐字写出两个 Agent 的目录。
    """
    foreign = [value for value in RUNTIME_HOME.values() if value != home]
    for line_no, line in enumerate(text.splitlines(), 1):
        if _IGNORE_PATH_RE.search(line):
            continue
        for hardcoded_home in foreign:
            for owned in RUNTIME_DIRS:
                needle = f"{hardcoded_home}/{owned}/"
                index = line.find(needle)
                while index != -1:
                    if line[max(0, index - 2):index] != "~/":
                        raise ValueError(
                            f"模板必须使用 {{{{AIDP_HOME}}}}，不得硬编码 {needle}（第 {line_no} 行）")
                    index = line.find(needle, index + 1)


def render_text(text: str, home: str, template_root: object = None) -> str:
    """渲染 UTF-8 契约，并拒绝 token、旧路径和模板绝对路径泄露。"""
    if home not in RUNTIME_HOME.values():
        raise ValueError(f"未知 AIDP_HOME: {home}")
    _reject_hardcoded_home(text, home)
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
        if _runtime_ignored(relative.parts):
            continue
        # ⛔ 必须应用 RUNTIME_EXCLUDES：运行根降层之后，脚手架 skill 装在
        #    `skills/aidp-code-engineer/` —— 那是**安装器自身**、不是运行契约，
        #    它的 SKILL.md 里合法地写着 `.aidp/`（维护文档）。不排除的话：
        #    ① 旧路径检查当场判红；② 它的文件被算成"运行包多出来的"造成指纹漂移。
        if _excluded(relative.as_posix()):
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


ADAPTER_MARKER = ".aidp-generated"


def _adapter_generated(runtime: Path, relative: str) -> bool:
    """这个条目属于**适配层产物**（`agent_sync` 生成的入口），既非运行契约也非用户文件。

    降层之后适配层会把插件 SKILL 命名空间写进 `skills/<plugin>/` —— 那正落在运行包自己的
    受管目录里。不排除它：① 会被当成用户文件跨版本携带；② Claude 包与 shared 包各自生成的
    内容不同，双包比对当场报"用户文件冲突"，升级直接失败。判据用适配层自己的生成标记。
    """
    parts = relative.split("/")
    for depth in range(1, len(parts)):
        if (runtime.joinpath(*parts[:depth]) / ADAPTER_MARKER).is_file():
            return True
    return False


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
        if not _user_owned_path(relative) or _adapter_generated(runtime, relative):
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
    # ⛔ 判据是「清单内的文件缺了或变了」，不是「实际集合与清单完全相等」：
    #    运行根降层之后那批目录是**共享的** —— 脚手架 skill 装在 `skills/aidp-code-engineer/`、
    #    插件 namespace 由 agent_sync 铺在 `skills/<plugin>/`、项目还会有自有的 skill 与命令。
    #    按"完全相等"判，这些统统算漂移，而它们本就不归运行包管。
    missing = sorted(set(expected_files) - set(actual))
    changed = sorted(name for name, meta in expected_files.items()
                     if name in actual and actual[name] != meta)
    if missing or changed:
        detail = []
        if missing:
            detail.append(f"缺失 {len(missing)} 个（{'、'.join(missing[:3])}）")
        if changed:
            detail.append(f"改动 {len(changed)} 个（{'、'.join(changed[:3])}）")
        raise ValueError("运行包文件指纹漂移：" + "；".join(detail))
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
        # 与 `_reject_hardcoded_home` 同一口径：只查「别的 Agent 的运行根 + 受管目录」，
        # 且认 `runtime-path-ignore` 豁免。按裸串查会把适配位对照表（必须同时写出
        # `.claude/skills/` 与 `.agents/skills/`）整片判红，而那些行正是要逐字写出来的。
        for line in text.splitlines():
            if _IGNORE_PATH_RE.search(line):
                continue
            for configured_home in RUNTIME_HOME.values():
                if configured_home == home:
                    continue
                for owned in RUNTIME_DIRS:
                    needle = f"{configured_home}/{owned}/"
                    index = line.find(needle)
                    while index != -1:
                        if line[max(0, index - 2):index] != "~/":
                            raise ValueError(
                                f"运行包含其他目标的 AIDP_HOME: {relative}（{needle}）")
                        index = line.find(needle, index + 1)
    if home not in RUNTIME_HOME.values():
        raise ValueError(f"非法 expected_home: {home}")
    return manifest


# Agent 自己在运行根下拥有的**非运行契约**条目。降层后运行根与 Agent 目录同名，
# `.claude/settings.json` 这类字面量与 `{{AIDP_HOME}}/commands/` 这类渲染产物混在同一行里，
# 只能靠"后面跟的是谁的东西"区分。⛔ 这个名单只收**确定不属于运行契约**的条目。
AGENT_OWNED_ENTRIES = frozenset({
    "settings.json", "settings.local.json", "worktrees",
    "hooks.json", "mcp.json", "config.toml", "statsig", "ide",
})
_LEADING_SEGMENT_RE = re.compile(r"[A-Za-z0-9_.-]+")


def _restore_home_token(line: str, home: str) -> str:
    """把渲染出的运行根反解回 `{{AIDP_HOME}}`，**只认渲染端会产出的两种形态**。

    渲染端只做一件事：`{{AIDP_HOME}}` → home。于是反解的合法输入也只有两种 ——
    `home/<受管目录>` 与裸 `home/`（其后不接标识符字符）。

    ⛔ 不能无差别 `line.replace(home, token)`：`.claude/settings.json` 里的 `.claude`
    不是运行路径而是 Agent 目录，反解后 Claude 包会变成 `{{AIDP_HOME}}/settings.json`、
    shared 包保持原样 —— 双包规范化当场分叉，而两包本该规范化成同一份。
    """
    out, index = [], 0
    needle = home + "/"
    while True:
        found = line.find(needle, index)
        if found == -1:
            out.append(line[index:])
            break
        out.append(line[index:found])
        rest = line[found + len(needle):]
        segment = _LEADING_SEGMENT_RE.match(rest)
        literal = (line[max(0, found - 2):found] == "~/"         # 用户级路径 `~/.claude/...`
                   or (segment and segment.group(0) in AGENT_OWNED_ENTRIES))
        out.append(needle if literal else "{{AIDP_HOME}}/")
        index = found + len(needle)
    line = "".join(out)
    # 裸运行根（后面不接 `/`，如用户文件内容 "new .claude"）：同样要反解，
    # 否则双包比较会因这类内容天然不同而分叉。`~` 前缀仍排除。
    out, index = [], 0
    while True:
        found = line.find(home, index)
        if found == -1:
            out.append(line[index:])
            break
        after = line[found + len(home): found + len(home) + 1]
        out.append(line[index:found])
        keep = after == "/" or line[max(0, found - 1):found] == "~" or after.isalnum()
        out.append(home if keep else "{{AIDP_HOME}}")
        index = found + len(home)
    return "".join(out)


def rendered_from_source(source_root: Path, home: str) -> Dict[str, dict]:
    """真源按 `home` 渲染后的**期望内容**（安装名 + 内容 + 权限）。

    ★ 双包一致性的判据用它，而不是"把各自运行根反解回 token 再比"：降层之后运行根字符串
    与 Agent 自有路径同名（`.claude/settings.json` 与 `{{AIDP_HOME}}/commands/` 同现一行），
    反解无法可靠区分谁是渲染产物、谁是本来就该写死的字面量 —— 那条路是结构性不可判定的。
    直接比"包 == 同一真源按各自 home 渲染的结果"既无歧义，又比反解更强。
    """
    expected = {}
    for relative, path in _source_contract_files(Path(source_root)):
        data = path.read_bytes()
        if _is_text(data):
            data = render_text(data.decode("utf-8"), home,
                               template_root=source_root).encode("utf-8")
        expected[relative] = {"content": data, "mode": _file_mode(path)}
    return expected


def packages_share_one_source(packages, source_root: Path) -> bool:
    """`packages` = [(运行包路径, home), …]：两包是否**一致**。

    分两侧判，缺一不可：
    · **契约侧** —— 每个包里由真源提供的文件，必须逐字等于该真源按自己 home 渲染的结果。
    · **用户侧** —— manifest 登记的 `user_files`（项目自己填的、跨包同步的那些）在两包间
      规范化后必须相同；它们不在真源里，只能靠反解比较。

    ⛔ 别退回"整包反解后相等"：运行根降层后运行根字符串与 Agent 自有路径同名，
    契约正文里的字面量无法与渲染产物区分，那条路结构性不可判定（见 `_restore_home_token`）。
    """
    user_views = []
    for runtime, home in packages:
        runtime = Path(runtime)
        expected = rendered_from_source(Path(source_root), home)
        # ⛔ 适配层产物（agent_sync 生成的插件 SKILL 命名空间）要排除：它落在运行包的受管目录里，
        #    但既不是契约（真源里没有）也不是用户物，两包各自生成的内容还不同 —— 算进来必然判不一致。
        actual = {relative: {"content": path.read_bytes(), "mode": _file_mode(path)}
                  for relative, path in _runtime_files(runtime)
                  if not _adapter_generated(runtime, relative)}
        user_names = set(_read_manifest(runtime).get("user_files") or []) \
            if (runtime / RUNTIME_MANIFEST).is_file() else set()
        contract_actual = {k: v for k, v in actual.items() if k not in user_names}
        if contract_actual != {k: v for k, v in expected.items() if k not in user_names}:
            return False
        user_views.append({k: normalize_runtime(runtime, home)[k]
                           for k in user_names if k in actual})
    return all(view == user_views[0] for view in user_views[1:])


def normalize_runtime(runtime: Path, home: str) -> Dict[str, dict]:
    """把运行根反向规范化为 token，并保留权限模式供双包比较。

    ⛔ 带 `runtime-path-ignore` 的行**原样保留**，与渲染端同口径：那些是适配位对照表，
    逐字写着各 Agent 的目录（`.claude/skills/` 与 `.agents/skills/` 同现一行）。
    若在这里也做反解，Claude 包会把 `.claude/...` 变成 token、shared 包不会，
    双包比较当场分叉 —— 而两包本就该规范化成同一份。
    """
    normalized = {}
    for relative, path in _runtime_files(Path(runtime)):
        data = path.read_bytes()
        if _is_text(data):
            lines = data.decode("utf-8").split("\n")
            data = "\n".join(line if _IGNORE_PATH_RE.search(line)
                             else _restore_home_token(line, home)
                             for line in lines).encode("utf-8")
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
    lock = _assert_contained(parent / RUNTIME_LOCK, boundary)
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
                # ⛔ 判据是「像不像一个未受管的运行包」，不是「目录在不在」：运行根降层后就是
                #    `.claude` / `.agents` 本身，它们作为 Agent 标记目录在首次安装前**本来就存在**
                #    （里面可能已有 settings.json）。按"存在即必须有 manifest"判会让 init 直接失败。
                #    真正要拦的是：里面已有受管目录却没有 manifest —— 那是来路不明的同名运行包。
                if not (destination / RUNTIME_MANIFEST).is_file():
                    # ⛔ 安装器自身不算占位：下游把脚手架 skill 装在 `<运行根>/skills/` 下
                    #    （自举形态），那会让 `skills/` 先于运行包存在 —— 按"有受管目录即拒"
                    #    会把正常的首次安装挡死。只有**除它以外**还有内容才算来路不明的运行包。
                    def _occupied(name: str) -> bool:
                        directory = destination / name
                        if not directory.is_dir():
                            return False
                        return any(child.name != L.SKILL_NAME for child in directory.iterdir())

                    squatters = sorted(name for name in RUNTIME_DIRS if _occupied(name))
                    if squatters:
                        raise RuntimeError(
                            f"同名目录已有受管目录却缺运行包 manifest，拒绝覆盖: {destination}"
                            f"（{'、'.join(squatters[:4])}）")
                expected_destination_digest = tree_digest(destination)
                # 首次接管（目录已在、但还没装过）无 manifest 可比，谈不上"被改过"。
                if (destination / RUNTIME_MANIFEST).is_file() and _runtime_modified(destination):
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
            # 用户物叠加要读上一版 manifest —— 只有**装过**才有。运行根降层后目录本身可能
            # 早已存在（Agent 标记目录），按"目录在不在"触发会去读不存在的 manifest。
            overlay = (_user_overlay(destination, home, source, contract)
                       if (destination / RUNTIME_MANIFEST).is_file() else {})
            counterpart = None
            counterpart_digest = None
            if destination == boundary / RUNTIME_HOME[source]:
                other_source = "shared" if source == "claude" else "claude"
                candidate = _assert_contained(boundary / RUNTIME_HOME[other_source], boundary)
                if (candidate / RUNTIME_MANIFEST).is_file():
                    if not candidate.is_dir():
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
