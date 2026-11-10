#!/usr/bin/env python3
"""风险事实仅来自任务起点增量；真实 Git 仓库回归，静态分析从不执行 SQL。"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import development_scope as scope
import entry_context


class DevelopmentScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aidp-risk-scope-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-q")
        self.put("code/schema.sql", "CREATE TABLE existing (id int);\n")
        self.git("add", ".")
        self.git("-c", "user.name=Probe", "-c", "user.email=probe@example.invalid", "commit", "-qm", "baseline")
        self.since = self.git("rev-parse", "HEAD").strip()

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True, text=True).stdout

    def put(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def analyze(self, **kwargs):
        return scope.analyze_changes(self.root, **kwargs)

    def test_old_create_plus_compatible_alter_is_m_not_newtable(self):
        self.put("code/schema.sql", "CREATE TABLE existing (id int);\nALTER TABLE existing ADD COLUMN note varchar(80);\n")
        result = self.analyze(since=self.since)
        self.assertEqual(result["risk_tier"], "M")
        self.assertTrue(result["has_ddl"])
        self.assertFalse(result["has_new_table"])
        self.assertFalse(result["has_destructive"])
        self.assertFalse(result["ddl_unknown"])

    def test_new_create_and_drop_have_distinct_evidence(self):
        self.put("code/migrate.sql", "CREATE TABLE added (id int);\nDROP TABLE existing;\n")
        result = self.analyze()
        self.assertTrue(result["has_new_table"])
        self.assertTrue(result["has_destructive"])
        self.assertEqual(result["risk_tier"], "L")
        self.assertNotIn("actions", result)
        self.assertNotIn("deploy", result)

    def test_unknown_alter_requires_impact_check(self):
        self.put("code/migrate.sql", "ALTER TABLE existing MODIFY COLUMN id varchar(8);\n")
        result = self.analyze()
        self.assertTrue(result["ddl_unknown"])
        self.assertTrue(result["impact_check_required"])
        self.assertFalse(result["has_destructive"])

    def test_thin_callers_are_cost_only(self):
        for n in range(12):
            self.put(f"code/caller{n}.py", "from api import call\ncall()\n")
        result = self.analyze(facts={"req_count": 1, "page_count": 1})
        self.assertEqual(result["risk_tier"], "S")
        self.assertEqual(result["cost"]["changed_files"], 12)
        self.assertEqual(result["cost"]["band"], "L")

    def test_business_complexity_and_api_are_independent(self):
        for evidence in ({"req_count": 8}, {"page_count": 3}, {"api_count": 1}):
            result = scope.classify_development(evidence)
            self.assertEqual(result["risk_tier"], "M")
        result = scope.classify_development({"has_architecture": True, "changed_files": 1})
        self.assertEqual(result["risk_tier"], "L")

    def test_task_snapshot_excludes_unchanged_preexisting_sql(self):
        self.put("code/old.sql", "CREATE TABLE unrelated (id int);\n")
        context = entry_context.resolve_context(self.root, "sprint-dev", version="V1")
        self.put("code/caller.py", "print('changed')\n")
        result = self.analyze(execution_context=context["execution_context"])
        self.assertFalse(result["has_ddl"])
        self.assertEqual(result["cost"]["changed_files"], 1)

    def test_context_analysis_only_hashes_changed_candidates(self):
        for number in range(20):
            self.put(f"code/unchanged{number}.py", "print('unchanged')\n")
        self.git("add", ".")
        self.git("-c", "user.name=Probe", "-c", "user.email=probe@example.invalid", "commit", "-qm", "unchanged files")
        context = entry_context.resolve_context(self.root, "sprint-dev", version="V1")
        self.put("code/schema.sql", "CREATE TABLE existing (id int);\nALTER TABLE existing ADD COLUMN note text;\n")
        with patch("entry_context.initial_file_hash", wraps=entry_context.initial_file_hash) as hashing:
            result = self.analyze(execution_context=context["execution_context"])
        self.assertEqual(result["scope"]["files"], ["code/schema.sql"])
        self.assertEqual(result["risk_tier"], "M")
        self.assertFalse(result["has_new_table"])
        self.assertLessEqual(hashing.call_count, 2)

    def test_context_declared_paths_exclude_other_tasks_new_table(self):
        context = entry_context.resolve_context(self.root, "sprint-dev", version="V1", write_set=["code/caller.py"])
        self.put("code/caller.py", "print('task')\n")
        self.put("code/other.sql", "CREATE TABLE other_task (id int);\n")
        result = self.analyze(execution_context=context["execution_context"])
        self.assertFalse(result["has_ddl"])
        self.assertEqual(result["scope"]["files"], ["code/caller.py"])
        self.assertEqual(result["scope"]["excluded_files"], ["code/other.sql"])

    def test_dirty_sql_changed_after_entry_is_unknown_not_newtable(self):
        self.put("code/schema.sql", "CREATE TABLE existing (id int);\n-- preexisting change\n")
        context = entry_context.resolve_context(self.root, "sprint-dev", version="V1")
        self.put("code/schema.sql", "CREATE TABLE existing (id int);\n-- preexisting change\nALTER TABLE existing ADD COLUMN note text;\n")
        result = self.analyze(execution_context=context["execution_context"])
        self.assertTrue(result["ddl_unknown"])
        self.assertFalse(result["has_new_table"])

    def test_task_snapshot_includes_committed_and_subsequent_unstaged_change(self):
        context = entry_context.resolve_context(self.root, "sprint-dev", version="V1")
        self.put("code/new.sql", "CREATE TABLE added (id int);\n")
        self.git("add", ".")
        self.git("-c", "user.name=Probe", "-c", "user.email=probe@example.invalid", "commit", "-qm", "task step")
        self.put("code/alter.sql", "ALTER TABLE existing ADD COLUMN note text;\n")
        result = self.analyze(execution_context=context["execution_context"])
        self.assertTrue(result["has_new_table"])
        self.assertEqual({x["path"] for x in result["sql_evidence"]}, {"code/new.sql", "code/alter.sql"})

    def test_sql_comments_strings_and_unchanged_create_do_not_raise_risk(self):
        self.put("code/schema.sql", "-- CREATE TABLE fake (id int);\nCREATE TABLE existing (id int);\nINSERT INTO existing VALUES ('DROP TABLE x;');\n")
        result = self.analyze()
        self.assertFalse(result["has_ddl"])
        self.assertFalse(result["has_new_table"])

    def test_multiline_add_nullable_column(self):
        self.put("code/alter.sql", "ALTER TABLE existing\n ADD COLUMN note\n varchar(80) NULL;\n")
        result = self.analyze()
        self.assertEqual(result["risk_tier"], "M")
        self.assertFalse(result["ddl_unknown"])

    def test_modifying_existing_create_definition_is_unknown(self):
        self.put("code/schema.sql", "CREATE TABLE existing (id varchar(4));\n")
        result = self.analyze()
        self.assertFalse(result["has_new_table"])
        self.assertTrue(result["ddl_unknown"])

    def test_deleted_sql_is_unknown(self):
        (self.root / "code/schema.sql").unlink()
        result = self.analyze()
        self.assertTrue(result["ddl_unknown"])
        self.assertFalse(result["has_new_table"])

    def test_submodule_sql_without_frozen_blob_is_unknown(self):
        with tempfile.TemporaryDirectory(prefix="aidp-risk-child-") as directory:
            child = Path(directory)
            subprocess.run(["git", "init", "-q", str(child)], check=True)
            (child / "schema.sql").write_text("CREATE TABLE old_child (id int);\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(child), "add", "."], check=True)
            subprocess.run(["git", "-C", str(child), "-c", "user.name=Probe", "-c", "user.email=probe@example.invalid",
                            "commit", "-qm", "child"], check=True)
            self.git("-c", "protocol.file.allow=always", "submodule", "add", "-q", str(child), "code/child")
            self.git("-c", "user.name=Probe", "-c", "user.email=probe@example.invalid", "commit", "-qam", "add child")
            context = entry_context.resolve_context(self.root, "sprint-dev", version="V1")
            self.put("code/child/schema.sql", "CREATE TABLE old_child (id int);\nALTER TABLE old_child ADD COLUMN note text;\n")
            for arguments in ({}, {"execution_context": context["execution_context"]}):
                result = self.analyze(**arguments)
                self.assertTrue(result["ddl_unknown"])
                self.assertFalse(result["has_new_table"])
                self.assertIn("code/child/schema.sql", result["scope"]["files"])

    def test_drop_not_null_is_compatible(self):
        self.put("code/migrate.sql", "ALTER TABLE existing ALTER COLUMN id DROP NOT NULL;\n")
        result = self.analyze()
        self.assertEqual(result["risk_tier"], "M")
        self.assertFalse(result["has_destructive"])
        self.assertFalse(result["ddl_unknown"])

    def test_staged_sql_survives_worktree_revert(self):
        self.put("code/schema.sql", "CREATE TABLE existing (id int);\nCREATE TABLE new_staged (id int);\n")
        self.git("add", "code/schema.sql")
        self.put("code/schema.sql", "CREATE TABLE existing (id int);\n")
        result = self.analyze()
        self.assertTrue(result["has_new_table"])

    def test_cli_same_baseline_and_facts(self):
        self.put("code/migrate.sql", "ALTER TABLE existing ADD COLUMN note text;\n")
        result = subprocess.run([sys.executable, str(SCRIPTS / "development_scope.py"), "--root", str(self.root),
                                 "--since", self.since, "--facts-json", '{"req_count":1}', "--json"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["risk_tier"], "M")


if __name__ == "__main__":
    unittest.main()
