#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`{user}` 解析单一信源门 —— 命令 / 流程不得自行拼 `git config user.name`。

## 为什么需要这道门

`{user}` 决定 `memory/{version}/{user}/` 这个路径槽。它的合法来源只有
`vcs.py::developer_identity`（CLI = `python3 {{AIDP_HOME}}/scripts/vcs.py user`），
优先级：显式 → 本地 Git 身份 → `AIDP_USER` → OS 用户。

命令端若自己写 `$(git config user.name)`，在**无 Git 项目**或**设了 `AIDP_USER`** 的项目上
会解析出**另一个**身份。两边各自建目录，产物长得一模一样：

  · 写方按 `vcs.py` 的身份建 `memory/V0.2.0/alice/`；
  · 读方按 `git config` 的身份找 `memory/V0.2.0/--/`（或反过来）。

于是「SQL 已应用清单」永远读不到 → 部署前安全网恒判「未应用」；`progress.md` 扫错目录 →
Sprint 关闭状态误判。⛔ 这类缺陷**不会报错**，两侧单独看都正常。

## 判据

扫 `{{AIDP_HOME}}/{commands,flows,rules,reference}/**` 与 `AIDP-AGENTS.md`，命中
`git config user.name` / `git config --get user.name` 即 ERROR。

**豁免**（下列位置写它是正确的，不是解析 `{user}`）：
  · `chrome-<git_user>` 的 **MCP 服务名**：那是「每台机器一个 chrome 实例」的命名约定，
    要求的是**本机 git 身份**本身，与 `{user}` 目录槽无关；换身份等于换机器，本就该不同。
  · `check_cascade_obligation.py` 之类的**脚本内部兜底**（不是契约正文）。
  · 本文件自身（含阳性正则与自检探针）。
  · 行内带 `identity-ignore:` 注释的（须写明为什么这里必须用 Git 身份）。

⛔ 别把豁免写宽：豁免一宽，本门就退化成「永绿」，而永绿等于没有。
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
SCAN_DIRS = ("commands", "flows", "rules", "reference")
SCAN_FILES = ("AIDP-AGENTS.md",)
TEXT_SUFFIXES = {".md", ".py", ".sh", ".js", ".json", ".yaml", ".yml", ".tpl"}

PATTERN = re.compile(r"git\s+(?:-c\s+\S+\s+)?config\s+(?:--\w+\s+)*user\.name"
                     r"|git\s+config\s+--get\s+user\.name")
# 「别自己拼 `git config user.name`」这类**反向教导**不是解析点：它恰恰在劝人别这么写。
# 不排除它会让每条修正说明都变成新 ERROR —— 修一处、报一处，最后只能靠豁免把门关掉。
NEGATION_RE = re.compile(r"[⛔🚫]\s*别|不要|禁止|不得|切勿|别自己|不再各自|⛔")
# `chrome-<git_user>` 服务名的既定命名：`GIT_USER=$(git config user.name)`。
# 它要的是**本机 Git 身份本身**（换机器就该换实例），与 `memory/{version}/{user}/` 路径槽无关。
# ⛔ 但它**不得**被拿去拼 memory 路径 —— 那正是本门要拦的第二种漂移。
MCP_IDENTITY_ASSIGN = re.compile(r"^\s*GIT_USER\s*=\s*\$\(\s*git\s+config\s+user\.name")
# MCP 服务名：`chrome-$(git config user.name)` / `chrome-<git_user>` 一类。同一行出现
# `chrome` 且该行是在讲 server 名 / .mcp.json 时，这才是它的正确用法。
MCP_SERVER_LINE = re.compile(r"chrome[-_<]|\.mcp\.json|mcp\s+add|mcpServers", re.I)
IGNORE_RE = re.compile(r"identity-ignore:\s*\S")
MAX_BYTES = 2 * 1024 * 1024


def _iter_targets(root: Path):
    aidp = root / RUNTIME_REL
    for name in SCAN_FILES:
        p = aidp / name
        if p.is_file():
            yield p
    for sub in SCAN_DIRS:
        base = aidp / sub
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if p.is_file() and not p.is_symlink() and p.suffix.lower() in TEXT_SUFFIXES:
                try:
                    if p.stat().st_size <= MAX_BYTES:
                        yield p
                except OSError:
                    continue


def scan(root: Path) -> list[dict]:
    findings = []
    aidp = root / RUNTIME_REL
    for path in _iter_targets(root):
        try:
            rel = path.relative_to(aidp).as_posix()
        except ValueError:
            rel = path.relative_to(root).as_posix()
        if rel.endswith("check_identity_source.py"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if not PATTERN.search(line) or IGNORE_RE.search(line):
                continue
            if NEGATION_RE.search(line):
                continue          # 反向教导：本行在劝人别这么写
            if MCP_SERVER_LINE.search(line) or MCP_IDENTITY_ASSIGN.search(line):
                continue          # `chrome-<git_user>` 服务名，见模块文档
            findings.append({
                "kind": "identity-split", "path": rel, "line": lineno,
                "value": PATTERN.search(line).group(0),
                "hint": "改用 `python3 " + "{{AIDP_HOME}}" + "/scripts/vcs.py user`"
                        "（唯一解析实现）；确需 Git 身份本身时加 `identity-ignore:` 说明理由",
            })
    return findings


def self_check() -> bool:
    root = Path(tempfile.mkdtemp(prefix="aidp-identity-check-"))
    try:
        base = root / RUNTIME_REL / "commands"
        base.mkdir(parents=True)
        # 阳性：命令正文自己解析身份
        (base / "bad.md").write_text(
            "2. **{user}** ← `git config user.name`\n"
            'APPLIED="memory/$V/$(git config user.name)/x.json"\n',
            encoding="utf-8")
        # 阴性：正确写法 + MCP 服务名 + 显式豁免
        (base / "good.md").write_text(
            "2. **{user}** ← `python3 {{AIDP_HOME}}/scripts/vcs.py user`\n"
            'claude mcp add "chrome-$(git config user.name)" --scope project chrome-devtools-mcp\n'
            "本行必须取 Git 身份：`git config user.name` <!-- identity-ignore: 服务名约定 -->\n",
            encoding="utf-8")
        found = scan(root)
        bad = [x for x in found if x["path"].endswith("bad.md")]
        good = [x for x in found if x["path"].endswith("good.md")]
        return len(bad) == 2 and not good
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="`{user}` 解析单一信源门")
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
    findings = scan(root)
    if args.json:
        print(json.dumps({"ok": not findings, "findings": findings}, ensure_ascii=False, indent=2))
    elif findings:
        for item in findings:
            print(f"[ERROR] {item['kind']} {item['path']}:{item['line']} {item['value']}")
            print(f"        → {item['hint']}")
    else:
        print("[OK] {user} 解析单一信源通过")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
