#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""check_flow_bash_syntax.py — flow 分片里 ```bash 围栏的语法有效性（脚手架契约脚本）。

## 为什么需要本脚本

flow 分片里的 bash 围栏是**要被逐字执行的**，但它写在 Markdown 里、没有任何编译期检查。
一次维护就足以把它写坏，而坏法往往**看起来很正常**：

- 把注释插进 `\\` 续行中间 —— 续行会把注释行并进命令，参数解析立刻错乱；
- 编辑长行时从中间截断了字符串 —— 引号不配对，整段 here-doc/命令跟着塌；
- `case` 少了 `esac`、`if` 少了 `fi`、`$(` 没闭合。

这些在执行前一个字符都看不出来，执行时才炸——而 flow 分片的执行现场往往是
**7×24 无人值守的某个 tick**，炸了只留一行 stderr，没人看。

`bash -n` 只做**语法解析、不执行任何命令**，正好适合当这道门。

⚠️ 但它**抓不到第一类**：`cmd \` 后面跟一行 `# 注释`，续行会把两行并成
`cmd   # 注释   --flag`，`#` 之后全成注释 —— **语法完全合法、参数被静默吞掉**。
这类只能按词法判（行尾 `\` + 下一行首个非空字符是 `#`），故本脚本除 `bash -n` 外
另做一条 **B. 续行吞注释** 检查。它是无歧义的：这种写法没有任何正当用途。

## 占位符中和（零误报的关键）

flow 里大量使用 `<0.3.4 判定的 TARGET_VERSION>` / `<hash>` 这类**占位符**表示"由 Claude 就地代入"。
bash 会把 `<` 读成输入重定向 → 报假语法错。实测全仓 146 个围栏里有 7 个纯因此失败。
故在 `bash -n` 之前把 `<…>` 整体替换成一个普通 token。**这是本脚本能零误报的前提，别删。**

同理中和：`{{mustache}}` 模板占位、以及被 `> ` 引用块包裹的围栏（先剥引用前缀）。

## 判定

- 围栏 `bash -n` 不通过 → **ERROR**（会真的执行失败）。
- 只扫 ```bash / ```sh 围栏；其它语言围栏不碰。
- 扫描面 = `flows` / `commands` / `agents` / `reference` / `rules` —— 都是会被逐字执行的契约目录。

## 豁免

    <!-- bashsyntax-check: ignore -->        紧邻围栏上方一行，跳过该围栏
    <!-- bashsyntax-check: ignore-file 理由 -->  整份文件豁免

## bash 能力探针（Windows 零空等的关键）

本门的**唯一外部依赖**是一个能跑 `bash -n` 的 bash。而 `shutil.which("bash")` **不足以判定可用**：
Windows 上 `C:\Windows\System32\bash.exe` 是 WSL 转发壳，未装发行版时它会挂在那里等交互输入；
Git-Bash 的 `bash.exe` 在无 MSYS 运行时的机器上也可能存在但起不来。实测代价 = 每个围栏各挂一次，
调用方（`verify.py::_run_guard`）180 秒超时才收场，**一次 verify 被一条环境事实拖死**。

故执行前先做两段探测，任一失败即判「不适用」：
  ① `shutil.which("bash")` 找得到；
  ② 用它跑一次 `bash -c exit 0`（`BASH_PROBE_TIMEOUT` 秒上限、stdin 接 DEVNULL），rc 必须为 0。
探针本身有上限，所以**无论 bash 多坏，本门的最坏耗时都是常数**。
逐围栏的 `bash -n` 另设 `BASH_FENCE_TIMEOUT`：探针过了而某个围栏把 bash 挂住，同样立刻收敛成「不适用」，
⛔ 不允许退化成"等到调用方超时"。

## 退出码

| 码 | 含义 |
|----|------|
| 0 | 全部通过 |
| 1 | 有语法错 |
| 2 | 用法 / 参数错 |
| 3 | **不适用**（`N/A(bash-unavailable)`）：本机没有可用 bash，本门**一个围栏都没验过** |

⛔ 3 既不是"通过"也不是"环境炸了"：返回 0 会把"没验过"伪装成"验过且没问题"（假绿，最坏），
返回 2 会让调用方按环境错处理。3 是独立的第三态，JSON 里同时给 `applicable=false` /
`status="unsupported"` / `reason="bash-unavailable"` / `level="INFO"`，
调用方既可按退出码、也可按字段判，两条路同源。

用法:
    python3 AIDP_HOME/scripts/check_flow_bash_syntax.py [--root <仓库根>] [--json]
"""

from __future__ import annotations
import sys as _aidp_sys
from pathlib import Path as _AidpPath
_aidp_scripts = str((_AidpPath(__file__).resolve().parent if _AidpPath(__file__).resolve().parent.name == "scripts" else _AidpPath(__file__).resolve().parents[1] / "scripts"))
if _aidp_scripts not in _aidp_sys.path:
    _aidp_sys.path.insert(0, _aidp_scripts)
from aidp_runtime import runtime_relpath

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# 扫描面 = 所有会被**逐字执行**的契约目录。
# `agents/`（如 aidp-compliance 的检查命令）与 `reference/`（细则里的可执行片段）同样是执行面，
# 漏收 = 那些围栏永远没门管。`rules/` 目前无 bash 围栏，收进来也无害、日后加了自动覆盖。
SCAN_DIRS = ("flows", "commands", "agents", "reference", "rules")

OPEN_RE = re.compile(r"^((?:\s*>\s*)*)\s*```(?:bash|sh)\s*$")
CLOSE_RE = re.compile(r"^(?:\s*>\s*)*\s*```\s*$")
QUOTE_PREFIX_RE = re.compile(r"^\s*>\s?")

IGNORE_LINE_RE = re.compile(r"<!--\s*bashsyntax-check:\s*ignore\s*-->")
IGNORE_FILE_RE = re.compile(r"<!--\s*bashsyntax-check:\s*ignore-file")

# ★ 占位符中和：`<…>` 与 `{{…}}` 都是"由 Claude 就地代入"的记号，不是 bash 语法。
#   不中和就会被读成重定向 / 花括号展开 → 假语法错（实测 7 处）。
# ⚠️ 三处收窄缺一不可（否则会把 shell 自己的语法当占位符吃掉）：
#   · `(?<!<)` —— 不匹配 heredoc `<<'PY'`：实测 `python3 - <<'PY' 2>/dev/null` 里的 `<'PY' 2>`
#     会被当成占位符替换掉，heredoc 定界符没了 → 内嵌 Python 被 bash 当命令解析 → 假语法错；
#   · 排除 `'"` —— 带引号的几乎都是 shell 语法而非占位符；
#   · 排除 `/` —— 排掉 `2>/dev/null` 这类重定向片段。
#   · `(?!!)` —— **不匹配 HTML 注释 `<!-- … -->`**：它在 bash 里是**真语法错**
#     （`bash -n` 报 `syntax error near unexpected token 'newline'`，整块打死）。
#     把它当占位符中和掉，就等于给这个真错开了后门 —— 实测本仓有两处
#     `<!-- flowvar-check: allow … -->` 写在了围栏**内**，正因这条漏判而全绿。
#     这类标注要生效只需写在围栏**外**；写在里面会连坐整块。
PLACEHOLDER_RE = re.compile(r"(?<!<)<(?!!)([^<>\n'\"/]{1,120})>")
MUSTACHE_RE = re.compile(r"\{\{[^{}\n]{1,80}\}\}")

# ★ 两个上限都必须存在，且都要**小到人能等**。
#   探针：一次 `bash -c exit 0` 的正常耗时是毫秒级，5 秒已经宽到离谱；给它留大值没有收益，
#   只会让"不可用"这一结论迟迟不出来——而本门的调用方（verify.py）是串行跑几十道门的。
#   围栏：`bash -n` 不执行任何命令，正常也是毫秒级；10 秒仍不返回 = 这个 bash 有问题，
#   不是这个围栏有问题，故按「不适用」收敛而**不是**记一条 finding（记 finding 等于把
#   环境故障栽赃给契约正文，会让人去改一段本来没错的 bash）。
BASH_PROBE_TIMEOUT = 5
BASH_FENCE_TIMEOUT = 10
EXIT_NOT_APPLICABLE = 3


class BashUnavailable(RuntimeError):
    """本机没有可用 bash（或 bash 中途挂死）→ 本门不适用，⛔ 既不是通过也不是失败。"""


def probe_bash():
    """→ bash 可执行路径；不可用则抛 `BashUnavailable(原因)`。

    ⛔ 不要退回成只用 `shutil.which`：Windows 的 `bash.exe` 大量以"存在但起不来"的形态出现
    （WSL 转发壳未装发行版 / Git-Bash 缺 MSYS 运行时），which 对它们一律返回真。
    实测代价是每个围栏各挂一次，调用方 180 秒超时才收场。探针是这道门在 Windows 上
    **唯一**能把最坏耗时钉成常数的地方。
    """
    exe = shutil.which("bash")
    if not exe:
        return _fail("PATH 上找不到 bash")
    try:
        p = subprocess.run([exe, "-c", "exit 0"], stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=BASH_PROBE_TIMEOUT)
    except subprocess.TimeoutExpired:
        return _fail("`%s -c \"exit 0\"` %d 秒未返回（存在但不可用，典型如未装发行版的 WSL 转发壳）"
                     % (exe, BASH_PROBE_TIMEOUT))
    except OSError as e:
        return _fail("`%s` 无法执行：%s" % (exe, e))
    if p.returncode != 0:
        return _fail("`%s -c \"exit 0\"` 退出码 %d（存在但不可用）" % (exe, p.returncode))
    return exe


def _fail(reason):
    raise BashUnavailable(reason)


def _neutralize(code: str) -> str:
    code = PLACEHOLDER_RE.sub("PLACEHOLDER", code)
    code = MUSTACHE_RE.sub("PLACEHOLDER", code)
    return code


def iter_fences(text: str):
    """yield (起始行号1based, 围栏代码, 是否被 ignore 标记豁免)。"""
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = OPEN_RE.match(lines[i])
        if not m:
            i += 1
            continue
        quoted = bool(m.group(1).strip())
        waived = i > 0 and bool(IGNORE_LINE_RE.search(lines[i - 1]))
        j = i + 1
        body = []
        while j < len(lines) and not CLOSE_RE.match(lines[j]):
            ln = lines[j]
            if quoted:
                ln = QUOTE_PREFIX_RE.sub("", ln)
            body.append(ln)
            j += 1
        yield i + 1, "\n".join(body), waived
        i = j + 1


def run(root: Path, bash: str = "bash"):
    findings, scanned, waived = [], 0, 0
    for d in SCAN_DIRS:
        base = root / runtime_relpath("", __file__) / d
        if not base.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [x for x in dirnames if x != "__pycache__"]
            for fn in sorted(filenames):
                if not fn.endswith(".md"):
                    continue
                fp = Path(dirpath) / fn
                try:
                    text = fp.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                if IGNORE_FILE_RE.search(text):
                    continue
                rel = str(fp.relative_to(root))
                for line_no, code, skip in iter_fences(text):
                    if skip:
                        waived += 1
                        continue
                    scanned += 1
                    if not code.strip():
                        continue
                    try:
                        p = subprocess.run([bash, "-n"], input=_neutralize(code),
                                           capture_output=True, text=True,
                                           timeout=BASH_FENCE_TIMEOUT)
                    except (subprocess.TimeoutExpired, OSError) as e:
                        # 探针刚刚还是好的，这里却挂/炸 ⇒ 是 bash 的问题、不是围栏的问题。
                        # 立刻整门收敛成「不适用」，⛔ 不要 continue 到下一个围栏——
                        # 那会让剩下的上百个围栏一个个各挂 BASH_FENCE_TIMEOUT 秒，
                        # 正是本次要消灭的"空等到调用方超时"。
                        raise BashUnavailable(
                            "%s:%d 的围栏跑 `bash -n` 时 bash 未能返回（%s）——"
                            "已巡检 %d 个围栏后中止" % (rel, line_no, type(e).__name__, scanned))
                    if p.returncode != 0:
                        msg = (p.stderr or "").strip().splitlines()
                        findings.append({
                            "file": rel, "line": line_no, "kind": "syntax",
                            "detail": msg[0][:180] if msg else "bash -n 失败",
                        })
                    # C. **命令位**上的尖括号占位符（`<cicd-run> --x`）——
                    #    `bash -n` 永远抓不到它：`<` `>` 被解析成输入/输出重定向，整行**语法合法**，
                    #    运行时却只会新建一个以下一个参数命名的空文件、真正的命令一次没跑。
                    #    而本脚本自己的 `_neutralize` 又把占位符替换掉了，于是双重放行。
                    #    ⚠️ 只判**命令位**（行首、或仅隔着 `VAR=值` 形式的环境前缀）：
                    #    参数位/值位的 `<...>` 是正常模板写法，判它会满屏假红。
                    for k, raw in enumerate(code.split("\n")):
                        ln = raw.strip()
                        if not ln or ln.startswith("#"):
                            continue
                        ln = re.sub(r"^(?:\$\()?\s*", "", ln)
                        while re.match(r"^[A-Za-z_][A-Za-z0-9_]*=\S*\s+", ln):
                            ln = re.sub(r"^[A-Za-z_][A-Za-z0-9_]*=\S*\s+", "", ln)
                        if ln.startswith("<") and not ln.startswith("<<") and ">" in ln[:120]:
                            findings.append({
                                "file": rel, "line": line_no + k, "kind": "placeholder-in-command-position",
                                "detail": "命令位是尖括号占位符 —— `<`/`>` 会被当成重定向，"
                                          "`bash -n` 与本门的占位符中和**都会放行**，运行时只新建一个空文件、"
                                          "命令一次没跑。把它移出围栏写成显式的 `Skill`/工具调用步骤",
                            })

                    # B. 续行吞注释（bash -n 判不了：语法合法、语义错）
                    body = code.split("\n")
                    for k in range(len(body) - 1):
                        cur = body[k].rstrip()
                        if not cur.endswith("\\"):
                            continue
                        # ⚠️ 注释行末的 `\` 不是续行（整行都被 `#` 吃掉了）——不排除会误报
                        #    "在注释块里贴示例命令"这种完全正当的写法（实测命中过一处）。
                        if cur.lstrip().startswith("#"):
                            continue
                        nxt = body[k + 1].lstrip()
                        if nxt.startswith("#"):
                            findings.append({
                                "file": rel, "line": line_no + k + 1, "kind": "continuation-comment",
                                "detail": "行尾 `\\` 续行的下一行是注释 —— 续行会把两行并成一条命令，"
                                          "`#` 之后的参数被静默吞掉（语法合法、语义错，bash -n 查不出）",
                            })
    return findings, scanned, waived


def main(argv=None):
    ap = argparse.ArgumentParser(description="flow/命令里 ```bash 围栏的语法有效性")
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-check", action="store_true",
                    help="阳性对照自检：注入必然命中的探针，验证本检查确实生效"
                         "（骨架与探针登记表见 selfcheck.py）")
    args = ap.parse_args(argv)
    if args.self_check:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from selfcheck import run_self_check
        sys.exit(run_self_check(os.path.basename(__file__),
                                json_out=getattr(args, "json", False)))

    root = Path(args.root).resolve()
    try:
        bash = probe_bash()
        findings, scanned, waived = run(root, bash)
    except BashUnavailable as e:
        # ★ 「不适用」必须是一个**自带字段**的结论，不能只靠退出码：
        #   调用方 `verify.py::_run_guard` 先 `json.loads(stdout)` 再看退出码，
        #   stdout 不是合法 JSON 就会被当成"脚本执行失败"。故 --json 下必须照常吐 JSON。
        payload = {
            "applicable": False, "status": "unsupported", "level": "INFO",
            "reason": "bash-unavailable", "na": "N/A(bash-unavailable)",
            "detail": str(e),
            # ⛔ 这三个计数必须是 0/空：本门一个围栏都没验过。
            #    给个非零数或省略它们，读的人（和聚合脚本）会当成"验过且没问题"。
            "scanned_fences": 0, "waived": 0, "errors": 0, "findings": [],
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("[INFO] N/A(bash-unavailable) —— %s；本门 0 个围栏被验证，"
                  "⛔ 这不等于通过" % e)
        sys.stderr.write("N/A(bash-unavailable): %s\n" % e)
        return EXIT_NOT_APPLICABLE

    if args.json:
        # ★ `applicable` 与 N/A 分支成对出现：只在 N/A 时给字段，按字段判的调用方会把
        #   一次**真跑过且没问题**读成「不适用」而整门跳过（假绿）。两条路必须同源。
        print(json.dumps({"applicable": True, "scanned_fences": scanned, "waived": waived,
                          "errors": len(findings), "findings": findings},
                         ensure_ascii=False, indent=2))
    elif not findings:
        print("[OK] flow/命令 bash 围栏语法全部有效（巡检 %d 个围栏%s）"
              % (scanned, "，豁免 %d" % waived if waived else ""))
    else:
        print("[FAIL] %d 个 bash 围栏语法错误（会真的执行失败）：" % len(findings))
        for f in findings:
            print("  · [%s] %s:%d —— %s" % (f.get("kind", "syntax"), f["file"], f["line"], f["detail"]))
        print("  常见成因：注释插进 `\\` 续行中间 / 编辑长行时截断了字符串 / case 缺 esac。")
        print("  豁免：围栏上方加 `<!-- bashsyntax-check: ignore -->`。")

    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
