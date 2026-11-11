#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_readme_registry.py — 目录里的文件必须在同目录 README 登记（模板维护脚本）。

## 为什么需要本脚本

`reference/README.md` 等自述「新增文件须登记」，可没有任何东西在新增文件时检查它：
`部署操作约定.md` 落地后一度是该目录唯一未登记的文件，读 README 找文件的人（和执行体）
看不见它。「README 是目录索引」这类自述若无机检，与「人记得登记」等价，迟早漏。

## 判据（确定性，零语义推断）

扫描面：`{{AIDP_HOME}}/*/README.md`（运行包各子目录）与 `docs/**/README.md`（项目根 docs 下，
版本目录 `V<数字>…` 不下钻）。对每份 README 所在目录的**直接子项**（文件与子目录）：

  · basename 必须在该 README 正文里出现（ASCII 边界匹配，`a.md` 不会被 `data.md` 蒙混）；
  · 范围写法视为逐一登记：`约定细则-1.md ~ 约定细则-5.md` / `约定细则-1 ~ 5`；
  · 排除：README 自身、隐藏项、`__pycache__`、`tests`、版本目录 `V<数字>…`。

## 豁免（显式标记，理由必填）

    <!-- registry-ignore: 文件名 理由 -->    写在该目录的 README 里；缺理由不生效

## 适用范围

仅**模板仓库**（根有 `版本变更历史.md`）：下游项目的 `docs/` 下有用户自己的文件，不归契约管。
非模板仓库输出 `applicable: false` 并退出 0（verify.py 记 N/A）。

## 用法

    python3 AIDP_HOME/scripts/check_readme_registry.py [--root .] [--json] [--self-check]

退出码：0 = 全部登记（或不适用）；1 = 有未登记；2 = 用法错。
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

_scripts = str(Path(__file__).resolve().parent)
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)
from aidp_runtime import runtime_relpath

RUNTIME_REL = runtime_relpath("", __file__)
TEMPLATE_MARKER = "版本变更历史.md"
SKIP_NAMES = {"README.md", "__pycache__", "tests"}
VERSION_DIR_RE = re.compile(r"^V\d")
IGNORE_RE = re.compile(r"<!--\s*registry-ignore:\s*(\S+)\s+(\S[^>]*?)\s*-->")
# 范围：`<前缀><起>[.ext] ~ [<前缀>]<止>[.ext]`，前缀不含空白 / 反引号 / 竖线 / 括号类标点
_P = r"[^\s`|()（）\[\]「」,，;；:：]*?"
RANGE_RE = re.compile(
    r"(?P<p>" + _P + r")(?P<a>\d+)(?P<e1>\.[A-Za-z0-9]+)?`?\s*[~～]\s*`?"
    r"(?:" + _P + r")(?P<b>\d+)(?P<e2>\.[A-Za-z0-9]+)?")


def expand_ranges(text: str) -> set[str]:
    out: set[str] = set()
    for m in RANGE_RE.finditer(text):
        a, b = int(m.group("a")), int(m.group("b"))
        if not (0 <= a <= b <= a + 200):
            continue
        exts = [e for e in (m.group("e1"), m.group("e2")) if e] or [""]
        for n in range(a, b + 1):
            for e in exts:
                out.add(f"{m.group('p')}{n}{e}")
    return out


def mentioned(name: str, text: str, ranged: set[str]) -> bool:
    if name in ranged or Path(name).stem in ranged:
        return True
    return re.search(r"(?<![A-Za-z0-9_.-])" + re.escape(name) + r"(?![A-Za-z0-9_-])", text) is not None


def _readmes(root: Path):
    aidp = root / RUNTIME_REL
    if aidp.is_dir():
        for d in sorted(aidp.iterdir()):
            if d.is_dir() and (d / "README.md").is_file():
                yield d / "README.md"
    docs = root / "docs"
    if docs.is_dir():
        stack = [docs]
        while stack:
            cur = stack.pop()
            if (cur / "README.md").is_file():
                yield cur / "README.md"
            for sub in sorted(cur.iterdir()):
                if sub.is_dir() and not sub.name.startswith(".") and not VERSION_DIR_RE.match(sub.name) \
                        and sub.name != "__pycache__":
                    stack.append(sub)


def scan(root: Path) -> dict:
    if not (root / TEMPLATE_MARKER).is_file():
        return {"applicable": False, "reason": f"非模板仓库（根无 {TEMPLATE_MARKER}）", "scanned": 0, "findings": []}
    findings, scanned = [], 0
    for readme in sorted(set(_readmes(root))):
        try:
            text = readme.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        scanned += 1
        ignored = {m.group(1) for m in IGNORE_RE.finditer(text)}
        text = re.sub(r"<!--\s*registry-ignore:.*?-->", "", text)   # 豁免标记自带文件名，不算「登记」
        ranged = expand_ranges(text)
        for item in sorted(readme.parent.iterdir(), key=lambda p: p.name):
            n = item.name
            if n in SKIP_NAMES or n.startswith(".") or n in ignored:
                continue
            if item.is_dir() and VERSION_DIR_RE.match(n):
                continue
            if mentioned(n, text, ranged):
                continue
            findings.append({
                "kind": "unregistered",
                "file": item.relative_to(root).as_posix(),
                "readme": readme.relative_to(root).as_posix(),
                "line": 0,
                "hint": f"在 {readme.name} 登记 `{n}`，或加 `<!-- registry-ignore: {n} 理由 -->`",
            })
    return {"applicable": True, "scanned": scanned, "findings": findings}


def self_check() -> bool:
    root = Path(tempfile.mkdtemp(prefix="aidp-registry-check-"))
    try:
        (root / "版本变更历史.md").write_text("x\n", encoding="utf-8")
        d = root / RUNTIME_REL / "reference"
        d.mkdir(parents=True)
        (d / "README.md").write_text("`a.md` 约定细则-1 ~ 2\n", encoding="utf-8")
        for n in ("a.md", "约定细则-1.md", "约定细则-2.md", "orphan.md"):
            (d / n).write_text("x\n", encoding="utf-8")
        got = [f["file"] for f in scan(root)["findings"]]
        return got == [f"{RUNTIME_REL}/reference/orphan.md"]       # 阳性 1 条 + 阴性（登记 / 范围）0 条
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="目录内文件必须在同目录 README 登记")
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-check", action="store_true")
    args = ap.parse_args(argv)
    if args.self_check:
        ok = self_check()
        print(json.dumps({"self_check": "pass" if ok else "fail"}, ensure_ascii=False))
        return 0 if ok else 1
    root = Path(args.root).resolve()
    if not root.is_dir():
        ap.error("--root 必须是目录")
    res = scan(root)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    elif not res["applicable"]:
        print(f"[N/A] {res['reason']}")
    elif res["findings"]:
        for f in res["findings"]:
            print(f"[ERROR] {f['kind']} {f['file']}（README: {f['readme']}）")
            print(f"        → {f['hint']}")
    else:
        print(f"[OK] README 登记完整（{res['scanned']} 份 README）")
    return 1 if res.get("findings") else 0


if __name__ == "__main__":
    sys.exit(main())
