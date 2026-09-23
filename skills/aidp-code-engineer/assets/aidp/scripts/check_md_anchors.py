#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_md_anchors.py — 站内锚点链接有效性检查（脚手架契约脚本）。

## 为什么需要本脚本

AIDP 的命令主体被反复「瘦身」：`Step N` 的正文外置到 `AIDP_HOME/flows/<命令>/*.md` 分片，
命令里只留一张骨架索引表。**外置时最容易漏改的就是表格里的站内锚点** —— 目标标题已经
搬走了，`[Step 2.4.7](#step-247...)` 还留在原地，点进去哪儿也不去。

这类死链**不会**被任何现有检查发现：文件都存在（不是断链）、文本也读得通（不是错字），
只有真去点才知道。一次 `/version` 瘦身就留下了 9 处死锚点，横跨顶部 flag 表与底部速查表。

## 判定口径

1. 逐文件提取 ATX 标题（`#`~`######`），**跳过围栏代码块内的行** —— bash 注释 `# 0. 前置…`
   长得和一级标题一模一样，不跳会把它们当标题、反而漏报真死链；
2. 按 GitHub slugify 规则算锚点：去 markdown 行内格式（`` ` ``/`**`/`[]()`）→ 转小写 →
   删掉非「字母数字下划线/空格/连字符」的字符（CJK 属字母、保留；`★：（）+/` 等删除）→
   空格逐个转连字符（**不合并连续空格**，故 ` + ` 会产生 `--`）；重复标题追加 `-1`/`-2`；
3. 收集同文件内的站内链接 `](#anchor)`，锚点不在该文件 slug 集合里 = 死锚点。

4. 跨文件锚点（`](other.md#anchor)`）：按引用者所在目录解析目标文件，解析得到就用目标文件的 slug 集合判；解析不到则不报（交路径类检查，避免双写同一结论）。

## 豁免（显式标记，不做隐式特例）

文档里有一类**合法的"假链接"**：正文在**教人怎么给另一个文件写锚点**，示例锚点自然不指向
本文件的标题（如 `release-2.md` 讲 `版本更新日志.md` 的版本概览表该写 `[V1.2.0](#v120)`）。
这类必须豁免，但**只认写在文件里的显式标记**，绝不在脚本里硬编码文件名特例：

    <!-- anchor-check: ignore-file 理由 -->      整份文件跳过
    <!-- anchor-check: ignore-begin 理由 -->     区块开始
    ...
    <!-- anchor-check: ignore-end -->            区块结束

## 用法

    python3 AIDP_HOME/scripts/check_md_anchors.py                 # 默认扫 AIDP 契约面
    python3 AIDP_HOME/scripts/check_md_anchors.py --json
    python3 AIDP_HOME/scripts/check_md_anchors.py --root . --path AIDP_HOME/commands

退出码：0 = 无死锚点；1 = 检出死锚点；2 = 用法/读取错误。
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

DEFAULT_PATHS = [
    runtime_text('__AIDP_HOME__/commands', __file__),
    runtime_text('__AIDP_HOME__/agents', __file__),
    runtime_text('__AIDP_HOME__/flows', __file__),
    runtime_text('__AIDP_HOME__/reference', __file__),
    runtime_text('__AIDP_HOME__/rules', __file__),
    "docs/init",
]

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
# ★ 围栏判定必须按 CommonMark，不能用「见 ``` 就翻转」的朴素 toggle：
#   收尾围栏的要求有两条 —— ① 反引号/波浪线**不少于**开启那行 ② **不带 info string**。
#   带 info 的 ```bash / ```markdown 只是块内的普通文本。朴素 toggle 把它们也当收尾，
#   于是外层 ````markdown 模板里的内层 ```bash 一出现，本脚本就认为块已结束，
#   把随后那些**渲染器眼里在块内、根本不存在**的标题收进 slug 集合 —— 目录锚点指向它们时
#   本门判"有效"，而实际渲染出来是死链。这正是「门是绿的 ≠ 目标达成」。
FENCE_OPEN_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})\s*(\S.*)?$")
# 站内锚点：](#xxx)，排除跨文件的 ](other.md#xxx)
INPAGE_LINK_RE = re.compile(r"\]\(#([^)\s]+)\)")
# ★ 跨文件锚点 `](other.md#anchor)`：原先整类移交给「路径断链检查」，但**接收方并不存在**
#   （`AIDP_HOME/scripts/` 下没有任何脚本做跨文件锚点校验）—— 于是这一整类死锚点全仓无人管。
#   现就地补上：路径按引用者所在目录解析，目标文件在 → 用它的 slug 集合判锚点。
#   目标文件不在 → 交给别的路径检查，本门不报（避免与路径类检查双写同一结论）。
CROSSFILE_LINK_RE = re.compile(r"\]\(([^)#\s]+\.md)#([^)\s]+)\)")
IGNORE_FILE_RE = re.compile(r"<!--\s*anchor-check:\s*ignore-file")
IGNORE_BEGIN_RE = re.compile(r"<!--\s*anchor-check:\s*ignore-begin")
IGNORE_END_RE = re.compile(r"<!--\s*anchor-check:\s*ignore-end")


def slugify(text: str) -> str:
    """GitHub 风格锚点。CJK 属 `\\w`，予以保留。"""
    s = text.strip()
    s = re.sub(r"`([^`]*)`", r"\1", s)          # 去行内代码
    s = re.sub(r"\*\*([^*]*)\*\*", r"\1", s)    # 去粗体
    s = re.sub(r"\*([^*]*)\*", r"\1", s)        # 去斜体
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)  # 链接只留文字
    s = s.lower()
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    return s.replace(" ", "-")


def parse_md(text: str):
    """返回 (slug 集合, [(行号, 锚点)])，标题提取跳过围栏代码块。"""
    slugs, seen, links = set(), {}, []
    in_fence = in_ignore = False
    fence_marks = ""
    for i, line in enumerate(text.split("\n"), 1):
        m = FENCE_OPEN_RE.match(line)
        if m:
            marks, info = m.group(1), (m.group(2) or "").strip()
            if not in_fence:
                in_fence, fence_marks = True, marks
            elif not info and marks[0] == fence_marks[0] and len(marks) >= len(fence_marks):
                in_fence, fence_marks = False, ""
            continue
        if in_fence:
            continue
        # ★ 豁免区只屏蔽【收集链接】，标题照常收 —— 区块里的标题仍是本文件的真实锚点目标
        if IGNORE_BEGIN_RE.search(line):
            in_ignore = True
        elif IGNORE_END_RE.search(line):
            in_ignore = False
        m = HEADING_RE.match(line)
        if m:
            base = slugify(m.group(2))
            if not base:
                continue
            n = seen.get(base, 0)
            slugs.add(base if n == 0 else f"{base}-{n}")
            seen[base] = n + 1
        if in_ignore:
            continue
        for a in INPAGE_LINK_RE.findall(line):
            links.append((i, a))
    return slugs, links


def iter_md(root: str, paths):
    for rel in paths:
        p = os.path.join(root, rel)
        if os.path.isfile(p) and p.endswith(".md"):
            yield p
        elif os.path.isdir(p):
            for dirpath, dirnames, filenames in os.walk(p):
                dirnames[:] = [d for d in dirnames if d not in ("__pycache__", ".git")]
                for fn in sorted(filenames):
                    if fn.endswith(".md"):
                        yield os.path.join(dirpath, fn)


def run(root: str, paths):
    broken, scanned = [], 0
    for path in sorted(set(iter_md(root, paths))):
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError as e:
            broken.append({"file": os.path.relpath(path, root), "line": 0,
                           "anchor": "", "detail": f"读取失败：{e}"})
            continue
        if IGNORE_FILE_RE.search(text):
            continue
        scanned += 1
        slugs, links = parse_md(text)
        # 跨文件锚点：解析得到目标文件才判，判不到就交给路径类检查
        _skip = False
        for i, ln in enumerate(text.split("\n"), 1):
            if IGNORE_BEGIN_RE.search(ln):
                _skip = True
            elif IGNORE_END_RE.search(ln):
                _skip = False
            if _skip:
                continue
            for tgt, anchor in CROSSFILE_LINK_RE.findall(ln):
                cand = os.path.normpath(os.path.join(os.path.dirname(path), tgt))
                if not os.path.isfile(cand):
                    continue
                try:
                    tslugs, _ = parse_md(open(cand, encoding="utf-8").read())
                except OSError:
                    continue
                if anchor not in tslugs:
                    broken.append({
                        "file": os.path.relpath(path, root), "line": i, "anchor": f"{tgt}#{anchor}",
                        "detail": f"目标文件 {tgt} 内无此标题（跨文件锚点）",
                    })
        for line, anchor in links:
            if anchor not in slugs:
                broken.append({
                    "file": os.path.relpath(path, root),
                    "line": line,
                    "anchor": anchor,
                    "detail": "本文件内无此标题（正文可能已外置到 flows 分片 / 标题被改写）",
                })
    return {"scanned": scanned, "broken": broken}


def main():
    ap = argparse.ArgumentParser(description="站内锚点链接有效性检查（死锚点 = 点了不跳转）")
    ap.add_argument("--root", default=".", help="仓库根目录（默认当前目录）")
    ap.add_argument("--path", action="append", default=None,
                    help="只扫指定相对路径（可重复）；缺省扫 AIDP 契约面")
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
        res = run(args.root, args.path or DEFAULT_PATHS)
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False) if args.json
              else f"[ERROR] 检查执行失败：{e}")
        return 2

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    elif not res["broken"]:
        print(f"[OK] 站内锚点全部有效（巡检 {res['scanned']} 份 .md）")
    else:
        print(f"[FAIL] 检出 {len(res['broken'])} 处死锚点（巡检 {res['scanned']} 份 .md）：")
        for b in res["broken"]:
            print(f"  · {b['file']}:{b['line']}  #{b['anchor']}")
        print("  修复：正文已外置的改为指向分片文件的相对链接（如 "
              "`[Step 2.4.7](../flows/version/planning-7.md)`）；标题改过的同步锚点。")
    return 1 if res["broken"] else 0


if __name__ == "__main__":
    sys.exit(main())
