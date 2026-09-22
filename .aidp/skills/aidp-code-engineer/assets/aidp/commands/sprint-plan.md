# /sprint-plan — 研发执行计划生成

你正在执行 `/sprint-plan` 命令，为当前版本生成迭代执行计划。

**★ 本命令是 skill 编排器**：调用 `dev-execution-planner` skill 从 PRD 需求、原型、详细设计生成研发执行计划。

参数：$ARGUMENTS（可选）
- 第 1 位：版本号（如省略，从 AGENTS.md 当前状态读取）
- `--supplement={NN}`：★ 补充模式— 产品在版本开发中途更新了 PRD **或原型**，由 `/version` 检测变更后传入；本命令产出研发执行计划增量 `NN_<业务主题>.md`（约定 15 统一命名，文件名不带"补充"字眼、补充身份记入 `00_索引.md`）而非覆盖主文档；详见下方「补充模式」段
- `--ledger-cascade`：★ 约定 22 级联落盘 — 由攒批收口子 Agent / `--cascade-now` 即时级联调用；**就地改** `docs/plans/{version}/01_研发执行计划.md` 正文 + 刷该目录 `00_索引.md` 生成时间；⛔ **不新建任何分册**（`NN_<业务主题>.md` 是产品侧 PRD/原型变更与口述累进的命名空间），⛔ 不产任何中转增量册；与 `--supplement={NN}` 互斥；详见下方「补充模式」段
- `--scale=S|M|L`（可选）：需求规模档位，透传给 `dev-execution-planner` SKILL（缺省回退 L 现状全套）。由 `/version` Step 2.4.1.5 自动判档时自动带入；直接调用可手动指定。调 SKILL 时随 prompt 传入 `scale=<档位>`
<!-- dup-check: ignore 四个规划子命令各需在自己参数表里声明，刻意的四份、非漂移 -->
- `--unattended`（可选）：★ **无人值守上下文标记**（由 `/version`·`/sprint-autopilot`·`/sprint-test` 等上游透传）——本命令内**一切 `AskUserQuestion` 与"暂停待用户裁决"一律不弹**，改按下方各门的确定性默认自动推进并留痕；**绝不静默跳过质量门**，只是把"问人"换成"按保守默认走 + 记录"。⛔ 上游传了而本命令不认，flag 会被静默丢弃、在无人值守链里挂死。
  - 本命令的门：Step 1.5 回检 ❌ 时"列 Fail 询问用户"→ 无人值守下**按退出码分流自动处置**（`1`=判违规、暂停并返回失败信号交上游熔断；`2`=入参错，修正路径后重跑一次，仍失败才返回失败信号），⛔ 不得无限重试、也不得当作通过继续。

## 前置流程

按 `docs/init/06_版本与用户目录约定.md`：
1. **{version}** ← `AGENTS.md`「当前状态.当前版本」，读不到则询问。
2. **{user}** ← `git config user.name`

## 前置检查

1. 确认需求文档已存在：`ls docs/requirements/{version}/研发需求/{01_研发需求,00_索引,00_研发需求}.md 2>/dev/null` 任一命中即可（拆分态 `00_索引.md`+`01_研发需求.md` / 历史裸 `00_研发需求.md` 兼容）
   - 若不存在 → **停止执行**，提示"需求文档不存在，请先执行 /sprint-requirements"
2. 确认设计文档已存在：`ls docs/design/detail/{version}/*.md` 有内容主文档即可（★ **glob 探测、兼容约定 14 三态**——拆分态 `01_详细设计.md`…〔新生成〕 / 历史单份态 `00_详细设计.md` / 历史存量裸名 `详细设计.md`〔后两者仅存量 grandfather〕；不硬编码裸名，与本命令 53/168/191 行 glob 口径一致）
   - 若设计目录无任何内容主文档 → **停止执行**，提示"设计文档不存在，请先执行 /sprint-design"

## 执行步骤

### Step 1：调用 dev-execution-planner skill

**★ QR 变更范围裁剪协议接线（必须传，别让增量迭代付全量 QR 的代价）**：`dev-execution-planner` 的质量检查支持按本轮变更范围裁剪，**唯一入参 = `qr_delta_scope`（可选，不传 = 全量）**。⛔ 命令端**不得自造 `qr_mode`**——该 SKILL 从未定义它（`qr_mode` 是 `dev-manual-testcase` 独有概念），凭空传等于修改 SKILL 契约（违反约定 21）且被静默忽略。命令端按下面两条传：

- **全量生成**（首次规划 / 主文档重生成）→ **不传 `qr_delta_scope`**（SKILL 契约：不传 = 全量）。
- **增量补充**（`/version` 补充模式〔情况 B-2〕检出 PRD/原型变更后**派发本命令并传入** `--supplement={NN}`；⛔ `/version` 自身没有 `--supplement` flag，别照字面去敲）→ 传 `qr_delta_scope = <本轮 NN_<业务主题>.md 的专题名 / 章节清单>`。
- ⛔ **只裁「语义核对」的范围，机器门一律全量跑**（SKILL 明文，标「全量」档的维度不接受裁剪——它们的失效形态正是「新增这一处与旧的那些不一致」，只看增量内部一个都发现不了）。算不出 Δ 就退回全量并注明，**宁可多算一个专题、绝不漏传播一处语义**。

使用 `Skill` 工具调用 `dev-execution-planner`，由 skill 自主完成执行计划生成 + 多维度独立 Agent 检查（详见 SKILL.md）+ 多轮 Quality Review 阻塞完成判定。**SKILL 内规则为单一信源**（含多用户判定 / AIDP 资源扫描 / 上游引用规则 / 核心原则 / 拆分控制 / 不中断原则 / 金额字段类型守恒等），命令端按 AGENTS.md 约定 21 不复述、不修改，仅做编排和项目级补充。

> 详细规则查 `{{AIDP_HOME}}/skills/dev-execution-planner/SKILL.md`；命令端只负责传入路径上下文 + Step 1.5 grep 回检（项目级补充）。
> **项目级补充**（喂给 SKILL prompt 的本项目上游路径）：PRD=`docs/requirements/{version}/研发需求/`、原型=`docs/prototype/{version}/`、详设=`docs/design/detail/{version}/`。

**调用参数**（按 SKILL 输入要求传入 PRD / 原型 / 详细设计三类路径）：
- **PRD 路径**：`docs/requirements/{version}/研发需求/`（含 `01_研发需求.md`（历史裸 `00_研发需求.md` 兼容）或拆分的 `0?_*.md`）
- **原型路径**：`docs/prototype/{version}/code/` / `docs/prototype/{version}/mockup/`（任一存在即可）
- **设计文档路径**：`docs/design/detail/{version}/`（含本目录下全部分册）
- **★ 既有项目代码根**：`code/`（存在即传）——SKILL 把它列为「推荐；详细设计含『✅ 沿用已有』接口或第三方对接时**升为必需**」，其「接口可用性深度核验」是 **Critical** 步骤、判据脚本要吃**代码根目录**。不传 ⇒ 该 Critical 核验无输入、静默降级

**★ 项目级约束补充（必须写进 SKILL prompt —— 不写则产出的 Task 会与本项目硬约定冲突）**：

SKILL 的 `references/task-templates.md` Task 1.2「第三方中间件配置」模板会被原样写进 `01_研发执行计划.md` 的验收标准。其中一条与本项目硬约定冲突、须在 prompt 里显式覆盖；另一条只需声明本项目的选择。命令端**不改 SKILL**（约定 16）：

- **验收动作不得含「启动服务 / 完整构建」**（约定 35）：**SKILL 侧已自禁且判据更细**——`task-templates.md` 的验收标准把后端编译命令**转授权**给 `references/stack-java-spring.md`「二、开发期轻量验证」（该节是其 Java 编译命令唯一信源：默认 `mvn -q compiler:compile` 直调 goal 不走 lifecycle，⛔ 明令不得直接写 `mvn compile`），另有「严禁启动被测服务」铁律与「⛔ 不含『启动应用连接成功』」。与约定 35 **一致，无需命令端覆盖**；prompt 里不必重述（约定 21）。⚠️ 仅在上游回退该铁律时才需恢复覆盖——真实连通性验证一律挪到部署后的 `/sprint-aiauto-test`。
- **不产出 `.env.example`**（约定 25，**声明选择、非覆盖冲突**）：SKILL 已把该文件明确为**可选形态、由调用方规范决定**，本项目按约定 25 选「运行时配置文件即权威、不维护示例副本」。**替换落点** = `docs/deployment/{version}/配置文件/增量/配置项清单.md`。prompt 里声明本项目的选择即可，不必再写覆盖理由。
- 连带：`check_env_config.py` **先判形态再决定跑不跑**——项目无 `.env`/`.env.example` 且配置文件不用 `${}` 环境变量引用时，它返回 `skipped=true` + `total_checks=0` + `checks=[]` + **exit 0**，即**整份 N/A**。⛔ **读 `--json` 时必须先看 `skipped`**：`skipped=true` 时 `failed_critical=0` / `all_passed=true` 只是"没跑"，**不是"跑过且通过"**——把 N/A 读成通过正是脚本自身注释点名要防的假绿。`skipped=false` 时才逐项读其检查结果（`.gitignore` 排除 `.env`、配置文件 `${}` 引用等）；其中「`.env.example` 文件存在」为 `Important`，采用「运行时配置文件即权威、不维护示例副本」形态时属正常，不构成阻断。

**额外提示**（命令端在调用 prompt 中补充，让 skill 的资源扫描覆盖本项目）：
- 让 skill 扫描 `{{AIDP_HOME}}/commands/` 作为 L2 层可用命令
- 让 skill 扫描 `{{AIDP_HOME}}/skills/` 作为 L2 层可用 skill
- 让 skill 把 `docs/architecture/`（架构约束 / 技术选型 / UI 规范约束 + 可选架构设计文档，全目录识别）作为约束条件
- 多人协作时，把"功能模块 → 开发者"分配关系显式说明，触发 skill 第零步多用户分支

**★ SKILL 路径占位符显式传参**：`dev-execution-planner` 的 DDL Task 输出路径包含占位符 `{SQL脚本目录}/v{版本号}/{NN}_<中文名>.sql`，**禁止让 SKILL 自动推断**——显式传 `{SQL脚本目录}=code/sql/`（与 dev-logic-architect Module D 落盘保持一致；映射表见 `docs/init/06` §2.5.7）。

**★ 项目级补充 — 信号传递（精简，按约定 21）**：

```
【项目级补充 — 信号传递】

本次调用是 /version 串联场景，**上游来源齐全**：
- 研发需求：docs/requirements/{version}/研发需求/*.md（version.md Step 2.4.1 已产出）
- 详细设计：docs/design/detail/{version}/*.md（version.md Step 2.4.2 已产出）
- 原型代码：docs/prototype/{version}/code/（含 .jsx/.vue/.html 等）
- 高保真原型：docs/prototype/{version}/mockup/（如存在）

【信号】上游齐全 → 请走严格模式（不走"独立使用上游不全时"的宽松判定）。

SKILL 内置规则单一信源（命令端按约定 21 不复述，不写死列数/阈值）：任务表结构 + 行级三锚点（REQ / 设计 / 原型）+ 粒度/EPIC 完整性，均由 SKILL 内置硬核回检 + `scripts/check_task_granularity.py` 把关（详见 SKILL.md）。命令端仅传参 + 编排。
```

命令端把上述 prompt 作为「调用约束」原样追加到 SKILL 调用的 system prompt 末尾。SKILL QR 通过后，命令端在 Step 1.5 用 bash grep 兜底核验（详见 Step 1.5）。

**输出**：skill 生成执行计划内容。命令端按 AIDP 落盘到 `docs/plans/{version}/01_研发执行计划.md`（内容主文档从 `01_` 起 + 专职 `00_索引.md`，约定 15）。**dev-execution-planner SKILL 原生只产**：单用户 `00_索引.md` + `01_研发执行计划.md`；多用户 `00_索引.md` + `NN_研发执行计划-{开发者姓名}.md`。**拆分阈值与拆分维度以 `dev-execution-planner` SKILL 为单一信源**（约定 21），⛔ 命令端不另立数值阈值、不另立拆分维度——SKILL 按内容量拆（>800 行/60KB、Task>40、单 Phase Task>15）且维度是 **Phase**，命令端另立「按里程碑拆」会同时造成两种错：Task 少却跨 3 里程碑时被强拆成撞 SKILL「严禁 <150 行碎片」的分册（`check_doc_split.py` 恒红），以及真正该拆的（单 Phase Task>15）因里程碑只有 1 个而不拆。`00_` 槽位恒归专职索引 `00_索引.md`，内容主文档从 `01_` 起。

> ★ **归一边界**：`00_索引.md` + `01_` 序号态由 SKILL 原生产出（里程碑分册 `0N_M{N}研发执行计划.md` 属命令级拆分产物，仍占 `01_` 起序号、`00_索引.md` 照常由 SKILL 维护）；`/version` 串联场景下最终由其 Step 2.4.4 统一幂等归一/校验，本命令**单独调用**时在此就地生成兜底（幂等，已合规则不动）。

> skill 自带的"AI 执行指令"会引用本项目 L1/L2 层命令（`/sprint-dev` 等）+ L3 superpowers + L4 工具——命令不需要重复约定。

### Step 1.5：★ 上游溯源 + 越界检查 — SKILL Quality Review 复核

> 上游溯源完整性 + 越界判定（Task PRD/原型/详细设计来源、章节+行号精度、禁写 DDL/接口设计）的规则、脚本、退出码与 `--json` 分档口径**单一信源 = `{{AIDP_HOME}}/skills/dev-execution-planner/references/flow-qr-dispatch.md`「🛡️ 落盘后 bash 硬核回检」**（由其质量检查子 Agent 步骤 0 强制跑）。命令端**不另列脚本清单、不复述阈值**。
>
> 需要复核时（SKILL 报告缺脚本退出码证据 / 产物明显违规）→ **派一个独立子 Agent 按该文件原样跑全部脚本**（`<SKILL_DIR>` = `{{AIDP_HOME}}/skills/dev-execution-planner`，计划目录 = `docs/plans/{version}/`），只回传各脚本退出码 + `--json` 的必修 / 警告 / `skipped` 摘要；⛔ 不在主对话内联跑。

判违规 → 暂停 Step 2，把退出码 + 报告正文展示给用户，让 SKILL 重写；退出码 `2`（入参错）→ 修参数重跑，不算产物违规。SKILL QR 标记通过但产物明显违规 → 视为 SKILL 缺陷，在模板仓库修 SKILL（约定 16），不在此步绕过。

### Step 1.6：★ DDL Task SQL 路径回写到最终部署位置（搬迁配套，镜像 sprint-design Step 3.2 ④）

> `dev-execution-planner` 按 `{SQL脚本目录}=code/sql/` 暂存位生成 DDL Task 路径 `code/sql/v{版本号}/{NN}_<中文名>.sql`（Step 1.5 的上游 `check_sql_path_handoff.py` 亦按此**暂存格式**校验 `/v{版本号}/` 子目录，故本回写**必须在 Step 1.5 校验通过之后**跑、绝不可提前——P2 是 `warn` 档、不置 `passed=False`，提前回写只多一条 Important 告警噪音（与本文件上方同一口径））。但 SQL 最终落 `docs/deployment/{version}/sql/增量/`（约定 6/11，由 `/sprint-design` Step 3.2 按源文件跟踪状态归位）——故命令端在上游校验通过后，把研发执行计划正文里的暂存位 SQL 路径**确定性回写**为最终部署位置，避免"SQL 已在最终位置、计划仍指暂存位"的断链（`/sprint-dev` 按约定 6 从 `docs/deployment/{version}/sql/增量/` 检测应用 SQL，计划路径须与之一致）。纯确定性文件替换，命令端内联跑（与 sprint-design ④ 同）。

```bash
# 回写研发执行计划全部分册（单文件 01_ / 拆分 00_总览 + 0N_ / 00_索引）中的暂存位 SQL 路径 → 最终部署位置
# 暂存位 code/sql/v{版本号}/ (或 V/ 无前缀变体) → 最终 docs/deployment/{version}/sql/增量/（版本已在 deployment 下，折叠掉 v{版本号} 子目录层）
for f in docs/plans/{version}/*.md; do
  [ -f "$f" ] || continue
  sed -i -E 's#code/sql/[Vv]?[0-9]+(\.[0-9]+){0,2}/#docs/deployment/{version}/sql/增量/#g' "$f"
done
echo "✅ 研发执行计划 SQL 路径已回写到最终部署位置 docs/deployment/{version}/sql/增量/（如含 DDL Task；无 SQL 则 no-op）"
```

> 幂等：只匹配 `code/sql/<版本>/`，已是 `docs/deployment/…` 的不动；standalone 单独调用（未经 /version 串联）同样适用——SQL 落位由约定 6 恒定，与是否本轮跑过 sprint-design 无关。

### Step 2：PM Agent 补充任务分配矩阵 + 关联文档

读取 `{{AIDP_HOME}}/agents/pm.md` 获取 PM Agent 角色定义。

**在 `01_研发执行计划.md` 头部**（紧跟标题之后，正文之前）注入「关联文档」章节：

```markdown
## 关联文档

> 路径约定：见 `docs/init/06_版本与用户目录约定.md` §4.x「文档内引用路径的写法」（单一信源，本处不复述）。

| 关系 | 文档 |
|------|------|
| ⬅ 上游输入 | `../../requirements/{version}/研发需求/*.md`；`../../design/detail/{version}/*.md`（详细设计 / 接口设计 / 数据库设计 / 各专题） |
| ➡ 下游引用 | Sprint 期 `code/` 实现；`../../testing/{version}/sprint-{NNN}/`（Sprint 期生成） |
| ↔ 同版本平行 | `./NN_研发执行计划-{开发者姓名}.md`（多人协作时，每人一份，从 `01_` 起）；拆分时回链 `./00_索引.md` |
| 🔗 全局约束 | `docs/architecture/架构约束.md`；`docs/architecture/技术选型.md`；`docs/architecture/UI规范约束.md`；`docs/architecture/架构设计.md` 或 `架构设计/`（如有）；`memory/systemPatterns.md` |
| ⏮ 跨版本前序 | `../../plans/{prev-version}/01_研发执行计划.md`（历史裸 `00_研发执行计划.md` 兼容；如 `{prev-version}` 存在） |
| 📌 关键 memory | `memory/{version}/{user}/activeContext.md`；`memory/{version}/{user}/progress.md` |
```

**拆分时（触发条件由 SKILL 判定）**：`00_索引.md` 必须**逐行列出**所有内容分册（含 Sprint 范围 / 关键交付物 / 生成时间）；各分册的「同版本平行」也回链 `00_索引.md`。

**在 `01_研发执行计划.md` 末尾补充**：

> ⛔⛔ **填矩阵前先读这两条硬规则**（单一信源 = `docs/init/06_版本与用户目录约定.md` §3.3 / §3.4，本处只做落地提示）：
>
> 1. **Sprint 编号跨版本连续自增、不随版本重置**——本版第一个 Sprint 的号 **必须**取自
>    `python3 {{AIDP_HOME}}/scripts/check_sprint_numbering.py next`（跨全部版本扫 MAX+1）。
>    ⛔ **严禁**新版本又从 `Sprint-001` 起：编号是项目全局流水号，重置会让同一项目出现多个 `sprint-001`，
>    bugfix 记录 / `testing/{version}/sprint-{NNN}/` / Sprint 归档全部无法只凭编号定位（下游实测问题）。
> 2. **一个 Sprint = 一个可独立验收的功能单元；同一功能的前后端任务归属【同一个】Sprint**——
>    即**一行 = 一个功能模块 = 一个 Sprint，前后端填在同一行的两列**（正是下表表头的语义）。
>    ⛔ **严禁**把一个功能的前端、后端拆成两个 Sprint（下游实测问题）：那样任一 Sprint 都无法独立验收——
>    前端 Sprint 无接口可联调、后端 Sprint 无页面可验证，`/sprint-test` 验收循环与 `/sprint-close` 归档均失去意义。
>    上游 `dev-execution-planner` 按「**EPIC × Sprint × Task** 三层模型」产出（含「Sprint 排期总览」与「REQ ↔ EPIC ↔ Sprint 三级索引表」，编号形如 `Sprint-NNN`）——**Sprint 层由 SKILL 自产，命令端不另建编号体系**，本表只是它的任务分配视图：
>    **一个 Sprint 承载一个或多个 EPIC 的完整交付**，EPIC 内前端/后端/测试三类 Task 一并落入同一 Sprint。
>    确属纯前端/纯后端的需求 → 在该行显式标注「单端 / 仅前端 / 仅后端」豁免。
>
> **落盘后必跑回检**（Critical 项不过即修正矩阵，勿带病进 Sprint 执行期）：
> ```bash
> python3 {{AIDP_HOME}}/scripts/check_sprint_numbering.py check
> ```

```markdown
## 任务分配矩阵

| 功能模块 | 后端任务 | 前端任务 | 负责人 | Sprint | 对应需求章节 | 对应设计章节 |
|---------|---------|---------|--------|--------|------------|------------|
| {模块1} | {API 数量} 个接口 | {页面数量} 个页面 | {user} | Sprint-001 | `01_研发需求.md#xx-模块` | `01_详细设计.md#xx-模块` |

> **必须**：每行的「对应需求章节」「对应设计章节」要给出**可点击的 anchor 链接**（指向 `01_研发需求.md` 与 `01_详细设计.md` / `03_接口设计.md` 等的具体小节）；这是把计划与上游需求/设计绑死的关键。

## Sprint 文件级冲突矩阵（★ 并行可行性的唯一判据，必须规划期产出）

> **为什么必须在规划期产出、不能执行期临时判断**：并行执行的两个 Sprint 若触碰同一文件，
> 会**互相覆盖且不报错**——没有任何机制会告诉你结果被吞了。而执行期才判断时，
> 各 Sprint 的实际改动面尚未确定，判据不可靠。故冲突面**只能**在规划期按 Task 的
> 「涉及文件」清单静态求交集得出。
>
> **列什么**：逐对列出触碰同一文件的 Sprint（含具体冲突文件），无交集的显式标注"无冲突"。
> 文件粒度到具体路径，**不要写目录**（`src/views/` 这种粒度会把本可并行的判成冲突）。

| Sprint 对 | 冲突文件 | 结论 |
|----------|---------|------|
| Sprint-001 × Sprint-002 | `src/api/user.ts` | ❌ 有冲突，必须串行 |
| Sprint-001 × Sprint-003 | — | ✅ 无冲突，可并行 |

> ⚠️ **"可并行"只表示【文件级无覆盖风险】，不等于"应该并行"**：还需满足①无业务依赖（后端接口须先于前端联调）
> ②各自可独立验收。当前 `/sprint-batch` 与 autopilot **默认仍严格串行**——本矩阵先把"哪些本可并行"
> 变成规划期的显式结论（下游实测：某 Sprint 与前三个文件级零重叠、规划文档里都写了"可并行"，
> 仍排队等了 27 分钟），供人工决定是否分批分人并行推进。

## 依赖关系

- Sprint-002 依赖 Sprint-001 的 {具体模块}（见 `01_详细设计.md#xx`）

## 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 | 相关文档 |
|------|------|------|---------|---------|
```

**每份 `NN_研发执行计划-{开发者姓名}.md` 也必须含「关联文档」章节**，并在「↔ 同版本平行」行回链 `00_索引.md` 与其他人的分册。

### Step 3：生成个人计划（可选，按需）

如果项目已有多个 git user（从 `memory/` 下扫描），为每人生成：
- `docs/plans/{version}/NN_研发执行计划-{开发者姓名}.md`（从 `01_` 起自增；★ 命名以 dev-execution-planner SKILL「多用户文件命名」为单一信源——**不得**写成无两位数字前缀的 `plan-{user}.md`，那会被其 `check_doc_split.py` 判 error）

内容包含该用户负责的任务清单、执行顺序、时间估算。

### Step 4：更新状态

更新 `memory/{version}/{user}/activeContext.md`：
- 记录研发执行计划已生成
- 当前工作焦点：版本规划完成，等待 Sprint-001 执行

更新 `memory/{version}/{user}/progress.md` 的「版本历史」表格，确认 Sprint 清单。

### Step 5：★ 研发自测（方案 + 自测用例 + 测试环境与账号）—— 由独立命令 `/sprint-selftest` 负责

> ⚠️ **本命令不生成研发自测**。研发自测（研发自测方案 / 自测用例 / 测试环境与账号）由独立命令 **`/sprint-selftest`** 负责——与 `/sprint-requirements`·`/sprint-design`·`/sprint-plan` **对称**，是 `dev-manual-testcase` 生成研发自测的**唯一信源入口**。

- **版本规划串联**：`/version` 在 `/sprint-plan`（Step 2.4.3）之后、显式 **Step 2.4.3.5 调 `/sprint-selftest`** 生成研发自测；本命令只负责研发执行计划。
- **单独跑 `/sprint-plan`**：不产研发自测——需要研发自测时另跑 `/sprint-selftest {version}`。
- **约定 22 级联 L4**（研发自测用例增量）：走 `/sprint-selftest {version} --supplement={NN}`（本命令 `--supplement` 不带出自测）。

---

## ★ 硬门通用执行约束

> 本文档有**一道输出前硬门**：文末「研发执行计划回检」。遵循以下约束。

🛑 **跳过硬门 = 严重违规。** Claude 长任务跑到硬门处直接输出"✅ 完成"而没出现对应的"🔍 …输出前回检"块 → 用户有权要求"重跑硬门 / 回滚此次输出"。

**关键约束**（在输出"✅ 完成"**之前**必须做）：
1. 真实执行该门的 bash 块（用 Bash 工具跑，不是默念）
2. 逐项填该门对应的"🔍 …输出前回检"块
3. **任一 Fail → 立即停下**（输出"❌ 回检未通过 …"或不进入下一步），要求 skill 重跑或人工补齐；不得用"基本通过"等模糊措辞绕过

## ★ 输出前硬门：研发执行计划回检

> 🛑 **STOP** — 跑完 Step 1~3 后在此暂停，先跑下面 bash 块、填完"🔍 输出前回检"块，再决定能否输出"✅ /sprint-plan 完成"。**适用上方「★ 硬门通用执行约束」**。

```bash
# ⛔ 不得硬编码单一文件名：本命令自己规定多用户产物为 `NN_研发执行计划-{姓名}.md`（没有 01_ 那份），
#    拆分态另有 `0N_M{N}研发执行计划.md`——硬判 `01_` 会让合规产出被判缺失：
#    check_task_granularity.py 对不存在的路径返回 exit 2（入参错、按判定表不计 Fail ⇒ 既不核验也不判失败），
#    同时 `head -20 $FILE` 得 0 ⇒ L1 头部假 Fail。三个下游命令（sprint-start/batch/full）都已用
#    5 模式并集并加粗警告禁止硬判，唯产出方自己没跟上。
FILES=$(ls docs/plans/{version}/01_研发执行计划.md \
           docs/plans/{version}/00_研发执行计划.md \
           docs/plans/{version}/0[0-9]_M*研发执行计划.md \
           docs/plans/{version}/[0-9][0-9]_研发执行计划-*.md 2>/dev/null)
[ -n "$FILES" ] || { echo "❌ docs/plans/{version}/ 下无任何研发执行计划内容主文档"; exit 1; }
# L1 头部 / 越界检测：逐份取、合并判定
L1=$(for f in $FILES; do head -20 "$f"; done | grep -cE '(详细设计|研发 PRD|产品需求文档|原型) ?来源')
DDL_HIT=$(grep -cE 'CREATE TABLE|^interface .* \{|^表名[:：]' $FILES)
# Task 三锚点溯源 — 判定以 SKILL 脚本退出码为准；逐份跑、任一非 0 即取该码
# ⛔ 每份计划单独落 JSON 再合并判定：多份共用一个输出文件会被循环覆盖、只剩最后一份的结论
GRAN_DIR=$(mktemp -d); GRAN_EXIT=0; GRAN_SKIPPED=False; GRAN_MUST=0; n=0
for f in $FILES; do
  n=$((n+1))
  python3 {{AIDP_HOME}}/skills/dev-execution-planner/scripts/check_task_granularity.py "$f" --json > "$GRAN_DIR/$n.json"
  _e=$?; [ "$_e" -ne 0 ] && GRAN_EXIT=$_e
done
# ★ skipped（一个 Task 段都没识别到 = 未实质核验）：任一份 skipped 即整体按未核验处理
# 分档读 JSON（exit 1 内部还分两档：severity 2 = 必修 / 1 = 警告复核）
eval "$(python3 - "$GRAN_DIR" <<'PY'
import json, glob, sys
sk, must = False, 0
for p in glob.glob(sys.argv[1] + "/*.json"):
    try:
        d = json.load(open(p))
    except Exception:
        sk = True; continue
    sk = sk or bool(d.get("skipped"))
    must += sum(1 for x in d.get("findings", []) if x.get("severity") == 2)
print(f"GRAN_SKIPPED={sk}; GRAN_MUST={must}")
PY
)"
# 待澄清问题清单— 单文件含「待澄清问题清单」章节 OR 多文件含 99_待澄清问题清单.md
PENDING=$(grep -l '待澄清问题清单' docs/plans/{version}/*.md 2>/dev/null | wc -l)
PENDING_FILE=$(ls docs/plans/{version}/99_待澄清问题清单.md 2>/dev/null | wc -l)
```

**回检判定**：

| # | 检查项 | Pass 条件 | 当前结果 |
|---|--------|---------|---------|
| 1 | L1 文档级头部 | `L1 ≥ 3` | { ✅ / ❌（L1=N）} |
| 2 | 禁越界（不写设计） | `DDL_HIT == 0` | { ✅ / ❌（命中 N 处）} |
| 3 | Task 三锚点溯源 | **以 `check_task_granularity.py` 为准**（SKILL 要求每行 REQ / 设计 / 原型三锚点同时命中）：`GRAN_EXIT == 0` **且 `GRAN_SKIPPED != True`** 才算过（`skipped=True` = 一个 Task 段都没识别到、**未实质核验**，须回查 Task 标题形态 `### Task N.M` 后重跑，不得当通过）；`== 1` 且 `GRAN_MUST > 0` = 必修、`== 1` 且 `GRAN_MUST == 0` = 警告复核；`== 2` = 入参错，修参数重跑、不计 Fail。命令端不另设百分比阈值 | { ✅ / ❌（退出码 N + 必修 M 条 + 摘要）} |
| 4 | 拆分文件数控制 | 单文件，或 ≤5（含 `00_索引.md`）；**Task>60 时按 SKILL 例外放行** —— 判据以 SKILL「拆分关键约束」为单一信源 | { ✅ / ❌ } |
| 4b | **验收标准可验收性**| 每个 Task 行的「验收标准」单元格**非空且可判真假**——⛔ 不接受「完成开发」「功能正常」「按设计实现」这类无法判定的措辞。**判据委派 `dev-execution-planner` 的 QR**（机器门 `check_task_granularity.py` 只校 9 列**表头**、不看单元格内容）| { ✅ / ❌（N 行不可验收）} |
| 4c | **与已交付代码同向**| 每个涉及**已有能力**的 Task，其验收标准与 `code/` 现状**不对立**（不出现"计划要求 A、代码是非 A"却仍判通过）。⚠️ fresh 模式**同样必查**——fresh ≠ greenfield，brownfield 重规划时 `code/` 里已有大量已交付实现；核对方法与 `## 补充模式` 的「必读『代码现状』轻量核对」同一套（单一信源见该段）。⛔ **留空不算过**：留空无法区分「核对过、无对立」与「根本没核对」 | { ✅ / ❌（N 处对立）/ ⛔ 未核对 } |
| 5 | 待澄清问题清单 | `PENDING ≥ 1` OR `PENDING_FILE == 1`；P-NNN/D-NNN/Q-NNN 编号格式合法 + 🔧 暂行方案列无空白 + 不接受模糊表述（grep `待确认\|按常规处理\|参考行业惯例` 命中 = 0） | { ✅ / ❌ } |

**输出格式**：

```
🔍 输出前回检：
  1. L1 文档级头部上游引用：{✅ / ❌}
  2. 禁越界（不写设计）：{✅ / ❌}
  3. Task 三锚点溯源（check_task_granularity.py 退出码）：{exit N；✅ / ❌}
  4. 拆分文件数控制：{✅ / ❌}
  4b. 验收标准可验收性：{✅ / ❌}
  4c. 与已交付代码同向：{✅ / ❌（N 处对立）/ ⛔ 未核对}
  5. 待澄清问题清单：{✅ / ❌}
  总评：{✅ → 进入输出 / ❌ → 列 Fail 询问用户}
```

## 输出

```
✅ /sprint-plan 完成（{version}）

📋 生成的文件：
- docs/plans/{version}/00_索引.md（专职索引，恒有）+ docs/plans/{version}/01_研发执行计划.md（内容主文档）
- docs/plans/{version}/NN_研发执行计划-{开发者姓名}.md（个人计划，如有多人协作，从 `01_` 起）

★ 拆分规则（约定 15）：默认单文件；**是否拆、按什么维度拆一律由 `dev-execution-planner`
  SKILL 判定**（`docs/init/02_迭代输入指导.md §10.4` 已把该阈值整体转授权给 SKILL，
  ⛔ 命令端不另立）；`00_索引.md` 恒产出并承担分册导航。

计划摘要：
- Sprint 数量：{N} 个
- 总功能模块：{N} 个
- 预计总工期：{N} 周

Sprint 拆分：
  Sprint-001：{目标}（{N} 天）
  Sprint-002：{目标}（{N} 天）
  Sprint-003：{目标}（{N} 天）

📌 下一步：
/sprint-start 001 → 启动第一个 Sprint 的执行
```

---

## 补充模式（`--supplement={NN}`）

当版本开发中途产品更新了 PRD **或原型**且需求/设计补充已就绪时，由 `/version` 调用本命令并传入 `--supplement={NN}`。**fresh 模式（无此参数）保持原流程不变**。


### ★ 约定 22 级联落盘（`--ledger-cascade`，与 `--supplement={NN}` 互斥，同时传则报错）

由**约定 22 级联**调用时（攒批收口子 Agent / `--cascade-now` 即时级联）**必须**加 `--ledger-cascade`：**就地改内容主文档正文** `docs/plans/{version}/01_研发执行计划.md`，改完刷该目录 `00_索引.md` 生成时间（约定 15）。
⛔ 不新建 `NN_` 分册、不产中转增量册、不全量扫 `code/` 等落盘细则与内容产出方式，**单一信源 = `{{AIDP_HOME}}/reference/开发期族增量.md`「收口执行要点」第 2/3 条（L3 计划）**，本命令不复述。

### 输入差异
- **必读** `docs/requirements/{version}/研发需求/输入变更-{NN}.md`（含 PRD 与原型两类变更）
- **必读** 本轮研发需求增量 `docs/requirements/{version}/研发需求/NN_<业务主题>.md`（文件名不带"补充"字眼；补充身份见 `00_索引.md`）
- **必读** 本轮各类设计增量（详细设计 / 接口设计 / 数据库设计 增量，均为 `docs/design/detail/{version}/NN_<业务主题>.md`）（如有）
- **必读** 原 `docs/plans/{version}/01_研发执行计划.md`（历史裸 `00_研发执行计划.md` 兼容；基线，只读）
- **★ 必读「代码现状」轻量核对（★ 三条路径都适用：`--supplement` / `--ledger-cascade` / **fresh 模式的输出前硬门 4c**——本段是它们共同的单一信源）**：⛔ 别只挂在
  `--supplement` 上——`--ledger-cascade` 走的是约定 22 攒批收口，**输入台账里的每一条本就来自「代码已经改过」**，
  更需要核对代码现状；收口时「被后续改动推翻的条目直接作废」这条规则若不核代码就无从执行。若四项输入
  **全是文档**、输出前硬门也**不触碰 `code/`**，则"计划要求 A、已交付代码是非 A"这类对立
  在 standalone `--supplement` 路径上无人拦（`version-auditor` D-2/D-3 只判结构性冲突，且只在
  `/version` 链内跑）。这里只做**轻量**核对、不做全扫（全扫归 `/sprint-design` Step 0.3 四象限）：
  - 对本次增量涉及的每个功能点，`grep` 一次 `code/` 看是否**已有反向实现**（如计划写"新增 X 开关"
    而代码里 X 已被删除 / 已按相反默认值交付）。
  - 命中 → **不自行改计划**：在传给 skill 的 prompt 里显式列出「计划意图 vs 代码现状」的冲突条目，
    由 skill 按"代码是最终事实源"决定是改计划还是登记为待澄清。
  - 未命中 → 一句话记「已核对，无对立」，⛔ 不留空（留空无法区分"核对过没冲突"与"根本没核对"）。
- **传给 skill 的 prompt 必须显式说明**：「本次仅产出新增 / 取消 / 时间调整的 Sprint 任务；未变 Sprint 不重复；新增任务关联输入变更摘要小节（PRD / 原型）+ 各类补充文档小节」

### 输出差异

★ **命名保持**：dev-execution-planner SKILL 内部按其默认产物路径风格生成纯 `NN_业务名.md`（已禁"补充/追加"语义前缀）；命令端返回后**只做序号续编校正**——规则与 `/sprint-design` 同款、**单一信源见 `{{AIDP_HOME}}/commands/sprint-design.md`「命名保持」段**，本处不复述（约定 21）。<!-- dup-check: ignore 已改为指针，此行是指针本身 -->

| 文档 | SKILL 默认产物路径（待归一） | 归一后路径（统一 `NN_<业务主题>.md`，文件名不带"补充"字眼） |
|------|-------------------------|--------------------------|
| 研发执行计划 | `NN_业务名.md`（SKILL 统一带 NN_ 前缀、不带"补充/追加"字样） | 单文件 → 内容主文档即 `01_研发执行计划.md`（历史裸 `00_研发执行计划.md` 兼容），增量 `docs/plans/{version}/NN_<业务主题>.md` 续编（补充身份记入 `00_索引.md`）|

- 内容含「本轮变更总览」表（新增 N 任务 / 取消 M 任务 / 调整 K 任务）
- 任务分配矩阵中**仅列**变更行，每行标注 🆕 / 🔄 / ❌
- 「依赖关系」段说明本轮新增任务对原 Sprint 的影响
- **业务主题**：① 用户调 `/sprint-plan {version} --supplement={NN} "<主题>"` 显式传；② 从研发需求增量文件名/头部解析；③ 兜底 `增量NN{NN}`
- 子目录+前缀场景：在归一后的增量文档头部第一段加「本补充信息」段：`> 共享编号 NN={NN} | 本目录续编序号 {NEXT} | 业务主题：{TOPIC}`
- 在目录 `00_索引.md` 登记该增量行（类型=补充 + 生成时间，**用归一后的真实路径**）
- ⛔ **不回写 `01_研发执行计划.md`**——与本节上方「开发期一律不改 `01_` 内容主文档正文」一致，合并回主文档是发布期 `/version` Step 3.3.10 的**专属**动作。下游 `/sprint-dev` 读计划时按 `00_索引.md` 的清单 union 主文档 + 各增量（与另三个姊妹命令的 `--supplement` 同口径）
