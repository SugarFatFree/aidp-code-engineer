#!/usr/bin/env python3
"""dispatch_plan.py：并行判定、冲突、阈值、prompt 必带项与输入错误。"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "dispatch_plan.py"
sys.path.insert(0, str(SCRIPT.parent))
from entry_context import fork_context, resolve_context, revise_context


def run(*args):
    p = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)
    return p.returncode, (json.loads(p.stdout) if p.stdout.strip() else None), p.stderr


class DispatchPlanTest(unittest.TestCase):
    def test_four_independent_tasks_parallel(self):
        args = []
        for i in "abcd":
            args += ["--task", f"{i}=src/{i}.py,tests/test_{i}.py"]
        rc, out, _ = run(*args)
        self.assertEqual(rc, 0)
        self.assertEqual(out["decision"], "parallel")
        self.assertEqual(out["parallel_groups"], [["a", "b", "c", "d"]])
        self.assertEqual(out["serial"], [])
        self.assertEqual(out["conflicts"], [])

    def test_overlap_serial_with_conflict_files(self):
        rc, out, _ = run("--task", "a=x.py,common.py", "--task", "b=y.py,common.py")
        self.assertEqual(rc, 0)
        self.assertEqual(out["decision"], "serial")
        self.assertEqual(out["conflicts"], [{"files": ["common.py"], "tasks": ["a", "b"]}])
        self.assertEqual(out["serial"], ["a", "b"])

    def test_partial_conflict_keeps_parallel_rest(self):
        rc, out, _ = run("--task", "a=x.py,c.py", "--task", "b=y.py,c.py",
                         "--task", "d=p.py,q.py", "--task", "e=r.py,s.py")
        self.assertEqual(out["decision"], "parallel")
        self.assertEqual(out["parallel_groups"], [["d", "e"]])
        self.assertEqual(out["serial"], ["a", "b"])

    def test_directory_prefix_overlaps(self):
        rc, out, _ = run("--task", "a=pkg/**,z.py", "--task", "b=pkg/m.py,w.py")
        self.assertEqual(out["decision"], "serial")
        self.assertTrue(out["conflicts"])

    def test_directory_spellings_conflict_but_siblings_do_not(self):
        for directory in ('pkg/', 'pkg', './pkg//', 'pkg/**'):
            with self.subTest(directory=directory):
                rc, out, _ = run('--task', f'a={directory},z.py', '--task', 'b=pkg/m.py,w.py')
                self.assertEqual(rc, 0)
                self.assertEqual(out['decision'], 'serial')
                self.assertTrue(out['conflicts'])
        rc, out, _ = run('--task', 'a=pkg/,z.py', '--task', 'b=pkg2/m.py,w.py')
        self.assertEqual(out['decision'], 'parallel')

    def test_unsafe_write_paths_rejected(self):
        for path in ('../pkg', 'pkg/../other', '/tmp/pkg', '.', '.git/config',
                     'memory/.aidp/state', 'C:\\tmp', 'pkg/*.py'):
            with self.subTest(path=path):
                rc, _, _ = run('--task', f'a={path},z.py')
                self.assertEqual(rc, 2)
        rc, _, _ = run('--tasks-json', '[{"id":"a","writes":[123]}]')
        self.assertEqual(rc, 2)

    def test_prompts_require_child_context_mapping(self):
        rc, _, _ = run('--task', 'a=a.py,b.py', '--task', 'b=c.py,d.py',
                       '--emit-prompts', '--execution-context', 'parent/context.json',
                       '--action', 'implement', '--budget', '{}')
        self.assertEqual(rc, 2)

    def test_single_task_serial_with_reason(self):
        rc, out, _ = run("--task", "a=x.py,y.py")
        self.assertEqual(out["decision"], "serial")
        self.assertTrue(any("单个" in r for r in out["reasons"]))

    def test_below_threshold_serial(self):
        rc, out, _ = run("--task", "a=x.py", "--task", "b=y.py", "--reads", "a=1", "--reads", "b=2")
        self.assertEqual(out["decision"], "serial")
        self.assertEqual(sorted(out["serial"]), ["a", "b"])
        self.assertTrue(any("未达并行阈值" in r for r in out["reasons"]))

    def test_reads_threshold_makes_eligible(self):
        rc, out, _ = run("--task", "a=x.py", "--task", "b=y.py", "--reads", "a=3", "--reads", "b=5")
        self.assertEqual(out["decision"], "parallel")

    def test_tasks_json_and_prompts_contain_required_items(self):
        tasks = [{"id": "a", "writes": ["a1.py", "a2.py"], "summary": "改 A"},
                 {"id": "b", "writes": ["b1.py"], "reads": 4}]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            parent = resolve_context(root, 'sprint-dev', version='V1', write_set=['a1.py', 'a2.py', 'b1.py'])
            children = {task['id']: fork_context(root, parent['execution_context'], child_key=task['id'],
                        write_set=task['writes'])['execution_context'] for task in tasks}
            args = ['--root', str(root), '--tasks-json', json.dumps(tasks), '--emit-prompts',
                    '--execution-context', parent['execution_context'], '--action', 'implement', '--budget', '{"agents": 3}']
            mappings = [part for tid, path in children.items() for part in ('--child-context', f'{tid}={path}')]
            rc, out, err = run(*args, *mappings)
            self.assertEqual(rc, 0, err)
            self.assertEqual(len(out['prompts']), 2)
            for item in out['prompts']:
                text = item['prompt']
                for needle in (parent['execution_context'], children[item['task_id']], 'implement', '{"agents": 3}',
                               '只跑本写集对应的相关测试', '不得传入/追加任何 grant', '不得再向下派发', '先静态，再选测，再测试',
                               '保留子分片证据', '独占最终总 scope'):
                    self.assertIn(needle, text)
            self.assertIn('a1.py', out['prompts'][0]['prompt'])
            self.assertIn('b1.py', out['prompts'][1]['prompt'])
            for wrong in (parent['execution_context'], children['b'], str(root / 'missing.json')):
                rc, _, _ = run(*args, '--child-context', f'a={wrong}', '--child-context', f'b={children["b"]}')
                self.assertEqual(rc, 2)
            # 声明窄写集不得复用实际较宽的子 context。
            changed = [dict(tasks[0], writes=['a1.py'], reads=3), tasks[1]]
            rc, _, _ = run(*args, '--tasks-json', json.dumps(changed), *mappings)
            self.assertEqual(rc, 2)
            revise_context(root, parent['execution_context'], ['extra.py'])
            rc, _, _ = run(*args, *mappings)
            self.assertEqual(rc, 2)

    def test_symlink_write_path_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'alias').symlink_to(root / 'actual', target_is_directory=True)
            rc, _, _ = run('--root', str(root), '--task', 'a=alias/x.py,z.py')
            self.assertEqual(rc, 2)

    def test_input_errors_exit_2(self):
        for args in ([], ["--task", "bad"], ["--task", "a=x.py", "--task", "a=y.py"],
                     ["--tasks-json", "{oops"], ["--task", "a=x.py", "--reads", "zz=1"],
                     ["--task", "a=x.py,y.py", "--task", "b=z.py,w.py", "--emit-prompts"]):
            rc, _, err = run(*args)
            self.assertEqual(rc, 2, args)
            self.assertIn("输入错误", err)


if __name__ == "__main__":
    unittest.main()
