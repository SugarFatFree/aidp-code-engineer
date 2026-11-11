#!/usr/bin/env python3
"""离线真实子进程：备份额度/并发/回执与部署文档生命周期。"""
from datetime import datetime, timezone
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
        self.record = self.root / "memory/backups.json"
        self.record.write_text(json.dumps({"verified_at": datetime.now(timezone.utc).isoformat(), "backups": []}))
        # 此假命令只创建测试目录中的非业务文本，不复制 DB/服务数据。
        self.fake = self.root / "fake_backup.py"
        self.fake.write_text('''import datetime, json, pathlib, time
p = pathlib.Path("calls")
p.write_text(p.read_text() + "call\\n" if p.exists() else "call\\n")
time.sleep(0.08)
pathlib.Path("fixture.bak").write_text("offline fixture")
print(json.dumps({"backed_up_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  "targets": ["dev/db", "dev/service"], "artifacts": ["fixture.bak"]}))
''')
        self.config = {"deployment": {"backup": {"max_per_day": 1, "timezone": "UTC",
                       "record_file": "memory/backups.json", "skip_args": ["--existing-project-skip"],
                       "commands": {k: [sys.executable, "-I", str(self.fake)]
                                    for k in ("database", "cold", "migration")}}}}
        self.save_config()

    def save_config(self):
        policy = self.config["deployment"]["backup"]
        lines = ["deployment:", "  backup:"]
        for key, value in policy.items():
            if key == "commands":
                lines.append("    commands:")
                lines += ["      " + kind + ": " + json.dumps(argv) for kind, argv in value.items()]
            else:
                lines.append("    " + key + ": " + json.dumps(value))
        (self.root / "memory/aidp-config.yaml").write_text("\n".join(lines) + "\n")

    def run_cli(self, *args):
        result = subprocess.run([sys.executable, "-I", str(SCRIPT), "--root", str(self.root), *args],
                                capture_output=True, text=True)
        return result.returncode, json.loads(result.stdout)

    def backup(self, kind="database", target="dev/db"):
        return self.run_cli("backup", "--kind", kind, "--target", target)

    def calls(self):
        path = self.root / "calls"
        return len(path.read_text().splitlines()) if path.exists() else 0

    def test_standard_backup_fence_enforces_parent_deploy_grant(self):
        import os
        import re
        sys.path.insert(0, str(SCRIPT.parent))
        import entry_context
        (self.root / "app.py").write_text("value = 1\n")
        context = entry_context.resolve_context(self.root, "sprint-dev", version="V1", write_set=["app.py"])
        source = SCRIPT.parents[1] / "reference/部署操作约定.md"
        fences = re.findall(r"```bash\n(.*?)```", source.read_text(), re.S)
        fence = next(text for text in fences if "deployment_ops.py backup" in text)
        fence = fence.replace("{{AIDP_HOME}}", str(SCRIPT.parents[1]))
        env = dict(os.environ, EXECUTION_CONTEXT=context["execution_context"], BACKUP_TARGET="dev/db")
        denied = subprocess.run(["bash", "-c", fence], cwd=self.root, env=env, capture_output=True, text=True)
        self.assertNotEqual(denied.returncode, 0, denied.stdout + denied.stderr)
        self.assertEqual(self.calls(), 0)
        self.assertEqual(json.loads(self.record.read_text())["backups"], [])
        self.assertEqual(self.run_cli("pending", "--version", "V1")[0], 0)
        granted = entry_context.revise_context(self.root, context["execution_context"],
            additional_grants=["deploy"], authorization_source={"kind": "user-text", "request_id": "offline-deploy",
                                                               "text": "部署到测试环境"})
        env["EXECUTION_CONTEXT"] = granted["execution_context"]
        allowed = subprocess.run(["bash", "-c", fence], cwd=self.root, env=env, capture_output=True, text=True)
        self.assertEqual(allowed.returncode, 0, allowed.stdout + allowed.stderr)
        self.assertEqual(self.calls(), 1)

    def test_second_deploy_and_migration_reuse_actual_time(self):
        rc, first = self.backup()
        self.assertEqual(rc, 0, first)
        original = self.record.read_text()
        for kind in ("database", "cold", "migration"):
            rc, second = self.backup(kind)
            self.assertEqual(rc, 0, second)
            self.assertEqual(second["status"], "reused")
            self.assertEqual(second["backup"]["backed_up_at"], first["backup"]["backed_up_at"])
            self.assertEqual(second["skip_args"], ["--existing-project-skip"])
        self.assertEqual(self.calls(), 1)
        self.assertEqual(self.record.read_text(), original)

    def test_cross_kind_target_gap_cannot_expand_quota(self):
        self.assertEqual(self.backup()[0], 0)
        rc, result = self.backup("migration", "prod/db")
        self.assertEqual(rc, 2)
        self.assertIn("缺口", result["reason"])
        self.assertEqual(self.calls(), 1)

    def test_parallel_backup_types_share_one_lock(self):
        processes = [subprocess.Popen([sys.executable, "-I", str(SCRIPT), "--root", str(self.root),
                     "backup", "--kind", kind, "--target", "dev/db"], stdout=subprocess.PIPE,
                     stderr=subprocess.PIPE, text=True) for kind in ("database", "migration", "cold")]
        results = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0, stderr + stdout)
            results.append(json.loads(stdout)["status"])
        self.assertEqual(results.count("succeeded"), 1)
        self.assertEqual(results.count("reused"), 2)
        self.assertEqual(self.calls(), 1)

    def test_missing_conflicting_or_lost_records_never_fake_reuse(self):
        good = self.record.read_text()
        self.record.unlink()
        self.assertEqual(self.backup()[0], 2)
        self.record.write_text(good)
        self.assertEqual(self.backup()[0], 0)
        rows = json.loads(self.record.read_text())
        rows["backups"].append(dict(rows["backups"][0]))
        self.record.write_text(json.dumps(rows))
        self.assertEqual(self.backup("migration")[0], 2)
        rows["backups"].pop()
        self.record.write_text(json.dumps(rows))
        (self.root / "fixture.bak").unlink()
        self.assertEqual(self.backup()[0], 2)
        self.assertEqual(self.calls(), 1)

    def test_failed_command_is_visible_and_consumes_quota(self):
        self.fake.write_text('import sys\nfrom pathlib import Path\nPath("calls").write_text("call\\n")\nsys.exit(9)\n')
        rc, result = self.backup()
        self.assertEqual(rc, 1)
        self.assertEqual(result["status"], "failed")
        self.assertIn("exit=9", result["backup"]["error"])
        self.assertEqual(self.backup("cold")[0], 2)
        self.assertEqual(self.calls(), 1)

    def test_process_not_started_does_not_consume_actual_quota(self):
        self.config["deployment"]["backup"]["commands"]["database"] = [str(self.root / "missing-command")]
        self.save_config()
        rc, result = self.backup()
        self.assertEqual(rc, 1)
        self.assertEqual(result["status"], "not-executed")
        self.assertEqual(self.calls(), 0)
        self.assertEqual(self.backup("migration")[0], 0)
        self.assertEqual(self.calls(), 1)

    def test_successful_backup_followup_failure_remains_visible(self):
        self.fake.write_text(self.fake.read_text() + "\nimport sys\nsys.exit(7)\n")
        rc, result = self.backup()
        self.assertEqual(rc, 1)
        self.assertEqual(result["status"], "post-backup-failed")
        self.assertEqual(result["backup"]["status"], "succeeded")
        self.assertEqual(self.backup("migration")[1]["status"], "reused")
        self.assertEqual(self.calls(), 1)

    def test_completed_backup_recording_failure_preserves_operation_fact(self):
        import importlib.util
        from unittest.mock import patch
        spec = importlib.util.spec_from_file_location("deployment_ops_fixture", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        original = module.write_json
        count = [0]
        def fail_final(path, value):
            count[0] += 1
            if count[0] == 2:
                raise OSError("fixture write failure")
            original(path, value)
        with patch.object(module, "write_json", side_effect=fail_final):
            result = module.backup(self.root, "database", ["dev/db"])
        self.assertEqual(result["status"], "recording-failed")
        self.assertEqual(result["operation_status"], "succeeded")
        self.assertTrue(result["backup"]["backed_up_at"])
        self.assertEqual(self.backup("migration")[0], 2)
        self.assertEqual(self.calls(), 1)

    def test_forged_receipt_time_not_success(self):
        self.fake.write_text(self.fake.read_text().replace('datetime.datetime.now(datetime.timezone.utc).isoformat()',
                                                         '"2000-01-01T00:00:00+00:00"'))
        rc, result = self.backup()
        self.assertEqual(rc, 1)
        self.assertEqual(result["status"], "failed")
        self.assertNotIn("backed_up_at", result["backup"])

    def test_daily_deployment_records_only_and_planning_release_render_minimal_sql(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.email", "fixture@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.name", "fixture"], check=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "--allow-empty", "-qm", "fixture"], check=True)
        before = subprocess.check_output(["git", "-C", str(self.root), "rev-parse", "HEAD"])
        rc, result = self.run_cli("note", "--version", "V1", "--ref", "code/migrate.sql")
        self.assertEqual(rc, 0, result)
        self.assertEqual(self.run_cli("sql-ledger", "--version", "V1", "--phase", "daily")[1]["status"], "deferred")
        self.assertFalse(list(self.root.glob("docs/**/*.md")))
        self.assertEqual(before, subprocess.check_output(["git", "-C", str(self.root), "rev-parse", "HEAD"]))
        for phase in ("planning", "release"):
            sql = self.root / "docs/deployment/V1/sql/增量/01_change.sql"
            sql.parent.mkdir(parents=True, exist_ok=True)
            sql.write_text("ALTER TABLE item ADD COLUMN label TEXT;")
            source = self.root / "ops.json"
            source.write_text(json.dumps({"upgrade": [{"database": "dev/app", "scripts": [str(sql.relative_to(self.root))]}],
                                         "password": "must-not-render", "test_count": 90, "analysis": "not-ops"}))
            rc, result = self.run_cli("sql-ledger", "--version", "V1", "--phase", phase, "--input", str(source))
            self.assertEqual(rc, 0, result)
            self.assertEqual(result["pending_refs"], ["code/migrate.sql"])
            output = Path(result["path"]).read_text()
            self.assertEqual(output, "# V1 SQL 执行台账\n\n## 手工升级\n\n| 目标数据库 | SQL脚本路径（按执行顺序） |\n|---|---|\n| dev/app | `docs/deployment/V1/sql/增量/01_change.sql` |\n")
        self.assertEqual(before, subprocess.check_output(["git", "-C", str(self.root), "rev-parse", "HEAD"]))

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
            rc, result = self.run_cli("sql-ledger", "--version", "V1", "--phase", "release", "--input", str(source))
            self.assertEqual(rc, 0, result)
            self.assertEqual(Path(result["path"]).read_text(), f"# V1 SQL 执行台账\n\n{expected}\n")


if __name__ == "__main__":
    unittest.main()
