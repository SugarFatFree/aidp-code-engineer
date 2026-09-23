#!/usr/bin/env python3
"""
临时 Mock 反模式扫描器（THIRD_PARTY_MOCK / DEV_MOCK 两类，判据按类型分流）

⚠️ **先读这一段：两类 mock 的守卫策略是相反的，⛔ 不要混用。**
   单一信源：`dev-execution-planner/references/flow-edge-cases.md` 情况 0 / 情况 1。

   | 标记             | 场景             | 守卫期望                             | 必填字段 |
   | THIRD_PARTY_MOCK | 第三方未交付     | **必须运行时开关** —— 要活到 UAT/Demo | vendor/api/since/expected_ready/owner/REMOVE_WHEN |
   | DEV_MOCK         | 同项目后端未部署 | **应当构建期裁掉** —— 绝不能进生产    | since/owner/REMOVE_WHEN |

   **本脚本的「构建期守卫 = Critical」只对 THIRD_PARTY_MOCK 成立。**
   对 DEV_MOCK，`import.meta.env.DEV` 这类构建期守卫正是要求的合规形态；
   反过来，DEV_MOCK 用运行时开关才该提示（那意味着它在生产有机会被打开）。

检测项：
1. 构建期守卫反模式（前端 DEV guard / 后端 @Profile）—— **仅对含 THIRD_PARTY_MOCK 标注块的文件判违规**
   （不以「文件含 mock 字样」为门控：DEV_MOCK 文件必然含 "mock" 字样，
    那样会把它要求的合规守卫判 Critical，且修复建议会把 dev mock 打进生产包）
   **两类标注块并存于同一文件时按「行距最近的标注块（双向）」逐处归属**，
   归 DEV_MOCK 的守卫跳过；前面没有任何块时回退文件级判违规。判据详见 scan_file() 内注释。
2. 真实对接后残留（全仓任一真实 SDK/client 信号、后端配置真实 base URL（.yml/.properties，保守认厂商生产域名 / base-url 真实 https）、或 .env baseURL 已切真实地址但 mock 开关仍为 true，与 **THIRD_PARTY_MOCK** 标注块并存）
3. Mock 兜底调用（catch / || / default 分支）
4. 标注块字段缺失（两类各按自己的必填字段集；兼容 //、#、* 注释风格）
5. THIRD_PARTY_MOCK 的 expected_ready 过期（默认 14 天容忍，--max-overdue-days 可调）
6. DEV_MOCK 按 since 计龄超阈值 → Important（同项目内没有 expected_ready 这个概念）
7. DEV_MOCK 出现运行时 mock 开关 → Important（反向判据，它本该被构建期裁掉）
8. 标注合规的临时 mock 以 Important 级列为"合规但待 follow-up"（--strict 时返回非零退出码）

**不归本脚本管**：没有任何标记的 mock 数据残留 —— 那由维度 2A 的 `scan_mock_data.py`
（普通 mock 零容忍）承担。本脚本管的是「**已声明**的临时 mock 合不合协议」。

用法（示例命令用裸 python，与全仓惯例一致）：
  python scan_third_party_mock_antipatterns.py src/
  python scan_third_party_mock_antipatterns.py src/ --json
  python scan_third_party_mock_antipatterns.py src/ --strict           # Important 也返回非零
  python scan_third_party_mock_antipatterns.py src/ --max-overdue-days 14

退出码（遵全仓统一约定；⚠️ 严重度分档一律走 --json，不占退出码）：
  0  无 Critical（--strict 下还需无 Important：合规待 follow-up + dev_mock_stale + dev_mock_runtime_switch）
  1  存在 Critical（构建期守卫 / 真实对接后残留 / 兜底 / 字段缺失 / 过期），或 --strict 且有 Important
  2  入参错（路径不存在 / 传入的是文件而非目录）
     ⚠️ 本小节须与实现（`sys.exit(2)`）保持一致，调用方据此区分「入参错」与「检出违规」。

依赖：Python 3.8+ 标准库（跨平台 Linux / macOS / Windows）
"""

import re
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple, Set

# ============ 常量定义 ============

# 前端构建期守卫模式（严禁）
FRONTEND_BUILD_TIME_GUARDS = [
    r'import\.meta\.env\.DEV\b',
    r'process\.env\.NODE_ENV\s*===?\s*["\']development["\']',
    r'process\.env\.NODE_ENV\s*===?\s*["\']dev["\']',
    r'__DEV__\b',
    r'NODE_ENV\s*===?\s*["\']development["\']',
]

# 后端构建期守卫模式（严禁）
BACKEND_BUILD_TIME_GUARDS = [
    r'@Profile\s*\(\s*["\']dev["\']\s*\)',
    r'@Profile\s*\(\s*["\']!prod["\']\s*\)',
    r'#if\s+DEBUG',
    r'#ifdef\s+DEV',
]

# 运行时可控正确模式（应该使用）
FRONTEND_RUNTIME_PATTERNS = [
    r'import\.meta\.env\.VITE_THIRD_PARTY_MOCK_ENABLED',
    r'process\.env\.VITE_THIRD_PARTY_MOCK_ENABLED',
    r'process\.env\.REACT_APP_THIRD_PARTY_MOCK',
]

BACKEND_RUNTIME_PATTERNS = [
    r'@Value\s*\(\s*"\$\{third-party\.mock\.enabled',
    r'@Value\s*\(\s*"\$\{THIRD_PARTY_MOCK_ENABLED',
]

# ⚠️ Mock 有两个**目的相反**的场景,标记与守卫策略也相反,⛔ 不要混用
#    (单一信源:dev-execution-planner/references/flow-edge-cases.md 情况 0 / 情况 1):
#
#    | 标记              | 场景             | 守卫期望                              |
#    | THIRD_PARTY_MOCK  | 第三方未交付     | **必须运行时开关** —— 要活到 UAT/Demo  |
#    | DEV_MOCK          | 同项目后端未部署 | **应当构建期裁掉** —— 绝不能进生产     |
#
#    故本脚本的「构建期守卫 = Critical」**只对 THIRD_PARTY_MOCK 成立**。
#    对 DEV_MOCK,`import.meta.env.DEV` 这类构建期守卫正是**要求的合规形态**;
#    ⛔ 判它违规会让开发者去掉 tree-shake 守卫、把 dev mock 打进生产包 ——
#    恰好制造出本脚本本意要防的那类事故(planner `flow-edge-cases.md` 情况 1 的推荐写法
#    若被判 Critical + exit 1,修复建议正是「去掉那个守卫」)。
REQUIRED_FIELDS = ['vendor', 'api', 'since', 'expected_ready', 'owner', 'REMOVE_WHEN']
# 按标记类型取不同必填字段集。DEV_MOCK 是同项目内的临时拦截,没有"厂商 / 对方接口 /
# 对方交付日"这三个概念,故只要三字段。
REQUIRED_FIELDS_BY_KIND = {
    'THIRD_PARTY_MOCK': REQUIRED_FIELDS,
    'DEV_MOCK': ['since', 'owner', 'REMOVE_WHEN'],
}
# _FIELD_LINE 的字段全集(当前 DEV_MOCK 未引入新字段;取并集是为了以后加字段时不必两处改)
ALL_FIELDS = list(dict.fromkeys(
    [f for fields in REQUIRED_FIELDS_BY_KIND.values() for f in fields]))

# 真实 vendor SDK/client 信号（表示已开始对接）
VENDOR_SDK_PATTERNS = [
    r'import\s+.*\s+from\s+["\']@alipay/sdk["\']',
    r'import\s+com\.alipay\.api\.',
    r'import\s+com\.wechat\.pay\.',
    r'new\s+AlipayClient\s*\(',
    r'new\s+WechatPayClient\s*\(',
    r'RestTemplate.*alipay',
    r'FeignClient.*alipay',
]

# 后端真实对接信号(application.yml / *.properties / Java·Go 配置类等):
# 命中 = 已开始真实对接,与 THIRD_PARTY_MOCK 并存判 Critical(对接信号 2「真实 base URL 配置」)。
# 保守策略:只认"明确生产地址",排除 localhost/sandbox/mock/占位,宁可漏不可误。
# 信号 3「真实凭证(app.id/private.key)」误报风险高,本脚本不实现,仍需人工 grep。
REAL_VENDOR_DOMAIN_RE = re.compile(
    r'https?://(?:openapi\.alipay\.com|api\.mch\.weixin\.qq\.com|api\.weixin\.qq\.com|'
    r'gw\.api\.taobao\.com|(?:payment)?api\.unionpay\.com)',
    re.IGNORECASE,
)
# ⚠️ 前导**不能**写成 `[\w.\-]*`:它与紧随的 `base` 在「连续 word/点/横线长串」上产生
#    O(L²) 灾难性回溯,而本正则对**每个源文件**都跑(不限配置文件)。实测 60KB 内嵌 token
#    的单个 .ts 耗时 **32.5s**(同输入 scan_mock_data.py 仅 0.07s,差 460×),2MB 输入 >120s
#    不返回。本脚本是无人值守验收链路上的硬门禁,一个含长 token/证书/base64 串的文件
#    就能把整轮验收挂死。
#    修法是**直接去掉前导组**——`base[-_.]?url` 作为子串照样命中 `xxx.baseUrl` /
#    `third_party_base_url`,且无前导量词即无回溯。
#    ⚠️ 勿改成 `(?:^|[^\w.\-])base…` 这种边界断言:`third_party_base_url` 的 `base` 前面是
#       `_`(属 \w),会被断言挡掉 —— 那是**丢检出**,不是等价改写(本次修复中实际踩过)。
BACKEND_BASE_URL_RE = re.compile(
    r'base[-_.]?url\s*[:=]\s*["\']?(https?://[^"\'\s]+)', re.IGNORECASE,
)
_PLACEHOLDER_URL_HINT = re.compile(
    r'localhost|127\.0\.0\.1|0\.0\.0\.0|sandbox|mock|example\.com|test\.|\$\{|\{\{|<your|<vendor|占位|todo',
    re.IGNORECASE,
)


def find_real_backend_signal(content: str) -> bool:
    """后端真实对接信号:命中厂商生产域名,或 base-url 指向真实 https 地址(排除 localhost/sandbox/mock/占位)"""
    if REAL_VENDOR_DOMAIN_RE.search(content):
        return True
    for m in BACKEND_BASE_URL_RE.finditer(content):
        if not _PLACEHOLDER_URL_HINT.search(m.group(1)):
            return True
    return False

# ============ 核心函数 ============

# 标注块字段行前缀:支持 // 行注释、# 注释、Java 块注释 * 前缀
_FIELD_LINE = re.compile(
    r'^\s*(?://|#|\*)?\s*(' + '|'.join(ALL_FIELDS) + r')\s*[:：]\s*(.+?)\s*$'
)
# ⚠️ 两种 marker 分开识别,`_MARKER_LINE` 只用于"块与块之间的分界"(两类都算界)。
_MARKER_LINE_TPM = re.compile(r'(?://|#|\*|/\*\*?)?\s*THIRD_PARTY_MOCK\s*[:：]')
_MARKER_LINE_DEV = re.compile(r'(?://|#|\*|/\*\*?)?\s*DEV_MOCK\s*[:：]')
_MARKER_LINE = re.compile(r'(?://|#|\*|/\*\*?)?\s*(?:THIRD_PARTY_MOCK|DEV_MOCK)\s*[:：]')

# ⚠️ **标注行前缀护栏(⛔ 勿删)**:只有 token 之前**仅有空白与注释符号**
#    才算真正的标注行。没有它,`DEV_MOCK` 作为**普通标识符**出现就会被当成标注块:
#      TS   `const DEV_MOCK: boolean = import.meta.env.DEV`
#      Py   `DEV_MOCK: bool = True`
#      Go   `case DEV_MOCK:`  (switch 分支)
#    三种形态都命中 `DEV_MOCK\s*[:：]` → 凭空造出一个缺三字段的块 → **missing_fields/Critical
#    + exit 1,而那是一行完全正常的业务代码**,作者无从修(除非改变量名)。
#    `THIRD_PARTY_MOCK` 因 token 长、几乎不会被用作标识符,风险低;`DEV_MOCK` token 短
#    且是极自然的常量名,风险量级完全不同。
#    ⚠️ 判据与 `dev-logic-architect/scripts/check_third_party_mock_runtime.py` 的
#    `MOCK_TAG_PREFIX_OK_RE` **同款**(两个 SKILL 各持一份副本,遵独立性原则)。
#    代价(已知且接受):行尾注释形态 `const x = 1; // DEV_MOCK: ...` 不再被识别为标注块 ——
#    但协议本就要求标注块**独占注释行**(字段行紧随其后),行尾形态凑不齐字段集。
#    ⚠️ **残留的一种形态查不出来**:顶格无任何前缀的 `DEV_MOCK: bool = True`(Python 模块级
#    类型标注)与顶格的裸 marker `DEV_MOCK: 说明` 前缀都是空串,**行级正则分不开**。
#    ⛔ 不要为此禁掉空前缀 —— Java 块注释里不带 `*` 续行符的写法(`/*` 换行后直接顶格写
#    marker 与字段行、再 `*/` 收尾)正是顶格无前缀,禁掉它方向会从假红翻成**假绿**
#    (整个标注块对本门隐形)。⚠️ 此处刻意**不写出那个 marker 字面量**:本文件会被自家扫描器
#    扫到,写出来当场造一个缺六字段的假标注块 + 连带把全文注释里的 `import.meta.env.DEV`
#    举例全判成 build_time_guard(实测一次多出 8 条自伤,已回退)。
#    该取舍与 architect 的 `MOCK_TAG_PREFIX_OK_RE` 逐字一致,⛔ 别只改一边。
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


def _marker_at(line: str, in_block_comment: bool = False):
    """返回该行的 marker 匹配对象(仅当它是**真正的标注行**),否则 None。

    ⚠️ `in_block_comment` **必须由调用方传入**(见上方 `block_comment_flags`)。
       默认 False 只是为了让"单行、无上下文"的调用仍可用,⛔ 扫描主路径不得省略它 ——
       省了等于退回纯前缀判定,Java 块注释里顶格写的标注块会被整块跳过(假绿)。
    """
    m = _MARKER_LINE.search(line)
    if m is None:
        return None
    # search 命中的可能是带前缀注释符的整段,需按 token 自身位置判前缀
    tok = re.search(r'THIRD_PARTY_MOCK|DEV_MOCK', line)
    if tok is None:
        return None
    if not is_marker_line(line, tok, in_block_comment):
        return None
    return m

# DEV_MOCK 的**反向**判据:它本就该被构建期裁掉,所以出现「运行时开关」反而危险 ——
# 那意味着这个 dev mock 在生产**有机会被打开**。
# ⚠️ 判据必须要求**正向信号**(真的出现了某个 mock 开关环境变量),
# ⛔ 不能写成「没有构建期守卫就报」—— planner 的第二种 ✅ 推荐形态 MSW `handlers.ts`
#    里根本没有任何守卫(靠调用点 `setupWorker` 不进生产来剔除),那样写会把合规形态判死。
_DEV_MOCK_RUNTIME_SWITCH = re.compile(
    r'(?:import\.meta\.env|process\.env)\.[A-Za-z_]*MOCK[A-Za-z_]*'
    r'|@Value\s*\(\s*"\$\{[^}"]*mock[^}"]*\.enabled')


def _extract_mock_blocks(lines: List[str]) -> List[Dict]:
    """逐行识别 **两种** 标注块(兼容 //、#、* 注释风格),返回 [{line, kind, fields, missing}]。

    ⚠️ `kind` 决定必填字段集与后续全部判定 —— THIRD_PARTY_MOCK 要六字段、构建期守卫判 Critical;
       DEV_MOCK 只要三字段、构建期守卫是**合规形态**。判错 kind 会让两类判据互换,方向两侧都错。
    """
    blocks = []
    in_block = block_comment_flags(lines)
    i = 0
    while i < len(lines):
        if _marker_at(lines[i], in_block[i]):
            # ⚠️ 先判 THIRD_PARTY_MOCK:两个 token 互不含子串,顺序目前不影响结果,
            #    但把"更严的那个"放前面是防以后有人放宽 DEV 正则时静默降级。
            kind = 'THIRD_PARTY_MOCK' if _MARKER_LINE_TPM.search(lines[i]) else 'DEV_MOCK'
            required = REQUIRED_FIELDS_BY_KIND[kind]
            fields = {}
            last_j = i
            for j in range(i + 1, min(i + 13, len(lines))):
                if _marker_at(lines[j], in_block[j]):
                    break  # 遇到下一个标注块 marker(任一类型),停止本块字段收集,避免吞掉相邻块
                fm = _FIELD_LINE.match(lines[j])
                if fm:
                    fields[fm.group(1)] = fm.group(2).strip()
                    last_j = j
            missing = [f for f in required if f not in fields]
            blocks.append({'line': i + 1, 'kind': kind, 'fields': fields, 'missing': missing})
            i = last_j + 1  # 前进到本块最后字段行的下一行,而非固定 +13(否则跳过相邻块)
        else:
            i += 1
    return blocks


def scan_file(file_path: Path, max_overdue_days: int = 14) -> Dict:
    """扫描单个文件"""
    try:
        content = file_path.read_text(encoding='utf-8', errors='ignore')
    except Exception as e:
        return {'error': str(e)}

    issues = []
    seen = set()  # (type, line) 去重,避免多个 pattern 命中同一行重复上报
    lines = content.splitlines()
    mock_blocks = _extract_mock_blocks(lines)
    has_tpm_block = any(b['kind'] == 'THIRD_PARTY_MOCK' for b in mock_blocks)
    has_dev_block = any(b['kind'] == 'DEV_MOCK' for b in mock_blocks)

    # 1. 扫描构建期守卫反模式 —— **只对含 THIRD_PARTY_MOCK 标注块的文件判违规**。
    #
    # ⚠️⚠️ 这一层的门控是「有没有 THIRD_PARTY_MOCK 标注块」,⛔ 不得放宽为「文件里有没有 mock 字样」
    #      (`_MOCK_HINT` 宽匹配)。两个理由:
    #      ① **宽匹配会把 DEV_MOCK 判死**:DEV_MOCK 文件里必然出现 "mock" 字样,
    #         于是 `import.meta.env.DEV` —— 它**要求的合规形态** —— 被判 Critical,
    #         而修复建议是「改用运行时开关」,照做就把 dev mock 打进了生产包。
    #      ② **未标记的 mock 不归本脚本管**:那由维度 2A 的 `scan_mock_data.py`
    #         (普通 mock 零容忍)承担。本脚本管的是「**已声明**的临时 mock 合不合协议」,
    #         靠 "mock" 这个词去撞未声明的 mock 本就是副作用而非判据。
    #      代价是:一个**忘了写 THIRD_PARTY_MOCK 标记**的第三方 mock + 构建期守卫,
    #      本脚本不报 —— 但那种情况「缺标记」才是主缺陷,由 2A 兜。
    #
    # ⚠️⚠️ **归属判定(⛔ 勿退回纯文件级)**:门控是文件级的,但**同一个文件里
    #      两类标注块并存是完全正常的形态**(一个 api 模块里既有第三方 mock、又有本地 dev mock)。
    #      纯文件级判定下,只要该文件有 TPM 块,**DEV_MOCK 自己那段合规的 `import.meta.env.DEV`
    #      也会被判 build_time_guard/Critical**,而 suggestion 写着「改用运行时环境变量判断」——
    #      照做就去掉了 tree-shake 守卫、把 dev mock 打进生产包,**正是标注块门控要消灭的那类事故,
    #      只是换了个触发条件**。故每处守卫按「**行距最近的标注块(双向)**」归属:
    #        · 前一个块是 DEV_MOCK → 跳过(那是它要求的合规形态)
    #        · 前一个块是 THIRD_PARTY_MOCK → 判违规
    #        · 前面没有任何块 → 回退文件级(即照旧判违规),⛔ 不放宽,避免开假绿口子
    #      ⚠️ 只在**两类并存**时启用逐处归属(`has_dev_block` 为真),纯 TPM 文件按文件级判定。
    #      ⚠️ 对应的 architect 门 `check_third_party_mock_runtime.py` 是**代码块粒度**、
    #         本门是**标注块粒度**,两者是同一条判据在各自载体上的落法(设计文档有围栏、源码没有)。
    _block_marks = sorted((b['line'], b['kind']) for b in mock_blocks)

    def _owner_kind(ln: int):
        """该行守卫归属于哪个标注块 —— 按**行距取最近的 marker,双向**;没有块则 None。

        ⚠️⚠️ **必须双向,⛔ 不能只往前看**:两类 mock 的
        **canonical 形态都是「守卫包着标注块」**,即 marker 在守卫的**下一行**——

            if (import.meta.env.DEV) {        // ← 守卫在这一行
              // DEV_MOCK: 后端接口未部署     // ← 它自己的 marker 在下一行

        只往前看会把这处守卫归给**文件里更早的那个块**(通常正是 TPM 块)→ 判 Critical,
        而这恰恰是 planner `flow-edge-cases.md` 情况 1 逐字推荐的写法。
        实测:TPM 块在前 + DEV_MOCK 块在后的混写文件,DEV_MOCK 自己那段合规守卫被判 Critical
        —— 正是本次变更要消灭的那类事故,只是换了触发条件。
        ⚠️ 等距时取 **THIRD_PARTY_MOCK 从严**(混写本就该被指出来)。
        """
        best = None  # (distance, kind_rank, kind);kind_rank 0=TPM 优先
        for bl, bk in _block_marks:
            d = abs(bl - ln)
            rank = 0 if bk == 'THIRD_PARTY_MOCK' else 1
            if best is None or (d, rank) < (best[0], best[1]):
                best = (d, rank, bk)
        return best[2] if best else None

    if has_tpm_block:
        for pattern in FRONTEND_BUILD_TIME_GUARDS + BACKEND_BUILD_TIME_GUARDS:
            for match in re.finditer(pattern, content):
                line_num = content[:match.start()].count('\n') + 1
                if has_dev_block and _owner_kind(line_num) == 'DEV_MOCK':
                    continue
                key = ('build_time_guard', line_num)
                if key in seen:
                    continue
                seen.add(key)
                issues.append({
                    'type': 'build_time_guard',
                    'severity': 'Critical',
                    'line': line_num,
                    'code': match.group(0),
                    'message': '使用构建期守卫，打包后被裁掉或部署后失效',
                    'suggestion': '改用运行时环境变量判断（VITE_THIRD_PARTY_MOCK_ENABLED / third-party.mock.enabled）'
                })

    # 1b. DEV_MOCK 的**反向**判据:它本该被构建期裁掉,出现运行时开关反而意味着
    #     「这个 dev mock 在生产有机会被打开」。判 Important 不判 Critical ——
    #     开关名是启发式匹配,判死的方向是假红。
    if has_dev_block and not has_tpm_block:
        for match in _DEV_MOCK_RUNTIME_SWITCH.finditer(content):
            line_num = content[:match.start()].count('\n') + 1
            key = ('dev_mock_runtime_switch', line_num)
            if key in seen:
                continue
            seen.add(key)
            issues.append({
                'type': 'dev_mock_runtime_switch',
                'severity': 'Important',
                'line': line_num,
                'code': match.group(0),
                'message': 'DEV_MOCK 用运行时开关控制,该开关在生产环境有可能被打开',
                'suggestion': '改用构建期守卫(import.meta.env.DEV / MSW 仅 dev 注册),'
                              '让它在生产构建被 tree-shake 剔除;运行时开关是 THIRD_PARTY_MOCK 的要求,两者相反'
            })

    # 2. 扫描标注块(必填字段 + 过期),按 kind 分流
    compliant_blocks = []
    for blk in mock_blocks:
        line_num = blk['line']
        kind = blk['kind']
        required = REQUIRED_FIELDS_BY_KIND[kind]
        if blk['missing']:
            issues.append({
                'type': 'missing_fields',
                'severity': 'Critical',
                'line': line_num,
                'kind': kind,
                'missing': blk['missing'],
                'message': f'{kind} 标注块缺失必填字段: {", ".join(blk["missing"])}',
                'suggestion': f'补全完整标注块（{kind} + {"/".join(required)}）'
            })
            continue

        # DEV_MOCK 没有 expected_ready(那是"对方什么时候交付"的概念,同项目内不存在),
        # 改按 since 计龄:拖过阈值说明后端接口早该部署了、这个拦截块该清了。
        # ⚠️ 判 Important 不判 Critical —— 与 THIRD_PARTY_MOCK 的 expected_ready 过期
        #    (对方违约、有明确承诺日)不同,since 计龄只是"放久了"的启发式。
        if kind == 'DEV_MOCK':
            since_str = blk['fields'].get('since', '')
            ms = re.match(r'(\d{4}-\d{2}-\d{2})', since_str)
            stale = False
            if ms:
                try:
                    since_date = datetime.strptime(ms.group(1), '%Y-%m-%d')
                    days_old = (datetime.now() - since_date).days
                    if days_old > max_overdue_days:
                        stale = True
                        issues.append({
                            'type': 'dev_mock_stale',
                            'severity': 'Important',
                            'line': line_num,
                            'kind': kind,
                            'since': ms.group(1),
                            'days_old': days_old,
                            'message': f'DEV_MOCK 已存在 {days_old} 天（超过 {max_overdue_days} 天阈值）,'
                                       f'后端接口大概率已部署',
                            'suggestion': 'REMOVE_WHEN 条件若已满足请立即删除本拦截块;'
                                          '确需继续请更新 since 并说明原因'
                        })
                except ValueError:
                    pass
            if not stale:
                compliant_blocks.append({
                    'type': 'compliant_pending',
                    'severity': 'Important',
                    'line': line_num,
                    'kind': kind,
                    'since': blk['fields'].get('since'),
                    'message': '标注合规的同项目 dev mock（DEV_MOCK）,待后端接口部署后删除',
                    'suggestion': '后端接口部署到 dev 环境后立即删除本拦截块'
                })
            continue

        # 检查 expected_ready 是否过期
        ready_str = blk['fields'].get('expected_ready', '')
        expired = False
        m = re.match(r'(\d{4}-\d{2}-\d{2})', ready_str)
        if m:
            try:
                ready_date = datetime.strptime(m.group(1), '%Y-%m-%d')
                days_overdue = (datetime.now() - ready_date).days
                if days_overdue > max_overdue_days:
                    expired = True
                    issues.append({
                        'type': 'expired',
                        'severity': 'Critical',
                        'line': line_num,
                        'expected_ready': m.group(1),
                        'days_overdue': days_overdue,
                        'message': f'expected_ready 已过期 {days_overdue} 天（超过 {max_overdue_days} 天阈值）',
                        'suggestion': '催第三方交付或转设计 Module E 暂行方案'
                    })
            except ValueError:
                pass
        if not expired:
            compliant_blocks.append({
                'type': 'compliant_pending',
                'severity': 'Important',
                'line': line_num,
                'kind': kind,
                'vendor': blk['fields'].get('vendor'),
                'api': blk['fields'].get('api'),
                'expected_ready': blk['fields'].get('expected_ready'),
                'message': '标注合规的第三方临时 mock，待真实接口交付（下次 Review 必查进度）',
                'suggestion': '真实接口可调通后立即删除，禁止保留为兜底'
            })

    # 3. 真实 client 信号(文件级):vendor SDK/client + 后端真实 base URL(源码中硬编码);
    #    与 mock 的并存判定在 scan_directory 做全仓聚合(配置文件另行单独扫描)
    has_vendor_sdk = (any(re.search(p, content) for p in VENDOR_SDK_PATTERNS)
                      or find_real_backend_signal(content))
    # ⚠️ 「真实对接后残留」只看 **THIRD_PARTY_MOCK** 块 —— 该判据的语义是
    #    「第三方 SDK 已经接上了、mock 却还在」。DEV_MOCK 讲的是**同项目后端**,
    #    与某个厂商 SDK 在不在同一个仓里毫无关系;把它算进来 = 一个文件里同时有
    #    dev mock 和一句无关的 vendor import 就被判残留(假红)。
    has_mock_block = has_tpm_block

    # 4. 检查 mock 兜底调用（catch / || / fallback）
    fallback_patterns = [
        (r'catch\s*\([^)]*\)\s*\{[^}]*mock', re.DOTALL | re.IGNORECASE),
        (r'\|\|\s*mock', re.IGNORECASE),
        (r'default:[^\n]*mock', re.IGNORECASE),  # 限单行,避免 DOTALL 跨行误报
    ]
    for pattern, flags in fallback_patterns:
        for match in re.finditer(pattern, content, flags):
            line_num = content[:match.start()].count('\n') + 1
            key = ('fallback', line_num)
            if key in seen:
                continue
            seen.add(key)
            issues.append({
                'type': 'fallback',
                'severity': 'Critical',
                'line': line_num,
                'code': match.group(0)[:50],
                'message': 'Mock 函数在 catch/fallback/默认分支中被调用（兜底逻辑）',
                'suggestion': '删除兜底逻辑，真实接口失败应抛出错误而非回退到 mock'
            })

    return {
        'file': str(file_path),
        'issues': issues,
        'compliant_pending': compliant_blocks,
        'has_vendor_sdk': has_vendor_sdk,
        'has_mock_block': has_mock_block,
    }


def scan_residue_in_env_files(src_dir: Path) -> List[Dict]:
    """扫描环境变量配置文件中的 mock 残留"""
    issues = []

    # 查找 .env.* 文件(按绝对路径去重,glob 与 **/glob 会重复命中顶层文件)
    env_files = sorted({p.resolve() for p in
                        list(src_dir.glob('.env*')) + list(src_dir.glob('**/.env*'))})

    for env_file in env_files:
        if env_file.is_file():
            try:
                content = env_file.read_text(encoding='utf-8')

                # 检查 baseURL 是否已切换到真实地址
                base_url_match = re.search(
                    r'(VITE_API_BASE_URL|REACT_APP_API_BASE_URL|API_BASE_URL)\s*=\s*["\']?(https?://[^"\';\s]+)',
                    content
                )

                if base_url_match:
                    base_url = base_url_match.group(2)
                    # 非 localhost/127.0.0.1 → 真实地址
                    is_real_url = not any(x in base_url for x in ['localhost', '127.0.0.1', 'mock', '0.0.0.0'])

                    if is_real_url:
                        # 检查 mock 开关是否仍为 true
                        mock_enabled_match = re.search(
                            r'(VITE_THIRD_PARTY_MOCK_ENABLED|THIRD_PARTY_MOCK_ENABLED)\s*=\s*["\']?true',
                            content
                        )
                        if mock_enabled_match:
                            issues.append({
                                'type': 'env_residue',
                                'severity': 'Critical',
                                'file': str(env_file),
                                'base_url': base_url,
                                'mock_var': mock_enabled_match.group(1),
                                'message': f'baseURL 已切换到真实地址（{base_url}），但 Mock 开关仍为 true',
                                'suggestion': f'修改 {mock_enabled_match.group(1)}=false 或删除该变量'
                            })
            except Exception:
                pass

    return issues


EXCLUDED_DIRS = {'node_modules', '.git', 'dist', 'build', 'target', 'out',
                 '.next', '.nuxt', 'vendor', '__pycache__'}

# 后端配置文件单独扫描:只查真实对接信号,不跑 mock/fallback 检查(避免 yaml 的 `default: mock-xxx` 等误报)
CONFIG_EXTENSIONS = {'.yml', '.yaml', '.properties'}


def scan_config_backend_signal(src_dir: Path) -> bool:
    """单独扫描 application.yml / *.properties 等后端配置的真实对接信号(对接信号 2),命中即视为已对接"""
    for cfg in src_dir.rglob('*'):
        if not cfg.is_file() or cfg.suffix not in CONFIG_EXTENSIONS:
            continue
        if set(cfg.relative_to(src_dir).parts) & EXCLUDED_DIRS:
            continue
        try:
            if find_real_backend_signal(cfg.read_text(encoding='utf-8')):
                return True
        except Exception:
            pass
    return False


def scan_directory(src_dir: Path, extensions: Set[str],
                   max_overdue_days: int = 14) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """扫描目录,返回 (问题文件列表, env 残留, 合规待 follow-up 列表)"""
    file_results = []
    env_residue = scan_residue_in_env_files(src_dir.parent if src_dir.name == 'src' else src_dir)

    scanned = 0
    for file_path in src_dir.rglob('*'):
        if not file_path.is_file() or file_path.suffix not in extensions:
            continue
        rel_parts = set(file_path.relative_to(src_dir).parts)
        if rel_parts & EXCLUDED_DIRS:
            continue
        scanned += 1
        result = scan_file(file_path, max_overdue_days)
        if 'error' not in result:
            file_results.append(result)

    # 全仓聚合:任一源码文件出现真实 vendor SDK/base URL 信号,或后端配置文件出现真实 base URL,
    # 或前端 .env 已把 baseURL 切到真实地址(env_residue,本身即 Critical 真实对接信号),
    # 则所有含 mock 标注块的文件判并存。
    # 配置文件扫描与 env 残留扫描对齐:扫 src/ 时回退到项目根,覆盖 src 外的 application.yml
    cfg_root = src_dir.parent if src_dir.name == 'src' else src_dir
    repo_real_onboarding = (any(r['has_vendor_sdk'] for r in file_results)
                            or scan_config_backend_signal(cfg_root)
                            or bool(env_residue))
    if repo_real_onboarding:
        for r in file_results:
            if r['has_mock_block']:
                r['issues'].append({
                    'type': 'coexistence',
                    'severity': 'Critical',
                    'line': 0,  # 文件级问题
                    'message': '代码仓已出现真实 vendor SDK/client 或真实 base URL 配置，与 THIRD_PARTY_MOCK 并存',
                    'suggestion': '真实接口已对接，立即删除所有 THIRD_PARTY_MOCK 标注块和 mock 实现'
                })

    results = [{'file': r['file'], 'issues': r['issues']}
               for r in file_results if r['issues']]
    # 已判并存(Critical)的仓库中,标注块不再视为"合规待 follow-up"
    compliant_pending = [] if repo_real_onboarding else [
        {**blk, 'file': r['file']}
        for r in file_results for blk in r.get('compliant_pending', [])
    ]
    return results, env_residue, compliant_pending, scanned


def format_text_output(results: List[Dict], env_residue: List[Dict],
                       compliant_pending: List[Dict]) -> str:
    """格式化文本输出"""
    lines = []
    lines.append('【第三方临时 Mock 反模式扫描】\n')

    total_issues = sum(len(r['issues']) for r in results) + len(env_residue)
    critical_count = sum(
        1 for r in results for i in r['issues'] if i['severity'] == 'Critical'
    ) + len(env_residue)

    lines.append(f'  问题文件: {len(results)} 个')
    lines.append(f'  发现问题: {total_issues} 处')
    lines.append(f'  Critical: {critical_count} 处\n')

    if critical_count > 0:
        lines.append('  🔴 Critical 违规:\n')

        # 环境变量残留
        for issue in env_residue:
            lines.append(f'    - {issue["file"]}')
            lines.append(f'      {issue["message"]}')
            lines.append(f'      建议: {issue["suggestion"]}\n')

        # 代码文件问题
        for result in results:
            for issue in result['issues']:
                if issue['severity'] == 'Critical':
                    lines.append(f'    - {result["file"]}:{issue["line"]}')
                    lines.append(f'      {issue["message"]}')
                    lines.append(f'      建议: {issue["suggestion"]}\n')

    # ⚠️ **Important 明细必须打出来**:`dev_mock_stale` / `dev_mock_runtime_switch` 等 Important
    #    若不逐条输出,人读输出只剩一行「发现问题: N 处 / Critical: 0 处」,
    #    读者拿到的是一份「说有问题但不说是什么」的报告,无从下手。
    important_issues = [(r, i) for r in results for i in r['issues']
                        if i['severity'] != 'Critical']
    if important_issues:
        lines.append(f'\n  🟡 Important 提示: {len(important_issues)} 处\n')
        for result, issue in important_issues:
            lines.append(f'    - {result["file"]}:{issue["line"]} [{issue["type"]}]')
            lines.append(f'      {issue["message"]}')
            lines.append(f'      建议: {issue["suggestion"]}\n')

    lines.append(f'  🟡 合规但待 follow-up: {len(compliant_pending)} 处')
    for blk in compliant_pending:
        lines.append(f'    - {blk["file"]}:{blk["line"]} [{blk.get("kind")}]')
        # ⚠️ 按 kind 打对应字段:DEV_MOCK 根本没有 vendor / api / expected_ready 三个概念,
        #    照 TPM 的模板打会输出 `vendor=None api=None expected_ready=None` —— 既无信息、
        #    又让读者以为标注块缺字段(而它明明已判合规)。
        if blk.get('kind') == 'DEV_MOCK':
            lines.append(f'      since={blk.get("since")}(同项目后端未部署,待部署后删除)')
        else:
            lines.append(f'      vendor={blk.get("vendor")} api={blk.get("api")} '
                         f'expected_ready={blk.get("expected_ready")}')

    if total_issues == 0 and not compliant_pending:
        lines.append('\n  ✅ 无第三方接口 Mock 反模式')

    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(
        description='扫描第三方接口临时 Mock 反模式'
    )
    parser.add_argument(
        'path',
        type=Path,
        help='要扫描的目录路径（如 src/）'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='以 JSON 格式输出结果'
    )
    parser.add_argument(
        '--strict',
        action='store_true',
        help='严格模式：Important 级别问题也返回非零退出码'
    )
    parser.add_argument(
        '--extensions',
        default='.ts,.tsx,.js,.jsx,.vue,.java,.kt,.cs,.go,.py',
        help='要扫描的文件扩展名（逗号分隔）'
    )
    parser.add_argument(
        '--max-overdue-days',
        type=int,
        default=14,
        help='expected_ready 过期容忍天数（默认 14 天，超过升 Critical）'
    )

    args = parser.parse_args()

    # ⚠️ 同 check_file_complexity.py：`exists()` 与 `is_dir()` 必须分开判。
    # 传存在的单个文件时 scan_directory 的 rglob 取空集 → 「✅ 无第三方接口 Mock 反模式」exit 0。
    # 此处后果比一般脚本更重：SKILL.md 要求 2A/2B 两个脚本互为兜底，而 2A 侧对合规标注块
    # 本就按 --third-party-mode 豁免，2B 侧一旦静默关掉，**两道闸门同时失效**。
    if not args.path.exists():
        print(f'错误: 路径不存在: {args.path}', file=sys.stderr)
        sys.exit(2)  # 入参错(路径不存在),非产物违规
    if not args.path.is_dir():
        print(f'错误: 需要目录，收到的是文件: {args.path}', file=sys.stderr)
        sys.exit(2)

    extensions = set(args.extensions.split(','))
    results, env_residue, compliant_pending, scanned_files = scan_directory(
        args.path, extensions, args.max_overdue_days)

    if args.json:
        output = {
            'scan_path': str(args.path),
            # ⚠️ 「0 命中」须能与「0 文件被扫(路径给错)」区分:本脚本是维度 2B(Critical)的采集侧,
            #    路径给错时早期同样输出 issue_file_count=0 → 报告照抄「✅ 无残留」(假绿)。
            'scanned_files': scanned_files,
            'skipped': scanned_files == 0,
            'issue_file_count': len(results),
            'env_residue': env_residue,
            'compliant_pending': compliant_pending,
            'results': results
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print(format_text_output(results, env_residue, compliant_pending))

    # 判断退出码:Critical → 1;--strict 时 Important(合规待 follow-up)也 → 1
    has_critical = any(
        i['severity'] == 'Critical'
        for r in results
        for i in r['issues']
    ) or len(env_residue) > 0

    if has_critical:
        sys.exit(1)
    # ⚠️ **`--strict` 必须含全部 Important**:`--help` 写的是「Important 级别问题也返回非零退出码」,
    #    `dev_mock_stale` / `dev_mock_runtime_switch` 也是 Important —— 只看 `compliant_pending`
    #    会让「DEV_MOCK 既超龄又用了运行时开关」在 `--strict` 下仍 `exit 0`,**方向是假绿**。
    has_important = any(i['severity'] != 'Critical'
                        for r in results for i in r['issues'])
    if args.strict and (compliant_pending or has_important):
        sys.exit(1)

    sys.exit(0)


if __name__ == '__main__':
    main()
