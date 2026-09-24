#!/usr/bin/env python3
"""记录版本规划阶段的实际耗时与可用计量，不推断模型用量。"""
import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from baseline_edit import lock_path

VALID_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
USAGE_FIELDS = ("input_tokens", "output_tokens", "cache_read_tokens", "tool_calls", "read_bytes")
WAIT_CATEGORIES = ("cicd", "auth", "browser", "overnight-idle", "other")


def instant(text):
    value = datetime.fromisoformat(text)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("时间必须携带时区")
    return value.timestamp()


def span_union(spans):
    merged = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return sum(end - start for start, end in merged)


def summarize(data):
    rows = []
    for event in data.get("phases", []):
        row = dict(event)
        start = instant(row["started_at"])
        end = instant(row["ended_at"]) if row.get("ended_at") else None
        row["wall_seconds"] = round(end - start, 3) if end is not None else None
        waits = row.pop("waits", [])
        row["wait_by_category"] = {}
        spans = []
        for wait in waits:
            left, right = instant(wait["from"]), instant(wait["to"])
            row["wait_by_category"][wait["category"]] = row["wait_by_category"].get(wait["category"], 0) + right - left
            if end is not None:
                left, right = max(left, start), min(right, end)
                if left < right:
                    spans.append((left, right))
        row["wait_seconds"] = round(span_union(spans), 3) if end is not None else None
        row["unclassified_seconds"] = round(max(0, row["wall_seconds"] - row["wait_seconds"]), 3) if end is not None else None
        row["artifact_lines"] = sum(item["lines"] for item in row.get("artifacts", [])) if row.get("artifacts") else None
        row["artifact_bytes"] = sum(item["bytes"] for item in row.get("artifacts", [])) if row.get("artifacts") else None
        for field in USAGE_FIELDS + ("model_work_seconds",):
            row.setdefault(field, None)
        if end is None:
            row["status"] = "incomplete"
        rows.append(row)
    return {"schema": 1, "run_id": data["run_id"], "version": data["version"], "phases": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--version", required=True)
    parser.add_argument("--run-id", required=True)
    actions = parser.add_subparsers(dest="action", required=True)
    for name in ("start", "end", "wait", "summary"):
        sub = actions.add_parser(name)
        if name != "summary":
            sub.add_argument("--phase", required=True)
            sub.add_argument("--agent", default="main")
            sub.add_argument("--retry-round", type=int, default=0)
        if name in ("start", "end"):
            sub.add_argument("--at")
        if name == "end":
            sub.add_argument("--status", choices=("pass", "warn", "block", "fail", "skipped"), default="pass")
            sub.add_argument("--source", default="provided")
            sub.add_argument("--artifact", action="append", default=[])
            sub.add_argument("--model-work-seconds", type=float)
            for field in USAGE_FIELDS:
                sub.add_argument("--" + field.replace("_", "-"), type=int)
        if name == "wait":
            sub.add_argument("--category", choices=WAIT_CATEGORIES, required=True)
            sub.add_argument("--from", dest="from_at", required=True)
            sub.add_argument("--to", dest="to_at", required=True)
        if name == "summary":
            sub.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if not all(VALID_ID.fullmatch(v) for v in (args.version, args.run_id)):
        parser.error("version/run-id 只能包含字母数字、点、下划线和连字符")
    root = Path(args.root).resolve()
    folder = root / "docs" / "audit" / args.version
    path = folder / ("metrics-" + args.run_id + ".json")
    if args.action == "summary":
        if not path.is_file():
            parser.error("未找到本次运行的计量文件")
        result = summarize(json.loads(path.read_text(encoding="utf-8")))
        print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else
              "\n".join(f"{r['phase']}: {r['status']}, wall={r['wall_seconds']}s" for r in result["phases"]))
        return 0
    from fcntl import LOCK_EX, flock
    folder.mkdir(parents=True, exist_ok=True)
    lock_file = Path(lock_path(str(path)))
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        with lock_file.open("a+") as lock:
            flock(lock.fileno(), LOCK_EX)
            data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"schema": 1, "version": args.version, "run_id": args.run_id, "phases": []}
            key = (args.phase, args.agent, args.retry_round)
            row = next((p for p in data["phases"] if (p["phase"], p["agent"], p["retry_round"]) == key), None)
            if args.action == "start":
                if row:
                    raise ValueError("阶段已经开始；重试须使用新的 retry-round")
                at = args.at or datetime.now(timezone.utc).isoformat()
                instant(at)
                data["phases"].append({"phase": args.phase, "agent": args.agent, "retry_round": args.retry_round,
                                       "started_at": at, "ended_at": None, "waits": [], "artifacts": [], "status": "incomplete"})
            else:
                if not row or row["ended_at"]:
                    raise ValueError("阶段未开始或已经结束")
                if args.action == "wait":
                    left, right = instant(args.from_at), instant(args.to_at)
                    if right <= left or left < instant(row["started_at"]):
                        raise ValueError("等待区间必须位于阶段开始之后，且结束晚于开始")
                    row["waits"].append({"category": args.category, "from": args.from_at, "to": args.to_at})
                else:
                    at = args.at or datetime.now(timezone.utc).isoformat()
                    if instant(at) < instant(row["started_at"]):
                        raise ValueError("阶段结束时间早于开始时间")
                    if any(instant(w["to"]) > instant(at) for w in row["waits"]):
                        raise ValueError("等待区间超出阶段结束时间")
                    artifacts = []
                    for name in args.artifact:
                        target = (root / name).resolve()
                        try:
                            relative = target.relative_to(root)
                        except ValueError:
                            raise ValueError("产物必须是仓库内现存文件")
                        if not target.is_file():
                            raise ValueError("产物必须是仓库内现存文件")
                        blob = target.read_bytes()
                        artifacts.append({"path": relative.as_posix(), "bytes": len(blob),
                                          "lines": len(blob.splitlines())})
                    if args.model_work_seconds is not None and (args.model_work_seconds < 0 or args.model_work_seconds > instant(at) - instant(row["started_at"])):
                        raise ValueError("模型工作耗时必须位于本阶段墙钟范围内")
                    row.update({"ended_at": at, "status": args.status, "source": args.source,
                                "artifacts": artifacts, "model_work_seconds": args.model_work_seconds})
                    for field in USAGE_FIELDS:
                        value = getattr(args, field)
                        if value is not None and value < 0:
                            raise ValueError("计量值不能为负数")
                        row[field] = value
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=folder, delete=False) as tmp:
                json.dump(data, tmp, ensure_ascii=False, indent=2)
                tmp_path = tmp.name
            os.replace(tmp_path, path)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"[aidp_run_metrics] {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
