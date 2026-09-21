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

两种目录布局(--layout,缺省 auto 自动识别):
  flat       {SQL根目录}/{version}/*.sql
  two-track  {部署根目录}/{version}/sql/增量/**/*.sql + sql/全量/**/*.sql(AIDP 约定 37 双轨)
             V1/V3/V4 两轨都校;V2 只比较本版与上一版的「增量」轨(全量轨按定义就是整库快照)
  auto       {根}/{version}/sql/增量 或 sql/全量 存在 → two-track,否则 flat
  两种布局下都递归扫描子目录。

使用:
  python check_sql_version_isolation.py <SQL根目录> --version <当前版本号>
  python check_sql_version_isolation.py docs/deployment --version V1.2.0 --layout two-track
  python check_sql_version_isolation.py <根目录> --version v1.2.0 --prev v1.1.0 --json
  python check_sql_version_isolation.py --self-check      # 阳性对照:植入违规 → 必须被抓到

退出码: 0 通过 / 1 不通过 / 2 用法错误
"""

from __future__ import annotations

import argparse
import json
import re
import sys
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


TWO_TRACK_INC = ("sql", "增量")
TWO_TRACK_FULL = ("sql", "全量")


def list_sql_files(d: Optional[Path]) -> List[Path]:
    """递归列出目录下全部 .sql(两种布局都允许按子目录组织)。"""
    if d is None or not d.is_dir():
        return []
    return sorted(p for p in d.rglob("*.sql") if p.is_file())


def collect_sql_lines(version_dir: Path) -> List[str]:
    lines: List[str] = []
    for sql in list_sql_files(version_dir):
        try:
            for raw in sql.read_text(encoding="utf-8", errors="replace").splitlines():
                norm = normalize_sql_line(raw)
                if norm and len(norm) >= 10:  # 过滤掉过短行(单括号、单分号等)
                    lines.append(norm)
        except Exception:
            continue
    return lines


def detect_layout(root: Path, version: str) -> str:
    vd = find_version_dir(root, version, "flat")
    if vd is not None and ((vd.joinpath(*TWO_TRACK_INC)).is_dir() or (vd.joinpath(*TWO_TRACK_FULL)).is_dir()):
        return "two-track"
    return "flat"


def find_version_dir(root: Path, version: str, layout: str = "flat") -> Optional[Path]:
    """flat 返回 {root}/{version};two-track 返回 {root}/{version}/sql/增量(不存在返回 None)。"""
    if layout == "two-track":
        base = find_version_dir(root, version, "flat")
        if base is None:
            return None
        inc = base.joinpath(*TWO_TRACK_INC)
        return inc if inc.is_dir() else None
    candidate = root / version
    if candidate.is_dir():
        return candidate
    # 兼容 v1.2.0 / 1.2.0
    if version.startswith("v"):
        alt = root / version[1:]
    else:
        alt = root / f"v{version}"
    if alt.is_dir():
        return alt
    return None


def _version_key(name: str) -> tuple:
    """把版本目录名解析为数字元组用于比较(避免字典序把 1.10 误判为早于 1.2)。"""
    return tuple(int(x) for x in re.findall(r"\d+", name.lstrip("v")))


def find_prev_version_dir(root: Path, current_version: str, layout: str = "flat") -> Optional[Path]:
    """启发式查找上一版本目录: 同目录下数字版本号紧邻 current 之前的 v* 目录
    (two-track 只认带 sql/增量 的版本目录,返回其增量轨目录)"""
    versions = sorted(
        [d for d in root.iterdir() if d.is_dir() and re.match(r"^[vV]?\d+\.\d+", d.name)
         and (layout != "two-track" or d.joinpath(*TWO_TRACK_INC).is_dir())],
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
    if prev is not None and layout == "two-track":
        return prev.joinpath(*TWO_TRACK_INC)
    return prev


def check_version(root: Path, version: str, prev_version: Optional[str],
                  layout: str = "auto") -> Tuple[List[Dict], Dict]:
    issues: List[Dict] = []
    if layout == "auto":
        layout = detect_layout(root, version)
    summary: Dict = {"version": version, "layout": layout, "version_dir": None, "sql_files": 0,
                     "prev_dir": None, "duplicate_lines": 0}

    version_dir = find_version_dir(root, version, layout)
    extra_files: List[Path] = []
    if layout == "two-track":
        base = find_version_dir(root, version, "flat")
        if base is not None:
            extra_files = list_sql_files(base.joinpath(*TWO_TRACK_FULL))
    if version_dir is None and not extra_files:
        # V3: 无目录是合法的(本版本无 DDL 变更)
        summary["version_dir"] = "(不存在,视为本版本无 DDL 变更)"
        return issues, summary

    summary["version_dir"] = str(version_dir) if version_dir else "(无增量轨)"

    inc_files = list_sql_files(version_dir)
    sql_files = inc_files + extra_files
    summary["sql_files"] = len(sql_files)

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
                "msg": f"版本 {version} 下所有 SQL 文件无实质内容,本版本若无 DDL 变更应不建目录或仅建 00_README.md 说明",
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
    if prev_version:
        prev_dir = find_version_dir(root, prev_version, layout)
    if prev_dir is None:
        prev_dir = find_prev_version_dir(root, version, layout)

    if version_dir and prev_dir and prev_dir != version_dir:
        summary["prev_dir"] = str(prev_dir)
        cur_lines = set(collect_sql_lines(version_dir))
        prev_lines = set(collect_sql_lines(prev_dir))
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
                "msg": f"本版本({version_dir})与上一版本({prev_dir})去模板后重复业务行数 {len(dup)} (≥5),"
                       f"严重违反「SQL 版本严格隔离」铁律。重复样例: {sample[:3]}",
            })

    return issues, summary


def main() -> int:
    ap = argparse.ArgumentParser(description="SQL 版本隔离硬核回检(Module D 子项)")
    ap.add_argument("sql_root", nargs="?", help="SQL 根目录(flat 如 db/migrations/;two-track 为 docs/deployment)")
    ap.add_argument("--version", help="当前版本号(如 v1.2.0)")
    ap.add_argument("--prev", help="上一版本号(可选,缺省自动推断)")
    ap.add_argument("--layout", choices=["auto", "flat", "two-track"], default="auto",
                    help="目录布局(缺省 auto 自动识别)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-check", action="store_true", help="阳性对照自检")
    args = ap.parse_args()
    if args.self_check:
        return self_check()
    if not args.sql_root or not args.version:
        ap.error("需要 <sql_root> 与 --version(或使用 --self-check)")

    root = Path(args.sql_root)
    if not root.is_dir():
        # 仓库可能尚未建立 SQL 目录,这是允许情形
        if args.json:
            print(json.dumps({"passed": True, "skipped": True,
                              "msg": f"SQL 根目录不存在: {root} (未建项目早期允许)"},
                             ensure_ascii=False, indent=2))
        else:
            print(f"⚠️  SQL 根目录不存在,跳过: {root}")
        return 0

    issues, summary = check_version(root, args.version, args.prev, args.layout)

    if args.json:
        print(json.dumps({
            "passed": not any(i["level"] == "error" for i in issues),
            "summary": summary,
            "issues": issues,
        }, ensure_ascii=False, indent=2))
        return 0 if not any(i["level"] == "error" for i in issues) else 1

    failed = [i for i in issues if i["level"] == "error"]
    if not failed:
        print(f"✅ 通过: {summary['version_dir']} ({summary['sql_files']} 个 SQL 文件,"
              f"与上一版本重复 {summary['duplicate_lines']} 行)")
        return 0

    print(f"❌ 不通过: {len(failed)} 处违规\n")
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


def self_check() -> int:
    """阳性对照:两种布局各植入一次基线复制 + 英文通用名,必须被抓到;干净样本必须通过。"""
    import tempfile
    body = "\n".join(f"  col_{i} VARCHAR(64) NOT NULL COMMENT '业务字段{i}'," for i in range(8))
    ok = True
    with tempfile.TemporaryDirectory() as t:
        tp = Path(t)
        # two-track:V1.1.0 增量 与 V1.2.0 增量 复制
        for v in ("V1.1.0", "V1.2.0"):
            inc = tp / "deploy" / v / "sql" / "增量" / "子目录"
            inc.mkdir(parents=True)
            (inc / "01_订单表.sql").write_text("CREATE TABLE t_order (\n" + body + "\n);\n", encoding="utf-8")
        full = tp / "deploy" / "V1.2.0" / "sql" / "全量"
        full.mkdir(parents=True)
        (full / "init.sql").write_text("CREATE TABLE t_x (id BIGINT NOT NULL PRIMARY KEY);\n", encoding="utf-8")
        iss, summ = check_version(tp / "deploy", "V1.2.0", None)
        rules = {i["rule"] for i in iss}
        if summ["layout"] != "two-track" or "V2_基线复制" not in rules or "V1_英文通用名" not in rules:
            print(f"[self-check] FAIL two-track 未抓到植入违规: layout={summ['layout']} rules={rules}")
            ok = False
        # 干净 two-track:本版只有新增
        clean = tp / "clean" / "V1.2.0" / "sql" / "增量"
        clean.mkdir(parents=True)
        (clean / "01_新增表.sql").write_text("CREATE TABLE t_new (id BIGINT NOT NULL PRIMARY KEY);\n", encoding="utf-8")
        iss, _ = check_version(tp / "clean", "V1.2.0", None)
        if iss:
            print(f"[self-check] FAIL 干净样本被误报: {iss}")
            ok = False
        # flat
        for v in ("v1.1.0", "v1.2.0"):
            d = tp / "flat" / v
            d.mkdir(parents=True)
            (d / "01_订单表.sql").write_text("CREATE TABLE t_order (\n" + body + "\n);\n", encoding="utf-8")
        iss, summ = check_version(tp / "flat", "v1.2.0", None)
        if summ["layout"] != "flat" or "V2_基线复制" not in {i["rule"] for i in iss}:
            print(f"[self-check] FAIL flat 未抓到基线复制: {iss}")
            ok = False
    print("[self-check] OK" if ok else "[self-check] FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
