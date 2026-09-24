#!/usr/bin/env python3
"""汇总已运行规划检查器的结果；不替代任何检查器或独立审计。"""
import argparse
import json
import posixpath
import sys
from pathlib import Path


SEVERITIES = {"Important": 1, "Critical": 2}


def aggregate(checks):
    if not isinstance(checks, list) or not checks:
        raise ValueError("必须提供非空检查器结果数组")
    output = {"status": "pass", "checks": [], "findings": []}
    found = {}
    for check in checks:
        source = check["source"]
        if (not check.get("executed") or not check.get("output_present")
                or check.get("exit_code") is None or check.get("scanned_files", 1) == 0
                or check.get("skipped") is True):
            status = "unavailable"
        elif check["exit_code"] not in (0, 1):
            status = "unavailable"
        elif check["exit_code"] == 1:
            status = "block"
        else:
            status = "pass"
        for issue in check.get("findings", []):
            if status == "pass":
                status = "block" if issue["severity"] == "Critical" else "warn"
            key = (issue["check_id"], posixpath.normpath(Path(issue["file"]).as_posix()), issue.get("anchor", ""))
            if key not in found:
                item = {"check_id": key[0], "file": key[1], "anchor": key[2],
                        "severity": issue["severity"], "sources": []}
                found[key] = item
                output["findings"].append(item)
            item = found[key]
            if SEVERITIES[issue["severity"]] > SEVERITIES[item["severity"]]:
                item["severity"] = issue["severity"]
            if source not in item["sources"]:
                item["sources"].append(source)
        output["checks"].append({"source": source, "status": status,
                                  "exit_code": check.get("exit_code") if check.get("executed") else None})
    statuses = {item["status"] for item in output["checks"]}
    if "block" in statuses or any(f["severity"] == "Critical" for f in output["findings"]):
        output["status"] = "block"
    elif "unavailable" in statuses:
        output["status"] = "unavailable"
    elif "warn" in statuses:
        output["status"] = "warn"
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="现有检查器执行清单 JSON")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = aggregate(json.loads(Path(args.input).read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"[version_preflight] {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else
          f"预检 {result['status']}：{len(result['checks'])} 项、{len(result['findings'])} 个问题")
    return 0 if result["status"] in ("pass", "warn") else 1


if __name__ == "__main__":
    sys.exit(main())
