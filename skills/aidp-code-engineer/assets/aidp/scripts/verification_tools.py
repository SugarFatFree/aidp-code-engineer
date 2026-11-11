#!/usr/bin/env python3
"""项目核验工具选择与命令分析；只消费既有授权，不执行、安装或保存任务状态。

inspect_command 保留实际 argv；discover_checks 从配置、开发说明和 CI 入口选择候选。
READY 仅表示分类/范围/已知副作用核验通过；调用方仍负责预算、执行及结果证据。
"""
from __future__ import annotations

import ast
import copy
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import sys
import xml.etree.ElementTree as ET


CONFIG_NAMES = ("pyproject.toml", "ruff.toml", ".ruff.toml", "setup.cfg", "tox.ini", "pytest.ini",
                ".pylintrc", "pylintrc", "mypy.ini", ".mypy.ini", "pyrightconfig.json",
                "package.json", "tsconfig.json", "eslint.config.js", "eslint.config.mjs",
                "eslint.config.cjs", ".eslintrc.json", ".eslintrc", "pom.xml", "build.gradle",
                "build.gradle.kts", "settings.gradle", "settings.gradle.kts", "gradle.properties",
                "uv.lock", "poetry.lock", "Pipfile", "Pipfile.lock", "requirements.txt", "requirements-dev.txt",
                "pnpm-lock.yaml", "package-lock.json", "yarn.lock", "gradle.lockfile")
DOCUMENT_NAMES = ("AGENTS.md", "CLAUDE.md", "README.md", "CONTRIBUTING.md", "DEVELOPMENT.md")
IGNORED = frozenset((".git", "node_modules", ".venv", "venv", "target", "build", "__pycache__", ".gradle"))
TOOLS = frozenset(("ruff", "pylint", "flake8", "mypy", "pyright", "eslint", "tsc", "pytest",
                   "mvn", "mvnw", "gradle", "gradlew", "shellcheck", "yamllint", "black", "isort", "git"))
WRITE_FLAGS = frozenset(("--fix", "--fix-only", "--unsafe-fixes", "--write", "--watch", "-w",
                         "--update", "--update-snapshots", "-u", "--fix-dry-run", "--output-file", "--output",
                         "--report-file", "--outputFile"))
CONFIG_FLAGS = frozenset(("--config", "--config-file", "--rcfile", "--project", "-p", "-c"))
VALUE_FLAGS = CONFIG_FLAGS | frozenset(("--select", "--ignore", "--extend-select", "--extend-ignore", "--target-version",
    "--output-format", "--line-length", "--format", "--python-version", "--python-executable", "--disable", "--enable",
    "--max-line-length", "--max-warnings", "--extension", "--ext", "--report", "--level", "--ignore-path", "--file",
    "--directory", "--jobs", "-j", "-k", "-m", "--rootdir", "--confcutdir", "--import-mode"))


def _inside(root, path):
    path = Path(path).resolve()
    if not path.is_relative_to(root):
        raise ValueError("核验路径越出项目 root")
    return path


def _rel(root, path):
    return Path(path).relative_to(root).as_posix()


class _ReadCallbackFailure(Exception):
    def __init__(self, error):
        self.error = error


class _SelectionReads:
    """只统计/转发读取；正文缓存和预算属于调用方，不建立第二套缓存。"""
    def __init__(self, callback):
        self.callback = callback
        self.requests = self.calls = self.reads = self.bytes_read = self.failures = 0
        self.paths = set()

    def __call__(self, path):
        path = Path(path)
        self.requests += 1
        self.paths.add(str(path.resolve()))
        if self.callback is not None:
            self.calls += 1
            try:
                value = self.callback(path)
                if not isinstance(value, str):
                    raise TypeError("read_text 回调必须返回 str")
                return value
            except Exception as exc:
                # 包装以越过分类器的 ValueError/OSError 处理；最外层原样抛出预算等异常。
                raise _ReadCallbackFailure(exc) from exc
        self.reads += 1
        try:
            data = path.read_bytes()
            self.bytes_read += len(data)
            return data.decode("utf-8")
        except OSError:
            self.failures += 1
            raise

    def cost(self, scope):
        return {"scope": scope, "read_requests": self.requests, "reader_calls": self.calls,
                "content_reads": self.reads if self.callback is None else None,
                "bytes_read": self.bytes_read if self.callback is None and not self.failures else None,
                "physical_cost_owner": "callback" if self.callback is not None else "selector",
                "read_files": sorted(self.paths), "external_tool_io": "unknown"}


def _project_files(root, cwd):
    """只读取对象所在模块及祖先配置；CI 只读常用入口，不扫描整个项目。"""
    result = []
    for directory in (cwd, *cwd.parents):
        if not directory.is_relative_to(root):
            break
        for dependency in sorted(directory.glob("requirements*.txt")):
            if dependency.is_file():
                result.append(_inside(root, dependency))
        for name in CONFIG_NAMES + DOCUMENT_NAMES:
            path = directory / name
            if path.is_file():
                result.append(_inside(root, path))
    for folder in (root / ".github/workflows", root / ".gitlab/ci"):
        if folder.is_dir():
            result.extend(_inside(root, p) for p in sorted(folder.iterdir()) if p.suffix in (".yaml", ".yml"))
    for name in (".gitlab-ci.yml", "Jenkinsfile", "Makefile"):
        if (root / name).is_file():
            result.append(root / name)
    return dict.fromkeys(result)


def _sources(root, files, read_text):
    rows = []
    for path in files:
        if path.name == "package.json":
            data = json.loads(read_text(path))
            for name, command in data.get("scripts", {}).items():
                if isinstance(command, str):
                    rows.append({"path": _rel(root, path), "location": "scripts." + name,
                                 "command": command, "cwd": _rel(root, path.parent)})
        elif path.name not in CONFIG_NAMES:
            for number, line in enumerate(read_text(path).splitlines(), 1):
                # 单行 shell 命令才可确定解释；复合 shell 留给人工核验。
                value = line.strip().strip("`").strip()
                value = re.sub(r"^(?:-\s*)?run:\s*[>|]?\s*", "", value).strip()
                value = re.sub(r"^\$\s+", "", value)
                try:
                    argv = shlex.split(value)
                except ValueError:
                    continue
                if argv and (Path(argv[0]).name in TOOLS | {"npm", "pnpm", "yarn", "bash", "sh", "docker"} or
                             re.fullmatch(r"python(?:3(?:\.\d+)?)?", Path(argv[0]).name)):
                    rows.append({"path": _rel(root, path), "location": "line:" + str(number),
                                 "command": value, "cwd": "." if ".github" in path.parts else _rel(root, path.parent)})
    return rows


def _environment_dependencies(executable, module=None):
    dependencies = {str(Path(executable).resolve())} if executable else set()
    if executable and "node_modules" in Path(executable).resolve().parts:
        binary = Path(executable).resolve()
        for directory in binary.parents:
            if directory.name == "node_modules":
                break
            if (directory / "package.json").is_file():
                for parent, dirs, names in os.walk(directory):
                    dirs[:] = [name for name in dirs if name not in IGNORED]
                    dependencies.update(str((Path(parent) / name).resolve()) for name in names
                                        if Path(name).suffix in (".js", ".cjs", ".mjs", ".json"))
                break
    if module:
        try:
            spec = importlib.util.find_spec(module)
            if spec and spec.origin and Path(spec.origin).is_file():
                dependencies.add(str(Path(spec.origin).resolve()))
            # 只枚举安装路径；metadata.files 会隐式读 RECORD，绕过预算读回调。
            for location in (spec.submodule_search_locations or ()) if spec else ():
                for parent, dirs, names in os.walk(location):
                    dirs[:] = [name for name in dirs if name not in IGNORED]
                    dependencies.update(str((Path(parent) / name).resolve()) for name in names
                                        if Path(name).suffix in (".py", ".so", ".pyd"))
            if spec and spec.origin and Path(spec.origin).is_file():
                site = Path(spec.origin).parent.parent if spec.submodule_search_locations else Path(spec.origin).parent
                prefix = re.sub(r"[-_.]+", "-", module).lower() + "-"
                for metadata in site.glob("*.dist-info"):
                    if re.sub(r"[-_.]+", "-", metadata.name).lower().startswith(prefix):
                        dependencies.update(str((metadata / name).resolve()) for name in ("METADATA", "RECORD", "entry_points.txt")
                                            if (metadata / name).is_file())
        except (ImportError, ValueError, OSError):
            pass
    return sorted(dependencies)


def _positions(args, skip=()):
    values, configs = [], []
    index = 0
    while index < len(args):
        token = args[index]
        key, equals, value = token.partition("=")
        if key in VALUE_FLAGS:
            if not equals:
                index += 1
                value = args[index] if index < len(args) else ""
            if key in CONFIG_FLAGS and value:
                configs.append(value)
        elif not token.startswith("-") and token not in skip:
            values.append(token)
        index += 1
    return values, configs


def _files(root, cwd, objects):
    found = set()
    for name in objects:
        # pytest node ids identify a file plus a selection, not a filesystem path.
        path = _inside(root, cwd / name.split("::", 1)[0])
        if path.is_file():
            found.add(_rel(root, path))
        elif path.is_dir():
            for parent, dirs, names in os.walk(path):
                dirs[:] = sorted(d for d in dirs if d not in IGNORED and not (Path(parent) / d).is_symlink())
                for item in names:
                    candidate = _inside(root, Path(parent) / item)
                    if candidate.is_file():
                        found.add(_rel(root, candidate))
                        if len(found) > 10000:
                            raise ValueError("对象超过 10000 文件；需先细化模块范围")
        else:
            raise ValueError("检查对象不存在：" + name)
    return sorted(found)


def _typescript_files(root, config, data, read_text):
    directory = config.parent
    extensions = (".ts", ".tsx", ".mts", ".cts") + ((".js", ".jsx") if data.get("compilerOptions", {}).get("allowJs") else ())
    excludes = list(data.get("exclude", ("node_modules", "bower_components", "jspm_packages")))
    out_dir = data.get("compilerOptions", {}).get("outDir")
    if out_dir:
        excludes.append(out_dir)
    excluded = set()
    for pattern in excludes:
        for item in directory.glob(pattern):
            if item.is_dir():
                excluded.update(item.rglob("*"))
            else:
                excluded.add(item)
    files = set()
    for name in data.get("files", []):
        files.add(_inside(root, directory / name))
    for pattern in data.get("include", [] if "files" in data else ["**/*"]):
        for item in directory.glob(pattern):
            if item.is_file() and item.suffix in extensions and item not in excluded and not any(part in IGNORED for part in item.relative_to(directory).parts):
                files.add(_inside(root, item))
    # 本地静态 import 的直接/传递输入也属于项目类型检查，不仅是 include 初始文件。
    pending = list(files)
    while pending:
        path = pending.pop()
        for match in re.finditer(r"(?:from\s+|import\s*\(?\s*|require\s*\(\s*)['\"](\.[^'\"]+)['\"]", read_text(path)):
            base = path.parent / match.group(1)
            candidates = [base, *[Path(str(base) + ext) for ext in extensions], base / "index.ts", base / "index.tsx"]
            target = next((p for p in candidates if p.is_file()), None)
            if target is not None:
                target = _inside(root, target)
                if target not in files:
                    files.add(target)
                    pending.append(target)
        if len(files) > 10000:
            raise ValueError("TypeScript 依赖对象超过 10000 文件；需细化范围")
    return sorted(_rel(root, path) for path in files)


def _inline(args, cwd):
    if len(args) != 2 or args[0] != "-c":
        raise ValueError("未知 Python 包装脚本不能作为静态检查")
    tree = ast.parse(args[1])
    expanded = []
    for statement in tree.body:
        if not isinstance(statement, ast.Expr) or not isinstance(statement.value, ast.ListComp):
            expanded.append(statement)
            continue
        comp = statement.value
        if len(comp.generators) != 1:
            raise ValueError("内联 syntax 只接受单层字面量路径列表")
        generator = comp.generators[0]
        if (generator.is_async or not isinstance(generator.target, ast.Name) or
                not isinstance(generator.iter, (ast.List, ast.Tuple)) or
                any(not isinstance(item, ast.Constant) or not isinstance(item.value, str) for item in generator.iter.elts)):
            raise ValueError("内联 syntax 路径必须是静态字面量列表")
        variable = generator.target.id
        is_file = ast.dump(ast.parse("Path(" + variable + ").is_file()", mode="eval").body)
        suffix = ast.dump(ast.parse("Path(" + variable + ").suffix == '.py'", mode="eval").body)
        predicates = []
        for condition in generator.ifs:
            conditions = condition.values if isinstance(condition, ast.BoolOp) and isinstance(condition.op, ast.And) else [condition]
            for item in conditions:
                shape = ast.dump(item)
                if shape not in (is_file, suffix):
                    raise ValueError("内联 syntax 列表过滤仅接受 is_file 与 .py suffix 条件")
                predicates.append(shape)
        for value in generator.iter.elts:
            path = cwd / value.value
            if any(shape == is_file and not path.is_file() or shape == suffix and path.suffix != ".py" for shape in predicates):
                continue
            class LiteralPath(ast.NodeTransformer):
                def visit_Name(self, node):
                    return ast.copy_location(ast.Constant(value=value.value), node) if node.id == variable else node
            expanded.append(ast.Expr(value=LiteralPath().visit(copy.deepcopy(comp.elt))))
    tree.body = expanded
    node_types = (ast.Module, ast.Import, ast.ImportFrom, ast.alias, ast.Expr, ast.Call, ast.Name,
                  ast.Attribute, ast.Constant, ast.Load, ast.keyword)
    paths, read_paths = [], []
    for node in ast.walk(tree):
        if not isinstance(node, node_types):
            raise ValueError("内联 syntax 只接受直接语法读取表达式")
        if isinstance(node, ast.Import) and any(a.name not in ("ast", "pathlib", "tokenize") or a.asname for a in node.names):
            raise ValueError("内联 syntax 导入未知模块或别名")
        if isinstance(node, ast.ImportFrom) and (node.module != "pathlib" or any(a.name != "Path" or a.asname for a in node.names)):
            raise ValueError("内联 syntax 只支持 from pathlib import Path")
        if isinstance(node, ast.Attribute) and node.attr not in ("parse", "read", "read_text", "read_bytes", "Path"):
            raise ValueError("内联 syntax 含未知属性访问")
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ""
            if name not in ("open", "Path", "parse", "read", "read_text", "read_bytes", "compile", "print", "len", "str"):
                raise ValueError("内联 syntax 含未知调用")
            if name in ("parse", "compile"):
                if name == "parse" and not (isinstance(node.func, ast.Attribute) and
                        isinstance(node.func.value, ast.Name) and node.func.value.id == "ast"):
                    raise ValueError("内联 syntax 只接受 ast.parse 或 builtin compile")
                source = node.args[0] if node.args else None
                if not (isinstance(source, ast.Call) and isinstance(source.func, ast.Attribute) and
                        source.func.attr in ("read", "read_text", "read_bytes") and not source.args):
                    raise ValueError("语法检查必须直接解析完整文件读取结果，不能用常量/局部读取冒充文件检查")
                if any(k.arg != "encoding" for k in source.keywords) or (source.func.attr != "read_text" and source.keywords):
                    raise ValueError("语法检查读取参数尚未核验")
                reader = source.func.value
                if not isinstance(reader, ast.Call) or not reader.args:
                    raise ValueError("语法检查读取链必须连接到明确文件")
                reader_name = reader.func.id if isinstance(reader.func, ast.Name) else reader.func.attr if isinstance(reader.func, ast.Attribute) else ""
                if reader_name != ("open" if source.func.attr == "read" else "Path"):
                    raise ValueError("语法检查只接受 open.read 或 Path.read_text/read_bytes")
                filename = reader.args[0]
                if not isinstance(filename, ast.Constant) or not isinstance(filename.value, str):
                    raise ValueError("语法检查文件必须为可核对常量")
                paths.append(filename.value)
            if name in ("open", "Path"):
                if not node.args or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
                    raise ValueError("内联 syntax 文件路径必须为可核对常量")
                if name == "Path" and (len(node.args) != 1 or node.keywords):
                    raise ValueError("内联 syntax Path 只接受单一明确路径")
                read_paths.append(node.args[0].value)
            if name == "open":
                if len(node.args) > 2 or any(k.arg not in ("mode", "encoding") for k in node.keywords):
                    raise ValueError("内联 syntax 禁止 opener/未知读取参数")
                modes = list(node.args[1:]) + [k.value for k in node.keywords if k.arg == "mode"]
                if any(not isinstance(m, ast.Constant) or m.value not in ("r", "rb", "rt") for m in modes):
                    raise ValueError("内联 syntax 禁止写文件")
    if not paths:
        raise ValueError("内联 syntax 必须实际检查明确文件")
    if not set(read_paths) <= set(paths):
        raise ValueError("内联 syntax 含未接入语法检查的数据读取；不能将其计为已检查文件")
    return paths


def _maven(root, cwd, args, read_text):
    if any(os.environ.get(key) for key in ("MAVEN_OPTS", "MAVEN_ARGS", "JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS")):
        raise ValueError("Maven/JVM 环境附加参数可能加载 agent/扩展，尚未核验")
    for directory in (cwd, *cwd.parents):
        if not directory.is_relative_to(root):
            break
        if any((directory / ".mvn" / name).exists() for name in ("extensions.xml", "maven.config", "jvm.config")):
            raise ValueError("Maven 祖先 .mvn 隐式扩展/参数尚未核验")
    forbidden = {"-am", "--also-make", "-amd", "--also-make-dependents", "-P", "--activate-profiles"}
    if any(a.split("=", 1)[0] in forbidden or a.startswith("-P") for a in args):
        raise ValueError("Maven reactor/profile 扩大范围尚未核验")
    pom, modules, goals = cwd / "pom.xml", [], []
    index = 0
    while index < len(args):
        token = args[index]
        if token in ("-f", "--file", "-pl", "--projects"):
            index += 1
            if index >= len(args):
                raise ValueError("Maven 缺少选项值")
            if token in ("-f", "--file"):
                pom = _inside(root, cwd / args[index])
            else:
                modules = args[index].split(",")
        elif token not in ("-o", "--offline", "-B", "--batch-mode", "-q", "--quiet", "-DskipTests", "-Dmaven.test.skip=true"):
            if token.startswith("-"):
                raise ValueError("Maven 未核验选项：" + token)
            goals.append(token)
        index += 1
    if goals != ["compile"]:
        raise ValueError("Maven 仅对单一明确 compile 目标提供静态分类")
    if not set(args) & {"-o", "--offline"}:
        raise ValueError("Maven 需 offline；不得自动安装/下载依赖")
    if pom.is_dir():
        pom /= "pom.xml"
    selected = [_inside(root, pom.parent / module / "pom.xml") for module in modules] if modules else [pom]
    dependencies = set()
    seen = set()

    def inspect(path):
        path = _inside(root, path)
        if path in seen:
            return
        seen.add(path)
        dependencies.add(_rel(root, path))
        tree = ET.fromstring(read_text(path))
        # 忽略命名空间以兼容标准 POM 和小型测试片段。
        for element in tree.iter():
            element.tag = element.tag.rsplit("}", 1)[-1]
        parent = tree.find("parent")
        if parent is not None:
            relative = parent.find("relativePath")
            if relative is not None and not relative.text:
                raise ValueError("Maven 外部 parent 生命周期不可核验")
            ancestor = path.parent / ((relative.text if relative is not None else None) or "../pom.xml")
            if not ancestor.is_file():
                raise ValueError("Maven parent POM 缺失，生命周期不可核验")
            inspect(ancestor)
        if tree.find("profiles") is not None or tree.find("build/extensions") is not None:
            raise ValueError("Maven profiles/extensions 可改变生命周期，尚未核验")
        for plugin in tree.findall(".//plugin"):
            artifact = plugin.findtext("artifactId", "")
            group = plugin.findtext("groupId", "org.apache.maven.plugins")
            if group != "org.apache.maven.plugins" or artifact not in ("maven-compiler-plugin", "maven-resources-plugin", "maven-surefire-plugin", "maven-jar-plugin", "maven-clean-plugin", "maven-install-plugin", "maven-deploy-plugin"):
                raise ValueError("Maven 生命周期含未核验插件（exec/frontend/服务等）：" + artifact)
            if artifact not in ("maven-compiler-plugin", "maven-resources-plugin") and plugin.find("executions") is not None:
                raise ValueError("Maven 插件重绑生命周期尚未核验：" + artifact)
            if plugin.find("configuration") is not None:
                raise ValueError("Maven 插件自定义配置/processor/输出位置尚未核验：" + artifact)
        if tree.find("build/sourceDirectory") is not None or tree.find("build/directory") is not None:
            raise ValueError("Maven 自定义源码/输出边界尚未核验")
        if path in selected and tree.find("modules") is not None:
            raise ValueError("Maven 聚合模块必须用 -pl 明确选择，不自动构建全部 reactor")
        for extra in (path.parent / ".mvn/extensions.xml", path.parent / ".mvn/maven.config", path.parent / ".mvn/jvm.config"):
            if extra.exists():
                dependencies.add(_rel(root, extra))
                raise ValueError("Maven 隐式扩展/参数尚未核验：" + _rel(root, extra))
    inspect(pom)
    for path in selected:
        inspect(path)
    return [_rel(cwd, p.parent / "src/main") for p in selected], sorted(dependencies)


def _gradle(root, cwd, args, read_text):
    if any(os.environ.get(key) for key in ("GRADLE_OPTS", "JAVA_OPTS", "JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS")):
        raise ValueError("Gradle/JVM 环境附加参数可能加载 agent/扩展，尚未核验")
    user_home = Path(os.environ.get("GRADLE_USER_HOME", str(Path.home() / ".gradle")))
    if (any((user_home / name).exists() for name in ("init.gradle", "init.gradle.kts", "gradle.properties")) or
            (user_home / "init.d").is_dir() and any((user_home / "init.d").iterdir())):
        raise ValueError("Gradle 用户级 init/配置可附加任意任务，尚未核验")
    tasks = [a for a in args if not a.startswith("-")]
    if tasks != ["compileJava"] or any(a not in ("compileJava", "--offline", "--no-daemon", "--console=plain", "--quiet", "-q") for a in args):
        raise ValueError("Gradle 仅对当前明确模块的 compileJava 目标分类")
    if "--offline" not in args:
        raise ValueError("Gradle 需 offline；不得自动安装/下载依赖")
    build = next((cwd / name for name in ("build.gradle", "build.gradle.kts") if (cwd / name).is_file()), None)
    if build is None:
        raise ValueError("Gradle 构建配置缺失")
    dependencies = [_rel(root, build)]
    for directory in (cwd, *cwd.parents):
        if not directory.is_relative_to(root):
            break
        for name in ("buildSrc", "gradle.properties", "init.gradle", "init.gradle.kts"):
            if (directory / name).exists():
                raise ValueError("Gradle 隐式构建逻辑/配置尚未核验：" + name)
        for name in ("settings.gradle", "settings.gradle.kts"):
            settings = directory / name
            if settings.exists():
                dependencies.append(_rel(root, settings))
                if not re.fullmatch(r"\s*(?:rootProject\.name\s*=\s*['\"][\w.-]+['\"]\s*;?\s*)?", read_text(settings)):
                    raise ValueError("Gradle settings/includeBuild 动态逻辑尚未核验")
    text = re.sub(r"(?m)//[^\n]*$", "", read_text(build)).strip()
    # Gradle 是任意代码 DSL；只承认这个小型声明子集，不用危险关键词黑名单伪装沙箱。
    text = re.sub(r"plugins\s*\{\s*(?:(?:id\s*\(?\s*['\"]java(?:-library)?['\"]\s*\)?|java)\s*;?\s*)+\}", "", text)
    text = re.sub(r"(?:group|version|sourceCompatibility|targetCompatibility)\s*=\s*['\"][\w.-]+['\"]\s*;?", "", text)
    text = re.sub(r"repositories\s*\{\s*mavenCentral\(\)\s*\}", "", text)
    text = re.sub(r"dependencies\s*\{\s*(?:(?:implementation|compileOnly|testImplementation)\s*\(?\s*['\"][\w.:-]+['\"]\s*\)?\s*;?\s*)*\}", "", text)
    if text.strip():
        raise ValueError("Gradle 动态任务/exec/frontend/build 附加逻辑尚未核验")
    return ["src/main"], dependencies


def _shell_argv(command):
    if any(char in command for char in ("$", "`", "\n", "\r")):
        raise ValueError("shell 动态替换/多行逻辑尚未核验")
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    tokens = list(lexer)
    if not tokens or any(token in ("&&", "||", ";", "|", ">", ">>", "<", "&", "(", ")") for token in tokens):
        raise ValueError("shell 仅接受单一直接命令，不解释管道/重定向/复合逻辑")
    return tokens[1:] if tokens[0] == "exec" else tokens


def _container(root, cwd, args):
    if not args or args[0] != "run":
        raise ValueError("容器只接受一次性 run 静态检查")
    values, flags, index = {}, set(), 1
    while index < len(args) and args[index].startswith("-"):
        key, equals, value = args[index].partition("=")
        if key in ("--rm", "--read-only") and not equals:
            flags.add(key)
        elif key in ("--pull", "--network", "--entrypoint", "--volume", "-v", "--workdir", "-w"):
            if not equals:
                index += 1
                if index >= len(args):
                    raise ValueError("容器选项缺少值")
                value = args[index]
            key = {"-v": "--volume", "-w": "--workdir"}.get(key, key)
            if key in values:
                raise ValueError("容器重复选项/多重挂载尚未核验")
            values[key] = value
        else:
            raise ValueError("容器未知/服务/特权/宿主环境选项尚未核验：" + key)
        index += 1
    if flags != {"--rm", "--read-only"} or values.get("--pull") != "never" or values.get("--network") != "none":
        raise ValueError("容器必须 --rm --read-only --pull=never --network=none，不自动下载镜像或启动服务")
    if index >= len(args) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./:@-]*", args[index]):
        raise ValueError("容器缺少明确镜像")
    image, command = args[index], args[index + 1:]
    entrypoint = values.get("--entrypoint")
    if entrypoint not in ("ruff", "mypy", "pyright", "pylint", "eslint", "tsc"):
        raise ValueError("容器必须显式指定已知静态工具 entrypoint，不能信任镜像隐式入口")
    volume = values.get("--volume", "").split(":")
    if len(volume) != 3 or volume[2] != "ro" or not Path(volume[0]).is_absolute():
        raise ValueError("容器需单一绝对宿主项目目录到容器的只读 ro 挂载；命名 volume 不映射项目输入")
    host = _inside(root, cwd / volume[0])
    target = Path(volume[1])
    if not host.is_dir() or not target.is_absolute() or ".." in target.parts or target == Path("/") or "docker.sock" in volume[0]:
        raise ValueError("容器宿主路径/挂载目标尚未核验")
    if values.get("--workdir") != str(target):
        raise ValueError("容器 workdir 必须与只读项目挂载目标一致")
    translated = []
    for token in command:
        if token.startswith("/"):
            path = Path(token)
            if not path.is_relative_to(target):
                raise ValueError("容器命令引用了未知挂载外路径")
            token = path.relative_to(target).as_posix()
        elif "=" in token and token.split("=", 1)[1].startswith("/"):
            key, value = token.split("=", 1)
            path = Path(value)
            if not path.is_relative_to(target):
                raise ValueError("容器配置引用了未知挂载外路径")
            token = key + "=" + path.relative_to(target).as_posix()
        translated.append(token)
    return [entrypoint, *translated], host, {"image": image, "entrypoint": entrypoint, "host_path": _rel(root, host),
                                            "container_path": str(target), "pull": "never", "network": "none",
                                            "run_image_index": index + 1}


def inspect_command(root, argv, *, allowed_actions=(), scope_paths=(), cwd=None, read_text=None, read_cost=None):
    """项目读取经 read_text(Path)->str；预算异常原样传播，默认独立读取明确报告成本。"""
    reader = _SelectionReads(read_text)
    try:
        result = _inspect_command(root, argv, allowed_actions=allowed_actions, scope_paths=scope_paths,
                                  cwd=cwd, read_text=reader)
    except _ReadCallbackFailure as exc:
        raise exc.error
    finally:
        cost = reader.cost("inspection")
        if read_cost is not None:
            read_cost.update(cost)
    result["selection_read_cost"] = cost
    return result


def _inspect_command(root, argv, *, allowed_actions=(), scope_paths=(), cwd=None, read_text, _depth=0):
    """返回可审计的分类结果；绝不因为配置/命令名字/marker 而增授 action。"""
    root = Path(root).resolve()
    cwd = _inside(root, root / (cwd or "."))
    if not isinstance(argv, (list, tuple)) or not argv or any(not isinstance(a, str) or not a for a in argv):
        raise ValueError("argv 必须为非空字符串数组")
    result = {"argv": list(argv), "cwd": _rel(root, cwd), "category": "unknown", "required_action": "static",
              "status": "UNVERIFIED", "reason": "未知工具或包装脚本，未核验", "command_sources": [],
              "config_dependencies": [], "objects": [], "object_count": 0, "checked_files": [], "checked_file_count": 0,
              "expanded_scope_reason": None, "side_effects": [], "available": False, "syntax_only": False,
              "unit_tests_executed": False, "environment_probes": [], "execution_argv": list(argv),
              "selection_roots": [], "checked_suffixes": None}
    name = Path(argv[0]).name.lower()
    args = list(argv[1:])
    executable = shutil.which(argv[0])
    if executable is None and (cwd / argv[0]).is_file() and os.access(cwd / argv[0], os.X_OK):
        executable = str(cwd / argv[0])
    result["environment"] = {"executable": executable, "available": bool(executable), "reason": None if executable else "工具不可用：" + argv[0]}
    result["available"] = bool(executable)
    result["environment"]["dependency_files"] = _environment_dependencies(executable)
    selected_typescript_files = None
    try:
        if _depth > 4:
            raise ValueError("包装命令递归过深或成环")
        files = _project_files(root, cwd)
        sources = _sources(root, files, read_text)
        result["config_dependencies"] = sorted(_rel(root, p) for p in files if p.name in CONFIG_NAMES or p.match("requirements*.txt"))
        result["command_sources"] = [s for s in sources if shlex.split(s["command"]) == list(argv)]
        if not result["command_sources"]:
            result["command_sources"] = [{"path": None, "location": "explicit-argv", "command": shlex.join(argv), "cwd": result["cwd"]}]
        if name in ("bash", "sh", "docker"):
            dependency, container = None, None
            inner_cwd = cwd
            if name == "docker":
                inner, inner_cwd, container = _container(root, cwd, args)
            elif len(args) == 2 and args[0] == "-c":
                inner = _shell_argv(args[1])
            elif len(args) == 1 and not args[0].startswith("-"):
                dependency = _inside(root, cwd / args[0])
                lines = [line.strip() for line in read_text(dependency).splitlines() if line.strip() and not line.lstrip().startswith("#")]
                if len(lines) != 1:
                    raise ValueError("shell 文件仅接受一条可解析静态命令；其他逻辑尚未核验")
                inner = _shell_argv(lines[0])
            else:
                raise ValueError("shell 仅接受 -c 单命令或明确的单命令脚本，不加载 login/profile")
            checked = _inspect_command(root, inner, allowed_actions=allowed_actions, scope_paths=scope_paths, read_text=read_text,
                                      cwd=_rel(root, inner_cwd), _depth=_depth + 1)
            if checked["category"] not in ("syntax", "lint", "typecheck", "unknown"):
                raise ValueError("该包装入口仅承载纯静态检查，不能借用为 test/build/服务授权")
            checked["argv"] = list(argv)
            if container is None and "container" not in checked["environment"]:
                checked["execution_argv"] = list(argv)
            checked["cwd"] = result["cwd"]
            checked["command_sources"] = result["command_sources"]
            if dependency is not None:
                checked["command_sources"] = [{"path": _rel(root, dependency), "location": "single-command-script",
                                              "command": shlex.join(inner), "cwd": result["cwd"]}]
            checked["config_dependencies"] = sorted(set(checked["config_dependencies"]) | {s["path"] for s in checked["command_sources"] if s["path"]})
            checked["environment"]["launcher"] = executable
            checked["environment"]["dependency_files"] = sorted(set(checked["environment"].get("dependency_files", [])) | set(_environment_dependencies(executable)))
            if container is not None:
                checked["environment"]["container"] = container
                checked["execution_argv"] = list(argv)
                image = container["image"]
                if not re.fullmatch(r"(?:[^\s]+@)?sha256:[a-fA-F0-9]{64}", image):
                    checked["environment_probes"] = [{"kind": "docker-image-id", "argv": [argv[0], "image", "inspect", "--format", "{{.Id}}", image],
                                                      "image": image, "run_image_index": container["run_image_index"]}]
                checked["environment"]["executable"] = executable
                checked["environment"]["dependency_files"] = _environment_dependencies(executable)
                checked["available"] = bool(executable)
                checked["environment"]["available"] = bool(executable)
                # 宿主没有 Ruff 不代表已存在镜像中没有 Ruff；never 禁止安装，实跑缺镜像保留原错误。
                if checked["status"] in ("READY", "ENV_UNAVAILABLE"):
                    checked.update(status="READY" if executable else "ENV_UNAVAILABLE",
                                   reason="一次性本地镜像静态命令已分类；镜像/内层工具须由实跑证据确认" if executable else "容器工具不可用：" + argv[0])
                checked["side_effects"] = ["创建并删除一次性容器；项目只读挂载，禁网且不拉取镜像"]
            elif not executable and checked["status"] == "READY":
                checked.update(status="ENV_UNAVAILABLE", available=False, reason="shell 工具不可用：" + argv[0])
            return checked
        if any(any(c in a for c in ("\n", "\x00")) for a in argv) or any(a in ("&&", "||", ";", "|", ">", "&") for a in args):
            raise ValueError("不解释复合 shell/重定向命令")
        if any(a.split("=", 1)[0] in WRITE_FLAGS for a in args) or (name not in ("mvn", "mvnw") and "-o" in args):
            result["status"] = "UNAUTHORIZED"
            raise ValueError("只读检查禁止自动修复、格式写回或 watch")
        if name in ("npm", "pnpm", "yarn"):
            script_name = args[1] if len(args) == 2 and args[0] in ("run", "run-script") else None
            package = cwd / "package.json"
            if script_name is None or not package.is_file():
                raise ValueError("仅接受当前 package.json 的明确脚本入口")
            scripts = json.loads(read_text(package)).get("scripts", {})
            if any(key in scripts for key in ("pre" + script_name, "post" + script_name)):
                raise ValueError("包脚本含 pre/post 生命周期，尚未核验")
            command = scripts.get(script_name)
            if not isinstance(command, str):
                raise ValueError("包脚本不存在")
            inner = _shell_argv(command)
            if inner:
                local_binary = cwd / "node_modules/.bin" / inner[0]
                if "/" not in inner[0] and local_binary.is_file() and os.access(local_binary, os.X_OK):
                    _inside(root, local_binary)
                    inner[0] = str(local_binary)
            if not inner or Path(inner[0]).name in ("npm", "pnpm", "yarn"):
                raise ValueError("嵌套包脚本尚未核验")
            checked = _inspect_command(root, inner, allowed_actions=allowed_actions, scope_paths=scope_paths, read_text=read_text, cwd=result["cwd"], _depth=_depth + 1)
            checked.update(argv=list(argv), command_sources=[{"path": _rel(root, package), "location": "scripts." + script_name,
                "command": command, "cwd": result["cwd"]}])
            if "container" not in checked["environment"]:
                checked["execution_argv"] = list(argv)
            checked["config_dependencies"] = sorted(set(checked["config_dependencies"]) | {_rel(root, package)})
            if not executable and checked["status"] == "READY":
                checked.update(status="ENV_UNAVAILABLE", available=False, reason="包管理器不可用：" + argv[0])
            checked["environment"]["launcher"] = executable
            checked["environment"]["dependency_files"] = sorted(set(checked["environment"].get("dependency_files", [])) | set(_environment_dependencies(executable)))
            return checked
        python_module = None
        if re.fullmatch(r"(?:python|pypy)(?:\d+(?:\.\d+)*)?", name):
            args = [a for a in args if a not in ("-B", "-I", "-S")]
            if args[:1] == ["-m"] and len(args) > 1:
                python_module, args = args[1], args[2:]
                name = python_module
                if name not in TOOLS | {"unittest"}:
                    raise ValueError("未知 Python 模块不能当作静态检查")
                # 不 import 项目插件，也不执行工具来探测安装情况。
                if Path(executable or "").resolve() == Path(sys.executable).resolve():
                    try:
                        installed = importlib.util.find_spec(name) is not None
                    except (ValueError, ImportError):
                        installed = False
                    result["environment"]["dependency_files"] = _environment_dependencies(executable, name)
                    if not installed:
                        result.update(available=False)
                        result["environment"].update(available=False, reason="Python 模块不可用：" + name)
                else:
                    raise ValueError("其他 Python 解释器的模块可用性尚未核验")
            else:
                objects = _inline(args, cwd)
                name = "python-syntax"
        if name in ("mvnw", "gradlew"):
            raise ValueError("构建 wrapper 可下载工具或运行脚本，需先核验；不自动安装")
        if name in ("mvn", "gradle"):
            result["category"] = "compile"
            objects, dependencies = (_maven if name == "mvn" else _gradle)(root, cwd, args, read_text)
            result["config_dependencies"] = sorted(set(result["config_dependencies"]) | set(dependencies))
            result["side_effects"] = ["工具自己的编译输出/缓存；不自动修改源码、格式或配置"]
        elif name == "python-syntax":
            result.update(category="syntax", syntax_only=True)
        elif name == "git" and args[:2] == ["diff", "--check"]:
            if len(args) != 2:
                raise ValueError("git diff --check 额外参数的对象边界尚未核验")
            result["category"], objects = "lint", list(scope_paths)
        elif name in TOOLS | {"unittest"}:
            if any(a.split("=", 1)[0] in ("--version", "--help", "-h", "--show-files", "--show-settings", "--listFilesOnly", "--showConfig", "--collect-only", "--co") for a in args):
                raise ValueError("信息/收集命令未实际执行所声明检查")
            if name == "ruff" and (not args or args[0] not in ("check", "format") or args[0] == "format" and "--check" not in args):
                raise ValueError("Ruff 仅接受 check 或 format --check")
            if name in ("black", "isort") and not set(args) & {"--check", "--check-only"}:
                raise ValueError("格式工具必须显式 check，禁止写回")
            if name == "tsc" and ("--noEmit" not in args or any(a in ("false", "--build", "-b", "--watch") for a in args)):
                raise ValueError("tsc 必须 --noEmit，禁止 build/watch 或反向覆盖")
            if name in ("pylint", "mypy") and any(a.split("=", 1)[0] in ("--init-hook", "--load-plugins", "--plugins") for a in args):
                raise ValueError("动态检查插件/启动 hook 尚未核验")
            result["category"] = "related-test" if name in ("pytest", "unittest") else "typecheck" if name in ("mypy", "pyright", "tsc") else "lint"
            result["required_action"] = "related-test" if result["category"] == "related-test" else "static"
            objects, configs = _positions(args, skip=("check", "format", "discover"))
            for config in configs:
                path = _inside(root, cwd / config)
                if path.is_dir() and name == "tsc":
                    path /= "tsconfig.json"
                if not path.is_file():
                    raise ValueError("显式配置不存在或为未核验内联覆盖：" + config)
                result["config_dependencies"].append(_rel(root, path))
            if name == "tsc":
                config = _inside(root, cwd / (configs[0] if configs else "tsconfig.json"))
                if config.is_dir():
                    config /= "tsconfig.json"
                if config.is_file():
                    data = json.loads(read_text(config))
                    if data.get("extends") or data.get("references"):
                        raise ValueError("tsconfig extends/references 依赖边界尚未核验")
                    result["config_dependencies"].append(_rel(root, config))
                    selected_typescript_files = _typescript_files(root, config, data, read_text)
                    objects = [os.path.relpath(config.parent, cwd)]
                    result["expanded_scope_reason"] = "TypeScript 项目模式按 tsconfig 模块检查，不能把单文件冒充整个项目类型检查"
            if name == "unittest":
                if "discover" in args:
                    raise ValueError("unittest discover 范围需由既有相关测试执行器核验；优先明确模块")
                selected = []
                for item in objects:
                    parts = item.split(".")
                    match = next((cwd.joinpath(*parts[:count]).with_suffix(".py") for count in range(len(parts), 0, -1)
                                  if cwd.joinpath(*parts[:count]).with_suffix(".py").is_file()), None)
                    if match is None:
                        raise ValueError("unittest 未找到明确测试模块：" + item)
                    selected.append(_rel(cwd, match))
                objects = selected
            if name in ("pytest", "unittest") and any(not (cwd / item.split("::", 1)[0]).is_file() for item in objects):
                raise ValueError("相关测试仅接受明确测试文件/node id/module；目录或全项目发现不能自行扩大授权")
            if not objects:
                if result["category"] == "related-test":
                    raise ValueError("相关测试必须明确测试文件/node id，项目配置不是全量测试授权")
                objects = ["."]
                result["expanded_scope_reason"] = "命令未指定文件，实际对象为当前模块"
            review_configs = dict.fromkeys(result["config_dependencies"]) if name in ("ruff", "pylint", "mypy") else ()
            for filename in review_configs:
                text = read_text(root / filename)
                if name == "ruff" and re.search(r'''(?m)^\s*["']?fix(?:-only)?["']?\s*=\s*true\b''', text) and "--no-fix" not in args:
                    raise ValueError("Ruff 配置启用了自动修复；必须显式 --no-fix")
                if name == "ruff" and re.search(r'''(?m)^\s*["']?extend["']?\s*=''', text):
                    raise ValueError("Ruff extend 配置链尚未绑定；需明确核验所继承配置")
                if name in ("pylint", "mypy") and re.search(r'''(?m)^\s*["']?(?:init-hook|load-plugins|plugins)["']?\s*=\s*\S''', text):
                    raise ValueError("项目检查配置含动态 plugin/init-hook，副作用尚未核验")
            if name == "eslint" and any((cwd / config).exists() for config in ("eslint.config.js", "eslint.config.mjs", "eslint.config.cjs")):
                raise ValueError("ESLint JavaScript 配置可执行代码，副作用尚未核验")
            if result["category"] == "related-test":
                result["side_effects"] = ["执行测试与 fixture；仍需父任务 related-test 授权和既有测试执行器的范围核验"]
        else:
            if not result["available"]:
                result.update(status="ENV_UNAVAILABLE" if "static" in allowed_actions else "UNAUTHORIZED",
                              reason=result["environment"]["reason"] if "static" in allowed_actions else "父上下文未授权 static")
                return result
            raise ValueError("未知工具或包装脚本，未核验")
        result["objects"] = sorted(set(_rel(root, _inside(root, cwd / item.split("::", 1)[0])) for item in objects))
        result["object_count"] = len(result["objects"])
        result["checked_files"] = _files(root, cwd, objects)
        extensions = {"ruff": (".py", ".pyi"), "pylint": (".py", ".pyi"), "mypy": (".py", ".pyi"),
                      "pyright": (".py", ".pyi"), "flake8": (".py",), "pytest": (".py",), "unittest": (".py",),
                      "tsc": (".ts", ".tsx", ".js", ".jsx", ".mts", ".cts"),
                      "eslint": (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"), "gradle": (".java",)}
        result["selection_roots"] = [name for name in result["objects"] if (root / name).is_dir()]
        result["checked_suffixes"] = list(extensions[name]) if name in extensions else None
        if name in extensions:
            result["checked_files"] = [p for p in result["checked_files"] if Path(p).suffix in extensions[name]]
        if selected_typescript_files is not None:
            result["checked_files"] = selected_typescript_files
        result["checked_file_count"] = len(result["checked_files"])
        result["config_dependencies"] = sorted(set(result["config_dependencies"]) | {s["path"] for s in result["command_sources"] if s["path"]})
        if scope_paths and any(not any(p == s or p.startswith(s.rstrip("/") + "/") for s in scope_paths) for p in result["checked_files"]):
            result["expanded_scope_reason"] = result["expanded_scope_reason"] or "现有命令按目录/模块检查，覆盖面大于本次输入；由调用方核对预算与范围"
        if result["required_action"] not in allowed_actions:
            result.update(status="UNAUTHORIZED", reason="父上下文未授权 " + result["required_action"])
        elif not result["available"]:
            result.update(status="ENV_UNAVAILABLE", reason=result["environment"]["reason"])
        else:
            result.update(status="READY", reason="命令、对象及已知配置副作用已分类；尚未执行")
    except (ValueError, OSError, ET.ParseError, SyntaxError) as exc:
        result["reason"] = str(exc)
        if result["required_action"] not in allowed_actions:
            result["status"] = "UNAUTHORIZED"
    return result


def bind_environment(check, probe_results):
    """消费执行器已预算/实跑的环境探测；不执行命令，不授予额外 action。

    probe_results 与 environment_probes 同序，包含 argv/returncode/stdout/stderr。
    tag 每次新执行都须探测；已保存证据绑定实际镜像 ID，不重解释可变 tag。
    """
    result = copy.deepcopy(check)
    probes = result.get("environment_probes", [])
    if not isinstance(probe_results, list) or len(probe_results) != len(probes):
        raise ValueError("环境探测结果数量不匹配")
    result["environment_probe_results"] = copy.deepcopy(probe_results)
    for probe, row in zip(probes, probe_results):
        if not isinstance(row, dict) or row.get("argv") != probe["argv"] or not isinstance(row.get("stdout"), str) or not isinstance(row.get("stderr"), str):
            raise ValueError("环境探测缺少实际 argv/stdout/stderr")
        if row.get("returncode") != 0:
            result.update(status="ENV_UNAVAILABLE", available=False,
                          reason="容器镜像/daemon 环境探测未完成：" + row["stderr"])
            result["environment"].update(available=False, reason=result["reason"])
            return result
        image_id = row["stdout"].strip()
        if not re.fullmatch(r"sha256:[a-fA-F0-9]{64}", image_id):
            result.update(status="UNVERIFIED", reason="docker image inspect 未返回可核验镜像 ID")
            return result
        actual = result["execution_argv"]
        index = probe["run_image_index"]
        if index >= len(actual) or actual[index] != probe["image"]:
            raise ValueError("环境探测与实际容器镜像参数不一致")
        actual[index] = image_id
        result["environment"]["container"]["image_id"] = image_id
    result["environment_probes"] = []
    return result


def discover_checks(root, *, allowed_actions=(), scope_paths=(), read_text=None, read_cost=None):
    """选择批次共享读回调；read_cost 接收整批成本，即使没有候选也不丢失读取事实。"""
    reader = _SelectionReads(read_text)
    try:
        checks = _discover_checks(root, allowed_actions=allowed_actions, scope_paths=scope_paths, read_text=reader)
    except _ReadCallbackFailure as exc:
        raise exc.error
    finally:
        cost = reader.cost("discovery-batch")
        if read_cost is not None:
            read_cost.update(cost)
    for check in checks:
        check["selection_read_cost"] = cost
    return checks


def _discover_checks(root, *, allowed_actions=(), scope_paths=(), read_text):
    """优先项目显式命令，再配置工具；仅完全没有对应工具时提供 syntax-only。"""
    root = Path(root).resolve()
    paths = [_inside(root, root / p) for p in scope_paths]
    directories = set()
    for path in paths:
        directory = path if path.is_dir() else path.parent
        owners = [candidate.parent for candidate in _project_files(root, directory) if candidate.name in CONFIG_NAMES]
        directories.add(owners[0] if owners else directory)
    directories = directories or {root}
    checks, seen = [], set()
    for directory in sorted(directories):
        files = _project_files(root, directory)
        sources = _sources(root, files, read_text)
        local = [_rel(directory, p) for p in paths if p.is_relative_to(directory)] or ["."]
        candidates = []
        for source in sources:
            argv = shlex.split(source["command"])
            if source["location"].startswith("scripts."):
                argv = ["npm", "run", source["location"][8:]]
            candidates.append((argv, source["cwd"]))
        texts = {p.name: read_text(p) for p in files if p.name in CONFIG_NAMES}
        combined = "\n".join(texts.values())
        selected = []
        for tool, configured in (
            ("ruff", any(n in texts for n in ("ruff.toml", ".ruff.toml")) or "[tool.ruff" in combined),
            ("pylint", any(n in texts for n in ("pylintrc", ".pylintrc")) or "[tool.pylint" in combined),
            ("mypy", any(n in texts for n in ("mypy.ini", ".mypy.ini")) or "[tool.mypy" in combined or "[mypy]" in combined),
            ("pyright", "pyrightconfig.json" in texts or "[tool.pyright" in combined),
            ("pytest", "pytest.ini" in texts or "[tool.pytest" in combined or "[tool:pytest]" in combined),
        ):
            if configured:
                selected.append(tool)
                targets = local
                if tool == "pytest":
                    targets = [name for name in local if Path(name).suffix == ".py" and
                               (Path(name).name.startswith("test_") or Path(name).name.endswith("_test.py"))]
                    # 只有已知明确测试文件才选择真实 pytest；不从 testpaths 推导全量授权。
                    if not targets:
                        targets = []
                argv = [tool, "check", "--no-fix", *targets] if tool == "ruff" else [tool, *targets]
                candidates.append((argv, _rel(root, directory)))
        if "pytest" not in selected:
            unittest_targets = []
            for name in local:
                path = directory / name
                if path.is_file() and path.suffix == ".py":
                    try:
                        tree = ast.parse(read_text(path))
                    except SyntaxError:
                        continue
                    if any(isinstance(node, ast.Import) and any(alias.name == "unittest" for alias in node.names) or
                           isinstance(node, ast.ImportFrom) and node.module == "unittest" for node in ast.walk(tree)):
                        unittest_targets.append(name)
            if unittest_targets:
                candidates.append(([sys.executable, "-B", "-m", "unittest", *unittest_targets], _rel(root, directory)))
        if "tsconfig.json" in texts:
            selected.append("tsc")
            candidates.append((["tsc", "--noEmit", "--project", "."], _rel(root, directory)))
        if any(name.startswith(("eslint.config.", ".eslintrc")) for name in texts):
            selected.append("eslint")
            candidates.append((["eslint", *local], _rel(root, directory)))
        for config, tool, args in (("pom.xml", "mvn", ["-o", "compile"]), ("build.gradle", "gradle", ["--offline", "--no-daemon", "compileJava"]),
                                   ("build.gradle.kts", "gradle", ["--offline", "--no-daemon", "compileJava"])):
            if config in texts:
                selected.append(tool)
                module = next(p.parent for p in files if p.name == config)
                candidates.append(([tool, *args], _rel(root, module)))
        python_paths = [p for p in paths if p.is_file() and p.suffix == ".py" and p.is_relative_to(directory)]
        if python_paths and not set(selected) & {"ruff", "pylint", "mypy", "pyright"} and not any(re.search(r"\b(?:ruff|pylint|mypy|pyright)\b", source["command"]) for source in sources):
            code = "import ast; " + "; ".join("ast.parse(open(" + repr(_rel(directory, p)) + ").read())" for p in python_paths)
            candidates.append(([sys.executable, "-I", "-B", "-c", code], _rel(root, directory)))
        for argv, cwd in candidates:
            key = (tuple(argv), cwd)
            if key in seen:
                continue
            seen.add(key)
            checks.append(_inspect_command(root, argv, allowed_actions=allowed_actions, scope_paths=scope_paths, cwd=cwd, read_text=read_text))
    return checks
