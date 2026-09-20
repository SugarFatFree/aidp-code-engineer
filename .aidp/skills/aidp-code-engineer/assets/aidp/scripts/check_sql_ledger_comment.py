#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_sql_ledger_comment.py — 「本版新增列的注释覆盖率没实查」门（约定 37.5bis ②）。

⛔ **它堵的缺口（实际项目中的实测事故）**：那次的 SQL 脚本里**是写了**
`COMMENT ON COLUMN` 的，但手工执行时只跑了 `ALTER TABLE ADD` 那一段循环，注释语句
**整段被漏掉**——**而没有任何一步会发现**。事后实查 `ALL_COL_COMMENTS`：新增 10 列
**10/10 无注释**。

**脚本内容正确 ≠ 库里状态正确。** 只校"脚本里有没有写 COMMENT"会**恰好漏掉这次事故的形态**。
真正的判据是"库里到底有没有"，而那要连库——CI 里连不上生产/演示环境的库是常态，所以本门不连库，
改为校验**执行方有没有把实查结果落进台账**：

    本版 SQL 有 `ADD COLUMN`  ⟹  `SQL执行台账.md` 必须有「三之二」注释覆盖率节，
                                  且该节的开发库行必须已填（不是 `{待填}` / 空 / 待部署）。

这样把"漏跑注释语句"从**不可见**变成**可见**：要填那张表，就得真去查一次库。

★ 本门**不判注释内容好不好**（那是语义判断，归设计期的上游 SKILL），只判**有没有实查过**。

判据（确定性）：
  · 扫 `docs/deployment/{version}/sql/`（含 `增量/`）的 `.sql`，找 `ADD COLUMN` / `ADD (`；
  · 无新增列 → PASS（本版不涉及）；
  · 有新增列 → 台账须存在、须有「三之二」节、开发库行须已填实。

退出码：0 = 合规 / 本版无新增列；1 = 有新增列却没实查留痕；2 = 入参或环境错。
"""
import argparse
import json
import os
import re
import sys

# `ALTER TABLE x ADD COLUMN y` / 达梦·Oracle 的 `ALTER TABLE x ADD (y ...)` 两种方言都认。
# ⛔ 不能只认 `ADD COLUMN`：Oracle/达梦系常写 `ADD (COL TYPE)`，漏掉它 = 本门在最常见的
#    国产库方言上恒判"本版无新增列"，静默失效。
_ADD_COL = re.compile(r"\bADD\s+COLUMN\b|\bADD\s*\(", re.I)
_SECTION = "三之二"
# 占位符 / 未填标记：填了这些等于没填
_UNFILLED = ("{待填}", "{ 待填 }", "待部署", "{YYYY-MM-DD", "TBD", "待填")


def _sql_files(root, version):
    base = os.path.join(root, "docs", "deployment", version, "sql")
    out = []
    if not os.path.isdir(base):
        return out
    for dp, _dn, fns in os.walk(base):
        for fn in sorted(fns):
            if fn.endswith(".sql") and not fn.startswith("99_"):   # 99_ 是回滚脚本
                out.append(os.path.join(dp, fn))
    return out


def run(root, version):
    res = {"version": version, "add_column_files": [], "ledger": None,
           "has_section": False, "dev_row_filled": False,
           "status": "", "passed": False, "detail": ""}
    hits = []
    for f in _sql_files(root, version):
        try:
            txt = open(f, encoding="utf-8", errors="replace").read(400_000)
        except OSError:
            continue
        if _ADD_COL.search(txt):
            hits.append(os.path.relpath(f, root).replace(os.sep, "/"))
    res["add_column_files"] = hits
    if not hits:
        res["status"] = "no-add-column"
        res["passed"] = True
        res["detail"] = "本版 SQL 无 ADD COLUMN，本门不适用"
        return res

    led = os.path.join(root, "docs", "deployment", version, "SQL执行台账.md")
    res["ledger"] = os.path.relpath(led, root).replace(os.sep, "/")
    if not os.path.isfile(led):
        res["status"] = "ledger-missing"
        res["detail"] = ("本版有 %d 份 SQL 含 ADD COLUMN，却没有 SQL执行台账.md"
                         "（模板 .aidp/templates/deployment/SQL执行台账.md）" % len(hits))
        return res
    try:
        body = open(led, encoding="utf-8", errors="replace").read(400_000)
    except OSError as exc:
        res["status"] = "ledger-unreadable"
        res["detail"] = str(exc)
        return res

    if _SECTION not in body:
        res["status"] = "section-missing"
        res["detail"] = ("台账缺「三之二、本版新增列注释覆盖率」节 —— "
                         "本版有新增列就必须实查库（ALL_COL_COMMENTS / information_schema.COLUMNS）"
                         "并把结果填进去。⛔ 校脚本里有没有写 COMMENT 是不够的："
                         "下游事故里脚本写了、执行漏了，实查 10/10 无注释")
        return res
    res["has_section"] = True

    # 取「三之二」节到下一个 `## ` 之间；找开发库那一行是否填实
    seg = body.split(_SECTION, 1)[1]
    seg = re.split(r"^##\s", seg, maxsplit=1, flags=re.M)[0]
    dev_rows = [ln for ln in seg.splitlines()
                if ln.lstrip().startswith("|") and "开发库" in ln]
    if not dev_rows:
        res["status"] = "dev-row-missing"
        res["detail"] = "「三之二」节里找不到开发库这一行"
        return res
    row = dev_rows[0]
    # 模板示例行（`{如 ...}` / `{2/2}`）与占位符都算未填
    unfilled = any(u in row for u in _UNFILLED) or "{如" in row or re.search(r"\{\d+/\d+\}", row)
    res["dev_row_filled"] = not unfilled
    if unfilled:
        res["status"] = "dev-row-unfilled"
        res["detail"] = ("「三之二」开发库行仍是模板占位 —— 说明没真去查过库。"
                         "该行须填：本版新增列逐列列出 / 有注释数 / 总数 / 缺注释列名 / 核对时间")
        return res
    res["status"] = "ok"
    res["passed"] = True
    res["detail"] = "本版 %d 份 SQL 含新增列，台账「三之二」已填实查结果" % len(hits)
    return res


def main():
    ap = argparse.ArgumentParser(description="本版新增列注释覆盖率是否已实查留痕（约定 37.5bis）")
    ap.add_argument("--root", default=".")
    ap.add_argument("--version")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-check", action="store_true",
                    help="阳性对照自检：注入必然命中的探针，验证本检查确实生效")
    args = ap.parse_args()
    if args.self_check:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from selfcheck import run_self_check
        return run_self_check(os.path.basename(__file__), json_out=args.json)

    root = os.path.abspath(args.root)
    if not os.path.isdir(root) or not args.version:
        print("[ERROR] 需要有效 --root 与 --version", file=sys.stderr)
        return 2
    res = run(root, args.version)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        tag = "OK   " if res["passed"] else "ERROR"
        print("[%s] %s：%s" % (tag, args.version, res["detail"]))
        if not res["passed"] and res["add_column_files"]:
            print("       含新增列的脚本：%s" % "、".join(res["add_column_files"][:5]))
    return 0 if res["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
