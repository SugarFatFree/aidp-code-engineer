#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文案与数据口径一致性采集脚本
(对应 code-verification-loop 维度 4「文案与数据口径一致性」子行 —— Critical)

本版改了语义/口径的展示位,其说明文案(tooltip / 表头注解 / 帮助文字 / 空态提示 等)
必须同步改写;若仍残留旧口径表述,会与实际展示值相反、误导用户对账。另外,被本版
「作废」的历史需求(见 ux-logic-extractor 表 F),其在代码注释里引用的旧 REQ 编号
若未标注失效,后续维护者会误把已作废需求当有效依据。本脚本按两条给定清单在前端/后端
代码里 grep,采集命中位置,供验收 Agent 语义判定。

两类采集(清单来自上游 ux-logic-extractor 表 E / 表 F,由 Agent 或调用方给定):
  ① 旧口径残留(--stale-phrases / --stale-phrases-file)
     来源 = 表 E「语义变更 → 派生展示物影响清单」中【处置=改写】行的「变更前语义」旧表述
            (如 "仅统计企业级" / "不含员工个人消费")。
     在代码里逐条 grep,命中即"改了口径的展示位仍残留旧口径表述"的嫌疑点。
     判定(Agent):命中处确属本版已改口径的展示位说明文案 → 🔴 Critical(回修复团队 Agent1)。

  ② 作废 REQ 编号注释失效标注(--stale-reqs / --stale-reqs-file)
     来源 = 表 F「历史需求作废清单」中【本版处置=作废】行的「需求编号」。
     逐条 grep,对每个命中行核验邻近(同行或 ±LINES 行)是否已带失效标注
            (如 "该需求已于 {version} 作废" / "已作废" / "废弃" / "失效" / "deprecated")。
     未带失效标注的命中 → 命中项(应补 "该需求已于 {version} 作废" 标注)。
     已带失效标注的命中 → 归入 annotated(合规、仅信息)。

与维度 4 其它行的边界:
  · 「字段/列对账」管展示列集合(缺/多/改名/换序)的字段级对账;
  · 维度 3.7 管接口出参字段结构变更后的"同一数据多消费点(主渲染路径+旁路)逐点适配";
  · 本脚本管"说明性文案的口径 ⟷ 实际取数/展示值一致性" + "作废 REQ 注释失效标注",互补不重叠。

清单文件格式(--*-file):每行一条,支持 # 行注释与空行,首尾空白自动裁剪。

扫描文件类型: .vue .ts .js .tsx .jsx .html .java .kt .go .py .sql .md
豁免目录:     node_modules .git dist build target out .next .nuxt vendor
              __pycache__ coverage .idea .vscode

退出码:
  0 = 默认(仅报告,命中与否都不判错;违规判定交给 Agent 结合表 E/表 F 语义核验)
  1 = 仅当 --strict 且存在命中(旧口径残留 或 未标注失效的作废 REQ)时返回,供 CI 卡口
  2 = 用法错误(未给任何清单)、目录不存在、或清单文件不存在

用法:
  # 旧口径残留(逗号分隔内联)
  python scan_stale_copy.py <代码目录> --stale-phrases "仅统计企业级,不含员工个人消费"
  # 作废 REQ(清单文件,每行一条)
  python scan_stale_copy.py <代码目录> --stale-reqs-file reqs.txt
  # 两类同时 + JSON + 严格
  python scan_stale_copy.py <代码目录> --stale-phrases-file p.txt --stale-reqs "REQ-2025-031" --json --strict

JSON 输出:
  {"stale_phrase_hits": [{"phrase":..,"file":..,"line":..,"snippet":..}],
   "stale_req_unmarked": [{"req":..,"file":..,"line":..,"snippet":..}],
   "stale_req_annotated": [{"req":..,"file":..,"line":..,"snippet":..,"marker":..}],
   "summary": {"phrase_hits": N, "req_unmarked": M, "req_annotated": K}}
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

# 扫描的源码/文案后缀(文案可能落在前端模板、后端注释、SQL 注解、文档)
SCAN_SUFFIXES = {
    ".vue", ".ts", ".js", ".tsx", ".jsx", ".html",
    ".java", ".kt", ".go", ".py", ".sql", ".md",
}

# 豁免目录段
EXCLUDED_DIRS = {
    "node_modules", ".git", "dist", "build", "target", "out",
    ".next", ".nuxt", "vendor", "__pycache__", ".idea", ".vscode",
    "coverage", ".nyc_output", "tmp", ".cache",
}

# 失效标注标记(命中作废 REQ 的行邻近若含其一,视为已标注失效)
INVALIDATION_MARKER = re.compile(
    r"作废|已废|废弃|失效|停用|不再使用|已下线|deprecated|obsolete|removed",
    re.IGNORECASE,
)

# 邻近扫描窗口(命中行上下各 N 行内找失效标注)
DEFAULT_NEIGHBOR_LINES = 2


def is_excluded(path: Path, root: Path) -> bool:
    """仅基于 root 以内的相对路径判断排除,避免项目位于含排除名祖先目录时被整体跳过。"""
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = path
    return bool(set(rel.parts) & EXCLUDED_DIRS)


def load_list(inline: Optional[str], file_path: Optional[Path]) -> List[str]:
    """合并 内联逗号分隔 + 清单文件(每行一条,# 注释/空行忽略)。"""
    items: List[str] = []
    if inline:
        items.extend(p.strip() for p in inline.split(",") if p.strip())
    if file_path:
        for raw in file_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            items.append(line)
    # 去重保序
    seen = set()
    uniq: List[str] = []
    for it in items:
        if it not in seen:
            seen.add(it)
            uniq.append(it)
    return uniq


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def scan_file(
    path: Path,
    root: Path,
    phrases: List[str],
    reqs: List[str],
    neighbor: int,
    phrase_hits: List[Dict],
    req_unmarked: List[Dict],
    req_annotated: List[Dict],
) -> None:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return
    rel = _rel(path, root)

    for idx, line in enumerate(lines):
        # ① 旧口径残留:子串匹配(文案是自然语言,literal 子串最稳)
        for ph in phrases:
            if ph in line:
                phrase_hits.append({
                    "phrase": ph,
                    "file": rel,
                    "line": idx + 1,
                    "snippet": line.strip()[:200],
                })
        # ② 作废 REQ 编号:子串匹配后,邻近窗口找失效标注
        for req in reqs:
            if req in line:
                # ⚠️ 窗口判定必须**排除串味**：作废 REQ 引用在代码里天然扎堆（同一段注释罗列多条
                #    历史需求），若只看「邻近 N 行内有没有失效标注」，相邻另一条 REQ 的标注会把
                #    本条也一并"洗白"进 🟢 合规桶 —— Agent 不再复查，维度 4 那条 Critical 就此漏掉。
                #    实测：两行各引一条作废 REQ、只有第二条带标注时，两条都被判合规。
                #    规则：① 同行命中标注 → 合规；② 仅窗口命中、且窗口里**没有其它清单内 REQ**
                #    → 合规；③ 窗口命中但混着别的 REQ → 归第三档 ambiguous，交人工确认。
                same_line = INVALIDATION_MARKER.search(line)
                lo = max(0, idx - neighbor)
                hi = min(len(lines), idx + neighbor + 1)
                window = "\n".join(lines[lo:hi])
                other_reqs = [r for r in reqs if r != req and r in window]
                m = same_line or INVALIDATION_MARKER.search(window)
                if m and not same_line and other_reqs:
                    m = None  # 串味：窗口里还有别的作废 REQ，标注归属不明
                rec = {
                    "req": req,
                    "file": rel,
                    "line": idx + 1,
                    "snippet": line.strip()[:200],
                }
                if m:
                    rec["marker"] = m.group(0)
                    req_annotated.append(rec)
                else:
                    req_unmarked.append(rec)


def scan(root: Path, phrases: List[str], reqs: List[str], neighbor: int) -> Dict:
    phrase_hits: List[Dict] = []
    req_unmarked: List[Dict] = []
    req_annotated: List[Dict] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SCAN_SUFFIXES:
            continue
        if is_excluded(path, root):
            continue
        scan_file(path, root, phrases, reqs, neighbor,
                  phrase_hits, req_unmarked, req_annotated)
    for lst in (phrase_hits, req_unmarked, req_annotated):
        lst.sort(key=lambda h: (h["file"], h["line"]))
    return {
        "stale_phrase_hits": phrase_hits,
        "stale_req_unmarked": req_unmarked,
        "stale_req_annotated": req_annotated,
        "summary": {
            "phrase_hits": len(phrase_hits),
            "req_unmarked": len(req_unmarked),
            "req_annotated": len(req_annotated),
        },
    }


def render_text(result: Dict, phrases: List[str], reqs: List[str]) -> str:
    out: List[str] = []
    out.append("=== 文案与数据口径一致性采集 (维度 4「文案与数据口径一致性」子行) ===")
    s = result["summary"]
    out.append(
        f"\n清单: 旧口径字样 {len(phrases)} 条 / 作废 REQ {len(reqs)} 条"
        f"\n命中: 旧口径残留 {s['phrase_hits']} 处"
        f" / 作废 REQ 未标注失效 {s['req_unmarked']} 处"
        f" / 作废 REQ 已标注(合规) {s['req_annotated']} 处"
    )

    if result["stale_phrase_hits"]:
        out.append("\n🔴 旧口径残留(疑似改了口径但说明文案未同步改写):")
        cur = None
        for h in result["stale_phrase_hits"]:
            if h["file"] != cur:
                cur = h["file"]
                out.append(f"  📄 {cur}")
            out.append(f"    - L{h['line']:<5} 旧口径「{h['phrase']}」: {h['snippet']}")
    elif phrases:
        out.append("\n✅ 旧口径字样清单在代码中无残留命中。")

    if result["stale_req_unmarked"]:
        out.append("\n🔴 作废 REQ 编号引用未标注失效(应补「该需求已于 {version} 作废」):")
        cur = None
        for h in result["stale_req_unmarked"]:
            if h["file"] != cur:
                cur = h["file"]
                out.append(f"  📄 {cur}")
            out.append(f"    - L{h['line']:<5} {h['req']}: {h['snippet']}")

    if result["stale_req_annotated"]:
        out.append("\n🟢 作废 REQ 编号引用已带失效标注(合规、仅信息):")
        for h in result["stale_req_annotated"]:
            out.append(
                f"    - {h['file']}:L{h['line']} {h['req']}"
                f" (标注: {h.get('marker', '')})"
            )
    elif reqs and not result["stale_req_unmarked"]:
        out.append("\n✅ 作废 REQ 编号清单在代码中无引用命中。")

    out.append("\n⚠️ 以上仅为采集清单,是否违规由 Agent 结合表 E/表 F 语义核验:")
    out.append("   · 旧口径残留处确属本版已改口径的展示位说明文案 → 🔴 Critical(回修复团队 Agent1)")
    out.append("   · 作废 REQ 未标注失效 → 命中,补「该需求已于 {version} 作废」标注")
    out.append("   (清单来源: ux-logic-extractor 表 E【处置=改写】行「变更前语义」/ 表 F【处置=作废】行「需求编号」)")
    return "\n".join(out)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("root", type=Path, help="代码根目录")
    parser.add_argument("--stale-phrases", help="旧口径字样清单,逗号分隔(表 E 变更前语义)")
    parser.add_argument("--stale-phrases-file", type=Path, help="旧口径字样清单文件,每行一条")
    parser.add_argument("--stale-reqs", help="作废 REQ 编号清单,逗号分隔(表 F 作废行编号)")
    parser.add_argument("--stale-reqs-file", type=Path, help="作废 REQ 编号清单文件,每行一条")
    parser.add_argument("--neighbor", type=int, default=DEFAULT_NEIGHBOR_LINES,
                        help=f"作废 REQ 失效标注的邻近扫描行数,默认 {DEFAULT_NEIGHBOR_LINES}")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出供 Agent 解析")
    parser.add_argument("--strict", action="store_true",
                        help="存在命中(旧口径残留 或 未标注失效作废 REQ)时返回退出码 1")
    args = parser.parse_args(argv)

    if not args.root.exists() or not args.root.is_dir():
        print(f"错误: 目录不存在或不是目录: {args.root}", file=sys.stderr)
        return 2
    for fp in (args.stale_phrases_file, args.stale_reqs_file):
        if fp is not None and not fp.is_file():
            print(f"错误: 清单文件不存在: {fp}", file=sys.stderr)
            return 2

    # ⚠️ 只判 is_file() 不够：清单文件存在但不可读时 read_text 抛 PermissionError，
    # 裸 traceback 且退出码为 1 —— 按全仓约定 1 = 检出违规，接进 CI 会被读成
    # 「检出旧口径残留」而误红。环境错必须落在 2。
    try:
        phrases = load_list(args.stale_phrases, args.stale_phrases_file)
        reqs = load_list(args.stale_reqs, args.stale_reqs_file)
    except OSError as e:
        print(f"错误: 清单文件读取失败: {e}", file=sys.stderr)
        return 2
    if not phrases and not reqs:
        print("错误: 至少提供一类清单(--stale-phrases[/-file] 或 --stale-reqs[/-file])", file=sys.stderr)
        return 2

    result = scan(args.root, phrases, reqs, max(0, args.neighbor))

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_text(result, phrases, reqs))

    if args.strict and (result["summary"]["phrase_hits"] or result["summary"]["req_unmarked"]):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
