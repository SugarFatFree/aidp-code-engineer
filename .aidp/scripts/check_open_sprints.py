#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_open_sprints.py — 「研发执行计划里还有未关闭 Sprint」的确定性判定【单一信源】。

## 这道门拦什么

约定 9：**未归档不得开下一个 Sprint**（`设计目标.md` G-CLOSE-1「验收结论与归档产物同时存在；
未归档不得开下一个 Sprint」）。四个命令都声明了这道前置门：

    /sprint-start      步骤 1「若有未关闭的 Sprint → 停止执行」
    /sprint-dev        Phase 0B.00 约定 9 前置门
    /sprint-bugfix     Phase 0C.00 约定 9 前置门
    /sprint-full       Phase 0B.0 前自检

★ 但此前**只有散文**，没有任何一处给出可执行判据 —— 而「有没有未关闭 Sprint」是
**完全确定性**的（计划集合 ∖ 已关闭集合），散文化的后果是执行体各自按理解判：
看 `activeContext.md` 的、看 baseline 的、看最近一次 commit 的，谁都说自己查过了。
更糟的是它**漏判的方向是放行** —— 判不出来就继续往下走，于是 Sprint 号被消耗、
六类 `NN_*.md` 增量落盘，上一轮产物成为无 Sprint 归属的孤儿（`/sprint-dev` Phase 0B.00
的注释已经把这个后果写出来了，但只写了后果、没给判据）。

## 判据（⛔ 与 `autopilot-ceremony-gate.py::_open_sprints` 同源，本脚本是其提取）

  · **计划集合** = `docs/plans/{V}/` 下所有 `.md` 里出现的 `Sprint-NNN`
  · **已关闭集合** = `memory/{V}/*/progress.md` 里**同一行**同时出现 `Sprint-NNN` 与 ✅ 的条目
  · 未关闭 = 计划集合 ∖ 已关闭集合

两点刻意如此，⛔ 别"优化"回去：

1. **跨用户扫描**（`memory/{V}/*/`，不是只看本机 `git config user.name`）——
   baseline 已扁平化为项目级，Sprint 记录可能落在任一协作者目录下；
   只看本机身份会把**别人关闭的** Sprint 误判成未关闭，这道门于是恒红、下游第一件事就是关掉它。
2. **取不到计划文件 → 返回空列表**（如 `--no-planning` 的合法路径），⛔ 不制造假 FAIL。
   ⚠️ 这一条是「适用范围」不是「放宽」：没有研发执行计划 = 这个版本还没规划到 Sprint 粒度，
   此时报「有未关闭 Sprint」只会指错方向。

## 用法

    python3 AIDP_HOME/scripts/check_open_sprints.py --version V0.2.0 [--root .] [--json]
    python3 AIDP_HOME/scripts/check_open_sprints.py --self-check

退出码：`0`=无未关闭 Sprint（含「适用范围外」）/ `1`=有未关闭 Sprint（调用方须停下）/ `2`=用法错。
⚠️ 退出码 1 的语义是「**本命令不得继续**」，调用方应提示先跑 `/sprint-close`，
⛔ 不是「记一笔告警然后往下走」—— 那等于这道门不存在。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

SPRINT_RE = re.compile(r"Sprint-(\d{3})")


def planned_sprints(root: Path, version: str) -> set:
    """研发执行计划里登记的 Sprint 号。计划目录不存在 → 空集（适用范围外）。"""
    plans = Path(root) / "docs" / "plans" / version
    if not plans.is_dir():
        return set()
    found = set()
    for path in sorted(plans.iterdir()):
        if path.suffix != ".md" or not path.is_file():
            continue
        try:
            found |= set(SPRINT_RE.findall(path.read_text(encoding="utf-8", errors="ignore")))
        except OSError:
            continue
    return found


def closed_sprints(root: Path, version: str) -> set:
    """已关闭的 Sprint 号：`memory/{V}/*/progress.md` 里同一行同时有 Sprint-NNN 与 ✅。

    ⛔ 必须**同一行**：整份文件里"某处有 ✅、另一处提到 Sprint-003"不构成关闭证据 ——
    progress.md 里 ✅ 是高频符号（阶段完成、检查项通过都在用）。
    """
    closed = set()
    mem = Path(root) / "memory" / version
    if not mem.is_dir():
        return closed
    for user_dir in sorted(mem.iterdir()):
        progress = user_dir / "progress.md"
        if not progress.is_file():
            continue
        try:
            for line in progress.read_text(encoding="utf-8", errors="ignore").splitlines():
                if "✅" in line:
                    closed |= set(SPRINT_RE.findall(line))
        except OSError:
            continue
    return closed


def scan(root: Path, version: str) -> dict:
    root = Path(root)
    planned = planned_sprints(root, version)
    if not planned:
        return {"ok": True, "skipped": "no-plan", "version": version, "open": [],
                "detail": f"docs/plans/{version}/ 无研发执行计划或未登记任何 Sprint —— "
                          f"适用范围外（⛔ 不等于「已全部关闭」）"}
    closed = closed_sprints(root, version)
    open_ids = sorted(planned - closed)
    return {"ok": not open_ids, "version": version,
            "planned": sorted(f"Sprint-{n}" for n in planned),
            "closed": sorted(f"Sprint-{n}" for n in closed),
            "open": [f"Sprint-{n}" for n in open_ids],
            "detail": ("无未关闭 Sprint" if not open_ids else
                       f"仍有 {len(open_ids)} 个未关闭 Sprint，须先 `/sprint-close` 收口")}


def self_check() -> bool:
    """阳性 + 两类阴性对照（⛔ 证明这道门既不恒绿也不恒红）。"""
    import shutil
    import tempfile
    root = Path(tempfile.mkdtemp(prefix="aidp-open-sprint-"))
    try:
        plans = root / "docs" / "plans" / "V0.1.0"
        plans.mkdir(parents=True)
        (plans / "01_研发执行计划.md").write_text(
            "# 计划\n\n- Sprint-001 登录\n- Sprint-002 导出\n", encoding="utf-8")
        # 阳性：两个都没关 → 两个都报
        if scan(root, "V0.1.0")["open"] != ["Sprint-001", "Sprint-002"]:
            return False
        mem = root / "memory" / "V0.1.0" / "alice"
        mem.mkdir(parents=True)
        mem.joinpath("progress.md").write_text("- Sprint-001 已完成 ✅\n", encoding="utf-8")
        if scan(root, "V0.1.0")["open"] != ["Sprint-002"]:
            return False
        # ★ 跨用户：别人关的也算关 —— 只看本机身份会让这道门恒红
        other = root / "memory" / "V0.1.0" / "bob"
        other.mkdir(parents=True)
        other.joinpath("progress.md").write_text("- Sprint-002 已完成 ✅\n", encoding="utf-8")
        if scan(root, "V0.1.0")["open"]:
            return False
        # ⛔ 阴性：✅ 与 Sprint 号**不在同一行**不构成关闭证据
        mem.joinpath("progress.md").write_text(
            "- 阶段检查通过 ✅\n\n- Sprint-001 进行中\n", encoding="utf-8")
        other.joinpath("progress.md").write_text("- Sprint-002 已完成 ✅\n", encoding="utf-8")
        if scan(root, "V0.1.0")["open"] != ["Sprint-001"]:
            return False
        # 适用范围外：无计划目录 → ok 且标 skipped（⛔ 不是假 FAIL、也不等于已全关）
        res = scan(root, "V9.9.9")
        return bool(res["ok"] and res.get("skipped") == "no-plan")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".", help="仓库根，默认当前目录")
    ap.add_argument("--version", help="版本号，如 V0.2.0")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--self-check", action="store_true", help="阳性 + 阴性对照自检")
    args = ap.parse_args(argv)

    if args.self_check:
        ok = self_check()
        print(("[PASS] " if ok else "[FAIL] ") + "check_open_sprints 自检")
        return 0 if ok else 1
    if not args.version:
        ap.error("需要 --version（或 --self-check）")

    res = scan(Path(args.root), args.version)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    elif res.get("skipped"):
        print(f"ℹ️ {res['detail']}")
    elif res["ok"]:
        print(f"✅ {args.version}：{res['detail']}")
    else:
        print(f"⛔ {args.version}：{res['detail']}")
        print("   " + "、".join(res["open"]))
        print("   → 先跑 `/sprint-close` 收口，再重试本命令")
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
