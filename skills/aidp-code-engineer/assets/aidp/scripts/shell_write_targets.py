#!/usr/bin/env python3
"""静态识别常见 shell 写目标；不执行命令，不把未知动态写入当成安全。

API analyze(command, cwd, env=None) -> {targets, uncertain, reasons}。
这是入口协议的误操作护栏，不是任意程序/恶意 shell 的安全沙箱。
"""
from __future__ import annotations

import ast
import os
from pathlib import Path
import re
import shlex
import uuid

from aidp_paths import runtime_dir

ASSIGN = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", re.S)
VARIABLE = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")
SHELLS = {"bash", "sh", "dash", "zsh"}
WRITERS = {"sed", "tee", "cp", "mv", "install", "rm", "touch", "mkdir", "truncate", "chmod", "chown", "ln"}
SEPARATORS = {";", "&&", "||", "|", "&", "|&", "(", ")"}
REDIRECTS = {">", ">>", ">|", "&>", "&>>", ">&", "<", "<<", "<<<", "<&", "<>"}


def command_text(value):
    """Claude string / Codex argv；argv 必须 quote 后再解析，不能空格拼接。"""
    if isinstance(value, str) and value.strip():
        return value
    if isinstance(value, list) and value and all(isinstance(x, str) for x in value):
        return shlex.join(value)
    raise ValueError("shell command 必须是非空字符串或 argv 字符串数组")


def _tokens(text):
    # 保留引号内换行；外部换行是命令分隔符。
    out, quote, escaped, comment = [], None, False, False
    for char in text:
        if comment:
            if char != "\n":
                continue
            comment = False
        if not quote and not escaped and char == "#" and (not out or out[-1][-1:] in " \t;|&()"):
            comment = True
            continue
        if escaped:
            out.append(char)
            escaped = False
            continue
        if char == "\\" and quote != "'":
            escaped = True
        elif char in "\"'":
            if quote == char:
                quote = None
            elif quote is None:
                quote = char
        out.append(" ; " if char == "\n" and quote is None else char)
    lex = shlex.shlex("".join(out), posix=True, punctuation_chars=";&|<>()")
    lex.whitespace_split = True
    lex.commenters = ""
    return list(lex)


class _Analysis:
    def __init__(self):
        self.targets = []
        self.writes = []
        self.reasons = []
        self.trusted_eval = set()
        self.cwd_mutation = False
        self.metadata_operations_only = True
        self.command_variables = set()
        self.conditional_assignments = set()

    def unknown(self, reason):
        if reason not in self.reasons:
            self.reasons.append(reason)

    def expand(self, value, env):
        def substitute(match):
            name = match.group(1) or match.group(2)
            return str(env[name]) if name in env else match.group(0)
        value = VARIABLE.sub(substitute, value)
        # 连先前的 cwd 命令别名也保留：分支末次赋值不能抹掉另一条路径上的 cd。
        if re.search(r"(?:^|\s)(?:cd|pushd|popd)(?:\s|$)", value):
            self.cwd_mutation = True
        if "__AIDP_DYNAMIC" in value or any(c in value for c in ("$", "`", "*", "?", "[", "{", "\n", "\x00")):
            return None
        return value

    def path(self, value, cwd, env):
        value = self.expand(value, env)
        if not value or value == "-":
            return None
        if value.startswith("~/"):
            home = env.get("HOME")
            if not home:
                return None
            value = home + value[1:]
        elif value.startswith("~"):
            return None
        path = Path(value)
        return str(Path(os.path.normpath(path if path.is_absolute() else Path(cwd) / path)))

    def write(self, value, cwd, env, *, metadata=False):
        # 条件元数据例外只覆盖重定向/mkdir；ln/cp/mv 等可能改变后续路径含义。
        self.metadata_operations_only = self.metadata_operations_only and metadata
        target = self.path(value, cwd, env)
        if target is None:
            self.unknown("写目标含未解析变量、通配符或动态展开")
        else:
            if target not in self.targets:
                self.targets.append(target)
            # 同一个目标在不同上下文下重复写，仍需逐条校验；不记录其他环境变量。
            binding = {key: env[key] for key in ("AIDP_EXECUTION_CONTEXT",) if key in env}
            self.writes.append({"target": target, "env": binding,
                                "variable_path": bool(VARIABLE.search(value))})

    def _tick_flags_export(self, command, cwd):
        """只信任与 helper 同一安装目录的固定导出契约，不执行脚本。"""
        try:
            argv = _tokens(command)
        except ValueError:
            return False
        if len(argv) < 3 or argv[0] != "python3":
            return False
        path = Path(argv[1])
        path = path if path.is_absolute() else Path(cwd) / path
        if path.resolve() != Path(__file__).resolve().with_name("autopilot_tick_flags.py"):
            return False
        args, shell, command_seen = argv[2:], False, False
        while args:
            option = args.pop(0)
            if option == "--shell" and not shell:
                shell = True
            elif option == "--command" and not command_seen and args and args[0] in {"autopilot", "aiauto-test"}:
                args.pop(0)
                command_seen = True
            elif option in {"--command=autopilot", "--command=aiauto-test"} and not command_seen:
                command_seen = True
            else:
                return False
        return shell

    def _remember_assignments(self, text, env):
        """仅把前面完整语句中的常量赋值提供给后续命令替换。"""
        try:
            words = _tokens(text)
        except ValueError:
            return
        if words and words[0] == "export":
            words = words[1:]
        if not words or not all(ASSIGN.match(word) for word in words):
            return
        for word in words:
            key, value = ASSIGN.match(word).groups()
            env[key] = self.expand(value, env) or "__AIDP_DYNAMIC__"

    def substitutions(self, text, cwd, env, depth):
        """分析实际执行的替换；替换输出标为动态，不能成为已知写目标。"""
        out, quote, i, statement = [], None, 0, 0
        env = dict(env)
        while i < len(text):
            char = text[i]
            if quote is None and char == "#" and (i == 0 or text[i - 1] in " \t\n;|&()"):
                end = text.find("\n", i)
                if end == -1:
                    out.append(text[i:])
                    break
                self._remember_assignments("".join(out[statement:]), env)
                out.append(text[i:end + 1])
                statement = len(out)
                i = end + 1
                continue
            if char == "\\" and quote != "'" and i + 1 < len(text):
                out.append(text[i:i + 2])
                i += 2
                continue
            if char in "\"'":
                if quote == char:
                    quote = None
                elif quote is None:
                    quote = char
            start = (text.startswith("$(", i) or (quote is None and text[i:i + 2] in {"<(", ">("}))
            backtick = char == "`" and quote != "'"
            if quote != "'" and (start or backtick):
                offset = 1 if backtick else 2
                end, nesting, inner_quote = i + offset, 1, None
                while end < len(text):
                    current = text[end]
                    if current == "\\" and inner_quote != "'":
                        end += 2
                        continue
                    if current in "\"'" and not backtick:
                        if inner_quote == current:
                            inner_quote = None
                        elif inner_quote is None:
                            inner_quote = current
                    if inner_quote is None:
                        if backtick and current == "`":
                            break
                        if not backtick:
                            if current == "(":
                                nesting += 1
                            elif current == ")":
                                nesting -= 1
                                if not nesting:
                                    break
                    end += 1
                if end >= len(text):
                    self.unknown("命令替换未闭合")
                    return text
                inner = text[i + offset:end]
                self.shell(inner, cwd, env, depth + 1)
                if quote == '"' and text.startswith("$(", i) and self._tick_flags_export(inner, cwd):
                    token = "__AIDP_DYNAMIC_TICK_" + uuid.uuid4().hex + "__"
                    self.trusted_eval.add(token)
                    out.append(token)
                else:
                    out.append("__AIDP_DYNAMIC__")
                i = end + 1
                continue
            if quote is None and char in ";\n":
                self._remember_assignments("".join(out[statement:]), env)
                out.append(char)
                statement = len(out)
            else:
                out.append(char)
            i += 1
        return "".join(out)

    def shell(self, command, cwd, env, depth=0):
        if depth > 8:
            self.unknown("shell 包装层级过深")
            return
        try:
            words = _tokens(self.substitutions(command, cwd, env, depth))
        except ValueError:
            self.unknown("shell 引号或语法无法解析")
            return
        env = dict(env)
        env["PWD"] = str(cwd)
        metadata_dir = runtime_dir(cwd)
        if any(word in {"cd", "pushd", "popd", "-C", "--chdir"}
               or word.startswith("--chdir=") for word in words):
            self.cwd_mutation = True
        segment, conditional = [], False
        for word in words + [";"]:
            if word in {"if", "elif", "for", "while", "until", "case"}:
                conditional = True
            assignment = ASSIGN.match(word)
            if conditional and assignment:
                self.conditional_assignments.add(assignment.group(1))
            if word in SEPARATORS:
                cwd = self.segment(segment, cwd, env, depth)
                segment = []
            else:
                segment.append(word)
        compound = any(word in {"(", ")", "&", "for", "while", "if"} for word in words)
        # || exit/true 不改变先前已确定的写目标。其他 OR 分支也逐段解析；
        # 只有 cwd 或变量参与目标时仍不能用线性模拟证明分支写集。
        uncertain_or = False
        for index, word in enumerate(words):
            if word != "||":
                continue
            tail = []
            for part in words[index + 1:]:
                if part in SEPARATORS:
                    break
                tail.append(part)
            terminal = (tail in (["true"], [":"], ["exit"])
                        or (len(tail) == 2 and tail[0] == "exit"
                            and (tail[1] == "$?" or tail[1].isdigit())))
            uncertain_or = uncertain_or or not terminal
        branch_environment = uncertain_or and ("cd" in words or any(w["variable_path"] for w in self.writes))
        # 官方条件围栏只写固定运行元数据时，分支只影响是否写入，不影响目标。
        # 不豁免变量目标或任何 cwd 变化；目标仍逐条交 entry_gate（含 symlink）核验。
        fixed_metadata = (self.metadata_operations_only and not self.cwd_mutation
                          and not (self.command_variables & self.conditional_assignments)) and all(
            not write["variable_path"] and (write["target"] == os.devnull
                or write["target"] == metadata_dir or write["target"].startswith(metadata_dir + os.sep))
            for write in self.writes)
        if (compound or branch_environment) and not fixed_metadata and any(target != os.devnull for target in self.targets):
            self.unknown("条件分支、循环或子 shell 的写入环境不确定")

    def segment(self, words, cwd, env, depth):
        if not words:
            return cwd
        local = dict(env)
        # 只用于收窄 metadata 例外，不解释或执行控制流。then $CMD 也须记录。
        command_words = list(words)
        while command_words and command_words[0] in {"if", "then", "elif", "else", "do", "while", "until", "!"}:
            command_words.pop(0)
        if command_words:
            variable = VARIABLE.fullmatch(command_words[0])
            if variable:
                self.command_variables.add(variable.group(1) or variable.group(2))
        while words and ASSIGN.match(words[0]):
            key, value = ASSIGN.match(words.pop(0)).groups()
            expanded = self.expand(value, local)
            if expanded is None:
                local[key] = "__AIDP_DYNAMIC__"
            else:
                local[key] = expanded
        if not words:
            env.update(local)
            return cwd
        argv, i, here_string = [], 0, False
        while i < len(words):
            word = words[i]
            if word in REDIRECTS:
                if i + 1 >= len(words):
                    self.unknown("重定向缺少目标")
                    break
                target = words[i + 1]
                if argv and argv[-1].isdigit():
                    argv.pop()  # 2>file
                if word in {">", ">>", ">|", "&>", "&>>", "<>"}:
                    self.write(target, cwd, local, metadata=True)
                elif word == ">&" and not (target.isdigit() or target == "-"):
                    self.write(target, cwd, local, metadata=True)
                elif word == "<<<":
                    here_string = True
                elif word == "<<":
                    self.unknown("here-document 执行语义未展开")
                i += 2
            else:
                argv.append(word)
                i += 1
        if not argv:
            return cwd
        if VARIABLE.fullmatch(argv[0]):
            variable = VARIABLE.fullmatch(argv[0])
            self.command_variables.add(variable.group(1) or variable.group(2))
            expanded = self.expand(argv[0], local)
            if expanded is not None:
                # 未引号命令变量执行的是词拆分，不把变量里的 ; 当作 shell 语法。
                argv = expanded.split() + argv[1:]
        while argv and Path(argv[0]).name in {"env", "command", "exec", "nohup", "sudo"}:
            wrapper = Path(argv.pop(0)).name
            while argv and (argv[0].startswith("-") or ASSIGN.match(argv[0])):
                item = argv.pop(0)
                if ASSIGN.match(item):
                    key, value = ASSIGN.match(item).groups()
                    expanded = self.expand(value, local)
                    if expanded is not None:
                        local[key] = expanded
                    else:
                        local[key] = "__AIDP_DYNAMIC__"
                elif item in {"-u", "--unset", "-C", "--chdir"} and argv:
                    value = argv.pop(0)
                    if item in {"-C", "--chdir"}:
                        self.cwd_mutation = True
                        new = self.path(value, cwd, local)
                        if new:
                            cwd = new
                        else:
                            self.unknown("env 工作目录无法解析")
                    else:
                        local.pop(value, None)
                elif wrapper == "env" and item in {"-i", "--ignore-environment"}:
                    local.clear()
                elif item not in {"--", "-p", "-n"}:
                    self.unknown(wrapper + " 包装参数无法确定")
        if not argv:
            return cwd
        name = Path(argv[0]).name
        args = argv[1:]
        if name in {"cd", "pushd", "popd"}:
            self.cwd_mutation = True
        if here_string:
            reads_stdin = name in {"cat", "rg", "grep", "sed", "head", "tail", "wc", "sort", "uniq", "cut", "tr", "read"}
            python_code = bool(re.fullmatch(r"python(?:[23](?:\.\d+)?)?", name)) and "-c" in args
            shell_code = name in SHELLS and any(a.startswith("-") and not a.startswith("--") and "c" in a for a in args)
            if not (reads_stdin or python_code or shell_code):
                self.unknown("here-string 消费方不能证明只把 stdin 当数据")
        if name == "export":
            for item in args:
                match = ASSIGN.match(item)
                if match:
                    key, value = match.groups()
                    expanded = self.expand(value, local)
                    if expanded is not None:
                        env[key] = expanded
                    else:
                        env[key] = "__AIDP_DYNAMIC__"
            return cwd
        if name == "cd":
            if len(args) != 1 or args[0].startswith("-"):
                self.unknown("cd 目标无法解析")
                return cwd
            new = self.path(args[0], cwd, local)
            if new is None:
                self.unknown("cd 目标含动态展开")
                return cwd
            env["PWD"] = new
            return new
        if name in SHELLS:
            flag = next((i for i, a in enumerate(args) if a.startswith("-") and not a.startswith("--") and "c" in a), None)
            if flag is not None and flag + 1 < len(args):
                self.shell(args[flag + 1], cwd, local, depth + 1)
            elif not args or any(a in {"-s", "-"} for a in args):
                self.unknown("shell 从标准输入读取动态程序")
            # 外部脚本正文不在本静态解析器覆盖范围内。
        elif re.fullmatch(r"python(?:[23](?:\.\d+)?)?", name) and "-c" in args:
            index = args.index("-c")
            if index + 1 < len(args):
                self.python(args[index + 1], cwd, local, depth + 1)
            else:
                self.unknown("python -c 缺少程序")
        elif name == "eval":
            if len(args) != 1 or args[0] not in self.trusted_eval:
                self.unknown("动态执行命令不能证明无业务写入；仅兼容本安装的 tick_flags --shell 固定引导")
        elif name in {"source", "."} or "$" in name or "`" in name:
            self.unknown("动态执行命令不能证明无业务写入")
        elif name == "sed":
            inplace = any(a == "--in-place" or a.startswith("--in-place=") or a.startswith("-i")
                          or (a.startswith("-") and not a.startswith("--") and "i" in a[1:]) for a in args)
            if inplace:
                operands, expression = [], False
                i = 0
                while i < len(args):
                    a = args[i]
                    if a in {"-e", "--expression", "-f", "--file"}:
                        expression = True
                        i += 2
                        continue
                    if a.startswith(("--expression=", "--file=")) or (a.startswith(("-e", "-f")) and len(a) > 2):
                        expression = True
                    elif not a.startswith("-"):
                        operands.append(a)
                    i += 1
                if not expression and operands:
                    operands.pop(0)
                if not operands:
                    self.unknown("sed -i 写目标无法解析")
                suffix = next((a.split("=", 1)[1] for a in args if a.startswith("--in-place=")), "")
                suffix = next((a[2:] for a in args if a.startswith("-i") and len(a) > 2), suffix)
                for item in operands:
                    self.write(item, cwd, local)
                    if suffix:
                        if "*" in suffix:
                            self.unknown("sed 备份后缀含动态目标")
                        else:
                            self.write(item + suffix, cwd, local)
            elif any(re.search(r"(?:^|[; ])w\s+", a) for a in args):
                self.unknown("sed w 指令写目标需拆成显式重定向")
        elif name in WRITERS:
            operands, dest, i = [], None, 0
            values = {"-t", "--target-directory", "-m", "--mode", "-o", "--owner", "-g", "--group",
                      "-S", "--suffix", "-s", "--size", "--reference"}
            options = True
            while i < len(args):
                a = args[i]
                if options and a == "--":
                    options = False
                elif options and a in values and i + 1 < len(args):
                    if a in {"-t", "--target-directory"}:
                        dest = args[i + 1]
                    i += 1
                elif options and a.startswith("--target-directory="):
                    dest = a.split("=", 1)[1]
                elif options and a.startswith("-t") and len(a) > 2 and name in {"cp", "mv", "install"}:
                    dest = a[2:]
                elif not options or not a.startswith("-"):
                    operands.append(a)
                i += 1
            if name in {"cp", "mv", "install", "ln"}:
                sources = operands if dest else operands[:-1]
                destination = dest or (operands[-1] if len(operands) >= 2 else None)
                if destination:
                    dpath = self.path(destination, cwd, local)
                    if dpath and (dest or Path(dpath).is_dir() or destination.endswith("/")) and not any(a in {"-T", "--no-target-directory"} for a in args):
                        for source in sources:
                            self.write(str(Path(dpath) / Path(source).name), cwd, local)
                    else:
                        self.write(destination, cwd, local)
                elif name == "install" and "-d" in args:
                    for operand in operands:
                        self.write(operand, cwd, local)
                else:
                    self.unknown(name + " 写目标无法解析")
                if name == "mv":
                    for source in sources:
                        self.write(source, cwd, local)
            else:
                for operand in operands:
                    if operand != "-":
                        self.write(operand, cwd, local, metadata=(name == "mkdir"))
        elif name in {"find", "xargs"}:
            if any(a in WRITERS or a in {"-exec", "-execdir", "-delete"} for a in args):
                self.unknown("循环或复合命令写目标需展开后校验")
        elif name not in {"echo", "printf", "cat", "rg", "grep"} and any(Path(a).name in WRITERS for a in args):
            self.unknown("未识别的包装器包含写入命令")
        return cwd

    def python(self, program, cwd, env, depth):
        try:
            tree = ast.parse(program)
        except (ValueError, SyntaxError):
            self.unknown("python -c 无法静态解析")
            return
        values = {}

        def literal(node):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                return node.value
            if isinstance(node, ast.Name):
                return values.get(node.id)
            if isinstance(node, ast.Call) and node.args and label(node.func) in {"Path", "pathlib.Path"}:
                return literal(node.args[0])
            if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Div, ast.Add)):
                left, right = literal(node.left), literal(node.right)
                if left is not None and right is not None:
                    return str(Path(left) / right) if isinstance(node.op, ast.Div) else left + right
            return None

        def label(node):
            if isinstance(node, ast.Name):
                return node.id
            if isinstance(node, ast.Attribute):
                return label(node.value) + "." + node.attr
            return ""

        def write(node):
            value = literal(node)
            if value is None:
                self.unknown("python 写目标不是可解析的常量路径")
            else:
                self.write(value, cwd, env)

        # 按语句顺序处理，后续赋值不能改写先前 open 的目标。
        for node in (node for statement in tree.body for node in ast.walk(statement)):
            if isinstance(node, (ast.For, ast.While, ast.If, ast.Try, ast.FunctionDef, ast.Lambda)):
                self.unknown("python 控制流中的文件操作不能静态证明安全")
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                values[node.targets[0].id] = literal(node.value)
            if not isinstance(node, ast.Call):
                continue
            name = label(node.func)
            method = node.func.attr if isinstance(node.func, ast.Attribute) else ""
            if name in {"open", "io.open"} or method == "open":
                path = node.args[0] if name in {"open", "io.open"} and node.args else getattr(node.func, "value", None)
                modes = node.args[1:] if name in {"open", "io.open"} else node.args
                mode = literal(modes[0]) if modes else "r"
                for keyword in node.keywords:
                    if keyword.arg == "mode":
                        mode = literal(keyword.value)
                if mode is None or any(x in mode for x in "wax+"):
                    write(path)
            elif method in {"write_text", "write_bytes", "unlink", "touch", "mkdir", "rmdir", "chmod"}:
                write(node.func.value)
            elif name in {"os.remove", "os.unlink", "os.rmdir", "os.mkdir", "os.makedirs", "shutil.rmtree"}:
                if node.args:
                    write(node.args[0])
                else:
                    self.unknown("python 文件调用缺参数")
            elif method in {"rename", "replace"} or name in {"shutil.copy", "shutil.copy2", "shutil.copyfile", "shutil.move"}:
                if name.startswith(("os.", "shutil.")):
                    if len(node.args) >= 2:
                        write(node.args[1])
                        if name in {"os.rename", "os.replace", "shutil.move"}:
                            write(node.args[0])
                    else:
                        self.unknown("python 移动/复制参数不完整")
                elif node.args:
                    write(node.func.value)
                    write(node.args[0])
            elif name == "os.chdir":
                self.unknown("python chdir 需拆成 shell cd 后的独立命令")
            elif name in {"os.system", "subprocess.run", "subprocess.call", "subprocess.check_call", "subprocess.Popen"}:
                try:
                    command = ast.literal_eval(node.args[0])
                    self.shell(command_text(command), cwd, env, depth + 1)
                except (ValueError, TypeError, IndexError):
                    self.unknown("python 子进程命令无法解析")
            elif name in {"print", "len", "str", "repr", "int", "bool", "Path", "pathlib.Path", "json.dumps", "json.loads", "json.load"}:
                pass
            elif method in {"get", "read", "read_text", "read_bytes", "exists", "is_file", "is_dir", "stat", "glob", "rglob"}:
                pass
            elif method == "write" and isinstance(node.func.value, ast.Call) and label(node.func.value.func) in {"open", "io.open"}:
                pass  # 内层 open 独立检查
            else:
                self.unknown("python 调用的写入效果无法确定：" + (name or method))


def analyze(command, cwd, env=None):
    result = _Analysis()
    result.shell(command_text(command), str(Path(cwd).resolve()), os.environ if env is None else env)
    return {"targets": result.targets, "writes": result.writes,
            "uncertain": bool(result.reasons), "reasons": result.reasons}
