# sprint-autopilot · Phase 3 详情分片 [3/13]（3.1 版本规划 + 启动通知）

> 本文件是 `/sprint-autopilot` 命令 **Phase 3** 详情的**第 3/13 片**（每片 ≤20KB，命令主体按子步进度依次 `Read` 对应分片）。
> - **本片覆盖**：3.1（版本规划 + 启动通知 + 里程碑通知 #1/#1b）；3.1.0 跳过规划门独立在 `phase-3-3b.md`
> - **同 Phase 其它分片**：phase-3-1.md … phase-3-9.md（含 phase-3-3b.md；清单见命令主体 Phase 3 骨架表「所在分片」列）
>
> ⚠️ **权威性**：进入 Phase 3 后以本文件为准逐项执行，不得凭命令主体骨架或记忆略过任一子步骤/硬门。
> ⚠️ **维护**：随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-autopilot/phase-3-3.md`。理据见同目录 `rationale.md`。

---

### 3.1 版本规划（★ 已规划则跳过）+ 启动通知

#### 3.1.0 版本规划已存在检测（跳过规划门）

> ★ 本步判据独立成片：见同目录 **`phase-3-3b.md`**——`PLANNING_DONE`（**六类**规划产物齐全）、P0-1 incremental 硬判据②（规划齐）③（无未关闭 Sprint）、P0-0 跳过规划的两个合法来源、以及裁定结果回写 baseline。**必须先读它并跑完裁定**，再继续本片 step 1；跳过它 = 用增量名义免除规划 / 丢下未跑完的 Sprint。

1. **里程碑通知 #1 规划开始（见 0.1bis；仅当真正要跑规划才发）**——**仅当 `PLANNING_DONE=0` 或带 `--force-replan`** 时经 `notify.py --auto` 发送（公共字段 项目名/工作目录/时间 + 下列内容）；`PLANNING_DONE=1`（规划已提前完成）→ **跳过本通知**，直接进 step 2/3（规划完成通知仍会发）：
   （**首行 = 通知标题 `--title`，按 0.1bis「通知标题固定前缀」必带项目中文名称**；其余为正文）
   ```
   📋 {项目名称} {TARGET_VERSION} · 规划开始      ← 标题（未铸 build，不带 _Build{N}）
   版本：{TARGET_VERSION}
   触发：{TRIGGER_REASON}（如 "PRD 目录有新 commit: abc1234"）
   PRD 目录：docs/requirements/{TARGET_VERSION}/产品提供/（含 {N} 份 .md）
   模式：{--full-auto | --single-sprint}
   分支：{branch}
   即将生成：研发需求 · 详细设计 · 接口 · 数据库 · 研发执行计划 · 研发自测用例
   失败/决策卡点会主动 @你，无消息即一切顺利
   ```

2. **跑 `/version {TARGET_VERSION} [--unattended]`**（⛔ 无人值守下必带——`/version` 有多个交互门）（**仅当 `PLANNING_DONE=0` 或带 `--force-replan`**；否则整步跳过）（含里程碑参数，从 Phase 0.6 收集到的 `autopilot_decisions` 推断）：
   - **★★ 上下文隔离（#2 子 Agent 委派，仅 `LOOP_UNATTENDED=1`）**：`/version` 是全链路最重的一段，**优先委派【独立子 Agent】执行**（隔离上下文）——子 Agent 在其自身上下文里读 `.aidp/commands/version.md` 跑完整规划链 + 终审，只回传 **compact JSON**：`{version, planning_done:bool, artifacts:[主产物路径], sprint_count:N, auditor_verdict:"pass"|"block", key_counts:{req,design,api,db,cases}, fail_reason?}`。主流程据此发 #1b / 写 `run_state` / 进 3.1.5。**⛔ 交互式（`LOOP_UNATTENDED=0`）不委派**：`/version` 的决策类 `AskUserQuestion` 需用户在场应答，子 Agent 无法与用户交互 → 内联执行（见下条）。**回退**：子 Agent 工具不可用 → 内联执行，行为与产物完全不变。理据（为何这是规划 tick 破 1M 的最大来源）见 rationale.md。
     > ⛔⛔ **委派 × flag 一致性铁律（二选一，不许骑墙）**：`LOOP_UNATTENDED=0` 时**要么严格内联不委派**，
     > **要么**委派时**绝不给子 Agent 传 `--unattended`**（改走「子 Agent 回传 `needs_interaction` →
     > 主流程代问 → 结果回灌」协议）。**"委派"与"传 unattended"是两个独立决定，绝不因前者顺手做后者**：
     > 该 flag 的语义是"没人可答"，而交互式恰恰有人可答（实测：交互式误委派并传该 flag，决策类
     > 弹窗全被跳过、`pending_actions` 挂 7 小时无人处置）。**出口自检**：「是否委派」「是否传该 flag」
     > 与 `LOOP_UNATTENDED` 三者必须自洽，不自洽即停下改正、不得带着不一致继续推进。委派失败 → **先走「子 Agent 派发失败的分层重试与降级」（P0-3 C1–C3，见 `flows/sprint-autopilot/invariants.md`）**：瞬时服务端错误（529/503/超时）指数退避重试 → 退避用满换**更小粒度**（把 `/version` 拆成 requirements/design/plan 分段各自委派）→ 仍不成才内联（带 C3 上下文预算护栏、不足则分批落盘续跑）；**唯有确定性失败**（子 Agent 早退 / 回传不合 compact 契约 / audit 反复 Critical）才按「失败处置」记 `dev_fail_streak`，不静默当成功。
   - **★ `--unattended` 按 `LOOP_UNATTENDED` 条件透传**：
     - **交互式（`LOOP_UNATTENDED=0`：用户当面跑 `--once` / 明确执行意图，非 `/loop` 守护）→ 调 `/version {TARGET_VERSION}`（★ 不带 `--unattended`）**：让 `/version` 走**完整交互式版本规划**，其决策类 `AskUserQuestion` 用户在场、该发生就发生。
     - **无人值守（`LOOP_UNATTENDED=1`：`/loop` 守护 / cron `--no-loop`）→ 调 `/version {TARGET_VERSION} --unattended`**（7×24 兜底铁律）：`/version` 的交互门按 Phase 0.6 预声明的 `autopilot_decisions` 自动落值或走保守默认，绝不挂死。
   - `--full-auto` 模式下自动用 `autopilot_decisions` 填所有 `AskUserQuestion` 决策
   - **强制不跳过** `version-auditor`（独立子 Agent 审计八项 A–H）；`--unattended` 下审计 `block` 时 `/version` 自动修复 3 轮仍不过 → **返回 `audit-block` 失败信号**（不弹窗，见 `version.md` Step 2.4.7）
     > 📌 **本步的审计 ≠ Phase 3.3 的 autopilot 终审，两者产物必须是【不同文件】**：`/version` 内部审计写 `docs/audit/{V}/version-output-audit-YYYY-MM-DD.md`；Phase 3.3 的 autopilot 终审另写 `docs/audit/{V}/version-output-audit-{BUILD}.md`。**严禁**让本步产物顶替 Phase 3.3 终审（同名会使收尾门 glob 到上游遗留文件即判通过、终审没跑也能过），命名规则单一信源见 `phase-3-8.md` Phase 3.3。
   - 失败（含 `/version` 返回 `audit-block`）→ 走「失败处置」流程（记 `dev_fail_streak` + 熔断，见本命令「失败处置」）——⛔ 五步（记账/判阈/冻结四件套/发 #4/让位）必须**可执行地**跑，散文不算：

   ```bash
   eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --command autopilot --shell)"
   # ★ reason 必须按**失败类别**分流，⛔ 不能一律 audit-critical：后者属人工专属解冻档
   #   （`_HUMAN_ONLY`，探针一律不解冻），把「子 Agent 派发失败 / 网络抖动 / 超时」这类
   #   瞬态错误按它冻上，是把一次重试就能过去的事变成必须人来救；而 needs_human_reason
   #   还会把人指向一份根本没有 Critical 的审计报告。
   # ⛔ 下面这行由 Claude 按 `/version` 的实际返回**就地改写**为 audit-block 或 other，
   #    取不到时保持 other —— 默认值必须落在**可自动解冻**的一侧（宁可多试一轮，
   #    不要把瞬态错误钉成人工专属）。
   PLAN_FAIL_KIND=other    # ← 仅当 /version 明确返回 audit-block 时改成 audit-block
   # ⛔ reason 写**字面量**、别收进变量再 `--reason "$_R"`：`check_freeze_contract` 的写入者
   #   识别看的是字面 reason，走变量会让这两个枚举值双双变成「零写入者」——而那道门正是
   #   用来发现「读侧留了解冻分支、写侧其实没人写」的，先把自己弄瞎不可接受。
   V3="--version ${TARGET_VERSION:?} --phase 3.1-plan"
   case "$PLAN_FAIL_KIND" in
     audit-block) python3 .aidp/scripts/autopilot_fail_handle.py $V3 --reason audit-critical \
       --why "version-auditor 审计 block 且自动修复 3 轮未过，需人工裁决" ;;
     *)           python3 .aidp/scripts/autopilot_fail_handle.py $V3 --reason plan-transient \
       --why "/version 规划未走完（派发/网络/超时等），非审计 block" ;;
   esac
   # 0=已记账让位本 tick／3=已冻结（达阈或无唤醒源）／2=入参错（⛔ 什么都没写）

   ```

   - ★ `PLANNING_DONE=1` 且无 `--force-replan` → **跳过本步**，日志记 "版本规划已存在，跳过 /version"（规划完成通知由 step 3 统一发，不在此另发）
   - **★ 本步结束落盘终审结论**（出口摘要要用它；跨 Bash 调用取不到裸 shell 变量）。
     ⛔ **必须是可执行语句**：写成散文里的 inline-code 且值留 `<pass|warn|block>` 占位符时，
     读回恒空 → 出口的 `${AUDIT_VERDICT:-pass}` 把 **block / warn 恒记成 pass**。
     `VERDICT` 由执行体按本步实际结论就地代入（同 `IS_LOOP_CONTEXT` 范式）：

     ```bash
     VERDICT=pass   # ← 按本步终审结论就地改为 pass / warn / block；跳过本步时填 pass
     python3 .aidp/scripts/autopilot_tick_flags.py set --command autopilot AUDIT_VERDICT "$VERDICT"
     ```

3. 解析 `docs/plans/{TARGET_VERSION}/01_研发执行计划.md` 得到 Sprint 总数 N（跳过规划时直接读现存文件）→ 发 **里程碑通知 #1b 规划完成（见 0.1bis；总是发）**（公共字段 + 下列内容）：
   （**首行 = 通知标题 `--title`，按 0.1bis「通知标题固定前缀」必带项目中文名称**；其余为正文）
   ```
   ✅ {项目名称} {TARGET_VERSION} · {版本规划完成 | 复用已有版本规划}      ← 标题（未铸 build，不带 _Build{N}）
   版本：{TARGET_VERSION}
   将执行：{N} 个 Sprint
   产物：
     - 研发需求：docs/requirements/{TARGET_VERSION}/研发需求/
     - 详细设计：docs/design/detail/{TARGET_VERSION}/
     - 执行计划：docs/plans/{TARGET_VERSION}/01_研发执行计划.md
   下一步：进入 Phase 3.2 批量开发
   ```


### 3.1bis ★ 用例前置资源对账【补账】（规划刚产出用例册的那一刻，唯一有效落点）

> Phase 0 的 **0.6bis 对账门**（`phase-0-9.md`）在 full 模式下必然判 `no-casebook`——用例册是本 Phase 的 `/version` Step 2.4.3.5 才生成的，Phase 0 时它还不存在。**若不在这里补跑一次，full 模式下这道门等于从未存在**（下游正是 full 模式踩的）。

```bash
eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --shell)"
python3 .aidp/scripts/check_testdata_prereq.py --version "$TARGET_VERSION" --record
```

- `exit 0` → 通过，继续 3.1.5。
- `exit 1`（`gaps`）→ **口径与 0.6bis 完全一致、不另立一套**：交互式在**此刻**一次性 `AskUserQuestion` 问清并写回 `01_测试环境与账号.md` + 同步 `01_研发自测方案.md` §3 + commit；无人值守留占位 + WARN 继续。⛔ 无论哪条路径，**此后都不得以"缺前置数据/账号"为由暂停**（`phase-3-1.md` 非法跳过借口清单）。

---

## ⛳ 本 Phase 出口：`run_state` 写盘（**硬动作，不可跳过**）

> 单一信源 = `invariants.md`「阶段推进不变式」，此处只给本分片的**具体实参**。
> ⛔ 漏这一步 = 状态机不存在：`next_phase` 恒空 → tick 中途中断后下一 tick 从 Phase 3.0 全量重推；
> `next_sprint` 恒空 → Stop hook 的「中间 yield-tick 豁免」判据取不到值 → 每个中间 tick 都误跑一次
> 收尾门（必 FAIL）并白烧熔断额度。**本 Phase 的实质动作做完、离开本分片之前立即执行**：

> ⛔⛔ **写出口【之前】必须先过完成校验——「阶段完成 = 产物与结论都已落盘可校验」，不是「活已经
> 派出去了」**（与「强制仪式不可精简硬门」同级铁律；实测事故与连带失效见 `rationale.md`）。
> 出口前逐条自检：
>
> | # | 校验 | 不通过怎么办 |
> |---|---|---|
> | ① | **六类规划产物存在**（需求/详设/计划/自测用例/自测方案/测试环境与账号；判据复用 `version.md` Step 2.4.5「三步落盘自检」，不另立） | 补齐后再写出口 |
> | ② | **审计报告存在且 `verdict ∈ {pass, warn}`** | `block` → 按 Step 2.4.7 修复重审 |
> | ③ | **走委派的**：已**实际收到** compact JSON 且 `planning_done==true` | 没收到就等；等不到走 P0-3 C1–C3 降级，**不得先写出口再等** |
> | ④ | **委派 × flag 自洽**（见上方一致性铁律） | 不自洽即停下改正 |
>
> ⛔ `--summary` 不得写「已派发/执行中/等待回传」：`run-state` 对这类进行时自述**硬性拒写**
> （`exit 1`）。中途进度用 `--pending` 表达。

```bash
eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --shell)"
BE="python3 .aidp/scripts/baseline_edit.py"; V="${TARGET_VERSION}"
# ★ FIX-7 输入漂移检测：PRD 可能在规划**进行中**被产品改（实测：22:12 新增 §3.7/§3.8 并改写
#   两条验收标准，而快照只在规划开始时记过一次）——此时四类产物是按**旧 PRD** 产的，却会被
#   当成"本版规划已完成"。出口重算一次 PRD 摘要与快照比对，不符即 WARN 并要求走补充模式重跑。
#   复用既有检测器、**不带 `--commit`**（只报不写，绝不在此把中途变更推平进基线——那会让这批
#   变更此后永远检测不出，见 phase-1.md「短路时不回写 tracked_files」同源坑）。
eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --shell)"   # 读回 AUDIT_VERDICT（3.1 step 2 落盘）等
eval "$(python3 .aidp/scripts/autopilot-prd-watch.py --version "$V" --shell 2>/dev/null || echo SHOULD_RUN=0)"
[ "${SHOULD_RUN:-0}" = "1" ] && echo "⚠️ PRD 在本次规划【进行中】发生变化（${TRIGGER_REASON:-}）：四类产物可能基于旧 PRD，请按 /version 补充模式重跑增量并走约定 22 级联"
$BE --version "$V" run-state "3.1-plan" "3.1.5-build" "" \
  --summary "Phase 3.1 版本规划完成（PLANNING_DONE=${PLANNING_DONE:-1}）：需求/设计/计划/自测用例/自测方案/测试环境六类产物已就位，auditor verdict=${AUDIT_VERDICT:-pass}" --pending ""
```

> 规划被跳过（`PLANNING_DONE=1` 且无 `--force-replan`）时同样要写——写盘记录的是"本 Phase 已推进"，不是"本 Phase 做了活"（此时①②仍需成立：产物本就在，才谈得上"可跳过"）。
