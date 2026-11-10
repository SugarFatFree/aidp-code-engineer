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
**可以按用途确定性区分**的（交付：计划集合 ∖ 已关闭集合；开工：已启动集合 ∖ 已关闭集合），散文化的后果是执行体各自按理解判：
看 `activeContext.md` 的、看 baseline 的、看最近一次 commit 的，谁都说自己查过了。
更糟的是它**漏判的方向是放行** —— 判不出来就继续往下走，于是 Sprint 号被消耗、
六类 `NN_*.md` 增量落盘，上一轮产物成为无 Sprint 归属的孤儿（`/sprint-dev` Phase 0B.00
的注释已经把这个后果写出来了，但只写了后果、没给判据）。

## 判据（⛔ 与 `autopilot-ceremony-gate.py::_open_sprints` 同源，本脚本是其提取）

  · **计划集合** = `docs/plans/{V}/` 下所有 `*研发执行计划*.md` 里出现的 `Sprint-NNN`
  · **已关闭集合** = progress 同行 `Sprint-NNN` + ✅ 验收记录 ∩ 非空归档文件
  · `--scope all`（缺省，交付门）未关闭 = 计划集合 ∖ 已关闭集合
  · `--scope started`（开工门）未关闭 = 已启动集合 ∖（已关闭集合 ∩ 已归档集合）；尚未开工的计划不阻断首次启动
  · 已启动集合 = 跨用户启动记录 `memory/{V}/*/sprints/sprint-NNN.started.json`
    + 存量 progress 的进行中/待验收等显式状态 + activeContext 的「当前 Sprint」字段
  · `/sprint-start` 状态置位后用 `--record-start NNN --user <用户>` 登记启动记录；关闭必须同时有 progress 验收与归档

两点刻意如此，⛔ 别"优化"回去：

1. **跨用户扫描**（`memory/{V}/*/`，不是只看本机 `git config user.name`）——
   baseline 已扁平化为项目级，Sprint 记录可能落在任一协作者目录下；
   只看本机身份会把**别人关闭的** Sprint 误判成未关闭，这道门于是恒红、下游第一件事就是关掉它。
2. **取不到计划文件 → 返回空列表**（如 `--no-planning` 的合法路径），⛔ 不制造假 FAIL。
   ⚠️ 这一条是「适用范围」不是「放宽」：没有研发执行计划 = 这个版本还没规划到 Sprint 粒度，
   此时报「有未关闭 Sprint」只会指错方向。

## 用法

    python3 AIDP_HOME/scripts/check_open_sprints.py --version V0.2.0 [--root .] [--json]
    python3 AIDP_HOME/scripts/check_open_sprints.py --version V0.2.0 --scope started --json
    python3 AIDP_HOME/scripts/check_open_sprints.py --version V0.2.0 --record-start 001 --user alice
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sprint_inventory import inventory, closure_evidence


def planned_sprints(root: Path, version: str) -> set:
    return inventory(root, version)[version]["planned"]


def closed_sprints(root: Path, version: str) -> set:
    """验收同行 ✅ 与跨用户归档同时具备才关闭。"""
    return inventory(root, version)[version]["closed"]


def record_start(root: Path, version: str, user: str, sprint: str) -> Path:
    """每个用户/轮次独立落盘，不改写其他人的启动记录；归档后由 closed 集合扣除。"""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", version):
        raise ValueError("版本号格式非法")
    if not user or user in (".", "..") or any(c in user for c in "/\\\n\r"):
        raise ValueError("用户必须是单层目录名")
    if not re.fullmatch(r"\d{3}", sprint):
        raise ValueError("Sprint 编号须为三位数字")
    path = Path(root) / "memory" / version / user / "sprints" / f"sprint-{sprint}.started.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"sprint": f"Sprint-{sprint}", "user": user}, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def started_sprints(root: Path, version: str) -> set:
    return inventory(root, version)[version]["started"]


def scan(root: Path, version: str, scope: str = "all") -> dict:
    if scope not in ("all", "started"):
        raise ValueError("scope 必须为 all 或 started")
    item = inventory(root, version)[version]
    planned, started, closed = (item[key] for key in ("planned", "started", "closed"))
    selected = started if scope == "started" else planned
    open_ids = sorted(selected - closed)
    result = {"ok": not open_ids, "version": version, "scope": scope,
              "started": sorted(f"Sprint-{n}" for n in started),
              "planned": sorted(f"Sprint-{n}" for n in planned),
              "closed": sorted(f"Sprint-{n}" for n in closed),
              "open": [f"Sprint-{n}" for n in open_ids],
              "evidence": closure_evidence(item, selected),
              "detail": ("无未关闭 Sprint" if not open_ids else
                         f"仍有 {len(open_ids)} 个未关闭 Sprint，须先 `/sprint-close` 收口")}
    if not planned and scope == "all":
        result.update(skipped="no-plan", detail=f"docs/plans/{version}/ 无研发执行计划或未登记 Sprint；交付范围不适用")
    return result


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
        (mem / "sprints").mkdir()
        (mem / "sprints/sprint-001.md").write_text("# Sprint-001 归档\n", encoding="utf-8")
        if scan(root, "V0.1.0")["open"] != ["Sprint-002"]:
            return False
        # ★ 跨用户：别人关的也算关 —— 只看本机身份会让这道门恒红
        other = root / "memory" / "V0.1.0" / "bob"
        other.mkdir(parents=True)
        other.joinpath("progress.md").write_text("- Sprint-002 已完成 ✅\n", encoding="utf-8")
        (other / "sprints").mkdir()
        (other / "sprints/sprint-002.md").write_text("# Sprint-002 归档\n", encoding="utf-8")
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
    ap.add_argument("--scope", choices=("all", "started"), default="all", help="all=全部计划（交付）；started=已启动轮次（开工）")
    ap.add_argument("--record-start", metavar="NNN", help="记录已启动的 Sprint，不执行门检查")
    ap.add_argument("--user", help="启动记录所属用户，与 --record-start 同传")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--self-check", action="store_true", help="阳性 + 阴性对照自检")
    args = ap.parse_args(argv)

    if args.self_check:
        ok = self_check()
        print(("[PASS] " if ok else "[FAIL] ") + "check_open_sprints 自检")
        return 0 if ok else 1
    if not args.version:
        ap.error("需要 --version（或 --self-check）")

    if args.record_start is not None:
        if not args.user:
            ap.error("--record-start 需要 --user")
        try:
            path = record_start(Path(args.root), args.version, args.user, args.record_start)
        except (OSError, ValueError) as exc:
            print(f"启动记录写入失败：{exc}", file=sys.stderr)
            return 2
        print(json.dumps({"ok": True, "path": str(path)}, ensure_ascii=False))
        return 0
    try:
        res = scan(Path(args.root), args.version, scope=args.scope)
    except (OSError, UnicodeError) as exc:
        print(f"启动状态读取失败：{exc}", file=sys.stderr)
        return 2
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
