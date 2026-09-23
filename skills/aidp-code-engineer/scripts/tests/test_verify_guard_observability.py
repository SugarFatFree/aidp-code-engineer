#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify 守卫编排的可观测性与超时治理。

## 为什么需要本套件

下游实测：verify 在外层 120s 限额下被杀，**零线索** —— 既不知道跑到第几个守卫、
也不知道是哪个卡住。原因是 38 个守卫在一个裸 for 里串行跑，单守卫 180s 上限、总时长无上限，
而超时被 `except Exception` 一把吞成「执行失败」，连守卫名和阈值都丢了。

这里钉死四件事：带值 flag 不被当成位置参数、总时限到点要给三段清单、
`--json` 必须是纯 JSON、`--no-guards` 不得被说成「完整合规检查通过」。
"""
import json
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parents[2]
sys.path.insert(0, str(SCRIPTS))

import verify as V  # noqa: E402


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPTS / "verify.py"), str(REPO),
                           "--template", "--read-only", *args],
                          capture_output=True, text=True)


class ValueFlagParsingTest(unittest.TestCase):
    def test_value_flags_are_not_mistaken_for_positionals(self):
        # ★ main 按「不以 -- 开头」抽位置参数。带值 flag 不从 argv 删掉的话，
        #   `--guard-timeout 60` 的 60 会被当成 <version> 传进去 —— 症状是莫名其妙的用法错，
        #   且只在**用了新 flag 时**才出现，最容易漏测。
        p = run("--guard-timeout", "60", "--total-timeout", "600")
        self.assertEqual(p.returncode, 0, p.stdout[-800:] + p.stderr[-800:])
        self.assertNotIn("这里要项目业务版本号", p.stdout)

    def test_non_numeric_value_is_rejected(self):
        p = run("--guard-timeout", "abc")
        self.assertEqual(p.returncode, 2)
        self.assertIn("--guard-timeout", p.stdout)


class TotalTimeoutTest(unittest.TestCase):
    def test_total_timeout_lists_done_and_pending(self):
        p = run("--total-timeout", "1")
        text = p.stdout + p.stderr
        self.assertIn("守卫总时限", text)
        self.assertIn("已完成", text)
        self.assertIn("未执行", text)
        # ★ 必须非零退出：到点即停是「没查完」，不是「查过了都通过」。
        self.assertNotEqual(p.returncode, 0)


class JsonOutputTest(unittest.TestCase):
    def test_json_is_pure_json_and_carries_per_guard_timing(self):
        p = run("--json", "--guard-timeout", "120")
        # ★ 纯 JSON：混进人读抬头会让调用方的 json.loads 当场炸（下游正是机器消费）。
        data = json.loads(p.stdout)
        self.assertEqual(data["scope"], "full")
        self.assertTrue(data["guards"], "guards 为空 —— 派发循环没留痕")
        for guard in data["guards"]:
            self.assertIn(guard["status"], {"ok", "warn", "error", "not-run"})
            self.assertGreaterEqual(guard["seconds"], 0)
        self.assertIn("check_flow_bash_syntax", {g["name"] for g in data["guards"]})

    def test_no_guards_is_labelled_structure_only(self):
        # ⛔ --no-guards 的结论只是结构检查，上层报告不得据此宣称「完整合规检查完成」。
        data = json.loads(run("--json", "--no-guards").stdout)
        self.assertEqual(data["scope"], "structure-only")
        self.assertTrue(data["no_guards"])
        self.assertEqual(data["guards"], [])


class ProgressProbeRobustnessTest(unittest.TestCase):
    def test_isatty_failure_does_not_break_verify(self):
        # ★ 回归：为了决定"要不要打进度"而调 sys.stdout.isatty()，遇到不实现该方法的代理流
        #   （GBK 降级流 / 日志捕获 / _SafeConsole）会 AttributeError，把整次检查炸掉 ——
        #   与缺陷 D「检查跑完却死在输出上」同一类错误。
        import io

        class NoIsatty(io.StringIO):
            def isatty(self):
                raise AttributeError("probe")

        saved = sys.stdout
        sys.stdout = NoIsatty()
        try:
            code = V.main([str(REPO), "--template", "--read-only", "--no-guards"])
        finally:
            sys.stdout = saved
        self.assertEqual(code, 0)


class GuardTimeoutAttributionTest(unittest.TestCase):
    def test_timeout_carries_guard_name_and_threshold(self):
        # 用 0 秒阈值逼真实守卫超时：错误文案必须带阈值，调用方才知道该调哪个参数。
        _data, err = V._run_guard(REPO, "check_flow_shell_escapes", timeout=0.001)
        self.assertIsNotNone(err, "0.001s 阈值下竟然没超时 —— 断言失效")
        self.assertIn("超时", err)
        self.assertIn("--guard-timeout", err)

    def test_normal_exit_codes_still_pass_through(self):
        # ★ 阳性对照：把超时单列出来之后，正常的 0/1 退出码必须原样可用，
        #   否则等于把所有守卫的结果都吞了。
        data, err = V._run_guard(REPO, "check_flow_shell_escapes")
        self.assertIsNone(err, err)
        self.assertIsInstance(data, dict)


if __name__ == "__main__":
    unittest.main()
