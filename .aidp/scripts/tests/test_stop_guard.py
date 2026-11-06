#!/usr/bin/env python3
"""真实 Stop hook 重入：每条阻止路径都有上限并留下可见告警。"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HOOK = Path(__file__).resolve().parents[2] / 'hooks/autopilot-stop-guard.py'


class StopGuardLimitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='aidp-stop-limit-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'memory').mkdir()
        self.baseline = self.root / 'memory/.sprint-autopilot-baseline.json'
        self.data = {'versions': {'V1': {'run_state': {'next_phase': '3.1-plan'}}}}
        self.save()

    def save(self):
        self.baseline.write_text(json.dumps(self.data), encoding='utf-8')

    def stop(self, session='same-task'):
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.root), AIDP_TICK_COMMAND='sprint-autopilot')
        return subprocess.run([sys.executable, str(HOOK)], input=json.dumps({'session_id': session}),
                              text=True, capture_output=True, env=env, timeout=20)

    def records(self):
        path = self.root / 'memory/.aidp/stop-guard-skips.jsonl'
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def test_missing_build_blocks_three_times_then_allows_and_notes_once(self):
        results = [self.stop() for _ in range(6)]
        self.assertEqual([2, 2, 2, 0, 0, 0], [r.returncode for r in results])
        noted = [r for r in self.records() if r['branch'] == 'max-blocks-reached']
        self.assertEqual(1, len(noted))
        self.assertIn('no-build', noted[0]['detail'])
        self.assertIn('上限', results[3].stderr)
        self.assertEqual(2, self.stop('new-task').returncode)

    def install_gate(self):
        script = self.root / '.aidp/scripts/autopilot-ceremony-gate.py'
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text('import sys\nfrom pathlib import Path\n'
                          'if sys.argv[1] == "test-loop-alive": print("0")\n'
                          'elif sys.argv[1] == "handback-check" and not Path("ok").exists():\n'
                          ' print("未完成交接"); raise SystemExit(1)\n', encoding='utf-8')
        self.data['versions']['V1'].update(current_build='b1', builds=[{'build': 'b1', 'status': 'open'}])
        self.save()

    def test_handback_has_limit_and_success_clears_build_counter(self):
        self.install_gate()
        results = [self.stop() for _ in range(5)]
        self.assertEqual([2, 2, 2, 0, 0], [r.returncode for r in results])
        self.assertEqual(1, len([r for r in self.records() if r['branch'] == 'max-blocks-reached']))
        # 脚本通过绝对根控制状态，不依赖 hook 子进程 cwd。
        gate = self.root / '.aidp/scripts/autopilot-ceremony-gate.py'
        gate.write_text('import sys\nprint("0" if sys.argv[1] == "test-loop-alive" else "PASS")\n')
        self.assertEqual(0, self.stop().returncode)
        self.install_gate()
        self.assertEqual(2, self.stop().returncode)


if __name__ == '__main__':
    unittest.main()
