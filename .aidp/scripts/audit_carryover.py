#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""version-auditor「上轮未处置项结转 + 连续 3 轮自动升级 Critical」的确定性计算与回检。

承载 `agents/version-auditor.md`「六bis」的机械部分：读上一份审计报告「十·修复建议」表，
轮次 +1、阈值升级、渲染「十二」章、回检本轮报告的轮次与升级标记。
**「本轮是否仍是同一个问题」是语义判断，脚本不猜**——由审计 Agent 用 `--still-open` 传入仍成立的编号。

子命令（均默认人读输出，`--json` 输出结构化结果）：
  carry --audit-dir <docs/audit/{version}> [--exclude <本轮报告文件>] [--prev <上轮报告>]
        [--still-open I-02,I-05] [--threshold 3] [--json]
      上轮可结转候选（Important / Warning，及上轮已升级且仍未处置者）+ 结转后的轮次 / 升级判定 / 「十二」章表格。
      不传 `--still-open` 只列候选与「若仍成立」的结果；传了才产出 carried / dropped / 渲染表。
  check --audit-dir <dir> --report <本轮报告> [--prev <上轮报告>] [--threshold 3] [--json]
      回检本轮报告：沿用编号的轮次必须 = 上轮 + 1；Important 达阈值必须标升级；
      「十二」章缺失 / 上轮候选与本轮零重合 → WARN（重新编号会让计数永远归 1，且看起来一切正常）。

上一份报告 = `version-output-audit-*.md` 中修改时间最新者（并列按文件名），`--prev` 可显式指定。
退出码：0 = 通过（含仅 WARN）；1 = `check` 有 ERROR；2 = 用法错 / 目录或报告不存在。
"""
import argparse
import glob
import json
import os
import re
import sys

REPORT_GLOB = "version-output-audit-*.md"
LEVEL_RE = re.compile(r"Critical|Important|Warning", re.I)
HEADING10_RE = re.compile(r"^#{1,6}\s*十[、.．\s]")
HEADING12_RE = re.compile(r"^#{1,6}\s*十二[、.．\s]")
ESCALATED_MARK = "⬆️"


def _cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _is_sep(line):
    return bool(re.match(r"^\s*\|?\s*:?-{2,}", line)) and set(line.strip()) <= set("|-: ")


def _section_table(lines, heading_re):
    """返回 heading 之后第一张表的 (header_cells, [row_cells])；无则 None。"""
    start = None
    for i, ln in enumerate(lines):
        if heading_re.match(ln):
            start = i + 1
            break
    if start is None:
        return None
    header, rows = None, []
    for ln in lines[start:]:
        if re.match(r"^#{1,6}\s", ln) and header is None:
            return None
        if re.match(r"^#{1,6}\s", ln):
            break
        if not ln.strip().startswith("|"):
            if header is not None and rows:
                break
            continue
        if _is_sep(ln):
            continue
        if header is None:
            header = _cells(ln)
        else:
            rows.append(_cells(ln))
    return (header, rows) if header else None


def _col(header, *names):
    for idx, cell in enumerate(header):
        if any(n in cell for n in names):
            return idx
    return None


def parse_findings(path):
    """解析「十·修复建议」表 → [{id, level, rounds, escalated}]。无表返回 None。"""
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    table = _section_table(lines, HEADING10_RE)
    if table is None:
        return None
    header, rows = table
    i_id, i_lv, i_rd = _col(header, "编号"), _col(header, "优先级"), _col(header, "连续未处置", "轮次")
    if i_id is None or i_lv is None:
        return None
    out = []
    for cells in rows:
        if len(cells) <= max(i_id, i_lv):
            continue
        fid = re.sub(r"[`*\s]", "", cells[i_id])
        if not fid:
            continue
        lv_cell = cells[i_lv]
        rd_cell = cells[i_rd] if i_rd is not None and i_rd < len(cells) else ""
        m = LEVEL_RE.search(lv_cell)
        n = re.search(r"\d+", rd_cell)
        out.append({
            "id": fid,
            "level": m.group(0).capitalize() if m else "",
            "rounds": int(n.group(0)) if n else 1,
            "escalated": ESCALATED_MARK in (lv_cell + rd_cell) or "升级" in rd_cell,
        })
    return out


def has_chapter12(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return any(HEADING12_RE.match(ln) for ln in f.read().splitlines())


def latest_report(audit_dir, exclude=None):
    ex = os.path.abspath(exclude) if exclude else None
    files = [p for p in glob.glob(os.path.join(audit_dir, REPORT_GLOB)) if os.path.abspath(p) != ex]
    if not files:
        return None
    return max(files, key=lambda p: (os.stat(p).st_mtime_ns, os.path.basename(p)))


def candidates(prev_rows):
    """上轮可结转：Important / Warning；已升级为 Critical 且仍标轮次者按 Important 继续计。"""
    out = []
    for r in prev_rows:
        lv = r["level"]
        if lv in ("Important", "Warning"):
            out.append(dict(r, origin=lv))
        elif lv == "Critical" and r["escalated"]:
            out.append(dict(r, origin="Important"))
    return out


def judge(cand, threshold):
    rounds = cand["rounds"] + 1
    escalate = cand["origin"] == "Important" and rounds >= threshold
    return rounds, escalate


def _resolve_prev(args):
    if args.prev:
        if not os.path.isfile(args.prev):
            print("上轮报告不存在：%s" % args.prev, file=sys.stderr)
            sys.exit(2)
        return args.prev
    if not os.path.isdir(args.audit_dir):
        print("审计目录不存在：%s" % args.audit_dir, file=sys.stderr)
        sys.exit(2)
    return latest_report(args.audit_dir, getattr(args, "report", None) or getattr(args, "exclude", None))


def cmd_carry(args):
    prev = _resolve_prev(args)
    result = {"previous_report": prev, "candidates": [], "carried": [], "dropped": [],
              "unknown_ids": [], "escalations": [], "table_12": "无结转项"}
    if prev is None:
        _emit(args, result, "本版首次审计：无上轮报告，「十二」章写「无结转项」。")
        return 0
    rows = parse_findings(prev)
    if rows is None:
        print("上轮报告缺少可解析的「十·修复建议」表：%s" % prev, file=sys.stderr)
        return 2
    cands = candidates(rows)
    for c in cands:
        rounds, esc = judge(c, args.threshold)
        result["candidates"].append({"id": c["id"], "origin_level": c["origin"], "prev_rounds": c["rounds"],
                                     "rounds_if_still_open": rounds, "escalate_if_still_open": esc})
    if args.still_open is not None:
        wanted = [x.strip() for x in args.still_open.split(",") if x.strip()]
        by_id = {c["id"]: c for c in cands}
        result["unknown_ids"] = [w for w in wanted if w not in by_id]
        table = ["| 编号 | 首次出现 | 原优先级 | 连续未处置轮次 | 本轮判定 |", "|------|---------|---------|---------------|---------|"]
        for c in cands:
            if c["id"] not in wanted:
                result["dropped"].append(c["id"])
                continue
            rounds, esc = judge(c, args.threshold)
            result["carried"].append({"id": c["id"], "origin_level": c["origin"], "rounds": rounds, "escalated": esc})
            if esc:
                result["escalations"].append(c["id"])
            verdict = ("%s **升级为 Critical**（连续 %d 轮未处置）" % (ESCALATED_MARK, rounds)) if esc else \
                "维持 %s%s" % (c["origin"], "（再拖 %d 轮升级）" % (args.threshold - rounds)
                                  if c["origin"] == "Important" else "，Warning 不升级")
            table.append("| %s | `%s` | %s | %d | %s |" % (c["id"], os.path.basename(prev), c["origin"], rounds, verdict))
        result["table_12"] = "\n".join(table) if result["carried"] else "无结转项"
    _emit(args, result, None)
    return 0


def _emit(args, result, note):
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if note:
        print(note)
        return
    print("上轮报告：%s" % result["previous_report"])
    for c in result["candidates"]:
        print("  候选 %s（%s，上轮 %d 轮）→ 若仍成立：%d 轮%s" % (
            c["id"], c["origin_level"], c["prev_rounds"], c["rounds_if_still_open"],
            "，⬆️ 升级 Critical" if c["escalate_if_still_open"] else ""))
    if result["unknown_ids"]:
        print("⚠️ --still-open 含上轮不存在的编号：%s" % ", ".join(result["unknown_ids"]))
    if result["carried"] or result["dropped"]:
        print("\n「十二」章：\n%s" % result["table_12"])


def cmd_check(args):
    if not os.path.isfile(args.report):
        print("本轮报告不存在：%s" % args.report, file=sys.stderr)
        return 2
    prev = _resolve_prev(args)
    errors, warns = [], []
    cur = parse_findings(args.report)
    if cur is None:
        warns.append("本轮报告缺少可解析的「十·修复建议」表（编号 / 优先级列），无法回检结转")
        cur = []
    if prev is None:
        res = {"previous_report": None, "errors": errors, "warnings": warns}
        _emit_check(args, res)
        return 0
    prev_rows = parse_findings(prev)
    cands = candidates(prev_rows or [])
    cur_by_id = {r["id"]: r for r in cur}
    overlap = 0
    for c in cands:
        r = cur_by_id.get(c["id"])
        if r is None:
            continue
        overlap += 1
        rounds, esc = judge(c, args.threshold)
        if r["rounds"] != rounds:
            errors.append("%s 沿用编号，连续未处置轮次应为 %d（上轮 %d + 1），报告写 %d"
                          % (c["id"], rounds, c["rounds"], r["rounds"]))
        if esc and not (r["escalated"] or r["level"] == "Critical"):
            errors.append("%s 连续 %d 轮未处置的 Important 必须标 %s 已升级为 Critical" % (c["id"], rounds, ESCALATED_MARK))
        if not esc and c["origin"] == "Warning" and (r["level"] == "Critical" or r["escalated"]):
            errors.append("%s 是 Warning，不得自动升级" % c["id"])
    if cands and overlap == 0:
        warns.append("上轮 %d 条可结转项在本轮零重合：若并非全部已解决而是重新编号，轮次计数会永远归 1（本机制静默失效）"
                     % len(cands))
    if cands and not has_chapter12(args.report):
        warns.append("上轮有 %d 条可结转候选，本轮报告缺「十二、上轮未处置项结转」章" % len(cands))
    res = {"previous_report": prev, "errors": errors, "warnings": warns}
    _emit_check(args, res)
    return 1 if errors else 0


def _emit_check(args, res):
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        for e in res["errors"]:
            print("[ERROR] " + e)
        for w in res["warnings"]:
            print("[WARN ] " + w)
        if not res["errors"] and not res["warnings"]:
            print("[OK] 结转轮次与升级标记一致（上轮：%s）" % (res["previous_report"] or "无"))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("carry", "check"):
        sp = sub.add_parser(name)
        sp.add_argument("--audit-dir", required=True)
        sp.add_argument("--prev")
        sp.add_argument("--threshold", type=int, default=3)
        sp.add_argument("--json", action="store_true")
        if name == "carry":
            sp.add_argument("--exclude", help="本轮将写入的报告文件（不作为上轮）")
            sp.add_argument("--still-open", help="仍成立的上轮编号，逗号分隔（语义判断由调用方给出）")
        else:
            sp.add_argument("--report", required=True)
    args = ap.parse_args(argv)
    return cmd_carry(args) if args.cmd == "carry" else cmd_check(args)


if __name__ == "__main__":
    sys.exit(main())
