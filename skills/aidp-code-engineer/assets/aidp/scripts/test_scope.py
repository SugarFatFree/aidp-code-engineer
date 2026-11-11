#!/usr/bin/env python3
"""从任务/Sprint 起点 commit、当前树和 write_set 推导单测，绝不回落全量。

--root . --since SHA --runners-json JSON [--write-set PATH ...] --json
--root . --execution-context PATH --runners-json JSON --json
light 从冻结上下文取起点/写集，排除未改动的初始 dirty；无需 Sprint 号或契约卡。
上下文全身份进入 scope_hash，执行/验证时必须携带同一上下文，不能跨任务借用证据。
运行器示例：{"suffixes":[".py"],"cwd":"api","argv":["python3","-m","unittest","{tests}"]}
命名运行器必须选择 {tests}（独立 argv 项，路径相对 cwd）或 {test_classes}（Java 全限定类名）。
related 运行器须声明 mode=related，使用 {sources} 独立项和 Jest --findRelatedTests
或 Vitest related；不能使用空选择。已知多选择器运行器安全合批，batch:false 保留逐文件证据。
命名映射只作种子；Python import/from、本地测试辅助代码与包初始化的传递闭包补充选择。
模块由运行器 cwd 与最近的构建清单确定；依赖可跨模块。未知加载明确记录并保守补测。
无映射/不支持的代码进入 unmapped（Minor）；已有测试缺运行器进入 unrunnable（Important 未核验）。
scope_hash 绑定完整确定性输出；依赖分析按真实树/输入/环境/工具 hash 缓存，本批验真一次。
runner.resources 显式声明资源到 consumer/tests 的映射；无映射 JSON/YAML/SQL 保留 Minor 缺口。
范围文件请写入 docs/ 或 memory/，避免输出自身成为测试输入。退出码：0 推导成功，2 输入错误。
"""
from __future__ import annotations

import argparse
import copy
import time
import ast
import stat
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile

SCHEMA = 2
RESOURCE_EXTS = frozenset((".json", ".yaml", ".yml", ".sql"))
_ANALYSIS_CACHE = {}
_ANALYSIS_EXTRA = {}
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
    def __init__(self, message):
        super().__init__(message)
        self.status = "BUDGET_EXCEEDED" if message.startswith("BUDGET_EXCEEDED") else "UNVERIFIED"


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


def repository_files(root, execution_context=None):
    from project_inventory import git_worktree_inventory
    return git_worktree_inventory(root)["files"]


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


def changed_files(root, since, write_set, execution_context=None, files=None, inventory=None, current_files=None, baseline_reader=None):
    since = resolve_since(root, since)
    names = set(git_paths(root, "diff", "--name-only", "--no-renames", "-z", since, "--"))
    names.update(git_paths(root, "ls-files", "--others", "--exclude-standard", "-z"))
    if files is None:
        files = repository_files(root, execution_context)
    if execution_context is not None:
        from entry_context import initial_file_hash, initial_hash
        baseline_reader = baseline_reader or (lambda p: initial_hash(root, execution_context, p))
        from project_inventory import git_worktree_inventory, default_excluded
        observed = inventory if inventory is not None else git_worktree_inventory(root, since=since)
        # 父仓 diff 只给 gitlink 目录；递归 pin 差异给出候选，初始 dirty 还覆盖恢复为 Git 基线。
        # 干净且未变化的文件无需逐个 git show，完整执行树仍由 tree_snapshot 内容指纹约束。
        candidates = names | set(observed["preexisting_dirty"]) | set(execution_context["preexisting_dirty"])
        # 干净符号链接也可能仅目标内容变化；初始已实读的少量路径保持逐内容比较。
        candidates.update(p for p, value in execution_context["initial_files"].items() if value is not None)
        # Git 不报告非 executable 权限位变化，廉价 stat 仍须保留旧内容指纹的权限语义。
        for path, baseline in execution_context.get("initial_git_files", {}).items():
            if PurePosixPath(path).suffix not in CODE_EXTS | RESOURCE_EXTS:
                continue
            try:
                current_mode = stat.S_IMODE((root / path).stat().st_mode)
            except OSError:
                candidates.add(path)
            else:
                if current_mode != baseline["mode"]:
                    candidates.add(path)
        names = set(p for p in candidates
                     if not (root / p).is_dir() and not default_excluded(p, observed["repositories"])
                     and (PurePosixPath(p).suffix in CODE_EXTS | RESOURCE_EXTS or is_configuration(p))
                     and (current_files[p] if current_files is not None and p in current_files else initial_file_hash(root / p))
                     != baseline_reader(p))
    else:
        # 无冻结上下文无法区分他人未提交改动：只有已提交差异和显式写集内的脏文件归属本任务。
        dirty = set(git_paths(root, "diff", "--name-only", "--no-renames", "-z", "HEAD", "--"))
        dirty.update(git_paths(root, "ls-files", "--others", "--exclude-standard", "-z"))
        from project_inventory import default_excluded, git_worktree_inventory
        observed = inventory if inventory is not None else git_worktree_inventory(root, since=since)
        # 子模块内部脏文件只在递归清单中可见；仍按同一写集归属，不能整仓混入。
        committed = set(git_paths(root, "diff", "--name-only", "--no-renames", "-z", since, "HEAD", "--"))
        dirty |= set(observed["preexisting_dirty"]) - committed
        behavior = lambda p: (not default_excluded(p, observed["repositories"])
                              and (PurePosixPath(p).suffix in CODE_EXTS | RESOURCE_EXTS or is_configuration(p)))
        if not write_set and any(behavior(p) for p in dirty if not (root / p).is_dir()):
            raise ScopeError("工作区存在未归属改动；必须提供 execution-context 或明确 write-set，禁止全工作区选测")
        names = (names | {p for p in dirty if not (root / p).is_dir()}) - {
            p for p in dirty if not any(within(p, value) for value in write_set)}
    for value in write_set:
        rel = relative_path(root, value)
        if (root / rel).is_dir():
            candidates = (names | set((inventory or {}).get("preexisting_dirty", ())) if execution_context is not None else files)
            names.update(p for p in candidates if within(p, rel))
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
        batch = runner.get("batch")
        if batch is not None and type(batch) is not bool:
            raise ScopeError("runner.batch 必须为布尔值")
        if batch is None:
            names = [Path(a).name for a in argv]
            batch = ("{test_classes}" in placeholders and names[0] in ("mvn", "mvnw")
                     or names[0] in ("pytest", "py.test", "jest", "vitest")
                     or names[0] in ("npx", "npm", "pnpm") and any(x in names for x in ("jest", "vitest", "pytest"))
                     or names[0].startswith(("python", "pypy")) and "-m" in argv
                     and argv[argv.index("-m") + 1] in ("unittest", "pytest"))
        resources = runner.get("resources", {})
        if not isinstance(resources, dict) or any(not isinstance(v, list) or not all(isinstance(x, str) for x in v) for v in resources.values()):
            raise ScopeError("runner.resources 必须为 resource 路径到 consumer/tests 路径数组的映射")
        if root is not None:
            resources = {relative_path(root, k): sorted(set(relative_path(root, x) for x in v)) for k, v in resources.items()}
            inputs = normalize_inputs(root, [*inputs, *(p for p in resources if (root / p).exists())])
        item = {"batch": batch, "resources": resources, "suffixes": sorted(set(suffixes)), "argv": argv, "cwd": cwd, "mode": mode,
                "env_id": env_id, "inputs": inputs}
        if item not in normalized:
            normalized.append(item)
    return normalized


def is_configuration(path):
    name = PurePosixPath(path).name
    return (name in MODULE_MARKERS | {".gitignore", ".gitmodules", "pytest.ini", "tox.ini", "Makefile",
            "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "uv.lock", "Pipfile", "Pipfile.lock", "go.sum", "Cargo.lock"}
            or name.startswith((".env", "requirements")) or "config" in name.lower()
            or name.endswith((".toml", ".cfg", ".ini")))


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


def read_frozen_source(root, path, frozen_files=None, observer=None, frozen_tokens=None, metadata=None):
    """解析只使用已与冻结快照核对的同一字节缓冲，拒绝读入 A→B→A 中间态 B。"""
    target = root / path
    from project_inventory import fingerprint_token, fingerprint_metadata, _stat_identity
    if metadata is None:
        metadata = fingerprint_metadata() or {}
    token, observation = fingerprint_token(target, metadata=metadata), _stat_identity(target)
    try:
        if observer:
            observer({"content_reads": 1, "metadata_entries": 1, "cache_hits": 0}, {str(target)})
        content = target.read_bytes()
        mode = target.lstat().st_mode
        link = os.readlink(target) if stat.S_ISLNK(mode) else None
        if link is not None:
            mode = target.stat().st_mode
    except OSError as exc:
        raise ScopeError(f"UNVERIFIED：无法读取冻结分析输入 {path}：{exc}") from exc
    if frozen_files is not None:
        observed = digest({"sha256": hashlib.sha256(content).hexdigest(), "mode": stat.S_IMODE(mode), "link": link})
        if path not in frozen_files and frozen_tokens is not None:
            # 未展开包中的真实 import 仍是输入；以本次实际解析字节补入冻结证明。
            frozen_files[path] = observed
            frozen_tokens[path] = {"token": token, "observation": observation}
        elif observed != frozen_files.get(path):
            raise ScopeError(f"TREE_CHANGED：实际解析字节与冻结快照不一致：{path}")
    if token != fingerprint_token(target, metadata=metadata) or observation != _stat_identity(target):
        raise ScopeError(f"TREE_CHANGED：解析期间文件变化：{path}")
    return content


def dependency_analysis(root, files, modules, runners, deadline=None, repositories=(".",), frozen_files=None,
                        observer=None, candidates=None, frozen_tokens=None, metadata=None):
    """解析本地 Python 导入闭包；命名映射只增加依赖，绝不证明独立。

    不执行项目代码。缺失/外部导入、动态加载及无法解析的文件均显式标记 unknown。
    闭包随 scope_hash 入账，历史复验不需要从当前工作树猜测旧文件内容。
    """
    from project_inventory import default_excluded, fingerprint_metadata
    if metadata is None:
        metadata = fingerprint_metadata() or {}
    files = set(files)
    python_files = {p for p in files if p.endswith(".py")}
    directories = {str(parent) for p in python_files for parent in PurePosixPath(p).parents}
    parsed = {}

    def parse(path):
        if path not in parsed:
            try:
                content = read_frozen_source(root, path, frozen_files, observer, frozen_tokens, metadata)
                # ast.parse(bytes) 保留 Python 源码编码声明/BOM 的处理，且不再次打开源码。
                parsed[path] = ast.parse(content, filename=path)
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
    for test in sorted(p for p in (files if candidates is None else candidates) if is_test(p)):
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
            if deadline is not None and time.monotonic() > deadline:
                raise ScopeError("BUDGET_EXCEEDED：依赖扫描时间超出预算")
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
                                if not default_excluded(rel, repositories):
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


def render_argv(argv, tests, root=None, cwd=".", sources=(), frozen_files=None, observer=None, metadata=None):
    relative_tests = [PurePosixPath(t).relative_to(cwd).as_posix() for t in tests]
    relative_sources = [PurePosixPath(t).relative_to(cwd).as_posix() for t in sources]
    classes = []
    if metadata is None:
        from project_inventory import fingerprint_metadata
        metadata = fingerprint_metadata() or {}
    for test in tests:
        package = None
        if any("{test_classes}" in a for a in argv) and not re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", PurePosixPath(test).stem):
            raise ScopeError(f"测试类名不是精确 Java 标识符：{test}")
        if root is not None and PurePosixPath(test).suffix == ".java":
            package = re.search(r"^\s*package\s+([\w.]+)\s*;", read_frozen_source(root, test, frozen_files, observer, metadata=metadata).decode("utf-8"), re.MULTILINE)
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


def execution_context_data(root, context):
    """CLI 路径由入口模块验真；Python 调用也可传已加载的上下文。"""
    if context is None:
        return None
    from entry_context import load_context, validate_context
    return validate_context(root, context) if isinstance(context, dict) else load_context(root, context)


def context_identity(root, context):
    context = execution_context_data(root, context)
    if context is None:
        return None
    from entry_context import evidence_identity as entry_identity
    return entry_identity(context)


def analysis_paths(root, inventory, context, write_set):
    """light 默认不展开未修改的安装技能包；导入到它们的真实依赖仍可懒读取。"""
    if context is None or context["mode"] != "light":
        return None
    from project_inventory import default_excluded, fingerprint_token
    from test_ledger import _FingerprintCache
    cache = _FingerprintCache(root)
    from project_inventory import installed_skill_package
    def package(path):
        return installed_skill_package(root, path)
    active = {package(path) for path in write_set if package(path)}
    for path, baseline in context.get("initial_git_files", {}).items():
        owner = package(path)
        if owner is not None and (baseline.get("token") is None
                or fingerprint_token(root / path, metadata=cache.metadata) != baseline["token"]):
            active.add(owner)
    for path in inventory["preexisting_dirty"]:
        owner = package(path)
        if owner is None:
            continue
        if path not in context["preexisting_dirty"]:
            active.add(owner)
            continue
        record = cache.files.get(str(root / path), {})
        token = fingerprint_token(root / path, metadata=cache.metadata)
        if (token is None or token != record.get("token")
                or record.get("hash") != context["initial_files"].get(path)):
            active.add(owner)
    return [path for path in inventory["files"]
            if not default_excluded(path, inventory["repositories"])
            and (PurePosixPath(path).suffix in CODE_EXTS | RESOURCE_EXTS or is_configuration(path))
            and (package(path) is None or package(path) in active)]


def derive(root, since, runners, write_set=(), execution_context=None):
    owned = []
    try:
        return _derive(root, since, runners, write_set, execution_context, owned)
    finally:
        for progress in owned:
            progress.finish()


def _derive(root, since, runners, write_set=(), execution_context=None, _owned=None):
    root = Path(root).resolve()
    execution_context = execution_context_data(root, execution_context)
    identity = context_identity(root, execution_context)
    if identity is not None:
        if since and resolve_since(root, since) != identity["since"]:
            raise ScopeError("--since 与 execution-context 起点冲突")
        if write_set and sorted(set(relative_path(root, p) for p in write_set)) != identity["write_set"]:
            raise ScopeError("--write-set 与 execution-context 范围冲突")
        since, write_set = identity["since"], identity["write_set"]
    since = resolve_since(root, since)
    runners = validate_runners(runners, root)
    write_set = sorted(set(relative_path(root, p) for p in write_set))
    from project_inventory import git_worktree_inventory, default_excluded
    from test_ledger import tree_snapshot, environment_hash, snapshot_estimate, _ValidationProgress, _FingerprintCache
    started = time.monotonic()
    scan_seconds = min(10, execution_context["execution_budget"]["elapsed_seconds"]) if execution_context else 300
    deadline = started + scan_seconds
    if execution_context and scan_seconds <= 0:
        raise ScopeError("BUDGET_EXCEEDED：没有可用于静态扫描的时间预算")
    inventory = git_worktree_inventory(root, since=since)
    repository = inventory["files"]
    explicit_inputs = [path for runner in runners for path in runner["inputs"]]
    document_inputs = [p for p in write_set if (root / p).is_file()
                       and PurePosixPath(p).suffix in {".md", ".rst", ".txt"}]
    explicit_inputs = sorted(set(explicit_inputs) | set(document_inputs))
    for runner in runners:
        runner["inputs"] = sorted(set(runner["inputs"]) | set(document_inputs))
    analysis_inputs = analysis_paths(root, inventory, execution_context, [*write_set, *explicit_inputs])
    progress, observer = None, None
    if execution_context:
        estimate = snapshot_estimate(root, explicit_inputs, analysis_inputs)
        parsable = sum(p.endswith((".py", ".java")) and not default_excluded(p, inventory["repositories"])
                       for p in (repository if analysis_inputs is None else analysis_inputs))
        baseline_reads = len(set(inventory["preexisting_dirty"]) & set(execution_context.get("initial_git_files", {})))
        stages = {"pre_evidence": {"scanned_files": estimate["content_reads"] + parsable + baseline_reads + 3,
                                   "elapsed_seconds": scan_seconds},
                  "command": {}, "post_evidence": {"scanned_files": estimate["objects"]}, "cleanup": {}}
        progress = _ValidationProgress(root, execution_context, stages,
            digest([identity, runners, write_set, estimate["hash"]]), "static", defer_input=True)
        _owned.append(progress)
        observer = progress.observe("pre_evidence")
    snapshot = tree_snapshot(root, explicit_inputs, paths=analysis_inputs, inventory=inventory, observer=observer)
    baseline_session = None
    if execution_context is not None:
        from entry_context import _FingerprintSession
        baseline_session = _FingerprintSession(root, execution_context, charge=False)
    def baseline_reader(path):
        before_reads, before_hits = baseline_session.reads, baseline_session.hits
        try:
            return baseline_session.initial(path)
        finally:
            reads, hits = baseline_session.reads - before_reads, baseline_session.hits - before_hits
            if observer:
                observer({"content_reads": reads, "metadata_entries": 0, "cache_hits": hits},
                         {str(root / path)} if reads else set())
            if reads:
                baseline_session.save()
    raw_changes = changed_files(root, since, write_set, execution_context, repository, inventory,
                                snapshot["files"], baseline_reader if baseline_session else None)
    resource_paths = {p for r in runners for p in r["resources"]}
    changes = [p for p in raw_changes if p in resource_paths or
               (not p.startswith(NON_CODE_ROOTS) and (PurePosixPath(p).suffix in CODE_EXTS | RESOURCE_EXTS or is_configuration(p)))]
    changes = sorted(p for p in set(changes) if p in resource_paths or not default_excluded(p, inventory["repositories"]))
    if analysis_inputs is not None:
        changes = [p for p in changes if p in analysis_inputs or not (root / p).exists()]
    files = [p for p in repository if not default_excluded(p, inventory["repositories"]) and (root / p).is_file()]
    modules = module_roots(files, runners)
    cache = _FingerprintCache(root)
    tool_files = [Path(__file__), Path(__file__).with_name("project_inventory.py"), Path(__file__).with_name("test_ledger.py")]
    tools = []
    try:
        for tool in tool_files:
            record = cache.read(tool)
            tools.append(record["hash"])
            if observer:
                observer({"content_reads": int(record["read"]), "metadata_entries": 1,
                          "cache_hits": int(not record["read"])}, {str(tool)} if record["read"] else set())
    finally:
        cache.save()
    tool_hash = digest(tools)
    analysis_key = digest([str(root), snapshot["hash"], environment_hash(), tool_hash, files, modules, runners])
    initial_snapshot_paths = set(snapshot["files"])
    analysis = _ANALYSIS_CACHE.get(analysis_key)
    extra_files = _ANALYSIS_EXTRA.get(analysis_key, {})
    pending_analysis = None
    from aidp_paths import ensure_runtime_dir
    cache_file = Path(ensure_runtime_dir(root)) / "scope-analysis" / (analysis_key + ".json")
    if analysis is None:
        try:
            record = json.loads(cache_file.read_text(encoding="utf-8"))
            candidate, extra = record["analysis"], record.get("extra_files", {})
            if (record.get("key") == analysis_key and record.get("checksum") == digest([candidate, extra])
                    and candidate.get("policy") == DEPENDENCY_POLICY and isinstance(candidate.get("tests"), dict)
                    and isinstance(extra, dict)
                    and all(isinstance(v, dict) and isinstance(v.get("files"), list) and isinstance(v.get("unknown"), list)
                            for v in candidate["tests"].values())):
                analysis, extra_files = candidate, extra
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            pass
    if analysis is not None and extra_files:
        extra = tree_snapshot(root, paths=list(extra_files), observer=observer)
        observed = {path: extra["files"].get(path) for path in extra_files}
        snapshot["files"].update({p: value for p, value in observed.items() if value is not None})
        snapshot["tokens"].update(extra["tokens"])
        if observed != extra_files:
            analysis = None
    if analysis is None:
        analysis = dependency_analysis(root, files, modules, runners, deadline=deadline, repositories=inventory["repositories"],
                                       frozen_files=snapshot["files"], observer=observer, candidates=analysis_inputs,
                                       frozen_tokens=snapshot["tokens"], metadata=cache.metadata)
        pending_analysis = analysis
    dependencies = copy.deepcopy(analysis)
    # 显式资源依赖进入传递闭包，既用于选测，也用于跨树证据判断。
    for runner in runners:
        for resource, consumers in runner["resources"].items():
            for test, proof in dependencies["tests"].items():
                mapped = {t for consumer in consumers for t in mapped_tests(consumer, files, modules)}
                if test in consumers or test in mapped or set(consumers).intersection(proof["files"]):
                    proof["files"] = sorted(set(proof["files"]) | {resource})
    reverse = {}
    unknown = set()
    for test, proof in dependencies["tests"].items():
        for source in proof["files"]:
            reverse.setdefault(source, set()).add(test)
        if test.endswith(".py") and proof["unknown"]:
            unknown.add(test)
    proven_tests, conservative_tests = set(), set()

    criteria = execution_context.get("acceptance", []) if execution_context else []
    acceptance_paths = sorted(p for p in files if any(
        p == criterion or f"`{p}`" in criterion for criterion in criteria))
    mapping, unmapped, tests, related = [], [], set(), []
    for rel in sorted(set(changes) | set(acceptance_paths)):
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
        found = set(mapped_tests(rel, files, modules)) | reverse.get(rel, set())
        if is_configuration(rel):
            base = PurePosixPath(rel).parent.as_posix()
            found.update(test for test in dependencies["tests"] if within(test, base))
        proven = set(found)
        proven_tests.update(proven)
        if rel.endswith(".py"):
            conservative_tests.update(unknown - proven)
        if found:
            tests.update(found)
            mapping.append({"change": rel, "tests": sorted(found), "classification": "proven",
                            "reason": "本地依赖、资源声明或命名目录映射"})
        if not proven:
            unmapped.append(rel)
    conservative_tests -= proven_tests
    tests.update(conservative_tests)
    runs, claimed = [], set()
    groups = {}
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
            key = digest(runner) if runner["batch"] else digest([runner, test])
            groups.setdefault(key, (runner, []))[1].append(test)
        claimed.add(test)
    related_groups = {}
    for source, runner in related:
        key = digest(runner) if runner["batch"] else digest([runner, source])
        related_groups.setdefault(key, (runner, set()))[1].add(source)
    for runner, selected in related_groups.values():
        selected = sorted(selected)
        runs.append({"suffixes": runner["suffixes"], "cwd": runner["cwd"],
                     "tests": [p for p in selected if is_test(p)], "sources": selected,
                     "module": module_for(selected[0], modules), "mode": "related",
                     "env_id": runner["env_id"], "inputs": runner["inputs"],
                     "argv": render_argv(runner["argv"], [], root, runner["cwd"], selected, frozen_files=snapshot["files"], observer=observer, metadata=cache.metadata)})
    for runner, selected in groups.values():
        runs.append({"suffixes": runner["suffixes"], "cwd": runner["cwd"], "tests": selected, "sources": [],
                     "module": module_for(selected[0], modules), "mode": "named",
                     "env_id": runner["env_id"], "inputs": runner["inputs"],
                     "argv": render_argv(runner["argv"], selected, root, runner["cwd"], frozen_files=snapshot["files"], observer=observer, metadata=cache.metadata)})
    # 分析期间内容及元数据前后都要稳定，A→B→A 也不能发布依赖证明。
    from test_ledger import snapshot_changed
    if analysis_inputs is not None:
        missing = {path for proof in dependencies["tests"].values() for path in proof["files"]
                   if path not in snapshot["files"] and (root / path).is_file()}
        if missing:
            extra = tree_snapshot(root, paths=sorted(missing), observer=observer)
            snapshot["files"].update(extra["files"])
            snapshot["tokens"].update(extra["tokens"])
        analysis_inputs = sorted(set(analysis_inputs) | {p for p in snapshot["files"]
                                                       if not p.endswith(("/", "/@gitlink"))})
    if analysis_inputs is not None:
        from test_ledger import inventory_membership
        snapshot["files"]["@inventory"] = inventory_membership(root, inventory, analysis_inputs)
    snapshot["hash"] = digest({"files": snapshot["files"], "vcs_mode": snapshot["vcs_mode"]})
    after = tree_snapshot(root, explicit_inputs, paths=analysis_inputs,
                          observer=progress.observe("post_evidence") if progress else None)
    if snapshot_changed(snapshot, after):
        raise ScopeError("TREE_CHANGED：范围推导期间输入变化，请重新推导")
    if time.monotonic() > deadline:
        raise ScopeError("BUDGET_EXCEEDED：范围扫描时间超出预算")
    if progress:
        progress.actual["pre_evidence"]["elapsed_seconds"] = time.monotonic() - started
        progress.flush()
        progress.bind(digest([identity, runners, write_set, snapshot["hash"]]))
        progress.finish("PASS")
    # 只有前后内容一致才发布分析缓存，失效/混合树的分析不能污染后续恢复的原树。
    if len(_ANALYSIS_CACHE) >= 8:
        _ANALYSIS_CACHE.clear()
        _ANALYSIS_EXTRA.clear()
    extra_files = {p: value for p, value in snapshot["files"].items() if p not in initial_snapshot_paths}
    _ANALYSIS_CACHE[analysis_key] = analysis
    _ANALYSIS_EXTRA[analysis_key] = extra_files
    if pending_analysis is not None:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", dir=cache_file.parent, delete=False) as stream:
            json.dump({"key": analysis_key, "analysis": analysis, "extra_files": extra_files,
                       "checksum": digest([analysis, extra_files])}, stream)
            temporary = stream.name
        os.replace(temporary, cache_file)
    dependencies["tests"] = {test: dependencies["tests"][test] for test in sorted(tests)}
    validation_files = None
    if identity is not None and identity["mode"] == "light":
        relevant = set(changes) | tests
        for proof in dependencies["tests"].values():
            relevant.update(proof["files"])
            if proof["unknown"] or proof.get("runner_unknown"):
                # 未知加载不能靠窄集合伪造独立；对应运行模块内的源码/配置仍为真实输入。
                roots = {item["cwd"] for item in runs if set(item["tests"]) & tests}
                relevant.update(path for path in snapshot["files"] if any(within(path, base) for base in roots))
        if related:
            relevant.update(path for path in snapshot["files"] if any(within(path, runner["cwd"]) for _, runner in related))
        relevant.update(path for path in snapshot["files"] if is_configuration(path))
        validation_files = sorted(p for p in relevant if p != "@inventory" and not p.endswith(("/", "/@gitlink")))
        visible = {path: value for path, value in snapshot["files"].items()
                   if path in relevant or path.endswith("/@gitlink")
                   or any(within(path, declared) for declared in explicit_inputs)}
        from test_ledger import inventory_membership
        visible["@inventory"] = inventory_membership(root, inventory, validation_files)
        snapshot = dict(snapshot, files=visible, hash=digest({"files": visible, "vcs_mode": snapshot["vcs_mode"]}))
    documented = sorted(p for p in raw_changes if PurePosixPath(p).suffix in {".md", ".rst", ".txt"}
                        and (p.startswith("docs/") or PurePosixPath(p).name.lower().startswith(("readme", "changelog"))))
    unknown_changes = sorted(set(raw_changes) - set(changes) - set(documented))
    applicability = {"status": "REQUIRED", "reason": "本任务源码、测试、配置资源或验收规则需要行为验证", "paths": changes}
    if not changes and not acceptance_paths:
        if documented and not unknown_changes and all(p in document_inputs for p in documented):
            applicability = {"status": "NOT_APPLICABLE", "reason": "仅说明文档变更，未命中源码、测试、配置、资源声明或验收测试；无可执行行为变更",
                             "paths": documented, "content_hashes": {p: snapshot["files"].get(p) for p in documented}}
        else:
            applicability = {"status": "UNVERIFIED", "reason": "没有可证明不适用的本任务行为范围或存在无法分类的改动", "paths": unknown_changes}
    result = {"schema": SCHEMA, "since": since, "write_set": write_set, "runners": runners,
              "acceptance_paths": acceptance_paths, "applicability": applicability,
              "changed": changes, "tests": sorted(tests), "runs": runs,
              "unrunnable": sorted(tests - claimed) or ([p for p in changes if is_configuration(p)] if not runs else []),
              "mapping": mapping, "unmapped": unmapped,
              "modules": modules, "dependencies": dependencies, "tree_hash": snapshot["hash"],
              "analysis_version": tool_hash,
              "selection": {"proven": sorted(proven_tests), "conservative": sorted(conservative_tests),
                            "unanalysable": sorted(unmapped), "reason": "unknown dependency candidates require bounded execution"}}
    if identity is not None:
        result["execution_context"] = identity
    if validation_files is not None:
        result["validation_files"] = validation_files
    result["scope_hash"] = digest(result)
    return result


def version_context(root, context, manifest):
    """版本执行沿既有父上下文核真；唯一跨 root 场景是同仓固定提交 worktree。"""
    if context is None:
        return None
    try:
        raw = context if isinstance(context, dict) else json.loads(Path(context).read_text(encoding="utf-8"))
        owner = Path(raw["root"]).resolve()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ScopeError("版本 execution-context 不可读") from exc
    loaded = execution_context_data(owner, context)
    from execution_policy import validate_test_binding
    validate_test_binding(owner, loaded, manifest.get("version"), manifest.get("build"), manifest)
    root = Path(root).resolve()
    def common(path):
        value = os.fsdecode(git_output(path, "rev-parse", "--git-common-dir")).strip()
        return (path / value).resolve()
    if common(root) != common(owner) or resolve_since(root, "HEAD") != manifest.get("commit"):
        raise ScopeError("版本执行必须使用同仓 manifest.commit 固定的 worktree")
    return loaded


def derive_suite(root, runners, manifest, execution_context=None):
    """只把已冻结版本验收清单编译为现有 scope；绝不自动发现全仓测试。"""
    root = Path(root).resolve()
    if not isinstance(manifest, dict) or not isinstance(manifest.get("version"), str):
        raise ScopeError("版本范围必须提供明确 manifest/version")
    version = manifest["version"]
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", version):
        raise ScopeError("版本标识无效")
    baseline = manifest.get("acceptance_baseline")
    if not isinstance(baseline, dict):
        raise ScopeError("版本范围缺少正式验收 acceptance_baseline")
    path = relative_path(root, baseline.get("path"))
    if not path.startswith(f"docs/testing/{version}/") or not path.endswith(".json"):
        raise ScopeError("验收基线必须归属本版本 docs/testing/<version>/ 下 JSON")
    try:
        content = (root / path).read_bytes()
        data = json.loads(content)
    except (OSError, ValueError) as exc:
        raise ScopeError("正式版本验收基线不可读") from exc
    if hashlib.sha256(content).hexdigest() != baseline.get("sha256") or data.get("version") != version:
        raise ScopeError("验收基线 hash/version 不一致")
    def paths(key, required=False):
        values = manifest.get(key)
        if (not isinstance(values, list) or required and not values
                or not all(isinstance(p, str) for p in values) or len(values) != len(set(values))):
            raise ScopeError(f"manifest.{key} 必须是明确且无重复的文件清单")
        selected = sorted(relative_path(root, p) for p in values)
        if sorted(data.get(key, [])) != selected:
            raise ScopeError(f"manifest.{key} 未完整覆盖冻结验收基线")
        if any(not (root / p).is_file() for p in selected):
            raise ScopeError(f"manifest.{key} 只能列出现有文件，禁止目录/通配发现")
        return selected
    acceptance = paths("acceptance_tests", True)
    declared_dependencies = paths("dependencies")
    if not all(is_test(p) for p in acceptance):
        raise ScopeError("acceptance_tests 必须是明确测试文件")
    cases = data.get("cases")
    if (not isinstance(cases, list) or not cases or any(not isinstance(c, dict) or not isinstance(c.get("id"), str)
            or not isinstance(c.get("test_files"), list) or not c["test_files"]
            or not all(isinstance(p, str) for p in c["test_files"]) for c in cases)
            or len({c["id"] for c in cases}) != len(cases)
            or {p for c in cases for p in c["test_files"]} != set(acceptance)):
        raise ScopeError("正式验收用例 cases 必须完整且唯一映射 acceptance_tests")
    try:
        from build_unit_test import validate_case_index
        validate_case_index(root, manifest)
    except (ValueError, OSError) as exc:
        raise ScopeError(f"正式用例索引未完整覆盖：{exc}") from exc
    loaded = version_context(root, execution_context, manifest)
    identity = context_identity(Path(loaded["root"]), loaded) if loaded else None
    runners = validate_runners(runners, root)
    if any(r["mode"] != "named" for r in runners):
        raise ScopeError("版本验收必须显式选择测试文件，禁止 related 自动扩展")
    files = sorted(set(acceptance) | set(declared_dependencies))
    tests = sorted(p for p in files if is_test(p))
    modules = module_roots(files, runners)
    from test_ledger import tree_snapshot, snapshot_changed
    index = data.get("case_index", {}).get("path")
    index = relative_path(root, index)
    inputs = sorted({path, index, *(p for r in runners for p in r["inputs"])})
    before = tree_snapshot(root, inputs, paths=files)
    analysis = dependency_analysis(root, files, modules, runners, frozen_files=before["files"],
                                   frozen_tokens=before["tokens"], candidates=tests)
    declared = set(files)
    for test, proof in analysis["tests"].items():
        missing = set(proof["files"]) - declared
        if missing:
            raise ScopeError(f"版本清单遗漏必要依赖：{test}: {sorted(missing)}")
        # 显式文件清单无法证明动态/缺失本地导入完整；调用方必须补齐清单或提供可解析依赖。
        if any("未解析导入" in reason for reason in proof["unknown"]):
            raise ScopeError(f"版本清单依赖未闭合：{test}: {proof['unknown']}")
    groups = {}
    for test in tests:
        owners = [r for r in runners if within(test, r["cwd"]) and PurePosixPath(test).suffix in r["suffixes"]]
        depth = max((len(PurePosixPath(r["cwd"]).parts) for r in owners), default=-1)
        owners = [r for r in owners if len(PurePosixPath(r["cwd"]).parts) == depth]
        if len(owners) != 1:
            raise ScopeError(f"版本测试必须唯一归属一个运行器：{test}")
        runner = owners[0]
        key = digest(runner) if runner["batch"] else digest([runner, test])
        groups.setdefault(key, (runner, []))[1].append(test)
    runs = [{"suffixes": runner["suffixes"], "cwd": runner["cwd"], "tests": selected, "sources": [],
             "module": module_for(selected[0], modules), "mode": "named", "env_id": runner["env_id"],
             "inputs": sorted(set(inputs) | set(runner["inputs"])),
             "argv": render_argv(runner["argv"], selected, root, runner["cwd"], frozen_files=before["files"])}
            for runner, selected in groups.values()]
    if snapshot_changed(before, tree_snapshot(root, inputs, paths=files)):
        raise ScopeError("TREE_CHANGED：版本范围推导期间输入变化")
    result = {"schema": SCHEMA, "kind": "version", "manifest": manifest, "since": manifest.get("commit"),
              "write_set": files, "runners": runners, "changed": files, "tests": tests, "runs": runs,
              "unrunnable": [], "unmapped": [], "mapping": [], "modules": modules,
              "dependencies": analysis, "tree_hash": before["hash"], "validation_files": files,
              "execution_context": identity, "applicability": {"status": "REQUIRED", "reason": "冻结版本正式验收清单", "paths": tests}}
    result["scope_hash"] = digest(result)
    return result


def validate_scope(root, scope, execution_context=None):
    if not isinstance(scope, dict) or scope.get("schema") != SCHEMA:
        raise ScopeError("范围文件版本/结构错误，请重新运行 test_scope.py")
    unsigned = {k: v for k, v in scope.items() if k != "scope_hash"}
    if scope.get("scope_hash") != digest(unsigned):
        raise ScopeError("scope_hash 与范围内容不匹配")
    if scope.get("kind") == "version":
        current = derive_suite(root, scope.get("runners"), scope.get("manifest"), execution_context)
        if current != scope:
            raise ScopeError("版本范围与当前输入或正式验收清单不一致")
        return current
    if scope.get("execution_context") != context_identity(root, execution_context):
        raise ScopeError("范围 execution-context 与当前任务不一致；不能跨任务或 Sprint 使用")
    current = derive(root, scope.get("since"), scope.get("runners"), scope.get("write_set", []),
                     execution_context=execution_context)
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
    parser.add_argument("--execution-context", help="入口冻结上下文 JSON；light 不需要 Sprint")
    parser.add_argument("--runners-json", default="[]")
    parser.add_argument("--write-set", action="append", default=[])
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args(argv)
    try:
        out = self_check() if args.self_check else derive(Path(args.root).resolve(), args.since,
                                                          json.loads(args.runners_json), args.write_set,
                                                          args.execution_context)
        code = 0 if out.get("ok", True) else 1
    except (OSError, ValueError, TypeError) as exc:
        out, code = {"kind": "error", "status": getattr(exc, "status", "UNVERIFIED"), "error": str(exc)}, 2
        if getattr(exc, "details", None):
            out["details"] = exc.details
    print(json.dumps(out, ensure_ascii=True, sort_keys=True, indent=None if args.json else 2))
    return code


if __name__ == "__main__":
    sys.exit(main())
