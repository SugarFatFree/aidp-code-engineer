#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_shard_counts.py — flow 分片「自称片数 / 范围记法」与实际文件数的一致性守卫。

## 为什么需要本脚本

`.aidp/flows/<命令>/` 下的分片会二次切分（`phase-0-6.md` → 追加 `phase-0-6b.md`），
而散落在多处的「**N 片**」「`phase-0-1.md` … `phase-0-9.md`」这类**范围记法**不会自动跟着改。
后果不是排版问题：执行体按「共 9 片、`phase-0-1` … `phase-0-9`」推进时，
**`phase-0-6b.md` 整片不会被 Read**——那一片里的硬门（如 0.4 项目状态检查、
P0-1 incremental 判据）就此静默漏跑，而所有既有守卫都看不出来。

`check_count_claims.py` 只查三类硬编码计数（核心约定数 / 语义维度数 / 测试分组数），
不含分片数；`check_md_anchors.py` 只验 markdown 链接。这一类此前无人守。

## 判据（两条，都只在能确定性核出真值时才判）

1. **片数声明**：形如「**22 片**」「共 24 片」的声明，若与该命令目录下实际
   `phase-*.md` / `step-*.md` / `planning-*.md`+`release-*.md` 的文件数不符 → FAIL。
   声明行必须能确定归属哪个命令（行内出现命令名或目录名），否则跳过不猜。
2. **范围记法**：形如「`phase-0-1.md` … `phase-0-9.md`」的端点写法，若该目录下
   存在**端点之间**却未被本行显式提及的分片（典型 = `b` / `bis` 后缀）→ FAIL。

## 豁免

    <!-- shardcount-check: ignore -->        该行豁免
    <!-- shardcount-check: ignore-file -->   整份文件豁免

## 用法

    python3 .aidp/scripts/check_shard_counts.py
    python3 .aidp/scripts/check_shard_counts.py --json

退出码：0 = 一致；1 = 检出不一致；2 = 用法/读取错误。
"""
import argparse
import json
import os
import re
import sys

FLOW_ROOT = ".aidp/flows"
SCAN_DIRS = [".aidp/flows", ".aidp/commands", ".aidp/reference"]
EXCLUDE_DIRS = {".git", "node_modules", "__pycache__", "skills"}

IGNORE_LINE_RE = re.compile(r"<!--\s*shardcount-check:\s*ignore\s*(?:-->|\s)")
IGNORE_FILE_RE = re.compile(r"<!--\s*shardcount-check:\s*ignore-file")

# 「**22 片**」「共 24 片」——数字可被 ** 包裹
# `(?<!第)` 排除序数形「第 1 片」——那说的是"第几片"，不是"共几片"，拿它比总数必假阳
# ⚠️ 数字**不得是标识符的一部分**：`<!-- 二次切分 · phase-3 片2/5 -->` 里的 `3` 属于
#   `phase-3` 这个分组名，不是片数；少了这条前瞻/后顾，它会被读成「3 片」并整批误报
#   （路径归属接进来、覆盖面变大之后立刻暴露出这批假阳）。同理排除 `片2/5` 的 `2`——
#   那是"第 2 片"的序号写法，已由 `(?<!第)` 之外的斜杠形态承担。
# ★ 必须同时认「N 片」与「N 个分片」两种写法：只认前者时，「外置为 5 个分片」里的「片」前是
#   「分」而非空白，整条声明**从未被校验过**——实测全仓 9 处 `N 个分片` 写法全部在检查面之外，
#   其中一处（Phase 3 实有 6 片却写 5）就是这么漏掉的。
COUNT_RE = re.compile(
#   ⛔ 同时要挡住小数点后的数字：放开「分片」写法后，「3.9 分片取不到值」里的 `9` 会被读成片数
#      （`9` 前是 `.`，原先的 `(?<![-\w])` 拦不住它）——那是 Step 号，不是计数。
#   ⛔ 还要挡住**斜杠左侧**：`第 1/10 片` 里的 `10` 是片号分母、由下面 `SHARD_ID_RES` 专管，
#      被本条重复报一遍只会让同一处错误出现两次，噪音掩盖真信号。
    r"(?<!第)(?<!第\s)(?<!/)(?<!/\s)(?<![-\w.])(?:共\s*)?\*{0,2}(\d{1,3})\*{0,2}\s*(?:个\s*)?分?片(?!\s*\d*\s*/)")
# 「`phase-0-1.md` … `phase-0-9.md`」——中间可为 … / ~ / - / 到
# ★ 斜杠形片号（`分片 [7/10]` / `第 1/9 片` / `片6a/8` / `分片 1/7`）——**此前完全在检查面之外**：
#   `COUNT_RE` 末尾的 `(?!\s*\d*\s*/)` 负向前瞻专门把它们排除掉了。而分片头那句
#   「第 N/M 片」正是执行体判断"我是不是已经读完整段"的依据：M 少一片，最后一片永远不会被 Read。
SHARD_ID_RES = (
    re.compile(r"(?:分片|片)\s*\[?\s*\d{1,3}[a-z0-9]*\s*/\s*(\d{1,3})\s*\]?"),
    re.compile(r"第\s*\d{1,3}[a-z0-9]*\s*/\s*(\d{1,3})\s*片"),
)
# 文件名 → 所属分组（`phase-0-6b2.md` → `phase-0`）
SHARD_GROUP_RE = re.compile(r"^([a-z0-9-]+?)-(\d+)([a-z][a-z0-9]*)?\.md$")

RANGE_RE = re.compile(
    r"`(?P<a>[a-z0-9-]+?)-(?P<n1>\d+)\.md`\s*(?:…|\.{2,}|~|—|-|到)\s*`(?P=a)-(?P<n2>\d+)\.md`")


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return None


def shard_dirs(root):
    """{命令名: [分片文件名…]}；只收真正做了分片的目录。"""
    out = {}
    base = os.path.join(root, FLOW_ROOT)
    if not os.path.isdir(base):
        return out
    for name in sorted(os.listdir(base)):
        d = os.path.join(base, name)
        if not os.path.isdir(d):
            continue
        files = [f for f in sorted(os.listdir(d))
                 if f.endswith(".md") and f != "README.md"]
        if files:
            out[name] = files
    return out


def _walk(root):
    for d in SCAN_DIRS:
        base = os.path.join(root, d)
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [x for x in dirnames if x not in EXCLUDE_DIRS]
            for fn in sorted(filenames):
                if fn.endswith(".md"):
                    yield os.path.join(dirpath, fn)


def run(root):
    dirs = shard_dirs(root)
    # ★ 附属文件（理据/不变式/用法守卫）不计入"执行分片"，但计入"全部"
    ATTACH = {"rationale.md", "invariants.md", "usage-guard.md"}
    exec_counts, all_counts, by_prefix, phase_counts = {}, {}, {}, {}
    for cmd, files in dirs.items():
        numbered = [f for f in files if f not in ATTACH]
        exec_counts[cmd] = len(numbered)
        all_counts[cmd] = len(files)
        pref, ph = {}, {}
        for f in numbered:
            # ★ 后缀必须吃数字：`phase-0-6b2.md` 的 `b2` 用 `([a-z]*)` 整条匹配不上 ⇒
            #   该文件不计入任何分组 ⇒ `phase-0` 组少算一片 ⇒ 「10 片」这类错误声明判过。
            m = SHARD_GROUP_RE.match(f)
            if m:
                pref.setdefault(m.group(1), []).append(f)
                ph[m.group(1)] = ph.get(m.group(1), 0) + 1
        by_prefix[cmd] = pref
        phase_counts[cmd] = ph          # {"phase-0": 10, "phase-3": 10, ...}

    findings, scanned, claims = [], 0, 0
    for path in sorted(set(_walk(root))):
        text = _read(path)
        if text is None or IGNORE_FILE_RE.search(text):
            continue
        scanned += 1
        rel = os.path.relpath(path, root)
        for i, line in enumerate(text.split("\n"), 1):
            if IGNORE_LINE_RE.search(line):
                continue
            # 判据 1：片数声明——必须能确定归属命令，否则不猜。
            # ★ 归属优先看**文件所在目录**：`.aidp/flows/<cmd>/x.md` 里的「第 N/M 片」
            #   天然说的就是 `<cmd>` 的分片，比在行内找命令名可靠得多。原先只认行内命令名，
            #   而分片自己的头注释（「本文件是 … 第 9/10 片」）常不重复写命令名 →
            #   实测 61 处片数声明里有 17 处（27%）**一处都没被校验过**，全落在这类头注释上。
            owner = None
            _parts = rel.replace(os.sep, "/").split("/")
            if len(_parts) >= 3 and _parts[0] == ".aidp" and _parts[1] == "flows" \
                    and _parts[2] in dirs:
                owner = _parts[2]
            if owner is None:
                for cmd in dirs:
                    if cmd in line:
                        owner = cmd
                        break
            if owner:
                # ★ 片数声明常带**作用域**：「Phase 0 … 第 3/10 片」说的是 Phase 0 内的片数，
                #   不是整命令。故把本行提到的所有合法真值都收进候选集，命中任一即通过；
                #   不这样做会把一整批正确的分片头注释全判成错（实测 20+ 假阳）。
                #   合法真值 = 整命令执行分片数 / 整命令全部文件数 / **任一前缀分组的片数**
                #   （`phase-0` 组 10 片、`step-1` 组 2 片、`postdev-writeback` 组 3 片…）。
                #   只认 Phase 前缀会把 Step/自定义前缀的分组计数全判成错。
                ok_vals = {exec_counts[owner], all_counts[owner]}
                # ★ 行内**点名了某个分组**时，只认那一组的片数，不再吃下全部分组的并集。
                #   吃并集会放过最典型的一种错：**两个分组的片数被写反**（`Phase 0 … 12 片` /
                #   `Phase 3 … 10 片`，而实际是 10 / 12）——两个数都在并集里，于是恒绿。
                #   而这正是本门 docstring 声称要防的失效：执行体按错数字推进，整片不被 Read。
                #   只在**恰好点名一个分组**时收紧；同时提到多个分组无法判归属，维持并集。
                named = {g for g in phase_counts[owner]
                         if re.search(r"(?<![-\w])" + re.escape(g).replace(r"\-", r"[-\s]?") +
                                      r"(?![-\w])", line, re.IGNORECASE)}
                if len(named) == 1:
                    ok_vals |= {phase_counts[owner][next(iter(named))]}
                else:
                    ok_vals |= set(phase_counts[owner].values())
                for m in COUNT_RE.finditer(line):
                    claims += 1
                    decl = int(m.group(1))
                    if decl not in ok_vals:
                        findings.append({
                            "file": rel, "line": i, "kind": "片数",
                            "claim": m.group(0), "decl": decl,
                            "actual": f"合法真值 {sorted(ok_vals)}"
                                      f"（执行分片 {exec_counts[owner]} / 全部 {all_counts[owner]}）",
                            "owner": owner, "context": line.strip()[:120],
                        })
            # 判据 3：斜杠形片号的**分母**必须等于本文件所属分组的真实片数
            _dir = os.path.basename(os.path.dirname(path))
            _gm = SHARD_GROUP_RE.match(os.path.basename(path))
            if _gm and _dir in phase_counts and _gm.group(1) in phase_counts[_dir]:
                _real = phase_counts[_dir][_gm.group(1)]
                for _rx in SHARD_ID_RES:
                    for _m in _rx.finditer(line):
                        claims += 1
                        if int(_m.group(1)) != _real:
                            findings.append({
                                "file": rel, "line": i, "kind": "片号分母",
                                "claim": _m.group(0), "decl": int(_m.group(1)),
                                "actual": f"{_gm.group(1)} 组实有 {_real} 片",
                                "owner": _dir, "context": line.strip()[:120],
                            })
            # 判据 2：范围记法端点之间是否存在未被提及的分片
            # ⛔ 范围记法只在**本行/本文件所属命令**内比对：`phase-3-*` 这类前缀多个命令都有，
            #   跨命令比会拿 A 命令的 b 分片去指责 B 命令的范围记法（实测假阳）。
            #   归属推断优先级：行内明写的命令 > 文件所在 flows 子目录 > 命令文件自身的 basename
            #   （`.aidp/commands/sprint-aiauto-test.md` 里的 `phase-3-*` 范围显然指它自己的分片）
            range_owner = owner or next(
                (c for c in dirs if os.sep + c + os.sep in path), None) or \
                next((c for c in dirs
                      if os.path.basename(path) == c + ".md"), None)
            for m in RANGE_RE.finditer(line):
                claims += 1
                pfx, n1, n2 = m.group("a"), int(m.group("n1")), int(m.group("n2"))
                for cmd, pref in by_prefix.items():
                    if range_owner and cmd != range_owner:
                        continue
                    for f in pref.get(pfx, []):
                        mm = re.match(r"^[a-z0-9-]+?-(\d+)([a-z]+)\.md$", f)
                        if not mm:
                            continue          # 无后缀分片天然被范围覆盖
                        if n1 <= int(mm.group(1)) <= n2 and f not in line:
                            findings.append({
                                "file": rel, "line": i, "kind": "范围记法",
                                "claim": m.group(0), "decl": f"{pfx}-{n1}…{n2}",
                                "actual": f"区间内存在未显式提及的分片 {f}",
                                "owner": cmd, "context": line.strip()[:120],
                            })
    # 同文件同问题只报一次
    seen, uniq = set(), []
    for f in findings:
        k = (f["file"], f["kind"], f["claim"], f["actual"])
        if k not in seen:
            seen.add(k)
            uniq.append(f)
    return {"scanned": scanned, "claims": claims, "dirs": exec_counts, "findings": uniq}


def main():
    ap = argparse.ArgumentParser(description="flow 分片自称片数 / 范围记法 vs 实际文件数")
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
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
        res = run(args.root)
    except Exception as e:                                    # noqa: BLE001
        print(json.dumps({"error": str(e)}, ensure_ascii=False) if args.json
              else f"[ERROR] 检查执行失败：{e}")
        return 2

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    elif not res["findings"]:
        print(f"[OK] flow 分片计数与范围记法一致"
              f"（巡检 {res['scanned']} 份 .md，命中 {res['claims']} 处声明）")
    else:
        print(f"[FAIL] 检出 {len(res['findings'])} 处分片计数/范围记法与实际不符"
              f"（巡检 {res['scanned']} 份 .md）——按它推进的执行体会整片漏 Read：")
        for f in res["findings"]:
            print(f"  · {f['file']}:{f['line']}  [{f['kind']}] {f['claim']}"
                  f"  → {f['actual']}（{f['owner']}）")
            print(f"      {f['context']}")
        print("  修复：改成实际值；范围记法须把 b/bis 后缀分片显式列出"
              "（如 `phase-0-1.md` … `phase-0-6.md` / `phase-0-6b.md` / `phase-0-7.md`）。")
    return 1 if res["findings"] else 0


if __name__ == "__main__":
    sys.exit(main())
