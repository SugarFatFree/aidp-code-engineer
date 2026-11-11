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
# scanned_files 是本工具取证累计实际内容读取/扫描操作：同一路径再读仍计费，不能按去重路径退款。
# unique_files、metadata_entries、cache_hits 仅作旁路观测，不抵扣实际 I/O；调用方逐段报告。
# 外部命令自身的 I/O 若未测量须在 evidence 标 unknown，不并入扫描次数或伪称为零。
SCAN_SEMANTICS = {"scanned_files": "cumulative_evidence_content_read_operations",
                  "unique_files": "distinct_content_paths_per_validation",
                  "metadata_entries": "metadata_only_entries_visited",
                  "cache_hits": "content_reads_avoided_by_valid_cache",
                  "tool_objects": "external_tool_selected_objects_not_measured_io"}
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
    actions, sources, budget = set(SCOPE_ACTIONS[kind]), [], dict(DEFAULT_BUDGET)
    configured = read_execution_policy(root)
    if configured and (not configured["authorization_source"].get("command") or
                       configured["authorization_source"]["command"].lstrip("/") == command):
        chosen = validate_source(configured["authorization_source"])
        selected = _actions(configured.get("allowed_actions", []))
        reject_direct_full(selected, chosen)
        actions.update(selected)
        actions.difference_update(source_removals(chosen))
        sources.append(dict(chosen, actions=sorted(selected)))
        budget = normalize_budget(configured.get("execution_budget"), budget)
    if additional_grants or authorization_source:
        source = validate_source(authorization_source)
        grants = _actions(additional_grants or [])
        reject_direct_full(grants, source)
        if source["kind"] == "explicit-command":
            public = command_grants(source)
            if grants - public - BASE_ACTIONS:
                raise PolicyError("UNAUTHORIZED", "额外动作超出公开命令职责，需要独立 user-text 授权")
            grants.update(public)
            budget = dict(COMMAND_BUDGETS.get(source["command"].lstrip("/"), budget))
        actions.update(grants)
        actions.difference_update(source_removals(source))
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


def _mark_exhausted(root, budget_path, items):
    """记录一次预算耗尽事实（resource + 继续所需的最小限额），供 budget_exhaustion 处置。

    ⛔ 写独立的 exhausted.json，不动 budget.json：拒绝不得改变预算账本（原子拒绝语义）。
    """
    from entry_context import _atomic_json
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
    shortfall = {key: max(0, expected[key] - remaining[key]) for key in limits}
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
        limits = {key: min(locked["execution_budget"][key], current["execution_budget"][key])
                  for key in DEFAULT_BUDGET}
        diagnostic = _budget_diagnostic(state, limits, stages)
        if any(diagnostic["shortfall"].values()):
            _mark_exhausted(root, path, [(key, limits[key] + short) for key, short in diagnostic["shortfall"].items() if short])
            raise PolicyError("BUDGET_EXCEEDED", "余额不足以完成整个验证闭环，执行前拒绝", **diagnostic)
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
        return dict(copy.deepcopy(row), budget_task_id=locked["task_id"],
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
            limits = {key: min(locked["execution_budget"][key], current["execution_budget"][key])
                      for key in DEFAULT_BUDGET}
            row["over_budget"] = {key: state["used"][key] - limit for key, limit in limits.items()
                                  if state["used"][key] > limit}
            if row["over_budget"]:
                _mark_exhausted(root, path, [(key, state["used"][key]) for key in row["over_budget"]])
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
        if used + cost > limit:
            _mark_exhausted(root, path, [(resource, used + cost)])
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
        if row is None or row.get("resource") != "elapsed_seconds" or row["task_id"] != current["task_id"]:
            raise PolicyError("UNVERIFIED", "无法结算非本任务时间预留")
        if "actual_cost" in row:
            if row["actual_cost"] != elapsed_seconds:
                raise PolicyError("UNVERIFIED", "同一预留不可重复按不同耗时结算")
            return dict(row)
        state["used"]["elapsed_seconds"] += elapsed_seconds - row["cost"]
        row["actual_cost"] = elapsed_seconds
        if state["used"]["elapsed_seconds"] > locked["execution_budget"]["elapsed_seconds"]:
            _mark_exhausted(root, path, [("elapsed_seconds", state["used"]["elapsed_seconds"])])
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
        if args.command == "require-action":
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
