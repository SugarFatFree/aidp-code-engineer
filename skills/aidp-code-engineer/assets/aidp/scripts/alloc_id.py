#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""原子保留业务编号；账本是已保留号的权威，未使用的空洞永不回收。

allocate(root, kind, count, owner, *, version='', scope='', prefix=None) 返回
{ids, kind, scope, version, prefix, start, end, count, owner, seed_max, source_files, ...}。
check_ledger(root) 是只读门禁，返回 {passed, errors, reservations}；历史编号无需补登记。

scope 缺省：C=changes（四族开发期增量），BUG=bugs，REQ/Q=requirements，
D=design，ADR=architecture，TC=testing。bugs 扫 docs/bugfix 与 docs/testing，
排除开发期增量。C --scope bugs 用于测试缺陷，不能和开发变更混用。
也可传 docs/ 或 memory/ 下相对文件/目录；相交路径共用保留高水位，禁止绕 scope 撞号。
version 空时扫描该域全部版本；非空仅扫描该版本。跨版本旧编号不算重号。
prefix 缺省 kind，可传 REQ-V1.2、REQ-3P、REQ-3P-CB、REQ-V1.2-A。

锁和账本仅约束同 checkout，不承诺跨 clone 分配互斥。每次锁内重扫源文档，
兼容升级前/合并带来的未登记编号。账本只在 memory 本地运行态创建，不是模板资产。
退出码 0=成功，1=账本/源数据错误，2=CLI 入参错误。
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(Path(__file__).resolve().parent))
from aidp_paths import id_alloc_ledger
from aidp_runtime import project_root
from baseline_edit import lock_path

KINDS = ("C", "BUG", "REQ", "Q", "D", "ADR", "TC")
DEFAULT_SCOPE = dict(C="changes", BUG="bugs", REQ="requirements", Q="requirements",
                     D="design", ADR="architecture", TC="testing")
SCOPE_ROOTS = {
    "changes": ("docs/requirements", "docs/design", "docs/plans", "docs/testing"),
    "bugs": ("docs/bugfix", "docs/testing"),
    "testing": ("docs/testing",),
    "requirements": ("docs/requirements",),
    "design": ("docs/design",),
    "architecture": ("memory/systemPatterns.md", "docs/architecture"),
}
VERSION_RE = re.compile(r"V\d+(?:\.\d+)*(?:[-_][A-Za-z0-9.]+)?$")
ID_RE = re.compile(r"(?<![A-Za-z0-9_-])(?:ADR|BUG|REQ|TC|C|Q|D)-[A-Za-z0-9][A-Za-z0-9_.-]*")
NON_CHANGE_SCOPES = {"requirements", "design", "bugs", "testing"}
SCHEMA = 1


def _safe_path(root, rel):
    """不跟随文档/账本 symlink，避免扫描或写到另一个编号空间。"""
    path = Path(root)
    for part in Path(rel).parts:
        path /= part
        if path.is_symlink():
            raise ValueError("编号路径不可为 symlink: %s" % path)
    return path


def _scope(scope):
    if scope in SCOPE_ROOTS:
        return scope
    path = Path(scope)
    if (not scope or path.is_absolute() or ".." in path.parts or
            path.parts[0] not in ("docs", "memory") or
            any(p.startswith(".") for p in path.parts)):
        raise ValueError("scope 必须为预置域或 docs/memory 下的相对源路径")
    return path.as_posix()


def _prefix(kind, prefix):
    value = prefix or kind
    if not re.fullmatch(re.escape(kind) + r"(?:-[A-Za-z0-9][A-Za-z0-9_.-]*)?-?", value):
        raise ValueError("prefix 必须以 kind 开头且只含字母、数字、点、下划线和连字符")
    value = value.rstrip("-")
    # 旧编号 REQ-V0.10-A02 的数字紧接单字母；其余前缀以 - 隔开。
    return value if re.search(r"-[A-Za-z]$", value) else value + "-"


def _version(path):
    return next((p for p in Path(path).parts if VERSION_RE.fullmatch(p)), "")


def _roots(scope):
    return SCOPE_ROOTS.get(scope, (scope,))


def _overlaps(a, b):
    if a["kind"] != b["kind"] or a["prefix"] != b["prefix"]:
        return False
    if ((a["scope"] == "changes" and b["scope"] in NON_CHANGE_SCOPES) or
            (b["scope"] == "changes" and a["scope"] in NON_CHANGE_SCOPES)):
        return False  # 目录可相交，但开发增量与正式文档集合互斥。
    av = a["version"] or _version(a["scope"])
    bv = b["version"] or _version(b["scope"])
    if av and bv and av != bv:
        return False
    return any(x == y or x.startswith(y + "/") or y.startswith(x + "/")
               for x in _roots(a["scope"]) for y in _roots(b["scope"]))


def _is_change(path):
    return "开发期" in path.name and "增量" in path.name


def _in_scope(scope, path):
    if scope == "changes":
        return _is_change(path)
    return scope not in NON_CHANGE_SCOPES or not _is_change(path)


def _files(root, scope, version=""):
    for rel in _roots(scope):
        base = _safe_path(root, rel)
        if not base.exists():
            continue
        def walk_error(exc):
            raise exc
        candidates = [base] if base.is_file() else []
        if base.is_dir():
            for directory, dirs, names in os.walk(base, onerror=walk_error):
                for name in dirs + names:
                    candidate = Path(directory) / name
                    if candidate.is_symlink():
                        raise ValueError("编号源路径不可为 symlink: %s" % candidate)
                dirs[:] = sorted(d for d in dirs if not d.startswith("."))
                candidates.extend(Path(directory) / n for n in sorted(names) if n.endswith(".md"))
        for path in candidates:
            relative = path.relative_to(root)
            if any(p.startswith(".") for p in relative.parts) or path.suffix != ".md":
                continue
            _safe_path(root, relative)
            if version and _version(relative) != version:
                continue
            if not _in_scope(scope, path):
                continue
            # 导航索引可参与 seed，但不会作为独立定义；模板教学目录永不扫描。
            if len(relative.parts) > 1 and relative.parts[1] in ("init", "templates", "reports"):
                continue
            yield path


def _lines(path):
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"<!--.*?-->", lambda m: "\n" * m.group().count("\n"), text, flags=re.S)
    fence = ""
    for n, line in enumerate(text.splitlines(), 1):
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            if not fence:
                fence = marker.group(1)
            elif marker.group(1)[0] == fence[0] and len(marker.group(1)) >= len(fence):
                fence = ""
            continue
        if not fence:
            yield n, line


def _seed(root, spec):
    maximum, sources = 0, []
    rx = re.compile(r"(?<![A-Za-z0-9_-])" + re.escape(spec["prefix"]) + r"(\d+)(?![A-Za-z0-9_.])")
    for path in _files(root, spec["scope"], spec["version"]):
        sources.append(path.relative_to(root).as_posix())
        for _, line in _lines(path):
            for match in rx.finditer(line):
                maximum = max(maximum, int(match.group(1)))
    return maximum, sources


def _definition_ids(path):
    """标题及表格首列为候选定义；按可核验上下文排除报告引用与审计维度。

    复测/验证结果表（不含问题描述列）是引用；报告内仅有复测状态的行也是引用。
    审计上下文的短号 C-4/C-5 是维度，三位业务号 C-004/C-005 仍是定义。
    不按 testing/报告目录整体豁免：报告里的新缺陷、真实问题清单照常判重。
    同文件目录表+标题以标题为准；纯链接、普通引用、注释、围栏过滤保持不变。
    """
    if path.name in ("00_索引.md", "README.md"):
        return []
    heads, rows, bullets = [], [], []
    reference_section = False
    audit_context = "审计" in path.stem or "audit" in path.parts
    report_context = bool(re.search(r"报告|复测|回归", path.stem))
    table_reference = False
    table_dimension = False
    for n, line in _lines(path):
        stripped = line.strip()
        heading = re.match(r"^#{1,6}\s+(.+)", stripped)
        if heading and _is_change(path):
            reference_section = "已知失准" in heading.group(1)
        if reference_section:
            continue
        bullet = re.match(r"^[-*+]\s+(.+)", stripped)
        cells = stripped.strip("|").split("|") if stripped.startswith("|") else []
        cell = cells[0].strip() if len(cells) > 1 else ""
        if heading:
            audit_context = audit_context or "审计" in heading.group(1)
            report_context = report_context or bool(re.search(r"报告|复测|回归", heading.group(1)))
        if not cells:
            table_reference = table_dimension = False
        elif not ID_RE.search(cell) and not re.fullmatch(r"[\s:*-]+", cell):
            header = "|".join(cells)
            has_description = any(re.search(r"描述|标题|现象|症状|原因", c)
                                  or c.strip("*` ") in ("问题", "缺陷", "内容") for c in cells[1:])
            table_reference = bool(re.search(r"复测结果|回归结果|验证结果|引用来源", header)
                                   and not has_description)
            table_dimension = bool(re.search(r"审计项|审计维度|维度编号", header))
        if table_reference and not (heading or bullet):
            continue
        if len(cells) > 1 and re.fullmatch(r"\s*\[[^\]]+\]\([^)]+\)\s*", cells[1]):
            continue  # 编号 + 来源链接的导航行，不是第二份正文定义。
        text = heading.group(1) if heading else bullet.group(1) if bullet else cell
        if not text or re.search(r"\[[^\]]+\]\(", text):
            continue
        text = text.strip("*` ")
        # 标题可为 REQ-001 标题或 标题（REQ-V1-A02）；不把“参见 REQ-001”当定义。
        matches = list(ID_RE.finditer(text))
        for m in matches:
            rid = m.group().rstrip(".")
            payload = text[m.end():] if heading or bullet else " ".join(cells[1:])
            dimension_name = re.search(r"PRD|原子.*(?:覆盖|核对)|字段.*(?:覆盖|核对|设计)|审计维度", payload, re.I)
            if rid in ("C-4", "C-5") and (table_dimension or (audit_context and dimension_name)):
                continue
            # 仅状态的报告条目是对既有编号的复测引用；有实质问题描述仍参与判重。
            status = re.sub(r"[\s*`，,。:：|✅]+", "", payload)
            if report_context and re.fullmatch(r"(?:已修复|已关闭)?(?:复测|回归|验证)(?:已)?(?:通过|失败|未通过)", status):
                continue
            if not re.search(r"\d", rid):
                continue
            if m.start() and not (heading and text[m.start() - 1] in "（("):
                continue
            if not (heading or bullet) and rid != text:
                continue
            if bullet and not re.match(r"^[*`\s]*[·:：]", text[m.end():]):
                continue
            (heads if heading else bullets if bullet else rows).append((rid, n))
    head_ids = {rid for rid, _ in heads}
    return heads + bullets + [(rid, n) for rid, n in rows if rid not in head_ids]


def _definition_errors(root, records):
    # 默认只扫各 kind 的源域，避免下游设计/计划中的 REQ 引用冒充需求定义。
    scans = {(kind, scope, "") for kind, scope in DEFAULT_SCOPE.items()}
    scans.add(("C", "bugs", ""))
    scans.update((r["kind"], r["scope"], r["version"]) for r in records)
    occurrences = {}
    for kind, scope, version in sorted(scans):
        for path in _files(root, scope, version):
            rel = path.relative_to(root).as_posix()
            for rid, line in _definition_ids(path):
                if not rid.startswith(kind + "-"):
                    continue
                # 同一 C 变更横跨四族是合法对应条目；同族内两个定义仍阻断。
                domain = next((name for name in ("requirements", "design", "plans", "testing", "bugfix")
                               if name in Path(rel).parts), str(Path(rel).parent))
                if kind in ("C", "BUG") and domain in ("testing", "bugfix") and not _is_change(path):
                    domain = "bugs"  # 两个目录同属缺陷空间，历史未登记条目也按此判重。
                matching = []
                for record in records:
                    if record["kind"] != kind or not rid.startswith(record["prefix"]):
                        continue
                    if record["version"] and record["version"] != _version(rel):
                        continue
                    if not _in_scope(record["scope"], path):
                        continue
                    for base in _roots(record["scope"]):
                        if rel == base or rel.startswith(base + "/"):
                            matching.append((len(Path(base).parts), record["scope"]))
                if matching:
                    # 最宽的已登记冲突域优先；只有窄域登记时，互不相交的自定义域保持独立。
                    selected = min(matching)[1]
                    domain = selected + (":" + domain if selected == "changes" else "")
                elif kind == "ADR":
                    domain = "architecture"
                norm = re.sub(r"(?<=-)0+(?=\d)", "", rid)
                key = (kind, _version(rel), domain, norm)
                occurrences.setdefault(key, set()).add((rel, line))
    errors = []
    for key, locations in sorted(occurrences.items()):
        if len(locations) > 1:
            errors.append({"check": "duplicate-definition", "id": key[-1],
                           "version": key[1], "scope": key[2],
                           "locations": [{"file": p, "line": n} for p, n in sorted(locations)],
                           "message": "同一编号空间存在多个正文定义"})
    return errors


def _read_ledger(path):
    if not path.exists():
        return []
    raw = path.read_text(encoding="utf-8")
    if not raw or not raw.endswith("\n"):
        raise ValueError("编号账本为空或尾行截断，拒绝重新 seed")
    records = []
    for line_no, line in enumerate(raw.splitlines(), 1):
        try:
            r = json.loads(line)
            if not isinstance(r, dict) or type(r.get("schema_version")) is not int or r["schema_version"] != SCHEMA:
                raise ValueError("未知 schema")
            for key in ("kind", "scope", "version", "prefix", "owner", "created_at"):
                if not isinstance(r.get(key), str):
                    raise ValueError("字段不是字符串: " + key)
            if r["kind"] not in KINDS or _scope(r["scope"]) != r["scope"]:
                raise ValueError("kind/scope 无效")
            if _prefix(r["kind"], r["prefix"]) != r["prefix"]:
                raise ValueError("prefix 未归一")
            if not r["owner"].strip() or not r["created_at"]:
                raise ValueError("缺 owner/created_at")
            if r["version"] and not VERSION_RE.fullmatch(r["version"]):
                raise ValueError("version 无效")
            for key in ("start", "end", "count", "seed_max"):
                if type(r.get(key)) is not int:
                    raise ValueError("非整数范围: " + key)
            if not (r["start"] >= 1 and 1 <= r["count"] <= 10000 and r["seed_max"] >= 0 and
                    r["end"] == r["start"] + r["count"] - 1 and r["start"] > r["seed_max"]):
                raise ValueError("范围不合法")
            if not isinstance(r.get("source_files"), list) or not all(isinstance(p, str) for p in r["source_files"]):
                raise ValueError("source_files 无效")
            if r.get("ids") != [r["prefix"] + "%03d" % n for n in range(r["start"], r["end"] + 1)]:
                raise ValueError("ids 与范围不一致")
            for previous in records:
                if _overlaps(r, previous) and r["start"] <= previous["end"]:
                    raise ValueError("保留范围重叠或高水位倒退")
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError("编号账本第 %d 行损坏: %s" % (line_no, exc)) from exc
        records.append(r)
    return records


@contextmanager
def _locked(root):
    # 复用仓库统一 lock_path；锁失败必须失败，不能使用 baseline 的无锁降级。
    import fcntl
    path = Path(id_alloc_ledger(root))
    _safe_path(root, path.relative_to(root))
    lock = Path(lock_path(str(path)))
    _safe_path(root, lock.relative_to(root))
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield path
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def allocate(root, kind, count, owner, *, version="", scope="", prefix=None):
    root = Path(root).absolute()
    if not root.is_dir():
        raise ValueError("root 必须为已有项目目录")
    if kind not in KINDS or type(count) is not int or not 1 <= count <= 10000:
        raise ValueError("kind 无效或 count 不在 1..10000")
    if not isinstance(owner, str) or not owner.strip():
        raise ValueError("owner 不能为空")
    if version and not VERSION_RE.fullmatch(version):
        raise ValueError("version 必须为 V 开头版本号")
    scope = _scope(scope or DEFAULT_SCOPE[kind])
    if kind == "ADR" and scope == "architecture" and version:
        raise ValueError("architecture 的 ADR 是项目级编号，请省略 --version")
    if version and _version(scope) and version != _version(scope):
        raise ValueError("version 与 scope 中版本不一致")
    spec = dict(kind=kind, scope=scope, version=version, prefix=_prefix(kind, prefix))
    with _locked(root) as path:
        records = _read_ledger(path)
        seed, sources = _seed(root, spec)
        high = max([seed] + [r["end"] for r in records if _overlaps(r, spec)])
        record = dict(spec, schema_version=SCHEMA, start=high + 1, end=high + count,
                      count=count, owner=owner.strip(), seed_max=seed, source_files=sources,
                      created_at=datetime.now(timezone.utc).isoformat())
        record["ids"] = [spec["prefix"] + "%03d" % n for n in range(high + 1, high + count + 1)]
        # 一个保留批次一行；fsync 完成才返回。中途写失败留下的截断行由下次读显式拒绝。
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    return record


def check_ledger(root):
    """只读检查；无账本仍可检查历史多定义，绝不创建空账本或强制补登记。"""
    root = Path(root).absolute()
    records, errors = [], []
    try:
        if not root.is_dir():
            raise ValueError("root 必须为已有项目目录")
        path = Path(id_alloc_ledger(root))
        _safe_path(root, path.relative_to(root))
        if path.exists():
            with _locked(root) as path:
                records = _read_ledger(path)
        errors.extend(_definition_errors(root, records))
    except (OSError, ValueError, ImportError) as exc:
        errors.append({"check": "ledger-invalid", "message": str(exc)})
    return {"passed": not errors, "errors": errors, "reservations": len(records)}


def self_check():
    """下发后也能自检，不依赖模板专属 tests/；正反例及真实子进程竞争。"""
    with tempfile.TemporaryDirectory(prefix="aidp-id-check-") as temp:
        root = Path(temp)
        source = root / "docs/requirements/V1/研发需求/90_开发期增量.md"
        source.parent.mkdir(parents=True)
        source.write_text("## C-007 已有变更\n参见 C-007。\n", encoding="utf-8")
        first = allocate(root, "C", 3, "probe")
        checks = {"seed": first["ids"] == ["C-008", "C-009", "C-010"],
                  "holes_and_references": check_ledger(root)["passed"]}
        issues = root / "docs/testing/V1/正式用例/问题清单.md"
        issues.parent.mkdir(parents=True)
        issues.write_text("| C-020 | 测试缺陷 |\n## TC-PTS-012 用例\n", encoding="utf-8")
        (issues.parent / "_开发期用例增量.md").write_text("- C-999 · 11-05 · 开发变更\n", encoding="utf-8")
        checks["testing_bug_scope"] = allocate(root, "C", 1, "probe", scope="bugs")["ids"] == ["C-021"]
        checks["tc_module_prefix"] = allocate(root, "TC", 1, "probe", prefix="TC-PTS")["ids"] == ["TC-PTS-013"]
        def child(n):
            p = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--root", temp,
                                "--kind", "C", "--count", "2", "--owner", str(n), "--json"],
                               capture_output=True, text=True, timeout=30)
            if p.returncode:
                raise ValueError(p.stderr or p.stdout)
            return json.loads(p.stdout)["ids"]
        with ThreadPoolExecutor(max_workers=4) as pool:
            ids = [rid for batch in pool.map(child, range(4)) for rid in batch]
        checks["concurrent_lock"] = len(set(ids)) == 8 and check_ledger(root)["passed"]
        source.write_text("## C-007 一\n## C-007 二\n", encoding="utf-8")
        checks["duplicate_definition"] = not check_ledger(root)["passed"]
        path = Path(id_alloc_ledger(root))
        with path.open("a", encoding="utf-8") as handle:
            handle.write('{"broken":')
        before = path.read_bytes()
        try:
            allocate(root, "C", 1, "probe")
            checks["corrupt_fail_closed"] = False
        except ValueError:
            checks["corrupt_fail_closed"] = path.read_bytes() == before
        return {"passed": all(checks.values()), "checks": checks}


def main(argv=None):
    ap = argparse.ArgumentParser(description="原子保留 C/BUG/REQ/Q/D/ADR/TC 编号，允许保留空洞")
    ap.add_argument("--root", help="项目根；默认按运行包解析 AIDP_PROJECT_ROOT")
    ap.add_argument("--kind", choices=KINDS)
    ap.add_argument("--count", type=int, default=1)
    ap.add_argument("--owner")
    ap.add_argument("--version", default="", help="空值扫该作用域所有版本")
    ap.add_argument("--scope", default="", help="逻辑域或 docs/memory 下的源文件/目录")
    ap.add_argument("--prefix", help="完整编号前缀，如 REQ-V1.2 或 REQ-3P-CB")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--check", action="store_true", help="只读账本和重复定义检查")
    ap.add_argument("--self-check", action="store_true")
    args = ap.parse_args(argv)
    if not (args.check or args.self_check) and (not args.kind or not args.owner):
        ap.error("分配需 --kind 和 --owner")
    try:
        root = Path(args.root).absolute() if args.root else project_root(__file__)
        if args.self_check:
            result = self_check()
        elif args.check:
            result = check_ledger(root)
        else:
            result = allocate(root, args.kind, args.count, args.owner,
                              version=args.version, scope=args.scope, prefix=args.prefix)
        if args.json:
            print(json.dumps(result, ensure_ascii=False))
        elif "ids" in result:
            print("\n".join(result["ids"]))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("passed", True) else 1
    except (OSError, ValueError, ImportError, RuntimeError) as exc:
        if args.json:
            print(json.dumps({"passed": False, "errors": [{"check": "allocation-failed", "message": str(exc)}]}, ensure_ascii=False))
        else:
            print("[ERROR] %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
