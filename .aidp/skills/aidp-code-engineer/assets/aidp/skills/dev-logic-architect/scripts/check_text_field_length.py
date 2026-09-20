#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_text_field_length.py — 文本字段长度冗余合规扫描

对照 dev-logic-architect SKILL 核心原则 13「文本字段长度冗余原则」。
扫描详细设计文档(.md)中的 SQL DDL,识别 VARCHAR/CHAR 文本字段并核验:
  1. 自由输入字段 DB 长度 ≥ 前端限制 × 3(从 COMMENT 解析"前端限制 N 字符"等)
  2. COMMENT 显式标注"DB 冗余 3×"
  3. 豁免字段需在 COMMENT 标注豁免理由,豁免类型:
     - 强格式(手机/身份证/邮箱/银行卡/邮编/IP/MAC/URL)
     - 系统生成(UUID/订单号/Token/Session ID 等)
     - 敏感字段(密码哈希/密钥/签名/Hash,长度由算法决定)
     - 设备/序列号(由系统/硬件分配)
     - 扩展属性 / 元数据 JSON 字符串(非自由输入)
     - 文件路径 / 对象存储 Key(系统生成)
     - 枚举 code(_code/_type/_status/_state 后缀)
     - 历史沿用(配合检查项 18)
     - TEXT/MEDIUMTEXT/LONGTEXT(非 VARCHAR)
  4. VARCHAR 长度不超出 utf8mb4 单字段上限(16383)
  5. COMMENT 已显式标豁免关键词(强格式/系统生成/算法决定/JSON 字符串/Base64/BCrypt 等)
     时尊重作者声明,即使字段名命中自由输入关键词也不再要求"前端限制 N + 3× 冗余"

用法:
    python check_text_field_length.py <详细设计文档或目录> [--json]

仅依赖 Python 3.6+ 标准库。

退出码:
  0 = 全部通过
  1 = 发现警告(豁免字段未标注理由等非阻断问题)
      **或** 发现违规(自由输入字段长度不足 3× 等阻断问题)
     ⚠️ 该档曾单用退出码 2,与全仓统一约定「2 = 入参错」撞码——调用方按约定把 2 当
        入参错「修正参数后重跑、不计维度失败」,就会把这条**强制不通过**静默放行(假绿)。
        已并入 1;分档改从 --json 读(见下)。严重度不占退出码,见 CLAUDE.md 全仓约定。
        分档:--json 的 `issues[].severity` 为 `Critical` 即阻断档、`Important` 为警告。
  2 = 输入错误(路径不存在 / 无 .md 文件)——非维度违规,修正参数后重跑
"""

import argparse
import json
import re
import sys
from pathlib import Path

FREE_INPUT_FIELD_KEYWORDS_EN = [
    "name", "nickname", "title", "description", "desc", "remark", "content",
    "address", "addr", "keyword", "tag", "summary", "note", "memo", "label",
    "intro", "bio", "subject", "message", "reason", "feedback", "review",
    "answer", "question", "company", "department", "position", "school",
    "major", "hobby",
]
FREE_INPUT_COMMENT_KEYWORDS_CN = [
    "名称", "昵称", "标题", "描述", "备注", "评论", "内容", "地址",
    "关键字", "关键词", "标签", "摘要", "简介", "说明", "备忘",
    "留言", "反馈", "评价", "回答", "提问", "公司", "部门", "职位",
    "学校", "专业", "爱好", "用户名", "姓名", "真名", "真实姓名",
]

EXCLUDE_FIELD_PATTERNS = [
    re.compile(r"^(id|.*_id)$", re.IGNORECASE),
    re.compile(r"^(create|update|delete)_(time|by|at)$", re.IGNORECASE),
    re.compile(r"^(creator|updater|deleter)$", re.IGNORECASE),
    re.compile(r"^(version|sort|order|status|state|level|gender|sex)$", re.IGNORECASE),
    re.compile(r"^is_\w+$", re.IGNORECASE),
    re.compile(r"^.*_(at|on|date)$", re.IGNORECASE),
    re.compile(r"^.*_count$", re.IGNORECASE),
    re.compile(r"^.*_num$", re.IGNORECASE),
]

# 豁免字段名关键词(命中即视为豁免,但 COMMENT 仍应标豁免理由)
STRICT_FORMAT_KEYWORDS = {
    "phone": "手机号(强格式)", "mobile": "手机号(强格式)",
    "tel": "电话(强格式)", "telephone": "电话(强格式)",
    "email": "邮箱(强格式)", "id_card": "身份证(强格式)",
    "idcard": "身份证(强格式)", "id_number": "证件号(强格式)",
    "bank_card": "银行卡号(强格式)", "bank_account": "银行账号(强格式)",
    "card_no": "卡号(强格式)", "zip_code": "邮编(强格式)",
    "postal_code": "邮编(强格式)", "ip": "IP 地址(强格式)",
    "ip_address": "IP 地址(强格式)", "mac": "MAC 地址(强格式)",
    "url": "URL(强格式)",
}
SYSTEM_GENERATED_KEYWORDS = {
    "uuid": "UUID(系统生成)", "guid": "GUID(系统生成)",
    "order_no": "订单号(系统生成)", "trade_no": "交易号(系统生成)",
    "out_trade_no": "外部交易号(系统生成)",
    "request_id": "请求 ID(系统生成)", "trace_id": "追踪 ID(系统生成)",
    "token": "Token(系统生成)", "session_id": "会话 ID(系统生成)",
    # 敏感字段(密钥/哈希等,长度由算法决定,无前端限制概念)
    "password": "密码哈希(算法决定长度)", "passwd": "密码哈希(算法决定长度)",
    "pwd": "密码哈希(算法决定长度)", "salt": "盐值(算法决定长度)",
    "secret": "密钥(算法决定长度)", "secret_key": "密钥(算法决定长度)",
    "api_key": "API 密钥(系统生成)", "access_key": "访问密钥(系统生成)",
    "access_token": "访问 Token(系统生成)", "refresh_token": "刷新 Token(系统生成)",
    "private_key": "私钥(算法决定长度)", "public_key": "公钥(算法决定长度)",
    "signature": "签名(算法决定长度)", "hash": "哈希值(算法决定长度)",
    "checksum": "校验和(算法决定长度)",
    # 设备/序列号类
    "device_no": "设备号(系统生成)", "device_id": "设备号(系统生成)",
    "serial_no": "序列号(系统生成)", "sn": "序列号(系统生成)",
    "mac_address": "MAC 地址(强格式)",
    # 扩展属性 / JSON 字符串(无前端限制概念)
    "ext_attr": "扩展属性 JSON(非自由输入)",
    "extra": "扩展信息 JSON(非自由输入)",
    "ext_data": "扩展数据 JSON(非自由输入)",
    "ext_info": "扩展信息 JSON(非自由输入)",
    "metadata": "元数据 JSON(非自由输入)",
    "config": "配置 JSON(非自由输入)",
    "settings": "设置 JSON(非自由输入)",
    "props": "属性 JSON(非自由输入)",
    # 二进制/编码内容
    "icon": "图标(URL 或 Base64)",
    "thumbnail": "缩略图(URL 或 Base64)",
    "qr_code": "二维码(URL 或 Base64)",
    "barcode": "条形码(URL 或 Base64)",
    # 文件路径/Key
    "file_path": "文件路径(系统生成)", "file_key": "文件 Key(系统生成)",
    "object_key": "对象存储 Key(系统生成)", "oss_key": "OSS Key(系统生成)",
    "s3_key": "S3 Key(系统生成)",
}
ENUM_CODE_SUFFIXES = ["_code", "_type", "_status", "_state"]

VARCHAR_PATTERN = re.compile(r"^(VAR)?CHAR\s*\(\s*(\d+)\s*\)$", re.IGNORECASE)
TEXT_TYPES = {"TEXT", "MEDIUMTEXT", "LONGTEXT", "TINYTEXT"}

FRONTEND_LIMIT_PATTERNS = [
    re.compile(r"前端限制\s*(\d+)"),
    re.compile(r"前端限\s*(\d+)"),
    re.compile(r"前端\s*(\d+)\s*字"),
    re.compile(r"前端\s*[::]\s*(\d+)"),
    re.compile(r"输入限制\s*(\d+)"),
    re.compile(r"输入限\s*(\d+)"),
    re.compile(r"maxlength\s*[:=]?\s*(\d+)", re.IGNORECASE),
    re.compile(r"max[\s_-]?length\s*[:=]?\s*(\d+)", re.IGNORECASE),
    re.compile(r"限\s*(\d+)\s*字"),
]

REDUNDANCY_PATTERNS = [
    re.compile(r"DB\s*冗余\s*[3三]\s*[×x*倍]", re.IGNORECASE),
    re.compile(r"冗余\s*[3三]\s*[×x*倍]", re.IGNORECASE),
    re.compile(r"DB\s*[3三]\s*[×x*倍]", re.IGNORECASE),
    re.compile(r"3\s*[×x*]\s*前端", re.IGNORECASE),
]

EXEMPT_KEYWORDS = [
    "强格式", "精确长度", "系统生成", "固定长度", "枚举", "字典 code",
    "字典code", "历史沿用", "沿用历史", "已有表", "ISO", "国际标准",
    "算法决定", "非自由输入", "JSON 字符串", "JSON字符串", "扩展属性",
    "Base64", "BCrypt", "BCRYPT", "SHA", "MD5", "RSA", "AES",
    "fixed length", "strict format", "legacy",
]

SQL_BLOCK_PATTERN = re.compile(r"```sql\s*\n(.*?)\n```", re.DOTALL | re.IGNORECASE)
CREATE_TABLE_HEAD_PATTERN = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"\[]?(\w+)[`\"\]]?\s*\(",
    re.IGNORECASE,
)


def iter_create_tables(sql_text):
    """逐表产出 (表名, 表体, CREATE 起始偏移)。

    表体用括号配对(并跳过引号内字符)定位真正的结束括号,避免列内
    `VARCHAR(20) COMMENT '...'` 这类「) 紧跟 COMMENT」把表体提前截断——
    旧的非贪婪正则会在第一个「) 紧跟 COMMENT」处收尾,漏掉其后所有字段与索引,
    使维度检查静默失效(可空列 + 行内 COMMENT 是最常见的触发写法)。
    """
    for m in CREATE_TABLE_HEAD_PATTERN.finditer(sql_text):
        name = m.group(1)
        open_idx = m.end() - 1  # 表体起始 '(' 下标
        depth = 0
        quote = None
        for j in range(open_idx, len(sql_text)):
            c = sql_text[j]
            if quote is not None:
                if c == quote:
                    quote = None
                continue
            if c in ("'", '"', "`"):
                quote = c
            elif c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    yield name, sql_text[open_idx + 1:j], m.start()
                    break
FIELD_LINE_PATTERN = re.compile(
    r"^\s*[`\"]?(\w+)[`\"]?\s+"
    r"((?:VAR)?CHAR\s*\(\s*\d+\s*\)|TEXT|MEDIUMTEXT|LONGTEXT|TINYTEXT)"
    r"([^,]*?)"
    r"(?:COMMENT\s+['\"]([^'\"]*)['\"])?"
    r"\s*,?\s*$",
    re.IGNORECASE,
)

MYSQL_UTF8MB4_VARCHAR_MAX = 16383


def field_match_keyword(field_name, kw_dict):
    fname_low = field_name.lower()
    if fname_low in kw_dict:
        return kw_dict[fname_low]
    for k, v in kw_dict.items():
        if fname_low == k or fname_low.endswith("_" + k):
            return v
    return None


def is_excluded(field_name):
    return any(p.match(field_name) for p in EXCLUDE_FIELD_PATTERNS)


def is_enum_code(field_name):
    return any(field_name.lower().endswith(s) for s in ENUM_CODE_SUFFIXES)


def looks_like_free_input(field_name, comment):
    if is_excluded(field_name):
        return False
    # COMMENT 已显式标注豁免关键词时,尊重作者声明,不视为自由输入
    if comment and has_exempt_declaration(comment):
        return False
    fname_low = field_name.lower()
    for kw in FREE_INPUT_FIELD_KEYWORDS_EN:
        if kw in fname_low:
            return True
    if comment:
        for kw in FREE_INPUT_COMMENT_KEYWORDS_CN:
            if kw in comment:
                return True
    return False


def parse_frontend_limit(comment):
    if not comment:
        return None
    for p in FRONTEND_LIMIT_PATTERNS:
        m = p.search(comment)
        if m:
            return int(m.group(1))
    return None


def has_redundancy_declaration(comment):
    if not comment:
        return False
    return any(p.search(comment) for p in REDUNDANCY_PATTERNS)


def has_exempt_declaration(comment):
    if not comment:
        return False
    return any(kw in comment for kw in EXEMPT_KEYWORDS)


def classify_type(raw_type):
    t = raw_type.strip().upper()
    m = VARCHAR_PATTERN.match(t)
    if m:
        return "VARCHAR", int(m.group(2))
    base = re.split(r"[\s(]", t, maxsplit=1)[0]
    if base in TEXT_TYPES:
        return "TEXT", None
    return "OTHER", None


def check_field(field_name, raw_type, comment, table_name, file_path):
    """对单个文本字段执行合规核验,返回 (entry, issues)"""
    type_kind, db_len = classify_type(raw_type)
    entry = {
        "file": str(file_path),
        "table": table_name,
        "field": field_name,
        "type": raw_type.strip(),
        "type_kind": type_kind,
        "db_length": db_len,
        "comment": comment or "",
    }
    issues = []

    # TEXT 类型不适用 3× 规则,但前端应有限制
    if type_kind == "TEXT":
        entry["category"] = "TEXT"
        entry["status"] = "OK"
        return entry, issues

    if type_kind != "VARCHAR":
        entry["category"] = "OTHER"
        entry["status"] = "SKIP"
        return entry, issues

    # 超长 VARCHAR 警告
    if db_len > MYSQL_UTF8MB4_VARCHAR_MAX:
        issues.append({
            **entry,
            "severity": "Critical",
            "rule": "VARCHAR 超出 utf8mb4 上限",
            "hint": f"VARCHAR({db_len}) 超出 utf8mb4 单字段上限 {MYSQL_UTF8MB4_VARCHAR_MAX} 字符,改用 TEXT",
        })

    # 豁免字段优先识别
    strict = field_match_keyword(field_name, STRICT_FORMAT_KEYWORDS)
    sysgen = field_match_keyword(field_name, SYSTEM_GENERATED_KEYWORDS)
    enum_code = is_enum_code(field_name)

    if strict or sysgen or enum_code:
        if strict:
            entry["category"] = "EXEMPT_STRICT"
            exempt_label = strict
        elif sysgen:
            entry["category"] = "EXEMPT_SYSGEN"
            exempt_label = sysgen
        else:
            entry["category"] = "EXEMPT_ENUM_CODE"
            exempt_label = "枚举 code(豁免)"
        if not has_exempt_declaration(comment):
            issues.append({
                **entry,
                "severity": "Important",
                "rule": "豁免字段需在 COMMENT 标注豁免理由",
                "hint": f"COMMENT 应标注 '{exempt_label}' 等豁免理由(强格式/系统生成/枚举 code)",
            })
        entry["status"] = "EXEMPT"
        return entry, issues

    # 自由输入字段核验 3× 规则
    if not looks_like_free_input(field_name, comment):
        entry["category"] = "OTHER_VARCHAR"
        entry["status"] = "SKIP"
        return entry, issues

    entry["category"] = "FREE_INPUT"
    frontend_limit = parse_frontend_limit(comment)
    entry["frontend_limit"] = frontend_limit
    has_redundancy = has_redundancy_declaration(comment)
    entry["has_redundancy_declaration"] = has_redundancy

    if frontend_limit is None:
        # 前端限制未在 COMMENT 中标注 → 警告(可能 PRD 也未明)
        issues.append({
            **entry,
            "severity": "Important",
            "rule": "自由输入字段未在 COMMENT 标注前端限制",
            "hint": "COMMENT 应写明 '前端限制 N 字符,DB 冗余 3×';PRD 未定时 Module E 待澄清",
        })
        entry["status"] = "WARN_NO_FRONTEND_LIMIT"
        return entry, issues

    expected_min = frontend_limit * 3
    entry["expected_min_db_length"] = expected_min
    entry["redundancy_ratio"] = round(db_len / frontend_limit, 2) if frontend_limit > 0 else None

    if db_len < expected_min:
        issues.append({
            **entry,
            "severity": "Critical",
            "rule": "DB 长度不足前端限制 3×",
            "hint": f"前端限制 {frontend_limit} 字符,DB 应 ≥ {expected_min},当前 {db_len}",
        })
        entry["status"] = "FAIL_LENGTH"
    elif not has_redundancy:
        issues.append({
            **entry,
            "severity": "Important",
            "rule": "COMMENT 缺少 'DB 冗余 3×' 标注",
            "hint": f"COMMENT 应显式标注 '前端限制 {frontend_limit} 字符,DB 冗余 3×'",
        })
        entry["status"] = "WARN_NO_DECLARATION"
    else:
        entry["status"] = "OK"

    return entry, issues


def scan_file(path):
    text = path.read_text(encoding="utf-8", errors="replace")
    fields = []
    issues = []
    for sql_match in SQL_BLOCK_PATTERN.finditer(text):
        sql = sql_match.group(1)
        for table_name, body, _ in iter_create_tables(sql):
            for raw_line in body.splitlines():
                line = raw_line.strip().rstrip(",")
                if not line or line.startswith("--"):
                    continue
                upper = line.upper()
                if upper.startswith(("PRIMARY KEY", "KEY ", "INDEX ", "UNIQUE",
                                     "CONSTRAINT", "FOREIGN", ")")):
                    continue
                m = FIELD_LINE_PATTERN.match(line)
                if not m:
                    continue
                field_name, raw_type, _modifiers, comment = m.groups()
                comment = comment or ""
                entry, field_issues = check_field(
                    field_name, raw_type, comment, table_name, path
                )
                fields.append(entry)
                issues.extend(field_issues)
    return fields, issues


def collect_md_files(root):
    if root.is_file() and root.suffix.lower() == ".md":
        return [root]
    if root.is_dir():
        return sorted(root.rglob("*.md"))
    return []


def render_text_report(all_fields, all_issues, files_scanned):
    lines = []
    lines.append("=" * 72)
    lines.append("文本字段长度冗余合规扫描报告")
    lines.append("=" * 72)
    lines.append(f"扫描文件数: {files_scanned}")
    lines.append(f"识别文本字段总数: {len(all_fields)}")

    by_status = {}
    for f in all_fields:
        by_status[f.get("status", "?")] = by_status.get(f.get("status", "?"), 0) + 1
    lines.append(f"状态分布: {dict(by_status)}")

    crit = [i for i in all_issues if i.get("severity") == "Critical"]
    imp = [i for i in all_issues if i.get("severity") == "Important"]
    lines.append(f"Critical 违规: {len(crit)} 项")
    lines.append(f"Important 警告: {len(imp)} 项")
    lines.append("")

    if crit:
        lines.append("🔴 Critical 违规清单:")
        for i in crit:
            lines.append(f"  - {i['file']} :: {i['table']}.{i['field']}")
            lines.append(f"    类型: {i['type']} | 规则: {i['rule']}")
            lines.append(f"    建议: {i['hint']}")
            if i.get("comment"):
                lines.append(f"    COMMENT: {i['comment']}")
            lines.append("")

    if imp:
        lines.append("🟡 Important 警告清单:")
        for i in imp:
            lines.append(f"  - {i['file']} :: {i['table']}.{i['field']}")
            lines.append(f"    类型: {i['type']} | 规则: {i['rule']}")
            lines.append(f"    建议: {i['hint']}")
            lines.append("")

    if not crit and not imp:
        lines.append("✅ 全部通过")
    lines.append("=" * 72)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="扫描详细设计文档中的 SQL DDL,核验文本字段长度 ≥ 前端限制 3×"
    )
    parser.add_argument("path", help="详细设计文档路径或目录")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    args = parser.parse_args()

    root = Path(args.path)
    if not root.exists():
        print(f"错误: 路径不存在 {root}", file=sys.stderr)
        sys.exit(2)

    md_files = collect_md_files(root)
    if not md_files:
        print(f"错误: 未找到 .md 文件 {root}", file=sys.stderr)
        sys.exit(2)

    all_fields = []
    all_issues = []
    for f in md_files:
        fields, issues = scan_file(f)
        all_fields.extend(fields)
        all_issues.extend(issues)

    if args.json:
        out = {
            "files_scanned": len(md_files),
            "total_fields": len(all_fields),
            "fields": all_fields,
            "issues": all_issues,
            "critical_count": sum(1 for i in all_issues if i.get("severity") == "Critical"),
            "important_count": sum(1 for i in all_issues if i.get("severity") == "Important"),
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(render_text_report(all_fields, all_issues, len(md_files)))

    if any(i.get("severity") == "Critical" for i in all_issues):
        sys.exit(1)  # 曾为 2,与入参错撞码(见 docstring),已并入 1
    if any(i.get("severity") == "Important" for i in all_issues):
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
