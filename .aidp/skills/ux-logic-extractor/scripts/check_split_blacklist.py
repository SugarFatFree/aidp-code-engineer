#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多文件拆分白名单检查 — ux-logic-extractor 维度 10「职责边界」补强

PRD 多文件拆分模式下,**严禁**生成"字段与字典""数据库设计先验"
"接口设计""非功能需求技术栈"类独立分册。本脚本对子文件名做关键词匹配
+ 内容嗅探,违规则不通过。

匹配规则(命中即违规):
  B1  文件名含技术域关键词    — 字段|字典(独立分册)|DTO|VO|实体|Entity
                              |数据库设计|ER图|表结构|DDL|接口设计|API设计
                              |技术栈|架构设计|非功能需求(单独)
  B2  文件内容嗅探            — 子文档技术信号行(R2 字段类型 + R4 DDL)合计 ≥ 10 条
                              且占表格行 ≥ 30% 时,视为技术分册,违规
  B3  文件名英文/拼音/kebab   — 去掉 `NN_` 前缀后无中文 = 不合规

豁免:
  - 字典枚举独立成文件是 PRD 拆分的合法形态(如 `06_字典枚举.md`),
    白名单关键词为「字典枚举」「字典与枚举」「枚举值」等;
  - 单文件命名"字段与字典.md"才属违规(混合了字段表)。

使用:
  python check_split_blacklist.py <PRD目录>
  python check_split_blacklist.py <PRD目录> --json
退出码: 0 = 通过 或 单文件模式 N/A 跳过(--json 带 skipped:true)
        1 = 不通过(存在违规分册)
        2 = 入参错(路径不存在 / 不可读 / 目录内无 .md)
"""

from __future__ import annotations

import os
import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List

# B1 文件名违规关键词 (Python 中文 unicode 区间,匹配技术域词)
FILENAME_VIOLATION_PATTERNS = [
    (r"字段与字典|字段及字典|DTO|实体表|VO定义", "字段+字典混合分册(应只独立字典枚举)"),
    (r"数据库设计|数据库先验|表结构设计|DDL|ER\s*图|实体关系", "数据库设计分册(归 dev-logic-architect)"),
    (r"接口设计|API\s*设计|API\s*契约|接口契约", "接口设计分册(归 dev-logic-architect)"),
    (r"技术架构|架构设计|技术栈|框架选型|部署架构", "技术架构分册(归 dev-logic-architect)"),
    (r"非功能需求.*技术|性能.*实现|安全.*实现|缓存.*策略", "非功能技术分册(只描述业务指标)"),
]
FILENAME_PATTERNS = [(re.compile(p), reason) for p, reason in FILENAME_VIOLATION_PATTERNS]

# B1 白名单(允许的字典枚举独立分册)
ALLOWED_DICT_PATTERN = re.compile(r"字典(?:枚举)?|枚举(?:定义|值)?|状态字典")

# B3 中文字符
CHINESE_PATTERN = re.compile(r"[一-鿿]")

# B2 内容嗅探: 字段类型表 / DDL 关键字
TYPE_TABLE_PATTERN = re.compile(
    r"\|.*\b[a-z][a-zA-Z0-9]*[A-Z][a-zA-Z0-9]*\b.*\|.*"
    r"\b(string|number|boolean|integer|varchar|datetime|String|Integer)\b.*\|"
)
DDL_PATTERN = re.compile(r"\b(CREATE\s+TABLE|ALTER\s+TABLE|VARCHAR\s*\(|NOT\s+NULL\b)", re.IGNORECASE)


def check_filename(name: str) -> List[Dict]:
    issues: List[Dict] = []
    # B1 黑名单:直接匹配技术域黑名单词即违规。
    # 不能用 `含"字典" → 白名单豁免` 短路 B1 —— 否则「字段与字典」这类混合分册
    # (docstring 明确应判违规)会因文件名含"字典"被错误豁免。
    # 当前黑名单词(字段与字典 / 数据库设计 / 接口设计 / 技术架构 / 非功能技术)
    # 均不会误伤纯字典枚举文件(如 06_字典枚举.md / 07_用户域字典枚举.md);
    # 纯字典枚举文件的内容嗅探豁免另由 main() 中的 ALLOWED_DICT_PATTERN 处理(B2)。
    for pat, reason in FILENAME_PATTERNS:
        if pat.search(name):
            issues.append({"rule": "B1_文件名违规", "name": name, "reason": reason})
            break  # 单文件名只报一次
    # B3 中文检查(去 NN_ 前缀)
    base = re.sub(r"^\d{2}[_-]", "", Path(name).stem)
    if not CHINESE_PATTERN.search(base):
        issues.append({"rule": "B3_文件名无中文", "name": name,
                       "reason": "去 NN_ 前缀后无中文字符,违反「中文文件名」要求"})
    return issues


def check_content(path: Path) -> List[Dict]:
    issues: List[Dict] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return issues
    if not lines:
        return issues

    type_hits = sum(1 for l in lines if TYPE_TABLE_PATTERN.search(l))
    ddl_hits = sum(1 for l in lines if DDL_PATTERN.search(l))
    table_lines = sum(1 for l in lines if "|" in l)
    total_signal = type_hits + ddl_hits

    # 启发式: 字段类型/DDL 命中 ≥10 条 且 ≥ 总表格行的 30%
    if total_signal >= 10 and table_lines > 0 and total_signal / max(table_lines, 1) >= 0.3:
        issues.append({
            "rule": "B2_内容技术分册",
            "name": path.name,
            "reason": f"字段类型表 {type_hits} 行 + DDL {ddl_hits} 行,占表格行 ≥30%,疑似技术分册",
        })
    return issues


def main() -> int:
    ap = argparse.ArgumentParser(description="PRD 多文件拆分白名单检查")
    ap.add_argument("target", help="PRD 目录")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    target = Path(args.target)
    # ⚠️ **exists 与 is_dir 必须分开判,不可合并**。
    #    原先只有 `if not target.is_dir(): return 0`,把「路径根本不存在」与「传入的是单个文件
    #    (合法的单文件模式,本检查不适用)」混为一谈,于是**一个手滑写错的路径 = 退出码 0 = 假绿**,
    #    整个白名单检查被静默放行、调用方还以为过了。这是四种退出码里最危险的一种。
    if not target.exists():
        print(f"错误: 路径不存在: {target}", file=sys.stderr)
        return 2
    if not os.access(target, os.R_OK):
        print(f"错误: 目录不可读(权限): {target}", file=sys.stderr)
        return 2
    if not target.is_dir():
        # ⚠️ `--json` 下也必须输出 JSON。这条分支 exit 0(成功),调用方**一定会**去解析
        #    stdout —— 打纯文本会让它 JSONDecodeError 崩掉。
        if args.json:
            print(json.dumps({"passed": True, "mode": "single_file",
                              "skipped": True, "files": 1}, ensure_ascii=False))
        else:
            print(f"⚠️  非目录,跳过(单文件模式): {target}")
        return 0

    md_files = sorted(target.rglob("*.md"))
    if not md_files:
        # 传了个目录却一个 .md 都没有 —— 与「单文件模式」不是一回事,多半是路径给错了层级。
        # 混为一谈就是又一个假绿:整个白名单检查静默跳过,调用方以为过了。
        print(f"错误: 目录内未发现任何 .md 文件: {target}", file=sys.stderr)
        return 2
    if len(md_files) == 1:
        # 单文件模式不适用本检查
        if args.json:
            print(json.dumps({"passed": True, "mode": "single_file",
                              "skipped": True, "files": len(md_files)},
                             ensure_ascii=False))
        else:
            print(f"⚠️  单文件模式(共 {len(md_files)} 个 .md),跳过白名单检查")
        return 0

    all_issues: List[Dict] = []
    for f in md_files:
        if f.name.startswith("00_"):  # 专职索引 00_索引.md 豁免(历史 00_*总览/主文档同豁免)
            continue
        all_issues.extend(check_filename(f.name))
        # 字典枚举白名单文件跳过 B2 内容嗅探(避免误报字典 PascalCase + 类型词)
        if ALLOWED_DICT_PATTERN.search(f.name):
            continue
        all_issues.extend(check_content(f))

    if args.json:
        print(json.dumps({
            "passed": len(all_issues) == 0,
            "files": len(md_files),
            "issue_count": len(all_issues),
            "issues": all_issues,
        }, ensure_ascii=False, indent=2))
        return 0 if not all_issues else 1

    if not all_issues:
        print(f"✅ 通过: {len(md_files)} 个 PRD 子文件,无违规分册")
        return 0
    print(f"❌ 不通过: 发现 {len(all_issues)} 处违规分册\n")
    for it in all_issues:
        print(f"  [{it['rule']}] {it['name']}: {it['reason']}")
    print("\n修复建议: 删除技术分册,字段/DDL/接口/技术栈类内容下沉到 dev-logic-architect。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
