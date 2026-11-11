#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bugfix_scope.py — 按「列」解析 docs/bugfix/{version}/bugfix-*.md 的 Bug 台账表（确定性）。

背景：`/version` 发布前的「未闭环 P0」判定曾是整行 grep（`P0|严重|阻塞` 再剔除闭环词）。
标准台账的表头列名就含「严重」、字段说明行含「P0 阻塞」，所以**全部闭环时仍恒误判**（实测得 2）。
行匹配无法区分「严重度列」与「状态列」，本脚本改为：表头含「编号」「严重」「状态」三列的表，
逐数据行按列取值。

判定口径（与 docs/init/00 §7.2 的字段说明一致）：
  · 严重度：取单元格里第一个 `P0~P3`；无 P 编号但含「阻塞」→ P0；其余 → 无法识别（unparsed）。
  · 状态：优先看首个英文词（Open / In-Progress / Reopened = 未闭环；Fixed / Verified / Closed = 已闭环）；
    无英文词时按中文关键词，未闭环词优先（待修 / 修复中 / 未修 / 回归）；已修 / 已验证 / 已关闭 / 已根治 / 已解决 = 已闭环。
  · 认不出的行进 `unparsed_rows`，**绝不静默当作已闭环**；有 unparsed 行时退出码 1，由调用方转人工判定。

用法：
  python3 bugfix_scope.py --root . --version V0.1.0 [--sprint 003] [--file X.md ...]
        [--severity P0] [--status open|closed|all] [--json | --count]
  默认输出命中条目（人读）；`--count` 只输出命中条数；`--json` 输出
  {"bugs":[{id,sprint,severity,status,closed,file,line}],"unparsed_rows":[...],"count":N}。
  退出码：0 = 解析成功（无台账 / 无命中也是 0）；1 = 存在无法识别的数据行；2 = 用法错。
"""
import argparse
import glob
import json
import os
import re
import sys

OPEN_EN = ("open", "in-progress", "inprogress", "reopened")
CLOSED_EN = ("fixed", "verified", "closed")
OPEN_ZH = ("待修", "修复中", "未修", "未闭环", "回归", "未关闭")
CLOSED_ZH = ("已修", "已验证", "已关闭", "已根治", "已解决", "已闭环")


def split_cells(line):
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", body)]


def is_sep(line):
    s = line.strip()
    return s.startswith("|") and set(s) <= set("|-: ") and "-" in s


def parse_severity(cell):
    m = re.search(r"P([0-3])", cell, re.I)
    if m:
        return "P" + m.group(1)
    if "阻塞" in cell:
        return "P0"
    return None


def parse_closed(cell):
    """返回 True（已闭环）/ False（未闭环）/ None（认不出）。"""
    low = cell.lower()
    m = re.search(r"[a-z][a-z-]*", low)
    if m:
        w = m.group(0)
        if w in OPEN_EN:
            return False
        if w in CLOSED_EN:
            return True
    if any(k in cell for k in OPEN_ZH):
        return False
    if any(k in cell for k in CLOSED_ZH):
        return True
    return None


def parse_file(path):
    bugs, unparsed = [], []
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    cols = None
    for no, ln in enumerate(lines, 1):
        if not ln.strip().startswith("|"):
            cols = None
            continue
        if is_sep(ln):
            continue
        cells = split_cells(ln)
        if cols is None:
            heads = [c.replace(" ", "") for c in cells]
            if "编号" in heads and "严重" in heads and "状态" in heads:
                cols = {k: heads.index(k) for k in ("编号", "严重", "状态")}
                cols["Sprint"] = heads.index("Sprint") if "Sprint" in heads else None
            continue
        need = max(v for v in cols.values() if v is not None)
        bid = cells[cols["编号"]] if cols["编号"] < len(cells) else ""
        if len(cells) <= need:
            unparsed.append({"id": bid, "file": path, "line": no, "reason": "列数不足"})
            continue
        if not bid or set(bid) <= set("-—_ "):
            continue  # 空占位行
        sev = parse_severity(cells[cols["严重"]])
        closed = parse_closed(cells[cols["状态"]])
        sprint = ""
        if cols["Sprint"] is not None:
            m = re.search(r"\d+", cells[cols["Sprint"]])
            sprint = m.group(0).lstrip("0") or "0" if m else ""
        if sev is None or closed is None:
            why = "严重度无法识别" if sev is None else "状态无法识别"
            unparsed.append({"id": bid, "file": path, "line": no, "reason": why,
                             "severity_cell": cells[cols["严重"]], "status_cell": cells[cols["状态"]]})
            continue
        bugs.append({"id": bid, "sprint": sprint, "severity": sev, "status": cells[cols["状态"]],
                     "closed": closed, "file": path, "line": no})
    return bugs, unparsed


def main(argv=None):
    ap = argparse.ArgumentParser(description="按列解析 bugfix 台账，判未闭环缺陷")
    ap.add_argument("--root", default=".")
    ap.add_argument("--version")
    ap.add_argument("--file", action="append", default=[])
    ap.add_argument("--sprint")
    ap.add_argument("--severity", choices=["P0", "P1", "P2", "P3"])
    ap.add_argument("--status", choices=["open", "closed", "all"], default="all")
    out = ap.add_mutually_exclusive_group()
    out.add_argument("--json", action="store_true")
    out.add_argument("--count", action="store_true")
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    files = list(a.file)
    if a.version:
        files += sorted(glob.glob(os.path.join(a.root, "docs", "bugfix", a.version, "bugfix-*.md")))
    if not files and not a.version:
        print("用法错：需 --version 或 --file", file=sys.stderr)
        return 2
    want_sprint = None
    if a.sprint:
        m = re.search(r"\d+", a.sprint)
        if not m:
            print("用法错：--sprint 需含数字", file=sys.stderr)
            return 2
        want_sprint = m.group(0).lstrip("0") or "0"
    bugs, unparsed = [], []
    for f in files:
        if not os.path.isfile(f):
            print("用法错：文件不存在 %s" % f, file=sys.stderr)
            return 2
        b, u = parse_file(f)
        bugs += b
        unparsed += u
    sel = [b for b in bugs
           if (not a.severity or b["severity"] == a.severity)
           and (a.status == "all" or (a.status == "closed") == b["closed"])
           and (want_sprint is None or b["sprint"] == want_sprint)]
    rc = 1 if unparsed else 0
    if a.count:
        print(len(sel))
    elif a.json:
        print(json.dumps({"bugs": sel, "unparsed_rows": unparsed, "count": len(sel)}, ensure_ascii=False, indent=2))
    else:
        for b in sel:
            print("%s  %s  Sprint-%s  %s  (%s:%d)" % (b["id"], b["severity"], b["sprint"] or "?", b["status"], b["file"], b["line"]))
        for u in unparsed:
            print("UNPARSED %s %s (%s:%d)" % (u["id"], u["reason"], u["file"], u["line"]))
        print("命中 %d 条；无法识别 %d 行" % (len(sel), len(unparsed)))
    return rc


if __name__ == "__main__":
    sys.exit(main())
