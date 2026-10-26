#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把自测用例里的 `⟨PLAN-REF:REQ-xxx⟩` 占位符替换成研发执行计划链接(plan_ref_mode=deferred 的收尾)。

语法与规则见 references/flow-scale-control.md 第一节。本脚本由**编排层**在研发执行计划生成之后调用,
SKILL 自身在 deferred 模式下只写占位符、不调用它。

  python resolve_plan_refs.py <用例文件或目录> --map <映射.json> [--json]

映射 JSON:{"REQ-004": {"label": "Sprint-012 Task 2.3",
                        "href": "../plans/V1/01_研发执行计划.md#task-2-3"}, ...}
替换结果:`⟨PLAN-REF:REQ-004⟩` → `[Sprint-012 Task 2.3](../plans/V1/01_研发执行计划.md#task-2-3)`,
同一行里的其它文字(含分隔用的「、」)原样保留。
`href` 按**用例目录根**(传目录即该目录,传文件即其所在目录)计算;子目录里的用例由本脚本按各自位置
**词法重算**相对路径(不跟随软链),编排层不必按子目录拆分映射。替换后的形态与 S4 的既有写法相同,
`check_suite_upstream.py`(缺省 required 模式)与 `check_testcase_format.py` 照常校验。

映射由 dev-execution-planner 的 `export_plan_refs.py` 从执行计划**确定性导出**(label 与锚点都是计划原生的
`Sprint-NNN Task <Phase>.<序号>` / `#task-<phase>-<seq>`);⛔ 编排层不得自拟编号凑格式。

**全有或全无**:先扫全部文件,任何占位符在映射里找不到 → 一个文件都不写、exit 1(⛔ 不留半替换状态)。

退出码:0 = 已替换(或本来就没有占位符,`replaced: 0`) / 1 = 有占位符找不到映射 / 2 = 入参错
(路径不存在、映射不是合法 JSON、label 不是 `Sprint-NNN Task N.N`、href 是绝对路径或不是 `<相对路径>.md#task-N-N`)。
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

PLAN_REF_RE = re.compile(r"⟨PLAN-REF:([^⟩]*)⟩")
LABEL_RE = re.compile(r"^Sprint-\d+ Task \d+\.\d+$")
HREF_RE = re.compile(r"^[^#\s]+\.md#task-\d+-\d+$")
ABS_RE = re.compile(r"^(?:https?://|/|[A-Za-z]:[/\\]|~/)")


def load_map(path: Path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise ValueError(f"映射读不出或不是合法 JSON: {exc}")
    if not isinstance(data, dict):
        raise ValueError("映射必须是 {REQ: {label, href}} 对象")
    for req, v in data.items():
        if not isinstance(v, dict) or not isinstance(v.get("label"), str) \
                or not isinstance(v.get("href"), str):
            raise ValueError(f"{req}: 必须含字符串 label 与 href")
        if not LABEL_RE.match(v["label"]):
            raise ValueError(f"{req}: label 必须形如 `Sprint-NNN Task N.N`,实际 {v['label']!r}")
        if ABS_RE.match(v["href"]) or not HREF_RE.match(v["href"]):
            raise ValueError(f"{req}: href 必须是 `<相对路径>.md#task-N-N`,实际 {v['href']!r}")
    return data


def main() -> int:
    ap = argparse.ArgumentParser(description="替换 ⟨PLAN-REF:REQ-xxx⟩ 占位符为研发执行计划链接")
    ap.add_argument("target")
    ap.add_argument("--map", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    target = Path(args.target)
    if not target.exists():
        print(f"路径不存在: {target}", file=sys.stderr)
        return 2
    try:
        mapping = load_map(Path(args.map))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    files = [target] if target.is_file() else sorted(target.rglob("*.md"))
    root = os.path.abspath(target.parent if target.is_file() else target)
    pending, unmapped, replaced = {}, [], 0
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"读不出: {f} ({exc})", file=sys.stderr)
            return 2
        if "⟨PLAN-REF:" not in text:
            continue
        for n, ln in enumerate(text.splitlines(), 1):
            for req in PLAN_REF_RE.findall(ln):
                if req.strip() not in mapping:
                    unmapped.append({"file": str(f), "line": n, "req": req.strip()})

        fdir = os.path.dirname(os.path.abspath(f))

        def sub(m, fdir=fdir):
            v = mapping.get(m.group(1).strip())
            if not v:
                return m.group(0)
            path, frag = v["href"].split("#", 1)
            rel = os.path.relpath(os.path.normpath(os.path.join(root, path)), fdir).replace(os.sep, "/")
            return f"[{v['label']}]({rel}#{frag})"
        new, k = PLAN_REF_RE.subn(sub, text)
        replaced += k
        pending[f] = new

    out = {"replaced": 0 if unmapped else replaced,
           "files_changed": 0 if unmapped else len(pending), "unmapped": unmapped}
    if not unmapped:
        for f, new in pending.items():
            f.write_text(new, encoding="utf-8")
    if args.json:
        print(json.dumps(out, ensure_ascii=False))
    elif unmapped:
        print(f"❌ {len(unmapped)} 个占位符在映射里找不到,未写任何文件:")
        for u in unmapped[:20]:
            print(f"  {u['file']}:L{u['line']}  {u['req']}")
    else:
        print(f"✅ 已替换 {replaced} 个占位符,涉及 {len(pending)} 个文件")
    return 1 if unmapped else 0


if __name__ == "__main__":
    sys.exit(main())
