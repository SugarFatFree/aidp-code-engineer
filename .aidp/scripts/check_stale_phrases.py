#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_stale_phrases.py — 陈旧短语黑名单棘轮（模板维护脚本）。

## 为什么需要本脚本

行为改了，描述旧行为的句子却散落在 README / 范式文档 / 命令说明里继续「生效」：
「`/sprint-test` 只做静态与文档层」「部署 SOP 每次生成」「每个 Sprint 在独立分支」……
这些句子**与新口径同时存在时没有任何结构性冲突**（每处单看都通顺），所以已有的一致性
检查（计数、引用、编号）一个都抓不到，只能靠人下一次通读时撞见。一次审计一口气翻出
十余处，全是历史行为变更时「只改了主路径、没扫其余描述面」的遗留。

## 机制：黑名单棘轮

数据文件 `{{AIDP_HOME}}/scripts/stale-phrases.txt`，每行一条：

    正则 | 作用域 glob | 现行替代说明 | 引入版本

  · 以 ` | `（空格竖线空格）分四段；**正则内部的 `|` 前后不得带空格**（用 `(?:a|b)`）；
  · 作用域 glob 可用 `;` 分多个，`**` 跨目录，`{{AIDP_HOME}}` 展开为运行包根；
  · `#` 开头与空行忽略；坏条目（字段不足 / 正则不合法 / 版本格式错）报 `bad-entry`，不静默跳过。

**棘轮语义**：每条初始即 0 命中；之后**每次改变行为的提交，往黑名单加一条旧口径**
（与约定 30「只陈述最终行为」配套）——旧说法再次出现就是 ERROR，而不是等下一轮审计。

## 误报控制

  · 命中行带 `stale-ignore: 理由`（理由必填）才放行——说明性引用（「旧版曾……」）用它，
    不要把正则写宽或在脚本里加文件名白名单；
  · 全局排除（历史 / 理据性文档，按定义允许提旧说法）：`**/rationale.md`、`版本变更历史.md`、
    `设计目标.md`、`docs/superpowers/**`、`memory/.aidp/**`、`**/skills/**`（SKILL 本体 + bundle
    镜像）、`.aidp-backup*`；
  · 反面说明（「不要求每个 Sprint 新建分支」）靠正则自带的 `(?<!不要求)` 等断言放行，
    写条目时先 `grep` 一遍现仓确认 0 命中。

## 适用范围

仅**模板仓库**（根有 `版本变更历史.md`）：黑名单管的是模板自己的描述面，下游项目的 `docs/` 是用户的。
非模板仓库、或数据文件缺失 → `applicable: false`，退出 0。

## 用法

    python3 AIDP_HOME/scripts/check_stale_phrases.py [--root .] [--json] [--phrases 文件] [--self-check]

退出码：0 = 无陈旧口径（或不适用）；1 = 有命中 / 坏条目；2 = 用法错。
"""
from __future__ import annotations

import argparse
import json
import os
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
PHRASES_REL = f"{RUNTIME_REL}/scripts/stale-phrases.txt"
TEMPLATE_MARKER = "版本变更历史.md"
HOME_TOKEN = "{{AIDP_HOME}}"
VERSION_RE = re.compile(r"^V\d+\.\d+\.\d+\+?$")
IGNORE_RE = re.compile(r"stale-ignore:\s*(?!-->)\S")
SKIP_DIRS = {".git", "node_modules", "__pycache__", "dist", "build", ".venv"}
GLOBAL_EXCLUDES = ("**/rationale.md", "版本变更历史.md", "设计目标.md", "docs/superpowers/**",
                   "memory/.aidp/**", "**/skills/**", "**/.aidp-backup*/**", "**/assets/**")
MAX_BYTES = 2 * 1024 * 1024


def glob_to_re(glob: str) -> re.Pattern:
    out, i = [], 0
    while i < len(glob):
        c = glob[i]
        if glob.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif glob.startswith("**", i):
            out.append(".*")
            i += 2
        elif c == "*":
            out.append("[^/]*")
            i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(c))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def parse_entries(text: str):
    """→ (entries, bad)。entry = dict(rx, scopes, replacement, since, lineno, raw)。"""
    entries, bad = [], []
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in raw.rsplit(" | ", 3)]
        why = None
        if len(parts) != 4 or not all(parts):
            why = "需要四段「正则 | 作用域 | 现行替代 | 引入版本」"
        elif not VERSION_RE.match(parts[3]):
            why = f"引入版本格式应为 V1.2.3：{parts[3]!r}"
        else:
            try:
                rx = re.compile(parts[0])
            except re.error as e:
                why = f"正则不合法：{e}"
        if why:
            bad.append({"kind": "bad-entry", "file": PHRASES_REL, "line": n, "detail": why, "raw": line[:100]})
            continue
        scopes = [glob_to_re(s.strip().replace(HOME_TOKEN, RUNTIME_REL)) for s in parts[1].split(";") if s.strip()]
        entries.append({"rx": rx, "pattern": parts[0], "scopes": scopes, "replacement": parts[2],
                        "since": parts[3], "lineno": n})
    return entries, bad


def _iter_md(root: Path):
    excl = [glob_to_re(g) for g in GLOBAL_EXCLUDES]
    for dp, dn, fn in os.walk(root):
        dn[:] = sorted(d for d in dn if d not in SKIP_DIRS)
        for f in sorted(fn):
            if not f.endswith(".md"):
                continue
            p = Path(dp) / f
            rel = p.relative_to(root).as_posix()
            if any(e.match(rel) for e in excl):
                continue
            try:
                if p.is_symlink() or p.stat().st_size > MAX_BYTES:
                    continue
            except OSError:
                continue
            yield rel, p


def scan(root: Path, phrases: Path | None = None) -> dict:
    if not (root / TEMPLATE_MARKER).is_file():
        return {"applicable": False, "reason": f"非模板仓库（根无 {TEMPLATE_MARKER}）", "findings": []}
    pf = phrases or (root / PHRASES_REL)
    if not pf.is_file():
        return {"applicable": False, "reason": f"无黑名单数据文件 {PHRASES_REL}", "findings": []}
    entries, bad = parse_entries(pf.read_text(encoding="utf-8"))
    findings, scanned = list(bad), 0
    for rel, path in _iter_md(root):
        active = [e for e in entries if any(s.match(rel) for s in e["scopes"])]
        if not active:
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        scanned += 1
        for i, line in enumerate(lines, 1):
            if IGNORE_RE.search(line):
                continue
            for e in active:
                m = e["rx"].search(line)
                if m:
                    findings.append({"kind": "stale-phrase", "file": rel, "line": i, "text": m.group(0)[:80],
                                     "pattern": e["pattern"], "replacement": e["replacement"],
                                     "since": e["since"]})
    return {"applicable": True, "entries": len(entries), "scanned": scanned, "findings": findings}


def self_check() -> bool:
    root = Path(tempfile.mkdtemp(prefix="aidp-stale-check-"))
    try:
        (root / TEMPLATE_MARKER).write_text("x\n", encoding="utf-8")
        pf = root / "p.txt"
        pf.write_text(r"旧口径甲(?:乙|丙) | **/*.md | 新口径 | V1.0.0" "\n", encoding="utf-8")
        (root / "bad.md").write_text("这里有旧口径甲乙。\n", encoding="utf-8")
        (root / "ok.md").write_text("新口径。\n旧口径甲丙 <!-- stale-ignore: 历史说明 -->\n", encoding="utf-8")
        (root / "rationale.md").write_text("旧口径甲乙\n", encoding="utf-8")
        got = [(f["file"], f["line"]) for f in scan(root, pf)["findings"]]
        return got == [("bad.md", 1)]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="陈旧短语黑名单棘轮")
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--phrases", default=None, help="黑名单数据文件（缺省 {{AIDP_HOME}}/scripts/stale-phrases.txt）")
    ap.add_argument("--self-check", action="store_true")
    args = ap.parse_args(argv)
    if args.self_check:
        ok = self_check()
        print(json.dumps({"self_check": "pass" if ok else "fail"}, ensure_ascii=False))
        return 0 if ok else 1
    root = Path(args.root).resolve()
    if not root.is_dir():
        ap.error("--root 必须是目录")
    res = scan(root, Path(args.phrases) if args.phrases else None)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    elif not res["applicable"]:
        print(f"[N/A] {res['reason']}")
    elif res["findings"]:
        for f in res["findings"]:
            if f["kind"] == "bad-entry":
                print(f"[ERROR] bad-entry {f['file']}:{f['line']} {f['detail']}")
            else:
                print(f"[ERROR] stale-phrase {f['file']}:{f['line']} 「{f['text']}」（自 {f['since']} 起已废）")
                print(f"        → 现行：{f['replacement']}；确属说明性引用 → 同行加 `stale-ignore: 理由`")
    else:
        print(f"[OK] 无陈旧口径（{res['entries']} 条黑名单 / 巡检 {res['scanned']} 份 .md）")
    return 1 if res.get("findings") else 0


if __name__ == "__main__":
    sys.exit(main())
