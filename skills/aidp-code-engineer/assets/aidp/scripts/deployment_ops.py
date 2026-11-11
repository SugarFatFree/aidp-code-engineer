#!/usr/bin/env python3
"""部署小工具：共用真实备份记录限频、既有 baseline 待同步项、极简 SQL 指引。

不执行部署、恢复、Git 或测试；备份只调用项目已配置的 argv，不添加参数。
备份记录必须已由项目核对并建立；缺记录不能当成当天零次。
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
from uuid import uuid4
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from aidp_config import load
from baseline_edit import LockedBaseline


class PrerequisiteError(ValueError):
    pass


def instant(value):
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        raise PrerequisiteError("时间必须包含时区")
    return dt


def now():
    return datetime.now(timezone.utc)


def write_json(path, value):
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)


def target_id(value):
    return isinstance(value, str) and bool(re.fullmatch(r"[\w./:-]+", value)) and "://" not in value


def backup(root, kind, targets):
    config, ok = load(str(root))
    policy = config.get("deployment", {}).get("backup") if ok else None
    if not isinstance(policy, dict):
        raise PrerequisiteError("缺少可解析的项目 deployment.backup 策略")
    limit = policy.get("max_per_day")
    if type(limit) is not int or limit < 1:
        raise PrerequisiteError("max_per_day 必须是项目明确配置的正整数")
    zone = ZoneInfo(policy["timezone"])
    record = (root / policy["record_file"]).resolve()
    # 项目须接入唯一真实记录路径；禁止按 kind/env/version 拆开额度。
    if not record.is_file():
        raise PrerequisiteError("真实备份记录缺失；先核对项目历史，不能假定零次或已保护")
    import fcntl  # 锁不可用即失败，不能降级为无锁执行。
    with record.with_name(record.name + ".lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        ledger = json.loads(record.read_text(encoding="utf-8"))
        rows = ledger.get("backups")
        checked = instant(ledger["verified_at"])
        current = now()
        if not isinstance(rows, list) or checked > current:
            raise PrerequisiteError("真实备份记录结构或核对时间矛盾")
        today = current.astimezone(zone).date()
        ids, used, reusable = set(), 0, []
        required = set(targets)
        if not required or not all(target_id(item) for item in required):
            raise PrerequisiteError("必须明确数据库/服务数据目标")
        for row in rows:
            if row["id"] in ids or row["status"] not in {"running", "failed", "succeeded", "not-executed"}:
                raise PrerequisiteError("备份记录重复或状态矛盾")
            ids.add(row["id"])
            start = instant(row["started_at"])
            end = instant(row["finished_at"]) if row.get("finished_at") else current
            if start > current or end > current or end < start:
                raise PrerequisiteError("备份实际时间矛盾")
            if row["status"] == "not-executed" and (row.get("backed_up_at") or row.get("artifacts")):
                raise PrerequisiteError("未执行记录却含业务副本，不能绕过额度")
            if row["status"] == "running":
                raise PrerequisiteError("有未结清备份操作，先核验真实结果")
            if not row.get("finished_at"):
                raise PrerequisiteError("终态备份缺少结束时间")
            if (row["status"] != "not-executed"
                    and start.astimezone(zone).date() <= today <= end.astimezone(zone).date()):
                used += 1  # 失败可能已复制部分业务数据，同样占用本日操作额度。
            if row["status"] == "succeeded":
                captured = instant(row["backed_up_at"])
                if not start <= captured <= end:
                    raise PrerequisiteError("备份时点不在真实操作区间内")
                if (not isinstance(row.get("targets"), list) or not all(target_id(t) for t in row["targets"])
                        or not isinstance(row.get("artifacts"), list)):
                    raise PrerequisiteError("成功备份缺少覆盖范围/产物")
                if (captured.astimezone(zone).date() == today and required <= set(row["targets"])
                        and row["artifacts"] and all((root / p).is_file() and (root / p).stat().st_size
                                                    for p in row["artifacts"])):
                    reusable.append(row)
        if reusable:
            chosen = max(reusable, key=lambda row: instant(row["backed_up_at"]))
            public = {k: chosen[k] for k in ("id", "kind", "targets", "status", "started_at", "finished_at",
                                            "backed_up_at", "artifacts", "command_exit") if k in chosen}
            return {"status": "reused", "backup": public,
                    "skip_args": policy.get("skip_args", []),
                    "note": "只覆盖原备份时点；不保护之后新增业务数据，不自动恢复"}
        if used >= limit:
            raise PrerequisiteError("本日额度已用且无适用备份；目标保护有缺口，需明确例外授权，不自动扩容")
        # 经初始化核对的权威记录由全部入口持续共享；跨日自然重新计额，
        # 不要求人每天改 verified_at，也不把昨天的产物伪复用为今天备份。
        command = policy.get("commands", {}).get(kind)
        if not isinstance(command, list) or not command or any(not isinstance(p, str) for p in command):
            raise PrerequisiteError("项目没有该类型的既有备份命令，不能自行编造命令/flag")
        row = {"id": uuid4().hex, "kind": kind, "targets": sorted(required),
               "started_at": now().isoformat(), "status": "running"}
        rows.append(row)
        write_json(record, ledger)  # 调用前占位落盘，进程中断不能被当零次重试。
        started = False
        try:
            with subprocess.Popen(command, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True, start_new_session=True) as process:
                started = True
                try:
                    stdout, _stderr = process.communicate(timeout=policy.get("timeout_seconds", 3600))
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.communicate()
                    raise PrerequisiteError("备份超时；已启动操作的副作用未知，需核验")
                command_exit = process.returncode
            try:
                receipt = json.loads(stdout)
            except ValueError:
                raise PrerequisiteError("项目备份命令未提供成功回执，exit=" + str(command_exit))
            captured = instant(receipt["backed_up_at"])
            finished = now()
            if not instant(row["started_at"]) <= captured <= finished:
                raise PrerequisiteError("回执备份时点不在实际调用区间内")
            if (not isinstance(receipt["targets"], list) or not all(target_id(t) for t in receipt["targets"])
                    or not required <= set(receipt["targets"])):
                raise PrerequisiteError("备份回执未覆盖请求目标")
            artifacts = receipt["artifacts"]
            if not isinstance(artifacts, list) or not artifacts or not all(
                    isinstance(p, str) and (root / p).is_file() and (root / p).stat().st_size for p in artifacts):
                raise PrerequisiteError("备份产物缺失或为空，不能标成功")
            row.update(status="succeeded", backed_up_at=receipt["backed_up_at"],
                       targets=receipt["targets"], artifacts=artifacts, command_exit=command_exit)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            # 命令/回执可能含秘密：只输出固定分类；不转储 argv、stdout 或 stderr。
            detail = str(exc) if isinstance(exc, PrerequisiteError) else type(exc).__name__
            row.update(status="failed" if started else "not-executed", error=detail)
        row["finished_at"] = now().isoformat()
        try:
            write_json(record, ledger)
        except OSError:
            return {"status": "recording-failed", "operation_status": row["status"],
                    "backup": row, "reason": "实际操作与终态登记分离；禁止自动重跑备份"}
        status = "post-backup-failed" if row.get("command_exit") else row["status"]
        return {"status": status, "backup": row,
                "skip_args": policy.get("skip_args", []) if status == "succeeded" else []}


def pending(root, version, refs=None):
    path = root / "memory/.sprint-autopilot-baseline.json"
    with LockedBaseline(str(path), write=refs is not None) as state:
        by_version = state.data.setdefault("deployment_doc_pending", {})
        entries = by_version.setdefault(version, [])
        if refs is not None:
            for ref in refs:
                if ref not in entries:
                    entries.append(ref)
        return {"version": version, "pending_refs": entries}


def sql_ledger(root, version, phase, source):
    if phase not in {"planning", "release"}:
        return {"status": "deferred", **pending(root, version)}
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
    return {"status": "written", "path": str(output), **pending(root, version)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    sub = parser.add_subparsers(dest="action", required=True)
    b = sub.add_parser("backup")
    b.add_argument("--kind", required=True, choices=["database", "cold", "migration"])
    b.add_argument("--target", action="append", required=True)
    note_parser = sub.add_parser("note")
    note_parser.add_argument("--version", required=True)
    note_parser.add_argument("--ref", action="append", required=True)
    pending_parser = sub.add_parser("pending")
    pending_parser.add_argument("--version", required=True)
    ledger_parser = sub.add_parser("sql-ledger")
    ledger_parser.add_argument("--version", required=True)
    ledger_parser.add_argument("--phase", choices=["daily", "planning", "release"], required=True)
    ledger_parser.add_argument("--input")
    args = parser.parse_args()
    try:
        root = Path(args.root).resolve()
        if args.action != "backup" and (Path(args.version).name != args.version or args.version in {".", ".."}):
            raise PrerequisiteError("版本不能包含路径")
        if args.action == "backup":
            result = backup(root, args.kind, args.target)
        elif args.action == "sql-ledger":
            result = sql_ledger(root, args.version, args.phase, args.input)
        else:
            result = pending(root, args.version, args.ref if args.action == "note" else None)
        print(json.dumps(result, ensure_ascii=False))
        return 1 if result.get("status") in {"failed", "not-executed", "recording-failed", "post-backup-failed"} else 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "prerequisite-missing", "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
