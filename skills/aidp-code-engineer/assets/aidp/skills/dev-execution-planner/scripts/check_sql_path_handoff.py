#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SQL 路径透传核验 — dev-execution-planner 维度 9 子项

校验研发执行计划中 Task 引用的 SQL 路径格式是否与详细设计 Module D 规定的
`{SQL脚本目录}/v{版本号}/{NN}_{中文描述}.sql` 命名规范一致。

检测项:
  P1  英文通用名禁止 — 严禁 init.sql / schema.sql / migration.sql / baseline.sql 等
  P2  版本子目录约束 — 路径必须含 v{version} 子目录
  P3  中文命名 + NN_ 序号 — 文件名必须 `{NN}_{中文描述}.sql`
  P4  版本号一致 — 同一研发执行计划文件内,所有 SQL 引用的版本号应一致(允许 1 个版本)
  P5  回滚脚本配套 — 若任一 SQL 为 99_*.sql,文件名必须含「回滚」

使用:
  python check_sql_path_handoff.py <研发执行计划路径>
  python check_sql_path_handoff.py <研发执行计划路径> --json
  python check_sql_path_handoff.py <研发执行计划路径> --strict   # 必须存在 SQL 引用

退出码: 0 = 通过(或无 SQL 引用) / 1 = 不通过 / 2 = 环境错(路径不存在 / 无 markdown 文件 /
        **有 .md 读取失败**——读不出来的文件记进 `--json` 的 `read_errors[]` 并按 2 返回,
        ⛔ 绝不静默计为「该文件无违规」(修:此前是裸 read_text,断链符号链接会抛
        FileNotFoundError 裸 traceback 且 exit 1,与「检出违规」撞码)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Set

# 抓取所有 SQL 路径引用 — 支持反引号包裹、markdown 链接、纯文本
SQL_PATH_RE = re.compile(
    r"`?([^\s`<>()\[\]]*?\.sql)`?",
    re.IGNORECASE,
)
# 版本号目录 v{N.N.N} 或 v{N}
VERSION_DIR_RE = re.compile(r"/v(\d+(?:\.\d+){0,2})/", re.IGNORECASE)
# 文件名 NN_中文.sql
VALID_FILENAME_RE = re.compile(r"^\d{2}_[一-鿿].*\.sql$")
# 英文通用名黑名单
ENGLISH_GENERIC_NAMES = re.compile(
    r"^(init|schema|migration|baseline|database|all|full|setup|main|create_all)\.sql$",
    re.IGNORECASE,
)
# 99_ 回滚命名
ROLLBACK_RE = re.compile(r"^99_.*回滚.*\.sql$")


def collect_sql_refs(text: str) -> List[str]:
    """从 markdown 抓取所有 .sql 路径引用,去重"""
    refs: Set[str] = set()
    for m in SQL_PATH_RE.finditer(text):
        path = m.group(1).strip()
        # 过滤明显不是路径的(如 example.sql 占位符仅适合在示例)
        if not path:
            continue
        # 排除占位符 {SQL脚本目录} 中含义不明的
        if "{" in path or "}" in path:
            continue
        # 排除尖括号占位符 <...>(如 <ddl文件.sql> / <DDL文件路径>.sql):捕获组紧跟在 '<' 之后
        start = m.start(1)
        if start > 0 and text[start - 1] == "<":
            continue
        # 排除仅捕到扩展名的残片(如 <DDL路径>.sql 被 '>' 截断后只剩 '.sql')
        if not path[:-4].strip("/").strip():
            continue
        refs.add(path)
    return sorted(refs)


def analyze(text: str) -> Dict:
    refs = collect_sql_refs(text)
    issues: List[Dict] = []
    versions: Set[str] = set()

    if not refs:
        return {"refs": [], "issues": [], "versions": []}

    for ref in refs:
        filename = ref.rsplit("/", 1)[-1]

        # P1 英文通用名
        if ENGLISH_GENERIC_NAMES.match(filename):
            issues.append({
                "rule": "P1_英文通用名",
                "file": ref,
                "msg": f"严禁 {filename} 这类英文通用名,必须用 `{{NN}}_{{中文描述}}.sql`",
                "level": "error",
            })
            continue

        # P3 中文命名 + NN_ 序号
        if not VALID_FILENAME_RE.match(filename):
            issues.append({
                "rule": "P3_命名违规",
                "file": ref,
                "msg": f"文件名 {filename} 不符合 `{{NN}}_{{中文描述}}.sql` 规范",
                "level": "error",
            })

        # P5 99_ 回滚配套
        if filename.startswith("99_") and not ROLLBACK_RE.match(filename):
            issues.append({
                "rule": "P5_99回滚名",
                "file": ref,
                "msg": f"99_ 序号固定保留给回滚脚本,文件名应含「回滚」",
                "level": "error",
            })

        # P2 版本子目录
        ver_match = VERSION_DIR_RE.search(ref)
        if ver_match:
            versions.add(ver_match.group(1))
        else:
            # 不强制(占位符示例可能省略路径前缀);仅警告
            issues.append({
                "rule": "P2_版本子目录",
                "file": ref,
                "msg": f"路径 {ref} 缺 `/v{{版本号}}/` 子目录,违反 Module D 版本隔离原则",
                "level": "warn",
            })

    # P4 版本号一致
    if len(versions) > 1:
        issues.append({
            "rule": "P4_版本号不一致",
            "file": "(全局)",
            "msg": f"研发执行计划内出现多个版本号: {sorted(versions)};Module D 规定本迭代只对应单一版本",
            "level": "error",
        })

    return {"refs": refs, "issues": issues, "versions": sorted(versions)}


def main() -> int:
    ap = argparse.ArgumentParser(description="SQL 路径透传核验(对接 Module D)")
    ap.add_argument("path", help="研发执行计划文件或目录")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true",
                    help="研发执行计划必须含至少 1 个 SQL 引用,否则不通过")
    args = ap.parse_args()

    target = Path(args.path)
    if not target.exists():
        print(f"❌ 路径不存在: {target}", file=sys.stderr)
        return 2

    md_files = [target] if target.is_file() else sorted(target.rglob("*.md"))
    if not md_files:
        print(f"⚠️  未发现 markdown 文件: {target}", file=sys.stderr)
        return 2

    aggregated = {"files": [], "total_refs": 0, "total_issues": 0,
                  "passed": True, "read_errors": []}
    for f in md_files:
        # ⚠️ 读不出来的文件(断链符号链接 / 无读权限)必须记成 read_error 并按 exit 2
        # 返回,⛔ 绝不可静默计为「该文件无违规」。
        # 此前这里是裸 `f.read_text(...)`:一个断链的 `01_研发执行计划.md` 会让脚本抛
        # FileNotFoundError 裸 traceback 且 **exit 1** —— 而 exit 1 按全仓退出码约定是
        # 「检出违规」,QR 子 Agent 会读成「维度 9 详细设计一致性不通过」,产物方怎么改
        # 都修不好(实测复现:ln -s /nonexistent/x.md 01_研发执行计划.md → exit 1 + traceback)。
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            aggregated["read_errors"].append({"file": str(f), "error": str(exc)})
            print(f"❌ 文件读取失败: {f} ({exc})", file=sys.stderr)
            continue
        result = analyze(text)
        result["file"] = str(f)
        aggregated["files"].append(result)
        aggregated["total_refs"] += len(result["refs"])
        errors = [i for i in result["issues"] if i["level"] == "error"]
        if errors:
            aggregated["passed"] = False
            aggregated["total_issues"] += len(errors)

    if args.strict and aggregated["total_refs"] == 0:
        aggregated["passed"] = False
        aggregated["strict_violation"] = "无 SQL 引用,但 --strict 要求必须有"

    if args.json:
        print(json.dumps(aggregated, ensure_ascii=False, indent=2))
        if aggregated["read_errors"]:
            return 2  # 环境错:有文件没读到,本次结论不完整
        return 0 if aggregated["passed"] else 1

    if aggregated["read_errors"]:
        # 文本模式同样按 exit 2 返回:结论不完整,⛔ 不得当成通过
        print(f"❌ {len(aggregated['read_errors'])} 个文件读取失败,本次结论不完整:")
        for e in aggregated["read_errors"]:
            print(f"    {e['file']}: {e['error']}")
        return 2

    if aggregated["total_refs"] == 0:
        if args.strict:
            print("❌ --strict 模式:未发现任何 .sql 引用")
            return 1
        print("⚠️  无 SQL 引用,跳过(本迭代可能无 DDL 变更)")
        return 0

    if aggregated["passed"]:
        all_versions = sorted({v for r in aggregated["files"] for v in r["versions"]})
        print(f"✅ 通过: 扫描 {len(md_files)} 个文件,{aggregated['total_refs']} 处 SQL 引用,版本: {all_versions}")
        # ⚠️ **warn 必须在文本模式也打出来**:QR 派发的必跑命令不带 `--json`,而子 Agent 被要求
        #    「把报告正文原样贴进报告」。早期 warn 只进 `--json`,于是「路径缺 /v{版本号}/ 子目录」
        #    这条 Module D 版本隔离铁律的违规,在正文里只显示一句 ✅ —— 违规被 ✅ 吞掉。
        warns = [(r["file"], i) for r in aggregated["files"]
                 for i in r["issues"] if i["level"] == "warn"]
        if warns:
            print(f"\n🟡 Important 告警 {len(warns)} 处(不影响退出码,**须人工确认后并入维度判定**):")
            for f, i in warns:
                print(f"    [{i['rule']}] {i.get('file', f)}: {i['msg']}")
        return 0

    print(f"❌ 不通过: {aggregated['total_issues']} 处错误\n")
    for r in aggregated["files"]:
        errs = [i for i in r["issues"] if i["level"] == "error"]
        if not errs:
            continue
        print(f"  {r['file']}:")
        for i in errs:
            print(f"    [{i['rule']}] {i['file']}: {i['msg']}")
    print("\n修复建议: 改用 `{SQL脚本目录}/v{版本号}/{NN}_{中文描述}.sql` 命名;"
          "对接 dev-logic-architect Module D 规范。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
