#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tasks.md 进度状态机管理(断点续跑内核)。

4 态状态机:[ ] 待执行 / [>] 执行中 / [√] 已完成(pass) / [!] 阻塞或失败(fail/block)。
tasks.md 按 `## {模块名}` 分组,条目形如 `- [ ] TC-001 - 用例名称`。

子命令:
  init   从用例文档解析 SUITE/TC 生成 tasks.md(全 [ ])
  update 改某用例状态(--id TC-001 --state done|running|block|todo)
  scan   统计各状态数量;存在 [ ]/[>] 残留 → 退出码 1(供质量维度 3)
  resume 列出所有待续跑项([ ] 与 [>]),供断点续跑

build/round 作用域(重要):
  * 新 build(上一 build 缺陷经外层 bugfix 修复后的新回归轮)一律用 `init`
    重建全新 tasks.md(全部回 [ ])并全量重跑;
  * `resume` 仅用于「同一 build 内」某轮执行被中断后的续跑,已 [√] 跳过;
  * 绝不用 `resume` 跨 build 沿用上一 build 的 [√]、绝不只复跑被修用例
    (只复验被修用例会漏同源缺陷)。

仅标准库,支持 --json。退出码:0 正常/无残留, 1 有残留(scan), 2 输入错误。
"""
import argparse
import json
import os
import re
import stat
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

STATE_MARK = {'todo': ' ', 'running': '>', 'done': '√', 'block': '!'}
MARK_STATE = {' ': 'todo', '>': 'running', '√': 'done', 'x': 'done', '!': 'block'}

# 套件 / 用例标题识别 —— 口径单一信源见 `references/usecase-format.md` §二「标题形态契约」。
# ⚠️ 只能比上游 dev-manual-testcase 更宽、不得更窄:收窄的后果不是报错而是**静默漏跑**
#    (用例扫不到 = 整条不进 tasks.md)。改这两条正则前先跑 `tasks_state.py selftest`。
SUITE_RE = re.compile(
    r'^#{2,4}\s*(?:测试)?套件\s+((?:SUITE|TS)-[\w\-]+)\s*[:：]?\s*(.*)$', re.MULTILINE)
CASE_RE = re.compile(
    r'^#{3,6}\s*(?:用例\s+)?(TC-[\w\-]+)\s*[:：]?\s*(.*)$', re.MULTILINE)
# 用例四要素表里的「优先级」行(形态兼容:`| 优先级 | P0 |`、`优先级:P0`、`优先级：P0`)
PRIORITY_RE = re.compile(r'优先级[^\w]{0,6}(P[0-2])')
# 选集(执行深度维度)。⚠️ **刻意不引入 smoke/regression/release 三值新标签**——
# 上游 dev-manual-testcase 的 test-design-methodology.md 已把 **P0 定义为「核心功能正向(冒烟)」**,
# `[回归]` 标记也早已存在并透传为 `is_regression`。再造一套平行标签只会让同一件事有两个信源、
# 互相漂移。故深度维度**直接复用既有数据**,执行侧只做过滤。
SELECT_MODES = {
    'all': '全部用例(默认)',
    'smoke': '冒烟:优先级 P0(上游定义 P0 = 核心功能正向(冒烟))',
    'regression': '回归:带 `[回归]` 标记的用例',
}

# tasks.md 条目:- [ ] TC-001 - 名称
ITEM_RE = re.compile(r'^\s*-\s*\[([ >√x!])\]\s*(TC-[\w\-]+)\s*-\s*(.*)$')
GROUP_RE = re.compile(r'^##\s+(.*)$')


# 写锁由**内核**持有,不靠 mtime 猜「持有者是不是死了」。
# ⚠️⚠️ 这里曾用「锁文件 + mtime 判陈旧 + rename 接管」,已实测出**双持有者**:
#    判陈旧(lstat)与搬走(rename)不是原子的 —— 两步之间若另一进程已接管并建了新鲜锁,
#    搬走的就是那把**活锁**;在「搬走」与「搬回」之间锁路径是空的,第三个进程能直接
#    O_EXCL 进来,两个持有者同时读改写 tasks.md(丢更新),随后「原样放回」又覆盖后来者的锁。
#    ⛔ 任何基于时间戳的陈旧判定都无法做到原子,别再走回那条路。
# 内核锁的性质正好补上这个缺口:持有者进程无论正常退出还是被 SIGKILL/OOM 带走,
# 内核都会立即释放,故**不需要任何陈旧计时器**,崩溃后下一次 checkpoint 立刻能拿到锁。
try:                                    # POSIX(Linux / macOS)
    import fcntl

    def _try_acquire(fd):
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def _release(fd):
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
except ImportError:                     # Windows
    import msvcrt

    def _try_acquire(fd):
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False

    def _release(fd):
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            pass


@contextmanager
def _locked_tasks(path):
    """对 tasks.md 取跨进程独占写锁。

    ⚠️ 锁文件**故意不删**:删除会让「已打开该 inode 并正在等锁的进程」与
       「刚新建同名文件的进程」锁在两个不同 inode 上 —— 又是一条无锁并发写的路。
       残留的是一个 0 字节隐藏文件,代价远小于丢更新。
    """
    lock = path.with_name('.' + path.name + '.lock')
    fd = os.open(str(lock), os.O_RDWR | os.O_CREAT, 0o600)
    deadline = time.monotonic() + 5
    try:
        while not _try_acquire(fd):
            if time.monotonic() >= deadline:
                raise OSError(f'tasks.md 写锁等待超时:{lock}')
            time.sleep(0.05)
    except BaseException:
        os.close(fd)
        raise
    try:
        yield
    finally:
        _release(fd)
        os.close(fd)


def _default_file_mode():
    """按当前 umask 算出普通文件的默认权限(与 write_text 的行为一致)。

    ⚠️ 读 umask 只能靠「设了再设回去」,中间有极窄窗口;本脚本是单线程 CLI,
       可接受。⛔ 别把它搬进多线程场景。
    """
    mask = os.umask(0)
    os.umask(mask)
    return 0o666 & ~mask


def _atomic_write(path, content):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
                mode='w', encoding='utf-8', dir=str(path.parent),
                prefix='.' + path.name + '.', suffix='.tmp', delete=False) as output:
            temporary = Path(output.name)
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        if path.exists():
            os.chmod(str(temporary), stat.S_IMODE(path.stat().st_mode))
        else:
            # 新建时没有旧 mode 可继承,而 NamedTemporaryFile 恒给 0600。
            # 旧的 write_text 走 umask,不补这一步就是静默收紧权限:
            # 团队/CI 下同机另一账号读同一份 tasks.md 会被拒。
            os.chmod(str(temporary), _default_file_mode())
        os.replace(str(temporary), str(path))
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _resolve_input(args, name, usage):
    """取「位置参数 or 同名 --具名参数」。

    ⚠️ 这不是可有可无的糖:下游实测反馈,执行子 Agent 按语义直觉写成
    `init --usecase X --round-dir Y` 触发 `unrecognized arguments` 而空转一轮——
    位置参数写法只出现在 argparse 的 epilog(只有主动 `--help` 才看得到)。
    故 **每个子命令的主入参都同时接受位置与具名两种写法**,并在缺参时打印用法而非裸报错。
    """
    val = getattr(args, name, None) or getattr(args, name + '_opt', None)
    if not val:
        _err(args, f'缺少参数 {name}。用法:{usage}')
        return None
    return val


def cmd_init(args):
    source = _resolve_input(args, 'source', 'tasks_state.py init <用例文件或目录> -o <round目录>/tasks.md')
    if not source:
        return 2
    src = Path(source)
    if not src.exists():
        return _err(args, f'用例源不存在:{src}')
    texts = []
    # 跳过非用例文档:00_索引 / 01_研发自测方案 / 98_跨系统清单 / 99_待澄清 + 测试环境与账号 配置
    # + 「总览」索引文档(多文件模式下套件在 03_ 起的模块分册里,总览只有表格清单)。
    # (兼容历史旧锚:旧布局 00_=研发自测方案 也以 00_ 前缀被跳过。)
    # ⚠️ 排除口径对齐上游 5 个脚本的同名契约;CASE_RE 放宽后(「用例」二字与冒号均可省)
    # 容错余量变小,口径分歧更易变成实害。仅作用于**目录**模式,直接传单文件永远解析。
    def _is_case_src(name):
        if name.startswith(('00_', '98_', '99_')):
            return False
        if '研发自测方案' in name or '测试环境与账号' in name or '总览' in name:
            return False
        return True
    files = [src] if src.is_file() else sorted(
        f for f in src.rglob('*.md') if _is_case_src(f.name))
    for f in files:
        texts.append(f.read_text(encoding='utf-8', errors='replace'))
    text = '\n'.join(texts)

    # 按套件分组收集用例(用出现顺序,套件标题作分组)
    tokens = []
    for m in SUITE_RE.finditer(text):
        tokens.append((m.start(), 'suite', m.group(1), m.group(2).strip()))
    for m in CASE_RE.finditer(text):
        tokens.append((m.start(), 'case', m.group(1), m.group(2).strip()))
    tokens.sort()

    # 每个 token 的正文范围 = 本 token 起点 → 下一个 token 起点(末尾到文末),
    # 用于就地解析该用例的优先级(四要素表在标题之后、下一条用例之前)
    bounds = [tokens[i + 1][0] if i + 1 < len(tokens) else len(text) for i in range(len(tokens))]

    select = getattr(args, 'select', None) or 'all'
    groups = []  # [(suite_label, [(tc_id, name)])]
    cur = None
    skipped = 0
    unlabeled_kept = 0
    for i, (start, kind, ident, label) in enumerate(tokens):
        if kind == 'suite':
            cur = (f'{ident} {label}'.strip(), [])
            groups.append(cur)
            continue
        if select != 'all':
            body = text[start:bounds[i]]
            if select == 'smoke':
                m = PRIORITY_RE.search(body)
                if m is None:
                    # ⚠️ 解析不到优先级 → **保留**(宁可多跑,不可漏测),并在输出如实报数。
                    #    静默丢弃未标注用例会让 `--select smoke` 的覆盖面无声缩水。
                    unlabeled_kept += 1
                elif m.group(1) != 'P0':
                    skipped += 1
                    continue
            elif select == 'regression':
                if '[回归]' not in label and '[回归]' not in body:
                    skipped += 1
                    continue
        if cur is None:
            cur = ('未分组', [])
            groups.append(cur)
        cur[1].append((ident, label))

    total = sum(len(g[1]) for g in groups)
    lines = ['# 执行进度 tasks.md', '',
             '> 状态:`[ ]`待执行 / `[>]`执行中 / `[√]`已完成(pass) / `[!]`阻塞或失败', '']
    # ★选集留痕(硬要求):不写这行,子集 tasks.md 与全量版**逐字同形** ——
    #   `scan` 对子集恒报「无残留」、`gen_report` 的通过率与「P0 100%」准则在子集上计算,
    #   报告读者根本看不出本轮只跑了一部分。留痕行让「跑的是子集」这件事全程可见。
    #   (`_parse_items` 只认 `## ` 与 `- [x] TC-… - …` 条目行,引用块不影响解析)
    if select != 'all':
        note = f'> ⚠️ **本轮为子集**:选集 `{select}` — {SELECT_MODES[select]};已过滤 {skipped} 条'
        note += f',{unlabeled_kept} 条未标注优先级已保留' if unlabeled_kept else ''
        lines += [note,
                  '> 通过率与「P0=100%」等通过准则**仅对该子集成立**,不代表全量结论;'
                  '**新 build 回归轮禁用选集**(须全量重跑,见 execution-methodology 第五节跨 build 硬边界)。',
                  '']
    for label, cases in groups:
        if not cases:
            continue
        lines.append(f'## {label}')
        for tc, name in cases:
            lines.append(f'- [ ] {tc} - {name}')
        lines.append('')
    content = '\n'.join(lines)

    if args.output:
        output_path = Path(args.output)
        try:
            with _locked_tasks(output_path):
                _atomic_write(output_path, content)
        except OSError as exc:
            return _err(args, f'tasks.md 初始化失败:{exc}')
    result = {'suites': len([g for g in groups if g[1]]), 'cases': total,
              'output': args.output or None, 'select': select,
              'skipped_by_select': skipped, 'unlabeled_kept': unlabeled_kept}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if args.output:
            extra = ''
            if select != 'all':
                extra = f'(选集 {select},已过滤 {skipped} 条'
                extra += f';{unlabeled_kept} 条未标注优先级已保留)' if unlabeled_kept else ')'
            print(f'✅ 生成 {args.output}:{result["suites"]} 模块 / {total} 用例{extra}')
        else:
            # 选集摘要打 **stderr**:stdout 是 tasks.md 正文(可能被重定向进文件),
            # 摘要混进去会污染产物;但静默又会让「跑的是子集」这件事在 stdout 模式下完全看不见。
            if select != 'all':
                print(f'(选集 {select}:已过滤 {skipped} 条'
                      + (f';{unlabeled_kept} 条未标注优先级已保留)' if unlabeled_kept else ')'),
                      file=sys.stderr)
            print(content)
    return 0


def _parse_items(path):
    items = []  # (group, mark, tc_id, name, lineno)
    group = None
    for i, line in enumerate(path.read_text(encoding='utf-8', errors='replace').splitlines()):
        gm = GROUP_RE.match(line)
        if gm:
            group = gm.group(1).strip()
            continue
        im = ITEM_RE.match(line)
        if im:
            items.append({'group': group, 'mark': im.group(1),
                          'state': MARK_STATE.get(im.group(1), 'todo'),
                          'id': im.group(2), 'name': im.group(3).strip(), 'line': i})
    return items


def cmd_update(args):
    tasks = _resolve_input(args, 'tasks', 'tasks_state.py update <tasks.md> --id TC-001 --state done')
    if not tasks:
        return 2
    path = Path(tasks)
    if not path.is_file():
        return _err(args, f'tasks.md 不存在:{path}')
    if args.state not in STATE_MARK:
        return _err(args, f'未知状态:{args.state}(可选 {list(STATE_MARK)})')
    mark = STATE_MARK[args.state]
    changed = 0
    ids = set(args.id)
    try:
        with _locked_tasks(path):
            lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
            for idx, line in enumerate(lines):
                im = ITEM_RE.match(line)
                if im and im.group(2) in ids:
                    lines[idx] = re.sub(r'\[([ >√x!])\]', f'[{mark}]', line, count=1)
                    changed += 1
            _atomic_write(path, '\n'.join(lines) + '\n')
    except OSError as exc:
        return _err(args, f'tasks.md 更新失败:{exc}')
    result = {'updated': changed, 'ids': list(ids), 'state': args.state}
    print(json.dumps(result, ensure_ascii=False) if args.json
          else f'✅ 更新 {changed} 条为 [{mark}]')
    return 0


def cmd_scan(args):
    tasks = _resolve_input(args, 'tasks', 'tasks_state.py scan <tasks.md>')
    if not tasks:
        return 2
    path = Path(tasks)
    if not path.is_file():
        return _err(args, f'tasks.md 不存在:{path}')
    items = _parse_items(path)
    counts = {'todo': 0, 'running': 0, 'done': 0, 'block': 0}
    for it in items:
        counts[it['state']] += 1
    residual = counts['todo'] + counts['running']
    passed = residual == 0
    result = {'total': len(items), 'counts': counts, 'residual': residual,
              'passed': passed}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"用例 {len(items)} | 待执行 {counts['todo']} / 执行中 {counts['running']} "
              f"/ 已完成 {counts['done']} / 阻塞 {counts['block']}")
        print('✅ 无残留' if passed else f'❌ 存在 {residual} 条未落定([ ]/[>])')
    return 0 if passed else 1


def cmd_resume(args):
    tasks = _resolve_input(args, 'tasks', 'tasks_state.py resume <tasks.md>')
    if not tasks:
        return 2
    path = Path(tasks)
    if not path.is_file():
        return _err(args, f'tasks.md 不存在:{path}')
    items = _parse_items(path)
    pending = [it for it in items if it['state'] in ('todo', 'running')]
    result = {'pending': [{'id': it['id'], 'name': it['name'],
                           'group': it['group'], 'state': it['state']} for it in pending],
              'count': len(pending)}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if not pending:
            print('✅ 无待续跑项,全部已落定')
        else:
            print(f'待续跑 {len(pending)} 条:')
            for it in pending:
                print(f"  [{it['mark']}] {it['id']} - {it['name']}  ({it['group']})")
    return 0


# 标题形态自检样本 —— 契约见 `references/usecase-format.md` §二「标题形态契约」。
# 上游 dev-manual-testcase 的 5 个套件解析脚本能认的形态,本端**必须全部能认**。
# 这里做成可执行断言,是因为「解析端不得收窄」此前只是注释里的一句话,后人改窄了没有任何机制拦——
# 而收窄的表现是**静默漏跑**(用例不进 tasks.md),不会报错、跑完还是绿的。
_SELFTEST_SUITES = [
    ('## 套件 SUITE-01: 标题', 'SUITE-01'),
    ('### 套件 SUITE-USER: 标题', 'SUITE-USER'),
    ('#### 套件 SUITE-INC-01: 标题', 'SUITE-INC-01'),
    ('### 测试套件 SUITE-02: 标题', 'SUITE-02'),
    ('### 套件 TS-001: 标题', 'TS-001'),
    ('### 测试套件 TS-001: 标题', 'TS-001'),
    ('## 测试套件 TS-003：全角冒号标题', 'TS-003'),
    ('### 套件 SUITE-03 无冒号标题', 'SUITE-03'),
]
_SELFTEST_CASES = [
    ('#### 用例 TC-USER-001: 标题', 'TC-USER-001'),
    ('##### 用例 TC-USER-002：全角冒号', 'TC-USER-002'),
    ('#### TC-USER-003: 省略「用例」二字', 'TC-USER-003'),
    ('###### TC-A-1 无冒号', 'TC-A-1'),
]
# 优先级形态自检 —— `--select smoke` 靠 PRIORITY_RE 识别 P0,与上面两条正则同性质:
# **收窄即静默漏跑**(P0 用例没进冒烟集,不报错、跑完还是绿的)。故一并做成硬断言。
# 期望 None = 该形态**不应**被识别(防放宽过头,把别处的"优先级"三个字误判成本条用例的优先级)。
_SELFTEST_PRIORITY = [
    ('| 优先级 | P0 |', 'P0'),              # 四要素表(最常见)
    ('| 优先级 | `P1` |', 'P1'),            # 值带反引号
    ('- 优先级:P2', 'P2'),                  # 列表 + 全角冒号
    ('- 优先级: P0', 'P0'),                 # 列表 + 半角冒号 + 空格
    ('> **优先级**: P1', 'P1'),             # 引用 + 加粗
    ('优先级P0', 'P0'),                      # 无分隔
    ('本用例优先处理级别较高', None),          # 近似词不得误命中
]


def _priority_of(text):
    m = PRIORITY_RE.search(text)
    return m.group(1) if m else None


def cmd_selftest(args):
    """校验 SUITE_RE / CASE_RE / PRIORITY_RE 未被收窄(收窄 = 静默漏跑,故做成硬断言)。"""
    failures = []
    for text, want in _SELFTEST_SUITES:
        m = SUITE_RE.match(text)
        if not m or m.group(1) != want:
            failures.append({'kind': 'suite', 'input': text, 'expect': want,
                             'got': m.group(1) if m else None})
    for text, want in _SELFTEST_CASES:
        m = CASE_RE.match(text)
        if not m or m.group(1) != want:
            failures.append({'kind': 'case', 'input': text, 'expect': want,
                             'got': m.group(1) if m else None})
    for text, want in _SELFTEST_PRIORITY:
        got = _priority_of(text)
        if got != want:
            failures.append({'kind': 'priority', 'input': text, 'expect': want, 'got': got})
    total = len(_SELFTEST_SUITES) + len(_SELFTEST_CASES) + len(_SELFTEST_PRIORITY)
    if args.json:
        print(json.dumps({'passed': not failures, 'total': total,
                          'failures': failures}, ensure_ascii=False, indent=2))
    elif failures:
        print(f'❌ 形态自检不通过:{len(failures)}/{total} 条未识别'
              f'(解析端被收窄 → 会静默漏跑,契约见 references/usecase-format.md §二)\n')
        for f in failures:
            print(f"  [{f['kind']}] {f['input']}\n      期望 {f['expect']},实得 {f['got']}")
    else:
        print(f'✅ 形态自检通过:{total}/{total} 条'
              f'(套件/用例标题 {len(_SELFTEST_SUITES) + len(_SELFTEST_CASES)} 条 + '
              f'--select 优先级 {len(_SELFTEST_PRIORITY)} 条)')
    return 1 if failures else 0


def _err(args, msg):
    print(json.dumps({'error': msg}, ensure_ascii=False) if args.json else msg)
    return 2


def main():
    # --json 同时挂到顶层与各子命令(parent),故 `--json init ...` 与 `... scan --json` 均可
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--json', action='store_true', help='JSON 输出')

    ap = argparse.ArgumentParser(
        description='tasks.md 进度状态机管理(断点续跑内核)。4 态:[ ]待执行 / [>]执行中 / '
                    '[√]已完成(pass) / [!]阻塞或失败(fail/block)。子命令 init/update/scan/resume。',
        epilog='示例:\n'
               '  python3 tasks_state.py init 02_全量自测用例.md -o tasks.md   # 解析用例建 tasks.md\n'
               '  python3 tasks_state.py update tasks.md --id TC-001 TC-002 --state running  # 批量改状态\n'
               '  python3 tasks_state.py scan tasks.md --json                 # 统计各态,有残留退出码 1\n'
               '  python3 tasks_state.py resume tasks.md --json               # 列出待续跑项\n'
               '\n'
               '主入参位置/具名两种写法等价(缺参时打印用法,不裸报 unrecognized arguments):\n'
               '  python3 tasks_state.py init --source 用例目录/ -o round-1/tasks.md\n'
               '  python3 tasks_state.py scan --tasks round-1/tasks.md',
        formatter_class=argparse.RawDescriptionHelpFormatter, parents=[common])
    sub = ap.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('init', parents=[common],
                       help='从用例文档解析 SUITE/TC 生成 tasks.md(全 [ ]);新 build 全量重跑用它重建',
                       description='从用例文件或目录解析 SUITE/TC,按模块分组生成 tasks.md(全 [ ] 初态)。'
                                   '新 build(外层 bugfix 修复后的新回归轮)用本命令重建全新 tasks.md、全量重跑,不沿用旧 build 的 [√]。')
    p.add_argument('source', nargs='?',
                   help='用例文件或目录(位置参数;单文件或多文件目录均可,自动跳过 00_索引/01_研发自测方案/99_待澄清等非用例文件)')
    p.add_argument('--source', dest='source_opt',
                   help='与位置参数 source 等价的具名写法(二选一即可)')
    p.add_argument('-o', '--output', help='输出 tasks.md 路径(不给则打印到 stdout)')
    p.add_argument('--select', choices=sorted(SELECT_MODES), default='all',
                   help='执行选集(深度维度,复用既有数据不新增标签):'
                        + ';'.join(f'{k}={v}' for k, v in SELECT_MODES.items()))
    p.set_defaults(func=cmd_init)

    p = sub.add_parser('update', parents=[common],
                       help='改某些用例状态(--id ... --state ...)',
                       description='把指定 TC-ID 的条目状态改为 todo/running/done/block。')
    p.add_argument('tasks', nargs='?', help='tasks.md 路径(位置参数;亦可用 --tasks)')
    p.add_argument('--tasks', dest='tasks_opt', help='与位置参数 tasks 等价的具名写法')
    p.add_argument('--id', nargs='+', required=True, help='用例 ID(可多个,空格分隔)')
    p.add_argument('--state', required=True,
                   help='目标状态:todo([ ]) | running([>]) | done([√]) | block([!])')
    p.set_defaults(func=cmd_update)

    p = sub.add_parser('scan', parents=[common],
                       help='统计各状态数量;有 [ ]/[>] 残留则退出码 1(供质量维度 3)',
                       description='统计 tasks.md 各态数量;存在 [ ]/[>] 残留 → 退出码 1。')
    p.add_argument('tasks', nargs='?', help='tasks.md 路径(位置参数;亦可用 --tasks)')
    p.add_argument('--tasks', dest='tasks_opt', help='与位置参数 tasks 等价的具名写法')
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser('resume', parents=[common],
                       help='列出所有待续跑项([ ] 与 [>]),供【同一 build 内】断点续跑',
                       description='列出所有 [ ]/[>] 待续跑项,已 [√] 跳过,不从头重来。'
                                   '作用域仅限「同一 build 内」中断恢复;勿用 resume 跨 build 沿用旧 build 的 [√],'
                                   '跨 build 的新回归轮请用 init 重建 tasks.md 全量重跑。')
    p.add_argument('tasks', nargs='?', help='tasks.md 路径(位置参数;亦可用 --tasks)')
    p.add_argument('--tasks', dest='tasks_opt', help='与位置参数 tasks 等价的具名写法')
    p.set_defaults(func=cmd_resume)

    p = sub.add_parser('selftest', parents=[common],
                       help='校验套件/用例标题形态识别未被收窄(改解析正则后必跑)',
                       description='对 4 种套件前缀组合 + 「用例」二字可省的用例标题各断言一次。'
                                   '任一未识别即 exit 1——解析端收窄的表现是**静默漏跑**'
                                   '(用例不进 tasks.md、报告里连"未执行"都不体现),不会自己报错。'
                                   '契约见 references/usecase-format.md §二「标题形态契约」。')
    p.set_defaults(func=cmd_selftest)

    args = ap.parse_args()
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
