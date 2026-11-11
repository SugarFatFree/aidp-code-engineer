#!/usr/bin/env python3
"""在部署 commit 的 detached worktree 内执行 build 全量单测（无网络安装/部署）。

plan-init --root ROOT --version VERSION [--out PATH] [--force]   项目侧一次性发现测试文件，写 test-plan.json 草稿（提交后冻结；运行期不全仓发现）
freeze --root ROOT --version VERSION --build BUILD --commit SHA [--source PATH] [--out DIR]
run --root ROOT --version VERSION --build BUILD --commit SHA --plan JSON [--timeout 3600]
status --root ROOT --version VERSION --build BUILD
--self-check  用真实临时 Git 仓库和标准库 unittest 验证隔离、缓存及失败分类。

计划格式及运行协议唯一信源：flows/sprint-aiauto-test/phase-2-unit.md。
本进程为阻塞式子 Agent 执行器；run/status 从不冻结链路。终态按 build 固定，
同 build 的后续调用仅读结果；新 build 即使同 SHA 也重新执行。使用 POSIX flock。
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import signal
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)
import test_ledger
from aidp_paths import baseline, runtime_dir
from baseline_edit import load_archived_node

SCHEMA = 1
STATUSES = {"PASS", "FAIL", "UNVERIFIED", "TIMEOUT", "RUNNING", "NOT_APPLICABLE"}
NULL_COUNTS = {"passed": None, "failed": None, "skipped": None}
MISSING = re.compile(
    r"ModuleNotFoundError|ImportError:|No module named|Cannot find module|ERR_MODULE_NOT_FOUND|"
    r"command not found|not recognized as an internal|No such file or directory|"
    r"ClassNotFoundException|NoClassDefFoundError|spawn .+ ENOENT", re.I)


class BuildError(ValueError):
    pass


class BudgetExpired(KeyboardInterrupt):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                     separators=(",", ":")).encode()).hexdigest()


def component(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,159}", value):
        raise BuildError("version/build 必须是安全的非空路径分量")
    return value


def build_dir(root, version, build):
    return Path(runtime_dir(root)) / "build-unit" / component(version) / component(build)


def blank(version, build, commit, status="UNVERIFIED", reason="not-started"):
    return {"schema": SCHEMA, "version": version, "build": build, "commit": commit,
            "status": status, "reason": reason, "runs": [], "counts": dict(NULL_COUNTS),
            "failed_cases": [], "primary_error": None, "reused": False}


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".write-", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, ensure_ascii=True, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def save_result(directory, result):
    atomic_json(directory / "result.json", dict(result, checksum=digest(result)))


def load_result(directory):
    path = directory / "result.json"
    if not path.exists():
        return None
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise BuildError("本地结果必须是 JSON 对象")
    checksum = result.pop("checksum", None)
    if (checksum != digest(result) or result.get("schema") != SCHEMA
            or result.get("status") not in STATUSES):
        raise BuildError("本地结果损坏，不能复用")
    return result


def git(root, *args, timeout=30):
    env = {"PATH": os.defpath, "HOME": str(root), "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0"}
    proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                          env=env, timeout=timeout)
    if proc.returncode:
        raise BuildError(proc.stderr.decode("utf-8", "replace").strip() or "Git 命令失败")
    return proc.stdout


def relative(value, allow_dot=False):
    if not isinstance(value, str) or not value or "\x00" in value:
        raise BuildError("需要非空的项目相对路径")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or ".git" in path.parts or "\\" in value:
        raise BuildError(f"路径不可逃出 worktree：{value}")
    if str(path) == "." and not allow_dot:
        raise BuildError("输入路径不能是整个项目")
    return str(path)


UNIT_NA = {"status": "NOT_APPLICABLE", "reason": "all-cases-browser-only"}


def none_found(evidence):
    """“发现过程执行了且结果为空”的机器证据（plan-init 写入）；手写空清单不算。"""
    return (isinstance(evidence, dict) and evidence.get("status") == "none-found" and evidence.get("files") == 0
            and isinstance(evidence.get("checked"), list) and bool(evidence["checked"]))
FREEZE_DIR = "version-freeze"


def read_plan_config(source_path, payload):
    """解析部署 commit 内的测试计划来源（JSON，或契约卡内唯一 aidp-test-plan 围栏块）；load_plan/freeze 共用。"""
    if source_path.lower().endswith(".json"):
        config = json.loads(payload)
    else:
        blocks = re.findall(r"^```aidp-test-plan[ \t]*\n(.*?)^```[ \t]*$",
                            payload.decode("utf-8"), re.M | re.S)
        if len(blocks) != 1:
            raise BuildError("契约卡须有且仅有一个 fenced aidp-test-plan JSON 块")
        config = json.loads(blocks[0])
        if not isinstance(config, dict) or config.get("schema") != SCHEMA:
            raise BuildError("aidp-test-plan 块的 schema 必须是 1")
    if not isinstance(config, dict) or not isinstance(config.get("test_plan", config), dict):
        raise BuildError("项目测试配置必须是 JSON 对象")
    return config


def load_plan(root, version, build, commit, plan):
    if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", commit or ""):
        raise BuildError("commit 必须是完整小写 Git SHA，禁止 HEAD/分支/缩写")
    actual = git(root, "rev-parse", "--verify", commit + "^{commit}").decode().strip()
    if actual != commit:
        raise BuildError("commit 不是可核验的完整 commit SHA")
    if not isinstance(plan, dict) or plan.get("schema") != SCHEMA:
        raise BuildError("plan.schema 必须是 1")
    if plan.get("version") != version or plan.get("build") != build or plan.get("commit") != commit:
        raise BuildError("plan 的 version/build/commit 与请求不一致")

    baseline_path = Path(baseline(root))
    node = {}
    if baseline_path.exists():
        data = json.loads(baseline_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("versions", {}), dict):
            raise BuildError("baseline versions 结构无效")
        node = data.get("versions", {}).get(version, {})
        if not isinstance(node, dict):
            raise BuildError("baseline 版本节点无效")
        if node.get("archived"):
            node = load_archived_node(str(baseline_path), version) or node
    if not isinstance(node.get("builds", []), list) or any(not isinstance(item, dict) for item in node.get("builds", [])):
        raise BuildError("baseline builds 必须是对象数组")
    matches = [item for item in node.get("builds", []) if item.get("build") == build]
    if matches:
        if len(matches) != 1 or matches[0].get("push_commit") != commit:
            raise BuildError("baseline 本 build push_commit 与部署 commit 不一致或缺失")
    else:
        deployment = plan.get("deployment", {})
        if not isinstance(deployment, dict):
            raise BuildError("standalone deployment 必须是对象")
        if (plan.get("standalone") is not True or deployment.get("commit") != commit
                or deployment.get("verified") is not True
                or not isinstance(deployment.get("evidence"), str)
                or not deployment["evidence"].strip()):
            raise BuildError("没有 baseline 本 build；standalone 必须提供已核验部署 commit 及 evidence")

    source = plan.get("source", {})
    if not isinstance(source, dict):
        raise BuildError("source 必须是对象")
    source_path = relative(source.get("path"))
    payload = git(root, "show", f"{commit}:{source_path}")
    if source.get("sha256") != hashlib.sha256(payload).hexdigest():
        raise BuildError("计划来源 SHA256 与部署 commit 内文件不符")
    config = read_plan_config(source_path, payload)
    suites = plan.get("suites")
    # 只读取部署 commit 中的配置；不读取主工作区相同路径。
    configured = config.get("test_plan", config).get("suites")
    if plan.get("unit_applicability") is not None:
        # 单测不适用（全部 browser_only）：无 runner 可冻结；来源不得另含 suites，防止“声明不适用却有单测”。
        applicability = plan["unit_applicability"]
        if (not isinstance(applicability, dict) or {k: applicability.get(k) for k in UNIT_NA} != UNIT_NA
                or not none_found(applicability.get("evidence")) or suites != [] or configured not in (None, [])):
            raise BuildError("unit_applicability 只能与空 suites 同时出现，且来源不得含 suites")
        return plan
    if not isinstance(suites, list) or not suites or suites != configured:
        raise BuildError("冻结 suites 必须与部署 commit 内项目测试配置完全一致且非空")
    identities = set()
    for suite in suites:
        if not isinstance(suite, dict):
            raise BuildError("suite 必须是对象")
        identity = (suite.get("cwd"), suite.get("env_id"))
        if identity in identities:
            raise BuildError("每个 suite 的 cwd/env_id 必须唯一")
        identities.add(identity)
        runners = suite.get("runners")
        if not isinstance(runners, list) or not runners:
            raise BuildError("suite 缺显式文件目标 runners；禁止回退 full_argv / 全仓发现")
        for runner in runners:
            argv = runner.get("argv", [])
            if (any(arg in {"-k", "--grep", "-g", "--testNamePattern", "--testPathIgnorePatterns", "--exclude", "--ignore"}
                    or arg.startswith(("--grep=", "--testNamePattern=", "--ignore=", "--exclude=")) for arg in argv[1:])
                    or "pytest" in argv and "-m" in argv[argv.index("pytest") + 1:]):
                raise BuildError("版本测试运行器含过滤参数，无法证明完整用例覆盖")
            if runner.get("cwd", ".") != suite.get("cwd") or runner.get("env_id", "default") != suite.get("env_id"):
                raise BuildError("runner cwd/env_id 必须与所属 suite 一致")
        command = suite.get("full_argv", runners[0].get("argv"))
        if (not isinstance(command, list) or not command
                or any(not isinstance(arg, str) or not arg or "\x00" in arg for arg in command)):
            raise BuildError("full_argv 必须是真实非空字符串数组")
        exe = Path(command[0]).name
        if exe in {"true", "false", "echo", "printf", "sh", "bash", "zsh", "fish", "cmd", "powershell"}:
            raise BuildError("full_argv 不接受占位命令或 shell 包装")
        if any(arg in {"install", "ci", "build", "start", "serve", "deploy"} for arg in command[1:]):
            raise BuildError("单测计划不可安装依赖、构建、启动或部署服务")
        for position, arg in enumerate(command):
            if str(root) in arg or re.search(r"(?:^|[=/])\.\.(?:/|$)", arg):
                raise BuildError("full_argv 不可引用主工作区或父目录路径")
            if position and (arg.startswith("/") or re.search(r"^--?[^=]+=/", arg)):
                raise BuildError("测试参数只能引用 worktree 相对路径；外部工具路径只允许 argv[0]")
        if Path(command[0]).is_absolute() and Path(command[0]).resolve().is_relative_to(root):
            raise BuildError("测试可执行程序不可来自主工作区")
        relative(suite.get("cwd"), allow_dot=True)
        if not isinstance(suite.get("env_id"), str) or not suite["env_id"].strip():
            raise BuildError("每套必须有 env_id")
        if not isinstance(suite.get("inputs"), list):
            raise BuildError("每套必须显式给出 inputs 数组")
        for value in suite["inputs"]:
            relative(value)
        if suite.get("external_dependencies") not in ("none", "isolated"):
            raise BuildError("每套须声明 external_dependencies=none 或 isolated，不能指向部署环境")
        env = suite.get("env", {})
        if not isinstance(env, dict) or any(not isinstance(k, str) or not k or "=" in k or "\x00" in k
                                           or not isinstance(v, str) or "\x00" in v for k, v in env.items()):
            raise BuildError("env 必须是字符串映射")
        for key, value in env.items():
            path_parts = value.split(os.pathsep)
            if (str(root) in value or re.search(r"(?:^|[:=/])\.\.(?:/|$)", value)
                    or any(Path(part).is_absolute() and Path(part).resolve().is_relative_to(root)
                           for part in path_parts)
                    or key in {"HOME", "PWD", "TMPDIR", "GIT_DIR", "GIT_WORK_TREE"}):
                raise BuildError("env 不可覆盖隔离路径或引用主工作区/父目录")
        if "junit_xml" in suite:
            relative(suite["junit_xml"])
    return plan


NON_CASE_BOOK_PREFIXES = ("_", "00_", "98_", "99_")
NON_CASE_BOOK_TOKENS = ("研发自测方案", "测试环境与账号", "总览")


def is_case_book(name):
    """正式用例册判定的唯一规则：排除开发期增量册(_)、索引/跨系统/待澄清册及方案、账号、总览文档。"""
    return not (name.startswith(NON_CASE_BOOK_PREFIXES) or any(token in name for token in NON_CASE_BOOK_TOKENS))


def formal_case_books(root, version):
    formal = (Path(root) / "docs/testing" / component(version) / "正式用例").resolve()
    books = []
    for path in sorted(formal.rglob("*.md")):
        if not is_case_book(path.name):
            continue
        if not path.resolve().is_relative_to(formal):
            raise BuildError("正式用例路径逃出本版本")
        books.append(path)
    return books


def case_parser():
    """正式用例标题的唯一解析器（tasks_state.CASE_RE）。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("_aidp_formal_cases", Path(__file__).resolve().parent.parent /
                                                 "skills/auto-test-runner/scripts/tasks_state.py")
    parser = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parser)
    return parser


def baseline_file(root, version, rel, baseline_root=None):
    """验收基线只有两个合法落点：本版本 docs/testing/<v>/ 下 JSON（读 root），或 freeze 写入主仓运行态目录
    memory/.aidp/version-freeze/<v>/ 下 JSON（读 baseline_root，默认 root）；后者由 manifest 摘要固定，不入 Git。"""
    rel = relative(rel)
    if not rel.endswith(".json"):
        raise BuildError("验收基线必须是 JSON")
    if rel.startswith(f"docs/testing/{component(version)}/"):
        base = Path(root).resolve()
    elif rel.startswith(f"memory/.aidp/{FREEZE_DIR}/{component(version)}/"):
        base = Path(baseline_root or root).resolve()
    else:
        raise BuildError("验收基线必须归属本版本 docs/testing/<version>/ 或 freeze 运行态目录")
    path = (base / rel).resolve()
    if not path.is_relative_to(base):
        raise BuildError("验收基线路径逃出 root")
    return path


def unit_not_applicable(acceptance):
    """全部正式用例都显式 browser_only 且无任何测试文件映射。仅基于验收基线事实判定，不由缺 runner/空 suites 推出。"""
    cases = acceptance.get("cases") or []
    ids = {case.get("id") for case in cases if isinstance(case, dict)}
    browser = acceptance.get("browser_only")
    return (bool(ids) and isinstance(browser, list) and set(browser) == ids and len(browser) == len(ids)
            and not any(case.get("test_files") for case in cases) and not acceptance.get("acceptance_tests"))


def validate_case_index(root, plan, baseline_root=None):
    """把验收映射与本版本正式用例标题核对；不扫描仓库测试代码。

    每个正式用例 ID 必须恰好出现一次，并且要么映射 ≥1 个测试文件，要么显式列入 browser_only（此时无测试文件）。"""
    root = Path(root).resolve()
    baseline_path = baseline_file(root, plan["version"], plan["acceptance_baseline"]["path"], baseline_root)
    acceptance = json.loads(baseline_path.read_text(encoding="utf-8"))
    index = acceptance.get("case_index") or {}
    index_path = (root / relative(index.get("path"))).resolve()
    formal = root / "docs/testing" / component(plan["version"]) / "正式用例"
    if not index_path.is_relative_to(formal.resolve()) or not index_path.is_file():
        raise BuildError("验收基线 case_index 必须指向本版本正式用例索引")
    if hashlib.sha256(index_path.read_bytes()).hexdigest() != index.get("sha256"):
        raise BuildError("正式用例索引 SHA256 不匹配")
    parser = case_parser()
    actual = []
    for path in formal_case_books(root, plan["version"]):
        actual.extend(match[1] for match in parser.CASE_RE.finditer(path.read_text(encoding="utf-8")))
    cases = acceptance.get("cases", [])
    mapped = [case.get("id") for case in cases]
    if not actual or len(set(actual)) != len(actual) or set(mapped) != set(actual) or len(set(mapped)) != len(mapped):
        raise BuildError("验收基线 cases 与本版本完整正式用例清单不一致（缺失、历史用例或重复 ID）")
    browser = acceptance.get("browser_only", [])
    if (not isinstance(browser, list) or any(not isinstance(item, str) for item in browser)
            or len(set(browser)) != len(browser) or not set(browser) <= set(actual)):
        raise BuildError("browser_only 必须是正式用例 ID 的无重复字符串数组")
    for case in cases:
        files = case.get("test_files")
        if not isinstance(files, list) or any(not isinstance(item, str) for item in files):
            raise BuildError(f"用例 {case.get('id')} 的 test_files 必须是字符串数组")
        if not files and case["id"] not in browser:
            raise BuildError(f"用例 {case['id']} 既无测试文件映射也未声明 browser_only")
        if files and case["id"] in browser:
            raise BuildError(f"用例 {case['id']} 不能同时映射测试文件并声明 browser_only")
    return sorted(actual)


def git_exists(root, commit, path):
    try:
        git(root, "cat-file", "-e", f"{commit}:{path}")
        return True
    except BuildError:
        return False


class FreezeBlock(Exception):
    def __init__(self, reason, hint, gaps=None):
        super().__init__(reason)
        self.reason, self.hint, self.gaps = reason, hint, list(gaps or [])


def canonical(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True) + "\n").encode()


def freeze(root, version, build, commit, source=None, out=None):
    """确定性冻结版本全量清单：只读部署 commit，写 acceptance.json 与 manifest 到运行态目录。

    来源 `unit_tests`（必填，可显式 []）= 本版本单测文件清单，决定 acceptance_tests；`case_tests` 可选，仅记录确有对应单测的
    用例；未出现在 case_tests 的正式用例默认归浏览器实测路（browser_only）。显式 `"unit_tests": []` 才可 NOT_APPLICABLE。"""
    root = Path(root).resolve()
    summary = {"cases": 0, "mapped": 0, "browser_only": 0, "acceptance_tests": 0, "gaps": []}
    try:
        if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", commit or ""):
            raise FreezeBlock("invalid-commit", "--commit 必须是部署完整小写 Git SHA")
        if git(root, "rev-parse", "--verify", commit + "^{commit}").decode().strip() != commit:
            raise FreezeBlock("invalid-commit", "--commit 不是可核验的 commit 对象")
        component(version), component(build)
        candidates = [f"docs/testing/{version}/test-plan.json", "docs/testing/test-plan.json"]
        where = ("在部署 commit 提交 " + candidates[0] + "（可先运行 build_unit_test.py plan-init 生成草稿；JSON，根含 suites[每套含 runners]、"
                 "unit_tests:[本版本单测文件]（无单测须显式写 []）；可选 case_tests:{TC-ID:[测试文件]}、dependencies:[文件]），"
                 "或用 --source 指向含唯一 ```aidp-test-plan 围栏 JSON 的契约卡")
        if source:
            source_path = relative(source)
            found = [source_path] if git_exists(root, commit, source_path) else []
        else:
            found = [item for item in candidates if git_exists(root, commit, item)]
        if not found:
            raise FreezeBlock("test-plan-source-missing", "部署 commit 内没有测试计划来源；" + where)
        if len(found) > 1:
            raise FreezeBlock("test-plan-source-ambiguous", "部署 commit 内同时存在多个来源，请用 --source 指定其一：" + ", ".join(found))
        source_path = found[0]
        payload = git(root, "show", f"{commit}:{source_path}")
        try:
            config = read_plan_config(source_path, payload)
        except (ValueError, UnicodeDecodeError, BuildError) as exc:
            raise FreezeBlock("test-plan-source-invalid", f"{source_path} 无法解析：{exc}；{where}")
        plan_cfg = config.get("test_plan", config)
        case_tests, browser_only = plan_cfg.get("case_tests", {}), plan_cfg.get("browser_only", [])
        dependencies, unit_tests = plan_cfg.get("dependencies", []), plan_cfg.get("unit_tests")
        if plan_cfg.get("needs_review"):
            raise FreezeBlock("test-plan-needs-review", f"{source_path} 仍标 needs_review（plan-init 草稿未经确认）；"
                              "核对 suites/unit_tests 后删除该字段再提交。无单测也须人工确认后保留 \"unit_tests\": []")
        if unit_tests is None:
            raise FreezeBlock("unit-tests-undeclared", f"{source_path} 未声明 unit_tests：写本版本单测文件清单；"
                              "确无单测则显式写 \"unit_tests\": []（不声明不会被当作不适用）。可先运行 build_unit_test.py plan-init")
        if (not isinstance(unit_tests, list) or any(not isinstance(i, str) for i in unit_tests)
                or len(set(unit_tests)) != len(unit_tests)):
            raise FreezeBlock("test-plan-source-invalid", f"{source_path} 的 unit_tests 须为无重复的文件路径字符串数组")
        discovery = plan_cfg.get("unit_discovery")
        if not unit_tests and not none_found(discovery):
            raise FreezeBlock("unit-tests-empty-no-evidence", f"{source_path} 的 unit_tests 为空但没有 unit_discovery 证据（可能是忘写）："
                              "运行 build_unit_test.py plan-init --force 重新发现（确无测试会自动写 unit_discovery.status=none-found），"
                              "或补写本版本单测文件清单")
        if (not isinstance(case_tests, dict) or any(not isinstance(k, str) or not isinstance(v, list) or not v
                or any(not isinstance(i, str) for i in v) for k, v in case_tests.items())
                or not isinstance(browser_only, list) or any(not isinstance(i, str) for i in browser_only)
                or not isinstance(dependencies, list) or any(not isinstance(i, str) for i in dependencies)):
            raise FreezeBlock("test-plan-source-invalid", f"{source_path} 的 case_tests 须为 {{TC-ID:[文件…]}}（非空数组），"
                              "browser_only/dependencies 须为字符串数组")
        # 正式用例：只扫部署 commit 的本版本册，沿用 is_case_book 单一排除规则。
        formal = f"docs/testing/{version}/正式用例/"
        listed = [os.fsdecode(name) for name in git(root, "ls-tree", "-r", "-z", "--name-only", commit, "--", formal).split(b"\0") if name]
        parser, ids = case_parser(), []
        for name in sorted(listed):
            if name.endswith(".md") and is_case_book(PurePosixPath(name).name):
                ids.extend(m[1] for m in parser.CASE_RE.finditer(git(root, "show", f"{commit}:{name}").decode("utf-8")))
        if not ids:
            raise FreezeBlock("formal-cases-missing", f"部署 commit 的 {formal} 下没有带 TC-ID 标题的正式用例册")
        dup = sorted({i for i in ids if ids.count(i) > 1})
        if dup:
            raise FreezeBlock("formal-case-duplicate", "正式用例 ID 重复：" + ", ".join(dup), dup)
        indexes = [n for n in listed if PurePosixPath(n).parent == PurePosixPath(formal.rstrip("/"))
                   and PurePosixPath(n).name.startswith("00_") and "索引" in PurePosixPath(n).name]
        if len(indexes) != 1:
            raise FreezeBlock("case-index-missing", f"{formal} 下须有且仅有一个 00_*索引*.md 正式用例索引（现有 {len(indexes)} 个）")
        known, gaps = set(ids), []
        gaps += [f"{i}: case_tests/browser_only 引用了不存在的正式用例" for i in sorted((set(case_tests) | set(browser_only)) - known)]
        gaps += [f"{i}: 同时出现在 case_tests 与 browser_only" for i in sorted(set(case_tests) & set(browser_only))]
        gaps += [f"{i}: browser_only 重复" for i in sorted({i for i in browser_only if browser_only.count(i) > 1})]
        from test_scope import is_test
        files = sorted(unit_tests)
        for item in sorted(set(files) | {f for v in case_tests.values() for f in v}):
            relative(item)
            if not is_test(item) or not git_exists(root, commit, item):
                gaps.append(f"{item}: 不是部署 commit 内的明确测试文件")
        gaps += [f"{i}: case_tests 引用的 {f} 不在 unit_tests 清单内" for i, v in sorted(case_tests.items()) for f in v if f not in unit_tests]
        # 默认归实测路：未出现在 case_tests 的正式用例（含显式 browser_only）。
        default_browser = sorted(known - set(case_tests))
        for item in dependencies:
            relative(item)
            if not git_exists(root, commit, item):
                gaps.append(f"{item}: dependencies 文件不在部署 commit 内")
        summary.update(cases=len(known), mapped=len(known & set(case_tests)), browser_only=len(default_browser),
                       explicit_browser_only=len(set(browser_only) & known), default_browser=len(default_browser),
                       default_browser_ids=default_browser, acceptance_tests=len(files), gaps=gaps)
        if gaps:
            raise FreezeBlock("coverage-gaps", f"修正 {source_path}：unit_tests/case_tests 须引用部署 commit 内的测试文件，case_tests 文件须在 unit_tests 内，"
                              "browser_only 不得与 case_tests 重叠或引用不存在的用例", gaps)
        suites = plan_cfg.get("suites")
        not_applicable = not files
        if not_applicable and suites not in (None, []):
            raise FreezeBlock("unit-source-inconsistent", f"{source_path} 全部用例为 browser_only 时不得再含 suites；请移除 suites 或为用例补 case_tests")
        if not not_applicable and (not isinstance(suites, list) or not suites):
            raise FreezeBlock("test-plan-suites-missing", f"{source_path} 缺 suites（非空，每套含 runners）；" + where)
        if not not_applicable:
            for item in files:  # 静态检查：每个单测文件至少被某个 runner 的 suffixes 与 cwd 命中。
                if not any(isinstance(r, dict) and PurePosixPath(item).suffix in (r.get("suffixes") or [])
                           and (r.get("cwd", ".") in (".", "") or item.startswith(r["cwd"].rstrip("/") + "/"))
                           for suite in suites if isinstance(suite, dict) for r in (suite.get("runners") or [])):
                    gaps.append(f"{item}: 没有任何 runner 的 suffixes/cwd 命中该单测文件")
            if gaps:
                raise FreezeBlock("unit-test-no-runner", f"在 {source_path} 的 suites.runners 补能运行这些文件的 runner", gaps)
        freeze_root = (Path(runtime_dir(root)) / FREEZE_DIR / version).resolve()
        directory = Path(out).resolve() if out else freeze_root / build
        if not directory.is_relative_to(freeze_root):
            raise FreezeBlock("invalid-out", f"--out 必须位于 memory/.aidp/{FREEZE_DIR}/{version}/ 下，验收基线读取受此限制")
        acceptance = {"version": version, "acceptance_tests": files, "dependencies": sorted(set(dependencies)),
                      "browser_only": default_browser,
                      "cases": [{"id": i, "test_files": sorted(case_tests.get(i, []))} for i in sorted(known)],
                      "case_index": {"path": indexes[0],
                                     "sha256": hashlib.sha256(git(root, "show", f"{commit}:{indexes[0]}")).hexdigest()}}
        acceptance_path, manifest_path = directory / "acceptance.json", directory / "manifest.json"
        manifest = {"schema": SCHEMA, "version": version, "build": build, "commit": commit,
                    "source": {"path": source_path, "sha256": hashlib.sha256(payload).hexdigest()},
                    "suites": [] if not_applicable else suites,
                    "acceptance_tests": files, "dependencies": acceptance["dependencies"],
                    "acceptance_baseline": {"path": acceptance_path.relative_to(root).as_posix(),
                                            "sha256": hashlib.sha256(canonical(acceptance)).hexdigest()}}
        if not_applicable:
            manifest["unit_applicability"] = dict(UNIT_NA, evidence=discovery)
        if manifest_path.exists():
            if manifest_path.read_bytes() != canonical(manifest):
                raise FreezeBlock("manifest-conflict", "同 build 已冻结不同清单；不得覆盖原证据，须使用新 build")
        else:
            atomic_json(acceptance_path, acceptance)
            atomic_json(manifest_path, manifest)
        return {"schema": SCHEMA, "status": "FROZEN", "reason": "unit-not-applicable" if not_applicable else "frozen",
                "version": version, "build": build, "commit": commit, "manifest": str(manifest_path),
                "acceptance": str(acceptance_path), "unit_applicability": manifest.get("unit_applicability"),
                "summary": summary}
    except FreezeBlock as exc:
        return {"schema": SCHEMA, "status": "UNVERIFIED", "reason": exc.reason, "hint": exc.hint,
                "version": version, "build": build, "commit": commit, "summary": summary}
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as exc:
        return {"schema": SCHEMA, "status": "UNVERIFIED", "reason": "freeze-error", "hint": str(exc),
                "version": version, "build": build, "commit": commit, "summary": summary}


def plan_init(root, version, out=None, force=False):
    """项目侧一次性写计划：只读发现项目实际测试文件与运行器，写 test-plan.json 草稿。

    ⚠️ 这是“写计划时”的一次性发现，结果经 git 提交后冻结；运行期（freeze/run）绝不全仓发现。
    已存在则不覆盖（--force 才覆盖）。发现结果为空时写 unit_tests:[] + unit_discovery(none-found) 机器证据；发现了测试文件却无可用运行器则标 needs_review。"""
    root = Path(root).resolve()
    component(version)
    rel = relative(out) if out else f"docs/testing/{version}/test-plan.json"
    target = (root / rel).resolve()
    if not target.is_relative_to(root):
        raise BuildError("--out 不可逃出项目")
    if target.exists() and not force:
        return {"schema": SCHEMA, "status": "EXISTS", "path": rel,
                "note": "计划已存在，复用不覆盖（需重新生成请 --force）"}
    from test_scope import is_test
    names = git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard").split(b"\0")
    tests = sorted({os.fsdecode(n) for n in names if n and is_test(os.fsdecode(n))
                    and "node_modules/" not in os.fsdecode(n)
                    and not os.fsdecode(n).startswith(("memory/", "docs/"))})

    def text(name):
        path = root / name
        return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""

    pytest_cfg = any((root / n).is_file() for n in ("pytest.ini", ".pytest.ini")) or any(
        marker in text(n) for n, marker in (("pyproject.toml", "[tool.pytest"), ("setup.cfg", "[tool:pytest"), ("tox.ini", "[pytest"))
    )
    package = text("package.json")
    candidates = {
        ".py": ("pytest" if pytest_cfg else "unittest",
                ["python3", "-m", "pytest", "-q", "{tests}"] if pytest_cfg else ["python3", "-m", "unittest", "-v", "{tests}"]),
        ".java": ("maven", ["mvn", "-q", "test", "-Dtest={test_classes}"]) if (root / "pom.xml").is_file() else None,
    }
    js = ("vitest", ["npx", "vitest", "run", "{tests}"]) if "vitest" in package else (
        ("jest", ["npx", "jest", "{tests}"]) if "jest" in package else None)
    for suffix in (".ts", ".tsx", ".js", ".jsx"):
        candidates[suffix] = js
    checked = [n for n in ("pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini", "package.json", "pom.xml") if (root / n).is_file()]
    checked = checked or ["git-tracked-and-untracked-files"]  # 没有任何运行器配置时，检查对象是文件清单本身
    suites, grouped, notes, listed = {}, {}, [], []
    for test in tests:
        suffix = PurePosixPath(test).suffix
        choice = candidates.get(suffix)
        if choice is None:
            notes.append(f"{test}: 未识别到对应测试运行器（只识别 pytest/unittest、vitest/jest、maven），未列入 unit_tests")
            continue
        grouped.setdefault(choice[0], (choice[1], set()))[1].add(suffix)
        listed.append(test)
    for name, (argv, suffixes) in sorted(grouped.items()):
        env_id = f"plan-init-{name}"
        suites[name] = {"cwd": ".", "env_id": env_id, "inputs": [], "external_dependencies": "none",
                        "runners": [{"suffixes": sorted(suffixes), "argv": argv, "cwd": ".", "env_id": env_id}]}
    if not tests:
        notes.append("未发现任何测试文件：写 unit_tests=[] 与 unit_discovery.status=none-found 机器证据，freeze 将按单测不适用处理并在报告醒目显示")
    if suites:
        notes.append("external_dependencies 默认写 none、cwd 默认 '.'；有数据库/子目录工程请人工修正")
    draft = {"schema": SCHEMA, "version": version, "suites": [suites[k] for k in sorted(suites)],
             "unit_tests": sorted(listed), "case_tests": {}, "dependencies": [],
             "unit_discovery": {"status": "none-found" if not tests else "found", "files": len(tests), "checked": checked,
                                "runners": sorted(grouped)},
             # 发现了测试文件却没有可用运行器 = 需人决定怎么跑；没有任何测试文件则是确定的“不适用”证据，不卡 freeze。
             "needs_review": bool(tests) and len(listed) != len(tests), "review_notes": notes}
    if not draft["needs_review"]:
        del draft["needs_review"]
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(target, draft)
    return {"schema": SCHEMA, "status": "CREATED", "path": rel, "unit_tests": len(listed),
            "needs_review": bool(draft.get("needs_review")), "review_notes": notes}


def assert_worktree_inputs(worktree, suite):
    cwd = (worktree / suite["cwd"]).resolve()
    if not cwd.is_relative_to(worktree) or not cwd.is_dir():
        raise BuildError("cwd 必须是 worktree 内现有目录")
    for value in suite["inputs"]:
        path = (worktree / value).resolve()
        if not path.is_relative_to(worktree) or not path.exists():
            raise BuildError(f"输入缺失或逃出 worktree：{value}")
    if "junit_xml" in suite:
        path = (worktree / suite["junit_xml"]).resolve()
        if not path.is_relative_to(worktree):
            raise BuildError("JUnit XML 路径逃出 worktree")
        if path.exists():
            raise BuildError("JUnit XML 已存在，拒绝把旧报告当成本次结果")
    # 任何跟踪的向外符号链接/未装配 submodule 都破坏部署树隔离。
    for entry in git(worktree, "ls-files", "--stage", "-z").split(b"\0"):
        if not entry:
            continue
        metadata, name = entry.split(b"\t", 1)
        path = worktree / os.fsdecode(name)
        if metadata.startswith(b"160000"):
            raise BuildError("部署树含未装配 submodule，本执行器不下载依赖")
        if path.is_symlink() and not path.resolve().is_relative_to(worktree):
            raise BuildError(f"部署树符号链接指向 worktree 外：{os.fsdecode(name)}")


@contextmanager
def isolated_environment(directory, suite):
    # 不继承部署连接串、PYTHONPATH、NODE_OPTIONS、用户 site 等隐式配置。
    # HOME/TMPDIR 进入环境身份；同版本共享目录才能让同内容证据跨 build 可信复用。
    home = directory.parent / "home"
    temporary = directory.parent / "tmp"
    home.mkdir(exist_ok=True)
    temporary.mkdir(exist_ok=True)
    env = {"PATH": os.defpath, "HOME": str(home), "TMPDIR": str(temporary),
           "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PYTHONNOUSERSITE": "1",
           "PYTHONDONTWRITEBYTECODE": "1", "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0"}
    env.update(suite.get("env", {}))
    original = dict(os.environ)
    os.environ.clear()
    os.environ.update(env)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(original)


@contextmanager
def capture(path):
    # ledger 的 Popen 继承 fd，而非 Python redirect_stdout；日志包含完整 stdout/stderr。
    sys.stdout.flush()
    sys.stderr.flush()
    saved = [os.dup(1), os.dup(2)]
    try:
        with path.open("wb") as stream:
            os.dup2(stream.fileno(), 1)
            os.dup2(stream.fileno(), 2)
            yield
            sys.stdout.flush()
            sys.stderr.flush()
    finally:
        for target, fd in zip((1, 2), saved):
            os.dup2(fd, target)
            os.close(fd)


def parse_output(text, junit=None):
    counts, failed, error = dict(NULL_COUNTS), [], None
    if junit is not None:
        xml = ET.parse(junit).getroot()
        cases = list(xml.iter("testcase"))
        if cases:
            failures = [case for case in cases if case.find("failure") is not None or case.find("error") is not None]
            skipped = sum(case.find("skipped") is not None for case in cases)
            counts = {"passed": len(cases) - len(failures) - skipped, "failed": len(failures), "skipped": skipped}
            failed = [(case.get("classname", "") + "." + case.get("name", "?")).lstrip(".") for case in failures]
            if failures:
                element = failures[0].find("failure")
                if element is None:
                    element = failures[0].find("error")
                error = element.get("message") or (element.text or "").strip() or failed[0]
        else:
            # 没有 testcase 时只接受叶 testsuite 明确、完整的计数，避免父子重复计数。
            leaves = [node for node in xml.iter("testsuite") if not list(node.iter("testcase"))
                      and not list(node.findall("testsuite"))]
            if leaves and all(all(k in node.attrib for k in ("tests", "failures", "errors", "skipped")) for node in leaves):
                totals = {key: sum(int(node.get(key)) for node in leaves)
                          for key in ("tests", "failures", "errors", "skipped")}
                counts = {"passed": totals["tests"] - totals["failures"] - totals["errors"] - totals["skipped"],
                          "failed": totals["failures"] + totals["errors"], "skipped": totals["skipped"]}
    else:
        summaries = list(re.finditer(r"^Ran (\d+) tests? in [^\n]+\n\s*\n(OK(?: \([^\n]*\))?|FAILED \([^\n]*\)|NO TESTS RAN)", text, re.M))
        if summaries:
            counts = {"passed": 0, "failed": 0, "skipped": 0}
            for match in summaries:
                fields = {key.strip(): int(value) for key, value in re.findall(r"([a-z ]+)=(\d+)", match[2])}
                nfailed = fields.get("failures", 0) + fields.get("errors", 0) + fields.get("unexpected successes", 0)
                # expected failures 归 skipped；unexpected successes 属 unittest 真实失败。
                nskip = fields.get("skipped", 0) + fields.get("expected failures", 0)
                counts["failed"] += nfailed
                counts["skipped"] += nskip
                counts["passed"] += int(match[1]) - nfailed - nskip
            failed = re.findall(r"^(?:FAIL|ERROR): (.+)$", text, re.M)
    if any(value is not None and value < 0 for value in counts.values()):
        raise BuildError("测试报告计数非法")
    if error is None:
        lines = text.splitlines()
        error = next((line.strip() for line in lines if "ModuleNotFoundError:" in line), None)
        error = error or next((line.strip() for line in lines if MISSING.search(line)), None)
        if error is None:
            error = next((line.strip() for line in lines if re.search(r"(?:AssertionError|\w+Error):", line)), None)
        if error is None and failed:
            error = failed[0]
    return counts, failed, error


def classify(row, code, text, counts):
    if code == 124:
        return "TIMEOUT", "total-budget-exhausted"
    if code == 127 or MISSING.search(text):
        return "UNVERIFIED", "tool-or-module-unavailable"
    if counts["passed"] is not None and sum(counts.values()) == 0:
        return "UNVERIFIED", "no-tests-executed"
    if row["status"] == "PASS" and code == 0:
        if counts["passed"] is None:
            return "UNVERIFIED", "test-coverage-unverified"
        if counts["failed"]:
            return "FAIL", "test-cases-failed"
        return "PASS", "tests-passed"
    if row["status"] == "FAIL" and counts["failed"]:
        return "FAIL", "test-cases-failed"
    return "UNVERIFIED", row.get("error") or "test-execution-not-verified:" + row["status"]


def summarize(result):
    runs = result["runs"]
    if runs:
        result["counts"] = {key: (sum(run["counts"][key] for run in runs)
                                  if all(run["counts"][key] is not None for run in runs) else None)
                            for key in NULL_COUNTS}
    result["failed_cases"] = [case for run in runs for case in run["failed_cases"]]
    result["primary_error"] = result.get("primary_error") or next(
        (run["primary_error"] for run in runs if run["primary_error"]), None)


def read_status(root, version, build):
    root = Path(root).resolve()
    directory = build_dir(root, version, build)
    try:
        result = load_result(directory)
        if result is None:
            return blank(version, build, None)
        if result["status"] == "RUNNING":
            with (directory / "lifecycle.lock").open("a+b") as stream:
                try:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    return result
                result.update(status="UNVERIFIED", reason="executor-interrupted", reused=True)
                result["primary_error"] = "执行器已退出但无终态；不自动重跑或删除遗留 worktree"
        else:
            result["reused"] = True
        return result
    except (OSError, ValueError, TypeError, KeyError) as exc:
        result = blank(version, build, None, reason="invalid-local-result")
        result["primary_error"] = str(exc)
        return result


def run_build(root, version, build, commit, plan, timeout=3600, retry=False, execution_context=None):
    """plan 可为字典或 JSON 文件路径；只在独立子进程主线程调用（信号/环境/fd 隔离）。"""
    root = Path(root).resolve()
    result = blank(version, build, commit)
    from execution_policy import require_action, PolicyError, validate_test_binding
    try:
        if execution_context is None:
            raise BuildError("版本全量缺可追溯 autopilot 测试委派 execution_context")
        if not isinstance(plan, dict):
            plan = json.loads(Path(plan).read_text(encoding="utf-8"))
        require_action(execution_context, "full-regression")
        validate_test_binding(root, execution_context, version, build, plan)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        status = getattr(exc, "status", "UNVERIFIED")
        result.update(status="UNVERIFIED", reason="action-not-requested" if status == "UNAUTHORIZED" else "policy-unverified",
                      authorization_status="NOT_REQUESTED" if status == "UNAUTHORIZED" else status,
                      executed=False, primary_error=str(exc))
        return result
    try:
        directory = build_dir(root, version, build)
        directory.mkdir(parents=True, exist_ok=True)
        if not math.isfinite(timeout) or timeout <= 0:
            raise BuildError("timeout 必须是正有限秒数")
        if not isinstance(plan, dict):
            plan = json.loads(Path(plan).read_text(encoding="utf-8"))
        plan_hash = digest(plan)
        with (directory / "lifecycle.lock").open("a+b") as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                running = load_result(directory) or blank(version, build, commit, "RUNNING", "executor-active")
                if running.get("commit") != commit or running.get("plan_hash", plan_hash) != plan_hash:
                    raise BuildError("同 build 已有不同 commit/plan 的执行器")
                return running
            previous = load_result(directory)
            if previous:
                load_plan(root, version, build, commit, plan)
                if previous.get("commit") != commit or previous.get("plan_hash") != plan_hash:
                    raise BuildError("同 build 的 commit/plan 已冻结；变更必须使用新 build")
                if previous["status"] == "RUNNING":
                    previous.update(status="UNVERIFIED", reason="executor-interrupted")
                    previous["primary_error"] = "执行器中断；保留现场，不自动重跑或删除遗留 worktree"
                    save_result(directory, previous)
                if not retry or previous["status"] not in {"UNVERIFIED", "TIMEOUT"}:
                    return dict(previous, reused=True)
                atomic_json(directory / f"result-attempt-{previous.get('attempt', 1)}.json", previous)
            reservation = None
            if execution_context is not None:
                from execution_policy import reserve_budget, settle_elapsed
                input_hash = digest({"commit": commit, "plan": plan, "environment": test_ledger.environment_hash()})
                if retry:
                    reserve_budget(root, execution_context, "retries", 1, input_hash, action="full-regression")
                reserve_budget(root, execution_context, "processes", len(plan.get("suites", [])),
                               input_hash, action="full-regression")
                available = reserve_budget(root, execution_context, "elapsed_seconds", 0,
                                           input_hash, action="full-regression")["remaining"]
                timeout = min(timeout, available)
                if timeout <= 0:
                    raise BuildError("任务执行耗时预算已用尽")
                reservation = reserve_budget(root, execution_context, "elapsed_seconds", timeout,
                                             input_hash, action="full-regression")
            result.update(plan_hash=plan_hash, status="RUNNING", reason="validating",
                          attempt=previous.get("attempt", 1) + 1 if previous else 1,
                          started_at=time.time(), deadline_at=time.time() + timeout, pid=os.getpid())
            save_result(directory, result)
            started = time.monotonic()
            completed = execute(root, directory, result, plan, timeout, execution_context, retry)
            if reservation is not None:
                try:
                    settle_elapsed(root, execution_context, reservation, time.monotonic() - started)
                except ValueError as exc:
                    # 测试事实已经落盘；预算结算故障另记，不能把已结束测试留下假RUNNING。
                    completed["budget_error"] = str(exc)
                    save_result(directory, completed)
            return completed
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as exc:
        result.update(status="UNVERIFIED", reason="invalid-request", primary_error=str(exc))
        if getattr(exc, "status", None):
            result.update(policy_status=exc.status, reason="task-policy-stopped", executed=False)
        return result


def execute(root, directory, result, plan, timeout, execution_context, retry=False):
    worktree = directory / "worktree"
    owned = False
    deadline = time.monotonic() + timeout
    expired = False

    def interrupt(signum, frame):
        nonlocal expired
        expired = signum == signal.SIGALRM
        raise BudgetExpired()

    old_handlers = {sig: signal.signal(sig, interrupt) for sig in (signal.SIGALRM, signal.SIGTERM, signal.SIGINT)}
    signal.setitimer(signal.ITIMER_REAL, timeout)
    try:
        load_plan(root, result["version"], result["build"], result["commit"], plan)
        registered = git(root, "worktree", "list", "--porcelain", "-z").split(b"\0")
        if os.path.lexists(worktree) or os.fsencode("worktree " + str(worktree)) in registered:
            raise BuildError("固定 worktree 路径已存在或已注册；拒绝接管或删除")
        # 创建唯一空目录即取得本次清理权限；失败也仅清理本次创建的目录。
        worktree.mkdir()
        owned = True
        git(root, "-c", "core.hooksPath=/dev/null", "worktree", "add", "--detach", str(worktree), result["commit"],
            timeout=max(0.001, deadline - time.monotonic()))
        if plan.get("unit_applicability") is not None:
            # 先过正式用例索引/映射核验，再由验收基线事实判定；不得由缺 runner/空 suites 推出。
            case_ids = validate_case_index(worktree, plan, baseline_root=root)
            acceptance = json.loads(baseline_file(worktree, result["version"], plan["acceptance_baseline"]["path"], root)
                                    .read_text(encoding="utf-8"))
            if not unit_not_applicable(acceptance) or plan["acceptance_tests"]:
                raise BuildError("manifest 声明 unit_applicability，但验收基线并非全部用例 browser_only")
            atomic_json(directory / "plan.json", plan)
            result["testScope"] = {"kind": "version", "version": result["version"], "build": result["build"],
                                   "manifest_hash": digest(plan), "acceptance_baseline": plan["acceptance_baseline"],
                                   "acceptance_tests": [], "dependencies": plan["dependencies"], "case_ids": case_ids,
                                   "unit_applicability": dict(plan["unit_applicability"], browser_only=case_ids)}
            result.update(status="NOT_APPLICABLE", reason=UNIT_NA["reason"], execution_context=str(execution_context),
                          primary_error=None)
            return result
        from test_scope import derive_suite
        runners = [runner for suite in plan["suites"] for runner in suite["runners"]]
        # 推导与账本复核必须在同一隔离环境（如 PYTHONPATH 已清除）下进行，否则依赖分析不可复现。
        with isolated_environment(directory, plan["suites"][0]):
            scope_plan = derive_suite(worktree, runners, plan, execution_context=execution_context)
        if scope_plan.get("unrunnable") or not scope_plan.get("runs"):
            raise BuildError("版本清单存在不可执行项或没有实际测试目标")
        case_ids = validate_case_index(worktree, plan, baseline_root=root)
        atomic_json(directory / "plan.json", plan)
        result["testScope"] = {"kind": "version", "version": result["version"],
                               "build": result["build"], "manifest_hash": digest(plan),
                               "acceptance_baseline": plan["acceptance_baseline"],
                               "acceptance_tests": plan["acceptance_tests"],
                               "dependencies": plan["dependencies"], "case_ids": case_ids}
        result["execution_context"] = str(execution_context)
        result["reason"] = "executing"
        result["worktree"] = str(worktree)
        save_result(directory, result)
        suites = {(suite["cwd"], suite["env_id"]): suite for suite in plan["suites"]}
        for index, run in enumerate(scope_plan["runs"]):
            suite = suites[(run["cwd"], run["env_id"])]
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise BudgetExpired()
            assert_worktree_inputs(worktree, suite)
            log = directory / f"suite-{result['attempt']}-{index + 1}.log"
            row, code = None, None
            with isolated_environment(directory, suite), capture(log):
                row, code = test_ledger.run(root=worktree, cwd=run["cwd"], scope="version",
                                            env_id=run["env_id"], command=run["argv"],
                                            inputs=scope_plan["tests"] + plan["dependencies"], force=bool(retry),
                                            timeout=max(0.001, deadline - time.monotonic()),
                                            ledger_root=directory.parent / "ledger", scope_plan=scope_plan,
                                            execution_context=execution_context)
            if row.get("status") == "CARRIED" or row.get("reused") and row.get("status") == "PASS":
                source_id = row.get("source_run_id", row["run_id"])
                source = None
                for candidate in directory.parent.glob("*/result.json"):
                    previous = load_result(candidate.parent)
                    if previous and previous.get("version") == result["version"]:
                        found = next((item for item in previous.get("runs", []) if item.get("run_id") == source_id
                                      and item.get("status") == "PASS"), None)
                        if found:
                            source = dict(found, source_build=previous["build"])
                            break
                if source is None:
                    raise BuildError("可信复用账本缺原始同版本测试计数与日志，不能假定通过")
                source.update(run_id=row["run_id"], source_run_id=source_id, reused=True,
                              evidence_status=row["status"], reason="unchanged-version-evidence")
                result["runs"].append(source)
                summarize(result)
                save_result(directory, result)
                continue
            text = log.read_text(encoding="utf-8", errors="replace")
            junit = worktree / suite["junit_xml"] if "junit_xml" in suite else None
            counts, failures, error = dict(NULL_COUNTS), [], None
            report_error = None
            try:
                counts, failures, error = parse_output(text, junit)
            except (OSError, ValueError, ET.ParseError) as exc:
                report_error = str(exc)
            status, reason = classify(row, code, text, counts)
            if report_error:
                status, reason, error = "UNVERIFIED", "invalid-test-report", report_error
            if expired or time.monotonic() >= deadline:
                status, reason = "TIMEOUT", "total-budget-exhausted"
            result["runs"].append({"run_id": row["run_id"], "status": status, "reason": reason,
                                   "command": run["argv"], "cwd": run["cwd"],
                                   "env_id": run["env_id"], "inputs": scope_plan["tests"] + plan["dependencies"],
                                   "tests": run["tests"],
                                   "counts": counts, "failed_cases": failures,
                                   "primary_error": error or row.get("error"), "log": str(log),
                                   "exit_code": code})
            summarize(result)
            save_result(directory, result)
            if status == "TIMEOUT":
                break
        statuses = {run["status"] for run in result["runs"]}
        result["status"] = next(status for status in ("TIMEOUT", "FAIL", "UNVERIFIED", "PASS") if status in statuses)
        result["reason"] = {"PASS": "all-suites-passed", "FAIL": "test-cases-failed",
                            "UNVERIFIED": "one-or-more-suites-unverified", "TIMEOUT": "total-budget-exhausted"}[result["status"]]
    except (BudgetExpired, KeyboardInterrupt):
        result.update(status="TIMEOUT" if expired or time.monotonic() >= deadline else "UNVERIFIED",
                      reason="total-budget-exhausted" if expired or time.monotonic() >= deadline else "executor-interrupted")
    except subprocess.TimeoutExpired:
        result.update(status="TIMEOUT", reason="total-budget-exhausted")
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as exc:
        result.update(status="UNVERIFIED", reason="execution-unverified", primary_error=str(exc))
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)
        if owned:
            try:
                git(root, "worktree", "remove", "--force", str(worktree), timeout=30)
            except (BuildError, OSError, subprocess.SubprocessError) as exc:
                # git add 失败且未注册时，只能移除仍为空的自有目录；不递归删除未知内容。
                try:
                    worktree.rmdir()
                except OSError:
                    result.update(status="UNVERIFIED", reason="worktree-cleanup-failed",
                                  primary_error=str(exc))
        result["finished_at"] = time.time()
        summarize(result)
        save_result(directory, result)
    return result


def self_check():
    with tempfile.TemporaryDirectory(prefix="aidp-build-unit-selfcheck-") as temporary:
        root = Path(temporary) / "repo"
        root.mkdir()
        git(root, "init", "-q")
        git(root, "config", "user.email", "selfcheck@example.invalid")
        git(root, "config", "user.name", "Self check")
        (root / ".gitignore").write_text("memory/\n__pycache__/\n")
        (root / "test_sample.py").write_text("import unittest\nclass Sample(unittest.TestCase):\n def test_ok(self): self.assertEqual(2+2,4)\n")
        formal = root / 'docs/testing/V1/正式用例'
        formal.mkdir(parents=True)
        index = formal / '00_索引.md'
        index.write_text('TC-SAMPLE\n')
        (formal / '03_cases.md').write_text('#### 用例 TC-SAMPLE: sample\n')
        acceptance = {'version': 'V1', 'acceptance_tests': ['test_sample.py'], 'dependencies': [],
                      'cases': [{'id': 'TC-SAMPLE', 'test_files': ['test_sample.py']}],
                      'case_index': {'path': index.relative_to(root).as_posix(),
                                     'sha256': hashlib.sha256(index.read_bytes()).hexdigest()}}
        acceptance_path = formal.parent / 'acceptance.json'
        acceptance_path.write_text(json.dumps(acceptance))
        suites = [{"runners": [{'suffixes': ['.py'], 'argv': [sys.executable, '-m', 'unittest', '-v', '{tests}'],
                               'cwd': '.', 'env_id': 'stdlib'}],
                   "cwd": ".", "env_id": "stdlib", "inputs": [], "external_dependencies": "none"}]
        config = json.dumps({"suites": suites}).encode()
        (root / "unit-plan.json").write_bytes(config)
        git(root, "add", ".")
        git(root, "commit", "-qm", "fixture")
        commit = git(root, "rev-parse", "HEAD").decode().strip()
        plan = {"schema": 1, "version": "V1", "build": "build1", "commit": commit,
                "standalone": True, "deployment": {"commit": commit, "verified": True, "evidence": "self-check fixture"},
                "source": {"path": "unit-plan.json", "sha256": hashlib.sha256(config).hexdigest()}, "suites": suites,
                'acceptance_baseline': {'path': acceptance_path.relative_to(root).as_posix(),
                                        'sha256': hashlib.sha256(acceptance_path.read_bytes()).hexdigest()},
                'acceptance_tests': ['test_sample.py'], 'dependencies': []}
        from entry_context import resolve_autopilot_root, fork_test_build
        parent = resolve_autopilot_root(root, 'V1', authorization_source={
            'kind': 'explicit-command', 'command': 'sprint-autopilot', 'request_id': 'self-check',
            'options': ['--skip-dev']})['execution_context']
        manifest = root / 'memory/build1-plan.json'
        atomic_json(manifest, plan)
        child = fork_test_build(root, parent, 'V1', 'build1', manifest=manifest)['execution_context']
        (root / "test_sample.py").write_text("raise RuntimeError('dirty main must never run')\n")
        first = run_build(root, "V1", "build1", commit, plan, execution_context=child)
        second = run_build(root, "V1", "build1", commit, plan, execution_context=child)
        plan["build"] = "build2"
        manifest = root / 'memory/build2-plan.json'
        atomic_json(manifest, plan)
        child = fork_test_build(root, parent, 'V1', 'build2', manifest=manifest)['execution_context']
        third = run_build(root, "V1", "build2", commit, plan, execution_context=child)
        checks = [first["status"] == "PASS", first["counts"] == {"passed": 1, "failed": 0, "skipped": 0},
                  second["reused"], first["runs"] == second["runs"], third["status"] == "PASS",
                  first["runs"][0]["run_id"] != third["runs"][0]["run_id"],
                  not (build_dir(root, "V1", "build1") / "worktree").exists()]
        return {"ok": all(checks), "checks": len(checks)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--self-check", action="store_true")
    sub = parser.add_subparsers(dest="action")
    for action in ("plan-init", "freeze", "run", "status"):
        child = sub.add_parser(action, help="项目侧一次性只读发现测试文件/运行器并写 test-plan.json 草稿；结果经 git 提交后冻结，"
                               "不是运行期全仓发现；已存在不覆盖" if action == "plan-init" else None,
                               description="项目侧一次性只读发现：写计划时扫描项目实际测试文件与运行器，写 docs/testing/{version}/test-plan.json 草稿；"
                               "结果由 git 提交后冻结，不是运行期全仓发现（freeze/run 不发现）。已存在不覆盖，--force 才覆盖。"
                               if action == "plan-init" else None)
        child.add_argument("--root", required=True)
        child.add_argument("--version", required=True)
        if action == "plan-init":
            child.add_argument("--out", help="默认 docs/testing/{version}/test-plan.json")
            child.add_argument("--force", action="store_true", help="覆盖已存在的计划")
            continue
        child.add_argument("--build", required=True)
        if action == "freeze":
            child.add_argument("--commit", required=True)
            child.add_argument("--source", help="部署 commit 内测试计划来源（JSON 或含 aidp-test-plan 围栏的契约卡）；缺省仅查约定位置")
            child.add_argument("--out", help="输出目录，须在 memory/.aidp/version-freeze/{version}/ 下")
        if action == "run":
            child.add_argument("--execution-context", help="继承父任务授权与预算；status只读不消费预算")
            child.add_argument("--commit", required=True)
            child.add_argument("--plan", required=True, help="冻结计划 JSON 文件路径")
            child.add_argument("--timeout", type=float, default=3600, help="全部套件共享总秒数预算")
            child.add_argument("--retry", action="store_true", help="仅显式重试本 build 的 UNVERIFIED/TIMEOUT；不重跑 PASS/FAIL")
    args = parser.parse_args(argv)
    try:
        if args.self_check:
            result = self_check()
            code = 0 if result["ok"] else 1
        elif args.action == "run":
            result = run_build(args.root, args.version, args.build, args.commit, args.plan, args.timeout, args.retry, args.execution_context)
            code = 0  # 业务结论只由 JSON 表达，FAIL/TIMEOUT 不终止实测链路。
        elif args.action == "plan-init":
            result = plan_init(args.root, args.version, args.out, args.force)
            code = 0
        elif args.action == "freeze":
            result = freeze(args.root, args.version, args.build, args.commit, args.source, args.out)
            code = 0 if result["status"] == "FROZEN" else 3  # 冻结失败须让围栏记账，不能静默继续委派。
        elif args.action == "status":
            result = read_status(args.root, args.version, args.build)
            code = 0
        else:
            parser.error("需要 run/status 或 --self-check")
    except (OSError, ValueError, TypeError, KeyError) as exc:
        result = {"schema": SCHEMA, "status": "UNVERIFIED", "reason": str(exc), "reused": False}
        code = 0
    print(json.dumps(result, ensure_ascii=args.action not in ("freeze", "plan-init"), sort_keys=True), flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
