#!/usr/bin/env python3
"""显式执行策略：默认最小权限、同任务授权修订和真实证据。"""
import concurrent.futures
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
import entry_context as entry


def reserve_worker(root, context):
    import execution_policy as policy
    try:
        policy.reserve_budget(root, context, "processes", 1, "a" * 64)
        return "reserved"
    except policy.PolicyError as exc:
        return exc.status


def validation_worker(root, context):
    import execution_policy as policy
    stages = {stage: {} for stage in policy.VALIDATION_STAGES}
    stages["command"] = {"processes": 1}
    stages["pre_evidence"] = {"scanned_files": 1}
    stages["post_evidence"] = {"scanned_files": 1}
    try:
        ticket = policy.reserve_validation(root, context, stages, "a" * 64, action="static")
        return ticket
    except policy.PolicyError as exc:
        return exc.status


def bind_validation_worker(root, context, ticket, input_hash):
    import execution_policy as policy
    try:
        return policy.bind_validation_input(root, context, ticket, input_hash)['input_hash']
    except policy.PolicyError as exc:
        return exc.status


def settle_validation_worker(root, context, ticket):
    import execution_policy as policy
    return policy.settle_validation(root, context, ticket,
        {"pre_evidence": {"scanned_files": 2}, "command": {"processes": 1, "elapsed_seconds": .25}},
        evidence={"returncode": 0, "external_tool_io": "unknown"})


class ExecutionPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aidp-policy-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for args in (("init", "-q"), ("config", "user.name", "Policy Test"),
                     ("config", "user.email", "policy@example.test")):
            self.git(*args)
        (self.root / ".gitignore").write_text("memory/.aidp/\n")
        (self.root / "app.py").write_text("value = 1\n")
        self.git("add", ".")
        self.git("commit", "-qm", "initial")

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], check=True,
                              capture_output=True, text=True).stdout

    def resolve(self, **kwargs):
        return entry.resolve_context(self.root, kwargs.pop("entry", "sprint-dev"),
                                     version="V1", write_set=["app.py"], **kwargs)

    def source(self, text="跑相关测试", request_id="request-2"):
        return {"kind": "user-text", "request_id": request_id, "text": text}

    def resolve_static_only(self, **kwargs):
        kwargs.setdefault("authorization_source", {"kind": "user-text", "request_id": "explicit-static-only",
            "text": "本任务只实现并检查语法，明确跳过相关测试", "skip_actions": ["related-test"]})
        return self.resolve(**kwargs)

    def grant(self, result, actions, **kwargs):
        return entry.revise_context(self.root, result["execution_context"],
                                    additional_grants=actions, authorization_source=self.source(), **kwargs)

    def static(self, result, argv=None):
        return entry.run_static(self.root, result["execution_context"],
            argv or [sys.executable, "-B", "-c", "import ast; ast.parse(open('app.py').read())"],
            inputs=["app.py"])

    def test_natural_request_implements_static_and_related_tests_for_every_identity(self):
        for options in ({}, {"sprint": "007"}, {"entry": "sprint-full"}, {"entry": "sprint-bugfix"}):
            result = self.resolve(**options)
            self.assertEqual(result["context"].get("allowed_actions"), ["implement", "related-test", "static"])
            route = entry.route_context(self.root, result["execution_context"], "close")
            self.assertIn("related-test", route["actions"])
            self.assertNotIn("review", route["actions"])
            self.assertIn("full-regression", route["not_requested_actions"])

    def test_default_development_requires_real_related_tests(self):
        for command in (None, "sprint-dev", "sprint-bugfix"):
            with self.subTest(command=command):
                (self.root / "app.py").write_text("value = 1\n")
                source = ({"kind": "explicit-command", "request_id": "explicit-" + command,
                           "command": "/" + command} if command else self.source("修复 app.py 的值"))
                first = self.resolve(entry=command or "sprint-dev", authorization_source=source)
                (self.root / "app.py").write_text("value = 2\n")
                static = self.static(first)
                blocked = entry.complete_context(self.root, first["execution_context"], static_evidence=static["evidence_file"])
                self.assertFalse(blocked["completed"])
                self.assertEqual(blocked["checks"]["related-test"], "UNVERIFIED")
                related = self.run_related_test(first)
                done = entry.complete_context(self.root, first["execution_context"], static_evidence=static["evidence_file"], **related)
                self.assertTrue(done["completed"], done)
                self.assertTrue(done["development_completed"])
                self.assertEqual(done["quality_verdict"], "PASS")
                self.assertEqual(done["task_id"], first["task_id"])
                self.assertFalse((self.root / "memory/activeContext.md").exists())

    def test_explicit_restrictions_keep_original_source_and_never_claim_quality_pass(self):
        import execution_policy as policy
        for restriction in ("analysis-only", "modify-only", "skip-verification"):
            with self.subTest(restriction=restriction):
                source = dict(self.source("本轮用户明确限制 " + restriction), restriction=restriction)
                result = self.resolve(authorization_source=source)
                nested = entry.resolve_context(self.root, "bugfix", execution_context=result["execution_context"])
                self.assertEqual(result["identity_hash"], nested["identity_hash"])
                self.assertEqual(nested["context"]["authorization_source"][0]["text"], source["text"])
                done = entry.complete_context(self.root, result["execution_context"])
                self.assertTrue(done["completed"], done)
                self.assertEqual(done["status"], "LIMITED")
                self.assertFalse(done["development_completed"])
                self.assertFalse(done["ready_for_release"])
                if restriction == "analysis-only":
                    with self.assertRaises(policy.PolicyError):
                        policy.require_action(nested["context"], "implement")
                else:
                    policy.require_action(nested["context"], "implement")
        for source in ({"kind": "explicit-command", "request_id": "fake-exception", "command": "/sprint-dev",
                        "skip_actions": ["related-test"]}, dict(self.source(), skip_actions=["deploy"])):
            with self.assertRaises(policy.PolicyError):
                self.resolve(authorization_source=source)

    def test_full_regression_only_via_autopilot_fork_never_grant_or_text(self):
        import execution_policy as policy
        forged = self.source("对当前版本做全量测试", "ask-full")
        with self.assertRaises(policy.PolicyError) as denied:
            self.resolve(entry="sprint-aiauto-test", task_scope="test",
                         additional_grants=["full-regression"], authorization_source=forged)
        self.assertEqual(denied.exception.status, "UNAUTHORIZED")
        self.assertIn("autopilot", str(denied.exception))
        text_only = self.resolve(entry="sprint-aiauto-test", task_scope="test", authorization_source=forged)
        self.assertNotIn("full-regression", text_only["context"]["allowed_actions"])
        self.assertLessEqual(set(text_only["context"]["allowed_actions"]), {"static", "live-tests"})
        self.assertNotEqual(text_only["context"]["verification_level"], "full")
        explicit = self.resolve(entry="sprint-aiauto-test", task_scope="test", additional_grants=["live-tests"],
            authorization_source={"kind": "explicit-command", "command": "/sprint-aiauto-test", "request_id": "aiauto"})
        self.assertNotIn("full-regression", explicit["context"]["allowed_actions"])
        with self.assertRaises(policy.PolicyError):
            entry.revise_context(self.root, text_only["execution_context"], additional_grants=["full-regression"],
                                 authorization_source=self.source("再要全量", "ask-full-2"))
        manifest_path, _ = self.version_manifest()
        parent = self.resolve(entry="sprint-autopilot", authorization_source={"kind": "explicit-command",
            "command": "/sprint-autopilot", "request_id": "delegate", "options": ["--skip-dev"]})
        child = entry.fork_test_build(self.root, parent["execution_context"], "V1", "build-007", manifest=manifest_path)
        self.assertIn("full-regression", child["context"]["allowed_actions"])
        self.assertEqual(child["context"]["verification_level"], "full")
        policy.require_action(child["context"], "full-regression")

    def test_root_may_delegate_full_but_never_execute_it(self):
        import execution_policy as policy
        manifest_path, _ = self.version_manifest()
        root = self.resolve(entry="sprint-autopilot", authorization_source={"kind": "explicit-command",
            "command": "/sprint-autopilot", "request_id": "root-delegate", "options": ["--skip-dev"]})
        policy.require_delegable(root["context"], "full-regression")
        with self.assertRaises(policy.PolicyError):
            policy.require_action(root["context"], "full-regression")
        with self.assertRaises(policy.PolicyError):
            policy.require_delegable(root["context"], "deploy")
        standalone = self.resolve(entry="sprint-aiauto-test", task_scope="test", authorization_source={
            "kind": "explicit-command", "command": "/sprint-aiauto-test", "request_id": "solo"})
        text = self.resolve(entry="sprint-aiauto-test", task_scope="test", authorization_source=self.source("全量", "txt"))
        for ctx in (standalone, text):
            with self.assertRaises(policy.PolicyError):
                policy.require_delegable(ctx["context"], "full-regression")
        child = entry.fork_test_build(self.root, root["execution_context"], "V1", "build-007", manifest=manifest_path)
        policy.require_action(child["context"], "full-regression")

    def test_test_entry_is_readonly_kind_and_child_keeps_restriction(self):
        import execution_policy as policy
        standalone = self.resolve(entry="test")
        self.assertEqual(standalone["context"]["task_scope"]["kind"], "test")
        self.assertNotIn("implement", standalone["context"]["allowed_actions"])
        self.assertNotIn("full-regression", entry.route_context(self.root, standalone["execution_context"], "test")["actions"])
        parent = self.resolve(entry="sprint-batch", authorization_source=dict(
            self.source("只修改代码，不运行任何验证"), restriction="skip-verification"))
        child = entry.fork_context(self.root, parent["execution_context"], "001")
        self.assertEqual(child["context"]["allowed_actions"], ["implement"])
        with self.assertRaises(policy.PolicyError):
            policy.require_action(child["context"], "related-test")
        done = entry.check_completion(self.root, child["execution_context"])
        self.assertEqual(done["checks"]["related-test"], "SKIPPED_BY_REQUEST")
        self.assertFalse(done["development_completed"])

    def test_nested_test_entry_does_not_grant_or_change_identity(self):
        first = self.resolve()
        nested = entry.resolve_context(self.root, "sprint-test", execution_context=first["execution_context"])
        self.assertEqual(first["identity_hash"], nested["identity_hash"])
        self.assertEqual(nested["context"].get("allowed_actions"), ["implement", "related-test", "static"])
        with self.assertRaises(ValueError):
            entry.resolve_context(self.root, "sprint-test", execution_context=first["execution_context"],
                authorization_source={"kind": "explicit-command", "command": "/sprint-test", "request_id": "child"})

    def test_grant_preserves_task_and_start_and_invalidates_old_identity(self):
        first = self.resolve_static_only()
        revised = self.grant(first, ["related-test"])
        self.assertEqual(first["task_id"], revised["task_id"])
        self.assertEqual(first["since"], revised["since"])
        self.assertEqual(revised["revision"], 2)
        self.assertNotEqual(first["identity_hash"], revised["identity_hash"])
        self.assertIn("related-test", revised["context"]["allowed_actions"])
        self.assertNotIn("review", revised["context"]["allowed_actions"])
        import execution_policy as policy
        with self.assertRaises(ValueError):
            policy.require_action(first["context"], "static")
        policy.require_action(revised["context"], "related-test")

    def test_grants_require_real_source_and_legacy_template_is_not_a_choice(self):
        first = self.resolve()
        for source in (None, {"kind": "template"}, {"kind": "user-text", "text": "<user authorization>"},
                       {"kind": "project-policy", "user_selected": False}):
            with self.assertRaises(ValueError):
                entry.revise_context(self.root, first["execution_context"], additional_grants=["full-regression"],
                                     authorization_source=source)
        config = self.root / "memory/aidp-config.yaml"
        config.parent.mkdir(exist_ok=True)
        config.write_text("execution_policy:\n  allowed_actions: [full-regression, deploy]\n"
                          "cicd:\n  auto_trigger: true\nautopilot_decisions:\n  tests: auto\n")
        self.assertEqual(self.resolve()["context"]["allowed_actions"], ["implement", "related-test", "static"])

    def test_explicit_command_combination_and_browser_grant_stay_distinct(self):
        explicit = self.resolve(entry="sprint-aiauto-test", authorization_source={
            "kind": "explicit-command", "command": "/sprint-aiauto-test", "request_id": "request-1"})
        self.assertIn("live-tests", explicit["context"]["allowed_actions"])
        self.assertNotIn("full-regression", explicit["context"]["allowed_actions"])
        natural = self.resolve(additional_grants=["live-tests"], authorization_source=self.source("浏览器测试"))
        self.assertNotIn("full-regression", natural["context"]["allowed_actions"])

    def test_release_grants_do_not_imply_extra_verification(self):
        first = self.resolve_static_only()
        release = self.grant(first, ["commit", "push", "deploy"])
        self.assertEqual(set(release["context"]["allowed_actions"]),
                         {"implement", "static", "commit", "push", "deploy"})
        route = entry.route_context(self.root, release["execution_context"], "close")
        self.assertIn("migration-rehearsal", route["not_requested_actions"])
        static = self.static(release)
        gate = entry.check_completion(self.root, release["execution_context"], static_evidence=static["evidence_file"])
        self.assertEqual(gate["pending_actions"], ["commit", "push", "deploy"])

    def test_explicit_static_only_completes_limited_without_test_or_review(self):
        first = self.resolve_static_only()
        (self.root / "app.py").write_text("value = 2\n")
        static = self.static(first)
        self.assertEqual(static["status"], "PASS")
        result = entry.complete_context(self.root, first["execution_context"], static_evidence=static["evidence_file"])
        self.assertTrue(result["completed"], result)
        self.assertEqual(result["checks"]["related-test"], "SKIPPED_BY_REQUEST")
        self.assertEqual(result["status"], "LIMITED")
        self.assertFalse(result["development_completed"])
        self.assertFalse(result["ready_for_release"])
        self.assertEqual(result["checks"]["review"], "NOT_REQUESTED")
        self.assertFalse((self.root / "docs").exists())

    def test_readonly_static_failure_and_missing_tool_terminate_without_repair(self):
        for argv, expected in ((None, "FAIL"), (["aidp_missing_static_tool_fixture"], "UNVERIFIED")):
            with self.subTest(expected=expected):
                result = self.resolve(task_scope="test", authorization_source=self.source("只检查语法并报告，不修改代码"))
                (self.root / "app.py").write_text("def broken(:\n")
                before = (self.root / "app.py").read_bytes()
                static = self.static(result, argv)
                done = entry.complete_context(self.root, result["execution_context"], static_evidence=static["evidence_file"])
                self.assertTrue(done["completed"], done)
                self.assertTrue(done["action_completed"])
                self.assertEqual(done["quality_verdict"], expected)
                self.assertFalse(done["ready_for_release"])
                self.assertEqual((self.root / "app.py").read_bytes(), before)
                self.assertNotIn("implement", result["context"]["allowed_actions"])
                (self.root / "app.py").write_text("fixed_outside = True\n")
                stale = entry.check_completion(self.root, result["execution_context"], static_evidence=static["evidence_file"])
                self.assertFalse(stale["ready"])
        developer = self.resolve()
        (self.root / "app.py").write_text("def broken(:\n")
        static = self.static(developer)
        blocked = entry.complete_context(self.root, developer["execution_context"], static_evidence=static["evidence_file"])
        self.assertFalse(blocked["completed"])
        self.assertEqual(blocked["quality_verdict"], "FAIL")

    def test_readonly_review_completes_with_findings_without_granting_repairs(self):
        result = self.resolve(task_scope="review", additional_grants=["review"], authorization_source=self.source("只做代码审查"))
        report_path = Path(self.review_report(result))
        report = json.loads(report_path.read_text())
        report["status"] = "FAIL"
        report["checks"][0]["status"] = "FAIL"
        report["findings"] = [{"id": "R-1", "kind": "error", "severity": "important", "status": "open",
                               "evidence": ["app.py:1 缺少本用例要求的边界处理"]}]
        report_path.write_text(json.dumps(report))
        before = (self.root / "app.py").read_bytes()
        done = entry.complete_context(self.root, result["execution_context"], review_evidence=str(report_path))
        self.assertTrue(done["completed"], done)
        self.assertEqual(done["quality_status"], "FAIL")
        self.assertEqual(done["checks"]["review"], "FAIL")
        self.assertNotIn("implement", result["context"]["allowed_actions"])
        self.assertEqual((self.root / "app.py").read_bytes(), before)

    def test_accepted_pure_improvement_does_not_force_implementation(self):
        result = self.resolve(task_scope="review", additional_grants=["review"], authorization_source=self.source("只做代码审查"))
        report_path = Path(self.review_report(result))
        report = json.loads(report_path.read_text())
        report["findings"] = [{"id": "R-2", "kind": "improvement", "severity": "Minor", "status": "accepted",
                               "reason": "仅为可选命名改进，本任务不实施", "evidence": ["app.py:1 局部命名建议"]}]
        report_path.write_text(json.dumps(report))
        done = entry.complete_context(self.root, result["execution_context"], review_evidence=str(report_path))
        self.assertTrue(done["completed"], done)
        self.assertEqual(done["status"], "PASS")
        report["findings"][0]["kind"] = "error"
        report_path.write_text(json.dumps(report))
        blocked = entry.check_completion(self.root, result["execution_context"], review_evidence=str(report_path))
        self.assertFalse(blocked["ready"])

    def test_test_only_failed_run_ends_detection_without_implementation(self):
        import test_ledger as ledger
        from test_scope import derive
        (self.root / "tests").mkdir()
        (self.root / "tests/test_app.py").write_text("from pathlib import Path\nassert Path('app.py').read_text() == 'value = 999\\n'\n")
        result = self.resolve(task_scope="test", additional_grants=["related-test"], authorization_source=self.source("只运行相关测试，不修改代码"))
        (self.root / "app.py").write_text("value = 2\n")
        plan = derive(self.root, None, [{"cwd": ".", "suffixes": [".py"], "argv": [sys.executable, "-B", "{tests}"]}],
                      execution_context=result["execution_context"])
        scope = Path(result["execution_context"]).with_name("scope.json")
        scope.write_text(json.dumps(plan))
        runs, code = ledger.run_scope(self.root, str(scope), "policy-env", execution_context=result["context"])
        self.assertNotEqual(code, 0)
        static = self.static(result)
        done = entry.complete_context(self.root, result["execution_context"], static_evidence=static["evidence_file"],
            scope_file=str(scope), scope_hash=plan["scope_hash"], run_ids=runs["run_ids"], env_id="policy-env")
        self.assertTrue(done["completed"], done)
        self.assertTrue(done["action_completed"])
        self.assertEqual(done["quality_verdict"], "FAIL")
        self.assertEqual(done["verification"]["original_runs"][0]["status"], "FAIL")
        self.assertNotIn("implement", result["context"]["allowed_actions"])
        self.assertEqual((self.root / "app.py").read_text(), "value = 2\n")
        self.assertEqual(len([row for row in ledger.load(self.root) if row["kind"] == "run"]), 1)

    def test_development_failure_still_blocks_quality_completion(self):
        import test_ledger as ledger
        from test_scope import derive
        (self.root / "tests").mkdir()
        (self.root / "tests/test_app.py").write_text("from pathlib import Path\nassert Path('app.py').read_text() == 'value = 999\\n'\n")
        result = self.resolve(additional_grants=["related-test"], authorization_source=self.source("开发并运行相关测试"))
        (self.root / "app.py").write_text("value = 2\n")
        plan = derive(self.root, None, [{"cwd": ".", "suffixes": [".py"], "argv": [sys.executable, "-B", "{tests}"]}],
                      execution_context=result["execution_context"])
        scope = Path(result["execution_context"]).with_name("scope.json")
        scope.write_text(json.dumps(plan))
        runs, _ = ledger.run_scope(self.root, str(scope), "policy-env", execution_context=result["context"])
        static = self.static(result)
        done = entry.complete_context(self.root, result["execution_context"], static_evidence=static["evidence_file"],
            scope_file=str(scope), scope_hash=plan["scope_hash"], run_ids=runs["run_ids"], env_id="policy-env")
        self.assertFalse(done["completed"], done)
        self.assertEqual(done["quality_verdict"], "FAIL")

    def test_test_only_missing_runner_terminates_unverified_without_installing(self):
        import test_ledger as ledger
        from test_scope import derive
        (self.root / "tests").mkdir()
        (self.root / "tests/test_app.py").write_text("assert True\n")
        result = self.resolve(task_scope="test", additional_grants=["related-test"], authorization_source=self.source("只运行相关测试"))
        (self.root / "app.py").write_text("value = 2\n")
        plan = derive(self.root, None, [{"cwd": ".", "suffixes": [".py"],
            "argv": [sys.executable, "-B", "-m", "aidp_missing_test_runner_fixture", "{tests}"]}], execution_context=result["execution_context"])
        scope = Path(result["execution_context"]).with_name("scope.json")
        scope.write_text(json.dumps(plan))
        runs, code = ledger.run_scope(self.root, str(scope), "policy-env", execution_context=result["context"])
        self.assertNotEqual(code, 0)
        static = self.static(result)
        done = entry.complete_context(self.root, result["execution_context"], static_evidence=static["evidence_file"],
            scope_file=str(scope), scope_hash=plan["scope_hash"], run_ids=runs["run_ids"], env_id="policy-env")
        self.assertTrue(done["completed"], done)
        self.assertEqual(done["quality_verdict"], "UNVERIFIED")
        self.assertEqual(done["action_status"], "TERMINATED")
        self.assertFalse(done["ready_for_release"])
        self.assertEqual(done["verification"]["original_runs"][0]["failure_kind"], "ENV_UNAVAILABLE")

    def run_related_test(self, result):
        import test_ledger as ledger
        from test_scope import derive
        (self.root / "tests").mkdir(exist_ok=True)
        (self.root / "tests/test_app.py").write_text("import runpy\nassert runpy.run_path('app.py')['value'] == 2\n")
        plan = derive(self.root, None, [{"cwd": ".", "suffixes": [".py"],
            "argv": [sys.executable, "-B", "{tests}"]}], execution_context=result["execution_context"])
        scope = Path(result["execution_context"]).with_name("scope.json")
        scope.write_text(json.dumps(plan))
        runs, code = ledger.run_scope(self.root, str(scope), "policy-env", execution_context=result["context"])
        self.assertEqual(code, 0, runs)
        return {"scope_file": str(scope), "scope_hash": plan["scope_hash"],
                "run_ids": runs["run_ids"], "env_id": "policy-env"}

    def test_commit_grant_is_release_readiness_not_completed_execution(self):
        result = self.resolve(additional_grants=["commit"], authorization_source=self.source("完成后提交"))
        (self.root / "app.py").write_text("value = 2\n")
        related = self.run_related_test(result)
        static = self.static(result)
        ready = entry.check_completion(self.root, result["execution_context"], static_evidence=static["evidence_file"], **related)
        self.assertTrue(ready["ready_for_release"], ready)
        pending = entry.complete_context(self.root, result["execution_context"], static_evidence=static["evidence_file"], **related)
        self.assertFalse(pending["completed"], pending)
        self.assertEqual(pending["status"], "PENDING_ACTIONS")
        self.assertEqual(pending["pending_actions"], ["commit"])
        self.git("add", "app.py")
        output = self.git("commit", "-m", "fixture authorized change")
        receipt = Path(result["execution_context"]).with_name("commit.json")
        receipt.write_text(json.dumps({"action": "commit", "status": "PASS", "execution_context": result["identity"],
            "inputs": {"app.py": entry.initial_file_hash(self.root / "app.py")},
            "argv": ["git", "commit", "-m", "fixture authorized change"],
            "result": {"returncode": 0, "stdout": output, "stderr": ""},
            "checks": [{"kind": "tool-receipt", "status": "PASS", "evidence": [self.git("rev-parse", "HEAD").strip()]}]}))
        done = entry.complete_context(self.root, result["execution_context"], static_evidence=static["evidence_file"],
                                     action_evidence={"commit": str(receipt)}, **related)
        self.assertTrue(done["completed"], done)
        self.assertEqual(done["checks"]["commit"], "PASS")

    def test_self_declared_pass_stale_code_and_missing_tools_never_fake_pass(self):
        first = self.resolve()
        fake = Path(first["execution_context"]).with_name("fake.json")
        fake.write_text(json.dumps({"status": "PASS", "task_id": first["task_id"]}))
        result = entry.check_completion(self.root, first["execution_context"], static_evidence=str(fake))
        self.assertFalse(result["ready"])
        static = self.static(first)
        (self.root / "app.py").write_text("value = 3\n")
        result = entry.check_completion(self.root, first["execution_context"], static_evidence=static["evidence_file"])
        self.assertFalse(result["ready"])
        missing = self.static(first, ["aidp-nonexistent-static-tool"])
        self.assertEqual(missing["status"], "ENV_UNAVAILABLE")
        result = entry.check_completion(self.root, first["execution_context"], static_evidence=missing["evidence_file"])
        self.assertEqual(result["status"], "UNVERIFIED")
        self.assertFalse(result["ready"])

    def test_optional_pending_authorization_does_not_block_static_completion(self):
        first = self.resolve_static_only()
        static = self.static(first)
        result = entry.complete_context(self.root, first["execution_context"],
            static_evidence=static["evidence_file"], pending_authorizations=["deploy"])
        self.assertTrue(result["completed"], result)

    def test_cli_settle_elapsed_returns_unused_reservation_without_resetting_usage(self):
        import time
        result = self.resolve(entry="sprint-autopilot", authorization_source={"kind": "explicit-command",
            "request_id": "tool-budget", "command": "/sprint-autopilot"})
        def cli(command, *args, context=None, expected=0):
            process = subprocess.run([sys.executable, str(SCRIPTS / "execution_policy.py"), command,
                "--root", str(self.root), "--execution-context", (context or result)["execution_context"], *args],
                capture_output=True, text=True)
            self.assertEqual(process.returncode, expected, process.stdout + process.stderr)
            return json.loads(process.stdout)
        command = [sys.executable, "-B", "-c", "import ast; ast.parse(open('app.py').read())"]
        input_hash = entry._digest({"argv": command, "app.py": entry.initial_file_hash(self.root / "app.py")})
        ticket = cli("reserve-budget", "--resource", "elapsed_seconds", "--cost", "7200", "--action", "static", "--input-hash", input_hash)
        started = time.monotonic()
        actual = subprocess.run(command, cwd=self.root, capture_output=True, text=True)
        elapsed = time.monotonic() - started
        self.assertEqual(actual.returncode, 0)
        cli("record-outcome", "--action", "static", "--status", "PASS", "--input-hash", input_hash,
            "--evidence-json", json.dumps({"returncode": actual.returncode, "stdout": actual.stdout,
                                          "stderr": actual.stderr, "elapsed_seconds": elapsed}))
        cli("reserve-budget", "--resource", "elapsed_seconds", "--cost", "1", "--input-hash", input_hash, expected=2)
        settled = cli("settle-elapsed", "--reservation-id", ticket["reservation_id"], "--elapsed-seconds", str(elapsed))
        self.assertEqual(settled["status"], "SETTLED")
        self.assertAlmostEqual(settled["actual_cost"], elapsed)
        reserved = cli("reserve-budget", "--resource", "elapsed_seconds", "--cost", "1", "--input-hash", input_hash)
        self.assertAlmostEqual(reserved["used"], elapsed + 1)
        cli("settle-elapsed", "--reservation-id", ticket["reservation_id"], "--elapsed-seconds", str(elapsed))
        for value in (str(elapsed + 1), "-1", "nan"):
            cli("settle-elapsed", "--reservation-id", ticket["reservation_id"], "--elapsed-seconds", value, expected=2)
        other = self.resolve()
        cli("settle-elapsed", "--reservation-id", ticket["reservation_id"], "--elapsed-seconds", str(elapsed), context=other, expected=2)
        state = json.loads(Path(result["execution_context"]).with_name("budget.json").read_text())
        self.assertAlmostEqual(state["used"]["elapsed_seconds"], elapsed + 1)
        self.assertNotIn("actual_cost", next(row for row in state["reservations"] if row["reservation_id"] == reserved["reservation_id"]))

    def test_budget_is_atomic_across_processes(self):
        first = self.resolve(execution_budget={"processes": 3})
        with concurrent.futures.ProcessPoolExecutor(max_workers=6) as pool:
            statuses = list(pool.map(reserve_worker, [str(self.root)] * 12, [first["execution_context"]] * 12))
        self.assertEqual(statuses.count("reserved"), 3, statuses)
        self.assertEqual(statuses.count("BUDGET_EXCEEDED"), 9, statuses)

    def validation_stages(self, scans=2, processes=1):
        return {"pre_evidence": {"scanned_files": scans},
                "command": {"processes": processes, "elapsed_seconds": 10},
                "post_evidence": {"scanned_files": scans}, "cleanup": {"scanned_files": 1}}

    def budget_state(self, result):
        return json.loads(Path(result["execution_context"]).with_name("budget.json").read_text())

    def test_validation_rejects_all_resources_atomically_with_complete_diagnostic(self):
        import execution_policy as policy
        first = self.resolve(execution_budget={"scanned_files": 5, "processes": 0})
        before = self.budget_state(first)
        with self.assertRaises(policy.PolicyError) as denied:
            policy.reserve_validation(self.root, first["context"], self.validation_stages(), "a" * 64, action="static")
        self.assertEqual(denied.exception.status, "BUDGET_EXCEEDED")
        details = denied.exception.details
        self.assertEqual(details["expected"]["scanned_files"], 5)
        self.assertEqual(details["shortfall"]["processes"], 1)
        self.assertEqual(details["stages"]["post_evidence"]["scanned_files"], 2)
        self.assertIn("basis", details["recommendation"])
        self.assertEqual(before, self.budget_state(first))

    def test_validation_real_process_concurrency_shares_root_and_rejects_without_charge(self):
        import execution_policy as policy
        parent = self.resolve(entry="sprint-batch", execution_budget={"processes": 3})
        child = entry.fork_context(self.root, parent["execution_context"], "001")
        before = self.budget_state(parent)["used"]
        with concurrent.futures.ProcessPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(validation_worker, [str(self.root)] * 12,
                                    [parent["execution_context"], child["execution_context"]] * 6))
        tickets = [row for row in results if isinstance(row, dict)]
        self.assertEqual(len(tickets), 3, results)
        self.assertEqual(results.count("BUDGET_EXCEEDED"), 9, results)
        state = self.budget_state(parent)
        self.assertEqual(state["used"]["processes"], 3)
        self.assertEqual(state["used"]["scanned_files"], before["scanned_files"] + 6)
        with self.assertRaises(policy.PolicyError):
            policy.reserve_budget(self.root, child["context"], "processes", 1)

    def test_validation_cancel_retains_recorded_reads_and_only_refunds_unused(self):
        import execution_policy as policy
        first = self.resolve()
        initial = self.budget_state(first)["used"]
        ticket = policy.reserve_validation(self.root, first["context"], self.validation_stages(), "a" * 64, action="static")
        actual = {"pre_evidence": {"scanned_files": 2}}
        policy.record_validation_usage(self.root, first["context"], ticket, actual,
            observations={"unique_files": 1, "metadata_entries": 9, "cache_hits": 3})
        cancelled = policy.cancel_validation(self.root, first["context"], ticket, root_cause="cancel before command")
        self.assertEqual(cancelled["status"], "UNVERIFIED")
        state = self.budget_state(first)
        self.assertEqual(state["used"]["scanned_files"], initial["scanned_files"] + 2)
        self.assertEqual(state["used"]["processes"], 0)
        self.assertEqual(state["used"]["elapsed_seconds"], 0)
        self.assertEqual(cancelled["observations"]["unique_files"], 1)
        self.assertEqual(policy.cancel_validation(self.root, first["context"], ticket,
                          root_cause="cancel before command"), cancelled)
        self.assertEqual(len(state["outcomes"]), 1)
        with self.assertRaises(policy.PolicyError):
            policy.settle_validation(self.root, first["context"], ticket, actual, status="PASS")
        with self.assertRaises(policy.PolicyError):
            policy.record_validation_usage(self.root, first["context"], ticket, {})

    def test_validation_unused_cancel_refunds_every_resource_and_rejects_foreign_task(self):
        import execution_policy as policy
        parent = self.resolve(entry="sprint-batch")
        child = entry.fork_context(self.root, parent["execution_context"], "001")
        before = self.budget_state(parent)["used"]
        ticket = policy.reserve_validation(self.root, parent["context"], self.validation_stages(), "a" * 64, action="static")
        with self.assertRaises(policy.PolicyError):
            policy.cancel_validation(self.root, child["context"], ticket)
        policy.cancel_validation(self.root, parent["context"], ticket)
        self.assertEqual(self.budget_state(parent)["used"], before)
        with self.assertRaises(policy.PolicyError):
            policy.settle_elapsed(self.root, parent["context"], ticket, 0)

    def test_validation_partial_execution_records_original_failure_and_elapsed(self):
        import execution_policy as policy
        first = self.resolve()
        before = self.budget_state(first)["used"]
        ticket = policy.reserve_validation(self.root, first["context"], self.validation_stages(), "a" * 64, action="static")
        actual = {"pre_evidence": {"scanned_files": 2},
                  "command": {"processes": 1, "elapsed_seconds": .125},
                  "post_evidence": {"scanned_files": 1}}
        result = policy.settle_validation(self.root, first["context"], ticket, actual,
            root_cause="post evidence interrupted", evidence={"returncode": 0, "stderr": "original output"})
        self.assertEqual(result["status"], "UNVERIFIED")
        state = self.budget_state(first)
        self.assertEqual(state["used"]["scanned_files"], before["scanned_files"] + 3)
        self.assertEqual(state["used"]["processes"], 1)
        self.assertEqual(state["used"]["elapsed_seconds"], .125)
        self.assertEqual(state["outcomes"][-1]["evidence"]["returncode"], 0)
        self.assertEqual(policy.settle_validation(self.root, first["context"], ticket, actual,
            root_cause="post evidence interrupted", evidence={"returncode": 0, "stderr": "original output"}), result)
        self.assertEqual(state, self.budget_state(first))
        with self.assertRaises(policy.PolicyError):
            policy.settle_validation(self.root, first["context"], ticket, actual, root_cause="changed")

    def test_validation_deferred_input_binds_real_content_without_changing_cost(self):
        import execution_policy as policy
        first = self.resolve()
        ticket = policy.reserve_validation(self.root, first['context'], self.validation_stages(),
                                           'a' * 64, action='static', defer_input=True)
        self.assertIsNone(ticket['input_hash'])
        self.assertFalse(ticket['input_bound'])
        actual = {'pre_evidence': {'scanned_files': 2}}
        policy.record_validation_usage(self.root, first['context'], ticket, actual)
        before = self.budget_state(first)['used']
        bound = policy.bind_validation_input(self.root, first['context'], ticket, 'b' * 64)
        self.assertEqual(bound['input_hash'], 'b' * 64)
        self.assertTrue(bound['input_bound'])
        self.assertEqual(self.budget_state(first)['used'], before)
        self.assertEqual(policy.bind_validation_input(self.root, first['context'], ticket, 'b' * 64), bound)
        with self.assertRaises(policy.PolicyError):
            policy.bind_validation_input(self.root, first['context'], ticket, 'c' * 64)
        actual['command'] = {'processes': 1, 'elapsed_seconds': .2}
        result = policy.settle_validation(self.root, first['context'], ticket, actual, status='PASS')
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(self.budget_state(first)['outcomes'][-1]['input_hash'], 'b' * 64)

    def test_validation_binding_concurrency_accepts_only_one_actual_input(self):
        import execution_policy as policy
        first = self.resolve()
        ticket = policy.reserve_validation(self.root, first['context'], self.validation_stages(),
                                           'a' * 64, action='static', defer_input=True)
        before = self.budget_state(first)['used']
        with concurrent.futures.ProcessPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(bind_validation_worker, [str(self.root)] * 12,
                [first['execution_context']] * 12, [ticket] * 12, ['b' * 64, 'c' * 64] * 6))
        accepted = {value for value in results if value != 'UNVERIFIED'}
        self.assertEqual(len(accepted), 1)
        self.assertEqual(results.count('UNVERIFIED'), 6)
        self.assertEqual(self.budget_state(first)['used'], before)

    def test_validation_pending_input_rejects_pass_but_preserves_pre_reads_on_cancel(self):
        import execution_policy as policy
        first = self.resolve(entry='sprint-batch')
        child = entry.fork_context(self.root, first['execution_context'], '001')
        ticket = policy.reserve_validation(self.root, first['context'], self.validation_stages(),
                                           'a' * 64, action='static', defer_input=True)
        for operation in (
            lambda: policy.bind_validation_input(self.root, child['context'], ticket, 'b' * 64),
            lambda: policy.settle_validation(self.root, first['context'], ticket, {}, status='PASS')):
            with self.assertRaises(policy.PolicyError):
                operation()
        initial = self.budget_state(first)['used']['scanned_files'] - ticket['costs']['scanned_files']
        policy.record_validation_usage(self.root, first['context'], ticket, {'pre_evidence': {'scanned_files': 2}})
        cancelled = policy.cancel_validation(self.root, first['context'], ticket, root_cause='pre-evidence interrupted')
        self.assertEqual(cancelled['status'], 'UNVERIFIED')
        self.assertEqual(self.budget_state(first)['used']['scanned_files'], initial + 2)
        self.assertIsNone(self.budget_state(first)['outcomes'][-1]['input_hash'])
        with self.assertRaises(policy.PolicyError):
            policy.bind_validation_input(self.root, first['context'], ticket, 'b' * 64)

    def test_validation_unbound_real_execution_is_accounted_as_unverified(self):
        import execution_policy as policy
        first = self.resolve()
        ticket = policy.reserve_validation(self.root, first['context'], self.validation_stages(),
                                           'a' * 64, action='static', defer_input=True)
        actual = {'command': {'processes': 1, 'elapsed_seconds': .25}}
        with self.assertRaises(policy.PolicyError) as recorded:
            policy.record_validation_usage(self.root, first['context'], ticket, actual)
        self.assertEqual(recorded.exception.status, 'UNVERIFIED')
        self.assertTrue(recorded.exception.details['reservation']['unbound_execution'])
        with self.assertRaises(policy.PolicyError):
            policy.bind_validation_input(self.root, first['context'], ticket, 'b' * 64)
        with self.assertRaises(policy.PolicyError):
            policy.settle_validation(self.root, first['context'], ticket, actual, status='PASS', evidence={'returncode': 0})
        state = self.budget_state(first)
        self.assertEqual(state['used']['processes'], 1)
        self.assertEqual(state['used']['elapsed_seconds'], .25)
        self.assertEqual(state['outcomes'][-1]['status'], 'UNVERIFIED')
        self.assertEqual(state['outcomes'][-1]['evidence']['returncode'], 0)

    def test_validation_deferred_negative_cache_checks_actual_not_plan_hash(self):
        import execution_policy as policy
        first = self.resolve()
        policy.record_outcome(self.root, first['context'], 'static', 'TOOL_ERROR', 'a' * 64,
                              root_cause='previous actual input failed')
        ticket = policy.reserve_validation(self.root, first['context'], self.validation_stages(),
                                           'a' * 64, action='static', defer_input=True)
        before = self.budget_state(first)
        with self.assertRaises(policy.PolicyError) as denied:
            policy.bind_validation_input(self.root, first['context'], ticket, 'a' * 64)
        self.assertEqual(denied.exception.status, 'TOOL_ERROR')
        self.assertEqual(self.budget_state(first), before)
        policy.bind_validation_input(self.root, first['context'], ticket, 'b' * 64)
        policy.cancel_validation(self.root, first['context'], ticket)

    def test_validation_cleanup_failure_preserves_successful_delivery_receipt(self):
        import execution_policy as policy
        first = self.resolve(additional_grants=["deploy"], authorization_source=self.source("部署后核验回执"))
        before = self.budget_state(first)["used"]
        ticket = policy.reserve_validation(self.root, first["context"], self.validation_stages(), "a" * 64, action="deploy")
        actual = {"command": {"processes": 1, "elapsed_seconds": .5}, "cleanup": {"scanned_files": 1}}
        evidence = {"delivery": {"status": "PASS", "returncode": 0, "receipt": "release-42"},
                    "cleanup": {"status": "UNVERIFIED", "error": "receipt index unavailable"},
                    "external_tool_io": "unknown"}
        result = policy.settle_validation(self.root, first["context"], ticket, actual,
            root_cause="machine final verification failed", evidence=evidence)
        self.assertEqual(result["status"], "UNVERIFIED")
        state = self.budget_state(first)
        self.assertEqual(state["outcomes"][-1]["evidence"], evidence)
        self.assertEqual(state["used"]["scanned_files"], before["scanned_files"] + 1)
        self.assertEqual(state["used"]["processes"], before["processes"] + 1)
        self.assertEqual(state["used"]["elapsed_seconds"], before["elapsed_seconds"] + .5)
        replay = policy.settle_validation(self.root, first["context"], ticket, actual,
            root_cause="machine final verification failed", evidence=evidence)
        self.assertEqual(result, replay)
        self.assertEqual(state, self.budget_state(first))

    def test_validation_explicit_budget_revision_keeps_usage_and_applies_current_limit(self):
        import execution_policy as policy
        first = self.resolve(execution_budget={'elapsed_seconds': 10})
        ticket = policy.reserve_validation(self.root, first['context'], self.validation_stages(), 'a' * 64, action='static')
        revised = entry.revise_context(self.root, first['execution_context'], execution_budget={'elapsed_seconds': 20},
            authorization_source=self.source('增加本任务时间预算到20秒'))
        actual = {'command': {'processes': 1, 'elapsed_seconds': 12}}
        result = policy.settle_validation(self.root, revised['context'], ticket, actual, status='PASS')
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(self.budget_state(first)['used']['elapsed_seconds'], 12)
        self.assertEqual(policy.reserve_budget(self.root, revised['context'], 'elapsed_seconds', 8)['remaining'], 0)

    def test_validation_overrun_is_recorded_before_error_and_cannot_be_refunded(self):
        import execution_policy as policy
        first = self.resolve(execution_budget={"processes": 1, "elapsed_seconds": 10})
        ticket = policy.reserve_validation(self.root, first["context"], self.validation_stages(), "a" * 64, action="static")
        actual = {"command": {"processes": 2, "elapsed_seconds": 12}}
        with self.assertRaises(policy.PolicyError) as overrun:
            policy.record_validation_usage(self.root, first["context"], ticket, actual)
        self.assertEqual(overrun.exception.status, "BUDGET_EXCEEDED")
        self.assertEqual(self.budget_state(first)["used"]["processes"], 2)
        with self.assertRaises(policy.PolicyError):
            policy.cancel_validation(self.root, first["context"], ticket, {"command": {"processes": 1}})
        with self.assertRaises(policy.PolicyError) as settled:
            policy.settle_validation(self.root, first["context"], ticket, actual, status="PASS", evidence={"returncode": 0})
        self.assertEqual(settled.exception.status, "BUDGET_EXCEEDED")
        state = self.budget_state(first)
        self.assertEqual(state["used"]["elapsed_seconds"], 12)
        self.assertEqual(state["outcomes"][-1]["status"], "UNVERIFIED")
        self.assertEqual(state["outcomes"][-1]["evidence"]["returncode"], 0)
        with self.assertRaises(policy.PolicyError):
            policy.settle_validation(self.root, first["context"], ticket, actual, status="PASS", evidence={"returncode": 0})
        self.assertEqual(state, self.budget_state(first))

    def test_validation_concurrent_settlement_is_idempotent_and_resume_keeps_used(self):
        import execution_policy as policy
        first = entry.resolve_autopilot_root(self.root, "V1", authorization_source={"kind": "explicit-command",
            "command": "/sprint-autopilot", "request_id": "one-loop", "options": ["--once"]})
        policy.reserve_budget(self.root, first["context"], "scanned_files", 854)
        before = self.budget_state(first)["used"]["scanned_files"]
        ticket = policy.reserve_validation(self.root, first["context"], self.validation_stages(), "a" * 64, action="static")
        with concurrent.futures.ProcessPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(settle_validation_worker, [str(self.root)] * 12,
                                    [first["execution_context"]] * 12, [ticket] * 12))
        self.assertTrue(all(row == results[0] for row in results))
        state = self.budget_state(first)
        self.assertEqual(state["used"]["scanned_files"], before + 2)
        self.assertEqual(state["used"]["processes"], 1)
        self.assertEqual(len(state["outcomes"]), 1)
        resumed = entry.resolve_autopilot_root(self.root, "V1", execution_context=first["execution_context"])
        self.assertEqual(first["task_id"], resumed["task_id"])
        self.assertEqual(state, self.budget_state(resumed))
        self.assertEqual(policy.reserve_budget(self.root, resumed["context"], "processes", 1)["used"], 2)

    def test_validation_progress_replay_and_invalid_values_do_not_change_usage(self):
        import execution_policy as policy
        first = self.resolve()
        ticket = policy.reserve_validation(self.root, first["context"], self.validation_stages(), "a" * 64, action="static")
        actual = {"pre_evidence": {"scanned_files": 2}}
        observations = {"unique_files": 1, "metadata_entries": 10, "cache_hits": 3, "tool_objects": 29}
        policy.record_validation_usage(self.root, first["context"], ticket, actual, observations=observations)
        before = self.budget_state(first)
        policy.record_validation_usage(self.root, first["context"], ticket, actual, observations=observations)
        self.assertEqual(before, self.budget_state(first))
        for bad in (True, -1, float("nan"), 1.5):
            with self.assertRaises(policy.PolicyError):
                policy.record_validation_usage(self.root, first["context"], ticket, {"pre_evidence": {"scanned_files": bad}})
        with self.assertRaises(policy.PolicyError):
            policy.record_validation_usage(self.root, first["context"], ticket, {}, observations=observations)
        with self.assertRaises(policy.PolicyError):
            policy.record_validation_usage(self.root, first["context"], ticket, actual, observations={"unique_files": 0})
        self.assertEqual(before, self.budget_state(first))
        cancelled = policy.cancel_validation(self.root, first["context"], ticket)
        self.assertEqual(cancelled["held"]["scanned_files"], 2)
        self.assertEqual(cancelled["observations"]["unique_files"], 1)
        self.assertEqual(cancelled["observations"]["tool_objects"], 29)

    def test_validation_reservation_respects_actions_retry_and_complete_stages(self):
        import execution_policy as policy
        first = self.resolve()
        for stages, action in ((self.validation_stages(), "full-regression"), ({"command": {}}, "static")):
            before = self.budget_state(first)
            with self.assertRaises(policy.PolicyError):
                policy.reserve_validation(self.root, first["context"], stages, "a" * 64, action=action)
            self.assertEqual(before, self.budget_state(first))
        ticket = policy.reserve_validation(self.root, first["context"], self.validation_stages(), "a" * 64, action="static")
        policy.settle_validation(self.root, first["context"], ticket, {"command": {"processes": 1}},
                                 status="TOOL_ERROR", root_cause="bad option")
        before = self.budget_state(first)
        with self.assertRaises(policy.PolicyError) as failure:
            policy.reserve_validation(self.root, first["context"], self.validation_stages(), "a" * 64, action="static")
        self.assertEqual(failure.exception.status, "TOOL_ERROR")
        self.assertEqual(before, self.budget_state(first))
        policy.reserve_validation(self.root, first["context"], self.validation_stages(), "b" * 64, action="static")

    def test_failure_retry_is_blocked_for_same_inputs_but_fixed_inputs_can_run(self):
        import execution_policy as policy
        first = self.resolve()
        policy.record_outcome(self.root, first["context"], "static", "TOOL_ERROR", "a" * 64,
                              root_cause="invalid-tool-option", evidence={"stderr": "unknown option"})
        with self.assertRaises(policy.PolicyError) as denied:
            policy.reserve_budget(self.root, first["context"], "processes", 1, "a" * 64, action="static")
        self.assertEqual(denied.exception.status, "TOOL_ERROR")
        policy.reserve_budget(self.root, first["context"], "processes", 1, "b" * 64, action="static")
        policy.record_outcome(self.root, first["context"], "static", "FAIL", "b" * 64,
                              root_cause="syntax", evidence={"returncode": 1})
        policy.reserve_budget(self.root, first["context"], "processes", 1, "c" * 64, action="static")

    def test_release_or_review_grant_keeps_existing_code_evidence(self):
        first = self.resolve_static_only()
        static = self.static(first)
        revised = self.grant(first, ["commit", "push", "deploy"])
        self.assertEqual(entry.evidence_identity(first["context"]), entry.evidence_identity(revised["context"]))
        self.assertTrue(entry.check_completion(self.root, revised["execution_context"],
                                              static_evidence=static["evidence_file"])["ready"])
        review = entry.revise_context(self.root, revised["execution_context"], additional_grants=["review"],
                                     authorization_source=self.source("只做代码审查", "request-3"))
        self.assertEqual(entry.evidence_identity(first["context"]), entry.evidence_identity(review["context"]))
        self.assertEqual(entry.load_context(self.root, review["execution_context"])["scope_revision"], 1)

    def test_review_only_does_not_authorize_implementation_or_require_static(self):
        result = self.resolve(task_scope="review", additional_grants=["review"],
                              authorization_source=self.source("只做代码审查"))
        self.assertEqual(result["context"]["allowed_actions"], ["review"])
        report = Path(result["execution_context"]).with_name("review.json")
        report.write_text(json.dumps({"schema": 1, "action": "review", "status": "PASS",
            "execution_context": entry.evidence_identity(result["context"]),
            "inputs": {"app.py": entry.initial_file_hash(self.root / "app.py")},
            "checks": [{"kind": "code-review", "status": "PASS", "evidence": ["app.py:1 constant assignment checked"]}],
            "findings": []}))
        done = entry.complete_context(self.root, result["execution_context"], review_evidence=str(report))
        self.assertTrue(done["completed"], done)
        self.assertEqual(done["checks"]["static"], "NOT_REQUESTED")
        self.assertEqual(done["checks"]["related-test"], "NOT_REQUESTED")

    def test_legacy_context_migrates_without_replaying_template_permissions(self):
        import execution_policy as policy
        first = self.resolve()
        legacy = dict(first["context"])
        for field in (*policy.POLICY_FIELDS, "scope_revision", "authorization_revision"):
            legacy.pop(field)
        identity = {name: legacy[name] for name in entry.IDENTITY_FIELDS if name in legacy}
        identity["initial_files_hash"] = entry._digest(legacy["initial_files"])
        identity["initial_gitlinks_hash"] = entry._digest(legacy["initial_gitlinks"])
        legacy["identity_hash"] = entry._digest(identity)
        legacy["checksum"] = entry._digest({key: value for key, value in legacy.items() if key != "checksum"})
        Path(first["execution_context"]).write_text(json.dumps(legacy))
        migrated = entry.load_context(self.root, first["execution_context"])
        self.assertEqual(migrated["task_id"], first["task_id"])
        self.assertEqual(migrated["since"], first["since"])
        self.assertEqual(migrated["allowed_actions"], ["implement", "static"])
        self.assertEqual(migrated["authorization_source"], [])

    def test_explicit_project_choice_is_read_but_default_config_is_not_grant(self):
        config = self.root / "memory/aidp-config.yaml"
        config.parent.mkdir(exist_ok=True)
        config.write_text("execution_policy:\n  allowed_actions: [review]\n  authorization_source:\n"
            "    kind: project-policy\n    user_selected: true\n    request_id: choice-1\n    text: 以后执行代码审查\n")
        result = self.resolve()
        self.assertIn("review", result["context"]["allowed_actions"])
        self.assertIn("related-test", result["context"]["allowed_actions"])

    def test_grant_replay_is_idempotent_and_budget_usage_survives_revision(self):
        import execution_policy as policy
        first = self.resolve(execution_budget={"processes": 1})
        policy.reserve_budget(self.root, first["context"], "processes", 1, "a" * 64)
        revised = self.grant(first, ["push"])
        repeated = self.grant(revised, ["push"])
        self.assertEqual(revised["identity_hash"], repeated["identity_hash"])
        with self.assertRaises(policy.PolicyError):
            policy.reserve_budget(self.root, repeated["context"], "processes", 1, "b" * 64)

    def test_every_budget_resource_is_enforced_and_elapsed_settles_actual_work(self):
        import execution_policy as policy
        first = self.resolve(execution_budget={**{key: 1 for key in policy.DEFAULT_BUDGET}, "scanned_files": 2})
        for resource in policy.DEFAULT_BUDGET:
            ticket = policy.reserve_budget(self.root, first["context"], resource, 1, "a" * 64)
            with self.assertRaises(policy.PolicyError):
                policy.reserve_budget(self.root, first["context"], resource, 1, "b" * 64)
            if resource == "elapsed_seconds":
                policy.settle_elapsed(self.root, first["context"], ticket, .01)
                policy.reserve_budget(self.root, first["context"], resource, .5, "c" * 64)

    def test_historical_same_version_family_damage_does_not_block_new_task(self):
        ledger = self.root / "docs/design/detail/V1/_开发期设计增量.md"
        ledger.parent.mkdir(parents=True)
        ledger.write_text("## 待级联\nold unrecognized line\nanother old line\n")
        first = self.resolve_static_only()
        static = self.static(first)
        done = entry.complete_context(self.root, first["execution_context"], static_evidence=static["evidence_file"])
        self.assertTrue(done["completed"], done)
        self.assertEqual(done["blocking_obligations"], [])
        self.assertEqual(done["diagnostics"][0]["status"], "PREEXISTING_UNCHANGED")

    def review_report(self, result):
        path = Path(result["execution_context"]).with_name("review-fixture.json")
        path.write_text(json.dumps({"schema": 1, "action": "review", "status": "PASS",
            "execution_context": entry.evidence_identity(result["context"]),
            "inputs": {"app.py": entry.initial_file_hash(self.root / "app.py")},
            "checks": [{"kind": "code-review", "status": "PASS", "evidence": ["app.py:1 assignment inspected"]}],
            "findings": []}))
        return str(path)

    def test_equivalent_is_explicit_keeps_tool_error_and_rejects_business_fail(self):
        from unittest import mock
        import test_ledger as ledger
        import execution_policy as policy
        first = self.resolve(additional_grants=["related-test", "review", "equivalent-evidence"],
                             authorization_source=self.source("运行相关测试并允许既有审查与实际成功进程的等价证据"))
        before = ledger.tree_snapshot(self.root, [])
        # 执行真实exit0进程，只模拟运行后文件系统读取故障；原工具错误必须保留。
        with mock.patch.object(ledger, "tree_snapshot", side_effect=[before, OSError("post-run stat unavailable")]):
            run, code = ledger.run(self.root, ".", "targeted", "policy-env",
                [sys.executable, "-B", "-c", "assert 1 + 1 == 2"], execution_context=first["context"])
        self.assertNotEqual(code, 0)
        review = self.review_report(first)
        alternative = entry.record_equivalent(self.root, first["execution_context"], run["run_id"], "policy-env", review)
        self.assertEqual(alternative["status"], "EQUIVALENT")
        original = next(row for row in ledger.load(self.root) if row.get("run_id") == run["run_id"])
        self.assertEqual(original["status"], "ERROR")
        self.assertEqual(original["exit_code"], 0)
        bad, _ = ledger.run(self.root, ".", "targeted", "policy-env",
            [sys.executable, "-B", "-c", "assert False"], execution_context=first["context"])
        with self.assertRaises(ValueError):
            entry.record_equivalent(self.root, first["execution_context"], bad["run_id"], "policy-env", review)
        other = self.resolve(additional_grants=["related-test"], authorization_source=self.source())
        with self.assertRaises(policy.PolicyError):
            entry.record_equivalent(self.root, other["execution_context"], run["run_id"], "policy-env", review)
        with self.assertRaises(ValueError):
            entry.record_equivalent(self.root, first["execution_context"], run["run_id"], "policy-env", None)

    def version_manifest(self, build="build-007"):
        import hashlib
        cases = self.root / "docs/testing/V1/正式用例"
        cases.mkdir(parents=True, exist_ok=True)
        index = cases / "00_索引.md"
        index.write_text("TC-ONE 本版本的值验收\n")
        (cases / "03_cases.md").write_text("#### 用例 TC-ONE: value correctness\n")
        (self.root / "tests").mkdir(exist_ok=True)
        test = self.root / "tests/test_app.py"
        test.write_text("import unittest\nclass T(unittest.TestCase):\n def test_value(self): self.assertEqual(1 + 1, 2)\n")
        baseline = self.root / "docs/testing/V1/acceptance.json"
        baseline.write_text(json.dumps({"version": "V1", "acceptance_tests": ["tests/test_app.py"], "dependencies": [],
            "cases": [{"id": "TC-ONE", "test_files": ["tests/test_app.py"]}],
            "case_index": {"path": index.relative_to(self.root).as_posix(), "sha256": hashlib.sha256(index.read_bytes()).hexdigest()}}))
        self.git("add", "docs", "tests")
        self.git("commit", "-qm", "freeze version acceptance")
        manifest = {"schema": 1, "version": "V1", "build": build, "commit": self.git("rev-parse", "HEAD").strip(),
            "source": "version-acceptance", "acceptance_baseline": {"path": baseline.relative_to(self.root).as_posix(),
                "sha256": hashlib.sha256(baseline.read_bytes()).hexdigest()},
            "acceptance_tests": ["tests/test_app.py"], "dependencies": [],
            "suites": [{"cwd": ".", "env_id": "policy-env", "inputs": [], "external_dependencies": "none",
                "runners": [{"cwd": ".", "env_id": "policy-env", "suffixes": [".py"],
                    "argv": [sys.executable, "-B", "-m", "unittest", "-v", "{tests}"]}]}]}
        path = self.root / "memory/.aidp/test-manifest.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(manifest))
        return path, manifest

    def test_full_manifest_checks_real_suite_and_rejects_missing_discovered_tests(self):
        import test_ledger as ledger
        import execution_policy as policy
        from test_scope import derive_suite
        manifest_path, manifest = self.version_manifest()
        standalone = self.resolve(authorization_source=self.source("跑全量单测"))
        with self.assertRaises(policy.PolicyError):
            policy.require_action(standalone["context"], "full-regression")
        parent = self.resolve(entry="sprint-autopilot", authorization_source={"kind": "explicit-command",
            "command": "/sprint-autopilot", "request_id": "version-full", "options": ["--skip-dev"]})
        first = entry.fork_test_build(self.root, parent["execution_context"], "V1", "build-007", manifest=manifest_path)
        plan = derive_suite(self.root, manifest["suites"][0]["runners"], manifest, first["context"])
        item = plan["runs"][0]
        command = item["argv"]
        run, code = ledger.run(self.root, ".", "version", "policy-env", command,
            inputs=item["inputs"], execution_context=first["context"], scope_plan=plan)
        self.assertEqual(code, 0, run)
        report = {"action": "full-regression", "status": "PASS", "execution_context": first["identity"],
            "inputs": {name: entry.initial_file_hash(self.root / name) for name in ("app.py", "tests/test_app.py")},
            "checks": [{"kind": "suite-inventory", "status": "PASS", "evidence": ["frozen version acceptance tests"]}],
            "ledger_root": str(self.root), "tests": ["tests/test_app.py"],
            "suites": [{"name": "python", "run_id": run["run_id"], "command": command, "cwd": ".", "tests": ["tests/test_app.py"]}]}
        path = Path(first["execution_context"]).with_name("full.json")
        path.write_text(json.dumps(report))
        verified = entry.verify_full_evidence(self.root, first["context"], str(path), "policy-env")
        self.assertEqual(verified["status"], "PASS", verified)
        report["tests"] = []
        path.write_text(json.dumps(report))
        with self.assertRaises(ValueError):
            entry.verify_full_evidence(self.root, first["context"], str(path), "policy-env")

    def test_equivalent_single_scope_completes_without_erasing_original_error(self):
        from unittest import mock
        import test_ledger as ledger
        from test_scope import derive
        (self.root / "tests").mkdir()
        (self.root / "tests/test_app.py").write_text(
            "from pathlib import Path\nassert Path('app.py').read_text() == 'value = 2\\n'\n"
            "Path('memory/.aidp/after-test-marker').write_text('done')\n")
        first = self.resolve(additional_grants=["related-test", "review", "equivalent-evidence"],
            authorization_source=self.source("相关测试、审查，允许明确的工具故障等价证据"))
        (self.root / "app.py").write_text("value = 2\n")
        plan = derive(self.root, None, [{"cwd": ".", "suffixes": [".py"],
            "argv": [sys.executable, "-B", "{tests}"]}], execution_context=first["execution_context"])
        scope = Path(first["execution_context"]).with_name("scope.json")
        scope.write_text(json.dumps(plan))
        original_snapshot = ledger.tree_snapshot
        failed = []
        def snapshot(*args, **kwargs):
            if (self.root / "memory/.aidp/after-test-marker").exists() and not failed:
                failed.append(True)
                raise OSError("post-run filesystem tool unavailable")
            return original_snapshot(*args, **kwargs)
        with mock.patch.object(ledger, "tree_snapshot", side_effect=snapshot):
            runs, code = ledger.run_scope(self.root, str(scope), "policy-env", execution_context=first["context"])
        self.assertNotEqual(code, 0)
        report_path = Path(self.review_report(first))
        report = json.loads(report_path.read_text())
        report["inputs"]["tests/test_app.py"] = entry.initial_file_hash(self.root / "tests/test_app.py")
        report_path.write_text(json.dumps(report))
        alternate = entry.record_equivalent(self.root, first["execution_context"], runs["run_ids"][0],
                                              "policy-env", str(report_path))
        static = self.static(first)
        done = entry.complete_context(self.root, first["execution_context"], static_evidence=static["evidence_file"],
            scope_file=str(scope), scope_hash=plan["scope_hash"], run_ids=runs["run_ids"], env_id="policy-env",
            review_evidence=str(report_path), equivalent_evidence=alternate["evidence_file"])
        self.assertTrue(done["completed"], done)
        self.assertEqual(done["status"], "EQUIVALENT")
        self.assertEqual(done["verification"]["original_error"]["status"], "ERROR")

    def test_refork_refreshes_parent_grants_budget_and_preserves_same_scope_evidence(self):
        import execution_policy as policy
        parent = self.resolve_static_only(entry="sprint-batch", execution_budget={"processes": 3})
        child = entry.fork_context(self.root, parent["execution_context"], "001")
        static = self.static(child)
        revised = entry.revise_context(self.root, parent["execution_context"], additional_grants=["commit"],
            execution_budget={"processes": 5}, authorization_source=self.source("追加提交授权并增加进程预算"))
        with self.assertRaises(ValueError):
            policy.require_action(child["context"], "static")
        refreshed = entry.fork_context(self.root, revised["execution_context"], "001")
        policy.require_action(refreshed["context"], "static")
        policy.require_action(refreshed["context"], "commit")
        self.assertEqual(refreshed["task_id"], child["task_id"])
        self.assertEqual(refreshed["since"], child["since"])
        self.assertEqual(refreshed["identity"], child["identity"])
        self.assertEqual(refreshed["context"]["execution_budget"]["processes"], 5)
        with self.assertRaises(ValueError):
            policy.require_action(child["context"], "static")
        result = entry.check_completion(self.root, refreshed["execution_context"], static_evidence=static["evidence_file"])
        self.assertTrue(result["ready"], result)
        reservation = policy.reserve_budget(self.root, refreshed["context"], "processes", 1, "a" * 64)
        self.assertEqual(reservation["used"], 2)  # 原静态进程仍计入父预算。
        retry = entry.fork_context(self.root, revised["execution_context"], "001")
        self.assertEqual(retry["identity_hash"], refreshed["identity_hash"])

    def test_refork_parent_write_set_change_invalidates_child_scope_evidence(self):
        (self.root / "other.py").write_text("other = 1\n")
        parent = self.resolve(entry="sprint-batch")
        child = entry.fork_context(self.root, parent["execution_context"], "001")
        static = self.static(child)
        revised = entry.revise_context(self.root, parent["execution_context"], write_set=["other.py"])
        refreshed = entry.fork_context(self.root, revised["execution_context"], "001")
        self.assertEqual(refreshed["context"]["write_set"], ["app.py", "other.py"])
        self.assertEqual(refreshed["since"], child["since"])
        self.assertEqual(refreshed["context"]["scope_revision"], child["context"]["scope_revision"] + 1)
        self.assertNotEqual(refreshed["identity"], child["identity"])
        stale = entry.check_completion(self.root, refreshed["execution_context"], static_evidence=static["evidence_file"])
        self.assertFalse(stale["ready"])

    def test_refork_preserves_explicit_child_action_restriction(self):
        import execution_policy as policy
        parent = self.resolve(entry="sprint-batch")
        child = entry.fork_context(self.root, parent["execution_context"], "001", allowed_actions=["static"])
        revised = self.grant(parent, ["commit"])
        refreshed = entry.fork_context(self.root, revised["execution_context"], "001")
        self.assertEqual(refreshed["context"]["allowed_actions"], ["static"])
        policy.require_action(refreshed["context"], "static")
        with self.assertRaises(ValueError):
            policy.require_action(refreshed["context"], "commit")

    def test_directory_write_set_accepts_complete_file_inputs_and_detects_membership_changes(self):
        source = self.root / "src"
        source.mkdir()
        (source / "app.py").write_text("value = 2\n")
        result = entry.resolve_context(self.root, "sprint-dev", version="V1", write_set=["src"],
            authorization_source=dict(self.source("仅语法验证，跳过相关测试"), skip_actions=["related-test"]))
        static = entry.run_static(self.root, result["execution_context"],
            [sys.executable, "-B", "-c", "import ast; ast.parse(open('src/app.py').read())"], ["src/app.py"])
        self.assertEqual(static["status"], "PASS")
        self.assertTrue(entry.check_completion(self.root, result["execution_context"], static_evidence=static["evidence_file"])["ready"])
        (source / "added.py").write_text("added = True\n")
        self.assertFalse(entry.check_completion(self.root, result["execution_context"], static_evidence=static["evidence_file"])["ready"])
        (source / "added.py").unlink()
        (source / "app.py").unlink()
        source.rmdir()
        self.assertFalse(entry.check_completion(self.root, result["execution_context"], static_evidence=static["evidence_file"])["ready"])

    def test_directory_inputs_expand_and_reject_empty_missing_members_or_symlinks(self):
        source = self.root / "src"
        (source / "nested").mkdir(parents=True)
        (source / "app.py").write_text("value = 1\n")
        (source / "nested/data.json").write_text("{}\n")
        result = entry.resolve_context(self.root, "sprint-dev", version="V1", write_set=["src"])
        ctx = result["context"]
        self.assertEqual(set(entry._input_files(self.root, ctx, ["src"])), {"src/app.py", "src/nested/data.json"})
        for incomplete in ([], ["src/app.py"], ["app.py"]):
            with self.assertRaises(ValueError):
                entry._input_files(self.root, ctx, incomplete)
        with tempfile.TemporaryDirectory(prefix="aidp-outside-input-") as outside:
            (Path(outside) / "hidden.py").write_text("hidden = 1\n")
            (source / "escape").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError):
                entry._input_files(self.root, ctx, ["src"])
            with self.assertRaises(ValueError):
                entry._input_files(self.root, ctx, ["src/app.py", "src/nested/data.json"])
        (self.root / "empty").mkdir()
        empty = entry.resolve_context(self.root, "sprint-dev", version="V1", write_set=["empty"])
        with self.assertRaises(ValueError):
            entry._input_files(self.root, empty["context"], ["empty"])
        with self.assertRaises(ValueError):
            entry._input_files(self.root, empty["context"], ["app.py"])

    def test_child_can_narrow_but_not_expand_actions(self):
        parent = self.resolve(entry="sprint-batch")
        child = entry.fork_context(self.root, parent["execution_context"], "007", allowed_actions=["static"])
        self.assertEqual(child["context"]["allowed_actions"], ["static"])
        with self.assertRaises(ValueError):
            entry.fork_context(self.root, parent["execution_context"], "008", allowed_actions=["full-regression"])

    def test_cicd_default_and_legacy_switch_do_not_create_user_authorization(self):
        from aidp_config import cicd_config
        self.assertFalse(cicd_config(self.root)["auto_trigger"])
        config = self.root / "memory/aidp-config.yaml"
        config.parent.mkdir(exist_ok=True)
        config.write_text("cicd:\n  auto_trigger: false\n")
        self.assertFalse(cicd_config(self.root)["auto_trigger_explicitly_disabled"])
        config.write_text("cicd:\n  auto_trigger: false\n  auto_trigger_source:\n    kind: project-policy\n"
            "    user_selected: true\n    request_id: disabled-by-user\n    text: 禁止自动流水线写操作\n")
        self.assertTrue(cicd_config(self.root)["auto_trigger_explicitly_disabled"])
        self.assertNotIn("deploy", self.resolve()["context"]["allowed_actions"])

    def test_other_task_new_same_version_ledger_issue_is_diagnostic_not_blocking(self):
        first = self.resolve_static_only()
        ledger = self.root / "docs/design/detail/V1/_开发期设计增量.md"
        ledger.parent.mkdir(parents=True)
        ledger.write_text("## 待级联\nother task malformed line\nanother unrelated line\n")
        static = self.static(first)
        result = entry.complete_context(self.root, first["execution_context"], static_evidence=static["evidence_file"])
        self.assertTrue(result["completed"], result)
        self.assertEqual(result["blocking_obligations"], [])
        self.assertEqual(result["diagnostics"][0]["status"], "UNATTRIBUTED_CHANGE")

    def test_large_repository_creates_light_context_without_hashing_all_clean_files(self):
        from unittest import mock
        bulk = self.root / "src"
        bulk.mkdir()
        for index in range(2200):
            (bulk / f"file_{index}.py").write_text(f"value = {index}\n")
        self.git("add", "src")
        self.git("commit", "-qm", "large clean repository")
        with mock.patch.object(entry, "initial_file_hash", wraps=entry.initial_file_hash) as hashing:
            resolved = self.resolve()
        self.assertLessEqual(hashing.call_count, 2)
        self.assertEqual(entry.initial_hash(self.root, resolved["context"], "src/file_100.py"),
                         entry.initial_file_hash(bulk / "file_100.py"))
        proc = subprocess.run([sys.executable, str(SCRIPTS / "entry_context.py"), "resolve", "--root", str(self.root),
            "--entry", "sprint-dev", "--version", "V1", "--write-set", "app.py", "--json"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertLess(len(proc.stdout.encode()), 16000)
        self.assertNotIn("context", json.loads(proc.stdout))
        consumed = subprocess.run([sys.executable, "-c", "import json,sys; assert json.loads(sys.argv[1])['execution_context']",
                                   proc.stdout], capture_output=True)
        self.assertEqual(consumed.returncode, 0)

    def test_generation_entries_have_minimal_explicit_document_responsibility(self):
        for command in ("sprint-requirements", "sprint-design", "sprint-plan", "sprint-selftest"):
            result = self.resolve(entry=command, authorization_source={"kind": "explicit-command",
                "request_id": command + "-request", "command": "/" + command})
            self.assertEqual(result["context"]["mode"], "light")
            self.assertEqual(result["context"]["allowed_actions"], ["document", "static"])
            self.assertEqual(result["context"]["task_scope"]["kind"], "planning")
            parent = self.resolve()
            nested = entry.resolve_context(self.root, command, execution_context=parent["execution_context"])
            self.assertNotIn("document", nested["context"]["allowed_actions"])

    def test_autopilot_root_reuses_same_version_and_only_persistent_intent_starts_next_version(self):
        import execution_policy as policy
        source = {"kind": "explicit-command", "command": "/sprint-autopilot", "request_id": "continuous-user",
                  "persistent": True, "text": "持续执行 /sprint-autopilot，处理后续真实新版本"}
        first = entry.resolve_autopilot_root(self.root, "V1", authorization_source=source)
        policy.reserve_budget(self.root, first["context"], "processes", 1, "a" * 64)
        repeated = entry.resolve_autopilot_root(self.root, "V1", execution_context=first["execution_context"])
        self.assertEqual(repeated["task_id"], first["task_id"])
        self.assertEqual(policy.reserve_budget(self.root, repeated["context"], "processes", 1, "b" * 64)["used"], 2)
        revised = entry.revise_context(self.root, first["execution_context"], additional_grants=["migration-rehearsal"],
                                      authorization_source=self.source("本版额外演练"))
        next_version = entry.resolve_autopilot_root(self.root, "V2", execution_context=revised["execution_context"])
        self.assertNotEqual(next_version["task_id"], first["task_id"])
        self.assertEqual(next_version["context"]["version"], "V2")
        self.assertNotIn("migration-rehearsal", next_version["context"]["allowed_actions"])
        self.assertEqual(next_version["context"]["authorization_source"][0]["request_id"], "continuous-user")
        policy.record_outcome(self.root, next_version["context"], "static", "TOOL_ERROR", "c" * 64, root_cause="unchanged tool failure")
        resumed = entry.resolve_autopilot_root(self.root, "V2", execution_context=revised["execution_context"])
        self.assertEqual(resumed["identity_hash"], next_version["identity_hash"])
        with self.assertRaises(policy.PolicyError):
            policy.reserve_budget(self.root, resumed["context"], "processes", 1, "c" * 64, action="static")
        once = entry.resolve_autopilot_root(self.root, "V3", authorization_source=dict(source, request_id="once-user", options=["--once"], persistent=False))
        with self.assertRaises(ValueError):
            entry.resolve_autopilot_root(self.root, "V4", execution_context=once["execution_context"])
        with self.assertRaises(ValueError):
            entry.resolve_autopilot_root(self.root, "V4")
        unproven = self.resolve(entry="sprint-autopilot")
        with self.assertRaises(ValueError):
            entry.resolve_autopilot_root(self.root, "V4", execution_context=unproven["execution_context"])

    def test_same_version_explicit_skip_narrows_old_wide_root_without_resetting_budget(self):
        import execution_policy as policy
        original = entry.resolve_autopilot_root(self.root, "V1", authorization_source={"kind": "explicit-command",
            "command": "/sprint-autopilot", "request_id": "initial-wide-command"})
        policy.reserve_budget(self.root, original["context"], "processes", 1, "a" * 64)
        narrowed = entry.resolve_autopilot_root(self.root, "V1", execution_context=original["execution_context"],
            authorization_source={"kind": "explicit-command", "command": "/sprint-autopilot", "request_id": "current-skip-command",
                "options": ["--skip-dev", "--skip-deploy", "--skip-aiauto-test"]})
        self.assertEqual(narrowed["context"]["allowed_actions"], ["static"])
        self.assertEqual(narrowed["task_id"], original["task_id"])
        self.assertEqual(narrowed["identity"], original["identity"])
        self.assertGreater(narrowed["context"]["authorization_revision"], original["context"]["authorization_revision"])
        self.assertEqual(len(narrowed["context"]["authorization_source"]), 2)
        self.assertEqual(policy.reserve_budget(self.root, narrowed["context"], "processes", 1, "b" * 64)["used"], 2)
        with self.assertRaises(ValueError):
            policy.require_action(original["context"], "deploy")
        with self.assertRaises(ValueError):
            policy.require_action(narrowed["context"], "full-regression")

    def test_once_and_no_loop_roots_resume_same_task_but_do_not_authorize_next_version(self):
        import execution_policy as policy
        for flag in ("--no-loop", "--once"):
            with self.subTest(flag=flag):
                first = entry.resolve_autopilot_root(self.root, "V1.0.0", authorization_source={
                    "kind": "explicit-command", "command": "/sprint-autopilot", "request_id": "wrapper-" + flag,
                    "options": ["--unattended", flag]})
                reserved = policy.reserve_budget(self.root, first["context"], "processes", 1, "a" * 64)
                resumed = entry.resolve_autopilot_root(self.root, "V1.0.0", execution_context=first["execution_context"])
                self.assertEqual(resumed["task_id"], first["task_id"])
                self.assertEqual(resumed["identity_hash"], first["identity_hash"])
                self.assertEqual(policy.reserve_budget(self.root, resumed["context"], "processes", 1, "b" * 64)["used"], reserved["used"] + 1)
                with self.assertRaises(ValueError):
                    entry.resolve_autopilot_root(self.root, "V2.0.0", execution_context=resumed["execution_context"])

    def test_explicit_target_scope_cannot_be_carried_to_a_different_version(self):
        for index, options in enumerate((["--target", "V1.0.0"], ["--target=V1.0.0"])):
            with self.subTest(options=options):
                source = {"kind": "explicit-command", "command": "/sprint-autopilot", "request_id": f"targeted-{index}",
                          "options": options, "persistent": True, "text": "持续检查明确指定的 V1.0.0"}
                first = entry.resolve_autopilot_root(self.root, "V1.0.0", authorization_source=source)
                same = entry.resolve_autopilot_root(self.root, "V1.0.0", execution_context=first["execution_context"])
                self.assertEqual(same["task_id"], first["task_id"])
                with self.assertRaises(ValueError):
                    entry.resolve_autopilot_root(self.root, "V2.0.0", execution_context=first["execution_context"])
                with self.assertRaises(ValueError):
                    entry.resolve_autopilot_root(self.root, "V2.0.0", authorization_source=source)
        fresh = entry.resolve_autopilot_root(self.root, "V2.0.0", authorization_source={
            "kind": "explicit-command", "command": "/sprint-autopilot", "request_id": "new-target-current-request",
            "options": ["--target=V2.0.0"]})
        self.assertEqual(fresh["context"]["version"], "V2.0.0")

    def test_bare_historical_command_does_not_imply_future_version_intent(self):
        first = entry.resolve_autopilot_root(self.root, "V1", authorization_source={
            "kind": "explicit-command", "command": "/sprint-autopilot", "request_id": "single-unbounded-command"})
        with self.assertRaises(ValueError):
            entry.resolve_autopilot_root(self.root, "V2", execution_context=first["execution_context"])
        with self.assertRaises(ValueError):
            entry.resolve_autopilot_root(self.root, "V2", authorization_source={"kind": "explicit-command",
                "command": "/sprint-autopilot", "request_id": "placeholder-persistence", "persistent": True})

    def test_autopilot_root_accepts_selected_command_policy_without_inventing_public_grants(self):
        config = self.root / "memory/aidp-config.yaml"
        config.parent.mkdir(exist_ok=True)
        config.write_text("execution_policy:\n  allowed_actions: [document, commit, push]\n  authorization_source:\n"
            "    kind: project-policy\n    command: /sprint-autopilot\n    user_selected: true\n"
            "    request_id: project-loop-choice\n    text: 持续处理各版本文档和提交推送\n")
        result = entry.resolve_autopilot_root(self.root, "V2")
        self.assertIn("document", result["context"]["allowed_actions"])
        self.assertNotIn("full-regression", result["context"]["allowed_actions"])
        child = entry.fork_version(self.root, result["execution_context"], "V2")
        self.assertEqual(child["context"]["allowed_actions"], ["commit", "document", "push", "static"])
        self.assertEqual(result["context"]["authorization_source"][0]["kind"], "project-policy")

    def test_root_selector_keeps_narrow_incoming_and_named_root_ahead_of_wide_cache(self):
        wide = entry.resolve_autopilot_root(self.root, "V1", authorization_source={"kind": "explicit-command",
            "command": "/sprint-autopilot", "request_id": "canonical-wide"})
        narrow = self.resolve(entry="sprint-autopilot", authorization_source={"kind": "explicit-command",
            "command": "/sprint-autopilot", "request_id": "incoming-narrow", "options": ["--skip-aiauto-test"]})
        selected = entry.resolve_autopilot_root(self.root, "V1", execution_context=narrow["execution_context"])
        self.assertEqual(selected["task_id"], narrow["task_id"])
        self.assertNotIn("live-tests", selected["context"]["allowed_actions"])
        other_entry = self.resolve()
        with self.assertRaises(ValueError):
            entry.resolve_autopilot_root(self.root, "V1", execution_context=other_entry["execution_context"])
        baseline = self.root / "memory/.sprint-autopilot-baseline.json"
        baseline.write_text(json.dumps({"versions": {"V1": {"autopilot_root_context": narrow["execution_context"],
                                                            "execution_context": wide["execution_context"]}}}))
        indexed = entry.resolve_autopilot_root(self.root, "V1")
        self.assertEqual(indexed["task_id"], narrow["task_id"])
        self.assertNotIn("full-regression", indexed["context"]["allowed_actions"])

    def test_existing_only_root_selector_never_creates_or_regrants(self):
        source = {"kind": "explicit-command", "command": "/sprint-autopilot", "request_id": "current-controller"}
        with self.assertRaises(ValueError):
            entry.resolve_autopilot_root(self.root, "V1", existing_only=True)
        self.assertFalse((self.root / "memory/.aidp").exists())
        root = entry.resolve_autopilot_root(self.root, "V1", authorization_source=source)
        before = {str(path.relative_to(self.root)): path.read_bytes()
                  for path in (self.root / "memory/.aidp").rglob("*") if path.is_file()}
        selected = entry.resolve_autopilot_root(self.root, "V1", execution_context=root["execution_context"], existing_only=True)
        self.assertEqual(selected["task_id"], root["task_id"])
        with self.assertRaises(ValueError):
            entry.resolve_autopilot_root(self.root, "V2", execution_context=root["execution_context"], existing_only=True)
        with self.assertRaises(ValueError):
            entry.resolve_autopilot_root(self.root, "V1", authorization_source=source, existing_only=True)
        after = {str(path.relative_to(self.root)): path.read_bytes()
                 for path in (self.root / "memory/.aidp").rglob("*") if path.is_file()}
        self.assertEqual(before, after)

    def test_autopilot_root_preserves_existing_version_pointer_and_budget(self):
        import execution_policy as policy
        existing = self.resolve(entry="sprint-autopilot", authorization_source={"kind": "explicit-command",
            "command": "/sprint-autopilot", "request_id": "existing-version-root"})
        policy.reserve_budget(self.root, existing["context"], "processes", 1, "a" * 64)
        baseline = self.root / "memory/.sprint-autopilot-baseline.json"
        baseline.write_text(json.dumps({"versions": {"V1": {"execution_context": existing["execution_context"]}}}))
        restored = entry.resolve_autopilot_root(self.root, "V1")
        self.assertEqual(restored["task_id"], existing["task_id"])
        self.assertEqual(policy.reserve_budget(self.root, restored["context"], "processes", 1, "b" * 64)["used"], 2)

    def test_autopilot_same_version_release_child_preserves_restricted_shared_context(self):
        import execution_policy as policy
        parent = entry.resolve_context(self.root, "sprint-autopilot", version="V1", write_set=["app.py"],
            authorization_source={"kind": "explicit-command", "request_id": "pre-only", "command": "/sprint-autopilot"},
            execution_budget={"processes": 1})
        child = entry.fork_version(self.root, parent["execution_context"], "V1")
        self.assertEqual(child["context"]["version"], "V1")
        self.assertEqual(child["context"]["allowed_actions"], ["commit", "docs-audit", "document", "push", "static"])
        policy.reserve_budget(self.root, child["context"], "processes", 1, "a" * 64)
        again = entry.fork_version(self.root, parent["execution_context"], "V1")
        self.assertEqual(again["identity_hash"], child["identity_hash"])
        with self.assertRaises(policy.PolicyError):
            policy.reserve_budget(self.root, again["context"], "processes", 1, "b" * 64)

    def test_test_build_child_is_deterministic_restricted_and_shares_refreshed_budget(self):
        import execution_policy as policy
        manifest_path, manifest = self.version_manifest()
        parent = self.resolve(entry="sprint-autopilot", authorization_source={"kind": "explicit-command",
            "request_id": "scheduled-tests", "command": "/sprint-autopilot"}, execution_budget={"processes": 2})
        child = entry.fork_test_build(self.root, parent["execution_context"], "V1", "build-007", manifest=manifest_path)
        self.assertEqual(child["context"]["mode"], "formal")
        self.assertEqual(child["context"]["allowed_actions"], ["full-regression", "live-tests", "static"])
        self.assertEqual(child["context"]["build_id"], "build-007")
        policy.reserve_budget(self.root, child["context"], "processes", 1, "a" * 64)
        repeat = entry.fork_test_build(self.root, parent["execution_context"], "V1", "build-007", manifest=manifest_path)
        self.assertEqual(repeat["identity_hash"], child["identity_hash"])
        self.assertEqual(policy.reserve_budget(self.root, repeat["context"], "processes", 1, "b" * 64)["used"], 2)
        revised = entry.revise_context(self.root, parent["execution_context"], execution_budget={"processes": 3},
                                        authorization_source=self.source("增加本任务预算"))
        refreshed = entry.fork_test_build(self.root, revised["execution_context"], "V1", "build-007", manifest=manifest_path)
        self.assertEqual(refreshed["identity"], child["identity"])
        self.assertEqual(policy.reserve_budget(self.root, refreshed["context"], "processes", 1, "c" * 64)["used"], 3)
        with self.assertRaises(ValueError):
            policy.require_action(child["context"], "static")
        for version, build in (("V0", "build-007"), ("V2", "build-008"), ("V1", ""), ("V1", "../escape")):
            with self.assertRaises(ValueError):
                entry.fork_test_build(self.root, revised["execution_context"], version, build, manifest=manifest_path)
        light = self.resolve(additional_grants=["live-tests"], authorization_source=self.source("浏览器测试"))
        with self.assertRaises(ValueError):
            entry.fork_test_build(self.root, light["execution_context"], "V1", "build-007", manifest=manifest_path)
        formal_without_grant = self.resolve(entry="sprint-autopilot")
        with self.assertRaises(ValueError):
            entry.fork_test_build(self.root, formal_without_grant["execution_context"], "V1", "build-007", manifest=manifest_path)
        standalone = self.resolve(entry="sprint-aiauto-test", authorization_source={"kind": "explicit-command",
            "request_id": "standalone-tests", "command": "/sprint-aiauto-test"})
        self.assertEqual(standalone["context"]["mode"], "formal")
        with self.assertRaises(ValueError):
            entry.fork_test_build(self.root, standalone["execution_context"], "V1", "build-007", manifest=manifest_path)
        policy.require_action(refreshed["context"], "full-regression")
        manifest["acceptance_tests"] = []
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):
            policy.require_action(refreshed["context"], "full-regression")

    def test_cli_fork_development_subset_defers_version_delivery_to_parent(self):
        parent = self.resolve(entry="sprint-autopilot", authorization_source={"kind": "explicit-command",
            "request_id": "full-pipeline", "command": "/sprint-autopilot"})
        development = ["implement", "static", "document", "related-test", "review", "full-cvl", "docs-audit"]
        proc = subprocess.run([sys.executable, str(SCRIPTS / "entry_context.py"), "fork", "--root", str(self.root),
            "--execution-context", parent["execution_context"], "--sprint", "001", "--json",
            *[value for action in development for value in ("--allow-action", action)]], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        child = json.loads(proc.stdout)
        self.assertEqual(set(child["allowed_actions"]), set(development))
        child_static = self.static(child)
        child_gate = entry.check_completion(self.root, child["execution_context"], static_evidence=child_static["evidence_file"])
        for action in ("commit", "push", "deploy", "live-tests", "full-regression"):
            self.assertEqual(child_gate["checks"][action], "NOT_REQUESTED")
        parent_static = self.static(parent)
        parent_gate = entry.check_completion(self.root, parent["execution_context"], static_evidence=parent_static["evidence_file"])
        self.assertEqual(parent_gate["checks"]["full-regression"], "UNVERIFIED")
        self.assertIn("full-evidence", parent_gate["error"])
        self.assertIn("deploy", parent["context"]["allowed_actions"])

    def test_autopilot_previous_version_inherits_document_grant_and_shared_budget(self):
        import execution_policy as policy
        parent = entry.resolve_context(self.root, "sprint-autopilot", version="V2", write_set=["app.py"],
            authorization_source={"kind": "explicit-command", "request_id": "autopilot-v2", "command": "/sprint-autopilot"},
            execution_budget={"processes": 1})
        child = entry.fork_version(self.root, parent["execution_context"], "V1")
        self.assertEqual(child["context"]["version"], "V1")
        self.assertEqual(child["context"]["allowed_actions"], ["commit", "docs-audit", "document", "push", "static"])
        self.assertEqual(child["context"]["parent_task_id"], parent["task_id"])
        self.assertEqual(entry.fork_version(self.root, parent["execution_context"], "V1")["identity_hash"], child["identity_hash"])
        policy.reserve_budget(self.root, child["context"], "processes", 1, "a" * 64)
        with self.assertRaises(policy.PolicyError):
            policy.reserve_budget(self.root, parent["context"], "processes", 1, "b" * 64)
        for result in (self.resolve(), self.resolve(entry="sprint-autopilot")):
            with self.assertRaises(ValueError):
                entry.fork_version(self.root, result["execution_context"], "V0")
        with self.assertRaises(ValueError):
            entry.fork_version(self.root, parent["execution_context"], "V3")

    def test_version_release_option_grants_git_while_planning_does_not(self):
        source = {"kind": "explicit-command", "request_id": "version-user", "command": "/version"}
        planning = self.resolve(entry="version", authorization_source=source)
        self.assertEqual(planning["context"]["task_scope"]["kind"], "planning")
        self.assertNotIn("commit", planning["context"]["allowed_actions"])
        for option in ("--release", "--no-tag"):
            release = self.resolve(entry="version", authorization_source=dict(source, options=[option]))
            self.assertEqual(release["context"]["task_scope"]["kind"], "release")
            self.assertTrue({"commit", "push"} <= set(release["context"]["allowed_actions"]))
            self.assertNotIn("deploy", release["context"]["allowed_actions"])
            self.assertNotIn("full-regression", release["context"]["allowed_actions"])

    def test_explicit_cascade_now_grants_document_without_docs_audit(self):
        plain = self.resolve()
        self.assertNotIn("document", plain["context"]["allowed_actions"])
        explicit = self.resolve(authorization_source={"kind": "explicit-command", "request_id": "cascade-user",
            "command": "/sprint-dev", "options": ["--cascade-now"]})
        self.assertIn("document", explicit["context"]["allowed_actions"])
        self.assertNotIn("docs-audit", explicit["context"]["allowed_actions"])
        route = entry.route_context(self.root, explicit["execution_context"], "dev", action="cascade")
        self.assertIn("cascade", route["actions"])
        nested = entry.resolve_context(self.root, "sprint-dev", execution_context=plain["execution_context"])
        self.assertNotIn("document", nested["context"]["allowed_actions"])
        with self.assertRaises(ValueError):
            entry.route_context(self.root, nested["execution_context"], "dev", action="cascade")

    def test_explicit_autopilot_public_pipeline_and_existing_skip_options(self):
        source = {"kind": "explicit-command", "request_id": "autopilot-user", "command": "/sprint-autopilot"}
        full = self.resolve(entry="sprint-autopilot", authorization_source=source)
        self.assertTrue({"commit", "push", "deploy", "live-tests", "full-regression"} <= set(full["context"]["allowed_actions"]))
        skipped = self.resolve(entry="sprint-autopilot", authorization_source=dict(source,
                              options=["--skip-deploy", "--skip-aiauto-test"]))
        self.assertFalse({"deploy", "live-tests", "full-regression"} & set(skipped["context"]["allowed_actions"]))
        natural = self.resolve(entry="sprint-autopilot")
        self.assertEqual(natural["context"]["allowed_actions"], ["implement", "related-test", "static"])
        test_only = self.resolve(entry="sprint-autopilot", authorization_source=dict(source, options=["--skip-dev"]))
        self.assertNotIn("implement", test_only["context"]["allowed_actions"])
        self.assertNotIn("install", full["context"]["allowed_actions"])

    def test_explicit_command_budgets_support_public_workers_without_changing_natural_defaults(self):
        plain = self.resolve(entry="sprint-full")
        self.assertEqual(plain["context"]["execution_budget"]["agents"], 2)
        self.assertEqual(plain["context"]["execution_budget"]["elapsed_seconds"], 300)
        for command in ("version", "sprint-full", "sprint-batch", "sprint-autopilot", "sprint-aiauto-test"):
            result = self.resolve(entry=command, authorization_source={"kind": "explicit-command",
                "request_id": "explicit-" + command, "command": "/" + command})
            self.assertGreaterEqual(result["context"]["execution_budget"]["agents"], 4)
            if command == "sprint-aiauto-test":
                self.assertEqual(result["context"]["execution_budget"]["elapsed_seconds"], 7200)
                import execution_policy as policy
                with self.assertRaises(policy.PolicyError):
                    policy.reserve_budget(self.root, result["context"], "elapsed_seconds", 3600, "a" * 64, action="full-regression")
                policy.reserve_budget(self.root, result["context"], "elapsed_seconds", 3600, "b" * 64, action="live-tests")
        self.assertEqual(self.resolve()["context"]["execution_budget"]["agents"], 2)

    def test_repaired_tool_environment_changes_input_and_allows_necessary_recheck(self):
        from unittest import mock
        import os
        first = self.resolve()
        tools = self.root / "memory/.aidp/tool-fixture"
        tools.mkdir(parents=True)
        with mock.patch.dict(os.environ, {"PATH": str(tools)}):
            missing = self.static(first, ["ruff", "check", "app.py"])
            self.assertEqual(missing["status"], "ENV_UNAVAILABLE")
            (tools / "ruff").write_text("#!" + sys.executable + "\nimport ast\nast.parse(open('app.py').read())\n")
            (tools / "ruff").chmod(0o755)
            repaired = self.static(first, ["ruff", "check", "app.py"])
            self.assertEqual(repaired["status"], "PASS")
            self.assertNotEqual(missing["input_hash"], repaired["input_hash"])

    def test_static_executor_rejects_tests_builds_services_and_unknown_wrappers(self):
        first = self.resolve()
        wrapper = self.root / "unknown.py"
        wrapper.write_text("from pathlib import Path\nPath('side-effect').write_text('bad')\n")
        for command in ([sys.executable, "-m", "unittest"], [sys.executable, "-m", "pytest"],
                        ["pytest"], ["mvn", "test"], ["npm", "run", "build"],
                        ["npm", "start"], [sys.executable, "unknown.py"],
                        [sys.executable, "-c", "import subprocess; subprocess.run(['pytest'])"]):
            with self.subTest(command=command), self.assertRaises(ValueError):
                entry.run_static(self.root, first["execution_context"], command, ["app.py"])
        self.assertFalse((self.root / "side-effect").exists())

    def test_child_inherits_grants_and_shares_parent_budget(self):
        import execution_policy as policy
        parent = self.resolve(entry="sprint-batch", execution_budget={"processes": 1})
        child = entry.fork_context(self.root, parent["execution_context"], "007")
        self.assertEqual(child["context"]["allowed_actions"], parent["context"]["allowed_actions"])
        with self.assertRaises(ValueError):
            self.grant(child, ["full-regression"])
        policy.reserve_budget(self.root, child["context"], "processes", 1, "a" * 64)
        with self.assertRaises(policy.PolicyError) as denied:
            policy.reserve_budget(self.root, parent["context"], "processes", 1, "b" * 64)
        self.assertEqual(denied.exception.status, "BUDGET_EXCEEDED")


if __name__ == "__main__":
    unittest.main()
