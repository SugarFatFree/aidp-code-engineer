#!/usr/bin/env python3
"""入口上下文的最小授权与共享执行预算；没有独立任务身份或默认安装权限。

调用方在实际工作前 require_action/reserve_budget，工作后 record_outcome。
预算和失败记录沿用 entry_context 的任务锁；所有子任务消费根任务同一份余额。
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path
import re
import time
import uuid

BASE_ACTIONS = frozenset(("implement", "static"))
SCOPE_ACTIONS = {"development": BASE_ACTIONS, "review": frozenset(), "test": frozenset(("static",)),
                 "planning": frozenset(("static",)), "release": frozenset(("static",))}
COMMAND_SCOPES = {"version": "planning", "sprint-test": "test", "sprint-aiauto-test": "test",
    **{name: "planning" for name in ("sprint-requirements", "sprint-design", "sprint-plan", "sprint-selftest")}}
OPTIONAL_ACTIONS = frozenset(("document", "related-test", "review", "full-cvl", "docs-audit", "full-regression",
    "migration-rehearsal", "deployment-tool-development", "commit", "push", "deploy", "live-tests", "equivalent-evidence"))
ACTION_ALIASES = {"fullCVL": "full-cvl", "docsAudit": "docs-audit", "fullRegression": "full-regression",
                  "migrationRehearsal": "migration-rehearsal", "deploymentToolDevelopment": "deployment-tool-development",
                  "liveTests": "live-tests", "targeted-tests": "related-test"}


def canonical_action(action):
    return ACTION_ALIASES.get(action, action)

ACTIONS = BASE_ACTIONS | OPTIONAL_ACTIONS
# 公开组合只由用户本轮显式命令启用，entry 或 formal 身份从不推导这些权限。
COMMAND_ACTIONS = {
    "sprint-dev": (), "sprint-start": ("document",), "sprint-bugfix": (), "sprint-close": (),
    "version": ("document", "docs-audit"),
    **{name: ("document",) for name in ("sprint-requirements", "sprint-design", "sprint-plan", "sprint-selftest")},
    "sprint-test": ("related-test", "review", "full-cvl"),
    "sprint-full": ("document", "related-test", "review", "full-cvl", "docs-audit"),
    "sprint-batch": ("document", "related-test", "review", "full-cvl", "docs-audit"),
    "sprint-autopilot": ("document", "related-test", "review", "full-cvl", "docs-audit",
                         "commit", "push", "deploy", "live-tests", "full-regression"),
    "sprint-aiauto-test": ("live-tests", "full-regression"),
}
# 已有 autopilot_tick_flags 的公开裁剪选项只减权限；没有新造参数或安装权限。
COMMAND_OPTION_REMOVALS = {"sprint-autopilot": {
    "--skip-deploy": ("deploy",), "--skip-aiauto-test": ("live-tests", "full-regression"),
    "--skip-dev": ("implement", "document", "related-test", "review", "full-cvl", "docs-audit", "commit", "push"),
}}


def command_grants(source):
    command = source["command"].lstrip("/")
    grants = set(COMMAND_ACTIONS[command])
    options = source.get("options", [])
    if not isinstance(options, list) or any(not isinstance(item, str) for item in options):
        raise PolicyError("UNAUTHORIZED", "命令 options 必须为用户显式选项数组")
    if command == "version" and set(options) & {"--release", "--no-tag"}:
        grants.update(("commit", "push"))
    if "--cascade-now" in options and command in ("sprint-dev", "sprint-bugfix", "sprint-full", "sprint-batch"):
        grants.add("document")
    for option in options:
        grants.difference_update(COMMAND_OPTION_REMOVALS.get(command, {}).get(option, ()))
    return grants
DEFAULT_BUDGET = {"scanned_files": 2000, "selected_tests": 40, "processes": 24,
                  "agents": 2, "retries": 2, "elapsed_seconds": 300}
# 仅本轮明确命令采用公开职责预算；formal/entry 标签或旧模板配置从不启用。
COMMAND_BUDGETS = {
    "version": {"scanned_files": 10000, "selected_tests": 40, "processes": 128,
                "agents": 8, "retries": 4, "elapsed_seconds": 1800},
    "sprint-test": {"scanned_files": 10000, "selected_tests": 300, "processes": 128,
                    "agents": 8, "retries": 4, "elapsed_seconds": 1800},
    "sprint-full": {"scanned_files": 20000, "selected_tests": 1000, "processes": 256,
                    "agents": 16, "retries": 6, "elapsed_seconds": 3600},
    "sprint-batch": {"scanned_files": 50000, "selected_tests": 5000, "processes": 1024,
                     "agents": 64, "retries": 12, "elapsed_seconds": 7200},
    "sprint-autopilot": {"scanned_files": 50000, "selected_tests": 5000, "processes": 1024,
                         "agents": 64, "retries": 12, "elapsed_seconds": 7200},
    # 两路并行共享累计执行时间；单测进程仍由 runner 保持 3600 秒上限。
    "sprint-aiauto-test": {"scanned_files": 50000, "selected_tests": 10000, "processes": 256,
                           "agents": 16, "retries": 6, "elapsed_seconds": 7200},
}
STATUSES = frozenset(("PASS", "FAIL", "TOOL_ERROR", "ENV_UNAVAILABLE", "UNVERIFIED",
                     "NOT_REQUESTED", "UNAUTHORIZED", "BUDGET_EXCEEDED"))
POLICY_FIELDS = ("task_scope", "allowed_actions", "verification_level", "authorization_source", "execution_budget")


class PolicyError(ValueError):
    def __init__(self, status, message, **details):
        super().__init__(f"{status}: {message}")
        self.status = status
        self.details = details


def _text(value):
    return (isinstance(value, str) and bool(value.strip()) and not value.strip().startswith(("<", "{{"))
            and value.strip().lower() not in ("template", "placeholder", "default", "null", "auto"))


def validate_source(source):
    """只接受可追溯用户输入；旧模板开关和占位授权不能迁移为 grant。"""
    if not isinstance(source, dict) or not _text(source.get("request_id")):
        raise PolicyError("UNAUTHORIZED", "授权缺少本轮用户请求标识 request_id")
    if "persistent" in source:
        if type(source["persistent"]) is not bool:
            raise PolicyError("UNAUTHORIZED", "persistent 必须是明确布尔选择")
        if source["persistent"] and not _text(source.get("text")):
            raise PolicyError("UNAUTHORIZED", "持续授权必须保留用户明确持续执行的原文")
    kind = source.get("kind")
    if kind == "explicit-command":
        command = str(source.get("command", "")).lstrip("/")
        if command not in COMMAND_ACTIONS:
            raise PolicyError("UNAUTHORIZED", "命令没有公开授权组合")
    elif kind == "user-text":
        if not _text(source.get("text")):
            raise PolicyError("UNAUTHORIZED", "user-text 授权必须保留本轮用户原文")
    elif kind == "project-policy":
        if source.get("user_selected") is not True or not _text(source.get("text")):
            raise PolicyError("UNAUTHORIZED", "项目策略未记录明确用户选择")
        if "command" in source and (not isinstance(source["command"], str) or
                                     source["command"].lstrip("/") not in COMMAND_ACTIONS):
            raise PolicyError("UNAUTHORIZED", "已选策略的 command 必须指向已公开命令")
    else:
        raise PolicyError("UNAUTHORIZED", "授权来源必须是 user-text、explicit-command 或已选 project-policy")
    return copy.deepcopy(source)


def _actions(values):
    if (not isinstance(values, (list, tuple, set, frozenset)) or
            any(not isinstance(v, str) or canonical_action(v) not in ACTIONS for v in values)):
        raise PolicyError("UNAUTHORIZED", "未知动作，拒绝隐式扩大权限")
    return {canonical_action(value) for value in values}


def normalize_budget(values=None, base=None):
    result = dict(DEFAULT_BUDGET if base is None else base)
    if values is None:
        return result
    if not isinstance(values, dict) or set(values) - set(DEFAULT_BUDGET):
        raise PolicyError("BUDGET_EXCEEDED", "预算包含未知资源")
    for resource, value in values.items():
        if (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
                or value < 0 or (resource != "elapsed_seconds" and type(value) is not int)):
            raise PolicyError("BUDGET_EXCEEDED", f"{resource} 必须是有限非负预算")
        result[resource] = value
    return result


def verification_level(actions):
    if "full-regression" in actions:
        return "full"
    if set(actions) & {"full-cvl", "docs-audit", "live-tests"}:
        return "extended"
    if "related-test" in actions:
        return "targeted"
    if "review" in actions:
        return "review"
    return "static"


def policy_fields(root, paths, acceptance, *, additional_grants=None, authorization_source=None,
                  execution_budget=None, task_scope=None):
    from aidp_config import read_execution_policy
    command = (str((authorization_source or {}).get("command", "")).lstrip("/")
               if isinstance(authorization_source, dict) else "")
    release_requested = (command == "version" and isinstance(authorization_source, dict) and
                         authorization_source.get("kind") == "explicit-command" and
                         any(option in authorization_source.get("options", []) for option in ("--release", "--no-tag")))
    inferred_scope = "release" if release_requested else COMMAND_SCOPES.get(command, "development")
    kind = task_scope or inferred_scope
    if release_requested and kind != "release":
        raise PolicyError("UNAUTHORIZED", "显式发布参数与 task_scope 冲突")
    if kind not in SCOPE_ACTIONS:
        raise PolicyError("UNAUTHORIZED", "未知 task_scope")
    actions, sources, budget = set(SCOPE_ACTIONS[kind]), [], dict(DEFAULT_BUDGET)
    configured = read_execution_policy(root)
    if configured and (not configured["authorization_source"].get("command") or
                       configured["authorization_source"]["command"].lstrip("/") == command):
        chosen = validate_source(configured["authorization_source"])
        selected = _actions(configured.get("allowed_actions", []))
        actions.update(selected)
        sources.append(dict(chosen, actions=sorted(selected)))
        budget = normalize_budget(configured.get("execution_budget"), budget)
    if additional_grants or authorization_source:
        source = validate_source(authorization_source)
        grants = _actions(additional_grants or [])
        if source["kind"] == "explicit-command":
            public = command_grants(source)
            if grants - public - BASE_ACTIONS:
                raise PolicyError("UNAUTHORIZED", "额外动作超出公开命令职责，需要独立 user-text 授权")
            grants.update(public)
            budget = dict(COMMAND_BUDGETS.get(source["command"].lstrip("/"), budget))
        actions.update(grants)
        if source["kind"] == "explicit-command":
            for option in source.get("options", []):
                actions.difference_update(COMMAND_OPTION_REMOVALS.get(source["command"].lstrip("/"), {}).get(option, ()))
        sources.append(dict(source, actions=sorted(grants)))
    new_budget = normalize_budget(execution_budget, budget)
    if any(new_budget[key] > budget[key] for key in budget) and not authorization_source:
        raise PolicyError("UNAUTHORIZED", "扩大执行预算需要本轮明确授权")
    return {"task_scope": {"kind": kind, "paths": list(paths), "acceptance": list(acceptance)},
            "allowed_actions": sorted(actions), "verification_level": verification_level(actions),
            "authorization_source": sources, "execution_budget": new_budget}


def validate_policy(ctx):
    actions = _actions(ctx.get("allowed_actions", []))
    scope = ctx.get("task_scope", {})
    kind = scope.get("kind") if isinstance(scope, dict) else None
    if kind not in SCOPE_ACTIONS or sorted(actions) != ctx.get("allowed_actions"):
        raise PolicyError("UNAUTHORIZED", "上下文缺少规范任务范围或权限")
    if ctx.get("verification_level") != verification_level(actions):
        raise PolicyError("UNAUTHORIZED", "核验等级与显式动作不一致")
    if scope != {"kind": kind, "paths": ctx["write_set"], "acceptance": ctx["acceptance"]}:
        raise PolicyError("UNAUTHORIZED", "task_scope 与冻结写集/验收目标不一致")
    if normalize_budget(ctx.get("execution_budget")) != ctx.get("execution_budget"):
        raise PolicyError("BUDGET_EXCEEDED", "执行预算必须列明全部资源")
    sources = ctx.get("authorization_source")
    if not isinstance(sources, list):
        raise PolicyError("UNAUTHORIZED", "授权来源必须为记录列表")
    authorized = set(SCOPE_ACTIONS[kind])
    for source in sources:
        validate_source(source)
        granted = _actions(source.get("actions", []))
        if source["kind"] == "explicit-command" and granted - command_grants(source) - BASE_ACTIONS:
            raise PolicyError("UNAUTHORIZED", "授权记录超出公开命令职责")
        authorized.update(granted)
    if not actions <= authorized:
        raise PolicyError("UNAUTHORIZED", "动作缺少可追溯用户授权")


def _context(root, ctx):
    from entry_context import load_context, validate_context
    root = Path(root).resolve()
    return validate_context(root, ctx) if isinstance(ctx, dict) else load_context(root, ctx)


def require_action(ctx, action):
    """dict 带 root；路径从文件读 root，再通过唯一运行目录及 revision 验真。"""
    if isinstance(ctx, dict):
        root = ctx.get("root", ".")
    else:
        try:
            root = json.loads(Path(ctx).read_text(encoding="utf-8"))["root"]
        except (OSError, ValueError, KeyError) as exc:
            raise PolicyError("UNAUTHORIZED", "无法读取执行上下文") from exc
    current = _context(root, ctx)
    action = canonical_action(action)
    _budget_owner(Path(root).resolve(), current)
    if action not in ACTIONS or action not in current["allowed_actions"]:
        raise PolicyError("UNAUTHORIZED", f"动作 {action} 未获本任务授权", action=action)
    return current


def _budget_owner(root, ctx):
    from entry_context import load_context, _context_path, identity_hash
    current = ctx
    seen = set()
    while "parent_task_id" in current:
        if current["task_id"] in seen:
            raise PolicyError("UNAUTHORIZED", "父任务循环")
        seen.add(current["task_id"])
        parent = load_context(root, _context_path(root, current["parent_task_id"]))
        if current["parent_identity_hash"] != identity_hash(parent):
            raise PolicyError("UNAUTHORIZED", "父任务策略已变化，请重新继承当前授权")
        if not set(current["allowed_actions"]) <= set(parent["allowed_actions"]):
            raise PolicyError("UNAUTHORIZED", "子任务不得扩展父任务权限")
        current = parent
    return current


def _budget_state(root, owner):
    from entry_context import _context_path, _safe_inside
    path = _safe_inside(root, _context_path(root, owner["task_id"]).with_name("budget.json"))
    if not path.exists():
        return path, {"task_id": owner["task_id"], "used": {key: 0 for key in DEFAULT_BUDGET},
                      "outcomes": [], "reservations": []}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        if state["task_id"] != owner["task_id"] or set(state["used"]) != set(DEFAULT_BUDGET):
            raise ValueError("budget identity/resources mismatch")
        normalize_budget(state["used"])
        if not isinstance(state["outcomes"], list) or not isinstance(state["reservations"], list):
            raise ValueError("budget journal malformed")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise PolicyError("UNVERIFIED", f"预算记录不可读取：{exc}") from exc
    return path, state


def reserve_budget(root, ctx, resource, cost=1, input_hash=None, *, action=None):
    """预留累计资源；锁内检查和扣减，多个 Agent/子任务不能各取一份预算。

    elapsed_seconds 预留计划最长执行时间，调用方必须把同一上限给进程 timeout。
    不退款避免并发抢占和反复启动绕过累计上限。扫描/选测按实际条目数预留。
    """
    from entry_context import _task_lock, _context_path, _atomic_json
    root = Path(root).resolve()
    current = _context(root, ctx)
    action = canonical_action(action)
    if action:
        require_action(current, action)
    if resource not in DEFAULT_BUDGET:
        raise PolicyError("BUDGET_EXCEEDED", f"未知资源 {resource}")
    normalize_budget({resource: cost})
    if input_hash is not None and not re.fullmatch(r"[0-9a-f]{64}", str(input_hash)):
        raise PolicyError("UNVERIFIED", "input_hash 必须是实际输入 SHA256")
    owner = _budget_owner(root, current)
    with _task_lock(root, _context_path(root, owner["task_id"])) as locked:
        current = _context(root, ctx)
        _budget_owner(root, current)
        path, state = _budget_state(root, locked)
        if input_hash:
            failure = next((row for row in reversed(state["outcomes"])
                if row.get("input_hash") == input_hash and (action is None or row.get("action") == action)
                and row.get("status") in ("TOOL_ERROR", "ENV_UNAVAILABLE")), None)
            if failure:
                raise PolicyError(failure["status"], "同根因同输入的工具失败已终止，保留原错误，不自动换证据路径",
                                  original_error=failure)
        used = state["used"][resource]
        # 子任务可以缩小上限，但任何子任务的消耗仍计入父任务总额。
        limit = min(locked["execution_budget"][resource], current["execution_budget"][resource])
        if used + cost > limit:
            raise PolicyError("BUDGET_EXCEEDED", f"{resource}: {used} + {cost} > {limit}",
                              resource=resource, used=used, cost=cost, limit=limit)
        state["used"][resource] += cost
        reservation_id = str(uuid.uuid4())
        state["reservations"].append({"reservation_id": reservation_id, "resource": resource, "cost": cost,
                                      "task_id": current["task_id"], "revision": current["revision"],
                                      "input_hash": input_hash, "action": canonical_action(action), "at": time.time()})
        _atomic_json(root, path, state)
        return {"status": "RESERVED", "reservation_id": reservation_id,
                "resource": resource, "cost": cost, "used": state["used"][resource],
                "limit": limit, "remaining": limit - state["used"][resource], "budget_task_id": locked["task_id"]}


def settle_elapsed(root, ctx, reservation, elapsed_seconds):
    """一次性结算时间预留为真实工作耗时；用户等待/队列时间不计入预算。"""
    from entry_context import _task_lock, _context_path, _atomic_json
    root = Path(root).resolve()
    current = _context(root, ctx)
    normalize_budget({"elapsed_seconds": elapsed_seconds})
    owner = _budget_owner(root, current)
    with _task_lock(root, _context_path(root, owner["task_id"])) as locked:
        path, state = _budget_state(root, locked)
        row = next((item for item in state["reservations"]
                    if item.get("reservation_id") == reservation.get("reservation_id")), None)
        if row is None or row["resource"] != "elapsed_seconds" or row["task_id"] != current["task_id"]:
            raise PolicyError("UNVERIFIED", "无法结算非本任务时间预留")
        if "actual_cost" in row:
            if row["actual_cost"] != elapsed_seconds:
                raise PolicyError("UNVERIFIED", "同一预留不可重复按不同耗时结算")
            return dict(row)
        state["used"]["elapsed_seconds"] += elapsed_seconds - row["cost"]
        row["actual_cost"] = elapsed_seconds
        _atomic_json(root, path, state)
        if state["used"]["elapsed_seconds"] > locked["execution_budget"]["elapsed_seconds"]:
            raise PolicyError("BUDGET_EXCEEDED", "实际执行耗时超限", used=state["used"]["elapsed_seconds"])
        return dict(row)


def record_outcome(root, ctx, action, status, input_hash, *, root_cause=None, evidence=None):
    """保存原始错误或结果；PASS 记录本身不是完成证据，完成门另验真实命令证据。"""
    from entry_context import _task_lock, _context_path, _atomic_json
    root = Path(root).resolve()
    current = _context(root, ctx)
    action = canonical_action(action)
    if status not in STATUSES or action not in ACTIONS:
        raise PolicyError("UNVERIFIED", "未知执行状态或动作")
    if not re.fullmatch(r"[0-9a-f]{64}", str(input_hash)):
        raise PolicyError("UNVERIFIED", "结果必须绑定实际输入 SHA256")
    owner = _budget_owner(root, current)
    with _task_lock(root, _context_path(root, owner["task_id"])) as locked:
        _context(root, ctx)
        path, state = _budget_state(root, locked)
        row = {"task_id": current["task_id"], "revision": current["revision"], "action": action,
               "status": status, "input_hash": input_hash, "root_cause": root_cause,
               "evidence": evidence, "at": time.time()}
        state["outcomes"].append(row)
        _atomic_json(root, path, state)
        return row


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("require-action", "reserve-budget", "record-outcome", "settle-elapsed"):
        item = sub.add_parser(name)
        item.add_argument("--root", default=".")
        item.add_argument("--execution-context", required=True)
        item.add_argument("--json", action="store_true")
        item.add_argument("--action", required=name in ("require-action", "record-outcome"))
        if name == "reserve-budget":
            item.add_argument("--resource", choices=tuple(DEFAULT_BUDGET), required=True)
            item.add_argument("--cost", type=float, default=1)
        if name in ("reserve-budget", "record-outcome"):
            item.add_argument("--input-hash", required=True)
        if name == "settle-elapsed":
            item.add_argument("--reservation-id", required=True)
            item.add_argument("--elapsed-seconds", type=float, required=True)
        if name == "record-outcome":
            item.add_argument("--status", choices=tuple(sorted(STATUSES)), required=True)
            item.add_argument("--root-cause")
            item.add_argument("--evidence-json", type=json.loads)
    args = parser.parse_args(argv)
    try:
        ctx = _context(args.root, args.execution_context)
        if args.command == "require-action":
            current = require_action(ctx, args.action)
            result = {"status": "AUTHORIZED", "action": canonical_action(args.action),
                      "task_id": current["task_id"], "revision": current["revision"]}
        elif args.command == "reserve-budget":
            cost = args.cost if args.resource == "elapsed_seconds" else int(args.cost)
            if cost != args.cost:
                raise PolicyError("BUDGET_EXCEEDED", "计数预算必须是整数")
            result = reserve_budget(args.root, ctx, args.resource, cost, args.input_hash, action=args.action)
        elif args.command == "settle-elapsed":
            settled = settle_elapsed(args.root, ctx, {"reservation_id": args.reservation_id}, args.elapsed_seconds)
            result = dict(settled, status="SETTLED")
        else:
            result = record_outcome(args.root, ctx, canonical_action(args.action), args.status, args.input_hash,
                                    root_cause=args.root_cause, evidence=args.evidence_json)
        code = 0
    except (ValueError, OSError) as exc:
        result = {"status": getattr(exc, "status", "UNVERIFIED"), "error": str(exc),
                  "details": getattr(exc, "details", {})}
        code = 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
