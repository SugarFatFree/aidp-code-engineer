#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""autopilot / aiauto-test 冻结的解冻入口（单一实现）。

子功能：
  · `<reason>`                 前置熔断（`preflight_fail_*` 三件套）的成功路径解冻
  · `--aiauto-probe <V>` / `--aiauto-probe-all`  版本级冻结的解冻证据探针（只判不写）
  · `--env-reprobe <V> [--apply]`  环境类冻结的自动复探（指数退避 + 上限）
  · `--clear <V> --reason <R>`     成功路径显式解冻（仅当 freeze_reason == R）
  · `--manual <V>`                 人工解冻（人工专属类冻结的唯一出口）
  · `--notify-reprobe`             里程碑通知通道复探

## 前置熔断解冻的由来

`preflight_fail_streak` / `preflight_frozen_at` / `preflight_fail_reason` 被**多个作用域**
共用：0.1 自己的 git 类失败（detached-head / git-pull-conflict / …），以及 0.1 **之后**
三个失败点（0.3.1 `prd-root-missing` / 0.4 `stale-active-sprint` / 0.7 `preflight-gate`）。

0.1 每 tick 必跑，故它**只清自己那几个 reason** —— 无条件清会让后三类永远达不到阈值。
后三类由各自的成功路径调用本脚本清除，做成脚本而非内联三段的理由有二：
① 各产生点分片已顶着 20KB 上限，内联放不下；
② 恢复条件的判定要用产生点自己的上下文（PRD_ROOT 路径、REQ 清单），**跨分片取不到** ——
   所以由产生点在自己的成功分支里调用一行，判定权留在有上下文的地方。

## 语义

`autopilot_unfreeze.py <reason>`：**仅当**当前 `preflight_fail_reason` 恰等于 `<reason>` 时
清三件套；不等 / 无冻结 / baseline 不存在一律 no-op 且 exit 0（幂等、绝不误清他人作用域）。
"""
import sys as _aidp_sys
from pathlib import Path as _AidpPath
_aidp_scripts = str(_AidpPath(__file__).resolve().parent)
if _aidp_scripts not in _aidp_sys.path:
    _aidp_sys.path.insert(0, _aidp_scripts)
from aidp_runtime import project_root, runtime_relpath, runtime_text
import argparse
import json
import os
import subprocess
import sys

VALID = {"prd-root-missing", "stale-active-sprint", "preflight-gate"}
KEYS = ["preflight_fail_streak", "preflight_frozen_at", "preflight_fail_reason"]
# ⛔ 顶层 `aiauto_blocked_reason` 也是本门写的（前缀 `frozen:preflight-incomplete@`），不清就永久残留：
#    autopilot Phase 2 的 TEST_LOOP_ALIVE 判据读它，残留会让"测试链路存活"永远判 0。
#    只在它确属本作用域（该前缀）时清，绝不误清别人写的阻塞原因。
BLOCKED_KEY = "aiauto_blocked_reason"
BLOCKED_PREFIX = "frozen:preflight-incomplete@"


def unfreeze(reason, root="."):
    if reason not in VALID:
        return {"ok": False, "error": "unknown-reason", "valid": sorted(VALID)}
    be = os.path.join(root, runtime_relpath("", __file__), "scripts", "baseline_edit.py")
    if not os.path.isfile(be):
        return {"ok": True, "cleared": False, "note": "baseline_edit.py 不存在，no-op"}
    try:
        cur = subprocess.run([sys.executable, be, "get", "preflight_fail_reason", "--default", ""],
                             capture_output=True, text=True, timeout=60, cwd=root)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": True, "cleared": False, "note": f"读取失败，no-op：{exc}"}
    if (cur.stdout or "").strip() != reason:
        return {"ok": True, "cleared": False, "reason_now": (cur.stdout or "").strip(),
                "note": "当前冻结原因不属本作用域，不动"}
    # ★ 逐条接住 del 的返回码。⛔ 丢弃返回码 = 恒报「已解冻」：
    #   del 失败（baseline 被占 / 不可解析）时上游打印「🔓 已解冻」，而冻结字段还在盘上 →
    #   下个 tick 该版本仍被选版剔除 ⇒ **永久冻结 + 假解冻日志**，两者叠加后
    #   看日志完全看不出问题在哪。注意 subprocess 的非零退出不属于
    #   (OSError, SubprocessError)，原来的 except 根本捕不到它。
    _failed = []
    try:
        r0 = subprocess.run([sys.executable, be, "del", *KEYS],
                            capture_output=True, text=True, timeout=60, cwd=root)
        if r0.returncode != 0:
            _failed.append(f"del {' '.join(KEYS)}: rc={r0.returncode} "
                           f"{(r0.stderr or '').strip()[:120]}")
        blk = subprocess.run([sys.executable, be, "get", BLOCKED_KEY, "--default", ""],
                             capture_output=True, text=True, timeout=60, cwd=root)
        _blk = (blk.stdout or "").strip()
        if _blk.startswith(BLOCKED_PREFIX):
            r1 = subprocess.run([sys.executable, be, "del", BLOCKED_KEY],
                                capture_output=True, text=True, timeout=60, cwd=root)
            if r1.returncode != 0:
                _failed.append(f"del {BLOCKED_KEY}: rc={r1.returncode}")
            # ★ 版本级四件套也必须清：只清顶层 preflight_* 会让 `versions.<V>.needs_human=true`
            #    永久残留——运维用 `jq '.versions[]|select(.needs_human==true)'` 巡检会一直看到它，
            #    而该版本其实早已恢复。版本号取自 blocked_reason 的 `@<version>` 后缀。
            _v = _blk.split("@", 1)[1] if "@" in _blk else ""
            if _v and _v != "preflight":
                r2 = subprocess.run(
                    [sys.executable, be, "--version", _v, "del", "needs_human",
                     "aiauto_frozen_at", "freeze_reason", "needs_human_reason"],
                    capture_output=True, text=True, timeout=60, cwd=root)
                if r2.returncode != 0:
                    _failed.append(f"del versions.{_v}.四件套: rc={r2.returncode}")
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": True, "cleared": False, "note": f"清除失败，no-op：{exc}"}
    if _failed:
        return {"ok": True, "cleared": False, "reason": reason,
                "note": "⛔ 部分冻结字段未能清除 —— **本版并未真正解冻**，"
                        "⛔ 别按已解冻处置：" + "；".join(_failed)}
    return {"ok": True, "cleared": True, "reason": reason}


# ── 版本级 aiauto 冻结的解冻探针 ──────────────────────────────────────────────
# 单一信源 = flows/sprint-aiauto-test/rationale.md「冻结分类」表。各类的恢复证据不同：
#   环境类/收敛类 → 冻结后有新部署；配置类 → 配置文件 mtime 晚于冻结；
#   CICD 配置类 → memory/aidp-config.yaml mtime 晚于冻结；交接类 → 仅人工，本探针一律不解冻。
# `chrome-unavailable` 刻意不在部署类：新部署与「机器装好浏览器 / 驱动」无关，
#   它由测试链路驱动检测通过时 `--clear` 显式解冻，或走环境类自动复探。
_UNFREEZE_BY_DEPLOY = {"probe-timeout", "deploy-unreachable",
                       "unconverged", "pipeline-unknown", "cicd-run-vanished",
                       "cicd-unreachable", "cicd-cli-unavailable"}
_UNFREEZE_BY_CONFIG = {"account-missing", "account-invalid", "testplan-incomplete"}
# `cicd-auto-trigger-off`：无人值守下 `cicd.auto_trigger=false` 不许自动触发 / 重试 CICD 流水线。
#   真实修复动作就是改 `memory/aidp-config.yaml`（打开 auto_trigger / 调整 provider·pipelines），
#   故只认该文件 mtime —— ⛔ 不并入 `_UNFREEZE_BY_CONFIG`：测试方案 / 账号文件的改动与它不同域，
#   混用会让「补了个测试账号」把 CICD 配置类冻结一并解掉。
_UNFREEZE_BY_AIDP_CONFIG = {"cicd-auto-trigger-off"}
# ⛔ config-missing 单列「心跳专判」：它是 autopilot 写的「测试链路未挂载」，恢复证据只能是
#   测试链路心跳恢复——补挂第二条 loop **不产生任何文件 mtime 变化**，用 mtime 判会永远解不开。
#   而 prd-missing 恰好相反：它由测试链路自己写，若也认心跳就会被自己每 tick 无条件刷的心跳
#   立刻解冻（冻结永远立不住、两条链路无限震荡），故只认 PRD 目录 mtime。
_UNFREEZE_BY_HEARTBEAT = {"config-missing"}
# ⛔ `preflight-incomplete`（Phase 0.7 前置收口门连续未过）**不进任何自动探针类别**：
#    它的恢复信号只有一个——0.7 收口门本身再次通过，由该成功路径调 `unfreeze("preflight-gate")`
#    显式清除。认「测试链路心跳」会让第二条链路每个周期刷心跳就把它误解冻，而前置配置一个字节没变。
_UNFREEZE_BY_GATE = {"preflight-incomplete"}
_UNFREEZE_BY_PRD = {"prd-missing"}
# ⛔ `unconverged` 虽在 _UNFREEZE_BY_DEPLOY 里，但**自动解冻自我封闭**：冻结后该版本即被
#   剔出部署候选（`/loop` 跳过该版本），于是"新部署"这条证据永远不会出现。而它的真实恢复
#   信号本就不是部署、是**有人推了修复代码**。故补一条 HEAD 变更判据：当前 HEAD ≠ 冻结时
#   autopilot 推到的 HEAD ⇒ 有新提交 ⇒ 具备复测价值。
# `plan-transient` 与 `unconverged` 同构：冻结后该版本被剔出部署候选，"新部署"这条证据
# 永远不会出现；它的真实恢复信号是**有人推了新提交**（修了脚本 / 补了 PRD / 网络恢复后重推）。
_UNFREEZE_BY_HEAD = {"unconverged", "plan-transient"}
# `audit-critical`：累进路径增量审计检出 Critical（C-4/C-5/F/G/H）。归人工解冻类——
# 它要的是「人裁决 + 回对应 SKILL 补齐文档」，没有任何自动信号（部署/心跳/配置 mtime）
# 能证明它已被解决；给它配自动解冻等于让审计结论被下一个 tick 抹掉。
_HUMAN_ONLY = {"handoff-exhausted", "stuck-phase", "release-blocked", "audit-critical"}


def _ts(v):
    from datetime import datetime
    if not v:
        return 0
    try:
        return datetime.fromisoformat(str(v)).timestamp()
    except (ValueError, TypeError):
        return 0


def aiauto_probe(root, version, baseline="memory/.sprint-autopilot-baseline.json"):
    """判定版本级 aiauto 冻结是否已具备解冻证据；返回 {unfreeze, reason, evidence}。"""
    path = os.path.join(root, baseline)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {"unfreeze": False, "note": "baseline 不可读，no-op"}
    vn = ((data.get("versions") or {}).get(version) or {})
    fr = vn.get("freeze_reason") or ""
    if not fr:
        return {"unfreeze": False, "note": "未冻结"}
    if fr in _HUMAN_ONLY:
        return {"unfreeze": False, "reason": fr, "note": "交接类：仅人工，探针一律不解冻"}
    fzt = _ts(vn.get("aiauto_frozen_at"))
    if fr in _UNFREEZE_BY_AIDP_CONFIG:
        cfg = os.path.join(root, "memory", "aidp-config.yaml")
        try:
            if os.path.getmtime(cfg) > fzt:
                return {"unfreeze": True, "reason": fr,
                        "evidence": "memory/aidp-config.yaml 已更新（冻结之后）"}
        except OSError:
            pass
    elif fr in _UNFREEZE_BY_GATE:
        return {"unfreeze": False, "reason": fr,
                "note": "preflight-incomplete 只由 Phase 0.7 收口门通过时显式解冻，探针不判"}
    elif fr in _UNFREEZE_BY_HEARTBEAT:
        hb = data.get("aiauto_test_heartbeat_at")
        if _ts(hb) > fzt:
            return {"unfreeze": True, "reason": fr, "evidence": f"测试链路心跳已恢复（{hb}）"}
    elif fr in _UNFREEZE_BY_PRD:
        import glob
        for f in glob.glob(os.path.join(root, "docs/requirements", version, "产品提供", "*")):
            try:
                if os.path.getmtime(f) > fzt:
                    return {"unfreeze": True, "reason": fr,
                            "evidence": f"PRD 目录已更新（{os.path.relpath(f, root)}）"}
            except OSError:
                continue
    elif fr in _UNFREEZE_BY_DEPLOY:
        dep = vn.get("last_deployed_at")
        if _ts(dep) > fzt:
            return {"unfreeze": True, "reason": fr, "evidence": f"冻结后已有新部署（{dep}）"}
    if fr in _UNFREEZE_BY_HEAD:
        import subprocess
        try:
            cur = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"],
                                 capture_output=True, text=True, timeout=20).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            cur = ""
        # ★ 优先用【冻结时刻的快照】，`last_autopilot_head` 只作兜底。
        #   两个独立缺陷都出在直接拿活指针当快照：
        #   ① `last_autopilot_head` 只在「云端 CICD + 就绪探针通过」那一条路径上被写过，
        #      `local` / `manual-script` / 未配 CICD 的 `git-push` 三条路径下它恒为空 →
        #      `frozen_head` 空即整条判据恒假；而该版一旦 `needs_human` 又会被选版剔除、
        #      再不为它部署，`_UNFREEZE_BY_DEPLOY` 那条也走不通 —— **两条证据同时不可达 = 永久冻结**。
        #   ② 它是**活指针**（每次 push 刷新）不是快照：若冻结前最后一次人工提交早于
        #      autopilot 最后一次 push，`cur != frozen_head` 在冻结瞬间就成立，冻结当场被解掉。
        #   故写冻结契约时一并快照 `unconverged_frozen_head`（与 `retest_frozen_head` 同款）。
        #   ★ `retest_frozen_head` 必须在链里：`retest-cap` 冻结（phase-0-6b 分支①）写的是**它**，
        #     而那条冻结的 freeze_reason 同样是 `unconverged`。漏掉它 → 快照恒取不到 →
        #     只能落到下面的 `code/` mtime 兜底（活指针、跨版本误判），而该版一旦 needs_human
        #     又会被选版剔除、不再为它部署 ⇒ `_UNFREEZE_BY_DEPLOY` 也走不通 = **自锁**。
        frozen_head = (vn.get("unconverged_frozen_head")
                       or vn.get("retest_frozen_head")
                       or vn.get("frozen_head")
                       or data.get("last_autopilot_head")
                       or vn.get("last_autopilot_head") or "")
        if cur and frozen_head and cur != frozen_head:
            return {"unfreeze": True, "reason": fr,
                    "evidence": f"冻结后有新提交（HEAD {cur[:8]} ≠ 冻结时 {frozen_head[:8]}）"}
        if cur and not frozen_head:
            # 快照缺失时**不静默判"不解冻"**——那正是永久冻结的形态。降级为按 mtime 兜底：
            # 冻结之后仓库里有任何 `code/` 改动即视为有人来修过。
            try:
                changed = subprocess.run(
                    ["git", "-C", root, "log", "-1", "--format=%cI", "--", "code/"],
                    capture_output=True, text=True, timeout=20).stdout.strip()
            except (OSError, subprocess.SubprocessError):
                changed = ""
            if _ts(changed) > fzt:
                return {"unfreeze": True, "reason": fr,
                        "evidence": f"冻结快照缺失、按 code/ 最后提交时间兜底判定有人已修（{changed}）"}
    if fr in _UNFREEZE_BY_CONFIG:
        import glob
        # ⛔ 扫描面必须与**写入侧**同源：`/sprint-aiauto-test` Phase 0.0.5 定位测试方案时
        #    `正式用例/` 优先、`研发自测/` 只是兜底。只扫后者的后果是——项目按文档把
        #    「测试环境与账号」放在 `正式用例/` → 冻 testplan-incomplete → 人照 #4 去那里补字段
        #    → `研发自测/*.md` 一字节未变 → 探针恒 {"unfreeze": false} → **永久冻结**。
        #    P2 凭据落点 `memory/.sprint-autopilot-credentials.json` 同理，一并纳入。
        pats = [os.path.join(root, "docs/testing", version, d, "**", "*.md")
                for d in ("正式用例", "测试验收", "测试执行", "研发自测")]
        pats += [os.path.join(root, "docs/testing", version, d, "*.md")
                 for d in ("正式用例", "测试验收", "测试执行", "研发自测")]
        pats += [os.path.join(root, runtime_text('__AIDP_HOME__/skills/*/config.json', __file__)),
                 os.path.join(root, "memory/.sprint-autopilot-credentials.json")]
        for pat in pats:
            for f in glob.glob(pat, recursive=True):
                try:
                    if os.path.getmtime(f) > fzt:
                        return {"unfreeze": True, "reason": fr,
                                "evidence": f"配置已更新（{os.path.relpath(f, root)}）"}
                except OSError:
                    continue
    return {"unfreeze": False, "reason": fr, "note": "尚无恢复证据"}



def aiauto_probe_all(root, baseline="memory/.sprint-autopilot-baseline.json"):
    """对 baseline 里**全部** `needs_human=true` 的版本逐个跑解冻探针（只判不写）。

    ⛔ 补的是一处结构性死角：探针此前只对「本轮选中的那个版本」运行，而 0.3.4 选版时
    **恰恰会把 `needs_human=true` 的版本从候选里剔除** —— 被冻的版本因此永远不是探针的入参。
    Phase 2 写下的三处冻结（作用于 `PRE_RELEASE_VERSION`）于是只在冻结发生的**同一 tick** 内
    有一次机会翻转，之后再不复评：根因（部署恢复、测试收敛、补挂第二条 loop）早就解决了，
    版本仍永久冻着。探针本就只读、幂等、成本极低，遍历一遍没有代价。
    """
    out = {"probed": [], "unfreezable": []}
    try:
        with open(os.path.join(root, baseline), encoding="utf-8") as f:
            bl = json.load(f)
    except Exception as exc:
        out["error"] = str(exc)[:160]
        return out
    for v, vo in sorted((bl.get("versions") or {}).items()):
        if not (isinstance(vo, dict) and vo.get("needs_human")):
            continue
        r = aiauto_probe(root, v, baseline)
        r["version"] = v
        out["probed"].append(r)
        if r.get("unfreeze"):
            out["unfreezable"].append(v)
    return out


def notify_reprobe(root="."):
    """里程碑通知通道的自动复探 —— 冷启动关掉之后唯一能把它重新打开的机制。

    形态：`/loop` 冷启动第一个 tick 发现通知渠道不可用 → 写
    `notify_enabled=false` + `notify_disabled_reason` + `notify_disabled_at` → 静默跳过通知。
    那两个留痕字段就是为"自动复探"而写的；若无读者，通道一旦关掉就永不复开，
    此后**所有 #4 只落 baseline 与本地终端**，而 #4 恰是冻结时刻唯一对外可见的信号：
    外面一片安静，看起来和还在正常跑一模一样。

    判据与其它配置类解冻同构：**配置源 mtime 晚于关闭时刻**即重开。配置源 =
    `memory/aidp-config.yaml`（有人补了 notify.channels / 打开了 notify.enabled）。
    重开只清 `notify_enabled` 三件套，不代替正常的通道检测——下一 tick 照常走正常流程。
    """
    be = os.path.join(os.path.dirname(os.path.abspath(__file__)), "baseline_edit.py")
    bp = os.path.join(root, "memory", ".sprint-autopilot-baseline.json")
    try:
        with open(bp, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return {"reprobed": False, "note": "baseline 不可读"}
    if d.get("notify_enabled") is not False:
        return {"reprobed": False, "note": "通道未被关闭，无需复探"}
    off_at = _ts(d.get("notify_disabled_at"))
    if not off_at:
        # ⛔ 缺关闭时刻就无法比 mtime —— 这正是强调"两个留痕字段必带"的原因。
        return {"reprobed": False, "note": "缺 notify_disabled_at，无法判定（请补写留痕字段）"}
    cfg = os.path.join(root, "memory", "aidp-config.yaml")
    ev = ""
    try:
        if os.path.getmtime(cfg) > off_at:
            ev = "memory/aidp-config.yaml 已更新"
    except OSError:
        pass
    if not ev:
        return {"reprobed": False, "note": "尚无恢复证据（通知配置未变）"}
    errors = []
    for k in ("notify_enabled", "notify_disabled_reason", "notify_disabled_at"):
        # ⛔ 不得丢弃返回码：删失败却照打「🔓 通知通道已重开」= 恒报成功，
        #    而 notify_enabled=false 还在盘上，播报节点继续静默跳过。
        cp = subprocess.run([sys.executable, be, "--baseline", bp, "del", k],
                            capture_output=True, text=True, timeout=60)
        if cp.returncode != 0:
            errors.append("%s: %s" % (k, (cp.stderr or "").strip()[:80]))
    if errors:
        return {"reprobed": False, "note": "通知字段清除失败", "errors": errors}
    return {"reprobed": True, "evidence": ev}


# ── 环境类自动复探 / 显式解冻 / 人工解冻 ──────────────────────────────────────
ENV_ENUM_FILE = os.path.join(runtime_relpath("", __file__), "flows", "sprint-aiauto-test", "rationale.md")
REPROBE_BASE_SECONDS = 20 * 60        # 第 0 次复探：冻结后 20 分钟
REPROBE_MAX_INTERVAL = 4 * 3600       # 单次间隔封顶 4 小时
REPROBE_MAX_ATTEMPTS = 10             # 用尽后转人工（发一次告警）
FREEZE_FIELDS = ["needs_human", "aiauto_frozen_at", "probe_frozen_at", "freeze_reason",
                 "needs_human_reason"]
STREAK_FIELDS = ["dev_fail_streak", "dev_fail_phase", "probe_fail_streak", "push_probe_fail_streak",
                 "prerelease_deploy_block_streak", "prerelease_test_hold_streak", "auto_retest_streak",
                 "test_loop_missing_streak", "cicd_unreachable_streak", "cicd_cli_fail_streak",
                 "aiauto_gate_fail_streak", "env_reprobe_attempts", "env_reprobe_last_at",
                 "env_reprobe_exhausted_at"]


def env_class_reasons(root=None):
    """从冻结枚举权威表解析「解冻类别 = 环境类」的 reason 集合（⛔ 不在调用方手抄 case 列表）。"""
    base = root or str(project_root(__file__))
    p = os.path.join(base, ENV_ENUM_FILE)
    out = set()
    try:
        for ln in open(p, encoding="utf-8").read().splitlines():
            m = __import__("re").match(r"^\|\s*`([a-z][a-z0-9-]{3,})`\s*\|\s*环境类\s*\|", ln)
            if m:
                out.add(m.group(1))
    except OSError:
        pass
    return out


def _be_cmd(root, args):
    be = os.path.join(os.path.dirname(os.path.abspath(__file__)), "baseline_edit.py")
    bp = os.path.join(root, "memory", ".sprint-autopilot-baseline.json")
    return subprocess.run([sys.executable, be, "--baseline", bp] + args,
                          capture_output=True, text=True, timeout=60)


def _load_baseline(root):
    try:
        with open(os.path.join(root, "memory", ".sprint-autopilot-baseline.json"), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def _clear_version(root, version, extra_fields=()):
    """清版本级冻结字段 + 以 `@<version>` 结尾的顶层 aiauto_blocked_reason。返回失败说明列表。"""
    failed = []
    r = _be_cmd(root, ["--version", version, "del", *FREEZE_FIELDS, *extra_fields])
    if r.returncode != 0:
        failed.append("del versions.%s 冻结字段 rc=%s %s" % (version, r.returncode, (r.stderr or "").strip()[:120]))
    d = _load_baseline(root) or {}
    if str(d.get("aiauto_blocked_reason") or "").endswith("@" + version):
        r = _be_cmd(root, ["del", "aiauto_blocked_reason"])
        if r.returncode != 0:
            failed.append("del aiauto_blocked_reason rc=%s" % r.returncode)
    return failed


def env_reprobe(root, version, apply=False, now=None):
    """环境类冻结的自动复探：到期（冻结后 min(20min×2^n, 4h)）即放行一次，最多 10 次。"""
    import time as _t
    now = now if now is not None else _t.time()
    d = _load_baseline(root)
    if d is None:
        return {"reprobe": False, "applied": False, "note": "baseline 不可读"}
    vn = (d.get("versions") or {}).get(version) or {}
    fr = vn.get("freeze_reason") or ""
    out = {"version": version, "reason": fr, "reprobe": False, "applied": False, "exhausted": False}
    if not vn.get("needs_human") or not fr:
        out["note"] = "未冻结"
        return out
    if fr not in env_class_reasons(root if os.path.isfile(os.path.join(root, ENV_ENUM_FILE)) else None):
        out["note"] = "非环境类冻结，不走自动复探"
        return out
    try:
        attempts = int(vn.get("env_reprobe_attempts") or 0)
    except (TypeError, ValueError):
        attempts = 0
    last_at = _ts(vn.get("env_reprobe_last_at"))
    if last_at and _ts(vn.get("last_deployed_at")) > last_at:
        attempts = 0                    # 复探后环境已恢复过（有新部署）→ 退避重新计
    out["attempts"] = attempts
    if attempts >= REPROBE_MAX_ATTEMPTS:
        out["exhausted"] = True
        out["note"] = "自动复探已用尽（%d 次），转人工：`autopilot_unfreeze.py --manual %s`" % (attempts, version)
        if apply and not vn.get("env_reprobe_exhausted_at"):
            _be_cmd(root, ["--version", version, "set", "env_reprobe_exhausted_at", "@now"])
            try:
                sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
                import aidp_paths
                aidp_paths.append_alert(root, kind="env-reprobe-exhausted", version=version,
                                        title="环境类冻结自动复探已用尽：%s" % fr, detail=out["note"])
            except Exception:  # noqa: BLE001
                pass
        return out
    frozen_at = _ts(vn.get("aiauto_frozen_at")) or _ts(vn.get("probe_frozen_at"))
    wait = min(REPROBE_BASE_SECONDS * (2 ** attempts), REPROBE_MAX_INTERVAL)
    due = (frozen_at or now) + wait
    from datetime import datetime as _dt
    out["next_at"] = _dt.fromtimestamp(due).isoformat(timespec="seconds")
    if now < due:
        out["note"] = "未到复探时刻"
        return out
    out["reprobe"] = True
    if apply:
        failed = _clear_version(root, version)
        r = _be_cmd(root, ["--version", version, "set", "env_reprobe_attempts", str(attempts + 1),
                           "env_reprobe_last_at", "@now"])
        if r.returncode != 0:
            failed.append("写 env_reprobe_attempts 失败")
        out["applied"] = not failed
        out["attempts"] = attempts + 1
        if failed:
            out["note"] = "⛔ 放行未完成：" + "；".join(failed)
            out["errors"] = failed        # 供 main 转成非零退出码：写盘失败不得报成功
    return out


def clear_if_reason(root, version, reason):
    """成功路径显式解冻：仅当该版 freeze_reason == reason 时清（幂等）。"""
    vn = ((_load_baseline(root) or {}).get("versions") or {}).get(version) or {}
    if vn.get("freeze_reason") != reason:
        return {"cleared": False, "note": "当前冻结原因不是 %s，不动" % reason,
                "reason_now": vn.get("freeze_reason") or ""}
    failed = _clear_version(root, version)
    return {"cleared": not failed, "reason": reason, "errors": failed}


def manual_unfreeze(root, version):
    """人工解冻：清冻结四件套、复测上限冻结字段、顶层阻塞原因与该版全部失败计数。"""
    vn = ((_load_baseline(root) or {}).get("versions") or {}).get(version)
    if vn is None:
        return {"cleared": False, "note": "baseline 无版本 %s" % version}
    failed = _clear_version(root, version, extra_fields=["needs_human_kind", "retest_cap_frozen_at",
                                                         *STREAK_FIELDS])
    return {"cleared": not failed, "version": version, "was": vn.get("freeze_reason")
            or vn.get("needs_human_kind") or "", "errors": failed}


def main():
    ap = argparse.ArgumentParser(description="autopilot / aiauto-test 冻结解冻入口（幂等）")
    ap.add_argument("reason", nargs="?", default=None,
                    help=f"前置熔断 reason，仅接受：{' / '.join(sorted(VALID))}")
    ap.add_argument("--aiauto-probe", metavar="VERSION", default=None,
                    help="改为判定该版本的 aiauto 冻结是否具备解冻证据（只判不写）")
    ap.add_argument("--aiauto-probe-all", action="store_true",
                    help="对全部 needs_human=true 的版本逐个探测（只判不写）——"
                         "被冻版本会被选版逻辑剔除，不遍历就永远探不到")
    ap.add_argument("--notify-reprobe", action="store_true",
                    help="复探里程碑通知通道：冷启动被关掉后，配置恢复即自动重开")
    ap.add_argument("--env-reprobe", metavar="VERSION", default=None,
                    help="环境类冻结自动复探（指数退避 20min×2^n、封顶 4h、最多 10 次）；配 --apply 才写")
    ap.add_argument("--apply", action="store_true", help="与 --env-reprobe 连用：到期即放行")
    ap.add_argument("--clear", metavar="VERSION", default=None,
                    help="成功路径显式解冻：仅当该版 freeze_reason == --reason 时清")
    ap.add_argument("--reason", dest="clear_reason", default="", help="与 --clear 连用")
    ap.add_argument("--manual", metavar="VERSION", default=None,
                    help="人工解冻：清该版冻结字段、复测上限冻结与全部失败计数")
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if args.env_reprobe:
        r = env_reprobe(args.root, args.env_reprobe, apply=args.apply)
        print(json.dumps(r, ensure_ascii=False) if args.json else
              ("🔓 %s 环境类复探放行（第 %s 次）" % (args.env_reprobe, r.get("attempts"))
               if r.get("applied") else "🔒 %s：%s" % (args.env_reprobe, r.get("note") or "到期可放行（未 --apply）")))
        # 「到期未放行」是正常态（rc=0）；只有**该放行却写盘失败**才是错。
        if r.get("errors"):
            sys.stderr.write("❌ 环境类复探写盘失败：%s\n" % r["errors"])
            return 1
        return 0
    if args.clear:
        if not args.clear_reason:
            sys.stderr.write("❌ --clear 需要 --reason <freeze_reason>\n")
            return 2
        r = clear_if_reason(args.root, args.clear, args.clear_reason)
        print(json.dumps(r, ensure_ascii=False) if args.json else
              ("🔓 %s 已解冻（%s）" % (args.clear, args.clear_reason) if r.get("cleared") else "ℹ️ %s" % r.get("note", r)))
        # ⛔ 写失败必须非零：`errors` 非空 = 冻结字段还在盘上，而上面已经打印了「已解冻」。
        #    丢弃它 = 恒报成功，调用方与人都以为解冻了，下个 tick 照样被冻（本文件开篇的同病）。
        if r.get("errors"):
            sys.stderr.write("❌ 解冻写盘失败：%s\n" % r["errors"])
            return 1
        return 0
    if args.manual:
        r = manual_unfreeze(args.root, args.manual)
        print(json.dumps(r, ensure_ascii=False) if args.json else
              ("🔓 %s 已人工解冻（原冻结：%s）" % (args.manual, r.get("was") or "无") if r.get("cleared")
               else "⛔ %s" % (r.get("note") or r.get("errors"))))
        return 0 if r.get("cleared") or r.get("note") else 1
    if args.notify_reprobe:
        r = notify_reprobe(args.root)
        if args.json:
            print(json.dumps(r, ensure_ascii=False))
        elif r.get("reprobed"):
            print("🔓 里程碑通知通道已重开（%s）" % r["evidence"])
        else:
            print("🔒 里程碑通知保持关闭（%s）" % r.get("note", ""))
        # 「没有恢复证据」是正常态（rc=0）；清字段失败则必须非零，否则恒报「已重开」。
        if r.get("errors"):
            sys.stderr.write("❌ 通知字段清除失败：%s\n" % r["errors"])
            return 1
        return 0
    if args.aiauto_probe_all:
        res = aiauto_probe_all(args.root)
        if args.json:
            print(json.dumps(res, ensure_ascii=False))
        else:
            for r in res.get("probed") or []:
                mark = "🔓 可解冻" if r.get("unfreeze") else "🔒 保持冻结"
                print(f"{mark} {r['version']}（{r.get('evidence') or r.get('note') or r.get('reason')}）")
            if not res.get("probed"):
                print("ℹ️ 无 needs_human=true 的版本")
        return 0

    if args.aiauto_probe:
        res = aiauto_probe(args.root, args.aiauto_probe)
        if args.json:
            print(json.dumps(res, ensure_ascii=False))
        elif res.get("unfreeze"):
            print(f"🔓 {args.aiauto_probe} {res['evidence']} → 可解冻")
        else:
            print(f"🔒 {args.aiauto_probe} 保持冻结（{res.get('note') or res.get('reason')}）")
        return 0
    if not args.reason:
        sys.stderr.write("❌ 需要 reason 参数，或用 --aiauto-probe <VERSION>\n")
        return 2
    res = unfreeze(args.reason, args.root)
    if args.json:
        print(json.dumps(res, ensure_ascii=False))
    elif not res["ok"]:
        sys.stderr.write(f"❌ 未知 reason：{args.reason}（仅接受 {res['valid']}）\n")
    elif res.get("cleared"):
        print(f"✅ 已解冻前置熔断（reason={args.reason}）")
    return 0 if res["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
