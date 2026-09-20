#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""「错误契约」硬核回检 — dev-logic-architect 维度 31(Critical,对应核心原则 23)

背景:下游反复出现同一类缺陷——**失败没有被正确表达**:
  · 失败被伪装成成功(HTTP 200 + "操作成功" + 空 data / `{success:true, data:[]}`),
    前端把它当"没有数据"渲染成空态,故障对用户与监控双双静默;
  · 上游不可达时用内部代号报错("order-svc 连接失败"),用户看不懂、也泄漏内部拓扑;
  · 鉴权/权限/归属/签名判据 fail-open——"取不到租户 ID"被当成"无限制"放行。
根因不在编码期,而在**详细设计/接口设计根本没规定错误行为**,于是编码期各写各的、
测试期才当 bug 抓。对策:把失败正确性前移到设计期,每个接口强制产出「错误契约」小节。

本脚本做**结构性硬核回检**(只判可靠判定的结构缺陷),分两层:

【接口级 · Critical(退出码 1)】
  C1 接口缺「错误契约」表      —— 识别为接口的章节内找不到含「错误码」列的表
  C2 错误契约表缺列            —— 5 列固定契约:错误码 | HTTP Status | 触发条件 |
                                  面向用户的中文提示 | 失败/降级行为
  C3 用户提示列空/占位/无中文  —— 面向最终用户的文案必须逐行填实且是中文
  C4 失败/降级行为列空/占位
  C5 用户提示列泄漏内部代号    —— kebab/snake 服务名(ops-service)、IP[:port]、URL
  C8 错误码未登记进全局枚举    —— 接口错误契约表用了全局错误码枚举里没有的码(各接口自编码)

【文档级 · Critical(退出码 1)】
  C0 缺全局错误码枚举          —— 有接口错误契约表却找不到「全局错误码」枚举章节(仅目录模式判 Critical,
                                  单文件模式降 Important——枚举很可能定义在同目录另一份文档里)
  C6 失败伪装成功反模式        —— "失败/异常/超时 → 返回 200 / 空数组 / success:true / code:0"
  C7 显式 fail-open 反模式     —— "取不到…不过滤 / 异常…放行 / 为空…视为全部 / 默认放行"

【文档级 · Important(仅告警,不影响退出码)】
  W1 有安全判据信号(鉴权/权限/归属/签名/越权/租户隔离)却无 fail-closed 声明
  W2 有上游/第三方调用信号却无「以上游契约为准」类权威标注
  W3 有上游/第三方调用信号却无任何"上游不可达"类错误契约行

⚠️ 本脚本**不做**语义层判定(某个错误码是否恰当、某条降级是否合理、文案是否贴合业务),
那由 QR 子 Agent 按 `references/quality-review-checklist.md` 检查项 31 语义核验。
与既有脚本的边界:`check_http_client_config.py` 管"我方**作为调用方**怎么配客户端/怎么判
下游失败"(核心原则 16),本脚本管"我方**作为被调用方**怎么向前端表达失败"(核心原则 23),
方向相反、互补,不可互相替代。

用法:
  python check_error_contract.py <设计文档文件或目录>
  python check_error_contract.py <设计文档文件或目录> --json

退出码:
  0  通过 / 跳过(未识别到接口章节时,**仅接口级检查 C0~C5/C8 跳过**;
     文档级反模式 C6/C7 照常判——它们不依赖接口章节,且常出现在无接口的 B.3 异常处理篇)
  1  不通过(存在 Critical)
  2  输入错误(路径不存在 / 无 .md 文件)——非维度违规,修正参数后重跑
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ── 「错误契约」5 列固定契约(与 SKILL.md 核心原则 23 / assets/api-template.md 严格一致) ──
REQUIRED_COLUMNS = ["错误码", "HTTP Status", "触发条件", "面向用户的中文提示", "失败/降级行为"]
# 需逐行非空核验的两列
NONEMPTY_COLUMNS = ["面向用户的中文提示", "失败/降级行为"]

EMPTY_MARKERS = {"", "-", "—", "–", "─", "无", "n/a", "na", "/", "\\", "待定",
                 "tbd", "todo", "?", "??", "待补", "待确认", "暂无", "...", "…",
                 "xxx", "同上", "略", "按实际", "按实际调整", "视情况"}

# ⚠️ 必须**全串锚定**:只有"整格就是一个占位符"才算未填。早期写成 `\{[^{}]*\}`(未锚尾)
#    配合 re.match,会把「{上游中文名}服务无法连接,请稍后再试」这种**已填实、只留一个名称槽位**
#    的合规文案整格判空——本 SKILL 自带的 api-template.md 就这么被自家硬门判死过。
PLACEHOLDER_RE = re.compile(r"^\{[^{}]*\}$|^<[^<>]+>$")
CJK_RE = re.compile(r"[一-鿿]")

# 内部代号 / 内部拓扑泄漏(只在「面向用户的中文提示」列扫描)
INTERNAL_CODENAME_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:"
    r"https?://\S+"                                   # URL
    r"|\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?"              # IP[:port]
    r"|[a-z][a-z0-9]*(?:[-_][a-z0-9]+)+"              # kebab/snake 服务名 ops-service / ops_svc
    r")"
)

# 全局错误码枚举章节识别(靠**标题**认,避免把接口自己的错误契约表当成全局枚举)
ERROR_ENUM_HEADING_RE = re.compile(r"全局错误码|错误码枚举|错误码字典|错误码总表|统一错误码|ErrorCode", re.I)

# 接口章节识别信号(模板固定写法:`- **Method:** GET` / `**Path:** /xxx`)
METHOD_SIGNAL_RE = re.compile(r"\*\*\s*(Method|Path|请求方法|接口路径)\s*[:：]?\s*\*\*")
# ⚠️ 判定接口章节前必须先剥掉**行内代码**:文档正文里用反引号**提到**模板信号
#    (如"缺 `**Method:**` / `**Path:**` 信号")并不是一个接口块。实测本 SKILL 的
#    quality-review-checklist.md 就因这一句被误判成接口章节、继而误报「缺错误契约表」。
INLINE_CODE_RE = re.compile(r"`+[^`]*`+")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")

# ── 文档级反模式(C6/C7):行内正则,命中即 Critical ──
FAIL_AS_SUCCESS_PATTERNS: List[Tuple[str, str]] = [
    (r"(失败|异常|超时|错误|不可用|报错)[^。;；\n]{0,24}(返回|响应|仍返?回|置)[^。;；\n]{0,12}"
     r"(HTTP\s*)?200(?!\s*[)）])",
     "失败态返回 HTTP 200"),
    (r"(失败|异常|超时|错误|不可用|查不到|拿不到)[^。;；\n]{0,24}(返回|响应|置)[^。;；\n]{0,12}"
     r"(空(数组|列表|对象|集合|结果|data)|`?\[\]`?|`?\{\}`?)",
     "失败态返回空集合(与业务真空不可区分)"),
    (r"(失败|异常|超时|错误|不可用)[^。;；\n]{0,24}"
     r"(success\s*[:=]\s*true|`?code`?\s*[:=]\s*0\b|状态\s*[:=]?\s*成功)",
     "失败态仍标成功(success:true / code:0)"),
]

# ⚠️ 禁令/正确声明语境护栏(C6/C7 通用):设计文档**必然**要写出反模式本身才能禁止它
#   ("严禁失败返回空列表""取不到 → 拒绝,禁止放行""失败态与空结果态判然区分:无匹配 = code=0"),
#   不加护栏则一份**完全合规**的设计文档反而必判不通过——实测本 SKILL 自带的合规 fixture
#   就被 C6/C7 各误报一次。故命中禁令语境的行整行跳过 C6/C7。
#   取舍与仓库既有口径一致:**宁可漏报也不误报**(噪声常驻会让整个硬门被无视)。
NEGATION_GUARD_RE = re.compile(
    # ⚠️ 勿把「避免」加进来:它常作**动机**出现在违规句里("下游超时仍返回 200,避免前端
    #    报错弹窗"),实测加了它就漏掉这条真违规。护栏只收**明确的禁令/区分声明**词。
    # ⚠️ 更勿写裸「不可」:它是「不可用」的子串,而「不可用」正是失败关键词之一,
    #    会把「下游不可用 → 返 200 空数组」「鉴权服务不可用时默认放行」这类**真违规整行吞掉**。
    #    需要豁免的是规范性表述「默认不可用」,已单列。
    r"严禁|禁止|不得|不许|不可以|勿|杜绝|反模式|错误示范|❌|"
    r"判然区分|须能区分|必须能与|区分于|"
    r"fail[-\s]?closed|一律拒绝|直接拒绝|不允许|不放行|"
    # ⚠️ 勿写裸「空结果」:C6 的违规词里就有 `空(数组|列表|对象|集合|结果|data)`,
    #    两者**完全相同** —— 「下游超时时返回空结果」这条真违规会被自己的护栏吞掉
    #    (与已修的「不可」⊂「不可用」是同一个 bug,当时只修了一处)。
    #    改用**带区分语境**的形态:只有在谈「空结果态与失败态的区别」时才豁免。
    r"无匹配|空结果态|与空结果|空结果不同|业务真空|合法成功|"
    # 检查清单 / 不通过标志一类**描述违规长什么样**的句子(本身不是违规)
    r"不通过|违规|反例|类表述|不合规|默认不可用|"
    # 引述构式:`出现「…」类 X 表述` / `「…」等` —— 引号收尾后接"类/等/这类"是**在描述一类写法**,
    # 不是在采用它。实测本 SKILL 检查清单的「不通过标志」条目正是这个构式。
    r"」类|」等|」这类|』类|』等"
)

# 第三元 needs_ctx=True 表示**必须落在安全语境内才算数**:「缺失 → 放行」这种通用措辞在非安全语境里
# 满地都是(实测 SKILL.md 里「主锚缺失且存在旧锚 → warn 放行」这条**文档命名 grandfather 规则**就被误报),
# 只有当同一行还谈到鉴权/权限/归属/签名/租户/越权/token/角色时,它才真是 fail-open。
# 而「视为管理员」「忽略权限」「跳过校验」这类**自证型**措辞不需要额外语境。
FAIL_OPEN_PATTERNS: List[Tuple[str, str, bool]] = [
    (r"(取不到|拿不到|为空|缺失|解析失败|查询异常|异常时|未获取到)[^。;；\n]{0,24}"
     r"(不过滤|不做过滤|不限制|无限制|放行|默认通过)",
     "安全判据 fail-open(取不到 → 放行)", True),
    (r"(取不到|拿不到|为空|缺失|解析失败|查询异常|异常时|未获取到)[^。;；\n]{0,24}"
     r"(视为(全部|管理员|超管|不限)|跳过校验|忽略(校验|权限))",
     "安全判据 fail-open(取不到 → 当成无限制)", False),
    (r"(默认放行|异常放行|失败放行|校验失败[^。;；\n]{0,10}放行)",
     "安全判据 fail-open(默认放行)", False),
]

# 安全语境词(needs_ctx 的判据):比 SECURITY_SIGNAL_RE 略宽,含"校验/租户/token/角色"等
SECURITY_CTX_RE = re.compile(r"鉴权|权限|归属|签名|验签|越权|租户|隔离|校验|授权|认证|登录|"
                             r"token|jwt|role|角色|数据范围|数据权限", re.IGNORECASE)

# ── 文档级信号词(W1/W2/W3 的触发前提) ──
SECURITY_SIGNAL_RE = re.compile(r"鉴权|权限校验|数据权限|越权|归属校验|数据归属|签名校验|验签|租户隔离|"
                                r"authorization|@PreAuthorize")
FAIL_CLOSED_DECL_RE = re.compile(r"fail[-\s]?closed|失败即拒|一律拒绝|直接拒绝|拒绝访问|拒绝并|"
                                 r"返回\s*40[13]|抛出?[^。\n]{0,8}(鉴权|权限|无权|未登录)[^。\n]{0,6}异常|"
                                 r"禁止[^。\n]{0,6}放行")
UPSTREAM_SIGNAL_RE = re.compile(r"上游|第三方|下游服务|外部系统|外部接口|@FeignClient|B\.7")
UPSTREAM_AUTHORITY_RE = re.compile(r"以上游契约为准|以第三方契约为准|以对方契约为准|上游变更[^。\n]{0,10}跟进")
UPSTREAM_FAILURE_ROW_RE = re.compile(r"上游|第三方|下游|不可达|无法连接|连接失败|超时|服务不可用")


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
    """归一化单元格文本:去粗体/反引号/引用符/空白,全角括号→半角。"""
    s = re.sub(r"[*`>\s]", "", s)
    return s.replace("（", "(").replace("）", ")")


def cell_matches_column(cell: str, concept: str) -> bool:
    c = _norm(cell).lower()
    if concept == "错误码":
        return "错误码" in c or "错误代码" in c or c in ("code", "errcode", "errorcode", "业务码")
    if concept == "HTTP Status":
        return "http" in c or "状态码" in c or "httpstatus" in c
    if concept == "触发条件":
        return "触发" in c or "条件" in c or "场景" in c
    if concept == "面向用户的中文提示":
        return ("提示" in c) or ("文案" in c) or ("message" in c and "提示" not in c) \
            or ("用户" in c and ("提示" in c or "文案" in c))
    if concept == "失败/降级行为":
        return ("行为" in c) or ("降级" in c) or ("处置" in c) or ("处理方式" in c)
    return False


def col_index(cells: List[str], concept: str) -> Optional[int]:
    for idx, c in enumerate(cells):
        if cell_matches_column(c, concept):
            return idx
    return None


def is_error_contract_header(cells: List[str]) -> bool:
    """签名判定:含「错误码」列的表 = 一张错误契约表(含旧版「错误码定义」表)。"""
    return any(cell_matches_column(c, "错误码") for c in cells)


def is_enum_table_header(cells: List[str]) -> bool:
    """签名判定:全局错误码**枚举表** = 含「错误码」列 + 至少一个枚举专有列
    (label / 业务含义 / 归属域)。

    ⚠️ 与接口错误契约表(错误码 | HTTP Status | 触发条件 | 提示 | 失败降级行为)**列签名互斥**,
    故不会互相误认。加这条是因为只靠 `#` 标题识别枚举章节太脆:实测枚举小节常写成**加粗行**
    (`**GlobalErrorCode 全局错误码**`)而非 markdown 标题,纯标题法一个码都收不到、
    继而误报"缺全局错误码枚举"。
    """
    if not any(cell_matches_column(c, "错误码") for c in cells):
        return False
    for c in cells:
        n = _norm(c).lower()
        if "label" in n or "显示文本" in n or "业务含义" in n or "归属域" in n or "所属域" in n:
            return True
    return False


def strip_code_fences(lines: List[str]) -> List[bool]:
    """返回逐行的「是否位于代码围栏内」标记(围栏行本身标 True)。"""
    inside = []
    in_code = False
    for line in lines:
        st = line.strip()
        if st.startswith("```") or st.startswith("~~~"):
            in_code = not in_code
            inside.append(True)
            continue
        inside.append(in_code)
    return inside


def collect_interface_sections(lines: List[str], in_code: List[bool]) -> List[Dict]:
    """识别接口章节:标题下、**第一个子标题之前**出现 `**Method:**` / `**Path:**` 信号。

    ⚠️ 「第一个子标题之前」这道限制是必须的:父章节(如 `#### B.2 API 契约定义`)的正文
    范围包含全部子接口,不加限制会把父章节也识别成一个接口,继而误报「父章节缺错误契约表」。
    """
    heads: List[Tuple[int, int, str]] = []   # (行号 idx, 层级, 标题文本)
    for i, line in enumerate(lines):
        if in_code[i]:
            continue
        m = HEADING_RE.match(line)
        if m:
            heads.append((i, len(m.group(1)), m.group(2)))

    sections: List[Dict] = []
    for k, (idx, level, title) in enumerate(heads):
        # 本章节正文范围:到下一个同级/上级标题为止
        end = len(lines)
        first_sub = len(lines)
        for j in range(k + 1, len(heads)):
            nidx, nlevel, _ = heads[j]
            if nlevel <= level:
                end = nidx
                break
            first_sub = min(first_sub, nidx)
        probe_end = min(end, first_sub)
        signal = any(METHOD_SIGNAL_RE.search(INLINE_CODE_RE.sub(" ", lines[m]))
                     for m in range(idx + 1, probe_end) if not in_code[m])
        if signal:
            sections.append({"title": title, "line": idx + 1, "start": idx, "end": end})
    return sections


def scan_tables(lines: List[str], in_code: List[bool], start: int, end: int) -> List[Dict]:
    """在 [start, end) 区间内提取全部错误契约表(含表头列位与数据行)。"""
    tables: List[Dict] = []
    i = start
    while i < end:
        if in_code[i] or "|" not in lines[i]:
            i += 1
            continue
        cells = split_row(lines[i])
        if is_separator_row(cells) or not is_error_contract_header(cells):
            i += 1
            continue
        # ⚠️ GFM 表头必须紧跟分隔行(`|---|---|`)。不校验这一条,任何**散文行里出现 `|`**
        #    都会被当成表头——实测 api-template.md 的说明文字
        #    「旧版「错误码 | HTTP Status | 说明」三列表已作废」就被识别成一张缺列的错误契约表。
        if not (i + 1 < end and "|" in lines[i + 1]
                and is_separator_row(split_row(lines[i + 1]))):
            i += 1
            continue
        header_line = i + 1
        missing = [c for c in REQUIRED_COLUMNS
                   if not any(cell_matches_column(x, c) for x in cells)]
        idx_map = {c: col_index(cells, c) for c in REQUIRED_COLUMNS}
        rows: List[Dict] = []
        j = i + 1
        if j < end and "|" in lines[j] and is_separator_row(split_row(lines[j])):
            j += 1
        while j < end and "|" in lines[j] and not in_code[j]:
            rcells = split_row(lines[j])
            if is_separator_row(rcells):
                j += 1
                continue
            if all(c == "" for c in rcells):
                break
            rows.append({"line": j + 1, "cells": rcells})
            j += 1
        tables.append({"header_line": header_line, "missing_columns": missing,
                       "idx_map": idx_map, "rows": rows})
        i = max(j, i + 1)
    return tables


def _header_cells(lines: List[str], idx: int) -> List[str]:
    return split_row(lines[idx])


def collect_enum_codes(lines: List[str], in_code: List[bool],
                       iface_starts: set, _iface_ranges=()) -> List[str]:
    """收集本文件里「全局错误码枚举」章节登记的全部错误码。

    靠**标题**识别枚举章节(全局错误码 / 错误码枚举 / 统一错误码 / ErrorCode…),
    并排除接口章节——接口自己的错误契约表也含「错误码」列,不能拿它当全局枚举的信源,
    否则"各接口自编码"这件事永远自证通过。
    """
    heads: List[Tuple[int, int]] = []
    for i, line in enumerate(lines):
        if in_code[i]:
            continue
        m = HEADING_RE.match(line)
        if m:
            heads.append((i, len(m.group(1))))

    codes: List[str] = []

    # 路径 ②(与标题法取并集):全文按**表签名**认枚举表,不依赖标题层级,
    #     但排除落在接口章节内的表(接口自己的错误契约表不能当全局枚举信源)。
    iface_ranges = [(s, e) for s, e in _iface_ranges]
    for tbl in scan_tables(lines, in_code, 0, len(lines)):
        hl = tbl["header_line"] - 1
        if any(s <= hl < e for s, e in iface_ranges):
            continue
        ci = tbl["idx_map"].get("错误码")
        if ci is None or not is_enum_table_header(_header_cells(lines, hl)):
            continue
        for row in tbl["rows"]:
            val = _norm(_cell(row, ci))
            if val and val.lower() not in EMPTY_MARKERS:
                codes.append(val)

    # 路径 ①:靠标题识别枚举章节
    for k, (idx, level) in enumerate(heads):
        if idx in iface_starts:
            continue
        title = INLINE_CODE_RE.sub(" ", lines[idx])
        if not ERROR_ENUM_HEADING_RE.search(title):
            continue
        end = len(lines)
        for j in range(k + 1, len(heads)):
            if heads[j][1] <= level:
                end = heads[j][0]
                break
        for tbl in scan_tables(lines, in_code, idx, end):
            ci = tbl["idx_map"].get("错误码")
            if ci is None:
                continue
            for row in tbl["rows"]:
                val = _norm(_cell(row, ci))
                if val and val.lower() not in EMPTY_MARKERS:
                    codes.append(val)
    return codes


def _cell(row: Dict, idx: Optional[int]) -> str:
    if idx is None or idx >= len(row["cells"]):
        return ""
    return row["cells"][idx].strip()


def _is_empty(val: str) -> bool:
    n = _norm(val).lower()
    return (val.strip() == "") or (n in EMPTY_MARKERS) or bool(PLACEHOLDER_RE.match(val.strip()))


def scan_file(path: Path, root: Path) -> Dict:
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        return {"file": str(path), "read_error": str(exc)}
    try:
        rel = str(path.relative_to(root))
    except ValueError:
        rel = str(path)

    lines = text.splitlines()
    in_code = strip_code_fences(lines)
    sections = collect_interface_sections(lines, in_code)

    criticals: List[Dict] = []
    warnings: List[Dict] = []
    iface_report: List[Dict] = []
    # 接口错误契约表里用到的全部错误码(供 main 与「全局错误码枚举」跨文件比对 → C8)
    code_cells: List[Dict] = []
    enum_codes = collect_enum_codes(lines, in_code, {s["start"] for s in sections},
                                    [(s["start"], s["end"]) for s in sections])

    for sec in sections:
        tables = scan_tables(lines, in_code, sec["start"], sec["end"])
        if not tables:
            criticals.append({"type": "C1 缺错误契约表", "file": rel, "line": sec["line"],
                              "detail": f"接口章节「{sec['title']}」内未找到「错误契约」表"
                                        f"(须含 5 列:{' | '.join(REQUIRED_COLUMNS)})"})
            iface_report.append({"title": sec["title"], "line": sec["line"], "tables": 0, "ok": False})
            continue
        ok = True
        for tbl in tables:
            if tbl["missing_columns"]:
                ok = False
                criticals.append({
                    "type": "C2 错误契约表缺列", "file": rel, "line": tbl["header_line"],
                    "detail": f"接口「{sec['title']}」错误契约表缺列: "
                              + " / ".join(tbl["missing_columns"])
                              + "(旧版「错误码 | HTTP Status | 说明」三列表已不满足核心原则 23)"})
            tip_idx = tbl["idx_map"].get("面向用户的中文提示")
            act_idx = tbl["idx_map"].get("失败/降级行为")
            code_idx = tbl["idx_map"].get("错误码")
            for row in tbl["rows"]:
                code = _norm(_cell(row, code_idx))
                if code and code.lower() not in EMPTY_MARKERS \
                        and not PLACEHOLDER_RE.match(_cell(row, code_idx).strip()):
                    code_cells.append({"line": row["line"], "code": code,
                                       "iface": sec["title"]})
                tip = _cell(row, tip_idx)
                act = _cell(row, act_idx)
                if tip_idx is not None:
                    if _is_empty(tip):
                        ok = False
                        criticals.append({"type": "C3 用户提示空/占位", "file": rel,
                                          "line": row["line"],
                                          "detail": f"「面向用户的中文提示」为空/占位(值「{tip[:40]}」)"})
                    elif not CJK_RE.search(tip):
                        ok = False
                        criticals.append({"type": "C3 用户提示非中文", "file": rel,
                                          "line": row["line"],
                                          "detail": f"「面向用户的中文提示」无中文(值「{tip[:40]}」),"
                                                    f"面向最终用户的文案必须是中文"})
                    else:
                        hit = INTERNAL_CODENAME_RE.search(tip)
                        if hit:
                            ok = False
                            criticals.append({"type": "C5 用户提示泄漏内部代号", "file": rel,
                                              "line": row["line"],
                                              "detail": f"用户提示含内部代号/拓扑「{hit.group(0)}」,"
                                                        f"须改为业务中文名(如「订单中心服务无法连接,"
                                                        f"请稍后再试」)"})
                if act_idx is not None and _is_empty(act):
                    ok = False
                    criticals.append({"type": "C4 失败/降级行为空", "file": rel, "line": row["line"],
                                      "detail": f"「失败/降级行为」为空/占位(值「{act[:40]}」);"
                                                f"确需降级须写明降级理由与范围"})
        iface_report.append({"title": sec["title"], "line": sec["line"],
                             "tables": len(tables), "ok": ok})

    # ── 文档级反模式(整篇扫,含代码块内的伪代码/注释) ──
    for i, line in enumerate(lines):
        if NEGATION_GUARD_RE.search(line):
            continue
        for pat, label in FAIL_AS_SUCCESS_PATTERNS:
            if re.search(pat, line, re.IGNORECASE):
                criticals.append({"type": "C6 失败伪装成功", "file": rel, "line": i + 1,
                                  "detail": f"{label}:{line.strip()[:90]}"})
                break
        for pat, label, needs_ctx in FAIL_OPEN_PATTERNS:
            if needs_ctx and not SECURITY_CTX_RE.search(line):
                continue
            if re.search(pat, line):
                criticals.append({"type": "C7 安全判据 fail-open", "file": rel, "line": i + 1,
                                  "detail": f"{label}:{line.strip()[:90]}"})
                break

    # ── 文档级 Important(仅告警) ──
    has_security = bool(SECURITY_SIGNAL_RE.search(text))
    has_upstream = bool(UPSTREAM_SIGNAL_RE.search(text))
    if has_security and not FAIL_CLOSED_DECL_RE.search(text):
        warnings.append({"type": "W1 缺 fail-closed 声明", "file": rel, "line": 0,
                         "detail": "文档含鉴权/权限/归属/签名类安全判据,但未声明"
                                   "「取不到/解析失败/查询异常 → 拒绝或报错」的 fail-closed 立场"})
    if has_upstream and not UPSTREAM_AUTHORITY_RE.search(text):
        warnings.append({"type": "W2 缺上游契约权威标注", "file": rel, "line": 0,
                         "detail": "文档引用了上游/第三方接口契约,但未标注「以上游契约为准,"
                                   "上游变更即需跟进」,设计易滞留旧契约"})
    if has_upstream and sections:
        rows_text = "\n".join(
            "|".join(r["cells"])
            for sec in sections
            for tbl in scan_tables(lines, in_code, sec["start"], sec["end"])
            for r in tbl["rows"])
        if not UPSTREAM_FAILURE_ROW_RE.search(rows_text):
            warnings.append({"type": "W3 缺上游不可达错误行", "file": rel, "line": 0,
                             "detail": "文档含上游/第三方调用,但所有错误契约表均无"
                                       "「上游不可达/超时/连接失败」类行"})

    return {"file": rel, "interfaces": iface_report, "enum_codes": enum_codes,
            "code_cells": code_cells, "criticals": criticals, "warnings": warnings}


def render_text(results: List[Dict], iface_total: int,
                criticals: List[Dict], warnings: List[Dict],
                global_codes: Optional[List[str]] = None) -> str:
    out: List[str] = []
    out.append("=== 「错误契约」硬核回检(维度 31 Critical · 核心原则 23) ===\n")
    out.append(f"识别到接口章节: {iface_total} 个")
    out.append(f"全局错误码枚举已登记: {len(global_codes or [])} 个\n")

    if iface_total == 0:
        # ⚠️ 只跳过**接口清单段落**,绝不能在这里 return —— 文档级 C6/C7 仍可能有 Critical,
        #    早期这里直接 return 并打印「跳过(退出码 0)」,而真实退出码是 1,
        #    报告正文与退出码**直接矛盾**,读报告的人/Agent 会判「无问题」。
        out.append("ℹ️ 未识别到接口章节 → **接口级检查(C0~C5/C8)跳过**;文档级 C6/C7 结果见下。")
        out.append("   识别信号 = 标题下、首个子标题之前出现 `**Method:**` / `**Path:**`。")
        out.append("   若本文档实际承载接口设计却未被识别,说明接口块未按 B.2 模板书写,")
        out.append("   QR 子 Agent 须按检查项 31 人工核验。")
        out.append("")

    for r in results:
        if r.get("read_error"):
            out.append(f"[读取失败] {r['file']}: {r['read_error']}")
            continue
        if not r["interfaces"]:
            continue
        out.append(f"📄 {r['file']}")
        for it in r["interfaces"]:
            mark = "✅" if it["ok"] else "❌"
            out.append(f"   {mark} L{it['line']} {it['title'][:60]}  (错误契约表 {it['tables']} 张)")
        out.append("")

    if criticals:
        out.append(f"❌ 不通过: {len(criticals)} 处 Critical\n")
        for v in criticals:
            out.append(f"  [{v['type']}] {v['file']}:L{v['line']}  {v['detail']}")
        out.append("")
    else:
        out.append("✅ Critical 全通过: 每个接口均有 5 列齐全的错误契约表,"
                   "用户提示逐行中文非空、无内部代号,失败/降级行为逐行填实\n")

    if warnings:
        out.append(f"⚠️ Important(不影响退出码,QR 子 Agent 须人工确认): {len(warnings)} 处")
        for w in warnings:
            out.append(f"  [{w['type']}] {w['file']}  {w['detail']}")
        out.append("")

    out.append("⚠️ 本脚本只做结构性回检。错误码取值是否恰当、降级范围是否合理、"
               "文案是否贴合业务语义,仍由 QR 子 Agent 按检查项 31 语义核验。")
    return "\n".join(out)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("path", type=Path, help="详细设计文档文件或目录")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    args = parser.parse_args(argv)

    if not args.path.exists():
        print(f"错误: 路径不存在 {args.path}", file=sys.stderr)
        return 2

    root = args.path if args.path.is_dir() else args.path.parent
    md_files = find_md_files(args.path)
    if not md_files:
        print("⚠️ 未发现任何 .md 文件", file=sys.stderr)
        return 2

    results: List[Dict] = []
    for f in md_files:
        # 跳过专职索引 / 待澄清清单(不承载接口契约)
        if f.name.startswith("00_") or "99_" in f.name:
            continue
        results.append(scan_file(f, root))

    iface_total = sum(len(r.get("interfaces", [])) for r in results)
    criticals = [c for r in results for c in r.get("criticals", [])]
    warnings = [w for r in results for w in r.get("warnings", [])]

    # ── 全局错误码枚举比对(C0/C8),**跨文件**:多文件拆分模式下枚举通常单独成篇
    #    (如 `05_字典与枚举索引.md` / `07_错误码枚举.md`),必须先把全目录的枚举并起来再比,
    #    否则一拆分就满屏误报。
    dir_mode = args.path.is_dir()
    global_codes = {c for r in results for c in r.get("enum_codes", [])}
    all_code_cells = [(r["file"], cc) for r in results for cc in r.get("code_cells", [])]
    if iface_total and all_code_cells:
        if not global_codes:
            msg = ("未找到「全局错误码枚举」章节(标题含 全局错误码 / 错误码枚举 / 统一错误码 / ErrorCode),"
                   "接口错误契约表的错误码无统一信源、必然各接口自编码;"
                   "须在 A.4 增设全局错误码枚举并按检查项 11 生成枚举类")
            if dir_mode:
                criticals.append({"type": "C0 缺全局错误码枚举", "file": str(args.path), "line": 0,
                                  "detail": msg})
            else:
                warnings.append({"type": "C0 缺全局错误码枚举(单文件模式降级)",
                                 "file": str(args.path), "line": 0,
                                 "detail": msg + "。⚠️ 当前是**单文件**模式,枚举可能定义在同目录"
                                                 "另一份文档里,故只告警;**请改传目录复检**"})
        else:
            for fname, cc in all_code_cells:
                if cc["code"] not in global_codes:
                    criticals.append({
                        "type": "C8 错误码未登记进全局枚举", "file": fname, "line": cc["line"],
                        "detail": f"接口「{cc['iface']}」用了错误码 `{cc['code']}`,"
                                  f"但它不在全局错误码枚举中(已登记 {len(global_codes)} 个)。"
                                  f"错误码必须全局统一分配、禁各接口自编"})

    # ⚠️ 「未识别到接口章节 → 跳过」只对**接口级**检查成立(C0~C5/C8 全部派生自接口章节,
    #    没有接口章节时它们本就不会产生),**不得**顺手把文档级的 C6/C7 也清掉——
    #    早期这里写的是 `criticals = []`,而那一刻能存在的 Critical **恰恰只有 C6/C7**,
    #    等于专门把"失败伪装成功 / 安全判据 fail-open"这两条丢进垃圾桶。
    #    实际场景很常见:B.3 异常处理章节常单独成篇(`01_详细设计.md`),那一篇里没有任何接口。

    passed = len(criticals) == 0
    if args.json:
        print(json.dumps({"passed": passed, "interface_total": iface_total,
                          "global_error_codes": sorted(global_codes),
                          "criticals": criticals, "warnings": warnings,
                          "files": results}, ensure_ascii=False, indent=2))
    else:
        print(render_text(results, iface_total, criticals, warnings,
                          sorted(global_codes)))

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
