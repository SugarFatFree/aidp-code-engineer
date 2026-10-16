#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""未定义名静态门：抓「用了但没 import / 没定义」的符号。

这类缺陷的失效形态是**延迟到运行时**，且往往落在只有特定分支才走到的行上——
实证：`migrate.py` 调用未 import 的 `_parse_scaffold_version`，而该行只在
「下游已有 scaffold 基线」时执行，模板项目自身永远到不了 ⇒ 本仓全绿、
每个下游升级必崩。单测也挡不住：没人会为一行分支专门造一个下游夹具。

AST 层面判它是确定性的、零歧义的，且一次扫全仓。

⛔ **不替代类型检查**：只看「名字能不能解析」，不看类型、不看参数个数。

## 采集量自证（⛔ 别把「没扫到」读成「没问题」）

`--json` 恒输出 `collected`（files_scanned / files_failed / names_checked）。
**扫到 0 个文件 或 有文件解析失败 ⇒ 退出码非 0**，而不是打印「通过」——
本门的失效形态与通过同形（都是「没有告警」），没有采集量自证就无法区分
「代码是干净的」和「门根本没跑起来」。
"""
import argparse
import ast
import builtins
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aidp_runtime import runtime_relpath  # noqa: E402

# 扫描面：模板自有的确定性脚本 + 脚手架引擎自身。
# 扫描面：下发的确定性脚本 + **脚手架引擎自身** + 本仓库自有的下发 SKILL 脚本。
# ★ 脚手架引擎必须在列：它的失效形态最刻毒 —— 未 import 的名字往往只在
#   「下游已有 scaffold 基线」这类分支上执行，**模板项目自身永远到不了**
#   ⇒ 本仓全绿、每个下游升级必崩。单测也挡不住：没人会为一行分支造一个下游夹具。
# ★ 本仓库的下发 SKILL **全部自有**（约定 16），可直接改，故一并扫；
#   ⛔ 这一点与上游不同（上游那些是 vendored 只读、不该由本门判），别照抄它的排除清单。
DEFAULT_SCOPES = (
    runtime_relpath("scripts", __file__),
    "skills/aidp-code-engineer/scripts",
    runtime_relpath("skills", __file__),
)

_BUILTINS = frozenset(dir(builtins)) | {"__file__", "__name__", "__doc__", "__spec__"}


def _guarded_names(tree):
    """收集 `if "X" in globals()` / `in dir()` 这类**显式守卫**里的名字。

    这是刻意的防御写法（符号不存在就走 else 分支），不是缺陷——不豁免它
    会把一堆故意为之的兜底分支报成错，门很快就会被当噪声关掉。
    """
    names = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        if not any(isinstance(op, ast.In) for op in node.ops):
            continue
        if not isinstance(node.left, ast.Constant) or not isinstance(node.left.value, str):
            continue
        for comp in node.comparators:
            target = comp.func.id if isinstance(comp, ast.Call) and isinstance(comp.func, ast.Name) else None
            if target in ("globals", "locals", "vars", "dir"):
                names.add(node.left.value)
    return names


def _bound_names(tree):
    """模块内一切被绑定的名字（import / def / class / 赋值 / 形参 / except / global）。

    ⚠️ 刻意**不做作用域分析**：只要名字在本模块任何位置被绑定过就算已知。
    这会漏掉「跨函数引用局部名」，但换来零误报——门的价值在于能被长期信任。
    """
    bound = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bound.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            bound.add(node.id)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)
        elif isinstance(node, ast.Global):
            bound.update(node.names)
        elif isinstance(node, ast.Nonlocal):
            bound.update(node.names)
    return bound


def scan_file(path):
    """返回 (findings, names_checked)；解析失败时 findings 含一条 parse-error。"""
    try:
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
    except OSError as exc:
        return [{"file": path, "line": 0, "name": "", "kind": "read-error",
                 "detail": str(exc)}], 0
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        return [{"file": path, "line": exc.lineno or 0, "name": "", "kind": "parse-error",
                 "detail": exc.msg}], 0

    # `from x import *` 会引入不可静态枚举的名字 ⇒ 本模块整体放弃判定（宁可不报，不可错报）。
    if any(isinstance(n, ast.ImportFrom) and any(a.name == "*" for a in n.names)
           for n in ast.walk(tree)):
        return [], 0

    known = _bound_names(tree) | _guarded_names(tree) | _BUILTINS
    findings, checked = [], 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            checked += 1
            if node.id not in known:
                findings.append({"file": path, "line": node.lineno, "name": node.id,
                                 "kind": "undefined-name",
                                 "detail": "用到了但本模块既未定义也未 import"})
    return findings, checked


def run(root, scopes):
    findings, scanned, failed, checked = [], 0, 0, 0
    for scope in scopes:
        base = os.path.join(root, scope)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in ("__pycache__", ".git")]
            for name in sorted(filenames):
                if not name.endswith(".py"):
                    continue
                path = os.path.relpath(os.path.join(dirpath, name), root)
                got, n = scan_file(os.path.join(root, path))
                for item in got:
                    item["file"] = path
                if any(i["kind"] in ("parse-error", "read-error") for i in got):
                    failed += 1
                scanned += 1
                checked += n
                findings.extend(got)
    return {
        "findings": findings,
        "collected": {"files_scanned": scanned, "files_failed": failed,
                      "names_checked": checked},
    }


_SELF_CHECK_SRC = '''
import os


def helper():
    return os.sep


def broken():
    return _never_defined_anywhere(1)
'''


def self_check():
    """阳性对照（约定 35）：植入一个必然被抓到的未定义名，确认本门真会报。"""
    with tempfile.TemporaryDirectory() as tmp:
        scope = os.path.join(tmp, *runtime_relpath("scripts", __file__).split("/"))
        os.makedirs(scope)
        with open(os.path.join(scope, "probe.py"), "w", encoding="utf-8") as handle:
            handle.write(_SELF_CHECK_SRC)
        result = run(tmp, [runtime_relpath("scripts", __file__)])
    hits = [f for f in result["findings"] if f["name"] == "_never_defined_anywhere"]
    ok = bool(hits) and result["collected"]["files_scanned"] == 1
    print(json.dumps({"self_check": "pass" if ok else "fail",
                      "probe_hits": len(hits),
                      "collected": result["collected"]}, ensure_ascii=False))
    return 0 if ok else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--scope", action="append",
                        help="限定扫描目录（可重复）；缺省扫模板自有脚本 + 脚手架引擎")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    if args.self_check:
        return self_check()

    root = os.path.abspath(args.root)
    result = run(root, args.scope or list(DEFAULT_SCOPES))
    collected = result["collected"]
    # ★ 采集量自证：扫不到文件 / 有文件没解析成功，都不许走「通过」出口。
    starved = collected["files_scanned"] == 0 or collected["files_failed"] > 0
    if args.json:
        print(json.dumps({**result, "starved": starved}, ensure_ascii=False, indent=2))
    else:
        for item in result["findings"]:
            print("ERROR %s:%d %s —— %s"
                  % (item["file"], item["line"], item["name"] or item["kind"], item["detail"]))
        print("[check_undefined_names] 扫 %d 文件 / 解析失败 %d / 名字 %d / 告警 %d"
              % (collected["files_scanned"], collected["files_failed"],
                 collected["names_checked"], len(result["findings"])))
        if starved:
            print("[check_undefined_names] ⛔ 采集量异常：没有扫到文件或有文件解析失败，"
                  "本次结果【不构成通过】", file=sys.stderr)
    return 1 if (result["findings"] or starved) else 0


if __name__ == "__main__":
    sys.exit(main())
