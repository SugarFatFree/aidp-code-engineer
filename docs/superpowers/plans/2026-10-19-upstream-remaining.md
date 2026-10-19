# 上游剩余能力完整落地 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成上游 3f24fda8..3ac201f9 审阅后剩余的全部适用能力：级联触发按阶段收口、测试用例生成与实测边界、规模/缓存/阳性探针工具接线，以及测试链路 stuck 熔断。

**Architecture:** 保留 `commit_gate.py` 作为变更事实与台账解析的单一信源，但移除其“每日首次提交派收口”的职责；实际收口只由 `/version`、`/sprint-batch`、`/sprint-autopilot` 的明确阶段触发。测试链路通过 `baseline_edit.py run-state` 维护 Phase 进入计数，再由通用 `check_stuck_phase.py` 判定“不失败也不推进”。所有新增脚本必须接入真实 flow/command，并登记 README、测试、bundle。

**Tech Stack:** Python 3 标准库、Bash flow、现有 baseline/state 机制、Node/离线报告工具。

---

### Task 1: 约定 22 级联触发面改为阶段收口

**Files:**
- Modify: `.aidp/scripts/commit_gate.py`
- Modify: `.aidp/scripts/tests/test_commit_gate.py`
- Modify: `.aidp/reference/开发期族增量.md`
- Modify: `.aidp/reference/约定细则-2.md`
- Modify: `.aidp/commands/sprint-batch.md`
- Modify: `.aidp/flows/sprint-batch/step-6.md` / `rationale.md`
- Modify: `.aidp/flows/version/release-5.md`
- Modify: `.aidp/flows/sprint-autopilot/phase-3-4.md`
- Create: `.aidp/flows/sprint-autopilot/phase-3-4b.md`
- Modify: `.aidp/scripts/README.md`

- [ ] **Step 1: 锁定新触发矩阵测试**

增加回归断言：

```python
# commit_gate 仍返回 pending_cascade 摘要，但不再返回 should_dispatch_cascade，
# stale 不再生成 cascade-stale 义务或 stderr「每日首次提交」派单告警。
assert "pending_cascade" in info
assert "should_dispatch_cascade" not in info
assert "cascade-stale" not in info["debts"]
```

同时为阶段入口建立文本断言：`release-5.md` 保留版本级收口，`phase-3-4b.md` 存在并包含 `cascade_dev_closed_at` / `cascade_case_closed_at` build 级幂等标志，`sprint-batch` 不再把 Step 5.5 描述为通用兜底收口。

- [ ] **Step 2: 从 commit_gate 移除每日派单义务**

保留 `pending_cascade()`、`cascaded_not_cleaned`、格式漂移、归档未删和绕过判定；删除输出字段 `should_dispatch_cascade`、`cascade-stale` debt 及其恒打印告警。`--cascade-now` 仍只抑制 `suspected_cascade_bypass`。

- [ ] **Step 3: 添加 autopilot Phase 3.1.6 阶段收口分片**

实现：

```bash
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command autopilot --shell)"
V="$TARGET_VERSION"; B="$BUILD"
FAMS=""
[ "${ENTRY_MODE:-full}" != "test-only" ] && FAMS="需求,设计,计划"
[ "${SKIP_AIAUTO_TEST:-0}" != 1 ] && FAMS="${FAMS:+$FAMS,}用例"
DEV_DONE=$($BE --version "$V" --build "$B" get cascade_dev_closed_at --default "")
CASE_DONE=$($BE --version "$V" --build "$B" get cascade_case_closed_at --default "")
```

阶段收口只处理白名单族；子 Agent 第一动作重新读取台账；`ENTRY_MODE=test-only` 不收需求/设计/计划；成功/失败都写 build 级幂等标志；收口门同时跑 `check_cascade_landing.py --ledger-closed` 与 `--worktree`。

- [ ] **Step 4: 删除 sprint-batch 的旧通用 Step 5.5 触发文案**

保留 Step 5.6 落点/终态门，说明 `/sprint-full -> sprint-dev --cascade-now` 已覆盖逐 Sprint 即时级联；`--skip-aiauto-test` 不得伪造“测试前必须收口”的理由。

- [ ] **Step 5: 更新约定正文与 README**

把“四个收口点 / 每日首次提交 / commit_gate should_dispatch”改成三个入口：`/version` 规划期、`/version` 发布期、`/sprint-autopilot` 阶段级联。所有历史解释写最终行为，根因放 rationale。

- [ ] **Step 6: 定向测试、镜像、提交**

```bash
python3 .aidp/scripts/tests/test_commit_gate.py
python3 .aidp/scripts/check_convention30_prose.py
python3 .aidp/scripts/check_script_callers.py
python3 skills/aidp-code-engineer/scripts/mirror_to_bundle.py --check
```

### Task 2: 测试用例生成与实测边界

**Files:**
- Modify: `.aidp/commands/sprint-dev.md`
- Modify: `.aidp/flows/sprint-dev/postdev-writeback-1.md`
- Modify: `.aidp/commands/sprint-selftest.md`
- Modify: `.aidp/flows/sprint-aiauto-test/phase-2-1.md`
- Modify: `.aidp/scripts/check_case_ledger_pending.py`
- Modify: `.aidp/scripts/tests/test_offchain_scope.py` 或 `test_guard_scripts.py`

- [ ] **Step 1: 定义“是否需要实测”唯一事实**

在开发链路结束时记录 `versions.{V}.sprints.{NNN}.aiauto_test_required`：由本轮是否进入 `/sprint-autopilot` 编排、`--skip-aiauto-test`、用户显式 `/sprint-aiauto-test` 三类事实共同决定。开发期纯技术内部调整可不生成正式用例，但必须写 `aiauto_test_required=false` 留痕；一旦测试入口真实启动，前置门要求用例集存在且完整。

- [ ] **Step 2: 用例生成条件与欠账状态写入 baseline**

`/sprint-selftest` 在 `aiauto_test_required=false` 时只生成增量册记录，不产正式用例分册；在 `true` 时必须生成正式用例并让 `check_case_ledger_pending.py` 归零，否则记录 `case_ledger_pending` 并阻止通过结论。

- [ ] **Step 3: 测试前置门消费该状态**

`phase-2-1.md` 2.0.0 先读 `aiauto_test_required`：未要求实测则明确输出“本轮不适用，未启动浏览器测试”；要求实测则按现有 `check_case_ledger_pending.py` 退出码 0/1/2 分流，禁止把未级联用例当作老用例全绿。

- [ ] **Step 4: 添加双侧回归**

覆盖：纯技术调整不产正式用例但有留痕；要求实测且增量未级联时退出 1；要求实测且台账归零时通过；缺失状态字段 fail-closed 按需要实测处理。

### Task 3: 接入规模预算、前置缓存和批量阳性探针

**Files:**
- Create: `.aidp/scripts/check_scale_budget.py`
- Create: `.aidp/scripts/preflight_cache.py`
- Create: `.aidp/scripts/batch_probe.py`
- Modify: `.aidp/flows/sprint-dev/postdev-writeback-1.md`
- Modify: `.aidp/flows/sprint-autopilot/phase-0-1.md` / `phase-0-6.md`
- Modify: `.aidp/scripts/README.md`
- Modify: `.aidp/scripts/tests/run.sh`, `.aidp/scripts/tests/README.md`

- [ ] **Step 1: 移植三个标准库脚本并适配 `{{AIDP_HOME}}`**

保留上游脚本的 JSON/退出码契约；`preflight_cache` 只缓存成功且键包含 git HEAD、依赖文件 fingerprint、run_id；`batch_probe` 必须快照全部目标文件后再注入，任何异常走 finally 还原。

- [ ] **Step 2: 接规模预算**

在开发档位判定后、产物生成后调用 `check_scale_budget.py --version ... --tier ...`，输入本轮已落盘的 `dev_scale` 与结构性变更事实；Important 只告警，报告必须输出实际 cases/design_docs/tasks/lines 与预算。

- [ ] **Step 3: 接前置检查缓存**

在 autopilot Phase 0 与 aiauto-test Phase 0 的重复检查之间，以同一 `run_id`、同一检查名和输入 fingerprint 读写缓存；命中时打印来源，失败不入缓存，跨 tick 不复用。

- [ ] **Step 4: 接批量阳性探针**

把现有 `selfcheck.py` 中可批量执行的多个静态门探针迁移到 JSON probes 描述，确保阴性侧绿、阳性侧红、finally 还原；保留现有单门探针作为不适合批量的语义门。

- [ ] **Step 5: 测试与接线门**

```bash
python3 .aidp/scripts/check_scale_budget.py --self-check
python3 .aidp/scripts/preflight_cache.py --self-check
python3 .aidp/scripts/batch_probe.py --self-check
python3 .aidp/scripts/check_script_callers.py
```

### Task 4: 测试链路 run_state 与 stuck 熔断

**Files:**
- Create: `.aidp/scripts/check_stuck_phase.py`
- Modify: `.aidp/flows/sprint-aiauto-test/phase-0-1.md`
- Modify: `.aidp/flows/sprint-aiauto-test/phase-1.md`
- Modify: `.aidp/flows/sprint-aiauto-test/phase-2-1.md`
- Modify: `.aidp/flows/sprint-aiauto-test/phase-3-3.md`
- Modify: `.aidp/scripts/tests/test_unattended_recovery.py` or `test_guard_scripts.py`

- [ ] **Step 1: 统一测试链路 Phase 出口 run_state 写入**

每个测试链路 tick 在进入 Phase 时使用 `baseline_edit.py run-state` 写 `current_phase`；首次进入设置 `phase_first_entered_at`，同一 Phase 重入递增 `phase_enter_count`，Phase 推进时清零入口计数并更新 `phase_started_at`。写失败必须 fail-closed。

- [ ] **Step 2: 移植 stuck 判定**

`check_stuck_phase.py --command aiauto-test --version V --phase 2-exec --freeze` 只在 `phase_enter_count >= 8` 且滞留超过 7200 秒时触发；退出码 0/3 与开发链路的 0/1/3 语义分开，冻结统一走 `autopilot_fail_handle.py --command aiauto-test --reason stuck-phase`。

- [ ] **Step 3: 在 Phase 1/2/3 出口接门**

测试链路每次 Phase 出口先写状态，再执行 stuck 判定；判定到达阈值时写四件套、#4 和本地告警台账，阻止继续测试；正常推进时不误冻。

- [ ] **Step 4: 双侧回归**

覆盖：次数未达阈值不冻、时长未达阈值不冻、两者同时满足冻结、写盘失败返回阻塞、从任意子目录调用仍能定位脚本、环境类冻结可自动复探。

- [ ] **Step 5: 最终定向验证、镜像、提交、推送**

```bash
python3 .aidp/scripts/tests/test_commit_gate.py
python3 .aidp/scripts/tests/test_guard_scripts.py
python3 .aidp/scripts/tests/test_unattended_recovery.py
python3 skills/aidp-code-engineer/scripts/mirror_to_bundle.py --check
python3 skills/aidp-code-engineer/scripts/verify.py . --template --read-only
```

只跑定向测试，不启动全量 `run.sh`。
