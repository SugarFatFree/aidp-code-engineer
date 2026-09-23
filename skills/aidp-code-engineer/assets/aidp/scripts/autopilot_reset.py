#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""autopilot_reset.py —— `/sprint-autopilot` `--reset-*` 旗标的唯一执行者。

## 为什么需要它

这些旗标在命令参数表里定义、在冻结 #4 里程碑通知正文里被写成"人工恢复动作"（`--reset-baseline`
更被 `invariants.md` 称作某类冻结的**唯一出路**），却一直**没有任何实现**：
`BOOL_FLAGS` 里一个都没登记，全仓也搜不到对应变量。用户照通知操作，跑的是空气。

本脚本把它们落地。由 `phase-0-0` 在读 baseline **之前**调用一次：命中任一 reset 就执行
并退出本 tick（`--reset-baseline` 语义就是"删掉后退出"），其余 reset 执行完继续本 tick。

## 退出码

  0 = 未命中任何 reset（调用方继续正常流程）
  10 = 已执行 reset 且**应当结束本 tick**（--reset-baseline）
  11 = 已执行 reset，调用方继续本 tick（其余旗标）
  2 = 入参错
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BE = os.path.join(HERE, "baseline_edit.py")
DEFAULT_BASELINE = os.path.join("memory", ".sprint-autopilot-baseline.json")

# 旗标 → (要删的 baseline 键, 是否结束本 tick)
RESETS = {
    "--reset-baseline": (None, True),
    "--reset-unattended": (["autopilot.unattended_confirmed",
                            "autopilot.unattended_confirmed_at"], False),
}


def _be(baseline, *args):
    return subprocess.run([sys.executable, BE, "--baseline", baseline] + list(args),
                          capture_output=True, text=True)


def run(baseline, tokens):
    hit = [f for f in RESETS if f in tokens]
    out = {"hit": hit, "done": [], "errors": [], "end_tick": False}
    if not hit:
        return 0, out
    for f in hit:
        keys, end = RESETS[f]
        if keys is None:
            # --reset-baseline：整份删除。⛔ 不是清空成 `{}` —— 留一个空壳会让各处
            #   "baseline 不存在"的早退分支失效，反而进入一堆读空值的路径。
            try:
                if os.path.exists(baseline):
                    os.remove(baseline)
                out["done"].append(f + "（baseline 文件已删除）")
            except OSError as exc:
                out["errors"].append("%s 失败：%s" % (f, exc))
                continue
        else:
            for k in keys:
                r = _be(baseline, "del", k)
                if r.returncode != 0:
                    out["errors"].append("%s: del %s 失败（%s）"
                                         % (f, k, (r.stderr or "").strip()[:120]))
            out["done"].append("%s（已清 %s）" % (f, "/".join(keys)))
        out["end_tick"] = out["end_tick"] or end
    if out["errors"]:
        return 2, out
    return (10 if out["end_tick"] else 11), out


def main():
    ap = argparse.ArgumentParser(description="执行 /sprint-autopilot 的 --reset-* 旗标")
    ap.add_argument("--arguments", default="", help="本轮 $ARGUMENTS 原文")
    ap.add_argument("--baseline", default=DEFAULT_BASELINE)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-check", action="store_true")
    a = ap.parse_args()
    if a.self_check:
        sys.path.insert(0, HERE)
        from selfcheck import run_self_check
        sys.exit(run_self_check(os.path.basename(__file__), json_out=a.json))
    rc, out = run(a.baseline, (a.arguments or "").split())
    if a.json:
        print(json.dumps(out, ensure_ascii=False))
    elif rc == 0:
        print("[reset] 本轮无 --reset-* 旗标")
    else:
        for d in out["done"]:
            print("♻️ " + d)
        for e in out["errors"]:
            print("⛔ " + e, file=sys.stderr)
        if out["end_tick"]:
            print("→ baseline 已重置，本 tick 到此结束（下次任意 PRD 变化即触发）")
    return rc


if __name__ == "__main__":
    sys.exit(main())
