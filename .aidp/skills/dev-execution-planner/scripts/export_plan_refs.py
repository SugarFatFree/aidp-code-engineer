#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从研发执行计划导出「REQ → 首个承接 Task」映射(供编排层回填自测用例的 ⟨PLAN-REF:REQ-xxx⟩ 占位符)。

口径单一信源:references/output-format.md「Task 锚点与 REQ 承接映射」。

  python export_plan_refs.py <执行计划文件或目录> [--cases-dir <用例目录根>] [--out plan_refs.json] [--json]

读三样东西,全部来自计划本身、⛔ 不推断:
  · Task 标题上一行的锚点 `<a id="task-<phase>-<seq>"></a>`(编号必须与 `### Task <phase>.<seq>` 一致);
  · Task 标题下方紧邻的 `>` 元信息块里的 `**Sprint**: Sprint-NNN`(每个 Task 恰好一个;正文与代码围栏里的不算);
  · 9 列任务总表的「Task」与「REQ 关联」两列(表头口径与 check_task_granularity.py 同一份别名表;
    Task 格写成链接 `[Task 2.3](#task-2-3)` 也认)。
多文件模式请传**目录**:任务总表在主文档、Task 小节在 Phase 子文档,只传主文档会把每行报成 task_not_found。

一条 REQ 被多个 Task 承接时取 **Sprint 号最小**、其次 **Task 号最小**(按数值比,`2.9` < `2.10`)。
输出形如 {"REQ-104": {"label": "Sprint-001 Task 2.2", "href": "../plans/V1/01_研发执行计划.md#task-2-2"}};
`href` 是计划文件相对 `--cases-dir`(用例目录**根**,缺省当前目录)的词法路径(不跟随软链);
用例在子目录时由 resolve_plan_refs.py 按各文件位置重算,编排层不必拆分。

**全有或全无**:有任何 issue → `--out` 不写(已存在的旧映射文件会被删除,防止下游误用过期映射)、exit 1。
没被任何 Task 承接的 REQ 不进映射(⛔ 不替它挑一个 Task)。

issue 严重度(`--json` 的 `issues[].severity`,⚠️ 不占退出码):
  · Important —— **整份文件一个锚点都没有**的存量计划(本约定落地前生成)缺锚点 / 缺 Sprint:不判死存量;
  · Critical  —— 其余一切:部分 Task 有锚点而其它没有、锚点编号不符、多 Sprint、总表引用不存在的 Task、
    Task 格解析不出、缺任务总表、文件读不出。

退出码:0 = 已导出,或既无 Task 也无任务总表(`skipped: true`,⚠️ 不等于通过) / 1 = 有 issue /
2 = 入参错(路径不存在、`--cases-dir` 不是目录、全部文件读不出)。
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# 同 SKILL 内复用:需求编号判据 + 任务总表列名别名表(两道门对同一张表只有一份口径)
from check_task_granularity import COLUMN_ALIASES, REQ_ID_CORE  # noqa: E402

REQ_ID_RE = re.compile(REQ_ID_CORE)
TASK_HEAD_RE = re.compile(r"^#{3,4}\s+Task\s+(\d+)\.(\d+)\s*[:：]?")
ANCHOR_RE = re.compile(r'^<a\s+id="(task-\d+-\d+)"\s*>\s*</a>\s*$')
SPRINT_FIELD_RE = re.compile(r"\*\*Sprint\*\*\s*[:：]\s*([^|\n]+)")
SPRINT_ID_RE = re.compile(r"Sprint-(\d+)")
CELL_TASK_RE = re.compile(r"^Task\s*(\d+)\.(\d+)$", re.IGNORECASE)
TASK_MENTION_RE = re.compile(r"Task\s*\d+\.\d+", re.IGNORECASE)
MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
SEP_CELL_RE = re.compile(r"^:?-+:?$")


def split_row(line):
    cells = re.split(r"(?<!\\)\|", line.strip())
    if cells and cells[0].strip() == "":
        cells = cells[1:]
    if cells and cells[-1].strip() == "":
        cells = cells[:-1]
    return [c.strip() for c in cells]


def _norm(cell):
    return cell.strip().strip("*` ").lower().replace(" ", "")


def task_table_columns(cells):
    """是任务总表表头则返回 (Task 列, REQ 列) 下标,否则 None。别名取自 check_task_granularity。"""
    norm = [_norm(c) for c in cells]
    # 首格须是列名(不含数字):数据行首格 `Task 1.1` 同样含 task,不加这条会被当成新表头
    if len(norm) < 5 or re.search(r"\d", norm[0]) or not any(a in norm[0] for a in COLUMN_ALIASES["Task"]):
        return None
    if not any("描述" in c for c in norm):
        return None
    req = next((i for i, c in enumerate(norm) if any(a in c for a in COLUMN_ALIASES["REQ 关联"])), None)
    return None if req is None else (0, req)


def cell_task(cell):
    plain = MD_LINK_RE.sub(r"\1", cell).strip().strip("*` ")
    m = CELL_TASK_RE.match(plain)
    return (int(m.group(1)), int(m.group(2))) if m else None


def parse_file(path: Path, text: str, tasks, rows, issues):
    lines = text.splitlines()
    in_fence, prev_nonblank, header, headers = False, None, None, 0
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith("```") or s.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = TASK_HEAD_RE.match(ln)
        if m:
            p, q = int(m.group(1)), int(m.group(2))
            want = f"task-{p}-{q}"
            am = ANCHOR_RE.match(prev_nonblank or "")
            anchor = am.group(1) if am else None
            # Sprint 只认标题下方紧邻的 `>` 元信息块(中间可空行),正文 / 代码围栏里的示例不算
            sprints, j = [], i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            while j < len(lines) and lines[j].lstrip().startswith(">"):
                fm = SPRINT_FIELD_RE.search(lines[j])
                if fm:
                    sprints.extend(SPRINT_ID_RE.findall(fm.group(1)))
                j += 1
            key = (p, q)
            if key in tasks:
                issues.append({"type": "task_duplicate", "file": str(path), "line": i + 1,
                               "msg": f"Task {p}.{q} 重复出现(首次在 {tasks[key]['file']}:{tasks[key]['line']})"})
            else:
                tasks[key] = {"file": path, "line": i + 1, "anchor": anchor, "want": want,
                              "sprints": sprints}
            prev_nonblank = ln
            continue
        if s.startswith("|"):
            cells = split_row(s)
            cols = task_table_columns(cells)
            if cols:
                header = cols
                headers += 1
            elif header and cells and not SEP_CELL_RE.match(cells[0]) and len(cells) > max(header):
                cell = cells[header[0]]
                tk = cell_task(cell)
                if tk:
                    rows.append({"task": tk, "reqs": REQ_ID_RE.findall(cells[header[1]]),
                                 "file": str(path), "line": i + 1})
                elif TASK_MENTION_RE.search(cell):
                    issues.append({"type": "task_cell_unparsed", "file": str(path), "line": i + 1,
                                   "msg": f"任务总表 Task 格「{cell[:40]}」解析不出 `Task N.N`,该行承接的 REQ 会被漏掉"})
        elif s:
            header = None
        if s:
            prev_nonblank = ln
    return headers


def judge_tasks(tasks, issues):
    """逐 Task 判锚点与 Sprint;整份文件一个锚点都没有 = 存量计划,缺项降 Important。"""
    anchored_files = {t["file"] for t in tasks.values() if t["anchor"]}
    for (p, q), t in sorted(tasks.items()):
        legacy = t["file"] not in anchored_files
        sev = "Important" if legacy else "Critical"
        loc = {"file": str(t["file"]), "line": t["line"]}
        if t["anchor"] is None:
            issues.append({**loc, "type": "task_anchor_missing", "severity": sev,
                           "msg": f'Task {p}.{q} 标题上一行缺锚点 <a id="{t["want"]}"></a>'
                                  + ("(整份文件无锚点,按存量计划降级)" if legacy else "")})
        elif t["anchor"] != t["want"]:
            issues.append({**loc, "type": "task_anchor_mismatch", "severity": "Critical",
                           "msg": f"Task {p}.{q} 的锚点是 {t['anchor']},应为 {t['want']}"})
            t["anchor"] = None
        ids = sorted(set(int(x) for x in t["sprints"]))
        t["sprint"] = None
        if not ids:
            issues.append({**loc, "type": "task_sprint_missing", "severity": sev,
                           "msg": f"Task {p}.{q} 标题下方元信息块缺 **Sprint**: Sprint-NNN 字段"})
        elif len(ids) > 1:
            issues.append({**loc, "type": "task_sprint_ambiguous", "severity": "Critical",
                           "msg": f"Task {p}.{q} 写了多个 Sprint({', '.join('Sprint-' + x for x in t['sprints'])}),每个 Task 只能归属一个"})
        else:
            t["sprint"] = "Sprint-" + t["sprints"][0]


def main() -> int:
    ap = argparse.ArgumentParser(description="导出 REQ → 首个承接 Task 映射(⟨PLAN-REF⟩ 回填用)")
    ap.add_argument("target", help="研发执行计划文件或目录(多文件模式传目录)")
    ap.add_argument("--cases-dir", default=".", help="自测用例目录根(href 相对它计算,缺省当前目录)")
    ap.add_argument("--out", help="映射 JSON 写到此文件(有任何 issue 时不写,并删除已存在的旧文件)")
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

    tasks, rows, issues, read_errors, headers = {}, [], [], [], 0
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            read_errors.append({"file": str(f), "error": str(exc)})
            continue
        headers += parse_file(f, text, tasks, rows, issues)
    if files and len(read_errors) == len(files):
        print(f"全部 {len(files)} 个文件读不出: {read_errors[0]['error']}", file=sys.stderr)
        return 2
    for e in read_errors:
        issues.append({"type": "read_error", "file": e["file"], "line": 0,
                       "msg": f"文件读不出({e['error']}),其中的 Task 与任务总表行未纳入"})

    if not tasks and not rows and not issues:
        out = {"skipped": True, "reason": "既无 `### Task X.Y` 标题也无任务总表", "files_scanned": len(files),
               "mapping": {}, "issues": []}
        print(json.dumps(out, ensure_ascii=False) if args.json else "⚠️ 未识别到任何 Task,跳过(不等于通过)")
        return 0
    judge_tasks(tasks, issues)
    if not headers:
        issues.append({"type": "req_table_missing", "file": str(target), "line": 0,
                       "msg": "缺 9 列任务总表(表头首列 Task、含「描述」与「REQ 关联」列),无法确定 REQ 承接关系"})

    candidates = {}
    for r in rows:
        if r["task"] not in tasks:
            issues.append({"type": "task_not_found", "file": r["file"], "line": r["line"],
                           "msg": "任务总表引用了 Task {}.{},但计划里没有这个 Task 小节".format(*r["task"])
                                  + ("(多文件模式请传目录)" if target.is_file() else "")})
            continue
        for req in r["reqs"]:
            candidates.setdefault(req, set()).add(r["task"])
    for it in issues:
        it.setdefault("severity", "Critical")

    mapping = {}
    if not issues:
        for req in sorted(candidates):
            best = min(candidates[req], key=lambda k: (int(tasks[k]["sprint"][7:]), k))
            t = tasks[best]
            rel = os.path.relpath(os.path.abspath(t["file"]), os.path.abspath(cases_dir)).replace(os.sep, "/")
            mapping[req] = {"label": "{} Task {}.{}".format(t["sprint"], *best), "href": f"{rel}#{t['anchor']}"}

    ok = not issues
    if args.out:
        out_path = Path(args.out)
        if ok:
            out_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        elif out_path.is_file():
            out_path.unlink()
    if args.json:
        print(json.dumps({"skipped": False, "files_scanned": len(files), "tasks": len(tasks),
                          "reqs": len(candidates), "mapping": mapping, "issues": issues,
                          "read_errors": read_errors}, ensure_ascii=False))
    elif ok:
        print(f"✅ {len(tasks)} 个 Task,导出 {len(mapping)} 条 REQ 映射" + (f" → {args.out}" if args.out else ""))
        if not args.out:
            print(json.dumps(mapping, ensure_ascii=False, indent=2))
    else:
        print(f"❌ {len(issues)} 个问题,未导出映射:")
        for it in issues[:30]:
            print(f"  [{it['severity']}][{it['type']}] {it['file']}:{it['line']}  {it['msg']}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
