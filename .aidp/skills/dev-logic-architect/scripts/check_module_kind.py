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
  K2 module_kind_missing      —— 某个模块标题下的 `>` 元信息块没写 `**模块类型**: <取值>`
  K3 module_kind_invalid      —— 取值不在枚举内(不带括注 / 说明,逐字匹配)
  K4 fr_outside_module        —— B.1 里出现在任何模块分组之前的功规点(它归属哪个模块无从判定)
只认 B.1 章节范围内的模块标题;多文件模式下文件名含「功规点实现映射」的分册整份都算 B.1。
既无 B.1 章节也无模块标题 → `skipped: true`(⚠️ 不等于通过)。部分文件读不出 → 继续,列进
`read_errors[]`(⚠️ 非空时 modules 是残缺样本)。

退出码:0 = 无问题,或只有 Important(未加 --strict),或 N/A 跳过 / 1 = --strict 下有 Important 或有 read_errors /
2 = 入参错(路径不存在、全部文件读不出)。
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
# 写法:详细设计 B.1 按业务模块分组,每组一个 `模块: <模块名>` 标题(可带编号前缀 `1.` / `B.1.1`),
#   标题下方 `>` 元信息块写 `> **模块类型**: 批处理`(同行多字段 `| **模块类型**: …`、`**模块类型:**` 都认)。
# 取值必须**逐字**是下面两组之一(不带括注、不带说明);⛔ 不根据模块名或「页面少」推断。
# 非交互组与 dev-manual-testcase `flow-scale-control.md` 第五节的枚举一一对应。
# 只认 **B.1 章节范围内**的模块标题:B.1 标题(`B.1` 或「功规点实现映射」,H1~H6)起,到下一个
#   `A.N`/`C.N`… 主模块标题或 `Module X` 为止;多文件模式下文件名含「功规点实现映射」则整份都算。
#   ⛔ 不按标题层级判 B.1 结束 —— 模板里功规点标题层级常高于 B.1 标题,按层级会把 B.1 提前截断。
MODULE_KIND_INTERACTIVE = ("页面", "接口服务")
MODULE_KIND_NON_INTERACTIVE = ("迁移工具", "数据迁移", "数据脚本", "批处理", "定时任务", "CLI", "命令行工具")
MODULE_HEAD_RE = re.compile(r"^#{1,6}\s+(?:[0-9A-Za-z.、)）]+\s*)?模块\s*[:：]\s*(\S.*?)\s*$")
MODULE_KIND_RE = re.compile(r"\*\*模块类型(?:\*\*\s*[:：]|\s*[:：]\s*\*\*)\s*([^|]*?)\s*(?:\||$)")
B1_HEAD_RE = re.compile(r"^#{1,6}\s.*?(?:(?<![\w.])B\.1(?![.\d])|功规点实现映射)")
B1_END_RE = re.compile(r"^#{1,6}\s+(?:(?<![\w.])[A-E]\.\d+(?![.\d])|Module\s+[A-E]\b)")
FR_HEAD_RE = re.compile(r"^#{1,6}\s+(FR-\d+)")
ANY_HEAD_RE = re.compile(r"^#{1,6}\s")


def parse_module_kinds(text, whole_file_b1=False):
    """返回 {"has_b1", "modules": [{name, kind, line}], "orphan_frs": [{fr, line}]}。

    kind 为 None = 该模块标题下没写「模块类型」;orphan_frs = B.1 内出现在任何模块分组之前的功规点。
    代码围栏内的一律不算。
    """
    out = {"has_b1": whole_file_b1, "modules": [], "orphan_frs": []}
    in_b1, cur, meta, in_fence = whole_file_b1, None, False, False
    for n, ln in enumerate(text.splitlines(), 1):
        s = ln.strip()
        if s.startswith("```") or s.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if ANY_HEAD_RE.match(ln):
            meta = False
            if B1_HEAD_RE.match(ln):
                in_b1, cur, out["has_b1"] = True, None, True
                continue
            if B1_END_RE.match(ln) and not whole_file_b1:
                in_b1, cur = False, None
                continue
            if not in_b1:
                continue
            m = MODULE_HEAD_RE.match(ln)
            if m:
                cur = {"name": m.group(1), "kind": None, "line": n}
                out["modules"].append(cur)
                meta = True
                continue
            fr = FR_HEAD_RE.match(ln)
            if fr and cur is None:
                out["orphan_frs"].append({"fr": fr.group(1), "line": n})
            continue
        if not meta or not s:
            continue
        if not s.startswith(">"):
            meta = False
            continue
        k = MODULE_KIND_RE.search(s)
        if k and cur["kind"] is None:
            cur["kind"] = k.group(1).strip("`").strip()
    return out
# <<< SHARED-SEGMENT: module-kind-enum <<<


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
    modules, findings, read_errors, has_b1 = [], [], [], False
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            read_errors.append({"file": str(f), "error": str(exc)})
            continue
        res = parse_module_kinds(text, whole_file_b1="功规点实现映射" in f.name)
        has_b1 = has_b1 or res["has_b1"]
        for fr in res["orphan_frs"]:
            findings.append({"level": "Important", "type": "fr_outside_module", "file": f"{f}:{fr['line']}",
                             "msg": f"功规点 {fr['fr']} 不在任何「模块: <名称>」分组下,无法判定其模块类型"})
        for m in res["modules"]:
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
    if files and len(read_errors) == len(files):
        print(f"全部 {len(files)} 个文件读不出: {read_errors[0]['error']}", file=sys.stderr)
        return 2
    if has_b1 and not modules:
        # 一个分组都没有时只报 K1:否则每个功规点再各报一条 K4,同一缺口被重复计数
        findings = [x for x in findings if x["type"] != "fr_outside_module"]
        findings.append({"level": "Important", "type": "module_inventory_missing", "file": str(target),
                         "msg": "有 B.1 功规点实现映射,但 B.1 内没有任何「模块: <名称>」分组标题,下游无法逐模块判定交互形态"})
    skipped = not has_b1 and not modules and not read_errors
    out = {"skipped": skipped, "files_scanned": len(files) - len(read_errors),
           "modules": [{k: m[k] for k in ("name", "kind", "file", "line")} for m in modules],
           "findings": findings, "read_errors": read_errors}
    if args.json:
        print(json.dumps(out, ensure_ascii=False))
    elif skipped:
        print("⚠️ 未识别到 B.1 功规点章节与模块分组,跳过(不等于通过)")
    else:
        for e in read_errors:
            print(f"⚠️ 读不出: {e['file']} ({e['error']})")
        if findings:
            print(f"🟡 {len(findings)} 项 Important:")
            for it in findings:
                print(f"  [{it['type']}] {it['file']}  {it['msg']}")
        else:
            print(f"✅ {len(modules)} 个模块均已声明模块类型")
    return 1 if read_errors or (args.strict and findings) else 0


if __name__ == "__main__":
    sys.exit(main())
