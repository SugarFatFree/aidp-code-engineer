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


if __name__ == "__main__":
    test_fail_handle()
    test_env_reprobe()
    test_clear_and_manual()
    test_aiauto_stuck_phase_contract()
    test_vcs_disabled_unattended_flow_contract()
    test_prd_watch_steady_state()
    print(f"\n══ 结果：{_passed} passed / {_failed} failed ══")
    sys.exit(1 if _failed else 0)
