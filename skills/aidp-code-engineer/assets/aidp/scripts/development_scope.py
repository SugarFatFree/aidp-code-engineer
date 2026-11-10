#!/usr/bin/env python3
"""开发前后共用的风险事实与成本摘要；只读，不授予部署、归档或生产 SQL 权限。

analyze_changes(root, *, since=None, execution_context=None, files=None,
                facts=None, before_texts=None) 比较冻结任务快照或 Sprint commit。
无显式起点且无 context 的提交门兼容调用仅比较 HEAD；无可读基线为 unknown。
任务开始已经脏的 SQL 没有原文时不能重建差异，明确 unknown，不拿全文 CREATE 充新表。
classify_development(evidence) 是开发前预计事实与开发后实际事实的同一分档函数。
"""
from collections import Counter
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

# 小型语句切分器：跳过注释，保留引号内分号；不尝试理解任意方言或存储过程。
TOKEN = re.compile(r"--[^\n]*|/\*.*?\*/|'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|`(?:``|[^`])*`|[^'\"`;/-]+|.", re.S)
DDL = re.compile(r"^(?:CREATE|ALTER|DROP|TRUNCATE|RENAME)\b", re.I)
TABLE = re.compile(r"^CREATE\s+(?:TEMPORARY\s+|TEMP\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([^\s(]+)", re.I)


def _statements(text):
    statements, current = [], []
    for match in TOKEN.finditer(text):
        token = match[0]
        if token.startswith(("--", "/*")):
            current.append(" ")
        elif token == ";":
            value = " ".join("".join(current).split())
            if value:
                statements.append(value)
            current = []
        else:
            current.append(token)
    value = " ".join("".join(current).split())
    if value:
        statements.append(value)
    return statements


def sql_delta(before, after, path):
    """只分类本次新增/变动语句；不执行 SQL，无法静态确定兼容性时保留 unknown。"""
    if before is None:
        return [{"path": path, "kind": "unknown", "reason": "缺少本任务 SQL 起点原文，需核查实际影响"}]
    old, new = _statements(before), _statements(after or "")
    old_counts = Counter(old)
    added = []
    for statement in new:
        if old_counts[statement]:
            old_counts[statement] -= 1
        else:
            added.append(statement)
    old_tables = {m[1].casefold() for statement in old if (m := TABLE.match(statement))}
    evidence = []
    for statement in added:
        upper = statement.upper()
        create = TABLE.match(statement)
        if create:
            kind = "unknown" if create[1].casefold() in old_tables else "new-table"
            reason = "修改既有 CREATE 定义，需核查迁移影响" if kind == "unknown" else "本次新增 CREATE TABLE"
        elif re.fullmatch(r"ALTER\s+TABLE\s+\S+\s+ALTER\s+(?:COLUMN\s+)?\S+\s+DROP\s+NOT\s+NULL", upper):
            kind, reason = "compatible-alter", "本次放宽字段非空约束"
        elif re.match(r"^(?:DROP|TRUNCATE|RENAME)\b", upper) or (
                re.match(r"^ALTER\s+TABLE\b", upper) and re.search(r"\b(?:DROP|RENAME)\b", upper)):
            kind, reason = "destructive", "本次包含删除、截断或重命名操作"
        elif re.match(r"^ALTER\s+TABLE\s+\S+\s+ADD\s+(?:COLUMN\s+)?[\w`\"]+\s+", upper):
            # 可确定的加列：无非空/唯一/主外键约束；其余方言与约束需要业务核查。
            if re.search(r"\b(?:NOT\s+NULL|PRIMARY|UNIQUE|REFERENCES|CONSTRAINT|CHECK|GENERATED)\b", upper):
                kind, reason = "unknown", "新增约束/生成列的兼容性需要影响核查"
            else:
                kind, reason = "compatible-alter", "本次追加无约束可空列"
        elif re.match(r"^CREATE\s+INDEX\b", upper):
            kind, reason = "compatible-alter", "本次新增普通索引，仍需核查锁表/性能影响"
        elif DDL.match(statement) or re.match(r"^(?:DO|EXECUTE|EXEC|DELIMITER)\b", upper):
            kind, reason = "unknown", "未覆盖的 DDL/动态 SQL 方言，需明确影响核查"
        else:
            continue
        evidence.append({"path": path, "kind": kind, "reason": reason, "statement": statement[:500]})
    if any(count and DDL.match(statement) for statement, count in old_counts.items()):
        evidence.append({"path": path, "kind": "unknown", "reason": "已有 DDL 被删改，需核查迁移与基线影响"})
    return evidence


def classify_development(evidence):
    """风险 L 只由新表/破坏性/架构事实触发；文件数仅是成本，不是风险。"""
    data = dict(evidence)
    for key in ("req_count", "page_count", "api_count", "changed_files", "code_files"):
        value = data.get(key, 0)
        if type(value) is not int or value < 0:
            raise ValueError(key + " 必须是非负整数")
    flags = ("has_ddl", "has_new_table", "has_destructive", "has_architecture", "ddl_unknown",
             "has_api", "has_semantic", "has_config", "cross_module", "impact_enumerated")
    for key in flags:
        if key in data and type(data[key]) is not bool:
            raise ValueError(key + " 必须是布尔值")
    sql = data.get("sql_evidence", [])
    kinds = {row["kind"] for row in sql}
    new_table = bool(data.get("has_new_table") or "new-table" in kinds)
    destructive = bool(data.get("has_destructive") or "destructive" in kinds)
    unknown = bool(data.get("ddl_unknown") or "unknown" in kinds)
    ddl = bool(data.get("has_ddl") or sql or new_table or unknown)
    complexity = {key: data.get(key, 0) for key in ("req_count", "page_count", "api_count")}
    complexity.update({key: bool(data.get(key)) for key in
                       ("has_api", "has_semantic", "has_config", "cross_module", "impact_enumerated")})
    semantic_complex = complexity["has_semantic"] and not complexity["impact_enumerated"]
    if new_table or destructive or data.get("has_architecture"):
        tier = "L"
    elif (ddl or data.get("has_api") or complexity["api_count"] or complexity["req_count"] > 5
          or complexity["page_count"] > 2 or complexity["has_config"] or complexity["cross_module"]
          or semantic_complex):
        tier = "M"
    else:
        tier = "S"
    count = data.get("changed_files", 0)
    cost = {"changed_files": count, "code_files": data.get("code_files", 0),
            "band": "XS" if count <= 2 else "S" if count <= 5 else "M" if count <= 10 else "L"}
    return {"tier": tier, "risk_tier": tier, "complexity": complexity, "cost": cost,
            "has_ddl": ddl, "has_new_table": new_table, "has_destructive": destructive,
            "has_architecture": bool(data.get("has_architecture")), "ddl_unknown": unknown,
            "sql_evidence": sql, "impact_check_required": bool(ddl or destructive or tier == "L"),
            "semantic_check_required": "需求、页面、接口、规则与架构影响需按任务事实补充，档位不授予动作权限"}


def _git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True)


def _safe_file(root, rel):
    path = root / rel
    if Path(rel).is_absolute() or ".." in Path(rel).parts or not path.resolve().is_relative_to(root):
        raise ValueError("变更路径越出项目：" + rel)
    if path.is_symlink():
        raise ValueError("SQL/开发范围不接受符号链接：" + rel)
    return path


def _before(root, since, rel):
    if not since:
        return None
    tree = _git(root, "ls-tree", "-z", since, "--", rel)
    if tree.returncode:
        return None
    if not tree.stdout:
        # gitlink 内没有父仓 blob，不能把子模块已有文件误认为新增。
        if any((parent / ".git").exists() for parent in (root / rel).parents if parent != root and root in parent.parents):
            return None
        return ""
    content = _git(root, "show", f"{since}:{rel}")
    return content.stdout.decode("utf-8") if content.returncode == 0 else None


def analyze_changes(root, *, since=None, execution_context=None, files=None, facts=None, before_texts=None):
    root = Path(root).resolve()
    context = None
    if execution_context is not None:
        from entry_context import load_context, validate_context
        context = (validate_context(root, execution_context) if isinstance(execution_context, dict)
                   else load_context(root, execution_context))
        if since is not None and since != context["since"]:
            raise ValueError("不能替换冻结任务的起点")
        since = context["since"]
    explicit_since = since is not None
    if since is None and context is None:
        head = _git(root, "rev-parse", "--verify", "HEAD^{commit}")
        since = head.stdout.decode().strip() if head.returncode == 0 else None
    elif since:
        if since.startswith("-") or _git(root, "rev-parse", "--verify", since + "^{commit}").returncode:
            raise ValueError("无法读取开发范围起点：" + since)
    candidates = set()
    if context:
        import entry_context
        from entry_context import initial_file_hash
        initial = context["initial_files"]
        if context.get("git_status") == "supported":
            from project_inventory import git_worktree_inventory
            observed = git_worktree_inventory(root, since=since)
            current = set(observed["files"])
            # Git 先确定可能变化的文件，再计算内容摘要；干净且未变的源码无需读取。
            possible = (set(observed["preexisting_dirty"]) | set(context.get("preexisting_dirty", []))
                        | (initial.keys() ^ current))
            candidates = {p for p in possible
                          if (entry_context.initial_hash(root, context, p) if context.get("initial_git_files")
                              else initial.get(p)) != initial_file_hash(root / p)}
        else:
            from aidp_paths import runtime_dir
            runtime = Path(runtime_dir(root))
            current = {p.relative_to(root).as_posix() for p in root.rglob("*")
                       if p.is_file() and runtime not in p.parents and ".git" not in p.parts}
            candidates = {p for p in initial.keys() | current if initial.get(p) != initial_file_hash(root / p)}
    elif since:
        from project_inventory import git_worktree_inventory
        candidates.update(git_worktree_inventory(root, since=since)["preexisting_dirty"])
    elif files:
        candidates.update(files)
    excluded = set()
    if context and context.get("write_set"):
        declared = context["write_set"]
        selected = {p for p in candidates if any(f == "." or p == f or p.startswith(f.rstrip("/") + "/") for f in declared)}
        excluded = candidates - selected
        candidates = selected
    if files is not None:
        requested = list(files)
        candidates = {p for p in candidates if any(f == "." or p == f or p.startswith(f.rstrip("/") + "/") for f in requested)}
    before_texts = before_texts or {}
    sql, changed = [], sorted(candidates)
    for rel in changed:
        path = _safe_file(root, rel)
        if path.suffix.lower() != ".sql":
            continue
        after = path.read_text(encoding="utf-8") if path.is_file() else ""
        if rel in before_texts:
            before = before_texts[rel]
        elif context and rel in context.get("preexisting_dirty", []):
            before = None
        elif context and rel not in context["initial_files"]:
            before = ""
        else:
            before = _before(root, since, rel)
        sql.extend(sql_delta(before, after, rel))
        if not context and since:
            indexed = _git(root, "show", ":" + rel)
            if indexed.returncode == 0:
                staged = indexed.stdout.decode("utf-8")
                if staged != after:
                    sql.extend(sql_delta(before, staged, rel))
    data = dict(facts or {})
    data.update(changed_files=len(changed), code_files=sum(p.startswith("code/") for p in changed), sql_evidence=sql)
    result = classify_development(data)
    result["scope"] = {"kind": "task" if context else "sprint" if explicit_since else "head-delta",
                       "since": since, "task_id": context.get("task_id") if context else None,
                       "files": changed, "excluded_files": sorted(excluded),
                       "baseline_available": bool(since or context or before_texts)}
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--since")
    parser.add_argument("--execution-context")
    parser.add_argument("--files", action="append", help="可重复相对文件/目录，用于收窄本轮范围")
    parser.add_argument("--facts-json", default="{}", help="开发前预计/开发后核对的需求、页面、接口、规则事实")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        facts = json.loads(args.facts_json)
        if not isinstance(facts, dict):
            raise ValueError("facts-json 必须是对象")
        result = analyze_changes(args.root, since=args.since, execution_context=args.execution_context,
                                 files=args.files, facts=facts)
    except (OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
