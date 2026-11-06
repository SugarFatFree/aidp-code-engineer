# sprint-autopilot · Phase 3 详情分片 [6b/14]（3.2.1 Step C 监控执行 + 失败重试 + 出口游标）

> 本文件续接 `phase-3-6.md` 的 Step A0/A/B；覆盖 Step C 与出口 `run_state`。
> ⚠️ 与前片同级，进入 Step C 前必须 Read，不得略过。
> ⚠️ 维护：随脚手架下发；理据见同目录 `rationale.md`。

---

**Step C — 监控执行 + 失败重试（最多 `cicd.max_retries` 次，默认 3）**

⛔ CICD 明确失败的第一动作恒为重试。未用满配额之前，不查业务代码、不启动本地完整构建（`vite build` / `mvn package` / `gradle build`）。用满仍稳定失败才转自查，详见约定 31.5 / 35 与 `rationale.md`。

`cicd_run.cicd_retry_count` 是跨 tick 的重试真源，不能在进入本步时置 0；只在重试实际受理后自增，报告保留实际次数。**只有明确 `failed` 才消耗重试预算**，平台不可达、未知状态、授权请求均不消耗。

**统一结果消费**：每次 detect / poll / trigger / retry 后，必须将刚获得的 JSON 和**原始退出码**传给 `cicd_watch.py --mode consume`。该模式不调用平台写接口，只通过 `baseline_edit.py` 落证据/游标、通过 `autopilot_fail_handle.py` 做失败记账或以实际 `--freeze-now` 即时冻结。每个围栏独立执行，不依赖前一个 Bash 的变量或 `freeze()` 函数。

- **rc=0、success、probe**：重新核对本 build 的 `push_commit`、请求 `expected_commit`、流水线与 `run_id`；只有 SHA 匹配才记成功并转 Step D。
- **rc=4、probe、degraded=true、push_auto_deploy=true**：仅接受 `not-observed/unreachable/vanished/unknown-status`，并核对请求绑定。落 `cicd_run.status=unknown`、`degraded=true`、原 `degraded_reason` 和完整 `observation`，转 Step D；**不冻结、不记流水线 success、不写 `last_deployed_at`、不清不可达计数**。
- **rc=4、need-accept、accept**：这是 Command 提供方的授权请求，与降级放行无关。保留原响应，冻结 `cicd-auto-trigger-off`，交互模式把请求交用户确认；无人值守等待人工，绝不自动追加 `--accept`。`auto_trigger=true` 也不能替代平台这道授权。
- 其余 probe / rc4 组合一律拒绝推进。真正成功后调用 fail_handle 的 `--success`，仅清与失败 phase 和 build 作用域匹配的计数，不解除已有冻结。

**轮询围栏（精确锁定运行，不滑到最新一条）**：

```bash
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell)"
V="${TARGET_VERSION:?}"; BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py"
B=$($BE --version "$V" get current_build --default "")
RID=$($BE --version "$V" get cicd_run.run_id --default "")
GIT_PUSH_COMMIT=$([ -n "$B" ] && $BE --version "$V" --build "$B" get push_commit --default "" || echo "")
GIT_PUSH_AT=$([ -n "$B" ] && $BE --version "$V" --build "$B" get push_at --default "" || echo "")
if [ -z "$RID" ] || [ -z "$GIT_PUSH_COMMIT" ]; then
  python3 {{AIDP_HOME}}/scripts/autopilot_fail_handle.py --command autopilot --version "$V" --build "$B" \
    --freeze-now --phase 3.2.1-deploy --reason cicd-run-vanished \
    --why "缺少本 build 的 push_commit 或 CICD run id，禁止盲目监听和放行部署"
  exit 3
fi
PL=$($BE --version "$V" get cicd_run.pipeline --default "")
CENV=$($BE --version "$V" get cicd_run.env --default "test")
if [ -n "$PL" ]; then TARGET=(--pipeline "$PL"); else TARGET=(--env "$CENV"); fi
mkdir -p memory/.aidp
CICD_POLL_WINDOW=480
[ "${HAS_WAKE_SOURCE:-0}" = "0" ] && CICD_POLL_WINDOW=300
WRC=0
python3 {{AIDP_HOME}}/scripts/cicd_watch.py --mode poll --run-id "$RID" --commit "$GIT_PUSH_COMMIT" --push-at "$GIT_PUSH_AT" \
  "${TARGET[@]}" --version "$V" --max-retries "${CICD_MAX_RETRIES:-3}" --timeout "$CICD_POLL_WINDOW" \
  > memory/.aidp/cicd-poll.json || WRC=$?
VERDICT=$(jq -r '.verdict // ""' memory/.aidp/cicd-poll.json)
if [ "$VERDICT" = "running" ] && [ "${HAS_WAKE_SOURCE:-0}" = "0" ]; then
  WRC=0
  python3 {{AIDP_HOME}}/scripts/cicd_watch.py --mode poll --run-id "$RID" --commit "$GIT_PUSH_COMMIT" --push-at "$GIT_PUSH_AT" \
    "${TARGET[@]}" --version "$V" --max-retries "${CICD_MAX_RETRIES:-3}" --timeout 120 \
    > memory/.aidp/cicd-poll.json || WRC=$?
  VERDICT=$(jq -r '.verdict // ""' memory/.aidp/cicd-poll.json)
  if [ "$VERDICT" = "running" ]; then
    python3 {{AIDP_HOME}}/scripts/autopilot_fail_handle.py --command autopilot --version "$V" --build "$B" \
      --freeze-now --phase 3.2.1-deploy --reason deploy-unreachable \
      --why "CICD 运行 $RID 在本次无唤醒源调用的 420 秒轮询预算内未终态，需人工续跑"
    exit 3
  fi
fi
cat memory/.aidp/cicd-poll.json
python3 {{AIDP_HOME}}/scripts/cicd_watch.py --mode consume --version "$V" \
  --result memory/.aidp/cicd-poll.json --result-code "$WRC" || exit $?
```

**按结果分流（原始退出码与 JSON 必须一起判，不凭 rc 单独放行）**：

| 结果 | 处置 |
| :- | :- |
| success / rc0 / probe | consume 写 `3.2.1-probe`，Read `phase-3-7.md` 跑 Step D |
| 合法 degraded / rc4 / probe | 保留 unknown 与原因，consume 写 `3.2.1-probe`，Step D 探实际部署目标；未经平台确认不冒充成功 |
| running / rc0 / poll | 有唤醒源留 `3.2.1-deploy` 下 tick 续同一 run；无唤醒源按上面 420 秒预算冻结 |
| failed / rc1 / retry | 进入下方重试围栏，同一失败运行、同一 push commit |
| failed / rc2（配额已满） | consume 以 `--freeze-now --reason deploy-unreachable` 实际冻结；不写部署成功证据、不进测试 |
| unreachable / rc2 | 版本级 `cicd_unreachable_streak`，阈值 3 冻结 `cicd-unreachable`；不空触发 |
| vanished / rc2，commit-mismatch / rc2 | consume 即时冻结 `cicd-run-vanished`，不滑旧运行、不消耗重试 |
| unknown-status / rc2，trigger-failed / rc2 | consume 即时冻结 `pipeline-unknown`，保留原 reason |
| retry-failed / rc2 | consume 即时冻结 `cicd-unreachable`，原 reason 落 `needs_human_reason` 与 #4 |
| auto-trigger-off / rc2，need-accept / rc4 | consume 即时冻结 `cicd-auto-trigger-off`；不执行未经授权写动作 |
| cli-missing / unauthenticated / provider-unavailable / rc3 | 版本级 `cicd_cli_fail_streak`，阈值 3 冻结 `cicd-cli-unavailable`，可自动环境复探 |
| disabled / not-configured / bad-args / rc3 | 未接入 CICD 按 `phase-3-5b.md` 轻量分支；参数错误先修正再跑，不制造成功证据 |
| parse-error / rc2 | 报修脚本，按 31.5 最保守口径直接重试；不查业务代码，不自写平台轮询 |

环境类冻结恢复由 Phase 0 的 `autopilot_unfreeze.py --env-reprobe` 负责：环境复探放行时清相应失败/重试预算，再从 `3.2.1-deploy` 真正执行部署。不能要求冻结后先出现 `last_deployed_at` 才重试，避免自锁；人工类原因仍遵既有人工解冻边界。

**失败重试围栏（仅当前 poll 确认 failed/retry，或已按 31.5 处理 parse-error 后执行）**：

```bash
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell)"
BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py"; V="${TARGET_VERSION:?}"
B=$($BE --version "$V" get current_build --default "")
RESOLVED_RUN_ID=$($BE --version "$V" get cicd_run.run_id --default "")
GIT_PUSH_COMMIT=$([ -n "$B" ] && $BE --version "$V" --build "$B" get push_commit --default "" || echo "")
GIT_PUSH_AT=$([ -n "$B" ] && $BE --version "$V" --build "$B" get push_at --default "" || echo "")
CICD_RETRY=$($BE --version "$V" get cicd_run.cicd_retry_count --default 0)
CICD_MAX=${CICD_MAX_RETRIES:-3}
if [ "$CICD_RETRY" -ge "$CICD_MAX" ]; then
  python3 {{AIDP_HOME}}/scripts/autopilot_fail_handle.py --command autopilot --version "$V" --build "$B" \
    --freeze-now --phase 3.2.1-deploy --reason deploy-unreachable \
    --why "CICD 流水线连续 $((CICD_RETRY+1)) 次执行失败，已重跑满上限；运行 $RESOLVED_RUN_ID"
  exit 3
fi
[ -n "$RESOLVED_RUN_ID" ] && [ -n "$GIT_PUSH_COMMIT" ] || {
  python3 {{AIDP_HOME}}/scripts/autopilot_fail_handle.py --command autopilot --version "$V" --build "$B" \
    --freeze-now --phase 3.2.1-deploy --reason cicd-run-vanished --why "重试缺运行 id 或本 build push_commit"
  exit 3
}
AUTO=$(python3 {{AIDP_HOME}}/scripts/aidp_config.py get cicd.auto_trigger 2>/dev/null); AUTO=${AUTO:-true}
if [ "$AUTO" != "true" ]; then
  python3 {{AIDP_HOME}}/scripts/autopilot_fail_handle.py --command autopilot --version "$V" --build "$B" \
    --freeze-now --phase 3.2.1-deploy --reason cicd-auto-trigger-off \
    --why "cicd.auto_trigger=false，需人工重跑 $RESOLVED_RUN_ID（commit $GIT_PUSH_COMMIT）"
  exit 3
fi
PL=$($BE --version "$V" get cicd_run.pipeline --default "")
CENV=$($BE --version "$V" get cicd_run.env --default "test")
if [ -n "$PL" ]; then TARGET=(--pipeline "$PL"); else TARGET=(--env "$CENV"); fi
mkdir -p memory/.aidp; RRC=0
python3 {{AIDP_HOME}}/scripts/cicd_watch.py --mode retry --run-id "$RESOLVED_RUN_ID" --commit "$GIT_PUSH_COMMIT" "${TARGET[@]}" \
  --version "$V" --max-retries "$CICD_MAX" --timeout 480 > memory/.aidp/cicd-retry.json || RRC=$?
cat memory/.aidp/cicd-retry.json
python3 {{AIDP_HOME}}/scripts/cicd_watch.py --mode consume --version "$V" \
  --result memory/.aidp/cicd-retry.json --result-code "$RRC" || exit $?
if [ "$RRC" = "0" ]; then
  $BE --version "$V" bump cicd_run.cicd_retry_count
  if [ "$(jq -r '.next_action' memory/.aidp/cicd-retry.json)" = "detect" ]; then
    # 平台不回显新 id：删除旧失败锚点，按原 push_commit 重锁；不以旧 run 空耗配额。
    $BE --version "$V" del cicd_run.run_id
    DRC=0
    python3 {{AIDP_HOME}}/scripts/cicd_watch.py --mode detect --commit "$GIT_PUSH_COMMIT" --push-at "$GIT_PUSH_AT" "${TARGET[@]}" \
      --version "$V" --timeout 480 > memory/.aidp/cicd-detect.json || DRC=$?
    python3 {{AIDP_HOME}}/scripts/cicd_watch.py --mode consume --version "$V" \
      --result memory/.aidp/cicd-detect.json --result-code "$DRC" || exit $?
  fi
fi
```

重跑已受理后，按新 `run_id` 回 Step C 精确轮询；不能改用 trigger 部署分支新 HEAD。平台不回显 id 且 detect 尚未命中时，下 tick 从 A0 detect 重新锁定，不把旧失败 run 当成新一次。轮询始终核对本 build 的 push SHA，错绑即冻结；最终报告附重试次数与平台 `run_url`。

⛔ 三条 RED FLAG 仍须逐条遵守，见 `rationale.md`「Step C 的三条 RED FLAG」。

---

## ⛳ 本 Phase 出口：消费结果时立即写 `run_state`

**写盘已由每个围栏中的 consume 完成**，不得再从固定 `cicd-poll.json` 推断出口：A0 的合法降级可能根本没有 poll 文件，固定读它也可能读到上一轮 success。`cicd_run.observation` 保存本次原始 rc、JSON、build 与 push_commit，供复核；不跨 tick 重放消费来重复累计失败。

```bash
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell)"
python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version "${TARGET_VERSION:?}" get run_state --default '{}'
```

只有 `next_phase=3.2.1-probe` 才 Read `phase-3-7.md` 跑 Step D，**不得跳到 `3.3-audit`**。其他状态留 `3.2.1-deploy`，已冻结则结束本版当前 tick；真实就绪前一律不写 `last_deployed_at` / `phase_beta_done_at`，不放行测试链路。
