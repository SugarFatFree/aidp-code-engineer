# sprint-autopilot · Phase 2 详情（上版准发布 —— /version --no-tag 归档）

> 本文件是 `/sprint-autopilot` 命令 **Phase 2（上版准发布：仅当 PRE_RELEASE_VERSION 非 null）** 的完整详细步骤，由命令主体在**进入 Phase 2 时用 `Read` 工具按需加载**。命令主体只保留 Phase 2 骨架 + 硬门提示 + 指针。
> - **本片覆盖**：Phase 2 准发布前置双门（0a 部署就绪 + 0b 测试收敛）+ 步骤 1–5（#pre-start 通知 / `/version --no-tag` / 回写 baseline / #pre-done 通知 / `run_state` 写盘）
>
> ⚠️ **权威性**：进入 Phase 2 后以本文件为准逐项执行，不得凭命令主体骨架或记忆略过任一子步骤/硬门。
> ⚠️ **维护**：随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-autopilot/phase-2.md`。理据见同目录 `rationale.md`。

---

## Phase 2：上版准发布（仅当 PRE_RELEASE_VERSION 非 null）

跑「`/version <PRE_RELEASE_VERSION> --no-tag`」做归档但不打 tag，让 V0.1.0 的 SQL + 文档 + memory 都进入"已归档"状态，等运维正式部署时手动跑 `/version <PRE_RELEASE_VERSION>` 补打 tag。

0. **★ 准发布前置门：部署就绪 + 测试收敛双校验（不可绕过的跳过门）**——任一门未过则本 tick 不执行下面 1~4 步、直接让位（记 streak + 按阈值告警/冻结，绝不静默）。两门判据见下方 0a / 0b；设立理由见 `rationale.md`。

   > ⛔ **门的强制形态 = 跳过门（skip-gate），不是 `exit 1`**（理据见 `rationale.md`）：本门只否决"上版归档"这一件事，落地形态是 **`PRERELEASE_HOLD=1` → 立刻结束 Phase 2（跳过下面 1~4 步）→ 继续同 tick 的 Phase 3**，`exit` 只留给整轮真正无事可做时的正常收尾。
   > **★ 强制性靠三件结构化动作保证（不是靠 `echo` 自律）**：① 记账对应 streak（`baseline_edit.py bump`）② 达阈发 #4 / 再达阈按「冻结字段写入契约」置 `needs_human` ③ **本节末尾必写 `run-state`**（把 `pending_actions` 标上 `prerelease-hold:<原因>`，未清空即本 Phase 未完成，见 `invariants.md` 阶段推进不变式）。三者缺一即视为门未落地。

   ```bash
   : "${BASELINE_FILE:=memory/.sprint-autopilot-baseline.json}"   # ★ 统一变量名 + 兜底默认（未定义时 jq 会读 stdin 静默失败，streak 永不落盘）
   BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py"                   # ★ baseline 唯一加锁写入口（见 invariants「baseline 单一写入口不变式」）
   # 时间一律 epoch 数值比较：ISO8601 的 "+08:00" 与 "Z" 两种时区写法混排时，字符串比较必误判
   to_ts() { date -d "$1" +%s 2>/dev/null || echo 0; }
   # ★ PRE_RELEASE_VERSION 由 Phase 0.3.4 选出（另一分片、另一次 Bash 调用）→ 必须读回；
   #   取空会让下面所有 jq 路径拼成 `.versions."".…` 恒取空 → 双前置门恒判"未部署/未收敛"。
   eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell)"
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
   # ── 0y 尾段让位（先于双门判）──：本版开发链路尾段仍在跑（部署 / CICD 重试 / 探针 / 终审 / 收尾），
   #   或自动修复复测闭环进行中 → 部署未就绪、测试未收敛都是**合法中间态**，Phase 2 直接让位、⛔ 不记任何 streak、
   #   不写 run-state（Phase 3 尾段游标优先，覆盖它等于把续跑点抹掉）。
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

   # ── 0b 测试收敛校验（B1+B2 修复）──：mode≠none 且部署已就绪时，准发布前必须等本 build 浏览器测试收敛；防「准发布静默抢占测试窗口」+ 把 test_loop_missing 熔断从只跑一次的 Phase 3.4 移到此每 tick 重入处
   if [ "$PRERELEASE_YIELD" = "0" ] && [ "$PRERELEASE_HOLD" = "0" ] && [ "$DEPLOY_EXPECTED" = "1" ] && [ -n "$LAST_DEP" ]; then
     AT=$(jq -r ".versions.\"$PRE_RELEASE_VERSION\".aiauto_tested_at // \"\"" "$BASELINE_FILE")
     UNC=$(jq -r ".versions.\"$PRE_RELEASE_VERSION\".aiauto_test_unconverged_streak // 0" "$BASELINE_FILE")
     # 已测收敛 = aiauto_tested_at 非空 且 不早于 last_deployed_at 且 未收敛 streak==0
     # ★ 时间比较走 epoch（to_ts），不用字符串 `>`（理据见 rationale.md）
     # ★ 必须同时校 `ai_report_finalized`（理据见 rationale.md；统一处置见 aiauto-test Phase 3.7）
     # ⛔ 只写在 builds[] 那层；读版本级恒 false → 误冻结（rationale.md）
PRE_CUR_BUILD=$(jq -r ".versions.\"$PRE_RELEASE_VERSION\".current_build // empty" "$BASELINE_FILE")
# ⛔ 必须把 build 也用转义双引号插进 jq 源码（与 phase-3-4.md 同款写法），不能用 --arg（理据见 rationale.md）。
FIN=$(jq -r ".versions.\"$PRE_RELEASE_VERSION\".builds[]? | select(.build==\"$PRE_CUR_BUILD\") | .ai_report_finalized // false" "$BASELINE_FILE" | head -1)
FIN="${FIN:-false}"
     if [ -n "$AT" ] && [ "$UNC" = "0" ] && [ "$FIN" = "true" ] && [ "$(to_ts "$LAST_DEP")" -le "$(to_ts "$AT")" ]; then
       $BE --version "$PRE_RELEASE_VERSION" del test_loop_missing_streak prerelease_test_hold_streak || true
       echo "✅ 0b 测试收敛：本 build 已于 $AT 测过、已收敛、报告已 finalize → 允许准发布归档"
     else
       # 未测收敛 → 本 tick 不归档（不写 internal_released_at、不把版本移出 aiauto-test 候选），按测试链路是否存活分流
   # ★ 存活判据 = 新鲜心跳 **且** `aiauto_blocked_reason` 对本版不成立（两个字段缺一不可）。
   #   值形如 `frozen:<reason>@<version>`：全局类原因（机器无浏览器/驱动）对任何版本成立，
   #   版本类只对 `@` 后那一版成立。根因详见 rationale.md。
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
         # 暂缓必须有上限（理据见 rationale.md）：记账→判阈→冻结四件套（含
         # unconverged_frozen_head 解冻快照）→发 #4，一次调用做完；未达阈只记账不发通知。
         python3 {{AIDP_HOME}}/scripts/autopilot_fail_handle.py --version "${PRE_RELEASE_VERSION:?}" \
           --phase 2-prerelease-unconverged --reason unconverged \
           --streak-key prerelease_test_hold_streak \
           --threshold "${PRERELEASE_TEST_HOLD_FREEZE:-12}" \
           --extra "unconverged_frozen_head=$(git rev-parse HEAD 2>/dev/null || echo '')" \
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
           # ★ 达阈冻结**不等于**收尾：还须按 `phase-3-9.md`「达阈后的静态-only 收尾」三步实跑
           #   （finalize testSummary + 产报告本体 + 发 #3），否则本 build 的 AI执行报告永停骨架、
           #   #3 永不发 —— 与本分支承诺的「静态-only 收尾」完全相反。
           echo "⛔ 测试链路缺失达阈 → 先按 phase-3-9.md 三步实跑静态-only 收尾（testSummary 如实标"
           echo "   『浏览器实测未执行(测试链路未挂载)』，⛔ 不填 0/0/0、⛔ 不标已测），再继续本步"
         fi
       fi
       PRERELEASE_HOLD=1
     fi
   fi

   # ── 0T 中间过渡版本兜底（在双门冻结【之后】、收尾【之前】判；把"假告警冻结"翻转成"按过渡版本归档"）──
   # 触发条件：双门已卡到阈值、刚写下冻结（deploy-unreachable / unconverged / config-missing），
   #   同时【已存在更新版本的研发执行计划】= 用户已开下一版规划 → 按约定 2 细则「中间过渡版本」，
   #   本版是用户显式跳过、不需正式发布的过渡版 → 直接归档准发布
   #   （`--no-tag` 本就不是正式发布，SQL/文档/memory 照常沉淀），并**如实**记「未经部署/测试收敛」。
   # ⛔ 必须等到阈值才判、不能一进门就判（关键，别"优化"掉；理据见 rationale.md）。
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
           # ★ 通配到底：`[0-9][0-9]_研发执行计划.md` 匹配不到 `01_M1研发执行计划.md` /
           #   `01_研发执行计划-张三.md` 等合规拆分形态 → 过渡版本漏判
           ls "docs/plans/$nv/"*研发执行计划*.md >/dev/null 2>&1 || continue
           TRANSITIONAL=1; NEWER_V="$nv"; break
         done
         if [ "$TRANSITIONAL" = "1" ]; then
           echo "🔀 0T 中间过渡版本：$PRE_RELEASE_VERSION 双门卡到阈值（$FR），且 $NEWER_V 的研发执行计划已存在"
           echo "   → 用户已开下一版规划 = 本版不需正式发布；撤销本次冻结、跳过双门，直接归档准发布（--no-tag）"
           $BE --version "$PRE_RELEASE_VERSION" del needs_human needs_human_reason aiauto_frozen_at \
             freeze_reason prerelease_deploy_block_streak prerelease_test_hold_streak test_loop_missing_streak || true
           # 顶层 aiauto_blocked_reason 只在指向本版时才清（可能是别的版本写的，不能误清）
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
   if [ "$PRERELEASE_HOLD" = "1" ]; then
     echo "→ 本 tick 到此结束 Phase 2（不归档准发布、不写 internal_released_at）→ 继续同 tick 的 Phase 3（若 TARGET_VERSION 非 null）"
     # run_state 写盘：把 hold 原因挂进 pending_actions，未清空即本 Phase 未完成（invariants 阶段推进不变式）
     $BE --version "$PRE_RELEASE_VERSION" run-state "2-prerelease" "2-prerelease" "" \
       --summary "准发布前置门未过（0a 部署就绪 / 0b 测试收敛），本 tick 暂缓归档" \
       --pending "prerelease-hold"
   fi
   ```
   > 双门通过（部署就绪 + 测试已收敛，或 `DEPLOY_EXPECTED=0` 无需部署/测试）→ 继续下面 1~4 步准发布归档；任一门未过（`PRERELEASE_HOLD=1`）或尾段让位（`PRERELEASE_YIELD=1`）→ **跳过 Phase 2 的 1~4 步**（不写 internal_released_at）、直接进同 tick 的 Phase 3，版本留待重新部署 / 测试收敛 / 人工介入。**⛔ 此处不 `exit`**（理由见本节开头「门的强制形态」）。
   >
   > **第三条出口 = 0T 中间过渡版本**：双门卡到阈值本应冻结、但已有更新版本的研发执行计划时，翻转为**照常归档**（`prerelease_transitional=true`）。它**不放宽双门本身**——只在「门已判死 + 开发确已前进」这一确定组合下，把「冻结待人 + 假告警 #4」换成「归档收尾」。

1. **里程碑通知 #pre-start（见 0.1bis）**：
   ```
   🏷️ {项目名称} {PRE_RELEASE_VERSION} · 准发布启动（--no-tag 模式）
   触发：本版本所有 Sprint 已关闭，autopilot 自动归档
   动作：SQL 整理 + 文档清理 + memory 同步 + push commit（不打 tag）
   ```
   > `prerelease_transitional=true` 时，通知**加一行如实说明**（不得省略、不得说成"已收敛"）：
   > `🔀 中间过渡版本：{NEWER_V} 已开始规划，本版未经部署/测试收敛（{FR}）即归档，不做正式发布`

2. **跑 `/version {PRE_RELEASE_VERSION} --no-tag --unattended`**（用 `Skill` 工具或命令端编排）：
   - ★ **必传 `--unattended`（7×24 兜底铁律）**：Phase 2 准发布**始终透传**，不按 `LOOP_UNATTENDED` 分流（理据见 `rationale.md`「Phase 2 为何恒传 --unattended」）。
   - 走 `/version` Step 3.1~3.6 的归档流程
   - Step 3.4.2 **被跳过**（不打 tag）
   - Step 3.4.3 仍 push commit（含 SQL 归档）
   - Step 3.6 输出 "准发布报告"
   - 失败 → 走「失败处置」流程（⛔ 不是只写这一句：「失败处置」= 记账 + 判阈 + 冻结四件套 + 发 #4 五步，必须**可执行地**跑）：

  ```bash
  eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command autopilot --shell)"
  # ⛔ 版本必须是 `PRE_RELEASE_VERSION`（理据见 rationale.md「Phase 2 的失败处置传哪个版本」）
  python3 {{AIDP_HOME}}/scripts/autopilot_fail_handle.py --version "${PRE_RELEASE_VERSION:?}" \
    --phase 2-prerelease --reason release-blocked \
    --why "准发布归档失败：归档流程 Step 3.1~3.6 未走完"
  # 退出码：0=已记账让位本 tick／3=已冻结（达阈或无唤醒源）／2=入参错（⛔ 此时什么都没写）
  ```


3. **回写 baseline**（标记已准发布）——⛔ **必须是可执行语句**：此前这里给的是一个 JSON
   **示例块**，而下方步骤 5 的 run-state 摘要却写着「已写 internal_released_at」，
   声称已写、实际没写。字段恒空 ⇒ 该版本永远留在 `current-version` 候选集里，
   状态机不进 S3，测试链路持续重测**已归档**的版本。
   ```bash
   eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell)"
   python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version "$PRE_RELEASE_VERSION" \
     set internal_released_at @now
   ```

4. **里程碑通知 #pre-done（见 0.1bis）**：
   ```
   ✅ {项目名称} {PRE_RELEASE_VERSION} · 准发布完成
   commit：{hash} | 分支：{branch}
   📌 正式部署时手动跑 /version {PRE_RELEASE_VERSION} 补打 tag
   ```
   > `prerelease_transitional=true` 时同样**加一行如实说明**：
   > `🔀 中间过渡版本归档：未经部署/测试收敛（{FR}）；如需转正式发布，请先部署+实测再跑 /version {PRE_RELEASE_VERSION}`

5. **★ 本片收尾必写 `run_state`（分片末尾硬动作，见 `invariants.md`「阶段推进不变式」——漏写即断点续跑失效）**：
   ```bash
   eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell)"
   # ⛔ next_phase 恒 done（理由见 rationale.md「归档版的游标不得代写下一版的阶段」）
   python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version "$PRE_RELEASE_VERSION" \
     run-state "2-prerelease" "done" "" \
     --summary "准发布归档完成（--no-tag），已写 internal_released_at，#pre-done 已发" --pending ""
   ```
