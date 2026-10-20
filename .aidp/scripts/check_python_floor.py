#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""脚本最低 Python 版本门 —— 声明支持的最低版本上必须真的能导入。

## 为什么需要这道门

`README.md` 与脚手架 `SKILL.md` 声明「Python ≥ 3.9」，但代码里用 `X | None` 这类
**PEP 604 联合类型**时，3.9 会在**函数定义求值时**抛
`TypeError: unsupported operand type(s) for |` —— 不是在使用时，而是 import 那一刻。

失败面全在「离开发者很远」的地方：

  · `agent_sync.py` 由脚手架在 init / migrate / upgrade **末尾**以子进程调用 → 新用户第一次
    初始化就崩，而维护者的 3.12 上永远复现不了；
  · `autopilot_tick_flags.py` 在 7×24 每个 tick 上调用 → 无人值守链路整条起不来。

CI 只跑一个 Python 版本时，这类缺陷**结构上不可见**。所以判据不能是「跑一次测试」，
而是「静态断言：没有 future 导入的文件不得出现运行期求值的新语法」。

## 判据

对 `{{AIDP_HOME}}/scripts/**/*.py` 与 `skills/aidp-code-engineer/scripts/**/*.py`：

  · 文件**不含** `from __future__ import annotations` 时，禁止在**注解**里出现 `X | Y`
    （含函数参数、返回、变量注解）；
  · 文件**不含** `match` 说明（`ast.Match` 属 3.10+）时同理禁止 `match` 语句。

含 future 导入的文件不受 PEP 604 限制：注解变成字符串、不求值，3.9 可正常导入。
"""
from __future__ import annotations

import argparse
import ast
import json
import shutil
import sys
import tempfile
from pathlib import Path

_scripts = str(Path(__file__).resolve().parent)
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)
from aidp_runtime import runtime_relpath

HAS_FUTURE = "from __future__ import annotations"
SCAN_ROOTS = (runtime_relpath("scripts", __file__), "skills/aidp-code-engineer/scripts")
SKIP_PARTS = {"tests", "__pycache__"}


def _has_pep604_annotation(tree: ast.AST) -> list[tuple[int, str]]:
    hits = []
    for node in ast.walk(tree):
        anns = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = list(node.args.posonlyargs) + list(node.args.args) + list(node.args.kwonlyargs)
            for extra in (node.args.vararg, node.args.kwarg):
                if extra is not None:
                    args.append(extra)
            anns.extend(a.annotation for a in args if a.annotation is not None)
            if node.returns is not None:
                anns.append(node.returns)
        elif isinstance(node, ast.AnnAssign) and node.annotation is not None:
            anns.append(node.annotation)
        for ann in anns:
            for sub in ast.walk(ann):
                if isinstance(sub, ast.BinOp) and isinstance(sub.op, ast.BitOr):
                    hits.append((getattr(node, "lineno", 0), ast.unparse(ann)[:60]))
                    break
    return hits


def scan_file(path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return [{"path": str(path), "line": exc.lineno or 0,
                 "reason": f"语法错，无法校验最低版本：{exc.msg}"}]
    findings = []
    if HAS_FUTURE not in text:
        # 同一文件里多个签名都用 PEP 604 时报一条即可：这是**一个**「文件缺 future 导入」
        # 的缺陷，按注解条数报会让输出重心跑偏到「有多少个函数」上。
        hits = _has_pep604_annotation(tree)
        if hits:
            lineno, what = hits[0]
            more = f"（另 {len(hits) - 1} 处）" if len(hits) > 1 else ""
            findings.append({
                "path": str(path), "line": lineno,
                "reason": f"注解 `{what}`{more} 用了 PEP 604 联合类型，而本文件没有 "
                          f"`from __future__ import annotations`；"
                          f"声明的 Python 3.9 上 import 即 TypeError",
            })
    if any(isinstance(n, ast.Match) for n in ast.walk(tree)):
        findings.append({"path": str(path), "line": 0,
                         "reason": "使用了 `match` 语句（Python 3.10+），"
                                   "与声明的最低版本 3.9 不符"})
    return findings


def scan(root: Path) -> list[dict]:
    findings = []
    for rel_root in SCAN_ROOTS:
        base = root / rel_root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if any(p in SKIP_PARTS for p in path.parts):
                continue
            for item in scan_file(path):
                try:
                    item["path"] = path.relative_to(root).as_posix()
                except ValueError:
                    pass
                findings.append(item)
    return findings


def self_check() -> bool:
    root = Path(tempfile.mkdtemp(prefix="aidp-pyver-"))
    try:
        d = root / SCAN_ROOTS[0]
        d.mkdir(parents=True)
        (d / "bad.py").write_text(
            "def f(x: int | None = None) -> str | None:\n    return None\n", encoding="utf-8")
        (d / "good_future.py").write_text(
            "from __future__ import annotations\n\n"
            "def f(x: int | None = None) -> str | None:\n    return None\n", encoding="utf-8")
        (d / "good_optional.py").write_text(
            "from typing import Optional\n\n"
            "def f(x: Optional[int] = None) -> Optional[str]:\n    return None\n",
            encoding="utf-8")
        found = scan(root)
        names = sorted(Path(x["path"]).name for x in found)
        return names == ["bad.py"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="脚本最低 Python 版本门")
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
            print(f"[ERROR] python-floor {item['path']}:{item['line']} — {item['reason']}")
    else:
        print("[OK] 脚本最低 Python 版本契约通过")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
