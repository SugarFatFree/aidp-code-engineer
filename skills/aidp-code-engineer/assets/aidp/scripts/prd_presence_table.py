#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""研发需求「表 D：PRD 条目映射表」→ 研发自测「PRD 行 → 研发需求对账表」（确定性转换）。

`dev-manual-testcase` 在 `prd_presence_mode=table` 时不再逐行写 `[PRD存在性]` 用例，只对编排层给的
对账表里「未承接」的行补用例（四列契约见该 SKILL `references/flow-scale-control.md` 第四节）。

★ 本脚本**不另立一套 PRD 覆盖判据**：PRD 条目 → 研发需求的反向覆盖由 `ux-logic-extractor` 在需求阶段
产出表 D、并由它的 `check_prd_item_coverage.py`（机器门，任何 QR 档位都全量跑）判 100% 分类。
这里只把那张已过门的表**换个形状**交给下游，两处判据各自演进就会出现「需求阶段说全覆盖、
用例阶段说有漏」的互相矛盾。

转换口径：
  · 行号 = `<PRD 文件名>:L<行>`（取自表 D「PRD 位置」里的 `文件.md:行`）——多份 PRD 不撞号；
    取不到行号的行用 `D<表内序号>`，并在 `rows_without_line` 里列出；
  · `已承接` / `已存在无需重复` → 已承接；处置为空或不在枚举内 → 未承接（兜底，正常已被需求阶段拦下）；
  · `本版不做` → **不进对账表**，单列在表外：产品明确不做的条目当成「未承接」，下游就会给它补
    「应该存在」的用例，方向正好相反。

用法：
  python3 prd_presence_table.py --root . --version V1.0.0 [--out <路径>] [--json]
  python3 prd_presence_table.py --self-check

退出码：0 = 已生成（或无表 D → 跳过，`skipped` 说明原因，此时下游按 cases 模式）/ 2 = 入参错。
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

D_COLS = ("PRD位置", "条目内容", "研发需求落点", "处置")
ACCEPTED = ("已承接", "已存在无需重复")
NOT_THIS_VERSION = "本版不做"
LOC_RE = re.compile(r"([^\s`|:：/\\]+\.(?:md|txt))\s*[:：]\s*L?(\d+)")
_UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")


def _cells(line):
    s = line.strip()
    s = s[1:] if s.startswith("|") else s
    s = s[:-1] if s.endswith("|") and not s.endswith("\\|") else s
    return [c.strip().replace("\\|", "|") for c in _UNESCAPED_PIPE.split(s)]   # 还原 GFM 的 `\|`，渲染时统一再转义


def _norm(text):
    return re.sub(r"[\s*`]", "", text)


def parse_table_d(text):
    """返回表 D 的数据行 [{loc, item, target, disposition}]；没有表 D 返回 None。"""
    lines = text.splitlines()
    for i, line in enumerate(lines[:-1]):
        if not line.lstrip().startswith("|"):
            continue
        head = [_norm(c) for c in _cells(line)]
        if not all(c in head for c in D_COLS):
            continue
        if not all(re.fullmatch(r"\s*:?-+:?\s*", c) for c in _cells(lines[i + 1])):
            continue
        idx = [head.index(c) for c in D_COLS]
        rows = []
        for raw in lines[i + 2:]:
            if not raw.lstrip().startswith("|"):
                break
            cells = _cells(raw)
            if len(cells) != len(head):
                continue
            loc, item, target, disp = (cells[k] for k in idx)
            rows.append({"loc": loc, "item": item, "target": target, "disposition": _norm(disp)})
        return rows
    return None


def build(root: Path, version: str) -> dict:
    req_dir = root / "docs" / "requirements" / version / "研发需求"
    rows, sources = [], []
    for path in sorted(req_dir.glob("*.md")) if req_dir.is_dir() else []:
        parsed = parse_table_d(path.read_text(encoding="utf-8", errors="replace"))
        if parsed is not None:
            rows.extend(parsed)
            sources.append(path.relative_to(root).as_posix())
    if not sources:
        return {"skipped": "no-table-d", "detail": "研发需求里没有表 D（模式 A / 无产品 PRD），下游按 cases 模式"}
    table, excluded, without_line, seen = [], [], [], {}
    for n, row in enumerate(rows, 1):
        match = LOC_RE.search(row["loc"])
        rid = f"{match.group(1)}:L{match.group(2)}" if match else f"D{n}"
        if not match:
            without_line.append(rid)
        seen[rid] = seen.get(rid, 0) + 1
        if seen[rid] > 1:   # 同一行拆成多条表 D 条目时，键要能区分
            rid = f"{rid}#{seen[rid]}"
        if row["disposition"] == NOT_THIS_VERSION:
            excluded.append({"id": rid, "item": row["item"]})
            continue
        status = "已承接" if row["disposition"] in ACCEPTED else "未承接"
        table.append({"id": rid, "item": row["item"], "target": row["target"] or "—", "status": status})
    return {"sources": sources, "rows": table, "excluded_not_this_version": excluded,
            "rows_without_line": without_line,
            "unaccepted": sum(1 for r in table if r["status"] == "未承接")}


def _escape(text):
    return text.replace("|", "\\|").replace("\n", " ")


def render(result: dict, version: str) -> str:
    out = [f"# PRD 行 → 研发需求对账表（{version}）", "",
           "> 由 `prd_presence_table.py` 从研发需求「表 D」确定性转换，⛔ 不手改；表 D 变了就重新生成。",
           f"> 来源：{'、'.join(result['sources'])}", "",
           "| PRD 行号 | PRD 原文 | 承接 REQ | 状态 |", "| :- | :- | :- | :- |"]
    out += [f"| {r['id']} | {_escape(r['item'])} | {_escape(r['target'])} | {r['status']} |" for r in result["rows"]]
    if result["excluded_not_this_version"]:
        out += ["", "## 本版不做（不进对账表、不生成存在性用例）", ""]
        out += [f"- {r['id']}：{r['item']}" for r in result["excluded_not_this_version"]]
    return "\n".join(out) + "\n"


def self_check() -> bool:
    root = Path(tempfile.mkdtemp(prefix="aidp-prd-presence-"))
    try:
        empty = build(root, "V1.0.0")
        req = root / "docs/requirements/V1.0.0/研发需求"
        req.mkdir(parents=True)
        (req / "01_研发需求.md").write_text(
            "# 研发需求\n\n| PRD 位置 | 条目内容 | 研发需求落点 | 处置 |\n| :- | :- | :- | :- |\n"
            "| `产品需求.md:120` 操作描述表 | 列表工具栏「导出」操作 | 功规点 5.3 | 已承接 |\n"
            "| `产品需求.md:210` 迭代建议表 | 支持批量导出 Excel | — | 本版不做 |\n"
            "| `产品需求.md:60` | 用户姓名 | 通用组件 | 已存在无需重复 |\n"
            "| `附录.md:12` | 金额\\|单位 | | |\n"
            "| §3 散文 | 审批意见 | 功规点 6 | 已承接 |\n", encoding="utf-8")
        got = build(root, "V1.0.0")
        ids = {r["id"]: r["status"] for r in got["rows"]}
        return (empty.get("skipped") == "no-table-d"
                and ids == {"产品需求.md:L120": "已承接", "产品需求.md:L60": "已承接",
                            "附录.md:L12": "未承接", "D5": "已承接"}
                and [r["id"] for r in got["excluded_not_this_version"]] == ["产品需求.md:L210"]
                and got["rows_without_line"] == ["D5"] and got["unaccepted"] == 1
                and "金额\\|单位" in render(got, "V1.0.0"))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="表 D → PRD 行对账表")
    ap.add_argument("--root", default=".")
    ap.add_argument("--version")
    ap.add_argument("--out", help="缺省 docs/audit/{version}/PRD行对账表.md")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-check", action="store_true")
    args = ap.parse_args(argv)
    if args.self_check:
        ok = self_check()
        print(json.dumps({"self_check": "pass" if ok else "fail"}, ensure_ascii=False))
        return 0 if ok else 1
    if not args.version or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", args.version):
        ap.error("--version 必填且只能含字母数字、点、下划线、连字符")
    root = Path(args.root).resolve()
    if not root.is_dir():
        ap.error("--root 必须是目录")
    result = build(root, args.version)
    if "skipped" not in result:
        out = Path(args.out) if args.out else root / "docs" / "audit" / args.version / "PRD行对账表.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render(result, args.version), encoding="utf-8")
        result["table_path"] = out.as_posix()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif "skipped" in result:
        print(f"[SKIP] {result['detail']}")
    else:
        print(f"[OK] {result['table_path']}：{len(result['rows'])} 行（未承接 {result['unaccepted']}），"
              f"本版不做 {len(result['excluded_not_this_version'])} 条不入表")
    return 0


if __name__ == "__main__":
    sys.exit(main())
