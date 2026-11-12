#!/usr/bin/env python3
"""由改动推出显式相关测试白名单，不授权目录/无参或系统全量入口。

  --root . [--since REF] [--write-set PATH ...] [--execution-context CTX_JSON]
  [--scope FILE] [--runners-json JSON|@file] [--max-tests N] [--out FILE] [--json]

改动来源：git diff（起点→工作树）+ 未跟踪文件 + 显式写集；有 execution-context 时以冻结任务范围为准。
选测复用 test_scope.derive（导入闭包/命名映射/资源声明）；无上下文时补充其他布局的命名约定。
--scope 校验已有范围的任务身份、内容 hash 与当前输入后原样使用 tests，禁止版本全量范围。
上下文或推导校验失败即拒绝，不回退命名猜测。白名单写入
memory/.aidp/test-allowlist/<key>.json（key = 上下文 task_id，无上下文为 default），
由 test_command_guard 对「显式文件参数」做子集校验。

输出 JSON：{"tests":[...],"unmapped":[...],"allowed_args":[...],"allowlist_file":"...","basis":{...}}
tests 为空时 unmapped/basis.note 说明原因（仅文档改动、无对应测试等）。

保留完整相关文件集合，即使恰好覆盖小项目全部测试；不截断已证明相关的测试。
默认不设数量上限；显式 --max-tests 不足时返回 BUDGET_EXCEEDED，不发布部分白名单。
退出码：0 成功（tests 可为空），2 输入/上下文/范围校验或预算错误。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SCHEMA = 1
DEFAULT_MAX = None
ALLOWLIST_DIR = "memory/.aidp/test-allowlist"
NON_CODE_ROOTS = ("docs/", "memory/", ".git/")
SOURCE_EXTS = frozenset((".java", ".ts", ".tsx", ".js", ".jsx", ".vue", ".py", ".go", ".rs", ".kt", ".kts",
                         ".cs", ".rb", ".php", ".c", ".h", ".cpp", ".swift", ".scala", ".dart", ".ex", ".exs"))
EXTRA_TEST_NAME = re.compile(r"(Tests?\.(java|kt|cs|php|scala|swift)|_spec\.rb|_test\.(rb|py|go|rs|exs)"
                             r"|\.(spec|test)\.(ts|tsx|js|jsx|mjs|cjs)|Spec\.(scala|kt))$")


class InputError(ValueError):
    pass


def _git(root, *args):
    try:
        result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise InputError(f"git 不可用：{exc}") from exc
    if result.returncode:
        raise InputError(f"git {' '.join(args)} 失败：{os.fsdecode(result.stderr).strip()}")
    return result.stdout


def _paths(root, *args):
    return [os.fsdecode(p) for p in _git(root, *args).split(b"\0") if p]


def looks_like_test(rel):
    import test_scope
    path = PurePosixPath(rel)
    return bool(test_scope.is_test(rel) or EXTRA_TEST_NAME.search(path.name)
                or (path.name.startswith("test_") and path.suffix == ".py"))


def name_candidates(rel):
    """命名约定候选文件名（不含目录）：在 test_scope.stem_candidates 之上补 kt/cs/rb/php。"""
    import test_scope
    path = PurePosixPath(rel)
    name, suffix = path.stem, path.suffix
    names = list(test_scope.stem_candidates(rel))
    if suffix in (".kt", ".kts"):
        names += [f"{name}Test.kt", f"{name}Tests.kt"]
    elif suffix == ".cs":
        names += [f"{name}Test.cs", f"{name}Tests.cs"]
    elif suffix == ".rb":
        names += [f"{name}_spec.rb", f"{name}_test.rb"]
    elif suffix == ".php":
        names += [f"{name}Test.php"]
    elif suffix == ".rs":
        names += [f"{name}_test.rs"]
    return names


def safe_key(value):
    key = re.sub(r"[^A-Za-z0-9_.-]", "_", str(value or "default"))
    return key.strip(".") or "default"


def load_context_meta(root, ctx_path):
    """先验证本仓当前任务身份；无效上下文不得回退命名选测。"""
    import test_scope
    try:
        data = test_scope.execution_context_data(root, ctx_path)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise InputError(f"执行上下文无效：{ctx_path}（{exc}）") from exc
    return {"task_id": data["task_id"], "since": data["since"], "write_set": data["write_set"]}


def collect_changes(root, since, write_set):
    names = set(_paths(root, "diff", "--name-only", "--no-renames", "-z", since, "--"))
    names.update(_paths(root, "ls-files", "--others", "--exclude-standard", "-z"))
    for value in write_set:
        p = Path(value)
        if p.is_absolute() or ".." in p.parts:
            raise InputError(f"--write-set 必须是 root 内相对路径：{value}")
        if (root / value).is_dir():
            names.update(f for f in repo_files(root) if f == value or f.startswith(value.rstrip("/") + "/"))
        else:
            names.add(PurePosixPath(value).as_posix())
    return sorted(n for n in names if not n.startswith("memory/.aidp/"))


def repo_files(root):
    names = set(_paths(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z"))
    return sorted(p for p in names if (root / p).is_file())


def behavior_change(rel):
    return (not rel.startswith(NON_CODE_ROOTS) and PurePosixPath(rel).suffix in SOURCE_EXTS)


def naming_matches(rel, files, by_name):
    """目录映射（test_scope.mapped_tests）+ 全仓同名约定；返回 (直接映射, 同名约定)。"""
    import test_scope
    modules = test_scope.module_roots(files, [])
    direct = set(test_scope.mapped_tests(rel, set(files), modules))
    named = set()
    for name in name_candidates(rel):
        named.update(by_name.get(name, ()))
    return direct, named - direct


def tests_for(rel, files, by_name):
    direct, named = naming_matches(rel, files, by_name)
    return direct | named


def try_derive(root, since, runners, write_set, ctx_path):
    import test_scope
    try:
        return test_scope.derive(root, since, runners, write_set, ctx_path or None)
    except (OSError, ValueError) as exc:
        raise InputError(f"范围推导失败：{exc}") from exc


def select(root, since, write_set, ctx_path, runners, max_tests, scope_path=""):
    root = Path(root).resolve()
    requested_since, requested_write_set = since, write_set
    meta = load_context_meta(root, ctx_path) if ctx_path else None
    if meta:
        since = since or meta["since"]
        write_set = write_set or meta["write_set"]
    since = since or "HEAD"
    if not (root / ".git").exists() and not _paths_ok(root):
        raise InputError("root 不是 git 仓库")
    _git(root, "rev-parse", "--verify", f"{since}^{{commit}}")
    changes = collect_changes(root, since, write_set)
    files = repo_files(root)
    all_tests = sorted(p for p in files if looks_like_test(p))
    by_name = {}
    for t in all_tests:
        by_name.setdefault(PurePosixPath(t).name, set()).add(t)
    sources = [c for c in changes if behavior_change(c) and not looks_like_test(c) and (root / c).is_file()]
    changed_tests = [c for c in changes if looks_like_test(c) and (root / c).is_file()]
    basis = {"mode": "naming", "since": since, "changed": changes, "total_tests": len(all_tests)}

    proven_changes = set()
    tier = {}  # test -> 优先级，越小越直接
    for t in changed_tests:
        tier[t] = 0
    covered = set()
    for src in sources:
        direct, named = naming_matches(src, files, by_name)
        for t in direct | named:
            tier[t] = min(tier.get(t, 1), 1)
        if direct | named:
            covered.add(src)

    if scope_path:
        import test_scope
        try:
            scope = json.loads(Path(scope_path).read_text(encoding="utf-8"))
            if not isinstance(scope, dict) or scope.get("kind") == "version":
                raise InputError("--scope 必须是本任务相关测试范围，不能使用版本全量范围")
            derived = test_scope.validate_scope(root, scope, ctx_path or None)
            if requested_write_set and sorted(set(test_scope.relative_path(root, p) for p in requested_write_set)) != derived["write_set"]:
                raise InputError("--write-set 与 scope 范围冲突")
            if requested_since and test_scope.resolve_since(root, requested_since) != derived["since"]:
                raise InputError("--since 与 scope 起点冲突")
            if runners and test_scope.validate_runners(runners, root) != derived["runners"]:
                raise InputError("--runners-json 与 scope 运行器冲突")
        except (OSError, ValueError) as exc:
            raise InputError(f"范围校验失败：{exc}") from exc
    else:
        derived = try_derive(root, since, runners, write_set if ctx_path else (write_set or changes), ctx_path)
    basis["mode"] = "test_scope"
    basis["since"] = derived["since"]
    if ctx_path or scope_path:
        # 执行及白名单共用同一确定性结果，不混入工作区其他任务的命名命中。
        tier = {t: 2 for t in derived["tests"]}
        basis["changed"] = derived["changed"]
        sources = [c for c in derived["changed"] if behavior_change(c) and not looks_like_test(c)]
    proven = set(derived.get("selection", {}).get("proven", []))
    conservative = set(derived.get("selection", {}).get("conservative", []))
    for t in proven:
        tier[t] = min(tier.get(t, 2), 2)
    for t in conservative:
        tier.setdefault(t, 3)
    proven_changes = {m["change"] for m in derived.get("mapping", []) if m.get("tests")}
    covered |= proven_changes

    for test in tier:
        if not (root / test).is_file():
            raise InputError(f"范围包含非文件测试：{test}")
    ordered = sorted(tier, key=lambda t: (tier[t], t))
    if max_tests is not None and (max_tests < 1 or len(ordered) > max_tests):
        raise InputError(f"BUDGET_EXCEEDED：相关测试 {len(ordered)} 个超过 --max-tests {max_tests}；不发布截断白名单")
    basis["tiers"] = {str(k): sum(1 for t in ordered if tier[t] == k) for k in (0, 1, 2, 3)}
    tests = sorted(ordered)
    chosen = set(tests)
    unmapped = sorted(s for s in sources if s not in covered
                      or not (set(tests_for(s, files, by_name)) & chosen or s in proven_changes))
    if not tests and "note" not in basis:
        basis["note"] = "改动仅含文档/配置或没有对应测试；无相关测试可跑" if not sources else "改动源码没有可映射的测试，见 unmapped"
    key = safe_key(meta["task_id"] if meta else "default")
    rel = f"{ALLOWLIST_DIR}/{key}.json"
    result = {"schema": SCHEMA, "tests": tests, "unmapped": unmapped, "allowed_args": list(tests),
              "allowlist_file": rel, "basis": basis}
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    record = dict(result, task_id=meta["task_id"] if meta else "default", created_at=int(time.time()))
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, target)
    return result


def _paths_ok(root):
    try:
        _git(root, "rev-parse", "--git-dir")
        return True
    except InputError:
        return False


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=".")
    parser.add_argument("--since", default="")
    parser.add_argument("--write-set", action="append", default=[])
    parser.add_argument("--execution-context", default="")
    parser.add_argument("--runners-json", default="[]")
    parser.add_argument("--scope", default="", help="校验已有 test_scope 范围后原样发布测试文件白名单")
    parser.add_argument("--max-tests", type=int, default=DEFAULT_MAX)
    parser.add_argument("--out", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.max_tests is not None and args.max_tests < 1:
            raise InputError("--max-tests 必须 >= 1")
        raw = args.runners_json
        if raw.startswith("@"):
            raw = Path(raw[1:]).read_text(encoding="utf-8")
        try:
            runners = json.loads(raw)
        except ValueError as exc:
            raise InputError(f"--runners-json 不是合法 JSON：{exc}") from exc
        result = select(args.root, args.since, args.write_set, args.execution_context, runners, args.max_tests, args.scope)
    except (InputError, OSError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    text = json.dumps(result, ensure_ascii=False, indent=None if args.json else 2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    if args.json or not args.out:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
