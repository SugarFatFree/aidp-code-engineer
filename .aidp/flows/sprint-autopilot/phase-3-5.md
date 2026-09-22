# sprint-autopilot · Phase 3 详情分片 [5/13]（3.2 批量 Sprint 执行 + 推送 + 出口游标）
<!-- flowvar-check: allow VKEY -->

> 本片覆盖 Phase 3.2：批量 Sprint、推送、部署与出口游标；进入本阶段后按本文逐项执行。
> 分片清单见 `{{AIDP_HOME}}/commands/sprint-autopilot.md`，维护理由见同目录 `rationale.md`。

---

### 3.2 批量 Sprint 执行（里程碑通知 #1c 开发开始 + #2 在循环内 + #1d 部署完成）

> `ENTRY_MODE=incremental` 不跑全量 `/sprint-batch`，改经 `/sprint-bugfix` 或 `/sprint-dev` 落地增量改动；#1c/#1d、部署、子流程 R 与回写 build 仍照常执行。`full` 模式跑全量 Sprint。

0. **里程碑通知 #1c 开发开始（见 0.1bis；总是发）**——`/sprint-batch` 执行**前**经 `notify.py --auto` 发送（公共字段 + 下列内容）：
   ```
   🔨 {项目名称} {TARGET_VERSION} · 开发开始
   版本：{TARGET_VERSION}
   计划：{N} 个 Sprint，逐个 start → dev → test（静态）→ bugfix → close
   分支：{branch}
   部署模式：{local | cloud | none}（按 autopilot_decisions.deployment）
   进度：每个 Sprint 关闭时播报（#2 通知），全部完成发 #3 AI执行报告
   ```

> ★ 进入步骤 1 前从 baseline 读回本 tick 信号（shell state 不跨 Bash 调用），并将两值写入子 Agent prompt：
> `BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py"; HAS_WAKE_SOURCE=$($BE get autopilot.wake_source_this_tick --default 0); LOOP_UNATTENDED=$($BE get autopilot.loop_unattended_this_tick --default 0)`

1. **★ 执行粒度决策（#1 上下文优化 —— 决定"一 tick 跑几个 Sprint"，先于下面的调用）**：全量开发把 N 个 Sprint 的 dev/test/bugfix 往返**线性累积在同一上下文**，是 autopilot 单 tick 破 1M 上下文的最大来源。故按上下文分流：
   - **`HAS_WAKE_SOURCE=1`（`/loop` / cron）且未带 `--batch-one-tick`（★ 默认）= 逐 tick 单 Sprint**：进入下方 **1.1 单 Sprint 可执行分支**，本 tick 只跑下一个未关闭 Sprint。
   - **`HAS_WAKE_SOURCE=0`（交互式单次 / 裸 `--unattended`）或 `--batch-one-tick`**：走下面的 `/sprint-batch`，**本轮内连跑到全部 Sprint 关闭为止**。⛔⛔ **此时绝对禁止 `UNATTENDED_YIELD`**（无受托人 = 永久停摆）。上下文靠 #2 子 Agent 隔离压。
   - **`ENTRY_MODE=incremental`**：增量本身即一个改动单元、无多 Sprint 累积，不拆 tick，一 tick 跑完。

   **1.1 `HAS_WAKE_SOURCE=1` 默认逐 tick 单 Sprint（★ 必须实际执行，不得只更新游标）**：

   **① 计算下一个待跑 Sprint（fail-closed）**：
   ```bash
   # 先从权威计划与已关闭归档计算下一个 Sprint；任一集合为空都 fail-closed。
   eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell)"
   BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py"; V="${TARGET_VERSION:?}"
   # ★ Sprint 集合唯一口径 = plan_sprints.py（根因见 rationale.md「计划文件的三种解析法」）
   _PS=$(python3 {{AIDP_HOME}}/scripts/plan_sprints.py --version "$V" --shell) || exit 1
   eval "$_PS"; : "${REMAIN_COUNT:?plan_sprints fail-closed}"
   # ⛔ 本 exit 0 **只结束本围栏、不让位本 tick**（全仓唯一例外，见 rationale「全部关闭分支的 exit 0」）
   [ "$REMAIN_COUNT" -eq 0 ] && { echo "✅ 全部 Sprint 已关闭 → 跳过 Sprint 循环 → Read phase-3-5b.md，从步骤 2.5『部署触发前置』（commit → 分类 → push）执行（不退本 tick）"; exit 0; }
   SPRINT_NO="$NEXT_SPRINT"; echo "SPRINT_NO=$SPRINT_NO"
   ```

   **② 委派子 Agent 执行该 Sprint（IRON-8）**：用 `Agent({run_in_background:false})` 派子 Agent 跑
   `/sprint-full ${SPRINT_NO} --unattended --from-batch`（内部即 start→dev→test→bugfix→close 全链），
   要求它**只回传 compact JSON** `{"sprint":"NNN","closed":true|false,"reason":"..."}`。
   ⛔ **斜杠命令不能写进 bash 围栏**（它不是 shell 命令，在 Bash 工具里必 `127`；见 rationale.md「斜杠命令进围栏」）。

   **③ 据落盘产物判定 + 记账 + 写游标**（⛔ 只认 close 归档文件，不信子 Agent 口述）：

   ```bash
   eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell)"
   BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py"; V="${TARGET_VERSION:?}"
   _PS=$(python3 {{AIDP_HOME}}/scripts/plan_sprints.py --version "$V" --shell) || exit 1
   eval "$_PS"; : "${REMAIN_COUNT:?plan_sprints fail-closed}"
   read -ra CLOSED_AFTER <<< "$CLOSED_SPRINTS"
   SPRINT_NO=$($BE --version "$V" get run_state.next_sprint --default "")
   # ★ 游标丢失必须显式 fail：空数组 + 空模式会互相命中，最坏组合反被判成功（rationale.md）
   if [ -z "$SPRINT_NO" ]; then
     S=$($BE --version "$V" bump dev_fail_streak)
     $BE --version "$V" set dev_fail_phase "3.2-dev"
     echo "⛔ run_state.next_sprint 为空（游标丢失，dev_fail_streak=$S）→ 让位本 tick"; exit 0
   fi
   # ⛔ 失败不能裸 exit 1（记账范式同 phase-3-9，根因见 rationale.md「裸退让熔断永不达阈」）
   if ! printf '%s\n' "${CLOSED_AFTER[@]}" | grep -qx "$SPRINT_NO"; then
     S=$($BE --version "$V" bump dev_fail_streak)
     $BE --version "$V" set dev_fail_phase "3.2-dev"
     $BE --version "$V" run-state "3.2-dev" "3.2-dev" "$SPRINT_NO" \
       --summary "Sprint-$SPRINT_NO 未取得 close 归档（第 $S 次）" --pending "sprint-close-failed"
     # ★★ 只 bump 不判阈 = 熔断永不触发（根因见 rationale.md「3.2 的达阈冻结」）
     if [ "$S" -ge "${DEV_FAIL_FREEZE_THRESHOLD:-3}" ]; then
       $BE --version "$V" set needs_human true aiauto_frozen_at @now freeze_reason handoff-exhausted \
         needs_human_reason "Sprint-$SPRINT_NO 连续 $S tick 未取得 close 归档（3.2-dev），结构性不可自愈，请人工介入"
       $BE set aiauto_blocked_reason "frozen:handoff-exhausted@$V"
       # ⛔ 冻结必须同时发 #4（口径见 phase-0-4.md）：不发 = 「停了，但没人知道」。
       python3 {{AIDP_HOME}}/scripts/notify.py --node "#4" --auto --header-color red \
         --title "开发受阻：Sprint 未取得 close 归档" --version "$V" \
         --section "Sprint-$SPRINT_NO 连续 $S tick 无 close 归档（3.2-dev），已冻结本版待人工。" || true   # 退出码 3 = 未配置通知渠道，静默跳过
       echo "⛔ Sprint-$SPRINT_NO 连续 $S tick 无 close 归档（≥ 阈值 ${DEV_FAIL_FREEZE_THRESHOLD:-3}）→ needs_human 冻结本版止损"; exit 0
     fi
     echo "⛔ Sprint-$SPRINT_NO 无 close 归档产物（dev_fail_streak=$S）→ 让位本 tick"; exit 0
   fi
   $BE --version "$V" del dev_fail_streak dev_fail_phase || true
   # 本块开头那次 plan_sprints 扫描发生在子 Agent 收工【之后】，CLOSED/REMAIN 已是最新态
   REMAIN_AFTER="$NEXT_SPRINT"
   $BE --version "$V" run-state "3.2-dev" "3.2-dev" "${REMAIN_AFTER:-done}" \
     --summary "Sprint-$SPRINT_NO 已完成 start→dev→test→bugfix→close" --pending ""
   # ★ 让位前**可执行地**断言唤醒源（理据见 rationale.md「让位前必须断言唤醒源」）
   eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell)"
   if [ -n "$REMAIN_AFTER" ] && [ "${HAS_WAKE_SOURCE:-0}" = "1" ]; then
     echo "UNATTENDED_YIELD"; exit 0   # 让位本 tick，下一 tick 接着跑 Sprint-$REMAIN_AFTER
   elif [ -n "$REMAIN_AFTER" ]; then
     echo "⛔ 无唤醒源（HAS_WAKE_SOURCE=0）⇒ 禁止让位：本轮内继续跑下一个 Sprint-$REMAIN_AFTER"
   fi
   ```

> ⬇️ **步骤 2–4（`/sprint-batch` 执行——每个 Sprint 走 `/sprint-start` → `/sprint-dev` → `/sprint-test` → `/sprint-bugfix` → `/sprint-close`——+ 推送 + 部署动作 + #2 通知 + `--single-sprint`）已外置到 `phase-3-5b.md`**
> （本片达 20KB 上限，按本目录二次切分约定拆）。**进入步骤 2 前必须 `Read` 它**；步骤 2–4 执行完后回到本片执行下方出口 `run_state` 写盘，
> ⛔ 二者都不是可选附录。


---

## ⛳ 本 Phase 出口：`run_state` 写盘（**硬动作，不可跳过**）

> 本 Phase 动作完成后立即写 `run_state`；`next_phase`/`next_sprint` 是续跑与收尾门的必要状态，不得省略。
>

⛔ **「算」与「写」必须在同一个 Bash 围栏内**：shell state 不跨 Bash 工具调用，拆成两块会让
`NEXT_PHASE_AFTER_DEV` / `NEXT_SPRINT` **恒空** → `run-state` 写进空游标 → 下 tick 断点续跑失效、
从 Phase 3.0 全量重推，Stop hook 的中间 yield 豁免同时失灵。下面就是完整的一整块（就地重算，
不依赖任何跨围栏变量），写盘前还有一道"算空即拒写"的兜底：

```bash
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell)"
BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py"; V="${TARGET_VERSION:?TARGET_VERSION 未由 tick flags 提供}"
# ★ 同上：Sprint 集合唯一口径 = plan_sprints.py（fail-closed 内建，含"计划在但解析不出 Sprint"）
_PS=$(python3 {{AIDP_HOME}}/scripts/plan_sprints.py --version "$V" --shell) || exit 1
eval "$_PS"; : "${REMAIN_COUNT:?plan_sprints fail-closed}"
REMAINING_SPRINTS="$REMAIN_COUNT"; NEXT_SPRINT_NO="$NEXT_SPRINT"
if [ -n "$NEXT_SPRINT_NO" ]; then
  NEXT_PHASE_AFTER_DEV="3.2-dev"; NEXT_SPRINT="$NEXT_SPRINT_NO"
else
  NEXT_SPRINT="done"
  # ⛔ 判据真源【不在 baseline】，走 tick_flags 读真源（见 rationale.md「3.2 出口路由」）
  eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell)"
  CICD_BOUND="${CICD_PIPELINE_BOUND:-0}"   # ← memory/aidp-config.yaml cicd 段（provider + pipelines.<env>，同 cicd_watch.py 的真源）
  READY_CFG="${CLOUD_READY_URL:-}"         # ← PRD autopilot_decisions.deployment（按版本取）
  # 无 Git 的 cloud 不能 push，也不能进入 3.2.1-deploy/probe 游标等待不存在的远端部署。
  # VCS_MODE 从本围栏 tick flags 取回；未提供时以入口能力检测为准，不可把 none 默认成 git。
  VCS_MODE=$(python3 -c 'from pathlib import Path; import sys; sys.path.insert(0, "{{AIDP_HOME}}/scripts"); from vcs import detect_mode; print(detect_mode(Path.cwd()))') || exit 1
  if [ "${VCS_MODE:-git}" = "git" ] && [ "${DEPLOY_MODE:-none}" = "cloud" ] && [ "${SKIP_DEPLOY:-0}" != "1" ] && [ "${CICD_BOUND:-0}" != "0" ]; then
    NEXT_PHASE_AFTER_DEV="3.2.1-deploy"
  elif [ "${VCS_MODE:-git}" = "git" ] && [ "${DEPLOY_MODE:-none}" = "cloud" ] && [ "${SKIP_DEPLOY:-0}" != "1" ] && [ -n "$READY_CFG" ]; then
    NEXT_PHASE_AFTER_DEV="3.2.1-probe"
  else
    NEXT_PHASE_AFTER_DEV="3.3-audit"
  fi
fi
[ -n "$NEXT_PHASE_AFTER_DEV" ] && [ -n "$NEXT_SPRINT" ] \
  || { echo "⛔ 出口游标算空，禁止写盘（写空游标 = 下 tick 从头重推）"; exit 1; }
$BE --version "$V" run-state "3.2-dev" "$NEXT_PHASE_AFTER_DEV" "$NEXT_SPRINT" \
  --summary "Phase 3.2：Sprint-${CURRENT_SPRINT:-无} 已关闭；剩余 ${REMAINING_SPRINTS} 个" --pending ""
```

> `next_sprint` 非 `done`（或 `next_phase` 为跨 tick 等待游标 `3.2.1-*`）即代表「中间 yield-tick」——Stop hook 据此豁免收尾门（`hooks/autopilot-stop-guard.py`；它只拦正在执行 autopilot tick 的轮次，测试链路与普通对话一律放行）。
