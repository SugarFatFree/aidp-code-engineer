#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_audit_field_fill.py — 审计字段操作人溯源与自动填充合规扫描

对照 dev-logic-architect SKILL 核心原则 22「审计字段操作人溯源与自动填充铁律」
与质量检查清单维度 30,扫描详细设计文档(.md)采集以下信号。

弱机检 · 采集为主:是否违规由 Agent 结合上下文判定,退出码恒 0。

采集四类信号:
  1. 审计字段覆盖:逐 CREATE TABLE 识别审计四件套(create_by/create_time/
     update_by/update_time)与逻辑删除标记(is_deleted/deleted/del_flag)的覆盖,
     区分 full/partial/none。哪些表算"业务实体表"由 Agent 判定,脚本仅给覆盖清单
     (并对"疑似业务表却零审计字段"给出软提示)。
  2. 填充机制声明:全文是否出现自动填充机制关键词
     (MetaObjectHandler/insertFill/updateFill/@CreatedBy/@LastModifiedBy/
      AuditorAware/自动填充/填充机制/操作人来源)。
  3. 逻辑删除同步:"逻辑删除"上下文附近是否提及同步更新 update_by/update_time。
  4. 写死 system 反模式:审计人字段(create_by/update_by/创建人/修改人 等)被赋值为
     字符串字面量("system"/"admin" 等)的命中点(DDL DEFAULT / 代码 setXxx / 赋值)。

用法:
    python check_audit_field_fill.py <详细设计文档或目录> [--json]

仅依赖 Python 3.6+ 标准库。
"""

import argparse
import json
import re
import sys
from pathlib import Path

# --------------------------------------------------------------------------- 字段识别
CREATOR_RE = re.compile(
    r"(?i)\b(create[_]?by|created[_]?by|creator|create[_]?user(?:[_]?id)?|"
    r"create[_]?uid|created[_]?uid|founder)\b")
CREATE_TIME_RE = re.compile(
    r"(?i)\b(create[_]?time|created[_]?time|gmt[_]?create|create[_]?at|"
    r"created[_]?at|create[_]?date)\b")
UPDATER_RE = re.compile(
    r"(?i)\b(update[_]?by|updated[_]?by|updater|update[_]?user(?:[_]?id)?|"
    r"modifier|modify[_]?by|modified[_]?by|last[_]?modified[_]?by|"
    r"update[_]?uid|updated[_]?uid)\b")
UPDATE_TIME_RE = re.compile(
    r"(?i)\b(update[_]?time|updated[_]?time|gmt[_]?modified|update[_]?at|"
    r"updated[_]?at|modify[_]?time|modified[_]?time|last[_]?modified)\b")
DELETE_FLAG_RE = re.compile(
    r"(?i)\b(is[_]?deleted|deleted|del[_]?flag|is[_]?delete|delete[_]?flag|"
    r"logic[_]?delete)\b")

# 审计人字段(含中文语义名)——用于"写死 system"命中判定
AUDIT_PERSON_TOKEN_RE = re.compile(
    r"(?i)(create[_]?by|created[_]?by|creator|create[_]?user|"
    r"update[_]?by|updated[_]?by|updater|update[_]?user|modifier|modify[_]?by|"
    r"创建人|修改人|创建者|修改者|操作人|更新人)")
# 写死的常量字面量(引号包裹)
SYSTEM_LITERAL_RE = re.compile(
    r"""['"](system|sys|admin|administrator|unknown|default|默认用户|系统|管理员)['"]""",
    re.IGNORECASE)

# 自动填充机制关键词
FILL_MECH_KEYWORDS = [
    "MetaObjectHandler", "insertFill", "updateFill", "strictInsertFill",
    "strictUpdateFill", "@CreatedBy", "@LastModifiedBy", "@CreatedDate",
    "@LastModifiedDate", "AuditorAware", "@EntityListeners", "AuditingEntityListener",
    "自动填充", "填充机制", "操作人来源", "审计填充", "@EnableJpaAuditing",
    "fill.strategy", "FieldFill",
]
# 逻辑删除上下文关键词
LOGIC_DELETE_KEYWORDS_RE = re.compile(
    r"(?i)(逻辑删除|@TableLogic|logic[\s_]?delete|软删除|soft[\s_]?delete|"
    r"set\s+(?:is[_]?deleted|deleted|del[_]?flag)\s*=\s*1)")
# 逻辑删除附近应出现的"同步修改人"信号
# 只认 setXxxBy setter 与带词界的 snake_case update_by/update_time,不认裸 camelCase
# updateBy —— 否则会误命中 ORM 方法名 updateById(每次 update 都出现)。
DELETE_SYNC_RE = re.compile(
    r"(?i)(setUpdate[d]?By|setUpdate[d]?Time|setModifier|"
    r"\bupdate_by\b|\bupdated_by\b|\bupdate_time\b|\bupdated_time\b|"
    r"updateFill|修改人|修改时间|更新人|更新时间)")

# 表名"疑似豁免"(字典/枚举/关联中间/日志流水)提示
EXEMPT_TABLE_HINT_RE = re.compile(
    r"(?i)(dict|enum|_rel$|_ref$|_map$|mapping|_log$|_logs$|log_|_record$|"
    r"_flow$|_seq$|_snapshot$|字典|枚举|关联|中间|日志|流水|快照)")

# CREATE TABLE 表头
CREATE_TABLE_HEAD_PATTERN = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"\[]?(\w+)[`\"\]]?\s*\(",
    re.IGNORECASE)


def iter_create_tables(sql_text):
    """逐表产出 (表名, 表体);表体用括号配对定位真正的结束括号,避免列内
    `VARCHAR(20) COMMENT '...'` 的 `)` 把表体提前截断。"""
    for m in CREATE_TABLE_HEAD_PATTERN.finditer(sql_text):
        name = m.group(1)
        open_idx = m.end() - 1
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
                    yield name, sql_text[open_idx + 1:j]
                    break


def scan_table_coverage(name, body):
    has_creator = bool(CREATOR_RE.search(body))
    has_ctime = bool(CREATE_TIME_RE.search(body))
    has_updater = bool(UPDATER_RE.search(body))
    has_utime = bool(UPDATE_TIME_RE.search(body))
    has_del = bool(DELETE_FLAG_RE.search(body))
    quad = [has_creator, has_ctime, has_updater, has_utime]
    if all(quad):
        level = "full"
    elif any(quad):
        level = "partial"
    else:
        level = "none"
    return {
        "table": name,
        "has_creator": has_creator,
        "has_create_time": has_ctime,
        "has_updater": has_updater,
        "has_update_time": has_utime,
        "has_delete_flag": has_del,
        "level": level,
        "exempt_hint": bool(EXEMPT_TABLE_HINT_RE.search(name)),
    }


def scan_hardcoded_system(rel_name, text):
    """逐行:同一行既有审计人 token 又有写死常量字面量 → 命中。"""
    findings = []
    for i, raw in enumerate(text.splitlines(), 1):
        if not raw.strip():
            continue
        if AUDIT_PERSON_TOKEN_RE.search(raw) and SYSTEM_LITERAL_RE.search(raw):
            findings.append({
                "file": rel_name, "line": i, "snippet": raw.strip()[:200],
            })
    return findings


def scan_fill_mechanism(text):
    found = [kw for kw in FILL_MECH_KEYWORDS if kw.lower() in text.lower()]
    return {"declared": bool(found), "keywords_found": found}


def scan_logical_delete(text):
    """逻辑删除上下文附近 ±400 字是否出现同步修改人信号。"""
    hits = []
    mentioned = False
    sync_nearby = False
    for m in LOGIC_DELETE_KEYWORDS_RE.finditer(text):
        mentioned = True
        s = max(0, m.start() - 400)
        e = min(len(text), m.end() + 400)
        window = text[s:e]
        near = bool(DELETE_SYNC_RE.search(window))
        if near:
            sync_nearby = True
        hits.append({"keyword": m.group(0)[:40], "sync_nearby": near})
    return {"mentioned": mentioned, "sync_nearby": sync_nearby, "hits": hits}


def analyze_text(rel_name, text):
    coverage = [scan_table_coverage(n, b) for n, b in iter_create_tables(text)]
    return {
        "file": rel_name,
        "coverage": coverage,
        "fill_mechanism": scan_fill_mechanism(text),
        "logical_delete": scan_logical_delete(text),
        "hardcoded_system": scan_hardcoded_system(rel_name, text),
    }


def iter_md_files(root):
    if root.is_file():
        yield root
        return
    for p in sorted(root.rglob("*.md")):
        yield p


def build_report(target):
    root = Path(target)
    per_file = []
    for p in iter_md_files(root):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel_name = str(p.relative_to(root)) if root.is_dir() else p.name
        per_file.append(analyze_text(rel_name, text))

    all_cov = [c for f in per_file for c in f["coverage"]]
    hard = [h for f in per_file for h in f["hardcoded_system"]]
    fill_declared = any(f["fill_mechanism"]["declared"] for f in per_file)
    fill_kws = sorted({k for f in per_file for k in f["fill_mechanism"]["keywords_found"]})
    ld_mentioned = any(f["logical_delete"]["mentioned"] for f in per_file)
    ld_sync = any(f["logical_delete"]["sync_nearby"] for f in per_file)

    # 软提示:疑似业务表(非豁免命名)却零审计字段
    suspect_no_audit = [c["table"] for c in all_cov
                        if c["level"] == "none" and not c["exempt_hint"]]
    partial_tables = [c["table"] for c in all_cov if c["level"] == "partial"]

    notes = []
    if not all_cov:
        notes.append("未解析到 CREATE TABLE DDL(设计可能用 Markdown 字段表,"
                     "审计字段覆盖需 Agent 人工核对)。")
    if not fill_declared:
        notes.append("全文未出现审计字段自动填充机制关键词 → 需确认 A.2/A.3 "
                     "是否显式声明填充机制 + 操作人来源(维度 30 核验点 2)。")
    if ld_mentioned and not ld_sync:
        notes.append("出现「逻辑删除」上下文但附近未见 update_by/update_time 同步信号 "
                     "→ 需确认逻辑删除是否同步更新修改人(维度 30 核验点 4)。")
    if hard:
        notes.append("命中「审计人字段 + 写死常量」疑似反模式 → 需 Agent 排除"
                     "定时任务/无登录态并显式标注的场景(维度 30 核验点 3/5)。")

    return {
        "target": str(target),
        "files_scanned": len(per_file),
        "tables_scanned": len(all_cov),
        "coverage": all_cov,
        "coverage_summary": {
            "full": sum(1 for c in all_cov if c["level"] == "full"),
            "partial": sum(1 for c in all_cov if c["level"] == "partial"),
            "none": sum(1 for c in all_cov if c["level"] == "none"),
            "suspect_business_no_audit": suspect_no_audit,
            "partial_tables": partial_tables,
        },
        "fill_mechanism": {"declared": fill_declared, "keywords_found": fill_kws},
        "logical_delete": {"mentioned": ld_mentioned, "sync_nearby": ld_sync},
        "hardcoded_system": hard,
        "notes": notes,
    }


def render_text(r):
    out = []
    out.append("【审计字段操作人溯源与自动填充回检】check_audit_field_fill.py")
    out.append(f"  扫描目标: {r['target']}  (文件 {r['files_scanned']} / 表 {r['tables_scanned']})")
    out.append("")
    cs = r["coverage_summary"]
    out.append(f"■ 审计字段覆盖: full={cs['full']} partial={cs['partial']} none={cs['none']}")
    for c in r["coverage"]:
        mark = {"full": "✅", "partial": "⚠️", "none": "❌"}[c["level"]]
        exempt = " (疑似豁免表)" if c["exempt_hint"] else ""
        out.append(f"    {mark} {c['table']}{exempt}: "
                   f"creator={_b(c['has_creator'])} c_time={_b(c['has_create_time'])} "
                   f"updater={_b(c['has_updater'])} u_time={_b(c['has_update_time'])} "
                   f"del_flag={_b(c['has_delete_flag'])}")
    if cs["suspect_business_no_audit"]:
        out.append(f"    ⚠️ 疑似业务表却零审计字段: {', '.join(cs['suspect_business_no_audit'])}")
    out.append("")

    fm = r["fill_mechanism"]
    out.append(f"■ 填充机制声明: {'✅ 已出现关键词' if fm['declared'] else '❌ 未出现关键词'}")
    if fm["keywords_found"]:
        out.append(f"    命中: {', '.join(fm['keywords_found'])}")
    out.append("")

    ld = r["logical_delete"]
    if ld["mentioned"]:
        tag = "✅ 附近有同步信号" if ld["sync_nearby"] else "⚠️ 附近未见同步信号"
        out.append(f"■ 逻辑删除同步修改人: 提及逻辑删除, {tag}")
    else:
        out.append("■ 逻辑删除同步修改人: 未出现逻辑删除上下文")
    out.append("")

    hs = r["hardcoded_system"]
    out.append(f"■ 写死 system 反模式命中: {len(hs)} 处")
    for h in hs[:40]:
        out.append(f"    {h['file']}:{h['line']}  {h['snippet']}")
    if len(hs) > 40:
        out.append(f"    ... 余 {len(hs) - 40} 处见 --json")
    out.append("")

    if r["notes"]:
        out.append("  说明/提示:")
        for n in r["notes"]:
            out.append(f"    - {n}")
        out.append("")

    out.append("  ⚠️ 本脚本仅采集信号,是否违规由 Agent 对照维度 30 结合上下文判定(退出码恒 0)。")
    return "\n".join(out)


def _b(v):
    return "有" if v else "无"


def main():
    parser = argparse.ArgumentParser(
        description="审计字段操作人溯源与自动填充合规扫描(核心原则 22 / 维度 30)")
    parser.add_argument("target", help="详细设计文档(.md)或其所在目录")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    target = Path(args.target)
    if not target.exists():
        print(f"错误:路径不存在 -> {target}", file=sys.stderr)
        return 2

    report = build_report(target)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_text(report))
    return 0  # 采集器:恒返回 0,违规判定交给 Agent


if __name__ == "__main__":
    sys.exit(main())
