#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""样式重构编译等价性对照 — code-verification-loop 维度 14

**要解决的事**:样式**重构**(抽公共 / 参数化 / 移动位置)的正确性若无本门则**零覆盖**。
`vue-tsc` 与 `eslint` **都不编译 `<style>` 块**(维度 7 的 🎯 已点明),而
「类型检查过了」对样式**毫无意义**——这是使用者最容易误采信的一句话。

重构的定义就是**产物不变**,所以:

    改动前样式段 → 预处理器编译 → old.css
    改动后样式段 → 预处理器编译 → new.css
    归一 + 排序 + diff  ⇒ 要求【零差异】

本脚本只做**归一 + 比较 + 基线有效性判定**这一段(纯标准库);**两次编译由调用方用被测项目
自己的 `./node_modules/.bin/sass` / `lessc` / `stylus` 产生**,⛔ 不联网装、不全局装、不打包、
不起任何服务——与本 SKILL「全程静态」的最高约束一致。

⚠️ **基线有效性判定(本脚本的第二个职责,别当附属功能)**:
   下游真实失效——用 `git stash` 取基线时把验证依赖的**未跟踪配置文件**一起带走了,
   **基线那次实际没跑起来**,却产出了一个看似正常的基线文件,差点把假的「错误变少了」
   当成好消息接受。故本脚本对**空 / 疑似未执行**的基线**拒绝比较、按 exit 2 返回**,
   ⛔ 绝不给出一个差值——与本 SKILL 反复强调的「失效形态是 0 命中假绿」同源。
   ⚠️ **exit 2 的语义是「入参/环境错、须修好再跑」,不是「通过」**,调用方不得当成 0 处理。

归一规则(**保守**:只做能保证语义等价的变换,拿不准就不动):
  - 去掉 CSS 注释 `/* ... */`(它们不影响渲染,但**会被编译进产物**——维度 14 的配套判据正是
    「公共样式文件的文档注释必须用 `//`」,块注释进产物是缺陷本身,故比较时先剥掉、
    由**另一条判据**去管它,不要让它把整份 diff 淹掉)
  - 压缩空白(连续空白 → 单空格;`{`/`}`/`;`/`:`/`,` 周边空白去掉)
  - 数值单位等价形式:`0px`/`0em`/`0rem`/`0pt`/`0vh`/`0vw` → `0`;`.5` → `0.5`;十六进制颜色统一小写
    ⚠️ **`0%` 刻意不归一**(它在 `@keyframes` 里是**选择器**、在 `flex-basis` 上与 `0` 有已知行为差异,
       归一掉就可能掩盖真差异);**`0s` / `0ms` 更不能归一**(时间单位不可省,`transition:0` 无效)。
    ⚠️ **`#abc` 与 `#aabbcc` 刻意不归一**——等价但保守不动,方向是假红(人看一眼即排除),
       与本脚本「拿不准就不动」一致。
  - **按规则块排序**后比较——重构常见的合法变化就是「顺序变了」。⚠️ 但 CSS 有**层叠**语义,
    同选择器同属性时后写的胜出,**排序会掩盖这类真差异**;故默认**同时**给出
    「排序后是否等价」与「原序是否等价」两个结论:原序不等价而排序后等价 = **仅顺序变化**,
    报 Important 让人确认,⛔ 不当作通过。

用法:
    python3 check_css_equivalence.py <old.css> <new.css> [--json]

退出码:
    0 = 等价(原序即等价)
    1 = 有差异(含「仅顺序变化」——它只是 Important,但仍然占退出码 1,因为需要人确认)
    2 = 入参或环境错:路径不存在 / 不可读 / **基线无效**(空文件、只有空白、
        不含任何 `{` 因而不像 CSS 产物、或首行是编译/命令报错)
    ⚠️ **本脚本没有 N/A 跳过分支**:两侧都空 = 两次编译都没跑起来,恰恰是本脚本要拦的形态,
       按 exit 2 返回而**不是** exit 0。故 `--json` 里没有也不需要 `skipped` 字段
       (基线无效时出 `baseline_valid: false` + `reason`,与「真通过」判然可分)。

仅依赖 Python 3.8+ 标准库。
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import List

COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
# 「基线其实没跑起来」的信号。⚠️⚠️ **判据必须行首锚定、且只看头几行非空行**,
#    ⛔ 绝不能拿这些词去全文子串匹配 —— 裸子串匹配会把
#    `.error:hover{color:red}` 这种**再普通不过的 CSS 选择器**判成「无效基线」并 exit 2,
#    而 exit 2 的语义是「修好再来」、调用方无从修 → 整个维度 14 静默消失(假红比假绿更隐蔽:
#    它看起来像脚本在尽责)。`content:"数据不存在"` 同理被 `不存在` 命中。
#    口径:编译器/shell 的报错**总是打在产物开头**,故只查前几行的行首。
INVALID_BASELINE_RE = re.compile(
    r"^\s*(?:Error|error|SyntaxError|Traceback|npm ERR!|Exception)\b"
    r"|^[^\n]{0,80}?(?:command not found|No such file or directory|"
    r"[Cc]annot find module|Permission denied)")
# 一份合法的 CSS 产物必然至少有一个 `{`(纯 `@charset`/`@import` 的产物极罕见,
# 且那种基线本身就该复核)。报错文本几乎不会有 `{`,故这条是最稳的「不像产物」判据。
BRACE_RE = re.compile(r"\{")


def normalize(css: str) -> str:
    s = COMMENT_RE.sub("", css)
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s*([{};:,>])\s*", r"\1", s)
    # 0 值单位归一(只处理紧跟在 `:` 或空格后的独立 0)。
    # ⚠️ `%` 不在其中(见 docstring):它在 @keyframes 里是选择器;`s`/`ms` 更不可省。
    s = re.sub(r"(?<=[:\s(,])0(?:px|em|rem|pt|vh|vw)\b", "0", s)
    # `.5` → `0.5`
    s = re.sub(r"(?<=[:\s(,])\.(\d)", r"0.\1", s)
    # 十六进制颜色小写
    s = re.sub(r"#([0-9A-Fa-f]{3,8})\b", lambda m: "#" + m.group(1).lower(), s)
    # ⚠️ 末尾分号必须去掉:`margin:0;}` 与 `margin:0}` 语义完全相同,而压缩器一个留一个不留,
    #    不归一会让**每一条规则**都报差异 —— 整份 diff 变成噪声,真差异就淹没了(实测第一次就踩到)。
    s = re.sub(r";+\s*}", "}", s)
    return s.strip()


def split_rules(norm: str) -> List[str]:
    """按顶层 `}` 切成规则块(足够粗但稳定;嵌套已由预处理器展平)。"""
    out, depth, buf = [], 0, []
    for ch in norm:
        buf.append(ch)
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth <= 0:
                depth = 0
                piece = "".join(buf).strip()
                if piece:
                    out.append(piece)
                buf = []
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out


def baseline_invalid_reason(path: Path, raw: str) -> str:
    if raw.strip() == "":
        return "文件为空(0 字节或只有空白)——基线那次很可能根本没执行"
    # 只查**前 5 行非空行的行首**:编译器与 shell 的报错总在产物开头,
    # 而 CSS 正文里的 `.error:hover` / `content:"数据不存在"` 不会落在行首关键字上。
    head = [ln for ln in raw.split("\n") if ln.strip()][:5]
    for ln in head:
        m = INVALID_BASELINE_RE.search(ln)
        if m:
            return ("开头出现「%s」这类未执行/报错信号,不是一份合法的 CSS 产物"
                    % m.group(0).strip()[:60])
    if not BRACE_RE.search(raw):
        return "整份产物里一个 `{` 都没有——不像编译出来的 CSS,基线那次很可能没跑起来"
    return ""


def main() -> int:
    ap = argparse.ArgumentParser(description="样式重构编译等价性对照(cvl 维度 14)")
    ap.add_argument("old", help="改动前样式段编译出的 CSS")
    ap.add_argument("new", help="改动后样式段编译出的 CSS")
    ap.add_argument("--json", action="store_true", help="输出 JSON(供 Agent 解析)")
    args = ap.parse_args()

    p_old, p_new = Path(args.old), Path(args.new)
    for p in (p_old, p_new):
        # ⚠️ exists() 与 is_file() 分开判(全仓退出码约定第 2 条)。
        if not p.exists():
            print("路径不存在: %s" % p, file=sys.stderr)
            return 2
        if not p.is_file():
            print("不是文件: %s" % p, file=sys.stderr)
            return 2
    try:
        raw_old = p_old.read_text(encoding="utf-8", errors="replace")
        raw_new = p_new.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        print("读文件失败: %s" % e, file=sys.stderr)
        return 2

    # ── 基线有效性判定(先于一切比较) ─────────────────────────────
    reason = baseline_invalid_reason(p_old, raw_old)
    if reason:
        msg = ("⛔ 基线无效,拒绝比较:%s(%s)\n"
               "   下游真实失效:`git stash` 取基线时把未跟踪的配置文件一起带走了,基线那次没跑起来,\n"
               "   却产出一个看着正常的基线 —— 差点把假的「错误变少了」当成好消息接受。\n"
               "   ⚠️ 本次返回 exit 2 = 入参/环境错,**不是通过**;先把基线跑对再来。" % (reason, p_old))
        print(msg, file=sys.stderr)
        if args.json:
            print(json.dumps({"baseline_valid": False, "reason": reason,
                              "old": str(p_old), "new": str(p_new)}, ensure_ascii=False))
        return 2
    reason_new = baseline_invalid_reason(p_new, raw_new)
    if reason_new:
        print("⛔ 改动后的产物无效,拒绝比较:%s(%s)" % (reason_new, p_new), file=sys.stderr)
        if args.json:
            print(json.dumps({"baseline_valid": False, "reason": reason_new,
                              "old": str(p_old), "new": str(p_new)}, ensure_ascii=False))
        return 2

    n_old, n_new = normalize(raw_old), normalize(raw_new)
    same_order = n_old == n_new
    r_old, r_new = split_rules(n_old), split_rules(n_new)
    same_sorted = sorted(r_old) == sorted(r_new)

    # ⚠️ 必须按**多重集**求差,⛔ 不能写成 `[x for x in r_old if x not in r_new]`:
    #    同一条规则出现两次 vs 一次时,那种写法两侧都得空列表,于是报告只印一句
    #    「有差异」却一条都列不出来 —— 有结论没证据,排查无从下手(实测 dup-rule fixture)。
    c_old, c_new = Counter(r_old), Counter(r_new)
    only_old = list((c_old - c_new).elements())
    only_new = list((c_new - c_old).elements())

    if args.json:
        print(json.dumps({
            "baseline_valid": True, "equivalent": same_order,
            "equivalent_ignoring_order": same_sorted,
            "order_only_change": (not same_order) and same_sorted,
            "rules_old": len(r_old), "rules_new": len(r_new),
            "only_in_old": only_old[:50], "only_in_new": only_new[:50],
            "old": str(p_old), "new": str(p_new),
        }, ensure_ascii=False, indent=2))
        return 0 if same_order else 1

    print("规则块:改动前 %d 条 / 改动后 %d 条" % (len(r_old), len(r_new)))
    if same_order:
        print("✅ 编译产物等价(归一后逐字一致)—— 本次样式重构未改变产物")
        return 0
    if same_sorted:
        print("🟡 [Important] **仅顺序变化**:排序后等价、原序不等价。")
        print("   ⚠️ CSS 有**层叠**语义——同选择器同属性时后写的胜出,顺序变化可能是真差异;")
        print("      请逐条确认这些块之间没有覆盖关系,⛔ 不得直接当作通过。")
        return 1
    print("🔴 [Critical] 编译产物有差异,本次样式重构改变了产物:")
    for x in only_old[:20]:
        print("  - 仅出现在改动前: %s" % (x[:160]))
    for x in only_new[:20]:
        print("  + 仅出现在改动后: %s" % (x[:160]))
    if len(only_old) > 20 or len(only_new) > 20:
        print("  …(还有 %d 条未列出)" % (max(0, len(only_old) - 20) + max(0, len(only_new) - 20)))
    print("\n每一条差异要么由本次改动的意图解释、并写进报告,要么就是缺陷。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
