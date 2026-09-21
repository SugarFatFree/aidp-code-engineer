#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""baseline_archive.py — 把**已正式发布**版本的 baseline 明细搬进归档文件（主文件留墓碑）。

## 为什么需要本脚本

`memory/.sprint-autopilot-baseline.json` **只增不减**：每个版本一段 `versions.<V>`，
其中 `builds[]` 是大头（每版 10~15KB）。两条 `/loop` 一次会话要 30+ 次
`baseline_edit.py`，每次都持 flock **全量读写整个文件** —— 而其中 90% 是已发布、
永不再改的历史。下游实测 80KB / 16 个版本，一年后按现速率到 200KB+。

## 归档不能让读方取空（这一条比归档本身重要）

⛔ **整段删掉 `versions.<V>` 是错的**。`/sprint-autopilot` Phase 0.3.3 状态机按
**S0→S1→S2→S3→S4 顺序、首个命中即生效**判定，其中：

    S2 = 计划在 + 所有 Sprint ✅ + `versions.<V>.internal_released_at` **为空**

`internal_released_at` 一旦取空，一个**早已 tag 发布**的版本会重新命中 S2、
被选成 `PRE_RELEASE_VERSION`，autopilot 下一 tick 就对它再跑一遍准发布归档。
"数据还在但机器读不到"比不归档更糟，而且全程零告警。

故本脚本用**墓碑（tombstone）**而不是删除：主文件保留 `KEEP_KEYS` 白名单里的少量标量
（全是被 `jq` 直读、或被状态机/选版判据消费的字段），bulk 搬进
`memory/.aidp-baseline-archive/baseline-<V>.json`。

- **`jq` 直读的读方**拿不到回落（它们读的是原始 JSON），所以 `KEEP_KEYS` 必须覆盖
  它们会按历史版本号回查的字段；本脚本的归档面又只限**非最近两版**，
  而 `jq` 读方的版本入参恒是 `TARGET_VERSION` / `PRE_RELEASE_VERSION`（= 最近两版）。
- **`baseline_edit.py get`** 有归档回落（`load_archived_node`），
  连 `--build` 形态一并覆盖。
- 未被保留、也未被回落的键（`run_state` / `auto_fixable_pending` / 各类 streak）
  **恰好应当读空**：已发布版本不该再被选成 TARGET，读空正是期望行为。

## 归档范围（三条同时成立才搬）

1. 按 SemVer 倒序**排在第 3 位及以后**（= 保留「当前版本 + 上一版本」，准发布要读上一版）；
2. `internal_released_at` 非空（已准发布归档）；
3. 默认还要求**有对应 git tag**（`v0.1.0` / `V0.1.0`），即真正正式发布过；
   `--no-require-tag` 可放宽（无 git 仓库的夹具/测试用）。

## 并发安全

全部改动在 `baseline_edit.LockedBaseline(write=True)` 的 **flock + 锁内重读 + 原子写回**
里完成，与两条 loop 共用同一把锁、**不新增锁文件**。⛔ 绝不裸 read-modify-write。

## 幂等

节点里除 `KEEP_KEYS` + `archived*` 外没有别的键 → 已是墓碑 → 跳过，归档文件不动
（⛔ 尤其不能拿墓碑去覆盖一份完好的归档）。

## 用法

    python3 AIDP_HOME/scripts/baseline_archive.py                 # 执行归档
    python3 AIDP_HOME/scripts/baseline_archive.py --dry-run       # 只报不写
    python3 AIDP_HOME/scripts/baseline_archive.py --json          # 机读
    python3 AIDP_HOME/scripts/baseline_archive.py --keep 3        # 多留一版

## 退出码

  0 = 成功（含"无可归档"）  ·  2 = baseline 不可读写 / 用法错
"""
import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from baseline_edit import (ARCHIVE_DIRNAME, DEFAULT_BASELINE,  # noqa: E402
                           LockedBaseline, archive_file, now_iso)

# ★ 墓碑保留键（主文件留下的全部内容）。每一条都有明确读方，删任何一条都会让某个判据取空：
#   · internal_released_at —— Phase 0.3.3 的 S2/S3 判据 + `current-version` 的排除条件（最关键）
#   · phase_beta_done_at   —— `current-version` 选版判据的另一半
#   · source               —— `/sprint-batch` step-6b「是否属 autopilot 体系」判据
#   · last_deployed_at / deployment_mode / aiauto_tested_at —— Phase 2 准发布双门的 jq 读点
#   · current_build / build_seq —— build 号连续性（版本万一被重开时不从头发号）
#   · release_tag_name / release_branch_name —— 发布产物定位，人读与 3.4.4 失败处置
#   · needs_human          —— 0.3.4 候选剔除；已发布版通常没有，有则必须原样留着
KEEP_KEYS = (
    "internal_released_at", "phase_beta_done_at", "source",
    "last_deployed_at", "deployment_mode", "aiauto_tested_at",
    "current_build", "build_seq",
    "release_tag_name", "release_branch_name", "needs_human",
)
# 墓碑自身的元数据键（判"是否已归档"时不算作 bulk）
MARKER_KEYS = ("archived", "archived_at", "archive_file", "archived_build_count")

_SEMVER_RE = re.compile(r"^[Vv]?(\d+)\.(\d+)\.(\d+)")


def semver_key(v: str):
    """`V0.10.0` → (0,10,0)；解析不了给 (-1,-1,-1) 让它排最后。"""
    m = _SEMVER_RE.match(str(v or ""))
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else (-1, -1, -1)


def git_tags(root: str) -> set:
    try:
        out = subprocess.run(["git", "-C", root, "tag"], capture_output=True,
                             text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return set()
    if out.returncode != 0:
        return set()
    return {t.strip() for t in (out.stdout or "").splitlines() if t.strip()}


def has_tag(version: str, tags: set) -> bool:
    bare = str(version or "").lstrip("Vv")
    return bool(tags & {"v" + bare, "V" + bare, version, "release-v" + bare})


def is_tombstone(node: dict) -> bool:
    """节点里除白名单 + 墓碑元数据外再无别的键 → 已归档过，无需重复搬。"""
    extra = set(node) - set(KEEP_KEYS) - set(MARKER_KEYS)
    return not extra


def plan(versions: dict, keep: int, tags: set, require_tag: bool):
    """返回 (待归档版本列表, 逐版跳过原因)。"""
    ordered = sorted(versions, key=semver_key, reverse=True)
    todo, skipped = [], []
    for rank, v in enumerate(ordered):
        node = versions.get(v)
        if not isinstance(node, dict):
            skipped.append({"version": v, "reason": "not-a-dict"})
            continue
        if rank < keep:
            skipped.append({"version": v, "reason": "recent-%d" % (rank + 1)})
            continue
        if not node.get("internal_released_at"):
            skipped.append({"version": v, "reason": "not-released"})
            continue
        if require_tag and not has_tag(v, tags):
            skipped.append({"version": v, "reason": "no-git-tag"})
            continue
        if is_tombstone(node):
            skipped.append({"version": v, "reason": "already-archived"})
            continue
        todo.append(v)
    return todo, skipped


def node_bytes(node) -> int:
    return len(json.dumps(node, ensure_ascii=False).encode("utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description="baseline 已发布版本归档（主文件留墓碑）")
    ap.add_argument("--baseline", default=DEFAULT_BASELINE)
    ap.add_argument("--root", default=".", help="仓库根（git tag 判定用）")
    ap.add_argument("--keep", type=int, default=2,
                    help="主文件保留最近几个版本的完整明细（默认 2 = 当前版 + 上一版）")
    ap.add_argument("--no-require-tag", action="store_true",
                    help="不要求 git tag 存在（无 git 仓库的夹具用）")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if a.keep < 1:
        sys.stderr.write("✗ --keep 至少为 1（准发布要读上一版，留 0 版必然取空）\n")
        return 2
    if not os.path.isfile(a.baseline):
        res = {"baseline": a.baseline, "archived": [], "skipped": [],
               "note": "baseline 不存在，无可归档"}
        print(json.dumps(res, ensure_ascii=False, indent=2) if a.json
              else "ℹ️ baseline 不存在：%s（无可归档）" % a.baseline)
        return 0

    tags = set() if a.no_require_tag else git_tags(a.root)
    archive_dir = os.path.join(os.path.dirname(a.baseline) or ".", ARCHIVE_DIRNAME)

    # ⛔ 全程在同一把 flock 内：计划与落盘之间不能放开锁，否则另一条 loop 刚写进去的
    #    字段会被"按旧计划搬走"而丢失。LockedBaseline 进入时就是锁内重读。
    archived, skipped, before, after = [], [], 0, 0
    with LockedBaseline(a.baseline, write=not a.dry_run) as b:
        versions = (b.data or {}).get("versions") or {}
        before = node_bytes(b.data)
        todo, skipped = plan(versions, a.keep, tags, not a.no_require_tag)
        for v in todo:
            node = versions[v]
            tomb = {k: node[k] for k in KEEP_KEYS if k in node}
            tomb["archived"] = True
            tomb["archived_at"] = now_iso()
            tomb["archive_file"] = archive_file(a.baseline, v)
            blds = node.get("builds")
            tomb["archived_build_count"] = len(blds) if isinstance(blds, list) else 0
            payload = {"version": v, "archived_at": tomb["archived_at"],
                       "source_baseline": a.baseline, "node": node}
            saved = node_bytes(node) - node_bytes(tomb)
            if not a.dry_run:
                os.makedirs(archive_dir, exist_ok=True)
                dst = archive_file(a.baseline, v)
                tmp = dst + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)
                os.replace(tmp, dst)
                # ⛔ 归档文件**先落盘、再改主文件**：反过来一旦中途失败，主文件已成墓碑
                #    而明细无处可读 —— 正是本脚本要避免的那种不可逆丢失。
                versions[v] = tomb
            archived.append({"version": v, "archive_file": archive_file(a.baseline, v),
                             "builds": tomb["archived_build_count"], "saved_bytes": saved})
        after = node_bytes(b.data)

    res = {"baseline": a.baseline, "dry_run": a.dry_run, "keep": a.keep,
           "require_tag": not a.no_require_tag,
           "archived": archived, "skipped": skipped,
           "bytes_before": before, "bytes_after": after,
           "bytes_saved": before - after if not a.dry_run
           else sum(x["saved_bytes"] for x in archived)}
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        tag = "（dry-run，未写盘）" if a.dry_run else ""
        if not archived:
            print("ℹ️ 无可归档版本%s（保留最近 %d 版；其余需 internal_released_at 非空%s）"
                  % (tag, a.keep, "" if a.no_require_tag else " + 有 git tag"))
        else:
            print("✅ 已归档 %d 个版本%s → %s" % (len(archived), tag, archive_dir))
            for x in archived:
                print("   · %s（%d 条 build，省 %d 字节）" % (x["version"], x["builds"],
                                                       x["saved_bytes"]))
            print("   主文件 %d → %d 字节" % (before, after))
    return 0


if __name__ == "__main__":
    sys.exit(main())
