#!/usr/bin/env python3
"""离线真实子进程：deployment_ops.py 仅保留 sql-ledger 渲染；备份/note/pending 已删除。"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "deployment_ops.py"


class DeploymentOpsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "memory").mkdir()

    def run_cli(self, *args):
        result = subprocess.run([sys.executable, "-I", str(SCRIPT), "--root", str(self.root), *args],
                                capture_output=True, text=True)
        return result.returncode, (json.loads(result.stdout) if result.stdout.strip() else {}), result.stderr

    def test_removed_subcommands_are_rejected_and_touch_nothing(self):
        for args in (("backup", "--kind", "database", "--target", "dev/db"),
                     ("note", "--version", "V1", "--ref", "code/migrate.sql"),
                     ("pending", "--version", "V1")):
            rc, _out, err = self.run_cli(*args)
            self.assertEqual(rc, 2, args)
            self.assertIn("invalid choice", err)
        self.assertFalse((self.root / "memory/.sprint-autopilot-baseline.json").exists())
        self.assertFalse(list(self.root.glob("docs/**/*")))

    def test_daily_phase_removed_and_ledger_never_touches_baseline(self):
        rc, _out, err = self.run_cli("sql-ledger", "--version", "V1", "--phase", "daily", "--input", "x")
        self.assertEqual(rc, 2)
        self.assertIn("invalid choice", err)
        for phase in ("planning", "release"):
            sql = self.root / "docs/deployment/V1/sql/增量/01_change.sql"
            sql.parent.mkdir(parents=True, exist_ok=True)
            sql.write_text("ALTER TABLE item ADD COLUMN label TEXT;")
            source = self.root / "ops.json"
            source.write_text(json.dumps({"upgrade": [{"database": "dev/app", "scripts": [str(sql.relative_to(self.root))]}],
                                         "password": "must-not-render", "test_count": 90, "analysis": "not-ops"}))
            rc, result, _err = self.run_cli("sql-ledger", "--version", "V1", "--phase", phase, "--input", str(source))
            self.assertEqual(rc, 0, result)
            self.assertNotIn("pending_refs", result)
            output = Path(result["path"]).read_text()
            self.assertEqual(output, "# V1 SQL 执行台账\n\n## 手工升级\n\n| 目标数据库 | SQL脚本路径（按执行顺序） |\n|---|---|\n| dev/app | `docs/deployment/V1/sql/增量/01_change.sql` |\n")
        self.assertFalse((self.root / "memory/.sprint-autopilot-baseline.json").exists())

    def test_release_guard_accepts_machine_evidence_without_analysis_in_ops_docs(self):
        import hashlib
        import importlib.util
        spec = importlib.util.spec_from_file_location("release_baseline_fixture", SCRIPT.parent / "release_baseline_check.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        version = self.root / "docs/deployment/V1"
        (version / "sql/全量").mkdir(parents=True)
        (version / "配置文件/全量").mkdir(parents=True)
        (version / "README.md").write_text("全新部署执行全量；升级执行增量，两套不叠加。")
        (version / "sql/全量/建表说明.md").write_text("目标库 app；执行 01_create.sql。")
        (version / "sql/全量/01_create.sql").write_text("CREATE TABLE app_item(id INT);")
        (version / "配置文件/全量/配置说明.md").write_text("导入 app.yml 后启动服务。")
        (version / "配置文件/全量/app.yml").write_text("port: 8000\n")
        records = {}
        for track in ("sql", "配置文件"):
            files = {p.relative_to(version).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in (version / track / "全量").glob("*") if p.suffix != ".md"}
            records[track] = {"source": "dev/app", "read_method": "metadata-readonly", "excluded": [], "files": files}
        (self.root / "memory/.sprint-autopilot-baseline.json").write_text(json.dumps({"deployment_baseline_checks": {"V1": records}}))
        report = module.Report()
        module.check_structure(version, report)
        self.assertFalse(report.errors, report.errors)
        (version / "sql/全量/01_create.sql").write_text("CREATE TABLE changed(id INT);")
        changed = module.Report()
        module.check_structure(version, changed)
        self.assertTrue(changed.errors)

    def test_automatic_migration_and_no_sql_do_not_generate_manual_steps(self):
        source = self.root / "ops.json"
        for data, expected in (({"automatic": True}, "应用启动时自动迁移，无需重复手工执行。"),
                               ({}, "本版本无须手工执行 SQL。")):
            source.write_text(json.dumps(data))
            rc, result, _err = self.run_cli("sql-ledger", "--version", "V1", "--phase", "release", "--input", str(source))
            self.assertEqual(rc, 0, result)
            self.assertEqual(Path(result["path"]).read_text(), f"# V1 SQL 执行台账\n\n{expected}\n")


if __name__ == "__main__":
    unittest.main()
