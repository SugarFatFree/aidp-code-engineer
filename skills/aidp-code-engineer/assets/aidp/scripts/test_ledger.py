#!/usr/bin/env python3
"""执行选中测试、复用同树 PASS、追溯跨树证据并登记审查基线。

run --root . --cwd . --scope targeted|sprint|full --env-id ENV [--input PATH] [--ledger-root DIR] -- argv...
run-scope --root . --scope-file PATH --env-id ENV [--input PATH] [--force] [--timeout SECONDS]
verify --root . --scope-file PATH --scope-hash HASH --env-id ENV [--run-id ID ...]
record-review --root . --name NAME --scope-file PATH --scope-hash HASH --env-id ENV --report PATH [--run-id ID ...]
review-delta --root . --name NAME --env-id ENV

run-scope 执行前重推 Git+write_set 范围；run_ids 必须精确覆盖全部运行项才能 verify。
命名测试逐文件记账。前后 Python 导入闭包均证明变化不相交时沿用来源 PASS，登记 CARRIED、
source_run_id/source_tree_hash/assessment_hash/delta，绝不冒充当前整树已实跑 PASS。
命名映射和兄弟目录都不是独立证明。未知依赖/配置/文件增删使已有 Sprint 选择保守补跑；
related/其它语言跨树不猜测独立性。runner 的 env_id 和 inputs 与整体 env-id 一起绑定复用键。
EMPTY 表示无对应测试，PARTIAL 表示 Minor 未覆盖，均不伪造 PASS/run_id；可登记审查。
FAIL 为实际测试失败；工具缺失/超时/树变化为 UNVERIFIED（单 run 为 ERROR/TREE_CHANGED）。

full 只供 /sprint-aiauto-test：run 的 ledger_root 使用每 build 专属缓存目录，不能混用主仓
Sprint 账本。外置 full 账本按仓库身份/相对 cwd/内容树匹配，可跨临时 worktree 路径复用。
默认忽略根 docs/、memory/ 及 CLAUDE.md、AGENTS.md、README.md；真实测试输入用 --input
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
import signal
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


def tree_snapshot(root, inputs=()):
    """返回可供 review diff 使用的文件内容清单和整体指纹。"""
    mode = detect_mode(root)
    if mode != "git" and os.path.lexists(root / ".git"):
        raise LedgerError("存在 .git 但无法读取工作树；拒绝降级复用")
    paths = set()
    directory_inputs = {}
    runtime = Path(ensure_runtime_dir(root)).resolve()

    def excluded(path):
        rel = path.relative_to(root)
        return ".git" in rel.parts or path == runtime or runtime in path.parents

    def default_excluded(path):
        rel = path.relative_to(root)
        return (rel.parts[0] in ("docs", "memory") or excluded(path)
                or (len(rel.parts) == 1 and rel.name in ROOT_STATE_FILES))

    def walk(base, fallback=False):
        # 不吞掉读取错误；无法观察的输入必须 fail closed。
        def onerror(exc):
            raise exc
        for parent, dirs, files in os.walk(base, onerror=onerror, followlinks=False):
            parent = Path(parent)
            kept = []
            for name in dirs:
                p = parent / name
                if excluded(p) or (fallback and name in SKIP_DIR_NAMES):
                    continue
                if p.is_symlink():
                    raise LedgerError(f"目录符号链接无法完整指纹：{p}")
                kept.append(name)
            dirs[:] = kept
            for name in files:
                p = parent / name
                if not excluded(p):
                    paths.add(p)

    if mode == "git":
        try:
            proc = subprocess.run(["git", "-C", str(root), "ls-files", "--cached", "--others",
                                   "--exclude-standard", "-z"], capture_output=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise LedgerError(f"Git 文件清单读取失败：{exc}") from exc
        if proc.returncode:
            raise LedgerError("Git 文件清单读取失败，不能使用旧测试结果")
        for name in proc.stdout.split(b"\0"):
            if not name:
                continue
            p = project_path(root, os.fsdecode(name))
            if default_excluded(p):
                continue
            if p.is_dir() and not p.is_symlink():
                # gitlink/submodule：保守扫描工作树，不只取索引中的 commit。
                walk(p)
            elif p.exists() or p.is_symlink():
                paths.add(p)
    else:
        for p in root.iterdir():
            if default_excluded(p) or p.name in SKIP_DIR_NAMES:
                continue
            if p.is_dir() and not p.is_symlink():
                walk(p, fallback=True)
            else:
                paths.add(p)

    for rel in normalize_inputs(root, inputs):
        p = root / rel
        if excluded(p):
            raise LedgerError("运行账本及 .git 不能作为显式输入")
        if p.is_dir() and not p.is_symlink():
            directory_inputs[rel + "/"] = digest("directory")
            walk(p)
        else:
            paths.add(p)
    files = {p.relative_to(root).as_posix(): file_hash(p) for p in sorted(paths)}
    files.update(directory_inputs)
    return {"files": files, "vcs_mode": mode,
            "hash": digest({"files": files, "vcs_mode": mode})}


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
        rows = []
        for line in lines:
            row = json.loads(line)
            if not isinstance(row, dict) or row.get("schema") != SCHEMA:
                raise LedgerError("账本记录结构/版本不正确")
            unsigned = {key: value for key, value in row.items() if key != "checksum"}
            external_full = (ledger is not None and Path(ledger).resolve() != root and row.get("scope") == "full"
                             and row.get("ledger_root") == str(Path(ledger).resolve()))
            if row.get("checksum") != digest(unsigned) or (row.get("root") != str(root) and not external_full):
                raise LedgerError("账本校验和或项目 root 不匹配")
            if row.get("kind") == "run":
                if (not isinstance(row.get("context"), dict)
                        or row.get("key") != digest(row["context"])
                        or row.get("status") not in ("RUNNING", "PASS", "CARRIED", "FAIL", "ERROR", "TREE_CHANGED")
                        or not isinstance(row.get("run_id"), str)
                        or type(row.get("reuse_count")) is not int or row["reuse_count"] < 0):
                    raise LedgerError("测试记录字段损坏")
                if row["before_hash"] != digest({"files": row["files"], "vcs_mode": row["vcs_mode"]}):
                    raise LedgerError("测试快照损坏")
                if row["status"] == "PASS" and not stable_pass(row):
                    raise LedgerError("PASS 记录证据不完整")
                binding = row.get("scope_binding")
                if binding:
                    plan = binding["plan"]
                    if (plan["scope_hash"] != digest({k: v for k, v in plan.items() if k != "scope_hash"})
                            or row.get("scope_hash") != plan["scope_hash"] or binding["item"] not in plan["runs"]
                            or row["context"].get("selection") != binding["item"]):
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
            for row in rows:
                unsigned = {key: value for key, value in row.items() if key != "checksum"}
                sealed = dict(unsigned, checksum=digest(unsigned))
                stream.write(json.dumps(sealed, ensure_ascii=True, sort_keys=True) + "\n")
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


def can_carry(previous, current, binding, inputs):
    """执行与历史加载共用同一闭包判据；旧命名映射不构成独立证据。"""
    from test_scope import DEPENDENCY_POLICY, dependency_impact, within
    old_binding = previous.get("scope_binding")
    if not stable_evidence(previous) or not old_binding or not binding or previous["inputs"] != list(inputs):
        return False
    old_plan, plan = old_binding["plan"], binding["plan"]
    if any(old_plan[k] != plan[k] for k in ("since", "modules")):
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
            if key not in ("files", "checksum", "context", "scope_binding")}


def run(root, cwd, scope, env_id, command, inputs=(), force=False, timeout=None, ledger_root=None,
        scope_binding=None):
    root = Path(root).resolve()
    if not root.is_dir() or not isinstance(env_id, str) or not env_id.strip():
        raise LedgerError("root 必须存在，env-id 不能为空")
    if timeout is not None and (not math.isfinite(timeout) or timeout <= 0):
        raise LedgerError("timeout 必须为正有限秒数")
    if scope not in ("targeted", "sprint", "full"):
        raise LedgerError(f"未知 scope：{scope}")
    ledger = Path(ledger_root).resolve() if ledger_root else root
    if scope_binding is not None:
        from test_scope import validate_scope
        plan = validate_scope(root, scope_binding["plan"])
        if scope != "sprint" or scope_binding["item"] not in plan["runs"]:
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
    context = {"root": str(root), "cwd": str(cwd), "scope": scope, "env_id": env_id,
               "environment_hash": environment_hash(), "command": list(command),
               "inputs": inputs, "timeout": timeout}
    if scope == "full" and ledger != root:
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
    with lock(ledger, key) as command_lock:
        if scope_binding is not None:
            # 等待同命令锁期间工作树可能改变，不能只信任加锁前的范围。
            validate_scope(root, scope_binding["plan"])
        before = tree_snapshot(root, inputs)
        with lock(ledger, "write"):
            rows = load(root, ledger)
            previous = next((r for r in reversed(rows) if r["kind"] == "run" and r["key"] == key), None)
            if (not force and previous and stable_evidence(previous)
                    and evidence_hash(previous) == before["hash"]
                    and previous.get("scope_hash") == (scope_binding["plan"]["scope_hash"] if scope_binding else None)):
                previous["reuse_count"] += 1
                previous["last_reused_at"] = time.time()
                save(root, rows, ledger)
                return result(previous, reused=True), 0
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
                rows.append(carried)
                save(root, rows, ledger)
                return result(carried), 0
            row = {"schema": SCHEMA, "kind": "run", "key": key,
                   "context": context, **context, "root": str(root), "ledger_root": str(ledger),
                   "run_id": uuid.uuid4().hex,
                   "status": "RUNNING", "exit_code": None, "before_hash": before["hash"],
                   "after_hash": None, "files": before["files"], "vcs_mode": before["vcs_mode"],
                   "duration_seconds": 0, "started_at": time.time(), "reuse_count": 0}
            if scope_binding is not None:
                row.update(scope_binding=scope_binding, scope_hash=scope_binding["plan"]["scope_hash"])
            # 先存 RUNNING，kill/崩溃后不可能回退复用更早的 PASS。
            rows.append(row)
            save(root, rows, ledger)
        started = time.monotonic()
        error = None
        process = None
        try:
            if scope_binding and Path(command[0]).name.startswith(("python", "pypy")) and "-m" in command:
                module_index = command.index("-m")
                if "-c" not in command[:module_index] and module_index + 1 < len(command):
                    probe = subprocess.run([*command[:module_index], "-B", "-c",
                                            "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec(sys.argv[1]) else 127)",
                                            command[module_index + 1]], cwd=cwd, capture_output=True,
                                           timeout=min(timeout or 10, 10))
                    if probe.returncode:
                        raise FileNotFoundError(f"Python 测试运行器模块不可用：{command[module_index + 1]}")
            # 包装进程被 SIGKILL 后，仍活着的测试子进程继续持同键锁。
            process = subprocess.Popen(command, cwd=cwd, start_new_session=True,
                                       pass_fds=(command_lock,))
            exit_code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            error, exit_code = "测试命令超时", 124
        except KeyboardInterrupt:
            error, exit_code = "测试命令被中断", 130
        except OSError as exc:
            error, exit_code = str(exc), 127
        finally:
            if process is not None and process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        duration = time.monotonic() - started
        try:
            after_hash = tree_snapshot(root, inputs)["hash"]
        except (OSError, ValueError) as exc:
            after_hash = None
            error = f"测试后指纹读取失败：{exc}"
        if not error and exit_code in (126, 127):
            error = "测试工具无法启动（退出码 126/127），未核验"
        if not error and exit_code in (2, 3, 4, 5) and any(Path(a).name in ("pytest", "py.test") for a in command):
            error = "pytest 中断/配置错误/未收集到测试，未核验"
        status = ("ERROR" if error else "FAIL" if exit_code else
                  "TREE_CHANGED" if before["hash"] != after_hash else "PASS")
        row.update(status=status, exit_code=exit_code, after_hash=after_hash,
                   duration_seconds=duration, finished_at=time.time())
        if error:
            row["error"] = error
        with lock(ledger, "write"):
            rows = load(root, ledger)
            index = next((i for i, r in enumerate(rows) if r.get("run_id") == row["run_id"]
                          and r["kind"] == "run"), None)
            if index is None:
                raise LedgerError("执行中的账本记录丢失，拒绝出具 PASS")
            rows[index] = row
            save(root, rows, ledger)
        code = exit_code if exit_code >= 0 else 128 - exit_code
        return result(row), code or (0 if status == "PASS" else 1)


def accepted_run(rows, root, run_id, env_id):
    row = next((r for r in rows if r["kind"] == "run" and r["run_id"] == run_id), None)
    if (not row or not stable_evidence(row) or row["scope"] != "sprint" or row["root"] != str(root)
            or row["env_id"] != env_id or row["environment_hash"] != environment_hash()):
        raise LedgerError("需要同 root/环境的实际 sprint PASS 作为验收证据")
    # 历史 PASS 不能绕过同 key 后续失败、未完成或中断的运行。
    latest = next(r for r in reversed(rows) if r["kind"] == "run" and r["key"] == row["key"])
    if not stable_evidence(latest):
        raise LedgerError(f"同 key 最新测试状态为 {latest['status']}，需要最新可信 sprint PASS")
    if latest["run_id"] != run_id:
        raise LedgerError("验收后已有新 sprint PASS，须审查并用 record-review 显式登记最新 run_id")
    return row


def report_hash(root, report):
    path = project_path(root, report)
    if not path.is_file() or not path.read_bytes().strip():
        raise LedgerError("审查报告必须存在且非空；测试 PASS 不等于审查已完成")
    return file_hash(path)


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


def record_review(root, name, run_id, env_id, report, inputs=(), scope_file=None, scope_hash=None):
    root = Path(root).resolve()
    if not scope_file or not scope_hash:
        raise LedgerError("新验收必须同时提供 scope-file 与 scope-hash；手工 sprint PASS 不能替代范围证据")
    run_ids = normalize_run_ids(run_id, allow_empty=True)
    verification = verify_scope(root, scope_file, scope_hash, run_ids, env_id)
    with lock(root, "write"):
        rows = load(root)
        sources = [accepted_run(rows, root, value, env_id) for value in run_ids]
    inputs = normalize_inputs(root, [*(path for source in sources for path in source["inputs"]), *inputs])
    snapshot = tree_snapshot(root, inputs)
    report_digest = report_hash(root, report)
    for source in sources:
        tested = tree_snapshot(root, source["inputs"])
        if (tested["hash"] != evidence_hash(source)
                or any(snapshot["files"].get(path) != value for path, value in tested["files"].items())):
            raise LedgerError(f"sprint PASS {source['run_id']} 已过期，须对当前树重新验收")
    row = {"schema": SCHEMA, "kind": "review", "root": str(root), "name": name,
           "review_id": uuid.uuid4().hex, "run_id": run_ids[-1] if run_ids else None, "run_ids": run_ids,
           "recorded_at": time.time(), "env_id": env_id,
           "environment_hash": environment_hash(), "inputs": inputs,
           "report": project_path(root, report).relative_to(root).as_posix(),
           "report_hash": report_digest, **snapshot}
    row.update(scope_hash=scope_hash, scope_file=project_path(root, scope_file).relative_to(root).as_posix(),
               test_status=verification["status"], minor=verification["minor"],
               unmapped=verification["unmapped"], unrunnable=verification["unrunnable"],
               evidence=verification["evidence"])
    # 整树/报告 IO 在写锁之外；入账时逐套重新核对是否被后续运行取代。
    with lock(root, "write"):
        rows = load(root)
        for value in run_ids:
            accepted_run(rows, root, value, env_id)
        rows.append(row)
        save(root, rows)
    return result(row)


def review_delta(root, name, env_id):
    with lock(root, "write"):
        rows = load(root)
        baseline = next((r for r in reversed(rows) if r["kind"] == "review" and r["name"] == name), None)
        if not baseline:
            raise LedgerError("没有可信审查基线，须全量审查")
        run_ids = review_run_ids(baseline)
        for value in run_ids:
            accepted_run(rows, root, value, env_id)
    if (baseline["env_id"] != env_id or baseline["environment_hash"] != environment_hash()
            or baseline["report_hash"] != report_hash(root, baseline["report"])):
        raise LedgerError("审查环境/报告已变化，须全量审查")
    current = tree_snapshot(root, baseline["inputs"])
    old, new = baseline["files"], current["files"]
    return {"kind": "review-delta", "name": name, "review_id": baseline["review_id"],
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


def read_scope(root, scope_file, scope_hash=None):
    from test_scope import validate_scope
    try:
        path = project_path(root, scope_file)
        scope = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise LedgerError(f"单测范围文件不可读或非 JSON：{exc}") from exc
    scope = validate_scope(root, scope)
    if scope_hash is not None and scope_hash != scope["scope_hash"]:
        raise LedgerError("指定 scope_hash 与当前范围不一致")
    return scope


def set_status(scope, sources):
    statuses = {r["status"] for r in sources}
    if "FAIL" in statuses:
        return "FAIL", 1
    if statuses - {"PASS", "CARRIED"}:
        return "UNVERIFIED", 2
    if scope["unrunnable"]:
        return "UNVERIFIED", 2
    if not sources:
        return "EMPTY", 0
    if scope["unmapped"]:
        return "PARTIAL", 0
    return ("CARRIED" if "CARRIED" in statuses else "PASS"), 0


def verify_scope(root, scope_file, scope_hash, run_ids, env_id, ledger_root=None):
    root = Path(root).resolve()
    if not root.is_dir() or not isinstance(env_id, str) or not env_id.strip():
        raise LedgerError("root 必须存在，env-id 不能为空")
    if not isinstance(scope_hash, str) or not scope_hash:
        raise LedgerError("verify 必须提供当前 scope_hash")
    scope = read_scope(root, scope_file, scope_hash)
    if scope["unrunnable"]:
        raise LedgerError("已映射测试缺少运行器，Important 未核验，不能验收")
    ids = normalize_run_ids(run_ids, allow_empty=True)
    ledger = Path(ledger_root).resolve() if ledger_root else root
    with lock(ledger, "write"):
        rows = load(root, ledger)
        sources = [accepted_run(rows, root, run_id, env_id) for run_id in ids]
    expected = sorted(digest(item) for item in scope["runs"])
    actual = []
    for row in sources:
        binding = row.get("scope_binding")
        if not binding or row.get("scope_hash") != scope_hash or binding["plan"] != scope:
            raise LedgerError("验收 run_id 未绑定当前确定性 Sprint 范围")
        if tree_snapshot(root, row["inputs"])["hash"] != evidence_hash(row):
            raise LedgerError("验收证据对应的树/测试输入已变化，须先 run-scope 补跑或 carry-forward")
        actual.append(digest(binding["item"]))
    if sorted(actual) != expected:
        raise LedgerError("run_ids 必须精确覆盖当前范围的全部运行项，不能漏套或重复")
    status, _ = set_status(scope, sources)
    return {"kind": "sprint-verification", "status": status, "scope_hash": scope_hash,
            "run_ids": ids, "unmapped": scope["unmapped"], "unrunnable": scope["unrunnable"],
            "minor": bool(scope["unmapped"]),
            "evidence": [{"run_id": r["run_id"], "status": r["status"],
                          "source_run_id": r.get("source_run_id"),
                          "source_tree_hash": r.get("source_tree_hash", r["after_hash"])} for r in sources]}


def run_scope(root, scope_file, env_id, inputs=(), ledger_root=None, force=False, timeout=None):
    """重推范围后逐项执行。旧 PASS 跨树只可转成带来源的 CARRIED。"""
    root = Path(root).resolve()
    if not root.is_dir() or not isinstance(env_id, str) or not env_id.strip():
        raise LedgerError("root 必须存在，env-id 不能为空")
    if timeout is not None and (not math.isfinite(timeout) or timeout <= 0):
        raise LedgerError("timeout 必须为正有限秒数")
    inputs = normalize_inputs(root, inputs)
    scope = read_scope(root, scope_file)
    runs = []
    for item in scope["runs"]:
        out, code = run(root, item["cwd"], "sprint", env_id, item["argv"],
                        [*inputs, *item["inputs"]], force, timeout, ledger_root,
                        scope_binding={"plan": scope, "item": item})
        runs.append(dict(out, exit=code))
        if out["status"] == "TREE_CHANGED":
            break
    status, code = set_status(scope, runs)
    if len(runs) != len(scope["runs"]):
        status, code = "UNVERIFIED", 2
    return {"kind": "sprint-run-set", "status": status, "run_ids": [r["run_id"] for r in runs],
            "runs": runs, "unrunnable": scope["unrunnable"], "scope_hash": scope["scope_hash"],
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
        child.add_argument("--env-id", required=True, help="测试环境/部署/外部状态标识，变化后更新")
        if action == "run-scope":
            child.add_argument("--scope-file", required=True, help="test_scope.py 输出的 JSON")
            child.add_argument("--input", action="append", default=[])
            child.add_argument("--ledger-root", help="外置账本根目录；full 使用每 build 专属缓存，勿混入主仓 Sprint 账本")
            child.add_argument("--force", action="store_true")
            child.add_argument("--timeout", type=float)
        elif action == "run":
            child.add_argument("--cwd", default=".", help="相对于 root 的命令目录")
            child.add_argument("--scope", required=True, choices=("targeted", "sprint", "full"))
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
                    plan = read_scope(root, args.scope_file, args.scope_hash)
                    matches = [item for item in plan["runs"] if item["argv"] == command and item["cwd"] == args.cwd]
                    if len(matches) != 1:
                        raise LedgerError("命令/cwd 不精确对应范围中的唯一运行项")
                    binding = {"plan": plan, "item": matches[0]}
                out, code = run(root, args.cwd, args.scope, args.env_id, command,
                                args.input, args.force, args.timeout, args.ledger_root, binding)
            elif args.action == "run-scope":
                out, code = run_scope(root, args.scope_file, args.env_id, args.input,
                                      args.ledger_root, args.force, args.timeout)
            elif args.action == "verify":
                out = verify_scope(root, args.scope_file, args.scope_hash, args.run_id, args.env_id, args.ledger_root)
                code = 0
            elif args.action == "record-review":
                out = record_review(root, args.name, args.run_id, args.env_id, args.report, args.input,
                                    args.scope_file, args.scope_hash)
                code = 0
            else:
                out = review_delta(root, args.name, args.env_id)
                code = 0
    except (OSError, ValueError) as exc:
        out, code = {"kind": "error", "status": "ERROR", "error": str(exc), "reused": False}, 2
    # 子命令可能没有输出末尾换行，确保结果 JSON 总是独占最后一行。
    print("\n" + json.dumps(out, ensure_ascii=True, sort_keys=True), flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
