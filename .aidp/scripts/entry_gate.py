#!/usr/bin/env python3
"""code/** 写前入口门：显式任务上下文 + branch-policy，两项均必需。

不扫描其他 active context，不豁免 formal/tick。上下文由 AIDP_EXECUTION_CONTEXT
或 bind 创建的任务标记选择；有 AIDP_SESSION_ID 时只读取同会话标记。
check 是只读；bind 在入口已完成后写绑定。默认新鲜期 24h，可用
AIDP_ENTRY_GATE_MAX_AGE_HOURS 配置（<=0 不限）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import sys
import time
from pathlib import Path

_SCRIPTS = str(Path(__file__).resolve().parent)
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)
from aidp_runtime import runtime_text
from aidp_paths import runtime_dir

GUARDED_PREFIXES = ("code/",)
DEFAULT_MAX_AGE_HOURS = 24.0
MARKER_NAME = "branch-policy-read.json"
TASK_MARKER_NAME = "entry-task.json"


def _runtime_dir(root):
    return Path(runtime_dir(str(root)))


def _max_age_seconds():
    try:
        hours = float(os.environ.get("AIDP_ENTRY_GATE_MAX_AGE_HOURS", DEFAULT_MAX_AGE_HOURS))
    except ValueError:
        hours = DEFAULT_MAX_AGE_HOURS
    return hours * 3600 if hours > 0 else 0


def relative_target(root, target):
    if target in (None, ""):
        return None
    root = Path(root).resolve()
    path = Path(str(target)).expanduser()
    path = path if path.is_absolute() else root / path
    # 保留 code/ 下 symlink 的词法保护；项目内别名指向 code/ 也要保护。
    for candidate in (Path(os.path.normpath(path)), path.resolve()):
        try:
            rel = candidate.relative_to(root).as_posix()
        except ValueError:
            continue
        if rel == "code" or rel.startswith("code/"):
            return rel
    try:
        return Path(os.path.normpath(path)).relative_to(root).as_posix()
    except ValueError:
        return None


def is_guarded(root, target):
    rel = relative_target(root, target)
    return bool(rel) and any(rel == p.rstrip("/") or rel.startswith(p) for p in GUARDED_PREFIXES)


def _fresh(path, limit):
    try:
        age = time.time() - path.stat().st_mtime
        return -60 <= age and (not limit or age <= limit)
    except OSError:
        return False


def _load_json(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, ValueError):
        return None


def _same_root(data, root):
    declared = data.get("root")
    return isinstance(declared, str) and Path(declared).is_absolute() and Path(declared).resolve() == root


def task_marker_path(root, session_id=None):
    base = _runtime_dir(Path(root).resolve())
    if session_id:
        key = hashlib.sha256(str(session_id).encode()).hexdigest()
        return base / "entry-sessions" / (key + ".json")
    return base / TASK_MARKER_NAME


def find_context(root, env=None):
    """只读选定上下文；显式指向坏文件时绝不回退到其他任务。"""
    root = Path(root).resolve()
    env = os.environ if env is None else env
    limit = _max_age_seconds()
    explicit = env.get("AIDP_EXECUTION_CONTEXT")
    marker = None
    if "AIDP_EXECUTION_CONTEXT" not in env:
        marker_path = task_marker_path(root, env.get("AIDP_SESSION_ID"))
        marker = _load_json(marker_path)
        if not marker or not _same_root(marker, root) or not _fresh(marker_path, limit):
            return None, None
        if marker.get("session_id") != (env.get("AIDP_SESSION_ID") or None):
            return None, None
        explicit = marker.get("execution_context")
    if not isinstance(explicit, str) or not explicit:
        return None, None
    path = Path(explicit)
    path = path if path.is_absolute() else root / path
    if not _fresh(path, limit):
        return None, None
    from entry_context import load_context, ContextError
    try:
        ctx = load_context(root, path, migrate=False)
    except (ContextError, ValueError, TypeError, KeyError, OSError):
        return None, None
    if ctx.get("status") != "active" or not _same_root(ctx, root):
        return None, None
    if marker and marker.get("task_id") != ctx.get("task_id"):
        return None, None
    return path, ctx


def _resolve_cmd():
    return runtime_text(
        'python3 __AIDP_HOME__/scripts/entry_context.py resolve --root . --entry sprint-dev '
        '--version "<版本号>" --write-set "<本任务写集路径>" --acceptance "<本轮可核验业务结果>" --json', __file__)


def _branch_cmd():
    return runtime_text("python3 __AIDP_HOME__/scripts/aidp_config.py branch-policy", __file__)


def _branch_check(root, result):
    path = _runtime_dir(root) / MARKER_NAME
    marker = _load_json(path)
    if (not marker or not _same_root(marker, root) or not _fresh(path, _max_age_seconds())
            or not isinstance(marker.get("needs_choice"), bool)):
        result["missing"].append("branch-policy")
        result["hints"].append("先读取工作分支偏好：" + _branch_cmd())
        return
    import aidp_config
    try:
        live = aidp_config.branch_policy(str(root))
    except Exception:
        result["missing"].append("branch-policy")
        result["hints"].append("分支配置无法校验，修复后重新执行：" + _branch_cmd())
        return
    if (live.get("vcs_mode") not in {"git", "none"}
            or (live.get("vcs_mode") == "none" and os.path.lexists(root / ".git"))
            or live.get("status") not in {"ready", "not-applicable", "needs-choice"}):
        result["missing"].append("branch-policy")
        result["hints"].append("仓库或分支配置无效，修复后重新执行：" + _branch_cmd())
    elif live.get("needs_choice"):
        result["missing"].append("branch-policy-choice")
        result["hints"].append("分支偏好尚未选择：主流程保存 development.branch_policy current|new 后重读 " + _branch_cmd())
    elif any(marker.get(key) != live.get(key) for key in ("policy", "status", "vcs_mode", "needs_choice")):
        result["missing"].append("branch-policy")
        result["hints"].append("分支偏好已变化或读取标记不完整，请重新执行：" + _branch_cmd())


def check(root=".", target=None, env=None):
    root = Path(root).resolve()
    env = os.environ if env is None else env
    result = {"ok": True, "applies": True, "missing": [], "hints": [], "warnings": [],
              "context": None, "target": relative_target(root, target)}
    if target not in (None, "") and not is_guarded(root, target):
        result["applies"] = False
        return result
    path, ctx = find_context(root, env)
    if path:
        result["context"] = str(path)
        rel = relative_target(root, target)
        scope = ctx.get("authorization_scope", ctx["write_set"])
        if "implement" not in ctx.get("allowed_actions", []):
            result["missing"].append("implement")
            result["hints"].append("当前任务未授权 implement；先经开发入口 resolve 对应任务")
        if not scope:
            result["missing"].append("write-set")
            result["hints"].append("本任务写集为空，先用 entry_context.py revise 声明写集")
        elif rel:
            from entry_context import _relative_path, ContextError
            try:
                _relative_path(root, rel)
                valid_target = True
            except ContextError:
                valid_target = False
            if not valid_target or not any(rel == p or rel.startswith(p.rstrip("/") + "/") for p in scope):
                result["missing"].append("write-set")
                result["hints"].append("目标含符号链接或不在本任务 write_set 内，先明确真实路径并用 entry_context.py revise 更新写集")
    else:
        result["missing"].append("entry-context")
        result["hints"].append("先执行入口协议 resolve：" + _resolve_cmd())
        session_arg = " --session-id " + shlex.quote(str(env["AIDP_SESSION_ID"])) if env.get("AIDP_SESSION_ID") else ""
        result["hints"].append(runtime_text(
            '随后显式传 AIDP_EXECUTION_CONTEXT，或 python3 __AIDP_HOME__/scripts/entry_gate.py bind '
            '--root . --execution-context "<context.json>"' + session_arg + ' --json', __file__))
    _branch_check(root, result)
    result["ok"] = not result["missing"]
    return result


def bind_context(root, execution_context, session_id=None, *, if_writable=False):
    """选择当前任务身份；只读/空写集可正常进入，但不授予编辑权限。"""
    root = Path(root).resolve()
    env = {"AIDP_EXECUTION_CONTEXT": str(execution_context)}
    result = check(root, env=env)
    if not result["ok"]:
        # 只跳过写入资格，仍替换本会话身份，防止复用上个可写任务。
        if if_writable and result["missing"] and set(result["missing"]) <= {"implement", "write-set"}:
            result = dict(result, skipped=True, reason="not-writable")
        else:
            return result
    path, ctx = find_context(root, env)
    marker_path = task_marker_path(root, session_id)
    record = {"root": str(root), "task_id": ctx["task_id"], "execution_context": str(path.resolve()),
              "session_id": session_id or None, "bound_at": time.time()}
    from entry_context import _atomic_json
    _atomic_json(root, marker_path, record)
    return dict(result, marker=str(marker_path), task_id=ctx["task_id"])


def _self_check():
    import tempfile
    from entry_context import resolve_context
    import aidp_config
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory).resolve()
        assert not check(root, "code/a.py", env={})["ok"]
        assert not check(root, "code/a.py", env={"AIDP_TICK_COMMAND": "x"})["ok"]
        assert check(root, "docs/a.md", env={})["ok"]
        resolved = resolve_context(root, "sprint-dev", version="V1.0.0", write_set=["code"], acceptance=["check"])
        aidp_config._mark_branch_policy_read(str(root), aidp_config.branch_policy(str(root)))
        assert bind_context(root, resolved["execution_context"])["ok"]
        assert check(root, "code/a.py", env={})["ok"]
        assert not check(root, "code/a.py", env={"AIDP_EXECUTION_CONTEXT": "bad.json"})["ok"]
    print("entry_gate self-check PASS")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="改 code/** 前须绑定本任务 resolve 且已读 branch-policy")
    parser.add_argument("--self-check", action="store_true")
    sub = parser.add_subparsers(dest="cmd")
    for name in ("check", "bind"):
        command = sub.add_parser(name)
        command.add_argument("--root", default=".")
        command.add_argument("--json", action="store_true")
        if name == "check":
            command.add_argument("--target")
        else:
            command.add_argument("--execution-context", required=True)
            command.add_argument("--session-id", default=os.environ.get("AIDP_SESSION_ID"))
            command.add_argument("--if-writable", action="store_true",
                                 help="只读/空写集选择当前身份但保留 skipped/ok=false，不授写权限；其他错误仍失败")
    args = parser.parse_args(argv)
    if args.self_check:
        return _self_check()
    if not args.cmd:
        parser.print_help()
        return 2
    try:
        result = (check(args.root, args.target) if args.cmd == "check"
                  else bind_context(args.root, args.execution_context, args.session_id,
                                    if_writable=args.if_writable))
    except Exception as exc:
        result = {"ok": False, "missing": ["internal-error"], "hints": [str(exc)]}
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    elif result.get("skipped"):
        print("未绑定代码入口：无 implement 授权或有效写集为空；只读准备后再核验。", file=sys.stderr)
    elif result["ok"]:
        print("入口协议已满足")
    else:
        print("入口协议未走完，缺：" + "、".join(result["missing"]))
        for hint in result["hints"]:
            print("  → " + hint)
    return 0 if result["ok"] or result.get("skipped") else 2


if __name__ == "__main__":
    sys.exit(main())
