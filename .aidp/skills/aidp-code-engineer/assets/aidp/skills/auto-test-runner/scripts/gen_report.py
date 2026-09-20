#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 round-{M}/results/*.json 聚合生成测试报告统计。

统计口径:总数/Pass/Fail/Block/NA/通过率(Pass/(总数−NA))/自动化率((Pass+Fail)/(总数−NA))/
自动化覆盖率((总数−driver-missing)/总数)/自动化成功率((Pass+Fail)/(总数−driver-missing))/各模块通过情况;
两派生指标据已有 block_reason 枚举计算,driver-missing=0 时与 auto_rate 一致(向后兼容);
另聚合 self_heal_trace(self-heal 失败复测追溯,可选字段);
缺陷分级中,环境类 block_reason(ENV_BLOCK_REASONS:driver-missing / precondition-unmet / network-error …,或执行方显式 is_environment_issue)一律判「环境问题」不计产品缺陷;
其余情形回归([回归]/is_regression)、PRD存在性([PRD存在性])与文案一致性([文案一致性])用例族失败在优先级映射前先锁 Critical(覆盖 P0→P1 等常规映射);
并校验 verified/self-heal 模式的 pass 是否都有 evidence(无证据的 pass = 未验证,质量维度 5)。

输出 --json(供子 Agent 组织报告),或 --md 打印报告「二、测试结果汇总」章
(2.1 汇总数据 / 2.2 各模块 / 2.3 缺陷列表 / 2.4 执行明细 /(有 self-heal 时)2.5 追溯 /(有 free-scan 项时)2.6 自由巡检);
一、概况与三、结论(上线条件/遗留风险/改进建议)属判断性内容,由子 Agent 据本章数据人工撰写,脚本不产出。
仅标准库。退出码:0 = 聚合成功且无「无证据 verified pass」, 1 = 存在无证据 verified pass, 2 = 输入错误。
"""
import argparse
import json
import sys
from pathlib import Path

RESULT_ICON = {'pass': '✅Pass', 'fail': '❌Fail', 'block': '⚠️Block', 'na': '➖N/A'}
# fail 用例优先级 → 缺陷等级映射(P0→P1, P1→P2, P2→P3)
FAIL_LEVEL = {'P0': 'P1', 'P1': 'P2', 'P2': 'P3'}
# ★用例族标记(命中则失败锁 Critical,覆盖优先级映射,见 report-format.md §2.3)
# ⚠️ **`[还原度]` 刻意不在此列,勿「顺手」加进来。** 该族(dev-manual-testcase 维度 21 的通用还原度
#    套件)十条模板项里既有「导出只导当前页」这种确定的 Critical、也有「截断没 tooltip」这种
#    Important,**整族锁 Critical 会把后者拔高成阻断项**。执行结果按每条用例自身 severity 判。
#    (本注释是副本:上游 dev-manual-testcase 各自持一份,按 SKILL 独立性原则不跨 skill 引用。)
CRITICAL_FAMILY_MARKERS = ('[PRD存在性]', 'PRD存在性', '[回归]', '[文案一致性]', '文案一致性')


def _fmt_ms(ms):
    """毫秒 → 人读时长。⚠️ 报告里一律用它,别各处各写一套格式。"""
    try:
        sec = float(ms) / 1000.0
    except (TypeError, ValueError):
        return '—'
    if sec < 60:
        return f'{sec:.1f}s'
    if sec < 3600:
        return f'{sec / 60:.1f}min'
    return f'{sec / 3600:.2f}h'


def has_lightweight_evidence(value):
    """direct pass 的轻量事实门:摘要或产物路径即可,不要求完整截图。

    ⚠️ 与 check_result.has_lightweight_evidence 逻辑必须保持一致(落盘校验 vs 聚合复用同一判据),
    改一处必须同步改另一处——两脚本各自独立、不跨文件 import,故只能靠这行注释提醒。
    """
    if not isinstance(value, list) or not value:
        return False
    for item in value:
        if isinstance(item, str) and item.strip():
            return True
        if isinstance(item, dict) and (str(item.get('summary') or '').strip()
                                       or str(item.get('artifact') or '').strip()):
            return True
    return False


def evidence_artifact(ev):
    """从 evidence 数组取首条证据的产物路径,**对形状不合契约的元素降级而非崩溃**。

    2026-08-18 上游实测反馈:执行方把 evidence 写成字符串数组
    `["round-1/evidence/x.png"]`,而本脚本两处直接 `ev[0].get('artifact')` →
    `AttributeError: 'str' object has no attribute 'get'`,**整份报告聚合中断**。
    结果 JSON 由执行子 Agent 手写、形状本就会漂,聚合器必须容错:
      · 规范形状 {step, summary, artifact} → 取 artifact;
      · 字符串元素 → 整串当 artifact(最常见的简写形态);
      · 其它形状 → 返回 ''(落到 '—'),不抛异常。
    形状告警由 collect_shape_warnings 单独收集,写进报告「遗留风险」,不静默。"""
    if not ev or not isinstance(ev, list):
        return ''
    first = ev[0]
    if isinstance(first, dict):
        return str(first.get('artifact') or '')
    if isinstance(first, str):
        return first
    return ''


def collect_shape_warnings(results):
    """扫描结果 JSON 里不合契约的 evidence / runtimeErrors 形状,产出可读告警(不中断聚合)。
    供报告「三、结论 → 遗留风险」呈现:数据形状不对会让证据路径、运行时错误统计失真。"""
    warns = []
    for r in results:
        cid = r.get('case_id', '?')
        for field in ('evidence', 'runtimeErrors'):
            val = r.get(field)
            if val is None:
                continue
            if not isinstance(val, list):
                warns.append(f'{cid}: `{field}` 不是数组(实为 {type(val).__name__}),已忽略')
                continue
            for i, item in enumerate(val):
                if isinstance(item, dict):
                    if field == 'evidence' and not item.get('artifact'):
                        warns.append(f'{cid}: `evidence[{i}]` 缺 artifact(证据路径将显示 —)')
                elif isinstance(item, str):
                    warns.append(f'{cid}: `{field}[{i}]` 是字符串而非对象,已按 artifact 兼容解析'
                                 f'(规范形状见 assets/result-schema.json)')
                else:
                    warns.append(f'{cid}: `{field}[{i}]` 形状不合契约({type(item).__name__}),已跳过')
    return warns


def is_critical_family(r):
    """判断该用例是否属「回归 / PRD存在性 / 文案一致性」用例族(失败须锁 Critical)。
    识别源:① is_regression 布尔透传;② 用例标题/类型/套件/case_family/tags 里出现
    文本标记 [回归]/[PRD存在性]/[文案一致性];③ 类型直接等于「回归」。按文本标记识别,与 dev-manual-testcase 共享契约。
    [文案一致性]:语义/口径变更后旧文案残留(反向断言"不存在文本X"命中)或新语义未落地,口径误导对账,失败锁 Critical。"""
    if r.get('is_regression'):
        return True
    if str(r.get('type', '')).strip() == '回归':
        return True
    hay = ' '.join(str(r.get(k, '')) for k in
                   ('test_name', 'type', 'suite', 'case_family', 'tags'))
    return any(m in hay for m in CRITICAL_FAMILY_MARKERS)


# ★环境类 block_reason 单一信源(命中即判「环境问题」、不计产品缺陷、不锁 Critical)。
# 前置环境未就绪导致的整批 block 若被计成产品缺陷,会污染下游「缺陷→升级 bug→回写问题汇总清单」链路。
# 此集合供 level_defect 与环境问题统计共用,新增环境类枚举只改这一处。
# ⚠️ retry-exhausted 刻意不在集合内——「单操作重试到顶」既可能是环境抖动、也可能是真缺陷
# (元素永远定位不到 = 页面没渲染出来),保守留在「待验证/产品缺陷」侧由人复核,宁可多看一眼。
ENV_BLOCK_REASONS = frozenset({
    'driver-missing',      # 驱动未装/不可用,该端用例整体跳过
    'driver-hung',         # 驱动进程级卡死,且连续 driver_heal_retry_limit 次自愈重启均失败
    'precondition-unmet',  # 前置不满足(账号失效/前置数据缺失/依赖系统未就绪)
    'network-error',       # 网络或接口不可达
    'env-unavailable',     # 被测环境整体不可用(预留)
    'account-invalid',     # 测试账号失效/权限被回收(预留)
    # 条件启用能力(WebMCP)的驱动版本类阻塞:驱动版本太旧 / 版本取不到。
    # 与 driver-missing 同性质——环境没准备好,不是被测产品的缺陷。
    'webmcp-driver-too-old',
    'webmcp-driver-version-unknown',
})


def is_env_issue(r):
    """判断该条结果是否属「环境问题」(不计产品缺陷)。

    优先读执行方显式标注的 `is_environment_issue`(执行方最了解阻塞性质,可覆盖枚举推断);
    缺省时回落到 `block_reason ∈ ENV_BLOCK_REASONS` 的枚举判定(向后兼容旧结果 JSON)。
    只有 status=block 才可能是环境问题——fail 表示用例真跑起来了且断言不符,不归环境。"""
    if str(r.get('status', '')) != 'block':
        return False
    explicit = r.get('is_environment_issue')
    if isinstance(explicit, bool):
        return explicit
    return r.get('block_reason') in ENV_BLOCK_REASONS


def level_defect(status, priority, block_reason, critical_family=False, env_issue=None):
    """据用例结果 + 优先级 + block_reason 枚举返回 (等级, 类别, 是否计入产品缺陷)。
    见 report-format.md §2.3。block_reason 枚举而非 error 文本判定。
    ★环境问题优先级最高:命中 ENV_BLOCK_REASONS(或执行方显式标 is_environment_issue)一律
    判「环境问题」、不计产品缺陷、不锁 Critical——即便是回归/PRD存在性/文案一致性用例族,
    环境没起来也不是产品缺陷(锁 Critical 只对"真跑起来了但不对"有意义)。
    ★其次用例族锁定优先于优先级映射:回归 / PRD存在性 / 文案一致性 用例族失败一律 Critical,
    覆盖 P0→P1/P1→P2/P2→P3 常规映射,不许降级。"""
    if env_issue is None:  # 兼容旧调用签名(只传 block_reason)
        env_issue = status == 'block' and block_reason in ENV_BLOCK_REASONS
    if env_issue:
        return ('—', '环境问题', False)
    if critical_family:
        # 回归 / PRD存在性 / 文案一致性 用例族失败一律 Critical(先于优先级映射)
        if status == 'fail':
            return ('Critical', '产品缺陷', True)
        # 非环境类的 block 亦属未通过 → Critical 待验证
        return ('Critical 待验证', '待验证', True)
    if status == 'block':
        # retry-exhausted 等非环境类阻塞 → 待验证
        lvl = 'P2' if priority in ('P0', 'P1') else 'P3'
        return (f'{lvl} 待验证', '待验证', True)
    # status == 'fail'
    return (FAIL_LEVEL.get(priority, 'P3'), '产品缺陷', True)


# round 目录根下的非用例产物。回退分支(无 results/ 子目录时直接 glob round 根)必须排除它们,
# 否则 env-facts.json 会被当成一条用例统计——实测「1 条用例 + env-facts.json」曾聚合出
# total=2 / block=2 / 多出一个「未分组」模块。用文件名黑名单 + 「无 case_id 即非用例」双保险。
NON_RESULT_FILES = {'env-facts.json', 'token-usage.json', 'run-context.json'}


def load_results(round_dir):
    rd = Path(round_dir)
    fallback = not (rd / 'results').is_dir()
    results_dir = rd if fallback else rd / 'results'
    files = sorted(results_dir.glob('*.json'))
    out = []
    for f in files:
        if f.name in NON_RESULT_FILES:
            continue
        try:
            data = json.loads(f.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError):
            continue
        # 回退分支下 round 根可能混入其它元数据 JSON:没有 case_id 的一律不算用例
        if fallback and not (isinstance(data, dict) and data.get('case_id')):
            continue
        out.append(data)
    return out


FREE_SCAN_KIND = 'free-scan'


def split_entries(entries):
    """把「自由巡检项」从用例集里分出来。

    ⚠️ **为什么必须分流:** 巡检项是对「菜单可达但用例未覆盖」页面的探索性导航,
    不是任何一条用例的断言。若混进 `total`,通过率、自动化率、以及「P0 100%」这类
    通过准则会被一批**没有断言**的条目稀释 —— 巡检页越多指标越好看,方向恰好是反的。
    故巡检项**不计入用例统计、不进缺陷列表**,单列 §2.6,由人确认后再转 bug。
    """
    scans = [r for r in entries if isinstance(r, dict) and r.get('entry_kind') == FREE_SCAN_KIND]
    cases = [r for r in entries if not (isinstance(r, dict) and r.get('entry_kind') == FREE_SCAN_KIND)]
    return cases, scans


def aggregate(all_entries):
    results, scans = split_entries(all_entries)
    total = len(results)
    counts = {'pass': 0, 'fail': 0, 'block': 0, 'na': 0}
    modules = {}
    no_evidence = []  # verified/self-heal 且 pass 但 evidence 空
    direct_pass_without_evidence = []  # direct pass 缺轻量事实,Important 不阻断
    defects = []
    runtime_findings = []  # pass 用例携带的运行时错误(供升级 bug)
    self_heal_traces = []  # 携带 self_heal_trace 的用例(供报告明细/遗留风险展示)
    driver_missing = 0     # block(driver-missing) 计数(环境未装驱动整体跳过)
    timings, timing_missing = [], []
    self_heal_actual = 0
    mode_counts, mech_counts = {}, {}
    for r in results:
        st = r.get('status', 'block')
        counts[st] = counts.get(st, 0) + 1
        suite = r.get('suite', '未分组')
        m = modules.setdefault(suite, {'total': 0, 'pass': 0, 'fail': 0, 'block': 0, 'na': 0})
        m['total'] += 1
        m[st] = m.get(st, 0) + 1
        mode = r.get('execution_mode', 'direct')
        if st == 'block' and r.get('block_reason') == 'driver-missing':
            driver_missing += 1
        if st == 'pass' and mode in ('verified', 'self-heal') and not r.get('evidence'):
            no_evidence.append(r.get('case_id', '?'))
        elif st == 'pass' and mode == 'direct' and not has_lightweight_evidence(r.get('evidence')):
            direct_pass_without_evidence.append(r.get('case_id', '?'))
        # ── 单条耗时(2026-09-10 下游实证:没有它,任何优化都无法验证是否生效) ──
        # ⚠️ `elapsed_ms` 优先、`duration_ms` 兼容回落:旧结果只有后者,不回落等于整轮没有耗时。
        el = r.get('elapsed_ms')
        if not isinstance(el, (int, float)) or isinstance(el, bool):
            el = r.get('duration_ms')
        if isinstance(el, (int, float)) and not isinstance(el, bool) and el >= 0:
            timings.append({'case_id': r.get('case_id', '?'), 'suite': suite,
                            'status': st, 'elapsed_ms': float(el)})
        else:
            timing_missing.append(r.get('case_id', '?'))
        # ★ 实际触发自愈的次数 ≠ execution_mode=self-heal(后者只表示「具备」自愈能力)
        att = r.get('self_heal_attempts')
        if isinstance(att, (int, float)) and not isinstance(att, bool) and att > 0:
            self_heal_actual += int(att)
        elif r.get('self_heal_applied'):
            self_heal_actual += 1          # 旧结果没有 attempts 字段,按「至少一次」计
        mode_counts[mode] = mode_counts.get(mode, 0) + 1
        # ⚠️ **未声明 ≠ dom**:把缺省算进 `dom` 等于替执行方断言「这条走的是 DOM」,
        #    而事实是**没人填过这一格** —— 与约束 10「事实字段可溯源、禁模板默认」直接冲突,
        #    且方向是假绿(真用了 WebMCP 验还原度、却不填 mechanism 的那条,报告上会显示成 dom)。
        #    故单列 `未声明` 桶,让「这一档没测量」在报告里看得见。⛔ 别改回 `or 'dom'`。
        mkey = r.get('mechanism')
        mkey = str(mkey) if isinstance(mkey, str) and mkey.strip() else '未声明'
        mech_counts[mkey] = mech_counts.get(mkey, 0) + 1

        # self-heal 失败反思追溯(可选字段;缺省则不收集)
        sht = r.get('self_heal_trace')
        if isinstance(sht, dict) and sht:
            self_heal_traces.append({
                'case_id': r.get('case_id', '?'), 'suite': suite, 'status': st,
                'cause': sht.get('cause', ''), 'recovery': sht.get('recovery', ''),
                'outcome': sht.get('outcome', ''),
            })
        rt_errors = r.get('runtimeErrors') or []
        # 形状容错:非数组、或元素非对象的一律跳过(告警由 collect_shape_warnings 单收),不崩不静默
        rt_errors = [e for e in rt_errors if isinstance(e, dict)] if isinstance(rt_errors, list) else []
        if st in ('fail', 'block'):
            crit_family = is_critical_family(r)
            env_flag = is_env_issue(r)
            lvl, cat, is_product = level_defect(
                st, r.get('priority', ''), r.get('block_reason'), crit_family, env_flag)
            detail = r.get('error', '') or ''
            # 去重:同用例的运行时错误折进本条缺陷,不另计(report-format §2.3)
            if rt_errors:
                detail = f"{detail}(另含 {len(rt_errors)} 条运行时错误)"
            defects.append({
                'case_id': r.get('case_id', '?'), 'suite': suite,
                'priority': r.get('priority', ''), 'status': st,
                'block_reason': r.get('block_reason'),
                'level': lvl, 'category': cat, 'is_product_defect': is_product,
                'is_environment_issue': env_flag,
                'critical_family': crit_family,
                'is_regression': bool(r.get('is_regression')),
                'related_defect_id': r.get('related_defect_id'),
                'error': detail, 'evidence': r.get('evidence', []),
                'kind': 'case',
            })
        else:
            # pass 用例的运行时错误:单列为「运行时错误」发现项(供升级 bug),
            # 不折进任何 case 缺陷(该用例本身通过)
            for e in rt_errors:
                runtime_findings.append({
                    'case_id': r.get('case_id', '?'), 'suite': suite,
                    'level': e.get('severity', 'P3'), 'category': '运行时错误',
                    'type': e.get('type', ''), 'error': e.get('detail') or e.get('message', ''),
                    'artifact': e.get('artifact', ''), 'kind': 'runtime',
                })

    product_defect_count = sum(1 for d in defects if d['is_product_defect'])
    env_issue_count = sum(1 for d in defects if not d['is_product_defect'])
    # 环境问题按 block_reason 细分(供报告写清「32 条全是前置未就绪」而不是笼统一句环境问题)
    env_issue_by_reason = {}
    for d in defects:
        if not d['is_product_defect']:
            k = d.get('block_reason') or 'unknown'
            env_issue_by_reason[k] = env_issue_by_reason.get(k, 0) + 1
    # ★回归 / PRD存在性 / 文案一致性 用例族失败被真正锁 Critical 的缺陷数(driver-missing 属环境问题、未锁,不计;供报告醒目呈现)
    critical_family_count = sum(
        1 for d in defects if d.get('critical_family') and str(d['level']).startswith('Critical'))
    runtime_finding_count = len(runtime_findings)
    na_count = counts['na']
    eligible_total = total - na_count
    pass_rate = counts['pass'] / eligible_total if eligible_total else 0
    auto_rate = (counts['pass'] + counts['fail']) / eligible_total if eligible_total else 0
    # ★na 不属于可执行范围,所有比例分母先排除 na;再排除 driver-missing 计算可尝试范围。
    attemptable = eligible_total - driver_missing
    auto_cover_rate = attemptable / eligible_total if eligible_total else 0
    auto_success_rate = (counts['pass'] + counts['fail']) / attemptable if attemptable else 0
    for m in modules.values():
        module_eligible = m['total'] - m.get('na', 0)
        m['pass_rate'] = round(m['pass'] / module_eligible, 4) if module_eligible else 0
    # 自由巡检聚合(free_scan 开启时才有;缺省为空,整节不输出)
    scan_findings = []
    for sc in scans:
        sc_rt = sc.get('runtimeErrors') or []
        sc_rt = [e for e in sc_rt if isinstance(e, dict)] if isinstance(sc_rt, list) else []
        scan_findings.append({
            'page': sc.get('test_name') or sc.get('case_id', '?'),
            'case_id': sc.get('case_id', '?'),
            'status': sc.get('status', 'block'),
            'error_count': len(sc_rt),
            'errors': sc_rt,
            'evidence': sc.get('evidence', []),
            # ★必须保留:12.6「不静默截断」的做法就是把「被跳过的页面清单」写进 error;
            #   导航失败/白屏巡检项的失败原因同样在这里。丢了它这条承诺在报告里就落空了。
            'error': sc.get('error', '') or '',
        })
    scan_error_count = sum(f['error_count'] for f in scan_findings)

    return {
        'total': total,
        'eligible_total': eligible_total,
        'counts': counts,
        'na_count': na_count,
        'pass_rate': round(pass_rate, 4),
        'auto_rate': round(auto_rate, 4),
        'auto_cover_rate': round(auto_cover_rate, 4),
        'auto_success_rate': round(auto_success_rate, 4),
        'driver_missing_count': driver_missing,
        'modules': modules,
        'defects': defects,
        'runtime_findings': runtime_findings,
        'self_heal_traces': self_heal_traces,
        'timings': sorted(timings, key=lambda x: -x['elapsed_ms']),
        'timing_missing': timing_missing,
        'elapsed_total_ms': sum(t['elapsed_ms'] for t in timings),
        'self_heal_actual': self_heal_actual,
        'mode_counts': mode_counts,
        'mech_counts': mech_counts,
        'product_defect_count': product_defect_count,
        'env_issue_count': env_issue_count,
        'env_issue_by_reason': env_issue_by_reason,
        'critical_family_count': critical_family_count,
        'runtime_finding_count': runtime_finding_count,
        'verified_pass_without_evidence': no_evidence,
        'direct_pass_without_evidence': direct_pass_without_evidence,
        # 形状告警查**全集**(巡检项写歪了同样要报),故用 all_entries 而非分流后的 results
        'shape_warnings': collect_shape_warnings(all_entries),
        'scan_count': len(scans),
        'scan_findings': scan_findings,
        'scan_error_count': scan_error_count,
    }


def to_md(agg, results):
    # ⚠️ **内部再分流一次(防呆)**:main() 传进来的是**未分流的全集**,而 §2.4 明细直接遍历它——
    #    巡检项会既在 §2.6 单列、又在 §2.4 冒充用例占一行,导致 §2.4 行数 ≠ §2.1 用例总数,
    #    报告自相矛盾(正是本次改动声称要杜绝的失败模式)。这里不依赖调用方是否已分流。
    results, _ = split_entries(results)
    L = []
    c = agg['counts']
    L.append('## 二、测试结果汇总\n')
    L.append('### 2.1 汇总数据\n')
    L.append('| 用例总数 | 可计算总数 | 执行数 | Pass | Fail | Block | N/A | 通过率 | 自动化率 | 自动化覆盖率 | 自动化成功率 |')
    L.append('| :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: |')
    L.append(f"| {agg['total']} | {agg['eligible_total']} | {agg['eligible_total']} | {c['pass']} | {c['fail']} | "
             f"{c['block']} | {c['na']} | {agg['pass_rate']:.1%} | {agg['auto_rate']:.1%} | "
             f"{agg['auto_cover_rate']:.1%} | {agg['auto_success_rate']:.1%} |")
    L.append(f"> N/A={c['na']} 条,不计入通过率分子与分母;通过率=Pass/(总数−N/A);自动化率=(Pass+Fail)/(总数−N/A);"
             f"自动化覆盖率=(可计算总数−driver-missing {agg['driver_missing_count']} 条)/可计算总数;"
             f"自动化成功率=(Pass+Fail)/(可计算总数−driver-missing)。\n")
    direct_missing = agg.get('direct_pass_without_evidence') or []
    if direct_missing:
        L.append(f"> ⚠️ **无依据的 direct pass：{len(direct_missing)} 条**(Important,不阻断):"
                 f" {', '.join(direct_missing[:20])}"
                 f"{' …' if len(direct_missing) > 20 else ''}\n")

    L.append('### 2.2 各模块通过情况\n')
    L.append('| 模块 | 用例数 | Pass | Fail | Block | N/A | 通过率 |')
    L.append('| :- | :-: | :-: | :-: | :-: | :-: | :-: |')
    for name, m in agg['modules'].items():
        L.append(f"| {name} | {m['total']} | {m['pass']} | {m.get('fail', 0)} | "
                 f"{m.get('block', 0)} | {m.get('na', 0)} | {m['pass_rate']:.1%} |")
    L.append('')

    L.append('### 2.3 缺陷列表\n')
    by_reason = agg.get('env_issue_by_reason') or {}
    reason_txt = ('(' + ' / '.join(f'{k} {v}' for k, v in sorted(by_reason.items())) + ')') if by_reason else ''
    L.append(f"> 产品缺陷 {agg['product_defect_count']} 条(其中回归/PRD存在性/文案一致性用例族锁 Critical "
             f"{agg.get('critical_family_count', 0)} 条)/ 环境问题 {agg['env_issue_count']} 条{reason_txt} "
             f"/ 运行时错误(pass 用例携带){agg['runtime_finding_count']} 条"
             f"(环境类 block_reason ——driver-missing / precondition-unmet / network-error 等——编号 ENV-xxx、"
             f"不计产品缺陷;同用例 error+fail 只计一条;缺陷数 ≠ fail+block 数)\n")
    L.append('| 缺陷编号 | 等级 | 类别 | 所属模块 | 问题详情 | 证据路径 | 关联用例 |')
    L.append('| :- | :-: | :- | :- | :- | :- | :- |')
    case_defect = {}  # case_id → 缺陷编号(供 2.4「关联缺陷」列回填)
    pi = ei = 0
    for d in agg['defects']:
        detail = (d['error'] or '')[:60].replace('\n', ' ')
        if d['is_product_defect']:
            pi += 1
            no = f'BUG-{pi:03d}'
        else:
            ei += 1
            no = f'ENV-{ei:03d}'
        ev_path = evidence_artifact(d.get('evidence')) or '—'
        case_defect.setdefault(d['case_id'], no)
        L.append(f"| {no} | {d['level']} | {d['category']} | {d['suite']} | {detail} | {ev_path} | {d['case_id']} |")
    # pass 用例携带的运行时错误(供升级 bug)
    for i, e in enumerate(agg['runtime_findings'], 1):
        detail = f"[{e['type']}] {(e['error'] or '')[:50]}".replace('\n', ' ')
        L.append(f"| RT-{i:03d} | {e['level']} | 运行时错误 | {e['suite']} | {detail} | "
                 f"{e.get('artifact') or '—'} | {e['case_id']} |")
    if not agg['defects'] and not agg['runtime_findings']:
        L.append('| — | — | — | — | 无缺陷 | — | — |')
    L.append('')

    L.append('### 2.4 用例执行明细\n')
    L.append('| 用例编号 | 名称 | 优先级 | 模式 | 结果 | 失败原因 | 关联缺陷 | 证据 |')
    L.append('| :- | :- | :-: | :-: | :-: | :- | :- | :- |')
    for r in results:
        cid = r.get('case_id', '?')
        icon = RESULT_ICON.get(r.get('status', 'block'), '?')
        err = (r.get('error') or '')[:50].replace('\n', ' ')
        ev_path = evidence_artifact(r.get('evidence')) or '—'
        L.append(f"| {cid} | {r.get('test_name', '')} | "
                 f"{r.get('priority', '')} | {r.get('execution_mode', '')} | {icon} | {err} | "
                 f"{case_defect.get(cid, '—')} | {ev_path} |")

    # 结果 JSON 形状告警(仅在有不合契约形状时输出;供报告「三、结论 → 遗留风险」引用)
    shape_warns = agg.get('shape_warnings') or []
    if shape_warns:
        L.append('')
        L.append(f'> ⚠️ **结果 JSON 形状告警 {len(shape_warns)} 条**(已按兼容规则解析、未中断聚合,'
                 f'但证据路径/运行时错误统计可能失真,请一并写入「三、结论 → 遗留风险」):')
        for w in shape_warns[:20]:
            L.append(f'> - {w}')
        if len(shape_warns) > 20:
            L.append(f'> - …另有 {len(shape_warns) - 20} 条,见 `--json` 的 `shape_warnings`')

    # self-heal 失败反思追溯(仅在有 self_heal_trace 时输出;缺省则整段不出)
    traces = agg.get('self_heal_traces') or []
    if traces:
        L.append('')
        L.append('### 2.5 self-heal 失败复测追溯\n')
        L.append('> 触发状态恢复重试的用例,记录 为何失败(cause)/ 做了什么恢复(recovery)/ 复测结论(outcome);'
                 'outcome=still-fail-block 的同时归入 §3.2 遗留风险。\n')
        L.append('| 用例编号 | 结果 | 根因(cause) | 恢复动作 + observe 检验(recovery) | 复测结论(outcome) |')
        L.append('| :- | :-: | :- | :- | :-: |')
        for t in traces:
            icon = RESULT_ICON.get(t.get('status', 'block'), '?')
            cause = (t.get('cause') or '')[:50].replace('\n', ' ')
            recovery = (t.get('recovery') or '')[:60].replace('\n', ' ')
            L.append(f"| {t['case_id']} | {icon} | {cause} | {recovery} | {t.get('outcome', '')} |")

    # 自由巡检(仅 free_scan 开启且有巡检项时输出;缺省整段不出)
    scan_findings = agg.get('scan_findings') or []
    if scan_findings:
        L.append('')
        L.append('### 2.6 自由巡检(未被用例覆盖的页面)\n')
        # 阻塞项(含 12.6「已达巡检上限」标记项)不算已巡检页面,否则抬头会把"跳过 7 页"报成"巡检了 1 页"
        scanned = [f for f in scan_findings if f.get('status') != 'block']
        blocked = [f for f in scan_findings if f.get('status') == 'block']
        head = (f"> 对「菜单可达、但本轮用例未覆盖」的 {len(scanned)} 个页面逐个导航并拉运行时错误,"
                f"共发现 {agg.get('scan_error_count', 0)} 条。")
        if blocked:
            head += f"另有 {len(blocked)} 项阻塞/未巡检(见下表「导航结果」为 ⚠️Block 的行)。"
        L.append(head + '\n'
                 '> **不计入用例统计、不进缺陷列表** —— 巡检项没有断言,混入会稀释通过率与「P0 100%」准则。\n'
                 '> 这里的发现是**线索**:需人工确认后再转 bug,或补成正式用例进下一轮。\n')
        L.append('| 页面 | 导航结果 | 运行时错误数 | 最高级别 | 摘要 |')
        L.append('| :- | :-: | :-: | :-: | :- |')
        for f in scan_findings:
            icon = RESULT_ICON.get(f.get('status', 'block'), '?')
            errs = f.get('errors') or []
            top = min((str(e.get('severity', 'P3')) for e in errs), default='—')
            summary = '; '.join(
                (e.get('message') or e.get('detail') or '')[:40].replace('\n', ' ') for e in errs[:3])
            # 无 runtimeErrors 时回落 error:上限标记项的「跳过了哪些页面」、
            # 导航失败项的失败原因都在 error 里,不回落这两类信息整条不进报告
            if not summary:
                summary = (f.get('error') or '')[:80].replace('\n', ' ') or '—'
            L.append(f"| {f['page']} | {icon} | {f['error_count']} | {top} | {summary} |")
    # ── 2.7 耗时分布(2026-09-10 新增) ──
    # ⚠️ **本节存在的全部理由**:下游实证两轮 116 条里,`TC-PXY-F01` **一条占总时长 25%**,
    #    而这个结论是靠三个 evidence 文件的 mtime 跨度**手工反推**才发现的 —— 只要那条用例少产
    #    一个证据文件,它就整条漏掉。有了 elapsed_ms 就能直接排序,「哪条慢」不再靠运气。
    # ⚠️ 无耗时数据时**不输出空表**,而是打一行「未采集」——空表会被读成「都很快」。
    timings = agg.get('timings') or []
    tmiss = agg.get('timing_missing') or []
    if timings or tmiss:
        L.append('')
        L.append('### 2.7 耗时分布\n')
        if not timings:
            L.append(f'> ⚠️ **本轮 {len(tmiss)} 条用例全部未采集单条耗时**(`started_at`/`finished_at`/`elapsed_ms`)。\n'
                     f'> **这不是「都很快」,是「没测量」** —— 在补齐它之前,任何针对耗时的优化都无法验证是否生效。\n')
        else:
            tot = agg.get('elapsed_total_ms', 0.0)
            L.append(f'> 已采集 {len(timings)} 条,合计 {_fmt_ms(tot)}'
                     + (f';**另有 {len(tmiss)} 条未采集耗时**(其真实耗时不在下表内,'
                        f'⛔ 不要把本表合计当作全轮执行时长)' if tmiss else '') + '。\n')
            L.append('| # | 用例 | 套件 | 结果 | 耗时 | 占已采集合计 |')
            L.append('| :-: | :- | :- | :-: | -: | -: |')
            for i, t in enumerate(timings[:10], 1):
                pct = (t['elapsed_ms'] / tot * 100) if tot else 0.0
                L.append(f"| {i} | {t['case_id']} | {t['suite']} | "
                         f"{RESULT_ICON.get(t['status'], '?')} | {_fmt_ms(t['elapsed_ms'])} | {pct:.1f}% |")
            if len(timings) > 10:
                L.append(f"\n> 只列耗时最长的 10 条(共 {len(timings)} 条)。")
        # ★ execution_mode 语义纠偏:两个字段并排出现时极易被读反
        mc = agg.get('mode_counts') or {}
        if mc:
            dist = ' / '.join(f'{k}={v}' for k, v in sorted(mc.items()))
            L.append(f"\n> **execution_mode 分布**:{dist};**实际触发自愈 "
                     f"{agg.get('self_heal_actual', 0)} 次**。\n"
                     f"> ⚠️ `execution_mode=self-heal` 表示「**具备**自愈能力」,**不表示「实际自愈了」** —— "
                     f"下游实证曾把「43 条 self-heal」读成「43 条在重跑」,而实际只重试过 1 次,"
                     f"调优方向当场被带偏。两个数必须并排看。")
        mech = agg.get('mech_counts') or {}
        if mech and set(mech) - {'dom'}:
            L.append(f"\n> **执行机制分布**:{' / '.join(f'{k}={v}' for k, v in sorted(mech.items()))}"
                     f"(枚举 dom / webmcp / mixed;`未声明` = **结果 JSON 没填 `mechanism`**,"
                     f"⛔ 不等于 dom —— 那一档没测量,`[还原度]` 类若实际走了 WebMCP 在这里看不出来)。")
    return '\n'.join(L)


def main():
    ap = argparse.ArgumentParser(
        description='从 round-{M}/results/*.json 聚合生成测试报告统计:总数/Pass/Fail/Block/'
                    '通过率/自动化率/各模块/缺陷分级;并校验 verified/self-heal 的 pass 是否都有 evidence。',
        epilog='示例:\n'
               '  python3 gen_report.py round-1 --json   # 聚合为 JSON(供子 Agent 组织报告)\n'
               '  python3 gen_report.py round-1 --md     # 打印报告「二、汇总」章 markdown(概况/结论由子 Agent 撰写)\n'
               '  python3 gen_report.py round-1          # 打印一行摘要',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('round_dir', help='round-{M} 目录(含 results/ 子目录,或直接是 *.json 所在目录)')
    ap.add_argument('--json', action='store_true', help='JSON 输出(供子 Agent 解析)')
    ap.add_argument('--md', action='store_true',
                    help='打印报告「二、测试结果汇总」章 markdown(2.1~2.7;2.5/2.6 为可选节,2.7 无耗时数据时打「全部未采集」而非空表);概况/结论由子 Agent 撰写')
    args = ap.parse_args()

    if not Path(args.round_dir).exists():
        msg = f'目录不存在:{args.round_dir}'
        print(json.dumps({'error': msg}, ensure_ascii=False) if args.json else msg)
        return 2

    results = load_results(args.round_dir)
    if not results:
        msg = f'未找到结果 JSON:{args.round_dir}'
        print(json.dumps({'error': msg}, ensure_ascii=False) if args.json else msg)
        return 2

    agg = aggregate(results)
    if args.json:
        print(json.dumps(agg, ensure_ascii=False, indent=2))
    elif args.md:
        print(to_md(agg, results))
    else:
        c = agg['counts']
        print(f"总数 {agg['total']} | Pass {c['pass']} / Fail {c['fail']} / Block {c['block']} / N/A {c['na']}"
              f"(driver-missing {agg['driver_missing_count']})"
              f" | 通过率 {agg['pass_rate']:.1%} | 自动化率 {agg['auto_rate']:.1%}"
              f" | 覆盖率 {agg['auto_cover_rate']:.1%} | 成功率 {agg['auto_success_rate']:.1%}")
        if agg.get('direct_pass_without_evidence'):
            print(f"⚠️ 无依据的 direct pass: {len(agg['direct_pass_without_evidence'])} 条(Important,不阻断)")
        if agg.get('shape_warnings'):
            print(f"⚠️ 结果 JSON 形状告警 {len(agg['shape_warnings'])} 条(已兼容解析,见 --json/--md)")
        if agg['verified_pass_without_evidence']:
            print(f"❌ 无证据的 verified/self-heal pass:"
                  f"{agg['verified_pass_without_evidence']}")

    return 1 if agg['verified_pass_without_evidence'] else 0


if __name__ == '__main__':
    sys.exit(main())
