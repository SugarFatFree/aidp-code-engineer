#!/usr/bin/env python3
"""部署小工具：发布/规划期渲染极简 SQL 执行台账。

不执行部署、备份、恢复、Git 或测试；不读写 baseline。
"""
import argparse
import json
from pathlib import Path
import re
import sys


class PrerequisiteError(ValueError):
    pass


def target_id(value):
    return isinstance(value, str) and bool(re.fullmatch(r"[\w./:-]+", value)) and "://" not in value


def sql_ledger(root, version, phase, source):
    data = json.loads(Path(source).read_text(encoding="utf-8"))
    lines = [f"# {version} SQL 执行台账", ""]
    found = False
    for key, title, track in (("install", "手工新装", "全量"), ("upgrade", "手工升级", "增量"),
                              ("rollback", "手工回退", "增量")):
        rows = data.get(key, [])
        if not rows:
            continue
        found = True
        lines += [f"## {title}", "", "| 目标数据库 | SQL脚本路径（按执行顺序） |", "|---|---|"]
        for row in rows:
            target = row["database"]
            if not target_id(target):
                raise PrerequisiteError("目标数据库必须是无凭据的单行库标识")
            scripts = row["scripts"]
            if not isinstance(scripts, list) or not scripts:
                raise PrerequisiteError("手工 SQL 必须有实际脚本")
            rendered = []
            for name in scripts:
                relative = Path(name)
                base = root / "docs/deployment" / version / "sql" / track
                path = (root / relative).resolve()
                if (not path.is_relative_to(base.resolve()) or not path.is_file()
                        or path.suffix.lower() != ".sql" or any(c in name for c in "|\n\r`")):
                    raise PrerequisiteError("SQL 路径缺失或不属于对应全量/增量轨")
                rendered.append("`" + name + "`")
            lines.append("| " + target + " | " + " → ".join(rendered) + " |")
        lines.append("")
    if data.get("automatic") is True:
        lines += ["应用启动时自动迁移，无需重复手工执行。", ""]
    if not found and data.get("automatic") is not True:
        lines += ["本版本无须手工执行 SQL。", ""]
    if data.get("install") and data.get("upgrade"):
        lines += ["新装仅执行全量轨，已有环境升级仅执行增量轨；两套不可叠加。", ""]
    output = root / "docs/deployment" / version / "部署流程/SQL执行台账.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    return {"status": "written", "path": str(output)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    sub = parser.add_subparsers(dest="action", required=True)
    ledger_parser = sub.add_parser("sql-ledger")
    ledger_parser.add_argument("--version", required=True)
    ledger_parser.add_argument("--phase", choices=["planning", "release"], required=True)
    ledger_parser.add_argument("--input", required=True)
    args = parser.parse_args()
    try:
        root = Path(args.root).resolve()
        if Path(args.version).name != args.version or args.version in {".", ".."}:
            raise PrerequisiteError("版本不能包含路径")
        result = sql_ledger(root, args.version, args.phase, args.input)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "prerequisite-missing", "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
