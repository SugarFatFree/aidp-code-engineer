#!/usr/bin/env python3
"""无人值守小项回归：执行真实报告取证正则并核对调用模板和兼容忽略说明。"""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


class UnattendedEdgeTests(unittest.TestCase):
    def test_run_summary_counts_only_outer_unittest_result(self):
        import shlex
        import sys
        source = (ROOT / '.aidp/scripts/tests/run.sh').read_text()
        prefix, marker, _ = source.partition('\nrun "test_report_schema.py')
        self.assertTrue(marker, '必须运行当前run.sh中的真实汇总函数')
        cases = [
            ('Ran 1 test in 0.1s\nFAILED (failures=1, errors=1)\n'
             'Ran 10 tests in 0.2s\nOK (skipped=2)\n', 0, 'COUNTS:8:0:2'),
            ('Ran 5 tests in 0.1s\nOK (skipped=5)\n'
             'Ran 7 tests in 0.2s\nFAILED (failures=1, errors=2, skipped=1)\n', 1, 'COUNTS:3:3:1'),
            ('Ran 2 tests in 0.1s\nOK (skipped=2)\n'
             'Ran 3 tests in 0.2s\nOK\n', 0, 'COUNTS:3:0:0'),
            ('Ran 1 test in 0.1s\nOK\nRan 3 tests in 0.2s\n', 1, 'COUNTS:0:0:0'),
        ]
        for output, code, expected in cases:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                runner = root / '.aidp/scripts/tests/run.sh'
                runner.parent.mkdir(parents=True)
                fixture = root / 'fixture.py'
                fixture.write_text('import sys\nsys.stdout.write(' + repr(output) + ')\nsys.exit(' + str(code) + ')\n')
                runner.write_text(prefix + '\nrun fixture ' + shlex.quote(sys.executable) + ' ' + shlex.quote(str(fixture)) +
                                  '\nprintf "COUNTS:%s:%s:%s\\n" "$total_pass" "$total_fail" "$total_skip"\n')
                result = subprocess.run(['bash', str(runner)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(expected, result.stdout)

    def test_chain_guard_understands_quoted_context_without_trusting_quoted_flags(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('chain_guard', ROOT / '.aidp/scripts/check_chain_unattended.py')
        guard = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(guard)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commands = root / '.aidp/commands'
            commands.mkdir(parents=True)
            (commands / 'sprint-dev.md').write_text('参数 --unattended\n')
            caller = commands / 'sprint-full.md'
            for args, missing in [
                ('--execution-context "$CTX" {NNN} [--from-batch] [--unattended]', False),
                ('{NNN} --execution-context "path with spaces" --unattended', False),
                ('{NNN} --execution-context "$CTX" [--unattended]（其它描述）', False),
                ('{NNN} --execution-context "$CTX" --scale={档位} [--unattended]', False),
                ('{NNN} --execution-context "$CTX" --param=--unattended', True),
                ('{NNN} --execution-context "$CTX"', True),
                ('{NNN} --description "--unattended"', True),
                ('{NNN} --execution-context "$CTX"（务必带 --unattended）', True),
            ]:
                with self.subTest(args=args):
                    caller.write_text('执行：/sprint-dev ' + args + '\n')
                    self.assertEqual(bool(guard.collect(root)), missing)

    def test_report_source_check_understands_emitted_json(self):
        text = (ROOT / '.aidp/flows/sprint-aiauto-test/phase-3-2.md').read_text()
        match = re.search(r"<<'REPORT_READY'\n(.*?)\nREPORT_READY", text, re.S)
        self.assertIsNotNone(match, '报告来源校验必须有真实可执行入口')
        block = match.group(1).replace('{{AIDP_HOME}}', str(ROOT / '.aidp'))
        for payload, invalid in (({'renderMode': 'headless'}, True),
                                 ({'renderMode': 'headed', 'renderModeSource': 'env-facts'}, False),
                                 ({'renderMode': None}, False)):
            import json
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'build.js'
                path.write_text('window.__BUILDS__.push(' + json.dumps(payload) + ');')
                import sys
                result = subprocess.run([sys.executable, '-c', block, str(path)],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode != 0, invalid, result.stdout + result.stderr)
                if invalid:
                    self.assertIn('renderMode 缺运行取证来源', result.stderr)
                else:
                    self.assertIn('报告已按真实终态汇总', result.stdout)

    def test_python_failure_callers_are_checked_without_comment_exemptions(self):
        import importlib.util
        import shutil
        spec = importlib.util.spec_from_file_location('freeze_guard', ROOT / '.aidp/scripts/check_freeze_contract.py')
        guard = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(guard)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            enum = root / '.aidp/flows/sprint-aiauto-test/rationale.md'
            enum.parent.mkdir(parents=True)
            shutil.copy2(ROOT / '.aidp/flows/sprint-aiauto-test/rationale.md', enum)
            scripts = root / '.aidp/scripts'
            scripts.mkdir(parents=True)
            shutil.copy2(ROOT / '.aidp/scripts/autopilot_unfreeze.py', scripts / 'autopilot_unfreeze.py')
            probe = scripts / 'consumer.py'
            probe.write_text("call('autopilot_fail_handle.py', '--freeze-now', '--reason', 'cicd-unreachable')\n")
            result = guard.run(str(root))
            self.assertFalse(any(f['level'] == 'ERROR' for f in result['findings']))
            self.assertFalse(any('`cicd-unreachable` 零写入者' in f['detail'] for f in result['findings']))
            for fragment in ("'--reason', 'unknown-freeze'", "'--reason', reason", "'--reason', 'cicd-unreachable', '--no-card'"):
                probe.write_text("call('autopilot_fail_handle.py', " + fragment + ")\n")
                self.assertTrue(any(f['level'] == 'ERROR' for f in guard.run(str(root))['findings']), fragment)
            probe.write_text("# call('autopilot_fail_handle.py', '--reason', 'cicd-unreachable')\n")
            self.assertTrue(any('`cicd-unreachable` 零写入者' in f['detail'] for f in guard.run(str(root))['findings']))

    def test_python_streak_writer_scan_requires_real_call_or_preflight_bump(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('flowvar_guard', ROOT / '.aidp/scripts/check_flow_var_refs.py')
        guard = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(guard)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scripts = root / '.aidp/scripts'
            scripts.mkdir(parents=True)
            consumer = scripts / 'consumer.py'
            consumer.write_text("# call('autopilot_fail_handle.py', '--streak-key', 'cicd_test_streak')\n")
            self.assertEqual(guard._python_streak_writers(str(root)), set())
            consumer.write_text("call('autopilot_fail_handle.py', '--streak-key', 'cicd_test_streak')\n")
            self.assertEqual(guard._python_streak_writers(str(root)), {'cicd_test_streak'})
            handler = scripts / 'autopilot_fail_handle.py'
            constants = "PREFLIGHT_KEYS = {'autopilot': ('preflight_test_streak', 'frozen', 'reason')}\n"
            handler.write_text(constants)
            self.assertNotIn('preflight_test_streak', guard._python_streak_writers(str(root)))
            handler.write_text(constants + "def _preflight(a):\n _be(['bump', k_streak])\n")
            self.assertIn('preflight_test_streak', guard._python_streak_writers(str(root)))

    def test_actual_dev_templates_carry_required_cases_flag(self):
        flow = ROOT / '.aidp/flows/sprint-autopilot'
        for name, command in (('phase-3-5.md', '/sprint-full ${SPRINT_NO}'),
                              ('phase-3-5b.md', '/sprint-batch')):
            text = (flow / name).read_text()
            call = next(line for line in text.splitlines() if command in line and '[--aiauto-test-required]' in line)
            self.assertIn('[--aiauto-test-required]', call)
            self.assertIn('--execution-context', call)
            if name == 'phase-3-5b.md':
                self.assertIn('--skip-context-check', call)
            self.assertIn('SKIP_AIAUTO_TEST!=1', text)

    def test_dirty_tree_default_does_not_stage_everything(self):
        text = (ROOT / '.aidp/flows/sprint-autopilot/phase-0-7.md').read_text()
        row = next(line for line in text.splitlines() if '| 脏树处置' in line)
        self.assertNotIn('git add -A', row)
        self.assertIn('autostash', row)
        self.assertIn('dirty-tree', row)

    def test_legacy_preflight_unfreezes_but_cannot_be_new_freeze_reason(self):
        import json
        import shutil
        import sys
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scripts = root / '.aidp/scripts'
            shutil.copytree(ROOT / '.aidp/scripts', scripts, ignore=shutil.ignore_patterns('tests', '__pycache__'))
            (root / 'memory').mkdir()
            baseline = root / 'memory/.sprint-autopilot-baseline.json'
            baseline.write_text(json.dumps({'preflight_fail_reason': 'preflight-gate',
                'preflight_frozen_at': '2026-01-01', 'preflight_fail_streak': 3,
                'aiauto_blocked_reason': 'frozen:preflight-incomplete@V1.0.0',
                'versions': {'V1.0.0': {'needs_human': True, 'freeze_reason': 'preflight-incomplete',
                                      'aiauto_frozen_at': '2026-01-01'}}}))
            result = subprocess.run([sys.executable, str(ROOT / '.aidp/scripts/autopilot_fail_handle.py'),
                '--baseline', str(baseline), '--version', 'V1.0.0', '--phase', 'probe',
                '--reason', 'preflight-incomplete', '--why', 'test', '--json'], capture_output=True, text=True)
            self.assertEqual(2, result.returncode)
            result = subprocess.run([sys.executable, str(ROOT / '.aidp/scripts/autopilot_unfreeze.py'),
                'preflight-gate', '--root', str(root), '--json'], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertTrue(json.loads(result.stdout)['cleared'])
            data = json.loads(baseline.read_text())
            self.assertNotIn('aiauto_blocked_reason', data)
            self.assertNotIn('needs_human', data['versions']['V1.0.0'])

    def test_trimmed_flow_fragments_leave_editing_headroom(self):
        for rel in ('sprint-autopilot/phase-3-8.md', 'version/release-6.md'):
            self.assertLess((ROOT / '.aidp/flows' / rel).stat().st_size, 20200)

    def test_old_gitignore_locations_are_labelled_as_legacy(self):
        text = (ROOT / 'skills/aidp-code-engineer/sources/root/gitignore.tpl').read_text()
        for filename in ('memory/.autopilot-ceremony-ledger.json', 'memory/.autopilot-stop-guard-count',
                         'memory/.autopilot-stop-guard-skips.jsonl'):
            lines = text.splitlines()
            n = lines.index(filename)
            context = '\n'.join(lines[max(0, n-3):n])
            self.assertIn('旧版', context)
            self.assertIn('memory/.aidp/', context)


if __name__ == '__main__':
    unittest.main()
