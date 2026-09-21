#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""两层解耦检查(质量维度 1):方法论层不得泄漏端专有 API。

方法论层文档(SKILL.md 执行流程/模式/闭环/失败/断点/报告 段 + execution-methodology.md
+ report-format.md + usecase-format.md + assets/ 下全部端无关产物,均端无关)只应引用四原子能力
(locate/act/observe/capture)与抽象的「DB 断言驱动 / 数据真值对账」,不得直接出现端专有 API——
含 UI 自动化 API(browser_click / driver.find_element / getByText…)、MCP 工具名
(mcp__<服务>__<工具>,服务/工具名常带连字符)、以及裸 SQL(SELECT/INSERT/UPDATE/DELETE)。
这些端专有 API 只允许出现在驱动适配层文件(references/driver-*.md,含 driver-db-assertion.md),
那里是刻意的映射示例。

用法:python check_layer_isolation.py <SKILL_DIR>
仅标准库,支持 --json。退出码:0 = 无泄漏, 1 = 方法论层泄漏端专有 API, 2 = 输入错误。
"""
import argparse
import json
import re
import sys
from pathlib import Path

# 端专有 API 特征(出现在方法论层即泄漏)。用词边界避免误伤中文说明。
LEAK_PATTERNS = [
    r'browser_click', r'browser_type', r'browser_snapshot', r'browser_navigate',
    r'browser_fill_form',
    # MCP 工具名(mcp__<服务>__<工具>)。★只认前缀 `mcp__` 即判泄漏:服务名/工具名常含连字符,
    #   且文档里常写成占位形式(如 `mcp__..._chrome-devtools__*` / `mcp__<服务>__*`),
    #   带字符类的旧写法(mcp__[\w-]+__)会被这类占位省略号绕过而漏判。方法论层写抽象能力即可,
    #   任何形态的 MCP 工具名都不该出现,故用最宽的前缀匹配。
    r'mcp__',
    r'\bpage\.\$\$?', r'page\.tap\b', r'page\.wxml\b',
    # ⚠️ 小程序端探针曾只有上面三条,而 driver-miniprogram.md 实际用的
    #    miniProgram.callWxMethod / pageStack / screenshot 与 page.data 一条都不在面上——
    #    写进方法论层完全不被拦(实测注入 exit 0)。全仓预扫:两条新探针仅命中
    #    references/driver-miniprogram.md(适配层豁免面),0 假红。
    r'\bminiProgram\.\w+', r'\bpage\.data\b',
    r'driver\.find_element', r'find_element\b', r'get_screenshot_as_file',
    r'By\.(id|xpath|name|accessibility_id)', r'send_keys\b',
    r'setInputFiles\b', r'getByRole\b', r'getByText\b', r'\.locator\(',
    # chrome-devtools 家族「裸名」工具(不带 browser_ 前缀),端专有,仅允许出现在
    # driver-adapters.md(适配层)。方法论层写这些=泄漏。constraint 明确点名 list_pages。
    # chrome-devtools 家族裸名工具(snake_case,不与英文散文冲突)。逐个列举而非泛匹配,
    # 因为 click/fill/hover/drag/emulate 这些是普通英文词,泛匹配会误伤中文文档里的说明。
    r'\blist_pages\b', r'\btake_snapshot\b', r'\btake_screenshot\b',
    r'\bnavigate_page\b', r'\bnew_page\b', r'\bselect_page\b', r'\bclose_page\b',
    r'\bevaluate_script\b', r'\bresize_page\b',
    r'\blist_console_messages\b', r'\blist_network_requests\b',
    r'\bget_console_message\b', r'\bget_network_request\b',
    r'\bwait_for\b', r'\bpress_key\b', r'\bfill_form\b', r'\bhandle_dialog\b',
    r'\bupload_file\b', r'\btype_text\b', r'\btake_heapsnapshot\b',
    r'\bperformance_start_trace\b', r'\bperformance_stop_trace\b',
    # 驱动 CLI 子命令(方法论层写具体命令即泄漏;适配层写才对)
    r'chrome-devtools\s+(status|start|stop)\b',
    # ★运行环境取证的泄漏面:取证信号本身是 Web 专有 JS API。方法论层只写抽象的
    #   「运行环境通道 / 渲染标识 / 自动化标识 / 视口尺寸」,具体读哪个属性属适配层。
    #   这是「运行环境取证」原子步骤最可能被写穿两层的地方,故整族匹配而非白名单几个属性
    #   ——白名单法上一版只列了 4 个属性,`screen.width` / `navigator.platform` /
    #   `window.devicePixelRatio` 这些同源写法全部漏网。
    r'\bnavigator\.\w+', r'\bscreen\.(width|height|avail\w+)\b',
    r'\bwindow\.(outerWidth|outerHeight|innerWidth|innerHeight|devicePixelRatio|screen)\b',
    r'\bpage\.(goto|click|fill|evaluate|waitForSelector|screenshot)\b',
    r'\bbrowser\.newPage\b',
    # ★WebMCP(Web 适配器的可选补充能力 `invoke`)的泄漏面:能力入口 API 名与浏览器启动开关
    #   都是 Web 专有,只允许出现在 references/driver-web-webmcp.md。方法论层只写抽象的
    #   「invoke 能力 / 工具清单 / 工具调用」。⚠️ **刻意不收 `--user-data-dir`**:它在
    #   execution-methodology.md 的「并行会话隔离」里早有正当用法,加进来是纯假红——
    #   给硬门加判据前先全仓跑一遍看假红率,这条是实测结论不是保守。
    r'\b(?:un)?registerTool\b', r'\bgetTools\b', r'\bexecuteTool\b', r'\bontoolchange\b',
    r'\bisSecureContext\b', r'unsafely-treat-insecure-origin-as-secure',
    # 补齐第二个启动开关与相关端专有名(初版只收了第一个开关,判据不对称;全仓预扫命中 0,无假红)
    r'--enable-experimental-web-platform-features', r'--enable-features=WebMCP',
    r'chrome://flags', r'\bRegisteredTool\b',
    r'\blist_webmcp_tools\b', r'\bexecute_webmcp_tool\b', r'--categoryExperimentalWebmcp',
    # ★SQL DML(DB 断言驱动 / 前置数据编排的等价 SQL 属端专有,只允许出现在
    #   driver-db-assertion.md 适配层)。方法论层只写抽象「DB 断言驱动 / 数据真值对账」,禁写裸 SQL。
    #   仅大写关键字(SQL 惯例),不误伤中文散文里的 update_by / 「对账 SQL」等词。
    r'\bSELECT\b', r'\bINSERT\s+INTO\b', r'\bUPDATE\b\s+\w', r'\bDELETE\s+FROM\b',
]

# 方法论层文件(相对 SKILL_DIR)。豁免:references/driver-*.md(适配层,刻意列端专有 API 映射);
# quality-review-checklist.md(检查清单,须举例点名被禁 API 来定义规则)。
# usecase-format.md 属端无关解析逻辑(方法论侧),一并扫描,防止解析契约里混入端专有 API。
# ⚠️ **不要写死这三个文件名**——「写死名单 = 新增一份产物自动逃检」这条教训下面 assets/ 的注释
#    已经写了，但 references/ 侧当时没跟着改。实测：新建 `references/flow-new-methodology.md`
#    并写入 `browser_click`，本检查照样 exit 0 —— 方法论层零端专有 API 这条 Critical 判据被绕过。
#    改为 glob 动态纳入：references/ 下**除适配层与检查清单外**的 .md 全部进扫描面。
METHODOLOGY_GLOBS_REFS = ['references/*.md']
# 适配层（端专有 API 的唯一合法落点）与须点名被禁 API 的检查清单，从方法论层扫描面排除
ADAPTER_PREFIXES = ('driver-',)
DOC_EXEMPT = {'quality-review-checklist.md'}
# ★assets/ 同属端无关方法论层产物(结果 schema / 报告骨架 / 进度状态机 / run-context),
#   与 report-format.md 是同一份契约的两种载体。此前整个 assets/ 不在扫描面内,导致
#   result-schema.json 的 driver 字段说明里留着真实 MCP 工具名,而同一段内容在
#   report-format.md 里已按"具体工具名见 driver-web.md"改写——同源契约两处不一致且检查器看不见。
#   用 **glob 动态纳入**而非逐个列文件名:写死名单等于「新增一份 assets 产物 = 自动逃过检查」,
#   而"扫描面漏了一个文件"正是这条检查上一次失守的根因。
#   assets/ 全部内容按定义都是端无关产物;真要放端专有示例,请放 references/driver-*.md。
#   ⚠️ 必须**递归**(`assets/**/*`):非递归的 `assets/*` 会让任何放进子目录的产物自动逃检,
#   这与本段注释声称要防的「新增一份 assets 产物 = 自动逃过检查」是同一个失守面。
METHODOLOGY_GLOBS = ['assets/**/*']
# SKILL.md 里只扫「执行流程/闭环/模式/失败/断点/报告」正文;豁免「驱动适配层」相关章节
# 与「约束」章节(后者须点名被禁 API 来定义两层分离规则,非执行逻辑)。
# ★用 in-heading 子串匹配的适配层特征词(不含「约束」,避免误伤 L40「…最高约束」这类含「约束」的
#   方法论段而漏扫)。「约束」章节改由 CONSTRAINT_HEADING_RE 精确匹配 `## 约束` 独立标题。
ADAPTER_HEADINGS = ('驱动适配层', '四原子能力抽象', '适配器矩阵')
# 精确匹配「约束」总结章标题(允许 # 数量与前后空白,但标题正文须恰为「约束」),
# 不误伤「无人值守流畅性硬要求(Critical,最高约束)」等含「约束」二字的方法论段标题。
CONSTRAINT_HEADING_RE = re.compile(r'^#{1,6}\s*约束\s*$')

LEAK_RE = re.compile('|'.join(LEAK_PATTERNS))


def scan_text(text, source):
    hits = []
    for i, line in enumerate(text.splitlines(), 1):
        m = LEAK_RE.search(line)
        if m:
            hits.append({'file': source, 'line': i, 'match': m.group(0),
                         'text': line.strip()[:100]})
    return hits


def scan_skill_md(path):
    """SKILL.md:跳过驱动适配层相关章节,只扫方法论层正文。

    ★按标题层级判豁免范围:进入适配层章节时记下它的层级,只有遇到**同级或更高级**的标题
    才退出豁免。早期实现见到任何 `#` 开头的行就重算,于是适配层章节内的**子标题**会把状态
    复位,导致适配层子小节里合法的端专有 API 被误判泄漏。
    """
    hits = []
    exempt_level = None            # None = 不在豁免区;否则为进入豁免时的标题层级
    for i, line in enumerate(path.read_text(encoding='utf-8', errors='replace').splitlines(), 1):
        m = re.match(r'^(#{1,6})\s', line)
        if m:
            level = len(m.group(1))
            is_adapter = (any(h in line for h in ADAPTER_HEADINGS)
                          or bool(CONSTRAINT_HEADING_RE.match(line)))
            if is_adapter:
                exempt_level = level
            elif exempt_level is not None and level <= exempt_level:
                exempt_level = None     # 同级/上级标题才结束豁免;子标题不复位
        if exempt_level is not None:
            continue
        m = LEAK_RE.search(line)
        if m:
            hits.append({'file': 'SKILL.md', 'line': i, 'match': m.group(0),
                         'text': line.strip()[:100]})
    return hits


def main():
    ap = argparse.ArgumentParser(
        description='两层解耦检查(质量维度 1):扫方法论层文档(SKILL.md 执行正文 + '
                    'execution-methodology.md + report-format.md + usecase-format.md + '
                    'assets/ 全部产物)是否泄漏'
                    '端专有 API(如 browser_click / driver.find_element)。端专有 API 只允许出现在'
                    'references/driver-*.md(适配层刻意映射示例)。',
        epilog='示例: python3 check_layer_isolation.py <SKILL_DIR> --json',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('skill_dir', help='auto-test-runner skill 根目录(含 SKILL.md)')
    ap.add_argument('--json', action='store_true', help='JSON 输出(供子 Agent 解析)')
    args = ap.parse_args()

    root = Path(args.skill_dir)
    if not (root / 'SKILL.md').is_file():
        msg = f'非 skill 目录(缺 SKILL.md):{root}'
        print(json.dumps({'error': msg}, ensure_ascii=False) if args.json else msg)
        return 2

    hits = scan_skill_md(root / 'SKILL.md')
    targets = []
    # references/ 动态纳入：排除适配层 driver-*.md 与须点名被禁 API 的检查清单
    for pattern in METHODOLOGY_GLOBS_REFS:
        for f in sorted(root.glob(pattern)):
            if not f.is_file():
                continue
            if f.name.startswith(ADAPTER_PREFIXES) or f.name in DOC_EXEMPT:
                continue
            targets.append(f)
    for pattern in METHODOLOGY_GLOBS:
        targets += sorted(p for p in root.glob(pattern) if p.is_file())
    seen = set()
    for p in targets:
        if not p.is_file() or p in seen:
            continue
        seen.add(p)
        rel = p.relative_to(root).as_posix()
        hits += scan_text(p.read_text(encoding='utf-8', errors='replace'), rel)

    passed = not hits
    if args.json:
        print(json.dumps({'passed': passed, 'leaks': hits}, ensure_ascii=False, indent=2))
    else:
        if passed:
            print('✅ 方法论层无端专有 API 泄漏')
        else:
            print(f'❌ 方法论层泄漏端专有 API {len(hits)} 处:')
            for h in hits:
                print(f"   {h['file']}:{h['line']}  [{h['match']}]  {h['text']}")
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
