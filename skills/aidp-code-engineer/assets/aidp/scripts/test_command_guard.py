#!/usr/bin/env python3
"""测试/静态检查命令护栏：把「只跑相关测试」从文字约定变成机器判定。

API：evaluate(command, root=".", execution_context=None, allow_full=False)
     -> {"allowed","reason","hint","kind"}；kind=none 表示不是测试命令（放行）。
CLI：
  check --command STR [--root .] [--execution-context CTX] [--json]   允许退 0，拒绝退 2
  wrap [--allow-full] [--background --log FILE] [--root .] [--execution-context CTX] -- CMD...
       先 evaluate 再执行；--background 时分离执行，输出写 FILE，结束写 FILE.exit（内容为退出码）
  changed [--root .] [--ext .py ...]       打印改动文件（git diff HEAD + 未跟踪），供 ruff 等只检查改动
规则：无位置参数或参数为目录 → 拒绝；显式文件须属于白名单（memory/.aidp/test-allowlist/<key>.json，
由 select_related_tests.py 生成）。有上下文时仅接受本任务白名单，缺失/损坏/身份错误即拒绝；
无上下文时只读取 default，缺失时按显式文件放行并提示；--allow-full 仅当执行上下文真实持有
full-regression（autopilot 测试编排 fork 子任务，复用 execution_policy.require_action）才放行，缺授权 fail closed。
git stash（push/save/无子命令/-u）一律拒绝：基线对照改用 test_baseline.py 或 git worktree。
执行上下文也可由环境变量 AIDP_EXECUTION_CONTEXT 提供。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path, PurePosixPath

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ALLOWLIST_DIR = "memory/.aidp/test-allowlist"
SEPARATORS = {"&&", "||", ";", "|", "&", ";;", "|&", "(", ")", "&;"}
REDIRECTS = {">", ">>", "<", "<<", "<<<", ">&", "<&", "&>", "&>>", ">|"}
WRAPPERS = {"nohup", "time", "command", "exec", "sudo", "nice", "ionice", "stdbuf", "xargs", "setsid", "builtin"}
RUNNER_PREFIX = (("uv", "run"), ("poetry", "run"), ("pipenv", "run"), ("pdm", "run"), ("pnpm", "exec"),
                 ("npm", "exec"), ("yarn", "run"), ("pnpm", "dlx"), ("rye", "run"), ("hatch", "run"))
BARE_RUNNERS = {"npx", "pnpx", "bunx"}
SHELLS = {"bash", "sh", "zsh", "dash"}
RUN_TESTS = re.compile(r"^(run[_-]?tests?|runtests?)([._-].*)?$", re.I)
ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
STASH_SAFE = {"pop", "apply", "list", "show", "drop", "clear", "branch", "create", "store"}
PYTEST_VALUE = {"-k", "-m", "-c", "-p", "-o", "-W", "-n", "-r", "--maxfail", "--rootdir", "--tb", "--junitxml",
                "--junit-xml", "--ignore", "--ignore-glob", "--deselect", "--durations", "--durations-min",
                "--basetemp", "--capture", "--color", "--confcutdir", "--override-ini", "--import-mode",
                "--log-level", "--log-file", "--numprocesses", "--dist", "--timeout", "--reruns",
                "--randomly-seed", "--html", "--splits", "--group", "--workers", "--asyncio-mode", "--cov-report",
                "--cov-config", "--cache-clear-dir", "--log-cli-level", "--junit-prefix", "--result-log"}
RUFF_VALUE = {"--select", "--ignore", "--extend-select", "--extend-ignore", "--config", "--exclude", "--extend-exclude",
              "--output-format", "--target-version", "--line-length", "--per-file-ignores", "--cache-dir",
              "--fixable", "--unfixable", "--stdin-filename", "--output-file"}
JEST_VALUE = {"-t", "--testNamePattern", "-c", "--config", "--maxWorkers", "-w", "--reporters", "--coverageReporters",
              "--env", "--rootDir", "--testMatch", "--shard", "--outputFile", "--testPathIgnorePatterns",
              "--project", "--projects", "--root", "-r", "--reporter", "--testTimeout", "--pool", "--mode",
              "--changed", "--coverageDirectory", "--setupFiles", "--cacheDirectory", "--testEnvironment"}
GO_VALUE = {"-run", "-bench", "-count", "-timeout", "-tags", "-p", "-parallel", "-cpu", "-coverprofile", "-covermode",
            "-coverpkg", "-o", "-skip", "-shuffle", "-vet", "-mod", "-ldflags", "-gcflags", "-fuzz", "-fuzztime"}
GENERIC_VALUE = {"-c", "--config", "-p", "-n", "--filter", "--project", "--test", "--package", "--exclude",
                 "-f", "--format", "-o", "--out", "--tag", "-t", "--testNamePattern", "--features"}
FULL_RUN_PREFIX = "--allow-full"


def _result(allowed, reason="", hint="", kind="none"):
    return {"allowed": allowed, "reason": reason, "hint": hint, "kind": kind}


# ---------------------------------------------------------------- 命令解析

def _split_newlines(command):
    out, quote, i = [], "", 0
    while i < len(command):
        ch = command[i]
        if quote:
            if ch == "\\" and quote == '"' and i + 1 < len(command):
                out.append(command[i:i + 2]); i += 2; continue
            if ch == quote:
                quote = ""
            out.append(ch)
        elif ch in "'\"":
            quote = ch; out.append(ch)
        elif ch == "\\" and i + 1 < len(command):
            out.append(command[i:i + 2]); i += 2; continue
        elif ch == "\n":
            out.append(" ; ")
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def _tokens(command):
    text = _split_newlines(command)
    try:
        lex = shlex.shlex(text, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        lex.commenters = ""
        return list(lex)
    except ValueError:
        return text.split()


def _segments(command):
    segs, cur, skip_next = [], [], False
    toks = _tokens(command)
    for idx, tok in enumerate(toks):
        if skip_next:
            skip_next = False
            continue
        if tok in SEPARATORS or (set(tok) <= set("&|;()") and tok):
            if cur:
                segs.append(cur)
            cur = []
        elif tok in REDIRECTS:
            skip_next = True
            if cur and cur[-1].isdigit():
                cur.pop()
        else:
            cur.append(tok)
    if cur:
        segs.append(cur)
    return segs


def _strip_prefix(seg):
    """去掉环境变量前缀与包装器，返回 (cd 目标或 None, 剩余 argv)。"""
    argv = list(seg)
    while argv:
        head = argv[0]
        base = os.path.basename(head)
        if ENV_ASSIGN.match(head):
            argv.pop(0)
        elif base == "env":
            argv.pop(0)
            while argv and (argv[0].startswith("-") or ENV_ASSIGN.match(argv[0])):
                argv.pop(0)
        elif base == "timeout":
            argv.pop(0)
            while argv and argv[0].startswith("-"):
                opt = argv.pop(0)
                if opt in ("-s", "-k", "--signal", "--kill-after") and argv:
                    argv.pop(0)
            if argv and re.fullmatch(r"[0-9.]+[smhd]?", argv[0]):
                argv.pop(0)
        elif base in WRAPPERS:
            argv.pop(0)
            while argv and argv[0].startswith("-") and base != "time":
                opt = argv.pop(0)
                if base in ("nice", "ionice", "stdbuf") and "=" not in opt and len(opt) == 2 and argv and argv[0].lstrip("-").isdigit():
                    argv.pop(0)
        elif head in BARE_RUNNERS:
            argv.pop(0)
            while argv and argv[0].startswith("-"):
                argv.pop(0)
        elif len(argv) > 1 and (base, argv[1]) in RUNNER_PREFIX:
            # yarn run test 是包脚本入口，不能剥成无语义的裸 test。
            if base == "yarn" and len(argv) > 2 and argv[2] in ("test", "tests", "test:unit", "test:ci"):
                break
            del argv[:2]
        else:
            break
    return argv


def _split_args(args, value_opts):
    """返回 (positionals, flags, values)；-- 之后全部视为位置参数。"""
    pos, flags, i = [], [], 0
    while i < len(args):
        a = args[i]
        if a == "--":
            pos.extend(args[i + 1:])
            break
        if a.startswith("-") and len(a) > 1:
            if "=" in a:
                flags.append(a.split("=", 1)[0])
            elif a in value_opts:
                flags.append(a)
                i += 1
            else:
                flags.append(a)
        else:
            pos.append(a)
        i += 1
    return pos, flags


# ---------------------------------------------------------------- 白名单与授权

def _context_key(root, ctx):
    if not ctx:
        return None
    from test_scope import execution_context_data
    return execution_context_data(root, ctx)["task_id"]


def _safe(key):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", key).strip(".") or "default"


def load_allowlist(root, ctx):
    """只读取本任务白名单；无上下文时只读取 default，不借用其他任务记录。"""
    key = _context_key(root, ctx)
    path = Path(root) / ALLOWLIST_DIR / f"{_safe(key) if key else 'default'}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        if key is None:
            return None, None
        raise ValueError(f"本任务相关测试白名单缺失：{path}") from exc
    except (OSError, ValueError) as exc:
        raise ValueError(f"相关测试白名单不可读：{path}（{exc}）") from exc
    if not isinstance(data, dict) or (key is not None and data.get("task_id") != key):
        raise ValueError(f"相关测试白名单任务身份不一致：{path}")
    if key is None and data.get("task_id", "default") != "default":
        raise ValueError(f"default 白名单不属于无上下文选测：{path}")
    tests = data.get("tests")
    if not isinstance(tests, list) or not all(isinstance(test, str) and test for test in tests):
        raise ValueError(f"相关测试白名单 tests 必须为文件路径数组：{path}")
    return set(tests), path


def _full_authorized(root, ctx):
    ctx = ctx or os.environ.get("AIDP_EXECUTION_CONTEXT") or None
    if not ctx:
        return False, "缺少 execution_context（--execution-context 或 AIDP_EXECUTION_CONTEXT）"
    try:
        import execution_policy as policy
        current = policy.require_action(ctx, "full-regression")
        sources = current.get("authorization_source") or []
        if isinstance(sources, dict):
            sources = [sources]
        if not any(policy._autopilot_source(s) for s in sources):
            return False, "授权来源不是 autopilot 测试编排"
        return True, ""
    except Exception as exc:  # noqa: BLE001 — 授权校验任何异常都 fail closed
        return False, f"full-regression 未获真实授权：{exc}"


# ---------------------------------------------------------------- 各类命令判定

FULL_HINT = ("只跑相关测试：python3 {{AIDP_HOME}}/scripts/select_related_tests.py --json 取白名单后传显式文件；"
             "全量仅由 autopilot 测试编排授权（--allow-full 且上下文持有 full-regression）")


def _norm(root, cwd, arg):
    path = os.path.normpath(os.path.join(cwd, arg))
    try:
        return PurePosixPath(Path(path).resolve().relative_to(Path(root).resolve()).as_posix()), Path(path)
    except ValueError:
        return None, Path(path)


def _is_dir_arg(arg, abspath):
    return arg in (".", "..") or arg.endswith(("/", os.sep, "/...")) or abspath.is_dir()


def _check_files(kind, args_pos, root, cwd, allow, allow_path, strict_file=True):
    """位置参数全部须为显式文件（可带 ::node）；返回 None 表示通过，否则 deny 结果。"""
    outside, bad = [], []
    for raw in args_pos:
        arg = raw.split("::", 1)[0]
        rel, absp = _norm(root, cwd, arg)
        if _is_dir_arg(arg, absp):
            return _result(False, f"{kind}：参数 {raw!r} 是目录，等同整目录运行", FULL_HINT, kind)
        if strict_file and not absp.is_file() and not PurePosixPath(arg).suffix:
            bad.append(raw)
            continue
        if allow is not None and (rel is None or rel.as_posix() not in allow):
            outside.append(raw)
    if bad:
        return _result(False, f"{kind}：参数 {bad} 不是已存在的显式测试文件", FULL_HINT, kind)
    if outside:
        return _result(False, f"{kind}：{outside} 不在相关测试白名单内（{allow_path}）",
                       "先运行 select_related_tests.py 重新生成白名单（写集/改动已变化时），或只跑白名单内文件", kind)
    return None


def _no_args(kind, what="未指定任何测试文件"):
    return _result(False, f"{kind}：{what}，等同全量运行", FULL_HINT, kind)


def _pytest(args, ctx):
    root, cwd, allow, allow_path = ctx
    pos, flags = _split_args(args, PYTEST_VALUE)
    if set(flags) & {"-h", "--help", "--version", "--fixtures", "--markers"}:
        return _result(True, "", "", "pytest")
    if not pos:
        return _no_args("pytest")
    denied = _check_files("pytest", pos, root, cwd, allow, allow_path)
    return denied or _result(True, "", "" if allow is not None else "未发现白名单文件，已按显式文件放行（建议先跑 select_related_tests.py）", "pytest")


def _unittest(args, ctx):
    root, cwd, allow, allow_path = ctx
    pos, flags = _split_args(args, {"-k", "-s", "-t", "-p"})
    if not pos or pos[0] == "discover":
        return _no_args("unittest", "discover/无参数")
    converted = []
    for p in pos:
        if (cwd / p).exists() or "/" in p or p.endswith(".py"):
            converted.append(p)
        else:
            parts = p.split(".")
            for n in range(len(parts), 0, -1):
                cand = "/".join(parts[:n]) + ".py"
                if (cwd / cand).is_file():
                    converted.append(cand)
                    break
            else:
                return _result(False, f"unittest：无法把 {p!r} 解析为测试文件", FULL_HINT, "other-test")
    denied = _check_files("unittest", converted, root, cwd, allow, allow_path)
    return _retag(denied, "other-test") or _result(True, "", "", "other-test")


def _retag(res, kind):
    if res:
        res["kind"] = kind
    return res


def _run_tests(args, ctx):
    root, cwd, allow, allow_path = ctx
    pos, flags = _split_args(args, GENERIC_VALUE)
    if set(flags) & {"--related", "--changed"}:
        return _result(True, "", "入口脚本自行计算白名单并经 test_command_guard wrap 复核", "run_tests")
    if not pos:
        return _no_args("run_tests")
    denied = _check_files("run_tests", pos, root, cwd, allow, allow_path)
    return denied or _result(True, "", "", "run_tests")


def _ruff(args, ctx):
    root, cwd, _, _ = ctx
    pos, flags = _split_args(args, RUFF_VALUE)
    sub = pos[0] if pos else ""
    if sub not in ("check", "format"):
        return _result(True, "", "", "ruff")
    targets = pos[1:]
    if set(flags) & {"-h", "--help", "--version"}:
        return _result(True, "", "", "ruff")
    hint = "ruff 默认只检查改动文件：ruff check $(python3 {{AIDP_HOME}}/scripts/test_command_guard.py changed --ext .py)"
    if not targets:
        return _result(False, "ruff：未指定文件，等同检查整个项目", hint, "ruff")
    for t in targets:
        if t == "-":
            continue
        _, absp = _norm(root, cwd, t)
        if _is_dir_arg(t, absp):
            return _result(False, f"ruff：参数 {t!r} 是目录，等同整目录检查", hint, "ruff")
    return _result(True, "", "", "ruff")


def _jest(tool, args, ctx):
    root, cwd, allow, allow_path = ctx
    kind = "vitest" if tool == "vitest" else "jest"
    pos, flags = _split_args(args, JEST_VALUE)
    if set(flags) & {"-h", "--help", "--version", "--listTests"}:
        return _result(True, "", "", kind)
    if pos and pos[0] in ("run", "related", "bench"):
        if pos[0] == "related":
            flags.append("--findRelatedTests")
        pos = pos[1:]
    scoped_changed = set(flags) & {"-o", "--onlyChanged", "--changedSince", "--changed"}
    if not pos:
        if scoped_changed:
            return _result(True, "", "按 git 改动选测", kind)
        return _no_args(kind)
    denied = _check_files(kind, pos, root, cwd, allow if "--findRelatedTests" not in flags else None, allow_path)
    return denied or _result(True, "", "", kind)


_MVN_PHASES = {"test", "verify", "package", "install", "integration-test", "deploy", "surefire:test", "failsafe:integration-test"}


def _class_stems(allow):
    return {PurePosixPath(t).stem for t in allow} if allow is not None else None


def _mvn(args, ctx):
    root, cwd, allow, allow_path = ctx
    skip = any(re.match(r"-D(skipTests|maven\.test\.skip)(=true)?$", a) for a in args)
    phases = [a for a in args if not a.startswith("-") and a in _MVN_PHASES]
    if not phases or skip:
        return _result(True, "", "", "mvn")
    spec = None
    for i, a in enumerate(args):
        if a.startswith("-Dtest="):
            spec = a.split("=", 1)[1]
        elif a == "-Dtest" and i + 1 < len(args):
            spec = args[i + 1]
    if not spec:
        return _no_args("mvn", f"{phases[0]} 未带 -Dtest=<测试类>")
    return _named_tests("mvn", [s for s in spec.split(",") if s], allow, allow_path)


def _named_tests(kind, names, allow, allow_path):
    stems = _class_stems(allow)
    for n in names:
        cls = n.split("#", 1)[0].split(".")[-1]
        if not cls or "*" in cls or "?" in cls:
            return _result(False, f"{kind}：测试选择器 {n!r} 含通配或为空，等同批量运行", FULL_HINT, kind)
        if stems is not None and cls not in stems:
            return _result(False, f"{kind}：{n!r} 不在相关测试白名单内（{allow_path}）",
                           "先运行 select_related_tests.py 重新生成白名单，或只跑白名单内的测试类", kind)
    return _result(True, "", "" if stems is not None else "未发现白名单文件，已按显式测试类放行", kind)


def _gradle(args, ctx):
    root, cwd, allow, allow_path = ctx
    tasks = [a.split(":")[-1] for a in args if not a.startswith("-")]
    excluded = {args[i + 1].split(":")[-1] for i, a in enumerate(args[:-1]) if a in ("-x", "--exclude-task")}
    runs = [t for t in tasks if t in ("test", "check", "build", "integrationTest", "allTests", "jvmTest")]
    if not set(runs) - excluded:
        return _result(True, "", "", "gradle")
    names = []
    for i, a in enumerate(args):
        if a == "--tests" and i + 1 < len(args):
            names.append(args[i + 1])
        elif a.startswith("--tests="):
            names.append(a.split("=", 1)[1])
    if not names:
        return _no_args("gradle", f"{runs[0]} 未带 --tests <测试类>")
    return _named_tests("gradle", names, allow, allow_path)


def _go(args, ctx):
    root, cwd, allow, allow_path = ctx
    pos, flags = _split_args(args, GO_VALUE)
    if not pos:
        return _no_args("go", "go test 未指定测试文件/包")
    scoped = any(f.startswith(("-run", "-fuzz")) for f in flags)
    files = [p for p in pos if p.endswith(".go")]
    if files and len(files) == len(pos):
        return _check_files("go", files, root, cwd, allow, allow_path) or _result(True, "", "", "go")
    for p in pos:
        if p.endswith("...") or p in (".", "./", "..") :
            return _result(False, f"go test：{p!r} 是整包/整目录范围", FULL_HINT, "go")
        _, absp = _norm(root, cwd, p)
        rel, _a = _norm(root, cwd, p)
        if absp.is_dir():
            if not scoped:
                return _result(False, f"go test：包目录 {p!r} 未带 -run 限定，等同整包运行", FULL_HINT, "go")
            if allow is not None and rel is not None and not any(PurePosixPath(t).parent == rel for t in allow):
                return _result(False, f"go test：包 {p!r} 内没有白名单测试（{allow_path}）",
                               "先运行 select_related_tests.py 重新生成白名单", "go")
    return _result(True, "", "", "go")


def _generic_test(tool, args, ctx):
    root, cwd, allow, allow_path = ctx
    pos, flags = _split_args(args, GENERIC_VALUE)
    if set(flags) & {"-h", "--help", "--version"}:
        return _result(True, "", "", "other-test")
    if flags and set(flags) & {"--filter", "--test", "--tests", "-t", "--testNamePattern"} and tool in ("cargo", "dotnet"):
        return _result(True, "", "", "other-test")
    if not pos:
        return _no_args("other-test", f"{tool} 未指定测试文件")
    denied = _check_files(tool, pos, root, cwd, allow, allow_path)
    return _retag(denied, "other-test") or _result(True, "", "", "other-test")


def _git_stash(args):
    sub = next((a for a in args if not a.startswith("-")), "")
    if sub in STASH_SAFE:
        return None
    return _result(False, "git stash：会连同未跟踪/未提交文件一并带走，做「基线对照」会让基线那次实际未执行却看似正常",
                   "基线对照请用 test_baseline.py 记录已知失败基线，或 git worktree add 取干净副本", "other-test")


def _classify(argv, ctx_tuple, depth=0):
    """单段命令 → 结果；None 表示不是受管命令。"""
    argv = _strip_prefix(argv)
    if not argv:
        return None
    head, rest = argv[0], argv[1:]
    base = os.path.basename(head)
    name = re.sub(r"\.(exe|cmd|bat)$", "", base)
    if name == "git":
        i = 0
        while i < len(rest) and rest[i].startswith("-"):
            i += 2 if rest[i] in ("-C", "-c", "--git-dir", "--work-tree") else 1
        if i < len(rest) and rest[i] == "stash":
            return _git_stash(rest[i + 1:])
        return None
    if name in SHELLS or name == "eval":
        if name == "eval":
            return _evaluate_text(" ".join(rest), ctx_tuple, depth + 1) if depth < 3 else None
        for idx, a in enumerate(rest):
            if re.fullmatch(r"-[a-z]*c[a-z]*", a) and idx + 1 < len(rest):
                return _evaluate_text(rest[idx + 1], ctx_tuple, depth + 1) if depth < 3 else None
        script = next((a for a in rest if not a.startswith("-")), "")
        if script and RUN_TESTS.match(os.path.basename(script)):
            return _run_tests([a for a in rest if a != script], ctx_tuple)
        return None
    if RUN_TESTS.match(base):
        return _run_tests(rest, ctx_tuple)
    if re.fullmatch(r"python[0-9.]*|py|pypy[0-9]*", name):
        if "-m" in rest:
            mod = rest.index("-m")
            module, margs = (rest[mod + 1] if mod + 1 < len(rest) else ""), rest[mod + 2:]
            if module in ("pytest", "py.test"):
                return _pytest(margs, ctx_tuple)
            if module == "unittest":
                return _unittest(margs, ctx_tuple)
            if module == "ruff":
                return _ruff(margs, ctx_tuple)
            if module in ("tox", "nox"):
                return _generic_test(module, margs, ctx_tuple)
            return None
        script = next((a for a in rest if not a.startswith("-")), "")
        if script and RUN_TESTS.match(os.path.basename(script)):
            return _run_tests([a for a in rest if a != script], ctx_tuple)
        from test_scope import is_test
        script_path = (ctx_tuple[1] / script).resolve()
        # 仅本安装的构建元数据子命令不是测试执行；同名外部脚本与 run 仍受管。
        script_args = rest[rest.index(script) + 1:] if script else []
        if (script_path == Path(__file__).resolve().with_name("build_unit_test.py")
                and script_args[:1] in (["plan-init"], ["freeze"], ["status"])):
            return None
        if script.endswith(".py") and is_test(script) and script_path.is_file():
            return (_check_files("other-test", [script], *ctx_tuple)
                    or _result(True, "", "", "other-test"))
        return None
    if name in ("node", "nodejs") and "--test" in rest:
        pos, flags = _split_args(rest, {"--test-name-pattern", "--test-skip-pattern", "--test-concurrency",
                                       "--test-reporter", "--test-reporter-destination", "--test-shard",
                                       "--test-timeout", "--require", "-r", "--import", "--loader"})
        if not pos:
            return _no_args("node-test")
        return (_check_files("node-test", pos, *ctx_tuple)
                or _result(True, "", "", "node-test"))
    if name in ("pytest", "py.test"):
        return _pytest(rest, ctx_tuple)
    if name == "ruff":
        return _ruff(rest, ctx_tuple)
    if name in ("jest", "vitest"):
        return _jest(name, rest, ctx_tuple)
    if name in ("mvn", "mvnw", "mvnd"):
        return _mvn(rest, ctx_tuple)
    if name in ("gradle", "gradlew"):
        return _gradle(rest, ctx_tuple)
    if name == "go" and rest[:1] == ["test"]:
        return _go(rest[1:], ctx_tuple)
    if name in ("cargo", "dotnet") and rest[:1] == ["test"]:
        return _generic_test(name, rest[1:], ctx_tuple)
    if name in ("rspec", "phpunit", "tox", "nox", "nosetests", "karma", "mocha", "ava", "playwright", "cypress"):
        if name in ("playwright", "cypress") and rest[:1] not in (["test"], ["run"]):
            return None
        return _generic_test(name, rest[1:] if name in ("playwright", "cypress") else rest, ctx_tuple)
    if name in ("npm", "pnpm", "yarn", "bun"):
        sub = rest[0] if rest else ""
        if sub in ("test", "t", "tst") or (sub in ("run", "run-script") and len(rest) > 1 and rest[1] in ("test", "tests", "test:unit", "test:ci")):
            tail = rest[1:] if sub in ("test", "t", "tst") else rest[2:]
            pos, flags = _split_args(tail, JEST_VALUE)
            return _generic_jest_like(pos, flags, tail, ctx_tuple)
        return None
    if name == "make" and any(a in ("test", "tests", "check", "unittest") for a in rest if not a.startswith("-")):
        return _no_args("other-test", "make test 无法限定测试范围")
    return None


def _generic_jest_like(pos, flags, tail, ctx):
    root, cwd, allow, allow_path = ctx
    files = [p for p in pos if p != "--"]
    scoped = set(flags) & {"-o", "--onlyChanged", "--changedSince", "--findRelatedTests", "--changed"}
    if not files:
        return _result(True, "", "按 git 改动选测", "jest") if scoped else _no_args("other-test", "npm test 未指定测试文件")
    denied = _check_files("npm test", files, root, cwd, allow if "--findRelatedTests" not in flags else None, allow_path)
    return _retag(denied, "other-test") or _result(True, "", "", "other-test")


def _evaluate_text(command, ctx_tuple, depth=0):
    root = ctx_tuple[0]
    cwd = ctx_tuple[1]
    first = None
    for seg in _segments(command):
        argv = _strip_prefix(seg)
        if argv and os.path.basename(argv[0]) == "cd":
            target = argv[1] if len(argv) > 1 else ""
            if target and target != "-":
                cwd = Path(os.path.normpath(os.path.join(cwd, os.path.expanduser(target))))
            continue
        res = _classify(seg, (root, cwd) + tuple(ctx_tuple[2:]), depth)
        if res is None:
            continue
        if not res["allowed"]:
            return res
        first = first or res
    return first


def evaluate(command, root=".", execution_context=None, allow_full=False):
    root = Path(root).resolve()
    ctx = execution_context or os.environ.get("AIDP_EXECUTION_CONTEXT") or None
    wants_full = bool(allow_full) or FULL_RUN_PREFIX in command.split()
    if wants_full:
        command_wo = " ".join(t for t in command.split() if t != FULL_RUN_PREFIX)
    else:
        command_wo = command
    # 普通命令与入口元数据不消费测试身份或白名单，错误 ctx 也不改变命令分类。
    if _evaluate_text(command_wo, (root, root, None, None)) is None:
        return _result(True)
    allow_error = None
    try:
        allow, allow_path = load_allowlist(root, ctx)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        allow, allow_path = set(), None
        allow_error = str(exc)
    res = _evaluate_text(command_wo, (root, root, allow, allow_path))
    if res is None:
        return _result(True)
    if wants_full and not res["reason"].startswith("git stash"):
        # 声明 --allow-full 的测试命令一律核验真实授权；缺授权 fail closed
        ok, why = _full_authorized(root, ctx)
        if ok:
            return _result(True, "full-regression 已由 autopilot 授权放行", "", res["kind"])
        return _result(False, f"--allow-full 被拒绝：{why}", FULL_HINT, res["kind"])
    if allow_error and res["kind"] != "ruff":
        return _result(False, f"相关测试白名单校验失败：{allow_error}", FULL_HINT, res["kind"])
    return res


# ---------------------------------------------------------------- CLI

def changed_files(root, exts=()):
    def out(*a):
        r = subprocess.run(["git", "-C", str(root), *a], capture_output=True, timeout=30)
        return [os.fsdecode(p) for p in r.stdout.split(b"\0") if p] if r.returncode == 0 else []
    names = set(out("diff", "--name-only", "--no-renames", "-z", "HEAD", "--"))
    names.update(out("ls-files", "--others", "--exclude-standard", "-z"))
    return sorted(n for n in names if (Path(root) / n).is_file() and (not exts or n.endswith(tuple(exts))))


def _wrap(args):
    cmd = list(args.cmd)
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        print("wrap：缺少要执行的命令", file=sys.stderr)
        return 2
    res = evaluate(shlex.join(cmd), args.root, args.execution_context, args.allow_full)
    if not res["allowed"]:
        print(f"[test_command_guard] 拒绝：{res['reason']}\n提示：{res['hint']}", file=sys.stderr)
        return 2
    if res.get("hint"):
        print(f"[test_command_guard] {res['hint']}", file=sys.stderr)
    if not args.background:
        try:
            return subprocess.call(cmd, cwd=args.root)
        except OSError as exc:
            print(f"[test_command_guard] 无法执行 {cmd[0]}：{exc}", file=sys.stderr)
            return 127
    if not args.log:
        print("wrap --background 需要 --log FILE", file=sys.stderr)
        return 2
    log = Path(args.log).resolve()
    marker = Path(str(log) + ".exit")
    log.parent.mkdir(parents=True, exist_ok=True)
    marker.unlink(missing_ok=True)
    script = '"$@" > "$LOG" 2>&1; rc=$?; echo "$rc" > "$MARK.tmp"; mv "$MARK.tmp" "$MARK"'
    subprocess.Popen(["bash", "-c", script, "_", *cmd], cwd=args.root, start_new_session=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     env=dict(os.environ, LOG=str(log), MARK=str(marker)))
    print(json.dumps({"log": str(log), "exit_marker": str(marker)}, ensure_ascii=False))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="mode", required=True)
    chk = sub.add_parser("check")
    chk.add_argument("--command", required=True)
    chk.add_argument("--root", default=".")
    chk.add_argument("--execution-context", default=None)
    chk.add_argument("--json", action="store_true")
    wr = sub.add_parser("wrap")
    wr.add_argument("--allow-full", action="store_true")
    wr.add_argument("--background", action="store_true")
    wr.add_argument("--log", default="")
    wr.add_argument("--root", default=".")
    wr.add_argument("--execution-context", default=None)
    wr.add_argument("cmd", nargs=argparse.REMAINDER)
    ch = sub.add_parser("changed")
    ch.add_argument("--root", default=".")
    ch.add_argument("--ext", action="append", default=[])
    args = parser.parse_args(argv)
    if args.mode == "check":
        res = evaluate(args.command, args.root, args.execution_context)
        if args.json:
            print(json.dumps(res, ensure_ascii=False))
        elif not res["allowed"]:
            print(f"拒绝：{res['reason']}\n提示：{res['hint']}", file=sys.stderr)
        return 0 if res["allowed"] else 2
    if args.mode == "changed":
        print("\n".join(changed_files(Path(args.root), args.ext)))
        return 0
    return _wrap(args)


if __name__ == "__main__":
    sys.exit(main())
