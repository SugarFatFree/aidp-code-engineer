#!/usr/bin/env python3
"""研发执行计划验收标准形式初筛：空白/占位/套话/过短无落点命中，带链接或反引号命令的单元格放行。"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "check_plan_ac.py"
SAMPLE = Path(__file__).resolve().parents[2] / "skills/dev-execution-planner/references/iteration-plan-sample.md"

TABLE = """# 计划

| Task | 描述 | 验收标准 |
| :- | :- | :- |
| Task 1.1 | 建表 | [§C-1.1 订单表用例](../a.md#C-1-1) |
| Task 1.2 | 接口 | `curl -s :8080/x` 返回 200 |
| Task 2.1 | 空 |  |
| Task 2.2 | 占位 | TBD |
| Task 2.3 | 套话 | 功能正常 |
| Task 2.4 | 套话2 | 按设计实现。 |
| Task 2.5 | 过短 | 接口通 |
| Task 2.6 | 足够长且描述了判据 | 提交空表单时页面在输入框下方显示红色必填提示并阻止提交 |
"""


class PlanAcTests(unittest.TestCase):
    def run_cli(self, path, *extra):
        r = subprocess.run([sys.executable, str(SCRIPT), str(path), *extra], capture_output=True, text=True)
        return r.returncode, r.stdout, r.stderr

    def test_flags_expected_rows_only(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "plan.md"
            p.write_text(TABLE, encoding="utf-8")
            rc, out, _ = self.run_cli(p, "--json")
            self.assertEqual(rc, 0)
            tasks = [f["task"] for f in json.loads(out)["findings"]]
            self.assertEqual(tasks, ["Task 2.1", "Task 2.2", "Task 2.3", "Task 2.4", "Task 2.5"])

    def test_strict_and_count(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "plan.md"
            p.write_text(TABLE, encoding="utf-8")
            self.assertEqual(self.run_cli(p, "--strict")[0], 1)
            self.assertEqual(self.run_cli(p, "--count")[1].strip(), "5")

    def test_shipped_sample_passes(self):
        rc, out, _ = self.run_cli(SAMPLE, "--strict")
        self.assertEqual(rc, 0, out)

    def test_missing_file_is_usage_error(self):
        self.assertEqual(self.run_cli("/nonexistent/plan.md")[0], 2)


if __name__ == "__main__":
    unittest.main()
