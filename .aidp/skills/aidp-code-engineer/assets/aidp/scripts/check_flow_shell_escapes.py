#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""flow / 命令的 shell 围栏里，单引号字符串内不得出现 `\\n` 这类双重转义。

## 为什么需要本脚本

在 Markdown 里写 bash，作者常出于"这是文档、反斜杠要转义一次"的直觉写成
`printf '%s\\n' "${ARR[@]}"`。但 **shell 单引号内不做任何转义**：`\\n` 就是
反斜杠加字母 n 两个字符，`printf` 把它原样打出来——整个数组被拼成**一行**、
且带着字面 `\n`。紧跟其后的 `grep -qx "$x"`（整行精确匹配）于是**永远匹配不上**。

实测（本仓真实缺陷，autopilot 主干路径）：
    printf '%s\\n' 001 002   → `001\\n002\\n`（单行）  → grep -qx 001 不匹配
    printf '%s\n'  001 002   → 两行 001 / 002         → grep -qx 001 匹配

后果是**静默的**：语法合法、脚本 exit 0、既有的变量供给门/旗标门/锚点门全绿，
只有真跑起来才发现"未关闭 Sprint 集合恒等于全集、部署出口永不可达"。
这类错误一旦写下就没有任何机器会指出来——本门就是补这个盲区。

## 判据（宁可少报不可误报）

只在 ```bash / ```sh / ```shell 代码块内，检查**单引号**字符串的内容：
含 `\\n` / `\\t` / `\\r` → ERROR。

⛔ 双引号字符串不查：`"...\\n..."` 在 shell 里确实表示字面反斜杠+n，
   而 jq / sed / awk 的程序文本里那常常是**正确**的写法（如 jq 的 `"\\n"`）。
⛔ 非代码块正文不查：散文里讲"要写 `\\n`"是合法的说明。
豁免：行尾加 `# shell-escape-ignore` 或行内 `<!-- shell-escape-ignore -->`。
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

FENCE_RE = re.compile(r"^\s*(?:>\s*)?```+\s*(bash|sh|shell)\b", re.I)
FENCE_END_RE = re.compile(r"^\s*(?:>\s*)?```+\s*$")
SINGLE_QUOTED_RE = re.compile(r"'([^']*)'")
BAD_RE = re.compile(r"\\\\[ntr]")
# ★ 第二类：bash 围栏里残留的**文档占位符**（`{V}` / `{BUILD}` / `{version}` / `{NNN}` 等）。
#   花括号在 bash 里不展开，会被当成字面目录名/参数值——脚本照样"成功"运行，只是操作在
#   一个名为 `{V}` 的不存在路径上：钢门恒 FAIL、streak 记在真实版本头上、3 tick 后误冻。
#   `check_flow_var_refs` 只查 `$VAR`，对这类一无所知。⛔ 排除 `${...}`（那是正常变量展开）
#   与 jq/awk 的程序体（`'...'` 单引号内，由上面那条规则另行管辖）。
# ⛔ 只查 `{V}` / `{BUILD}` 这两个——它们在 flows 里**确有对应 shell 变量**
#   （`$TARGET_VERSION` / `$BUILD`），写成花括号就是把变量写漏了。
#   `{version}` / `{NNN}` / `{user}` 是全仓通行的**文档模板路径**写法（执行体按上下文替换），
#   报它们只会得到一个恒红的门 —— 那比没有门更糟。
PLACEHOLDER_RE = re.compile(r"(?<!\$)\{(V|BUILD)\}")
PLACEHOLDER_DIRS = ("flows",)   # agents/commands 里多是给人读的命令模板，不适用
IGNORE_RE = re.compile(r"shell-escape-ignore")
SCAN_DIRS = ["flows", "commands", "agents", "reference", "rules"]


def scan(root="."):
    root = os.path.abspath(root)
    findings, files, blocks = [], 0, 0
    for sub in SCAN_DIRS:
        base = os.path.join(root, runtime_relpath("", __file__), sub)
        if not os.path.isdir(base):
            continue
        for cur, dirs, names in os.walk(base):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for name in sorted(names):
                if not name.endswith(".md"):
                    continue
                path = os.path.join(cur, name)
                rel = os.path.relpath(path, root)
                try:
                    with open(path, encoding="utf-8", errors="replace") as f:
                        lines = f.read().splitlines()
                except OSError:
                    continue
                files += 1
                in_block = False
                for i, line in enumerate(lines, 1):
                    if not in_block:
                        if FENCE_RE.match(line):
                            in_block = True
                            blocks += 1
                        continue
                    if FENCE_END_RE.match(line):
                        in_block = False
                        continue
                    if IGNORE_RE.search(line):
                        continue
                    body = re.sub(r"^\s*>\s?", "", line)     # 剥引用块前缀
                    # 注释行不查：`# 台账在 versions.{V} 下` 这类是在**讲路径结构**，不是可执行代码
                    _in_flow = (rel.replace("\\", "/").startswith(runtime_text('__AIDP_HOME__/flows/', __file__))
                                and not body.lstrip().startswith("#"))
                    for pm in (PLACEHOLDER_RE.finditer(re.sub(r"'[^']*'", "", body))
                               if _in_flow else []):
                        findings.append({
                            "level": "ERROR", "file": rel, "line": i,
                            "snippet": body.strip()[:120],
                            "kind": "placeholder",
                            "detail": (f"bash 围栏里残留文档占位符 `{{{pm.group(1)}}}`：花括号不展开，"
                                       "会被当成字面路径/参数——用 `$TARGET_VERSION` / `$BUILD` 等真实变量"),
                        })
                        break
                    for m in SINGLE_QUOTED_RE.finditer(body):
                        if BAD_RE.search(m.group(1)):
                            findings.append({
                                "level": "ERROR", "file": rel, "line": i,
                                "snippet": body.strip()[:120],
                                "detail": ("shell 单引号内不做转义：`\\\\n` 是字面两个字符，"
                                           "不是换行——数组会被拼成一行、后续 grep -qx 恒不匹配"),
                            })
                            break
    return {"applicable": files > 0, "findings": findings, "files": files, "blocks": blocks}


def main():
    ap = argparse.ArgumentParser(description="flow/命令 shell 围栏内的双重转义检查")
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-check", action="store_true",
                    help="阳性对照自检：注入必然命中的探针，验证本检查确实生效"
                         "（骨架与探针登记表见 selfcheck.py）")
    args = ap.parse_args()
    if args.self_check:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from selfcheck import run_self_check
        sys.exit(run_self_check(os.path.basename(__file__),
                                json_out=getattr(args, "json", False)))
    res = scan(args.root)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    elif not res["applicable"]:
        print("[SKIP] 无可扫描的 .aidp 文档目录")
    elif res["findings"]:
        sys.stderr.write(f"❌ shell 围栏内双重转义 {len(res['findings'])} 处"
                         f"（巡检 {res['files']} 份 .md、{res['blocks']} 个代码块）：\n")
        for f in res["findings"]:
            sys.stderr.write(f"   · {f['file']}:{f['line']}  {f['snippet']}\n")
        sys.stderr.write("   → 单引号内写 `\\n` 即可；确需字面反斜杠请加 `# shell-escape-ignore`\n")
    else:
        print(f"[OK] shell 围栏内无双重转义（巡检 {res['files']} 份 .md，{res['blocks']} 个代码块）")
    return 1 if res["findings"] else 0


if __name__ == "__main__":
    sys.exit(main())
