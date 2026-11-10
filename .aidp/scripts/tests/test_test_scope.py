#!/usr/bin/env python3
"""Sprint 单测确定性推导（test_scope.py）+ 逐套记账（test_ledger.py run-scope）+ worktree 复用。

临时 Git 仓库与真实子进程；不触碰本仓工作区。运行：python3 .aidp/scripts/tests/test_test_scope.py
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
SCOPE = ROOT / ".aidp/scripts/test_scope.py"
LEDGER = ROOT / ".aidp/scripts/test_ledger.py"
PY = sys.executable
sys.path.insert(0, str(ROOT / ".aidp/scripts"))
from aidp_paths import test_ledger as ledger_path  # noqa: E402  账本落点与生产代码同源


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


def last_json(text):
    return json.loads(text.strip().splitlines()[-1])


class ScopeFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aidp-test-scope-"))
        self.root = self.tmp / "repo"
        self.root.mkdir()
        git(self.root, "init", "-q")
        git(self.root, "config", "user.email", "t@example.invalid")
        git(self.root, "config", "user.name", "t")
        self.write("src/calc.py", "def f():\n    return 1\n")
        self.write("tests/__init__.py", "")
        self.write("tests/test_calc.py", "import unittest\nfrom src.calc import f\n\nclass CalcTests(unittest.TestCase):\n    def test_f(self):\n        self.assertIsInstance(f(), int)\n")
        self.write("web/card.tsx", "export const c = 1\n")
        self.write("web/card.spec.tsx", "test('c', () => {})\n")
        self.write("docs/a.md", "doc\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "base")
        self.base = git(self.root, "rev-parse", "HEAD")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def derive(self, runners, since=None, expect=0):
        argv = [PY, str(SCOPE), "--root", str(self.root), "--since", self.base if since is None else since,
                "--runners-json", json.dumps(runners), "--json"]
        p = subprocess.run(argv, capture_output=True, text=True)
        self.assertEqual(p.returncode, expect, p.stdout + p.stderr)
        return json.loads(p.stdout) if expect == 0 else None

    def ledger(self, *args, expect=0):
        p = subprocess.run([PY, str(LEDGER), *args], capture_output=True, text=True)
        self.assertEqual(p.returncode, expect, p.stdout + p.stderr)
        return last_json(p.stdout)


class TestScopeTests(ScopeFixture):
    def test_mixed_repo_splits_runners_by_suffix_and_maps_frontend_spec(self):
        self.write("src/calc.py", "def f():\n    return 2\n")
        self.write("web/card.tsx", "export const c = 2\n")
        out = self.derive([
            {"suffixes": [".py"], "argv": [PY, "-m", "pytest", "{tests}"]},
            {"suffixes": [".tsx"], "argv": ["npx", "vitest", "run", "{tests}"]},
        ])
        by = {tuple(r["suffixes"]): r for r in out["runs"]}
        self.assertEqual(by[(".py",)]["argv"][-1], "tests/test_calc.py")
        self.assertEqual(by[(".tsx",)]["argv"], ["npx", "vitest", "run", "web/card.spec.tsx"])
        self.assertEqual(out["unrunnable"], [])

    def test_untested_source_is_listed_as_unmapped_not_full_run(self):
        self.write("src/orphan.py", "x = 1\n")
        self.write("docs/a.md", "changed doc\n")
        out = self.derive([{"suffixes": [".py"], "argv": [PY, "-m", "pytest", "{tests}"]}])
        self.assertIn("src/orphan.py", out["unmapped"])
        self.assertNotIn("docs/a.md", str(out))  # 非代码与 docs 不进入输出，保证同树输出稳定
        self.assertEqual(out["runs"], [], "无对应单测时不得回落为全量")

    def test_missing_since_or_runner_fails_closed(self):
        self.write("src/calc.py", "def f():\n    return 3\n")
        self.derive([{"suffixes": [".py"], "argv": [PY, "{tests}"]}], since="", expect=2)
        self.assertEqual(self.derive([])["unrunnable"], ["tests/test_calc.py"])
        self.derive([{"suffixes": [".py"], "argv": [PY, "{unknown}"]}], expect=2)

    def test_runner_without_selection_is_rejected(self):
        self.write("src/calc.py", "x = 2\n")
        self.derive([{"suffixes": [".py"], "argv": [PY, "-m", "unittest", "discover"]}], expect=2)

    def test_same_name_modules_are_isolated_and_paths_relative_to_cwd(self):
        for module in ("one", "two"):
            self.write(f"{module}/src/calc.py", "value = 1\n")
            self.write(f"{module}/tests/test_calc.py", "import unittest\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "modules")
        self.base = git(self.root, "rev-parse", "HEAD")
        self.write("one/src/calc.py", "value = 2\n")
        out = self.derive([{"cwd": module, "suffixes": [".py"],
                            "argv": [PY, "-m", "unittest", "{tests}"]} for module in ("one", "two")])
        self.assertEqual(out["tests"], ["one/tests/test_calc.py"])
        self.assertEqual(out["runs"][0]["cwd"], "one")
        self.assertEqual(out["runs"][0]["argv"][-1], "tests/test_calc.py")

    def test_git_paths_with_unicode_spaces_and_newline_are_not_split(self):
        self.write("src/计算 空\n值.py", "x = 1\n")
        self.write("tests/test_计算 空\n值.py", "import unittest\n")
        out = self.derive([{"suffixes": [".py"], "argv": [PY, "-m", "unittest", "{tests}"]}])
        self.assertIn("src/计算 空\n值.py", out["changed"])
        self.assertIn("tests/test_计算 空\n值.py", out["tests"])

    def test_test_module_not_mistaken_for_test_file(self):
        self.write("scripts/test_ledger.py", "x = 1\n")
        self.write("test_root.py", "import unittest\n")
        out = self.derive([{"suffixes": [".py"], "argv": [PY, "-m", "pytest", "{tests}"]}])
        self.assertNotIn("scripts/test_ledger.py", out["tests"])
        self.assertIn("test_root.py", out["tests"])

    def test_since_covers_committed_and_dirty_changes_and_write_set(self):
        import test_scope
        self.write("src/calc.py", "def f(): return 2\n")
        git(self.root, "add", "src/calc.py")
        git(self.root, "commit", "-qm", "sprint change")
        self.write("web/card.tsx", "export const c = 3\n")
        out = test_scope.derive(self.root, self.base,
                               [{"suffixes": [".py"], "argv": [PY, "{tests}"]}], ["tests"])
        self.assertIn("src/calc.py", out["changed"])
        self.assertIn("web/card.tsx", out["changed"])
        self.assertIn("tests/test_calc.py", out["changed"])
        self.assertEqual(out["since"], self.base)
        self.assertEqual(out["write_set"], ["tests"])

    def test_package_directory_mapping_avoids_same_name_siblings(self):
        for package in ("a", "b"):
            self.write(f"api/src/main/java/{package}/Foo.java", "class Foo {}\n")
            self.write(f"api/src/test/java/{package}/FooTest.java", f"package {package};\nclass FooTest {{}}\n")
        self.write("api/pom.xml", "<project/>\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "java modules")
        self.base = git(self.root, "rev-parse", "HEAD")
        self.write("api/src/main/java/a/Foo.java", "class Foo { int x; }\n")
        out = self.derive([{"cwd": "api", "suffixes": [".java"], "argv": ["mvn", "test", "-Dtest={test_classes}"]}])
        self.assertEqual(out["tests"], ["api/src/test/java/a/FooTest.java"])
        self.assertEqual(out["runs"][0]["argv"][-1], "-Dtest=a.FooTest")

    def test_related_selects_source_without_empty_or_full_fallback(self):
        self.write("web/orphan.ts", "export const f = 1\n")
        out = self.derive([{"cwd": "web", "suffixes": [".ts"], "mode": "related",
                            "argv": ["npx", "vitest", "related", "--run", "{sources}"]}])
        self.assertEqual(out["unmapped"], [])
        self.assertEqual(out["runs"][0]["sources"], ["web/orphan.ts"])
        self.assertEqual(out["runs"][0]["argv"][-1], "orphan.ts")
        self.derive([{"suffixes": [".ts"], "mode": "related", "argv": ["npx", "vitest", "run", "{sources}"]}], expect=2)

    def test_bad_cwd_and_overlapping_runners_fail_before_execution(self):
        self.write("src/calc.py", "def f(): return 2\n")
        for cwd in ("..", "/tmp", "absent"):
            self.derive([{"cwd": cwd, "suffixes": [".py"], "argv": [PY, "{tests}"]}], expect=2)
        self.derive([{"suffixes": [".py"], "argv": [PY, "{tests}"]},
                     {"suffixes": [".py"], "argv": [PY, "-B", "{tests}"]}], expect=2)

    def test_tests_without_runner_are_unrunnable(self):
        self.write("web/card.spec.tsx", "test('d', () => {})\n")
        out = self.derive([{"suffixes": [".py"], "argv": [PY, "-m", "pytest", "{tests}"]}])
        self.assertIn("web/card.spec.tsx", out["unrunnable"])


class RunScopeTests(ScopeFixture):
    """逐套记账：PASS 复用、FAIL 不能冒充通过、推导为空返回 EMPTY。"""

    def scope_file(self, runners):
        out = self.derive(runners)
        target = self.root / "docs/testing/V1/sprint-001/unit-scope.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
        return "docs/testing/V1/sprint-001/unit-scope.json"

    def test_run_scope_passes_then_reuses_on_same_tree(self):
        runners = [{"suffixes": [".py"], "argv": [PY, "-B", "-m", "unittest", "{tests}"]}]
        self.write("src/calc.py", "def f():\n    return 4\n")
        scope = self.scope_file(runners)
        first = self.ledger("run-scope", "--root", str(self.root), "--scope-file", str(self.root / scope),
                            "--env-id", "e1")
        self.assertEqual(first["status"], "PASS")
        self.assertEqual(len(first["run_ids"]), 1)
        again = self.ledger("run-scope", "--root", str(self.root), "--scope-file", str(self.root / scope),
                            "--env-id", "e1")
        self.assertTrue(again["runs"][0]["reused"], "同树同命令同环境应复用 PASS")

    def test_failing_suite_is_fail_not_pass(self):
        runners = [{"suffixes": [".py"], "argv": [PY, "-B", "-m", "unittest", "{tests}"]}]
        self.write("src/calc.py", "def f():\n    return 'wrong type'\n")
        scope = self.scope_file(runners)
        out = self.ledger("run-scope", "--root", str(self.root), "--scope-file", str(self.root / scope),
                          "--env-id", "e1", expect=1)
        self.assertEqual(out["status"], "FAIL")

    def test_empty_scope_reports_empty_without_fake_run_id(self):
        self.write("docs/a.md", "changed\n")
        scope = self.scope_file([{"suffixes": [".py"], "argv": [PY, "-B", "-m", "unittest", "{tests}"]}])
        out = self.ledger("run-scope", "--root", str(self.root), "--scope-file", str(self.root / scope),
                          "--env-id", "e1")
        self.assertEqual(out["status"], "EMPTY")
        self.assertEqual(out["run_ids"], [])

    def test_record_review_accepts_sprint_runs_and_rejects_full(self):
        runners = [{"suffixes": [".py"], "argv": [PY, "-B", "-m", "unittest", "{tests}"]}]
        self.write("src/calc.py", "def f():\n    return 6\n")
        scope = self.scope_file(runners)
        ok = self.ledger("run-scope", "--root", str(self.root), "--scope-file", str(self.root / scope),
                         "--env-id", "e1")
        self.write("docs/testing/V1/sprint-001/report.md", "CVL 通过\n")
        args = ["record-review", "--root", str(self.root), "--name", "V1-sprint-001", "--env-id", "e1",
                "--report", "docs/testing/V1/sprint-001/report.md", "--input", scope,
                "--scope-file", scope, "--scope-hash", ok["scope_hash"]]
        for run_id in ok["run_ids"]:
            args += ["--run-id", run_id]
        self.assertEqual(self.ledger(*args)["kind"], "review")
        full = self.ledger("run", "--root", str(self.root), "--cwd", ".", "--scope", "full", "--env-id", "e1",
                           "--", PY, "-c", "pass")
        self.assertEqual(full["status"], "PASS")
        self.ledger("record-review", "--root", str(self.root), "--name", "bad", "--env-id", "e1",
                    "--report", "docs/testing/V1/sprint-001/report.md", "--run-id", full["run_id"],
                    "--scope-file", scope, "--scope-hash", ok["scope_hash"], expect=2)


class ScopeEvidenceTests(ScopeFixture):
    """真实 unittest 选择、跨树证据与输入绑定；不依赖 pytest。"""

    scope_file = RunScopeTests.scope_file

    def runners(self, **extra):
        return [{"suffixes": [".py"], "batch": False, "argv": [PY, "-B", "-m", "unittest", "{tests}"], **extra}]

    def execute(self, scope, expect=0, *extra):
        return self.ledger("run-scope", "--root", str(self.root), "--scope-file", scope,
                           "--env-id", "e1", *extra, expect=expect)

    def verify(self, scope, result, expect=0, ids=None):
        return self.ledger("verify", "--root", str(self.root), "--scope-file", scope,
                           "--scope-hash", result["scope_hash"], "--env-id", "e1",
                           *(arg for run_id in (result["run_ids"] if ids is None else ids)
                             for arg in ("--run-id", run_id)), expect=expect)

    def counting_suite(self, name, value):
        self.write(f"src/{name}.py", f"value = {value}\n")
        self.write(f"tests/test_{name}.py", (
            "import unittest\nfrom pathlib import Path\n"
            f"from src.{name} import value\n"
            "class ValueTests(unittest.TestCase):\n"
            "    def test_value(self):\n"
            f"        p = Path('memory/{name}-count')\n"
            "        p.parent.mkdir(exist_ok=True)\n"
            "        p.write_text(str(int(p.read_text())+1) if p.exists() else '1')\n"
            "        self.assertGreater(value, 0)\n"
            "        self.assertFalse(Path('memory/fail').exists())\n"))

    def test_only_affected_test_reruns_and_other_evidence_is_traceable(self):
        self.counting_suite("calc", 1)
        self.counting_suite("other", 1)
        scope = self.scope_file(self.runners())
        first = self.execute(scope)
        self.assertEqual(len(first["run_ids"]), 2)
        self.write("src/calc.py", "value = 2\n")
        # 过期文件不能直接运行，即使自己重算外部 hash 也不能绕过重推。
        self.execute(scope, 2)
        scope = self.scope_file(self.runners())
        second = self.execute(scope)
        self.assertEqual(second["status"], "CARRIED")
        self.assertEqual((self.root / "memory/calc-count").read_text(), "2")
        self.assertEqual((self.root / "memory/other-count").read_text(), "1")
        carried = next(r for r in second["runs"] if r["status"] == "CARRIED")
        self.assertIsNone(carried["exit_code"])
        self.assertIsNone(carried["after_hash"])
        self.assertIn(carried["source_run_id"], first["run_ids"])
        self.assertNotEqual(carried["source_tree_hash"], carried["assessment_hash"])
        self.assertEqual(self.verify(scope, second)["status"], "CARRIED")
        self.verify(scope, second, 2, ids=first["run_ids"])
        again = self.execute(scope)
        self.assertTrue(all(r["reused"] for r in again["runs"]))
        self.write("docs/review.md", "审查了增量变化与来源证据。")
        review = self.ledger("record-review", "--root", str(self.root), "--name", "r", "--env-id", "e1",
                             "--scope-file", scope, "--scope-hash", second["scope_hash"],
                             "--report", "docs/review.md",
                             *(arg for run_id in second["run_ids"] for arg in ("--run-id", run_id)))
        self.assertEqual(review["test_status"], "CARRIED")
        self.assertEqual(len(review["evidence"]), 2)

    def test_later_failure_invalidates_carried_evidence(self):
        self.counting_suite("calc", 1)
        self.counting_suite("other", 1)
        scope = self.scope_file(self.runners())
        self.execute(scope)
        self.write("src/calc.py", "value = 2\n")
        scope = self.scope_file(self.runners())
        carried = self.execute(scope)
        self.write("memory/fail", "fail")
        failed = self.execute(scope, 1, "--force")
        self.assertEqual(failed["status"], "FAIL")
        self.verify(scope, carried, 2)
        (self.root / "memory/fail").unlink()
        recovered = self.execute(scope)
        self.assertTrue(all(not r["reused"] and r["status"] == "PASS" for r in recovered["runs"]))

    def test_unknown_auxiliary_and_explicit_inputs_prevent_carry(self):
        self.counting_suite("calc", 1)
        self.counting_suite("other", 1)
        self.write("docs/fixture.json", "v1")
        runners = self.runners(inputs=["docs/fixture.json"])
        scope = self.scope_file(runners)
        self.execute(scope)
        self.write("docs/fixture.json", "v2")
        # 相同默认 tree_hash 下显式输入依然使两项实跑。
        scope = self.scope_file(runners)
        changed = self.execute(scope)
        self.assertTrue(all(r["status"] == "PASS" and not r["reused"] for r in changed["runs"]))
        self.write("src/shared.py", "shared = 2\n")
        scope = self.scope_file(runners)
        unknown = self.execute(scope)
        self.assertEqual(unknown["status"], "PARTIAL")
        self.assertTrue(all(r["status"] == "PASS" and not r["reused"] for r in unknown["runs"]))
        self.assertEqual((self.root / "memory/other-count").read_text(), "3")

    def test_tampered_scope_and_hash_are_rejected_before_execution(self):
        import test_scope
        self.write("src/calc.py", "def f(): return 2\n")
        scope = self.scope_file(self.runners())
        path = self.root / scope
        original = json.loads(path.read_text())
        for reseal in (False, True):
            tampered = dict(original, runs=[])
            if reseal:
                tampered["scope_hash"] = test_scope.digest({k: v for k, v in tampered.items() if k != "scope_hash"})
            path.write_text(json.dumps(tampered))
            self.execute(scope, 2)
            self.assertFalse(Path(ledger_path(self.root)).exists())
        path.write_text(json.dumps(original))
        result = self.execute(scope)
        result["scope_hash"] = "0" * 64
        self.verify(scope, result, 2)

    def test_verify_rejects_missing_duplicate_unbound_or_foreign_suite_ids(self):
        self.counting_suite("calc", 1)
        self.counting_suite("other", 1)
        scope = self.scope_file(self.runners())
        result = self.execute(scope)
        for ids in ([], result["run_ids"][:1], [result["run_ids"][0]] * 2, ["unknown"]):
            self.verify(scope, result, 2, ids=ids)
        unbound = self.ledger("run", "--root", str(self.root), "--scope", "sprint", "--env-id", "e1",
                              "--", PY, "-c", "pass")
        self.verify(scope, result, 2, ids=[unbound["run_id"], result["run_ids"][1]])

    def test_zero_corresponding_tests_records_minor_without_fake_pass(self):
        self.write("src/orphan.rs", "fn untouched() {}\n")
        scope = self.scope_file([])
        result = self.execute(scope)
        self.assertEqual(result["status"], "EMPTY")
        self.assertEqual(result["run_ids"], [])
        self.assertTrue(result["minor"])
        self.assertEqual(self.verify(scope, result)["status"], "EMPTY")
        self.write("docs/review.md", "无对应单测，已记录 Minor。")
        review = self.ledger("record-review", "--root", str(self.root), "--env-id", "e1", "--name", "empty",
                             "--scope-file", scope, "--scope-hash", result["scope_hash"], "--report", "docs/review.md")
        self.assertIsNone(review["run_id"])
        self.assertEqual(review["test_status"], "EMPTY")
        self.assertFalse(self.ledger("review-delta", "--root", str(self.root), "--env-id", "e1",
                                     "--name", "empty")["code_changed"])

    def test_unrunnable_tools_or_timeouts_are_unverified(self):
        self.write("src/calc.py", "def f(): return 2\n")
        scope = self.scope_file([])
        partial = self.execute(scope, 2)
        self.assertEqual(partial["status"], "UNVERIFIED")
        self.assertEqual(partial["unrunnable"], ["tests/test_calc.py"])
        self.verify(scope, partial, 2)
        self.write("docs/review.md", "Tests not executed.")
        self.ledger("record-review", "--root", str(self.root), "--env-id", "e1", "--name", "bad",
                    "--scope-file", scope, "--scope-hash", partial["scope_hash"], "--report", "docs/review.md", expect=2)
        for argv, extra in ((["/aidp-missing-tool", "{tests}"], ()),
                            ([PY, "-m", "aidp_missing_runner_module", "{tests}"], ()),
                            ([PY, "-c", "import time; time.sleep(5)", "{tests}"], ("--timeout", "0.05"))):
            scope = self.scope_file([{"suffixes": [".py"], "argv": argv}])
            result = self.execute(scope, 2, *extra)
            self.assertEqual(result["status"], "UNVERIFIED")
            self.assertEqual(result["runs"][0]["status"], "ERROR")

    def test_real_same_name_suites_run_in_each_module_cwd(self):
        runners = []
        for name in ("one", "two"):
            self.write(f"{name}/src/calc.py", "value = 1\n")
            self.write(f"{name}/tests/test_calc.py", (
                "import unittest\nfrom pathlib import Path\n"
                "class LocalTests(unittest.TestCase):\n"
                "    def test_module(self):\n"
                f"        self.assertEqual(Path.cwd().name, {name!r})\n"
                "        self.assertIn('value', Path('src/calc.py').read_text())\n"
                "if __name__ == '__main__': unittest.main()\n"))
            runners.append({"cwd": name, "suffixes": [".py"], "env_id": f"runtime-{name}",
                            "argv": [PY, "-B", "{tests}"]})
        scope = self.scope_file(runners)
        result = self.execute(scope)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(len(result["runs"]), 2)
        self.assertEqual(self.verify(scope, result)["status"], "PASS")
        self.write("one/src/calc.py", "value = 2\n")
        scope = self.scope_file(runners)
        changed = self.execute(scope)
        by_cwd = {Path(r["cwd"]).name: r for r in changed["runs"]}
        self.assertEqual(by_cwd["one"]["status"], "PASS")
        self.assertEqual(by_cwd["two"]["status"], "CARRIED")
        runners[0]["env_id"] = "runtime-one-new"
        scope = self.scope_file(runners)
        changed_env = self.execute(scope)
        by_cwd = {Path(r["cwd"]).name: r for r in changed_env["runs"]}
        self.assertEqual(by_cwd["one"]["status"], "PASS")
        self.assertEqual(by_cwd["two"]["status"], "CARRIED")
        self.assertEqual(self.verify(scope, changed_env)["status"], "CARRIED")

    def test_review_cli_and_python_reject_missing_scope_for_manual_pass(self):
        import test_ledger
        unbound = self.ledger("run", "--root", str(self.root), "--scope", "sprint", "--env-id", "e1",
                              "--", PY, "-c", "pass")
        self.write("docs/review.md", "manual pass is not acceptance")
        process = subprocess.run([PY, str(LEDGER), "record-review", "--root", str(self.root),
                                  "--env-id", "e1", "--name", "bad", "--run-id", unbound["run_id"],
                                  "--report", "docs/review.md"], capture_output=True, text=True)
        self.assertEqual(process.returncode, 2)
        self.assertIn("--scope-file", process.stderr)
        with self.assertRaises(test_ledger.LedgerError):
            test_ledger.record_review(self.root, "bad", unbound["run_id"], "e1", "docs/review.md")

    def test_carry_chain_requires_real_source_pass_and_valid_delta(self):
        import test_ledger
        self.counting_suite("calc", 1)
        self.counting_suite("other", 1)
        scope = self.scope_file(self.runners())
        first = self.execute(scope)
        for value in (2, 3):
            self.write("src/calc.py", f"value = {value}\n")
            scope = self.scope_file(self.runners())
            current = self.execute(scope)
            carried = next(r for r in current["runs"] if r["status"] == "CARRIED")
            self.assertIn(carried["source_run_id"], first["run_ids"])
            self.assertEqual(self.verify(scope, current)["status"], "CARRIED")
        rows = test_ledger.load(self.root)
        row = next(r for r in rows if r.get("run_id") == carried["run_id"])
        row["source_tree_hash"] = "bad-source"
        test_ledger.save(self.root, rows)
        self.verify(scope, current, 2)
        self.execute(scope, 2)

    def test_real_import_dependency_cannot_carry_a_when_b_has_own_test(self):
        self.write("b.py", "value = 1\n")
        self.write("a.py", "from b import value\ndef calculate(): return value\n")
        self.write("tests/test_a.py", "import unittest\nfrom a import calculate\n"
                   "class A(unittest.TestCase):\n def test_a(self): self.assertEqual(calculate(), 1)\n")
        self.write("tests/test_b.py", "import unittest\nfrom b import value\n"
                   "class B(unittest.TestCase):\n def test_b(self): self.assertGreater(value, 0)\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "dependency baseline")
        self.base = git(self.root, "rev-parse", "HEAD")
        self.write("a.py", "from b import value\ndef calculate(): return value\n# Sprint edit\n")
        scope = self.scope_file(self.runners())
        first = self.execute(scope)
        self.assertEqual(first["status"], "PASS")
        self.assertEqual([r["command"][-1] for r in first["runs"]], ["tests/test_a.py"])
        self.write("b.py", "value = 2\n")
        scope = self.scope_file(self.runners())
        command = [PY, str(LEDGER), "run-scope", "--root", str(self.root),
                   "--scope-file", scope, "--env-id", "e1"]
        normal = subprocess.run(command, capture_output=True, text=True)
        out = last_json(normal.stdout)
        verification = subprocess.run(
            [PY, str(LEDGER), "verify", "--root", str(self.root), "--scope-file", scope,
             "--scope-hash", out["scope_hash"], "--env-id", "e1",
             *(arg for value in out["run_ids"] for arg in ("--run-id", value))],
            capture_output=True, text=True)
        forced = subprocess.run([*command, "--force"], capture_output=True, text=True)
        diagnostics = {"normal": [(r["command"][-1], r["status"]) for r in out["runs"]],
                       "verify_exit": verification.returncode,
                       "force": last_json(forced.stdout)["status"]}
        self.assertEqual(forced.returncode, 1, forced.stdout + forced.stderr)
        self.assertEqual(normal.returncode, 1, json.dumps(diagnostics))
        self.assertEqual(verification.returncode, 2, verification.stdout)
        self.assertEqual(next(r for r in out["runs"] if r["command"][-1] == "tests/test_a.py")["status"], "FAIL")

    def test_transitive_imports_and_test_helpers_expand_sprint_write_set(self):
        import test_scope
        self.write("src/leaf.py", "value = 1\n")
        self.write("src/middle.py", "from .leaf import value\n")
        self.write("src/top.py", "import src.middle as m\ndef result(): return m.value\n")
        self.write("tests/helper.py", "from src.top import result\n")
        self.write("tests/test_behavior.py", "import unittest\nfrom tests.helper import result\n"
                   "class Behavior(unittest.TestCase):\n def test_value(self): self.assertEqual(result(), 1)\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "transitive baseline")
        self.base = git(self.root, "rev-parse", "HEAD")
        plan = test_scope.derive(self.root, self.base, self.runners(), ["src/leaf.py"])
        self.assertEqual(plan["tests"], ["tests/test_behavior.py"])
        proof = plan["dependencies"]["tests"]["tests/test_behavior.py"]
        self.assertEqual(proof["unknown"], [])
        self.assertTrue({"src/top.py", "src/middle.py", "src/leaf.py", "tests/helper.py"} <= set(proof["files"]))
        self.write("docs/transitive-scope.json", json.dumps(plan))
        self.assertEqual(self.execute("docs/transitive-scope.json")["status"], "PASS")
        self.write("src/leaf.py", "value = 2\n")
        scope = self.scope_file(self.runners())
        self.assertEqual(self.derive(self.runners())["tests"], ["tests/test_behavior.py"])
        failure = self.execute(scope, 1)
        self.assertEqual(failure["runs"][0]["status"], "FAIL")
        self.verify(scope, failure, 2)

    def test_sibling_module_shared_source_cannot_be_assumed_independent(self):
        runners = self.runners()
        for name in ("one", "two"):
            self.write(f"{name}/__init__.py", "")
            self.write(f"{name}/tests/__init__.py", "")
            self.write(f"{name}/src/__init__.py", "")
            self.write(f"{name}/src/local.py", "value = 1\n")
            self.write(f"{name}/tests/test_local.py", (
                f"import unittest\nfrom {name}.src.local import value\n"
                "class Local(unittest.TestCase):\n def test_value(self): self.assertGreater(value, 0)\n"))
        # 子模块由构建清单确定，根运行器允许真实跨模块 import。
        self.write("one/pyproject.toml", "")
        self.write("two/pyproject.toml", "")
        self.write("one/src/shared.py", "value = 1\n")
        self.write("one/tests/test_shared.py", "import unittest\nfrom one.src.shared import value\n"
                   "class Shared(unittest.TestCase):\n def test_value(self): self.assertGreater(value, 0)\n")
        self.write("two/src/local.py", "from one.src.shared import value\n")
        scope = self.scope_file(runners)
        self.assertEqual(self.execute(scope)["status"], "PASS")
        self.write("one/src/shared.py", "value = -1\n")
        scope = self.scope_file(runners)
        second = self.execute(scope, 1)
        states = {r["command"][-1]: r["status"] for r in second["runs"]}
        self.assertEqual(states["one/tests/test_shared.py"], "FAIL")
        self.assertEqual(states["two/tests/test_local.py"], "FAIL")
        self.assertEqual(states["one/tests/test_local.py"], "CARRIED")
        self.verify(scope, second, 2)

    def test_multirunner_env_and_inputs_only_invalidate_owner(self):
        runners = []
        for name in ("one", "two"):
            self.write(f"{name}/src/calc.py", "value = 1\n")
            self.write(f"{name}/tests/__init__.py", "")
            self.write(f"{name}/tests/test_calc.py", "import unittest\nfrom src.calc import value\n"
                       "class Local(unittest.TestCase):\n def test_value(self): self.assertGreater(value, 0)\n")
            self.write(f"docs/{name}.json", "1")
            runners.append({"cwd": name, "suffixes": [".py"], "env_id": name,
                            "inputs": [f"docs/{name}.json"],
                            "argv": [PY, "-B", "-m", "unittest", "{tests}"]})
        scope = self.scope_file(runners)
        self.execute(scope)
        for mutate in (lambda: runners[0].update(env_id="one-new"),
                       lambda: self.write("docs/one.json", "2"),
                       lambda: runners[0].update(inputs=["docs/one.json", "docs/two.json"])):
            mutate()
            scope = self.scope_file(runners)
            out = self.execute(scope)
            states = {Path(r["cwd"]).name: r["status"] for r in out["runs"]}
            self.assertEqual(states, {"one": "PASS", "two": "CARRIED"})
            self.assertEqual(self.verify(scope, out)["status"], "CARRIED")

    def test_dynamic_dependency_is_recorded_and_never_carried(self):
        self.write("src/b.py", "value = 1\n")
        self.write("tests/test_dynamic.py", "import unittest\nimport importlib\n"
                   "class Dynamic(unittest.TestCase):\n"
                   " def test_value(self): self.assertEqual(importlib.import_module('src.b').value, 1)\n")
        scope = self.scope_file(self.runners())
        first = self.execute(scope)
        self.assertEqual(first["status"], "PARTIAL")
        plan = json.loads((self.root / scope).read_text())
        self.assertTrue(plan["dependencies"]["tests"]["tests/test_dynamic.py"]["unknown"])
        self.write("src/b.py", "value = 2\n")
        scope = self.scope_file(self.runners())
        failed = self.execute(scope, 1)
        self.assertEqual(failed["runs"][0]["status"], "FAIL")
        self.verify(scope, failed, 2)

    def test_runner_environment_identity_changes_key(self):
        self.write("src/calc.py", "def f(): return 2\n")
        scope = self.scope_file(self.runners(env_id="python-a"))
        first = self.execute(scope)
        scope = self.scope_file(self.runners(env_id="python-b"))
        second = self.execute(scope)
        self.assertNotEqual(first["runs"][0]["key"], second["runs"][0]["key"])
        self.assertFalse(second["runs"][0]["reused"])
        self.assertEqual(self.verify(scope, second)["status"], "PASS")


class TaskScopeTests(ScopeFixture):
    """无 Sprint 的真实任务范围、续跑和独立审查证据。"""

    def context(self, **kwargs):
        import entry_context
        return entry_context.resolve_context(self.root, "sprint-dev", version="V1",
            additional_grants=["related-test", "review"],
            authorization_source={"kind": "user-text", "request_id": "scope-fixture", "text": "运行专项测试并审查"},
            **kwargs)["execution_context"]

    def task_scope(self, context, runners=None):
        runners = runners if runners is not None else [
            {"suffixes": [".py"], "batch": False, "argv": [PY, "-B", "-m", "unittest", "{tests}"]}]
        p = subprocess.run([PY, str(SCOPE), "--root", str(self.root), "--execution-context", context,
                            "--runners-json", json.dumps(runners), "--json"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        plan = json.loads(p.stdout)
        path = Path(context).parent / "scope.json"
        path.write_text(json.dumps(plan))
        return str(path), plan

    def execute_task(self, context, scope, expect=0, *extra):
        return self.ledger("run-scope", "--root", str(self.root), "--execution-context", context,
                           "--scope-file", scope, "--env-id", "e1", *extra, expect=expect)

    def verify_task(self, context, scope, result, expect=0):
        return self.ledger("verify", "--root", str(self.root), "--execution-context", context,
                           "--scope-file", scope, "--scope-hash", result["scope_hash"], "--env-id", "e1",
                           *(arg for value in result["run_ids"] for arg in ("--run-id", value)), expect=expect)

    def test_no_sprint_task_reuses_only_its_own_evidence(self):
        first_context, second_context = self.context(), self.context()
        self.write("src/calc.py", "def f(): return 2\n")
        first_scope, first_plan = self.task_scope(first_context)
        second_scope, second_plan = self.task_scope(second_context)
        self.assertNotEqual(first_plan["scope_hash"], second_plan["scope_hash"])
        self.assertNotIn("sprint", first_plan["execution_context"])
        self.assertEqual(first_plan["since"], self.base)
        first = self.execute_task(first_context, first_scope)
        self.assertEqual(first["kind"], "task-run-set")
        self.assertEqual(first["runs"][0]["scope"], "task")
        self.assertTrue(self.execute_task(first_context, first_scope)["runs"][0]["reused"])
        second = self.execute_task(second_context, second_scope)
        self.assertFalse(second["runs"][0]["reused"])
        self.assertNotEqual(first["runs"][0]["key"], second["runs"][0]["key"])
        self.verify_task(second_context, second_scope, dict(second, run_ids=first["run_ids"]), expect=2)
        self.verify_task(first_context, first_scope, first)
        self.execute_task(second_context, first_scope, expect=2)
        self.ledger("run-scope", "--root", str(self.root), "--scope-file", first_scope, "--env-id", "e1", expect=2)
        formal_plan = self.derive(first_plan["runners"])
        self.write("memory/formal-scope.json", json.dumps(formal_plan))
        formal = self.ledger("run-scope", "--root", str(self.root), "--scope-file", "memory/formal-scope.json",
                             "--env-id", "e1")
        self.verify_task(first_context, first_scope, dict(first, run_ids=formal["run_ids"]), expect=2)
        self.ledger("verify", "--root", str(self.root), "--scope-file", "memory/formal-scope.json",
                    "--scope-hash", formal["scope_hash"], "--env-id", "e1", "--run-id", first["run_ids"][0], expect=2)

    def test_preexisting_dirty_is_excluded_until_changed_or_declared(self):
        self.write("src/calc.py", "def f(): return 2\n")
        context = self.context()
        _, initial = self.task_scope(context)
        self.assertEqual(initial["changed"], [])
        self.assertEqual(initial["runs"], [])
        self.write("src/calc.py", "def f(): return 3\n")
        _, changed = self.task_scope(context)
        self.assertEqual(changed["changed"], ["src/calc.py"])
        declared = self.context(write_set=["src/calc.py"])
        _, selected = self.task_scope(declared)
        self.assertEqual(selected["tests"], ["tests/test_calc.py"])
        self.write("src/calc.py", "def f():\n    return 1\n")
        self.assertEqual(git(self.root, "diff", "--name-only", "HEAD"), "")
        _, restored = self.task_scope(context)
        self.assertEqual(restored["changed"], ["src/calc.py"])
        self.assertEqual(restored["tests"], ["tests/test_calc.py"])

    def test_failure_pending_and_missing_runs_never_verify(self):
        self.write("tests/test_calc.py", "import unittest\nfrom pathlib import Path\n"
                   "class CalcTests(unittest.TestCase):\n"
                   " def test_ok(self): self.assertFalse(Path('memory/fail').exists())\n")
        context = self.context(write_set=["src/calc.py"])
        scope, _ = self.task_scope(context)
        first = self.execute_task(context, scope)
        self.verify_task(context, scope, dict(first, run_ids=[]), expect=2)
        self.write("memory/fail", "fail")
        failed = self.execute_task(context, scope, 1, "--force")
        self.assertEqual(failed["status"], "FAIL")
        self.verify_task(context, scope, first, expect=2)
        self.verify_task(context, scope, failed, expect=2)
        (self.root / "memory/fail").unlink()
        recovered = self.execute_task(context, scope)
        self.assertFalse(recovered["runs"][0]["reused"])
        import test_ledger
        rows = test_ledger.load(self.root)
        pending = dict(rows[-1], run_id="pending-task-run", status="RUNNING", exit_code=None, after_hash=None)
        test_ledger.save(self.root, [*rows, pending])
        self.verify_task(context, scope, recovered, expect=2)

    def test_task_review_is_machine_json_and_cannot_be_test_pass(self):
        import entry_context
        first_context, second_context = self.context(), self.context()
        self.write("src/calc.py", "def f(): return 2\n")
        scope, plan = self.task_scope(first_context)
        result = self.execute_task(first_context, scope)
        report = str(Path(first_context).parent / "review.json")
        args = ["record-review", "--root", str(self.root), "--name", "same-name", "--env-id", "e1",
                "--execution-context", first_context, "--scope-file", scope, "--scope-hash", plan["scope_hash"],
                "--report", report, "--run-id", result["run_ids"][0]]
        Path(report).write_text(json.dumps(result))
        self.ledger(*args, expect=2)
        review = {"schema": 1, "kind": "code-review", "status": "PASS", "scope_hash": plan["scope_hash"],
                  "execution_context": entry_context.evidence_identity(entry_context.load_context(self.root, first_context)),
                  "reviewer": "review-agent", "findings": [],
                  "checks": [{"kind": "code-review", "status": "PASS", "evidence": ["src/calc.py:1 f returns int"]}]}
        Path(report).write_text(json.dumps(review))
        recorded = self.ledger(*args)
        delta = self.ledger("review-delta", "--root", str(self.root), "--name", "same-name", "--env-id", "e1",
                            "--execution-context", first_context)
        self.assertEqual(recorded["review_id"], delta["review_id"])
        self.assertFalse(delta["code_changed"])
        self.ledger("review-delta", "--root", str(self.root), "--name", "same-name", "--env-id", "e1",
                    "--execution-context", second_context, expect=2)
        self.ledger("review-delta", "--root", str(self.root), "--name", "same-name", "--env-id", "e1", expect=2)
        self.assertFalse((self.root / "docs/testing").exists())
        review["checks"][0]["status"] = "UNVERIFIED"
        Path(report).write_text(json.dumps(review))
        self.ledger(*args, expect=2)

    def test_task_carry_preserves_real_source_and_dependency_proof(self):
        ScopeEvidenceTests.counting_suite(self, "calc", 1)
        ScopeEvidenceTests.counting_suite(self, "other", 1)
        context = self.context(write_set=["src/calc.py", "src/other.py"])
        scope, _ = self.task_scope(context)
        first = self.execute_task(context, scope)
        self.write("src/calc.py", "value = 2\n")
        scope, _ = self.task_scope(context)
        second = self.execute_task(context, scope)
        carried = next(r for r in second["runs"] if r["status"] == "CARRIED")
        self.assertIn(carried["source_run_id"], first["run_ids"])
        self.assertIsNone(carried["exit_code"])
        self.assertIsNone(carried["after_hash"])
        self.assertEqual((self.root / "memory/other-count").read_text(), "1")
        self.assertEqual(self.verify_task(context, scope, second)["status"], "CARRIED")

    def test_formal_context_remains_sprint_and_isolated_from_legacy(self):
        import entry_context
        context = self.context(sprint="001", write_set=["src/calc.py"])
        scope, _ = self.task_scope(context)
        out = self.execute_task(context, scope)
        self.assertEqual(out["kind"], "sprint-run-set")
        self.assertEqual(out["runs"][0]["scope"], "sprint")
        self.assertEqual(self.verify_task(context, scope, out)["kind"], "sprint-verification")
        self.ledger("verify", "--root", str(self.root), "--scope-file", scope, "--scope-hash", out["scope_hash"],
                    "--env-id", "e1", "--run-id", out["run_ids"][0], expect=2)

    def test_unrunnable_and_no_git_tasks_fail_closed(self):
        context = self.context(write_set=["src/calc.py"])
        scope, _ = self.task_scope(context, runners=[])
        out = self.execute_task(context, scope, expect=2)
        self.assertEqual(out["status"], "UNVERIFIED")
        self.verify_task(context, scope, out, expect=2)
        shutil.rmtree(self.root / ".git")
        no_git = self.context()
        p = subprocess.run([PY, str(SCOPE), "--root", str(self.root), "--execution-context", no_git, "--json"],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.ledger("run", "--root", str(self.root), "--execution-context", no_git, "--scope", "task",
                    "--env-id", "e1", "--", PY, "-c", "pass", expect=2)

    def test_submodule_tasks_expand_files_isolate_evidence_and_reject_missing_checkout(self):
        source = self.tmp / "submodule-source"
        source.mkdir()
        git(source, "init", "-q")
        git(source, "config", "user.email", "t@example.invalid")
        git(source, "config", "user.name", "t")
        for name, text in {
            "pyproject.toml": "",
            "src/calc.py": "value = 1\n",
            "tests/__init__.py": "",
            "tests/test_calc.py": "import unittest\nfrom src.calc import value\n"
                                  "class Calc(unittest.TestCase):\n def test_value(self): self.assertGreater(value, 0)\n",
        }.items():
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        git(source, "add", "-A")
        git(source, "commit", "-qm", "submodule baseline")
        git(self.root, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(source), "vendor/pkg")
        git(self.root, "commit", "-qam", "parent gitlink")
        self.base = git(self.root, "rev-parse", "HEAD")
        self.write("vendor/pkg/src/calc.py", "value = 2\n")  # 任务开始前已有的子模块 dirty。
        first_context, second_context = self.context(), self.context()
        runners = [{"cwd": "vendor/pkg", "suffixes": [".py"],
                    "argv": [PY, "-B", "-m", "unittest", "{tests}"]}]
        _, initial = self.task_scope(first_context, runners)
        self.assertEqual(initial["changed"], [])
        declared = self.context(write_set=["vendor/pkg/src"])
        _, explicit = self.task_scope(declared, runners)
        self.assertEqual(explicit["tests"], ["vendor/pkg/tests/test_calc.py"])
        self.write("vendor/pkg/src/calc.py", "value = 3\n")
        first_scope, first_plan = self.task_scope(first_context, runners)
        second_scope, second_plan = self.task_scope(second_context, runners)
        self.assertEqual(first_plan["changed"], ["vendor/pkg/src/calc.py"])
        self.assertEqual(first_plan["tests"], ["vendor/pkg/tests/test_calc.py"])
        self.assertNotEqual(first_plan["scope_hash"], second_plan["scope_hash"])
        first = self.execute_task(first_context, first_scope)
        second = self.execute_task(second_context, second_scope)
        self.assertEqual(first["status"], "PASS")
        self.assertFalse(second["runs"][0]["reused"])
        self.assertTrue(self.execute_task(first_context, first_scope)["runs"][0]["reused"])
        self.verify_task(first_context, first_scope, first)
        self.verify_task(second_context, second_scope, dict(second, run_ids=first["run_ids"]), expect=2)
        shutil.rmtree(self.root / "vendor/pkg")
        (self.root / "vendor/pkg").mkdir()
        p = subprocess.run([PY, str(SCOPE), "--root", str(self.root), "--execution-context", first_context,
                            "--runners-json", json.dumps(runners), "--json"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertEqual(json.loads(p.stdout)["kind"], "error")
        self.execute_task(first_context, first_scope, expect=2)
        self.verify_task(first_context, first_scope, first, expect=2)

    def test_context_baseline_and_write_set_cannot_be_overridden(self):
        context = self.context(write_set=["src/calc.py"])
        for extra in (["--since", "missing"], ["--write-set", "web/card.tsx"]):
            p = subprocess.run([PY, str(SCOPE), "--root", str(self.root), "--execution-context", context,
                                *extra, "--json"], capture_output=True, text=True)
            self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.ledger("run", "--root", str(self.root), "--execution-context", context, "--scope", "sprint",
                    "--env-id", "e1", "--", PY, "-c", "pass", expect=2)
        self.ledger("run", "--root", str(self.root), "--scope", "task", "--env-id", "e1",
                    "--", PY, "-c", "pass", expect=2)


class WorktreeLedgerTests(ScopeFixture):
    """全量单测在 build worktree 执行；账本留专属 build 缓存，worktree 删除后仍可复用。"""

    def test_full_run_in_detached_worktree_reuses_across_ticks_after_cleanup(self):
        wt = self.tmp / "wt"
        cache = self.tmp / "build-ledger" / self.base
        git(self.root, "worktree", "add", "--detach", str(wt), self.base)
        try:
            self.write("src/calc.py", "def f():\n    return 9\n")  # 主工作区改动不得影响 build 树结果
            argv = [PY, str(LEDGER), "run", "--root", str(wt), "--cwd", ".", "--scope", "full",
                    "--env-id", f"aiauto-unit:{self.base}", "--ledger-root", str(cache),
                    "--", PY, "-c", "pass"]
            first = last_json(subprocess.run(argv, capture_output=True, text=True).stdout)
            self.assertEqual(first["status"], "PASS")
            self.assertFalse(first["reused"])
        finally:
            git(self.root, "worktree", "remove", "--force", str(wt))
        # 临时 worktree 已删除，专属 build 账本仍在，主仓 Sprint 账本保持隔离。
        self.assertTrue(Path(ledger_path(cache)).exists())
        self.assertFalse(Path(ledger_path(self.root)).exists())
        self.assertFalse((wt / "memory/.aidp/test-ledger.jsonl").exists())
        # 重建同一 detached worktree（同 commit、同树）后复用专属缓存里的 PASS
        git(self.root, "worktree", "add", "--detach", str(wt), self.base)
        try:
            argv = [PY, str(LEDGER), "run", "--root", str(wt), "--cwd", ".", "--scope", "full",
                    "--env-id", f"aiauto-unit:{self.base}", "--ledger-root", str(cache),
                    "--", PY, "-c", "pass"]
            again = last_json(subprocess.run(argv, capture_output=True, text=True).stdout)
            self.assertTrue(again["reused"], again)
        finally:
            git(self.root, "worktree", "remove", "--force", str(wt))


class FullScopeConfinementTests(unittest.TestCase):
    """全量单测（--scope full）只属于 /sprint-aiauto-test；Sprint 级与部署前门禁一律用 sprint。"""

    def test_full_scope_is_not_a_sprint_or_deploy_gate(self):
        offenders = []
        for base in (ROOT / ".aidp/commands", ROOT / ".aidp/flows"):
            for path in base.rglob("*.md"):
                rel = path.relative_to(ROOT).as_posix()
                if "sprint-aiauto-test" in rel:
                    continue
                if "--scope full" in path.read_text(encoding="utf-8"):
                    offenders.append(rel)
        self.assertEqual(offenders, [], "Sprint 级 / 部署前门禁不得使用 --scope full")


if __name__ == "__main__":
    unittest.main(verbosity=2)
