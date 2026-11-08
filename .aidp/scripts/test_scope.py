#!/usr/bin/env python3
"""从 Sprint 起点 commit、当前树和契约 write_set 推导单测，绝不回落全量。

--root . --since SHA --runners-json JSON [--write-set PATH ...] --json
运行器示例：{"suffixes":[".py"],"cwd":"api","argv":["python3","-m","unittest","{tests}"]}
命名运行器必须选择 {tests}（独立 argv 项，路径相对 cwd）或 {test_classes}（Java 全限定类名）。
related 运行器须声明 mode=related，使用 {sources} 独立项和 Jest --findRelatedTests
或 Vitest related；不能使用空选择。每个 run 只选择一个测试文件/related 源文件，便于增量补测。
命名映射只作种子；Python import/from、本地测试辅助代码与包初始化的传递闭包补充选择。
模块由运行器 cwd 与最近的构建清单确定；依赖可跨模块。未知加载明确记录并保守补测。
无映射/不支持的代码进入 unmapped（Minor）；已有测试缺运行器进入 unrunnable（Important 未核验）。
scope_hash 绑定完整确定性输出（含工作树内容指纹）；执行方必须重新 derive 验真。
范围文件请写入 docs/ 或 memory/，避免输出自身成为测试输入。退出码：0 推导成功，2 输入错误。
"""
from __future__ import annotations

import argparse
import ast
import tokenize
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile

SCHEMA = 2
CODE_EXTS = frozenset((".java", ".ts", ".tsx", ".js", ".jsx", ".vue", ".py", ".go",
                       ".rs", ".kt", ".kts", ".cs", ".rb", ".php", ".c", ".h", ".cpp", ".swift",
                       ".scala", ".sc", ".m", ".mm", ".dart", ".ex", ".exs", ".erl", ".clj", ".sh", ".sql"))
TEST_NAME = re.compile(r"(Tests?\.java|\.(spec|test)\.(ts|tsx|js|jsx)|_test\.py|_test\.go)$")
PLACEHOLDER = re.compile(r"\{[a-z_]+\}")
NON_CODE_ROOTS = ("docs/", "memory/", ".git/")
MODULE_MARKERS = frozenset(("package.json", "pom.xml", "build.gradle", "build.gradle.kts", "pyproject.toml",
                            "setup.py", "setup.cfg", "go.mod", "Cargo.toml"))


class ScopeError(ValueError):
    """范围输入不明确；不能回落全量。"""


def digest(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def git_output(root, *args):
    try:
        result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ScopeError(f"Git 不可用：{exc}") from exc
    if result.returncode:
        raise ScopeError(f"git {' '.join(args)} 失败：{os.fsdecode(result.stderr).strip()}")
    return result.stdout


def git_paths(root, *args):
    return [os.fsdecode(path) for path in git_output(root, *args).split(b"\0") if path]


def repository_files(root):
    return sorted(set(git_paths(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z")))


def relative_path(root, value, directory=False):
    if not isinstance(value, str) or not value or "\0" in value or Path(value).is_absolute():
        raise ScopeError(f"必须是 root 内相对路径：{value!r}")
    path = Path(os.path.abspath(root / value))
    if not path.is_relative_to(root) or not path.resolve().is_relative_to(root):
        raise ScopeError(f"路径越出 root：{value!r}")
    if directory and not path.is_dir():
        raise ScopeError(f"运行器 cwd 不存在：{value!r}")
    return path.relative_to(root).as_posix()


def resolve_since(root, since):
    if not isinstance(since, str) or not since or since.startswith("-"):
        raise ScopeError("缺少有效 --since（本 Sprint 起点 commit），不能回落 HEAD")
    return os.fsdecode(git_output(root, "rev-parse", "--verify", f"{since}^{{commit}}")).strip()


def changed_files(root, since, write_set):
    since = resolve_since(root, since)
    names = set(git_paths(root, "diff", "--name-only", "--no-renames", "-z", since, "--"))
    names.update(git_paths(root, "ls-files", "--others", "--exclude-standard", "-z"))
    for value in write_set:
        rel = relative_path(root, value)
        if (root / rel).is_dir():
            names.update(p for p in repository_files(root) if within(p, rel))
        else:
            names.add(rel)
    return sorted(names)


def is_test(rel):
    path = PurePosixPath(rel)
    return bool(TEST_NAME.search(path.name) or (path.name.startswith("test_") and path.suffix == ".py"
                and (path.parent == PurePosixPath(".") or {"tests", "test"}.intersection(path.parent.parts))))


def stem_candidates(rel):
    path = PurePosixPath(rel)
    name, suffix = path.stem, path.suffix
    if suffix == ".java":
        return [f"{name}Test.java", f"{name}Tests.java"]
    if suffix in (".ts", ".tsx", ".js", ".jsx", ".vue"):
        return [f"{name}.{kind}{ext}" for kind in ("spec", "test") for ext in (".ts", ".tsx", ".js", ".jsx")]
    if suffix == ".py":
        return [f"test_{name}.py", f"{name}_test.py"]
    if suffix == ".go":
        return [f"{name}_test.go"]
    return []


def validate_runners(runners, root=None):
    if not isinstance(runners, list):
        raise ScopeError("--runners-json 必须是数组；[] 表示未配置运行器，不可冒充测试通过")
    normalized = []
    for runner in runners:
        if not isinstance(runner, dict):
            raise ScopeError("运行器必须是对象")
        suffixes, argv = runner.get("suffixes"), runner.get("argv")
        if (not isinstance(suffixes, list) or not suffixes
                or not all(isinstance(s, str) and re.fullmatch(r"\.[a-zA-Z0-9]+", s) for s in suffixes)):
            raise ScopeError("运行器 suffixes 必须是扩展名数组")
        if not isinstance(argv, list) or not argv or not all(isinstance(a, str) and a and "\0" not in a for a in argv):
            raise ScopeError("运行器 argv 必须是非空字符串数组")
        mode = runner.get("mode", "named")
        placeholders = [p for a in argv for p in PLACEHOLDER.findall(a)]
        if mode == "named":
            if not placeholders or any(p not in ("{tests}", "{test_classes}") for p in placeholders):
                raise ScopeError("命名运行器必须用 {tests} 或 {test_classes} 选择测试，禁止全量命令")
            if any("{tests}" in a and a != "{tests}" for a in argv):
                raise ScopeError("{tests} 必须是独立 argv 项")
            if "{test_classes}" in placeholders and suffixes != [".java"]:
                raise ScopeError("{test_classes} 仅适用于 Java 测试")
            if any(a in ("--passWithNoTests", "--allowEmpty") for a in argv):
                raise ScopeError("不能把零测试收集配置成 PASS")
        elif mode == "related":
            if any(a in ("--passWithNoTests", "--allowEmpty") for a in argv):
                raise ScopeError("不能把零测试收集配置成 PASS")
            if (placeholders != ["{sources}"] or "{sources}" not in argv
                    or not ("--findRelatedTests" in argv or "related" in argv)):
                raise ScopeError("related 必须使用 {sources} 及 --findRelatedTests/related 选择参数")
        else:
            raise ScopeError(f"不支持运行器 mode：{mode}")
        cwd = runner.get("cwd", ".")
        if root is not None:
            cwd = relative_path(root, cwd, directory=True)
        elif not isinstance(cwd, str):
            raise ScopeError("运行器 cwd 必须是字符串")
        env_id = runner.get("env_id", "")
        inputs = runner.get("inputs", [])
        if not isinstance(env_id, str) or not isinstance(inputs, list) or not all(isinstance(p, str) for p in inputs):
            raise ScopeError("运行器 env_id 必须为字符串，inputs 必须为相对 root 的路径数组")
        if root is not None:
            from test_ledger import normalize_inputs
            inputs = normalize_inputs(root, inputs)
        item = {"suffixes": sorted(set(suffixes)), "argv": argv, "cwd": cwd, "mode": mode,
                "env_id": env_id, "inputs": inputs}
        if item not in normalized:
            normalized.append(item)
    return normalized


def module_roots(files, runners):
    return sorted({".", *(r["cwd"] for r in runners),
                   *(PurePosixPath(p).parent.as_posix() for p in files if PurePosixPath(p).name in MODULE_MARKERS)},
                  key=lambda p: (len(PurePosixPath(p).parts), p))


def within(path, directory):
    return directory == "." or path == directory or path.startswith(directory + "/")


def module_for(path, modules):
    return next((m for m in reversed(modules) if within(path, m)), ".")


def mapped_tests(rel, files, modules):
    """命名与目录共同匹配；不按全仓同名搜索。"""
    existing = files if isinstance(files, (set, frozenset)) else set(files)
    if is_test(rel):
        return [rel] if rel in existing else []
    module = module_for(rel, modules)
    local = PurePosixPath(rel).relative_to(module)
    parent = local.parent
    directories = {parent}
    if local.suffix != ".go":
        directories.update((parent / "tests", parent / "test", parent / "__tests__"))
        parts = list(parent.parts)
        # Maven 标准布局保持 package 路径。
        if parts[:3] == ["src", "main", "java"]:
            directories.add(PurePosixPath("src/test/java", *parts[3:]))
        tail = parts[1:] if parts[:1] in (["src"], ["lib"]) else parts
        directories.update(PurePosixPath(base, *tail) for base in ("tests", "test", "__tests__"))
    candidates = {str(PurePosixPath(module, directory, name))
                  for directory in directories for name in stem_candidates(rel)}
    return sorted(p for p in candidates & existing if module_for(p, modules) == module)


DEPENDENCY_POLICY = "python-import-closure-v1"


def dependency_analysis(root, files, modules, runners):
    """解析本地 Python 导入闭包；命名映射只增加依赖，绝不证明独立。

    不执行项目代码。缺失/外部导入、动态加载及无法解析的文件均显式标记 unknown。
    闭包随 scope_hash 入账，历史复验不需要从当前工作树猜测旧文件内容。
    """
    files = set(files)
    python_files = {p for p in files if p.endswith(".py")}
    directories = {str(parent) for p in python_files for parent in PurePosixPath(p).parents}
    parsed = {}

    def parse(path):
        if path not in parsed:
            try:
                with tokenize.open(root / path) as stream:
                    parsed[path] = ast.parse(stream.read(), filename=path)
            except (OSError, UnicodeError, SyntaxError) as exc:
                parsed[path] = type(exc).__name__
        return parsed[path]

    def package_files(path):
        return {str(parent / "__init__.py") for parent in PurePosixPath(path).parents
                if str(parent / "__init__.py") in python_files}

    def resolve(module, bases):
        resolved, exists = set(), False
        for base in bases:
            path = PurePosixPath(base, *module.split(".")) if module else PurePosixPath(base)
            matches = {str(path) + ".py", str(path / "__init__.py")} & python_files
            if matches or str(path) in directories:
                # 多个可能的导入根取并集，不猜测 sys.path 中哪一个优先。
                exists = True
                resolved.update(matches)
                resolved.update(package_files(str(path / "__namespace__.py")))
                for match in matches:
                    resolved.update(package_files(match))
        return resolved, exists

    named_sources = {}
    for source in python_files:
        if not is_test(source):
            for test in mapped_tests(source, files, modules):
                named_sources.setdefault(test, set()).add(source)
    analysis = {}
    for test in sorted(p for p in files if is_test(p)):
        matching = [r for r in runners if within(test, r["cwd"]) and PurePosixPath(test).suffix in r["suffixes"]]
        runner = max(matching, key=lambda r: len(PurePosixPath(r["cwd"]).parts), default=None)
        cwd = runner["cwd"] if runner else module_for(test, modules)
        unknown, runner_unknown = set(), set()
        if not test.endswith(".py"):
            analysis[test] = {"files": [test], "unknown": ["非 Python 依赖未静态解析"]}
            continue
        if runner:
            argv = runner["argv"]
            if (runner["mode"] != "named" or not Path(argv[0]).name.startswith(("python", "pypy"))
                    or "-c" in argv or ("-m" in argv and argv[argv.index("-m") + 1] != "unittest")
                    or any(a.endswith(".py") for a in argv[1:])):
                runner_unknown.add("运行器可能引入额外依赖，未证明独立")
        pythonpath = []
        for entry in os.environ.get("PYTHONPATH", "").split(os.pathsep):
            if not entry:
                continue
            path = Path(os.path.abspath(root / cwd / entry))
            if path.is_relative_to(root):
                pythonpath.append(path.relative_to(root).as_posix())
            else:
                unknown.add("仓库外 PYTHONPATH 无法解析")
        seeds = {test} | package_files(test)
        # unittest/pytest 本地测试包初始化和 fixture 也是依赖。
        seeds.update(str(parent / "conftest.py") for parent in PurePosixPath(test).parents
                     if str(parent / "conftest.py") in python_files)
        seeds.update(named_sources.get(test, ()))
        pending, closure = list(seeds), set()
        while pending:
            path = pending.pop()
            if path in closure:
                continue
            closure.add(path)
            if path not in python_files:
                continue
            tree = parse(path)
            if isinstance(tree, str):
                unknown.add(f"{path}: 无法解析 Python ({tree})")
                continue
            module = module_for(path, modules)
            bases = list(dict.fromkeys((cwd, str(PurePosixPath(test).parent),
                                        str(PurePosixPath(cwd, "src")), str(PurePosixPath(cwd, "lib")),
                                        module, str(PurePosixPath(module, "src")), ".", "src", "lib", *pythonpath)))
            dependencies = set()
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    if isinstance(node, ast.Import):
                        imports = [(a.name, False) for a in node.names]
                        search = bases
                    else:
                        search = bases
                        if any(a.asname and a.asname != a.name for a in node.names
                               if a.name in {"Path", "open", "eval", "exec", "__import__"}):
                            unknown.add(f"{path}: 动态输入函数别名")
                        if node.level:
                            parent = PurePosixPath(path).parent
                            for _ in range(node.level - 1):
                                parent = parent.parent
                            search = [str(parent)]
                        imports = [(node.module or "", False)]
                        imports += [(".".join(filter(None, (node.module, a.name))), True)
                                    for a in node.names if a.name != "*"]
                        if any(a.name == "*" for a in node.names):
                            unknown.add(f"{path}: 星号导入无法证明独立")
                    for name, attribute in imports:
                        resolved, exists = resolve(name, search)
                        dependencies.update(resolved)
                        if not exists and not attribute and name.split(".")[0] not in sys.stdlib_module_names:
                            unknown.add(f"{path}: 未解析导入 {name or '.'}")
                        if name.split(".")[0] in {"importlib", "runpy", "subprocess", "ctypes", "builtins", "os", "sys"}:
                            unknown.add(f"{path}: 动态加载/外部执行 {name}")
                elif isinstance(node, ast.Call):
                    name = node.func.id if isinstance(node.func, ast.Name) else (
                        node.func.attr if isinstance(node.func, ast.Attribute) else "")
                    if name in {"__import__", "eval", "exec", "compile", "getattr", "globals", "locals",
                                "system", "popen", "load_tests", "loadTestsFromName", "loadTestsFromNames",
                                "discover", "joinpath", "with_name", "with_suffix", "glob", "rglob", "chdir"}:
                        unknown.add(f"{path}: 动态依赖调用 {name}")
                    if name in {"Path", "open"}:
                        if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                            value = node.args[0].value
                            target = Path(os.path.abspath(root / cwd / value))
                            if not target.is_relative_to(root):
                                unknown.add(f"{path}: 仓库外文件输入")
                            else:
                                rel = target.relative_to(root).as_posix()
                                # docs/memory 等默认排除状态仍遵守 --input/env-id 契约。
                                if not rel.startswith(NON_CODE_ROOTS):
                                    dependencies.add(rel)
                                    dependencies.update(p for p in files if within(p, rel))
                        else:
                            unknown.add(f"{path}: 动态文件路径 {name}")
                elif isinstance(node, ast.Name) and node.id in {"__import__", "eval", "exec", "compile", "globals", "locals"}:
                    unknown.add(f"{path}: 动态执行引用 {node.id}")
                elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Name) and node.value.id in {"Path", "open"}:
                    unknown.add(f"{path}: 动态输入函数转交")
                elif isinstance(node, ast.Attribute) and node.attr in {"path", "modules", "meta_path", "__dict__"}:
                    unknown.add(f"{path}: 动态解析属性 {node.attr}")
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in {"__getattr__", "load_tests"}:
                    unknown.add(f"{path}: 动态加载钩子 {node.name}")
            pending.extend(dependencies - closure)
        analysis[test] = {"files": sorted(closure), "unknown": sorted(unknown),
                          "runner_unknown": sorted(runner_unknown)}
    return {"policy": DEPENDENCY_POLICY, "tests": analysis}


def dependency_impact(proof, changes, include_runner=True):
    """范围扩充与跨树继承共用；返回可记录的影响判据，空串才是已证明不相交。"""
    if set(proof["files"]).intersection(changes):
        return "本地传递依赖命中"
    unknown = proof["unknown"] + (proof.get("runner_unknown", []) if include_runner else [])
    if changes and unknown:
        return "依赖未知，保守补测：" + "; ".join(unknown)
    return ""


def render_argv(argv, tests, root=None, cwd=".", sources=()):
    relative_tests = [PurePosixPath(t).relative_to(cwd).as_posix() for t in tests]
    relative_sources = [PurePosixPath(t).relative_to(cwd).as_posix() for t in sources]
    classes = []
    for test in tests:
        package = None
        if any("{test_classes}" in a for a in argv) and not re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", PurePosixPath(test).stem):
            raise ScopeError(f"测试类名不是精确 Java 标识符：{test}")
        if root is not None and PurePosixPath(test).suffix == ".java":
            package = re.search(r"^\s*package\s+([\w.]+)\s*;", (root / test).read_text(encoding="utf-8"), re.MULTILINE)
        classes.append((package.group(1) + "." if package else "") + PurePosixPath(test).stem)
    rendered = []
    for item in argv:
        if item in ("{tests}", "{sources}"):
            selected = relative_tests if item == "{tests}" else relative_sources
            if not selected:
                raise ScopeError("空选择禁止执行")
            # 路径以 - 开头不能成为运行器选项。
            rendered.extend("./" + p if p.startswith("-") else p for p in selected)
        else:
            if "{test_classes}" in item and not classes:
                raise ScopeError("空测试类选择禁止执行")
            rendered.append(item.replace("{test_classes}", ",".join(classes)))
    return rendered


def derive(root, since, runners, write_set=()):
    root = Path(root).resolve()
    since = resolve_since(root, since)
    runners = validate_runners(runners, root)
    write_set = sorted(set(relative_path(root, p) for p in write_set))
    changes = [p for p in changed_files(root, since, write_set)
               if not p.startswith(NON_CODE_ROOTS) and PurePosixPath(p).suffix in CODE_EXTS]
    files = [p for p in repository_files(root) if not p.startswith(NON_CODE_ROOTS) and (root / p).is_file()]
    modules = module_roots(files, runners)
    dependencies = dependency_analysis(root, files, modules, runners)
    mapping, unmapped, tests, related = [], [], set(), []
    for rel in changes:
        matching = [r for r in runners if r["mode"] == "related" and within(rel, r["cwd"])
                    and PurePosixPath(rel).suffix in r["suffixes"] and (root / rel).is_file()]
        if matching:
            depth = max(len(PurePosixPath(r["cwd"]).parts) for r in matching)
            owners = [r for r in matching if len(PurePosixPath(r["cwd"]).parts) == depth]
            if len(owners) != 1:
                raise ScopeError(f"源码存在多个同级 related 运行器：{rel}")
            related.append((rel, owners[0]))
            mapping.append({"change": rel, "tests": [rel] if is_test(rel) else [], "reason": "framework related"})
            continue
        found = set(mapped_tests(rel, files, modules))
        proven = set(found)
        reasons = []
        if rel.endswith(".py"):
            for test, proof in dependencies["tests"].items():
                if not test.endswith(".py"):
                    continue
                reason = dependency_impact(proof, [rel], include_runner=False)
                if reason:
                    found.add(test)
                    reasons.append(f"{test}: {reason}")
                if rel in proof["files"]:
                    proven.add(test)
        if found:
            tests.update(found)
            mapping.append({"change": rel, "tests": sorted(found),
                            "reason": "；".join(reasons) or ("改动的测试文件" if is_test(rel) else "命名及目录映射")})
        if not proven:
            unmapped.append(rel)
    runs, claimed = [], set()
    for test in sorted(tests):
        matching = [r for r in runners if within(test, r["cwd"]) and PurePosixPath(test).suffix in r["suffixes"]]
        if not matching:
            continue
        depth = max(len(PurePosixPath(r["cwd"]).parts) for r in matching)
        owners = [r for r in matching if len(PurePosixPath(r["cwd"]).parts) == depth]
        if len(owners) != 1:
            raise ScopeError(f"测试存在多个同级运行器，须明确 cwd/suffixes：{test}")
        runner = owners[0]
        if runner["mode"] == "related":
            # 已知测试文件本身可以作为框架 related 输入。
            related.append((test, runner))
        else:
            runs.append({"suffixes": runner["suffixes"], "cwd": runner["cwd"], "tests": [test], "sources": [],
                         "module": module_for(test, modules), "mode": "named",
                         "env_id": runner["env_id"], "inputs": runner["inputs"],
                         "argv": render_argv(runner["argv"], [test], root, runner["cwd"])})
        claimed.add(test)
    for source, runner in related:
        runs.append({"suffixes": runner["suffixes"], "cwd": runner["cwd"],
                     "tests": [source] if is_test(source) else [], "sources": [source],
                     "module": module_for(source, modules), "mode": "related",
                     "env_id": runner["env_id"], "inputs": runner["inputs"],
                     "argv": render_argv(runner["argv"], [], root, runner["cwd"], [source])})
    # 共用账本的内容指纹算法，避免范围与证据对“同树”作不同解释。
    from test_ledger import tree_snapshot
    snapshot = tree_snapshot(root, [path for runner in runners for path in runner["inputs"]])
    dependencies["tests"] = {test: dependencies["tests"][test] for test in sorted(tests)}
    result = {"schema": SCHEMA, "since": since, "write_set": write_set, "runners": runners,
              "changed": changes, "tests": sorted(tests), "runs": runs,
              "unrunnable": sorted(tests - claimed), "mapping": mapping, "unmapped": unmapped,
              "modules": modules, "dependencies": dependencies, "tree_hash": snapshot["hash"]}
    result["scope_hash"] = digest(result)
    return result


def validate_scope(root, scope):
    if not isinstance(scope, dict) or scope.get("schema") != SCHEMA:
        raise ScopeError("范围文件版本/结构错误，请重新运行 test_scope.py")
    unsigned = {k: v for k, v in scope.items() if k != "scope_hash"}
    if scope.get("scope_hash") != digest(unsigned):
        raise ScopeError("scope_hash 与范围内容不匹配")
    current = derive(root, scope.get("since"), scope.get("runners"), scope.get("write_set", []))
    if current != scope:
        raise ScopeError("范围与当前树/确定性推导不一致，请重新运行 test_scope.py")
    return current


def self_check():
    checks = []
    with tempfile.TemporaryDirectory(prefix="aidp-test-scope-selfcheck-") as temp:
        root = Path(temp)
        git_output(root, "init", "-q")
        git_output(root, "config", "user.email", "t@example.invalid")
        git_output(root, "config", "user.name", "t")
        for name in ("src/x.py", "tests/test_x.py"):
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_text("x=1\n")
        git_output(root, "add", "-A")
        git_output(root, "commit", "-qm", "base")
        base = resolve_since(root, "HEAD")
        (root / "src/x.py").write_text("x=2\n")
        runners = [{"suffixes": [".py"], "argv": [sys.executable, "{tests}"]}]
        out = derive(root, base, runners)
        checks.extend((out["tests"] == ["tests/test_x.py"], validate_scope(root, out) == out))
        for argv in ([sys.executable, "-m", "unittest", "discover"], [sys.executable, "{unknown}"]):
            try:
                derive(root, base, [{"suffixes": [".py"], "argv": argv}])
                checks.append(False)
            except ScopeError:
                checks.append(True)
        checks.append(derive(root, base, [])["unrunnable"] == ["tests/test_x.py"])
    return {"ok": all(checks), "checks": len(checks), "positive": 3, "negative": 2}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=".")
    parser.add_argument("--since", default="")
    parser.add_argument("--runners-json", default="[]")
    parser.add_argument("--write-set", action="append", default=[])
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args(argv)
    try:
        out = self_check() if args.self_check else derive(Path(args.root).resolve(), args.since,
                                                          json.loads(args.runners_json), args.write_set)
        code = 0 if out.get("ok", True) else 1
    except (OSError, ValueError, TypeError) as exc:
        out, code = {"kind": "error", "error": str(exc)}, 2
    print(json.dumps(out, ensure_ascii=True, sort_keys=True, indent=None if args.json else 2))
    return code


if __name__ == "__main__":
    sys.exit(main())
