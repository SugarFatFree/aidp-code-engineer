# /sprint-start — Sprint 启动（执行模式）

你正在执行 `/sprint-start` 命令，启动当前 Sprint 的执行。

**★**：需求和设计已在版本规划时生成，本命令只负责读取需求、更新状态、启动执行。

参数：$ARGUMENTS
请从参数中解析 Sprint 编号。
格式示例：`/sprint-start 001`

如果参数不完整，询问用户提供 Sprint 编号。

| 参数 | 说明 |
|------|------|
| `--unattended` | **无人值守上下文标记**（由 `/sprint-full` → `/sprint-batch` → `/sprint-autopilot` 逐层透传）：本命令全程**⛔ 绝不弹 `AskUserQuestion`**——参数不完整或前置检查不通过时直接输出原因并停止，交上层编排按失败信号处理。 |

## 前置流程

按 `docs/init/06_版本与用户目录约定.md`：
1. **{version}** ← 项目记忆文件（路径经 `python3 .aidp/scripts/agent_env.py memory-file` 取：`AGENTS.md`，只用 Claude Code 时为 `CLAUDE.md`）「当前状态.当前版本」
2. **{user}** ← `git config user.name`
3. 后续路径全部使用解析到的 `{version}` / `{user}`。

## 前置检查

1. 读取 `memory/{version}/{user}/activeContext.md`，**确认无进行中的 Sprint**
   - 若有未关闭的 Sprint → **停止执行**，提醒用户先 `/sprint-close`
2. **确认需求文档已存在**：`ls docs/requirements/{version}/研发需求/{01_研发需求,00_索引,00_研发需求}.md 2>/dev/null` 任一命中即可（**不硬编码裸名**——multi 模式按系统拆分时 `01_研发需求.md` 本就不存在，硬判会把合规项目误判缺失而**错误停止执行**；口径同 `/sprint-design` 前置门）
   - 若不存在 → **停止执行**，提示"需求文档不存在，请先执行 /version 进行版本规划"
3. **确认研发执行计划已存在**：`ls docs/plans/{version}/{01_研发执行计划,00_索引,00_研发执行计划}.md docs/plans/{version}/0[0-9]_M*研发执行计划.md docs/plans/{version}/NN_研发执行计划-*.md 2>/dev/null` 任一命中即可（**不硬编码裸名**——`/sprint-plan` 对多用户产 `NN_研发执行计划-{开发者}.md`、里程碑 ≥3 产 `0N_M{N}研发执行计划.md`，硬判会把这两类合规产出误判缺失而**错误停止执行**）
   - 若不存在 → **停止执行**，提示"研发执行计划不存在，请先执行 /sprint-plan 或 /version"
4. **确认设计文档已存在**：`docs/design/detail/{version}/`
   - 若不存在 → **停止执行**，提示"设计文档不存在，请先执行 /version 进行版本规划"

## Step 1：读取计划与需求（职责分离）

**Step 1.1 从研发执行计划获取本 Sprint 的"何时做"**

读取 `docs/plans/{version}/` 下**全部** `*研发执行计划*.md`（★ 口径同上方前置门第 3 条，**不得**硬编码 `*研发执行计划*.md`——前置门放行的两类合规拆分产物 `NN_研发执行计划-{开发者}.md` / `0N_M{N}研发执行计划.md` 在硬判下都不存在，会让本步指向一个不存在的文件），在其中定位 `Sprint-{NNN}` 行，提取：
- **Sprint 目标**（一句话）
- **包含的功能模块列表**
- **开始 / 结束日期**与时间估算
- **任务分配**（如有）
- **依赖与风险**

**Step 1.2 从研发需求获取本 Sprint 的"做什么"**

读取 `docs/requirements/{version}/研发需求/01_研发需求.md`（或拆分后的 `0?_*.md`），按 Step 1.1 拿到的功能模块列表过滤，加载这些功能的：
- 功能描述
- 验收标准（AC）
- 排除项
- 依赖
- 增量需求章节（如 `增量需求：Sprint-{NNN}`，是追溯标记）

## Step 2：更新 memory/{version}/{user}/activeContext.md

重置并更新 activeContext：
- 当前 Sprint 编号
- Sprint 目标（**来源：`*研发执行计划*.md`（全部分册）**）
- 本次迭代范围 = 功能模块列表 + 各模块的验收标准（**来源：`*研发执行计划*.md`（全部分册） + 研发需求/01_研发需求.md 联合**）
- 开始 / 结束日期（**来源：`*研发执行计划*.md`（全部分册）**）
- 当前工作焦点：等待开发
- 子迭代记录：清空，准备记录新的 Round

## Step 3：更新项目记忆文件

路径经 `python3 .aidp/scripts/agent_env.py memory-file` 取（⛔ 不写死 `AGENTS.md`），定点更新「当前状态」区域：
- 当前 Sprint：Sprint-{NNN}
- 当前阶段：执行中

## 输出

```
✅ Sprint-{NNN} 已启动（执行模式）

版本 / 开发者：{version} / {user}
Sprint 目标：{来源：`*研发执行计划*.md`（全部分册）}
功能数量：{N} 个
开始 / 结束：{date} / {date}（来源：`*研发执行计划*.md`（全部分册））

📋 输入文档（已存在）：
- docs/plans/{version}/*研发执行计划*.md — Sprint 范围、目标、排期、任务分配（拆分态含多份）
- docs/requirements/{version}/研发需求/01_研发需求.md — 功能描述、验收标准

📋 设计文档（已存在）：
- docs/design/detail/{version}/*详细设计.md（glob 兼容 `01_详细设计.md` 与历史裸名）
- docs/design/detail/{version}/*接口设计.md（glob 兼容 `03_接口设计.md` 与历史裸名）
- docs/design/detail/{version}/*数据库设计.md（glob 兼容 `02_数据库设计.md` 与历史裸名）

🔄 已更新：
- memory/{version}/{user}/activeContext.md
- 项目记忆文件（AGENTS.md / CLAUDE.md）

📌 下一步：
/sprint-dev → 开始开发（前后端同时）
/sprint-dev backend → 仅后端开发
/sprint-dev frontend → 仅前端开发
```
