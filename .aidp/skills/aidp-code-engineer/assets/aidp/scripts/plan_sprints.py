#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""研发执行计划 → Sprint 集合的**唯一口径**（全部计划文件，不是第一份）。

## 它堵的是哪一类失效

「本版一共有哪些 Sprint」这个判断此前在 autopilot 链里有三种写法，分散在四个分片：

  · `find … -name '*研发执行计划*.md' -print -quit`   ← 只取**一份**，且 find 不排序
  · `docs/plans/$V/01_研发执行计划.md`（硬编码）      ← 拆分形态下该文件不存在
  · `ls "$PLAN_DIR/"*研发执行计划*.md`（全量 glob）   ← 唯一正确的那个

而多文件是上游 SKILL **明确支持并会产生**的形态：多用户拆 `NN_研发执行计划-{姓名}.md`、
内容量超阈拆 `02_`…、跨 ≥3 里程碑拆 `01_M1研发执行计划.md` / `02_M2研发执行计划.md`。

`-print -quit` 命中 M1 那份时，「全部 Sprint」就等于 M1 的 Sprint。M1 跑完 → 差集为空 →
打印「✅ 全部 Sprint 已关闭」→ 正常部署、finalize、发报告、发卡，**M2 的 Sprint 从未执行
且没有任何告警**。这是无人值守下最坏的一类失效：不报错、不重试、结论是"成功"。

硬编码 `01_研发执行计划.md` 的那两处则是另一面：拆分形态下文件不存在 → 变量取空 →
下游拿空游标做判定（`grep -qx ""` 在空数组上恒命中，反而判成功）。

## 判据

  · 计划文件 = `docs/plans/{version}/` **一层内**所有 `*研发执行计划*.md`（按文件名排序，全取）
  · Sprint 全集 = 上述文件里所有 `Sprint-NNN` 的 NNN，去重排序
  · 已关闭 = `memory/{version}/*/sprints/sprint-*.md` 里的 NNN（兼容 `sprint-abc001.md` 形态）
  · 剩余 = 全集 − 已关闭，保持全集顺序

## 退出码（与全仓下发脚本同一套）

  0 = 解析成功
  1 = fail-closed：无计划文件，或有文件但一个 Sprint 都没解析出来
      （⛔ 刻意不返回"空集 + exit 0"——空集会被上游读成「全部已关闭」，
        正是本脚本要堵的那个假成功）
  2 = 用法错

## 用法

    # ⛔ 别写成 `eval "$(...)"` 一行：fail-closed 时本脚本 **exit 1 且 stdout 零字节**
    #    （诊断走 stderr），`eval` 会把退出码吞掉 ⇒ 变量全 unset ⇒ 上游读成"没有待跑 Sprint"。
    _PS=$(python3 .aidp/scripts/plan_sprints.py --version V0.1.0 --shell) || exit 1
    eval "$_PS"; : "${REMAIN_COUNT:?plan_sprints fail-closed}"
    python3 .aidp/scripts/plan_sprints.py --version V0.1.0 --json

`--shell` 导出：`PLAN_FILE_COUNT` `PLAN_FILES` `ALL_SPRINTS` `CLOSED_SPRINTS`
`REMAIN_SPRINTS` `REMAIN_COUNT` `FIRST_SPRINT` `NEXT_SPRINT` `CURRENT_SPRINT`
（空格分隔的字符串；数组用 `read -ra` 还原，避免各分片再各写一套 mapfile）。
"""
import argparse
import glob
import json
import os
import re
import shlex
import sys

_SPRINT_RE = re.compile(r"Sprint-(\d{3})")
_CLOSED_RE = re.compile(r"sprint-(?:[a-z]+)?(\d{3})\.md$")


def scan(root: str, version: str):
    plan_dir = os.path.join(root, "docs", "plans", version)
    # ★ 全取、排序——不是 -print -quit 的第一份（见文件头「它堵的是哪一类失效」）
    plan_files = sorted(glob.glob(os.path.join(plan_dir, "*研发执行计划*.md")))

    all_sp: list = []
    for f in plan_files:
        try:
            text = open(f, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        for m in _SPRINT_RE.finditer(text):
            if m.group(1) not in all_sp:
                all_sp.append(m.group(1))
    all_sp.sort()

    closed: list = []
    mem_dir = os.path.join(root, "memory", version)
    for f in glob.glob(os.path.join(mem_dir, "*", "sprints", "sprint-*.md")):
        m = _CLOSED_RE.search(os.path.basename(f))
        if m and m.group(1) not in closed:
            closed.append(m.group(1))
    closed.sort()

    remain = [s for s in all_sp if s not in closed]
    return {
        "plan_files": [os.path.relpath(f, root) for f in plan_files],
        "plan_file_count": len(plan_files),
        "all_sprints": all_sp,
        "closed_sprints": closed,
        "remain_sprints": remain,
        "remain_count": len(remain),
        "first_sprint": all_sp[0] if all_sp else "",
        "next_sprint": remain[0] if remain else "",
        "current_sprint": closed[-1] if closed else "",
    }


def main():
    ap = argparse.ArgumentParser(
        description="研发执行计划 → Sprint 集合（全部计划文件的唯一口径）")
    ap.add_argument("--root", default=".")
    ap.add_argument("--version", required=True)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--shell", action="store_true", help="输出可 eval 的 shell 赋值")
    g.add_argument("--json", action="store_true")
    args = ap.parse_args()

    res = scan(args.root, args.version)

    if not res["plan_files"]:
        sys.stderr.write(
            f"⛔ docs/plans/{args.version}/ 下无 *研发执行计划*.md → fail-closed\n"
            f"   （⛔ 不返回空集：空集会被上游读成「全部 Sprint 已关闭」而误判完成）\n")
        if args.json:
            print(json.dumps(res, ensure_ascii=False))
        return 1
    if not res["all_sprints"]:
        sys.stderr.write(
            f"⛔ {res['plan_file_count']} 份研发执行计划里一个 Sprint-NNN 都没解析出来 → fail-closed\n")
        if args.json:
            print(json.dumps(res, ensure_ascii=False))
        return 1

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    if args.shell:
        out = [
            f"PLAN_FILE_COUNT={res['plan_file_count']}",
            "PLAN_FILES=" + shlex.quote(" ".join(res["plan_files"])),
            "ALL_SPRINTS=" + shlex.quote(" ".join(res["all_sprints"])),
            "CLOSED_SPRINTS=" + shlex.quote(" ".join(res["closed_sprints"])),
            "REMAIN_SPRINTS=" + shlex.quote(" ".join(res["remain_sprints"])),
            f"REMAIN_COUNT={res['remain_count']}",
            "FIRST_SPRINT=" + shlex.quote(res["first_sprint"]),
            "NEXT_SPRINT=" + shlex.quote(res["next_sprint"]),
            "CURRENT_SPRINT=" + shlex.quote(res["current_sprint"]),
        ]
        print("\n".join(out))
        return 0

    print(f"[OK] 计划 {res['plan_file_count']} 份 / Sprint 全集 {len(res['all_sprints'])} 个"
          f"（{' '.join(res['all_sprints'])}）/ 已关闭 {len(res['closed_sprints'])} 个"
          f" / 剩余 {res['remain_count']} 个（下一个 {res['next_sprint'] or '-'}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
