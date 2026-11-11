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

退出码：0 = 已预确认；1 = 缺失（两源按维度合并后仍缺 backend/database）；2 = 用法错或脚本自身故障
（未预期异常，⛔ 不得当作「缺失」冻结，应告警后人工排查）。
`--summary` 只打印可直接并入 `/sprint-design` 上下文的 `tech_boundary_preconfirmed` 清单（仅 0 时有输出）。
`db_dialect`（达梦 → `dameng`、mysql → `mysql`，未识别 → `unknown`）仅用于入参与 D-NNN 占位；
SKILL 脚本 `--db` / `--sql-db` 的取值**一律经** `aidp_config.py sql-db-flag`（只有 dameng 会传）。
`--write-dialect`：已预确认且 db_dialect=dameng、而 `project.sql_dialect` 为空时回写 `dameng`
（幂等：已有值不覆盖；经 `aidp_config.py` 的 `set_scalar`，保证后续 CVL / SQL 扫描能拿到方言）。

## 信源合并（逐维度，PRD 优先）

PRD 单源已满足 backend+database → 只用 PRD；否则把 `技术选型.md` 已填行**按维度**补进缺的维度
（PRD 同名维度永远优先），合并后仍缺才报 missing。`技术选型.md` 按**表头列名**取值
（`技术选型` / `技术` 列，兼容 7 列总览表与 `/sprint-init` 的 `层级|技术|版本|…` 表），
文档编码异常按 `errors="replace"` 读取，不会让合法 PRD 声明被判缺失。
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
# 技术栈总览表「分类 / 层级」列 → 维度键（其余分类不参与判定）。
# `开发语言` 只作 backend 的**兜底**（且「项目」列含前端字样的行不算），不得抢在 `后端框架` 之前。
CATEGORY_KEYS = {"数据库": "database", "主数据库": "database", "后端框架": "backend",
                 "前端框架": "frontend", "中间件": "middleware", "ui 组件库": "ui", "构建工具": "build"}
LANG_CATEGORY = "开发语言"
_CHOICE_HEADERS = ("技术选型", "技术")
_CATEGORY_HEADERS = ("分类", "层级")
_PROJECT_HEADERS = ("项目",)
ARCH_DOC = os.path.join("docs", "architecture", "技术选型.md")


def _filled(value):
    return str(value).strip().lower() not in PLACEHOLDERS


def dialect_of(database):
    """数据库声明 -> 方言键（仅用于入参 / D-NNN 占位）；none 返回 none，判不出返回 unknown。

    ⛔ 传给 SKILL 脚本 `--db` / `--sql-db` 的值不取自这里，走 `aidp_config.py sql-db-flag`。
    """
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
    return "unknown" if v else ""


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


def _col(headers, names):
    """表头里第一个等于 `names` 之一的列下标；找不到 -1。"""
    for name in names:
        for i, h in enumerate(headers):
            if h.strip().lower() == name:
                return i
    return -1


def _from_arch_doc(root):
    """`技术选型.md` 表格 → 维度；按表头列名定位，不写死第 3 列。"""
    path = os.path.join(root, ARCH_DOC)
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return {}
    dims, lang = {}, ""
    cat_i = choice_i = proj_i = -1
    for line in text.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not cells or all(re.fullmatch(r":?-{2,}:?", c) or not c for c in cells):
            continue  # 分隔行
        probe_cat, probe_choice = _col(cells, _CATEGORY_HEADERS), _col(cells, _CHOICE_HEADERS)
        if probe_cat >= 0 and probe_choice >= 0:
            cat_i, choice_i, proj_i = probe_cat, probe_choice, _col(cells, _PROJECT_HEADERS)
            continue  # 表头行：记下列位置
        if cat_i < 0 or max(cat_i, choice_i) >= len(cells):
            continue  # 没见过表头的表（无法确定列语义）不猜
        cat, choice = cells[cat_i].lower(), cells[choice_i]
        if not _filled(choice):
            continue
        if cat == LANG_CATEGORY:
            proj = cells[proj_i].lower() if 0 <= proj_i < len(cells) else ""
            if not lang and not re.search(r"前端|frontend|ui", proj):
                lang = choice
            continue
        key = CATEGORY_KEYS.get(cat)
        if key and key not in dims:
            dims[key] = choice
    if lang and "backend" not in dims:
        dims["backend"] = lang
    return dims


def _missing(dims):
    return [k for k in REQUIRED if not _filled(dims.get(k, ""))]


def resolve_boundary(root, version, prd_root="docs/requirements"):
    """逐维度合并（PRD 优先）；惰性读取：PRD 已满足就不再碰 `技术选型.md`。"""
    arch_src = ARCH_DOC.replace(os.sep, "/")
    prd = _from_prd(root, version, prd_root)
    if prd and not _missing(prd):
        return {"status": "confirmed", "source": "prd:autopilot_decisions.tech_boundary", "dimensions": prd,
                "missing": [], "db_dialect": dialect_of(prd.get("database"))}
    arch = _from_arch_doc(root)
    merged = dict(arch)
    merged.update(prd)  # PRD 同名维度永远优先
    if merged and not _missing(merged):
        src = arch_src if not prd else "prd:autopilot_decisions.tech_boundary+" + arch_src
        return {"status": "confirmed", "source": src, "dimensions": merged, "missing": [],
                "db_dialect": dialect_of(merged.get("database"))}
    return {"status": "missing", "source": "", "dimensions": merged, "missing": _missing(merged),
            "db_dialect": ""}


def write_dialect(root, res):
    """回写 `project.sql_dialect=dameng`（仅已预确认 + 达梦 + 该键为空；幂等）。→ True=本次写入。"""
    if res.get("status") != "confirmed" or res.get("db_dialect") != "dameng":
        return False
    import aidp_config
    if aidp_config.sql_dialect(root):
        return False
    aidp_config.set_scalar(root, "project.sql_dialect", "dameng")
    return True


def summary_text(res):
    """SKILL 入参 `tech_boundary_preconfirmed` / `db_dialect` 的取值块（原样并入调用 prompt）。"""
    lines = [f"tech_boundary_preconfirmed（来源：{res['source']}；视为用户已 accept，直接进入 Phase 2，不再提问）："]
    lines += [f"- {k}: {v}" for k, v in res["dimensions"].items()]
    if res.get("db_dialect") and res["db_dialect"] != "unknown":
        lines.append(f"db_dialect: {res['db_dialect']}")
    lines.append("清单外的栈维度（ORM/连接池/序列化/实时通信等）不推断、不自编暂行值："
                 "按 SKILL 登记 99_待澄清问题清单.md 的 D-NNN（暂行方案列写 {待用户填写: <维度>}，状态 ⏳ 待确认）。")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="无人值守技术边界预确认判定（只读、不推断）")
    ap.add_argument("--version", required=True)
    ap.add_argument("--root", default=".")
    ap.add_argument("--prd-root", default="docs/requirements")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--summary", action="store_true", help="仅在已预确认时输出 tech_boundary_preconfirmed 清单文本")
    ap.add_argument("--write-dialect", action="store_true",
                    help="已预确认且为达梦、而 project.sql_dialect 为空时回写 dameng（幂等）")
    a = ap.parse_args(argv)
    try:
        root = os.path.abspath(a.root)
        res = resolve_boundary(root, a.version, a.prd_root)
        if a.write_dialect and write_dialect(root, res):
            print("📝 已回写 project.sql_dialect=dameng", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001 —— 未预期故障 ≠ 「缺失」：rc=2，调用方告警而非冻结 prd-missing
        print("❌ autopilot_tech_boundary.py 自身故障（%s: %s）——不等于技术边界缺失，请排查脚本/文档编码"
              % (type(exc).__name__, exc), file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    elif a.summary:
        if res["status"] == "confirmed":
            print(summary_text(res))
    elif res["status"] == "confirmed":
        print(f"✅ 技术边界已预确认（{res['source']}；db_dialect={res['db_dialect']}）")
    else:
        print(f"⛔ 技术边界无预确认来源，缺维度：{'/'.join(res['missing'])}（不推断；请在 PRD autopilot_decisions.tech_boundary "
              f"或 {ARCH_DOC.replace(os.sep, '/')} 补声明，后端/数据库无则显式写 none；已有维度 "
              f"{'/'.join(res['dimensions']) or '无'}）", file=sys.stderr)
    return 0 if res["status"] == "confirmed" else 1


if __name__ == "__main__":
    sys.exit(main())
