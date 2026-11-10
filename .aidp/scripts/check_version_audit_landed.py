#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""版本规划产物审计「真的跑过」的存在性门（确定性，ERROR 级）。

`/version` Step 2.4.7 派 `version-auditor` 子 Agent 做八项审计，是 G-VERSION-2
「规划产物经独立审计才算数」的**唯一**承载者，也是 G-REQ-1 / G-REQ-2 的唯一落点
（PRD 条目去处 = 审计 C/C-4，原型覆盖度 = 审计 F，两者都是 Critical 硬门）。

★ 这道门补的是一个**静默失效面**：那一步的全部强制力此前都在散文里（铁律段 +
反模式表 + 三条自检问句），而「跑了且通过」与「压根没跑」在终端上**长得一模一样**
—— `docs/audit/{version}/` 为空、没有任何 flag、命令照样往下走。分片自己把这个
失效形态写出来了（planning-7.md「绝不因 Agent 不可用而视同 pass」），却只用它约束
了「Agent 不可用」一个分支，没有变成一条通用断言。

判据刻意只做**存在性 + 非空壳**，不碰审计内容：
  - `docs/audit/{version}/version-output-audit-*.md` 至少一份（fresh 与补丁两种命名都认）；
  - 该报告不是空壳 —— 须同时含八项标记里的多数与「结论/overall」字样。
      ⛔ 不去判 pass/warn/block：那是审计自己的结论，本门只回答「它到底产出过没有」。

`--skip-audit` 是**唯一**豁免，对应用户显式给 `/version` 传的同名旗标；豁免时退出 0
但把事实打出来，便于 Step 2.8 报告如实登记「本次未经审计」。

★ 第二条断言：**SKILL 的 QR 移交清单已结清**。`--qr-level=critical|scripts` 时，各规划 SKILL 把非 Critical
维度登记进产物目录 `00_索引.md` 的 `<!-- AIDP-QR-HANDOFF: … -->` 块，由 Step 2.4.7 的 qr-handoff-auditor
接手、审完由主流程清块。块还在 = 这些维度**既没被 SKILL 审、也没被统一审计接手**，而产物看起来一切正常。
`--fast` 时移交审计按设计延后：放行但如实打出「已延后」，发布前由发布流程强制结清。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import re
import sys
from pathlib import Path

_script_dir = str(Path(__file__).resolve().parent)
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)
from planning_state import content_bytes

REPORT_GLOB = "version-output-audit-*.md"
# 八项审计的小节标记。报告须命中多数项才算"有内容"，命中少数 = 空壳/半截。
ITEM_RE = re.compile(r"(?m)^\W{0,4}\**\s*([A-H])[\s、.:：\-]")
MIN_ITEMS = 5
VERDICT_RE = re.compile(r"overall|结论|综合评级|审计结果")
MIN_BYTES = 512


# 规划产物落点：任一存在即说明「这个版本确实跑过规划」，本门才有判定对象。
PLANNING_DIRS = ("docs/requirements/{v}", "docs/design/detail/{v}", "docs/plans/{v}",
                 "docs/testing/{v}")
# 四个规划 SKILL 写 QR 移交清单的位置（与 reference/SKILL编排层接入.md 第二节同一张表）。
HANDOFF_INDEXES = ("docs/requirements/{v}/研发需求/00_索引.md", "docs/design/detail/{v}/00_索引.md",
                   "docs/plans/{v}/00_索引.md", "docs/testing/{v}/研发自测/00_索引.md")
HANDOFF_RE = re.compile(r"^<!-- AIDP-QR-HANDOFF: (\{.*\}) -->\s*$")


def unsettled_handoffs(root: Path, version: str) -> list:
    """返回仍留在 00_索引.md 里的移交清单（代码围栏里的示例不算）。"""
    found = []
    for rel in HANDOFF_INDEXES:
        path = root / rel.format(v=version)
        if not path.is_file():
            continue
        fenced = False
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.lstrip().startswith(("```", "~~~")):
                fenced = not fenced
                continue
            match = None if fenced else HANDOFF_RE.match(line)
            if not match:
                continue
            try:
                block = json.loads(match.group(1))
            except ValueError:
                block = {}
            dims = [d.get("id") for d in block.get("deferred_dims", []) if isinstance(d, dict)]
            found.append({"file": path.relative_to(root).as_posix(),
                          "skill": block.get("skill", "?"), "deferred_dims": dims})
    return found


def _local(root: Path, name: str) -> Path:
    path = root / name
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"证据路径超出项目: {name}")
    return path


def _hash_files(root: Path, names: list, semantic: bool = False) -> dict:
    values = {}
    for name in sorted(set(names)):
        path = _local(root, name)
        files = sorted(path.rglob("*")) if path.is_dir() else [path]
        if not files:
            values[name + "/"] = "empty-directory"
        for item in files:
            if item.is_dir():
                continue
            rel = item.relative_to(root).as_posix()
            _local(root, rel)
            values[rel] = hashlib.sha256(content_bytes(item, semantic)).hexdigest() if item.is_file() else "missing"
    return values


def qr_key(artifact: str, dimension: str) -> str:
    return hashlib.sha256((artifact + "\0" + dimension).encode()).hexdigest()


def qr_evidence(root: Path, version: str, artifact: str, dimension: str,
                inputs: list, params: list, result_path: str = "", owner: str = "",
                producer: str = "", reviewer: str = "", expected: str = "") -> dict:
    """只消费调用层保存的真实逐维 JSON；存在报告不等于每个维度都审过。"""
    current = {"artifact": artifact, "dimension": dimension,
               "content": _hash_files(root, [artifact]), "inputs": _hash_files(root, inputs, semantic=True),
               "params": sorted(params)}
    fingerprint = hashlib.sha256(json.dumps(current, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    key = qr_key(artifact, dimension)
    path = root / "memory" / version / ".planning-qr" / (key + ".json")
    if not result_path:
        cached = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        evidence = cached.get("evidence", {})
        hit = (cached.get("subject") == current and bool(evidence)
               and evidence == _hash_files(root, list(evidence)))
        return {"action": "reused" if hit else "missing", "artifact": artifact,
                "dimension": dimension, "owner": cached.get("owner") if hit else None,
                "evidence": evidence if hit else {}, "fingerprint": fingerprint, "ok": bool(hit)}
    if expected != fingerprint:
        raise ValueError("审查派单时的 fingerprint 缺失或已变化，必须按当前内容/输入重审")
    if not inputs or not params or any(v in ("missing", "empty-directory") for v in current["content"].values()):
        raise ValueError("QR 证据必须绑定已有产物、必要 inputs 和判据/调用参数")
    skill, sep, dim = dimension.partition(":")
    if not sep or owner not in (f"skill:{skill}", f"handoff:{skill}"):
        raise ValueError("维度须为 skill:QR-NN，owner 为 skill:<skill> 或 handoff:<skill>")
    if not producer or not reviewer or (owner.startswith("handoff:") and producer == reviewer):
        raise ValueError("移交审查必须来自与产物生成者不同的独立 reviewer")
    result = json.loads(_local(root, result_path).read_text(encoding="utf-8"))
    dims = result.get("dims", [])
    matches = [d for d in dims if isinstance(d, dict) and d.get("id") == dim]
    if result.get("overall") not in ("pass", "warn") or len(matches) != 1 or matches[0].get("verdict") != "pass":
        raise ValueError("缺少该维度的可信 pass 结果；失败/未核验不能缓存")
    report = result.get("report_path", "")
    if not report or not _local(root, report).is_file() or not _local(root, report).read_bytes().strip():
        raise ValueError("逐维结果必须引用已落盘的非空报告")
    record = {"subject": current, "owner": owner, "producer": producer, "reviewer": reviewer,
              "input_paths": inputs, "params": params,
              "evidence": _hash_files(root, [result_path, report])}
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False, encoding="utf-8") as out:
        json.dump(record, out, ensure_ascii=False, indent=2)
        temporary = out.name
    os.replace(temporary, path)
    return {"action": "redone", "ok": True, "artifact": artifact, "dimension": dimension, "owner": owner}


def settle_handoff(root: Path, version: str, index: str, skill: str, level: str, home: Path) -> dict:
    """调用依赖原协议校验清单，逐 artifact×dimension 命中才允许原工具清块。"""
    expected = {p.format(v=version) for p in HANDOFF_INDEXES}
    if index not in expected or skill not in ("ux-logic-extractor", "dev-logic-architect",
                                             "dev-execution-planner", "dev-manual-testcase"):
        raise ValueError("非规划 SKILL 或非版本移交索引")
    tool = home / "skills" / skill / "scripts/qr_orchestration.py"
    settled = root / "memory" / version / ".planning-qr" / f"settled-{skill}.json"
    if settled.is_file() and not any(h["file"] == index for h in unsettled_handoffs(root, version)):
        # 已清块后的新增/失效证据仍按原清单协议补审，不让缺块变成永久豁免。
        previous = json.loads(settled.read_text(encoding="utf-8"))
        if previous.get("level", level) != level:
            raise ValueError("补审必须使用原移交档位")
        restored = subprocess.run([sys.executable, str(tool), "handoff", "--qr-level", level,
                                   "--write", str(_local(root, index))], capture_output=True, text=True)
        if restored.returncode:
            return {"ok": False, "missing": ["handoff-restore-failed"]}
    parsed = subprocess.run([sys.executable, str(tool), "parse-handoff", str(_local(root, index)),
                             "--expect-level", level], capture_output=True, text=True)
    if parsed.returncode:
        return {"ok": False, "missing": ["handoff-invalid"], "detail": parsed.stdout + parsed.stderr}
    handoffs = [h for h in unsettled_handoffs(root, version) if h["file"] == index]
    if not handoffs:
        return {"ok": True, "reused": [], "missing": []}
    if any(h["skill"] != skill for h in handoffs):
        raise ValueError("清单 SKILL 与请求不一致")
    artifacts = sorted(p for p in _local(root, index).parent.rglob("*.md") if p.name != "00_索引.md")
    missing, reused = [], []
    for artifact in artifacts:
        rel = artifact.relative_to(root).as_posix()
        for dim in handoffs[0]["deferred_dims"]:
            dimension = skill + ":" + dim
            cached = root / "memory" / version / ".planning-qr" / (qr_key(rel, dimension) + ".json")
            record = json.loads(cached.read_text(encoding="utf-8")) if cached.is_file() else {}
            hit = qr_evidence(root, version, rel, dimension, record.get("input_paths", []), record.get("params", []))
            (reused if hit["ok"] else missing).append({"artifact": rel, "dimension": dimension})
    if not artifacts or missing:
        return {"ok": False, "reused": reused, "missing": missing or ["no-artifacts"]}
    settled.write_text(json.dumps({"index": index, "level": level, "skill": skill,
                                   "subjects": reused}, ensure_ascii=False), encoding="utf-8")
    cleared = subprocess.run([sys.executable, str(tool), "handoff", "--qr-level", "full", "--write",
                              str(_local(root, index))], capture_output=True, text=True)
    return {"ok": cleared.returncode == 0, "reused": reused, "missing": [],
            "detail": cleared.stdout + cleared.stderr}


def stale_settlements(root: Path, version: str) -> list:
    stale = []
    directory = root / "memory" / version / ".planning-qr"
    for path in directory.glob("settled-*.json"):
        record = json.loads(path.read_text(encoding="utf-8"))
        subjects = record["subjects"]
        origin = {"index": record["index"], "skill": record.get("skill", "cached-evidence"),
                  "level": record.get("level", "critical")}
        covered = {s["artifact"] for s in subjects}
        current = {p.relative_to(root).as_posix() for p in _local(root, record["index"]).parent.rglob("*.md")
                   if p.name != "00_索引.md"}
        for added in sorted(current - covered):
            stale.append({**origin, "artifact": added, "dimension": "unreviewed-artifact"})
        for subject in subjects:
            key = qr_key(subject["artifact"], subject["dimension"])
            evidence = directory / (key + ".json")
            data = json.loads(evidence.read_text(encoding="utf-8")) if evidence.is_file() else {}
            if not qr_evidence(root, version, subject["artifact"], subject["dimension"],
                               data.get("input_paths", []), data.get("params", []))["ok"]:
                stale.append({**origin, **subject})
    return stale


def _audit_dir(root: Path, version: str) -> Path:
    return root / "docs" / "audit" / version


def _has_planning_artifacts(root: Path, version: str) -> bool:
    """这个版本有没有规划产物。

    ⛔ 这是本门的**适用范围**判据，不是放宽：没有任何规划产物 = Step 2.4 都没跑完，
    此时报「审计缺失」只会指错方向（真问题在上游），且会让任何在无关目录里调用本门的
    场景恒红。有产物才谈得上「这批产物经没经过独立审计」。
    """
    for pattern in PLANNING_DIRS:
        directory = root / pattern.format(v=version)
        if directory.is_dir() and any(directory.rglob("*.md")):
            return True
    return False


def _handoff_finding(items: list, fast: bool) -> dict:
    listing = "；".join(f"{h['file']}（{h['skill']}：{', '.join(h['deferred_dims']) or '—'}）" for h in items)
    if fast:
        return {"kind": "qr-handoff-deferred-by-fast",
                "detail": f"--fast：移交维度未经统一审计、按设计延后 —— {listing}。"
                          "版本发布前必须补跑 Step 2.4.7 结清（发布流程会拦）。"}
    return {"kind": "qr-handoff-unsettled",
            "detail": f"QR 移交清单未结清 —— {listing}：这些维度没被 SKILL 审，也没被统一审计接手。"
                      "回跑 Step 2.4.7 的移交维度并行审计，pass 后由主流程清块。"}


def scan(root: Path, version: str, skip_audit: bool = False, fast: bool = False) -> dict:
    directory = _audit_dir(root, version)
    reports = sorted(p for p in directory.glob(REPORT_GLOB) if p.is_file()) \
        if directory.is_dir() else []
    result = {
        "version": version,
        "audit_dir": directory.relative_to(root).as_posix()
        if directory.is_absolute() == root.is_absolute() else str(directory),
        "reports": [p.name for p in reports],
        "skip_audit": bool(skip_audit),
        "ok": False,
        "findings": [],
    }
    handoffs = unsettled_handoffs(root, version)
    stale = stale_settlements(root, version)
    # 发布旧调用方按未结清份数分流；清块后的过期证据仍作为真实欠账暴露。
    debts = {}
    for item in stale:
        index = item["index"]
        debt = debts.setdefault(index, {"file": index, "skill": item["skill"], "qr_level": item["level"],
                                        "deferred_dims": [], "reason": "qr-evidence-stale"})
        debt["deferred_dims"].append(item["dimension"])
    result["unsettled_handoffs"] = handoffs + list(debts.values())
    cases = root / f"docs/testing/{version}/研发自测"
    unresolved = [p.relative_to(root).as_posix() for p in cases.rglob("*.md")
                  if "⟨PLAN-REF:" in p.read_text(encoding="utf-8", errors="replace")]
    if unresolved:
        result["findings"].append({"kind": "plan-ref-unresolved", "detail": "计划引用尚未回填：" + ", ".join(unresolved)})
        return result
    if skip_audit:
        result["ok"] = True
        result["findings"].append({
            "kind": "audit-skipped-by-flag",
            "detail": "用户显式传了 --skip-audit：本次规划产物未经独立审计，"
                      "须在版本规划报告里如实登记（⛔ 不得写成「审计通过」）。",
        })
        if handoffs:   # 豁免审计 ≠ 移交维度审过了：事实照样打出来
            result["findings"].append(_handoff_finding(handoffs, fast=True))
        return result
    if not _has_planning_artifacts(root, version):
        result["ok"] = True
        result["skipped"] = "no-planning-artifacts"
        return result
    if not reports:
        result["findings"].append({
            "kind": "audit-report-missing",
            "detail": f"未找到 {result['audit_dir']}/{REPORT_GLOB}："
                      "Step 2.4.7 的独立审计没有产出报告。回跑 Step 2.4.7；"
                      "确需跳过须用户显式以 --skip-audit 重新调用 /version。",
        })
        return result
    substantive = []
    for path in reports:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            result["findings"].append({
                "kind": "audit-report-unreadable",
                "detail": f"{path.name}：{exc}",
            })
            continue
        items = {m.group(1) for m in ITEM_RE.finditer(text)}
        if len(text.encode("utf-8")) >= MIN_BYTES and len(items) >= MIN_ITEMS \
                and VERDICT_RE.search(text):
            substantive.append(path.name)
        else:
            result["findings"].append({
                "kind": "audit-report-stub",
                "detail": f"{path.name}：只命中 {len(items)} 项八项标记"
                          f"（需 ≥{MIN_ITEMS}）或缺结论字样 —— 像是占位空壳，不算审计产出。",
            })
    result["substantive"] = substantive
    result["ok"] = bool(substantive)
    if stale:
        result["findings"].append({"kind": "qr-evidence-stale", "detail": stale})
        if not fast:
            result["ok"] = False
    if handoffs:
        result["findings"].append(_handoff_finding(handoffs, fast))
        if not fast:
            result["ok"] = False
    return result


def self_check() -> bool:
    import tempfile
    import shutil

    root = Path(tempfile.mkdtemp(prefix="aidp-version-audit-gate-"))
    body = ("# 版本规划产物审计\n\n## A 存在性\nok\n## B 边界\nok\n## C 覆盖完整性\nok\n"
            "## D 增量一致性\nok\n## E 引用链\nok\n## F 原型覆盖度\nok\n"
            "## G 语义变更派生完整性\nok\n## H 跨版本需求作废完整性\nok\n\n"
            "overall: pass\n" + "补充说明。\n" * 40)
    try:
        # 适用范围：没有任何规划产物 → N/A 跳过（阴性对照：⛔ 不是"缺失"）。
        na = scan(root, "V0.1.0")
        # 造出规划产物，本门才开始判。
        planning = root / "docs/requirements/V0.1.0"
        planning.mkdir(parents=True)
        (planning / "01_需求.md").write_text("# 需求\n", encoding="utf-8")
        # 阴性①：有规划产物但没有审计报告 → 必须报缺失。
        missing = scan(root, "V0.1.0")
        # 阴性②：有目录但只有空壳报告 → 仍不算审计产出。
        directory = _audit_dir(root, "V0.1.0")
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "version-output-audit-2026-01-01.md").write_text(
            "# 审计\n\nTODO\n", encoding="utf-8")
        stub = scan(root, "V0.1.0")
        # 阳性：实质报告 → 通过。
        (directory / "version-output-audit-2026-01-01.md").write_text(body, encoding="utf-8")
        landed = scan(root, "V0.1.0")
        # 豁免：--skip-audit 通过，但必须留下「未经审计」的事实。
        waived = scan(root, "V0.9.9", skip_audit=True)   # --skip-audit 先于适用范围判据
        # 移交清单：块在 → 不通过；--fast → 放行但留痕；代码围栏里的示例块不算。
        idx = root / "docs/requirements/V0.1.0/研发需求/00_索引.md"
        idx.parent.mkdir(parents=True, exist_ok=True)
        block = ('<!-- AIDP-QR-HANDOFF: {"skill":"ux-logic-extractor","qr_level":"critical",'
                 '"deferred_dims":[{"id":"QR-02"}],"handoff_to":"编排层统一审计"} -->')
        idx.write_text("# 索引\n\n```text\n" + block + "\n```\n", encoding="utf-8")
        fenced_only = scan(root, "V0.1.0")
        idx.write_text("# 索引\n> QR 级别: critical；未审维度: [QR-02 示例]；移交: 编排层统一审计\n" + block + "\n",
                       encoding="utf-8")
        unsettled = scan(root, "V0.1.0")
        deferred = scan(root, "V0.1.0", fast=True)
        return (na["ok"] and na.get("skipped") == "no-planning-artifacts"
                and not missing["ok"]
                and [f["kind"] for f in missing["findings"]] == ["audit-report-missing"]
                and not stub["ok"]
                and [f["kind"] for f in stub["findings"]] == ["audit-report-stub"]
                and landed["ok"] and landed["findings"] == []
                and waived["ok"]
                and [f["kind"] for f in waived["findings"]] == ["audit-skipped-by-flag"]
                and fenced_only["ok"] and fenced_only["findings"] == []
                and not unsettled["ok"]
                and [f["kind"] for f in unsettled["findings"]] == ["qr-handoff-unsettled"]
                and deferred["ok"]
                and [f["kind"] for f in deferred["findings"]] == ["qr-handoff-deferred-by-fast"])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="版本规划产物审计存在性门")
    ap.add_argument("--root", default=".")
    ap.add_argument("--version", help="版本号，如 V0.1.0")
    ap.add_argument("--skip-audit", action="store_true",
                    help="对应 /version 的同名旗标：用户显式声明本次不做独立审计")
    ap.add_argument("--fast", action="store_true",
                    help="对应 /version --fast：移交维度审计按设计延后，放行但留痕（发布前须结清）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--qr-action", choices=("get", "put", "settle"))
    ap.add_argument("--artifact")
    ap.add_argument("--dimension")
    ap.add_argument("--input", action="append", default=[])
    ap.add_argument("--param", action="append", default=[])
    ap.add_argument("--result", default="")
    ap.add_argument("--fingerprint", default="", help="QR 派单前 get 返回的指纹，put 时防止审查期间输入变化")
    ap.add_argument("--owner", default="")
    ap.add_argument("--producer", default="")
    ap.add_argument("--reviewer", default="")
    ap.add_argument("--index")
    ap.add_argument("--skill")
    ap.add_argument("--expect-level", choices=("scripts", "critical", "full"), default="critical")
    ap.add_argument("--aidp-home", default=str(Path(__file__).resolve().parents[1]))
    ap.add_argument("--self-check", action="store_true")
    args = ap.parse_args(argv)
    if args.self_check:
        ok = self_check()
        print(json.dumps({"self_check": "pass" if ok else "fail"}, ensure_ascii=False))
        return 0 if ok else 1
    if not args.version:
        ap.error("--version 必填")
    root = Path(args.root).resolve()
    if not root.is_dir():
        ap.error("--root 必须是目录")
    if not re.fullmatch(r"[Vv]\d+(?:\.\d+){0,2}", args.version):
        ap.error("版本号须为 V主[.次[.补丁]]")
    try:
        if args.qr_action == "settle":
            if not args.index or not args.skill:
                ap.error("settle 必须提供 --index / --skill")
            result = settle_handoff(root, args.version, args.index, args.skill, args.expect_level,
                                    Path(args.aidp_home).resolve())
        elif args.qr_action:
            if not args.artifact or not args.dimension or (args.qr_action == "put" and not args.result):
                ap.error("QR get/put 须提供 --artifact / --dimension；put 另须 --result")
            result = qr_evidence(root, args.version, args.artifact, args.dimension, args.input, args.param,
                                 args.result if args.qr_action == "put" else "", args.owner,
                                 args.producer, args.reviewer, args.fingerprint)
        else:
            result = scan(root, args.version, args.skip_audit, args.fast)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    if args.json or args.qr_action:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result["ok"] and not result["findings"]:
        print(f"[OK] 版本规划产物审计已落地：{'、'.join(result['reports'])}")
    else:
        level = "WARN" if result["ok"] else "ERROR"
        for item in result["findings"]:
            print(f"[{level}] {item['kind']} {item['detail']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
