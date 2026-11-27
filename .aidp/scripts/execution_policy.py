#!/usr/bin/env python3
"""入口上下文的最小授权与共享执行预算；没有独立任务身份或默认安装权限。

调用方在实际工作前 require_action/reserve_budget，工作后 record_outcome。
预算和失败记录沿用 entry_context 的任务锁；所有子任务消费根任务同一份余额。
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import re
import time
import uuid

BASE_ACTIONS = frozenset(("implement", "static"))
SCOPE_ACTIONS = {"development": BASE_ACTIONS | {"related-test"}, "review": frozenset(), "test": frozenset(("static",)),
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
    "sprint-dev": ("related-test",), "sprint-start": ("document",), "sprint-bugfix": ("related-test",), "sprint-close": (),
    "version": ("document", "docs-audit"),
    **{name: ("document",) for name in ("sprint-requirements", "sprint-design", "sprint-plan", "sprint-selftest")},
    "sprint-test": ("related-test", "review", "full-cvl"),
    "sprint-full": ("document", "related-test", "review", "full-cvl", "docs-audit"),
    "sprint-batch": ("document", "related-test", "review", "full-cvl", "docs-audit"),
    "sprint-autopilot": ("document", "related-test", "review", "full-cvl", "docs-audit",
                         "commit", "push", "deploy", "live-tests", "full-regression"),
    "sprint-aiauto-test": ("live-tests",),
}
# 已有 autopilot_tick_flags 的公开裁剪选项只减权限；没有新造参数或安装权限。
COMMAND_OPTION_REMOVALS = {"sprint-autopilot": {
    "--skip-deploy": ("deploy",), "--skip-aiauto-test": ("live-tests", "full-regression"),
    "--skip-dev": ("implement", "document", "related-test", "review", "full-cvl", "docs-audit", "commit", "push", "deploy"),
}}


FULL_HINT = "版本全量只能由真实 autopilot 测试编排经 fork-test-build --manifest 交接；请经 autopilot 测试编排交接"


def _autopilot_source(source):
    return (isinstance(source, dict) and source.get("kind") in ("explicit-command", "project-policy")
            and str(source.get("command", "")).lstrip("/") == "sprint-autopilot")


def reject_direct_full(grants, source):
    """用户文本、--grant、命令名都不是版本全量来源；只有 autopilot 根与其 fork 子任务持有。"""
    if "full-regression" in set(canonical_action(g) for g in grants) and not _autopilot_source(source):
        raise PolicyError("UNAUTHORIZED", "full-regression 不可由用户文本/--grant/独立命令授予；" + FULL_HINT)


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
# 预算分三类（口径单一信源）：
#   并发硬限  agents/processes：同时运行的上限，由 acquire_slot 强制；used 里只是累计启动数（统计/告警），
#             父任务、子 Agent、嵌套流程共用根任务同一并发池。
#   总量软限  scanned_files/elapsed_seconds：默认只预警并按降级顺序缩小输入，不因超额停止；
#             仅当用户显式写入（含旧配置）、autopilot 无人值守链路或部署/推送等高风险动作时才阻断。
#   固定硬限  selected_tests/retries：范围与失败风暴护栏，始终阻断。
CONCURRENT_RESOURCES = ("agents", "processes")
SOFT_RESOURCES = ("scanned_files", "elapsed_seconds")
ALWAYS_HARD_RESOURCES = ("selected_tests", "retries")
HIGH_RISK_ACTIONS = frozenset(("deploy", "push", "live-tests", "migration-rehearsal", "full-regression"))
DEGRADE_STEPS = ("narrow-scope", "use-cache", "reduce-repeated-evidence", "ask-user")
SOFT_WARN_RATIO = 0.8
DEFAULT_BUDGET = {"scanned_files": 2000, "selected_tests": 40, "processes": 4,
                  "agents": 2, "retries": 2, "elapsed_seconds": 300}
# 仅本轮明确命令采用公开职责预算；formal/entry 标签或旧模板配置从不启用。
COMMAND_BUDGETS = {
    "version": {"scanned_files": 10000, "selected_tests": 40, "processes": 4,
                "agents": 4, "retries": 4, "elapsed_seconds": 1800},
    "sprint-test": {"scanned_files": 10000, "selected_tests": 300, "processes": 8,
                    "agents": 4, "retries": 4, "elapsed_seconds": 1800},
    "sprint-full": {"scanned_files": 20000, "selected_tests": 1000, "processes": 8,
                    "agents": 4, "retries": 6, "elapsed_seconds": 3600},
    "sprint-batch": {"scanned_files": 50000, "selected_tests": 5000, "processes": 8,
                     "agents": 6, "retries": 12, "elapsed_seconds": 7200},
    "sprint-autopilot": {"scanned_files": 50000, "selected_tests": 5000, "processes": 8,
                         "agents": 6, "retries": 12, "elapsed_seconds": 7200},
    # 两路并行共享累计执行时间；单测进程仍由 runner 保持 3600 秒上限。
    "sprint-aiauto-test": {"scanned_files": 50000, "selected_tests": 10000, "processes": 8,
                           "agents": 4, "retries": 6, "elapsed_seconds": 7200},
}
# scanned_files 口径：同一路径、同一内容的重复读取按去重计量（unique 路径只计一次），缓存命中不计费；
# 每段扫描须区分 实际内容读取(content_reads) / 仅元数据(metadata_entries) / 缓存命中(cache_hits) /
# 外部工具未测量(tool_objects，计为 unknown，不并入扫描数也不伪称为零)。见 charge_content_reads。
SCAN_SEMANTICS = {"scanned_files": "distinct_content_paths_read_deduplicated_by_path_and_content",
                  "unique_files": "distinct_content_paths_per_validation",
                  "metadata_entries": "metadata_only_entries_visited",
                  "cache_hits": "content_reads_avoided_by_valid_cache",
                  "tool_objects": "external_tool_selected_objects_not_measured_io",
                  "deduplicated_reads": "repeat_reads_of_same_path_not_charged",
                  "unknown_tool_io": "external_tool_io_not_measured_reported_as_unknown_never_zero"}
VALIDATION_STAGES = ("pre_evidence", "command", "post_evidence", "cleanup")
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


VERIFICATION_ACTIONS = frozenset(("static", "related-test", "review", "full-cvl", "docs-audit",
    "full-regression", "live-tests", "migration-rehearsal", "equivalent-evidence"))
RESTRICTIONS = {
    "analysis-only": ACTIONS - {"review"},
    "modify-only": ACTIONS - {"implement", "document"},
    "skip-verification": VERIFICATION_ACTIONS,
}


def source_removals(source):
    """例外只消费有原文的明确来源；支持只跳过某项，不把测试缺失当授权。"""
    removed = set(RESTRICTIONS.get(source.get("restriction"), ()))
    removed.update(source.get("skip_actions", []))
    command = str(source.get("command", "")).lstrip("/")
    for option in source.get("options", []):
        removed.update(COMMAND_OPTION_REMOVALS.get(command, {}).get(option, ()))
    return removed


def completion_restrictions(ctx):
    """按来源顺序还原仍有效的减权；后续明确追加 grant 可恢复指定动作。"""
    removed = set()
    for source in ctx.get("authorization_source", []):
        removed.difference_update(source.get("actions", []))
        removed.update(source_removals(source))
    return removed


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
    if "restriction" in source or "skip_actions" in source:
        if not _text(source.get("text")):
            raise PolicyError("UNAUTHORIZED", "减权例外必须保留用户明确边界的原文")
        if "restriction" in source and source["restriction"] not in RESTRICTIONS:
            raise PolicyError("UNAUTHORIZED", "未知任务限制")
        skipped = source.get("skip_actions", [])
        if (not isinstance(skipped, list) or any(not isinstance(value, str) or value not in VERIFICATION_ACTIONS
                                                for value in skipped)):
            raise PolicyError("UNAUTHORIZED", "skip_actions 只能逐项跳过已知核验动作")
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


def adaptive_defaults(root):
    """按项目规模自适应的软阈值（scanned_files / elapsed_seconds），不再用固定 2000 / 300。

    只读一次 git 文件清单（project_inventory.quick_counts），不读文件内容；git 不可用时回退固定下限。
    公式：scanned_files = max(2000, 3×文件数)，上限 50000；elapsed_seconds = 300 + 文件数÷10，上限 3600。
    只影响软限；selected_tests/retries/并发硬限不随规模放宽，也不改变任何动作授权。
    """
    floor = {key: DEFAULT_BUDGET[key] for key in SOFT_RESOURCES}
    try:
        from project_inventory import quick_counts
        counts = quick_counts(root)
    except (ImportError, OSError, ValueError):
        counts = None
    if not counts:
        return floor
    files = counts["files"]
    return {"scanned_files": int(min(50000, max(floor["scanned_files"], 3 * files))),
            "elapsed_seconds": int(min(3600, max(floor["elapsed_seconds"], 300 + files // 10)))}


def _source_budget_keys(source):
    keys = source.get("budget_keys")
    if keys is not None:
        return set(keys) if isinstance(keys, list) else set()
    # 旧记录没有 budget_keys：用户明确选择的项目策略 / 修订中写过 execution_budget 的值一律按硬上限，不静默放宽。
    if source.get("kind") == "project-policy" or "execution_budget" in source:
        return set(SOFT_RESOURCES)
    return set()


def hard_resources(ctx):
    """该任务中会阻断的总量资源集合（并发资源恒由 acquire_slot 强制，不在此列）。

    阻断 = 固定硬限 ∪ 用户显式写入的键（含旧配置）∪ 低于默认值的限额（用户收紧）；
    autopilot 无人值守来源下全部阻断。其余总量资源（默认值/自适应值）只预警，不停止。
    """
    sources = ctx.get("authorization_source") or []
    if isinstance(sources, dict):
        sources = [sources]
    if any(_autopilot_source(source) for source in sources if isinstance(source, dict)):
        return set(ALWAYS_HARD_RESOURCES) | set(SOFT_RESOURCES)
    hard = set(ALWAYS_HARD_RESOURCES)
    for source in sources:
        if isinstance(source, dict):
            hard |= _source_budget_keys(source)
    for key in SOFT_RESOURCES:
        value = (ctx.get("execution_budget") or {}).get(key)
        if value is not None and value < DEFAULT_BUDGET[key]:
            hard.add(key)
    return hard


def is_blocking(contexts, resource, action=None):
    """resource 超额时是否阻断：任一上下文（根/当前）判为硬，或动作属高风险。"""
    if resource in CONCURRENT_RESOURCES:
        return True
    if canonical_action(action) in HIGH_RISK_ACTIONS:
        return True
    return any(resource in hard_resources(ctx) for ctx in contexts)


def soft_advice(state, resource):
    """软限触发后的固定降级顺序：缩小范围 → 使用缓存 → 减少重复取证 → 确实无法继续才请用户决策。

    只有「超限后始终没有新结果产出」才逐级升级；有进展就停在当前一级继续工作，且从不停止任务。
    """
    events = [row for row in state.get("soft_events", []) if row.get("resource") == resource]
    outcomes = len(state.get("outcomes", []))
    stalled = 0
    for row in reversed(events):
        if row.get("outcomes_seen") != outcomes:
            break
        stalled += 1
    index = min(max(stalled - 1, 0), len(DEGRADE_STEPS) - 1)
    return {"order": list(DEGRADE_STEPS), "step": DEGRADE_STEPS[index], "stalled_events": stalled,
            "stops_task": False,
            "message": "软限已超出但可继续：先" + {"narrow-scope": "缩小输入范围", "use-cache": "复用有效缓存",
                       "reduce-repeated-evidence": "去除重复取证", "ask-user": "仅在确实无法继续时请用户决策"}[DEGRADE_STEPS[index]]}


def _soft_event(state, resource, used, limit, **extra):
    events = state.setdefault("soft_events", [])
    events.append(dict({"resource": resource, "used": used, "limit": limit, "at": time.time(),
                        "outcomes_seen": len(state.get("outcomes", []))}, **extra))
    del events[:-100]
    return dict(resource=resource, used=used, limit=limit, advice=soft_advice(state, resource))


def _limits(locked, current):
    return {key: min(locked["execution_budget"][key], current["execution_budget"][key]) for key in DEFAULT_BUDGET}


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
                  execution_budget=None, task_scope=None, entry_name=None):
    from aidp_config import read_execution_policy
    command = (str((authorization_source or {}).get("command", "")).lstrip("/")
               if isinstance(authorization_source, dict) else "")
    release_requested = (command == "version" and isinstance(authorization_source, dict) and
                         authorization_source.get("kind") == "explicit-command" and
                         any(option in authorization_source.get("options", []) for option in ("--release", "--no-tag")))
    scope_entry = command or {"test": "sprint-test"}.get(entry_name, entry_name)
    inferred_scope = "release" if release_requested else COMMAND_SCOPES.get(scope_entry, "development")
    kind = task_scope or inferred_scope
    if release_requested and kind != "release":
        raise PolicyError("UNAUTHORIZED", "显式发布参数与 task_scope 冲突")
    if kind not in SCOPE_ACTIONS:
        raise PolicyError("UNAUTHORIZED", "未知 task_scope")
    actions, sources, budget = set(SCOPE_ACTIONS[kind]), [], {**DEFAULT_BUDGET, **adaptive_defaults(root)}
    configured = read_execution_policy(root)
    project_budget = None
    if configured and (not configured["authorization_source"].get("command") or
                       configured["authorization_source"]["command"].lstrip("/") == command):
        chosen = validate_source(configured["authorization_source"])
        selected = _actions(configured.get("allowed_actions", []))
        reject_direct_full(selected, chosen)
        actions.update(selected)
        actions.difference_update(source_removals(chosen))
        sources.append(dict(chosen, actions=sorted(selected),
                            budget_keys=sorted(configured.get("execution_budget") or {})))
        project_budget = configured.get("execution_budget")
        budget = normalize_budget(project_budget, budget)
    if additional_grants or authorization_source:
        source = validate_source(authorization_source)
        grants = _actions(additional_grants or [])
        reject_direct_full(grants, source)
        if source["kind"] == "explicit-command":
            public = command_grants(source)
            if grants - public - BASE_ACTIONS:
                raise PolicyError("UNAUTHORIZED", "额外动作超出公开命令职责，需要独立 user-text 授权")
            grants.update(public)
            # 命令职责预算只补缺省，不能覆盖项目已明确选择的限额（含 0）。
            budget = normalize_budget(project_budget, COMMAND_BUDGETS.get(source["command"].lstrip("/"), budget))
        actions.update(grants)
        actions.difference_update(source_removals(source))
        sources.append(dict(source, actions=sorted(grants), budget_keys=[]))
    new_budget = normalize_budget(execution_budget, budget)
    if any(new_budget[key] > budget[key] for key in budget) and not authorization_source:
        raise PolicyError("UNAUTHORIZED", "扩大执行预算需要本轮明确授权")
    if execution_budget and sources:
        # 用户显式给出的键视为硬上限；只记键名，不改授权。
        sources[-1]["budget_keys"] = sorted(set(sources[-1].get("budget_keys", [])) | set(execution_budget))
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
        authorized.difference_update(source_removals(source))
    if not actions <= authorized:
        raise PolicyError("UNAUTHORIZED", "动作缺少可追溯用户授权")


def _context(root, ctx):
    from entry_context import load_context, validate_context
    root = Path(root).resolve()
    return validate_context(root, ctx) if isinstance(ctx, dict) else load_context(root, ctx)


def _loaded(ctx):
    if isinstance(ctx, dict):
        root = ctx.get("root", ".")
    else:
        try:
            root = json.loads(Path(ctx).read_text(encoding="utf-8"))["root"]
        except (OSError, ValueError, KeyError) as exc:
            raise PolicyError("UNAUTHORIZED", "无法读取执行上下文") from exc
    return root, _context(root, ctx)


def require_action(ctx, action):
    """dict 带 root；路径从文件读 root，再通过唯一运行目录及 revision 验真。真正执行的唯一入口。"""
    root, current = _loaded(ctx)
    action = canonical_action(action)
    _budget_owner(Path(root).resolve(), current)
    if action not in ACTIONS or action not in current["allowed_actions"]:
        raise PolicyError("UNAUTHORIZED", f"动作 {action} 未获本任务授权", action=action)
    if action == "full-regression":
        validate_test_binding(root, current, current["version"], current.get("build_id"))
    return current


def require_delegable(ctx, action):
    """只判定“有资格委派”：授权持有+父链/revision 验真，不做 binding，⛔ 不得用于真正执行。
    full-regression 仅 autopilot 来源的根持有；执行必须经 fork-test-build 子上下文的 require_action。"""
    root, current = _loaded(ctx)
    action = canonical_action(action)
    _budget_owner(Path(root).resolve(), current)
    if current.get("mode") == "light" and current.get("parent_task_id"):
        raise PolicyError("UNAUTHORIZED", "light 子任务仅执行已委派动作，不得再次委派", action=action)
    if action not in ACTIONS or action not in current["allowed_actions"]:
        raise PolicyError("UNAUTHORIZED", f"动作 {action} 未获本任务授权，无权委派", action=action)
    if action == "full-regression" and not any(_autopilot_source(source) for source in current["authorization_source"]):
        raise PolicyError("UNAUTHORIZED", "full-regression 无 autopilot 来源，不可委派；" + FULL_HINT, action=action)
    return current


def test_manifest_binding(root, version, build, manifest):
    """复用既有版本 build plan，冻结验收基线与正式用例集合的文件摘要。"""
    from entry_context import _safe_inside
    root = Path(root).resolve()
    if not isinstance(manifest, (str, Path)) or not str(manifest):
        raise PolicyError("UNAUTHORIZED", "版本全量必须提供真实 --manifest build plan")
    path = Path(manifest)
    path = _safe_inside(root, path if path.is_absolute() else root / path)
    try:
        raw = path.read_bytes()
        plan = json.loads(raw)
    except (OSError, ValueError) as exc:
        raise PolicyError("UNAUTHORIZED", "版本测试 manifest 不可读取") from exc
    if (not isinstance(plan, dict) or plan.get("version") != version or plan.get("build") != build
            or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", str(plan.get("commit", "")))):
        raise PolicyError("UNAUTHORIZED", "版本测试 manifest 未绑定当前 version/build/commit")
    baseline = plan.get("acceptance_baseline")
    if (not isinstance(baseline, dict) or not _text(baseline.get("path"))
            or not re.fullmatch(r"[0-9a-f]{64}", str(baseline.get("sha256", "")))):
        raise PolicyError("UNAUTHORIZED", "版本全量缺少真实验收基线及摘要")
    baseline_path = _safe_inside(root, root / baseline["path"])
    if not baseline_path.is_file() or hashlib.sha256(baseline_path.read_bytes()).hexdigest() != baseline["sha256"]:
        raise PolicyError("UNAUTHORIZED", "验收基线文件不存在或已改变")
    tests, dependencies = plan.get("acceptance_tests"), plan.get("dependencies")
    if plan.get("unit_applicability") is not None:
        # 单测不适用：仅当声明精确匹配且验收基线事实上全部正式用例 browser_only、无任何测试文件映射。
        data = json.loads(baseline_path.read_text(encoding="utf-8"))
        cases = data.get("cases") if isinstance(data, dict) else None
        ids = [c.get("id") for c in cases if isinstance(c, dict)] if isinstance(cases, list) else []
        browser = data.get("browser_only") if isinstance(data, dict) else None
        claim = plan["unit_applicability"]
        evidence = claim.get("evidence") if isinstance(claim, dict) else None
        if (not isinstance(claim, dict) or {k: claim.get(k) for k in ("status", "reason")} !=
                {"status": "NOT_APPLICABLE", "reason": "all-cases-browser-only"}
                or not (isinstance(evidence, dict) and evidence.get("status") == "none-found" and evidence.get("files") == 0
                        and isinstance(evidence.get("checked"), list) and evidence["checked"])
                or tests != [] or plan.get("suites") != [] or not isinstance(dependencies, list) or not ids
                or len(ids) != len(cases) or not isinstance(browser, list) or sorted(browser) != sorted(ids)
                or len(set(ids)) != len(ids) or any(c.get("test_files") for c in cases)
                or data.get("acceptance_tests") != []):
            raise PolicyError("UNAUTHORIZED", "unit_applicability 与验收基线事实不符：须全部正式用例 browser_only 且无测试文件映射")
    elif (not isinstance(tests, list) or not tests or not isinstance(dependencies, list)
            or any(not _text(item) for item in tests + dependencies) or not plan.get("suites")):
        raise PolicyError("UNAUTHORIZED", "版本全量必须列明正式用例及必要依赖，不能扫描系统补全")
    for item in tests + dependencies:
        _safe_inside(root, root / item)
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()}, plan


def validate_test_binding(root, context, version, build, manifest=None):
    """仅 autopilot 当前版本的冻结 build 子任务可以消费版本全量授权。"""
    from entry_context import _pipeline_source
    current = _context(root, context)
    parent = _budget_owner(Path(root).resolve(), current)
    _pipeline_source(parent, "sprint-autopilot")
    if (current.get("parent_task_id") != parent["task_id"] or current.get("entry") != "sprint-aiauto-test"
            or current.get("task_scope", {}).get("kind") != "test" or current["version"] != parent["version"]
            or current["version"] != version or not build or current.get("build_id") != build
            or set(current["allowed_actions"]) - {"static", "live-tests", "full-regression"}
            or "full-regression" not in current["allowed_actions"]):
        raise PolicyError("UNAUTHORIZED", "全量必须由 autopilot 委派当前 version/build 的仅测试子任务")
    frozen = current.get("test_manifest")
    if not isinstance(frozen, dict):
        raise PolicyError("UNAUTHORIZED", "全量测试子任务缺少冻结 manifest")
    binding, plan = test_manifest_binding(root, version, build, frozen.get("path"))
    if binding != frozen:
        raise PolicyError("UNAUTHORIZED", "版本测试 manifest 已变化，须重新委派当前验收范围")
    if manifest is not None:
        supplied = manifest if isinstance(manifest, dict) else test_manifest_binding(root, version, build, manifest)[1]
        if supplied != plan:
            raise PolicyError("UNAUTHORIZED", "执行器 plan 与委派时冻结 manifest 不一致")
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
                      "outcomes": [], "reservations": [], "slots": [], "queue": [], "soft_events": [], "progress": {},
                      "started": {}}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        if state["task_id"] != owner["task_id"] or set(state["used"]) != set(DEFAULT_BUDGET):
            raise ValueError("budget identity/resources mismatch")
        normalize_budget(state["used"])
        if not isinstance(state["outcomes"], list) or not isinstance(state["reservations"], list):
            raise ValueError("budget journal malformed")
        for key, empty in (("slots", []), ("queue", []), ("soft_events", []), ("progress", {}), ("started", {})):
            state.setdefault(key, empty)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise PolicyError("UNVERIFIED", f"预算记录不可读取：{exc}") from exc
    return path, state


def _mark_exhausted(root, budget_path, items, state=None, limits=None):
    """记录一次预算耗尽事实（resource + 继续所需的最小限额），供 budget_exhaustion 处置。

    ⛔ 写独立的 exhausted.json，不动 budget.json：拒绝不得改变预算账本（原子拒绝语义）。
    """
    from entry_context import _atomic_json
    if state is not None and limits is not None:
        # 只有「真实耗尽」（已用 >= 上限）才登记；单次估算超出剩余额度只拒绝该步骤并给降耗建议，
        # 不能因此冻结整个版本（否则一次估算偏大就让无人值守链路只能等人续额）。
        items = [(resource, required) for resource, required in items if state["used"][resource] >= limits[resource]]
        if not items:
            return
    try:
        _atomic_json(root, budget_path.with_name("exhausted.json"), {"at": time.time(), "items": [
            {"resource": resource, "required": required} for resource, required in items]})
    except OSError:
        pass  # 记录是处置旁路，不能盖住真正的 BUDGET_EXCEEDED


def budget_exhaustion(root, execution_context):
    """只读：根任务预算的耗尽处置状态 -> (state, items)。

    state：exhausted = 记录过耗尽且当前根限额仍不足以放行；renewed = 记录过耗尽但限额已续到足够；
    none = 从未耗尽 / 上下文不是可读根。续额只能经 entry_context revise 的真实用户来源，不在此重置 used。
    """
    from entry_context import load_context
    root = Path(root).resolve()
    try:
        ctx = load_context(root, execution_context)
        owner = _budget_owner(root, ctx)
        budget_path, _ = _budget_state(root, owner)
    except (ValueError, OSError, KeyError, TypeError):
        return "none", []
    try:
        mark = json.loads(budget_path.with_name("exhausted.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "none", []
    items = mark.get("items") if isinstance(mark, dict) else None
    if not isinstance(items, list) or not items:
        return "none", []
    limits = owner["execution_budget"]
    short = [row for row in items if isinstance(row, dict) and row.get("resource") in limits
             and limits[row["resource"]] < row.get("required", 0)]
    return ("exhausted" if short else "renewed"), (short or items)


def budget_usage(root, execution_context):
    """只读：根任务预算已用 / 限额 / 占比 -> dict | None（上下文不可读时 None）。

    供调度器 status 展示余量与「接近耗尽」预警用；不改任何账本、不放宽任何限额。
    返回 {"resources": {资源: {"used","limit","pct"}}, "max_pct", "max_resource"}，pct 为 0-100+ 的整数。
    """
    from entry_context import load_context
    root = Path(root).resolve()
    try:
        ctx = load_context(root, execution_context)
        owner = _budget_owner(root, ctx)
        _, state = _budget_state(root, owner)
        limits = owner["execution_budget"]
    except (ValueError, OSError, KeyError, TypeError, PolicyError):
        return None
    rows = {}
    hard = hard_resources(owner)
    for key, limit in limits.items():
        used = state["used"].get(key, 0)
        if key in CONCURRENT_RESOURCES:
            running = sum(1 for slot in state.get("slots", []) if slot.get("resource") == key)
            rows[key] = {"used": used, "limit": limit, "class": "concurrent", "running": running,
                         "queued": sum(1 for row in state.get("queue", []) if row.get("resource") == key), "pct": 0}
            continue
        rows[key] = {"used": used, "limit": limit, "class": "hard" if key in hard else "soft",
                     "pct": int(round(100.0 * used / limit)) if limit else (100 if used else 0)}
    capped = {k: v for k, v in rows.items() if k not in CONCURRENT_RESOURCES}
    if not capped:
        return None
    top = max(capped, key=lambda k: capped[k]["pct"])
    return {"resources": rows, "max_pct": capped[top]["pct"], "max_resource": top}


def _check_failed_input(state, input_hash, action):
    if input_hash:
        failure = next((row for row in reversed(state["outcomes"])
            if row.get("input_hash") == input_hash and (action is None or row.get("action") == action)
            and row.get("status") in ("TOOL_ERROR", "ENV_UNAVAILABLE")), None)
        if failure:
            raise PolicyError(failure["status"], "同根因同输入的工具失败已终止，保留原错误，不自动换证据路径",
                              original_error=failure)


def _validation_stages(stages, *, complete=False):
    if (not isinstance(stages, dict) or set(stages) - set(VALIDATION_STAGES)
            or (complete and set(stages) != set(VALIDATION_STAGES))):
        raise PolicyError("UNVERIFIED", "验证预算必须包含 pre_evidence/command/post_evidence/cleanup 四段")
    zero = {key: 0 for key in DEFAULT_BUDGET}
    result = {}
    for stage in VALIDATION_STAGES:
        values = stages.get(stage, {})
        if not isinstance(values, dict):
            raise PolicyError("UNVERIFIED", "每段预算必须为资源映射")
        result[stage] = normalize_budget(values, zero)
    return result


def _stage_totals(stages):
    totals = {key: sum(values[key] for values in stages.values()) for key in DEFAULT_BUDGET}
    return normalize_budget(totals)


def _budget_diagnostic(state, limits, stages):
    expected = _stage_totals(stages)
    remaining = {key: limits[key] - state["used"][key] for key in limits}
    # 并发资源不是累计额度：shortfall 恒 0，上限由 acquire_slot 强制
    shortfall = {key: (expected[key] if limits[key] == 0 else 0) if key in CONCURRENT_RESOURCES
                 else max(0, expected[key] - remaining[key]) for key in limits}
    return {"used": dict(state["used"]), "remaining": remaining, "limit": limits,
            "stages": stages, "expected": expected, "shortfall": shortfall,
            "scan_semantics": SCAN_SEMANTICS,
            "recommendation": {
                "minimum_limit": {key: max(limits[key], state["used"][key] + expected[key]) for key in limits},
                "required_remaining": expected,
                "basis": "已占用预算加前取证、命令、后取证和必需收尾的逐段估算；没有未经依据的倍增余量，追加预算需原授权门"}}


def reserve_validation(root, ctx, stages, input_hash, *, action, defer_input=False):
    """一次预留完整闭环；任一资源不足即零扣费拒绝，沿用根共享 reservations。

    used 兼容原接口，表示实际消耗加尚未结算的预留。各段应包含预期内容读取次数，
    elapsed_seconds 包含工作时间而非用户等待；command 的时间上限须传给进程 timeout。
    cleanup 指必需收尾核验，不指清理业务数据；预算接口只记账，从不执行或重放动作。
    冷缓存前取证尚无内容 hash 时 defer_input=True：入参只作 plan_hash，命令前必须绑定真实输入。
    """
    from entry_context import _task_lock, _context_path, _atomic_json
    root = Path(root).resolve()
    current = require_action(_context(root, ctx), action)
    action = canonical_action(action)
    stages = _validation_stages(stages, complete=True)
    if type(defer_input) is not bool:
        raise PolicyError("UNVERIFIED", "defer_input 必须为明确布尔值")
    if not re.fullmatch(r"[0-9a-f]{64}", str(input_hash)):
        raise PolicyError("UNVERIFIED", "input_hash 必须是实际输入 SHA256")
    owner = _budget_owner(root, current)
    with _task_lock(root, _context_path(root, owner["task_id"])) as locked:
        current = require_action(_context(root, ctx), action)
        path, state = _budget_state(root, locked)
        if not defer_input:
            _check_failed_input(state, input_hash, action)
        limits = _limits(locked, current)
        diagnostic = _budget_diagnostic(state, limits, stages)
        blocking = {key: short for key, short in diagnostic["shortfall"].items()
                    if short and is_blocking((locked, current), key, action)}
        soft_short = {key: short for key, short in diagnostic["shortfall"].items() if short and key not in blocking}
        if blocking:
            _mark_exhausted(root, path, [(key, limits[key] + short) for key, short in blocking.items()], state, limits)
            raise PolicyError("BUDGET_EXCEEDED", "余额不足以完成整个验证闭环，执行前拒绝", **diagnostic)
        soft_events = [_soft_event(state, key, state["used"][key] + diagnostic["expected"][key], limits[key], action=action)
                       for key in soft_short]
        totals = diagnostic["expected"]
        row = {"reservation_id": str(uuid.uuid4()), "kind": "validation", "task_id": current["task_id"],
               "revision": current["revision"], "input_hash": None if defer_input else input_hash,
               "input_bound": not defer_input, "plan_hash": input_hash if defer_input else None,
               "action": action, "at": time.time(), "stages": stages, "costs": totals, "held": dict(totals), "limits": limits,
               "actual_stages": _validation_stages({}), "observations": {}, "status": "RESERVED"}
        for key, cost in totals.items():
            state["used"][key] += cost
        state["reservations"].append(row)
        _atomic_json(root, path, state)
        return dict(copy.deepcopy(row), budget_task_id=locked["task_id"], soft_exceeded=soft_events,
                    used=dict(state["used"]), remaining={key: limits[key] - state["used"][key] for key in limits})


def bind_validation_input(root, ctx, reservation, input_hash):
    """前取证后、命令前给原票据绑定真实内容输入；不改费用，也不以计划 hash 判断失败重试。"""
    from entry_context import _task_lock, _context_path, _atomic_json
    root = Path(root).resolve()
    current = _context(root, ctx)
    owner = _budget_owner(root, current)
    if not re.fullmatch(r"[0-9a-f]{64}", str(input_hash)):
        raise PolicyError("UNVERIFIED", "绑定输入必须是实际内容 SHA256")
    with _task_lock(root, _context_path(root, owner["task_id"])) as locked:
        current = _context(root, ctx)
        _budget_owner(root, current)
        path, state = _budget_state(root, locked)
        row = next((item for item in state["reservations"]
                    if item.get("reservation_id") == reservation.get("reservation_id")), None)
        if row is None or row.get("kind") != "validation" or row["task_id"] != current["task_id"]:
            raise PolicyError("UNVERIFIED", "无法绑定非本任务验证预留")
        require_action(current, row["action"])
        if "settlement" in row:
            raise PolicyError("UNVERIFIED", "已结算票据不可绑定输入")
        if row.get("input_bound", True):
            if row["input_hash"] != input_hash:
                raise PolicyError("UNVERIFIED", "票据已绑定其他实际输入，不能换输入绕过失败记录")
            return copy.deepcopy(row)
        if any(row["actual_stages"]["command"].values()):
            raise PolicyError("UNVERIFIED", "命令已执行，不能事后换输入")
        _check_failed_input(state, input_hash, row["action"])
        row.update(input_hash=input_hash, input_bound=True)
        _atomic_json(root, path, state)
        return copy.deepcopy(row)


def _validation_observations(values):
    if values is None:
        return None
    if (not isinstance(values, dict) or set(values) - (set(SCAN_SEMANTICS) - {"scanned_files"})
            or any(type(value) is not int or value < 0 for value in values.values())):
        raise PolicyError("UNVERIFIED", "扫描观测只能包含非负 unique_files/metadata_entries/cache_hits/tool_objects 计数")
    return dict(values)


def _update_validation(root, ctx, reservation, actual_stages, *, final=False, cancelled=False,
                       status="UNVERIFIED", root_cause=None, evidence=None, observations=None):
    from entry_context import _task_lock, _context_path, _atomic_json
    root = Path(root).resolve()
    current = _context(root, ctx)
    owner = _budget_owner(root, current)
    actual = None if actual_stages is None else _validation_stages(actual_stages)
    observations = _validation_observations(observations)
    if status not in STATUSES:
        raise PolicyError("UNVERIFIED", "未知验证结算状态")
    with _task_lock(root, _context_path(root, owner["task_id"])) as locked:
        current = _context(root, ctx)
        _budget_owner(root, current)
        path, state = _budget_state(root, locked)
        row = next((item for item in state["reservations"]
                    if item.get("reservation_id") == reservation.get("reservation_id")), None)
        if row is None or row.get("kind") != "validation" or row["task_id"] != current["task_id"]:
            raise PolicyError("UNVERIFIED", "无法结算非本任务验证预留")
        actual = row["actual_stages"] if actual is None else actual
        unbound_execution = not row.get("input_bound", True) and any(actual["command"].values())
        if not row.get("input_bound", True) and final and status == "PASS" and not unbound_execution:
            raise PolicyError("UNVERIFIED", "未绑定实际内容输入的票据不能声明 PASS")
        observations = row["observations"] if observations is None else observations
        settlement = {"actual_stages": actual, "observations": observations, "status": status,
                      "cancelled": cancelled, "root_cause": root_cause, "evidence": evidence}
        if "settlement" in row:
            if not final or row["settlement"] != settlement:
                raise PolicyError("UNVERIFIED", "同一预留不可按不同事实重复结算")
        else:
            if any(actual[stage][key] < row["actual_stages"][stage][key]
                   for stage in VALIDATION_STAGES for key in DEFAULT_BUDGET):
                raise PolicyError("UNVERIFIED", "实际消耗必须累计报告，不得退款已发生工作")
            if any(observations.get(key, 0) < value for key, value in row["observations"].items()):
                raise PolicyError("UNVERIFIED", "已记录扫描观测不得减少")
            totals = _stage_totals(actual)
            held = totals if final else {key: max(row["costs"][key], totals[key]) for key in totals}
            for key in totals:
                state["used"][key] += held[key] - row["held"][key]
            row.update(actual_stages=actual, observations=observations, held=held,
                       unbound_execution=unbound_execution)
            # 超过预留的事实也必须入账；只禁止下一次工作，不抹掉已经发生的执行。
            # 原票据保留预留时额度作审计；合法预算修订由当前父链决定，不重置任何实际费用。
            limits = _limits(locked, current)
            over = {key: state["used"][key] - limit for key, limit in limits.items()
                    if state["used"][key] > limit and key not in CONCURRENT_RESOURCES}
            row["over_budget"] = {key: value for key, value in over.items()
                                  if is_blocking((locked, current), key, row.get("action"))}
            row["soft_over"] = {key: value for key, value in over.items() if key not in row["over_budget"]}
            if row["over_budget"]:
                _mark_exhausted(root, path, [(key, state["used"][key]) for key in row["over_budget"]])
            for key in row["soft_over"]:
                _soft_event(state, key, state["used"][key], limits[key], action=row.get("action"), settled=final)
            if final:
                row.update(settlement=copy.deepcopy(settlement), settled_at=time.time(),
                           status="UNVERIFIED" if row["over_budget"] or cancelled or unbound_execution else status)
                state["outcomes"].append({"task_id": current["task_id"], "revision": current["revision"],
                    "reservation_id": row["reservation_id"], "action": row["action"], "status": row["status"],
                    "input_hash": row["input_hash"], "root_cause": root_cause, "evidence": evidence,
                    "over_budget": row["over_budget"], "at": row["settled_at"]})
            _atomic_json(root, path, state)
        result = copy.deepcopy(row)
        if row.get("over_budget"):
            raise PolicyError("BUDGET_EXCEEDED", "实际消耗超限，执行事实和真实费用已保存", reservation=result)
        if row.get("unbound_execution"):
            raise PolicyError("UNVERIFIED", "命令执行前未绑定实际输入；违规执行事实和真实费用已保存", reservation=result)
        return result


def record_validation_usage(root, ctx, reservation, actual_stages, *, observations=None):
    """持久化累计已发生费用；不释放尚未执行部分，重复同一累计进度不重复扣费。"""
    return _update_validation(root, ctx, reservation, actual_stages, observations=observations)


def settle_validation(root, ctx, reservation, actual_stages, *, status="UNVERIFIED", root_cause=None,
                      evidence=None, observations=None):
    """原子结算全部实际费用并保留结果；后取证中断须以 UNVERIFIED 和原执行事实收尾。

    status 描述验证闭环；evidence 中命令/交付的真实成功与机器收尾失败保持分开，不改写、不重放。
    """
    return _update_validation(root, ctx, reservation, actual_stages, final=True, status=status,
                              root_cause=root_cause, evidence=evidence, observations=observations)


def cancel_validation(root, ctx, reservation, actual_stages=None, *, root_cause=None,
                      evidence=None, observations=None):
    """取消只返未用预留，省略 actual_stages 时保留所有已记实际费用；从不产生 PASS。"""
    return _update_validation(root, ctx, reservation, actual_stages, final=True, cancelled=True,
                              root_cause=root_cause, evidence=evidence, observations=observations)


def reserve_budget(root, ctx, resource, cost=1, input_hash=None, *, action=None):
    """预留累计资源；锁内检查和扣减，多个 Agent/子任务不能各取一份预算。

    elapsed_seconds 预留计划最长执行时间，调用方必须把同一上限给进程 timeout。
    非时间单资源接口即计费，调用方须在实际内容读取/扫描前调用，重复读同一路径仍计费。
    完整验证应使用 reserve_validation，取消/结算只退尚未使用的预留。
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
        _check_failed_input(state, input_hash, action)
        used = state["used"][resource]
        # 子任务可以缩小上限，但任何子任务的消耗仍计入父任务总额。
        limit = min(locked["execution_budget"][resource], current["execution_budget"][resource])
        soft = None
        if resource in CONCURRENT_RESOURCES and limit == 0 and cost > 0:
            # 并发上限为 0 = 明确禁止启动该类任务（不是“累计额度用完”）
            raise PolicyError("BUDGET_EXCEEDED", f"{resource} 并发上限为 0，不允许启动", resource=resource,
                              used=used, cost=cost, limit=limit, recovery=recovery_path(resource))
        if resource not in CONCURRENT_RESOURCES and used + cost > limit:
            if is_blocking((locked, current), resource, action):
                _mark_exhausted(root, path, [(resource, used + cost)], state, {resource: limit})
                raise PolicyError("BUDGET_EXCEEDED", f"{resource}: {used} + {cost} > {limit}",
                                  resource=resource, used=used, cost=cost, limit=limit,
                                  recovery=recovery_path(resource))
            soft = _soft_event(state, resource, used + cost, limit, action=action)
        state["used"][resource] += cost
        reservation_id = str(uuid.uuid4())
        state["reservations"].append({"reservation_id": reservation_id, "resource": resource, "cost": cost,
                                      "task_id": current["task_id"], "revision": current["revision"],
                                      "input_hash": input_hash, "action": canonical_action(action), "at": time.time()})
        _atomic_json(root, path, state)
        result = {"status": "RESERVED", "reservation_id": reservation_id,
                  "resource": resource, "cost": cost, "used": state["used"][resource],
                  "limit": limit, "remaining": limit - state["used"][resource], "budget_task_id": locked["task_id"]}
        if resource in CONCURRENT_RESOURCES:
            result["note"] = f"{resource} 是并发硬限：本调用只做累计统计；强制同时运行上限请用 acquire-slot / release-slot"
        if soft:
            result["soft_exceeded"] = soft
        elif resource not in CONCURRENT_RESOURCES and limit and state["used"][resource] >= SOFT_WARN_RATIO * limit:
            result["warning"] = f"{resource} 已用 {state['used'][resource]}/{limit}，接近上限：先缩小范围、复用缓存、减少重复取证"
        return result


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
        if row is None or row.get("resource") != "elapsed_seconds" or row["task_id"] != current["task_id"]:
            raise PolicyError("UNVERIFIED", "无法结算非本任务时间预留")
        if "actual_cost" in row:
            if row["actual_cost"] != elapsed_seconds:
                raise PolicyError("UNVERIFIED", "同一预留不可重复按不同耗时结算")
            return dict(row)
        state["used"]["elapsed_seconds"] += elapsed_seconds - row["cost"]
        row["actual_cost"] = elapsed_seconds
        over = state["used"]["elapsed_seconds"] > locked["execution_budget"]["elapsed_seconds"]
        blocking = over and is_blocking((locked, current), "elapsed_seconds", row.get("action"))
        if blocking:
            _mark_exhausted(root, path, [("elapsed_seconds", state["used"]["elapsed_seconds"])])
        elif over:
            _soft_event(state, "elapsed_seconds", state["used"]["elapsed_seconds"],
                        locked["execution_budget"]["elapsed_seconds"], settled=True)
        _atomic_json(root, path, state)
        if blocking:
            raise PolicyError("BUDGET_EXCEEDED", "实际执行耗时超限", used=state["used"]["elapsed_seconds"],
                              recovery=recovery_path("elapsed_seconds"))
        return dict(row)


# ---------------------------------------------------------------- 恢复路径 / 步骤超时 / 并发槽位 / 进展

def recovery_path(resource):
    """BUDGET_EXCEEDED 的明确恢复路径：先降耗，其次用户明确续额；续额只能走带用户原文的 revise。"""
    steps = ["缩小范围（收窄 write_set / 显式相关测试入口 select_related_tests.py --explicit-tests）",
             "复用有效缓存（重跑同命令即断点续扫，已完成部分不重做）", "去除重复取证"]
    steps.append("用户明确续额：entry_context.py revise --execution-budget '{\"%s\": N}' 并附本轮用户原文来源；"
                 "续额只放宽执行资源，不扩大业务授权（全量回归/启动服务/写集/部署仍须各自授权）" % resource)
    return {"resource": resource, "steps": steps, "only_affected_stage_stops": True}


# 单步超时的唯一信源：默认值可由 AIDP_STEP_TIMEOUT_<KIND> 环境变量或调用方显式参数覆盖；
# 内部不得再写 min(10, …) 一类未说明的更低上限。总量预算 hard 时才以剩余额度封顶。
STEP_TIMEOUTS = {"scan": 300.0, "selection": 60.0, "command": 30.0, "version-command": 3600.0}


def step_timeout(root, ctx, kind, requested=None, *, action=None):
    """某一步的超时秒数：显式参数 > 环境变量 > STEP_TIMEOUTS；elapsed 为阻断类时再以剩余额度封顶。"""
    import os
    if kind not in STEP_TIMEOUTS:
        raise PolicyError("UNVERIFIED", f"未知步骤超时类别 {kind}")
    base = requested
    if base is None:
        raw = os.environ.get("AIDP_STEP_TIMEOUT_" + kind.upper().replace("-", "_"))
        try:
            base = float(raw) if raw else STEP_TIMEOUTS[kind]
        except ValueError:
            base = STEP_TIMEOUTS[kind]
    if not (isinstance(base, (int, float)) and math.isfinite(base) and base > 0):
        raise PolicyError("UNVERIFIED", "步骤超时必须是正有限秒数")
    if ctx is None:
        return float(base)
    root = Path(root).resolve()
    current = _context(root, ctx)
    owner = _budget_owner(root, current)
    if not is_blocking((owner, current), "elapsed_seconds", action):
        return float(base)
    _, state = _budget_state(root, owner)
    limit = min(owner["execution_budget"]["elapsed_seconds"], current["execution_budget"]["elapsed_seconds"])
    remaining = limit - state["used"]["elapsed_seconds"]
    if remaining <= 0:
        raise PolicyError("BUDGET_EXCEEDED", "没有可用于该步骤的耗时预算", recovery=recovery_path("elapsed_seconds"))
    return float(min(base, remaining))


SLOT_KINDS = {"agent": "agents", "test": "processes", "build": "processes", "process": "processes"}
SLOT_LEASE_SECONDS = 3600.0
QUEUE_TTL_SECONDS = 1800.0   # 排队票据最长保留时间：调用方消失（崩溃/被 kill）后不会永久占着队首


def _pid_identity(pid):
    """Linux starttime 区分 PID 复用；其它平台保守依赖存活检测。"""
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def _pid_alive(pid):
    import os
    if type(pid) is not int or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except (PermissionError, OSError, ValueError, TypeError):
        return True
    return True


def _reap(state, now):
    """释放已过期租约或持有进程已死亡的占用；崩溃/被杀的 Agent 不会永久占着并发额度。"""
    import socket
    host = socket.gethostname()
    reaped = []
    for key in ("slots", "queue"):
        keep = []
        for row in state[key]:
            local_pid = row.get("host") == host and type(row.get("pid")) is int and row["pid"] > 0
            alive = local_pid and _pid_alive(row["pid"])
            identity = _pid_identity(row["pid"]) if alive else None
            if alive and row.get("pid_identity") and identity and row["pid_identity"] != identity:
                alive = False
            lease = row.get("lease_until", 0)
            expired = (key == "slots" and not alive and
                       (not isinstance(lease, (int, float)) or not math.isfinite(lease) or lease < now)) or \
                      (key == "queue" and now - row.get("enqueued_at", now) > QUEUE_TTL_SECONDS)
            dead = local_pid and not alive
            (reaped if expired or dead else keep).append(row)
        state[key] = keep
    return reaped


def acquire_slot(root, ctx, kind, *, action=None, wait_seconds=0.0, lease_seconds=SLOT_LEASE_SECONDS,
                 poll_seconds=0.2, label="", pid=None, cancel_event=None, group=None):
    """取得一个并发槽位（agents / processes），与父任务、子 Agent、嵌套流程共用根任务同一并发池。

    满额时先进队（队列可见、FIFO、可 cancel_queued）；wait_seconds 内轮询，超时返回 status=QUEUED 而不是失败，
    调用方可继续等待或取消。累计 used 只作统计。槽位必须经 release_slot 或 concurrency_slot 释放。
    声明 group 时与根池内全部同组槽位互斥，不受上下文、run_scope 或类别边界分割。
    """
    import os
    import socket
    from entry_context import _task_lock, _context_path, _atomic_json
    if kind not in SLOT_KINDS:
        raise PolicyError("UNVERIFIED", f"未知并发类别 {kind}")
    for name, value, positive in (("lease_seconds", lease_seconds, True),
                                  ("wait_seconds", wait_seconds, False), ("poll_seconds", poll_seconds, True)):
        if (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
                or value < 0 or positive and value == 0):
            raise PolicyError("UNVERIFIED", f"{name} 必须为{'正' if positive else '非负'}有限秒数")
    if pid is not None and (type(pid) is not int or pid < 0):
        raise PolicyError("UNVERIFIED", "pid 必须是非负整数；0 使用有限租约")
    if group is not None and (not isinstance(group, str) or not group.strip()):
        raise PolicyError("UNVERIFIED", "group 必须是非空共享资源名")
    group = group.strip() if group is not None else None
    resource = SLOT_KINDS[kind]
    root = Path(root).resolve()
    current = _context(root, ctx)
    if action:
        require_action(current, action)
    owner = _budget_owner(root, current)
    ticket_id = str(uuid.uuid4())
    deadline = time.monotonic() + max(0.0, wait_seconds)
    holder_pid = os.getpid() if pid is None else pid
    try:
        while True:
            if cancel_event is not None and cancel_event.is_set():
                raise PolicyError("CANCELLED", "并发等待已取消")
            with _task_lock(root, _context_path(root, owner["task_id"])) as locked:
                current = _context(root, ctx)
                path, state = _budget_state(root, locked)
                _reap(state, time.time())
                limit = min(locked["execution_budget"][resource], current["execution_budget"][resource])
                if limit == 0:
                    raise PolicyError("BUDGET_EXCEEDED", f"{resource} 并发上限为 0，不允许启动", resource=resource,
                                      limit=0, recovery=recovery_path(resource))
                active = [row for row in state["slots"] if row["resource"] == resource]
                waiting = [row for row in state["queue"] if row["resource"] == resource]
                mine = next((row for row in waiting if row["ticket_id"] == ticket_id), None)
                first = (waiting[0]["ticket_id"] == ticket_id) if mine else not waiting
                group_busy = group is not None and any(row.get("group") == group for row in state["slots"])
                if len(active) < limit and first and not group_busy:
                    if mine:
                        state["queue"] = [row for row in state["queue"] if row["ticket_id"] != ticket_id]
                    slot = {"slot_id": str(uuid.uuid4()), "kind": kind, "resource": resource, "task_id": current["task_id"],
                            "label": label, "group": group, "pid": holder_pid, "pid_identity": _pid_identity(holder_pid), "host": socket.gethostname(),
                            "chain": os.environ.get("AIDP_TICK_COMMAND", ""), "tick": os.environ.get("AIDP_TICK_TOKEN", ""),
                            "acquired_at": time.time(), "lease_until": time.time() + lease_seconds}
                    state["slots"].append(slot)
                    # 槽位累计启动数单独统计（不并入 used：验证预留/reserve_budget 已按各自口径记 used，避免双计）
                    state["started"][resource] = state["started"].get(resource, 0) + 1
                    _atomic_json(root, path, state)
                    return {"status": "ACQUIRED", "slot": slot, "limit": limit, "active": len(active) + 1}
                if mine is None:
                    state["queue"].append({"ticket_id": ticket_id, "kind": kind, "resource": resource,
                                           "task_id": current["task_id"], "label": label, "group": group, "pid": holder_pid,
                                           "host": socket.gethostname(), "enqueued_at": time.time(),
                                           "chain": os.environ.get("AIDP_TICK_COMMAND", ""),
                                           "tick": os.environ.get("AIDP_TICK_TOKEN", "")})
                else:
                    mine["enqueued_at"] = time.time()
                _atomic_json(root, path, state)
                position = 1 + [row["ticket_id"] for row in state["queue"] if row["resource"] == resource].index(ticket_id)
                snapshot = {"status": "QUEUED", "ticket_id": ticket_id, "position": position, "limit": limit,
                            "active": len(active), "resource": resource, "group": group, "group_busy": group_busy}
            if time.monotonic() >= deadline:
                return snapshot
            time.sleep(min(poll_seconds, max(0.0, deadline - time.monotonic())))
    except BaseException:
        # 中断或上下文修订后仍按取得队列时的根身份清理，不能让活跃父 PID 的孤儿队列挡住后续工作。
        with _task_lock(root, _context_path(root, owner["task_id"])) as locked:
            path, state = _budget_state(root, locked)
            state["queue"] = [row for row in state["queue"] if row["ticket_id"] != ticket_id]
            _atomic_json(root, path, state)
        raise


def release_slot(root, ctx, slot):
    """幂等释放；正常完成、异常、取消、超时后都必须调用（concurrency_slot 已保证）。"""
    from entry_context import _task_lock, _context_path, _atomic_json
    root = Path(root).resolve()
    current = _context(root, ctx)
    owner = _budget_owner(root, current)
    slot_id = slot.get("slot_id") if isinstance(slot, dict) else slot
    with _task_lock(root, _context_path(root, owner["task_id"])) as locked:
        path, state = _budget_state(root, locked)
        before = len(state["slots"])
        state["slots"] = [row for row in state["slots"] if row["slot_id"] != slot_id]
        if len(state["slots"]) != before:
            _atomic_json(root, path, state)
        return {"status": "RELEASED" if len(state["slots"]) != before else "NOT_HELD", "slot_id": slot_id}


def cancel_queued(root, ctx, ticket_id):
    """取消仍在排队的请求（不影响已持有槽位的任务）。"""
    from entry_context import _task_lock, _context_path, _atomic_json
    root = Path(root).resolve()
    current = _context(root, ctx)
    owner = _budget_owner(root, current)
    with _task_lock(root, _context_path(root, owner["task_id"])) as locked:
        path, state = _budget_state(root, locked)
        before = len(state["queue"])
        state["queue"] = [row for row in state["queue"] if row["ticket_id"] != ticket_id]
        if len(state["queue"]) != before:
            _atomic_json(root, path, state)
        return {"status": "CANCELLED" if len(state["queue"]) != before else "NOT_QUEUED", "ticket_id": ticket_id}


def reap_slots(root, ctx, chain, keep_tick=""):
    """新一轮 tick 开始时回收「同一链路上一轮遗留」的槽位与排队票据。

    旧 tick 的本机活跃进程仍占额度；令牌变化不能证明其已停止。
    仅回收同链路旧票据：已结束本机持有者、无持有 PID 的 CLI 遗留，或远端到期租约。
    """
    import socket
    from entry_context import _task_lock, _context_path, _atomic_json
    root = Path(root).resolve()
    current = _context(root, ctx)
    owner = _budget_owner(root, current)
    host, now = socket.gethostname(), time.time()

    def removable(row, kind):
        if row.get('chain') != chain or row.get('tick') == keep_tick:
            return False
        pid = row.get('pid')
        if type(pid) is int and pid > 0:
            if row.get('host') == host:
                if _pid_alive(pid):
                    identity = _pid_identity(pid)
                    return bool(row.get('pid_identity') and identity and row['pid_identity'] != identity)
            else:
                expiry = row.get('lease_until', 0) if kind == 'slots' else row.get('enqueued_at', now) + QUEUE_TTL_SECONDS
                return expiry < now
        return True

    with _task_lock(root, _context_path(root, owner["task_id"])) as locked:
        path, state = _budget_state(root, locked)
        dropped = 0
        for key in ("slots", "queue"):
            keep = [row for row in state[key] if not removable(row, key)]
            dropped += len(state[key]) - len(keep)
            state[key] = keep
        if dropped:
            _atomic_json(root, path, state)
        return {"reaped": dropped, "chain": chain}


def slot_status(root, ctx):
    """只读：当前并发占用与排队（可见的队列）。"""
    root = Path(root).resolve()
    current = _context(root, ctx)
    owner = _budget_owner(root, current)
    _, state = _budget_state(root, owner)
    limits = _limits(owner, current)
    return {"limits": {key: limits[key] for key in CONCURRENT_RESOURCES},
            "running": [dict(row) for row in state["slots"]], "queued": [dict(row) for row in state["queue"]],
            "started_total": {key: state["started"].get(key, 0) for key in CONCURRENT_RESOURCES}}


from contextlib import contextmanager  # noqa: E402


@contextmanager
def concurrency_slot(root, ctx, kind, *, action=None, wait_seconds=300.0, lease_seconds=SLOT_LEASE_SECONDS, label="",
                     cancel_event=None, group=None):
    """取槽 → 工作 → 无论正常/异常/取消/超时都释放；同 group 在根任务池互斥。"""
    result = acquire_slot(root, ctx, kind, action=action, wait_seconds=wait_seconds,
                          lease_seconds=lease_seconds, label=label, cancel_event=cancel_event, group=group)
    if result["status"] != "ACQUIRED":
        cancel_queued(root, ctx, result["ticket_id"])
        reason = f"共享资源组 {result['group']} 已占用" if result.get("group_busy") else f"并发已达上限 {result['limit']}"
        raise PolicyError("QUEUED", f"{reason}，排队等待超时（第 {result['position']} 位）；"
                          "队列项已撤销，可稍后重试或调低并行度", **{k: v for k, v in result.items() if k != "status"})
    try:
        yield result["slot"]
    finally:
        release_slot(root, ctx, result["slot"])


def record_progress(root, ctx, stage, processed, total=None, note=""):
    """长任务阶段进展：阶段、已处理数、总数、最近进展时间；供 assess_progress 与人读输出使用。"""
    from entry_context import _task_lock, _context_path, _atomic_json
    root = Path(root).resolve()
    current = _context(root, ctx)
    owner = _budget_owner(root, current)
    with _task_lock(root, _context_path(root, owner["task_id"])) as locked:
        path, state = _budget_state(root, locked)
        old = state["progress"].get(stage, {})
        now = time.time()
        moved = processed > old.get("processed", -1)
        row = {"stage": stage, "processed": processed, "total": total, "note": note,
               "first_total": old.get("first_total", total), "started_at": old.get("started_at", now),
               "last_progress_at": now if moved else old.get("last_progress_at", now), "updated_at": now}
        state["progress"][stage] = row
        _atomic_json(root, path, state)
        return dict(row)


def assess_progress(root, ctx, stage, *, now=None, stall_seconds=300.0, growth_ratio=1.5):
    """按进展与失败原因归类：advancing / repeated-failure / external-failure / scope-growth / stalled / idle。

    只读。repeated-failure 表示同输入同原因已失败，不得无意义重试（参数/代码/环境实质变化后才重新评估）；
    advancing 表示有真实进展，不得因总耗时长而误判卡死。
    """
    root = Path(root).resolve()
    current = _context(root, ctx)
    owner = _budget_owner(root, current)
    _, state = _budget_state(root, owner)
    now = time.time() if now is None else now
    failing = [row for row in state["outcomes"] if row.get("status") in ("TOOL_ERROR", "ENV_UNAVAILABLE", "FAIL")]
    if len(failing) >= 2 and all(failing[-1].get(k) == failing[-2].get(k) for k in ("input_hash", "root_cause", "status")):
        return {"state": "repeated-failure", "retry": False, "evidence": failing[-1],
                "message": "相同输入、相同原因的失败不再重试；改变参数、代码或环境后才重新评估"}
    row = state["progress"].get(stage)
    if row is None:
        if failing and failing[-1]["status"] == "ENV_UNAVAILABLE":
            return {"state": "external-failure", "retry": True, "message": "外部依赖暂时失败：退避后可重试一次"}
        return {"state": "idle", "retry": True, "message": "尚无进展记录"}
    first = row.get("first_total") or 0
    if first and row.get("total") and row["total"] > first * growth_ratio:
        return {"state": "scope-growth", "retry": False, "evidence": row,
                "message": f"扫描范围从 {first} 扩大到 {row['total']}：先收窄输入或用显式相关测试入口，不继续全量扩张"}
    if now - row["last_progress_at"] <= stall_seconds:
        return {"state": "advancing", "retry": False, "evidence": row,
                "message": f"{stage} 已处理 {row['processed']}/{row.get('total') or '?'}，仍在推进"}
    if failing and failing[-1]["status"] == "ENV_UNAVAILABLE":
        return {"state": "external-failure", "retry": True, "evidence": row, "message": "外部依赖暂时失败"}
    return {"state": "stalled", "retry": False, "evidence": row,
            "message": f"{stage} 已 {int(now - row['last_progress_at'])} 秒无新进展：停止受影响阶段并告警，不连带停摆整个任务"}


def emit_progress(stage, processed, total=None, note="", stream=None):
    """一行人读进展：阶段、已处理/总数、最近进展；写 stderr，避免长时间只有“仍在运行”。"""
    import sys
    out = stream or sys.stderr
    out.write(f"[progress] {stage}: {processed}/{total if total is not None else '?'}" + (f" — {note}" if note else "") + "\n")
    out.flush()


def budget_summary(ctx):
    """入口输出里的紧凑预算分类；旧配置/用户显式值按硬上限保留时给出迁移说明（不静默放宽、不静默降为软限）。"""
    rows = budget_report(ctx)["resources"]
    summary = {"concurrent_hard": [k for k, v in rows.items() if v["class"] == "concurrent-hard"],
               "hard": [k for k, v in rows.items() if v["class"] == "hard"],
               "soft": [k for k, v in rows.items() if v["class"] == "soft"],
               "migration": [f"{k}={rows[k]['limit']}：{rows[k]['why']}" for k in rows
                             if rows[k]["class"] == "hard" and k not in ALWAYS_HARD_RESOURCES]}
    return summary


def budget_report(ctx):
    """每项资源的类别（并发硬限/总量软限/总量硬限/固定硬限）与原因；升级后向用户展示迁移结果。"""
    hard = hard_resources(ctx)
    sources = ctx.get("authorization_source") or []
    autopilot = any(_autopilot_source(x) for x in sources if isinstance(x, dict))
    rows = {}
    for key, limit in ctx["execution_budget"].items():
        if key in CONCURRENT_RESOURCES:
            rows[key] = {"limit": limit, "class": "concurrent-hard", "why": "同时运行上限；累计启动数仅作统计"}
        elif key in ALWAYS_HARD_RESOURCES:
            rows[key] = {"limit": limit, "class": "hard", "why": "范围/失败风暴护栏，始终阻断"}
        elif key in hard:
            why = ("autopilot 无人值守链路阻断" if autopilot else
                   "用户显式写入（含旧配置）或低于默认值，按硬上限保留，不静默放宽")
            rows[key] = {"limit": limit, "class": "hard", "why": why}
        else:
            rows[key] = {"limit": limit, "class": "soft", "why": "默认/自适应软阈值：超出只预警并按降级顺序缩小范围，不停止"}
    return {"resources": rows, "degrade_order": list(DEGRADE_STEPS),
            "note": "资源额度不等于业务授权；放宽额度不会授予全量回归、启动服务、扩大写集或部署权限"}


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
    # 注意：子命令统一用循环注册（check_cli_invocation 只在没有字面量 add_parser 时才跳过子命令名核对）
    for name in ("budget-report", "slots", "acquire-slot", "release-slot", "cancel-queued"):
        item = sub.add_parser(name)
        item.add_argument("--root", default=".")
        item.add_argument("--execution-context", required=True)
        item.add_argument("--json", action="store_true")
        if name == "acquire-slot":
            item.add_argument("--kind", choices=tuple(SLOT_KINDS), required=True)
            item.add_argument("--action")
            item.add_argument("--wait-seconds", type=float, default=0.0)
            item.add_argument("--lease-seconds", type=float, default=SLOT_LEASE_SECONDS,
                              help="租约（秒）：超过未释放则自动回收，长任务请调大")
            item.add_argument("--label", default="")
            item.add_argument("--group", help="根任务共享资源组；同组槽位互斥")
        if name == "release-slot":
            item.add_argument("--slot-id", required=True)
        if name == "cancel-queued":
            item.add_argument("--ticket-id", required=True)
    for name in ("require-action", "require-delegable", "reserve-budget", "record-outcome", "settle-elapsed"):
        item = sub.add_parser(name)
        item.add_argument("--root", default=".")
        item.add_argument("--execution-context", required=True)
        item.add_argument("--json", action="store_true")
        item.add_argument("--action", required=name in ("require-action", "require-delegable", "record-outcome"))
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
        if args.command == "budget-report":
            result = budget_report(_context(args.root, ctx))
        elif args.command == "slots":
            result = slot_status(args.root, ctx)
        elif args.command == "acquire-slot":
            # CLI 进程立即退出：不做 pid 存活判定，仅靠租约（lease）回收
            result = acquire_slot(args.root, ctx, args.kind, action=args.action, wait_seconds=args.wait_seconds,
                                  label=args.label, pid=0, lease_seconds=args.lease_seconds, group=args.group)
            if result["status"] != "ACQUIRED":
                # 没拿到槽位就不能让调用方继续派发：撤销排队票据（不留孤儿）并以非零退出，流程 `|| exit $?` 会停下重试
                cancel_queued(args.root, ctx, result["ticket_id"])
                print(json.dumps(dict(result, retry="并发已满：稍后重试 acquire-slot，或等已有任务 release-slot"),
                                 ensure_ascii=False, sort_keys=True))
                return 2
        elif args.command == "release-slot":
            result = release_slot(args.root, ctx, {"slot_id": args.slot_id})
        elif args.command == "cancel-queued":
            result = cancel_queued(args.root, ctx, args.ticket_id)
        elif args.command == "require-action":
            current = require_action(ctx, args.action)
            result = {"status": "AUTHORIZED", "action": canonical_action(args.action),
                      "task_id": current["task_id"], "revision": current["revision"]}
        elif args.command == "require-delegable":
            current = require_delegable(ctx, args.action)
            result = {"status": "DELEGABLE", "action": canonical_action(args.action),
                      "task_id": current["task_id"], "revision": current["revision"], "executable": False}
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
