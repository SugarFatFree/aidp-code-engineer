#!/usr/bin/env python3
"""C1/C2 派发退避状态；只记账，不派 Agent、不等待、不替代统一失败处置。

退出码：0=可派发/已清零，10=有唤醒源可 yield，11=改小粒度，
12=工具不可用，进 C3 预算检查，13=无唤醒源，必须本轮处理，20=失败处置，2=输入/状态错误。
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from baseline_edit import LockedBaseline

FIELDS = ("subagent_retry_at", "subagent_retry_round", "subagent_retry_stage",
          "subagent_retry_phase")
DELAYS = (30, 60, 120)


def _clear(node):
    for key in FIELDS:
        node.pop(key, None)


def transition(node, op, *, phase, kind="transient", has_wake_source=False, now=None):
    """在调用方持有的 baseline 锁内执行；now 注入供定向验证，延迟无随机量。"""
    now = now or datetime.now(timezone.utc)
    if node.get("subagent_retry_phase", phase) != phase:
        _clear(node)
    if op == "success":
        _clear(node)
        return 0, {"action": "cleared", "phase": phase}
    stage = node.get("subagent_retry_stage", "full")
    round_no = int(node.get("subagent_retry_round", 0))
    if stage not in ("full", "split", "inline", "exhausted") or round_no < 0:
        raise ValueError("invalid dispatch retry state")

    def outcome(code, action, **extra):
        return code, {"action": action, "phase": phase, "stage": stage,
                      "round": round_no, **extra}

    def exhausted():
        nonlocal stage
        stage = node["subagent_retry_stage"] = "exhausted"
        node["subagent_retry_phase"] = phase
        node.pop("subagent_retry_at", None)
        return outcome(20, "fail", reason="plan-transient")

    if op == "failure":
        node["subagent_retry_phase"] = phase
        if kind == "deterministic":
            return exhausted()
        if kind == "unavailable":
            stage = node["subagent_retry_stage"] = "inline"
            node.pop("subagent_retry_at", None)
            return outcome(12, "inline-budget")
        if stage in ("inline", "exhausted"):
            return exhausted()
        round_no += 1
        node["subagent_retry_round"] = round_no
        node["subagent_retry_stage"] = stage

    # 旧实现可能已经写到 >3，先检查上限，再读 retry_at，防远期旧闸门永久卡住。
    if stage == "exhausted":
        return exhausted()
    if stage == "inline":
        return outcome(12, "inline-budget")
    if round_no > len(DELAYS):
        if stage == "split":
            return exhausted()
        stage = node["subagent_retry_stage"] = "split"
        node["subagent_retry_phase"] = phase
        round_no = node["subagent_retry_round"] = 0
        node.pop("subagent_retry_at", None)
        return outcome(11, "split")

    if op == "failure":
        node["subagent_retry_at"] = (now + timedelta(seconds=DELAYS[round_no - 1])).isoformat()
    retry_at = node.get("subagent_retry_at")
    if retry_at:
        deadline = datetime.fromisoformat(str(retry_at).replace("Z", "+00:00"))
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        remaining = max(0, int((deadline - now).total_seconds() + 0.999999))
        if remaining:
            return outcome(10 if has_wake_source else 13,
                           "yield" if has_wake_source else "wait-inline",
                           retry_at=retry_at, retry_after_seconds=remaining)
    return outcome(11, "split") if stage == "split" else outcome(0, "dispatch")


def self_check():
    node = {}
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for stage in ("full", "split"):
        for delay in DELAYS:
            rc, out = transition(node, "failure", phase="3.1-plan", has_wake_source=True, now=now)
            assert (rc, out["retry_after_seconds"]) == (10, delay)
            rc, out = transition(node, "gate", phase="3.1-plan", now=now)
            assert (rc, out["action"]) == (13, "wait-inline")
            now += timedelta(seconds=delay)
        rc, _ = transition(node, "failure", phase="3.1-plan", now=now)
        assert rc == (11 if stage == "full" else 20)
    transition(node, "success", phase="3.1-plan", now=now)
    assert node == {}
    assert transition(node, "failure", phase="3.1-plan", kind="deterministic", now=now)[0] == 20
    print("dispatch_retry self-check: PASS")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("op", nargs="?", choices=("gate", "failure", "success"))
    parser.add_argument("--baseline", default="memory/.sprint-autopilot-baseline.json")
    parser.add_argument("--version")
    parser.add_argument("--phase")
    parser.add_argument("--kind", choices=("transient", "deterministic", "unavailable"))
    parser.add_argument("--has-wake-source", choices=("0", "1"), default="0")
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args(argv)
    if args.self_check:
        return self_check()
    if not args.op or not args.version or not args.phase:
        parser.error("op、--version、--phase 必填")
    if args.op == "failure" and args.kind is None:
        parser.error("failure 必须显式指定 --kind，不把未知错误默认为瞬态")
    try:
        with LockedBaseline(args.baseline, write=True) as baseline:
            node = baseline.data.setdefault("versions", {}).setdefault(args.version, {})
            rc, out = transition(node, args.op, phase=args.phase, kind=args.kind,
                                 has_wake_source=args.has_wake_source == "1")
    except (ValueError, TypeError, AttributeError, OSError) as exc:
        print(json.dumps({"action": "error", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(out, ensure_ascii=False))
    return rc


if __name__ == "__main__":
    sys.exit(main())
