#!/usr/bin/env python3
"""
第三方接口对接清单状态分析器
分析执行计划中的"第三方接口对接清单"表格,统计开发和联调进度。

使用方式:
  python analyze_third_party_progress.py <执行计划路径>
  python analyze_third_party_progress.py <执行计划路径> --json
"""

import argparse
import json
import re
import sys
from pathlib import Path

# 注:更具体的状态(partial/blocked)必须排在 completed 之前——
# "部分通过" 含子串 "通过",若 completed 先匹配会把 "部分通过" 误归 "已完成"。
STATUS_EMOJI = {
    "pending": ["⏳", "待开始", "待联调", "TODO"],
    "in_progress": ["🔄", "开发中", "联调中", "进行中"],
    "partial": ["⚠️", "部分通过", "部分完成"],
    "blocked": ["⛔", "阻塞"],
    "completed": ["✅", "完成", "通过"],
}


def classify_status(text: str) -> str:
    """将状态文本分类为 pending/in_progress/completed/blocked/partial"""
    text = text.strip()
    for status, markers in STATUS_EMOJI.items():
        for marker in markers:
            if marker in text:
                return status
    return "unknown"


def extract_checklist_rows(content: str) -> list:
    """提取对接清单表格的数据行"""
    rows = []

    # 查找"第三方接口对接清单"章节
    pattern = r'(?:第三方接口对接清单|对接清单|API-T)[^\n]*\n(.*?)(?=^#{1,6}\s|\Z)'
    match = re.search(pattern, content, re.DOTALL | re.MULTILINE | re.IGNORECASE)

    if not match:
        return rows

    section = match.group(1)

    # 解析表格行(以 API-T 开头的行,或有 9 列以上的表格行)
    for line in section.split('\n'):
        line = line.strip()
        if not line.startswith('|'):
            continue
        if '---' in line:
            continue

        cells = [c.strip() for c in line.split('|') if c.strip()]

        # 需要至少 7 列才可能是有效对接清单行
        if len(cells) < 7:
            continue

        # 第一列通常是接口编号(API-T01) 或序号
        if not (re.match(r'API-T\d+', cells[0], re.IGNORECASE) or re.match(r'^\d+$', cells[0])):
            continue

        row = {
            "id": cells[0],
            "system": cells[1] if len(cells) > 1 else "",
            "direction": cells[2] if len(cells) > 2 else "",
            "name": cells[3] if len(cells) > 3 else "",
            "task": cells[4] if len(cells) > 4 else "",
            "contact": cells[5] if len(cells) > 5 else "",
            "ready_date": cells[6] if len(cells) > 6 else "",
            "dev_status": cells[7] if len(cells) > 7 else "⏳ 待开始",
            "joint_status": cells[8] if len(cells) > 8 else "⏳ 待联调",
        }
        row["dev_status_class"] = classify_status(row["dev_status"])
        row["joint_status_class"] = classify_status(row["joint_status"])
        rows.append(row)

    return rows


def summarize(rows: list) -> dict:
    """汇总统计"""
    total = len(rows)
    if total == 0:
        return {
            "total": 0,
            "dev_progress": {},
            "joint_progress": {},
            "blocked": [],
            "completion_rate": 0,
        }

    dev_counts = {"pending": 0, "in_progress": 0, "completed": 0, "blocked": 0, "partial": 0, "unknown": 0}
    joint_counts = {"pending": 0, "in_progress": 0, "completed": 0, "blocked": 0, "partial": 0, "unknown": 0}
    blocked = []

    for row in rows:
        dev_counts[row["dev_status_class"]] = dev_counts.get(row["dev_status_class"], 0) + 1
        joint_counts[row["joint_status_class"]] = joint_counts.get(row["joint_status_class"], 0) + 1

        if row["dev_status_class"] == "blocked" or row["joint_status_class"] == "blocked":
            blocked.append(row)

    completion_rate = joint_counts["completed"] / total * 100

    return {
        "total": total,
        "dev_progress": dev_counts,
        "joint_progress": joint_counts,
        "blocked": blocked,
        "completion_rate": completion_rate,
    }


def format_report(rows: list, summary: dict) -> str:
    """生成 Markdown 报告"""
    lines = []
    lines.append("# 第三方接口对接进度报告")
    lines.append("")

    total = summary["total"]
    if total == 0:
        lines.append("**未找到第三方接口对接清单。**")
        return '\n'.join(lines)

    lines.append(f"**总接口数:** {total}")
    lines.append(f"**联调完成率:** {summary['completion_rate']:.1f}% ({summary['joint_progress']['completed']}/{total})")
    lines.append("")

    lines.append("## 开发状态分布")
    lines.append("")
    lines.append("| 状态 | 数量 | 占比 |")
    lines.append("|------|------|------|")
    for status in ["completed", "in_progress", "partial", "pending", "blocked"]:
        count = summary["dev_progress"].get(status, 0)
        if count > 0:
            pct = count / total * 100
            status_name = {
                "completed": "✅ 完成",
                "in_progress": "🔄 开发中",
                "partial": "⚠️ 部分完成",
                "pending": "⏳ 待开始",
                "blocked": "⛔ 阻塞",
            }[status]
            lines.append(f"| {status_name} | {count} | {pct:.1f}% |")

    lines.append("")
    lines.append("## 联调状态分布")
    lines.append("")
    lines.append("| 状态 | 数量 | 占比 |")
    lines.append("|------|------|------|")
    for status in ["completed", "in_progress", "partial", "pending", "blocked"]:
        count = summary["joint_progress"].get(status, 0)
        if count > 0:
            pct = count / total * 100
            status_name = {
                "completed": "✅ 通过",
                "in_progress": "🔄 联调中",
                "partial": "⚠️ 部分通过",
                "pending": "⏳ 待联调",
                "blocked": "⛔ 阻塞",
            }[status]
            lines.append(f"| {status_name} | {count} | {pct:.1f}% |")

    if summary["blocked"]:
        lines.append("")
        lines.append("## ⛔ 阻塞接口(需重点关注)")
        lines.append("")
        lines.append("| 接口 | 对接系统 | 开发状态 | 联调状态 | 对接人 |")
        lines.append("|------|---------|---------|---------|--------|")
        for row in summary["blocked"]:
            lines.append(
                f"| {row['id']} {row['name']} | {row['system']} | "
                f"{row['dev_status']} | {row['joint_status']} | {row['contact']} |"
            )

    lines.append("")
    lines.append("## 建议行动")
    lines.append("")
    if summary["joint_progress"].get("blocked", 0) > 0:
        lines.append(f"- 🔴 优先跟进 {summary['joint_progress']['blocked']} 个阻塞接口,联系第三方对接人")
    if summary["dev_progress"].get("pending", 0) > total * 0.5:
        lines.append(f"- 🟡 超过一半接口未开始开发,建议重新评估排期")
    if summary["joint_progress"]["completed"] > 0:
        lines.append(f"- ✅ {summary['joint_progress']['completed']} 个接口已联调通过,可评估是否灰度上线")

    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description="分析第三方接口对接进度")
    parser.add_argument("plan_doc", help="执行计划文档路径")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    parser.add_argument("-o", "--output", help="输出文件路径")
    args = parser.parse_args()

    plan_path = Path(args.plan_doc)
    if not plan_path.exists():
        print(f"错误: 文件不存在: {plan_path}", file=sys.stderr)
        sys.exit(1)

    content = plan_path.read_text(encoding='utf-8')
    rows = extract_checklist_rows(content)
    summary = summarize(rows)

    if args.json:
        output = json.dumps({
            "source": str(plan_path),
            "summary": {k: v for k, v in summary.items() if k != "blocked"},
            "rows": rows,
            "blocked_count": len(summary["blocked"]),
        }, ensure_ascii=False, indent=2)
    else:
        output = format_report(rows, summary)

    if args.output:
        Path(args.output).write_text(output, encoding='utf-8')
        print(f"✓ 已写入: {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()
