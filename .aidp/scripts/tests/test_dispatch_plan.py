#!/usr/bin/env python3
"""dispatch_plan.py：并行判定、冲突、阈值、prompt 必带项与输入错误。"""
import json
from pathlib import Path
import subprocess
import sys
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "dispatch_plan.py"


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
        rc, out, _ = run("--tasks-json", json.dumps(tasks), "--emit-prompts",
                         "--execution-context", "memory/.aidp/entry-contexts/t1/context.json",
                         "--action", "implement", "--budget", '{"agents": 3}')
        self.assertEqual(rc, 0)
        self.assertEqual(len(out["prompts"]), 2)
        for item in out["prompts"]:
            text = item["prompt"]
            for needle in ("memory/.aidp/entry-contexts/t1/context.json", "implement", '{"agents": 3}',
                           "只跑本写集对应的相关测试", "不得传入/追加任何 grant", "不得再向下派发"):
                self.assertIn(needle, text)
        self.assertIn("a1.py", out["prompts"][0]["prompt"])
        self.assertIn("b1.py", out["prompts"][1]["prompt"])

    def test_input_errors_exit_2(self):
        for args in ([], ["--task", "bad"], ["--task", "a=x.py", "--task", "a=y.py"],
                     ["--tasks-json", "{oops"], ["--task", "a=x.py", "--reads", "zz=1"],
                     ["--task", "a=x.py,y.py", "--task", "b=z.py,w.py", "--emit-prompts"]):
            rc, _, err = run(*args)
            self.assertEqual(rc, 2, args)
            self.assertIn("输入错误", err)


if __name__ == "__main__":
    unittest.main()
