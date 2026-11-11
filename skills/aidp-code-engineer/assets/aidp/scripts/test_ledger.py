#!/usr/bin/env python3
"""执行选中测试、复用同树 PASS、追溯跨树证据并登记审查基线。

run --root . --cwd . --scope targeted|sprint|task|full --env-id ENV [--input PATH] [--ledger-root DIR] -- argv...
run-scope --root . --scope-file PATH --env-id ENV [--input PATH] [--force] [--timeout SECONDS]
verify --root . --scope-file PATH --scope-hash HASH --env-id ENV [--run-id ID ...]
record-review --root . --name NAME --scope-file PATH --scope-hash HASH --env-id ENV --report PATH [--run-id ID ...]
review-delta --root . --name NAME --env-id ENV
上述命令均接受 --execution-context PATH；light 自动使用 task 身份，所有证据绑定该任务。
light 的 --report 是独立 code-review JSON，可放 memory/.aidp；要求 reviewer、scope_hash、
execution_context、真实 code-review PASS checks 和已闭环 findings，拒绝把测试汇总当审查。

run-scope 执行前重推 Git+write_set 范围；run_ids 必须精确覆盖全部运行项才能 verify。
命名测试按安全批次记账，完整计划和快照内容寻址单存。前后导入闭包均证明不相交时登记 CARRIED、
source_run_id/source_tree_hash/assessment_hash/delta，绝不冒充当前整树已实跑 PASS。
命名映射和兄弟目录都不是独立证明。未知依赖/配置/文件增删使已有 Sprint 选择保守补跑；
related/其它语言跨树不猜测独立性。runner 的 env_id 和 inputs 与整体 env-id 一起绑定复用键。
EMPTY 表示无对应测试，PARTIAL 表示 Minor 未覆盖，均不伪造 PASS/run_id；可登记审查。
FAIL 为实际测试失败；工具缺失/超时/树变化为 UNVERIFIED（单 run 为 ERROR/TREE_CHANGED）。

full 只供 /sprint-aiauto-test：run 的 ledger_root 使用每 build 专属缓存目录，不能混用主仓
Sprint 账本。外置 full 账本按仓库身份/相对 cwd/内容树匹配，可跨临时 worktree 路径复用。
默认按主仓/每层子仓边界忽略 docs/、memory/ 及 CLAUDE.md、AGENTS.md、README.md；真实输入用 --input
或 runner.inputs 声明（相对 root，可为目录）。内容、权限、符号链接目标进入指纹。
环境仅排除 SHLVL、_、PWD、OLDPWD；外部状态改变须更新 env-id 或 --force。无 TTL。
账本是带校验和的本地证据，不是防恶意伪造签名。直接 run 保持原 API 兼容。
退出码：run 保留子进程退出码，超时124/启动127；run-scope 为0（PASS/CARRIED/EMPTY/PARTIAL）、
1（FAIL）、2（UNVERIFIED/输入证据错误）。verify/record-review 失败为2。stdout 最后一行为 JSON。
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import select
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import uuid

_script_dir = str(Path(__file__).resolve().parent)
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)
from aidp_paths import ensure_runtime_dir, test_ledger as ledger_path
from code_inventory import SKIP_DIR_NAMES
from vcs import detect_mode

SCHEMA = 1
ROOT_STATE_FILES = frozenset(("CLAUDE.md", "AGENTS.md", "README.md"))
SHELL_NOISE = frozenset(("SHLVL", "_", "PWD", "OLDPWD"))


class LedgerError(ValueError):
    """证据不可用或输入不明确；不可当作已通过。"""


def digest(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def environment_hash():
    # 环境值只以摘要存盘，避免将凭据写进账本。
    environment = {key: value for key, value in os.environ.items() if key not in SHELL_NOISE}
    return digest({"env": environment, "platform": sys.platform, "python": sys.version})


def project_path(root, value):
    path = Path(os.path.abspath(root / value))
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise LedgerError(f"路径必须在 root 内：{value}") from exc
    return path


def normalize_inputs(root, inputs):
    normalized = []
    for value in inputs:
        path = project_path(root, value)
        rel = path.relative_to(root).as_posix()
        if rel == "." or rel == ".git" or rel.startswith(".git/"):
            raise LedgerError("--input 须指定输入文件/目录，不能是整个 root 或 .git")
        if not path.exists() and not path.is_symlink():
            raise LedgerError(f"显式输入不存在：{value}")
        normalized.append(rel)
    return sorted(set(normalized))


def file_hash(path):
    mode = path.lstat().st_mode
    link = None
    if stat.S_ISLNK(mode):
        link = os.readlink(path)
        if not path.exists():
            return digest({"link": link, "target": "missing"})
        mode = path.stat().st_mode
    if not stat.S_ISREG(mode):
        raise LedgerError(f"输入不是普通文件（目录符号链接也不支持）：{path}")
    content = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            content.update(block)
    return digest({"sha256": content.hexdigest(), "mode": stat.S_IMODE(mode), "link": link})


class _FingerprintCache:
    """共享入口内容缓存；只保存可信 token→内容 hash，缓存损坏仅触发重读。"""
    def __init__(self, root):
        self.path = Path(ensure_runtime_dir(root)) / "content-fingerprints.json"
        self.files = {}
        try:
            record = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(record.get("files"), dict) and record.get("checksum") == digest(record["files"]):
                self.files = record["files"]
        except (OSError, ValueError, TypeError, AttributeError):
            pass
        from project_inventory import fingerprint_metadata
        self.metadata = fingerprint_metadata() or {}
        self.changed = False

    def read(self, path, on_read=None):
        from project_inventory import fingerprint_file
        key = str(path)
        def reader(target):
            if on_read:
                on_read(target)
            return file_hash(target)
        value = fingerprint_file(path, previous=self.files.get(key), reader=reader, metadata=self.metadata)
        if self.files.get(key) != value:
            self.files[key] = value
            self.changed = True
        return value

    def save(self):
        if not self.changed:
            return
        temporary = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.path.parent, delete=False) as stream:
                temporary = stream.name
                json.dump({"files": self.files, "checksum": digest(self.files)}, stream, sort_keys=True)
            os.replace(temporary, self.path)
            temporary = None
        finally:
            if temporary:
                Path(temporary).unlink(missing_ok=True)


def snapshot_paths(root, inputs=(), paths=None, inventory=None):
    """仅枚举与 stat，不读源码；供闭环预估和实际取证使用。"""
    root = Path(root).resolve()
    from project_inventory import git_worktree_inventory, default_excluded, runtime_excluded, generated_excluded
    mode = detect_mode(root)
    if mode != "git" and os.path.lexists(root / ".git"):
        raise LedgerError("存在 .git 但无法读取工作树；拒绝降级复用")
    selected, paths, directory_inputs = paths, set(), {}
    inventory = inventory or (git_worktree_inventory(root) if mode == "git" else {"repositories": ["."], "gitlinks": {}})

    def walk(base, fallback=False):
        def onerror(exc):
            raise exc
        for parent, dirs, names in os.walk(base, onerror=onerror, followlinks=False):
            parent = Path(parent)
            kept = []
            for name in dirs:
                path = parent / name
                if runtime_excluded(path.relative_to(root).as_posix()) or (fallback and (name in SKIP_DIR_NAMES or generated_excluded(path.relative_to(root).as_posix()))):
                    continue
                if path.is_symlink():
                    raise LedgerError(f"目录符号链接无法完整指纹：{path}")
                kept.append(name)
            dirs[:] = kept
            paths.update(parent / name for name in names
                         if not runtime_excluded((parent / name).relative_to(root).as_posix()))

    if selected is not None:
        paths.update(project_path(root, rel) for rel in selected
                     if not runtime_excluded(rel) and not rel.endswith("/@gitlink")
                     and ((root / rel).exists() or (root / rel).is_symlink()))
    elif mode == "git":
        paths.update(root / rel for rel in inventory["files"]
                     if not default_excluded(rel, inventory["repositories"])
                     and ((root / rel).exists() or (root / rel).is_symlink()))
    else:
        for path in root.iterdir():
            if default_excluded(path.name) or path.name in SKIP_DIR_NAMES:
                continue
            if path.is_dir() and not path.is_symlink():
                walk(path, fallback=True)
            else:
                paths.add(path)
    normalized = normalize_inputs(root, inputs)
    for rel in normalized:
        path = root / rel
        if runtime_excluded(rel):
            raise LedgerError("运行账本及 .git 不能作为显式输入")
        if path.is_dir() and not path.is_symlink():
            directory_inputs[rel + "/"] = digest("directory")
            walk(path)
        else:
            paths.add(path)
    return {"paths": sorted(paths), "directory_inputs": directory_inputs, "normalized": normalized,
            "inventory": inventory, "vcs_mode": mode}


def inventory_membership(root, inventory, paths):
    """目录成员仅算元数据；窄快照也必须感知新增/删除/重命名的解析候选。"""
    from project_inventory import default_excluded, installed_skill_package
    active = {None, *(installed_skill_package(root, path) for path in paths)}
    return digest(sorted(path for path in inventory.get("files", ())
                         if not default_excluded(path, inventory["repositories"])
                         and installed_skill_package(root, path) in active
                         and os.path.lexists(root / path)))


def snapshot_estimate(root, inputs=(), paths=None):
    """估算目前缓存未命中的内容读取；后置预算仍预留所有输入各读一次。"""
    from project_inventory import fingerprint_token
    plan = snapshot_paths(root, inputs, paths)
    cache = _FingerprintCache(root)
    misses, files = 0, dict(plan["directory_inputs"])
    for path in plan["paths"]:
        token = fingerprint_token(path, metadata=cache.metadata)
        cached = cache.files.get(str(path), {})
        if token is None or cached.get("token") != token:
            misses += 1
        else:
            files[path.relative_to(root).as_posix()] = cached["hash"]
    files.update({rel + "/@gitlink": digest({"kind": "gitlink", "path": rel, "indexed": pins.get("index") is not None})
                  for rel, pins in plan["inventory"]["gitlinks"].items()})
    if paths is not None:
        files["@inventory"] = inventory_membership(root, plan["inventory"], paths)
    return {"content_reads": misses, "objects": len(plan["paths"]), "files": files,
            "hash": digest({"files": files, "vcs_mode": plan["vcs_mode"]}) if not misses else None}


def tree_snapshot(root, inputs=(), *, paths=None, inventory=None, observer=None):
    """内容 hash 不含 token；token 只用于减少读取和检测执行窗口 A→B→A。"""
    root = Path(root).resolve()
    plan = snapshot_paths(root, inputs, paths, inventory)
    cache = _FingerprintCache(root)
    files, tokens, read_paths = {}, {}, set()
    io = {"objects": len(plan["paths"]), "content_reads": 0, "unique_files": 0,
          "metadata_entries": len(plan["inventory"].get("files", plan["paths"])), "cache_hits": 0,
          "tool_io": "unknown"}
    try:
        for path in plan["paths"]:
            # 在实际 reader 上计次，避免 stat 后竞态导致估计命中、实际读取却漏计。
            def observed_read(target):
                io["content_reads"] += 1
                read_paths.add(str(target))
            value = cache.read(path, observed_read)
            if not value["read"]:
                io["cache_hits"] += 1
            rel = path.relative_to(root).as_posix()
            if value["hash"] is not None:
                files[rel], tokens[rel] = value["hash"], {"token": value["token"], "observation": value.get("observation")}
    finally:
        io["unique_files"] = len(read_paths)
        if observer is not None:
            observer(io, read_paths)
        cache.save()
    files.update(plan["directory_inputs"])
    # Gitlink 结构是输入；提交 pin/HEAD 是事实，内容相同的提交不使测试失效。
    gitlinks = plan["inventory"]["gitlinks"]
    files.update({rel + "/@gitlink": digest({"kind": "gitlink", "path": rel, "indexed": pins.get("index") is not None})
                  for rel, pins in gitlinks.items()})
    if paths is not None:
        files["@inventory"] = inventory_membership(root, plan["inventory"], paths)
    normalized = plan["normalized"]
    categories = {p: ("input" if any(p == x or p.startswith(x + "/") for x in normalized) else "source")
                  for p in files}
    return {"files": files, "tokens": tokens, "gitlinks": gitlinks, "io": io,
            "vcs_mode": plan["vcs_mode"], "categories": categories,
            "hash": digest({"files": files, "vcs_mode": plan["vcs_mode"]})}


def snapshot_changed(before, after):
    if before["hash"] != after["hash"]:
        return True
    # 未知 token 的平台仍实读内容，但不声称具备可信执行窗口证据。
    return any(value is not None and after.get("tokens", {}).get(path) != value
               for path, value in before.get("tokens", {}).items())


@contextmanager
def lock(root, name):
    directory = Path(ensure_runtime_dir(root)) / "locks"
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ("test-ledger." + name + ".lock")).open("a+b") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield stream.fileno()
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def load(root, ledger=None):
    path = Path(ledger_path(ledger or root))
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        if not lines:
            raise LedgerError("账本为空或写入中断")
        rows, plans, snapshots, verified_plans = [], {}, {}, set()
        for line in lines:
            row = json.loads(line)
            if not isinstance(row, dict) or row.get("schema") != SCHEMA:
                raise LedgerError("账本记录结构/版本不正确")
            unsigned = {key: value for key, value in row.items() if key != "checksum"}
            external_full = (ledger is not None and Path(ledger).resolve() != root and row.get("scope") in ("full", "version")
                             and row.get("ledger_root") == str(Path(ledger).resolve()))
            external_record = (ledger is not None and row.get("kind") in {"plan", "snapshot"}
                               and row.get("root") == str(Path(ledger).resolve()))
            if row.get("checksum") != digest(unsigned) or (row.get("root") != str(root) and not external_full and not external_record):
                raise LedgerError("账本校验和或项目 root 不匹配")
            if row.get("kind") == "plan":
                plan = row["plan"]
                plan_id = row["plan_id"]
                if (plan_id != plan.get("scope_hash") or plan_id != digest({k: v for k, v in plan.items() if k != "scope_hash"})
                        or plan_id in plans):
                    raise LedgerError("内容寻址计划损坏或重复")
                plans[plan_id] = plan
                verified_plans.add(id(plan))
                continue
            if row.get("kind") == "snapshot":
                snapshot_id = row["snapshot_id"]
                if snapshot_id in snapshots or snapshot_id != digest({"files": row["files"], "vcs_mode": row["vcs_mode"]}):
                    raise LedgerError("内容寻址快照损坏或重复")
                snapshots[snapshot_id] = row
                continue
            if row.get("kind") == "run":
                bound_snapshot = row.pop("snapshot_id", None)
                if bound_snapshot is not None:
                    snapshot = snapshots[bound_snapshot]
                    if row["before_hash"] != bound_snapshot or row["vcs_mode"] != snapshot["vcs_mode"]:
                        raise LedgerError("运行快照引用损坏")
                    row["files"] = snapshot["files"]
                binding = row.get("scope_binding")
                if binding and "plan_id" in binding:
                    plan = plans[binding["plan_id"]]
                    matches = [item for item in plan["runs"] if digest(item) == binding["item_id"]]
                    if len(matches) != 1:
                        raise LedgerError("运行项引用损坏")
                    row["scope_binding"] = {"plan": plan, "item": matches[0]}

                if (not isinstance(row.get("context"), dict)
                        or row.get("key") != digest(row["context"])
                        or row.get("status") not in ("RUNNING", "PASS", "CARRIED", "FAIL", "ERROR", "TREE_CHANGED")
                        or not isinstance(row.get("run_id"), str)
                        or type(row.get("reuse_count")) is not int or row["reuse_count"] < 0):
                    raise LedgerError("测试记录字段损坏")
                if bound_snapshot is None and row["before_hash"] != digest({"files": row["files"], "vcs_mode": row["vcs_mode"]}):
                    raise LedgerError("测试快照损坏")
                if row["status"] == "PASS" and not stable_pass(row):
                    raise LedgerError("PASS 记录证据不完整")
                binding = row.get("scope_binding")
                if binding:
                    plan = binding["plan"]
                    if id(plan) not in verified_plans:
                        if plan["scope_hash"] != digest({k: v for k, v in plan.items() if k != "scope_hash"}):
                            raise LedgerError("Sprint 计划摘要损坏")
                        verified_plans.add(id(plan))
                    if (row.get("scope_hash") != plan["scope_hash"] or binding["item"] not in plan["runs"]
                            or row["context"].get("selection") != binding["item"]
                            or (plan.get("kind") != "version" and row["context"].get("execution_context") != plan.get("execution_context"))
                            or row.get("execution_context") != plan.get("execution_context")):
                        raise LedgerError("Sprint 范围绑定损坏")
                if row["status"] == "CARRIED":
                    parent = next((r for r in reversed(rows) if r["kind"] == "run" and r["key"] == row["key"]), None)
                    source = next((r for r in rows if r.get("run_id") == row["source_run_id"] and r["kind"] == "run"), None)
                    if (not stable_evidence(row) or not parent or parent["run_id"] != row.get("parent_run_id")
                            or not source or not stable_pass(source) or source["key"] != row["key"]
                            or source["after_hash"] != row["source_tree_hash"]
                            or not can_carry(parent, {"files": row["files"]}, binding, row["inputs"])
                            or row.get("delta") != snapshot_delta(parent["files"], row["files"])):
                        raise LedgerError("carry-forward 缺少可信来源或影响分析")
            elif row.get("kind") == "review":
                if (not row.get("name") or (not row.get("run_id") and not row.get("scope_hash")) or not row.get("report_hash")
                        or row.get("hash") != digest({"files": row["files"], "vcs_mode": row["vcs_mode"]})):
                    raise LedgerError("审查快照损坏")
                review_run_ids(row)
            else:
                raise LedgerError("未知账本记录类型")
            rows.append(row)
        return rows
    except (ValueError, KeyError, TypeError, UnicodeError) as exc:
        raise LedgerError(f"账本损坏，拒绝复用：{exc}") from exc


def save(root, rows, ledger=None):
    """调用方持短写锁；写临时文件 + fsync + replace，不追加半条 JSON。"""
    path = Path(ledger_path(ledger or root))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=path.name + ".", delete=False) as stream:
            temporary = stream.name
            plans, snapshots = set(), set()
            def emit(value):
                unsigned = {key: item for key, item in value.items() if key != "checksum"}
                stream.write(json.dumps(dict(unsigned, checksum=digest(unsigned)), ensure_ascii=True, sort_keys=True) + "\n")
            for original in rows:
                row = dict(original)
                binding = row.get("scope_binding")
                if binding and "plan" in binding:
                    plan, item = binding["plan"], binding["item"]
                    plan_id = plan["scope_hash"]
                    if plan_id not in plans:
                        emit({"schema": SCHEMA, "kind": "plan", "root": str(Path(ledger or root).resolve()), "plan_id": plan_id, "plan": plan})
                        plans.add(plan_id)
                    row["scope_binding"] = {"plan_id": plan_id, "item_id": digest(item)}
                    snapshot_id = digest({"files": row["files"], "vcs_mode": row["vcs_mode"]})
                    if snapshot_id not in snapshots:
                        emit({"schema": SCHEMA, "kind": "snapshot", "root": str(Path(ledger or root).resolve()), "snapshot_id": snapshot_id,
                              "files": row["files"], "vcs_mode": row["vcs_mode"]})
                        snapshots.add(snapshot_id)
                    row["snapshot_id"] = snapshot_id
                    row.pop("files")
                emit(row)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)


def persist_run(root, ledger, row):
    with lock(ledger, "write"):
        rows = load(root, ledger)
        index = next((i for i, value in enumerate(rows) if value.get("run_id") == row["run_id"] and value["kind"] == "run"), None)
        if index is None:
            raise LedgerError("执行中的账本记录丢失，拒绝出具 PASS")
        rows[index] = row
        save(root, rows, ledger)


def stable_pass(row):
    return (row.get("status") == "PASS" and type(row.get("exit_code")) is int
            and row["exit_code"] == 0 and bool(row.get("before_hash"))
            and row["before_hash"] == row.get("after_hash"))


def evidence_hash(row):
    return row.get("assessment_hash") if row.get("status") == "CARRIED" else row.get("after_hash")


def stable_evidence(row):
    return stable_pass(row) or (row.get("status") == "CARRIED" and row.get("exit_code") is None
                               and row.get("after_hash") is None and row.get("assessment_hash") == row.get("before_hash")
                               and bool(row.get("source_run_id")) and bool(row.get("source_tree_hash")))


def snapshot_delta(old, new):
    return sorted(p for p in old.keys() | new.keys() if old.get(p) != new.get(p))


def version_content_identity(plan):
    manifest = plan.get("manifest", {})
    return {key: manifest.get(key) for key in ("version", "acceptance_baseline", "acceptance_tests", "dependencies")}


def can_carry(previous, current, binding, inputs):
    """执行与历史加载共用同一闭包判据；旧命名映射不构成独立证据。"""
    from test_scope import DEPENDENCY_POLICY, dependency_impact, within
    old_binding = previous.get("scope_binding")
    if not stable_evidence(previous) or not old_binding or not binding or previous["inputs"] != list(inputs):
        return False
    old_plan, plan = old_binding["plan"], binding["plan"]
    if plan.get("kind") == "version" or old_plan.get("kind") == "version":
        if (plan.get("kind") != old_plan.get("kind") or version_content_identity(old_plan) != version_content_identity(plan)
                or old_plan["modules"] != plan["modules"]):
            return False
    elif (old_plan.get("execution_context") != plan.get("execution_context")
            or any(old_plan[k] != plan[k] for k in ("since", "modules"))):
        return False
    if old_binding["item"] != binding["item"]:
        return False
    item = binding["item"]
    # 不用当前源码重新解释历史；闭包绑定于各自完整范围和树快照。
    analyses = [p.get("dependencies", {}) for p in (old_plan, plan)]
    if any(not isinstance(a, dict) or a.get("policy") != DEPENDENCY_POLICY
           or not isinstance(a.get("tests"), dict) for a in analyses):
        return False
    changes = snapshot_delta(previous["files"], current["files"])
    if not changes:
        return True  # 同树、同选择；其它运行器的 env_id/inputs 不应强迫本项实跑。
    if item["mode"] != "named" or not item["tests"]:
        return False
    if any(any(within(path, explicit) for explicit in inputs) for path in changes):
        return False
    # 配置、其它语言、增删文件可能改变解析/加载方式，不按模块目录推测独立。
    if any(not path.endswith(".py") or path not in previous["files"] or path not in current["files"]
           for path in changes):
        return False
    for analysis in analyses:
        for test in item["tests"]:
            proof = analysis.get("tests", {}).get(test)
            if not isinstance(proof, dict) or not proof or dependency_impact(proof, changes):
                return False
    return True


def result(row, reused=False):
    # 文件清单只在账本存储，CLI 回包保持小而可读。
    return {key: value for key, value in dict(row, reused=reused).items()
            if key not in ("files", "tokens", "checksum", "context", "scope_binding", "snapshot_id")}


def python_runner_module(command):
    """仅识别解释器自身的 -m，不把脚本/-c 后的业务参数当运行器。"""
    if not Path(command[0]).name.startswith(("python", "pypy")) or "-m" not in command:
        return None
    index = command.index("-m")
    if index + 1 >= len(command) or "-c" in command[:index] or any(arg.endswith(".py") for arg in command[1:index]):
        return None
    return command[index + 1]


def missing_python_runner(command, stderr):
    """模块名和解释器顶层诊断同时匹配；业务 traceback 的 ModuleNotFoundError 不是工具缺失。"""
    module = python_runner_module(command)
    if not module or "Traceback (most recent call last)" in stderr:
        return False
    for line in stderr.splitlines():
        executable, separator, diagnostic = line.partition(": ")
        if not separator or not Path(executable).name.startswith(("python", "pypy")):
            continue
        if diagnostic in (f"No module named {module}", f"No module named '{module}'", f'No module named "{module}"'):
            return True
        prefix = f"Error while finding module specification for '{module}' (ModuleNotFoundError: No module named '"
        if diagnostic.startswith(prefix) and diagnostic.endswith("')"):
            missing = diagnostic[len(prefix):-2]
            if module == missing or module.startswith(missing + "."):
                return True
    return False


class _ValidationProgress:
    """现有预算票据的累计观测适配器；资源状态仅由 execution_policy 保存。"""
    def __init__(self, root, context, stages, input_hash, action, *, defer_input=False):
        from execution_policy import reserve_validation
        self.root, self.context = root, context
        self.actual = {name: {} for name in stages}
        self.paths, self.selected, self.run_ids = set(), set(), []
        self.observations = {"unique_files": 0, "metadata_entries": 0, "cache_hits": 0, "tool_objects": 0}
        options = {"defer_input": True} if defer_input else {}
        self.ticket = reserve_validation(root, context, stages, input_hash, action=action, **options)
        self.finished = False

    def bind(self, input_hash):
        if self.ticket.get("input_bound") is False:
            from execution_policy import bind_validation_input
            self.ticket = bind_validation_input(self.root, self.context, self.ticket, input_hash)
        elif self.ticket.get("input_hash") != input_hash:
            raise LedgerError("TREE_CHANGED：预算预估后真实验证输入已变化，请重新预留")

    def observe(self, stage):
        def record(io, paths):
            values = self.actual[stage]
            values["scanned_files"] = values.get("scanned_files", 0) + io["content_reads"]
            self.paths.update(paths)
            self.observations["unique_files"] = len(self.paths)
            self.observations["metadata_entries"] += io["metadata_entries"]
            self.observations["cache_hits"] += io["cache_hits"]
        return record

    def command(self, row, selected):
        values = self.actual["command"]
        values["processes"] = values.get("processes", 0) + int(row.get("process_started", False))
        values["elapsed_seconds"] = values.get("elapsed_seconds", 0) + row["duration_seconds"]
        if row.get("process_started"):
            self.selected.update(selected)
        values["selected_tests"] = len(self.selected)
        self.observations["tool_objects"] = len(self.selected)
        self.run_ids.append(row["run_id"])
        self.flush()

    def flush(self):
        from execution_policy import record_validation_usage
        record_validation_usage(self.root, self.context, self.ticket, self.actual, observations=self.observations)

    def summary(self):
        return {"evidence_content_reads": sum(stage.get("scanned_files", 0) for stage in self.actual.values()),
                "distinct_content_files": len(self.paths), "selected_objects": len(self.selected),
                "metadata_entries": self.observations["metadata_entries"], "cache_hits": self.observations["cache_hits"],
                "external_tool_io": "unknown", "stages": self.actual}

    def finish(self, status="UNVERIFIED", reason=None):
        if self.finished:
            return
        from execution_policy import settle_validation
        # 超额结算先落账再抛；不能随后改参数重复结算。
        self.finished = True
        settle_validation(self.root, self.context, self.ticket, self.actual, status=status,
                          root_cause=reason, evidence={"run_ids": self.run_ids, "tool_io": "unknown"},
                          observations=self.observations)


def validation_stages(reads, objects, processes, selected, timeout):
    return {"pre_evidence": {"scanned_files": reads},
            "command": {"processes": processes, "selected_tests": selected,
                        "elapsed_seconds": (timeout or 0) * processes},
            "post_evidence": {"scanned_files": objects}, "cleanup": {}}


@contextmanager
def evidence_budget(root, execution_context, requests, *, extra_reads=0, action="static"):
    """没有命令的验真/审查也按实读取证计费，复用命中不虚扣对象数。"""
    if execution_context is None:
        yield None
        return
    from test_scope import execution_context_data
    context = execution_context_data(root, execution_context)
    estimates = [snapshot_estimate(root, inputs, paths) for inputs, paths in requests]
    reads = sum(item["content_reads"] for item in estimates) + extra_reads
    progress = _ValidationProgress(root, context,
        validation_stages(reads, 0, 0, 0, 0), digest([action, estimates]), action)
    successful = False
    try:
        yield progress
        successful = True
    finally:
        progress.finish("PASS" if successful else "UNVERIFIED")


class _BatchProof:
    """仅当前 run_scope 持有的冻结证明，不接受来自 JSON 的快捷验真标志。"""
    def __init__(self, root, plan, env_id):
        self.root, self.plan_hash = root, digest(plan)
        self.environment = environment_hash()
        self.inputs = sorted({p for r in [*plan["runners"], *plan["runs"]] for p in r["inputs"]})
        self.tree_hash = plan["tree_hash"]
        from project_inventory import fingerprint_token, fingerprint_metadata, _stat_identity
        metadata = fingerprint_metadata() or {}
        paths = snapshot_paths(root, self.inputs, plan.get("validation_files"))["paths"]
        self.tokens = {path.relative_to(root).as_posix(): {"token": fingerprint_token(path, metadata=metadata),
                                                       "observation": _stat_identity(path)} for path in paths}
        self.input_hash = digest([self.tree_hash, env_id, self.environment, plan["runners"]])
        self.reserved_keys = set()

    def check(self, root, plan):
        if root != self.root or digest(plan) != self.plan_hash or environment_hash() != self.environment:
            raise LedgerError("冻结范围/环境已变化，须重新推导")


def run(root, cwd, scope, env_id, command, inputs=(), force=False, timeout=None, ledger_root=None,
        scope_binding=None, execution_context=None, _batch=None, scope_plan=None):
    owned = []
    try:
        return _run(root, cwd, scope, env_id, command, inputs, force, timeout, ledger_root,
                    scope_binding, execution_context, _batch, owned, scope_plan)
    finally:
        for progress in owned:
            progress.finish()


def _run(root, cwd, scope, env_id, command, inputs=(), force=False, timeout=None, ledger_root=None,
         scope_binding=None, execution_context=None, _batch=None, _owned=None, scope_plan=None):
    root = Path(root).resolve()
    if not root.is_dir() or not isinstance(env_id, str) or not env_id.strip():
        raise LedgerError("root 必须存在，env-id 不能为空")
    if timeout is not None and (not math.isfinite(timeout) or timeout <= 0):
        raise LedgerError("timeout 必须为正有限秒数")
    from test_scope import context_identity, execution_context_data
    if scope == "full":
        raise LedgerError("无版本边界 full 已禁用；须使用 version + 冻结验收 manifest + autopilot 测试委派")
    version_identity = None
    if scope == "version":
        from test_scope import validate_scope
        if execution_context is None or not isinstance(scope_plan, dict) or scope_plan.get("kind") != "version":
            raise LedgerError("version 必须绑定冻结 scope_plan 与真实 autopilot 测试委派上下文")
        plan = validate_scope(root, scope_plan, execution_context)
        matches = [item for item in plan["runs"] if item["argv"] == list(command) and item["cwd"] == cwd
                   and item["env_id"] == env_id]
        if len(matches) != 1:
            raise LedgerError("版本命令/cwd/env-id 不唯一对应 manifest 运行项")
        scope_binding = {"plan": plan, "item": matches[0]}
        _batch = _BatchProof(root, plan, env_id)
        version_identity = plan["execution_context"]
        # 真实父预算由 build_unit_test 覆盖 worktree 创建、执行与收尾；这里不重复扣费。
        execution_context = None
    elif scope_plan is not None:
        raise LedgerError("scope_plan 仅用于版本验收；日常任务沿既有 scope_binding")
    execution_context = execution_context_data(root, execution_context)
    identity = version_identity or context_identity(root, execution_context)
    action = "full-regression" if scope == "version" else "related-test"
    if execution_context is not None:
        from execution_policy import require_action
        require_action(execution_context, action)
    if scope == "task" and (identity is None or identity["mode"] != "light"):
        raise LedgerError("scope=task 必须绑定 light execution-context")
    if identity and identity["mode"] == "light":
        from test_scope import resolve_since
        resolve_since(root, identity.get("since"))
    if identity and identity["mode"] == "light" and scope not in ("task", "targeted", "full"):
        raise LedgerError("light execution-context 不能升级为 sprint；full 必须另有显式 full-regression 授权")
    if scope not in ("targeted", "sprint", "version", "task"):
        raise LedgerError(f"未知 scope：{scope}")
    ledger = Path(ledger_root).resolve() if ledger_root else root
    if scope_binding is not None:
        from test_scope import validate_scope
        if isinstance(_batch, _BatchProof):
            _batch.check(root, scope_binding["plan"])
            plan = scope_binding["plan"]
        else:
            plan = validate_scope(root, scope_binding["plan"], execution_context)
            _batch = _BatchProof(root, plan, env_id)
        expected_scope = "version" if plan.get("kind") == "version" else ("task" if identity and identity["mode"] == "light" else "sprint")
        if scope != expected_scope or scope_binding["item"] not in plan["runs"]:
            raise LedgerError("运行项不属于已验证 Sprint 范围")
        if list(command) != scope_binding["item"]["argv"] or cwd != scope_binding["item"]["cwd"]:
            raise LedgerError("命令/cwd 与范围运行项不一致")
        inputs = [*inputs, *scope_binding["item"]["inputs"]]
    cwd = project_path(root, cwd).resolve()
    if not cwd.is_dir() or not cwd.is_relative_to(root):
        raise LedgerError("cwd 必须是 root 内的现有目录")
    if not command or not command[0]:
        raise LedgerError("-- 后必须提供原始命令 argv")
    inputs = normalize_inputs(root, inputs)
    requested_timeout = timeout
    if execution_context is not None:
        if scope == "version" and timeout is None:
            from execution_policy import reserve_budget
            available = reserve_budget(root, execution_context, "elapsed_seconds", 0, action=action)["remaining"]
            timeout = min(3600, available)
        else:
            timeout = timeout or min(30, execution_context["execution_budget"]["elapsed_seconds"])
    context = {"root": str(root), "cwd": str(cwd), "scope": scope, "env_id": env_id,
               "environment_hash": environment_hash(), "command": list(command),
               # full 默认剩余预算随结算变化，不能让同树已通过证据因此失效。
               "inputs": inputs, "timeout": requested_timeout if scope == "version" else timeout}
    if scope == "version":
        context["version_content"] = version_content_identity(scope_binding["plan"])
        context["timeout"] = None
    elif identity is not None:
        context["execution_context"] = identity
    if scope == "version" and ledger != root:
        # 每 build 独占账本；执行 worktree 可重建在不同临时路径。root 保留实际执行路径。
        proc = subprocess.run(["git", "-C", str(root), "rev-parse", "--git-common-dir"],
                              capture_output=True, text=True, timeout=30)
        if proc.returncode:
            raise LedgerError("外置 full 账本要求可识别的 Git worktree")
        context.update(root=str(ledger), cwd=cwd.relative_to(root).as_posix(),
                       repository=str((root / proc.stdout.strip()).resolve()))
    if scope_binding is not None:
        context["selection"] = scope_binding["item"]
    key = digest(context)
    selected_paths = scope_binding["plan"].get("validation_files") if scope_binding else None
    progress = getattr(_batch, "progress", None)
    with lock(ledger, key) as command_lock:
        if execution_context is not None and progress is None:
            estimate = snapshot_estimate(root, inputs, selected_paths)
            with lock(ledger, "write"):
                previous = next((r for r in reversed(load(root, ledger)) if r["kind"] == "run" and r["key"] == key), None)
            cached = (not force and previous and estimate["hash"] and stable_evidence(previous)
                      and (evidence_hash(previous) == estimate["hash"]
                           and previous.get("scope_hash") == (scope_binding["plan"]["scope_hash"] if scope_binding else None)
                           or scope_binding and can_carry(previous, estimate, scope_binding, inputs)))
            selected_count = len(set(scope_binding["item"]["tests"] + scope_binding["item"]["sources"])) if scope_binding else 1
            stages = validation_stages(estimate["content_reads"], 0 if cached else estimate["objects"],
                                       0 if cached else 1, 0 if cached else selected_count, timeout)
            reservation_input = _batch.input_hash if _batch else digest([estimate["hash"], env_id, context["environment_hash"], list(command)])
            progress = _ValidationProgress(root, execution_context, stages, reservation_input, action,
                                           defer_input=not _batch and estimate["hash"] is None)
            _owned.append(progress)
        observer = progress.observe("pre_evidence") if progress else None
        before = tree_snapshot(root, inputs, paths=selected_paths, observer=observer)
        if scope_binding is not None:
            # 锁后全内容核验，绝不把等待前的证明当成当前事实。
            _batch.check(root, scope_binding["plan"])
            scoped = before if inputs == _batch.inputs else tree_snapshot(root, _batch.inputs, paths=selected_paths, observer=observer)
            if scoped["hash"] != _batch.tree_hash or scoped["tokens"] != _batch.tokens:
                raise LedgerError("TREE_CHANGED：等待命令锁期间源文件/输入已变化，须重新推导")
        execution_input = _batch.input_hash if _batch else digest([before["hash"], env_id, context["environment_hash"], list(command)])
        if progress:
            progress.flush()
            progress.bind(execution_input)
        with lock(ledger, "write"):
            rows = load(root, ledger)
            previous = next((r for r in reversed(rows) if r["kind"] == "run" and r["key"] == key), None)
            blocked = next((r for r in reversed(rows) if r.get("kind") == "run" and r.get("key") == key
                            and r.get("before_hash") == before["hash"]
                            and r.get("tool_fingerprint") == tool_fingerprint(command, cwd)
                            and r.get("exit_code") not in (0, None)
                            and r.get("failure_kind") in {"ENV_UNAVAILABLE", "RUNNER_USAGE_ERROR", "NO_TESTS_COLLECTED"}), None)
            if blocked:
                return dict(result(blocked), retry_blocked=True,
                            retry_reason="相同输入与环境的工具失败已记录；先修复输入或更新真实环境身份"), 2
            if (not force and previous and stable_evidence(previous)
                    and evidence_hash(previous) == before["hash"]
                    and previous.get("scope_hash") == (scope_binding["plan"]["scope_hash"] if scope_binding else None)):
                previous["reuse_count"] += 1
                previous["last_reused_at"] = time.time()
                save(root, rows, ledger)
                if progress:
                    progress.flush()
                    if progress in _owned:
                        progress.finish("PASS")
                return dict(result(previous, reused=True), io=before["io"]), 0
            if not force and previous and scope_binding and can_carry(previous, before, scope_binding, inputs):
                carried = {"schema": SCHEMA, "kind": "run", "key": key, "context": context,
                           **context, "root": str(root), "ledger_root": str(ledger),
                           "run_id": uuid.uuid4().hex, "status": "CARRIED", "exit_code": None,
                           "before_hash": before["hash"], "after_hash": None,
                           "assessment_hash": before["hash"], "files": before["files"],
                           "vcs_mode": before["vcs_mode"], "scope_binding": scope_binding,
                           "scope_hash": scope_binding["plan"]["scope_hash"],
                           "source_run_id": previous.get("source_run_id", previous["run_id"]),
                           "parent_run_id": previous["run_id"],
                           "source_tree_hash": previous.get("source_tree_hash", previous["after_hash"]),
                           "started_at": time.time(), "duration_seconds": 0, "reuse_count": 0,
                           "delta": snapshot_delta(previous["files"], before["files"])}
                if version_identity is not None:
                    carried["execution_context"] = version_identity
                rows.append(carried)
                save(root, rows, ledger)
                if progress:
                    progress.flush()
                    if progress in _owned:
                        progress.finish("PASS")
                return dict(result(carried), io=before["io"]), 0
            if progress:
                if timeout is None or timeout <= 0:
                    raise LedgerError("BUDGET_EXCEEDED：没有可用于实际测试执行的时间预算")
                # 锁等待后若原预计复用的运行已失效，不得挪用零命令预留执行。
                reserved = progress.ticket["stages"]["command"]
                if (progress.actual["command"].get("processes", 0) >= reserved["processes"]
                        or progress not in _owned and _batch and key not in _batch.reserved_keys):
                    raise LedgerError("等待命令锁期间证据变化，当前票据没有剩余进程预留，须重新推导")
                progress.flush()
            row = {"schema": SCHEMA, "kind": "run", "key": key,
                   "context": context, **context, "root": str(root), "ledger_root": str(ledger),
                   "run_id": uuid.uuid4().hex,
                   "status": "RUNNING", "exit_code": None, "before_hash": before["hash"],
                   "after_hash": None, "files": before["files"], "vcs_mode": before["vcs_mode"],
                   "duration_seconds": 0, "started_at": time.time(), "reuse_count": 0,
                   "gitlinks": before["gitlinks"], "tool_fingerprint": tool_fingerprint(command, cwd)}
            if scope_binding is not None:
                row.update(scope_binding=scope_binding, scope_hash=scope_binding["plan"]["scope_hash"])
            if version_identity is not None:
                row["execution_context"] = version_identity
            if scope == "version" and execution_context is not None:
                row["execution_timeout"] = timeout
            # 先存 RUNNING，kill/崩溃后不可能回退复用更早的 PASS。
            rows.append(row)
            save(root, rows, ledger)
        started = time.monotonic()
        error = None
        process = None
        streams = {}
        try:
            output_dir = Path(ensure_runtime_dir(ledger)) / "test-output"
            output_dir.mkdir(parents=True, exist_ok=True)
            row["output"] = {name: str(output_dir / (row["run_id"] + "." + name)) for name in ("stdout", "stderr")}
            for name, path in row["output"].items():
                streams[name] = Path(path).open("w+b")
        except OSError as exc:
            for stream in streams.values():
                stream.close()
            row.update(status="ERROR", evidence_status="UNVERIFIED", command_status="NOT_EXECUTED",
                       process_started=False, error=str(exc), finished_at=time.time())
            persist_run(root, ledger, row)
            raise
        closed = set()

        def relay_output():
            if process is None:
                return
            for name, fd in (("stdout", 1), ("stderr", 2)):
                pipe = getattr(process, name)
                if pipe is None or name in closed:
                    continue
                # 有界搬运使持续刷屏也能响应 deadline；原输出同时持久化与实时转发。
                for _ in range(64):
                    try:
                        chunk = os.read(pipe.fileno(), 65536)
                    except BlockingIOError:
                        break
                    if not chunk:
                        closed.add(name)
                        break
                    streams[name].write(chunk)
                    pending = memoryview(chunk)
                    while pending:
                        pending = pending[os.write(fd, pending):]

        try:
            # 包装进程被 SIGKILL 后，仍活着的测试子进程继续持同键锁。
            process = subprocess.Popen(command, cwd=cwd, start_new_session=True,
                                       pass_fds=(command_lock,), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            for name in streams:
                os.set_blocking(getattr(process, name).fileno(), False)
            while True:
                relay_output()
                exit_code = process.poll()
                if exit_code is not None:
                    break
                remaining = timeout - (time.monotonic() - started) if timeout is not None else .1
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(command, timeout)
                select.select([getattr(process, name) for name in streams if name not in closed], [], [], min(.1, remaining))
        except subprocess.TimeoutExpired:
            error, exit_code = "测试命令超时", 124
        except KeyboardInterrupt:
            error, exit_code = "测试命令被中断", 130
        except OSError as exc:
            error, exit_code = str(exc), 127
        finally:
            try:
                if process is not None and process.poll() is None:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait()
                relay_output()
            finally:
                if process is not None:
                    for name in streams:
                        pipe = getattr(process, name)
                        if pipe is not None:
                            pipe.close()
                for stream in streams.values():
                    stream.flush()
                    os.fsync(stream.fileno())
                streams["stderr"].seek(0)
                stderr_text = streams["stderr"].read().decode("utf-8", errors="replace")
                for stream in streams.values():
                    stream.close()
        missing_module = bool(exit_code and missing_python_runner(command, stderr_text))
        if missing_module:
            error = "Python 测试运行器模块不可用"
        duration = time.monotonic() - started
        if not error and exit_code in (126, 127):
            error = "测试工具无法启动（退出码 126/127），未核验"
        pytest_failure = None
        is_pytest = Path(command[0]).name in ("pytest", "py.test") or python_runner_module(command) == "pytest"
        if not error and is_pytest and exit_code in (2, 3, 4, 5):
            pytest_failure, error = {
                2: ("COLLECTION_OR_INTERRUPTION", "pytest 收集错误或中断；不能仅凭退出码认定工具缺失，保留原始输出"),
                3: ("TOOL_ERROR", "pytest 报告内部错误，未核验"),
                4: ("RUNNER_USAGE_ERROR", "pytest 参数/配置错误，未核验"),
                5: ("NO_TESTS_COLLECTED", "pytest 未收集到测试，未核验"),
            }[exit_code]
        if (not error and python_runner_module(command) == "unittest"
                and re.search(r"\bRan 0 tests\b", stderr_text)):
            pytest_failure, error = "NO_TESTS_COLLECTED", "unittest 未执行任何测试，未核验"
        # 命令事实先落账；后取证/预算错误永远不能遗留 RUNNING 或吞掉输出/退出码。
        row.update(status="ERROR", evidence_status="UNVERIFIED", command_status="ERROR" if error else "FAIL" if exit_code else "PASS",
                   exit_code=exit_code, process_started=process is not None,
                   duration_seconds=duration, finished_at=time.time())
        persist_run(root, ledger, row)
        policy_notice = None
        after = None
        try:
            if progress:
                selected = (scope_binding["item"]["tests"] + scope_binding["item"]["sources"]) if scope_binding else [key]
                progress.command(row, selected)
            after = tree_snapshot(root, inputs, paths=selected_paths,
                                  observer=progress.observe("post_evidence") if progress else None)
            after_hash = after["hash"]
            if progress:
                progress.flush()
        except (OSError, ValueError) as exc:
            after_hash = after["hash"] if after else None
            error = f"测试后取证未核验：{exc}"
            policy_notice = {"status": getattr(exc, "status", "UNVERIFIED"), "reason": str(exc)} if progress else None
        changed = after is not None and snapshot_changed(before, after)
        status = ("ERROR" if error else "FAIL" if exit_code else "TREE_CHANGED" if changed else "PASS")
        row["evidence_status"] = "UNVERIFIED" if error or changed else "VERIFIED"
        row["after_gitlinks"] = after["gitlinks"] if after else None
        row["io"] = {"pre_evidence": before["io"], "post_evidence": after["io"] if after else None,
                     "tool_io": "unknown"}
        row.update(status=status, exit_code=exit_code, after_hash=after_hash,
                   duration_seconds=duration, finished_at=time.time())
        if error:
            row["error"] = error
        row["failure_kind"] = ("TIMEOUT" if exit_code == 124 and error else "ENV_UNAVAILABLE" if exit_code in (126, 127) or missing_module
                               else pytest_failure if pytest_failure else "TOOL_ERROR" if error else "TREE_CHANGED" if status == "TREE_CHANGED"
                               else "TEST_FAILURE" if status == "FAIL" else None)
        persist_run(root, ledger, row)
        try:
            if progress in _owned:
                outcome = row["failure_kind"] if row["failure_kind"] in ("ENV_UNAVAILABLE", "TOOL_ERROR") else (
                    "UNVERIFIED" if status in ("ERROR", "TREE_CHANGED") else status)
                progress.finish(outcome, row["failure_kind"])
        except ValueError as exc:
            policy_notice = {"status": getattr(exc, "status", "UNVERIFIED"), "reason": str(exc)}
        if policy_notice:
            row.update(status="ERROR", evidence_status="UNVERIFIED", policy_notice=policy_notice)
            persist_run(root, ledger, row)
        code = exit_code if exit_code >= 0 else 128 - exit_code
        out = result(row)
        if policy_notice:
            out["policy_notice"] = policy_notice
        return out, 2 if policy_notice else code or (0 if status == "PASS" else 1)


def accepted_run(rows, root, run_id, env_id, identity=None):
    row = next((r for r in rows if r["kind"] == "run" and r["run_id"] == run_id), None)
    scope = "task" if identity and identity["mode"] == "light" else "sprint"
    if (not row or not stable_evidence(row) or row["scope"] != scope or row["root"] != str(root)
            or row.get("execution_context") != identity
            or row["env_id"] != env_id or row["environment_hash"] != environment_hash()):
        raise LedgerError("需要同 root/环境的实际 sprint PASS 作为验收证据")
    # 历史 PASS 不能绕过同 key 后续失败、未完成或中断的运行。
    latest = next(r for r in reversed(rows) if r["kind"] == "run" and r["key"] == row["key"])
    if not stable_evidence(latest):
        raise LedgerError(f"同 key 最新测试状态为 {latest['status']}，需要最新可信 sprint PASS")
    if latest["run_id"] != run_id:
        raise LedgerError("验收后已有新 sprint PASS，须审查并用 record-review 显式登记最新 run_id")
    return row


def report_hash(root, report, observer=None):
    path = project_path(root, report)
    if not path.is_file() or path.stat().st_size == 0:
        raise LedgerError("审查报告必须存在且非空；测试 PASS 不等于审查已完成")
    cache = _FingerprintCache(root)
    def read(target):
        if observer:
            observer({"content_reads": 1, "metadata_entries": 1, "cache_hits": 0}, {str(target)})
    try:
        record = cache.read(path, read)
        if observer and not record["read"]:
            observer({"content_reads": 0, "metadata_entries": 1, "cache_hits": 1}, set())
        return record["hash"]
    finally:
        cache.save()


def validate_review_report(root, report, scope_hash, identity=None, observer=None):
    """报告单次实读同时解析与计算指纹；测试 PASS 永远不是 code-review。"""
    path = project_path(root, report)
    from project_inventory import fingerprint_file
    content = None
    def reader(target):
        nonlocal content
        if observer:
            observer({"content_reads": 1, "metadata_entries": 1, "cache_hits": 0}, {str(target)})
        content = target.read_bytes()
        if not content.strip():
            raise LedgerError("审查报告必须存在且非空；测试 PASS 不等于审查已完成")
        mode = target.stat().st_mode
        return digest({"sha256": hashlib.sha256(content).hexdigest(), "mode": stat.S_IMODE(mode),
                       "link": os.readlink(target) if target.is_symlink() else None})
    cache = _FingerprintCache(root)
    record = fingerprint_file(path, reader=reader, metadata=cache.metadata)
    if content is None:
        raise LedgerError("审查报告必须存在且非空")
    cache.files[str(path)] = record
    cache.changed = True
    cache.save()
    hashed = record["hash"]
    if identity is None or identity["mode"] != "light":
        return hashed
    try:
        review = json.loads(content.decode("utf-8"))
    except (OSError, ValueError) as exc:
        raise LedgerError(f"light 审查必须是独立 code-review JSON：{exc}") from exc
    if (not isinstance(review, dict) or review.get("schema") != 1 or review.get("kind") != "code-review"
            or review.get("status") != "PASS" or review.get("scope_hash") != scope_hash
            or review.get("execution_context") != identity
            or not isinstance(review.get("reviewer"), str) or not review["reviewer"].strip()):
        raise LedgerError("审查身份/范围/reviewer/结论不完整；测试 PASS 不能替代真实审查")
    checks, findings = review.get("checks"), review.get("findings")
    if not isinstance(checks, list) or not checks or not isinstance(findings, list):
        raise LedgerError("审查必须包含 checks 与 findings 数组")
    reviewed = False
    for check in checks:
        if not isinstance(check, dict) or check.get("kind") not in ("code-review", "static", "compile"):
            raise LedgerError("审查检查项 kind 无效")
        status = check.get("status")
        if status == "NA":
            if not isinstance(check.get("reason"), str) or not check["reason"].strip():
                raise LedgerError("NA 检查项必须说明不适用原因")
            continue
        evidence = check.get("evidence")
        if (status != "PASS" or not isinstance(evidence, list) or not evidence
                or any(not isinstance(item, str) or not item.strip() for item in evidence)):
            raise LedgerError("审查检查项失败/未核验或缺少真实证据，不能登记通过")
        reviewed |= check["kind"] == "code-review"
    if not reviewed:
        raise LedgerError("缺少带证据的 code-review PASS；测试或编译 PASS 不等于审查完成")
    for finding in findings:
        if (not isinstance(finding, dict) or not all(isinstance(finding.get(key), str) and finding[key].strip()
                for key in ("id", "severity", "status"))):
            raise LedgerError("审查 finding 缺少 id/severity/status")
        evidence = finding.get("evidence")
        references = [evidence] if isinstance(evidence, str) else evidence
        if (not isinstance(references, list) or not references
                or any(not isinstance(item, str) or not item.strip() for item in references)):
            raise LedgerError("审查 finding 必须提供真实证据引用")
        severity, status = finding["severity"].lower(), finding["status"].lower()
        if (severity not in ("critical", "important", "minor", "suggestion")
                or status not in ("closed", "resolved", "fixed", "accepted")):
            raise LedgerError("审查 finding 尚未闭环")
        kind = finding.get("kind")
        if kind is not None and kind not in ("error", "improvement"):
            raise LedgerError("审查 finding.kind 必须是 error 或 improvement")
        if status == "accepted":
            if severity not in ("minor", "suggestion") or kind != "improvement":
                raise LedgerError("仅明确的 Minor/Suggestion 纯优化可接受；代码错误必须修复闭环")
            if not isinstance(finding.get("reason"), str) or not finding["reason"].strip():
                raise LedgerError("接受纯优化 finding 必须记录明确原因")
    return hashed


def normalize_run_ids(run_ids, allow_empty=False):
    # Python API 保留旧单字符串调用；CLI 与新基线使用非空、无重复列表。
    if isinstance(run_ids, str):
        run_ids = [run_ids]
    if (not isinstance(run_ids, list) or (not run_ids and not allow_empty)
            or any(not isinstance(value, str) or not value.strip() for value in run_ids)
            or len(set(run_ids)) != len(run_ids)):
        raise LedgerError("run_ids 必须是非空且无重复的 run_id 字符串列表")
    return list(run_ids)


def review_run_ids(row):
    # 老账本只有 run_id；新账本的 run_id 是最后一套的兼容字段，不能替代全集。
    run_ids = row.get("run_ids", [row.get("run_id")])
    if not isinstance(run_ids, list):
        raise LedgerError("审查 run_ids 字段损坏")
    run_ids = normalize_run_ids(run_ids, allow_empty=bool(row.get("scope_hash")))
    if row.get("run_id") != (run_ids[-1] if run_ids else None):
        raise LedgerError("审查 run_id 与 run_ids 引用不一致")
    return run_ids


def record_review(root, name, run_id, env_id, report, inputs=(), scope_file=None, scope_hash=None,
                  execution_context=None):
    root = Path(root).resolve()
    if execution_context is not None:
        from test_scope import execution_context_data
        from execution_policy import require_action
        current_context = execution_context_data(root, execution_context)
        review_action = "review" if "review" in current_context["allowed_actions"] else "full-cvl"
        require_action(current_context, review_action)
    if not scope_file or not scope_hash:
        raise LedgerError("新验收必须同时提供 scope-file 与 scope-hash；手工 sprint PASS 不能替代范围证据")
    run_ids = normalize_run_ids(run_id, allow_empty=True)
    from test_scope import context_identity
    identity = context_identity(root, execution_context)
    verification = verify_scope(root, scope_file, scope_hash, run_ids, env_id, execution_context=execution_context)
    with lock(root, "write"):
        rows = load(root)
        sources = [accepted_run(rows, root, value, env_id, identity) for value in run_ids]
    inputs = normalize_inputs(root, [*(path for source in sources for path in source["inputs"]), *inputs])
    validation_files = verification.get("validation_files")
    requests = [(inputs, validation_files), *((list(values), validation_files) for values in {tuple(s["inputs"]) for s in sources})]
    with evidence_budget(root, execution_context, requests, extra_reads=1) as progress:
        observer = progress.observe("pre_evidence") if progress else None
        snapshot = tree_snapshot(root, inputs, paths=validation_files, observer=observer)
        report_digest = validate_review_report(root, report, scope_hash, identity, observer)
        tested_snapshots = {tuple(inputs): snapshot}
        for source in sources:
            input_key = tuple(source["inputs"])
            if input_key not in tested_snapshots:
                tested_snapshots[input_key] = tree_snapshot(root, source["inputs"], paths=validation_files, observer=observer)
            tested = tested_snapshots[input_key]
            if (tested["hash"] != evidence_hash(source)
                    or any(snapshot["files"].get(path) != value for path, value in tested["files"].items())):
                raise LedgerError(f"sprint PASS {source['run_id']} 已过期，须对当前树重新验收")
    row = {"schema": SCHEMA, "kind": "review", "root": str(root), "name": name,
           "review_id": uuid.uuid4().hex, "run_id": run_ids[-1] if run_ids else None, "run_ids": run_ids,
           "recorded_at": time.time(), "env_id": env_id,
           "environment_hash": environment_hash(), "inputs": inputs,
           "report": project_path(root, report).relative_to(root).as_posix(),
           "report_hash": report_digest, **snapshot}
    if identity is not None:
        row["execution_context"] = identity
    if validation_files is not None:
        row["validation_files"] = validation_files
    row.update(scope_hash=scope_hash, scope_file=project_path(root, scope_file).relative_to(root).as_posix(),
               test_status=verification["status"], minor=verification["minor"],
               unmapped=verification["unmapped"], unrunnable=verification["unrunnable"],
               evidence=verification["evidence"])
    # 整树/报告 IO 在写锁之外；入账时逐套重新核对是否被后续运行取代。
    with lock(root, "write"):
        rows = load(root)
        for value in run_ids:
            accepted_run(rows, root, value, env_id, identity)
        rows.append(row)
        save(root, rows)
    return result(row)


def review_delta(root, name, env_id, execution_context=None):
    root = Path(root).resolve()
    from test_scope import context_identity
    identity = context_identity(root, execution_context)
    with lock(root, "write"):
        rows = load(root)
        baseline = next((r for r in reversed(rows) if r["kind"] == "review" and r["name"] == name
                         and r.get("execution_context") == identity), None)
        if not baseline:
            raise LedgerError("没有可信审查基线，须全量审查")
        run_ids = review_run_ids(baseline)
        for value in run_ids:
            accepted_run(rows, root, value, env_id, identity)
    from project_inventory import fingerprint_token
    cache = _FingerprintCache(root)
    report_path = project_path(root, baseline["report"])
    token = fingerprint_token(report_path, metadata=cache.metadata)
    report_reads = int(token is None or cache.files.get(str(report_path), {}).get("token") != token)
    with evidence_budget(root, execution_context, [(baseline["inputs"], baseline.get("validation_files"))],
                         extra_reads=report_reads) as progress:
        observer = progress.observe("pre_evidence") if progress else None
        if (baseline["env_id"] != env_id or baseline["environment_hash"] != environment_hash()
                or baseline["report_hash"] != report_hash(root, baseline["report"], observer)):
            raise LedgerError("审查环境/报告已变化，须全量审查")
        current = tree_snapshot(root, baseline["inputs"], paths=baseline.get("validation_files"), observer=observer)
    old, new = baseline["files"], current["files"]
    from project_inventory import classify_changes
    classification = classify_changes(snapshot_delta(old, new), baseline["inputs"])
    return {"kind": "review-delta", "change_categories": classification, "name": name, "review_id": baseline["review_id"],
            "execution_context": identity, "scope_hash": baseline.get("scope_hash"),
            "run_id": baseline["run_id"], "run_ids": run_ids,
            "baseline_hash": baseline["hash"], "current_hash": current["hash"],
            "code_changed": baseline["hash"] != current["hash"],
            "added": sorted(new.keys() - old.keys()), "removed": sorted(old.keys() - new.keys()),
            "changed": sorted(k for k in new.keys() & old.keys() if new[k] != old[k]),
            "inputs": baseline["inputs"], "report": baseline["report"],
            "legacy": not bool(baseline.get("scope_hash")),
            "requires_verification": not bool(baseline.get("scope_hash")),
            "note": ("历史无范围绑定基线，仅供差异参考；须新 scope 验证后重新 record-review"
                     if not baseline.get("scope_hash") else "差异是审查输入，不代表当前树已通过测试或审查")}


def read_scope(root, scope_file, scope_hash=None, execution_context=None):
    from test_scope import validate_scope
    try:
        path = project_path(root, scope_file)
        scope = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise LedgerError(f"单测范围文件不可读或非 JSON：{exc}") from exc
    scope = validate_scope(root, scope, execution_context)
    if scope_hash is not None and scope_hash != scope["scope_hash"]:
        raise LedgerError("指定 scope_hash 与当前范围不一致")
    return scope


def tool_fingerprint(command, cwd):
    """runner 可执行文件及 shebang 解释器的存在/内容观测；缺失也是可比较的值。"""
    def observe(value):
        if not value:
            return None
        path = Path(value)
        found = (cwd / path if "/" in value and not path.is_absolute() else path) if "/" in value else (
            shutil.which(value, path=os.environ.get("PATH")) or None)
        if not found:
            return {"path": None, "hash": None}
        found = Path(found)
        try:
            content = found.read_bytes()
        except OSError:
            return {"path": str(found), "hash": None}
        return {"path": str(found.resolve()), "hash": hashlib.sha256(content).hexdigest(), "mode": stat.S_IMODE(found.stat().st_mode),
                "interpreter": observe(content.split(b"\n", 1)[0][2:].strip().split(b" ")[0].decode("utf-8", "replace"))
                if content.startswith(b"#!") else None}
    return digest(observe(command[0]))


def historical_failures(rows, plan):
    """历史失败独立展示，不把已修复的旧失败混入当前覆盖结论。"""
    identity = plan.get("execution_context")
    return [{"run_id": row["run_id"], "status": row["status"], "failure_kind": row.get("failure_kind"),
             "scope_hash": row.get("scope_hash"), "exit_code": row.get("exit_code")}
            for row in rows if row.get("kind") == "run" and row.get("status") in {"FAIL", "ERROR", "TREE_CHANGED"}
            and row.get("scope_binding", {}).get("plan", {}).get("execution_context") == identity
            and row.get("scope_binding", {}).get("plan", {}).get("since") == plan.get("since")]


def set_status(scope, sources):
    statuses = {r["status"] for r in sources}
    if "FAIL" in statuses:
        return "FAIL", 1
    if statuses - {"PASS", "CARRIED"}:
        return "UNVERIFIED", 2
    if scope["unrunnable"] or scope["unmapped"]:
        return "UNVERIFIED", 2
    if not sources:
        applicable = scope.get("applicability", {})
        if applicable.get("status") == "NOT_APPLICABLE" and applicable.get("reason") and applicable.get("paths"):
            return "NOT_APPLICABLE", 0
        return "UNVERIFIED", 2
    return ("CARRIED" if "CARRIED" in statuses else "PASS"), 0


def verify_scope(root, scope_file, scope_hash, run_ids, env_id, ledger_root=None, execution_context=None):
    root = Path(root).resolve()
    if not root.is_dir() or not isinstance(env_id, str) or not env_id.strip():
        raise LedgerError("root 必须存在，env-id 不能为空")
    if not isinstance(scope_hash, str) or not scope_hash:
        raise LedgerError("verify 必须提供当前 scope_hash")
    scope = read_scope(root, scope_file, scope_hash, execution_context)
    identity = scope.get("execution_context")
    if scope["unrunnable"]:
        raise LedgerError("已映射测试缺少运行器，Important 未核验，不能验收")
    ids = normalize_run_ids(run_ids, allow_empty=True)
    ledger = Path(ledger_root).resolve() if ledger_root else root
    with lock(ledger, "write"):
        rows = load(root, ledger)
        sources = [accepted_run(rows, root, run_id, env_id, identity) for run_id in ids]
    expected = sorted(digest(item) for item in scope["runs"])
    actual, snapshots = [], {}
    requests = [(list(inputs), scope.get("validation_files")) for inputs in {tuple(row["inputs"]) for row in sources}]
    with evidence_budget(root, execution_context, requests) as progress:
        for row in sources:
            binding = row.get("scope_binding")
            if not binding or row.get("scope_hash") != scope_hash or binding["plan"] != scope:
                raise LedgerError("验收 run_id 未绑定当前确定性 Sprint 范围")
            input_key = tuple(row["inputs"])
            if input_key not in snapshots:
                snapshots[input_key] = tree_snapshot(root, row["inputs"], paths=scope.get("validation_files"),
                    observer=progress.observe("pre_evidence") if progress else None)
            if snapshots[input_key]["hash"] != evidence_hash(row):
                raise LedgerError("验收证据对应的树/测试输入已变化，须先 run-scope 补跑或 carry-forward")
            actual.append(digest(binding["item"]))
    if sorted(actual) != expected:
        raise LedgerError("run_ids 必须精确覆盖当前范围的全部运行项，不能漏套或重复")
    status, code = set_status(scope, sources)
    if code:
        raise LedgerError("测试证据存在覆盖缺口或未核验项，不能作为完成证据")
    return {"applicability": scope.get("applicability"), "historical_failures": historical_failures(rows, scope), "kind": "task-verification" if identity and identity["mode"] == "light" else "sprint-verification",
            "execution_context": identity, "status": status, "scope_hash": scope_hash,
            "validation_files": scope.get("validation_files"),
            "run_ids": ids, "unmapped": scope["unmapped"], "unrunnable": scope["unrunnable"],
            "minor": bool(scope["unmapped"]),
            "evidence": [{"run_id": r["run_id"], "status": r["status"],
                          "source_run_id": r.get("source_run_id"),
                          "source_tree_hash": r.get("source_tree_hash", r["after_hash"])} for r in sources]}


def run_scope(root, scope_file, env_id, inputs=(), ledger_root=None, force=False, timeout=None,
              execution_context=None):
    owned = []
    try:
        return _run_scope(root, scope_file, env_id, inputs, ledger_root, force, timeout, execution_context, owned)
    finally:
        for progress in owned:
            progress.finish()


def _run_scope(root, scope_file, env_id, inputs=(), ledger_root=None, force=False, timeout=None,
               execution_context=None, _owned=None):
    """重推范围后逐项执行。旧 PASS 跨树只可转成带来源的 CARRIED。"""
    root = Path(root).resolve()
    if not root.is_dir() or not isinstance(env_id, str) or not env_id.strip():
        raise LedgerError("root 必须存在，env-id 不能为空")
    if timeout is not None and (not math.isfinite(timeout) or timeout <= 0):
        raise LedgerError("timeout 必须为正有限秒数")
    inputs = normalize_inputs(root, inputs)
    scope = read_scope(root, scope_file, execution_context=execution_context)
    identity = scope.get("execution_context")
    scope_kind = "task" if identity and identity["mode"] == "light" else "sprint"
    context = None
    proof = _BatchProof(root, scope, env_id)
    if execution_context is not None:
        from test_scope import execution_context_data
        from execution_policy import require_action
        context = execution_context_data(root, execution_context)
        require_action(context, "related-test")
        count = len(scope["runs"])
        timeout = timeout or min(30, context["execution_budget"]["elapsed_seconds"] / max(count, 1))
        # 同树证据不消耗新进程/测试额度；锁后失效而无预留时明确终止，不能挪用其它运行项预算。
        ledger = Path(ledger_root).resolve() if ledger_root else root
        with lock(ledger, "write"):
            previous_rows = load(root, ledger)
        selected, pending = set(), set()
        estimates = {}
        pre_reads, post_reads = 0, 0
        for item in scope["runs"]:
            item_inputs = normalize_inputs(root, [*inputs, *item["inputs"]])
            item_context = {"root": str(root), "cwd": str((root / item["cwd"]).resolve()), "scope": scope_kind,
                            "env_id": env_id, "environment_hash": proof.environment, "command": item["argv"],
                            "inputs": item_inputs, "timeout": timeout, "selection": item, "execution_context": identity}
            key = digest(item_context)
            previous = next((r for r in reversed(previous_rows) if r["kind"] == "run" and r["key"] == key), None)
            input_key = tuple(item_inputs)
            if input_key not in estimates:
                estimates[input_key] = snapshot_estimate(root, item_inputs, scope.get("validation_files"))
            estimate = estimates[input_key]
            # 每个运行项都锁后核验；未知平台可能每次实读，预算按真实操作上限预留。
            pre_reads += estimate["content_reads"]
            reusable = (not force and previous and stable_evidence(previous) and estimate["hash"]
                        and (evidence_hash(previous) == estimate["hash"] and previous.get("scope_hash") == scope["scope_hash"]
                             or can_carry(previous, estimate, {"plan": scope, "item": item}, item_inputs)))
            if not reusable:
                pending.add(key)
                selected.update(item["tests"] + item["sources"])
                post_reads += estimate["objects"]
        # 范围联合输入的锁后检查也计入闭环上限，不先逐资源扣费。
        if scope["runs"]:
            pre_reads += snapshot_estimate(root, proof.inputs, scope.get("validation_files"))["content_reads"] * len(scope["runs"])
        proof.progress = _ValidationProgress(root, context,
            validation_stages(pre_reads, post_reads, len(pending), len(selected), timeout),
            proof.input_hash, "related-test")
        _owned.append(proof.progress)
        proof.reserved_keys = pending
    runs = []
    interruption = None
    for item in scope["runs"]:
        try:
            out, code = run(root, item["cwd"], scope_kind, env_id, item["argv"],
                            [*inputs, *item["inputs"]], force, timeout, ledger_root,
                            scope_binding={"plan": scope, "item": item}, execution_context=context, _batch=proof)
        except (OSError, ValueError) as exc:
            interruption = {"status": getattr(exc, "status", "UNVERIFIED"), "reason": str(exc)}
            break
        runs.append(dict(out, exit=code))
        if out.get("policy_notice"):
            interruption = out["policy_notice"]
            break
        if out["status"] == "TREE_CHANGED" or out.get("failure_kind") in {"ENV_UNAVAILABLE", "TOOL_ERROR", "RUNNER_USAGE_ERROR"}:
            break
    status, code = set_status(scope, runs)
    if interruption or len(runs) != len(scope["runs"]):
        status, code = "UNVERIFIED", 2
    if context is not None:
        try:
            failures = [r.get("failure_kind") for r in runs if r.get("failure_kind") in ("ENV_UNAVAILABLE", "TOOL_ERROR")]
            outcome = failures[0] if failures else status if status in ("PASS", "FAIL", "UNVERIFIED") else "PASS"
            proof.progress.finish(outcome, interruption["reason"] if interruption else (failures[0] if failures else None))
        except ValueError as exc:
            interruption = {"status": getattr(exc, "status", "UNVERIFIED"), "reason": str(exc)}
            status, code = "UNVERIFIED", 2
            # 收尾失败不能留下本票据的新 PASS；历史复用来源保持原真实结论。
            executed = set(proof.progress.run_ids)
            with lock(ledger, "write"):
                rows = load(root, ledger)
                for row in rows:
                    if row.get("run_id") in executed and row["kind"] == "run":
                        row.update(status="ERROR", evidence_status="UNVERIFIED", policy_notice=interruption)
                save(root, rows, ledger)
            for row in runs:
                if row["run_id"] in executed:
                    row.update(status="ERROR", evidence_status="UNVERIFIED", policy_notice=interruption)
    ledger = Path(ledger_root).resolve() if ledger_root else root
    with lock(ledger, "write"):
        history = historical_failures(load(root, ledger), scope)
    return {"kind": scope_kind + "-run-set", "execution_context": identity,
            "applicability": scope.get("applicability"), "historical_failures": history,
            "status": status, "run_ids": [r["run_id"] for r in runs],
            "runs": runs, "interruption": interruption, "unrunnable": scope["unrunnable"], "scope_hash": scope["scope_hash"],
            "validation_cost": proof.progress.summary() if context is not None else None,
            "unmapped": scope["unmapped"], "minor": bool(scope["unmapped"])}, code


def self_check():
    with tempfile.TemporaryDirectory(prefix="aidp-test-ledger-selfcheck-") as temp:
        root = Path(temp).resolve()
        (root / "app.py").write_text("value=1\n", encoding="utf-8")
        command = [sys.executable, "-c", "pass"]
        first, code = run(root, ".", "sprint", "self-check", command)
        hit, hit_code = run(root, ".", "sprint", "self-check", command)
        (root / "app.py").write_text("value=2\n", encoding="utf-8")
        changed, changed_code = run(root, ".", "sprint", "self-check", command)
        failure, failed_code = run(root, ".", "sprint", "self-check", [sys.executable, "-c", "raise SystemExit(7)"])
        checks = [code == 0 and not first["reused"], hit_code == 0 and hit["reused"],
                  changed_code == 0 and not changed["reused"], failed_code == 7 and failure["status"] == "FAIL"]
        return {"ok": all(checks), "checks": len(checks), "positive": 2, "negative": 2}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--self-check", action="store_true")
    sub = parser.add_subparsers(dest="action")
    for action in ("run", "run-scope", "record-review", "review-delta", "verify"):
        child = sub.add_parser(action)
        child.add_argument("--root", default=".")
        child.add_argument("--execution-context", help="冻结入口上下文 JSON；task 证据必须传入")
        child.add_argument("--env-id", required=True, help="测试环境/部署/外部状态标识，变化后更新")
        if action == "run-scope":
            child.add_argument("--scope-file", required=True, help="test_scope.py 输出的 JSON")
            child.add_argument("--input", action="append", default=[])
            child.add_argument("--ledger-root", help="外置账本根目录；full 使用每 build 专属缓存，勿混入主仓 Sprint 账本")
            child.add_argument("--force", action="store_true")
            child.add_argument("--timeout", type=float)
        elif action == "run":
            child.add_argument("--cwd", default=".", help="相对于 root 的命令目录")
            child.add_argument("--scope", required=True, choices=("targeted", "sprint", "full", "task"))
            child.add_argument("--force", action="store_true")
            child.add_argument("--timeout", type=float)
            child.add_argument("--input", action="append", default=[])
            child.add_argument("--ledger-root", help="外置账本根目录；full 使用每 build 专属缓存，勿混入主仓 Sprint 账本")
            child.add_argument("--scope-file", help="可选：将此命令绑定到确定性范围中的一个运行项")
            child.add_argument("--scope-hash")
            child.add_argument("command", nargs=argparse.REMAINDER)
        else:
            if action != "verify":
                child.add_argument("--name", required=True)
            if action in ("record-review", "verify"):
                child.add_argument("--run-id", action="append", default=[],
                                   help="全部 Sprint 运行项的证据 ID；无运行项时可不传")
                child.add_argument("--scope-file", required=True)
                child.add_argument("--scope-hash", required=True)
            if action == "verify":
                child.add_argument("--ledger-root")
            if action == "record-review":
                child.add_argument("--report", required=True)
                child.add_argument("--input", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        if args.self_check:
            out = self_check()
            code = 0 if out["ok"] else 1
        else:
            if not args.action:
                parser.error("需要 run/run-scope/record-review/review-delta 或 --self-check")
            root = Path(args.root).resolve()
            if not root.is_dir() or not args.env_id.strip():
                raise LedgerError("root 必须存在，env-id 不能为空")
            if args.action == "run":
                if args.timeout is not None and (not math.isfinite(args.timeout) or args.timeout <= 0):
                    raise LedgerError("timeout 必须为正有限秒数")
                command = args.command[1:] if args.command[:1] == ["--"] else args.command
                binding = None
                if args.scope_file or args.scope_hash:
                    if not args.scope_file or not args.scope_hash:
                        raise LedgerError("绑定 run 时 scope-file/scope-hash 须同时提供")
                    plan = read_scope(root, args.scope_file, args.scope_hash, args.execution_context)
                    matches = [item for item in plan["runs"] if item["argv"] == command and item["cwd"] == args.cwd]
                    if len(matches) != 1:
                        raise LedgerError("命令/cwd 不精确对应范围中的唯一运行项")
                    binding = {"plan": plan, "item": matches[0]}
                out, code = run(root, args.cwd, args.scope, args.env_id, command,
                                args.input, args.force, args.timeout, args.ledger_root, binding, args.execution_context)
            elif args.action == "run-scope":
                out, code = run_scope(root, args.scope_file, args.env_id, args.input,
                                      args.ledger_root, args.force, args.timeout, args.execution_context)
            elif args.action == "verify":
                out = verify_scope(root, args.scope_file, args.scope_hash, args.run_id, args.env_id, args.ledger_root, args.execution_context)
                code = 0
            elif args.action == "record-review":
                out = record_review(root, args.name, args.run_id, args.env_id, args.report, args.input,
                                    args.scope_file, args.scope_hash, args.execution_context)
                code = 0
            else:
                out = review_delta(root, args.name, args.env_id, args.execution_context)
                code = 0
    except (OSError, ValueError) as exc:
        out, code = {"kind": "error", "status": getattr(exc, "status", "ERROR"), "error": str(exc), "reused": False}, 2
        if getattr(exc, "details", None):
            out["details"] = exc.details
    # 子命令可能没有输出末尾换行，确保结果 JSON 总是独占最后一行。
    print("\n" + json.dumps(out, ensure_ascii=True, sort_keys=True), flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
