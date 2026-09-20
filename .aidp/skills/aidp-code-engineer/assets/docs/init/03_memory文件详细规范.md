# 03 — Memory Bank 文件详细规范

> **文档定位**：本文档提供各 Memory Bank 文件的详细说明和完整模板。
>
> **相关文档**：
> - 记忆系统总览：`00_AIDP范式主文档.md` 第 3 节（记忆层级架构）
> - 路径规则：`06_版本与用户目录约定.md`（项目级 vs 迭代级隔离策略）
> - 使用约束：各 Agent 文件的"管辖文件写权限白名单"章节
>
> **说明**：迭代级文件（activeContext / progress / sprints）改为按 `{version}/{user}/` 隔离；
> 项目级文件（projectBrief / productContext / systemPatterns / techContext / databaseBaseline）仍为单一真源，保持在 `memory/` 根。
> 路径规则权威来源见 `06_版本与用户目录约定.md`。
>
> **⚠️ memory 是本地快照、不是实时权威（读 memory 作上下文时的铁律）**：memory 记录可能**滞后于外部系统或其它成员的操作**——涉及**外部系统状态**（Issue / 缺陷、CICD 与部署状态、他人负责的进度项）时，**必须以实时查询结果为准**，memory 记录仅作线索。多人协作项目尤甚：他人的操作**不会**反映到你的 memory 文件里（如 `progress.md` 写「12 项任务均未开始」，实际可能已有成员完成数条）。据此决策前先实时拉取（`git log`、GitHub Issues / Actions、对端仓库/部署现状），**绝不按 memory 旧值重复写入他人已完成的工作**。

---

## 目录

- [1. memory/projectBrief.md](#1-memoryprojectbriefmd) — 项目级
- [2. memory/productContext.md](#2-memoryproductcontextmd) — 项目级
- [3. memory/systemPatterns.md](#3-memorysystempatternsmd) — 项目级
- [4. memory/techContext.md](#4-memorytechcontextmd) — 项目级
- [5. memory/databaseBaseline.md](#5-memorydatabasebaselinemd) — 项目级
- [6. memory/{version}/{user}/activeContext.md](#6-memoryversionuseractivecontextmd) — ★ 迭代级
- [7. memory/{version}/{user}/progress.md](#7-memoryversionuserprogressmd) — ★ 迭代级
- [8. memory/{version}/{user}/sprints/sprint-NNN.md](#8-memoryversionusersprintssprint-nnnmd) — ★ 迭代级
- [9. AGENTS.md（项目记忆文件）](#9-agentsmd项目记忆文件) — 项目级
- [10. memory/ 下的运行时状态文件](#10-memory-下的运行时状态文件) — ★ 项目级·非记忆

---

## 1. memory/projectBrief.md

**用途**：项目的"北极星"文件，记录永远不变的核心信息。

**更新频率**：初始化时创建，仅在项目方向发生重大调整时修改（极少）。

**谁来写**：PM Agent（初始化时生成）。

### projectBrief 完整模板

```markdown
# 项目简介

> 此文件为 L1 永久记忆，仅在项目方向重大调整时修改。
> 创建于：YYYY-MM-DD | 最后修改：YYYY-MM-DD

## 项目名称
[项目名]

## 核心目标（一句话）
[用一句话说明这个项目做什么、为谁做、带来什么价值]

## 解决的核心问题
[描述目标用户当前面临的具体问题]

## 目标用户
| 用户角色 | 特征描述 | 核心诉求 |
|---------|---------|---------|
| [角色1] | [特征] | [诉求] |
| [角色2] | [特征] | [诉求] |

## 项目范围
**包含：**
- ...

**不包含（明确排除）：**
- ...

## 关键成功指标（KPI）
- 指标1：[描述]
- 指标2：[描述]

## 项目时间线
- 项目启动：YYYY-MM-DD
- MVP 上线：YYYY-MM-DD

## 干系人
| 角色 | 姓名 | 职责 |
|------|------|------|
| 产品负责人 | | |
| 技术负责人 | | |
```

---

## 2. memory/productContext.md

**用途**：记录产品的"为什么"和"做什么"，以及随时间演进的功能地图。

**更新频率**：每次需求变更时更新。

**谁来写**：PM Agent。

### productContext 完整模板

```markdown
# 产品上下文

> L1 永久记忆（产品方向层），需求变更时更新。
> 最后更新：YYYY-MM-DD

## 产品解决方案概述
[产品如何解决 projectBrief 中描述的问题]

## 核心功能模块
| 模块 | 说明 | 优先级 | 状态 |
|------|------|--------|------|
| [模块名] | [功能描述] | P0/P1/P2 | 未开始/开发中/已完成 |

## 核心用户旅程

### 旅程1：[旅程名称]
[步骤描述]

## 产品约束和原则
- 原则1：[如：操作步骤不超过3步]
- 约束1：[如：必须支持国产浏览器]

## 重要产品决策历史
- YYYY-MM-DD：[决策内容和原因]

## 最近更新
- YYYY-MM-DD Sprint-NNN：[更新内容]
```

---

## 3. memory/systemPatterns.md

**用途**：记录所有架构决策（ADR）和技术规范，防止前后不一致。

**更新频率**：每次做重大技术决策时追加 ADR，只追加不修改历史记录。

**谁来写**：Architect Agent。

### systemPatterns 完整模板

```markdown
# 系统架构模式与决策记录

> L2 架构记忆，重大技术决策时追加 ADR，历史决策不可修改。
> 最后更新：YYYY-MM-DD

## 技术选型总览

| 层级 | 技术 | 版本 | 选型理由 |
|------|------|------|---------|
| 前端框架 | | | |
| UI 组件库 | | | |
| 后端框架 | | | |
| ORM / 数据访问 | | | |
| 主数据库 | | | |
| 缓存 | | | |
| 构建工具 | | | |

## 系统架构概述
[用文字或 ASCII 图描述整体架构]

## 代码规范约定

### 命名规范
- 文件名：[规范]
- 组件名：[规范]
- 函数名：[规范]
- 数据库表名：[规范]
- API 路径：[规范]

### 前端目录结构
[描述 src/ 下的目录结构约定]

### 后端目录结构
[描述后端代码的分层结构约定]

## 关键约束（来自 docs/architecture/ ）
[从架构约束文档中提取的关键约束条目]
- [约束1]
- [约束2]

## 禁止事项（反模式）
- ❌ 禁止：[具体禁止的做法]，原因：[原因]

## 架构决策记录（ADR）

### ADR-001: [决策标题]
- **日期**：YYYY-MM-DD
- **状态**：已接受 / 已废弃（被 ADR-XXX 替代）
- **背景**：[为什么需要做这个决策]
- **方案对比**：
  - 方案A：[描述] — 优点：... 缺点：...
  - 方案B：[描述] — 优点：... 缺点：...
- **决策**：[选择了哪个方案，为什么]
- **影响**：[这个决策对系统的影响]
- **相关 Sprint**：Sprint-XXX
```

---

## 4. memory/techContext.md

**用途**：记录开发环境、启动命令、环境变量、外部服务，帮助任何人（和任何 AI Agent 实例）快速上手。

**更新频率**：开发环境变更时更新，每次追加注明日期和操作人。

### techContext 完整模板

````markdown
# 技术上下文

> L2 架构记忆，环境变更时更新。更新请注明日期和操作人。
> 最后更新：YYYY-MM-DD

## 项目代码结构

### 前端项目
- **位置**：code/frontend/{project-name}/（单/多项目都套父目录；旧扁平 code/web/ 仅 upgrade 兼容）
- **框架**：[Vue3/React/...]
- **构建工具**：[Vite/Webpack/...]
- **包管理器**：[pnpm/npm/...]
- **端口**：[开发端口]

### 后端项目
- **位置**：code/backend/{module-name}/（单/多项目都套父目录；旧扁平 code/server/ 仅 upgrade 兼容）
- **框架**：[Spring Boot/NestJS/...]
- **构建工具**：[Maven/Gradle/...]
- **端口**：[服务端口]
- **context-path**：[接口路径前缀]

### SQL 脚本
- **位置**：`docs/deployment/{version}/sql/增量/`
- **命名规范**：`{NN}_<中文名>.sql`（中文命名 + 两位数字序号前缀；`99_回滚脚本.sql` 序号固定保留给本版本回滚；DDL/DML 同一序号空间按执行顺序混排）
- **示例**：`01_用户表DDL.sql` / `02_订单表DDL.sql` / `03_订单状态字典初始化.sql` / `99_回滚脚本.sql`
- 详见 `docs/init/06_版本与用户目录约定.md` §2.5.4 与 `dev-logic-architect` SKILL 的「Module D 版本归档完整性」维度（维度计数以 SKILL.md 为准）

## 运行环境要求

| 工具 | 版本要求 | 说明 |
|------|---------|------|
| [JDK/Node.js] | >= X | |
| [Maven/pnpm] | >= X | |
| [数据库] | X | |

## 快速启动

### 前端启动
```bash
cd code/frontend/{project-name}
{安装命令}
{启动命令}
```

### 后端启动
```bash
cd code/backend/{module-name}
{编译命令}
{启动命令}
```

## 环境变量说明

| 变量名 | 示例值 | 是否必须 | 说明 |
|--------|--------|---------|------|
| [变量] | [值] | ✅/📎 | [说明] |

## 外部服务依赖

| 服务 | 用途 | 接入方式 | 配置位置 |
|------|------|---------|---------|
| [数据库] | | | |
| [缓存] | | | |

## 脚手架代码参考

[说明哪些已有代码可作为新模块开发的参考]

### 前端参考
- `code/frontend/{project}/src/pages/{page}.vue` — 页面实现参考
- `code/frontend/{project}/src/api/{module}.ts` — API 调用参考
- `code/frontend/{project}/AGENTS.md` — 前端开发规范

### 后端参考
- `code/backend/{module}/` — 完整模块结构参考
- `code/backend/{module}/{sub}/src/main/java/` — 代码分层参考

## 已知问题和技术债务

- [ ] [问题描述] — [来源] — [计划处理时间]

## 变更历史

| 日期 | 操作人 | 变更内容 |
|------|--------|---------|
| YYYY-MM-DD | [姓名] | [变更内容] |
````

---

## 5. memory/databaseBaseline.md

**用途**：跨 Sprint 累积的数据库表基线，是所有已存在数据库表的**唯一权威来源**。Architect Agent 每次设计新表前必须先读取此文件，避免跨迭代重复建表。

**更新频率**：
- 初始化时创建（可为空）
- 每次 Sprint 关闭时由 Architect Agent 更新，将本次新增/变更的表追加到基线
- 每次 `/sprint-design` 前必读

**谁来写**：Architect Agent。

### databaseBaseline 完整模板

```markdown
# 累积数据库基线

> L2 架构记忆，记录项目所有已存在的数据库表。
> ⚠️ Architect Agent 设计新表前必须先读取此文件，已存在的表不得重复创建。
> 最后更新：YYYY-MM-DD | 更新 Sprint：Sprint-NNN

## 全局约定

| 约定项 | 值 |
|--------|---|
| 数据库 | [数据库类型和版本] |
| 用户/Schema | [Schema 名] |
| 表名前缀 | [前缀] |
| 主键类型 | [主键类型说明] |
| 其他约定 | [其他数据库相关约定] |

## 已有表清单

| 表名 | 用途 | 创建于 Sprint | 最后变更 Sprint | 状态 |
|------|------|-------------|----------------|------|
| [表名1] | [用途描述] | Sprint-001 | Sprint-001 | 使用中 |
| [表名2] | [用途描述] | Sprint-001 | Sprint-002 | 使用中 |

## 表关系概览

[用文字或 ASCII 图描述主要表之间的关系]

## 变更历史

### Sprint-001（YYYY-MM-DD）
- 新增表：[表名1]、[表名2]、...
- 变更表：无
- 数据初始化：[描述]

### Sprint-002（YYYY-MM-DD）
- 新增表：[表名3]
- 变更表：[表名1] 新增字段 XXX
- 数据初始化：[描述]
```

**重要规则**：
- Architect Agent 在设计数据库时，必须先检查此文件中的"已有表清单"
- 如果需要的表已存在，应复用而非重新创建
- 如果需要修改已有表（新增字段等），在数据库设计文档中标注为"变更"而非"新建"
- Sprint 关闭时，将本次新增/变更的表更新到此基线文件

---

## 6. memory/{version}/{user}/activeContext.md

**路径**：`memory/{version}/{user}/activeContext.md`（按版本 + git 用户隔离，见 `06_版本与用户目录约定.md`）

**用途**：当前版本 × 当前开发者视角下的 Sprint 实时状态文件，是 AI Agent 每次启动必读的最重要文件。

**更新频率**：实时更新（功能完成时、遇到阻塞时、每天结束时）。

**谁来写**：该 `{user}` 本人独占写入。其他用户可读不可写。

### activeContext 完整模板

```markdown
# 当前活跃上下文

> ⚠️ L3 迭代记忆。路径 `memory/{version}/{user}/activeContext.md`（用户私有，不得跨用户修改）。
> Sprint 开始时由 /sprint-start 重置，关闭时由 /sprint-close 归档到同级 `sprints/` 目录。
> 最后更新：YYYY-MM-DD HH:MM | 更新人：[姓名/Agent]

## 当前上下文

- **当前版本**：{version}（如 V0.1.0）
- **当前开发者**：{git-user}（如 alice）

## 当前 Sprint

- **Sprint 编号**：Sprint-NNN
- **Sprint 目标**：[一句话目标]
- **开始日期**：YYYY-MM-DD
- **预计结束**：YYYY-MM-DD

## 本次迭代范围

### 功能清单（含状态）

- [ ] 功能1：[描述] — 状态：待开始/设计中/开发中/测试中/完成
- [ ] 功能2：[描述] — 状态：...

### 明确排除（本 Sprint 不做）

- [排除项1]：[原因/移到哪个Sprint]

## 子迭代记录

### Round 1: [阶段名称]（YYYY-MM-DD ~ YYYY-MM-DD）
- [执行的工作]
- 状态：✅ 完成 / 🚧 进行中

## 当前工作焦点

[此刻正在做什么，完成后下一步做什么]

## 关键决策（本 Sprint 新增）

- [决策描述]：[原因] — [日期]

## 阻塞问题

- [ ] [问题描述] — 等待：[谁处理] — 开始于：[日期]

## 已完成工作

- [x] [任务描述] — 完成于 YYYY-MM-DD

## 待 Sprint 结束时同步

- memory/systemPatterns.md（项目级）需追加 ADR：[内容]
- memory/techContext.md（项目级）需更新：[内容]
- memory/{version}/{user}/progress.md 需更新：[哪些功能状态变化]

## 待处理 Bugfix

- [ ] bugfix-YYYYMMDD-{user}.md — [问题标题] — 状态：待修复/已修复/已验证
      （文件位于 `docs/bugfix/{version}/`）
```

---

## 7. memory/{version}/{user}/progress.md

**路径**：`memory/{version}/{user}/progress.md`（按版本 + git 用户隔离）

**用途**：该版本该用户视角下的进度仪表盘。同版本多人协作时，每人维护各自的 progress，项目整体视图由 `/health-check` 聚合生成。

**更新频率**：每个 Sprint 关闭时由 `/sprint-close` 更新。

### progress 完整模板

```markdown
# 进度快照（{version} / {user}）

> L3 迭代记忆，路径 `memory/{version}/{user}/progress.md`。
> 每个 Sprint 关闭时由 /sprint-close 更新。
> 最后更新：YYYY-MM-DD

## 总体完成度

- 整体进度（我负责部分）：XX%（P0功能 X/Y 完成）
- 当前阶段：[MVP 开发中 / 正式版开发中 / ...]
- 预计下一里程碑：YYYY-MM-DD

## 我负责的功能模块完成状态

| 功能模块 | 优先级 | 状态 | 完成 Sprint | 备注 |
|---------|--------|------|------------|------|
| [模块1] | P0 | ✅ 完成 / 🚧 开发中 / ⏳ 未开始 | Sprint-NNN | |

## Sprint 历史（本用户在本版本的 Sprint）

| Sprint | 目标 | 状态 | 完成时间 | 主要产出 |
|--------|------|------|---------|---------|
| Sprint-001 | [目标] | ✅ 完成 | YYYY-MM-DD | [产出] |

## 版本历史（项目级参考）

> 以下为项目所有版本一览，由 /version 命令维护。
> 此区域跨用户共享，任何用户的 progress.md 中保持同步。

| 版本 | 发布日期 | 里程碑 | 包含 Sprint | 状态 | Git 标签 |
|------|---------|--------|------------|------|---------|
| V0.0.1 | - | M0 初始化 | - | 🚧 开发中 | - |

## 累计技术债务

- [ ] [描述] — Sprint-NNN 遗留 — 计划 Sprint-NNN 处理

## 累计 Bugfix 统计

| Sprint | 提出数 | 已修复 | 待修复 |
|--------|--------|--------|--------|
| Sprint-001 | N | N | N |

## 下一个里程碑

- **目标**：[里程碑描述]
- **预计时间**：YYYY-MM-DD
- **所需 Sprint**：Sprint-NNN ~ Sprint-NNN
```

---

## 8. memory/{version}/{user}/sprints/sprint-NNN.md


**路径**：`memory/{version}/{user}/sprints/sprint-{NNN}.md`（按版本 + 用户隔离）

**用途**：每个 Sprint 完成后的完整历史快照，永不修改。

**更新频率**：仅在 `/sprint-close` 时由 PM Agent 创建，创建后禁止修改。

**内容**：Sprint 关闭时的 `memory/{version}/{user}/activeContext.md` 完整副本 + 验收结果摘要。

```markdown
# Sprint-NNN 历史记录（已归档）

> 归档时间：YYYY-MM-DD HH:MM
> ⚠️ 此文件为只读历史记录，禁止修改

---

{activeContext.md 的完整内容}

---

## 验收摘要

| 功能 | 状态 | 备注 |
|------|------|------|
| [功能1] | ✅ 通过 | |
| [功能2] | ⚠️ 部分通过 | [说明] |
```

---

## 9. AGENTS.md（项目记忆文件）

**用途**：AI Agent 每次启动必读的主入口文件（Codex / DeepSeek Harness 读 `AGENTS.md`；Claude Code 读 `CLAUDE.md`，二者并存时 `CLAUDE.md` 仅引用 `AGENTS.md`）。

> ⚠️ **本章节不内嵌完整模板**：内嵌副本易落后于 `AGENTS.md` 实际权威版本。**模板请直接读取本仓库根目录的 `AGENTS.md` 实际文件**——它是权威单一信源；新建/升级项目时由 `aidp-code-engineer` SKILL 同步分发到下游项目。
>
> 详细内容（当前状态字段格式、Agent 激活路由、命令清单、核心约定 41 条、Skill 表等）见 `AGENTS.md` 本体。

---

## 10. memory/ 下的运行时状态文件

`memory/` 除上述 Markdown 记忆文件外，还承载若干**命令运行时状态**（点号开头的 JSON）。它们**不是"记忆"、不供人工编辑**，由对应命令/脚本首次用到时才创建。**清单与字段说明的单一信源 = `memory/README.md`**「运行时状态文件」段，本节只声明其存在与最关键的一条纪律，避免两处双写。

> **运行时状态文件的清单、字段、是否入库一律看 `memory/README.md`**；本节只留下面的并发写铁律。

> ⛔ **并发写铁律**：`.sprint-autopilot-baseline.json` 被**两条链路并发读写**（开发链路 10m tick + 测试链路 5m tick）。**任何写入必须经 `python3 .aidp/scripts/baseline_edit.py`**（`flock` 加锁 + 锁内重读 + 原子替换）——**严禁**直接 `Write` / `jq > file` / 手工编辑该 JSON。裸写只保证"文件不半截"，**不保证"不丢对方刚写的字段"**：长 tick 交叉时会把对方落的 `last_deployed_at` / 各 streak 整体抹掉，表现为门判据错乱、熔断永不达阈。读取可直接读。
