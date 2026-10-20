#!/usr/bin/env python3
"""测试阶段入口/出口：独立游标、同 tick 幂等、真实进度和 stuck 熔断。"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

from check_stuck_phase import baseline_file

HERE = Path(__file__).resolve().parent
BASELINE = HERE / "baseline_edit.py"
STUCK = HERE / "check_stuck_phase.py"
PHASES = ("1-probe", "2-exec", "3-audit", "done")


def progress_token(root, version, build):
    """用最新轮次和已落盘的终态任务表达推进，不把 mtime/日志刷新当成进度。"""
    directory = root / "docs/reports" / version / "AI测试报告" / ("build-" + build)
    rounds = [p for p in directory.glob("round-*") if p.name[6:].isdigit() and p.is_dir()]
    if not rounds:
        return build
    latest = max(rounds, key=lambda p: int(p.name[6:]))
    path = latest / "tasks.md"
    rows = []
    if path.exists():
        parser_path = HERE.parent / "skills/auto-test-runner/scripts/tasks_state.py"
        spec = importlib.util.spec_from_file_location("_aidp_tasks_progress", parser_path)
        parser = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(parser)
        for line in path.read_text(encoding="utf-8").splitlines():
            item = parser.ITEM_RE.match(line)
            if item and item[1] in ("√", "x", "!"):
                rows.append((item[2], parser.MARK_STATE[item[1]]))
    digest = hashlib.sha256(json.dumps(sorted(rows)).encode()).hexdigest()[:16]
    return build + "|" + latest.name + ":" + digest


def _call(cmd, root):
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(root), timeout=120)
    if result.stdout:
        print(result.stdout, end="", file=sys.stderr)
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    return result.returncode


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--version", required=True)
    ap.add_argument("--phase", required=True, choices=PHASES[:-1])
    ap.add_argument("--next-phase", required=True, choices=PHASES)
    ap.add_argument("--build", default="standalone")
    ap.add_argument("--summary", default="")
    ap.add_argument("--baseline", default=None)
    ap.add_argument("--tick-id", default="")
    ap.add_argument("--complete", action="store_true", help="产物核验成功后写完成态并推进游标")
    ap.add_argument("--no-card", action="store_true", help="仅隔离演练不发通知")
    args = ap.parse_args(argv)
    bp = baseline_file(args.baseline)
    root = bp.parent.parent if bp.parent.name == "memory" else bp.parent
    try:
        data = json.loads(bp.read_text(encoding="utf-8"))
        node = (data.get("versions") or {}).get(args.version) or {}
        old = node.get("aiauto_run_state") or {}
        if not isinstance(old, dict):
            raise ValueError("aiauto_run_state 必须是对象")
        token = progress_token(root, args.version, args.build)
        tick_id = args.tick_id or (data.get("aiauto") or {}).get("tick_id") \
            or (data.get("aiauto") or {}).get("tick_started_at") or ""
        prefix = ["--baseline", str(bp), "--version", args.version]

        def guard(phase):
            cmd = [sys.executable, str(STUCK), *prefix, "--command", "aiauto-test",
                   "--phase", phase, "--state-key", "aiauto_run_state", "--freeze"]
            if args.no_card:
                cmd.append("--no-card")
            return _call(cmd, root)

        active = old.get("current_phase")
        same_build = str(old.get("phase_token") or args.build).split("|", 1)[0] == args.build
        running = old.get("phase_status", "running") == "running" and active in PHASES[:-1] and same_build
        skip = False
        if not args.complete and same_build and old.get("phase_status") == "complete":
            following = old.get("next_phase")
            if following in PHASES[:-1] and PHASES.index(args.phase) < PHASES.index(following):
                print(json.dumps({"ok": True, "skip_phase": True, "resume_phase": following,
                                  "complete": False, "next_phase": following}, ensure_ascii=False))
                return 0
            if following in PHASES[:-1] and PHASES.index(args.phase) > PHASES.index(following):
                raise ValueError("必须先执行游标指定的阶段 %s" % following)
        if args.complete:
            if not running or active != args.phase:
                raise ValueError("不能完成一个未进入或不属于本 build 的阶段")
            current = args.phase
        else:
            current = args.phase
            if running:
                # 先查旧阶段再改游标；重新从 P1 开 tick 不能抹掉卡住的 P2。
                # 已有真实终态任务推进时允许重置停滞计数。
                if old.get("phase_token") == token:
                    rc = guard(active)
                    if rc:
                        return rc
                if PHASES.index(args.phase) > PHASES.index(active):
                    raise ValueError("前一阶段 %s 尚未完成，禁止跳到 %s" % (active, args.phase))
                if PHASES.index(args.phase) < PHASES.index(active):
                    current, skip = active, True
        next_phase = args.next_phase if current == args.phase else old.get("next_phase", current)
        state = [sys.executable, str(BASELINE), *prefix, "--state-key", "aiauto_run_state",
                 "--phase-token", token, "--tick-id", str(tick_id)]
        if not args.complete:
            state.append("--enter")
        summary = args.summary or ("测试阶段结果已落盘" if args.complete else "测试阶段执行中")
        state += ["run-state", current, next_phase, "done", "--summary", summary, "--pending", ""]
        rc = _call(state, root)
        if rc:
            return rc
        if not args.complete:
            rc = guard(current)
            if rc:
                return rc
        print(json.dumps({"ok": True, "skip_phase": skip, "resume_phase": current,
                          "complete": args.complete, "next_phase": next_phase}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError, subprocess.TimeoutExpired) as exc:
        print("⛔ 测试阶段状态写入/核验失败：%s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
