#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通用 stuck 熔断：某个 Phase「既不失败也不前进」时把它冻住 —— 两条 loop 共用。

## 为什么要有「通用」这一道

两条链路已各有一堆**按失败模式**的 streak（`dev_fail_streak` / `env_fail_streak` /
`case_gate_fail_streak` / `final_gate_fail_streak` / `aiauto_test_unconverged_streak` …）。
它们各自都对，但覆盖面等于**「有人预想到的失败模式」的并集**。

真正停不下来的是第三种形态：**不报错、也不推进**。它不命中任何一个 streak
（因为那些都要有一次"失败"才记账），于是每个 tick 都干干净净地重跑同一个 Phase，
看起来完全正常 —— 而它可以这样跑到天荒地老。本门就是接这一类的。

## 判据（两条**同时**满足才熔断，缺一都会误伤）

1. `run_state.phase_enter_count >= <enter-threshold>`（默认 8）
2. `run_state.phase_first_entered_at` 距今 > `<age-seconds>`（默认 7200 = 2h）

**只看次数**会误伤「逐 tick 单 Sprint」这类**正常**的同 Phase 多次重入
（`3.2-dev` 本就每 tick 重入，但 `next_sprint` 游标在前移、耗时也远短于 2 小时）；
**只看时长**会误伤长 Sprint。所以是双判据，⛔ 不要为了「更敏感」拆掉任一条。

## 为什么是脚本而不是各分片内联

判据原先以**内联 bash** 存在于开发链路的 `invariants.md`。测试链路需要同一道门时，
照抄一份就意味着两份判据各自演化 —— 而「两套判据各报一份结论、各自都说自己对」
是本仓反复修过的那类缺陷。

⚠️ **分工（⛔ 别把本脚本读成"两条链路都调它"）**：本脚本服务**测试链路**
（`/sprint-aiauto-test` Phase 1），退出码 0/3；**开发链路**（`/sprint-autopilot`
Phase 1.3ter）调的是 `autopilot_stuck_check.py`，退出码 0/1/3（多一档"写盘失败"）。
两份的判据（`phase_enter_count >= 8` 且滞留 > 2h）各有一份 —— 这是**已知的双写面**，
动判据必须同步改两边；两份都已登记进 `check_freeze_contract.GATE_SCRIPT_REASONS`。

## 用法

    python3 {{AIDP_HOME}}/scripts/check_stuck_phase.py --command aiauto-test \\
        --version V0.10.1 --phase 2-exec [--freeze]

退出码：`0` = 未卡住；`3` = **判定卡住**（带 `--freeze` 时已冻结并发 #4）；`2` = 用法/环境错。
不带 `--freeze` 时只判定 + 打印，不产生任何副作用（供巡检/排查）。
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
BE = os.path.join(HERE, "baseline_edit.py")
FAIL_HANDLE = os.path.join(HERE, "autopilot_fail_handle.py")

ENTER_THRESHOLD_DEFAULT = 8
AGE_SECONDS_DEFAULT = 7200


def _be_get(version, dotted, default="", baseline=None):
    cmd = [sys.executable, BE]
    if baseline:
        cmd += ["--baseline", baseline]
    if version:
        cmd += ["--version", version]
    cmd += ["get", dotted, "--default", str(default)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
    except OSError:
        return default
    out = (r.stdout or "").strip()
    return out if out else default


def _to_epoch(s):
    """ISO8601 → epoch 秒。⛔ 别用字符串比较：`+08:00` 与 `Z` 混排会误判。"""
    s = (s or "").strip()
    if not s:
        return None
    try:
        t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return int(t.timestamp())


def evaluate(enter_count, first_entered_at, now_epoch=None,
             enter_threshold=ENTER_THRESHOLD_DEFAULT,
             age_seconds=AGE_SECONDS_DEFAULT):
    """纯函数判定，便于夹具断言。→ {"stuck": bool, "count", "age_seconds", "why"}"""
    now = now_epoch if now_epoch is not None else int(
        datetime.now(timezone.utc).timestamp())
    try:
        cnt = int(enter_count)
    except (TypeError, ValueError):
        cnt = 0
    first = _to_epoch(first_entered_at)
    # ⛔ 取不到首次进入时刻 ⇒ **不熔断**：此刻无法证明"滞留很久"，
    #   而误冻一个正常推进的 Phase 要人工介入才能解，代价远高于多等一个 tick。
    age = None if first is None else max(0, now - first)
    stuck = cnt >= enter_threshold and age is not None and age > age_seconds
    return {"stuck": stuck, "count": cnt, "age_seconds": age,
            "enter_threshold": enter_threshold, "age_threshold": age_seconds,
            "why": ("Phase 连续进入 %d 次、滞留超 %d 分钟且无推进（既不失败也不前进）"
                    % (cnt, (age or 0) // 60)) if stuck else ""}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--command", choices=("autopilot", "aiauto-test"), required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--phase", default="", help="当前 Phase 标识（仅用于告警文案）")
    ap.add_argument("--freeze", action="store_true",
                    help="判定卡住时真的冻结 + 发 #4；缺省只判定不动手")
    ap.add_argument("--enter-threshold", type=int, default=None)
    ap.add_argument("--age-seconds", type=int, default=None)
    ap.add_argument("--baseline", default=None, help="baseline 路径（测试夹具用）")
    # ★ 与 `baseline_edit.py run-state --state-key` 同一组键名：两条 loop 各用自己的游标。
    #   ⛔ 共享会让双方互相把 phase_enter_count 清回 1 ⇒ 两条链路的熔断都永不达阈。
    ap.add_argument("--state-key", default=None,
                    help="状态键名；缺省按 --command 推导（autopilot→run_state，"
                         "aiauto-test→aiauto_run_state）")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    et = a.enter_threshold or int(os.environ.get(
        "STUCK_PHASE_ENTER_THRESHOLD", ENTER_THRESHOLD_DEFAULT))
    ag = a.age_seconds or int(os.environ.get(
        "STUCK_PHASE_AGE_SECONDS", AGE_SECONDS_DEFAULT))

    sk = a.state_key or ("aiauto_run_state" if a.command == "aiauto-test" else "run_state")
    cnt = _be_get(a.version, "%s.phase_enter_count" % sk, 1, a.baseline)
    first = _be_get(a.version, "%s.phase_first_entered_at" % sk, "", a.baseline)
    recorded = _be_get(a.version, "%s.current_phase" % sk, "", a.baseline)
    cur = a.phase or recorded
    # ★ 调用方声明的 phase 与状态里记着的不一致 ⇒ 这份计数**不是本 Phase 的**，判它等于乱判。
    #   ⛔ 此时必须出声而不是沉默放行：沉默会让「判了对面链路的 phase」与「真的没卡住」同形。
    if a.phase and recorded and a.phase != recorded:
        msg = ("⚠️ %s.current_phase 记的是 `%s`，而本次 --phase 是 `%s` —— 计数不属本 Phase，"
               "判定按【不卡住】返回但**不可据此断言健康**；先查 run-state 写入点是否串键"
               % (sk, recorded, a.phase))
        if a.json:
            print(json.dumps({"stuck": False, "applicable": False, "reason": msg,
                              "state_key": sk, "recorded_phase": recorded,
                              "asked_phase": a.phase}, ensure_ascii=False, indent=2))
        else:
            print(msg)
        return 0
    res = evaluate(cnt, first, enter_threshold=et, age_seconds=ag)
    res.update(command=a.command, version=a.version, phase=cur, state_key=sk,
               first_entered_at=first, froze=False)

    if res["stuck"] and a.freeze:
        # 判据不是 streak（是「次数 + 滞留时长」双条件）⇒ 用 --freeze-now：
        # 冻结四件套 + #4 一次做完。⛔ 别给它塞一个 streak 字段，
        #   运维巡检会看到一串永不清零的假计数、而真判据根本不在那里。
        try:
            cmd = [sys.executable, FAIL_HANDLE]
            if a.baseline:
                cmd += ["--baseline", a.baseline]
            cmd += ["--version", a.version, "--freeze-now",
                    "--command", a.command, "--phase", cur or "unknown",
                    "--reason", "stuck-phase", "--why", res["why"]]
            r = subprocess.run(cmd, capture_output=True, text=True)
            res["froze"] = r.returncode in (0, 3)
            if not res["froze"]:
                res["freeze_error"] = (r.stderr or "").strip()[:200]
        except OSError as exc:
            res["freeze_error"] = str(exc)

    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    elif res["stuck"]:
        print("⛔ 通用 stuck 熔断：Phase %s 连续 %d tick 原地打转（首次进入 %s）%s"
              % (cur or "?", res["count"], first or "未记录",
                 "→ 已冻结并发 #4" if res["froze"] else "（未带 --freeze，仅判定）"))
    else:
        print("✅ 未卡住（进入 %d 次 / 阈值 %d；滞留 %s 秒 / 阈值 %d）"
              % (res["count"], et,
                 "未记录" if res["age_seconds"] is None else res["age_seconds"], ag))
    return 3 if res["stuck"] else 0


def _self_check():
    now = 1_000_000_000
    def iso(off):
        return datetime.fromtimestamp(now - off, timezone.utc).isoformat()
    ok = [
        ("两条都满足 → 熔断",
         evaluate(8, iso(7300), now)["stuck"] is True),
        ("★ 只够次数、滞留不够 → ⛔ 不熔断（否则误伤逐 tick 单 Sprint 的正常重入）",
         evaluate(20, iso(600), now)["stuck"] is False),
        ("★ 只够滞留、次数不够 → ⛔ 不熔断（否则误伤长 Sprint）",
         evaluate(2, iso(99999), now)["stuck"] is False),
        ("恰好等于次数阈值且超时 → 熔断（阈值取 >=）",
         evaluate(8, iso(7201), now)["stuck"] is True),
        ("恰好等于时长阈值 → ⛔ 不熔断（取严格 >）",
         evaluate(8, iso(7200), now)["stuck"] is False),
        ("★ 取不到首次进入时刻 → ⛔ 不熔断（证不出滞留，误冻要人工解）",
         evaluate(99, "", now)["stuck"] is False),
        ("★ 首次进入时刻不可解析 → ⛔ 不熔断",
         evaluate(99, "昨天下午", now)["stuck"] is False),
        ("计数非数值按 0 处理 → ⛔ 不熔断",
         evaluate("多次", iso(99999), now)["stuck"] is False),
        ("★ 时区混排不误判（+08:00 与 Z 同一时刻）",
         _to_epoch("2026-10-09T12:00:00+08:00") == _to_epoch("2026-10-09T04:00:00Z")),
        ("自定义阈值生效",
         evaluate(3, iso(100), now, enter_threshold=2, age_seconds=50)["stuck"] is True),
    ]
    for n, r in ok:
        print(("  ✅ " if r else "  ❌ FAIL: ") + n)
    return 0 if all(r for _, r in ok) else 1


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        raise SystemExit(_self_check())
    raise SystemExit(main())
