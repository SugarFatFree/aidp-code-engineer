#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 `tests/README.md` 的分组表与 `test_guard_scripts.py` 的实跑分组对齐。

## 为什么要有它

这张表按标题逐组列出 `test_guard_scripts.py` 的分组。靠人手抄维护必然漂移，
只加一道行数门也不够：门每次都红，人每次都得手工重排。
故把「重排」做成确定性动作：真值现算（跑一遍测试、按实跑顺序取分组标题），
已有的「覆盖」列描述按标题原样保留，新增分组填 `—`。

## 用法

    python3 .aidp/scripts/tests/sync_group_table.py          # 写回 README
    python3 .aidp/scripts/tests/sync_group_table.py --check   # 只比对，不写（有漂移 exit 1）

退出码：`0`=已一致 / 已写回；`1`=`--check` 下检出漂移；`2`=用法或环境错。
"""
import argparse
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SUITE = os.path.join(HERE, "test_guard_scripts.py")
README = os.path.join(HERE, "README.md")
HEADER = "| # | 分组标题 | 覆盖 |"
GROUP_RE = re.compile(r"^【(.*)】|^\[(\d+)\] (.*)$", re.M)


def live_groups():
    """跑一遍测试套件，按**实跑顺序**取分组标题（两种打印形态都认）。"""
    cp = subprocess.run([sys.executable, SUITE], capture_output=True, text=True)
    return [a if a else b for a, _num, b in GROUP_RE.findall(cp.stdout)]


def rebuild(text, groups):
    start = text.index(HEADER)
    lines = text[start:].split("\n")
    end = next(i for i, ln in enumerate(lines) if i > 1 and not ln.startswith("|"))
    # 保留已填的「覆盖」列：按分组标题匹配，不按行号（插入/重排都不会错位）
    cover = {}
    for ln in lines[2:end]:
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cells) >= 3:
            cover[cells[1].strip("`")] = cells[2]
    tbl = [HEADER, "|---|---------|------|"]
    for i, g in enumerate(groups, 1):
        tbl.append(f"| {i} | `{g}` | {cover.get(g, '—')} |")
    return text[:start] + "\n".join(tbl) + "\n" + "\n".join(lines[end:])


def main():
    ap = argparse.ArgumentParser(description="tests/README 分组表 ↔ 实跑分组对齐")
    ap.add_argument("--check", action="store_true", help="只比对不写回")
    args = ap.parse_args()

    if not (os.path.isfile(SUITE) and os.path.isfile(README)):
        sys.stderr.write("❌ 找不到 test_guard_scripts.py 或 README.md\n")
        return 2
    groups = live_groups()
    if not groups:
        sys.stderr.write("❌ 未从测试输出解析出任何分组标题（套件是否跑挂了？）\n")
        return 2
    old = open(README, encoding="utf-8").read()
    try:
        new = rebuild(old, groups)
    except (ValueError, StopIteration):
        sys.stderr.write("❌ README 里找不到分组表表头，或表格结构异常\n")
        return 2

    if new == old:
        print(f"[OK] 分组表已与实跑一致（{len(groups)} 组）")
        return 0
    if args.check:
        rows = len([ln for ln in old.split("\n") if re.match(r"^\|\s*\d+\s*\|", ln)])
        sys.stderr.write(f"❌ 分组表漂移：README {rows} 行 vs 实跑 {len(groups)} 组 —— "
                         f"跑 `python3 .aidp/scripts/tests/sync_group_table.py` 对齐\n")
        return 1
    open(README, "w", encoding="utf-8").write(new)
    print(f"[OK] 分组表已重排为 {len(groups)} 组（「覆盖」列按标题保留，新增填 —）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
