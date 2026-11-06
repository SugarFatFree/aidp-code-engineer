#!/usr/bin/env python3
"""派发退避必须有界，成功必须清闸门，单次调用不能静默 yield。"""
import importlib.util
import json
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

SCRIPTS = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("dispatch_retry", SCRIPTS / "dispatch_retry.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class DispatchRetryTest(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 6, tzinfo=timezone.utc)
        self.node = {"dev_fail_streak": 2, "unrelated": {"keep": True}}

    def apply(self, op, kind="transient", wake=True):
        return m.transition(self.node, op, phase="3.1-plan", kind=kind,
                            has_wake_source=wake, now=self.now)

    def test_full_retry_is_bounded_and_fourth_failure_splits(self):
        for delay in (30, 60, 120):
            rc, out = self.apply("failure")
            self.assertEqual((rc, out["action"], out["retry_after_seconds"]),
                             (10, "yield", delay))
            self.now += timedelta(seconds=delay)
            self.assertEqual(self.apply("gate")[0], 0)
        rc, out = self.apply("failure")
        self.assertEqual((rc, out["action"], self.node["subagent_retry_stage"]),
                         (11, "split", "split"))
        self.assertNotIn("subagent_retry_at", self.node)
        self.assertEqual(self.node["subagent_retry_round"], 0)
        self.assertEqual(self.node["dev_fail_streak"], 2)
        self.assertEqual(self.apply("gate")[1]["action"], "split")

    def test_split_retry_exhaustion_stays_terminal_until_handled(self):
        self.node.update(subagent_retry_stage="split", subagent_retry_round=3,
                         subagent_retry_phase="3.1-plan")
        rc, out = self.apply("failure")
        self.assertEqual((rc, out["action"], out["reason"]),
                         (20, "fail", "plan-transient"))
        self.assertEqual(self.apply("gate")[0], 20)
        self.assertEqual(self.node["subagent_retry_round"], 4)

    def test_success_clears_all_dispatch_fields_and_preserves_other_state(self):
        self.apply("failure")
        self.assertEqual(self.apply("success")[0], 0)
        self.assertFalse(any(k.startswith("subagent_retry_") for k in self.node))
        self.assertEqual(self.node["unrelated"], {"keep": True})
        self.assertEqual(self.apply("gate")[0], 0)

    def test_gate_does_not_increment_retry_and_has_no_silent_yield_without_wake(self):
        self.apply("failure")
        rc, out = self.apply("gate", wake=False)
        self.assertEqual((rc, out["action"]), (13, "wait-inline"))
        self.assertEqual(self.node["subagent_retry_round"], 1)
        rc, out = self.apply("failure", wake=False)
        self.assertEqual((rc, out["action"]), (13, "wait-inline"))
        self.assertEqual(self.node["subagent_retry_round"], 2)

    def test_deterministic_failure_is_never_retried_as_transient(self):
        rc, out = self.apply("failure", kind="deterministic")
        self.assertEqual((rc, out["action"]), (20, "fail"))
        self.assertNotIn("subagent_retry_at", self.node)

    def test_unavailable_tool_selects_budget_checked_inline(self):
        rc, out = self.apply("failure", kind="unavailable")
        self.assertEqual((rc, out["action"]), (12, "inline-budget"))
        self.assertEqual(self.apply("gate")[1]["action"], "inline-budget")

    def test_legacy_round_above_cap_cannot_loop_forever(self):
        self.node.update(subagent_retry_round=99, subagent_retry_at="2099-01-01T00:00:00Z")
        self.assertEqual(self.apply("gate")[1]["action"], "split")
        self.assertNotIn("subagent_retry_at", self.node)

    def test_other_phase_does_not_inherit_retry_gate(self):
        self.apply("failure")
        rc, _ = m.transition(self.node, "gate", phase="3.2-dev", kind="transient",
                             has_wake_source=True, now=self.now)
        self.assertEqual(rc, 0)
        self.assertNotIn("subagent_retry_at", self.node)

    def test_cli_persists_and_success_clears_gate(self):
        with tempfile.TemporaryDirectory() as td:
            baseline = Path(td) / "baseline.json"
            baseline.write_text(json.dumps({"versions": {"V1.0.0": self.node}}))
            args = [sys.executable, str(SCRIPTS / "dispatch_retry.py"),
                    "--baseline", str(baseline), "--version", "V1.0.0",
                    "--phase", "3.1-plan", "--has-wake-source", "0"]
            failed = subprocess.run(args + ["failure", "--kind", "transient"],
                                    capture_output=True, text=True)
            self.assertEqual(failed.returncode, 13, failed.stderr)
            self.assertEqual(json.loads(failed.stdout)["action"], "wait-inline")
            good = subprocess.run(args + ["success"], capture_output=True, text=True)
            self.assertEqual(good.returncode, 0, good.stderr)
            node = json.loads(baseline.read_text())["versions"]["V1.0.0"]
            self.assertNotIn("subagent_retry_at", node)
            self.assertEqual(node["unrelated"], {"keep": True})

    def run_planning_block(self, node, wake, success=False):
        flow = (SCRIPTS.parent / "flows/sprint-autopilot/phase-3-3.md").read_text()
        blocks = re.findall(r"```bash\n(.*?)```", flow, flags=re.S)
        marker = '--phase 3.1-plan success' if success else 'run-state "3.1-plan" "3.1-plan" "" --enter'
        block = next(b for b in blocks if marker in b)
        if success:
            block = block[block.index("# 仅完成校验通过后"):]
            block = 'BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py"; V="$TARGET_VERSION"\n' + block
        else:
            block = re.sub(r'^\s*eval .*autopilot_tick_flags[^\n]*\n', '', block, flags=re.M)
        block = block.replace("{{AIDP_HOME}}", str(SCRIPTS.parent))
        with tempfile.TemporaryDirectory() as td:
            baseline = Path(td) / "memory/.sprint-autopilot-baseline.json"
            baseline.parent.mkdir()
            baseline.write_text(json.dumps({"autopilot": {"wake_source_this_tick": str(wake)},
                                            "versions": {"V1.0.0": node}}))
            # 使用真实统一失败 API，但关闭通知；测试只写临时项目。
            block = block.replace(str(SCRIPTS / "autopilot_fail_handle.py"),
                                  str(SCRIPTS / "autopilot_fail_handle.py") +
                                  f' --no-card --baseline "{baseline}"')
            result = subprocess.run(["bash", "-c", f'TARGET_VERSION=V1.0.0; HAS_WAKE_SOURCE={wake}\n' + block],
                                    cwd=td, capture_output=True, text=True)
            return result, json.loads(baseline.read_text())["versions"]["V1.0.0"]

    def test_real_entry_without_wake_freezes_and_keeps_resume_cursor(self):
        node = {"subagent_retry_round": 1, "subagent_retry_stage": "full",
                "subagent_retry_phase": "3.1-plan", "subagent_retry_at": "2099-01-01T00:00:00Z",
                "run_state": {"current_phase": "3.0", "next_phase": "3.1-plan",
                              "phase_completed_at": "old"}}
        result, node = self.run_planning_block(node, wake=0)
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertTrue(node["needs_human"])
        self.assertEqual(node["freeze_reason"], "plan-transient")
        self.assertEqual(node["run_state"]["next_phase"], "3.1-plan")
        self.assertEqual(node["run_state"]["phase_status"], "running")
        self.assertEqual(node["run_state"]["pending_actions"], ["planning"])
        self.assertNotIn("phase_completed_at", node["run_state"])

    def test_real_exhausted_gate_calls_failure_api(self):
        node = {"subagent_retry_round": 4, "subagent_retry_stage": "exhausted",
                "subagent_retry_phase": "3.1-plan"}
        result, node = self.run_planning_block(node, wake=1)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(node["dev_fail_streak"], 1)
        self.assertEqual(node["dev_fail_phase"], "3.1-plan")
        self.assertEqual(node["run_state"]["next_phase"], "3.1-plan")
        self.assertNotIn("phase_completed_at", node["run_state"])

    def test_real_success_clears_dispatch_and_failure_state_before_advancing(self):
        self.apply("failure")
        self.node.update(dev_fail_phase="3.1-plan", dev_fail_reason="plan-transient",
                         run_state={"current_phase": "3.1-plan", "next_phase": "3.1-plan",
                                    "phase_status": "running", "pending_actions": ["planning"]})
        result, node = self.run_planning_block(self.node, wake=1, success=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(any(k.startswith("subagent_retry_") for k in node))
        self.assertEqual(node.get("dev_fail_streak", 0), 0)
        self.assertEqual(node["run_state"]["next_phase"], "3.1.5-build")
        self.assertEqual(node["run_state"]["phase_status"], "complete")
        self.assertEqual(node["run_state"]["pending_actions"], [])
        self.assertTrue(node["run_state"]["phase_completed_at"])

    def test_planning_flow_enters_before_dispatch_and_success_is_executable(self):
        flow = (SCRIPTS.parent / "flows/sprint-autopilot/phase-3-3.md").read_text()
        entry = flow.index('run-state "3.1-plan" "3.1-plan" "" --enter')
        gate = flow.index("/scripts/dispatch_retry.py")
        self.assertLess(entry, gate)
        self.assertIn('--phase 3.1-plan success', flow)
        self.assertIn('--reason plan-transient', flow)
        self.assertIn('run_state.phase_status complete', flow)


if __name__ == "__main__":
    unittest.main(verbosity=2)
