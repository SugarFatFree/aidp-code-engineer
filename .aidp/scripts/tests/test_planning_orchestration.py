#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""版本规划编排层回归：接入 SKILL「编排层调用协议」后的命令侧机器门。

· `aidp_run_metrics.py`：`[AIDP-STAGE]` 打点即时落盘、子 Agent 总 token、`规划耗时.md` 渲染；
· `--qr-level` 分级派发：继承父授权计算有效档位，四个子命令始终传给 SKILL 并按同档位校验移交；
· `check_version_audit_landed.py`：移交清单未结清即不通过（与 SKILL 真实写入格式对账）；
· `prd_presence_table.py`：表 D → PRD 行对账表，产物必须被 dev-manual-testcase 自己的硬门正确解析；
· `--fast`：移交审计延后、清单即痕迹，发布 Step 3.1 机器判未结清并补跑；
· 计划 ‖ 自测并行：执行 planning-3 的回填 bash（planner 导出映射 → dmt 回填占位符），全有或全无；
· Critical 不出「有人审」的集合：独立解析 checklist 等级列 ↔ SKILL 推导、篡改清单必被拒、--fast 不豁免八项审计。
  （⚠️ 语义检出能力是大模型判断、无法确定性回归；这里守的是更底层的保证：没有 Critical 维度被裁掉。）
"""
import json
import os
import shlex
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
    print("\n[Q1] 分级派发：父授权决定有效档位、四入口显式传递并校验移交")
    version = (REPO / ".aidp/commands/version.md").read_text(encoding="utf-8")
    planning3 = (REPO / ".aidp/flows/version/planning-3.md").read_text(encoding="utf-8")
    recipe = (REPO / ".aidp/reference/SKILL编排层接入.md").read_text(encoding="utf-8")
    fences = re.findall(r"```bash\n(.*?)\n\s*```", recipe, re.S)
    policy_fence = next((block for block in fences if 'REQUESTED_QR_LEVEL=' in block), None)
    handoff_fence = next((block for block in fences if '$QO parse-handoff' in block), None)
    check("/version 参数表登记 --qr-level 且写明缺省 critical",
          re.search(r"^\| `--qr-level=scripts\\\|critical\\\|full` \|.*缺省 `critical`", version, re.M) is not None)
    calls = re.findall(r"执行：/sprint-(?:requirements|design|plan|selftest) \{version\}[^\n]*", planning3)
    check("规划链 8 处子命令调用（fresh + 补充）透传档位及父上下文",
          len(calls) == 8 and all('--qr-level={qr_level}' in call and
                                  '--execution-context "$EXECUTION_CONTEXT"' in call for call in calls))
    selection = next((line for line in planning3.splitlines() if '{qr_level}' in line), '')
    check("planning-3 保留显式档位，未显式时 critical，仍按父授权使用",
          all(part in selection for part in ('version', 'critical', '父授权', '继承'))
          and re.search(r'未显式|未传', selection) is not None)
    for cmd, skill in SUBCMDS.items():
        body = (REPO / f".aidp/commands/{cmd}.md").read_text(encoding="utf-8")
        item = next((line for line in body.splitlines() if line.startswith('- `--qr-level=')), '')
        check(f"/{cmd} 显式传有效档位给 {skill}，parse-handoff 校验相同档位",
              f'`{skill}`' in item and all(part in item for part in (
                  '父授权', '无docs-audit取scripts', '始终', 'parse-handoff', 'expect-level保持一致',
                  'reference/SKILL编排层接入.md'))
              and handoff_fence is not None and '--expect-level <档位>' in handoff_fence)
    check("共用父授权与移交校验围栏可提取", bool(policy_fence and handoff_fence))
    if not policy_fence or not handoff_fence:
        return
    sys.path.insert(0, str(SCRIPTS))
    import entry_context
    policy_script = policy_fence.replace('{{AIDP_HOME}}', str(REPO / '.aidp'))
    cases = (
        ('入口名称不自授 document', 'sprint-plan', False, (), 'full', None),
        ('仅 document 缺省使用 scripts', 'sprint-plan', True, (), '', 'scripts'),
        ('仅 document 不能借 full flag 扩权', 'sprint-plan', True, (), 'full', 'scripts'),
        ('公开 version 缺省 critical', 'version', True, (), '', 'critical'),
        ('公开 version 保留显式 scripts', 'version', True, (), 'scripts', 'scripts'),
        ('公开 version 保留显式 critical', 'version', True, (), 'critical', 'critical'),
        ('公开 version 保留显式 full', 'version', True, (), 'full', 'full'),
        ('version fast 缺省仍为 critical', 'version', True, ('--fast',), '', 'critical'),
        ('version fast 不覆盖显式 full', 'version', True, ('--fast',), 'full', 'full'),
        ('不允许 none 档关闭最低自检', 'version', True, (), 'none', None),
    )
    with tempfile.TemporaryDirectory(prefix='aidp-qr-parent-policy-') as directory:
        root = Path(directory)
        for index, (label, entry, explicit, options, requested, expected) in enumerate(cases):
            source = ({'kind': 'explicit-command', 'request_id': f'qr-policy-{index}',
                       'command': entry, 'options': list(options)} if explicit else None)
            context = entry_context.resolve_context(root, entry, version='V1.0.0',
                                                     authorization_source=source)['execution_context']
            result = subprocess.run(['bash', '-e', '-c', policy_script], cwd=root, capture_output=True, text=True,
                                    env={**os.environ, 'EXECUTION_CONTEXT': context, 'REQUESTED_QR_LEVEL': requested})
            levels = re.findall(r'^qr_level=(\w+)$', result.stdout, re.M)
            check(label, result.returncode == 0 and levels == [expected] if expected is not None
                  else result.returncode != 0 and not levels)
        for command, skill in SUBCMDS.items():
            index = root / command / '00_索引.md'
            index.parent.mkdir(parents=True)
            index.write_text('# 夹具索引\n', encoding='utf-8')
            qo = str(REPO / '.aidp/skills' / skill / 'scripts/qr_orchestration.py')
            generated = _run(qo, 'handoff', '--qr-level', 'scripts', '--write', str(index))
            script = handoff_fence.replace('{{AIDP_HOME}}', str(REPO / '.aidp')).replace('<SKILL>', skill) \
                .replace('<上表的 00_索引.md>', shlex.quote(str(index))).replace('<档位>', 'scripts')
            matching = subprocess.run(['bash', '-e', '-c', script], cwd=root, capture_output=True, text=True)
            mismatched = subprocess.run(['bash', '-e', '-c', script.replace('--expect-level scripts', '--expect-level full')],
                                        cwd=root, capture_output=True, text=True)
            check(f"{command} 真实 scripts 移交按同档通过，冒充 full 被拒",
                  generated.returncode == 0 and matching.returncode == 0 and mismatched.returncode != 0)


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
    table_before = table.read_bytes()
    again = _run(str(SCRIPTS / "prd_presence_table.py"), "--root", str(root), "--version", "V1.0.0", "--json")
    check("同输入重导出 PRD 对账表字节不变，不制造指纹失效", again.returncode == 0 and table.read_bytes() == table_before)
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


def test_fast_mode_release_gate():
    print("\n[F1] --fast：移交审计延后，发布前机器判未结清")
    version = (REPO / ".aidp/commands/version.md").read_text(encoding="utf-8")
    row = next((l for l in version.splitlines() if l.startswith("| `--fast` |")), "")
    check("/version 登记 --fast：取 critical、不派移交审计、发布前须结清",
          "`critical`" in row and "不派" in row and "发布" in row)
    p3 = (REPO / ".aidp/flows/version/planning-3.md").read_text(encoding="utf-8")
    p7 = (REPO / ".aidp/flows/version/planning-7.md").read_text(encoding="utf-8")
    p8 = (REPO / ".aidp/flows/version/planning-8.md").read_text(encoding="utf-8")
    qr_selection = next((line for line in p3.splitlines() if '{qr_level}' in line), '')
    check("规划链：fast 只在未显式指定时取 critical，任何档位加 --matrix-scope=p0",
          '未显式给出' in row and all(part in qr_selection for part in ('显式', '继承', 'critical', '父授权'))
          and re.search(r'未显式|未传', qr_selection) is not None
          and "带了 `--fast` → 任何档位都加 `--matrix-scope=p0`" in p3)
    check("Step 2.4.7：--fast 不派移交审计；Step 2.5.0 带 --fast 且认 deferred 留痕",
          "`--fast` 不派、清单保留" in p7 and "--fast" in p8 and "qr-handoff-deferred-by-fast" in p8)
    rel = (REPO / ".aidp/flows/version/release-1.md").read_text(encoding="utf-8")
    fence = re.search(r"  ```bash\n(  UNSETTLED=\$\(python3 \{\{AIDP_HOME\}\}/scripts/check_version_audit_landed\.py.*?)\n  ```", rel, re.S)
    check("发布 Step 3.1 有机器判的结清检查", fence is not None)
    if not fence:
        return
    script = "\n".join(l[2:] if l.startswith("  ") else l for l in fence.group(1).splitlines())
    script = script.replace("{{AIDP_HOME}}", str(REPO / ".aidp")).replace("{version}", "V1.0.0")
    root = Path(tempfile.mkdtemp(prefix="aidp-fast-release-"))
    idx = root / "docs/plans/V1.0.0/00_索引.md"
    idx.parent.mkdir(parents=True)
    idx.write_text("# 索引\n", encoding="utf-8")
    qo = str(REPO / ".aidp/skills/dev-execution-planner/scripts/qr_orchestration.py")
    _run(qo, "handoff", "--qr-level", "critical", "--write", str(idx))
    left = subprocess.run(["bash", "-c", script], cwd=root, capture_output=True, text=True)
    check("清单在 → 数出 1 份未结清", "未结清：1 份" in left.stdout)
    _run(qo, "handoff", "--qr-level", "full", "--write", str(idx))
    done = subprocess.run(["bash", "-c", script], cwd=root, capture_output=True, text=True)
    check("结清后 → 0 份", "未结清：0 份" in done.stdout)
    shutil.rmtree(root, ignore_errors=True)


PLANNING_SKILLS = ("ux-logic-extractor", "dev-logic-architect", "dev-execution-planner", "dev-manual-testcase")


def _checklist_levels(skill):
    """独立解析 checklist「维度成本与裁剪索引表」的等级列（⛔ 不复用 SKILL 脚本——要的就是交叉验证）。"""
    text = (REPO / f".aidp/skills/{skill}/references/quality-review-checklist.md").read_text(encoding="utf-8")
    lines = text.splitlines()
    for i, line in enumerate(lines):
        head = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.startswith("| #") and "等级" in head:
            levels = {}
            for row in lines[i + 2:]:
                if not row.startswith("|"):
                    break
                cells = [c.strip() for c in row.strip().strip("|").split("|")]
                num = re.match(r"\d+", cells[0])
                if num and len(cells) == len(head):
                    levels[f"QR-{int(num.group()):02d}"] = cells[head.index("等级")]
            return levels
    return {}


def test_critical_never_deferred():
    print("\n[C1] Critical 不出「有人审」的集合")
    for skill in PLANNING_SKILLS:
        levels = _checklist_levels(skill)
        critical = {k for k, v in levels.items() if v == "Critical"}
        qo = str(REPO / f".aidp/skills/{skill}/scripts/qr_orchestration.py")
        for tier in ("critical", "scripts"):
            plan = json.loads(_run(qo, "plan", "--qr-level", tier).stdout or "{}")
            deferred = {d["id"] if isinstance(d, dict) else d for d in plan.get("deferred_dims", [])}
            kept = {d["id"] if isinstance(d, dict) else d for d in plan.get("semantic_dims", []) + plan.get("escalated_dims", [])}
            check(f"{skill} · {tier}：{len(critical)} 个 Critical 全部仍在 SKILL 内审、无一移交",
                  bool(critical) and not (critical & deferred) and critical <= kept)
    root = Path(tempfile.mkdtemp(prefix="aidp-critical-"))
    idx = root / "00_索引.md"
    qo = str(REPO / ".aidp/skills/dev-manual-testcase/scripts/qr_orchestration.py")
    critical = sorted(k for k, v in _checklist_levels("dev-manual-testcase").items() if v == "Critical")

    def tamper(fn):
        idx.write_text("# 索引\n", encoding="utf-8")
        _run(qo, "handoff", "--qr-level", "critical", "--write", str(idx))
        text = idx.read_text(encoding="utf-8")
        line = next(l for l in text.splitlines() if l.startswith("<!-- AIDP-QR-HANDOFF: "))
        block = json.loads(line[len("<!-- AIDP-QR-HANDOFF: "):-len(" -->")])
        fn(block)
        idx.write_text(text.replace(line, "<!-- AIDP-QR-HANDOFF: " + json.dumps(block, ensure_ascii=False) + " -->"),
                       encoding="utf-8")
        return _run(qo, "parse-handoff", str(idx), "--expect-level", "critical").returncode
    check("篡改：把 Critical 维度塞进移交清单 → parse-handoff 拒绝（rc=1）",
          tamper(lambda b: b["deferred_dims"].append({"id": critical[0], "name": "x", "level": "Critical",
                                                      "script_coverage": "否", "delta_tier": "Δ"})) == 1)
    check("篡改：少登记一个移交维度 → 拒绝（rc=1）", tamper(lambda b: b["deferred_dims"].pop()) == 1)
    check("篡改：把移交维度的等级改成 Minor → 拒绝（rc=1）",
          tamper(lambda b: b["deferred_dims"][0].update(level="Minor")) == 1)
    check("阴性对照：原样不动 → 通过（rc=0）", tamper(lambda b: None) == 0)
    shutil.rmtree(root, ignore_errors=True)
    gate = _load_gate()
    root = Path(tempfile.mkdtemp(prefix="aidp-fast-noreport-"))
    (root / "docs/requirements/V1.0.0").mkdir(parents=True)
    (root / "docs/requirements/V1.0.0/01_研发需求.md").write_text("# 需求\n", encoding="utf-8")
    fast = gate.scan(root, "V1.0.0", fast=True)
    check("--fast 不豁免八项审计：没有 version-auditor 报告照样不通过",
          not fast["ok"] and [f["kind"] for f in fast["findings"]] == ["audit-report-missing"])
    shutil.rmtree(root, ignore_errors=True)
    auditor = (REPO / ".aidp/agents/version-auditor.md").read_text(encoding="utf-8")
    check("version-auditor 的 Critical 硬门 C-4 / C-5 / F / G 声明仍在",
          all(k in auditor for k in ("Step C-4：", "Step C-5：", "### F. 原型覆盖度审计", "### G. 语义变更派生完整性审计"))
          and auditor.count("Critical 硬门") >= 4)
    check("version-auditor 独立读取 PRD 原文，不能仅信表D或对账表",
          "docs/requirements/{version}/产品提供/**/*.md   → PRD 原始来源" in auditor
          and "不能仅信 PRD 行对账表或表 D" in auditor
          and "每次读 `产品提供/**/*.md` 原始全集" in auditor)


def test_parallel_plan_selftest_backfill():
    print("\n[R1] 计划 ‖ 自测并行：回填 bash 实跑（planner 导出 → dmt 回填）")
    p3 = (REPO / ".aidp/flows/version/planning-3.md").read_text(encoding="utf-8")
    check("fresh 模式同一条消息派两个子 Agent，自测侧另加 --plan-ref-mode=deferred",
          "**同一条消息**派两个子 Agent" in p3 and "另加 `--plan-ref-mode=deferred`" in p3)
    check("不支持并行子 Agent 时串行且不加 --plan-ref-mode", "串行，且**不加** `--plan-ref-mode`" in p3)
    selftest = (REPO / ".aidp/commands/sprint-selftest.md").read_text(encoding="utf-8")
    check("/sprint-selftest：deferred 时跳过「执行计划必须存在」、回检传 --plan-ref-mode deferred",
          "带 `--plan-ref-mode=deferred` 时**本项跳过**" in selftest
          and "`check_suite_upstream.py` 传 `--plan-ref-mode deferred`" in selftest)
    fence = re.search(r"   ```bash\n(   T_DIR=.*?)\n   ```", p3, re.S)
    check("planning-3 有回填 bash 围栏", fence is not None)
    if not fence:
        return
    script = "\n".join(l[3:] for l in fence.group(1).splitlines())
    script = script.replace("{{AIDP_HOME}}", str(REPO / ".aidp")).replace("{version}", "V1.0.0")

    def run_case(reqs, strip_anchors=False, empty_plan=False, nested_reqs=None):
        root = Path(tempfile.mkdtemp(prefix="aidp-plan-refs-"))
        plans = root / "docs/plans/V1.0.0"
        plans.mkdir(parents=True)
        plan = (REPO / ".aidp/skills/dev-execution-planner/references/iteration-plan-sample.md").read_text(encoding="utf-8")
        if strip_anchors:   # 整份无锚点 = 脚本判 Important，但仍 exit 1、不写映射
            plan = re.sub(r'(?m)^<a id="task-\d+-\d+"></a>\n', "", plan)
        if empty_plan:
            plan = "# 执行计划\n\n尚无任务。\n"
        (plans / "01_研发执行计划.md").write_text(plan, encoding="utf-8")
        (root / "memory/V1.0.0").mkdir(parents=True)
        # 旧映射不能在 export skipped 时被继续消费。
        (root / "memory/V1.0.0/.plan-refs.json").write_text(
            '{"REQ-101":{"label":"Sprint-001 Task 1.1","href":"old.md#task-1-1"}}', encoding="utf-8")
        cases = root / "docs/testing/V1.0.0/研发自测"
        cases.mkdir(parents=True)
        sources = ("> **自测方案章节:** [范围](01_研发自测方案.md#范围)\n"
                   "> **PRD 来源:** [REQ-101 下单](../../../requirements/V1.0.0/研发需求/01_研发需求.md#REQ-101)\n"
                   "> **详细设计来源:** [下单设计](../../../design/detail/V1.0.0/01_详细设计.md#下单)\n")
        body = "# 用例\n\n## 套件 SUITE-001: 下单\n" + sources + "> **研发执行计划来源**: " + "、".join(f"⟨PLAN-REF:{r}⟩" for r in reqs) + "\n"
        (cases / "02_全量自测用例.md").write_text(body, encoding="utf-8")
        nested = cases / "模块/子模块/03_模块用例.md"
        if nested_reqs is not None:
            nested.parent.mkdir(parents=True)
            nested_sources = sources.replace("](", "](../../")
            nested.write_text("# 模块用例\n\n## 套件 SUITE-002: 导出\n" + nested_sources + "> **研发执行计划来源**: "
                              + "、".join(f"⟨PLAN-REF:{req}⟩" for req in nested_reqs) + "\n", encoding="utf-8")
        # 正式流程先分别保存两个生成结果，围栏只驱动其后三个持久阶段。
        state_cli = [str(SCRIPTS / "planning_state.py"), "--root", str(root), "--version", "V1.0.0"]
        (root / "inputs.md").write_text("REQ-101 REQ-104", encoding="utf-8")
        (root / "generated.json").write_text('{"status":"pass","exit_code":0}', encoding="utf-8")
        for stage, outputs in (("plan", [plans / "01_研发执行计划.md"]),
                               ("case", [cases / "02_全量自测用例.md"] + ([nested] if nested_reqs is not None else []))):
            arguments = ["start", stage, "--input", "inputs.md"]
            for output in outputs:
                arguments.extend(["--output", output.relative_to(root).as_posix()])
            _run(*state_cli, *arguments)
            _run(*state_cli, "finish", stage, "--result", "generated.json")
        out = subprocess.run(["bash", "-c", script], cwd=root, capture_output=True, text=True)
        results = root / "memory/V1.0.0/.planning-results"
        codes = []
        for step in ("map", "ref", "verify"):
            result_file = results / f"{step}.json"
            data = json.loads(result_file.read_text()) if result_file.exists() else {}
            code = data.get("exit_code", "-")
            if step == "map" and code == 0 and not (root / "memory/V1.0.0/.plan-refs.json").is_file():
                code = "skipped"
            codes.append(code)
        observed = f"export={codes[0]} resolve={codes[1]} upstream={codes[2]}"
        text = (cases / "02_全量自测用例.md").read_text(encoding="utf-8")
        if nested_reqs is not None:
            text += "\n" + nested.read_text(encoding="utf-8")
        shutil.rmtree(root, ignore_errors=True)
        return observed, text
    out, text = run_case(["REQ-101", "REQ-104"])
    check("真实计划样例 → export=0 且 resolve=0", "export=0 resolve=0" in out)
    check("占位符回填为 Sprint + Task 锚点链接（Sprint 号最小、其次 Task 号最小）",
          "⟨PLAN-REF" not in text and "[Sprint-001 Task 4.1](../../../plans/V1.0.0/01_研发执行计划.md#task-4-1)" in text
          and "[Sprint-001 Task 2.2](" in text)
    out, text = run_case(["REQ-101"], nested_reqs=["REQ-104"])
    check("同一用例根一次回填：嵌套两层的链接重算相对路径且保留锚点",
          "export=0 resolve=0 upstream=0" in out and "⟨PLAN-REF" not in text
          and "[Sprint-001 Task 4.1](../../../plans/V1.0.0/01_研发执行计划.md#task-4-1)" in text
          and "[Sprint-001 Task 2.2](../../../../../plans/V1.0.0/01_研发执行计划.md#task-2-2)" in text)
    out, text = run_case(["REQ-101"], nested_reqs=["REQ-999"])
    check("嵌套用例缺映射时根目录与子目录都不改", "export=0" in out and "resolve=0" not in out
          and text.count("⟨PLAN-REF:") == 2)
    out, text = run_case(["REQ-101", "REQ-999"])
    check("计划里没有 Task 承接的 REQ → resolve 拒绝（≠0）", "export=0" in out and "resolve=0" not in out)
    check("全有或全无：拒绝时一个占位符都不改", text.count("⟨PLAN-REF:") == 2)
    out, text = run_case(["REQ-101"], strip_anchors=True)
    check("计划整份无锚点（仅 Important）→ export≠0，后两步标「-」未跑", "export=1 resolve=- upstream=-" in out
          and text.count("⟨PLAN-REF:") == 1)
    check("处置段点明 fresh 模式下 Important 同样必修", "**同样必修**" in p3)
    out, text = run_case(["REQ-101"], empty_plan=True)
    check("export skipped → 不消费旧映射、不误派 selftest 修复", "export=skipped resolve=- upstream=-" in out
          and text.count("⟨PLAN-REF:") == 1)


def test_sprint_start_gate_scope():
    """开工门不拦未来任务；交付门仍检查全部计划，已启动未归档仍阻断。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("open_sprints_test", REPO / ".aidp/scripts/check_open_sprints.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory(prefix="aidp-start-gate-") as directory:
        root = Path(directory)
        plans = root / "docs/plans/V1.0.0"
        plans.mkdir(parents=True)
        (plans / "01_研发执行计划.md").write_text("- Sprint-001 登录\n- Sprint-002 导出\n", encoding="utf-8")
        check("交付门默认仍拦全部未关闭计划", not module.scan(root, "V1.0.0")["ok"])
        try:
            first = module.scan(root, "V1.0.0", scope="started")
        except TypeError:
            check("开工门支持 started 范围（fresh 计划可开工）", False)
            return
        check("fresh 两个未来 Sprint 不阻止首开", first["ok"] and not first["open"])
        module.record_start(root, "V1.0.0", "alice", "001")
        check("显式启动记录使未归档 Sprint 阻断下一轮", module.scan(root, "V1.0.0", scope="started")["open"] == ["Sprint-001"])
        memory = root / "memory/V1.0.0/alice"
        (memory / "progress.md").write_text("- Sprint-001 ✅ 已关闭\n- Sprint-002 未开始\n", encoding="utf-8")
        check("仅有同行✅、没有归档文件时仍阻止开启下一轮", not module.scan(root, "V1.0.0", scope="started")["ok"])
        (memory / "sprints/sprint-001.md").write_text("# Sprint-001\n\n验收通过，已归档。\n", encoding="utf-8")
        check("关闭首轮且归档后可启动计划中的下一轮", module.scan(root, "V1.0.0", scope="started")["ok"])
        check("交付门仍拦尚未完成的第二轮", module.scan(root, "V1.0.0")["open"] == ["Sprint-002"])
        other = root / "memory/V1.0.0/bob"
        other.mkdir()
        (other / "activeContext.md").write_text("- 当前 Sprint：Sprint-002\n", encoding="utf-8")
        check("存量项目跨用户当前上下文也能识别已开工轮次", module.scan(root, "V1.0.0", scope="started")["open"] == ["Sprint-002"])
        (other / "activeContext.md").write_text("- 当前 Sprint：Sprint-001 已关闭，等待 Sprint-002\n", encoding="utf-8")
        check("等待下一轮的文字不算已经启动", module.scan(root, "V1.0.0", scope="started")["ok"])
        (other / "progress.md").write_text("- Sprint-002 ✅\n", encoding="utf-8")
        check("旧项目仅有完成勾但缺归档也不能放行", not module.scan(root, "V1.0.0", scope="started")["ok"])
        (other / "progress.md").write_text("- Sprint-002 未开始（后续等待开发）\n", encoding="utf-8")
        check("计划中的等待开发说明不当成已启动", module.scan(root, "V1.0.0", scope="started")["ok"])


def test_planning_intent_dispatch():
    print("\n[P2] 强制规划与补件语义不能被未变快照吞掉")
    flow = (REPO / ".aidp/flows/sprint-autopilot/phase-3-3.md").read_text(encoding="utf-8")
    version = (REPO / ".aidp/commands/version.md").read_text(encoding="utf-8")
    planning = (REPO / ".aidp/flows/version/planning-3.md").read_text(encoding="utf-8")
    check("version 登记 force-replan / repair-planning", all(f"| `{flag}` |" in version
          for flag in ("--force-replan", "--repair-planning")))
    decision = version[version.index("模式决议："):version.index("**分支 → 流程章节对照**")]
    check("强制与缺件分支优先于 B-1 输入未变退出", "B-0" in decision
          and decision.index("B-0") < decision.index("**情况 B-1"))
    check("补件按族复用已有主文档，不误走只含变化的 supplement", "repair 模式" in planning
          and "fresh 调用" in planning and "缺失" in planning)
    match = re.search(r"<!-- planning-intent -->\s*```bash\n(.*?)```", flow, re.S)
    check("autopilot 实际组装并输出规划调用参数", match is not None)
    if not match:
        return
    with tempfile.TemporaryDirectory(prefix="aidp-plan-intent-") as directory:
        context_run = _run(str(SCRIPTS / "entry_context.py"), "resolve", "--root", directory,
                           "--entry", "version", "--version", "V1.0.0", "--json")
        context = json.loads(context_run.stdout)["execution_context"]
        _run(str(SCRIPTS / "baseline_edit.py"), "--version", "V1.0.0", "set", "execution_context", context, cwd=directory)
        for force, done, unattended, expected in (
                (1, 1, 1, "--force-replan --unattended"),
                (0, 0, 1, "--repair-planning --unattended"),
                (1, 0, 0, "--force-replan"),
                (0, 1, 0, "")):
            for name, value in (("TARGET_VERSION", "V1.0.0"), ("FORCE_REPLAN", str(force)),
                                ("PLANNING_DONE", str(done)), ("LOOP_UNATTENDED", str(unattended))):
                args = [sys.executable, str(SCRIPTS / "autopilot_tick_flags.py"), "set", "--command", "autopilot", name, value]
                subprocess.run(args, cwd=directory, check=True, capture_output=True)
            body = match.group(1).replace("{{AIDP_HOME}}", str(REPO / ".aidp"))
            result = subprocess.run(["bash", "-c", body], cwd=directory, capture_output=True, text=True)
            check(f"force={force} done={done} unattended={unattended} 参数不丢失",
                  result.returncode == 0 and result.stdout.strip().splitlines()[-1]
                  == f"/version V1.0.0 --execution-context {context} {expected}".strip())


def test_repair_scope_and_guard():
    print("\n[R2] 补件真实写集与只读字节保护")
    with tempfile.TemporaryDirectory(prefix="aidp-repair-") as directory:
        root = Path(directory)
        files = {
            "docs/requirements/V1.0.0/研发需求/01_研发需求.md": "# 需求\nREQ-101\n",
            "docs/design/detail/V1.0.0/01_详细设计.md": "# 设计\n保持字节\n",
            "docs/plans/V1.0.0/01_研发执行计划.md": "# 计划\n",
            "docs/testing/V1.0.0/研发自测/01_研发自测方案.md": "# 方案\n",
            "docs/testing/V1.0.0/研发自测/02_全量自测用例.md": "# 用例\n",
        }
        for name, text in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode())
            (path.parent / "00_索引.md").write_text("# 索引\n", encoding="utf-8")
        cli = [str(SCRIPTS / "planning_state.py"), "--root", str(root), "--version", "V1.0.0"]
        before = {p: (root / p).read_bytes() for p in files}
        out = _run(*cli, "begin-repair")
        scope = json.loads(out.stdout)
        target = "docs/testing/V1.0.0/研发自测/01_测试环境与账号.md"
        check("仅缺环境文件时只调 selftest 一个目标", scope["targets"] == {target: "selftest"})
        check("只有目标族索引可修改", scope["necessary_indexes"] == ["docs/testing/V1.0.0/研发自测/00_索引.md"])
        (root / target).write_text("# 环境\n本地模拟地址\n", encoding="utf-8")
        (root / scope["necessary_indexes"][0]).write_text("# 索引\n环境文件已登记\n", encoding="utf-8")
        verified = json.loads(_run(*cli, "check-repair").stdout)
        check("真实补件只改目标+necessary index，untouched bytes 完全不变",
              verified["ok"] and len(verified["redone"]) == 2
              and all((root / p).read_bytes() == body for p, body in before.items()))
        changed = next(p for p in files if "/design/" in p)
        (root / changed).write_text("越权重生成\n", encoding="utf-8")
        rejected = _run(*cli, "check-repair")
        check("无关族重写被机器门拒绝", rejected.returncode == 1 and changed in json.loads(rejected.stdout)["unexpected"])
        check("不能重新 begin-repair 清洗越权改写基线", _run(*cli, "begin-repair").returncode == 2)
        # 索引本身不能代替缺失的内容。
        (root / changed).unlink()
        scope = json.loads(_run(*cli, "scope").stdout)
        check("只有索引而无详设仍算缺件", changed in scope["targets"])


def test_five_stage_recovery():
    print("\n[R3] 五环节真实脚本恢复与依赖闭包失效")
    with tempfile.TemporaryDirectory(prefix="aidp-five-stage-") as directory:
        root = Path(directory)
        cli = [str(SCRIPTS / "planning_state.py"), "--root", str(root), "--version", "V1.0.0"]
        plan = "docs/plans/V1.0.0/01_研发执行计划.md"
        case = "docs/testing/V1.0.0/研发自测/02_全量自测用例.md"
        for name, text in {"inputs/requirements.md": "REQ-101", "inputs/plan-params.json": "{}",
                           "inputs/case-params.json": "{}", "inputs/00_索引.md": "# 输入索引\n\n[需求](requirements.md)\n"}.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        plan_text = (REPO / ".aidp/skills/dev-execution-planner/references/iteration-plan-sample.md").read_text(encoding="utf-8")
        case_text = ("# 用例\n\n## 套件 SUITE-001: 下单\n"
                     "> **自测方案章节:** [范围](01_研发自测方案.md#范围)\n"
                     "> **PRD 来源:** [REQ-101 下单](../../../requirements/V1.0.0/研发需求/01_研发需求.md#REQ-101)\n"
                     "> **详细设计来源:** [下单设计](../../../design/detail/V1.0.0/01_详细设计.md#下单)\n"
                     "> **研发执行计划来源**: ⟨PLAN-REF:REQ-101⟩\n")

        input_index = root / "inputs/00_索引.md"
        original_index = input_index.read_bytes()
        qo = str(REPO / ".aidp/skills/dev-execution-planner/scripts/qr_orchestration.py")
        _run(qo, "handoff", "--qr-level", "critical", "--write", str(input_index))

        def start(stage):
            cp = _run(*cli, "start", stage, "--input", "inputs/00_索引.md", "--input", "inputs/requirements.md",
                      "--input", f"inputs/{stage}-params.json", "--output", plan if stage == "plan" else case)
            return json.loads(cp.stdout)

        def finish(stage, success=True):
            result = root / f"{stage}-result.json"
            result.write_text(json.dumps({"status": "pass" if success else "fail", "exit_code": 0 if success else 1}))
            return _run(*cli, "finish", stage, "--result", result.name)

        # 两支均先 start，case 失败，plan 成功；恢复不重写成功分支。
        start("plan")
        start("case")
        (root / plan).parent.mkdir(parents=True)
        (root / plan).write_text(plan_text, encoding="utf-8")
        (root / case).parent.mkdir(parents=True)
        finish("plan")
        finish("case", False)
        frozen = (root / plan).read_bytes()
        check("case 单支失败后 plan 返回 reused", start("plan")["action"] == "reused")
        check("case 单支失败后只重新生成 case", start("case")["action"] == "redone")
        (root / case).write_text(case_text, encoding="utf-8")
        finish("case")
        cp = _run(*cli, "refs")
        output = json.loads(cp.stdout)
        check("真实 export/resolve/upstream 三脚本全通过并各自产生持久结果",
              cp.returncode == 0 and output["redone"] == ["map", "ref", "verify"]
              and all((root / f"memory/V1.0.0/.planning-results/{s}.json").is_file() for s in ("map", "ref", "verify")))
        check("回填完成没有 PLAN-REF 占位，plan 字节保持", "⟨PLAN-REF:" not in (root / case).read_text()
              and (root / plan).read_bytes() == frozen)
        cp = _run(*cli, "refs")
        check("同指纹恢复三环节全部 reused", json.loads(cp.stdout)["reused"] == ["map", "ref", "verify"])
        _run(qo, "handoff", "--qr-level", "full", "--write", str(input_index))
        status = json.loads(_run(*cli, "status").stdout)
        check("真实清 handoff 后五环节全部 reused，不自我失效",
              status["reused"] == ["plan", "case", "map", "ref", "verify"] and input_index.read_bytes() == original_index)
        input_index.write_bytes(original_index + b"\n[extra](other.md)\n")
        check("索引真实链接改动仍使依赖两支失效", not json.loads(_run(*cli, "status").stdout)["reused"])
        input_index.write_bytes(original_index)
        # 计划参数变化仅失效 plan -> map -> ref -> verify；case 生成仍保留。
        (root / "inputs/plan-params.json").write_text('{"iteration":2}')
        status = json.loads(_run(*cli, "status").stdout)
        check("计划输入变更只失效相关依赖闭包，case 复用", status["reused"] == ["case"])
        print("  plan-input-changed: " + json.dumps(status, ensure_ascii=False))
        scope = json.loads(_run(*cli, "scope").stdout)
        check("repair 自动从持久失效节点扩入 plan 目标与必要 case 回填",
              scope["targets"].get(plan) == "plan" and case not in scope["targets"]
              and case in scope["necessary_references"])
        start("plan")
        finish("plan", False)
        check("plan 单支失败后已生成 case 仍复用", start("case")["action"] == "reused")
        start("plan")
        (root / plan).write_text(plan_text.replace("Sprint-001", "Sprint-002"), encoding="utf-8")
        finish("plan")
        cp = _run(*cli, "refs")
        check("计划变化从 raw 用例快照重新回填链接、不重新生成 case",
              cp.returncode == 0 and "[Sprint-002 Task" in (root / case).read_text()
              and "case" in json.loads(_run(*cli, "status").stdout)["reused"])
        # 用例参数变化只失效 case/ref/verify，map 不动。
        (root / "inputs/case-params.json").write_text('{"cap":30}')
        status = json.loads(_run(*cli, "status").stdout)
        check("用例输入变化不失效计划和 map", status["reused"] == ["plan", "map"])
        print("  case-input-changed: " + json.dumps(status, ensure_ascii=False))
        # 真实 resolve 失败不覆盖任何旧有效用例。
        start("case")
        (root / case).write_text(case_text.replace("PLAN-REF:REQ-101", "PLAN-REF:REQ-999"), encoding="utf-8")
        finish("case")
        before = (root / case).read_bytes()
        cp = _run(*cli, "refs")
        check("ref 失败保持文件字节并保留 map 成功结果", cp.returncode == 1
              and (root / case).read_bytes() == before
              and "map" in json.loads(cp.stdout)["reused"])
        gate = _load_gate()
        check("占位 ref 连 skip-audit 都不能放行开发", not gate.scan(root, "V1.0.0", skip_audit=True)["ok"])


def test_qr_evidence_reuse():
    print("\n[Q4] artifact/contenthash/dimension/inputs/owner 证据缓存")
    gate = _load_gate()
    with tempfile.TemporaryDirectory(prefix="aidp-qr-cache-") as directory:
        root = Path(directory)
        artifact = "docs/plans/V1.0.0/01_研发执行计划.md"
        index = str(Path(artifact).parent / "00_索引.md")
        for name, text in {artifact: "# 计划\n内容\n", index: "# 索引\n", "inputs/req.md": "需求",
                           "inputs/design.md": "设计", "audit.md": "逐维度审查内容"}.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        skill = "dev-execution-planner"
        qo = str(REPO / f".aidp/skills/{skill}/scripts/qr_orchestration.py")
        _run(qo, "handoff", "--qr-level", "critical", "--write", str(root / index))
        dims = gate.unsettled_handoffs(root, "V1.0.0")[0]["deferred_dims"]
        (root / "result.json").write_text(json.dumps({"overall": "pass", "report_path": "audit.md",
                "dims": [{"id": d, "verdict": "pass"} for d in dims]}))
        def fingerprint(dim, inputs):
            return gate.qr_evidence(root, "V1.0.0", artifact, skill + ":" + dim,
                                    inputs, ["checklist=v1"])["fingerprint"]

        for dim in dims:
            inputs = ["inputs/req.md", index] if dim == dims[0] else ["inputs/design.md", index]
            gate.qr_evidence(root, "V1.0.0", artifact, skill + ":" + dim, inputs, ["checklist=v1"],
                             "result.json", "handoff:" + skill, "generator-1", "reviewer-2", fingerprint(dim, inputs))
        hit = gate.qr_evidence(root, "V1.0.0", artifact, skill + ":" + dims[0], ["inputs/req.md", index], ["checklist=v1"])
        check("同 artifact/hash/dimension/inputs 可复用且明确 owner", hit["ok"] and hit["owner"] == "handoff:" + skill)
        (root / "inputs/req.md").write_text("需求改变")
        miss = gate.qr_evidence(root, "V1.0.0", artifact, skill + ":" + dims[0], ["inputs/req.md", index], ["checklist=v1"])
        kept = gate.qr_evidence(root, "V1.0.0", artifact, skill + ":" + dims[1], ["inputs/design.md", index], ["checklist=v1"])
        check("必要 inputs 变化只失效相关维度", not miss["ok"] and kept["ok"])
        result = gate.settle_handoff(root, "V1.0.0", index, skill, "critical", REPO / ".aidp")
        check("任一维度失效时不清 handoff，收口失败", not result["ok"] and bool(gate.unsettled_handoffs(root, "V1.0.0")))
        gate.qr_evidence(root, "V1.0.0", artifact, skill + ":" + dims[0], ["inputs/req.md", index], ["checklist=v1"],
                         "result.json", "handoff:" + skill, "generator-1", "reviewer-2", fingerprint(dims[0], ["inputs/req.md", index]))
        result = gate.settle_handoff(root, "V1.0.0", index, skill, "critical", REPO / ".aidp")
        check("全部维度可信后调用原 SKILL 协议清 handoff", result["ok"] and not gate.unsettled_handoffs(root, "V1.0.0"))
        check("QR 必要输入包含自身索引，record→settle 后仍全复用", not gate.stale_settlements(root, "V1.0.0")
              and all(gate.qr_evidence(root, "V1.0.0", artifact, skill + ":" + d,
                     ["inputs/req.md", index] if d == dims[0] else ["inputs/design.md", index],
                     ["checklist=v1"])["action"] == "reused" for d in dims))
        old_fingerprint = fingerprint(dims[0], ["inputs/req.md", index])
        (root / artifact).write_text("# 计划\n产物内容变化\n", encoding="utf-8")
        check("清块后产物变化仍能检出过期证据", bool(gate.stale_settlements(root, "V1.0.0")))
        audit = root / "docs/audit/V1.0.0/version-output-audit-test.md"
        audit.parent.mkdir(parents=True, exist_ok=True)
        audit.write_text("".join(f"## {c} 项\nok\n" for c in "ABCDEFGH") + "overall: pass\n" + "说明。\n" * 80)
        final = gate.scan(root, "V1.0.0")
        fast = gate.scan(root, "V1.0.0", fast=True)
        check("--fast 可延期但最终门仍抓到缓存失效欠账", fast["ok"] and not final["ok"]
              and bool(final["unsettled_handoffs"]) and final["findings"][0]["kind"] == "qr-evidence-stale")
        try:
            gate.qr_evidence(root, "V1.0.0", artifact, skill + ":" + dims[0], ["inputs/req.md", index], ["checklist=v1"],
                             "result.json", "handoff:" + skill, "generator-1", "reviewer-2", old_fingerprint)
            changed_during_review = False
        except ValueError:
            changed_during_review = True
        check("审查期间 artifact 变更，旧 fingerprint 禁止登记新内容 pass", changed_during_review)
        try:
            gate.qr_evidence(root, "V1.0.0", artifact, skill + ":" + dims[0], ["inputs/req.md", index], ["checklist=v1"],
                             "result.json", "handoff:" + skill, "same-agent", "same-agent", fingerprint(dims[0], ["inputs/req.md", index]))
            independent = False
        except ValueError:
            independent = True
        check("生成者不能自签独立移交审查", independent)


if __name__ == "__main__":
    test_repair_scope_and_guard()
    test_five_stage_recovery()
    test_qr_evidence_reuse()
    test_planning_intent_dispatch()
    test_sprint_start_gate_scope()
    test_run_metrics_stage_and_render()
    test_parallel_plan_selftest_backfill()
    test_critical_never_deferred()
    test_fast_mode_release_gate()
    test_prd_presence_table_roundtrip()
    test_qr_level_dispatch_contract()
    test_selftest_scale_control_wiring()
    test_handoff_settlement_gate()
    print(f"\n══ 结果：{_passed} passed / {_failed} failed ══")
    sys.exit(1 if _failed else 0)
