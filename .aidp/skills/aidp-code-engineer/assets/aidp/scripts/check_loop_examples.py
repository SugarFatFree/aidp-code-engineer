#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_loop_examples.py — `/loop` 示例必带 `--unattended` 护栏（脚手架契约脚本）。

## 为什么需要本脚本

7×24 无人值守要挂两条 loop：

    /loop 10m /sprint-autopilot --unattended     # 开发链路
    /loop 5m  /sprint-aiauto-test --unattended   # 测试链路

`--unattended` **不是可选的装饰**：两命令的 `LOOP_UNATTENDED` 由 4 信号 OR 派生，而**首个
tick** 上 baseline 持久化标志尚未落盘，实际只剩"prompt 里有没有 `/loop` 字样"这一个信号；
某些 runtime 唤起时 prompt 不含该字样 → 首 tick 误判为交互式 → 在**全新项目**上撞第一个
`AskUserQuestion` 就挂起等人，7×24 从第一分钟起就是死的。文档自己写着这条，可散落各处的
示例照样漏写 —— 一次审计在 flows / commands / reference 里查出多处漏写，用户逐处手工补。

**这类漏写复发率极高**：新写一处引导、复制一段旧示例，就又漏一次。人是记不住的，故固化成
有退出码的硬门 —— 凡是文档里出现"可被用户直接复制粘贴执行"的 `/loop … /sprint-*` 写法，
同一处就必须带 `--unattended`。

## 判定口径

1. 全仓 `.md`（默认排除 `.aidp/skills/`：那是 SKILL 本体 + 脚手架 bundle 镜像，
   本体改完由 `mirror_to_bundle.py` 单向同步，重复报只会产生双份噪音）；
2. 匹配 `/loop [间隔] /sprint-autopilot` 与 `/loop [间隔] /sprint-aiauto-test`
   （间隔如 `10m` / `5m` / `30s`，允许缺省）；
3. **按出现逐个判**，不按行判：取本次出现到**下一次出现（或行尾）**之间的片段，片段内
   必须含 `--unattended`。一行里并排写两条 loop、只给其中一条加 flag 的写法同样被抓到。

## 豁免（显式标记，不硬编码文件名）

文档里存在**合法的不带 flag 写法**：对照表里的"错误示例 vs 正确示例"、讲"去掉该 flag 才
保留交互式判据"的段落。这类必须豁免，但**只认写在文件里的显式标记**——绝不在脚本里写死
`usage-guard.md` 之类的文件名白名单（硬编码文件名的豁免会随文件改名/拆分静默失效，
而且下一个人根本不知道某个文件为什么被放过）：

    <!-- loop-check: ignore -->              该行豁免（写在同一行，行尾即可）
    <!-- loop-check: ignore-file 理由 -->     整份文件豁免
    <!-- loop-check: ignore-begin 理由 -->    区块开始
    ...
    <!-- loop-check: ignore-end -->          区块结束

## 用法

    python3 .aidp/scripts/check_loop_examples.py            # 人读报告
    python3 .aidp/scripts/check_loop_examples.py --json     # 机读 JSON
    python3 .aidp/scripts/check_loop_examples.py --root . --path .aidp/flows

退出码：0 = 全部示例合规；1 = 检出漏写 `--unattended`；2 = 用法/读取错误。
"""
import argparse
import json
import os
import re
import sys

# 默认扫全仓；这些目录不下钻（SKILL 本体 / 依赖 / 产物）
EXCLUDE_DIRS = {
    ".git", "node_modules", "__pycache__", "dist", "build", ".venv",
    "skills",  # `.aidp/skills/`：SKILL 本体 + 脚手架 bundle 镜像，由 mirror 脚本同步
}
# ★ 前缀式排除：`.aidp-backup-<时间戳>` 目录名带时间戳，**永远不可能**命中上面的精确名集合。
#   漏排的后果只在下游显形（模板项目自身从不 upgrade、没有备份目录）：任一做过 upgrade 的下游
#   都会把历史备份里的旧文案当成活跃违规报出来，且是 ERROR 级 —— 活跃文件 0 处却恒红，
#   等于把这道守卫在所有下游一次性废掉。备份是冻结的历史副本，按定义不该参与巡检。
EXCLUDE_DIR_PREFIXES = (".aidp-backup",)
REQUIRED_FLAG = "--unattended"
# `/loop 10m /sprint-autopilot` / `/loop /sprint-aiauto-test`（间隔可缺省）
LOOP_RE = re.compile(r"/loop(?:\s+\d+\s*[smhd])?\s+/sprint-(?:autopilot|aiauto-test)\b")

IGNORE_LINE_RE = re.compile(r"<!--\s*loop-check:\s*ignore\s*(?:-->|\s)")
IGNORE_FILE_RE = re.compile(r"<!--\s*loop-check:\s*ignore-file")
IGNORE_BEGIN_RE = re.compile(r"<!--\s*loop-check:\s*ignore-begin")
IGNORE_END_RE = re.compile(r"<!--\s*loop-check:\s*ignore-end")


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
    """返回本行缺 `--unattended` 的出现列表 [(片段文本, 列号)]。

    逐"出现"切片：本次匹配起点 → 下次匹配起点（或行尾）。按行判会漏掉
    "一行两条 loop、只有一条带 flag" 的情况。
    """
    hits = list(LOOP_RE.finditer(line))
    bad = []
    for idx, m in enumerate(hits):
        end = hits[idx + 1].start() if idx + 1 < len(hits) else len(line)
        segment = line[m.start():end]
        if REQUIRED_FLAG not in segment:
            bad.append((segment.strip(), m.start() + 1))
    return bad


def run(root, paths=None):
    violations, scanned, total_hits = [], 0, 0
    for path in sorted(set(iter_md(root, paths))):
        rel = os.path.relpath(path, root)
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except (OSError, UnicodeDecodeError) as e:
            violations.append({"file": rel, "line": 0, "col": 0, "snippet": "",
                               "detail": f"读取失败：{e}"})
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
            total_hits += len(LOOP_RE.findall(line))
            for snippet, col in scan_line(line):
                violations.append({
                    "file": rel, "line": i, "col": col,
                    "snippet": snippet[:120],
                    "detail": f"缺 {REQUIRED_FLAG}：无人值守首个 tick 会被判交互式而挂起等人",
                })
    return {"scanned": scanned, "loop_examples": total_hits, "violations": violations}


def main():
    ap = argparse.ArgumentParser(
        description="`/loop … /sprint-autopilot|aiauto-test` 示例必须带 --unattended")
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
        print(f"[OK] `/loop` 示例全部带 {REQUIRED_FLAG}"
              f"（巡检 {res['scanned']} 份 .md，命中 {res['loop_examples']} 处示例）")
    else:
        print(f"[FAIL] 检出 {len(res['violations'])} 处 `/loop` 示例漏写 {REQUIRED_FLAG}"
              f"（巡检 {res['scanned']} 份 .md，命中 {res['loop_examples']} 处示例）：")
        for v in res["violations"]:
            print(f"  · {v['file']}:{v['line']}:{v['col']}  {v['snippet']}")
        print(f"  修复：补成 `/loop 10m /sprint-autopilot {REQUIRED_FLAG}` / "
              f"`/loop 5m /sprint-aiauto-test {REQUIRED_FLAG}`；"
              f"确属「对比反例 / 讲去掉该 flag 的语义」→ 加 `<!-- loop-check: ignore -->` 豁免。")
    return 1 if res["violations"] else 0


if __name__ == "__main__":
    sys.exit(main())
