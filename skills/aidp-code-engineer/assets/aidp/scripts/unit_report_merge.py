#!/usr/bin/env python3
"""全量单测与实测的报告契约；emit-report 与 ceremony 门共享，不改浏览器用例计数。"""
from copy import deepcopy
import json
import re
from pathlib import Path


def open_bug_count(root, version):
    count = 0
    for area in ("正式用例", "测试验收", "测试执行", "研发自测"):
        for path in (Path(root) / "docs/testing" / version / area).rglob("*.md"):
            count += len(re.findall(r"\|\s*待修复\s*\|", path.read_text(encoding="utf-8")))
    return count


def read_payload(path):
    """只解析 JSON，不执行 data.js；可供 join/ceremony 消费同一份报告事实。"""
    text = Path(path).read_text(encoding="utf-8")
    if text.lstrip().startswith("{"):
        value = json.loads(text)
    else:
        marker = text.find(".push(")
        start = text.find("{", marker) if marker >= 0 else -1
        if start < 0:
            raise ValueError("报告数据缺 JSON 或 .push(JSON)")
        value, _ = json.JSONDecoder().raw_decode(text[start:])
    if not isinstance(value, dict):
        raise ValueError("报告数据必须是对象")
    return value

UNIT_STATES = ("PASS", "FAIL", "UNVERIFIED", "TIMEOUT", "RUNNING", "NOT_APPLICABLE")
UNIT_NA_REASON = "all-cases-browser-only"
BROWSER_STATES = ("N/A", "UNVERIFIED", "TIMEOUT", "RUNNING")


def validate_unit_tests(unit, build, commit):
    """校验身份、状态和原始 run 证据；未知计数允许 null，禁止伪造零。"""
    if not isinstance(unit, dict):
        return ["unitTests 必须是对象"]
    errors = []
    if type(unit.get("schema")) is not int or unit.get("schema") != 1:
        errors.append("unitTests.schema 必须为 1")
    if not build or unit.get("build") != build:
        errors.append("unitTests.build 与报告 build 不匹配")
    if not isinstance(commit, str) or not commit.strip() or unit.get("commit") != commit:
        errors.append("unitTests.commit 与 build.commit 不匹配或缺失")
    if unit.get("status") not in UNIT_STATES:
        errors.append("unitTests.status 非法")
    if not isinstance(unit.get("reason"), str):
        errors.append("unitTests.reason 必须为字符串")
    if not isinstance(unit.get("reused"), bool):
        errors.append("unitTests.reused 必须为布尔值")
    runs = unit.get("runs")
    if not isinstance(runs, list):
        errors.append("unitTests.runs 必须为数组")
        runs = []
    seen = set()
    for index, item in enumerate([unit] + runs):
        where = "unitTests" if index == 0 else f"unitTests.runs[{index - 1}]"
        if not isinstance(item, dict):
            errors.append(f"{where} 必须为对象")
            continue
        counts = item.get("counts")
        if counts is not None:
            if not isinstance(counts, dict):
                errors.append(f"{where}.counts 必须为对象或 null")
            else:
                for key in ("passed", "failed", "skipped"):
                    value = counts.get(key)
                    if value is not None and (type(value) is not int or value < 0):
                        errors.append(f"{where}.counts.{key} 必须为非负整数或 null")
        if not isinstance(item.get("failed_cases"), list):
            errors.append(f"{where}.failed_cases 必须为数组")
        if item.get("primary_error") is not None and not isinstance(item["primary_error"], str):
            errors.append(f"{where}.primary_error 必须为字符串或 null")
        if item.get("status") not in UNIT_STATES:
            errors.append(f"{where}.status 非法")
        if item.get("status") == "PASS" and (item.get("failed_cases") or
                (isinstance(counts, dict) and isinstance(counts.get("failed"), int) and counts["failed"] > 0)):
            errors.append(f"{where} 标为 PASS 却有失败用例")
        if index:
            run_id = item.get("run_id")
            if not isinstance(run_id, str) or not run_id.strip() or run_id in seen:
                errors.append(f"{where}.run_id 为空或重复")
            else:
                seen.add(run_id)
            command = item.get("command")
            if not ((isinstance(command, str) and command.strip()) or
                    (isinstance(command, list) and command and all(isinstance(arg, str) for arg in command)
                     and command[0].strip())):
                errors.append(f"{where}.command 必须为非空字符串或 argv 字符串数组")
            for key in ("cwd", "env_id"):
                if not isinstance(item.get(key), str) or not item[key].strip():
                    errors.append(f"{where}.{key} 必须为非空字符串")
            if item.get("log") is not None and not isinstance(item["log"], str):
                errors.append(f"{where}.log 必须为字符串或 null")
    if unit.get("status") == "NOT_APPLICABLE":
        applicability = (unit.get("testScope") or {}).get("unit_applicability") or {}
        if (runs or unit.get("reason") != UNIT_NA_REASON or applicability.get("status") != "NOT_APPLICABLE"
                or applicability.get("reason") != UNIT_NA_REASON or (unit.get("testScope") or {}).get("acceptance_tests") != []
                or (applicability.get("evidence") or {}).get("status") != "none-found"
                or (applicability.get("evidence") or {}).get("files") != 0
                or sorted(applicability.get("browser_only") or []) != sorted((unit.get("testScope") or {}).get("case_ids") or [None])):
            errors.append("unitTests NOT_APPLICABLE 必须无 runs，且 testScope 声明全部正式用例 browser_only 及“发现过程已执行且为空”(evidence none-found) 的依据")
    if unit.get("status") == "PASS" and (not runs or any(
            not isinstance(run, dict) or run.get("status") != "PASS" for run in runs)):
        errors.append("unitTests PASS 必须有 runs 且全部 PASS")
    if unit.get("status") in ("PASS", "FAIL") and any(
            isinstance(run, dict) and run.get("status") == "RUNNING" for run in runs):
        errors.append("unitTests 仍有 RUNNING run，不能标为已完成")
    return errors


def unverified_result(build, commit, reason="未提供本 build 的全量单测结果"):
    return {"schema": 1, "build": build, "commit": commit, "status": "UNVERIFIED",
            "reason": reason, "runs": [], "counts": None, "failed_cases": [],
            "primary_error": None, "reused": False}


def browser_status(payload):
    summary = payload.get("summary") or payload.get("testSummary") or {}
    browser = payload.get("browserTests") or {}
    if (summary.get("fail", 0) or summary.get("openBugs", 0) or summary.get("runtime_errors", 0)
            or summary.get("openDefects", 0) or payload.get("runtimeErrors")
            or any(isinstance(d, dict) and d.get("status") in ("待修复", "未修复", "open", "pending", "fail")
                   for d in (payload.get("defects") or []))):
        return "FAIL"
    if summary.get("pendingBrowserTest"):
        return "RUNNING"
    if summary.get("pendingCases", 0) and browser.get("status") not in ("RUNNING", "TIMEOUT"):
        return "UNVERIFIED"
    if browser.get("status") in BROWSER_STATES and str(browser.get("reason") or "").strip():
        return browser["status"]
    if summary.get("block", 0) or summary.get("skip", 0):
        return "UNVERIFIED"
    if summary.get("total", 0) > 0 and summary.get("na", 0) == summary.get("total"):
        return "N/A"
    executable = summary.get("total", 0) - summary.get("na", 0)
    if executable > 0 and summary.get("pass") == executable and not summary.get("browserTested") is False:
        return "PASS"
    return "UNVERIFIED"


def unit_has_failure(unit):
    """已完成套件的真实失败不能被后续超时/未核验覆盖。"""
    if not isinstance(unit, dict):
        return False
    return any(isinstance(item, dict) and (
        item.get("status") == "FAIL" or bool(item.get("failed_cases")) or
        (isinstance(item.get("counts"), dict) and isinstance(item["counts"].get("failed"), int)
         and item["counts"]["failed"] > 0)) for item in [unit] + (unit.get("runs") or []))


def triage_targets(payload):
    """报告事实的稳定引用；统计有失败而明细不全时仍必须显式分流。"""
    targets = set()
    summary = payload.get("summary") or payload.get("testSummary") or {}
    cases = payload.get("cases") or []
    for index, case in enumerate(cases):
        if isinstance(case, dict) and case.get("result") in ("fail", "block", "skip"):
            targets.add("case:" + str(case.get("id") or index))
    for key in ("fail", "block", "skip"):
        detailed = sum(isinstance(c, dict) and c.get("result") == key for c in cases)
        if summary.get(key, 0) > detailed:
            targets.add("summary:" + key)
    defects = payload.get("defects") or []
    opened = [d for d in defects if isinstance(d, dict)
              and d.get("status") in ("待修复", "未修复", "open", "pending", "fail")]
    for index, defect in enumerate(opened):
        targets.add("defect:" + str(defect.get("id") or index))
    if summary.get("openDefects", 0) > len(opened):
        targets.add("summary:openDefects")
    if summary.get("openBugs", 0):
        targets.add("summary:openBugs")  # 版本未关闭缺陷可能来自其他人的测试，不得被本轮覆盖。
    runtime = payload.get("runtimeErrors") or []
    for index, error in enumerate(runtime):
        targets.add("runtime:" + str(error.get("id") or index) if isinstance(error, dict)
                    else "runtime:" + str(index))
    if summary.get("runtime_errors", 0) > len(runtime):
        targets.add("summary:runtime_errors")
    if (payload.get("browserTests") or {}).get("status") in ("UNVERIFIED", "TIMEOUT"):
        targets.add("browser:status")
    return sorted(targets)


def validate_failure_triage(payload):
    triage = payload.get("failureTriage")
    if triage is None:
        return []  # 缺分类允许保留报告事实；由 triage_state 阻止静默完成。
    if not isinstance(triage, dict):
        return ["failureTriage 必须为对象"]
    errors = []
    if type(triage.get("schema")) is not int or triage.get("schema") != 1:
        errors.append("failureTriage.schema 必须为 1")
    for key in ("build", "commit"):
        if not triage.get(key) or triage.get(key) != payload.get(key):
            errors.append(f"failureTriage.{key} 与报告不匹配")
    items = triage.get("items")
    if not isinstance(items, list):
        return errors + ["failureTriage.items 必须为数组"]
    targets, seen = set(triage_targets(payload)), set()
    for item in items:
        if not isinstance(item, dict):
            errors.append("failureTriage.items 元素必须为对象")
            continue
        refs = item.get("refs")
        if not isinstance(refs, list) or not refs or any(not isinstance(ref, str) for ref in refs):
            errors.append("failureTriage.refs 必须为非空字符串数组")
            continue
        for ref in refs:
            if ref not in targets or ref in seen:
                errors.append(f"failureTriage 引用不存在或重复：{ref}")
            seen.add(ref)
        if item.get("category") not in ("auto_fixable", "clarification", "environment"):
            errors.append("failureTriage.category 非法")
        if not isinstance(item.get("reason"), str) or not item["reason"].strip():
            errors.append("failureTriage.reason 必须提供分类证据")
        if item.get("category") == "clarification":
            for key in ("question", "interim_verdict"):
                if not isinstance(item.get(key), str) or not item[key].strip():
                    errors.append(f"failureTriage.{key} 必须为非空字符串")
            cases = item.get("affected_cases")
            if not isinstance(cases, list) or not cases or any(not isinstance(c, str) or not c.strip() for c in cases):
                errors.append("failureTriage.affected_cases 必须为非空用例 ID 数组")
    return errors


def triage_state(payload):
    """分类不改变原始测试成败；只决定修复/澄清/补核验的后继动作。"""
    errors = validate_failure_triage(payload)
    if errors:
        raise ValueError("；".join(errors))
    items = (payload.get("failureTriage") or {}).get("items", [])
    covered = {ref for item in items for ref in item["refs"]}
    missing = sorted(set(triage_targets(payload)) - covered)
    return {"status": "PENDING" if missing else "COMPLETE", "missing": missing,
            "auto_fixable": any(item["category"] == "auto_fixable" for item in items),
            "clarifications": [item for item in items if item["category"] == "clarification"],
            "environment": [item for item in items if item["category"] == "environment"]}


def validate_report_scope(payload):
    unit = payload.get("unitTests") or {}
    scope = payload.get("testScope")
    if not isinstance(scope, dict) or scope.get("kind") != "version":
        return ["缺当前版本冻结 testScope；历史结果不能作为版本全量完成证据"]
    errors = []
    if scope != unit.get("testScope"):
        errors.append("实测与单测 testScope 不一致")
    for key in ("version", "build"):
        if not scope.get(key) or scope[key] != payload.get(key) or scope[key] != unit.get(key):
            errors.append(f"testScope.{key} 与报告身份不一致")
    if not re.fullmatch(r"[0-9a-f]{64}", scope.get("manifest_hash", "")):
        errors.append("testScope 缺冻结 manifest_hash")
    unit_na = unit.get("status") == "NOT_APPLICABLE"
    if (not scope.get("acceptance_baseline") or not isinstance(scope.get("dependencies"), list)
            or not (scope.get("acceptance_tests") or unit_na and scope.get("acceptance_tests") == [])):
        errors.append("testScope 缺验收基线、正式测试清单或依赖清单")
    ids = scope.get("case_ids")
    if not isinstance(ids, list) or not ids or len(set(ids)) != len(ids):
        errors.append("testScope 缺完整正式用例 ID")
    elif (payload.get("browserTests") or {}).get("status") != "N/A":
        cases = payload.get("cases") or []
        actual = [case.get("id") for case in cases if isinstance(case, dict)]
        if set(actual) != set(ids) or len(set(actual)) != len(actual):
            errors.append("实测报告用例与本版本完整正式清单不一致")
    elif payload.get("cases"):
        # 浏览器 N/A = 声明无浏览器实测；此时 cases[] 若仍有条目即自相矛盾（C-03：不再整段跳过校验）。
        # 注：冻结清单逐条归类（哪些由单测覆盖）尚无 schema 字段，属已知设计取舍，需另行定 schema 后再收紧。
        errors.append("browserTests 为 N/A 但报告仍带实测用例 cases[]，二者矛盾")
    return errors


def overall_status(payload):
    browser = browser_status(payload)
    unit = payload.get("unitTests")
    if unit is None:  # 历史报告保持原来的实测语义；新生成入口必须补 unitTests。
        return browser
    if validate_unit_tests(unit, payload.get("build"), payload.get("commit")):
        return "UNVERIFIED"
    status = unit["status"]
    if browser == "FAIL" or unit_has_failure(unit):
        return "FAIL"
    for pending in ("RUNNING", "TIMEOUT", "UNVERIFIED"):
        if pending in (browser, status):
            return pending
    if triage_targets(payload):
        return "UNVERIFIED"  # 明细里的未完成问题也不能被 PASS 统计覆盖。
    if status == "NOT_APPLICABLE":
        return "PASS" if browser == "PASS" else "UNVERIFIED"  # 单测不适用时必须有真实浏览器实测，不能零实测通过。
    return "PASS" if browser in ("PASS", "N/A") else "UNVERIFIED"


def report_ready(payload):
    """终态可产报告，运行中只保留草稿，不能进入 final 收尾。"""
    unit = payload.get("unitTests")
    summary = payload.get("summary") or payload.get("testSummary") or {}
    return (not summary.get("pendingBrowserTest")
            and (payload.get("browserTests") or {}).get("status") != "RUNNING"
            and not validate_unit_tests(unit, payload.get("build"), payload.get("commit"))
            and unit.get("status") != "RUNNING"
            and all(run.get("status") != "RUNNING" for run in unit.get("runs", [])))


def success_ready(payload):
    return report_ready(payload) and not validate_report_scope(payload) and overall_status(payload) == "PASS"


def finalize_ready(payload):
    """仅已完成单测可冻结失败/成功事实；历史缺字段由调用方决定是否豁免。"""
    unit = payload.get("unitTests")
    return (report_ready(payload)
            and not validate_report_scope(payload)
            and not validate_failure_triage(payload)
            and triage_state(payload)["status"] == "COMPLETE"
            and not triage_state(payload)["environment"]
            and (payload.get("browserTests") or {}).get("status") not in ("UNVERIFIED", "TIMEOUT", "RUNNING")
            and browser_status(payload) in ("PASS", "FAIL", "N/A")
            and unit.get("status") in ("PASS", "FAIL", "NOT_APPLICABLE")
            and not (unit.get("status") == "NOT_APPLICABLE" and browser_status(payload) == "N/A")
            and all(run.get("status") in ("PASS", "FAIL") for run in unit.get("runs", [])))


def merge_unit_tests(payload, unit, build, commit, kind="test"):
    """返回合并副本，身份错误直接拒绝；统计保持实测原义，总判定另设字段。"""
    if not isinstance(payload, dict):
        raise ValueError("报告 payload 必须为对象")
    if payload.get("build") not in (None, build):
        raise ValueError("报告 build 与目标 build 不匹配")
    if payload.get("commit") not in (None, "", commit):
        raise ValueError("报告 commit 与 build.commit 不匹配")
    errors = validate_unit_tests(unit, build, commit)
    if errors:
        raise ValueError("；".join(errors))
    result = deepcopy(payload)
    result.update(build=build, commit=commit, unitTests=deepcopy(unit))
    if unit.get("testScope") is not None:
        if payload.get("testScope") not in (None, unit["testScope"]):
            raise ValueError("实测与单测冻结 testScope 不一致")
        result["testScope"] = deepcopy(unit["testScope"])
        scope_errors = validate_report_scope(result)
        if scope_errors:
            raise ValueError("；".join(scope_errors))
    key = "summary" if kind == "test" else "testSummary"
    summary = result.setdefault(key, {})
    if "runtimeErrors" in result:
        count = len(result["runtimeErrors"] or [])
        summary["runtime_errors"] = max(count, summary.get("runtime_errors", 0)) if kind == "exec" else count
    if "defects" in result:
        count = sum(1 for d in (result["defects"] or []) if isinstance(d, dict)
                    and d.get("status") in ("待修复", "未修复", "open", "pending", "fail"))
        summary["openDefects"] = max(count, summary.get("openDefects", 0)) if kind == "exec" else count
    triage = triage_state(result)
    status = overall_status(result)
    summary.update(overallStatus=status, unitStatus=unit["status"], browserStatus=browser_status(result),
                   triageStatus=triage["status"], triageMissing=triage["missing"])
    if kind == "exec":
        overview = result.setdefault("overview", {})
        if status != "PASS":
            overview["statusKind"] = "fail" if status == "FAIL" else "pend"
            overview["statusText"] = "测试失败" if status == "FAIL" else "测试未核验完成"
        overview["testStatus"] = status
    return result


def validate_report_units(payload, kind):
    """历史报告缺字段兼容；出现 unitTests 时必须按新契约验证。"""
    if "unitTests" not in payload:
        return []
    errors = validate_unit_tests(payload["unitTests"], payload.get("build"), payload.get("commit"))
    errors.extend(validate_failure_triage(payload))
    if payload.get("testScope") is not None or (payload.get("unitTests") or {}).get("testScope") is not None:
        errors.extend(validate_report_scope(payload))
    browser = payload.get("browserTests")
    if browser is not None and (not isinstance(browser, dict) or browser.get("status") not in BROWSER_STATES
                                or not isinstance(browser.get("reason"), str) or not browser["reason"].strip()):
        errors.append("browserTests 必须为有 reason 的 N/A/UNVERIFIED/TIMEOUT/RUNNING 声明")
    summary = payload.get("summary" if kind == "test" else "testSummary") or {}
    if not errors:
        expected = overall_status(payload)
        for key, value in (("overallStatus", expected), ("unitStatus", payload["unitTests"]["status"]),
                           ("browserStatus", browser_status(payload))):
            if summary.get(key) != value:
                errors.append(f"{key} 与 unitTests / 实测事实不一致，应为 {value}")
        routing = triage_state(payload)
        for key, value in (("triageStatus", routing["status"]), ("triageMissing", routing["missing"])):
            if key in summary and summary[key] != value:
                errors.append(f"{key} 与 failureTriage / 实测事实不一致")
        if kind == "exec" and expected != "PASS" and (payload.get("overview") or {}).get("statusKind") == "done":
            errors.append("overview.statusKind=done 不能掩盖未通过的单测/实测")
    return errors
