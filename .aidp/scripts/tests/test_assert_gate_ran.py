#!/usr/bin/env python3
"""外部机器门部分读取失败不能被包装成通过。"""
import json
from pathlib import Path
import subprocess
import sys
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "assert_gate_ran.py"


class ExternalGateTests(unittest.TestCase):
    def run_gate(self, payload, *, exit_code=0, allow_empty=False, json_output=True):
        child = ("import sys; print(sys.argv[1]); "
                 "sys.stderr.write(sys.argv[2]); sys.exit(int(sys.argv[3]))")
        command = [sys.executable, "-B", str(SCRIPT), "--label", "fixture"]
        if json_output:
            command += ["--json"]
        if allow_empty:
            command += ["--allow-empty", "本次没有适用需求"]
        command += ["--", sys.executable, "-B", "-c", child,
                    json.dumps(payload), "unreadable input\n" if payload.get("read_errors") else "",
                    str(exit_code)]
        return subprocess.run(command, capture_output=True, text=True)

    def test_partial_read_error_rejects_success_and_preserves_details(self):
        errors = [{"file": "02_requirement.md", "error": "FileNotFoundError"}]
        result = self.run_gate({"passed": True, "total_sections": 1, "read_errors": errors})
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["verdict"], "read-error")
        self.assertFalse(data["gate_passed"])
        self.assertTrue(data["ran"])
        self.assertTrue(data["incomplete"])
        self.assertEqual(data["read_errors"], errors)
        self.assertIn("unreadable input", data["gate_stderr"])

    def test_allow_empty_cannot_hide_read_errors(self):
        result = self.run_gate({"passed": True, "skipped": True, "total_sections": 0,
                                "read_errors": [{"file": "broken.md", "error": "unreadable"}]},
                               allow_empty=True)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["verdict"], "read-error")

    def test_text_output_exposes_partial_read_error(self):
        result = self.run_gate({"passed": True, "total_sections": 1,
                                "read_errors": [{"file": "broken.md", "error": "unreadable"}]},
                               json_output=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("broken.md", result.stdout + result.stderr)
        self.assertIn("unreadable input", result.stderr)

    def test_mixed_quality_and_read_errors_preserve_diagnostics(self):
        payload = {"passed": False, "total_sections": 1,
                   "issues": [{"level": "Important", "message": "REQ-001-source-incomplete"}],
                   "read_errors": [{"file": "broken.md", "error": "FileNotFoundError"}]}
        for json_output in (True, False):
            with self.subTest(json_output=json_output):
                result = self.run_gate(payload, exit_code=1, json_output=json_output)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                if json_output:
                    data = json.loads(result.stdout)
                    self.assertEqual(data["gate_exit_code"], 1)
                    self.assertFalse(data["gate_passed"])
                    self.assertEqual(json.loads(data["gate_stdout"]), payload)
                    self.assertIn("unreadable input", data["gate_stderr"])
                else:
                    self.assertIn("REQ-001-source-incomplete", result.stdout)
                    self.assertIn("broken.md", result.stdout)
                    self.assertIn("unreadable input", result.stderr)

    def test_success_and_quality_failure_keep_original_meaning(self):
        for passed, exit_code in ((True, 0), (False, 1)):
            with self.subTest(passed=passed):
                result = self.run_gate({"passed": passed, "total_sections": 1, "read_errors": []},
                                       exit_code=exit_code)
                self.assertEqual(result.returncode, exit_code, result.stdout + result.stderr)
                self.assertEqual(json.loads(result.stdout)["gate_passed"], passed)

    def test_zero_collection_still_requires_explicit_reason(self):
        payload = {"passed": True, "skipped": True, "total_sections": 0}
        self.assertEqual(self.run_gate(payload).returncode, 3)
        result = self.run_gate(payload, allow_empty=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["verdict"], "allow-empty")


if __name__ == "__main__":
    unittest.main()
