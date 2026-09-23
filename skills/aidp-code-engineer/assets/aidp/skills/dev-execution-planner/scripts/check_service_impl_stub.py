#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Service 实现层占位检测脚本

对应本 SKILL 检查项 9.8「接口可用性核验」/ SKILL.md「第一步半之二」
(概念源自 dev-logic-architect 核心原则 18「代码事实采集深度铁律」)。

实测发现: 设计期扫描既有代码判定"接口是否沿用"时,只看 Controller 层注解,
未读 Service 实现层方法体,导致 `throw new BizException(501)` 这种占位实现
被误判为"✅ 沿用已有",联调阶段才暴露问题。

本脚本扫描指定代码目录下的 Service 实现类,识别占位实现并输出清单。

检测项(L3 命中任一即"未实现"):
  S1. throw NotImplementedException / BizException(5xx, "未实现")
      / UnsupportedOperationException / NotImplementedError
  S2. return null / 空集合 / 空对象 + 方法体仅 1-2 行
  S3. return mockData / 硬编码假数据(字段含 mock/test/demo 语义)
  S4. // TODO: 实现 / // FIXME: 占位 + 空方法体
  S5. @Deprecated 注解 + 提示已废弃
  S6. 仅 log.warn("接口未实现") 后直接返回

支持语言: Java / Kotlin / TypeScript / Python / Go / C# 主流后端

使用:
  python check_service_impl_stub.py <代码根目录>
  python check_service_impl_stub.py <代码根目录> --json
  python check_service_impl_stub.py <代码根目录> --method <方法名>   # 仅扫指定方法
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# 占位实现检测正则(按严重度从 Critical 到 Important)
STUB_PATTERNS = {
    "S1_throw_unimplemented": [
        r"throw\s+new\s+(BizException|BusinessException)\s*\(\s*5\d{2}\s*[,，]\s*[\"'].*?(未实现|占位|TODO|未完成|not implemented)",
        r"throw\s+new\s+(NotImplementedException|UnsupportedOperationException|UnsupportedError)\s*\(",
        r"raise\s+(NotImplementedError|NotImplemented)",
        r"panic\s*\(\s*[\"'](not implemented|未实现|占位)",
        r"throw\s+(NotImplementedError|UnsupportedOperationException)\s*\(",
    ],
    "S2_return_empty": [
        # return null / 空 List / 空对象 — 但要求方法体很短
        r"^\s*return\s+(null|None|nil|undefined|new\s+ArrayList<>\(\)|Collections\.emptyList\(\)|Lists\.newArrayList\(\)|new\s+\w+VO\(\)|new\s+\w+DTO\(\))\s*;?\s*$",
    ],
    "S3_return_mock": [
        r"return\s+\w*([Mm]ock|[Ff]ake|[Dd]emo|[Tt]est)\w*Data",
        r"return\s+[\"'](mock|test|demo|fake)",
    ],
    "S4_todo_placeholder": [
        r"//\s*(TODO|FIXME|XXX)\s*[:：].*(实现|占位|placeholder|to.?implement|后续完善)",
        r"#\s*(TODO|FIXME|XXX)\s*[:：].*(实现|占位|placeholder|to.?implement)",
    ],
    "S5_deprecated": [
        r"@Deprecated\s*(?:\(.*?\))?",
        r"//\s*已废弃|//\s*deprecated|/\*\*?\s*@deprecated",
    ],
    "S6_log_only": [
        r"log\.warn\s*\(\s*[\"'].*未实现",
        r"logger\.warn\s*\(\s*[\"'].*not implemented",
    ],
}

# 文件扩展名 → 语言
LANG_EXT = {
    ".java": "java",
    ".kt": "kotlin",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".py": "python",
    ".go": "go",
    ".cs": "csharp",
}

# Service 实现层文件名模式
SERVICE_IMPL_FILE_PATTERNS = [
    re.compile(r".*ServiceImpl\.(java|kt)$"),  # Java/Kotlin: XxxServiceImpl
    re.compile(r".*\.service\..*\.(ts|js|py)$"),  # TS/JS/Python service 目录
    re.compile(r".*[/\\]service[/\\].*\.(ts|js|py)$"),
    re.compile(r".*[/\\]services[/\\].*\.(ts|js|py)$"),
    re.compile(r".*Service\.(go|cs)$"),
]

# 方法定义粗略匹配
METHOD_DEF_PATTERNS = {
    "java": re.compile(r"^\s*(?:public|private|protected)?\s*(?:static\s+|final\s+|abstract\s+)*[\w<>\[\],\s]+?\s+(\w+)\s*\([^)]*\)\s*(?:throws\s+[\w,\s]+)?\s*\{", re.MULTILINE),
    "kotlin": re.compile(r"^\s*(?:override\s+|open\s+|public\s+|private\s+|internal\s+)*fun\s+(\w+)\s*\(", re.MULTILINE),
    "typescript": re.compile(r"^\s*(?:public|private|protected|async)?\s*(?:async\s+)?(\w+)\s*\([^)]*\)\s*(?::\s*[\w<>\[\],\s|]+)?\s*\{", re.MULTILINE),
    "python": re.compile(r"^\s*(?:async\s+)?def\s+(\w+)\s*\(", re.MULTILINE),
    "go": re.compile(r"^\s*func\s+(?:\([^)]+\)\s+)?(\w+)\s*\(", re.MULTILINE),
    "csharp": re.compile(r"^\s*(?:public|private|protected|internal)\s+(?:async\s+|static\s+|virtual\s+|override\s+)*[\w<>\[\],\s]+\s+(\w+)\s*\(", re.MULTILINE),
}


def detect_language(path: Path) -> Optional[str]:
    return LANG_EXT.get(path.suffix.lower())


def is_service_impl(path: Path) -> bool:
    s = str(path)
    return any(p.match(s) for p in SERVICE_IMPL_FILE_PATTERNS)


def find_service_impl_files(root: Path) -> List[Path]:
    """查找代码根目录下的所有 Service 实现文件"""
    candidates: List[Path] = []
    skip_dirs = {"node_modules", "target", "build", "dist", ".git", ".idea", "__pycache__", "venv", ".venv"}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(skip in path.parts for skip in skip_dirs):
            continue
        if detect_language(path) and is_service_impl(path):
            candidates.append(path)
    return sorted(candidates)


def extract_method_bodies(content: str, lang: str) -> List[Tuple[str, int, str]]:
    """提取每个方法的 (方法名, 起始行号, 方法体)

    简化实现:基于花括号配对(对 Python 用缩进)
    """
    methods: List[Tuple[str, int, str]] = []

    if lang == "python":
        # Python 按缩进分块
        pattern = METHOD_DEF_PATTERNS["python"]
        for m in pattern.finditer(content):
            method_name = m.group(1)
            start = m.start()
            line_no = content[:start].count("\n") + 1
            # 取 def 后到下一个同级 def 或类结束的行
            after = content[m.end():]
            lines = after.split("\n")
            # 找出基础缩进
            body_lines = []
            base_indent = None
            for line in lines[:50]:  # 最多看 50 行
                stripped = line.lstrip()
                if not stripped or stripped.startswith("#"):
                    body_lines.append(line)
                    continue
                indent = len(line) - len(stripped)
                if base_indent is None:
                    base_indent = indent
                elif indent < base_indent and stripped:
                    break
                body_lines.append(line)
            methods.append((method_name, line_no, "\n".join(body_lines)))
        return methods

    # Java / Kotlin / TS / Go / C# — 基于花括号
    pattern = METHOD_DEF_PATTERNS.get(lang)
    if not pattern:
        return methods

    for m in pattern.finditer(content):
        method_name = m.group(1)
        # 排除常见误匹配(Controller/构造器/getter)
        if method_name in {"if", "for", "while", "switch", "return", "new", "class", "interface", "enum"}:
            continue
        start = m.end() - 1  # 指向 {
        line_no = content[:m.start()].count("\n") + 1
        # 配对花括号
        depth = 1
        i = start + 1
        while i < len(content) and depth > 0:
            if content[i] == "{":
                depth += 1
            elif content[i] == "}":
                depth -= 1
            i += 1
        body = content[start + 1:i - 1]
        methods.append((method_name, line_no, body))

    return methods


def detect_stub_in_method(method_body: str) -> List[Dict]:
    """检测方法体内是否含占位实现,返回命中的 stub 类型清单"""
    hits: List[Dict] = []
    body_clean = method_body.strip()
    line_count = body_clean.count("\n") + 1 if body_clean else 0

    for stub_type, patterns in STUB_PATTERNS.items():
        for pat in patterns:
            m = re.search(pat, method_body, re.MULTILINE)  # S2 的 ^...$ 锚点需逐行匹配,否则多行方法体漏检
            if not m:
                continue
            # S2(空返回)需要方法体很短才算
            if stub_type == "S2_return_empty" and line_count > 5:
                continue
            hits.append({
                "type": stub_type,
                "match": m.group(0)[:100],
                "severity": "Critical" if stub_type in ("S1_throw_unimplemented", "S3_return_mock") else "Important",
            })
            break  # 同类只算一次
    return hits


def analyze_file(path: Path) -> Dict:
    """分析单个 Service 实现文件"""
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return {"file": str(path), "error": str(e)}

    lang = detect_language(path) or "unknown"
    methods = extract_method_bodies(content, lang)
    content_lines = content.split("\n")

    stubs: List[Dict] = []
    for method_name, line_no, body in methods:
        hits = detect_stub_in_method(body)
        # S5: @Deprecated / 已废弃 注解写在方法签名上方,不在方法体内,需单独扫签名前 3 行
        if not any(h["type"] == "S5_deprecated" for h in hits):
            preamble = "\n".join(content_lines[max(0, line_no - 4):line_no])
            for pat in STUB_PATTERNS["S5_deprecated"]:
                dm = re.search(pat, preamble)
                if dm:
                    hits.append({"type": "S5_deprecated", "match": dm.group(0)[:100], "severity": "Important"})
                    break
        if hits:
            stubs.append({
                "method": method_name,
                "line": line_no,
                "stub_types": [h["type"] for h in hits],
                "severity": "Critical" if any(h["severity"] == "Critical" for h in hits) else "Important",
                "evidence": hits[0]["match"],
            })

    return {
        "file": str(path),
        "language": lang,
        "method_count": len(methods),
        "stub_methods": stubs,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Service 实现层占位检测(对应本 SKILL 检查项 9.8;概念源自 dev-logic-architect 核心原则 18)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("root", type=Path, help="代码根目录")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    ap.add_argument("--method", help="只关心指定方法名")
    ap.add_argument("--strict", action="store_true", help="严格模式:Important 也返回非零退出码")
    args = ap.parse_args()

    if not args.root.exists():
        print(f"❌ 路径不存在: {args.root}", file=sys.stderr)
        return 2

    files = find_service_impl_files(args.root)
    if not files:
        msg = f"⚠️  未发现 Service 实现文件(扫描目录: {args.root})"
        if args.json:
            print(json.dumps({"passed": True, "skipped": True, "msg": msg}, ensure_ascii=False, indent=2))
        else:
            print(msg)
        return 0

    aggregated = {
        "scan_root": str(args.root),
        "service_impl_files": len(files),
        "results": [],
        "total_stub_methods": 0,
        "critical_count": 0,
        "important_count": 0,
        "passed": True,
    }

    for f in files:
        result = analyze_file(f)
        if "error" in result:
            continue
        # 过滤指定方法
        if args.method:
            result["stub_methods"] = [m for m in result["stub_methods"] if m["method"] == args.method]
        if not result["stub_methods"]:
            continue
        aggregated["results"].append(result)
        for m in result["stub_methods"]:
            aggregated["total_stub_methods"] += 1
            if m["severity"] == "Critical":
                aggregated["critical_count"] += 1
            else:
                aggregated["important_count"] += 1

    # 判定退出码
    if aggregated["critical_count"] > 0:
        aggregated["passed"] = False
    elif args.strict and aggregated["important_count"] > 0:
        aggregated["passed"] = False

    if args.json:
        print(json.dumps(aggregated, ensure_ascii=False, indent=2))
    else:
        print(f"扫描 {aggregated['service_impl_files']} 个 Service 实现文件\n")
        if aggregated["total_stub_methods"] == 0:
            print("✅ 未发现占位实现")
        else:
            print(f"❌ 发现 {aggregated['total_stub_methods']} 处占位实现 "
                  f"(Critical: {aggregated['critical_count']}, Important: {aggregated['important_count']})\n")
            for r in aggregated["results"]:
                print(f"📄 {r['file']}")
                for m in r["stub_methods"]:
                    sev_icon = "🔴" if m["severity"] == "Critical" else "🟡"
                    print(f"  {sev_icon} L{m['line']}  {m['method']}()  [{', '.join(m['stub_types'])}]")
                    print(f"      证据: {m['evidence']}")
                print()
            print("修复建议: 设计文档中将这些接口标注为「🔧 待实现」或「🛰️ 外部系统接口」,")
            print("          严禁标注为「✅ 沿用已有」。详见 dev-logic-architect 核心原则 18。")

    return 0 if aggregated["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
