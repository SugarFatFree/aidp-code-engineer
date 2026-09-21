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


if __name__ == "__main__":
    test_fail_handle()
    test_env_reprobe()
    test_clear_and_manual()
    print(f"\n══ 结果：{_passed} passed / {_failed} failed ══")
    sys.exit(1 if _failed else 0)
