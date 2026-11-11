#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""autopilot_tech_boundary.py — 无人值守「技术边界预确认」的唯一可执行判定。

## 为什么需要本脚本

`dev-logic-architect` Phase 1「技术边界确认」是强交互闸门（逐维度向用户确认、数据库必确认、
严禁从框架/原型推断、确认汇总须用户 accept 后才能生成设计）。无人值守（`/loop` / 调度）下子 Agent
没有 `AskUserQuestion`，该门在无供给时只有两种结局：向无人可答的终端提问后结束本轮（既不失败也不推进，
要到 stuck 熔断才被冻结），或违反铁律自行补全技术栈。

本脚本给该门一个**机械的供给判定**——只读取用户已经落盘的声明，**绝不推断**：

  1. PRD 头部 `autopilot_decisions.tech_boundary`（经 `autopilot_decisions_merge.py` 双信源合并，PRD 优先）；
  2. 否则 `docs/architecture/技术选型.md`「技术栈总览」表中已填写（非 `-`/待定）的行。

最低要求的维度（缺任一即 `missing`）：`backend`（后端；纯前端项目显式写 `none`）与 `database`
（数据库；无库项目显式写 `none`）。显式 `none` 是用户的声明，不等于缺失。

## 用法

    autopilot_tech_boundary.py --version V0.2.0 [--root .] [--prd-root docs/requirements] [--json|--summary]

退出码：0 = 已预确认；1 = 缺失（两源都不足以构成确认汇总）；2 = 用法错。
`--summary` 只打印可直接并入 `/sprint-design` 上下文的「确认汇总」文本（仅 0 时有输出）。
`db_dialect`（达梦 → `dameng` 等）供 `--db` / `--sql-db` 取值，来源同上，不另猜。
"""
import argparse
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

REQUIRED = ("backend", "database")
PLACEHOLDERS = {"", "-", "—", "待定", "待确认", "<待确认>", "tbd", "todo", "n/a"}
EXPLICIT_NONE = {"none", "无", "不适用"}
# 技术栈总览表「分类」列 → 维度键（其余分类原样收进 extra，不参与判定）
CATEGORY_KEYS = {"数据库": "database", "后端框架": "backend", "开发语言": "backend",
                 "前端框架": "frontend", "中间件": "middleware", "ui 组件库": "ui", "构建工具": "build"}
ARCH_DOC = os.path.join("docs", "architecture", "技术选型.md")


def _filled(value):
    return str(value).strip().lower() not in PLACEHOLDERS


def dialect_of(database):
    """数据库声明 -> 方言键（供 --db / --sql-db）；判不出返回小写原文，none 返回 none。"""
    v = str(database or "").strip().lower()
    if v in EXPLICIT_NONE:
        return "none"
    if re.search(r"达梦|dameng|\bdm\d*\b", v):
        return "dameng"
    for key, pat in (("mysql", r"mysql|mariadb"), ("postgresql", r"postgres|\bpg\b"),
                     ("oracle", r"oracle"), ("sqlserver", r"sql\s*server|mssql"),
                     ("sqlite", r"sqlite")):
        if re.search(pat, v):
            return key
    return v


def _from_prd(root, version, prd_root):
    try:
        from autopilot_decisions_merge import resolve, resolve_fallback
        res = resolve(version, os.path.join(root, prd_root), resolve_fallback(None, root))
    except Exception:  # noqa: BLE001 —— 读不到按无声明，不阻断判定
        return {}
    tb = (res.get("merged") or {}).get("tech_boundary")
    if not isinstance(tb, dict):
        return {}
    return {str(k): str(v).strip() for k, v in tb.items() if not isinstance(v, (dict, list)) and _filled(v)}


def _from_arch_doc(root):
    path = os.path.join(root, ARCH_DOC)
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        return {}
    dims = {}
    for line in text.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        key = CATEGORY_KEYS.get(cells[0].lower())
        choice = cells[2]
        if key and _filled(choice) and key not in dims:
            dims[key] = choice
    return dims


def resolve_boundary(root, version, prd_root="docs/requirements"):
    for source, dims in (("prd:autopilot_decisions.tech_boundary", _from_prd(root, version, prd_root)),
                         (ARCH_DOC.replace(os.sep, "/"), _from_arch_doc(root))):
        missing = [k for k in REQUIRED if not _filled(dims.get(k, ""))]
        if dims and not missing:
            return {"status": "confirmed", "source": source, "dimensions": dims, "missing": [],
                    "db_dialect": dialect_of(dims.get("database"))}
    # 两源都不足：报告「最接近」的来源缺什么，便于补声明
    prd = _from_prd(root, version, prd_root)
    arch = _from_arch_doc(root)
    best = prd if len(prd) >= len(arch) else arch
    return {"status": "missing", "source": "", "dimensions": best,
            "missing": [k for k in REQUIRED if not _filled(best.get(k, ""))], "db_dialect": ""}


def summary_text(res):
    lines = [f"技术边界已由用户预确认（来源：{res['source']}）；以下即『确认汇总』，视为已 accept，直接进入 Phase 2，不再提问："]
    lines += [f"- {k}: {v}" for k, v in res["dimensions"].items()]
    lines.append("未在上表列出的栈维度（ORM/连接池/序列化/实时通信等）不得推断或静默补全："
                 "按「不臆造兜底原则」登记进 99_待澄清问题清单.md，设计中以 <待确认> 标注。")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="无人值守技术边界预确认判定（只读、不推断）")
    ap.add_argument("--version", required=True)
    ap.add_argument("--root", default=".")
    ap.add_argument("--prd-root", default="docs/requirements")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--summary", action="store_true", help="仅在已预确认时输出确认汇总文本")
    a = ap.parse_args(argv)
    res = resolve_boundary(os.path.abspath(a.root), a.version, a.prd_root)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    elif a.summary:
        if res["status"] == "confirmed":
            print(summary_text(res))
    elif res["status"] == "confirmed":
        print(f"✅ 技术边界已预确认（{res['source']}；db_dialect={res['db_dialect']}）")
    else:
        print(f"⛔ 技术边界无预确认来源，缺维度：{'/'.join(res['missing'])}（不推断；请在 PRD autopilot_decisions.tech_boundary "
              f"或 {ARCH_DOC.replace(os.sep, '/')} 补声明，后端/数据库无则显式写 none）", file=sys.stderr)
    return 0 if res["status"] == "confirmed" else 1


if __name__ == "__main__":
    sys.exit(main())
