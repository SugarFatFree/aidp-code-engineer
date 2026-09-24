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
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPORT_GLOB = "version-output-audit-*.md"
# 八项审计的小节标记。报告须命中多数项才算"有内容"，命中少数 = 空壳/半截。
ITEM_RE = re.compile(r"(?m)^\W{0,4}\**\s*([A-H])[\s、.:：\-]")
MIN_ITEMS = 5
VERDICT_RE = re.compile(r"overall|结论|综合评级|审计结果")
MIN_BYTES = 512


# 规划产物落点：任一存在即说明「这个版本确实跑过规划」，本门才有判定对象。
PLANNING_DIRS = ("docs/requirements/{v}", "docs/design/detail/{v}", "docs/plans/{v}",
                 "docs/testing/{v}")


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


def scan(root: Path, version: str, skip_audit: bool = False) -> dict:
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
    if skip_audit:
        result["ok"] = True
        result["findings"].append({
            "kind": "audit-skipped-by-flag",
            "detail": "用户显式传了 --skip-audit：本次规划产物未经独立审计，"
                      "须在版本规划报告里如实登记（⛔ 不得写成「审计通过」）。",
        })
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
        return (na["ok"] and na.get("skipped") == "no-planning-artifacts"
                and not missing["ok"]
                and [f["kind"] for f in missing["findings"]] == ["audit-report-missing"]
                and not stub["ok"]
                and [f["kind"] for f in stub["findings"]] == ["audit-report-stub"]
                and landed["ok"] and landed["findings"] == []
                and waived["ok"]
                and [f["kind"] for f in waived["findings"]] == ["audit-skipped-by-flag"])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="版本规划产物审计存在性门")
    ap.add_argument("--root", default=".")
    ap.add_argument("--version", help="版本号，如 V0.1.0")
    ap.add_argument("--skip-audit", action="store_true",
                    help="对应 /version 的同名旗标：用户显式声明本次不做独立审计")
    ap.add_argument("--json", action="store_true")
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
    result = scan(root, args.version, args.skip_audit)
    if args.json:
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
