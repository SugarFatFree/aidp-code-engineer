#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_cli_invocation.py — 文档里 `python3 <脚本>.py <子命令> --flag` 必须属于**那个脚本**（ERROR 级）。

## 为什么需要本脚本

`check_ghost_flags.py` 只查「某个 flag 在全仓有没有定义」，查不到「它是不是这个脚本的 flag」：
文档写 `agent_env.py sync`，而 `sync` 是 `agent_sync.py` 的职责；写 `commit_gate.py --no-track`，
而该参数早已不存在——全仓别处恰好有同名 flag，全局检查就放过了。执行体照抄命令时才撞上 argparse 报错，
在无人值守链路里这就是一次整 tick 的失败。

## 判据

扫描 `.md` 里的 `python3 <路径>.py …` 调用（代码块与行内代码都算，行尾 `\\` 续行会拼接）：

1. **脚本定位**：路径含占位（`<SKILL_DIR>`、`$VAR`、`{skill}`）时按文件名找；同名多份时，优先取与文档同属
   一个 SKILL 目录的那份，否则取并集。`AIDP_HOME/` 下写死的路径找不到 → ERROR `missing-script`。
2. **flag**：每个 `--flag`（去掉 `=值`）必须是目标脚本（及其同目录被 import 的模块）源码里的字符串常量，
   或能被 argparse 缩写匹配到唯一一个 → 否则 ERROR `unknown-flag`。
3. **子命令**：目标脚本有 `add_subparsers` 时，紧跟脚本路径的第一个非 flag 词必须是某个 `add_parser` 名；
   首个位置参数声明了 `choices` 时，必须落在 choices 内 → 否则 ERROR `unknown-subcommand`。
4. 目标脚本既不含 `argparse` 也不读 `sys.argv` 却被传了 flag → WARN `non-argparse`。

占位值（含 `<` `{` `$` `…`）不参与判定；遇到 `|` `&&` `;` `>` `#`、反引号或中文即视为命令结束。

## 豁免

行内写 `cli-check: ignore <原因>` 即豁免该行。

## 用法

    python3 AIDP_HOME/scripts/check_cli_invocation.py
    python3 AIDP_HOME/scripts/check_cli_invocation.py --json
    python3 AIDP_HOME/scripts/check_cli_invocation.py --self-check

退出码：0 = 无 ERROR（WARN 不影响）；1 = 有 ERROR；2 = 用法 / 读取错误。
"""
import sys as _aidp_sys
from pathlib import Path as _AidpPath
_aidp_scripts = str(_AidpPath(__file__).resolve().parent)
if _aidp_scripts not in _aidp_sys.path:
    _aidp_sys.path.insert(0, _aidp_scripts)
from aidp_runtime import runtime_text
import argparse
import ast
import json
import os
import re
import shlex
import sys

EXCLUDE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "assets", "dist", "build"}
EXCLUDE_DIR_PREFIXES = (".aidp-backup",)
IGNORE_RE = re.compile(r"cli-check:\s*ignore\s*\S")
INVOKE_RE = re.compile(r"(?<![\w-])python3?\s+(?:-u\s+)?([^\s`'\"|;&()]+\.py)\b([^`\n]*)")
STOP_TOKENS = {"|", "||", "&&", ";", ">", ">>", "<", "2>&1", "&", ")", "then", "do"}
CJK_RE = re.compile("[\u3000-\u9fff\uff00-\uffef]")
PLACEHOLDER_RE = re.compile(r"[<>{}$…]|\.\.\.")
SKILL_DIR_RE = re.compile(runtime_text('\\__AIDP_HOME__/skills/([^/]+)/', __file__))


def _walk(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDE_DIRS
                             and not d.startswith(EXCLUDE_DIR_PREFIXES))
        for fn in sorted(filenames):
            yield os.path.join(dirpath, fn)


class ScriptInfo:
    def __init__(self, paths):
        self.paths = paths
        self.consts = set()
        self.subcommands = set()
        self.has_subparsers = False
        self.first_choices = None
        self.argparse = False
        for p in paths:
            self._load(p, top=True)

    def _load(self, path, top):
        try:
            src = open(path, encoding="utf-8").read()
            tree = ast.parse(src)
        except (SyntaxError, UnicodeDecodeError, OSError):
            return
        if "argparse" in src or "sys.argv" in src:
            self.argparse = True
        first_positional_seen = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                self.consts.add(node.value)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                name = node.func.attr
                if name == "add_subparsers" and top:
                    self.has_subparsers = True
                elif name == "add_parser" and top and node.args and isinstance(node.args[0], ast.Constant):
                    self.subcommands.add(node.args[0].value)
                    for kw in node.keywords:
                        if kw.arg == "aliases" and isinstance(kw.value, (ast.List, ast.Tuple)):
                            for e in kw.value.elts:
                                if isinstance(e, ast.Constant):
                                    self.subcommands.add(e.value)
                elif (name == "add_argument" and top and not first_positional_seen and node.args
                      and isinstance(node.args[0], ast.Constant)
                      and isinstance(node.args[0].value, str)
                      and not node.args[0].value.startswith("-")):
                    first_positional_seen = True
                    for kw in node.keywords:
                        if kw.arg == "choices" and isinstance(kw.value, (ast.List, ast.Tuple, ast.Set)):
                            vals = [e.value for e in kw.value.elts if isinstance(e, ast.Constant)]
                            if vals:
                                self.first_choices = set(vals)
        if top:
            d = os.path.dirname(path)
            for node in ast.walk(tree):
                mods = []
                if isinstance(node, ast.Import):
                    mods = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    mods = [node.module]
                for m in mods:
                    mp = os.path.join(d, m.split(".")[0] + ".py")
                    if os.path.isfile(mp) and mp not in self.paths:
                        self._load(mp, top=False)

    def flag_known(self, flag):
        if flag in self.consts:
            return True
        cands = [c for c in self.consts if c.startswith(flag) and c.startswith("--")]
        return len(cands) == 1


def _tokens(rest):
    rest = rest.split(" #", 1)[0]
    try:
        toks = shlex.split(rest, posix=True)
    except ValueError:
        toks = rest.split()
    out = []
    for t in toks:
        # 用法摘要里的可选写法 `[--flag X]` / `[--a|--b]`：去掉方括号后照常判定
        t = t.strip("[]")
        if not t:
            continue
        if t.startswith("--") and ("|" in t or "/--" in t):
            # `--a|--b` / `--a/--b` 并列写法：逐个判定
            parts = [x for x in re.split(r"[|/]", t) if x.startswith("--")]
            out.extend(parts[:-1])
            t = parts[-1]
        if CJK_RE.search(t) and out and out[-1].startswith("--") and not t.startswith("-"):
            out.append("<value>")   # 中文取值（如 `--data 结果.json`）：当作值，继续往后判
            continue
        if t in STOP_TOKENS or t.startswith(("#", ">", "2>", "|", "&")) or CJK_RE.search(t):
            break
        if t.endswith((";", ")", "|", ')"', ")'")):
            out.append(t.rstrip(";)|\"'"))
            break
        out.append(t)
    return out


def run(root, paths=None):
    index = {}
    for p in _walk(root):
        if p.endswith(".py"):
            index.setdefault(os.path.basename(p), []).append(p)
    cache = {}
    errors, warns, scanned, calls = [], [], 0, 0
    bases = [os.path.join(root, p) for p in paths] if paths else [root]
    for base in bases:
        files = [base] if os.path.isfile(base) else list(_walk(base))
        for f in files:
            if not f.endswith(".md"):
                continue
            try:
                raw = open(f, encoding="utf-8").read().splitlines()
            except (UnicodeDecodeError, OSError):
                continue
            scanned += 1
            rel = os.path.relpath(f, root)
            doc_skill = SKILL_DIR_RE.search(rel.replace(os.sep, "/") + "/")
            i = 0
            while i < len(raw):
                no, line = i + 1, raw[i]
                while line.rstrip().endswith("\\") and i + 1 < len(raw):
                    i += 1
                    line = line.rstrip()[:-1] + " " + raw[i].strip()
                i += 1
                if "python" not in line or IGNORE_RE.search(line):
                    continue
                for m in INVOKE_RE.finditer(line):
                    spath, rest = m.group(1), m.group(2)
                    bname = os.path.basename(spath)
                    if PLACEHOLDER_RE.search(bname):
                        continue
                    concrete = not PLACEHOLDER_RE.search(spath)
                    cands = []
                    if concrete and os.path.isfile(os.path.join(root, spath)):
                        cands = [os.path.join(root, spath)]
                    else:
                        allc = index.get(bname, [])
                        if doc_skill:
                            same = [c for c in allc
                                    if "/skills/%s/" % doc_skill.group(1) in c.replace(os.sep, "/")]
                            cands = same or allc
                        else:
                            cands = allc
                    if not cands:
                        if concrete and spath.startswith(runtime_text('__AIDP_HOME__/', __file__)):
                            errors.append({"file": rel, "line": no, "script": spath,
                                           "kind": "missing-script", "token": spath})
                        continue
                    calls += 1
                    key = tuple(sorted(cands))
                    if key not in cache:
                        cache[key] = ScriptInfo(list(key))
                    info = cache[key]
                    toks = _tokens(rest)
                    flags = [t.split("=", 1)[0] for t in toks if t.startswith("--") and len(t) > 2]
                    if flags and not info.argparse:
                        warns.append({"file": rel, "line": no, "script": bname,
                                      "kind": "non-argparse", "token": flags[0]})
                        continue
                    for fl in flags:
                        if PLACEHOLDER_RE.search(fl):
                            continue
                        if not info.flag_known(fl):
                            errors.append({"file": rel, "line": no, "script": bname,
                                           "kind": "unknown-flag", "token": fl})
                    if toks and not toks[0].startswith("-") and not PLACEHOLDER_RE.search(toks[0]) \
                            and re.match(r"^[a-z][a-z0-9_-]*$", toks[0]):
                        sub = toks[0]
                        if info.has_subparsers and info.subcommands and sub not in info.subcommands:
                            errors.append({"file": rel, "line": no, "script": bname,
                                           "kind": "unknown-subcommand", "token": sub})
                        elif not info.has_subparsers and info.first_choices is not None \
                                and sub not in info.first_choices:
                            errors.append({"file": rel, "line": no, "script": bname,
                                           "kind": "unknown-subcommand", "token": sub})
    return {"ok": not errors, "scanned": scanned, "calls": calls, "errors": errors, "warns": warns}


def main():
    ap = argparse.ArgumentParser(description="文档中脚本调用的子命令 / flag 归属检查")
    ap.add_argument("--root", default=".", help="仓库根目录（默认当前目录）")
    ap.add_argument("--path", action="append", default=None, help="只扫指定相对路径（可重复）")
    ap.add_argument("--json", action="store_true", help="机读 JSON")
    ap.add_argument("--self-check", action="store_true",
                    help="阳性对照自检（骨架与探针登记表见 selfcheck.py）")
    args = ap.parse_args()
    if args.self_check:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from selfcheck import run_self_check
        sys.exit(run_self_check(os.path.basename(__file__), json_out=args.json))
    try:
        res = run(args.root, args.path)
    except Exception as e:  # noqa: BLE001
        print("[ERROR] 检查执行失败：%s" % e, file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        if res["ok"]:
            print("[OK] %d 处脚本调用的子命令 / flag 均属于目标脚本（巡检 %d 份 .md）"
                  % (res["calls"], res["scanned"]))
        else:
            print("[FAIL] %d 处不属于目标脚本的子命令 / flag（共 %d 处调用）：" % (len(res["errors"]), res["calls"]))
            for e in res["errors"]:
                print("  · %s:%d  %s %s  [%s]" % (e["file"], e["line"], e["script"], e["token"], e["kind"]))
        for w in res["warns"]:
            print("  [WARN] %s:%d  %s 不是 argparse 脚本却被传了 %s" % (w["file"], w["line"], w["script"], w["token"]))
        if not res["ok"]:
            print("  修复：按目标脚本 `--help` 改正调用；确属示例的行内加 `cli-check: ignore <原因>`")
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
