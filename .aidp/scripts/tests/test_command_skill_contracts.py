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
import textwrap
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
    # 运行根降层后脚手架 skill 就在 `{{AIDP_HOME}}/skills/` 下，那层 `../` 是嵌套结构的产物、已收敛。
    # 两种写法都收：仓库里还可能残留旧形态，漏掉就等于本门空跑。
    pat = re.compile(
        r"python3 \{\{AIDP_HOME\}\}/(?:\.\./)?skills/aidp-code-engineer/scripts/scaffold\.py ([^\n`#]*)")
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
    check("正式发布首次 poll 绑定本次 push SHA",
          bool(re.search(r'--mode poll --run-id "\$RUN_ID"\s*\\\n\s*--commit "\$PUSH_COMMIT"', r7)))


def test_released_version_gate_fail_closed():
    print("\n[sprint-dev 版本落点门：tag 判定失败 fail-closed]")
    md = (REPO / ".aidp/commands/sprint-dev.md").read_text(encoding="utf-8")
    m = re.search(r"\*\*① 检测「当前版本已发布[^\n]*\n```bash\n(.*?)```", md, re.S)
    check("找到版本落点检测 bash 块", bool(m))
    if not m:
        return
    with tempfile.TemporaryDirectory() as td:
        script = "VCS_MODE=git\nV=V0.2.0\n" + m.group(1).split("\n", 1)[1]
        r = subprocess.run(["bash", "-c", script], cwd=td, capture_output=True, text=True,
                           env={**os.environ, "GIT_DIR": os.path.join(td, "nope")})
        check("★ 非 git 仓库（TAG_OK=0）→ RELEASED 非空，进决策门而非静默累进",
              "RELEASED=unknown(tag-query-failed)" in r.stdout)


def test_released_version_gate_without_git():
    print("\n[sprint-dev 无 Git 版本落点门]")
    md = (REPO / ".aidp/commands/sprint-dev.md").read_text(encoding="utf-8")
    m = re.search(r"\*\*① 检测「当前版本已发布[^\n]*\n```bash\n(.*?)```", md, re.S)
    check("找到无 Git 版本落点检测块", bool(m))
    if not m:
        return
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "bin").mkdir()
        (root / "bin/git").write_text("#!/bin/sh\nprintf '%s\\n' \"$*\" >> git-calls\nexit 1\n", encoding="utf-8")
        (root / "bin/git").chmod(0o755)
        script = 'VCS_MODE=none\nV=V0.2.0\n' + m.group(1).split("\n", 1)[1]
        env = {**os.environ, "PATH": str(root / "bin") + os.pathsep + os.environ["PATH"]}

        def run():
            return subprocess.run(["bash", "-c", script], cwd=root, capture_output=True, text=True, env=env)

        unknown = run()
        check("无 Git 未知发布状态进入落点门", "RELEASED=unknown(" in unknown.stdout)
        check("无 Git 状态检测不调用任何 git 命令", not (root / "git-calls").exists())

        progress = root / "memory/V0.2.0/dev1/progress.md"
        progress.parent.mkdir(parents=True)
        progress.write_text("# 版本历史\nV0.2.0 ✅ 已发布\n", encoding="utf-8")
        released = run()
        check("无 Git 按版本目录中的本地发布记录拦截", "RELEASED=V0.2.0(状态已发布)" in released.stdout)
        check("本地发布记录检查不借道 git config", not (root / "git-calls").exists())
        progress.write_text("# 版本历史\nV0.2.0 未发布\n", encoding="utf-8")
        unreleased = run()
        check("明确本地未发布状态允许正常累进", "RELEASED=\n" in unreleased.stdout)
        progress.write_text("V0.2.0 ✅ 已发布\nV0.2.0 未发布\n", encoding="utf-8")
        conflicting = run()
        check("本地发布记录冲突时 fail-closed", "RELEASED=unknown(local-release-state-conflict)" in conflicting.stdout)
    gate = md.split("**③ `RELEASED` 非空", 1)[1].split("### Phase 0B.1", 1)[0]
    check("未知状态无人值守不自行选 patch", "`RELEASED=unknown(...)`" in gate and
          "不使用下方已确认发布版本的默认 patch 路径" in gate)


def test_autopilot_local_archive_contract():
    print("\n[autopilot 无 Git S2 本地归档]")
    flow = (REPO / ".aidp/flows/sprint-autopilot/phase-2.md").read_text(encoding="utf-8")
    check("S2 无 Git 显式走本地文档整理", "vcs_mode=none" in flow and
          "/version {PRE_RELEASE_VERSION} --finalize-docs --unattended" in flow)
    check("无 Git 不走 --no-tag 发布路径", "无 Git 不走正式发布的 `--no-tag` 路径" in flow)
    check("本地整理失败不写归档成功状态", "internal_released_at" in flow and
          "本地归档失败" in flow and "PRERELEASE_HOLD=1" in flow)
    check("无 Git 正式发布仍不支持", "unsupported:vcs-disabled" in flow and "正式发布" in flow)


def test_selftest_move_contract():
    print("\n[sprint-selftest 无 Git / 未跟踪 / 已跟踪迁移与失败保护]")
    text = (REPO / ".aidp/flows/sprint-selftest/step-1-2.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```bash\n(.*?)\n```", text, re.S)
    supplement = re.search(r"(?m)^  selftest_move\(\) \{\n(.*?)\n\n落盘：", text, re.S)
    check("归一与补充脚本均可提取", len(blocks) == 1 and bool(supplement))
    if len(blocks) != 1 or not supplement:
        return
    scripts = (blocks[0], textwrap.dedent("  selftest_move() {\n" + supplement.group(1)))

    for index, label in enumerate(("归一", "补充")):
        for mode in ("none", "untracked", "tracked", "collision", "mv-error"):
            with tempfile.TemporaryDirectory() as td:
                root = Path(td)
                base = root / "docs/testing/V1.0.0"
                source = base / ("项目名/01_研发自测方案.md" if index == 0 else "研发自测用例.md")
                destination = base / ("研发自测/01_研发自测方案.md" if index == 0 else "研发自测/02_全量自测用例.md")
                source.parent.mkdir(parents=True)
                if index == 0:
                    destination.parent.mkdir(parents=True)
                source.write_text("原件", encoding="utf-8")
                if index == 0:
                    source.with_name("02_全量自测用例.md").write_text("用例", encoding="utf-8")
                if mode in ("untracked", "tracked"):
                    _git(root, "init", "-q")
                    if mode == "tracked":
                        _git(root, "add", "--", str(source.relative_to(root)))
                collision_target = destination if index == 0 else base / "研发自测.md"
                if mode == "collision":
                    collision_target.parent.mkdir(parents=True, exist_ok=True)
                    collision_target.write_text("已有文件", encoding="utf-8")
                env = os.environ.copy()
                if mode == "mv-error":
                    bin_dir = root / "bin"
                    bin_dir.mkdir()
                    stub = bin_dir / "mv"
                    stub.write_text("#!/bin/sh\nexit 42\n", encoding="utf-8")
                    stub.chmod(0o755)
                    env["PATH"] = str(bin_dir) + os.pathsep + env["PATH"]
                script = scripts[index].replace("{version}", "V1.0.0")
                result = subprocess.run(["bash", "-c", script], cwd=root,
                                        capture_output=True, text=True, env=env)
                if mode in ("none", "untracked", "tracked"):
                    check(f"{label} {mode} 文件迁移成功", result.returncode == 0 and
                          destination.is_file() and destination.read_text(encoding="utf-8") == "原件" and
                          not source.exists())
                    if mode == "tracked":
                        check(f"{label} 已跟踪文件保留 Git 索引迁移",
                              bool(_git(root, "diff", "--cached", "--name-status").stdout.strip()))
                else:
                    check(f"{label} {mode} 硬停并保留源与目标", result.returncode != 0 and
                          source.is_file() and source.read_text(encoding="utf-8") == "原件" and
                          (mode != "collision" or collision_target.read_text(encoding="utf-8") == "已有文件"))

    for old, new in (("00_研发自测方案.md", "01_研发自测方案.md"),
                     ("全量自测用例-旧版.md", "02_全量自测用例.md"),
                     ("增量自测用例-旧版.md", "02_增量自测用例.md"),
                     ("02_旧总览.md", "02_自测用例-总览.md")):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dst = root / "docs/testing/V1.0.0/研发自测"
            dst.mkdir(parents=True)
            (dst / old).write_text("旧产物", encoding="utf-8")
            if old != "00_研发自测方案.md":
                (dst / "01_研发自测方案.md").write_text("方案", encoding="utf-8")
                (dst / "02_全量自测用例.md" if old == "02_旧总览.md" else dst / "02_自测用例-总览.md").write_text("用例", encoding="utf-8")
            else:
                (dst / "02_全量自测用例.md").write_text("用例", encoding="utf-8")
            result = subprocess.run(["bash", "-c", scripts[0].replace("{version}", "V1.0.0")],
                                    cwd=root, capture_output=True, text=True)
            check(f"归一别名 {old} 迁移到 {new}", result.returncode == 0 and
                  (dst / new).read_text(encoding="utf-8") == "旧产物" and not (dst / old).exists())

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        dst = root / "docs/testing/V1.0.0/研发自测"
        dst.mkdir(parents=True)
        legacy = dst / "00_研发自测方案.md"
        current = dst / "01_研发自测方案.md"
        legacy.write_text("旧方案", encoding="utf-8")
        current.write_text("现有方案", encoding="utf-8")
        (dst / "02_全量自测用例.md").write_text("用例", encoding="utf-8")
        result = subprocess.run(["bash", "-c", scripts[0].replace("{version}", "V1.0.0")],
                                cwd=root, capture_output=True, text=True)
        check("归一旧方案与新方案并存时硬停且两文件保持原样",
              result.returncode != 0 and legacy.read_text(encoding="utf-8") == "旧方案" and
              current.read_text(encoding="utf-8") == "现有方案")

    for old in ("研发自测用例", "研发自测用例-补充-01.md", "研发自测-补充-01.md"):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            base = root / "docs/testing/V1.0.0"
            base.mkdir(parents=True)
            source = base / old
            if old == "研发自测用例":
                source.mkdir()
                (source / "00_索引.md").write_text("原件", encoding="utf-8")
                target = base / "研发自测/00_索引.md"
            else:
                source.write_text("原件", encoding="utf-8")
                target = base / "研发自测" / old
            result = subprocess.run(["bash", "-c", scripts[1].replace("{version}", "V1.0.0")],
                                    cwd=root, capture_output=True, text=True)
            check(f"补充旧布局 {old} 迁移成功", result.returncode == 0 and
                  target.read_text(encoding="utf-8") == "原件" and not source.exists())


def test_skill_invocation_contracts():
    print("\n[命令 ↔ SKILL 调用契约]")
    st = (REPO / ".aidp/commands/sprint-test.md").read_text(encoding="utf-8")
    cvl = (REPO / ".aidp/skills/code-verification-loop/SKILL.md").read_text(encoding="utf-8")
    check("★ /sprint-test 以仅验收模式调 CVL", "mode=verify-only" in st)
    check("★ CVL SKILL 提供 verify-only 模式", "verify-only" in cvl)
    check("G-TEST-1 在线接口结果不参与静态验收结论",
          "在线结果不参与静态验收结论" in st
          and "不一致项按 Critical 转写 bug 记录" not in st)
    batch = (REPO / ".aidp/commands/sprint-batch.md").read_text(encoding="utf-8")
    check("G-BATCH-1 顶层循环不调用会停下征询的 executing-plans",
          "superpowers:executing-plans" not in batch
          and "for NNN in 执行列表" in batch and "plan_sprints.py" in batch)
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
    p2 = flow(auto / "phase-2.md")
    check("准发布双门无 Git 不读取 HEAD",
          'if [ "$VCS_MODE" = "git" ]; then' in p2
          and '--extra "unconverged_frozen_head=$FROZEN_HEAD"' in p2)
    p35 = flow(auto / "phase-3-5.md")
    p36 = flow(auto / "phase-3-6.md")
    p38 = flow(auto / "phase-3-8.md")
    p39 = flow(auto / "phase-3-9.md")
    p1 = flow(dev / "postdev-writeback-1.md")
    p2 = flow(dev / "postdev-writeback-2.md")
    command = flow(REPO / ".aidp/commands/sprint-dev.md")
    version = flow(REPO / ".aidp/commands/version.md")
    aiauto_freeze = flow(REPO / ".aidp/flows/sprint-aiauto-test/phase-3-3b.md")
    check("测试链路冻结仅在 Git 模式读取 HEAD",
          'if [ "$VCS_MODE" = "git" ]; then' in aiauto_freeze
          and 'FROZEN_HEAD="$(git rev-parse HEAD' in aiauto_freeze
          and 'unconverged_frozen_head "$FROZEN_HEAD"' in aiauto_freeze)
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
    test_released_version_gate_without_git()
    test_autopilot_local_archive_contract()
    test_selftest_move_contract()
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
