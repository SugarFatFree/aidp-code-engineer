#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""「上游调用日志与脱敏声明表」硬核回检 — dev-logic-architect 检查项 35(Important 档,对应核心原则 27)

对应上下游共用的通用规则 **约定40**(上游/第三方调用日志规范)。
⚠️ 引用一律写全称 `约定40`:本 SKILL 的 `R1/R2/R3` 已被**上游溯源三项**占用
   (见 `check_upstream_reference.py`),别把通用规则号写成裸 `RNN`。

⚠️ **术语消歧(本 SKILL 特有的一处高频误读)**:本检查项里的「**上游**」指**进程外被调用的
   第三方 / 上游服务**(第三方 HTTP API、微服务 RPC·Feign、对象存储、短信邮件网关、
   支付鉴权中心);**不含本地 DB 与本地缓存**。它与**检查项 15「上游溯源完备性」**里的
   「上游」(= PRD / 原型等**上游文档**)完全是两回事,两处都在本 SKILL 里、极易看串。

背景(下游实测):同一项目里 **4 个上游客户端写出 4 种日志规格、另有 2 个直接漏掉**。
根因不在编码期——**详细设计从来没写过**"这个上游调用要打哪些日志、哪些字段要脱敏",
于是"打不打、打什么"退化成个人习惯。对策与检查项 31(错误契约)、34(统计口径)同构:
**把运行期才暴露的约定前移到设计期,做成每个上游调用的强制产出小表。**

★ 与被测项目侧脚本的**去重边界(重要)**:运行时五条判据(C1 出站调用类零日志 / C2 成功路径
   不可见 / I1 无一条日志提到 URL / I2 成功路径只有 debug / I3 疑似凭据明文入日志)由
   **被测项目侧**的 `<项目根>/AIDP_HOME/scripts/check_upstream_call_log.py` 承担(经脚手架下发,
   不在任何 SKILL 内)。**本脚本只判设计期声明这一段,绝不重写那 5 条**——同一判据两份实现
   是最高频漂移源。两者扫描对象也不同:那份扫 `.java`/`.kt` 源码,本份扫设计文档 `.md`。

本脚本做**结构性硬核回检**(只判可靠判定的结构缺陷):

【Critical(退出码 1)】
  U2 缺列   —— 表存在但 6 列固定契约不齐:
               上游中文名 | 完整 URL | 请求段必打字段 | 响应段必打字段 | 脱敏字段清单 | 二进制/大对象降级说明
  U3 空格   —— 任一格为空或占位。**「脱敏字段清单」与「二进制/大对象降级说明」允许写「无」/「不涉及」**
               (= 确认过没有),但**不允许留空**——留空无法区分"确认过没有"与"根本没考虑"。

【Important(仅告警,不占退出码)】
  U1 缺表   —— 有上游调用信号却找不到「上游调用日志与脱敏声明表」。
               ⚠️ **刻意判 Important 不判 Critical**:存量设计文档会大面积命中,一上来就判死会让
               整个硬门被无视(本仓库既有教训:假红常驻 = 硬门被绕过)。表**一旦产出**,列不齐 /
               格子空就是新产物自身的缺陷,那两条才判 Critical。
  U5 空表   —— 表头齐全但**一行数据都没有**(空表 ≡ 没写,与 U1 同档)。
  U4 中文名 —— 「上游中文名」列不含任何中文(疑似直接写了 `ops-service` 这类内部代号)。
               面向用户的错误文案要求用中文服务名(检查项 31 C5 管的是**接口错误契约表**里的提示,
               本条管的是**本表**的服务名列,两处对象不同、各自登记,不重复计)。

⚠️ **U1 是「按本次扫描范围聚合」判定,不是逐文件判定** —— 与 `check_metric_spec.py` 的 M1 同一个坑:
   本 SKILL 在 M/L 档**强制多册拆分**,本表通常落在接口设计册或 B.7 所在册,而带「第三方 / 外部依赖」
   字样的标题必然散落在多册里 → 逐文件判会让合规多册设计**必假红**。**因此调用方应传目录。**

⚠️ 本脚本**不做**语义判定(该打的字段是不是真打了、脱敏清单列得全不全、降级说明合不合理),
   那由 QR 子 Agent 按 `references/quality-review-checklist.md` 检查项 35 对照 PRD / B.7 逐行判。
   **脚本全绿 ≠ 检查项 35 通过。**

用法:
    python3 check_upstream_call_log_spec.py <设计文档路径或目录> [--json]

退出码:
    0 = 通过,或跳过(确无上游调用信号 / 已显式声明「无外部依赖」且无反证)
    1 = 检出违规(严重度分档读 --json,不占用退出码;U1/U4 是 Important,不会让退出码变 1)
    2 = 入参或环境错(路径不存在、目录下没有 .md、全部文件不可读)

仅依赖 Python 3.8+ 标准库。
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

# ── 6 列固定契约(与 quality-review-checklist.md 检查项 35 严格一致) ──
REQUIRED_COLUMNS = ["上游中文名", "完整 URL", "请求段必打字段", "响应段必打字段",
                    "脱敏字段清单", "二进制/大对象降级说明"]

# 允许写「无」的两列:写「无」= 确认过没有,是**合格填写**;留空才是不合格。
NONE_ALLOWED_COLUMNS = {"脱敏字段清单", "二进制/大对象降级说明"}
NONE_ALLOWED_VALUES = {"无", "不涉及", "无敏感字段", "无脱敏字段", "无二进制", "无大对象",
                       "不涉及二进制", "不涉及大对象", "本调用无", "无(已确认)"}

EMPTY_MARKERS = {
    "", "-", "—", "–", "─", "n/a", "na", "/", "\\", "待定", "tbd", "todo",
    "?", "??", "待补", "待确认", "暂无", "...", "…", "xxx",
    "同上", "略", "按实际", "按实际调整", "视情况", "按业务", "视业务而定",
    "见上", "同前", "同左",
}

# ⚠️ 必须**全串锚定**:只有"整格就是一个占位符"才算未填。未锚定的写法会把
#    `https://${SMS_HOST}/v2/send` 这种**已填实、只留环境变量槽位**的合规 URL 判成空格
#    (本仓库 check_error_contract.py / check_metric_spec.py 都在这处翻过车,勿改回)。
PLACEHOLDER_RE = re.compile(r"^\{[^{}]*\}$|^<[^<>]+>$")

# ── 上游调用信号:只认**标题行**,不扫正文散文 ──
# ⚠️ 正词表**刻意不含裸「上游」**:本 SKILL 的「上游引用规则 / 上游溯源」指的是 PRD 等**上游文档**,
#    收进来会让每一份合规设计都长出一条 U1(实测必假红)。要「上游」就必须带服务性后缀。
UPSTREAM_SIGNAL_RE = re.compile(
    r"第三方|外部依赖|外部接口|外部系统|外部服务|集成方案|对接方案"
    r"|上游(?:服务|系统|接口|调用|依赖)|微服务调用|远程调用|RPC|Feign")

# 标题级否定护栏:这些是**流程性 / 元文档**标题,与"真的调了谁"无关。
UPSTREAM_SIGNAL_NEG_RE = re.compile(
    r"溯源|引用|待澄清|清单模板|规范|流程|附录|目录|索引|自检|评审|术语"
    r"|检查项|维度\s*\d|核心原则|判据|核验清单")

# 章节级豁免:标题命中即整节跳过(含其子标题)。
# ⚠️ **刻意比 check_lock_strategy.py / check_metric_spec.py 的同名词表窄两个词** ——
#    那两份收了 `识别清单|方案对比`,是为「stack-db-mysql.md 整节在**列举** FOR UPDATE 而非采用它」
#    这个具体场景加的;本检查没有对应的枚举型文档,收进来只剩副作用:
#    「## 第三方依赖识别清单」是列举上游调用**最自然的标题之一**,一旦整节豁免,
#    表、信号、外部端点反证**三样一起消失** → `skipped:true` + exit 0 + 零发现,
#    而 QR 会把 skipped 读成「确无出站调用」的合法 N/A(实测复现的假绿,勿把这两个词加回来)。
EXEMPT_HEADING_RE = re.compile(r"不适用|未采用|备选方案|反模式|已废弃|作废")

# 显式声明"本设计无外部依赖"——命中即跳过 U1(仍校验已存在的表)。
# ⚠️ 必须是**独立成句的声明行** + 否定护栏:B.7 的模板里恰恰教作者写「无外部依赖时须标注…」,
#    无差别 search 会把这句**指引**当成声明,把 U1 整份关掉(实测假绿方向)。
# ⚠️ 行首**不收 `|`**:收了会让表格单元格 `| 无外部依赖 |` 也算一条声明;
#    尾部余量从 12 收到 4:12 个字符足够让「本设计无外部依赖,但调用了内部 RPC。」这种
#    **自相矛盾的句子**照样算声明(实测)。
NO_UPSTREAM_DECLARE_RE = re.compile(
    r"^\s*[>*\-\s]*\**\s*(?:本次|本设计|本版|本期)?\s*"
    r"(?:确)?无(?:外部依赖|外部集成|第三方依赖|第三方集成|上游调用|外部调用)"
    r"[^\n]{0,4}?\s*\**\s*[。.:：]?\s*$")
DECLARE_GUARD_RE = re.compile(r"须|应|时[,，]|不得|禁止|例如|如[:：]|见|参见|模板|判据|硬门")

# ── 反证:真出现了外部端点 / HTTP 客户端标识,则无论哪句话写了"不涉及第三方",都不算无外部集成 ──
# (与 check_http_client_config.py 同一条思路:只按全文正则会让"真有集成却缺表"的设计静默放行)
EXTERNAL_ENDPOINT_RE = re.compile(
    r"https?://(?!localhost|127\.0\.0\.1|0\.0\.0\.0|example\.(?:com|org))([a-z0-9.-]+\.[a-z]{2,})",
    re.IGNORECASE)
# 文档站不算集成证据(A.2 引一句框架官方文档链接极常见)
DOC_HOST_RE = re.compile(
    r"^(?:docs?|developer|guide|guides|wiki|blog|learn|help|support|www)\."
    r"|(?:github|gitee|gitlab|stackoverflow|baeldung|wikipedia|npmjs|mvnrepository)\."
    r"|(?:readthedocs\.io|spring\.io|apache\.org|w3\.org|ietf\.org|json-schema\.org"
    r"|openapis\.org|oracle\.com|python\.org|golang\.org|nodejs\.org|mozilla\.org)$",
    re.IGNORECASE)
HTTP_CLIENT_RE = re.compile(
    r"@FeignClient|OpenFeign|RestTemplate|WebClient|RestClient|@HttpExchange|OkHttp"
    r"|HttpClient|Ktor\s*Client|Refit|httpx|aiohttp|undici|resty|net/http")

CJK_RE = re.compile(r"[一-鿿]")

# 表标题锚点:表头上方 ≤3 行内出现这些字样 → 紧随的第一张 GFM 表**无条件**按本表判。
# ⚠️ 为什么要有它(实测的假绿):列签名 hinge 在「脱敏」**单个列名**上——把「脱敏字段清单」
#    写成「敏感字段清单」,一张 6 列俱全、标题白纸黑字写着「上游调用日志与脱敏声明表」、
#    格子全空的表会**整张认不出**,U2/U3 一条都报不出来。正文标题比列名更可靠地表达意图。
TABLE_ANCHOR_RE = re.compile(r"上游调用日志|脱敏声明表")
# 回看 **3 个非空行**(不是 3 个物理行):表标题与表之间常隔空行、甚至夹一句导语,
# 按物理行数回看会正好错过标题(实测)。
TABLE_ANCHOR_LOOKBACK = 3
# ⚠️ 锚点**只认标题行或独立加粗标签行**,不认散文里的提及 —— 否则「有上游『上游调用日志与
#    脱敏声明表』时逐行为基准」这类**说明文字**会把它下方 3 行内任何一张无关表拉进来判缺列
#    (实测在 dev-manual-testcase 的方法论文档上假红)。与 check_error_contract.py 那条
#    「GFM 表头必须紧跟分隔行」是同一类护栏:**判据要认结构,不要认字面出现**。
ANCHOR_LABEL_RE = re.compile(
    r"^\s*[>*\-\s]*\*\*[^*]*(?:上游调用日志|脱敏声明表)[^*]*\*\*\s*[::]?\s*$")


def find_md_files(path: Path) -> List[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(path.rglob("*.md"))
    return []


def split_row(line: str) -> List[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def is_separator_row(cells: List[str]) -> bool:
    # ⚠️ 空行必须先判掉:split_row("") 得到 [""],把空单元格过滤后 all() 对空序列返回 True,
    #    于是**空行被当成分隔行** ——「候选表头 + 紧跟一个空行」会被识别成一张 0 行的表,
    #    对按表头签名判列的检查器就是一条凭空的「缺列 Critical」。
    #    实测复现:`output-module-examples.md` B.7 的键值表末行 + 空行 → 假红。勿改回。
    if not cells or all(c.strip() == "" for c in cells):
        return False
    return all(re.fullmatch(r":?-{1,}:?", c.replace(" ", "")) for c in cells if c != "")


def _norm(s: str) -> str:
    """归一化:剥行首引用符,去粗体/反引号/空白,全角括号→半角。

    ⚠️ **不要无差别删 `>`**:那会让 `PLACEHOLDER_RE` 的 `^<[^<>]+>$` 分支变成死代码——
       `<待定>` 归一化成 `<待定` 后永不命中,占位格被判成「已填实」(小假绿)。
       `>` 出现在格里只有一种正当来源:引用块里的表格 `> | a | b |` 的行首,故只剥行首。
    """
    s = re.sub(r"^\s*>+\s*", "", s)
    s = re.sub(r"[*`\s]", "", s)
    return s.replace("（", "(").replace("）", ")")


def cell_matches_column(cell: str, concept: str) -> bool:
    c = _norm(cell).lower()
    if concept == "上游中文名":
        return "中文名" in c or "服务名" in c or ("上游" in c and "名" in c) or ("系统" in c and "名" in c)
    if concept == "完整 URL":
        return "url" in c or "地址" in c or "端点" in c or "endpoint" in c
    if concept == "请求段必打字段":
        return "请求" in c and ("字段" in c or "日志" in c or "打" in c or "参数" in c)
    if concept == "响应段必打字段":
        return ("响应" in c or "返回" in c) and ("字段" in c or "日志" in c or "打" in c)
    if concept == "脱敏字段清单":
        return "脱敏" in c
    if concept == "二进制/大对象降级说明":
        return "二进制" in c or "大对象" in c or "降级" in c
    return False


def col_index(cells: List[str], concept: str) -> Optional[int]:
    for idx, c in enumerate(cells):
        if cell_matches_column(c, concept):
            return idx
    return None


def is_spec_table_header(cells: List[str]) -> bool:
    """签名判定:含「脱敏字段清单」列 + 至少 1 个其它专有列 = 一张上游调用日志声明表。

    ⚠️ 「脱敏」是本表**唯一高辨识度的列名**——B.7 既有的「第三方接口复用清单」「单位转换映射表」
       都可能带 URL / 请求 / 响应 字样,只认那几列会把它们误当本表、直接 U2 缺列假红。
       反过来只要求"6 列全中"又会让**缺列的表**整张认不出来、U2 永远报不出(缺列变假绿),
       所以门槛设在"能认出它想当这张表"的最低复合度上,缺的列交给 U2 报。
    """
    if col_index(cells, "脱敏字段清单") is None:
        return False
    hits = sum(1 for c in ("上游中文名", "完整 URL", "请求段必打字段",
                           "响应段必打字段", "二进制/大对象降级说明")
               if col_index(cells, c) is not None)
    # ⚠️ 门槛是 **≥2 不是 ≥1**:≥1 时任何「脱敏 + 请求参数」两列的普通接口脱敏说明表都会被
    #    当成本表并报缺列 Critical(实测假红);≥2 既排掉它,又仍能认出「缺 1~3 列」的真表
    #    (缺 4 列以上的残表交给标题锚点 TABLE_ANCHOR_RE 兜)。
    return hits >= 2


def strip_code_fences(lines: List[str]) -> List[bool]:
    """逐行标记「是否位于代码围栏内」(围栏行本身标 True)。"""
    flags = [False] * len(lines)
    fence = None
    for i, ln in enumerate(lines):
        s = ln.lstrip()
        m = re.match(r"^(`{3,}|~{3,})", s)
        if m:
            tok = m.group(1)[0]
            if fence is None:
                fence, flags[i] = tok, True
                continue
            if tok == fence:
                flags[i], fence = True, None
                continue
        flags[i] = fence is not None
    return flags


def exempt_line_flags(lines: List[str], in_code: List[bool]) -> List[bool]:
    """章节级豁免:命中豁免词的标题起,到**同级或更高级**标题止,整段标 True。"""
    flags = [False] * len(lines)
    level = None
    for i, ln in enumerate(lines):
        if in_code[i]:
            flags[i] = level is not None
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", ln)
        if m:
            lv, title = len(m.group(1)), m.group(2)
            if level is not None and lv <= level:
                level = None
            if level is None and EXEMPT_HEADING_RE.search(title):
                level = lv
        flags[i] = level is not None
    return flags


def scan_spec_tables(lines: List[str], in_code: List[bool], exempt: List[bool]) -> List[Dict]:
    """扫出全部上游调用日志声明表。**表头下一行必须是 GFM 分隔行**——否则散文里
    「固定小表:上游中文名 | 完整 URL | … | 脱敏字段清单 | …」这类**说明文字**会被当成表
    (本仓库 check_error_contract.py 就因此把自家模板判死过)。"""
    tables, i, n = [], 0, len(lines)
    while i < n:
        if in_code[i] or exempt[i] or "|" not in lines[i]:
            i += 1
            continue
        cells = split_row(lines[i])
        if len(cells) < 2 or is_separator_row(cells):
            i += 1
            continue
        # 标题锚点兜底:上方 ≤3 行(跳过空行)出现「上游调用日志 / 脱敏声明表」即无条件按本表判,
        # 缺什么列交给 U2 说 —— 防「列改个名整张表就认不出」的假绿。
        anchored = False
        seen = 0
        for k in range(i - 1, -1, -1):
            if not lines[k].strip():
                continue
            if in_code[k] or exempt[k]:
                break
            is_heading = bool(re.match(r"^#{1,6}\s", lines[k]))
            if TABLE_ANCHOR_RE.search(lines[k]) and (is_heading or ANCHOR_LABEL_RE.match(lines[k])):
                anchored = True
                break
            if is_heading:
                break          # 回看已跨到上一个章节标题,锚点不属于本表
            seen += 1
            if seen >= TABLE_ANCHOR_LOOKBACK:
                break
        if not anchored and not is_spec_table_header(cells):
            i += 1
            continue
        if i + 1 >= n or not is_separator_row(split_row(lines[i + 1])):
            i += 1
            continue
        rows, j = [], i + 2
        while j < n and "|" in lines[j] and not in_code[j]:
            r = split_row(lines[j])
            # ⚠️ 全空行既**不算分隔行**(见 is_separator_row 的前置判)、也**不算数据行**:
            #    两个性质必须同时成立。只改前者会让 Word 转出的 `||||` 占位行变成数据行,
            #    每格报一条「为空」Critical(实测在真实 PRD 语料里有 35 处这种行)。
            if is_separator_row(r) or all(c.strip() == "" for c in r):
                j += 1
                continue
            rows.append({"line": j + 1, "cells": r})
            j += 1
        tables.append({"header_line": i + 1, "header": cells, "rows": rows})
        i = j
    return tables


def _cell(row: Dict, idx: Optional[int]) -> str:
    if idx is None:
        return ""
    cells = row["cells"]
    return cells[idx] if idx < len(cells) else ""


def _is_empty(val: str, concept: str) -> bool:
    v = _norm(val)
    if concept in NONE_ALLOWED_COLUMNS and v in NONE_ALLOWED_VALUES:
        return False
    if v.lower() in EMPTY_MARKERS:
        return True
    return bool(PLACEHOLDER_RE.match(v))


def has_upstream_signal(lines: List[str], in_code: List[bool], exempt: List[bool]) -> List[Dict]:
    """上游调用信号:只认**标题行**,且跳过豁免章节与代码块。"""
    hits = []
    for i, ln in enumerate(lines):
        if in_code[i] or exempt[i]:
            continue
        m = re.match(r"^#{1,6}\s+(.*)$", ln)
        if not m:
            continue
        title = m.group(1)
        if UPSTREAM_SIGNAL_RE.search(title) and not UPSTREAM_SIGNAL_NEG_RE.search(title):
            hits.append({"line": i + 1, "title": title.strip()})
    return hits


def has_external_evidence(lines: List[str], in_code: List[bool]) -> bool:
    """反证:真实外部端点(非文档站)或 HTTP 客户端标识出现过。

    ⚠️ **刻意不吃章节级豁免**(参数里连 exempt 都不收):端点与客户端标识是「有没有真的调了谁」的
       **客观事实**,不该被一个章节标题关掉。豁免只用于「别把列举当采用」,那是**表与信号**的问题;
       若让它也关掉反证,一个 `## 备选方案(未采用)` 标题就能把真实调用整段藏掉(假绿)。
    """
    for i, ln in enumerate(lines):
        if in_code[i]:
            continue
        for m in EXTERNAL_ENDPOINT_RE.finditer(ln):
            if not DOC_HOST_RE.search(m.group(1)):
                return True
        if HTTP_CLIENT_RE.search(ln):
            return True
    return False


def scan_file(path: Path, root: Path) -> Dict:
    rel = str(path.relative_to(root)) if root in path.parents or path == root else path.name
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        # ⚠️ 读不出来 ≠ 没有违规:记为 read_error。**全部文件都不可读时** main() 判入参/环境错
        #    (exit 2);**部分不可读**时进 `read_errors` 并在人读输出里告警,与同族
        #    `check_metric_spec.py` 行为一致。
        return {"file": rel, "read_error": str(exc), "tables": 0, "signals": [],
                "criticals": [], "importants": [], "declared_none": False, "external": False}

    lines = text.splitlines()
    in_code = strip_code_fences(lines)
    exempt = exempt_line_flags(lines, in_code)

    tables = scan_spec_tables(lines, in_code, exempt)
    signals = has_upstream_signal(lines, in_code, exempt)
    external = has_external_evidence(lines, in_code)

    declared_none = False
    for i, ln in enumerate(lines):
        if in_code[i] or exempt[i]:
            continue
        if NO_UPSTREAM_DECLARE_RE.match(ln) and not DECLARE_GUARD_RE.search(ln):
            declared_none = True
            break

    criticals: List[Dict] = []
    importants: List[Dict] = []

    for tb in tables:
        idx = {c: col_index(tb["header"], c) for c in REQUIRED_COLUMNS}
        missing = [c for c in REQUIRED_COLUMNS if idx[c] is None]
        if missing:
            criticals.append({"rule": "U2", "file": rel, "line": tb["header_line"],
                              "msg": "上游调用日志与脱敏声明表缺列: " + " / ".join(missing)})
        # U5:表头齐全但一行数据都没有 —— 与「缺表」是同一件事换了个外观,同判 Important。
        # (全空占位行不计入数据行,见 scan_spec_tables 的行循环护栏)
        if not tb["rows"]:
            importants.append({"rule": "U5", "file": rel, "line": tb["header_line"],
                               "msg": "上游调用日志与脱敏声明表存在但**无任何数据行**"
                                      "(空表 ≡ 没写:每个进程外依赖调用都要占一行)"})
        for row in tb["rows"]:
            for c in REQUIRED_COLUMNS:
                if idx[c] is None:
                    continue
                val = _cell(row, idx[c])
                if _is_empty(val, c):
                    hint = "(本列允许写「无」表示确认过没有,但不允许留空)" \
                        if c in NONE_ALLOWED_COLUMNS else ""
                    criticals.append({"rule": "U3", "file": rel, "line": row["line"],
                                      "msg": "「%s」列为空或占位: %r%s" % (c, val[:40], hint)})
            ni = idx["上游中文名"]
            if ni is not None:
                name = _cell(row, ni)
                if name and not _is_empty(name, "上游中文名") and not CJK_RE.search(name):
                    importants.append({"rule": "U4", "file": rel, "line": row["line"],
                                       "msg": "「上游中文名」列无中文,疑似内部代号: %r"
                                              "(面向用户的错误文案要求中文服务名)" % name[:40]})

    return {"file": rel, "tables": len(tables), "signals": signals, "criticals": criticals,
            "importants": importants, "declared_none": declared_none, "external": external}


def render_text(results: List[Dict], criticals: List[Dict], importants: List[Dict],
                skipped: bool, target: Path) -> None:
    # ⚠️ criticals / importants 由 main() 传入(已含跨文件聚合的 U1)。**勿改回在本函数里
    #    从 results 重算**——那样人读输出会与退出码打架(本仓库实测踩过)。
    n_tables = sum(r["tables"] for r in results)
    print("上游调用日志与脱敏声明表核验(检查项 35 / 约定40) — %s" % target)
    print("  扫描文件: %d   识别到声明表: %d 张" % (len(results), n_tables))
    if skipped:
        print("  ⏭️  跳过:未发现上游/第三方调用信号,且无声明表(exit 0,**不等于通过**——"
              "若本设计确有出站调用而标题里没出现第三方/外部依赖类词,请人工确认)")
        return
    if not criticals and not importants:
        if n_tables == 0:
            print("  ✅ 通过:已声明无外部依赖,无需本表(**未校验任何表**,0 张)")
            return
        print("  ✅ 通过:声明表 6 列齐全、逐格填实、服务名为中文")
        print("  ⚠️ 脚本只做结构性核验;该打的字段是否真的够、脱敏清单全不全,须 QR 子 Agent 逐行判")
        return
    if criticals:
        print("  ❌ Critical: %d" % len(criticals))
        for c in criticals:
            print("    [%s] %s:%s  %s" % (c["rule"], c["file"], c["line"], c["msg"]))
    if importants:
        print("  🟡 Important: %d(不占退出码,须人工确认)" % len(importants))
        for c in importants:
            print("    [%s] %s:%s  %s" % (c["rule"], c["file"], c["line"], c["msg"]))


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="上游调用日志与脱敏声明表结构性核验(检查项 35)")
    ap.add_argument("target", help="详细设计文档路径或目录")
    ap.add_argument("--json", action="store_true", help="输出 JSON 供 Agent 解析")
    args = ap.parse_args(argv)

    target = Path(args.target)
    # ⚠️ exists() 与 is_dir() 必须分开判(全仓约定):合并写会把"路径不存在"和"传单个文件=合法"
    #    混为一谈,手滑写错路径等于整档静默放行。
    if not target.exists():
        print("[错误] 路径不存在: %s" % target, file=sys.stderr)
        return 2
    files = find_md_files(target)
    if not files:
        print("[错误] 未发现任何 .md 文件: %s" % target, file=sys.stderr)
        return 2

    root = target if target.is_dir() else target.parent
    results = [scan_file(f, root) for f in files]

    read_errors = [r for r in results if r.get("read_error")]
    if read_errors and len(read_errors) == len(results):
        for r in read_errors:
            print("[错误] 无法读取 %s: %s" % (r["file"], r["read_error"]), file=sys.stderr)
        return 2

    criticals = [c for r in results for c in r["criticals"]]
    importants = [c for r in results for c in r["importants"]]
    n_tables = sum(r["tables"] for r in results)
    n_signals = sum(len(r["signals"]) for r in results)
    external_any = any(r["external"] for r in results)
    declared_none_any = any(r["declared_none"] for r in results)
    skipped = (n_tables == 0 and n_signals == 0 and not external_any)

    # ── U1 做**跨文件聚合**判定,勿改回 per-file ──
    # per-file 判会让 M/L 档的多册设计必假红:表落在接口设计册,而「第三方 / 外部依赖」
    # 字样的标题必然散落在别的册里(与 check_metric_spec.py 的 M1 同一个坑)。
    if (n_signals or external_any) and not n_tables:
        # ⚠️ 抑制口径必须与 U1 的聚合方向**相反**,这一条实测翻过车:
        #    U1 跨文件聚合(防多册假红)是对的,但抑制它的 declared_none 若也跨文件 any(),
        #    多册设计里前端册合法写一句「本设计无外部依赖。」就把**整个扫描范围**的 U1 关掉,
        #    哪怕另一册白纸黑字写着调两个上游(假绿,且脚本自己推荐的「传目录」用法下必然触发)。
        #    正确口径:**每个带信号的文件都各自声明了无外部依赖**,才算这条声明成立。
        signal_files = [r for r in results if r["signals"]]
        suppressed = (not external_any) and bool(signal_files) \
            and all(r["declared_none"] for r in signal_files)
        if not suppressed:
            src = next((r for r in results if r["signals"]), None)
            if src is not None:
                where, line, what = src["file"], src["signals"][0]["line"], \
                    "标题「%s」" % src["signals"][0]["title"][:40]
            else:
                src = next(r for r in results if r["external"])
                where, line, what = src["file"], 1, "外部端点 / HTTP 客户端标识"
            importants.append({
                "rule": "U1", "file": where, "line": line,
                "msg": "本次扫描范围内存在上游/第三方调用信号(%s)却找不到"
                       "「上游调用日志与脱敏声明表」(约定40:设计期须声明打哪些日志、哪些字段脱敏)"
                       % what})

    if args.json:
        print(json.dumps({
            "target": str(target),
            "passed": not criticals,
            "skipped": skipped,
            "scanned_files": len(files),
            "spec_tables": n_tables,
            "upstream_signals": n_signals,
            "external_evidence": external_any,
            "declared_none": declared_none_any,
            "read_errors": [{"file": r["file"], "error": r["read_error"]} for r in read_errors],
            "criticals": criticals,
            "importants": importants,
        }, ensure_ascii=False, indent=2))
    else:
        render_text(results, criticals, importants, skipped, target)
        for r in read_errors:
            print("  ⚠️ 未能读取(未参与检查,不等于干净): %s — %s" % (r["file"], r["read_error"]))

    return 1 if criticals else 0


if __name__ == "__main__":
    sys.exit(main())
