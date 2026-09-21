#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""autopilot-prd-watch.py — PRD 目录变化检测（`/sprint-autopilot` Phase 1 的确定性内核）。

## 为什么需要本脚本

Phase 1「PRD 变化检测」此前是内联 bash，判据写成：

    [ "$(echo "$CURRENT_FILES" | sha256sum)" != "$(jq -r '.tracked_files | tostring' b.json | sha256sum)" ]

左边是 `sha256sum` 的**文本行**（`<hash>␠␠<path>` 多行）的哈希，右边是 baseline 里
`[{"path":…,"sha256":…}]` **JSON 串**的哈希——**两种不可比的表示，永不相等**。
后果：`SHOULD_RUN` 恒为 1，「无变化 → 干净退出」这条路径不可达，`/loop` 每 tick 都误判
"PRD 有未 commit 改动"并进主流程空转。

本脚本把检测收敛为一个确定性程序：**两侧都归一到同一 JSON 结构后比对**，
顺带修掉内联 bash 的其它脆弱点（PRD 目录不存在时 `find` 报错、时间戳字符串比较、
tracked_files 回写与检测判据分离导致的口径漂移）。

## 判定顺序（与原 bash 语义一致，只修判据本身）

  1. PRD 目录不存在或无 `*.md`                → skip（`no-prd-files`），不报错
  2. baseline 不存在 / 该版本无记录          → run（`no-baseline`）
  3. `last_commit_hash` 变了                  → run（`new-commit`）
  4. `tracked_files` 归一后不等               → run（`uncommitted-change`）
  5. 其余                                     → skip（`no-change`）

## 用法

    # 检测（只读），机读
    python3 AIDP_HOME/scripts/autopilot-prd-watch.py --version V0.1.0 --json

    # shell 取值
    eval "$(python3 AIDP_HOME/scripts/autopilot-prd-watch.py --version V0.1.0 --shell)"
    # → SHOULD_RUN=1  TRIGGER_REASON='...'  PRD_DIR='...'

    # 命中后回写（Phase 1.4）：加锁写 tracked_files / last_commit_hash / last_trigger_at
    python3 AIDP_HOME/scripts/autopilot-prd-watch.py --version V0.1.0 --commit

    # 每 tick 心跳（无论是否命中都写，供运维区分「loop 存活无变化」与「loop 掉了」）
    python3 AIDP_HOME/scripts/autopilot-prd-watch.py --version V0.1.0 --heartbeat

## 退出码

  0 恒 0（检测结果由 `should_run` 字段承载，绝不用非零退出打断 `/loop`）
  2 用法/环境错误
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from baseline_edit import LockedBaseline, now_iso  # 复用同一把锁，避免两套写盘范式
except ImportError:  # pragma: no cover - 同目录脚本缺失属环境异常
    LockedBaseline, now_iso = None, None

DEFAULT_BASELINE = os.path.join("memory", ".sprint-autopilot-baseline.json")
PRD_SUBDIR = os.path.join("docs", "requirements", "{version}", "产品提供")


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def scan_prd(prd_dir: str) -> list:
    """产出**归一化** tracked_files：[{"path": 相对路径, "sha256": …}]，按 path 升序。

    与 baseline 里存的结构逐字段同构 —— 这是 C1 的修复要点：比对双方必须同构。
    """
    out = []
    if not os.path.isdir(prd_dir):
        return out
    for root, _dirs, files in os.walk(prd_dir):
        for name in files:
            if not name.endswith(".md"):
                continue
            full = os.path.join(root, name)
            rel = os.path.relpath(full, prd_dir).replace(os.sep, "/")
            try:
                out.append({"path": rel, "sha256": sha256_file(full)})
            except OSError:
                continue
    return sorted(out, key=lambda x: x["path"])


def normalize(tracked) -> list:
    """把 baseline 里可能的历史形态归一到 [{"path","sha256"}] 排序列表，供等值比对。"""
    if not isinstance(tracked, list):
        return []
    norm = []
    for item in tracked:
        if isinstance(item, dict) and "path" in item:
            norm.append({"path": str(item["path"]), "sha256": str(item.get("sha256", ""))})
    return sorted(norm, key=lambda x: x["path"])


def git_head_hash(root: str, rel_dir: str) -> str:
    """该 PRD 目录的最近一次 commit hash；不在 git / 无提交 → 空串。"""
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%H", "--", rel_dir],
            cwd=root, capture_output=True, text=True, timeout=10,
        )
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def main() -> int:
    ap = argparse.ArgumentParser(description="PRD 目录变化检测（autopilot Phase 1 内核）")
    ap.add_argument("--root", default=".", help="项目根（默认当前目录）")
    ap.add_argument("--version", required=True, help="目标版本号，如 V0.1.0")
    ap.add_argument("--baseline", default=DEFAULT_BASELINE)
    ap.add_argument("--prd-dir", default="", help="覆盖默认 docs/requirements/{version}/产品提供")
    ap.add_argument("--json", action="store_true", help="机读 JSON 输出")
    ap.add_argument("--shell", action="store_true", help="输出可 eval 的 shell 赋值")
    ap.add_argument("--commit", action="store_true", help="回写 tracked_files/last_commit_hash/last_trigger_at")
    ap.add_argument("--heartbeat", action="store_true", help="额外写顶层 autopilot_loop_heartbeat_at")
    a = ap.parse_args()

    if LockedBaseline is None:
        print("[prd-watch] ✗ 同目录缺 baseline_edit.py（本脚本复用其锁实现）", file=sys.stderr)
        return 2

    root = os.path.abspath(a.root)
    baseline_path = os.path.join(root, a.baseline)
    rel_prd = a.prd_dir or PRD_SUBDIR.format(version=a.version)
    prd_dir = os.path.join(root, rel_prd)

    current = scan_prd(prd_dir)
    head = git_head_hash(root, rel_prd)

    with LockedBaseline(baseline_path, write=False) as b:
        ver = ((b.data.get("versions") or {}).get(a.version) or {}) if isinstance(b.data, dict) else {}
    has_baseline = os.path.isfile(baseline_path) and bool(ver)

    if not current:
        # 无 PRD 可读 → 无论有无 baseline 都没有可规划的输入，跳过而非报错（原内联 bash 会 find 报错）
        should_run, reason = 0, f"{rel_prd} 不存在或无 *.md，跳过（不报错）"
        code = "no-prd-files"
    elif not has_baseline:
        should_run, reason = 1, f"首次运行，{a.version} 无 baseline 记录"
        code = "no-baseline"
    elif head and head != str(ver.get("last_commit_hash") or ""):
        should_run, reason = 1, f"{a.version} PRD 目录有新 commit"
        code = "new-commit"
    elif current != normalize(ver.get("tracked_files")):
        should_run, reason = 1, f"{a.version} PRD 目录有未 commit 文件改动"
        code = "uncommitted-change"
    else:
        should_run, reason = 0, f"{a.version} PRD 无变化"
        code = "no-change"

    if a.commit or a.heartbeat:
        ts = now_iso()
        with LockedBaseline(baseline_path, write=True) as b:
            if a.heartbeat:
                b.data["autopilot_loop_heartbeat_at"] = ts
            versions = b.data.setdefault("versions", {})
            node = versions.setdefault(a.version, {})
            node["last_check_at"] = ts
            if a.commit:
                node["tracked_files"] = current
                node["last_commit_hash"] = head
                node["last_trigger_at"] = ts

    payload = {
        "version": a.version,
        "prd_dir": rel_prd,
        "should_run": should_run,
        "reason_code": code,
        "trigger_reason": reason,
        "file_count": len(current),
        "commit_hash": head,
        "committed": bool(a.commit),
    }

    if a.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif a.shell:
        esc = reason.replace("'", "'\\''")
        print(f"SHOULD_RUN={should_run}")
        print(f"TRIGGER_REASON='{esc}'")
        print(f"PRD_DIR='{rel_prd}'")
        print(f"PRD_REASON_CODE='{code}'")
    else:
        print(f"{'▶️ 触发' if should_run else '⏭️ 跳过'}（{code}）：{reason}｜{rel_prd} 共 {len(current)} 份 PRD")
    return 0


if __name__ == "__main__":
    sys.exit(main())
