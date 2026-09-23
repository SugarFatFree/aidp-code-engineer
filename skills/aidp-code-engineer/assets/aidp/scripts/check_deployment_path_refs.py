#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_deployment_path_refs.py — 文档里的部署产物路径必须写成约定 37 两轨结构（脚手架契约脚本）。

## 为什么需要本脚本

约定 37 把部署基线拆成对称同级的两轨：

    docs/deployment/{version}/sql/增量/          ← 已有环境怎么升级
    docs/deployment/{version}/sql/全量/          ← 从零怎么搭
    docs/deployment/{version}/配置文件/增量/配置项清单.md
    docs/deployment/{version}/配置文件/全量/     ← nginx.conf / docker-compose / k8s-* 等完整文件

**根下不得再直放两轨产物**，且**不设双读兼容**——留在旧位置的文件会被新 glob 漏掉 = 静默丢产物。
文件系统侧已有机器门 `verify.py::check_deployment_two_track_layout`，但它**只查文件、查不到文档**。
而真正长期漂移的恰恰是文档：命令/flow/README/memory 里写着 `docs/deployment/{version}/sql/init.sql`
这类**旧结构路径**，执行体照着它 `mkdir` / 写文件 —— 于是"文件系统检查过了、下一次又被文档带回旧结构"。
一次审计在 8 份文档里查出旧写法。**本脚本 = 那道机器门的文档版**，与它同源同判据。

## 判定口径（与 verify.py::check_deployment_two_track_layout 同源）

扫全仓 `.md`（默认排除 `AIDP_HOME/skills/`：SKILL 本体 + 脚手架 bundle 镜像，本体改完由
`mirror_to_bundle.py` 单向同步，重复报只产生双份噪音），对每一处 `docs/deployment/<版本>/` 路径：

1. `…/sql/` 之后的**下一个路径段**不是 `增量` / `全量` → 违规
   （典型：`…/sql/init.sql`、`…/sql/*.sql`、`…/sql/sprint-001.sql`）；
2. `…/配置文件/` 之后**直接**接 `配置项清单*.md` / `*.conf` / `docker-compose*` / `k8s-*` → 违规
   （前者属增量轨 → `配置文件/增量/`；后三者是完整文件 = 全量轨 → `配置文件/全量/`，见约定 37.2）。

`<版本>` 段同时认：占位符 `{version}` / `{V}` / `<version>`、真实版本号 `V1.2.3`、通配 `*`。

**只在"后面还接着东西"时才判**：`docs/deployment/{version}/sql/` 后面什么都没有（行尾 / 反引号 /
表格竖线 / 中文标点）= 指两轨的**父目录本身**，那是约定 37 正文自己的合法写法，不报。
配置文件侧同理，且**只认上面四种旧结构文件名**——宁可少报，不为多抓一个而制造误报噪音。

## 豁免（显式标记，不硬编码文件名）

文档里存在**合法的旧结构写法**：搬迁映射表的"旧位置"列、讲"从哪儿搬到哪儿"的段落、
历史版本变更记录。这类必须豁免，但**只认写在文件里的显式标记**——绝不在脚本里写死文件名白名单
（硬编码的豁免会随文件改名/拆分静默失效，而且下一个人根本不知道某文件为什么被放过）：

    <!-- deploypath-check: ignore -->              该行豁免（写在同一行，行尾即可）
    <!-- deploypath-check: ignore-file 理由 -->     整份文件豁免
    <!-- deploypath-check: ignore-begin 理由 -->    区块开始
    ...
    <!-- deploypath-check: ignore-end -->          区块结束

## 用法

    python3 AIDP_HOME/scripts/check_deployment_path_refs.py            # 人读报告
    python3 AIDP_HOME/scripts/check_deployment_path_refs.py --json     # 机读 JSON
    python3 AIDP_HOME/scripts/check_deployment_path_refs.py --root . --path AIDP_HOME/flows

级别 **ERROR**（同 `verify.py` 那道文件系统门：旧结构 = 静默丢产物，不是风格问题）。
退出码：0 = 全部两轨写法；1 = 检出旧结构写法；2 = 用法/读取错误。
"""
import argparse
import json
import os
import re
import sys

# 默认扫全仓；这些目录不下钻（SKILL 本体 / 依赖 / 产物）
EXCLUDE_DIRS = {
    ".git", "node_modules", "__pycache__", "dist", "build", ".venv",
    "skills",  # `AIDP_HOME/skills/`：SKILL 本体 + 脚手架 bundle 镜像，由 mirror 脚本同步
}
# ★ 前缀式排除：`.aidp-backup-<时间戳>` 目录名带时间戳，永远命中不了上面的精确名集合。
#   备份是冻结的历史副本（按定义就装着旧结构），不排除会让每个做过 upgrade 的下游恒红。
EXCLUDE_DIR_PREFIXES = (".aidp-backup",)

# 两轨目录名（约定 37）
TRACKS = ("增量", "全量")

# 版本段：占位符 `{version}`/`{V}`/`{prev-version}`、尖括号 `<version>`、真实号 `V1.2.3`、通配 `*`
VER = r"(?:\{[^}/\s]+\}|<[^>/\s]+>|[Vv]\d+(?:\.\d+)*[\w.-]*|\*)"
SQL_RE = re.compile(r"docs/deployment/" + VER + r"/sql/")
CFG_RE = re.compile(r"docs/deployment/" + VER + r"/配置文件/")
# 路径段终止符：空白、反引号、表格竖线、引号、括号、中文标点
SEG_RE = re.compile(r"[^/\s`|\"'，。、；：）（【】]+")
# 配置文件根下的旧结构文件名（与 verify.py 的 glob 清单一一对应）
STALE_CFG_RE = re.compile(
    r"^(?:配置项清单[^/\s]*\.md"          # 增量轨 → 配置文件/增量/
    r"|[^/\s]*\.conf"                      # nginx.conf 等完整文件 → 配置文件/全量/
    r"|docker-compose[^/\s]*"
    r"|k8s-[^/\s]*)"
)

IGNORE_LINE_RE = re.compile(r"<!--\s*deploypath-check:\s*ignore\s*(?:-->|\s)")
IGNORE_FILE_RE = re.compile(r"<!--\s*deploypath-check:\s*ignore-file")
IGNORE_BEGIN_RE = re.compile(r"<!--\s*deploypath-check:\s*ignore-begin")
IGNORE_END_RE = re.compile(r"<!--\s*deploypath-check:\s*ignore-end")


def iter_md(root, paths=None):
    """遍历待检 `.md`：给了 --path 就只扫它，否则全仓（跳 EXCLUDE_DIRS）。"""
    if paths:
        for rel in paths:
            p = os.path.join(root, rel)
            if os.path.isfile(p) and p.endswith(".md"):
                yield p
            elif os.path.isdir(p):
                for x in _walk(p):
                    yield x
    else:
        for x in _walk(root):
            yield x


def _walk(base):
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames
                       if d not in EXCLUDE_DIRS and not d.startswith(EXCLUDE_DIR_PREFIXES)]
        for fn in sorted(filenames):
            if fn.endswith(".md"):
                yield os.path.join(dirpath, fn)


def scan_line(line):
    """返回本行的旧结构写法列表 [(片段, 列号, 提示)]。"""
    bad = []
    for m in SQL_RE.finditer(line):
        seg = SEG_RE.match(line, m.end())
        if seg is None:                    # 后面没东西 = 指两轨父目录本身，合法
            continue
        if seg.group(0) in TRACKS:         # …/sql/增量… / …/sql/全量… = 新结构
            continue
        bad.append((line[m.start():seg.end()], m.start() + 1,
                    "约定 37 两轨：SQL 产物应落 sql/增量/（升级脚本）或 sql/全量/（从零搭建），不得直放 sql/ 根"))
    for m in CFG_RE.finditer(line):
        rest = line[m.end():]
        seg = SEG_RE.match(rest)
        if seg is None or seg.group(0) in TRACKS:
            continue
        if not STALE_CFG_RE.match(rest):   # 只认四种旧结构文件名，其余不猜
            continue
        bad.append((line[m.start():m.end()] + seg.group(0), m.start() + 1,
                    "约定 37 两轨：配置项清单 → 配置文件/增量/；nginx/compose/k8s 完整文件 → 配置文件/全量/"))
    return bad


def run(root, paths=None):
    violations, scanned, total_hits = [], 0, 0
    read_errors = []
    for path in sorted(set(iter_md(root, paths))):
        rel = os.path.relpath(path, root)
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except (OSError, UnicodeDecodeError) as e:
            # ⛔ 读取失败**不算 violation**：本检查已被接成 verify 的 ERROR，任何瞬时文件消失
            #    （并发会话临时装/删可选规则、编辑器换盘）都会变成硬 ERROR、把干净仓库判红。
            #    真读不出的文件计入 read_errors 供人排查，不参与判定。
            read_errors.append({"file": rel, "detail": f"读取失败：{e}"})
            continue
        if IGNORE_FILE_RE.search(text):
            continue
        scanned += 1
        in_ignore = False
        for i, line in enumerate(text.split("\n"), 1):
            if IGNORE_BEGIN_RE.search(line):
                in_ignore = True
            elif IGNORE_END_RE.search(line):
                in_ignore = False
            if in_ignore or IGNORE_LINE_RE.search(line):
                continue
            total_hits += len(SQL_RE.findall(line)) + len(CFG_RE.findall(line))
            for snippet, col, detail in scan_line(line):
                violations.append({"file": rel, "line": i, "col": col,
                                   "snippet": snippet[:120], "detail": detail})
    return {"scanned": scanned, "deployment_path_refs": total_hits, "violations": violations, "read_errors": read_errors}


def main():
    ap = argparse.ArgumentParser(
        description="文档里的 docs/deployment/{version}/ 路径必须写成约定 37 两轨结构")
    ap.add_argument("--root", default=".", help="仓库根目录（默认当前目录）")
    ap.add_argument("--path", action="append", default=None,
                    help="只扫指定相对路径（可重复）；缺省扫全仓 .md")
    ap.add_argument("--json", action="store_true", help="机读 JSON")
    ap.add_argument("--self-check", action="store_true",
                    help="阳性对照自检：注入必然命中的探针，验证本检查确实生效"
                         "（骨架与探针登记表见 selfcheck.py）")
    args = ap.parse_args()
    if args.self_check:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from selfcheck import run_self_check
        sys.exit(run_self_check(os.path.basename(__file__),
                                json_out=getattr(args, "json", False)))

    try:
        res = run(args.root, args.path)
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False) if args.json
              else f"[ERROR] 检查执行失败：{e}")
        return 2

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    elif not res["violations"]:
        print(f"[OK] 部署路径引用全部为约定 37 两轨写法"
              f"（巡检 {res['scanned']} 份 .md，命中 {res['deployment_path_refs']} 处部署路径）")
    else:
        print(f"[FAIL] 检出 {len(res['violations'])} 处旧结构部署路径写法"
              f"（巡检 {res['scanned']} 份 .md，命中 {res['deployment_path_refs']} 处部署路径）：")
        for v in res["violations"]:
            print(f"  · {v['file']}:{v['line']}:{v['col']}  {v['snippet']}")
            print(f"      {v['detail']}")
        print("  修复：把路径改写为 sql/{增量,全量}/ 与 配置文件/{增量,全量}/；"
              "确属「搬迁映射表的旧位置列 / 讲历史结构」→ 加 `<!-- deploypath-check: ignore -->` 豁免。")
    return 1 if res["violations"] else 0


if __name__ == "__main__":
    sys.exit(main())
