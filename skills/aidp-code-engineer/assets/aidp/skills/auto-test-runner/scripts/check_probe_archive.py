#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""环境探针档案有效性核验 — auto-test-runner 维度 7 折入子核查
(⚠️ **据实:只挂维度 7**。此处原写「维度 2 / 维度 7」,而 `quality-review-checklist.md`
 的探针档案核查项只在维度 7 下、维度 2 下一条都没有 —— 自述过期是本仓库高频缺陷,
 别让读者去维度 2 找一个不存在的核查项。档案是**输入侧**事物而维度 7 是「报告章节完整」,
 该归属语义上确有偏离,但那是基线既有、不在本轮改动范围内。)

「环境探针档案」= run-context 第四·补节记录的**上一轮**环境观测事实(驱动通道限制 / 鉴权头形态 /
未登录真实响应形态 / 三类取证可用性 / 元素定位方式 / 已知需重试项),用于启动前预热、减少重复探测。
它**不是权威契约**,本轮观测与之冲突时一律以本轮为准。

机制本身很有价值(实测:喂了上轮环境结论的轮次每用例 10.9s,没喂的首轮 197s)。
本脚本补的是它**反向制造危害**的那两条,而此前**一条机器检查都没有**:

  ★ C1 **失效条目被当成有效结论注入执行子 Agent 的 prompt。**
     实测:档案某行写着「⛔⛔ 主测账号口令失效、三条独立路径同结论」,而该档案按自身契约
     会注入 prompt ⇒ 子 Agent 收到一个带 ⛔⛔ 的**错误结论**,而那正是上一轮 31 条登录态用例
     集体 block 的成因。档案自己写了「冲突时以本轮为准、改写为『已失效 + 新结论』」,
     **但没有任何东西确保这件事做了**。
     处置:每条必填 `verified_at` + `verdict(valid|superseded)`;**注入前过滤掉 superseded**。

  ★ C2 **模板在鼓励写固定数值基线。** 上游数据会在测试窗口内被并发改动(实测:课程 5→4→3、
     活动 7→6,每次 DOM == 计数区 == 接口 三源自洽)⇒ 任何**绝对值**基线都会过期并制造
     **假性失败**。稳定成立的是**不变量**(`游客 ⊆ 某企业 = True`、`某企业 ⊆ 游客 = False`、
     差集成员名不变)。处置:每条必填 `事实性质(不变量|绝对值)`,绝对值类告警。

检查项:
【Critical(退出码 1)】
  P1 probe_missing_column   —— 7 列契约不齐(旧四列档案命中此条:没有 verdict 格,
                                「已失效」就**无处表达**,C1 必然复发)
  P2 probe_empty_cell       —— 任一必填格空 / 只有 `-`、`TBD`、`待补`、`同上`、`{占位}`
  P3 probe_bad_verdict      —— `verdict` 不是 `valid` / `superseded` 二选一
  P4 probe_bad_nature       —— `事实性质` 不是 `不变量` / `绝对值` 二选一
  P5 probe_bad_verified_at  —— `verified_at` 解析不出日期(写「上一轮」这类无法判新鲜度)
  P6 probe_row_width        —— 数据行格数与表头不符。**最常见根因是事实格里的 `|` 未转义为 `\|`**
                               (GFM 里它是列分隔符,反引号代码段保护不了它)。
                               ⚠️ 刻意不并进 P1:表象是「列数不符」,并进去只会报「表头列不齐」、
                               把排查带偏到表头上(与 `check_residual_assertions.py` 的 Z7、
                               `check_count_claim_table.py` 的 C5 同一取舍)

【Important(仅告警,不影响退出码)】
  W1 probe_stale            —— `verified_at` 距今 > `--stale-days`(默认 14)天未复验。
                                ⚠️ 必须显著标注:超期条目和刚验过的条目**长得一模一样**
  W2 probe_absolute_value   —— 事实性质=绝对值(易漂移,应尽量改写成不变量)

【Info(不影响退出码)】
  I1 probe_superseded_present —— 档案含 N 条 `superseded`。⚠️ **刻意不判违规**:留痕是对的,
                                 判了就是**常驻告警**(本仓库教训:假红常驻 = 硬门被绕过);
                                 但必须出声 —— **注入 prompt 前必须把这些条目过滤掉**,
                                 而「过滤没过滤」脚本看不见,属 QR 人工核查项。

⚠️ **档案是可选输入:整份找不到档案表 → `skipped: true` + exit 0,⛔ 不判缺表。**
   与 `quality-review-checklist.md` 既有口径一致(「可选子核查缺数据 → 退回旧路径,不判不通过」)。
   ⚠️ 故 `skipped=true` **不等于档案没问题**,只等于「本轮没提供档案」。

用法:
    python3 check_probe_archive.py <run-context 文件或目录> [--json] [--stale-days N] [--strict]

退出码: 0 = 通过或整档跳过 / 1 = 检出 Critical(`--strict` 时 Important 也算)
        2 = 入参或环境错(路径不存在、目录下无 .md、文件全部不可读)
⚠️ 严重度分档一律读 `--json`,**不占用退出码**(全仓约定)。

仅依赖 Python 3.8+ 标准库。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

# 7 列契约。
# ⚠️ **据实订正(独立审计复核)**:此处原写「`verified_at` 与 `verdict` 都以 `verd` 开头,
#    只靠 `in` 会**互认**」—— 那是**错的**:`in` 是子串包含,而这两个词**互不为子串**,
#    裸 `in` 本来就分得开。实测 17 种表头写法 × 7 列的矩阵一对一全部正确。
#    ⛔ 别照那句错因去「加固」,否则会引入真问题。
# ⚠️ 真正需要「互相排掉对方专名词」的风险在**别处**:本仓库三次踩到「两个中文列名字面互相包含
#    → col_index 解析到错位置 → 核心判据整条静默失效而表头看着完全正常」
#    (`check_list_page_scale.py` / `check_permission_constraint.py` /
#     `check_sibling_family_spec.py`);本表的 `上一轮观测事实` 与 `来源/轮次` 就有这个形态
#    (表头写成 `上一轮观测事实(含来源)` 时该格会因含别列专名词而**一列都匹配不上**)。
#    故保留「全串相等优先 + 含专名词且不含其它列专名词」两级判定。
COLUMNS = {
    'category': ('探针类别',),
    'fact': ('上一轮观测事实', '观测事实'),
    'nature': ('事实性质',),
    'verified_at': ('verified_at', '复验时间'),
    'verdict': ('verdict', '有效性'),
    'source': ('来源/轮次', '来源'),
    'action': ('本轮处置',),
}
REQUIRED_KEYS = tuple(COLUMNS)

NATURE_ENUM = ('不变量', '绝对值')
VERDICT_ENUM = ('valid', 'superseded')

# 占位/空值:全串精确匹配。⛔ 不可改 `search` —— 「不变量:差集成员名不变(同上一轮)」
# 是合格填写,子串匹配会把它判空。
EMPTY_MARKERS = {'', '-', '—', '–', 'tbd', 'TBD', 'n/a', 'N/A', '待补', '待填', '同上', '待定', '?', '??'}
# ⚠️ **全串锚定**(`^\{...\}$`),与全仓姊妹脚本同一约定:**不锚定**会把
#    「近 30 天(含今日,{T-29 00:00} 起)」这种**已填实、只留槽位**的合规写法整格判空。
#    ⚠️ 据实:锚定已写在**式子里**,所以此处 `match` 与 `search` **等价**,
#    姊妹脚本那句「⛔ 不可改 search」对本式不适用(变异实测属等价变异);
#    真正不可动的是 `^` 与 `$` 本身。
# ⚠️ 代价(登记在案,**不是**放宽判据的理由):① 嵌套花括号 `{round-{M-1} 证据}` 认不出来,
#    模板里**不要写嵌套占位**(本 SKILL 的模板已按此改);② 形如 `{"code":401}` 的 JSON 片段
#    会被当成占位,方向是假绿 —— 真要记这类事实请写成 `响应体 {"code":401}`(前面带说明词)。
PLACEHOLDER_RE = re.compile(r'^\{[^{}]*\}$')

DATE_RE = re.compile(r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})')
SEPARATOR_RE = re.compile(r'^\|[\s:|\-–—]+\|$')
CODE_FENCE_RE = re.compile(r'^\s*```')


def split_row(line: str):
    """按未转义的 `|` 切列。

    ⚠️ 与 `check_result.py` 无关,但与本 SKILL 之外的姊妹脚本口径一致:档案的「上一轮观测事实」
       格会写 `游客 ⊆ 某企业 \\| 某企业 ⊄ 游客` 这类**已按 GFM 规矩转义**的内容,
       裸 `split('|')` 会把合规行多切一格、当场判「格数不符」。
    """
    body = line.strip()
    if body.startswith('|'):
        body = body[1:]
    if body.endswith('|') and not body.endswith('\\|'):
        body = body[:-1]
    return [c.strip().replace('\\|', '|') for c in re.split(r'(?<!\\)\|', body)]


def is_empty_cell(value: str) -> bool:
    # ⚠️ **必须先剥反引号**:模板里的占位一律写成 `` `{YYYY-MM-DD}` ``(带反引号),
    #    不剥则 PLACEHOLDER_RE 整条失配 —— 实测后果是模板行被判 `probe_bad_verified_at`
    #    而不是「占位」,排查方向当场被带偏到日期格式上。
    v = (value or '').strip().strip('`').strip()
    return v in EMPTY_MARKERS or v.lower() in EMPTY_MARKERS or bool(PLACEHOLDER_RE.match(v))


def match_column(cell: str, key: str) -> bool:
    """单元格是否就是 `key` 这一列的表头。

    判据:**先全串小写相等**,再退到「含专名词且不含其它列的专名词」。
    ⚠️ `verified_at` / `verdict` 前缀相同,只靠 `in` 会互认。
    """
    c = (cell or '').strip().lower().strip('*` ')
    for alias in COLUMNS[key]:
        if c == alias.lower():
            return True
    others = [a.lower() for k, aliases in COLUMNS.items() if k != key for a in aliases]
    for alias in COLUMNS[key]:
        a = alias.lower()
        if a in c and not any(o in c for o in others if o != a and a not in o):
            return True
    return False


def find_archive_tables(lines):
    """找出档案表:表头须紧跟 GFM 分隔行,且命中 `探针类别` + ≥2 个其它契约列。

    ⚠️ **表头必须紧跟分隔行**:否则散文里「档案条目必填 `事实性质` | `verified_at` | `verdict`」
       这类**说明文字**会被当成一张缺列的表,本 SKILL 自带模板被自家硬门判死
       (`check_error_contract.py` 实测过这个坑)。
    """
    tables, in_fence = [], False
    for i, raw in enumerate(lines):
        if CODE_FENCE_RE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence or '|' not in raw:
            continue
        if i + 1 >= len(lines) or not SEPARATOR_RE.match(lines[i + 1].strip()):
            continue
        cells = split_row(raw)
        # ★ 识别口径:**(命中专名列 `探针类别` + ≥3 契约列) 或 (契约列 ≥4)**。
        # ⚠️⚠️ **⛔ 绝不可改回「必须命中 `探针类别`」** —— 那是本仓库记载过**三次**的同一个洞
        #    (`check_residual_assertions.py` C2 / `check_list_page_scale.py` ⑤ /
        #     `check_sibling_family_spec.py`):删掉其它任一列判 `probe_missing_column` **Critical**,
        #    而删掉或改名**专名列**那一张表**整张认不出来** → `skipped: true` + **exit 0**,
        #    **该最重的反而最轻**。独立审计实测:第一列表头从 `探针类别` 改成 `类别`、其余一字不动,
        #    连「⛔⛔ 口令失效 + verdict=无 + 直接采用」这条立论案例都被整条吞掉。
        # ⚠️ 两支都要:`>=4` 那支兜住专名列被改名的情形,`has_cat + >=3` 那支兜住列较少的残表
        #    (canonical 残表仍须报 `probe_missing_column`,⛔ 不得降成 skipped)。
        has_cat = any(match_column(c, 'category') for c in cells)
        hits = sum(1 for key in REQUIRED_KEYS
                   if any(match_column(c, key) for c in cells))
        if not ((has_cat and hits >= 3) or hits >= 4):
            continue
        rows = []
        for j in range(i + 2, len(lines)):
            nxt = lines[j]
            if CODE_FENCE_RE.match(nxt) or '|' not in nxt or not nxt.strip():
                break
            rows.append((j + 1, split_row(nxt)))
        tables.append({'line': i + 1, 'header': cells, 'rows': rows})
    return tables


def parse_date(value: str):
    m = DATE_RE.search(value or '')
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def check_table(table, rel, findings, stale_days, counters):
    header = table['header']
    index = {}
    for key in REQUIRED_KEYS:
        for pos, cell in enumerate(header):
            if match_column(cell, key):
                index[key] = pos
                break
    missing = [key for key in REQUIRED_KEYS if key not in index]
    if missing:
        counters['bad_tables'] += 1
        names = ' / '.join(COLUMNS[k][0] for k in missing)
        findings.append({
            'level': 'Critical', 'rule': 'probe_missing_column',
            'file': f'{rel}:{table["line"]}',
            'msg': f'环境探针档案缺列:{names} —— 没有 `verdict` 这一格,'
                   f'「已失效」就无处表达,失效条目会原样注入执行子 Agent 的 prompt'
                   f'(实测:一条带 ⛔⛔ 的错误结论造成 31 条登录态用例集体 block)',
        })
        return
    width = len(header)
    for lineno, cells in table['rows']:
        if len(cells) != width:
            counters['bad_tables'] += 1
            findings.append({
                'level': 'Critical', 'rule': 'probe_row_width',
                'file': f'{rel}:{lineno}',
                'msg': f'数据行 {len(cells)} 格、表头 {width} 格 —— '
                       f'最常见根因是事实格里的 `|` 未转义为 `\\|`(GFM 里它是列分隔符,'
                       f'反引号代码段保护不了它)',
            })
            continue
        cat = cells[index['category']] or f'第 {lineno} 行'
        empty_keys = [k for k in REQUIRED_KEYS if is_empty_cell(cells[index[k]])]
        empty = [COLUMNS[k][0] for k in empty_keys]
        # ★ **整行每个契约格都是占位 → 模板行,跳过。**
        # ⚠️ 不跳的后果是**自家模板被自家硬门判死**(`assets/run-context-template.md` 按定义
        #    就该带 `{YYYY-MM-DD}` 这类占位),而「假红常驻 = 硬门被绕过」是本仓库反复记录的教训。
        # ⚠️ 判据刻意**窄**:除「探针类别」外**每一格**都是占位才算模板行(这样的行携带零信息),
        #    ⛔ 不是「有占位就跳过」—— 只要有一格实填了,这行就是真条目,缺的格照判 Critical。
        # ⚠️ **为什么把「探针类别」排除在外**:模板里那一列是**固定分类法**(驱动通道限制 /
        #    鉴权头形态 / 未登录真实响应形态 / 三类取证可用性 / 元素定位方式 / 已知需重试项),
        #    本来就该实填;按「整行都是占位」判会一条都认不出来,模板照旧被判死(实测)。
        # ⚠️ 代价(登记在案):只填了类别、其余全空的行会被当模板行跳过,方向是假绿;
        #    但那种行同样携带零信息,且已计进 `template_rows` 出声。
        # ⚠️ 跳过必须**可见**:计进 `template_rows`,`--json` 与人读输出都写出来,
        #    否则「还没填」与「填好了」在报告里长得一模一样。
        if all(k in empty_keys for k in REQUIRED_KEYS if k != 'category'):
            counters['template'] += 1
            continue
        counters['rows'] += 1
        if empty:
            findings.append({
                'level': 'Critical', 'rule': 'probe_empty_cell',
                'file': f'{rel}:{lineno}',
                'msg': f'{cat}: 必填格空或占位({" / ".join(empty)}）—— '
                       f'留空无法区分「确认过没有」与「根本没考虑」',
            })
            continue
        nature = cells[index['nature']].strip().strip('*` ')
        if not any(e in nature for e in NATURE_ENUM):
            findings.append({
                'level': 'Critical', 'rule': 'probe_bad_nature',
                'file': f'{rel}:{lineno}',
                'msg': f'{cat}: 事实性质={nature!r} 不在二选一内 {NATURE_ENUM} —— '
                       f'这一格决定这条事实会不会过期:**绝对值**类(「课程共 5 条」)在测试窗口内'
                       f'就会被上游并发改动、制造假性失败,**不变量**类(「游客 ⊆ 某企业 = True」)才稳定',
            })
        elif NATURE_ENUM[1] in nature and NATURE_ENUM[0] not in nature:
            counters['absolute'] += 1
            findings.append({
                'level': 'Important', 'rule': 'probe_absolute_value',
                'file': f'{rel}:{lineno}',
                'msg': f'{cat}: 事实性质=绝对值 —— 实测上游数据在测试窗口内被并发改动过'
                       f'(课程 5→4→3、活动 7→6,每次三源自洽),任何固定数值基线都会过期;'
                       f'能改写成不变量就改写(差集成员名、子集关系),改不了的要在本轮处置里写明重探',
            })
        verdict = cells[index['verdict']].strip().strip('*` ').lower()
        if verdict not in VERDICT_ENUM:
            findings.append({
                'level': 'Critical', 'rule': 'probe_bad_verdict',
                'file': f'{rel}:{lineno}',
                'msg': f'{cat}: verdict={verdict!r} 不在二选一内 {VERDICT_ENUM}',
            })
        elif verdict == 'superseded':
            counters['superseded'] += 1
        when = parse_date(cells[index['verified_at']])
        if when is None:
            findings.append({
                'level': 'Critical', 'rule': 'probe_bad_verified_at',
                'file': f'{rel}:{lineno}',
                'msg': f'{cat}: verified_at={cells[index["verified_at"]]!r} 解析不出日期'
                       f'(须 YYYY-MM-DD)—— 写「上一轮」这类无法判新鲜度,而**超期未复验的条目'
                       f'和刚验过的条目在 prompt 里长得一模一样**',
            })
        else:
            age = (date.today() - when).days
            if age > stale_days:
                counters['stale'] += 1
                findings.append({
                    'level': 'Important', 'rule': 'probe_stale',
                    'file': f'{rel}:{lineno}',
                    'msg': f'{cat}: verified_at={when.isoformat()} 距今 {age} 天'
                           f'(> {stale_days})未复验 —— 注入 prompt 时必须显著标注「待复验」,'
                           f'⛔ 不得当作本轮结论使用',
                })


def collect_files(target: Path):
    """收集待检 `.md`。

    ⚠️ **断链符号链接必须收进来**(由调用方读取时落进 `read_errors`),⛔ 不能靠 `is_file()`
       静默过滤掉 —— 那会让「读不出来」既不出声也不影响 `skipped`,与全仓登记的口径
       「部分不可读 → 继续 + `read_errors[]` 进 `--json`;**全部**不可读才 exit 2」有缝。
    """
    if target.is_file():
        return [target]
    out = []
    for p in sorted(target.rglob('*.md')):
        if p.is_file() or p.is_symlink():
            out.append(p)
    return out


def main():
    ap = argparse.ArgumentParser(description='环境探针档案有效性核验')
    ap.add_argument('target', help='run-context 文件或目录')
    ap.add_argument('--json', action='store_true', help='输出 JSON(供 Agent 解析)')
    ap.add_argument('--stale-days', type=int, default=14, help='超期未复验阈值(默认 14 天)')
    ap.add_argument('--strict', action='store_true', help='Important 也计入失败')
    args = ap.parse_args()

    target = Path(args.target)
    # ⚠️ exists() 与 is_dir() 必须分开判(全仓约定②):合并写法会把「路径根本不存在」
    #    和「传入单个文件 = 合法」混为一谈,手滑写错路径等于整个检查静默放行。
    if not target.exists():
        print(f'路径不存在: {target}', file=sys.stderr)
        return 2
    files = collect_files(target)
    if not files:
        print(f'未发现 markdown 文件: {target}', file=sys.stderr)
        return 2

    findings, read_errors = [], []
    counters = {'rows': 0, 'superseded': 0, 'stale': 0, 'absolute': 0,
                'template': 0, 'bad_tables': 0}
    tables_total = 0
    for f in files:
        try:
            lines = f.read_text(encoding='utf-8', errors='replace').splitlines()
        except OSError as exc:
            read_errors.append({'file': str(f), 'error': str(exc)})
            continue
        rel = f.name if target.is_file() else str(f.relative_to(target))
        for table in find_archive_tables(lines):
            tables_total += 1
            check_table(table, rel, findings, args.stale_days, counters)

    if read_errors and len(read_errors) == len(files):
        print(f'全部文件不可读: {target}', file=sys.stderr)
        return 2
    for item in read_errors:
        findings.append({'level': 'Important', 'rule': 'read_error',
                         'file': item['file'],
                         'msg': f'读不出来、已跳过其内容({item["error"]})。'
                                f'⛔ 不得据此判该文件无违规'})

    if counters['superseded']:
        findings.append({
            'level': 'Info', 'rule': 'probe_superseded_present', 'file': '-',
            'msg': f'档案含 {counters["superseded"]} 条 verdict=superseded —— '
                   f'留痕是对的(⛔ 不许静默删),但**注入执行子 Agent 的 prompt 前必须把它们过滤掉**;'
                   f'脚本看不见「过滤没过滤」,这一条属 QR 人工核查',
        })

    # ⚠️⚠️ **`skipped` 绝不可与 findings 并存。** 三处文档都写「无档案 → `skipped: true` + exit 0」
    #    「`skipped` 只等于本轮没提供档案」,QR 子 Agent 据此把这一档标 N/A ——
    #    若此时还挂着 Critical,那条 Critical 就被**丢掉**。
    # ⚠️ 首版写的是 `counters['rows'] == 0`,而 P1(缺列)与行宽不符两条分支都在计数前
    #    `return`/`continue`,于是 `rows` 停在 0、`skipped` 被置真 —— 而 P1 命中的恰是
    #    **存量档案的默认形态**(旧四列),不是边角。
    # ⚠️ `not findings` 与 `bad_tables == 0` **互为冗余**(变异实测:去掉任一条行为不变、
    #    同时去掉才被测试抓住)。这是**刻意的双保险**,⛔ 别当死代码清掉其中一条 ——
    #    它守的是「`skipped: true` 与 Critical 并存」这一类假绿,而那一类的代价是
    #    QR 把整档读成 N/A、把 Critical 丢掉。
    skipped = (not findings and counters['rows'] == 0
               and counters['bad_tables'] == 0 and not read_errors)
    crit = [i for i in findings if i['level'] == 'Critical']
    imp = [i for i in findings if i['level'] == 'Important']
    passed = not crit and (not imp if args.strict else True)

    if args.json:
        print(json.dumps({
            'target': str(target), 'files': len(files), 'tables': tables_total,
            'rows': counters['rows'], 'template_rows': counters['template'],
            'superseded': counters['superseded'],
            'stale': counters['stale'], 'absolute_value_facts': counters['absolute'],
            'skipped': skipped, 'passed': passed,
            'critical': len(crit), 'important': len(imp),
            'read_errors': read_errors, 'findings': findings,
        }, ensure_ascii=False, indent=2))
    elif skipped and not findings:
        # ⚠️ 判据带 `not findings`:首版是裸 `elif skipped:`,排在明细打印之前,于是 P1 的消息
        #    **一个字都不打**,只留一行「整档跳过」配 rc=1 —— 一份说有问题却不说是什么、
        #    而且**说的是反话**(表就在那里)的报告。
        if tables_total and counters['template']:
            print(f'⚠️ 找到 {tables_total} 张档案表,但 {counters["template"]} 行仍是模板占位、'
                  f'一条实填条目都没有 —— 整档跳过。**这不是通过**,只是本轮没填档案')
        else:
            print('⚠️ 未发现环境探针档案表,整档跳过 —— 档案是可选输入,'
                  '但 skipped **不等于档案没问题**,只等于本轮没提供档案')
    else:
        print(f'档案表 {tables_total} 张 / 条目 {counters["rows"]} 条'
              + (f' / 模板占位行 {counters["template"]} 条(整行未填,已跳过 —— '
                 f'**不是通过**)' if counters['template'] else '')
              + f':Critical {len(crit)} / Important {len(imp)}')
        for i in findings:
            print(f'  [{i["level"]}] {i["rule"]}: {i["msg"]}')
        if passed:
            print('✅ 通过')
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
