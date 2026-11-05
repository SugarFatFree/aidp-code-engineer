#!/usr/bin/env python3
"""原子编号保留：源文档 seed、作用域、损坏拒绝及进程并发。"""
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import alloc_id
from aidp_paths import id_alloc_ledger


class AllocIdTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def put(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def alloc(self, kind="C", count=1, **kw):
        return alloc_id.allocate(self.root, kind, count, "agent-a", **kw)

    def test_seed_and_reserved_holes_survive_source_removal(self):
        path = self.put("docs/requirements/V1/研发需求/90_开发期增量.md", "## C-008 修改\n")
        self.assertEqual(self.alloc(count=5, version="V1")["ids"],
                         ["C-%03d" % n for n in range(9, 14)])
        path.unlink()
        self.assertEqual(self.alloc(version="V1")["ids"], ["C-014"])
        self.assertTrue(alloc_id.check_ledger(self.root)["passed"])

    def test_defaults_seed_all_versions_without_merging_c_domains(self):
        self.put("docs/requirements/V1/研发需求/90_开发期增量.md", "## C-008 一\n")
        self.put("docs/requirements/V2/研发需求/90_开发期增量.md", "## C-020 二\n")
        self.put("docs/bugfix/V2/bugs.md", "| C-999 | 缺陷 |\n")
        self.assertEqual(self.alloc()["ids"], ["C-021"])
        self.assertEqual(self.alloc(version="V1")["ids"], ["C-022"])
        self.assertEqual(self.alloc(scope="bugs", version="V2")["ids"], ["C-1000"])

    def test_versions_and_prefix_namespaces_are_independent(self):
        self.put("docs/requirements/V1/研发需求/01_需求.md", "### REQ-009 一\n### REQ-3P-080 能力\n### REQ-V1-031 二\n")
        self.assertEqual(self.alloc("REQ", version="V1")["ids"], ["REQ-010"])
        self.assertEqual(self.alloc("REQ", version="V2")["ids"], ["REQ-001"])
        self.assertEqual(self.alloc("REQ", version="V1", prefix="REQ-3P")["ids"], ["REQ-3P-081"])
        self.assertEqual(self.alloc("REQ", version="V1", prefix="REQ-V1")["ids"], ["REQ-V1-032"])

    def test_all_kinds_and_alphabetic_sequence_prefix(self):
        for kind, path in (("BUG", "docs/bugfix/V1/bugs.md"),
                           ("Q", "docs/requirements/V1/研发需求/99_待澄清问题清单.md"),
                           ("D", "docs/design/detail/V1/99_待澄清问题清单.md"),
                           ("ADR", "memory/systemPatterns.md")):
            self.put(path, "## %s-014 条目\n" % kind)
            self.assertEqual(self.alloc(kind)["ids"], [kind + "-015"])
        self.put("docs/requirements/V1/研发需求/01_需求.md", "## 登录（REQ-V1-A02）\n")
        self.assertEqual(self.alloc("REQ", prefix="REQ-V1-A")["ids"], ["REQ-V1-A003"])

    def test_project_adr_cannot_be_split_by_version_argument(self):
        self.put("memory/systemPatterns.md", "## ADR-014 已有决策\n")
        with self.assertRaises(ValueError):
            self.alloc("ADR", version="V1")
        self.assertFalse(Path(id_alloc_ledger(self.root)).exists())

    def test_child_id_seeds_parent_without_treating_child_as_parent_definition(self):
        self.put("docs/requirements/V1/研发需求/90_开发期增量.md", "## C-036-01 子条目\n## C-036-02 子条目\n")
        self.assertEqual(self.alloc()["ids"], ["C-037"])
        self.assertTrue(alloc_id.check_ledger(self.root)["passed"])

    def test_rereads_legacy_additions_after_first_allocation(self):
        self.alloc("REQ", version="V1")
        self.put("docs/requirements/V1/研发需求/01_需求.md", "### REQ-050 历史合入\n")
        self.assertEqual(self.alloc("REQ", version="V1")["ids"], ["REQ-051"])

    def test_references_indexes_fences_and_four_family_copies_are_not_duplicates(self):
        for family in ("requirements/V1/研发需求", "design/detail/V1", "plans/V1", "testing/V1/研发自测"):
            self.put("docs/" + family + "/90_开发期增量.md", "## C-003 改动\n参见 C-003。\n")
        self.put("docs/requirements/V1/研发需求/01_需求.md", "| REQ-007 | 索引 |\n### REQ-007 正文\n参考 REQ-007。\n```md\n### REQ-007 示例\n```\n")
        self.put("docs/requirements/V1/研发需求/00_索引.md", "| REQ-007 | [链接](01_需求.md) |\n")
        self.put("docs/init/demo.md", "### REQ-999 教学示例\n### REQ-999 教学示例\n")
        self.alloc(version="V1")
        self.alloc("REQ", version="V1")
        self.assertTrue(alloc_id.check_ledger(self.root)["passed"])

    def test_real_duplicate_definitions_fail_even_with_reservation(self):
        self.alloc("REQ", version="V1")
        for name in ("01_需求.md", "02_需求.md"):
            self.put("docs/requirements/V1/研发需求/" + name, "### REQ-001 不同定义\n")
        report = alloc_id.check_ledger(self.root)
        self.assertFalse(report["passed"])
        self.assertIn("duplicate-definition", {e["check"] for e in report["errors"]})

    def test_duplicate_rows_fail_but_cross_version_same_ids_pass(self):
        self.put("docs/bugfix/V1/bugs.md", "| BUG-001 | 一 |\n| BUG-001 | 二 |\n")
        self.assertFalse(alloc_id.check_ledger(self.root)["passed"])
        self.put("docs/bugfix/V1/bugs.md", "| BUG-001 | 一 |\n")
        self.put("docs/bugfix/V2/bugs.md", "| BUG-001 | 二 |\n")
        self.assertTrue(alloc_id.check_ledger(self.root)["passed"])

    def test_overlapping_source_scopes_share_reserved_high_water(self):
        a = self.alloc("REQ", scope="docs/requirements/V1", count=3)
        b = self.alloc("REQ", scope="docs/requirements/V1/研发需求", count=2)
        c = self.alloc("REQ", version="V1")
        self.assertEqual(a["ids"], ["REQ-001", "REQ-002", "REQ-003"])
        self.assertEqual(b["ids"], ["REQ-004", "REQ-005"])
        self.assertEqual(c["ids"], ["REQ-006"])
        self.assertTrue(alloc_id.check_ledger(self.root)["passed"])

    def test_disjoint_custom_scopes_remain_independent_in_checker(self):
        for module in ("module-a", "module-b"):
            scope = "docs/requirements/V1/" + module
            self.assertEqual(self.alloc("REQ", scope=scope)["ids"], ["REQ-001"])
            self.put(scope + "/01.md", "### REQ-001 模块内需求\n")
        self.assertTrue(alloc_id.check_ledger(self.root)["passed"])

    def test_linked_reference_rows_do_not_become_definitions(self):
        self.put("docs/requirements/V1/研发需求/01.md", "### REQ-001 正文\n")
        self.put("docs/requirements/V1/研发需求/02.md", "| REQ-001 | [上游](01.md#req-001) |\n")
        self.alloc("REQ", version="V1")
        self.assertTrue(alloc_id.check_ledger(self.root)["passed"])

    def test_corrupt_ledger_fails_closed_without_modification(self):
        ledger = self.put("memory/.aidp/id-alloc.jsonl", '{"kind":"C"}\n')
        before = ledger.read_bytes()
        with self.assertRaises(ValueError):
            self.alloc()
        self.assertEqual(ledger.read_bytes(), before)
        self.assertFalse(alloc_id.check_ledger(self.root)["passed"])

    def test_truncated_and_overlapping_records_fail_closed(self):
        self.alloc()
        ledger = Path(id_alloc_ledger(self.root))
        valid = ledger.read_bytes()
        for invalid in (valid.rstrip(b"\n"), valid + valid, b"", valid + b"\n"):
            ledger.write_bytes(invalid)
            with self.assertRaises(ValueError):
                self.alloc()
        ledger.write_bytes(valid)
        self.assertTrue(alloc_id.check_ledger(self.root)["passed"])

    def test_tc_default_testing_scope_and_module_prefix(self):
        self.put("docs/testing/V1/研发自测/02_订单.md", "## TC-009 旧用例\n## TC-PTS-014 积分用例\n")
        self.put("docs/testing/V1/正式用例/02_订单.md", "## TC-PTS-018 另一用例\n")
        self.put("docs/testing/V2/研发自测/02_订单.md", "## TC-PTS-050 另一版本\n")
        self.assertEqual(self.alloc("TC", version="V1")["ids"], ["TC-010"])
        self.assertEqual(self.alloc("TC", version="V1", prefix="TC-PTS")["ids"], ["TC-PTS-019"])
        self.assertEqual(self.alloc("TC", version="V1", prefix="TC-ORD")["ids"], ["TC-ORD-001"])
        self.assertEqual(self.alloc("TC", prefix="TC-PTS")["ids"], ["TC-PTS-051"])
        self.assertTrue(alloc_id.check_ledger(self.root)["passed"])

    def test_tc_duplicate_definitions_fail_but_references_pass(self):
        self.put("docs/testing/V1/研发自测/02_订单.md", "## TC-PTS-001 正文\n参考 TC-PTS-001。\n")
        other = self.put("docs/testing/V1/研发自测/03_积分.md", "| TC-PTS-001 | [来源](02_订单.md) |\n")
        self.alloc("TC", version="V1", prefix="TC-PTS")
        self.assertTrue(alloc_id.check_ledger(self.root)["passed"])
        other.write_text("## TC-PTS-001 另一定义\n", encoding="utf-8")
        self.assertFalse(alloc_id.check_ledger(self.root)["passed"])

    def test_bug_scope_seeds_testing_issue_lists_and_ignores_other_kinds(self):
        self.put("docs/bugfix/V1/bugs.md", "| C-003 | 缺陷 |\n")
        self.put("docs/testing/V1/正式用例/问题清单.md", "| C-008 | 正式测试缺陷 |\n| TC-999 | 用例引用 |\n")
        self.put("docs/testing/V1/研发自测/问题清单.md", "| C-012 | 自测缺陷 |\n| BUG-004 | 另一缺陷 |\n")
        self.put("docs/testing/V1/研发自测/_开发期用例增量.md", "- C-090 · 11-05 · 开发变更\n")
        self.assertEqual(self.alloc("C", version="V1", scope="bugs")["ids"], ["C-013"])
        self.assertEqual(self.alloc("BUG", version="V1")["ids"], ["BUG-005"])
        self.assertEqual(self.alloc("C", version="V1")["ids"], ["C-091"])
        self.assertEqual(self.alloc("C", version="V1", scope="bugs")["ids"], ["C-014"])
        self.assertTrue(alloc_id.check_ledger(self.root)["passed"])

    def test_change_copies_do_not_become_bug_definitions(self):
        for family in ("requirements/V1/研发需求", "testing/V1/研发自测"):
            self.put("docs/" + family + "/_开发期增量.md", "- C-003 · 11-05 · 同一变更的各族记录\n")
        self.put("docs/testing/V1/正式用例/问题清单.md", "| C-003 | 独立测试缺陷 |\n")
        self.alloc("C", version="V1")
        self.alloc("C", version="V1", scope="bugs")
        self.assertTrue(alloc_id.check_ledger(self.root)["passed"])
        self.put("docs/testing/V1/研发自测/问题清单.md", "| C-003 | 撞号缺陷 |\n")
        self.assertFalse(alloc_id.check_ledger(self.root)["passed"])

    def test_historical_bug_definitions_share_scope_across_testing_and_bugfix(self):
        self.put("docs/bugfix/V1/bugs.md", "| C-003 | 一条缺陷 |\n")
        self.put("docs/testing/V1/正式用例/问题清单.md", "| C-003 | 另一条缺陷 |\n")
        report = alloc_id.check_ledger(self.root)
        self.assertFalse(report["passed"])
        self.assertEqual(report["errors"][0]["check"], "duplicate-definition")

    def test_invalid_args_do_not_create_ledger(self):
        for kw in ({"count": 0}, {"kind": "INVALID"}, {"scope": "../outside"}, {"prefix": "BUG"}):
            with self.assertRaises(ValueError):
                self.alloc(**kw)
        self.assertFalse(Path(id_alloc_ledger(self.root)).exists())

    def test_lock_failure_does_not_allocate(self):
        with patch("fcntl.flock", side_effect=OSError("lock unavailable")):
            with self.assertRaises(OSError):
                self.alloc()
        self.assertFalse(Path(id_alloc_ledger(self.root)).exists())

    def test_cli_json_and_concurrent_processes(self):
        def invoke(i):
            p = subprocess.run([sys.executable, str(SCRIPTS / "alloc_id.py"), "--root", str(self.root),
                                "--kind", "C", "--count", "5", "--owner", "agent-%d" % i, "--json"],
                               capture_output=True, text=True, timeout=20)
            self.assertEqual(p.returncode, 0, p.stderr)
            return json.loads(p.stdout)["ids"]
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            batches = list(pool.map(invoke, range(8)))
        ids = [item for batch in batches for item in batch]
        self.assertEqual(len(set(ids)), 40)
        self.assertEqual(set(ids), {"C-%03d" % n for n in range(1, 41)})
        self.assertTrue(alloc_id.check_ledger(self.root)["passed"])

    def test_real_change_bullets_and_known_mismatch_references(self):
        text = ("## 已知失准点\n- C-003：参见待级联条目\n"
                "## 待级联\n- C-003 · 11-05 10:00 · 真实改动 · sprint-001\n")
        path = self.put("docs/requirements/V1/研发需求/_开发期需求增量.md", text)
        self.put("docs/design/detail/V1/_开发期设计增量.md", text)
        self.alloc(version="V1")
        self.assertTrue(alloc_id.check_ledger(self.root)["passed"])
        path.write_text(text + "- C-003 · 11-05 11:00 · 另一条改动\n", encoding="utf-8")
        self.assertFalse(alloc_id.check_ledger(self.root)["passed"])

    def test_named_scopes_do_not_collide_with_unrelated_requirements(self):
        self.put("docs/requirements/V1/研发需求/_开发期需求增量.md", "- C-010 · 11-05 · 改动\n")
        self.put("docs/requirements/V1/研发需求/01_需求.md", "### REQ-001 需求\n")
        self.assertEqual(self.alloc(version="V1")["ids"], ["C-011"])
        self.assertEqual(self.alloc("REQ", version="V1")["ids"], ["REQ-002"])

    def test_symlinked_source_directory_fails_closed(self):
        outside = self.root / "external"
        outside.mkdir()
        (outside / "req.md").write_text("### REQ-010 旧需求\n", encoding="utf-8")
        directory = self.root / "docs/requirements/V1"
        directory.mkdir(parents=True)
        (directory / "研发需求").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.alloc("REQ")

    def test_existing_lock_blocks_another_process_until_release(self):
        import fcntl
        from baseline_edit import lock_path
        lock = Path(lock_path(id_alloc_ledger(self.root)))
        lock.parent.mkdir(parents=True)
        with lock.open("a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            code = ("import sys; sys.path.insert(0, sys.argv[1]); import alloc_id; "
                    "print('ready', flush=True); alloc_id.allocate(sys.argv[2], 'C', 1, 'child')")
            p = subprocess.Popen([sys.executable, "-c", code, str(SCRIPTS), str(self.root)],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                self.assertEqual(p.stdout.readline().strip(), "ready")
                with self.assertRaises(subprocess.TimeoutExpired):
                    p.wait(timeout=0.1)
                self.assertFalse(Path(id_alloc_ledger(self.root)).exists())
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)
                _, err = p.communicate(timeout=10)
            self.assertEqual(p.returncode, 0, err)
        self.assertTrue(alloc_id.check_ledger(self.root)["passed"])

    def test_check_is_read_only_when_ledger_missing(self):
        self.assertTrue(alloc_id.check_ledger(self.root)["passed"])
        self.assertFalse((self.root / "memory").exists())


if __name__ == "__main__":
    unittest.main()
