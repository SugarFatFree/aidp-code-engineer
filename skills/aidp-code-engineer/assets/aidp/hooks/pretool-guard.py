#!/usr/bin/env python3
"""PreToolUse：独立入口门与测试范围门。目标输入/模块异常拒绝并留痕。

Claude Bash/Edit/Write 与 Codex shell/patch payload 共用判定；不宣称 DSH
已有官方 PreToolUse 接口。exit 2 + stderr 阻断，Codex 另输出 deny JSON。
"""
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

SKIP_LOG_MAX = 50
RUNTIME_DIRNAME = "." + "aidp"
EDIT_TOOLS = {"edit", "write", "multiedit", "notebookedit", "apply_patch"}
SHELL_TOOLS = {"bash", "shell", "shell_command", "exec_command", "local_shell"}
PATCH_PATH_RE = re.compile(r"(?m)^\*\*\* (?:Add File|Update File|Delete File|Move to): (.+?)\s*$")
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _agent_flag():
    argv = sys.argv[1:]
    if "--agent" in argv:
        i = argv.index("--agent")
        if i + 1 < len(argv):
            return argv[i + 1]
    return "claude"


def _block(text):
    sys.stderr.write(text.rstrip() + "\n")
    if _agent_flag() == "codex":
        sys.stdout.write(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse", "permissionDecision": "deny",
            "permissionDecisionReason": text}}, ensure_ascii=False) + "\n")
    raise SystemExit(2)


def _project_root(data):
    for key in ("CLAUDE_PROJECT_DIR", "CODEX_PROJECT_DIR"):
        val = os.environ.get(key)
        if val and os.path.isdir(val):
            return Path(val).resolve()
    cwd = data.get("cwd") if isinstance(data, dict) else None
    base = cwd if isinstance(cwd, str) and os.path.isdir(cwd) else os.getcwd()
    try:
        result = subprocess.run(["git", "-C", base, "rev-parse", "--show-toplevel"],
                                capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            return Path(result.stdout.strip()).resolve()
    except Exception:
        pass
    return Path(base).resolve()


def _note_skip(root, detail):
    """历史日志文件名兼容；现在异常会阻断，不再表示 fail-open。"""
    try:
        if not (root / "memory").is_dir():
            return
        directory = root / "memory" / RUNTIME_DIRNAME
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "pretool-guard-skips.jsonl"
        record = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "decision": "deny", "detail": str(detail)[:400]}
        lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
        path.write_text("\n".join(lines[-(SKIP_LOG_MAX - 1):] + [json.dumps(record, ensure_ascii=False)]) + "\n", encoding="utf-8")
    except Exception:
        pass


def _enabled(root, guard):
    # 配置依赖损坏时保守开启；检查模块失败由 main 阻断。
    try:
        import aidp_config
        return getattr(aidp_config, guard + "_guard_enabled")(str(root))
    except Exception:
        return True


def edit_targets(tool_name, tool_input, cwd):
    if isinstance(tool_input, str) and tool_name == "apply_patch":
        tool_input = {"patch": tool_input}
    if not isinstance(tool_input, dict):
        raise ValueError("编辑工具输入必须是对象")
    raw = []
    for key in ("file_path", "notebook_path", "path"):
        if key in tool_input:
            value = tool_input[key]
            if not isinstance(value, str) or not value.strip():
                raise ValueError("编辑目标路径无效")
            raw.append(value)
    patch = tool_input.get("command") or tool_input.get("input") or tool_input.get("patch")
    if tool_name == "apply_patch" or not raw:
        if isinstance(patch, str):
            raw.extend(PATCH_PATH_RE.findall(patch))
    if not raw:
        raise ValueError("无法确定编辑工具的写目标")
    out = []
    for item in raw:
        path = Path(item).expanduser()
        out.append(str(path if path.is_absolute() else Path(cwd) / path))
    return out


def _execution_context(root, env):
    # 错误的显式指向原样交测试门，不能回退到另一任务。
    if env.get("AIDP_EXECUTION_CONTEXT"):
        return env["AIDP_EXECUTION_CONTEXT"]
    import entry_gate
    path, _ = entry_gate.find_context(root, env)
    return str(path) if path else None


def _render_home(text, root):
    home = Path(os.path.relpath(Path(__file__).resolve().parents[1], root)).as_posix()
    return str(text).replace("{{" + "AIDP_HOME}}", home).replace("__" + "AIDP_HOME__", home)


def check_bash(root, command, env):
    import test_command_guard
    result = test_command_guard.evaluate(command, root=str(root), execution_context=_execution_context(root, env))
    if not isinstance(result, dict) or not isinstance(result.get("allowed"), bool):
        raise ValueError("测试范围校验未返回明确 allowed 判定")
    if result["allowed"]:
        return None
    reason = _render_home(result.get("reason") or "命令被测试范围护栏拒绝", root)
    hint = _render_home(result.get("hint") or "", root)
    return ("AIDP 测试范围护栏：" + reason + ("\n  → " + hint if hint else "")
            + "\n（仅测试门临时停用：test_guard.enabled: false 或 touch memory/.test-guard-off；入口门保持独立。）")


def check_targets(root, targets, env):
    import entry_gate
    for target in targets:
        result = entry_gate.check(root, target, env=env)
        if result["ok"]:
            continue
        lines = ["AIDP 入口护栏：修改 %s 前入口协议未走完，缺：%s" % (
            result.get("target") or target, "、".join(result["missing"]))]
        lines.extend("  → " + hint for hint in result["hints"])
        lines.append("（仅入口门临时停用：entry_guard.enabled: false 或 touch memory/.entry-guard-off；测试门保持独立。）")
        return "\n".join(lines)
    return None


def _shell_input(tool_input):
    if not isinstance(tool_input, dict):
        raise ValueError("shell 工具输入必须是对象")
    value = tool_input.get("command", tool_input.get("cmd"))
    if isinstance(value, str) and value.strip():
        return value
    if isinstance(value, list) and value and all(isinstance(v, str) for v in value):
        return shlex.join(value)
    raise ValueError("shell command 必须是非空字符串或 argv 字符串数组")


def main():
    root = _project_root({})
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict) or not isinstance(data.get("tool_name"), str):
            raise ValueError("PreToolUse 输入缺少 tool_name")
        root = _project_root(data)
        tool = data["tool_name"].split(".")[-1].lower()
        if tool not in SHELL_TOOLS | EDIT_TOOLS:
            return 0
        tool_input = data.get("tool_input")
        # Codex 的工具 arguments 可能由调用方序列化；仅接受合法 JSON 对象。
        if isinstance(tool_input, str) and tool != "apply_patch":
            tool_input = json.loads(tool_input)
        cwd = data.get("cwd") or str(root)
        if isinstance(tool_input, dict):
            cwd = tool_input.get("workdir") or tool_input.get("cwd") or cwd
        if not isinstance(cwd, str):
            raise ValueError("工具 cwd/workdir 必须是路径字符串")
        cwd = str((root / cwd).resolve())
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        env = dict(os.environ)
        if data.get("session_id"):
            env["AIDP_SESSION_ID"] = str(data["session_id"])
        entry_enabled, test_enabled = _enabled(root, "entry"), _enabled(root, "test")
        message = None
        if tool in SHELL_TOOLS:
            command = _shell_input(tool_input)
            if test_enabled:
                scoped_command = command if Path(cwd) == root else f"cd {shlex.quote(cwd)} && {command}"
                message = check_bash(root, scoped_command, env)
            if not message and entry_enabled:
                import shell_write_targets
                writes = shell_write_targets.analyze(command, cwd, env)
                for write in writes["writes"]:
                    message = check_targets(root, [write["target"]], dict(env, **write["env"]))
                    if message:
                        break
                if not message and writes["uncertain"]:
                    # 入口就绪也不能据此证明未知目标在 write_set 中；拆分后按实际目标复验。
                    message = ("AIDP 入口护栏：无法确定动态/复合写入是否落在 code/** 及本任务 write_set 内："
                               + "；".join(writes["reasons"])
                               + "\n先完成入口 resolve、branch-policy 和任务绑定，再拆为可校验的显式路径写入命令。")
        elif entry_enabled:
            message = check_targets(root, edit_targets(tool, tool_input, cwd), env)
        if message:
            _block(message)
    except SystemExit:
        raise
    except Exception as exc:
        detail = "%s: %s" % (type(exc).__name__, exc)
        _note_skip(root, detail)
        _block("AIDP 护栏无法完成校验，已拒绝此次工具调用：" + detail
               + "\n请修复输入或守卫模块后重试；入口门与测试范围门分别配置，不能以内部异常代替通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
