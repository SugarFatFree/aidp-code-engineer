#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_sprint_numbering.py — Sprint 编号跨版本连续性 + Sprint 划分粒度（脚手架契约脚本）。

## 为什么需要本脚本（两个下游实测问题，同一个根因）

两条规则此前**都只隐含在示例里、从未成文，更没有机器回检**，于是下游各按各的理解落地：

**① Sprint 编号该不该跨版本连续？** 权威定义（`docs/init/06_版本与用户目录约定.md` §3.3）
只写了「三位数字，从 001 起」——没说是否随版本重置。而命令端算下一个编号时扫的是
`memory/{version}/{user}/sprints/` + `docs/plans/{version}/01_研发执行计划.md`，**两个都带
`{version}` 限定**：新版本目录天然是空的 → MAX=0 → 新版本又从 `sprint-001` 开始。
于是同一个项目里存在多个 `sprint-001`，Sprint 号不再是项目内的唯一标识——
bugfix 记录、测试目录 `docs/testing/{version}/sprint-{NNN}/`、归档记录里
的「Sprint」字段全部产生歧义，跨版本回溯时无法只凭编号定位。
**正确语义：编号是项目全局流水号，跨版本【连续自增、绝不回退重置】。**

**② 前后端该不该拆成两个 Sprint？** 任务分配矩阵的表头本就表达了正确语义——
`| 功能模块 | 后端任务 | 前端任务 | 负责人 | Sprint |`，**一行 = 一个功能模块 = 一个 Sprint，
前后端是同一行的两列**。但上游 `dev-execution-planner` 产出的是 EPIC / Phase / Task
（**SKILL 里根本没有 Sprint 概念**），Sprint 是命令端映射出来的，映射规则从未成文；
执行体便可能按 Phase（"后端 Phase" / "前端 Phase"）或按端去切，把一个功能的前后端
拆进两个 Sprint。后果：任一 Sprint 都无法独立验收（前端 Sprint 没有接口可联调、
后端 Sprint 没有页面可验证），`/sprint-test` 的验收循环与 `/sprint-close` 的归档
都失去意义，Sprint 退化成"任务批次"。
**正确语义：一个 Sprint = 一个可独立验收的功能单元，其前后端任务同属该 Sprint。**

## 两个子命令

    next   算下一个 Sprint 编号（跨全部版本扫描，供 /sprint-dev·/sprint-full·/sprint-plan 取号）
    check  回检上述两条规则

## 判据

**A 编号连续性**（`check`）：
  - A1 **跨版本重复**（Critical）：同一编号出现在 ≥2 个版本 → 编号被重置过。
  - A2 **版本内重复**（Critical）：同一版本内同号出现多次。
  - A3 **断号**（Info，不判失败）：全局编号不连续。跳号本身不影响唯一性
    （Sprint 可能被取消/合并），故只报不拦。

**B 划分粒度**（`check`，解析「任务分配矩阵」表格）：
  - B1 **同一功能模块跨 Sprint**（Critical）：同一「功能模块」出现在 ≥2 个 Sprint
    → 功能被切开了。这是最确定的信号，零歧义。
  - B2 **单端 Sprint**（Important）：某 Sprint 的全部行「后端任务」列皆空、或「前端任务」
    列皆空 → 疑似按端拆分。**豁免**：该 Sprint 任一行显式标注「单端 / 仅前端 / 仅后端 /
    纯前端 / 纯后端」（沿用上游 `check_task_granularity.py` 的同款标记词，语义一致，
    真有纯前端需求时不误伤）。

## 用法

    python3 AIDP_HOME/scripts/check_sprint_numbering.py next [--root .] [--json]
    python3 AIDP_HOME/scripts/check_sprint_numbering.py check [--root .] [--json]

退出码：`0`=通过 / `1`=检出问题 / `2`=用法或读取错误。
"""
import argparse
import json
import os
import re
import sys

# Sprint 归档快照：memory/{version}/{user}/sprints/sprint-{NNN}.md
SPRINT_FILE_RE = re.compile(r"^sprint-(?:[a-z]+)?(\d{3,})\.md$", re.I)
# 计划正文里的 Sprint-NNN / sprint-NNN / Sprint NNN
SPRINT_REF_RE = re.compile(r"\bsprint[-\s]?(\d{3,})\b", re.I)
# 版本目录名 V{x}.{y}.{z}
VERSION_DIR_RE = re.compile(r"^[Vv]\d+\.\d+(\.\d+)?$")
# 单端豁免标记（与上游 dev-execution-planner/scripts/check_task_granularity.py 同款词表）
SINGLE_END_MARK = re.compile(r"单端|仅前端|仅后端|纯前端|纯后端|前端独立|后端独立")
# 空单元格：-、—、无、/、N/A、空
EMPTY_CELL_RE = re.compile(r"^(|-+|—+|无|/|n/?a|暂无)$", re.I)

PLAN_GLOB_NAMES = ("01_研发执行计划.md", "00_研发执行计划.md")


def _read(path, limit=600_000):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(limit)
    except OSError:
        return None


def _version_dirs(root, base):
    """base 下的版本目录列表（V0.1.0 形态）。"""
    d = os.path.join(root, base)
    if not os.path.isdir(d):
        return []
    return sorted(x for x in os.listdir(d)
                  if VERSION_DIR_RE.match(x) and os.path.isdir(os.path.join(d, x)))


def collect_sprints(root):
    """跨【全部版本】收集 Sprint 编号 → {num: [来源描述, ...]} + {version: set(num)}。

    ★ 关键：扫描面必须是所有版本，不能带 {version} 限定——那正是"新版本又从 001 开始"的成因。
    两个来源：① memory/{V}/{user}/sprints/sprint-{NNN}.md 归档快照（既成事实）
             ② docs/plans/{V}/01_研发执行计划.md 的任务分配矩阵（已规划）
    """
    by_num, by_version = {}, {}

    for v in _version_dirs(root, "memory"):
        vdir = os.path.join(root, "memory", v)
        for user in sorted(os.listdir(vdir)):
            sdir = os.path.join(vdir, user, "sprints")
            if not os.path.isdir(sdir):
                continue
            for fn in sorted(os.listdir(sdir)):
                m = SPRINT_FILE_RE.match(fn)
                if not m:
                    continue
                n = int(m.group(1))
                by_num.setdefault(n, []).append(f"memory/{v}/{user}/sprints/{fn}")
                by_version.setdefault(v, set()).add(n)

    for v in _version_dirs(root, os.path.join("docs", "plans")):
        pdir = os.path.join(root, "docs", "plans", v)
        for fn in sorted(os.listdir(pdir)):
            if fn not in PLAN_GLOB_NAMES and not fn.endswith("研发执行计划.md"):
                continue
            text = _read(os.path.join(pdir, fn))
            if not text:
                continue
            for n in {int(x) for x in SPRINT_REF_RE.findall(text)}:
                src = f"docs/plans/{v}/{fn}"
                by_num.setdefault(n, [])
                if src not in by_num[n]:
                    by_num[n].append(src)
                by_version.setdefault(v, set()).add(n)

    return by_num, by_version


def next_number(root):
    by_num, _ = collect_sprints(root)
    mx = max(by_num) if by_num else 0
    return mx + 1, mx


def _split_row(line):
    """拆 markdown 表格行 → 单元格列表（去首尾管道）。"""
    cells = line.strip().strip("|").split("|")
    return [c.strip() for c in cells]


def parse_matrices(root):
    """解析各版本计划里的「任务分配矩阵」→ [{version, file, module, backend, frontend, sprint, raw}]。

    只认表头同时含「功能模块」与「Sprint」的表格；列位置按表头动态定位，
    不写死列序（下游可能增删列，写死列号会静默错位）。
    """
    rows = []
    for v in _version_dirs(root, os.path.join("docs", "plans")):
        pdir = os.path.join(root, "docs", "plans", v)
        if not os.path.isdir(pdir):
            continue
        for fn in sorted(os.listdir(pdir)):
            if not fn.endswith(".md"):
                continue
            text = _read(os.path.join(pdir, fn))
            if not text or "功能模块" not in text:
                continue
            idx = None
            for line in text.split("\n"):
                if not line.strip().startswith("|"):
                    idx = None
                    continue
                cells = _split_row(line)
                if idx is None:
                    if "功能模块" in "".join(cells) and any("sprint" in c.lower() for c in cells):
                        idx = {}
                        for i, c in enumerate(cells):
                            cl = c.lower()
                            if "功能模块" in c:
                                idx["module"] = i
                            elif "后端" in c:
                                idx["backend"] = i
                            elif "前端" in c:
                                idx["frontend"] = i
                            elif "sprint" in cl:
                                idx["sprint"] = i
                        if "module" not in idx or "sprint" not in idx:
                            idx = None
                    continue
                if set("".join(cells).replace("|", "")) <= set("-: "):
                    continue  # 分隔行 |---|---|
                if max(idx.values()) >= len(cells):
                    continue
                sp = SPRINT_REF_RE.search(cells[idx["sprint"]])
                mod = cells[idx["module"]]
                if not sp or not mod or EMPTY_CELL_RE.match(mod):
                    continue
                rows.append({
                    "version": v, "file": f"docs/plans/{v}/{fn}",
                    "module": mod, "sprint": int(sp.group(1)),
                    "backend": cells[idx["backend"]] if "backend" in idx else "",
                    "frontend": cells[idx["frontend"]] if "frontend" in idx else "",
                    "raw": line.strip(),
                })
    return rows


def check(root):
    by_num, by_version = collect_sprints(root)
    rows = parse_matrices(root)
    findings = []

    # ── A1 跨版本重复 = 编号被重置（本次下游问题的确定性指纹）──
    ver_of = {}
    for v, nums in by_version.items():
        for n in nums:
            ver_of.setdefault(n, set()).add(v)
    for n in sorted(x for x, vs in ver_of.items() if len(vs) > 1):
        findings.append({
            "level": "Critical", "rule": "A1-跨版本重复",
            "detail": f"sprint-{n:03d} 同时出现在版本 {'、'.join(sorted(ver_of[n]))}"
                      f"——编号在新版本被重置了；Sprint 编号是项目全局流水号，须跨版本连续自增",
            "where": "; ".join(by_num.get(n, [])),
        })

    # ── A2 版本内重复 ──
    for n, srcs in sorted(by_num.items()):
        files = [s for s in srcs if s.startswith("memory/")]
        if len(files) > 1:
            per_ver = {}
            for s in files:
                per_ver.setdefault(s.split("/")[1], []).append(s)
            for v, ss in per_ver.items():
                if len(ss) > 1:
                    findings.append({
                        "level": "Critical", "rule": "A2-版本内重复",
                        "detail": f"sprint-{n:03d} 在版本 {v} 内有 {len(ss)} 份归档",
                        "where": "; ".join(ss),
                    })

    # ── A3 断号（只报不拦：Sprint 可能被取消/合并）──
    if by_num:
        allnums = sorted(by_num)
        missing = [n for n in range(min(allnums), max(allnums) + 1) if n not in by_num]
        if missing:
            findings.append({
                "level": "Info", "rule": "A3-断号",
                "detail": f"编号不连续，缺 {', '.join('%03d' % n for n in missing[:20])}"
                          f"{' 等' if len(missing) > 20 else ''}（Sprint 取消/合并属正常，仅提示）",
                "where": "-",
            })

    # ── B1 同一功能模块跨 Sprint（功能被切开，零歧义）──
    mod_sprints = {}
    for r in rows:
        mod_sprints.setdefault(r["module"], {}).setdefault(r["sprint"], []).append(r)
    for mod, sps in sorted(mod_sprints.items()):
        if len(sps) > 1:
            findings.append({
                "level": "Critical", "rule": "B1-功能跨Sprint",
                "detail": f"功能模块「{mod}」被拆到 {len(sps)} 个 Sprint："
                          f"{'、'.join('sprint-%03d' % s for s in sorted(sps))}"
                          f"——同一功能须归属同一 Sprint，前后端是其下的不同 Task",
                "where": "; ".join(sorted({r["file"] for rs in sps.values() for r in rs})),
            })

    # ── B2 单端 Sprint（疑似按端拆分）──
    per_sprint = {}
    for r in rows:
        per_sprint.setdefault((r["version"], r["sprint"]), []).append(r)
    for (v, sp), rs in sorted(per_sprint.items()):
        if any(SINGLE_END_MARK.search(r["raw"]) for r in rs):
            continue  # 显式标注单端 → 豁免
        has_be = any(not EMPTY_CELL_RE.match(r["backend"]) for r in rs)
        has_fe = any(not EMPTY_CELL_RE.match(r["frontend"]) for r in rs)
        if has_be and has_fe:
            continue
        if not has_be and not has_fe:
            continue  # 两列都空 = 表格没填任务，不属本规则管辖
        side = "只有前端任务" if has_fe else "只有后端任务"
        findings.append({
            "level": "Important", "rule": "B2-单端Sprint",
            "detail": f"{v} sprint-{sp:03d} {side}（{len(rs)} 行全部如此）——疑似按端拆分 Sprint；"
                      f"确属单端需求请在该行标注「单端/仅前端/仅后端」豁免",
            "where": "; ".join(sorted({r["file"] for r in rs})),
        })

    blocking = [f for f in findings if f["level"] in ("Critical", "Important")]
    return {
        "applicable": bool(by_num or rows),
        "sprint_count": len(by_num),
        "max_sprint": max(by_num) if by_num else 0,
        "next_sprint": (max(by_num) + 1) if by_num else 1,
        "versions": {v: sorted(ns) for v, ns in sorted(by_version.items())},
        "matrix_rows": len(rows),
        "findings": findings,
        "passed": not blocking,
    }


def main():
    ap = argparse.ArgumentParser(
        description="Sprint 编号跨版本连续性 + Sprint 划分粒度检查")
    ap.add_argument("cmd", choices=["next", "check"])
    ap.add_argument("--root", default=".", help="仓库根目录（默认当前目录）")
    ap.add_argument("--json", action="store_true", help="输出机读 JSON")
    ap.add_argument("--self-check", action="store_true",
                    help="阳性对照自检：注入必然命中的探针，验证本检查确实生效"
                         "（骨架与探针登记表见 selfcheck.py）")
    args = ap.parse_args()
    if args.self_check:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from selfcheck import run_self_check
        sys.exit(run_self_check(os.path.basename(__file__),
                                json_out=getattr(args, "json", False)))

    try:
        if args.cmd == "next":
            nxt, mx = next_number(args.root)
            if args.json:
                print(json.dumps({"next_sprint": nxt, "max_sprint": mx,
                                  "formatted": "%03d" % nxt}, ensure_ascii=False))
            else:
                print("%03d" % nxt)
            return 0

        res = check(args.root)
    except Exception as e:
        if args.json:
            print(json.dumps({"error": str(e)}, ensure_ascii=False))
        else:
            print(f"[ERROR] 检查执行失败：{e}")
        return 2

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res["passed"] else 1

    if not res["applicable"]:
        print("[SKIP] 未发现任何 Sprint 归档或研发执行计划，跳过")
        return 0
    if res["passed"]:
        extra = [f for f in res["findings"] if f["level"] == "Info"]
        print(f"[OK] Sprint 编号与划分粒度合规："
              f"共 {res['sprint_count']} 个 Sprint（最大 {res['max_sprint']:03d}，"
              f"下一个 {res['next_sprint']:03d}），矩阵 {res['matrix_rows']} 行。")
        for f in extra:
            print(f"  · [Info] {f['rule']}：{f['detail']}")
        return 0

    print(f"[FAIL] Sprint 检查检出 {len([f for f in res['findings'] if f['level'] != 'Info'])} 项：")
    for f in res["findings"]:
        if f["level"] == "Info":
            continue
        print(f"  · [{f['level']}] {f['rule']}：{f['detail']}")
        print(f"      落点：{f['where']}")
    print("  规则：① Sprint 编号是项目全局流水号，跨版本连续自增、不随版本重置"
          "（取号一律 `check_sprint_numbering.py next`）"
          "；② 一个 Sprint = 一个可独立验收的功能单元，前后端是其下的不同 Task、不拆成两个 Sprint。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
