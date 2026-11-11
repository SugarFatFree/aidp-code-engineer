#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""无人值守链路的失败处置与自动恢复回归：

· `autopilot_fail_handle.py`：按链路取唤醒源（测试链路不误读开发链路键）、同 reason 冻结幂等、
  未达阈不发通知、冻结恒写本地告警台账、测试链路前置熔断键独立；
· `autopilot_unfreeze.py`：环境类自动复探（指数退避 + 上限 + 放行时清顶层阻塞原因）、
  成功路径显式解冻、人工解冻。
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import shutil
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SCRIPTS = REPO / ".aidp" / "scripts"
FH = str(SCRIPTS / "autopilot_fail_handle.py")
sys.path.insert(0, str(SCRIPTS))
import autopilot_unfreeze as U  # noqa: E402

_passed = _failed = 0


def check(name, cond):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ✅ {name}")
    else:
        _failed += 1
        print(f"  ❌ FAIL: {name}")


def _mk(baseline):
    root = Path(tempfile.mkdtemp(prefix="aidp-recover-"))
    (root / "memory").mkdir()
    (root / "memory/.sprint-autopilot-baseline.json").write_text(json.dumps(baseline), encoding="utf-8")
    return root


def _bl(root):
    return json.loads((root / "memory/.sprint-autopilot-baseline.json").read_text(encoding="utf-8"))


def _fh(root, *args):
    cp = subprocess.run([sys.executable, FH, "--json", *args], cwd=str(root),
                        capture_output=True, text=True, env={**os.environ, "AIDP_FEISHU_WEBHOOK": ""})
    try:
        out = json.loads(cp.stdout or "{}")
    except ValueError:
        out = {}
    return cp.returncode, out, cp.stderr


def test_retest_cap_probe_ignores_autopilot_pushes():
    print("\n[R0] 复测配额不能被其他版本的自动提交重置")
    from unittest.mock import patch
    from types import SimpleNamespace
    base = {"last_autopilot_head": "bot-other-version", "versions": {"V1.0.0": {
        "needs_human": True, "needs_human_kind": "retest-cap", "freeze_reason": "unconverged",
        "aiauto_frozen_at": "2026-01-01T00:00:00Z", "retest_cap_frozen_at": "2026-01-02T00:00:00Z",
        "retest_frozen_head": "frozen", "unconverged_frozen_head": "older", "auto_retest_streak": 3}}}
    root = _mk(base)
    try:
        def probe(head):
            with patch("subprocess.run", return_value=SimpleNamespace(stdout=head, returncode=0)):
                return U.aiauto_probe_all(str(root))
        check("自动提交不解冻任何被封顶版本", probe("bot-other-version")["unfreezable"] == [])
        check("冻结快照与其它快照不同时仍不误解冻", probe("frozen")["unfreezable"] == [])
        check("不同于冻结与自动提交的人工提交可解冻", probe("human-fix")["unfreezable"] == ["V1.0.0"])
        version = base["versions"]["V1.0.0"]
        version["last_deployed_at"] = "2026-01-01T12:00:00Z"
        (root / "memory/.sprint-autopilot-baseline.json").write_text(json.dumps(base))
        check("早于配额冻结的新部署不解冻", probe("bot-other-version")["unfreezable"] == [])
        version["last_deployed_at"] = "2026-01-03T00:00:00Z"
        (root / "memory/.sprint-autopilot-baseline.json").write_text(json.dumps(base))
        check("当前版本在配额冻结后重新部署可解冻", probe("bot-other-version")["unfreezable"] == ["V1.0.0"])
        version.pop("last_deployed_at")
        version.pop("retest_frozen_head")
        (root / "memory/.sprint-autopilot-baseline.json").write_text(json.dumps(base))
        check("配额冻结缺快照不使用其它版本提交时间兜底", probe("human-fix")["unfreezable"] == [])
        check("探测本身不修改配额", _bl(root)["versions"]["V1.0.0"]["auto_retest_streak"] == 3)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_fail_handle():
    print("\n[R1] 失败处置：链路分键 / 幂等 / 通知策略 / 告警台账")
    root = _mk({"aiauto": {"wake_source_this_tick": "1"}, "versions": {"V1.0.0": {}}})
    base = ["--version", "V1.0.0", "--phase", "0.1.1", "--reason", "chrome-unavailable", "--why", "无浏览器"]
    rc, out, _ = _fh(root, *base, "--command", "aiauto-test")
    check("★ 测试链路（aiauto 唤醒源=1）首次失败只记账、不冻结", rc == 0 and out.get("frozen") is False)
    check("★ 未达阈不发 #4", out.get("card_sent") is False)
    rc, out, _ = _fh(root, *base)
    check("阳性对照：同 baseline 按开发链路（autopilot 唤醒源缺失）→ 当场冻结", rc == 3 and out.get("frozen"))
    ledger = root / "memory/.aidp/alerts.jsonl"
    check("★ 冻结写本地告警台账（无通知渠道也「停得响」）", ledger.is_file() and ledger.read_text().strip())
    n_lines = len(ledger.read_text().splitlines())
    at1 = _bl(root)["versions"]["V1.0.0"]["aiauto_frozen_at"]
    time.sleep(1.1)
    rc, out, _ = _fh(root, *base, "--command", "aiauto-test")
    check("★ 同 reason 已冻结 → no-op：rc=3 + already_frozen", rc == 3 and out.get("already_frozen"))
    check("★ 幂等：冻结时刻不被刷新、不重复告警",
          _bl(root)["versions"]["V1.0.0"]["aiauto_frozen_at"] == at1
          and len(ledger.read_text().splitlines()) == n_lines)
    rc, out, err = _fh(root, *base[:-2])
    check("缺 --why → rc=2 且什么都没写", rc == 2)
    shutil.rmtree(root, ignore_errors=True)

    root = _mk({"versions": {}})
    for _ in range(3):
        rc, out, _ = _fh(root, "--preflight", "--command", "aiauto-test", "--reason", "git-pull-conflict",
                         "--why", "拉码冲突", "--threshold", "3")
    bl = _bl(root)
    check("★ 测试链路前置熔断用独立键 aiauto_preflight_*（不复用开发侧 preflight_*）",
          bl.get("aiauto_preflight_frozen_at") and "preflight_fail_streak" not in bl)
    shutil.rmtree(root, ignore_errors=True)

    # ★★ 前置熔断在**无唤醒源**时必须当场冻结：`/sprint-autopilot --once --unattended`
    #   撞上 detached HEAD / pull 冲突时，没有下一 tick 来叠 streak，阈值恒不可达 ——
    #   只记 streak=1 就结束，表现为「跑完了、什么都没说」，与正常收尾完全同形。
    root = _mk({"versions": {}})          # 无 autopilot.wake_source_this_tick ⇒ 视作无唤醒源
    rc, out, _ = _fh(root, "--preflight", "--command", "autopilot", "--reason", "git-pull-conflict",
                     "--why", "拉码冲突", "--threshold", "5")
    bl = _bl(root)
    check("★★ 无唤醒源 + 前置失败首次即熔断（否则静默停摆）",
          out.get("frozen") is True and bl.get("preflight_frozen_at"))
    # ★ 判据是「停得响」而非「发出去了」：未配置渠道时 card_sent=False 是**合法降级**，
    #   真正的承载面是本地告警台账 —— 且它必须落在**本项目**，不是进程 cwd 指向的别处。
    ledger = root / "memory/.aidp/alerts.jsonl"
    check("★★ 无唤醒源冻结 → 本地告警台账落在本项目（没渠道也要留得下证据）",
          ledger.is_file() and ledger.read_text().strip() != "")
    shutil.rmtree(root, ignore_errors=True)

    # 阴性：有唤醒源时首次失败只记账，不提前冻（否则每次瞬态冲突都冻版本）
    root = _mk({"autopilot": {"wake_source_this_tick": "1"}, "versions": {}})
    rc, out, _ = _fh(root, "--preflight", "--command", "autopilot", "--reason", "git-pull-conflict",
                     "--why", "拉码冲突", "--threshold", "5")
    check("阴性：有唤醒源时前置失败首次不冻结", out.get("frozen") is False
          and not _bl(root).get("preflight_frozen_at"))
    shutil.rmtree(root, ignore_errors=True)

    cp = subprocess.run([sys.executable, FH, "--self-check"], capture_output=True, text=True)
    check("★ --self-check 无需其他参数即可跑通", cp.returncode == 0)


def _frozen(reason, frozen_ago, **extra):
    t = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - frozen_ago))
    v = {"needs_human": True, "aiauto_frozen_at": t, "freeze_reason": reason,
         "needs_human_reason": "x", **extra}
    return {"aiauto_blocked_reason": "frozen:%s@V1.0.0" % reason, "versions": {"V1.0.0": v}}


def test_env_reprobe():
    print("\n[R2] 环境类自动复探：退避 / 放行 / 上限")
    envs = U.env_class_reasons()
    check("★ 环境类集合从权威表解析，含 cicd-unreachable 与 cicd-cli-unavailable",
          {"cicd-unreachable", "cicd-cli-unavailable", "probe-timeout"} <= envs)
    root = _mk(_frozen("cicd-unreachable", 5 * 60))
    r = U.env_reprobe(str(root), "V1.0.0", apply=True)
    check("冻结 5 分钟 < 20 分钟 → 未到复探时刻、不放行", not r["reprobe"] and _bl(root)["versions"]["V1.0.0"]["needs_human"])
    shutil.rmtree(root, ignore_errors=True)

    root = _mk(_frozen("cicd-cli-unavailable", 25 * 60))
    r = U.env_reprobe(str(root), "V1.0.0", apply=True)
    bl = _bl(root)
    vn = bl["versions"]["V1.0.0"]
    check("★ 冻结 25 分钟 → 放行：冻结字段清除", r["applied"] and "needs_human" not in vn and "freeze_reason" not in vn)
    check("★ 放行同时清以 @V 结尾的顶层 aiauto_blocked_reason", "aiauto_blocked_reason" not in bl)
    check("放行计数 +1", str(vn.get("env_reprobe_attempts")) == "1")
    shutil.rmtree(root, ignore_errors=True)

    root = _mk(_frozen("probe-timeout", 25 * 60, env_reprobe_attempts=2))
    r = U.env_reprobe(str(root), "V1.0.0", apply=True)
    check("★ 第 3 次复探需等 80 分钟（指数退避）→ 25 分钟不放行", not r["reprobe"])
    shutil.rmtree(root, ignore_errors=True)

    root = _mk(_frozen("probe-timeout", 10 * 3600, env_reprobe_attempts=U.REPROBE_MAX_ATTEMPTS))
    r = U.env_reprobe(str(root), "V1.0.0", apply=True)
    check("★ 达上限 → exhausted、不再自动放行、写告警台账",
          r["exhausted"] and not r["reprobe"] and (root / "memory/.aidp/alerts.jsonl").is_file())
    shutil.rmtree(root, ignore_errors=True)

    root = _mk(_frozen("handoff-exhausted", 10 * 3600))
    r = U.env_reprobe(str(root), "V1.0.0", apply=True)
    check("阴性：人工专属类不走自动复探", not r["reprobe"] and _bl(root)["versions"]["V1.0.0"]["needs_human"])
    shutil.rmtree(root, ignore_errors=True)


def test_clear_and_manual():
    print("\n[R3] 显式解冻 / 人工解冻")
    root = _mk(_frozen("chrome-unavailable", 60))
    r = U.clear_if_reason(str(root), "V1.0.0", "probe-timeout")
    check("reason 不匹配 → 不动", not r["cleared"] and _bl(root)["versions"]["V1.0.0"]["needs_human"])
    r = U.clear_if_reason(str(root), "V1.0.0", "chrome-unavailable")
    check("★ 驱动检测通过 → --clear chrome-unavailable 解冻", r["cleared"] and "needs_human" not in _bl(root)["versions"]["V1.0.0"])
    shutil.rmtree(root, ignore_errors=True)

    root = _mk(_frozen("stuck-phase", 60, dev_fail_streak=5, needs_human_kind="retest-cap"))
    r = U.manual_unfreeze(str(root), "V1.0.0")
    vn = _bl(root)["versions"]["V1.0.0"]
    check("★ 人工解冻清冻结字段、复测上限标记与失败计数",
          r["cleared"] and not any(k in vn for k in ("needs_human", "dev_fail_streak", "needs_human_kind")))
    shutil.rmtree(root, ignore_errors=True)

    # ★★ 解冻必须同时重置**正在生效的那个**停滞窗口：`stuck-phase` 的判据读 `run_state`
    #   （autopilot_stuck_check）与 `aiauto_run_state`（check_stuck_phase）两处。只清冻结字段
    #   不清计数，下个 tick 判据原封不动成立 → 立刻重冻。而恢复指引给的正是 `--manual`：
    #   照做 = 解冻、重冻、再解冻，版本就此永久锁死。
    for state_key in ("run_state", "aiauto_run_state"):
        root = _mk(_frozen("stuck-phase", 60,
                           **{state_key: {"current_phase": "3.2-dev", "next_phase": "3.2-dev",
                                          "phase_enter_count": 9,
                                          "phase_first_entered_at": "2026-01-01T00:00:00Z"}}))
        r = U.manual_unfreeze(str(root), "V1.0.0")
        rs = (_bl(root)["versions"]["V1.0.0"].get(state_key) or {})
        check(f"★★ 人工解冻重置 {state_key} 停滞窗口（否则立刻重冻）",
              r["cleared"] and int(rs.get("phase_enter_count") or 0) <= 1)
        check(f"★★ {state_key} 首次进入时刻一并刷新（旧时刻会让时长判据恒成立）",
              r["cleared"] and str(rs.get("phase_first_entered_at") or "") not in ("", "2026-01-01T00:00:00Z"))
        shutil.rmtree(root, ignore_errors=True)

    # 非 stuck-phase 的冻结不该动停滞窗口（那是另一类问题的证据，清了会掩盖推进情况）
    root = _mk(_frozen("chrome-unavailable", 60,
                       run_state={"current_phase": "3.2-dev", "phase_enter_count": 9,
                                  "phase_first_entered_at": "2026-01-01T00:00:00Z"}))
    U.manual_unfreeze(str(root), "V1.0.0")
    check("阴性：非 stuck-phase 解冻不动停滞计数",
          _bl(root)["versions"]["V1.0.0"]["run_state"]["phase_enter_count"] == 9)
    shutil.rmtree(root, ignore_errors=True)


def test_aiauto_stuck_phase_contract():
    print("\n[R5] 测试链路 stuck-phase：次数 + 时长双判据")
    import check_stuck_phase as S
    now = 1_000_000_000
    iso = lambda off: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - off))
    check("两条件同时满足 → 判 stuck", S.evaluate(8, iso(7300), now)["stuck"] is True)
    check("只够次数 → 不误冻", S.evaluate(20, iso(600), now)["stuck"] is False)
    check("只够时长 → 不误冻", S.evaluate(2, iso(99999), now)["stuck"] is False)
    check("首次时间缺失 → 不误冻", S.evaluate(99, "", now)["stuck"] is False)
    check("测试链路使用独立 aiauto_run_state", "aiauto_run_state" in (Path(S.__file__).read_text(encoding="utf-8")))


def _prd_watch_fence():
    """phase-1.md 1.2 的变化检测围栏原文（第一个 ```bash 块）。"""
    text = (REPO / ".aidp/flows/sprint-autopilot/phase-1.md").read_text(encoding="utf-8")
    start = text.find("### 1.2 ")
    end = text.find("### 1.3 ", start)
    block = text[start:end]
    m = re.search(r"```bash\n(.*?)```", block, re.S)
    return m.group(1) if m else ""


def test_prd_watch_steady_state():
    """★ 「上版等准发布、下版还没提 PRD」（TARGET 空 + PRE_RELEASE 非空）是 7×24 最常见的稳态。

    Phase 0.3.4 的决策矩阵允许它，并会把 `TARGET_VERSION` 落成**空串**；此时 1.2 若用
    `: "${TARGET_VERSION:?...}"` 就会整 tick 中止 —— 该版 `internal_released_at` 永远写不上，
    每 10 分钟重撞一次，Phase 2 结构上不可达。
    """
    print("\n[R6] Phase 1.2 变化检测：准发布-only 稳态不得中止 tick")
    fence = _prd_watch_fence()
    check("取到 1.2 变化检测围栏", bool(fence.strip()))
    check("阴性对照：围栏里确实还引用 TARGET_VERSION",
          "TARGET_VERSION" in fence)
    if not fence.strip():
        return
    # 用真实 shell 跑：空 TARGET 不再中止，非空仍按原路径（脚本被替换为惰性桩）
    root = Path(tempfile.mkdtemp(prefix="aidp-prdwatch-"))
    (root / "memory").mkdir()
    (root / "memory/.sprint-autopilot-baseline.json").write_text(
        json.dumps({"autopilot": {"target_version": "", "pre_release_version": "V0.9.0"},
                    "versions": {"V0.9.0": {}}}), encoding="utf-8")
    for name in ("scripts", "hooks"):
        (root / name).mkdir()
    shim = root / "scripts"
    (shim / "autopilot_tick_flags.py").write_text(
        'import sys\nprint("TARGET_VERSION=\'\'")\nprint("PRE_RELEASE_VERSION=V0.9.0")\nprint("HAS_WAKE_SOURCE=1")\n',
        encoding="utf-8")
    (shim / "autopilot-prd-watch.py").write_text(
        'import sys,os\nopen(os.environ["PRDWATCH_HIT"],"w").write("called")\nprint("SHOULD_RUN=0")\n',
        encoding="utf-8")
    hit = root / "called.marker"
    body = (fence.replace("{{AIDP_HOME}}", str(root))
            .replace('PRD_ROOT="${1:-docs/requirements/}"', 'PRD_ROOT="docs/requirements/"'))
    (root / "fence.sh").write_text(body + "\necho \"AFTER_FENCE rc=0\"\n", encoding="utf-8")
    (root / "docs/requirements").mkdir(parents=True)
    cp = subprocess.run(["bash", str(root / "fence.sh")], cwd=str(root),
                        capture_output=True, text=True,
                        env={**os.environ, "PRDWATCH_HIT": str(hit)})
    check("★ 空 TARGET_VERSION + 非空 PRE_RELEASE_VERSION → 围栏内不中止（tick 还能走到 Phase 2）",
          cp.returncode == 0 and "AFTER_FENCE" in cp.stdout)
    check("★ 版本号为空时不拿空串去调 prd-watch（否则落一个垃圾版本节点）", not hit.exists())
    check("   失败时打印的仍是真因（不是与事实相反的占位符提示）",
          cp.returncode == 0 or "TARGET_VERSION" in cp.stderr)
    shutil.rmtree(root, ignore_errors=True)


def test_vcs_disabled_unattended_flow_contract():
    print("\n[R4] 无 Git 时跳过远端节点、继续本地开发")
    base = REPO / ".aidp/flows/sprint-autopilot"
    preflight = (base / "phase-0-3.md").read_text(encoding="utf-8")
    push = (base / "phase-3-5b.md").read_text(encoding="utf-8")
    cicd = (base / "phase-3-6.md").read_text(encoding="utf-8")
    check("拉码无 Git 不冻结本地开发", "vcs_mode=none" in preflight and "不冻结" in preflight)
    check("推送无 Git 记 skipped 且继续", "vcs_mode=none" in push and "unsupported:vcs-disabled" in push and "skipped" in push)
    check("CICD 无 Git 不误判成功", "vcs_mode=none" in cicd and "unsupported:vcs-disabled" in cicd and "不得标记通过" in cicd)


def test_build_mint_registers_one_row():
    print("【铸 build：current_build 占位行与完整登记合并为一行】")
    repo = Path(__file__).resolve().parents[3]
    flow = (repo / ".aidp/flows/sprint-autopilot/phase-3-4a.md").read_text(encoding="utf-8")
    code = re.search(r"python3 - <<'PY'\n(.*?)\nPY", flow, re.S).group(1)
    code = code.replace("{{AIDP_HOME}}", str(repo / ".aidp"))
    with tempfile.TemporaryDirectory() as td:
        bl = Path(td) / "memory/.sprint-autopilot-baseline.json"
        bl.parent.mkdir()
        bl.write_text('{"versions":{}}', encoding="utf-8")
        for _ in range(2):
            subprocess.run([sys.executable, str(repo / ".aidp/scripts/baseline_edit.py"), "--baseline", str(bl),
                            "--version", "V1.0.0", "set", "build_seq", "1001",
                            "current_build", "V1.0.0_build1001"], cwd=td, check=True, capture_output=True)
            subprocess.run([sys.executable, "-c", code], cwd=td, check=True, capture_output=True,
                           env=dict(os.environ, BV="V1.0.0", BUILD="V1.0.0_build1001", ENTRY_MODE="full"))
        builds = json.loads(bl.read_text(encoding="utf-8"))["versions"]["V1.0.0"]["builds"]
    check("同一 build 只有一行，且不是 unknown 占位", len(builds) == 1 and builds[0]["status"] == "running"
          and builds[0].get("entry_mode") == "full")


def test_active_sprint_recovery():
    print("\n[R7] 中断 Sprint 必须恢复开发，缺交付证据不得关闭")
    flow = (REPO / ".aidp/flows/sprint-autopilot/phase-0-6b.md").read_text(encoding="utf-8")
    active = flow[flow.index("### 0.4 "):]
    full = (REPO / ".aidp/commands/sprint-full.md").read_text(encoding="utf-8")
    close = (REPO / ".aidp/commands/sprint-close.md").read_text(encoding="utf-8")
    dispatch = (REPO / ".aidp/flows/sprint-autopilot/phase-3-5.md").read_text(encoding="utf-8")
    check("active Sprint 不再按中断直接关闭", "调 `/sprint-close --unattended`" not in active)
    check("恢复入口落 3.2-dev 游标并由 full --resume 执行", 'NEXT_PHASE="3.2-dev"' in active
          and "set run_state.next_phase" in active and "--resume" in dispatch)
    check("close 无证据返回 incomplete-sprint，禁止写关闭归档", "incomplete-sprint" in close
          and "无测试证据，按未验证归档" not in close)
    match = re.search(r"<!-- resume-gate -->\s*```bash\n(.*?)```", full, re.S)
    check("full --resume 有可执行身份与在途轮次校验", match is not None)
    if not match:
        return
    body = match.group(1).replace("{{AIDP_HOME}}", str(REPO / ".aidp"))
    body = body.replace("{version}", "V1.0.0").replace("{NNN}", "001")
    with tempfile.TemporaryDirectory(prefix="aidp-resume-") as directory:
        root = Path(directory)
        plan = root / "docs/plans/V1.0.0/01_研发执行计划.md"
        plan.parent.mkdir(parents=True)
        plan.write_text("- Sprint-001 登录\n- Sprint-002 导出\n", encoding="utf-8")
        memory = root / "memory/V1.0.0/alice"
        memory.mkdir(parents=True)
        ctx = memory / "activeContext.md"
        ctx.write_text("- 当前 Sprint：Sprint-001\n- 已完成：登录接口\n- 待办：权限检查\n", encoding="utf-8")
        before = ctx.read_bytes()
        def run():
            return subprocess.run(["bash", "-c", body], cwd=root, text=True, capture_output=True,
                                  env={**os.environ, "AIDP_USER": "alice"})
        check("同号同用户中断可续跑且不重置上下文", run().returncode == 0 and ctx.read_bytes() == before)
        handoff = re.search(r"<!-- resume-state -->\s*```bash\n(.*?)```", active, re.S)
        check("恢复状态有可执行交接围栏", handoff is not None)
        if handoff:
            baseline = root / "memory/.sprint-autopilot-baseline.json"
            baseline.write_text(json.dumps({"autopilot": {"target_version": "V1.0.0"}, "versions": {
                "V1.0.0": {"current_build": "V1.0.0_build1001", "run_state": {
                    "current_phase": "3.2-dev", "next_phase": "3.2-dev", "next_sprint": "001",
                    "phase_enter_count": 4}}}}), encoding="utf-8")
            script = handoff.group(1).replace("{{AIDP_HOME}}", str(REPO / ".aidp"))
            result = subprocess.run(["bash", "-c", script], cwd=root, capture_output=True, text=True)
            state = _bl(root)["versions"]["V1.0.0"]
            check("恢复同 build / 同 Sprint 并保留停滞计数", result.returncode == 0
                  and state["current_build"] == "V1.0.0_build1001"
                  and state["run_state"]["next_phase"] == "3.2-dev"
                  and str(state["run_state"]["next_sprint"]) == "001"
                  and state["run_state"]["phase_enter_count"] == 4)
            check("恢复交接不生成关闭归档", not (memory / "sprints/sprint-001.md").exists()
                  and ctx.read_bytes() == before)
        ctx.write_text("- 当前 Sprint：Sprint-002\n", encoding="utf-8")
        check("不能用 --resume 接管另一 Sprint", run().returncode != 0)
        ctx.write_bytes(before)
        other = root / "memory/V1.0.0/bob"
        other.mkdir()
        (other / "activeContext.md").write_bytes(before)
        check("跨用户同号在途不得自动接管", run().returncode != 0)
        shutil.rmtree(other)
        (memory / "progress.md").write_text("Sprint-001 ✅ 已关闭\n", encoding="utf-8")
        (memory / "sprints").mkdir()
        (memory / "sprints/sprint-001.md").write_text("已归档\n", encoding="utf-8")
        check("已关闭 Sprint 不得当作中断开发重跑", run().returncode != 0)


def test_wake_source_requires_scheduler():
    print("\n[R8] 手动调用频次不能伪装成下一 tick 唤醒源")
    flow = (REPO / ".aidp/flows/sprint-autopilot/phase-0-1.md").read_text(encoding="utf-8")
    body = flow[flow.index("IS_LOOP_CONTEXT=0    #"):flow.index("# ★ 把「本轮将怎么跑」")]
    body = body.replace("{{AIDP_HOME}}", str(REPO / ".aidp"))
    cases = [("反复手动 once", 0, 0, 0, "token", "0:0"),
             ("反复 once unattended", 0, 0, 1, "token", "0:1"),
             ("真实 loop", 1, 0, 1, "token", "1:1"),
             ("cron no-loop", 0, 1, 1, "token", "1:1"),
             ("wrapper 锁持有者", 0, 0, 1, "agent_loop", "1:1")]
    with tempfile.TemporaryDirectory(prefix="aidp-wake-evidence-") as directory:
        for label, context, no_loop, unattended, token, expected in cases:
            script = body.replace("IS_LOOP_CONTEXT=0    #", f"IS_LOOP_CONTEXT={context}    #")
            script += '\nprintf "RESULT=%s:%s\\n" "$HAS_WAKE_SOURCE" "$LOOP_UNATTENDED"\n'
            env = {**os.environ, "LOOP_EVIDENCE": "0" if token == "agent_loop" else "1", "HAS_ONCE_FLAG": "1",
                   "HAS_NO_LOOP_FLAG": str(no_loop), "HAS_UNATTENDED_FLAG": str(unattended),
                   "TICK_LOCK_TOKEN": token}
            result = subprocess.run(["bash", "-c", script], cwd=directory, capture_output=True, text=True, env=env)
            check(label, result.returncode == 0 and f"RESULT={expected}" in result.stdout)


def test_recovery_regressions():
    print("\n[R9] 冻结幂等、活性同源、环境重试与连续失败范围")
    from datetime import datetime, timezone
    args = ["--preflight", "--reason", "prd-root-missing", "--why", "目录缺失"]
    root = _mk({"versions": {}})
    try:
        rc, _, _ = _fh(root, *args)
        first = _bl(root)
        ledger = root / "memory/.aidp/alerts.jsonl"
        lines = ledger.read_text().splitlines()
        rc2, out, _ = _fh(root, *args, "--card-on-streak")
        check("前置首次及重复冻结均 rc3", rc == rc2 == 3)
        check("前置同 reason 只记账、不刷新时刻不发卡", out.get("already_frozen")
              and _bl(root)["preflight_fail_streak"] == 2
              and first["preflight_frozen_at"] == _bl(root)["preflight_frozen_at"]
              and ledger.read_text().splitlines() == lines)
        rc, _, _ = _fh(root, "--preflight", "--reason", "preflight-gate", "--why", "新原因")
        check("前置换 reason 首次告警仍发送", rc == 3 and len(ledger.read_text().splitlines()) == len(lines) + 1)
    finally:
        shutil.rmtree(root)

    for blocked in ("frozen:account-invalid@V1.0.0", "frozen:chrome-unavailable@V2.0.0", "global-error"):
        data = _frozen("config-missing", 60)
        data["aiauto_blocked_reason"] = blocked
        data["aiauto_test_heartbeat_at"] = datetime.now(timezone.utc).isoformat()
        root = _mk(data)
        try:
            check("新心跳不绕过真实阻塞 " + blocked, not U.aiauto_probe(str(root), "V1.0.0")["unfreeze"])
        finally:
            shutil.rmtree(root)
    data = _frozen("config-missing", 60)
    data["aiauto_test_heartbeat_at"] = datetime.now(timezone.utc).isoformat()
    root = _mk(data)
    try:
        check("仅自身 config-missing 标记不造成自锁", U.aiauto_probe(str(root), "V1.0.0")["unfreeze"])
    finally:
        shutil.rmtree(root)
    root = _mk({"aiauto_blocked_reason": "frozen:chrome-unavailable@V2.0.0", "versions": {"V1.0.0": {}}})
    try:
        _fh(root, "--version", "V1.0.0", "--phase", "2-prerelease-testloop", "--reason", "config-missing", "--why", "测试阻塞")
        check("config-missing 写侧保留测试真实 blocked_reason", _bl(root)["aiauto_blocked_reason"] == "frozen:chrome-unavailable@V2.0.0")
    finally:
        shutil.rmtree(root)

    root = _mk(_frozen("deploy-unreachable", 25 * 60, dev_fail_phase="2-prerelease-deploy",
                      prerelease_deploy_block_streak=3, cicd_run={"cicd_retry_count": 3, "run_id": "keep"},
                      run_state={"next_phase": "2-prerelease", "next_sprint": "done"}))
    try:
        r = U.env_reprobe(str(root), "V1.0.0", apply=True)
        vn = _bl(root)["versions"]["V1.0.0"]
        check("复探重置 CICD 重试预算并保留运行证据", r["applied"] and vn["cicd_run"].get("cicd_retry_count", 0) == 0 and vn["cicd_run"]["run_id"] == "keep")
        check("准发布部署失败复探后实际可重部署", vn["run_state"]["next_phase"] == "3.2.1-deploy"
              and vn.get("prerelease_deploy_block_streak", 0) == 0)
    finally:
        shutil.rmtree(root)

    root = _mk({"autopilot": {"wake_source_this_tick": "1"}, "versions": {"V1.0.0": {}}})
    try:
        def fail(phase, reason):
            return _fh(root, "--version", "V1.0.0", "--phase", phase, "--reason", reason, "--why", "失败", "--threshold", "10")
        fail("3.1-plan", "plan-transient")
        _, out, _ = fail("3.1-plan", "plan-transient")
        check("同 phase/reason 连续累加", out.get("streak") == 2)
        _, out, _ = fail("3.2-dev", "plan-transient")
        check("换 phase 从1重计", out.get("streak") == 1)
        _, out, _ = fail("3.2-dev", "handoff-exhausted")
        check("换 reason 从1重计", out.get("streak") == 1)
        rc, _, _ = _fh(root, "--success", "--version", "V1.0.0", "--phase", "3.1-plan")
        check("其他阶段成功不误清计数", rc == 0 and _bl(root)["versions"]["V1.0.0"]["dev_fail_streak"] == 1)
        rc, _, _ = _fh(root, "--success", "--version", "V1.0.0", "--phase", "3.2-dev")
        vn = _bl(root)["versions"]["V1.0.0"]
        check("本阶段成功清零及范围元数据", rc == 0 and vn.get("dev_fail_streak") == 0
              and "dev_fail_phase" not in vn and "dev_fail_reason" not in vn)
    finally:
        shutil.rmtree(root)

    root = _mk(_frozen("account-invalid", 60))
    try:
        before = _bl(root)
        rc, _, _ = _fh(root, "--version", "V1.0.0", "--phase", "2-prerelease-testloop",
                        "--reason", "config-missing", "--why", "测试仍阻塞", "--freeze-now")
        check("config-missing 不覆盖已有测试冻结证据", rc == 3 and _bl(root) == before)
    finally:
        shutil.rmtree(root)

    flow = (REPO / ".aidp/flows/sprint-autopilot/phase-2.md").read_text()
    check("归档失败使用合法字面量 release-blocked", "local-archive-failed" not in flow
          and '--phase 2-prerelease --reason release-blocked' in flow)
    for name in ("phase-0-6.md", "phase-0-9.md"):
        flow = (REPO / ".aidp/flows/sprint-autopilot" / name).read_text()
        check(name + " 前置失败统一入口", "--preflight" in flow and "bump preflight_fail_streak" not in flow)


def test_recovery_scope_boundaries():
    print("\n[R10] 恢复边界与真实 flow 入口")
    from datetime import datetime, timezone, timedelta
    for age in (120, 7200):
        data = _frozen("config-missing", 60 if age == 120 else 10000)
        data["aiauto_test_heartbeat_at"] = (datetime.now(timezone.utc) - timedelta(seconds=age)).isoformat()
        root = _mk(data)
        try:
            check("心跳必须晚于冻结且在 TTL 内 " + str(age), not U.aiauto_probe(str(root), "V1.0.0")["unfreeze"])
        finally:
            shutil.rmtree(root)
    data = _frozen("config-missing", 60)
    data["aiauto_test_heartbeat_at"] = datetime.now(timezone.utc).isoformat()
    data["aiauto_blocked_reason"] = "frozen:account-invalid@V2.0.0"
    root = _mk(data)
    try:
        check("其他版本局部阻塞不影响恢复", U.aiauto_probe(str(root), "V1.0.0")["unfreeze"])
        U.clear_if_reason(str(root), "V1.0.0", "config-missing")
        check("清冻结不误删其他测试阻塞", _bl(root)["aiauto_blocked_reason"] == data["aiauto_blocked_reason"])
    finally:
        shutil.rmtree(root)

    root = _mk(_frozen("plan-transient", 60, subagent_retry_at="old", subagent_retry_round=3,
                      subagent_retry_stage="exhausted", subagent_retry_phase="3.1-plan"))
    try:
        U.clear_if_reason(str(root), "V1.0.0", "plan-transient")
        check("plan-transient 恢复清调度退避状态", not any(k.startswith("subagent_retry_") for k in _bl(root)["versions"]["V1.0.0"]))
    finally:
        shutil.rmtree(root)

    root = _mk({"autopilot": {"wake_source_this_tick": "1"}, "versions": {"V1.0.0": {
        "dev_fail_streak": 2, "dev_fail_phase": "3.2-dev", "dev_fail_reason": "plan-transient",
        "current_build": "V1.0.0_build1001", "builds": [{"build": "V1.0.0_build1001"}]}}})
    try:
        args = ["--version", "V1.0.0", "--build", "V1.0.0_build1001", "--phase", "3.2.1-deploy"]
        _fh(root, *args, "--reason", "deploy-unreachable", "--why", "部署失败")
        rc, _, _ = _fh(root, *args, "--success")
        vn = _bl(root)["versions"]["V1.0.0"]
        check("build 成功不清版本计数", rc == 0 and vn["dev_fail_streak"] == 2 and vn["builds"][0]["dev_fail_streak"] == 0)
    finally:
        shutil.rmtree(root)
    root = _mk(_frozen("release-blocked", 60, dev_fail_streak=3, dev_fail_phase="2-prerelease", dev_fail_reason="release-blocked"))
    try:
        before = _bl(root)["versions"]["V1.0.0"]["aiauto_frozen_at"]
        _fh(root, "--success", "--version", "V1.0.0", "--phase", "2-prerelease")
        vn = _bl(root)["versions"]["V1.0.0"]
        check("成功清零 API 不绕过人工冻结", vn["needs_human"] and vn["freeze_reason"] == "release-blocked" and vn["aiauto_frozen_at"] == before)
    finally:
        shutil.rmtree(root)

    data = _frozen("deploy-unreachable", 25 * 60, current_build="V1.0.0_build1002",
                   cicd_run={"cicd_retry_count": 3}, env_reprobe_attempts=0,
                   run_state={"next_phase": "3.2.1-deploy"},
                   unconverged_frozen_head="keep", retest_frozen_head="keep2",
                   builds=[{"build": "V1.0.0_build1001", "dev_fail_streak": 3},
                           {"build": "V1.0.0_build1002", "dev_fail_streak": 3,
                            "dev_fail_phase": "3.2.1-deploy", "dev_fail_reason": "deploy-unreachable",
                            "cicd_run": {"cicd_retry_count": 3}}])
    root = _mk(data)
    try:
        U.env_reprobe(str(root), "V1.0.0", apply=True)
        vn = _bl(root)["versions"]["V1.0.0"]
        check("部署复探清当前build预算、保留历史build", vn["builds"][1].get("dev_fail_streak", 0) == 0
              and vn["builds"][1]["cicd_run"].get("cicd_retry_count", 0) == 0
              and vn["builds"][0]["dev_fail_streak"] == 3 and vn["run_state"]["next_phase"] == "3.2.1-deploy")
        check("复探保留冻结 HEAD 证据和退避计数", vn["unconverged_frozen_head"] == "keep"
              and vn["retest_frozen_head"] == "keep2" and vn["env_reprobe_attempts"] == 1)
    finally:
        shutil.rmtree(root)

    flow = (REPO / ".aidp/flows/sprint-autopilot/phase-0-6.md").read_text()
    fence = re.search(r"#### 0.3.1.*?```bash\n(.*?)```", flow, re.S).group(1)
    root = _mk({"versions": {}})
    try:
        body = fence.replace("{{AIDP_HOME}}", str(REPO / ".aidp"))
        for _ in range(2):
            cp = subprocess.run(["bash", "-c", body], cwd=root, capture_output=True, text=True,
                                env={**os.environ, "AIDP_FEISHU_WEBHOOK": ""})
        check("PRD 前置真实围栏重入只告警一次", cp.returncode == 0
              and len((root / "memory/.aidp/alerts.jsonl").read_text().splitlines()) == 1
              and _bl(root)["preflight_fail_streak"] == 2)
    finally:
        shutil.rmtree(root)

def _merge_fence():
    """取 phase-3-5b.md 推送围栏里「push DEV_BRANCH → 合并到部署源 → 记 push_commit」那一段真实文本。"""
    t = (REPO / ".aidp/flows/sprint-autopilot/phase-3-5b.md").read_text(encoding="utf-8")
    a = t.index("        _push_fail() {")
    b = t.index("        $BE --version \"$TARGET_VERSION\" --build \"$BUILD\" set push_at", a)
    body = "\n".join(l[8:] if l.startswith("        ") else l for l in t[a:b].splitlines())
    return body


def _git(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)


def test_push_fence_merge_to_deploy_source():
    """B-03：合并到部署源失败（冲突）时必须中止合并、切回 DEV_BRANCH、走失败处置；成功时也切回。"""
    print("▶ 推送围栏：合并到部署源的错误处理与切回开发分支")
    for conflict in (True, False):
        root = Path(tempfile.mkdtemp(prefix="aidp-pushfence-"))
        try:
            origin, work, stub = root / "origin.git", root / "work", root / "stub"
            stub.mkdir()
            (stub / "scripts").mkdir()
            (stub / "scripts/autopilot_fail_handle.py").write_text(
                "import sys,pathlib\npathlib.Path(%r).write_text(' '.join(sys.argv[1:]))\n" % str(root / "failcalled"))
            (stub / "scripts/classify_push.py").write_text("")
            subprocess.run(["git", "init", "-q", "--bare", "-b", "master", str(origin)], check=True)
            subprocess.run(["git", "clone", "-q", str(origin), str(work)], capture_output=True)
            for k, v in (("user.email", "t@t"), ("user.name", "t")):
                _git(work, "config", k, v)
            _git(work, "checkout", "-q", "-b", "master")
            (work / "a.txt").write_text("base\n"); _git(work, "add", "."); _git(work, "commit", "-qm", "base")
            _git(work, "push", "-q", "origin", "master")
            _git(work, "checkout", "-q", "-b", "feat")
            (work / "a.txt").write_text("feat\n"); _git(work, "commit", "-qam", "feat")
            _git(work, "checkout", "-q", "master")
            if conflict:  # 部署源上有冲突的并行提交
                (work / "a.txt").write_text("master-side\n"); _git(work, "commit", "-qam", "m2")
                _git(work, "push", "-q", "origin", "master")
            _git(work, "checkout", "-q", "feat")
            body = _merge_fence().replace("{{AIDP_HOME}}", str(stub))
            script = ("BE=true; TARGET_VERSION=V1; BUILD=b1; DEV_BRANCH=feat; PENDING_MERGE_TO=master\n"
                      "set -u\n" + body + "\necho REACHED_END")
            cp = subprocess.run(["bash", "-c", script], cwd=work, capture_output=True, text=True)
            branch = _git(work, "branch", "--show-current").stdout.strip()
            tag = "冲突" if conflict else "无冲突"
            check(f"[{tag}] 围栏结束后工作树回到 DEV_BRANCH", branch == "feat")
            check(f"[{tag}] 无残留 MERGE_HEAD", not (work / ".git/MERGE_HEAD").exists())
            if conflict:
                check("[冲突] 走了失败处置且部署源未被推出未合并 tip",
                      (root / "failcalled").exists() and "REACHED_END" not in cp.stdout)
            else:
                check("[无冲突] 部署源已含本轮代码且不走失败处置",
                      not (root / "failcalled").exists()
                      and _git(origin, "log", "--format=%s", "master").stdout.count("feat") >= 1)
        finally:
            shutil.rmtree(root)


def test_dev_branch_registered_in_tick_flags():
    print("▶ DEV_BRANCH 已登记为 autopilot tick 变量")
    import autopilot_tick_flags as F
    check("DEV_BRANCH 在 autopilot DERIVED_VARS 中", "DEV_BRANCH" in F.DERIVED_VARS["autopilot"])


def test_tech_boundary_preconfirmation():
    """B-01：无人值守技术边界只机械读用户已落盘声明（PRD tech_boundary > 技术选型.md），不推断；缺失即 rc=1。"""
    print("▶ 无人值守技术边界预确认判定（autopilot_tech_boundary.py）")
    TB = str(SCRIPTS / "autopilot_tech_boundary.py")
    root = Path(tempfile.mkdtemp(prefix="aidp-techb-"))
    try:
        def run(*a):
            return subprocess.run([sys.executable, TB, "--root", str(root), "--version", "V1.0.0", *a],
                                  capture_output=True, text=True)
        cp = run("--json")
        check("两源皆空 → missing/rc=1，不推断", cp.returncode == 1 and json.loads(cp.stdout)["status"] == "missing"
              and json.loads(cp.stdout)["missing"] == ["backend", "database"])
        arch = root / "docs/architecture"
        arch.mkdir(parents=True)
        (arch / "技术选型.md").write_text(
            "| 分类 | 项目 | 技术选型 | 版本 | 理由 | 决策人 | Sprint |\n|--|--|--|--|--|--|--|\n"
            "| 数据库 | - | - | - | - | - | - |\n| 后端框架 | - | Spring Boot | 3 | x | u | 1 |\n", encoding="utf-8")
        check("模板占位行不算确认：只有后端、缺数据库 → missing", run().returncode == 1
              and json.loads(run("--json").stdout)["missing"] == ["database"])
        (arch / "技术选型.md").write_text(
            "| 分类 | 项目 | 技术选型 | 版本 | 理由 | 决策人 | Sprint |\n|--|--|--|--|--|--|--|\n"
            "| 数据库 | - | 达梦 DM8 | 8 | x | u | 1 |\n| 后端框架 | - | Spring Boot | 3 | x | u | 1 |\n", encoding="utf-8")
        res = json.loads(run("--json").stdout)
        check("技术选型.md 已填 → confirmed 且 db_dialect=dameng", res["status"] == "confirmed"
              and res["db_dialect"] == "dameng" and "技术选型.md" in res["source"])
        prd = root / "docs/requirements/V1.0.0/产品提供"
        prd.mkdir(parents=True)
        (prd / "prd.md").write_text("---\nautopilot_decisions:\n  tech_boundary:\n    backend: none\n"
                                    "    database: none\n---\n# PRD\n", encoding="utf-8")
        res = json.loads(run("--json").stdout)
        check("PRD tech_boundary 优先，显式 none 是声明而非缺失", res["status"] == "confirmed"
              and res["source"].startswith("prd:") and res["db_dialect"] == "none")
        out = run("--summary").stdout
        check("--summary 输出『确认汇总』并禁止推断未列维度", "确认汇总" in out and "不得推断" in out)
    finally:
        shutil.rmtree(root)


if __name__ == "__main__":
    test_recovery_scope_boundaries()
    test_recovery_regressions()
    test_retest_cap_probe_ignores_autopilot_pushes()
    test_wake_source_requires_scheduler()
    test_active_sprint_recovery()
    test_fail_handle()
    test_env_reprobe()
    test_clear_and_manual()
    test_aiauto_stuck_phase_contract()
    test_vcs_disabled_unattended_flow_contract()
    test_prd_watch_steady_state()
    test_build_mint_registers_one_row()
    test_push_fence_merge_to_deploy_source()
    test_dev_branch_registered_in_tick_flags()
    test_tech_boundary_preconfirmation()
    print(f"\n══ 结果：{_passed} passed / {_failed} failed ══")
    sys.exit(1 if _failed else 0)
