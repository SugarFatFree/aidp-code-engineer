> 本片仅供 formal。先按 `{{AIDP_HOME}}/flows/sprint-dev/light-context.md` 核父身份；light 返回对应能力分支，不执行本片。

<!-- 本文件是 `/sprint-bugfix` 方式 B 的后半段（Step 5~6）执行分片，由 `mode-b.md` 指向。 -->

# /sprint-bugfix · 方式 B · Step 5 ~ 6

> 本文件承接 `mode-b.md`（前置准备 / 独立使用流程 / Step 1 调 bugfix skill / Step 2 推送分类与监听 /
> Step 3 回填 bug 记录 / Step 4 编译校验）；本片含 **Step 5.1 累进产物审计**（⛔ 不得省）。
> ⚠️ **维护**：本文件随脚手架下发；改动后同步 bundle 副本。

#### Step 5：★ 自动回写设计文档

> 本步骤是约定 22「上游文档级联同步」在 bugfix 链路的落地：若变更触达 研发需求 / 详细设计 / 研发执行计划 / 研发自测用例 多层，按约定 22 的 4 级触发表级联补充（与 `/sprint-dev` Step X.0.0 同一套补充文档体系、命名按约定 15），不绕过统一口径。

**触发条件**：修复 bug 引入了设计层面的变更：
- 修改接口签名 / 字段含义
- 新增字段 / 索引 / 约束
- 引入新组件 / 重构公共模块
- 架构级调整（缓存策略、事务边界等）

> ★ **产物落点分两种，⛔ 别混**：**默认（攒批）**只写台账、不产文档；
> **`--cascade-now` / 收口点**走约定 22 级联 —— **就地改各族内容主文档** + 刷 `00_索引.md` 生成时间，
> ⛔ **不新建 `NN_` 分册**（那是产品侧变更与**方式 C 累进新 Sprint**的命名空间；落点门对新建 `NN_` 判 exit 1）。

**★ 执行时机 = 攒批（约定 22 默认形态，同 `/sprint-dev` Step X.0.0）**

> ⛔ **本步默认【不当场跑下面的四级级联】**——它是修复完成后的回写，与 `/sprint-dev` 开发期漂移
> 同性质：**开发过程中只写台账，收口点才成文**（根因见 `rationale.md`）。默认动作 = 把每条变更按
> 一行追加到**受影响的每一族**增量册（四族落点见 `{{AIDP_HOME}}/reference/开发期族增量.md`；
> 同一变更跨族共用同一个 `C-NNN`、只记与该族相关的那一面；不存在则从
> `{{AIDP_HOME}}/templates/_开发期族增量.md` 拷骨架），**然后直接跳到 Step 5.1**。
>
> - 编号由主流程 `python3 {{AIDP_HOME}}/scripts/alloc_id.py --kind C --count 1 --owner orchestrator --version {version} --scope changes` 原子预留；同事件跨四族复用同一 C 号，读取最新台账后串行写入。不可用时保留待登记工作单，不自行 grep 最大号。
> - 一行格式：`- C-{NNN} · MM-DD HH:MM · 改了什么·为什么 · 🔴破坏性（可选）· sprint-{NNN}`
> - 🔴 破坏性变更须同时在台账「⚠️ 已知失准点」段登记失准位置，否则 gate 判 `destructive_unregistered`。
> - **唯一合法例外 = 显式 `--cascade-now`**（或本轮恰好命中收口点）→ 才走下面 1~7 步。
> - ⛔ 不得以"这次 bug 改得大 / 顺手就写了"为由当场级联：`commit_gate.py::suspected_cascade_bypass`
>   以「代码 + 上游规划产物 + 台账没动」三条同现反向检出、抬退出码 3。

**回写步骤（仅document已授权且显式cascade-now或命中收口点时执行；否则只登记实际漂移并到Step 5.1）**

未在route.authorized_actions中的document记NOT_REQUESTED并跳过本环节；已授权分支先执行，再按light-context预留实际资源：

```bash
EXECUTION_CONTEXT="${EXECUTION_CONTEXT:?必须从父任务入参重绑真实上下文路径}"
python3 {{AIDP_HOME}}/scripts/execution_policy.py require-action --root . \
  --execution-context "$EXECUTION_CONTEXT" --action document || exit $?
```
（`{NN}` = 本轮增量序号，各目录共享同一 NN）：
1. 扫描本次修复的 git diff（⛔ 内容从**代码增量**重新产出、不照抄台账；`SINCE=$(git log -1 --format=%H -- <该族主文档>)` 后只 diff 之后的 `code/`，**不全量扫盘**）
2. **★ 研发需求（L1，⛔ 不得跳过）**：变更触达**接口签名 / 字段含义 / 业务规则 / 口径**
   （即上方触发条件第一项，属约定 22 第三类「语义变更」，L1 必产）时，先经
   `/sprint-requirements {version} --execution-context "$EXECUTION_CONTEXT" --ledger-cascade [--unattended]` 编排 → **就地改** `01_研发需求.md`。
   ⚠️ 级联的**最上游一层**；漏它即命中约定 22 的典型漏项「只补了详细设计、把需求与自测用例留在旧口径」。
3. **设计**：经 `/sprint-design {version} --execution-context "$EXECUTION_CONTEXT" --ledger-cascade --scale={档位} [--unattended]` 编排（增量 prompt 驱动 `dev-logic-architect` 做根因分析 + 派生设计）→ **就地改** `docs/design/detail/{version}/` 下的 `01_详细设计.md`·`02_数据库设计.md`·`03_接口设计.md`（按实际范围）。⛔ **不直调 SKILL、⛔ 不新建 `NN_<业务主题>.md` 分册**（落点门 `check_cascade_landing.py` 见到新建 NN_ 即判 exit 1）
4. 如有架构级变更 → 按 `/sprint-design` Step 4.1–4.3 由 **Architect Agent** 增量更新 `docs/architecture/{技术选型,架构约束}.md`；**同时按 CLAUDE.md 约定 8「ADR 必记」追加架构决策记录到 `memory/systemPatterns.md`**（记录：决策点、上下文、替代方案、影响范围、回归路径）
5. 如新增/变更表 → 追加到 `memory/databaseBaseline.md` + 新增 `docs/deployment/{version}/sql/增量/{NN}_<中文名>.sql`（序号续当前版本最大序号 +1；99_ 保留给回滚；详见 /sprint-design Step 3）
6. **研发执行计划**：如影响后续 Sprint 任务 → 经 `/sprint-plan {version} --execution-context "$EXECUTION_CONTEXT" --ledger-cascade --scale={档位} [--unattended]` 编排 → **就地改** `01_研发执行计划.md`（⛔ **不直调 `dev-execution-planner`**——会绕过 `/sprint-plan` Step 1.5 三脚本回检 / 1.6 SQL 路径回写 / 2 关联文档注入；⛔ 不新建分册；也不能挂 `/sprint-design`——它不产计划）
7. **★ L4 自测用例**：经 `/sprint-selftest {version} --execution-context "$EXECUTION_CONTEXT" --ledger-cascade --scale={档位} [--unattended]` → **就地改**既有用例册（⛔ 不得跳过，bug 修复恰是最该产回归用例的场景）
8. **刷 `00_索引.md` 生成时间**（主文档动了、索引时间戳就该动；⛔ 不登记「类型=补充」——本路径不产分册）

**不触发条件**：纯代码逻辑修复（配置错误、笔误、边界判断等）不回写设计文档。

#### Step 5.1：累进产物审计

复用 `{{AIDP_HOME}}/flows/sprint-dev/postdev-writeback-3.md`「累进路径的产物审计」的唯一配方，消费本次正式产物changed_files。未授权docs-audit记NOT_REQUESTED并直接Step 5.5；已授权先执行下列门，再按父预算派发。已有规划QR/移交证据同revision、inputs真实hash匹配才复用，只补delta，不新建第二清单。

```bash
EXECUTION_CONTEXT="${EXECUTION_CONTEXT:?必须从父任务入参重绑真实上下文路径}"
python3 {{AIDP_HOME}}/scripts/execution_policy.py require-action --root . \
  --execution-context "$EXECUTION_CONTEXT" --action docs-audit || exit $?
```

#### Step 5.5：★ P0/P1 缺陷反哺回归用例（约定 33 缺口 5.1 — 缺陷是最精准的用例来源）

> 缺陷本身就是最精准的回归用例来源（复现步骤现成）；`docs/bugfix/{version}/` 的缺陷记录修复后即终结、release suite 不增长 → 同类缺陷可重复发生。故每条 P0/P1 缺陷修复后**强制沉淀一条回归用例**，并跨版本继承（`/sprint-aiauto-test` Phase 2.0 自动并入历史 `[回归]` 用例，见约定 33 缺口 5.2），让历史教训自动沉淀、不逐版从零。

**触发条件**：document已授权，且本次修复的缺陷严重度为 **P0 / P1**（严重度取 bug 记录；零散低 severity bug 可跳过）。

未授权则只登记实际用例事实义务，跳到Step 6，不写流程欠账；已授权沿用上方document围栏。

**步骤**：
1. 对每条状态转「已修复」的 P0/P1 缺陷，经 `/sprint-selftest {version} --execution-context "$EXECUTION_CONTEXT" --ledger-cascade [--unattended]`（内部调 `dev-manual-testcase` 增量）**就地追加**一条回归用例到既有用例册——★ **本命令带 `--unattended` 时必透传**：方式 A 的执行体就是本流程，而 batch/full/autopilot 的无人值守主链恒经方式 A，漏传会让 `dev-manual-testcase` 的强制询问第零步把整条 7×24 链挂死（`/sprint-selftest` 认这个 flag，上游传了它才不会被静默丢弃），落 `docs/testing/{version}/研发自测/` 既有用例主文档（⛔ 不新建 `NN_` 分册——方式 B 不产分册，见 Step 5）。
2. 命令端传给 SKILL 的上下文须含：**缺陷 ID + 复现步骤 + 修复后预期**，并要求用例**标记 `[回归]` + 用例头登记「关联缺陷: {缺陷ID}」**，形成 用例 ID ↔ 缺陷 ID 双向关联。（`[回归]` 标记 + 缺陷 ID 字段的用例 schema 支持以 `dev-manual-testcase` 为单一信源，命令端只传上下文、不定义字段结构——约定 21；该标记字段已由 dev-manual-testcase 落地，`/sprint-aiauto-test` Phase 2.0 glob 据此跨版本继承。）
3. 该回归用例即被 `/sprint-aiauto-test` Phase 2.0 跨版本 `[回归]` glob 纳入后续每版 release suite（缺口 5.2）。

#### Step 6：更新 activeContext

仅在当前 formal 上下文明确绑定同一 Sprint 时，在 `memory/{version}/{user}/activeContext.md` 的「待处理 Bugfix」区域更新修复状态；身份/编号不符返回调用方。light 已在入口 return，不执行本步。

独立方式B仅related-test已授权时遵循 `/sprint-test` Step 2.6 / Step 7；部署只复用已请求证据，不新跑测试；已有验收会话则回传原实现者的修复与单测证据，不重复完整 CVL，也不以测试代替质量审查。

