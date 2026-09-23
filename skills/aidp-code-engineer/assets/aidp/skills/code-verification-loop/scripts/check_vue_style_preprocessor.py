#!/usr/bin/env python3
"""
check_vue_style_preprocessor.py — Vue SFC `<style lang>` 与预处理器依赖一致性（维度 7 硬门）

补的盲区：`vue-tsc --noEmit` 与 `eslint` **都不编译 .vue 的 `<style>` 块**。
于是「预处理器没装 / lang 写错 / 用了全库都不用的另一种」这一整类问题，在开发期
轻量验证里 **100% 静默通过**，只有部署期 `vite build` 才炸（`loadSassPackage` 之类）。
反馈周期是「提交 → 推送 → CI → 构建失败」，而它本可被一次纯静态比对拦下。

> 这里**不主张**把完整构建塞进开发期（那条规定是对的）。本脚本零构建、零安装、
> 纯读文件，成本与一次 grep 同量级。

判定：
  1. 抽取每个**顶层** `<style ... lang="X">` 的 X（无 lang / lang=css 视为原生 CSS，跳过）
  2. X → 所需 npm 包候选：scss·sass → sass | sass-embedded | node-sass；
     less → less；styl·stylus → stylus
  3. 从该 .vue **就近向上**找 package.json（一路找到 git 根，兼容 monorepo 依赖提升），
     合并各层 dependencies / devDependencies / optionalDependencies
  4. 候选包一个都没声明 → **ERROR**（CI 构建必失败，阻塞级，退出码 1）
     已声明但与全库众数 lang 不一致（孤例）→ **WARN**（疑似写错，不阻断）

**不覆盖的项（须人工核验，勿当已查）**：`@import` / `@use` 路径是否存在、预处理器
`api`/`silenceDeprecations` 等 vite 配置、预处理器插件（`less-loader` 之类构建链）。
本脚本只回答一件事：`<style lang>` 声明的预处理器**有没有被 package.json 声明**。

误报控制（误报会阻塞发布，成本高，故一律按精度优先处理）：
  - HTML 注释 `<!-- <style lang="scss"> -->` 内的伪 style 块不参与判定
  - `<script>` 内字符串里的 `'<style lang="scss">'` 不参与判定
  - `<template>` 内的 `<style>` 标签（非 SFC 顶层块）不参与判定
  - 只认**行首（列 0）**的顶层块起始标签，这是 Vue SFC 的既定写法；若某文件因缩进
    导致一个顶层块都没认出、而宽松扫描能扫到，则给 WARN 提示人工确认（不静默漏过）

退出码：0 = 无 ERROR（`--strict` 时还须无 WARN）；1 = 未通过；2 = 输入错误
"""

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# lang → 满足它的 npm 包候选（命中任一即算已声明）
LANG_PACKAGES: Dict[str, Tuple[str, ...]] = {
    "scss": ("sass", "sass-embedded", "node-sass"),
    "sass": ("sass", "sass-embedded", "node-sass"),
    "less": ("less",),
    "styl": ("stylus",),
    "stylus": ("stylus",),
}
# 原生 CSS，不需要任何预处理器
NATIVE_LANGS = {"", "css", "postcss"}

# SFC 顶层块起始标签：必须**独占一行的开头**（允许缩进——实测真实项目里确有缩进写法）。
# 属性可跨行（`[^>]` 含换行），属性顺序任意。
TOP_BLOCK_OPEN_RE = re.compile(r"^[ \t]*<(template|script|style)\b([^>]*)>",
                               re.IGNORECASE | re.MULTILINE)
# 宽松扫描：仅用于「一个顶层块都没认出」时的兜底提示，不直接参与判定
LOOSE_STYLE_RE = re.compile(r"<style\b([^>]*)>", re.IGNORECASE)
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
ATTR_NAME_RE = re.compile(r"[^\s=/>]+")
BARE_VALUE_RE = re.compile(r"[^\s>]*")

DEP_FIELDS = ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies")


def find_git_root(start: Path) -> Path:
    """从 start（目录；给文件则取其父目录）向上找 .git，找不到返回起点目录。"""
    cur = start.resolve()
    if cur.is_file():
        cur = cur.parent
    origin = cur
    for _ in range(30):
        if (cur / ".git").exists():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return origin


def collect_declared_deps(vue_file: Path, stop_at: Path) -> Tuple[Set[str], List[str]]:
    """就近向上收集 package.json 里声明的依赖名。

    monorepo 常把 sass/less 提到根 package.json（依赖提升），只看最近那份会误报，
    故一路向上合并到 git 根为止。返回 (依赖名集合, 读到的 package.json 路径列表)。
    """
    deps: Set[str] = set()
    seen: List[str] = []
    cur = vue_file.parent.resolve()
    stop = stop_at.resolve()
    # stop 必须是本文件的祖先；否则（一次给了跨仓库的多个目标）退回本文件自己的 git 根，
    # 免得一路走到文件系统根、把项目外无关的 package.json 也合并进来。
    if stop != cur and stop not in cur.parents:
        stop = find_git_root(cur)
    for _ in range(30):
        pkg = cur / "package.json"
        if pkg.is_file():
            try:
                data = json.loads(pkg.read_text(encoding="utf-8", errors="replace"))
            except (ValueError, OSError):
                data = {}
            if isinstance(data, dict):
                for field in DEP_FIELDS:
                    section = data.get(field)
                    if isinstance(section, dict):
                        deps.update(section.keys())
            seen.append(str(pkg))
        if cur == stop or cur.parent == cur:
            break
        cur = cur.parent
    return deps, seen


def _blank_out(text: str, pattern: re.Pattern) -> str:
    """把匹配段落替换成等长空白（保留换行），从而行号/偏移全部不变。"""
    return pattern.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


def parse_attrs(attrs: str) -> Dict[str, str]:
    """按属性逐个切分（会正确消费掉引号内的内容）。

    不能直接用正则在整串上 search `lang=` —— `<style data-x="lang=scss">` 会被
    误当成 `lang="scss"`，进而误报一个 🔴 阻塞级问题。
    """
    out: Dict[str, str] = {}
    s = attrs or ""
    i, n = 0, len(s)
    while i < n:
        if s[i].isspace() or s[i] in "/>":
            i += 1
            continue
        nm = ATTR_NAME_RE.match(s, i)
        if not nm:
            i += 1
            continue
        name = nm.group(0).lower()
        i = nm.end()
        j = i
        while j < n and s[j].isspace():
            j += 1
        value = ""
        if j < n and s[j] == "=":
            j += 1
            while j < n and s[j].isspace():
                j += 1
            if j < n and s[j] in "\"'":
                quote = s[j]
                k = s.find(quote, j + 1)
                if k == -1:
                    k = n
                value = s[j + 1:k]
                i = k + 1
            else:
                vm = BARE_VALUE_RE.match(s, j)
                value = vm.group(0)
                i = vm.end()
        else:
            i = j
        out[name] = value
    return out


def _lang_of(attrs: str) -> str:
    return parse_attrs(attrs).get("lang", "").strip().lower()


def _skip_block(src: str, start: int, tag: str) -> int:
    """返回 `tag` 块结束后的偏移。

    `<template>` 可以嵌套（`<template #slot>`），必须按深度配对，否则会在第一个内层
    `</template>` 处提前收尾、把 template 体内剩下的 `<style>` 当成顶层块。
    """
    if tag == "template":
        pair = re.compile(r"<template\b[^>]*>|</\s*template\s*>", re.IGNORECASE)
        depth = 1
        pos = start
        while depth > 0:
            m = pair.search(src, pos)
            if not m:
                return len(src)
            depth += -1 if m.group(0).lstrip("<").lstrip().startswith("/") else 1
            pos = m.end()
        return pos
    close = re.compile(r"</\s*%s\s*>" % tag, re.IGNORECASE)
    cm = close.search(src, start)
    return cm.end() if cm else len(src)


def extract_style_langs(text: str) -> Tuple[List[Tuple[str, int]], bool]:
    """返回 ([(lang, 行号)], 是否有 <style> 标签一个顶层块都没认出来)。

    只认 **SFC 顶层块**：独占一行开头的 `<template>/<script>/<style>` 起始标签，
    并整段跳过 template/script 区域。这样注释里、`<script>` 字符串里、`<template>`
    内部的 `<style ...>` 都不会被误当成真的样式块 —— 这三类误报都是 🔴 阻塞级，
    一旦发生会直接卡住发布，成本远高于偶尔漏一个。
    """
    src = _blank_out(text, HTML_COMMENT_RE)
    out: List[Tuple[str, int]] = []
    pos = 0
    while True:
        m = TOP_BLOCK_OPEN_RE.search(src, pos)
        if not m:
            break
        tag = m.group(1).lower()
        attrs = m.group(2) or ""
        line = src[: m.start()].count("\n") + 1
        if tag == "style":
            out.append((_lang_of(attrs), line))
        if attrs.rstrip().endswith("/"):  # 自闭合 <style ... />
            pos = m.end()
            continue
        pos = _skip_block(src, m.end(), tag)

    # 兜底：整个文件一个顶层块都没认出、但宽松扫描能扫到 <style> —— 多半是写法不常规
    # （如整体缩进）。不静默漏过，交由调用方提示人工确认。
    suspicious = not out and bool(LOOSE_STYLE_RE.search(src))
    return out, suspicious


def iter_vue_files(targets: List[str]) -> List[Path]:
    files: List[Path] = []
    for t in targets:
        p = Path(t)
        if p.is_dir():
            files.extend(x for x in p.rglob("*.vue") if "node_modules" not in x.parts)
        elif p.is_file() and p.suffix == ".vue":
            files.append(p)
    # 去重且保持稳定顺序
    seen, uniq = set(), []
    for f in files:
        r = f.resolve()
        if r not in seen:
            seen.add(r)
            uniq.append(f)
    return uniq


def compute_majority_lang(root: Path) -> Tuple[Optional[str], Counter]:
    """全库众数 lang —— 判「孤例」用的基线。

    只统计**需要预处理器**的 lang：原生 CSS 与众数之争无关，混进来会稀释口径。
    """
    counter: Counter = Counter()
    for f in root.rglob("*.vue"):
        if "node_modules" in f.parts:
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lang, _ in extract_style_langs(text)[0]:
            if lang and lang not in NATIVE_LANGS:
                counter[lang] += 1
    if not counter:
        return None, counter
    return counter.most_common(1)[0][0], counter


def analyze(targets: List[str], baseline_root: Optional[Path]) -> Dict:
    files = iter_vue_files(targets)
    first = Path(targets[0]) if targets else Path(".")
    git_root = find_git_root(first if first.exists() else Path("."))
    root = baseline_root or git_root
    majority, dist = compute_majority_lang(root)

    errors: List[Dict] = []
    warns: List[Dict] = []
    checked = 0

    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            warns.append({"file": str(f), "line": 0, "lang": "",
                          "msg": f"读取失败，跳过：{e}"})
            continue
        langs, suspicious = extract_style_langs(text)
        if suspicious:
            warns.append({
                "file": str(f), "line": 0, "lang": "",
                "msg": "文件里有 <style> 标签，但没有一个位于 SFC 顶层（行首）——"
                       "写法不常规，本脚本不参与判定，请人工确认其 lang 与依赖是否匹配",
            })
        if not langs:
            continue
        deps, pkgs = collect_declared_deps(f, git_root)
        for lang, line in langs:
            if lang in NATIVE_LANGS:
                continue
            checked += 1
            candidates = LANG_PACKAGES.get(lang)
            if candidates is None:
                warns.append({
                    "file": str(f), "line": line, "lang": lang,
                    "msg": f"未知的 style lang「{lang}」——本脚本不认识它需要哪个预处理器，请人工确认",
                })
                continue
            hit = [c for c in candidates if c in deps]
            if not hit and not pkgs:
                # ⚠️ **一份 package.json 都没读到 ≠ 都没声明**,不得判 Critical(假红阻断)。
                #    `find_git_root()` 找不到 `.git` 时返回起点目录,`collect_declared_deps` 随即
                #    立刻停住 → `pkgs == []`。触发条件很常见:非 git 检出、zip/tar 解包的代码目录、
                #    导出产物目录,以及「传单个 .vue 文件列表」这一被报告模板推荐的形态
                #    (此时起点就是那个 .vue 的父目录)。实测同一份代码仅补一个 `.git` 目录即从
                #    ERROR 变全过 —— 判的是环境而不是产物。
                warns.append({
                    "file": str(f), "line": line, "lang": lang,
                    "required_any_of": list(candidates),
                    "package_json": pkgs,
                    "msg": f"<style lang=\"{lang}\"> 需要 {' 或 '.join(candidates)}，"
                           f"但**未找到任何 package.json**(git 根未找到,依赖解析范围受限)"
                           f" —— **本项判不了,不等于未声明**,请在能看到 package.json 的根目录重跑",
                })
                continue
            if not hit:
                errors.append({
                    "file": str(f), "line": line, "lang": lang,
                    "required_any_of": list(candidates),
                    "package_json": pkgs,
                    "msg": f"<style lang=\"{lang}\"> 需要 {' 或 '.join(candidates)}，"
                           f"但就近向上的 package.json 均未声明 —— CI 构建必失败",
                })
                continue
            if majority and lang != majority:
                warns.append({
                    "file": str(f), "line": line, "lang": lang,
                    "majority_lang": majority,
                    "msg": f"依赖已声明（{hit[0]}），但全库众数是「{majority}」"
                           f"（{dist.get(majority, 0)} 处 vs 本 lang {dist.get(lang, 0)} 处）—— "
                           f"孤例，疑似写错，请确认是否有意为之",
                })

    return {
        "passed": not errors,
        # 扫不到 .vue = 非 Vue 项目 → 整维度跳过（不计入通过/不通过）
        "skipped": not files,
        "scanned_files": len(files),
        "checked_style_blocks": checked,
        "majority_lang": majority,
        "lang_distribution": dict(dist),
        "baseline_root": str(root),
        "errors": errors,
        "warns": warns,
    }


def print_report(r: Dict) -> None:
    print("=" * 78)
    print("Vue SFC <style lang> 与预处理器依赖一致性（维度 7）")
    print("=" * 78)
    print(f"\n扫描 .vue：{r['scanned_files']} 个；需预处理器的 <style> 块：{r['checked_style_blocks']} 处")
    if r.get("skipped"):
        print("⏭️  未扫到任何 .vue —— 非 Vue 项目，维度 7 整维度跳过（不计入通过/不通过）")
    if r["majority_lang"]:
        dist = ", ".join(f"{k}×{v}" for k, v in sorted(r["lang_distribution"].items(),
                                                       key=lambda x: -x[1]))
        print(f"全库众数 lang：{r['majority_lang']}（分布：{dist}）")
    else:
        print("全库未发现需要预处理器的 <style> 块")
    print(f"ERROR {len(r['errors'])} · WARN {len(r['warns'])}\n")

    for e in r["errors"]:
        print(f"  🔴 {e['file']}:{e['line']}")
        print(f"       {e['msg']}")
        print(f"       修复：在对应 package.json 的 devDependencies 声明 "
              f"{e['required_any_of'][0]}，或把 lang 改为全库在用的那种")
    for w in r["warns"]:
        print(f"  🟡 {w['file']}:{w['line']}")
        print(f"       {w['msg']}")

    if r["passed"]:
        print("\n✅ 无阻塞级问题" + ("（另有 WARN 需确认）" if r["warns"] else ""))
    else:
        print(f"\n❌ {len(r['errors'])} 处预处理器未声明 —— CI 构建会失败，回 /sprint-bugfix")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Vue SFC <style lang> 与预处理器依赖一致性检查（纯静态，零构建）")
    ap.add_argument("targets", nargs="+",
                    help="本次改动涉及的 .vue 文件，或包含 .vue 的目录")
    ap.add_argument("--baseline-root", default=None,
                    help="计算「全库众数 lang」的根目录（默认自动探测 git 根）")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出供 Agent 解析")
    ap.add_argument("--strict", action="store_true", help="WARN 也计入失败")
    args = ap.parse_args(argv)

    missing = [t for t in args.targets if not Path(t).exists()]
    if missing:
        print(f"错误：路径不存在：{missing}", file=sys.stderr)
        return 2
    base = Path(args.baseline_root) if args.baseline_root else None
    if base is not None and not base.is_dir():
        print(f"错误：--baseline-root 不是目录：{base}", file=sys.stderr)
        return 2

    result = analyze(args.targets, base)
    # `passed` 恒为「无 ERROR」；`gate_passed` 才是本次退出码对应的闸门结论
    # （--strict 下 WARN 也算不通过）。二者分开，免得 JSON 消费方读 passed 得出
    # 与退出码相反的结论。
    result["strict"] = bool(args.strict)
    result["gate_passed"] = not result["errors"] and not (args.strict and result["warns"])
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_report(result)

    return 0 if result["gate_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
