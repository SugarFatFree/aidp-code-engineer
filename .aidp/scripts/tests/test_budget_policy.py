#!/usr/bin/env python3
"""预算策略：并发硬限 + 总量软限；显式相关测试入口；选测增量缓存；超时不被内部低值覆盖。"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import time
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
import entry_context as entry
import execution_policy as policy
import test_command_guard as guard
import test_scope as scope

SELECT = SCRIPTS / "select_related_tests.py"


class RepoCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aidp-budget-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for args in (("init", "-q"), ("config", "user.name", "B"), ("config", "user.email", "b@example.test")):
            self.git(*args)
        self.write(".gitignore", "memory/.aidp/\n__pycache__/\n")
        self.write("src/app.py", "value = 1\n")
        self.write("tests/test_app.py", "from src.app import value\n")
        self.commit()

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True, text=True).stdout

    def write(self, name, text="x = 1\n"):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def commit(self):
        self.git("add", "-A")
        self.git("commit", "-qm", "c")

    def context(self, *, budget=None, write_set=("src/app.py",), request="r1", text="只做相关测试", grants=("related-test",)):
        return entry.resolve_context(self.root, "sprint-dev", version="V1", write_set=list(write_set),
            additional_grants=list(grants), execution_budget=budget,
            authorization_source={"kind": "user-text", "request_id": request, "text": text})


class SoftLimitTests(RepoCase):
    def test_scan_over_soft_threshold_continues_with_degrade_advice(self):
        """场景1/12：累计扫描量超过软阈值但持续有进展，不停止；降级顺序固定且有进展时不升级。"""
        ctx = self.context()["context"]
        limit = ctx["execution_budget"]["scanned_files"]
        self.assertNotIn("scanned_files", policy.hard_resources(ctx))
        first = policy.reserve_budget(self.root, ctx, "scanned_files", limit + 500, "a" * 64)
        self.assertEqual(first["status"], "RESERVED")
        advice = first["soft_exceeded"]["advice"]
        self.assertEqual(advice["order"], ["narrow-scope", "use-cache", "reduce-repeated-evidence", "ask-user"])
        self.assertEqual(advice["step"], "narrow-scope")
        self.assertFalse(advice["stops_task"])
        # 每次都有真实结果产出 → 停在第一级继续工作，不升级、不停止
        for index in range(4):
            policy.record_outcome(self.root, ctx, "static", "PASS", f"{index:064x}")
            again = policy.reserve_budget(self.root, ctx, "scanned_files", 100)
            self.assertEqual(again["soft_exceeded"]["advice"]["step"], "narrow-scope")

    def test_degrade_order_escalates_only_without_progress(self):
        ctx = self.context()["context"]
        limit = ctx["execution_budget"]["scanned_files"]
        steps = [policy.reserve_budget(self.root, ctx, "scanned_files", limit + 1)["soft_exceeded"]["advice"]["step"]
                 for _ in range(6)]
        self.assertEqual(steps[0], "narrow-scope")
        self.assertIn("use-cache", steps)
        self.assertIn("reduce-repeated-evidence", steps)
        self.assertEqual(steps[-1], "ask-user")
        order = list(policy.DEGRADE_STEPS)
        self.assertEqual(steps, sorted(steps, key=order.index), "只升不降且顺序固定")

    def test_user_explicit_hard_limit_still_blocks_with_recovery_path(self):
        """场景4/12：用户显式写入的上限仍是硬上限；BUDGET_EXCEEDED 给出可测试的恢复路径。"""
        ctx = self.context(budget={"scanned_files": 5})["context"]
        self.assertIn("scanned_files", policy.hard_resources(ctx))
        with self.assertRaises(policy.PolicyError) as denied:
            policy.reserve_budget(self.root, ctx, "scanned_files", 6, "a" * 64)
        self.assertEqual(denied.exception.status, "BUDGET_EXCEEDED")
        recovery = denied.exception.details["recovery"]
        self.assertTrue(recovery["only_affected_stage_stops"])
        text = "\n".join(recovery["steps"])
        for needle in ("缩小范围", "缓存", "revise --execution-budget", "不扩大业务授权"):
            self.assertIn(needle, text)

    def test_renewal_unblocks_without_granting_actions(self):
        """场景12/9：续额后可继续，但不新增任何动作授权。"""
        result = self.context(budget={"scanned_files": 5})
        with self.assertRaises(policy.PolicyError):
            policy.reserve_budget(self.root, result["context"], "scanned_files", 6)
        before_actions = set(result["context"]["allowed_actions"])
        revised = entry.revise_context(self.root, result["execution_context"], execution_budget={"scanned_files": 100},
            authorization_source={"kind": "user-text", "request_id": "renew", "text": "继续，扫描额度放宽到 100"})
        ctx = revised["context"]
        self.assertEqual(set(ctx["allowed_actions"]), before_actions)
        policy.reserve_budget(self.root, ctx, "scanned_files", 6)
        for action in ("full-regression", "deploy", "push"):
            with self.assertRaises(policy.PolicyError):
                policy.require_action(ctx, action)

    def test_autopilot_source_blocks_every_total_resource(self):
        ctx = entry.resolve_context(self.root, "sprint-autopilot", version="V1", write_set=["src/app.py"],
            authorization_source={"kind": "explicit-command", "request_id": "ap", "command": "/sprint-autopilot"})["context"]
        self.assertTrue({"scanned_files", "elapsed_seconds", "retries", "selected_tests"} <= policy.hard_resources(ctx))

    def test_high_risk_action_blocks_even_when_resource_is_soft(self):
        ctx = self.context(grants=("related-test", "deploy"))["context"]
        self.assertNotIn("elapsed_seconds", policy.hard_resources(ctx))
        limit = ctx["execution_budget"]["elapsed_seconds"]
        with self.assertRaises(policy.PolicyError) as denied:
            policy.reserve_budget(self.root, ctx, "elapsed_seconds", limit + 1, action="deploy")
        self.assertEqual(denied.exception.status, "BUDGET_EXCEEDED")
        ok = policy.reserve_budget(self.root, ctx, "elapsed_seconds", limit + 1, action="related-test")
        self.assertIn("soft_exceeded", ok)

    def test_soft_validation_overrun_is_recorded_not_unverified(self):
        ctx = self.context()["context"]
        stages = {name: {} for name in policy.VALIDATION_STAGES}
        stages["pre_evidence"] = {"scanned_files": 10}
        ticket = policy.reserve_validation(self.root, ctx, stages, "a" * 64, action="static")
        over = ctx["execution_budget"]["scanned_files"] + 50
        settled = policy.settle_validation(self.root, ctx, ticket, {"pre_evidence": {"scanned_files": over}}, status="PASS")
        self.assertEqual(settled["status"], "PASS")
        self.assertIn("scanned_files", settled["soft_over"])
        self.assertEqual(settled["over_budget"], {})

    def test_task_start_is_not_aborted_by_soft_scan_limit_but_hard_limit_still_is(self):
        """任务初始化阶段：软限只预警，不能在建任务时就 BUDGET_EXCEEDED；用户显式硬上限仍然生效。"""
        for index in range(2100):                     # 超过默认 2000 的未提交文件：旧实现在建任务时直接 BUDGET_EXCEEDED
            self.write(f"pkg/m{index}.py")
        started = self.context(request="soft-start", budget={"retries": 2})
        self.assertNotIn("scanned_files", policy.hard_resources(started["context"]))
        with self.assertRaises(ValueError) as denied:
            self.context(budget={"scanned_files": 5}, request="hard-start")
        self.assertIn("BUDGET_EXCEEDED", str(denied.exception))

    def test_adaptive_soft_thresholds_scale_with_repository(self):
        small = policy.adaptive_defaults(self.root)
        self.assertEqual(small["scanned_files"], 2000)
        for index in range(900):
            self.write(f"pkg/m{index}.py")
        self.commit()
        big = policy.adaptive_defaults(self.root)
        self.assertGreaterEqual(big["scanned_files"], 3 * 900)
        self.assertGreater(big["elapsed_seconds"], small["elapsed_seconds"])
        self.assertEqual(self.context(request="r2")["context"]["execution_budget"]["scanned_files"], big["scanned_files"])


class ConcurrencyTests(RepoCase):
    def test_resource_group_is_exclusive_across_parent_and_child(self):
        import inspect
        self.assertIn("group", inspect.signature(policy.acquire_slot).parameters)
        parent = self.context(budget={"processes": 3})
        child = entry.fork_context(self.root, parent["execution_context"], child_key="unit",
                                   write_set=["src/app.py"])
        held = policy.acquire_slot(self.root, parent["context"], "test", group="database")["slot"]
        self.assertEqual(held["group"], "database")
        queued = policy.acquire_slot(self.root, child["context"], "test", group="database")
        self.assertEqual(queued["status"], "QUEUED", "根并发有余量也不能同时占用共享数据库")
        policy.cancel_queued(self.root, child["context"], queued["ticket_id"])
        other = policy.acquire_slot(self.root, child["context"], "test", group="other")["slot"]
        policy.release_slot(self.root, child["context"], other)
        policy.release_slot(self.root, parent["context"], held)
        with policy.concurrency_slot(self.root, child["context"], "test", group="database"):
            self.assertEqual(len(policy.slot_status(self.root, parent["context"])["running"]), 1)
        self.assertEqual(policy.slot_status(self.root, parent["context"])["running"], [])

    def test_cli_group_wait_does_not_leave_queue_ticket(self):
        result = self.context(budget={"processes": 3})
        rc, held = self.cli(result, "acquire-slot", "--kind", "test", "--group", "database")
        self.assertEqual(rc, 0)
        rc, waiting = self.cli(result, "acquire-slot", "--kind", "test", "--group", "database")
        self.assertEqual((rc, waiting["status"], waiting["group_busy"]), (2, "QUEUED", True))
        self.assertEqual(policy.slot_status(self.root, result["context"])["queued"], [])
        self.cli(result, "release-slot", "--slot-id", held["slot"]["slot_id"])
        rc, acquired = self.cli(result, "acquire-slot", "--kind", "test", "--group", "database")
        self.assertEqual(rc, 0)
        self.cli(result, "release-slot", "--slot-id", acquired["slot"]["slot_id"])
        self.assertEqual(policy.slot_status(self.root, result["context"])["running"], [])

    def test_light_child_executes_but_cannot_delegate_again(self):
        parent = self.context()
        child = entry.fork_context(self.root, parent["execution_context"], child_key="unit",
                                   write_set=["src/app.py"])
        self.assertEqual(policy.require_action(child["context"], "related-test")["task_id"], child["task_id"])
        with self.assertRaises(policy.PolicyError) as denied:
            policy.require_delegable(child["context"], "related-test")
        self.assertEqual(denied.exception.status, "UNAUTHORIZED")
        self.assertEqual(policy.require_delegable(parent["context"], "related-test")["task_id"], parent["task_id"])

    def test_command_lock_wait_is_cancellable(self):
        import inspect
        import test_ledger as ledger
        self.assertIn("cancel_event", inspect.signature(ledger.lock).parameters)
        cancel = threading.Event()
        errors = []
        def wait_for_key():
            try:
                with ledger.lock(self.root, "same-test", cancel_event=cancel):
                    errors.append("acquired")
            except ledger.LedgerError:
                errors.append("cancelled")
        with ledger.lock(self.root, "same-test"):
            thread = threading.Thread(target=wait_for_key)
            thread.start()
            cancel.set()
            thread.join(1)
            self.assertFalse(thread.is_alive())
        self.assertEqual(errors, ["cancelled"])

    def test_live_holder_survives_lease_expiry(self):
        ctx = self.context(budget={"processes": 1})["context"]
        held = policy.acquire_slot(self.root, ctx, "test", lease_seconds=.01)["slot"]
        time.sleep(.03)
        queued = policy.acquire_slot(self.root, ctx, "test")
        self.assertEqual(queued["status"], "QUEUED", "活跃持有者不能因租约过期被误回收")
        policy.cancel_queued(self.root, ctx, queued["ticket_id"])
        policy.release_slot(self.root, ctx, held)

    def test_interrupt_while_waiting_removes_own_queue_ticket(self):
        from unittest import mock
        ctx = self.context(budget={"processes": 1})["context"]
        held = policy.acquire_slot(self.root, ctx, "test")["slot"]
        with mock.patch.object(policy.time, "sleep", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                policy.acquire_slot(self.root, ctx, "test", wait_seconds=5)
        self.assertEqual(policy.slot_status(self.root, ctx)["queued"], [])
        policy.release_slot(self.root, ctx, held)

    def test_invalid_lease_cannot_make_pid_zero_slot_permanent(self):
        ctx = self.context()["context"]
        for value in (float("nan"), float("inf"), 0, -1):
            with self.subTest(value=value), self.assertRaises(policy.PolicyError):
                policy.acquire_slot(self.root, ctx, "test", pid=0, lease_seconds=value)
        self.assertEqual(policy.slot_status(self.root, ctx)["running"], [])

    def test_waiting_cancellation_removes_queue(self):
        ctx = self.context(budget={"processes": 1})["context"]
        held = policy.acquire_slot(self.root, ctx, "test")["slot"]
        cancel = threading.Event()
        errors = []
        def wait():
            try:
                with policy.concurrency_slot(self.root, ctx, "test", wait_seconds=5, cancel_event=cancel):
                    self.fail("cancelled waiter started")
            except policy.PolicyError as exc:
                errors.append(exc.status)
        thread = threading.Thread(target=wait)
        thread.start()
        deadline = time.monotonic() + 3
        while not policy.slot_status(self.root, ctx)["queued"] and time.monotonic() < deadline:
            time.sleep(.01)
        cancel.set()
        thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, ["CANCELLED"])
        self.assertEqual(policy.slot_status(self.root, ctx)["queued"], [])
        policy.release_slot(self.root, ctx, held)

    def test_hard_limit_queues_and_release_unblocks_in_order(self):
        """场景2：并发达上限排队（可见），释放后按序取得。"""
        ctx = self.context()["context"]
        limit = ctx["execution_budget"]["agents"]
        held = [policy.acquire_slot(self.root, ctx, "agent")["slot"] for _ in range(limit)]
        queued = policy.acquire_slot(self.root, ctx, "agent", wait_seconds=0.2, poll_seconds=0.05)
        self.assertEqual(queued["status"], "QUEUED")
        self.assertEqual(queued["position"], 1)
        status = policy.slot_status(self.root, ctx)
        self.assertEqual(len(status["running"]), limit)
        self.assertEqual(len(status["queued"]), 1)
        got = {}
        thread = threading.Thread(target=lambda: got.update(policy.acquire_slot(
            self.root, ctx, "agent", wait_seconds=5, poll_seconds=0.05)))
        policy.cancel_queued(self.root, ctx, queued["ticket_id"])
        thread.start()
        time.sleep(0.3)
        self.assertEqual(got, {})
        policy.release_slot(self.root, ctx, held[0])
        thread.join(5)
        self.assertEqual(got["status"], "ACQUIRED")
        self.assertEqual(len(policy.slot_status(self.root, ctx)["running"]), limit)

    def test_release_on_exception_cancel_and_timeout(self):
        """场景2：正常、异常、取消（排队超时撤销）后均释放额度。"""
        ctx = self.context()["context"]
        limit = ctx["execution_budget"]["agents"]
        with policy.concurrency_slot(self.root, ctx, "agent"):
            self.assertEqual(len(policy.slot_status(self.root, ctx)["running"]), 1)
        self.assertEqual(policy.slot_status(self.root, ctx)["running"], [])
        with self.assertRaises(RuntimeError):
            with policy.concurrency_slot(self.root, ctx, "agent"):
                raise RuntimeError("boom")
        self.assertEqual(policy.slot_status(self.root, ctx)["running"], [])
        held = [policy.acquire_slot(self.root, ctx, "agent")["slot"] for _ in range(limit)]
        with self.assertRaises(policy.PolicyError) as timed_out:
            with policy.concurrency_slot(self.root, ctx, "agent", wait_seconds=0.2):
                self.fail("不应取得槽位")
        self.assertEqual(timed_out.exception.status, "QUEUED")
        status = policy.slot_status(self.root, ctx)
        self.assertEqual(status["queued"], [], "排队超时必须撤销队列项，不留孤儿")
        self.assertEqual(len(status["running"]), limit)
        for slot in held:
            policy.release_slot(self.root, ctx, slot)
        self.assertEqual(policy.release_slot(self.root, ctx, held[0])["status"], "NOT_HELD")

    def test_dead_holder_and_expired_lease_are_reclaimed(self):
        ctx = self.context()["context"]
        limit = ctx["execution_budget"]["agents"]
        for _ in range(limit):
            policy.acquire_slot(self.root, ctx, "agent", pid=2 ** 22 + 12345)   # 不存在的进程
        reclaimed = policy.acquire_slot(self.root, ctx, "agent", pid=os.getpid())
        self.assertEqual(reclaimed["status"], "ACQUIRED")
        self.assertEqual(len(policy.slot_status(self.root, ctx)["running"]), 1)
        policy.release_slot(self.root, ctx, reclaimed["slot"])
        policy.acquire_slot(self.root, ctx, "agent", lease_seconds=.01, pid=0)
        time.sleep(.03)
        self.assertEqual(policy.acquire_slot(self.root, ctx, "agent", pid=0)["status"], "ACQUIRED")

    def test_parent_and_child_share_one_pool(self):
        """场景3：父子任务共用根并发池，不各自获得独立额度。"""
        parent = entry.resolve_context(self.root, "sprint-batch", version="V1", write_set=["src/app.py"],
            authorization_source={"kind": "explicit-command", "request_id": "batch", "command": "/sprint-batch"},
            execution_budget={"agents": 3})
        child = entry.fork_context(self.root, parent["execution_context"], "001")
        limit = parent["context"]["execution_budget"]["agents"]
        self.assertEqual(limit, 3)
        results = []
        for index in range(limit + 2):
            holder = parent["context"] if index % 2 == 0 else child["context"]
            results.append(policy.acquire_slot(self.root, holder, "agent", wait_seconds=0.05, poll_seconds=0.02)["status"])
        self.assertEqual(results.count("ACQUIRED"), limit)
        self.assertEqual(results.count("QUEUED"), 2)
        self.assertEqual(len(policy.slot_status(self.root, child["context"])["running"]), limit)

    def cli(self, result, *args, env=None):
        base = [sys.executable, str(SCRIPTS / "execution_policy.py")]
        out = subprocess.run([*base, *args, "--root", str(self.root), "--execution-context", result["execution_context"]],
                             capture_output=True, text=True, env=dict(os.environ, **(env or {})))
        return out.returncode, (json.loads(out.stdout) if out.stdout.strip() else {})

    def test_cli_queued_exits_nonzero_and_leaves_no_orphan_ticket(self):
        """P0-1：CLI 没拿到槽位必须非零退出（流程 `|| exit $?` 才会停），且不留孤儿排队票据把池永久堵死。"""
        result = self.context()
        limit = result["context"]["execution_budget"]["agents"]
        slots = []
        for _ in range(limit):
            rc, out = self.cli(result, "acquire-slot", "--kind", "agent")
            self.assertEqual((rc, out["status"]), (0, "ACQUIRED"))
            slots.append(out["slot"]["slot_id"])
        rc, out = self.cli(result, "acquire-slot", "--kind", "agent", "--wait-seconds", "0.2")
        self.assertEqual((rc, out["status"]), (2, "QUEUED"))
        self.assertEqual(policy.slot_status(self.root, result["context"])["queued"], [])
        for slot_id in slots:
            self.assertEqual(self.cli(result, "release-slot", "--slot-id", slot_id)[1]["status"], "RELEASED")
        rc, out = self.cli(result, "acquire-slot", "--kind", "agent")
        self.assertEqual((rc, out["status"]), (0, "ACQUIRED"), "全部释放后新申请必须立即成功，而不是排在孤儿票据后面")

    def test_stale_queue_tickets_expire(self):
        ctx = self.context()["context"]
        limit = ctx["execution_budget"]["agents"]
        for _ in range(limit):
            policy.acquire_slot(self.root, ctx, "agent")
        queued = policy.acquire_slot(self.root, ctx, "agent", wait_seconds=0.05, poll_seconds=0.02)
        self.assertEqual(queued["status"], "QUEUED")
        path = self.root / "memory/.aidp/entry-contexts" / ctx["task_id"] / "budget.json"
        state = json.loads(path.read_text())
        state["queue"][0]["enqueued_at"] -= policy.QUEUE_TTL_SECONDS + 5
        path.write_text(json.dumps(state))
        policy.slot_status(self.root, ctx)
        got = policy.acquire_slot(self.root, ctx, "agent", wait_seconds=0.05, poll_seconds=0.02)
        self.assertEqual(got["position"], 1, "过期的孤儿票据不能继续挡在队首")

    def test_new_tick_does_not_reclaim_a_still_running_process(self):
        from unittest import mock
        ctx = self.context(budget={'processes': 1})['context']
        with mock.patch.dict(os.environ, {'AIDP_TICK_COMMAND': 'sprint-autopilot', 'AIDP_TICK_TOKEN': 'previous'}):
            held = policy.acquire_slot(self.root, ctx, 'test')['slot']
        result = policy.reap_slots(self.root, ctx, 'sprint-autopilot', keep_tick='next')
        self.assertEqual(result['reaped'], 0)
        queued = policy.acquire_slot(self.root, ctx, 'test')
        self.assertEqual(queued['status'], 'QUEUED')
        policy.cancel_queued(self.root, ctx, queued['ticket_id'])
        policy.release_slot(self.root, ctx, held)

    def test_reap_slots_only_clears_previous_tick_of_the_same_chain(self):
        """P0-1：tick 开始时回收同链路上一轮遗留槽位；并行的另一条链路（aiauto 测试链）的槽位不受影响。"""
        result = self.context()
        ctx = result["context"]
        env = {"AIDP_TICK_COMMAND": "sprint-autopilot", "AIDP_TICK_TOKEN": "tick-old"}
        other = {"AIDP_TICK_COMMAND": "sprint-aiauto-test", "AIDP_TICK_TOKEN": "tick-test"}
        self.assertEqual(self.cli(result, "acquire-slot", "--kind", "agent", env=env)[0], 0)
        self.assertEqual(self.cli(result, "acquire-slot", "--kind", "agent", env=other)[0], 0)
        self.assertEqual(policy.reap_slots(self.root, ctx, "sprint-autopilot", keep_tick="tick-new")["reaped"], 1)
        remaining = policy.slot_status(self.root, ctx)["running"]
        self.assertEqual([row["chain"] for row in remaining], ["sprint-aiauto-test"])
        self.assertEqual(policy.reap_slots(self.root, ctx, "sprint-aiauto-test", keep_tick="tick-test")["reaped"], 0)

    def test_cumulative_started_count_is_statistics_only(self):
        ctx = self.context()["context"]
        for _ in range(10):
            policy.reserve_budget(self.root, ctx, "processes", 1)
        slot = policy.acquire_slot(self.root, ctx, "test")
        self.assertEqual(slot["status"], "ACQUIRED")
        status = policy.slot_status(self.root, ctx)
        self.assertEqual(status["started_total"]["processes"], 1)        # 槽位累计启动数单独统计
        used = json.loads(Path(entry.load_context(self.root, ctx)["execution_context"] if False else
                          (self.root / "memory/.aidp/entry-contexts" / ctx["task_id"] / "budget.json")).read_text())["used"]
        self.assertEqual(used["processes"], 10)                           # reserve_budget 的统计不被槽位双计


class ParallelScopeTests(RepoCase):
    def prepare_scope(self, *, workers=2, groups=None, outcomes=(0, 0, 0), delay=.18, parallel=True,
                      batch_size=None, delays=None):
        import test_ledger as ledger
        import inspect
        self.assertIn("max_parallel", inspect.signature(ledger.run_scope).parameters,
                      "run_scope 须接入有界外层并发")
        (self.root / "tests/test_app.py").unlink()
        for index, outcome in enumerate(outcomes):
            self.write(f"tests/g{index}/test_app.py", (
                "import fcntl, json, os, sys, time\nfrom pathlib import Path\n"
                "sys.path.insert(0, str(Path(__file__).resolve().parents[2]))\nfrom src.app import value\n"
                "def event(kind):\n"
                " with open(Path(__file__).resolve().parents[2] / 'memory/.aidp/events.jsonl', 'a') as f:\n"
                "  fcntl.flock(f, fcntl.LOCK_EX)\n"
                f"  f.write(json.dumps([kind, {index}, time.monotonic()]) + '\\n')\n"
                f"event('start')\ntime.sleep({delays[index] if delays else delay + index * .01})\nevent('end')\nraise SystemExit({outcome})\n"))
        if batch_size:
            self.write("runner.py", "import runpy, sys\nfor path in sys.argv[1:]:\n"
                       " try: runpy.run_path(path, run_name='__main__')\n"
                       " except SystemExit as exc:\n  if exc.code: raise\n")
        self.commit()
        result = self.context(budget={"processes": workers}, write_set=("src/app.py",))
        runners = []
        for index in range(len(outcomes)):
            runner = {"cwd": ".", "suffixes": [".py"], "argv": [sys.executable, "-B", "{tests}"], "batch": False}
            if batch_size:
                runner.update(batch=True, batch_size=batch_size, argv=[sys.executable, "-B", "runner.py", "{tests}"])
            if groups is not None:
                runner["cwd"] = f"tests/g{index}"
            if parallel:
                runner["parallel"] = {"enabled": True, "workers": 1}
                if groups is not None:
                    runner["parallel"]["group"] = groups[index]
            runners.append(runner)
            if groups is None:
                break
        self.write("src/app.py", "value = 2\n")
        plan = scope.derive(self.root, None, runners, execution_context=result["execution_context"])
        path = Path(result["execution_context"]).with_name("parallel-scope.json")
        path.write_text(json.dumps(plan))
        return result, path, plan

    def peak(self):
        events = [json.loads(line) for line in (self.root / "memory/.aidp/events.jsonl").read_text().splitlines()]
        current = peak = 0
        for kind, _, _ in events:
            current += 1 if kind == "start" else -1
            peak = max(peak, current)
        return peak

    def test_real_processes_overlap_but_respect_shared_root_limit_and_settle(self):
        import test_ledger as ledger
        ctx, path, plan = self.prepare_scope(workers=2)
        out, code = ledger.run_scope(self.root, str(path), "local", execution_context=ctx["execution_context"], max_parallel=3)
        self.assertEqual((out["status"], code), ("PASS", 0), out)
        self.assertEqual(self.peak(), 2)
        self.assertEqual(len(out["run_ids"]), 3)
        self.assertEqual(policy.slot_status(self.root, ctx["context"])["running"], [])
        budget = json.loads(Path(ctx["execution_context"]).with_name("budget.json").read_text())
        tickets = [r for r in budget["reservations"] if r.get("action") == "related-test"]
        self.assertEqual(len(tickets), 3)
        self.assertTrue(all("settlement" in ticket for ticket in tickets))
        verified = ledger.verify_scope(self.root, str(path), plan["scope_hash"], out["run_ids"], "local",
                                       execution_context=ctx["execution_context"])
        self.assertEqual(verified["status"], "PASS")

    def test_undeclared_runners_remain_serial(self):
        import test_ledger as ledger
        ctx, path, _ = self.prepare_scope(parallel=False)
        out, code = ledger.run_scope(self.root, str(path), "local", execution_context=ctx["execution_context"], max_parallel=3)
        self.assertEqual(code, 0, out)
        self.assertEqual(self.peak(), 1)

    def test_failures_keep_plan_order_and_deterministic_verdict(self):
        import test_ledger as ledger
        ctx, path, _ = self.prepare_scope(outcomes=(7, 0, 0), delays=(.6, .05, .05))
        out, code = ledger.run_scope(self.root, str(path), "local", execution_context=ctx["execution_context"], max_parallel=3)
        self.assertEqual((out["status"], code), ("FAIL", 1), out)
        self.assertEqual([r["status"] for r in out["runs"]], ["FAIL", "PASS", "PASS"])
        self.assertEqual(len(ledger.load(self.root)), 3)

    def test_explicit_frozen_batches_execute_and_verify_without_changing_argv(self):
        import test_ledger as ledger
        ctx, path, plan = self.prepare_scope(outcomes=(0, 0, 0, 0, 0), batch_size=2)
        self.assertEqual([len(item["tests"]) for item in plan["runs"]], [2, 2, 1])
        out, code = ledger.run_scope(self.root, str(path), "local", execution_context=ctx["execution_context"], max_parallel=3)
        self.assertEqual((out["status"], code), ("PASS", 0), out)
        self.assertEqual(self.peak(), 2)
        self.assertEqual([row["command"] for row in out["runs"]], [item["argv"] for item in plan["runs"]])
        self.assertEqual(ledger.verify_scope(self.root, str(path), plan["scope_hash"], out["run_ids"], "local",
                                            execution_context=ctx["execution_context"])["status"], "PASS")

    def test_run_scope_waits_for_root_group_holder_and_cancels_cleanly(self):
        import inspect
        import test_ledger as ledger
        self.assertIn("group", inspect.signature(policy.acquire_slot).parameters)
        ctx, path, _ = self.prepare_scope(groups=("database", "database", "database"))
        held = policy.acquire_slot(self.root, ctx["context"], "test", group="database")["slot"]
        cancel = threading.Event()
        results = []
        thread = threading.Thread(target=lambda: results.append(ledger.run_scope(
            self.root, str(path), "local", execution_context=ctx["execution_context"], max_parallel=3, cancel_event=cancel)))
        thread.start()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not policy.slot_status(self.root, ctx["context"])["queued"]:
            time.sleep(.01)
        waiting = policy.slot_status(self.root, ctx["context"])["queued"]
        cancel.set()
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertTrue(waiting, "另一个run_scope的同组持有者必须挡住本次执行")
        self.assertFalse((self.root / "memory/.aidp/events.jsonl").exists(), "等待同组资源时不能启动测试")
        self.assertEqual(results[0][0]["status"], "UNVERIFIED")
        state = policy.slot_status(self.root, ctx["context"])
        self.assertEqual(state["queued"], [])
        self.assertEqual([r["slot_id"] for r in state["running"]], [held["slot_id"]])
        policy.release_slot(self.root, ctx["context"], held)
        out, code = ledger.run_scope(self.root, str(path), "local", execution_context=ctx["execution_context"], max_parallel=3)
        self.assertEqual((out["status"], code), ("PASS", 0), out)
        self.assertEqual(self.peak(), 1)

    def test_independent_runners_can_overlap(self):
        import test_ledger as ledger
        ctx, path, _ = self.prepare_scope(groups=("db1", "db2", "db3"))
        out, code = ledger.run_scope(self.root, str(path), "local", execution_context=ctx["execution_context"], max_parallel=3)
        self.assertEqual(code, 0, out)
        self.assertEqual(self.peak(), 2)

    def test_shared_group_serializes_different_runners(self):
        import test_ledger as ledger
        ctx, path, _ = self.prepare_scope(groups=("database", "database", "database"))
        out, code = ledger.run_scope(self.root, str(path), "local", execution_context=ctx["execution_context"], max_parallel=3)
        self.assertEqual(code, 0, out)
        self.assertEqual(self.peak(), 1)

    def test_cancellation_kills_active_processes_and_settles_all_started_runs(self):
        import test_ledger as ledger
        ctx, path, _ = self.prepare_scope(delay=5)
        cancel = threading.Event()
        results = []
        thread = threading.Thread(target=lambda: results.append(ledger.run_scope(
            self.root, str(path), "local", execution_context=ctx["execution_context"], max_parallel=3, cancel_event=cancel)))
        thread.start()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            event_file = self.root / "memory/.aidp/events.jsonl"
            if event_file.exists() and len(event_file.read_text().splitlines()) >= 2:
                break
            time.sleep(.01)
        cancel.set()
        thread.join(5)
        self.assertFalse(thread.is_alive(), "取消必须停止子进程，不能等待完整5秒测试结束")
        self.assertTrue(results)
        out, code = results[0]
        self.assertEqual((out["status"], code), ("UNVERIFIED", 2), out)
        state = policy.slot_status(self.root, ctx["context"])
        self.assertEqual((state["running"], state["queued"]), ([], []))
        rows = ledger.load(self.root)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r["status"] == "ERROR" and r["failure_kind"] == "CANCELLED" for r in rows))
        budget = json.loads(Path(ctx["execution_context"]).with_name("budget.json").read_text())
        self.assertTrue(all("settlement" in r for r in budget["reservations"] if r.get("kind") == "validation"))

    def test_cli_termination_cleans_children_and_reservations(self):
        import test_ledger as ledger
        ctx, path, _ = self.prepare_scope(delay=.6)
        proc = subprocess.Popen([sys.executable, str(SCRIPTS / "test_ledger.py"), "run-scope", "--root", str(self.root),
                                 "--scope-file", str(path), "--env-id", "local", "--execution-context",
                                 ctx["execution_context"], "--max-parallel", "3"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        deadline = time.monotonic() + 5
        event_file = self.root / "memory/.aidp/events.jsonl"
        while time.monotonic() < deadline:
            if event_file.exists() and len(event_file.read_text().splitlines()) >= 2:
                break
            time.sleep(.01)
        proc.terminate()
        stdout, stderr = proc.communicate(timeout=5)
        self.assertEqual(proc.returncode, 2, stdout + stderr)
        self.assertEqual(json.loads(stdout.splitlines()[-1])["status"], "UNVERIFIED")
        self.assertEqual(policy.slot_status(self.root, ctx["context"])["running"], [])
        self.assertTrue(all(row["status"] != "RUNNING" for row in ledger.load(self.root)))
        budget = json.loads(Path(ctx["execution_context"]).with_name("budget.json").read_text())
        self.assertTrue(all("settlement" in r for r in budget["reservations"] if r.get("kind") == "validation"))

    def test_timeouts_settle_every_ticket_and_clear_slots(self):
        import test_ledger as ledger
        ctx, path, _ = self.prepare_scope(delay=.4)
        out, code = ledger.run_scope(self.root, str(path), "local", timeout=.05,
                                    execution_context=ctx["execution_context"], max_parallel=3)
        self.assertEqual((out["status"], code), ("UNVERIFIED", 2), out)
        self.assertEqual([r["failure_kind"] for r in out["runs"]], ["TIMEOUT"] * 3)
        self.assertEqual(policy.slot_status(self.root, ctx["context"])["running"], [])
        budget = json.loads(Path(ctx["execution_context"]).with_name("budget.json").read_text())
        self.assertTrue(all("settlement" in r for r in budget["reservations"] if r.get("kind") == "validation"))


class LegacyLedgerTests(RepoCase):
    def test_pre_concurrency_budget_json_is_readable_and_slots_work(self):
        """V1.2.4 形态的 budget.json（没有 slots/queue/soft_events/progress/started）必须兼容。"""
        result = self.context()
        ctx = result["context"]
        path = Path(result["execution_context"]).with_name("budget.json")
        legacy = {"task_id": ctx["task_id"], "used": {key: 0 for key in policy.DEFAULT_BUDGET},
                  "outcomes": [], "reservations": []}
        path.write_text(json.dumps(legacy))
        usage = policy.budget_usage(self.root, result["execution_context"])
        self.assertEqual(usage["resources"]["agents"]["class"], "concurrent")
        got = policy.acquire_slot(self.root, ctx, "agent")
        self.assertEqual(got["status"], "ACQUIRED")
        saved = json.loads(path.read_text())
        self.assertTrue({"slots", "queue", "soft_events", "progress", "started"} <= set(saved))
        policy.release_slot(self.root, ctx, got["slot"])

    def test_zero_concurrency_fails_fast_instead_of_queueing_until_timeout(self):
        ctx = self.context(budget={"agents": 0})["context"]
        started = time.monotonic()
        with self.assertRaises(policy.PolicyError) as denied:
            policy.acquire_slot(self.root, ctx, "agent", wait_seconds=30)
        self.assertEqual(denied.exception.status, "BUDGET_EXCEEDED")
        self.assertLess(time.monotonic() - started, 5)

    def test_reserve_budget_cli_labels_concurrent_resources_as_statistics(self):
        result = self.context()
        out = subprocess.run([sys.executable, str(SCRIPTS / "execution_policy.py"), "reserve-budget", "--root", str(self.root),
                              "--execution-context", result["execution_context"], "--resource", "agents", "--cost", "1",
                              "--input-hash", "a" * 64], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("acquire-slot", json.loads(out.stdout)["note"])


class ExplicitRelatedTestsTests(RepoCase):
    def run_select(self, *args, expect=0):
        out = subprocess.run([sys.executable, str(SELECT), "--root", str(self.root), "--json", *args],
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, expect, out.stderr)
        return json.loads(out.stdout) if expect == 0 else out

    def test_explicit_entry_builds_allowlist_without_dependency_scan(self):
        """场景5：已明确的少量相关测试可经正式入口执行，不先做全仓依赖扫描。"""
        for index in range(30):
            self.write(f"src/m{index}.py")
            self.write(f"tests/test_m{index}.py", f"import src.m{index}\n")
        self.write("tests/unit/test_extra.py")
        self.commit()
        result = self.context(write_set=("src/m3.py",))
        ctx = result["execution_context"]
        derive_calls = []
        out = self.run_select("--execution-context", ctx, "--explicit-tests", "tests/test_m3.py", "tests/unit/test_extra.py",
                              "--basis", "人工确认：m3 及其联动用例", "--command", "pytest tests/test_m3.py")
        self.assertEqual(out["tests"], ["tests/test_m3.py", "tests/unit/test_extra.py"])
        explicit = out["basis"]["explicit"]
        self.assertEqual(out["basis"]["mode"], "explicit")
        self.assertEqual(explicit["scan"], {"content_reads": 0, "dependency_scan": False})
        self.assertEqual(explicit["relations"]["tests/test_m3.py"], "name-mapped")
        self.assertEqual(explicit["relations"]["tests/unit/test_extra.py"], "declared")
        self.assertEqual(explicit["command"], "pytest tests/test_m3.py")
        self.assertEqual(explicit["task_id"], result["task_id"])
        self.assertFalse(derive_calls)
        ok = guard.evaluate("pytest tests/test_m3.py", str(self.root), execution_context=ctx)
        self.assertTrue(ok["allowed"], ok)
        self.assertFalse(guard.evaluate("pytest tests/test_m4.py", str(self.root), execution_context=ctx)["allowed"])
        self.assertFalse(guard.evaluate("pytest tests", str(self.root), execution_context=ctx)["allowed"])

    def test_explicit_entry_rejects_missing_outside_non_test_and_unrelated_without_basis(self):
        self.write("other/test_far.py")
        self.write("README_TEST.md", "x\n")
        self.commit()
        ctx = self.context()["execution_context"]
        for bad, needle in (("tests/test_missing.py", "不存在"), ("src/app.py", "不是测试文件"),
                            ("../outside_test.py", "root 内相对路径"), ("other/test_far.py", "无可核对关系")):
            out = self.run_select("--execution-context", ctx, "--explicit-tests", bad, expect=2)
            self.assertIn(needle, out.stderr)
        self.assertFalse((self.root / "memory/.aidp/test-allowlist").exists()
                         and any((self.root / "memory/.aidp/test-allowlist").iterdir()))
        good = self.run_select("--execution-context", ctx, "--explicit-tests", "other/test_far.py", "--basis", "人工确认其相关")
        self.assertEqual(good["basis"]["explicit"]["relations"]["other/test_far.py"], "declared")

    def test_explicit_entry_requires_related_test_authorization_and_cannot_forge(self):
        ctx = entry.resolve_context(self.root, "sprint-dev", version="V1", write_set=["src/app.py"],
            additional_grants=[], authorization_source={"kind": "user-text", "request_id": "no-test",
                                                       "text": "只改代码，跳过验证", "skip_actions": ["related-test"]})
        out = self.run_select("--execution-context", ctx["execution_context"], "--explicit-tests", "tests/test_app.py", expect=2)
        self.assertIn("related-test", out.stderr)

    def test_explicit_entry_without_context_needs_basis_and_never_widens(self):
        out = self.run_select("--explicit-tests", "tests/test_app.py", expect=2)
        self.assertIn("--basis", out.stderr)
        res = self.run_select("--explicit-tests", "tests/test_app.py", "--basis", "手工选择")
        self.assertEqual(res["tests"], ["tests/test_app.py"])
        self.assertTrue(guard.evaluate("pytest tests/test_app.py", str(self.root))["allowed"])
        self.assertFalse(guard.evaluate("pytest", str(self.root))["allowed"])

    def test_selection_and_budget_adjustment_never_record_pass_or_widen_authorization(self):
        """场景9：选测/调额都不会把未执行的测试记为 PASS，也不借预算调整扩大动作授权。"""
        result = self.context()
        ctx = result["execution_context"]
        before = set(result["context"]["allowed_actions"])
        self.run_select("--execution-context", ctx, "--explicit-tests", "tests/test_app.py", "--basis", "x")
        state = json.loads((Path(ctx).with_name("budget.json")).read_text()) if Path(ctx).with_name("budget.json").exists() else {"outcomes": []}
        self.assertFalse([row for row in state["outcomes"] if row.get("status") == "PASS"])
        policy.reserve_budget(self.root, result["context"], "scanned_files", result["context"]["execution_budget"]["scanned_files"] + 1)
        reloaded = entry.load_context(self.root, ctx)
        self.assertEqual(set(reloaded["allowed_actions"]), before)
        for action in ("full-regression", "deploy", "push", "commit"):
            with self.assertRaises(policy.PolicyError):
                policy.require_action(reloaded, action)
        # 白名单只含显式文件；无参/整目录/全量命令仍被护栏拒绝
        for command in ("pytest", "pytest tests", "python3 -m pytest -x"):
            self.assertFalse(guard.evaluate(command, str(self.root), execution_context=ctx)["allowed"], command)

    def test_explicit_entry_unions_with_existing_allowlist(self):
        ctx = self.context()["execution_context"]
        self.write("tests/test_two.py"); self.commit()
        self.run_select("--execution-context", ctx, "--explicit-tests", "tests/test_app.py", "--basis", "a")
        out = self.run_select("--execution-context", ctx, "--explicit-tests", "tests/test_two.py", "--basis", "b")
        self.assertEqual(out["tests"], ["tests/test_app.py", "tests/test_two.py"])
        stored = json.loads((self.root / out["allowlist_file"]).read_text())
        self.assertEqual(len(stored["explicit"]), 2)


class IncrementalAnalysisTests(RepoCase):
    def build(self, count=24):
        for index in range(count):
            self.write(f"src/m{index}.py", f"value = {index}\n")
            self.write(f"tests/test_m{index}.py", f"import unittest\nfrom src.m{index} import value\n")
        self.write("src/__init__.py", ""); self.write("tests/__init__.py", "")
        self.commit()

    def derive(self, write_set):
        scope._ANALYSIS_CACHE.clear()
        scope._ANALYSIS_EXTRA.clear()
        scope._FACTS_MEMORY.clear()
        stats = {}
        real = scope.FactsCache.save

        def spy(self_):
            stats.update(hits=self_.hits, misses=self_.misses)
            return real(self_)
        scope.FactsCache.save = spy
        try:
            plan = scope.derive(self.root, "HEAD", [], write_set, None)
        finally:
            scope.FactsCache.save = real
        return plan, stats

    def test_unrelated_change_does_not_invalidate_cached_facts_and_related_change_does(self):
        """场景6/7/8：只重解析变化文件；无关文件变化不致全量失效；相关依赖变化被正确识别。"""
        self.build()
        plan, cold = self.derive(["src/m1.py"])
        self.assertGreaterEqual(cold["misses"], 40)          # 冷启动：全部解析
        self.write("src/m1.py", "value = 100\n")
        plan, warm = self.derive(["src/m1.py"])
        self.assertLessEqual(warm["misses"], 1)               # 仅被改文件需要重解析
        self.assertGreater(warm["hits"], 0)                  # 窄分析只访问相关缓存，不要求全仓命中
        self.assertEqual(plan["selection"]["proven"], ["tests/test_m1.py"])
        # 改动与测试无关的文件（无任何 import 指向它）：其余文件不重解析
        self.write("notes/standalone.py", "z = 1\n")
        _, again = self.derive(["notes/standalone.py"])
        self.assertLessEqual(again["misses"], 2)
        # 相关依赖变化：m2 开始依赖 m5 → 改 m5 时 test_m2 必须被选中
        self.write("src/m2.py", "from src.m5 import value as v\nvalue = v\n")
        self.write("src/m5.py", "value = 55\n")
        plan, _ = self.derive(["src/m5.py"])
        self.assertIn("tests/test_m2.py", plan["selection"]["proven"])
        self.assertIn("tests/test_m5.py", plan["selection"]["proven"])
        self.assertNotIn("tests/test_m9.py", plan["selection"]["proven"])

    def test_checkpoint_resume_after_deadline_keeps_finished_work(self):
        """断点续扫：中途超时后已完成文件的事实已落盘，重跑不从头来。"""
        self.build(60)
        real_monotonic, real_put = scope.time.monotonic, scope.FactsCache.put
        state = {"puts": 0, "jump": 0}

        def ticking():
            return real_monotonic() + state["jump"]

        def counting_put(self_, path, digest_value, facts):
            real_put(self_, path, digest_value, facts)
            state["puts"] += 1
            if state["puts"] >= 15:
                state["jump"] = 10 ** 6      # 之后一切 deadline 检查都视为已超时
        scope.time.monotonic, scope.FactsCache.put = ticking, counting_put
        try:
            with self.assertRaises(scope.ScopeError) as caught:
                self.derive(["src/m1.py"])
        finally:
            scope.time.monotonic, scope.FactsCache.put = real_monotonic, real_put
        self.assertIn("断点续扫", str(caught.exception))
        facts = json.loads((self.root / "memory/.aidp/scope-facts/facts.json").read_text())
        self.assertGreater(len(facts["files"]), 10)
        _, resumed = self.derive(["src/m1.py"])
        self.assertGreater(resumed["hits"], 10)

    def test_changed_content_with_same_path_misses_cache(self):
        self.build(4)
        self.derive(["src/m1.py"])
        self.write("tests/test_m0.py", "import unittest\nfrom src.m3 import value\n")   # 导入关系变化
        plan, stats = self.derive(["src/m3.py"])
        self.assertGreaterEqual(stats["misses"], 1)
        self.assertIn("tests/test_m0.py", plan["selection"]["proven"])


class TimeoutAndProgressTests(RepoCase):
    def test_step_timeout_is_not_capped_by_hidden_low_limits(self):
        """场景11：统一超时配置不再被内部更低的硬编码值覆盖。"""
        ctx = self.context()["context"]
        self.assertEqual(policy.step_timeout(self.root, ctx, "scan"), 300.0)
        self.assertEqual(policy.step_timeout(self.root, ctx, "selection"), 60.0)
        self.assertEqual(policy.step_timeout(self.root, ctx, "scan", 900), 900.0)
        os.environ["AIDP_STEP_TIMEOUT_SCAN"] = "1234"
        try:
            self.assertEqual(policy.step_timeout(self.root, ctx, "scan"), 1234.0)
        finally:
            del os.environ["AIDP_STEP_TIMEOUT_SCAN"]
        hard = self.context(budget={"elapsed_seconds": 5}, request="hard")["context"]
        self.assertEqual(policy.step_timeout(self.root, hard, "scan"), 5.0)   # 用户硬上限仍封顶

    def test_no_hidden_min_constants_remain_in_scripts(self):
        pattern = re.compile(r"min\(\s*\d+(\.\d+)?\s*,[^)]*execution_budget")
        offenders = []
        for path in SCRIPTS.glob("*.py"):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if pattern.search(line) and not line.lstrip().startswith("#"):
                    offenders.append(f"{path.name}:{number}: {line.strip()}")
        self.assertEqual(offenders, [])

    def test_repeated_same_failure_is_not_retried_but_changed_input_is(self):
        """场景8：同输入同原因不重试；真实进展不被误判为卡死。"""
        ctx = self.context()["context"]
        same = "a" * 64
        policy.record_outcome(self.root, ctx, "related-test", "TOOL_ERROR", same, root_cause="missing-runner")
        policy.record_outcome(self.root, ctx, "related-test", "TOOL_ERROR", same, root_cause="missing-runner")
        with self.assertRaises(policy.PolicyError) as denied:
            policy.reserve_budget(self.root, ctx, "retries", 1, same, action="related-test")
        self.assertEqual(denied.exception.status, "TOOL_ERROR")
        self.assertEqual(policy.assess_progress(self.root, ctx, "analysis")["state"], "repeated-failure")
        policy.reserve_budget(self.root, ctx, "retries", 1, "b" * 64, action="related-test")  # 输入实质变化后可重新评估

    def test_progress_classification(self):
        ctx = self.context()["context"]
        policy.record_progress(self.root, ctx, "analysis", 10, 100, "解析中")
        now = time.time()
        advancing = policy.assess_progress(self.root, ctx, "analysis", now=now + 30, stall_seconds=300)
        self.assertEqual(advancing["state"], "advancing")
        self.assertIn("10/100", advancing["message"])
        stalled = policy.assess_progress(self.root, ctx, "analysis", now=now + 4000, stall_seconds=300)
        self.assertEqual(stalled["state"], "stalled")
        self.assertIn("不连带停摆整个任务", stalled["message"])
        grown = policy.record_progress(self.root, ctx, "scope", 5, 100)
        policy.record_progress(self.root, ctx, "scope", 6, 400)
        self.assertEqual(policy.assess_progress(self.root, ctx, "scope")["state"], "scope-growth")
        policy.record_progress(self.root, ctx, "analysis", 60, 100)
        self.assertEqual(policy.assess_progress(self.root, ctx, "analysis", now=time.time() + 5)["state"], "advancing")
        self.assertEqual(grown["stage"], "scope")


class LegacyMigrationTests(RepoCase):
    def test_public_commands_preserve_explicit_project_budget(self):
        configured = {"scanned_files": 5000, "elapsed_seconds": 600, "processes": 0,
                      "agents": 1, "selected_tests": 3, "retries": 0}
        self.write("memory/aidp-config.yaml", """execution_policy:
  authorization_source:
    kind: project-policy
    user_selected: true
    request_id: old-budget-choice
    text: 用户明确限定项目执行预算
  execution_budget:
""" + "".join(f"    {key}: {value}\n" for key, value in configured.items()))
        for command in ("version", "sprint-test", "sprint-autopilot"):
            with self.subTest(command=command):
                context = policy.policy_fields(self.root, [], [], authorization_source={
                    "kind": "explicit-command", "command": command, "request_id": "current-command"})
                self.assertEqual(context["execution_budget"], configured)
                self.assertTrue({"scanned_files", "elapsed_seconds"} <= policy.hard_resources(context))

    def test_public_command_defaults_fill_only_unconfigured_budget_keys(self):
        self.write("memory/aidp-config.yaml", """execution_policy:
  authorization_source:
    kind: project-policy
    user_selected: true
    request_id: partial-budget-choice
    text: 用户明确限定累计扫描最多5000文件
  execution_budget:
    scanned_files: 5000
""")
        source = {"kind": "explicit-command", "command": "sprint-test", "request_id": "current-command"}
        context = policy.policy_fields(self.root, [], [], authorization_source=source)
        expected = dict(policy.COMMAND_BUDGETS["sprint-test"], scanned_files=5000)
        self.assertEqual(context["execution_budget"], expected)
        revised = policy.policy_fields(self.root, [], [], authorization_source=source,
                                       execution_budget={"scanned_files": 6000})
        self.assertEqual(revised["execution_budget"], dict(expected, scanned_files=6000))

    def test_legacy_sources_keep_user_written_budget_hard(self):
        """场景10：旧项目配置兼容迁移——用户显式写入的值默认硬上限，不静默降为软限，并向用户展示。"""
        ctx = self.context()["context"]
        legacy = json.loads(json.dumps(ctx))
        legacy["authorization_source"] = [{"kind": "project-policy", "request_id": "old", "user_selected": True,
                                           "text": "项目策略", "actions": []}]          # 旧记录：没有 budget_keys
        self.assertTrue({"scanned_files", "elapsed_seconds"} <= policy.hard_resources(legacy))
        report = policy.budget_report(legacy)
        self.assertEqual(report["resources"]["scanned_files"]["class"], "hard")
        self.assertIn("不静默放宽", report["resources"]["scanned_files"]["why"])
        self.assertEqual(report["resources"]["agents"]["class"], "concurrent-hard")
        self.assertEqual(report["degrade_order"], list(policy.DEGRADE_STEPS))
        self.assertIn("不等于业务授权", report["note"])
        legacy["authorization_source"] = [{"kind": "user-text", "request_id": "old2", "text": "x", "actions": [],
                                           "execution_budget": {"scanned_files": 100}}]  # 旧修订记录
        self.assertIn("scanned_files", policy.hard_resources(legacy))
        legacy["authorization_source"] = [{"kind": "user-text", "request_id": "old3", "text": "x", "actions": []}]
        self.assertNotIn("scanned_files", policy.hard_resources(legacy))
        shrunk = json.loads(json.dumps(ctx))
        shrunk["execution_budget"]["elapsed_seconds"] = 10                             # 用户收紧到默认以下
        self.assertIn("elapsed_seconds", policy.hard_resources(shrunk))

    def test_budget_report_cli_and_slots_cli(self):
        result = self.context()
        base = [sys.executable, str(SCRIPTS / "execution_policy.py")]
        out = subprocess.run([*base, "budget-report", "--root", str(self.root), "--execution-context",
                              result["execution_context"]], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        report = json.loads(out.stdout)
        self.assertEqual(report["resources"]["scanned_files"]["class"], "soft")
        acquired = json.loads(subprocess.run([*base, "acquire-slot", "--root", str(self.root), "--execution-context",
            result["execution_context"], "--kind", "agent"], capture_output=True, text=True).stdout)
        self.assertEqual(acquired["status"], "ACQUIRED")
        listed = json.loads(subprocess.run([*base, "slots", "--root", str(self.root), "--execution-context",
            result["execution_context"]], capture_output=True, text=True).stdout)
        self.assertEqual(len(listed["running"]), 1)
        released = json.loads(subprocess.run([*base, "release-slot", "--root", str(self.root), "--execution-context",
            result["execution_context"], "--slot-id", acquired["slot"]["slot_id"]], capture_output=True, text=True).stdout)
        self.assertEqual(released["status"], "RELEASED")


class ConfigUnknownKeyTests(RepoCase):
    def test_typo_keys_are_reported_but_free_form_sections_and_template_are_clean(self):
        import aidp_config as cfg
        self.assertEqual(cfg.config_warnings(str(SCRIPTS.parents[1])), [], "仓库自带配置不得有未知键")
        (self.root / "memory").mkdir(exist_ok=True)
        (self.root / "memory/aidp-config.yaml").write_text(
            "entry_gaurd:\n  enabled: false\nscheduler:\n  agnt: claude\n  exec: {codex: x}\n"
            "cicd:\n  pipelines: {test: a.yml}\ncustom_user:\n  anything: 1\nexecution_policy: null\n")
        text = "\n".join(cfg.config_warnings(str(self.root)))
        self.assertIn("entry_gaurd", text)
        self.assertIn("entry_guard", text)          # 近似建议
        self.assertIn("scheduler.agnt", text)
        for ok in ("scheduler.exec", "pipelines", "custom_user", "execution_policy"):
            self.assertNotIn(ok + " 不在", text)


class ScanAccountingTests(RepoCase):
    def test_repeated_reads_of_same_path_are_charged_once_and_unknown_io_is_not_zero(self):
        """扫描计费透明：同路径重复读取去重计量；缓存命中不计费；外部工具 I/O 标 unknown 而非零。"""
        import test_ledger as ledger
        ctx = self.context()["context"]
        stages = {name: {} for name in policy.VALIDATION_STAGES}
        stages["pre_evidence"] = {"scanned_files": 10}
        progress = ledger._ValidationProgress(self.root, ctx, stages, "c" * 64, "static")
        observe = progress.observe("pre_evidence")
        observe({"content_reads": 1, "metadata_entries": 1, "cache_hits": 0}, {"a.py"})
        observe({"content_reads": 1, "metadata_entries": 1, "cache_hits": 0}, {"a.py"})
        observe({"content_reads": 0, "metadata_entries": 0, "cache_hits": 3}, set())
        observe({"content_reads": 2, "metadata_entries": 0, "cache_hits": 0}, {"a.py", "b.py"})
        summary = progress.summary()
        self.assertEqual(summary["evidence_content_reads"], 2)            # a.py 一次 + b.py 一次
        self.assertEqual(progress.observations["deduplicated_reads"], 2)
        self.assertEqual(summary["cache_hits"], 3)
        self.assertEqual(summary["external_tool_io"], "unknown")
        progress.finish("PASS")


if __name__ == "__main__":
    unittest.main()
