#!/usr/bin/env python3
"""离线性能夹具：冻结输入不变，真实执行16或128个unittest，输出推导/指纹/启动/存储成本。

用法：python3 .aidp/scripts/tests/benchmark_scope_cost.py --repo . --out memory/.aidp/cost.json --files 16
不纳入日常run.sh；前后对比使用同一脚本、解释器与文件数，只切换 --repo 指向的实现。
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

parser = argparse.ArgumentParser()
parser.add_argument('--repo', required=True)
parser.add_argument('--out', required=True)
parser.add_argument('--files', type=int, default=16)
a = parser.parse_args()
if not 1 <= a.files <= 512:
    parser.error("--files 必须在1到512之间，避免意外大规模启动")
sys.path.insert(0, str(Path(a.repo) / '.aidp/scripts'))
import test_scope as scope
import test_ledger as ledger

counts = {'derive': 0, 'dependency_analysis': 0, 'tree_snapshot': 0, 'test_processes': 0}
for mod, name in ((scope, 'derive'), (scope, 'dependency_analysis'), (ledger, 'tree_snapshot')):
    original = getattr(mod, name)
    def counted(*args, _original=original, _name=name, **kwargs):
        counts[_name] += 1
        return _original(*args, **kwargs)
    setattr(mod, name, counted)
original_popen = subprocess.Popen
def popen(argv, *args, **kwargs):
    if isinstance(argv, (list, tuple)) and '-m' in argv and 'unittest' in argv:
        counts['test_processes'] += 1
    return original_popen(argv, *args, **kwargs)
subprocess.Popen = popen
with tempfile.TemporaryDirectory(prefix='aidp-cost-') as directory:
    root = Path(directory)
    def git(*args):
        return subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True, check=True).stdout.strip()
    git('init', '-q'); git('config', 'user.name', 'fixture'); git('config', 'user.email', 'fixture@example.invalid')
    (root / '.gitignore').write_text('__pycache__/\nmemory/.aidp/\n')
    (root / 'src').mkdir(); (root / 'tests').mkdir(); (root / 'tests/__init__.py').write_text('')
    for i in range(a.files):
        (root / f'src/m{i}.py').write_text('value = 1\n')
        (root / f'tests/test_m{i}.py').write_text(f'import unittest\nfrom src.m{i} import value\nclass TestM{i}(unittest.TestCase):\n def test_value(self): self.assertEqual(value, 2)\n')
    git('add', '-A');git('commit', '-qm', 'base');base=git('rev-parse','HEAD')
    for i in range(a.files): (root / f'src/m{i}.py').write_text('value = 2\n')
    started = time.perf_counter()
    plan = scope.derive(root, base, [{'cwd':'.','suffixes':['.py'],'argv':[sys.executable,'-B','-m','unittest','{tests}']}])
    state = root / 'memory/.aidp'; state.mkdir(parents=True, exist_ok=True)
    path = state / 'scope.json';path.write_text(json.dumps(plan, ensure_ascii=False))
    result, code = ledger.run_scope(root, path, 'cost-fixture')
    elapsed = time.perf_counter() - started
    rows = [json.loads(line) for line in (state / 'test-ledger.jsonl').read_text().splitlines()]
    metrics = {'files': a.files, 'counts': counts, 'elapsed_seconds': elapsed,
               'scope_bytes': path.stat().st_size, 'ledger_bytes': (state/'test-ledger.jsonl').stat().st_size,
               'embedded_plan_copies': sum(isinstance(r.get('scope_binding'),dict) and 'plan' in r['scope_binding'] for r in rows),
               'run_items': len(plan['runs']), 'selected_tests': len(plan['tests']),
               'status': result['status'], 'exit_code': code}
    Path(a.out).write_text(json.dumps(metrics, ensure_ascii=False, indent=2))
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    raise SystemExit(code)
