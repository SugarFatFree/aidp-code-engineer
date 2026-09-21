#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
第三方接口临时 Mock 运行时可控核验

对应 dev-logic-architect 核心原则 14「第三方接口临时 Mock 运行时可控原则」
+ QR 检查项 8「外部依赖与集成说明」mock 子项。

检测项:
1. 构建期守卫反模式(部署后 mock 失效,严禁出现在设计文档的正式代码示例中):
   - 前端: if (import.meta.env.DEV) / process.env.NODE_ENV === 'development'
           / 基于 NODE_ENV / DEV / PROD 常量的构建期判断
   - 后端: @Profile("dev") / @Profile("!prod") / #if DEBUG / #ifdef DEV
2. THIRD_PARTY_MOCK 标注块完整性:
   出现 THIRD_PARTY_MOCK: 的代码块必须在其后 8 行内含全部 6 个必填字段
   (vendor / api / since / expected_ready / owner / REMOVE_WHEN)
3. 运行时可控正向信号(信息项,不计违规):
   VITE_THIRD_PARTY_MOCK_ENABLED / third-party.mock.enabled /
   THIRD_PARTY_MOCK_ENABLED / @Value("${third-party.mock.enabled}")

豁免(两层,缺一不可):
- **块级**:文档中标注为反例的代码块(代码块前 5 行内出现 ❌ / 错误写法 / 反例 / 严禁的写法)
  本身就是用于教学的"错误示范",不计违规。
- **块内段级**:代码块**内部**以注释行写 `// ❌ …` 开启的反例段,直到出现 `✅ / 正确写法 / 推荐`
  注释行或代码块结束为止,整段豁免。
  ⚠️ **这一层是实测补上的、⛔ 勿删**:本 SKILL 自己的 `stack-react.md` / `stack-java-spring.md` /
  `stack-dotnet.md` 三份模板写的正是「块内 `// ❌ 构建期裁掉` + 下一行反模式代码 + `// ✅ 运行时开关`」
  这一形态——`❌` 在**块内**而不在块前 5 行,只有块级豁免时这三份模板 100% 假红(实测
  `check_third_party_mock_runtime.py references` → exit 1 / 7 处,其中 3 处正是它们)。
  设计文档的 A.2 mock 章节照抄这些模板,故真实产物同样会中招;
  而本仓库铁律是「假红常驻 = 硬门被绕过」。

另:`THIRD_PARTY_MOCK:` 标注块完整性只对**真正的标注行**判定——即该 token 之前只有空白与注释
符号(`// * # -- <!--`)。`if grep -r "THIRD_PARTY_MOCK:" src/` 这类**检索命令**里出现同名 token
不是标注块,不判缺字段(实测 `output-module-examples.md:585` 正是这一形态、原先被判死)。

用法:
  python check_third_party_mock_runtime.py <设计文档路径或目录>
  python check_third_party_mock_runtime.py <设计文档路径或目录> --json

退出码: 0 = 通过, 1 = 存在违规, 2 = 参数/路径错误

跨平台支持: Linux / macOS / Windows
"""

import json
import re
import sys
from pathlib import Path
from typing import Dict, List

# 构建期守卫反模式(命中即违规)
ANTI_PATTERNS = [
    (re.compile(r"import\.meta\.env\.DEV\b"), "前端构建期守卫 import.meta.env.DEV(production 构建被 tree-shake 裁掉)"),
    (re.compile(r"process\.env\.NODE_ENV\s*[=!]==?\s*['\"](development|production)['\"]"),
     "前端构建期守卫 NODE_ENV 常量判断(打包后被裁掉)"),
    (re.compile(r"@Profile\(\s*['\"](dev|!prod)['\"]\s*\)"), "后端构建期守卫 @Profile(prod profile 部署时 mock 类不加载)"),
    (re.compile(r"#\s*if\s+DEBUG\b"), "条件编译 #if DEBUG(编译期裁掉)"),
    (re.compile(r"#\s*ifdef\s+DEV\b"), "条件编译 #ifdef DEV(编译期裁掉)"),
]

# 运行时可控正向信号(信息项)
RUNTIME_OK_PATTERNS = [
    re.compile(r"VITE_THIRD_PARTY_MOCK_ENABLED"),
    re.compile(r"third-party\.mock\.enabled"),
    re.compile(r"THIRD_PARTY_MOCK_ENABLED"),
]

# ⚠️ Mock 有两个**目的相反**的场景,标记与守卫策略也相反,⛔ 不要混用
#    (单一信源:dev-execution-planner/references/flow-edge-cases.md 情况 0 / 情况 1):
#      THIRD_PARTY_MOCK(第三方未交付)  → **必须运行时开关**,要活到 UAT/Demo
#      DEV_MOCK(同项目后端未部署)      → **应当构建期裁掉**,绝不能进生产
#    故本脚本的「构建期守卫 = 违规」**只对 THIRD_PARTY_MOCK 成立**;
#    ⛔ 对 DEV_MOCK 判违规,等于要求作者去掉 tree-shake 守卫、把 dev mock 打进生产包。
MOCK_FIELDS_BY_KIND = {
    "THIRD_PARTY_MOCK": ["vendor", "api", "since", "expected_ready", "owner", "REMOVE_WHEN"],
    "DEV_MOCK": ["since", "owner", "REMOVE_WHEN"],
}
# THIRD_PARTY_MOCK 标注块必填字段(保留原名,供既有引用)
MOCK_FIELDS = MOCK_FIELDS_BY_KIND["THIRD_PARTY_MOCK"]

COUNTEREXAMPLE_RE = re.compile(r"❌|错误写法|错误示例|反例|严禁的写法|严禁示例")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
MOCK_TAG_RE = re.compile(r"(THIRD_PARTY_MOCK|DEV_MOCK)\s*:")
MOCK_TAG_TPM_RE = re.compile(r"THIRD_PARTY_MOCK\s*:")
MOCK_TAG_DEV_RE = re.compile(r"DEV_MOCK\s*:")

# 块内反例段:以注释行 `// ❌ …` 开启,遇 `✅ / 正确写法 / 推荐写法` 注释行或代码块结束时关闭。
# ⚠️ 只认**注释行**(行首除空白外以 // # * -- ; % 开头),避免把真代码行当成段落标记。
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
PROSE_PROHIBITION_RE = re.compile(r"反模式|严禁|禁止|⛔|不得|构建期守卫|判\s*Critical|判不通过")
COMMENT_LINE_RE = re.compile(r"^\s*(//+|#+|\*+|--|;+|%+|<!--)")
POSITIVE_RE = re.compile(r"✅|正确写法|正确示例|推荐写法|正例")

# 真正的标注行:token 之前只有空白与注释符号。
# `if grep -r "<marker>:" src/` 这类**检索命令**里的同名 token 不算标注块。
# >>> SHARED-SEGMENT: mock-marker-line >>>
# ── 标注行判定:前缀护栏 + 块注释状态机 ──────────────────────────────────────────
# ⚠️⚠️ **本段在 `code-verification-loop/scripts/scan_third_party_mock_antipatterns.py` 与
#      `dev-logic-architect/scripts/check_third_party_mock_runtime.py` 两处各持一份
#      **逐字节相同**的副本(遵 SKILL 独立性:不得跨 SKILL 引用)。改一处必须改另一处,
#      **连引号风格都要一致** —— 留出「哪天加一道机器门比对这两份副本」的余地。
#
# 判据:`标注行` == 前缀只由空白与注释符构成 **且**(前缀里真有注释符 **或** 本行处于块注释内)。
#
# ⚠️ **为什么不能只看前缀字符**:`^[\s/*#\-<!;%]*$` 允许**纯空白**前缀,
#    于是任何缩进层级的 Python 类型标注都通过 ——
#      `<marker>: bool = True`(顶格 / 函数内缩进 / 类内)三种全部被当成标注块,
#      判 `missing_fields`/**Critical**/exit 1 **打在一行完全正常的业务代码上**,
#      而作者除了改变量名无从修。`DEV_MOCK` 是个极自然的模块级常量名,量级不小。
#
# ⚠️ **为什么也不能干脆禁掉空前缀**:Java 块注释里**不带 `*` 续行符**的写法正是顶格无前缀 ——
#      /*
#      <marker>: 支付宝退款未交付
#      */
#    禁掉它,整块对本门**隐形**,方向从假阳翻成**假绿**(比假阳更难发现)。
#
# ⚠️ 故改用「**是否处于块注释内**」来区分这两类:Java 的那种写法在 `/* */` 里面,
#    而 Python 类型标注不在。该判据**不看描述内容**,没有误跳风险。
#    ⛔ 不要退回「靠正则识别 `NAME: type = value`」的方案:纯英文描述且首段恰好是
#    `标识符 = 值` 形态时(`<marker>: enabled = false until backend ships`)会被误跳,方向是假绿。
MARKER_PREFIX_OK_RE = re.compile(r"^[\s/*#\-<!;%]*$")
_BLOCK_COMMENT_PAIRS = (("/*", "*/"), ("<!--", "-->"))


def block_comment_flags(lines):
    """逐行标记「该行是否位于**行首形态**的块注释内」(开、闭行本身也算 True)。

    ★ 判据刻意**窄**:块注释只在「开标记前面全是空白」时才算开启,且**必须在文件内闭合**。
      两条闸门各自堵掉一类实测假阳,⛔ 放宽任一条都会让它们回来。

    ⚠️ **闸门一:开标记前必须全是空白**。否则任何**行中**出现的
       `/*` 都会开一个永不闭合的"块注释",其后所有零前缀行都变成"在块注释内" ——
       而 `/*` 在真实代码与文档里**极常见**,它就是 glob 路径 `src/*` / `dist/*` /
       `plugins/*/skills` 的一部分:
         · Python/Shell 行注释   `# 前端构建只扫 src/*.ts`
         · markdown 散文         `前端源码位于 src/*，产物在 dist/*。`
       实测这两种都会让其后的 `<marker>: bool = True` 被判 `missing_fields`/**Critical**
       并 exit 1 —— ⛔ **正是本护栏要消灭的那一类假阳,只是换了一扇门进来**。
       ⚠️ 逐字符的**引号状态机挡不住它们**(注释与散文里的 glob 本就不在引号内),
          本闸门**已完整覆盖**引号状态机原本负责的那个 case
          (`app.get('/*', h)` —— 该行 lstrip 后以 `app` 开头,同样不算开标记),
          故状态机已删除;⛔ 别再加回来当"双保险",那只会让人以为引号那条在起作用。

    ⚠️ **闸门二:未闭合的块不算块**。行首 `/*` 若直到文件结束都没有 `*/`,在真代码里是
       语法错、在文档里通常是被截断的片段;若照样认,它之后**整份文件**的零前缀行全部
       变成标注行(同样是 Critical 假阳)。故 EOF 时**回撤**该段 flags。

    ⚠️ 代价(登记在案,**不是**放宽判据的理由):**行中开启**的多行块注释
       (`foo(); /*` 换行后才写 marker)不被认,方向是假绿;该写法在真实标注块里没有
       出现过。本门要救的形态是开标记独占一行的那种 ——
         /*
         <marker>: 支付宝退款未交付
         */
       它的开标记前面只有空白、且必然闭合,两条闸门都不影响它。
    """
    flags = [False] * len(lines)
    open_tok = None
    open_from = -1
    for i, raw in enumerate(lines):
        if open_tok is not None:
            flags[i] = True
            close = dict(_BLOCK_COMMENT_PAIRS)[open_tok]
            if raw.find(close) < 0:
                continue
            open_tok = None
            open_from = -1
            continue
        stripped = raw.lstrip()
        hit = None
        for o, c in _BLOCK_COMMENT_PAIRS:
            if stripped.startswith(o):
                hit = (o, c)
                break
        if hit is None:
            continue
        o, c = hit
        flags[i] = True
        if raw.find(c, len(raw) - len(stripped) + len(o)) < 0:
            open_tok = o
            open_from = i
    if open_tok is not None:
        for k in range(open_from, len(lines)):
            flags[k] = False
    return flags


def is_marker_line(line, marker_match, in_block_comment):
    """该行的 marker 是不是**真正的标注行**(而非同名标识符 / 检索命令)。"""
    prefix = line[:marker_match.start()]
    if not MARKER_PREFIX_OK_RE.match(prefix):
        return False
    return bool(prefix.strip()) or in_block_comment
# <<< SHARED-SEGMENT: mock-marker-line <<<

# 兼容既有引用名(本文件内多处按旧名引用)
MOCK_TAG_PREFIX_OK_RE = MARKER_PREFIX_OK_RE


def iter_md_files(target: Path) -> List[Path]:
    if target.is_file():
        return [target] if target.suffix.lower() == ".md" else []
    return sorted(target.rglob("*.md"))


def scan_file(path: Path) -> Dict:
    """扫描单个 markdown 文件,返回违规与信息项"""
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    # ⚠️ 块注释状态必须**整份文件**算(含围栏内外),与 `is_marker_line` 配套使用;
    #    省掉它等于退回纯前缀判定 —— Python 类型标注 `<marker>: bool = True` 会被
    #    当成标注块判 Critical(实测顶格 / 函数内缩进 / 类内三种全中)。
    in_block_comment = block_comment_flags(lines)

    violations = []  # type: List[Dict]
    runtime_signals = 0
    mock_blocks = 0

    in_code = False
    block_is_counterexample = False
    in_counterexample_section = False  # 块内 `// ❌ …` 开启的反例段
    block_is_dev_mock_only = False     # 本代码块只含 DEV_MOCK 标注 → 构建期守卫是合规形态

    for idx, line in enumerate(lines):
        if FENCE_RE.match(line):
            if not in_code:
                # 进入代码块:检查前 5 行是否为反例标注
                context = "\n".join(lines[max(0, idx - 5):idx])
                block_is_counterexample = bool(COUNTEREXAMPLE_RE.search(context))
                # ⚠️ **前瞻本代码块到闭合围栏,判定它是哪一类 mock**。
                #    只有含 THIRD_PARTY_MOCK 标注的块才查构建期守卫;
                #    只含 DEV_MOCK 标注的块,构建期守卫正是**要求的合规形态**,⛔ 不判违规。
                #    实测:planner `flow-edge-cases.md:299-311` 的 ✅ 推荐写法被本脚本判违规
                #    → 设计文档照抄它即检查项 8 不通过,而"修法"会把 dev mock 送进生产。
                #    ⚠️ 两类同时出现时按 THIRD_PARTY_MOCK 从严 —— 混写本就该被指出来。
                #    ⚠️⚠️ **登记在案的局限**:「从严」的前提是**两个 token
                #    都在同一围栏内**。若 TPM 的标注写在围栏**外面的散文里**、围栏内只有 DEV_MOCK,
                #    则整块被豁免、该块里属于第三方 mock 的构建期守卫**逃检**(方向是假绿)。
                #    ⛔ 不要为此放宽豁免条件——那会把本门此次修复整个推翻;正解是协议本就要求
                #    标注块**随代码就地写在块内**(字段行紧随其后),标注跑到围栏外本身即不合规,
                #    由 mock_annotation_incomplete 与人工核对兜。
                #    另:围栏**未闭合**时前瞻会一路吃到文件末尾,该块的类型判定会被后文影响——
                #    属畸形文档,由分片时的「围栏配对检查」兜(见 AGENTS.md 分片范式)。
                blk = []
                for k in range(idx + 1, len(lines)):
                    if FENCE_RE.match(lines[k]):
                        break
                    blk.append(lines[k])
                blk_text = "\n".join(blk)
                block_is_dev_mock_only = (bool(MOCK_TAG_DEV_RE.search(blk_text))
                                          and not MOCK_TAG_TPM_RE.search(blk_text))
            in_code = not in_code
            in_counterexample_section = False  # 出入代码块都复位
            continue

        # 块内反例段状态机(只在代码块内的注释行上翻转)
        if in_code and COMMENT_LINE_RE.match(line):
            if COUNTEREXAMPLE_RE.search(line):
                in_counterexample_section = True
            elif POSITIVE_RE.search(line):
                in_counterexample_section = False

        # ⚠️ **散文禁令行护栏**:规范文档必然要**写出反模式本身**才能禁止它,
        #    而 QR 派发的 prompt 恰好放在一个**无语言标记的代码围栏**里 —— 于是
        #    `flow-qr-dispatch.md` 里那句列举「import.meta.env.DEV / @Profile("dev") / #if DEBUG
        #    判 Critical」的说明,被当成三处真违规(实测 3 条,全在同一行)。
        #    判据要两个条件**同时**成立才跳过,单独任一条都不够:
        #      ① 该行中文字符 ≥ 40 —— 真代码行不会有这么多中文(那一行有 1753 个,行长 4416);
        #      ② 含禁令/描述性词 —— 排除「代码行 + 一段长中文注释」这种理论上的巧合。
        #    ⛔ 不要放宽成「含禁令词就跳过」:那样「一边写 ⛔ 一边真在用」的代码行会蒙混过去
        #    (同 check_render_merge_table.py R5 与 check_error_contract.py C6/C7 的既有教训)。
        if in_code and PROSE_PROHIBITION_RE.search(line) and len(CJK_RE.findall(line)) >= 40:
            continue

        # 反模式检测(代码块内,非反例示范,且**该块不是纯 DEV_MOCK 块**)
        if (in_code and not block_is_counterexample and not in_counterexample_section
                and not block_is_dev_mock_only):
            for pattern, desc in ANTI_PATTERNS:
                if pattern.search(line):
                    violations.append({
                        "type": "build_time_guard",
                        "file": str(path),
                        "line": idx + 1,
                        "snippet": line.strip()[:120],
                        "issue": desc,
                    })

        # 正向信号统计(全文)
        for pattern in RUNTIME_OK_PATTERNS:
            if pattern.search(line):
                runtime_signals += 1
                break

        # THIRD_PARTY_MOCK 标注块完整性(全文,反例块豁免)
        # ⚠️ 只认真正的标注行:token 之前只有空白与注释符号;检索命令里的同名 token 不算
        m_tag = MOCK_TAG_RE.search(line)
        if (m_tag and is_marker_line(line, m_tag, in_block_comment[idx])
                and not (in_code and (block_is_counterexample or in_counterexample_section))):
            mock_blocks += 1
            kind = "THIRD_PARTY_MOCK" if MOCK_TAG_TPM_RE.search(line) else "DEV_MOCK"
            window = "\n".join(lines[idx:idx + 9])
            missing = [f for f in MOCK_FIELDS_BY_KIND[kind]
                       if not re.search(r"\b" + re.escape(f) + r"\b", window)]
            if missing:
                violations.append({
                    "type": "mock_annotation_incomplete",
                    "file": str(path),
                    "line": idx + 1,
                    "kind": kind,
                    "snippet": line.strip()[:120],
                    "issue": kind + " 标注块缺少必填字段: " + ", ".join(missing),
                })

    return {
        "file": str(path),
        "violations": violations,
        "runtime_signals": runtime_signals,
        "mock_blocks": mock_blocks,
    }


def main() -> int:
    argv = sys.argv[1:]
    if not argv or "-h" in argv or "--help" in argv:
        print("用法: python check_third_party_mock_runtime.py <设计文档路径或目录> [--json]")
        return 0 if argv else 2

    as_json = "--json" in argv
    paths = [a for a in argv if not a.startswith("-")]
    if not paths:
        print("错误: 缺少设计文档路径", file=sys.stderr)
        return 2
    target = Path(paths[0])
    if not target.exists():
        print("错误: 路径不存在: {}".format(target), file=sys.stderr)
        return 2

    files = iter_md_files(target)
    results = [scan_file(f) for f in files]
    all_violations = [v for r in results for v in r["violations"]]
    total_mock_blocks = sum(r["mock_blocks"] for r in results)
    total_runtime_signals = sum(r["runtime_signals"] for r in results)
    passed = not all_violations

    if as_json:
        print(json.dumps({
            "target": str(target),
            "files_scanned": len(files),
            "mock_blocks": total_mock_blocks,
            "runtime_signals": total_runtime_signals,
            "violation_count": len(all_violations),
            "passed": passed,
            "violations": all_violations,
            "principle_ref": "dev-logic-architect/SKILL.md 核心原则 14",
        }, ensure_ascii=False, indent=2))
        return 0 if passed else 1

    print("第三方接口临时 Mock 运行时可控核验")
    # ⚠️ 标签写「mock 标注块」不写「THIRD_PARTY_MOCK 标注块」:起 DEV_MOCK 也计入
    #    这个计数器，沿用旧标签会让读者按 TPM 数量去对账（实测 planner 目录 3 → 5，多出的 2 个是
    #    DEV_MOCK），把「新增了两个第三方 mock」这种不存在的结论读出来。`--json` 的键名 mock_blocks
    #    本就是中性的，⛔ 不要为对齐标签去改它（那是对外契约）。
    print("扫描文件数: {} | mock 标注块(THIRD_PARTY_MOCK + DEV_MOCK): {} | 运行时开关信号: {}".format(
        len(files), total_mock_blocks, total_runtime_signals))
    if passed:
        print("✅ 通过: 未发现构建期守卫反模式与标注块缺字段问题")
        return 0
    print("❌ 不通过: 发现 {} 处违规".format(len(all_violations)))
    for v in all_violations:
        print("  - [{}] {}:{} {}".format(v["type"], v["file"], v["line"], v["issue"]))
        print("    > {}".format(v["snippet"]))
    print()
    print("修复建议: mock 开关必须运行时可控(环境变量/配置文件 + 运行时 if 分支),")
    print("详见 dev-logic-architect/SKILL.md 核心原则 14「第三方接口临时 Mock 运行时可控原则」")
    return 1


if __name__ == "__main__":
    sys.exit(main())
