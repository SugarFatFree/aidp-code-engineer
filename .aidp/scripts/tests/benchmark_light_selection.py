#!/usr/bin/env python3
"""同输入 light 性能夹具，不纳入日常回归。

python3 .aidp/scripts/tests/benchmark_light_selection.py --scripts .aidp/scripts --out /tmp/light-cost.json
前后对比只切换 --scripts；临时 Git 仓库包含 200 个 Python 测试和 3000 个无关 Java 文件。
只修改一个源码文件，分别测冷缓存、再次修改后的增量选测至真实 unittest 结果；不测下游环境。
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--scripts', required=True)
parser.add_argument('--out', required=True)
args = parser.parse_args()
sys.path.insert(0, str(Path(args.scripts).resolve()))
import entry_context
import test_scope
import test_ledger
import select_related_tests

with tempfile.TemporaryDirectory(prefix='aidp-light-benchmark-') as directory:
    root = Path(directory)

    def git(*argv):
        return subprocess.run(['git', '-C', str(root), *argv], check=True,
                              capture_output=True, text=True).stdout.strip()

    def write(path, text):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    git('init', '-q')
    git('config', 'user.name', 'benchmark')
    git('config', 'user.email', 'benchmark@example.invalid')
    write('.gitignore', '__pycache__/\nmemory/.aidp/\n')
    write('tests/__init__.py', '')
    for i in range(200):
        write(f'src/m{i}.py', 'value=1\n')
        write(f'tests/test_m{i}.py', f'import unittest\nfrom src.m{i} import value\n'
              'class Check(unittest.TestCase):\n def test_value(self): self.assertGreater(value, 0)\n')
    for i in range(3000):
        write(f'java/Unused{i}.java', f'class Unused{i} {{}}\n')
    git('add', '-A')
    git('commit', '-qm', 'fixture')
    context = entry_context.resolve_context(root, 'sprint-dev', version='V1', write_set=['src/m0.py'],
        additional_grants=['related-test'], authorization_source={
            'kind': 'user-text', 'request_id': 'benchmark', 'text': '修改并运行相关测试'})['execution_context']
    runners = [{'suffixes': ['.py'], 'argv': [sys.executable, '-B', '-m', 'unittest', '{tests}']}]
    metrics = []
    real_hash, real_analysis = test_ledger.file_hash, test_scope.dependency_analysis
    counts = {}

    def count_hash(path, *a, **kw):
        counts['fingerprint_reads'] += 1
        return real_hash(path, *a, **kw)

    def count_analysis(*a, **kw):
        candidates = kw.get('candidates')
        counts['analysis_candidates'] += sum(test_scope.is_test(p) for p in
                                             (a[1] if candidates is None else candidates))
        return real_analysis(*a, **kw)

    test_ledger.file_hash, test_scope.dependency_analysis = count_hash, count_analysis
    for label, value in [('cold', 2), ('changed_warm', 3)]:
        write('src/m0.py', f'value={value}\n')
        counts = {'fingerprint_reads': 0, 'analysis_candidates': 0}
        start = time.perf_counter()
        plan = test_scope.derive(root, '', runners, execution_context=context)
        selected_at = time.perf_counter()
        path = Path(context).parent / 'benchmark-scope.json'
        path.write_text(json.dumps(plan))
        whitelist = select_related_tests.select(root, '', [], context, [], None, str(path))
        result, code = test_ledger.run_scope(root, path, 'benchmark', execution_context=context)
        metrics.append(dict(phase=label, selection_seconds=round(selected_at - start, 4),
                            total_seconds=round(time.perf_counter() - start, 4), selected=plan['tests'],
                            whitelist_matches=whitelist['tests'] == plan['tests'],
                            verdict=result['status'], exit_code=code, **counts))
        if code:
            raise SystemExit(json.dumps(result))
    report = {'fixture_files': 3402, 'changed_files': 1, 'python_candidates': 200,
              'unrelated_java_files': 3000, 'runs': metrics}
    Path(args.out).write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
