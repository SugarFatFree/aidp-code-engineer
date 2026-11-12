# /sprint-dev — 开发阶段（独立可用；默认 light，formal 由父编排累进）

## 执行身份与授权前置路由（先于本文其余动作）

参数：$ARGUMENTS。解析父 `EXECUTION_CONTEXT` 和显式 `EXPLICIT_SPRINT`；不从历史计划、activeContext 或规模推断身份。子命令/修复/重试/续跑均保留原参数并附 `--execution-context "$EXECUTION_CONTEXT"`。

**独立调用（无父上下文、无显式 Sprint）**：只 Read `{{AIDP_HOME}}/reference/light-entry.md`。下方 `light_task.py start` 包办 resolve + route(dev)，随后从实现步骤继续，**不要再执行一次 start/route**。填写真实写集与验收；默认 `POLICY_ARGS=()`，有限制/额外授权才读 `light-context.md`「入口、继承与 grant revision」。

**有父上下文或显式 Sprint**：按节 Read `{{AIDP_HOME}}/flows/sprint-dev/light-context.md` 的入口规则，执行另一分支；仅新任务生成 `POLICY_ARGS`，嵌套不追加 grant。

<!-- flowvar-check: allow POLICY_ARGS,TASK_WRITE_SET,TASK_ACCEPTANCE,EXPLICIT_SPRINT,AIDP_SESSION_ID -->
```bash
# EXECUTION_CONTEXT 来自入参；EXPLICIT_SPRINT 仅来自用户明确的 Sprint。
CONTEXT_ARGS=()
if [ -n "${EXECUTION_CONTEXT:-}" ]; then
  CONTEXT_ARGS+=(--execution-context "$EXECUTION_CONTEXT")
else
  CONTEXT_ARGS+=(--version "{version}" "${POLICY_ARGS[@]}")
  for W in "${TASK_WRITE_SET[@]}"; do CONTEXT_ARGS+=(--write-set "$W"); done
  for AC in "${TASK_ACCEPTANCE[@]}"; do CONTEXT_ARGS+=(--acceptance "$AC"); done
fi
if [ -z "${EXECUTION_CONTEXT:-}" ] && [ -z "${EXPLICIT_SPRINT:-}" ]; then
  ROUTE_RESULT=$(python3 {{AIDP_HOME}}/scripts/light_task.py start --root . --entry sprint-dev \
    "${CONTEXT_ARGS[@]}") || exit $?
else
  [ -z "${EXPLICIT_SPRINT:-}" ] || [ -n "${EXECUTION_CONTEXT:-}" ] || CONTEXT_ARGS+=(--sprint "$EXPLICIT_SPRINT")
  CONTEXT_RESULT=$(python3 {{AIDP_HOME}}/scripts/entry_context.py resolve --root . --entry sprint-dev \
    "${CONTEXT_ARGS[@]}" --json) || exit $?
  EXECUTION_CONTEXT=$(printf '%s' "$CONTEXT_RESULT" | python3 -c 'import json,sys; print(json.load(sys.stdin)["execution_context"])') || exit $?
  ROUTE_RESULT=$(python3 {{AIDP_HOME}}/scripts/entry_context.py route --root . --entry sprint-dev \
    --execution-context "$EXECUTION_CONTEXT" --phase dev --json) || exit $?
  python3 {{AIDP_HOME}}/scripts/aidp_config.py branch-policy --root . >&2 || exit $?
  BIND_ARGS=()
  [ -z "${AIDP_SESSION_ID:-}" ] || BIND_ARGS+=(--session-id "$AIDP_SESSION_ID")
  python3 {{AIDP_HOME}}/scripts/entry_gate.py bind --if-writable --root . \
    --execution-context "$EXECUTION_CONTEXT" "${BIND_ARGS[@]}" >/dev/null || exit $?
fi
EXECUTION_CONTEXT=$(printf '%s' "$ROUTE_RESULT" | python3 -c 'import json,sys; print(json.load(sys.stdin)["execution_context"])') || exit $?
printf '%s\n' "$ROUTE_RESULT"
```

消费路由动作与错误；`branch_needs_choice=true` 先处理分支选择。无 implement 或空写集只选择当前任务身份、不授写权限，避免复用旧任务；仅只读准备，按真实任务 revise 后重跑绑定才可写代码，不能猜写集。

- **`route=light`**：按 `reference/light-entry.md` 执行实现 → 静态 → `light_task.py all` → `entry_context.py check/complete`，真实失败修复复验后终端 **return**。不进入 formal，不取 Sprint 号、不写卡片/activeContext/started/报告或归档。工具仍经 `entry_gate` 与动作/预算围栏；细则按节读 `light-context.md`。
- **light 并行**：可拆成 ≥2 个互不相交写集（各读≥3或改≥2文件）时，Read `{{AIDP_HOME}}/flows/sprint-dev/light-parallel.md`，先跑 `python3 {{AIDP_HOME}}/scripts/dispatch_plan.py --task "a=f1,f2" --task "b=f3,f4" --emit-prompts --execution-context "$EXECUTION_CONTEXT" --action implement --budget "$BUDGET_JSON"` 再决定是否并行派发；汇合后仍按 light 收口并 return。
- **只有 `route=formal`** 才进入下表；未知 route 停止。正式身份不扩大授权，可选未请求为 NOT_REQUESTED。

## formal 流程

先 Read `{{AIDP_HOME}}/flows/sprint-dev/formal-preflight.md`，执行参数、纪律与前置门，确定 A/B。**进入各阶段的第一动作 = Read 该行分片**；只读适用阶段，禁止一次加载全部 formal 片。分片路径相对 `{{AIDP_HOME}}/flows/sprint-dev/`。

| Phase / 原锚点 | 所在分片 | 适用条件 |
|---|---|---|
| 参数 / 统一决策纪律 / 前置流程 / 参数解析与路径分支 | `formal-preflight.md` | formal 恒适用；控制 flag 不作需求描述 |
| 0A / 0A.5 | `formal-existing.md` | A：已有明确 Sprint；完成后直入 Phase 1 |
| 0B.00 / 0B.0 / 0B.1 | `formal-increment.md` | B：formal 父编排明确累进；开工门→版本落点门→取号及绑定 |
| 0B.1.1 | `formal-docs.md` | B 恒判契约；S 卡与台账，M docs 并行且 test 前汇合，L 开发前成文 |
| 0B.1.3 / 0B.2 | `formal-reversal.md` | B；追加/反转门随事件重入，启动后入 Phase 1 |
| 1 / 1.0pre / 1.0 / 1.1 / 1.1.5 / 1.2 / 1.3 / 1.4 | `formal-development.md` → `phase-1-dev-1.md`、`phase-1-dev-2.md` | A/B 开发；保留两片原子步及围栏 |
| X.0.0 / X.0 / X.2 / X.3 / X.4 / X.5 / X.6 / 审计收口 | `formal-writeback.md` → `postdev-writeback-1.md`、`postdev-writeback-2.md`、`postdev-writeback-3.md` | A/B 开发后；保留三片判据，动作按授权执行 |
| 2–4 / 完成前验证 / 自动串联后续 | `formal-completion.md` | A/B 回写后；skip-test 依真实来源移交或 LIMITED 返回 |

完整参数见 `formal-preflight.md`，用法与输出见 `output-examples.md`；原阶段标题保留。`--unattended` 不弹交互门，`--from-batch` 待裁决交上层。

- `--skip-deadcode-scan`：仅已知全绿地新建场景，跳过 Phase 0A.5 扫描。
