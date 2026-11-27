#!/usr/bin/env python3
"""PreToolUse：独立入口门与测试范围门。目标输入/模块异常拒绝并留痕。

Claude Bash/Edit/Write 与 Codex shell/patch payload 共用判定；不宣称 DSH
已有官方 PreToolUse 接口。exit 2 + stderr 阻断，Codex 另输出 deny JSON。
外部副作用（容器内写入等，不是仓库文件直写）输出 ask 决定，由宿主弹出授权提示。

离线自检（只解释判定，不执行）：
  pretool-guard.py --explain "<shell 命令>" [--cwd DIR] [--json]
  pretool-guard.py --explain-edit <文件路径>
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
    message = ("AIDP 测试范围护栏 · 拒绝（测试命令超出本任务白名单）\n类别：测试范围\n原因：" + reason
               + ("\n合规替代：\n  → " + hint if hint else "")
               + "\n（仅测试门临时停用：test_guard.enabled: false 或 touch memory/.test-guard-off；入口门保持独立。）")
    return _decision("deny", "test-scope", category="test-scope", fragment=reason[:120], message=message)


CATEGORY_LABEL = {
    "heredoc": "heredoc", "redirect": "重定向", "wildcard": "变量/通配符写目标", "docker-write": "docker 写",
    "wrapper": "包装器写入", "python": "python 写入", "sed": "sed", "compound": "复合/条件分支",
    "dynamic-exec": "动态执行", "cwd": "目录切换", "parse": "语法解析", "other": "其他",
}
CATEGORY_ADVICE = {
    "heredoc": "heredoc 目标必须是字面量路径（cat > code/…/x <<'EOF'），且在 write_set 内；或改用 Write/Edit 工具写文件",
    "redirect": "重定向目标写成字面量路径并在 write_set 内；或改用 Write/Edit 工具",
    "wildcard": "把变量/通配符展开成字面量路径后逐个写；或改用 Write/Edit 工具",
    "docker-write": "容器内目标走授权提示；bind mount 到仓库的路径按宿主源路径校验，须在 write_set 内",
    "wrapper": "去掉包装层，直接写字面量路径；或改用 Write/Edit 工具",
    "python": "写目标用字面常量路径，避免循环/分支内写文件；或改用 Write/Edit 工具",
    "sed": "sed -i 's/旧/新/' <字面量文件路径>；脚本里的字符不会被当作写目标",
    "compound": "拆成多条单步命令，每条只写一个字面量路径",
    "dynamic-exec": "避免 eval/source/动态命令；改用显式命令",
    "cwd": "不要在同一命令里 cd 后再写；用字面量绝对/相对路径",
    "parse": "检查引号/括号是否成对，或拆成更简单的命令",
    "other": "改用 Write/Edit 工具，或拆成可静态判定的显式路径命令",
}
SCRATCH_HINT = "临时内容可写 scratch 目录：memory/.aidp/scratch/ 或 /tmp（不受入口门限制）"


def _decision(decision, kind, **extra):
    return dict({"decision": decision, "kind": kind, "category": "", "fragment": "", "message": "",
                 "alternatives": []}, **extra)


def check_targets(root, targets, env):
    import entry_gate
    for target in targets:
        result = entry_gate.check(root, target, env=env)
        if result["ok"]:
            continue
        protocol = {"entry-context", "branch-policy", "branch-policy-choice", "implement"}
        kind = "protocol-incomplete" if protocol & set(result["missing"]) else "out-of-write-set"
        label = "协议未完成" if kind == "protocol-incomplete" else "超出本任务 write_set"
        shown = result.get("target") or target
        lines = ["AIDP 入口护栏 · 拒绝（%s）" % label,
                 "类别：%s" % ("入口协议" if kind == "protocol-incomplete" else "超出 write_set"),
                 "命中目标：%s；缺：%s" % (shown, "、".join(result["missing"]))]
        lines.append("合规替代：")
        lines.extend("  → " + hint for hint in result["hints"])
        lines.append("（仅入口门临时停用：entry_guard.enabled: false 或 touch memory/.entry-guard-off；测试门保持独立。）")
        return _decision("deny", kind, category=kind, fragment=str(shown), message="\n".join(lines),
                         alternatives=list(result["hints"]))
    return None


def check_shell_writes(root, command, cwd, env):
    import shell_write_targets
    writes = shell_write_targets.analyze(command, cwd, env)
    for write in writes["writes"]:
        found = check_targets(root, [write["target"]], dict(env, **write["env"]))
        if found:
            return found
    if writes["uncertain"]:
        details = writes.get("details") or [{"category": "other", "reason": r, "fragment": ""} for r in writes["reasons"]]
        lines = ["AIDP 入口护栏 · 拒绝（静态分析无法判定；这不表示入口协议未完成）",
                 "无法证明该命令的写目标是否落在 code/** 及本任务 write_set 内："]
        alternatives = []
        for item in details:
            label = CATEGORY_LABEL.get(item["category"], item["category"])
            lines.append("  · [%s] %s%s" % (label, item["reason"], "：" + item["fragment"] if item["fragment"] else ""))
            advice = CATEGORY_ADVICE.get(item["category"], CATEGORY_ADVICE["other"])
            if advice not in alternatives:
                alternatives.append(advice)
        lines.append("合规替代：")
        lines.extend("  → " + advice for advice in alternatives)
        lines.append("  → 改用 Write/Edit 工具逐文件写入（工具写入只校验目标路径）")
        lines.append("  → " + SCRATCH_HINT)
        lines.append("自检（只解释、不执行）：pretool-guard.py --explain \"<命令>\"")
        first = details[0] if details else {"category": "other", "fragment": ""}
        return _decision("deny", "static-undecidable", category=first["category"], fragment=first["fragment"],
                         message="\n".join(lines), alternatives=alternatives)
    if writes.get("external"):
        lines = ["AIDP 入口护栏 · 需要授权（外部副作用，不是对仓库文件的直接写入）"]
        for item in writes["external"]:
            lines.append("  · [%s] %s" % (item["kind"], item["fragment"]))
        lines.append("该命令写的是容器文件系统，或容器内未绑定到仓库的路径；请确认是否继续。")
        return _decision("ask", "external-side-effect", category="docker-write",
                         fragment=writes["external"][0]["fragment"], message="\n".join(lines))
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


def evaluate(root, tool, tool_input, cwd, env):
    """纯判定，不执行命令：返回 {decision: allow|deny|ask, kind, category, fragment, message, alternatives}。"""
    entry_enabled, test_enabled = _enabled(root, "entry"), _enabled(root, "test")
    if tool in SHELL_TOOLS:
        command = _shell_input(tool_input)
        if test_enabled:
            scoped_command = command if Path(cwd) == root else f"cd {shlex.quote(cwd)} && {command}"
            found = check_bash(root, scoped_command, env)
            if found:
                return found
        if entry_enabled:
            found = check_shell_writes(root, command, cwd, env)
            if found:
                return found
    elif entry_enabled:
        found = check_targets(root, edit_targets(tool, tool_input, cwd), env)
        if found:
            return found
    return _decision("allow", "allow")


def _explain(argv):
    """离线自检：只解释判定结果，不执行命令。"""
    import argparse
    parser = argparse.ArgumentParser(prog="pretool-guard.py")
    parser.add_argument("--explain", metavar="CMD")
    parser.add_argument("--explain-edit", metavar="PATH")
    parser.add_argument("--cwd")
    parser.add_argument("--root")
    parser.add_argument("--session-id")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--agent")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve() if args.root else _project_root({})
    cwd = str((root / args.cwd).resolve()) if args.cwd else str(root)
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    env = dict(os.environ)
    if args.session_id:
        env["AIDP_SESSION_ID"] = args.session_id
    try:
        if args.explain is not None:
            result = evaluate(root, "bash", {"command": args.explain}, cwd, env)
            subject = args.explain
        else:
            result = evaluate(root, "edit", {"file_path": args.explain_edit}, cwd, env)
            subject = args.explain_edit
    except Exception as exc:  # 与真实 hook 同样 fail-closed，但这里只是解释
        result = _decision("deny", "guard-error", category="guard-error", fragment=str(exc)[:120],
                           message="AIDP 护栏无法完成校验：%s: %s" % (type(exc).__name__, exc))
        subject = args.explain if args.explain is not None else args.explain_edit
    result = dict(result, subject=subject, executed=False)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        label = {"allow": "允许", "deny": "拒绝", "ask": "需授权提示"}[result["decision"]]
        print("判定：%s（%s）  [仅解释，未执行]" % (label, result["kind"]))
        print("对象：" + str(subject))
        if result["message"]:
            print(result["message"])
    return 2 if result["decision"] == "deny" else 0


def _resolve_unattended_ask(root, env, result):
    """无人值守下把 ask 变成确定性决定：当前任务持有 deploy 授权 → allow（写 external-side-effects.jsonl 留痕）。"""
    granted = False
    try:
        import entry_gate
        from execution_policy import require_action
        _, ctx = entry_gate.find_context(root, env)
        if ctx:
            ctx = require_action(ctx, 'deploy')  # 重验当前 revision 与完整父链，不能仅检查子记录中的动作名。
            granted = True
    except (OSError, ValueError, KeyError, TypeError):
        granted = False
    if granted:
        try:
            from entry_context import _safe_inside
            ledger = _safe_inside(Path(root).resolve(), Path(root) / 'memory' / RUNTIME_DIRNAME / 'external-side-effects.jsonl')
            ledger.parent.mkdir(parents=True, exist_ok=True)
            with ledger.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "decision": "allow",
                                         "basis": "deploy-authorized-unattended", 'task_id': ctx['task_id'],
                                         'revision': ctx['revision'], 'authorization_revision': ctx['authorization_revision'],
                                         "detail": result.get("message", "")[:300]}, ensure_ascii=False) + "\n")
        except (OSError, ValueError) as exc:
            return 'deny', '外部副作用授权已核验，但授权留痕写入失败；修复后重试：' + str(exc)
        return "allow", ""
    return "deny", ("无人值守 tick 中该命令属于外部副作用（如 docker cp/exec/run 写容器文件系统），需要 deploy 授权，"
                    "而当前任务没有该授权，且无人可确认。\n" + result.get("message", "") +
                    "\n处置：改为在 bind mount 内或宿主机上完成；确需写容器时，由用户在 /sprint-autopilot 授权中包含 deploy 后再运行。")


def main():
    if any(a in ("--explain", "--explain-edit") for a in sys.argv[1:]):
        return _explain(sys.argv[1:])
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
        result = evaluate(root, tool, tool_input, cwd, env)
        if result["decision"] == "deny":
            _block(result["message"])
        if result["decision"] == "ask" and env.get("AIDP_TICK_COMMAND"):
            # 无人值守 tick（调度器注入 AIDP_TICK_COMMAND）：没有人可答 ask，等同拒绝却不说明原因。
            # 按 deploy 授权确定性处置：已授权 → 放行并留痕；未授权 → 明确拒绝（各 Agent 行为一致）。
            decision, note = _resolve_unattended_ask(root, env, result)
            if decision == "deny":
                _block(note)
        elif result["decision"] == "ask" and _agent_flag() == "claude":
            sys.stdout.write(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PreToolUse", "permissionDecision": "ask",
                "permissionDecisionReason": result["message"]}}, ensure_ascii=False) + "\n")
    except SystemExit:
        raise
    except Exception as exc:
        detail = "%s: %s" % (type(exc).__name__, exc)
        _note_skip(root, detail)
        _block("AIDP 护栏无法完成校验，已拒绝此次工具调用（校验异常，不是入口协议未完成）：" + detail
               + "\n请修复输入或守卫模块后重试；可用 pretool-guard.py --explain \"<命令>\" 离线复现。"
               + "入口门与测试范围门分别配置，不能以内部异常代替通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
