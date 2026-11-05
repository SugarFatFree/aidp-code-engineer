#!/usr/bin/env python3
"""执行测试并按内容树/命令/范围/环境复用 PASS；显式登记审查基线。

run --root . --cwd . --scope targeted|full --env-id ENV [--input PATH] -- argv...
record-review --root . --name NAME --run-id ID [--run-id ID ...] --env-id ENV --report PATH [--input PATH]
review-delta --root . --name NAME --env-id ENV

命令通过 argv 原样执行，stdout/stderr 保留，最后一行输出 JSON。环境标识必填；
外部服务/数据库等不可自动指纹的状态变化由调用方更新 env-id 或使用 --force。
开发定向与汇合/部署前全量由 scope 区分，不能互相冒充。无 TTL/复用次数上限。
默认忽略根 docs/、memory/ 及 CLAUDE.md、AGENTS.md、README.md；其中真实
测试输入须用 --input 显式声明（可重复，相对 root，支持目录）。其它 Markdown
照常纳入。审查继承测试输入，并可额外声明文档/契约审查输入。
环境指纹仅排除 SHLVL、_、PWD、OLDPWD 四项 shell 噪声；cwd 单独匹配。
Git 枚举已跟踪与未跟踪非忽略文件；无 Git 使用目录遍历及既有生成目录排除约定。
内容 SHA256 不依赖 HEAD/mtime；文件权限、符号链接及其文件目标也进入指纹。

账本为本地证据而非防恶意伪造的签名。损坏/不完整证据拒绝复用，返回 2；
子进程失败沿用退出码，超时 124，启动失败 127；exit 0 但树变化返回 1。
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


def load(root):
    path = Path(ledger_path(root))
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
            if row.get("checksum") != digest(unsigned) or row.get("root") != str(root):
                raise LedgerError("账本校验和或项目 root 不匹配")
            if row.get("kind") == "run":
                if (not isinstance(row.get("context"), dict)
                        or row.get("key") != digest(row["context"])
                        or row.get("status") not in ("RUNNING", "PASS", "FAIL", "ERROR", "TREE_CHANGED")
                        or not isinstance(row.get("run_id"), str)
                        or type(row.get("reuse_count")) is not int or row["reuse_count"] < 0):
                    raise LedgerError("测试记录字段损坏")
                if row["before_hash"] != digest({"files": row["files"], "vcs_mode": row["vcs_mode"]}):
                    raise LedgerError("测试快照损坏")
                if row["status"] == "PASS" and not stable_pass(row):
                    raise LedgerError("PASS 记录证据不完整")
            elif row.get("kind") == "review":
                if (not row.get("name") or not row.get("run_id") or not row.get("report_hash")
                        or row.get("hash") != digest({"files": row["files"], "vcs_mode": row["vcs_mode"]})):
                    raise LedgerError("审查快照损坏")
                review_run_ids(row)
            else:
                raise LedgerError("未知账本记录类型")
            rows.append(row)
        return rows
    except (ValueError, KeyError, TypeError, UnicodeError) as exc:
        raise LedgerError(f"账本损坏，拒绝复用：{exc}") from exc


def save(root, rows):
    """调用方持短写锁；写临时文件 + fsync + replace，不追加半条 JSON。"""
    path = Path(ledger_path(root))
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


def result(row, reused=False):
    # 文件清单只在账本存储，CLI 回包保持小而可读。
    return {key: value for key, value in dict(row, reused=reused).items()
            if key not in ("files", "checksum", "context")}


def run(root, cwd, scope, env_id, command, inputs=(), force=False, timeout=None):
    cwd = project_path(root, cwd).resolve()
    if not cwd.is_dir() or not cwd.is_relative_to(root):
        raise LedgerError("cwd 必须是 root 内的现有目录")
    if not command or not command[0]:
        raise LedgerError("-- 后必须提供原始命令 argv")
    inputs = normalize_inputs(root, inputs)
    context = {"root": str(root), "cwd": str(cwd), "scope": scope, "env_id": env_id,
               "environment_hash": environment_hash(), "command": list(command),
               "inputs": inputs, "timeout": timeout}
    key = digest(context)
    with lock(root, key) as command_lock:
        before = tree_snapshot(root, inputs)
        with lock(root, "write"):
            rows = load(root)
            previous = next((r for r in reversed(rows) if r["kind"] == "run" and r["key"] == key), None)
            if (not force and previous and stable_pass(previous)
                    and previous["after_hash"] == before["hash"]):
                previous["reuse_count"] += 1
                previous["last_reused_at"] = time.time()
                save(root, rows)
                return result(previous, reused=True), 0
            row = {"schema": SCHEMA, "kind": "run", "root": str(root), "key": key,
                   "context": context, **context, "run_id": uuid.uuid4().hex,
                   "status": "RUNNING", "exit_code": None, "before_hash": before["hash"],
                   "after_hash": None, "files": before["files"], "vcs_mode": before["vcs_mode"],
                   "duration_seconds": 0, "started_at": time.time(), "reuse_count": 0}
            # 先存 RUNNING，kill/崩溃后不可能回退复用更早的 PASS。
            rows.append(row)
            save(root, rows)
        started = time.monotonic()
        error = None
        process = None
        try:
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
        status = ("ERROR" if error else "FAIL" if exit_code else
                  "TREE_CHANGED" if before["hash"] != after_hash else "PASS")
        row.update(status=status, exit_code=exit_code, after_hash=after_hash,
                   duration_seconds=duration, finished_at=time.time())
        if error:
            row["error"] = error
        with lock(root, "write"):
            rows = load(root)
            index = next((i for i, r in enumerate(rows) if r.get("run_id") == row["run_id"]
                          and r["kind"] == "run"), None)
            if index is None:
                raise LedgerError("执行中的账本记录丢失，拒绝出具 PASS")
            rows[index] = row
            save(root, rows)
        code = exit_code if exit_code >= 0 else 128 - exit_code
        return result(row), code or (0 if status == "PASS" else 1)


def accepted_run(rows, root, run_id, env_id):
    row = next((r for r in rows if r["kind"] == "run" and r["run_id"] == run_id), None)
    if (not row or not stable_pass(row) or row["scope"] != "full" or row["root"] != str(root)
            or row["env_id"] != env_id or row["environment_hash"] != environment_hash()):
        raise LedgerError("需要同 root/环境的实际 full PASS 作为验收证据")
    # 历史 PASS 不能绕过同 key 后续失败、未完成或中断的运行。
    latest = next(r for r in reversed(rows) if r["kind"] == "run" and r["key"] == row["key"])
    if not stable_pass(latest):
        raise LedgerError(f"同 key 最新测试状态为 {latest['status']}，需要最新可信 full PASS")
    if latest["run_id"] != run_id:
        raise LedgerError("验收后已有新 full PASS，须审查并用 record-review 显式登记最新 run_id")
    return row


def report_hash(root, report):
    path = project_path(root, report)
    if not path.is_file() or not path.read_bytes().strip():
        raise LedgerError("审查报告必须存在且非空；测试 PASS 不等于审查已完成")
    return file_hash(path)


def normalize_run_ids(run_ids):
    # Python API 保留旧单字符串调用；CLI 与新基线使用非空、无重复列表。
    if isinstance(run_ids, str):
        run_ids = [run_ids]
    if (not isinstance(run_ids, list) or not run_ids
            or any(not isinstance(value, str) or not value.strip() for value in run_ids)
            or len(set(run_ids)) != len(run_ids)):
        raise LedgerError("run_ids 必须是非空且无重复的 run_id 字符串列表")
    return list(run_ids)


def review_run_ids(row):
    # 老账本只有 run_id；新账本的 run_id 是最后一套的兼容字段，不能替代全集。
    run_ids = row.get("run_ids", [row.get("run_id")])
    if not isinstance(run_ids, list):
        raise LedgerError("审查 run_ids 字段损坏")
    run_ids = normalize_run_ids(run_ids)
    if row.get("run_id") != run_ids[-1]:
        raise LedgerError("审查 run_id 与 run_ids 引用不一致")
    return run_ids


def record_review(root, name, run_id, env_id, report, inputs=()):
    run_ids = normalize_run_ids(run_id)
    with lock(root, "write"):
        rows = load(root)
        sources = [accepted_run(rows, root, value, env_id) for value in run_ids]
    inputs = normalize_inputs(root, [*(path for source in sources for path in source["inputs"]), *inputs])
    snapshot = tree_snapshot(root, inputs)
    report_digest = report_hash(root, report)
    for source in sources:
        tested = tree_snapshot(root, source["inputs"])
        if (tested["hash"] != source["after_hash"]
                or any(snapshot["files"].get(path) != value for path, value in tested["files"].items())):
            raise LedgerError(f"full PASS {source['run_id']} 已过期，须对当前树重新验收")
    row = {"schema": SCHEMA, "kind": "review", "root": str(root), "name": name,
           "review_id": uuid.uuid4().hex, "run_id": run_ids[-1], "run_ids": run_ids,
           "recorded_at": time.time(), "env_id": env_id,
           "environment_hash": environment_hash(), "inputs": inputs,
           "report": project_path(root, report).relative_to(root).as_posix(),
           "report_hash": report_digest, **snapshot}
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
            "note": "差异是审查输入，不代表当前树已通过测试或审查"}


def self_check():
    with tempfile.TemporaryDirectory(prefix="aidp-test-ledger-selfcheck-") as temp:
        root = Path(temp).resolve()
        (root / "app.py").write_text("value=1\n", encoding="utf-8")
        command = [sys.executable, "-c", "pass"]
        first, code = run(root, ".", "full", "self-check", command)
        hit, hit_code = run(root, ".", "full", "self-check", command)
        (root / "app.py").write_text("value=2\n", encoding="utf-8")
        changed, changed_code = run(root, ".", "full", "self-check", command)
        failure, failed_code = run(root, ".", "full", "self-check", [sys.executable, "-c", "raise SystemExit(7)"])
        checks = [code == 0 and not first["reused"], hit_code == 0 and hit["reused"],
                  changed_code == 0 and not changed["reused"], failed_code == 7 and failure["status"] == "FAIL"]
        return {"ok": all(checks), "checks": len(checks), "positive": 2, "negative": 2}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--self-check", action="store_true")
    sub = parser.add_subparsers(dest="action")
    for action in ("run", "record-review", "review-delta"):
        child = sub.add_parser(action)
        child.add_argument("--root", default=".")
        child.add_argument("--env-id", required=True, help="测试环境/部署/外部状态标识，变化后更新")
        if action == "run":
            child.add_argument("--cwd", default=".", help="相对于 root 的命令目录")
            child.add_argument("--scope", required=True, choices=("targeted", "full"))
            child.add_argument("--force", action="store_true")
            child.add_argument("--timeout", type=float)
            child.add_argument("--input", action="append", default=[])
            child.add_argument("command", nargs=argparse.REMAINDER)
        else:
            child.add_argument("--name", required=True)
            if action == "record-review":
                child.add_argument("--run-id", required=True, action="append",
                                   help="每套必需 full PASS 的 run_id；多套时重复传入")
                child.add_argument("--report", required=True)
                child.add_argument("--input", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        if args.self_check:
            out = self_check()
            code = 0 if out["ok"] else 1
        else:
            if not args.action:
                parser.error("需要 run/record-review/review-delta 或 --self-check")
            root = Path(args.root).resolve()
            if not root.is_dir() or not args.env_id.strip():
                raise LedgerError("root 必须存在，env-id 不能为空")
            if args.action == "run":
                if args.timeout is not None and (not math.isfinite(args.timeout) or args.timeout <= 0):
                    raise LedgerError("timeout 必须为正有限秒数")
                command = args.command[1:] if args.command[:1] == ["--"] else args.command
                out, code = run(root, args.cwd, args.scope, args.env_id, command,
                                args.input, args.force, args.timeout)
            elif args.action == "record-review":
                out = record_review(root, args.name, args.run_id, args.env_id, args.report, args.input)
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
