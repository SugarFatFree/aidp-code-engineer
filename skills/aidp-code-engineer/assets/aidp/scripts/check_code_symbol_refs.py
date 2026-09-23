#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_code_symbol_refs.py — 文档里 `脚本.py::符号` 引用的存在性（ERROR 级）。

## 为什么需要本脚本

契约文档大量用 `scaffold_lib.py::skeleton_dirs`、`verify.py::check_contract_drift` 这种写法把
「单一信源」指到具体函数。函数一改名、一挪文件，这些指针就全部悬空——而读者照着去找，
找不到时往往会按字面「补一个」，于是同一职责出现两份实现。链接 / 锚点检查只认 Markdown 链接，
查不到反引号里的符号。

## 判据

扫描 `.md` / `.py` / `.sh` / `.js` / `.json` / `.yaml` 里形如 `name.py::symbol`（也认 `.sh` / `.js`）的引用：

1. **文件**：按文件名在仓库里找（排除脚手架 bundle `assets/` 与缓存目录）；同名多份时取并集。
   找不到文件 → ERROR `missing-file`。
2. **符号**：取 `::` 后第一段标识符（`A.b` 取 `A`，再校验 `b` 存在于该文件）：
   - `.py`：模块级 `def` / `class` / 赋值目标，或类内方法（AST 解析）；另认字典字面量里的字符串键
     （如 `GUARDS` 表的检查名）。
   - `.sh` / `.js`：`name()` / `function name` / `const|let|var name`。
   找不到 → ERROR `missing-symbol`。
3. 占位写法（含 `<` `{` `*` `x.py` `xxx.py` `foo.py`）不校验。

## 豁免

行内写 `symbol-ref-ignore: <原因>` 即豁免该行。

## 用法

    python3 AIDP_HOME/scripts/check_code_symbol_refs.py
    python3 AIDP_HOME/scripts/check_code_symbol_refs.py --json
    python3 AIDP_HOME/scripts/check_code_symbol_refs.py --self-check

退出码：0 = 全部可解析；1 = 有悬空引用；2 = 用法 / 读取错误。
"""
import argparse
import ast
import json
import os
import re
import sys

EXCLUDE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "assets", "dist", "build"}
EXCLUDE_DIR_PREFIXES = (".aidp-backup",)
SCAN_EXT = {".md", ".py", ".sh", ".js", ".json", ".yaml", ".yml", ".txt"}
CODE_EXT = {".py", ".sh", ".js"}

REF_RE = re.compile(r"(?<![\w/<{*-])([A-Za-z0-9_][A-Za-z0-9_.-]*\.(?:py|sh|js))::([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?)")
PLACEHOLDER_FILES = {"name.py", "x.py", "xxx.py", "foo.py", "bar.py", "some.py", "script.py", "a.py", "b.py"}
IGNORE_RE = re.compile(r"symbol-ref-ignore:\s*\S")


def _walk(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDE_DIRS
                             and not d.startswith(EXCLUDE_DIR_PREFIXES))
        for fn in sorted(filenames):
            yield dirpath, fn


def index_code_files(root):
    idx = {}
    for dirpath, fn in _walk(root):
        if os.path.splitext(fn)[1] in CODE_EXT:
            idx.setdefault(fn, []).append(os.path.join(dirpath, fn))
    return idx


def py_symbols(path):
    """返回 (顶层名集合, 全部名集合含方法与字典字符串键)。"""
    try:
        src = open(path, encoding="utf-8").read()
        tree = ast.parse(src)
    except (SyntaxError, UnicodeDecodeError, OSError):
        return set(), set()
    top, every = set(), set()

    def _targets(t):
        if isinstance(t, ast.Name):
            yield t.id
        elif isinstance(t, (ast.Tuple, ast.List)):
            for e in t.elts:
                yield from _targets(e)

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            top.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                top.update(_targets(t))
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            top.update(_targets(node.target))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            every.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                every.update(_targets(t))
        elif isinstance(node, ast.Dict):
            for k in node.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    every.add(k.value)
        elif isinstance(node, (ast.Tuple, ast.List)):
            # 登记表形如 GUARDS = [("check_x", fn), ...]：元组首元素的字符串也算可引用名
            if node.elts and isinstance(node.elts[0], ast.Constant) and isinstance(node.elts[0].value, str):
                every.add(node.elts[0].value)
    every |= top
    return top, every


def text_symbols(path):
    try:
        src = open(path, encoding="utf-8").read()
    except (UnicodeDecodeError, OSError):
        return set()
    names = set(re.findall(r"^\s*(?:function\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*\)\s*\{", src, re.M))
    names |= set(re.findall(r"\bfunction\s+([A-Za-z_][A-Za-z0-9_]*)", src))
    names |= set(re.findall(r"\b(?:const|let|var|class)\s+([A-Za-z_][A-Za-z0-9_]*)", src))
    names |= set(re.findall(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", src, re.M))
    return names


_CACHE = {}


def symbols_of(path):
    if path not in _CACHE:
        if path.endswith(".py"):
            _CACHE[path] = py_symbols(path)
        else:
            s = text_symbols(path)
            _CACHE[path] = (s, s)
    return _CACHE[path]


def run(root, paths=None):
    idx = index_code_files(root)
    errors, scanned, refs = [], 0, 0
    bases = [os.path.join(root, p) for p in paths] if paths else [root]
    for base in bases:
        items = [(os.path.dirname(base), os.path.basename(base))] if os.path.isfile(base) else _walk(base)
        for dirpath, fn in items:
            if os.path.splitext(fn)[1] not in SCAN_EXT:
                continue
            p = os.path.join(dirpath, fn)
            try:
                lines = open(p, encoding="utf-8").read().splitlines()
            except (UnicodeDecodeError, OSError):
                continue
            scanned += 1
            rel = os.path.relpath(p, root)
            for no, line in enumerate(lines, 1):
                if "::" not in line or IGNORE_RE.search(line):
                    continue
                for m in REF_RE.finditer(line):
                    fname, sym = m.group(1), m.group(2)
                    base_name = os.path.basename(fname)
                    if base_name in PLACEHOLDER_FILES:
                        continue
                    refs += 1
                    targets = idx.get(base_name)
                    if not targets:
                        errors.append({"file": rel, "line": no, "ref": m.group(0),
                                       "kind": "missing-file"})
                        continue
                    head, _, tail = sym.partition(".")
                    found = False
                    for t in targets:
                        top, every = symbols_of(t)
                        if head in top or head in every:
                            if not tail or tail in every:
                                found = True
                                break
                    if not found:
                        errors.append({"file": rel, "line": no, "ref": m.group(0),
                                       "kind": "missing-symbol"})
    return {"ok": not errors, "scanned": scanned, "refs": refs, "errors": errors}


def main():
    ap = argparse.ArgumentParser(description="文档中 `脚本::符号` 引用存在性检查")
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
    elif res["ok"]:
        print("[OK] %d 处 `脚本::符号` 引用全部可解析（巡检 %d 份）" % (res["refs"], res["scanned"]))
    else:
        print("[FAIL] %d 处悬空引用（共 %d 处，巡检 %d 份）：" % (len(res["errors"]), res["refs"], res["scanned"]))
        for e in res["errors"]:
            print("  · %s:%d  %s  [%s]" % (e["file"], e["line"], e["ref"], e["kind"]))
        print("  修复：改成真实的文件与函数名；确属占位写法的，行内加 `symbol-ref-ignore: <原因>`")
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
