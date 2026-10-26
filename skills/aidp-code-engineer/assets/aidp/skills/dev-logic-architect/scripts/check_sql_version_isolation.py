#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SQL 版本隔离硬核回检 — dev-logic-architect 维度 22 Module D 子项

Module D 「SQL 版本严格隔离」铁律核验:
  V1  英文通用名禁止 — 严禁 init.sql / schema.sql / migration.sql / baseline.sql
                       / database.sql / all.sql / full.sql 等英文通用名
  V2  基线复制检测   — 当前版本与上一版本 SQL 文件比较,业务行重复过多视为
                       "复制基线"违规;Critical 阻塞。注:本脚本先过滤模板/语法
                       噪声(CREATE/纯括号/分号等),再以"≥ 5 行业务字段重复"判定;
                       等价于 checklist 里 `comm -12 | wc -l` 原始法的 ≥ 10 行
                       (原始法未过滤模板噪声,故阈值取更高的 10)
  V3  空目录违规     — 本版本无 DDL 变更时不应创建 {SQL脚本目录}/v{version}/
                       目录(允许仅有 00_README.md 一句话说明)
  V4  中文命名+序号  — 文件名必须 `{NN}_{中文描述}.sql`,99_ 固定回滚

  V5  两轨之外有 SQL — 仅 versioned:版本目录内 sql/增量、sql/全量 之外的 .sql
                       (如 V1.2.0/init.sql、V1.2.0/sql/schema.sql)一律判 error,
                       并照常过 V1/V4 —— 否则它们对本门完全隐形(假绿)

两种目录布局(--layout,缺省 auto 自动识别):
  flat       {SQL根目录}/{version}/*.sql               —— 每个版本一个目录,**只扫版本目录当层**
                                                         (缺省行为与早期版本一致,子目录不扫)
  versioned  {部署根目录}/{version}/sql/增量/**/*.sql  —— 按版本目录 + 增量/全量双轨,两轨内递归
             {部署根目录}/{version}/sql/全量/**/*.sql
             V1/V3/V4 两轨都校;两轨之外的 .sql 判 V5(并过 V1/V4);
             V2 比较本版「增量」轨与上一版「增量」轨;上一版**只有全量轨**时改与其全量轨比较
             (本版增量照抄上一版全量 = 复制基线)。本版全量轨按定义就是整库快照,
             与上一版重复是常态,不参与 V2
  auto       {根}/{version}/sql/增量 或 sql/全量 存在 → versioned,否则 flat
  (`two-track` 是 versioned 的兼容别名。)
  版本目录名的 `v` / `V` 前缀都认:`--version v1.2.0` 能命中 `V1.2.0/`,反之亦然。

使用:
  python check_sql_version_isolation.py <SQL根目录> --version <当前版本号>
  python check_sql_version_isolation.py <部署根目录> --version V1.2.0 --layout versioned
  python check_sql_version_isolation.py <根目录> --version v1.2.0 --prev v1.1.0 --json
  python check_sql_version_isolation.py --self-check   # 内建夹具阳性/阴性对照,不可与 path/--json/--version/--prev/--layout 组合

SQL 根目录**不存在** → exit 0 + `--json` 出 `skipped: true`(项目早期尚未建 SQL 目录,刻意的 N/A 跳过,
不等于通过);路径存在但**不是目录** → 入参错。

退出码: 0 通过或 N/A 跳过 / 1 不通过 / 2 用法或环境错误
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# V1 英文通用名黑名单
ENGLISH_GENERIC_NAMES = re.compile(
    r"^(init|schema|migration|baseline|database|all|full|create_all|setup|main)\.sql$",
    re.IGNORECASE,
)

# V4 文件名规范: NN_中文描述.sql
VALID_NAME_PATTERN = re.compile(r"^\d{2}_[一-鿿].*\.sql$")
# 99_ 固定回滚
ROLLBACK_NAME_PATTERN = re.compile(r"^99_.*回滚.*\.sql$")


def normalize_sql_line(line: str) -> str:
    """规范化 SQL 行用于基线对比(去注释/空白/空行)"""
    # 去单行注释
    line = re.sub(r"--.*$", "", line)
    line = re.sub(r"#.*$", "", line)
    line = line.strip()
    return line


TRACK_INC = ("sql", "增量")
TRACK_FULL = ("sql", "全量")
LAYOUT_CHOICES = ("auto", "flat", "versioned", "two-track")
VERSION_DIR_RE = re.compile(r"^[vV]?\d+\.\d+")


def list_sql_files(d: Optional[Path], recursive: bool = True) -> List[Path]:
    """列出目录下 .sql。versioned 两轨内递归;flat 只扫当层(recursive=False)。"""
    if d is None or not d.is_dir():
        return []
    it = d.rglob("*.sql") if recursive else d.glob("*.sql")
    return sorted(p for p in it if p.is_file())


def collect_sql_lines_from(files: List[Path]) -> List[str]:
    lines: List[str] = []
    for sql in files:
        try:
            for raw in sql.read_text(encoding="utf-8", errors="replace").splitlines():
                norm = normalize_sql_line(raw)
                if norm and len(norm) >= 10:  # 过滤掉过短行(单括号、单分号等)
                    lines.append(norm)
        except Exception:
            continue
    return lines


def _norm_version(name: str) -> str:
    """版本标识归一:去掉 `v`/`V` 前缀,用于「同一版本」判定(`v1.2.0` ≡ `V1.2.0` ≡ `1.2.0`)。"""
    return name[1:] if name[:1] in ("v", "V") else name


def _canonical_layout(layout: str) -> str:
    return "versioned" if layout == "two-track" else layout


def find_base_version_dir(root: Path, version: str) -> Optional[Path]:
    """{root}/{version};精确名优先,其次按去 `v`/`V` 前缀后的版本标识匹配。"""
    candidate = root / version
    if candidate.is_dir():
        return candidate
    want = _norm_version(version)
    for d in sorted(root.iterdir()):
        if d.is_dir() and _norm_version(d.name) == want:
            return d
    return None


def detect_layout(root: Path, version: str) -> str:
    vd = find_base_version_dir(root, version)
    if vd is not None and (vd.joinpath(*TRACK_INC).is_dir() or vd.joinpath(*TRACK_FULL).is_dir()):
        return "versioned"
    return "flat"


def find_version_dir(root: Path, version: str, layout: str = "flat") -> Optional[Path]:
    """flat 返回 {root}/{version};versioned 返回 {root}/{version}/sql/增量(不存在返回 None)。"""
    base = find_base_version_dir(root, version)
    if _canonical_layout(layout) == "versioned":
        if base is None:
            return None
        inc = base.joinpath(*TRACK_INC)
        return inc if inc.is_dir() else None
    return base


def _version_key(name: str) -> tuple:
    """把版本目录名解析为数字元组用于比较(避免字典序把 1.10 误判为早于 1.2)。"""
    return tuple(int(x) for x in re.findall(r"\d+", _norm_version(name)))


def _has_track(d: Path) -> bool:
    return d.joinpath(*TRACK_INC).is_dir() or d.joinpath(*TRACK_FULL).is_dir()


def find_prev_version_dir(root: Path, current_version: str, layout: str = "flat") -> Optional[Path]:
    """启发式查找上一版本目录: 同目录下数字版本号紧邻 current 之前的版本目录
    (versioned 只认带 sql/增量 或 sql/全量 的版本目录,返回版本基目录)"""
    versioned = _canonical_layout(layout) == "versioned"
    versions = sorted(
        [d for d in root.iterdir() if d.is_dir() and VERSION_DIR_RE.match(d.name)
         and (not versioned or _has_track(d))],
        key=lambda d: _version_key(d.name),
    )
    cur_key = _version_key(current_version)
    prev: Optional[Path] = None
    for d in versions:
        d_key = _version_key(d.name)
        if d_key < cur_key:
            prev = d
        elif d_key == cur_key:
            break
    return prev


def _rel(p: Path, root: Path) -> str:
    """消息里用相对根目录的路径(flat 下即版本目录名,与早期输出一致)。"""
    try:
        return str(p.relative_to(root))
    except ValueError:
        return str(p)


def _prev_baseline_files(prev_base: Optional[Path]) -> Tuple[List[Path], Optional[Path]]:
    """versioned 下上一版的 V2 比对面:有增量轨用增量轨;只有全量轨时用全量轨。"""
    if prev_base is None:
        return [], None
    inc = prev_base.joinpath(*TRACK_INC)
    if inc.is_dir():
        return list_sql_files(inc), inc
    full = prev_base.joinpath(*TRACK_FULL)
    if full.is_dir():
        return list_sql_files(full), full
    return [], None


def check_version(root: Path, version: str, prev_version: Optional[str],
                  layout: str = "auto") -> Tuple[List[Dict], Dict]:
    issues: List[Dict] = []
    requested = _canonical_layout(layout)
    if requested == "auto":
        layout = detect_layout(root, version)
    else:
        layout = requested
    summary: Dict = {"version": version, "layout": layout, "layout_requested": requested,
                     "version_dir": None, "sql_files": 0,
                     "prev_dir": None, "duplicate_lines": 0}

    base = find_base_version_dir(root, version)
    version_dir = find_version_dir(root, version, layout)
    inc_files: List[Path] = []
    full_files: List[Path] = []
    outside_files: List[Path] = []
    if layout == "versioned":
        if base is not None:
            inc_files = list_sql_files(base.joinpath(*TRACK_INC))
            full_files = list_sql_files(base.joinpath(*TRACK_FULL))
            in_track = set(inc_files) | set(full_files)
            outside_files = [p for p in list_sql_files(base) if p not in in_track]
    else:
        inc_files = list_sql_files(version_dir, recursive=False)
    if version_dir is None and not full_files and not outside_files:
        # V3: 无目录是合法的(本版本无 DDL 变更)
        summary["version_dir"] = "(不存在,视为本版本无 DDL 变更)"
        return issues, summary

    summary["version_dir"] = str(version_dir) if version_dir else "(无增量轨)"

    sql_files = inc_files + full_files + outside_files
    summary["sql_files"] = len(sql_files)
    if layout == "versioned":
        summary["outside_track_files"] = len(outside_files)
        for f in outside_files:
            issues.append({
                "rule": "V5_两轨之外有SQL",
                "level": "error",
                "file": str(f.relative_to(base)),
                "msg": f"{f.relative_to(base)} 位于 sql/增量、sql/全量 两轨之外;"
                       f"双轨布局下 SQL 只允许放进两轨之一",
            })

    # V3: 仅有空文件或注释占位的违规
    if sql_files:
        all_empty = True
        for f in sql_files:
            text = f.read_text(encoding="utf-8", errors="replace")
            non_comment = [l for l in text.splitlines()
                           if normalize_sql_line(l)]
            if non_comment:
                all_empty = False
                break
        if all_empty:
            issues.append({
                "rule": "V3_空SQL占位",
                "level": "error",
                "msg": f"目录 {version_dir or base} 下所有 SQL 文件无实质内容,本版本若无 DDL 变更应不建目录或仅建 00_README.md 说明",
            })

    for f in sql_files:
        # V1 英文通用名
        if ENGLISH_GENERIC_NAMES.match(f.name):
            issues.append({
                "rule": "V1_英文通用名",
                "level": "error",
                "file": f.name,
                "msg": f"严禁 {f.name} 这类英文通用名,必须用 `{{NN}}_{{中文描述}}.sql`",
            })
            continue

        # V4 命名规范
        if not VALID_NAME_PATTERN.match(f.name):
            issues.append({
                "rule": "V4_命名违规",
                "level": "error",
                "file": f.name,
                "msg": f"文件名 {f.name} 不符合 `{{NN}}_{{中文描述}}.sql` 规范",
            })
        # 99_ 固定回滚
        if f.name.startswith("99_") and not ROLLBACK_NAME_PATTERN.match(f.name):
            issues.append({
                "rule": "V4_99_回滚名",
                "level": "error",
                "file": f.name,
                "msg": f"99_ 序号固定保留给回滚脚本,文件名应含「回滚」",
            })

    # V2 基线复制检测
    prev_dir: Optional[Path] = None
    prev_files: List[Path] = []
    if layout == "versioned":
        prev_base: Optional[Path] = None
        if prev_version:
            prev_base = find_base_version_dir(root, prev_version)
            if prev_base is not None and not _has_track(prev_base):
                prev_base = None
        if prev_base is None:
            prev_base = find_prev_version_dir(root, version, layout)
        if prev_base is not None and base is not None and prev_base == base:
            prev_base = None
        prev_files, prev_dir = _prev_baseline_files(prev_base)
    else:
        if prev_version:
            prev_dir = find_version_dir(root, prev_version, layout)
        if prev_dir is None:
            prev_dir = find_prev_version_dir(root, version, layout)
        if prev_dir is not None and prev_dir != version_dir:
            prev_files = list_sql_files(prev_dir, recursive=False)

    if version_dir and prev_dir and prev_dir != version_dir:
        summary["prev_dir"] = str(prev_dir)
        cur_lines = set(collect_sql_lines_from(inc_files))
        prev_lines = set(collect_sql_lines_from(prev_files))
        dup = cur_lines & prev_lines
        # 排除模板/语法噪声行 — 这些在 DDL 中高频复用,出现交集不代表"基线复制"
        # 仅当**业务表/字段定义行**重复才视为基线泄漏
        TEMPLATE_LINE = re.compile(
            r"^\s*("
            r"BEGIN|COMMIT|ROLLBACK"  # 事务控制
            r"|SET\s+\w+\s*=\s*\w+;?"  # SET 配置
            r"|\)\s*ENGINE\s*=.*"  # ENGINE 声明
            r"|.*DEFAULT\s+CHARSET\s*=.*"  # 字符集声明
            r"|.*COLLATE\s*=.*"  # 排序规则
            r"|IF\s+NOT\s+EXISTS\s*"  # 单独 IF NOT EXISTS
            r"|IF\s+EXISTS\s*"
            r"|.*INDEX\s+idx_\w+.*"  # 索引声明(常用名)
            r"|.*KEY\s+(idx|uk|fk|pk)_\w+.*"
            r"|.*PRIMARY\s+KEY.*"
            r"|.*UNIQUE\s+KEY.*"
            r"|--.*"  # 单行注释
            r"|\)\s*;?\s*"  # 结束括号
            r"|\(\s*"  # 起始括号
            r"|;\s*"  # 单分号
            r"|\s*"  # 空行
            r")$",
            re.IGNORECASE,
        )
        dup = {l for l in dup if not TEMPLATE_LINE.match(l)}
        summary["duplicate_lines"] = len(dup)
        # 阈值 5: 模板/语法噪声已在 TEMPLATE_LINE 过滤,剩余的都是业务字段/CREATE TABLE 行
        # 5 行业务字段重复已经足够说明"复制基线",不必等到 10 行
        if len(dup) >= 5:
            sample = sorted(list(dup))[:8]
            issues.append({
                "rule": "V2_基线复制",
                "level": "error",
                "msg": f"本版本({_rel(version_dir, root)})与上一版本({_rel(prev_dir, root)})去模板后重复业务行数 {len(dup)} (≥5),"
                       f"严重违反「SQL 版本严格隔离」铁律。重复样例: {sample[:3]}",
            })

    return issues, summary


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="SQL 版本隔离硬核回检(Module D 子项)")
    ap.add_argument("sql_root", nargs="?",
                    help="SQL 根目录(flat 如 db/migrations/;versioned 为按版本分目录的部署根目录)")
    ap.add_argument("--version", help="当前版本号(如 v1.2.0 / V1.2.0)")
    ap.add_argument("--prev", help="上一版本号(可选,缺省自动推断)")
    ap.add_argument("--layout", choices=LAYOUT_CHOICES, default=None,
                    help="目录布局:auto(缺省,自动识别)/ flat / versioned(two-track 为兼容别名)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-check", action="store_true",
                    help="运行内建夹具的阳性/阴性对照(独立模式)")
    args = ap.parse_args(argv)

    if args.self_check:
        if (args.sql_root is not None or args.json or args.version is not None
                or args.prev is not None or args.layout is not None):
            print("错误: --self-check 不能与 path / --json / --version / --prev / --layout 同时使用",
                  file=sys.stderr)
            return 2
        return run_self_check()
    if args.sql_root is None or not args.version:
        print("错误: 需要 <SQL根目录> 与 --version(或使用 --self-check)", file=sys.stderr)
        return 2
    layout = args.layout or "auto"

    root = Path(args.sql_root)
    # ⚠️ exists() 与 is_dir() 必须分开判:「根目录不存在」是刻意的 N/A 跳过,
    #    「路径存在但是个文件」是手滑传错 —— 合并判会让传错路径静默放行。
    if not root.exists():
        # 仓库可能尚未建立 SQL 目录,这是允许情形
        if args.json:
            print(json.dumps({"passed": True, "skipped": True,
                              "msg": f"SQL 根目录不存在: {root} (未建项目早期允许;跳过不等于通过)"},
                             ensure_ascii=False, indent=2))
        else:
            print(f"⚠️  SQL 根目录不存在,跳过(不等于通过): {root}")
        return 0
    if not root.is_dir():
        print(f"错误: SQL 根目录不是目录: {root}", file=sys.stderr)
        return 2

    try:
        issues, summary = check_version(root, args.version, args.prev, layout)
    except OSError as exc:
        print(f"错误: 读取 SQL 目录失败: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({
            "passed": not any(i["level"] == "error" for i in issues),
            "skipped": False,
            "summary": summary,
            "issues": issues,
        }, ensure_ascii=False, indent=2))
        return 0 if not any(i["level"] == "error" for i in issues) else 1

    failed = [i for i in issues if i["level"] == "error"]
    if not failed:
        print(f"✅ 通过: {summary['version_dir']} (布局 {summary['layout']},{summary['sql_files']} 个 SQL 文件,"
              f"与上一版本重复 {summary['duplicate_lines']} 行)")
        return 0

    print(f"❌ 不通过: {len(failed)} 处违规\n")
    print(f"  布局: {summary['layout']}")
    print(f"  当前版本目录: {summary['version_dir']}")
    if summary.get("prev_dir"):
        print(f"  上一版本目录: {summary['prev_dir']}")
    print()
    for i in failed:
        if "file" in i:
            print(f"  [{i['rule']}] {i['file']}: {i['msg']}")
        else:
            print(f"  [{i['rule']}] {i['msg']}")
    print("\n修复建议: 删除复制的基线 SQL,只保留本版本新增/ALTER;改用中文命名 + NN_ 前缀。")
    return 1


_SELF_CHECK_BODY = "\n".join(
    f"  col_{i} VARCHAR(64) NOT NULL COMMENT '业务字段{i}'," for i in range(8))


def _self_check_cases() -> List[Dict]:
    """内建夹具:每条 = (名称, 文件表, 额外参数, 期望退出码, 期望命中规则, 期望布局)。"""
    order = "CREATE TABLE IF NOT EXISTS biz_order (\n" + _SELF_CHECK_BODY + "\n);\n"
    new_tbl = "CREATE TABLE IF NOT EXISTS biz_coupon (\n  coupon_no VARCHAR(32) NOT NULL COMMENT '券号'\n);\n"
    full = "CREATE TABLE IF NOT EXISTS biz_order (\n" + _SELF_CHECK_BODY + "\n);\n"
    cases: List[Dict] = []

    def add(name, files, args, rc, rule=None, layout=None, skipped=None, absent_rule=None):
        cases.append({"name": name, "files": files, "args": args, "rc": rc, "rule": rule,
                      "layout": layout, "skipped": skipped, "absent_rule": absent_rule})

    # ── flat:{root}/{version}/*.sql ──
    add("flat-复制上一版", {"v1.1.0/01_订单表.sql": order, "v1.2.0/01_订单表.sql": order},
        ["--version", "v1.2.0"], 1, "V2_基线复制", "flat")
    add("flat-干净增量", {"v1.1.0/01_订单表.sql": order, "v1.2.0/01_优惠券表.sql": new_tbl},
        ["--version", "v1.2.0"], 0, None, "flat", absent_rule="V2_基线复制")
    add("flat-大写V前缀", {"V1.1.0/01_订单表.sql": order, "V1.2.0/01_订单表.sql": order},
        ["--version", "v1.2.0"], 1, "V2_基线复制", "flat")
    add("flat-子目录不扫(只扫版本目录当层)",
        {"v1.1.0/01_订单表.sql": order, "v1.2.0/ddl/01_订单表.sql": order},
        ["--version", "v1.2.0"], 0, None, "flat", absent_rule="V2_基线复制")
    add("flat-上一版子目录不参与比对",
        {"v1.1.0/old/01_订单表.sql": order, "v1.2.0/01_订单表.sql": order},
        ["--version", "v1.2.0"], 0, None, "flat", absent_rule="V2_基线复制")
    add("flat-英文通用名", {"v1.2.0/init.sql": new_tbl}, ["--version", "v1.2.0"], 1, "V1_英文通用名", "flat")
    add("flat-命名违规", {"v1.2.0/create_coupon.sql": new_tbl}, ["--version", "v1.2.0"], 1, "V4_命名违规", "flat")
    add("flat-空占位", {"v1.2.0/01_占位.sql": "-- 本版本无变更\n"}, ["--version", "v1.2.0"], 1, "V3_空SQL占位", "flat")
    add("flat-本版无目录", {"v1.1.0/01_订单表.sql": order}, ["--version", "v1.2.0"], 0, None, "flat")
    # ── versioned:{root}/{version}/sql/增量|全量/**/*.sql ──
    add("versioned-复制上一版增量",
        {"V1.1.0/sql/增量/01_订单表.sql": order, "V1.2.0/sql/增量/01_订单表.sql": order},
        ["--version", "V1.2.0"], 1, "V2_基线复制", "versioned")
    add("versioned-小写v前缀",
        {"v1.1.0/sql/增量/01_订单表.sql": order, "v1.2.0/sql/增量/01_订单表.sql": order},
        ["--version", "V1.2.0"], 1, "V2_基线复制", "versioned")
    add("versioned-全量轨重复不算复制",
        {"V1.1.0/sql/全量/01_全量建表.sql": full, "V1.1.0/sql/增量/01_订单表.sql": order,
         "V1.2.0/sql/全量/01_全量建表.sql": full, "V1.2.0/sql/增量/01_优惠券表.sql": new_tbl},
        ["--version", "V1.2.0"], 0, None, "versioned", absent_rule="V2_基线复制")
    add("versioned-全量轨也校命名",
        {"V1.2.0/sql/增量/01_优惠券表.sql": new_tbl, "V1.2.0/sql/全量/init.sql": full},
        ["--version", "V1.2.0"], 1, "V1_英文通用名", "versioned")
    add("versioned-两轨之外init.sql",
        {"V1.2.0/sql/增量/01_优惠券表.sql": new_tbl, "V1.2.0/init.sql": new_tbl},
        ["--version", "V1.2.0"], 1, "V1_英文通用名", "versioned")
    add("versioned-两轨之外sql/schema.sql判V5",
        {"V1.2.0/sql/增量/01_优惠券表.sql": new_tbl, "V1.2.0/sql/schema.sql": new_tbl},
        ["--version", "V1.2.0"], 1, "V5_两轨之外有SQL", "versioned")
    add("versioned-无增量轨仅全量+两轨之外SQL也要查",
        {"V1.2.0/sql/全量/01_全量建表.sql": full, "V1.2.0/sql/01_优惠券表.sql": new_tbl},
        ["--version", "V1.2.0"], 1, "V5_两轨之外有SQL", "versioned")
    add("versioned-上一版只有全量-本版增量照抄",
        {"V1.1.0/sql/全量/01_全量建表.sql": full, "V1.2.0/sql/增量/01_订单表.sql": order},
        ["--version", "V1.2.0"], 1, "V2_基线复制", "versioned")
    add("versioned-上一版只有全量-本版干净增量",
        {"V1.1.0/sql/全量/01_全量建表.sql": full, "V1.2.0/sql/增量/01_优惠券表.sql": new_tbl},
        ["--version", "V1.2.0"], 0, None, "versioned", absent_rule="V2_基线复制")
    add("versioned-显式--prev",
        {"V1.0.0/sql/增量/01_订单表.sql": order, "V1.1.0/sql/增量/01_优惠券表.sql": new_tbl,
         "V1.2.0/sql/增量/01_订单表.sql": order},
        ["--version", "V1.2.0", "--prev", "v1.0.0"], 1, "V2_基线复制", "versioned")
    add("versioned-two-track别名",
        {"V1.1.0/sql/增量/01_订单表.sql": order, "V1.2.0/sql/增量/01_订单表.sql": order},
        ["--version", "V1.2.0", "--layout", "two-track"], 1, "V2_基线复制", "versioned")
    # ── 显式 --layout 覆盖自动识别 ──
    add("显式flat-不递归-双轨子目录不扫",
        {"V1.1.0/sql/增量/01_订单表.sql": order, "V1.2.0/sql/增量/01_订单表.sql": order},
        ["--version", "V1.2.0", "--layout", "flat"], 0, None, "flat", absent_rule="V2_基线复制")
    add("显式versioned-扁平目录的SQL判两轨之外(不比V2)",
        {"v1.1.0/01_订单表.sql": order, "v1.2.0/01_订单表.sql": order},
        ["--version", "v1.2.0", "--layout", "versioned"], 1, "V5_两轨之外有SQL", "versioned",
        absent_rule="V2_基线复制")
    # ── 退出码约定 ──
    add("根目录不存在-N/A", None, ["--version", "v1.2.0"], 0, skipped=True)
    add("根路径是文件-入参错", "FILE", ["--version", "v1.2.0"], 2)
    return cases


def run_self_check() -> int:
    """端到端回归:内建夹具逐条以子进程 `--json` 跑一遍,比对退出码 / 命中规则 / 布局 / skipped。"""
    failures: List[str] = []
    cases = _self_check_cases()
    try:
        with tempfile.TemporaryDirectory(prefix="sql-isolation-selfcheck-") as td:
            tmp = Path(td)
            for idx, case in enumerate(cases):
                root = tmp / f"case{idx:02d}"
                if case["files"] is None:
                    target = root / "不存在"
                elif case["files"] == "FILE":
                    root.mkdir()
                    target = root / "x.sql"
                    target.write_text("SELECT 1;\n", encoding="utf-8")
                else:
                    target = root
                    for rel, content in case["files"].items():
                        fp = root / rel
                        fp.parent.mkdir(parents=True, exist_ok=True)
                        fp.write_text(content, encoding="utf-8")
                proc = subprocess.run(
                    [sys.executable, str(Path(__file__).resolve()), str(target), *case["args"], "--json"],
                    text=True, capture_output=True, check=False, timeout=30)
                ok = proc.returncode == case["rc"]
                payload: Dict = {}
                if case["rc"] != 2:
                    try:
                        payload = json.loads(proc.stdout)
                    except json.JSONDecodeError:
                        failures.append(f"{case['name']}: stdout 非 JSON: {proc.stdout!r} {proc.stderr!r}")
                        print(f"SELF-CHECK {case['name']}: FAIL")
                        continue
                rules = {i["rule"] for i in payload.get("issues", [])}
                if case["rule"] is not None:
                    ok = ok and case["rule"] in rules
                if case["absent_rule"] is not None:
                    ok = ok and case["absent_rule"] not in rules
                if case["layout"] is not None:
                    ok = ok and payload.get("summary", {}).get("layout") == case["layout"]
                if case["skipped"] is not None:
                    ok = ok and payload.get("skipped") is case["skipped"]
                print(f"SELF-CHECK {case['name']}: {'PASS' if ok else 'FAIL'}")
                if not ok:
                    failures.append(f"{case['name']}: rc={proc.returncode}, rules={sorted(rules)}, "
                                    f"payload={payload}, stderr={proc.stderr.strip()!r}")
    except OSError as exc:
        print(f"SELF-CHECK 环境错误: {exc}", file=sys.stderr)
        return 2
    except subprocess.TimeoutExpired as exc:
        # 子进程超时是环境问题(机器负载/被挂起),不是产物违规 → 归入参/环境错档
        print(f"SELF-CHECK 超时失败: {exc}", file=sys.stderr)
        return 2
    if failures:
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1
    print(f"SELF-CHECK 通过: {len(cases)}/{len(cases)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
