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
from flow_test_helpers import sprint_dev_text

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
    md = sprint_dev_text("formal-increment")
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
    md = sprint_dev_text("formal-increment")
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
          bool(re.search(r'/version \{PRE_RELEASE_VERSION\} --execution-context "\$PRERELEASE_EXECUTION_CONTEXT" --finalize-docs --unattended', flow)))
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
        if cmd == "sprint-plan":
            dispatch = all(part in t for part in (
                "flow-qr-dispatch.md", "不另列脚本清单", "同revision/inputs真实hash证据",
                "独立子 Agent", "仅补缺失/失效的必要脚本", "不追加未授权非Critical语义QR"))
        else:
            dispatch = "flow-qr-dispatch.md" in t and "原样跑全部脚本" in t
        check("★ %s 回检委派 SKILL 派单块、不另列平行清单" % cmd, dispatch)


def test_batch_cascade_and_bugfix_scope_contracts():
    """父编排不能恢复隐式级联；导入的测试缺陷须与 SKILL 的 Sprint 过滤同域。"""
    print('\n[批量级联与测试缺陷归属契约]')
    batch = (REPO / '.aidp/commands/sprint-batch.md').read_text(encoding='utf-8')
    push = (REPO / '.aidp/flows/sprint-autopilot/phase-3-5b.md').read_text(encoding='utf-8')
    check('batch 不再把显式级联写成逐 Sprint 固定动作',
          '逐 Sprint `--cascade-now`' not in batch
          and '`/sprint-dev --cascade-now` 按 Sprint 即时处理' not in batch)
    check('batch 明确默认攒批且只透传显式 cascade-now',
          '不自动添加 `--cascade-now`' in batch and '[--cascade-now]' in batch)
    check('push 提交门不因积压派发整套级联，CICD 欠账仍补监听',
          '台账积压 → 派台账收口子 Agent' not in push
          and '不因提交门返回欠账而派级联' in push and '补监听' in push)
    mb = (REPO / '.aidp/flows/sprint-bugfix/mode-b.md').read_text(encoding='utf-8')
    skill = (REPO / '.aidp/skills/bugfix/SKILL.md').read_text(encoding='utf-8')
    check('依赖 SKILL 的 Sprint 参数实际过滤 Sprint 列',
          '给了 Sprint 编号 → 仅处理 Sprint 列匹配的条目' in skill)
    check('来源 B 不再无条件留空 Sprint，核实归属后再登记',
          '追加条目的 Sprint 列留空' not in mb
          and '已核实属于指定 Sprint' in mb and 'Sprint 列填该编号' in mb)
    check('未知归属显式范围冲突，不把整版缺陷强绑当前 Sprint',
          'scope-conflict' in mb and '不把整版缺陷强绑当前 Sprint' in mb)
    check('下传范围与导入清单一致，不清空参数绕过过滤',
          '派单前对账' in mb and '不得通过删掉 Sprint 参数扩大修复范围' in mb)
    check('无 Sprint 的零散入口仍可导入留空归属',
          '无 Sprint 过滤' in mb and '可留空' in mb)
    conv = (REPO / '.aidp/reference/skills.md').read_text(encoding='utf-8')
    light = (REPO / '.aidp/flows/sprint-dev/light-context.md').read_text(encoding='utf-8')
    check('bugfix 默认仍产报告文件，light 日常可切 evidence-only 且不写报告（约定集中在 skills.md，两侧只引用）',
          '`file`（默认）' in skill and '`evidence-only`' in skill and '**不写任何 `*-report.md`**' in skill
          and 'bugfix SKILL 调用约定' in conv and 'report_mode=evidence-only' in conv
          and 'bugfix SKILL 调用约定' in mb and 'reference/skills.md' in light
          and 'report_mode=evidence-only' in light and '不能遵守范围/产物边界' in mb)
    check('bugfix 空参数不等于全扫：SKILL 与命令同口径（澄清 / 返回缺口，清单限定范围）',
          '空参数不等于全扫' in skill and '缺少修复范围' in skill and '空参数不等于全扫' in conv
          and '不扫描接管全部历史待修' in (REPO / '.aidp/commands/sprint-bugfix.md').read_text(encoding='utf-8')
          and '修复所有待修复 bug' not in (REPO / '.aidp/commands/sprint-bugfix.md').read_text(encoding='utf-8')
          and '处理全部待修复条目' not in skill)
    check('evidence-only 不得越出调用方给定的问题清单范围',
          '内核不得自行扩大到其他问题记录、其他 Sprint 或其他版本' in skill)
    task_input = skill.split('### light + evidence-only 输入', 1)[-1].split('## 前置条件', 1)[0]
    check('light 修复明确接受父上下文中的真实故障清单，不要求正式台账',
          '### light + evidence-only 输入' in skill
          and all(token in task_input for token in ('execution_context', 'failures', 'write_set', 'acceptance',
                                                     'run_id', 'evidence', '不创建', 'docs/bugfix', '缺少修复范围')))
    check('light SKILL 只读取当前任务证据，不读取历史 Sprint 状态',
          'light 不读取 activeContext/progress' in skill
          and 'light 跳过 2.1 的目录扫描' in skill
          and 'formal/file 的问题记录' in skill)
    check('light 无台账时不制造回填目标，根因结构化证据留在父任务',
          '无原问题记录时不创建状态列或 Commit 列' in skill
          and 'record-outcome' in conv and 'failures' in conv)


def test_vcs_mode_command_contracts():
    print("\n[vcs_mode 命令入口与无 Git 语义]")
    for name in ("sprint-dev", "sprint-test", "sprint-autopilot", "sprint-aiauto-test", "sprint-close", "version"):
        text = (sprint_dev_text("formal-preflight") if name == "sprint-dev" else
                (REPO / f".aidp/commands/{name}.md").read_text(encoding="utf-8"))
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
    command = sprint_dev_text("formal-preflight", "formal-existing")
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
    scope_contract = flow(dev / "incremental-contract.md")
    check("回写阶段消费本地哈希变更",
          all(part in p1 for part in ("development_scope.py", "execution_context", "内容哈希（含新增/删除）", "快照缺失/文件不可读"))
          and 'development_scope.py --root .' in scope_contract
          and '--execution-context "$EXECUTION_CONTEXT"' in scope_contract)


def test_local_file_change_evidence():
    print("\n[无 Git 开发前后文件快照实跑]")
    command = sprint_dev_text("formal-preflight")
    flow = (REPO / ".aidp/flows/sprint-dev/postdev-writeback-1.md").read_text(encoding="utf-8")
    contract = (REPO / ".aidp/flows/sprint-dev/incremental-contract.md").read_text(encoding="utf-8")
    capture = re.search(r'```bash\n(SNAP="memory/\{version\}/\{user\}/sprints/sprint-\{NNN\}-local-before\.json".*?\nfi)\n```', command, re.S)
    compare = next((block for block in re.findall(r'```bash\n(.*?)\n```', contract, re.S)
                    if 'development_scope.py --root .' in block), None)
    check("快照与权威比较脚本可提取", bool(capture and compare and
          'development_scope.py' in flow and 'incremental-contract.md' in flow))
    if not capture or not compare:
        return
    sys.path.insert(0, str(REPO / '.aidp/scripts'))
    import entry_context
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "code").mkdir()
        (root / "code/changed.py").write_text("before", encoding="utf-8")
        (root / "code/removed.py").write_text("remove", encoding="utf-8")
        script = capture.group(1).replace("{version}", "V1.0.0").replace("{user}", "tester").replace("{NNN}", "001")
        result = subprocess.run(["bash", "-e", "-c", script], cwd=root, capture_output=True, text=True)
        check("本地快照脚本可执行", result.returncode == 0)
        snapshot = root / 'memory/V1.0.0/tester/sprints/sprint-001-local-before.json'
        original = snapshot.read_bytes()
        context = entry_context.resolve_context(root, 'sprint-dev', version='V1.0.0', sprint='001',
                                                write_set=['code'])['execution_context']
        frozen = entry_context.load_context(root, context)
        (root / "code/changed.py").write_text("after", encoding="utf-8")
        (root / "code/removed.py").unlink()
        (root / "code/added.py").write_text("add", encoding="utf-8")
        result = subprocess.run(["bash", "-e", "-c", script], cwd=root, capture_output=True, text=True)
        check("重入快照不覆盖开发前态", result.returncode == 0 and snapshot.read_bytes() == original)
        script = compare.replace('{{AIDP_HOME}}', str(REPO / '.aidp'))
        result = subprocess.run(['bash', '-e', '-c', script], cwd=root, capture_output=True, text=True,
                                env={**os.environ, 'EXECUTION_CONTEXT': context, 'DEVELOPMENT_FACTS_JSON': '{}'})
        check("本地差异脚本可执行", result.returncode == 0)
        payload = json.loads(result.stdout) if result.returncode == 0 else {}
        changed = payload.get('scope', {}).get('files', [])
        check("新增修改删除均入清单", set(changed) == {'code/changed.py', 'code/removed.py', 'code/added.py'}
              and 'code/added.py' not in frozen['initial_files']
              and 'code/removed.py' in frozen['initial_files'] and not (root / 'code/removed.py').exists()
              and frozen['initial_files']['code/changed.py'] != entry_context.initial_file_hash(root / 'code/changed.py'))
        missing = subprocess.run(['bash', '-e', '-c', script], cwd=root, capture_output=True, text=True,
                                 env={**os.environ, 'EXECUTION_CONTEXT': '', 'DEVELOPMENT_FACTS_JSON': '{}'})
        check("缺少冻结上下文不能把空 Git diff 当零变化", missing.returncode != 0)


def test_deploy_reuse_registration_contract():
    """test-only 复用部署：开发侧登记、测试侧按「精确相等」放行。

    两侧必须成对，单看一侧都发现不了问题：只登记不识别 → 测试链路每 tick 跳过；
    只识别不登记 → 永远没有可识别的值。判据刻意是**精确相等**（不是「不早于」）：
    部署被回滚或时间戳重写时，后者会错误放行、测到旧代码。
    """
    print("\n[test-only 复用部署的两侧契约]")
    main_flow = (REPO / ".aidp/flows/sprint-autopilot/phase-3-4.md").read_text(encoding="utf-8")
    mint_step = re.search(r"^1\.\s.*?(?=^2\.\s)", main_flow, re.M | re.S)
    check("开发侧：主片步骤1先Read并执行R-1子片，再进入步骤2",
          mint_step is not None
          and "Read `{{AIDP_HOME}}/flows/sprint-autopilot/phase-3-4a.md`" in mint_step.group()
          and "执行" in mint_step.group())
    mint = (REPO / ".aidp/flows/sprint-autopilot/phase-3-4a.md").read_text(encoding="utf-8")
    gate = (REPO / ".aidp/flows/sprint-aiauto-test/phase-0-6.md").read_text(encoding="utf-8")
    check("开发侧：铸 build 时登记 deploy_reuse_of",
          'entry["deploy_reuse_of"]' in mint and 'ENTRY_MODE"' in mint and "test-only" in mint)
    check("开发侧：登记值取自该版本 last_deployed_at",
          'ver.get("last_deployed_at")' in mint)
    check("测试侧：读取 deploy_reuse_of", ".deploy_reuse_of" in gate)
    check("测试侧：精确相等才放行（⛔ 不是「不早于」）",
          '[ "$(_ts "$_REUSE")" = "$(_ts "$_LDP")" ]' in gate)
    check("测试侧：登记失效时退回常规判据（有兜底分支）",
          "_REUSE_OK" in gate and '!= "1"' in gate)
    # 语义对照：相等放行、不等失效
    def pass_gate(reuse, ldp):
        return bool(reuse) and bool(ldp) and reuse == ldp
    check("语义：登记值与当前部署一致 → 放行", pass_gate("T1", "T1") is True)
    check("语义：之后又部署过 → 登记失效", pass_gate("T1", "T2") is False)
    check("语义：从未部署 → 不放行", pass_gate("", "") is False)


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


def _collection_script():
    flow = (REPO / ".aidp/flows/sprint-aiauto-test/phase-3-1.md").read_text(encoding="utf-8")
    block = re.search(r"python3 - \"\$SHOT_DIR\" \"\$\{SHAPE_BAD:-0\}\" <<'SHOTS'\n(.*?)\nSHOTS\n", flow, re.S)
    return block.group(1)


def _valid_png(tag=255):
    import struct
    import zlib

    def chunk(kind, data):
        body = struct.pack(">I", len(data)) + kind + data
        return body + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00" + bytes([tag, tag, tag]))) + chunk(b"IEND", b""))


def test_aiauto_screenshot_collection():
    """归集段消费 check_result --json 的 artifacts：扩展名分类归上游，顺序/覆盖/去旧图/不动门归本段。"""
    print("\n[aiauto 截图归集实跑]")
    code = _collection_script()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        shot = root / "report with spaces/screenshots/B1"
        shot.mkdir(parents=True)

        def collect(artifacts, shape_bad="0"):
            payload = json.dumps({"artifacts": artifacts})
            return subprocess.run([sys.executable, "-c", code, str(shot), shape_bad], cwd=root,
                                  capture_output=True, text=True, env={**os.environ, "CR_JSON": payload})

        def item(rnd, name, kind="screenshot"):
            path = root / f"build-B1/round-{rnd}/evidence/{name}"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"r{rnd}:{name}".encode())
            return {"case_id": name.split("-step")[0], "path": str(path), "ext": path.suffix.lstrip("."), "kind": kind}

        (shot / "TC-1-step1.JPG").write_bytes(b"stale")
        arts = [item(10, "TC-1-step1.webp"), item(2, "TC-1-step1.png"), item(2, "TC-2-step1.jpeg"),
                item(10, "TC-3-step1.jpg"), item(10, "TC-4-step1.PNG"), item(2, "notes.txt", kind="other")]
        r = collect(arts)  # 故意把 round-10 排在 round-2 前：上游 artifacts 就是字符串序
        check("归集代码可执行", r.returncode == 0)
        check("四种截图扩展名均归集，非截图（kind=other）不归集",
              {p.suffix.lower() for p in shot.iterdir()} == {".webp", ".png", ".jpg", ".jpeg"}
              and not (shot / "notes.txt").exists())
        check("round-10 覆盖 round-2（按数字序重排，不依赖 artifacts 顺序）",
              (shot / "TC-1-step1.webp").read_bytes() == b"r10:TC-1-step1.webp")
        check("同主干格式变更不留旧图（含大写扩展名）", len(list(shot.glob("TC-1-step1.*"))) == 1)
        check("未被结果 JSON 引用的孤儿图不归集（artifacts 之外的文件不进报告）",
              not (shot / "orphan.png").exists())
        r = collect([])
        check("本 tick 无新证据时旧目录不能替它过截图门", r.returncode == 0 and not list(shot.iterdir()))
        (shot / "keep.png").write_bytes(b"x")
        r = collect([item(1, "TC-9-step1.png")], shape_bad="1")
        check("结果契约不合（SHAPE_BAD=1）不消费 artifacts，也不动已有目录，缺图交非空核验门",
              r.returncode == 0 and [p.name for p in shot.iterdir()] == ["keep.png"])
        r = subprocess.run([sys.executable, "-c", code, str(shot), "0"], cwd=root, capture_output=True, text=True,
                           env={**os.environ, "CR_JSON": "not json"})
        check("CR_JSON 损坏按无证据处理且不抛异常", r.returncode == 0)

    # 集成：真实 check_result.py 的 --json 输出（含合法 PNG）喂给同一段归集代码
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for rnd, tag in ((2, 20), (10, 100)):
            evidence = root / f"build-B1/round-{rnd}/evidence"
            results = root / f"build-B1/round-{rnd}/results"
            evidence.mkdir(parents=True)
            results.mkdir(parents=True)
            (evidence / "TC-1-step1.png").write_bytes(_valid_png(tag))
            (results / "TC-1.json").write_text(json.dumps({
                "case_id": "TC-1", "title": "t", "status": "pass", "runtimeErrors": [],
                "evidence": [{"step": 1, "artifact": "evidence/TC-1-step1.png", "type": "screenshot", "note": "ok"}]}))
        (root / "build-B1/round-10/evidence/orphan.png").write_bytes(_valid_png(7))
        script = REPO / ".aidp/skills/auto-test-runner/scripts/check_result.py"
        done = subprocess.run([sys.executable, "-I", str(script), "--json", "build-B1/round-2/results/",
                               "build-B1/round-10/results/"], cwd=root, capture_output=True, text=True)
        data = json.loads(done.stdout) if done.stdout.strip() else {}
        check("真实 check_result 输出 artifacts 且无 Critical（夹具合法）",
              data.get("artifacts") and not [i for i in data.get("issues", []) if i.get("level") == "Critical"])
        shot = root / "shots"
        shot.mkdir()
        r = subprocess.run([sys.executable, "-c", code, str(shot), "0"], cwd=root, capture_output=True, text=True,
                           env={**os.environ, "CR_JSON": done.stdout})
        check("真实输出驱动归集：留下最新 round-10 的图，孤儿图不归集",
              r.returncode == 0 and [p.name for p in shot.iterdir()] == ["TC-1-step1.png"]
              and (shot / "TC-1-step1.png").read_bytes() == _valid_png(100))


def test_aiauto_convergence_aggregation():
    """从 flow 提取真实判定代码，喂真实 gen_report 结果，避免复刻判据。"""
    print("\n[aiauto 收敛聚合实跑]")
    raw = (REPO / ".aidp/flows/sprint-aiauto-test/phase-3-3.md").read_text(encoding="utf-8")
    block = re.search(r'> ```bash\n(.*?)> ```', raw, re.S).group(1)
    block = "\n".join(line[2:] if line.startswith("> ") else line for line in block.splitlines())
    # 本函数保留旧无 unitTests 的九类统计场景；联合分支在 test_unit_report 中实跑。
    block = "OPEN_BUGS=" + block.split("\nOPEN_BUGS=", 1)[1]
    block = block.split("\nAUTO_FIXABLE_FOUND=", 1)[0]
    block = "\n".join(line for line in block.splitlines() if not line.startswith('eval "$('))
    block = block.replace("{{AIDP_HOME}}", str(REPO / ".aidp"))
    base = {"case_id": "TC-1", "status": "pass", "execution_mode": "direct",
            "evidence": [{"summary": "实际显示成功"}]}
    cases = (
        ("正常结果", [base], None, 1),
        ("无证据 verified pass", [{**base, "execution_mode": "verified", "evidence": []}], None, 0),
        ("direct pass 缺轻量事实按 SKILL 告警但不阻断", [{**base, "evidence": []}], None, 1),
        ("坏文件不能让 fail 蒸发", [base], "{broken", 0),
        ("合法 JSON 非对象也不能蒸发", [base], "[]", 0),
        ("巡检 block 不抵消真实用例 block", [base, {"case_id": "TC-2", "status": "block",
          "block_reason": "retry-exhausted"}, {"case_id": "运行时-page", "entry_kind": "free-scan",
          "status": "block", "block_reason": "driver-missing"}], None, 0),
        ("环境 block 排除后可收敛", [base, {"case_id": "TC-2", "status": "block",
          "block_reason": "driver-missing"}], None, 1),
        ("precondition-unmet 不自动豁免", [base, {"case_id": "TC-2", "status": "block",
          "block_reason": "precondition-unmet"}], None, 0),
        ("缺聚合器不沿用上次 shell 的通过数", [base], None, 0),
    )
    for label, rows, broken, expected in cases:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            rd = root / "docs/reports/V1.0.0/AI测试报告/build-B1/round-1/results"
            rd.mkdir(parents=True)
            for i, row in enumerate(rows):
                (rd / f"{i}.json").write_text(json.dumps(row), encoding="utf-8")
            if broken is not None:
                (rd / "bad.json").write_text(broken, encoding="utf-8")
            script = block
            if label.startswith("缺聚合器"):
                script = script.replace("GR=" + str(REPO / ".aidp/skills/auto-test-runner/scripts/gen_report.py"),
                                        "GR=/missing-gen-report.py")
            r = subprocess.run(["bash", "-c", 'THIS_ROUND_FAIL_COUNT=0\nTHIS_ROUND_BLOCK=0\n' + script +
                                '\nprintf "\\nCONVERGED=%s\\n" "$CONVERGED"'],
                               cwd=root, capture_output=True, text=True,
                               env={**os.environ, "TARGET_VERSION": "V1.0.0", "BUILD": "B1"})
            check(label, r.returncode == 0 and f"CONVERGED={expected}" in r.stdout)


def test_aiauto_client_mcp_flag():
    """实跑检测桥接：新声明、旧声明、非 Web 与声明冲突均覆盖。"""
    print("\n[aiauto client_mcp 检测桥接实跑]")
    raw = (REPO / ".aidp/flows/sprint-aiauto-test/phase-3-1.md").read_text(encoding="utf-8")
    script = "CR_CLIENT_JSON=" + raw.split("CR_CLIENT_JSON=", 1)[1].split("  CR_JSON=", 1)[0]
    script = script.replace("{{AIDP_HOME}}", str(REPO / ".aidp"))
    # 检测失败路径仍实跑记账，只关闭测试沙箱里的通知出口。
    script = script.replace("/scripts/autopilot_fail_handle.py ", "/scripts/autopilot_fail_handle.py --no-card ")
    fixtures = (
        ("新 Web 声明", "  client_mcp:\n    enabled: true\n    client_type: web\n    implementation: webmcp\n", "--webmcp-enabled"),
        ("旧 Web 声明", "  webmcp:\n    enabled: true\n", "--webmcp-enabled"),
        ("非 Web 已实现", "  client_mcp:\n    enabled: true\n    client_type: mobile\n    implementation: app-native\n", ""),
        ("未声明", "", ""),
        ("冲突不可冒充关闭", "  client_mcp:\n    enabled: true\n    client_type: mobile\n    implementation: app-native\n  webmcp:\n    enabled: true\n", None),
    )
    for label, declaration, expected in fixtures:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            prd = root / "docs/requirements/V1.0.0/产品提供/PRD.md"
            prd.parent.mkdir(parents=True)
            prd.write_text("---\nautopilot_decisions:\n" + declaration + "---\n", encoding="utf-8")
            _mcp_prd(root, 'V2.0.0', '  webmcp:\n    enabled: ' +
                     ('false' if expected == '--webmcp-enabled' else 'true') + '\n')
            r = subprocess.run(["bash", "-c", script + '\nprintf "FLAG=%s\\n" "$CR_WEBMCP"'],
                               cwd=root, capture_output=True, text=True,
                               env={**os.environ, "TARGET_VERSION": "V1.0.0", "BUILD": "B1"})
            check(label, r.returncode == 0 and
                  (("FLAG=" not in r.stdout and "conflict:" in r.stderr) if expected is None
                   else f"FLAG={expected}\n" in r.stdout))


def test_aiauto_report_summary_mapping():
    """执行 flow 的字段桥接代码，确认聚合输出可映射为 SPA summary 且坏统计拒写。"""
    print("\n[aiauto 报告字段映射实跑]")
    raw = (REPO / ".aidp/flows/sprint-aiauto-test/phase-3-2.md").read_text(encoding="utf-8")
    import ast
    code = raw.split("<<'BROWSER_SUMMARY'\n", 1)[1].split("\nBROWSER_SUMMARY", 1)[0]
    node = next(n for n in ast.parse(code).body if isinstance(n, ast.FunctionDef) and n.name == "report_summary")
    mapper = "import json,sys\nfrom pathlib import Path\n" + ast.get_source_segment(code, node) + "\n"
    mapper += ('agg=json.load(sys.stdin)\nsummary=report_summary(agg)\n'
               'path=Path(sys.argv[1]); data=json.loads(path.read_text(encoding="utf-8"))\n'
               'data["summary"]=summary\npath.write_text(json.dumps(data,ensure_ascii=False),encoding="utf-8")\n')
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        results = root / "round-1/results"
        results.mkdir(parents=True)
        for i, status in enumerate(("pass", "fail", "block", "na")):
            data = {"case_id": f"TC-{i}", "status": status, "execution_mode": "direct",
                    "evidence": [{"summary": "已取到实际值"}]}
            (results / f"{i}.json").write_text(json.dumps(data), encoding="utf-8")
        (results / "scan.json").write_text(json.dumps({"case_id": "运行时-page", "entry_kind": "free-scan", "status": "pass"}), encoding="utf-8")
        agg = subprocess.run([sys.executable, str(REPO / ".aidp/skills/auto-test-runner/scripts/gen_report.py"),
                              str(results.parent), "--json"], capture_output=True, text=True)
        target = root / "input.json"
        target.write_text('{"summary":{"total":999},"cases":[]}', encoding="utf-8")
        r = subprocess.run([sys.executable, "-c", mapper, str(target)], input=agg.stdout,
                           capture_output=True, text=True)
        summary = json.loads(target.read_text(encoding="utf-8"))["summary"]
        check("total 来自顶层、四态来自 counts、skip=0、na 排除分母且巡检不混入",
              agg.returncode == 0 and r.returncode == 0 and summary ==
              {"total": 4, "pass": 1, "fail": 1, "block": 1, "skip": 0, "na": 1, "passRate": 0.3333})
        trusted = target.read_bytes()
        payload = json.loads(agg.stdout)
        payload["read_errors"] = [{"file": "broken.json", "error": "unreadable"}]
        r = subprocess.run([sys.executable, "-c", mapper, str(target)], input=json.dumps(payload),
                           capture_output=True, text=True)
        check("read_errors 非空不覆盖既有报告输入", r.returncode != 0 and target.read_bytes() == trusted)


def test_cvl_callsite_contract_details():
    print("\n[CVL 调用边界回归]")
    st = (REPO / ".aidp/commands/sprint-test.md").read_text(encoding="utf-8")
    check("调用方保留检测器 enabled:true 门控字段", "保留 `enabled`" in st)
    check("record-review 证据必填机器证据，不再默认指向日常不生成的 test-report.md",
          "REVIEW_EVIDENCE:?" in st and "REVIEW_EVIDENCE:-" not in st and "sprint-{NNN}-test-report.md}\"" not in st)
    ref = (REPO / ".aidp/reference/SKILL编排层接入.md").read_text(encoding="utf-8")
    sec5 = ref.split("## 五、客户端应用 MCP", 1)[1]
    check("client_mcp 判定配方单一落点：两级判定 + 不传即不启用 + 非 Web 不传 webmcp_*",
          "check_client_mcp.py --version" in sec5 and "check_webmcp.py --version" in sec5
          and "不传 = 该维度" in sec5 and "非 Web **不传 `webmcp_*`**" in sec5 and "保留 `enabled`" in sec5)
    for cmd in ("sprint-requirements", "sprint-plan", "sprint-design", "sprint-selftest", "sprint-test"):
        t = (REPO / f".aidp/commands/{cmd}.md").read_text(encoding="utf-8")
        check(f"{cmd} 接入 client_mcp 检测并引用共用配方", "check_client_mcp.py --version" in t
              and "SKILL编排层接入.md" in t and "enabled: true" in t)
    sec4 = ref.split("## 四、QR 变更范围裁剪", 1)[1].split("## 五、", 1)[0]
    check("qr_delta_scope 协议单一落点，三个规划命令只引用", "不得自造 `qr_mode`" in sec4
          and all("SKILL编排层接入.md" in (REPO / f".aidp/commands/{c}.md").read_text(encoding="utf-8")
                  for c in ("sprint-requirements", "sprint-design", "sprint-plan")))
    check("全部 Important 登记并保留 loop 推进标记，不沿用已解决的上游冲突说明",
          "Critical 与 Important 一律" in st and "登记 bug 与是否阻断是两件事" in st
          and "`loop 推进`" in st and "上游判据冲突，待澄清" not in st)
    check("精简回传保留完整发现与四态，不过滤非阻断 Important",
          "唯一问题编号" in st and "不得只回传阻塞项" in st
          and "各维度 Pass / Fail / 不适用 / 未核验（原因）" in st
          and "仅非阻断 Important 仍按 SKILL 返回的 `不通过` 交接" in st)
    check("终端模板不把未核验一律导向代码修复",
          "未核验（原因）" in st[st.index("code-verification-loop 验收结果："):]
          and "总体结论：{通过 / 不通过" in st and "❌ 需修复" not in st)
    check("基线经 SKILL 正式入参 baseline_ref 传递：有起点传 commit，取不到传 none，不回落本轮错误数，无 Git 明记未核验",
          "baseline_ref=<本 Sprint 起点 commit>" in st and "baseline_ref=none" in st
          and "不回落 `merge-base`" in st and "本轮首跑错误数作基线" in st and "unsupported:vcs-disabled" in st
          and "不得回落 merge-base / 本轮首跑错误数" not in st  # 命令端不再把自己的 prompt 约束说成 SKILL 契约
          and "SKILL 目前没有显式的「无基线」入参" not in st)  # 上游已提供该入参，过期变通不得残留
    check("CVL 以 scope_files 限定当前 task/Sprint，范围无法收窄记未核验且不回退全项目，未核验不得写全部通过",
          "scope_files" in st and "SKILL 范围模式规则" in st and "存在未核验维度" in st
          and "未核验" in st and "不转" in st)
    check("命令端不预判外部脚本维度能否按文件清单运行（能力以脚本与 SKILL 为准）",
          "不支持文件级范围" not in st and "命令端不预判脚本能力" in st
          and "--third-party-mode" not in st.replace("命令端不传 `--third-party-mode`", ""))
    check("移除失效 dimension 链接与首轮错误数作基线的旧指令", "references/dimension-" not in st
          and "首轮记录存量错误数作基线" not in st)
    recheck = st[st.index("## Step 7"):st.index("## 输出")]
    check("复验工具或基线不可用按未核验交接，不误送代码修复",
          "工具未安装标跳过" not in recheck and "非零退出先分类" in recheck
          and "未核验（原因）" in recheck and "不交代码 bugfix" in recheck)
    front = (REPO / ".aidp/agents/frontend.md").read_text(encoding="utf-8")
    check("前端明确预处理器检查不覆盖 import/use 路径", "`@import` / `@use` 路径错**不在**该脚本覆盖内" in front)


def test_incremental_acceptance_contract():
    print('\n[日常累进验收：分档汇合、同轮修复与差量关闭]')
    st = (REPO / '.aidp/commands/sprint-test.md').read_text(encoding='utf-8')
    close = (REPO / '.aidp/commands/sprint-close.md').read_text(encoding='utf-8')
    full = (REPO / '.aidp/commands/sprint-full.md').read_text(encoding='utf-8')
    bugfix = (REPO / '.aidp/commands/sprint-bugfix.md').read_text(encoding='utf-8')
    check('验收显式消费契约卡和权威汇合流程',
          '_sprint-{NNN}-契约卡.md' in st and 'flows/sprint-dev/incremental-contract.md' in st)
    authority = (REPO / '.aidp/flows/sprint-dev/incremental-contract.md').read_text(encoding='utf-8')
    check('M 汇合核修订、真实写集、docs 与获授权的真实 review 结果',
          all(x in st for x in ('contract_revision', '实际写集', 'docs路径', 'docs 完成状态',
                               '已授权 review 的真实结果', '未授权 review 为 NOT_REQUESTED',
                               '任一缺失、仍运行、旧修订或路径仅占位'))
          and '失败、工具不可用、未执行不能算通过' in authority)
    check('S 静态验收不强制补正式用例，required 仍门控',
          'required=false' in st and '四族' in st and 'CASE_REQUIRED' in st)
    check('错误性 Suggestion 同轮归原实现者，等级不变',
          all(x in st for x in ('错误性 Suggestion', '原实现 Agent', '原严重度', '不新起 `/sprint-bugfix`')))
    check('CVL 无虚构 delta 入参，原结论与差量结果分开',
          '不支持 delta 参数' in st and '不得宣称 CVL 二次完整通过' in st)
    check('已修证据允许未提交树 hash，但不能造 SHA',
          '尚未提交' in st and 'after_hash' in st and '不得伪造' in st)
    check('close 零差异不重复审查，缺基线退回验收',
          'review-delta' in close and '零 diff' in close and '无可信 review baseline' in close)
    check('close 保留归档和 cascade_obligation，不重跑全 Sprint 审查',
          'check_cascade_obligation.py' in close and '约定 9' in close
          and '对本 Sprint 的代码与设计进行最终走查' not in close)
    check('full 尊重显式 cascade-now，不无条件开启',
          '[--cascade-now]' in full and '`--cascade-now` 不可省' not in full)
    check('full 与 bugfix 外层仅接管未闭环项，无每轮完整 test',
          all('只接管未闭环项' in text and '不重复完整' in text for text in (full, bugfix))
          and not re.search(r'/sprint-bugfix sprint-.*\n\s*/sprint-test', full + bugfix))
    mode_c = bugfix.split('## 方式 C：', 1)[1].split('## 输出', 1)[0]
    check('bugfix C 委派 sprint-dev 新协议，不重复四层前置',
          'incremental-contract.md' in mode_c and '/sprint-dev "{描述}" --execution-context "$EXECUTION_CONTEXT" skip-test' in mode_c
          and '/sprint-requirements {version} --supplement' not in mode_c)


def test_incremental_contract_resume():
    """直接执行 full 的恢复门，未成正式计划的 S/M 仍保留严格身份与修订校验。"""
    print('\n[S/M 契约卡中断恢复真实示例]')
    full = (REPO / '.aidp/commands/sprint-full.md').read_text(encoding='utf-8')
    match = re.search(r'<!-- resume-gate -->\s*```bash\n(.*?)```', full, re.S)
    check('恢复门可提取', bool(match))
    if not match:
        return
    script = match.group(1).replace('{{AIDP_HOME}}', str(REPO / '.aidp')) \
        .replace('{version}', 'V1.0.0').replace('{NNN}', '001')
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        ctx = root / 'memory/V1.0.0/alice/activeContext.md'
        ctx.parent.mkdir(parents=True)
        ctx.write_text('- 当前 Sprint：Sprint-001\n- contract_revision: 1\n'
                       '- contract_path: docs/design/detail/V1.0.0/_sprint-001-契约卡.md\n'
                       '- 已完成：接口\n', encoding='utf-8')
        before = ctx.read_bytes()
        card = root / 'docs/design/detail/V1.0.0/_sprint-001-契约卡.md'
        card.parent.mkdir(parents=True)
        valid = {'version': 'V1.0.0', 'sprint': '001', 'owner': 'alice',
                 'contract_revision': 1, 'dev_scale': 'M', 'approved_revision': 1,
                 'status': 'approved'}

        def invoke(data):
            card.write_text('# 契约卡\n```aidp-contract\n' + json.dumps(data) + '\n```\n', encoding='utf-8')
            return subprocess.run(['bash', '-c', script], cwd=root, capture_output=True, text=True,
                                  env={**os.environ, 'AIDP_USER': 'alice'})

        result = invoke(valid)
        check('M 已放行卡无正式计划仍可恢复且不重置 activeContext',
              result.returncode == 0 and ctx.read_bytes() == before)
        check('S 已放行卡同样可恢复', invoke({**valid, 'dev_scale': 'S'}).returncode == 0)
        for label, patch in (
            ('未放行', {'status': 'draft'}), ('版本不符', {'version': 'V2.0.0'}),
            ('用户不符', {'owner': 'bob'}), ('编号不符', {'sprint': '002'}),
            ('批准修订过期', {'approved_revision': 0}),
            ('active 修订不符', {'contract_revision': 2, 'approved_revision': 2}),
            ('L 不能借卡省正式计划', {'dev_scale': 'L'}),
            ('布尔不能冒充修订整数', {'contract_revision': True, 'approved_revision': True}),
            ('尚未批准', {'approved_revision': None}),
        ):
            check(label + ' 拒绝恢复', invoke({**valid, **patch}).returncode != 0)
        card.write_text('# 存在但没有放行证据\n', encoding='utf-8')
        result = subprocess.run(['bash', '-c', script], cwd=root, capture_output=True, text=True,
                                env={**os.environ, 'AIDP_USER': 'alice'})
        check('仅存在卡文件不能放行', result.returncode != 0)
        for label, raw in (
            ('坏 JSON', '{broken'),
            ('重复键', json.dumps(valid)[:-1] + ', "owner": "alice"}'),
            ('非 JSON 常量', json.dumps(valid)[:-1] + ', "extra": NaN}'),
            ('多块', json.dumps(valid) + '\n```\n```aidp-contract\n' + json.dumps(valid)),
        ):
            card.write_text('```aidp-contract\n' + raw + '\n```\n', encoding='utf-8')
            result = subprocess.run(['bash', '-c', script], cwd=root, capture_output=True, text=True,
                                    env={**os.environ, 'AIDP_USER': 'alice'})
            check(label + ' 拒绝恢复', result.returncode != 0)
        ctx.write_text(before.decode().replace('contract_path: docs/', 'contract_path: wrong/'), encoding='utf-8')
        check('active 契约路径不符拒绝恢复', invoke(valid).returncode != 0)
        ctx.write_bytes(before)
        other = root / 'memory/V1.0.0/bob/activeContext.md'
        other.parent.mkdir(parents=True)
        other.write_bytes(before)
        check('另一个用户同号在途仍拒绝', invoke(valid).returncode != 0)


def test_acceptance_ledger_command_examples():
    """提取命令正文实跑：Sprint 单测 PASS ≠ review、零变化复用、修改和坏证据阻断。"""
    print('\n[验收/关闭账本命令真实示例]')
    st = (REPO / '.aidp/commands/sprint-test.md').read_text(encoding='utf-8')
    close = (REPO / '.aidp/commands/sprint-close.md').read_text(encoding='utf-8')
    snippets = {}
    for name, text in (('acceptance-sprint-unit', st), ('acceptance-record-review', st),
                       ('close-review-delta', close)):
        match = re.search(r'<!-- ' + name + r' -->\s*```bash\n(.*?)\n```', text, re.S)
        check(name + ' 可提取真实调用', bool(match))
        if match:
            snippets[name] = match.group(1).replace('{{AIDP_HOME}}', str(REPO / '.aidp')) \
                .replace('{version}', 'V1.0.0').replace('{NNN}', '001')
    if len(snippets) != 3:
        return
    sys.path.insert(0, str(REPO / '.aidp/scripts'))
    import entry_context
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)

        def git(*args):
            return subprocess.run(['git', '-C', str(root), *args], check=True,
                                  capture_output=True, text=True).stdout.strip()

        git('init', '-q')
        git('config', 'user.email', 't@example.invalid')
        git('config', 'user.name', 't')
        code = root / 'app.py'
        code.write_text('value = 0\n', encoding='utf-8')
        (root / 'test_app.py').write_text('import unittest\nimport app\nclass AppTest(unittest.TestCase):\n    def test_value(self):\n        self.assertEqual(app.value, 1)\n', encoding='utf-8')
        git('add', '-A')
        git('commit', '-qm', 'base')
        base = git('rev-parse', 'HEAD')
        # 普通开发默认含 related-test；“没有相关测试授权”只能来自用户明确跳过，围栏仍须据此拒绝。
        context = entry_context.resolve_context(root, 'sprint-dev', version='V1.0.0', sprint='001', since=base,
            authorization_source={'kind': 'user-text', 'request_id': 'contract-skip-unit',
                                  'text': '本轮先不执行相关单测', 'skip_actions': ['related-test']})['execution_context']
        code.write_text('value = 1\n', encoding='utf-8')  # 本 Sprint 真实改动：推导出 test_app.py
        # 夹具运行器配置属于工具状态；放根目录会成为真实 JSON 资源覆盖缺口。
        runners = root / 'memory/.aidp/fixture-runners.json'
        runners.write_text(json.dumps([{'suffixes': ['.py'], 'argv': [
            sys.executable, '-B', '-m', 'unittest', '{tests}']}]), encoding='utf-8')
        contract = root / 'docs/design/detail/V1.0.0/_sprint-001-契约卡.md'
        contract.parent.mkdir(parents=True)
        contract.write_text('contract_revision: 1\nAC: value == 1\n', encoding='utf-8')
        scope_dir = root / 'docs/testing/V1.0.0/sprint-001'
        scope_dir.mkdir(parents=True)
        report = scope_dir / 'sprint-001-test-report.md'
        report.write_text('CVL: 通过\nreviewer: 已核 value == 1\n', encoding='utf-8')
        run_set = root / 'docs/testing/V1.0.0/sprint-001/sprint-001-run-set.json'  # 与命令正文同一路径

        def invoke(name, env_id='fixture-static'):
            prelude = (f'TEST_ENV_ID={env_id}\nSINCE={base}\nWRITE_SET=()\n'
                       f'UNIT_RUNNERS_JSON="$(cat {runners})"\n'
                       f'REVIEW_EVIDENCE={report.relative_to(root)}\n')
            result = subprocess.run(['bash', '-e', '-c', prelude + snippets[name]],
                                    cwd=root, capture_output=True, text=True,
                                    env={**os.environ, 'EXECUTION_CONTEXT': context})
            return result

        def run_set_payload():
            try:
                return json.loads(run_set.read_text(encoding='utf-8').strip().splitlines()[-1])
            except (OSError, IndexError, ValueError):
                return {}

        denied = invoke('acceptance-sprint-unit')
        check('formal 身份无相关测试授权仍拒绝真实围栏', denied.returncode != 0
              and 'UNAUTHORIZED' in denied.stdout + denied.stderr and not run_set.exists())
        entry_context.revise_context(root, context, additional_grants=['related-test'],
            authorization_source={'kind': 'user-text', 'request_id': 'contract-unit-fixture',
                                  'text': '执行当前 Sprint 的相关单测'})
        first = invoke('acceptance-sprint-unit')
        payload = run_set_payload()
        check('真实推导并执行 Sprint 单测得到 PASS', first.returncode == 0 and payload.get('status') == 'PASS'
              and len(payload.get('run_ids', [])) == 1)
        reused = invoke('acceptance-sprint-unit')
        again = run_set_payload()
        check('同树同命令 Sprint 单测复用 PASS', reused.returncode == 0 and again['runs'][0].get('reused') is True)
        missing = invoke('close-review-delta')
        check('只有测试 PASS、未审查登记时 close 拒绝', missing.returncode != 0)
        denied = invoke('acceptance-record-review')
        check('测试通过不隐式授予审查登记权限', denied.returncode != 0
              and 'UNAUTHORIZED' in denied.stdout + denied.stderr)
        entry_context.revise_context(root, context, additional_grants=['review'],
            authorization_source={'kind': 'user-text', 'request_id': 'contract-review-fixture',
                                  'text': '登记已完成的当前 Sprint 审查'})
        recorded = invoke('acceptance-record-review')
        check('真实报告显式登记审查基线', recorded.returncode == 0)
        delta, clean = invoke('close-review-delta'), None
        clean = json.loads(delta.stdout.strip().splitlines()[-1]) if delta.stdout.strip() else {}
        check('零 diff 有可验证证据', delta.returncode == 0 and clean.get('code_changed') is False
              and all(clean.get(key) == [] for key in ('added', 'changed', 'removed')))
        memory = root / 'memory/V1.0.0/tester/progress.md'
        memory.parent.mkdir(parents=True)
        memory.write_text('Sprint-001 已归档\n', encoding='utf-8')
        delta = invoke('close-review-delta')
        clean = json.loads(delta.stdout.strip().splitlines()[-1]) if delta.stdout.strip() else {}
        check('close 归档 memory 不抹除既有审查证据', delta.returncode == 0 and clean.get('code_changed') is False)
        contract.write_text('contract_revision: 2\nAC: value == 2\n', encoding='utf-8')
        delta = invoke('close-review-delta')
        dirty = json.loads(delta.stdout.strip().splitlines()[-1]) if delta.stdout.strip() else {}
        check('契约变更进入差量而非被 docs 默认忽略', delta.returncode == 0 and
              str(contract.relative_to(root)) in dirty.get('changed', []))
        contract.write_text('contract_revision: 1\nAC: value == 1\n', encoding='utf-8')
        code.write_text('value = 2\n', encoding='utf-8')
        delta = invoke('close-review-delta')
        dirty = json.loads(delta.stdout.strip().splitlines()[-1]) if delta.stdout.strip() else {}
        check('验收后代码变化可定位', delta.returncode == 0 and 'app.py' in dirty.get('changed', []))
        failed = invoke('acceptance-sprint-unit')
        check('变更导致 Sprint 单测真实失败，不能复用先前 PASS',
              failed.returncode != 0 and run_set_payload().get('status') == 'FAIL')
        # 恢复可信基线后分别破坏报告和环境，避免前一条 FAIL 掩盖这两个负例。
        code.write_text('value = 1\n', encoding='utf-8')
        recovered = invoke('acceptance-sprint-unit')
        rerecorded = invoke('acceptance-record-review')
        check('恢复代码后重新登记可信审查基线', recovered.returncode == 0 and rerecorded.returncode == 0)
        trusted_report = report.read_bytes()
        report.write_text('篡改验收报告\n', encoding='utf-8')
        invalid = invoke('close-review-delta')
        check('报告变化使 close 拒绝旧基线', invalid.returncode != 0)
        report.write_bytes(trusted_report)
        wrong_env = invoke('close-review-delta', 'different-env')
        check('环境变化使 close 拒绝旧基线', wrong_env.returncode != 0)


def _mcp_cli(root, script, *args):
    result = subprocess.run([sys.executable, str(REPO / '.aidp/scripts' / script),
                             '--root', str(root), '--json', *args], capture_output=True, text=True)
    try:
        payload = json.loads(result.stdout)
    except ValueError:
        payload = {}
    return result, payload


def _mcp_prd(root, version, declaration):
    path = root / f'docs/requirements/{version}/产品提供/PRD.md'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('---\nautopilot_decisions:\n' + declaration + '---\n', encoding='utf-8')


def test_mcp_enabled_skill_contract():
    print('\n[MCP 检测输出直传 SKILL 的 enabled 契约]')
    fixtures = (
        ('未声明', '', False, 'not-declared'),
        ('显式关闭', '  client_mcp:\n    enabled: false\n', False, 'explicitly-disabled'),
        ('未实现', '  client_mcp:\n    enabled: true\n    client_type: mobile\n', False, 'declared-unimplemented'),
        ('非 Web', '  client_mcp:\n    enabled: true\n    client_type: mobile\n    implementation: app-native\n', True, 'declared'),
        ('新 Web', '  client_mcp:\n    enabled: true\n    client_type: web\n    implementation: webmcp\n', True, 'declared'),
        ('旧 Web', '  webmcp:\n    enabled: true\n', True, 'declared'),
    )
    for label, declaration, enabled, state in fixtures:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _mcp_prd(root, 'V1.0.0', declaration)
            result, payload = _mcp_cli(root, 'check_client_mcp.py', '--detect')
            check(f'{label}: enabled 与 declared 同值，可直传 SKILL', result.returncode == 0 and
                  payload.get('enabled') is enabled and payload.get('declared') is enabled and
                  payload.get('capability_state') == state)
            if label == '新 Web':
                result, payload = _mcp_cli(root, 'check_webmcp.py', '--detect')
                check('新 Web 声明也启用 Web 适配', result.returncode == 0 and payload.get('enabled') is True)


def test_mcp_version_scope():
    print('\n[MCP 版本作用域：当前覆盖、历史继承与未来隔离]')
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _mcp_prd(root, 'V0.9.0', '  webmcp:\n    enabled: false\n')
        _mcp_prd(root, 'V0.10.0', '  webmcp:\n    enabled: true\n    entry_symbols: [window.CurrentTool]\n')
        _mcp_prd(root, 'V0.11.0', '')
        _mcp_prd(root, 'V0.12.0', '  webmcp:\n    enabled: false\n')
        _mcp_prd(root, 'V0.13.0', '')
        for script in ('check_client_mcp.py', 'check_webmcp.py'):
            for version, expected in (('V0.8.0', False), ('V0.9.0', False), ('V0.10.0', True),
                                      ('V0.11.0', True), ('V0.12.0', False), ('V0.13.0', False)):
                result, payload = _mcp_cli(root, script, '--detect', '--version', version)
                check(f'{script} {version}: 只继承不晚于目标的最近声明',
                      result.returncode == 0 and payload.get('enabled') is expected)
            result, payload = _mcp_cli(root, script, '--detect')
            check(f'{script} 无参兼容按数值最新声明（不取字典序首份）',
                  result.returncode == 0 and payload.get('enabled') is False)
            result, _ = _mcp_cli(root, script, '--detect', '--version', '')
            check(f'{script} 空目标版本不静默回落全局', result.returncode == 2)
        result, payload = _mcp_cli(root, 'check_webmcp.py', '--detect', '--version', 'V0.11.0')
        check('继承的入口标识符与声明来自同一版本', result.returncode == 0 and
              payload.get('entry_symbols') == ['window.CurrentTool'] and 'V0.10.0' in payload.get('symbols_source', ''))
        # 当前非 Web 或未实现声明必须截断旧 Web 能力，不能分别挑两份 PRD。
        for declaration in ('  client_mcp:\n    enabled: true\n    client_type: mobile\n    implementation: bridge\n',
                            '  client_mcp:\n    enabled: true\n    client_type: web\n    implementation: none\n'):
            _mcp_prd(root, 'V0.11.0', declaration)
            result, payload = _mcp_cli(root, 'check_webmcp.py', '--detect', '--version', 'V0.11.0')
            check('当前跨端声明截断历史 Web 启用', result.returncode == 0 and payload.get('enabled') is False)


def test_mcp_environment_scope():
    print('\n[MCP 启动命令、origin 与环境回检同作用域]')
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _mcp_prd(root, 'V0.9.0', '  webmcp:\n    enabled: true\n')
        for version, host in (('V0.9.0', 'old.example'), ('V0.10.0', 'current.example'), ('V0.12.0', 'future.example')):
            path = root / f'docs/testing/{version}/研发自测/01_测试环境与账号.md'
            path.parent.mkdir(parents=True)
            path.write_text(f'| 前端 | https://{host} |\n## WebMCP\n'
                            f'| 完整启动命令 | `chrome --enable-features=WebMCP https://{host}` |\n', encoding='utf-8')
        for version, host in (('V0.9.0', 'old.example'), ('V0.10.0', 'current.example'), ('V0.11.0', 'current.example')):
            result, payload = _mcp_cli(root, 'check_webmcp.py', '--detect', '--version', version)
            check(f'{version} 启动命令不取未来环境', result.returncode == 0 and
                  payload.get('launch_command') == f'chrome --enable-features=WebMCP https://{host}')
            result, payload = _mcp_cli(root, 'check_webmcp.py', '--launch-args', '--version', version)
            check(f'{version} 自动 origin 与启动命令同源', result.returncode == 0 and
                  payload.get('origins') == [f'https://{host}'])
        current = root / 'docs/testing/V0.10.0/研发自测/01_测试环境与账号.md'
        current.write_text('# 当前环境未登记\n', encoding='utf-8')
        result, payload = _mcp_cli(root, 'check_webmcp.py', '--detect', '--version', 'V0.10.0')
        check('当前环境已存在但缺命令时不拿旧命令冒充', result.returncode == 0 and payload.get('launch_command') == '')
        result, payload = _mcp_cli(root, 'check_webmcp.py', '--launch-args', '--version', 'V0.10.0')
        check('当前环境缺 origin 不拿历史或未来 origin 冒充', result.returncode == 2 and
              str(payload.get('error', '')).startswith('no-origin'))
        result, payload = _mcp_cli(root, 'check_webmcp.py', '--version', 'V0.10.0')
        check('装配回检检查目标环境缺段，不能被未来环境放行', result.returncode == 1 and
              any(f.get('check') == 'testenv-section' and 'V0.10.0' in f.get('file', '')
                  for f in payload.get('findings', [])))


def test_mcp_callsite_version_contract():
    print('\n[MCP 实际调用点必须传目标版本并保留 enabled]')
    missing, count = [], 0
    for directory in ('commands', 'flows', 'agents', 'rules', 'templates/optional-rules'):
        for path in (REPO / '.aidp' / directory).rglob('*.md'):
            for match in re.finditer(r'check_(?:client_mcp|webmcp)\.py(?=\s+--)\s+([^`\n]+)',
                                     path.read_text(encoding='utf-8')):
                count += 1
                if '--version' not in match.group(1):
                    missing.append(str(path.relative_to(REPO)))
    check('所有版本内调用携带 --version: ' + ', '.join(sorted(set(missing))), count >= 30 and not missing)
    for command in ('sprint-design', 'sprint-test', 'sprint-selftest', 'sprint-aiauto-test'):
        text = (REPO / f'.aidp/commands/{command}.md').read_text(encoding='utf-8')
        check(f'{command} 明示直传 enabled 字段', 'enabled: true' in text and
              ('保留 `enabled`' in text or '`enabled` / `declared`' in text or '`enabled`/`declared`' in text))
    early = (REPO / '.aidp/flows/sprint-aiauto-test/phase-0-1.md').read_text(encoding='utf-8')
    selected = early.split('# ★★ 版本号轻量预解析', 1)[1].split('TESTPLAN_DIR=', 1)[0]
    check('浏览器分片前将显式 --target 的预解析版本落盘',
          bool(re.search(r'autopilot_tick_flags\.py set --command aiauto-test\s+\\?\s*\n?\s*TARGET_VERSION', selected)))


def main():
    test_batch_cascade_and_bugfix_scope_contracts()
    test_incremental_acceptance_contract()
    test_incremental_contract_resume()
    test_acceptance_ledger_command_examples()
    test_mcp_callsite_version_contract()
    test_mcp_enabled_skill_contract()
    test_mcp_version_scope()
    test_mcp_environment_scope()
    test_aiauto_screenshot_collection()
    test_aiauto_convergence_aggregation()
    test_aiauto_client_mcp_flag()
    test_aiauto_report_summary_mapping()
    test_cvl_callsite_contract_details()
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
    test_deploy_reuse_registration_contract()
    test_sql_isolation_two_track()
    test_skill_ref_freshness_delegation()
    print(f"\n══ 结果：{_passed} passed / {_failed} failed ══")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
