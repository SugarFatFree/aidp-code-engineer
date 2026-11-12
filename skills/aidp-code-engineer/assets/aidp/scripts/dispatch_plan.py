#!/usr/bin/env python3
"""light 任务并行派发判定：由各子任务预期写集/读写规模，确定性给出并行分组、串行名单、冲突文件与子 Agent prompt。

只做判定与 prompt 渲染，不授权、不执行、不改预算；委派资格仍由 execution_policy.py require-delegable 判定。
退出码：0 成功（decision 可为 serial）/ 2 输入错误。
"""
from __future__ import annotations

import argparse
import json
import posixpath
import sys

MIN_READS = 3    # 单个子任务至少读这么多文件
MIN_WRITES = 2   # 或至少改这么多文件

PROMPT_TEMPLATE = """你是父任务派发的子 Agent，只完成下列子任务 {task_id}。
- 父 execution_context：{execution_context}（原样沿用，不得新建任务身份）
- 动作 action：{action}（只在该父授权动作内工作；不得传入/追加任何 grant，不得 revise 授权，不得再向下派发）
- 剩余 budget：{budget}（共享父预算，每个实际动作先按 light-context 围栏预留）
- 本子任务写集（只允许修改这些文件，其余文件只读）：
{writes}
- 子任务说明：{summary}
- 测试范围：只跑本写集对应的相关测试（select_related_tests.py --write-set 推导），不跑全量、不跑目录级测试；不自行汇总全局测试，主 Agent 完成后统一做一次相关测试。
- 回传：改动文件清单、已做的静态检查结果、未解决问题；共享状态（ledger/activeContext/报告）由主流程串行写，不要改。"""


class InputError(Exception):
    pass


def _norm(path):
    p = str(path).strip().replace("\\", "/")
    if not p:
        raise InputError("写集含空路径")
    return posixpath.normpath(p)


def _overlap(a, b):
    """相同文件，或一方是另一方的目录前缀（以 / 或 /** 结尾的写集项）。"""
    if a == b:
        return True
    for x, y in ((a, b), (b, a)):
        base = x[:-3] if x.endswith("/**") else x[:-1] if x.endswith("/") else None
        if base is not None and (y == base or y.startswith(base.rstrip("/") + "/")):
            return True
    return False


def _count(value, label, default):
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InputError(f"{label} 必须是非负整数")
    return value


def parse_tasks(args):
    tasks = {}
    if args.tasks_json:
        raw = args.tasks_json
        if raw.startswith("@"):
            try:
                raw = open(raw[1:], encoding="utf-8").read()
            except OSError as exc:
                raise InputError(f"无法读取 {raw[1:]}: {exc}")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise InputError(f"--tasks-json 不是合法 JSON: {exc}")
        if isinstance(data, dict):
            data = [{"id": k, **(v if isinstance(v, dict) else {"writes": v})} for k, v in data.items()]
        if not isinstance(data, list):
            raise InputError("--tasks-json 须为数组或 {id: 写集} 对象")
        for item in data:
            if not isinstance(item, dict) or not item.get("id"):
                raise InputError("每个任务须含 id")
            tid = str(item["id"])
            writes = item.get("writes")
            if not isinstance(writes, list) or not writes:
                raise InputError(f"任务 {tid} 的 writes 须为非空数组")
            if tid in tasks:
                raise InputError(f"任务 id 重复: {tid}")
            tasks[tid] = {"writes": [_norm(w) for w in writes], "reads": item.get("reads"),
                          "summary": str(item.get("summary", ""))}
    for spec in args.task or []:
        tid, sep, files = spec.partition("=")
        tid = tid.strip()
        paths = [f for f in files.split(",") if f.strip()]
        if not sep or not tid or not paths:
            raise InputError(f"--task 须为 ID=file1,file2: {spec!r}")
        if tid in tasks:
            raise InputError(f"任务 id 重复: {tid}")
        tasks[tid] = {"writes": [_norm(f) for f in paths], "reads": None, "summary": ""}
    for spec in args.reads or []:
        tid, sep, num = spec.partition("=")
        if tid not in tasks or not sep or not num.strip().isdigit():
            raise InputError(f"--reads 须为已声明任务的 ID=N: {spec!r}")
        tasks[tid]["reads"] = int(num)
    for spec in args.writes or []:
        tid, sep, num = spec.partition("=")
        if tid not in tasks or not sep or not num.strip().isdigit():
            raise InputError(f"--writes 须为已声明任务的 ID=N: {spec!r}")
        tasks[tid]["write_count"] = int(num)
    if not tasks:
        raise InputError("未提供任何子任务（--tasks-json 或 --task）")
    for tid, t in tasks.items():
        t["reads"] = _count(t["reads"], f"任务 {tid} reads", 0)
        t["write_count"] = _count(t.get("write_count"), f"任务 {tid} writes", len(t["writes"]))
    return tasks


def plan(tasks):
    reasons, ids = [], list(tasks)
    eligible, serial = [], []
    for tid in ids:
        t = tasks[tid]
        if t["reads"] >= MIN_READS or t["write_count"] >= MIN_WRITES:
            eligible.append(tid)
        else:
            serial.append(tid)
            reasons.append(f"{tid} 未达并行阈值（读 {t['reads']}<{MIN_READS} 且改 {t['write_count']}<{MIN_WRITES}），主 Agent 直接做")
    conflicts, clashed = [], set()
    for i, a in enumerate(eligible):
        for b in eligible[i + 1:]:
            files = sorted({w for x in tasks[a]["writes"] for y in tasks[b]["writes"] if _overlap(x, y) for w in (x, y)})
            if files:
                clashed.update((a, b))
                for c in conflicts:
                    if c["files"] == files:
                        c["tasks"] = sorted(set(c["tasks"]) | {a, b})
                        break
                else:
                    conflicts.append({"files": files, "tasks": [a, b]})
    if clashed:
        reasons.append("写集有交集须串行：" + "、".join(sorted(clashed)))
    group = [t for t in eligible if t not in clashed]
    serial = [t for t in ids if t in serial or t in clashed]
    if len(group) >= 2:
        decision, groups = "parallel", [group]
        reasons.append(f"{len(group)} 个子任务写集互不相交且各达读/改阈值，默认并行派子 Agent")
        if serial:
            reasons.append("串行项在并行批全部完成后由主 Agent 依次处理：" + "、".join(serial))
    else:
        decision, groups = "serial", []
        if len(ids) < 2:
            reasons.append("仅单个子任务，无并行收益")
        elif not clashed or len(group) < 2:
            reasons.append("可并行的互不相交子任务不足 2 个")
        serial = ids
    return {"parallel_groups": groups, "serial": serial, "conflicts": conflicts,
            "decision": decision, "reasons": reasons, "prompts": []}


def emit_prompts(result, tasks, args):
    if not args.execution_context or not args.action or not args.budget:
        raise InputError("--emit-prompts 须同时给 --execution-context、--action、--budget")
    out = []
    for tid in (result["parallel_groups"][0] if result["parallel_groups"] else []):
        t = tasks[tid]
        out.append({"task_id": tid, "prompt": PROMPT_TEMPLATE.format(
            task_id=tid, execution_context=args.execution_context, action=args.action,
            budget=args.budget, writes="\n".join(f"  - {w}" for w in t["writes"]),
            summary=t["summary"] or "按父任务说明完成该写集内的改动")})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tasks-json", help='JSON 数组 [{"id","writes":[...],"reads":N,"summary"}] 或 @文件')
    ap.add_argument("--task", action="append", metavar="ID=f1,f2", help="子任务写集，可重复")
    ap.add_argument("--reads", action="append", metavar="ID=N", help="该子任务需读文件数，可重复")
    ap.add_argument("--writes", action="append", metavar="ID=N", help="覆盖该子任务改动文件数（默认=写集长度）")
    ap.add_argument("--emit-prompts", action="store_true")
    ap.add_argument("--execution-context", help="父 execution_context 路径")
    ap.add_argument("--action", help="子任务沿用的父授权动作，如 implement")
    ap.add_argument("--budget", help="父剩余预算摘要（文本或 JSON）")
    args = ap.parse_args(argv)
    try:
        tasks = parse_tasks(args)
        result = plan(tasks)
        if args.emit_prompts:
            result["prompts"] = emit_prompts(result, tasks, args)
    except InputError as exc:
        print(f"dispatch_plan: 输入错误: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
