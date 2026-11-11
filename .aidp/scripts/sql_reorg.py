#!/usr/bin/env python3
"""SQL 整理（/version 发布期 3.3.7）的内容守恒校验。

check --orig <dir> --new <dir> [--exclude 99_回滚脚本.sql]... [--json]
  按语句切分（跳过注释与字符串内分号）、规范化空白与引号外大小写，比对两侧语句多重集合：
  - 整型比较，不依赖 shell 变量拼接（`grep -c … || echo 0` 在 0 行时会得到 "0\\n0"，比较报错被当作放行）；
  - 原侧 0 条 / 新侧 0 条 / 集合不等 → 一律不通过（fail-closed）。
退出码：0 = 守恒；1 = 不守恒（调用方必须保留原文件）；2 = 入参错误（目录不存在等）。
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from development_scope import _statements  # 复用既有语句切分器（单一实现）

DEFAULT_EXCLUDE = ("99_回滚脚本.sql",)
QUOTED = re.compile(r"('(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|`(?:``|[^`])*`)")


def fingerprint(statement):
    """引号外转小写、空白折叠；引号内（字符串字面量 / 引号标识符）原样保留。"""
    parts = QUOTED.split(statement)
    return " ".join("".join(p if i % 2 else p.lower() for i, p in enumerate(parts)).split())


def collect(directory, exclude):
    counts = Counter()
    for path in sorted(Path(directory).glob("*.sql")):
        if path.name in exclude:
            continue
        for stmt in _statements(path.read_text(encoding="utf-8")):
            counts[fingerprint(stmt)] += 1
    return counts


def check(orig, new, exclude=DEFAULT_EXCLUDE):
    a, b = collect(orig, exclude), collect(new, exclude)
    oc, nc = sum(a.values()), sum(b.values())
    missing = sorted((a - b).elements())
    extra = sorted((b - a).elements())
    passed = oc > 0 and nc > 0 and not missing and not extra
    reason = ("原侧无可识别语句，无法证明守恒" if oc == 0 else
              "新侧无可识别语句" if nc == 0 else
              "语句集合不一致" if not passed else "")
    return {"orig_count": oc, "new_count": nc, "missing": missing, "extra": extra,
            "passed": passed, "reason": reason}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="整理前后语句守恒校验")
    c.add_argument("--orig", required=True)
    c.add_argument("--new", required=True)
    c.add_argument("--exclude", action="append", default=None, help="按文件名排除，可重复；默认 99_回滚脚本.sql")
    c.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    for d in (a.orig, a.new):
        if not Path(d).is_dir():
            print("目录不存在：" + d, file=sys.stderr)
            return 2
    result = check(a.orig, a.new, tuple(a.exclude) if a.exclude else DEFAULT_EXCLUDE)
    if a.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(("PASS" if result["passed"] else "FAIL") + f": 原 {result['orig_count']} / 新 {result['new_count']}"
              + (f"（{result['reason']}）" if result["reason"] else ""))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
