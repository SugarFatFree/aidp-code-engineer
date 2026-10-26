#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""详细设计「模块类型」字段检查(B.1 按业务模块分组时,每个模块须声明交互形态)。

下游 dev-manual-testcase 的 `module_kind=auto` 逐模块读这个字段,决定按页面模板还是非交互模板
(命令 / 前置数据 / 预期退出码 / 输出断言)写自测用例;缺字段时下游只能一律按页面模板写,
批处理 / 迁移工具类模块就会被写成「打开浏览器、点菜单」的假用例。规则见
references/output-module-examples.md「B.1 功规点实现映射」的模块分组与本文件下方共享段。

  python check_module_kind.py <详细设计文件或目录> [--json] [--strict]

判据(均 Important,⚠️ 严重度不占退出码):
  K1 module_inventory_missing —— 有 B.1 功规点章节,却一个 `模块: <名称>` 分组标题都没有
  K2 module_kind_missing      —— 某个模块标题下没写 `> **模块类型**: <取值>`
  K3 module_kind_invalid      —— 取值不在枚举内(不带括注 / 说明,逐字匹配)
既无 B.1 章节也无模块标题 → `skipped: true`(⚠️ 不等于通过)。

退出码:0 = 无问题,或只有 Important(未加 --strict),或 N/A 跳过 / 1 = --strict 下有 Important /
2 = 入参错(路径不存在、文件读不出)。
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

B1_HEAD_RE = re.compile(r"^#{2,6}\s*(?:B\.1(?![0-9])|.*功规点实现映射)")


def main() -> int:
    ap = argparse.ArgumentParser(description="详细设计「模块类型」字段检查")
    ap.add_argument("target", help="详细设计文件或目录")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true", help="Important 也计入退出码")
    args = ap.parse_args()

    target = Path(args.target)
    if not target.exists():
        print(f"路径不存在: {target}", file=sys.stderr)
        return 2
    files = [target] if target.is_file() else sorted(target.rglob("*.md"))
    modules, findings, has_b1 = [], [], False
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"读不出: {f} ({exc})", file=sys.stderr)
            return 2
        in_fence = False
        for ln in text.splitlines():
            if ln.strip().startswith(("```", "~~~")):
                in_fence = not in_fence
            elif not in_fence and B1_HEAD_RE.match(ln):
                has_b1 = True
        for m in parse_module_kinds(text):
            m["file"] = str(f)
            modules.append(m)
            loc = f"{f}:{m['line']}"
            if m["kind"] is None:
                findings.append({"level": "Important", "type": "module_kind_missing", "file": loc,
                                 "msg": f"模块「{m['name']}」未声明 > **模块类型**: <取值>"})
            elif m["kind"] not in MODULE_KIND_INTERACTIVE + MODULE_KIND_NON_INTERACTIVE:
                findings.append({"level": "Important", "type": "module_kind_invalid", "file": loc,
                                 "msg": f"模块「{m['name']}」的模块类型「{m['kind']}」不在枚举内:"
                                        + " / ".join(MODULE_KIND_INTERACTIVE + MODULE_KIND_NON_INTERACTIVE)})
    if has_b1 and not modules:
        findings.append({"level": "Important", "type": "module_inventory_missing", "file": str(target),
                         "msg": "有 B.1 功规点实现映射,但没有任何「模块: <名称>」分组标题,下游无法逐模块判定交互形态"})
    skipped = not has_b1 and not modules
    out = {"skipped": skipped, "modules": [{k: m[k] for k in ("name", "kind", "file", "line")} for m in modules],
           "findings": findings}
    if args.json:
        print(json.dumps(out, ensure_ascii=False))
    elif skipped:
        print("⚠️ 未识别到 B.1 功规点章节与模块分组,跳过(不等于通过)")
    elif findings:
        print(f"🟡 {len(findings)} 项 Important:")
        for it in findings:
            print(f"  [{it['type']}] {it['file']}  {it['msg']}")
    else:
        print(f"✅ {len(modules)} 个模块均已声明模块类型")
    return 1 if (args.strict and findings) else 0


if __name__ == "__main__":
    sys.exit(main())
