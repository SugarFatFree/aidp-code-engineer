#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""module_kind=auto 的逐模块识别:从详细设计读每个模块的「模块类型」,给出交互 / 非交互结论。

规则见 references/flow-scale-control.md 第五节。本脚本只**读**,不判对错(产出侧的缺字段检查在上游详细设计侧)。

  python read_module_kinds.py <详细设计文件或目录> [--json]

输出:每个模块 {name, kind, interactive, file, line};字段缺失或取值不在枚举内 → `interactive: true`
(按页面模板写),并分别列进 `missing` / `invalid` 供 QR 子 Agent 报告。⛔ 不根据模块名推断。
一个模块标题都没有 → `modules: []` + `skipped: true`,即全部按页面模板(与 `interactive` 等价,⚠️ 不等于识别成功)。

退出码:0 = 已读取(含 skipped) / 2 = 入参错(路径不存在、文件读不出)。
"""
import argparse
import json
import re
import sys
from pathlib import Path

# >>> SHARED-SEGMENT: module-kind-enum >>>
# ── 模块类型字段(详细设计 → 自测用例 module_kind=auto 的跨产物契约)──────────────────
# ⚠️⚠️ 本段在两个 SKILL 的脚本里各持一份逐字节相同的副本(遵 SKILL 独立性:不得跨 SKILL 引用):
#      · dev-logic-architect/scripts/check_module_kind.py   (产出侧:缺字段/取值非法 → Important)
#      · dev-manual-testcase/scripts/read_module_kinds.py   (消费侧:module_kind=auto 逐模块识别)
#      改一处必须两处同改 —— 仓库级硬门 `scripts/check_shared_segment_sync.py` 逐字节比对。
#
# 写法:详细设计 B.1 按业务模块分组,每组一个 `模块: <模块名>` 标题,标题下方元信息块写
#   > **模块类型**: 批处理
# 取值必须**逐字**是下面两组之一(不带括注、不带说明);⛔ 不根据模块名或「页面少」推断。
# 非交互组与 dev-manual-testcase `flow-scale-control.md` 第五节的枚举一一对应。
MODULE_KIND_INTERACTIVE = ("页面", "接口服务")
MODULE_KIND_NON_INTERACTIVE = ("迁移工具", "数据迁移", "数据脚本", "批处理", "定时任务", "CLI", "命令行工具")
MODULE_HEAD_RE = re.compile(r"^#{2,6}\s*模块\s*[:：]\s*(\S.*?)\s*$")
MODULE_KIND_RE = re.compile(r"^>\s*\*\*模块类型\*\*\s*[:：]\s*(.*?)\s*$")
ANY_HEAD_RE = re.compile(r"^#{1,6}\s")


def parse_module_kinds(text):
    """返回 [{name, kind, line}];kind 为 None 表示该模块标题下没写「模块类型」。代码围栏内的一律不算。"""
    modules, cur, in_fence = [], None, False
    for n, ln in enumerate(text.splitlines(), 1):
        s = ln.strip()
        if s.startswith("```") or s.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = MODULE_HEAD_RE.match(ln)
        if m:
            cur = {"name": m.group(1), "kind": None, "line": n}
            modules.append(cur)
            continue
        if ANY_HEAD_RE.match(ln):
            cur = None
            continue
        k = MODULE_KIND_RE.match(ln)
        if k and cur is not None and cur["kind"] is None:
            cur["kind"] = k.group(1).strip("`").strip()
    return modules
# <<< SHARED-SEGMENT: module-kind-enum <<<


def main() -> int:
    ap = argparse.ArgumentParser(description="读取详细设计各模块的模块类型(module_kind=auto)")
    ap.add_argument("target", help="详细设计文件或目录")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    target = Path(args.target)
    if not target.exists():
        print(f"路径不存在: {target}", file=sys.stderr)
        return 2
    files = [target] if target.is_file() else sorted(target.rglob("*.md"))
    modules = []
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"读不出: {f} ({exc})", file=sys.stderr)
            return 2
        for m in parse_module_kinds(text):
            m["interactive"] = m["kind"] not in MODULE_KIND_NON_INTERACTIVE
            m["file"] = str(f)
            modules.append(m)
    out = {
        "skipped": not modules,
        "modules": [{k: m[k] for k in ("name", "kind", "interactive", "file", "line")} for m in modules],
        "non_interactive": [m["name"] for m in modules if not m["interactive"]],
        "missing": [m["name"] for m in modules if m["kind"] is None],
        "invalid": [m["name"] for m in modules if m["kind"] is not None
                    and m["kind"] not in MODULE_KIND_INTERACTIVE + MODULE_KIND_NON_INTERACTIVE],
    }
    if args.json:
        print(json.dumps(out, ensure_ascii=False))
    elif not modules:
        print("⚠️ 详细设计里没有「模块: <名称>」分组标题:全部按页面模板(不等于识别成功)")
    else:
        for m in modules:
            tag = "非交互" if not m["interactive"] else "页面"
            print(f"  {tag:<4} {m['name']}  (模块类型: {m['kind'] or '未声明'})")
        if out["missing"] or out["invalid"]:
            print(f"⚠️ 未声明 {len(out['missing'])} 个 / 取值非法 {len(out['invalid'])} 个,已按页面模板处理")
    return 0


if __name__ == "__main__":
    sys.exit(main())
