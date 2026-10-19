#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""约定 22 里程碑卡片矩阵回归。"""
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
PATH = ROOT / ".aidp/scripts/ceremony_cards.py"
spec = importlib.util.spec_from_file_location("ceremony_cards", PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class CeremonyCardsTest(unittest.TestCase):
    def test_full_static_only(self):
        self.assertEqual(mod.expected_cards("full", deployed=False), ["#0", "#1b", "#1c", "#3", "#2"])

    def test_full_deployed(self):
        self.assertEqual(mod.expected_cards("full", deployed=True), ["#0", "#1b", "#1c", "#1d", "#2"])

    def test_incremental_has_no_sprint_close(self):
        self.assertEqual(mod.expected_cards("incremental", deployed=False), ["#0", "#1b", "#1c", "#3"])
        self.assertNotIn("#2", mod.expected_cards("incremental", deployed=True))

    def test_test_only_has_no_development_cards(self):
        self.assertEqual(mod.expected_cards("test-only", deployed=False), [])
        self.assertEqual(mod.expected_cards("test-only", deployed=True), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
