#!/usr/bin/env python3
"""不臆造兜底扫描(对应 ux-logic-extractor 维度 12)

扫描研发 PRD 文档(.md),识别疑似"兜底/降级/默认值/缺省/Mock 兜底/缓存机制臆造"语句并输出清单,
供 Agent/作者逐条对照产品需求文档/原型溯源。脚本对 **Mock 兜底(退出码 1,原 2)** 与 **未标暂行方案的疑似兜底(退出码 1)** 判错;其余情形仅列清单供逐条溯源、不判错(退出码 0)。⚠️ 别把退出码 1 当噪声放过——维度 12 是始终必查的 Critical。

覆盖类别:数据源兜底 / Mock 兜底(强制不通过) / 字段兜底 / 业务规则兜底 / 权限兜底 /
状态兜底 / 加载兜底 / 缓存机制臆造(Redis 缓存/本地缓存字典/接口响应缓存 N 分钟等,
对应 SKILL.md「缓存机制臆造(Critical)」;已标 ❓ 待澄清 / 🔧 暂行方案 / "不缓存"的合法处置放行)。

允许的灰区(自动放行,不报警):
- A 类异常处理:错误提示/Toast/重试按钮/抛出错误码
- C 类空状态/加载态/错误态 UI 推断:暂无数据/骨架屏/Spinner/搜索无结果引导

强制不通过(无论是否标暂行方案):
- Mock 兜底(下游 dev-logic-architect 维度 19 + code-verification-loop 维度 2 均强制移除)

退出码:
  0  无疑似兜底,或全部已显式标 🔧 Agent 暂行方案
  1  存在疑似兜底但未标 🔧 Agent 暂行方案(需人工对照产品需求文档/原型溯源)
     **或** 存在 Mock 兜底(强制不通过)
     ⚠️ Mock 兜底曾单用退出码 2,与全仓统一约定「2 = 入参错」撞码——调用方若按约定
        把 2 当入参错处理,会把「Mock 兜底零容忍」这一最严重违规静默放过。已并入 1;
        是否 Mock 兜底改从 --json 的 is_mock_fallback 字段读。
  2  输入错误(路径不存在 / 无 .md 文件)——非维度违规,修正参数后重跑

用法:
  python check_no_fabricated_fallback.py <PRD 路径>
  python check_no_fabricated_fallback.py <PRD 目录>
  python check_no_fabricated_fallback.py <路径> --json
  python check_no_fabricated_fallback.py <路径> --strict   # 任何疑似都返回非零

输入接受单文件(.md)或目录(批量加载所有 .md)。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# 兜底关键词分类
FALLBACK_PATTERNS = {
    "数据源兜底": [
        r"接口[失异][败常](?:时|后)?[^\n。]{0,30}(?:回退|降级|fallback|mock|缓存|静态|示例|占位)",
        r"(?:加载|请求|拉取)失败[^\n。]{0,30}(?:回退|降级|显示\s*(?:静态|示例|默认|mock|缓存))",
        r"(?:回退|降级)\s*(?:到|为)\s*(?:mock|静态|示例|缓存|本地)",
        r"上次(?:成功的?)?快照",
        r"内置示例数据",
    ],
    "Mock 兜底(强制不通过)": [
        r"接口[失异][败常](?:时|后)?[^\n。]{0,40}(?:mock|Mock)",
        r"(?:回退|降级|fallback)[^\n。]{0,20}(?:mock|Mock)",
        r"mock\s*(?:数据|接口)\s*(?:作为)?(?:兜底|降级|备用)",
        r"调用\s*[/\w]+mock[/\w-]*\s*(?:回退|兜底)",
    ],
    "字段兜底": [
        r"(?:字段|值)\s*为空(?:时|的话)?[^\n。]{0,30}(?:显示|默认|回退|展示)\s*(?:N/A|横线|--+|空字符串|0\b)",
        r"(?:NULL|null)\s*(?:时|的话)?[^\n。]{0,20}(?:显示|展示)\s*(?:N/A|横线|--+|0\b)",
    ],
    "业务规则兜底": [
        r"(?:如|若)\s*未\s*配置[^\n。]{0,30}(?:则\s*)?(?:默认|按|走)",
        r"未\s*指定\s*(?:时|的话)?[^\n。]{0,30}(?:默认|采用|按)",
    ],
    "权限兜底": [
        r"无\s*权限\s*(?:时|的话)?[^\n。]{0,30}(?:显示|降级|只读|展示)",
        r"未\s*授权\s*(?:时|的话)?[^\n。]{0,30}(?:显示|降级|只读)",
    ],
    "状态兜底": [
        r"(?:未知|其他|枚举\s*外)[^\n。]{0,20}(?:状态|值)\s*[^\n。]{0,15}(?:显示|归类|默认)\s*为",
        r"非\s*预定义[^\n。]{0,20}(?:显示|归类|默认)\s*为",
    ],
    "加载兜底": [
        r"加载失败[^\n。]{0,30}(?:骨架屏|占位|示例|静态|mock)",
    ],
    # 缓存机制臆造(对应 SKILL.md「缓存机制臆造(Critical)」+ 维度 12 checklist):
    # PRD 未说"需要缓存"却自行添加"使用 Redis 缓存/本地缓存字典/接口响应缓存 N 分钟"等
    # 技术缓存机制描述。命中的合法处置(标 ❓ 待澄清 / 🔧 暂行方案 / 明确"不缓存"/"是否缓存")
    # 由 CACHE_LEGIT_RE 就地放行,避免误伤隐藏逻辑表里"缓存策略:❓ 待澄清"这类正确写法。
    "缓存机制臆造": [
        r"使用\s*Redis\s*缓存",
        r"Redis\s*缓存\s*(?:接口|响应|数据|字典)",
        r"本地缓存\s*(?:字典|数据|接口响应)",
        r"接口响应\s*缓存",
        r"响应\s*缓存\s*\d+",
        r"缓存\s*\d+\s*(?:秒|分钟|分|小时|min|h)\b",
    ],
}

# 缓存机制臆造的合法处置上下文(命中即放行):已标待澄清/暂行方案,或明确否定/疑问语气。
# 对应 SKILL.md「缓存策略:❓ 待澄清」「🔧 暂行方案(建议使用缓存，待用户确认)」正确写法。
CACHE_LEGIT_RE = re.compile(r"待澄清|暂行方案|严禁|不缓存|不做缓存|是否缓存|❓|🔧")

# 标记为"暂行方案"则不报警(允许在 Module E 中显式声明)
PROVISIONAL_MARKER_RE = re.compile(r"🔧\s*暂行方案|暂行方案\s*\(Agent\s*推断\)")
# 标记为"异常处理告知/重试/错误码",这类不算兜底
LEGIT_ERROR_HANDLING_RE = re.compile(
    r"(?:错误提示|Toast|Message|重试按钮|重试机制|跳转登录|抛出.*错误码|记录日志|监控告警|Sentry|失败抛出)"
)
# 空状态 / 加载态 / 错误态 UI 推断 — 允许,不算数据源兜底
UI_EMPTY_STATE_RE = re.compile(
    r"(?:暂无数据|无数据|没有数据|空状态|空列表|空插画|无结果|无匹配|未找到|"
    r"占位卡片|占位图|skeleton|骨架屏|Spinner|loading|加载中|加载动画|进度条|"
    r"引导按钮|引导操作|创建按钮|添加按钮|清空筛选|返回上一级)"
)


def find_md_files(path: Path) -> List[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(path.rglob("*.md"))
    return []


def scan_file(path: Path, root: Path, read_errors: Optional[List[Dict]] = None) -> List[Dict]:
    findings: List[Dict] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        # ⚠️ 读不出来 ≠ 没有违规:早期这里直接 `return findings`,一份读不出的 PRD
        #    等价于「零违规」→ exit 0 假绿。现登记给 main() 判环境错。
        if read_errors is not None:
            read_errors.append({"file": str(path), "read_error": str(exc)})
        return findings
    try:
        rel = str(path.relative_to(root))
    except ValueError:
        rel = str(path)

    lines = text.splitlines()
    seen: set = set()  # (line, category) 去重:同一行被同类多个正则命中只报一次
    for category, patterns in FALLBACK_PATTERNS.items():
        for pat in patterns:
            cre = re.compile(pat, re.IGNORECASE)
            for i, line in enumerate(lines):
                if not cre.search(line):
                    continue
                if (i, category) in seen:
                    continue
                # 缓存机制臆造:已标 ❓ 待澄清 / 🔧 暂行方案 / 明确"不缓存/是否缓存"的行放行
                if category == "缓存机制臆造" and CACHE_LEGIT_RE.search(line):
                    continue
                # 跳过已标"暂行方案"的语句(同行或相邻 2 行内)
                window = "\n".join(lines[max(0, i - 2): min(len(lines), i + 3)])
                has_provisional = bool(PROVISIONAL_MARKER_RE.search(window))
                has_legit_error = bool(LEGIT_ERROR_HANDLING_RE.search(line))
                has_ui_empty_state = bool(UI_EMPTY_STATE_RE.search(line))
                has_real_data_substitute = bool(re.search(
                    r"(?:静态|示例|mock|Mock|缓存|降级\s*视图|默认数据|占位数据)", line
                ))
                # 异常处理(错误提示/重试/错误码)同行命中且无替代数据词,跳过
                if has_legit_error and not has_real_data_substitute:
                    continue
                # 空状态/加载态 UI 推断(无替代真实数据词),跳过
                if has_ui_empty_state and not has_real_data_substitute:
                    continue
                seen.add((i, category))
                findings.append({
                    "file": rel,
                    "line": i + 1,
                    "category": category,
                    "snippet": line.strip()[:200],
                    "has_provisional_marker": has_provisional,
                    "is_mock_fallback": category.startswith("Mock"),
                })
    return findings


def render_text(findings: List[Dict]) -> str:
    out: List[str] = []
    out.append("=== 不臆造兜底扫描(维度 12) ===")
    if not findings:
        out.append("\n✅ 未发现疑似兜底语句")
        return "\n".join(out)

    by_category: Dict[str, List[Dict]] = {}
    for f in findings:
        by_category.setdefault(f["category"], []).append(f)

    out.append(f"\n共发现 {len(findings)} 条疑似兜底语句:\n")
    for cat, items in by_category.items():
        marker = "🔴" if cat.startswith("Mock") else "🟡"
        out.append(f"{marker} {cat} ({len(items)} 条)")
        for it in items:
            tag = "✅ 已标 Agent 暂行方案" if it["has_provisional_marker"] else "❌ 未溯源"
            out.append(f"  - [{tag}] {it['file']}:{it['line']}  {it['snippet']}")
        out.append("")
    out.append("⚠️ 请逐条对照产品需求文档/原型溯源:")
    out.append('  - 能在产品需求文档找到对应描述 → 在 PRD 中补"上游引用块"标章节+行号')
    out.append("  - 产品文档未覆盖但需要保留 → 移到「十、待澄清问题清单」,显式标 🔧 Agent 暂行方案")
    out.append("  - 行业惯例为快速失败 → 删除该兜底,改为错误提示 + 重试按钮")
    out.append("  - Mock 兜底 → 强制删除(下游 dev-logic-architect 维度 19 + code-verification-loop 维度 2 零 Mock 容忍)")
    return "\n".join(out)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", type=Path, help="设计文档路径(单文件或目录)")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    parser.add_argument("--strict", action="store_true", help="任何疑似(包括已标暂行方案)都返回非零")
    args = parser.parse_args(argv)

    if not args.path.exists():
        print(f"错误: 路径不存在 {args.path}", file=sys.stderr)
        return 2

    root = args.path if args.path.is_dir() else args.path.parent
    md_files = find_md_files(args.path)
    if not md_files:
        print("⚠️ 未发现任何 .md 文件", file=sys.stderr)
        return 2

    all_findings: List[Dict] = []
    read_errors: List[Dict] = []
    for f in md_files:
        all_findings.extend(scan_file(f, root, read_errors))
    if read_errors and len(read_errors) == len(md_files):
        for r in read_errors:
            print(f"错误: 无法读取 {r['file']}: {r['read_error']}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(all_findings, ensure_ascii=False, indent=2))
    else:
        print(render_text(all_findings))

    has_mock = any(f["is_mock_fallback"] for f in all_findings)
    has_unprovisional = any(not f["has_provisional_marker"] and not f["is_mock_fallback"] for f in all_findings)

    if has_mock:
        return 1
    if has_unprovisional:
        return 1
    if args.strict and all_findings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
