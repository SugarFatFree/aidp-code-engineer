#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发布域门禁回归：增量轨存在性 / 只读采集方式 / 零残留断言发布总闸 / 推送状态如实渲染。

四项都属同一族缺口——**「做过」与「没做过」在产物上完全同形**：
· 增量轨：`check_increment_terseness` 首行 `if not inc.is_dir(): return` ⇒
  从未产增量轨的版本，12 项门照样打「🎉 无 ERROR」放行发布；
· 只读采集：G-RELEASE-2 的「全程只读」半条此前零落点（全仓 grep「只读」在该脚本命中 0）；
· 零残留总闸：release-7.md 写着「⛔ 不接受任何 skipped」，`version.md` 骨架表照抄，
  **让它在骨架层看起来像硬门**，实际无执行体、无判定器、无阻断力；
· 推送状态：报告恒写「已创建并自动推送」，于是「tag 未创建」欠账与「发布成功·已推送」同屏出现。
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
RBC = str(REPO / ".aidp/scripts/release_baseline_check.py")
RRG = str(REPO / ".aidp/scripts/check_release_residual_gate.py")
SQL_FLOW = REPO / ".aidp/flows/sprint-design/step-2to4-架构补充与SQL-2.md"
PLAN_FLOW = REPO / ".aidp/flows/version/planning-4.md"

_passed = _failed = 0


def check(name, cond):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ✅ {name}")
    else:
        _failed += 1
        print(f"  ❌ FAIL: {name}")


def _mk_version_dir(root, *, inc_content=True, zero_decl=False, readonly_decl=True):
    """造一个最小可判定的 docs/deployment/V0.1 双轨目录。"""
    v = root / "docs/deployment/V0.1"
    for sub in ("sql/全量", "配置文件/全量", "sql/增量", "配置文件/增量"):
        (v / sub).mkdir(parents=True, exist_ok=True)
    idx = "# 索引\n\n全新部署走全量轨，升级走增量轨，两套绝不叠加执行。\n"
    if zero_decl:
        idx += "\n本版无增量：配置中心在该区间无变更记录，SQL 亦无 DDL。\n"
    (v / "README.md").write_text(idx, encoding="utf-8")
    # ⛔ 全量轨判据读的是**各全量子目录自己的**说明文件（建表说明.md / 配置说明.md），不是版本级那份
    #   （第一次写对照时就栽在这里：夹具写了版本级索引，判据一条都没跑到、阳性对照假绿）
    full_idx = "# 全量索引\n本版无剔除项（已交叉核对）。导出源：192.0.2.20:5236 schema=APP。\n"
    if readonly_decl:
        full_idx += "DDL 经 INFORMATION_SCHEMA 元数据视图只读导出；配置经配置中心只读 API 拉取。\n"
    for sub, doc in (("sql/全量", "建表说明.md"), ("配置文件/全量", "配置说明.md")):
        (v / sub / doc).write_text(full_idx, encoding="utf-8")
    if inc_content:
        (v / "sql/增量/01_加列.sql").write_text("ALTER TABLE T ADD COLUMN X INT;\n", encoding="utf-8")
        (v / "配置文件/增量/配置项清单.md").write_text("```yaml\na: b\n```\n", encoding="utf-8")
    return v


def _rbc(root, grep):
    cp = subprocess.run([sys.executable, RBC, "--root", str(root), "--version", "V0.1"],
                        capture_output=True, text=True)
    out = cp.stdout + cp.stderr
    return [l for l in out.splitlines() if grep in l]


def test_increment_presence():
    """增量轨存在性：空是合法的，空得没有交代不是。"""
    print("\n[R1] 增量轨存在性（约定 37.2 两轨对称 + 37.5-7 零变更显式成文）")
    d = Path(tempfile.mkdtemp())
    _mk_version_dir(d, inc_content=False, zero_decl=False)
    hits = _rbc(d, "增量轨存在性")
    check("★ 阳性：增量轨为空且索引无零变更声明 → ERROR（此前 12 项门全绿放行）",
          any("❌" in h for h in hits) and len([h for h in hits if "❌" in h]) == 2)
    shutil.rmtree(d, ignore_errors=True)

    d = Path(tempfile.mkdtemp())
    _mk_version_dir(d, inc_content=True)
    check("阴性：增量轨有产出 → 放行", not any("❌" in h for h in _rbc(d, "增量轨存在性")))
    shutil.rmtree(d, ignore_errors=True)

    d = Path(tempfile.mkdtemp())
    _mk_version_dir(d, inc_content=False, zero_decl=True)
    check("★ 阴性：空但索引显式声明零变更 → 合法放行（⛔ 零变更本就是合法结论）",
          not any("❌" in h for h in _rbc(d, "增量轨存在性")))
    shutil.rmtree(d, ignore_errors=True)


def test_readonly_collection_declared():
    """G-RELEASE-2 的「全程只读」半条：产物证明不了过程，但采集方式必须可复核。"""
    print("\n[R2] 全量基线只读采集方式声明")
    d = Path(tempfile.mkdtemp())
    _mk_version_dir(d, readonly_decl=False)
    hits = _rbc(d, "只读采集方式")
    check("★ 阳性：索引未交代只读采集方式 → ERROR（两个全量轨各一条）",
          len([h for h in hits if "❌" in h]) == 2)
    shutil.rmtree(d, ignore_errors=True)

    d = Path(tempfile.mkdtemp())
    _mk_version_dir(d, readonly_decl=True)
    check("阴性：写明元数据视图 + 只读 API → 放行", not _rbc(d, "只读采集方式"))
    shutil.rmtree(d, ignore_errors=True)


def test_residual_release_gate():
    """零残留断言发布总闸：Sprint 内可裁剪，发布前必须全跑一次。"""
    print("\n[R3] 零残留断言发布总闸")
    hdr = ("| # | 断言 | 守护面 | 实跑命令 | 方向一·现状命中 | 方向二·阳性对照 | 退役状态 |\n"
           "| :- | :- | :- | :- | :- | :- | :- |\n")

    def scene(row, as_of="2026-09-16"):
        d = Path(tempfile.mkdtemp())
        base = d / "docs/testing/V0.1/研发自测"
        base.mkdir(parents=True)
        (base / "02_用例.md").write_text(hdr + row, encoding="utf-8")
        cp = subprocess.run([sys.executable, RRG, "--root", str(d), "--version", "V0.1",
                             "--as-of", as_of, "--json"], capture_output=True, text=True)
        shutil.rmtree(d, ignore_errors=True)
        return json.loads(cp.stdout)

    A = '| Z-01 | `断言(反向):不存在文本"批量导出"` | `src/**` | `grep ...` | '
    r = scene(A + 'skipped(out-of-scope) | 1 命中 | 在役 |\n')
    check("★ 阳性：在役行标 skipped → 不通过（发布总闸不接受任何 skipped）",
          not r["ok"] and any("不接受任何 skipped" in e["msg"] for e in r["errors"]))
    r = scene(A + '0 命中(2026-09-01 10:12) | 1 命中 | 在役 |\n')
    check("★ 阳性：沿用上一轮的实跑日期 → 不通过（那不是「发布前跑过」）",
          not r["ok"] and any("上一轮" in e["msg"] for e in r["errors"]))
    r = scene(A + '3 命中(2026-09-16 10:12) | 1 命中 | 在役 |\n')
    check("阳性：非零命中 → 不通过（断言未归零）",
          not r["ok"] and any("未归零" in e["msg"] for e in r["errors"]))
    r = scene(A + '0 命中(2026-09-16 10:12) | 1 命中 | 在役 |\n')
    check("阴性：当日实跑且 0 命中 → 通过", r["ok"] and r["active_rows"] == 1)
    r = scene(A + '— (已退役) | — | 已退役(Sprint-046) |\n')
    check("★ 阴性：已退役行不要求实跑（否则退役等于永远还债）", r["ok"])

    d = Path(tempfile.mkdtemp())
    (d / "docs/testing/V0.1/研发自测").mkdir(parents=True)
    (d / "docs/testing/V0.1/研发自测/02_用例.md").write_text("# 用例\n无反向断言。\n", encoding="utf-8")
    cp = subprocess.run([sys.executable, RRG, "--root", str(d), "--version", "V0.1", "--json"],
                        capture_output=True, text=True)
    check("★ 零误报：本版无反向断言 → 合法跳过，不得恒红",
          json.loads(cp.stdout).get("skipped_reason") == "no-assertion")
    (d / "docs/testing/V0.1/研发自测/02_用例.md").write_text(
        '断言(反向):不存在文本"X"\n', encoding="utf-8")
    cp = subprocess.run([sys.executable, RRG, "--root", str(d), "--version", "V0.1", "--json"],
                        capture_output=True, text=True)
    check("★ 阳性：有反向断言却无登记表 → 不通过（断言无人跟踪）",
          not json.loads(cp.stdout)["ok"])
    shutil.rmtree(d, ignore_errors=True)

    cp = subprocess.run([sys.executable, RRG, "--self-check"], capture_output=True, text=True)
    check("脚本自带阳性对照可独立跑通（--self-check）", cp.returncode == 0)


def test_push_state_not_hardcoded():
    """报告里的 tag/分支推送状态必须按实际渲染，⛔ 不得恒写「已推送」。"""
    print("\n[R4] 发布报告推送状态如实渲染")
    t = (REPO / ".aidp/flows/version/release-7b.md").read_text(encoding="utf-8")
    check("★ 不再硬编码「本地已创建并自动推送」",
          "本地已创建并自动推送至 origin" not in t)
    check("改为按状态渲染的占位（TAG_STATE / BRANCH_STATE）",
          "{TAG_STATE}" in t and "{BRANCH_STATE}" in t)
    check("★ 状态取值消费 release_push_failed（Step 3.4.3 落的失败标记）",
          "release_push_failed" in t)

    # 三态判定逻辑本身的双侧对照（与分片里那段 state() 同形）
    script = '''
state(){ [ -z "$1" ] && { echo NOT_CREATED; return; }
  case ",$PF," in *",$2,"*) echo PUSH_FAILED;; *) echo PUSHED;; esac; }
PF="$3"; state "$1" "$2"
'''
    def st(name, kind, pf):
        return subprocess.run(["bash", "-c", script, "_", name, kind, pf],
                              capture_output=True, text=True).stdout.strip()
    check("阴性：未创建 tag → NOT_CREATED", st("", "tag", "") == "NOT_CREATED")
    check("阴性：创建且推送成功 → PUSHED", st("v0.1.0", "tag", "") == "PUSHED")
    check("★ 阳性：创建但推送失败 → PUSH_FAILED（此前恒写「已推送」）",
          st("v0.1.0", "tag", "commit,tag") == "PUSH_FAILED")
    check("★ 边界：commit 推失败但 tag 自身成功 → tag 仍判 PUSHED（不连坐）",
          st("v0.1.0", "tag", "commit") == "PUSHED")


def _flow_block(path, index):
    blocks = re.findall(r"^[ \t]*```bash\n(.*?)\n[ \t]*```", path.read_text(encoding="utf-8"), re.M | re.S)
    return (blocks[index].replace("{version}", "V0.2.0")
            .replace("{prev-version}", "V0.1.0").replace("{版本号}", "0.2.0"))


def _move_scene(block, source, target, *, git_mode=False, tracked=False, conflict=False,
                fail_git_mv=False, extra_sources=(), ignored=False):
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        src, dst = root / source, root / target
        src.parent.mkdir(parents=True, exist_ok=True)
        is_dir = source.endswith("/")
        if is_dir:
            src.mkdir()
            (src / "02_用例.md").write_text("main\n", encoding="utf-8")
        else:
            src.write_text("-- V0.2.0: new\n" if src.suffix == ".sql" else "main\n", encoding="utf-8")
        for extra in extra_sources:
            other = root / extra
            other.parent.mkdir(parents=True, exist_ok=True)
            other.write_text("other\n", encoding="utf-8")
            os.utime(other, (1, 1))
        if git_mode:
            subprocess.run(["git", "init", "-q", td], check=True)
            if ignored:
                (root / ".gitignore").write_text("*.sql\n", encoding="utf-8")
            if tracked:
                subprocess.run(["git", "-C", td, "add", source], check=True)
                subprocess.run(["git", "-C", td, "-c", "user.name=test", "-c", "user.email=test@example.org",
                                "commit", "-qm", "baseline"], check=True)
                modified = src / "02_用例.md" if is_dir else src
                modified.write_text(modified.read_text(encoding="utf-8") + "modified\n", encoding="utf-8")
        if conflict:
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text("existing\n", encoding="utf-8")
        env = os.environ.copy()
        if fail_git_mv:
            shim = root / "bin"
            shim.mkdir()
            real_git = shutil.which("git")
            (shim / "git").write_text(f'#!/bin/sh\n[ "$1" = mv ] && exit 39\nexec "{real_git}" "$@"\n', encoding="utf-8")
            (shim / "git").chmod(0o755)
            env["PATH"] = f'{shim}:{env["PATH"]}'
        marker = root / "skill_start"
        marker.touch()
        os.utime(marker, (1, 1))
        result = subprocess.run(["bash", "-e", "-c", block.replace("/tmp/skill_start", str(marker))],
                                cwd=root, env=env,
                                capture_output=True, text=True)
        content = dst.read_text(encoding="utf-8") if dst.is_file() else ("directory" if dst.is_dir() else None)
        if is_dir and tracked and git_mode and dst.is_dir():
            staged = subprocess.run(["git", "-C", td, "ls-files", "--error-unmatch", "--",
                                     str(dst.relative_to(root) / "02_用例.md")], capture_output=True)
            content = "tracked-directory" if staged.returncode == 0 else "unstaged-directory"
        return result.returncode, src.exists(), content


def test_flow_move_modes():
    print("\n[R5] SQL 和规划产物归位（执行围栏）")
    sql = _flow_block(SQL_FLOW, 1)
    source = "code/sql/v0.2.0/01_新增.sql"
    target = "docs/deployment/V0.2.0/sql/增量/01_新增.sql"
    for mode, tracked in ((False, False), (True, False), (True, True)):
        rc, src, dst = _move_scene(sql, source, target, git_mode=mode, tracked=tracked)
        check(f"SQL 搬迁 git={mode} tracked={tracked}", rc == 0 and not src and dst is not None)
    for stage in ("code/sql/V0.2.0", "code/sql/vV0.2.0"):
        rc, src, dst = _move_scene(sql, stage + "/01_新增.sql", target)
        check(f"SQL legacy/双 v 路径归位 {stage}", rc == 0 and not src and dst is not None)
    rc, src, dst = _move_scene(sql, "code/sql/v0.1.0/01_新增.sql", target,
                               git_mode=True, tracked=True)
    check("Git 模式上一版本本轮修改可纠正", rc == 0 and not src and dst is not None)
    rc, src, dst = _move_scene(sql, "code/sql/v0.1.0/01_新增.sql", target)
    check("无 Git 的上一版本 SQL 来源不明时阻断", rc != 0 and src and dst is None)
    rc, src, dst = _move_scene(sql, source, target, git_mode=True, ignored=True)
    check("被 ignore 的 SQL 不得静默漏搬", rc != 0 and src and dst is None)
    for conflict, fail_git in ((True, False), (False, True)):
        rc, src, dst = _move_scene(sql, source, target, git_mode=True, tracked=True,
                                   conflict=conflict, fail_git_mv=fail_git)
        check(f"SQL 移动失败 fail-closed conflict={conflict} git_mv={fail_git}",
              rc != 0 and src and (dst == "existing\n" if conflict else dst is None))

    plan = _flow_block(PLAN_FLOW, 0)
    for mode, tracked in ((False, False), (True, False), (True, True)):
        rc, src, dst = _move_scene(plan, "docs/design/detail/V0.2.0/00_详细设计.md",
                                   "docs/design/detail/V0.2.0/01_详细设计.md", git_mode=mode, tracked=tracked)
        check(f"规划主文档归一 git={mode} tracked={tracked}", rc == 0 and not src and dst is not None)
    rc, src, dst = _move_scene(plan, "docs/design/detail/V0.2.0/00_详细设计.md",
                               "docs/design/detail/V0.2.0/01_详细设计.md", git_mode=True,
                               tracked=True, fail_git_mv=True)
    check("规划 git mv 失败不回退普通 mv", rc != 0 and src and dst is None)
    rc, src, dst = _move_scene(plan, "docs/design/detail/V0.2.0/00_详细设计.md",
                               "docs/design/detail/V0.2.0/01_详细设计.md", conflict=True)
    check("规划已有 01 时续编并保留原目标", rc == 0 and not src and dst == "existing\n")

    bare = "docs/design/detail/V0.2.0/"
    rc, src, dst = _move_scene(plan, bare + "详细设计.md", bare + "01_详细设计.md",
                               extra_sources=(bare + "数据库设计.md",))
    check("设计裸名多文件归一", rc == 0 and not src and dst is not None)
    inc = _flow_block(PLAN_FLOW, 2)
    for mode, tracked in ((False, False), (True, False), (True, True)):
        rc, src, dst = _move_scene(inc, "docs/plans/V0.2.0/01_补充-功能.md",
                                   "docs/plans/V0.2.0/02_功能.md", git_mode=mode, tracked=tracked)
        check(f"补充规划续编 git={mode} tracked={tracked}", rc == 0 and not src and dst is not None)
    dedup = ('next_seq() { printf "03"; }\n' +
             _flow_block(PLAN_FLOW, 3).split('gen_index() {', 1)[0] +
             '\ndedup_prefix "docs/testing/V0.2.0/研发自测/" || exit 1\n')
    for mode, tracked in ((False, False), (True, False), (True, True)):
        directory = "docs/testing/V0.2.0/研发自测/"
        rc, src, dst = _move_scene(dedup, directory + "02_后.md", directory + "03_后.md",
                                   git_mode=mode, tracked=tracked,
                                   extra_sources=(directory + "02_先.md",))
        check(f"研发自测用例重号归一 git={mode} tracked={tracked}",
              rc == 0 and not src and dst is not None)

    full_index = _flow_block(PLAN_FLOW, 3)
    directory = "docs/testing/V0.2.0/研发自测/"
    rc, src, dst = _move_scene(full_index, directory + "02_后.md", directory + "03_后.md",
                               extra_sources=(directory + "02_先.md",
                                              "docs/requirements/V0.2.0/研发需求/01_需求.md",
                                              "docs/design/detail/V0.2.0/01_详细设计.md",
                                              "docs/plans/V0.2.0/01_计划.md"))
    check("索引围栏独立执行且完成重号归一", rc == 0 and not src and dst is not None)

    selftest = _flow_block(PLAN_FLOW, 1)
    for mode, tracked in ((False, False), (True, False), (True, True)):
        rc, src, dst = _move_scene(selftest, "docs/testing/V0.2.0/研发自测用例/",
                                   "docs/testing/V0.2.0/研发自测/", git_mode=mode, tracked=tracked)
        check(f"研发自测整目录归位 git={mode} tracked={tracked}",
              rc == 0 and not src and dst == ("tracked-directory" if tracked else "directory"))
    for mode, tracked in ((False, False), (True, False), (True, True)):
        rc, src, dst = _move_scene(selftest, "docs/testing/V0.2.0/研发自测.md",
                                   "docs/testing/V0.2.0/研发自测/02_全量自测用例.md",
                                   git_mode=mode, tracked=tracked)
        check(f"研发自测子目录化 git={mode} tracked={tracked}", rc == 0 and not src and dst is not None)


def test_release_cicd_degraded_probe():
    """执行发布 push 围栏，替身只隔离 Git/平台网络；循环与 rc 判据直接取生产分片。"""
    print('\n[R6] 发布 CICD 降级交接：rc4 + probe、证据与 push 时刻')
    block = _flow_block(REPO / '.aidp/flows/version/release-7.md', 2)
    degraded = {'verdict': 'not-observed', 'next_action': 'probe', 'degraded': True,
                'degraded_reason': '平台未观测到本次运行', 'push_auto_deploy': True}
    poll = {'verdict': 'running', 'next_action': 'poll', 'run_id': 'run-1'}
    retry = {'verdict': 'failed', 'next_action': 'retry', 'run_id': 'run-1', 'retry_commit': 'release-sha'}
    scenes = (
        ('首轮新提交', [(4, degraded)], True, 0),
        ('首轮降级', [(4, degraded)], True, 0),
        ('poll 降级', [(0, poll), (4, degraded)], True, 0),
        ('retry 后 poll 降级', [(1, retry), (0, {'run_id': 'run-2'}), (4, degraded)], True, 0),
        ('retry 后 detect 降级', [(1, retry), (0, {}), (4, degraded)], True, 0),
        ('降级但探针失败', [(4, degraded)], False, 1),
        ('rc4 未要求 probe', [(4, {**degraded, 'next_action': 'abort'})], False, 0),
        ('未知退出码', [(5, degraded)], False, 0),
        ('真实失败不得降级', [(2, {'verdict': 'failed', 'next_action': 'abort'})], False, 0),
        ('正常成功', [(0, {'verdict': 'success', 'next_action': 'probe'})], True, 0),
    )
    stub = '''import json, os, sys
from pathlib import Path
root = Path(os.environ['SCENE_ROOT'])
name, args = Path(sys.argv[1]).name, sys.argv[2:]
statefile = root / 'state.json'
state = json.loads(statefile.read_text())
def save(): statefile.write_text(json.dumps(state, ensure_ascii=False))
if name == 'baseline_edit.py':
    while args and args[0].startswith('--'):
        args = args[2:]
    action = args.pop(0)
    if action == 'current-version': print('V0.2.0')
    elif action in ('get', 'take'):
        key = args[0]
        print(state.get(key, args[2] if len(args) > 2 else ''))
        if action == 'take': state.pop(key, None); save()
    elif action == 'set':
        for key, value in zip(args[::2], args[1::2]):
            try: state[key] = json.loads(value)
            except ValueError: state[key] = value
        save()
    elif action == 'bump':
        key = args[0]; state[key] = int(state.get(key, 0)) + 1; save(); print(state[key])
elif name == 'autopilot_tick_flags.py': print('TARGET_VERSION=V0.2.0')
elif name == 'classify_push.py': print('{}')
elif name == 'cicd_watch.py':
    with (root / 'watch-calls.jsonl').open('a') as stream: stream.write(json.dumps(args) + '\\n')
    queuefile = root / 'queue.json'
    queue = json.loads(queuefile.read_text())
    if not queue: raise SystemExit(99)
    code, value = queue.pop(0); queuefile.write_text(json.dumps(queue))
    print(json.dumps(value, ensure_ascii=False)); raise SystemExit(code)
elif name == 'autopilot-deploy-watch.py':
    (root / 'probe-called').touch(); raise SystemExit(int(os.environ['PROBE_RC']))
else: raise SystemExit('Unexpected command: ' + name)
'''
    for label, sequence, success, probe_rc in scenes:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / 'stub.py').write_text(stub, encoding='utf-8')
            # 已推同一提交的监听重入：必须保留首次 push 时刻，不能每次重新等满。
            pushed_at = '2026-01-01T00:00:00Z'
            (root / 'state.json').write_text(json.dumps({
                'release_push_commit': 'previous-sha' if label == '首轮新提交' else 'release-sha',
                'release_push_at': pushed_at}), encoding='utf-8')
            (root / 'queue.json').write_text(json.dumps(sequence), encoding='utf-8')
            prd = root / 'docs/requirements/V0.2.0/产品提供/PRD.md'
            prd.parent.mkdir(parents=True)
            prd.write_text('---\nautopilot_decisions:\n  deployment:\n    mode: cloud\n'
                           '    cicd_env: test\n    cloud_ready_api_url: https://example.com/health\n---\n', encoding='utf-8')
            prefix = '''python3() { command "$REAL_PYTHON" "$SCENE_ROOT/stub.py" "$@"; }
git() { case "$1" in rev-parse) printf 'release-sha\\n';; symbolic-ref) printf 'main\\n';; push) return 0;; *) return 42;; esac; }
'''
            result = subprocess.run(['bash', '-c', prefix + block], cwd=root, capture_output=True, text=True,
                                    env={**os.environ, 'SCENE_ROOT': td, 'REAL_PYTHON': sys.executable,
                                         'PROBE_RC': str(probe_rc)})
            check(f'{label}: 正确继续或阻断发布', (result.returncode == 0) is success)
            called = (root / 'probe-called').exists()
            expected_probe = success or probe_rc != 0
            check(f'{label}: 仅合法 probe 分支执行探针', called is expected_probe)
            state = json.loads((root / 'state.json').read_text())
            if label == '首轮新提交':
                check('新 push commit 更新并持久化开始时刻',
                      state.get('release_push_commit') == 'release-sha' and
                      state.get('release_push_at') and state['release_push_at'] != pushed_at)
                pushed_at = state.get('release_push_at')
            if expected_probe:
                calls = [json.loads(line) for line in (root / 'watch-calls.jsonl').read_text().splitlines()]
                reads = [args for args in calls if 'retry' not in args]
                check(f'{label}: watch/poll/detect 均携首次 --push-at', all(
                    '--push-at' in args and args[args.index('--push-at') + 1] == pushed_at for args in reads))
                if sequence[-1][0] == 4:
                    evidence = state.get('release_cicd', {})
                    check(f'{label}: 保留 unknown、降级标记与平台原原因',
                          evidence.get('status') == 'unknown' and evidence.get('degraded') is True and
                          evidence.get('degraded_reason') == degraded['degraded_reason'])


def test_release_actual_write_set():
    """真实临时 Git 仓执行发布围栏：版本修正、记忆与文档必须一起入库。"""
    print('\n[R7] 发布实际写集与无关修改隔离（执行围栏）')
    release6 = REPO / '.aidp/flows/version/release-6.md'
    release7 = REPO / '.aidp/flows/version/release-7.md'
    blocks = re.findall(r'^```bash\n(.*?)\n```', release6.read_text(), re.M | re.S)
    apply_block = next((b for b in blocks if '--apply-scope' in b),
                       'python3 {{AIDP_HOME}}/scripts/check_version_identifier.py '
                       '--version {version} --apply --apply-scope all')
    apply_block = apply_block.replace('{version}', 'V0.2.0').replace('{{AIDP_HOME}}', str(REPO / '.aidp'))
    commit_block = _flow_block(release7, 0).replace('{{AIDP_HOME}}', str(REPO / '.aidp'))
    be = [sys.executable, str(REPO / '.aidp/scripts/baseline_edit.py'), '--version', 'V0.2.0']
    real_git = shutil.which('git')
    for scene in ('clean', 'dirty-version-file', 'changed-after-fix', 'unrelated-staged', 'add-failure', 'post-commit-residue'):
        with tempfile.TemporaryDirectory(prefix='aidp-release-write-set-') as td:
            root = Path(td)
            version_files = ['code/frontend/app/package.json', 'code/backend/app/pom.xml']
            artifacts = ['docs/reports/V0.2.0/release notes.md', 'docs/reports/V0.2.0/obsolete.md',
                         'memory/V0.2.0/test/progress.md', 'CLAUDE.md']
            originals = {
                version_files[0]: '{"name":"app","version":"0.1.0"}\n',
                version_files[1]: '<project><modelVersion>4.0.0</modelVersion><groupId>example</groupId>'
                                  '<artifactId>app</artifactId><version>0.1.0</version></project>\n',
                'code/frontend/app/src/main.js': 'old business\n',
                'frontend/unrelated.js': 'old frontend\n',
                **{path: 'old artifact\n' for path in artifacts},
                '.gitignore': 'memory/.sprint-autopilot-baseline.json*\nmemory/.aidp/\n.claude/\nbin/\n',
            }
            for path, content in originals.items():
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding='utf-8')
            (root / '.claude').mkdir()
            def git(*args):
                return subprocess.run([real_git, *args], cwd=root, capture_output=True, text=True, check=True)
            git('init', '-q')
            git('config', 'user.name', 'test')
            git('config', 'user.email', 'test@example.org')
            git('add', '.')
            git('commit', '-qm', 'baseline')
            for path in artifacts:
                (root / path).write_text('released artifact\n', encoding='utf-8')
            (root / artifacts[1]).unlink()
            for path in ('code/frontend/app/src/main.js', 'frontend/unrelated.js'):
                (root / path).write_text('unrelated dirty business\n', encoding='utf-8')
            (root / 'code/backend/app/unrelated.py').write_text('untracked business\n', encoding='utf-8')
            if scene == 'dirty-version-file':
                (root / version_files[0]).write_text('{"name":"app","version":"0.1.0","private":true}\n')
            if scene == 'unrelated-staged':
                git('add', 'code/frontend/app/src/main.js')
            subprocess.run([*be, 'set', 'release_artifact_paths', json.dumps(artifacts),
                            'phase_beta_done_at', '@now'], cwd=root, check=True,
                           capture_output=True, text=True)
            env = {**os.environ, 'AIDP_AGENT': 'claude'}
            applied = subprocess.run(['bash', '-c', apply_block], cwd=root, env=env,
                                     capture_output=True, text=True, timeout=20)
            check(f'{scene}: 真实版本修正执行成功', applied.returncode == 0)
            fix = subprocess.run([*be, 'get', 'release_version_fix', '--default', '{}'], cwd=root,
                                 capture_output=True, text=True, check=True)
            saved = json.loads(fix.stdout)
            check(f'{scene}: 修正路径跨围栏落盘', set(version_files) <= set((saved or {}).get('files', {})))
            if scene == 'clean':
                replay = subprocess.run(['bash', '-c', apply_block], cwd=root, env=env,
                                        capture_output=True, text=True, timeout=20)
                replay_fix = subprocess.run([*be, 'get', 'release_version_fix'], cwd=root,
                                            capture_output=True, text=True, check=True)
                check('修正围栏重入无新修正时保留原实际写集',
                      replay.returncode == 0 and json.loads(replay_fix.stdout) == saved)
            if scene == 'changed-after-fix':
                (root / version_files[0]).write_text('{"name":"app","version":"0.2.0","private":true}\n')
            if scene in ('add-failure', 'post-commit-residue'):
                shim = root / 'bin'
                shim.mkdir()
                code = (f'#!{sys.executable}\nimport subprocess, sys\nfrom pathlib import Path\n'
                        f'args = sys.argv[1:]\nscene = {scene!r}\n'
                        "if scene == 'add-failure' and 'add' in args: raise SystemExit(39)\n"
                        f'rc = subprocess.call([{real_git!r}, *args])\n'
                        "if scene == 'post-commit-residue' and 'commit' in args and rc == 0:\n"
                        f' Path({version_files[0]!r}).write_text(\'{{"version":"0.9.0"}}\\n\')\n'
                        'raise SystemExit(rc)\n')
                (shim / 'git').write_text(code)
                (shim / 'git').chmod(0o755)
                env['PATH'] = f'{shim}:{env["PATH"]}'
            # 仅隔离无关的产物欠账扫描；版本/记忆/baseline 与所有 Git 操作均是真实 CLI。
            prefix = ('python3() { case "$1" in */release_debt.py) return 0;; '
                      f'*) command "{sys.executable}" "$@";; esac; }}\n')
            committed = subprocess.run(['bash', '-c', prefix + commit_block], cwd=root, env=env,
                                       capture_output=True, text=True, timeout=20)
            if scene == 'clean':
                if committed.returncode:
                    print(committed.stdout + committed.stderr)
                check('CLAUDE-only 发布围栏成功，不依赖不存在的 AGENTS.md', committed.returncode == 0)
                check('code/ 中 package/pom 新版号均进入提交', all(
                    '0.2.0' in git('show', f'HEAD:{path}').stdout for path in version_files))
                check('真实记忆与带空格文档进入提交，删除产物同步入库',
                      all(git('show', f'HEAD:{path}').stdout == 'released artifact\n'
                          for path in (artifacts[0], artifacts[2], 'CLAUDE.md'))
                      and artifacts[1] not in git('ls-tree', '-r', '--name-only', 'HEAD').stdout.splitlines())
                check('无关 dirty/untracked 业务文件既未提交也未暂存',
                      git('show', 'HEAD:code/frontend/app/src/main.js').stdout == 'old business\n'
                      and git('show', 'HEAD:frontend/unrelated.js').stdout == 'old frontend\n'
                      and not git('diff', '--cached', '--name-only').stdout
                      and 'code/backend/app/unrelated.py' in git('ls-files', '--others', '--exclude-standard').stdout)
                check('提交后全部发布写集无残留', not git('status', '--porcelain', '--', *version_files, *artifacts).stdout)
            else:
                reason = {'dirty-version-file': '原有混杂', 'changed-after-fix': '版本修正后又有未核对变更',
                          'unrelated-staged': '暂存区含写集外修改',
                          'add-failure': '39', 'post-commit-residue': '发布写集未全部入库'}[scene]
                check(f'{scene}: fail-closed 且确因预期原因阻断',
                      committed.returncode != 0 and reason in committed.stdout + committed.stderr)
                if scene == 'post-commit-residue':
                    check('提交后残留是在真实发布提交完成后检出', git('rev-list', '--count', 'HEAD').stdout.strip() == '2')
                if scene != 'post-commit-residue':
                    check(f'{scene}: 未创建夹带或不完整发布提交', git('rev-list', '--count', 'HEAD').stdout.strip() == '1')
    for path in (release6, release7):
        check(f'{path.name}: 分片小于 20480 字节', path.stat().st_size < 20480)


def test_changelog_uses_semver_baseline_and_original_tag():
    first = (REPO / '.aidp/flows/version/release-1.md').read_text(encoding='utf-8')
    section = first.split('### tag 风格识别约定', 1)[1].split('### Step 3.1', 1)[0]
    block = re.search(r'```bash\n(.*?)\n```', section, re.S).group(1)
    block = block.replace('{{AIDP_HOME}}', str(REPO / '.aidp')).replace('{version}', 'V0.3.0')
    second = (REPO / '.aidp/flows/version/release-2.md').read_text(encoding='utf-8')
    commits = re.search(r'<!-- release-changelog-commits -->\s*```bash\n(.*?)\n```', second, re.S)
    check('发布日志以原始tag为Git引用，不用归一展示版本',
          'git log {prev-version}' not in second and 'git describe --tags' not in second)
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        def git(*args):
            return subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True, check=True).stdout.strip()
        git('init', '-q'); git('config', 'user.name', 'audit'); git('config', 'user.email', 'audit@example.invalid')
        for index, tag in enumerate(('v0.1.0', 'V0.2.0', 'release-V0.2.5')):
            (root / 'app.txt').write_text(str(index))
            git('add', 'app.txt'); git('commit', '-qm', f'feat(app): released-{index}'); git('tag', tag)
        (root / 'app.txt').write_text('pending')
        git('add', 'app.txt'); git('commit', '-qm', 'fix(app): pending')
        for expected in ('release-V0.2.5', 'V0.2.0', 'v0.1.0', ''):
            result = subprocess.run(['bash', '-e', '-c', block + '\nprintf "%s" "$PREV"'],
                                    cwd=root, capture_output=True, text=True)
            check('混合tag原始基线=' + (expected or '首版'), result.returncode == 0 and result.stdout == expected)
            if commits:
                command = commits.group(1).replace('{{AIDP_HOME}}', str(REPO / '.aidp')).replace('{version}', 'V0.3.0')
                run = subprocess.run(['bash', '-e', '-c', command], cwd=root, capture_output=True, text=True)
                check('原始tag范围可执行=' + (expected or '首版'), run.returncode == 0 and 'fix(app): pending' in run.stdout)
                if expected == 'release-V0.2.5':
                    check('不把已发布提交重复写入新日志', 'released-' not in run.stdout)
            if expected:
                git('tag', '-d', expected)
    check('变更日志有可提取执行入口', commits is not None)


def main():
    test_changelog_uses_semver_baseline_and_original_tag()
    test_release_actual_write_set()
    test_release_cicd_degraded_probe()
    test_increment_presence()
    test_readonly_collection_declared()
    test_residual_release_gate()
    test_push_state_not_hardcoded()
    test_flow_move_modes()
    print(f"\n══ 结果：{_passed} passed / {_failed} failed ══")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
