#!/usr/bin/env python3
"""测试链路 Phase 入口：写入独立 aiauto_run_state 并执行 stuck 熔断。"""
import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASELINE = HERE / "baseline_edit.py"
STUCK = HERE / "check_stuck_phase.py"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--version", required=True)
    ap.add_argument("--phase", required=True)
    ap.add_argument("--next-phase", required=True)
    ap.add_argument("--build", default="standalone")
    ap.add_argument("--summary", default="测试链路 Phase 执行中")
    ap.add_argument("--baseline", default=None)
    args = ap.parse_args(argv)
    prefix = ["--baseline", args.baseline] if args.baseline else []
    state = [sys.executable, str(BASELINE), *prefix, "--version", args.version,
             "--state-key", "aiauto_run_state", "--enter", "--phase-token", args.build,
             "run-state", args.phase, args.next_phase, "done", "--summary", args.summary, "--pending", ""]
    r = subprocess.run(state)
    if r.returncode:
        return r.returncode
    stuck = [sys.executable, str(STUCK), *prefix, "--command", "aiauto-test",
             "--version", args.version, "--phase", args.phase,
             "--state-key", "aiauto_run_state", "--freeze"]
    return subprocess.run(stuck).returncode


if __name__ == "__main__":
    raise SystemExit(main())
