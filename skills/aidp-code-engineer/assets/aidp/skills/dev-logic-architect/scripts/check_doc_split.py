#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_doc_split.py — 通用多文件拆分一致性检查（AIDP 索引态现行规范）

【AIDP 文档命名范式（本 SKILL 已收敛为「索引态」为唯一新生成形态）】
  - `00_` 槽位恒给专职索引 `00_索引.md`;内容主文档一律从 `01_` 起。
  - 即便只产一份内容文档,也走 `00_索引.md` + `01_<专题>.md`(≥2 文件)。
  - `00_索引.md` 载:全部内容文档清单 + 每份生成时间 + 主/补充标识(见 SKILL.md)。
  - `--supplement` 增量只给 `00_索引.md` 追加一行,不新造带"补充"字眼的文件名。

目录形态(自动识别,新生成只产索引态,其余均为历史 grandfather):
  - 索引态(默认/唯一新生成形态):`00_索引.md`(专职索引)+ `01_..98_` 内容 + `99_` 待澄清
      · 单份内容也走此态:`00_索引.md` + `01_<专题>.md`(≥2 文件)
      · 多专题:`00_索引.md` + `01_详细设计.md` + `02_接口设计.md` + `03_数据库设计.md` + …
  - 单份态(⚠️ 历史 grandfather):目录恰一份 `00_<专题>.md`(如 `00_详细设计.md`),00_ 即主文档本体
      → grandfather 放行、warn、exit 0;新生成不再产出(应走 00_索引.md + 01_<专题>.md)
  - 总览态(⚠️ 历史 grandfather):`00_*_总览.md` / `00_*-主文档.md` 作拆分锚
      → 识别但降级为 grandfather(warn,不 error);新生成统一 `00_索引.md`
  - 并列态(约定15,⚠️ 历史存量兼容):无任何 NN_ 序号文件 + ≥2 份裸名中文主文档共目录
      → 合法使用裸中文名,不强制 00_ 索引、不报"缺前缀"、grandfather 放行

  ⚠️ 00_ 槽位唯一:任一时刻目录内 00_ 文件唯一(现行规范恒为 00_索引.md)

  ⚠️ 总原则:历史存量(单份态 / 总览锚 / 并列态 / 补充中缀)绝不 exit 非 0(warn 放行);
     现行规范产出(00_索引.md + 01_*)必须 PASS。

检查项:
  1. 子文档文件名是否带两位数字序号前缀 (00_、01_、...)(并列态豁免)
  2. 主锚识别:`00_索引.md` 为首选/要求主锚;历史 `00_*_总览.md`/`00_*-主文档.md`/单份 `00_<专题>.md` 仍识别但降 grandfather(warn)
  2b.(硬核) 00_ 槽位唯一:目录内至多一个 00_ 主文档
  3. 主文档"文档结构与拆分说明"表中列出的子文档是否都存在
  4. 目录下是否有主文档未列出的子文档(反向检查)
  5. (可选) Task 编号在主+子文档间全局唯一
  6. (可选) 字典/枚举编码在多文件中全局唯一
  7. (硬核) 文件名分隔符必须用下划线 `_`,严禁 `-`(如 `01-接口设计.md`)
  8. (硬核) 拆分目录下严禁创建二级子目录嵌套(如 `modules/policy.md`)
  9. (硬核) 文件名去 NN_ 前缀后必须含中文字符(`[一-龥]`),纯英文/拼音/kebab 不通过
 10. (硬核) 业务模块代号(英文)不得入文件名(只允许中文业务描述)
 11. 语义前缀/中缀检测:
       · 无序号裸「补充-/追加-/附加-/扩展-」开头 → error
       · 历史 `NN_补充-/NN_追加-/NN_附加-/NN_扩展-` 中缀命中 → grandfather warn(exit 0)
 12. (硬核) 序号连续性:除保留整十号(10_/20_/30_...)及保留序号(98_/99_)外,序号不跳号

用法:
  python check_doc_split.py <文档目录>
  python check_doc_split.py <文档目录> --json
  python check_doc_split.py <文档目录> --check-tasks   # Task 编号唯一性(执行计划文档专用;详细设计不含 Task,本 SKILL 未使用)
  python check_doc_split.py <文档目录> --check-dict-enums

退出码:
  0 = 全部通过 / 单文件模式(无须拆分检查)/ 历史 grandfather 存量放行
  1 = 存在不通过项(仅现行规范违规:如新生成拆分态裸名、活跃语义前缀、序号跳号等)
  2 = 用法错误或目录不存在
"""

from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path

# 主文档锚识别:
#  - 现行规范(索引态):唯一主锚 `00_索引.md`(专职索引,00_ 槽位恒给它)
#  - 历史 grandfather:`00_*_总览.md` / `00_*-主文档.md` / 单份 `00_<专题>.md`(总览态/单份态旧锚)
# 中文名合法性由**本脚本内部检查项 9/10**(见上方 docstring「检查项」列表,非 QR 维度 9/10)统一校验;此处只负责"认出 00_ 主文档"并区分现行规范锚 vs 历史锚
MAIN_DOC_PATTERNS = [
    re.compile(r'^00_.+\.md$'),
]
# 现行规范主锚:专职索引 00_索引.md
INDEX_ANCHOR_PATTERN = re.compile(r'^00_索引\.md$')
# 历史总览锚:00_*_总览.md / 00_*-主文档.md
LEGACY_OVERVIEW_ANCHOR_PATTERN = re.compile(r'^00_.*(总览|主文档)\.md$')
SUB_DOC_PATTERN = re.compile(r'^(\d{2})_[^/]+\.md$')
# NN 序号前缀(下划线或短横,用于区分"已编号文件"与"裸名文件")
NN_PREFIX_PATTERN = re.compile(r'^\d{2}[_-]')
TASK_ID_PATTERN = re.compile(r'^#{1,3}\s*Task\s+(\d+\.\d+)\s*[:：]', re.MULTILINE)
ENUM_NAME_PATTERN = re.compile(
    r'^#{2,4}\s+([A-Za-z][A-Za-z0-9_]+)\s*[\(\(（]?(枚举|字典|Enum|Dict)?',
    re.MULTILINE,
)

# 7. NN- 分隔符违规(应用 `_`)
DASH_SEPARATOR_PATTERN = re.compile(r'^\d{2}-')
# 9. 中文字符
CHINESE_PATTERN = re.compile(r'[一-鿿]')
# 10. 纯英文模块代号(全部 ASCII letter/digit/dash/underscore,无中文)
ENGLISH_MODULE_PATTERN = re.compile(r'^[A-Za-z][A-Za-z0-9_-]+$')
# 11a. 无序号裸语义前缀违规(error):以「补充-/追加-…」开头且无 NN_ 序号
SEMANTIC_PREFIX_PATTERN = re.compile(r'^(补充|追加|附加|扩展|新增|extra|append|supplement|additional)[-_]', re.IGNORECASE)
# 11b. 历史带序号语义中缀(grandfather warn):NN_补充-/NN_追加-/NN_附加-/NN_扩展-
SEMANTIC_INFIX_PATTERN = re.compile(r'^\d{2}_(补充|追加|附加|扩展)[-_]')


def find_main_doc(doc_dir: Path):
    """优先返回现行规范索引锚 00_索引.md;否则回退到任意 00_ 主文档(历史锚)。"""
    zero = [f for f in doc_dir.iterdir()
            if f.is_file() and any(p.match(f.name) for p in MAIN_DOC_PATTERNS)]
    if not zero:
        return None
    for f in zero:
        if INDEX_ANCHOR_PATTERN.match(f.name):
            return f
    return sorted(zero, key=lambda f: f.name)[0]


def collect_sub_docs(doc_dir: Path, exclude):
    subs = []
    for f in sorted(doc_dir.iterdir()):
        if not f.is_file() or f.suffix != '.md':
            continue
        # `_` 前缀是开发期过程性文件，不属于交付子文档，不参与任何拆分判定。
        if f.name.startswith('_'):
            continue
        if exclude and f == exclude:
            continue
        subs.append(f)
    return subs


def collect_nested_md(doc_dir: Path):
    """收集二级或更深目录下的 .md(违反平铺原则)"""
    nested = []
    for f in doc_dir.rglob('*.md'):
        if f.parent != doc_dir and not f.name.startswith('_'):
            nested.append(f)
    return nested


def extract_referenced_files(main_doc: Path):
    text = main_doc.read_text(encoding='utf-8', errors='replace')
    files = set()
    # markdown 链接形态 [文本](02_x.md) —— 缺了它则「主文档引用断链」对可点击链接 100% 漏检，
    # 且合规索引（SKILL 自己的拆分规范要求「可点击跳转」）会被反过来误报「子文档未列出」。
    # ⚠️ 变量名是 files 不是 refs —— 此处曾误写 refs.add()，而 refs 从未定义，
    #    于是**索引里只要出现一个 markdown 链接就 NameError 崩溃**、exit 1 被读成"检出违规"，
    #    越是按规范写「可点击跳转」的索引越必崩，维度 9/Task 编号唯一两道闸门一次都没真跑过。
    for m in re.finditer(r'\[[^\]]*\]\(([^)#\s]+\.md)[^)]*\)', text):
        name = Path(m.group(1)).name
        if name and name != main_doc.name:
            files.add(name)
    for m in re.finditer(r'`([^`]+\.md)`', text):
        name = m.group(1).split('/')[-1].split(' ')[0]
        if name and name != main_doc.name:
            files.add(name)
    return files


def extract_task_ids(md_file: Path):
    text = md_file.read_text(encoding='utf-8', errors='replace')
    return TASK_ID_PATTERN.findall(text)


def extract_enum_names(md_file: Path):
    text = md_file.read_text(encoding='utf-8', errors='replace')
    return [m.group(1) for m in ENUM_NAME_PATTERN.finditer(text)]


# ── 碎片子文档检测(--check-fragment,补;此前本阈值**零机器门**)────────
# 判据(单一信源见 references/flow-output-format.md「避免过度拆分(碎片化)」口径块):
#   合规 = 行数 ≥150 **或** 体积 ≥6KB(二选一满足即可);违规 = 行数 <150 **且** 体积 <6KB。
#   ⚠️ 是「且」不是「或」——一份 120 行但 8KB 的密集文档(表格多、行长)**不是碎片**。
#     这一条连续两轮被文档写反(反向语义要求合规须同时满足两条),做成机器门正是为了不再靠人读。
MIN_SUB_DOC_LINES = 150
MIN_SUB_DOC_BYTES = 6 * 1024

# 碎片检测豁免(闭合清单,与 flow-output-format.md 口径块逐条对应):
#   ① 专职索引 00_;② 文件名以「索引.md」结尾的内部索引文档;③ 保留序号 98_/99_。
# ⚠️⚠️ ② 用「以 索引.md 结尾」,⛔ **不能用「含索引」**:「索引」在本 skill 是高频**业务**词
#    (数据库索引),按「含」豁免会把 `08_数据库索引设计.md` 这类业务文档一并放行,方向是**假绿**。
#    姊妹 skill ux-logic-extractor 的同名脚本用的是「含索引」——它那边 PRD 不讲数据库索引、安全,
#    ⛔ 照搬到本 skill 即是缺陷。
# ⚠️ ③ 必须有:本 skill 的目录范式**强制产出** `99_待澄清问题清单.md`,而它按性质天然短;
#    漏掉它会让每一份合规设计当场假红 —— 「假红常驻 = 硬门被绕过」。
FRAGMENT_EXEMPT_PATTERN = re.compile(r'^00_|^98_|^99_|索引\.md$|总览\.md$')


def is_fragment_exempt(name: str) -> bool:
    return bool(FRAGMENT_EXEMPT_PATTERN.search(name))


def check_fragment_docs(doc_dir, md_files):
    """行数 < 150 **且** 字节 < 6144 才判碎片。返回 issues 列表。"""
    out = []
    for f in sorted(md_files):
        if is_fragment_exempt(f.name):
            continue
        try:
            raw = f.read_bytes()
        except OSError as e:
            out.append({'dim': '碎片子文档', 'level': 'warn', 'file': f.name,
                        'msg': f'无法读取({e});本项跳过,⚠️ 这不是通过'})
            continue
        n_lines = len(raw.decode('utf-8', errors='replace').splitlines())
        n_bytes = len(raw)
        # ⚠️ **and 不是 or** —— 写成 or 会把密集短文档判死(连续两轮读错的就是这一处)。
        if n_lines < MIN_SUB_DOC_LINES and n_bytes < MIN_SUB_DOC_BYTES:
            out.append({'dim': '碎片子文档', 'level': 'error', 'file': f.name,
                        'lines': n_lines, 'bytes': n_bytes,
                        'msg': f'{f.name} 仅 {n_lines} 行 / {n_bytes} 字节 —— '
                               f'行数 <{MIN_SUB_DOC_LINES} **且** 体积 <{MIN_SUB_DOC_BYTES},属碎片,'
                               f'须合并回上级模块(满足其一即合规:行数 ≥{MIN_SUB_DOC_LINES} 或 体积 ≥{MIN_SUB_DOC_BYTES})'})
    return out


def main():
    parser = argparse.ArgumentParser(description='多文件拆分一致性检查')
    parser.add_argument('doc_dir', help='文档目录(包含主文档和子文档)')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--check-tasks', action='store_true')
    parser.add_argument('--check-dict-enums', action='store_true')
    parser.add_argument('--check-fragment', action='store_true',
                        help='碎片子文档检测(行数 <150 且 体积 <6KB 判碎片)')
    args = parser.parse_args()

    doc_dir = Path(args.doc_dir)
    # ⚠️ exists() 与 is_dir() 必须分开判（CLAUDE.md 退出码约定②，不可回退）。
    #    合并成一个 is_dir() 会把「路径根本不存在」和「传入单文件＝合法 N/A」压成同一个 exit 2，
    #    而下游 QR 口径把 exit 2 一律当「入参错、非维度违规、不计失败」略过
    #    —— 于是路径打错一个字，整档硬门静默消失且无任何告警。
    #    本脚本在 AIDP 下游是**恒跑**的兜底硬门（多文档拆分与命名序号，Critical），代价更大。
    #    与 ux-logic-extractor / dev-execution-planner 的同名脚本保持三态一致。
    if not doc_dir.exists():
        print(f'路径不存在: {doc_dir}', file=sys.stderr)
        return 2
    if doc_dir.is_file():
        # 传入单个 .md = 合法的单文件模式，属 N/A 跳过（0），不是入参错（2）
        if getattr(args, 'json', False):
            print(json.dumps({'skipped': True, 'mode': 'single_file',
                              'path': str(doc_dir)}, ensure_ascii=False, indent=2))
        else:
            print(f'单文件模式，本检查 N/A 跳过: {doc_dir}')
        return 0
    if not doc_dir.is_dir():
        print(f'既非文件也非目录: {doc_dir}', file=sys.stderr)
        return 2

    # `_` 前缀文件是过程性中间产物，不计入交付文档总数或模式判定。
    md_files = [f for f in doc_dir.iterdir()
                if f.is_file() and f.suffix == '.md' and not f.name.startswith('_')]
    issues = []
    summary = {'total_md': len(md_files), 'main_doc': None, 'sub_docs': 0, 'mode': 'single'}

    if len(md_files) <= 1:
        # 单份/空目录:
        #   · 现行规范要求索引态(00_索引.md + 01_<专题>.md,≥2 文件),故单份非现行规范默认。
        #   · 历史单份 `00_<专题>.md` 或裸名 → grandfather 放行、warn、exit 0(绝不 fail)。
        if len(md_files) == 1:
            only = md_files[0]
            if only.name.startswith('00_'):
                msg = (f'历史单份主文档 {only.name}(单份态 grandfather 放行);'
                       f'现行规范即便只产一份内容也应走 00_索引.md + 01_<专题>.md,'
                       f'请勿再新生成单份 00_<专题>.md 锚')
            else:
                msg = (f'历史裸名单份文档 {only.name}(grandfather 放行);'
                       f'现行规范应走 00_索引.md + 01_<专题>.md')
            issue = {'dim': '单份态 grandfather', 'level': 'warn', 'file': only.name, 'msg': msg}
            result = {'status': 'pass', 'mode': 'single', 'summary': summary, 'issues': [issue]}
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print('✅ 单文件模式(历史 grandfather 放行,跳过拆分检查)')
                print(f'  ⚠️ [{issue["dim"]}] {issue["msg"]}')
            return 0
        result = {'status': 'pass', 'mode': 'single', 'message': '单文件模式,跳过拆分检查', 'issues': []}
        print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else '✅ 单文件模式,跳过拆分检查')
        return 0

    summary['mode'] = 'multi'

    # 形态判定:无任何 NN_ 序号文件 + ≥2 份裸名 .md = 并列态(约定15 多主文档共目录,合法裸中文名)
    numbered = [f for f in md_files if NN_PREFIX_PATTERN.match(f.name)]
    bare = [f for f in md_files if not NN_PREFIX_PATTERN.match(f.name)]
    parallel_main = (not numbered) and len(bare) >= 2
    if parallel_main:
        summary['mode'] = 'parallel-main'

    main_doc = find_main_doc(doc_dir)
    if parallel_main:
        # 并列态(历史 grandfather):不强制 00_ 索引;每份裸名文件均为并列主文档。
        # ⚠️ 不再静默 PASS:发 warn 提示——新生成 ≥2 份专题主文档一律走 00_索引.md 拆分态,
        # 严禁裸中文名多文件(如 详细设计.md+接口设计.md 并列无前缀无索引)。历史存量仍 grandfather 不硬失败(exit 0)。
        summary['main_doc'] = '(并列态,历史 grandfather,无 00_ 索引)'
        issues.append({'dim': '并列态裸名(历史)', 'level': 'warn',
                       'msg': f'检测到并列态:{len(bare)} 份裸中文名主文档、无 00_ 索引、无序号前缀'
                              f'({", ".join(f.name for f in bare[:5])}{"…" if len(bare) > 5 else ""})。'
                              f'历史存量 grandfather 放行;但新生成 ≥2 份专题主文档必须走拆分态 '
                              f'00_索引.md + 01_详细设计.md/02_接口设计.md/…,不得产裸名多文件。'})
    elif not main_doc:
        issues.append({'dim': '主文档', 'level': 'error',
                       'msg': f'未找到 00_ 主文档;现行规范要求 00_索引.md 作专职索引锚(目录: {doc_dir})'})
    else:
        summary['main_doc'] = main_doc.name
        summary['mode'] = 'index' if INDEX_ANCHOR_PATTERN.match(main_doc.name) else 'multi'
        # 主锚新旧口径:00_索引.md = 现行规范;00_*_总览.md/00_*-主文档.md = 历史锚(warn,不 error)
        if not INDEX_ANCHOR_PATTERN.match(main_doc.name):
            if LEGACY_OVERVIEW_ANCHOR_PATTERN.match(main_doc.name):
                issues.append({'dim': '主锚旧口径', 'level': 'warn', 'file': main_doc.name,
                               'msg': f'主锚 {main_doc.name} 为历史总览/主文档锚(grandfather 放行);'
                                      f'现行规范应改用专职索引 00_索引.md'})
            else:
                issues.append({'dim': '主锚旧口径', 'level': 'warn', 'file': main_doc.name,
                               'msg': f'主锚 {main_doc.name} 非现行规范索引锚(grandfather 放行);'
                                      f'现行规范应改用专职索引 00_索引.md,内容主文档从 01_ 起'})

    # 2b. 00_ 槽位唯一:目录内 00_ 文件至多一个(现行规范恒为 00_索引.md)
    zero_prefixed = [f for f in md_files if f.name.startswith('00_')]
    if len(zero_prefixed) > 1:
        issues.append({'dim': '00_ 槽位唯一', 'level': 'error',
                       'file': ', '.join(sorted(f.name for f in zero_prefixed)),
                       'msg': f'目录内出现多个 00_ 文件({sorted(f.name for f in zero_prefixed)});'
                              f'00_ 槽位唯一,现行规范仅允许 00_索引.md,内容主文档应改用 01_ 起的序号'})

    sub_docs = collect_sub_docs(doc_dir, exclude=main_doc)
    summary['sub_docs'] = len(sub_docs)

    all_named = sub_docs + ([main_doc] if main_doc else [])

    # 1. 文件名序号前缀(同时处理主文档与子文档;并列态豁免——裸名主文档合法)
    if not parallel_main:
        for f in all_named:
            if not SUB_DOC_PATTERN.match(f.name):
                issues.append({'dim': '文件名序号', 'level': 'error', 'file': f.name,
                               'msg': f'子文档 {f.name} 未使用两位数字前缀+下划线(如 01_xxx.md)'})

    # 7. NN- 分隔符违规
    for f in all_named:
        if DASH_SEPARATOR_PATTERN.match(f.name):
            issues.append({'dim': '文件名分隔符', 'level': 'error', 'file': f.name,
                           'msg': f'文件名 {f.name} 用了 `-` 作分隔符,必须改为 `_`(如 01_xxx.md)'})

    # 9. 中文 + 10. 业务代号检测(去 NN_/NN- 前缀后判定)
    for f in all_named:
        stem = f.stem
        base = re.sub(r'^\d{2}[_-]?', '', stem)
        if not base:
            continue
        if not CHINESE_PATTERN.search(base):
            issues.append({'dim': '中文文件名', 'level': 'error', 'file': f.name,
                           'msg': f'文件名 {f.name} 去 NN_ 前缀后无中文字符,违反「中文业务描述」原则'})
            if ENGLISH_MODULE_PATTERN.match(base):
                issues.append({'dim': '业务代号入名', 'level': 'error', 'file': f.name,
                               'msg': f'文件名 {f.name} 使用了英文业务代号 `{base}`;业务代号只能写在文件正文头部元数据,不进文件名'})

    # 8. 二级目录嵌套违规
    for f in collect_nested_md(doc_dir):
        rel = f.relative_to(doc_dir)
        issues.append({'dim': '目录结构平铺', 'level': 'error', 'file': str(rel),
                       'msg': f'拆分文档应平铺在版本目录下,严禁二级子目录嵌套({rel})'})

    # 11. 语义前缀/中缀检测
    #   11a. 无序号裸「补充-/追加-…」开头 → error(活跃违规)
    #   11b. 历史 `NN_补充-/NN_追加-…` 中缀 → grandfather warn(exit 0)
    for f in all_named:
        if SEMANTIC_INFIX_PATTERN.match(f.name):
            issues.append({'dim': '语义中缀(历史)', 'level': 'warn', 'file': f.name,
                           'msg': f'文件名 {f.name} 含历史语义中缀(NN_补充-/追加-/附加-/扩展-);'
                                  f'grandfather 放行,现行规范补充文档应直接用序号+业务名(如 07_订单域字典枚举.md),'
                                  f'并只在 00_索引.md 标类型=补充'})
        elif SEMANTIC_PREFIX_PATTERN.search(f.name):
            issues.append({'dim': '语义前缀违规', 'level': 'error', 'file': f.name,
                           'msg': f'文件名 {f.name} 使用了无序号语义前缀(补充/追加/附加/扩展等),'
                                  f'必须改为序号+业务名(如 07_订单域字典枚举.md)'})

    # 12. 序号连续性检测(提取所有序号,检查是否连续)
    seq_nums = []
    for f in all_named:
        m = SUB_DOC_PATTERN.match(f.name)
        if m:
            seq_nums.append((int(m.group(1)), f.name))
    seq_nums.sort()

    # 检查序号连续性(允许保留整十号和98_/99_)
    for i in range(len(seq_nums) - 1):
        cur_num, cur_file = seq_nums[i]
        next_num, next_file = seq_nums[i + 1]
        gap = next_num - cur_num

        # 允许的跳号情况
        if gap == 1:
            continue  # 连续,OK
        if gap == 0:
            continue  # 同序号(不同主/子文件),由 00_ 槽位唯一等单独判
        if cur_num % 10 == 0 and gap <= 10:
            continue  # 整十号后可跳到下一个整十号前,OK
        if cur_num < 98 and next_num >= 98:
            continue  # 跳到保留序号98_/99_,OK

        # 不允许的跳号
        issues.append({'dim': '序号连续性', 'level': 'error',
                       'file': f'{cur_file} → {next_file}',
                       'msg': f'序号从 {cur_num:02d}_ 跳到 {next_num:02d}_(跳 {gap}),违反序号连续累进原则(允许保留整十号和98_/99_)'})

    # 2-3. 主文档引用 vs 实际文件
    if main_doc:
        referenced = extract_referenced_files(main_doc)
        actual = {f.name for f in sub_docs}
        missing_in_dir = referenced - actual - {main_doc.name}
        missing_in_dir = {n for n in missing_in_dir if SUB_DOC_PATTERN.match(n)}
        unlisted = actual - referenced
        for n in sorted(missing_in_dir):
            issues.append({'dim': '主文档引用一致性', 'level': 'error', 'file': n,
                           'msg': f'主文档引用了 {n} 但目录下不存在'})
        for n in sorted(unlisted):
            issues.append({'dim': '主文档引用一致性', 'level': 'warn', 'file': n,
                           'msg': f'子文档 {n} 存在但主文档未在结构表中列出'})

    # 4. Task 编号全局唯一
    if args.check_tasks:
        task_map = {}
        for f in sub_docs:
            for tid in extract_task_ids(f):
                task_map.setdefault(tid, []).append(f.name)
        for tid, files in task_map.items():
            if len(files) > 1:
                issues.append({'dim': 'Task 编号唯一性', 'level': 'error', 'task': tid,
                               'msg': f'Task {tid} 在多个子文档中重复定义: {files}'})
        summary['task_count'] = len(task_map)

    # 5. 字典/枚举名全局唯一
    if args.check_dict_enums:
        enum_map = {}
        for f in sub_docs:
            for name in extract_enum_names(f):
                enum_map.setdefault(name, []).append(f.name)
        for name, files in enum_map.items():
            if len(files) > 1:
                issues.append({'dim': '字典枚举名唯一性', 'level': 'error', 'name': name,
                               'msg': f'字典/枚举 {name} 在多个子文档中重复定义: {files}'})
        summary['enum_count'] = len(enum_map)

    # 6. 碎片子文档检测(行数 <150 **且** 体积 <6KB;豁免 00_/98_/99_/「索引.md」结尾)
    # ⚠️ 扫 md_files 而非 sub_docs:两者的差别是主文档在不在内,而主文档已被 `^00_` 豁免覆盖,
    #    用 md_files 可以顺带覆盖「只有 01_ 一份内容文档」的单文件拆分态。
    if args.check_fragment:
        frag = check_fragment_docs(doc_dir, md_files)
        issues.extend(frag)
        summary['fragment_checked'] = len(md_files)
        summary['fragment_exempt'] = sum(1 for f in md_files if is_fragment_exempt(f.name))

    status = 'pass' if not any(i['level'] == 'error' for i in issues) else 'fail'
    result = {'status': status, 'summary': summary, 'issues': issues}

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f'状态: {"✅ PASS" if status == "pass" else "❌ FAIL"}  '
              f'(形态: {summary["mode"]}, 主文档: {summary["main_doc"]}, 子文档: {summary["sub_docs"]})')
        for i in issues:
            icon = '❌' if i['level'] == 'error' else '⚠️'
            print(f'  {icon} [{i["dim"]}] {i["msg"]}')
        if not issues:
            print('  无问题')

    return 0 if status == 'pass' else 1


if __name__ == '__main__':
    sys.exit(main())
