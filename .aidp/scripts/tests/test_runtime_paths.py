#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""下发运行路径契约守卫回归。"""
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / ".aidp/scripts/check_runtime_paths.py"
_passed = _failed = 0


def check(name, cond):
    global _passed, _failed
    if cond:
        _passed += 1
        print("  ✅ " + name)
    else:
        _failed += 1
        print("  ❌ FAIL: " + name)


def run(root, *args):
    p = subprocess.run([sys.executable, str(SCRIPT), "--root", str(root), "--json", *args],
                       capture_output=True, text=True)
    try:
        data = json.loads(p.stdout)
    except ValueError:
        data = {}
    return p.returncode, data


def write(root, rel, text):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_script(name):
    path = REPO / ".aidp/scripts" / name
    spec = importlib.util.spec_from_file_location("runtime_path_" + name.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_user_visible_messages(root):
    emit = load_script("emit-report.py")
    try:
        emit.ensure_skeleton(str(root / "report"), str(root / "missing-template"))
        emit_message = ""
    except FileNotFoundError as exc:
        emit_message = str(exc)
    check("emit-report 模板缺失提示使用具体运行根且无多余引号",
          "python3" not in emit_message
          and ".aidp/templates/reports/" in emit_message
          and "'（" not in emit_message and "）'" not in emit_message)

    debt = load_script("release_debt.py")
    debt.add(str(root), "V1.2.3", "1", "探针")
    debt_text = (root / "docs/audit/V1.2.3/发布欠账.md").read_text(encoding="utf-8")
    check("release_debt 标题与恢复命令无多余引号",
          debt_text.startswith("# V1.2.3 发布欠账\n")
          and "python3 .aidp/scripts/release_debt.py" in debt_text
          and "V1.2.3'" not in debt_text)

    write(root, ".aidp/commands/demo.md", "# demo\n")
    write(root, ".aidp/flows/demo/x.md", "参数：$ARGUMENTS\n")
    arguments = load_script("check_arguments_channel.py").run(str(root))
    detail = (arguments.get("findings") or [{}])[0].get("detail", "")
    check("arguments channel 提示反引号配对且路径具体",
          "`/demo`" in detail and "`.aidp/commands/*.md`" in detail
          and "demo'`" not in detail and "落 0**'" not in detail)

    ceremony_source = (REPO / ".aidp/scripts/autopilot-ceremony-gate.py").read_text(encoding="utf-8")
    webmcp_source = (REPO / ".aidp/scripts/check_webmcp.py").read_text(encoding="utf-8")
    check("ceremony driver 文案无迁移引号残留",
          "driver={_claim or '(无)'}'）" not in ceremony_source
          and "waiver 说明理由'" not in ceremony_source)
    check("WebMCP rule 文案无迁移引号残留",
          "{RULE_INSTALLED}'`" not in webmcp_source
          and "模板位：'{RULE_TEMPLATE}" not in webmcp_source)


def main():
    root = Path(tempfile.mkdtemp(prefix="aidp-runtime-path-test-"))
    try:
        write(root, ".aidp/commands/ok.md", "python3 {{AIDP_HOME}}/scripts/x.py\n")
        write(root, ".aidp/skills/aidp-code-engineer/SKILL.md", "python3 .aidp/scripts/private.py\n")
        write(root, ".aidp/scripts/tests/fixture.py", 'X = ".aidp/scripts/test.py"\n')
        rc, data = run(root)
        check("源契约允许 AIDP_HOME，排除脚手架自身与 tests", rc == 0 and data.get("ok"))

        write(root, ".aidp/flows/x/bad.md",
              "python3 .aidp/scripts/x.py # runtime-path-ignore: 不能掩盖运行路径\n")
        rc, data = run(root)
        check("硬编码路径即使带豁免也报错",
              rc == 1 and [x.get("kind") for x in data.get("findings", [])]
              == ["hardcoded-runtime-path"])

        (root / ".aidp/flows/x/bad.md").unlink()
        rc, data = run(root, "--rendered")
        check("渲染态抓未解析 AIDP_HOME",
              rc == 1 and [x.get("kind") for x in data.get("findings", [])]
              == ["unresolved-runtime-home"])

        (root / ".aidp/commands/ok.md").write_text("ok\n", encoding="utf-8")
        write(root, ".aidp/scripts/ast_probe.py",
              "from pathlib import Path\nimport os\n"
              "LEGACY_AIDP_DIR = '.aidp'\n"
              "AIDP_DIR = '.aidp'\n"
              "D = Path(AIDP_DIR) / 'commands'\n"
              "A = Path('.aidp') / 'commands'\n"
              "B = os.path.join('x', '.aidp', 'scripts')\n"
              "C = '.aidp' + '/flows/x.md'\n"
              "print('__AIDP_HOME__/scripts/leak.py')\n")
        rc, data = run(root)
        ast_hits = [x for x in data.get("findings", []) if x.get("kind") == "hardcoded-runtime-construction"]
        variable_hits = [x for x in data.get("findings", []) if x.get("kind") == "hardcoded-runtime-root-variable"]
        token_hits = [x for x in data.get("findings", []) if x.get("kind") == "unexpanded-runtime-output"]
        check("AST 抓 Path/join/拼接构造，LEGACY 常量单独声明放行",
              rc == 1 and len(ast_hits) == 3)
        check("AST 数据流抓 AIDP_DIR 变量及其路径使用", len(variable_hits) == 1)
        check("Python 用户输出不得泄露内部运行根 token", len(token_hits) == 1)
        (root / ".aidp/scripts/ast_probe.py").unlink()

        state = root / ".aidp/memory/.aidp/alerts.jsonl"
        state.parent.mkdir(parents=True)
        state.write_text("{}\n", encoding="utf-8")
        rc, data = run(root)
        check("模板运行源禁止携带 memory/.aidp 状态文件",
              rc == 1 and any(x.get("kind") == "runtime-state-in-source" for x in data.get("findings", [])))
        shutil.rmtree(root / ".aidp/memory")

        native = root / ".agents/aidp"
        (native / "scripts").mkdir(parents=True)
        shutil.copy2(REPO / ".aidp/scripts/aidp_runtime.py", native / "scripts/aidp_runtime.py")
        skill_script = native / "skills/dev-execution-planner/scripts/scan_aidp.py"
        skill_script.parent.mkdir(parents=True)
        shutil.copy2(REPO / ".aidp/skills/dev-execution-planner/scripts/scan_aidp.py", skill_script)
        (native / "commands").mkdir()
        (native / "commands/demo.md").write_text("# demo\n", encoding="utf-8")
        p = subprocess.run([sys.executable, str(skill_script), str(root), "--json"],
                           capture_output=True, text=True)
        try:
            payload = json.loads(p.stdout)
        except ValueError:
            payload = {}
        check("Skill 脚本可从原生 runtime 定位运行包",
              p.returncode == 0 and any(x.get("type") == "aidp_directory"
                                        and ".agents/aidp" in x.get("source", "")
                                        for x in payload.get("sources", [])))
        shutil.rmtree(root / ".agents")

        test_user_visible_messages(root)

        rc = subprocess.run([sys.executable, str(SCRIPT), "--self-check"],
                            capture_output=True, text=True).returncode
        check("脚本自检通过", rc == 0)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    print(f"\n══ 结果：{_passed} passed / {_failed} failed ══")
    return 1 if _failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
