#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""autopilot_design_placeholders.py — 详细设计里「清单外维度占位」的确定性扫描门（只读）。

## 为什么需要本脚本

`dev-logic-architect` 在无人值守预确认分支下，对 `tech_boundary` 清单之外的栈维度（ORM / 连接池 /
序列化 / 实时通信 …）**不得自编暂行默认值**：设计正文写 `{待用户填写: <维度>}`，并在
`99_待澄清问题清单.md` 登记 D-NNN「⏳ 待确认」。而 `dev-execution-planner` 又规定「详细设计不明确的
Task 必须标『⚠️ 设计待澄清』并暂停实施」。无人值守链路上没有任何一步消费这些占位：
要么「暂停实施」无人接手（既不失败也不推进，拖到 stuck-phase 熔断才被发现），要么开发 Agent 自行补栈
（违反用户主权）——这是新入参接线后的真空带。

本脚本给它一个**确定性出口**：扫 `docs/design/detail/{V}/**/*.md` 里的 `{待用户填写: <维度>}`，
命中即 rc=1，并列出维度与所在文件。调用方：

  · `/sprint-autopilot` Phase 3.1ter（规划之后、开发之前）：无人值守命中 → 冻结 `prd-missing`
    （选冻结而非「对该维度 Task 标 skipped」：skipped 会让功能静默缺失、且没有可机检的「该 Task 依赖哪个
    维度」映射；冻结一次后由人补声明，补完按 mtime 证据自动解冻，不会空转）；
  · `/sprint-plan` Step 1：命中 → 只告知与登记，不阻断（planner 自己会标「设计待澄清」）。

## 用法

    autopilot_design_placeholders.py --version V0.2.0 [--root .] [--json] [--self-check]

退出码：0 = 无占位（或无设计目录）；1 = 有占位；2 = 用法错。
"""
import argparse
import json
import os
import re
import shutil
import sys
import tempfile

PLACEHOLDER_RE = re.compile(r"\{待用户填写[:：]\s*([^}\n]*)\}")


def scan(root, version):
    """→ {"dimensions": [{"dimension", "files": [...]}], "total": N}（无设计目录 → 空）。"""
    base = os.path.join(root, "docs", "design", "detail", version)
    by_dim = {}
    total = 0
    if os.path.isdir(base):
        for cur, _dirs, files in os.walk(base):
            for fn in sorted(files):
                if not fn.endswith(".md"):
                    continue
                path = os.path.join(cur, fn)
                try:
                    with open(path, encoding="utf-8", errors="replace") as fh:
                        text = fh.read()
                except OSError:
                    continue
                rel = os.path.relpath(path, root).replace(os.sep, "/")
                for m in PLACEHOLDER_RE.finditer(text):
                    dim = m.group(1).strip() or "(未命名维度)"
                    total += 1
                    files_of = by_dim.setdefault(dim, [])
                    if rel not in files_of:
                        files_of.append(rel)
    return {"version": version, "total": total,
            "dimensions": [{"dimension": d, "files": f} for d, f in sorted(by_dim.items())]}


def summary_line(res):
    dims = "、".join(x["dimension"] for x in res["dimensions"])
    return "设计含 %d 处清单外维度占位 {待用户填写}（维度：%s）" % (res["total"], dims)


def _self_check():
    d = tempfile.mkdtemp()
    ok = []
    try:
        ok.append(("无设计目录 → 无占位", scan(d, "V1.0.0")["total"] == 0))
        base = os.path.join(d, "docs", "design", "detail", "V1.0.0")
        os.makedirs(os.path.join(base, "sub"))
        with open(os.path.join(base, "01.md"), "w", encoding="utf-8") as fh:
            fh.write("ORM：{待用户填写: ORM}\n连接池：{待用户填写：连接池}\n")
        with open(os.path.join(base, "sub", "99_待澄清问题清单.md"), "w", encoding="utf-8") as fh:
            fh.write("| D-001 | ORM | {待用户填写: ORM} | ⏳ 待确认 |\n")
        res = scan(d, "V1.0.0")
        ok.append(("★ 阳性：命中 3 处、2 个维度（含子目录与全角冒号）",
                   res["total"] == 3 and [x["dimension"] for x in res["dimensions"]] == ["ORM", "连接池"]))
        with open(os.path.join(base, "01.md"), "w", encoding="utf-8") as fh:
            fh.write("ORM：MyBatis-Plus\n")
        os.remove(os.path.join(base, "sub", "99_待澄清问题清单.md"))
        ok.append(("★ 阴性：占位被替换后 → 0", scan(d, "V1.0.0")["total"] == 0))
    finally:
        shutil.rmtree(d, ignore_errors=True)
    for name, r in ok:
        print(("  ✅ " if r else "  ❌ FAIL: ") + name)
    return 0 if all(r for _, r in ok) else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="详细设计清单外维度占位扫描门（只读）")
    ap.add_argument("--version")
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-check", action="store_true")
    a = ap.parse_args(argv)
    if a.self_check:
        return _self_check()
    if not a.version:
        ap.error("--version 必填")
    res = scan(os.path.abspath(a.root), a.version)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    elif res["total"]:
        print("⚠️ " + summary_line(res))
        for x in res["dimensions"]:
            print("  - %s：%s" % (x["dimension"], "、".join(x["files"])))
    return 1 if res["total"] else 0


if __name__ == "__main__":
    sys.exit(main())
