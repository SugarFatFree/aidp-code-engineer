#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全量设计 `全量/` 的**分册内 section 级前滚**支撑（Step 3.3.11 提速）。

## 为什么需要本脚本

3.3.11 的「变更范围增量」只到**专题层**：一个专题只要进了 Δ，就**从零重新合成整份分册**
（读旧全量 + 本版设计 + 全量需求 + 代码事实后重写整个文件）。于是"增量"只在专题**数量**上省，
专题**内容**上一分没省。

下游实测（V0.13.0 正式发布）：全量 6342 行，Δ 命中 4/5 个专题，**5245 行（83%）被重新合成**，
只前滚了唯一能靠 git diff 一眼判零 DDL 的那册。该步 41m49s / 551k tokens / 170 次工具调用，
占发布主体 54%、关键路径 72%。而这**不是特例**——凡"多域并行的正常版本"（6 个 Sprint 铺满
各领域）Δ 都会几乎全覆盖，增量必然退化为准全量。

## 本脚本做什么（只做机械部分）

- `scope`：切出各分册的 H2 章节清单 + 行数，算出**覆盖率报告**——「Δ 覆盖 N/M 专题、
  约 X% 行将被重算」。⛔ 这一行必须在重算**开始前**打印：否则执行体和用户都要等 40 分钟
  才发现"这次其实接近全量"，而那时已经没有改主意的机会了。
- `rollforward`：以**旧分册为底本**，只把指定章节替换成新内容，其余章节**原样保留**
  （按 `^## ` H2 切段）。

**哪些章节需要重写是语义判断，本脚本不猜**：由执行体按 Δ 映射决定后用 `--sections` 传入。
脚本只保证"没被点名的章节一个字节都不动"，并在结果里报告各章节的去向（rewritten/kept）。

## 用法

    design_full_rollforward.py scope --full-dir docs/design/detail/全量 --delta 01_详细设计,03_接口设计
    design_full_rollforward.py rollforward --old 全量/01_详细设计.md --new staging/01_详细设计.md \\
        --sections "接口清单,数据流" --out 全量/01_详细设计.md
"""
import argparse
import json
import os
import re
import sys

H2 = re.compile(r"^## ", re.M)


def split_sections(text):
    """按 `^## ` 切段 → [(title, body)]；首个 H2 之前的内容归入 title=None 的前言段。"""
    idxs = [m.start() for m in H2.finditer(text)]
    if not idxs:
        return [(None, text)]
    out = []
    if idxs[0] > 0:
        out.append((None, text[:idxs[0]]))
    for i, start in enumerate(idxs):
        end = idxs[i + 1] if i + 1 < len(idxs) else len(text)
        seg = text[start:end]
        title = seg.splitlines()[0][3:].strip()
        out.append((title, seg))
    return out


def scope(full_dir, delta):
    """覆盖率报告：Δ 命中哪些分册、涉及多少行、占全量多少。"""
    if not os.path.isdir(full_dir):
        return {"ok": False, "error": "full-dir-not-found", "path": full_dir}
    books, total, delta_lines = [], 0, 0
    for name in sorted(os.listdir(full_dir)):
        if not name.endswith(".md"):
            continue
        stem = os.path.splitext(name)[0]
        try:
            text = open(os.path.join(full_dir, name), encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        lines = text.count("\n") + 1
        secs = [{"title": t, "lines": b.count("\n") + 1} for t, b in split_sections(text)]
        hit = any(d.strip() and d.strip() in stem for d in delta)
        books.append({"book": stem, "lines": lines, "sections": secs, "in_delta": hit})
        total += lines
        if hit:
            delta_lines += lines
    pct = round(delta_lines * 100.0 / total, 1) if total else 0.0
    return {"ok": True, "books": books, "total_lines": total,
            "delta_books": sum(1 for b in books if b["in_delta"]), "book_count": len(books),
            "delta_lines": delta_lines, "delta_pct": pct}


def rollforward(old_path, new_path, sections, out_path):
    """以旧分册为底本，只替换点名章节；其余原样保留。"""
    try:
        old_text = open(old_path, encoding="utf-8").read()
    except OSError as e:
        return {"ok": False, "error": f"old-unreadable: {e}"}
    try:
        new_text = open(new_path, encoding="utf-8").read()
    except OSError as e:
        return {"ok": False, "error": f"new-unreadable: {e}"}
    want = {s.strip() for s in sections if s.strip()}
    new_map = {t: b for t, b in split_sections(new_text) if t}
    missing = sorted(want - set(new_map))
    if missing:
        return {"ok": False, "error": "sections-missing-in-new", "missing": missing,
                "hint": "点名要重写的章节必须在新内容里存在，否则会静默丢章节"}
    parts, report = [], []
    for title, body in split_sections(old_text):
        if title and title in want:
            parts.append(new_map[title])
            report.append({"section": title, "action": "rewritten"})
        else:
            parts.append(body)
            if title:
                report.append({"section": title, "action": "kept"})
    # 新分册里新增的章节（旧底本没有）追加到末尾，避免"新写的章节被静默丢掉"
    old_titles = {t for t, _ in split_sections(old_text) if t}
    for title, body in split_sections(new_text):
        if title and title not in old_titles and title in want:
            if parts and not parts[-1].endswith("\n\n"):
                parts.append("\n" if parts[-1].endswith("\n") else "\n\n")
            parts.append(body)
            report.append({"section": title, "action": "appended"})
    merged = "".join(parts)
    if out_path:
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(merged)
    kept = sum(1 for r in report if r["action"] == "kept")
    return {"ok": True, "out": out_path, "sections": report,
            "rewritten": len(report) - kept, "kept": kept,
            "old_lines": old_text.count("\n") + 1, "merged_lines": merged.count("\n") + 1}


def main():
    ap = argparse.ArgumentParser(description="全量设计分册内 section 级前滚（3.3.11 提速）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s1 = sub.add_parser("scope", help="Δ 覆盖率报告（重算前必打印）")
    s1.add_argument("--full-dir", required=True)
    s1.add_argument("--delta", default="", help="逗号分隔的 Δ 专题名（匹配分册文件名）")
    s2 = sub.add_parser("rollforward", help="以旧分册为底本只替换点名章节")
    s2.add_argument("--old", required=True); s2.add_argument("--new", required=True)
    s2.add_argument("--sections", required=True, help="逗号分隔的待重写 H2 标题")
    s2.add_argument("--out", default="")
    ap.add_argument("--json", action="store_true")
    # ★ `--json` 在子命令后面也要认：`… scope --full-dir X --json` 是最自然的写法，
    #   只挂全局位会让它报 `unrecognized arguments` —— 调用方（含执行体）会照直觉写在后面。
    for _s in (s1, s2):
        _s.add_argument("--json", dest="json_sub", action="store_true",
                        help="输出机读 JSON（与放在子命令前等效）")
    a = ap.parse_args()
    want_json = bool(a.json or getattr(a, "json_sub", False))

    if a.cmd == "scope":
        res = scope(a.full_dir, a.delta.split(","))
        if want_json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
            # ⛔ 退出码必须跟着 ok 走：只 print 就 return 0 会让 --json 调用方
            #    拿到「目录不存在」却看到 exit 0，是典型 fail-open。
            return 0 if res["ok"] else 2
        elif not res["ok"]:
            sys.stderr.write(f"❌ {res['error']}: {res.get('path')}\n"); return 2
        else:
            print(f"📐 Δ 覆盖 {res['delta_books']}/{res['book_count']} 个专题、"
                  f"{res['delta_lines']}/{res['total_lines']} 行将被重算（{res['delta_pct']}%）")
            if res["delta_pct"] >= 70:
                sys.stderr.write(
                    f"⚠️ 本次增量已接近全量（{res['delta_pct']}%）——按专题级重算会退化为准全量重写。"
                    f"请启用分册内 section 级前滚：只重写 Δ 命中的章节，其余用 rollforward 前滚。\n")
        return 0

    res = rollforward(a.old, a.new, a.sections.split(","), a.out)
    if want_json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    elif not res["ok"]:
        sys.stderr.write(f"❌ {res['error']}"
                         + (f"：{res.get('missing')}\n   {res.get('hint','')}\n" if res.get("missing") else "\n"))
        return 1
    else:
        print(f"✅ 前滚完成：重写 {res['rewritten']} 节 / 保留 {res['kept']} 节 "
              f"（{res['old_lines']} → {res['merged_lines']} 行）→ {res['out'] or '(stdout only)'}")
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
