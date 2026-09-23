#!/usr/bin/env python3
"""
check_doc_split.py — 通用多文件拆分一致性检查（AIDP 文档命名范式）

【AIDP 文档命名范式（四 SKILL 统一）】
  1. `00_` 槽位恒给专职索引 `00_索引.md`;内容主文档一律从 `01_` 起。
     即便只有一份内容文档,也产出两个文件:`00_索引.md` + `01_<语义名>.md`。
  2. `00_索引.md` 载:全部内容文档(`01_`+)清单 + 每份生成时间 + 主/补充标识。
  3. 补充文档:文件名不带「补充」字眼,直接 `NN_<业务名>.md`;`--supplement` 只追加索引行。
  4. 历史存量(裸 `00_<语义名>.md` / `00_…-总览.md` / `NN_补充-…`):grandfather 识别放行、不报错。

检查项:
  1. 子文档文件名是否带两位数字序号前缀 (00_、01_、...)
  2. 主锚(优先/要求 `00_索引.md`;历史 `00_*-总览.md`/`00_*-主文档.md` grandfather 识别)是否存在
  3. 主文档"文档结构与拆分说明"表中列出的子文档是否都存在
  4. 目录下是否有主文档未列出的子文档(反向检查)
  5. (可选) Task 编号在主+子文档间全局唯一
  6. (可选) 字典/枚举编码在多文件中全局唯一
  7. 禁语义前缀:行首裸「补充-/追加-/附加-/扩展-」= error;`NN_补充-` 等中缀 = warn(grandfather)
  8. 碎片子文档检测:子文档(排除 00_ 主文档/总览/索引)行数 < 150 行视为碎片,不通过
     (对应 dev-execution-planner 维度 11.6「子文档 ≥ 150 行,碎片即不通过」)
  9. 目录结构平铺:顶层只有 `00_索引.md`、内容文档却躺在二级子目录(典型:多用户模式
     按人建 `张三/` `李四/` 目录)= error。**本条就是为堵这个洞而设**:本脚本的清单以顶层为准,
     若无此条,该布局会被判成「单文件模式」整体放行,拆分一致性与 Task 编号唯一两道闸门同时失效。
     现已通过 rglob 探到二级子目录并直接判 error。人员归属写进文件名后缀
     (`01_研发执行计划-张三.md`),不进目录层级。

用法:
  python check_doc_split.py <文档目录>
  python check_doc_split.py <文档目录> --json
  python check_doc_split.py <文档目录> --check-tasks         # 执行计划场景
  python check_doc_split.py <文档目录> --check-dict-enums    # 详细设计场景

退出码:
  0 = 全部通过 / 仅历史 grandfather 告警(warn)
  1 = 存在不通过项(error)
  2 = 用法错误或目录不存在
"""

from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path

# 现行规范主锚:专职索引
INDEX_DOC_PATTERN = re.compile(r'^00_索引\.md$')
# 历史主锚(grandfather 识别,不报错):00_*-总览.md / 00_*-主文档.md
LEGACY_MAIN_DOC_PATTERNS = [
    re.compile(r'^00_.*(总览|主文档)\.md$'),
]
# ⚠️ 裸 `00_<语义名>.md` 也是 grandfather 形态（补，对齐 ux 副本的
# MAIN_DOC_FALLBACK_PATTERN）：缺这条兜底时，历史存量 `00_研发执行计划.md` 会被判
# 「未找到主锚」exit 1 —— 与本文件 docstring「历史存量 grandfather 识别放行、
# **绝不 exit 非 0**」及 flow-qr-dispatch.md「0=通过(含仅历史 grandfather 告警)」
# 直接冲突。同一 fixture 下 ux/architect 两份副本均 exit 0，只有本份判死。
MAIN_DOC_FALLBACK_PATTERN = re.compile(r'^00_.*\.md$')
SUB_DOC_PATTERN = re.compile(r'^(\d{2})_[^/]+\.md$')
# ⚠️ 必须与 check_task_granularity.py 的 TASK_HEADER_RE 兼容:**四井号**与**省略冒号**两种
#    形态都要认。早期这里是 `^#{1,3}…[:：]`(最多三井号 + 冒号强制),而 flow-edge-cases.md
#    自己就在用 `#### Task 4.1:` —— 实测「两文档重号 Task 1.1」用四井号或省冒号写时
#    **重号一条都检不出**(维度 11「Task 编号全局唯一」假绿)。范围放宽到 2~4 井号并兼容存量两井号。
TASK_ID_PATTERN = re.compile(r'^#{2,4}\s*Task\s+(\d+\.\d+)\s*[:：]?', re.MULTILINE)
ENUM_NAME_PATTERN = re.compile(r'^#{2,4}\s+([A-Za-z][A-Za-z0-9_]+)\s*[（(]?(枚举|字典|Enum|Dict)?', re.MULTILINE)

# 7. 禁语义前缀
# 行首裸「补充-/追加-/附加-/扩展-」(无两位序号) = error
SEMANTIC_BARE_PATTERN = re.compile(r'^(补充|追加|附加|扩展)-')
# 带序号的语义中缀 `NN_补充-` 等 = warn(历史存量 grandfather,不硬失败)
SEMANTIC_MIDFIX_PATTERN = re.compile(r'^\d{2}_(补充|追加|附加|扩展)-')

# 8. 碎片子文档检测:子文档行数下限(< 此值视为碎片,不通过)
MIN_SUB_DOC_LINES = 150
# 碎片检测豁免:00_ 主文档/总览/索引 + 98_/99_ 等固定编号聚合清单(常合法地短)
OVERVIEW_INDEX_PATTERN = re.compile(r'^00_|^98_|^99_|总览|索引|index|待澄清|跨系统', re.IGNORECASE)


def find_index_doc(doc_dir: Path) -> Path | None:
    """现行规范主锚:专职索引 00_索引.md"""
    for f in doc_dir.iterdir():
        if f.is_file() and INDEX_DOC_PATTERN.match(f.name):
            return f
    return None


def find_legacy_main_doc(doc_dir: Path) -> Path | None:
    """历史主锚(grandfather):00_*-总览.md / 00_*-主文档.md"""
    for f in doc_dir.iterdir():
        if f.is_file() and (any(p.match(f.name) for p in LEGACY_MAIN_DOC_PATTERNS)
                            or MAIN_DOC_FALLBACK_PATTERN.match(f.name)):
            return f
    return None


def collect_sub_docs(doc_dir: Path, exclude: Path | None) -> list[Path]:
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


def extract_referenced_files(main_doc: Path) -> set[str]:
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


def extract_task_ids(md_file: Path) -> list[str]:
    text = md_file.read_text(encoding='utf-8', errors='replace')
    return TASK_ID_PATTERN.findall(text)


def extract_enum_names(md_file: Path) -> list[str]:
    text = md_file.read_text(encoding='utf-8', errors='replace')
    return [m.group(1) for m in ENUM_NAME_PATTERN.finditer(text)]


def count_lines(md_file: Path) -> int:
    """统计文件总行数(含空行,与人工 wc -l 直觉一致)"""
    text = md_file.read_text(encoding='utf-8', errors='replace')
    if not text:
        return 0
    return len(text.splitlines())


def is_overview_or_index(name: str) -> bool:
    """碎片检测豁免: 00_ 主文档 / 总览 / 索引文档不参与行数下限检查"""
    return bool(OVERVIEW_INDEX_PATTERN.search(name))


def check_semantic_prefix(sub_docs: list[Path], issues: list[dict]) -> None:
    """7. 禁语义前缀:行首裸「补充-」= error;`NN_补充-` 中缀 = warn(grandfather)"""
    for f in sub_docs:
        if SEMANTIC_MIDFIX_PATTERN.match(f.name):
            issues.append({'dim': '禁语义前缀', 'level': 'warn', 'file': f.name,
                           'msg': f'文件名 {f.name} 含语义中缀(补充-/追加-/附加-/扩展-),'
                                  f'现行规范应直接 `NN_<业务名>.md`;历史存量 grandfather 放行(不硬失败)'})
        elif SEMANTIC_BARE_PATTERN.match(f.name):
            issues.append({'dim': '禁语义前缀', 'level': 'error', 'file': f.name,
                           'msg': f'文件名 {f.name} 以语义词(补充-/追加-/附加-/扩展-)开头且无两位序号前缀,'
                                  f'应改为 `NN_<业务名>.md`'})


def main() -> int:
    parser = argparse.ArgumentParser(description='多文件拆分一致性检查(AIDP 命名范式)')
    parser.add_argument('doc_dir', help='文档目录(包含索引和内容文档)')
    parser.add_argument('--json', action='store_true', help='以 JSON 格式输出结果')
    parser.add_argument('--check-tasks', action='store_true', help='额外检查 Task 编号全局唯一(执行计划场景)')
    parser.add_argument('--check-dict-enums', action='store_true', help='额外检查字典/枚举名全局唯一(详细设计场景)')
    args = parser.parse_args()

    doc_dir = Path(args.doc_dir)
    # ⚠️ exists() 与 is_dir() 必须分开判（CLAUDE.md 退出码约定②，不可回退）。
    #    合并成一个 is_dir() 会把「路径根本不存在」和「传入单文件＝合法 N/A」压成同一个 exit 2，
    #    而下游 QR 口径把 exit 2 一律当「入参错、非维度违规、不计失败」略过
    #    —— 于是路径打错一个字，整档硬门静默消失且无任何告警。
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
    issues: list[dict] = []
    summary: dict = {'total_md': len(md_files), 'main_doc': None, 'sub_docs': 0, 'mode': 'single'}

    index_doc = find_index_doc(doc_dir)
    legacy_main = find_legacy_main_doc(doc_dir)

    # ── 【无条件前置】目录结构平铺 ────────────────────────────────
    # ⚠️ 这一检查**必须先于模式判定**,且不得挂在任何分支下。
    #    早期它嵌在 `if len(md_files) <= 1:` + `if index_doc:` 双重分支里,只有
    #    「顶层恰好只有 00_索引.md」这一种形态会走到,实测两种更常见的布局直接 exit 0 逃检:
    #      · 顶层 00_索引.md + 01_总览.md,真内容仍在 张三/ 李四/  → 走多文件分支,碰不到本检查
    #      · 顶层零 md,全部内容在 张三/ 李四/                      → index_doc 为 None,走 else
    #    后者更糟:它还会自报「单文件模式(grandfather 放行)」,而目录里其实有 N 份子目录文档,
    #    连 --check-tasks 的 Task 编号全局唯一也一并失效(collect_sub_docs 只 iterdir 顶层)。
    # ⚠️ 白名单不可少:资产目录(assets/images/附件)与归档目录(历史版本/archive)里
    #    放带序号的 .md 是**合法**的,无白名单会把这两类正常布局硬阻断 exit 1。
    _NESTED_ALLOW = {'assets', 'images', 'img', 'attachments', '附件', '素材',
                     'archive', '归档', '历史版本', '旧版本', '.git'}
    nested = sorted(
        p for p in doc_dir.rglob('*.md')
        if p.parent != doc_dir and SUB_DOC_PATTERN.match(p.name)
        and not (_NESTED_ALLOW & set(p.relative_to(doc_dir).parts[:-1]))
    )
    if nested:
        summary['nested_content_docs'] = [str(p.relative_to(doc_dir)) for p in nested]
        issues.append({
            'dim': '目录结构平铺', 'level': 'error',
            'msg': '内容文档位于二级子目录('
                   + ', '.join(str(p.relative_to(doc_dir)) for p in nested[:5])
                   + (' …' if len(nested) > 5 else '')
                   + ')。执行计划文档必须**平铺**在同一目录下'
                     '(多用户模式把人名写进文件名后缀,如 01_研发执行计划-张三.md,'
                     '严禁按人建子目录),否则拆分一致性与 Task 编号全局唯一两道闸门整体失效。'})
        result = {'status': 'fail', 'mode': 'nested', 'summary': summary, 'issues': issues}
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print('❌ FAIL  (内容文档被放进了二级子目录,必须平铺)')
            for i in issues:
                mark = '❌' if i['level'] == 'error' else '⚠️'
                print(f'  {mark} [{i["dim"]}] {i["msg"]}')
        return 1

    # ── 单/裸文件模式判定 ──────────────────────────────────────────
    # 现行规范要求 `00_索引.md` + `01_<语义名>.md`(≥2 文件)。
    # 历史裸单文件(仅 1 个 .md 且非 00_索引.md)grandfather 放行、warn、不 exit 非 0。
    if len(md_files) <= 1:
        summary['mode'] = 'single'
        if index_doc:
            # 只有 00_索引.md 而无内容文档:范式要求 + 01_ 内容文档,提示但不硬失败
            issues.append({'dim': '现行规范', 'level': 'warn',
                           'msg': '仅有 00_索引.md 而无内容文档(01_+);现行规范应产出 00_索引.md + 01_<语义名>.md'})
            result = {'status': 'pass', 'mode': 'single', 'summary': summary, 'issues': issues}
        else:
            issues.append({'dim': '现行规范', 'level': 'warn',
                           'msg': '历史裸单文件模式:现行规范要求 00_索引.md + 01_<语义名>.md(≥2 文件);'
                                  '历史存量 grandfather 放行(不硬失败)'})
            result = {'status': 'pass', 'mode': 'single', 'summary': summary, 'issues': issues}
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print('✅ 单文件模式(grandfather 放行)')
            for i in issues:
                print(f'  ⚠️ [{i["dim"]}] {i["msg"]}')
        return 0

    # ── 多文件模式 ────────────────────────────────────────────────
    summary['mode'] = 'multi'

    # 主锚:优先 00_索引.md;否则回退历史主锚(grandfather,warn)
    if index_doc:
        main_doc = index_doc
        summary['main_doc'] = index_doc.name
    elif legacy_main:
        main_doc = legacy_main
        summary['main_doc'] = legacy_main.name
        issues.append({'dim': '主文档', 'level': 'warn', 'file': legacy_main.name,
                       'msg': f'使用历史主锚 {legacy_main.name}(总览/主文档);'
                              f'现行规范应产出专职索引 00_索引.md(grandfather 放行,不硬失败)'})
    else:
        main_doc = None
        issues.append({'dim': '主文档', 'level': 'error',
                       'msg': f'未找到主锚:现行规范要求 00_索引.md(历史 00_*-总览.md/00_*-主文档.md 亦可识别)。目录: {doc_dir}'})

    sub_docs = collect_sub_docs(doc_dir, exclude=main_doc)
    summary['sub_docs'] = len(sub_docs)

    # 1. 文件名序号前缀
    for f in sub_docs:
        if not SUB_DOC_PATTERN.match(f.name):
            issues.append({'dim': '文件名序号', 'level': 'error', 'file': f.name,
                           'msg': f'子文档 {f.name} 未使用两位数字前缀(如 01_xxx.md)'})

    # 7. 禁语义前缀(含 00_索引.md 外的全部内容文档)
    check_semantic_prefix(sub_docs, issues)

    # 8. 碎片子文档检测(行数 < MIN_SUB_DOC_LINES,排除 00_/总览/索引)
    fragment_files = []
    for f in sub_docs:
        if is_overview_or_index(f.name):
            continue
        n_lines = count_lines(f)
        if n_lines < MIN_SUB_DOC_LINES:
            fragment_files.append({'file': f.name, 'lines': n_lines})
            issues.append({'dim': '碎片子文档', 'level': 'error', 'file': f.name, 'lines': n_lines,
                           'msg': f'子文档 {f.name} 仅 {n_lines} 行(< {MIN_SUB_DOC_LINES} 行),属碎片文档,'
                                  f'应合并到相邻子文档或补充内容至 ≥ {MIN_SUB_DOC_LINES} 行'})
    summary['fragment_sub_docs'] = fragment_files

    # 8. 序号连续性检测(提取所有序号,检查是否连续)
    # ⚠️ 补：本 SKILL 的 SKILL.md 明文要求「后续序号接上一文档自动累进、
    # **不跳号**、不嵌套二级序号」，而这条判据此前只有 ux/architect 两份副本实现，
    # planner 副本整段缺失 —— 属能力回退（同一 fixture：ux exit 1、planner exit 0）。
    # SKILL 独立性允许三份副本各自演进，但不允许自家规范写了、自家硬门不查。
    seq_nums = []
    # ⚠️ 本副本的变量名是 `sub_docs`（不是 ux 副本里的 `all_docs`）—— 从姊妹脚本搬判据时
    # 必须核对变量名，否则就是又一次「新增分支引用未定义变量」（本仓库已连续踩 4 次）。
    for f in sub_docs:
        m = SUB_DOC_PATTERN.match(f.name)
        if m:
            seq_nums.append((int(m.group(1)), f.name))
    seq_nums.sort()

    # 检查序号连续性(允许保留整十号和98_/99_)
    for i in range(len(seq_nums) - 1):
        cur_num, cur_file = seq_nums[i]
        next_num, next_file = seq_nums[i + 1]
        gap = next_num - cur_num
        if gap == 1:
            continue                                  # 连续,OK
        if cur_num % 10 == 0 and gap <= 10:
            continue                                  # 整十号后跳到下一个整十号前,OK
        if cur_num < 98 and next_num >= 98:
            continue                                  # 跳到保留序号 98_/99_,OK
        issues.append({'dim': '序号连续性', 'level': 'error',
                       'file': f'{cur_file} → {next_file}',
                       'msg': f'序号从 {cur_num:02d}_ 跳到 {next_num:02d}_(跳 {gap}),'
                              f'违反序号连续累进原则(允许保留整十号和98_/99_)'})

    # 2-3. 主文档引用 vs 实际文件
    if main_doc:
        referenced = extract_referenced_files(main_doc)
        actual = {f.name for f in sub_docs}
        missing_in_dir = referenced - actual - {main_doc.name}
        # 仅保留疑似子文档的引用(有 .md 后缀且看起来像子文档名)
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
        task_map: dict[str, list[str]] = {}
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
        enum_map: dict[str, list[str]] = {}
        for f in sub_docs:
            for name in extract_enum_names(f):
                enum_map.setdefault(name, []).append(f.name)
        for name, files in enum_map.items():
            if len(files) > 1:
                issues.append({'dim': '字典枚举名唯一性', 'level': 'error', 'name': name,
                               'msg': f'字典/枚举 {name} 在多个文件中重复定义: {files}'})
        summary['enum_count'] = len(enum_map)

    status = 'pass' if not any(i['level'] == 'error' for i in issues) else 'fail'
    result = {'status': status, 'summary': summary, 'issues': issues}

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f'状态: {"✅ PASS" if status == "pass" else "❌ FAIL"}  '
              f'(主锚: {summary["main_doc"]}, 内容文档: {summary["sub_docs"]})')
        for i in issues:
            icon = '❌' if i['level'] == 'error' else '⚠️'
            print(f'  {icon} [{i["dim"]}] {i["msg"]}')
        if not issues:
            print('  无问题')

    return 0 if status == 'pass' else 1


if __name__ == '__main__':
    sys.exit(main())
