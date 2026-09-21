#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文档引用与开源卫生三道门的回归：

· `check_code_symbol_refs.py`：`脚本.py::符号` 指向的文件 / 函数 / 登记表键必须存在；
· `check_cli_invocation.py`：文档里的子命令与 flag 必须属于被调用的那个脚本；
· `check_private_markers.py`：内网地址、内网主机名、非占位 MCP 服务名、事故叙述点名下游项目、
  非示例子项目名、本地名单；
· `check_convention_dup.py` 的主行长度上限（常驻记忆正文只留决策要点 + 指针）。

每组都有阴性对照（合规写法不报）与阳性对照（违规写法必报），另跑脚本自带 `--self-check`。
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SCRIPTS = REPO / ".aidp" / "scripts"

_passed = _failed = 0


def check(name, cond):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ✅ {name}")
    else:
        _failed += 1
        print(f"  ❌ FAIL: {name}")


def _run(script, root, *extra):
    p = subprocess.run([sys.executable, str(SCRIPTS / script), "--root", str(root), "--json", *extra],
                       capture_output=True, text=True)
    try:
        data = json.loads(p.stdout)
    except ValueError:
        data = {}
    return p.returncode, data


def _mkroot():
    return Path(tempfile.mkdtemp(prefix="aidp-docref-"))


def _w(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_symbol_refs():
    print("\n[S] check_code_symbol_refs.py")
    root = _mkroot()
    _w(root, ".aidp/scripts/tool_a.py",
       "GUARDS = [(\"guard_x\", 1)]\nLIMIT = 3\n\nclass Box:\n    def open(self):\n        pass\n\n"
       "def real_fn():\n    pass\n")
    _w(root, ".aidp/scripts/run_b.sh", "helper() {\n  :\n}\n")
    # 引用写法用 SEP 拼接：本测试文件自身也在全仓扫描面内，字面量会被当成悬空引用
    sep = "::"
    ok_refs = ["tool_a.py%sreal_fn", "tool_a.py%sLIMIT", "tool_a.py%sBox.open",
               "tool_a.py%sguard_x", "run_b.sh%shelper", "x.py%swhatever"]
    _w(root, "docs/ok.md", "见 " + "、".join("`%s`" % (r % sep) for r in ok_refs) + "。\n")
    rc, d = _run("check_code_symbol_refs.py", root)
    check("阴性：函数 / 常量 / 方法 / 登记表键 / shell 函数 / 占位文件名均放行", rc == 0 and d.get("ok"))
    bad_refs = ["tool_a.py%sgone_fn", "tool_a.py%sBox.close", "missing_c.py%sf"]
    _w(root, "docs/bad.md", "见 " + "、".join("`%s`" % (r % sep) for r in bad_refs) + "。\n"
                            "忽略 `tool_a.py" + sep + "legacy` symbol-ref-ignore: 示例\n")
    rc, d = _run("check_code_symbol_refs.py", root)
    kinds = sorted(e["kind"] for e in d.get("errors", []))
    check("★ 阳性：缺函数、缺方法、缺文件各报一处（豁免行不报）",
          rc == 1 and kinds == ["missing-file", "missing-symbol", "missing-symbol"])
    shutil.rmtree(root, ignore_errors=True)


def test_cli_invocation():
    print("\n[C] check_cli_invocation.py")
    root = _mkroot()
    _w(root, ".aidp/scripts/tool_sub.py",
       "import argparse\nap = argparse.ArgumentParser()\nsub = ap.add_subparsers(dest='cmd')\n"
       "a = sub.add_parser('add')\na.add_argument('--version')\nap.add_argument('--json', action='store_true')\n")
    _w(root, ".aidp/scripts/tool_pos.py",
       "import argparse\nap = argparse.ArgumentParser()\n"
       "ap.add_argument('mode', nargs='?', choices=['detect', 'memory-file'])\nap.add_argument('--root')\n")
    _w(root, ".aidp/scripts/tool_raw.py", "print('no parser')\n")
    _w(root, "docs/ok.md",
       "```bash\npython3 .aidp/scripts/tool_sub.py add --version V1 --json\n"
       "OUT=\"$(python3 .aidp/scripts/tool_pos.py detect --root .)\"\n"
       "python3 .aidp/scripts/tool_sub.py add --ver \\\n  V1\n"
       "python3 .aidp/scripts/tool_sub.py add --version <V>  # 占位\n```\n"
       "行内：`python3 .aidp/scripts/tool_pos.py memory-file` 输出路径。\n")
    rc, d = _run("check_cli_invocation.py", root)
    check("阴性：子命令 / flag / 缩写 / 续行 / 命令替换 / 行内均放行", rc == 0 and d.get("ok"))
    _w(root, "docs/bad.md",
       "```bash\npython3 .aidp/scripts/tool_sub.py addx --json\n"
       "python3 .aidp/scripts/tool_pos.py sync\n"
       "python3 .aidp/scripts/tool_sub.py add --no-track\n"
       "python3 .aidp/scripts/gone_tool.py --json\n"
       "python3 .aidp/scripts/tool_raw.py --json\n"
       "python3 .aidp/scripts/tool_sub.py add --bogus  # cli-check: ignore 示例\n```\n")
    rc, d = _run("check_cli_invocation.py", root)
    kinds = sorted(e["kind"] for e in d.get("errors", []))
    check("★ 阳性：错子命令 ×2、错 flag、脚本不存在各报（豁免行不报）",
          rc == 1 and kinds == ["missing-script", "unknown-flag", "unknown-subcommand", "unknown-subcommand"])
    check("非 argparse 脚本被传 flag → WARN 不计 ERROR",
          [w["kind"] for w in d.get("warns", [])] == ["non-argparse"])
    shutil.rmtree(root, ignore_errors=True)


def test_private_markers():
    print("\n[P] check_private_markers.py")
    root = _mkroot()
    doc_ip = ".".join(["192", "0", "2", "10"])
    _w(root, "docs/ok.md",
       f"连 `http://{doc_ip}:8080` 或 `http://test.example.com/app`；数据库用 `mcp__<db-mcp>__query`，"
       "浏览器用 `mcp__chrome-devtools__click`；子项目 `demo-backend` / `demo-frontend`；"
       "文件 `.env.local` 不算主机名；真实下游事故。\n")
    rc, d = _run("check_private_markers.py", root)
    check("阴性：文档地址段 / example 域名 / 占位 MCP / 示例子项目名放行", rc == 0 and d.get("ok"))
    lan = ".".join(["10", "20", "30", "40"])
    lan2 = ".".join(["172", "18", "0", "9"])
    _w(root, "docs/bad.md",
       f"连 http://{lan}:9222\n"
       f"库在 {lan2}:5236\n"
       # 以下违规样例一律拼接构造：本测试文件自身也在全仓扫描面内
       "打开 http://build." + "corp/app\n"
       "调 mcp__" + "warehouse-db__query\n"
       "（下游 shop-portal" + " 实测事故）\n"
       "如 `acme" + "-backend`\n"
       "秘密词 Zeta-Secret-Word\n"
       f"豁免 http://{lan}:1 private-marker-ignore: 解析器反例\n")
    deny = root / "deny.txt"
    deny.write_text("# 注释\nzeta-secret-word\n", encoding="utf-8")
    rc, d = _run("check_private_markers.py", root, "--path", "docs", "--denylist", str(deny))
    rules = sorted(e["rule"] for e in d.get("errors", []))
    check("★ 阳性：P1×2 / P2 / P3 / P4 / P5 / P6 全部报出（豁免行不报）",
          rc == 1 and rules == ["P1", "P1", "P2", "P3", "P4", "P5", "P6"])
    rc, _ = _run("check_private_markers.py", root, "--denylist", str(root / "nope.txt"))
    check("denylist 文件不存在 → exit 2", rc == 2)
    shutil.rmtree(root, ignore_errors=True)


def test_self_checks():
    print("\n[X] 三个脚本的 --self-check")
    for s in ("check_code_symbol_refs.py", "check_cli_invocation.py", "check_private_markers.py"):
        p = subprocess.run([sys.executable, str(SCRIPTS / s), "--self-check"], capture_output=True, text=True)
        check(f"{s} --self-check 通过", p.returncode == 0 and "[PASS]" in p.stdout)


def test_convention_main_line_length():
    print("\n[L] check_convention_dup.py 主行长度上限（WARN，不进退出码）")
    root = _mkroot()
    (root / ".aidp/reference").mkdir(parents=True)
    shutil.copy(REPO / ".aidp/AIDP-AGENTS.md", root / ".aidp/AIDP-AGENTS.md")
    for f in (REPO / ".aidp/reference").glob("约定细则-*.md"):
        shutil.copy(f, root / ".aidp/reference" / f.name)
    rc, d = _run("check_convention_dup.py", root)
    check("阴性：现行主行均不超长", rc == 0 and d.get("overlong") == [])
    p = root / ".aidp/AIDP-AGENTS.md"
    text = p.read_text(encoding="utf-8")
    lines = text.split("\n")
    sec = next(i for i, ln in enumerate(lines) if ln.startswith("## 核心约定"))
    idx = next(i for i, ln in enumerate(lines) if i > sec and ln.startswith("3. "))
    lines[idx] = lines[idx] + "补充说明" * 200
    p.write_text("\n".join(lines), encoding="utf-8")
    rc, d = _run("check_convention_dup.py", root)
    check("★ 阳性：超长主行报出且不改退出码",
          rc == 0 and [o["convention"] for o in d.get("overlong", [])] in (["3"], [3]))
    shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    test_symbol_refs()
    test_cli_invocation()
    test_private_markers()
    test_convention_main_line_length()
    test_self_checks()
    print(f"\n══ 结果：{_passed} passed / {_failed} failed ══")
    sys.exit(1 if _failed else 0)
