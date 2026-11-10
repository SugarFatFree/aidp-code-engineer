#!/usr/bin/env python3
"""冻结日常任务/正式 Sprint 入口身份，给命令编排提供可执行路由门。

resolve 创建或继承上下文；route 只读给出阶段动作，--action 可作单动作门。
revise 显式扩展写集并提升 revision，使旧 scope/运行/审查证据失效。
check/complete 仅核验本任务已授权的静态/测试/审查证据，机器报告仅落运行目录。
普通入口默认 light；显式 Sprint 或 version/full/batch/autopilot 才是 formal。
此模块从不分配 Sprint、建分支或改 activeContext/progress/baseline。
校验和用于本地数据完整性，不是防恶意伪造签名。
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, nullcontext
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import stat
from functools import lru_cache
import sys
import tempfile
import time
import uuid

_script_dir = str(Path(__file__).resolve().parent)
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)
from aidp_paths import ensure_runtime_dir, runtime_dir
import execution_policy as policy

SCHEMA = 1
FORMAL_ENTRIES = frozenset(("version", "sprint-full", "sprint-batch", "sprint-autopilot"))
ENTRIES = frozenset(("sprint-dev", "start", "test", "bugfix", "close", "sprint-aiauto-test", "sprint-requirements",
                     "sprint-design", "sprint-plan", "sprint-selftest")) | FORMAL_ENTRIES
ALIASES = {"sprint-start": "start", "sprint-test": "test", "sprint-bugfix": "bugfix",
           "sprint-close": "close", "sprint-version": "version"}
LIGHT_ACTIONS = {
    "route": ("read-context",),
    "prepare": ("read-context",),
    "dev": ("read-context", "implement", "related-test"),
    "test": ("read-context", "related-test", "family-ledger"),
    "repair": ("read-context", "implement", "related-test", "review", "family-ledger"),
    "close": ("read-context", "related-test", "review", "family-ledger", "task-summary"),
}
LIGHT_FORBIDDEN = ("allocate-sprint", "create-contract", "start-sprint", "close-sprint",
                   "archive", "reset-active", "cascade")
FORMAL_ACTIONS = {
    "route": ("read-context", "formal-gates"),
    "prepare": ("read-context", "formal-gates", "create-contract", "start-sprint"),
    "dev": ("read-context", "formal-gates", "implement", "related-test"),
    "test": ("read-context", "formal-gates", "sprint-test", "family-ledger"),
    "repair": ("read-context", "formal-gates", "implement", "sprint-test", "review", "family-ledger"),
    "close": ("read-context", "formal-gates", "sprint-test", "review", "family-ledger",
              "close-sprint", "archive", "reset-active"),
}
IDENTITY_FIELDS = ("schema", "root", "mode", "task_id", "version", "since", "git_status",
                   "entry", "revision", "scope_revision", "authorization_revision", "write_set", "acceptance", "preexisting_dirty") + policy.POLICY_FIELDS


class ContextError(ValueError):
    """身份、路径或证据冲突；调用方必须停止当前动作。"""


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode("utf-8")).hexdigest()


def context_identity(ctx):
    """scope/run/review 共用的稳定全身份；生命周期字段不参与摘要。"""
    identity = {name: ctx[name] for name in IDENTITY_FIELDS}
    identity["initial_files_hash"] = _digest(ctx["initial_files"])
    identity["initial_gitlinks_hash"] = _digest(ctx.get("initial_gitlinks", {}))
    if ctx.get("initial_git_files"):
        identity["initial_git_files_hash"] = _digest(ctx["initial_git_files"])
    if "build_id" in ctx:
        identity["build_id"] = ctx["build_id"]
    if ctx["mode"] == "formal":
        identity["sprint"] = ctx["sprint"]
    if "parent_task_id" in ctx:
        identity["parent_task_id"] = ctx["parent_task_id"]
        identity["parent_identity_hash"] = ctx["parent_identity_hash"]
        if "inherit_action_limit" in ctx:
            identity["inherit_action_limit"] = ctx["inherit_action_limit"]
    return identity


def evidence_identity(ctx):
    """实质任务范围身份；授权修订不等于代码变化，动作类型由证据自身和完成门验真。"""
    identity = context_identity(ctx)
    identity["revision"] = ctx["scope_revision"]
    for field in ("authorization_revision", "authorization_source", "execution_budget",
                  "allowed_actions", "verification_level", "parent_identity_hash", "inherit_action_limit"):
        identity.pop(field, None)
    return identity


def identity_hash(ctx):
    return _digest(context_identity(ctx))


def initial_file_hash(path):
    """与测试账本一致的内容/权限/链接摘要；初始已删除文件为 None。"""
    from test_ledger import file_hash
    path = Path(path)
    if not path.exists() and not path.is_symlink():
        return None
    return file_hash(path)


@lru_cache(maxsize=4096)
def _committed_file_hash(root, repo, revision, relative, mode):
    result = _git(Path(root) / repo, "show", revision + ":" + relative)
    if result.returncode:
        raise ContextError("UNVERIFIED：任务起点文件内容不可读取：" + relative)
    return _digest({"sha256": hashlib.sha256(result.stdout).hexdigest(), "mode": mode, "link": None})


def initial_hash(root, ctx, relative):
    """只在实际验证候选文件时读取冻结 Git 内容，干净全仓不在 resolve 时 hash。"""
    lazy = ctx.get("initial_git_files", {}).get(relative)
    if lazy is None:
        return ctx["initial_files"].get(relative)
    return _committed_file_hash(str(Path(root).resolve()), lazy["repo"], lazy["revision"], lazy["path"], lazy["mode"])


def _root(value):
    root = Path(value).resolve()
    if not root.is_dir():
        raise ContextError("root 必须是现存目录")
    return root


def _safe_inside(root, path):
    """拒绝词法逃逸及符号链接；运行状态不能借链接写到另一项目。"""
    try:
        rel = path.relative_to(root)
    except ValueError as exc:
        raise ContextError("路径必须位于当前 root 内") from exc
    if ".." in rel.parts:
        raise ContextError("路径不能包含 ..")
    cursor = root
    for part in rel.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ContextError(f"上下文/写集路径不能经过符号链接：{cursor}")
    return path


def _context_base(root):
    return _safe_inside(root, Path(runtime_dir(root)) / "entry-contexts")


def _context_path(root, task_id):
    return _safe_inside(root, _context_base(root) / task_id / "context.json")


def _relative_path(root, value):
    if not isinstance(value, str) or not value or "\\" in value:
        raise ContextError("写集必须是非空项目相对路径")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() == "." or ".git" in path.parts:
        raise ContextError(f"非法项目相对路径：{value}")
    normalized = path.as_posix()
    target = _safe_inside(root, root / normalized)
    runtime = Path(runtime_dir(root))
    if target == runtime or runtime in target.parents:
        raise ContextError("写集不能包含运行时状态目录")
    return normalized


def _write_set(root, paths):
    return sorted({_relative_path(root, path) for path in (paths or ())})


def _acceptance(values):
    if not isinstance(values, (list, tuple)) or any(not isinstance(v, str) or not v.strip() for v in values):
        raise ContextError("acceptance 必须是非空文本数组（可以无条目）")
    return list(dict.fromkeys(v.strip() for v in values))


def _entry(value):
    value = ALIASES.get(value, value)
    if value not in ENTRIES:
        raise ContextError(f"未知入口：{value}")
    return value


def _validate(root, ctx):
    if not isinstance(ctx, dict) or ctx.get("schema") != SCHEMA:
        raise ContextError("上下文 schema 无效")
    if ctx.get("root") != str(root) or ctx.get("mode") not in ("light", "formal"):
        raise ContextError("上下文 root/mode 与当前请求不符")
    try:
        if str(uuid.UUID(ctx["task_id"])) != ctx["task_id"]:
            raise ValueError("noncanonical UUID")
    except (KeyError, ValueError, TypeError, AttributeError) as exc:
        raise ContextError("上下文 task_id 必须为规范 UUID") from exc
    if not re.fullmatch(r"V[0-9][A-Za-z0-9._-]*", str(ctx.get("version", ""))):
        raise ContextError("上下文 version 必须以 V 和数字开头")
    if ctx["mode"] == "light" and "sprint" in ctx:
        raise ContextError("light 上下文不能带 Sprint 身份")
    if ctx["mode"] == "formal" and ("sprint" not in ctx or
            (ctx["sprint"] is not None and not re.fullmatch(r"[0-9]{3,}", str(ctx["sprint"])) )):
        raise ContextError("formal sprint 必须为 NNN 或 null（尚未由原流程分配）")
    if ctx.get("git_status") not in ("supported", "unsupported"):
        raise ContextError("缺少明确的 Git 支持状态")
    if ctx["git_status"] == "supported":
        if not isinstance(ctx.get("since"), str) or not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", ctx["since"]):
            raise ContextError("since 必须为任务起点完整 commit SHA")
    elif ctx.get("since") is not None:
        raise ContextError("无 Git 起点时 since 必须为 null")
    if any(type(ctx.get(key)) is not int or ctx[key] < 1 for key in ("revision", "scope_revision", "authorization_revision")):
        raise ContextError("revision 必须为正整数")
    if _entry(ctx.get("entry")) != ctx["entry"]:
        raise ContextError("上下文入口必须规范化")
    if ctx["mode"] == "light" and ctx["entry"] in FORMAL_ENTRIES:
        raise ContextError("正式入口不能伪装为轻量上下文")
    if not isinstance(ctx.get("write_set"), list) or _write_set(root, ctx["write_set"]) != ctx["write_set"]:
        raise ContextError("上下文 write_set 非规范路径列表")
    if _acceptance(ctx.get("acceptance")) != ctx["acceptance"]:
        raise ContextError("上下文 acceptance 非规范文本列表")
    files = ctx.get("initial_files")
    dirty = ctx.get("preexisting_dirty")
    if not isinstance(files, dict) or not isinstance(dirty, list) or any(not isinstance(p, str) for p in dirty):
        raise ContextError("上下文缺少初始工作树快照")
    # 初始快照只是已冻结的历史路径，不重新要求文件存在或链接仍维持原状。
    for path, digest in files.items():
        rel = PurePosixPath(path)
        if (not path or rel.is_absolute() or ".." in rel.parts or ".git" in rel.parts
                or (digest is not None and not re.fullmatch(r"[0-9a-f]{64}", str(digest)))):
            raise ContextError("初始工作树快照包含非法路径或摘要")
    if dirty != sorted(set(dirty)) or any(p not in files for p in dirty):
        raise ContextError("preexisting_dirty 必须是初始快照中的规范路径列表")
    lazy = ctx.get("initial_git_files", {})
    if not isinstance(lazy, dict):
        raise ContextError("延迟 Git 基线必须为映射")
    for path, item in lazy.items():
        if (path not in files or files[path] is not None or not isinstance(item, dict) or
                set(item) != {"repo", "revision", "path", "mode"} or
                not isinstance(item["mode"], int) or not 0 <= item["mode"] <= 0o7777 or
                not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", str(item["revision"]))):
            raise ContextError("延迟 Git 基线格式无效")
        for name in (item["repo"], item["path"]):
            if not isinstance(name, str) or PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts or ".git" in PurePosixPath(name).parts:
                raise ContextError("延迟 Git 基线路径非法")
    gitlinks = ctx.get("initial_gitlinks", {})
    if not isinstance(gitlinks, dict):
        raise ContextError("initial_gitlinks 必须为子模块 pin 字典")
    for path, pins in gitlinks.items():
        rel = PurePosixPath(path)
        if (not path or rel.is_absolute() or ".." in rel.parts or ".git" in rel.parts
                or not isinstance(pins, dict) or set(pins) != {"index", "committed", "head"}
                or pins["head"] is None or any(value is not None and not re.fullmatch(
                    r"(?:[0-9a-f]{40}|[0-9a-f]{64})", str(value)) for value in pins.values())):
            raise ContextError("子模块初始 pin 快照格式无效")
    if "parent_task_id" in ctx:
        try:
            valid_parent = str(uuid.UUID(ctx["parent_task_id"])) == ctx["parent_task_id"]
        except (TypeError, ValueError, AttributeError):
            valid_parent = False
        if (ctx["mode"] != "formal" or not valid_parent or ctx["parent_task_id"] == ctx["task_id"]
                or not re.fullmatch(r"[0-9a-f]{64}", str(ctx.get("parent_identity_hash", "")))):
            raise ContextError("正式子任务的父身份无效")
    elif "parent_identity_hash" in ctx:
        raise ContextError("parent_identity_hash 缺少 parent_task_id")
    if ctx.get("status") not in ("active", "completed"):
        raise ContextError("未知任务生命周期状态")
    if any(field not in ctx for field in policy.POLICY_FIELDS):
        raise ContextError("旧上下文缺少执行策略；不能从旧 template/formal 自动恢复重型授权")
    policy.validate_policy(ctx)
    if "parent_task_id" not in ctx:
        for source in ctx["authorization_source"]:
            _check_source_version(source, ctx["version"])
    if ctx.get("identity_hash") != identity_hash(ctx):
        raise ContextError("冻结身份已变化；写集扩展必须显式 revise")
    if ctx.get("checksum") != _digest({k: v for k, v in ctx.items() if k != "checksum"}):
        raise ContextError("上下文 checksum 不匹配")
    return ctx


def _migrate_legacy_context(root, source, ctx):
    """验旧签名后原位降权迁移，保留 task_id/起点/原 Sprint，不重放旧模板动作。"""
    if not isinstance(ctx, dict) or "scope_revision" in ctx:
        return ctx
    try:
        task_id = str(uuid.UUID(ctx["task_id"]))
    except (KeyError, ValueError, TypeError) as exc:
        raise ContextError("旧上下文 task_id 无效") from exc
    if ctx.get("root") != str(root) or source != _context_path(root, task_id):
        raise ContextError("旧上下文不在当前任务唯一位置")
    lock = _safe_inside(root, source.with_name("context.lock"))
    with lock.open("a+b") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            ctx = json.loads(source.read_text(encoding="utf-8"))
            if "scope_revision" in ctx:
                return ctx
            if ctx.get("checksum") != _digest({key: value for key, value in ctx.items() if key != "checksum"}):
                raise ContextError("旧上下文 checksum 不匹配")
            legacy_fields = [name for name in IDENTITY_FIELDS
                             if name not in (*policy.POLICY_FIELDS, "scope_revision", "authorization_revision")]
            old_identity = {name: ctx[name] for name in legacy_fields}
            old_identity["initial_files_hash"] = _digest(ctx["initial_files"])
            old_identity["initial_gitlinks_hash"] = _digest(ctx.get("initial_gitlinks", {}))
            if ctx["mode"] == "formal":
                old_identity["sprint"] = ctx["sprint"]
            if "parent_task_id" in ctx:
                old_identity.update(parent_task_id=ctx["parent_task_id"], parent_identity_hash=ctx["parent_identity_hash"])
            if all(field in ctx for field in policy.POLICY_FIELDS):
                old_identity.update({field: ctx[field] for field in policy.POLICY_FIELDS})
            if ctx.get("identity_hash") != _digest(old_identity):
                raise ContextError("旧上下文冻结身份不匹配")
            if not all(field in ctx for field in policy.POLICY_FIELDS):
                ctx.update(task_scope={"kind": "development", "paths": list(ctx["write_set"]),
                                       "acceptance": list(ctx["acceptance"])},
                           allowed_actions=sorted(policy.BASE_ACTIONS), verification_level="static",
                           authorization_source=[], execution_budget=dict(policy.DEFAULT_BUDGET))
                ctx["legacy_policy_migration"] = "旧模板无用户授权来源；仅保留实现与静态检查，重型项 NOT_REQUESTED"
            ctx["scope_revision"] = ctx["revision"]
            ctx["authorization_revision"] = 1
            ctx["revision"] += 1
            ctx["status"] = "active"
            ctx.pop("completed_at", None)
            _save(root, ctx)
            return ctx
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def load_context(root, path, *, migrate=True):
    """读取并校验唯一位置的上下文；不从 activeContext/计划推断身份。"""
    root = _root(root)
    source = Path(path)
    if not source.is_absolute():
        source = root / source
    _safe_inside(root, source)
    try:
        ctx = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ContextError(f"无法读取 execution-context：{exc}") from exc
    if migrate:
        ctx = _migrate_legacy_context(root, source, ctx)
    _validate(root, ctx)
    if source != _context_path(root, ctx["task_id"]):
        raise ContextError("execution-context 必须位于本任务运行目录的 context.json")
    return ctx


def validate_context(root, ctx):
    """Python API 同样验真，并拒绝被 revise 替换的旧内存身份。"""
    root = _root(root)
    _validate(root, ctx)
    current = load_context(root, _context_path(root, ctx["task_id"]))
    if context_identity(current) != context_identity(ctx):
        raise ContextError("内存 execution-context 已过期，请读取当前 revision")
    return current


def _atomic_json(root, path, data):
    _safe_inside(root, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".entry-", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def _save(root, ctx):
    ctx["identity_hash"] = identity_hash(ctx)
    ctx["checksum"] = _digest({k: v for k, v in ctx.items() if k != "checksum"})
    _validate(root, ctx)
    _atomic_json(root, _context_path(root, ctx["task_id"]), ctx)


@contextmanager
def _task_lock(root, path):
    ctx = load_context(root, path)
    lock_path = _context_path(root, ctx["task_id"]).with_name("context.lock")
    _safe_inside(root, lock_path)
    with lock_path.open("a+b") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield load_context(root, path)
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, timeout=30)


def git_worktree_inventory(root, max_files=None):
    """统一发现主仓/递归子模块，保留既有入口快照返回形状。"""
    from project_inventory import git_worktree_inventory as inventory, InventoryError
    try:
        return inventory(_root(root), max_files=max_files)
    except InventoryError as exc:
        if getattr(exc, "status", None) == "BUDGET_EXCEEDED":
            raise policy.PolicyError("BUDGET_EXCEEDED", str(exc)) from exc
        raise ContextError(str(exc)) from exc


def snapshot_worktree(root, max_files=None):
    """当前 Git 工作树的逐文件指纹，供入口及轻量范围共用（递归子模块）。"""
    root = _root(root)
    inventory = git_worktree_inventory(root, max_files=max_files)
    return {"files": {rel: initial_file_hash(root / rel) for rel in inventory["files"]},
            "gitlinks": inventory["gitlinks"], "dirty": inventory["preexisting_dirty"]}


def _initial_snapshot(root, since, max_files=None, write_set=()):
    try:
        probe = _git(root, "rev-parse", "--show-toplevel")
    except FileNotFoundError:
        probe = None
    git = probe is not None and probe.returncode == 0
    if not git and os.path.lexists(root / ".git"):
        raise ContextError("存在 .git 但不能读取；拒绝当作无 Git")
    if git and Path(os.fsdecode(probe.stdout).strip()).resolve() != root:
        raise ContextError("root 必须是 Git 工作树根目录")
    names, dirty = set(), set()
    start = None
    if git:
        head = _git(root, "rev-parse", "--verify", "HEAD^{commit}")
        if head.returncode == 0:
            start = head.stdout.decode().strip()
        if since is not None:
            if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", since):
                raise ContextError("--since 必须是完整 commit SHA，不接受 HEAD 或短引用")
            checked = _git(root, "rev-parse", "--verify", since + "^{commit}")
            if checked.returncode or checked.stdout.decode().strip() != since:
                raise ContextError("--since 不是当前仓库可读取的 commit")
            start = since
        inventory = git_worktree_inventory(root)  # 元数据枚举不等同于内容扫描。
        files, lazy = {}, {}
        dirty = set(inventory["preexisting_dirty"])
        repositories = sorted(inventory["repositories"], key=len, reverse=True)
        frozen_head = head.stdout.decode().strip() if head.returncode == 0 else None
        materialized = 0
        for relative in inventory["files"]:
            path = root / relative
            selected = any(relative == value or relative.startswith(value.rstrip("/") + "/") for value in write_set)
            if selected or relative in dirty or path.is_symlink() or not path.exists() or frozen_head is None:
                materialized += 1
                if max_files is not None and materialized > max_files:
                    raise policy.PolicyError("BUDGET_EXCEEDED", "任务写集/既有脏文件超过内容扫描预算")
                files[relative] = initial_file_hash(path)
                continue
            repo = next((name for name in repositories if name != "." and relative.startswith(name + "/")), ".")
            revision = inventory["gitlinks"][repo]["head"] if repo != "." else frozen_head
            local = relative[len(repo) + 1:] if repo != "." else relative
            lazy[relative] = {"repo": repo, "revision": revision, "path": local,
                              "mode": stat.S_IMODE(path.stat().st_mode)}
            files[relative] = None
        return start, "supported" if start else "unsupported", files, sorted(dirty), inventory["gitlinks"], lazy
    else:
        if since is not None:
            raise ContextError("无 Git 仓库不能声明 --since")
        def onerror(exc):
            raise exc
        for parent, dirs, files in os.walk(root, followlinks=False, onerror=onerror):
            base = Path(parent)
            dirs[:] = [d for d in dirs if d != ".git" and base / d != Path(runtime_dir(root))]
            for name in [*files, *(d for d in dirs if (base / d).is_symlink())]:
                names.add((base / name).relative_to(root).as_posix())
                if max_files is not None and len(names) > max_files:
                    raise policy.PolicyError("BUDGET_EXCEEDED", "初始文件清单超过扫描预算")
        dirty.update(names)
    runtime = Path(runtime_dir(root))
    snapshot = {}
    for name in sorted(names):
        path = root / name
        if path == runtime or runtime in path.parents or ".git" in PurePosixPath(name).parts:
            continue
        snapshot[name] = initial_file_hash(path)
    return start, "unsupported", snapshot, sorted(dirty & snapshot.keys()), {}, {}


def _result(root, ctx):
    return {"execution_context": str(_context_path(root, ctx["task_id"])),
            "mode": ctx["mode"], "route": ctx["mode"], "task_id": ctx["task_id"],
            "identity_hash": identity_hash(ctx), "revision": ctx["revision"],
            "since": ctx["since"], "identity": evidence_identity(ctx),
            "authorization_identity": context_identity(ctx),
            **{field: ctx[field] for field in policy.POLICY_FIELDS},
            "snapshot_cost": {"metadata_files": len(ctx["initial_files"]),
                              "hashed_files": len(ctx["initial_files"]) - len(ctx.get("initial_git_files", {}))}}


def _inherit(ctx, entry, version=None, sprint=None, since=None, write_set=None, acceptance=None):
    if ctx["mode"] == "light" and (entry in FORMAL_ENTRIES or sprint is not None):
        raise ContextError("继承 light 与正式入口/Sprint 冲突；不能自动升级或另分配身份")
    for key, requested in (("version", version), ("sprint", sprint), ("since", since)):
        if requested is not None and requested != ctx.get(key):
            raise ContextError(f"续跑不得改写冻结 {key}")
    root = Path(ctx["root"])
    if write_set is not None and _write_set(root, write_set) != ctx["write_set"]:
        raise ContextError("续跑扩展 write_set 必须显式 revise")
    if acceptance is not None and _acceptance(acceptance) != ctx["acceptance"]:
        raise ContextError("续跑不得替换验收目标")


def resolve_context(root, entry, version=None, sprint=None, execution_context=None,
                    since=None, write_set=None, acceptance=None, *, additional_grants=None,
                    authorization_source=None, execution_budget=None, task_scope=None, _task_id=None):
    root, entry = _root(root), _entry(entry)
    if execution_context:
        if additional_grants or authorization_source or execution_budget is not None or task_scope is not None:
            raise ContextError("子入口只能继承；后续用户授权必须显式 revise，不能借切换入口升权")
        ctx = load_context(root, execution_context)
        _inherit(ctx, entry, version, sprint, since, write_set, acceptance)
    else:
        if not version or not re.fullmatch(r"V[0-9][A-Za-z0-9._-]*", version):
            raise ContextError("新任务必须提供 --version V...")
        if sprint is not None and not re.fullmatch(r"[0-9]{3,}", sprint):
            raise ContextError("--sprint 必须是 NNN 格式")
        task_id = str(uuid.UUID(_task_id)) if _task_id is not None else str(uuid.uuid4())
        if _context_path(root, task_id).exists():
            raise ContextError("任务位置已存在；只能继承或显式 revise，不能覆盖重置预算")
        if authorization_source:
            _check_source_version(authorization_source, version)
        paths, criteria = _write_set(root, write_set), _acceptance(acceptance or [])
        _context_base(root)  # 在任何目录创建之前检查运行目录没有链接逃逸。
        execution = policy.policy_fields(root, paths, criteria, additional_grants=additional_grants,
            authorization_source=authorization_source, execution_budget=execution_budget, task_scope=task_scope)
        if authorization_source and authorization_source.get("kind") in ("explicit-command", "project-policy") and authorization_source.get("command"):
            if _entry(authorization_source["command"].lstrip("/")) != entry:
                raise ContextError("显式命令来源与入口不一致")
        start, support, files, dirty, gitlinks, lazy = _initial_snapshot(
            root, since, max_files=execution["execution_budget"]["scanned_files"], write_set=paths)
        explicit_aiauto = bool(authorization_source and authorization_source.get("kind") in ("explicit-command", "project-policy")
                               and authorization_source.get("command", "").lstrip("/") == "sprint-aiauto-test")
        ctx = {"schema": SCHEMA, "root": str(root), "entry": entry,
               "mode": "formal" if entry in FORMAL_ENTRIES or sprint is not None or explicit_aiauto else "light",
               "task_id": task_id, "version": version, "since": start, "git_status": support,
               "revision": 1, "scope_revision": 1, "authorization_revision": 1,
               "write_set": paths, "acceptance": criteria,
               "initial_files": files, "preexisting_dirty": dirty, "initial_gitlinks": gitlinks,
               "initial_git_files": lazy,
               "created_at": time.time(), "status": "active", **execution}
        if ctx["mode"] == "formal":
            ctx["sprint"] = sprint
        ensure_runtime_dir(root)
        _save(root, ctx)
        policy.reserve_budget(root, ctx, "scanned_files", len(files) - len(lazy))
    return dict(_result(root, ctx), context=ctx)


def _check_source_version(source, version):
    """公开 --target 两种写法都是权限范围，不能把固定目标复制成另一版本授权。"""
    if source.get("command", "").lstrip("/") not in ("sprint-autopilot", "sprint-aiauto-test"):
        return
    options = source.get("options", [])
    if not isinstance(options, list) or any(not isinstance(option, str) for option in options):
        raise policy.PolicyError("UNAUTHORIZED", "命令 options 必须是原始选项数组")
    targets = []
    for index, option in enumerate(options):
        if option == "--target":
            if index + 1 >= len(options) or options[index + 1].startswith("--"):
                raise policy.PolicyError("UNAUTHORIZED", "来源 --target 缺少真实目标版本")
            targets.append(options[index + 1])
        elif option.startswith("--target="):
            targets.append(option.split("=", 1)[1])
    if targets and (len(set(targets)) != 1 or targets[0] != version):
        raise policy.PolicyError("UNAUTHORIZED", "来源明确限定的 --target 与目标版本不一致")


def _pipeline_source(ctx, entry, persistent=False):
    if ctx["mode"] != "formal" or ctx["entry"] != entry or "parent_task_id" in ctx:
        raise policy.PolicyError("UNAUTHORIZED", "持续执行必须来自对应命令的真实 formal 根")
    for source in reversed(ctx["authorization_source"]):
        if source.get("command", "").lstrip("/") != entry:
            continue
        if source["kind"] not in ("explicit-command", "project-policy"):
            continue
        policy.validate_source(source)
        _check_source_version(source, ctx["version"])
        if persistent and source["kind"] == "explicit-command" and source.get("persistent") is not True:
            continue
        return json.loads(json.dumps(source))
    raise policy.PolicyError("UNAUTHORIZED", "没有可持续执行的真实命令/明确已选策略来源；旧模板不能授权")


def _resolve_pipeline_root(root, version, entry, execution_context=None, authorization_source=None, existing_only=False):
    """沿用既有版本指针及确定性 context 位置；只在真实新版本边界建立新根。"""
    from aidp_config import read_execution_policy
    root = _root(root)
    if not re.fullmatch(r"V[0-9][A-Za-z0-9._-]*", str(version)):
        raise ContextError("持续执行根必须指定真实版本 V...")
    if existing_only and authorization_source is not None:
        raise policy.PolicyError("UNAUTHORIZED", "existing-only 不接受新来源或授权修订")
    source = policy.validate_source(authorization_source) if authorization_source is not None else None
    if source is not None and (source["kind"] not in ("explicit-command", "project-policy") or
                               source.get("command", "").lstrip("/") != entry):
        raise policy.PolicyError("UNAUTHORIZED", "当前来源没有请求对应持续命令")
    if source:
        _check_source_version(source, version)
    incoming = load_context(root, execution_context, migrate=not existing_only) if execution_context else None
    if incoming and (incoming["mode"] != "formal" or incoming["entry"] != entry or "parent_task_id" in incoming):
        raise policy.PolicyError("UNAUTHORIZED", "传入的外层上下文不是对应命令根，不能丢弃它改借宽缓存授权")
    root_id = str(uuid.uuid5(uuid.NAMESPACE_URL, str(root) + ":" + entry + ":" + version))
    canonical = _context_path(root, root_id)
    base = _context_base(root)
    if not existing_only:
        ensure_runtime_dir(root)
        base.mkdir(parents=True, exist_ok=True)
    lock_path = _safe_inside(root, base / "pipeline-roots.lock")
    with (nullcontext(None) if existing_only else lock_path.open("a+b")) as stream:
        if stream is not None:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            candidates = []
            if incoming and incoming["version"] == version:
                candidates.append((_context_path(root, incoming["task_id"]), True))
            baseline = root / "memory/.sprint-autopilot-baseline.json"
            record = {}
            if baseline.exists():
                _safe_inside(root, baseline)
                data = json.loads(baseline.read_text(encoding="utf-8"))
                record = data.get("versions", {}).get(version, {})
                if not isinstance(record, dict):
                    raise ContextError("版本根索引必须是映射")
                key = "autopilot_root_context" if entry == "sprint-autopilot" else "aiauto_execution_context"
                if record.get(key):
                    candidates.append((record[key], True))
            if canonical.exists():
                candidates.append((canonical, True))
            if entry == "sprint-autopilot" and record.get("execution_context"):
                candidates.append((record["execution_context"], False))
            seen = set()
            for candidate, strict in candidates:
                path = str(candidate)
                if path in seen:
                    continue
                seen.add(path)
                current = load_context(root, path, migrate=not existing_only)
                if (current["version"] != version or current["entry"] != entry or
                        current["mode"] != "formal" or "parent_task_id" in current):
                    if strict:
                        raise policy.PolicyError("UNAUTHORIZED", "指定根指针范围不符，不能退回旧宽根")
                    continue  # 兼容旧 planning 指针，但绝不把它当作授权。
                if source:
                    grants = []
                    configured = read_execution_policy(root)
                    if source["kind"] == "project-policy" and configured:
                        grants = configured.get("allowed_actions", [])
                    revised = revise_context(root, path, additional_grants=grants, authorization_source=source)
                    current = revised["context"]
                _pipeline_source(current, entry, persistent=False)
                return dict(_result(root, current), context=current, created=False)
            if existing_only:
                raise policy.PolicyError("UNAUTHORIZED", "没有已有可信版本根；只读选择不会新建任务或预算")
            configured = read_execution_policy(root)
            chosen = configured.get("authorization_source") if configured else None
            if chosen and chosen.get("command", "").lstrip("/") != entry:
                chosen = None
            if source is None and chosen:
                source = policy.validate_source(chosen)
            if source is None and incoming:
                source = _pipeline_source(incoming, entry, persistent=True)
                if source["kind"] == "project-policy":
                    raise policy.PolicyError("UNAUTHORIZED", "新版本需要当前仍有效的已选项目策略，不能从历史配置快照补 grant")
                def order(value):
                    parsed = re.match(r"V([0-9]+)(?:\.([0-9]+))?(?:\.([0-9]+))?", value)
                    return tuple(int(part or 0) for part in parsed.groups())
                if order(version) <= order(incoming["version"]):
                    raise ContextError("历史版本没有可信根指针；只能沿原根 fork-version 收口，不能新建根清零预算")
            if source is None:
                raise policy.PolicyError("UNAUTHORIZED", "新版本根缺少当前真实命令或明确选择的持续执行来源")
            _check_source_version(source, version)
            extra = configured.get("allowed_actions", []) if chosen and source["kind"] == "project-policy" else []
            budget = configured.get("execution_budget") if chosen and source["kind"] == "project-policy" else None
            if source["kind"] == "project-policy" and budget is None:
                budget = policy.COMMAND_BUDGETS.get(entry)
            result = resolve_context(root, entry, version=version, additional_grants=extra,
                                     authorization_source=source, execution_budget=budget, _task_id=root_id)
            return dict(result, created=True)
        finally:
            if stream is not None:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def resolve_autopilot_root(root, version, execution_context=None, authorization_source=None, *, existing_only=False):
    return _resolve_pipeline_root(root, version, "sprint-autopilot", execution_context, authorization_source, existing_only)


def resolve_test_root(root, version, execution_context=None, authorization_source=None, *, existing_only=False):
    return _resolve_pipeline_root(root, version, "sprint-aiauto-test", execution_context, authorization_source, existing_only)


def route_context(root, execution_context, phase="route", entry=None, action=None):
    root = _root(root)
    ctx = load_context(root, execution_context)
    _inherit(ctx, _entry(entry or ctx["entry"]))
    if phase not in LIGHT_ACTIONS:
        raise ContextError(f"未知阶段：{phase}")
    candidates = LIGHT_ACTIONS[phase] if ctx["mode"] == "light" else FORMAL_ACTIONS[phase]
    actions = []
    for candidate in candidates:
        candidate = "related-test" if candidate == "sprint-test" else candidate
        if candidate == "formal-gates":
            continue  # formal 保留编号/归档身份，不以泛称门禁暗授重型检查。
        if candidate not in policy.ACTIONS or candidate in ctx["allowed_actions"]:
            actions.append(candidate)
    if phase in ("dev", "test", "repair", "close"):
        actions.extend(a for a in ctx["allowed_actions"] if a not in actions)
    if ctx["mode"] == "formal" and ctx["sprint"] is None and phase == "prepare":
        actions.append("allocate-sprint")
    not_requested = sorted(policy.OPTIONAL_ACTIONS - set(ctx["allowed_actions"]))
    forbidden = list(LIGHT_FORBIDDEN if ctx["mode"] == "light" else ("cascade",))
    cascade_requested = "document" in ctx["allowed_actions"] and any(
        source["kind"] == "explicit-command" and "--cascade-now" in source.get("options", [])
        for source in ctx["authorization_source"])
    if cascade_requested and phase in ("dev", "repair", "close"):
        actions.append("cascade")
        forbidden.remove("cascade")
    if action and policy.canonical_action(action) not in actions:
        raise policy.PolicyError("UNAUTHORIZED", f"{ctx['mode']}/{phase} 不允许动作 {action}")
    return dict(_result(root, ctx), phase=phase, actions=actions,
                authorized_actions=list(ctx["allowed_actions"]), not_requested_actions=not_requested,
                execution_budget=ctx["execution_budget"], verification_level=ctx["verification_level"],
                forbidden_actions=forbidden, preserve_formal_gates=ctx["mode"] == "formal",
                completion_requires="authorized-task-evidence", optional_status="NOT_REQUESTED")


def revise_context(root, execution_context, write_set=None, *, additional_grants=None,
                   authorization_source=None, execution_budget=None):
    root = _root(root)
    with _task_lock(root, execution_context) as ctx:
        before = identity_hash(ctx)
        expanded = sorted(set(ctx["write_set"]) | set(_write_set(root, write_set)))
        if "parent_task_id" in ctx and (additional_grants or authorization_source or execution_budget is not None):
            raise ContextError("子任务不得修订父任务授权或扩大预算；必须由根任务接收新用户请求")
        if additional_grants or authorization_source or execution_budget is not None:
            source = policy.validate_source(authorization_source)
            _check_source_version(source, ctx["version"])
            grants = policy._actions(additional_grants or [])
            if source["kind"] == "explicit-command":
                public = policy.command_grants(source)
                if grants - public:
                    raise policy.PolicyError("UNAUTHORIZED", "额外 grant 超出显式命令公开职责")
                grants.update(public)
            default_budget = dict(ctx["execution_budget"])
            if source["kind"] == "explicit-command":
                preset = policy.COMMAND_BUDGETS.get(source["command"].lstrip("/"), {})
                default_budget = {key: max(value, preset.get(key, value)) for key, value in default_budget.items()}
            budget = policy.normalize_budget(execution_budget, default_budget)
            removed = set()
            if source["kind"] in ("explicit-command", "project-policy"):
                for option in source.get("options", []):
                    removed.update(policy.COMMAND_OPTION_REMOVALS.get(source.get("command", "").lstrip("/"), {}).get(option, ()))
            next_actions = (set(ctx["allowed_actions"]) | grants) - removed
            record = dict(source, actions=sorted(grants))
            if execution_budget is not None:
                record["execution_budget"] = budget
            prior = next((s for s in ctx["authorization_source"] if s["request_id"] == source["request_id"]), None)
            if prior is not None and prior != record:
                raise ContextError("同一 request_id 的授权重放内容不一致")
            if prior is None and (next_actions != set(ctx["allowed_actions"]) or budget != ctx["execution_budget"]
                                  or source["kind"] in ("explicit-command", "project-policy")):
                ctx["authorization_source"].append(record)
                ctx["allowed_actions"] = sorted(next_actions)
                ctx["execution_budget"] = budget
                ctx["verification_level"] = policy.verification_level(ctx["allowed_actions"])
        if expanded != ctx["write_set"]:
            ctx["scope_revision"] += 1
        elif identity_hash(ctx) != before:
            ctx["authorization_revision"] += 1
        ctx["write_set"] = expanded
        ctx["task_scope"]["paths"] = expanded
        if identity_hash(ctx) != before:
            ctx["revision"] += 1
            ctx["status"] = "active"
            ctx.pop("completed_at", None)
            _save(root, ctx)
        return dict(_result(root, ctx), context=ctx)


def bind_sprint(root, execution_context, sprint, since=None):
    """绑定原正式流程已分配的号；不取号，同号重试不重新读取 HEAD。"""
    root = _root(root)
    if not re.fullmatch(r"[0-9]{3,}", sprint):
        raise ContextError("--sprint 必须是 NNN 格式")
    with _task_lock(root, execution_context) as ctx:
        if ctx["mode"] != "formal":
            raise ContextError("light 不能绑定 Sprint 或升级正式身份")
        if ctx["sprint"] is not None:
            if ctx["sprint"] != sprint or (since is not None and since != ctx["since"]):
                raise ContextError("已绑定的 Sprint/起点不能重新分配")
            return dict(_result(root, ctx), context=ctx)
        if since is not None:
            start, support, files, dirty, gitlinks, lazy = _initial_snapshot(root, since)
            ctx.update(since=start, git_status=support, initial_files=files, preexisting_dirty=dirty,
                       initial_gitlinks=gitlinks, initial_git_files=lazy)
        ctx["sprint"] = sprint
        ctx["scope_revision"] += 1
        ctx["revision"] += 1
        _save(root, ctx)
        return dict(_result(root, ctx), context=ctx)


def _refresh_child(root, parent, child, action_limit, inherit_scope=False):
    """在父锁及子锁内显式刷新继承；预算余额和起点始终留在原任务。"""
    before = identity_hash(child)
    old_scope = (list(child["write_set"]), list(child["acceptance"]))
    actions = set(parent["allowed_actions"])
    if action_limit is not None:
        actions.intersection_update(action_limit)
    child.update(parent_identity_hash=identity_hash(parent), inherit_action_limit=action_limit,
                 allowed_actions=sorted(actions), verification_level=policy.verification_level(actions),
                 authorization_source=json.loads(json.dumps(parent["authorization_source"])),
                 execution_budget=dict(parent["execution_budget"]))
    if inherit_scope:
        child["write_set"] = sorted(set(child["write_set"]) | set(parent["write_set"]))
        child["acceptance"] = list(dict.fromkeys([*child["acceptance"], *parent["acceptance"]]))
        child["task_scope"].update(paths=child["write_set"], acceptance=child["acceptance"])
    if identity_hash(child) != before:
        if old_scope != (child["write_set"], child["acceptance"]):
            child["scope_revision"] += 1
        child["authorization_revision"] += 1
        child["revision"] += 1
        child["status"] = "active"
        child.pop("completed_at", None)
        _save(root, child)
    return child


def fork_context(root, execution_context, sprint, since=None, *, allowed_actions=None):
    """正式批量的单 Sprint 子任务；同父同号只创建一次，起点取开工时 HEAD。"""
    root = _root(root)
    if not re.fullmatch(r"[0-9]{3,}", sprint):
        raise ContextError("--sprint 必须是已有分配的 NNN")
    with _task_lock(root, execution_context) as parent:
        if parent["mode"] != "formal":
            raise ContextError("light 不能 fork 正式 Sprint")
        narrowed = set(parent["allowed_actions"]) if allowed_actions is None else policy._actions(allowed_actions)
        if not narrowed <= set(parent["allowed_actions"]):
            raise policy.PolicyError("UNAUTHORIZED", "子任务 allowed_actions 必须是父任务子集")
        # 父 UUID + Sprint 确定子位置，不遍历/依赖其他任务；只锁本父任务派发。
        child_id = str(uuid.uuid5(uuid.UUID(parent["task_id"]), "sprint:" + sprint))
        candidate = _context_path(root, child_id)
        if candidate.exists():
            with _task_lock(root, candidate) as child:
                if child.get("parent_task_id") != parent["task_id"] or child.get("sprint") != sprint:
                    raise ContextError("正式子任务冻结的父身份或 Sprint 不一致")
                if since is not None and since != child["since"]:
                    raise ContextError("本 Sprint 子任务已存在，续跑不得更改起点")
                # 老子任务未记录限权选择时保守保留既有权限；可显式传父权限内的新名单。
                limit = (sorted(narrowed) if allowed_actions is not None else
                         child.get("inherit_action_limit", list(child["allowed_actions"])))
                child = _refresh_child(root, parent, child, limit, inherit_scope=True)
                return dict(_result(root, child), context=child)
        start, support, files, dirty, gitlinks, lazy = _initial_snapshot(root, since)
        child = {"schema": SCHEMA, "root": str(root), "mode": "formal", "entry": "sprint-full",
                 "task_id": child_id, "parent_task_id": parent["task_id"],
                 "parent_identity_hash": identity_hash(parent), "version": parent["version"],
                 "sprint": sprint, "since": start, "git_status": support, "revision": 1,
                 "scope_revision": 1, "authorization_revision": parent["authorization_revision"],
                 "write_set": list(parent["write_set"]), "acceptance": list(parent["acceptance"]),
                 "initial_files": files, "preexisting_dirty": dirty, "initial_gitlinks": gitlinks,
               "initial_git_files": lazy,
                 "created_at": time.time(), "status": "active",
                 **{key: json.loads(json.dumps(parent[key])) for key in policy.POLICY_FIELDS}}
        child["inherit_action_limit"] = sorted(narrowed) if allowed_actions is not None else None
        child["allowed_actions"] = sorted(narrowed)
        child["verification_level"] = policy.verification_level(narrowed)
        _save(root, child)
        return dict(_result(root, child), context=child)


def fork_version(root, execution_context, version):
    """显式 autopilot 的上版文档/准发布子任务，继承根预算及来源，不扩大业务权限。"""
    root = _root(root)
    if not re.fullmatch(r"V[0-9][A-Za-z0-9._-]*", str(version)):
        raise ContextError("前版版本号必须以 V 和数字开头")
    def order(value):
        numbers = re.match(r"V([0-9]+)(?:\.([0-9]+))?(?:\.([0-9]+))?", value)
        return tuple(int(part or 0) for part in numbers.groups())
    with _task_lock(root, execution_context) as parent:
        _pipeline_source(parent, "sprint-autopilot")
        explicit = True
        if (parent["mode"] != "formal" or parent["entry"] != "sprint-autopilot" or
                "parent_task_id" in parent or not explicit or "document" not in parent["allowed_actions"]):
            raise policy.PolicyError("UNAUTHORIZED", "仅真实显式 autopilot 根任务可继承上版收口")
        if order(version) > order(parent["version"]):
            raise ContextError("fork-version 不能继承晚于当前目标的版本收口")
        child_id = str(uuid.uuid5(uuid.UUID(parent["task_id"]), "pre-release:" + version))
        candidate = _context_path(root, child_id)
        if candidate.exists():
            with _task_lock(root, candidate) as child:
                if child.get("parent_task_id") != parent["task_id"] or child["version"] != version:
                    raise ContextError("前版子任务归属不一致")
                child = _refresh_child(root, parent, child, ["commit", "docs-audit", "document", "push", "static"])
                return dict(_result(root, child), context=child)
        child = json.loads(json.dumps(parent))
        actions = sorted(set(parent["allowed_actions"]) & {"document", "static", "docs-audit", "commit", "push"})
        child.update(task_id=child_id, parent_task_id=parent["task_id"], parent_identity_hash=identity_hash(parent),
                     entry="version", version=version, sprint=None, revision=1, scope_revision=1,
                     authorization_revision=parent["authorization_revision"], write_set=[], acceptance=[],
                     task_scope={"kind": "release", "paths": [], "acceptance": []},
                     allowed_actions=actions, verification_level=policy.verification_level(actions),
                     inherit_action_limit=["commit", "docs-audit", "document", "push", "static"],
                     created_at=time.time(), status="active")
        child.pop("completed_at", None)
        _save(root, child)
        return dict(_result(root, child), context=child)


def fork_test_build(root, execution_context, version, build_id):
    """真实部署 build 的受限测试身份；选择/部署证明仍由原 build 消费者核验。"""
    root = _root(root)
    if not re.fullmatch(r"V[0-9][A-Za-z0-9._-]*", str(version)):
        raise ContextError("测试版本号必须以 V 和数字开头")
    if not isinstance(build_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", build_id):
        raise ContextError("build-id 必须是已选真实 build 的非空标识")
    def order(value):
        numbers = re.match(r"V([0-9]+)(?:\.([0-9]+))?(?:\.([0-9]+))?", value)
        return tuple(int(part or 0) for part in numbers.groups())
    with _task_lock(root, execution_context) as parent:
        if parent["mode"] != "formal" or "parent_task_id" in parent:
            raise policy.PolicyError("UNAUTHORIZED", "测试 build 必须继承已有真实 formal 根任务")
        if not {"live-tests", "full-regression"} <= set(parent["allowed_actions"]):
            raise policy.PolicyError("UNAUTHORIZED", "父任务未授权双路测试；baseline 不能生成授权")
        if order(version) > order(parent["version"]):
            raise ContextError("不能借测试子任务扩展到父目标之后的版本")
        limit = ["full-regression", "live-tests", "static"]
        child_id = str(uuid.uuid5(uuid.UUID(parent["task_id"]), "test-build:" + version + ":" + build_id))
        candidate = _context_path(root, child_id)
        if candidate.exists():
            with _task_lock(root, candidate) as child:
                if (child.get("parent_task_id") != parent["task_id"] or child["version"] != version
                        or child.get("build_id") != build_id):
                    raise ContextError("测试 build 子任务归属不一致")
                child = _refresh_child(root, parent, child, limit)
                return dict(_result(root, child), context=child)
        child = json.loads(json.dumps(parent))
        actions = sorted(set(parent["allowed_actions"]) & set(limit))
        child.update(task_id=child_id, parent_task_id=parent["task_id"], parent_identity_hash=identity_hash(parent),
                     entry="sprint-aiauto-test", version=version, build_id=build_id, sprint=None,
                     revision=1, scope_revision=1, authorization_revision=parent["authorization_revision"],
                     write_set=[], acceptance=[], task_scope={"kind": "test", "paths": [], "acceptance": []},
                     allowed_actions=actions, verification_level=policy.verification_level(actions),
                     inherit_action_limit=limit, created_at=time.time(), status="active")
        child.pop("completed_at", None)
        _save(root, child)
        return dict(_result(root, child), context=child)


def completion_obligations(root, execution_context):
    """只读取本任务版本四个固定族路径；不把历史全局欠账带入新任务。"""
    from commit_gate import cascade_ledger_paths, _parse_cascade_entries, _has_archived_mark, debt_items
    root = _root(root)
    ctx = load_context(root, execution_context)
    current = {"files": [], "families": {}, "total": 0, "stale": 0,
               "cascaded_not_cleaned": 0, "unparsed": [], "archived_not_deleted": [],
               "destructive_unregistered": []}
    diagnostics = []
    for family, filename in cascade_ledger_paths(str(root), ctx["version"]):
        path = Path(filename)
        rel = path.relative_to(root).as_posix()
        if not path.exists():
            continue
        _safe_inside(root, path)
        digest = initial_file_hash(path)
        if initial_hash(root, ctx, rel) == digest:
            diagnostics.append({"file": rel, "status": "PREEXISTING_UNCHANGED"})
            continue
        if rel in ctx["preexisting_dirty"]:
            diagnostics.append({"file": rel, "status": "UNVERIFIED",
                                "reason": "任务前已脏，缺少原文不能把历史问题归给本任务"})
            continue
        text = path.read_text(encoding="utf-8")
        if len(text) > 400000:
            diagnostics.append({"file": rel, "status": "UNVERIFIED", "reason": "族册超过轻量读取上限"})
            continue
        attributed = any(rel == value or rel.startswith(value.rstrip("/") + "/") for value in ctx["write_set"])
        if not attributed and ctx["task_id"] not in text:
            diagnostics.append({"file": rel, "status": "UNATTRIBUTED_CHANGE",
                                "reason": "同版本变动不自动归属本任务；不扩大审计或补历史清理"})
            continue
        old_text = ""
        if rel in ctx["initial_files"] and ctx["since"]:
            before = _git(root, "show", ctx["since"] + ":" + rel)
            if before.returncode:
                diagnostics.append({"file": rel, "status": "UNVERIFIED", "reason": "任务起点原文不可读取"})
                continue
            old_text = before.stdout.decode("utf-8", errors="replace")
        today = time.strftime("%m-%d")
        count, stale, done, unregistered, unparsed = _parse_cascade_entries(text, today)
        _, _, old_done, old_unregistered, old_unparsed = _parse_cascade_entries(old_text, today)
        current["files"].append(rel)
        current["families"][family] = {"file": rel, "total": count, "stale": stale}
        current["total"] += count
        current["stale"] += stale
        current["cascaded_not_cleaned"] += max(0, done - old_done)
        if unparsed and not old_unparsed:
            current["unparsed"].append(rel)
        if _has_archived_mark(text) and not _has_archived_mark(old_text):
            current["archived_not_deleted"].append(rel)
        current["destructive_unregistered"].extend({"file": rel, "id": item}
            for item in unregistered if item not in old_unregistered)
    blocking = debt_items({"pending_cascade": current})
    return {"obligations": blocking, "blocking_obligations": blocking,
            "external_obligations": [], "diagnostics": diagnostics,
            "version_obligations": {"version": ctx["version"], "cascade": current}}


def _input_files(root, ctx, inputs):
    """将目录展开为真实文件，并以起点成员的删除墓碑绑定目录增删。"""
    declared = _write_set(root, inputs)
    if not declared:
        raise ContextError("证据 inputs 必须非空且覆盖任务 write_set")
    runtime = Path(runtime_dir(root))
    cache = {}

    def members(relative):
        if relative in cache:
            return cache[relative]
        target = _safe_inside(root, root / relative)
        previous = {name for name in ctx["initial_files"] if name.startswith(relative + "/")}
        directory = target.is_dir() or bool(previous)
        found = set(previous)
        if target.is_dir():
            def onerror(exc):
                raise exc
            for parent, dirs, files in os.walk(target, followlinks=False, onerror=onerror):
                base = Path(parent)
                kept = []
                for name in dirs:
                    path = base / name
                    if name == ".git" or path == runtime:
                        continue
                    _safe_inside(root, path)  # 目录链接不得藏掉真实成员或穿越 root。
                    kept.append(name)
                dirs[:] = kept
                for name in files:
                    path = base / name
                    if name == ".git" or path == runtime or runtime in path.parents:
                        continue
                    found.add(_relative_path(root, path.relative_to(root).as_posix()))
        elif target.exists() or not directory:
            found.add(relative)
        if directory and not found:
            raise ContextError(f"目录写集没有可核验的真实文件：{relative}")
        cache[relative] = found
        return found

    paths = set().union(*(members(relative) for relative in declared))
    required = set().union(*(members(relative) for relative in ctx["write_set"])) if ctx["write_set"] else set()
    if not paths or not required <= paths:
        raise ContextError("证据 inputs 必须覆盖任务 write_set 的全部真实文件及删除成员")
    for relative in paths:
        _safe_inside(root, root / relative)
        if not (root / relative).exists() and relative not in ctx["initial_files"]:
            raise ContextError(f"输入不存在且没有冻结删除基线：{relative}")
    policy.reserve_budget(root, ctx, "scanned_files", len(paths))
    return {relative: initial_file_hash(root / relative) for relative in sorted(paths)}


def _validate_static_command(root, argv):
    """有限静态执行器，拒绝已知重流程和未知包装脚本；不解释 shell 语言。"""
    import ast
    import shutil
    name = Path(argv[0]).name.lower()
    args = list(argv[1:])
    if any(token in ("--fix", "--write", "--watch", "-w") for token in args):
        raise policy.PolicyError("UNAUTHORIZED", "static 只接受只读检查选项")
    if name.startswith(("python", "pypy")):
        args = [arg for arg in args if arg not in ("-B", "-I", "-S")]
        if args[:1] == ["-m"] and len(args) >= 2:
            if args[1] in ("py_compile", "compileall"):
                return
            if args[1] in ("ruff", "mypy", "flake8", "pylint"):
                return _validate_static_command(root, args[1:])
            raise policy.PolicyError("UNAUTHORIZED", "Python 测试/未知模块不能作为 static 执行")
        if args[:1] == ["-c"] and len(args) == 2:
            tree = ast.parse(args[1])
            allowed_modules = {"ast", "pathlib", "tokenize"}
            allowed_calls = {"compile", "open", "print", "len", "str", "Path"}
            allowed_methods = {"parse", "read", "read_text", "read_bytes", "open", "is_file", "exists"}
            for node in ast.walk(tree):
                if isinstance(node, ast.Import) and any(alias.name not in allowed_modules for alias in node.names):
                    raise policy.PolicyError("UNAUTHORIZED", "内联 static 只支持语法读取模块")
                if isinstance(node, ast.ImportFrom) and node.module not in allowed_modules:
                    raise policy.PolicyError("UNAUTHORIZED", "内联 static 导入了未知执行模块")
                if isinstance(node, ast.Call):
                    target = node.func
                    if ((isinstance(target, ast.Name) and target.id not in allowed_calls) or
                        (isinstance(target, ast.Attribute) and target.attr not in allowed_methods) or
                            not isinstance(target, (ast.Name, ast.Attribute))):
                        raise policy.PolicyError("UNAUTHORIZED", "内联 static 含非语法检查调用")
            if not any(isinstance(node, ast.Call) and
                       ((isinstance(node.func, ast.Name) and node.func.id == "compile") or
                        (isinstance(node.func, ast.Attribute) and node.func.attr == "parse"))
                       for node in ast.walk(tree)):
                raise policy.PolicyError("UNAUTHORIZED", "内联 static 必须包含实际语法检查")
            return
        raise policy.PolicyError("UNAUTHORIZED", "未知 Python 包装脚本不能以 static 标签执行")
    if name == "git" and args[:1] == ["diff"] and "--check" in args:
        return
    if name in ("flake8", "pylint", "mypy", "pyright", "shellcheck", "yamllint", "eslint"):
        return
    if name == "ruff" and (args[:1] == ["check"] or (args[:1] == ["format"] and "--check" in args)):
        return
    if name == "tsc" and "--noEmit" in args:
        return
    if name in ("black", "isort") and any(arg in args for arg in ("--check", "--check-only")):
        return
    if name in ("pytest", "unittest", "mvn", "mvnw", "gradle", "gradlew", "npm", "pnpm", "yarn",
                "npx", "make", "docker", "kubectl", "helm", "sh", "bash", "node", "java", "go", "cargo"):
        raise policy.PolicyError("UNAUTHORIZED", "测试、构建、服务或部署命令不能标为 static")
    # 缺失工具只能留下 ENV_UNAVAILABLE，不能自动安装或找替代脚本。
    if shutil.which(argv[0]) is None and not (root / argv[0]).exists():
        return
    raise policy.PolicyError("UNAUTHORIZED", "未知静态包装命令未经显式检查来源确认，停止执行")


def _static_environment(root, argv):
    import shutil
    executable = shutil.which(argv[0])
    if executable is None and (root / argv[0]).is_file():
        executable = str(root / argv[0])
    target = Path(executable).resolve() if executable else None
    return {"path": os.environ.get("PATH", ""), "python": sys.version,
            "executable": str(target) if target else None,
            "executable_hash": initial_file_hash(target) if target and target.is_file() else None}


def run_static(root, execution_context, argv, inputs=(), timeout=30):
    """执行真实静态命令并生成绑定当前任务/代码的 JSON；缺工具只记未核验。"""
    root = _root(root)
    ctx = policy.require_action(load_context(root, execution_context), "static")
    if (not isinstance(argv, (list, tuple)) or not argv or
            any(not isinstance(arg, str) or not arg for arg in argv)):
        raise ContextError("static 必须提供实际命令 argv")
    _validate_static_command(root, argv)
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ContextError("static timeout 必须为正数")
    fingerprints = _input_files(root, ctx, inputs)
    binding = {"identity_hash": _digest(evidence_identity(ctx)), "action": "static", "argv": list(argv),
               "cwd": ".", "inputs": fingerprints, "environment": _static_environment(root, argv)}
    input_hash = _digest(binding)
    policy.reserve_budget(root, ctx, "processes", 1, input_hash, action="static")
    reservation = policy.reserve_budget(root, ctx, "elapsed_seconds", timeout, input_hash, action="static")
    started = time.monotonic()
    row = {"schema": 1, "kind": "command-evidence", "execution_context": evidence_identity(ctx),
           **binding, "input_hash": input_hash, "started_at": time.time()}
    try:
        proc = subprocess.run(list(argv), cwd=root, capture_output=True, text=True, errors="replace", timeout=timeout)
        status = "PASS" if proc.returncode == 0 else "FAIL"
        output = {"returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}
    except FileNotFoundError as exc:
        status, output = "ENV_UNAVAILABLE", {"returncode": None, "stdout": "", "stderr": str(exc)}
    except (OSError, subprocess.SubprocessError) as exc:
        status, output = "TOOL_ERROR", {"returncode": None, "stdout": "", "stderr": str(exc)}
    elapsed = time.monotonic() - started
    row.update(status=status, result=output, finished_at=time.time(), elapsed_seconds=elapsed)
    # 静态命令不能边改输入边把旧指纹的成功结果当成核验。
    if _input_files(root, ctx, inputs) != fingerprints:
        row.update(status="UNVERIFIED", error="静态命令执行期间输入变化")
    try:
        policy.record_outcome(root, ctx, "static", row["status"], input_hash,
                              root_cause=output["stderr"] if status != "PASS" else None, evidence=output)
        policy.settle_elapsed(root, ctx, reservation, elapsed)
    except (ValueError, OSError) as exc:
        row["policy_notice"] = {"status": getattr(exc, "status", "UNVERIFIED"), "error": str(exc)}
    row["checksum"] = _digest(row)
    path = _context_path(root, ctx["task_id"]).with_name("static-" + str(uuid.uuid4()) + ".json")
    _atomic_json(root, path, row)
    return {"status": row.get("policy_notice", {}).get("status", row["status"]),
            "process_status": row["status"], "evidence_file": str(path), "input_hash": input_hash,
            "execution_context": evidence_identity(ctx), "result": output, "elapsed_seconds": elapsed}


def _read_evidence(root, ctx, filename, action, allow_failure=False):
    path = Path(filename)
    if not path.is_absolute():
        path = root / path
    _safe_inside(root, path)
    report = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(report, dict) or report.get("execution_context") != evidence_identity(ctx):
        raise ContextError(f"{action} 证据不属于当前任务 revision")
    if report.get("action", action) != action:
        raise ContextError("证据动作与授权检查不一致")
    inputs = report.get("inputs")
    if not isinstance(inputs, dict) or _input_files(root, ctx, list(inputs)) != inputs:
        raise ContextError(f"{action} 证据缺少真实 inputs 或代码已经变化")
    if action == "static":
        if (report.get("kind") != "command-evidence" or not report.get("argv") or
                report.get("checksum") != _digest({k: v for k, v in report.items() if k != "checksum"})):
            raise ContextError("static 需要实际命令结果，不能仅声明 PASS")
        if report.get("policy_notice"):
            raise policy.PolicyError(report["policy_notice"]["status"], "静态进程结果已保留，但策略/预算尚未核验", original_error=report)
        binding = {key: report.get(key) for key in ("identity_hash", "action", "argv", "cwd", "inputs", "environment")}
        if report.get("environment") != _static_environment(root, report["argv"]):
            raise ContextError("静态检查工具/环境已变化，旧证据不可冒充当前执行")
        if report.get("input_hash") != _digest(binding) or report.get("identity_hash") != _digest(evidence_identity(ctx)):
            raise ContextError("静态证据实际命令/输入摘要不一致")
        result = report.get("result", {})
        if not isinstance(result.get("stdout"), str) or not isinstance(result.get("stderr"), str):
            raise ContextError("静态证据缺少真实命令输出")
        status, returncode = report.get("status"), result.get("returncode")
        successful = status == "PASS" and type(returncode) is int and returncode == 0
        failed = status == "FAIL" and type(returncode) is int and returncode != 0
        unavailable = status in ("TOOL_ERROR", "ENV_UNAVAILABLE") and returncode is None
        if not successful and not failed and not unavailable:
            raise ContextError("静态证据缺少已结束的真实结果，或结论与退出码不一致")
        if not successful and not allow_failure:
            raise policy.PolicyError("FAIL" if failed else "UNVERIFIED", "静态检查未通过或工具不可用", original_error=report)
    else:
        checks = report.get("checks")
        if report.get("status") not in ("PASS", "FAIL") or not isinstance(checks, list) or not checks:
            raise ContextError(f"{action} 缺少真实逐项检查结果")
        actual = []
        for check in checks:
            if not isinstance(check, dict):
                raise ContextError("检查项必须为结构化记录")
            if check.get("status") == "NA":
                if not isinstance(check.get("reason"), str) or not check["reason"].strip():
                    raise ContextError("NA 检查必须说明不适用原因")
                continue
            evidence = check.get("evidence")
            if (check.get("status") not in ("PASS", "FAIL") or not isinstance(evidence, list) or not evidence or
                    any(not isinstance(item, str) or not item.strip() for item in evidence)):
                raise ContextError(f"{action} 需要实际检查证据，不能仅声明结论")
            actual.append(check)
        if not actual or (action == "review" and not any(item.get("kind") == "code-review" for item in actual)):
            raise ContextError("缺少实际执行的检查，NA 不能替代审查")
        findings = report.get("findings", [])
        if not isinstance(findings, list):
            raise ContextError("findings 必须为数组")
        unresolved = False
        for item in findings:
            if not isinstance(item, dict) or not all(isinstance(item.get(key), str) and item[key].strip()
                    for key in ("id", "severity", "status")):
                raise ContextError("发现缺少 id/severity/status")
            evidence = item.get("evidence")
            evidence = [evidence] if isinstance(evidence, str) else evidence
            if not isinstance(evidence, list) or not evidence or any(not isinstance(value, str) or not value.strip() for value in evidence):
                raise ContextError("发现必须附带实际证据")
            status = item["status"].lower()
            if status == "accepted":
                if (item.get("kind") != "improvement" or item["severity"].lower() not in ("minor", "suggestion") or
                        not isinstance(item.get("reason"), str) or not item["reason"].strip()):
                    raise ContextError("仅有原因和证据的 Minor/Suggestion 纯优化可接受，错误不能改标 accepted")
            elif status not in ("fixed", "resolved", "closed"):
                unresolved = True
        failed = unresolved or any(item["status"] == "FAIL" for item in actual)
        if failed and report["status"] != "FAIL":
            raise ContextError("发现/检查实际失败，不能把报告结论标为 PASS")
        if (failed or report["status"] == "FAIL") and not allow_failure:
            raise policy.PolicyError("FAIL", f"{action} 仍未通过质量门", original_error=report)
    return report


def _ledger_run(root, ctx, run_id, env_id, ledger_root=None):
    from test_ledger import load, environment_hash
    ledger = Path(ledger_root or root).resolve()
    rows = load(root, ledger)
    row = next((item for item in rows if item.get("kind") == "run" and item.get("run_id") == run_id), None)
    if row is None or row.get("execution_context") != evidence_identity(ctx):
        raise ContextError("run_id 不属于当前实质任务范围")
    if not env_id or row.get("env_id") != env_id or row.get("environment_hash") != environment_hash():
        raise ContextError("运行环境与实跑记录不一致")
    latest = next((item for item in reversed(rows) if item.get("kind") == "run" and item.get("key") == row["key"]), None)
    if latest is None or latest["run_id"] != run_id:
        raise ContextError("不能复用同命令较新的失败之前的旧记录")
    return row


def verify_full_evidence(root, ctx, filename, env_id):
    """全量以实际 suite 清单及 full 账本验真，不把 targeted scope 改名为 full。"""
    from test_ledger import stable_pass, tree_snapshot
    from test_scope import is_test
    from project_inventory import default_excluded
    report = _read_evidence(root, ctx, filename, "full-regression")
    inventory = git_worktree_inventory(root, max_files=ctx["execution_budget"]["scanned_files"])
    policy.reserve_budget(root, ctx, "scanned_files", len(inventory["files"]), action="full-regression")
    discovered = sorted(path for path in inventory["files"]
                        if is_test(path) and not default_excluded(path, inventory["repositories"]))
    if sorted(report.get("tests", [])) != discovered:
        raise ContextError("full 清单没有精确列出当前全部已发现测试")
    suites = report.get("suites")
    if not isinstance(suites, list) or not suites:
        raise ContextError("全量证据缺少完整 suite/run-id 清单")
    covered, ids, names = set(), set(), set()
    snapshots = {}
    for suite in suites:
        if not isinstance(suite, dict) or not suite.get("name") or suite["name"] in names:
            raise ContextError("full suite 名称必须非空且唯一")
        names.add(suite["name"])
        row = _ledger_run(root, ctx, suite.get("run_id"), env_id, report.get("ledger_root"))
        if row["run_id"] in ids or row.get("scope") != "full" or not stable_pass(row):
            raise ContextError("full 要求每套最新真实 PASS，不接受 CARRIED/ERROR/重复 run")
        if row.get("command") != suite.get("command"):
            raise ContextError("suite 命令与实跑 argv 不一致")
        actual_cwd = row.get("context", {}).get("cwd")
        declared_cwd = suite.get("cwd", ".")
        if actual_cwd not in (declared_cwd, str((root / declared_cwd).resolve())):
            raise ContextError("suite cwd 与实跑目录不一致")
        key = tuple(row["inputs"])
        if key not in snapshots:
            snapshots[key] = tree_snapshot(root, row["inputs"])
        if snapshots[key]["hash"] != row.get("after_hash"):
            raise ContextError("full 实跑后的代码/资源/显式输入已经变化")
        tests = suite.get("tests")
        if not isinstance(tests, list) or any(path not in discovered for path in tests):
            raise ContextError("suite tests 不属于真实测试清单")
        covered.update(tests)
        ids.add(row["run_id"])
    if covered != set(discovered):
        raise ContextError("suite 实跑清单没有覆盖全部测试")
    return {"kind": "full-verification", "status": "PASS", "execution_context": evidence_identity(ctx),
            "run_ids": sorted(ids), "tests": discovered, "unmapped": [], "unrunnable": [], "minor": False}


def _equivalent_inputs(root, ctx, run_id, env_id, review_evidence, ledger_root=None):
    from test_ledger import tree_snapshot
    policy.require_action(ctx, "equivalent-evidence")
    policy.require_action(ctx, "related-test")
    if not review_evidence:
        raise ContextError("预定义等价路径需要已有适用审查，不自动补派审查")
    row = _ledger_run(root, ctx, run_id, env_id, ledger_root)
    if (row.get("status") != "ERROR" or row.get("exit_code") != 0 or
            row.get("failure_kind") not in ("TOOL_ERROR", "TREE_CHANGED", "ENV_UNAVAILABLE")):
        raise ContextError("等价路径仅接受实跑 exit0 的原工具错误，业务 FAIL 不可替代")
    snapshot = tree_snapshot(root, row["inputs"])
    if snapshot["hash"] != row.get("before_hash") or snapshot["files"] != row.get("files"):
        raise ContextError("等价证据要求当前代码/资源/显式输入与原实跑完全一致")
    review = _read_evidence(root, ctx, review_evidence, "review")
    # 完整树摘要由账本提供；审查还必须覆盖真实选中源码/测试/显式输入。
    selection = (row.get("scope_binding") or {}).get("item", {})
    required = set(selection.get("sources", [])) | set(selection.get("tests", [])) | set(row["inputs"])
    if not required <= set(review["inputs"]):
        raise ContextError("已有审查未覆盖原运行的源码/测试/显式输入")
    return row, snapshot, review


def record_equivalent(root, execution_context, original_run_id, env_id, review_evidence, ledger_root=None):
    """唯一预定义等价路径；写独立 alternative，原 ERROR 行永不改写。"""
    root = _root(root)
    ctx = load_context(root, execution_context)
    row, snapshot, review = _equivalent_inputs(root, ctx, original_run_id, env_id, review_evidence, ledger_root)
    record = {"schema": 1, "kind": "alternative-evidence", "status": "EQUIVALENT",
        "execution_context": evidence_identity(ctx), "authorization_identity_hash": identity_hash(ctx),
        "original_run_id": original_run_id, "original_error_hash": _digest(row), "original_error": row,
        "source_tree_hash": snapshot["hash"], "env_id": env_id, "ledger_root": str(ledger_root or root),
        "review_evidence": str(review_evidence), "review_hash": _digest(review), "created_at": time.time()}
    record["checksum"] = _digest(record)
    path = _context_path(root, ctx["task_id"]).with_name("equivalent-" + original_run_id + ".json")
    _atomic_json(root, path, record)
    return {"status": "EQUIVALENT", "evidence_file": str(path), "original_run_id": original_run_id,
            "original_status": row["status"]}


def _verify_equivalent(root, ctx, filename, scope_file, scope_hash, run_ids, env_id):
    from test_ledger import read_scope
    path = Path(filename)
    path = path if path.is_absolute() else root / path
    _safe_inside(root, path)
    alternative = json.loads(path.read_text(encoding="utf-8"))
    if (alternative.get("kind") != "alternative-evidence" or alternative.get("status") != "EQUIVALENT" or
            alternative.get("execution_context") != evidence_identity(ctx) or
            alternative.get("checksum") != _digest({key: value for key, value in alternative.items() if key != "checksum"})):
        raise ContextError("等价证据结构/身份无效")
    row, snapshot, review = _equivalent_inputs(root, ctx, alternative["original_run_id"], env_id,
        alternative["review_evidence"], alternative.get("ledger_root"))
    if _digest(row) != alternative["original_error_hash"] or _digest(review) != alternative["review_hash"]:
        raise ContextError("原错误或既有审查证据已变化")
    plan = read_scope(root, scope_file, scope_hash, _context_path(root, ctx["task_id"]))
    binding = row.get("scope_binding") or {}
    if (list(run_ids) != [row["run_id"]] or binding.get("plan") != plan or
            plan["runs"] != [binding.get("item")] or row.get("scope_hash") != scope_hash):
        raise ContextError("预定义等价路径仅覆盖精确单运行 scope，不能遮蔽其他失败或未执行项")
    return {"kind": "alternative-verification", "status": "EQUIVALENT", "execution_context": evidence_identity(ctx),
        "run_ids": list(run_ids), "original_error": row, "alternative_evidence": str(path), "scope_hash": scope_hash,
        "unmapped": plan["unmapped"], "unrunnable": plan["unrunnable"], "minor": bool(plan["unmapped"])}


def _finished_test_runs(root, ctx, plan, run_ids, env_id):
    """只读测试任务可结束并报告 FAIL/UNVERIFIED，不以修复作为完成动作的前提。"""
    from test_ledger import tree_snapshot, evidence_hash
    rows, actual = [], []
    snapshots = {}
    for run_id in run_ids:
        row = _ledger_run(root, ctx, run_id, env_id)
        binding = row.get("scope_binding") or {}
        if binding.get("plan") != plan or row.get("scope_hash") != plan["scope_hash"]:
            raise ContextError("检测结果未绑定当前精确范围")
        if row.get("status") not in ("PASS", "FAIL", "ERROR", "CARRIED"):
            raise ContextError("测试尚未结束，不能登记动作完成")
        key = tuple(row["inputs"])
        if key not in snapshots:
            snapshots[key] = tree_snapshot(root, row["inputs"])
        expected_hash = evidence_hash(row) if row["status"] in ("PASS", "CARRIED") else row.get("after_hash") or row["before_hash"]
        if snapshots[key]["hash"] != expected_hash:
            raise ContextError("测试结束后源码/输入已变化，检测结论须保留原范围不能冒充当前结果")
        actual.append(_digest(binding.get("item")))
        rows.append(row)
    if sorted(actual) != sorted(_digest(item) for item in plan["runs"]):
        raise ContextError("run_ids 未精确覆盖已请求测试，不能把未执行项标完成")
    if not any(row["status"] in ("FAIL", "ERROR") for row in rows):
        raise ContextError("没有已结束的失败/工具错误记录，不能把未执行项归为业务 FAIL")
    verdict = "UNVERIFIED" if any(row["status"] == "ERROR" for row in rows) else "FAIL"
    return {"kind": "test-execution-result", "status": verdict, "action_completed": True,
            "execution_context": evidence_identity(ctx), "scope_hash": plan["scope_hash"],
            "run_ids": list(run_ids), "original_runs": rows, "unmapped": plan["unmapped"],
            "unrunnable": plan["unrunnable"], "minor": bool(plan["unmapped"])}


def check_completion(root, execution_context, scope_file=None, scope_hash=None, env_id=None,
                     run_ids=(), review_name=None, pending_authorizations=(), static_evidence=None,
                     review_evidence=None, action_evidence=None, full_evidence=None, equivalent_evidence=None):
    """只核验本任务已授权证据；未请求项不是 PASS、失败或欠账。"""
    root = _root(root)
    ctx = load_context(root, execution_context)
    allowed = set(ctx["allowed_actions"])
    diagnostic_only = ctx["task_scope"]["kind"] in ("review", "test") and "implement" not in allowed
    checks = {action: ("AUTHORIZED" if action in {"document", "commit", "push", "deploy", "equivalent-evidence"}
                       else "UNVERIFIED") if action in allowed else "NOT_REQUESTED"
              for action in policy.OPTIONAL_ACTIONS | {"static"}}
    result = dict(_result(root, ctx), completed=False, ready=False, action_completed=False,
                  quality_verdict="UNVERIFIED", quality_status="UNVERIFIED", status="UNVERIFIED", checks=checks,
                  not_requested_actions=sorted(policy.OPTIONAL_ACTIONS - allowed))
    supplied = {policy.canonical_action(key): value for key, value in (action_evidence or {}).items()}
    try:
        # 可选流程的未授权提示不阻止普通任务收口；已授权动作自身等待才是阻塞。
        pending = [item for item in pending_authorizations if policy.canonical_action(item) in allowed]
        if pending:
            return dict(result, status="BLOCKED_AUTHORIZATION", pending_authorizations=pending)
        if "static" in allowed:
            if not static_evidence:
                raise ContextError("完成需要 --static-evidence 的实际静态命令证据")
            result["static"] = _read_evidence(root, ctx, static_evidence, "static", allow_failure=diagnostic_only)
            static_status = result["static"]["status"]
            checks["static"] = static_status if static_status in ("PASS", "FAIL") else "UNVERIFIED"
        verification = None
        if "full-regression" in allowed:
            if not full_evidence:
                raise ContextError("全量回归需要 --full-evidence 的真实 suite/run-id 清单")
            full = verify_full_evidence(root, ctx, full_evidence, env_id)
            result["full_regression"] = full
            checks["full-regression"] = "PASS"
        if "related-test" in allowed:
            from test_ledger import verify_scope, read_scope
            if not scope_file or not scope_hash or not env_id:
                raise ContextError("已授权测试需要 scope-file/scope-hash/env-id 与当前全部 run-id")
            plan = read_scope(root, scope_file, scope_hash, execution_context)
            try:
                verification = verify_scope(root, scope_file, scope_hash, list(run_ids), env_id,
                                            execution_context=execution_context)
            except ValueError as original_error:
                if getattr(original_error, "status", None) in ("BUDGET_EXCEEDED", "UNAUTHORIZED") or str(original_error).startswith("BUDGET_EXCEEDED"):
                    raise
                if equivalent_evidence:
                    verification = _verify_equivalent(root, ctx, equivalent_evidence, scope_file, scope_hash, run_ids, env_id)
                else:
                    try:
                        ended = _finished_test_runs(root, ctx, plan, run_ids, env_id)
                    except ValueError:
                        raise original_error
                    if not diagnostic_only:
                        raise policy.PolicyError(ended["status"], "实际测试未通过开发质量门",
                                                 original_runs=ended["original_runs"]) from original_error
                    verification = ended
            if verification.get("execution_context") != evidence_identity(ctx):
                raise ContextError("测试证据不属于当前任务范围/核验策略")
            accepted = {"PASS", "CARRIED", "EMPTY", "PARTIAL", "EQUIVALENT"}
            if diagnostic_only and verification.get("action_completed"):
                accepted.update(("FAIL", "UNVERIFIED"))
            if verification.get("status") not in accepted or verification.get("unrunnable"):
                raise policy.PolicyError(verification.get("status", "UNVERIFIED"), "授权测试未通过")
            action = "related-test"
            checks[action] = verification["status"]
            if verification["status"] == "EQUIVALENT":
                checks["equivalent-evidence"] = "EQUIVALENT"
            if "related-test" in allowed:
                checks["related-test"] = verification["status"]
            result.update(verification=verification, minor=bool(verification.get("minor")),
                          unmapped=verification.get("unmapped", []), scope_hash=scope_hash,
                          run_ids=verification["run_ids"], env_id=env_id)
        if "review" in allowed:
            if review_evidence:
                result["review"] = _read_evidence(root, ctx, review_evidence, "review", allow_failure=diagnostic_only)
            elif "full-cvl" in allowed and supplied.get("full-cvl"):
                report = _read_evidence(root, ctx, supplied["full-cvl"], "full-cvl", allow_failure=diagnostic_only)
                if not any(item.get("kind") == "code-review" for item in report["checks"]):
                    raise ContextError("full-cvl 证据缺少实际 code-review 检查")
                result["review"] = report  # 同 scope 质量审查只执行一次。
            elif review_name and env_id:
                from test_ledger import review_delta
                review = review_delta(root, review_name, env_id, execution_context=execution_context)
                if (review.get("execution_context") != evidence_identity(ctx) or review.get("code_changed") is not False
                        or review.get("requires_verification")):
                    raise ContextError("审查基线不属于当前范围或代码已变化")
                if verification and (review.get("scope_hash") != scope_hash or
                        sorted(review.get("run_ids", [])) != sorted(verification.get("run_ids", []))):
                    raise ContextError("审查与当前 scope/run_ids 不一致")
                result["review"] = review
            else:
                raise ContextError("已授权审查需要 review-evidence 或当前 ledger review-name")
            checks["review"] = result["review"].get("status", "PASS")
        for action in sorted(allowed & {"full-cvl", "docs-audit", "live-tests", "migration-rehearsal",
                                         "deployment-tool-development"}):
            if not supplied.get(action):
                raise ContextError(f"已授权 {action} 需要 --action-evidence {action}=FILE")
            result[action] = _read_evidence(root, ctx, supplied[action], action, allow_failure=diagnostic_only)
            checks[action] = result[action]["status"]
        pending_actions = []
        for action in (name for name in ("commit", "push", "deploy") if name in allowed):
            if action not in supplied:
                pending_actions.append(action)
                continue
            receipt = _read_evidence(root, ctx, supplied[action], action)
            execution = receipt.get("result", {})
            command = receipt.get("argv")
            actual_command = (isinstance(command, list) and bool(command) and
                execution.get("returncode") == 0 and isinstance(execution.get("stdout"), str) and
                isinstance(execution.get("stderr"), str))
            provider_receipt = receipt.get("receipt", {})
            actual_receipt = (isinstance(provider_receipt, dict) and
                provider_receipt.get("status") in ("success", "successful", "succeeded", "passed", "deployed", "committed", "pushed") and
                any(isinstance(provider_receipt.get(key), str) and provider_receipt[key].strip()
                    for key in ("id", "url", "sha", "run_id")))
            if not actual_command and not actual_receipt:
                raise ContextError(f"{action} 需要实际工具结果/提供方 receipt，AUTHORIZED 不等于已执行")
            result[action] = receipt
            checks[action] = "PASS"
        result["pending_actions"] = pending_actions
        if "implement" in allowed or "document" in allowed:
            result.update(completion_obligations(root, execution_context))
        else:
            result.update(obligations=[], blocking_obligations=[], external_obligations=[], diagnostics=[])
        if result["blocking_obligations"]:
            return dict(result, status="BLOCKED_OBLIGATIONS", error="本任务新增族登记问题尚未闭环")
        if identity_hash(load_context(root, execution_context)) != identity_hash(ctx):
            raise ContextError("核验期间策略 revision 已变化，请读取当前上下文")
        verdict = verification["status"] if verification else "PASS"
        if "FAIL" in checks.values():
            verdict = "FAIL"
        if diagnostic_only and "UNVERIFIED" in checks.values():
            verdict = "UNVERIFIED"
        return dict(result, ready=True, ready_for_release=verdict not in ("FAIL", "UNVERIFIED"),
                    status=verdict, action_completed=not pending_actions, terminal=not pending_actions,
                    action_status="PENDING_ACTIONS" if pending_actions else
                        ("TERMINATED" if verdict == "UNVERIFIED" else "COMPLETED"),
                    quality_verdict=verdict, quality_status=verdict)
    except (ValueError, OSError) as exc:
        return dict(result, error=str(exc), status=getattr(exc, "status", "UNVERIFIED"),
                    quality_verdict=getattr(exc, "status", "UNVERIFIED"), quality_status=getattr(exc, "status", "UNVERIFIED"),
                    diagnostic=getattr(exc, "details", {}))


def complete_context(root, execution_context, **evidence):
    root = _root(root)
    result = check_completion(root, execution_context, **evidence)
    if result["ready"] and result.get("pending_actions"):
        result.update(ready=False, completed=False, action_completed=False, status="PENDING_ACTIONS",
                      error="继续执行已授权动作并附实际回执；无需重新授权或重跑既有验证")
    with _task_lock(root, execution_context) as ctx:
        if result["identity_hash"] != identity_hash(ctx):
            result.update(ready=False, status="UNVERIFIED", error="完成期间上下文策略已修订")
        if result["ready"] and ctx["mode"] == "formal":
            result.update(ready=False, status="FORMAL_GATES_REQUIRED",
                          error="正式模式必须继续原正式门与归档流程；本任务完成门不替代 Sprint close")
        previously_completed = ctx["status"] == "completed"
        if result["ready"]:
            ctx["status"] = "completed"
            ctx["completed_at"] = time.time()
            result["completed"] = True
        elif previously_completed:
            ctx["status"] = "active"
            ctx.pop("completed_at", None)
        report = _context_path(root, ctx["task_id"]).with_name("completion.json")
        result["report"] = str(report)
        _atomic_json(root, report, result)
        if result["completed"] or previously_completed:
            _save(root, ctx)
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("resolve", "route", "revise", "fork", "bind-sprint", "fork-version", "fork-test-build", "resolve-autopilot-root", "resolve-test-root", "static", "equivalent", "check", "complete"):
        item = sub.add_parser(command)
        item.add_argument("--root", default=".")
        item.add_argument("--json", action="store_true")
        item.add_argument("--execution-context", required=command not in ("resolve", "resolve-autopilot-root", "resolve-test-root"))
        if command in ("resolve", "route"):
            item.add_argument("--entry", required=command == "resolve")
        if command == "resolve":
            item.add_argument("--version")
            item.add_argument("--sprint")
            item.add_argument("--since")
            item.add_argument("--acceptance", nargs="+", action="extend")
            item.add_argument("--task-scope", choices=tuple(policy.SCOPE_ACTIONS))
        if command in ("resolve", "revise"):
            item.add_argument("--write-set", nargs="+", action="extend")
            item.add_argument("--grant", action="append", default=[])
            item.add_argument("--authorization-source", type=json.loads)
            item.add_argument("--execution-budget", type=json.loads)
        if command in ("fork", "bind-sprint"):
            item.add_argument("--sprint", required=True)
            item.add_argument("--since")
        if command in ("resolve-autopilot-root", "resolve-test-root"):
            item.add_argument("--version", required=True)
            item.add_argument("--authorization-source", type=json.loads)
            item.add_argument("--existing-only", action="store_true")
        if command == "fork":
            item.add_argument("--allow-action", action="append")
        if command in ("fork-version", "fork-test-build"):
            item.add_argument("--version", required=True)
        if command == "fork-test-build":
            item.add_argument("--build-id", required=True)
        if command == "route":
            item.add_argument("--phase", choices=tuple(LIGHT_ACTIONS), default="route")
            item.add_argument("--action")
        if command == "static":
            item.add_argument("--input", action="append", required=True)
            item.add_argument("--timeout", type=float, default=30)
            item.add_argument("argv", nargs=argparse.REMAINDER)
        if command == "equivalent":
            item.add_argument("--original-run-id", required=True)
            item.add_argument("--env-id", required=True)
            item.add_argument("--review-evidence", required=True)
            item.add_argument("--ledger-root")
        if command in ("check", "complete"):
            item.add_argument("--scope-file")
            item.add_argument("--scope-hash")
            item.add_argument("--env-id")
            item.add_argument("--run-id", action="append", default=[])
            item.add_argument("--review-name")
            item.add_argument("--static-evidence")
            item.add_argument("--full-evidence")
            item.add_argument("--equivalent-evidence")
            item.add_argument("--review-evidence")
            item.add_argument("--action-evidence", action="append", default=[])
            item.add_argument("--pending-authorization", action="append", default=[])
    args = parser.parse_args(argv)
    code = 0
    try:
        if args.command == "resolve":
            result = resolve_context(args.root, args.entry, args.version, args.sprint,
                args.execution_context, args.since, args.write_set, args.acceptance,
                additional_grants=args.grant, authorization_source=args.authorization_source,
                execution_budget=args.execution_budget, task_scope=args.task_scope)
        elif args.command in ("resolve-autopilot-root", "resolve-test-root"):
            operation = resolve_autopilot_root if args.command == "resolve-autopilot-root" else resolve_test_root
            result = operation(args.root, args.version, args.execution_context, args.authorization_source, existing_only=args.existing_only)
        elif args.command == "route":
            result = route_context(args.root, args.execution_context, args.phase, args.entry, args.action)
        elif args.command == "revise":
            result = revise_context(args.root, args.execution_context, args.write_set,
                additional_grants=args.grant, authorization_source=args.authorization_source,
                execution_budget=args.execution_budget)
        elif args.command in ("fork", "bind-sprint"):
            operation = fork_context if args.command == "fork" else bind_sprint
            if args.command == "fork":
                result = operation(args.root, args.execution_context, args.sprint, args.since, allowed_actions=args.allow_action)
            else:
                result = operation(args.root, args.execution_context, args.sprint, args.since)
        elif args.command == "fork-version":
            result = fork_version(args.root, args.execution_context, args.version)
        elif args.command == "fork-test-build":
            result = fork_test_build(args.root, args.execution_context, args.version, args.build_id)
        elif args.command == "equivalent":
            result = record_equivalent(args.root, args.execution_context, args.original_run_id,
                                       args.env_id, args.review_evidence, args.ledger_root)
        elif args.command == "static":
            argv = args.argv[1:] if args.argv[:1] == ["--"] else args.argv
            result = run_static(args.root, args.execution_context, argv, args.input, args.timeout)
            code = 0 if result["status"] == "PASS" else 2
        else:
            operation = complete_context if args.command == "complete" else check_completion
            evidence = {}
            for value in args.action_evidence:
                action, separator, filename = value.partition("=")
                if not separator or not filename:
                    raise ContextError("action-evidence 必须为 ACTION=FILE")
                evidence[action] = filename
            result = operation(args.root, args.execution_context, scope_file=args.scope_file,
                scope_hash=args.scope_hash, env_id=args.env_id, run_ids=args.run_id,
                review_name=args.review_name, pending_authorizations=args.pending_authorization,
                static_evidence=args.static_evidence, review_evidence=args.review_evidence, action_evidence=evidence,
                full_evidence=args.full_evidence, equivalent_evidence=args.equivalent_evidence)
            code = 0 if result["ready"] else 2
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        result, code = {"status": getattr(exc, "status", "ERROR"), "error": str(exc),
                        "details": getattr(exc, "details", {}), "completed": False}, 2
    result.pop("context", None)  # CLI 只返路径/身份摘要，初始全清单留在 context.json。
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
