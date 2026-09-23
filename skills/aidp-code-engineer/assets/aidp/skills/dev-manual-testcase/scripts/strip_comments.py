#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""按块剥离注释,输出 `路径:行号:正文` —— 零残留断言实跑的默认取材方式

**为什么需要它(下游实测,该根因跨 4 个版本复发 5 次)**:零残留断言(`断言(反向):不存在文本"X"`)
的初稿假红,绝大多数是**命中了本 Sprint 自己写的注释**——防回退注释、变更留痕注释、
给后续维护者的告诫。而旧口径字样**恰恰最常出现在变更留痕注释里**,所以这不是偶发,是模式。

早期用的是**行级 grep 前置**(`grep -vE '^([^:]*:)?[0-9]+:[[:space:]]*(//|\*|/\*|<!--)'`),
它只认**行首注释标记**,有三个确定的漏面:

  (a) `/* … */` 块里**不以 `*` 开头**的中间行;
  (b) `<!-- … -->` **跨行块**的中间行(Vue / HTML 模板高发);
  (c) **行尾注释**(`doSomething(); // 旧口径XXX`)。

本脚本按**块**剥离,三个漏面一次性关掉:注释内容被替换成等长空白、**行号与文件名照常输出**,
所以下游 grep 拿到的位置信息与 `grep -rn` 完全一致,「反向复现片段」照旧记得下来。

典型用法(两个方向):

    # 方向一·现状实跑(期望 0 命中)
    python3 strip_comments.py 'src/**/*.ts' 'src/**/*.vue' | grep -E '批量导出'

    # 断言目标本身就是注释内容时(失效 REQ 编号的作废标注),反过来只扫注释
    python3 strip_comments.py --only-comments 'src/**/*.java' | grep -E 'REQ-0142'

⚠️ **这不是通用词法分析器,是给"找残留文本"用的保守剥离器。** 判据只有一条:
   **宁可少剥一点(留下 → 假红 → 人看一眼就排除),绝不多剥(剥掉 → 假绿 → 缺陷溜过去)。**
   由此派生几条刻意的保守取舍(改之前先读):
   - **字符串字面量里的 `//` 不当注释**(`const u = "https://api/x"` 整行保留)。这是**必须**的:
     早期行级方案正因为没有字符串意识,`://` 会让整行被吞掉,方向是假绿。
     两条配套护栏:
     ① **反引号模板串跨行保留状态** —— 否则多行模板串第 2 行的裸 URL 会被当行注释整段剥掉;
     ② **`://` 不作注释起点** —— 覆盖不带引号的 URL(CSS 的 `url(https://…)`)。
   - **`#` 默认不当注释**:它在 Markdown 里是**标题**、在 CSS 里是 **id 选择器**,两者都是
     **会被用户看见的内容**,剥掉就是假绿。Shell / Python / YAML 需要时用 `--hash`
     ——它**只对 `HASH_FAMILY` 扩展名生效**,`.md` / `.css` 不受影响(实现兜住,不靠人记)。
   - **Markdown 默认只剥 `<!-- -->`**:`*` 开头在 md 里是**列表项**、`**文本**` 是整行加粗,
     都是正文;早期行级方案的 `\*` 分支正是在这里静默吞掉了它们。
     **且 ``` 代码围栏内一律不剥** —— 围栏里的 `<!--` 是被展示的字面量(本 SKILL 的方法论
     文档里就拿它举例),把它当注释会开出一个跨越几十行的块、把正文整段吞掉。
   - **闭合串在整份文件里找不到时,`/*` 与 `<!--` 都不当注释开头**(见 `has_closer`)。
     未闭合的开头几乎总是「文档在引用这个字面量」,照开会让其后**整份文件**静默消失。
   - **`.vue` 按段处理**:`<script>` / `<style>` 走 C 家族(`//` 与 `/* */`),
     `<template>` 只认 `<!-- -->`。不分段的话 Vue 项目里最常见的 `<script>` 行注释
     一条都剥不掉(纯假红,而 `.vue` 恰恰是守护面里最典型的文件类型)。
   - **未识别扩展名一律不剥**(`.txt` / `.csv` / `.json` / `.log` …),并在 stderr 出一行提示。
     ⚠️ 反过来做(未识别就按 C 家族剥)是**假绿**:`.txt` 里的 `plain // 旧口径XX` 会整段消失,
     而「全站不得出现」类断言的守护面写的正是 `**`、天然覆盖这些文件。
   - **Python 的三引号文档串不剥**:它既可能是文档、也可能是**被展示的模板字符串**,
     分不清就不剥(保守侧)。

用法:
    python3 strip_comments.py <文件或 glob> [<文件或 glob> ...] [--only-comments] [--hash] [--json]

退出码:
    0 = 正常输出(**包括"glob 一个文件都没匹配到"**——那是守护面写窄了,不是错误;
        ⚠️ 但它会在 stderr 打一行告警、`--json` 出 `skipped: true`,别把 0 命中当成"没有残留")
    1 = 未使用(本脚本不做判定,只做取材;判定交给下游 grep)
    2 = 入参或环境错(没给任何路径 / **不含通配符的字面路径不存在** / 全部路径都读不出来)
        ⚠️ 字面路径写错必须是 2、⛔ 不能降级成「0 命中 + 告警」——手滑写错一个路径就
        静默得出「没有残留」,正是全仓退出码约定第 2 条要消灭的形态。

仅依赖 Python 3.8+ 标准库。
"""

import argparse
import glob as globmod
import json
import os
import sys
from pathlib import Path
from typing import List, Tuple

# 按扩展名选注释语法。
# ⚠️⚠️ **未列出的扩展名一律「不剥任何注释」**,⛔ 不要改回「走 C 家族 + `<!--`」。
#    原注释写的是「多认一种注释形态 = 可能少剥(假红侧),不会多剥」——**这句话是反的**:
#    多认一种注释形态 = **剥得更多** = 假绿。实测:`.txt` 里的
#    `plain // 旧口径XX` 被当行注释整段剥掉,而 `.txt` 完全可能落在守护面里
#    (「全站不得出现」类断言的守护面写的正是 `**`,`.txt`/`.csv`/`.json`/`.log` 全在内)。
#    现在未识别扩展名走 `NO_COMMENT`(原样保留 + stderr 提示),方向是假红、可见、可排除。
C_FAMILY = {".java", ".kt", ".kts", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
            ".go", ".c", ".h", ".cpp", ".hpp", ".cs", ".scss", ".sass", ".less",
            ".styl", ".css", ".swift", ".rs", ".php", ".dart", ".scala",
            ".groovy", ".gradle", ".proto"}
MARKUP = {".html", ".htm", ".xml", ".vue", ".svg", ".md", ".markdown"}
HASH_FAMILY = {".sh", ".bash", ".zsh", ".py", ".yml", ".yaml", ".toml", ".ini",
               ".conf", ".properties", ".env", ".dockerfile", ".rb"}
SQL_FAMILY = {".sql"}
KNOWN_EXT = C_FAMILY | MARKUP | HASH_FAMILY | SQL_FAMILY
# `.vue` 三段注释语法各不相同,单独按段处理(见 strip_line_family 的 vue 分支)。
VUE_EXT = {".vue"}
# 反引号 = 多行模板串的语言。⚠️ 只有这些扩展名才允许把反引号状态**跨行**保留,
#    ⛔ 别把 `.md` 加进来(md 的 ``` 围栏会让跨行奇偶性彻底失真,详见 tpl_lang 注释)。
TEMPLATE_LITERAL_EXT = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}


def _blank(n: int) -> str:
    return " " * n


def strip_line_family(text: str, ext: str, hash_on: bool) -> Tuple[str, str]:
    """返回 (剥掉注释后的正文, 仅注释的文本);两者行数与原文完全一致。

    ⚠️ 行数必须守恒——下游要靠行号定位「反向复现片段」,少一行就对不上了。
    """
    keep: List[str] = []
    only: List[str] = []
    in_block = False          # /* ... */
    in_markup = False         # <!-- ... -->
    block_end, markup_end = "*/", "-->"
    is_vue = ext in VUE_EXT
    # ⚠️ 未识别扩展名 = 一律不剥(见 KNOWN_EXT 上方注释)。
    c_like = ext in C_FAMILY
    markup_like = ext in MARKUP
    # ⚠️ `.md` 走 markup:只剥 `<!-- -->`。⛔ 不要给它加 `//` —— md 正文里 `//` 是普通字符;
    #    也不要加 `*` 开头那一支 —— 那是列表项 / 整行加粗,是正文。
    # ⚠️ `--hash` **只对 HASH_FAMILY 生效**。原写法 `hash_on and (ext in HASH_FAMILY or hash_on)`
    #    恒等于 `hash_on`,即一旦加了 `--hash`,`.md` 的标题行 `# 标题` 与 `.css` 的 id 选择器
    #    `#foo{...}` 会**一起被剥掉** —— 那是会被用户看见的内容,剥掉就是假绿。
    #    docstring 里那句「守护面含 .md / .css 时不要开」是靠人记,现在由实现兜住。
    hash_like = hash_on and ext in HASH_FAMILY
    sql_like = ext in SQL_FAMILY
    # `.vue` 分段状态:template(默认) / script / style。三段注释语法不同——
    # `<script>`/`<style>` 走 C 家族(`//` 与 `/* */`),`<template>` 只认 `<!-- -->`。
    # 不分段的后果是 `.vue` 里最常见的 `<script>` 行注释一条都剥不掉(纯假红,而 `.vue`
    # 恰恰是守护面里最典型的文件类型)。
    vue_sec = "template"
    tpl_open = False          # 反引号模板串是否跨到了下一行
    # ⚠️⚠️ **反引号跨行只对「反引号确实是模板串」的语言开**(TS/JS 及 `.vue` 的 script 段)。
    #    ⛔ 绝不能对 Markdown 开:md 里 ``` 围栏与行内代码段让反引号奇偶性跨行毫无意义,
    #    实测对 `.md` 开启后,一行 ``` 把状态带到下一行,
    #    使原本被行内代码段保护的 `<!--` 跑到代码段外、开出一个**永不闭合的注释块**,
    #    本 SKILL 自家 test-design-methodology.md 从第 382 行起 **28 行正文被整段吞掉**(假绿)。
    tpl_lang = ext in TEMPLATE_LITERAL_EXT or is_vue
    # 供「未闭合的块注释不开」用的全局位置(见 has_closer)
    src_lines = text.split("\n")
    line_off, _acc = [], 0
    for _l in src_lines:
        line_off.append(_acc)
        _acc += len(_l) + 1

    def has_closer(closer: str, li: int, col: int) -> bool:
        """从 (行 li, 列 col) 起,整份文本里还找不找得到闭合串。

        ⚠️ 找不到 = **这个开头很可能不是注释**(文档里引用 `<!--` 字面量、
           正则里写 `/*`…),此时按「不剥」处理。方向是假红、可见;
           反过来「照开不误」会让开头之后的**整份文件**静默消失,是最坏的假绿。
        """
        return text.find(closer, line_off[li] + col) != -1

    is_md = ext in (".md", ".markdown")
    in_fence = False

    for li, raw in enumerate(src_lines):
        # ⚠️ Markdown 代码围栏内**一律不剥**:围栏里的 `<!--` 是被展示的**示例字面量**,
        #    不是注释(本 SKILL 的方法论文档里就写着 `<!--` 作例子)。围栏内容天然是正文,
        #    剥掉即假绿;而围栏是 md 里唯一能可靠识别的「这是要给人看的原文」边界。
        if is_md and raw.lstrip().startswith("```"):
            in_fence = not in_fence
            keep.append(raw)
            only.append(" " * len(raw))
            continue
        if is_md and in_fence:
            keep.append(raw)
            only.append(" " * len(raw))
            continue
        if is_vue and not in_block and not in_markup:
            low = raw.lower()
            if "<script" in low:
                vue_sec = "script"
            elif "<style" in low:
                vue_sec = "style"
            elif "</script" in low or "</style" in low:
                vue_sec = "template"
            c_like = vue_sec in ("script", "style")
            markup_like = vue_sec == "template"
        out = list(raw)
        com = [" "] * len(raw)
        i = 0
        # ⚠️ 只有反引号模板串跨行保留状态。单/双引号在行尾未闭合,绝大多数是散文里的
        #    撇号(`don't`),跨行保留会把后面整片正文误当字符串;而反引号在 JS/TS 里
        #    **就是多行模板串**,不跨行保留就会把模板串第 2 行的 `https://…` 当成行注释
        #    整段剥掉 —— 那正是 docstring 声称已经解决、实测却仍存在的假绿。
        quote = "`" if tpl_open else ""
        n = len(raw)
        while i < n:
            ch = raw[i]
            if in_block:
                com[i] = ch
                out[i] = " "
                if raw.startswith(block_end, i):
                    com[i + 1] = raw[i + 1]
                    out[i + 1] = " "
                    i += 2
                    in_block = False
                    continue
                i += 1
                continue
            if in_markup:
                com[i] = ch
                out[i] = " "
                if raw.startswith(markup_end, i):
                    for k in range(i, min(i + 3, n)):
                        com[k] = raw[k]
                        out[k] = " "
                    i += 3
                    in_markup = False
                    continue
                i += 1
                continue
            if quote:
                # ⚠️ 字符串里什么都不算注释(`"https://api/x"` 必须整行留下)
                if ch == "\\":
                    i += 2
                    continue
                if ch == quote:
                    quote = ""
                i += 1
                continue
            if ch in "\"'`":
                quote = ch
                i += 1
                continue
            if c_like and raw.startswith("//", i):
                # ⚠️ `://` 不算注释起点 —— 它是 URL 的 scheme 分隔符。
                #    没有这条护栏时,CSS 的 `background:url(https://x/旧口径)`(不带引号)
                #    与模板串续行里的裸 URL 都会被整段剥掉 = 假绿。
                #    代价是 `default://x` 这种紧贴写法漏剥一次(假红侧,可接受)。
                if i > 0 and raw[i - 1] == ":":
                    i += 2
                    continue
                com[i:] = list(raw[i:])
                for k in range(i, n):
                    out[k] = " "
                break
            if c_like and raw.startswith("/*", i):
                if not has_closer(block_end, li, i + 2):
                    i += 2          # 永不闭合 → 不是注释,原样保留(见 has_closer)
                    continue
                in_block = True
                com[i] = ch
                com[i + 1] = raw[i + 1] if i + 1 < n else " "
                out[i] = " "
                if i + 1 < n:
                    out[i + 1] = " "
                i += 2
                continue
            # ⚠️ **Markdown 里只认「行首 `<!--`」**(前面可有空白),⛔ 行中的一律不当注释。
            #    根因:md 的行内代码段靠反引号配对,而文档里经常出现
            #    ``` 这种**奇数个反引号**的字面量(讲代码围栏时必然要写),它会让本行后续的
            #    反引号配对**整体错位**,于是一个被反引号保护着的 `<!--` 跑到保护之外、
            #    开出一个跨行注释块 —— 实测把 test-design-methodology.md 的 435~437 行
            #    (一张表的三行正文)整段吞掉,方向是**假绿**。
            #    判据依据:全仓 182 份 md 里 `<!--` 出现 21 次,**只有 2 次在行首**,
            #    而那 2 次正是唯一真的注释块;其余 19 次全是文档在引用这个字面量。
            #    行首这条规则边界清晰、不需要任何护栏,符合「新判据宁可窄」。
            if (markup_like and raw.startswith("<!--", i)
                    and not (is_md and raw[:i].strip() != "")):
                if not has_closer(markup_end, li, i + 4):
                    i += 4          # 永不闭合 → 不是注释,原样保留(见 has_closer)
                    continue
                in_markup = True
                for k in range(i, min(i + 4, n)):
                    com[k] = raw[k]
                    out[k] = " "
                i += 4
                continue
            if sql_like and raw.startswith("--", i):
                com[i:] = list(raw[i:])
                for k in range(i, n):
                    out[k] = " "
                break
            if hash_like and ch == "#":
                com[i:] = list(raw[i:])
                for k in range(i, n):
                    out[k] = " "
                break
            i += 1
        # 行尾仍停在反引号里 → 模板串跨到下一行,下一行开头继续按字符串处理。
        # ⚠️ 只对 TEMPLATE_LITERAL_EXT 生效,见 tpl_lang 上方注释。
        tpl_open = tpl_lang and (quote == "`")
        keep.append("".join(out))
        only.append("".join(com))
    return "\n".join(keep), "\n".join(only)


GLOB_META = set("*?[")


def expand(patterns: List[str]) -> Tuple[List[Path], List[str]]:
    """返回 (文件列表, 写错了的字面路径列表)。

    ⚠️ **不含通配符的字面路径不存在 = 入参错(exit 2),⛔ 不是「0 命中」**。
       全仓退出码约定第 2 条针对的正是这一幕:手滑写错一个路径,脚本照常 exit 0,
       调用方读到 0 命中就以为「没有残留」。glob 写窄了(有通配符但 0 命中)
       仍按 exit 0 + 告警处理,那是另一回事。
    """
    out: List[Path] = []
    missing: List[str] = []
    for pat in patterns:
        p = Path(pat)
        if p.is_dir():
            out.extend(sorted(x for x in p.rglob("*") if x.is_file()))
        elif p.is_file():
            out.append(p)
        elif not (set(pat) & GLOB_META):
            missing.append(pat)
        else:
            out.extend(sorted(Path(x) for x in globmod.glob(pat, recursive=True)
                              if os.path.isfile(x)))
    # 去重保序
    seen, uniq = set(), []
    for f in out:
        s = str(f)
        if s not in seen:
            seen.add(s)
            uniq.append(f)
    return uniq, missing


def main() -> int:
    ap = argparse.ArgumentParser(
        description="按块剥离注释后输出 `路径:行号:正文`,供零残留断言实跑取材")
    ap.add_argument("paths", nargs="*", help="文件 / 目录 / glob(可多个)")
    ap.add_argument("--only-comments", action="store_true",
                    help="反过来:只输出注释内容(断言目标本身就是注释时用)")
    ap.add_argument("--hash", action="store_true",
                    help="把 `#` 也当行注释(Shell/Python/YAML);⛔ 守护面含 .md / .css 时不要开")
    ap.add_argument("--json", action="store_true", help="输出 JSON(供 Agent 解析)")
    args = ap.parse_args()

    if not args.paths:
        print("未给出任何路径", file=sys.stderr)
        return 2
    files, missing = expand(args.paths)
    if missing:
        # 字面路径写错 = 入参错。⛔ 不得降级成「0 命中 + 告警」——那正是假绿的入口。
        print("路径不存在(且不含通配符,按入参错处理):%s" % " ".join(missing),
              file=sys.stderr)
        return 2
    if not files:
        # ⚠️ glob 一个文件都没匹配到不是错误(守护面写窄了),但必须出声:
        #    0 命中在本场景里恰恰与"通过"长得一模一样。
        print("⚠️ 没有匹配到任何文件:%s —— 0 命中不等于没有残留,请先确认守护面写对了"
              % " ".join(args.paths), file=sys.stderr)
        if args.json:
            print(json.dumps({"skipped": True, "files": 0, "lines": 0,
                              "read_errors": 0, "unknown_ext": [], "rows": []},
                             ensure_ascii=False))
        return 0

    rows, read_errors, ok = [], 0, 0
    unknown_ext = {}
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            read_errors += 1
            continue
        ok += 1
        ext = f.suffix.lower()
        if ext not in KNOWN_EXT:
            unknown_ext[ext or "(无扩展名)"] = unknown_ext.get(ext or "(无扩展名)", 0) + 1
        keep, only = strip_line_family(text, ext, args.hash)
        chosen = only if args.only_comments else keep
        for idx, line in enumerate(chosen.split("\n"), 1):
            if line.strip():
                rows.append({"file": str(f), "line": idx, "text": line})

    if ok == 0:
        print("全部文件不可读", file=sys.stderr)
        return 2
    if read_errors:
        # ⚠️ 读失败绝不可静默(全仓退出码约定第 3 条):它会让本次实跑变成残缺样本上的 0 命中。
        print("⚠️ %d 个文件读不出来,已跳过 —— 本次输出是残缺样本,⛔ 不得据此下"
              "「没有残留」的结论" % read_errors, file=sys.stderr)
    if unknown_ext:
        # 未识别扩展名 = 原样保留(不剥)。方向是假红,但必须说出来:
        # 否则作者会以为「这些文件里的注释也剥过了」。
        print("ℹ️ %d 类未识别扩展名按「不剥注释」原样输出(%s)—— 其中的注释仍会命中,"
              "属可见的假红,人工排除即可" %
              (len(unknown_ext),
               ", ".join("%s×%d" % (k, v) for k, v in sorted(unknown_ext.items()))),
              file=sys.stderr)

    if args.json:
        print(json.dumps({"skipped": False, "files": ok, "lines": len(rows),
                          "read_errors": read_errors,
                          "unknown_ext": sorted(unknown_ext),
                          "rows": rows}, ensure_ascii=False))
        return 0
    for r in rows:
        print("%s:%d:%s" % (r["file"], r["line"], r["text"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
