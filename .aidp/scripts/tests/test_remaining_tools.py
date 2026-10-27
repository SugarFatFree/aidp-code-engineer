#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""上游剩余工具的真实调用边界：采集量、缓存、阶段状态和用例欠账。"""
import contextlib
import importlib.util
import io
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


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


probe = load("batch_probe")
cache = load("preflight_cache")
scale = load("check_scale_budget")
cases = load("check_case_ledger_pending")
stuck = load("check_stuck_phase")
phase = load("aiauto_phase_entry")


class TemporaryProject(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.baseline = self.root / "memory/.sprint-autopilot-baseline.json"
        self.baseline.parent.mkdir()
        self.save({"versions": {"V1": {}}, "aiauto": {"tick_started_at": "tick-1"}})

    def save(self, data):
        self.baseline.write_text(json.dumps(data), encoding="utf-8")

    def read(self):
        return json.loads(self.baseline.read_text(encoding="utf-8"))

    def cli(self, script, *args):
        return subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)],
                              cwd=self.root, capture_output=True, text=True, timeout=20)


class BatchProbeTests(TemporaryProject):
    def setUp(self):
        super().setUp()
        self.source = self.root / "sample.txt"
        self.source.write_bytes(b"BASE\r\n")
        self.probes = [{"id": "P1", "file": "sample.txt", "inject": "BAD", "expect": "EXPECTED"}]

    def test_positive_exit_zero_is_not_proof(self):
        with patch.object(probe, "_run", side_effect=[(0, "clean"), (0, "EXPECTED"), (0, "clean")]):
            result = probe.run(str(self.root), self.probes, "unused", 1)
        self.assertFalse(result["ok"], "命中文字但检查器退出0，不能证明它发现了错误")

    def test_multiple_probes_cannot_share_only_a_global_exit_or_diagnostic(self):
        (self.root / "second.txt").write_text("BASE\n", encoding="utf-8")
        for expect in ("", "EXPECTED"):
            probes = [{**self.probes[0], "expect": expect},
                      {**self.probes[0], "id": "P2", "file": "second.txt", "expect": expect}]
            with patch.object(probe, "_run", side_effect=[(0, ""), (1, "EXPECTED"), (0, "")]):
                self.assertFalse(probe.run(str(self.root), probes, "unused", 1)["ok"],
                                 "一个失败码或一条共享诊断不能证明每个探针都命中")

    def test_timeout_is_not_probe_hit(self):
        with patch.object(probe, "_run", side_effect=[(0, ""), (124, "timeout"), (0, "")]):
            result = probe.run(str(self.root), [{**self.probes[0], "expect": ""}], "unused", 1)
        self.assertFalse(result["ok"], "检查器超时不是检测到探针")

    def test_restores_exact_bytes(self):
        original = self.source.read_bytes()
        with patch.object(probe, "_run", side_effect=[(0, ""), (1, "EXPECTED"), (0, "")]):
            result = probe.run(str(self.root), self.probes, "unused", 1)
        self.assertEqual(self.source.read_bytes(), original, "还原不得改变 CRLF 或末尾换行")
        self.assertTrue(result["ok"])

    def test_restored_side_must_be_rechecked(self):
        with patch.object(probe, "_run", side_effect=[(0, ""), (1, "EXPECTED"), (1, "changed environment")]):
            result = probe.run(str(self.root), self.probes, "unused", 1)
        self.assertFalse(result["ok"], "还原后的检查必须重新变绿")

    def test_empty_probe_list_is_not_success(self):
        with patch.object(probe, "_run", return_value=(0, "")):
            self.assertFalse(probe.run(str(self.root), [], "unused", 1)["ok"])


class CacheTests(TemporaryProject):
    def test_cached_command_replays_json(self):
        code = 'print(\'{"passed": true, "items": 3}\')'
        command = shlex.join([sys.executable, "-c", code])
        args = ["--run-id", "t1", "--check", "scan", "--cmd", command]
        first = self.cli("preflight_cache.py", *args)
        second = self.cli("preflight_cache.py", *args)
        self.assertEqual(first.returncode, 0)
        self.assertEqual(second.returncode, 0)
        self.assertEqual(second.stdout, first.stdout, "调用方在缓存命中时仍需消费原始 JSON")
        self.assertIn("复用", second.stderr)

    def test_different_command_cannot_replay_old_output(self):
        one = shlex.join([sys.executable, "-c", "print('ONE')"])
        two = shlex.join([sys.executable, "-c", "print('TWO')"])
        args = ["--run-id", "t1", "--check", "same-name"]
        self.assertEqual(self.cli("preflight_cache.py", *args, "--cmd", one).stdout, "ONE\n")
        self.assertEqual(self.cli("preflight_cache.py", *args, "--cmd", two).stdout, "TWO\n")

    def test_failed_semantic_verdict_not_cached(self):
        code = 'print(\'{"passed": false, "items": 3}\')'
        command = shlex.join([sys.executable, "-c", code])
        result = self.cli("preflight_cache.py", "--run-id", "t1", "--check", "scan", "--cmd", command)
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("scan", cache._load(str(self.root)).get("checks", {}),
                         "exit0 的 passed:false 不能作为成功结论复用")

    def test_empty_run_id_cannot_create_reusable_cache(self):
        self.assertFalse(cache.put(str(self.root), "", "scan", "fp", "ok"))
        self.assertIsNone(cache.get(str(self.root), "", "scan", "fp"))


class ScaleBudgetTests(TemporaryProject):
    def test_missing_structural_facts_do_not_lower_tier(self):
        self.assertEqual(scale.effective_tier("M", None, None, None)[0], "M")

    def test_task_heading_is_collected(self):
        directory = self.root / "docs/plans/V1"
        directory.mkdir(parents=True)
        (directory / "01_研发执行计划.md").write_text("# 计划\n### Task 1.1 登录\n", encoding="utf-8")
        self.assertEqual(scale.measure(str(self.root), "V1")["tasks"], 1)

    def test_zero_recognized_cases_is_not_reported_within_budget(self):
        directory = self.root / "docs/testing/V1/研发自测"
        directory.mkdir(parents=True)
        (directory / "02_用例.md").write_text("# 用例\n只有文字，未生成用例段。\n", encoding="utf-8")
        result = scale.run(str(self.root), "V1", "S", None, None, None)
        self.assertTrue(result["findings"], "用例采集量0只能报未核验，不能报预算内")

    def test_private_ledger_is_not_a_case_source(self):
        directory = self.root / "docs/testing/V1/研发自测"
        directory.mkdir(parents=True)
        (directory / "_开发期用例增量.md").write_text("#### 用例 TC-EXAMPLE-1\n", encoding="utf-8")
        self.assertEqual(scale.measure(str(self.root), "V1")["cases"], 0)


class DeferredCaseTests(TemporaryProject):
    def test_malformed_case_ledger_blocks_testing(self):
        directory = self.root / "docs/testing/V1/研发自测"
        directory.mkdir(parents=True)
        (directory / "_开发期用例增量.md").write_text("# 台账\n\n## 待级联\n\n* 需要补登录用例\n* 需要补导出用例\n", encoding="utf-8")
        result = cases.run(str(self.root), "V1")
        self.assertFalse(result["passed"], "存在实质待办却解析为0时不能放行")

    def test_deferred_record_survives_ledger_loss(self):
        cases.record_generation(str(self.root), "V1", "001", "本轮不启动实测")
        ledger = self.root / "docs/testing/V1/研发自测/_开发期用例增量.md"
        ledger.unlink()
        self.assertFalse(cases.run(str(self.root), "V1")["passed"])

    def test_complete_rejects_placeholder_case_id(self):
        cases.record_generation(str(self.root), "V1", "001", "延后")
        directory = self.root / "docs/testing/V1/研发自测"
        (directory / "_开发期用例增量.md").unlink()
        (directory / "README.md").write_text("以后请填写 TC- 编号", encoding="utf-8")
        with self.assertRaises(ValueError):
            cases.record_generation(str(self.root), "V1", "001", "生成完成", complete=True)


class StuckBoundaryTests(TemporaryProject):
    def test_missing_state_cannot_report_healthy(self):
        result = self.cli("check_stuck_phase.py", "--command", "aiauto-test", "--version", "V1", "--json")
        self.assertEqual(result.returncode, 2, "缺阶段状态时应报不可判定，不能报未卡住")

    def test_previous_phase_must_be_checked_before_entry_overwrites_it(self):
        data = self.read()
        data["versions"]["V1"]["aiauto_run_state"] = {
            "current_phase": "2-exec", "phase_status": "running", "phase_token": "B1",
            "phase_enter_count": 8, "phase_first_entered_at": "2000-01-01T00:00:00Z"}
        self.save(data)
        calls = []
        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 3 if "check_stuck_phase.py" in str(cmd) else 0)
        with patch.object(phase.subprocess, "run", side_effect=fake_run):
            result = phase.main(["--baseline", str(self.baseline), "--version", "V1",
                                 "--phase", "1-probe", "--next-phase", "2-exec", "--build", "B1"])
        self.assertEqual(result, 3)
        self.assertIn("check_stuck_phase.py", str(calls[0]), "旧阶段未完成时应先检查，不能先写1-probe清零")


class GenerationPolicyTests(TemporaryProject):
    def test_generation_tracks_actual_outer_test_intent(self):
        self.assertFalse(cases.generation_required("direct"))
        self.assertTrue(cases.generation_required("autopilot"))
        self.assertTrue(cases.generation_required("batch"))
        self.assertFalse(cases.generation_required("batch", skip=True))
        self.assertTrue(cases.generation_required("batch", skip=True, explicit=True))
        self.assertTrue(cases.generation_required("testing", skip=True))

    def test_preparation_records_both_ledger_and_state(self):
        result = cases.prepare_generation(str(self.root), "V1", "001", "本轮只开发")
        self.assertFalse(result["required"])
        self.assertFalse(cases.run(str(self.root), "V1")["passed"])
        self.assertEqual(self.read()["versions"]["V1"]["sprints"]["001"]["case_generation"]["status"], "deferred")
        retry = cases.prepare_generation(str(self.root), "V1", "001", "现在请求实测", context="testing")
        self.assertTrue(retry["required"])
        self.assertFalse(cases.run(str(self.root), "V1")["passed"], "意图变化不能自动清掉用例欠账")

    def test_real_case_generation_clears_only_requested_sprint(self):
        for n in ("001", "002"):
            cases.prepare_generation(str(self.root), "V1", n, "延后")
        directory = self.root / "docs/testing/V1/研发自测"
        (directory / "_开发期用例增量.md").unlink()
        (directory / "02_登录.md").write_text("### 套件 SUITE-LOGIN\n#### 用例 TC-LOGIN-1 登录\n", encoding="utf-8")
        cases.record_generation(str(self.root), "V1", "001", "已生成并通过 QR", complete=True)
        self.assertEqual(cases.run(str(self.root), "V1")["deferred_sprints"], ["002"])
        cases.record_generation(str(self.root), "V1", "002", "已生成并通过 QR", complete=True)
        self.assertTrue(cases.run(str(self.root), "V1")["passed"])


class PhaseLifecycleTests(TemporaryProject):
    def enter(self, phase_name, next_phase, tick="tick-1", *extra):
        return self.cli("aiauto_phase_entry.py", "--version", "V1", "--phase", phase_name,
                        "--next-phase", next_phase, "--build", "B1", "--tick-id", tick, *extra)

    def test_same_tick_is_counted_once_then_next_tick_accumulates(self):
        self.assertEqual(self.enter("1-probe", "2-exec").returncode, 0)
        self.assertEqual(self.enter("1-probe", "2-exec").returncode, 0)
        self.assertEqual(self.read()["versions"]["V1"]["aiauto_run_state"]["phase_enter_count"], 1)
        self.assertEqual(self.enter("1-probe", "2-exec", "tick-2").returncode, 0)
        self.assertEqual(self.read()["versions"]["V1"]["aiauto_run_state"]["phase_enter_count"], 2)

    def test_enter_does_not_claim_completed(self):
        self.assertEqual(self.enter("1-probe", "2-exec").returncode, 0)
        state = self.read()["versions"]["V1"]["aiauto_run_state"]
        self.assertEqual(state["phase_status"], "running")
        self.assertNotIn("phase_completed_at", state)
        self.assertEqual(self.enter("1-probe", "2-exec", "tick-1", "--complete").returncode, 0)
        state = self.read()["versions"]["V1"]["aiauto_run_state"]
        self.assertEqual(state["phase_status"], "complete")
        self.assertEqual(state["next_phase"], "2-exec")

    def test_phase_advance_requires_completion_and_earlier_entry_resumes(self):
        self.assertEqual(self.enter("1-probe", "2-exec").returncode, 0)
        self.assertNotEqual(self.enter("2-exec", "3-audit").returncode, 0)
        self.assertEqual(self.enter("1-probe", "2-exec", "tick-1", "--complete").returncode, 0)
        self.assertEqual(self.enter("2-exec", "3-audit").returncode, 0)
        result = self.enter("1-probe", "2-exec", "tick-2")
        self.assertEqual(result.returncode, 0)
        self.assertTrue(json.loads(result.stdout)["skip_phase"])
        self.assertEqual(self.read()["versions"]["V1"]["aiauto_run_state"]["current_phase"], "2-exec")

    def test_completed_phase_is_skipped_on_next_entry(self):
        self.assertEqual(self.enter("1-probe", "2-exec").returncode, 0)
        self.assertEqual(self.enter("1-probe", "2-exec", "tick-1", "--complete").returncode, 0)
        result = self.enter("1-probe", "2-exec", "tick-2")
        self.assertEqual(result.returncode, 0)
        self.assertTrue(json.loads(result.stdout)["skip_phase"])

    def test_freeze_write_failure_is_not_reported_as_frozen(self):
        data = self.read()
        data["versions"]["V1"]["aiauto_run_state"] = {"current_phase": "2-exec", "phase_enter_count": 8,
                                                           "phase_first_entered_at": "2000-01-01T00:00:00Z"}
        self.save(data)
        result = subprocess.CompletedProcess([], 2, stdout='{"frozen": false}', stderr="disk unavailable")
        with patch.object(stuck.subprocess, "run", return_value=result), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            rc = stuck.main(["--command", "aiauto-test", "--version", "V1", "--baseline", str(self.baseline), "--freeze", "--json"])
        self.assertEqual(rc, 2)


class StageCascadeTests(TemporaryProject):
    def test_recorded_build_groups_produce_no_dispatch_families(self):
        runtime = self.root / "runtime/scripts"
        runtime.mkdir(parents=True)
        (runtime / "autopilot_tick_flags.py").write_text(
            "print('ENTRY_MODE=full;SKIP_AIAUTO_TEST=0;TARGET_VERSION=V1;BUILD=B1')\n", encoding="utf-8")
        (runtime / "baseline_edit.py").write_text("import sys\nif 'get' in sys.argv: print('2026-10-20T00:00:00Z')\n", encoding="utf-8")
        flow = (SCRIPTS.parent / "flows/sprint-autopilot/phase-3-4b.md").read_text(encoding="utf-8")
        script = flow.split("```bash\n", 1)[1].split("\n```", 1)[0]
        script = script.replace("{{AIDP_HOME}}", str(runtime.parent))
        result = subprocess.run(["bash", "-c", script + '\nprintf "%s" "$FAMS"'],
                                cwd=self.root, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "", "build 已处理的族必须在真实 FAMS 中剔除，而非只靠散文提醒")

    def test_test_only_gate_does_not_touch_unselected_families(self):
        directory = self.root / "docs/design/detail/V1"
        directory.mkdir(parents=True)
        (directory / "_开发期设计增量.md").write_text("# 设计台账\n## 待级联\n* 设计待办一\n* 设计待办二\n", encoding="utf-8")
        directory = self.root / "docs/testing/V1/研发自测"
        directory.mkdir(parents=True)
        (directory / "_开发期用例增量.md").write_text("# 用例台账\n## 待级联\n- C-001 · 10-20 12:00 · 用例待办 · sprint-001\n", encoding="utf-8")
        result = self.cli("check_cascade_landing.py", "--ledger-closed", "--version", "V1", "--family", "用例", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual({c["family"] for c in json.loads(result.stdout)["checked"]}, {"case"})

    def test_manual_unfreeze_resets_test_stuck_window(self):
        import autopilot_unfreeze as unfreeze
        data = self.read()
        data["versions"]["V1"] = {"needs_human": True, "freeze_reason": "stuck-phase",
            "aiauto_frozen_at": "2000-01-01T00:00:00Z",
            "aiauto_run_state": {"phase_enter_count": 8, "phase_first_entered_at": "2000-01-01T00:00:00Z",
                                 "current_phase": "2-exec", "phase_status": "running"}}
        self.save(data)
        result = unfreeze.manual_unfreeze(str(self.root), "V1")
        self.assertTrue(result["cleared"])
        self.assertLessEqual(self.read()["versions"]["V1"]["aiauto_run_state"]["phase_enter_count"], 1,
                             "人工解冻后不能在同一旧计数上立刻重冻")


class DigestAndTickTests(TemporaryProject):
    def test_digest_understands_runtime_tokens_and_only_lists_fenced_commands(self):
        digest = load("shard_gate_digest")
        path = self.root / "phase.md"
        path.write_text("## 硬门\npython3 {{AIDP_HOME}}/scripts/prose.py\n\n```bash\npython3 {{AIDP_HOME}}/scripts/check_case_ledger_pending.py --json\n```\n", encoding="utf-8")
        result, error = digest.digest(str(path))
        self.assertIsNone(error)
        self.assertEqual(result["commands"], ["python3 {{AIDP_HOME}}/scripts/check_case_ledger_pending.py"])

    def test_tick_identity_is_fresh_and_can_be_forwarded(self):
        first = self.cli("autopilot_tick_flags.py", "parse", "--command", "autopilot", "--arguments=--once")
        self.assertEqual(first.returncode, 0, first.stderr)
        one = self.read()["autopilot"]["tick_id"]
        token = next(line.split("=", 1)[1] for line in first.stdout.splitlines() if line.startswith("tick-lock-token="))
        finished = self.cli("autopilot_tick_flags.py", "finish", "--command", "autopilot", "--lock-token", token)
        self.assertEqual(finished.returncode, 0, finished.stderr)
        second = self.cli("autopilot_tick_flags.py", "parse", "--command", "autopilot", "--arguments=--once")
        self.assertEqual(second.returncode, 0, second.stderr)
        two = self.read()["autopilot"]["tick_id"]
        self.assertNotEqual(one, two, "同一秒开始的新 tick 也不能命中上次缓存")
        child = self.cli("autopilot_tick_flags.py", "parse", "--command", "aiauto-test",
                         "--arguments=--once --preflight-run-id " + two)
        self.assertEqual(child.returncode, 0, child.stderr)
        self.assertEqual(self.read()["aiauto"]["tick_id"], two)

    def test_scale_cli_reads_full_version_facts(self):
        data = self.read()
        data["versions"]["V1"]["req_scale"] = {"tier": "M", "has_api": True, "has_ddl": False, "page_count": 2}
        self.save(data)
        directory = self.root / "docs/plans/V1"
        directory.mkdir(parents=True)
        (directory / "01_计划.md").write_text("### Task 1.1 实现\n", encoding="utf-8")
        result = self.cli("check_scale_budget.py", "--version", "V1", "--from-baseline", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["effective_tier"], "M")


if __name__ == "__main__":
    unittest.main(verbosity=2)
