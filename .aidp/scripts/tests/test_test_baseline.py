#!/usr/bin/env python3
"""test_baseline.py：已知失败基线 record / diff（代替 git stash 对照）。"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "test_baseline.py"
PYTEST_LOG = """\
============ short test summary info ============
FAILED tests/test_a.py::test_one - AssertionError: x
ERROR tests/test_b.py::test_two
========= 2 failed, 5 passed in 0.12s =========
"""
JUNIT = """<testsuite><testcase classname="tests.test_a" name="test_one"><failure message="x"/></testcase>
<testcase classname="tests.test_a" name="test_ok"/></testsuite>"""


class BaselineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aidp-baseline-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args, "--root", str(self.root)], capture_output=True, text=True)

    def ids(self, name, *ids):
        path = self.root / name
        path.write_text("\n".join(ids) + "\n")
        return str(path)

    def test_record_then_diff_reports_only_new_failures(self):
        out = self.cli("record", "--ids-file", self.ids("base.txt", "t::a", "t::b"))
        self.assertEqual(out.returncode, 0, out.stderr)
        stored = json.loads((self.root / "memory/.aidp/test-baseline/default.json").read_text())
        self.assertEqual(stored["failures"], ["t::a", "t::b"])
        res = self.cli("diff", "--ids-file", self.ids("now.txt", "t::b", "t::c"), "--json")
        self.assertEqual(res.returncode, 1)
        data = json.loads(res.stdout)
        self.assertEqual(data, {"new_failures": ["t::c"], "known_failures": ["t::b"], "fixed": ["t::a"]})
        same = self.cli("diff", "--ids-file", self.ids("same.txt", "t::a"), "--json")
        self.assertEqual(same.returncode, 0)
        self.assertEqual(json.loads(same.stdout)["new_failures"], [])

    def test_log_and_junit_sources(self):
        log = self.root / "run.log"
        log.write_text(PYTEST_LOG)
        self.assertEqual(self.cli("record", "--from-log", str(log)).returncode, 0)
        base = json.loads((self.root / "memory/.aidp/test-baseline/default.json").read_text())
        self.assertEqual(base["failures"], ["tests/test_a.py::test_one", "tests/test_b.py::test_two"])
        xml = self.root / "r.xml"
        xml.write_text(JUNIT)
        self.assertEqual(self.cli("record", "--from-junit", str(xml), "--key", "j").returncode, 0)
        base = json.loads((self.root / "memory/.aidp/test-baseline/j.json").read_text())
        self.assertEqual(base["failures"], ["tests.test_a::test_one"])

    def test_refuses_when_baseline_missing_or_run_did_not_execute(self):
        res = self.cli("diff", "--ids-file", self.ids("x.txt", "a"))
        self.assertEqual(res.returncode, 2)
        self.assertIn("基线", res.stderr)
        empty = self.root / "empty.log"
        empty.write_text("python: can't open file 'x': No such file\n")
        for mode in ("record", "diff"):
            self.cli("record", "--ids-file", self.ids("seed.txt", "a")) if mode == "diff" else None
            res = self.cli(mode, "--from-log", str(empty))
            self.assertEqual(res.returncode, 2, mode)
            self.assertIn("没有测试已执行", res.stderr)

    def test_context_key_and_bad_input(self):
        ctx = self.root / "ctx.json"
        ctx.write_text(json.dumps({"task_id": "task-9"}))
        self.assertEqual(self.cli("record", "--ids-file", self.ids("i.txt", "a"), "--execution-context", str(ctx)).returncode, 0)
        self.assertTrue((self.root / "memory/.aidp/test-baseline/task-9.json").is_file())
        self.assertEqual(self.cli("record").returncode, 2)
        self.assertEqual(self.cli("record", "--ids-file", "nope.txt").returncode, 2)


if __name__ == "__main__":
    unittest.main()
