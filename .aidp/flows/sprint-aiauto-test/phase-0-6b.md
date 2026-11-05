<!-- 二次切分 · phase-0 片6b/9：0.2 自愈交接 / 通知与报告归属 -->
# sprint-aiauto-test · 执行分片 [6b/9]（0.2 交接与归属）

> 先执行 `phase-0-6.md`。本片逐项执行，不得省略硬门；随脚手架同步。

### 0.2（续）自愈式交接

`NEED_HANDOFF=1` 表示 **current_build 已定稿，或 AI执行报告骨架缺失**。必须在 Phase 1/2 开测、认领驱动及归档待确认项之前处理。`--once` / `--target` 只豁免已测去重，不能解除报告不可变锁；无 current_build 的 standalone 不交接、不铸官方 build、不产 HTML 报告。

**① 重新读取真源并登记一次交接**（分片间 shell 变量不持久；不得沿用旧 BUILD）：

```bash
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version ${TARGET_VERSION:?}"
BUILD=$($BE get current_build --default "")
NEED_HANDOFF=0
if [ -n "$BUILD" ]; then
  FINALIZED=$($BE --build "$BUILD" get ai_report_finalized --default false)
  if [ "$FINALIZED" = true ] || [ ! -f "docs/reports/$TARGET_VERSION/AI执行报告/data/${BUILD}.js" ]; then
    NEED_HANDOFF=1
  fi
fi
[ "$NEED_HANDOFF" = 1 ] || { echo "NEED_HANDOFF=0：真源已变化，回 phase-0-6.md 重新取归属"; exit 0; }
: "${PREFLIGHT_RUN_ID:?须沿用本次 parse 的 run id}"
PREVIOUS_HANDOFF=$($BE get aiauto_handoff_run_id --default "")
[ "$PREVIOUS_HANDOFF" != "$PREFLIGHT_RUN_ID" ] || { echo "⛔ 同 run 交接未完成，失败返回，不递归调用 autopilot"; exit 2; }
$BE set aiauto_handoff_run_id "$PREFLIGHT_RUN_ID" || exit 1
HANDOFF_ARGS="--skip-dev --target $TARGET_VERSION --preflight-run-id $PREFLIGHT_RUN_ID"
RETURN_ARGS="--target $TARGET_VERSION --preflight-run-id $PREFLIGHT_RUN_ID"
if [ "${HAS_ONCE_FLAG:-0}" = 1 ]; then
  HANDOFF_ARGS="$HANDOFF_ARGS --once"; RETURN_ARGS="$RETURN_ARGS --once"
fi
if [ "${LOOP_UNATTENDED:-0}" = 1 ]; then
  HANDOFF_ARGS="$HANDOFF_ARGS --unattended"; RETURN_ARGS="$RETURN_ARGS --unattended"
  if [ "${HAS_WAKE_SOURCE:-0}" = 1 ]; then
    HANDOFF_ARGS="$HANDOFF_ARGS --no-loop"; RETURN_ARGS="$RETURN_ARGS --no-loop"
  fi
fi
printf '交接命令：/sprint-autopilot %s\n返回命令：/sprint-aiauto-test %s\n' "$HANDOFF_ARGS" "$RETURN_ARGS"
```

**② 同步交接，仅调用一次**：执行体保存上面输出的两个完整命令。原测试实例交还控制权，不再进入后续阶段；同一用户请求的编排立即 invoke 交接命令，要求 autopilot 子流程 R 完成后按**返回命令**调用测试链路，`--target`、`--preflight-run-id`、`--once` 和无人值守标志均原样传递。

- **锁与调用边界**：原测试实例按 `reference/agent-tools.md`「tick 占位收尾」用自己 Phase 0 的 token 完成收尾，session 占位释放成功后才 invoke autopilot；不得从锁文件取别人的 token。OS token=`agent_loop` 不执行 finish、不释放 wrapper 的 flock，后续同步子调用须继承原 `AIDP_TICK_COMMAND` / `AIDP_TICK_TOKEN` 环境，现有准入门只允许该 wrapper 的真实子链复用。若开发链已被其它 tick 占用，则交接未完成，走下方失败处置，不能假称已测试。
- **唯一铸号与骨架生产者仍是 autopilot R-1（`sprint-autopilot/phase-3-4.md`）**：旧 build 已 finalized 时铸新号，记录 `retest_of`；test-only 无新代码时由该围栏登记 `deploy_reuse_of=last_deployed_at`。测试侧不改 current_build、不手造报告、不用 `--force-amend`。R-2 按需验证/部署，R-3 产骨架并过委派前硬门；返回后重新读新 current_build，部署复用登记须仍匹配当前部署。
- **不递归、不重复铸号**：同一 `--preflight-run-id` 只登记一次交接。回调若仍已定稿或缺骨架，`phase-0-6.md` 硬退失败；健康的未定稿新 build 直接续测，不再次调用 R-1。新的外部请求由 parse 生成新 run id，可重试失败交接；旧标记不阻挡新请求。R-1 对已有骨架、未定稿且未收尾的活动 build 按原规则复用。
- **`--once` / 无唤醒源必须同步完成交接与新 build 实测收尾**，不能以“等下次 tick”作为成功返回。交接返回后原测试实例直接结束，不能带旧 BUILD 再测一次。若父 autopilot 已在等待本测试回调，失败应返回该父调用，不能递归 invoke 第二个 autopilot。

**③ 失败才记账**：正常定稿后的新一轮不是故障，交接前不得调用失败处理器（无唤醒源会首次即冻、导致交接根本未执行）。autopilot 返回失败、被占用、未回调测试或本 run 回调仍不可测时，外层编排立即执行一次：

```bash
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
python3 {{AIDP_HOME}}/scripts/autopilot_fail_handle.py --command aiauto-test --version "$TARGET_VERSION" \
  --phase 0.6-handoff --reason handoff-exhausted --streak-key handoff_fail_streak \
  --threshold "${HANDOFF_FAIL_THRESHOLD:-3}" \
  --why "test-only 交接未取得可测的新 build/执行骨架，未完成本次实测"
```

退出码 3 已冻结，2 是处置失败；均不得继续实测或报告成功。未达阈亦结束本次失败交接；有唤醒源时后续 tick 用新 run id 重试。成功回调在 `phase-0-6.md` 可测分支清零 `handoff_fail_streak`。R-4 的真实 testSummary、两份报告定稿与 #3 通知仍由测试链路在 #F 后完成。

### 通知配置与报告归属

- **autopilot 委派路径**（current_build 存在）：继承 `memory/aidp-config.yaml` 的 notify 配置，不发 #0a；测试链路早期里程碑为 #D。
- **standalone 路径**（无 current_build，不能仅凭 `--once` 判定）：Phase 0.2 子步骤 4 自读 notify；未启用或渠道未配置则静默跳过，不弹窗收集。
- 报告路径恒为本地 `docs/reports/{V}/`，通知链接使用仓库相对路径。
