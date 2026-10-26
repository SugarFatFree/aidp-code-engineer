#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""版本规划编排层回归：接入 SKILL「编排层调用协议」后的命令侧机器门。

· `aidp_run_metrics.py`：`[AIDP-STAGE]` 打点即时落盘、子 Agent 总 token、`规划耗时.md` 渲染；
"""
import json
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SCRIPTS = REPO / ".aidp" / "scripts"
METRICS = str(SCRIPTS / "aidp_run_metrics.py")

_passed = _failed = 0


def check(name, cond):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ✅ {name}")
    else:
        _failed += 1
        print(f"  ❌ FAIL: {name}")


def _run(*args, cwd=None):
    return subprocess.run([sys.executable, *args], capture_output=True, text=True, cwd=cwd)


def _stage(skill, stage, event, rnd=0, status=None, shard=None):
    mark = {"skill": skill, "stage": stage, "shard": shard, "round": rnd, "event": event, "status": status}
    return "[AIDP-STAGE] " + json.dumps(mark, ensure_ascii=False, separators=(",", ":"))


def test_run_metrics_stage_and_render():
    print("\n[M1] 规划计量：打点即时落盘 + 规划耗时.md")
    root = Path(tempfile.mkdtemp(prefix="aidp-metrics-"))
    m = [METRICS, "--root", str(root), "--version", "V1.0.0", "--run-id", "r1"]
    _run(*m, "start", "--phase", "selftest", "--at", "2026-10-26T01:00:00+00:00")
    rc1 = _run(*m, "stage", "--line", _stage("dev-manual-testcase", "generate", "start", shard="迁移工具"),
               "--at", "2026-10-26T01:01:00+00:00").returncode
    rc2 = _run(*m, "stage", "--line", _stage("dev-manual-testcase", "generate", "end", status="pass", shard="迁移工具"),
               "--at", "2026-10-26T01:53:00+00:00").returncode
    _run(*m, "stage", "--line", _stage("dev-manual-testcase", "qr", "start", rnd=1), "--at", "2026-10-26T01:54:00+00:00")
    _run(*m, "stage", "--line", _stage("dev-manual-testcase", "qr", "end", rnd=1, status="fail"),
         "--at", "2026-10-26T02:04:00+00:00")
    _run(*m, "end", "--phase", "selftest", "--source", "agent-result", "--total-tokens", "250000",
         "--tool-calls", "120", "--at", "2026-10-26T02:10:00+00:00")
    check("合法打点行落盘成功（start / end 各 rc=0）", rc1 == 0 and rc2 == 0)
    data = json.loads((root / "docs/audit/V1.0.0/metrics-r1.json").read_text(encoding="utf-8"))
    by = {(p["phase"], p["retry_round"]): p for p in data["phases"]}
    gen = by.get(("dev-manual-testcase:generate@迁移工具", 0))
    check("分片生成阶段按 skill:stage@shard 记账", gen is not None and gen["status"] == "pass")
    check("QR 轮次落 retry_round、end 的 status 原样记录",
          by.get(("dev-manual-testcase:qr", 1), {}).get("status") == "fail")
    check("打点阶段来源标为 stage-marker", gen is not None and gen.get("source") == "stage-marker")
    check("子 Agent 总 token 如实记录（不拆分估算）", by[("selftest", 0)].get("total_tokens") == 250000
          and by[("selftest", 0)].get("input_tokens") is None)

    bad = _run(*m, "stage", "--line", '[AIDP-STAGE] {"skill":"x","event":"start"}')
    check("字段不全的打点行 → rc=2（⛔ 不静默吞掉）", bad.returncode == 2)
    orphan = _run(*m, "stage", "--line", _stage("dev-manual-testcase", "fix", "end", rnd=1, status="pass"))
    check("没有 start 的 end → rc=2", orphan.returncode == 2)
    start_with_status = _run(*m, "stage", "--line", _stage("ux-logic-extractor", "qr", "end", rnd=1, status=None))
    check("end 缺 status → rc=2", start_with_status.returncode == 2)

    cp = _run(*m, "render")
    md = (root / "docs/audit/V1.0.0/规划耗时.md")
    text = md.read_text(encoding="utf-8") if md.is_file() else ""
    check("render 写出 规划耗时.md", cp.returncode == 0 and md.is_file())
    inner = text.split("最慢的 5 个 SKILL 内部阶段")[-1].split("## ")[0]
    check("内部阶段榜首是 52 分钟的分片生成（3120s），QR 轮排其后",
          inner.split("\n")[4].startswith("| dev-manual-testcase:generate@迁移工具 | 0 | 3120.0 |")
          and inner.split("\n")[5].startswith("| dev-manual-testcase:qr | 1 | 600.0 | fail |"))
    check("顶层阶段表不混入 SKILL 内部打点", "dev-manual-testcase" not in text.split("## 顶层阶段")[1].split("## ")[0])
    check("合计只算顶层阶段（SKILL 打点不重复计入）", "顶层阶段墙钟合计：4200.0 s" in text)
    sel = next(l for l in text.split("全部阶段")[1].splitlines() if l.startswith("| selftest |"))
    check("顶层阶段记了真实总 token，未取到的入/出拆分显示「—」", "| 250000 | — |" in sel)
    shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    test_run_metrics_stage_and_render()
    print(f"\n══ 结果：{_passed} passed / {_failed} failed ══")
    sys.exit(1 if _failed else 0)
