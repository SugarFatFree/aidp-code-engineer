#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_release_residual_gate.py — 零残留断言「发布总闸」（约定 33 × 约定 37 发布期）。

## 它堵的缺口

规划期强制产出的「零残留断言登记表」**只增不退**；Sprint 收尾只跑「守护面 ∩ 本轮 git diff ≠ ∅」
的那几条、其余标 `skipped(out-of-scope)`。这在 Sprint 内是对的 —— 没碰到的面不必每轮重跑。

但**发布期若也接受 `skipped`**，整张表就在测试期和发布期**都没有消费入口**：
每一轮都合法地跳过一部分，而没有任何一个时刻要求它全跑一次 ⇒ 规划期产出即沉睡（约定 33）。

而此前「发布总闸」这件事**只有散文**：`flows/version/release-7.md` 的 Step 3.3.12bis 写着
「⛔ 不接受任何 skipped」，`commands/version.md` 的骨架表照抄了这句 ——
于是它在骨架层**看起来像硬门**，实际无执行体、无判定器、无阻断力。这是最糟的形态：
读的人以为有门，而「跑了」与「没跑」在产物上完全同形。

## 与上游 `check_residual_assertions.py` 的边界（约定 21，不重复）

| | 上游 `dev-manual-testcase/scripts/check_residual_assertions.py` | 本脚本 |
| :- | :- | :- |
| 问的问题 | 登记表**形态**对不对（7 类，含 Z4 阳性对照拦恒 0 假绿） | 每条在役断言**在本次发布前真跑过一次**吗 |
| 时机 | `/sprint-selftest` Step 2（规划期） | `/version` Step 3.3.12bis（发布期总闸） |
| 判据 | 列齐不齐、字段空不空 | 方向一·现状命中 = `0 命中(<日期>)` 且日期是本次发布当天 |

⛔ 本脚本**不重跑**任何断言、也不校形态 —— 它只回答「有没有在发布前跑」。

## 判据（确定性三态）

1. 本版用例册里**一条反向断言都没有** → `no-assertion`，INFO 跳过（合法：本版无零残留断言）。
2. 有反向断言**却没有登记表** → ERROR（登记表是"只增不退"的载体，缺它等于断言无人管）。
3. 有登记表 → 逐行判**在役**行（`已退役` 行跳过）：
   · 方向一·现状命中 必须是 `0 命中(<YYYY-MM-DD ...>)`；
   · 日期必须等于 `--as-of`（缺省=今天）—— 这正是「发布前全部跑一次」的可判定形式；
   · 出现 `skipped` / `—` / 非零命中 / 无日期 → ERROR 逐条点名。

退出码：0 = 通过（或合法跳过）；1 = 有 ERROR；2 = 用法 / 路径错。
"""
import argparse
import datetime
import json
import os
import re
import sys

# 登记表表头（7 列）识别：不写死全部列名，只认两根定位柱，容忍列序微调与全/半角差异
HEADER_RE = re.compile(r"\|\s*#\s*\|.*断言.*\|.*守护面.*\|", re.I)
ROW_RE = re.compile(r"^\|\s*(Z-\d+)\s*\|")
# 反向断言在用例正文里的形态（用于判「有断言却没登记表」）
ASSERTION_RE = re.compile(r"断言\(反向\)\s*[:：]\s*不存在")
# 「0 命中(2026-09-07 10:12)」——命中数与日期都要拿到
HIT_RE = re.compile(r"(\d+)\s*命中\s*[（(]\s*(\d{4}-\d{2}-\d{2})")
RETIRED_RE = re.compile(r"已退役")
SKIPPED_RE = re.compile(r"skipped|out-of-scope|未跑|待跑|暂不跑", re.I)


def _cells(line):
    """拆 Markdown 表行为单元格列表（去掉首尾空段）。"""
    parts = line.split("|")
    if parts and not parts[0].strip():
        parts = parts[1:]
    if parts and not parts[-1].strip():
        parts = parts[:-1]
    return [c.strip() for c in parts]


def scan(root, version, as_of):
    base = os.path.join(root, "docs", "testing", version, "研发自测")
    res = {"ok": True, "version": version, "as_of": as_of, "dir": base,
           "scanned_files": 0, "rows": 0, "active_rows": 0,
           "has_assertion": False, "has_table": False,
           "errors": [], "skipped_reason": None}
    if not os.path.isdir(base):
        res["ok"] = False
        res["skipped_reason"] = "no-testcase-dir"
        res["errors"].append({"row": "-", "msg": f"用例目录不存在：{base} —— 发布前无从核对零残留断言"})
        return res

    for dp, dn, fns in os.walk(base):
        dn[:] = [d for d in dn if d != "__pycache__"]
        for fn in sorted(fns):
            if not fn.endswith(".md"):
                continue
            path = os.path.join(dp, fn)
            try:
                lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
            except OSError as e:
                res["ok"] = False
                res["errors"].append({"row": "-", "msg": f"{path} 读取失败：{e}（fail-closed）"})
                continue
            res["scanned_files"] += 1
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            in_table = False
            for i, ln in enumerate(lines, 1):
                if ASSERTION_RE.search(ln):
                    res["has_assertion"] = True
                if HEADER_RE.search(ln):
                    in_table, res["has_table"] = True, True
                    continue
                if in_table and not ln.lstrip().startswith("|"):
                    in_table = False
                if not ROW_RE.match(ln.strip()):
                    continue
                cells = _cells(ln)
                if len(cells) < 7:
                    res["errors"].append({
                        "row": cells[0] if cells else "?", "file": rel, "line": i,
                        "msg": f"登记表行列数不足（{len(cells)}/7），无法判定是否跑过 —— 形态问题请先过上游 check_residual_assertions.py"})
                    continue
                zid, hit_cell, state_cell = cells[0], cells[4], cells[6]
                res["rows"] += 1
                if RETIRED_RE.search(state_cell):
                    continue                       # 已退役行不要求实跑
                res["active_rows"] += 1
                if SKIPPED_RE.search(hit_cell):
                    res["errors"].append({
                        "row": zid, "file": rel, "line": i,
                        "msg": f"方向一标了跳过（{hit_cell[:40]}）—— ⛔ 发布总闸不接受任何 skipped："
                               f"Sprint 内按守护面裁剪是合法的，发布前必须全跑一次，"
                               f"否则整张表在测试期和发布期都没有消费入口"})
                    continue
                m = HIT_RE.search(hit_cell)
                if not m:
                    res["errors"].append({
                        "row": zid, "file": rel, "line": i,
                        "msg": f"方向一无「N 命中(日期)」形态（实际：{hit_cell[:40]}）—— "
                               f"没有实跑时间戳就无法区分「本次发布前跑过」与「沿用上一轮结果」"})
                    continue
                n, day = int(m.group(1)), m.group(2)
                if n != 0:
                    res["errors"].append({
                        "row": zid, "file": rel, "line": i,
                        "msg": f"方向一 {n} 命中（{day}）—— 零残留断言未归零，本版仍有该文本残留"})
                elif day != as_of:
                    res["errors"].append({
                        "row": zid, "file": rel, "line": i,
                        "msg": f"方向一实跑日期 {day} ≠ 发布日 {as_of} —— 这是**上一轮**的结果。"
                               f"发布总闸要求本次发布前重跑一遍（守护面之外的代码也可能在此后引入残留）"})

    if not res["has_assertion"] and not res["has_table"]:
        res["skipped_reason"] = "no-assertion"
        return res
    if res["has_assertion"] and not res["has_table"]:
        res["errors"].append({
            "row": "-", "msg": "用例册里有反向断言（`断言(反向):不存在…`），却找不到「零残留断言登记表」—— "
                               "登记表是「只增不退」的唯一载体，缺它这些断言无人跟踪、无法退役、也无从总闸"})
    res["ok"] = not res["errors"]
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description="零残留断言发布总闸（发布前必须全跑一次、不接受 skipped）")
    ap.add_argument("--root", default=".")
    ap.add_argument("--version", default=None, help="目标版本号（--self-check 时可省）")
    ap.add_argument("--as-of", default=None,
                    help="发布日 YYYY-MM-DD（缺省=今天）。在役行的方向一实跑日期必须等于它")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-check", action="store_true", help="内置阳性对照：自造违规样本验证本门确实报得出")
    a = ap.parse_args(argv)

    if a.self_check:
        return _self_check()
    if not a.version:
        ap.error("--version 必填（除非 --self-check）")

    as_of = a.as_of or datetime.date.today().isoformat()
    res = scan(a.root, a.version, as_of)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res["ok"] else 1

    if res.get("skipped_reason") == "no-assertion":
        print(f"[OK] 本版无零残留断言（扫 {res['scanned_files']} 份用例文档），发布总闸不适用")
        return 0
    if res["ok"]:
        print(f"[OK] 零残留断言发布总闸通过：{res['active_rows']} 条在役断言均已于 {as_of} 实跑且 0 命中"
              f"（扫 {res['scanned_files']} 份用例文档 / 共 {res['rows']} 行登记）")
        return 0
    sys.stderr.write(f"❌ 零残留断言发布总闸未过（{version_hint(res)}）：{len(res['errors'])} 条\n")
    for e in res["errors"]:
        loc = f"{e.get('file', '')}:{e.get('line', '')}" if e.get("file") else ""
        sys.stderr.write(f"   · [{e['row']}] {loc}\n     {e['msg']}\n")
    sys.stderr.write("   按现有口径登记 docs/audit/<版本>/发布欠账.md（Important，不硬阻断发布），"
                     "但「跑没跑过」必须可判定 —— 这正是本门存在的理由\n")
    return 1


def version_hint(res):
    return f"{res['version']}；在役 {res['active_rows']} 条"


def _self_check():
    """阳性对照：造一份必然被抓的样本，确认本门报得出；再修正，确认转绿。"""
    import shutil
    import tempfile
    d = tempfile.mkdtemp()
    try:
        base = os.path.join(d, "docs", "testing", "V0.1", "研发自测")
        os.makedirs(base)
        hdr = ("| # | 断言 | 守护面 | 实跑命令 | 方向一·现状命中 | 方向二·阳性对照 | 退役状态 |\n"
               "| :- | :- | :- | :- | :- | :- | :- |\n")
        bad = hdr + ("| Z-01 | `断言(反向):不存在文本\"批量导出\"` | `src/**` | `grep ...` | "
                     "skipped(out-of-scope) | 1 命中 | 在役 |\n")
        open(os.path.join(base, "02_用例.md"), "w", encoding="utf-8").write(bad)
        r1 = scan(d, "V0.1", "2026-09-16")
        ok1 = (not r1["ok"]) and any("不接受任何 skipped" in e["msg"] for e in r1["errors"])
        good = hdr + ("| Z-01 | `断言(反向):不存在文本\"批量导出\"` | `src/**` | `grep ...` | "
                      "0 命中(2026-09-16 10:12) | 1 命中 | 在役 |\n")
        open(os.path.join(base, "02_用例.md"), "w", encoding="utf-8").write(good)
        r2 = scan(d, "V0.1", "2026-09-16")
        stale = hdr + ("| Z-01 | `断言(反向):不存在文本\"批量导出\"` | `src/**` | `grep ...` | "
                       "0 命中(2026-09-01 10:12) | 1 命中 | 在役 |\n")
        open(os.path.join(base, "02_用例.md"), "w", encoding="utf-8").write(stale)
        r3 = scan(d, "V0.1", "2026-09-16")
        ok3 = (not r3["ok"]) and any("上一轮" in e["msg"] for e in r3["errors"])
        print(f"阳性·skipped 被抓：{ok1}")
        print(f"阴性·当日实跑 0 命中放行：{r2['ok']}")
        print(f"阳性·沿用上一轮日期被抓：{ok3}")
        return 0 if (ok1 and r2["ok"] and ok3) else 1
    finally:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
