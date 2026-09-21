#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_unit_field.py — 数据单位标注合规扫描

对照 dev-logic-architect SKILL 核心原则 21「数据单位标注与转换全链路一致性」
与质量检查清单维度 28,扫描详细设计文档(.md)中的 SQL DDL 与接口字段说明,
识别疑似数值字段并核验:
  1. 数值类型字段 COMMENT 必须含"单位:..."声明
  2. 存储单位必须为基础单位(个/毫秒/字节/万分点/毫米/克等)
  3. 百分比/比率字段必须明确"万分点(BP)" / "百分比(%)" / "小数(0-1)" 三选一
  4. 时间戳字段必须明确"毫秒时间戳" / "秒时间戳" / "ISO 8601 字符串" 三选一
  5. 时长/耗时字段单位必须为秒(亚秒精度才用毫秒),严禁分钟/小时/天等展示单位(时长单位铁律)
  6. 字段名后缀与 COMMENT 单位一致(_ms → 毫秒,_bytes → 字节,_g → 克)
  7. 严禁后端 DTO 字段类型为 String 但 COMMENT 含"K/M/G/分钟前/MB"等展示词

用法:
    python check_unit_field.py <详细设计文档或目录> [--json]

仅依赖 Python 3.6+ 标准库。
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set

# ============================================================
# 疑似数值字段识别(字段名后缀关键词)
# ============================================================

# 7 类数值字段后缀关键词
COUNT_SUFFIXES = ["_count", "_total", "_num", "_number", "_quantity", "_amount"]
TIME_DURATION_SUFFIXES = ["_ms", "_duration_ms", "_elapsed_ms", "_duration", "_elapsed"]
TIMESTAMP_SUFFIXES = ["_at", "_time", "_timestamp", "_ts", "_date"]
SIZE_SUFFIXES = ["_bytes", "_size_bytes", "_size", "_capacity", "_length_bytes"]
RATE_SUFFIXES = ["_bp", "_rate_bp", "_rate", "_ratio", "_percent", "_pct", "_percentage"]
LENGTH_SUFFIXES = ["_mm", "_length_mm", "_length", "_distance_mm", "_distance", "_width_mm", "_height_mm"]
WEIGHT_SUFFIXES = ["_g", "_weight_g", "_weight", "_mass_g", "_mass"]

ALL_NUMERIC_SUFFIXES = (
    COUNT_SUFFIXES + TIME_DURATION_SUFFIXES + TIMESTAMP_SUFFIXES + SIZE_SUFFIXES +
    RATE_SUFFIXES + LENGTH_SUFFIXES + WEIGHT_SUFFIXES
)

# COMMENT 中文关键词
COUNT_KEYWORDS_CN = ["数量", "总数", "计数", "次数", "条数", "笔数", "个数", "总计", "合计"]
TIME_DURATION_KEYWORDS_CN = ["时长", "耗时", "持续时间", "通话时长", "间隔", "有效期", "超时", "时限", "时效", "播放时长", "倒计时"]
TIMESTAMP_KEYWORDS_CN = ["时间", "日期", "时刻", "创建时间", "更新时间", "删除时间"]

# 时长字段后缀(独立于 TIME_DURATION_SUFFIXES,用于"时长单位铁律"识别)
DURATION_SUFFIXES = ["_duration", "_duration_ms", "_duration_s", "_elapsed", "_elapsed_ms", "_seconds", "_ms", "_timeout", "_ttl", "_interval"]
# 时长展示单位(粗单位):后端/COMMENT 出现即违规(应为秒)
DURATION_COARSE_UNITS = ["分钟", "小时", "天", "日", "周", "月", "年", "分", "时"]
# 单位值提取(取"单位:"之后到分隔符前的第一段)
UNIT_VALUE_PATTERN = re.compile(r"单位\s*[:：]\s*([^,，;；。\s)）]+)")
SIZE_KEYWORDS_CN = ["大小", "容量", "尺寸", "文件大小"]
RATE_KEYWORDS_CN = ["比例", "百分比", "比率", "达成率", "完成率", "占比", "概率", "转化率"]
LENGTH_KEYWORDS_CN = ["长度", "距离", "高度", "宽度", "厚度"]
WEIGHT_KEYWORDS_CN = ["重量", "质量", "吨位"]

# 整数类型(合规)
INTEGER_TYPES = {"BIGINT", "INT", "INTEGER", "SMALLINT", "TINYINT", "MEDIUMINT", "INT8", "INT4", "INT2", "LONG", "SHORT", "BYTE"}
# 浮点类型(不推荐,但允许带说明)
FLOAT_TYPES = {"FLOAT", "DOUBLE", "REAL", "DOUBLE PRECISION"}
# Decimal 类型(视情况)
DECIMAL_PATTERN = re.compile(r"^(DECIMAL|NUMERIC|NUMBER)\s*\(", re.IGNORECASE)

# 单位声明 pattern
UNIT_PATTERN = re.compile(r"单位\s*[:：]")

# SQL 代码块 (flexible: allows optional trailing newline)
SQL_BLOCK_PATTERN = re.compile(r'```sql\s*\n(.*?)\n?```', re.DOTALL | re.IGNORECASE)

# DDL 字段定义(简化版)
DDL_FIELD_PATTERN = re.compile(
    r"^\s*`?(\w+)`?\s+(BIGINT|INT|INTEGER|SMALLINT|TINYINT|MEDIUMINT|LONG|SHORT|BYTE|FLOAT|DOUBLE|REAL|DECIMAL\s*\([^)]+\)|NUMERIC\s*\([^)]+\)|NUMBER\s*\([^)]*\)"
    r"|VARCHAR\s*\([^)]*\)|VARCHAR|CHAR\s*\([^)]*\)|CHAR|LONGTEXT|MEDIUMTEXT|TINYTEXT|TEXT|STRING)"
    r"[^,;]*COMMENT\s+['\"]([^'\"]+)['\"]",
    re.IGNORECASE | re.MULTILINE
)

# ============================================================
# 单位合规规则
# ============================================================


# 百分比歧义检测:COMMENT 含"百分比"但未明确三选一
RATE_AMBIGUOUS_KEYWORDS = ["百分比", "比例", "%", "percent"]
RATE_EXPLICIT_UNITS = ["万分点", "BP", "百分比%(", "小数(0-1", "小数(0-1.0"]

# 时间歧义检测
TIME_AMBIGUOUS_KEYWORDS = ["时间", "时刻", "日期", "timestamp"]
TIME_EXPLICIT_UNITS = ["毫秒时间戳", "秒时间戳", "ISO 8601"]

# 后端禁返已转换字符串关键词
DISPLAY_UNIT_KEYWORDS = ["K", "M", "G", "万", "千", "百", "MB", "GB", "TB", "KB", "分钟前", "小时前", "天前", "秒前"]

# 字段名后缀与单位映射
SUFFIX_UNIT_MAP = {
    "_ms": ["毫秒", "ms"],
    "_seconds": ["秒", "s"],
    "_duration_s": ["秒", "s"],
    "_bytes": ["字节", "B"],
    "_g": ["克", "g"],
    "_bp": ["万分点", "BP"],
    "_mm": ["毫米", "mm"],
    "_kg": ["千克", "kg"],  # 不推荐,应用_g
    "_mb": ["兆字节", "MB"],  # 不推荐,应用_bytes
}

# ============================================================
# 解析与核验
# ============================================================

def scan_ddl_fields(design_content: str) -> List[Dict]:
    """
    扫描设计文档中的 SQL DDL,提取数值字段 + COMMENT。
    返回: [{field, type, comment, line_no}, ...]
    """
    findings = []
    sql_blocks = SQL_BLOCK_PATTERN.findall(design_content)
    for block in sql_blocks:
        for m in DDL_FIELD_PATTERN.finditer(block):
            field = m.group(1).lower()
            ftype = m.group(2).upper()
            comment = m.group(3)
            # 行号近似
            line_no = design_content[:design_content.find(block)].count("\n") + block[:m.start()].count("\n") + 1
            findings.append({
                "field": field,
                "type": ftype,
                "comment": comment,
                "line_no": line_no,
                "source": "DDL",
            })
    return findings


def is_numeric_field_candidate(field: str, comment: str) -> bool:
    """
    判断字段是否疑似数值字段(基于后缀 + COMMENT 关键词)
    """
    field_lower = field.lower()
    comment_lower = comment.lower()
    # 后缀匹配
    if any(field_lower.endswith(suffix) for suffix in ALL_NUMERIC_SUFFIXES):
        return True
    # COMMENT 中文关键词
    all_cn_keywords = (
        COUNT_KEYWORDS_CN + TIME_DURATION_KEYWORDS_CN + TIMESTAMP_KEYWORDS_CN +
        SIZE_KEYWORDS_CN + RATE_KEYWORDS_CN + LENGTH_KEYWORDS_CN + WEIGHT_KEYWORDS_CN
    )
    if any(kw in comment for kw in all_cn_keywords):
        return True
    return False


def check_unit_declaration(comment: str) -> bool:
    """检查 COMMENT 是否含"单位:..."声明"""
    return bool(UNIT_PATTERN.search(comment))


def check_rate_ambiguity(comment: str) -> Optional[str]:
    """
    检查百分比/比率字段是否歧义。
    返回: None = 无歧义,非 None = 歧义描述
    """
    comment_lower = comment.lower()
    has_rate_keyword = any(kw in comment_lower for kw in RATE_AMBIGUOUS_KEYWORDS)
    has_explicit = any(unit in comment for unit in RATE_EXPLICIT_UNITS)
    if has_rate_keyword and not has_explicit:
        return "COMMENT 含百分比/比例关键词但未明确'万分点(BP)' / '百分比%(0-100)' / '小数(0-1)' 三选一"
    return None


def check_time_ambiguity(comment: str) -> Optional[str]:
    """
    检查时间字段是否歧义。
    返回: None = 无歧义,非 None = 歧义描述
    """
    comment_lower = comment.lower()
    has_time_keyword = any(kw in comment_lower for kw in TIME_AMBIGUOUS_KEYWORDS)
    has_explicit = any(unit in comment for unit in TIME_EXPLICIT_UNITS)
    if has_time_keyword and not has_explicit:
        return "COMMENT 含时间关键词但未明确'毫秒时间戳' / '秒时间戳' / 'ISO 8601 字符串' 三选一"
    return None


def is_duration_field(field: str, comment: str) -> bool:
    """
    判断字段是否疑似"时长/耗时"字段(区别于时间戳),用于时长单位铁律核验。
    时长字段展示为分钟/小时/天,时间戳字段展示为日期,二者规则不同。
    """
    field_lower = field.lower()
    if any(field_lower.endswith(suffix) for suffix in DURATION_SUFFIXES):
        return True
    if any(kw in comment for kw in TIME_DURATION_KEYWORDS_CN):
        return True
    return False


def check_duration_coarse_unit(field: str, comment: str) -> Optional[str]:
    """
    时长单位铁律:时长/耗时字段单位必须为秒(亚秒精度才用毫秒),
    严禁分钟/小时/天等展示单位——后端一律返回秒,前端自行换算分/时。
    返回: None = 合规,非 None = 违规描述
    """
    m = UNIT_VALUE_PATTERN.search(comment)
    if not m:
        return None  # 缺"单位:"声明由规则 1 处理
    unit = m.group(1)
    if "秒" in unit:  # 秒 / 毫秒(亚秒精度例外)均合规
        return None
    if any(cu in unit for cu in DURATION_COARSE_UNITS):
        return (f"时长字段单位为展示单位'{unit}',应为'秒'(亚秒精度才用毫秒);"
                f"后端接口一律返回秒,前端自行换算分/时")
    return None


def check_suffix_unit_consistency(field: str, comment: str) -> Optional[str]:
    """
    检查字段名后缀与 COMMENT 单位是否一致。
    返回: None = 一致,非 None = 不一致描述
    """
    field_lower = field.lower()
    for suffix, expected_units in SUFFIX_UNIT_MAP.items():
        if field_lower.endswith(suffix):
            if not any(unit in comment for unit in expected_units):
                return f"字段后缀 {suffix} 应对应单位 {'/'.join(expected_units)},但 COMMENT 未含此单位"
    return None


def check_backend_returns_display_string(ftype: str, comment: str) -> Optional[str]:
    """
    检查后端是否返回已转换展示字符串(字段类型 String 但 COMMENT 含 K/MB/分钟前等)
    返回: None = 合规,非 None = 违规描述
    """
    if "VARCHAR" in ftype.upper() or "CHAR" in ftype.upper() or "STRING" in ftype.upper() or "TEXT" in ftype.upper():
        if any(kw in comment for kw in DISPLAY_UNIT_KEYWORDS):
            return f"后端字段类型为 String 但 COMMENT 含展示单位词 {[kw for kw in DISPLAY_UNIT_KEYWORDS if kw in comment]},应改为数值类型 + 前端转换"
    return None


def analyze_design_document(design_path: Path) -> Dict:
    """
    分析单个设计文档,返回检查结果。
    """
    if not design_path.exists():
        return {"error": "FILE_NOT_FOUND", "path": str(design_path), "passed": False}
    try:
        content = design_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"error": "READ_ERROR", "path": str(design_path), "detail": str(e), "passed": False}

    ddl_fields = scan_ddl_fields(content)
    violations = []

    for f in ddl_fields:
        field, ftype, comment = f["field"], f["type"], f["comment"]
        if not is_numeric_field_candidate(field, comment):
            continue  # 非数值概念字段,跳过

        # 规则 5: 数值概念字段(名字带 _size/_amount 等数值后缀)却声明为 String
        #   且 COMMENT 含展示单位词(K/MB/分钟前…) → 后端返回了已转换的展示字符串,
        #   应改为数值类型 + 前端转换。仅对数值概念候选字段生效,普通文本 VARCHAR 不命中。
        is_string_type = any(s in ftype.upper() for s in ("VARCHAR", "CHAR", "TEXT", "STRING"))
        if is_string_type:
            display_str = check_backend_returns_display_string(ftype, comment)
            if display_str:
                violations.append({
                    "rule": "BACKEND_RETURNS_DISPLAY_STRING",
                    "field": field,
                    "type": ftype,
                    "line": f.get("line_no"),
                    "comment": comment[:80],
                    "detail": display_str,
                })
            continue  # String 字段不适用数值存储规则 1-4

        # 规则 1: 单位声明
        if not check_unit_declaration(comment):
            violations.append({
                "rule": "UNIT_DECLARATION_MISSING",
                "field": field,
                "type": ftype,
                "line": f.get("line_no"),
                "comment": comment[:80],
                "detail": f"数值字段 {field} COMMENT 缺'单位:...'声明",
            })

        # 规则 2: 百分比歧义
        rate_amb = check_rate_ambiguity(comment)
        if rate_amb:
            violations.append({
                "rule": "RATE_AMBIGUITY",
                "field": field,
                "type": ftype,
                "line": f.get("line_no"),
                "comment": comment[:80],
                "detail": rate_amb,
            })

        # 规则 3: 时长/时间字段
        #   时长字段(时长/耗时/有效期/超时…)走"时长单位铁律"(单位必须为秒);
        #   时间戳字段走"毫秒/秒时间戳/ISO"三选一歧义核验。二者互斥,避免
        #   "持续时间,单位:秒"因含"时间"子串被误判为时间戳歧义。
        if is_duration_field(field, comment):
            dur_coarse = check_duration_coarse_unit(field, comment)
            if dur_coarse:
                violations.append({
                    "rule": "DURATION_COARSE_UNIT",
                    "field": field,
                    "type": ftype,
                    "line": f.get("line_no"),
                    "comment": comment[:80],
                    "detail": dur_coarse,
                })
        else:
            time_amb = check_time_ambiguity(comment)
            if time_amb:
                violations.append({
                    "rule": "TIME_AMBIGUITY",
                    "field": field,
                    "type": ftype,
                    "line": f.get("line_no"),
                    "comment": comment[:80],
                    "detail": time_amb,
                })

        # 规则 4: 后缀与单位一致性
        suffix_inc = check_suffix_unit_consistency(field, comment)
        if suffix_inc:
            violations.append({
                "rule": "SUFFIX_UNIT_INCONSISTENT",
                "field": field,
                "type": ftype,
                "line": f.get("line_no"),
                "comment": comment[:80],
                "detail": suffix_inc,
            })

    return {
        "file": str(design_path),
        "total_numeric_fields": len([f for f in ddl_fields if is_numeric_field_candidate(f["field"], f["comment"])]),
        "violations": violations,
        "violation_count": len(violations),
        "passed": len(violations) == 0,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="数据单位标注合规扫描(对应核心原则 21 + QR 检查项 28)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("path", type=Path, help="详细设计文档或目录")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    args = ap.parse_args()

    if not args.path.exists():
        print(f"❌ 路径不存在: {args.path}", file=sys.stderr)
        return 2

    results = []
    if args.path.is_file():
        results.append(analyze_design_document(args.path))
    else:
        for md_file in args.path.rglob("*.md"):
            results.append(analyze_design_document(md_file))

    aggregated = {
        "scan_root": str(args.path),
        "files_scanned": len(results),
        "total_violations": sum(r.get("violation_count", 0) for r in results),
        "passed": all(r.get("passed", False) for r in results),
        "results": results,
    }

    if args.json:
        print(json.dumps(aggregated, ensure_ascii=False, indent=2))
        return 0 if aggregated["passed"] else 1

    # 文本输出
    print(f"扫描路径: {args.path}\n")
    print(f"📊 数据单位标注合规扫描结果\n")
    print(f"扫描文件: {aggregated['files_scanned']} 个")
    print(f"违规总数: {aggregated['total_violations']} 处\n")

    if aggregated["passed"]:
        print("✅ 所有数值字段单位标注合规")
        return 0

    print(f"❌ 发现 {aggregated['total_violations']} 处违规:\n")
    for r in results:
        if r.get("violation_count", 0) == 0:
            continue
        print(f"📄 {r['file']}")
        print(f"  数值字段: {r['total_numeric_fields']} 个,违规: {r['violation_count']} 处")
        for v in r["violations"][:5]:  # 每文件最多显示 5 条
            print(f"    [{v['rule']}] {v['field']} ({v['type']}) L{v.get('line', '?')}")
            print(f"      {v['detail']}")
            print(f"      COMMENT: {v['comment']}")
        if r["violation_count"] > 5:
            print(f"    ... 还有 {r['violation_count'] - 5} 处违规(使用 --json 查看全部)")
        print()

    print("📌 修复建议:")
    print("  1. 所有数值字段 COMMENT 添加'单位:...'声明(如'单位:个'/'单位:毫秒'/'单位:字节')")
    print("  2. 百分比字段明确'单位:万分点(BP,0-10000)'或'单位:百分比%(0-100)'")
    print("  3. 时间戳字段明确'单位:毫秒时间戳'或'单位:秒时间戳'或'单位:ISO 8601 字符串'")
    print("  4. 时长/耗时字段单位用'秒'(亚秒精度才用毫秒),禁分钟/小时/天;后端返秒,前端自转分/时")
    print("  5. 字段名后缀与 COMMENT 单位保持一致(_ms → 毫秒,_bytes → 字节,_g → 克)")
    print("  6. 后端字段类型为 String 但含 K/MB/分钟前 等展示词 → 改为数值类型 + 前端转换")
    print("  详见 dev-logic-architect SKILL 核心原则 21「数据单位标注与转换全链路一致性」")

    return 1


if __name__ == "__main__":
    sys.exit(main())
