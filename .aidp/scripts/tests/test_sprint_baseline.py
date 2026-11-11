#!/usr/bin/env python3
"""改动前基线 baseline_ref 解析：契约卡 → 上游透传 → 工作区未提交 → merge-base（≠HEAD）→ none。"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]
SCRIPT = SCRIPTS / "sprint_baseline.py"


class SprintBaselineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aidp-baseline-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-q", "-b", "main")
        self.commit("a.txt", "1\n", "c1")
        self.c1 = self.rev("HEAD")

    def git(self, *args, check=True):
        return subprocess.run(["git", "-C", str(self.root), "-c", "user.name=P", "-c", "user.email=p@example.invalid",
                               *args], check=check, capture_output=True, text=True).stdout

    def rev(self, ref):
        return self.git("rev-parse", ref).strip()

    def commit(self, name, text, msg):
        (self.root / name).write_text(text, encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-qm", msg)

    def resolve(self, *extra):
        r = subprocess.run([sys.executable, str(SCRIPT), "resolve", "--root", str(self.root), "--json", *extra],
                           capture_output=True, text=True)
        return r.returncode, json.loads(r.stdout)

    def test_card_ref_wins_when_ancestor(self):
        self.commit("b.txt", "2\n", "c2")
        rc, out = self.resolve("--card-ref", self.c1, "--passthrough", self.rev("HEAD"))
        self.assertEqual((rc, out["baseline_ref"], out["source"]), (0, self.c1, "contract-card"))

    def test_invalid_card_falls_to_passthrough(self):
        self.commit("b.txt", "2\n", "c2")
        rc, out = self.resolve("--card-ref", "0" * 40, "--passthrough", self.c1)
        self.assertEqual((out["baseline_ref"], out["source"]), (self.c1, "passthrough"))

    def test_non_ancestor_candidate_rejected(self):
        self.git("checkout", "-qb", "side")
        self.commit("s.txt", "s\n", "side")
        side = self.rev("HEAD")
        self.git("checkout", "-q", "main")
        self.commit("b.txt", "2\n", "c2")
        rc, out = self.resolve("--card-ref", side)
        self.assertEqual(out["baseline_ref"], "none")

    def test_worktree_only_uses_head_only_when_dirty_and_declared(self):
        rc, out = self.resolve("--sprint-uncommitted")
        self.assertEqual(out["baseline_ref"], "none")  # 工作区干净：声明不成立，不得取 HEAD
        (self.root / "a.txt").write_text("changed\n", encoding="utf-8")
        rc, out = self.resolve("--sprint-uncommitted")
        self.assertEqual((out["baseline_ref"], out["source"]), (self.c1, "worktree-only-HEAD"))

    def test_merge_base_on_trunk_is_rejected(self):
        self.commit("b.txt", "2\n", "c2")
        rc, out = self.resolve("--main-branch", "main")
        self.assertEqual(out["baseline_ref"], "none")
        self.assertEqual(rc, 3)
        self.assertEqual(out["unverified_label"], "基线无效：未取到 Sprint 起点 commit")

    def test_merge_base_on_feature_branch(self):
        self.git("checkout", "-qb", "feat")
        self.commit("b.txt", "2\n", "c2")
        rc, out = self.resolve("--main-branch", "main")
        self.assertEqual((rc, out["baseline_ref"], out["source"]), (0, self.c1, "merge-base"))

    def test_no_vcs_returns_none_with_unsupported_label(self):
        with tempfile.TemporaryDirectory(prefix="aidp-nogit-") as d:
            r = subprocess.run([sys.executable, str(SCRIPT), "resolve", "--root", d, "--json"],
                               capture_output=True, text=True)
            out = json.loads(r.stdout)
            self.assertEqual((out["baseline_ref"], out["vcs_mode"], out["unverified_label"]),
                             ("none", "none", "unsupported:vcs-disabled"))

    def test_option_like_ref_rejected(self):
        rc, out = self.resolve("--card-ref=--output=x")
        self.assertEqual(out["baseline_ref"], "none")


if __name__ == "__main__":
    unittest.main()
