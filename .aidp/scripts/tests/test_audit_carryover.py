#!/usr/bin/env python3
"""version-auditor 结转计算：轮次 +1、Important 连续 3 轮升级 Critical、Warning 不升级、回检轮次与升级标记。"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "audit_carryover.py"

PREV = """# 版本规划产物审计

## 十、修复建议（按优先级排序）

| 编号 | 优先级 | 问题 | 建议处置 | 连续未处置轮次 |
|------|--------|------|----------|---------------|
| I-01 | Critical | 已回调修复 | 回 Step 2.4.x | 1 |
| I-02 | Important | 缺口 A | 发布前补 | 2 |
| I-03 | Warning | 小问题 | 仅记录 | 2 |
| I-04 | Important | 缺口 B | 发布前补 | 1 |

> 说明行

## 十一、命令端建议下一步
- ok
"""


def new_report(rows, with12=True):
    body = ("# 审计\n\n## 十、修复建议\n\n| 编号 | 优先级 | 问题 | 建议处置 | 连续未处置轮次 |\n|---|---|---|---|---|\n"
            + "\n".join(rows) + "\n")
    if with12:
        body += "\n## 十二、上轮未处置项结转\n\n| 编号 |\n|---|\n| I-02 |\n"
    return body


class AuditCarryoverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="aidp-carry-")
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.prev = self.dir / "version-output-audit-2026-01-01.md"
        self.prev.write_text(PREV, encoding="utf-8")
        os.utime(self.prev, (1000, 1000))

    def run_cli(self, *args):
        r = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)
        return r.returncode, r.stdout, r.stderr

    def carry(self, *extra):
        rc, out, err = self.run_cli("carry", "--audit-dir", str(self.dir), "--json", *extra)
        self.assertEqual(rc, 0, err)
        return json.loads(out)

    def test_candidates_exclude_critical_and_count_plus_one(self):
        res = self.carry()
        ids = {c["id"]: c for c in res["candidates"]}
        self.assertEqual(set(ids), {"I-02", "I-03", "I-04"})
        self.assertEqual(ids["I-02"]["rounds_if_still_open"], 3)
        self.assertTrue(ids["I-02"]["escalate_if_still_open"])
        self.assertFalse(ids["I-03"]["escalate_if_still_open"], "Warning 即使 3 轮也不升级")
        self.assertEqual(ids["I-04"]["rounds_if_still_open"], 2)

    def test_still_open_carries_escalates_and_drops(self):
        res = self.carry("--still-open", "I-02,I-03,I-99")
        self.assertEqual([c["id"] for c in res["carried"]], ["I-02", "I-03"])
        self.assertEqual(res["escalations"], ["I-02"])
        self.assertEqual(res["dropped"], ["I-04"])
        self.assertEqual(res["unknown_ids"], ["I-99"])
        self.assertIn("升级为 Critical", res["table_12"])

    def test_no_previous_report_is_first_round(self):
        empty = self.dir / "sub"
        empty.mkdir()
        rc, out, _ = self.run_cli("carry", "--audit-dir", str(empty), "--json")
        self.assertEqual(rc, 0)
        self.assertIsNone(json.loads(out)["previous_report"])

    def test_exclude_current_report_and_pick_latest(self):
        newer = self.dir / "version-output-audit-补丁-01.md"
        newer.write_text(new_report(["| I-02 | Important | x | y | 3 ⬆️ 已升级为 Critical |"]), encoding="utf-8")
        os.utime(newer, (2000, 2000))
        res = self.carry()
        self.assertTrue(res["previous_report"].endswith("补丁-01.md"))
        res = self.carry("--exclude", str(newer))
        self.assertTrue(res["previous_report"].endswith("2026-01-01.md"))

    def test_check_passes_on_correct_carry(self):
        rep = self.dir / "version-output-audit-new.md"
        rep.write_text(new_report(["| I-02 | Important | A | b | 3 ⬆️ 已升级为 Critical |",
                                   "| I-03 | Warning | c | d | 3 |"]), encoding="utf-8")
        rc, out, _ = self.run_cli("check", "--audit-dir", str(self.dir), "--report", str(rep), "--prev", str(self.prev))
        self.assertEqual(rc, 0, out)

    def test_check_catches_reset_rounds_and_missing_escalation(self):
        rep = self.dir / "version-output-audit-new.md"
        rep.write_text(new_report(["| I-02 | Important | A | b | 1 |"]), encoding="utf-8")
        rc, out, _ = self.run_cli("check", "--audit-dir", str(self.dir), "--report", str(rep), "--prev", str(self.prev), "--json")
        self.assertEqual(rc, 1)
        errs = json.loads(out)["errors"]
        self.assertTrue(any("应为 3" in e for e in errs), errs)
        self.assertTrue(any("必须标" in e for e in errs), errs)

    def test_check_catches_missing_escalation_only(self):
        rep = self.dir / "version-output-audit-new.md"
        rep.write_text(new_report(["| I-02 | Important | A | b | 3 |"]), encoding="utf-8")
        rc, out, _ = self.run_cli("check", "--audit-dir", str(self.dir), "--report", str(rep), "--prev", str(self.prev), "--json")
        self.assertEqual(rc, 1)
        self.assertEqual(len(json.loads(out)["errors"]), 1)

    def test_check_warns_on_zero_overlap_renumbering(self):
        rep = self.dir / "version-output-audit-new.md"
        rep.write_text(new_report(["| I-01 | Important | A | b | 1 |"], with12=False), encoding="utf-8")
        rc, out, _ = self.run_cli("check", "--audit-dir", str(self.dir), "--report", str(rep), "--prev", str(self.prev), "--json")
        self.assertEqual(rc, 0)
        warns = json.loads(out)["warnings"]
        self.assertTrue(any("零重合" in w for w in warns), warns)
        self.assertTrue(any("十二" in w for w in warns), warns)

    def test_usage_errors(self):
        rc, _, _ = self.run_cli("carry", "--audit-dir", str(self.dir / "nope"))
        self.assertEqual(rc, 2)
        rc, _, _ = self.run_cli("check", "--audit-dir", str(self.dir), "--report", str(self.dir / "nope.md"))
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
