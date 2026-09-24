# sprint-autopilot · Phase 2 详情（上版准发布 —— /version --no-tag 归档）

> 本文件是 `/sprint-autopilot` 命令 **Phase 2（上版准发布：仅当 PRE_RELEASE_VERSION 非 null）** 的完整详细步骤，由命令主体在**进入 Phase 2 时用 `Read` 工具按需加载**。命令主体只保留 Phase 2 骨架 + 硬门提示 + 指针。
> - **本片覆盖**：Phase 2 准发布前置双门（0a 部署就绪 + 0b 测试收敛）+ 步骤 1–5（#pre-start 通知 / `/version --no-tag` / 回写 baseline / #pre-done 通知 / `run_state` 写盘）
>
> ⚠️ **权威性**：进入 Phase 2 后以本文件为准逐项执行，不得凭命令主体骨架或记忆略过任一子步骤/硬门。
> ⚠️ **维护**：随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-autopilot/phase-2.md`。理据见同目录 `rationale.md`。

---

## Phase 2：上版准发布（仅当 PRE_RELEASE_VERSION 非 null）

`vcs_mode=git` 跑「`/version <PRE_RELEASE_VERSION> --no-tag`」做准发布归档；`vcs_mode=none` 仅做本地 SQL / 文档 / memory 整理，不调用准发布或正式发布路径。两种模式均须先过下述前置门；本地归档成功不等于 tag、分支或远端发布成功。

0. **★ 准发布前置门：部署就绪 + 测试收敛双校验**。任一门未过：调用 `autopilot_fail_handle.py` 记账/判阈/告警，置 `PRERELEASE_HOLD=1`，跳过归档并写 `run-state`，继续同 tick 的 Phase 3；不得在这里退出整轮。判据见下方 0a / 0b，跳过门及冻结理由见 `rationale.md`「Phase 2 准发布双门的形态与判据」。

   ```bash
   : "${BASELINE_FILE:=memory/.sprint-autopilot-baseline.json}"   # ★ 统一变量名 + 兜底默认（未定义时 jq 会读 stdin 静默失败，streak 永不落盘）
   BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py"                   # ★ baseline 唯一加锁写入口（见 invariants「baseline 单一写入口不变式」）
   # 时间用 epoch 比较；PRE_RELEASE_VERSION 跨围栏从 tick 状态读回（理据见 rationale.md）。
   to_ts() { date -d "$1" +%s 2>/dev/null || echo 0; }
   eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command autopilot --shell)"
   TF="python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py set --command autopilot"
   # 每次进入 Phase 2 先关断成功信号；parse 在每个 tick 起点也会整段清零。
   for flag in PRERELEASE_GATE_OK PRERELEASE_ARCHIVE_OK PRERELEASE_YIELD; do $TF "$flag" 0 || exit 1; done
   $TF PRERELEASE_HOLD 1 || exit 1
   DEP_MODE=$(jq -r ".versions.\"$PRE_RELEASE_VERSION\".deployment_mode // \"\"" "$BASELINE_FILE")
   LAST_DEP=$(jq -r ".versions.\"$PRE_RELEASE_VERSION\".last_deployed_at // \"\"" "$BASELINE_FILE")
   # 部署意图（mode≠none = 本应部署 + 需浏览器实测）
   DEPLOY_EXPECTED=1
   [ "$DEP_MODE" = "none" ] && DEPLOY_EXPECTED=0
   if [ -z "$DEP_MODE" ]; then   # deployment_mode 空的歧义态（就绪超时可能未写）→ 读 PRD 意图兜底：mode:none 才放行
     PRD_FILE=$(ls "docs/requirements/$PRE_RELEASE_VERSION/产品提供/"*.md 2>/dev/null | head -1)
     grep -qE '^[[:space:]]*mode:[[:space:]]*none' "$PRD_FILE" 2>/dev/null && DEPLOY_EXPECTED=0
   fi
   PRERELEASE_HOLD=0   # 置 1 = 本 tick 暂缓、不归档准发布
   # 0y 尾段/自动修复进行中先让位，不记 streak、不覆盖 Phase 3 游标（见 rationale.md）。
   PRERELEASE_YIELD=0
   PRE_NP=$($BE --version "$PRE_RELEASE_VERSION" get run_state.next_phase --default "")
   PRE_AFP=$($BE --version "$PRE_RELEASE_VERSION" get auto_fixable_pending --default false)
   PRE_AFIP=$($BE --version "$PRE_RELEASE_VERSION" get auto_fix_in_progress_since --default "")
   case "$PRE_NP" in 3.2.1-*|3.3*|3.4*) PRERELEASE_YIELD=1;; esac
   { [ "$PRE_AFP" = "true" ] || [ -n "$PRE_AFIP" ]; } && PRERELEASE_YIELD=1
   [ "$PRERELEASE_YIELD" = "1" ] && echo "↪️ 0y $PRE_RELEASE_VERSION 尾段/自动修复进行中（next_phase=${PRE_NP:-空} AFP=$PRE_AFP）→ Phase 2 让位，本 tick 不判双门、不归档"

   # ── 0a 部署就绪校验 ──（本应部署却无 last_deployed_at = 部署失败/就绪探针从未通过）
   if [ "$PRERELEASE_YIELD" = "1" ]; then
     :
   elif [ "$DEPLOY_EXPECTED" = "1" ] && [ -z "$LAST_DEP" ]; then
     echo "⛔ 0a 部署就绪未过：$PRE_RELEASE_VERSION 部署模式=${DEP_MODE:-<未写,PRD意图非none>} 但 last_deployed_at 为空 → 本 tick 不归档"
     echo "   → 需经 Phase 3.2.1 重新部署；--target $PRE_RELEASE_VERSION 可人工点名重跑部署"
     # 记账→判阈→冻结四件套→发 #4 一次做完（⛔ 「发 #4」写成注释 = 停得住但停不响）
     python3 {{AIDP_HOME}}/scripts/autopilot_fail_handle.py --version "${PRE_RELEASE_VERSION:?}" \
       --phase 2-prerelease-deploy --reason deploy-unreachable \
       --streak-key prerelease_deploy_block_streak \
       --threshold "${PRERELEASE_DEPLOY_BLOCK_THRESHOLD:-3}" \
       --why "部署就绪从未通过(last_deployed_at 空)，拒绝静默准发布归档；请重部署或人工介入"
     PRERELEASE_HOLD=1
   elif [ -n "$LAST_DEP" ]; then
     $BE --version "$PRE_RELEASE_VERSION" del prerelease_deploy_block_streak || true   # 就绪已过 → 清零 streak
   fi

   # 0b：需部署的版本必须等本 build 测试收敛；本门每 tick 重入。
   if [ "$PRERELEASE_YIELD" = "0" ] && [ "$PRERELEASE_HOLD" = "0" ] && [ "$DEPLOY_EXPECTED" = "1" ] && [ -n "$LAST_DEP" ]; then
     AT=$(jq -r ".versions.\"$PRE_RELEASE_VERSION\".aiauto_tested_at // \"\"" "$BASELINE_FILE")
     UNC=$(jq -r ".versions.\"$PRE_RELEASE_VERSION\".aiauto_test_unconverged_streak // 0" "$BASELINE_FILE")
     # 收敛须同时满足 tested_at、streak、build 级 finalized 和部署时间；理据见 rationale.md。
PRE_CUR_BUILD=$(jq -r ".versions.\"$PRE_RELEASE_VERSION\".current_build // empty" "$BASELINE_FILE")
# build 插值写法同 phase-3-4.md；原因见 rationale.md。
FIN=$(jq -r ".versions.\"$PRE_RELEASE_VERSION\".builds[]? | select(.build==\"$PRE_CUR_BUILD\") | .ai_report_finalized // false" "$BASELINE_FILE" | head -1)
FIN="${FIN:-false}"
     if [ -n "$AT" ] && [ "$UNC" = "0" ] && [ "$FIN" = "true" ] && [ "$(to_ts "$LAST_DEP")" -le "$(to_ts "$AT")" ]; then
       $BE --version "$PRE_RELEASE_VERSION" del test_loop_missing_streak prerelease_test_hold_streak || true
       echo "✅ 0b 测试收敛：本 build 已于 $AT 测过、已收敛、报告已 finalize → 允许准发布归档"
     else
       # 未收敛不归档；测试链路存活须心跳新鲜且本版未阻塞（见 rationale.md）。
   TEST_LOOP_ALIVE=$(AP_V="$PRE_RELEASE_VERSION" python3 - <<'PY' 2>/dev/null || echo 0
import json,os,datetime
try:
    b=json.load(open("memory/.sprint-autopilot-baseline.json"))
    ab=b.get("aiauto_blocked_reason") or ""  # 测试侧已冻结/阻塞 → 心跳再新也不算"活着"（仅当该阻塞对本版成立）
    if ab:
        rsn=ab.split("@",1)[0].replace("frozen:","",1); tgt=ab.split("@",1)[1] if "@" in ab else ""
        if (not tgt) or tgt==os.environ.get("AP_V","") or rsn=="chrome-unavailable":
            print(0); raise SystemExit
    hb=b.get("aiauto_test_heartbeat_at")
    ttl=float(os.environ.get("AIAUTO_TEST_HEARTBEAT_TTL_MIN","30")); alive=0
    if hb is not None:
        try:
            age=(datetime.datetime.now(datetime.timezone.utc)-datetime.datetime.fromisoformat(hb).astimezone(datetime.timezone.utc)).total_seconds()/60.0
            alive=1 if age<=ttl else 0
        except Exception:
            # fail-closed（与 ceremony-gate 同口径；理据见 rationale.md）
            alive=0
    print(alive)
except SystemExit:
    pass
except Exception:
    print(0)
PY
)
       if [ "$TEST_LOOP_ALIVE" = "1" ]; then
         # fail_handle 统一记账、判阈和冻结告警；未达阈只记账（见 rationale.md）。
         VCS_MODE=$(python3 {{AIDP_HOME}}/scripts/vcs.py mode) || exit 1
         FROZEN_HEAD=""
         if [ "$VCS_MODE" = "git" ]; then
           FROZEN_HEAD="$(git rev-parse HEAD 2>/dev/null)" || exit 1
         fi
         python3 {{AIDP_HOME}}/scripts/autopilot_fail_handle.py --version "${PRE_RELEASE_VERSION:?}" \
           --phase 2-prerelease-unconverged --reason unconverged \
           --streak-key prerelease_test_hold_streak \
           --threshold "${PRERELEASE_TEST_HOLD_FREEZE:-12}" \
           --extra "unconverged_frozen_head=$FROZEN_HEAD" \
           --why "测试链路存活但连续多 tick 未收敛，准发布长期挂起，请人工看测试结果/环境"
       else
         TLM=$($BE --version "$PRE_RELEASE_VERSION" get test_loop_missing_streak --default 0)   # ⛔ 只读不 bump：记账唯一落点在下方 fail_handle，两处都记会让阈值提前一半到达
         BLOCKED=$(jq -r '.aiauto_blocked_reason // ""' "$BASELINE_FILE")
         echo "⚠️ 0b 本版需浏览器实测但**测试链路不可用**（${BLOCKED:+测试侧已阻塞：$BLOCKED；}${BLOCKED:-无近期 aiauto_test_heartbeat_at}，连续 ${TLM} tick）→ 准发布暂缓；请挂第二条 loop 「/loop 5m /sprint-aiauto-test --unattended」或先解掉测试侧阻塞"
         python3 {{AIDP_HOME}}/scripts/autopilot_fail_handle.py --version "${PRE_RELEASE_VERSION:?}" \
           --phase 2-prerelease-testloop --reason config-missing \
           --streak-key test_loop_missing_streak \
           --threshold "${TEST_LOOP_MISSING_THRESHOLD:-3}" \
           --why "测试链路未挂载(缺 /loop 5m /sprint-aiauto-test --unattended)，本 build 浏览器实测未执行"
         if [ "$?" = "3" ]; then
           # 达阈后仍须按 phase-3-9.md 完成静态-only 报告与 #3（理据见 rationale.md）。
           echo "⛔ 测试链路缺失达阈 → 先按 phase-3-9.md 三步实跑静态-only 收尾（testSummary 如实标"
           echo "   『浏览器实测未执行(测试链路未挂载)』，⛔ 不填 0/0/0、⛔ 不标已测），再继续本步"
         fi
       fi
       PRERELEASE_HOLD=1
     fi
   fi

   # 0T 过渡版只在双门达阈冻结后判；已有更新版本计划才翻转为归档（见 rationale.md）。
   if [ "$PRERELEASE_HOLD" = "1" ]; then
     FR=$(jq -r ".versions.\"$PRE_RELEASE_VERSION\".freeze_reason // \"\"" "$BASELINE_FILE")
     case "$FR" in
       deploy-unreachable|unconverged|config-missing)
         TRANSITIONAL=0; NEWER_V=""
         for nv in $(ls -d docs/plans/V*/ 2>/dev/null | sed -E 's#.*/(V[^/]+)/#\1#' \
                     | grep -E '^V[0-9]+\.[0-9]+\.[0-9]+$' | sort -V); do
           [ "$nv" = "$PRE_RELEASE_VERSION" ] && continue
           # 只留【严格更新】的版本（SemVer 比较，非字典序：V0.10.0 > V0.2.0）
           [ "$(printf '%s\n%s\n' "$nv" "$PRE_RELEASE_VERSION" | sort -V | head -1)" = "$PRE_RELEASE_VERSION" ] || continue
           # 接受拆分计划文件名，不能固定两位编号（见 rationale.md）。
           ls "docs/plans/$nv/"*研发执行计划*.md >/dev/null 2>&1 || continue
           TRANSITIONAL=1; NEWER_V="$nv"; break
         done
         if [ "$TRANSITIONAL" = "1" ]; then
           echo "🔀 0T 中间过渡版本：$PRE_RELEASE_VERSION 双门卡到阈值（$FR），且 $NEWER_V 的研发执行计划已存在"
           echo "   → 已开下一版，撤销本版冻结后按过渡版归档（--no-tag），不宣称测试已收敛"
           $BE --version "$PRE_RELEASE_VERSION" del needs_human needs_human_reason aiauto_frozen_at \
             freeze_reason prerelease_deploy_block_streak prerelease_test_hold_streak test_loop_missing_streak || true
           # 只清本版顶层阻塞，不误清其他版本。
           AB=$(jq -r '.aiauto_blocked_reason // ""' "$BASELINE_FILE")
           case "$AB" in *"@$PRE_RELEASE_VERSION") $BE del aiauto_blocked_reason || true;; esac
           $BE --version "$PRE_RELEASE_VERSION" set prerelease_transitional true \
             prerelease_transitional_newer "$NEWER_V" prerelease_unconverged_reason "$FR"
           PRERELEASE_HOLD=0   # 翻转：继续走下面 1~4 步归档
         fi;;
     esac
   fi

   # ── 跳过门收尾（必做，缺一即门未落地）──
   [ "$PRERELEASE_YIELD" = "1" ] && echo "→ 本 tick 跳过 Phase 2 的 1~4 步（尾段让位，不写 run-state）→ 继续同 tick 的 Phase 3"
   if [ "$PRERELEASE_HOLD" = "1" ] && [ "$PRERELEASE_YIELD" = "0" ]; then
     echo "→ 本 tick 暂缓 Phase 2，继续同 tick 的 Phase 3"
     $BE --version "$PRE_RELEASE_VERSION" run-state "2-prerelease" "2-prerelease" "" \
       --summary "准发布前置门未过，本 tick 暂缓归档" --pending "prerelease-hold" || exit 1
   fi
   $TF PRERELEASE_HOLD "$PRERELEASE_HOLD" || exit 1
   $TF PRERELEASE_YIELD "$PRERELEASE_YIELD" || exit 1
   if [ "$PRERELEASE_HOLD" = "0" ] && [ "$PRERELEASE_YIELD" = "0" ]; then
     $TF PRERELEASE_GATE_OK 1 || exit 1
   fi
   ```
   > 双门通过（或 0T 达阈且有更新版计划）才归档；hold/yield 不写 `internal_released_at`。依据见 `rationale.md`。

1. **里程碑通知 #pre-start（见 0.1bis）**：
   ```
   🏷️ {项目名称} {PRE_RELEASE_VERSION} · 准发布启动（--no-tag 模式）
   触发：本版本所有 Sprint 已关闭，autopilot 自动归档
   动作：SQL 整理 + 文档清理 + memory 同步 + push commit（不打 tag）
   ```
   > `vcs_mode=none` 时通知改为「本地归档启动：SQL / 文档 / memory 整理；Git 发布 unsupported:vcs-disabled」，不得预告 push commit。
   > `prerelease_transitional=true` 时，通知**加一行如实说明**（不得省略、不得说成"已收敛"）：
   > `🔀 中间过渡版本：{NEWER_V} 已开始规划，本版未经部署/测试收敛（{FR}）即归档，不做正式发布`

2. **按 VCS 模式归档**（命令端编排；⛔ `/version` 是**命令**不是 SKILL，`Skill` 工具调不起它、且失败形态静默；两路均始终传 `--unattended`）：
   - `vcs_mode=git`：跑 `/version {PRE_RELEASE_VERSION} --no-tag --unattended`，维持原 Step 3.1~3.6：跳过 Step 3.4.2 tag，Step 3.4.3 仍 push commit（含 SQL 归档），Step 3.6 输出准发布报告。
   - `vcs_mode=none`：**无 Git 不走正式发布的 `--no-tag` 路径**。先核对版本记忆、baseline、本地台账均明确未发布；已发布、矛盾或不明则按本地归档失败处置。跑 `/version {PRE_RELEASE_VERSION} --finalize-docs --unattended`，核验 Step 3.3.9.5 → 3.3.7 → 3.3.10 → 3.3.11 → 3.3.13；逐项检查 `docs/deployment/{PRE_RELEASE_VERSION}/sql/`（无 SQL 记不适用）、引用、`memory/{PRE_RELEASE_VERSION}/` Sprint 归档及项目记忆「本地已归档（未发布）」。`--finalize-docs` 仅覆盖文档，不证明 SQL / memory 已完成；欠账须核对。Git commit / push / tag / 分支均记 `unsupported:vcs-disabled`（非 passed）；不得记「✅ 已发布」「🟡 已准发布」或宣布 released。
   - **成功落账**：门禁放行、必需归档步骤成功且逐项核验后才运行；`--finalize-docs` 返回码不等于归档完成：
   ```bash
   eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command autopilot --shell)"
   if [ "$PRERELEASE_GATE_OK" = "1" ] && [ "$PRERELEASE_HOLD" = "0" ] && [ "$PRERELEASE_YIELD" = "0" ]; then
     python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py set --command autopilot PRERELEASE_ARCHIVE_OK 1 || exit 1
   else
     echo "⛔ Phase 2 未放行，不得登记归档成功" >&2
   fi
   ```
   - 必需归档失败或核验不明 → 不执行步骤 3–5 成功落账 / #pre-done；按下列失败处置并继续 Phase 3。无 Git 仅对实际本地归档失败记 `local-archive-failed`，不得因 Git 不可用记 `release-blocked`。
   - 失败处置（记账 + 判阈 + 冻结四件套 + #4）：

  ```bash
  python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py set --command autopilot PRERELEASE_HOLD 1 || exit 1
  python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py set --command autopilot PRERELEASE_ARCHIVE_OK 0 || exit 1
  eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command autopilot --shell)"
  VCS_MODE=$(python3 {{AIDP_HOME}}/scripts/vcs.py mode)
  ARCHIVE_REASON=release-blocked; ARCHIVE_WHY="准发布归档失败：归档流程 Step 3.1~3.6 未走完"
  if [ "$VCS_MODE" = "none" ]; then
    ARCHIVE_REASON=local-archive-failed; ARCHIVE_WHY="本地归档失败：文档/SQL/memory 未全部完成或本地发布状态无法核实（Git 发布 unsupported:vcs-disabled）"
  fi
  # ⛔ 版本必须是 `PRE_RELEASE_VERSION`（理据见 rationale.md「Phase 2 的失败处置传哪个版本」）
  python3 {{AIDP_HOME}}/scripts/autopilot_fail_handle.py --version "${PRE_RELEASE_VERSION:?}" \
    --phase 2-prerelease --reason "$ARCHIVE_REASON" --why "$ARCHIVE_WHY"
  # 退出码：0=已记账让位本 tick／3=已冻结（达阈或无唤醒源）／2=入参错（⛔ 此时什么都没写）
  ```


3. **回写 baseline**：`git` 为准发布归档，`none` 仅为本地内部归档；`PRERELEASE_HOLD=1` 不执行。必须实际写入 `internal_released_at`，不能以步骤 5 的摘要代替（根因见 `rationale.md`）。
   ```bash
   eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command autopilot --shell)"
   if [ "$PRERELEASE_GATE_OK" = "1" ] && [ "$PRERELEASE_HOLD" = "0" ] &&
      [ "$PRERELEASE_YIELD" = "0" ] && [ "$PRERELEASE_ARCHIVE_OK" = "1" ] &&
      [ -n "$PRE_RELEASE_VERSION" ]; then
     if ! python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version "$PRE_RELEASE_VERSION" \
       set internal_released_at @now; then
       python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py set --command autopilot PRERELEASE_HOLD 1 || exit 1
       echo "⛔ 内部归档游标写入失败：不发 #pre-done、不写 done，按步骤 2 的失败处置记账" >&2
     fi
   fi
   ```
   > `internal_released_at` 仅是内部选版游标；无 Git 时项目记忆仍记「本地已归档（未发布）」及 `unsupported:vcs-disabled`。

4. **里程碑通知 #pre-done（见 0.1bis）**：重新读本 tick 四信号，且 `internal_released_at` 已写入后才发送；不满足则不发、不宣称成功。通知失败按步骤 2 的失败处置登记 `PRERELEASE_HOLD=1`，步骤 5 不得写 done。
   ```
   ✅ {项目名称} {PRE_RELEASE_VERSION} · 准发布完成
   commit：{hash} | 分支：{branch}
   📌 正式部署时手动跑 /version {PRE_RELEASE_VERSION} 补打 tag
   ```
   > `vcs_mode=none` 仅在步骤 2–3 成功时发「本地归档完成（未发布）｜Git commit / tag / push：unsupported:vcs-disabled」；不填虚构 hash / branch，不提示补 tag。
   > `prerelease_transitional=true` 时同样**加一行如实说明**：
   > `🔀 中间过渡版本归档：未经部署/测试收敛（{FR}）；如需转正式发布，请先部署+实测再跑 /version {PRE_RELEASE_VERSION}`

5. **★ 本片收尾必写 `run_state`（分片末尾硬动作，见 `invariants.md`「阶段推进不变式」——漏写即断点续跑失效）**：
   ```bash
   eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command autopilot --shell)"
   # 仅本 tick 双门通过、未让位、已核验归档且步骤 3 实际写入游标才标 done。
   if [ "$PRERELEASE_GATE_OK" = "1" ] && [ "$PRERELEASE_HOLD" = "0" ] &&
      [ "$PRERELEASE_YIELD" = "0" ] && [ "$PRERELEASE_ARCHIVE_OK" = "1" ] &&
      [ -n "$PRE_RELEASE_VERSION" ] &&
      [ -n "$(python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version "$PRE_RELEASE_VERSION" get internal_released_at --default '')" ]; then
     VCS_MODE=$(python3 {{AIDP_HOME}}/scripts/vcs.py mode) || exit 1
     if [ "$VCS_MODE" = "none" ]; then
       ARCHIVE_SUMMARY="本地归档完成（未发布；Git 发布 unsupported:vcs-disabled），已写 internal_released_at，#pre-done 已发"
     else
       ARCHIVE_SUMMARY="准发布归档完成（--no-tag），已写 internal_released_at，#pre-done 已发"
     fi
     python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version "$PRE_RELEASE_VERSION" \
       run-state "2-prerelease" "done" "" --summary "$ARCHIVE_SUMMARY" --pending ""
   fi
   ```
