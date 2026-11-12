#!/usr/bin/env python3
"""light 任务标准流程单一入口：resolve → 选测 → 执行 → 汇总。

只编排既有脚本，不另立规则、不绕过 execution_policy：
  start   entry_context resolve + route(dev) + aidp_config branch-policy 读取
  select  execution_policy require-action(related-test) → test_scope（unit-scope.json）
          → select_related_tests（写白名单；脚本缺失时阻断）
  run     逐条 test_command_guard check 校验 scope 里的每条命令 → test_ledger run-scope → verify
          （命令只来自 test_scope 的相关测试，永不拼整目录/全量命令；guard 拒绝即终止）
  report  汇总改动文件/选中测试/通过·失败·未映射/known-failure 差集，并给出 verdict
  all     依次执行 start/select/run/report

输出：stdout 最后一行恒为 JSON（--json 时整个 stdout 仅此一行）。
退出码：0 已核验成功或明确不适用；1 测试 FAIL 或存在新失败；2 输入/授权/未核验/守卫拒绝。
"""
import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
STATE_NAME = "light-task.json"
OK_STATUSES = {"PASS", "CARRIED", "NOT_APPLICABLE"}


class StepError(Exception):
    def __init__(self, message, code=2, **extra):
        super().__init__(message)
        self.code = code
        self.extra = extra


def _script(name):
    return SCRIPTS / name


def _call(name, *args, check=True):
    """运行同目录脚本，返回 (rc, stdout, stderr, 末行JSON或None)。"""
    proc = subprocess.run([sys.executable, "-B", str(_script(name)), *map(str, args)],
                          text=True, capture_output=True)
    payload = None
    lines = [ln for ln in proc.stdout.strip().splitlines() if ln.strip()]
    for candidate in ([lines[-1]] if lines else []) + ([proc.stdout.strip()] if proc.stdout.strip() else []):
        try:
            payload = json.loads(candidate)
            break
        except ValueError:
            continue
    if check and proc.returncode != 0:
        raise StepError(f"{name} 失败(exit {proc.returncode}): {(proc.stderr or proc.stdout).strip()[:600]}",
                        code=2, script=name)
    return proc.returncode, proc.stdout, proc.stderr, payload


def _runners(value):
    value = value or os.environ.get("UNIT_RUNNERS_JSON", "")
    if not value:
        raise StepError("缺少项目测试运行器：传 --runners-json JSON|@file 或设置 UNIT_RUNNERS_JSON")
    if value.startswith("@"):
        value = Path(value[1:]).read_text(encoding="utf-8")
    try:
        parsed = json.loads(value)
    except ValueError as exc:
        raise StepError(f"--runners-json 不是合法 JSON: {exc}")
    if not isinstance(parsed, (list, dict)) or not parsed:
        raise StepError("--runners-json 须为非空运行器列表")
    return json.dumps(parsed, ensure_ascii=False)


def _ctx(args):
    ctx = args.execution_context or os.environ.get("AIDP_EXECUTION_CONTEXT") or os.environ.get("EXECUTION_CONTEXT", "")
    if not ctx:
        raise StepError("缺少 --execution-context（先跑 start，或继承父任务路径）")
    path = Path(ctx)
    if not path.is_file():
        raise StepError(f"execution_context 不存在: {ctx}")
    return str(path)


def _state_path(ctx):
    return Path(ctx).parent / STATE_NAME


def _load_state(ctx):
    try:
        return json.loads(_state_path(ctx).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_state(ctx, key, value):
    state = _load_state(ctx)
    state[key] = value
    _state_path(ctx).write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def _task_key(ctx):
    try:
        data = json.loads(Path(ctx).read_text(encoding="utf-8"))
        found = data.get("execution_context", data)
        return str(found.get("task_id") or "default")
    except (OSError, ValueError, AttributeError):
        return "default"


# ---------------------------------------------------------------- start
def step_start(args):
    root = args.root
    cmd = ["resolve", "--root", root, "--entry", args.entry, "--json"]
    if args.execution_context:
        cmd += ["--execution-context", args.execution_context]
    else:
        if not args.version or not args.write_set or not args.acceptance:
            raise StepError("新任务 start 须带 --version / --write-set / --acceptance（或继承 --execution-context）")
        cmd += ["--version", args.version, "--write-set", *args.write_set,
                "--acceptance", *args.acceptance]
        if args.task_scope:
            cmd += ["--task-scope", args.task_scope]
        if args.authorization_source:
            cmd += ["--authorization-source", args.authorization_source]
        for grant in args.grant or []:
            cmd += ["--grant", grant]
    _, _, _, resolved = _call("entry_context.py", *cmd)
    if not resolved or "execution_context" not in resolved:
        raise StepError("entry_context resolve 未返回 execution_context")
    ctx = resolved["execution_context"]
    _, _, _, route = _call("entry_context.py", "route", "--root", root, "--entry", args.entry,
                           "--execution-context", ctx, "--phase", args.phase, "--json")
    route = route or {}
    if route.get("route") not in (None, "light"):
        raise StepError(f"route={route.get('route')} 不是 light：formal 路径不使用 light_task.py", route=route)
    # 读取工作分支策略（aidp_config 子命令负责落「已读」标记，needs-choice 交主流程询问）
    policy_rc, _, policy_err, policy = _call("aidp_config.py", "branch-policy", "--root", root, check=False)
    if policy_rc not in (0, 3) or not isinstance(policy, dict):
        raise StepError(f"branch-policy 读取失败(exit {policy_rc}): {policy_err.strip()}")
    needs_choice = policy_rc == 3 or bool(policy.get("needs_choice"))
    binding = None
    if not needs_choice:
        bind_args = ["bind", "--root", root, "--execution-context", ctx, "--if-writable", "--json"]
        if args.session_id:
            bind_args += ["--session-id", args.session_id]
        _, _, _, binding = _call("entry_gate.py", *bind_args)
        if not isinstance(binding, dict) or (not binding.get("ok") and not binding.get("skipped")):
            raise StepError("entry_gate bind 未确认任务绑定成功或明确只读跳过")
    result = {
        "step": "start", "execution_context": ctx,
        "task_id": (resolved.get("identity") or {}).get("task_id") or _task_key(ctx),
        "mode": (resolved.get("identity") or {}).get("mode", "light"),
        "route": route.get("route", "light"),
        "allowed_actions": resolved.get("allowed_actions", []),
        "actions": route.get("actions", []),
        "branch_policy": policy,
        "branch_needs_choice": needs_choice,
        "entry_bound": bool(binding and binding.get("ok")),
        "entry_binding_skipped": bool(binding and binding.get("skipped")),
        "session_id": args.session_id,
    }
    _save_state(ctx, "start", result)
    return result


# --------------------------------------------------------------- select
def step_select(args):
    ctx = _ctx(args)
    runners = _runners(args.runners_json)
    _call("execution_policy.py", "require-action", "--root", args.root,
          "--execution-context", ctx, "--action", "related-test")
    scope_file = Path(ctx).parent / "unit-scope.json"
    _, out, _, scope = _call("test_scope.py", "--root", args.root, "--execution-context", ctx,
                             "--runners-json", runners, "--json")
    if not scope or "scope_hash" not in scope:
        raise StepError("test_scope 未返回有效 scope")
    scope_file.write_text(json.dumps(scope, ensure_ascii=False), encoding="utf-8")
    warnings, allowlist = [], None
    if _script("select_related_tests.py").is_file():
        rc, _, err, sel = _call("select_related_tests.py", "--root", args.root,
                                "--execution-context", ctx, "--scope", str(scope_file),
                                "--json", check=False)
        if rc == 0 and isinstance(sel, dict):
            allowlist = sel.get("allowlist_file")
            if set(sel.get("tests") or []) != set(scope.get("tests") or []):
                raise StepError("白名单与已冻结测试范围不一致，不能执行或宣称已覆盖")
        else:
            raise StepError(f"select_related_tests 失败(exit {rc}): {err.strip()[:400]}")
    else:
        raise StepError("select_related_tests.py 不存在：无法生成测试白名单，恢复安装后重试")
    unmapped = list(scope.get("unmapped") or [])
    result = {
        "step": "select", "execution_context": ctx, "scope_file": str(scope_file),
        "scope_hash": scope["scope_hash"], "changed": scope.get("changed", []),
        "tests": list(scope.get("tests") or []), "unmapped": unmapped,
        "unmapped_disposition": ("无对应测试，记 UNVERIFIED(Minor) 未核验，不得宣称已覆盖；"
                                 "需补测试或在终端结果如实列出" if unmapped else ""),
        "unrunnable": list(scope.get("unrunnable") or []),
        "applicability": (scope.get("applicability") or {}).get("status"),
        "allowlist_file": allowlist, "warnings": warnings,
    }
    _save_state(ctx, "select", result)
    return result


# ------------------------------------------------------------------ run
def _guard_check(args, ctx, scope):
    """逐条用 test_command_guard 评估 scope 的执行命令；返回 (blocked, warnings)。"""
    if not _script("test_command_guard.py").is_file():
        raise StepError("test_command_guard.py 不存在：无法校验测试范围，恢复安装后重试")
    blocked = []
    for item in scope.get("runs") or []:
        argv = [str(a) for a in item.get("argv") or []]
        if not argv:
            continue
        cwd = item.get("cwd") or "."
        text = shlex.join(argv)
        if cwd != ".":
            text = f"cd {shlex.quote(str(cwd))} && {text}"
        rc, _, _, verdict = _call("test_command_guard.py", "check", "--root", args.root,
                                  "--execution-context", ctx, "--command", text, "--json", check=False)
        if rc != 0 or not isinstance(verdict, dict) or verdict.get("allowed") is not True:
            details = verdict if isinstance(verdict, dict) else {}
            blocked.append({"command": text, "cwd": cwd,
                            "reason": details.get("reason", f"guard 未确认放行(exit {rc})"),
                            "hint": details.get("hint", "")})
    return blocked, []


def step_run(args):
    ctx = _ctx(args)
    state = _load_state(ctx)
    selected = state.get("select")
    # 新一轮执行开始即撤销旧汇总结论，守卫/执行/核验中断都不能复用旧 PASS。
    _save_state(ctx, "run", {"status": "UNVERIFIED", "run_ids": [], "exit_code": 2,
                             "warnings": ["本轮相关测试尚未完成执行与证据核验"]})
    scope_file = Path(ctx).parent / "unit-scope.json"
    if not selected or not scope_file.is_file() or args.reselect:
        selected = step_select(args)
    scope = json.loads(scope_file.read_text(encoding="utf-8"))
    env_id = args.env_id or os.environ.get("TEST_ENV_ID") or "light-local"
    blocked, warnings = _guard_check(args, ctx, scope)
    if blocked:
        raise StepError("test_command_guard 拒绝 scope 内命令，未执行任何测试", code=2,
                        step="run", guard_blocked=blocked)
    run_cmd = ["run-scope", "--root", args.root, "--execution-context", ctx,
               "--scope-file", str(scope_file), "--env-id", env_id]
    if args.timeout:
        run_cmd += ["--timeout", str(args.timeout)]
    if args.force:
        run_cmd.append("--force")
    rc, _, err, run = _call("test_ledger.py", *run_cmd, check=False)
    if not isinstance(run, dict):
        raise StepError(f"test_ledger run-scope 无有效输出(exit {rc}): {err.strip()[:400]}")
    run_file = Path(ctx).parent / "run-set.json"
    run_file.write_text(json.dumps(run, ensure_ascii=False) + "\n", encoding="utf-8")
    status = run.get("status", "UNVERIFIED")
    verified = None
    if status in OK_STATUSES:
        vargs = ["verify", "--root", args.root, "--execution-context", ctx, "--scope-file", str(scope_file),
                 "--scope-hash", scope["scope_hash"], "--env-id", env_id]
        for rid in run.get("run_ids") or []:
            vargs += ["--run-id", rid]
        vrc, _, verr, vpayload = _call("test_ledger.py", *vargs, check=False)
        verified = {"exit": vrc, "payload": vpayload}
        if vrc != 0 or not isinstance(vpayload, dict) or vpayload.get("status") not in OK_STATUSES:
            status = "UNVERIFIED"
            detail = (vpayload.get("error") if isinstance(vpayload, dict) else None) or verr.strip() or f"exit {vrc}"
            warnings.append(f"test_ledger verify 失败: {str(detail)[:300]}")
    result = {"step": "run", "execution_context": ctx, "status": status, "env_id": env_id,
              "scope_hash": scope["scope_hash"], "run_ids": run.get("run_ids", []),
              "run_set_file": str(run_file), "verify": verified, "warnings": warnings,
              "exit_code": 0 if status in OK_STATUSES else (1 if status == "FAIL" else 2)}
    _save_state(ctx, "run", result)
    return result


# --------------------------------------------------------------- report
def _failed_tests(run):
    failed = []
    for item in run.get("runs") or []:
        if item.get("status") in ("FAIL", "ERROR", "TREE_CHANGED") or item.get("command_status") == "FAIL":
            tests = (item.get("selection") or {}).get("tests") or []
            failed.extend(tests or [" ".join(map(str, item.get("command") or []))])
    return sorted(set(failed))


def _known_failure_diff(args, ctx, failed):
    key = _task_key(ctx)
    base = Path(args.root) / "memory/.aidp/test-baseline" / f"{key}.json"
    if not failed:
        return {"baseline": str(base) if base.is_file() else None, "known": [], "new_failures": []}
    if not base.is_file() or not _script("test_baseline.py").is_file():
        return {"baseline": None, "known": [], "new_failures": failed,
                "note": "无已知失败基线：全部失败按新失败处理（禁用 git stash 做基线对照）"}
    ids = Path(ctx).parent / "failed-ids.json"
    ids.write_text(json.dumps(failed), encoding="utf-8")
    rc, _, err, payload = _call("test_baseline.py", "diff", "--root", args.root,
                                "--execution-context", ctx, "--ids-file", str(ids), "--json", check=False)
    if rc not in (0, 1) or not isinstance(payload, dict):
        return {"baseline": str(base), "known": [], "new_failures": failed,
                "note": f"test_baseline diff 失败(exit {rc}): {err.strip()[:300]}，保守按新失败处理"}
    new = payload.get("new_failures", payload.get("new", failed))
    return {"baseline": str(base), "known": sorted(set(failed) - set(new)), "new_failures": sorted(new)}


def step_report(args):
    ctx = _ctx(args)
    state = _load_state(ctx)
    sel, run_state = state.get("select") or {}, state.get("run") or {}
    run_file = Path(ctx).parent / "run-set.json"
    try:
        run = json.loads(run_file.read_text(encoding="utf-8").strip().splitlines()[-1])
    except (OSError, ValueError, IndexError):
        run = {}
    failed = _failed_tests(run)
    passed = sorted({t for item in run.get("runs") or [] if item.get("status") in ("PASS", "CARRIED")
                     for t in (item.get("selection") or {}).get("tests") or []})
    diff = _known_failure_diff(args, ctx, failed)
    # run-set 只保存执行原始结果，最终状态须包含本轮证据核验结论。
    status = run_state.get("status") or "NOT_RUN"
    verification = run_state.get("verify")
    if isinstance(verification, dict) and verification.get("exit") != 0:
        status = "UNVERIFIED"
    unmapped = sel.get("unmapped", run.get("unmapped", []))
    if status == "FAIL":
        verdict = "FAIL" if diff["new_failures"] else "KNOWN_FAILURE_ONLY"
    elif status in ("PASS", "CARRIED"):
        verdict = "PASS" if not (sel.get("unrunnable") or unmapped) else "PASS_WITH_GAPS"
    elif status == "NOT_APPLICABLE" and sel.get("applicability") == "NOT_APPLICABLE":
        verdict = "NOT_APPLICABLE"
    else:
        verdict = "UNVERIFIED"
    return {
        "step": "report", "execution_context": ctx, "task_id": _task_key(ctx),
        "verdict": verdict, "run_status": status, "changed": sel.get("changed", []),
        "selected_tests": sel.get("tests", []), "passed": passed, "failed": failed,
        "unmapped": unmapped, "unmapped_disposition": sel.get("unmapped_disposition", ""),
        "unrunnable": sel.get("unrunnable", []), "known_failure_diff": diff,
        "scope_hash": sel.get("scope_hash"), "run_ids": run_state.get("run_ids", run.get("run_ids", [])),
        "warnings": (sel.get("warnings") or []) + (run_state.get("warnings") or []),
        "next": "entry_context.py check/complete 传 --scope-file/--scope-hash/--env-id/--run-id 收口",
        "exit_code": 1 if verdict == "FAIL" else (2 if verdict == "UNVERIFIED" else 0),
    }


# ------------------------------------------------------------------ all
def step_all(args):
    results = {}
    start = step_start(args)
    results["start"] = start
    args.execution_context = start["execution_context"]
    results["select"] = step_select(args)
    try:
        results["run"] = step_run(args)
    except StepError as exc:
        results["run"] = {"step": "run", "error": str(exc), **exc.extra}
    report = step_report(args)
    results["report"] = report
    code = report["exit_code"]
    if "error" in results["run"] or results["run"].get("exit_code") == 2:
        code = 2
    return {"step": "all", "execution_context": start["execution_context"],
            "verdict": report["verdict"], "steps": results, "exit_code": code}


STEPS = {"start": step_start, "select": step_select, "run": step_run, "report": step_report, "all": step_all}


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("step", choices=sorted(STEPS))
    parser.add_argument("--root", default=".")
    parser.add_argument("--execution-context", default="")
    parser.add_argument("--session-id", default=os.environ.get("AIDP_SESSION_ID", ""),
                        help="宿主提供的会话标识，绑定同一会话的编辑 hook")
    parser.add_argument("--entry", default="sprint-dev")
    parser.add_argument("--phase", default="dev")
    parser.add_argument("--version")
    parser.add_argument("--write-set", nargs="+", action="extend")
    parser.add_argument("--acceptance", nargs="+", action="extend")
    parser.add_argument("--task-scope")
    parser.add_argument("--grant", action="append")
    parser.add_argument("--authorization-source")
    parser.add_argument("--runners-json", default="")
    parser.add_argument("--env-id", default="")
    parser.add_argument("--timeout", type=int)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--reselect", action="store_true", help="run 前强制重新选测")
    parser.add_argument("--json", action="store_true", help="仅输出一行 JSON（默认同样以 JSON 收尾）")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        result = STEPS[args.step](args)
    except StepError as exc:
        print(json.dumps({"step": args.step, "error": str(exc), **exc.extra}, ensure_ascii=False))
        return exc.code
    except (OSError, ValueError) as exc:
        print(json.dumps({"step": args.step, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return int(result.get("exit_code", 0))


if __name__ == "__main__":
    sys.exit(main())
