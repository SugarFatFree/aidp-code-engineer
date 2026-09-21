#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""维度 9 硬门：WebMCP 前端能力实现合规（条件启用·纯静态）

只回答两件事（其余四项判据须人工静态核对，见 references/flow-webmcp.md）
------------------------------------------------------------------------
1. **单一适配层** —— 能力入口标识符在前端源码里的**命中文件数是不是恰好 1 个**？
2. **无 `unregisterTool`** —— 代码里出现它即 Critical。

为什么只做这两项：它们是**纯词法、零主观**的。9.2 的时序（登记不得早于配置就绪）、
9.3 错误契约死文案、9.4 写操作复用既有执行通道、9.5 敏感值不外泄、9.6 白名单而非黑名单，
都需要读语义，脚本判不了 —— **本脚本全绿 ≠ 维度 9 通过。**

判据要点
--------
* **注释里写了也算命中**：本脚本**刻意不剥离注释、不剥离字符串**。第二处适配层被注释掉一半
  留在文件里，照样是「这条判据有两份实现」，按「只扫有效代码」的口径会直接放行 —— 下游实际
  触发过这条。同理 `.vue` **整篇扫**（不像维度 8 那样只取 `<script>` 块）。
* **`unregisterTool` 是纯反模式**：实测该 API **不存在**。据草案臆想它存在会让撤销**静默失效**
  （曾用可选链做防御，撤销悄悄没生效、代码零报错、文档与实际不符）。故出现即 Critical。
* **`--allow` 声明单一适配层后口径反转**：信源之外只要有一处就是 Critical（哪怕全项目仅此一处），
  因为它就是平行于已声明信源的第二份。⚠️ **glob 的基准是仓库根**（`find_repo_root` 向上找
  `.git`），不是你传的扫描目录 —— 前端目录嵌在子路径下时（`code/frontend/web/src/...`）写
  `'src/adapter.ts'` 匹配不到，会把**唯一合法的信源**判成「平行实现」这种纯假红。故
  `--allow` 一个都没匹配上时**直接 exit 2 报入参错**，绝不继续跑出错误结论。

⛔ 不得写死 `--entry-symbols`
----------------------------
能力入口的挂载位置**已经迁移过一次、规范仍在演进**，写死任何一个名字都会过期。过期的方向是
**扫不到 → 0 命中 → 假绿**，正是本维度最不能出的错。故缺该入参时**报入参错（exit 2）**，
绝不猜一个默认值。

门控
----
本维度**只在调用方传入 `webmcp_enabled: true` 时启用**。为 false 或未传时，验收 Agent 根本
不该调用本脚本（整维度跳过，不计入通过/不通过、不产生告警、不在报告里留行）。
**判定权归调用方，本脚本与本 SKILL 都不自行探测是否启用。**

用法
----
    python3 check_webmcp_adapter.py <前端源码目录或文件...> \
        --entry-symbols <符号1> [<符号2> ...] [--allow <glob>...] [--json] [--strict]

退出码
------
    0  闸门通过（含「扫不到前端源码 → 整维度跳过」，此时 skipped=true，**不等于通过**）
    1  检出违规（严重度分档读 --json 的 errors / warns，不占用退出码）
    2  入参或环境错：路径不存在 / 缺位置参数 / 未传 --entry-symbols /
       --max-file-bytes 非正 / 显式传的文件全不在可扫类型内 / --allow 一个都没匹配上
"""
import argparse
import fnmatch
import json
import os
import re
import sys
from pathlib import Path

# ⚠️ 含 `.html`:WebMCP 登记写在 `index.html` 的内联 <script> 里是很自然的形态,漏掉即假绿。
#   这与本脚本「注释也算命中、`.vue` 整篇扫」的从宽口径一致——本维度判的是「这条判据有几份
#   实现」,任何一份写在哪都算。
SCAN_EXTS = {".ts", ".js", ".mjs", ".cjs", ".mts", ".cts", ".tsx", ".jsx", ".vue", ".html"}
# ⚠️ **刻意不跳过 `public/`**(与维度 8 的 check_request_channel_url.py 不同):那边扫的是
#   请求通道源码,`public/` 是静态资源无关;这边扫的是「能力入口出现在哪几个文件」,而
#   `public/legacy.js` 被原样拷进产物、照样会执行登记,跳过它就是漏掉一份平行实现。
SKIP_DIRS = {
    "node_modules", "dist", "build", "out", ".output", ".nuxt", ".next",
    "coverage", ".git", "__pycache__", ".turbo", ".cache",
}
SKIP_NAME_RE = re.compile(r"\.(min|bundle|chunk)\.[cm]?js$|\.d\.ts$", re.I)

# 实测不存在的 API。出现即 Critical（见模块 docstring）。
UNREGISTER_RE = re.compile(r"\bunregisterTool\b")

_SNIPPET_MAX = 160


def symbol_pattern(symbols):
    """把入口标识符编成一条正则。

    符号可能带点（成员形态）。故不能用 `\\b` —— `\\bfoo.bar\\b` 里的点还会当通配符，且
    `x.foo.bar` 这种**别的对象上的同名成员**会被误判成命中。改用显式前后界：前面不许是
    标识符字符或点，后面不许是标识符字符。

    ⚠️ **前界必须放行全局对象前缀，否则是假绿（实测踩过）**：只写 `(?<![\\w.$])` 的话，
    `window.navigator.modelContext` —— 一种完全合法、且很常见的写法 —— 会被那条负向后顾
    的 `.` 顺手挡掉。后果是第二处适配层扫不到、`distinct_files` 仍是 1，闸门 exit 0 还打印
    「✅ 认定为单一适配层」，给出的是**肯定性**的错误结论，`--strict` 也救不了。
    故显式允许一层 `window.` / `globalThis.` / `self.` / `top.`（含可选链 `?.`）。

    ⚠️ 只放行**一层**且必须紧邻：`window.foo.navigator.modelContext` 仍不命中（那是别的
    对象上的同名成员，与 `o.my.navigator.modelContext` 同类），护栏没有被放宽。
    """
    alts = "|".join(re.escape(s) for s in symbols)
    return re.compile(r"(?<![\w.$])(?:(?:window|globalThis|self|top)\s*\??\.\s*)?"
                      r"(?:" + alts + r")(?![\w$])")


def collect(paths):
    files, missing = [], []
    for p in paths:
        pp = Path(p)
        # exists() 与 is_dir() 分开判：合并写会把「路径根本不存在」和「传入单个文件＝合法」
        # 混为一谈 —— 手滑写错路径就等于整道闸门静默放行。
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


def line_of(text, pos):
    return text.count("\n", 0, pos) + 1


def snippet(text, pos):
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    if end < 0:
        end = len(text)
    return text[start:end].strip()[:_SNIPPET_MAX]


def analyse_file(path, sym_re, max_bytes):
    """返回 (入口命中列表, unregister 命中列表, 是否超限, 读取错误)。"""
    try:
        if path.stat().st_size > max_bytes:
            return [], [], True, None
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        # 读不出来 ≠ 干净：登记进 unreadable **并产一条 warn**（见 main），`--strict` 才拦得住。
        # ⚠️ 早期只登记不告警，`errors`/`warns` 双空 → 连 `--strict` 都放行，与本行注释
        #    自相矛盾（不可读文件里的第二适配层 + unregisterTool 实测被静默吃掉）。
        return [], [], False, str(e)
    entry = [{"line": line_of(text, m.start()), "symbol": m.group(0),
              "code": snippet(text, m.start())} for m in sym_re.finditer(text)]
    unreg = [{"line": line_of(text, m.start()), "code": snippet(text, m.start())}
             for m in UNREGISTER_RE.finditer(text)]
    return entry, unreg, False, None


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--entry-symbols", nargs="*", default=None)
    ap.add_argument("--allow", nargs="*", default=None)
    ap.add_argument("--max-file-bytes", type=int, default=2_000_000)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("-h", "--help", action="store_true")
    args = ap.parse_args(argv)

    if args.help:
        print(__doc__)
        return 0
    if not args.paths:
        # ⚠️ 先给一句人话再贴用法：`--entry-symbols A B <dir>` 这种顺序会让 argparse 把目录
        #    吞进符号列表、paths 变空，只贴 docstring 的话读者看不出是参数顺序问题。
        sys.stderr.write("❌ 缺少要扫描的前端源码路径（位置参数）。\n"
                         "   提示：`--entry-symbols` 是 nargs=*，若写成 "
                         "`--entry-symbols A B <目录>`，目录会被吞进符号列表；\n"
                         "         请把路径写在前面：`check_webmcp_adapter.py <目录> "
                         "--entry-symbols A B`\n\n")
        sys.stderr.write(__doc__)  # --json 模式下 stdout 必须只有 JSON
        return 2

    symbols = [s.strip() for s in (args.entry_symbols or []) if s and s.strip()]
    if not symbols:
        sys.stderr.write(
            "❌ 必须传 --entry-symbols（该项目实测的能力入口标识符，由调用方经 "
            "webmcp_entry_symbols 提供）。\n"
            "   ⛔ 本脚本刻意不内置默认符号：挂载位置已迁移过一次、规范仍在演进，"
            "写死必过期，\n"
            "      而过期的方向是「扫不到 → 0 命中 → 假绿」。\n")
        return 2
    if args.max_file_bytes <= 0:
        sys.stderr.write("❌ --max-file-bytes 必须为正整数（当前 %d，会把全部文件判为跳过、"
                         "闸门静默失效）\n" % args.max_file_bytes)
        return 2

    files, missing = collect(args.paths)
    if missing:
        sys.stderr.write("路径不存在：%s\n" % "、".join(missing))
        return 2
    # ⚠️ 显式传的**全是文件**、却一个都不在 SCAN_EXTS 内 → 入参错，不是「整维度 N/A」。
    #    否则 `check_webmcp_adapter.py index.htm --entry-symbols X` 这种手滑
    #    （或传了 .md/.json）会静默变成 skipped=true + exit 0，闸门被关掉而无人知晓。
    #    目录形态不适用本条：目录扫不到前端源码是合法的「本项目无前端 → 整维度跳过」。
    if not files and all(Path(p).is_file() for p in args.paths):
        sys.stderr.write("❌ 显式传入的文件没有一个属于可扫描类型 %s：%s\n"
                         % (sorted(SCAN_EXTS), "、".join(args.paths)))
        return 2

    root = find_repo_root(Path(args.paths[0]).resolve())
    sym_re = symbol_pattern(symbols)
    allow = list(args.allow or [])

    entry_sites, unreg_sites, oversized, unreadable = [], [], [], []
    for f in files:
        entry, unreg, oversize, unread = analyse_file(f, sym_re, args.max_file_bytes)
        if oversize:
            oversized.append(rel(f, root))
            continue
        if unread:
            unreadable.append({"file": rel(f, root), "error": unread})
            continue
        r = rel(f, root)
        entry_sites += [dict(h, file=r) for h in entry]
        unreg_sites += [dict(h, file=r) for h in unreg]

    def allowed(r):
        return any(fnmatch.fnmatch(r, g) for g in allow)

    allow_matched = sorted({s["file"] for s in entry_sites if allowed(s["file"])})
    allow_unmatched = [g for g in allow
                       if not any(fnmatch.fnmatch(s["file"], g) for s in entry_sites)]

    counted = [s for s in entry_sites if not allowed(s["file"])]
    distinct = sorted({s["file"] for s in counted})

    errors, warns = [], []
    if allow:
        for s in counted:
            errors.append(dict(s, kind="multi-adapter",
                               reason="平行于已声明的 WebMCP 单一适配层（--allow）"))
        # ⚠️ `--allow` 声明了 ≥2 个信源本身就违反 9.1「命中文件数必须 == 1」。
        #    早期只把「信源之外」的命中判 error，于是 `--allow '*'` 直接把整道闸门关掉
        #    （实测：两处适配层、`allow_matched_files` 两个、errors 空、exit 0）。
        if len(allow_matched) >= 2:
            errors.append({"file": "-", "line": 0, "kind": "multi-allowed-source", "code": "",
                           "reason": "--allow 命中 %d 个文件（%s）：单一适配层只能有一个，"
                                     "声明多个信源本身即违反 9.1"
                                     % (len(allow_matched), "、".join(allow_matched))})
    elif len(distinct) >= 2:
        for s in counted:
            errors.append(dict(s, kind="multi-adapter",
                               reason="能力入口散落于 %d 个文件，须收敛为单一适配层"
                                      % len(distinct)))
    for s in unreg_sites:
        errors.append(dict(s, kind="unregister-tool",
                           reason="unregisterTool 实测不存在，据草案臆想它存在会让撤销静默失效"))

    # 入口一处都没扫到 = **error 而不是 warn**。
    # ⚠️ 本脚本只在调用方传了 `webmcp_enabled: true` 时才会被调用——那意味着该项目**确实有**
    #    这个能力。此时 0 命中只有两种解释：符号过期 / 路径传错，**没有一种是「合规」**。
    #    早期判 warn，默认（非 --strict）下 `gate_passed=true`，而三处文档给的示例都不带
    #    `--strict`、也没要求核对 warns —— 照文档执行等于「符号写错就全绿」。
    if not entry_sites and files:
        errors.append({"file": "-", "line": 0, "kind": "no-entry-hit", "code": "",
                       "reason": "未命中任何入口标识符（%s）。本脚本仅在 webmcp_enabled=true 时"
                                 "调用，该项目应当有能力入口 → 0 命中 = 符号已过期或路径传错，"
                                 "不是合规" % "、".join(symbols)})

    # 超限 / 不可读文件 → 各产一条 warn（`--strict` 才拦得住）。
    # ⚠️ 早期只登记进结果字段、不产 warn，errors/warns 双空 → 连 --strict 都放行；
    #    实测把「第二适配层 + unregisterTool」放进超限或 chmod 000 的文件即整体静默通过。
    for f in oversized:
        warns.append({"file": f, "line": 0, "kind": "skipped-large", "code": "",
                      "reason": "超过 --max-file-bytes 未扫描，**不等于干净**：里面若有第二处"
                                "适配层或 unregisterTool 一律看不见，须人工确认"})
    for u in unreadable:
        warns.append({"file": u["file"], "line": 0, "kind": "unreadable", "code": "",
                      "reason": "文件不可读（%s），未参与检查，**不等于干净**" % u["error"]})

    # `--allow` 模式下 single_source 回落到唯一那个已声明信源，
    # 否则报告模板的「认定的单一适配层（single_source）」栏在 --allow 下永远填不出。
    if allow:
        single_source = allow_matched[0] if len(allow_matched) == 1 else None
    else:
        single_source = distinct[0] if len(distinct) == 1 else None
    skipped = not files
    passed = not errors
    gate_passed = passed and (not warns if args.strict else True)

    result = {
        "passed": passed,
        "gate_passed": gate_passed,
        "strict": bool(args.strict),
        "skipped": skipped,
        "skip_reason": "未扫到任何前端源码" if skipped else None,
        "repo_root": str(root),
        "scanned_files": len(files),
        "entry_symbols": symbols,
        "hit_sites": len(entry_sites),
        "distinct_files": len(distinct),
        "distinct_file_list": distinct,
        "single_source": single_source,
        "allow_matched_files": allow_matched,
        "allow_unmatched_globs": allow_unmatched,
        "unregister_sites": unreg_sites,
        "skipped_large": oversized,
        "unreadable_files": unreadable,
        "errors": errors,
        "warns": warns,
    }

    for u in unreadable:
        sys.stderr.write("⚠️  文件不可读，未参与检查（不等于干净）：%s（%s）\n"
                         % (u["file"], u["error"]))
    for g in allow_unmatched:
        sys.stderr.write("⚠️  --allow 未匹配到任何入口命中所在文件，可能是写错了：%s\n" % g)
    # ⚠️ `--allow` 一个 glob 都没匹配上 → **入参错（2），不是判违规（1）**。
    #    glob 基准是仓库根：前端目录嵌在子路径下时写 'src/adapter.ts' 匹配不到，于是
    #    「全项目唯一那处合法信源」会被判成「平行于已声明信源」的 Critical —— 纯假红，
    #    且文案与事实完全相反。宁可报参数错，也不给出错误结论。
    if allow and not allow_matched:
        sys.stderr.write(
            "❌ --allow 的 glob 一个都没匹配上（基准是仓库根 %s，不是你传的扫描目录）。\n"
            "   请写成相对仓库根的路径，例如 '%s'。\n"
            % (root, (entry_sites[0]["file"] if entry_sites else "code/frontend/web/src/xxx.ts")))
        return 2

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        report(result)
    return 0 if gate_passed else 1


def report(r):
    print("=" * 68)
    print("维度 9 · WebMCP 前端能力实现合规（单一适配层 + unregisterTool）")
    print("=" * 68)
    if r["skipped"]:
        print("⏭️  未扫到任何前端源码，整维度跳过（不计入通过/不通过）")
        return
    print("扫描文件 %d 个 · 入口命中 %d 处 · 分布于 %d 个文件"
          % (r["scanned_files"], r["hit_sites"], r["distinct_files"]))
    print("入口标识符（由调用方传入）：%s" % "、".join(r["entry_symbols"]))
    if r["single_source"]:
        print("✅ 入口命中全部集中在同一个文件，认定为单一适配层：%s" % r["single_source"])
    for e in r["errors"]:
        print("\n🔴 %s:%d  [%s]" % (e["file"], e["line"], e["kind"]))
        if e.get("code"):
            print("   %s" % e["code"])
        print("   → %s" % e["reason"])
    for w in r["warns"]:
        print("\n🟡 %s  [%s]" % (w["file"], w["kind"]))
        print("   → %s" % w["reason"])
    print()
    print("闸门：%s（--strict=%s）" % ("通过" if r["gate_passed"] else "未通过", r["strict"]))
    print("⚠️  本脚本只做 9.1 单一适配层 + 9.2 的 unregisterTool 两项；时序、错误契约死文案、"
          "写操作通道、敏感值外泄、白名单四项须人工静态核对。")


if __name__ == "__main__":
    sys.exit(main())
