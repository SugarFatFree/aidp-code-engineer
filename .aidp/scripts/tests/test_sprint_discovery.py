#!/usr/bin/env python3
"""三个消费者共用发现/占号/关闭证据；均用真实临时目录及 CLI。"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import check_open_sprints as opened
import check_sprint_numbering as numbering
import plan_sprints


class SprintDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aidp-sprint-discovery-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True, capture_output=True)
        self.version = "V1.0.0"

    def put(self, path, text):
        file = self.root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text, encoding="utf-8")
        return file

    def plan(self):
        self.put("docs/plans/V1.0.0/02_研发执行计划-alice.md", "Sprint-042 登录\nSprint-043 导出\n")

    def test_archive_041_split_plan_042_reserves_next_044(self):
        self.put("memory/V0.9.0/alice/sprints/sprint-041.md", "# Sprint-041\n")
        self.plan()
        self.assertEqual(numbering.next_number(self.root), (44, 43))
        self.assertEqual(opened.planned_sprints(self.root, self.version), {"042", "043"})
        self.assertEqual(plan_sprints.scan(str(self.root), self.version)["all_sprints"], ["042", "043"])
        self.assertTrue(opened.scan(self.root, self.version, "started")["ok"])

    def test_only_started_042_is_reserved_and_blocks_start(self):
        opened.record_start(self.root, self.version, "alice", "042")
        self.assertEqual(numbering.next_number(self.root), (43, 42))
        result = opened.scan(self.root, self.version, "started")
        self.assertEqual(result["open"], ["Sprint-042"])
        self.assertIn("missing-archive", result["evidence"]["Sprint-042"]["missing"])

    def test_progress_without_archive_is_open_for_both_consumers(self):
        self.plan()
        self.put("memory/V1.0.0/bob/progress.md", "Sprint-042 ✅ 已关闭\n")
        self.assertEqual(opened.closed_sprints(self.root, self.version), set())
        self.assertEqual(opened.scan(self.root, self.version)["open"], ["Sprint-042", "Sprint-043"])
        self.assertEqual(plan_sprints.scan(str(self.root), self.version)["remain_sprints"], ["042", "043"])

    def test_archive_without_progress_is_not_closed_and_blocks_start(self):
        self.plan()
        self.put("memory/V1.0.0/alice/sprints/sprint-042.md", "# Sprint-042\n验收通过\n")
        self.assertEqual(plan_sprints.scan(str(self.root), self.version)["remain_sprints"], ["042", "043"])
        self.assertEqual(opened.scan(self.root, self.version, "started")["open"], ["Sprint-042"])

    def test_cross_user_closure_requires_both_evidence_types(self):
        self.plan()
        self.put("memory/V1.0.0/alice/sprints/sprint-abc042.md", "# Sprint-042\n验收通过\n")
        self.put("memory/V1.0.0/bob/progress.md", "Sprint-042 ✅ 已关闭\nSprint-043 未开始\n")
        self.assertEqual(opened.closed_sprints(self.root, self.version), {"042"})
        self.assertTrue(opened.scan(self.root, self.version, "started")["ok"])
        self.assertEqual(plan_sprints.scan(str(self.root), self.version)["remain_sprints"], ["043"])

    def test_marker_progress_archive_are_not_three_archives(self):
        self.plan()
        opened.record_start(self.root, self.version, "alice", "042")
        self.put("memory/V1.0.0/alice/progress.md", "Sprint-042 ✅ 已关闭\n")
        self.put("memory/V1.0.0/alice/sprints/sprint-042.md", "# Sprint-042\n")
        self.assertFalse(any(x["rule"].startswith("A2") for x in numbering.check(self.root)["findings"]))
        self.put("memory/V1.0.0/bob/sprints/sprint-042.md", "# Sprint-042\n")
        self.assertTrue(any(x["rule"].startswith("A2") for x in numbering.check(self.root)["findings"]))

    def test_history_progress_occupies_number_without_plan(self):
        self.put("memory/V1/bob/progress.md", "Sprint-042 已完成 ✅\n")
        self.assertEqual(numbering.next_number(self.root), (43, 42))

    def test_misc_plan_reference_reserves_number_but_is_not_planned_work(self):
        self.put("docs/plans/V1.0.0/90_开发期增量.md", "回溯 Sprint-042\n")
        self.assertEqual(numbering.next_number(self.root), (43, 42))
        self.assertEqual(opened.planned_sprints(self.root, self.version), set())
        self.assertEqual(plan_sprints.scan(str(self.root), self.version)["all_sprints"], [])

    def test_old_reference_occupies_number_without_claiming_a_second_sprint(self):
        self.put("memory/V0.9.0/alice/sprints/sprint-042.md", "# Sprint-042\n")
        self.put("docs/plans/V1.0.0/90_开发期增量.md", "沿用历史 Sprint-042 的接口\n")
        self.assertEqual(numbering.next_number(self.root), (43, 42))
        self.assertFalse(any(x["rule"].startswith("A1") for x in numbering.check(self.root)["findings"]))
        self.assertTrue(opened.scan(self.root, "V1.0.0", "started")["ok"])

    def test_actual_cli_042_reconciliation(self):
        self.put("memory/V0.9.0/alice/sprints/sprint-041.md", "# Sprint-041\n")
        self.put("docs/plans/V1.0.0/02_研发执行计划-alice.md", "Sprint-042 登录\n")
        def run(script, *args):
            result = subprocess.run([sys.executable, str(SCRIPTS / script), *args,
                                     "--root", str(self.root), "--json"], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)
        self.assertEqual(run("check_sprint_numbering.py", "next")["formatted"], "043")
        self.assertEqual(run("plan_sprints.py", "--version", self.version)["remain_sprints"], ["042"])
        self.assertEqual(run("check_open_sprints.py", "--version", self.version, "--scope", "started")["open"], [])


if __name__ == "__main__":
    unittest.main()
