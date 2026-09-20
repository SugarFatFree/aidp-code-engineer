#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""aidp_paths.py —— AIDP 运行时产物的**路径单一信源**。

每个运行时产物的路径收成一个函数，调用点不自行拼接字面量——
两个进程各自拼路径、一处改了另一处没改，就会读写不同文件，而产物上与「正常工作」完全同形
（锁文件路径不一致 = 互斥静默归零）。

两类落点：
  · 入库：`memory/.sprint-autopilot-baseline.json`（状态机）、`memory/aidp-config.yaml`（人维护配置）
  · 本地不入库：`memory/.aidp/`（台账、计数、告警、日志、锁）

⛔ 新增运行时产物时**先在这里登记**，别在调用点直接拼路径。
"""
import os

# 程序写的运行时状态统一目录（人别动）；锁文件在其下 `locks/`。
RUNTIME_DIRNAME = ".aidp"
LOCK_DIRNAME = os.path.join(RUNTIME_DIRNAME, "locks")   # 与 baseline_edit.lock_path 同值，改这里要同步那边


def memory_dir(root="."):
    return os.path.join(root, "memory")


def baseline(root="."):
    """autopilot 主状态机（团队共享、入库）。"""
    return os.path.join(memory_dir(root), ".sprint-autopilot-baseline.json")


def _local(root, name):
    """本地运行时产物：落 `memory/.aidp/<name>`（纯本地、不入库）。"""
    return os.path.join(runtime_dir(root), name)


def ceremony_ledger(root="."):
    """里程碑通知台账（会话内本地校验状态，不入库）。"""
    return _local(root, "ceremony-ledger.json")


def stop_guard_count(root="."):
    return _local(root, "stop-guard-count")


def stop_guard_skips(root="."):
    return _local(root, "stop-guard-skips.jsonl")


def alerts_ledger(root="."):
    """本地告警台账（jsonl）：冻结 / 链路失联 / 通知未送达等告警恒追加一行。

    无通知渠道时它就是「停得响」的承载面——人或巡检脚本 `tail` 它即可看到全部告警。
    """
    return _local(root, "alerts.jsonl")


def logs_dir(root="."):
    """7×24 调度运行日志目录（`agent_loop.sh` / `aidp_scheduler.py` 写）。"""
    return _local(root, "logs")


def append_alert(root=".", **fields):
    """追加一条告警到 `alerts_ledger()` 并在 stderr 打印一行；返回写入的记录。

    ⛔ 写盘失败不抛异常（告警是旁路，不能把主流程弄崩），但 stderr 那一行照打。
    """
    import json
    import sys
    import time
    rec = {"at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    rec.update({k: v for k, v in fields.items() if v is not None})
    line = json.dumps(rec, ensure_ascii=False)
    try:
        ensure_runtime_dir(root)
        with open(alerts_ledger(root), "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError as exc:
        rec["ledger_error"] = str(exc)[:120]
    sys.stderr.write("🚨 [AIDP-ALERT] %s %s %s\n" % (
        rec.get("kind") or "alert", rec.get("version") or "", rec.get("title") or rec.get("detail") or ""))
    return rec


def aidp_config(root="."):
    """**人维护**配置的单一落点（团队共享、入库）。单一信源 = `aidp_config.py`。"""
    return os.path.join(memory_dir(root), "aidp-config.yaml")


def runtime_dir(root="."):
    """程序写的运行时产物目录。⛔ 用它之前先 `ensure_runtime_dir()`。"""
    return os.path.join(memory_dir(root), RUNTIME_DIRNAME)


def ensure_runtime_dir(root="."):
    """确保运行时目录存在，返回其路径。

    ⚠️ 为什么必须有这一步：追加写日志的写方通常只做 `open(path, "a")`、**不建父目录**；
    目录不在时写失败只打一行 WARN、业务照常继续 —— 也就是**记录静默丢失**。
    落点从仓库根挪进子目录之后，「目录存在」就从天然成立变成了需要有人保证的前置条件。
    """
    d = runtime_dir(root)
    os.makedirs(d, exist_ok=True)
    return d


def credentials(root="."):
    """生产 / UAT 凭据（chmod 600 + gitignore，**永不入库**）。"""
    return os.path.join(memory_dir(root), ".sprint-autopilot-credentials.json")


# 供体检类脚本遍历：(取路径的函数, 中文名, 性质, 入库策略)
# ⚠️ 第 4 列**必须与 .gitignore 的事实一致**，由 `--check-vcs` 断言。
#    这张表存在的理由就是让人分得清「哪个我能动」；标错等于把清单变成误导源，
#    而它与标对在产物上完全同形。
REGISTRY = (
    (baseline, "autopilot 主状态机", "运行时状态", "入库"),
    (ceremony_ledger, "里程碑通知台账", "运行时状态", "不入库"),
    (stop_guard_count, "Stop 护栏计数", "运行时状态", "不入库"),
    (stop_guard_skips, "Stop 护栏放行留痕", "运行时日志", "不入库"),
    (alerts_ledger, "本地告警台账", "运行时日志", "不入库"),
    (aidp_config, "人维护配置（开关/版本戳/决策兜底）", "人维护配置", "入库"),
    (credentials, "生产/UAT 凭据", "人维护配置", "⛔ 永不入库"),
)


def _git_ignored(root, rel):
    """→ True/False/None（None = 判不了，如非 git 仓库）。"""
    import subprocess
    try:
        r = subprocess.run(["git", "-C", root, "check-ignore", "-q", rel],
                           capture_output=True)
    except (OSError, ValueError):
        return None
    if r.returncode in (0, 1):
        return r.returncode == 0
    return None


def _check_vcs(root=".", as_json=False):
    """登记的入库策略 vs .gitignore 事实。

    ⛔ 判不出来（非 git 仓库 / git 不可用）时**不报绿**：那与「一致」在退出码上同形，
    正是本门要消灭的形态；改报 skipped 并把原因写出来。
    """
    import json
    drift, checked = [], 0
    for fn, cn, kind, vcs in REGISTRY:
        rel = os.path.relpath(fn(root), root).replace(os.sep, "/")
        ig = _git_ignored(root, rel)
        if ig is None:
            continue
        checked += 1
        claimed_ignored = vcs.lstrip("⛔ ").startswith("不入库") or "永不入库" in vcs
        if claimed_ignored != ig:
            drift.append({"path": rel, "name": cn, "claimed": vcs,
                          "actual": "不入库(ignored)" if ig else "入库"})
    res = {"ok": not drift, "checked": checked, "total": len(REGISTRY),
           "skipped": len(REGISTRY) - checked, "drift": drift}
    if as_json:
        print(json.dumps(res, ensure_ascii=False))
    elif checked == 0:
        print("[SKIP] 无法判定（非 git 仓库或 git 不可用）——⛔ 不当作通过")
    elif drift:
        for d in drift:
            print(f"  [ERROR] {d['path']} 登记为「{d['claimed']}」，实际「{d['actual']}」")
        print("  改法：改 REGISTRY 第 4 列或改 .gitignore，让清单与事实一致")
    else:
        print(f"[OK] {checked} 项登记的入库策略与 .gitignore 一致")
    return 1 if drift else 0


def inventory(root="."):
    """列出全部登记产物及其存在性 —— 供 `verify.py` 体检与人工排查。"""
    out = []
    for fn, cn, kind, vcs in REGISTRY:
        p = fn(root)
        out.append({"path": os.path.relpath(p, root).replace(os.sep, "/"),
                    "name": cn, "kind": kind, "vcs": vcs,
                    "exists": os.path.exists(p),
                    "bytes": os.path.getsize(p) if os.path.isfile(p) else 0})
    return out


if __name__ == "__main__":
    import argparse
    import json
    import sys
    ap = argparse.ArgumentParser(description="AIDP 运行时产物清单（路径单一信源）")
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--check-vcs", action="store_true",
                    help="断言登记的入库策略与 .gitignore 事实一致（漂移即 exit 1）")
    a = ap.parse_args()
    if a.check_vcs:
        sys.exit(_check_vcs(a.root, a.json))
    inv = inventory(a.root)
    if a.json:
        print(json.dumps({"artifacts": inv}, ensure_ascii=False, indent=2))
        sys.exit(0)
    print(f"AIDP 运行时产物（{len(inv)} 项 · 路径单一信源 = aidp_paths.py）")
    for it in inv:
        mark = "✔" if it["exists"] else "·"
        print(f"  {mark} {it['path']:<52} {it['kind']:<10} {it['vcs']:<8} {it['name']}")
    print("\n人维护的 = 你可以改；运行时状态/日志 = 程序写，别手动动。")
