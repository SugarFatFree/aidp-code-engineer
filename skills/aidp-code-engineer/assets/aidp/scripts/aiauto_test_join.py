#!/usr/bin/env python3
"""汇合 build 两路测试终态；真实失败登记 BUG，未核验不冒充通过、不写冻结。

settle --root . --version V --build B --report <AI测试报告 data.js 或 JSON> [--triage <分类 JSON>]
release-state --root . --version V
只消费已按 unit_report_merge 验证的报告，不执行测试、不改历史报告。
缺分类仍记录 PENDING/next_action=classify，CLI exit 2；单测真实 FAIL 保留自动登记。
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

from aidp_paths import runtime_dir
from alloc_id import allocate
from baseline_edit import LockedBaseline
from unit_report_merge import (read_payload, report_ready, overall_status, browser_status,
                               validate_report_units, open_bug_count, unit_has_failure,
                               triage_state)


def _name(value):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', value) or value in ('.', '..'):
        raise ValueError('版本/build 必须是单一路径段')
    return value


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def _atomic_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', dir=path.parent, encoding='utf-8', delete=False) as handle:
        temporary = handle.name
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _unit_bugs(root, version, build, unit):
    if not unit_has_failure(unit):
        return []
    failures = unit.get('failed_cases') or [case for r in unit.get('runs', [])
                if r.get('status') == 'FAIL' for case in r.get('failed_cases', [])] or [unit.get('primary_error') or '完整单测命令失败（用例名未提供）']
    path = root / 'docs/bugfix' / version / f'bugfix-unit-{build}.md'
    if path.is_symlink():
        raise ValueError('BUG 文档不能为符号链接')
    text = path.read_text(encoding='utf-8') if path.exists() else '# 全量单测失败记录\n'
    ids = []
    for failure in failures:
        label = failure if isinstance(failure, str) else json.dumps(failure, ensure_ascii=False, sort_keys=True)
        identity = _hash([build, label])
        marker = re.search(r'<!-- unit-failure:' + identity + r' (BUG-[0-9]+) -->', text)
        if marker:
            ids.append(marker[1])
            continue
        bug_id = allocate(root, 'BUG', 1, 'aiauto-test', version=version, scope='bugs')['ids'][0]
        ids.append(bug_id)
        commands = [r.get('command') for r in unit.get('runs', []) if r.get('status') == 'FAIL']
        run_ids = [r.get('run_id') for r in unit.get('runs', []) if r.get('status') == 'FAIL']
        text += (f'\n<!-- unit-failure:{identity} {bug_id} -->\n## {bug_id} 全量单测不通过\n\n'
                 f'- 状态：待修复\n- 来源：{build} / commit `{unit["commit"]}`\n'
                 f'- 失败用例：{label}\n- run_id：{json.dumps(run_ids, ensure_ascii=False)}\n'
                 f'- 命令：{json.dumps(commands, ensure_ascii=False)}\n'
                 f'- 首要报错：{unit.get("primary_error") or "详见单测原始日志"}\n'
                 '- 修复归口：`/sprint-bugfix`；修复后新 build 复测。\n')
    if ids:
        _atomic_text(path, text)
    return ids


def settle(root, version, build, payload, standalone=False, triage=None):
    root = Path(root).resolve()
    _name(version); _name(build)
    if payload.get('build') != build or 'unitTests' not in payload:
        raise ValueError('必须提供当前 build 的两路汇总报告')
    if triage is not None and triage != payload.get('failureTriage'):
        raise ValueError('--triage 与报告 failureTriage 不一致；必须先重新 emit 报告')
    errors = validate_report_units(payload, 'test')
    if errors or not report_ready(payload):
        raise ValueError('报告尚非有效终态：' + '; '.join(errors))
    status, browser = overall_status(payload), browser_status(payload)
    unit = payload['unitTests']
    routing = triage_state(payload)
    complete = routing['status'] == 'COMPLETE'
    auto_fixable = unit_has_failure(unit) or routing['auto_fixable']
    unverified = (unit['status'] in ('UNVERIFIED', 'TIMEOUT')
                  or browser in ('UNVERIFIED', 'TIMEOUT') or bool(routing['environment'])
                  or (payload.get('browserTests') or {}).get('status') in ('UNVERIFIED', 'TIMEOUT'))
    now = datetime.now(timezone.utc).isoformat()
    digest = _hash({key: payload.get(key) for key in
                    ('summary', 'unitTests', 'browserTests', 'cases', 'defects', 'runtimeErrors', 'failureTriage')})
    baseline = root / 'memory/.sprint-autopilot-baseline.json'
    if standalone:
        with LockedBaseline(str(baseline), write=False) as state:
            original = (state.data.get('versions') or {}).get(version) or {}
            if any(r.get('build') == build for r in original.get('builds', [])):
                raise ValueError('已有 baseline build 不得改走 standalone')
        directory = Path(runtime_dir(root)) / 'build-unit' / version / build
        plan = json.loads((directory / 'plan.json').read_text(encoding='utf-8'))
        deployment = plan.get('deployment') or {}
        if (plan.get('standalone') is not True or deployment.get('verified') is not True
                or not deployment.get('evidence') or plan.get('build') != build
                or plan.get('version') != version or plan.get('commit') != payload.get('commit')
                or deployment.get('commit') != payload.get('commit')):
            raise ValueError('standalone 缺已核验部署身份的冻结计划')
        baseline = directory / 'join.json'
    with LockedBaseline(str(baseline), write=True) as state:
        if standalone:
            state.data.setdefault('versions', {}).setdefault(version, {'current_build': build,
                'builds': [{'build': build, 'push_commit': payload['commit']}]})
        node = (state.data.get('versions') or {}).get(version)
        if not isinstance(node, dict):
            raise ValueError('baseline 缺本版本；独立部署使用已核验计划与 --standalone')
        rows = [r for r in node.get('builds', []) if r.get('build') == build]
        if len(rows) != 1 or rows[0].get('push_commit') != payload.get('commit'):
            raise ValueError('报告 commit 与本 build 部署 commit 不一致')
        row = rows[0]
        pending_cases = node.get('case_ledger_pending', 0)
        if type(pending_cases) is not int or pending_cases < 0:
            raise ValueError('用例台账待执行数非法')
        pending_bugs = open_bug_count(root, version)
        if node.get('current_build') == build:
            report_summary = payload.get('summary') or {}
            if (report_summary.get('pendingCases', 0) != pending_cases
                    or report_summary.get('openBugs', 0) != pending_bugs):
                raise ValueError('报告后用例欠账/待修BUG已变化，须重新 emit 后再汇总')
        existing = row.get('test_join') or {}
        if row.get('ai_report_finalized') and existing.get('digest') != digest:
            raise ValueError('已定稿 build 不得改写测试结论')
        if existing.get('digest') == digest:
            # 已消费的 AFP 不得因恢复/重放同一结果被重新置真；也不改时间/计数。
            return {key: value for key, value in existing.items() if key != 'at'}
        bug_ids = _unit_bugs(root, version, build, unit)
        summary = payload.get('summary') or {}
        result = {'build': build, 'commit': payload['commit'], 'overall_status': status,
                  'browser_status': browser, 'unit_status': unit['status'],
                  'unit_failed': unit_has_failure(unit), 'unverified': unverified,
                  'triage_status': routing['status'], 'triage_missing': routing['missing'],
                  'auto_fixable': auto_fixable, 'failure_triage': payload.get('failureTriage'),
                  'next_action': ('classify' if not complete else 'bugfix' if auto_fixable
                                  else 'clarify' if routing['clarifications']
                                  else 'verify' if unverified else 'none'),
                  'total': summary.get('total'), 'pass': summary.get('pass'),
                  'failed': summary.get('fail'), 'block': summary.get('block'),
                  'na': summary.get('na'), 'unit_counts': unit.get('counts'),
                  'runtime_errors': summary.get('runtime_errors', 0), 'bug_ids': bug_ids,
                  'report_ready': True, 'converged': status == 'PASS' and complete and not unverified,
                  'pending_cases': pending_cases, 'pending_bugs': pending_bugs}
        row['test_join'] = dict(result, digest=digest, at=existing.get('at', now) if existing.get('digest') == digest else now)
        row['unit_tests_status'] = unit['status']
        if node.get('current_build') == build:
            node['aiauto_test_result'] = result
            node['aiauto_test_report'] = f'docs/reports/{version}/AI测试报告/index.html#/build/{build}'
            node['aiauto_test_build_data'] = f'docs/reports/{version}/AI测试报告/data/{build}.js'
            node['triage_pending'] = not complete
            # 只替换当前 build 的分类记录，其他 build / 人工条目原样保留。
            for key, items in (('pending_clarifications', routing['clarifications']),
                               ('environment_unverified', routing['environment'])):
                kept = [item for item in node.get(key, [])
                        if not (item.get('source') == 'aiauto_test_join' and item.get('raised_build') == build)]
                kept.extend(dict(item, source='aiauto_test_join', raised_build=build,
                                 commit=payload['commit'], at=now) for item in items)
                if kept or key in node:
                    node[key] = kept
            if result['converged']:
                node.update(aiauto_tested_at=now, aiauto_test_unconverged_streak=0,
                            auto_fixable_pending=False)
                node.pop('auto_retest_streak', None)
                node.pop('auto_fix_in_progress_since', None)
                row['status'] = 'tested'
            else:
                node.pop('aiauto_tested_at', None)
                row['status'] = 'test-triage-pending' if not complete else 'test-unverified' if unverified else 'tested'
                if auto_fixable:
                    node['auto_fixable_pending'] = True
                    if not row.get('test_failure_counted'):
                        node['aiauto_test_unconverged_streak'] = int(node.get('aiauto_test_unconverged_streak', 0)) + 1
                        row['test_failure_counted'] = True
                elif not complete or not unverified or routing['environment'] or routing['clarifications']:
                    # 待分流不能沿用旧 AFP 猜测当前失败可修；已识别的单测/代码失败在上支保留。
                    node['auto_fixable_pending'] = False
            # 失败/未核验/待分流均不清复测周期；纯环境/语义问题不递增代码失败计数。
        return dict(result, digest=digest)


def begin(root, version, build, commit):
    """先声明本 build 双路在途；旧 PASS 不可让正在执行的新 build 提前发布。"""
    root = Path(root).resolve()
    _name(version); _name(build)
    with LockedBaseline(str(root / 'memory/.sprint-autopilot-baseline.json'), write=True) as state:
        node = (state.data.get('versions') or {}).get(version) or {}
        row = next((r for r in node.get('builds', []) if r.get('build') == build), None)
        if not row or row.get('push_commit') != commit:
            raise ValueError('begin 的 build/commit 必须已在部署 baseline 中绑定')
        if not row.get('test_join'):
            row['test_join'] = {'build': build, 'commit': commit, 'overall_status': 'RUNNING',
                                'at': datetime.now(timezone.utc).isoformat()}
            if node.get('current_build') == build:
                node.pop('aiauto_tested_at', None)
        return row['test_join']


def release_state(root, version):
    with LockedBaseline(str(Path(root) / 'memory/.sprint-autopilot-baseline.json'), write=False) as state:
        node = (state.data.get('versions') or {}).get(version) or {}
        current = node.get('current_build')
        row = next((r for r in node.get('builds', []) if r.get('build') == current), {})
        result = row.get('test_join') or {}
        if not result:
            return 'legacy'
        if result.get('commit') != row.get('push_commit') or result.get('build') != current:
            return 'pending'
        if result.get('triage_status') == 'PENDING':
            return 'pending'
        status = result.get('overall_status')
        return 'pass' if status == 'PASS' and result.get('converged') else 'failed' if status == 'FAIL' else 'pending'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    for name in ('begin', 'settle', 'release-state'):
        child = sub.add_parser(name)
        child.add_argument('--root', default='.')
        child.add_argument('--version', required=True)
        if name != 'release-state':
            child.add_argument('--build', required=True)
        if name == 'begin':
            child.add_argument('--commit', required=True)
        elif name == 'settle':
            child.add_argument('--report', required=True)
            child.add_argument('--triage', help='主协调者分类 JSON，必须与已 emit 报告 failureTriage 完全一致')
            child.add_argument('--standalone', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.action == 'release-state':
            print(release_state(args.root, args.version))
            return 0
        result = (begin(args.root, args.version, args.build, args.commit) if args.action == 'begin'
                  else settle(args.root, args.version, args.build, read_payload(args.report), args.standalone,
                              read_payload(args.triage) if args.triage else None))
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        if result.get('triage_status') == 'PENDING':
            print('缺陷分类未完成：须主协调者补齐 triage_missing 并重新 emit/settle；不得等待或 finalize', file=sys.stderr)
            return 2
        return 0
    except (ValueError, OSError, TypeError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
