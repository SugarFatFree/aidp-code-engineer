#!/usr/bin/env python3
"""
check_doc_split.py — 通用多文件拆分一致性检查

检查项:
  1. 子文档文件名是否带两位数字序号前缀 (00_、01_、...)
  2. 主锚识别:现行规范要求专职索引 `00_索引.md`(内容主文档从 01_ 起);
     历史锚 `00_*-总览.md` / `00_*-主文档.md` / 裸 `00_<语义名>.md` 仍 grandfather 识别、不报错
  3. 主文档"文档结构与拆分说明"表中列出的子文档是否都存在
  4. 目录下是否有主文档未列出的子文档(反向检查)
  5. (可选) Task 编号在主+子文档间全局唯一
  6. (可选) 字典/枚举编码在多文件中全局唯一
  7. (硬核) 严禁"补充"/"追加"/"附加"/"扩展"等语义前缀/中缀
     - 行首裸「补充-…」(无序号)= error;
     - `NN_补充-…` / `NN_追加-…` 等**中缀**= warn(静态脚本无法区分新旧,历史存量 grandfather,不硬失败)
  8. (硬核) 序号连续性:除保留整十号(10_/20_/30_...)及保留序号(98_/99_)外,序号不跳号
  9. 碎片子文档检测:子文档(排除 00_ 主文档/总览/索引)行数 < 100 行**且** < 4KB 视为碎片,不通过(密集短文档按字节豁免)
     (对应 ux-logic-extractor 维度 9「子文档 ≥ 100 行,碎片即不通过」)

AIDP 文档命名范式(现行规范):
  - `00_` 槽位恒给专职索引 `00_索引.md`;内容主文档一律从 `01_` 起。
  - 即便只有一份内容文档,也应产出 `00_索引.md` + `01_<语义名>.md`(≥2 文件)。
  - 历史存量(裸 `00_<语义名>.md` / `00_*-总览.md` / `NN_补充-…`)grandfather 识别放行、给 warn 提示可升级、**绝不 exit 非 0**。

用法:
  python check_doc_split.py <文档目录>
  python check_doc_split.py <文档目录> --json
  python check_doc_split.py <文档目录> --check-tasks         # 执行计划场景
  python check_doc_split.py <文档目录> --check-dict-enums    # 详细设计场景

退出码:
  0 = 全部通过 / 单文件模式(无须拆分检查)
  1 = 存在不通过项
  2 = 用法错误或目录不存在
"""

from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path

# 主锚识别:
#   现行规范主锚 = 专职索引 `00_索引.md`(优先/推荐);
#   历史锚 grandfather:`00_*总览/主文档.md`、裸 `00_<语义名>.md`(如 00_PRD-{项目名}.md)。
# 只要目录里能识别出任一「00_ 主锚」即视为找到主文档,不误报缺主文档。
MAIN_DOC_INDEX_PATTERN = re.compile(r'^00_索引\.md$')          # 现行规范专职索引(首选)
MAIN_DOC_LEGACY_PATTERNS = [
    re.compile(r'^00_.*(总览|主文档|索引)\.md$'),               # 历史「总览/主文档」锚
]
MAIN_DOC_FALLBACK_PATTERN = re.compile(r'^00_.*\.md$')         # 裸 00_<语义名>.md 历史锚(grandfather)
SUB_DOC_PATTERN = re.compile(r'^(\d{2})_[^/]+\.md$')
TASK_ID_PATTERN = re.compile(r'^#{1,3}\s*Task\s+(\d+\.\d+)\s*[:：]', re.MULTILINE)
ENUM_NAME_PATTERN = re.compile(r'^#{2,4}\s+([A-Za-z][A-Za-z0-9_]+)\s*[（(]?(枚举|字典|Enum|Dict)?', re.MULTILINE)

# 7a. 无序号裸语义前缀(行首「补充-…」等,无两位序号)= error
SEMANTIC_PREFIX_PATTERN = re.compile(r'^(补充|追加|附加|扩展|新增|extra|append|supplement|additional)[-_]', re.IGNORECASE)
# 7b. 带序号的语义中缀(`NN_补充-…` / `NN_追加-…` 等)= warn(历史 grandfather,不硬失败)
SEMANTIC_INFIX_PATTERN = re.compile(r'^\d{2}_(补充|追加|附加|扩展|新增)[-_]')

# 9. 碎片子文档检测:子文档行数下限(< 此值视为碎片,不通过)
MIN_SUB_DOC_LINES = 100
# 碎片检测豁免:00_ 主文档/总览/索引 + 98_/99_ 等固定编号聚合清单(跨系统验证清单/待澄清问题清单,常合法地短)
OVERVIEW_INDEX_PATTERN = re.compile(r'^00_|^98_|^99_|总览|索引|index|待澄清|跨系统', re.IGNORECASE)


def find_main_doc(doc_dir: Path) -> tuple[Path | None, str]:
    """返回 (主锚文件, 主锚类型)。
    类型: 'index'  = 现行规范专职索引 00_索引.md(首选)
          'legacy' = 历史 00_*总览/主文档/裸 00_<语义名>.md(grandfather,允许但可 warn)
          'none'   = 未找到任何 00_ 主锚
    """
    files = [f for f in doc_dir.iterdir() if f.is_file() and f.suffix == '.md']
    # 首选:现行规范专职索引 00_索引.md
    for f in files:
        if MAIN_DOC_INDEX_PATTERN.match(f.name):
            return f, 'index'
    # 历史锚:00_*总览/主文档/索引.md
    for f in sorted(files):
        if any(p.match(f.name) for p in MAIN_DOC_LEGACY_PATTERNS):
            return f, 'legacy'
    # 兜底:裸 00_<语义名>.md(如 00_PRD-{项目名}.md)= 历史锚
    for f in sorted(files):
        if MAIN_DOC_FALLBACK_PATTERN.match(f.name):
            return f, 'legacy'
    return None, 'none'


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


def main() -> int:
    parser = argparse.ArgumentParser(description='多文件拆分一致性检查')
    parser.add_argument('doc_dir', help='文档目录(包含主文档和子文档)')
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
    summary = {'total_md': len(md_files), 'main_doc': None, 'sub_docs': 0, 'mode': 'single'}

    if len(md_files) <= 1:
        # 历史裸单文件(无前缀单文件 / 裸 00_<语义名>.md / 00_*-总览.md 单独一目录):
        # 现行规范要求 00_索引.md + 01_<语义名>.md(≥2 文件),但历史裸单文件 grandfather 放行、
        # 给 warn 提示可升级,绝不 exit 非 0。
        lone = md_files[0].name if md_files else '(空目录)'
        warn_issues = [{
            'dim': '命名范式(可升级)', 'level': 'warn', 'file': lone,
            'msg': f'历史裸单文件 {lone}:新 AIDP 范式建议产出 00_索引.md + 01_<语义名>.md(≥2 文件),'
                   f'专职索引占 00_ 槽位、内容主文档从 01_ 起。此为 grandfather 放行,不判不通过。'
        }] if md_files else []
        result = {'status': 'pass', 'mode': 'single',
                  'message': '单文件模式,历史裸单文件 grandfather 放行(可升级为 00_索引.md+01_)',
                  'summary': summary, 'issues': warn_issues}
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print('✅ 单文件模式(历史裸单文件 grandfather 放行,不判不通过)')
            for i in warn_issues:
                print(f'  ⚠️ [{i["dim"]}] {i["msg"]}')
        return 0

    summary['mode'] = 'multi'
    main_doc, main_kind = find_main_doc(doc_dir)
    summary['main_anchor_kind'] = main_kind
    if not main_doc:
        issues.append({'dim': '主文档', 'level': 'error',
                       'msg': f'未找到 00_ 前缀主锚(现行规范应为专职索引 00_索引.md,目录: {doc_dir})'})
    else:
        summary['main_doc'] = main_doc.name
        if main_kind == 'legacy':
            # 历史主锚(00_*总览/主文档 或 裸 00_<语义名>.md)grandfather 放行,仅 warn 提示可升级
            issues.append({'dim': '命名范式(可升级)', 'level': 'warn', 'file': main_doc.name,
                           'msg': f'主锚 {main_doc.name} 为历史命名;新 AIDP 范式建议改用专职索引 00_索引.md,'
                                  f'内容主文档从 01_<语义名>.md 起。grandfather 放行,不判不通过。'})

    sub_docs = collect_sub_docs(doc_dir, exclude=main_doc)
    summary['sub_docs'] = len(sub_docs)

    # 1. 文件名序号前缀
    for f in sub_docs:
        if not SUB_DOC_PATTERN.match(f.name):
            issues.append({'dim': '文件名序号', 'level': 'error', 'file': f.name,
                           'msg': f'子文档 {f.name} 未使用两位数字前缀(如 01_xxx.md)'})

    # 9. 碎片子文档检测(行数 < MIN_SUB_DOC_LINES,排除 00_/总览/索引)
    fragment_files = []
    for f in sub_docs:
        if is_overview_or_index(f.name):
            continue
        n_lines = count_lines(f)
        # 文档承诺"≥100 行 或 ≥4KB",密集短文档(如紧凑表格)按字节豁免,避免误判碎片
        try:
            file_size = f.stat().st_size
        except OSError:
            file_size = 0
        if n_lines < MIN_SUB_DOC_LINES and file_size < 4096:
            fragment_files.append({'file': f.name, 'lines': n_lines})
            issues.append({'dim': '碎片子文档', 'level': 'error', 'file': f.name, 'lines': n_lines,
                           'msg': f'子文档 {f.name} 仅 {n_lines} 行(< {MIN_SUB_DOC_LINES} 行),属碎片文档,'
                                  f'应合并到相邻子文档或补充内容至 ≥ {MIN_SUB_DOC_LINES} 行'})
    summary['fragment_sub_docs'] = fragment_files

    # 7. 语义前缀/中缀违规检测
    #   7a. 行首无序号裸语义前缀(如 `补充-订单域.md`)= error
    #   7b. 带序号语义中缀(如 `03_补充-订单域.md`)= warn(历史 grandfather,静态脚本无法区分新旧,不硬失败)
    all_docs = sub_docs + ([main_doc] if main_doc else [])
    for f in all_docs:
        if SEMANTIC_PREFIX_PATTERN.search(f.name):
            issues.append({'dim': '语义前缀违规', 'level': 'error', 'file': f.name,
                           'msg': f'文件名 {f.name} 无序号且用了语义前缀(补充/追加/附加/扩展等),必须改为「两位序号+业务名」(如 07_订单域字典枚举.md)'})
        elif SEMANTIC_INFIX_PATTERN.match(f.name):
            issues.append({'dim': '语义中缀(可升级)', 'level': 'warn', 'file': f.name,
                           'msg': f'文件名 {f.name} 带序号但含语义中缀(补充/追加/附加/扩展),现行规范应直接用「序号+业务名」(如 03_订单域.md),补充身份靠 00_索引.md 登记;历史存量 grandfather,不判不通过。'})

    # 8. 序号连续性检测(提取所有序号,检查是否连续)
    seq_nums = []
    for f in all_docs:
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
              f'(主文档: {summary["main_doc"]}, 子文档: {summary["sub_docs"]})')
        for i in issues:
            icon = '❌' if i['level'] == 'error' else '⚠️'
            print(f'  {icon} [{i["dim"]}] {i["msg"]}')
        if not issues:
            print('  无问题')

    return 0 if status == 'pass' else 1


if __name__ == '__main__':
    sys.exit(main())
