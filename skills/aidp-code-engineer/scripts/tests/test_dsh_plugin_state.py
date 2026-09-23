#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DSH 扩展安装的**状态机**回归（缺陷 E）。

下游实况：Windows 上 `dsh` 是 PowerShell 侧的 shim，Python 子进程一句 `OSError [WinError 2]`
就找不到它；而同一台机器 `dsh --version` = 0.1.5-rc.2、`dsh plugin --profile web list` 里
明明有 `dsh-agent-extension@0.1.4`。旧实现「跑一次 add，失败就 warn 并返回 unavailable」把
**本进程调不起 dsh** 误读成 **扩展没装**。

本文件全部用 mock 的假 `dsh`（PATH 隔离），⛔ 不依赖本机真有 dsh；断言落在
`install_dsh_command_plugin` 的返回状态、是否真的执行了 add、以及输出文案上。
"""
import json
import os
import shutil
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

import _helpers as H          # noqa: F401  （统一把 scripts/ 挂进 sys.path 并校验仓库根）
import scaffold as S

# ⛔ 不能写 `#!/usr/bin/env python3`：用例把 PATH 收窄到只剩假 dsh，`env` 就找不到解释器了。
FAKE_DSH = "#!" + sys.executable + "\n" + textwrap.dedent('''
    """假 dsh：行为完全由环境变量驱动，用于复现下游各种探测结果。"""
    import json, os, sys

    argv = sys.argv[1:]
    log = os.environ.get("DSH_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(" ".join(argv) + "\\n")

    state_file = os.environ["DSH_STATE"]
    state = json.loads(open(state_file, encoding="utf-8").read())

    if argv[:1] == ["--version"]:
        code = int(os.environ.get("DSH_VERSION_EXIT", "0"))
        if code:
            sys.stderr.write("dsh: cannot initialise profile\\n")
        else:
            sys.stdout.write(state.get("version", "0.1.5-rc.2") + "\\n")
        sys.exit(code)

    if "list" in argv:
        code = int(os.environ.get("DSH_LIST_EXIT", "0"))
        if code:
            sys.stderr.write("dsh: profile locked\\n")
            sys.exit(code)
        if "--json" in argv:
            if os.environ.get("DSH_JSON", "0") != "1":
                sys.stderr.write("error: unexpected argument '--json'\\n")
                sys.exit(2)
            sys.stdout.write(json.dumps(
                {"plugins": [{"name": n.split("@")[0], "version": n.split("@")[-1]}
                             for n in state["installed"]]}) + "\\n")
            sys.exit(0)
        # 人读表格：带表头、分隔线、多余列，解析必须容错
        sys.stdout.write("NAME                      VERSION   PROFILE\\n")
        sys.stdout.write("------------------------  --------  -------\\n")
        for name in state["installed"]:
            stem, _, version = name.partition("@")
            sys.stdout.write("%-26s%-10s%s\\n" % (stem + "@" + version, version, "web"))
        sys.exit(0)

    if "add" in argv:
        code = int(os.environ.get("DSH_ADD_EXIT", "0"))
        if code:
            sys.stderr.write("dsh: plugin install failed\\n")
            sys.exit(code)
        if os.environ.get("DSH_ADD_EFFECT", "install") == "install":
            state["installed"].append("dsh-agent-extension@0.1.4")
            open(state_file, "w", encoding="utf-8").write(json.dumps(state))
        sys.exit(0)

    sys.stderr.write("dsh: unknown command\\n")
    sys.exit(2)
''').lstrip()


class DshHarness:
    """with DshHarness(installed=[...]) as dsh: …  —— PATH 只暴露假 dsh。"""

    def __init__(self, installed=(), present=True, **env):
        self.installed = list(installed)
        self.present = present
        self.extra_env = env

    def __enter__(self):
        self._tmp = tempfile.mkdtemp()
        base = Path(self._tmp)
        self.bindir = base / "bin"
        self.bindir.mkdir()
        self.log = base / "argv.log"
        self.state = base / "state.json"
        self.state.write_text(json.dumps({"installed": self.installed}), encoding="utf-8")
        if self.present:
            script = self.bindir / "dsh"
            script.write_text(FAKE_DSH, encoding="utf-8")
            script.chmod(0o755)
        self._saved = {k: os.environ.get(k) for k in
                       ("PATH", "DSH_LOG", "DSH_STATE", "DSH_JSON", "DSH_VERSION_EXIT",
                        "DSH_LIST_EXIT", "DSH_ADD_EXIT", "DSH_ADD_EFFECT")}
        os.environ["PATH"] = str(self.bindir)
        os.environ["DSH_LOG"] = str(self.log)
        os.environ["DSH_STATE"] = str(self.state)
        for key, value in self.extra_env.items():
            os.environ[key] = str(value)
        return self

    def __exit__(self, *exc):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        for key in self.extra_env:
            os.environ.pop(key, None)
        shutil.rmtree(self._tmp, ignore_errors=True)

    @property
    def calls(self):
        if not self.log.is_file():
            return []
        return [line for line in self.log.read_text(encoding="utf-8").splitlines() if line]

    @property
    def add_calls(self):
        return [c for c in self.calls if " add " in f" {c} "]


def install(**kwargs):
    report = S.Report()
    state = S.install_dsh_command_plugin("init", ["dsh"], report)
    return state, report


def texts(report):
    return "\n".join(report.warnings + report.notes
                     + [f"{a['op']} {a['path']} {a['why']}" for a in report.actions])


class AlreadyInstalledTest(unittest.TestCase):
    def test_existing_extension_skips_add(self):
        for json_supported in ("0", "1"):
            with self.subTest(json=json_supported), \
                 DshHarness(installed=["dsh-agent-extension@0.1.4", "dsh-plugin-web@2.0.0"],
                            DSH_JSON=json_supported) as dsh:
                state, report = install()
                self.assertEqual(state, "already-installed")
                self.assertEqual(dsh.add_calls, [], "⛔ 已装还去 add 是多余写动作")
                self.assertEqual(report.warnings, [], "已装应走 INFO，不是 WARN")
                self.assertIn("已在 profile=web", "\n".join(report.notes))
                self.assertIn(state, S.DSH_STATE_READY)

    def test_source_spec_form_is_recognised(self):
        """清单里以 `github:Owner/dsh-agent-extension` 形态出现也算已装（归一后比较）。"""
        with DshHarness(installed=["github:SugarFatFree/dsh-agent-extension@0.1.4"]) as dsh:
            state, _report = install()
            self.assertEqual(state, "already-installed")
            self.assertEqual(dsh.add_calls, [])


class CliUnavailableTest(unittest.TestCase):
    def test_missing_dsh_is_unverified_not_absent(self):
        with DshHarness(present=False) as dsh:
            state, report = install()
            self.assertEqual(state, "cli-unavailable")
            self.assertEqual(dsh.calls, [], "⛔ 定位不到 dsh 就不该再去跑它")
            self.assertNotIn(state, S.DSH_STATE_READY)
            output = texts(report) + S.DSH_STATE_LABEL[state]
            self.assertIn("未验证", output)
            self.assertNotIn("未安装", output, "⛔ 「本进程找不到 dsh」不得说成「扩展未安装」")
            self.assertNotIn("安装失败", output)
            # 诊断信息要够定位，又必须脱敏
            self.assertIn("platform=", output)
            self.assertIn("PATH 条目", output)
            self.assertIn("which(dsh)=", output)
            self.assertNotIn(str(dsh.bindir), output, "⛔ 不得外显 PATH 原文 / 绝对路径")

    def test_version_probe_failure_is_unknown(self):
        with DshHarness(installed=[], DSH_VERSION_EXIT="1") as dsh:
            state, report = install()
            self.assertEqual(state, "unknown")
            self.assertEqual(dsh.add_calls, [], "状态无从判断时⛔不得盲目 add")
            output = texts(report) + S.DSH_STATE_LABEL[state]
            self.assertNotIn("未安装", output)

    def test_unreadable_plugin_list_is_unknown(self):
        with DshHarness(installed=[], DSH_LIST_EXIT="3") as dsh:
            state, report = install()
            self.assertEqual(state, "unknown")
            self.assertEqual(dsh.add_calls, [])
            self.assertNotIn("未安装", texts(report) + S.DSH_STATE_LABEL[state])


class InstallPathTest(unittest.TestCase):
    def test_install_then_reconfirm(self):
        with DshHarness(installed=[]) as dsh:
            state, report = install()
            self.assertEqual(state, "installed")
            self.assertEqual(len(dsh.add_calls), 1, dsh.calls)
            # ★ add 之后必须再 list 一次复查：add 之前 1 次、之后 1 次
            list_calls = [c for c in dsh.calls if "list" in c]
            self.assertGreaterEqual(len(list_calls), 2, dsh.calls)
            self.assertLess(dsh.calls.index(dsh.add_calls[0]), len(dsh.calls) - 1,
                            "复查 list 必须排在 add 之后")
            self.assertEqual(report.warnings, [], report.warnings)
            self.assertEqual([a["op"] for a in report.actions], ["dsh-plugin"])
            self.assertIn(state, S.DSH_STATE_READY)

    def test_add_returns_zero_but_list_misses_is_not_available(self):
        """add 返回 0，复查清单却看不到 → ⛔ 不得返回可用。"""
        with DshHarness(installed=[], DSH_ADD_EFFECT="noop") as dsh:
            state, report = install()
            self.assertEqual(state, "not-installed")
            self.assertNotIn(state, S.DSH_STATE_READY)
            self.assertEqual(len(dsh.add_calls), 1)
            self.assertTrue(report.warnings, "复查落空必须出 WARN")
            self.assertIn("仍看不到", "\n".join(report.warnings))
            self.assertEqual(report.actions, [], "⛔ 没装上就不得记 dsh-plugin 动作")

    def test_add_nonzero_is_install_failed(self):
        with DshHarness(installed=[], DSH_ADD_EXIT="7") as dsh:
            state, report = install()
            self.assertEqual(state, "install-failed")
            self.assertNotIn(state, S.DSH_STATE_READY)
            warning = "\n".join(report.warnings)
            self.assertIn("DSH 命令插件安装失败", warning)
            self.assertIn("exit 7", warning)
            self.assertIn(S.DSH_COMMAND_PLUGIN_RETRY, warning)
            self.assertEqual(len(dsh.add_calls), 1)

    def test_non_dsh_agents_do_nothing(self):
        with DshHarness(installed=[]) as dsh:
            report = S.Report()
            self.assertIsNone(S.install_dsh_command_plugin("init", ["codex"], report))
            self.assertEqual(dsh.calls, [])


class ListParsingTest(unittest.TestCase):
    """清单解析要容错，⛔ 不写依赖固定列宽 / 表头的脆正则。"""

    def test_text_table_tolerance(self):
        table = ("NAME                VERSION\n"
                 "------------------  -------\n"
                 " dsh-agent-extension@0.1.4   0.1.4   web \n"
                 "| other-plugin@1.0 | 1.0 |\n")
        names = S._dsh_names_from_text(table)
        self.assertIn("dsh-agent-extension", names)
        self.assertIn("other-plugin", names)
        self.assertNotIn("", names)

    def test_json_shapes(self):
        for payload in ('{"plugins": [{"name": "dsh-agent-extension", "version": "0.1.4"}]}',
                        '[{"id": "github:Owner/dsh-agent-extension@0.1.4"}]',
                        '["dsh-agent-extension@0.1.4"]',
                        '{"web": {"plugins": ["dsh-agent-extension"]}}'):
            with self.subTest(payload=payload):
                self.assertIn("dsh-agent-extension", S._dsh_names_from_json(payload))
        self.assertIsNone(S._dsh_names_from_json("NAME  VERSION\n"), "非 JSON 必须交给文本回落")


class StateVocabularyTest(unittest.TestCase):
    def test_every_state_is_labelled_and_no_state_claims_absence(self):
        states = {"already-installed", "installed", "not-installed",
                  "cli-unavailable", "unknown", "install-failed"}
        self.assertEqual(set(S.DSH_STATE_LABEL), states)
        self.assertTrue(set(S.DSH_STATE_READY) <= states)
        self.assertEqual(set(S.DSH_STATE_READY), {"already-installed", "installed"})
        for state in ("cli-unavailable", "unknown"):
            self.assertNotIn("未安装", S.DSH_STATE_LABEL[state])
            self.assertNotIn("安装失败", S.DSH_STATE_LABEL[state])


if __name__ == "__main__":
    unittest.main(verbosity=2)
