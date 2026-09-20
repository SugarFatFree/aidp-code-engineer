#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
功能/数据/接口复用扫描脚本

对应 dev-logic-architect 核心原则 20「复用优先与去重」+ QR 检查项 27「复用识别完整性核验」。

实测发现: 设计期常常默判"新需求 = 全新设计",忽视代码仓中早已存在的同义实体/接口。
本脚本对设计文档标 🆕 新增 的实体/接口/数据表逐一反向扫描代码,识别"已存在的同义实现"。

扫描流程:
  1. 解析设计文档,提取 A.3 数据表、B.1 功规点、B.2 接口路径
  2. 对每个标 🆕 新增 / 未标的条目,在代码仓中扫描:
     - 实体名: entity/ + Entity.java + class XxxEntity / class Xxx 同名/相似名称
     - Mapper/Repository: Mapper.java / Repository.java 中的同名 SQL 查询方法
     - Service: Service.java 中的方法签名相似度
     - Controller: @RequestMapping path 相似度(同前缀/同后缀/同语义)
  3. 输出 ⚠️ 警示清单: 每条 🆕 条目附带"代码中已有 X (位置 Y),请确认是否复用"

退出码:
  0 = 无信号或仅警示(无强阻塞)
  1 = 检出未通过(存在应复用而未复用的强信号)
  2 = 入参错(设计文档 / 代码仓路径不存在,参数错误)——非产物违规,修正参数后重跑
      ⚠️ 「解析失败」曾归在 1,与「产物违规」同码,一次路径写错会被误报成设计缺陷(假红);
         且 --json 分支当时排在入参判定之前,人读模式返 2 而 --json 返 1、同一情形两个码。
         两处已统一为 2。

使用:
  python check_feature_reuse.py <设计文档路径> <代码根目录>
  python check_feature_reuse.py <设计文档路径> <代码根目录> --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ============================================================
# 设计文档解析
# ============================================================

# A.3 数据表声明: ## biz_user 表 / ## A.3 biz_user 表 / CREATE TABLE biz_user
TABLE_DECL_RE = re.compile(
    r"(?:^##+\s+(?:A\.3\s+)?|CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?)"
    r"`?([a-zA-Z_][a-zA-Z0-9_]+)`?\s*(?:表)?",
    re.MULTILINE | re.IGNORECASE,
)

# B.1 功规点 / B.2 接口路径(简化提取: HTTP 方法 + 路径)
API_PATH_RE = re.compile(
    r"\b(GET|POST|PUT|DELETE|PATCH)\s+(/[a-zA-Z_][a-zA-Z0-9_/{}\-]+)",
)

# 🆕 新增 标记识别(段落级)
NEW_MARKER_RE = re.compile(r"🆕\s*新增")

# 跳过常见无意义短表名
SKIP_TABLE_NAMES = {"a", "b", "c", "x", "y", "z", "main", "log", "test", "demo", "tmp"}


def parse_design_document(design_path: Path) -> Dict:
    """
    解析设计文档,提取标 🆕 新增 的实体名 / 接口路径。
    简化策略: 段落级扫描,如果段落含 🆕 标记,视为新增条目。
    """
    if not design_path.exists():
        return {"tables": [], "apis": [], "new_tables": [], "new_apis": []}
    try:
        text = design_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return {"tables": [], "apis": [], "new_tables": [], "new_apis": []}

    # 段落分块: 按 ## 或 ### 切
    sections = re.split(r"(?m)^##+\s+", text)

    all_tables: List[Tuple[str, str]] = []  # (table_name, section_title)
    all_apis: List[Tuple[str, str, str]] = []  # (method, path, section_title)
    new_tables: List[str] = []
    new_apis: List[Tuple[str, str]] = []

    for section in sections:
        if not section.strip():
            continue
        title_line = section.split("\n", 1)[0].strip()
        is_new = bool(NEW_MARKER_RE.search(section))

        # 提取表名
        for m in TABLE_DECL_RE.finditer(section):
            table = m.group(1).lower()
            if table in SKIP_TABLE_NAMES or len(table) < 3:
                continue
            all_tables.append((table, title_line))
            if is_new:
                new_tables.append(table)

        # 提取 API path
        for m in API_PATH_RE.finditer(section):
            method, path = m.group(1).upper(), m.group(2)
            all_apis.append((method, path, title_line))
            if is_new:
                new_apis.append((method, path))

    # 去重
    return {
        "tables": sorted(set([t for t, _ in all_tables])),
        "apis": sorted(set([(m, p) for m, p, _ in all_apis])),
        "new_tables": sorted(set(new_tables)),
        "new_apis": sorted(set(new_apis)),
    }


# ============================================================
# 代码仓扫描
# ============================================================

CODE_EXTS = {".java", ".kt", ".ts", ".tsx", ".js", ".py", ".go", ".cs"}
SKIP_DIRS = {"node_modules", "target", "build", "dist", ".git", ".idea",
             "__pycache__", "venv", ".venv", "out"}

# 实体类识别: class UserEntity / class User / @Entity public class XX
ENTITY_CLASS_RE = re.compile(
    r"(?:@Entity\b[^\n]*\n\s*)?(?:public\s+|export\s+)?class\s+([A-Z][A-Za-z0-9_]+)\b",
)

# 表名映射: snake_case → PascalCase 实体名
def snake_to_pascal(snake: str) -> str:
    parts = snake.split("_")
    # 去掉常见前缀
    while parts and parts[0] in {"biz", "sys", "tb", "t", "ods", "dim", "fact"}:
        parts = parts[1:]
    return "".join(p.capitalize() for p in parts if p)


# Controller 路径识别: @RequestMapping("/xx") / @GetMapping("/xx") / @PostMapping("/xx")
CONTROLLER_PATH_RE = re.compile(
    r"@(?:Request|Get|Post|Put|Delete|Patch)Mapping\s*\(\s*[\"']([^\"']+)[\"']",
)


def scan_existing_entities(code_root: Path) -> Dict[str, List[Dict]]:
    """
    扫描代码仓,返回所有已存在的实体类:
        {pascal_name: [{file, line, snippet}, ...]}
    """
    entities: Dict[str, List[Dict]] = {}
    for path in code_root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in CODE_EXTS:
            continue
        if any(skip in path.parts for skip in SKIP_DIRS):
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for m in ENTITY_CLASS_RE.finditer(content):
            name = m.group(1)
            line_no = content[:m.start()].count("\n") + 1
            entities.setdefault(name.lower(), []).append({
                "file": str(path.relative_to(code_root)),
                "line": line_no,
                "snippet": m.group(0)[:80],
                "name": name,
            })
    return entities


def scan_existing_api_paths(code_root: Path) -> Dict[str, List[Dict]]:
    """
    扫描代码仓,返回所有已存在的 Controller 路径:
        {path_signature: [{file, line, snippet}, ...]}
    path_signature 是路径标准化后的字符串(去尾斜线/小写/去 path param)
    """
    apis: Dict[str, List[Dict]] = {}
    for path in code_root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in CODE_EXTS:
            continue
        if any(skip in path.parts for skip in SKIP_DIRS):
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for m in CONTROLLER_PATH_RE.finditer(content):
            raw = m.group(1)
            sig = normalize_path(raw)
            line_no = content[:m.start()].count("\n") + 1
            apis.setdefault(sig, []).append({
                "file": str(path.relative_to(code_root)),
                "line": line_no,
                "raw_path": raw,
                "snippet": m.group(0)[:80],
            })
    return apis


def normalize_path(p: str) -> str:
    """标准化路径: 小写 + 去尾斜线 + path param 替换为 {}"""
    p = p.strip().lower().rstrip("/")
    p = re.sub(r"\{[^}]+\}", "{}", p)  # /user/{id} → /user/{}
    p = re.sub(r":[a-zA-Z_]+", "{}", p)  # /user/:id → /user/{}
    return p


# ============================================================
# 复用匹配
# ============================================================

def match_table_to_entity(table: str, entities: Dict[str, List[Dict]]) -> List[Dict]:
    """匹配表名到实体类(snake → PascalCase + 同名/相似名匹配)"""
    candidates = []
    pascal = snake_to_pascal(table)
    # 直接匹配
    for key in (pascal.lower(), pascal.lower() + "entity", pascal.lower() + "do",
                pascal.lower() + "po", pascal.lower() + "model"):
        if key in entities:
            candidates.extend(entities[key])
    # 部分匹配(实体名包含 pascal 或反之)
    for ent_key, items in entities.items():
        if ent_key in (pascal.lower(), pascal.lower() + "entity"):
            continue  # 已加
        if pascal.lower() in ent_key or ent_key in pascal.lower():
            if len(pascal) >= 4:  # 短词不做模糊匹配
                candidates.extend(items)
    # 去重(按 file + line)
    seen = set()
    unique = []
    for c in candidates:
        key = (c["file"], c["line"])
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique


def match_api_to_existing(method: str, path: str, apis: Dict[str, List[Dict]]) -> List[Dict]:
    """匹配 API 路径到已有 Controller(完全匹配 + 前缀匹配)"""
    candidates = []
    sig = normalize_path(path)
    # 完全匹配
    if sig in apis:
        candidates.extend(apis[sig])
    # 前缀匹配(新接口 path 是已有接口的子路径)
    for ex_sig, items in apis.items():
        if ex_sig == sig:
            continue
        if sig.startswith(ex_sig + "/") or ex_sig.startswith(sig + "/"):
            candidates.extend(items)
    return candidates


# ============================================================
# 主流程
# ============================================================

def analyze(design_path: Path, code_root: Path) -> Dict:
    if not design_path.exists():
        return {"error": "DESIGN_NOT_FOUND", "design": str(design_path), "passed": False}
    if not code_root.exists() or not code_root.is_dir():
        return {"error": "CODE_ROOT_NOT_FOUND", "code_root": str(code_root), "passed": False}

    design = parse_design_document(design_path)
    entities = scan_existing_entities(code_root)
    apis = scan_existing_api_paths(code_root)

    warnings: List[Dict] = []

    # 类型 A: 新增表 vs 已有实体
    for table in design["new_tables"]:
        matches = match_table_to_entity(table, entities)
        if matches:
            warnings.append({
                "type": "TABLE_ALREADY_EXISTS",
                "design_label": "🆕 新增",
                "design_item": f"数据表 {table}",
                "matched_count": len(matches),
                "matches": matches[:3],
                "suggestion": (
                    f"设计标 {table} 表为 🆕 新增,但代码中已有同义实体类: "
                    f"{', '.join(m['name'] for m in matches[:3])} "
                    f"({matches[0]['file']}:L{matches[0]['line']}...)。"
                    "请确认是否应改标 ✅ 复用已有 / ✅ 复用已有数据-新统计,或在 Module E 标注 D-NNN 待澄清。"
                ),
            })

    # 类型 B: 新增 API vs 已有 Controller
    for method, path in design["new_apis"]:
        matches = match_api_to_existing(method, path, apis)
        if matches:
            warnings.append({
                "type": "API_ALREADY_EXISTS",
                "design_label": "🆕 新增",
                "design_item": f"{method} {path}",
                "matched_count": len(matches),
                "matches": matches[:3],
                "suggestion": (
                    f"设计标 {method} {path} 为 🆕 新增,但代码中已有同/相似路径: "
                    f"{', '.join(m['raw_path'] for m in matches[:3])} "
                    f"({matches[0]['file']}:L{matches[0]['line']}...)。"
                    "请确认是否应改标 ✅ 复用已有,或解释为何新建同义接口。"
                ),
            })

    return {
        "design_path": str(design_path),
        "code_root": str(code_root),
        "design_summary": {
            "total_tables": len(design["tables"]),
            "total_apis": len(design["apis"]),
            "new_tables": len(design["new_tables"]),
            "new_apis": len(design["new_apis"]),
        },
        "code_summary": {
            "entities_indexed": len(entities),
            "api_paths_indexed": len(apis),
        },
        "warnings": warnings,
        "warning_count": len(warnings),
        "passed": True,  # 仅警示,不强阻塞
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="功能/数据/接口复用扫描(对应核心原则 20 + QR 检查项 27)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("design", type=Path, help="设计文档路径")
    ap.add_argument("code_root", type=Path, help="代码根目录")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    args = ap.parse_args()

    result = analyze(args.design, args.code_root)

    # ⚠️ 入参错的判定必须在 `if args.json` **之前** —— 否则 --json 模式下路径错会走
    #    `passed=False → return 1`，人读模式返回 2 而 --json 返回 1，同一情形两个码。
    #    路径校验发生在 analyze() 内部（不在 main 顶部），所以这里必须显式先判。
    if "error" in result:
        print(json.dumps(result, ensure_ascii=False, indent=2)) if args.json else None
        print(f"错误: {result['error']}: {result.get('design') or result.get('code_root')}",
              file=sys.stderr)
        return 2  # 入参错(设计文档/代码根不存在),非产物违规——原先返回 1 是假红

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("passed", False) else 1

    print(f"📐 设计文档: {result['design_path']}")
    print(f"📁 代码根目录: {result['code_root']}\n")

    ds = result["design_summary"]
    cs = result["code_summary"]
    print(f"设计文档汇总: 数据表 {ds['total_tables']} 张(其中 🆕 新增 {ds['new_tables']} 张),"
          f"API {ds['total_apis']} 个(其中 🆕 新增 {ds['new_apis']} 个)")
    print(f"代码仓索引: 实体类 {cs['entities_indexed']} 个,Controller 路径 {cs['api_paths_indexed']} 个\n")

    if result["warning_count"] == 0:
        print("✅ 无复用警示: 设计文档中所有 🆕 新增 条目在代码中均无同义实现。")
        return 0

    print(f"⚠️  发现 {result['warning_count']} 处复用警示(设计标 🆕 新增 但代码已有同义实现):\n")
    for w in result["warnings"]:
        print(f"  [{w['type']}] {w['design_item']}")
        print(f"    {w['suggestion']}")
        for m in w["matches"][:3]:
            extra = f"  → {m['name']}" if "name" in m else f"  → {m.get('raw_path', '')}"
            print(f"      {m['file']}:L{m['line']}{extra}")
        print()

    print("📌 处理建议:")
    print("  1. 对每个警示对照核心原则 20 决策矩阵,确认应改标 ✅ 复用已有 / ✅ 复用已有数据-新统计")
    print("  2. 若代码已有同义实现确实不可复用(如版本不兼容/语义差异大),在 Module E 标 D-NNN 说明")
    print("  3. 在 B.1 实现映射表「复用映射」列正确标注代码位置")
    print("  详见 dev-logic-architect QR 检查项 27「复用识别完整性核验」")
    return 0


if __name__ == "__main__":
    sys.exit(main())
