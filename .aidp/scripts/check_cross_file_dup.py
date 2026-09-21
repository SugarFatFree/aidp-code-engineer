#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_cross_file_dup.py — 跨文件长片段逐字重复（双写漂移守卫，脚手架契约脚本）。

## 为什么需要本脚本

本范式的核心纪律是「**单一信源**」：规则只写一处，别处只留指针。但纪律靠人守就会失效——
一次审计找出 **6 组**跨文件双写（最大一处 **636 字符逐字相同**），而**每一组的两侧都白纸黑字
写着「单一信源在别处、本处不复述（约定 21）」**。写的人真心以为自己没复述。

双写的代价不是"多占几行"，是**漂移**：改了一处、另一处留在旧口径，而两处都声称自己权威。
实际项目中就出现过：某个跳过判据的口径在实现里改了，5 处文档还说老规矩。

既有的 `check_convention_dup.py` 只比对**约定主行整句**，对「改写型复制」和「分片内部互抄」
无能为力（它自己报「38 条主行无一被复制」时，上面那 6 组正躺在仓库里）。

## 判据

把 `AIDP_HOME/{commands,agents,flows,reference,rules}` 与 `docs/init` 下的 `.md` 归一化
（去 markdown 标记 / 折叠空白 / 去行首列表符号）后按句切分，滑窗比对：

  - 同一片段（≥`--error-len`，默认 **150** 字符）出现在 **≥2 个文件** → **ERROR**
  - 同一片段（≥`--warn-len`，默认 **80** 字符）出现在 ≥2 个文件 → **WARN**

**只比跨文件**，同文件内重复不管（那多是模板/示例的正常重复）。

豁免：片段所在行或其上一行有 `<!-- dup-check: ignore -->`；整文件 `ignore-file`。
有意自包含的 bash 块（各分片需独立可执行）应当用它显式豁免——那是设计选择，不是漂移。

## 用法

    python3 AIDP_HOME/scripts/check_cross_file_dup.py [--root <仓库根>] [--json]
                                                    [--error-len 150] [--warn-len 80]

退出码：`0`=无 ERROR 级重复 / `1`=检出 / `2`=用法或读取错误。
"""
import sys as _aidp_sys
from pathlib import Path as _AidpPath
_aidp_scripts = str(_AidpPath(__file__).resolve().parent)
if _aidp_scripts not in _aidp_sys.path:
    _aidp_sys.path.insert(0, _aidp_scripts)
from aidp_runtime import runtime_text
import argparse
import json
import os
import re
import sys

SCAN = [runtime_text('__AIDP_HOME__/commands', __file__), runtime_text('__AIDP_HOME__/agents', __file__), runtime_text('__AIDP_HOME__/flows', __file__),
        runtime_text('__AIDP_HOME__/reference', __file__), runtime_text('__AIDP_HOME__/rules', __file__), "docs/init"]
ATTACH_SKIP = {"README.md"}
# ★ `ignore` 后允许跟说明文字（本脚本的修复建议本就要求写明豁免理由）——
#   若要求 `ignore` 紧跟 `-->`，带理由的豁免会静默失效、检查形同虚设。
IGNORE_LINE = re.compile(r"<!--\s*dup-check:\s*ignore(?!-file)\b[^>]*-->")
IGNORE_FILE = re.compile(r"<!--\s*dup-check:\s*ignore-file\b[^>]*-->")

# 归一化：去掉粗体/行内码/链接标记、列表符号、引用符号，折叠空白
_STRIP = re.compile(r"[*`>#\[\]()|~]|^\s*[-+·]\s*|\s+")
SENT_SPLIT = re.compile(r"[。；;!?\n]+")


def _read(p):
    try:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def _norm(s):
    return _STRIP.sub("", s)


def _files(root):
    for rel in SCAN:
        base = os.path.join(root, rel)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for fn in sorted(filenames):
                if fn.endswith(".md") and fn not in ATTACH_SKIP:
                    yield os.path.join(dirpath, fn)


def run(root, error_len=150, warn_len=80):
    seen = {}          # 归一化片段 → [(相对路径, 原文摘要)]
    scanned = 0
    for path in _files(root):
        text = _read(path)
        if not text or IGNORE_FILE.search(text):
            continue
        scanned += 1
        rel = os.path.relpath(path, root)
        lines = text.split("\n")
        # ★ 豁免作用域 = 从 `<!-- dup-check: ignore -->` 起，到**空行**为止；
        #   若紧随其后就是代码块围栏，则**延伸到该围栏闭合**。
        #   只豁免"下一行"不够：有意自包含的 bash 块通常跨多行，第 2 行起就又被报出来
        #   （实测：豁免加在第 84 行、重复片段落在第 86 行，仍命中）。
        #   ⛔ 围栏必须"穿过去"而不是"截断"：HTML 注释写在 ```bash 围栏**内**是**真 bash 语法错**
        #   （`bash -n` 报 syntax error、整块打死，见 check_flow_bash_syntax.py），所以标注只能写在
        #   围栏**外**；若此处遇围栏即终止豁免，标注就永远盖不住它要豁免的那段代码 —— 两道守卫
        #   会互相逼死（实测：把 5 处标注从围栏内移到围栏外后，本检查立刻转红）。
        in_exempt = False
        in_fence = False
        for i, line in enumerate(lines):
            if IGNORE_LINE.search(line):
                in_exempt = True
                in_fence = False
                continue
            if in_exempt:
                stripped = line.lstrip().lstrip("> ").lstrip()
                if stripped.startswith("```"):
                    in_fence = not in_fence
                    if not in_fence:          # 围栏闭合 → 豁免到此为止
                        in_exempt = False
                    continue
                if not in_fence and not line.strip():
                    in_exempt = False
                continue
            # ★ 除逐句外，**整行也要作为一个片段登记**。只按句切会漏掉一整类真双写：
            #   中文契约文档里一段 600 字符的复制粘贴，往往由 5 个各 120 字符的句子组成，
            #   **每一句都够不到 150 的 ERROR 阈值**，于是整段逐字重复只报几条 WARN 甚至不报。
            #   实测本仓有 4 组真双写落在这个缝里，其中一组是 `--unattended` 的语义定义
            #   **逐字抄在 4 个命令文件里** —— 正是本脚本 docstring 点名要防的形态。
            for frag in list(SENT_SPLIT.split(line)) + [line]:
                n = _norm(frag)
                if len(n) < warn_len:
                    continue
                seen.setdefault(n, [])
                if rel not in [x[0] for x in seen[n]]:
                    seen[n].append((rel, frag.strip()[:70]))

    findings = []
    for n, where in seen.items():
        if len(where) < 2:
            continue
        lvl = "ERROR" if len(n) >= error_len else "WARN"
        findings.append({
            "level": lvl, "length": len(n),
            "files": [w[0] for w in where],
            "excerpt": where[0][1],
        })
    findings.sort(key=lambda f: (-f["length"],))
    errs = [f for f in findings if f["level"] == "ERROR"]
    return {"applicable": scanned > 0, "scanned": scanned,
            "findings": findings, "passed": not errs}


def main():
    ap = argparse.ArgumentParser(description="跨文件长片段逐字重复（双写漂移守卫）")
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--error-len", type=int, default=150)
    ap.add_argument("--warn-len", type=int, default=80)
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
        res = run(args.root, args.error_len, args.warn_len)
    except Exception as e:
        if args.json:
            print(json.dumps({"error": str(e)}, ensure_ascii=False))
        else:
            print(f"[ERROR] 检查执行失败：{e}")
        return 2

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res["passed"] else 1

    if not res["applicable"]:
        print("[SKIP] 无可扫描的 .md")
        return 0
    errs = [f for f in res["findings"] if f["level"] == "ERROR"]
    warns = [f for f in res["findings"] if f["level"] == "WARN"]
    if not errs:
        print(f"[OK] 无跨文件长片段双写（巡检 {res['scanned']} 份 .md"
              f"{f"，{len(warns)} 处 WARN 级短重复" if warns else ""}）。")
        for f in warns[:5]:
            print(f"  · [WARN] {f['length']} 字符 × {len(f['files'])} 文件：{f['excerpt']}…")
        return 0

    print(f"[FAIL] 检出 {len(errs)} 处跨文件双写（≥{args.error_len} 字符逐字相同）：")
    for f in errs:
        print(f"  · {f['length']} 字符 × {len(f['files'])} 文件：{f['excerpt']}…")
        print(f"      落点：{'; '.join(f['files'])}")
    print("  修复：留一处权威正文，其余改为指针引用（「详见 X」）。"
          "确属有意自包含（如各分片需独立可执行的 bash 块）→ 加 `<!-- dup-check: ignore -->`。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
