#!/usr/bin/env python3
"""scripts_usage.py — 「这个脚本到底怎么调」的现场速查（脚手架契约脚本）。

## 为什么不是一份手写速查表

`.aidp/scripts/` 与各 SKILL `scripts/` 下有上百个脚本，CLI 形态互不统一——实测同一轮里
踩到四种：位置子命令（`check_sprint_numbering.py check`）、`--paths <路径>`、单个位置路径、
三个位置参数。子 Agent 每次都要试错 1~2 次才跑对，而失败信息是 argparse 原文、不指向正确用法。

统一 CLI 会破坏既有调用（上游 SKILL 的脚本也不归本项目改，约定 16），手写速查表则**必然过期**
——它是又一处"加东西的人不会想起去改"的计数式副本。

故做成**现场生成**：直接问每个脚本自己的 `--help`，输出永远是当下的真值。

## 用法

    python3 .aidp/scripts/scripts_usage.py                  # 全部（本项目 + 各 SKILL）
    python3 .aidp/scripts/scripts_usage.py check_count      # 名字含该子串的
    python3 .aidp/scripts/scripts_usage.py --json

输出每个脚本一行 `usage:`（argparse 的第一行），必要时带上位置参数名——那正是最常踩的一类。

退出码：0 正常；2 参数错。
"""
import argparse
import json
import os
import re
import subprocess
import sys

ROOTS = (".aidp/scripts", ".aidp/skills")
SKIP_DIRS = {"__pycache__", "tests", "assets", "node_modules"}
SKIP_NAMES = {"__init__.py", "scripts_usage.py"}


def _iter_scripts(root):
    for base in ROOTS:
        b = os.path.join(root, base)
        if not os.path.isdir(b):
            continue
        for dp, dn, fns in os.walk(b):
            dn[:] = [d for d in dn if d not in SKIP_DIRS]
            # SKILL 下只看 scripts/ 子目录，别把 lib/ 之类也算进来
            if base.endswith("skills") and os.path.basename(dp) != "scripts":
                continue
            for fn in sorted(fns):
                if fn.endswith(".py") and fn not in SKIP_NAMES:
                    yield os.path.join(dp, fn)


def _usage(path):
    try:
        cp = subprocess.run([sys.executable, path, "--help"],
                            capture_output=True, text=True, timeout=20)
    except Exception as e:
        return f"（取不到：{e}）"
    out = (cp.stdout or cp.stderr or "").strip()
    if not out:
        return "（无 --help，可能不是 argparse 脚本）"
    m = re.search(r"usage:\s*(.+?)(?:\n\n|\npositional|\noptions|\n可选|\Z)", out, re.S)
    if not m:
        return out.splitlines()[0][:200]
    return re.sub(r"\s+", " ", m.group(1)).strip()[:300]


def run(root=".", pattern=None):
    rows = []
    for p in _iter_scripts(root):
        rel = os.path.relpath(p, root).replace(os.sep, "/")
        if pattern and pattern not in os.path.basename(rel):
            continue
        rows.append({"path": rel, "usage": _usage(p)})
    return {"count": len(rows), "scripts": rows}


def main():
    ap = argparse.ArgumentParser(description="脚本调用速查（现场问 --help，永不过期）")
    ap.add_argument("pattern", nargs="?", default=None, help="只列名字含该子串的脚本")
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    r = run(a.root, a.pattern)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0
    for row in r["scripts"]:
        print(f"{row['path']}\n    {row['usage']}")
    print(f"\n共 {r['count']} 个脚本。⚠️ 位置参数（usage 里不带 `--` 的那些）是最常踩的一类，"
          f"传成 flag 会得到 argparse 原文报错。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
