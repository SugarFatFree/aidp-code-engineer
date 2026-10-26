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
# total_tokens：子 Agent 工具结果只给总量（不分输入/输出），如实记总量，⛔ 不拆分估算
USAGE_FIELDS = ("input_tokens", "output_tokens", "cache_read_tokens", "total_tokens", "tool_calls", "read_bytes")
WAIT_CATEGORIES = ("cicd", "auth", "browser", "overnight-idle", "other")
# SKILL 编排层协议的阶段打点行（SKILL 侧 qr_orchestration.py 生成）。
# 标记本身**不带时间**：必须在它出现的当下用 `stage --line` 落盘，事后批量导入拿不到真实时刻。
STAGE_LINE_RE = re.compile(r"^\[AIDP-STAGE\] (\{.*\})\s*$")
STAGE_KEYS = ("skill", "stage", "shard", "round", "event", "status")


def parse_stage_line(line):
    """解析一行打点 → (phase, round, event, status)；格式不符抛 ValueError。"""
    match = STAGE_LINE_RE.match(line.strip())
    if not match:
        raise ValueError("不是合法的 [AIDP-STAGE] 行")
    mark = json.loads(match.group(1))
    if not isinstance(mark, dict) or tuple(mark) != STAGE_KEYS:
        raise ValueError("[AIDP-STAGE] 字段必须恰好且按序为 " + "/".join(STAGE_KEYS))
    rnd = mark["round"]
    if not isinstance(mark["skill"], str) or not mark["skill"] or mark["stage"] not in ("generate", "qr", "fix") \
            or mark["event"] not in ("start", "end") or not isinstance(rnd, int) or isinstance(rnd, bool) or rnd < 0:
        raise ValueError("[AIDP-STAGE] 取值不合法")
    if mark["event"] == "end" and mark["status"] not in ("pass", "fail"):
        raise ValueError("[AIDP-STAGE] event=end 时 status 必须是 pass/fail")
    phase = mark["skill"] + ":" + mark["stage"] + ("@" + mark["shard"] if mark["shard"] else "")
    return phase, rnd, mark["event"], mark["status"]


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


def _cell(value):
    return "—" if value is None else str(value)


def render_markdown(result):
    """把汇总渲染成 规划耗时.md：用来定位瓶颈，⛔ 不参与任何质量门。"""
    rows = result["phases"]
    # 顶层阶段（requirements/design/plan/selftest/audit…）才计入合计；
    # 含 ":" 的是 SKILL 内部打点，与所属顶层阶段重叠，计入就重复了。
    top = [r for r in rows if ":" not in r["phase"] and r["wall_seconds"] is not None]
    known = [r for r in rows if r.get("total_tokens") is not None or r.get("input_tokens") is not None]
    lines = [f"# 规划耗时（{result['version']} · run {result['run_id']}）", "",
             "> 由 `aidp_run_metrics.py render` 生成。「—」= 未取到真实值，⛔ 不按篇幅估算。",
             "> 「未归类」是墙钟扣除已记录等待的余额，⛔ 不等于模型工作时间。", "",
             "## 汇总", "",
             f"- 顶层阶段墙钟合计：{round(sum(r['wall_seconds'] for r in top), 3)} s"
             f"（等待 {round(sum(r['wait_seconds'] or 0 for r in top), 3)} s）",
             f"- 有真实用量的阶段：{len(known)} / {len(rows)}",
             f"- 未结束的阶段：{sum(1 for r in rows if r['status'] == 'incomplete')}", "",
             "## 顶层阶段（按墙钟降序）", "",
             "| 阶段 | Agent | 轮次 | 墙钟(s) | 状态 |", "| :- | :- | :-: | -: | :- |"]
    by_wall = lambda rs: sorted(rs, key=lambda r: -r["wall_seconds"])
    lines += [f"| {r['phase']} | {r['agent']} | {r['retry_round']} | {r['wall_seconds']} | {r['status']} |"
              for r in by_wall(top)] or ["| — | — | — | — | — |"]
    # 瓶颈看这张：SKILL 内部打点（分片生成 / QR 轮 / 修复轮）。顶层阶段包含它们，混排永远排第一，定位不到瓶颈。
    inner = [r for r in rows if ":" in r["phase"] and r["wall_seconds"] is not None]
    lines += ["", "## 最慢的 5 个 SKILL 内部阶段", "",
              "| 阶段 | 轮次 | 墙钟(s) | 状态 |", "| :- | :-: | -: | :- |"]
    lines += [f"| {r['phase']} | {r['retry_round']} | {r['wall_seconds']} | {r['status']} |"
              for r in by_wall(inner)[:5]] or ["| —（本轮无 `[AIDP-STAGE]` 打点） | — | — | — |"]
    lines += ["", "## 全部阶段（按开始时间）", "",
              "| 阶段 | Agent | 轮次 | 状态 | 墙钟(s) | 等待(s) | 未归类(s) | token(总) | token(入/出) | 工具调用 | 产物行数 | 来源 |",
              "| :- | :- | :-: | :- | -: | -: | -: | -: | -: | -: | -: | :- |"]
    for r in sorted(rows, key=lambda r: instant(r["started_at"])):
        io = "—" if r.get("input_tokens") is None and r.get("output_tokens") is None else \
            f"{_cell(r.get('input_tokens'))}/{_cell(r.get('output_tokens'))}"
        lines.append(" | ".join(["", r["phase"], r["agent"], str(r["retry_round"]), r["status"],
                                 _cell(r["wall_seconds"]), _cell(r["wait_seconds"]),
                                 _cell(r["unclassified_seconds"]), _cell(r.get("total_tokens")), io,
                                 _cell(r.get("tool_calls")), _cell(r["artifact_lines"]),
                                 _cell(r.get("source")), ""]).strip())
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--version", required=True)
    parser.add_argument("--run-id", required=True)
    actions = parser.add_subparsers(dest="action", required=True)
    for name in ("start", "end", "wait", "summary", "stage", "render"):
        sub = actions.add_parser(name)
        if name == "stage":
            sub.add_argument("--line", required=True, help="SKILL 刚输出的一行 [AIDP-STAGE] 标记（原样传入）")
            sub.add_argument("--agent", default="main")
            sub.add_argument("--at")
            continue
        if name == "render":
            sub.add_argument("--out", help="缺省 docs/audit/{V}/规划耗时.md")
            continue
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
    if args.action == "stage":
        try:
            args.phase, args.retry_round, args.action, status = parse_stage_line(args.line)
        except (ValueError, json.JSONDecodeError) as exc:
            print(f"[aidp_run_metrics] {exc}", file=sys.stderr)
            return 2
        args.status = status or "pass"
        args.source, args.artifact, args.model_work_seconds = "stage-marker", [], None
        for field in USAGE_FIELDS:
            setattr(args, field, None)
    if args.action in ("summary", "render"):
        if not path.is_file():
            parser.error("未找到本次运行的计量文件")
        result = summarize(json.loads(path.read_text(encoding="utf-8")))
        if args.action == "render":
            out = Path(args.out) if args.out else folder / "规划耗时.md"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(render_markdown(result), encoding="utf-8")
            print(out.as_posix())
            return 0
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
