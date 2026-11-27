#!/usr/bin/env python3
"""light 任务并行派发判定：由各子任务预期写集/读写规模，确定性给出并行分组、串行名单、冲突文件与子 Agent prompt。

只做判定与 prompt 渲染，不授权、不执行、不改预算；委派资格仍由 execution_policy.py require-delegable 判定。
退出码：0 成功（decision 可为 serial）/ 2 输入错误。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

from entry_context import ContextError, _relative_path, load_context, identity_hash
import execution_policy as policy

MIN_READS = 3    # 单个子任务至少读这么多文件
MIN_WRITES = 2   # 或至少改这么多文件

PROMPT_TEMPLATE = """你是父任务派发的子 Agent，只完成下列子任务 {task_id}。
- 父 execution_context：{execution_context}（只用于归属核对，不用于子任务执行）
- 本子任务 execution_context：{child_context}；显式设置 AIDP_EXECUTION_CONTEXT 为此路径，所有静态/选测/测试命令均传此受限 context，保留分片文件。
- 动作 action：{action}（只在该子 context 已授权动作内工作；不得传入/追加任何 grant，不得 revise 授权或写集，不得再向下派发）
- 剩余 budget：{budget}（共享父预算，每个实际动作先按 light-context 围栏预留）
- 本子任务写集（只允许修改这些文件，其余文件只读）：
{writes}
- 子任务说明：{summary}
- 验证顺序：先静态，再选测，再测试。只跑本写集对应的相关测试；选测用 light_task.py select --execution-context 子路径，测试用 run，均使用子目录中的 unit-scope.json/状态文件；缺少 related-test 授权时回报未执行，不补 grant。
- 不跑全量或目录级测试；禁止写父 context 目录的 scope/状态/报告。主 Agent 在合并后独占最终总 scope、合并验证与汇总，保留子分片证据。
- 回传：改动文件清单、静态结果、子 scope/运行证据路径、未解决问题；业务共享状态（ledger/activeContext/总报告）由主流程串行写。"""


class InputError(Exception):
    pass


def _norm(path, root):
    if not isinstance(path, str) or not path.strip():
        raise InputError('写集必须是非空路径文本')
    p = path.strip()
    marker = '/**' if p.endswith('/**') else '/' if p.endswith('/') else ''
    base = p[:-3] if marker == '/**' else p
    if any(char in base for char in ('\\', '*', '?', '[', ']', '\x00', '\n', '\r')) or re.match(r'^[A-Za-z]:', base):
        raise InputError('写集必须是安全的项目相对路径；只支持目录尾部 /** 标记')
    try:
        normalized = _relative_path(root, base)
    except ContextError as exc:
        raise InputError(str(exc)) from exc
    return normalized + marker


def _base(path):
    return path[:-3] if path.endswith('/**') else path.rstrip('/')


def _overlap(a, b):
    """保守按组件前缀比较普通目录及显式目录，不依赖文件是否已创建。"""
    a, b = _base(a), _base(b)
    return a == b or a.startswith(b + '/') or b.startswith(a + '/')


def _count(value, label, default):
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InputError(f"{label} 必须是非负整数")
    return value


def parse_tasks(args):
    tasks = {}
    root = Path(args.root).resolve()
    if not root.is_dir():
        raise InputError('root 必须是现存目录')
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
            tasks[tid] = {"writes": [_norm(w, root) for w in writes], "reads": item.get("reads"),
                          "summary": str(item.get("summary", ""))}
    for spec in args.task or []:
        tid, sep, files = spec.partition("=")
        tid = tid.strip()
        paths = [f for f in files.split(",") if f.strip()]
        if not sep or not tid or not paths:
            raise InputError(f"--task 须为 ID=file1,file2: {spec!r}")
        if tid in tasks:
            raise InputError(f"任务 id 重复: {tid}")
        tasks[tid] = {"writes": [_norm(f, root) for f in paths], "reads": None, "summary": ""}
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
    children = {}
    for spec in args.child_context or []:
        tid, sep, path = spec.partition('=')
        if not sep or not path or tid not in tasks or tid in children:
            raise InputError('--child-context 须为唯一已声明任务的 ID=PATH')
        children[tid] = path
    group = result['parallel_groups'][0] if result['parallel_groups'] else []
    if set(children) != set(group):
        raise InputError('--emit-prompts 必须为每个并行任务提供且仅提供一个 --child-context ID=PATH')
    if not group:
        return []
    root = Path(args.root).resolve()
    parent = load_context(root, args.execution_context, migrate=False)
    if parent['mode'] != 'light' or 'parent_task_id' in parent:
        raise InputError('light 派发必须来自父 light 根 context')
    policy.require_delegable(parent, args.action)
    out = []
    for tid in group:
        t = tasks[tid]
        child = load_context(root, children[tid], migrate=False)
        if (child.get('parent_task_id') != parent['task_id']
                or child.get('parent_identity_hash') != identity_hash(parent)
                or child.get('child_key') != tid or child['status'] != 'active'
                or child['write_set'] != sorted({_base(path) for path in t['writes']})):
            raise InputError('子 context 与父身份、任务标识或声明写集不一致：' + tid)
        policy.require_action(child, args.action)
        out.append({'task_id': tid, 'execution_context': children[tid], 'prompt': PROMPT_TEMPLATE.format(
            task_id=tid, execution_context=args.execution_context, child_context=children[tid], action=args.action,
            budget=args.budget, writes='\n'.join(f'  - {w}' for w in t['writes']),
            summary=t['summary'] or '按父任务说明完成该写集内的改动')})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', default='.', help='项目根，用于校验写集路径与子 context')
    ap.add_argument('--child-context', action='append', metavar='ID=PATH', help='主流程预先 fork 的受限子 context')
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
    except (InputError, ContextError, policy.PolicyError, OSError) as exc:
        print(f"dispatch_plan: 输入错误: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
