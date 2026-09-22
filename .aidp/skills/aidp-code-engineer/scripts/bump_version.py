#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bump_version.py —— 提升范式版本号（仅在用户明确要求 bump 时使用）。

权威源是模板项目根 `版本变更历史.md`「当前范式版本」标记 `**AIDP V<x.y.z>**（最后更新：YYYY-MM-DD）`。
本脚本改写该标记，然后调用 `mirror_to_bundle.py` 派生 `assets/SCAFFOLD_VERSION` 与
`assets/CONTRACT_MANIFEST.json`。变更记录条目由人撰写（只写使用者可感知的能力变化）。

用法：
    python3 .aidp/skills/aidp-code-engineer/scripts/bump_version.py <新版本> [--date YYYY-MM-DD] [--root DIR] [--dry-run]

退出码：0 成功 · 1 派生失败 · 2 参数或环境错误
"""
import argparse
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import scaffold_lib as L  # noqa: E402

MARK_RE = re.compile(r"\*\*AIDP\s+V\d+\.\d+\.\d+\*\*(（最后更新：\d{4}-\d{2}-\d{2}）)?")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="提升范式版本号并派生 bundle 版本文件")
    ap.add_argument("new")
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--root", default=None)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    if not re.fullmatch(r"V\d+\.\d+\.\d+", a.new):
        print(f"⛔ 版本号须形如 V1.2.3：{a.new}", file=sys.stderr)
        return 2
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", a.date):
        print(f"⛔ 日期须形如 YYYY-MM-DD：{a.date}", file=sys.stderr)
        return 2
    root = Path(a.root).resolve() if a.root else HERE.parents[3]
    log = root / L.CHANGELOG
    text = L.read_text(log)
    old = L.changelog_version(root)
    if not old:
        print(f"⛔ {log} 缺「当前范式版本」标记 `**AIDP Vx.y.z**`", file=sys.stderr)
        return 2
    if L.parse_ver(a.new) <= L.parse_ver(old):
        print(f"⛔ 新版本 {a.new} 须大于当前 {old}", file=sys.stderr)
        return 2
    new_text = MARK_RE.sub(f"**AIDP {a.new}**（最后更新：{a.date}）", text, count=1)
    print(f"范式版本 {old} → {a.new}（{a.date}）")
    if a.dry_run:
        print("（dry-run，未写入）")
        return 0
    log.write_text(new_text, encoding="utf-8")
    p = subprocess.run([sys.executable, str(HERE / "mirror_to_bundle.py"), "--root", str(root)],
                       capture_output=True, text=True)
    print((p.stdout or "").strip().splitlines()[0] if p.stdout.strip() else "")
    if p.returncode != 0 or L.bundle_version() != a.new:
        print(f"⛔ 派生失败：{(p.stderr or p.stdout).strip()[:400]}", file=sys.stderr)
        return 1
    print(f"✅ assets/SCAFFOLD_VERSION = {a.new}；请在 {L.CHANGELOG}「变更记录」补一条本版本的能力摘要")
    return 0


if __name__ == "__main__":
    sys.exit(main())
