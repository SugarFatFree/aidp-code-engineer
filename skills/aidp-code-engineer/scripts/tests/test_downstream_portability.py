#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""下游可移植性回归：**skill 装在项目自身、非 Git 目录、无任何 AIDP_* 环境变量、控制台非 UTF-8**。

覆盖下游（Windows PowerShell + Python 3.12 + Codex / DeepSeek Harness）报回来的引擎缺陷，
全部用 **Linux 上可确定性复现的等价条件**表达（bundle 目录布局 / mock / 显式字节 / 剥环境变量），
⛔ 不写只能在 Windows 上跑的用例：

  A  `scaffold.py --detect` 在「skill 自带 bundle」布局下 import 期即崩（`_natural_layout` 不认 bundle）
  B  skill 的执行源 == 安装目标（自举安装）时被「无标记即用户内容」误判拒绝
  C  Windows 文本模式把 `\\n` 写成 `\\r\\n` → 运行包整包假漂移（等价表达 = 禁止任何文本模式写入 + 字节断言）
  D  GBK 控制台上 `❌`/`⚠️`/`↔` 一 print 就 UnicodeEncodeError，检查跑完了却死在汇报上
  F  运行包漂移只报第一个文件，看不出爆炸半径

另含两条与之连坐的不变式：同版本第二次 upgrade 幂等、`agent_sync.py --check` 无漂移。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

import _helpers as H
import scaffold_lib as L
import scaffold_marker
import runtime_layout

BUNDLE_VERSION = L.bundle_version()
# 与 scaffold.py 的 `_runtime_source()` 同口径：模板仓库里是 `.aidp/`，下游只有 bundle。
TEMPLATE_SOURCE = L.template_aidp() or L.BUNDLE_AIDP


def downstream_env(**extra):
    """下游最朴素的环境：⛔ 不预设 AIDP_HOME / AIDP_PROJECT_ROOT / AIDP_AGENT。"""
    env = {k: v for k, v in os.environ.items()
           if k not in ("AIDP_HOME", "AIDP_PROJECT_ROOT", "AIDP_AGENT")}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.update(extra)
    return env


def plant_skill(project: Path, family: str = ".agents") -> Path:
    """把脚手架 skill 按**下游真实安装形态**放进项目自身（受管副本不含 tests / sources）。

    这样 `L.template_aidp()` 必然返回 None，scaffold 只能回落 `assets/aidp/`（= 缺陷 A 的布局），
    且安装目标与执行源是同一个目录（= 缺陷 B 的自举场景）。
    """
    destination = project / family / "skills" / L.SKILL_NAME
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(H.SKILL_DIR, destination,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "tests", "sources"))
    return destination


def run_skill(skill: Path, script: str, *args, env=None, check=False):
    p = subprocess.run([sys.executable, str(skill / "scripts" / script), *map(str, args)],
                       capture_output=True, text=True, stdin=subprocess.DEVNULL,
                       env=env or downstream_env())
    if check and p.returncode != 0:
        raise AssertionError(f"{script} → exit {p.returncode}\n{p.stdout}\n{p.stderr}")
    return p


def skill_family(agent: str) -> str:
    """skill 必须落在本次启用的 Agent 家族下，否则 init 会去清理一个「未受管」的并列目录。"""
    return ".claude" if set(agent.split(",")) <= {"claude"} else ".agents"


def init_downstream(project: Path, agent: str, skill: Path = None) -> dict:
    """在非 Git 空目录上跑一次真实 init（skill 自举安装、adapter-mode=copy）。"""
    skill = skill or plant_skill(project, skill_family(agent))
    p = run_skill(skill, "scaffold.py", project, "--version", "V0.1.0", "--user", "tester",
                  "--agent", agent, "--adapter-mode", "copy", "--json", check=True)
    return json.loads(p.stdout)


def runtime_errors(project: Path, skill: Path):
    """★ 必须用**项目自己装的那份 skill** 去 verify。

    ⛔ 不能用模板仓库里 import 进来的 `verify`：那一侧的真源是模板 `.aidp/`，与下游安装用的
    bundle 存在既有的权限位差异（`.aidp/scripts/*.py` 是 755，bundle 里是 644），混用会凭空
    多出二十几条与本用例无关的漂移，把真正要观测的信号淹掉。
    """
    p = run_skill(skill, "verify.py", project, "V0.1.0", "tester", "--read-only", "--no-guards")
    return [line.strip()[len("[ERROR]"):].strip()
            for line in p.stdout.splitlines()
            if line.strip().startswith("[ERROR]") and "原生运行包" in line]


def tree_digest(root: Path) -> dict:
    return {path.relative_to(root).as_posix(): L.sha256(path.read_bytes())
            for path in sorted(root.rglob("*"))
            if path.is_file() and "__pycache__" not in path.parts}


class BundleLayoutResolutionTest(unittest.TestCase):
    """缺陷 A（阴性对照 = 修好后应当通过）：bundle 布局下 import 期不得崩。"""

    def test_natural_layout_accepts_bundle_and_still_rejects_strangers(self):
        sys.path.insert(0, str(L.BUNDLE_AIDP / "scripts"))
        try:
            import aidp_runtime
        finally:
            sys.path.pop(0)
        runtime, project = aidp_runtime._natural_layout(L.BUNDLE_AIDP / "scripts/agent_sync.py")
        self.assertEqual(runtime, L.BUNDLE_AIDP)
        self.assertEqual(project, L.ASSETS)
        with tempfile.TemporaryDirectory() as td:
            # ★ 只放宽 bundle 这一支：随便一个 `<x>/aidp/scripts/` 仍必须拒绝，
            #   否则真实运行根的解析就被放松了（下游会把任意目录当成运行根）。
            stranger = Path(td) / "whatever/aidp/scripts"
            stranger.mkdir(parents=True)
            with self.assertRaises(RuntimeError):
                aidp_runtime._natural_layout(stranger / "agent_sync.py")
            # 连 `assets/aidp/` 的形也不够：三件套不齐就不是 bundle
            half = Path(td) / "half/assets/aidp/scripts"
            half.mkdir(parents=True)
            with self.assertRaises(RuntimeError):
                aidp_runtime._natural_layout(half / "agent_sync.py")

    def test_detect_runs_without_aidp_env_vars(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "proj"
            project.mkdir()
            skill = plant_skill(project)
            p = run_skill(skill, "scaffold.py", project, "--detect")
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertNotIn("无法从脚本位置解析 AIDP 运行根", p.stderr)
            data = json.loads(p.stdout)
            self.assertEqual(data["mode"], "init")
            self.assertEqual(data["scaffold"]["bundle_version"], BUNDLE_VERSION)
            self.assertFalse((project / ".git").exists(), "⛔ 探测不得自动 git init")

    def test_verify_imports_in_bundle_layout(self):
        """verify.py 与 scaffold.py 走同一条 import 链，同样不得在 import 期崩。"""
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "proj"
            project.mkdir()
            skill = plant_skill(project)
            p = run_skill(skill, "verify.py", project, "V0.1.0", "tester",
                          "--read-only", "--no-guards")
            self.assertNotIn("无法从脚本位置解析 AIDP 运行根", p.stdout + p.stderr)
            self.assertNotIn("Traceback", p.stderr)
            # 尚未 init，报缺运行包是对的；这里只要求它「跑完并给出结论」，不要求通过。
            self.assertIn("验证结果", p.stdout)


class SelfInstalledSkillTest(unittest.TestCase):
    """缺陷 B：安装源 == 安装目标。"""

    def test_self_bootstrap_init_succeeds(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "proj"
            project.mkdir()
            skill = plant_skill(project)
            result = init_downstream(project, "codex", skill)
            self.assertEqual(result["agents"], ["codex"])
            self.assertTrue((skill / ".aidp-scaffold-generated").is_file(),
                            "自举安装后目标必须带受管标记")
            body = (skill / "SKILL.md").read_text(encoding="utf-8")
            self.assertNotIn("{{AIDP_HOME}}", body)
            self.assertIn(".agents/aidp", body)
            self.assertTrue((skill / "scripts/scaffold.py").is_file(), "自举后 skill 必须仍可执行")
            self.assertEqual(list((project / ".agents/skills").glob(".aidp-skill-stage-*")), [],
                             "⛔ 不得遗留临时装配目录")
            self.assertFalse((project / ".git").exists(), "⛔ init 不得自动 git init")
            verified = run_skill(skill, "verify.py", project, "V0.1.0", "tester",
                                 "--read-only", "--no-guards")
            self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)

    def test_real_user_skill_directory_is_still_refused(self):
        """⛔ 阳性对照：放宽只对「就是本次执行的那个 skill 目录」成立，真用户目录仍必须拒绝。"""
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "proj"
            project.mkdir()
            skill = plant_skill(project)
            intruder = project / ".claude/skills" / L.SKILL_NAME
            intruder.mkdir(parents=True)
            (intruder / "SKILL.md").write_text("# 用户自己写的同名 skill\n", encoding="utf-8")
            p = run_skill(skill, "scaffold.py", project, "--version", "V0.1.0",
                          "--user", "tester", "--agent", "claude,codex",
                          "--adapter-mode", "copy", "--json")
            self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
            self.assertIn("拒绝覆盖", p.stdout + p.stderr)
            self.assertEqual((intruder / "SKILL.md").read_text(encoding="utf-8"),
                             "# 用户自己写的同名 skill\n")

    def test_failure_during_atomic_replace_rolls_back_completely(self):
        """失败注入：原子替换当场炸 → skill 自身与项目骨架必须整体回到执行前。"""
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "proj"
            project.mkdir()
            skill = plant_skill(project)
            before = tree_digest(skill)
            driver = Path(td) / "inject.py"
            driver.write_text(textwrap.dedent('''
                import os, sys
                from argparse import Namespace
                skill, root = sys.argv[1], sys.argv[2]
                sys.path.insert(0, os.path.join(skill, "scripts"))
                import scaffold as S
                import scaffold_lib as L
                from pathlib import Path
                real_replace = os.replace
                def boom(src, dst, **kw):
                    # 只在「把装配好的 skill 副本原子换上去」这一步炸，其余 replace 照常
                    if ".aidp-skill-stage-" in str(src) and os.path.basename(str(dst)) == L.SKILL_NAME:
                        raise OSError("injected: 原子替换失败")
                    return real_replace(src, dst, **kw)
                os.replace = boom
                options = Namespace(mode="auto", agent="codex", json=True, user="tester",
                                    name_cn=None, version="V0.1.0", force=False,
                                    keep_backups=L.PRUNE_KEEP_LAST_DEFAULT,
                                    keep_days=L.PRUNE_KEEP_DAYS_DEFAULT,
                                    no_agent_sync=True, adapter_mode="copy")
                try:
                    S.run(Path(root).resolve(), options)
                except BaseException as exc:
                    print("RAISED", type(exc).__name__, exc)
                    sys.exit(3)
                print("NO-RAISE")
                sys.exit(0)
            ''').lstrip(), encoding="utf-8")
            p = subprocess.run([sys.executable, str(driver), str(skill), str(project)],
                               capture_output=True, text=True, env=downstream_env(),
                               stdin=subprocess.DEVNULL)
            self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
            self.assertIn("injected", p.stdout + p.stderr)
            self.assertEqual(tree_digest(skill), before, "skill 自身必须逐字回滚")
            self.assertFalse((skill / ".aidp-scaffold-generated").exists())
            self.assertFalse((project / ".agents/aidp").exists(), "运行包必须整体回滚")
            self.assertEqual(list((project / ".agents/skills").glob(".aidp-skill-stage-*")), [])


class DeterministicLfWriteTest(unittest.TestCase):
    """缺陷 C：manifest 计算 / 实际写入 / verify 比较三处必须同一口径（恒 LF 字节）。"""

    def test_write_text_lf_never_uses_text_mode(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "a.txt"
            # Windows 文本模式的等价表达：一旦走 `Path.write_text` 就判失败（那正是被翻成 CRLF 的入口）
            with mock.patch.object(Path, "write_text",
                                   side_effect=AssertionError("⛔ 不得走文本模式写入")):
                L.write_text_lf(target, "第一行\n第二行\n")
            self.assertEqual(target.read_bytes(), "第一行\n第二行\n".encode("utf-8"))

    def test_rendered_runtime_is_lf_only_and_passes_manifest_immediately(self):
        for source_kind, home in (("claude", ".claude/aidp"), ("shared", ".agents/aidp")):
            with self.subTest(home=home), tempfile.TemporaryDirectory() as td:
                destination = Path(td) / home
                with mock.patch.object(Path, "write_text",
                                       side_effect=AssertionError("⛔ 运行包不得走文本模式写入")):
                    runtime_layout.render_runtime(TEMPLATE_SOURCE, destination, home,
                                                  BUNDLE_VERSION, source_kind)
                # ① 写出去的字节里一个 CRLF 都不许有
                crlf = [relative for relative, path in runtime_layout._runtime_files(destination)
                        if b"\r\n" in path.read_bytes()]
                self.assertEqual(crlf, [], f"{home}: 写出的运行包含 CRLF")
                # ② 渲染完当场过 manifest / 占位符 / 家目录校验（= verify 侧同一口径）
                manifest = runtime_layout.validate_runtime(destination, expected_home=home)
                self.assertEqual(manifest["version"], BUNDLE_VERSION)
                self.assertGreater(len(manifest["files"]), 100)


class GbkConsoleTest(unittest.TestCase):
    """缺陷 D：非 UTF-8 控制台上打印不得让整次检查作废。"""

    class GbkStream:
        """没有 reconfigure 的 GBK 流 —— Windows 控制台「切不动 UTF-8」的确定性等价物。"""
        encoding = "gbk"

        def __init__(self):
            self.text = ""

        def write(self, text):
            text.encode("gbk")            # 编不出来就跟真控制台一样抛 UnicodeEncodeError
            self.text += text
            return len(text)

        def flush(self):
            pass

    def test_console_marks_fall_back_to_ascii(self):
        with mock.patch.object(sys, "stdout", self.GbkStream()), \
             mock.patch.object(sys, "stderr", self.GbkStream()):
            marks = L.console_marks()
            self.assertIsInstance(sys.stdout, L._SafeConsole, "编不出记号的流必须套兜底代理")
        self.assertEqual(marks["error"], "[X]")
        self.assertEqual(marks["warn"], "[!]")
        for value in marks.values():
            value.encode("gbk")           # ⛔ 降级后每一个记号都必须能在 GBK 下编码

    def test_safe_console_replaces_unencodable_text(self):
        """正文里的 `↔`（verify 护栏标题就带）在 GBK 下也不许把 print 打崩。"""
        stream = self.GbkStream()
        with mock.patch.object(sys, "stdout", stream), \
             mock.patch.object(sys, "stderr", self.GbkStream()):
            L.configure_console()
            print("散文承诺↔可执行落点 ✅")
            captured = sys.stdout
        self.assertIsInstance(captured, L._SafeConsole)
        self.assertIn("散文承诺", stream.text)
        self.assertNotIn("↔", stream.text)

    def test_verify_summary_survives_gbk_stdout(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "proj"
            project.mkdir()
            skill = plant_skill(project)
            init_downstream(project, "codex", skill)
            driver = Path(td) / "gbk_verify.py"
            driver.write_text(textwrap.dedent('''
                import os, sys
                skill, root = sys.argv[1], sys.argv[2]
                sys.path.insert(0, os.path.join(skill, "scripts"))
                raw = sys.stdout.buffer
                class GbkOut:                       # 无 reconfigure：切不到 UTF-8，只能降级
                    encoding = "gbk"
                    def write(self, text):
                        raw.write(text.encode("gbk"))   # emoji 会直接 UnicodeEncodeError
                        return len(text)
                    def flush(self):
                        raw.flush()
                sys.stdout = GbkOut()
                sys.stderr = GbkOut()
                import verify as V
                code = V.main([root, "V0.1.0", "tester", "--read-only", "--no-guards"])
                sys.stdout.flush()
                raw.write(("\\nEXIT=%d\\n" % code).encode("gbk"))
            ''').lstrip(), encoding="utf-8")
            p = subprocess.run([sys.executable, str(driver), str(skill), str(project)],
                               capture_output=True, env=downstream_env(), stdin=subprocess.DEVNULL)
            out = p.stdout.decode("gbk", errors="replace")
            err = p.stderr.decode("utf-8", errors="replace")
            self.assertEqual(p.returncode, 0, out + err)
            self.assertNotIn("UnicodeEncodeError", err)
            self.assertIn("EXIT=0", out)
            self.assertIn("验证结果", out)
            self.assertNotIn("❌", out)


class RuntimeDriftObservabilityTest(unittest.TestCase):
    """缺陷 F：整包漂移必须报总数，⛔ 不是只报第一个文件；同时保留阳性对照。"""

    @staticmethod
    def _reseal(runtime: Path, home: str, source_kind: str):
        """按篡改后的内容重算 manifest —— 这正是「安装侧写错了口径」时的真实形态：
        manifest 自洽（指纹校验过得去），与真源却整片不等。"""
        manifest = runtime_layout.build_runtime_manifest(runtime, BUNDLE_VERSION, source_kind, home)
        runtime_layout._write_manifest(runtime, manifest)

    def test_mass_crlf_drift_reports_total_count(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "proj"
            project.mkdir()
            skill = plant_skill(project)
            init_downstream(project, "codex", skill)
            runtime = project / ".agents/aidp"
            touched = 0
            for _relative, path in runtime_layout._runtime_files(runtime):
                data = path.read_bytes()
                if runtime_layout._is_text(data) and b"\n" in data:
                    path.write_bytes(data.replace(b"\n", b"\r\n"))   # Windows 文本模式的等价效果
                    touched += 1
            self._reseal(runtime, ".agents/aidp", "shared")
            self.assertGreater(touched, 100)
            errors = runtime_errors(project, skill)
            self.assertEqual(len(errors), 1, errors)
            self.assertRegex(errors[0], r"共 \d{3,}/\d+ 个文件字节或权限不同")
            self.assertIn("示例：", errors[0])

    def test_single_real_change_is_still_reported(self):
        """阳性对照：真实内容改动（且 manifest 重算过）仍必须被发现并指名。"""
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "proj"
            project.mkdir()
            skill = plant_skill(project)
            init_downstream(project, "codex", skill)
            runtime = project / ".agents/aidp"
            victim = runtime / "agents/aidp-compliance.md"
            self.assertTrue(victim.is_file())
            victim.write_bytes(victim.read_bytes() + "\n<!-- 真实内容改动 -->\n".encode("utf-8"))
            self._reseal(runtime, ".agents/aidp", "shared")
            errors = runtime_errors(project, skill)
            self.assertEqual(len(errors), 1, errors)
            self.assertIn("共 1/", errors[0])
            self.assertIn("agents/aidp-compliance.md", errors[0])

    def test_both_homes_verify_clean_after_install(self):
        """`{{AIDP_HOME}}` 渲染成两种运行根后都必须 verify 通过（阴性对照）。"""
        for agent, home in (("claude", ".claude/aidp"), ("codex", ".agents/aidp")):
            with self.subTest(home=home), tempfile.TemporaryDirectory() as td:
                project = Path(td) / "proj"
                project.mkdir()
                skill = plant_skill(project, skill_family(agent))
                init_downstream(project, agent, skill)
                self.assertTrue((project / home / runtime_layout.RUNTIME_MANIFEST).is_file())
                self.assertEqual(runtime_errors(project, skill), [])


class DownstreamIdempotencyTest(unittest.TestCase):
    """同版本第二次 upgrade：无漂移、⛔ 不产生多余备份；agent_sync --check 无 drift。"""

    def test_second_same_version_run_is_a_noop(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "proj"
            project.mkdir()
            skill = plant_skill(project)
            init_downstream(project, "codex", skill)
            backups = sorted(p.name for p in project.glob(".aidp-backup-*"))
            result = init_downstream(project, "codex", skill)
            self.assertEqual(sorted({a["op"] for a in result["actions"]}), ["agent-sync"],
                             result["actions"])
            self.assertEqual(sorted(x.name for x in project.glob(".aidp-backup-*")), backups,
                             "⛔ 同版本重跑不得再备份一次整个 skill")
            self.assertEqual(scaffold_marker.read_version(project), BUNDLE_VERSION)
            self.assertEqual(runtime_errors(project, skill), [])

    def test_agent_sync_check_reports_no_drift(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "proj"
            project.mkdir()
            init_downstream(project, "codex")
            p = subprocess.run(
                [sys.executable, str(project / ".agents/aidp/scripts/agent_sync.py"),
                 "--root", str(project), "--agents", "codex", "--mode", "copy", "--check"],
                capture_output=True, text=True, env=downstream_env(), stdin=subprocess.DEVNULL)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            data = json.loads(p.stdout.strip().splitlines()[-1])
            self.assertFalse(data["drift"], data)
            self.assertEqual(data["actions"], [], data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
