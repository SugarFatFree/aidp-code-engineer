#!/usr/bin/env python3
"""正式发布：验证本版新增列的真实注释核验机器记录，不向运维 SQL 表塞报告。

证据位于既有 baseline 的 deployment_sql_checks.<version> 数组：每项含
script、sha256、database、checked_at（带时区）、columns:[{name, comment}]。
本工具不连库、不生成报告；只能由已授权的发布校准消费，不能扩为日常全库审计。
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys

_ADD_COL = re.compile(r"\bADD\s+COLUMN\b|\bADD\s*\(", re.I)


def _sql_files(root, version):
    base = Path(root) / "docs/deployment" / version / "sql/增量"
    # 仅本版增量；全量轨不是改表迁移，回退脚本亦不触发本次实查。
    return sorted(p for p in base.glob("*.sql") if not p.name.startswith("99_"))


def run(root, version):
    root = Path(root)
    res = {"version": version, "add_column_files": [], "status": "", "passed": False, "detail": ""}
    hashes = {}
    for file in _sql_files(root, version):
        try:
            text = file.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            res.update(status="sql-unreadable", detail=str(exc))
            return res
        # 注释内的示例 ADD COLUMN 不能触发实查。
        body = re.sub(r"/\*.*?\*/|--[^\n]*", "", text, flags=re.S)
        if _ADD_COL.search(body):
            hashes[file.relative_to(root).as_posix()] = hashlib.sha256(file.read_bytes()).hexdigest()
    res["add_column_files"] = list(hashes)
    if not hashes:
        res.update(status="no-add-column", passed=True, detail="本版增量无新增列，本门不适用")
        return res
    try:
        state = json.loads((root / "memory/.sprint-autopilot-baseline.json").read_text(encoding="utf-8"))
        entries = state.get("deployment_sql_checks", {}).get(version, [])
        if not isinstance(entries, list):
            raise ValueError("实查记录必须是数组")
        for script, digest in hashes.items():
            matches = [item for item in entries if isinstance(item, dict) and item.get("script") == script]
            if len(matches) != 1:
                raise ValueError(f"{script} 缺少唯一实查记录")
            item = matches[0]
            checked = datetime.fromisoformat(item["checked_at"])
            if checked.tzinfo is None or checked > datetime.now(timezone.utc):
                raise ValueError("实查时间缺时区或在未来")
            if item.get("sha256") != digest or not item.get("database"):
                raise ValueError(f"{script} 内容已变化或目标数据库缺失")
            cols = item.get("columns")
            if not isinstance(cols, list) or not cols:
                raise ValueError(f"{script} 未提供实际查库列结果")
            names = set()
            for col in cols:
                if (not isinstance(col, dict) or not str(col.get("name", "")).strip()
                        or not isinstance(col.get("comment"), str) or not col["comment"].strip()
                        or "{待填}" in col["comment"] or col["name"] in names):
                    raise ValueError(f"{script} 实查列缺注释、重复或仍为占位")
                names.add(col["name"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        res.update(status="evidence-missing", detail=str(exc))
        return res
    res.update(status="ok", passed=True, detail="本版新增列已留目标库、脚本哈希、真实时点和逐列注释实查记录")
    return res


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--version")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    if args.self_check:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from selfcheck import run_self_check
        return run_self_check(os.path.basename(__file__), json_out=args.json)
    if not Path(args.root).is_dir() or not args.version:
        parser.error("需要有效 --root 和 --version")
    result = run(args.root, args.version)
    print(json.dumps(result, ensure_ascii=False) if args.json else result["detail"])
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
