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
import os
import re
import struct
import sys
import zlib
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
MECHANISM_ENUM = {'dom', 'webmcp', 'app-mcp', 'mixed'}
# ★「客户端 MCP 能力」是**跨端**功能点(Web / 小程序 / 移动 / 桌面),WebMCP 只是它的 **Web 端实现**。
#   `app-mcp` = 被测应用自己向 AI 暴露业务工具;`webmcp` 保留为 Web 端的历史写法(等价于
#   client_type=web + implementation_kind=webmcp)。
# ⛔⛔ 两条轴绝不可混:**测试驱动**(chrome-devtools / Appium / 小程序驱动去操控客户端)用的也是
#   MCP 协议,但那是「AI 操控客户端」,不是「应用提供了 MCP 能力」。把 driver 可用当成应用能力的证据
#   是本检查要拦的头号形态 —— 判定唯一实现见命令端 `AIDP_HOME/scripts/check_client_mcp.py`。
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


# ── 应用 MCP 能力（跨端）──────────────────────────────────────────────────────
# ★「客户端 MCP 能力」是**跨端**功能点(Web / 小程序 / 移动 / 桌面),WebMCP 只是 Web 端实现。
# ⛔⛔ 与**测试驱动**严格分轴：chrome-devtools / Appium / 小程序驱动用的也是 MCP 协议，
#     但那是「AI 操控客户端」，不是「应用提供了业务工具」。把驱动可用当成应用能力的证据，
#     整个功能点就是假绿 —— 这簇检查的头号防守对象。
# ⛔ 后一态不得由前一态推断：声明了≠有入口，有入口≠注册了，注册了≠真调用过。

def _valid_tool_calls(calls, registered, evidence, require_fact=False):
    """筛出「确有其事」的工具调用记录。

    判据三合一:工具必须在**当前实例注册清单**里、调用须指向一条真实的
    `evidence[].artifact`、且该证据条目的 summary 里点到了这个工具名 ——
    三者缺一,「调用过」就只是一句自称。
    ⚠️ 本函数是该口径的**单一信源**。此前新旧两条通道各写了一份几乎相同的推导式,
       而同一份代码的多份拷贝正是本仓库登记的最高频漂移源(标记识别那三份就已经漂过)。
    `require_fact`:新通道额外要求调用记录自带 source + observed_at(四态各自取证)。
    """
    result = []
    for call in calls:
        if not isinstance(call, dict):
            continue
        tool = call.get('tool_name')
        artifact = call.get('evidence_artifact')
        if not isinstance(tool, str) or tool not in registered:
            continue
        if require_fact and not _mcp_fact(call):
            continue
        if not isinstance(artifact, str):
            continue
        if any(isinstance(item, dict) and item.get('artifact') == artifact
               and tool in str(item.get('summary') or '') for item in evidence):
            result.append(call)
    return result


def _signal_label(data):
    """把用例上一切可能承载族标记的字段拼成一条检索串。

    ⚠️ **必须用 FIDELITY_SIGNAL_FIELDS 全集,⛔ 不要只取 test_name + tags**:
       标记透传到哪个字段各端不一致,只认一个字段会在别的端静默失配 ——
       而失配方向正是假绿(标了 `[WebMCP]` 却一条判据都不报)。实测 `case_family`
       与 `type` 两种落点曾整条零告警。本函数是该口径的**单一信源**,
       ⛔ 别在调用点再各自拼一份。
    """
    labels = []
    for field in FIDELITY_SIGNAL_FIELDS:
        value = data.get(field)
        if isinstance(value, (list, tuple)):
            labels.extend(str(item) for item in value)
        elif value is not None:
            labels.append(str(value))
    return ' '.join(labels)
TIMING_FIELDS = ('started_at', 'finished_at', 'elapsed_ms')
# 上游约定的巡检项 case_id 形态(`运行时-<页面>`),用于反查漏标 entry_kind
FREE_SCAN_ID_PREFIX = '运行时-'
# 非用例产物(与 gen_report.NON_RESULT_FILES 同口径),整目录校验时跳过
NON_RESULT_FILES = {'env-facts.json', 'token-usage.json', 'run-context.json'}
SCREENSHOT_EXTENSIONS = {'.webp', '.png', '.jpg', '.jpeg'}
# 仅拦「明确是图片、但不在截图兼容白名单」的扩展名。`.json`/`.log`/`.txt` 等是合法的
# 非截图证据,不能因为 artifact 字段同时承载它们就一刀切成四种图片后缀。
UNSUPPORTED_IMAGE_EXTENSIONS = {
    '.gif', '.bmp', '.tif', '.tiff', '.svg', '.avif', '.heic', '.heif',
    '.jfif', '.ico', '.jxl', '.jp2', '.j2k', '.apng', '.psd', '.raw', '.dng',
    '.qoi', '.exr', '.tga', '.dds', '.ppm', '.pgm', '.pbm', '.pnm', '.hdr',
}
KNOWN_IMAGE_EXTENSIONS = SCREENSHOT_EXTENSIONS | UNSUPPORTED_IMAGE_EXTENSIONS
PATH_EXCEPTIONS = (OSError, RuntimeError, ValueError)


# ⛔ 这些是**测试驱动**的事实，不是应用能力的证据。出现在四态的 source 里即判 Critical。
# ★ 本条是本仓库在上游实现之上**额外加的**：上游只校形状与四态一致性，没有拦
#   「拿驱动可用冒充应用能力」——而那正是本功能点立论的核心形态（见 check_client_mcp.py 开篇）。
#   少了它，一份把 source 写成「appium 已连接」的结果能全绿通过。
DRIVER_SOURCE_MARKERS = ('chrome-devtools', 'appium', 'cdp', 'playwright', 'selenium',
                         'mcp-remote', '小程序驱动', '测试驱动')


def _driver_source_issues(app, name, issues):
    for state in ('declared', 'entry', 'registration', 'invocation'):
        fact = app.get(state)
        if not isinstance(fact, dict):
            continue
        source = str(fact.get('source') or '').lower()
        if any(marker in source for marker in DRIVER_SOURCE_MARKERS):
            _issue(issues, 'Critical', 'application_mcp_driver_as_evidence',
                   f'{name}: application_mcp.{state}.source 指向**测试驱动**'
                   f'({fact.get("source")!r}) —— ⛔ 驱动可用不是「应用提供了 MCP 能力」的证据，'
                   f'两条轴不可混')


def _mcp_fact(value):
    if not isinstance(value, dict) or not all(
            isinstance(value.get(key), str) and value[key].strip()
            for key in ('source', 'observed_at')):
        return False
    if value['source'].strip().startswith('未取到') and (
            value.get('value') is True or
            value.get('status') in ('connected', 'registered', 'called')):
        return False
    return True


def _check_application_mcp(data, name, issues):
    """只核实应用业务工具的四态证据；测试驱动不参与能力判定。"""
    status = data.get('status')
    mechanism = data.get('mechanism')
    client = data.get('client')
    label = _signal_label(data)
    app = data.get('application_mcp')
    legacy = data.get('webmcp')
    negative = any(word in label for word in ('未启用', '关闭态', '禁用态'))
    marked = '[应用MCP]' in label and not negative
    web_marked = app is not None and client == 'web' and '[WebMCP]' in label and not negative
    legacy_required = app is not None and data.get('webmcp_required') is True
    requires_registration = data.get('mcp_required') is True or legacy_required or marked or web_marked
    requires_call = (data.get('mcp_required') is True or legacy_required
                     or ((marked or web_marked) and '工具调用' in label))
    if app is None:
        if status == 'block' and requires_registration and legacy is None:
            _issue(issues, 'Critical', 'application_mcp_fact_incomplete',
                   f'{name}: 专项用例 block 也须分别记录声明/入口/注册/调用未取到的来源')
        if status == 'pass' and requires_registration:
            _issue(issues, 'Critical', 'application_mcp_required_without_entry',
                   f'{name}: 应用 MCP 专项用例缺应用能力入口事实,不得以 UI 驱动结果充 pass')
        if status == 'pass' and mechanism == 'app-mcp':
            _issue(issues, 'Critical', 'application_mcp_claim_without_call',
                   f'{name}: driver 可用不等于应用实际调用了业务工具')
        return
    if not isinstance(app, dict):
        _issue(issues, 'Critical', 'application_mcp_fact_incomplete',
               f'{name}: application_mcp 须为逐态对象')
        return

    declared = app.get('declared')
    if not _mcp_fact(declared) or not isinstance(declared.get('value'), bool):
        _issue(issues, 'Critical', 'application_mcp_fact_incomplete',
               f'{name}: 应用能力声明缺布尔值/来源/观测时间')
        return
    _driver_source_issues(app, name, issues)
    if app.get('client_type') != client:
        _issue(issues, 'Critical', 'application_mcp_declaration_conflict',
               f'{name}: 声明客户端与结果 client 不一致')
    if legacy is not None:
        if (client != 'web' or not isinstance(legacy, dict)
                or legacy.get('declared_enabled') != declared['value']):
            _issue(issues, 'Critical', 'application_mcp_declaration_conflict',
                   f'{name}: 新旧应用 MCP 声明冲突,不得静默覆盖')
    if not declared['value']:
        if any(isinstance(app.get(key), dict) and app[key].get('status') == state
               for key, state in (('entry', 'connected'), ('registration', 'registered'),
                                  ('invocation', 'called'))):
            _issue(issues, 'Critical', 'application_mcp_declaration_conflict',
                   f'{name}: 项目声明未提供应用 MCP,结果却称入口/注册/调用已发生')
        if status == 'pass' and (requires_registration or mechanism in ('app-mcp', 'mixed')):
            _issue(issues, 'Critical', 'application_mcp_claim_without_call',
                   f'{name}: 项目声明未提供应用 MCP,不能报业务工具调用通过')
        return

    valid_kind = {'web': ('webmcp',), 'miniprogram': ('app-service', 'bridge'),
                  'mobile': ('app-service', 'bridge'), 'desktop': ('app-service', 'bridge')}
    implementation_evidence = app.get('implementation_evidence')
    evidence_present = (isinstance(implementation_evidence, str)
                        and bool(implementation_evidence.strip()))
    unresolved = evidence_present and implementation_evidence.strip().startswith('未取到')
    unresolved_block = status == 'block' and unresolved
    if (not evidence_present or (unresolved and status != 'block') or
            (app.get('implementation_kind') not in valid_kind.get(client, ())
             and not unresolved_block)):
        _issue(issues, 'Critical', 'application_mcp_implementation_unverified',
               f'{name}: 未给出该端已证实的应用自有实现形态/证据;'
               '未交付仅可注明未取到并 block 专项用例')

    entry, registry, invocation = (app.get(key) for key in
                                   ('entry', 'registration', 'invocation'))
    if any(not _mcp_fact(fact) for fact in (entry, registry, invocation)):
        _issue(issues, 'Critical', 'application_mcp_fact_incomplete',
               f'{name}: 入口/当前实例注册/本用例调用各须独立来源和观测时间')
        return
    tools = registry.get('tools')
    calls = invocation.get('calls')
    if (entry.get('status') not in ('connected', 'disconnected', 'unavailable')
            or registry.get('status') not in ('registered', 'none', 'unavailable')
            or invocation.get('status') not in ('called', 'not-called', 'unavailable')
            or not isinstance(tools, list) or not all(isinstance(t, str) for t in tools)
            or not isinstance(calls, list)):
        _issue(issues, 'Critical', 'application_mcp_fact_incomplete',
               f'{name}: 四态取值或工具/调用清单形状不合契约')
        return
    if ((registry['status'] == 'registered') != bool(tools)
            or (invocation['status'] == 'called') != bool(calls)
            or (registry['status'] == 'unavailable' and tools)
            or (invocation['status'] == 'unavailable' and calls)):
        _issue(issues, 'Critical', 'application_mcp_fact_incomplete',
               f'{name}: 注册/调用状态与实际工具清单或调用记录矛盾')
    # ★ Web 页面注册特有的作用域事实。⚠️ 这条**必须在新通道里也有**:旧 `webmcp` 字段
    #   靠 `scope` 守「浏览器全量工具清单不能冒充本页注册」,而结果一旦只写
    #   `application_mcp`,旧通道整段被短路,该判据会**整条消失**——方向是假绿,
    #   且消失的正是整份跨端契约最核心的那一条。
    # ⛔ 只对 client_type=web + implementation_kind=webmcp 生效:scope 是页面注册的概念,
    #   向 App/小程序/桌面强加它就是「照搬 Web 前提」,那是本轮明令禁止的。
    if app.get('client_type') == 'web' and app.get('implementation_kind') == 'webmcp':
        scope = registry.get('scope')
        if scope not in ('page', 'browser'):
            _issue(issues, 'Critical', 'application_mcp_fact_incomplete',
                   f'{name}: Web+WebMCP 的当前实例注册须写 scope(page|browser)')
        elif scope != 'page' and (mechanism in ('webmcp', 'app-mcp', 'mixed')
                                  or registry['status'] == 'registered'):
            _issue(issues, 'Critical', 'application_mcp_scope_not_page',
                   f'{name}: 浏览器全量工具清单不能证明本页实际注册')
    if legacy is not None and isinstance(legacy, dict) and client == 'web':
        old_calls = legacy.get('invocations')
        new_keys = [(call.get('tool_name'), call.get('evidence_artifact'))
                    for call in calls if isinstance(call, dict)]
        old_keys = ([(call.get('tool_name'), call.get('evidence_artifact'))
                     for call in old_calls if isinstance(call, dict)]
                    if isinstance(old_calls, list) else None)
        if (app.get('implementation_kind') != 'webmcp'
                or legacy.get('entry_detected') != (entry['status'] == 'connected')
                or legacy.get('scope') != 'page'
                or legacy.get('registered_tools') != tools
                or old_keys != new_keys):
            _issue(issues, 'Critical', 'application_mcp_declaration_conflict',
                   f'{name}: 新旧 Web 形态/入口/本页注册/调用证据冲突')
    if (status == 'pass' and (requires_registration or invocation['status'] == 'called'
                              or mechanism in ('app-mcp', 'webmcp', 'mixed'))
            and entry['status'] != 'connected'):
        _issue(issues, 'Critical', 'application_mcp_required_without_entry',
               f'{name}: 应用 MCP 入口未连接,专项用例须 block')
    if status == 'pass' and requires_registration and (registry['status'] != 'registered' or not tools):
        _issue(issues, 'Critical', 'application_mcp_required_without_registration',
               f'{name}: 当前应用实例未注册工具,专项用例须 block')
    evidence = data.get('evidence')
    evidence = evidence if isinstance(evidence, list) else []
    valid_calls = _valid_tool_calls(calls, tools, evidence, require_fact=True)
    if (status == 'pass' and (mechanism in ('app-mcp', 'webmcp', 'mixed') or requires_call)
            or invocation['status'] == 'called') and not valid_calls:
        _issue(issues, 'Critical', 'application_mcp_claim_without_call',
               f'{name}: 无已注册工具的真实调用 artifact,不得报应用 MCP 调用通过')
    if status == 'pass' and valid_calls and mechanism == 'dom':
        _issue(issues, 'Critical', 'application_mcp_mechanism_mismatch',
               f'{name}: 结果记录了应用业务工具调用却声明纯 UI 驱动机制')


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


# ── 产物契约（证据文件必须真实存在且是合法图片）────────────────────────────────
# ★ 这簇检查防的是**伪造证据**：结果 JSON 里写一个 artifact 路径谁都会写，而
#   「路径指向的文件到底在不在、是不是 0 字节、是不是真图片、有没有跨用例复用同一张」
#   在报告上**完全看不出来** —— 报告照样绿、截图位照样有个链接，点开才是 404。
# ⛔ 同时拦路径逃逸：绝对路径 / `..` 穿越 / 软链指到轮次目录外，都会让「证据」指向
#   本轮根本没产出的东西。

SCREENSHOT_EXTENSIONS = {'.webp', '.png', '.jpg', '.jpeg'}
# 仅拦「明确是图片、但不在截图兼容白名单」的扩展名。`.json`/`.log`/`.txt` 等是合法的
# 非截图证据,不能因为 artifact 字段同时承载它们就一刀切成四种图片后缀。


UNSUPPORTED_IMAGE_EXTENSIONS = {
    '.gif', '.bmp', '.tif', '.tiff', '.svg', '.avif', '.heic', '.heif',
    '.jfif', '.ico', '.jxl', '.jp2', '.j2k', '.apng', '.psd', '.raw', '.dng',
    '.qoi', '.exr', '.tga', '.dds', '.ppm', '.pgm', '.pbm', '.pnm', '.hdr',
}


KNOWN_IMAGE_EXTENSIONS = SCREENSHOT_EXTENSIONS | UNSUPPORTED_IMAGE_EXTENSIONS


PATH_EXCEPTIONS = (OSError, RuntimeError, ValueError)


def _artifact_candidates(artifact, result_path):
    """返回 artifact 的词法候选路径,不在此处触碰文件系统。

    `round-1/evidence/x.webp` 相对 build 根,`evidence/x.webp` 相对 round 根。
    文件存在性、符号链接与目录归属在 `_check_artifact_contract` 内统一判,确保异常能转成
    稳定 JSON finding,而不是从 `Path.resolve/is_file` 泄漏 traceback。
    """
    p = Path(artifact)
    if p.is_absolute():
        return [p]
    if result_path is None:
        return [Path.cwd() / p]
    round_dir = result_path.parent.parent
    # 合法形态只有两种:`evidence/x`(相对 round)与 `round-N/evidence/x`(相对 build)。
    # 不再从 results/round/build 三层猜第一个存在文件,避免 results/evidence 的同名残留抢先命中。
    if p.parts and p.parts[0] == 'evidence':
        return [round_dir / p]
    if len(p.parts) >= 2 and p.parts[0] == round_dir.name and p.parts[1] == 'evidence':
        return [round_dir.parent / p]
    return [round_dir / p]


def _is_file_safely(path):
    try:
        return path.is_file(), None
    except PATH_EXCEPTIONS as exc:
        return False, exc


def _resolve_safely(path):
    try:
        return path.resolve(strict=False), None
    except PATH_EXCEPTIONS as exc:
        return None, exc


def _is_within(path, root):
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _png_expected_bytes(width, height, bit_depth, color_type, interlace):
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color_type)
    valid_depths = {
        0: {1, 2, 4, 8, 16}, 2: {8, 16}, 3: {1, 2, 4, 8},
        4: {8, 16}, 6: {8, 16},
    }
    if channels is None or bit_depth not in valid_depths[color_type] or width <= 0 or height <= 0:
        return None
    def pass_size(x0, y0, dx, dy):
        pw = max(0, (width - x0 + dx - 1) // dx)
        ph = max(0, (height - y0 + dy - 1) // dy)
        return 0 if not pw or not ph else ph * (1 + (pw * channels * bit_depth + 7) // 8)
    if interlace == 0:
        return height * (1 + (width * channels * bit_depth + 7) // 8)
    if interlace == 1:
        return sum(pass_size(*p) for p in (
            (0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4),
            (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2)))
    return None


def _valid_image_signature(path, suffix):
    """标准库容器校验,拦文本、仅剩魔数以及缺关键图像段的截断空壳。"""
    try:
        size = path.stat().st_size
        with path.open('rb') as fh:
            if suffix == '.png':
                if fh.read(8) != b'\x89PNG\r\n\x1a\n':
                    return False, None
                saw_ihdr = saw_idat = saw_iend = False
                inflater = zlib.decompressobj()
                expected_output = None
                decompressed_size = 0
                max_output = 256 * 1024 * 1024  # 防压缩炸弹;远高于常规 4K RGBA 截图
                while fh.tell() < size:
                    raw_len = fh.read(4)
                    chunk_type = fh.read(4)
                    if len(raw_len) != 4 or len(chunk_type) != 4:
                        return False, None
                    length = int.from_bytes(raw_len, 'big')
                    if length > size - fh.tell() - 4:
                        return False, None
                    data = fh.read(length)
                    raw_crc = fh.read(4)
                    if len(data) != length or len(raw_crc) != 4:
                        return False, None
                    expected_crc = zlib.crc32(chunk_type + data) & 0xffffffff
                    if int.from_bytes(raw_crc, 'big') != expected_crc:
                        return False, None
                    if chunk_type == b'IHDR':
                        if saw_ihdr or length != 13:
                            return False, None
                        width = int.from_bytes(data[0:4], 'big')
                        height = int.from_bytes(data[4:8], 'big')
                        expected_output = _png_expected_bytes(
                            width, height, data[8], data[9], data[12])
                        if expected_output is None or expected_output > max_output:
                            return False, None
                        if data[10] != 0 or data[11] != 0:
                            return False, None
                        saw_ihdr = True
                    elif chunk_type == b'IDAT':
                        if not saw_ihdr or expected_output is None:
                            return False, None
                        saw_idat = True
                        remaining = expected_output - decompressed_size + 1
                        if remaining <= 0:
                            return False, None
                        out = inflater.decompress(data, remaining)
                        decompressed_size += len(out)
                        if decompressed_size > expected_output or inflater.unconsumed_tail:
                            return False, None
                    elif chunk_type == b'IEND':
                        if length != 0:
                            return False, None
                        saw_iend = True
                        break
                if not (saw_ihdr and saw_idat and saw_iend and fh.tell() == size
                        and expected_output is not None):
                    return False, None
                try:
                    remaining = expected_output - decompressed_size + 1
                    tail = inflater.flush(max(1, remaining))
                    decompressed_size += len(tail)
                except zlib.error:
                    return False, None
                return inflater.eof and decompressed_size == expected_output, None

            if suffix in {'.jpg', '.jpeg'}:
                if fh.read(2) != b'\xff\xd8':
                    return False, None
                saw_sof = saw_sos = False
                sof_markers = {0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7,
                               0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf}
                while fh.tell() < size:
                    byte = fh.read(1)
                    if byte != b'\xff':
                        continue
                    marker_raw = fh.read(1)
                    while marker_raw == b'\xff':
                        marker_raw = fh.read(1)
                    if not marker_raw:
                        return False, None
                    marker = marker_raw[0]
                    if marker == 0xda:  # SOS:后续是熵编码数据,只需确认容器以 EOI 收尾
                        saw_sos = True
                        break
                    if marker == 0xd9:
                        break
                    if marker in {0x01, *range(0xd0, 0xd8)}:
                        continue
                    raw_len = fh.read(2)
                    if len(raw_len) != 2:
                        return False, None
                    seg_len = int.from_bytes(raw_len, 'big')
                    if seg_len < 2 or fh.tell() + seg_len - 2 > size:
                        return False, None
                    if marker in sof_markers:
                        saw_sof = True
                    fh.seek(seg_len - 2, 1)
                if not (saw_sof and saw_sos and size >= 4):
                    return False, None
                fh.seek(-2, 2)
                return fh.read(2) == b'\xff\xd9', None

            if suffix == '.webp':
                header = fh.read(12)
                if (len(header) != 12 or header[:4] != b'RIFF'
                        or header[8:12] != b'WEBP'
                        or int.from_bytes(header[4:8], 'little') + 8 != size):
                    return False, None
                saw_image_chunk = False
                while fh.tell() < size:
                    fourcc = fh.read(4)
                    raw_len = fh.read(4)
                    if len(fourcc) != 4 or len(raw_len) != 4:
                        return False, None
                    chunk_len = int.from_bytes(raw_len, 'little')
                    padded = chunk_len + (chunk_len & 1)
                    if fh.tell() + padded > size:
                        return False, None
                    # VP8X 只是扩展画布头,本身没有像素;静态图须有 VP8/VP8L,
                    # 动画须有 ANMF 帧。只含 VP8X 的空壳不得算有效截图。
                    if fourcc in {b'VP8 ', b'VP8L', b'ANMF'} and chunk_len > 0:
                        saw_image_chunk = True
                    fh.seek(padded, 1)
                return saw_image_chunk and fh.tell() == size, None
    except (PATH_EXCEPTIONS, zlib.error) as exc:
        return False, exc
    return True, None


def _detect_image_content(path):
    """识别常见图片内容,防止把真实 PNG/GIF 等改成 `.bin` 绕过截图白名单。"""
    try:
        with path.open('rb') as fh:
            prefix = fh.read(32)
    except PATH_EXCEPTIONS as exc:
        return None, exc
    if prefix.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'png', None
    if prefix.startswith(b'\xff\xd8\xff'):
        return 'jpeg', None
    if len(prefix) >= 12 and prefix[:4] == b'RIFF' and prefix[8:12] == b'WEBP':
        return 'webp', None
    signatures = (
        (b'GIF87a', 'gif'), (b'GIF89a', 'gif'), (b'BM', 'bmp'),
        (b'II*\x00', 'tiff'), (b'MM\x00*', 'tiff'), (b'qoif', 'qoi'),
        (b'v/1\x01', 'exr'), (b'DDS ', 'dds'), (b'\x00\x00\x01\x00', 'ico'),
    )
    for magic, kind in signatures:
        if prefix.startswith(magic):
            return kind, None
    # PNM 不是看到 `P1`~`P6` 就算图片;至少要有合法的 magic + 宽高数字头,
    # 否则普通日志 `P1 failure...` 会被误判成截图。
    if re.match(br'^P[1-6][ \t\r\n]+(?:#[^\r\n]*[\r\n][ \t]*)*\d+[ \t\r\n]+\d+[ \t\r\n]', prefix):
        return 'pnm', None
    if len(prefix) >= 12 and prefix[4:8] == b'ftyp':
        brand = prefix[8:12]
        if brand in {b'heic', b'heix', b'hevc', b'hevx', b'mif1', b'msf1'}:
            return 'heic', None
        if brand in {b'avif', b'avis'}:
            return 'avif', None
    return None, None


def _parse_screenshot_stem(stem):
    for style, pattern in (
            ('canonical', r'^(?P<case>.+)-step(?P<step>[^/]+)$'),
            ('legacy-dash', r'^(?P<case>.+)-(?P<step>\d+)$'),
            ('legacy-cn', r'^(?P<case>.+)_步骤(?P<step>[^/]+)$')):
        m = re.fullmatch(pattern, stem)
        if m:
            return m.group('case'), m.group('step'), style
    return None, None, None


def _scan_evidence_directory(evidence_dir):
    """递归建立 `stem -> 目录项[]` 索引,每 round 一次,后续 sibling 查询近似 O(1)。"""
    try:
        entries = list(evidence_dir.rglob('*'))
    except PATH_EXCEPTIONS as exc:
        return {}, exc
    by_stem = {}
    for entry in entries:
        try:
            parent_key = entry.parent.relative_to(evidence_dir).as_posix()
        except ValueError:
            continue
        by_stem.setdefault((parent_key, entry.stem), []).append(entry)
    return by_stem, None


def _check_artifact_contract(data, name, result_path, issues, artifact_index=None,
                             artifact_owners=None):
    """校验 artifact 的本轮归属、格式、唯一性、文件头与实际存在性。"""
    screenshot_stems = {}
    actual_screenshots = []
    if artifact_owners is None:
        artifact_owners = {}
    registered_lexical_paths = set()
    seen_actual_artifacts = set()
    evidence_root = None
    evidence_dir = None
    sibling_entries, sibling_scan_error = (artifact_index if artifact_index is not None else (None, None))
    if result_path is not None:
        round_dir = result_path.parent.parent
        try:
            round_is_symlink = round_dir.is_symlink()
        except PATH_EXCEPTIONS as exc:
            round_is_symlink = False
            _issue(issues, 'Critical', 'artifact_invalid_path',
                   f'{name}: 无法读取当前 round 目录状态({exc})')
        if round_is_symlink:
            _issue(issues, 'Critical', 'artifact_round_symlink',
                   f'{name}: 当前 round 目录是符号链接 `{round_dir}`;'
                   f'不得把旧轮次或外部目录冒充本轮结果与证据根')
        evidence_dir = round_dir / 'evidence'
        try:
            root_is_symlink = evidence_dir.is_symlink()
        except PATH_EXCEPTIONS as exc:
            root_is_symlink = False
            _issue(issues, 'Critical', 'artifact_invalid_path',
                   f'{name}: 无法读取当前 round/evidence 目录状态({exc})')
        if root_is_symlink:
            _issue(issues, 'Critical', 'artifact_evidence_root_symlink',
                   f'{name}: 当前 round/evidence 是符号链接 `{evidence_dir}`;'
                   f'不得把旧轮次或外部目录冒充本轮证据根')
        evidence_root, root_error = _resolve_safely(evidence_dir)
        if root_error is not None:
            _issue(issues, 'Critical', 'artifact_invalid_path',
                   f'{name}: 无法解析当前 round/evidence 目录({root_error})')
        if sibling_entries is None:
            sibling_entries, sibling_scan_error = _scan_evidence_directory(evidence_dir)
    if sibling_entries is None:
        sibling_entries = {}

    for field in ('evidence', 'runtimeErrors'):
        value = data.get(field)
        if not isinstance(value, list):
            continue
        for i, item in enumerate(value):
            # evidence 的历史字符串简写按 artifact 兼容;runtimeErrors 的字符串更可能是错误消息,
            # 只能报形状 Important,不得把 `GET /api 500` 当文件路径升级成 Critical。
            artifact = (item if field == 'evidence' and isinstance(item, str) else
                        item.get('artifact') if isinstance(item, dict) else None)
            if not isinstance(artifact, str) or not artifact.strip():
                continue
            artifact = artifact.strip()
            if '\x00' in artifact:
                _issue(issues, 'Critical', 'artifact_invalid_path',
                       f'{name}: `{field}[{i}].artifact` 含 NUL 字节,无法作为文件路径')
                continue
            try:
                artifact_path = Path(artifact)
            except (TypeError, ValueError) as exc:
                _issue(issues, 'Critical', 'artifact_invalid_path',
                       f'{name}: `{field}[{i}].artifact` 路径非法({exc})')
                continue
            if artifact_path.is_absolute():
                _issue(issues, 'Critical', 'artifact_absolute_path',
                       f'{name}: `{field}[{i}].artifact` 必须是当前轮次相对路径,不得写绝对路径 `{artifact}`')
                continue
            if '..' in artifact_path.parts:
                _issue(issues, 'Critical', 'artifact_parent_traversal',
                       f'{name}: `{field}[{i}].artifact` 含 `..` 路径穿越段 `{artifact}`')
                continue
            if (result_path is not None and len(artifact_path.parts) >= 2
                    and artifact_path.parts[1] == 'evidence'
                    and artifact_path.parts[0].startswith('round-')
                    and artifact_path.parts[0] != result_path.parent.parent.name):
                _issue(issues, 'Critical', 'artifact_outside_round',
                       f'{name}: `{field}[{i}].artifact` 指向旧轮次 `{artifact_path.parts[0]}`;'
                       f'只允许当前 `{result_path.parent.parent.name}` 的 evidence')
                continue

            suffix = artifact_path.suffix.lower()
            unsupported_image_suffix = (suffix in KNOWN_IMAGE_EXTENSIONS
                                        and suffix not in SCREENSHOT_EXTENSIONS)
            if unsupported_image_suffix:
                _issue(issues, 'Critical', 'unsupported_screenshot_extension',
                       f'{name}: `{field}[{i}].artifact` 使用 {suffix} 截图格式;'
                       f'兼容格式仅 {sorted(SCREENSHOT_EXTENSIONS)}')

            candidates = _artifact_candidates(artifact, result_path)
            existing = None
            path_error = None
            for candidate in candidates:
                _, candidate_resolve_error = _resolve_safely(candidate)
                if candidate_resolve_error is not None:
                    path_error = candidate_resolve_error
                    continue
                is_file, error = _is_file_safely(candidate)
                if error is not None:
                    path_error = error
                    continue
                if is_file:
                    existing = candidate
                    break
            if existing is None:
                if path_error is not None:
                    _issue(issues, 'Critical', 'artifact_invalid_path',
                           f'{name}: `{field}[{i}].artifact` 无法稳定解析 `{artifact}`({path_error})')
                else:
                    _issue(issues, 'Critical', 'artifact_not_found',
                           f'{name}: `{field}[{i}].artifact` 指向不存在的文件 `{artifact}`;'
                           f'不得伪造路径或用空文件冒充取证结果')
                continue

            resolved, resolve_error = _resolve_safely(existing)
            if resolve_error is not None:
                _issue(issues, 'Critical', 'artifact_invalid_path',
                       f'{name}: `{field}[{i}].artifact` 无法解析 `{artifact}`({resolve_error})')
                continue
            if evidence_root is not None and not _is_within(resolved, evidence_root):
                _issue(issues, 'Critical', 'artifact_outside_round',
                       f'{name}: `{field}[{i}].artifact` 实际落点 `{resolved}` 不在当前轮次 '
                       f'`{evidence_root}` 内,不得引用旧 round 或外部文件')
                continue

            if resolved in seen_actual_artifacts:
                _issue(issues, 'Important', 'duplicate_artifact_entry',
                       f'{name}: `{field}[{i}].artifact` 重复登记同一个实际文件 `{resolved}`;'
                       f'每个步骤只登记一个 artifact')
            else:
                seen_actual_artifacts.add(resolved)
            registered_lexical_paths.add(existing.absolute())
            if suffix in SCREENSHOT_EXTENSIONS:
                case_id = str(data.get('case_id') or '')
                file_stem = existing.stem
                stem_case, stem_step, stem_style = _parse_screenshot_stem(file_stem)
                if field == 'evidence' and isinstance(item, dict) and item.get('step') is not None:
                    step = str(item.get('step'))
                    expected_stem = f'{case_id}-step{step}'
                    if case_id and stem_case != case_id:
                        _issue(issues, 'Critical', 'artifact_case_mismatch',
                               f'{name}: `evidence[{i}]` 截图主干 `{file_stem}` 的 case 为 '
                               f'`{stem_case or "无法解析"}`(应为 `{case_id}`)')
                    elif stem_step != step:
                        _issue(issues, 'Critical', 'artifact_step_mismatch',
                               f'{name}: `evidence[{i}]` step={step} 但截图主干为 '
                               f'`{file_stem}`(应为 `{expected_stem}`)')
                    elif stem_style in {'legacy-dash', 'legacy-cn'}:
                        _issue(issues, 'Important', 'legacy_artifact_name',
                               f'{name}: `evidence[{i}]` 使用历史截图主干 `{file_stem}`;'
                               f'继续兼容但新产物统一写 `{expected_stem}`')
                elif field == 'runtimeErrors':
                    if stem_style is not None:
                        if case_id and stem_case != case_id:
                            _issue(issues, 'Critical', 'artifact_case_mismatch',
                                   f'{name}: `runtimeErrors[{i}]` 截图主干 `{file_stem}` 的 case 为 '
                                   f'`{stem_case}`(应为 `{case_id}`)')
                    else:
                        labels = {'console', 'network', 'pageError', 'error'}
                        if isinstance(item, dict) and item.get('type'):
                            labels.add(str(item.get('type')))
                        allowed = {f'{case_id}-{label}' for label in labels}
                        if case_id and file_stem not in allowed:
                            _issue(issues, 'Critical', 'artifact_case_mismatch',
                                   f'{name}: `runtimeErrors[{i}]` 截图主干 `{file_stem}` '
                                   f'不属于 case_id `{case_id}`')
                previous_owner = artifact_owners.get(resolved)
                if previous_owner is not None and previous_owner != case_id:
                    _issue(issues, 'Critical', 'artifact_cross_case_reuse',
                           f'{name}: case_id `{case_id}` 与 `{previous_owner}` 复用同一个实际截图 '
                           f'`{resolved}`;每条用例必须有自己的证据')
                else:
                    artifact_owners[resolved] = case_id
                stem = str(resolved.with_suffix(''))
                previous = screenshot_stems.get(stem)
                if previous is not None and previous != suffix:
                    _issue(issues, 'Critical', 'duplicate_screenshot_artifact',
                           f'{name}: evidence/runtimeErrors 同一实际截图主干 `{stem}` 同时登记 '
                           f'{previous} 与 {suffix};每次 capture 只生成并登记一种实际格式')
                else:
                    screenshot_stems[stem] = suffix
                actual_screenshots.append((field, i, existing, resolved, suffix))

            try:
                empty = existing.stat().st_size == 0
            except PATH_EXCEPTIONS as exc:
                _issue(issues, 'Critical', 'artifact_invalid_path',
                       f'{name}: `{field}[{i}].artifact` 无法读取文件状态({exc})')
                continue
            if empty:
                _issue(issues, 'Critical', 'artifact_empty',
                       f'{name}: `{field}[{i}].artifact` 指向 0 字节空文件 `{artifact}`;'
                       f'截图失败残留的空壳不能算有效证据')
                continue
            detected_image, detect_error = _detect_image_content(existing)
            if detect_error is not None:
                _issue(issues, 'Critical', 'artifact_invalid_path',
                       f'{name}: `{field}[{i}].artifact` 无法识别文件类型({detect_error})')
            elif (detected_image is not None and suffix not in SCREENSHOT_EXTENSIONS
                  and not unsupported_image_suffix):
                _issue(issues, 'Critical', 'unsupported_screenshot_extension',
                       f'{name}: `{field}[{i}].artifact` 内容是 {detected_image} 图片,但后缀为 '
                       f'`{suffix or "<无>"}`;截图只允许 {sorted(SCREENSHOT_EXTENSIONS)}')
            if suffix in SCREENSHOT_EXTENSIONS:
                valid_image, image_error = _valid_image_signature(existing, suffix)
                if image_error is not None:
                    _issue(issues, 'Critical', 'artifact_invalid_path',
                           f'{name}: `{field}[{i}].artifact` 无法读取文件头({image_error})')
                elif not valid_image:
                    _issue(issues, 'Critical', 'artifact_invalid_image',
                           f'{name}: `{field}[{i}].artifact` 后缀为 {suffix},但文件头不是该图片格式;'
                           f'非图片文本/空壳不得冒充截图证据')

    # summary/计数证据不需要 evidence 目录;只有确实登记了截图时才把目录扫描失败判 Critical。
    if actual_screenshots and sibling_scan_error is not None:
        _issue(issues, 'Critical', 'artifact_invalid_path',
               f'{name}: 无法扫描当前 round/evidence 目录({sibling_scan_error})')
        return

    # 目录索引按 round 只建一次,键包含相对父目录 + stem:不同端子目录的同名截图不互相误伤。
    for field, i, existing, resolved, suffix in actual_screenshots:
        try:
            parent_key = existing.parent.relative_to(evidence_dir).as_posix()
        except (ValueError, AttributeError):
            parent_key = ''
        for sibling in sibling_entries.get((parent_key, existing.stem), []):
            if sibling.name == existing.name:
                continue
            is_file, file_error = _is_file_safely(sibling)
            if file_error is not None:
                _issue(issues, 'Critical', 'artifact_invalid_path',
                       f'{name}: 同主干候选 `{sibling}` 无法读取({file_error})')
                continue
            if not is_file:
                continue
            sibling_suffix = sibling.suffix.lower()
            if sibling_suffix not in KNOWN_IMAGE_EXTENSIONS:
                detected, detect_error = _detect_image_content(sibling)
                if detect_error is not None:
                    _issue(issues, 'Critical', 'artifact_invalid_path',
                           f'{name}: 同主干候选 `{sibling}` 无法识别({detect_error})')
                    continue
                if detected is None:
                    continue
            # 用词法路径判「有没有第二个目录项」;不能按 resolve 后目标去重,否则 `.png -> .webp`
            # 这种未登记符号链接会因目标相同被误当成已登记。
            if sibling.absolute() in registered_lexical_paths:
                continue
            _issue(issues, 'Critical', 'duplicate_screenshot_file',
                   f'{name}: `{field}[{i}].artifact` 的同目录同主干还残留 `{sibling.name}`;'
                   f'每次 capture 只能保留一种实际截图格式,回退前须清理失败半成品')


def check_one(data, name, result_path=None, artifact_index=None, artifact_owners=None):
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

    _check_application_mcp(data, name, issues)
    # 产物契约只在调用方给出结果文件路径时才可判（要靠它解析相对路径）；
    # ⛔ 取不到就跳过，不臆造 basedir —— 那会把「路径对的」判成 not_found。
    if result_path is not None:
        _check_artifact_contract(data, name, result_path, issues,
                                 artifact_index=artifact_index, artifact_owners=artifact_owners)

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
        all_issues.extend(check_one(data, name, result_path=f))

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
