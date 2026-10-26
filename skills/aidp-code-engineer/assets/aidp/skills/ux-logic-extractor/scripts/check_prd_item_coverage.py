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

以产品原文为基准(可选 `--prd-source <产品原始 PRD 文件或目录>`,`.md`/`.txt`):
  不传时行为与无此参数完全一致(只核表 D 自身的分类完整性)。传了即声明「本次是模式 B、有产品原文」:
  S0  有产品原文却无表 D                 → 不通过(模式 B 漏表 D)
  S1  产品原文里的原子条目未进表 D        → 不通过,逐条列出原文位置 + 条目
      原子条目只取**高精度**两类,⛔ 不扫散文段落(散文抽条目必满屏假红):
        ① 按钮/操作名:`点击「X」` / `"X"按钮` 等引号包裹的操作名;
        ② 字段/列/按钮/操作类表格:表头**任一列**含 字段/列名/按钮/操作/功能点/条目 即取**该列**取值
           (表头同时含 步骤/预期/序号/说明/描述/备注 的列不取——那是步骤、预期、序号或散文描述;
           取值恰为表头词本身〔如「操作」〕不算条目;同格以 、，,;； 分隔的多值逐个成条)。
      判定「已进表 D」(⚠️ **单向**):条目名归一后与某表 D 行「条目内容」**精确相等**,或该表 D 条目
        **包含**原文条目且原文条目归一后长度 ≥ MIN_CONTAIN_LEN。⛔ 不认反方向——表 D 写个「订单」
        不得覆盖原文「导出订单」「订单编号」(反向包含会让一个泛词吞掉整类条目 = 假绿)。
      抽到 0 条时 `--json` 出 `prd_source.zero_items: true` 并人读警示:**0 条 ≠ 原文全覆盖**,
        只说明原文没有这两类高精度写法,全部条目都要靠 QR Agent 人工比对。
  `--prd-source` 传单个文件时同样只认 .md/.txt 后缀,其它后缀判入参错(exit 2)。
  `--prd-source` 落在 <PRD 文件或目录> 之内时,其子树不计入研发 PRD 扫描面。
  脚本只抽得到这两类;散文/列表里的功能条目仍须由 QR Agent 逐条比对,⛔ 不得因脚本绿了就跳过。

用法:
  python check_prd_item_coverage.py <PRD 文件或目录>
  python check_prd_item_coverage.py <PRD 文件或目录> --json
  python check_prd_item_coverage.py <PRD 文件或目录> --prd-source <产品原始 PRD 文件或目录> [--json]
  python check_prd_item_coverage.py --self-check   # 阳性/阴性对照,不可与 path/--json/--prd-source 组合

退出码:
  0  通过(表 D 全部条目已分类,覆盖率 100%)  或  无表 D(模式 A 纯原型逆向 / 标 N/A / 历史存量无表 D
     的 grandfather 放行,跳过并提示迁移)
  1  表 D 存在未分类 / 未落点条目(处置为空或不在枚举内),覆盖率 < 100%,强制不通过;
     或(仅传 --prd-source 时)S0 有产品原文却无表 D / S1 产品原文条目未进表 D
  2  输入错误(路径不存在 / 无 .md 文件 / --prd-source 不存在、无可读文件或单文件后缀不是 .md/.txt)——非维度违规,修正参数后重跑
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import sys
import tempfile
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


def find_md_files(path: Path) -> List[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(path.rglob("*.md"))
    return []


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


# ── --prd-source:产品原文原子条目抽取(只取高精度两类,不扫散文) ──
PRD_SOURCE_SUFFIXES = (".md", ".txt")
_Q = r"[「“\"『]"
_QE = r"[」”\"』]"
SRC_BUTTON_RES = [
    re.compile(r"点击" + _Q + r"([^」”\"』\n]{1,20})" + _QE),
    re.compile(_Q + r"([^」”\"』\n]{1,20})" + _QE + r"\s*(?:按钮|操作|链接|入口)"),
]
SRC_TABLE_HEAD_KEYS = ("字段", "列名", "按钮", "操作", "功能点", "条目")
# 表头含这些词的列不取值:步骤/预期/序号 是测试或流程列,说明/描述/备注 是散文列(抽散文必满屏假红)
SRC_TABLE_COL_EXCLUDE = ("步骤", "预期", "序号", "说明", "描述", "备注")
_SRC_MULTI_SPLIT = re.compile(r"[、，,;；]")
# 单向包含匹配时原文条目(归一后)的最短长度;短于它只认精确相等
MIN_CONTAIN_LEN = 2
_NORM_STRIP = re.compile(r"[\s*`>「」“”\"『』()（）\[\]【】:：,，、。;；!！?？/\\-]")


def norm_item(v: str) -> str:
    return _NORM_STRIP.sub("", v)


def find_source_files(path: Path) -> List[Path]:
    if path.is_file():
        # 单文件同样走后缀白名单:否则传错一个 .docx/.pdf 会被当乱码文本扫、抽到 0 条后静默放行
        return [path] if path.suffix.lower() in PRD_SOURCE_SUFFIXES else []
    if path.is_dir():
        return sorted(p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in PRD_SOURCE_SUFFIXES)
    return []


def extract_source_items(path: Path, root: Path) -> Dict:
    """从一份产品原文里抽高精度原子条目;返回 {file, items:[{line, item, kind}]} 或 read_error。"""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"file": str(path), "read_error": str(exc)}
    try:
        rel = str(path.relative_to(root))
    except ValueError:
        rel = str(path)
    items: List[Dict] = []
    seen = set()

    def add(line_no: int, item: str, kind: str) -> None:
        key = norm_item(item)
        if len(key) < 2 or key in seen:
            return
        seen.add(key)
        items.append({"line": line_no, "item": item.strip(), "kind": kind})

    lines = text.splitlines()
    n = len(lines)
    in_fence = False
    i = 0
    while i < n:
        line = lines[i]
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            i += 1
            continue
        if in_fence:
            i += 1
            continue
        for rx in SRC_BUTTON_RES:
            for m in rx.finditer(line):
                add(i + 1, m.group(1), "按钮/操作")
        cells = split_row(line) if "|" in line else []
        hit_cols = [k for k, c in enumerate(cells)
                    if any(h in clean_cell(c) for h in SRC_TABLE_HEAD_KEYS)
                    and not any(x in clean_cell(c) for x in SRC_TABLE_COL_EXCLUDE)]
        if (hit_cols and i + 1 < n and "|" in lines[i + 1]
                and is_separator_row(split_row(lines[i + 1]))
                and not is_table_d_header(cells)):
            header_words = {norm_item(c) for c in cells} | set(SRC_TABLE_HEAD_KEYS)
            j = i + 2
            while j < n and "|" in lines[j]:
                rc = split_row(lines[j])
                if not is_separator_row(rc):
                    for k in hit_cols:
                        if k >= len(rc):
                            continue
                        for part in _SRC_MULTI_SPLIT.split(rc[k]):
                            val = part.strip().strip("*`").strip()
                            key = clean_cell(val)
                            if key and len(key) <= 30 and norm_item(val) not in header_words:
                                add(j + 1, val, "表格条目")
                for rx in SRC_BUTTON_RES:
                    for m in rx.finditer(lines[j]):
                        add(j + 1, m.group(1), "按钮/操作")
                j += 1
            i = j
            continue
        i += 1
    return {"file": rel, "items": items}


def _covered(key: str, d: str) -> bool:
    """原文条目 key 是否被表 D 条目 d 覆盖:精确相等,或 d 单向包含 key 且 key 够长。⛔ 不认 key 包含 d。"""
    return key == d or (len(key) >= MIN_CONTAIN_LEN and key in d)


def source_coverage(source_files: List[Path], source_root: Path, results: List[Dict]) -> Dict:
    d_items = [norm_item(r["item"]) for res in results for r in res.get("rows", [])]
    d_items = [x for x in d_items if len(x) >= 2]
    per_file: List[Dict] = [extract_source_items(f, source_root) for f in source_files]
    uncovered: List[Dict] = []
    total = 0
    for pf in per_file:
        for it in pf.get("items", []):
            total += 1
            key = norm_item(it["item"])
            if not any(_covered(key, d) for d in d_items):
                uncovered.append({"file": pf["file"], **it})
    return {"files": per_file, "items_total": total, "uncovered": uncovered,
            "read_errors": [pf for pf in per_file if pf.get("read_error")]}


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
        # ⚠️ GFM 表头必须**紧跟分隔行**（2026-08-23 补）。不校验这一条时，任何**散文行**
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
    # ⚠️ 「表 D 存在但零条目」绝不能算 100%（2026-08-23 补）：`cov = … if total else 100.0`
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
        "rows": rows,
    }


def render_text(results: List[Dict], failed: bool) -> str:
    out: List[str] = []
    out.append("=== PRD 条目反向覆盖率 硬核回检(维度 13 子项·命令 9) ===\n")

    any_table_d = any(r.get("has_table_d") for r in results)
    if not any_table_d:
        out.append("ℹ️ 未在任何 .md 中发现「表 D：PRD 条目映射表」表头。")
        out.append("   → 模式 A(纯原型逆向,无产品需求文档)或表 D 标 N/A:退出码 0 跳过,不判错。")
        out.append("   → 历史存量无表 D:grandfather 放行(退出码 0),建议后续新生成补齐表 D 走反向覆盖校验。")
        out.append("   → 若本次为模式 B(有产品需求文档)新生成却无表 D,QR Agent 应判维度 13 不通过(缺表 D 条目化)。")
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


def render_source(src: Dict, any_table_d: bool) -> str:
    out: List[str] = ["", "=== 以产品原文为基准的条目反向覆盖(--prd-source) ==="]
    out.append(f"   产品原文 {len(src['files'])} 份,抽到高精度原子条目 {src['items_total']} 条"
               "(只取按钮/操作名 + 字段/列/按钮/操作类表格列;散文条目须 Agent 逐条比对)")
    if src["items_total"] == 0:
        out.append("   ⚠️[zero_items] 产品原文一条高精度条目都没抽到 —— 这 ≠ 原文已全覆盖:"
                   "原文没有引号按钮名/字段类表格,全部条目须由 QR Agent 逐条人工比对表 D")
    for pf in src["read_errors"]:
        out.append(f"   [读取失败] {pf['file']}: {pf['read_error']}")
    if not any_table_d:
        out.append("   ❌[S0] 传了产品原文,研发 PRD 却无「表 D：PRD 条目映射表」—— 模式 B 漏表 D")
    if src["uncovered"]:
        out.append(f"   ❌[S1] 产品原文条目未进表 D {len(src['uncovered'])} 条:")
        for u in src["uncovered"]:
            out.append(f"      - {u['file']}:L{u['line']} [{u['kind']}] {u['item']}")
    elif any_table_d:
        out.append("   ✅ 抽到的产品原文条目均已进表 D")
    return "\n".join(out)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("path", type=Path, nargs="?", help="研发 PRD 文件或目录")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    parser.add_argument("--prd-source", type=Path, default=None,
                        help="产品原始 PRD 文件或目录(.md/.txt);传了即以产品原文为基准做条目反向覆盖")
    parser.add_argument("--self-check", action="store_true", help="运行内建阳性/阴性对照(独立模式)")
    args = parser.parse_args(argv)

    if args.self_check:
        if args.path is not None or args.json or args.prd_source is not None:
            print("错误: --self-check 不能与 path / --json / --prd-source 同时使用", file=sys.stderr)
            return 2
        return run_self_check()
    if args.path is None:
        print("错误: 缺少研发 PRD 文件或目录(或使用 --self-check)", file=sys.stderr)
        return 2

    if not args.path.exists():
        print(f"错误: 路径不存在 {args.path}", file=sys.stderr)
        return 2

    source_files: List[Path] = []
    if args.prd_source is not None:
        if not args.prd_source.exists():
            print(f"错误: --prd-source 路径不存在 {args.prd_source}", file=sys.stderr)
            return 2
        source_files = find_source_files(args.prd_source)
        if not source_files:
            print(f"错误: --prd-source 下未发现任何 .md/.txt 文件(单文件须为 .md/.txt 后缀) {args.prd_source}",
                  file=sys.stderr)
            return 2

    root = args.path if args.path.is_dir() else args.path.parent
    md_files = find_md_files(args.path)
    if args.prd_source is not None:
        src_resolved = {f.resolve() for f in source_files}
        src_dir = args.prd_source.resolve() if args.prd_source.is_dir() else None
        md_files = [f for f in md_files if f.resolve() not in src_resolved
                    and not (src_dir is not None and src_dir in f.resolve().parents)]
    if not md_files:
        print("⚠️ 未发现任何 .md 文件", file=sys.stderr)
        return 2

    results = [scan_file(f, root) for f in md_files]

    # ⚠️ 读不出来 ≠ 没有违规:全部文件都读失败时判**环境错(2)**,绝不静默计为通过。
    #    (同 skill 的 check_technical_content.py 已做对,此处对齐;统一退出码约定同款。)
    _read_errs = [r for r in results if isinstance(r, dict) and r.get("read_error")]
    if _read_errs and len(_read_errs) == len(results):
        for _r in _read_errs:
            print(f"错误: 无法读取 {_r['file']}: {_r['read_error']}", file=sys.stderr)
        return 2

    src: Optional[Dict] = None
    if args.prd_source is not None:
        src_root = args.prd_source if args.prd_source.is_dir() else args.prd_source.parent
        src = source_coverage(source_files, src_root, results)
        if len(src["read_errors"]) == len(source_files):
            for pf in src["read_errors"]:
                print(f"错误: 无法读取产品原文 {pf['file']}: {pf['read_error']}", file=sys.stderr)
            return 2
    # rows 只供 --prd-source 比对用,不进输出(缺省调用的输出保持不变)
    for r in results:
        r.pop("rows", None)

    any_table_d = any(r.get("has_table_d") for r in results)
    total_unclassified = sum(len(r.get("unclassified", [])) for r in results)
    # 判错:仅当存在表 D 且有未分类条目
    failed = any_table_d and total_unclassified > 0
    if src is not None:
        failed = failed or not any_table_d or bool(src["uncovered"])
    exit_code = 1 if failed else 0

    if args.json:
        payload = {
            "command": "check_prd_item_coverage",
            "has_table_d": any_table_d,
            "total_unclassified": total_unclassified,
            "failed": failed,
            "exit_code": exit_code,
            "files": results,
        }
        if src is not None:
            payload["prd_source"] = {
                "path": str(args.prd_source),
                "files": [pf["file"] for pf in src["files"]],
                "items_total": src["items_total"],
                "zero_items": src["items_total"] == 0,
                "missing_table_d": not any_table_d,
                "uncovered": src["uncovered"],
                "read_errors": src["read_errors"],
            }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        if src is None:
            print(render_text(results, failed))
        else:
            print(render_text(results, any_table_d and total_unclassified > 0))
            print(render_source(src, any_table_d))
            if failed:
                print("\n❌ 判定(含产品原文基准):不通过(退出码 1)。")
            else:
                print("\n✅ 判定(含产品原文基准):通过(退出码 0)。")

    return exit_code


_SC_TABLE_D = ("| PRD 位置 | 条目内容 | 研发需求落点 | 处置 |\n| :- | :- | :- | :- |\n"
               "| §2 操作表 | 导出订单 | REQ-001 | 已承接 |\n"
               "| §3 字段表 | 订单编号 | REQ-002 | 已承接 |\n")
_SC_SOURCE = ("# 订单管理(示例)\n\n点击「导出」按钮,导出当前筛选结果。\n\n"
              "| 字段 | 说明 |\n| :- | :- |\n| 订单编号 | 唯一 |\n")


def run_self_check() -> int:
    """阳性/阴性对照:(名称, 研发 PRD 内容, 产品原文内容或 None, 期望退出码, 期望命中)。"""
    cases = [
        ("表D全分类-无原文", _SC_TABLE_D, None, 0, None),
        ("表D未分类-无原文", _SC_TABLE_D.replace("| REQ-001 | 已承接 |", "| REQ-001 |  |"), None, 1, "unclassified"),
        ("无表D-无原文-放行", "# 研发 PRD\n\n无表 D。\n", None, 0, None),
        ("原文条目全覆盖", _SC_TABLE_D, _SC_SOURCE, 0, None),
        ("原文条目漏进表D", _SC_TABLE_D.replace("| §3 字段表 | 订单编号 | REQ-002 | 已承接 |\n", ""),
         _SC_SOURCE, 1, "uncovered:订单编号"),
        ("原文按钮漏进表D", _SC_TABLE_D.replace("导出订单", "查询订单"), _SC_SOURCE, 1, "uncovered:导出"),
        ("有原文无表D", "# 研发 PRD\n\n无表 D。\n", _SC_SOURCE, 1, "missing_table_d"),
        ("散文不抽条目", _SC_TABLE_D, "# 背景\n\n本系统用于管理订单,支持多种业务场景与统计报表。\n", 0, "zero_items"),
        # 单向匹配:表 D 泛词「订单」不得反向覆盖原文「导出订单」「订单编号」
        ("泛词不反向覆盖", _SC_TABLE_D.replace("导出订单", "订单").replace("| 订单编号 |", "| 订单 |"),
         "# 原文\n\n点击「导出订单」。\n\n| 字段 | 说明 |\n| :- | :- |\n| 订单编号 | 唯一 |\n",
         1, "uncovered:导出订单,订单编号"),
        # 任一列命中:字段列不在首列也要取;序号/说明列不取
        ("非首列字段列", _SC_TABLE_D, "# 原文\n\n| 序号 | 字段 | 说明 |\n| :- | :- | :- |\n| 1 | 下单时间 | 精确到秒 |\n",
         1, "uncovered:下单时间"),
        # 步骤/预期列不取;取值恰为表头词本身不算条目
        ("步骤预期列不取", _SC_TABLE_D,
         "# 原文\n\n| 序号 | 操作步骤 | 预期结果 |\n| :- | :- | :- |\n| 1 | 打开列表页 | 展示全部订单 |\n\n"
         "| 操作 | 备注 |\n| :- | :- |\n| 操作 | 表头复写行 |\n", 0, "zero_items"),
        # 同格多值逐个成条
        ("同格多值拆分", _SC_TABLE_D, "# 原文\n\n| 列名 | 操作 |\n| :- | :- |\n| 订单编号 | 导出订单、作废订单 |\n",
         1, "uncovered:作废订单"),
    ]
    failures: List[str] = []
    try:
        with tempfile.TemporaryDirectory(prefix="prd-item-selfcheck-") as td:
            for idx, (name, dev, source, rc, hit) in enumerate(cases):
                base = Path(td) / f"case{idx:02d}"
                (base / "研发需求").mkdir(parents=True)
                (base / "研发需求" / "01_PRD.md").write_text(dev, encoding="utf-8")
                argv = [str(base / "研发需求"), "--json"]
                if source is not None:
                    (base / "产品原文").mkdir()
                    (base / "产品原文" / "产品PRD.md").write_text(source, encoding="utf-8")
                    argv += ["--prd-source", str(base / "产品原文")]
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    got = main(argv)
                payload = json.loads(buf.getvalue())
                ok = got == rc
                if hit == "unclassified":
                    ok = ok and payload["total_unclassified"] > 0
                elif hit == "missing_table_d":
                    ok = ok and payload["prd_source"]["missing_table_d"] is True
                elif hit == "zero_items":
                    ok = ok and payload["prd_source"]["zero_items"] is True
                elif hit and hit.startswith("uncovered:"):
                    got_items = sorted(u["item"] for u in payload["prd_source"]["uncovered"])
                    ok = ok and got_items == sorted(hit.split(":", 1)[1].split(","))
                if source is not None and hit != "zero_items":
                    ok = ok and payload["prd_source"]["zero_items"] is False
                print(f"SELF-CHECK {name}: {'PASS' if ok else 'FAIL'}")
                if not ok:
                    failures.append(f"{name}: rc={got}, payload={payload}")
            # --prd-source 单文件后缀白名单:非 .md/.txt 判入参错
            bad = Path(td) / "产品PRD.docx"
            bad.write_text(_SC_SOURCE, encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                got = main([str(Path(td) / "case00" / "研发需求"), "--prd-source", str(bad)])
            ok = got == 2
            print(f"SELF-CHECK 单文件后缀白名单: {'PASS' if ok else 'FAIL'}")
            if not ok:
                failures.append(f"单文件后缀白名单: rc={got}")
    except OSError as exc:
        print(f"SELF-CHECK 环境错误: {exc}", file=sys.stderr)
        return 2
    if failures:
        for f in failures:
            print(f"  {f}", file=sys.stderr)
        return 1
    print(f"SELF-CHECK 通过: {len(cases) + 1}/{len(cases) + 1}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
