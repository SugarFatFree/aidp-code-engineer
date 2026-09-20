#!/usr/bin/env python3
"""autopilot-stop-guard.py — Stop hook：autopilot 执行态下「收尾门没过不许结束」的结构级兜底。

背景：/sprint-autopilot 的「命令收尾硬门」是 prose + 脚本，但轮次是否真跑到收尾仍依赖执行体自律。
本 Stop hook 把「收尾门没过就不结束」提为结构级——它在 Agent 试图结束轮次时触发，检测到
「autopilot 正处执行态且收尾门 exit 1（仪式产物缺失）」→ 返回 exit 2 阻止结束、迫使继续补产。

⛔⛔ 作用域：**只拦「本会话 / 本进程正在执行 `/sprint-autopilot` tick」的轮次**。判据（任一）：
  · 环境变量 `AIDP_TICK_COMMAND=sprint-autopilot`（由 agent_loop.sh / aidp_scheduler.py 注入）；
  · Stop 输入的 transcript 中最后一条用户输入是 `sprint-autopilot` 命令调用
    （Claude Code / DeepSeek Harness 为 `/sprint-autopilot`，Codex 为 `$sprint-autopilot`，含 `/loop … /sprint-autopilot`）。
  测试链路（`AIDP_TICK_COMMAND=sprint-aiauto-test`）与人的普通对话一律放行——仓库级 baseline 新鲜度
  不能区分「谁的轮次」，双链路下它恒新鲜。

安全第一（本 hook 全局每轮触发，绝不能误 wedge 正常对话）——多重 fail-open：
  1. 关闭开关：存在 memory/.autopilot-stop-guard-off → 立即 exit 0（用户临时禁用逃生舱）。
  2. 非 autopilot tick 轮次 / baseline 缺失 / run_state 无活跃 phase → exit 0（不干预）。
  3. 判不出 version/build / 收尾门脚本缺失 / 任何异常 → exit 0（永不因自身故障 wedge）。
  4. 熔断上限：连续阻止达 STOP_GUARD_MAX_BLOCKS 次仍未过 → fail-open exit 0 + 告警（防无限 wedge）。
只有【全部确定信号齐备 + 收尾门确定 exit 1 + 未达熔断上限】才 exit 2 阻止结束。
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

TRANSCRIPT_TAIL_BYTES = 512 * 1024   # 只读 transcript 尾部，找最后一条用户输入
STOP_GUARD_MAX_BLOCKS = 3         # 连续阻止上限，达到即 fail-open 防 wedge
SKIP_LOG_MAX = 50                 # fail-open 台账保留最近 N 条（滚动截断，不无限增长）


def _paths():
    """aidp_paths（本地运行时产物的路径单一信源）。"""
    import sys as _s
    _s.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import aidp_paths
    return aidp_paths


def _exit_allow():
    """无条件放行（用于【本就不该介入】的分支：非 autopilot 会话 / 中间 yield-tick）。"""
    sys.exit(0)


def _note_skip(root, branch, detail=""):
    """记一笔【本可介入却放行】的 fail-open，落 memory/.aidp/stop-guard-skips.jsonl。

    ⛔ 为什么必须有这个台账：不打印的放行会让「护栏看过了、判定一切正常」与
    「护栏因为读不到状态而弃权」在外部**完全同形**——*一个门是绿的 ≠ 目标达成*。
    事故复盘时必须能区分「hook 放行了」和「hook 根本没轮到判断」。

    ★ 只记【可疑】放行，不记良性放行：非 autopilot 轮次与中间 yield-tick 是高频路径
    （本 hook 每轮对话结束都触发），记了会把台账刷爆、把真正可疑的那几条挤掉。
    """
    try:
        d = root / "memory"
        if not d.is_dir():
            return                      # memory/ 不存在 = 非 AIDP 项目，静默
        _paths().ensure_runtime_dir(str(root))   # ⛔ 落点已在子目录，父目录不再天然存在
        f = Path(_paths().stop_guard_skips(str(root)))
        rec = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"),
               "branch": branch, "detail": str(detail)[:400]}
        lines = []
        if f.is_file():
            lines = f.read_text(encoding="utf-8").splitlines()
        lines = lines[-(SKIP_LOG_MAX - 1):] + [json.dumps(rec, ensure_ascii=False)]
        f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception:
        pass                            # 台账写不进去绝不能影响放行本身


def _exit_allow_noted(root, branch, detail=""):
    """放行 + 记账 + 打一行 stderr —— 用于「有活跃 run 却放行」的可疑分支。

    stderr 那一行是给【人】看的即时信号；jsonl 是给事后复盘看的。两者都不阻断。
    """
    _note_skip(root, branch, detail)
    sys.stderr.write(
        "ℹ️ autopilot 收尾护栏本轮未介入（分支 %s）：%s\n"
        "   —— 这不代表已收口，只代表护栏判不出来。台账：memory/.aidp/stop-guard-skips.jsonl\n"
        % (branch, detail or "无附加信息"))
    sys.exit(0)


def _agent_flag():
    """`--agent <claude|codex|dsh>`：由 agent_sync.py 接线时写进 hook 命令，缺省 claude。"""
    argv = sys.argv[1:]
    if "--agent" in argv:
        i = argv.index("--agent")
        if i + 1 < len(argv):
            return argv[i + 1]
    return "claude"


def _block(text):
    """阻止结束，迫使继续补产。

    三个宿主共用同一套信号：exit 2 + stderr 说明（Claude Code 语义）；
    Codex / DeepSeek Harness 另在 stdout 输出 `{"decision":"block","reason":...}`，
    二者的 Stop hook 以此作为「继续本轮」的结构化判据。
    """
    sys.stderr.write(text)
    if _agent_flag() != "claude":
        sys.stdout.write(json.dumps({"decision": "block", "reason": text}, ensure_ascii=False) + "\n")
    sys.exit(2)


def _exit_block(msg):
    """阻止结束（收尾前置脚本给出确定失败时）。"""
    _block("⛔ autopilot 未收口，不能就此结束：\n  " + msg + "\n"
           "（若确为误报或需临时禁用本护栏：touch memory/.autopilot-stop-guard-off）\n")


def _project_root():
    """项目根目录：CLAUDE_PROJECT_DIR → CODEX_PROJECT_DIR / DSH_PROJECT_DIR → git 根 → cwd。

    同一份脚本同时接在 Claude Code / Codex / DeepSeek Harness 的 Stop hook 上，
    各宿主注入的环境变量不同；都没有时回落 git 根，再回落当前工作目录。
    """
    for key in ("CLAUDE_PROJECT_DIR", "CODEX_PROJECT_DIR", "DSH_PROJECT_DIR"):
        val = os.environ.get(key)
        if val and os.path.isdir(val):
            return Path(val)
    try:
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, timeout=5)
        top = r.stdout.strip()
        if r.returncode == 0 and top and os.path.isdir(top):
            return Path(top)
    except Exception:
        pass
    return Path(os.getcwd())


_AUTOPILOT_CALL_RE = re.compile(
    r"(?:(?:^|\s)[$/]sprint-autopilot\b|<command-name>/?sprint-autopilot</command-name>)")


def _user_texts(obj):
    """从一条 transcript 记录里抽出**用户输入**文本（忽略工具结果）。兼容 Claude Code / Codex 形态。"""
    out = []
    if not isinstance(obj, dict):
        return out
    cands = [obj, obj.get("message"), obj.get("payload")]
    for c in cands:
        if not isinstance(c, dict):
            continue
        role = c.get("role") or (obj.get("type") if obj.get("type") == "user" and c is obj.get("message") else None)
        if role != "user":
            continue
        content = c.get("content")
        if isinstance(content, str):
            out.append(content)
        elif isinstance(content, list):
            for blk in content:
                if isinstance(blk, dict) and blk.get("type") in ("text", "input_text"):
                    out.append(str(blk.get("text") or ""))
    return [t for t in out if t.strip()]


def _is_autopilot_turn(data):
    """本轮是否 `/sprint-autopilot` tick → True/False。"""
    cmd = (os.environ.get("AIDP_TICK_COMMAND") or "").strip()
    if cmd:
        return cmd.lstrip("/") == "sprint-autopilot"
    tp = (data or {}).get("transcript_path") if isinstance(data, dict) else None
    if not tp or not os.path.isfile(tp):
        return False
    try:
        with open(tp, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - TRANSCRIPT_TAIL_BYTES))
            lines = fh.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return False
    for ln in reversed(lines):
        try:
            texts = _user_texts(json.loads(ln))
        except ValueError:
            continue
        if texts:
            return bool(_AUTOPILOT_CALL_RE.search("\n".join(texts)))
    return False


def main():
    # --- 读 Stop hook 输入（失败即放行）---
    try:
        data = json.load(sys.stdin)
    except Exception:
        _exit_allow()

    root = _project_root()
    mem = root / "memory"

    baseline = mem / ".sprint-autopilot-baseline.json"

    # 0. 作用域：只拦 autopilot tick 轮次（测试链路 / 普通对话一律放行）
    if not _is_autopilot_turn(data):
        _exit_allow()

    # 1. 关闭开关（逃生舱）——最该留痕：一旦 touch 出来就永久生效，护栏此后全程沉默
    if (mem / ".autopilot-stop-guard-off").exists():
        _exit_allow_noted(root, "escape-hatch",
                          "memory/.autopilot-stop-guard-off 存在，护栏被人工禁用（本轮是 autopilot tick）")

    # 1b. 配置开关：memory/aidp-config.yaml 的 stop_guard.enabled=false → 放行（读不出按开启处理）
    try:
        sys.path.insert(0, str(root / ".aidp" / "scripts"))
        import aidp_config
        if not aidp_config.stop_guard_enabled(str(root)):
            _exit_allow()
    except SystemExit:
        raise
    except Exception:
        pass

    if not baseline.is_file():
        _exit_allow()

    try:
        bl = json.loads(baseline.read_text(encoding="utf-8"))
        if not isinstance(bl, dict):
            _exit_allow()
    except Exception:
        _exit_allow()

    # 2. 活跃 run 判定：命令各 Phase 写的是【版本级】versions.{V}.run_state；
    #    只对 run_state 活跃的那个版本收尾、不跨版本抓历史 build。
    def _is_active(rs):
        np = str((rs or {}).get("next_phase") or "").strip().lower()
        return bool(np) and np != "done"

    versions = bl.get("versions") or {}
    if not isinstance(versions, dict):
        versions = {}

    # 收集【版本级】run_state 活跃的版本，按 run_state.phase_completed_at（ISO-8601 可字典序比较）取最新
    active = []
    for V, vobj in versions.items():
        if isinstance(vobj, dict) and _is_active(vobj.get("run_state")):
            ts = str((vobj.get("run_state") or {}).get("phase_completed_at") or "")
            active.append((ts, V, vobj))
    if active:
        active.sort(reverse=True)
        _, active_V, active_vobj = active[0]
        # ★ 中间 yield-tick 豁免（与「逐 tick 单 Sprint、跨 tick 等待 CICD / 探针」对齐）：
        #   本 tick 有唤醒源，且 run_state 显示只是让位给下一 tick——
        #   `next_sprint` 非 done（还有 Sprint 没跑），或 `next_phase` 是跨 tick 等待游标（3.2.1-*）。
        #   此时仪式还没到收口时机，跑收尾门必 FAIL。
        #   ⛔ 无唤醒源（`--once`）时不存在合法的中间 yield：没有下一 tick 来接，让位等于丢活儿。
        rs = active_vobj.get("run_state") or {}
        _wake = str((bl.get("autopilot") or {}).get("wake_source_this_tick") or "").strip()
        _has_wake = _wake not in ("", "0", "false", "none")
        _np_active = str(rs.get("next_phase") or "").strip().lower()
        if _has_wake and (str(rs.get("next_sprint") or "").strip().lower() not in ("", "done")
                          or _np_active.startswith("3.2.1-")):
            _exit_allow()
        scan_versions = {active_V: active_vobj}   # ★ 只对当前活跃版本收尾，不跨版本抓历史 build
    else:
        _exit_allow()                             # 无活跃 run_state = 本 tick 无待收口的流水线

    # 3. 判定 (version, build)：在 scan_versions 内找未关闭且未 finalize 的 build（= 仪式可能未收尾）
    target = None  # (V, B, will_browser_test)
    for V, vobj in scan_versions.items():
        if not isinstance(vobj, dict):
            continue
        cur_b = vobj.get("current_build")
        builds = vobj.get("builds") or []
        for b in builds:
            if not isinstance(b, dict):
                continue
            if cur_b and b.get("build") != cur_b:
                continue
            status = b.get("status")
            if status != "closed" and not b.get("ai_report_finalized"):
                # ⛔ 判据不能只看 aiauto_delegated_at：标准双 loop 下 autopilot **从不** invoke
                #    测试链路（该字段只在 test-only 子流程 R 写），于是 wbt 恒 0 → stage 恒 final
                #    → 门去校 exec_report 交付台账，而那份台账在该路径**只由测试链路产** →
                #    每次 Stop 都判失败、阻止轮次结束，逼执行体补产它不该产的测试产物。
                #    与 phase-3-9 的 GATE_STAGE 同口径：委派证据 **或** 测试链路真在干活。
                _alive = 0
                try:
                    _g = root / ".aidp" / "scripts" / "autopilot-ceremony-gate.py"
                    if _g.is_file():
                        _r = subprocess.run(
                            [sys.executable, str(_g), "test-loop-alive", "--version", str(V),
                             "--root", str(root)],
                            capture_output=True, text=True, timeout=30)
                        _alive = 1 if (_r.stdout or "").strip() == "1" else 0
                except Exception:
                    _alive = 0
                # ★ 第三个条件不可省：stage 分流的完整口径是
                #   `LOOP_UNATTENDED=1 AND (已委派 OR 测试链路活跃)` 才 skeleton
                #   （单一信源 = flows/sprint-autopilot/phase-3-9.md 的 stage 分流）。
                #   丢掉 LOOP_UNATTENDED 的后果**恰好落在最不该失效的场景**：交互式单次
                #   （`--once`，没有下一 tick 来接）+ 测试 loop 心跳存活时，命令端判 final、
                #   本 hook 判 skeleton —— 而 gate 的「0bis Sprint 关闭度」等结果级检查全部
                #   挂在 `stage == "final"` 下，于是**唯一的自动兜底恰好在无人接手的那一轮退化**。
                _loop_unattended = bool(
                    (bl.get("autopilot") or {}).get("loop_unattended_this_tick"))
                wbt = 1 if (_loop_unattended
                            and (b.get("aiauto_delegated_at") or _alive)) else 0
                # ★ 一并带出 entry_mode 供下方 --entry-mode 透传（见 4. 的说明）。
                #   ⛔ **build 级优先**：同版本首轮 full、复验轮 test-only 共用版本级槽位、后写覆盖先写，
                #   拿版本槽位去校另一个 build 会把通知集算错；build 条目未写时才取版本级。
                target = (V, b.get("build"), wbt,
                          b.get("entry_mode") or vobj.get("autopilot_entry_mode") or "")
                break
        if target:
            break
    if not target or not target[1]:
        # 「已进 Phase 3、但尚未铸 build」：取不到 build，但 run_state 显示还没走完
        #    （next_phase 非终态）时**拦截**，让执行体继续推进而不是静默停手；
        #    仍取不到任何信息时才放行（不误伤）。
        _rs, _rsv = {}, ""
        for _v, _vo in (bl.get("versions") or {}).items():
            if isinstance(_vo, dict) and isinstance(_vo.get("run_state"), dict):
                _rs = _vo["run_state"]
                _rsv = _v
        _np = str(_rs.get("next_phase") or "").strip().lower()
        # ★ 合法冻结豁免（与 ceremony-gate `_handback_verdict` 同口径）：按契约冻结并写齐
        #   四件套的那一轮，`next_phase` 必然停在半路——那是"停得响"、不是"丢活儿"。
        #   ⛔ 半截冻结（只置 needs_human、四件套不齐）不豁免。
        _vo_frozen = ((bl.get("versions") or {}).get(_rsv) or {}) if _rsv else {}
        _quartet = (bool(_vo_frozen.get("needs_human"))
                    and bool(_vo_frozen.get("aiauto_frozen_at"))
                    and bool(str(_vo_frozen.get("freeze_reason") or "").strip())
                    and bool(str(bl.get("aiauto_blocked_reason") or "").strip()))
        if _quartet:
            # 良性豁免，但仍记账：冻结四件套齐 ≠ 人一定会来看，台账让"冻了多少轮"可数
            _exit_allow_noted(root, "frozen-quartet",
                              "版本 %s 已按契约冻结（needs_human + 四件套齐），豁免收尾门"
                              % (_rsv or "?"))
        if _np and _np not in ("done", "finished", "complete", "completed", ""):
            _exit_block(
                f"run_state.next_phase={_rs.get('next_phase')} 尚未收口，但本轮尚未铸 build："
                f"请继续推进该阶段，或先跑 `/sprint-autopilot --target {_rsv} --once` 铸 build 后再收尾。"
                "（⛔ 不要停在这里等人——无人值守下没有人会来。）")
        # ⛔ 走到这里 = run_state 给不出任何非终态阶段、也没有可校的 build：放行但留痕。
        _exit_allow_noted(root, "no-build-no-runstate",
                          "baseline 新鲜但取不到待校 build，且 run_state.next_phase=%r "
                          "无法判定是否已收口" % (_np or ""))
    V, B, wbt, entry_mode = target

    # 4. 跑收尾门（确定性外部脚本）——脚本缺失/异常即放行
    gate = root / ".aidp" / "scripts" / "autopilot-ceremony-gate.py"
    if not gate.is_file():
        _exit_allow_noted(root, "gate-script-missing",
                          "收尾门脚本缺失：%s（version %s · build %s 未经任何校验即放行）"
                          % (gate, V, B))
    # ★ 参数必须与命令端收尾时的调用口径一致，否则门在校"尚未该产生的产物"、恒 FAIL：
    #   --stage：★ 判据 =【谁是 build 关闭方，谁跑 final】（单一信源 = flows/sprint-autopilot/phase-3-9.md
    #            的 stage 分流注释）：
    #              · 未委派浏览器实测（静态-only）→ autopilot 自己是 build 关闭方 → **final**（校交付）
    #              · 已委派（aiauto_delegated_at 非空）→ 关闭方是测试链路 Phase 3.7 → **skeleton**
    #            ⛔ 写反则双向都错：已委派跑 final 会去校测试链路尚未产出的终态产物（恒 FAIL、
    #              逼执行体伪造测试报告）；未委派跑 skeleton 会漏掉「从未真委派」的真空。
    #   --notify：里程碑通知不可用（未启用 / 无渠道具备发送条件）时传 0，
    #            否则门会要求一份根本不该发的通知台账。
    #   --entry-mode：★ 必须透传。gate 侧虽已按 `_resolve_entry_mode()` 回退读
    #            baseline，本处仍显式传一份作**纵深防御**——本 hook 是 gate 唯一的非交互调用方，
    #            漏传时的失败形态是"通知集按 full 算 → test-only 轮次恒索要 #1c/#1d/#2 三张
    #            本轮压根没发生的里程碑通知"，而调用方无法用任何配置纠正，只能被逼去谎报里程碑
    #            或关掉整个护栏。传空串则不加该参数（交回 gate 侧回退）。
    stage = "skeleton" if wbt else "final"   # ★ 关闭方判据，勿反：已委派→测试链路收 final，本 hook 只校骨架
    # 通知通道判定与 `notify.py --auto` 同源：总开关开启且至少一个渠道本地具备发送条件。
    #    判不出（配置模块缺失 / 解析异常）按「未启用」处理——宁可少校一项通知台账，
    #    也不逼执行体去补发一条根本发不出去的通知。
    notify_on = False
    try:
        sys.path.insert(0, str(root / ".aidp" / "scripts"))
        import notify as _notify
        notify_on = bool(_notify.notify_ready(str(root)))
    except Exception:
        notify_on = False
    try:
        r = subprocess.run(
            # ⛔ **刻意不传 `--will-browser-test`**（与命令端 phase-3-9.md 的调用口径一致）：
            #    本 hook 的 `wbt` 是由「委派证据」（aiauto_delegated_at / 心跳存活）推出来的，
            #    回答的是「有没有被测过」；而 gate 自己的判据是「**该不该**被测」= 部署模式非 none。
            #    传进去等于把 3b2「测试链路运行证据」这道门的开关，接到它要检测的那根线上——
            #    单挂一条 loop（正是文档反复警告、也最需要兜底的场景）时 wbt 恒 0，
            #    3b/3b2/3c/3i 四项全部跳过，护栏在唯一该生效的场景里自我关闭。
            #    `wbt` 在本 hook 内**只用于推 stage**（谁是 build 关闭方），不外传。
            [sys.executable, str(gate), "check", "--version", str(V), "--build", str(B),
             "--stage", stage,
             "--notify", "1" if notify_on else "0", "--repo-root", str(root)]
            + (["--entry-mode", entry_mode] if entry_mode else []),
            capture_output=True, text=True, timeout=120,
        )
    except Exception as e:
        _exit_allow_noted(root, "gate-exec-failed",
                          "收尾门执行失败（%s: %s）—— version %s · build %s 未经校验即放行"
                          % (type(e).__name__, e, V, B))

    # ★ 熔断计数**按 build 分键**：单个整数会让一个坏 build 累到上限后，
    #   此后所有 build 首次检查即 fail-open。分键后一个坏 build 不再连累后续 build。
    _paths().ensure_runtime_dir(str(root))
    cnt_file = Path(_paths().stop_guard_count(str(root)))
    cnt_key = f"{V}_{B}"

    def _load_counts():
        try:
            raw = json.loads(cnt_file.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except Exception:
            return {}  # 缺失 / 损坏 → 从零开始

    if r.returncode == 0:
        # ★★ 收尾门过了还要再问一句「活儿真派出去了吗」——HANDBACK 检查。
        #    gate 的 `check` **刻意不含**这一项（它在 3.7 / 3.4 step2 就跑，那时 run_state
        #    必然还是非终态，放进去每轮必假阳性），其注释指明正确落点是「命令返回前的独立
        #    handback-check 子命令」。本 Stop hook **就是**那个时刻，也是它唯一的自动触发点。
        try:
            # ★ 必须带 `--record`：`autopilot.last_handback` 的**唯一自动写入方**就是这里。
            #   不带则该键恒空，Phase 0.0.0bis 的「上一轮遗留自检」永不触发 —— 那条自称
            #   「不再依赖执行体自己想起来」的机制会回落成纯自律。
            hb = subprocess.run(
                [sys.executable, str(gate), "handback-check", "--version", str(V),
                 "--repo-root", str(root), "--record"],
                capture_output=True, text=True, timeout=60)
            if hb.returncode != 0:
                _exit_block((hb.stdout or "") + (hb.stderr or "")
                            or "handback-check 判定：仍有未完成的 run_state，却在无唤醒源下交还控制权")
        except Exception:
            pass          # 探测失败不阻断（与本 hook 其余外部调用同口径：宁可放行不误杀）
        # 收尾门已过 → 清本 build 的熔断计数、放行
        counts = _load_counts()
        if counts.pop(cnt_key, None) is not None:
            try:
                cnt_file.write_text(json.dumps(counts, ensure_ascii=False), encoding="utf-8")
            except OSError:
                pass
        elif not counts:
            try:
                cnt_file.unlink(missing_ok=True)
            except OSError:
                pass
        _exit_allow()

    # ★ exit 2 = gate 的**入参/环境错**（如 --build 取空、--no-pipeline-reason 与 baseline 矛盾），
    #   ⛔ 不是「仪式产物缺失」。混为一谈会把参数为空误报成「收尾门未过」并连续 wedge，
    #   故这里放行并留痕，交人看 ledger。
    if r.returncode != 1:
        _exit_allow_noted(root, "gate-usage-error",
                          f"rc={r.returncode}: {(r.stderr or '')[:200]}")

    # returncode == 1 → 收尾门未过（仪式产物确实缺失）。熔断上限检查（防无限 wedge）
    counts = _load_counts()
    cnt = int(counts.get(cnt_key) or 0)
    if cnt >= STOP_GUARD_MAX_BLOCKS:
        # 达上限 → fail-open，避免无限阻止；大声告警交人工
        sys.stderr.write(
            f"⚠️ autopilot 收尾门（build {B}）连续 {cnt} 次未过、已达阻止上限，本护栏放行止损。"
            f"请人工检查仪式产物是否缺失（跑 .aidp/scripts/autopilot-ceremony-gate.py check --version {V} --build {B}）。\n"
        )
        _note_skip(root, "max-blocks-reached",
                   f"version {V} · build {B} 收尾门连续 {cnt} 次未过，达阻止上限后放行止损")
        _exit_allow()

    counts[cnt_key] = cnt + 1
    try:
        cnt_file.write_text(json.dumps(counts, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass

    # 摘取收尾门输出里的 FAIL 摘要
    summary = ""
    for line in (r.stdout or "").splitlines():
        if "❌" in line or "GATE: FAIL" in line:
            summary += "  " + line.strip() + "\n"
    _block(
        f"⛔ autopilot 收尾门未过（version {V} · build {B}）——本轮仍有强制仪式产物缺失，不能就此结束：\n"
        f"{summary}"
        "请回对应 Phase 补产（emit-report.py / 补发里程碑通知 + record-card / 委派测试链路），"
        "补齐并复跑收尾门通过后再结束。\n"
        "（若确为误报或需临时禁用本护栏：touch memory/.autopilot-stop-guard-off）\n"
    )


if __name__ == "__main__":
    main()
