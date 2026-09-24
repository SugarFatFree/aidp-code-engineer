#!/usr/bin/env python3
"""收集 QR 步骤 0 的原始机器门结果；维度结论仍由独立 QR 作出。

退出码:0 = 无待关注项;1 = 有待关注项(findings / unavailable / inconclusive);
2 = 入参或环境错(argparse 判定)。⚠️ 严重度分档不占退出码,权威结论读 --json 的
每项 `status`——本脚本是采集器,退出码只够粗筛。

状态语义:
  pass          跑完、有可核对的扫描范围、无发现
  findings      检出问题(rc=1 或 JSON 里有发现项)
  skipped       脚本自报 N/A 跳过 —— 不等于通过
  collector     采集器类脚本(退出码恒 0),发现项须由 QR 读 stdout
  inconclusive  跑完并自报结论,但**扫描范围不可核对**(脚本未报扫描数);
                ⛔ 不得读成通过,也不同于「没跑」
  unavailable   没跑 / 跑不了 / 输出不可解析 / 有 read_errors
"""

import argparse
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
import sys
import time
from pathlib import Path


CHECKS = (
    ("check_doc_split.py", ("--check-dict-enums", "--check-fragment"), False),
    ("check_upstream_reference.py", (), False),
    ("check_sql_version_isolation.py", (), False),
    ("check_http_client_config.py", (), False),
    ("check_cache_user_confirmed.py", (), False),
    ("check_field_impl_inventory.py", (), False),
    ("check_copy_landing_table.py", (), False),
    ("check_error_contract.py", (), False),
    ("check_lock_strategy.py", (), False),
    ("check_metric_spec.py", (), False),
    ("check_list_page_scale.py", (), False),
    ("check_upstream_call_log_spec.py", (), False),
    ("check_count_claim_table.py", (), False),
    ("check_render_merge_table.py", (), False),
    ("check_column_consumer_evidence.py", (), False),
    ("check_ddl_column_comment.py", (), False),
    ("check_permission_constraint.py", (), False),
    ("check_sibling_family_spec.py", (), False),
    ("check_enum_contract.py", (), False),
    ("check_money_field.py", (), False),
    ("check_er_and_fk.py", (), False),
    ("check_index_not_null.py", (), False),
    ("check_unit_field.py", (), False),
    ("check_audit_field_fill.py", (), True),
    ("check_third_party_mock_runtime.py", (), False),
)


def scan_count(data):
    if isinstance(data, list):
        return len(data)
    for key in ("files_scanned", "scanned_files", "docs_scanned", "total_md", "files"):
        value = data.get(key)
        if isinstance(value, list):
            return len(value)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    summary = data.get("summary")
    return scan_count(summary) if isinstance(summary, dict) else None


def has_findings(data):
    if isinstance(data, list):
        return any(has_findings(item) for item in data if isinstance(item, dict))
    # ⚠️ 本表必须 ⊇ **被采集脚本实际输出的计数键名**,新增脚本须逐个核对。
    #    实测 check_metric_spec / check_error_contract / check_lock_strategy /
    #    check_upstream_call_log_spec 用 `criticals`,check_index_not_null 用 `violations`;
    #    它们当前都在有违规时 return 1,故 rc 通道兜住了 —— 但那是**脆弱耦合**:
    #    任一脚本改成「Important 不占退出码」,这里就会把它误标成 pass(假绿)。
    for key in ("findings", "issues", "importants", "warnings", "problems",
                "criticals", "violations"):
        value = data.get(key)
        if isinstance(value, list) and value:
            return True
        if isinstance(value, int) and value > 0:
            return True
    return data.get("passed") is False


def _collect_sequential(script_dir, target, checks, sql_root=None, version=None,
                        requirements=None):
    entries = []
    for name, flags, collector in checks:
        entry = {"script": name, "status": "unavailable", "returncode": None,
                 "command": None, "stdout": "", "stderr": "", "parsed": None,
                 "scanned": None, "skipped": None, "read_errors": [],
                 "important": [], "incomplete": False, "elapsed_ms": None}
        if name == "check_sql_version_isolation.py" and (not sql_root or not version):
            # ⚠️ 「调用方没要求跑」≠「想跑但跑不了」。本项需要 --sql-root + --version,
            #    两者缺省时把它标 unavailable 会让**默认调用恒非 0**,采集器退化成噪声
            #    (与本文件对 ATTENTION 的自述直接相抵)。故单列 not-requested:
            #    ⛔ **它同样不等于通过** —— 仍逐项出现在 --json 与人读输出里,
            #    只是不占退出码,「没跑」这件事必须始终可见。
            entry["status"] = "not-requested"
            entry["stderr"] = "未取到 SQL 根目录或版本;本项未运行(调用方未要求)"
            entries.append(entry)
            continue
        path = Path(script_dir) / name
        if not path.is_file():
            entry["stderr"] = "检查脚本不存在"
            entries.append(entry)
            continue
        command = [sys.executable, str(path),
                   str(sql_root if name == "check_sql_version_isolation.py" else target),
                   *flags]
        if name == "check_sql_version_isolation.py":
            command.extend(("--version", version))
        if name == "check_permission_constraint.py" and requirements:
            command.extend(("--requirements", str(requirements)))
        command.append("--json")
        entry["command"] = command
        started = time.monotonic()
        try:
            result = subprocess.run(command, text=True, capture_output=True,
                                    timeout=60, check=False)
            entry.update(returncode=result.returncode, stdout=result.stdout,
                         stderr=result.stderr)
            if result.stdout.strip():
                try:
                    parsed = json.loads(result.stdout)
                except ValueError:
                    parsed = None
                if isinstance(parsed, (dict, list)):
                    entry["parsed"] = parsed
                    # ⚠️ parsed 可用时丢掉 stdout 原文:两者是**同一份内容**,
                    #    双写让 --json 体量翻倍(实测单文件设计 1.3 KB → 57 KB,
                    #    其中 16 KB stdout + 11 KB parsed 完全重复)。
                    #    ⛔ 解析失败(parsed is None)时必须保留原文 —— 那是唯一需要它的场景。
                    entry["stdout"] = ""
                    entry["scanned"] = scan_count(parsed)
                    read_errors = parsed.get("read_errors") if isinstance(parsed, dict) else None
                    skipped = parsed.get("skipped") if isinstance(parsed, dict) else None
                    entry["read_errors"] = read_errors if isinstance(read_errors, list) else []
                    entry["skipped"] = skipped
                    entry["important"] = important_items(parsed)
                    entry["incomplete"] = bool(read_errors)
                    if result.returncode == 1 or has_findings(parsed):
                        entry["status"] = "findings"
                    elif read_errors:
                        entry["status"] = "unavailable"
                    elif result.returncode == 0:
                        if skipped:
                            entry["status"] = "skipped"
                        elif collector:
                            entry["status"] = "collector"
                        elif entry["scanned"] is not None and entry["scanned"] > 0:
                            entry["status"] = "pass"
                        elif entry["scanned"] is None:
                            # 跑完并自报了结论,但脚本没报扫描数(如 check_http_client_config.py
                            # 全通过时只出 file/passed/results)。既不能冒充 pass(范围不可
                            # 核对),也不能与「根本没跑」同标 unavailable —— 那正是本采集器
                            # 要消除的歧义。
                            # ⚠️ 只认「范围未知」(None)。**扫描数为 0 不在此列** —— 那是
                            #    明确的零扫描,按全仓铁律必须留在 unavailable,⛔ 别合并两者。
                            entry["status"] = "inconclusive"
                            entry["incomplete"] = True
            if result.returncode == 1:
                entry["status"] = "findings"
                entry["incomplete"] = entry["incomplete"] or entry["parsed"] is None or not entry["scanned"]
            elif result.returncode == 2:
                entry["status"] = "unavailable"
                entry["incomplete"] = True
            # 即使脚本正常退出，未知扫描范围也必须交给 QR 核实。
        except (OSError, subprocess.TimeoutExpired) as exc:
            entry["stderr"] = str(exc)
        entry["elapsed_ms"] = round((time.monotonic() - started) * 1000)
        entries.append(entry)
    return entries


def important_items(data):
    if isinstance(data, list):
        return [item for row in data if isinstance(row, dict)
                for item in important_items(row)]
    items = []
    for key in ("importants", "important", "warnings"):
        value = data.get(key)
        if isinstance(value, list):
            items.extend(value)
    for key in ("findings", "issues"):
        value = data.get(key)
        if isinstance(value, list):
            items.extend(item for item in value if isinstance(item, dict)
                         and item.get("level") == "Important")
    return items


def collect(script_dir, target, checks=CHECKS, sql_root=None, version=None,
            requirements=None, workers=1):
    if not 1 <= workers <= 4:
        raise ValueError("workers 必须在 1~4 之间")
    if workers == 1:
        return _collect_sequential(script_dir, target, checks, sql_root,
                                   version, requirements)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(
            lambda check: _collect_sequential(script_dir, target, (check,),
                                              sql_root, version, requirements)[0],
            checks,
        ))


STATUSES = ("pass", "skipped", "not-requested", "inconclusive", "unavailable",
            "collector", "findings")
# 待 QR 关注的状态:⛔ 不含 skipped/collector/not-requested —— 那三档由 QR 按各自判据读,
# 压进退出码会让本采集器几乎恒非 0、退化成噪声。
# ⚠️ 三者都**不等于通过**,只是不占退出码;它们在 --json 与人读输出里逐项可见。
ATTENTION = ("findings", "unavailable", "inconclusive")


def exit_code(entries):
    """1 = 有待关注项;0 = 没有。⛔ 不返回 2 —— 全仓约定里 2 专指入参/环境错。"""
    return 1 if any(e["status"] in ATTENTION for e in entries) else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path, help="详细设计文档目录")
    parser.add_argument("--sql-root", type=Path, help="SQL 版本检查的根目录")
    parser.add_argument("--version", help="当前版本，供 SQL 版本检查使用")
    parser.add_argument("--requirements", type=Path, help="研发需求目录，供权限约束检查使用")
    parser.add_argument("--json", action="store_true", help="输出全部原始结果")
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=1,
                        metavar="1..4", help="只读脚本的并发数，默认串行")
    args = parser.parse_args()
    # ⚠️ 两件事必须分开:exit 2 按全仓约定会被调用方读成「入参错、不计维度失败」,
    #    把「目录存在但一个 .md 都没有」也归进去,等于让**空的设计目录**被静默放过。
    if not args.target.exists() or not args.target.is_dir():
        parser.error("详细设计目录不存在或不是目录")
    if args.sql_root is not None and not args.sql_root.is_dir():
        parser.error("SQL 根目录不存在")
    if args.requirements is not None and not args.requirements.exists():
        parser.error("研发需求路径不存在")
    entries = collect(Path(__file__).parent, args.target, sql_root=args.sql_root,
                      version=args.version, requirements=args.requirements,
                      workers=args.workers)
    markdown_files = sum(1 for _ in args.target.rglob("*.md"))
    output = {"target": str(args.target), "markdown_files": markdown_files,
              "checks": entries,
              "summary": {status: sum(e["status"] == status for e in entries)
                          for status in STATUSES}}
    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        for entry in entries:
            print("{script}: {status} (rc={returncode}, scanned={scanned})".format(**entry))
    return exit_code(entries)


if __name__ == "__main__":
    sys.exit(main())
