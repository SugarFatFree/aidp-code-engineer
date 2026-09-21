#!/usr/bin/env python3
"""autopilot_fail_handle.py — 「失败处置」一次调用做完：记账 → 判阈 → 冻结四件套 → 发 #4。

## 为什么要有这个脚本

`/sprint-autopilot` 与 `/sprint-aiauto-test` 的「失败处置」是一套固定动作：

    bump <streak> → 判阈 → 达阈则写冻结四件套 + 顶层 aiauto_blocked_reason → 发 #4 + 本地告警 → 让位

收进一个调用后，「只写散文不记账」「冻了不发通知」「无唤醒源时阈值恒不可达」三类漏抄
在结构上不可能发生：要么整件事没做，要么全做了。

## 用法

    python3 AIDP_HOME/scripts/autopilot_fail_handle.py \\
      --version V0.1.0 --phase 3.2.1-deploy --reason deploy-unreachable \\
      --why "就绪探针连续超时，疑似环境未就绪" \\
      [--command autopilot|aiauto-test] \\
      [--build V0.1.0_build1002] [--streak-key dev_fail_streak] [--threshold 3] \\
      [--freeze-now] [--extra KEY=VALUE]... \\
      [--title "部署受阻"] [--section "<通知正文>"] [--no-card] [--card-on-streak] [--json]

`--command`：调用方所在链路。唤醒源键按链路取（`autopilot.wake_source_this_tick` /
`aiauto.wake_source_this_tick`）；`--preflight` 的计数键也按链路分开（测试链路为 `aiauto_preflight_*`）。
⛔ 测试链路必须传 `--command aiauto-test`，否则读到开发链路的唤醒源、首次失败即冻结。

通知：**达阈冻结**时发 #4（`notify.py --node #4`，无论送达与否都写本地告警台账
`memory/.aidp/alerts.jsonl`）；未达阈只记账、不发通知（避免正常重试期间每 tick 一张红卡），
需要逐次通知时显式 `--card-on-streak`。

幂等：同一版本已按**同一 reason** 冻结 → 不重复写、不刷新 `aiauto_frozen_at`、不重发 #4，返回 3。

`--freeze-now` = 判据不是 streak 的冻结点（stuck-phase 的「次数 + 滞留时长」双条件、
审计 Critical 的一次即冻等）：跳过 bump 与判阈直接冻结，**不写 streak 字段**——
给这类点硬塞一个 streak，运维巡检看到的是一串永不清零、也不是真判据的假计数。
`--extra` 用于冻结时一并写入的版本级附加字段（如 `unconverged_frozen_head=<sha>`），
可重复；⛔ 必须与四件套同批写入，分两次写会留下"冻了但解冻判据缺失"的中间态。

`--reason` 必须在「冻结字段写入契约」的枚举内（与 `check_freeze_contract.py` 同源，
从 `flows/sprint-autopilot/rationale.md` 的权威表实时解析，⛔ 不在本脚本里再写一份）。

## 退出码

  0 = 已记账（未达阈，让位本 tick）
  3 = 已冻结（达阈 / 无唤醒源 / 该版已按同一 reason 冻结）—— 调用方据此决定是否终止本版后续步骤
  2 = 用法/环境错（枚举非法、取不到版本号等）；⛔ 此时**什么都没写**，不要当成"处置过了"
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
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BE = os.path.join(HERE, "baseline_edit.py")
CARD = os.path.join(HERE, "notify.py")
# ⛔ 枚举与标记一律**复用 check_freeze_contract 的常量**，不在本脚本另写一份 ——
#   两份各自维护必然漂移，而漂移方向是"这里认得、那道门不认得"，静默通过。
sys.path.insert(0, HERE)


def _be(args):
    return subprocess.run([sys.executable, BE] + args, capture_output=True, text=True)


WAKE_KEY = {"autopilot": "autopilot.wake_source_this_tick",
            "aiauto-test": "aiauto.wake_source_this_tick"}
PREFLIGHT_KEYS = {
    "autopilot": ("preflight_fail_streak", "preflight_frozen_at", "preflight_fail_reason"),
    "aiauto-test": ("aiauto_preflight_fail_streak", "aiauto_preflight_frozen_at",
                    "aiauto_preflight_fail_reason"),
}
# 恢复指引按解冻类别给出（类别单一信源 = autopilot_unfreeze.py）
_UNFREEZE = runtime_text('python3 __AIDP_HOME__/scripts/autopilot_unfreeze.py', __file__)


def _recovery_hint(reason, version):
    try:
        import autopilot_unfreeze as _u
        env = _u.env_class_reasons()
        human = _u._HUMAN_ONLY
    except Exception:  # noqa: BLE001
        env, human = set(), set()
    if reason in human:
        return ("恢复：人工处理根因后运行 `%s --manual %s`，下个 tick 自动继续。" % (_UNFREEZE, version))
    if reason in env:
        return ("恢复：环境类，链路按退避自动复探（`%s --env-reprobe %s`）；"
                "修好环境后也可直接 `%s --manual %s`。" % (_UNFREEZE, version, _UNFREEZE, version))
    return ("恢复：修复根因（配置 / 代码 / 部署）后链路按解冻证据自动放行；"
            "需立即放行可运行 `%s --manual %s`。" % (_UNFREEZE, version))


def _alert(kind, **fields):
    try:
        import aidp_paths
        aidp_paths.append_alert(".", kind=kind, **fields)
    except Exception:  # noqa: BLE001 —— 告警台账是旁路
        sys.stderr.write("🚨 [AIDP-ALERT] %s %s\n" % (kind, fields))


def _send_card(cmd):
    """发 #4；返回 (sent, skipped_reason, err)。notify 自身负责写本地告警台账。"""
    cr = subprocess.run(cmd, capture_output=True, text=True)
    if cr.returncode == 0:
        return True, None, None
    if cr.returncode == 3:
        return False, "not-configured", None
    return False, None, (cr.stderr or "").strip()[:160]


def _enum():
    """合法 freeze_reason 集合 —— **直接调 check_freeze_contract 的解析器**，同一信源。

    取不到时返回空集。此时**仍照常记账 + 发 #4**（拒绝记账会制造新的静默停摆），
    但 `run()` 会**拒绝写冻结四件套**并大声报错 —— 一个拼错的 reason 写进 `freeze_reason`
    与 `aiauto_blocked_reason` 后，落不进 `_UNFREEZE_BY_*` 任何一类、探针永远返回
    「尚无恢复证据」⇒ **永久冻结**，而 rc=3 会让调用方以为处置正常。放掉「拒绝记账」是对的，
    连「拒绝写一个非法 reason」一起放掉不是。
    """
    try:
        import check_freeze_contract as _cfc
        fn = getattr(_cfc, "parse_enum", None) or getattr(_cfc, "_parse_enum", None) \
            or getattr(_cfc, "load_enum", None)
        if fn is None:
            return set()
        vals = fn(os.path.join(HERE, "..", ".."))
        if isinstance(vals, tuple):
            vals = vals[0]
        return set(vals or ())
    except Exception:
        return set()


def run(a):
    out = {"version": a.version, "phase": a.phase, "reason": a.reason,
           "frozen": False, "streak": None, "card_sent": False, "errors": []}
    enum = _enum()
    out["enum_ok"] = bool(enum)
    if enum and a.reason not in enum:
        out["errors"].append("freeze_reason `%s` 不在契约枚举内（合法值：%s）"
                             % (a.reason, "|".join(sorted(enum))))
        return 2, out
    if not enum:
        # 解析不到枚举 = 无法证明 reason 合法。记账与 #4 照做，冻结四件套**不写**。
        sys.stderr.write(
            "⛔ 取不到 freeze_reason 契约枚举（rationale 权威表被改格式 / "
            "check_freeze_contract 解析函数被改名）—— 本次**不写冻结四件套**，只记账 + 发 #4。\n"
            "   写一个未经校验的 reason 会落不进任何解冻分支 ⇒ 永久冻结，且 rc=3 让调用方以为一切正常。\n")

    vargs = ["--version", a.version] + (["--build", a.build] if a.build else [])

    # 幂等：同版本已按同一 reason 冻结 → no-op（不刷新冻结时刻，解冻判据不被后移；不重发 #4）
    cur_nh = (_be(["--version", a.version, "get", "needs_human", "--default", ""]).stdout or "").strip()
    cur_fr = (_be(["--version", a.version, "get", "freeze_reason", "--default", ""]).stdout or "").strip()
    if cur_nh.lower() == "true" and cur_fr == a.reason:
        out.update(frozen=True, already_frozen=True)
        return 3, out

    # ★ --freeze-now = 「熔断条件已由调用方判定成立，直接冻」——用于判据不是 streak 的冻结点
    #   （如 stuck-phase 的「进入次数 + 滞留时长」双条件、审计 Critical 的一次即冻）。
    #   ⛔ 此时**不得 bump**：给这类点硬塞一个 streak 字段，运维巡检会看到一串永不清零的
    #   假计数，而真正的判据根本不在那里。
    if a.freeze_now:
        streak = 0
        out["streak"] = None
        out["has_wake_source"] = None
        freeze = True
    else:
        r = _be(vargs + ["bump", a.streak_key])
        if r.returncode != 0:
            out["errors"].append("bump %s 失败：%s" % (a.streak_key, (r.stderr or "").strip()[:160]))
            return 2, out
        try:
            streak = int((r.stdout or "0").strip() or 0)
        except ValueError:
            streak = 0
        out["streak"] = streak

        # ★ 无唤醒源（`--once` / 无 /loop）时没有下一 tick 来叠 streak ⇒ 阈值恒不可达。
        #   故它与「已达阈」等价处置：宁可早冻一轮让人看见，也不要静默退出让上游以为跑过了。
        wake = (_be(["get", WAKE_KEY[a.command], "--default", "0"]).stdout or "0").strip()
        out["has_wake_source"] = wake
        freeze = streak >= a.threshold or wake == "0"

    if freeze and not enum:
        out["errors"].append("枚举不可解析 —— 已跳过冻结四件套写入（见 stderr）")
        freeze = False
        out["freeze_suppressed"] = True
    if freeze:
        extra = []
        for kv in a.extra:
            if "=" not in kv:
                out["errors"].append("--extra 需 KEY=VALUE 形式，已忽略：%s" % kv)
                continue
            k, v = kv.split("=", 1)
            extra += [k, v]
        # ★ 必须逐个检查写盘返回码。⛔ 丢弃返回码 = 「通知说冻了、盘上没冻」：
        #   baseline 不可解析 / 磁盘满 / 锁异常时 baseline_edit 非零退出，四件套一个字段
        #   都没落盘，而本函数照样置 frozen=True、返回 3、发出「已冻结本版待人工」的 #4。
        #   下个 tick 该版本 needs_human 为空 → 照常入选 → 重跑同一失败 Phase →
        #   每 10 分钟发一张「已冻结」卡而实际从未冻结。这是假绿的镜像形态：
        #   假红报告 + 真实空转，且比假绿更难察觉——通知里看着一切都在"正常告警"。
        writes = [
            _be(["--version", a.version, "set",
                 "needs_human", "true", "aiauto_frozen_at", "@now",
                 "freeze_reason", a.reason, "needs_human_reason", a.why] + extra),
            _be(["set", "aiauto_blocked_reason", "frozen:%s@%s" % (a.reason, a.version)]),
            _be(["--version", a.version, "set", "dev_fail_phase", a.phase]),
        ]
        bad = [w for w in writes if getattr(w, "returncode", 1) != 0]
        if bad:
            for w in bad:
                out["errors"].append(
                    "冻结写盘失败：rc=%s %s" % (w.returncode,
                                           ((w.stderr or w.stdout or "").strip()[:200])))
            out["frozen"] = False
            out["freeze_write_failed"] = True
            sys.stderr.write(
                "⛔ 冻结四件套未能落盘（见 errors）——**本版并未真正冻结**，"
                "⛔ 不要按「已冻结」处置：修好 baseline 可写性后重跑本命令。\n")
            return 2, out          # 2 = 入参/环境错，与其余脚本同口径
        out["frozen"] = True
    else:
        _be(["--version", a.version, "set", "dev_fail_phase", a.phase])

    title = a.title or ("已冻结：%s" % a.reason if freeze else "阶段失败：%s" % a.phase)
    if a.freeze_now:
        section = a.section or ("%s（%s，熔断条件已成立）已冻结本版。" % (a.why, a.phase))
    else:
        section = a.section or ("%s（%s 第 %d 次，阈值 %d）%s"
                                % (a.why, a.phase, streak, a.threshold,
                                   "已冻结本版。" if freeze else "已记账，让位本 tick。"))
    if freeze:
        section += "\n" + _recovery_hint(a.reason, a.version)
    want_card = (freeze or a.card_on_streak) and not a.no_card and os.path.isfile(CARD)
    if want_card:
        cmd = [sys.executable, CARD, "--node", "#4", "--auto",
               "--header-color", "red", "--title", title,
               "--version", a.version, "--section", section]
        if a.build:
            cmd += ["--build", a.build]
        sent, skipped, err = _send_card(cmd)
        out["card_sent"] = sent
        if skipped:
            out["card_skipped"] = skipped
        if err:
            out["errors"].append("发 #4 失败（不阻断处置）：%s" % err)
    elif freeze:
        # 不发通知时（--no-card / notify 缺失）冻结仍必须「停得响」：直接写本地告警台账
        _alert("freeze", version=a.version, build=a.build or None, title=title, detail=section)
    return (3 if freeze else 0), out


def _preflight(a):
    """前置熔断：无版本号的顶层失败处置（记账 → 判阈 → 冻结 → 发 #4）。

    与主路径的唯一差别是落点在 baseline 顶层（开发链路 `preflight_*` / 测试链路 `aiauto_preflight_*`）
    而非版本节点 —— 此时 TARGET_VERSION 还没解析出来，冻的是该链路的**所有版本**。
    """
    import json as _j
    k_streak, k_frozen, k_reason = PREFLIGHT_KEYS[a.command]
    out = {"mode": "preflight", "command": a.command, "reason": a.reason, "errors": []}
    r = _be(["bump", k_streak])
    if r.returncode != 0:
        sys.stderr.write("⛔ %s 自增失败，未做任何处置\n" % k_streak)
        return 2
    try:
        streak = int((r.stdout or "0").strip() or 0)
    except ValueError:
        streak = 0
    _be(["set", k_reason, a.reason])
    freeze = streak >= a.threshold
    if freeze:
        w = _be(["set", k_frozen, "@now"])
        if w.returncode != 0:
            out["errors"].append("%s 写盘失败：%s" % (k_frozen, (w.stderr or "").strip()[:200]))
            sys.stderr.write("⛔ 熔断标记未能落盘 —— **本次并未真正熔断**，⛔ 别按已熔断处置\n")
            if a.json:
                print(_j.dumps(out, ensure_ascii=False))
            return 2
    out.update(streak=streak, frozen=freeze)
    title = ("前置熔断待人工：%s" % a.reason) if freeze else ("前置受阻：%s" % a.reason)
    tail = (runtime_text('已熔断，此后每 tick 静默退出；人工修复后运行 `python3 __AIDP_HOME__/scripts/baseline_edit.py del %s %s %s` 恢复。', __file__) % (k_streak, k_frozen, k_reason)
            if freeze else "修复后自动恢复。")
    section = "%s（连续第 %d 次，阈值 %d）%s" % (a.why, streak, a.threshold, tail)
    if (freeze or a.card_on_streak) and not a.no_card and os.path.isfile(CARD):
        # ⛔ **preflight 模式下必须去掉 `--node`**：本门跑在版本解析之前，`a.version` 结构上恒空，
        #   而 `notify.py` 对「给了 `--node #N` 却缺 `--version`」是**发送前** fail-closed
        #   （台账侧 --version 必填）——硬带 `--node` 的净效果是整条通知一个字节都发不出去，
        #   与只 echo「发 #4 通知」完全同形。不登台账总好过不发通知。
        cmd = [sys.executable, CARD, "--auto", "--alert",
               "--header-color", "red", "--title", title, "--section", section]
        if (getattr(a, "version", "") or "").strip():
            cmd[2:2] = ["--node", "#4", "--version", a.version]
        sent, skipped, err = _send_card(cmd)
        out["card_sent"] = sent
        if skipped:
            out["card_skipped"] = skipped
        if err:
            out["errors"].append("发 #4 失败（不阻断处置）：%s" % err)
    elif freeze:
        _alert("preflight-freeze", title=title, detail=section)
    if a.json:
        print(_j.dumps(out, ensure_ascii=False))
    else:
        print(("⏸️ 前置失败已熔断待人工（%s，连续 %d 次 ≥ %d）" % (a.reason, streak, a.threshold))
              if freeze else
              ("⛔ 前置失败（%s）第 %d 次：%s → 已记账，退本 tick" % (a.reason, streak, a.why)))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="autopilot / aiauto-test 失败处置：记账 → 判阈 → 冻结 → 发 #4 + 本地告警")
    ap.add_argument("--version", default="")
    ap.add_argument("--command", choices=("autopilot", "aiauto-test"), default="autopilot",
                    help="调用方链路：决定唤醒源键与前置熔断计数键（测试链路必须传 aiauto-test）")
    ap.add_argument("--phase", default="", help="失败发生的 Phase 游标，如 3.2.1-deploy")
    # preflight 模式：前置熔断发生在 TARGET_VERSION 解析之前，拿不到版本号，
    #   故不走版本级四件套；「记账 → 判阈 → 冻结 → 发 #4」这套动作与主路径相同，⛔ 不在 flow 里另写一份。
    ap.add_argument("--preflight", action="store_true",
                    help="前置熔断模式（无版本号）：记 preflight_* / aiauto_preflight_*（按 --command）")
    ap.add_argument("--reason", default="", help="freeze_reason（须在契约枚举内）")
    ap.add_argument("--why", default="", help="写进 needs_human_reason 的真因，⛔ 别写「失败了」")
    ap.add_argument("--build", default="")
    ap.add_argument("--streak-key", default="dev_fail_streak")
    ap.add_argument("--threshold", type=int, default=3)
    ap.add_argument("--title", default="")
    ap.add_argument("--section", default="")
    ap.add_argument("--freeze-now", action="store_true",
                    help="熔断条件已由调用方判定成立 → 跳过 bump/判阈直接冻结（不写 streak）")
    ap.add_argument("--extra", action="append", default=[], metavar="KEY=VALUE",
                    help="冻结时一并写入的版本级附加字段，可重复（如 unconverged_frozen_head=<sha>）")
    ap.add_argument("--no-card", action="store_true", help="不发 #4（冻结时仍写本地告警台账）")
    ap.add_argument("--card-on-streak", action="store_true",
                    help="未达阈也发 #4（默认只在冻结时发）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-check", action="store_true")
    a = ap.parse_args(argv)
    if a.self_check:
        return _self_check()
    for k in ("reason", "why"):
        if not (getattr(a, k) or "").strip():
            sys.stderr.write(f"⛔ --{k} 必填\n")
            return 2
    if a.preflight:
        return _preflight(a)
    for k in ("version", "phase"):
        if not (getattr(a, k) or "").strip():
            sys.stderr.write(f"⛔ --{k} 必填（非 --preflight 模式）\n")
            return 2
    rc, out = run(a)
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        for e in out["errors"]:
            sys.stderr.write("⚠️ %s\n" % e)
        if rc == 2:
            sys.stderr.write("⛔ 入参/环境错 —— **什么都没写**，不要当成已处置\n")
        elif out.get("already_frozen"):
            print("⏸️ %s 已按 %s 冻结（未重复写入、未重发 #4）" % (a.version, a.reason))
        elif out["frozen"]:
            print("⏸️ 已冻结 %s（%s，%s）%s"
                  % (a.version, a.reason,
                     "熔断条件已成立" if a.freeze_now
                     else "streak=%s，唤醒源=%s" % (out["streak"], out.get("has_wake_source")),
                     "，#4 已发" if out["card_sent"]
                     else runtime_text('，#4 未送达（已写本地告警台账 memory/.aidp/alerts.jsonl）', __file__)))
        else:
            print("⛔ %s 失败第 %s 次（阈值 %d）→ 已记账%s，让位本 tick"
                  % (a.phase, out["streak"], a.threshold, " + 发 #4" if out["card_sent"] else ""))
    return rc


def _self_check():
    """离线双侧对照：临时目录内造 baseline，验证链路分键 / 幂等 / 未达阈不发通知 / 冻结写告警台账。"""
    import tempfile
    import shutil
    ok = []
    cwd = os.getcwd()
    d = tempfile.mkdtemp()
    saved = {k: os.environ.pop(k, None) for k in ("AIDP_AGENT_EXEC",)}
    try:
        os.chdir(d)
        os.makedirs("memory")
        bl = os.path.join("memory", ".sprint-autopilot-baseline.json")
        with open(bl, "w", encoding="utf-8") as fh:
            json.dump({"aiauto": {"wake_source_this_tick": "1"},
                       "autopilot": {"wake_source_this_tick": "0"},
                       "versions": {"V9.9.9": {}}}, fh)

        def call(*extra):
            import io
            from contextlib import redirect_stdout, redirect_stderr
            buf = io.StringIO()
            with redirect_stdout(buf), redirect_stderr(io.StringIO()):
                rc = main(["--version", "V9.9.9", "--phase", "0.1", "--reason", "probe-timeout",
                           "--why", "自检", "--json", *extra])
            return rc, json.loads(buf.getvalue() or "{}")

        rc, o = call("--command", "aiauto-test")
        ok.append(("★ 测试链路读 aiauto 唤醒源：首次失败只记账不冻结", rc == 0 and o.get("has_wake_source") == "1"))
        ok.append(("★ 未达阈默认不发 #4", o.get("card_sent") is False and not os.path.isfile(runtime_text('memory/.aidp/alerts.jsonl', __file__))))
        rc, o = call()
        ok.append(("阳性对照：开发链路无唤醒源 → 当场冻结", rc == 3 and o.get("frozen") is True))
        ok.append(("★ 冻结恒写本地告警台账", os.path.isfile(runtime_text('memory/.aidp/alerts.jsonl', __file__))))
        with open(bl, encoding="utf-8") as fh:
            at1 = json.load(fh)["versions"]["V9.9.9"].get("aiauto_frozen_at")
        rc, o = call()
        with open(bl, encoding="utf-8") as fh:
            at2 = json.load(fh)["versions"]["V9.9.9"].get("aiauto_frozen_at")
        ok.append(("★ 同 reason 已冻结 → no-op（不刷新冻结时刻）", rc == 3 and o.get("already_frozen") and at1 == at2))
    except Exception as exc:  # noqa: BLE001
        ok.append(("自检执行异常：%s" % exc, False))
    finally:
        os.chdir(cwd)
        shutil.rmtree(d, ignore_errors=True)
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v
    for name, r in ok:
        print(("  ✅ " if r else "  ❌ FAIL: ") + name)
    return 0 if ok and all(r for _, r in ok) else 1


if __name__ == "__main__":
    sys.exit(main())
