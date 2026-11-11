#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文档引用与开源卫生三道门，及后补的 README 登记 / 中文数字计数 / 陈旧短语 / `{user}` 扫描面扩展的回归：

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

    # memory/.aidp 是本地运行态（gitignore）：旧审计快照里的过期调用不是仓库文档，不能让检查变红。
    root = _mkroot()
    _w(root, ".aidp/scripts/tool_sub.py",
       "import argparse\nap = argparse.ArgumentParser()\nsub = ap.add_subparsers(dest='cmd')\n"
       "sub.add_parser('add')\n")
    _w(root, "docs/ok.md", "```bash\npython3 .aidp/scripts/tool_sub.py add\n```\n")
    _w(root, "memory/.aidp/snapshot/old.md", "```bash\npython3 .aidp/scripts/tool_sub.py removed-subcommand\n```\n")
    rc, d = _run("check_cli_invocation.py", root)
    check("阴性：memory/.aidp 运行态快照里的过期调用不被扫描", rc == 0 and d.get("ok"))
    _w(root, "docs/elsewhere/memory/.aidp-notes.md", "```bash\npython3 .aidp/scripts/tool_sub.py removed-subcommand\n```\n")
    rc, d = _run("check_cli_invocation.py", root)
    check("★ 阳性：只排除精确的 memory/.aidp，其他同名片段的错误调用仍报", rc == 1 and not d.get("ok"))
    shutil.rmtree(root, ignore_errors=True)

    # 条件探测式调用：文档自述「先跑 --help，脚本列有 … 时才带」→ unknown-flag 不报；无该说明仍报。
    root = _mkroot()
    _w(root, ".aidp/scripts/tool_probe.py", "import argparse\nap = argparse.ArgumentParser()\nap.add_argument('--version')\n")
    _w(root, "docs/probe.md", "先跑 `--help`，脚本列有 `--paths` 时带上：\n\n```bash\npython3 .aidp/scripts/tool_probe.py --version 1 --paths a\n```\n")
    rc, d = _run("check_cli_invocation.py", root)
    check("条件探测说明之后的未知 flag 不报", rc == 0 and d.get("ok"))
    _w(root, "docs/noprobe.md", "```bash\npython3 .aidp/scripts/tool_probe.py --version 1 --paths a\n```\n")
    rc, d = _run("check_cli_invocation.py", root)
    check("★ 阳性：无探测说明的同样调用仍报 unknown-flag", rc == 1 and [e["kind"] for e in d.get("errors", [])] == ["unknown-flag"])
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


def test_identity_scope_agents_and_init():
    print("\n[I] check_identity_source.py 扫描面扩到 agents/ 与 docs/init/")
    root = _mkroot()
    _w(root, ".aidp/agents/bad.md", "> `{user}` 来自 `git config user.name`。\n")
    _w(root, ".aidp/agents/good.md",
       "> `{user}` ← `python3 {{AIDP_HOME}}/scripts/vcs.py user`\n"
       "> 豁免写法 `git config user.name` <!-- identity-ignore: 取本机 Git 身份本身 -->\n")
    _w(root, "docs/init/06_x.md",
       "- {user} ← `git config user.name`\n"
       "> ⛔ **不要退回 `git config user.name`**：无 Git 的项目上会分叉。\n"
       "- ⛔ 命令 / 流程里不再各自写 `git config user.name`\n")
    rc, d = _run("check_identity_source.py", root)
    paths = sorted((f["path"], f["line"]) for f in d.get("findings", []))
    check("阳性：agents/ 下旧写法被抓", ("agents/bad.md", 1) in paths)
    check("阳性：docs/init 下旧写法被抓（路径相对项目根）", ("docs/init/06_x.md", 1) in paths)
    check("阴性：反面说明（不要退回 / 不再各自写）与 identity-ignore / vcs.py 口径不误报",
          len(paths) == 2 and rc == 1)
    shutil.rmtree(root, ignore_errors=True)


def test_readme_registry():
    print("\n[R] check_readme_registry.py：目录内文件必须在同目录 README 登记")
    root = _mkroot()
    _w(root, "版本变更历史.md", "# x\n")
    _w(root, ".aidp/reference/README.md",
       "| `a.md` | x |\n| `约定细则-1.md` ~ `约定细则-3.md` | 范围 |\n"
       "<!-- registry-ignore: legacy.md 历史遗留，仅内部引用 -->\n")
    for n in ("a.md", "约定细则-1.md", "约定细则-2.md", "约定细则-3.md", "legacy.md", "orphan.md", ".hidden.md"):
        _w(root, f".aidp/reference/{n}", "x\n")
    _w(root, ".aidp/reference/tests/t.py", "x\n")
    _w(root, ".aidp/reference/__pycache__/c.pyc", "x\n")
    _w(root, ".aidp/flows/README.md", "`sprint-x/` 一个命令一个子目录\n")
    _w(root, ".aidp/flows/sprint-x/phase-1.md", "x\n")
    _w(root, ".aidp/flows/sprint-y/phase-1.md", "x\n")      # 子目录未登记
    _w(root, "docs/plans/README.md", "见 `00_索引.md`\n")
    _w(root, "docs/plans/00_索引.md", "x\n")
    _w(root, "docs/plans/V1.0.0/01.md", "x\n")               # 版本目录不要求登记
    _w(root, "docs/plans/extra.md", "x\n")                   # 未登记
    rc, d = _run("check_readme_registry.py", root)
    miss = sorted(f["file"] for f in d.get("findings", []))
    check("阳性：未登记文件 / 子目录被抓",
          miss == [".aidp/flows/sprint-y", ".aidp/reference/orphan.md", "docs/plans/extra.md"] and rc == 1)
    check("阴性：范围写法 / registry-ignore / 隐藏 / tests / __pycache__ / 版本目录不误报",
          all("约定细则" not in m and "legacy" not in m and "hidden" not in m and "V1.0.0" not in m for m in miss))
    check("findings 带所属 README", all(f.get("readme", "").endswith("README.md") for f in d["findings"]))
    _w(root, ".aidp/reference/README.md", "`a.md` `约定细则-1.md` ~ `约定细则-3.md` `orphan.md` "
       "<!-- registry-ignore: legacy.md -->\n")
    rc, d = _run("check_readme_registry.py", root)
    check("registry-ignore 缺理由不生效（legacy.md 重新被抓）",
          any(f["file"].endswith("legacy.md") for f in d["findings"]))
    (root / "版本变更历史.md").unlink()
    rc, d = _run("check_readme_registry.py", root)
    check("非模板仓库（无版本变更历史.md）→ N/A 不报", rc == 0 and d.get("applicable") is False and d["findings"] == [])
    shutil.rmtree(root, ignore_errors=True)


def test_cn_count_claims():
    print("\n[C] check_cn_count_claims.py：中文数字自称计数 vs 目录实数")
    root = _mkroot()
    _w(root, "版本变更历史.md", "x\n")
    for i in range(3):
        _w(root, f".aidp/agents/r{i}.md", "x\n")
    _w(root, ".aidp/agents/README.md", "x\n")
    _w(root, ".aidp/AIDP-AGENTS.md", "## 核心约定\n\n1. **甲**\n2. **乙**\n3. **丙**\n")
    _w(root, "a.md", "本目录下的九份角色指令\n## 九份角色与归属\n")
    _w(root, "b.md", "共十二个 Agent 角色\n")
    _w(root, "c.md", "三份角色指令；共三个 Agent；三个 Agent 角色指令\n")
    _w(root, "d.md", "共五条核心约定；四条核心约定；核心约定 1–三\n")
    _w(root, "e.md", "派三个 Agent 并行；一份角色指令；每个角色一份\n")           # 局部数量 / 单数 → 不是总数
    _w(root, "f.md", "九份角色 <!-- countclaim-check: ignore 历史 -->\n")
    _w(root, "g.md", "二十一世纪；十条规则；共十个命令\n")                  # 无关量词 / 未覆盖对象
    _w(root, ".aidp/skills/x/SKILL.md", "九份角色\n")                      # skills 本体不扫
    rc, d = _run("check_cn_count_claims.py", root)
    got = sorted((v["file"], v["declared"]) for v in d.get("violations", []))
    check("阳性：九份角色 ×2（a.md）、共十二个 Agent（b.md）被抓",
          got.count(("a.md", 9)) == 2 and ("b.md", 12) in got)
    check("阳性：核心约定中文计数被抓（五条 / 四条）；与真值一致的 1–三 不报",
          sorted(x[1] for x in got if x[0] == "d.md") == [4, 5])
    check("阴性：与真值一致（三份/三个 Agent）不报", not [x for x in got if x[0] == "c.md"])
    check("阴性：局部数量 / 单数 / 豁免 / skills 本体 / 未覆盖对象不报",
          not [x for x in got if x[0] in ("e.md", "f.md", "g.md") or "skills" in x[0]])
    check("退出码 1 且 truths 带出", rc == 1 and d["truths"]["agent"] == 3 and d["truths"]["convention"] == 3)
    p = SCRIPTS
    sys.path.insert(0, str(p))
    import check_cn_count_claims as CN
    (root / "版本变更历史.md").unlink()
    rc2, d2 = _run("check_cn_count_claims.py", root)
    check("非模板仓库 → N/A 不报", rc2 == 0 and d2.get("applicable") is False and d2["violations"] == [])
    check("中文数字解析：十 / 十二 / 二十 / 四十一 / 九", [CN.cn2int(x) for x in ("十", "十二", "二十", "四十一", "九", "一百零五")] == [10, 12, 20, 41, 9, 105])
    shutil.rmtree(root, ignore_errors=True)


def test_stale_phrases():
    print("\n[T] check_stale_phrases.py：陈旧短语黑名单棘轮")
    root = _mkroot()
    _w(root, "版本变更历史.md", "x\n")
    data = root / "phrases.txt"
    data.write_text(
        "# 注释行与空行忽略\n\n"
        r"部署 SOP | {{AIDP_HOME}}/**/*.md;docs/**/*.md | 版本根 README 为唯一入口 | V1.2.2" "\n"
        r"(?<!不要求)每个 Sprint (?:在独立分支|新建分支) | **/*.md | branch_policy 决定 | V1.2.2" "\n"
        r"implement \+ static(?!\s*\+\s*related-test) | docs/**/*.md | 带 related-test | V1.2.2" "\n",
        encoding="utf-8")
    _w(root, ".aidp/commands/a.md", "生成部署 SOP\n默认 `implement + static`\n")           # 命中 1；implement 不在 docs 作用域
    _w(root, "docs/b.md", "默认 `implement + static`\n"                                    # 命中（作用域内）
                          "默认 `implement + static + related-test`\n"                      # 阴性（现行写法）
                          "不要求每个 Sprint 新建分支\n"                                    # 阴性（反面说明）
                          "每个 Sprint 新建分支 <!-- stale-ignore: 历史说明，已改为 branch_policy -->\n"   # 豁免
                          "每个 Sprint 新建分支 <!-- stale-ignore: -->\n")                 # 缺理由 → 仍报
    _w(root, ".aidp/flows/sprint-autopilot/rationale.md", "部署 SOP\n")                    # 全局排除
    _w(root, "docs/superpowers/p.md", "部署 SOP\n")                                        # 全局排除
    _w(root, "memory/.aidp/x/a.md", "部署 SOP\n")                                           # 运行态副本排除
    _w(root, "docs/c.txt", "部署 SOP\n")                                                    # 非 .md 不在 glob
    rc, d = _run("check_stale_phrases.py", root, "--phrases", str(data))
    got = sorted((f["file"], f["line"]) for f in d.get("findings", []))
    check("阳性：作用域内旧口径命中（含无豁免理由的 ignore）",
          got == [(".aidp/commands/a.md", 1), ("docs/b.md", 1), ("docs/b.md", 5)] and rc == 1)
    check("阴性：现行写法 / 反面说明 / 行内 stale-ignore / 排除面 / 非 .md 不误报",
          not any(f["file"] in ("docs/c.txt",) or "rationale" in f["file"] or "superpowers" in f["file"]
                  or f["file"].startswith("memory/") for f in d["findings"]))
    check("findings 带现行替代说明与引入版本",
          all(f.get("replacement") and f.get("since") == "V1.2.2" for f in d["findings"]))
    data.write_text("坏条目只有两段 | **/*.md\n[unclosed | **/*.md | x | V1.2.2\n", encoding="utf-8")
    rc, d = _run("check_stale_phrases.py", root, "--phrases", str(data))
    check("坏条目（字段不足 / 正则不合法）报 bad-entry，不静默跳过",
          rc == 1 and sorted(f["kind"] for f in d["findings"]) == ["bad-entry", "bad-entry"])
    (root / "版本变更历史.md").unlink()
    rc, d = _run("check_stale_phrases.py", root, "--phrases", str(data))
    check("非模板仓库 → N/A", rc == 0 and d.get("applicable") is False)
    shutil.rmtree(root, ignore_errors=True)


def test_self_checks():
    print("\n[X] 三个脚本的 --self-check")
    for s in ("check_code_symbol_refs.py", "check_cli_invocation.py", "check_private_markers.py"):
        p = subprocess.run([sys.executable, str(SCRIPTS / s), "--self-check"], capture_output=True, text=True)
        check(f"{s} --self-check 通过", p.returncode == 0 and "[PASS]" in p.stdout)
    for s in ("check_readme_registry.py", "check_cn_count_claims.py", "check_stale_phrases.py",
              "check_identity_source.py"):
        p = subprocess.run([sys.executable, str(SCRIPTS / s), "--self-check"], capture_output=True, text=True)
        check(f"{s} --self-check 通过", p.returncode == 0 and '"pass"' in p.stdout)


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
    test_identity_scope_agents_and_init()
    test_readme_registry()
    test_cn_count_claims()
    test_stale_phrases()
    test_self_checks()
    print(f"\n══ 结果：{_passed} passed / {_failed} failed ══")
    sys.exit(1 if _failed else 0)
