#!/usr/bin/env python3
"""
自测用例格式校验脚本

检查 dev-manual-testcase 生成的用例文档是否满足强制规则:
1. 入口检查:
   - 套件组织文档(含 `套件 SUITE-NN`/`测试套件 TS-NNN` 标题):入口流程由套件级
     Suite Setup 承担,用例内**不应**重复入口(由 check_testcase_suite.py 主检,本脚本跳过用例级入口检查)
   - 非套件组织的旧式平铺文档:每条用例必须从入口开始(步骤 1 = 打开浏览器/客户端/APP,步骤 2 = 访问 URL)
2. 用例步骤表四要素完备(操作动作 / 操作对象 / 操作数据 / 预期现象)
3. 禁止代码级动作关键词(调用接口/SQL/数据库/Redis 等)
   - 窄口径豁免:仅「统计/汇总/计数/金额」字段的 `[双源对账]` 用例,允许在其「双源对账」专段内
     出现等价 SQL 作**断言依据**(非操作步骤);步骤表操作列里的 SQL 仍一律拦截。
4. 禁止 DOM 选择器(#id, .class, xpath 等)
5. 专职索引存在(00_索引.md)+ 自测方案存在(01_研发自测方案.md)+ 多文件主文档存在(02_*总览*.md)+ 子文档序号合规

用法:
  python check_testcase_format.py <用例文档路径或目录>
  python check_testcase_format.py <路径> --json
"""

import argparse
import json
import re
import sys
from pathlib import Path

# 允许的"操作动作"动词
ALLOWED_ACTIONS = {
    "打开", "访问", "登录", "点击", "双击", "右键", "长按", "悬停", "输入", "清空",
    "选择", "勾选", "取消勾选", "上传", "下载", "拖拽", "滚动", "切换",
    "返回", "刷新", "关闭", "等待", "确认", "观察", "记录", "扫码", "滑动",
    # 检查/执行/重复 主要用于 mock 清理验证等特殊用例(核心原则 1 的例外,见 SKILL.md TC-PAY-004)
    "检查", "执行", "重复",
    # 核对 用于「列集合 vs 需求字段」逐列核对用例(维度 17 / SKILL.md 第五步之二)
    "核对",
}

# 禁止的代码级动作关键词
FORBIDDEN_PATTERNS = [
    (r"\b(?:调用接口|发送请求|发起请求)\b", "出现非 UI 操作:调用接口/发送请求"),
    (r"\b(?:POST|GET|PUT|DELETE|PATCH)\s+/\w", "出现 HTTP 方法 + 路径,属于接口调用"),
    (r"\b(?:执行|运行)\s*SQL\b", "出现 SQL 执行"),
    # DML 关键字 + 子句关键字在同一表格单元格内([^\n|] 限定不跨列 / 不跨行),覆盖
    # SELECT ... FROM / INSERT ... INTO|VALUES / UPDATE ... SET / DELETE ... FROM|WHERE 等真实 SQL,
    # 不再要求关键字紧邻(旧正则 `SELECT\s+FROM` 会漏掉 `SELECT COUNT(*) FROM t`)。
    # 注:[双源对账] 专段 / 前置数据编排段均不在 extract_step_table 范围内,不会被本规则误伤。
    (r"\b(?:SELECT|INSERT|UPDATE|DELETE)\b[^\n|]{0,80}?\b(?:FROM|INTO|TABLE|SET|WHERE|VALUES)\b", "出现 SQL 语句"),
    (r"\b(?:查询|查看)数据库\b", "出现数据库操作"),
    (r"\b(?:查看|检查)\s*Redis\b", "出现 Redis 缓存查看(非 UI 可视)"),
    (r"\b(?:写入|读取)缓存\b", "出现缓存操作(非 UI 可视)"),
]

# 禁止的 DOM 选择器特征(出现在"操作对象"列)
DOM_SELECTOR_PATTERNS = [
    (r"#[A-Za-z][\w-]*", "出现疑似 CSS id 选择器"),
    (r"\.[a-z][a-z0-9-]+(?:-[a-z0-9]+)+", "出现疑似 CSS class 选择器"),
    (r"//\*\[@|xpath", "出现 XPath 选择器"),
    (r"\bdata-\w+=", "出现 data-* 属性选择器"),
]

# ── 已知用例族类型标记(供识别 / 避免误判格式) ──
# 这些标记出现在用例标题或「类型」字段。除 [双源对账] 走窄口径 SQL 豁免(下方专门处理)外,
# 其余均为纯 UI / 断言类标记,格式检查中不构成禁用动作——尤其 [反向-残留] 与 [文案一致性]
# 的反向断言 DSL「断言(反向):不存在文本"X"」只是页面可见文案断言,不是 SQL/接口/DOM 操作,
# 不应被 FORBIDDEN_PATTERNS / DOM_SELECTOR_PATTERNS 误判(它们只扫测试步骤表,断言行不在其内)。
# [文案一致性]:语义/口径变更类文案一致性用例族(SKILL 第五步之八 / 方法论八之五),比照
# [反向-残留] 处理——复用同一反向 DSL、同判失败语义,格式检查无需特殊豁免、仅在此登记为已知标记。
# [外部调用方]:WebMCP 安全用例族(维度 20,**条件启用**——仅调用方传 webmcp_enabled: true 时存在)。
#   它验的是确认门/脱敏/不扩权对**任意调用方**都成立,故步骤会写「以外部调用方身份调用工具」。
#   ⚠️ **两道检查要分开看,别只核一道**(此前只核了前者、结论不完整):
#     ① FORBIDDEN_PATTERNS:`调用接口|发送请求|发起请求` 带词边界,「调用工具『X』」不命中 → 放行 ✅
#     ② ALLOWED_ACTIONS:**动作动词白名单会命中**——实测把动作写成「调用」/「发起」
#        均报 Important `invalid_action_verb`(而 flow-qr-dispatch 明确要求子 Agent 读
#        `by_level.Important` 并入维度判定 → 合规用例必被判不通过)。
#   **处置:不动脚本,改为在 SKILL/分片里规定动作动词用既有的「执行」**(实测放行),对象列写
#   「以外部调用方身份调用工具『X』」。理由:往白名单加「调用」会削弱核心原则 1 对
#   「调用接口」这类代码级动作的拦截面,代价大于收益。
KNOWN_CASE_TYPE_TAGS = (
    "[双源对账]", "[反向-残留]", "[文案一致性]", "[PRD存在性]", "[回归]", "[集成]", "[缓存场景]",
    "[外部调用方]",
    # 第三方临时 mock 流程的两个既有族标记(见 references/flow-third-party.md 示例)
    "[真实接口已交付-清理验证]", "[待第三方交付-切换测试]",
    # [还原度] = 通用还原度套件(维度 21,判据见 references/flow-fidelity-suite.md)。
    # ⚠️ 该族**刻意不进** auto-test-runner 的 CRITICAL_FAMILY_MARKERS:十条模板项里既有
    #    「导出只导当前页」这种确定的 Critical,也有「截断没 tooltip」这种 Important,
    #    整族锁 Critical 会把后者拔高成阻断项。执行结果按每条用例自身 severity 判。
    "[还原度]",
    # [日志可追溯] = 上游调用日志断言族(SKILL 第五步之十 / 通用规则 约定40,**条件触发**:
    #   仅本次迭代新增或改动了出站调用时追加,不对全部用例铺开)。
    #   断言写在「日志可追溯」专段里,该段已由 extract_step_table 的 end-marker **从 step_block 剥离**
    #   (与 `**双源对账**` 同款),故不需要放宽任何 FORBIDDEN_PATTERNS 拦截面;
    #   确需在步骤里体现"去看日志"时,动作动词只用既有白名单里的「观察」/「检查」/「记录」
    #   ——与 [外部调用方] 同一处置思路:**不动脚本、改用既有动词**(往白名单加「grep」「执行命令」
    #   会削弱核心原则 1 对代码级动作的拦截面,代价大于收益)。
    "[日志可追溯]",
)

# ── 双源对账用例:窄口径 SQL 豁免识别 ──
# 仅「统计/汇总/计数/金额」字段的 [双源对账] 用例,允许在其「双源对账」专段内出现等价 SQL
# 作断言依据(非操作步骤);步骤表操作列内的 SQL 仍由 FORBIDDEN_PATTERNS 拦截。
DUAL_SOURCE_TAG = "[双源对账]"
DUAL_SOURCE_SECTION_RE = re.compile(r"\*\*双源对账\*\*\s*[::]")
# 段内 SQL 迹象(用于识别是否出现 SQL,而非用于拦截)
_SQL_IN_TEXT_RE = re.compile(r"\bSELECT\b|\bFROM\b|执行\s*SQL|查询\s*数据库|查询数据库", re.IGNORECASE)
# 软删除 / 状态过滤条件迹象(双源对账 SQL 必须含,否则易漏「软删除/状态未过滤」缺陷)
_SOFTDELETE_STATUS_RE = re.compile(
    r"删除|is_deleted|is_delete|del_flag|deleted|逻辑删除|软删除|状态|status|state|有效|valid|enable|enabled|生效",
    re.IGNORECASE)

# markdown 链接目标 [文本](url#锚点) 与内联代码 `code#ref` 中的 `#锚点` / `.ext`
# 属于合法溯源(如 L4 代码引用 `i18n/zh-CN.json#user.create.success`、步骤验收锚点
# (验收: [§C-2.3](../docs/.../19_测试方案.md#C-2-3))),不是 UI 定位选择器。
# DOM 扫描前先剥除它们,避免把 SKILL 自己强制要求的溯源锚点误判成 CSS 选择器。
_MD_LINK_TARGET_RE = re.compile(r"\]\([^)]*\)")
_INLINE_CODE_RE = re.compile(r"`[^`]*`")


def strip_links_and_code(text: str) -> str:
    """剥除内联代码与 markdown 链接目标,只保留可见文本供 DOM 选择器扫描。"""
    text = _INLINE_CODE_RE.sub("", text)
    text = _MD_LINK_TARGET_RE.sub("]", text)
    return text

# 入口判定正则
ENTRY_STEP1_PATTERN = re.compile(r"^\s*\|\s*1\s*\|\s*打开\s*\|", re.MULTILINE)
ENTRY_STEP2_PATTERN = re.compile(r"^\s*\|\s*2\s*\|\s*访问\s*\|", re.MULTILINE)

# 用例块识别(兼容 "#### TC-XXX:" 与 "#### 用例 TC-XXX:"、3~5 级标题、中英文冒号)
# ⚠️ 层级 3~6 + 冒号可选,必须与下游 auto-test-runner/scripts/tasks_state.py 的
#    CASE_RE 保持同宽。此处曾收窄到 #{3,5} 且强制冒号,导致 6 级标题/无冒号标题的用例
#    整个不进检查集合——脚本照常打印"✅ 通过" exit 0,而下游 tasks_state 照跑,
#    于是裸 SQL、CSS 选择器等 Critical 违规被静默放行。放宽后须跑 --selftest 回归。
TESTCASE_HEADER = re.compile(r"^#{3,6}\s*(?:用例\s+)?(TC-[A-Za-z0-9_-]+)\s*[:：]?\s*(.*)$", re.MULTILINE)

# 套件组织识别(套件组织文档跳过用例级入口检查,入口由 Suite Setup 承担)
SUITE_HEADER = re.compile(
    r"^#{2,4}\s+(?:测试)?套件\s+(?:SUITE|TS)-[A-Za-z0-9][A-Za-z0-9-]*", re.MULTILINE)

# 步骤表行(以 | 开头 + 数字 + | 开头)
# ⚠️⚠️ **步骤号后允许一个可选的方括号标注**(如 `| 1 [加速可选] |`,见 flow-principles.md
#    「步骤级 `[加速可选]` 标注」)。**这一段不能省** —— 实测:不认它时,带标注的行
#    **整行匹配不上**,于是该行不被当成步骤行 → 四要素完备性 / 动作动词白名单 / 禁 SQL 与选择器
#    **一整套检查对这些行全部失效**,而输出里只表现为「缺少 **测试步骤**: 章节」这类看似无关的报错,
#    甚至在别的文档形态下**一条都不报** = **假绿**。
# ⚠️ 用**非捕获组**,group 编号不变(下游 `step_no, action, obj, data, expect = m.groups()` 依赖它)。
STEP_ROW_PATTERN = re.compile(
    r"^\s*\|\s*(\d+)\s*(?:\[[^\]]*\]\s*)?\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*$")


def scan_text_around_match(text: str, start: int, end: int, pattern: re.Pattern):
    """获取匹配上下文(行号)"""
    line_no = text.count("\n", 0, start) + 1
    return line_no


def split_testcases(content: str):
    """将文档按用例块切分"""
    cases = []
    matches = list(TESTCASE_HEADER.finditer(content))
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        cases.append({
            "tc_id": m.group(1),
            "title": m.group(2).strip(),
            "content": content[start:end],
            "start_line": content.count("\n", 0, start) + 1,
        })
    return cases


# 用例标题里的方括号标记(排除 markdown 链接 `[文本](url)` 与章节锚点 `[§…]`)
CASE_TAG_RE = re.compile(r"\[([^\[\]()§]{2,12})\](?!\()")


def check_case_type_tag(case: dict):
    """未登记的用例族标记 → Info。

    ⚠️ **刻意只报 Info,不报 Important。** `flow-qr-dispatch.md` 要求 QR 子 Agent 读
    `by_level.Important` 并入维度判定,若把"标记不在清单里"判 Important,下游产物里任何
    临时/项目自定义标记都会让**合规用例被判不通过**——那是本仓库反复踩过的假红方向。
    Info 既让 `KNOWN_CASE_TYPE_TAGS` 真正被消费(此前它是从未被读取的死常量,
    往里加标记是 no-op,却给人"新标记已被机检承认"的假象),又不制造阻断。
    典型收益:把 `[还原渡]` 这类**错字标记**显出来。
    """
    issues = []
    for tag in CASE_TAG_RE.findall(case.get("title") or ""):
        full = "[%s]" % tag
        if full not in KNOWN_CASE_TYPE_TAGS:
            issues.append({
                "level": "Info",
                "rule": "unknown_case_tag",
                "msg": f"{case['tc_id']} 标题里的标记 {full} 不在已登记的用例族清单内"
                       f"(疑似错字或项目自定义标记;确为新用例族请登记进 KNOWN_CASE_TYPE_TAGS)",
            })
    return issues


def check_entry(case: dict):
    """检查用例是否从入口开始(仅扫描测试步骤区域)"""
    issues = []
    step_block, _ = extract_step_table(case["content"])
    if not step_block:
        return issues  # missing_step_section 已由 check_steps_four_elements 报告
    if not ENTRY_STEP1_PATTERN.search(step_block):
        issues.append({
            "level": "Critical",
            "rule": "entry_step_1",
            "msg": f"{case['tc_id']} 步骤 1 不是\"打开\"动作,未从浏览器/客户端/APP 入口开始",
        })
    if not ENTRY_STEP2_PATTERN.search(step_block):
        issues.append({
            "level": "Critical",
            "rule": "entry_step_2",
            "msg": f"{case['tc_id']} 步骤 2 不是\"访问\"动作,缺少访问入口 URL 步骤",
        })
    return issues


def extract_step_table(body: str):
    """从用例正文中提取 **测试步骤**: 与 **预期总结**: / **跨系统验证** / 文档其他二级标题之间的内容"""
    start_match = re.search(r"\*\*测试步骤\*\*\s*[::]", body)
    if not start_match:
        return "", 0
    start = start_match.end()
    tail = body[start:]
    end_idx = len(tail)
    for end_marker in (
        r"\*\*预期总结\*\*\s*[::]",
        r"\*\*跨系统验证\*\*\s*[::]",
        r"\*\*双源对账\*\*\s*[::]",   # 双源对账专段(段内 SQL 作断言依据,不属步骤表)
        # 日志可追溯专段(约定40 / 第五步之十):段内断言引用服务端日志的**请求行**,形态天然是
        # 「method + /path」——不把它从 step_block 剥离,`断言:日志中存在 "POST /v2/sms/send" 请求行`
        # 这种最自然的写法会命中 FORBIDDEN_PATTERNS 的「HTTP 方法 + 路径」判 Critical(实测)。
        r"\*\*日志可追溯\*\*\s*[::]",
        r"\*\*回归路径\*\*\s*[::]",
        r"\*\*实际结果",
        r"^##\s",  # 二级章节
        r"^###\s",  # 三级章节
        r"^---\s*$",  # 分隔线
    ):
        m = re.search(end_marker, tail, re.MULTILINE)
        if m and m.start() < end_idx:
            end_idx = m.start()
    return tail[:end_idx], start


def extract_dual_source_section(body: str):
    """提取用例内 **双源对账**: 专段(至下一加粗小节 / 标题 / 分隔线)。

    该段用于「统计/汇总/计数/金额」字段的 [双源对账] 用例,段内给 ①页面取值方式
    ②等价 SQL(含软删除/状态过滤)③断言「页面值 == SQL 值」;段内 SQL 仅作断言依据、非操作步骤。
    """
    m = DUAL_SOURCE_SECTION_RE.search(body)
    if not m:
        return ""
    start = m.end()
    tail = body[start:]
    end_idx = len(tail)
    for end_marker in (
        r"\*\*预期总结\*\*\s*[::]",
        r"\*\*实际结果",
        r"^#{2,5}\s",
        r"^---\s*$",
    ):
        mm = re.search(end_marker, tail, re.MULTILINE)
        if mm and mm.start() < end_idx:
            end_idx = mm.start()
    return tail[:end_idx]


def check_steps_four_elements(case: dict):
    """检查每个步骤是否四要素完备(仅扫描 **测试步骤**: 区域内)"""
    issues = []
    body = case["content"]
    step_block, offset = extract_step_table(body)
    if not step_block:
        # 用例缺失测试步骤章节
        issues.append({
            "level": "Critical",
            "rule": "missing_step_section",
            "msg": f"{case['tc_id']} 缺少 **测试步骤**: 章节",
        })
        return issues
    base_line = case["start_line"] + body.count("\n", 0, offset)
    for ln_offset, line in enumerate(step_block.splitlines()):
        m = STEP_ROW_PATTERN.match(line)
        if not m:
            continue
        step_no, action, obj, data, expect = m.groups()
        # 表头/分隔行
        if action.strip().startswith(":") or action.strip() in {"操作动作", "---"}:
            continue
        line_no = base_line + ln_offset
        # 动作合法性
        action_clean = action.strip()
        if action_clean and action_clean not in ALLOWED_ACTIONS:
            # 允许"输入并提交"这类合并动词
            if not any(verb in action_clean for verb in ALLOWED_ACTIONS):
                issues.append({
                    "level": "Important",
                    "rule": "invalid_action_verb",
                    "msg": f"{case['tc_id']} 步骤 {step_no}(行 {line_no}):动作 \"{action_clean}\" 不在允许动词清单中",
                })
        # 四要素不为空(操作数据允许为 — / -)
        if not obj.strip() or obj.strip() in {"—", "-"}:
            issues.append({
                "level": "Critical",
                "rule": "missing_object",
                "msg": f"{case['tc_id']} 步骤 {step_no}(行 {line_no}):缺少操作对象",
            })
        if not expect.strip() or expect.strip() in {"—", "-"}:
            issues.append({
                "level": "Critical",
                "rule": "missing_expectation",
                "msg": f"{case['tc_id']} 步骤 {step_no}(行 {line_no}):缺少预期现象",
            })
    return issues


def check_forbidden_keywords(case: dict):
    """检查禁用关键词(仅扫描测试步骤区域;[双源对账] 专段窄口径豁免)

    - 步骤表操作列(**测试步骤** 区域)内的 SQL/接口/数据库动作一律拦截(Critical)。
    - 窄口径豁免:仅标 [双源对账] 的统计/金额对账用例,其「双源对账」专段内允许等价 SQL
      作断言依据(该段已从 step_block 剥离,不被下方扫描);但 SQL 须含软删除/状态过滤条件。
    - 未标 [双源对账] 的用例若用「双源对账」段夹带 SQL 规避禁令,判 Critical。
    """
    issues = []
    step_block, offset = extract_step_table(case["content"])
    if step_block:
        base_line = case["start_line"] + case["content"].count("\n", 0, offset)
        for idx, line in enumerate(step_block.splitlines()):
            line_no = base_line + idx
            for pattern, hint in FORBIDDEN_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    issues.append({
                        "level": "Critical",
                        "rule": "forbidden_code_level_action",
                        "msg": f"{case['tc_id']} 行 {line_no}:{hint};原文:`{line.strip()[:80]}`",
                    })
    # ── 双源对账窄口径豁免边界核验 ──
    dual_section = extract_dual_source_section(case["content"])
    if dual_section and _SQL_IN_TEXT_RE.search(dual_section):
        is_dual = DUAL_SOURCE_TAG in case["title"] or DUAL_SOURCE_TAG in case["content"]
        if not is_dual:
            issues.append({
                "level": "Critical",
                "rule": "dual_source_tag_missing",
                "msg": f"{case['tc_id']} 出现「双源对账」段含 SQL,但用例未标 {DUAL_SOURCE_TAG} 类型;"
                       f"SQL 豁免仅限标 {DUAL_SOURCE_TAG} 的统计/金额对账用例,不得借此段规避 SQL 禁令",
            })
        elif not _SOFTDELETE_STATUS_RE.search(dual_section):
            issues.append({
                "level": "Important",
                "rule": "dual_source_sql_missing_filter",
                "msg": f"{case['tc_id']} {DUAL_SOURCE_TAG} 专段 SQL 缺软删除/状态过滤条件"
                       f"(应含 del_flag/is_deleted/status/状态 等),易漏「软删除/状态未过滤」缺陷",
            })
    return issues


def check_dom_selectors(case: dict):
    """检查 DOM 选择器(仅扫描测试步骤区域)"""
    issues = []
    step_block, offset = extract_step_table(case["content"])
    if not step_block:
        return issues
    base_line = case["start_line"] + case["content"].count("\n", 0, offset)
    for idx, line in enumerate(step_block.splitlines()):
        if not line.strip().startswith("|"):
            continue
        line_no = base_line + idx
        # 剥除链接目标 / 内联代码后再扫描:markdown 链接锚点与代码引用是合法溯源,非 UI 选择器
        scan_line = strip_links_and_code(line)
        for pattern, hint in DOM_SELECTOR_PATTERNS:
            for m in re.finditer(pattern, scan_line):
                token = m.group(0)
                if token.startswith("#") and re.search(r"^\s*#\s", token):
                    continue
                if token.startswith(".") and re.search(r"\d+\.\d+", token):
                    continue
                if re.match(r"^\.(xlsx|md|json|png|jpg|jpeg|gif|html|css|js|ts|vue|txt|csv|pdf|svg|yml|yaml)$", token, re.IGNORECASE):
                    continue
                issues.append({
                    "level": "Important",
                    "rule": "dom_selector",
                    "msg": f"{case['tc_id']} 行 {line_no}:{hint} `{token}`;应改用页面可见文案",
                })
    return issues


def check_file(file_path: Path):
    """检查单个用例文档"""
    if not file_path.exists():
        return {"file": str(file_path), "error": "文件不存在", "issues": []}
    content = file_path.read_text(encoding="utf-8")
    cases = split_testcases(content)
    suite_organized = bool(SUITE_HEADER.search(content))
    file_result = {
        "file": str(file_path),
        "testcase_count": len(cases),
        "suite_organized": suite_organized,
        "issues": [],
    }
    if not cases:
        file_result["issues"].append({
            "level": "Info",
            "rule": "no_testcase_found",
            "msg": "文档中未识别到 TC-XXX 格式的用例标题(可能是总览/索引文档,跳过用例级检查)",
        })
        return file_result
    # 套件组织文档:入口由 Suite Setup 承担,跳过用例级入口检查(交由 check_testcase_suite.py)
    checkers = (check_steps_four_elements, check_forbidden_keywords, check_dom_selectors,
                check_case_type_tag)
    if not suite_organized:
        checkers = (check_entry,) + checkers
    for case in cases:
        for checker in checkers:
            file_result["issues"].extend(checker(case))
    return file_result


def check_multi_file_split(target: Path):
    """检查多文件拆分一致性

    单文件模式(默认): 00_索引.md + 01_研发自测方案.md + 02_全量自测用例.md / 02_增量自测用例.md,无需拆分检查。
    多文件模式: 出现模块拆分用例文件(03_+ 且非全量/增量整套)或 02_*总览* 主文档时触发,必须有 02_*总览* 主文档。
    通用规则(单/多文件均适用): 同目录所有用例文件必须带两位数字前缀,有序自增、序号唯一。
    """
    issues = []
    if not target.is_dir():
        return issues
    files = sorted(target.glob("*.md"))
    # 用例文件 = 排除专职索引(00_索引.md)、研发自测方案(01_研发自测方案.md)、
    #   保留序号(98_跨系统/99_待澄清)与非用例分册的配置文件
    # (测试环境与账号.md 是 aiauto-test 端的环境/账号配置,非用例分册,
    #  不参与序号重号扫描/多文件模块拆分判定,口径对齐 AIDP version.md 的 dedup_prefix 排除)
    def _is_case_file(name):
        if re.match(r"^00_", name):            # 00_索引.md(专职索引,AIDP 范式)
            return False
        if re.match(r"^9[89]_", name):         # 98_跨系统验证清单 / 99_待澄清问题清单
            return False
        if "研发自测方案" in name:              # 01_研发自测方案.md(方案,非用例分册)
            return False
        if "测试环境与账号" in name:            # aiauto-test 环境/账号配置
            return False
        return True

    case_files = [f for f in files if _is_case_file(f.name)]

    # ── AIDP 范式: 专职索引 00_索引.md 必须存在(与 ux/architect/planner 统一) ──
    has_index = any(f.name == "00_索引.md" for f in files)
    has_legacy_anchor = any(f.name == "00_研发自测方案.md" for f in files)  # 旧锚(历史存量)
    if not has_index and files:
        issues.append({
            "level": "Important",
            "rule": "missing_index",
            "msg": (f"目录 {target} 缺少专职索引 `00_索引.md`(AIDP 范式:00_索引 / 01_研发自测方案 / 02_用例总览)"
                    + ("；检测到旧锚 00_研发自测方案.md,历史目录可保留,新生成请迁移:方案改名 01_、用例顺延 02_、新增 00_索引.md"
                       if has_legacy_anchor else "")),
        })

    # ── 通用命名规则(单 / 多文件均适用): 同目录所有用例文件必须带两位数字前缀,有序自增、序号唯一 ──
    seen_prefixes = {}
    for f in case_files:
        m = re.match(r"^(\d{2})_", f.name)
        if not m:
            issues.append({
                "level": "Important",
                "rule": "invalid_filename_prefix",
                "msg": f"文件 {f.name} 未以两位数字前缀命名;同目录所有文件必须带 NN_ 序号前缀(单文件用例也应为 02_全量自测用例.md / 02_增量自测用例.md)",
            })
            continue
        prefix = m.group(1)
        if prefix in seen_prefixes:
            issues.append({
                "level": "Important",
                "rule": "duplicate_filename_prefix",
                "msg": f"序号 {prefix} 重复出现(文件 {f.name} 与 {seen_prefixes[prefix]});同目录序号必须唯一且自增",
            })
        else:
            seen_prefixes[prefix] = f.name
    # 文件名严禁"补充/追加"语义前缀
    for f in case_files:
        if re.search(r"补充|追加", f.name):
            issues.append({
                "level": "Important",
                "rule": "forbidden_filename_semantic_prefix",
                "msg": f"文件 {f.name} 使用了'补充/追加'语义前缀,应改为序号+模块名(如 03_订单管理用例.md)",
            })

    # ── 多文件模式判定: 有用例总览主文档,或存在"模块拆分"用例文件(带序号且非全量/增量整套单文件) ──
    def _is_overview(name):
        return bool(re.match(r"^02_", name)) and "总览" in name

    def _is_full_or_incr(name):
        # 单文件整套用例(全量/增量),允许 NN_ 前缀与 -后缀;非模块拆分
        return bool(re.match(r"^(?:\d{2}_)?(?:全量|增量)自测用例(?:[-_].+)?\.md$", name))

    overview_files = [f for f in case_files if _is_overview(f.name)]
    module_files = [
        f for f in case_files
        if re.match(r"^\d{2}_", f.name) and not _is_overview(f.name) and not _is_full_or_incr(f.name)
    ]
    multi_mode = bool(overview_files) or len(module_files) >= 1
    if multi_mode:
        # 用例总览主文档必须存在(00_ 索引 / 01_ 方案 / 02_ 用例总览)
        if not overview_files:
            issues.append({
                "level": "Critical",
                "rule": "missing_overview",
                "msg": f"目录 {target} 下检测到多文件用例(模块拆分),但缺少 `02_自测用例-总览.md` 主文档",
            })
        # 自测方案必须存在(维度 16 由 check_test_plan_alignment.py 主检,此处仅提示)
        has_test_plan = any(f.name == "01_研发自测方案.md" for f in files) \
            or any(f.name == "00_研发自测方案.md" for f in files)  # 兼容历史旧锚
        if not has_test_plan:
            issues.append({
                "level": "Important",
                "rule": "missing_test_plan",
                "msg": f"目录 {target} 下缺少 `01_研发自测方案.md`(详细核验见 check_test_plan_alignment.py)",
            })
    # TC-ID 全局唯一(只要有 ≥ 2 个用例文件就检查)
    if len(case_files) < 2:
        return issues
    tc_owner = {}
    for f in case_files:
        try:
            content = f.read_text(encoding="utf-8")
        except Exception:
            continue
        for m in TESTCASE_HEADER.finditer(content):
            tc_id = m.group(1)
            if tc_id in tc_owner:
                issues.append({
                    "level": "Critical",
                    "rule": "duplicate_tc_id",
                    "msg": f"用例编号 {tc_id} 在 {tc_owner[tc_id]} 和 {f.name} 中均出现",
                })
            else:
                tc_owner[tc_id] = f.name
    return issues


def aggregate(results, multi_issues):
    """汇总统计"""
    total = sum(len(r["issues"]) for r in results) + len(multi_issues)
    by_level = {"Critical": 0, "Important": 0, "Info": 0}
    for r in results:
        for i in r["issues"]:
            by_level[i["level"]] = by_level.get(i["level"], 0) + 1
    for i in multi_issues:
        by_level[i["level"]] = by_level.get(i["level"], 0) + 1
    return {"total_issues": total, "by_level": by_level}


def main():
    parser = argparse.ArgumentParser(description="自测用例格式校验")
    parser.add_argument("path", help="用例文档路径或目录")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    target = Path(args.path)
    if not target.exists():
        print(f"错误: 路径不存在 - {target}", file=sys.stderr)
        sys.exit(2)

    results = []
    if target.is_file():
        results.append(check_file(target))
        multi_issues = []
    else:
        for md in sorted(target.glob("*.md")):
            results.append(check_file(md))
        multi_issues = check_multi_file_split(target)

    summary = aggregate(results, multi_issues)

    if args.json:
        print(json.dumps({
            "summary": summary,
            "files": results,
            "multi_file_issues": multi_issues,
        }, ensure_ascii=False, indent=2))
    else:
        print(f"\n=== 自测用例格式校验报告 ===")
        print(f"扫描路径: {target}")
        print(f"问题汇总: 共 {summary['total_issues']} 项 "
              f"(Critical {summary['by_level'].get('Critical', 0)} / "
              f"Important {summary['by_level'].get('Important', 0)} / "
              f"Info {summary['by_level'].get('Info', 0)})")
        for r in results:
            if r["issues"]:
                print(f"\n📄 {r['file']}  (用例数 {r.get('testcase_count', 0)})")
                for i in r["issues"]:
                    icon = "🔴" if i["level"] == "Critical" else "🟡" if i["level"] == "Important" else "🔵"
                    print(f"  {icon} [{i['level']}] {i['msg']}")
        if multi_issues:
            print(f"\n📂 多文件拆分一致性问题:")
            for i in multi_issues:
                icon = "🔴" if i["level"] == "Critical" else "🟡"
                print(f"  {icon} [{i['level']}] {i['msg']}")
        print()

    sys.exit(1 if summary["by_level"].get("Critical", 0) > 0 else 0)


if __name__ == "__main__":
    main()
