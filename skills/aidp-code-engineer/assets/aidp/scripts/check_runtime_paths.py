#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查下发运行契约是否仍硬编码旧运行根或遗留未渲染运行根。"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from pathlib import Path

_scripts = str(Path(__file__).resolve().parent)
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)
from aidp_runtime import runtime_relpath

RUNTIME_DIRS = (
    "agents", "commands", "flows", "hooks", "plugins", "reference",
    "rules", "scripts", "skills", "templates",
)
EXCLUDED_PREFIXES = (
    "scripts/tests/", "skills/aidp-code-engineer/", "memory/",
)
EXCLUDED_FILES = {
    "scripts/design-goals-baseline.txt",
    "scripts/check_runtime_paths.py",  # 检查器自身包含阳性正则与自检探针
    "scripts/aidp_runtime.py",         # 运行根展开器定义内部 token
}
TEXT_SUFFIXES = {
    "", ".md", ".py", ".sh", ".js", ".ts", ".json", ".jsonl",
    ".yaml", ".yml", ".txt", ".tpl", ".html", ".css", ".toml",
    ".cfg", ".ini", ".sql", ".vue", ".xml", ".env",
}
LEGACY_AIDP_DIR = ".aidp"
OLD_RUNTIME_RE = re.compile(
    r"(?<!memory/)(?<![\w{])" + re.escape(LEGACY_AIDP_DIR) + r"/"
)
TOKEN = "{{" + "AIDP_HOME" + "}}"
# 本地运行态目录是 `memory/.aidp/`，**不随运行根变**。把运行根拼进 memory 下
# （`memory/各 Agent 的运行根/`、`memory/.claude/`、历史的 `memory/.claude/aidp/`）都是同一类错。  # runtime-path-ignore: 指 Agent 自身目录这一概念，非运行契约路径，两包均保持原样
STATE_HOME_RE = re.compile(
    r"memory/(?:\{\{AIDP_HOME\}\}|\.(?:claude|agents)(?:/aidp)?)/")
RUNTIME_REL = runtime_relpath("", __file__)
IGNORE_RE = re.compile(r"runtime-path-ignore:\s*\S")
MAX_BYTES = 2 * 1024 * 1024
LEGACY_MODULES = {RUNTIME_REL.rstrip("/") + "/scripts/agent_sync.py"}
LEGACY_FUNCTION_PREFIXES = ("cleanup_", "_cleanup_", "prune_legacy", "_prune_legacy")


def _is_excluded(rel: str) -> bool:
    return rel in EXCLUDED_FILES or any(rel.startswith(prefix) for prefix in EXCLUDED_PREFIXES)


def iter_contract_files(root: Path, selected: list[str] | None = None):
    aidp = root / RUNTIME_REL
    if selected:
        starts = [root / item for item in selected]
    else:
        starts = [aidp / item for item in RUNTIME_DIRS] + [aidp / "AIDP-AGENTS.md"]
    seen = set()
    for start in starts:
        if not start.exists() or start.is_symlink():
            continue
        paths = [start] if start.is_file() else start.rglob("*")
        for path in paths:
            if not path.is_file() or path.is_symlink() or path in seen:
                continue
            seen.add(path)
            try:
                aidp_rel = path.relative_to(aidp).as_posix()
            except ValueError:
                aidp_rel = path.relative_to(root).as_posix()
            if _is_excluded(aidp_rel) or path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            try:
                if path.stat().st_size > MAX_BYTES:
                    continue
            except OSError:
                continue
            yield path


def _legacy_assignment(node: ast.Constant, parents: dict) -> bool:
    parent = parents.get(node)
    if not isinstance(parent, ast.Assign) or parent.value is not node:
        return False
    return any(isinstance(target, ast.Name) and target.id == "LEGACY_AIDP_DIR"
               for target in parent.targets)


def _assignment_names(node: ast.AST, parents: dict) -> set[str]:
    current = node
    while current in parents:
        current = parents[current]
        if isinstance(current, ast.Assign):
            return {target.id for target in current.targets if isinstance(target, ast.Name)}
        if isinstance(current, (ast.Expr, ast.Return, ast.FunctionDef, ast.Module)):
            break
    return set()


def _memory_state_construction(node: ast.Constant, parents: dict) -> bool:
    current = parents.get(node)
    while current is not None and not isinstance(current, (ast.Assign, ast.Expr, ast.Return)):
        if isinstance(current, ast.Call):
            literals = {arg.value for arg in current.args
                        if isinstance(arg, ast.Constant) and isinstance(arg.value, str)}
            if "memory" in literals:
                return True
        current = parents.get(current)
    return "LOCK_DIRNAME" in _assignment_names(node, parents)


def _path_construction(node: ast.Constant, parents: dict) -> bool:
    if _memory_state_construction(node, parents):
        return False
    parent = parents.get(node)
    if isinstance(parent, ast.BinOp) and isinstance(parent.op, (ast.Div, ast.Add)):
        return True
    if isinstance(parent, ast.Call):
        func = parent.func
        if isinstance(func, ast.Name) and func.id in {"Path", "PurePath"}:
            return True
        if isinstance(func, ast.Attribute) and func.attr == "join":
            return True
    return False


def _wrapped_by_runtime_text(node: ast.AST, parents: dict) -> bool:
    current = node
    while current in parents:
        current = parents[current]
        if isinstance(current, ast.Call):
            func = current.func
            if isinstance(func, ast.Name) and func.id in {"runtime_text", "_runtime_text"}:
                return True
    return False


def _enclosing_function(node: ast.AST, parents: dict) -> str:
    current = node
    while current in parents:
        current = parents[current]
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return current.name
    return ""


def _assigned_legacy_names(tree: ast.AST) -> dict[str, ast.Constant]:
    result = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Constant) \
                or node.value.value != LEGACY_AIDP_DIR:
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                result[target.id] = node.value
    return result


def _scan_python_constructions(path: Path, root: Path) -> list[dict]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, SyntaxError):
        return []
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    findings = []
    rel = path.relative_to(root).as_posix()
    legacy_names = _assigned_legacy_names(tree)
    for name, value_node in legacy_names.items():
        if name != "LEGACY_AIDP_DIR":
            findings.append({
                "kind": "hardcoded-runtime-root-variable", "path": rel,
                "line": value_node.lineno, "value": name,
            })
        elif rel not in LEGACY_MODULES:
            findings.append({
                "kind": "legacy-runtime-root-outside-migration", "path": rel,
                "line": value_node.lineno, "value": name,
            })
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) \
                and node.id == "LEGACY_AIDP_DIR":
            parent = parents.get(node)
            in_path = (isinstance(parent, ast.BinOp) and isinstance(parent.op, (ast.Div, ast.Add))) \
                or (isinstance(parent, ast.Call) and isinstance(parent.func, ast.Attribute)
                    and parent.func.attr == "join")
            fn = _enclosing_function(node, parents)
            if in_path and not fn.startswith(LEGACY_FUNCTION_PREFIXES):
                findings.append({
                    "kind": "legacy-runtime-root-used-by-runtime", "path": rel,
                    "line": node.lineno, "value": fn or "<module>",
                })
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if node.value == LEGACY_AIDP_DIR:
            if _legacy_assignment(node, parents):
                continue
            if _path_construction(node, parents):
                findings.append({
                    "kind": "hardcoded-runtime-construction", "path": rel,
                    "line": node.lineno, "value": LEGACY_AIDP_DIR,
                })
        if ("__AIDP_HOME__" in node.value or "$AIDP_HOME" in node.value) \
                and not _wrapped_by_runtime_text(node, parents):
            findings.append({
                "kind": "unexpanded-runtime-output", "path": rel,
                "line": node.lineno, "value": "runtime-home-token",
            })
    return findings


def scan(root: Path, selected: list[str] | None = None, rendered: bool = False) -> list[dict]:
    findings = []
    state_root = root / RUNTIME_REL / "memory" / ".aidp"
    if os.path.lexists(str(state_root)):
        findings.append({
            "kind": "runtime-state-in-source",
            "path": state_root.relative_to(root).as_posix(),
            "line": 1,
            "value": "memory/.aidp",
        })
    for path in iter_contract_files(root, selected):
        if path.suffix.lower() == ".py":
            findings.extend(_scan_python_constructions(path, root))
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            rel = path.relative_to(root).as_posix()
            state_home = STATE_HOME_RE.search(line)
            if state_home:
                findings.append({
                    "kind": "runtime-state-home-confusion", "path": rel,
                    "line": lineno, "value": state_home.group(0),
                })
            old_hits = list(OLD_RUNTIME_RE.finditer(line))
            if old_hits:
                findings.append({
                    "kind": "hardcoded-runtime-path", "path": rel,
                    "line": lineno, "value": old_hits[0].group(0),
                })
            if rendered and TOKEN in line:
                findings.append({
                    "kind": "unresolved-runtime-home", "path": rel,
                    "line": lineno, "value": TOKEN,
                })
            # 豁免只用于其它路径示例；不能盖掉上述两个硬错误。
            if IGNORE_RE.search(line):
                continue
    return findings


def self_check() -> bool:
    import tempfile
    import shutil
    root = Path(tempfile.mkdtemp(prefix="aidp-runtime-path-check-"))
    try:
        p = root / LEGACY_AIDP_DIR / "commands/probe.md"
        p.parent.mkdir(parents=True)
        p.write_text(
            "python3 " + LEGACY_AIDP_DIR + "/scripts/x.py # runtime-path-ignore: 不能豁免硬错误\n"
            "python3 " + TOKEN + "/scripts/x.py\n",
            encoding="utf-8",
        )
        source = scan(root)
        rendered = scan(root, rendered=True)
        return ([x["kind"] for x in source] == ["hardcoded-runtime-path"]
                and sorted(x["kind"] for x in rendered)
                == ["hardcoded-runtime-path", "unresolved-runtime-home"])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--path", action="append", default=[])
    ap.add_argument("--rendered", action="store_true")
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
    findings = scan(root, args.path or None, args.rendered)
    if args.json:
        print(json.dumps({"ok": not findings, "findings": findings}, ensure_ascii=False, indent=2))
    elif findings:
        for item in findings:
            print(f"[ERROR] {item['kind']} {item['path']}:{item['line']} {item['value']}")
    else:
        print("[OK] 运行路径契约通过")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
