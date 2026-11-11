#!/usr/bin/env python3
"""SQL 整理守恒校验：整型比较、按语句多重集合比对、空侧 fail-closed（回归 release-3 `|| echo 0` 恒放行）。"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]
SCRIPT = SCRIPTS / "sql_reorg.py"


class SqlReorgCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aidp-sql-reorg-")
        self.addCleanup(self.temp.cleanup)
        self.orig = Path(self.temp.name) / "orig"
        self.new = Path(self.temp.name) / "new"
        self.orig.mkdir()
        self.new.mkdir()

    def put(self, d, name, text):
        (d / name).write_text(text, encoding="utf-8")

    def run_check(self, *extra):
        r = subprocess.run([sys.executable, str(SCRIPT), "check", "--orig", str(self.orig),
                            "--new", str(self.new), "--json", *extra], capture_output=True, text=True)
        return r.returncode, (json.loads(r.stdout) if r.stdout.strip() else None), r.stderr

    def test_same_statements_regrouped_and_recased_pass(self):
        self.put(self.orig, "01_a.sql", "CREATE TABLE a (id int);\nINSERT INTO a VALUES (1);\n")
        self.put(self.orig, "02_b.sql", "ALTER TABLE a ADD c int;\n")
        self.put(self.new, "01_aDDL.sql", "  create table a\n (id int);\nALTER TABLE a ADD c int;\n")
        self.put(self.new, "02_a初始化.sql", "-- note\nINSERT INTO a VALUES (1);\n")
        rc, out, _ = self.run_check()
        self.assertEqual(rc, 0, out)
        self.assertTrue(out["passed"])
        self.assertEqual((out["orig_count"], out["new_count"]), (3, 3))

    def test_new_side_zero_statements_fails(self):
        # G-01 原 bug：新侧 0 条时 shell 变量成 "0\n0"，比较报错被当作「条件为假」放行
        self.put(self.orig, "01_a.sql", "CREATE TABLE a (id int);\nINSERT INTO a VALUES (1);\n")
        self.put(self.new, "01_a.sql", "-- 全是注释\n")
        rc, out, _ = self.run_check()
        self.assertEqual(rc, 1)
        self.assertFalse(out["passed"])
        self.assertEqual(out["new_count"], 0)

    def test_new_dir_without_sql_fails(self):
        self.put(self.orig, "01_a.sql", "CREATE TABLE a (id int);\n")
        rc, out, _ = self.run_check()
        self.assertEqual(rc, 1)
        self.assertFalse(out["passed"])

    def test_same_count_different_statement_fails(self):
        self.put(self.orig, "01_a.sql", "CREATE TABLE a (id int);\n")
        self.put(self.new, "01_a.sql", "CREATE TABLE b (id int);\n")
        rc, out, _ = self.run_check()
        self.assertEqual(rc, 1)
        self.assertEqual(len(out["missing"]), 1)
        self.assertEqual(len(out["extra"]), 1)

    def test_string_literal_case_is_significant(self):
        self.put(self.orig, "01_a.sql", "INSERT INTO a VALUES ('Abc');\n")
        self.put(self.new, "01_a.sql", "INSERT INTO a VALUES ('abc');\n")
        rc, out, _ = self.run_check()
        self.assertEqual(rc, 1)

    def test_rollback_script_excluded_by_default_and_orig_empty_fails_closed(self):
        self.put(self.orig, "99_回滚脚本.sql", "DROP TABLE a;\n")
        self.put(self.new, "01_a.sql", "CREATE TABLE a (id int);\n")
        rc, out, _ = self.run_check()
        self.assertEqual(rc, 1)
        self.assertEqual(out["orig_count"], 0)

    def test_rollback_script_not_counted(self):
        self.put(self.orig, "01_a.sql", "CREATE TABLE a (id int);\n")
        self.put(self.orig, "99_回滚脚本.sql", "DROP TABLE a;\n")
        self.put(self.new, "01_a.sql", "CREATE TABLE a (id int);\n")
        rc, out, _ = self.run_check()
        self.assertEqual(rc, 0, out)

    def test_missing_dir_is_usage_error(self):
        r = subprocess.run([sys.executable, str(SCRIPT), "check", "--orig", str(self.orig / "nope"),
                            "--new", str(self.new), "--json"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
