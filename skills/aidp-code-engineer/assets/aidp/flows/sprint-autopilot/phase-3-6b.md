# sprint-autopilot · Phase 3 详情分片 [6b/13]（3.2.1 Step C 监控执行 + 失败重试 + 出口游标）

> 本文件是 `phase-3-6.md` 的**二次切分**（前片达 20KB 上限）。前片覆盖 Step A0 / A / B；
> 本片覆盖 **Step C（监控执行 + 失败重试）** 与 **出口 run-state 写盘**。
> ⚠️ **权威性**：与前片同级，不得因它是续片而略过任一项。
> ⚠️ **维护**：随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-autopilot/phase-3-6b.md`。理据见同目录 `rationale.md`。

---

**Step C — 监控执行 + 失败重试（最多 `cicd.max_retries` 次，默认 3）**

> ⛔⛔ **CICD 失败的第一动作恒为【重试】、不是【自查代码】**：无论在流程内还是流程外发现，**第一动作恒为重新触发一次**，绝不先排查自身代码 / 本地复现。
> - **理由**：见 `rationale.md`「CICD 失败为何先重试而非自查」（成本不对称 + 表象不可区分）。
> - **⚠️ 重试用满 `cicd.max_retries`（默认 3）次【之前】禁止启动本地完整构建**（`vite build` / `mvn package` / `gradle build`，另见约定 35）；用满仍**稳定**失败才转自查。
> - **可追踪**：重试次数持久化到 `cicd_run.cicd_retry_count`（= `CICD_RETRY`），收尾报告如实呈现「本轮重试 N 次」——偶发失败不许悄悄消失在过程里。

⛔ **`CICD_RETRY` 不在此处置 0**——它跨重试累计、真源在 baseline `cicd_run.cicd_retry_count`，
由下方可执行块读回（逐字执行「前置置 0」等于每次重试都清零、≤3 上限永不达到）。

**★ 轮询由 `cicd_watch.py` 执行（约定 31.5 指定的单一信源）—— ⛔ 不在本步自行实现轮询**：

```bash
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell)"
V="${TARGET_VERSION:?}"; BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py"
RID=$($BE --version "$V" get cicd_run.run_id --default "")
[ -n "$RID" ] || { echo "⛔ 取不到 RESOLVED_RUN_ID（Step A0/A/B 应已落 cicd_run.run_id）"; exit 1; }
B=$($BE --version "$V" get current_build --default "")
GIT_PUSH_COMMIT=$([ -n "$B" ] && $BE --version "$V" --build "$B" get push_commit --default "" || echo "")
[ -n "$GIT_PUSH_COMMIT" ] || { echo "⛔ 取不到本 build 的 push_commit，禁止轮询或放行部署"; exit 1; }
PL=$($BE --version "$V" get cicd_run.pipeline --default "")
CENV=$($BE --version "$V" get cicd_run.env --default "test")
if [ -n "$PL" ]; then TARGET=(--pipeline "$PL"); else TARGET=(--env "$CENV"); fi
mkdir -p memory/.aidp
# 有唤醒源留给下一 tick；无唤醒源最多轮询 300+120 秒，同 tick 必有明确终态或冻结。
CICD_POLL_WINDOW=480
[ "${HAS_WAKE_SOURCE:-0}" = "0" ] && CICD_POLL_WINDOW=300
python3 {{AIDP_HOME}}/scripts/cicd_watch.py --mode poll --run-id "$RID" --commit "$GIT_PUSH_COMMIT" "${TARGET[@]}" --version "$V" \
  --timeout "$CICD_POLL_WINDOW" > memory/.aidp/cicd-poll.json
WRC=$?
VERDICT=$(jq -r '.verdict // ""' memory/.aidp/cicd-poll.json)
if [ "$VERDICT" = "running" ] && [ "${HAS_WAKE_SOURCE:-0}" = "0" ]; then
  python3 {{AIDP_HOME}}/scripts/cicd_watch.py --mode poll --run-id "$RID" --commit "$GIT_PUSH_COMMIT" "${TARGET[@]}" --version "$V" \
    --timeout 120 > memory/.aidp/cicd-poll.json
  WRC=$?
  VERDICT=$(jq -r '.verdict // ""' memory/.aidp/cicd-poll.json)
  if [ "$VERDICT" = "running" ]; then
    python3 {{AIDP_HOME}}/scripts/autopilot_fail_handle.py --command autopilot --version "$V" --build "$B" \
      --freeze-now --phase 3.2.1-deploy --reason deploy-unreachable \
      --why "CICD 运行 $RID 在本次无唤醒源调用的 420 秒轮询预算内未终态，需人工续跑"
  fi
fi
cat memory/.aidp/cicd-poll.json   # 一行 JSON：verdict / next_action / reason / run_id / run_commit / next_retry_count
# poll 已逐次核对 view_run.commit 与本 build 的 push_commit；不以响应 SHA 覆盖基线锚点。
# ★ 取到状态（非 unreachable）= 平台可达 → 清连续不可达计数
case "$VERDICT" in unreachable|"") : ;; *) $BE --version "$V" del cicd_unreachable_streak cicd_cli_fail_streak || true ;; esac
```

**按 `verdict` / 退出码分流（下表即上游穷尽判定的对照，⛔ 不再在本步复述轮询细节）**：

| `verdict` / rc | 含义（对应旧散文档位） | 本步处置 |
| :- | :- | :- |
| `success` / rc=0 | ② 成功（仅代表**部署完成**、不代表可测） | 进 Step D 就绪探针 |
| `running` / rc=0 `next_action=poll` | 单次调用时限内未终态（正常长构建） | **不记失败、不耗重试**：出口写游标 `3.2.1-deploy` 让位下 tick，下 tick 续 poll 同一 `run_id` |
| `failed` / rc=1 `next_action=retry` | ③ 失败且重试配额未尽 | 走下方「失败重试」，对**同一** `RESOLVED_RUN_ID` 执行 `cicd_watch.py --mode retry` |
| `failed` / rc=2（重试用尽） | ③ 失败且 `CICD_RETRY` 已满 | 走下方「失败重试」的 **2.** 分支（既有「失败处置」流程，`--reason deploy-unreachable`）—— ⛔ 别另造冻结原因 |
| `unreachable` / rc=2 | ④ CICD 平台不可达（**取不到状态** ≠ 取到失败态，多为网络抖动 / 平台瞬时 5xx） | **不计入 `CICD_RETRY`、不空触发**；按 streak 记账（下方「瞬时故障记账」），连续 3 次才冻结 `cicd-unreachable`（环境类，自动复探）；游标留 `3.2.1-deploy` 下 tick 重试 |
| `vanished` / rc=2 | ⑤ 锚定运行消失 / 被顶替 | **绝不静默滑到"最近一条"顶替**；`freeze cicd-run-vanished "<原因>"`，**不写 `last_deployed_at`** |
| `commit-mismatch` / rc=2 | 锚定运行的 commit 不符或为空 | **禁止成功放行与部署证据**；按运行被顶替即时冻结 `cicd-run-vanished`，不消耗重试配额 |
| `unknown-status` / rc=2 | 状态字样连续无法归类 | 转人工（`freeze pipeline-unknown`），不消耗重试配额 |
| `parse-error` / rc=2 | 脚手架自身解析缺陷（**非**环境问题） | 报修脚本 + 按 31.5 最保守口径直接重试；⛔ 不回头查业务代码 |
| rc=3 `cli-missing` / `unauthenticated` / `provider-unavailable` | 提供方 CLI 未安装 / 未登录 / 令牌过期（7×24 下常见） | 按 streak 记账（下方「瞬时故障记账」），连续 3 次冻结 `cicd-cli-unavailable`（环境类，装好 / 重新登录后自动复探放行）；游标留 `3.2.1-deploy` |
| rc=3 `disabled` / `not-configured` / `bad-args` | 未接入 CICD（没有可监听的远端流水线） | 回 `phase-3-5b.md`「部署动作」的**未接入 CICD 轻量分支**（`cicd_skipped` 语义不变，不冻结） |

**★ 瞬时故障记账 + ⑤ 即时冻结（④ / ⑤ / rc=3 CLI 类，⛔ 可执行）**：

```bash
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command autopilot --shell)"
# CJ = 刚跑的那次 cicd_watch 输出（Step A0/A/B 的 detect / trigger、本步 poll / retry 同样适用）
V="${TARGET_VERSION:?}"; CJ="${CJ:-memory/.aidp/cicd-poll.json}"
VERDICT=$(jq -r '.verdict // ""' "$CJ" 2>/dev/null); REASON=$(jq -r '.reason // ""' "$CJ" 2>/dev/null)
case "$VERDICT" in
  unreachable)
    python3 {{AIDP_HOME}}/scripts/autopilot_fail_handle.py --command autopilot --version "$V" --build "${BUILD:-}" \
      --phase 3.2.1-deploy --reason cicd-unreachable --streak-key cicd_unreachable_streak --threshold 3 \
      --why "CICD 平台不可达：$REASON（请检查网络 / 平台状态）" ;;
  vanished|commit-mismatch)   # 锚定运行消失或 SHA 错绑：即时冻结（不放行探针、不写 last_deployed_at）
    python3 {{AIDP_HOME}}/scripts/autopilot_fail_handle.py --command autopilot --version "$V" --build "${BUILD:-}" \
      --freeze-now --phase 3.2.1-deploy --reason cicd-run-vanished \
      --why "锚定的 CICD 运行消失或被顶替：$REASON" ;;
  cli-missing|unauthenticated|provider-unavailable)
    python3 {{AIDP_HOME}}/scripts/autopilot_fail_handle.py --command autopilot --version "$V" --build "${BUILD:-}" \
      --phase 3.2.1-deploy --reason cicd-cli-unavailable --streak-key cicd_cli_fail_streak --threshold 3 \
      --why "CICD 提供方 CLI 不可用（$VERDICT）：$REASON（请安装 / 重新登录 cicd.provider 对应 CLI 或补令牌环境变量）" ;;
esac
```

> ⛔ **为什么必须调它而不是自己轮**：自写轮询会丢掉 `next_action` / `next_retry_count` 两个**唯一重要的产出**，
> 且会在本链路里长出第二套判定 —— 而 31.5 指定的单一信源是 `cicd_watch.py`。
> 脚本已实现锚定 `--run-id` 精确轮询（⛔ 不滑最新）、重试计数与穷尽判定，
> **不留"既非成功也非失败"的悬空态**（悬空态正是"失败了却不重试"的根源）。理据见 `rationale.md`。

**★ 本步的冻结与重试计数（⛔ 可执行，不是散文）** —— 上方 ④/⑤ 与下方 1./2. 一律调它：

```bash
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell)"
BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py"; V="${TARGET_VERSION:?}"
# ★ CICD_RETRY 必须**从 baseline 读回**：轮询跨多次 Bash 调用，shell 变量不持久。
#   写成「进入本步前置 CICD_RETRY=0」并逐字执行，等于每次重试都把计数清零 → ≤3 上限永不达到。
CICD_RETRY=$($BE --version "$V" get cicd_run.cicd_retry_count --default 0)
CICD_MAX=$(python3 {{AIDP_HOME}}/scripts/aidp_config.py get cicd.max_retries 2>/dev/null); CICD_MAX=${CICD_MAX:-3}
# ★ 冻结四件套一次写齐（缺任一即解冻判据恒假 / 落 unknown 不进任何解冻分支）
# ★★ **本函数是全 Phase 的通用冻结助手**：⛔ 任何冻结点都必须调它，不得自己拼
#   冻结四件套 —— 自己拼的那些恰恰是漏发 #4 的来源（落盘写了、通知没发）。
#   本步的即时冻结点（B 触发被拒 / C⑤ / 重试 auto_trigger 闸 / 重试被拒）全部经它；④ 与 CLI 类走上方 streak 记账；
#   调用形态：freeze <freeze_reason> "<needs_human_reason>"
freeze() {   # $1=freeze_reason  $2=needs_human_reason
  # ★★ 落盘 + #4 + 本地告警台账（memory/.aidp/alerts.jsonl）由 fail_handle 一次做完；
  #   同版本同原因已冻结时它是 no-op（不刷新冻结时刻、不重发 #4）。
  #   #4 是冻结时刻唯一对外可见的信号且不在收尾门期望通知集里，⛔ 不得自己拼四件套漏发。
  python3 {{AIDP_HOME}}/scripts/autopilot_fail_handle.py --command autopilot --version "$V" --build "${BUILD:-}" \
    --freeze-now --phase 3.2.1-deploy --reason "$1" --why "$2"
}
```

**失败重试（③ 命中时）——显式循环，绝不首次失败就放弃：**
1. **`CICD_RETRY < cicd.max_retries`（默认 3）→ 必须重跑失败的运行**：
   ```bash
   eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell)"
   # ★ 从 baseline 读回（轮询跨多次 Bash 调用，shell 变量不持久）
   # ⛔ 读侧恒空 → 重试锚不到失败运行、retry_count 恒 0 使 ≤3 上限失效。
   #    写入点见 Step A0 ① / Step B 与本分支（均为可执行语句，点号即嵌套路径）。
   BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py"; V="${TARGET_VERSION:?}"
   # ⛔ RESOLVED_RUN_ID 必须读回：它是 Step C 精确轮询的锚点。取空 ⇒ 要么滑到"最近一条"
   #    （本段明令 ⛔ 严禁），要么命中判定 ⑤「锚定运行消失」把一次正常部署冻成 cicd-run-vanished。
   RESOLVED_RUN_ID=$($BE --version "$V" get cicd_run.run_id --default "")
   RESOLVED_RUN_COMMIT=$($BE --version "$V" get cicd_run.run_commit --default "")
   [ -n "$RESOLVED_RUN_ID" ] || { echo "⛔ 取不到 cicd_run.run_id，禁止盲目触发新运行"; exit 1; }
   AUTO=$(python3 {{AIDP_HOME}}/scripts/aidp_config.py get cicd.auto_trigger 2>/dev/null); AUTO=${AUTO:-true}
   if [ "$AUTO" != "true" ]; then
     echo "⛔ cicd.auto_trigger=false → 不执行重跑，按 freeze cicd-auto-trigger-off 冻结"
   else
     PL=$($BE --version "$V" get cicd_run.pipeline --default "")
     CENV=$($BE --version "$V" get cicd_run.env --default "test")
     if [ -n "$PL" ]; then TARGET=(--pipeline "$PL"); else TARGET=(--env "$CENV"); fi
     mkdir -p memory/.aidp
     python3 {{AIDP_HOME}}/scripts/cicd_watch.py --mode retry --run-id "$RESOLVED_RUN_ID" "${TARGET[@]}" \
       --version "$V" --timeout 480 > memory/.aidp/cicd-retry.json
     RRC=$?; cat memory/.aidp/cicd-retry.json
     if [ "$RRC" = "0" ]; then
       $BE --version "$V" bump cicd_run.cicd_retry_count
       NEW_RID=$(jq -r '.run_id // empty' memory/.aidp/cicd-retry.json)
       if [ -z "$NEW_RID" ]; then
         # ★ 平台不回显新 run id（jenkins / command）→ 同 tick 按原 commit 重新 detect 锁定，⛔ 不留旧失败 run_id 空耗配额
         python3 {{AIDP_HOME}}/scripts/cicd_watch.py --mode detect --commit "${RESOLVED_RUN_COMMIT:?}" "${TARGET[@]}" \
           --version "$V" --timeout 480 > memory/.aidp/cicd-detect.json
         NEW_RID=$(jq -r '.run_id // empty' memory/.aidp/cicd-detect.json)
       fi
       # 以新锚精确轮询（GitHub Actions 为同一 id；GitLab CI / Jenkins 可能是新 id）
       [ -n "$NEW_RID" ] && $BE --version "$V" set cicd_run.run_id "$NEW_RID"
       echo "RETRY FROM=$RESOLVED_RUN_ID NEW=${NEW_RID:-<detect 未命中，下 tick 再 detect>} COMMIT=$RESOLVED_RUN_COMMIT"
     fi
   fi
   ```
   - **★★ 重跑 = 失败运行的原 commit**：`--mode retry` 重跑那次失败的运行（GitHub Actions 重跑失败 job、run id 不变；GitLab CI 重试该 pipeline；Jenkins 重新构建该 Job），不主动取分支新 HEAD。`next_action=poll` → 回 Step C 顶部按输出的 `run_id`（已写回 `cicd_run.run_id`）精确监控；`next_action=detect`（平台不回显新 id）→ 上面代码块已按 `RESOLVED_RUN_COMMIT` 同 tick 跑 `--mode detect` 重新锁定并回写 `cicd_run.run_id`。锁定后核对其 commit `== RESOLVED_RUN_COMMIT`，不等（平台按 Job 最新配置重建取了新 HEAD）→ 记 `commit_verified=false` 并在报告中注明。⛔ 不得改用 `--mode trigger` 充当"重试"——那是部署一份从未被确认的分支新 HEAD（理据见 rationale.md）。
   - **授权 = `cicd.auto_trigger`（默认 true，无需人工 accept）**：为 `false` 时 → 调 `freeze cicd-auto-trigger-off "cicd.auto_trigger=false，CICD 第 $((CICD_RETRY+1)) 次失败需人工重跑（run $RESOLVED_RUN_ID）"` 后结束本步。
   - **重试本身被拒**（`--mode retry` exit 2 / `verdict=retry-failed`，如运行已过保留期不可重跑、权限不足、`command` 提供方未配 `retry` 模板）→ 把输出的 `reason` **如实抄进** `needs_human_reason` 与 #4 正文，调 `freeze cicd-unreachable "<reason>"`，别只写「重试失败」。
2. **`CICD_RETRY >= cicd.max_retries`（已重跑满 3 次仍失败）→ 才**走「失败处置」流程（里程碑通知 #4 @用户介入，正文标注「CICD 流水线连续 {CICD_RETRY+1} 次执行失败」+ 附最近一次失败的 job / 日志线索，取输出的 `run_url` 指向的平台运行页），暂停本轮，**不写 `last_deployed_at`**、不进测试链路。

   ```bash
   eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command autopilot --shell)"
   python3 {{AIDP_HOME}}/scripts/autopilot_fail_handle.py --version "${TARGET_VERSION:?}" --build "${BUILD:-}" \
     --phase 3.2.1-deploy --reason deploy-unreachable \
     --why "CICD 流水线连续 $((CICD_RETRY+1)) 次执行失败，已重跑满上限" \
     --section "CICD 流水线连续 $((CICD_RETRY+1)) 次执行失败；附最近一次失败的 job / 日志线索。"
   # 0=已记账让位本 tick／3=已冻结／2=入参错（⛔ 什么都没写）。⛔ 不写 last_deployed_at、不进测试链路。
   ```


⛔ **RED FLAG（三条必须逐条守住）**：见 `rationale.md`「Step C 的三条 RED FLAG」。


---

## ⛳ 本 Phase 出口：`run_state` 写盘（**硬动作，不可跳过**）

> 单一信源 = `invariants.md`「阶段推进不变式」，此处只给本分片的**具体实参**。
> ⛔ 漏这一步 = 状态机不存在（`next_phase`/`next_sprint` 恒空的连锁后果见 rationale.md）。**本 Phase 的实质动作做完、离开本分片之前立即执行**：

```bash
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell)"
BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py"; V="${TARGET_VERSION}"
# 从本次 poll 的持久 JSON 读回，拒绝旧 run 或别的 commit 的 success。
RID=$($BE --version "$V" get cicd_run.run_id --default "")
B=$($BE --version "$V" get current_build --default "")
PUSH=$([ -n "$B" ] && $BE --version "$V" --build "$B" get push_commit --default "" || echo "")
CJ=memory/.aidp/cicd-poll.json
VERDICT=$(jq -r '.verdict // ""' "$CJ" 2>/dev/null)
POLL_RID=$(jq -r '.run_id // ""' "$CJ" 2>/dev/null)
POLL_COMMIT=$(jq -r '.run_commit // ""' "$CJ" 2>/dev/null)
if [ "$VERDICT" = "success" ] && [ -n "$RID" ] && [ "$POLL_RID" = "$RID" ] \
   && [ -n "$PUSH" ] && [ "$POLL_COMMIT" = "$PUSH" ]; then
  $BE --version "$V" run-state "3.2.1-deploy" "3.2.1-probe" "done" \
    --summary "Phase 3.2.1 Step A–C 完成：部署已触发、流水线成功；就绪探针（Step D）待跑" \
    --pending "deploy-probe"
else
  # 未终态 / ③失败重试中 / ④CICD 平台不可达 / CLI 不可用 / ⑤锚定运行消失 —— 一律留在本步，下 tick 重来
  $BE --version "$V" run-state "3.2.1-deploy" "3.2.1-deploy" "done" \
    --summary "Phase 3.2.1 Step C 尚无流水线成功证据；保留部署游标与待办" \
    --pending "cicd-watch"
fi
```

> ⛔ **`next` 必须是 `3.2.1-probe`、不是 `3.3-audit`**：Step D 就绪探针在下一分片 `phase-3-7.md`，写 `3.3-audit` 会让中断后的续跑**整段跳过探针**（理据见 `rationale.md`「Phase 3 相关根因」）。部署未就绪而本 tick 让位时：`next` 写 `3.2.1-deploy`（下 tick 从头重探）+ `--pending "deploy-probe"`。
