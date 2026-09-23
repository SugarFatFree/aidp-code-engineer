#!/usr/bin/env python3
"""
第三方接口对接清单生成器
从详细设计文档(B.7 外部依赖与集成方案)中提取所有第三方接口,
生成对接清单表格,供执行计划跟踪双方开发进度使用。

使用方式:
  python generate_third_party_checklist.py <详细设计文档路径>
  python generate_third_party_checklist.py <详细设计文档路径> --json
  python generate_third_party_checklist.py <详细设计文档路径> -o <输出路径>
"""

import argparse
import json
import re
import sys
from pathlib import Path
from datetime import datetime


def extract_third_party_interfaces(content: str) -> list:
    """
    从详细设计文档中提取第三方接口

    识别规则:
    - 查找 B.7 章节或标题含"外部依赖"、"集成方案"、"第三方"的章节
    - 识别"对外开放接口"和"调用第三方接口"两类
    - 提取接口名称、方向、对接系统
    """
    interfaces = []

    # 查找 B.7 章节内容 - 更宽松的匹配
    # 从 B.7 或包含"外部依赖"/"第三方系统对接"的标题开始,到下一个 B.x 或 C.x 或 Module 标题
    b7_patterns = [
        r'#{2,6}\s*B\.7[^\n]*\n(.*?)(?=#{2,6}\s*(?:B\.[89]|C\.|Module\s+[C-Z])|\Z)',
        r'#{2,6}\s*[^\n]*(?:外部依赖|集成方案|第三方系统对接)[^\n]*\n(.*?)(?=#{2,6}\s*(?:B\.[89]|C\.|Module)|\Z)',
    ]

    section = None
    for pattern in b7_patterns:
        match = re.search(pattern, content, re.DOTALL | re.IGNORECASE | re.MULTILINE)
        if match:
            section = match.group(1)
            break

    if not section:
        return interfaces

    # 识别子章节:对外开放的接口 vs 调用第三方的接口
    # 使用标记来划分两个方向
    outbound_keywords = ["对外开放", "我方对外开放", "开放给第三方", "供第三方调用", "方向 1", "方向1"]
    inbound_keywords = ["调用第三方", "我方调用", "需要第三方开放", "方向 2", "方向2"]

    # 按段落分析,每个段落分类为 outbound/inbound/unknown
    sections = re.split(r'(#{3,6}\s*[^\n]+)', section)

    current_direction = "未标注(需确认)"
    for i, part in enumerate(sections):
        if part.startswith('#'):
            # 这是一个标题,判断方向
            if any(kw in part for kw in outbound_keywords):
                current_direction = "我方对外开放"
            elif any(kw in part for kw in inbound_keywords):
                current_direction = "我方调用对方"
            # 如果标题本身包含接口名(#### 接口N: XXX 或 #### XXX接口)
            title_clean = re.sub(r'^#+\s*', '', part).strip()
            title_clean = re.sub(r'^(?:接口\s*\d+\s*[:：]?\s*)', '', title_clean)
            if _looks_like_interface_title(title_clean):
                interfaces.append({
                    "name": title_clean,
                    "direction": current_direction,
                    "source": "标题",
                })
        else:
            # 分析内容中的表格
            interfaces.extend(_extract_from_tables(part, current_direction, existing=interfaces))

    return interfaces


def _looks_like_interface_title(text: str) -> bool:
    """判断标题是否像接口名"""
    if not text or len(text) > 80:
        return False
    skip_keywords = [
        "外部依赖", "集成方案", "第三方系统对接", "对外开放", "调用第三方",
        "方向", "设计原则", "集成示例", "双向对接视角", "集成总览",
        "必须明确", "项目", "说明",
    ]
    for kw in skip_keywords:
        if kw in text and len(text) < 30:
            return False
    # 排除纯标点符号或无意义短串
    if len(re.sub(r'[一-鿿a-zA-Z0-9]', '', text)) > len(text) * 0.5:
        return False
    return True


def _extract_from_tables(block: str, direction: str, existing: list) -> list:
    """从文本块中提取表格中的接口名"""
    interfaces = []
    lines = block.split('\n')
    in_table = False
    header_passed = False
    for line in lines:
        stripped = line.strip()
        if '|' in stripped and '---' in stripped:
            in_table = True
            header_passed = True
            continue
        if in_table and header_passed and stripped.startswith('|'):
            cells = [c.strip() for c in stripped.split('|') if c.strip()]
            if cells and _looks_like_interface_name(cells[0]):
                name = cells[0]
                if not any(i['name'] == name for i in existing + interfaces):
                    interfaces.append({
                        "name": name,
                        "direction": direction,
                        "source": "表格",
                    })
        elif in_table and not stripped.startswith('|'):
            in_table = False
            header_passed = False
    return interfaces


def _looks_like_interface_name(text: str) -> bool:
    """判断文本是否像接口名"""
    if not text or len(text) < 2 or len(text) > 80:
        return False
    # 不应该是纯数字、表头关键词等
    skip_words = ["序号", "接口名称", "对接系统", "方向", "说明", "备注",
                  "API", "URL", "Method", "请求", "响应", "参数"]
    if text in skip_words:
        return False
    if text.startswith(('http', 'GET', 'POST', 'PUT', 'DELETE')):
        return False
    if text.startswith('/') and '/' in text[1:]:  # 看起来像 URL path
        return False
    # 至少包含中文或描述性词语
    has_chinese = bool(re.search(r'[一-鿿]', text))
    has_meaningful = bool(re.search(r'[a-zA-Z一-鿿]{2,}', text))
    return has_chinese or has_meaningful


def generate_checklist_markdown(interfaces: list) -> str:
    """生成对接清单 Markdown 表格"""
    if not interfaces:
        return "## 附录:第三方接口对接清单\n\n**本项目未识别到第三方接口对接需求。**\n"

    md = []
    md.append("## 附录:第三方接口对接清单")
    md.append("")
    md.append(f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    md.append(f"> 共识别 {len(interfaces)} 个第三方接口")
    md.append("")
    md.append("| 接口序号 | 对接系统 | 方向 | 接口名称 | 我方 Task | 第三方对接人 | 第三方预计就绪 | 我方开发状态 | 联调状态 |")
    md.append("|---------|---------|------|---------|----------|------------|-------------|------------|---------|")

    for i, iface in enumerate(interfaces, 1):
        seq = f"API-T{i:02d}"
        system = iface.get("system", "待确认")
        direction = iface["direction"]
        name = iface["name"]
        md.append(
            f"| {seq} | {system} | {direction} | {name} | 待分配 | 待确认 | 待确认 | ⏳ 待开始 | ⏳ 待联调 |"
        )

    md.append("")
    md.append("**状态说明:**")
    md.append("- 开发状态: ⏳ 待开始 / 🔄 开发中 / ✅ 完成 / ⛔ 阻塞")
    md.append("- 联调状态: ⏳ 待联调 / 🔄 联调中 / ✅ 通过 / ⚠️ 部分通过 / ⛔ 阻塞")
    md.append("")
    md.append("**使用指引:**")
    md.append("1. 为每个接口分配我方 Task 编号(如 Task 2.5、Task 3.8)")
    md.append("2. 记录第三方对接人姓名和联系方式")
    md.append("3. 与第三方对接人确认预计就绪时间")
    md.append("4. 每次推进开发/联调时更新状态列")
    md.append("")

    return '\n'.join(md)


def main():
    parser = argparse.ArgumentParser(description="从详细设计文档提取第三方接口清单")
    parser.add_argument("design_doc", help="详细设计文档路径")
    parser.add_argument("-o", "--output", help="输出文件路径(默认打印到标准输出)")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    args = parser.parse_args()

    design_path = Path(args.design_doc)
    if not design_path.exists():
        print(f"错误: 文件不存在: {design_path}", file=sys.stderr)
        sys.exit(1)

    content = design_path.read_text(encoding='utf-8')
    interfaces = extract_third_party_interfaces(content)

    if args.json:
        output = json.dumps({
            "source": str(design_path),
            "count": len(interfaces),
            "interfaces": interfaces,
        }, ensure_ascii=False, indent=2)
    else:
        output = generate_checklist_markdown(interfaces)

    if args.output:
        Path(args.output).write_text(output, encoding='utf-8')
        print(f"✓ 已写入: {args.output}")
        print(f"  识别接口数: {len(interfaces)}")
    else:
        print(output)


if __name__ == "__main__":
    main()
