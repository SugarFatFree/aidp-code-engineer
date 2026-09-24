#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用例统计与完备性度量检查(对应质量检查维度 19)。

从自测用例 Markdown 中统计:套件数、用例数、优先级分布(P0/P1/P2)、
正/反向分布、特殊场景条数,并校验:
  1. 文档末尾是否附「用例统计摘要」章节;
  2. 反向用例占比是否 ≥ 40%(happy path 过度堆积检测);
  3. 若摘要含「合计」行,声明的 P0+P1+P2 之和是否与实际用例数一致;
  4. 全量集合用例数是否 < 20(疑似覆盖遗漏)。

优先级分布偏离目标区间(P0 15-25% / P1 45-55% / P2 25-35%)为 warning-only,
不触发退出码 1,仅在 --json 的 priority_distribution 中给出提示。

可选:给了 --issue-record <《需求问题记录》/《待澄清问题清单》路径> 时,追加统计「需求问题覆盖 M/N」——
澄清点编号支持 **Q-(需求期) / D-(设计期) / P-(计划期) / T-(用例新增)** 四阶段体系
(含 Q-FIELD-001 等子前缀)与旧的「问题 #N」两套形态;来源可以是**表格首列**
(ux「十、待澄清问题清单」/ Module E 的实际形态)、段头或行内。

解析记录里的条目数为 N、用例名里 distinct `(需求问题#N)`/`(澄清#N)`/`(Q-001)` 标记数为 M,
输出 M/N + 未覆盖澄清点清单(对应第五步之五 / 方法论八之四)。不给该参数则输出与现状完全一致
(向后兼容)。

⚠️ **调用方契约:`issue_coverage` 是三态,禁止只读 `uncovered_nums` 判绿**。三态如下,`--json` 与人读输出**都会**给出:

  · 正常  {'covered':M, 'total':N, 'uncovered_nums':[...], 'tagged_extra_nums':[...]}
  · 跳过  {'skipped': True, 'reason': '...'}         ← 清单显式标注「无待澄清项」,合法形态
  · 错误  {'error': '...'}                            ← 解析出 0 条且无「无待澄清项」标注

  `skipped`/`error` 两态下**没有** covered/total/uncovered_nums 三个键。
  常见误判:`len(issue_coverage.get('uncovered_nums', []))==0` 在这两态下恒真 → 假绿灯。
  正确写法:先判 `error`(视为失败)、再判 `skipped`(视为 N/A),最后才读计数。

退出码:0 = 通过, 1 = 不通过(含 --issue-record 解析失败), 2 = 输入路径错误。
⚠️ 解析失败判 **1 而不是 2**,两条理由缺一不可:
  ① 2 是**整脚本 return**,维度 19 的核心判据(统计摘要 / 反向占比 / 优先级分布)一条都跑不到,
     而 QR 按「exit 2 = 入参错、不计维度失败」略过 —— 传一份解析不了的清单
     就能让 Critical 维度 19 整档静默跳过。**附加统计绝不该顶掉主体判据。**
  ② 只读退出码的接入方必须也能看见它。落在 1 上,主体判据照跑完、结果照打印,
     退出码仍然是红的。JSON 里 `passed` 字段**只反映用例文档本身**、不受此影响,
     两者刻意分开,避免把「清单解析不了」和「用例文档不合格」混成一个信号。
仅使用标准库,支持 Linux/macOS/Windows。
"""
import argparse
import json
import re
import sys
from pathlib import Path

# 套件 / 用例识别口径与 check_suite_upstream.py / check_testcase_suite.py /
# check_testcase_format.py 保持一致:兼容「测试套件」前缀 + SUITE-/TS- 双前缀,
# 用例标题「用例」二字可省(#### TC-XXX: 与 #### 用例 TC-XXX: 均识别)。
# 否则「测试套件 TS-NNN」组织的文档会被漏计套件数(仅影响统计展示,不影响判定)。
SUITE_RE = re.compile(r'^#{2,4}\s*(?:测试)?套件\s+((?:SUITE|TS)-[\w\-]+)', re.MULTILINE)
CASE_RE = re.compile(r'^#{3,6}\s*(?:用例\s+)?(TC-[\w\-]+)', re.MULTILINE)
# 优先级/类型字段行:> **优先级**: P0 | **类型**: 正向
PRIO_RE = re.compile(r'优先级\**\s*[:：]\s*\**\s*(P[012])')
TYPE_RE = re.compile(r'类型\**\s*[:：]\s*\**\s*([^\n|]+)')
# 显式「反向」字段(是/否),优先于类型推断
REVERSE_RE = re.compile(r'反向\**\s*[:：]\s*\**\s*(是|否)')
# 「覆盖」字段:覆盖矩阵维度标签,如 F4,R1(支持中英文逗号/顿号/空格分隔)
COVERAGE_RE = re.compile(r'覆盖\**\s*[:：]\s*\**\s*([FR][\w,，、\s]*)')
DIM_TOKEN_RE = re.compile(r'[FR]\d{1,2}')
SUMMARY_RE = re.compile(r'#{1,4}[^\n]*(?:用例统计摘要|统计汇总表|用例统计汇总)')
# 「用例统计摘要」表的合计/总计行:| **合计** | M | a(P0) | b(P1) | c(P2) | p(正向) | q(反向) |
SUMMARY_TOTAL_ROW_RE = re.compile(
    r'^\s*\|\s*\**\s*(?:合计|总计)\s*\**\s*\|(.+)\|\s*$', re.MULTILINE)
INT_RE = re.compile(r'-?\d+')
# 《需求问题记录》条目锚点。**澄清点 ID 一律规范化为字符串**,不能用 int ——
# 上游是 Q/D/P 三阶段编号体系(Q=需求期 ux / D=设计期 architect / P=计划期 planner,
# 见 dev-execution-planner「沿用上游 PRD 的 Q-NNN 和详细设计的 D-NNN」),
# 纯数字会让 Q-001 与 D-001 撞成同一条。
#
# ⚠️ 三种形态都要认:
#   ① **表格首列**——ux 的「十、待澄清问题清单」/ Module E 就是表格,`| Q-001 | 主题 | …`,
#      这是**实际最主要的形态**;漏认会解析 0 条 → issue_coverage 0/0
#      → 报告呈现为「看起来全覆盖」的绿灯,一条澄清点都没对账。**比不接更危险**。
#   ② 段头 `### Q-001 …` / `### 问题 #N`
#   ③ 行内 `问题#N`
# 子前缀变体(Q-FIELD-001 / Q-REUSE-002 / Q-PROTO-003 / Q-FLOW-004 / Q-ITEM-005)一并认。
# ⚠️ **T 必须在内**：`T-NNN` 是本 SKILL 自己规定的「用例新增项」澄清点前缀
#    （见 assets/full-testcase-template.md「编号沿用上游 Q-NNN/D-NNN/P-NNN，用例新增项用 T-NNN」），
#    而 checklist 13.8 明说可以传《待澄清问题清单》——漏掉 T 时纯 T- 清单解析 0 条，
#    混合清单更糟：T- 条目被静默丢弃、total 偏小，又是一个「看起来全覆盖」的假绿灯。
ISSUE_ID_CORE = r'(?:[QDPT]-(?:[A-Z]+-)?\d+)'
# ① 表格行首列(容忍加粗与前后空格)
ISSUE_TABLE_RE = re.compile(r'^\s*\|\s*\**\s*(' + ISSUE_ID_CORE + r')\s*\**\s*\|', re.MULTILINE)
# ② 段头:Q-NNN 形态 或 旧的「问题 #N」形态
ISSUE_ENTRY_ID_RE = re.compile(r'^#{2,4}\s*(' + ISSUE_ID_CORE + r')\b', re.MULTILINE)
ISSUE_ENTRY_RE = re.compile(r'^#{2,4}\s*问题\s*#\s*(\d+)', re.MULTILINE)
# ③ 行内回退
ISSUE_INLINE_ID_RE = re.compile(r'\b(' + ISSUE_ID_CORE + r')\b')
ISSUE_INLINE_RE = re.compile(r'问题\s*#\s*(\d+)')
# 用例名/正文里的澄清点覆盖标记:(需求问题#N)/(澄清#N)/(Q-001)/(澄清 Q-001)(全半角括号)
ISSUE_TAG_RE = re.compile(r'[（(]\s*(?:需求问题|澄清)\s*#\s*(\d+)\s*[）)]')
ISSUE_TAG_ID_RE = re.compile(r'[（(]\s*(?:需求问题|澄清)?\s*(' + ISSUE_ID_CORE + r')\s*[）)]')


# 「无待澄清项」是本 SKILL 规定的合法形态（模板明写"即使无项也保留标题并标注"），
# 不是入参错——识别到它就走 skipped，别报错。
EMPTY_ISSUE_RECORD_RE = re.compile(r'无待澄清项|无待澄清问题|暂无待澄清|待澄清项[:：]?\s*无')


def _norm_num_id(n):
    """旧的纯数字澄清点统一成 `#N`,与 Q-/D-/P- 形态共存不冲突。"""
    return '#%d' % int(n)

# 覆盖矩阵全维(正向 F1-F9 + 反向 R1-R12;R12=依赖/数据源故障注入与降级提示)
FORWARD_DIMS = [f'F{i}' for i in range(1, 10)]
REVERSE_DIMS = [f'R{i}' for i in range(1, 13)]
ALL_DIMS = FORWARD_DIMS + REVERSE_DIMS

# 反向类型关键词(命中即判反向)
# ⚠️ 「反向」必须在表内：本表只是**缺显式「反向: 是/否」字段时的类型推断兜底**
# (模板规范形态是显式字段，见 references/flow-steps.md「不再靠类型推断」)。但 FORWARD_KW
# 收了「正向」、这里却漏了对仗的「反向」——省略显式字段、照模板的「类型: 正向」对仗写
# 「类型: 反向」的文档会被算进 other，压低反向占比，在「反向占比 ≥40%」这条 Critical 判据上
# 产生**假红**。补它零误报风险：类型字面写着「反向」的用例，按任何读法都是反向。
REVERSE_KW = ['反向', '异常', '边界', '校验', '权限', '并发', '约束', '安全',
              '无效', '非法', '竞态', '超时', '失败', '错误', '降级',
              '故障', '注入']
# 正向类型关键词
FORWARD_KW = ['正向', '回归', '冒烟', '主流程']
# 特殊场景标记
SPECIAL_KW = {
    '缓存': ['缓存', '[缓存场景]'],
    'Mock': ['Mock', 'mock'],
    '第三方对接': ['第三方', '对接', '降级', '回调'],
    '并发': ['并发', '竞态', '乐观锁', '重复提交'],
    '字段逐列核对': ['列集合', '逐列核对', '字段核对', '列表列完整性', '列完整性'],
    '集成': ['集成'],
    # 语义/口径变更类文案一致性用例族(SKILL 第五步之八 / 方法论八之五);
    # 反向用例复用 `断言(反向):不存在文本"旧口径字样"` DSL,与 [反向-残留] 同判失败语义。
    '文案一致性': ['文案一致性', '[文案一致性]'],
    # 通用还原度套件(SKILL 第五步之九 / 维度 21,判据见 references/flow-fidelity-suite.md)。
    # ⚠️ 只作**统计口径**登记,不改变正向/反向分类:本族十条以守恒/存在性正向断言为主,
    #    其中「空态」「加载态无跳变」等条目本身带反向语义,由各用例自己的「类型」字段决定归属。
    '还原度': ['还原度', '[还原度]'],
    # 客户端应用 MCP 业务工具用例族(条件启用,判据见 references/flow-client-mcp.md)。
    # ⚠️ 只作**统计口径**登记,⛔ 不进 RATIO_EXCLUDED_TAGS:本族正反向混合
    #    (越权 / 取消 / 超时 / 并发 / 不扩权都是反向用例),不像 [还原度] 那样以正向为主,
    #    把它排除出反向占比分母会凭空抬高比值。
    # ⚠️ **条件触发**:未启用时计数为 0 是正常的,⛔ 不得据此判缺口。
    '应用MCP': ['应用MCP', '[应用MCP]'],
    # 上游调用日志断言族(SKILL 第五步之十 / 方法论八之六 · 通用规则 约定40)。
    # ⚠️ **条件触发**:仅本次迭代新增或改动了出站调用时才有,**计数为 0 是正常的**,
    #    不要据此判缺口(判缺口的条件是「本轮动了出站调用却一条都没有」,那属维度 18 的语义判断)。
    # ⚠️ 本族与 [还原度] 一样**整族排除在反向占比分子分母之外**(见 RATIO_EXCLUDED_TAGS):
    #    第③条「日志中不存在明文凭据」是**用例内的一条反向断言**、不代表整条用例是反向用例,
    #    而本族按定义主体是成功路径正向断言,计入分母必然稀释占比。
    '日志可追溯': ['日志可追溯', '[日志可追溯]'],
}

# 排除在反向占比分子分母之外的用例族标记,见下方 dir_count 计数处注释。
# ⚠️ **两族同因排除,别只加一个**:它们都是「按规则固定生成、绝大多数是正向断言」的族,
#    计入分母只会稀释反向占比、把业务用例本身已达标的文档判死(两族都实测复现过)。
FIDELITY_TAG = '[还原度]'                       # 维度 21 通用还原度套件
LOG_TRACE_TAG = '[日志可追溯]'                  # 第五步之十 上游调用日志断言族(约定40)
RATIO_EXCLUDED_TAGS = (FIDELITY_TAG, LOG_TRACE_TAG)

REVERSE_RATIO_FLOOR = 0.40
MIN_TOTAL_FULL = 20

# ★规模档位基线(对应 SKILL.md「需求规模档位」;单位 = **整轮全部模块合计**)。
# 缺省不传 --scale 时按 L 档,行为与旧版本逐字一致(只用 MIN_TOTAL_FULL=20 作硬下限告警)。
# ⚠️ 档位只伸缩**数量基线**:反向占比 ≥40%、统计摘要必附、合计行一致性三项在任何档位都不放松。
# ⚠️ L 档刻意为 None——它按**每模块**基线(简单 30-60 / 中等 80-150,见维度 19),
#    与 S/M 的整轮合计口径不是一回事,无法用单一区间机检,故仍只跑 MIN_TOTAL_FULL 硬下限。
SCALE_BASELINE = {'S': (25, 40), 'M': (60, 100), 'L': None}


def classify_type(type_str):
    """返回 'forward' / 'reverse' / 'other'。反向关键词优先。"""
    s = type_str or ''
    for kw in REVERSE_KW:
        if kw in s:
            return 'reverse'
    for kw in FORWARD_KW:
        if kw in s:
            return 'forward'
    return 'other'


def classify_direction(case):
    """方向判定:优先用显式「反向」字段(是=reverse/否=forward),缺失则回退类型推断。"""
    rf = case.get('reverse_field')
    if rf == '是':
        return 'reverse'
    if rf == '否':
        return 'forward'
    return classify_type(case.get('type'))


def analyze_text(text):
    suites = SUITE_RE.findall(text)
    # 逐个用例块:用用例标题切分,取标题后到下一个用例标题前的片段找优先级/类型
    case_iters = list(CASE_RE.finditer(text))
    cases = []
    for i, m in enumerate(case_iters):
        start = m.end()
        end = case_iters[i + 1].start() if i + 1 < len(case_iters) else len(text)
        block = text[start:end]
        prio_m = PRIO_RE.search(block)
        type_m = TYPE_RE.search(block)
        rev_m = REVERSE_RE.search(block)
        cov_m = COVERAGE_RE.search(block)
        # 用例标题(块首行,含 TC-id 后的标题文本)——特殊场景标记(如 [缓存场景]、
        # [待第三方交付-开发期Mock])写在标题里而非「类型」字段,故特殊场景统计须看标题。
        title = block.split('\n', 1)[0]
        cases.append({
            'id': m.group(1),
            'title': title,
            'priority': prio_m.group(1) if prio_m else None,
            'type': (type_m.group(1).strip() if type_m else ''),
            'reverse_field': rev_m.group(1) if rev_m else None,
            'coverage': DIM_TOKEN_RE.findall(cov_m.group(1)) if cov_m else [],
        })

    prio_count = {'P0': 0, 'P1': 0, 'P2': 0, 'unknown': 0}
    dir_count = {'forward': 0, 'reverse': 0, 'other': 0}
    # ★「反向占比 ≥40%」按**排除 [还原度] 后的业务用例集**计算(勿改回把它算进来)。
    #   Why:维度 21 要求**每个列表页 ≥10 条**通用还原度用例,而这批固定模板项(字段守恒 / 按钮守恒 /
    #   筛选排序守恒 / 导出 / 编辑后刷新 / 大数据量…)绝大多数是正向断言。它与维度 19 的
    #   「反向占比 ≥40%」都是 exit 1 的硬 Critical,叠加后**业务用例本身已达标的文档照样被判死**
    #   (实测:20 条业务用例中 8 条反向 = 恰好 40%,再加 3 个列表页 × 10 条还原度 → 掉到 16%)。
    #   还原度用例数单列一档统计(下方 special['还原度']),不进分子也不进分母。
    #   ★ `[日志可追溯]`(第五步之十 / 约定40)**同因同办**:本族按定义「正向断言必须落在成功场景」,
    #     几乎全是 `反向: 否`,计入分母只加分母不加分子。实测:20 条业务用例 12 正 / 8 反 = 恰好 40%,
    #     照章追加 6 条本族用例后掉到 31%、exit 1 —— 同样 6 条打 `[还原度]` 放行、打本标记判死。
    fidelity_count = 0
    for c in cases:
        prio_count[c['priority'] if c['priority'] in prio_count else 'unknown'] += 1
        hay = (c['type'] or '') + ' ' + (c.get('title') or '')
        if any(tag in hay for tag in RATIO_EXCLUDED_TAGS):
            fidelity_count += 1
            continue
        dir_count[classify_direction(c)] += 1

    special = {}
    for name, kws in SPECIAL_KW.items():
        special[name] = sum(
            1 for c in cases
            if any(kw in ((c['type'] or '') + ' ' + (c.get('title') or '')) for kw in kws))

    # 维度→用例覆盖映射(F1-F9 / R1-R12 → 命中的用例 ID 列表)
    coverage_matrix = {d: [] for d in ALL_DIMS}
    for c in cases:
        for dim in c['coverage']:
            if dim in coverage_matrix:
                coverage_matrix[dim].append(c['id'])
    uncovered = [d for d in ALL_DIMS if not coverage_matrix[d]]
    tagged = sum(1 for c in cases if c['coverage'])

    has_summary = bool(SUMMARY_RE.search(text))

    # 合计/总计行:声明的 P0+P1+P2 之和 / 用例数,供维度 19「与实际用例数一致」核验
    total_row_nums = None
    trm = SUMMARY_TOTAL_ROW_RE.search(text)
    if trm:
        nums = [int(x) for x in INT_RE.findall(trm.group(1))]
        if len(nums) >= 4:
            total_row_nums = nums

    return {
        'suites': len(set(suites)),
        'cases': len(cases),
        'priority': prio_count,
        'direction': dir_count,
        # 通用还原度族条数(维度 21):**已从 direction 三档中剔除**,反向占比不含它
        'fidelity': fidelity_count,
        'special': special,
        'has_summary': has_summary,
        'total_row_nums': total_row_nums,
        'coverage_matrix': coverage_matrix,
        'uncovered_dims': uncovered,
        'coverage_tagged_cases': tagged,
    }


def target_hint(prio_count, total):
    """优先级分布目标区间提示(warning-only)。"""
    if total == 0:
        return []
    hints = []
    ranges = {'P0': (0.15, 0.25), 'P1': (0.45, 0.55), 'P2': (0.25, 0.35)}
    for p, (lo, hi) in ranges.items():
        ratio = prio_count.get(p, 0) / total
        if ratio < lo or ratio > hi:
            hints.append(f'{p} 占比 {ratio:.0%} 偏离目标区间 {lo:.0%}-{hi:.0%}')
    return hints


def check_file(path, is_full=None, scale=None):
    text = path.read_text(encoding='utf-8', errors='replace')
    stat = analyze_text(text)
    total = stat['cases']
    problems = []  # Critical(触发退出码 1)
    warnings = []

    if total == 0:
        # 非用例文档(如纯方案),跳过
        return None

    # 1. 统计摘要存在性
    if not stat['has_summary']:
        problems.append('文档末尾缺「用例统计摘要」章节(维度 19 必附)')

    # 1b. 若摘要含「合计」行:声明的 P0+P1+P2 之和须与实际用例数一致(维度 19)
    #     列序按模板 | 合计 | 用例数 | P0 | P1 | P2 | 正向 | 反向 |,取前 4 个整数。
    tr = stat['total_row_nums']
    if tr is not None:
        declared_total = tr[0]
        declared_prio_sum = sum(tr[1:4])
        if declared_prio_sum != total:
            problems.append(
                f'「用例统计摘要」合计行 P0+P1+P2={declared_prio_sum} 与实际用例数 {total} 不符')
        elif declared_total != total:
            problems.append(
                f'「用例统计摘要」合计行用例数 {declared_total} 与实际统计用例数 {total} 不符')

    # 2. 反向占比(用例数 ≥ 10 才判定,避免小样本噪声)
    # ⚠️ 分母是**业务用例集**(总数减去 [还原度] 族),不是全部用例——两条 Critical 会互撞,见上方注释
    rev = stat['direction']['reverse']
    biz_total = stat['direction']['forward'] + rev + stat['direction']['other']
    rev_ratio = rev / biz_total if biz_total else 0
    total_for_ratio = biz_total
    if total_for_ratio >= 10 and rev_ratio < REVERSE_RATIO_FLOOR:
        problems.append(
            f'反向用例占比 {rev_ratio:.0%} < 下限 40%(happy path 过度堆积,完备性不足)')
    elif total_for_ratio < 10 and rev_ratio < REVERSE_RATIO_FLOOR:
        warnings.append(f'反向用例占比 {rev_ratio:.0%} < 40%(业务用例样本 <10 条,仅告警)')

    # 3a. 规模档位基线(仅当显式传了 --scale S|M 才判;缺省或 L 档跳过,行为同旧版本)
    band = SCALE_BASELINE.get(str(scale or '').upper())
    if band:
        lo, hi = band
        sc = str(scale).upper()
        if total < lo:
            warnings.append(f'用例总数 {total} 低于 {sc} 档基线下限 {lo}(基线 {lo}~{hi},整轮合计口径);'
                            f'低于下限须在统计摘要说明原因')
        elif total > hi:
            warnings.append(f'用例总数 {total} 高于 {sc} 档基线上限 {hi}(基线 {lo}~{hi});'
                            f'档位可能判低了,或本轮产出未按档位收敛')

    # 3. 单文件用例数 < 20(warning-only):全量集合疑似覆盖遗漏;增量/模块拆分子文件本就偏少,仅提示不拦截
    if total < MIN_TOTAL_FULL:
        warnings.append(
            f'用例总数 {total} < {MIN_TOTAL_FULL}(全量集合疑似覆盖遗漏,须在统计摘要说明原因;'
            f'增量/模块拆分子文件量少属正常,可忽略)')

    # 4. 优先级分布(warning-only)
    warnings.extend(target_hint(stat['priority'], total))
    if stat['priority']['unknown']:
        warnings.append(f"{stat['priority']['unknown']} 条用例未解析到 P0/P1/P2 优先级")

    return {
        'file': str(path),
        'stat': stat,
        'reverse_ratio': round(rev_ratio, 4),
        'problems': problems,
        'warnings': warnings,
        'passed': not problems,
    }


def collect_files(root):
    p = Path(root)
    if p.is_file():
        return [p] if p.suffix == '.md' else []
    if p.is_dir():
        # 跳过非用例文档:00_索引 / 01_研发自测方案 / 98_跨系统验证清单 / 99_待澄清问题清单
        #   + aiauto-test 的 测试环境与账号 配置(均无 TC- 用例块)。
        # 口径与 check_suite_upstream.py / check_testcase_format.py 一致,避免统计口径漂移。
        def _non_case(name):
            return (re.match(r'^00_', name) or re.match(r'^9[89]_', name)
                    or '研发自测方案' in name or '测试环境与账号' in name)
        return sorted(f for f in p.rglob('*.md') if not _non_case(f.name))
    return []


DIM_NAMES = {
    'F1': '页面加载', 'F2': '列表展示', 'F3': '筛选搜索', 'F4': '创建', 'F5': '编辑',
    'F6': '删除', 'F7': '状态流转', 'F8': '导航路由', 'F9': '交互反馈',
    'R1': '必填校验', 'R2': '长度格式', 'R3': '全空白', 'R4': '网络失败', 'R5': '空数据',
    'R6': '权限不足', 'R7': '弹窗关闭', 'R8': '服务端错误', 'R9': '状态约束',
    'R10': '并发竞态', 'R11': '安全输入', 'R12': '数据源故障注入',
}


def aggregate_coverage(results):
    """跨文件汇总 维度→用例 覆盖映射。"""
    matrix = {d: [] for d in ALL_DIMS}
    for r in results:
        for d, ids in r['stat']['coverage_matrix'].items():
            matrix[d].extend(ids)
    uncovered = [d for d in ALL_DIMS if not matrix[d]]
    return matrix, uncovered


def aggregate_priority(results):
    """跨文件汇总优先级分布(供 QR 子 Agent 按 priority_distribution 字段判定维度 19)。

    偏离目标区间(P0 15-25% / P1 45-55% / P2 25-35%)为 warning-only,
    仅在 off_target_hints 给出提示,不影响 passed 判定。
    """
    counts = {'P0': 0, 'P1': 0, 'P2': 0, 'unknown': 0}
    for r in results:
        for k in counts:
            counts[k] += r['stat']['priority'].get(k, 0)
    total = sum(counts.values())
    ratios = {p: round(counts[p] / total, 4) if total else 0
              for p in ('P0', 'P1', 'P2', 'unknown')}
    return {
        'counts': counts,
        'total': total,
        'ratios': ratios,
        'target_ranges': {'P0': [0.15, 0.25], 'P1': [0.45, 0.55], 'P2': [0.25, 0.35]},
        'off_target_hints': target_hint(counts, total),
    }


def print_coverage_matrix(matrix, uncovered, as_json):
    if as_json:
        print(json.dumps({'coverage_matrix': matrix, 'uncovered_dims': uncovered},
                         ensure_ascii=False, indent=2))
        return
    print('\n=== 维度 × 用例覆盖映射表(F 正向9维 / R 反向12维)===')
    print('| 维度 | 名称 | 覆盖用例数 | 用例 |')
    print('| :-: | :- | :-: | :- |')
    for d in ALL_DIMS:
        ids = matrix[d]
        mark = '❌ 无用例覆盖' if not ids else ', '.join(ids[:6]) + ('…' if len(ids) > 6 else '')
        print(f"| {d} | {DIM_NAMES.get(d, '')} | {len(ids)} | {mark} |")
    if uncovered:
        print(f"\n⚠️ 未被任何用例覆盖的维度({len(uncovered)}):{', '.join(uncovered)}")
        print("   (若某维度对本项目不适用,须在用例文档就地标注 `维度 不适用 + 原因`)")
    else:
        print('\n✅ 覆盖矩阵全维均有用例覆盖')


def parse_issue_record(path):
    """解析《需求问题记录》,返回按出现顺序去重的澄清点编号列表(int)。

    识别锚点优先用 `### 问题 #N` 段头;若无段头命中,回退行内"问题#N"。
    """
    text = Path(path).read_text(encoding='utf-8', errors='replace')
    # 优先级:表格首列 > 段头(Q 形态) > 段头(问题#N) > 行内。前者命中就不再回退,
    # 避免同一条澄清点被行内提及重复计入。
    ids = ISSUE_TABLE_RE.findall(text)
    if not ids:
        ids = ISSUE_ENTRY_ID_RE.findall(text)
    if not ids:
        ids = [_norm_num_id(n) for n in ISSUE_ENTRY_RE.findall(text)]
    if not ids:
        ids = ISSUE_INLINE_ID_RE.findall(text)
    if not ids:
        ids = [_norm_num_id(n) for n in ISSUE_INLINE_RE.findall(text)]
    seen, ordered = set(), []
    for i in ids:
        if i not in seen:
            seen.add(i)
            ordered.append(i)
    return ordered


def compute_issue_coverage(case_files, issue_nums):
    """统计用例集合里出现的 distinct (需求问题#N)/(澄清#N) 标记,对账《需求问题记录》。

    返回 dict:total(N)/covered(M)/covered_nums/uncovered_nums/tagged_extra(记录外多标注)。
    """
    tagged = set()
    for f in case_files:
        text = f.read_text(encoding='utf-8', errors='replace')
        for n in ISSUE_TAG_RE.findall(text):
            tagged.add(_norm_num_id(n))
        for i in ISSUE_TAG_ID_RE.findall(text):
            tagged.add(i)
    issue_set = set(issue_nums)
    covered = sorted(tagged & issue_set)
    uncovered = [n for n in issue_nums if n not in tagged]   # 保持记录里的原始顺序
    extra = sorted(tagged - issue_set)  # 用例标注了、但记录里无此编号
    return {
        'total': len(issue_nums),
        'covered': len(covered),
        'covered_nums': covered,
        'uncovered_nums': uncovered,
        'tagged_extra_nums': extra,
    }


def main():
    ap = argparse.ArgumentParser(description='用例统计与完备性度量检查(维度 19)')
    ap.add_argument('path', help='用例文件或目录')
    ap.add_argument('--json', action='store_true', help='输出 JSON')
    ap.add_argument('--coverage-matrix', action='store_true',
                    help='额外输出 维度→用例 交叉表(读用例「覆盖」字段,标出无用例覆盖的维度)')
    ap.add_argument('--scale', choices=['S', 'M', 'L', 's', 'm', 'l'],
                    help='需求规模档位(见 SKILL.md「需求规模档位」):S=25~40 / M=60~100 条'
                         '(**整轮全部模块合计**口径);L 档按每模块基线、无法单区间机检故跳过。'
                         '不传 = 按 L 档,行为与旧版本一致')
    ap.add_argument('--issue-record', metavar='PATH',
                    help='可选:《需求问题记录》/《待澄清问题清单》路径(支持 ux Module E 的 Q-NNN 表格形态)。'
                         '给了则追加统计「需求问题覆盖 M/N」+ 未覆盖澄清点清单'
                         '(读用例名里的 (澄清 Q-001)/(需求问题#N)/(澄清#N) 标记);'
                         'issue_coverage 是三态:正常 / skipped(清单标「无待澄清项」) / '
                         'error(解析不出编号,exit 1 且走 stderr)——'
                         '禁止只读 uncovered_nums 判绿,后两态该键不存在;'
                         '不给则输出与现状完全一致(向后兼容)')
    args = ap.parse_args()

    files = collect_files(args.path)
    if not files:
        msg = f'输入路径错误或无 .md 用例文件:{args.path}'
        print(json.dumps({'error': msg}, ensure_ascii=False) if args.json else msg)
        return 2

    results = [r for r in (check_file(f, scale=args.scale) for f in files) if r is not None]
    if not results:
        msg = '未在输入中找到含用例(TC-)的文档'
        print(json.dumps({'error': msg}, ensure_ascii=False) if args.json else msg)
        return 2

    all_passed = all(r['passed'] for r in results)
    cov_matrix, cov_uncovered = aggregate_coverage(results)

    # 需求问题覆盖(仅当给了 --issue-record 才计算,不给则完全不影响输出)
    issue_cov = None
    # ⚠️ 必须在分支外初始化:函数末尾的退出码要读它,而它只在 --issue-record 分支里赋值,
    # 留在分支内则不带该参数跑一次就是 NameError。
    issue_parse_error = None
    if args.issue_record:
        rec_path = Path(args.issue_record)
        if not rec_path.is_file():
            msg = f'--issue-record 路径不存在或非文件:{args.issue_record}'
            print(json.dumps({'error': msg}, ensure_ascii=False) if args.json else msg)
            return 2
        rec_text = rec_path.read_text(encoding='utf-8', errors='replace')
        issue_nums = parse_issue_record(rec_path)
        # 三态。「解析 0 条」不整脚本 return 2：本 SKILL 规定的合法输入里有
        #   · 「无待澄清项」的空清单 —— 模板明写「即使无项也保留标题并标注」；
        #   · 纯 T-NNN 清单。
        # 整脚本 return 会让维度 19 的核心判据（统计摘要 / 反向占比 / 优先级分布）一条都不跑，
        # QR 又按「exit 2 = 入参错、不计维度失败」略过 —— 附加统计绝不该顶掉主体判据。
        #
        # ⚠️ 「不 return 2」不等于「不报错」：错误只塞进 issue_cov dict 时，只读退出码、或读
        # uncovered_nums 求长度的接入方（error/skipped 两态该键都不存在 → len([])==0）会得到
        # 「✅ 全覆盖」的假绿。口径：**主体判据照跑完，错误另走 stderr + 退出码 1**。
        if not issue_nums:
            if EMPTY_ISSUE_RECORD_RE.search(rec_text):
                issue_cov = {'skipped': True, 'reason': '清单显式标注「无待澄清项」，无需对账'}
            else:
                issue_parse_error = (
                    '--issue-record 解析出 0 条澄清点：%s\n'
                    '  该文件里没有可识别的澄清点编号，也没有「无待澄清项」标注。\n'
                    '  已支持的形态（任一即可）：\n'
                    '    · 表格首列  | Q-001 | 主题 | …      (ux「十、待澄清问题清单」/ Module E 就是这种)\n'
                    '    · 段头      ### Q-001 …  /  ### 问题 #1\n'
                    '    · 行内      Q-001 / 问题#1\n'
                    '  编号前缀 Q-(需求期) / D-(设计期) / P-(计划期) / T-(用例新增)，含子前缀如 Q-FIELD-001。\n'
                    '  确实没有待澄清项时，请在清单里保留标题并标注「无待澄清项」。'
                    % args.issue_record)
                issue_cov = {'error': issue_parse_error}
        else:
            issue_cov = compute_issue_coverage(files, issue_nums)

    if args.json:
        out = {
            'passed': all_passed,
            'priority_distribution': aggregate_priority(results),
            'files': results,
        }
        if args.coverage_matrix:
            out['coverage_matrix'] = cov_matrix
            out['uncovered_dims'] = cov_uncovered
        if issue_cov is not None:
            out['issue_coverage'] = issue_cov
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        for r in results:
            s = r['stat']
            flag = '✅' if r['passed'] else '❌'
            print(f"{flag} {r['file']}")
            print(f"   套件 {s['suites']} | 用例 {s['cases']} | "
                  f"P0 {s['priority']['P0']} / P1 {s['priority']['P1']} / "
                  f"P2 {s['priority']['P2']} | "
                  f"正向 {s['direction']['forward']} / 反向 {s['direction']['reverse']} "
                  f"/ 其他 {s['direction']['other']} / 还原度 {s.get('fidelity', 0)}(反向占比 "
                  f"{r['reverse_ratio']:.0%},分母 = 业务用例 {s['direction']['forward'] + s['direction']['reverse'] + s['direction']['other']} 条,"
                  f"不含 [还原度] 族)")
            print(f"   特殊场景:" + " / ".join(
                f"{k} {v}" for k, v in s['special'].items()))
            for p in r['problems']:
                print(f"   ❌ {p}")
            for w in r['warnings']:
                print(f"   ⚠️  {w}")
        if args.coverage_matrix:
            print_coverage_matrix(cov_matrix, cov_uncovered, False)
        if issue_cov is not None:
            print('\n=== 需求问题覆盖(消费《需求问题记录》,对应第五步之五 / 方法论八之四)===')
            # ⚠️ 必须先判三态再取键：skipped/error 两态的 dict 里没有 covered/total/uncovered_nums，
            # 无条件取键会在「无待澄清项」这一合法形态上 KeyError。
            if issue_cov.get('skipped'):
                print(f"   ⏭️  跳过对账:{issue_cov.get('reason', '')}")
            elif issue_cov.get('error'):
                print(f"   ❌ {issue_cov['error']}")
            else:
                print(f"   需求问题覆盖:{issue_cov['covered']}/{issue_cov['total']} 个澄清点已有专项用例"
                      " (用例名 (需求问题#N)/(澄清#N)/(Q-001) 标记)")
                # ⚠️ 这里**不能**再加 `#` 前缀：uncovered_nums 装的是已归一化的字符串 ID ——
                # `#N` 形态经 _norm_num_id() 已是 '#1'、编号形态本就是 'Q-001'。
                if issue_cov['uncovered_nums']:
                    print("   ⚠️ 未覆盖澄清点:" + ", ".join(issue_cov['uncovered_nums'])
                          + " —— 须补 (需求问题#N) 专项用例或就地标不适用")
                elif issue_cov['total']:
                    print("   ✅ 每个澄清点均有专项用例覆盖")
                if issue_cov['tagged_extra_nums']:
                    print("   ℹ️  用例标注了记录外的编号:" + ", ".join(
                        issue_cov['tagged_extra_nums']))
        # ⚠️ 结论行必须与退出码同源：退出码要算上 issue_parse_error，只看 all_passed 会出现
        # 「末行打印『总体:✅ 通过』、EXIT=1」的自相矛盾（QR 子 Agent 会把那句 ✅ 原样贴进报告）。
        if all_passed and not issue_parse_error:
            print('\n总体:✅ 通过')
        elif all_passed:
            print('\n总体:❌ 不通过(用例文档本身合格,但 --issue-record 清单解析失败,见上)')
        else:
            print('\n总体:❌ 不通过')

    # 解析失败无条件走 stderr:--json 模式下 stdout 是纯 JSON 不能污染,但也绝不能因此静默。
    if issue_parse_error:
        print(issue_parse_error, file=sys.stderr)

    # `passed`(JSON 字段)只反映用例文档本身;退出码额外把清单解析失败也算上,
    # 这样只读退出码的接入方同样看得见。两者刻意不合并,见文件头 docstring。
    return 0 if (all_passed and not issue_parse_error) else 1


if __name__ == '__main__':
    sys.exit(main())
