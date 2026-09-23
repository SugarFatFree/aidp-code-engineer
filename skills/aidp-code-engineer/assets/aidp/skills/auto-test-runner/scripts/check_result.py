#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用例结果 JSON 落盘前校验(形状 + 枚举 + 取证契约)。

**为什么需要它:** `assets/result-schema.json` 本质是一份**示例 JSON**(`$comment` 标注「示例」),
`evidence` 只给了一个对象数组样例,**没有任何 JSON Schema 意义上的 items/required 约束**——
执行方无从被机器提示「evidence 元素必须是对象、必须含 artifact」。2026-08-18 上游实测:
执行方把 evidence 写成字符串数组,`gen_report.py` 直接 `AttributeError` 崩掉整份报告聚合。
`gen_report.py` 侧已改为**兼容解析 + 形状告警**(不再崩),本脚本则把同一套契约前移到**落盘时**,
让形状错误在写结果那一刻就被拦住,而不是攒到聚合期才发现。

校验项(Critical = 会让报告数据失真或聚合失效;Important = 不规范但可兼容解析):
  C1 缺 case_id / status 非法(不在 pass|fail|block|na)
  C2 status=block 但 block_reason 缺失或不在枚举内
  C3 evidence / runtimeErrors 不是数组
  C4 verified|self-heal 模式的 pass 无 evidence(= 未验证,质量维度 5)
  C5 self_heal_applied=true 但 self_heal_trace 空
  C6 db_assertion 结构不合契约(缺 pageValue/sqlValue/match)
  C7 db_assertion.match=false 但 status 不是 fail
  C8 entry_kind 非法(仅 case | free-scan)
  C9 status=na 但 note/na_reason/error 均为空(不适用必须有理由)
  C10 precondition_probe 结构不合契约(缺 id/status/detail/evidence)
  C11 precondition_probe.status 不在枚举内(satisfied|unmet|probe-error)
  C12 precondition_probe.status=unmet 但 status≠block 或 block_reason≠precondition-unmet
  C13 precondition_probe.status=probe-error 但 block_reason=precondition-unmet(探测失败伪装成数据缺位)
  C14 [还原度]/视觉类用例把 mechanism 标成 webmcp(WebMCP 读的是页面**声明的能力**、不是**渲染结果**,
      用它验还原度会让渲染层缺陷 100% 漏测**且全绿**——本条是唯一会「静默变绿」的机制误用)
  C15 mechanism 不在枚举内(dom | webmcp | mixed)
  I1 evidence 元素是字符串(按 artifact 兼容解析,但非规范形状)
  I2 evidence 元素是对象却缺 artifact(证据路径将显示 —)
  I3 runtimeErrors 元素形状不合契约(缺 type/message/severity)
  I4 is_environment_issue 不是布尔
  I5 case_id 形如巡检项(`运行时-…`)却未标 entry_kind=free-scan(会被计入用例统计)
  I6 某个 target 未匹配到任何结果 JSON(多路径下防「少校验一整轮却显示通过」)
  I7 direct 模式的 pass 无轻量事实 evidence(不阻断,报告单列「无依据的 direct pass」)
  I8 缺单条耗时(started_at/finished_at/elapsed_ms 三件套不齐)——⚠️ **判 Important 不判 Critical**:
     存量结果一条都没有,判死会让整个校验被绕过(同全仓「假红常驻 = 硬门被绕过」);
     但**没有单条耗时就无法判断任何优化是否生效**,故必须报出来
  I9 elapsed_ms 与 finished_at−started_at 相差 > 2s(两者不是同一次计时,数据不可信)
  I10 elapsed_ms 与旧字段 duration_ms 并存且不等
  I11 execution_mode=self-heal 但 retries=0 且 self_heal_attempts=0(= **具备**自愈能力而**未曾**自愈,
      本身完全正常;报出来是为了让「43 条 self-heal」不被读成「43 条在重跑」——下游实证的误导点)

仅标准库。退出码:0 = 无 Critical(`--strict` 时还须无 Important);1 = 有 Critical;2 = 输入错误。
用法:
  python3 check_result.py <round目录>/results/TC-001.json
  python3 check_result.py <round目录>/results/          # 整目录
  python3 check_result.py <round目录>/results/ --json --strict
  python3 check_result.py build-3/round-*/results/     # 跨轮次一次校验
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

STATUS_ENUM = {'pass', 'fail', 'block', 'na'}
NA_REASON_FIELDS = ('note', 'na_reason', 'error')
# 与 assets/result-schema.json 的 $field_notes.block_reason + gen_report.ENV_BLOCK_REASONS 对齐。
# ⚠️ 本表是「合法 block_reason」全集,含非环境类的 retry-exhausted;
#    「哪些算环境问题」的口径归 gen_report.ENV_BLOCK_REASONS,两者不是一回事,勿合并。
BLOCK_REASON_ENUM = {
    'retry-exhausted', 'driver-missing', 'driver-hung', 'precondition-unmet',
    'network-error', 'env-unavailable', 'account-invalid',
    # ★条件启用能力的驱动版本类阻塞(WebMCP,仅 webmcp_enabled: true 时可能出现)。
    #   ⚠️ 与 driver-missing 同属**环境类**,必须同步进 gen_report.ENV_BLOCK_REASONS,
    #   否则「驱动版本太旧」这种纯环境阻塞会被编号成产品 BUG——正是 report-format.md
    #   §2.3「勿改回」那条已实测踩过的坑(32 条环境 block 被误报成 32 个产品缺陷)。
    'webmcp-driver-too-old', 'webmcp-driver-version-unknown',
}
EVIDENCE_REQUIRED_MODES = {'verified', 'self-heal'}
# 与 assets/result-schema.json 的 $shape.precondition_probe.status枚举 对齐。
PRECONDITION_STATUS_ENUM = {'satisfied', 'unmet', 'probe-error'}
# 条目类型:普通用例(缺省) vs 自由巡检项。巡检项不计入用例统计,详见 gen_report.split_entries。
ENTRY_KIND_ENUM = {'case', 'free-scan'}
# 本条用例的主要执行机制。⚠️ `webmcp` 只允许用于**状态准备/数据构造/非视觉断言**类用例;
#    视觉还原度类严禁(C14),见 references/execution-methodology.md「WebMCP 分层铁律」。
MECHANISM_ENUM = {'dom', 'webmcp', 'mixed'}
# 判「这条是不是视觉还原度类」的信号:上游 dev-manual-testcase 的用例族标记会透传到
# type / test_name / case_id。⚠️ 刻意用**多字段任一命中**:标记透传到哪个字段各端不一致,
#    只认一个字段会在别的端静默失配 —— 而失配方向正是 C14 要防的假绿。
FIDELITY_MARKERS = ('还原度', '视觉', '布局', '样式')
# ⚠️⚠️ **本字段集必须 ⊇ gen_report.py `is_critical_family()` 的字段集**(现为
#    test_name / type / suite / case_family / tags)。2026-09-10 首版只取
#    (type, test_name, case_id, suite),而 `usecase-format.md` §五明写
#    「(可选)`case_family` 含标记,或标题/类型保留 `[…]` 字样」—— 即 `case_family` / `tags`
#    是**上游合法的标记承载位**。实测:把 `[还原度]` 放进 `case_family` 或 `tags`、
#    `mechanism` 填 `webmcp`,C14 一条都不报(**假绿**,正是本条注释上一段要防的那个方向)。
#    ⛔ 改这里时不要再收窄成「只认标题」。
FIDELITY_SIGNAL_FIELDS = ('type', 'test_name', 'case_id', 'suite', 'case_family', 'tags')
TIMING_FIELDS = ('started_at', 'finished_at', 'elapsed_ms')
# 上游约定的巡检项 case_id 形态(`运行时-<页面>`),用于反查漏标 entry_kind
FREE_SCAN_ID_PREFIX = '运行时-'
# 非用例产物(与 gen_report.NON_RESULT_FILES 同口径),整目录校验时跳过
NON_RESULT_FILES = {'env-facts.json', 'token-usage.json', 'run-context.json'}


def _issue(issues, level, rule, msg):
    issues.append({'level': level, 'rule': rule, 'msg': msg})


def _iso_span_ms(start, end):
    """两个 ISO-8601 时间串相差多少毫秒;任一不可解析返回 None。

    ⚠️ 只用标准库 `datetime.fromisoformat`。Python 3.8~3.10 不认结尾的 `Z`,
       先换成 `+00:00`(下游 run 的 Python 版本不受本 SKILL 控制,这一行不能省)。
    """
    from datetime import datetime
    def _p(v):
        if not isinstance(v, str) or not v.strip():
            return None
        t = v.strip().replace('Z', '+00:00')
        try:
            return datetime.fromisoformat(t)
        except ValueError:
            return None
    a, b = _p(start), _p(end)
    if a is None or b is None:
        return None
    if (a.tzinfo is None) != (b.tzinfo is None):
        return None      # 一个带时区一个不带,相减会 TypeError;判不了就返回 None
    return (b - a).total_seconds() * 1000.0


def has_lightweight_evidence(value):
    """direct pass 的轻量事实门:有摘要/产物路径即可,不要求截图类型。

    ⚠️ 与 gen_report.has_lightweight_evidence 逻辑必须保持一致(落盘校验 vs 聚合复用同一判据),
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


def check_one(data, name):
    """校验单条结果对象,返回 issues 列表。"""
    issues = []
    if not isinstance(data, dict):
        _issue(issues, 'Critical', 'not_object', f'{name}: 顶层不是 JSON 对象')
        return issues

    if not data.get('case_id'):
        _issue(issues, 'Critical', 'missing_case_id', f'{name}: 缺 case_id')
    status = data.get('status')
    if status not in STATUS_ENUM:
        _issue(issues, 'Critical', 'bad_status',
               f'{name}: status={status!r} 非法(应为 pass|fail|block|na)')

    # 条目类型:巡检项必须显式标注,否则会被当成用例计进通过率
    ek = data.get('entry_kind')
    if ek is not None and ek not in ENTRY_KIND_ENUM:
        _issue(issues, 'Critical', 'bad_entry_kind',
               f'{name}: entry_kind={ek!r} 非法(应为 {sorted(ENTRY_KIND_ENUM)},缺省=case)')
    elif str(data.get('case_id') or '').startswith(FREE_SCAN_ID_PREFIX) and ek != 'free-scan':
        _issue(issues, 'Important', 'free_scan_unmarked',
               f'{name}: case_id 形如巡检项(`{FREE_SCAN_ID_PREFIX}…`)却未标 entry_kind="free-scan"'
               f',会被计入用例统计、稀释通过率与「P0 100%」准则')

    if status == 'block':
        br = data.get('block_reason')
        if not br:
            _issue(issues, 'Critical', 'missing_block_reason',
                   f'{name}: status=block 但 block_reason 为空'
                   f'(缺陷分级按枚举判定,缺了会被当成非环境类阻塞误计产品缺陷)')
        elif br not in BLOCK_REASON_ENUM:
            _issue(issues, 'Critical', 'bad_block_reason',
                   f'{name}: block_reason={br!r} 不在枚举内 {sorted(BLOCK_REASON_ENUM)}')

    # evidence / runtimeErrors 形状
    for field in ('evidence', 'runtimeErrors'):
        val = data.get(field)
        if val is None:
            continue
        if not isinstance(val, list):
            _issue(issues, 'Critical', 'bad_array',
                   f'{name}: `{field}` 不是数组(实为 {type(val).__name__})')
            continue
        for i, item in enumerate(val):
            if isinstance(item, str):
                _issue(issues, 'Important', 'evidence_string_item',
                       f'{name}: `{field}[{i}]` 是字符串而非对象'
                       f'(聚合器会按 artifact 兼容解析,但规范形状是 '
                       f'{{step, summary, artifact}},见 assets/result-schema.json)')
            elif isinstance(item, dict):
                if field == 'evidence' and not item.get('artifact'):
                    _issue(issues, 'Important', 'evidence_missing_artifact',
                           f'{name}: `evidence[{i}]` 缺 artifact(报告证据路径将显示 —)')
                if field == 'runtimeErrors':
                    missing = [k for k in ('type', 'message', 'severity') if not item.get(k)]
                    if missing:
                        _issue(issues, 'Important', 'runtime_error_incomplete',
                               f'{name}: `runtimeErrors[{i}]` 缺 {"/".join(missing)}')
            else:
                _issue(issues, 'Critical', 'bad_array_item',
                       f'{name}: `{field}[{i}]` 形状不合契约({type(item).__name__})')

    # na 是永久不适用,必须有理由;缺省 na=0 由聚合器兼容,不影响旧结果。
    if status == 'na':
        reason = next((data.get(k) for k in NA_REASON_FIELDS
                       if isinstance(data.get(k), str) and data.get(k).strip()), None)
        if not reason:
            _issue(issues, 'Critical', 'na_without_reason',
                   f'{name}: status=na 但 note/na_reason/error 均为空(不适用必须说明理由)')

    # verified / self-heal 的 pass 必须有证据(「没有证据的 pass 等同未验证」)
    mode = str(data.get('execution_mode') or 'direct')
    ev = data.get('evidence')
    if status == 'pass' and mode in EVIDENCE_REQUIRED_MODES and not ev:
        _issue(issues, 'Critical', 'verified_pass_without_evidence',
               f'{name}: execution_mode={mode} 的 pass 无 evidence(= 未验证,质量维度 5)')
    elif status == 'pass' and mode == 'direct' and not has_lightweight_evidence(ev):
        _issue(issues, 'Important', 'direct_pass_without_light_evidence',
               f'{name}: direct 模式的 pass 缺少轻量事实 evidence(需记录实际值/元素文案/列表计数或产物路径;不阻断,报告单列)')

    # ── 执行机制(C14/C15):唯一会「静默变绿」的机制误用 ──
    mech = data.get('mechanism')
    if mech is not None:
        if not isinstance(mech, str) or mech not in MECHANISM_ENUM:
            _issue(issues, 'Critical', 'bad_mechanism',
                   f'{name}: mechanism={mech!r} 不在枚举内({" | ".join(sorted(MECHANISM_ENUM))})')
        elif mech == 'webmcp':
            # ⚠️ 只判 `webmcp`,**不判 `mixed`**:mixed 的正当用法就是「状态准备走 WebMCP、
            #    断言走 DOM」,那正是分层铁律鼓励的形态;把它一起判死会让唯一正确的加速姿势用不了。
            # `tags` 常是数组;str(list) 也能命中,但显式摊平可读性更好、也不依赖 repr 形态。
            parts = []
            for k in FIDELITY_SIGNAL_FIELDS:
                v = data.get(k)
                if isinstance(v, (list, tuple)):
                    parts.extend(str(x) for x in v)
                elif v is not None:
                    parts.append(str(v))
            blob = ' '.join(parts)
            hit = [m for m in FIDELITY_MARKERS if m in blob]
            if hit:
                _issue(issues, 'Critical', 'fidelity_via_webmcp',
                       f'{name}: 视觉还原度类用例(命中「{"/".join(hit)}」)把 mechanism 标成 webmcp —— '
                       f'WebMCP 读的是页面**声明的能力**、不是**渲染结果**,用它验还原度会让渲染层缺陷'
                       f'100% 漏测**且全绿**。断言必须走 DOM + 截图;若只是状态准备用了 WebMCP,请填 mixed')

    # ── 单条耗时(I8~I10):没有它,任何优化都无法验证是否生效 ──
    present = [f for f in TIMING_FIELDS if data.get(f) not in (None, '')]
    if len(present) < len(TIMING_FIELDS):
        miss = [f for f in TIMING_FIELDS if f not in present]
        _issue(issues, 'Important', 'missing_timing',
               f'{name}: 缺单条耗时字段 {"/".join(miss)} —— 没有它「哪条慢、慢在哪」只能靠 '
               f'evidence 文件 mtime 反推,而那只对产出了多个 evidence 的用例有效')
    else:
        el = data.get('elapsed_ms')
        if not isinstance(el, (int, float)) or isinstance(el, bool) or el < 0:
            _issue(issues, 'Important', 'bad_elapsed_ms',
                   f'{name}: elapsed_ms={el!r} 不是非负数值')
        else:
            span = _iso_span_ms(data.get('started_at'), data.get('finished_at'))
            if span is not None and abs(span - el) > 2000:
                _issue(issues, 'Important', 'timing_inconsistent',
                       f'{name}: elapsed_ms={int(el)} 与 finished_at−started_at={int(span)} 相差 '
                       f'{int(abs(span - el))}ms(>2s)—— 两者不是同一次计时,数据不可信')
            dur = data.get('duration_ms')
            if isinstance(dur, (int, float)) and not isinstance(dur, bool) and abs(dur - el) > 1:
                _issue(issues, 'Important', 'duration_ms_mismatch',
                       f'{name}: 旧字段 duration_ms={dur} 与 elapsed_ms={int(el)} 不等(两者同义)')

    # ── I11 execution_mode 语义提醒:「具备自愈能力」≠「实际自愈了」 ──
    if mode == 'self-heal' and not data.get('retries') and not data.get('self_heal_attempts'):
        _issue(issues, 'Important', 'self_heal_never_triggered',
               f'{name}: execution_mode=self-heal 但 retries=0 且 self_heal_attempts=0 —— '
               f'这**完全正常**(该字段表示「具备」自愈能力、不表示「实际自愈了」);'
               f'报出来是为了让报告里的 execution_mode 分布不被读成「N 条在重跑」')

    # self-heal 追溯
    if data.get('self_heal_applied') and not data.get('self_heal_trace'):
        _issue(issues, 'Critical', 'missing_self_heal_trace',
               f'{name}: self_heal_applied=true 但 self_heal_trace 为空'
               f'(须含 cause / recovery / outcome 三要素)')

    # 双源对账
    dba = data.get('db_assertion')
    if dba is not None:
        if not isinstance(dba, dict):
            _issue(issues, 'Critical', 'bad_db_assertion',
                   f'{name}: db_assertion 不是对象')
        else:
            missing = [k for k in ('pageValue', 'sqlValue', 'match') if k not in dba]
            if missing:
                _issue(issues, 'Critical', 'db_assertion_incomplete',
                       f'{name}: db_assertion 缺 {"/".join(missing)}')
            elif dba.get('match') is False and status != 'fail':
                _issue(issues, 'Critical', 'db_mismatch_not_fail',
                       f'{name}: db_assertion.match=false 但 status={status}'
                       f'(双源对账不一致必须判 fail)')

    # 前置数据面探测(ED-NNN,浏览器前批量只读探测)
    pp = data.get('precondition_probe')
    if pp is not None:
        if not isinstance(pp, dict):
            _issue(issues, 'Critical', 'bad_precondition_probe',
                   f'{name}: precondition_probe 不是对象')
        else:
            missing = [k for k in ('id', 'status', 'detail', 'evidence') if k not in pp]
            if missing:
                _issue(issues, 'Critical', 'precondition_probe_incomplete',
                       f'{name}: precondition_probe 缺 {"/".join(missing)}')
            pp_status = pp.get('status')
            if pp_status not in PRECONDITION_STATUS_ENUM:
                _issue(issues, 'Critical', 'bad_precondition_status',
                       f'{name}: precondition_probe.status={pp_status!r} 不在枚举内 '
                       f'{sorted(PRECONDITION_STATUS_ENUM)}')
            elif pp_status == 'unmet' and (status != 'block'
                                            or data.get('block_reason') != 'precondition-unmet'):
                _issue(issues, 'Critical', 'precondition_unmet_not_blocked',
                       f'{name}: precondition_probe.status=unmet 但 status={status!r}/'
                       f'block_reason={data.get("block_reason")!r}'
                       f'(前置不满足必须 status=block 且 block_reason=precondition-unmet)')
            elif pp_status == 'probe-error' and data.get('block_reason') == 'precondition-unmet':
                _issue(issues, 'Critical', 'probe_error_disguised_as_unmet',
                       f'{name}: precondition_probe.status=probe-error 但 block_reason='
                       f'precondition-unmet(探测调用本身失败,须归因为 network-error/'
                       f'env-unavailable 等环境类,不得伪装成「数据缺位」)')

    # ⚠️ null 是合法的「未显式标注」态(schema 示例里就写作 null),不能连 None 一起判错——
    #    否则本 skill 自带的 assets/result-schema.json 会被自家硬门判 Important。
    if data.get('is_environment_issue') is not None and not isinstance(data['is_environment_issue'], bool):
        _issue(issues, 'Important', 'bad_env_flag',
               f'{name}: is_environment_issue 应为布尔(实为 {type(data["is_environment_issue"]).__name__})')

    return issues


def collect_files(target):
    p = Path(target)
    if p.is_file():
        return [p]
    if p.is_dir():
        return [f for f in sorted(p.glob('*.json')) if f.name not in NON_RESULT_FILES]
    return []


def collect_all(targets):
    """多路径收集 + 保序去重,并回报「一个文件都没收到」的 target。

    ⚠️ **空 target 必须单独回报**:`nargs='+'` 下只要有一个 target 收到了文件,
    整体就不会 `return 2`,于是文档主推的 `build-3/round-*/results/` 用法里
    **glob 少匹配一轮、或路径写错**,结果是「少校验一整轮却显示通过」—— 假绿灯。

    去重按 `Path.resolve()`:同一文件用相对路径与绝对路径分别传入时,
    `dict.fromkeys(Path)` 认为是两个不同的 key、会把同一批问题重复计数两次。
    """
    files, empty = [], []
    seen = set()
    for t in targets:
        got = collect_files(t)
        if not got:
            empty.append(t)
        for f in got:
            try:
                key = f.resolve()
            except OSError:          # 断链软链等极端情况:退回原路径,不因去重把整轮校验搞崩
                key = f
            if key not in seen:
                seen.add(key)
                files.append(f)
    return files, empty


def label_for(f, dup_names):
    """展示名:同名文件跨轮次并存时(round-1/results/TC-001.json vs round-2/…)
    只显示 f.name 会让两轮的问题混作一谈,故对重名项补出后三段路径。"""
    if f.name not in dup_names:
        return f.name
    return '/'.join(f.parts[-3:]) if len(f.parts) >= 3 else str(f)


def main():
    ap = argparse.ArgumentParser(
        description='用例结果 JSON 落盘前校验:形状(evidence/runtimeErrors 必须是对象数组)、'
                    'block_reason 枚举、verified pass 证据、self-heal 追溯、双源对账结构。',
        epilog='示例:\n'
               '  python3 check_result.py round-1/results/TC-001.json\n'
               '  python3 check_result.py round-1/results/ --json\n'
               '  python3 check_result.py round-1/results/ --strict   # Important 也计入失败\n'
               '  python3 check_result.py build-3/round-*/results/    # 跨轮次(shell glob 展开成多路径)',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('target', nargs='+',
                    help='结果 JSON 文件或 results/ 目录(**可多个**;支持 shell glob 展开的跨轮次路径,\n'
                         '如 build-3/round-*/results/)')
    ap.add_argument('--json', action='store_true', help='JSON 输出(供 Agent 解析)')
    ap.add_argument('--strict', action='store_true', help='Important 也计入失败')
    args = ap.parse_args()

    files, empty_targets = collect_all(args.target)
    if not files:
        msg = f'未找到结果 JSON:{" ".join(args.target)}'
        print(json.dumps({'error': msg}, ensure_ascii=False) if args.json else msg)
        return 2

    dup_names = {n for n, c in Counter(f.name for f in files).items() if c > 1}
    all_issues = []
    # 部分 target 收不到文件 → 出声,别让「少校验一整轮」冒充通过
    for t in empty_targets:
        _issue(all_issues, 'Important', 'empty_target',
               f'{t}: 未匹配到任何结果 JSON(路径写错 / glob 少匹配一轮?'
               f'其余 target 仍已校验,但本轮覆盖面比预期少)')
    for f in files:
        name = label_for(f, dup_names)
        try:
            data = json.loads(f.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError) as e:
            _issue(all_issues, 'Critical', 'unreadable', f'{name}: 无法解析 JSON({e})')
            continue
        all_issues.extend(check_one(data, name))

    crit = [i for i in all_issues if i['level'] == 'Critical']
    imp = [i for i in all_issues if i['level'] == 'Important']
    passed = not crit and (not imp if args.strict else True)

    if args.json:
        print(json.dumps({'files': len(files), 'passed': passed,
                          'critical': len(crit), 'important': len(imp),
                          'issues': all_issues}, ensure_ascii=False, indent=2))
    else:
        print(f'校验 {len(files)} 份结果 JSON:Critical {len(crit)} / Important {len(imp)}')
        for i in all_issues:
            print(f"  [{i['level']}] {i['rule']}: {i['msg']}")
        if passed:
            print('✅ 通过')
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
