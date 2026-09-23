#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""autopilot 通用 stuck 检测（"既不失败也不推进"的兜底熔断）。

## 为什么需要它

autopilot 现有的熔断**全是"特定失败计数"式**——`dev_fail_streak` / `probe_fail_streak` /
`test_loop_missing_streak` / `report_gate_fail_streak` … 无一例外**都要求先有一次明确失败**才计数。
但真实卡死往往**没有失败**：子 Agent 每 tick 回传 partial、某个 Sprint 永远 close 不掉、
`pending_actions` 里某项每 tick 都补不完。表现是 `/loop` 岁月静好地空转，
**零告警、零熔断、build 永不收口**——没有任何现有护栏会响。

该检测此前只写在 `flows/sprint-autopilot/invariants.md` 里，**10 个执行分片一处都没调用**
（`phase_enter_count` / `STUCK_PHASE_ENTER` 全仓仅命中 invariants 与 `baseline_edit.py`）——
正是那份文件自己警告过的病：「只在 invariants 里描述而分片不写盘 = 状态机不存在」。
封装成脚本 + 由 `phase-1.md` 无条件调一次，才算真正落地。

## 判据（两条**同时**满足才熔断，缺一都会误伤）

1. `run_state.phase_enter_count >= --enter-threshold`（默认 8）
2. `run_state.phase_first_entered_at` 距今 > `--age-seconds`（默认 7200 = 2 小时）

只看次数会误伤「逐 tick 单 Sprint」这类**正常**的同 Phase 多次进入（`3.2-dev` 本就每 tick 重入，
但 `next_sprint` 在推进、单轮耗时也远短于 2 小时）；只看时长会误伤长 Sprint。

## 只读判定 + 加锁写冻结

`phase_enter_count` / `phase_first_entered_at` 的**唯一维护者**是各 Phase 出口的
`baseline_edit.py run-state`（它按「换 Phase 或 next_sprint 游标前移」判推进并重置）。
本脚本**绝不 bump 它们**——多加一次就等于每 tick 加两次、阈值提前一半到达，
长版本会在正常推进中被误判 stuck。冻结写入统一走 `baseline_edit.py`（flock + 锁内重读）。

## 冻结字段（遵守「冻结字段写入契约」，见 `/sprint-aiauto-test` `phase-0-6.md`）

`versions.{V}.needs_human=true` + `aiauto_frozen_at=@now` + `freeze_reason=stuck-phase`
+ 顶层 `aiauto_blocked_reason=frozen:stuck-phase@{V}`。
`stuck-phase` 属**交接类**（解冻 = 人工）——"原地打转"不会因新部署而消失。

## 退出码

  0 = 未 stuck（或不适用：无 baseline / 无 run_state / 已冻结）
  1 = 判定 stuck、已冻结、**#4 已由本脚本自己发出**（调用方让位本 tick 即可）
  2 = 入参或环境错
  3 = 判定 stuck 但**冻结字段写盘失败**（#4 仍已发出）——⛔ 调用方不得当 1 处理：
      盘上没冻，下 tick 判据未变、`already-frozen` 早退不生效 ⇒ 无限重冻循环
"""
import sys as _aidp_sys
from pathlib import Path as _AidpPath
_aidp_scripts = str(_AidpPath(__file__).resolve().parent)
if _aidp_scripts not in _aidp_sys.path:
    _aidp_sys.path.insert(0, _aidp_scripts)
from aidp_runtime import runtime_text

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

DEFAULT_BASELINE = os.path.join("memory", ".sprint-autopilot-baseline.json")
BE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "baseline_edit.py")


CARD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notify.py")


def _send_stuck_card(version: str, out: dict) -> None:
    """冻结成立即**由本脚本自己发 #4**，不把发通知义务留给调用方。

    ⛔ 别改回「发通知归调用方」：本门的存在理由正是「真实卡死表现为零告警空转」，
    调用方少写一行发通知，净效果就从「静默空转」换成「静默永冻」——而 `stuck-phase`
    属 `_HUMAN_ONLY`，没有任何探针能自动解冻，没人知道就永远不会有人来解。
    发通知失败只记 `card_error`、不改冻结结论（冻结已经写盘，回滚它只会更糟）。
    """
    if not os.path.isfile(CARD):
        out["card_sent"] = False
        out["card_error"] = "notify.py 不存在"
        return
    cmd = [sys.executable, CARD, "--node", "#4", "--auto", "--header-color", "red",
           "--title", "已冻结：%s 原地打转（stuck-phase）" % version,
           "--version", version,
           "--section", (runtime_text('Phase %s 连续进入 %d 次、滞留 %d 分钟且无推进（既不失败也不前进）。\n未完成动作：%s\n恢复：人工排查卡住原因后运行 `python3 __AIDP_HOME__/scripts/autopilot_unfreeze.py --manual %s`，下个 tick 自动继续。', __file__)
                         % (out.get("current_phase", "?"), out.get("phase_enter_count", 0),
                            int(out.get("age_seconds", 0)) // 60,
                            ", ".join(out.get("pending_actions") or []) or "无", version))]
    cr = subprocess.run(cmd, capture_output=True, text=True)
    out["card_sent"] = cr.returncode == 0
    if cr.returncode == 3:
        out["card_skipped"] = "not-configured"     # 未配置渠道 = 合法降级；告警已由 notify.py 写入本地告警台账
    elif cr.returncode != 0:
        out["card_error"] = (cr.stderr or "").strip()[:160]


def _to_epoch(ts) -> float:
    """ISO8601 → epoch 秒；不可解析返回 0。

    ⚠️ 一律 epoch 比较，不用字符串比大小——`+08:00` 与 `Z` 两种写法混排时字典序与真实先后不一致。
    """
    if not ts:
        return 0.0
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return 0.0


def _be(baseline: str, *args) -> int:
    """经 baseline_edit.py 写（唯一加锁写入口）。

    ⚠️ **必须把 `--baseline` 透传下去**：漏传时读用 `--baseline` 指定的文件、写却落到
    `baseline_edit.py` 的默认路径（真实 `memory/.sprint-autopilot-baseline.json`）——
    读写不同文件，既让 `--baseline` 形同虚设，也会让测试/演练把冻结态写进真实仓库 baseline
    （本项目已因此误提交过一次冻结版本键）。
    """
    return subprocess.run([sys.executable, BE, "--baseline", baseline, *args],
                          capture_output=True, text=True).returncode


def run(baseline: str, version: str, enter_threshold: int, age_seconds: int, apply: bool,
        send_card: bool = True) -> dict:
    try:
        with open(baseline, encoding="utf-8") as f:
            data = json.load(f) or {}
    except FileNotFoundError:
        return {"applicable": False, "reason": "no-baseline"}
    except (OSError, ValueError) as e:
        return {"applicable": False, "reason": f"unreadable: {e}"}

    node = ((data.get("versions") or {}).get(version) or {})
    rs = node.get("run_state") or {}
    if not rs:
        return {"applicable": False, "reason": "no-run-state"}
    if node.get("needs_human"):
        # 已冻结 → 不重复冻结、不重复发 #4
        return {"applicable": False, "reason": "already-frozen"}

    cnt = int(rs.get("phase_enter_count") or 1)
    first = rs.get("phase_first_entered_at") or ""
    cur = rs.get("current_phase") or "?"
    age = int(datetime.now(timezone.utc).timestamp() - _to_epoch(first)) if first else 0

    stuck = cnt >= enter_threshold and age > age_seconds
    out = {
        "applicable": True, "stuck": stuck, "version": version, "current_phase": cur,
        "phase_enter_count": cnt, "phase_first_entered_at": first, "age_seconds": age,
        "pending_actions": rs.get("pending_actions") or [],
        "enter_threshold": enter_threshold, "age_threshold": age_seconds,
    }
    if not stuck or not apply:
        return out

    reason = (f"Phase {cur} 连续进入 {cnt} 次、滞留超 {age // 60} 分钟且无推进"
              f"（既不失败也不前进）；未完成动作：{', '.join(out['pending_actions']) or '无'}")
    # ⚠️ 必须校 `baseline_edit.py` 的返回码：写失败仍报 `frozen:true` 会让调用方以为已冻结，
    #    实际下 tick 判据未变 → 每 tick 重发 #4、熔断形同虚设（"报喜不报忧"式的假冻结）。
    rc1 = _be(baseline, "--version", version, "set", "needs_human", "true", "aiauto_frozen_at", "@now",
              "freeze_reason", "stuck-phase", "needs_human_reason", reason)
    rc2 = _be(baseline, "set", "aiauto_blocked_reason", f"frozen:stuck-phase@{version}")
    out["frozen"] = (rc1 == 0 and rc2 == 0)
    if not out["frozen"]:
        out["freeze_error"] = f"baseline_edit 写冻结字段失败（rc={rc1}/{rc2}）→ 本版未真正冻结"
    # ★ 无论冻结字段写成没写成都要发通知：写失败反而更需要人知道（此刻既没冻住、也没人被通知）。
    if send_card:
        _send_stuck_card(version, out)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="autopilot 通用 stuck 检测（既不失败也不推进的兜底熔断）")
    ap.add_argument("--version", required=True, help="被检版本号（TARGET_VERSION）")
    ap.add_argument("--baseline", default=DEFAULT_BASELINE)
    ap.add_argument("--enter-threshold", type=int,
                    default=int(os.environ.get("STUCK_PHASE_ENTER_THRESHOLD", "8")))
    ap.add_argument("--age-seconds", type=int,
                    default=int(os.environ.get("STUCK_PHASE_AGE_SECONDS", "7200")))
    ap.add_argument("--dry-run", action="store_true", help="只判定不写冻结字段")
    ap.add_argument("--no-card", action="store_true",
                    help="冻结时不发 #4（仅自检/演练用；⛔ 正常链路不要传）")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if not a.version:
        print("[stuck-check] ✗ 缺 --version", file=sys.stderr)
        return 2
    r = run(a.baseline, a.version, a.enter_threshold, a.age_seconds, apply=not a.dry_run,
            send_card=not (a.no_card or a.dry_run))

    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    elif not r.get("applicable"):
        print(f"[stuck-check] N/A（{r.get('reason')}）")
    elif not r.get("stuck"):
        print(f"[stuck-check] ✅ 未 stuck：Phase {r['current_phase']} "
              f"进入 {r['phase_enter_count']}/{r['enter_threshold']} 次、滞留 {r['age_seconds'] // 60} 分钟")
    else:
        if r.get("frozen"):
            tail = " → 已 needs_human 冻结本版"
        elif r.get("freeze_error"):
            tail = f" → ⚠️ {r['freeze_error']}"
        else:
            tail = "（--dry-run，未写盘）"
        print(f"⛔ 通用 stuck 熔断：Phase {r['current_phase']} 连续 {r['phase_enter_count']} tick 原地打转"
              f"（首次进入 {r['phase_first_entered_at']}，已滞留 {r['age_seconds'] // 60} 分钟）"
              f"{tail}")
        print(f"   未完成动作：{', '.join(r['pending_actions']) or '无'}；解冻 = 人工"
              f"（--target <V> / --reset-baseline / 清 needs_human）")
        if "card_sent" in r:
            print("   #4 里程碑通知：" + ("已发出" if r["card_sent"]
                                  else (runtime_text('未配置通知渠道（已写本地告警台账 memory/.aidp/alerts.jsonl）', __file__)
                                        if r.get("card_skipped") else
                                        f"⚠️ 未送达（{r.get('card_error', '')}）——冻结仍然成立，告警见 memory/.aidp/alerts.jsonl")))
    # ★ 写盘失败必须走**另一个**退出码：声称已冻、盘上没冻 ⇒ 下 tick 判据未变、
    #   `already-frozen` 早退不生效 ⇒ 无限重冻循环，而调用方按 `1` 读成「已冻结、让位」。
    #   同 `autopilot_fail_handle.py` 对写盘失败返回 2 的口径。
    if r.get("freeze_error"):
        return 3
    return 1 if r.get("stuck") else 0


if __name__ == "__main__":
    sys.exit(main())
