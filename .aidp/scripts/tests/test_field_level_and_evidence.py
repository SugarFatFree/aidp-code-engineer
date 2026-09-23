#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""写读错层 / 保护面不足 / 落点收编 三处缺口回归。

· `decidable_skips`：写方落**版本级**、唯一读方读**build 级** ⇒ 两条路径完全不相交，
  「无人值守替人选了 patch」永不上浮。写了、也读了，只是读写的不是同一个地方——
  在产物上与「从没跳过」完全同形。
· `check_memory_loss` 的保护面不含 `AGENTS.md`，而 `/memory-sync` **自己点名会写**它
  ⇒ 命令会写、写坏了没有检出器。
· 运行时产物 / 人维护配置的落点必须有单一信源，新落点优先、旧落点回落不得静默失效。
"""
import json
import os
import subprocess
import sys
import tempfile
import shutil
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
GATE = str(REPO / ".aidp/scripts/autopilot-ceremony-gate.py")
MEM = str(REPO / ".aidp/scripts/check_memory_loss.py")

_passed = _failed = _skipped = 0


def check(name, cond):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ✅ {name}")
    else:
        _failed += 1
        print(f"  ❌ FAIL: {name}")


def skip(name, reason):
    global _skipped
    _skipped += 1
    print(f"  ⏭️ SKIP: {name}（{reason}）")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_decidable_skips_levels():
    print("\n[F1] decidable_skips 写读层级对齐")

    def scene(build_lvl, ver_lvl):
        root = Path(tempfile.mkdtemp())
        (root / "memory").mkdir()
        b = {"build": "V0.1_build1001"}
        if build_lvl:
            b["decidable_skips"] = build_lvl
        vn = {"current_build": "V0.1_build1001", "builds": [b]}
        if ver_lvl:
            vn["decidable_skips"] = ver_lvl
        (root / "memory/.sprint-autopilot-baseline.json").write_text(
            json.dumps({"versions": {"V0.1": vn}}, ensure_ascii=False), encoding="utf-8")
        cp = subprocess.run([sys.executable, GATE, "check", "--version", "V0.1",
                             "--build", "V0.1_build1001", "--stage", "final",
                             "--repo-root", str(root), "--notify", "0",
                             "--no-advance-run-state"], capture_output=True, text=True)
        shutil.rmtree(root, ignore_errors=True)
        return "\n".join(l for l in (cp.stdout + cp.stderr).splitlines() if "可决策跳过" in l)

    check("★ 阳性：只有版本级留痕也能上浮（/sprint-dev 写方的实际落点，改前永不可见）",
          "post-release" in scene(None, ["post-release-accrue-defaulted-patch"]))
    check("阴性：build 级留痕照常上浮（version.md 写方）",
          "system-story" in scene(["system-story-create-skipped"], None))
    check("★ 零误报：两层都空 → 本项不加噪音行", scene(None, None) == "")

    # 写方口径：三处必须一致，且与读方接得上
    dev = (REPO / ".aidp/commands/sprint-dev.md").read_text(encoding="utf-8")
    ver = (REPO / ".aidp/commands/version.md").read_text(encoding="utf-8")
    full = (REPO / ".aidp/commands/sprint-full.md").read_text(encoding="utf-8")
    check("★ sprint-dev 写方已改为 builds[current_build]（无 build 才回落版本级）",
          "builds[current_build].decidable_skips[]" in dev)
    check("version.md 写方本就是 build 级（三处口径现已一致）",
          "builds[current_build].decidable_skips[]" in ver)
    check("sprint-full 已点明落点层级（此前只写「baseline decidable_skips」）",
          "builds[current_build]" in full)


def test_memory_protection_covers_claude_md():
    print("\n[F2] memory 保护面覆盖 /memory-sync 的写入面")
    mem = _load("cml", MEM)
    check("★ 保护面含 AGENTS.md（命令点名会写它，此前无检出器）",
          "AGENTS.md" in mem.PROTECTED)

    root = Path(tempfile.mkdtemp())
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    for k, v in (("user.email", "alice@example.com"), ("user.name", "alice")):
        subprocess.run(["git", "-C", str(root), "config", k, v], check=True)
    (root / ".claude").mkdir()
    (root / "AGENTS.md").write_text(
        "# 入口\n\n## 当前状态\n\n- 当前版本：V0.1.0\n\n"
        "## 核心约定\n\n正文若干行。\n还有更多内容。\n再来一段。\n\n## 文档索引\n\n指向各处。\n",
        encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "base"], check=True)

    def run_mem():
        cp = subprocess.run([sys.executable, MEM, "--root", str(root), "--json"],
                            capture_output=True, text=True)
        return json.loads(cp.stdout)

    t = (root / "AGENTS.md").read_text(encoding="utf-8")
    (root / "AGENTS.md").write_text(t.replace("V0.1.0", "V0.2.0"), encoding="utf-8")
    r = run_mem()
    check("★ 阴性：只改「当前状态」的值（memory-sync 的正常行为）→ 不报（⛔ 否则是永远修不掉的假红）",
          not r["errors"] and r["checked"] >= 1)

    t = (root / "AGENTS.md").read_text(encoding="utf-8")
    i, j = t.index("## 核心约定"), t.index("## 文档索引")
    (root / "AGENTS.md").write_text(t[:i] + t[j:], encoding="utf-8")
    r = run_mem()
    check("★ 阳性：整段「核心约定」被吞 → 报出（段落消失 + 整份塌缩）",
          any("核心约定" in str(e.get("msg", "")) for e in r["errors"]))
    shutil.rmtree(root, ignore_errors=True)


def test_memory_baseline_without_git():
    print("\n[nonGit] memory 快照可用，缺快照不得伪报通过")
    with tempfile.TemporaryDirectory() as d:
        rel = "memory/projectBrief.md"
        path = Path(d) / rel
        path.parent.mkdir()
        path.write_text("## 约定\n原文\n", encoding="utf-8")
        def inspect():
            cp = subprocess.run([sys.executable, MEM, "--root", d, "--file", rel, "--json"],
                                capture_output=True, text=True)
            return cp.returncode, json.loads(cp.stdout)
        code, result = inspect()
        check("nonGit 无快照时 HEAD 比对 unsupported", code == 3 and result ==
              {"status": "unsupported", "reason": "vcs-disabled", "capability": "diff"})
        mem = _load("memory_snap", MEM)
        mem.take_snapshot(d, [rel])
        code, result = inspect()
        check("nonGit 写前快照仍能检测", code == 0 and result["checked"] == 1)
        path.write_text("## 其它\n原文\n", encoding="utf-8")
        code, result = inspect()
        check("nonGit 快照检测段落丢失", code == 1 and any(e["rule"] == "L1" for e in result["errors"]))
        as_list = mem.run(d, files=[rel])
        as_generator = mem.run(d, files=(item for item in [rel]))
        check("nonGit 文件生成器与列表一致：均巡检文件并检出 L1",
              as_list["checked"] == as_generator["checked"] == 1
              and any(e["rule"] == "L1" for e in as_generator["errors"]))


def test_lock_path_single_source():
    """锁路径三处独立实现 → 收敛成一个函数（否则互斥会在某次改路径时当场归零）。"""
    print("\n[F4] flock 锁路径单一信源 + 收编")
    be = _load("be", str(REPO / ".aidp/scripts/baseline_edit.py"))
    check("★ 提供唯一实现 lock_path()", callable(getattr(be, "lock_path", None)))
    check("锁文件收进隐藏子目录（不再与数据文件同级堆在 memory/ 下）",
          "/.aidp/locks/" in be.lock_path("memory/x.json"))
    check("★ 锁仍与数据文件同目录下（⛔ 挪去系统临时目录会随 TMPDIR 分裂成两把锁）",
          be.lock_path("memory/x.json").startswith(
              os.path.abspath("memory") + os.sep))

    for f, name in ((".aidp/scripts/autopilot-ceremony-gate.py", "ceremony-gate"),
                    (".aidp/scripts/emit-report.py", "emit-report")):
        t = (REPO / f).read_text(encoding="utf-8")
        check(f"★ {name} 改调单一信源（此前各写各的路径拼接）",
              "from baseline_edit import lock_path" in t)
        check(f"{name} 不再自行拼接 `+ \".lock\"`", '+ ".lock"' not in t)

    # 互斥必须仍然有效——这是换路径唯一真正的风险
    import threading
    import time
    d = Path(tempfile.mkdtemp())
    (d / "memory").mkdir()
    bp = str(d / "memory/b.json")
    Path(bp).write_text('{"n":0}', encoding="utf-8")
    order = []

    def worker(tag, hold):
        with be.LockedBaseline(bp, write=True) as lb:
            order.append(f"{tag}-in")
            time.sleep(hold)
            lb.data["n"] = lb.data.get("n", 0) + 1
            order.append(f"{tag}-out")

    t1 = threading.Thread(target=worker, args=("A", 0.3))
    t2 = threading.Thread(target=worker, args=("B", 0.0))
    t1.start()
    time.sleep(0.05)
    t2.start()
    t1.join()
    t2.join()
    check("★ 互斥仍然有效：两个写者不交错（A 进 A 出 B 进 B 出）",
          order == ["A-in", "A-out", "B-in", "B-out"])
    check("★ 两次自增都生效（⛔ 丢更新正是锁失效的静默形态）",
          json.loads(Path(bp).read_text(encoding="utf-8"))["n"] == 2)
    check("memory/ 下不再落裸 .lock 文件",
          not [f for f in os.listdir(d / "memory") if f.endswith(".lock")])
    shutil.rmtree(d, ignore_errors=True)

    gi = (REPO / ".gitignore").read_text(encoding="utf-8")
    check("gitignore 覆盖新落点（锁目录 memory/.aidp/locks 随本地运行态目录整体忽略）", "memory/.aidp/" in gi)
    check("★ 旧落点两种形态都覆盖（`*` 不匹配前导点，只写一条等于无效）",
          "memory/*.lock" in gi and "memory/.*.lock" in gi)


def test_runtime_artifact_paths():
    """运行时产物路径单一信源 + 入库策略体检。

    下游实测一个仓库有 17 个 AIDP 运行时产物、2 个位置、2 套前缀、4 种入库策略，
    使用者分不清「哪个是我能动的」。搬家的前提是路径先有单一信源——
    此前每处各自拼字面量，改漏一处就是两个进程读写不同文件，而它与「正常工作」完全同形
    （flock 锁路径那次正是这么埋进去的）。
    """
    print("\n[F5] 运行时产物路径单一信源")
    ap = _load("ap", str(REPO / ".aidp/scripts/aidp_paths.py"))
    inv = ap.inventory(str(REPO))
    check("登记表非空且每项都带性质与入库策略",
          len(inv) >= 6 and all(x["kind"] and x["vcs"] for x in inv))
    check("★ 收编后只剩三类落点：入库配置 / 入库状态机 / 本地运行时目录",
          {x["path"] for x in inv} >= {"memory/aidp-config.yaml",
                                       "memory/.sprint-autopilot-baseline.json",
                                       "memory/.aidp/ceremony-ledger.json"})
    check("★★ 登记的入库策略与 .gitignore 事实一致（标错 = 清单变误导源，与标对同形）",
          ap._check_vcs(str(REPO), as_json=False) == 0)
    cfg = _load("cfg", str(REPO / ".aidp/scripts/aidp_config.py"))
    check("★ 下游身份标记只落 aidp-config.yaml（无旧根级版本戳回落）",
          not hasattr(cfg, "LEGACY_SCAFFOLD_VERSION_REL") and cfg.CONFIG_REL.endswith("aidp-config.yaml"))
    check("★ 锁目录常量与 baseline_edit 一致（两处不一致 = 互斥归零）",
          ap.LOCK_DIRNAME == _load("be2", str(REPO / ".aidp/scripts/baseline_edit.py")).LOCK_DIRNAME)
    check("凭据文件标「永不入库」", any(x["vcs"].endswith("永不入库") for x in inv))

    # 入库策略体检：凭据被跟踪必须 ERROR
    vp = str(REPO / "skills/aidp-code-engineer/scripts/verify.py")
    d = Path(tempfile.mkdtemp())
    subprocess.run(["git", "init", "-q", str(d)], check=True)
    for k, v in (("user.email", "alice@example.com"), ("user.name", "alice")):
        subprocess.run(["git", "-C", str(d), "config", k, v], check=True)
    (d / "memory").mkdir()
    (d / ".aidp/scripts").mkdir(parents=True)
    shutil.copy(REPO / ".aidp/scripts/aidp_paths.py", d / ".aidp/scripts/aidp_paths.py")
    (d / "memory/.sprint-autopilot-credentials.json").write_text('{"prod":"secret"}', encoding="utf-8")
    subprocess.run(["git", "-C", str(d), "add", "-f", "memory/.sprint-autopilot-credentials.json",
                    ".aidp/scripts/aidp_paths.py"], check=True)
    subprocess.run(["git", "-C", str(d), "commit", "-qm", "leak"], check=True)
    out = subprocess.run([sys.executable, vp, str(d), "V0.0.1", "alice"],
                         capture_output=True, text=True).stdout
    check("★ 阳性：凭据文件被 git 跟踪 → ERROR（进了索引就随每次 clone 扩散）",
          "永不入库" in out and "[ERROR]" in out)
    shutil.rmtree(d, ignore_errors=True)

    # ⛔ 对真仓只读：非只读 verify 会按传入的版本 / 用户补建迭代目录，把夹具用户名写进仓库
    out2 = subprocess.run([sys.executable, vp, str(REPO), "V0.0.1", "alice", "--read-only"],
                          capture_output=True, text=True).stdout
    check("★ 阴性：本仓凭据未跟踪 → 不报（⛔ 且必须真的跑到，不能被 per-check 兜底吞掉）",
          "运行时产物入库策略一致" in out2)


def test_config_consolidation():
    """散落产物收编：人维护配置 / 程序状态 / 本地运行时目录 —— 按「谁写 × 入不入库」三分。

    合并这类东西最容易埋的不是「搬错位置」，而是**搬完之后新落点是空的、读取却优先它**——
    那一刻用户配过的值静默变回缺省，与「用户没配过」在输出上完全同形。
    下面几条正是钉这个形态。
    """
    print("\n[F7] 运行时/配置产物收编")
    cfg = _load("cfg2", str(REPO / ".aidp/scripts/aidp_config.py"))
    adm = _load("adm", str(REPO / ".aidp/scripts/autopilot_decisions_merge.py"))

    d = Path(tempfile.mkdtemp())
    (d / "memory").mkdir()
    (d / "docs/requirements/V0.1.0/产品提供").mkdir(parents=True)
    (d / "docs/requirements/V0.1.0/产品提供/prd.md").write_text("# PRD", encoding="utf-8")
    cfg.ensure(str(d))
    def _mode(root):
        cp = subprocess.run([sys.executable, str(REPO / ".aidp/scripts/autopilot_decisions_merge.py"),
                             "--root", str(root), "--version", "V0.1.0", "--get", "deployment.mode"],
                            capture_output=True, text=True)
        return (cp.stdout or "").strip()
    check("★ 配置未声明 → 合并结果为空", _mode(d) == "")
    p = d / "memory/aidp-config.yaml"
    p.write_text(p.read_text(encoding="utf-8").replace(
        "autopilot_decisions: {}",
        "autopilot_decisions:\n  deployment:\n    mode: github-actions"), encoding="utf-8")
    check("★ 新配置一旦有声明 → 以它为准", _mode(d) == "github-actions")
    shutil.rmtree(d, ignore_errors=True)

    # 开关：commit_gate 与 aidp_config 同口径（门禁不得自带一份读法）
    e = Path(tempfile.mkdtemp())
    (e / "memory").mkdir()
    cg = _load("cg2", str(REPO / ".aidp/scripts/commit_gate.py"))
    check("★ 无配置 → 门禁缺省开启（两处一致）",
          cfg.commit_gate_enabled(str(e)) is True and cg.commit_gate_enabled(str(e)) is True)
    cfg.ensure(str(e))
    cfg.set_scalar(str(e), "commit_gate.enabled", False)
    check("★★ commit_gate 与 aidp_config 同口径（显式关闭两处都读到）",
          cfg.commit_gate_enabled(str(e)) is False and cg.commit_gate_enabled(str(e)) is False)
    cfg.set_scalar(str(e), "commit_gate.enabled", True)
    check("★ 写回开启后两处同步生效", cfg.commit_gate_enabled(str(e)) is True
          and cg.commit_gate_enabled(str(e)) is True)
    check("notify 缺省关闭且无渠道", cfg.notify_config(str(e))["enabled"] is False
          and cfg.notify_config(str(e))["channels"] == [])
    shutil.rmtree(e, ignore_errors=True)

    check("★ 逃生舱 touch memory/.autopilot-stop-guard-off 仍是最高优先（误报时要能盲打）",
          cfg.STOP_GUARD_OFF_REL.endswith(".autopilot-stop-guard-off"))
    check("脚本自带双侧对照可独立跑通（--self-check）",
          subprocess.run([sys.executable, str(REPO / ".aidp/scripts/aidp_config.py"),
                          "--self-check"], capture_output=True).returncode == 0)
    _sm = REPO / "skills/aidp-code-engineer/scripts/scaffold_marker.py"
    if _sm.is_file():
        check("版本戳访问器自带双侧对照可独立跑通",
              subprocess.run([sys.executable, str(_sm), "--self-check"],
                             capture_output=True).returncode == 0)
    else:
        skip("版本戳访问器 --self-check", "脚手架 skill 的 scaffold_marker.py 未就位")


def test_runtime_dir_bootstrap():
    """本地运行时目录 memory/.aidp/：写方只 open(a)、不建父目录 → 目录必须由我们保证。"""
    print("\n[F6] 本地运行时目录兜底")
    ap = _load("ap2", str(REPO / ".aidp/scripts/aidp_paths.py"))
    d = Path(tempfile.mkdtemp())
    (d / "memory").mkdir()
    ap.ensure_runtime_dir(str(d))
    check("★ ensure_runtime_dir 建得出目录（不建就静默丢记录）", (d / "memory/.aidp").is_dir())
    shutil.rmtree(d, ignore_errors=True)

    tf = (REPO / ".aidp/scripts/autopilot_tick_flags.py").read_text(encoding="utf-8")
    check("★ tick 热路径挂了兜底（存量项目不跑 scaffold 也能有这个目录）",
          "ensure_runtime_dir" in tf)

    for f in (".gitignore", "skills/aidp-code-engineer/assets/root/gitignore.tpl"):
        fp = REPO / f
        if not fp.is_file():
            skip(f"{f} 覆盖 memory/.aidp/", "文件未就位")
            continue
        check(f"{f} 覆盖本地运行时目录 memory/.aidp/", "memory/.aidp/" in fp.read_text(encoding="utf-8"))


def main():
    test_decidable_skips_levels()
    test_memory_protection_covers_claude_md()
    test_memory_baseline_without_git()
    test_lock_path_single_source()
    test_runtime_artifact_paths()
    test_config_consolidation()
    test_runtime_dir_bootstrap()
    print(f"\n══ 结果：{_passed} passed / {_failed} failed / {_skipped} skipped ══")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
