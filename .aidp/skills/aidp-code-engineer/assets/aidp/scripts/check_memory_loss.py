#!/usr/bin/env python3
"""check_memory_loss.py — 项目级 memory 文件的「整段被吞」确定性检测。

## 这道门堵的是什么

`memory/` 下的项目级长期记忆（`projectBrief` / `productContext` / `systemPatterns` /
`techContext` / `databaseBaseline`）**相当一部分由人手写，且往往是仓库里唯一一份记录**——
覆盖即永久丢失，不像代码那样有第二处副本可对照。

`/memory-sync` Step 3 的「一律追加/定点改写，绝不整段重写」若只靠纪律，
"整段重写吞掉手写内容"与"本次确实没改那一段"在仓库里**完全同形**——失效时不可观测。

## 基线（写前快照优先，缺省回落 git HEAD）

- `--snapshot`：写入前把受保护文件的**工作区现状**复制到 `memory/.aidp/memory-snapshot/`。
  未提交的手写内容也因此受保护（只和 HEAD 比时，未提交的手改被整段重写仍会判通过）。
- 检查时：某文件有快照 → 与快照比；无快照 → 与 `git HEAD` 比；两者都无 → 跳过。
- 检查通过后自动清掉快照（`--keep-snapshot` 保留）；报红时保留快照，供取回被吞段落。

受保护面 = 项目级 memory 五件套 + 项目记忆文件 + 迭代级 `memory/V*/*/{activeContext,progress}.md`。

## 判据

对每份受保护文件：
  **L1 段落消失**（ERROR）—— HEAD 里有的 `##`/`###` 标题，工作区里找不到了。
  **L2 段落塌缩**（ERROR）—— 同名段落的非空行数下降 ≥ `--shrink`（默认 40%）且至少少 3 行。
  **L3 整份塌缩**（ERROR）—— 全文非空行数下降 ≥ `--shrink`。

⛔ **填占位符不算丢失**：`（待填充）`/`{{…}}` 被真实内容取代**正是**约定 8 要求的动作
（`### ADR-001: （待填充）` → `### ADR-001: 选用 X`）。标题里含占位标记的段落**只按标题前缀比对**，
标题改写不判消失；这一条是本门最容易误伤的地方，误伤一次就会有人把门关掉。

豁免：文件在 HEAD 中不存在（新建）→ 跳过；显式 `<!-- memory-loss: ignore 理由 -->` 在文件头 8 行内。

退出码：0 通过（或无可比基线）；1 有 ERROR；2 参数错。
"""
import sys as _aidp_sys
from pathlib import Path as _AidpPath
_aidp_scripts = str(_AidpPath(__file__).resolve().parent)
if _aidp_scripts not in _aidp_sys.path:
    _aidp_sys.path.insert(0, _aidp_scripts)
from aidp_runtime import runtime_relpath, runtime_text
from vcs import detect_mode, unsupported, EXIT_UNSUPPORTED
import argparse
import json
import os
import re
import subprocess
import sys

PROTECTED = (
    "memory/projectBrief.md",
    "memory/productContext.md",
    "memory/systemPatterns.md",
    "memory/techContext.md",
    "memory/databaseBaseline.md",
    # ★ 项目记忆文件（`AGENTS.md`，仅 Claude Code 时为 `CLAUDE.md`）——`/memory-sync`
    #   **自己点名会写**的文件（「当前状态」段由命令自动更新）：**命令会写、写坏了没有检出器**，
    #   正是本门要防的形态。两个文件名都登记：不存在的那份按「工作区无此文件」跳过。
    #   ⚠️ 二者并存时 `CLAUDE.md` 是 `@AGENTS.md` 薄壳、体量极小，
    #   L2「塌缩 ≥40%」对它天然更敏感（删掉一段占比就很高）——这正是想要的：
    #   它本来就不该被整段删。基线比对按各文件自身体量算，见 `_shrunk()`。
    "AGENTS.md",
    "CLAUDE.md",
    runtime_text('__AIDP_HOME__/AIDP-AGENTS.md', __file__),   # 模板仓库的下发记忆源：整段被吞同样会随脚手架扩散到全部下游
)
# 迭代级记忆（`/memory-sync` Step 2 的主写目标）：按 glob 动态展开
ITERATION_GLOBS = ("memory/V*/*/activeContext.md", "memory/V*/*/progress.md")
SNAPSHOT_DIR = os.path.join("memory", ".aidp", "memory-snapshot")
HEAD_RE = re.compile(r"^(#{2,4})\s+(.+?)\s*$")
IGNORE_RE = re.compile(r"<!--\s*memory-loss:\s*ignore\b")
# 占位标记：含它的标题只按"前缀"比对（填掉占位 = 合规动作，不是段落消失）
PLACEHOLDER_RE = re.compile(r"（待[填补][充写]）|\(待[填补][充写]\)|\{\{[^}]*\}\}|（待确认）")


def protected_files(root):
    import glob
    out = list(PROTECTED)
    for g in ITERATION_GLOBS:
        for p in sorted(glob.glob(os.path.join(root, g))):
            out.append(os.path.relpath(p, root).replace(os.sep, "/"))
    return out


def take_snapshot(root=".", files=None):
    """把受保护文件的工作区现状复制进快照目录（覆盖旧快照）→ 已快照的相对路径列表。"""
    import shutil
    snap = os.path.join(root, SNAPSHOT_DIR)
    if os.path.isdir(snap):
        shutil.rmtree(snap)
    done = []
    for rel in (files or protected_files(root)):
        src = os.path.join(root, rel)
        if os.path.isfile(src):
            dst = os.path.join(snap, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)
            done.append(rel)
    return done


def clear_snapshot(root="."):
    import shutil
    snap = os.path.join(root, SNAPSHOT_DIR)
    if os.path.isdir(snap):
        shutil.rmtree(snap)


def _baseline(root, rel):
    """→ (基线文本, 来源)；快照优先，其次 git HEAD。"""
    sp = os.path.join(root, SNAPSHOT_DIR, rel)
    if os.path.isfile(sp):
        return open(sp, encoding="utf-8").read(), "snapshot"
    old = _git_show(root, rel)
    return old, ("HEAD" if old is not None else None)


def _git_show(root, rel):
    r = subprocess.run(["git", "-C", root, "show", f"HEAD:{rel}"],
                       capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def _sections(text):
    """→ {(层级, 标题): 非空行数}，按出现顺序。"""
    out, cur, n = {}, None, 0
    for ln in text.split("\n"):
        m = HEAD_RE.match(ln)
        if m:
            if cur is not None:
                out[cur] = n
            cur, n = (m.group(1), m.group(2)), 0
        elif ln.strip():
            n += 1
    if cur is not None:
        out[cur] = n
    return out


def _match(old_key, new_sections):
    """在 new 里找到与 old 段落对应的键；找不到返回 None。

    ⛔ **含占位标记的旧标题必须按前缀匹配**：`### ADR-001: （待填充）` 被填成
    `### ADR-001: 选用 Redis` 是约定 8 **强制要求**的动作，逐字比对会把它判成"段落消失"——
    误伤这一条，等于用一道门去阻止另一条约定要求做的事，而那种门必然会被关掉。
    """
    if old_key in new_sections:
        return old_key
    lvl, title = old_key
    if not PLACEHOLDER_RE.search(title):
        return None
    prefix = PLACEHOLDER_RE.split(title)[0].strip()
    if not prefix:
        return None
    for k in new_sections:
        if k[0] == lvl and k[1].startswith(prefix):
            return k
    return None


def _nonempty(text):
    return sum(1 for l in text.split("\n") if l.strip())


def run(root=".", shrink=0.4, files=None):
    res = {"checked": 0, "skipped": [], "errors": []}
    targets = list(files or protected_files(root))
    if detect_mode(root) != "git" and any(
        os.path.isfile(os.path.join(root, rel)) and
        not os.path.isfile(os.path.join(root, SNAPSHOT_DIR, rel))
        for rel in targets
    ):
        return unsupported("diff")
    for rel in targets:
        path = os.path.join(root, rel)
        if not os.path.isfile(path):
            res["skipped"].append({"file": rel, "why": "工作区无此文件"})
            continue
        old, src = _baseline(root, rel)
        if old is None:
            res["skipped"].append({"file": rel, "why": "无快照且 HEAD 无此文件（新建），无可比基线"})
            continue
        new = open(path, encoding="utf-8").read()
        if IGNORE_RE.search("\n".join(new.split("\n")[:8])):
            res["skipped"].append({"file": rel, "why": "显式 ignore"})
            continue
        res["checked"] += 1
        so, sn = _sections(old), _sections(new)
        for k, cnt in so.items():
            title = k[1]
            hit = _match(k, sn)
            if hit is None:
                res["errors"].append({
                    "file": rel, "rule": "L1", "section": title,
                    "msg": "HEAD 里有的段落「%s」在工作区消失了 —— memory 覆盖即永久丢失，"
                           "无第二处副本可对照" % title,
                    "fix": "从基线（%s）取回该段落再定点编辑；确属有意删除 → "
                           "在文件头加 `<!-- memory-loss: ignore 理由 -->`"
                           % (os.path.join(SNAPSHOT_DIR, rel) if src == "snapshot" else "git show HEAD:" + rel),
                })
            elif cnt >= 3 and sn[hit] <= cnt * (1 - shrink) and cnt - sn[hit] >= 3:
                res["errors"].append({
                    "file": rel, "rule": "L2", "section": title,
                    "msg": "段落「%s」从 %d 行塌缩到 %d 行（降幅 ≥%d%%）—— 疑似整段重写"
                           % (title, cnt, sn[hit], int(shrink * 100)),
                    "fix": "确认是「定点改写」而不是「重写整段」；确属有意精简 → 显式 ignore",
                })
        no, nn = _nonempty(old), _nonempty(new)
        if no >= 10 and nn <= no * (1 - shrink):
            res["errors"].append({
                "file": rel, "rule": "L3", "section": "(整份)",
                "msg": "全文从 %d 行塌缩到 %d 行 —— 疑似整份被 Write 覆盖" % (no, nn),
                "fix": "先 Read 全文再定点编辑，⛔ 不得凭印象直接 Write 整份",
            })
    res["passed"] = not res["errors"]
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description="memory 文件整段被吞检测（与写前快照比，缺省与 git HEAD 比）")
    ap.add_argument("--snapshot", action="store_true", help="写入前调用：把受保护文件现状存为比对基线")
    ap.add_argument("--keep-snapshot", action="store_true", help="检查通过后不清理快照")
    ap.add_argument("--root", "--repo-root", dest="root", default=".")
    ap.add_argument("--shrink", type=float, default=0.4, help="塌缩判定降幅阈值（默认 0.4）")
    ap.add_argument("--file", action="append", help="只查指定文件（可重复）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-check", action="store_true")
    a = ap.parse_args(argv)
    if a.self_check:
        sc = os.path.join(os.path.dirname(os.path.abspath(__file__)), "selfcheck.py")
        return subprocess.call([sys.executable, sc, "--only", os.path.basename(__file__)])
    if a.snapshot:
        done = take_snapshot(a.root, a.file)
        print("已快照 %d 份受保护文件 → %s" % (len(done), SNAPSHOT_DIR))
        return 0
    r = run(a.root, a.shrink, a.file)
    if r.get("status") == "unsupported":
        print(json.dumps(r, ensure_ascii=False))
        return EXIT_UNSUPPORTED
    if r["passed"] and not a.keep_snapshot and not a.file:
        clear_snapshot(a.root)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print("巡检 %d 份 memory 文件%s"
              % (r["checked"], "（跳过 %d）" % len(r["skipped"]) if r["skipped"] else ""))
        for e in r["errors"]:
            print("❌ [%s] %s · %s" % (e["rule"], e["file"], e["msg"]))
            print("   → %s" % e["fix"])
        print("结论：%s" % ("✅ 无整段丢失" if r["passed"] else "❌ 检出 %d 处" % len(r["errors"])))
    return 0 if r["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
