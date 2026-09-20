#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""维度 8 硬门：请求通道 URL 拼装单一信源（前端专属·纯静态）

只回答一件事
------------
**「把 base 拼到 URL 前面」这条判据，在项目里是不是只有一处实现？**

判据类逻辑一旦有平行实现，写第 N 份的人不会被任何机制提醒「这里有坑、且已有答案」。
典型翻车（实际项目中曾出现）：新写的 SSE 封装无条件拼
`import.meta.env.VITE_API_BASE_URL`，而接口常量 `/demo-app/ai/...`
本就含 context-path，再拼一次 base →
`/demo-app/demo-app/ai/...` → 404。
同项目 `http.ts` 里 `resolveConfig` / `ssePost` 早有两处正确判断（注释白纸黑字写着
"must bypass baseURL to avoid doubling"），新写的第三处一处也没复用。
`vue-tsc` 与 `eslint` 全绿——**只有真实发请求才暴露**。

判定主线（结构信号，不是逐点命中即报）
--------------------------------------
自拼 base 在项目里有**唯一合法位置** = URL 解析单一信源本身（`resolveApiUrl` 之类）。
所以逐点命中即报必然误报一片。改用结构信号：

* 计入的「自拼点」= 同时满足两条 —— ① 出现 base 拼装形态（`${base}${url}` / `base + url`）
  ② **所在文件里存在请求发起点**（`fetch(` / `new EventSource(` / `axios.*(` / `.getReader()` …）。
  只算 ② 是为了把「页面跳转 `location.href = ${base}/logout`」「`new HttpClient(config.baseUrl)`
  传参」这类非请求通道的用法挡在门外（实测 aidp-code-engineer 里正是这两种形态）。
* 计入自拼点散落在 **≥2 个不同文件 = 平行实现** → 🔴 Critical（应收敛到单一信源）。
* 只有 **1 个文件** → 放行，并把该文件报为「认定的 URL 拼装单一信源」。
* `--changed` 给了本次改动文件时：≥2 个文件的前提下，**只有落在改动文件里的自拼点判
  Critical**，其余降为 🟡 Warn（存量技术债，不该卡本次验收）。
* `--allow` 显式声明了单一信源时：信源内不计数，**信源之外只要有一处就是 Critical**
  （哪怕只有一处）——因为它就是平行于已声明信源的第二份实现。
  ⚠️ **`--allow` 优先于 `--changed`**：两个一起传时 `--changed` 的存量降级**不生效**
  （已声明信源就意味着"之外一处都不许有"，存量也不例外），此时会打一条 stderr 提示。

**不覆盖（别当已查）**
* 不判断拼出来的 URL 到底对不对、有没有真的重复 context-path——静态拿不到 env 值。
  「base 该不该含 context-path」属维度 3（见 `references/stack-vue.md` §三）。
* 不跟踪跨文件的变量传递（`const u = base + p; sendIt(u)` 里 `sendIt` 在别的文件）。
* **条件 ② 是文件级的，同样能被跨文件击穿**：`const u = "`" + "${base}${p}" + "`"; request(u)`
  里 `request` 从别处 import、本文件没有请求发起点 → 落入 `ignored_no_request_call`
  不计入。这是为了去噪付出的代价，人工核对时请扫一眼该清单。
* **只认两种拼装形态**：`${base}...` 模板 与 `base + url` 加号（`+` 两侧可跨行）。
  `[base, url].join('')`、`base.concat(url)`、`new URL(url, base)`、`full += url`
  一律不认。
* **base 别名解析是单跳、不传递**：`const base = env.X; const b2 = base;` 里 `b2` 不算 base
  （除非中间那个名字本身就在 base 词表内）；`const { VITE_API_BASE_URL } = import.meta.env`
  这类解构不认，裸的 `VITE_*` 常量名也不在词表内。
* **只看文件级分布**：同一个文件里写了 N 份平行判据不判（`distinct_files` 仍是 1、照样放行）。
* 正则字面量按「值位置的 `/` + 同行闭合 + 体内含引号/反引号/`/`」启发式识别并整体抹白
  （避免正则里的引号或**反引号**让词法状态机串味——反引号没有「不跨行」止损，会一路吞到
  下一个反引号或文件尾）。三条约束缺一不可，**尤其第三条**：只在候选体内真的含有会串味的
  字符时才抹白，否则「除法 / JSX 被误判成正则」会把中间的真代码整段吃掉 → 真自拼点漏检
  → 假绿灯（漏检向比误报危险）。
  「值位置」在 JS 文法之上再扣掉四种 JSX/自增前驱（详见 `_regex_allowed_at` 的 docstring）：
  前一个非空字符是 `<` 或 `}`、是不构成 `=>` 的 `>`、或是 `++`/`--`。这四种覆盖了
  `</div>`、`<span>{used}/{total}</span>`、`<Foo a={b} /> … <Bar />`、`<code>/api/v1</code>`、
  `i++ / n`。
  **残留边界（别当已查）**——两个方向都会漏检，因为识别错了正则边界，真自拼点就要么被
  抹白、要么被串味吞掉，**殊途同归都是假绿灯**：
    * 识别过头：前驱是 `,` `;` `(` `[` `=` `:` `!` `&` `|` `?` `{` `-` `*` `%` `^` `~`
      或 `return` 等关键字时仍按文法判为正则起点。这些位置上真实代码写的几乎都是正则，
      但 JSX **文本**里恰好出现同款字符再跟一个 `/`（如 `<div>50% / 60% "x"</div>`）
      会误判，被误判的这段里若正好有自拼点则漏检。
    * 识别不足：上面那四种前驱（`<` `}` 非 `=>` 的 `>` `++`/`--`）之后若跟的是**真正则**
      且体内含 hazard 字符，它不会被抹白、引号/反引号照旧串味（实测 ``if(1){ } /`/.test(s)``
      同行后续的自拼点确实漏检）。这类写法在真实代码里近乎不存在，故按「JSX 常见、
      该写法罕见」取舍——但它是已知盲区，不是已覆盖项。
  该启发式不是完整的 JS 词法分析；要根治须真正的 JSX 词法，超出本脚本「纯 grep 级静态
  分析·零构建零依赖」的定位。

用法
----
    python check_request_channel_url.py <前端目录或文件...> [选项]

选项
    --changed F [F ...]   本次改动的文件（相对/绝对均可）；据此把存量平行实现降为 Warn
    --allow  G [G ...]    已确认的 URL 解析单一信源（glob，匹配仓库相对路径）
    --include-config      连同 *.config.js/ts 一起扫（默认排除，vite proxy 里拼 base 是正常的）
    --max-file-bytes N    超过 N 字节的文件跳过（默认 2000000，须为正整数）。手写的请求通道不会
                          有这么大，这类文件多是打包产物/内联 base64；跳过项会明列在
                          skipped_large，不静默丢弃
    --json                机器可读输出（此模式下 stdout 只会是 JSON；用法/报错走 stderr）
    --strict              Warn 也计入闸门失败

退出码：0 = 闸门通过 / 1 = 未通过 / 2 = 输入错误
        安全失败（宁可报参数错，也不给假绿灯）：
          * `--changed` 的路径**全部**不存在 → exit 2，而不是把所有平行实现降级为 Warn
          * `--max-file-bytes` ≤ 0 → exit 2，否则全部文件被判超限跳过 = 闸门被静默关掉
        另：不可读文件（权限/断链符号链接）登记进 `unreadable_files` 并打 stderr，
        **不**当作「已扫过且干净」静默吞掉。
"""

import argparse
import bisect
import fnmatch
import json
import os
import re
import sys
from pathlib import Path

SCAN_EXTS = {".ts", ".js", ".mjs", ".cjs", ".mts", ".cts", ".tsx", ".jsx", ".vue"}
SKIP_DIRS = {
    "node_modules", "dist", "build", "out", ".output", ".nuxt", ".next",
    "coverage", ".git", "__pycache__", ".turbo", ".cache", "public",
}
SKIP_NAME_RE = re.compile(r"\.(min|bundle|chunk)\.[cm]?js$|\.d\.ts$", re.I)
CONFIG_NAME_RE = re.compile(r"\.config\.[cm]?[jt]s$", re.I)

# ---- base 表达式：env 形态 + 常见标识符形态 + 成员形态 -------------------------
BASE_EXPR = re.compile(
    r"""(?:
          (?:import\.meta\.env|process\.env)\.[A-Za-z0-9_]*BASE_?URL[A-Za-z0-9_]*
        | \b(?:baseUrl|baseURL|BASE_URL|apiBase|apiBaseUrl|API_BASE|API_BASE_URL
             |serviceBase|serverBase|gatewayBase|prefixUrl|urlPrefix)\b
        | \b[A-Za-z_$][\w$]*\.(?:baseUrl|baseURL)\b
    )""",
    re.X,
)

# ---- 请求发起点：只作「该文件属于请求通道」的文件级判据 -----------------------
REQUEST_CALL = re.compile(
    r"""(?:
          \bfetch\s*\(
        | \bfetchEventSource\s*\(
        | \bofetch\s*\(
        | \$fetch\s*\(
        | \bnew\s+EventSource\s*\(
        | \bnew\s+WebSocket\s*\(
        | \bnew\s+XMLHttpRequest\b
        | \baxios\s*\(
        | \baxios\.(?:get|post|put|delete|patch|head|options|request)\s*\(
        # 前缀可为空：裸 `http.get(` / `api.post(` / `client.get(` 是最常见写法，
        # 早期版本要求前缀至少 1 个字符，把它们整批漏认成「本文件无请求发起点」。
        # 但后缀只许 [0-9_$]（`http$.request(`、`api2.get(`），**不许任意词**——
        # 否则 `httpStatusMap.get(code)` 这类 Map/集合操作会被当成请求发起点。
        # 方向很重要：本正则放宽 = 更多自拼点被「计入」= 更容易判 Critical，是**阻断向**，
        # 故按「精度优先、零误阻断」宁可漏认（漏认只会让自拼点落进 ignored，不卡发布）。
        | \b(?:[A-Za-z_$][\w$]*)?(?:[Hh]ttp|[Cc]lient|[Ii]nstance|[Ss]ervice|[Aa]pi)[0-9_$]*
              \.(?:get|post|put|delete|patch|request)\s*\(
        | \.getReader\s*\(\s*\)
        | \$\.ajax\s*\(
        | \bnavigator\.sendBeacon\s*\(
    )""",
    re.X,
)

# ---- 文件内别名：env 值常先落到局部变量，再拿局部变量去拼 --------------------
# 只认「RHS 就是 base 表达式本身」的赋值（允许 ?? / || 兜底），
# 显式排除 RHS 里已有 + 或反引号的情况——那种是拼装结果（`const full = base + url`），
# 把它也当 base 会把下游每一次再拼都算成新的自拼点。
ALIAS_ASSIGN = re.compile(
    r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*(?::[^=;\n]+?)?=\s*([^;\n]+)"
)

# ---- 正则字面量：识别「值位置的 /」------------------------------------------
# 不识别的话，正则里的引号/反引号会让词法状态机串味。反引号尤其危险：它会开启一个
# 假模板字面量，一路吞到下一个反引号或文件尾（不像引号那样有「不跨行」止损），
# 该段内的真实自拼点整批漏检，还可能把段内字符串里的 `${baseUrl}` 误当代码。
#
# 下表 = 「按 JS 文法，其后可以出现正则字面量」的前驱标点，**只表达文法允许**。
# 真实代码里明明是 JSX/自增的那几种，一律由 `_regex_allowed_at` 的例外分支否决
# （例外集中在一处，避免同一条规则在表里和分支里各表达一遍、改一处漏一处）。
_REGEX_PREV_PUNCT = set("(,=:[!&|?{};+-*%~^<>")
_REGEX_PREV_KW = {
    "return", "typeof", "case", "in", "of", "do", "else", "yield",
    "await", "new", "delete", "void", "instanceof",
}
_IDENT_TAIL = re.compile(r"[A-Za-z_$][\w$]*$")

# 只有这几个字符会真的让词法状态机串味：反引号/引号开启假模板或假字符串；`/` 会被
# 后续循环重新当成注释或新的正则起点（它只可能来自 `\/` 转义或 `[/]` 字符类，本身
# 就是强正则信号）。候选体内一个都不含时抹白零收益，却会在「除法/JSX 被误判成正则」
# 时吃掉真代码——那是**漏检向**（真自拼点被抹白 → 假绿灯），比误报危险得多，
# 故不含 hazard 一律不抹。
_REGEX_HAZARD = set("`\"'/")


def _regex_allowed_at(text, i):
    """`/` 是否处于「值位置」（即它开启的是正则字面量，而非除号或 JSX 里的斜杠）。

    `_REGEX_PREV_PUNCT` 给的是「JS 文法允许」，但 `.jsx/.tsx` 也在扫描范围内，
    而 JSX 里 `/` 极其常见。以下几种前驱在真实前端代码里**压不出正则字面量**，
    却是 JSX 斜杠的高频来源，一律否决——判错的代价是把候选体内的真代码整段抹白，
    即真自拼点漏检、假绿灯（漏检向比误报危险得多）：

      * `<` —— `a < /re/` 没人会写；`</div>` 闭合标签才是它的真实来源。
      * `}` —— `}` 结束的是块 / 对象 / JSX 插值，其后紧跟正则字面量在真实代码里不存在；
        而 `<span>{used}/{total}</span>`（比例、日期、路径）这类 JSX 写法极常见。
        它同时覆盖了自闭合标签 `<Foo a={b} /> … <Bar />`：那个 `/` 的前驱正是 `}`。
      * `>` 且不构成 `=>` —— 箭头函数 `x => /re/.test(x)` 是正则的合法前缀必须放行；
        但 `<span>…</span> / <span>…</span>`、`<code>/api/v1</code>` 里的 `>` 是标签
        闭合，而 `a > /re/` 是不会有人写的比较。
      * `++` / `--` —— 后缀自增之后只能接运算符，`i++ / n` 必然是除法。

    ⚠️ 不要改成「`/>` 即非正则」那种**按后继字符**的排除：它看似也能挡住自闭合标签，
    实则会把 `/>["']/g` 这类以 `>` 开头的真正则放回词法流，体内的引号随即开启假字符串
    吃掉本行余下代码——实测该写法会让同行的真自拼点漏检（`{used}/{total}` 一类由上面
    的 `}` 规则覆盖，无需再按后继字符排除）。
    """
    k = i - 1
    while k >= 0 and text[k] in " \t\r\n":
        k -= 1
    if k < 0:
        return True
    ch = text[k]
    if ch == "<" or ch == "}":
        return False
    if ch in "+-" and k >= 1 and text[k - 1] == ch:
        return False
    if ch == ">" and not (k >= 1 and text[k - 1] == "="):
        return False
    if ch in _REGEX_PREV_PUNCT:
        return True
    m = _IDENT_TAIL.search(text[max(0, k - 12):k + 1])
    return bool(m) and m.group(0) in _REGEX_PREV_KW


def _regex_end(text, i, n):
    """从 `/` 起找同一行内的闭合 `/`；找不到返回 -1（则按除号处理，保持旧行为）。"""
    j = i + 1
    in_class = False
    while j < n:
        ch = text[j]
        if ch == "\\":
            j += 2
            continue
        if ch == "\n":
            return -1
        if ch == "[":
            in_class = True
        elif ch == "]":
            in_class = False
        elif ch == "/" and not in_class:
            return j + 1
        j += 1
    return -1


def line_lookup(text):
    """O(n) 建行首索引 → O(log n) 查行号。

    原实现每命中一次就 `text.count("\\n", 0, pos)`，是 O(n·命中数) 的二次复杂度：
    实测 800KB 全命中文件 5.3s、5MB 文件 >120s 不返回（str.count 占 82% 时间）。
    """
    starts = [0]
    idx = text.find("\n")
    while idx >= 0:
        starts.append(idx + 1)
        idx = text.find("\n", idx + 1)
    return lambda pos: bisect.bisect_right(starts, pos)


def base_pattern_for(text):
    """按文件构造 base 表达式正则：通用形态 + 本文件内解析出的别名。"""
    aliases = set()
    for m in ALIAS_ASSIGN.finditer(text):
        name, rhs = m.group(1), m.group(2)
        if "+" in rhs or "`" in rhs:
            continue
        if BASE_EXPR.search(rhs):
            aliases.add(name)
    if not aliases:
        return BASE_EXPR
    extra = r"|\b(?:%s)\b" % "|".join(sorted(re.escape(a) for a in aliases))
    return re.compile("(?:%s%s)" % (BASE_EXPR.pattern, extra), re.X)


# ------------------------------------------------------------------ 词法扫描
def scan_js(text):
    """返回 (blanked, no_comment, templates)。

    blanked —— **只剩代码**的等长文本：注释、字符串字面量内容、模板字面量的原始文本
               一律替换成空白（保留换行，故行号不变），`${}` 内部因属代码而保留。
               这样形态 B（`base + url`）不会命中注释里的说明、也不会命中
               `const s = 'baseUrl + url'` 这种恰好写了同款字样的字符串。
    no_comment —— 只把注释抹白、字符串与模板原文原样保留：别名解析必须用它，
               否则 `const full = `${baseUrl}${url}`` 里反引号被抹白后会被误认成新别名。
    templates —— [(start, end, [(interp_start, interp_end), ...])]，start 指反引号；
               位置均指向**原文** text 的下标，可直接用来在上面三份等长文本里定位
               （三份长度一致，故同一下标在哪份上都指同一个字符）。形态 A 判 base 用
               `blanked`、判「模板尾部还有内容」用 `no_comment`——都不是原文。

    带状态机：正确处理字符串转义、模板字面量嵌套、`${}` 内的对象字面量花括号。
    正则字面量按启发式识别（`_regex_allowed_at` + 体内确含引号/反引号/斜杠才抹白），
    **不是完整词法**；极端歧义写法仍可能判错，边界见模块 docstring 的「不覆盖」。
    """
    out = list(text)
    nc = list(text)          # 仅去注释（字符串/模板原文保留），供别名解析用
    templates = []
    stack = []  # ('tpl', start, interps) | ('interp', start) | ('brace', start)
    i, n = 0, len(text)

    def blank(a, b):
        # 用切片赋值而非逐字符循环：巨型单行文件（打包产物、内联 base64）下
        # 逐字符版本会把 5MB 文件拖到秒级，这里保持线性且常数很小
        b = min(b, n)
        if a >= b:
            return
        seg = text[a:b]
        if "\n" in seg:
            out[a:b] = [ch if ch == "\n" else " " for ch in seg]
        else:
            out[a:b] = " " * (b - a)

    while i < n:
        c = text[i]
        # --- 模板字面量的原始文本区（非代码，整段抹白）---
        if stack and stack[-1][0] == "tpl":
            if c == "\\":
                blank(i, i + 2)
                i += 2
                continue
            if c == "`":
                _, start, interps = stack.pop()
                templates.append((start, i + 1, interps))
                blank(i, i + 1)
                i += 1
                continue
            if c == "$" and i + 1 < n and text[i + 1] == "{":
                stack.append(("interp", i + 2))
                blank(i, i + 2)
                i += 2
                continue
            blank(i, i + 1)
            i += 1
            continue
        # --- 代码区（顶层，或 ${} 内部）---
        if c == "\\":
            i += 2
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            j = text.find("\n", i)
            j = n if j < 0 else j
            for k in range(i, j):
                out[k] = nc[k] = " "
            i = j
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            for k in range(i, j):
                if out[k] != "\n":
                    out[k] = nc[k] = " "
            i = j
            continue
        if c == "/" and _regex_allowed_at(text, i):
            j = _regex_end(text, i, n)
            # 只抹「体内含 hazard 字符」的候选：抹白的唯一目的就是不让引号/反引号/`//`
            # 串味。不含 hazard 时保持原样，除法与 JSX 被误判也不会吃掉真代码。
            if j > 0 and not _REGEX_HAZARD.isdisjoint(text[i + 1:j - 1]):
                blank(i, j)  # 正则字面量整体不是「拼装代码」，且不得参与后续词法
                i = j
                continue
        if c in "\"'":
            q = c
            start = i
            i += 1
            while i < n:
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == q:
                    i += 1
                    break
                if text[i] == "\n":  # 未闭合引号，止损在本行
                    break
                i += 1
            blank(start, i)  # 字符串内容不是代码
            continue
        if c == "`":
            stack.append(("tpl", i, []))
            blank(i, i + 1)
            i += 1
            continue
        if c == "{":
            stack.append(("brace", i))
            i += 1
            continue
        if c == "}":
            if stack and stack[-1][0] == "brace":
                stack.pop()
            elif stack and stack[-1][0] == "interp":
                _, istart = stack.pop()
                if stack and stack[-1][0] == "tpl":
                    stack[-1][2].append((istart, i))
            i += 1
            continue
        i += 1
    return "".join(out), "".join(nc), templates


_NONSPACE = re.compile(r"\S")
VUE_BLOCK = re.compile(r"^[ \t]*<(script)\b([^>]*)>", re.I | re.M)


def extract_scannable(path, text):
    """.vue 只取 <script> 块内容（其余位置置空保号）；其它文件整篇。"""
    if path.suffix.lower() != ".vue":
        return text
    keep = [" " if ch != "\n" else "\n" for ch in text]
    for m in VUE_BLOCK.finditer(text):
        body_start = m.end()
        close = re.compile(r"</script\s*>", re.I).search(text, body_start)
        body_end = close.start() if close else len(text)
        for k in range(body_start, body_end):
            keep[k] = text[k]
    return "".join(keep)


_SNIPPET_WINDOW = 400  # 行首/行尾的回扫上限（> _SNIPPET_MAX + _SNIPPET_LEAD）
_SNIPPET_LEAD = 40     # 超长行重新锚定时，命中点左侧保留多少上下文
_SNIPPET_MAX = 160     # 最终截断长度


def snippet(text, pos):
    """取 pos 所在行、strip 后前 160 字符；**命中点保证落在返回的片段内**。

    ⚠️ 限窗是为了避免二次复杂度：`rfind("\\n", 0, pos)` 在**单行巨型文件**（打包产物、
    生成代码，名字不叫 `.min.js` 就进不了 SKIP_NAME_RE）上会一路回扫到文件头，
    `text[ls:le].strip()` 再把整行复制一遍 —— 每个命中都来一次 = O(n·命中数)。这与
    行号计算曾踩过的是同一种二次路径（那处已改为 `line_lookup` 建索引 + bisect 查表）。
    复现：单行 2MB、约 9 万个自拼点的 `.ts`，限窗前 18.7s、限窗后 1.05s。

    ⚠️ 但**限窗只解决耗时、不解决可读性**：窗口取 `[pos-400, pos+400]` 之后若仍从窗口
    头部截 160 字符，命中点在窗口内的偏移是 400、会被整个截掉——报告里那行 `code` 于是
    变成与命中点毫无关系的一段文本（实测：命中 `base + url` 的行只输出 160 个 `P`），
    比不给还糟，因为它看着像证据。故命中点会被截掉时，把起点重新锚到 `pos - 40`。
    命中点本就落在前 160 字符内时（绝大多数正常行）输出与不限窗时逐字相同。
    """
    lo = max(0, pos - _SNIPPET_WINDOW)
    ls = text.rfind("\n", lo, pos)
    ls = lo if ls < 0 else ls + 1
    hi = min(len(text), pos + _SNIPPET_WINDOW)
    le = text.find("\n", pos, hi)
    le = hi if le < 0 else le
    seg = text[ls:le]
    lead = len(seg) - len(seg.lstrip())      # strip() 会吃掉的行首空白
    if pos - ls - lead >= _SNIPPET_MAX:      # 命中点会被 [:160] 截掉 → 以命中点重新锚定
        ls = max(ls, pos - _SNIPPET_LEAD)
        seg = text[ls:le]
    return seg.strip()[:_SNIPPET_MAX]


# ------------------------------------------------------------------ 单文件分析
def analyse_file(path, max_bytes):
    """→ (hits, has_request_call, oversize, unreadable)；hits = [{line, kind, code}]"""
    try:
        if path.stat().st_size > max_bytes:
            return [], False, True, False
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        # 权限不足 / 断链符号链接：不能当「已扫过且干净」静默吞掉，否则文件里真有
        # 平行实现也照样绿灯。登记进 unreadable_files，由调用方明列。
        return [], False, False, str(exc)
    src = extract_scannable(path, raw)
    blanked, no_comment, templates = scan_js(src)

    has_request = bool(REQUEST_CALL.search(blanked))
    base_re = base_pattern_for(no_comment)
    plus_re = re.compile(
        r"(?:%s)\s*\+|\+\s*(?:%s)" % (base_re.pattern, base_re.pattern), re.X
    )

    hits = {}
    line_no = line_lookup(src)
    # 形态 A：模板字面量里 ${base} 之后还有内容
    # ⚠️ base 判定必须用 blanked（只剩代码）而不是原文 src——否则 `${}` 内部的
    #    字符串/注释/嵌套模板原文里出现 `baseUrl` 字样即误报，例如
    #    `${ t('baseUrl') }/x`、`${ /* baseUrl */ id }/x`、`${ c ? `baseUrl` : 'n' }/x`。
    #    tail 判「模板尾部还有内容」必须保留字面量原文（blanked 里模板原文已被抹白），
    #    但要用去掉注释的 no_comment，否则 `${base}/* c */` 的注释会被当成「有内容」。
    for tstart, tend, interps in templates:
        for istart, iend in sorted(interps):
            # 用 pos/endpos 而非切片：切片会在「一个模板里塞了成百上千个 ${}」时
            # 每个插值复制一次整段模板尾巴 = O(插值数 × 模板长度) 的二次路径
            # （实测 32000 个插值 / 597KB 文件 1.8s，切片改 pos/endpos 后线性）。
            if not base_re.search(blanked, istart, iend):
                continue
            # tail 判「'}' 到闭合反引号之间还有非空白内容」，等价于原来的 tail.strip()
            if _NONSPACE.search(no_comment, iend + 1, tend - 1):
                hits.setdefault(istart, ("template", line_no(istart)))
    # 形态 B：base 与 + 相邻
    for m in plus_re.finditer(blanked):
        hits.setdefault(m.start(), ("plus", line_no(m.start())))

    return (
        [
            {"line": ln, "kind": kind, "code": snippet(src, pos)}
            for pos, (kind, ln) in sorted(hits.items())
        ],
        has_request,
        False,
        False,
    )


# ------------------------------------------------------------------ 收集文件
def collect(paths, include_config):
    files, missing = [], []
    for p in paths:
        pp = Path(p)
        if not pp.exists():
            missing.append(str(pp))
            continue
        if pp.is_file():
            if pp.suffix.lower() in SCAN_EXTS:
                files.append(pp.resolve())
            continue
        for root, dirs, names in os.walk(pp):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
            for nm in names:
                f = Path(root) / nm
                if f.suffix.lower() not in SCAN_EXTS:
                    continue
                if SKIP_NAME_RE.search(nm):
                    continue
                if not include_config and CONFIG_NAME_RE.search(nm):
                    continue
                files.append(f.resolve())
    return sorted(set(files)), missing


def find_repo_root(start):
    cur = start if start.is_dir() else start.parent
    for c in [cur] + list(cur.parents):
        if (c / ".git").exists():
            return c
    return cur


def rel(p, root):
    try:
        return p.resolve().relative_to(root).as_posix()
    except ValueError:
        return p.as_posix()


# ------------------------------------------------------------------ 主流程
def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--changed", nargs="*", default=None)
    ap.add_argument("--allow", nargs="*", default=None)
    ap.add_argument("--include-config", action="store_true")
    ap.add_argument("--max-file-bytes", type=int, default=2_000_000)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("-h", "--help", action="store_true")
    args = ap.parse_args(argv)

    if args.help:
        print(__doc__)
        return 0
    if not args.paths:
        sys.stderr.write(__doc__)  # --json 模式下 stdout 必须只有 JSON
        return 2
    if args.max_file_bytes <= 0:
        # `--max-file-bytes 0` 会把每个文件都判为超限跳过 → 0 自拼点 → exit 0，
        # 等于静默关掉整道闸门。与本脚本「宁可 exit 2 也不给假绿灯」的原则一致，按输入错误拒绝。
        sys.stderr.write("❌ --max-file-bytes 必须为正整数（当前 %d，会把全部文件判为跳过、"
                         "闸门静默失效）\n" % args.max_file_bytes)
        return 2

    files, missing = collect(args.paths, args.include_config)
    if missing:
        sys.stderr.write("路径不存在：%s\n" % "、".join(missing))
        return 2

    root = find_repo_root(Path(args.paths[0]).resolve())
    # --changed / --allow 写错路径会让本闸门「静默放行」（无匹配 → 全降 Warn / 无 site 计入
    # → 通过），方向正是不安全的那一侧。故显式登记未解析项并打到 stderr。
    changed, changed_unresolved = set(), []
    if args.changed:
        for c in args.changed:
            cp = Path(c)
            ap = cp if cp.is_absolute() else (Path.cwd() / cp)
            r = rel(ap, root)
            changed.add(r)
            if not ap.exists():
                changed_unresolved.append(c)
    allow = list(args.allow or [])

    sites, ignored, oversized, unreadable = [], [], [], []
    for f in files:
        hits, has_req, oversize, unread = analyse_file(f, args.max_file_bytes)
        if oversize:
            oversized.append(rel(f, root))
            continue
        if unread:
            unreadable.append({"file": rel(f, root), "error": unread})
            continue
        if not hits:
            continue
        r = rel(f, root)
        for h in hits:
            rec = dict(h, file=r)
            (sites if has_req else ignored).append(rec)

    def allowed(r):
        return any(fnmatch.fnmatch(r, g) for g in allow)

    allow_matched = sorted({s["file"] for s in sites if allowed(s["file"])})
    allow_unmatched = [g for g in allow
                       if not any(fnmatch.fnmatch(s["file"], g) for s in sites)]

    counted = [s for s in sites if not allowed(s["file"])]
    distinct = sorted({s["file"] for s in counted})

    errors, warns = [], []
    if allow:
        for s in counted:
            errors.append(dict(s, reason="平行于已声明的 URL 解析单一信源（--allow）"))
    elif len(distinct) >= 2:
        for s in counted:
            if changed and s["file"] not in changed:
                warns.append(dict(s, reason="存量平行拼装（本次未改动，不阻断本轮验收）"))
            else:
                errors.append(
                    dict(s, reason="base 拼装判据平行实现于 %d 个文件，应收敛为单一信源"
                                   % len(distinct))
                )

    single_source = distinct[0] if (not allow and len(distinct) == 1) else None
    skipped = not files
    passed = not errors
    gate_passed = passed and (not warns if args.strict else True)

    result = {
        "passed": passed,
        "gate_passed": gate_passed,
        "strict": bool(args.strict),
        "skipped": skipped,
        "repo_root": str(root),
        "scanned_files": len(files),
        "concat_sites": len(sites),
        "distinct_files": len(distinct),
        "distinct_file_list": distinct,
        "single_source": single_source,
        "changed_unresolved": changed_unresolved,
        "allow_matched_files": allow_matched,
        "allow_unmatched_globs": allow_unmatched,
        "ignored_no_request_call": ignored,
        "skipped_large": oversized,
        "unreadable_files": unreadable,
        "errors": errors,
        "warns": warns,
    }

    # ⚠️ `--allow` 的 glob 一个都没匹配上 = **入参写错**，绝不能继续跑出结论。
    #    基准是**仓库根**、不是扫描目录：前端嵌在 `code/frontend/web/` 这类子路径下时，
    #    写成扫描目录相对路径就会一个都匹配不上 → 口径反转后「全项目唯一那处合法信源」
    #    被判成「平行于已声明信源」的 Critical —— 纯假红，且文案与事实完全相反，
    #    还会把开发赶去「收敛」一个本来就唯一的信源。宁可报参数错，也不给错误结论。
    #    ★ 本分支与姊妹脚本 check_webmcp_adapter.py 的同名分支**判据完全相同**，
    #      那边先修、这边漏了回灌 —— 属「新判据加了、旧的那份没跟着改」，勿再拆开。
    if allow and not allow_matched:
        sys.stderr.write(
            "❌ --allow 的 glob 一个都没匹配上（基准是仓库根 %s，不是你传的扫描目录）。\n"
            "   请写成相对仓库根的路径，例如 '%s'。\n"
            % (root, (sites[0]["file"] if sites else "code/frontend/web/src/utils/apiUrl.ts")))
        return 2

    if args.changed and allow:
        sys.stderr.write("⚠️  同时传了 --allow 与 --changed：--allow 的口径（信源之外一处都不许有）"
                         "优先，本次 --changed 的存量降级不生效\n")
    for u in unreadable:
        sys.stderr.write("⚠️  文件不可读，未参与检查（不等于干净）：%s（%s）\n"
                         % (u["file"], u["error"]))
    for c in changed_unresolved:
        sys.stderr.write("⚠️  --changed 路径不存在，不会匹配到任何自拼点：%s\n" % c)
    if args.changed and len(changed_unresolved) == len(args.changed):
        # 全部写错 = 参数出错。若继续跑，所有平行实现都会因「不在改动集里」降为 Warn
        # 而放行——静默通过正是最危险的方向，故按输入错误退出而不是给个假绿灯。
        sys.stderr.write("❌ --changed 的路径全部不存在，判为参数错误（否则会把所有平行"
                         "实现降级为 Warn 而静默放行）\n")
        return 2
    for g in allow_unmatched:
        sys.stderr.write("⚠️  --allow 模式未匹配到任何自拼点所在文件，可能是写错了：%s\n" % g)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        report(result)
    return 0 if gate_passed else 1


def report(r):
    print("=" * 68)
    print("维度 8 · 请求通道 URL 拼装单一信源")
    print("=" * 68)
    if r["skipped"]:
        print("⏭️  未扫到任何前端源码，整维度跳过（不计入通过/不通过）")
        return
    print("扫描文件 %d 个 · 计入自拼点 %d 处 · 分布于 %d 个文件"
          % (r["scanned_files"], r["concat_sites"], r["distinct_files"]))
    if r["single_source"]:
        if r["concat_sites"] == 1:
            print("✅ 全项目只有一处实现，认定为 URL 拼装单一信源：%s" % r["single_source"])
        else:
            print("✅ %d 处自拼点全部集中在同一个文件，认定为 URL 拼装单一信源：%s"
                  % (r["concat_sites"], r["single_source"]))
            print("   （⚠️ 本闸门只看文件级分布，同一文件内是否又写了多份判据请人工确认）")
    for e in r["errors"]:
        print("\n🔴 %s:%d  [%s]" % (e["file"], e["line"], e["kind"]))
        print("   %s" % e["code"])
        print("   → %s" % e["reason"])
    for w in r["warns"]:
        print("\n🟡 %s:%d  %s" % (w["file"], w["line"], w["code"]))
        print("   → %s" % w["reason"])
    if r["skipped_large"]:
        print("\n⚠️  %d 个文件超过 --max-file-bytes 未扫描（疑似打包产物/内联资源）：%s"
              % (len(r["skipped_large"]), "、".join(r["skipped_large"][:5])))
    if r["unreadable_files"]:
        print("\n⚠️  %d 个文件不可读、未参与检查（**不等于干净**）：%s"
              % (len(r["unreadable_files"]),
                 "、".join(u["file"] for u in r["unreadable_files"][:5])))
    if r["ignored_no_request_call"]:
        print("\n（另有 %d 处 base 拼装所在文件无请求发起点，非请求通道，未计入）"
              % len(r["ignored_no_request_call"]))
    print("\n结论：%s" % ("✅ 通过" if r["gate_passed"] else "❌ 未通过"))
    if r["errors"]:
        print("修法：把 base 拼装收敛到唯一的 URL 解析函数（如 `resolveApiUrl(url)`），"
              "所有请求发起点一律经它取 URL；已含 context-path 的绝对路径由该函数统一判定绕过 base。")


if __name__ == "__main__":
    sys.exit(main())
