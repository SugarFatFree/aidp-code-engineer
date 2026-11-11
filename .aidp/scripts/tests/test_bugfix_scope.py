#!/usr/bin/env python3
"""bugfix_scope.py：按列解析 bugfix 台账表，判未闭环 P0（替代 release-1 的整行 grep，F-01/G-01）。"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "bugfix_scope.py"

HEAD = """# Bugfix 20260508 - alice

## Bug 清单

| 编号 | 时间 | Sprint | 模块 | 现象 | 严重 | 优先级 | 难易 | 状态 | Commit | 备注 |
| :-: | :- | :-: | :- | :- | :-: | :-: | :-: | :-: | :- | :- |
"""
TAIL = """
### 字段说明
- **严重**：P0 阻塞 / P1 严重 / P2 一般 / P3 轻微
- **状态**：Open 待修 / In-Progress 修复中 / Fixed 已修 / Verified 已验证 / Closed 已关闭 / Reopened 回归
"""


def row(bid, sprint, sev, status):
    return f"| {bid} | 2026-05-08 | Sprint-{sprint} | m | 现象 | {sev} | 高 | 简单 | {status} | `abc` | - |\n"


class BugfixScopeTests(unittest.TestCase):
    def make(self, rows):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        bd = Path(d.name) / "docs/bugfix/V0.1.0"
        bd.mkdir(parents=True)
        (bd / "bugfix-20260508-alice.md").write_text(HEAD + "".join(rows) + TAIL, encoding="utf-8")
        return d.name

    def run_cli(self, root, *extra):
        r = subprocess.run([sys.executable, str(SCRIPT), "--root", root, "--version", "V0.1.0", *extra],
                           capture_output=True, text=True)
        return r.returncode, r.stdout, r.stderr

    def test_all_closed_is_zero_open_p0(self):
        """F-01 反例：全部闭环时，表头与字段说明里的「严重」「P0」字样不得被计为未闭环 P0。"""
        root = self.make([row("B-1", "001", "P0 阻塞", "Verified 已验证"),
                          row("B-2", "001", "P2 一般", "Closed 已关闭")])
        rc, out, _ = self.run_cli(root, "--severity", "P0", "--status", "open", "--count")
        self.assertEqual((rc, out.strip()), (0, "0"))

    def test_open_p0_counted_and_p1_serious_not(self):
        root = self.make([row("B-1", "001", "P0 阻塞", "Open 待修"),
                          row("B-2", "001", "P1 严重", "Open 待修"),
                          row("B-3", "002", "P0", "Reopened 回归"),
                          row("B-4", "002", "P0", "已修"),
                          row("B-5", "002", "P0", "Fixed 已修")])
        rc, out, _ = self.run_cli(root, "--severity", "P0", "--status", "open", "--json")
        self.assertEqual(rc, 0)
        self.assertEqual([b["id"] for b in json.loads(out)["bugs"]], ["B-1", "B-3"])

    def test_sprint_filter(self):
        root = self.make([row("B-1", "001", "P2 一般", "Open 待修"), row("B-2", "002", "P2 一般", "Open 待修")])
        rc, out, _ = self.run_cli(root, "--sprint", "002", "--status", "open", "--json")
        self.assertEqual([b["id"] for b in json.loads(out)["bugs"]], ["B-2"])

    def test_unparsed_status_is_not_silently_closed(self):
        root = self.make([row("B-1", "001", "P0", "待评审")])
        rc, out, _ = self.run_cli(root, "--severity", "P0", "--status", "open", "--json")
        self.assertEqual(rc, 1)
        data = json.loads(out)
        self.assertEqual(data["bugs"], [])
        self.assertEqual(data["unparsed_rows"][0]["id"], "B-1")

    def test_no_bugfix_dir_is_zero(self):
        with tempfile.TemporaryDirectory() as d:
            rc, out, _ = self.run_cli(d, "--severity", "P0", "--status", "open", "--count")
            self.assertEqual((rc, out.strip()), (0, "0"))

    def test_usage_error(self):
        r = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)

    def test_old_release1_grep_false_positive_reproduced(self):
        """记录旧实现的误判：同一份全闭环台账，整行 grep 得 2（证明新脚本修的是真问题）。"""
        root = self.make([row("B-1", "001", "P0 阻塞", "Verified 已验证")])
        f = next((Path(root) / "docs/bugfix/V0.1.0").glob("*.md"))
        out = subprocess.run(
            "grep -rhE 'P0|严重|阻塞' %s | grep -viE '已修复|已验证|已关闭|已根治|已解决|closed|fixed' | wc -l" % f,
            shell=True, capture_output=True, text=True).stdout.strip()
        self.assertEqual(out, "2")


if __name__ == "__main__":
    unittest.main(verbosity=2)
