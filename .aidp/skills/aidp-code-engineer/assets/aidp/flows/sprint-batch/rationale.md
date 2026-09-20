# sprint-batch · 理据 / 根因 / 反例（执行期不加载）

> 本文件承载 `/sprint-batch` 各段的**理据、根因、反例、历史事故**——对人类维护者有价值、但对执行期模型是噪音（稀释祈使信号），故从执行路径剥离、执行时**不 Read**。

## Step 6 外置（浏览器仿真测试链路）

- **为何外置**：Step 6（6.0–6.6，170 行）是 `/sprint-batch` 内最大的自包含段——从"跳过判定→SQL/部署文档安全网→用例存在性→deployment 配置→部署确认→调 aiauto-test→问题回写→兜底"完整一链，与 Step 1~5 的 Sprint 循环体正交。整份入上下文会与顶部「零询问连跑铁律」及 Step 1~5 循环规则互相稀释，走到 Step 6 时易漏子步骤（如 6.0.5 SQL 已应用校验、6.5 的 C-NNN/R-NNN 回写责任划分）。
- **命令主体保留**：Step 6 的衔接桥硬门（⛔）+ 6.0–6.6 骨架表 + 无人值守铁律 + `Read .aidp/flows/sprint-batch/step-6.md` 指针。
- **未外置的段**：顶部「零询问连跑铁律」+ 参数表 + Step 0.0~0.3 前置 + Step 1~5 执行策略（Step 1~5 共 90 行 < 120 阈值，且与「连跑铁律」强耦合，留主体）。

## 关键不变式（供维护者回溯，勿在执行期复述）

- Step 6 与 `/sprint-full` 边界：`/sprint-full` 单 Sprint 闭环**不含** Step 6；Step 6 只由 `/sprint-batch`（跑完 Step 1~5 全部 Sprint 后）触发一次。
- `source="sprint-batch"`（6.4 baseline 预写）是让 `/sprint-aiauto-test` Phase 0.2 步骤 2.5.1 自愈门识别"本 build 由 sprint-batch 直测、非 autopilot 体系"、不把测试链路弹回 `/sprint-autopilot` 的关键标记。

## 无响应 / 超时的处置为何是「换执行形态」而不是「终止」

本命令「零询问连跑铁律」禁止的是**理由**——「用"要省上下文"当借口停下来问人或终止」——
而不是这个理由出现在哪个位置。「5 分钟无响应 → 默认终止」这种形态正是该铁律要禁的东西，
只是披了一层"发生在循环体外"的壳：结果是 **0 个 Sprint 被执行**，
而本命令自己同时立着「上下文太长不构成终止理由」这条铁律，两者直接打架。

改为「按每 Sprint 一个独立子 Agent 的形态继续跑」后，上下文压力由子 Agent 隔离承担、
主循环只保留进度与收口——**既解决了压力，又不牺牲任何一个 Sprint**。


## Step 6.4 为何不能无条件写 last_deployed_at

该字段不只是"部署时间戳"：它同时是 `/sprint-aiauto-test` **去重门**的判据、以及**环境类冻结的
解冻信号**。无部署证据就刷新它，后果有两层——

1. Step 3 循环里 `/sprint-dev` 推过的代码是否真进了本次部署毫无判据，aiauto-test Phase 1 可能探到
   **上一次**部署的就绪 URL，即「推了就当完事」；
2. 环境类冻结会被这次无证据的刷新**误解冻**，并把上一次部署的结论当成本次新部署已测。

故必须按约定 31.5 接线：先分类，无正式代码变更则记 `cicd_skipped=true` 且不写该字段；
有变更须经 CICD 终态监听 + 就绪探针通过才写；分类缺失或失败一律 fail-closed 按有变更处理。

## Step 6.0.5/6.0.6 的版本号为何不能裸用 `current-version`

`baseline_edit.py current-version` 的定义是「有 `phase_beta_done_at` **且**无
`internal_released_at`」的版本。而本轮版本的 `phase_beta_done_at` **要到部署成功才写**
（`phase-3-5b.md` / `phase-3-7.md`）。

于是在 6.0.5 运行的那一刻，本轮版本**必然不在候选集里**：
- 仓库里若有一个尚未归档的上一版（Phase 2 hold 的常态）→ 返回**上一版**，校验对着错版本跑；
- 没有 → 返回**空串**，`SQL_DIR` 退化成 `docs/deployment//sql/增量`，被误判成"本版无 SQL"整段跳过。

两种结果都让「SQL 已应用校验」这道门失效，而它要防的正是"未应用的增量 SQL 直到部署后才炸"。
故改为首选 tick 变量 `TARGET_VERSION`，`current-version` 只作兜底，且**取空即 exit 1**（不静默跳过）。

## Step 6.4「预写 baseline」为何必须是可执行语句

该块此前从 `NOW=` 之后全是注释（"用 jq 写…"、"★ 必须标 `source=…`"、"不存在则初始化文件"），
**一条写入语句都没有**。而 `source="sprint-batch"` 正是本文件 Step 6.0 整个入口判据的唯一依据：
不落盘 ⇒ 判据恒取空 ⇒ aiauto-test Phase 0.2 的自愈门把本轮弹回 `/sprint-autopilot`，绕一整轮。

同仓 `postdev-writeback-3.md` 早已立下铁律：「必须是可执行语句，**只写在散文里 = 既没人看见、
也不落进 jq 巡检视图**」——这里是同一形态的复发。
