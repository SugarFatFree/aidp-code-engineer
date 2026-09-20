#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PRD 条目反向覆盖率 硬核回检 — ux-logic-extractor 维度 13 子项(命令 9)

对研发 PRD 文档(.md)里的「表 D：PRD 条目映射表」做**上游 PRD 原子条目 → 下游落点的反向覆盖校验**。

与命令 4(`check_req_upstream.py`,下游研发需求段 → 上游 PRD 的**正向**溯源)方向相反、并存不可替代:
命令 4 以「下游功规点」为基准查「有没有出处」;命令 9 以「上游 PRD 每个原子条目」为基准查「有没有在
下游落点」。产品需求文档里「导出」操作(藏在操作描述表 / 遗留问题·迭代建议表)、「完成率进度条分色」
(藏在字段说明表的『备注』列)等条目,过去正是缺这道反向覆盖校验而被研发需求整条静默丢失、全链路零告警。

表 D 结构(与 SKILL.md 六·4 严格一致):
  | PRD 位置 | 条目内容 | 研发需求落点 | 处置 |
  处置固定枚举 ∈ {已承接 / 本版不做 / 已存在无需重复}

判据(判错型):
  已分类条目 = 处置 ∈ {已承接, 本版不做, 已存在无需重复}
  未分类条目 = 处置列为空 或 取值不在枚举内
  (已承接 + 本版不做 + 已存在无需重复) / 总条目 必须 = 100%;**未分类条目 > 0 即退出码 1、强制不通过**,
  并列出每条未落点/未分类条目原文(PRD 位置 + 条目内容)。

三类高危丢失点专项回检(内置,report-only 提示,命中即醒目告警,不单独判错):
  ① 表 D 中「操作」类条目整类缺失,或整表操作类条目 0 承接的迹象;
  ② 疑似只承接字段名、无对应「备注 / 展示规则」属性的条目(字段说明表的备注列丢失);
  ③ 文档提到「遗留问题 / 迭代建议 / 待办」但表 D 无对应来源条目(未逐条进表 D)。
  另附提示:处置 = 本版不做 的条目须经产品确认门登记「十、待澄清问题清单」(Q-ITEM-NNN),严禁静默丢弃。

产品原始 PRD 源(模式 B 判定):`--prd-source <目录>` 显式指定;缺省自动探测输入路径所在目录
及其父目录下的 `产品提供/`(AIDP 布局 `docs/requirements/{version}/产品提供/*.md`)。扫描研发 PRD 时
自动排除 `产品提供/` 子树。

用法:
  python check_prd_item_coverage.py <PRD 文件或目录>
  python check_prd_item_coverage.py <PRD 文件或目录> --prd-source docs/requirements/V1.0.0/产品提供
  python check_prd_item_coverage.py <PRD 文件或目录> --json
  python check_prd_item_coverage.py --self-check      # 阳性对照

退出码:
  0  通过(表 D 全部条目已分类,覆盖率 100%)  或  无表 D 且**无产品原始 PRD 源**(模式 A 纯原型逆向)
  1  表 D 存在未分类 / 未落点条目(覆盖率 < 100%);或**存在产品原始 PRD 源却无表 D**(模式 B 漏表 D)
  2  输入错误(路径不存在 / 无 .md 文件)——非维度违规,修正参数后重跑
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

# 表 D 处置固定枚举(与 SKILL.md 六·4 表 D 严格一致)
DISPOSITION_ENUM_D = ["已承接", "本版不做", "已存在无需重复"]

# 表 D 表头特征:同一表头行含「条目内容」+「处置」+(「PRD 位置」或「研发需求落点」)
TABLE_D_ITEM = "条目内容"
TABLE_D_DISP = "处置"
TABLE_D_POS = ["PRD 位置", "PRD位置", "研发需求落点"]

# 高危 ①:操作类关键词(用于粗判操作类条目是否整类缺失 / 0 承接)
OPERATION_KEYWORDS = [
    "导出", "导入", "新增", "新建", "编辑", "修改", "删除", "批量", "提交", "审批",
    "保存", "上传", "下载", "查询", "搜索", "重置", "启用", "停用", "复制", "打印",
    "分配", "撤销", "确认", "取消", "刷新", "操作",
]
# 高危 ②:备注 / 展示规则 属性关键词(带这些的条目 = 备注列有被并入登记)
NOTE_ATTR_KEYWORDS = [
    "备注", "展示规则", "分色", "进度条", "颜色", "规则", "格式", "脱敏", "排序",
    "默认", "显示", "展示", "标红", "高亮", "阈值",
]
# 高危 ③:遗留问题 / 迭代建议 类来源关键词
LEGACY_KEYWORDS = ["遗留问题", "迭代建议", "待办", "后续需求", "后续迭代"]

Q_ITEM_RE = re.compile(r"Q-ITEM-\d+")


PRD_SOURCE_DIRNAME = "产品提供"


def find_md_files(path: Path) -> List[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(p for p in path.rglob("*.md") if PRD_SOURCE_DIRNAME not in p.relative_to(path).parts)
    return []


def find_prd_sources(path: Path, explicit: Optional[Path]) -> List[Path]:
    """产品原始 PRD 源文件(模式 B 的判据):显式目录优先,否则探测输入所在目录与父目录下的 产品提供/。"""
    if explicit is not None:
        cands = [explicit]
    else:
        base = path if path.is_dir() else path.parent
        cands = [base / PRD_SOURCE_DIRNAME, base.parent / PRD_SOURCE_DIRNAME]
    out: List[Path] = []
    for c in cands:
        if c.is_dir():
            out.extend(sorted(c.rglob("*.md")))
    return out


def split_row(line: str) -> List[str]:
    """切分 markdown 表格行为单元格列表(去掉首尾空管道)。"""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def is_separator_row(cells: List[str]) -> bool:
    # ⚠️ 空行必须先判掉:split_row("") 得到 [""],把空单元格过滤后 all() 对空序列返回 True,
    #    于是**空行被当成分隔行** ——「候选表头 + 紧跟一个空行」会被识别成一张 0 行的表,
    #    对按表头签名判列的检查器就是一条凭空的「缺列 Critical」。
    #    实测复现:`output-module-examples.md` B.7 的键值表末行 + 空行 → 假红。勿改回。
    if not cells or all(c.strip() == "" for c in cells):
        return False
    return all(re.fullmatch(r":?-{1,}:?", c.replace(" ", "")) for c in cells if c != "")


def is_table_d_header(cells: List[str]) -> bool:
    joined = " ".join(cells)
    if TABLE_D_ITEM not in joined:
        return False
    if TABLE_D_DISP not in joined:
        return False
    return any(k in joined for k in TABLE_D_POS)


def clean_cell(v: str) -> str:
    return re.sub(r"[*`>\s]", "", v)


def scan_file(path: Path, root: Path) -> Dict:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"file": str(path), "read_error": str(exc)}
    try:
        rel = str(path.relative_to(root))
    except ValueError:
        rel = str(path)

    lines = text.splitlines()
    n = len(lines)
    rows: List[Dict] = []          # 表 D 全部数据行
    table_d_header_lines: List[int] = []

    i = 0
    while i < n:
        line = lines[i]
        if "|" not in line:
            i += 1
            continue
        # ⚠️ GFM 表头必须**紧跟分隔行**。不校验这一条时，任何**散文行**
        # 或**别的表的数据行**只要凑齐了那几个列名词就会被当成表头 —— 实测本 SKILL 自己的
        # SKILL.md「参考资源」表里描述本脚本用途的一行（正文恰好含「处置」「PRD 位置」
        # 「条目内容」）被判成表 D 表头，随后其下两行被当作「未分类条目」，
        # 整份 SKILL.md 判维度 13 不通过且不可修。同源教训见 architect
        # check_error_contract.py:298（「散文里出现 `|` 就会被当成一张表」）。
        cells = split_row(line)
        if not is_table_d_header(cells) or not (
                i + 1 < n and "|" in lines[i + 1]
                and is_separator_row(split_row(lines[i + 1]))):
            i += 1
            continue
        # 命中表 D 表头,收集列索引
        table_d_header_lines.append(i + 1)
        pos_idx = next((k for k, c in enumerate(cells) if any(p in c for p in TABLE_D_POS)), None)
        item_idx = next((k for k, c in enumerate(cells) if TABLE_D_ITEM in c), None)
        disp_idx = next((k for k, c in enumerate(cells) if TABLE_D_DISP in c), None)
        j = i + 1
        if j < n and "|" in lines[j] and is_separator_row(split_row(lines[j])):
            j += 1
        while j < n and "|" in lines[j]:
            rcells = split_row(lines[j])
            # ⚠️ 全空行既**不算分隔行**(见 is_separator_row 前置判)、也**不算数据行**:两个性质必须
            #    同时成立。只改前者会让 Word 转出的 `||||` 占位行变成数据行、每格报一条「为空」
            #    (真实 PRD 语料里有 35 处这种行)。
            if is_separator_row(rcells) or all(c.strip() == "" for c in rcells):
                j += 1
                continue
            pos = rcells[pos_idx].strip() if (pos_idx is not None and pos_idx < len(rcells)) else ""
            item = rcells[item_idx].strip() if (item_idx is not None and item_idx < len(rcells)) else ""
            disp = rcells[disp_idx].strip() if (disp_idx is not None and disp_idx < len(rcells)) else ""
            disp_clean = clean_cell(disp)
            # 整行皆空则跳过(非条目)
            if disp_clean == "" and item == "" and pos == "":
                j += 1
                continue
            classified = disp_clean in DISPOSITION_ENUM_D
            rows.append({
                "line": j + 1,
                "pos": pos,
                "item": item,
                "disposition_raw": disp,
                "disposition": disp_clean,
                "classified": classified,
                "accepted": disp_clean == "已承接",
                "deferred": disp_clean == "本版不做",
            })
            j += 1
        i = j

    # ── 覆盖率判据 ──
    total = len(rows)
    unclassified = [r for r in rows if not r["classified"]]
    # ⚠️ 「表 D 存在但零条目」绝不能算 100%：`cov = … if total else 100.0`
    # 让一张只有表头+分隔行的空壳表拿到「覆盖率 100.0% ✅ 通过」——表 D 是模式 B 的
    # Critical 强制产物，贴个空表头就能过反向覆盖率闸门，是标准的统计口径空转。
    # 与「压根没有表 D」判然不同：那是模式 A 的合法形态，由 has_table_d=False 分支返回 0。
    # ⚠️ 必须在这里判、不能在 render 里判 —— 退出码取自 scan_file 的结果，渲染期改已经晚了。
    if table_d_header_lines and not rows:
        unclassified = [{"line": table_d_header_lines[0], "pos": "",
                         "item": "(表 D 只有表头、零条目：空壳表不等于「无条目可映射」)",
                         "disposition_raw": ""}]

    # ── 高危 ① 操作类条目 ──
    op_rows = [r for r in rows if any(k in r["item"] for k in OPERATION_KEYWORDS)]
    op_accepted = [r for r in op_rows if r["accepted"]]

    # ── 高危 ② 备注 / 展示规则 属性 ──
    note_rows = [r for r in rows if any(k in r["item"] for k in NOTE_ATTR_KEYWORDS)]

    # ── 高危 ③ 遗留问题 / 迭代建议 ──
    doc_mentions_legacy = any(k in text for k in LEGACY_KEYWORDS)
    legacy_rows = [r for r in rows if any(k in (r["item"] + " " + r["pos"]) for k in LEGACY_KEYWORDS)]

    # ── 本版不做 → Q-ITEM 登记提示 ──
    deferred_rows = [r for r in rows if r["deferred"]]
    q_item_count = len(Q_ITEM_RE.findall(text))

    return {
        "file": rel,
        "has_table_d": len(table_d_header_lines) > 0,
        "table_d_header_lines": table_d_header_lines,
        "total": total,
        "classified": total - len(unclassified),
        "unclassified": unclassified,
        "op_row_count": len(op_rows),
        "op_accepted_count": len(op_accepted),
        "note_row_count": len(note_rows),
        "doc_mentions_legacy": doc_mentions_legacy,
        "legacy_row_count": len(legacy_rows),
        "deferred_count": len(deferred_rows),
        "q_item_count": q_item_count,
    }


def render_text(results: List[Dict], failed: bool) -> str:
    out: List[str] = []
    out.append("=== PRD 条目反向覆盖率 硬核回检(维度 13 子项·命令 9) ===\n")

    any_table_d = any(r.get("has_table_d") for r in results)
    if not any_table_d:
        out.append("ℹ️ 未在任何 .md 中发现「表 D：PRD 条目映射表」表头。")
        out.append("   → 无产品原始 PRD 源(模式 A 纯原型逆向):退出码 0 跳过,不判错。")
        out.append("   → 探测到产品原始 PRD 源(`产品提供/` 或 --prd-source)却无表 D:模式 B 漏表 D,退出码 1。")
        return "\n".join(out)

    for r in results:
        if r.get("read_error"):
            out.append(f"[读取失败] {r['file']}: {r['read_error']}")
            continue
        if not r.get("has_table_d"):
            continue
        out.append(f"📄 {r['file']}")
        out.append(f"   表 D 表头行 {r['table_d_header_lines']};条目总数 {r['total']},已分类 {r['classified']}")
        cov = (r["classified"] / r["total"] * 100) if r["total"] else 100.0
        out.append(f"   覆盖率(已承接+本版不做+已存在无需重复)/总条目 = {cov:.1f}%")
        if r["unclassified"]:
            out.append(f"   ❌ 未分类 / 未落点条目 {len(r['unclassified'])} 条(处置为空或不在枚举 {DISPOSITION_ENUM_D} 内):")
            for u in r["unclassified"]:
                pos = u["pos"] or "(无 PRD 位置)"
                item = u["item"] or "(无条目内容)"
                disp = u["disposition_raw"] or "(空)"
                out.append(f"      - L{u['line']} 处置=「{disp}」 | PRD 位置:{pos} | 条目:{item}")
        else:
            out.append("   ✅ 表 D 条目 100% 已分类到固定枚举")

        # 高危 ①
        if r["op_row_count"] == 0:
            out.append("   🟡[高危①] 表 D 未发现任何「操作」类条目 — 操作描述表可能整类缺失,请核对导出/新增/编辑/删除/批量等操作是否逐条进表 D")
        elif r["op_accepted_count"] == 0:
            out.append(f"   🟡[高危①] 表 D 有 {r['op_row_count']} 条操作类条目但 0 条「已承接」— 整表操作 0 承接迹象,请核对操作是否被整类丢弃")
        # 高危 ②
        if r["note_row_count"] == 0:
            out.append("   🟡[高危②] 表 D 未发现带「备注/展示规则/分色/进度条」等属性的条目 — 字段说明表的『备注』列可能未并入条目登记(如完成率进度条分色),请核对备注列是否随字段名一起进表 D")
        # 高危 ③
        if r["doc_mentions_legacy"] and r["legacy_row_count"] == 0:
            out.append("   🟡[高危③] 文档提到「遗留问题/迭代建议/待办」但表 D 无对应来源条目 — 请核对遗留问题/迭代建议表是否逐条进表 D(遗留问题/迭代建议是需求输入,非缺陷备忘)")
        # 本版不做 → Q-ITEM 提示
        if r["deferred_count"] > 0:
            out.append(f"   ℹ️ 表 D 有 {r['deferred_count']} 条「本版不做」;全文 Q-ITEM-NNN 锚点 {r['q_item_count']} 个 — 每条「本版不做」须经产品确认门登记「十、待澄清问题清单」(Q-ITEM-NNN),严禁静默丢弃")
        out.append("")

    if failed:
        out.append("❌ 判定:存在未分类 / 未落点条目,PRD 条目反向覆盖率 < 100%,维度 13 不通过(退出码 1)。")
    else:
        out.append("✅ 判定:表 D 条目反向覆盖率 100%,通过(退出码 0)。高危①②③ 提示如上,请 Agent 结合产品需求文档逐条复核。")
    return "\n".join(out)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("path", type=Path, nargs="?", help="PRD 文件或目录")
    parser.add_argument("--prd-source", type=Path, default=None,
                        help="产品原始 PRD 目录(缺省自动探测同级/父级 产品提供/)")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    parser.add_argument("--self-check", action="store_true", help="阳性对照自检")
    args = parser.parse_args(argv)
    if args.self_check:
        return self_check()
    if args.path is None:
        parser.error("需要 <PRD 文件或目录>(或使用 --self-check)")

    if not args.path.exists():
        print(f"错误: 路径不存在 {args.path}", file=sys.stderr)
        return 2

    root = args.path if args.path.is_dir() else args.path.parent
    md_files = find_md_files(args.path)
    if not md_files:
        print("⚠️ 未发现任何 .md 文件", file=sys.stderr)
        return 2

    results = [scan_file(f, root) for f in md_files]

    # ⚠️ 读不出来 ≠ 没有违规:全部文件都读失败时判**环境错(2)**,绝不静默计为通过。
    #    (同 skill 的 check_technical_content.py 已做对,此处对齐;全仓退出码约定同款。)
    _read_errs = [r for r in results if isinstance(r, dict) and r.get("read_error")]
    if _read_errs and len(_read_errs) == len(results):
        for _r in _read_errs:
            print(f"错误: 无法读取 {_r['file']}: {_r['read_error']}", file=sys.stderr)
        return 2

    any_table_d = any(r.get("has_table_d") for r in results)
    total_unclassified = sum(len(r.get("unclassified", [])) for r in results)
    prd_sources = find_prd_sources(args.path, args.prd_source)
    # 判错:存在表 D 且有未分类条目;或有产品原始 PRD 源却无表 D(模式 B 漏表 D)
    missing_table_d = (not any_table_d) and bool(prd_sources)
    failed = (any_table_d and total_unclassified > 0) or missing_table_d
    exit_code = 1 if failed else 0

    if args.json:
        print(json.dumps({
            "command": "check_prd_item_coverage",
            "has_table_d": any_table_d,
            "prd_source_files": [str(p) for p in prd_sources],
            "missing_table_d": missing_table_d,
            "total_unclassified": total_unclassified,
            "failed": failed,
            "exit_code": exit_code,
            "files": results,
        }, ensure_ascii=False, indent=2))
    else:
        print(render_text(results, failed))
        if missing_table_d:
            print(f"❌ 判定:发现 {len(prd_sources)} 份产品原始 PRD(如 {prd_sources[0]}),研发 PRD 却无「表 D：PRD 条目映射表」"
                  "——模式 B 必须产出表 D,维度 13 不通过(退出码 1)。")

    return exit_code


def self_check() -> int:
    """阳性对照:有产品 PRD 无表 D → 1;表 D 含未分类 → 1;无产品 PRD 无表 D → 0;表 D 全分类 → 0。"""
    import tempfile, io, contextlib
    good = "| PRD 位置 | 条目内容 | 研发需求落点 | 处置 |\n|---|---|---|---|\n| §1 | 导出订单 | REQ-001 | 已承接 |\n"
    bad = good.replace("已承接", "")
    ok = True
    with tempfile.TemporaryDirectory() as t:
        v = Path(t) / "V1.0.0"
        (v / "研发需求").mkdir(parents=True)
        cases = []
        (v / "研发需求" / "01_x.md").write_text("# 无表D\n", encoding="utf-8")
        cases.append(("无产品PRD无表D", 0))
        def run():
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                return main([str(v / "研发需求")])
        got = run()
        if got != 0:
            print(f"[self-check] FAIL 无产品PRD无表D 期望 0 实得 {got}"); ok = False
        (v / "产品提供").mkdir()
        (v / "产品提供" / "PRD.md").write_text("# 产品需求\n导出订单\n", encoding="utf-8")
        got = run()
        if got != 1:
            print(f"[self-check] FAIL 有产品PRD无表D 期望 1 实得 {got}"); ok = False
        (v / "研发需求" / "01_x.md").write_text(bad, encoding="utf-8")
        got = run()
        if got != 1:
            print(f"[self-check] FAIL 表D未分类 期望 1 实得 {got}"); ok = False
        (v / "研发需求" / "01_x.md").write_text(good, encoding="utf-8")
        got = run()
        if got != 0:
            print(f"[self-check] FAIL 表D全分类 期望 0 实得 {got}"); ok = False
    print("[self-check] OK" if ok else "[self-check] FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
