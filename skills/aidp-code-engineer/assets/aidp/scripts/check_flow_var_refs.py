#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_flow_var_refs.py — flow 分片里「读了但从没人写」的变量与 baseline 字段（脚手架契约脚本）。

## 为什么需要本脚本

一次全量审计在 `AIDP_HOME/flows/` 里挖出 **6 条同类 Critical**，全部是同一个形状：

    判据引用了一个**从未被赋值的 shell 变量**，或读了一个**从未被写入的 baseline 字段**。

后果不是报错，而是**判据恒真/恒假**——最坏的一条把"红"判成了"绿"：

  · `THIS_ROUND_FAIL_COUNT`（全仓仅 1 处引用、0 处赋值）→ `${VAR:-0}` 取 0 →
    不论本轮失败多少条用例都判 `CONVERGED=1` → 发绿灯、finalize、写"已测通过"。
  · `DEPLOY_MODE`（0 处赋值）→ 云端部署整段被跳过，`last_deployed_at` 永不写，
    测试链路永不启动，反过来还把一个其实部署成功的版本冻结成"部署不可达"。
  · 版本级 `ai_report_finalized`（只有 `builds[].` 那层被写）→ 准发布收敛门恒假，
    任何版本都归档不了，最后按"未收敛"误冻结。

这类缺陷**人读发现不了**：每一段单独看都合理，错在"写的人和读的人不在同一个分片"。
而分片间 shell state 不跨 Bash 调用持久（`phase-0-1.md` 自己论证过），所以
"另一个分片里赋过值"根本不成立——必须同分片赋值，或经 baseline 落盘再读回。

## 判定口径

只扫 `AIDP_HOME/flows/**/*.md` 里的 ```bash / ```sh 代码块。

**A. shell 变量**：某分片**引用**了 `$VAR` / `${VAR...}`，而全仓 flow 的 bash 块里
   **没有任何地方**给它赋值（`VAR=`、`for VAR in`、`read VAR`、`export VAR=`、
   `local VAR=`、`$(...)` 赋值均算），且不在下列豁免里：

   · 环境/内建变量（`HOME`/`PWD`/`USER`/`?`/`#`/`@`/`1`..`9` 等）
   · 已知由命令端在调用前注入的编排变量（`ENVVAR_ALLOW`，见下）

   报 **ERROR**——它必然取空，`${VAR:-default}` 会静默落到默认值。

**B. baseline 字段**：`baseline_edit.py ... get <path>` / `jq '.versions...'` 读取的字段，
   在全仓 flow + `AIDP_HOME/scripts/*.py` 里找不到对应的 `set`/`touch`/`bump`/写盘点。
   报 **WARN**（写入方可能在 SKILL 或运行时动态生成，误报成本高于漏报）。

## 豁免

    <!-- flowvar-check: ignore -->            该行豁免
    <!-- flowvar-check: ignore-file 理由 -->   整份文件豁免
    <!-- flowvar-check: allow VAR1,VAR2 -->   声明这些变量由调用方注入（写在引用它的文件里）

## 用法

    python3 AIDP_HOME/scripts/check_flow_var_refs.py           # 人读报告
    python3 AIDP_HOME/scripts/check_flow_var_refs.py --json    # 机读
    python3 AIDP_HOME/scripts/check_flow_var_refs.py --path AIDP_HOME/flows/sprint-autopilot

退出码：0 = 无未定义引用；1 = 检出；2 = 用法/读取错误。
"""
import sys as _aidp_sys
from pathlib import Path as _AidpPath
_aidp_scripts = str(_AidpPath(__file__).resolve().parent)
if _aidp_scripts not in _aidp_sys.path:
    _aidp_sys.path.insert(0, _aidp_scripts)
from aidp_runtime import runtime_relpath, runtime_text
import argparse
import json
import os
import re
import sys

FLOW_ROOT = os.path.join(runtime_relpath("", __file__), "flows")
EXCLUDE_DIRS = {".git", "node_modules", "__pycache__", "dist", "build", ".venv", "skills"}
EXCLUDE_DIR_PREFIXES = (".aidp-backup",)

BASH_BLOCK_RE = re.compile(r"```(?:bash|sh)\n(.*?)```", re.S)
# 引用：$VAR / ${VAR} / ${VAR:-x} / ${VAR:+x} / ${#VAR}
REF_RE = re.compile(r"\$\{?#?([A-Za-z_][A-Za-z0-9_]*)\b")
# 赋值：VAR= / export VAR= / local VAR= / for VAR in / read VAR / read -r VAR
# `^[\s>]*` 而非 `^\s*`：分片里大量可执行片段写在 markdown 引用块（`> ` 前缀）里，
# 只认空白会把这些赋值全漏掉 → 噪声占比七成、守卫恒红。
# ★ 赋值起点不止「行首」：`A=0; B=0; C=0`、`[ x ] && S=final || S=skeleton`、`then V=1`、
#   `do X=$(...)`、`( Y=1 )` 都是常见写法。只认行首会把它们判成"从未赋值"——实测这一条
#   就贡献了 60 处 FAIL 中的近半数假阳性（`HAS_ONCE_FLAG` / `HAS_NO_LOOP_FLAG` / `GATE_STAGE`
#   全都在同一行的 `;` 或 `&&` 之后赋过值）。守卫误报多了就没人看，等于没有守卫。
# `\)\s*` = `case` 分支体（`mcp*) IS_MCP=1 ;;`）——case 分支是合法赋值位置，
# 不认它会把 case 里赋的变量全判成"从未赋值"。
_ASSIGN_LEAD = r"(?:^|[;&|]{1,2}\s*|\b(?:then|else|do|elif)\s+|\(\s*|\)\s*)"
ASSIGN_RES = [
    re.compile(rf"{_ASSIGN_LEAD}[\s>]*(?:export\s+|local\s+|declare\s+(?:-\w+\s+)?)?"
               r"([A-Za-z_][A-Za-z0-9_]*)=", re.M),
    re.compile(r"^[\s>]*for\s+([A-Za-z_][A-Za-z0-9_]*)\s+in\b", re.M),
    re.compile(r"\bread\s+(?:-r\s+)?(?:-p\s+\S+\s+)?([A-Za-z_][A-Za-z0-9_]*)", re.M),
    re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\+?=\(", re.M),          # 数组
    # ★ `${VAR:=默认}` / `${VAR=默认}` 是**赋值型**参数展开（与只读的 `${VAR:-默认}` 一字之差、
    #   语义相反）：它会真的把值写进 VAR。惯用法 `: "${VAR:=$(…)}"` 正是"没取到就现算一个"，
    #   漏认会把这种合法赋值报成"从未赋值"。
    re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*):?=", re.M),
]

# ★ 声明语句专项：一条 `local A="1" B="2" C="3"` 可声明多个变量，逐条正则只会捕获第一个，
#   后面的全被判成"从未赋值"（`gen_index() { local DIR="$1" RUN_TYPE="$2" IDX="…" }` 即如此被误报）；
#   `declare -A MAP` 这种**不带 `=`** 的纯声明（关联数组标准写法）也同样漏。故单独扫一遍。
DECL_STMT_RE = re.compile(r"^[\s>]*(?:local|declare|export|typeset)\s+([^\n;#]*)", re.M)
DECL_NAME_RE = re.compile(r"(?<![-\w])([A-Za-z_][A-Za-z0-9_]*)(?==|\s|$)")


def _decl_vars(text: str) -> set:
    out = set()
    for m in DECL_STMT_RE.finditer(text):
        seg = m.group(1)
        for token in seg.split():
            if token.startswith("-"):      # 选项如 -A / -a / -r
                continue
            nm = DECL_NAME_RE.match(token)
            if nm:
                out.add(nm.group(1))
            if "=" not in token:
                # `declare -A MAP` 之后就是命令的其它参数了，别把它们也当变量名
                break
    return out

# shell 内建 / 环境变量（永不需要本仓赋值）
BUILTIN = {
    "HOME", "PWD", "OLDPWD", "USER", "SHELL", "PATH", "IFS", "PS1", "PS2", "RANDOM",
    "LINENO", "SECONDS", "HOSTNAME", "TMPDIR", "EDITOR", "LANG", "LC_ALL", "TERM",
    "BASH", "BASH_SOURCE", "FUNCNAME", "PPID", "UID", "EUID", "GROUPS", "REPLY",
    # OS / 桌面环境（跨平台探测常用，永远由系统提供）
    "DISPLAY", "WAYLAND_DISPLAY", "XDG_SESSION_TYPE", "XDG_RUNTIME_DIR",
    "TEMP", "TMP", "WSLENV", "WSL_DISTRO_NAME", "OS", "OSTYPE", "COMSPEC",
    "APPDATA", "LOCALAPPDATA", "PROGRAMFILES", "USERPROFILE", "SSH_AUTH_SOCK",
    "NO_PROXY", "HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "no_proxy",
}
# 由命令端在进入分片前注入的编排变量（分片只消费、不负责赋值）——
# 每新增一个都必须能在命令正文里指出注入点，否则就是真缺陷、不该进这里。
ENVVAR_ALLOW = {
    # ⚠️ 本白名单只豁免 **A 类**（"全仓从未赋值"）；**C 类（围栏作用域）照判** ——
    #    "命令端注入、全链路贯穿"说的是它有真源，不代表**每个 Bash 围栏**都取得到：
    #    shell state 不跨调用，围栏内要用它仍须本围栏先 `eval --shell`。两条判据分工不同、不矛盾。
    "TARGET_VERSION",      # 命令端 Phase 0 解析后注入，有真源（C 类仍要求本围栏 eval）
    "ARGUMENTS",           # 斜杠命令入参
    "AIDP_PROJECT_NAME", "AIDP_AGENT",
    # 里程碑通知渠道的凭据 env 通道（notify.channels 的 webhook_env / secret_env，适合 CI 注入）
    "AIDP_FEISHU_WEBHOOK", "AIDP_FEISHU_SECRET", "AIDP_DINGTALK_WEBHOOK",
    "AIDP_DINGTALK_SECRET", "AIDP_WECOM_WEBHOOK",
    "SKILL_ACCESS_TOKEN",
}

# ★ 注释里的 `$VAR` 不是判据，必须剔除，否则守卫抓的是"文档在讨论这个变量"而非"代码在读它"。
#   实测噪声来源之一恰恰是**警告注释本身**——`phase-0-2.md` 写「⛔ 别再写 `$CURRENT_BUILD`，
#   那个变量全仓从未赋值」，结果被守卫当成"这里引用了未赋值变量"报出来：把已修好的缺陷的
#   墓志铭又报成缺陷。判定 `#` 为注释起点需排除 `${#VAR}` / `$#` / `#!` 三种非注释用法。
COMMENT_CUT_RE = re.compile(r"(?<![$\{])(?:(?<=\s)|^)#(?!\!)")


def strip_comment(line: str) -> str:
    """截去 shell 行注释部分；引号内的 `#` 不算注释起点（简易配对计数，够用且不误伤）。"""
    in_s = in_d = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch == "#" and not in_s and not in_d:
            if i == 0 or line[i - 1] in " \t":
                if not (i + 1 < len(line) and line[i + 1] == "!" and i == 0):
                    return line[:i]
    return line


# ★ 可调阈值：写法恒为 `${VAR:-<默认值>}`，**默认值就是设计意图**，不赋值是正常的
#   （运维想改就 `export VAR=5` 覆盖）。它们与 `${THIS_ROUND_FAIL_COUNT:-0}` 那种
#   "默认值恰好意味着没失败"的致命形态语法同形、语义相反 —— 这正是本脚本不作硬门的原因。
#   登记在此只是把已判定过的合法项从输出里摘掉，让剩下的每一条都值得看。
#   ⛔ 新增项必须满足两条：① 引用处恒带 `:-默认值` ② 默认值本身是安全取值（取到它不会把红判成绿）。
TUNABLE_ALLOW = {
    "DEV_FAIL_FREEZE_THRESHOLD", "ENV_FAIL_FREEZE_THRESHOLD", "HANDOFF_FAIL_THRESHOLD",
    "REPORT_GATE_FREEZE_THRESHOLD", "TEST_LOOP_MISSING_THRESHOLD",
    "PRERELEASE_DEPLOY_BLOCK_THRESHOLD", "PRERELEASE_TEST_HOLD_WARN", "PRERELEASE_TEST_HOLD_FREEZE",
    "STUCK_PHASE_ENTER_THRESHOLD", "STUCK_PHASE_AGE_SECONDS",
    "PREFLIGHT_THRESHOLD",
}

# ★ 由 `autopilot_tick_flags.py --shell` 注入的本 tick 变量：**只在真的写了那行 eval 的文件里**
#   才算已赋值。这一点很关键——正是"读的人和写的人不在同一分片"造成了本脚本要抓的那类缺陷，
#   所以豁免必须绑定到"该文件自己取回了值"这个事实，而不是全局放行。
# `[^\n]*?` 允许中间夹 `--command <c>` 等参数——写死 `\s+--shell` 会让
# `…tick_flags.py --command aiauto-test --shell` 这种完全合法的写法不被识别，
# 于是"明明取回了值"却仍被判未定义（假红），进而诱导把正确的读回行删掉。
TICK_EVAL_RE = re.compile(r"autopilot_tick_flags\.py[^\n]*?--shell")

# ★ 其它「`eval $(脚本 --shell)` 注入变量」的脚本：同样**绑文件**放行——文件里真的写了那行
#   eval 才算这些名字已赋值。值取自各脚本 `--shell` 分支实际 print 的赋值行。
SCRIPT_INJECTED = (
    (re.compile(r"autopilot-prd-watch\.py[^\n]*--shell"),
     {"SHOULD_RUN", "TRIGGER_REASON", "PRD_DIR", "PRD_REASON_CODE"}),
    (re.compile(r"plan_sprints\.py[^\n]*--shell"),
     {"PLAN_FILE_COUNT", "PLAN_FILES", "ALL_SPRINTS", "CLOSED_SPRINTS", "REMAIN_SPRINTS",
      "REMAIN_COUNT", "FIRST_SPRINT", "NEXT_SPRINT", "CURRENT_SPRINT"}),
)

# ★ 由上表变量经 `read -ra <名> <<< "$<供给变量>"` 就地还原出的数组名：供给行本身已被上表覆盖，
#   数组名再单列一次，避免"明明同围栏上一行刚 read 出来"被判成未赋值。
SCRIPT_INJECTED_ARRAYS = (
    (re.compile(r'read\s+-ra\s+CLOSED_AFTER\s*<<<'), {"CLOSED_AFTER"}),
)


def _tick_vars() -> set:
    """从 autopilot_tick_flags.py 取已登记的变量全集（单一信源，避免两处清单漂移）。"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "autopilot_tick_flags.py")
    try:
        with open(path, encoding="utf-8") as f:
            src = f.read()
    except OSError:
        return set()
    # 只取形如 "XXX": "VAR" 与 "VAR", 的大写标识符，够用且不需要执行该模块
    return set(re.findall(r"\"([A-Z][A-Z0-9_]{2,})\"", src))


IGNORE_LINE_RE = re.compile(r"<!--\s*flowvar-check:\s*ignore\s*(?:-->|\s)")
IGNORE_FILE_RE = re.compile(r"<!--\s*flowvar-check:\s*ignore-file")
ALLOW_RE = re.compile(r"<!--\s*flowvar-check:\s*allow\s+([^>]+?)\s*-->")


def _walk(base):
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames
                       if d not in EXCLUDE_DIRS and not d.startswith(EXCLUDE_DIR_PREFIXES)]
        for fn in sorted(filenames):
            if fn.endswith(".md"):
                yield os.path.join(dirpath, fn)


def collect(root, paths=None):
    """返回 {文件: {"text":全文, "blocks":[(起始行, 块文本)], "allow":set}}。"""
    bases = [os.path.join(root, p) for p in paths] if paths else [os.path.join(root, FLOW_ROOT)]
    out = {}
    for base in bases:
        if os.path.isfile(base):
            files = [base]
        elif os.path.isdir(base):
            files = list(_walk(base))
        else:
            continue
        for path in files:
            try:
                with open(path, encoding="utf-8") as f:
                    text = f.read()
            except (OSError, UnicodeDecodeError):
                continue
            if IGNORE_FILE_RE.search(text):
                continue
            blocks = []
            for m in BASH_BLOCK_RE.finditer(text):
                blocks.append((text[:m.start()].count("\n") + 1, m.group(1)))
            allow = set()
            for m in ALLOW_RE.finditer(text):
                # ⛔ 不能整串按逗号切：实际写法是「变量名… + 一句中文说明」（如
                #    `allow TARGET_VERSION PRE_RELEASE_VERSION 本步散文判定的产物`），
                #    整串切出来是**一个 token**、匹配不上任何变量名 ⇒ 标记变成哑的
                #    （实测两处都如此：看着有豁免、实际一个都没生效，只是碰巧别处有赋值）。
                #    改为：从头取连续的 `UPPER_SNAKE` token，遇到第一个非变量名（说明文字）即停。
                for tok in re.split(r"[,\s]+", m.group(1).strip()):
                    if re.fullmatch(r"[A-Z][A-Z0-9_]*", tok):
                        allow.add(tok)
                    else:
                        break
            out[path] = {"text": text, "blocks": blocks, "allow": allow}
    return out


def run(root, paths=None, strict=False, per_fence=False):
    """strict=False：只抓「全仓根本没人赋值」的硬错（默认，历史行为）。

    strict=True：**逐文件**判定——某分片引用了 `$VAR`，而该分片自己既没赋值、
    也没有任何取回手段（`autopilot_tick_flags.py --shell` / `baseline_edit.py get` /
    其它 `--shell` 注入 / 显式 allow 注释）→ 报错。

    ★ 为什么必须有 strict：flow 的每个分片是**独立的 Bash 工具调用**，shell 变量
      不跨调用持久。默认模式按"全仓有无赋值"判定，于是"A 分片赋值、B 分片读"这种
      **恒取空**的写法一路绿灯——而这恰恰是本脚本 docstring 自述要防的病因
      （"错在写的人和读的人不在同一个分片"）。默认模式与自身立意自相矛盾，
      strict 才是真正对得上那句话的判据。
    """
    files = collect(root, paths)
    # 全局赋值集合：任一分片里赋过值就算"这个名字在本体系里有定义"
    # （跨分片不持久是另一个问题，本脚本只抓"全仓根本没人写"这一类硬错）
    # ⚠️ 赋值扫**全文**而非只扫 bash 围栏：分片里大量赋值写在 `> ` 引用块、行内反引号、
    #    或"Claude 按本轮 prompt 就地改为 0/1"这类散文指令里（如 `IS_LOOP_CONTEXT=0`）。
    #    只扫围栏会把它们全判成"从未赋值"——实测噪声占比超七成，守卫会恒红、等于没有。
    assigned = set()
    for info in files.values():
        for rx in ASSIGN_RES:
            for m in rx.finditer(info["text"]):
                if m.lastindex:
                    assigned.add(m.group(1))
        assigned |= _decl_vars(info["text"])

    tickvars = _tick_vars()
    findings = []
    for path, info in sorted(files.items()):
        lines = info["text"].split("\n")
        # strict：把"已赋值"收缩为**本文件自己赋的值**（跨分片 shell 变量不持久）
        if strict:
            assigned = set()
            for rx in ASSIGN_RES:
                for m in rx.finditer(info["text"]):
                    if m.lastindex:
                        assigned.add(m.group(1))
            assigned |= _decl_vars(info["text"])
        # 本文件自己取回了 tick 变量 → 这些名字在本文件内视为已赋值（绑文件、不全局放行）
        file_allow = set(info["allow"])
        if TICK_EVAL_RE.search(info["text"]):
            file_allow |= tickvars

        # ── C 类：tick 变量的【围栏作用域】────────────────────────────────
        # ⚠️ 上面那条按【整份分片】放行，粒度太粗。shell state **不跨 Bash 调用持久**
        #    （`phase-0-1.md` 自己论证过），所以「本文件别处有 eval」根本不等于
        #    「本围栏取得到值」。实测：`phase-3-2.md` 的 eval 在 37-73 围栏，
        #    而 90-121 围栏首行就 `V="$TARGET_VERSION"` —— V 恒空 →
        #    路径拼成 `docs/reports//AI执行报告` → 五项检查全 miss → `exit 1` 禁止委派，
        #    `aiauto_delegated_at` 永不落盘、双链路交接直接断，而告警指向一个不存在的行为。
        #    故按围栏再判一次：围栏内引用 tick 变量，但**本围栏在该行之前没有 eval --shell**，
        #    且**本围栏内也没给它赋过值** → ERROR。
        for start, block in info["blocks"]:
            blines = block.split("\n")
            eval_at = None
            for i, line in enumerate(blines):
                if TICK_EVAL_RE.search(line):
                    eval_at = i
                    break
            local_assigned = set()
            for i, line in enumerate(blines):
                code = strip_comment(line)
                if not code.strip():
                    continue
                lineno = start + i + 1
                src = lines[lineno - 1] if 0 < lineno <= len(lines) else ""
                if IGNORE_LINE_RE.search(src):
                    for mm in ASSIGN_RES[0].finditer(code):
                        if mm.lastindex:
                            local_assigned.add(mm.group(1))
                    continue
                if eval_at is None or i < eval_at:
                    for m in REF_RE.finditer(code):
                        v = m.group(1)
                        if v not in tickvars or v in local_assigned or v in info["allow"]:
                            continue
                        findings.append({
                            "level": "ERROR", "kind": "fence-scope",
                            "file": os.path.relpath(path, root), "line": lineno,
                            "var": v,
                            "detail": ("围栏内引用 tick 变量 `%s`，但本围栏%s —— "
                                       "shell state 不跨 Bash 调用，取到的是空值"
                                       % (v, "没有 eval --shell" if eval_at is None
                                          else "的 eval --shell 在第 %d 行、晚于本次引用" % (start + eval_at + 1))),
                            "context": code.strip()[:120],
                        })
                for mm in ASSIGN_RES[0].finditer(code):
                    if mm.lastindex:
                        local_assigned.add(mm.group(1))
        for rx, names in SCRIPT_INJECTED + SCRIPT_INJECTED_ARRAYS:
            if rx.search(info["text"]):
                file_allow |= names
        for start, block in info["blocks"]:
            # ★★ per_fence：把「已赋值」再收紧一档到**本围栏内、且在引用行之前**。
            #   Why：flow 的每个 ```bash 围栏是**一次独立的 Bash 调用**，围栏之间连
            #   shell 变量都不共享。而默认 / strict 两档收集赋值的粒度分别是「全仓」「本文件」，
            #   于是「围栏 A 赋值、围栏 B 读取」这一整类断链**结构上检不出**——
            #   典型后果：`$BE` 展开成空 → `--version … set …` 报 command not found、
            #   状态一字节不写；`$V` 取空 → 判据恒假、门恒不触发。两者都不报错、只静默失效。
            fence_assigned = set()
            if per_fence:
                for j, ln0 in enumerate(block.split("\n")):
                    _c = strip_comment(ln0)
                    for rx in ASSIGN_RES:
                        for mm in rx.finditer(_c):
                            if mm.lastindex:
                                fence_assigned.add((mm.group(1), j))
                    # ★ 一条 `local A="1" B="2" C="3"` 逐条正则只捕获第一个 —— 不补这一遍，
                    #   `gen_index() { local DIR="$1" RUN_TYPE="$2" IDX="…"; }` 里的后两个
                    #   会被报成"本围栏从未赋值"，稳定假阳性会把这道门变成噪音。
                    for _n in _decl_vars(_c):
                        fence_assigned.add((_n, j))
            for i, line in enumerate(block.split("\n")):
                lineno = start + i + 1
                src = lines[lineno - 1] if 0 < lineno <= len(lines) else ""
                if IGNORE_LINE_RE.search(src):
                    continue
                code = strip_comment(line)
                if not code.strip():
                    continue
                for m in REF_RE.finditer(code):
                    v = m.group(1)
                    if per_fence:
                        # 本围栏内、**不晚于本行**赋过值才算数。
                        # ⛔ 必须含"同一行"：`X=$(...); [ -n "$X" ] || X=默认` 与
                        #   `f=$(echo "$f" | sed …)` 都是一行内先赋后用的惯用法，
                        #   取 `j < i` 会把它们全报成未赋值。
                        if any(n == v and j <= i for n, j in fence_assigned):
                            continue
                        if (v in BUILTIN or v in ENVVAR_ALLOW or v in TUNABLE_ALLOW
                                or v in file_allow or v.isdigit()):
                            continue
                        findings.append({
                            "file": os.path.relpath(path, root), "line": lineno,
                            "var": v, "context": line.strip()[:110],
                            "kind": "per-fence",
                        })
                        continue
                    if (v in assigned or v in BUILTIN or v in ENVVAR_ALLOW
                            or v in TUNABLE_ALLOW or v in file_allow or v.isdigit()):
                        continue
                    findings.append({
                        "file": os.path.relpath(path, root), "line": lineno,
                        "var": v, "context": line.strip()[:110],
                    })
    # ── 第二类：引用块里赋值、非引用块围栏里引用（跨围栏取空） ──────────────
    # 上面那类抓的是"全仓根本没人写"；本类抓的是**写在了不会被执行的地方**：
    # markdown 引用块（`> `）里的 bash 是**给人看的说明**，执行体照抄成两个 Bash 工具调用时
    # shell state 不跨调用持久 → 变量恒空。实测踩过：Phase 3.2 出口的 NEXT_PHASE_AFTER_DEV /
    # NEXT_SPRINT 在引用块算、在围栏里写盘，于是 run-state 恒写空游标，下 tick 断点续跑失效、
    # 从头全量重推，而上面那类检查因"全仓确实有人赋值"完全看不出来。
    # 判据严到零噪声：同一分片内，仅在引用块赋值 + 在非引用块围栏引用 + 该围栏内从未赋值。
    for path, info in files.items():
        lines = info["text"].splitlines()
        in_fence, q_assign, f_ref, f_assign = False, {}, {}, set()
        for i, ln in enumerate(lines, 1):
            body = ln.strip()
            is_quote = ln.lstrip().startswith(">")
            if body.startswith("```") and not is_quote:
                in_fence = not in_fence
                continue
            if is_quote:
                for rx in ASSIGN_RES:
                    for m in rx.finditer(ln):
                        if m.lastindex:
                            q_assign.setdefault(m.group(1), i)
            elif in_fence:
                for m in re.finditer(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)", ln):
                    f_ref.setdefault(m.group(1), i)
                for rx in ASSIGN_RES:
                    for m in rx.finditer(ln):
                        if m.lastindex:
                            f_assign.add(m.group(1))
        for v, qline in q_assign.items():
            if v in f_assign or v not in f_ref or v in tickvars:
                continue
            findings.append({
                "kind": "cross-fence", "file": os.path.relpath(path, root),
                "line": f_ref[v], "var": v,
                "context": f"引用块 L{qline} 赋值 → 围栏 L{f_ref[v]} 引用（跨 Bash 调用取空）",
            })

    # 同一文件同一变量只报首次，避免刷屏
    seen, uniq = set(), []
    for f in findings:
        k = (f["file"], f["var"], f.get("kind", "undefined-var"))
        if k not in seen:
            seen.add(k)
            uniq.append(f)
    return {"scanned": len(files), "assigned": len(assigned), "findings": uniq,
            "baseline_orphans": scan_baseline_orphans(root)}



# ─────────────────────────────────────────────── B 类：baseline 字段读而无人写
#
# ⛔ 这一类此前**只有 docstring、没有实现**——文档承诺了一道门，跑出来的 [OK] 只覆盖 shell
#    变量。真实代价：`phase_beta_done_at` / `last_deployed_at` / `internal_released_at` /
#    `last_autopilot_head` 四个**跨链路交接字段**的写入指令全部停留在散文从句里，全仓
#    零 `set`；读侧照读 → 恒空 → 两条 loop 都在刷屏、什么都没测，两小时后还冻结在一个
#    错误的原因上。为它专设的门是空的，所以没人发现。
#
# 判 WARN 不判 ERROR：写入方确实可能在 SKILL 内、或由运行时动态生成，误报成本高于漏报。
# 但**必须报出来**——"看起来有人管"的空门比没有门更坏。

# 读法：`baseline_edit.py [...] get <path>` / `jq '...versions...<字段>'`
_BE_GET_RE = re.compile(r"baseline_edit\.py[^\n|]*?\bget\s+([A-Za-z_][\w.]*)")
_JQ_FIELD_RE = re.compile(r'''jq\s+-r?\s*['"][^'"]*?\.versions[^'"]*?\.(\w+)''')
# 写法：baseline_edit.py 的 set/bump/touch/run-state，或 python 里 `["<字段>"] =`
# ⚠️ 一条 `set` 可带**多个** `字段 值` 对（`set a @now b @now`）；只捕首个会把后面的
#    字段误报成无写入方。故先切出 set 之后的整段，再逐个取字段样 token。
_BE_SET_SEG_RE = re.compile(r"\b(?:set|bump|touch)\b([^\n|]{0,300})")
_FIELD_TOKEN_RE = re.compile(r"\b([a-z_][a-z0-9_]{3,})\b")
# ⚠️ 只认**baseline 版本/build 节点**上的读取。放宽到"任意 .get()"会把各脚本自己的
#    输出键（commit_gate 的 JSON、notify 的配置…）全卷进来——实测 79 条噪音，
#    噪音一大这道门就等于不存在，那是它上一次失效的方式（只有 docstring、没有实现）。
_BASELINE_NODE = r"(?:v|vv|vobj|vnode|ver|vers|b|bobj|bentry|bew|build|entry|node)"
_PY_GET_RE = re.compile(r"""\b%s\.get\(\s*['"]([a-z][a-z0-9_]{5,})['"]""" % _BASELINE_NODE)
_PY_WRITE_RE = re.compile(r"""\[\s*['"]([a-z_][a-z0-9_]{3,})['"]\s*\]\s*=""")

# 这些是 baseline_edit.py 的子命令 / 通用选项，不是字段名
_BE_NOISE = {"version", "build", "default", "baseline", "json", "quiet", "shell", "command",
             "state", "summary", "pending", "root", "force", "value", "path", "true", "false",
             "null", "none", "auto", "phase", "status", "reason", "kind", "name", "type"}


def _all_text(root):
    """flows + commands + scripts 的全部正文（累加型字段查归零点用；语料面同 _scan_baseline_fields）。

    ⛔ **必须排除本文件自身**：本文件里写着 `del … <字段>` 形态的**说明性示例**，
    不排除的话「检查器拿自己的注释当作被检查方合规的证据」——阳性对照实测过：
    删掉真实归零点后本门仍判通过，唯一命中者就是这段注释。
    检查器的自述永远不能算证据，这是与「SKILL 自我文档不能证明命令端已接线」同一条纪律。
    """
    self_path = os.path.abspath(__file__)
    buf = []
    for sub in (FLOW_ROOT, runtime_text('__AIDP_HOME__/commands', __file__), runtime_text('__AIDP_HOME__/scripts', __file__)):
        base = os.path.join(root, sub)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames
                           if d not in EXCLUDE_DIRS and not d.startswith(EXCLUDE_DIR_PREFIXES)]
            if os.path.basename(dirpath) == "tests":
                continue
            for fn in sorted(filenames):
                if fn.endswith((".md", ".py")):
                    fp = os.path.join(dirpath, fn)
                    if os.path.abspath(fp) == self_path:
                        continue
                    try:
                        with open(fp, encoding="utf-8", errors="replace") as fh:
                            buf.append(fh.read())
                    except OSError:
                        pass
    return "\n".join(buf)


def _scan_baseline_fields(root):
    """返回 (读到的字段 -> 首个 文件:行, 写到的字段集合)。扫 flows + commands + scripts。"""
    reads, writes = {}, set()
    targets = []
    for sub in (FLOW_ROOT, runtime_text('__AIDP_HOME__/commands', __file__), runtime_text('__AIDP_HOME__/scripts', __file__)):
        base = os.path.join(root, sub)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames
                           if d not in EXCLUDE_DIRS and not d.startswith(EXCLUDE_DIR_PREFIXES)]
            if os.path.basename(dirpath) == "tests":
                continue          # 单测里的断言字典不是 baseline
            for fn in sorted(filenames):
                if fn.endswith((".md", ".py")):
                    targets.append(os.path.join(dirpath, fn))
    for path in targets:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                lines = fh.read().splitlines()
        except OSError:
            continue
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        prev_cont = False        # 上一行以 `\` 续行且带写入标记
        for i, line in enumerate(lines, 1):
            for m in _BE_GET_RE.finditer(line):
                f = m.group(1).split(".")[-1]
                if f and f not in _BE_NOISE:
                    reads.setdefault(f, f"{rel}:{i}")
            for m in _JQ_FIELD_RE.finditer(line):
                f = m.group(1)
                if f and f not in _BE_NOISE:
                    reads.setdefault(f, f"{rel}:{i}")
            # ★ 写入方识别必须认 `$BE` / `$BEV` 这类**别名**——仓内绝大多数写入都走
            #   `BE="python3 AIDP_HOME/scripts/baseline_edit.py"` 再 `$BE set ...`；
            #   只认全名会把一大批有写入的字段误报成孤儿，噪音一大这道门就会被无视。
            # ⚠️ 必须认 `\` 续行：`baseline_edit.py --version X \` 换行后才是 `set 字段 @now`，
            #    只看单行会把这类写入判成不存在（实测漏掉 internal_released_at）。
            _marked = ("baseline_edit.py" in line or "run-state" in line
                       or re.search(r"\$\{?BE[A-Z]*\}?\s", line)   # $BE / $BEV / $BEB … 一族别名
                       or "tick_flags.py set" in line)
            # ★ 第三种写入形态：`autopilot_fail_handle.py --streak-key <字段>` —— 该脚本内部
            #   一次做完 bump + 四件套写入。⛔ 不认它，把手抄 bump 收敛进脚本这件**修复**
            #   会被本门报成「只清零不递增、熔断永不触发」，而事实恰好相反。
            for _m in re.finditer(r"--streak-key\s+[\"\']?([A-Za-z_][A-Za-z0-9_]*)", line):
                writes.add(_m.group(1))
            if _marked or prev_cont:
                for seg in _BE_SET_SEG_RE.finditer(line):
                    for t in _FIELD_TOKEN_RE.finditer(seg.group(1)):
                        writes.add(t.group(1))
            prev_cont = (_marked or prev_cont) and line.rstrip().endswith("\\")
            if path.endswith(".py"):
                for m in _PY_WRITE_RE.finditer(line):
                    writes.add(m.group(1))
                # 读侧：`v.get("phase_beta_done_at")` 这类**脚本内**的 baseline 字段读取。
                # 四个跨链路交接字段全部只在脚本里被读、在 flow 里"被散文要求写"，
                # 不扫这一侧就恰好漏掉危害最大的那一类。
                for m in _PY_GET_RE.finditer(line):
                    f = m.group(1)
                    if f not in _BE_NOISE and len(f) > 6 and "_" in f:
                        reads.setdefault(f, f"{rel}:{i}")
    return reads, writes


# ★ 跨链路【交接字段】——两条 loop 靠它们互相知会"该我了"。它们的共同特征：
#   **读侧在脚本里、写侧的指令只写在 flow 的散文从句里**，于是"写"这一步从来没人执行。
#   后果不是报错而是静默停摆：测试链路每 tick 选不出版本、直接 exit 0，开发链路却因心跳
#   还在而判"测试链路健康"，两条 loop 都在正常刷屏、什么都没测，最后冻结在错误的原因上。
#   本清单里的字段**必须有确定性写入点**（`baseline_edit.py set` / `$BE set` 等可执行语句），
#   ⛔ 散文里写"再写 baseline 的 X"不算。
HANDOFF_FIELDS = {
    "phase_beta_done_at":  "开发链路 → 测试链路：本版可测（baseline_edit.py current-version 的选版判据）",
    "last_deployed_at":    "部署就绪信号：测试链路据它触发实测、开发链路 0a 门据它判部署可达",
    "internal_released_at": "准发布归档：不写则版本永留候选集，测试链路持续重测已归档版本",
    "last_autopilot_head": "retest-cap 的人工修复判别；恒空会让 3 轮上限退化为无限自动复测",
    # ↓ 以下为第二批：清单只有 4 项时这道门恒 [OK]，而下面这些字段同样是
    #   「读侧可执行、写侧只有散文」的形态，各自都能让链路静默停摆。
    "ai_report_finalized": "报告冻结基准；4 处可执行读侧（准发布 0b 门 / 已测去重 / Stop hook / "
                           "emit-report 不可变锁）。恒 false ⇒ 0b 门永不通过，第 12 tick 冻结在"
                           " unconverged——而测试其实早就跑完并通过了",
    "cicd_retry_count":    "CICD 失败重试计数；恒 0 ⇒「≤3 次」跨 tick 永不达阈，坏流水线可无限重跑",
    "run_commit":          "重试必须 pin 的 commit；恒空 ⇒ 重试变成「部署一份从未被确认过的新代码」",
    "probe_fail_streak":   "部署探测失败计数；只清零不递增 ⇒「≥3 次冻结止损」永不触发，"
                           "每 tick 重探 900s + 刷 #4",
    "auto_retest_streak":  "自动复测轮次；有 get/bump 无 del ⇒ 3 轮上限耗尽即永久锁死",
    "frontend_changed":    "半截部署门 3e 的入参；不为 True 时该门连一行都不输出（if/elif 无 else）",
}

# ★ 「累加型」字段：光有写入方还不够，**必须另有归零点**（`del` 或 `set … 0`）。
#   ⛔ 上一版把 `bump` 也算作「有写入」，于是这几个字段永远判"有供给"、
#   而 HANDOFF_FIELDS 里逐字写着的那条隐患（"有 get/bump 无 del ⇒ 上限耗尽即永久锁死"）
#   **这道门自己结构上永不触发**。实测代价：`auto_retest_streak` 全仓零归零点活了很久——
#   人工介入一次后配额恒为满，「每周期最多自动跑 3 轮」永久退化成 0 轮。
COUNTER_FIELDS = {
    "auto_retest_streak":  "人工介入周期内的自动复测配额；无归零点 ⇒ 解冻后配额恒满、下一轮立刻再撞上限",
    "probe_fail_streak":   "部署探测失败计数；无归零点 ⇒ 环境恢复后仍带着旧计数，一失败就立刻达阈",
    "cicd_retry_count":    "CICD 失败重试计数；无归零点 ⇒ 新一轮部署继承上轮次数，可用重试次数被吃掉",
    "dev_fail_streak":     "Phase 失败计数；无归零点 ⇒「连续失败」退化成终身累计，跨天攒够即冻 handoff-exhausted",
}

# ★ 反面判据：出现在 `del` 清单里、却**全仓没有任何 bump / set N** 的计数器。
#   归零点存在说明「有人以为它在计数」，而没有递增方 = **阈值永远达不到** ⇒ 那道熔断门
#   一次也不会触发。失效形态是「每 tick 从头重跑一整轮、通知渠道零消息、无 streak、无冻结」，
#   与「一切正常」在产物上完全同形 —— 比"无归零点"更隐蔽，因为它连锁死都不会发生。
#   ⚠️ 只查 `*_streak` / `*_count` 这类**语义即计数器**的名字，避免误伤普通标志位。
COUNTER_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*(?:_streak|_count|_retry_count)$")


def scan_baseline_orphans(root):
    """B 类结果：**交接字段**读了但全仓找不到确定性写入点。

    只判 HANDOFF_FIELDS 这几个，**刻意不做全量 baseline 字段扫描**——实测放开到"任意
    `.get()`"会一次报 79 条各脚本自己的输出键；噪音一大这道门就会被无视，
    而"看起来有人管"的空门比没有门更坏（这正是它上一次失效的方式：只有 docstring、没有实现）。
    新增交接字段时往 HANDOFF_FIELDS 里加一行即可。
    """
    _, writes = _scan_baseline_fields(root)
    out = []
    for field, why in sorted(HANDOFF_FIELDS.items()):
        if field in writes:
            continue
        out.append({"kind": "handoff-field-no-writer", "field": field, "why": why})
    # ★ 累加型字段另查归零点：`bump` 是写入、但**不是归零**。
    # ⚠️ 先把 shell 续行符折叠：真实的成套 del 恒写成多行
    #    （`$BE del needs_human \\` 换行 `  auto_retest_streak`），
    #    不折叠则 `[^\n]` 永远跨不过去 → 明明有归零点却仍报缺失（本检查初版即如此）。
    hay = re.sub(r"\\\s*\n\s*", " ", _all_text(root))
    for field, why in sorted(COUNTER_FIELDS.items()):
        zeroed = (re.search(r"\bdel\b[^\n]{0,200}\b" + re.escape(field) + r"\b", hay)
                  or re.search(r"\bset\b[^\n]{0,200}\b" + re.escape(field) + r"\s+0\b", hay))
        if not zeroed:
            out.append({"kind": "counter-field-no-reset", "field": field, "why": why})
    # ★ 反面：`del` 清单里出现过、却没有任何递增方的计数器 → 该熔断门永不触发
    deleted = set()
    for m in re.finditer(r"\bdel\b([^\n]{0,300})", hay):
        for tok in re.findall(r"[A-Za-z_][A-Za-z0-9_.]*", m.group(1)):
            leaf = tok.rsplit(".", 1)[-1]
            if COUNTER_NAME_RE.match(leaf):
                deleted.add(leaf)
    for field in sorted(deleted):
        if re.search(r"\bbump\b[^\n]{0,200}\b" + re.escape(field) + r"\b", hay):
            continue
        if re.search(r"\bset\b[^\n]{0,200}\b" + re.escape(field) + r"\s+[1-9]", hay):
            continue
        # ★ 第三种递增形态：`autopilot_fail_handle.py --streak-key <字段>`（bump 收进了脚本）。
        #   ⛔ 不认它的代价不是少认一种写法，而是**这道门跟着重构一起反转**：把手抄的
        #   bump 收敛进脚本本是修复，本门却会因此报「无任何 bump ⇒ 熔断永不触发」——
        #   一条精确描述了反面事实的假红。假红常驻 = 硬门被绕过，与失明同价。
        if re.search(r"--streak-key\s+[\"\']?" + re.escape(field) + r"\b", hay):
            continue
        out.append({"kind": "counter-field-no-increment", "field": field,
                    "why": "有归零点、无任何 bump/set N ⇒ 阈值永远达不到，该熔断门一次也不会触发"})
    return out


def main():
    ap = argparse.ArgumentParser(
        description="flow 分片 bash 块里「读了但全仓没人写」的 shell 变量")
    ap.add_argument("--root", default=".")
    ap.add_argument("--path", action="append", default=None,
                    help=runtime_text('只扫指定相对路径（可重复）；缺省扫 __AIDP_HOME__/flows', __file__))
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--per-fence", action="store_true",
                    help="把「已赋值」收紧到**本围栏内、引用行之前**（围栏 = 一次独立 Bash 调用）")
    ap.add_argument("--strict", action="store_true",
                    help="逐文件判定：分片自己既没赋值、也没取回手段的引用即报错"
                         "（flow 分片间 shell 变量不持久，这才是真正的判据）")
    ap.add_argument("--self-check", action="store_true",
                    help="阳性对照自检：注入必然命中的探针，验证本检查确实生效"
                         "（骨架与探针登记表见 selfcheck.py）")
    args = ap.parse_args()
    if args.self_check:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from selfcheck import run_self_check
        sys.exit(run_self_check(os.path.basename(__file__),
                                json_out=getattr(args, "json", False)))

    try:
        res = run(args.root, args.path, strict=args.strict,
                  per_fence=getattr(args, 'per_fence', False))
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False) if args.json
              else f"[ERROR] 检查执行失败：{e}")
        return 2

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    elif not res["findings"]:
        print(f"[OK] flow 分片无未定义变量引用{'（逐文件严格模式）' if args.strict else ''}"
              f"（巡检 {res['scanned']} 份分片，已知赋值 {res['assigned']} 个）")
    else:
        scope = "【本分片内既未赋值、也无取回手段】" if args.strict else "【全仓 flow 从未赋值】"
        print(f"[FAIL] 检出 {len(res['findings'])} 处引用了{scope}的变量"
              f"（巡检 {res['scanned']} 份分片）——它们必然取空，"
              f"`${{VAR:-默认}}` 会静默落到默认值、判据恒真或恒假：")
        for f in res["findings"]:
            print(f"  · {f['file']}:{f['line']}  ${f['var']}")
            if f.get("detail"):
                print(f"      ↳ {f['detail']}")
            print(f"      {f['context']}")
        print("  修复：① 同分片内先赋值；② 或经 baseline 落盘 + 读回"
              "（分片间 shell state 不跨 Bash 调用持久）；"
              "③ 确由命令端注入 → 在引用它的文件里加 `<!-- flowvar-check: allow VAR -->`。")
    orphans = res.get("baseline_orphans") or []
    if orphans and not args.json:
        print(f"\n[FAIL] {len(orphans)} 个**跨链路交接字段**只被读、全仓无确定性写入点"
              "（散文里写「再写 baseline 的 X」不算）：")
        for o in orphans:
            print(f"  · {o['field']}\n      ↳ {o['why']}")
        print(runtime_text('  后果不是报错、是静默停摆：读侧恒空 → 分支恒真/恒假 → 两条 loop 都在刷屏、什么都没测。\n  修复：在对应 flow 里落成可执行的 `python3 __AIDP_HOME__/scripts/baseline_edit.py --version $V set <字段> @now`。', __file__))
    return 1 if (res["findings"] or orphans) else 0


if __name__ == "__main__":
    sys.exit(main())
