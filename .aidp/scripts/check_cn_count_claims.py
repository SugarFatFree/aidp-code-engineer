#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_cn_count_claims.py — 文档里**中文数字**写的自称计数必须与实数一致。

## 为什么需要本脚本

`check_count_claims.py` 只认阿拉伯数字（`9 个 Agent`、`N 项核心约定`）。可文档里同样会写
「本目录下的九份角色指令」「## 九份角色与归属」：新增第 10 份角色时没人想起去改，而它们
正好是人读 README 时第一眼看到的数字。实测 `agents/README.md` 两处「九份」逃检，实有 10 份。

## 判据（宁可少做，不可误报）

只认**明确在报总数**的措辞，真值全部现算：

1. `N 份角色` / `N 份 Agent`（N ≥ 2）—— 真值 = `{{AIDP_HOME}}/agents/*.md`（不含 README）数；
   `共 N 个 角色|Agent`、`N 个 Agent 指令|角色指令` 同口径（局部数量「派三个 Agent 并行」不碰）。
2. `N 项|条 核心约定` / `核心约定 N 项|条` / `核心约定 1–N` —— 真值 = 核心约定正文最大约定号。

不碰「N 个命令 / N 个 SKILL」：文档里这类中文数字几乎全是**子集**（「四个命令对应的 SKILL」），
没有可机器区分的「总数」措辞，强判必误报。真值取不到（无 agents 目录等）→ 该类跳过。

数字写法：一二三…九、十、十一…九十九、一百零五（`两` 视同 2）。

## 适用范围

仅**模板仓库**（根有 `版本变更历史.md`）：下游文档里的「共三个 Agent」多半在讲业务自己的东西，
与契约的角色数无关。非模板仓库输出 `applicable: false`、退出 0（verify.py 记 N/A）。

## 豁免

沿用 `check_count_claims.py` 的显式标记 `<!-- countclaim-check: ignore -->`（行）/
`ignore-file 理由` / `ignore-begin 理由` … `ignore-end`。扫描面同它：全仓 `.md`，不下钻
`skills/`（SKILL 本体 + bundle 镜像）与 `.aidp-backup-*`，另不扫 `memory/.aidp/` 运行态副本。

## 用法

    python3 AIDP_HOME/scripts/check_cn_count_claims.py [--root .] [--json] [--self-check]

退出码：0 = 一致；1 = 有过期中文计数；2 = 用法/读取错。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

_scripts = str(Path(__file__).resolve().parent)
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)
from aidp_runtime import runtime_text
import check_count_claims as CC

_D = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
      "六": 6, "七": 7, "八": 8, "九": 9}
CN = r"[零〇一二两三四五六七八九十百]+"
ROLE_RE = re.compile(r"(?P<a>" + CN + r")\s*份\s*(?:角色|Agent)"
                     r"|共\s*\*{0,2}(?P<b>" + CN + r")\s*个\s*(?:角色|Agent)"
                     r"|(?P<c>" + CN + r")\s*个\s*Agent\s*(?:角色)?指令"
                     r"|(?P<d>" + CN + r")\s*个\s*角色指令")
CONV_RE = re.compile(r"(?P<a>" + CN + r")\s*[项条]\s*核心约定"
                     r"|核心约定\s*(?P<b>" + CN + r")\s*[项条]"
                     r"|核心约定\s*1\s*[–—\-]\s*(?P<c>" + CN + r")")


def cn2int(s: str):
    """中文数字 → int（支持到百位）；非法返回 None。"""
    s = s.strip()
    if not s:
        return None
    total, cur, seen = 0, 0, False
    for ch in s:
        if ch in _D:
            cur, seen = _D[ch], True
        elif ch == "十":
            total += (cur or 1) * 10
            cur, seen = 0, True
        elif ch == "百":
            total += (cur or 1) * 100
            cur, seen = 0, True
        else:
            return None
    return (total + cur) if seen else None


def _truths(root: str) -> dict:
    return {"agent": CC.truth_agents(root), "convention": CC.truth_max_convention(root)}


def scan_line(line: str, truths: dict):
    """逐处返回 (片段, 列, 类别, 声明值, 实际值)，仅含与真值不符者。"""
    out = []
    if truths.get("agent") is not None:
        for m in ROLE_RE.finditer(line):
            raw = next(m.group(k) for k in ("a", "b", "c", "d") if m.group(k))
            n = cn2int(raw)
            if n is None or n < 2 or n == truths["agent"]:
                continue
            out.append((m.group(0), m.start() + 1, "Agent 角色数", n, truths["agent"]))
    if truths.get("convention") is not None:
        for m in CONV_RE.finditer(line):
            raw = next(m.group(k) for k in ("a", "b", "c") if m.group(k))
            n = cn2int(raw)
            if n is None or n < 2 or n == truths["convention"]:
                continue
            out.append((m.group(0), m.start() + 1, "核心约定数", n, truths["convention"]))
    return out


def _walk(root: str):
    for p in CC._walk(root):
        if p.endswith(".md"):
            yield p


def run(root: str) -> dict:
    if not os.path.isfile(os.path.join(root, "版本变更历史.md")):
        return {"applicable": False, "reason": "非模板仓库（根无 版本变更历史.md）",
                "truths": {}, "scanned": 0, "cn_count_claims": 0, "violations": []}
    truths = _truths(root)
    violations, scanned, claims = [], 0, 0
    for path in sorted(set(_walk(root))):
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        if rel.startswith("memory/.aidp/"):
            continue
        text = CC._read(path)
        if text is None or CC.IGNORE_FILE_RE.search(text):
            continue
        scanned += 1
        in_ignore = False
        for i, line in enumerate(text.split("\n"), 1):
            if CC.IGNORE_BEGIN_RE.search(line):
                in_ignore = True
            elif CC.IGNORE_END_RE.search(line):
                in_ignore = False
            if in_ignore or CC.IGNORE_LINE_RE.search(line):
                continue
            claims += len(ROLE_RE.findall(line)) + len(CONV_RE.findall(line))
            for snippet, col, kind, decl, actual in scan_line(line, truths):
                violations.append({"file": rel, "line": i, "col": col, "snippet": snippet,
                                   "kind": kind, "declared": decl, "actual": actual,
                                   "detail": f"{kind}声明「{snippet}」= {decl}，实际 {actual}"})
    return {"truths": truths, "scanned": scanned, "cn_count_claims": claims, "violations": violations}


def self_check() -> bool:
    root = Path(tempfile.mkdtemp(prefix="aidp-cncount-check-"))
    try:
        agents = root / runtime_text("__AIDP_HOME__/agents", __file__)
        agents.mkdir(parents=True)
        for i in range(3):
            (agents / f"r{i}.md").write_text("x\n", encoding="utf-8")
        (root / "版本变更历史.md").write_text("x\n", encoding="utf-8")
        (root / "bad.md").write_text("本目录下的九份角色指令\n", encoding="utf-8")
        (root / "good.md").write_text("三份角色指令；派九个 Agent 并行；<!-- x -->\n", encoding="utf-8")
        got = [v["file"] for v in run(str(root))["violations"]]
        return got == ["bad.md"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="中文数字自称计数与实数一致")
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-check", action="store_true")
    args = ap.parse_args(argv)
    if args.self_check:
        ok = self_check()
        print(json.dumps({"self_check": "pass" if ok else "fail"}, ensure_ascii=False))
        return 0 if ok else 1
    try:
        res = run(args.root)
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"error": str(e)}, ensure_ascii=False) if args.json else f"[ERROR] 检查执行失败：{e}")
        return 2
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    elif res.get("applicable") is False:
        print(f"[N/A] {res['reason']}")
    elif res["violations"]:
        print(f"[FAIL] 检出 {len(res['violations'])} 处过期中文计数（真值 {res['truths']}）：")
        for v in res["violations"]:
            print(f"  · {v['file']}:{v['line']}:{v['col']}  {v['detail']}")
        print("  修复：改成实际值；确属讲历史 → 加 `<!-- countclaim-check: ignore -->`。")
    else:
        print(f"[OK] 中文数字自称计数与实际一致（巡检 {res['scanned']} 份 .md，命中 {res['cn_count_claims']} 处）")
    return 1 if res["violations"] else 0


if __name__ == "__main__":
    sys.exit(main())
