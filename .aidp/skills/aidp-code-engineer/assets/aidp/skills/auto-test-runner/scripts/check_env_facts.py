#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""运行环境事实取证校验(质量维度 2 / 维度 7 的机检落点)。

校验 `round-{M}/env-facts.json`:每个**环境事实字段**都配套一个 `<字段>Source` 来源标注,
来源取值落在五类枚举内,且「取不到」与「值为 null」严格互为充要条件——即
**取不到就必须写 null + 未取到(原因),不许回落成模板默认或"看起来合理"的推断值**。

为什么需要它:报告「一、测试概况」里的渲染模式 / 浏览器版本 / viewport / 是否复用已有实例 /
被测 URL / 登录角色属于**环境事实类**字段。这些字段若来自意图推断或模板默认,会与实际运行形态
无关(典型:远程无图形界面的环境本就只能无头运行,报告却恒填「有头」)。本脚本把「逐字段确认来源」
做成硬门,并可选地核对报告概况与取证事实不矛盾。

**字段自动纳管**:除元数据白名单(probedAt/round/build/notes)与 `$`/`_` 开头的注释键外,
**任何事实字段都要求配套 `<字段>Source`,任何 `XSource` 也必须有对应的事实字段 `X`**
(双向成对)——将来新增事实字段无需改本脚本即自动受约束,也堵掉「起个 `xxxSource` 名字就
既不校验也不要求来源」这个绕过口。

**`--report` 的检测范围严格限定在「一、测试概况」章节内,且渲染模式只看概况里的「渲染模式」行。**
早期版本扫全文,同时造成假绿灯(概况整行不写渲染模式,却被 `browserVersion` 里的
`HeadlessChrome` 顺带满足 presence 检查)与假红灯(结论章写「建议下轮补一轮有头回归」被判矛盾)。
⚠️ 不要改回全文子串扫描。

用法:
    python3 check_env_facts.py <env-facts.json> [--report 报告.md] [--json] [--strict]

退出码:0 = 通过(无 error;--strict 时还须无 warn) / 1 = 不通过 / 2 = 输入错误(含根节点非对象)。
仅标准库。
"""
import argparse
import json
import re
import sys
from pathlib import Path

# 必备事实字段(报告「一、测试概况」的固定数据源)。
# ⚠️ **判据 = `assets/env-facts-schema.json` 里配了 `XSource` 的字段**，不是一个随手维护的短名单。
#    上一轮把环境事实从 6 项扩到 8 项时只改了文档、没改这里，于是删掉 executionPath /
#    datasourceOwnership 照样 ✅ 通过 exit 0 —— 「共 N 项」的契约无任何机检兜底，
#    与那一轮把两处 warn 升 error 想堵的是同一类洞，只是留在了新字段上。
#    这里刻意**不写「共 N 个」**：写死数字必腐化，schema 增字段时同步本列表即可。
REQUIRED_FACTS = [
    'renderMode', 'browserVersion', 'viewport',
    'reusedInstance', 'testUrl', 'loginRole',
    'driver', 'executionPath', 'datasourceEnvironment', 'datasourceOwnership',
]
# 契约类型(见 references/report-format.md「一·补」):这些必填字段为 string|null,
# `reusedInstance` 单独为 bool|null。数字/数组/对象都不是合法取值——它们既进不了报告表格,
# 也让 --report 对账静默跳过。
STR_FACTS = {'renderMode', 'browserVersion', 'viewport', 'testUrl', 'loginRole',
             'driver', 'executionPath', 'datasourceEnvironment', 'datasourceOwnership'}

# 元数据键:不是「事实」,不要求配套 Source。另:`$`/`_` 开头的键一律视为注释/元数据
# (与 assets/result-schema.json 的 `$comment` 约定一致)。
META_KEYS = {'probedAt', 'round', 'build', 'notes'}


def _is_meta(key):
    return key in META_KEYS or key.startswith(('$', '_'))


# 来源标注五类枚举(**整串形态**匹配,不是宽松前缀匹配)。除「显式指定」外,其余四类必须带括号说明。
# ⚠️ 「运行配置」不是第六类来源——驱动能直接返回运行配置时,它是**最权威的取证方法**,
#    来源仍写 `运行取证(驱动运行配置:…)`。别把方法名当来源类别加进来。
SOURCE_PREFIXES = {
    '显式指定': False,          # 编排层/命令行显式传入(仅当已确认未复用已有实例时才可信)
    '复用已有实例': True,       # 连到已存在的驱动实例 → 传参不生效,须注明来源
    '无头不可用降级': True,     # 显式降级,须注明原因
    '运行取证': True,           # 执行期实测,须注明方法(含"读驱动运行配置")
    '未取到': True,             # 实测取不到,须注明原因 —— 此时值必须为 null
}

# 来源整串形态:`前缀` 或 `前缀(说明)`。宽松的 startswith 会放行
# 「显式指定的推断值,其实没测」这种把枚举词当句首的自由文本。
SOURCE_FULL_RE = re.compile(
    r'^(?P<prefix>' + '|'.join(SOURCE_PREFIXES) + r')\s*'
    r'(?P<ann>[(（].*[)）])?$', re.S)

# 模板占位残留:`{中文占位}` / `<xxx>` / 待填词。
# ⚠️ 不要放宽成裸 `[{}]` 或裸 `xxx`:实测会误伤 `http://xxx-test.example.com/console`
#    与 `http://t.com/a?f={id}` 这类合法值。
PLACEHOLDER_RE = re.compile(
    r'\{\s*\}'                       # 空花括号
    r'|\{[^{}]*[一-鿿][^{}]*\}'   # 花括号内含中文 = 占位骨架
    r'|^<[^<>]+>$'                   # 整个值被尖括号包住
    r'|待编排层传入|待填|待补'
    r'|\bTODO\b'
    r'|(?<![\w-])x{3,}(?![\w-])',    # 独立的 xxx(不粘连字母/连字符)
    re.IGNORECASE)

RENDER_MODES = {'headless', 'headed'}

# 报告侧:来源标注整段(五类前缀 + 可选括号说明),矛盾检测前剔除,避免
# 「无头不可用降级(容器内无头启动崩溃)」这类合法标注被当成与结论矛盾。
# ⚠️ 括号内容**禁跨行**:早期版本用 `[^)）]*` 可跨行吞噬,一个漏写右括号的来源标注
#    会吃掉后文的矛盾表述,造成假绿灯。
SOURCE_ANNOTATION_RE = re.compile(
    '(?:' + '|'.join(SOURCE_PREFIXES) + r')\s*(?:[(（][^)）\n]*[)）])?')

# 报告侧词面同义/反义(仅词面检测,不做语义解析)
MODE_SYNONYMS = {'headless': ('headless', '无头'), 'headed': ('headed', '有头')}
MODE_OPPOSITES = {'headless': ('headed', '有头'), 'headed': ('headless', '无头')}
BOOL_SYNONYMS = {True: ('是', 'true', '复用'), False: ('否', 'false', '新起', '未复用')}

# 报告「一、测试概况」章节定位:起于「一、测试概况」标题,止于「二、」标题或文末。
SUMMARY_START_RE = re.compile(r'^#{1,6}\s*一\s*[、.．]?\s*测试概况', re.M)
SUMMARY_END_RE = re.compile(r'^#{1,6}\s*二\s*[、.．]', re.M)
REPORT_PLACEHOLDER_RE = re.compile(r'\{[^{}\n]{1,40}\}')


def _norm(text):
    """归一化:去空白并统一 x/×(viewport 常写 1905×2053 或 1905x2053)。"""
    return re.sub(r'[\s×xX*]', '', text.lower())


def _is_empty(value):
    """值是否算「没取到」。空串/空白同 null 处理(避免用空串绕过 null 规则)。"""
    return value is None or (isinstance(value, str) and not value.strip())


def check_facts(data):
    """校验 env-facts 对象本身,返回 issues 列表。"""
    issues = []

    def err(field, msg):
        issues.append({'level': 'error', 'field': field, 'msg': msg})

    def warn(field, msg):
        issues.append({'level': 'warn', 'field': field, 'msg': msg})

    # 事实字段 = 非元数据、非 Source 键
    fact_keys = [k for k in data if not _is_meta(k) and not k.endswith('Source')]
    fact_set = set(fact_keys)

    for field in REQUIRED_FACTS:
        if field not in data:
            err(field, f'缺必备事实字段 `{field}`(报告「一、测试概况」的数据源)')

    # 孤儿来源标注:有 `XSource` 却没有事实字段 `X`。
    # 这同时堵住「把事实字段起名叫 xxxSource」的绕过——那样它既不被校验也不要求来源。
    for key in data:
        if _is_meta(key) or not key.endswith('Source'):
            continue
        base = key[:-len('Source')]
        if not base or base not in fact_set:
            err(key, f'孤儿来源标注 `{key}`:找不到对应的事实字段 `{base}`。'
                     f'若 `{key}` 本身是事实字段,请改名(名字不要以 Source 结尾)'
                     f'并为它补 `{key}Source`')

    for field in fact_keys:
        value = data[field]
        skey = f'{field}Source'
        source = data.get(skey)

        # 类型契约:事实值必须能落进报告表格的一个单元格
        if isinstance(value, (list, dict)):
            err(field, f'`{field}` 的值必须是标量(字符串/布尔/数字)或 null,'
                       f'当前是 {type(value).__name__}——它既进不了报告表格,'
                       f'也会让 --report 对账静默跳过')
            continue
        if field in STR_FACTS and value is not None and not isinstance(value, str):
            err(field, f'`{field}` 契约为 `string|null`(见 report-format.md「一·补」),'
                       f'当前是 {type(value).__name__}:{value!r}')

        if not isinstance(source, str) or not source.strip():
            err(field, f'事实字段 `{field}` 缺来源标注 `{skey}`——'
                       f'每个环境事实字段都须逐个声明来源,禁模板默认')
            continue

        source = source.strip()
        m = SOURCE_FULL_RE.match(source)
        if not m:
            err(field, f'`{skey}` 取值 "{source}" 形态不合法。须为「前缀」或「前缀(说明)」,'
                       f'前缀 ∈ {" / ".join(SOURCE_PREFIXES)}')
            continue

        prefix, ann = m.group('prefix'), m.group('ann')
        ann_body = ann[1:-1].strip() if ann else ''
        if SOURCE_PREFIXES[prefix] and not ann_body:
            err(field, f'`{skey}` 为「{prefix}」时必须在括号内补'
                       f'{"方法" if prefix == "运行取证" else "原因/来源"}(不能是空括号或纯空白),'
                       f'当前为 "{source}"')
        if PLACEHOLDER_RE.search(source):
            err(field, f'`{skey}` 残留模板占位/待填值 "{source}"——'
                       f'来源标注是本硬门要守的核心,不许留骨架')

        # 「未取到」与 null 互为充要条件
        if prefix == '未取到' and not _is_empty(value):
            err(field, f'`{skey}` 声明「未取到」,但 `{field}` 仍有值 {value!r}——'
                       f'取不到必须写 null,不许回落模板默认或推断值')
        if prefix != '未取到' and _is_empty(value):
            err(field, f'`{field}` 为空,但 `{skey}` 声明为「{prefix}」——'
                       f'值取不到时来源必须写「未取到(原因)」')

        if isinstance(value, str) and PLACEHOLDER_RE.search(value):
            err(field, f'`{field}` 残留模板占位/待填值 {value!r}——'
                       f'实测取不到应写 null + 未取到(原因),不许留骨架')

    # 值域
    render_mode = data.get('renderMode')
    if not _is_empty(render_mode) and render_mode not in RENDER_MODES:
        err('renderMode', f'renderMode 取值须为 {sorted(RENDER_MODES)} 或 null,'
                          f'当前 {render_mode!r}')

    reused = data.get('reusedInstance')
    if reused is not None and not isinstance(reused, bool):
        err('reusedInstance', f'reusedInstance 须为布尔或 null,当前 {reused!r}')

    # ★核心约束:复用已有实例时命令传入的参数不生效,渲染模式不得声称「显式指定」。
    #   `reusedInstance` 为 null(没测出来)同样不许——「是否复用未知」不等于「已确认未复用」,
    #   而这恰是复用常驻实例场景下最典型的取证失败态。
    if reused is not False:
        rms = (data.get('renderModeSource') or '').strip()
        m = SOURCE_FULL_RE.match(rms)
        if m and m.group('prefix') == '显式指定':
            state = ('reusedInstance=true(连到已存在的实例)' if reused is True
                     else 'reusedInstance 未取到(是否复用未知 ≠ 已确认未复用)')
            err('renderModeSource',
                f'{state}时命令传入的启动参数不生效或无法确认生效,'
                f'renderModeSource 不得为「显式指定」,须以运行探测为准'
                f'(运行取证(方法) / 复用已有实例(来源) / 未取到(原因))')

    if 'probedAt' in data and not isinstance(data['probedAt'], str):
        warn('probedAt', 'probedAt 建议为 ISO 时间字符串(由执行期打戳,脚本不产生时间)')

    return issues


def _summary_section(report_text):
    """截出报告「一、测试概况」章节正文;定位不到返回 None。"""
    start = SUMMARY_START_RE.search(report_text)
    if not start:
        return None
    rest = report_text[start.end():]
    end = SUMMARY_END_RE.search(rest)
    return rest[:end.start()] if end else rest


def _label_lines(section, *labels):
    """概况里含指定标签的行;优先取表格行(以 | 开头),避免误取散文里的同名字样。"""
    hits = [ln for ln in section.splitlines()
            if any(lb.lower() in ln.lower() for lb in labels)]
    table = [ln for ln in hits if ln.lstrip().startswith('|')]
    return table or hits


def _value_text(lines, labels):
    """取这些行的「值」部分:剔除标签单元格本身与来源标注,再小写归一。

    ⚠️ 必须剔标签:标签词自身可能含判据词——「是否复用已有实例」里就同时含「是」与「复用」,
    不剔的话 `reusedInstance=True` 的 presence 检查恒真,报告把该行写反也发现不了
    (与早期 `HeadlessChrome` 顺带满足 headless presence 是同一类污染)。
    """
    out = []
    for ln in lines:
        seg = ln
        if ln.lstrip().startswith('|'):
            cells = ln.split('|')
            idx = next((i for i, c in enumerate(cells)
                        if any(lb.lower() in c.lower() for lb in labels)), None)
            if idx is not None:
                seg = '|'.join(cells[idx + 1:])
        else:
            low = ln.lower()
            ends = [low.find(lb.lower()) + len(lb) for lb in labels
                    if lb.lower() in low]
            if ends:
                seg = ln[max(ends):]
        out.append(seg)
    return SOURCE_ANNOTATION_RE.sub('', '\n'.join(out)).lower()


def check_report(data, report_text):
    """附加校验:报告「一、测试概况」是否与取证事实矛盾/未采用。仅词面检测,且只在概况章节内。"""
    if not isinstance(data, dict):
        return []
    issues = []

    section = _summary_section(report_text)
    if section is None:
        return [{'level': 'error', 'field': '-',
                 'msg': '报告中定位不到「一、测试概况」章节——概况是环境事实字段的落点,'
                        '缺章节即无法核对(报告章节完整性另见质量维度 7)'}]

    mode = data.get('renderMode')
    if mode in MODE_SYNONYMS:
        labels = ('渲染模式', 'renderMode')
        lines = _label_lines(section, *labels)
        if not lines:
            issues.append({'level': 'error', 'field': 'renderMode',
                           'msg': f'取证为 {mode},但概况里没有「渲染模式」行——'
                                  f'环境事实字段必须逐行落进概况,不能省略'})
        else:
            # 剔除标签与来源标注后再判词面:来源里合法地含模式词
            # (如「无头不可用降级(容器内无头启动崩溃)」),不剔除会把正当叙述判成自相矛盾。
            text = _value_text(lines, labels)
            if not any(w in text for w in MODE_SYNONYMS[mode]):
                issues.append({'level': 'error', 'field': 'renderMode',
                               'msg': f'取证为 {mode},但概况「渲染模式」行里没有该模式'
                                      f'({"/".join(MODE_SYNONYMS[mode])})——概况须以取证事实为数据源'})
            hit = [w for w in MODE_OPPOSITES[mode] if w in text]
            if hit:
                issues.append({'level': 'error', 'field': 'renderMode',
                               'msg': f'取证为 {mode},概况「渲染模式」行却出现相反表述 {hit}——'
                                      f'与实测运行形态矛盾'})
            # 概况章节内、渲染模式行**之外**出现相反模式词 → warn。
            # 行级定位(上面)负责判死,这一层兜住「备注行写『本轮实际以有头执行』」这类
            # 同章节内的自相矛盾;判 warn 而非 error 是因为概况里也可能有正当的说明性文字。
            # 范围仍严格限定在概况章节内——结论章的「建议下轮补一轮有头回归」不在扫描面,
            # 那正是早期全文扫描的假红灯来源。
            others = [ln for ln in section.splitlines() if ln not in lines]
            rest = SOURCE_ANNOTATION_RE.sub('', '\n'.join(others)).lower()
            rest_hit = [w for w in MODE_OPPOSITES[mode] if w in rest]
            if rest_hit:
                issues.append({'level': 'warn', 'field': 'renderMode',
                               'msg': f'取证为 {mode},概况章节其它位置出现相反表述 {rest_hit}——'
                                      f'请确认不是与实测矛盾的遗留叙述'})

    reused = data.get('reusedInstance')
    if isinstance(reused, bool):
        labels = ('是否复用已有实例', '复用', 'reusedInstance')
        lines = _label_lines(section, *labels)
        if not lines:
            # 同上：checklist 明列为不通过标志，判 warn 会被 exit 0 掩盖
            issues.append({'level': 'error', 'field': 'reusedInstance',
                           'msg': '概况里没有「是否复用已有实例」行——该行属必备环境事实'})
        else:
            text = _value_text(lines, labels)
            if not any(w in text for w in BOOL_SYNONYMS[reused]):
                issues.append({'level': 'warn', 'field': 'reusedInstance',
                               'msg': f'取证为 {reused},但概况「是否复用」行未体现'
                                      f'({"/".join(BOOL_SYNONYMS[reused])})'})
            opp = [w for w in BOOL_SYNONYMS[not reused] if w in text]
            if opp and not any(w in text for w in BOOL_SYNONYMS[reused]):
                issues.append({'level': 'error', 'field': 'reusedInstance',
                               'msg': f'取证为 {reused},概况「是否复用」行却写成相反结论 {opp}'})

    norm = _norm(section)
    # ⚠️ 这里**不能**硬编码字段列表,否则与 check_facts() 的「新增事实字段自动纳管」自相矛盾:
    #    SKILL.md 承诺「新增事实字段自动纳管、无需改脚本」——那只对 XSource 配对成立;
    #    早期本处写死四个字段,新增的 executionPath / datasourceOwnership 等一律查不出漏写。
    #    现在改为遍历**所有非元数据的字符串类事实字段**(renderMode 上面已单独按行判 error)。
    auto_fields = [k for k in data
                   if not _is_meta(k) and not k.endswith('Source')
                   and k != 'renderMode' and isinstance(data.get(k), str)]
    for field in auto_fields:
        value = data.get(field)
        if _is_empty(value) or not isinstance(value, str):
            continue
        if _norm(value) not in norm:
            # 只有 renderMode 判 error(它有同义词表 + 行级定位,检测可靠,且正是本检查的痛点字段);
            # 其余字段报告里常有等价改写(如版本写成「Chrome 149(无头)」),纯子串比对易假阳,
            # 故一律判 warn,交 --strict 决定是否计入失败。
            issues.append({'level': 'warn', 'field': field,
                           'msg': f'取证值 {value!r} 未出现在概况章节——'
                                  f'该字段可能来自模板默认而非取证'})

    leftovers = sorted(set(REPORT_PLACEHOLDER_RE.findall(section)))
    if leftovers:
        # ⚠️ error 不是 warn：quality-review-checklist 把「概况残留模板占位」明列为维度 7 的
        #    **不通过标志**，而全仓 4 处调用命令都不带 --strict —— 判 warn 时 exit 0，
        #    QR 子 Agent 按「非 0 退出即不通过」读，会把它当已通过。
        #    占位正则已限定 `\{[^{}\n]{1,40}\}`，正例零命中，升 error 无误报风险。
        issues.append({'level': 'error', 'field': '-',
                       'msg': f'概况章节残留模板占位 {leftovers[:5]}——报告应填实测值或「未取到(原因)」'})
    return issues


def main():
    ap = argparse.ArgumentParser(
        description='运行环境事实取证校验:每个环境事实字段须配套来源标注,'
                    '取不到必须写 null + 未取到(原因),禁模板默认/推断值。',
        epilog='示例: python3 check_env_facts.py round-1/env-facts.json '
               '--report 测试报告.md --json',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('env_facts', help='env-facts.json 路径')
    ap.add_argument('--report', help='(可选)测试报告 .md,核对概况与取证事实不矛盾')
    ap.add_argument('--json', action='store_true', help='JSON 输出(供子 Agent 解析)')
    ap.add_argument('--strict', action='store_true', help='warn 也计入失败')
    args = ap.parse_args()

    def bail(msg):
        payload = {'passed': False, 'error': msg}
        print(json.dumps(payload, ensure_ascii=False) if args.json else f'❌ {msg}')
        return 2

    path = Path(args.env_facts)
    if not path.is_file():
        return bail(f'env-facts 文件不存在:{path}——运行环境取证是环境准备阶段的必做原子步骤,'
                    f'缺文件即视为未取证')
    try:
        # utf-8-sig:兼容 Windows 侧产出的带 BOM 文件(本仓库脚本要求跨平台)
        data = json.loads(path.read_text(encoding='utf-8-sig'))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return bail(f'env-facts 解析失败:{exc}')
    if not isinstance(data, dict):
        return bail(f'env-facts 根节点必须是对象,当前是 {type(data).__name__}')

    issues = check_facts(data)

    if args.report:
        rp = Path(args.report)
        if not rp.is_file():
            return bail(f'报告文件不存在:{rp}')
        issues += check_report(data, rp.read_text(encoding='utf-8-sig', errors='replace'))

    errors = [i for i in issues if i['level'] == 'error']
    warns = [i for i in issues if i['level'] == 'warn']
    passed = not errors and (not warns or not args.strict)

    if args.json:
        print(json.dumps({
            'passed': passed, 'strict': args.strict,
            'env_facts': str(path), 'report': args.report,
            'checked_facts': [k for k in data
                              if not _is_meta(k) and not k.endswith('Source')],
            'errors': errors, 'warns': warns,
        }, ensure_ascii=False, indent=2))
    else:
        if passed and not warns:
            print('✅ 运行环境事实取证合规:各字段来源标注齐备,无模板默认残留')
        else:
            for i in errors:
                print(f"❌ [{i['field']}] {i['msg']}")
            for i in warns:
                print(f"⚠️  [{i['field']}] {i['msg']}")
            print(f"\n结论:{'✅ 通过' if passed else '❌ 不通过'}"
                  f"(error {len(errors)} / warn {len(warns)})")
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
