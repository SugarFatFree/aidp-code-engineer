#!/usr/bin/env python3
"""不臆造兜底扫描(对应 dev-logic-architect 维度 19)

扫描详细设计文档(.md),识别疑似"兜底/降级/默认值/缺省/Mock 兜底"语句并输出清单,
供 Agent/作者逐条对照 PRD 溯源。脚本不做自动判定,只负责"找出来给人看"。

退出码:
  0  无疑似兜底,或全部已显式标 🔧 暂行方案
  1  存在疑似兜底但未标 🔧 暂行方案(需人工溯源)
     **或** 存在 Mock 兜底(强制不通过,无论是否标暂行方案)
     ⚠️ Mock 兜底曾单用退出码 2,与全仓统一约定「2 = 入参错」撞码——调用方若按约定
        把 2 当入参错处理,会把「Mock 兜底零容忍」这一最严重违规静默放过。已并入 1;
        是否 Mock 兜底改从 --json 的 is_mock_fallback 字段读。
  2  输入错误(路径不存在 / 无 .md 文件)——非维度违规,修正参数后重跑

用法:
  python check_no_fabricated_fallback.py <设计文档路径>
  python check_no_fabricated_fallback.py <设计文档目录>
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
}

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


# ⚠️ **禁令语境护栏**（与 check_lock_strategy.py 同源）：设计文档必然要写出反模式本身才能禁止它。
#    没有这道护栏时，「不降级」「严禁降级」「接口失败时禁止 fallback 到 mock 数据」这类**合规禁令句**
#    全部被判违规——而 assets/api-template.md 的错误契约行**强制**要求写「不降级：整单失败上抛，禁返空列表」，
#    即照本 SKILL 模板产出的设计必挂在本硬门上（假红灯）。
# ⚠️ 沿用 check_lock_strategy.py 的取舍：护栏**不含「避免」**——它常作动机出现在违规句里
#    （「下游超时仍返回 200，避免前端报错弹窗」），加了就漏真违规。
# ⚠️ **词表刻意收窄，勿改回宽表**：上一版把 check_lock_strategy.py 的词表整段照抄
#    过来，但两处护栏作用对象不同 —— 那边作用于**锁技术名**所在行，「不使用/未使用/无需」确实
#    表示"没用这个锁"；本脚本作用于**兜底行为句**，而这些词在中文设计文档里是**普通描述词、
#    routinely 出现在违规句内部**。实测宽表导致：
#      「接口失败时降级为 mock 数据，无需报错」   → 命中「无需」整行跳过（Mock 兜底漏报！）
#      「权限校验不通过时默认放行，展示只读视图」 → 命中「不通过」整行跳过（fail-open 漏报！）
#      「若接口异常，回退到缓存快照，不需要额外提示」→ 命中「不需要」整行跳过
#    且那次照抄**没有修复它声称要修的任何问题** —— `assets/api-template.md` 在加护栏之前
#    就已经是 rc=0（已实测复核），动机本身是未经验证的臆断。净效果：收益 0，
#    代价是 Critical「Mock 兜底零容忍」整档失效。
#    故只保留**真正的禁令标记**；「避免」照旧不在表内（它常作动机出现在违规句里）。
NEGATION_GUARD_RE = re.compile(
    r"严禁|禁止|不得|不许|不可以|勿|杜绝|反模式|错误示范|❌|反例|不降级|不回退")


def scan_file(path: Path, root: Path) -> List[Dict]:
    findings: List[Dict] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    try:  # Python 3.8 兼容:不用 3.9+ 的 is_relative_to
        rel = str(path.relative_to(root))
    except ValueError:
        rel = str(path)

    lines = text.splitlines()
    for category, patterns in FALLBACK_PATTERNS.items():
        for pat in patterns:
            cre = re.compile(pat, re.IGNORECASE)
            for i, line in enumerate(lines):
                if not cre.search(line):
                    continue
                # 禁令语境整行跳过（见 NEGATION_GUARD_RE 上方注释）
                if NEGATION_GUARD_RE.search(line):
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
    out.append("=== 不臆造兜底扫描(维度 19) ===")
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
            tag = "✅ 已标暂行方案" if it["has_provisional_marker"] else "❌ 未溯源"
            out.append(f"  - [{tag}] {it['file']}:{it['line']}  {it['snippet']}")
        out.append("")
    out.append("⚠️ 请逐条对照 PRD/上游需求文档溯源:")
    out.append('  - 能在 PRD 找到对应描述 → 在设计中补"上游引用块"标 PRD 章节+行号')
    out.append("  - PRD 未覆盖但需要保留 → 移到 Module E 待澄清清单,显式标 🔧 暂行方案(Agent 推断)")
    out.append("  - 行业惯例为快速失败 → 删除该兜底,改为抛出标准错误码")
    out.append("  - Mock 兜底 → 强制删除(下游 code-verification-loop 维度 2 零 Mock 容忍)")
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
    for f in md_files:
        all_findings.extend(scan_file(f, root))

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
