#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""命令 ↔ SKILL 契约与命令域确定性脚本回归。

覆盖：
· check_memory_loss.py 写前快照：未提交的手写内容被整段重写也能检出；迭代级 activeContext/progress 纳入保护；
· 命令文档中脚手架调用可被 scaffold.py 的 argparse 接受（位置参数只有 root）；
· 发布欠账台账 / 版本落点门 fail-closed / 命令↔SKILL 调用契约 / SQL 两轨隔离 / SKILL 脚本委派接线。
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
CML = str(REPO / ".aidp/scripts/check_memory_loss.py")

_passed = _failed = 0


def check(name, cond):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ✅ {name}")
    else:
        _failed += 1
        print(f"  ❌ FAIL: {name}")


def _git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)


def _cml(root, *args):
    return subprocess.run([sys.executable, CML, "--root", str(root), *args],
                          capture_output=True, text=True)


def test_memory_snapshot():
    print("\n[memory-sync 写前快照]")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _git(root, "init", "-q")
        (root / "memory").mkdir()
        body = "# 系统模式\n\n## 架构决策记录\n" + "".join(f"- ADR 行 {i}\n" for i in range(8)) + \
               "\n## 其他\n- x\n"
        (root / "memory/systemPatterns.md").write_text(body, encoding="utf-8")
        _git(root, "add", "-A")
        _git(root, "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-qm", "base")

        # 未提交的手写段落
        hand = body + "\n## 手写未提交段\n" + "".join(f"- 手写 {i}\n" for i in range(6))
        (root / "memory/systemPatterns.md").write_text(hand, encoding="utf-8")
        # 迭代级文件（未入库）
        it = root / "memory/V0.1.0/dev1"
        it.mkdir(parents=True)
        (it / "activeContext.md").write_text("# 上下文\n\n## 已完成工作\n" +
                                            "".join(f"- 完成 {i}\n" for i in range(6)), encoding="utf-8")

        r = _cml(root, "--snapshot")
        check("--snapshot 退出 0", r.returncode == 0)
        snap = root / "memory/.aidp/memory-snapshot"
        check("快照含迭代级 activeContext.md", (snap / "memory/V0.1.0/dev1/activeContext.md").is_file())

        # 整段重写吞掉未提交的手写段
        (root / "memory/systemPatterns.md").write_text(body, encoding="utf-8")
        r = _cml(root, "--json")
        check("★ 阳性：未提交手写段被吞 → exit 1（仅比 HEAD 时判通过）", r.returncode == 1)
        check("报红保留快照", snap.is_dir())

        # 迭代级文件塌缩
        (root / "memory/systemPatterns.md").write_text(hand, encoding="utf-8")
        (it / "activeContext.md").write_text("# 上下文\n", encoding="utf-8")
        r = _cml(root, "--json")
        check("★ 阳性：activeContext.md 段落消失 → exit 1", r.returncode == 1 and "activeContext.md" in r.stdout)

        # 阴性：只追加
        (it / "activeContext.md").write_text("# 上下文\n\n## 已完成工作\n" +
                                            "".join(f"- 完成 {i}\n" for i in range(7)), encoding="utf-8")
        r = _cml(root)
        check("阴性：仅追加 → exit 0", r.returncode == 0)
        check("通过后自动清理快照", not snap.exists())


def test_scaffold_invocations_in_commands():
    print("\n[命令文档中的 scaffold.py 调用可被 argparse 接受]")
    pat = re.compile(r"python3 \{\{AIDP_HOME\}\}/\.\./skills/aidp-code-engineer/scripts/scaffold\.py ([^\n`#]*)")
    hits = 0
    for md in sorted((REPO / ".aidp/commands").glob("*.md")):
        for m in pat.finditer(md.read_text(encoding="utf-8")):
            args = m.group(1).replace("{version}", "V0.1.0").replace("{user}", "dev1") \
                .replace("<mode>", "init").replace("<agents>", "claude").split()
            positional = []
            skip = False
            for i, a in enumerate(args):
                if skip:
                    skip = False
                    continue
                if a.startswith("--"):
                    if a in ("--version", "--user", "--mode", "--agent", "--name-cn",
                             "--adapter-mode", "--keep-backups", "--keep-days"):
                        skip = True
                    continue
                positional.append(a)
            hits += 1
            check(f"{md.name}: `{m.group(1).strip()}` 位置参数 ≤ 1", len(positional) <= 1)
    check("至少命中一处调用", hits > 0)


def test_release_debt_ledger():
    print("\n[发布欠账台账：唯一写入口 + 状态字段 + 终态落账门]")
    r = subprocess.run([sys.executable, str(REPO / ".aidp/scripts/release_debt.py"), "--self-check"],
                       capture_output=True, text=True)
    check("release_debt.py --self-check 通过（幂等 / resolve / gate）", r.returncode == 0)
    flows = list((REPO / ".aidp/flows/version").glob("*.md")) + [REPO / ".aidp/commands/version.md"]
    raw = [f.name for f in flows if re.search(r'>>\s*"?docs/audit/[^"\n]*发布欠账\.md', f.read_text(encoding="utf-8"))]
    check("★ version 流程无手写 `>> 发布欠账.md`（一律经 release_debt.py）", raw == [])
    r7 = (REPO / ".aidp/flows/version/release-7.md").read_text(encoding="utf-8")
    check("★ Step 3.4.1 提交前跑终态落账门", "release_debt.py gate" in r7 and "--register-missing" in r7)


def test_released_version_gate_fail_closed():
    print("\n[sprint-dev 版本落点门：tag 判定失败 fail-closed]")
    md = (REPO / ".aidp/commands/sprint-dev.md").read_text(encoding="utf-8")
    m = re.search(r"\*\*① 检测「当前版本已发布[^\n]*\n```bash\n(.*?)```", md, re.S)
    check("找到版本落点检测 bash 块", bool(m))
    if not m:
        return
    with tempfile.TemporaryDirectory() as td:
        script = "V=V0.2.0\n" + m.group(1).split("\n", 1)[1]
        r = subprocess.run(["bash", "-c", script], cwd=td, capture_output=True, text=True,
                           env={**os.environ, "GIT_DIR": os.path.join(td, "nope")})
        check("★ 非 git 仓库（TAG_OK=0）→ RELEASED 非空，进决策门而非静默累进",
              "RELEASED=unknown(tag-query-failed)" in r.stdout)


def test_skill_invocation_contracts():
    print("\n[命令 ↔ SKILL 调用契约]")
    st = (REPO / ".aidp/commands/sprint-test.md").read_text(encoding="utf-8")
    cvl = (REPO / ".aidp/skills/code-verification-loop/SKILL.md").read_text(encoding="utf-8")
    check("★ /sprint-test 以仅验收模式调 CVL", "mode=verify-only" in st)
    check("★ CVL SKILL 提供 verify-only 模式", "verify-only" in cvl)
    bf = (REPO / ".aidp/skills/bugfix/SKILL.md").read_text(encoding="utf-8")
    check("★ bugfix SKILL 允许无 Sprint 编号（零散模式）", "Sprint 编号（可选）" in bf and "零散模式" in bf)
    mb = (REPO / ".aidp/flows/sprint-bugfix/mode-b.md").read_text(encoding="utf-8")
    check("★ 方式 B 先把来源 B 落成 bugfix 条目再调 SKILL", "来源 B · 问题汇总清单" in mb and "唯一的输入面" in bf)
    check("★ 方式 B 不在 SKILL 修完后再调 systematic-debugging", "对每个 bug 调用 `superpowers:systematic-debugging`" not in mb)
    sd = (REPO / ".aidp/flows/sprint-design/step-2to4-架构补充与SQL-2.md").read_text(encoding="utf-8")
    check("★ /sprint-design 不再整体复制前版增量 SQL", "整体复制" not in sd and "不复制前版" in sd)
    sel = (REPO / ".aidp/commands/sprint-selftest.md").read_text(encoding="utf-8")
    check("★ selftest 无人值守占位符与 SKILL / check_testdata_prereq 同格式", "<待填写>" not in sel and "{待用户填写:" in sel)
    for cmd in ("sprint-design", "sprint-plan", "sprint-selftest"):
        t = (REPO / (".aidp/commands/%s.md" % cmd)).read_text(encoding="utf-8")
        if cmd == "sprint-design":
            t = (REPO / ".aidp/flows/sprint-design/step-1.6-落盘后回检.md").read_text(encoding="utf-8")
        check("★ %s 回检委派 SKILL 派单块、不另列平行清单" % cmd,
              "flow-qr-dispatch.md" in t and "原样跑全部脚本" in t)


def test_vcs_mode_command_contracts():
    print("\n[vcs_mode 命令入口与无 Git 语义]")
    for name in ("sprint-dev", "sprint-test", "sprint-autopilot", "sprint-aiauto-test", "sprint-close", "version"):
        text = (REPO / f".aidp/commands/{name}.md").read_text(encoding="utf-8")
        check(f"{name} 消费 vcs_mode=git|none", "vcs_mode" in text and "git|none" in text)
        check(f"{name} 无 Git 留痕 unsupported:vcs-disabled", "unsupported:vcs-disabled" in text)
    version = (REPO / ".aidp/commands/version.md").read_text(encoding="utf-8")
    check("version 非 Git 发布禁止宣布 released", "vcs_mode=none" in version and "不得宣布已发布" in version)
    close = (REPO / ".aidp/commands/sprint-close.md").read_text(encoding="utf-8")
    check("close 非 Git 本地归档允许完成但发布不通过", "本地归档" in close and "发布" in close)


def test_vcs_disabled_downstream_contracts():
    print("\n[无 Git 下游门禁与本地变更证据]")
    auto = REPO / ".aidp/flows/sprint-autopilot"
    dev = REPO / ".aidp/flows/sprint-dev"
    def flow(path):
        return path.read_text(encoding="utf-8")

    p09 = flow(auto / "phase-0-9.md")
    p35 = flow(auto / "phase-3-5.md")
    p36 = flow(auto / "phase-3-6.md")
    p38 = flow(auto / "phase-3-8.md")
    p39 = flow(auto / "phase-3-9.md")
    p1 = flow(dev / "postdev-writeback-1.md")
    p2 = flow(dev / "postdev-writeback-2.md")
    command = flow(REPO / ".aidp/commands/sprint-dev.md")
    version = flow(REPO / ".aidp/commands/version.md")
    check("0.7 Git 必需性按 vcs_mode 分支", "仅 `vcs_mode=git`" in p09 and "不得报错退出" in p09)
    check("3.2 云游标由 Git 能力约束", '"${VCS_MODE:-git}" = "git"' in p35)
    check("3.2.1 保留无 Git 本地部署就绪", "mode=local" in p36 and "本地就绪" in p36)
    check("3.4 无部署不委派浏览器", "DEPLOY_READY" in p38 and "vcs_mode=none" in p38)
    check("3.4 前端覆盖度消费本地变更证据", "CHANGES_ROOT" in p38 and 'startswith("code/frontend/")' in p38)
    check("3.4 门禁无部署不等待测试", "DEPLOY_READY" in p39 and "vcs_mode=none" in p39)
    check("finalize-docs 未知发布状态不改写", "--finalize-docs" in version and "无法核实已发布状态" in version)
    check("死代码无 Git 使用文件删除", "vcs_mode=none" in command and "Path.unlink" in command)
    check("开发入口留代码快照", "-local-before.json" in command)
    check("回写阶段消费本地哈希变更", "-local-before.json" in p1 and "sha256" in p1)
    check("配置清单消费本地哈希变更", "-local-before.json" in p2 and "sha256" in p2)


def test_local_file_change_evidence():
    print("\n[无 Git 开发前后文件快照实跑]")
    command = (REPO / ".aidp/commands/sprint-dev.md").read_text(encoding="utf-8")
    flow = (REPO / ".aidp/flows/sprint-dev/postdev-writeback-1.md").read_text(encoding="utf-8")
    capture = re.search(r'```bash\n(SNAP="memory/\{version\}/\{user\}/sprints/sprint-\{NNN\}-local-before\.json".*?\nfi)\n```', command, re.S)
    compare = re.search(r'```bash\n(SNAP="memory/\{version\}/\{user\}/sprints/sprint-\{NNN\}-local-before\.json".*?\nPY)\n\s*```', flow, re.S)
    check("快照与比较脚本可提取", bool(capture and compare))
    if not capture or not compare:
        return
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "code").mkdir()
        (root / "code/changed.py").write_text("before", encoding="utf-8")
        (root / "code/removed.py").write_text("remove", encoding="utf-8")
        for script in (capture.group(1), compare.group(1)):
            if script == compare.group(1):
                (root / "code/changed.py").write_text("after", encoding="utf-8")
                (root / "code/removed.py").unlink()
                (root / "code/added.py").write_text("add", encoding="utf-8")
            script = script.replace("{version}", "V1.0.0").replace("{user}", "tester").replace("{NNN}", "001")
            r = subprocess.run(["bash", "-e", "-c", script], cwd=td, capture_output=True, text=True)
            check("本地快照脚本可执行" if script.startswith("SNAP=") and "if [ ! -f" in script else "本地差异脚本可执行", r.returncode == 0)
        out = root / "memory/V1.0.0/tester/sprints/sprint-001-local-changes.json"
        changes = json.loads(out.read_text(encoding="utf-8")) if out.exists() else []
        check("新增修改删除均入清单", {x["kind"] for x in changes} == {"added", "modified", "deleted"})


def test_sql_isolation_two_track():
    print("\n[SQL 版本隔离门识别两轨布局]")
    sc = REPO / ".aidp/skills/dev-logic-architect/scripts/check_sql_version_isolation.py"
    r = subprocess.run([sys.executable, str(sc), "--self-check"], capture_output=True, text=True)
    check("check_sql_version_isolation.py --self-check 通过", r.returncode == 0)
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "docs/deployment"
        ddl = "CREATE TABLE IF NOT EXISTS t_order (\n" + ",\n".join(
            "  biz_field_%d VARCHAR(64) NOT NULL COMMENT '业务字段%d'" % (i, i) for i in range(12)) + "\n);\n"
        for v in ("V0.1.0", "V0.2.0"):
            d = root / v / "sql/增量"
            d.mkdir(parents=True)
            (d / "01_基线表DDL.sql").write_text(ddl, encoding="utf-8")
        r = subprocess.run([sys.executable, str(sc), str(root), "--version", "V0.2.0", "--prev", "V0.1.0"],
                           capture_output=True, text=True)
        check("★ 两轨布局下复制前版增量 SQL → 非 0（不再恒绿）", r.returncode != 0)


def test_skill_ref_freshness_delegation():
    print("\n[SKILL 脚本接线：委派派单块视为接线]")
    sys.path.insert(0, str(REPO / ".aidp/scripts"))
    import importlib
    M = importlib.import_module("check_skill_ref_freshness")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        sk = root / ".aidp/skills/demo-skill"
        (sk / "scripts").mkdir(parents=True)
        (sk / "references").mkdir()
        (sk / "SKILL.md").write_text("---\nname: demo-skill\n---\n", encoding="utf-8")
        for n in ("check_a.py", "check_b.py"):
            (sk / "scripts" / n).write_text("print(1)\n", encoding="utf-8")
        (sk / "references/flow-qr-dispatch.md").write_text("python3 <SKILL_DIR>/scripts/check_a.py x\n", encoding="utf-8")
        (root / ".aidp/commands").mkdir(parents=True)
        cmd = root / ".aidp/commands/x.md"
        cmd.write_text("无接线\n", encoding="utf-8")
        truth = M.load_truth(root / ".aidp/skills")
        before = {s for _, s in M.unreferenced_scripts(root, truth)}
        cmd.write_text("按 `.aidp/skills/demo-skill/references/flow-qr-dispatch.md` 原样跑全部脚本\n", encoding="utf-8")
        after = {s for _, s in M.unreferenced_scripts(root, truth)}
        check("阴性对照：未委派时两脚本都报未接线", before == {"check_a.py", "check_b.py"})
        check("★ 委派后派单块内脚本视为接线、块外脚本仍报", after == {"check_b.py"})


def main():
    test_memory_snapshot()
    test_scaffold_invocations_in_commands()
    test_release_debt_ledger()
    test_released_version_gate_fail_closed()
    test_skill_invocation_contracts()
    test_vcs_mode_command_contracts()
    test_vcs_disabled_downstream_contracts()
    test_local_file_change_evidence()
    test_sql_isolation_two_track()
    test_skill_ref_freshness_delegation()
    print(f"\n══ 结果：{_passed} passed / {_failed} failed ══")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
