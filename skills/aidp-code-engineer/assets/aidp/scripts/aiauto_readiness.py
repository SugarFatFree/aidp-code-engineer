#!/usr/bin/env python3
"""消费运行时取证，给客户端用例提供前置状态；绝不产 pass。

★ 「客户端 MCP 能力」是**跨端**功能点（Web / 小程序 / 移动 / 桌面），WebMCP 只是 Web 端实现。
声明判定的唯一实现 = `check_client_mcp.py`；本脚本只消费**运行期取证**，不自行探测、不读驱动信息。
⛔ 测试驱动（chrome-devtools / Appium / 小程序驱动）可用**不是**应用提供 MCP 能力的证据——
故 `driver_*` 一类事实在这里**根本不参与判定**，声明缺失时该类用例一律 block。
存量 Web 项目的 `webmcp_declared` / `webmcp_entry_available` / `requires_webmcp` 继续作为别名接收。

四态与上游 `auto-test-runner/references/driver-client-mcp.md` 一一对应（⛔ 别在两处各立一套）：
  declared     ↔ client_mcp_declared        registration ↔ registered_tools
  entry        ↔ client_mcp_entry_available invocation   ↔ invoked_tools + invocation_evidence
专项用例前置缺失的 `block_reason` 取上游枚举 `precondition-unmet`。
"""
import argparse
import json
import sys
from pathlib import Path


def _pick(facts, primary, legacy):
    """新字段优先；未给才回落存量别名（⛔ 不合并：两个都给且相反时以新字段为准并保持可见）。"""
    return facts[primary] if primary in facts else facts.get(legacy)


def assess(facts, cases):
    if not isinstance(facts, dict) or not isinstance(cases, list):
        raise ValueError("facts 必须为对象，cases 必须为数组")
    tools = facts.get("registered_tools")
    if tools is not None and not isinstance(tools, list):
        raise ValueError("registered_tools 必须为数组或 null")
    invoked = facts.get("invoked_tools")
    if invoked is not None and (not isinstance(invoked, list) or any(not isinstance(n, str) for n in invoked)):
        raise ValueError("invoked_tools 必须为工具名字符串数组或 null")

    declared = _pick(facts, "client_mcp_declared", "webmcp_declared")
    entry_available = _pick(facts, "client_mcp_entry_available", "webmcp_entry_available")
    client_type = facts.get("client_type") or (
        "web" if any(k.startswith("webmcp_") for k in facts) else None)

    evidence = facts.get("invocation_evidence")
    evidence_tools = ({item["tool"] for item in evidence
                       if isinstance(item, dict) and isinstance(item.get("tool"), str) and item.get("artifact")}
                      if isinstance(evidence, list) else set())
    registered_names = {item if isinstance(item, str) else item.get("name")
                        for item in (tools or []) if isinstance(item, (str, dict))}
    # 声称调用 ≠ 调用过：必须同时有「本端已注册该工具」与「该次调用的证据产物」
    inconsistent = bool(invoked) and (not tools or not set(invoked).issubset(evidence_tools & registered_names))

    result = {"client_mcp": {"client_type": client_type,
                             "declared_enabled": declared,
                             "entry_available": entry_available,
                             "registered_tools": len(tools) if tools is not None else None,
                             "invoked_tools": [] if inconsistent else invoked,
                             "evidence_status": "inconsistent: missing registration or invocation evidence"
                                                if inconsistent else "recorded"},
              "registered_tools": len(tools) if tools is not None else None, "cases": []}

    for case in cases:
        row = {"id": case["id"], "status": "ready", "block_reason": None, "reason": None}
        for field, block_reason in (("auth_instance_ok", "env-unavailable"),
                                    ("account_ok", "account-invalid"),
                                    ("protected_api_ok", "network-error"),
                                    ("deploy_fingerprint_ok", "env-unavailable")):
            value = facts.get(field)
            if value is False:
                row.update(status="block", block_reason=block_reason, reason=field)
                break
            if value is not True:
                row.update(status="unverified", reason=field)
                break
        if row["status"] == "ready" and case.get("requires_fault_injection"):
            value = facts.get("fault_injection_available")
            if value is False:
                row.update(status="block", block_reason="precondition-unmet", reason="fault_injection_available")
            elif value is not True:
                row.update(status="unverified", reason="fault_injection_available")
        if row["status"] == "ready" and (case.get("requires_client_mcp") or case.get("requires_webmcp")):
            # ★ block_reason 与上游 auto-test-runner 口径一致：应用 MCP 专项用例的前置缺失
            #   一律 `precondition-unmet`（不是 env-unavailable——那是"被测环境整体不可用"）。
            #   两者同属 gen_report.ENV_BLOCK_REASONS，都不会被编号成产品缺陷。
            if declared is not True:
                row.update(status="block", block_reason="precondition-unmet", reason="client_mcp_declared")
            elif entry_available is False or tools == []:
                row.update(status="block", block_reason="precondition-unmet", reason="client_mcp_tools_unavailable")
            elif entry_available is not True or tools is None:
                row.update(status="unverified", reason="client_mcp_tools_unverified")
        result["cases"].append(row)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    args = parser.parse_args()
    try:
        data = json.loads(Path(args.input).read_text(encoding="utf-8"))
        output = assess(data["facts"], data["cases"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"[aiauto_readiness] {exc}", file=sys.stderr)
        return 2
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 1 if output["client_mcp"]["evidence_status"].startswith("inconsistent") or any(
        c["status"] != "ready" for c in output["cases"]) else 0


if __name__ == "__main__":
    sys.exit(main())
