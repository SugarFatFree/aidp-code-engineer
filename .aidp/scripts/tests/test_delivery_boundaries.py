#!/usr/bin/env python3
"""通知配置与报告交付边界：临时项目、离线子进程、无网络/真实渠道。"""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import notify


def load_emit():
    spec = importlib.util.spec_from_file_location("delivery_emit_test", SCRIPTS / "emit-report.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NotifyConfigurationTests(unittest.TestCase):
    def test_legacy_managed_defaults_custom_channels_untouched(self):
        custom = {"type": "command", "command": shlex.quote(sys.executable) + " -c 'pass'",
                  "args": ["--destination", "custom-destination"], "custom": {"mode": "keep"}}
        original = {"enabled": True, "channels": [custom]}
        before = copy.deepcopy(original)
        migrated, report = notify.migrate_notify_config(original)
        self.assertEqual(original, before)
        self.assertEqual(migrated["channels"], before["channels"])
        self.assertEqual(set(report["added_fields"]), {"fallback", "channel_ready_card"})
        self.assertTrue(migrated["fallback"])
        self.assertFalse(migrated["channel_ready_card"])
        self.assertFalse(report["migration_complete"])
        again, after = notify.migrate_notify_config(migrated)
        self.assertEqual(again, migrated)
        self.assertTrue(after["migration_complete"])
        self.assertTrue(after["ready"])
        self.assertFalse(after["delivery_verified"])

    def test_nonempty_channels_missing_fields_remain_unavailable(self):
        section = {"enabled": True, "fallback": False, "channel_ready_card": True,
                   "channels": [{"type": "lark-cli", "bin": sys.executable, "args": ["custom"]},
                                {"type": "feishu"}, {"type": "command"}]}
        with patch.object(notify, "_post_json", side_effect=AssertionError("network forbidden")), \
                patch.object(notify.subprocess, "run", side_effect=AssertionError("probe forbidden")):
            migrated, report = notify.migrate_notify_config(section)
        self.assertEqual(migrated, section)
        self.assertFalse(report["ready"])
        self.assertFalse(report["migration_complete"])
        self.assertTrue(all(item["status"] == "unavailable" for item in report["channels"]))
        self.assertTrue(all("--check-config" in item["repair"] for item in report["channels"]))
        reasons = " ".join(item["reason"] for item in report["channels"])
        for field in ("chat_id", "webhook_env", "command"):
            self.assertIn(field, reasons)

    def test_command_argv_diagnosis_without_guessing_target(self):
        for command in ("missing-aidp-delivery-executable", "'unterminated", "$SENDER --target x"):
            self.assertFalse(notify.channel_ready({"type": "command", "command": command})[0])
        ready, reason = notify.channel_ready({"type": "command", "command": sys.executable + " unknown-target"})
        self.assertTrue(ready)
        self.assertIn("下游确认", reason)
        self.assertFalse(notify.channel_ready({"type": "lark-cli", "chat_id": "<chat id>"})[0])

    def test_generic_schema_completion_is_independent_from_local_readiness(self):
        section = {"enabled": True, "fallback": True, "channel_ready_card": False,
                   "channels": [{"type": "command", "command": "aidp-test-missing-executable --target opaque"}]}
        _, report = notify.migrate_notify_config(section)
        self.assertTrue(report["migration_complete"])
        self.assertEqual(report["migration_scope"], "generic-schema-only")
        self.assertFalse(report["ready"])
        self.assertFalse(report["delivery_verified"])
        section["channels"] = []
        section["enabled"] = False
        _, empty = notify.migrate_notify_config(section)
        self.assertTrue(empty["migration_complete"])
        self.assertFalse(empty["ready"])
        self.assertEqual(empty["reason"], "notify.enabled=false")

    def test_check_config_subprocess_is_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "memory").mkdir()
            config = root / "memory/aidp-config.yaml"
            config.write_text("notify:\n  enabled: true\n  channels:\n    - type: lark-cli\n", encoding="utf-8")
            before = config.read_bytes()
            result = subprocess.run([sys.executable, str(SCRIPTS / "notify.py"), "--repo-root", str(root),
                                     "--check-config", "--json"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 3, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["status"], "unavailable")
            self.assertFalse(report["migration_complete"])
            self.assertEqual(config.read_bytes(), before)
            self.assertEqual(sorted(p.name for p in root.iterdir()), ["memory"])


class ReportDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.version = "V0.1.0"
        self.build = self.version + "_build1001"
        (self.root / "memory").mkdir()
        self.baseline = self.root / "memory/.sprint-autopilot-baseline.json"
        self.baseline.write_text(json.dumps({"versions": {self.version: {"builds": [{"build": self.build}]}}}))
        # 故意保留 FAIL，报告交付不能要求 PASS 或再次运行测试。
        self.payload = {"build": self.build, "version": self.version,
                        "summary": {"total": 1, "pass": 0, "fail": 1, "block": 0, "skip": 0, "passRate": 0},
                        "cases": [{"id": "TC-1", "title": "真实失败", "result": "fail"}],
                        "testCommand": "touch TESTS_WERE_RERUN"}
        draft = self.root / "input.json"
        draft.write_text(json.dumps(self.payload), encoding="utf-8")
        result = self.run_script("emit-report.py", "--kind", "test", "--version", self.version,
                                 "--build", self.build, "--data", str(draft), "--templates-root",
                                 str(SCRIPTS.parent / "templates/reports"), "--json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.emitted = json.loads(result.stdout)
        self.report_dir = self.root / "docs/reports" / self.version / "AI测试报告"
        baseline = json.loads(self.baseline.read_text())
        baseline["versions"][self.version]["builds"][0].update(
            ai_report_finalized=True, ai_report_finalized_at="2026-01-01T00:00:00Z", status="closed")
        self.baseline.write_text(json.dumps(baseline))
        self.frozen = copy.deepcopy(baseline["versions"])
        self.hashes = self.report_hashes()

    def run_script(self, name, *args):
        return subprocess.run([sys.executable, str(SCRIPTS / name), "--repo-root", str(self.root), *args],
                              capture_output=True, text=True, timeout=20)

    def repair(self, *args):
        return subprocess.run([sys.executable, str(SCRIPTS / "emit-report.py"), "delivery-repair",
                               "--repo-root", str(self.root), "--kind", "test", "--version", self.version,
                               "--build", self.build, "--json", *args], capture_output=True, text=True, timeout=20)

    def notice(self, *args):
        return self.run_script("notify.py", "--report-kind", "test", "--version", self.version,
                               "--build", self.build, "--project-name", "示例项目", "--title", "FAIL 报告",
                               "--section", "本次测试失败，详见现有报告。", *args)

    def report_hashes(self):
        return {p.relative_to(self.report_dir).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in self.report_dir.rglob("*") if p.is_file()}

    def ledger(self):
        return json.loads(self.baseline.read_text())["report_deliveries"][self.build]["test_report"]

    def assert_facts_unchanged(self):
        self.assertEqual(self.report_hashes(), self.hashes)
        self.assertEqual(json.loads(self.baseline.read_text())["versions"], self.frozen)
        self.assertFalse((self.root / "TESTS_WERE_RERUN").exists())
        self.assertEqual(list(self.root.rglob("*.zip")), [])

    def test_local_only_does_not_claim_upload_failed(self):
        self.assertEqual(self.emitted["local"]["status"], "ready")
        self.assertEqual(self.emitted["upload"]["status"], "not_requested")
        self.assertEqual(self.emitted["notification"]["status"], "not_attempted")
        result = self.notice("--print-only")
        self.assertEqual(result.returncode, 0, result.stderr)
        message = json.loads(result.stdout)["message"]
        self.assertIn("需要仓库访问权限", " ".join(message["sections"]))
        self.assertNotIn("上传失败", json.dumps(message, ensure_ascii=False))
        self.assertEqual(self.ledger()["notification"]["status"], "not_attempted")
        self.assert_facts_unchanged()

    def test_upload_failure_preserves_local_and_reason_and_fallback_wording(self):
        result = self.repair("--upload-status", "failed", "--reason", "离线上传桩返回拒绝")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        state = json.loads(result.stdout)
        self.assertEqual(state["upload"]["status"], "failed")
        self.assertEqual(state["local"]["status"], "ready")
        self.assertEqual(state["notification"]["status"], "not_attempted")
        self.assertEqual(state["access_url"], self.emitted["access_url"])
        message = json.loads(self.notice("--print-only").stdout)["message"]
        self.assertIn("在线上传失败，当前提供仓库路径，需要仓库访问权限。", message["sections"])
        self.assertIn("离线上传桩返回拒绝", " ".join(message["sections"]))
        self.assert_facts_unchanged()

    def test_repair_and_fail_notification_only_metadata_no_attachments(self):
        result = self.repair("--upload-status", "succeeded", "--url", "https://reports.example.invalid/result.html")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        state = json.loads(result.stdout)
        self.assertTrue(state["access_url"].endswith("#/build/" + self.build))
        self.assertEqual(self.ledger()["notification"]["status"], "not_attempted")
        # 仅离线接收桩，从 stdin 落本地 JSON；没有外部通知/附件/网络。
        sink = self.root / "sink.py"
        sink.write_text("import pathlib,sys\npathlib.Path('captured.json').write_text(sys.stdin.read())\n")
        sender = shlex.join([sys.executable, str(sink)])
        result = self.notice("--sender", sender, "--json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        message = json.loads((self.root / "captured.json").read_text())
        self.assertIn("FAIL", message["title"])
        self.assertEqual(message["link"]["url"], state["access_url"])
        self.assertEqual(set(message), {"schema", "title", "color", "sections", "link", "footer", "meta"})
        self.assertNotIn("上传失败", " ".join(message["sections"]))
        ledger = self.ledger()
        self.assertEqual(ledger["notification"]["status"], "sent")
        self.assertEqual(ledger["upload"]["status"], "succeeded")
        self.assertEqual(ledger["local"]["status"], "ready")
        self.assert_facts_unchanged()

    def test_unavailable_notification_does_not_change_upload(self):
        self.repair("--upload-status", "failed", "--reason", "offline")
        result = self.notice("--auto", "--json")
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        ledger = self.ledger()
        self.assertEqual(ledger["notification"]["status"], "unavailable")
        self.assertEqual(ledger["upload"]["status"], "failed")
        self.assert_facts_unchanged()

    def test_repair_cannot_amend_or_accept_bad_upload_and_normal_emit_stays_frozen(self):
        for args in (("--force-amend",), ("--data", "irrelevant.json"), ("--upload-status", "failed"),
                     ("--upload-status", "succeeded", "--url", "file:///tmp/report.html")):
            result = self.repair(*args)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        draft = self.root / "new-input.json"
        draft.write_text(json.dumps(self.payload))
        result = self.run_script("emit-report.py", "--kind", "test", "--version", self.version,
                                 "--build", self.build, "--data", str(draft), "--json")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assert_facts_unchanged()

    def test_tampered_payload_or_ledger_refuses_repair(self):
        baseline = json.loads(self.baseline.read_text())
        baseline["report_deliveries"][self.build]["test_report"]["integrity"] = "sha256:wrong"
        self.baseline.write_text(json.dumps(baseline))
        before = self.baseline.read_bytes()
        result = self.repair("--upload-status", "failed", "--reason", "offline")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.baseline.read_bytes(), before)
        self.assert_facts_unchanged()

    def test_documented_shell_delivery_flow_runs_offline(self):
        readme = (SCRIPTS.parent / "templates/reports/README.md").read_text(encoding="utf-8")
        marker = ': "${TARGET_VERSION:?须指定已有报告版本}"'
        shell = readme.split(marker, 1)[1].split("```", 1)[0]
        shell = (marker + shell).replace("{{AIDP_HOME}}", str(SCRIPTS.parent))
        sink = self.root / "local-sink.py"
        sink.write_text("import pathlib,sys\npathlib.Path('shell-message.json').write_text(sys.stdin.read())\n")
        command = shlex.join([sys.executable, str(sink)])
        (self.root / "memory/aidp-config.yaml").write_text(
            "notify:\n  enabled: true\n  channels:\n    - type: command\n      command: "
            + json.dumps(command) + "\n", encoding="utf-8")
        env = dict(os.environ, TARGET_VERSION=self.version, BUILD=self.build, REPORT_KIND="test",
                   REPORT_UPLOAD_STATUS="failed", REPORT_UPLOAD_REASON="offline mock rejected")
        result = subprocess.run(["bash", "-c", shell], cwd=self.root, env=env,
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        message = json.loads((self.root / "shell-message.json").read_text())
        self.assertIn("在线上传失败，当前提供仓库路径，需要仓库访问权限。", message["sections"])
        self.assertEqual(self.ledger()["delivery"], "local")
        self.assertEqual(self.ledger()["upload"]["status"], "failed")
        self.assertEqual(self.ledger()["notification"]["status"], "sent")
        self.assert_facts_unchanged()

    def test_metadata_api_refuses_integrity_replacement(self):
        emit = load_emit()
        old = self.ledger()
        before = self.baseline.read_bytes()
        with self.assertRaisesRegex(ValueError, "metadata"):
            emit.record_baseline(str(self.baseline), "test", self.build, self.version, "local", old["url"],
                                 integrity=old["integrity"], delivery_patch={"integrity": "replacement"},
                                 metadata_only=True)
        self.assertEqual(self.baseline.read_bytes(), before)
        self.assert_facts_unchanged()

    def test_migration_and_diagnostics_never_send_network(self):
        with patch.object(notify, "_post_json", side_effect=AssertionError("network forbidden")), \
                patch.object(notify.subprocess, "run", side_effect=AssertionError("probe forbidden")), \
                patch.dict(os.environ, {}, clear=True):
            _, report = notify.migrate_notify_config({"enabled": True, "channels": [
                {"type": "feishu", "webhook_env": "AIDP_TEST_MISSING_WEBHOOK"}]})
        self.assertFalse(report["ready"])
        self.assertFalse(report["delivery_verified"])


if __name__ == "__main__":
    unittest.main()
