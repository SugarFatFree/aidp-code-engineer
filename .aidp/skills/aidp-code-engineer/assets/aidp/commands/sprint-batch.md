# /sprint-batch — 批量执行所有 Sprint

你正在执行 `/sprint-batch` 命令，连续执行研发执行计划中的多个 Sprint（计划可拆成多份，全集口径见 Step 1）。

**★**：批量循环调用 `/sprint-full`，适合首次全量跑完整个版本。

> 🔀 **与 `/sprint-full` 的边界**：本命令跑**多个** Sprint（循环调 `/sprint-full`）；只跑**单个** Sprint 用 `/sprint-full {NNN}`。

**★ 本命令是编排器**：
- 调用 `superpowers:executing-plans` 做顶层执行计划
- 循环调用 `/sprint-full {NNN} [--unattended]` 执行每个 Sprint（本命令带该 flag 时必透传）
- 调用 `superpowers:verification-before-completion` 做完成前验证
- **★ Step 6**：全部 Sprint 完成后**自动询问部署方式并衔接 `/sprint-aiauto-test`** 跑浏览器仿真测试，端到端闭环

> ⛔ **零询问连跑铁律（置顶强调 — 下游最易违反）**：本命令一旦启动，**Sprint 循环体（Step 3）内默认直接连跑研发执行计划的全部 Sprint、全程零询问**，把整张计划当**一个不可分割的任务**：
> - **不问"跑哪个 Sprint"**：无范围参数 = 跑**全部**研发执行计划文件里的未完成 Sprint（首跑 = 001→最后）；只跑一段才显式传 `001-003`。**严禁**启动时 `AskUserQuestion` 让用户选 Sprint。
> - **不问"是否继续下一个 Sprint"**：一个 `/sprint-full` 返回后**立即**进下一个，直到执行列表全部关闭。
> - **本命令的连跑节奏**：本命令用 `superpowers:executing-plans` 仅作循环脚手架，在**批量语境下不采用**其「When to Stop and Ask for Help」的逐任务停下确认节奏——Sprint 之间**绝不**冒出「继续吗 / 跑哪个」类询问（这是本命令自身的连跑行为声明，非改写该 skill 的内部逻辑）。
> - **Step 3 循环体内的唯一合法停顿**：① 硬失败（编译/前端校验失败、设计文档缺失，见 Step 4）② `/sprint-full` 内部必要决策门（UI 来源 C/D、约定 22 破坏性变更确认门、Critical 裁决）③ 显式 `--stop-on-blocker`（软失败也停）。除此之外，**Sprint 之间任何"要不要继续 / 跑哪个"的询问都是违规**。
> - ⛔ **严禁自发弹「工作量大 / 如何推进 / 全自主全做 vs 分阶段逐个确认」范围·进度门**（catch-all，**两种模式都禁**）：研发执行计划的全部 Sprint（含单 Sprint 内多个 REQ / 多端工作）是**一个不可分割、必须一次跑完的整体**。模型**不得**以"两个 REQ / 工作量较大 / 每个 Sprint 可控 / 稳妥起见"为由，自发弹「我全自主完成 N 个 Sprint vs 先做某 Sprint 给你 review 再继续」这类询问——它既违反上面"不问是否继续下一个 Sprint"，也**不属于** ② 的「必要决策门」（② 仅指 UI 来源/上游级联/Critical 这类**内容决策**，**不含**"要不要一次做完 / 分几段做"这种**范围·节奏决策**，后者永远默认"一次全做完"、无需问）。`--unattended` 下更是绝对禁止。
>   - **★ `--unattended` 例外（autopilot `/loop` 无人值守）= catch-all 绝不停等**：本命令带 `--unattended` 时，上面 ②③ 的内部决策门**以及任何未枚举的交互门一律不再停下等人**——透传 `--unattended` 给 `/sprint-full → /sprint-dev`，由其消费 PRD `autopilot_decisions` 预声明（UI C/D 走 `visual_baseline`、约定22 级联默认自动，见 `/sprint-dev` Step 0 / Step X.0.0）、或走文档化保守默认、或转失败熔断（Critical 无法自动裁决时），**绝不 `AskUserQuestion`**。这堵住 autopilot 7×24 在 Sprint 内部弹窗挂死的缺口；PRD 未预声明则走各门文档化的保守默认。
> - **★ 本铁律只管 Step 3 Sprint 循环体**：**循环体外**的命令自有交互门不受本铁律约束——现只剩 **Step 6**（循环全部跑完后的部署确认 + AI 自动化测试三选一，`--skip-aiauto-test` / `--auto-aiauto-test` 可跳）。⛔ **Step 0.0 不在此列**：上下文长度**只出 INFO 提示、不设询问门**——「上下文长 → 问 y/n」属于「用『要省上下文』当借口停下来问人」（本命令明禁）（用户回 n 就一个 Sprint 都不跑地终止），**披一层「发生在循环体外」的壳不改变性质**。故纯 INFO 提示后直接继续（`--skip-context-check` 连提示也不打）。被 `/sprint-autopilot` 调起时它已传 `--skip-context-check --skip-aiauto-test`。
> - **完成判定**：唯有"执行列表里每个 Sprint 都已 close"才算 Step 3 跑完；只要还有未跑的 Sprint 就是没跑完、必须继续（Step 5 末尾自检：已关闭 Sprint 数 == 执行列表长度）。
> - **★ "一次跑完" = 不中途向人征询，≠ 挤在同一上下文**（本铁律的作用域澄清，**单一信源在此**）：把 Sprint 分 tick / 分后台子 Agent 自动推进、中途 `/compact`、把长产物外置成文件后再续跑，**都不违反连跑**——只要全程不停下问人、执行列表最终全部 close 即可。反向同样成立：**"上下文太长 / 要省 token" 不构成停下来问人或终止的理由**——省上下文的正解是换执行形态（compact / 子 Agent / 分 tick），不是把控制权交回给人。

参数：$ARGUMENTS
- 为空：由 `plan_sprints.py` 取全部计划文件的未完成 Sprint，依次执行
- Sprint 范围：`/sprint-batch 001-003` 执行 001 到 003
- 起始范围：`/sprint-batch 002-` 从 002 开始跑到最后
- `skip-bugfix`：整体跳过 Sprint 内 bugfix 循环（仅记录 bug，不修复）
- `--skip-context-check`：跳过 Step 0.0 上下文压缩建议（明确不需要 /compact 时使用）
- `--stop-on-blocker`：遇阻即停模式（bugfix 循环超限就暂停；默认非阻塞模式继续）
- `--skip-aiauto-test`：跳过 Step 6 浏览器仿真测试整合（纯开发模式）
- `--auto-aiauto-test`：Step 6 跳过"是否要跑 AI 自动化测试"询问门，直接走部署确认 + 执行（仍会问 deployment 字段缺失项）
- `--unattended`：★ autopilot `/loop` 无人值守标记（等价环境变量 `LOOP_UNATTENDED=1`）。① **隐含跳过 Step 0.0**（上下文压缩询问门——其唯一出口是等人应答、超时即终止整条命令）② **透传给 Step 3 每个 `/sprint-full → /sprint-dev`**，令其 Sprint 内部决策门（UI C/D、约定22 级联）改为消费 PRD `autopilot_decisions` 预声明、不弹窗（见「零询问连跑铁律」`--unattended` 例外）

## 前置准备（Step 0.0~0.3）

### Step 0.0：上下文压缩建议

> ⛔ **无人值守守卫（本 Step 首行判定，先于一切检测）**：`--unattended` 或环境变量 `LOOP_UNATTENDED=1` 命中 → **整段 Step 0.0 跳过**（等同 `--skip-context-check`），直接进 Step 0.1。**Why**：本门唯一出口是等人应答、超时即**终止整条命令**，无人值守下必然挂满超时后一个 Sprint 都不跑；且"上下文长"在无人值守下的正解是换执行形态（compact / 子 Agent / 分 tick），不是停下问人（见「零询问连跑铁律」的作用域澄清）。

`/sprint-batch` 常紧接 `/version` 之后执行，两个命令都产生很长的上下文（PRD/设计/计划/自测用例等多文档生成）。**长上下文会导致 sprint-batch 内部子命令调用更慢、更易出错**。命令端在最开始执行**条件提示**：

**1. 检测当前上下文状态**（Claude 凭对会话历史的感知做近似判定，无需精确计数）：

- (a) **回看会话**：本会话历史中**是否出现过** `/compact` 命令、"compact" 关键词、或系统的"会话自动压缩"标记？→ **是 → 跳过提示**
- (b) **会话短**：本会话从开头到现在轮次很少（凭感知 ≤ 5 轮往返） / 上下文窗口占用还很轻 → **是 → 跳过提示**
- (c) **未跑大命令**：本会话**未执行**过 `/version` 或密集的 `/sprint-design` / `/sprint-requirements` 等大产物命令 → **是 → 跳过提示**

> 这三项是**启发式判定**，Claude 无法精确数 tokens 或轮次；只要任一条件你能**直观感受到**满足，即可跳过提示。判定不确定（边界场景）时，**默认触发提示**（保守倾向 — 多问一次胜过让用户掉进长上下文坑）。

**2. 触发提示的条件**（以上三项任一为否，即触发）：

终端输出：

```
💡 检测到当前上下文较长（最近跑过 /version 等大命令）。
   /sprint-batch 将批量调用多个 /sprint-full，每个内部又会调多个 SKILL，
   长上下文会显著拖慢执行 / 增加 token 消耗 / 提高出错概率。

   建议先手动执行 /compact 压缩上下文，再继续 /sprint-batch。

   → 本命令**不因此停下来问你**，直接按「每 Sprint 一个独立子 Agent」形态继续，
     上下文压力由子 Agent 隔离承担。要先压缩请自行中断后 /compact 再重跑。
```

- **★ 本提示是【纯 INFO】，不是询问门**：打印后**直接继续**，与下方超时分支同一处置。
  ⛔ 曾在此弹「y 继续 / n 中止」二选一，用户回 n 就**一个 Sprint 都不跑**地终止——
  那正是本命令「零询问连跑铁律」点名禁止的「反过来用『要省上下文』当借口停下来问人」，
  与它发生在循环体内还是体外无关（rationale 里"披了一层『发生在循环体外』的壳"说的就是它）。
  用户要中止随时可以外部中断，不需要命令替他造一个中止出口。
- **执行形态**（与上同一处置，不区分"有无响应"）：
  按「每 Sprint 一个独立子 Agent」形态跑（`/sprint-full <NNN> --from-batch` 逐个派），
  ⛔ **此处不传 `--unattended`**：本门仅交互式可达（见下一条），传了会让交互式用户静默进入无人值守语义——
  UI 情形 C/D、约定 22 破坏性变更确认门、Critical 裁决全部改走预声明/保守默认，该由用户拍板的一个都不弹。
  上下文压力由子 Agent 隔离承担，主循环只保留进度与收口。
  ⛔ **"上下文太长 / 要省 token" 不构成停下来问人或终止的理由**（本铁律禁的是这个**理由**，
  与它出现在循环体内还是体外无关）。仅交互式会走到本门；无人值守由本 Step 首行守卫整段跳过。
  成因见 `.aidp/flows/sprint-batch/rationale.md`「无响应处置为何不是终止」。

> 该提示**只在命令开头出现一次**；`--skip-context-check`、`--unattended`、`LOOP_UNATTENDED=1` 任一命中即一律跳过本 Step 0.0。

### Step 0.1：前置流程

按 `docs/init/06_版本与用户目录约定.md`：
1. **{version}** ← 项目记忆文件（路径经 `python3 .aidp/scripts/agent_env.py memory-file` 取：`AGENTS.md`，只用 Claude Code 时为 `CLAUDE.md`）「当前状态.当前版本」
2. **{user}** ← `git config user.name`

### Step 0.2：前置检查

1. 确认版本规划文档已生成：
   - `ls docs/requirements/{version}/研发需求/{01_研发需求,00_索引,00_研发需求}.md 2>/dev/null` 任一命中即可（**不硬编码裸名**——multi 模式按系统拆分时 `01_研发需求.md` 本就不存在，硬判会把合规项目误判缺失而错误停止）
   - **详细设计**：`ls docs/design/detail/{version}/*.md` 有内容主文档即可（★ **用 glob 探测、兼容约定 14 三态**——拆分态 `00_索引.md`+`01_详细设计.md`… / 单份态 `00_详细设计.md` / 历史存量裸名 `详细设计.md`；**不硬编码裸名**，否则拆分态项目会被误判缺失而错误停止）
   <!-- dup-check: ignore 前置检查清单需各命令自包含，读者不应为一行 glob 跳转 -->
   - 研发执行计划：`ls docs/plans/{version}/{01_研发执行计划,00_索引,00_研发执行计划}.md docs/plans/{version}/0[0-9]_M*研发执行计划.md docs/plans/{version}/NN_研发执行计划-*.md 2>/dev/null` 任一命中即可（**不硬编码裸名**，理由同上一行研发需求；合法布局见 `/sprint-plan` Step 1「输出」）
   - 任一缺失（设计目录无任何内容主文档）→ **停止执行**，提示先执行 `/version {version} "{里程碑}"`
2. 读取 `memory/{version}/{user}/activeContext.md`：
   - 如有进行中的 Sprint → **停止执行**，提示先 `/sprint-close`（约定 9 是**硬停**不是提示，与 `/sprint-full` 前置检查 2、`/sprint-start` 同口径；写成提示会先落 Step 0.3 / Step 1 的副作用，才被子命令拦下）
3. 读取 `memory/{version}/{user}/progress.md` 的 Sprint 历史

### Step 0.3：测试方案 AI 自动化预检（★ 跑 Sprint 之前就补全 AI 自动化测试信息）

> Step 6 末段会衔接 `/sprint-aiauto-test` 跑浏览器仿真测试。为**尽量减少中途用户介入**，在**跑 Sprint 之前（现在）**就把 chrome-devtools-mcp 所需信息补齐，而不是等 Step 6 才发现缺信息。

对 `{version}` 运行「测试方案 AI 自动化预检」（**逻辑单一信源 = `/sprint-aiauto-test` Phase 0.0.6**，本命令不复写）：

1. 读 `docs/testing/{version}/研发自测/01_测试环境与账号.md`
2. **前端 web 项目** 且 **缺 chrome-devtools-mcp 段** → 调 `/sprint-selftest` Step 3 模板自动补全该段（含安装 / 本地+远程启动 / 端口转发 / 验证命令）
3. 核验 chrome-devtools-mcp 正式使用所需信息：① 测试环境访问地址 ② 测试账号密码 ③ 是否跨设备 ④ 跨设备时远程 Chrome 的 IP + 端口
4. 缺任一项 → **现在（跑 Sprint 前）一次性 `AskUserQuestion` 收集** + 告知安装命令 / 远程端口转发命令 / 先配 mcp 文件后启动铁律 + Write 写回测试方案 + commit

- 命令带 `--skip-aiauto-test` / **非前端 web 项目** / `deployment.mode=none` → 跳过本预检
- **★ `--unattended` / `/loop` 无人值守（不弹窗铁律，勿只靠顶部 catch-all）**：point 4 的 `AskUserQuestion` 在无人值守下**不弹窗**——按已读到的字段跑、缺项标 `{待用户填写}` 占位交测试链路（与 Step 6.2 / `/sprint-aiauto-test` Phase 0.6 无人值守守卫同口径），绝不因本预检 `AskUserQuestion` 挂起。
- **与 Step 6.2 的边界**：本预检管"测试方案 chrome-devtools-mcp 段 + 连接/账号信息"；Step 6.2 管"PRD `deployment` 部署配置"，两者互补不重复

## 执行策略

### Step 1：解析执行范围

**★ Sprint 全集的唯一口径 = `plan_sprints.py`，⛔ 不得自己 glob / 硬编码 `01_研发执行计划.md`**：

```bash
# ⛔ 绝不写成 `eval "$(...)"` 一行：脚本 fail-closed 时 **exit 1 且 stdout 零字节**，
#    `eval` 会把退出码吞掉 → `REMAIN_COUNT` 未定义 → 执行列表为空 → **0 个 Sprint 跑完且零报错**，
#    正是下方 Why 段要堵的那种假成功。形态与 `flows/sprint-autopilot/phase-3-5.md` 的调用保持一致。
_PS=$(python3 .aidp/scripts/plan_sprints.py --version "$VERSION" --shell) || exit 1
eval "$_PS"; : "${REMAIN_COUNT:?plan_sprints fail-closed}"   # ALL_SPRINTS / CLOSED_SPRINTS / REMAIN_SPRINTS / REMAIN_COUNT
```

**Why**：计划是**多文件形态**（多用户拆 / 超阈拆 / 跨里程碑拆 `01_M1…` `02_M2…`）。只读到 M1 那一份时「全部 Sprint」就等于 M1 的 Sprint → M1 跑完差集为空 → 打印「✅ 全部 Sprint 已关闭」→ 照常部署、finalize、发报告与里程碑通知，而 **M2 的 Sprint 从未执行、且没有任何告警**：不报错、不重试、结论是「成功」。脚本对「目录下一份计划都没有」fail-closed（exit 1，⛔ 不返回空集——空集会被读成「全部已关闭」）。

执行列表 = `REMAIN_SPRINTS` 与范围参数取交集。**确定后直接开跑，绝不就"要执行哪些 Sprint"向用户确认**（无范围参数即默认全部未完成 Sprint —— `progress.md` 仅用于断点续跑跳过**已 close** 的，不是让你只跑"当前一个"）。

```
例：
  研发执行计划（可能拆成多份）定义 Sprint-001 ~ Sprint-005
  progress.md 显示 Sprint-001 已完成
  参数为空 → 执行列表 = [002, 003, 004, 005]
  参数 003-004 → 执行列表 = [003, 004]
  参数 003- → 执行列表 = [003, 004, 005]
```

### Step 2：调用 superpowers:executing-plans 作为顶层编排

使用 `Skill` 工具调用 `superpowers:executing-plans`（**仅作循环脚手架**）：

```
计划：批量执行 {version} 下的 {M} 个 Sprint
默认行为：**全流程批量跑完，中途仅"硬失败"才停**；软失败（bugfix 循环超限等）记账后继续，全部跑完再由人工介入联调验证
```

> ⛔ **executing-plans 的 stop-and-ask 在此被覆盖**：该 SKILL 自带「When to Stop and Ask for Help」会在任务间停下征询；但在 `/sprint-batch` 语境下，**Sprint 之间一律不停、不问**（连跑铁律见顶部）。executing-plans 仅提供"逐项执行 + 完成前汇报"骨架，其"遇不确定就停下问"**只对 `/sprint-full` 内部的必要决策门生效**，**不得**升格为"每个 Sprint 之间问一次要不要继续"。

### Step 2.5：★ 生成 Sprint 上下文预热包（首次派发前一次，循环内增量更新）

N 个 Sprint 子 Agent 各自重读同一批**本版内完全不变**的文档（研发执行计划含其全部铁律、
详细设计、研发需求、`AGENTS.md`）——读 N 遍，付 N 份 token 与时间。

**动作**：本步生成 `memory/{version}/{user}/_sprint-context-digest.md`（`_` 起头 = 过程文件，
不占 `NN_` 序号、不进索引、不是交付物），内容只收**跨 Sprint 复用且本版不变**的部分：

- 本版关键口径与铁律（从研发执行计划提炼，⛔ 不复制全文）
- 域间耦合关系与文件冲突面（有则写，无则写"未声明"）
- 本项目静态验证的**正确跑法**（命令原样，避免每个子 Agent 各试一遍）
- 已知环境坑（取自 `.aidp/reference/子Agent必读.md`，只摘与本版相关的）
- **上一 Sprint 的产出与登记的偏差**（见下方增量更新）

**三条边界（缺一则它会从加速器变成错误源）**：
- ⛔ **必须标注「本文件非权威，权威仍是原文」**，并在每段注明原文位置——
  子 Agent **先读摘要、只在需要细节时回查原文**，⛔ 不得据摘要下与原文冲突的结论。
- ⛔ **每个 Sprint 关闭后由主流程增量更新**：把刚关闭那个 Sprint 的**新增公共产物**追加进去
  （典型："Sprint-042 新建了 `UpstreamLogMasker`，后续 Sprint 复用它、不要重复造"）。
  不更新的话，后续 Sprint 只能靠人在派单 prompt 里手写传递这类信息——实测正是这么传的。
- ⛔ **不进硬门、不作为完成判据**：生成失败或内容为空 → 打印一行照常继续，子 Agent 回退读原文。

**派发时**：把该文件路径写进子 Agent 简报的首行（"先读它，再按需回查原文"）。

### Step 3：循环调用 /sprint-full（★ 必须跑完整个执行列表）

> ⛔ **循环铁律**：本步骤是 `/sprint-batch` 的核心循环体，**必须严格 for 循环跑完 Step 1 解析出的整个执行列表**。**单个 `/sprint-full` 返回 ≠ 命令结束**，Claude 不可以把单个 `/sprint-full` 的 Phase 5 输出当作整个 `/sprint-batch` 的终点。

> ★ **执行形态（本步恒适用，与任何 flag 无关）**：按「**每 Sprint 一个独立子 Agent**」跑（`/sprint-full <NNN> --from-batch` 逐个派），上下文压力由子 Agent 隔离承担、主循环只保留进度与收口。
> ⛔ **与 `--skip-context-check` 无关**：那个 flag 只关掉 Step 0.0 的一次性 INFO 提示，**不改变本步的执行形态**。⚠️ 上游主链路（`/sprint-autopilot` Phase 3.2 step 2）**恒传**该 flag，若把执行形态只写在 Step 0.0 里，本步就会在最常见的路径上失去它承诺的唯一上下文兜底手段。

**循环伪代码**（Claude 必须严格按此执行）：

```
for NNN in 执行列表:
    result = /sprint-full {NNN} --from-batch [skip-bugfix] [--unattended] [--stop-on-blocker]   # ★ 本命令带 --stop-on-blocker 时必透传（bugfix 超限的停顿判定在 /sprint-full Phase 4 内部，不透传则本 flag 与不带完全等价）；带 --unattended 时必透传，令 Sprint 内部决策门消费 PRD 预声明、不弹窗
    update progress(NNN, result)
    if result.kind == "硬失败"（编译/前端校验/设计文档缺失）:
        break  # 仅此一种情况允许中断
        # ⛔ 中断后**仍须跑 Step 5.5**（本批次台账收口）——break 只跳出 Sprint 循环、不豁免收口：
        #   漏跑则本批次已产生的开发期变更台账当轮无人收口，与「本批次确实没有变更」在机器上同形。
    update context_digest(NNN)   # Step 2.5 的增量更新：把本 Sprint 新增的公共产物追加进摘要
    # ✅ 完成 / ⚠️ 软失败（bugfix 超限 / 用例失败 / Critical 待裁决）→ 都视为该 Sprint 已结束
    # 立即继续下一个 NNN，禁止：
    #   ❌ 询问用户"是否继续下一个 Sprint"
    #   ❌ 输出"📌 下一步：/sprint-full {NNN+1}"等暗示用户手动调用的话
    #   ❌ 把 progress.md / activeContext.md 写成"任务全部完成"状态（必须等 Step 5 之后才写）
    continue
# 循环正常退出（执行列表跑完）→ 进入 Step 4 阻塞汇总 → Step 5 完成前验证 → 最终汇总报告
```

★ **`--from-batch` 旗标的作用**：通知 `/sprint-full` 当前是被 `/sprint-batch` 调起的子任务，必须**抑制 Phase 5 末尾的"📌 下一步：`/sprint-full {NNN+1}`"段落**，仅输出一行紧凑摘要 `▶ Sprint-{NNN} ✅ 完成（{N} 接口 / {N} 页面 / bugfix {M} 轮）` 即返回。这让 Claude 不会把单 Sprint 末尾输出误读为整个命令的终点。

★ **该询问的决策点由主循环代问（仅交互式；且仅限"内容决策"，不含范围·节奏）**：Sprint 在独立子 Agent 里跑，⛔ **子 Agent 无法 `AskUserQuestion`**，故 `/sprint-full` 带 `--from-batch` 透传到各子命令：其内部**内容决策门**（UI 视觉来源情形 C/D / 约定 22 破坏性变更确认门 / Critical 裁决 / 不可恢复错误）**不自行拍板**，以「⏸ 待裁决：<门名> / <选项> / <推荐>」返回。主循环收到后：**交互式** → 用 `AskUserQuestion` 问用户，把决策写进续派简报首段、**续派同一 Sprint**（⛔ 不算硬失败、不跳到下一个 Sprint）；**`--unattended`** → 子命令本就按 PRD 预声明 / 保守默认处理，不会返回待裁决。**"要不要一次全做完 / 分几段做 / 工作量大如何推进"属范围·节奏决策，永远默认"一次全做完"、任何模式都不问**（见上方零询问连跑铁律的范围·进度门 catch-all）。

`/sprint-full` 内部自己完成：
- Phase 1：/sprint-start {NNN} [--unattended]（无人值守时透传）
- Phase 2：/sprint-dev
- Phase 3：/sprint-test
- Phase 4：bugfix 循环（5 次上限）或跳过
- Phase 5：/sprint-close {NNN}

等待 `/sprint-full` 返回后**立即**进入下一个 Sprint（不停顿、不向用户汇报"是否继续"）。

### Step 4：阻塞检测

每个 `/sprint-full` 执行后检查返回状态。**默认"软失败"非阻塞**——即使 Sprint 验收未完美通过，记入"待人工处理清单"后**继续下一个 Sprint**；只有**硬失败**（环境/依赖性的不可继续错误）才停：

| 状态 | 类型 | 默认处理 |
|------|------|-------------------|
| ✅ 完成 | — | 输出简要摘要，进入下一个 Sprint |
| ⚠️ bugfix 循环超限 | **软失败** | 记入"待人工处理 bug 清单"，**继续下一个 Sprint**（不暂停）|
| ⚠️ 测试用例存在失败 | **软失败** | 记入"待人工验证用例清单"，**继续下一个 Sprint** |
| ⚠️ 验收 Critical 问题 | **软失败** | 记入"待人工裁决问题清单"，**继续下一个 Sprint** |
| ❌ 编译/前端校验失败 | **硬失败** | **停止批量执行**——后续 Sprint 依赖本 Sprint 可编译/校验通过，无法继续（后端编译 / 前端校验（lint + 类型检查，不打包）在本 Sprint 的 `/sprint-test` 验收点触发，仅改动侧 + 资源受限；失败即此硬失败）|
| ❌ **前置检查失败**（如约定 9「上个 Sprint 未 `/sprint-close` 归档」——`/sprint-full` 对此是**硬停**）| **硬失败** | **停止批量执行**——⛔ 本行不可省：该返回若不被归类，Step 5 的「回 Step 3 继续跑」会把它落进**无界重试**（单 tick 内死循环 + 上下文膨胀，而 autopilot 的 stuck 熔断是 tick 级、管不到 tick 内部）|
| ❌ 设计文档缺失 | **硬失败** | **停止批量执行**——后续命令链断裂，必须先补设计 |

**人工介入时机**：默认**全部 Sprint 跑完后才暂停**（Step 5 之后），由人工依据"待人工清单"做联调验证 + 集中修复。

**显式遇阻即停模式**：参数追加 `--stop-on-blocker` → bugfix 循环超限即暂停，等人工处理后再继续。

### Step 5：完成前验证

所有 Sprint 完成后，调用 `superpowers:verification-before-completion`：

```
检查：
  - 执行列表中所有 Sprint 都已关闭
  - memory/{version}/{user}/sprints/ 有所有归档文件
  - progress.md 中所有 Sprint 状态为 ✅ 完成
```

> ⛔ **完成自检（连跑铁律的可验证收口）**：进入本步前**重跑一次** `plan_sprints.py --shell`，核对 **`REMAIN_COUNT == 0`**（即 `ALL_SPRINTS − CLOSED_SPRINTS` 为空）。⛔ **不得拿「已 close 数 == Step 1 执行列表长度」当判据**——执行列表本身就是那次读计划的产物，读漏了一份计划时它与已 close 数天然相等，自检与被检对象同源、恒自洽。若 `REMAIN_COUNT > 0`（还有 Sprint 没跑）→ **未完成**，**回 Step 3 继续跑剩余 Sprint**，**绝不**在此提前收尾 / 汇报"全部完成" / 进 Step 6。唯一例外 = Step 4 硬失败中断（已记账并在汇总报告标明中断点）。
> ⛔ **回 Step 3 必须有进度判据与次数上限，否则是单 tick 内的死循环**：记录回跳前的「已 close 数」，回跳一轮后若该数**没有增加**即判**无进展**；连续 2 轮无进展 → 停止回跳，按 Step 4 硬失败处置（记账 + 汇总报告标明中断点 + 交上游熔断）。**Why**：`/sprint-full` 的前置检查 2（约定 9 未归档）是**硬停**，而 Step 4 的失败分类表**没有「前置检查失败」这一行** —— 该返回不被归类，就落进这里的无界重试；而 autopilot 的通用 stuck 熔断是 **tick 级**判据，管不到单 tick **内部**的循环，于是表现为上下文持续膨胀直到撞上限，且全程零告警。

### Step 5.5：★ 收口本批次开发期变更台账（约定 22 攒批级联 · 收口点 4；**必须先于 Step 6**）

> **单一信源 = `.aidp/reference/开发期族增量.md`**（收口执行要点 / 合并同类项 / 失效消解 /
> 按合并后总量重判档位 / 清理与删文件规则全在那份）。**进入本步第一动作 = Read 该文件。**
>
> ⛔ **为什么必须有这一步、且必须在 Step 6 之前**：本命令一次跑完 N 个 Sprint，每个 Sprint 的
> 本命令经 `/sprint-full` → `/sprint-dev --cascade-now` 逐 Sprint **即时级联**，进入本步时台账应已为空；
> 本步是**兜底收口**——覆盖 `--cascade-now` 失败的条目与非 Sprint 路径产生的条目。
> ⛔ 不得据此认为 `/sprint-full` 的 `--cascade-now` 可省：它保的是**单跑 `/sprint-full`** 那条路径。
> 于是紧接着的 **Step 6 当天就跑浏览器实测**——测的是**不含本批次任何新增用例**的用例集，
> 而 L4 自测用例正是「反向断言」的载体。这不是边角场景，是 `/sprint-batch` 的**主链路常态**
> 收口点 1/2/3 都覆盖不到这个窗口，故设第 4 个。

- **触发**：本版**四族任一**增量册（含存量单册台账）存在且有「待级联」条目；四族全无 → 打印 INFO 跳过。
  路径与条目解析走 `commit_gate.cascade_ledger_paths()` / `pending_cascade()`，⛔ 不自拼路径。
- **范围**：按族分流，**单一信源 = `.aidp/reference/开发期族增量.md` 收口点表「批量 Sprint 收尾」行**（本处不复述）。
- **动作**：派**独立子 Agent** 读台账 → 结合代码现状核实（被后续 Sprint 推翻的条目直接作废、不产文档）
  → 合并同类项 → 按合并后总量重判档位 → 跑四级级联 → 产物随本批次提交。
- **★ 清理**：成功级联的条目逐条删除；台账再无待级联条目 → 删除整个文件。失败条目留在台账 + WARN
  （**本收口点在版本开发中途，失败条目留到下个收口点是正常节奏**——与版本级收口点 2/3 的「必定删档」不同）。
- **★ 终态机器门（确定性，不通过不得进入 Step 6）**：
  `python3 .aidp/scripts/check_cascade_landing.py --base-ref "$BATCH_BASE_REF" --version {version}`（★ 落点门，模式 A；`BATCH_BASE_REF` = 进入本步时 `git rev-parse HEAD` 的值，本步级联产物**提交之后**跑，只看本批次提交范围；⛔ 不用 `--worktree`——它扫全部未提交文件、不止本批次）
  + `python3 .aidp/scripts/check_cascade_landing.py --ledger-closed --version {version}`（终态门，档②）
  ⛔ 两个都要跑：终态门只看「台账清没清」、**不看改动落在哪**；落点门只看「改动落在哪」、不看台账。二者正交，缺一即留缺口
  —— **默认档**（非 `--must-delete`）：断言**文件存在 ⟺ 确有未决条目**；空台账 / 条条已级联却仍留着
  = 该删没删，exit 1。格式漂移致解析不出条目同样判失败，不 fail-open。判据表见台账详规「终态机器门」。
- **跳过条件**：带 `--skip-aiauto-test`（不跑 Step 6，用例时效性无要求）时**仍执行本步**——
  文档欠账与是否实测无关，只是不再有"赶在实测前"的紧迫性。
- **打印**：`📋 本批次攒批级联：处理 N 条（成功 M / 失效 K / 失败 J）→ 已就地写回各族内容主文档（01_ 等）；台账已删除|保留 J 条`。

### Step 6：浏览器仿真测试链路（★ 编排 `/sprint-aiauto-test`）

> ⛔ **本步骤是 sprint-batch 与 sprint-aiauto-test 的衔接桥**：Step 1~5 跑"代码开发 + 单元/集成验证"，Step 6 跑"部署到运行环境后的真人视角浏览器仿真测试"，端到端闭环。按约定 21，**命令端只做编排 + 项目级补充**，不复述 sprint-aiauto-test / dev-manual-testcase 等 SKILL 内部规则。
>
> **进入本段第一动作 = Read `.aidp/flows/sprint-batch/step-6.md`**，逐项执行 6.0–6.6，绝不凭下方骨架表或记忆略过子步骤（骨架仅供定位，flow 文件为权威）。

| 子步骤 | 职责（一句话）|
|--------|--------------|
| 6.0.5 SQL 已应用校验 ★**先跑** | 部署前安全网：本版 `sql/增量/` 全 `NN_*.sql` 是否都在 `.applied-sql.json`，未应用 → WARN 部署阻断风险（约定 6）|
| 6.0.6 部署流程文档校验 ★**先跑** | 本版有 SQL 却缺 `部署流程/部署流程.md` 或仅剩占位符 → WARN（与 `/sprint-dev` Step X.8 呼应）|
| 6.0 跳过条件判定 | ⛔ **本行在 6.0.5/6.0.6 【之后】执行**（编号小 ≠ 先跑）：它们是部署前安全网、与"跑不跑浏览器测试"无关，放在判定之后会被 `--skip-aiauto-test` 连坐，而 7×24 主路径恒带该 flag。判据 = `--skip-aiauto-test` / Step 3 硬失败 / `deployment.mode==none` → 跳过并在报告标原因 |
| 6.1 用例存在性校验 | 测试人员用例（`正式用例/`）或研发自测任一存在即可，均无 → 跳过 AI 测试 |
| 6.2 deployment 配置 | 读 PRD `autopilot_decisions.deployment`；完整→三选一沿用/改/跳，缺→`AskUserQuestion` 分批收集写回 PRD |
| 6.3 部署完成确认 | 交互式按 `mode=local/cloud` 分流询问部署状态（无人值守整段不弹窗）|
| 6.4 baseline 预写 + 调用 | 写 `versions.{version}`（`source="sprint-batch"`）→ 调 `/sprint-aiauto-test --once` |
| 6.5 问题回写 | 失败用例回写 `C-NNN` 到「问题汇总清单」；运行时错误 `R-NNN` 由 aiauto-test 自写；`failed>0‖runtime_errors>0` 均非绿灯 |
| 6.6 兜底 | AI 测试整体失败（chrome 未装 / 探测超时 / 登录失败）由 aiauto-test 自发里程碑通知后退出；sprint-batch 主流程不回滚、汇总报告标出 |

> ★ **无人值守铁律（贯穿 6.0.5/6.0.6/6.2/6.3）**：`--unattended` / `/loop` 下所有 `AskUserQuestion` 一律不弹窗——按已读字段跑、缺项标 `{待用户填写}` 占位交测试链路，绝不因本段任何询问挂起（同 aiauto-test Phase 0.6 无人值守守卫口径）。

## 输出

### 批量执行过程中（每个 Sprint 完成时）

★ **紧凑摘要**（避免 Claude 把单 Sprint 摘要当作整个 `/sprint-batch` 任务终点）：

```
▶ Sprint-{NNN} ✅ 完成（{N} 接口 / {N} 页面 / bugfix {M} 轮 / 待修 {K}）
🔄 自动进入 Sprint-{NNN+1}...
```

或软失败：

```
▶ Sprint-{NNN} ⚠️ 软失败：bugfix 循环超限（{K} 个 bug 留待人工）— 已记账并继续
🔄 自动进入 Sprint-{NNN+1}...
```

每个 Sprint 之间**禁止**输出："下一步：执行 `/sprint-full {NNN+1}`" 等暗示用户手动继续的话；批量循环由 `/sprint-batch` 命令自身负责，必须自动连贯地跑完整个执行列表。

### 最终汇总报告

```
🎉 /sprint-batch 完成（{version}）

📊 执行摘要：
- 计划 Sprint：{M} 个
- 已完成：{N} 个
- 总耗时：{hh:mm}

各 Sprint 结果：
  Sprint-001：✅ 验收通过（bug {N} 个均已修复）
  Sprint-002：✅ 验收通过（bug {N} 个均已修复）
  Sprint-003：⚠️ bugfix 循环超限，{N} 个 bug 待人工处理（**非阻塞，已继续后续 Sprint**）
  Sprint-004：⚠️ 测试 N 用例失败（**非阻塞，已记入待人工验证清单**）
  Sprint-005：✅ 验收通过

📋 产出文件：
- docs/testing/{version}/sprint-001/ ~ sprint-{NNN}/
- docs/bugfix/{version}/bugfix-*.md
- memory/{version}/{user}/sprints/

🔄 已更新：
- memory/{version}/{user}/progress.md
- memory/systemPatterns.md / databaseBaseline.md
- AGENTS.md

🌐 浏览器仿真测试（★ Step 6）：

  情形 1 — 完成（全部用例通过 + 0 运行时错误 = 唯一绿灯）：
  - ✅ 完成（24/24 通过 · 运行时错误 0 · admin + normal-user）
    用例来源：测试人员（docs/testing/{version}/正式用例/）+ 研发自测查漏补充（docs/testing/{version}/研发自测/）
    AI测试报告（HTML）：docs/reports/{version}/AI测试报告/index.html
    部署模式：cloud / URL: https://uat.example.com

  情形 1b — 用例全通过但有运行时错误（★ 非绿灯，不可直接发布）：
  - ⚠️ 用例 24/24 通过，但捕获 3 个运行时错误（已记 bug R-001~R-003）
    运行时错误已回写「问题汇总清单」（R-NNN），下一步跑 /sprint-bugfix 自动拾取（C-NNN/R-NNN 回写责任划分见 6.5）

  情形 2 — 部分失败（失败用例 + 可能含运行时错误，已自动回写问题汇总清单）：
  - ⚠️ 部分失败（22/24，2 失败 + 3 运行时错误，共 5 个待修复）
    用例来源：测试人员（docs/testing/{version}/正式用例/）+ 研发自测查漏补充
    AI测试报告（HTML）：docs/reports/{version}/AI测试报告/index.html
    失败用例回写 C-001/C-002 + 运行时错误回写 R-001~R-003，下一步跑 /sprint-bugfix 自动拾取（C-NNN/R-NNN 回写责任划分见 6.5）

  情形 3 — 已跳过：
  - ⏭️ 已跳过（原因：--skip-aiauto-test / Step 3 硬失败 / deployment.mode=none / 正式用例/ 与 研发自测/ 均无用例 / 用户选择延后）

  情形 4 — 兜底失败：
  - ❌ AI 自动化测试启动失败（原因：chrome-devtools-mcp 未装 / 部署探测超时 / credentials 收集失败）
    sprint-batch 主流程不受影响，可单独跑 /sprint-aiauto-test --once 重试

📌 下一步：

★ **批量执行已全部完成，进入人工联调与验证阶段**：

1. **逐项审视"待人工清单"**（本次批量累计生成）：
   - `docs/bugfix/{version}/bugfix-{今日}-{user}.md`「待修 bug」段（bugfix 循环超限残留）
   - `docs/testing/{version}/sprint-*/sprint-*-test-report.md` 「失败用例 / Critical 问题」段
   - **★**：`docs/testing/{version}/正式用例/**` 与 `docs/testing/{version}/研发自测/**` 末尾「问题汇总清单」表（含 aiauto-test 自动回写的 C-NNN 行）
2. **跨 Sprint 联调验证**：基于研发执行计划（全部分册）的功能依赖链，按业务流跑端到端验证（不以单 Sprint 为单元）
3. **集中修复**：用 `/sprint-bugfix` 批量处理累计 bug 清单（自动拾取「问题汇总清单」+ 零散 bug 文件）
4. **回归测试**：修复完后用 `/sprint-aiauto-test --once` 跑浏览器实测复核
5. **发布**：人工裁决全部通过后执行 `/version {version}` 打 tag + 推送

如需重跑某个未完成的 Sprint：`/sprint-full {NNN}`
如需继续剩余 Sprint：`/sprint-batch {NNN}-`
切回"遇阻即停"模式：`/sprint-batch --stop-on-blocker`
跳过 AI 自动化测试：`/sprint-batch --skip-aiauto-test`
AI 自动化测试不询问直接跑：`/sprint-batch --auto-aiauto-test`
```

## 使用示例

```bash
# 场景 1：版本规划刚完成，一键跑完所有 Sprint + 自动询问跑 AI 自动化测试（★ 默认）
/version V0.1.0 "M1 MVP"         # 生成需求+设计+计划+研发自测方案+自测用例
/sprint-batch                    # 批量执行 → Step 6 自动询问部署 + 调 /sprint-aiauto-test
# → 全通过 → /version V0.1.0 发布
# → 有失败 → 失败用例自动回写问题汇总清单 → /sprint-bugfix 拾取并修复 → /sprint-aiauto-test --once 回归

# 场景 2：先跑前 3 个 Sprint（仍触发 Step 6 — 测试 Sprint-003 完成后的产物）
/sprint-batch 001-003

# 场景 3：跳过 Sprint 内 bugfix 循环（所有 bug 批量收尾统一处理）+ 跳过 AI 自动化测试
/sprint-batch skip-bugfix --skip-aiauto-test
# 后续：/sprint-bugfix → /sprint-aiauto-test --once

# 场景 4：无人值守模式 — AI 自动化测试自动跑不询问
/sprint-batch --auto-aiauto-test
# 适合 deployment 配置已完整 + 部署模式 local 的本地循环验证

# 场景 5：某个 Sprint 被卡住，单独重跑（不触发 AI 自动化测试 — /sprint-full 不包 Step 6）
/sprint-full 003
```
