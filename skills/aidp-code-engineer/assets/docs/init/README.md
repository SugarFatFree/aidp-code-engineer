# AIDP 使用指南

> AI-Driven Iterative Development Paradigm（AI 驱动的迭代开发范式）

## 📖 什么是 AIDP？

AIDP 是一套由 **AI 编码 Agent（Claude Code / Codex / DeepSeek Harness）+ Agent Team + Skills 生态** 驱动的结构化迭代开发范式，将传统软件工程的标准流程（需求 → 设计 → 开发 → 测试 → 上线）与 AI 能力结合，通过**结构化文档驱动** + **AI 记忆系统**实现：

- ✅ 每次迭代有完整的输入/输出文档
- ✅ AI Agent 在每次启动时能读取项目全貌，不丢失上下文
- ✅ 多人可并行工作，不互相干扰
- ✅ 项目历史完整可追溯
- ✅ 一条命令从需求到代码再到测试全部自动化

## 🚀 快速开始

### 1. 项目初始化

如果是新项目，让 AI Agent 调用 `aidp-code-engineer` 脚手架技能初始化（init 模式，目标版本 V0.1.0）。

如果是已有项目，调用该技能的 migrate 模式接入。

> ℹ️ `aidp-code-engineer` 是可由用户调用的 **SKILL**，而非 `{{AIDP_HOME}}/commands/` 下的 AIDP 命令：Claude Code 可输入 `/aidp-code-engineer init`，Codex 可输入 `$aidp-code-engineer init`，也可用自然语言触发。初始化与改建支持无 Git 项目，不自动 `git init`；非 Git 可规划、开发和本地测试/归档，但不可提交、推送、打 tag 或宣称正式发布成功。

### 2. 首次版本规划

```bash
/version V0.1.0 "MVP 版本"
# 内部自动串联：
# - /sprint-requirements  生成需求文档
# - /sprint-design        生成详细设计
# - /sprint-plan          生成研发执行计划
# - /sprint-selftest      生成研发自测（方案+用例+测试环境）
```

### 3. 执行开发

```bash
# ★ 推荐：一条命令批量跑完所有 Sprint
/sprint-batch

# 或按场景选择：
/sprint-dev "新增用户导出功能"         # 新增功能（自动累进 Sprint）
/sprint-bugfix                         # 修复已记录的 bug
/sprint-full 001                       # 按计划跑单个 Sprint
```

### 4. 发布版本

```bash
/version V0.1.0                        # 所有 Sprint 完成后打 tag
```

## 📁 目录结构说明

AIDP 项目的标准目录结构：

```
project/
├── {{AIDP_HOME}}/              # ★ 运行真源：仅 Claude 为 .claude；有 Codex / DSH 为 .agents（契约平铺其下）
│   ├── agents/                 # Agent 定义（PM/架构师/前端/后端/QA/审查员/UI/AIDP-Compliance/Version-Auditor，共 9 个）
│   ├── commands/               # 命令定义（/version /sprint-* 等）
│   ├── skills/                 # 公共技能定义
│   ├── plugins/                # 项目级插件真源（含 chrome-devtools-mcp）
│   ├── rules/                  # 路径限定规则（frontmatter `paths:` 匹配才加载）：代码向约定详规
│   ├── flows/                  # 长命令 Phase 分片（命令本体留骨架，Phase 正文按需 Read）
│   ├── reference/              # 按需 Read 的查阅分片（命令速查 / skills 用途 / 约定细则 / 文档索引）
│   ├── scripts/                # 确定性校验与判定脚本
│   ├── hooks/                  # 钩子脚本（autopilot Stop 护栏）
│   ├── templates/deployment/   # 部署流程 + SQL执行台账 模板
│   ├── templates/reports/      # AI 全自动报告模板
│   └── templates/optional-rules/  # ★ 按需安装的可选规则（如 WebMCP；未启用不装进 rules/）
├── code/                       # 源代码
│   ├── frontend/               # 前端代码
│   └── backend/                # 后端代码
├── docs/                       # 文档体系
│   ├── init/                   # 初始化文档（本 README 所在目录，含 00~06）
│   ├── architecture/           # 架构文档（架构约束三件套 + 可选架构设计）
│   ├── references/             # 第三方接口文档（根=跨版本通用；{version}/=本版对外需求）
│   ├── requirements/{version}/ # 需求文档（PRD/FSD）
│   ├── design/detail/{version}/# 详细设计
│   ├── design/detail/全量/     # ★ 跨版本全量详细设计（非版本目录，正式发布时生成）
│   ├── testing/{version}/      # 测试文档
│   ├── deployment/{version}/   # 部署文档
│   ├── plans/{version}/        # 研发执行计划（01_研发执行计划.md）
│   ├── reports/{version}/      # 项目报告（AI执行/AI测试/版本测试 + 走查/交付）
│   ├── audit/合规检查-{YYYYMMDD}.md  # 范式合规检查报告（★ 根级，与 {version}/ 并列）
│   ├── audit/{version}/        # 版本规划产物审计报告
│   ├── prompts/{version}/      # Prompt 记录
│   ├── prototype/{version}/    # 原型文件
│   ├── bugfix/{version}/       # Bug 修复记录
│   └── implementation/{version}/{user}/ # 个人实施记录
├── memory/                     # AI 记忆系统
│   ├── projectBrief.md         # 项目简介
│   ├── productContext.md       # 产品背景
│   ├── systemPatterns.md       # 系统模式
│   ├── techContext.md          # 技术上下文
│   ├── databaseBaseline.md     # 数据库基线
│   ├── aidp-config.yaml        # 项目配置（提交前门禁 / 通知 / CICD 等开关）
│   └── {version}/{user}/       # 版本级用户记忆
│       ├── activeContext.md    # 当前活跃上下文
│       ├── progress.md         # 进度跟踪
│       └── sprints/            # Sprint 记录
├── env/                        # 环境配置
├── .github/                    # CICD 流水线定义（默认 GitHub Actions；其他平台按其约定）
├── AGENTS.md                   # 项目记忆文件（Claude Code 下为 CLAUDE.md）
└── README.md                   # 项目说明
```

## 🎯 核心命令

### 版本管理

| 命令 | 说明 |
|------|------|
| `/version {version} "{desc}"` | 创建新版本（自动串联需求/设计/计划） |
| `/version {version}` | 发布版本（打 tag） |

### Sprint 执行

| 命令 | 说明 |
|------|------|
| `/sprint-init` | 项目初始化 |
| `/sprint-plan` | 生成研发执行计划 |
| `/sprint-batch` | 批量执行所有 Sprint |
| `/sprint-full {NNN}` | 执行单个 Sprint（完整流程） |
| `/sprint-dev "{desc}"` | 开发新功能（自动累进） |
| `/sprint-bugfix` | 修复 bug |
| `/sprint-test` | 执行测试 |
| `/sprint-close {NNN}` | 关闭 Sprint |
| `/sprint-autopilot` | ★ 7×24 全自动开发编排器（操作系统调度 `aidp_scheduler.py` 守护） |
| `/sprint-aiauto-test` | ★ chrome 浏览器仿真测试（操作系统调度 `aidp_scheduler.py` 守护） |

### 其他

| 命令 | 说明 |
|------|------|
| `/health-check` | 项目健康度检查 |
| `/memory-sync` | 记忆同步 |

## 📝 文档规范

### 需求文档（产品 PRD + 研发需求）

- 产品 PRD（用户输入）：`docs/requirements/{version}/产品提供/*.md`
- 研发需求（生成）：`docs/requirements/{version}/研发需求/` **恒有专职索引 `00_索引.md` + 内容主文档从 `01_` 起**（含单文件态、无例外，约定 15）——单系统 = `00_索引.md` + `01_研发需求.md`；多系统拆分 = `00_索引.md` + `01_<系统>.md` / `02_<系统>.md`。裸中文名（如 `研发需求.md`）属 `version-auditor` A-06b **Critical**
- 生成：`/sprint-requirements` 或 `/version` 自动生成（约定 14 中文文件名）

### 设计文档

- 位置：`docs/design/detail/{version}/`
- 命名（现行·索引态，约定 14/15：单份也走索引态）：`00_索引.md`（专职索引）+ `01_详细设计.md` / `02_数据库设计.md` / `03_接口设计.md` / `04_对外开放接口.md`（条件触发）/ `05_集成对接.md`（条件触发）+ `*事实清单.md`。裸名 `详细设计.md`/`接口设计.md`/`数据库设计.md` 仅**历史存量兼容识别**，新生成不再产出
- 命名（多专题拆分示例）：`00_索引.md` + `01_详细设计.md` / `02_数据库设计.md` / `03_接口设计.md` / …（两位数字前缀 + 中文专题名；`99_待澄清问题清单.md` 序号保留给末位）
- 生成：`/sprint-design` 或 `/version` 自动生成（详见项目记忆文件（AGENTS.md / CLAUDE.md）约定 15「同类多文件编号」）

### 测试文档

- 位置：`docs/testing/{version}/` 下 3 子目录 —— `研发自测/`（AIDP 生成，经 /sprint-selftest）、`正式用例/`（测试人员手动上传）、`sprint-{NNN}/`（QA 按 Sprint）；AI 测试报告落 `docs/reports/{version}/AI测试报告/`
- 生成：`/sprint-selftest`（研发自测）+ `/sprint-test`（sprint 报告）+ `/sprint-aiauto-test`（AI 测试）

### 研发执行计划

- 位置：`docs/plans/{version}/01_研发执行计划.md`
- 生成：`/sprint-plan` 或 `/version` 自动生成

## 🔄 工作流程

### 标准迭代流程

```
1. 版本规划
   /version V0.1.0 "MVP"
   ↓
2. 批量执行 Sprint
   /sprint-batch
   ↓
3. 发布版本
   /version V0.1.0
```

### 单个 Sprint 流程

```
1. 启动 Sprint
   /sprint-start {NNN}
   ↓
2. 开发实现
   /sprint-dev "功能描述"
   ↓
3. 测试验收
   /sprint-test
   ↓
4. 修复问题
   /sprint-bugfix
   ↓
5. 关闭 Sprint
   /sprint-close {NNN}
```

> ⚠️ **详细设计不在这里**：它在 `/version` 版本规划期一次性生成，Sprint 执行期**只读取、不重新生成**（约定 1）。

## 🛠️ 最佳实践

### 1. 版本命名

- 使用语义化版本：`V{major}.{minor}.{patch}`
- 示例：`V0.1.0`、`V1.0.0`、`V1.1.2`

### 2. Sprint 粒度

- 每个 Sprint 2-3 周
- 每个 Sprint 包含 3-5 个 **Task**（⚠️ AIDP 无「User Story」层；模型是 **EPIC × Sprint × Task 三层**，单一信源 = `dev-execution-planner` SKILL）

### 3. 文档维护

- 需求文档：产品经理维护
- 设计文档：架构师/开发维护
- 测试文档：QA 维护

### 4. 记忆系统

- `memory/` 下的文件是 AI Agent 的长期记忆
- 项目级文件（projectBrief.md 等）：项目初始化时填充，后续按需更新
- 版本级文件（activeContext.md 等）：每个版本独立维护

### 5. 代码提交

- 遵循 Conventional Commits 规范
- 每个 Sprint 在独立分支开发
- Sprint 完成后合并到主分支

## 🔍 常见问题

### Q: 如何在已有项目中使用 AIDP？

A: 调用 `aidp-code-engineer` 脚手架技能的 migrate 模式（SKILL，非斜杠命令）。

SKILL 会：
- 保留已有代码和文档
- 补充 AIDP 目录骨架
- 安装 `{{AIDP_HOME}}/` 运行契约并生成当前 Agent 的适配层
- 不覆盖已有文件

### Q: 如何升级旧版 AIDP？

A: 调用 `aidp-code-engineer` 脚手架技能的 upgrade 模式（SKILL，非斜杠命令）。

SKILL 会自动检测旧版本并升级到目标范式版本。

## 📚 深入学习

### 理论层文档

AIDP 范式提供了完整的理论层文档（位于 `docs/init/`），包含范式骨架、规则、模板和索引：

| 文档 | 定位 | 内容 | 何时阅读 |
|------|------|------|---------|
| [`00_AIDP范式主文档.md`](00_AIDP范式主文档.md) | 范式骨架 | 目录结构、流程总览、初始化决策树、三种典型场景 | **必读**，入门第一篇 |
| [`01_初始化输入指导.md`](01_初始化输入指导.md) | 输入指导 | 项目初始化时需要提供的输入详细说明 | 执行 `/sprint-init` 前 |
| [`02_迭代输入指导.md`](02_迭代输入指导.md) | 输入指导 | 各阶段迭代输入清单和提示词示例 | 执行 `/sprint-*` 前 |
| [`03_memory文件详细规范.md`](03_memory文件详细规范.md) | 文件模板 | Memory Bank 各文件的完整模板 | 初始化或手工编辑 memory 文件时 |
| [`04_agents详细规范.md`](04_agents详细规范.md) | 索引总览 | Agent 职责边界、协作流程、激活规则 | 理解 Agent 分工或激活方式 |
| [`05_commands详细规范.md`](05_commands详细规范.md) | 索引总览 | 命令体系分层、四种执行模式 | 理解命令层次或查找命令 |
| [`06_版本与用户目录约定.md`](06_版本与用户目录约定.md) | **权威来源** | 版本+用户目录层级的权威规则 | 任何涉及路径的场景（最高优先级） |

### 阅读顺序建议

**首次接触 AIDP**：`00 → 06 → 01 → 02`

**准备开始开发**：`00 第 5-6 节（决策树）→ AGENTS.md`

**理解 Agent 分工**：`04 → {{AIDP_HOME}}/agents/*.md`

**查找具体命令**：`05 → {{AIDP_HOME}}/commands/*.md`

**修改 memory 文件**：`03 → memory/README.md`

### 理论层与实现层的关系

```
理论层（docs/init/）
├── 00-03, 06 → 提供规则、模板、流程
└── 04-05    → 作为索引指向 .aidp/ 下的实现

实现层（下游 {{AIDP_HOME}}/；模板仓库 .aidp/ 只作维护源）
├── agents/     → 9 个 Agent 指令（7 业务 + 1 合规 + 1 版本审计，运行时读取）
├── commands/   → 19 个命令定义（/xxx 触发读取，含 /version /sprint-* /sprint-autopilot /sprint-aiauto-test 等）
├── skills/     → 7 个 skill（生成/执行类：研发需求、详细设计、执行计划、自测用例、自动化测试执行、代码验证、缺陷修复，被命令内部调用）
│                 ⛔ 脚手架 `aidp-code-engineer` 不在此列：它与公共 SKILL 同住本目录，但被排除出运行包受管清单（它是安装器、不是下发契约）
├── rules/      → 路径限定规则（`paths:` glob 匹配到才加载）：代码向核心约定详规
├── flows/      → 长命令的 Phase 分片（命令本体留骨架，Phase 正文按需 Read）
├── reference/  → 按需 Read 的查阅分片（命令速查 / skills 用途 / 约定细则 / 初始化与文档索引）
├── templates/  → deployment（部署流程+SQL执行台账）/ reports（AI 报告）/ optional-rules（按需安装的可选规则）
│                + `_开发期族增量.md` 四族共用模板
├── scripts/    → 确定性校验与判定脚本
└── hooks/      → 钩子脚本
```

**核心原则**：理论层不重复实现层内容，两者互为索引。

### 文档体系导航（docs/ 各子目录职责）

`docs/` 各子目录的**隔离级别、职责与写入者速查** 见 [`../README.md`](../README.md)（`docs/` 目录说明）——含"项目级 / 版本级 / 版本+用户级"三层划分、各子目录写入者、文件命名规范，以及 `deployment/tools/`（**非版本隔离**特例）等易放错的路径。路径的**权威定义**仍以本目录 [`06_版本与用户目录约定.md`](06_版本与用户目录约定.md) 为准。

---

*AIDP | 由 aidp-code-engineer SKILL 维护*
