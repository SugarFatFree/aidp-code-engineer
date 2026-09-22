#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_ghost_flags.py — 幽灵旗标检测（文档教用户传的 flag 必须真的存在；脚手架契约脚本）。

## 为什么需要本脚本

AIDP 的命令 flag 有两处落点：**定义处**（`AIDP_HOME/commands/*.md` 的参数表 / 参数列表 /
命令语法块）与**引用处**（flows 分片、reference 速查、docs/init 指导、命令正文互相引用）。
两处**没有任何机器约束**，于是稳定复发两类缺陷：

  · **幽灵旗标**——文档言之凿凿教用户传 `--aiauto-suite` / `--suite` / `--skip-audit`，
    可这些 flag **在任何命令里都没有定义**。用户照抄执行，命令端解析不到、静默当无参跑，
    "我明明加了 flag 却没生效"，排查成本极高（一次审计实测检出多个）。
  · **未登记旗标**（同一枚硬币的反面）——`/sprint-full` 正文消费 `--unattended` /
    `--stop-on-blocker`，却没写进自己的参数表，读者无从得知它支持。

这类缺陷**不会**被任何现有检查发现：文件在（不是断链）、锚点通（不是死链）、文字读得通。
只有真去跑一次命令才知道 flag 是假的。故固化为有退出码的硬门。

## 判定口径

**A. 定义源（满足任一即视为"该 flag 存在"）**

  1. `AIDP_HOME/commands/*.md` 的**表格首格**：`| `--x` | 默认 | 说明 |`（首格内多个 flag
     如 `` `--a` / `--b` `` 全部登记）；
  2. `AIDP_HOME/commands/*.md` 的**参数列表项**：`- `--x`：说明` / `- **`--x`** — 说明`；
  3. `AIDP_HOME/commands/<cmd>.md` 的**自身命令语法块**：围栏代码块里以 `/<cmd>` 开头的行
     （`## 命令语法` 段的惯用写法，如 `/sprint-batch --dry-run  # …`），整行的 flag 全登记
     —— 只认**该文件自己那条命令**，`/loop 10m /sprint-autopilot` 这种"调别的命令"不算定义；
  4. `AIDP_HOME/commands/*.md` 的**小标题**：`### `--x` 模式`；
  5. 仓库内 Python 的 `add_argument("--x"` —— 脚本类 flag 的权威定义；
  6. 仓库内脚本源码（`.py/.js/.mjs/.cjs/.ts/.sh`，含 `AIDP_HOME/skills/`）里的 **flag 字符串
     字面量** `"--x"` —— 覆盖 skill 自带 CLI（如 chrome-devtools）。

**B. 引用面**：`AIDP_HOME/commands`、`AIDP_HOME/flows`、`AIDP_HOME/reference`、`docs/init` 的 `.md`，
抽两类提及：① 行内代码里的 `` `--x` `` ② **围栏代码块内裸写**的 `--x`（`/cmd --x` 示例的
常见形态，不抽会漏掉最该抓的"可复制粘贴的错误示例"）。

**C. 结论**：提及了、A 全部落空、又不在豁免面内 → **未定义旗标（ERROR）**。
反向（定义了但全仓无人引用）→ **可能废弃（INFO，不影响退出码）**，只作提示。

## 豁免（零误报是本护栏的生命线）

一个天天误报的守卫等于没有。豁免分四层，**全部显式、可审计**：

  0. **旗标归属（owner）判定** —— 主力降噪，且**自维护**：每个提及都归属到它所在命令片段
     （按 `| ; && || $( ` 切段）的**首个命令 token**（跳过 `sudo`/`python3` 等前缀词）。

         · owner 是 AIDP 斜杠命令（`/sprint-batch --x`）        → **在检查范围**
         · owner 是本仓脚本（`AIDP_HOME/scripts/*.py` 的文件名）   → **在检查范围**（由 add_argument 兜底）
         · owner 是其它可执行名（`git` / `npx` / `claude` / `rmdir` / skill 自带 CLI …）→ **不在范围**
         · 段内没有 owner（如表格里孤零零一个 `` `--x` ``）      → **在检查范围**

     Why 这条排第一：`git branch --list` / `rmdir --ignore-fail-on-non-empty` /
     `claude mcp add --scope` 这类第三方 flag 数量无穷、永远列不完；靠"谁的 flag"判定，
     新写一条 `git xxx --yyy` 不会再制造误报，白名单就不必追着外部工具跑。

  1. `THIRD_PARTY_FLAG_WHITELIST` —— 只兜 owner 判定覆盖不到的**裸提及**（散文里单独写一个
     `` `--pomp` ``、`` `--headless` `` 讲上游工具的参数，句中没有命令 token 可归属）。
     **按工具分组 + 逐组写明为什么豁免**；这些 flag 的权威定义在别人的仓库里，本仓无从校验。
  2. `IGNORED_FLAG_PREFIXES` —— 前缀豁免，目前只用于 **CSS 自定义属性**（`--el-color-primary`
     等），它们和命令行 flag 长得一模一样但根本不是 flag；
  3. 行内豁免标记（教学示例 / 反面教材 / 占位符必用）：

         <!-- flag-check: ignore -->              该行豁免
         <!-- flag-check: ignore-file 理由 -->     整份文件豁免
         <!-- flag-check: ignore-begin 理由 -->    区块开始
         ...
         <!-- flag-check: ignore-end -->          区块结束

## 用法

    python3 AIDP_HOME/scripts/check_ghost_flags.py               # 人读报告
    python3 AIDP_HOME/scripts/check_ghost_flags.py --json        # 机读 JSON
    python3 AIDP_HOME/scripts/check_ghost_flags.py --show-orphans  # additionally 列 INFO
    python3 AIDP_HOME/scripts/check_ghost_flags.py --root . --path AIDP_HOME/commands

退出码：0 = 无未定义旗标；1 = 检出未定义旗标；2 = 用法/读取错误。
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

# ── 引用面（抽"文档教人传什么 flag"）──────────────────────────────
DEFAULT_MENTION_PATHS = [
    runtime_text('__AIDP_HOME__/commands', __file__),
    runtime_text('__AIDP_HOME__/flows', __file__),
    runtime_text('__AIDP_HOME__/reference', __file__),
    "docs/init",
]
# ── 定义面（命令参数的权威落点）────────────────────────────────
COMMANDS_DIR = runtime_text('__AIDP_HOME__/commands', __file__)
# ── 源码定义面（脚本 / skill 自带 CLI 的 flag 字面量）──────────────
SOURCE_DIRS = [runtime_text('__AIDP_HOME__/scripts', __file__), runtime_text('__AIDP_HOME__/skills', __file__)]
SOURCE_EXTS = (".py", ".js", ".mjs", ".cjs", ".ts", ".sh")
SKIP_DIRS = {"__pycache__", ".git", "node_modules", "dist", "build", ".venv"}

FLAG_BODY = r"--[A-Za-z][A-Za-z0-9-]*"
FENCE_RE = re.compile(r"^\s*(```|~~~)")
INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
FLAG_RE = re.compile(FLAG_BODY)
ADD_ARGUMENT_RE = re.compile(r'add_argument\(\s*["\'](' + FLAG_BODY + r')["\']')
# 末尾允许一个 `=`：`a.startswith("--mode=")` 这类"带值 flag"的手写解析同样算定义
SOURCE_LITERAL_RE = re.compile(r'["\'](' + FLAG_BODY + r')=?["\']')

# 命令片段切分：管道 / 逻辑连接 / 分号 / 命令替换 / 反引号，都开启一个新的"谁的 flag"作用域
SEGMENT_SPLIT_RE = re.compile(r"\|\||\||&&|&|;|\$\(|\)|<\(|`|\n")
# 前缀词（解释器 / 包装器）：跳过后才是真正的 owner
OWNER_SKIP_TOKENS = {
    "sudo", "env", "time", "exec", "command", "nohup", "xargs", "then", "else", "do", "fi",
    "python", "python3", "py", "bash", "sh", "zsh", "source", ".",
}
OWNER_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

# 定义形态
TABLE_ROW_RE = re.compile(r"^\s*\|(?P<first>[^|]*)\|")
LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+(?P<rest>.*)$")
HEADING_RE = re.compile(r"^#{1,6}\s+(?P<rest>.*)$")

IGNORE_LINE_RE = re.compile(r"<!--\s*flag-check:\s*ignore\s*(?:-->|\s)")
IGNORE_FILE_RE = re.compile(r"<!--\s*flag-check:\s*ignore-file")
IGNORE_BEGIN_RE = re.compile(r"<!--\s*flag-check:\s*ignore-begin")
IGNORE_END_RE = re.compile(r"<!--\s*flag-check:\s*ignore-end")

# ─────────────────────────────────────────────────────────────
# 豁免层 1：第三方工具 flag 白名单（**只兜 owner 判定覆盖不到的裸提及**）
#
# owner 判定已经把 `git branch --list` / `claude mcp add --scope` 这类"跟着命令一起出现"的
# 第三方 flag 全部挡在范围外，故本表**只需收录散文里单独出现、无命令可归属**的那些。
#
# 收录标准（三条同时满足才准进）：
#   ① 该 flag 的权威定义在**别人的仓库**（外部 CLI / 上游 skill / 浏览器内核），本仓无从校验；
#   ② 文档里出现它是在**讲那个工具的参数**，不是在教用户给 AIDP 斜杠命令传参；
#   ③ 拼错了会由那个工具自己报错，不属于"静默失效"的幽灵旗标风险面。
# 只要某条不满足（例如它其实是 AIDP 命令的 flag），就该去把它**定义清楚**，而不是加白名单。
# ─────────────────────────────────────────────────────────────
THIRD_PARTY_FLAG_WHITELIST = {
    # ── CICD 流水线参数（`cicd_watch.py` 定义，平台差异在 `cicd_providers.py`）──
    #    散文里讲"锚定哪条流水线 / 触发哪个分支"时常裸提，无命令 token 可归属。
    "--pipeline", "--ref",
    # ── chrome / chrome-devtools-mcp（`/sprint-aiauto-test` 浏览器链路）──
    #    浏览器内核 + MCP 驱动自带参数，由 chrome-devtools-mcp 上游定义；文档在讲"连接模式
    #    该带哪个参数"时经常裸提。
    "--headless", "--isolated", "--browser-url", "--executablePath", "--mcp-config",
    "--remote-allow-origins", "--user-data-dir", "--remote-debugging-port",
    "--no-sandbox", "--channel", "--args", "--no-first-run",
    #    ↓ secure context 白名单参数（WebMCP 可选能力用；`rules/webmcp.md` §1.3）——
    #      文档在表格里逐参数解释"为什么必须带它"时是裸提及，无 chrome token 可归属。
    "--unsafely-treat-insecure-origin-as-secure",
    # ── claude CLI（无头跑 / MCP 注册引导里裸提）──
    "--dangerously-skip-permissions", "--scope", "--permission-mode",
    # ── git（散文里裸提"用 `--rebase` 而非 merge"这类，无 `git` token 可归属）──
    "--author", "--amend", "--no-verify", "--force-with-lease",
    "--rebase", "--autostash", "--show-current", "--prune", "--abort",
    "--pretty", "--date", "--no-merges", "--since", "--until",
}

# 豁免层 2：前缀豁免 —— CSS 自定义属性长得像 flag 但不是 flag
IGNORED_FLAG_PREFIXES = (
    "--el-",   # Element Plus 设计令牌：--el-color-primary / --el-border-radius-…
    "--van-",  # Vant
    "--ant-",  # Ant Design
    "--tw-",   # Tailwind
    "--var-",  # 通用自定义属性写法
)


def _iter_files(root, rels, exts, skip_dirs=SKIP_DIRS):
    """遍历给定相对路径下的指定后缀文件（目录/单文件皆可）。"""
    for rel in rels:
        p = os.path.join(root, rel)
        if os.path.isfile(p) and p.endswith(exts):
            yield p
        elif os.path.isdir(p):
            for dirpath, dirnames, filenames in os.walk(p):
                dirnames[:] = [d for d in dirnames if d not in skip_dirs]
                for fn in sorted(filenames):
                    if fn.endswith(exts):
                        yield os.path.join(dirpath, fn)


def _flags_in(text):
    """抽一段文本里的全部 flag（含裸写）。"""
    return FLAG_RE.findall(text)


def _flags_in_code_spans(text, own_only=False):
    """只抽行内代码 `…` 里的 flag（正文散文里的裸 `--x` 不算提及，避免把破折号误当 flag）。

    `own_only=True`（抽**定义**时用）：只认 owner 为空或 AIDP 斜杠命令的片段 ——
    `| \\`git log --since=…\\` | 作用 |` 这种"数据源表"的首格长得和参数表一模一样，
    不判 owner 就会把 `--since`/`--stat` 登记成本项目的命令 flag（假定义 + 污染废弃提示）。
    """
    out = []
    for span in INLINE_CODE_RE.findall(text):
        if own_only:
            for seg in SEGMENT_SPLIT_RE.split(span):
                owner = segment_owner(seg)
                if owner and not owner.startswith("/"):
                    continue
                out.extend(FLAG_RE.findall(seg))
        else:
            out.extend(FLAG_RE.findall(span))
    return out


def collect_definitions_from_commands(root):
    """从 `AIDP_HOME/commands/*.md` 抽 flag 定义，返回 {flag: [来源, …]}。"""
    defs = {}

    def add(flag, where):
        defs.setdefault(flag, []).append(where)

    cmd_dir = os.path.join(root, COMMANDS_DIR)
    if not os.path.isdir(cmd_dir):
        return defs
    for path in sorted(_iter_files(root, [COMMANDS_DIR], (".md",))):
        rel = os.path.relpath(path, root)
        own_cmd = "/" + os.path.splitext(os.path.basename(path))[0]  # sprint-dev.md → /sprint-dev
        own_cmd_re = re.compile(r"^\s*" + re.escape(own_cmd) + r"(?![\w-])")
        with open(path, "r", encoding="utf-8") as f:
            lines = f.read().split("\n")
        in_fence = False
        for i, line in enumerate(lines, 1):
            if FENCE_RE.match(line):
                in_fence = not in_fence
                continue
            if in_fence:
                # 形态 3：命令语法块里"自己那条命令"的用法行
                if own_cmd_re.match(line):
                    for fl in _flags_in(line.split("#", 1)[0]):
                        add(fl, f"{rel}:{i}（命令语法块）")
                continue
            m = TABLE_ROW_RE.match(line)
            if m:  # 形态 1：表格首格
                for fl in _flags_in_code_spans(m.group("first"), own_only=True):
                    add(fl, f"{rel}:{i}（参数表）")
                continue
            m = LIST_ITEM_RE.match(line)
            if m:  # 形态 2：参数列表项 —— 只认**开头第一个**代码span，防"说明里顺带提到"被当定义
                spans = INLINE_CODE_RE.findall(m.group("rest"))
                if spans and m.group("rest").lstrip("*★ ").startswith("`"):
                    for fl in _flags_in_code_spans("`" + spans[0] + "`", own_only=True):
                        add(fl, f"{rel}:{i}（参数列表）")
                continue
            m = HEADING_RE.match(line)
            if m:  # 形态 4：小标题即定义（`### \`--xxx\` 模式`）
                for fl in _flags_in_code_spans(m.group("rest"), own_only=True):
                    add(fl, f"{rel}:{i}（小标题）")
    return defs


def collect_definitions_from_sources(root):
    """从仓库脚本源码抽 flag：argparse 的 `add_argument("--x")` + 任意 flag 字符串字面量。"""
    defs = {}
    for path in _iter_files(root, SOURCE_DIRS, SOURCE_EXTS):
        rel = os.path.relpath(path, root)
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        except OSError:
            continue
        for fl in ADD_ARGUMENT_RE.findall(text):
            defs.setdefault(fl, []).append(f"{rel}（add_argument）")
        for fl in SOURCE_LITERAL_RE.findall(text):
            defs.setdefault(fl, []).append(f"{rel}（源码字面量）")
    return defs


def repo_script_names(root):
    """本仓可执行脚本文件名集合（`AIDP_HOME/scripts/*.py|sh|js`）—— owner 判定用。"""
    names = set()
    d = os.path.join(root, runtime_relpath("", __file__), "scripts")
    if os.path.isdir(d):
        for fn in os.listdir(d):
            if fn.endswith((".py", ".sh", ".js", ".mjs")):
                names.add(fn)
    return names


def segment_owner(segment):
    """取一个命令片段的 owner（首个真正的命令 token）；取不到返回 ""。"""
    for tok in segment.split():
        if OWNER_ASSIGN_RE.match(tok):      # 形如 `FOO=bar cmd …` 的前置环境赋值
            continue
        if tok in OWNER_SKIP_TOKENS:        # sudo / python3 / bash … 等包装词
            continue
        if tok.startswith("-"):             # 还没见到命令就先见到 flag → 无归属
            return ""
        tok = tok.strip("\"'()[]{}<>,，。;；")
        if not tok:                          # 纯标点（`{` / `"` 等 shell 结构符）→ 继续往后找
            continue                         # 不 continue 会把 `{ git pull --rebase … }` 判成无归属
        return tok
    return ""


def owner_in_scope(owner, script_names):
    """owner 是否属"本仓自己的东西"（AIDP 斜杠命令 / 本仓脚本）→ 其 flag 才受本护栏管辖。

    无 owner（散文里孤零零一个 `--x`）同样按**在范围**处理：幽灵旗标的典型形态就是
    "只写 flag、不写命令"，若把它当成不可判定而放过，本护栏就漏掉了最主要的一类。
    """
    if not owner:
        return True
    if owner.startswith("/"):                       # `/sprint-batch` 等 AIDP 斜杠命令
        return True
    return os.path.basename(owner) in script_names  # `AIDP_HOME/scripts/commit_gate.py`


def _mentions_with_owner(text, default_owner=""):
    """把一段命令文本切成片段，产出 [(flag, owner)]。

    `default_owner` 用于**围栏内 `\\` 续行**：`git log --since=… \\` 的下一行以 flag 开头、
    段内没有命令 token，不继承上一行的 owner 就会被误判成"无归属"→ 当成 AIDP flag 误报。
    """
    out = []
    for seg in SEGMENT_SPLIT_RE.split(text):
        if not seg or "--" not in seg:
            continue
        owner = segment_owner(seg) or default_owner
        for fl in FLAG_RE.findall(seg):
            out.append((fl, owner))
    return out


def collect_mentions(root, paths):
    """抽引用面的 flag 提及，返回 ({flag: [(rel, line), …]}, 已扫文件数)。

    只保留 owner 在范围内的提及（见 `owner_in_scope`）；围栏内认裸写、围栏外只认行内代码
    （散文里的破折号/连字符不该被当成 flag）。
    """
    script_names = repo_script_names(root)
    mentions, scanned = {}, 0
    for path in sorted(set(_iter_files(root, paths, (".md",)))):
        rel = os.path.relpath(path, root)
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        if IGNORE_FILE_RE.search(text):
            continue
        scanned += 1
        in_fence = in_ignore = False
        cont_owner = ""
        for i, line in enumerate(text.split("\n"), 1):
            if FENCE_RE.match(line):
                in_fence = not in_fence
                cont_owner = ""
                continue
            if IGNORE_BEGIN_RE.search(line):
                in_ignore = True
            elif IGNORE_END_RE.search(line):
                in_ignore = False
            if in_ignore or IGNORE_LINE_RE.search(line):
                continue
            if in_fence:
                # 围栏内裸写（可复制粘贴的示例，最该抓）；`#` 之后是注释
                chunks = [line.split("#", 1)[0]]
            else:
                chunks = INLINE_CODE_RE.findall(line)
                cont_owner = ""            # 续行继承只在围栏内成立
            for chunk in chunks:
                for fl, owner in _mentions_with_owner(chunk, cont_owner):
                    if owner_in_scope(owner, script_names):
                        mentions.setdefault(fl, []).append((rel, i))
            if in_fence:
                # 本行以 `\\` 结尾 → 下一行是它的续行，把 owner 传下去
                cont_owner = (segment_owner(chunks[0]) or cont_owner) \
                    if line.rstrip().endswith("\\") else ""
    return mentions, scanned


def is_exempt(flag):
    """白名单 / 前缀豁免。"""
    if flag in THIRD_PARTY_FLAG_WHITELIST:
        return True
    return any(flag.startswith(p) for p in IGNORED_FLAG_PREFIXES)


def run(root, paths=None):
    paths = paths or DEFAULT_MENTION_PATHS
    cmd_defs = collect_definitions_from_commands(root)
    src_defs = collect_definitions_from_sources(root)
    mentions, scanned = collect_mentions(root, paths)

    undefined = []
    for flag in sorted(mentions):
        if flag in cmd_defs or flag in src_defs or is_exempt(flag):
            continue
        # 同一行出现多次只记一处：报告里重复的 `file:line` 看着像脚本坏了
        sites = sorted({f"{rel}:{ln}" for rel, ln in mentions[flag]})
        undefined.append({"flag": flag, "count": len(sites), "sites": sites})

    # 反向：命令参数表定义了、但引用面（除定义行本身外）无人提及 → 可能已废弃
    orphans = []
    for flag, wheres in sorted(cmd_defs.items()):
        def_lines = set()
        for w in wheres:
            loc = w.split("（")[0]
            def_lines.add(loc)
        used = [f"{rel}:{ln}" for rel, ln in mentions.get(flag, [])
                if f"{rel}:{ln}" not in def_lines]
        if not used:
            orphans.append({"flag": flag, "defined_at": wheres})

    return {
        "scanned": scanned,
        "defined_in_commands": len(cmd_defs),
        "defined_in_sources": len(src_defs),
        "mentioned": len(mentions),
        "undefined": undefined,
        "orphans": orphans,
    }


def main():
    ap = argparse.ArgumentParser(
        description="幽灵旗标检测：文档教用户传的 flag 必须在某个命令/脚本里真有定义")
    ap.add_argument("--root", default=".", help="仓库根目录（默认当前目录）")
    ap.add_argument("--path", action="append", default=None,
                    help="只扫指定相对路径（可重复）；缺省扫命令/flows/reference/docs-init")
    ap.add_argument("--show-orphans", action="store_true",
                    help="额外列出「定义了但全仓没人用」的可能废弃 flag（INFO，不影响退出码）")
    ap.add_argument("--json", action="store_true", help="机读 JSON")
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
        res = run(args.root, args.path)
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False) if args.json
              else f"[ERROR] 检查执行失败：{e}")
        return 2

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        if not res["undefined"]:
            print(f"[OK] 无未定义旗标（巡检 {res['scanned']} 份 .md，"
                  f"提及 {res['mentioned']} 个 flag；命令定义 {res['defined_in_commands']} 个 / "
                  f"源码定义 {res['defined_in_sources']} 个）")
        else:
            print(f"[FAIL] 检出 {len(res['undefined'])} 个未定义旗标"
                  f"（巡检 {res['scanned']} 份 .md）：")
            for u in res["undefined"]:
                print(f"  · {u['flag']}（{u['count']} 处）")
                for s in u["sites"][:5]:
                    print(f"      {s}")
                if len(u["sites"]) > 5:
                    print(f"      …… 另 {len(u['sites']) - 5} 处")
            print(runtime_text('  修复三选一：① 该 flag 应存在 → 去对应 `__AIDP_HOME__/commands/*.md` 参数表补定义；② 文档写错了 → 改成真实存在的 flag（或删掉）；③ 属教学示例/反面教材 → 加 `<!-- flag-check: ignore -->` 行内豁免。', __file__))
        if args.show_orphans and res["orphans"]:
            print(f"\n[INFO] {len(res['orphans'])} 个 flag 只在参数表里定义、"
                  f"引用面无人提及（可能已废弃，不影响退出码）：")
            for o in res["orphans"]:
                print(f"  · {o['flag']}  ← {o['defined_at'][0]}")

    return 1 if res["undefined"] else 0


if __name__ == "__main__":
    sys.exit(main())
