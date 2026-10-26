#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从研发执行计划导出「REQ → 首个承接 Task」映射(供编排层回填自测用例的 ⟨PLAN-REF:REQ-xxx⟩ 占位符)。

口径单一信源:references/output-format.md「Task 锚点与 REQ 承接映射」。

  python export_plan_refs.py <执行计划文件或目录> [--cases-dir <用例目录>] [--out plan_refs.json] [--json]

读三样东西,全部来自计划本身、⛔ 不推断:
  · Task 抬头上一行的锚点 `<a id="task-<phase>-<seq>"></a>`(编号必须与 `### Task <phase>.<seq>` 一致);
  · Task 抬头元信息行里的 `**Sprint**: Sprint-NNN`(每个 Task 恰好一个);
  · 9 列任务总表的「Task」与「REQ 关联」两列(一行可承接多条 REQ)。

一条 REQ 被多个 Task 承接时取 **Sprint 号最小**、其次 **Task 号最小**(Phase、序号按数值比,⛔ 不按字符串)。
输出形如 {"REQ-104": {"label": "Sprint-001 Task 2.2", "href": "../plans/V1/01_研发执行计划.md#task-2-2"}}。
`href` 是计划文件相对 `--cases-dir`(缺省当前目录)的路径——**按用例目录根算**,用例分在子目录时编排层须按子目录分别导出。

**全有或全无**:任一 Task 缺锚点 / 锚点编号不符 / 缺 Sprint / Sprint 不唯一 / 总表引用了不存在的 Task / 缺任务总表
→ 报出全部问题、`--out` 一个字都不写、exit 1。没被任何 Task 承接的 REQ 不进映射(⛔ 不替它挑一个 Task),
下游 `⟨PLAN-REF⟩` 替换会因此找不到映射而拒绝,这正是想要的结果。

退出码:0 = 已导出,或计划里一个 Task 都没有(`skipped: true`,⚠️ 不等于通过) / 1 = 有上述问题 /
2 = 入参错(路径不存在、读不出、`--cases-dir` 不是目录)。
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_task_granularity import REQ_ID_CORE  # noqa: E402  同 SKILL 内复用需求编号判据

REQ_ID_RE = re.compile(REQ_ID_CORE)
TASK_HEAD_RE = re.compile(r"^#{3,4}\s+Task\s+(\d+)\.(\d+)\s*[:：]?")
ANCHOR_RE = re.compile(r'^<a\s+id="(task-\d+-\d+)"\s*>\s*</a>\s*$')
SPRINT_FIELD_RE = re.compile(r"\*\*Sprint\*\*\s*[:：]\s*([^|\n]+)")
SPRINT_ID_RE = re.compile(r"Sprint-(\d+)")
ROW_TASK_RE = re.compile(r"^Task\s+(\d+)\.(\d+)$")
NEXT_HEAD_RE = re.compile(r"^#{1,6}\s")


def split_row(line):
    cells = re.split(r"(?<!\\)\|", line.strip())
    if cells and cells[0].strip() == "":
        cells = cells[1:]
    if cells and cells[-1].strip() == "":
        cells = cells[:-1]
    return [c.strip() for c in cells]


def parse_file(path: Path, text: str, tasks, table_rows, issues):
    lines = text.splitlines()
    in_fence = False
    prev_nonblank = None
    i = 0
    header = None
    while i < len(lines):
        ln = lines[i]
        s = ln.strip()
        if s.startswith("```") or s.startswith("~~~"):
            in_fence = not in_fence
            i += 1
            continue
        if in_fence:
            i += 1
            continue
        m = TASK_HEAD_RE.match(ln)
        if m:
            p, q = int(m.group(1)), int(m.group(2))
            key = (p, q)
            want = f"task-{p}-{q}"
            anchor = None
            am = ANCHOR_RE.match(prev_nonblank or "")
            if am:
                anchor = am.group(1)
                if anchor != want:
                    issues.append({"type": "task_anchor_mismatch", "file": str(path), "line": i + 1,
                                   "msg": f"Task {p}.{q} 的锚点是 {anchor},应为 {want}"})
                    anchor = None
            else:
                issues.append({"type": "task_anchor_missing", "file": str(path), "line": i + 1,
                               "msg": f'Task {p}.{q} 抬头上一行缺锚点 <a id="{want}"></a>'})
            sprints = []
            j = i + 1
            while j < len(lines) and not NEXT_HEAD_RE.match(lines[j]):
                fm = SPRINT_FIELD_RE.search(lines[j])
                if fm:
                    sprints.extend(SPRINT_ID_RE.findall(fm.group(1)))
                j += 1
            sprint = None
            if not sprints:
                issues.append({"type": "task_sprint_missing", "file": str(path), "line": i + 1,
                               "msg": f"Task {p}.{q} 抬头缺 **Sprint**: Sprint-NNN 字段"})
            elif len(set(int(x) for x in sprints)) > 1:
                issues.append({"type": "task_sprint_ambiguous", "file": str(path), "line": i + 1,
                               "msg": f"Task {p}.{q} 写了多个 Sprint({', '.join('Sprint-' + x for x in sprints)}),每个 Task 只能归属一个"})
            else:
                sprint = "Sprint-" + sprints[0]
            if key in tasks:
                issues.append({"type": "task_duplicate", "file": str(path), "line": i + 1,
                               "msg": f"Task {p}.{q} 重复出现(首次在 {tasks[key]['file']}:{tasks[key]['line']})"})
            else:
                tasks[key] = {"file": path, "line": i + 1, "anchor": anchor, "sprint": sprint}
            prev_nonblank = ln
            i += 1
            continue
        if s.startswith("|"):
            cells = split_row(s)
            if cells and cells[0] == "Task" and any("REQ 关联" in c for c in cells):
                header = (cells.index("Task"), next(k for k, c in enumerate(cells) if "REQ 关联" in c))
            elif header and not re.match(r"^:?-+:?$", cells[0] if cells else ""):
                if len(cells) > max(header):
                    tm = ROW_TASK_RE.match(cells[header[0]])
                    if tm:
                        table_rows.append({"task": (int(tm.group(1)), int(tm.group(2))),
                                           "reqs": REQ_ID_RE.findall(cells[header[1]]),
                                           "file": str(path), "line": i + 1})
        else:
            header = None if s else header
        if s:
            prev_nonblank = ln
        i += 1


def main() -> int:
    ap = argparse.ArgumentParser(description="导出 REQ → 首个承接 Task 映射(⟨PLAN-REF⟩ 回填用)")
    ap.add_argument("target", help="研发执行计划文件或目录")
    ap.add_argument("--cases-dir", default=".", help="自测用例目录根(href 相对它计算,缺省当前目录)")
    ap.add_argument("--out", help="映射 JSON 写到此文件(有任何问题时不写)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    target = Path(args.target)
    if not target.exists():
        print(f"路径不存在: {target}", file=sys.stderr)
        return 2
    cases_dir = Path(args.cases_dir)
    if not cases_dir.is_dir():
        print(f"--cases-dir 不是目录: {cases_dir}", file=sys.stderr)
        return 2
    files = [target] if target.is_file() else sorted(target.glob("*.md"))

    tasks, rows, issues = {}, [], []
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"读不出: {f} ({exc})", file=sys.stderr)
            return 2
        parse_file(f, text, tasks, rows, issues)

    if not tasks:
        out = {"skipped": True, "reason": "未识别到任何 `### Task X.Y` 抬头", "mapping": {}, "issues": []}
        print(json.dumps(out, ensure_ascii=False) if args.json else "⚠️ 未识别到任何 Task,跳过(不等于通过)")
        return 0
    if not rows:
        issues.append({"type": "req_table_missing", "file": str(target), "line": 0,
                       "msg": "缺 9 列任务总表(表头须含「Task」与「REQ 关联」两列),无法确定 REQ 承接关系"})

    candidates = {}
    for r in rows:
        t = tasks.get(r["task"])
        if t is None:
            issues.append({"type": "task_not_found", "file": r["file"], "line": r["line"],
                           "msg": "任务总表引用了 Task {}.{},但计划里没有这个 Task 小节".format(*r["task"])})
            continue
        for req in r["reqs"]:
            candidates.setdefault(req, set()).add(r["task"])

    mapping = {}
    for req in sorted(candidates):
        usable = [k for k in candidates[req] if tasks[k]["anchor"] and tasks[k]["sprint"]]
        if len(usable) != len(candidates[req]):
            continue  # 缺锚点/Sprint 的 Task 已在 issues 里;不在残缺信息上挑「最小」
        best = min(usable, key=lambda k: (int(SPRINT_ID_RE.search(tasks[k]["sprint"]).group(1)), k))
        t = tasks[best]
        rel = os.path.relpath(t["file"].resolve(), cases_dir.resolve()).replace(os.sep, "/")
        mapping[req] = {"label": "{} Task {}.{}".format(t["sprint"], *best), "href": f"{rel}#{t['anchor']}"}

    ok = not issues
    if ok and args.out:
        Path(args.out).write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps({"skipped": False, "tasks": len(tasks), "reqs": len(candidates),
                          "mapping": mapping if ok else {}, "issues": issues}, ensure_ascii=False))
    elif ok:
        print(f"✅ {len(tasks)} 个 Task,导出 {len(mapping)} 条 REQ 映射" + (f" → {args.out}" if args.out else ""))
        if not args.out:
            print(json.dumps(mapping, ensure_ascii=False, indent=2))
    else:
        print(f"❌ {len(issues)} 个问题,未导出映射:")
        for it in issues[:30]:
            print(f"  [{it['type']}] {it['file']}:{it['line']}  {it['msg']}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
