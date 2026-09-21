#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发布域门禁回归：增量轨存在性 / 只读采集方式 / 零残留断言发布总闸 / 推送状态如实渲染。

四项都属同一族缺口——**「做过」与「没做过」在产物上完全同形**：
· 增量轨：`check_increment_terseness` 首行 `if not inc.is_dir(): return` ⇒
  从未产增量轨的版本，12 项门照样打「🎉 无 ERROR」放行发布；
· 只读采集：G-RELEASE-2 的「全程只读」半条此前零落点（全仓 grep「只读」在该脚本命中 0）；
· 零残留总闸：release-7.md 写着「⛔ 不接受任何 skipped」，`version.md` 骨架表照抄，
  **让它在骨架层看起来像硬门**，实际无执行体、无判定器、无阻断力；
· 推送状态：报告恒写「已创建并自动推送」，于是「tag 未创建」欠账与「发布成功·已推送」同屏出现。
"""
import json
import os
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
RBC = str(REPO / ".aidp/scripts/release_baseline_check.py")
RRG = str(REPO / ".aidp/scripts/check_release_residual_gate.py")

_passed = _failed = 0


def check(name, cond):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ✅ {name}")
    else:
        _failed += 1
        print(f"  ❌ FAIL: {name}")


def _mk_version_dir(root, *, inc_content=True, zero_decl=False, readonly_decl=True):
    """造一个最小可判定的 docs/deployment/V0.1 双轨目录。"""
    v = root / "docs/deployment/V0.1"
    for sub in ("sql/全量", "配置文件/全量", "sql/增量", "配置文件/增量"):
        (v / sub).mkdir(parents=True, exist_ok=True)
    idx = "# 索引\n\n全新部署走全量轨，升级走增量轨，两套绝不叠加执行。\n"
    if zero_decl:
        idx += "\n本版无增量：配置中心在该区间无变更记录，SQL 亦无 DDL。\n"
    (v / "00_索引.md").write_text(idx, encoding="utf-8")
    # ⛔ 全量轨判据读的是**各全量子目录自己的** 00_索引.md，不是版本级那份
    #   （第一次写对照时就栽在这里：夹具写了版本级索引，判据一条都没跑到、阳性对照假绿）
    full_idx = "# 全量索引\n本版无剔除项（已交叉核对）。导出源：192.0.2.20:5236 schema=APP。\n"
    if readonly_decl:
        full_idx += "DDL 经 INFORMATION_SCHEMA 元数据视图只读导出；配置经配置中心只读 API 拉取。\n"
    for sub in ("sql/全量", "配置文件/全量"):
        (v / sub / "00_索引.md").write_text(full_idx, encoding="utf-8")
    if inc_content:
        (v / "sql/增量/01_加列.sql").write_text("ALTER TABLE T ADD COLUMN X INT;\n", encoding="utf-8")
        (v / "配置文件/增量/配置项清单.md").write_text("```yaml\na: b\n```\n", encoding="utf-8")
    return v


def _rbc(root, grep):
    cp = subprocess.run([sys.executable, RBC, "--root", str(root), "--version", "V0.1"],
                        capture_output=True, text=True)
    out = cp.stdout + cp.stderr
    return [l for l in out.splitlines() if grep in l]


def test_increment_presence():
    """增量轨存在性：空是合法的，空得没有交代不是。"""
    print("\n[R1] 增量轨存在性（约定 37.2 两轨对称 + 37.5-7 零变更显式成文）")
    d = Path(tempfile.mkdtemp())
    _mk_version_dir(d, inc_content=False, zero_decl=False)
    hits = _rbc(d, "增量轨存在性")
    check("★ 阳性：增量轨为空且索引无零变更声明 → ERROR（此前 12 项门全绿放行）",
          any("❌" in h for h in hits) and len([h for h in hits if "❌" in h]) == 2)
    shutil.rmtree(d, ignore_errors=True)

    d = Path(tempfile.mkdtemp())
    _mk_version_dir(d, inc_content=True)
    check("阴性：增量轨有产出 → 放行", not any("❌" in h for h in _rbc(d, "增量轨存在性")))
    shutil.rmtree(d, ignore_errors=True)

    d = Path(tempfile.mkdtemp())
    _mk_version_dir(d, inc_content=False, zero_decl=True)
    check("★ 阴性：空但索引显式声明零变更 → 合法放行（⛔ 零变更本就是合法结论）",
          not any("❌" in h for h in _rbc(d, "增量轨存在性")))
    shutil.rmtree(d, ignore_errors=True)


def test_readonly_collection_declared():
    """G-RELEASE-2 的「全程只读」半条：产物证明不了过程，但采集方式必须可复核。"""
    print("\n[R2] 全量基线只读采集方式声明")
    d = Path(tempfile.mkdtemp())
    _mk_version_dir(d, readonly_decl=False)
    hits = _rbc(d, "只读采集方式")
    check("★ 阳性：索引未交代只读采集方式 → ERROR（两个全量轨各一条）",
          len([h for h in hits if "❌" in h]) == 2)
    shutil.rmtree(d, ignore_errors=True)

    d = Path(tempfile.mkdtemp())
    _mk_version_dir(d, readonly_decl=True)
    check("阴性：写明元数据视图 + 只读 API → 放行", not _rbc(d, "只读采集方式"))
    shutil.rmtree(d, ignore_errors=True)


def test_residual_release_gate():
    """零残留断言发布总闸：Sprint 内可裁剪，发布前必须全跑一次。"""
    print("\n[R3] 零残留断言发布总闸")
    hdr = ("| # | 断言 | 守护面 | 实跑命令 | 方向一·现状命中 | 方向二·阳性对照 | 退役状态 |\n"
           "| :- | :- | :- | :- | :- | :- | :- |\n")

    def scene(row, as_of="2026-09-16"):
        d = Path(tempfile.mkdtemp())
        base = d / "docs/testing/V0.1/研发自测"
        base.mkdir(parents=True)
        (base / "02_用例.md").write_text(hdr + row, encoding="utf-8")
        cp = subprocess.run([sys.executable, RRG, "--root", str(d), "--version", "V0.1",
                             "--as-of", as_of, "--json"], capture_output=True, text=True)
        shutil.rmtree(d, ignore_errors=True)
        return json.loads(cp.stdout)

    A = '| Z-01 | `断言(反向):不存在文本"批量导出"` | `src/**` | `grep ...` | '
    r = scene(A + 'skipped(out-of-scope) | 1 命中 | 在役 |\n')
    check("★ 阳性：在役行标 skipped → 不通过（发布总闸不接受任何 skipped）",
          not r["ok"] and any("不接受任何 skipped" in e["msg"] for e in r["errors"]))
    r = scene(A + '0 命中(2026-09-01 10:12) | 1 命中 | 在役 |\n')
    check("★ 阳性：沿用上一轮的实跑日期 → 不通过（那不是「发布前跑过」）",
          not r["ok"] and any("上一轮" in e["msg"] for e in r["errors"]))
    r = scene(A + '3 命中(2026-09-16 10:12) | 1 命中 | 在役 |\n')
    check("阳性：非零命中 → 不通过（断言未归零）",
          not r["ok"] and any("未归零" in e["msg"] for e in r["errors"]))
    r = scene(A + '0 命中(2026-09-16 10:12) | 1 命中 | 在役 |\n')
    check("阴性：当日实跑且 0 命中 → 通过", r["ok"] and r["active_rows"] == 1)
    r = scene(A + '— (已退役) | — | 已退役(Sprint-046) |\n')
    check("★ 阴性：已退役行不要求实跑（否则退役等于永远还债）", r["ok"])

    d = Path(tempfile.mkdtemp())
    (d / "docs/testing/V0.1/研发自测").mkdir(parents=True)
    (d / "docs/testing/V0.1/研发自测/02_用例.md").write_text("# 用例\n无反向断言。\n", encoding="utf-8")
    cp = subprocess.run([sys.executable, RRG, "--root", str(d), "--version", "V0.1", "--json"],
                        capture_output=True, text=True)
    check("★ 零误报：本版无反向断言 → 合法跳过，不得恒红",
          json.loads(cp.stdout).get("skipped_reason") == "no-assertion")
    (d / "docs/testing/V0.1/研发自测/02_用例.md").write_text(
        '断言(反向):不存在文本"X"\n', encoding="utf-8")
    cp = subprocess.run([sys.executable, RRG, "--root", str(d), "--version", "V0.1", "--json"],
                        capture_output=True, text=True)
    check("★ 阳性：有反向断言却无登记表 → 不通过（断言无人跟踪）",
          not json.loads(cp.stdout)["ok"])
    shutil.rmtree(d, ignore_errors=True)

    cp = subprocess.run([sys.executable, RRG, "--self-check"], capture_output=True, text=True)
    check("脚本自带阳性对照可独立跑通（--self-check）", cp.returncode == 0)


def test_push_state_not_hardcoded():
    """报告里的 tag/分支推送状态必须按实际渲染，⛔ 不得恒写「已推送」。"""
    print("\n[R4] 发布报告推送状态如实渲染")
    t = (REPO / ".aidp/flows/version/release-7b.md").read_text(encoding="utf-8")
    check("★ 不再硬编码「本地已创建并自动推送」",
          "本地已创建并自动推送至 origin" not in t)
    check("改为按状态渲染的占位（TAG_STATE / BRANCH_STATE）",
          "{TAG_STATE}" in t and "{BRANCH_STATE}" in t)
    check("★ 状态取值消费 release_push_failed（Step 3.4.3 落的失败标记）",
          "release_push_failed" in t)

    # 三态判定逻辑本身的双侧对照（与分片里那段 state() 同形）
    script = '''
state(){ [ -z "$1" ] && { echo NOT_CREATED; return; }
  case ",$PF," in *",$2,"*) echo PUSH_FAILED;; *) echo PUSHED;; esac; }
PF="$3"; state "$1" "$2"
'''
    def st(name, kind, pf):
        return subprocess.run(["bash", "-c", script, "_", name, kind, pf],
                              capture_output=True, text=True).stdout.strip()
    check("阴性：未创建 tag → NOT_CREATED", st("", "tag", "") == "NOT_CREATED")
    check("阴性：创建且推送成功 → PUSHED", st("v0.1.0", "tag", "") == "PUSHED")
    check("★ 阳性：创建但推送失败 → PUSH_FAILED（此前恒写「已推送」）",
          st("v0.1.0", "tag", "commit,tag") == "PUSH_FAILED")
    check("★ 边界：commit 推失败但 tag 自身成功 → tag 仍判 PUSHED（不连坐）",
          st("v0.1.0", "tag", "commit") == "PUSHED")


def main():
    test_increment_presence()
    test_readonly_collection_declared()
    test_residual_release_gate()
    test_push_state_not_hardcoded()
    print(f"\n══ 结果：{_passed} passed / {_failed} failed ══")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
