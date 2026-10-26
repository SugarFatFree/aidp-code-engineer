#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""版本规划编排层回归：接入 SKILL「编排层调用协议」后的命令侧机器门。

· `aidp_run_metrics.py`：`[AIDP-STAGE]` 打点即时落盘、子 Agent 总 token、`规划耗时.md` 渲染；
· `--qr-level` 分级派发：只由 `/version` 传、四个子命令原样转给 SKILL 并校验移交清单；
· `check_version_audit_landed.py`：移交清单未结清即不通过（与 SKILL 真实写入格式对账）；
· `prd_presence_table.py`：表 D → PRD 行对账表，产物必须被 dev-manual-testcase 自己的硬门正确解析；
"""
import json
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path

import re
import importlib.util

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


SUBCMDS = {"sprint-requirements": "ux-logic-extractor", "sprint-design": "dev-logic-architect",
           "sprint-plan": "dev-execution-planner", "sprint-selftest": "dev-manual-testcase"}


def test_qr_level_dispatch_contract():
    print("\n[Q1] 分级派发：/version 传、子命令转给 SKILL 并校验移交清单")
    version = (REPO / ".aidp/commands/version.md").read_text(encoding="utf-8")
    planning3 = (REPO / ".aidp/flows/version/planning-3.md").read_text(encoding="utf-8")
    check("/version 参数表登记 --qr-level 且写明缺省 critical",
          re.search(r"^\| `--qr-level=scripts\\\|critical\\\|full` \|.*缺省 `critical`", version, re.M) is not None)
    calls = re.findall(r"执行：/sprint-(?:requirements|design|plan|selftest) \{version\}[^\n]*", planning3)
    check("规划链 8 处子命令调用（fresh + 补充）全部透传 --qr-level={qr_level}",
          len(calls) == 8 and all("--qr-level={qr_level}" in c for c in calls))
    check("planning-3 写明 {qr_level} 的取值（未传 = critical）", "**未传为 `critical`**" in planning3)
    for cmd, skill in SUBCMDS.items():
        body = (REPO / f".aidp/commands/{cmd}.md").read_text(encoding="utf-8")
        item = next((l for l in body.splitlines() if l.startswith("- `--qr-level=")), "")
        check(f"/{cmd} 登记 --qr-level：转给 {skill}、返回后 parse-handoff --expect-level",
              f"`{skill}`" in item and "parse-handoff" in item and "--expect-level" in item
              and "不带本 flag = 不传入参" in item)


def test_selftest_scale_control_wiring():
    print("\n[Q3] 研发自测规模控制：/version 拼入参、/sprint-selftest 原样转给 SKILL")
    planning3 = (REPO / ".aidp/flows/version/planning-3.md").read_text(encoding="utf-8")
    step = planning3[planning3.index("#### Step 2.4.3.5"):]
    calls = re.findall(r"执行：/sprint-selftest \{version\}[^\n]*", step)
    check("2.4.3.5 两处调用（fresh + 补充）都带 {selftest_args}",
          len(calls) == 2 and all("{selftest_args}" in c for c in calls))
    check("调用前先跑 prd_presence_table.py 生成对账表", "scripts/prd_presence_table.py --root . --version {version}" in step)
    check("L 档才加 --module-case-cap=30 --matrix-scope=p0", "档位 = L → 再加 `--module-case-cap=30 --matrix-scope=p0`" in step)
    selftest = (REPO / ".aidp/commands/sprint-selftest.md").read_text(encoding="utf-8")
    for flag in ("--prd-presence-table=", "--module-case-cap=", "--matrix-scope=", "--module-kind="):
        check(f"/sprint-selftest 登记 {flag}（只由 /version 传）",
              any(l.startswith(f"- `{flag}") and "/version" in l for l in selftest.splitlines()))
    check("命令端回检 check_case_stats 带同样参数", "--module-case-cap N` / `--prd-presence-table <路径>`" in selftest)


def _load_gate():
    spec = importlib.util.spec_from_file_location("audit_landed", SCRIPTS / "check_version_audit_landed.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_handoff_settlement_gate():
    print("\n[Q2] 审计落地门：移交清单未结清即不通过（与 SKILL 真实写入对账）")
    gate = _load_gate()
    ref = (REPO / ".aidp/reference/SKILL编排层接入.md").read_text(encoding="utf-8")
    ref_paths = re.findall(r"^\| `/sprint-[a-z]+` \| `[a-z-]+` \| `([^`]+)` \|", ref, re.M)
    check("落地门扫描的四个索引 == 参考文档第二节那张表",
          sorted(ref_paths) == sorted(p.replace("{v}", "{version}") for p in gate.HANDOFF_INDEXES))
    root = Path(tempfile.mkdtemp(prefix="aidp-handoff-gate-"))
    audit = root / "docs/audit/V1.0.0"
    audit.mkdir(parents=True)
    body = "".join(f"## {c} 项\nok\n" for c in "ABCDEFGH") + "overall: pass\n" + "说明。\n" * 80
    (audit / "version-output-audit-2026-10-26.md").write_text(body, encoding="utf-8")
    results = {}
    for cmd, skill in SUBCMDS.items():
        rel = next(p for p in gate.HANDOFF_INDEXES if p.startswith(
            {"sprint-requirements": "docs/requirements", "sprint-design": "docs/design",
             "sprint-plan": "docs/plans", "sprint-selftest": "docs/testing"}[cmd])).format(v="V1.0.0")
        idx = root / rel
        idx.parent.mkdir(parents=True, exist_ok=True)
        idx.write_text("# 索引\n\n正文\n", encoding="utf-8")
        qo = str(REPO / f".aidp/skills/{skill}/scripts/qr_orchestration.py")
        results[skill] = (qo, idx, _run(qo, "handoff", "--qr-level", "critical", "--write", str(idx)).returncode)
    check("四个 SKILL 用自己的协议工具写出移交清单（rc=0）", all(r[2] == 0 for r in results.values()))
    landed = gate.scan(root, "V1.0.0")
    check("四份清单全在 → 落地门不通过，逐份列出", not landed["ok"]
          and [f["kind"] for f in landed["findings"]] == ["qr-handoff-unsettled"]
          and len(landed["unsettled_handoffs"]) == 4)
    fast = gate.scan(root, "V1.0.0", fast=True)
    check("--fast → 放行但留痕「已延后」", fast["ok"]
          and [f["kind"] for f in fast["findings"]] == ["qr-handoff-deferred-by-fast"])
    for skill, (qo, idx, _) in list(results.items())[:3]:
        _run(qo, "handoff", "--qr-level", "full", "--write", str(idx))
    partial = gate.scan(root, "V1.0.0")
    check("清掉三份、还剩一份 → 仍不通过，且只报剩下那份", not partial["ok"]
          and [h["skill"] for h in partial["unsettled_handoffs"]] == ["dev-manual-testcase"])
    qo, idx, _ = results["dev-manual-testcase"]
    _run(qo, "handoff", "--qr-level", "full", "--write", str(idx))
    done = gate.scan(root, "V1.0.0")
    check("全部结清 → 通过且无 finding", done["ok"] and done["findings"] == [])
    shutil.rmtree(root, ignore_errors=True)


def test_prd_presence_table_roundtrip():
    print("\n[P1] PRD 行对账表：表 D 转换 → dev-manual-testcase 硬门读得懂")
    root = Path(tempfile.mkdtemp(prefix="aidp-prd-table-"))
    req = root / "docs/requirements/V1.0.0/研发需求"
    req.mkdir(parents=True)
    (req / "01_研发需求.md").write_text(
        "# 研发需求\n\n## 表 D：PRD 条目映射表\n\n| PRD 位置 | 条目内容 | 研发需求落点 | 处置 |\n| :- | :- | :- | :- |\n"
        "| `产品需求.md:12` 字段说明表 | 详情页展示「创建人」 | — |  |\n"
        "| `产品需求.md:120` 操作描述表 | 列表「导出」 | REQ-005 | 已承接 |\n"
        "| `产品需求.md:210` 迭代建议表 | 批量导出 | — | 本版不做 |\n", encoding="utf-8")
    cp = _run(str(SCRIPTS / "prd_presence_table.py"), "--root", str(root), "--version", "V1.0.0", "--json")
    result = json.loads(cp.stdout) if cp.returncode == 0 else {}
    table = Path(result.get("table_path", "/nonexistent"))
    check("生成对账表（rc=0，落在 docs/audit/{V}/，不进自测目录）",
          table.is_file() and table.parent == root / "docs/audit/V1.0.0")
    check("本版不做的条目不入表（否则下游会补「应该存在」的反向用例）",
          [r["id"] for r in result.get("excluded_not_this_version", [])] == ["产品需求.md:L210"]
          and "产品需求.md:L210 |" not in table.read_text(encoding="utf-8"))
    cases = root / "docs/testing/V1.0.0/研发自测"
    cases.mkdir(parents=True)
    stats = str(REPO / ".aidp/skills/dev-manual-testcase/scripts/check_case_stats.py")

    def presence(body):
        (cases / "02_全量自测用例.md").write_text(body, encoding="utf-8")
        out = _run(stats, str(cases), "--prd-presence-table", str(table), "--json")
        try:
            return json.loads(out.stdout).get("prd_presence", {})
        except ValueError:
            return {"error": out.stdout[:200] + out.stderr[:200]}
    miss = presence("# 用例\n\n### TC-001: 列表导出\n> **优先级**: P0 | **类型**: 正向\n")
    check("dmt 硬门解析出表：1 行未承接、且未被补用例覆盖",
          miss.get("unaccepted") == 1 and miss.get("uncovered_rows") == ["产品需求.md:L12"])
    hit = presence("# 用例\n\n### TC-002: [PRD存在性] 详情页展示创建人\n> **优先级**: P1 | **类型**: 正向\n"
                   "> **PRD 行号**: 产品需求.md:L12\n")
    check("补充用例按「PRD 行号」引用带文件名的键 → dmt 判已覆盖", hit.get("uncovered_rows") == [] and hit.get("covered") == 1)
    near = presence("# 用例\n\n### TC-003: [PRD存在性] 其它\n> **PRD 行号**: 产品需求.md:L120\n")
    check("L120 不会被当成 L12（行号独立成词）", near.get("uncovered_rows") == ["产品需求.md:L12"])
    shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    test_run_metrics_stage_and_render()
    test_prd_presence_table_roundtrip()
    test_qr_level_dispatch_contract()
    test_selftest_scale_control_wiring()
    test_handoff_settlement_gate()
    print(f"\n══ 结果：{_passed} passed / {_failed} failed ══")
    sys.exit(1 if _failed else 0)
