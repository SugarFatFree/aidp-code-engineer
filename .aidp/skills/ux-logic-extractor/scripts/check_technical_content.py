#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技术内容硬核回检脚本 — ux-logic-extractor 维度 10「职责边界」

强制 grep 化硬核回检 PRD 中的技术实现细节。
覆盖 6 类正则,任一命中 ≥ 1 次即 QR 不通过、强制 PRD 重写:

  R1  技术栈词典           — Vue/React/Spring Boot/MyBatis Plus/Element Plus/UnoCSS
                            /MySQL/Redis/达梦/国产数据库/Nacos/Docker/Kubernetes 等
  R2  字段类型标注同行表    — 变量名 + 类型(string/number/boolean/integer/varchar)
                            同行 + 表格 `|` 分隔符,典型"字段表 / DTO 表"特征
  R3  完整 API 路径         — HTTP Method + URL(/api/... 或 /v\\d+/...) ,
                            或 `MM->>NN: GET /...` 之类时序图载荷
  R4  DDL 关键字           — CREATE TABLE / ALTER TABLE / NOT NULL /
                            PRIMARY KEY / FOREIGN KEY / VARCHAR(N) / DDL 标题
  R5  HTTP 错误码同行表     — 4xx/5xx HTTP 状态码出现在表格行,且**同行带 HTTP 错误码语境**
                            (紧邻错误描述单元格,或同行含"状态码/错误码/未授权/资源不存在"
                            等语境词)。⚠️ 已锚定错误码语义,不再误伤业务数值(如
                            `| 在线用户数 | 500 |`、`| 日活 | 404 |`)。
  R6  T_ 前缀表名           — `T_[A-Z][A-Z0-9_]+` 出现在正文(产品 PRD 不应出现表名)
  R0  代码块围栏/内容       — ``` / ~~~ 围栏及其内容(衍生规则;**``` mermaid 围栏豁免**,
                            业务流程图为 SKILL 强制要求,但 Mermaid 内容仍按 R1-R6 扫描)

使用:
  python check_technical_content.py <PRD文件或目录>
  python check_technical_content.py <PRD文件或目录> --json
  python check_technical_content.py <PRD文件或目录> --strict   # 启用 R1 严格模式

退出码: 0 = 通过 / 1 = 不通过
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# ---------------------------------------------------------------------------
# 正则与白名单(豁免词)
# ---------------------------------------------------------------------------

# R1 技术栈词典(成串出现的框架/中间件名)
TECH_STACK_TERMS = [
    r"Vue\s*3?", r"React\s*\d?", r"Angular", r"Svelte",
    r"Element\s*Plus", r"Ant\s*Design", r"UnoCSS", r"Tailwind\s*CSS?",
    r"Spring\s*Boot\s*\d?", r"Spring\s*Cloud", r"MyBatis(?:\s*Plus)?",
    r"Redis", r"MySQL", r"PostgreSQL", r"Oracle", r"达梦(?:\s*DM)?",
    r"国产数据库", r"MongoDB", r"ElasticSearch",
    r"Nacos", r"Apollo", r"Eureka",
    r"Nginx", r"Docker", r"Kubernetes", r"k8s",
    r"RabbitMQ", r"Kafka", r"RocketMQ",
    r"TypeScript", r"JavaScript",  # 语言名出现在技术栈列表中
]
# 词典中至少 2 个词同行命中视为"技术栈成串描述"(单个词允许业务文档偶提)
TECH_STACK_PATTERN = re.compile("|".join(TECH_STACK_TERMS), re.IGNORECASE)

# R2 字段类型同行表(变量名 + 类型 + 表格管道)
TYPE_KEYWORDS = r"(?:string|number|boolean|integer|int|long|float|double|char|byte|short|" \
                r"varchar|text|datetime|timestamp|date|json|array|object|void|" \
                r"String|Number|Boolean|Integer|Long|Float|Double|Date|List|Map)"
# 同行同时出现:管道符、camelCase 标识符、类型词
FIELD_TABLE_PATTERN = re.compile(
    r"\|.*\b[a-z][a-zA-Z0-9]*[A-Z][a-zA-Z0-9]*\b.*\|.*\b" + TYPE_KEYWORDS + r"\b.*\|"
)

# R3 完整 API 路径(HTTP 动词 + 路径)
API_PATH_PATTERN = re.compile(
    r"\b(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\b\s+/\S+",
    re.IGNORECASE,
)
# R3-表格: 表格管道分隔的 HTTP Method 列 + URL 列(产品 PRD 表格高频格式)
API_TABLE_PATTERN = re.compile(
    r"\|\s*(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s*\|\s*/\S+",
    re.IGNORECASE,
)
# 时序图箭头载荷 FE->>BE: GET /xxx
SEQUENCE_API_PATTERN = re.compile(
    r"->>?[^:\n]+:\s*\b(GET|POST|PUT|DELETE|PATCH)\b\s+/",
    re.IGNORECASE,
)

# R4 DDL 关键字(出现 = 不通过)
DDL_PATTERN = re.compile(
    r"\b(CREATE\s+TABLE|ALTER\s+TABLE|DROP\s+TABLE|NOT\s+NULL|PRIMARY\s+KEY|"
    r"FOREIGN\s+KEY|UNIQUE\s+KEY|VARCHAR\s*\(|INT\s*\(\s*\d+\s*\)|BIGINT\b|"
    r"AUTO_INCREMENT|ON\s+UPDATE\s+CURRENT_TIMESTAMP|ENGINE\s*=)",
    re.IGNORECASE,
)

# R5 HTTP 错误码同行表(4xx/5xx 状态码 + 表格)
# ⚠️ 必须锚定"HTTP 错误码语义",否则会误伤业务数值(如 `| 在线用户数 | 500 |`、
#    `| 日活 | 404 |` 这类落在 400~599 区间的合法计数/金额/阈值)。
# 判定条件(二选一):
#   a) 状态码单元格两侧都是表格管道且**整行含 HTTP 错误码语境词**
#      (HTTP / 状态码 / 错误码 / 未授权 / 无权限 / 资源不存在 / 服务错误 / Unauthorized 等);
#   b) 状态码单元格**紧邻**一个以"错误/异常/未/无/超时/不存在/失败/拦截/服务"等开头的错误描述单元格
#      (典型 `| 404 | 资源不存在 |`、`| 500 | 服务繁忙 |`)。
_HTTP_STATUS = r"(?:4\d{2}|5\d{2})"
# a) 整行:表格里出现 4xx/5xx 状态码 且 同行含 HTTP 错误码语境词(用前视断言绑定,单行判定)。
#    状态码允许"独占单元格"(`| 404 |`)或"码+描述同格"(`|401 未授权|`),关键靠语境词区分
#    业务数值(纯计数/金额没有错误码语境词,不会命中)。
HTTP_STATUS_CONTEXT_PATTERN = re.compile(
    r"(?=.*(?:HTTP|状态码|错误码|响应码|未授权|无权限|越权|资源不存在|服务(?:异常|错误|繁忙)|"
    r"登录(?:已)?过期|请求超时|Unauthorized|Forbidden|Not\s*Found|Internal\s*Server))"
    r".*\|\s*\b(" + _HTTP_STATUS + r")\b",
    re.IGNORECASE,
)
# b) 4xx/5xx 单元格紧邻一个错误描述单元格(下一格以错误语义词开头)
HTTP_STATUS_TABLE_PATTERN = re.compile(
    r"\|\s*\b" + _HTTP_STATUS + r"\b\s*\|\s*"
    r"(?:HTTP|请|登录|无|未|越权|资源|服务|系统|网络|请求|参数)?[^|]*"
    r"(?:错误|异常|未授权|无权限|不存在|过期|超时|失败|拦截|繁忙|服务器)"
)

# R6 T_ 前缀表名(纯大写下划线)
T_PREFIX_TABLE_PATTERN = re.compile(r"\bT_[A-Z][A-Z0-9_]{2,}\b")

# 业务白名单(避开误报):豁免标题、显式反例块
# 注意:
#   - 引用块/标题豁免(^>、^#)是为了避免文档里的语义说明本身被检测
#   - "严禁/禁止/不得" 不能整行豁免 — 否则 PRD 中"严禁 POST /api/x" 这类反例说明本身
#     会让真实违规也被无脑放行;改为只在 5 行内有 ❌ 反例块标记时才豁免
EXEMPT_LINE_PATTERNS = [
    re.compile(r"^\s*>"),  # 引用块
    re.compile(r"^\s*#"),  # 标题
    re.compile(r"已剥离技术细节"),  # 净化记录表本身
]
# 显式反例块标记:命中即视为反例上下文,豁免其后 N 行
#
# ⚠️ **`✅` 曾在这个名单里,是一个恒绿漏洞、已移除**：
#    合规 PRD 里 `✅`/`⏳` 是**状态值**不是反例标记——SKILL.md 强制产出的三张表
#    (「六·2 数据来源说明」交付状态列、「权限差异矩阵」每格、「五·N 复用清单」复用状态列)
#    行行带 `✅`,于是**整表逐行自我豁免**,R1~R6 全部不扫。实测：同样两行内容,
#    带 `✅` → exit 0 放行;删掉 `✅` → 精确报 2 处 R3_完整API路径。即 SKILL.md 自己写的
#    「严禁写 HTTP Method+URL,R3 会拦截」在最该拦的强制表里恒不生效。
#    `❌` 保留但收紧:必须**同行**并存显式反例语境词才算反例区,否则权限矩阵的 `❌ 不可访问`
#    同样会把整表豁免掉。
COUNTEREXAMPLE_MARK = re.compile(r"正反对比|反例|对比示例|错误示例")
# `❌` 单独一档:需**同行或紧邻上文**有反例语境词。
# ⚠️ 词表与「紧邻上文」两条都不能少：
#    ① 词表只收「错误示例」不收「错误写法/反模式」时，一字之差即误报——本仓库自家文档
#       用的正是「正确写法/错误写法」「严禁的反模式」这类措辞；
#    ② 反例块最常见的排布是**语境标题在上一行、下面跟一串裸 `❌`**
#       （如 SKILL.md「**严禁的反模式:**」后接四行 `❌ …`），只判同行则一行都豁免不到。
#    放宽到「上文 N 行」不会让已修好的 `✅` 恒绿漏洞复发——`✅` 已从标记里彻底移除，
#    而权限矩阵那种 `| 页面访问 | ❌ 不可访问 |` 表格的上文是表头、不含反例语境词，照常受检。
COUNTEREXAMPLE_MARK_WEAK = re.compile(r"❌")
#    ③ ⚠️ 词表只收**谈论「示例」本身的元语言**，严禁收普通业务禁令词：
#       `严禁|禁止|不允许` 三个词在 PRD 正文里是家常便饭（「禁止重复提交」「不允许越权访问」），
#       一旦入表，其后 3 行内任何 `❌` 都会开启反例窗口，把真违规（字段类型表 / 完整 API 路径）
#       整段豁免掉——实测含一句 `**禁止**…` 的 fixture 由「发现 2 处违规 rc=1」变成「✅ 通过 rc=0」。
#       与 dev-logic-architect 的 check_no_fabricated_fallback 那次「护栏词表混入普通描述词
#       致 Critical 整档失效」是同一个错误，勿再照抄词表了事。
#       注释②举的「**严禁的反模式:**」由 `反模式` 命中，不依赖 `严禁`。
COUNTEREXAMPLE_CONTEXT = re.compile(
    r"反例|反模式|错误示例|错误写法|正确写法|正例|误写|不得写|不要写|正反对比")
COUNTEREXAMPLE_CONTEXT_LOOKBACK = 3  # `❌` 行向上回看几行找语境词
COUNTEREXAMPLE_WINDOW = 3  # 标记后 N 行视为反例区

CHECKS = [
    ("R1_技术栈词典", "技术栈成串描述", TECH_STACK_PATTERN, 2),  # >=2 个不同词同行
    ("R2_字段类型标注", "字段类型同行表(变量名+类型)", FIELD_TABLE_PATTERN, 1),
    ("R3_完整API路径", "HTTP Method + URL 路径", API_PATH_PATTERN, 1),
    ("R3_API表格", "HTTP Method + URL 表格格式", API_TABLE_PATTERN, 1),
    ("R3_时序图API", "时序图载荷含 HTTP Method+路径", SEQUENCE_API_PATTERN, 1),
    ("R4_DDL关键字", "DDL/SQL 关键字(CREATE TABLE/VARCHAR 等)", DDL_PATTERN, 1),
    ("R5_HTTP错误码表", "HTTP 4xx/5xx 状态码 + 错误描述同行表", HTTP_STATUS_TABLE_PATTERN, 1),
    ("R5_HTTP错误码语境", "HTTP 4xx/5xx 状态码 + 同行错误码语境词", HTTP_STATUS_CONTEXT_PATTERN, 1),
    ("R6_T_前缀表名", "T_前缀大写表名", T_PREFIX_TABLE_PATTERN, 1),
]


def is_exempt_line(line: str) -> bool:
    return any(p.search(line) for p in EXEMPT_LINE_PATTERNS)


def scan_file(path: Path) -> List[Dict]:
    """返回 issue 列表,每条 {file, line, rule, snippet, count}"""
    issues: List[Dict] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception as exc:
        return [{"file": str(path), "line": 0, "rule": "READ_ERROR",
                 "snippet": str(exc), "count": 0}]

    # 反例窗口:含 ❌/✅/反例 标记后的若干行视为反例上下文,豁免
    counterexample_remaining = 0

    # 代码块状态: None = 不在代码块内; "mermaid" = Mermaid 图(SKILL 强制要求,豁免 R0,
    #   但内容仍按 CHECKS 扫描以拦截时序图载荷中的 GET /api/x 等); 其他 = 普通代码块(R0 违规)
    in_code_block = None
    for line_num, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            if in_code_block is None:
                # 开围栏:提取语言标识
                lang = stripped.lstrip("`~").strip().lower()
                in_code_block = lang or "plain"
                if in_code_block != "mermaid":
                    # 非 Mermaid 代码块围栏出现在 PRD 内即视为不通过(R4 衍生)
                    issues.append({
                        "file": str(path), "line": line_num,
                        "rule": "R0_代码块围栏",
                        "snippet": stripped[:120], "count": 1,
                    })
            else:
                # 闭围栏
                if in_code_block != "mermaid":
                    issues.append({
                        "file": str(path), "line": line_num,
                        "rule": "R0_代码块围栏",
                        "snippet": stripped[:120], "count": 1,
                    })
                in_code_block = None
            continue
        if in_code_block is not None and in_code_block != "mermaid":
            issues.append({
                "file": str(path), "line": line_num,
                "rule": "R0_代码块内容",
                "snippet": line.rstrip()[:120], "count": 1,
            })
            continue
        # Mermaid 块内容不豁免 CHECKS 扫描(时序图载荷 GET /api/x 仍须拦截),落入下方通用扫描

        # 反例窗口扫描（`❌` 须同行或紧邻上文有反例语境词，防状态列整表豁免）
        if COUNTEREXAMPLE_MARK.search(line):
            counterexample_remaining = COUNTEREXAMPLE_WINDOW
        elif COUNTEREXAMPLE_MARK_WEAK.search(line):
            # ⚠️ 循环变量是 1-based 的 `line_num`，切 `lines` 必须换回 0-based。
            # 此处曾直接写 `idx`（从未定义）→ 任何含 `❌` 的文档一律 NameError 崩溃，
            # 而 SKILL.md 强制每个页面产出的「权限差异矩阵」模板逐行带 `❌`，
            # 等于照模板生成的 PRD 100% 必崩、且 rc=1 被 QR 读成「维度 10 不通过」。
            i0 = line_num - 1
            lo = max(0, i0 - COUNTEREXAMPLE_CONTEXT_LOOKBACK)
            if COUNTEREXAMPLE_CONTEXT.search("\n".join(lines[lo:i0 + 1])):
                counterexample_remaining = COUNTEREXAMPLE_WINDOW

        if is_exempt_line(line):
            continue

        if counterexample_remaining > 0:
            counterexample_remaining -= 1
            continue

        for rule_id, rule_desc, pattern, min_hits in CHECKS:
            matches = pattern.findall(line)
            if not matches:
                continue
            if rule_id == "R1_技术栈词典":
                # 至少 2 个不同的技术栈词
                unique = {m.lower() if isinstance(m, str) else str(m).lower()
                          for m in matches}
                if len(unique) < min_hits:
                    continue
            issues.append({
                "file": str(path), "line": line_num,
                "rule": rule_id, "rule_desc": rule_desc,
                "snippet": line.rstrip()[:160],
                "count": len(matches),
            })
    return issues


def collect_targets(arg: str) -> List[Path]:
    p = Path(arg)
    if p.is_file():
        return [p]
    if p.is_dir():
        return sorted(p.rglob("*.md"))
    return []


def main() -> int:
    ap = argparse.ArgumentParser(description="ux-logic-extractor 维度 10 硬核回检")
    ap.add_argument("target", help="PRD 文件或目录")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    ap.add_argument("--strict", action="store_true",
                    help="严格模式(R1 单个技术栈词即不通过)")
    args = ap.parse_args()

    if args.strict:
        # 严格模式: R1 改为命中 >=1 即违规
        for i, (rid, desc, pat, _) in enumerate(CHECKS):
            if rid == "R1_技术栈词典":
                CHECKS[i] = (rid, desc, pat, 1)

    targets = collect_targets(args.target)
    if not targets:
        print(f"错误: 未找到目标文件: {args.target}", file=sys.stderr)
        return 2  # 入参错。原先返回 1 = **假红**:把一次路径写错升级成"PRD 产物违规",触发无谓重写返工

    all_issues: List[Dict] = []
    for f in targets:
        all_issues.extend(scan_file(f))

    if args.json:
        print(json.dumps({
            "passed": len(all_issues) == 0,
            "scanned_files": len(targets),
            "issue_count": len(all_issues),
            "issues": all_issues,
        }, ensure_ascii=False, indent=2))
        return 0 if not all_issues else 1

    if not all_issues:
        print(f"✅ 通过: 扫描 {len(targets)} 个 PRD 文件,未发现技术内容残留")
        return 0

    print(f"❌ 不通过: 扫描 {len(targets)} 个文件,发现 {len(all_issues)} 处违规\n")
    by_rule: Dict[str, List[Dict]] = {}
    for it in all_issues:
        by_rule.setdefault(it["rule"], []).append(it)
    for rule, items in sorted(by_rule.items()):
        print(f"  [{rule}] {len(items)} 处:")
        for it in items[:5]:
            print(f"    {it['file']}:L{it['line']}  {it['snippet']}")
        if len(items) > 5:
            print(f"    ... 另 {len(items) - 5} 处")
        print()
    print("修复建议: 删除技术细节,改用业务中文描述;模式 B 融合时执行「上游内容净化」Step。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
