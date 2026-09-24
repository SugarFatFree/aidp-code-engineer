# AIDP — AI 驱动迭代开发范式

**AI-Driven Iterative Development Paradigm for AI Coding Agent Team**

> 适用场景：中大型 Web 项目 | 支持：多版本并行 + 多人协作 + Agent Team 模式 | 兼容 Claude Code / Codex / DeepSeek Harness
>
> 📌 本文只描述当前生效的范式结构与流程，不记录逐版变更（约定 30）。
>
> 完整目录规则见 `06_版本与用户目录约定.md`（单一权威来源）。本文中模板仓库 `.aidp/` 仅作维护源；下游运行契约用 `{{AIDP_HOME}}/` 表示（仅 Claude 为 `.claude/`，有 Codex / DSH 时为 `.agents/`；十个契约目录平铺其下、不再套中间层），下游项目根不创建 `.aidp/`。无 Git 可规划、开发、本地测试与归档，但提交、推送、tag、CICD 和正式发布不可用，不自动 `git init`。

---

## 目录

- [1. 范式概述](#1-范式概述)
- [2. 完整项目目录结构](#2-完整项目目录结构)
- [3. AI 记忆系统（Memory Bank）](#3-ai-记忆系统memory-bank)
- [4. Agent 角色分工](#4-agent-角色分工)
- [5. 项目初始化流程](#5-项目初始化流程)
- [6. 迭代开发流程（Sprint Cycle）](#6-迭代开发流程sprint-cycle)
- [7. 问题修复流程（Bugfix Cycle）](#7-问题修复流程bugfix-cycle)
- [8. 多人协作规范](#8-多人协作规范)
- [9. 防混乱机制](#9-防混乱机制)
- [10. Skills 扩展体系](#10-skills-扩展体系)
- [附录：快速参考卡](#附录快速参考卡)

---

## 1. 范式概述

### 1.1 核心理念

AIDP 将传统软件工程的标准流程（需求 → 设计 → 开发 → 测试 → 上线）与 AI 编码 Agent 的 Agent Team 模式相结合，通过**结构化文档驱动**和**AI 记忆系统**，确保：

- 每次迭代都有完整的输入/输出文档
- AI Agent 在每次启动时能读取项目全貌，不丢失上下文
- 多人可并行工作，不互相干扰
- 项目历史完整可追溯

### 1.2 核心原则

| 原则 | 说明 |
|------|------|
| **文档即代码** | 所有设计文档与代码同等重要，纳入版本管理 |
| **记忆持久化** | AI 的上下文通过结构化文件持久存储，而非依赖对话历史 |
| **单一事实源** | 每类信息只有一个权威来源文件，避免矛盾 |
| **迭代封闭性** | 每个 Sprint 必须有明确的输入、过程产物、输出和验收 |
| **阶段可独立** | 每个阶段（需求/设计/开发/测试/修复）可独立执行迭代 |
| **Agent 专职化** | 不同 Agent 承担不同角色，通过文档交接而非对话 |
| **跨迭代连续性** | 数据库表、公共组件等跨 Sprint 资产通过基线文件持续追踪，避免重复建设 |
| **组件复用优先** | 前端开发必须先识别和复用公共组件（布局、导航等），禁止跨页面重复实现 |

### 1.3 文档体系总览

| 文档 | 内容 |
|------|------|
| `00_AIDP范式主文档.md`（本文件） | 范式概述、目录结构、流程总览 |
| `01_初始化输入指导.md` | 项目初始化时需要提供的输入详细说明 |
| `02_迭代输入指导.md` | Sprint 迭代及各阶段独立迭代的输入说明 |
| `03_memory文件详细规范.md` | 各 Memory Bank 文件的详细说明与模板 |
| `04_agents详细规范.md` | 各 Agent 角色的详细指令内容与使用指南 |
| `05_commands详细规范.md` | 各自定义命令的详细定义与使用示例 |
| `06_版本与用户目录约定.md` | 版本 + git 用户双层目录层级的**单一权威来源**，所有其他文档遵循此规范 |

---

## 2. 完整项目目录结构

> 本节给出目录骨架总览。完整的路径规则、命名规范、路径解析算法见 `06_版本与用户目录约定.md`。
>
> `{version}` 示例 `V0.1.0`，来自 `git tag` 或 PM 指定；`{user}` 来自 `git config user.name`。

```
project-root/
│
├── AGENTS.md                             # ★ 项目记忆文件：会话流程 / 命令 / Agent 入口 / Skills / 核心约定（Claude Code 下为 CLAUDE.md）
├── README.md                             # 项目说明
│
├── {{AIDP_HOME}}/                        # ★ 下游运行真源：仅 Claude 为 .claude；有 Codex / DSH 为 .agents（契约平铺其下）
│   ├── agents/                           # 9 个 Agent 角色指令（7 业务 + 1 合规 + 1 版本审计）
│   ├── commands/                         # 自定义斜杠命令
│   │   ├── sprint-init.md                # /sprint-init            项目初始化
│   │   ├── sprint-init-design.md         # /sprint-init-design     初始化前半段（分步）
│   │   ├── sprint-init-complete.md       # /sprint-init-complete   初始化后半段（分步）
│   │   ├── version.md                    # /version                版本管理（规划/发布）
│   │   ├── sprint-requirements.md        # /sprint-requirements    生成需求（调用 ux-logic-extractor）
│   │   ├── sprint-design.md              # /sprint-design          生成设计（调用 dev-logic-architect）
│   │   ├── sprint-plan.md                # /sprint-plan            生成研发执行计划（调用 dev-execution-planner）
│   │   ├── sprint-selftest.md            # /sprint-selftest        生成研发自测方案+用例（调用 dev-manual-testcase）
│   │   ├── sprint-batch.md               # /sprint-batch           ★ 批量执行多 Sprint
│   │   ├── sprint-full.md                # /sprint-full            单 Sprint 一键
│   │   ├── sprint-start.md               # /sprint-start           启动 Sprint
│   │   ├── sprint-dev.md                 # /sprint-dev             开发阶段（TDD + 并行）
│   │   ├── sprint-test.md                # /sprint-test            测试阶段
│   │   ├── sprint-bugfix.md              # /sprint-bugfix          问题修复（独立可用）
│   │   ├── sprint-close.md               # /sprint-close           Sprint 关闭
│   │   ├── sprint-autopilot.md           # /sprint-autopilot       ★ 7×24 全自动开发编排器
│   │   ├── sprint-aiauto-test.md         # /sprint-aiauto-test     ★ AI 自动化测试（当前工具 chrome-devtools-mcp）
│   │   ├── memory-sync.md                # /memory-sync            记忆同步
│   │   └── health-check.md               # /health-check           健康检查
│   ├── skills/                           # 公共 Skills 扩展目录
│   ├── plugins/                          # 项目级插件真源（含 chrome-devtools-mcp）
│   ├── rules/                            # ★ 路径限定规则（frontmatter `paths:` 匹配才加载）：代码向约定详规
│   ├── flows/                            # ★ 长命令 Phase 分片（命令本体只留骨架，Phase 正文按需 Read）
│   ├── reference/                        # ★ 按需 Read 的查阅分片（命令速查 / skills 用途 / 约定细则 / 文档索引）
│   ├── scripts/                          # ★ 确定性校验与判定脚本（如 commit_gate.py、cicd_watch.py、notify.py）
│   ├── hooks/                            # ★ 钩子脚本（autopilot Stop 护栏）
│   ├── templates/deployment/             # ★ 部署流程 + SQL执行台账 模板（/sprint-dev Step X.8 复制填充）
│   ├── templates/reports/                # ★ AI 全自动报告模板（AI执行报告 + AI测试报告 + AI数据清理 + 版本测试报告 + README）
│   └── templates/optional-rules/         # ★ 按需安装的可选规则（如 WebMCP 详规；未启用即不装进 rules/）
│
├── .github/workflows/                    # CICD 流水线定义（默认 GitHub Actions；其他平台按其约定，约定 31）
│
├── docs/                                 # 文档体系
│   ├── init/                             # 项目级：AIDP 范式文档本体
│   │   ├── 00_AIDP范式主文档.md
│   │   ├── 01_初始化输入指导.md
│   │   ├── 02_迭代输入指导.md
│   │   ├── 03_memory文件详细规范.md
│   │   ├── 04_agents详细规范.md
│   │   ├── 05_commands详细规范.md
│   │   ├── 06_版本与用户目录约定.md     # 目录层级权威来源
│   │
│   ├── architecture/                     # 项目级：架构约束三件套 + 可选架构设计文档（单/多文档，兼容识别）
│   ├── references/                       # 项目级：第三方接口文档
│   ├── prototype/{version}/              # 版本级：原型资源
│   │   ├── code/                         # 原型代码（按模块）
│   │   └── mockup/                       # 高保真原型（按模块）
│   ├── deployment/{version}/             # 版本级：部署产物（发布/开发期维护）
│   │   ├── 00_索引.md                    # ★ 固定契约：部署产物清单 +「全新部署 / 升级 分别拿哪些」场景导航
│   │   ├── sql/                          # ⛔ 根下不直放 .sql，只允许 增量/ 与 全量/（约定 37 双轨，见 06 §2.5.4）
│   │   │   ├── 增量/                     # 【增量轨】本版 NN_中文名.sql + 99_回滚脚本.sql（上游暂存 code/sql/ → /sprint-design Step 3.2 搬迁至此）
│   │   │   └── 全量/                     # 【全量轨】发布期产出：00_索引.md + NN_建表-<业务域>.sql + NN_初始化数据.sql，不含任何 ALTER
│   │   ├── 部署流程/                     # 部署 SOP + SQL执行台账（精炼版，/sprint-dev Step X.8 检测驱动维护）
│   │   └── 配置文件/                     # ⛔ 根下不直放配置产物，只允许 增量/ 与 全量/
│   │       ├── 增量/                     # 【增量轨】配置项清单.md（/sprint-dev Step X.7 维护）
│   │       └── 全量/                     # 【全量轨】发布期产出：00_索引.md + 引导层环境文件 + nginx/compose/k8s 完整份 + <配置中心>/*.yml
│   ├── deployment/tools/               # ★ 跨版本：运维/一次性工具归档（非版本隔离；本应用/<上游系统>/其他 + README 索引，见 06 §2.5.4.1）
│   │
│   │── ★ 以下为「版本级」团队协作产物（需求/设计/测试/验收/计划/报告/Prompt） ──
│   │
│   ├── requirements/
│   │   ├── {version}/研发需求/00_索引.md        # ★ 恒有：专职索引（文件清单+每文件生成时间+主/补充标识，约定 15）
│   │   └── {version}/研发需求/01_研发需求.md   # 内容主文档（单系统；多系统拆 01_<系统>.md/02_<系统>.md）
│   ├── design/
│   │   ├── detail/{version}/                  # 版本增量详细设计（完全自由 + 仅约定命名）
│   │   │   ├── 00_索引.md                     # ★ 恒有：专职索引，列全分册+阅读顺序+每文件生成时间+主/补充标识（约定 15）
│   │   │   ├── 01_详细设计.md                 # 推荐：必出（模块结构 + 技术栈 + 公共组件）
│   │   │   ├── 02_数据库设计.md               # 推荐：有数据库时
│   │   │   ├── 03_接口设计.md                 # 推荐：有 API 时
│   │   │   ├── 04_对外开放接口.md / 05_集成对接.md / 06_测试方案.md / 07_安全设计.md / ... # 按需专题（序号权威 = /sprint-design；研发自测方案现归 docs/testing/{version}/研发自测/）
│   │   │   └── 98_事实清单.md                 # 代码事实基线（如 code/ 已存在）；99_待澄清问题清单.md（如有）。历史存量并列态裸名仍识别放行、新生成不采用
│   │   └── detail/全量/                        # ★ 跨版本全量详细设计（非版本目录）：/version 正式发布 Step 3.3.11 生成
│   │       ├── 00_索引.md                     # 仅目录内导航；整合"最新代码+全量需求+各版本详设"、自包含不引用外部文件
│   │       └── 01_详细设计.md / 02_数据库设计.md / ... / 98_事实清单.md  # 覆盖式只留最新、无历史；规划期不动
│   ├── testing/{version}/                        # ★ 下设并列子目录
│   │   ├── 研发自测/                              #   00_索引.md + 01_研发自测方案.md + 用例02_起 + 01_测试环境与账号.md（dev-manual-testcase SKILL，经 /sprint-selftest；配置入此）
│   │   ├── 正式用例/                              #   ★ 测试人员手动方案/用例（AIDP 不写入）
│   │   └── sprint-{NNN}/                          #   按 Sprint 测试用例与报告（QA 维护，与上述互补）
│   ├── plans/{version}/
│   │   ├── 00_索引.md                            # ★ 恒有：专职索引（文件清单+每文件生成时间+主/补充标识，约定 15）
│   │   ├── 01_研发执行计划.md                        # 内容主文档（必需）
│   │   └── plan-{user}.md                        # 个人任务细化（可选）
│   ├── reports/{version}/                        # AI执行报告（/sprint-autopilot）+ AI测试报告 + 版本测试报告（HTML）+ 走查/交付报告
│   ├── audit/{version}/                          # ★ 版本规划产物审计（version-auditor，/version Step 2.4.7）+ 合规检查（AIDP-Compliance）
│   ├── prompts/{version}/                        # 大型 Prompt 存档
│   │
│   │── ★ 以下为「版本+用户」双层隔离（仅 bugfix/implementation/memory 3 类）──
│   │
│   ├── bugfix/{version}/                         # bug 记录（文件名：bugfix-{YYYYMMDD}-{user}.md）
│   └── implementation/{version}/{user}/          # 实施过程记录、踩坑笔记
│
├── code/                                 # 代码目录（统一为 frontend/+backend/ 二分）
│   ├── frontend/                         # ★ 前端代码父目录（必含；单/多项目都套这层）
│   │   └── {子项目名}/                   # 单前端时一个；多前端时并列多个（如 web-admin / web-portal）
│   └── backend/                          # ★ 后端代码父目录（必含；单/多项目都套这层）
│       └── {子项目名}/                   # 单后端时一个；多后端时并列多个（如 gateway / biz-service）
│                                            （SQL 不在 code/：本版本 SQL 归 docs/deployment/{version}/sql/增量/，见 06 §2.5.4）
│
├── env/                                  # 环境信息
│   └── .env
│
├── memory/                               # ★ AI 记忆系统（Memory Bank）
│   ├── aidp-config.yaml                  # 项目配置（提交前门禁 / 里程碑通知 / CICD / Stop 护栏，人维护）
│   │
│   │── ★ 项目级（单一真源，不隔离） ────────────────────────────────
│   ├── projectBrief.md                   # L1 项目简介
│   ├── productContext.md                 # L1 产品上下文
│   ├── systemPatterns.md                 # L2 架构决策 ADR（跨版本累积）
│   ├── techContext.md                    # L2 技术上下文
│   ├── databaseBaseline.md               # L2 数据库基线（跨版本累积）
│   │
│   │── ★ 迭代级（按版本+用户隔离） ────────────────────────────────
│   └── {version}/{user}/
│       ├── activeContext.md              # L3 当前 Sprint 实时状态
│       ├── progress.md                   # L3 该版本该用户视角的进度
│       └── sprints/                      # L4 已归档历史（只追加）
│           └── sprint-{NNN}.md
│
```

### 2.1 目录隔离级别速查

| 级别 | 隔离维度 | 典型路径 | 说明 |
|------|---------|---------|------|
| 项目级 | 不隔离 | `docs/init/`、`memory/projectBrief.md`、`memory/systemPatterns.md` | 全项目唯一 |
| 版本级 | 按版本 | `docs/requirements/{version}/`、`docs/plans/{version}/`、`docs/prototype/{version}/mockup/` | 同版本团队共享 |
| 版本+用户级 | 双层 | `docs/bugfix/{version}/`（文件名带 user）、`docs/implementation/{version}/{user}/`、`memory/{version}/{user}/` | 仅 3 类（详见 06 §2.3）：bugfix 为版本级目录、按发现人命名文件 `bugfix-{YYYYMMDD}-{user}.md`；implementation / memory 为每人独立子目录 |

### 2.2 目录职责说明

| 目录 | 用途 | 初始化时机 |
|------|------|-----------|
| `docs/init/` | AIDP 范式文档本体，不随项目迭代修改 | 范式创建时 |
| `docs/requirements/{version}/` | 版本需求文档（整个版本的需求） | /version |
| `docs/design/detail/{version}/` | 版本详细设计、API、DB 设计（整个版本） | /version |
| `docs/testing/{version}/` | 研发自测/（用例+方案+`01_测试环境与账号.md`）、正式用例/（测试人员方案/用例，AIDP 只读）、sprint-{NNN}/（按 Sprint）；AI 测试报告落 docs/reports/{version}/AI测试报告/ | /sprint-selftest（研发自测/，`dev-manual-testcase` 唯一信源入口）· /sprint-test（sprint-{NNN}/）· /sprint-aiauto-test |
| `docs/plans/{version}/` | 研发执行计划（01_研发执行计划.md + plan-{user}.md） | /version |
| `docs/reports/{version}/` | AI执行报告（autopilot 流水线）、测试报告（AI测试报告 + 版本测试报告 HTML）、走查/交付报告 | /sprint-autopilot · /sprint-aiauto-test · /version |
| `docs/audit/{version}/` | 版本规划产物全量审计报告（version-auditor）；范式合规检查报告 `docs/audit/合规检查-*.md`（aidp-compliance） | /version Step 2.4.7 · aidp-compliance |
| `docs/prototype/{version}/mockup/` | ★ 高保真原型（人工图片或 AI 生成），前端视觉样式最高优先级参考 | /version 或 人工提供 |
| `docs/prototype/{version}/code/` | 原型代码（vibe coding 产物），功能和交互逻辑的参考 | 项目初始化前由人提供 |
| `docs/architecture/` | 架构约束三件套 + 可选架构设计文档（单/多文档，兼容识别） | 项目初始化前由人提供 |
| `docs/bugfix/{version}/` | 测试或使用中发现的问题记录（版本级单层，发现人在文件名） | 迭代过程中由该用户记录 |
| `docs/implementation/{version}/{user}/` | 个人实施过程记录、踩坑笔记 | 迭代过程中 |
| `docs/deployment/{version}/` | 部署产物：双轨 SQL（增量/全量）+ 配置文件 + 部署流程 + checklist（约定 37）；**`docs/deployment/tools/` 跨版本、不按版本隔离** | `/sprint-dev` X.7/X.8 · `/version` 3.3.7 |
| `docs/references/{version}/` | 提给第三方的对外需求 / 接口对接资料（版本专属；另有跨版本「通用区」）| `/sprint-design` · `/version` 3.3.9 |
| `docs/prompts/{version}/` | 本版沉淀的提示词模板（供复用，不参与发布收敛）| 人工 / 各命令按需 |

---

## 3. AI 记忆系统（Memory Bank）

> 解决 AI 编码 Agent 无跨会话记忆的问题。
>
> **隔离策略**：迭代级（L3/L4）记忆按 `{version}/{user}/` 隔离，项目级（L1/L2）保持单一真源。

### 3.1 记忆层级架构

```
┌──────────────────────────────────────────────────────────────────────┐
│                      Memory Bank                                     │
│                                                                      │
│  L1 永久记忆（项目级，项目全生命周期不变）                              │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  memory/projectBrief.md      memory/productContext.md         │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  L2 架构记忆（项目级，重大技术决策时追加，跨版本累积）                  │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  memory/systemPatterns.md     memory/techContext.md           │   │
│  │  memory/databaseBaseline.md ★（累积数据库基线）                │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  L3 迭代记忆（按 {version}/{user} 隔离，Sprint 开始/关闭时更新）       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  memory/{version}/{user}/activeContext.md ★                   │   │
│  │  memory/{version}/{user}/progress.md                          │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  L4 历史记忆（按 {version}/{user} 隔离，只追加）                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  memory/{version}/{user}/sprints/sprint-{NNN}.md              │   │
│  └──────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

> **为什么 L1/L2 不隔离**：ADR、数据库基线是跨版本跨人共用的"项目真相"，必须只有一份。
> **为什么 L3/L4 要隔离**：不同开发者、不同版本可能同时进行，隔离后才能并发且互不覆盖。

### 3.2 会话启动时的读取顺序

```
先解析上下文（由命令/项目记忆文件触发）：
  · git config user.name                 → 当前 {user}
  · AGENTS.md（Claude Code 下为 CLAUDE.md）的"当前状态"区域 → 当前 {version}
  · 读不到时询问用户（话术见 06_版本与用户目录约定.md 第 6 节）

必读（每次都要）：
  1. AGENTS.md                             → 项目概况和当前状态
  2. memory/{version}/{user}/activeContext.md      → 当前 Sprint 状态
  3. memory/{version}/{user}/progress.md           → 该版本该用户的进度

按需读取（根据任务类型）：
  4. memory/systemPatterns.md     → 做技术决策前必读（项目级）
  5. memory/techContext.md        → 搭建/修改开发环境前必读（项目级）
  6. memory/databaseBaseline.md   → ★ 做数据库设计前必读（项目级，防重复建表）
  7. memory/productContext.md     → 做需求分析前必读（项目级）
  8. memory/projectBrief.md       → 了解项目背景时读取（项目级）

初始化输入（按需）：
  9.  docs/architecture/           → 架构约束三件套 + 可选架构设计文档（单/多文档，全目录识别）
  10. docs/prototype/{version}/mockup/           → ★ 高保真原型（视觉样式最高优先级）
  11. docs/prototype/{version}/code/                       → 原型代码（功能+交互参考）
  12. env/.env                            → 环境配置信息

查阅历史：
  13. memory/{version}/{user}/sprints/sprint-{NNN}.md  → 某个 Sprint 的历史决策
```

各文件的详细模板见 `03_memory文件详细规范.md`。

---

## 4. Agent 角色分工

### 4.1 Agent 职责矩阵

| Agent | 职责 | 主要输入 | 主要输出 | 指令文件 |
|-------|------|---------|---------|---------|
| PM Agent | 需求分析、需求拆分（EPIC/Task）、验收结论 | PRD、业务需求 | Sprint 需求文档、验收结论（并入 AI执行报告/progress） | `{{AIDP_HOME}}/agents/pm.md` |
| Architect Agent | 系统设计、技术决策、ADR、详细设计 | PRD、架构约束、技术栈 | 详细设计文档、API 设计、DB 设计 | `{{AIDP_HOME}}/agents/architect.md` |
| UI Agent | 界面规范、原型分析、设计映射 | PRD、UI 原型代码、UI 规范约束 | UI 规范文档、组件映射清单 | `{{AIDP_HOME}}/agents/ui.md` |
| Frontend Agent | 前端代码实现 | 详细设计、UI 规范、原型代码、前端脚手架 | 前端页面代码 | `{{AIDP_HOME}}/agents/frontend.md` |
| Backend Agent | 后端代码实现、API、数据库 | API 设计、DB 设计、后端脚手架 | 后端接口代码 | `{{AIDP_HOME}}/agents/backend.md` |
| QA Agent | 测试用例设计与执行、问题修复验证 | 研发需求、验收标准、bugfix 记录 | 测试用例、测试报告 | `{{AIDP_HOME}}/agents/qa.md` |
| Reviewer Agent | 代码审查、质量把关 | PR 代码、设计文档 | 审查意见、合并决策 | `{{AIDP_HOME}}/agents/reviewer.md` |
| **AIDP-Compliance Agent** ★ | 范式合规检查（包住 verify.py 全部脚本 + 4 个语义维度：模板残留 / 事实清单 ↔ 代码 / 引用三角 / 目标 ↔ 实现背离〔仅当仓库根有 `设计目标.md` 时启用，无则 INFO 跳过〕） | verify.py 输出、memory/、项目记忆文件、code/、事实清单 | 合规报告（终端 + 必要时 `docs/audit/合规检查-{YYYYMMDD}.md`） | `{{AIDP_HOME}}/agents/aidp-compliance.md` |
| **Version-Auditor Agent** ★ | 版本规划产物全量审计（A 存在性 / B 边界 / C 覆盖完整性 / D 增量一致性 / E 引用链 / F 原型覆盖度（Critical 硬门）/ G 语义变更派生完整性（约定 22 第三类，Critical 硬门）/ H 跨版本需求作废完整性（约定 34） 共 8 项）| 版本规划产物（requirements / design / plans / testing 等）| 审计报告 `docs/audit/{version}/version-output-audit-*.md` | `{{AIDP_HOME}}/agents/version-auditor.md` |

共 **7 业务 Agent + 1 合规 Agent + 1 版本规划产物审计 Agent = 9 个 Agent**。各 Agent 的详细指令内容见 `04_agents详细规范.md`。

### 4.2 主入口 `AGENTS.md` 结构

项目记忆文件（AGENTS.md / CLAUDE.md）是 AI Agent 每次启动时的第一个读取文件，包含：

- 项目一句话描述
- 当前 Sprint 状态（由 /memory-sync 自动更新）
- Agent 激活路由表
- 可用命令列表
- 核心约定
- 初始化输入文件清单

---

## 5. 项目初始化流程

> **初始化分两步**：先 `/sprint-init` 建骨架，再 `/version` 做版本规划。
> 但实际场景很多样（可能克隆自老项目、可能已有 PRD、可能已有部分 memory），**本节给出决策树帮你确定从哪一步开始**。

### 5.1 初始化决策树

执行以下检查，对号入座决定从哪一步开始：

```
开始
  │
  ├─ 检查 1：memory/ 目录是否存在且有内容？
  │    ├─ 否 → 从 Step 1 开始（全新项目）
  │    └─ 是 → 进入检查 2
  │
  ├─ 检查 2：AGENTS.md 是否存在？
  │    ├─ 否 → 先重跑脚手架（`scaffold.py` 从模板 create-if-missing 渲染出本体），
  │    │        再执行 Phase 4 末步**回填**「当前状态」区（⛔ 该步不生成本体）
  │    └─ 是 → 进入检查 3
  │
  ├─ 检查 3：docs/architecture/ 三份约束文件是否存在？（架构设计文档可选，不参与此基线检查）
  │    ├─ 否 → 从 **Phase 2 / Step 2.1** 开始（memory 和项目记忆文件已有，补 architecture 约束空模板）
  │    └─ 是 → 进入检查 4
  │
  ├─ 检查 4：docs/requirements/{version}/研发需求/01_研发需求.md 是否存在？
  │    ├─ 否 → 跳过 Step 1，直接 Step 2（执行 /version 做版本规划）
  │    └─ 是 → 进入检查 5
  │
  ├─ 检查 5：docs/design/detail/{version}/ 设计文档目录下全部分册是否存在？
  │    ├─ 否 → 单独执行 /sprint-design 生成设计
  │    └─ 是 → 进入检查 6
  │
  ├─ 检查 6：docs/plans/{version}/01_研发执行计划.md 是否存在？
  │    ├─ 否 → 单独执行 /sprint-plan 生成研发执行计划
  │    └─ 是 → 进入检查 7
  │
  ├─ 检查 7：docs/testing/{version}/研发自测/ 下自测用例是否存在？
  │    ├─ 否 → 单独执行 /sprint-selftest 生成研发自测（方案+用例+测试环境）
  │    └─ 是 → 全部就绪，直接进入 Step 3（执行 Sprint）
```

### 5.2 三种典型场景

#### 场景 A：全新项目（从零开始）

**状态**：空仓库或仅有 PRD / 脚手架代码

**执行顺序**：
```bash
/sprint-init              # Step 1：建骨架
/version V0.1.0 "M1 MVP"  # Step 2：版本规划
/sprint-batch             # Step 3：执行 Sprint
```

#### 场景 B：克隆自老项目（复用模板）

**状态**：从另一个 AIDP 项目克隆过来，memory/ 和项目记忆文件已存在但内容不适用

**执行顺序**：
```bash
# 1. 备份旧内容（⚠️ 先确认旧 memory/ 与项目记忆文件确实不适用，统一 mv 备份而非直接删除）
mv memory/ memory.backup/                 # 备份旧记忆（确认无用后再删 memory.backup/）
mv AGENTS.md AGENTS.md.backup

# 2. 全新初始化
/sprint-init
/version V0.1.0 "M1 MVP"
/sprint-batch
```

> ⚠️ `rm -rf memory/` 不可恢复，且会连同**项目级**记忆（projectBrief / productContext 等）一起删除。除非确认旧内容完全无用，否则一律先 `mv` 备份再清理。

**或保留部分内容**（推荐）：
```bash
# 保留 memory/projectBrief.md 和 productContext.md，手工编辑更新项目信息
# 清空 memory/{version}/{user}/
rm -rf memory/V*

# 单独执行缺失的步骤
/sprint-init-complete     # 补生成 activeContext/progress + 回填项目记忆文件「当前状态」区
/version V0.1.0 "M1 MVP"
```

#### 场景 C：已有 PRD 和详细设计（不走自动生成）

**状态**：人工已经写好了 PRD 和详细设计文档，想跳过自动生成步骤

**执行顺序**：
```bash
# 1. 把已有文档放到标准位置（新生成一律索引态：00_索引 + 01_ 序号，见约定 15）
# docs/requirements/V0.1.0/研发需求/00_索引.md + 01_研发需求.md
# docs/design/detail/V0.1.0/00_索引.md
# docs/design/detail/V0.1.0/01_详细设计.md
# docs/design/detail/V0.1.0/02_数据库设计.md
# docs/design/detail/V0.1.0/03_接口设计.md

# 2. 初始化骨架（memory 等）
/sprint-init

# 3. 跳过 /version 的需求和设计生成，只跑研发执行计划
/sprint-plan              # 基于已有文档生成 01_研发执行计划.md
# 或手工编辑 01_研发执行计划.md

# 4. 人工补充 docs/architecture/ 三份约束文档（架构设计文档可选，按需补 架构设计.md 或 架构设计/）
# （因为不走 /sprint-design，architecture 不会自动填充）

# 5. 执行 Sprint
/sprint-batch
```

### 5.3 各步骤的幂等检查与跳过规则

每个命令都应该在执行前检查目标文件是否已存在，给用户选择：

| 命令 | 检查项 | 已存在时的行为 |
|------|--------|--------------|
| `/sprint-init` | `memory/`、`AGENTS.md`、`docs/architecture/` | 提示用户"是否覆盖 / 跳过该步 / 合并" |
| `/version V0.1.0` | `docs/requirements/V0.1.0/研发需求/01_研发需求.md` 等 | 已存在则跳过对应子命令（`/sprint-requirements` 等），仅补缺失 |
| `/sprint-requirements` | `01_研发需求.md` | 存在则询问"是否重新生成 / 增量追加 / 跳过" |
| `/sprint-design` | `00_索引.md` + `01_详细设计.md` 等 | 同上 |
| `/sprint-plan` | `01_研发执行计划.md` | 同上 |

**推荐做法**：所有 `/sprint-*` 命令默认"检测到目标文件存在时先询问用户"，避免误覆盖人工编辑的内容。

### 5.4 完整初始化流程（场景 A 全新项目）

```
┌─────────────────────────────────────────────────────────────┐
│ Step 1：/sprint-init — 建立项目骨架（一次性）                 │
│                                                              │
│   生成内容：                                                  │
│   - memory/ 项目级文件（5 个，含模板或脚手架分析结果）         │
│   - memory/{version}/{user}/ 迭代级目录                      │
│   - docs/architecture/ 三份约束空模板（架构设计文档按需人工补）│
│   - docs/ 各版本目录骨架                                      │
│   - AGENTS.md 主入口                                 │
│                                                              │
│   支持分步：                                                  │
│   - /sprint-init-design    Phase 1-2（memory 骨架 + arch 模板）│
│   - /sprint-init-complete  Phase 3-4（activeContext + AGENTS.md）│
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 2：/version V0.1.0 "M1 MVP" — 首版本规划                 │
│                                                              │
│   内部自动串联（每一步都检查文件是否已存在）：                   │
│   - /sprint-requirements  → 01_研发需求.md              │
│   - /sprint-design  → 00_索引 + 01_详细设计/02_数据库设计/03_接口设计 │
│                           + ★ 动态填充 architecture 三份文档  │
│   - /sprint-plan          → 01_研发执行计划.md                  │
│   - /sprint-selftest      → 研发自测：方案+用例+测试环境        │
│                                                              │
│   四个子命令也可独立调用（补缺或重生成）                        │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 3：选择执行模式（见第 6 节）                             │
│   /sprint-batch / /sprint-dev "<描述>" / /sprint-bugfix      │
└─────────────────────────────────────────────────────────────┘
```

### 5.5 为什么分两步？

| 职责 | 命令 | 何时执行 |
|------|------|---------|
| 建空容器 | `/sprint-init` | 项目首次建立，生成所有目录和空模板 |
| 填充实际内容 | `/version` | 每个新版本启动时调用 skill 生成需求/设计/计划 |

**关键原则**：
- **`docs/architecture/` 三份约束文档是累积的全局约束**
- 初始化时为空模板（团队可人工补充强约束）
- 每次 `/sprint-design` 根据实际设计追加内容
- 人工可随时编辑补充
- **架构设计文档为可选类**：项目级整体架构设计可放 `架构设计.md`（单文档）或 `架构设计/`（多文档子文件夹，`00_索引.md`+`NN_*.md`）；存量任意命名亦兼容识别（见 `06_版本与用户目录约定.md` §2.1.1）

### 5.6 /sprint-init 详细步骤（全新项目）

**Phase 0：★ 确定性骨架产出（先跑脚手架）**
- 由 `aidp-code-engineer` 一次性建出全部目录骨架与模板文件
- ⛔ **不要手工 `mkdir` 补目录**：`/sprint-init` Phase 0 明令禁止（历史事故：手搓漏建 `sql/全量`、`产品提供/`，`/sprint-start` 直接停在找不到目录上）

**Phase 1：PM Agent — 项目认知建立**
- **核验** Phase 0 已建出 memory 目录结构（⛔ 不手工建）
- 生成 `memory/projectBrief.md`（从 PRD 提取，无 PRD 则留空模板）
- 生成 `memory/productContext.md`

**Phase 2：Architect Agent — 技术认知建立**
- 创建 `docs/architecture/` 三份约束空模板（架构设计文档可选，按需人工补）
- 生成 `memory/systemPatterns.md`（从脚手架提取，无则空模板）
- 生成 `memory/techContext.md`
- 生成 `memory/databaseBaseline.md`

**Phase 3：UI Agent — 原型认知建立（可选）**
- 如 `docs/prototype/{version}/code/` 存在原型代码，提取视觉特征回填 `UI规范约束.md` 初版

**Phase 4：PM Agent — 完成初始化**
- 生成 `memory/{version}/{user}/activeContext.md`（初始状态）
- 生成 `memory/{version}/{user}/progress.md`
- **回填** `AGENTS.md` 的「当前状态」区（⛔ 本体由 `scaffold.py::sync_memory_file` 产出，不重写正文）

### 5.7 初始化输入清单

| 类型 | 路径 | 是否必须 | 说明 |
|------|------|---------|------|
| AIDP 范式 | `docs/init/` | ✅ | 框架自带 |
| 产品需求文档 | ★ 推荐版本级 `docs/requirements/{version}/产品提供/*.md`；`docs/requirements/PRD-*.md` 为项目级兜底 | 📎 推荐 | 首次 `/version` 生成 01_研发需求.md 的主要输入 |
| 原型代码 | `docs/prototype/{version}/code/` | 📎 推荐 | UI Agent 生成 UI 规范的输入 |
| 高保真原型 | `docs/prototype/{version}/mockup/` | 📎 推荐 | 视觉最高优先级；无则按约定 4 的 4 情形决策（**仅情形 D、用户显式选择时**才由 UI Agent 流程 C 生成，单一信源 = `agents/ui.md` 流程 A Step 0）|
| 脚手架代码 | `code/` | 📎 推荐 | 提取已有技术栈、公共组件、表结构 |
| 环境配置 | `env/.env` | 📎 推荐 | 记录数据库连接、外部服务账号 |

初始化输入的详细说明见 `01_初始化输入指导.md`。

---

## 6. 迭代开发流程（Sprint Cycle）

> **流程说明**：区分"版本规划期"（/version 一次性生成文档）与"Sprint 执行期"（四种模式按需选择）。

### 6.1 两阶段流程总览

```
┌──────────────────────────────────────────────────────────────────────┐
│ 阶段 A：版本规划期（一次性）                                           │
│                                                                       │
│   /version V0.1.0 "M1 MVP"                                           │
│     ├─ /sprint-requirements  → 01_研发需求.md                   │
│     │   （调用 ux-logic-extractor skill）                             │
│     ├─ /sprint-design        → 详细设计 / 接口设计 / 数据库设计.md     │
│     │   （调用 dev-logic-architect skill）                            │
│     ├─ /sprint-plan          → 01_研发执行计划.md                        │
│     │   （调用 dev-execution-planner skill）                          │
│     └─ /sprint-selftest      → 研发自测方案 / 用例 / 测试环境与账号     │
│         （调用 dev-manual-testcase skill）                            │
└──────────────────────────────────────────────────────────────────────┘
                          ↓
┌──────────────────────────────────────────────────────────────────────┐
│ 阶段 B：Sprint 执行期（★ 三个常用入口，按场景选一个）                   │
│                                                                       │
│   ★ 首次全量跑：      /sprint-batch                                   │
│      批量执行 研发执行计划 中所有 Sprint                               │
│                                                                       │
│   ★ 新增功能：        /sprint-dev "<目标描述>"                        │
│      自动累进新 Sprint + 追加设计 + 完整流程                          │
│                                                                       │
│   ★ 修复 bug：       /sprint-bugfix 或 /sprint-bugfix "<描述>"       │
│      - 无参数：修复已记录的零散 bug（无需新 Sprint）                   │
│      - 带描述：自动累进新 Sprint + 完整流程（适合较大 bug）            │
│                                                                       │
│   其他入口（按需使用）：                                                │
│   - /sprint-full {NNN}     按 研发执行计划 跑已规划的 Sprint          │
│   - /sprint-start ... /sprint-close  分步执行（严格人工审核）         │
└──────────────────────────────────────────────────────────────────────┘
                          ↓
┌──────────────────────────────────────────────────────────────────────┐
│ 阶段 C：发布                                                          │
│   /version V0.1.0   （所有 Sprint 完成后打 tag）                      │
└──────────────────────────────────────────────────────────────────────┘
```

### 6.2 四种执行模式对比

| 模式 | 命令 | 适用场景 | 人工介入 | 推荐度 |
|------|------|---------|---------|--------|
| **模式 1：批量** | `/sprint-batch` | 规划文档齐全，首次全量跑 | 最少 | ★★★ |
| **模式 2A：单 Sprint（按计划）** | `/sprint-full {NNN}` | 按 研发执行计划 的规划跑单个 Sprint | 中等 | ★★ |
| **模式 2B：自动累进** | `/sprint-full "<目标描述>"` | 首轮完成后继续新增功能/修复 | 中等 | ★★★ |
| **模式 3：分步** | `/sprint-start` → ... → `/sprint-close` | 需要严格审核每步 | 最多 | ★ |
| **独立修复** | `/sprint-bugfix` | 零散 bug，不需要新 Sprint | 最少 | ★★★ |

**关于自动累进（模式 2B）**：
- ★ **前提：当前版本【未发布】**——自动累进仅在当前版本尚未发布时适用。若当前版本【已发布】（有 release tag / 标「✅ 已发布」），累进前先过「版本落点决策门」三选一（落回已发布版重发 / 新开 patch / 新开 minor），执行体绝不静默往已发布版本累进（单一信源见约定 2 / `/sprint-dev` Phase 0B.0）
- 自动扫描已有 Sprint，序号取最大值 + 1（如 `sprint-005` 后续累进到 `sprint-006`）
- 自动产出**增量文档** `NN_<业务主题>.md` 到版本级各目录（研发需求 / 详细设计 / 数据库设计 / 接口设计），并在各目录 `00_索引.md` 登记；⛔ **不改主文档正文**（细则单一信源 = `/sprint-dev` Phase 0B.1.1）
- 按约定 22 级联到 `01_研发执行计划.md` 的 Sprint 清单**与研发自测用例**（四级 L1→L2→L3→**L4**，漏 L4 即违规）。★ **执行形态 = 攒批**：变更先按族记入 `_开发期{族}增量.md`（四族各一份、与该族内容主文档同目录，一行一条：编号·时间·一句话），由若干**收口点**批量级联——每日首次提交（push 后）/ 版本规划 / 版本发布 / `/sprint-batch` 收尾；收口时结合代码现状核实、成功即删条目、某族清空即删该族文件。判定规则一条未改，变的只是**执行时机**。详见 `{{AIDP_HOME}}/reference/开发期族增量.md`
- 然后执行完整的 Sprint 流程（start → dev → test → bugfix → close）
- ★ **用户不需要手动跑五步命令**，也不需要先改文档再开发

### 6.3 Sprint 执行期的命令层次

```
/sprint-batch  (批量,循环调用 /sprint-full)
    └─ /sprint-full  (单 Sprint 一键,串联下方 5 个子命令)
         ├─ /sprint-start    启动,读取需求和设计
         ├─ /sprint-dev      开发 (TDD + 并行)
         ├─ /sprint-test     测试 (code-verification-loop)
         ├─ /sprint-bugfix          修复 (循环直到通过或超限)
         └─ /sprint-close    关闭归档
```

**关键约定**：
- 上层命令只负责编排，具体工作由下层子命令完成
- 每个子命令都可单独调用（支持模式 3 分步执行）
- Bugfix 循环默认 5 次上限；**超限默认标记"⚠️ 软失败：bugfix 循环超限"并继续进入关闭 Sprint**，未修 bug 留在 `bugfix-{YYYYMMDD}-{user}.md`（状态「待修复」）交批量末段人工处理。仅显式传 `--stop-on-blocker` 才停下等待人工介入

### 6.4 Sprint 与子迭代机制

一个 Sprint 可以包含多次子迭代（Round）。**Round 主要指 Sprint 执行期内的循环**（测试 → 修复 → 回归测试）：

```
Sprint-001（执行期）
  ├── Round 1: 开发阶段      → backend + frontend 并行实现
  ├── Round 2: 测试阶段      → QA 执行测试，记录 bug
  ├── Round 3: 修复迭代      → Dev 修复 bug
  ├── Round 4: 回归测试      → QA 验证修复（可能再触发新的修复）
  └── Sprint 关闭            → PM 归档
```

需求和设计在 `/version` 阶段完成（不属 Sprint 内 Round）。

### 6.5 命令总览

> 本节为概览速查；**命令清单 + 用途 + 输入输出的单一信源见 [`05_commands详细规范.md`](./05_commands详细规范.md) §2「命令总览表」**，增删命令以 05 为准（本概览随后同步）。

| 类别 | 命令 | 职责 | 调用的 Skill |
|------|------|------|-------------|
| **初始化** | `/sprint-init` | 项目全量初始化（一次性） | - |
| | `/sprint-init-design` / `/sprint-init-complete` | 分步初始化（推荐） | - |
| **版本规划** | `/version` | 版本管理（规划/发布/串联下方 4 个） | - |
| | `/sprint-requirements` | 生成版本需求文档 | `ux-logic-extractor` |
| | `/sprint-design` | 生成详细设计文档 | `dev-logic-architect` |
| | `/sprint-plan` | 生成研发执行计划 | `dev-execution-planner` |
| | `/sprint-selftest` | 生成研发自测（方案+用例+测试环境） | `dev-manual-testcase` |
| **Sprint 执行** | `/sprint-batch` | 批量执行多个 Sprint（主体为循环 `/sprint-full`，末段 Step 6 触发部署 + AI 自动化测试） | `superpowers:verification-before-completion`（输出前硬门；⛔ 顶层循环**不用** `executing-plans`——它会停下征询，与「零询问连跑」冲突）|
| | `/sprint-full` | 单 Sprint 一键执行 | - |
| | `/sprint-start` | 启动 Sprint | - |
| | `/sprint-dev` | 开发阶段（支持独立使用 + 自动累进） | `superpowers:test-driven-development` + `superpowers:subagent-driven-development` |
| | `/sprint-test` | 测试阶段（静态扫描 + 可选接口测试；**前端浏览器仿真不在本命令内**，走 `/sprint-aiauto-test`） | `code-verification-loop`（`api-tester` 为可选外部能力） |
| | `/sprint-bugfix` | 问题修复（独立可用 + 自动累进） | `bugfix` skill + `superpowers:systematic-debugging` |
| | `/sprint-close` | Sprint 关闭 | - |
| | `/sprint-autopilot` | ★ 7×24 全自动开发编排器（操作系统调度 `aidp_scheduler.py` 守护） | 串联 `/version` + `/sprint-batch` |
| | `/sprint-aiauto-test` | ★ AI 自动化测试（当前工具 chrome-devtools-mcp；操作系统调度 `aidp_scheduler.py` 守护） | `auto-test-runner`（执行内核）+ chrome-devtools-mcp（Web 驱动）；用例读已落盘的 `docs/testing/{version}/`，不直调用例生成 SKILL |
| **辅助** | `/memory-sync` | 记忆同步 | - |
| | `/health-check` | 健康检查 | - |

### 6.6 阶段 B 各命令输入输出汇总

| 阶段 | 命令 | 负责 Agent | 输入 | 输出 |
|------|------|-----------|------|------|
| 启动 | `/sprint-start` | PM | 版本规划文档（01_研发需求.md / 01_详细设计.md / 01_研发执行计划.md） | 更新 activeContext |
| 开发 | `/sprint-dev` | Backend + Frontend | 详细设计、API 设计、DB 设计、UI 原型、脚手架 | 源代码（含公共组件）、编译/构建通过 |
| 测试 | `/sprint-test` | QA | 需求文档、代码 | 测试用例、测试报告、bug 记录 |
| 修复 | `/sprint-bugfix` | Backend / Frontend | bug 记录文件 | 修复代码、回填 bug 文件 |
| 关闭 | `/sprint-close` | PM | 测试结果、验收确认 | 验收结论记录、memory 归档、progress 更新 |

迭代输入的详细说明见 `02_迭代输入指导.md`。

### 6.7 ★ 文档动态同步机制

所有 `/sprint-*` 命令在执行过程中，如检测到引入**新接口/新表/新功能/新架构决策**，**先按受影响的族记入 `_开发期{族}增量.md`**（append-only），由**收口点**批量级联回四份上游文档，保持"设计 ↔ 代码"一致。⛔ **开发过程中不实时改这四册主文档正文**（约定 12 / 22 的攒批模型）；收口点全集、四族落点与条目格式的单一信源 = `{{AIDP_HOME}}/reference/开发期族增量.md`。

| 触发命令 | 检测内容 | 自动回写目标 |
|---------|---------|-------------|
| `/sprint-design` | 首次 `/version` 或增量设计 | `00_索引.md` + `01_详细设计.md` / `02_数据库设计.md` / `03_接口设计.md`（档位 S 合并为 1 册）+ `架构约束.md` / `技术选型.md` / `UI规范约束.md` |
| `/sprint-dev` | Step X.0.0 开发完成后 git diff 对比 | 检出实质变更 → **追加台账条目**（`--cascade-now` 才当场级联）；到收口点由 `/sprint-batch` Step 5.5 / `/version` Step 3.3.9.5 批量写回四册 |
| `/sprint-bugfix` | 修复过程涉及接口/表/架构变更 | 同上（纯代码逻辑修复不触发） |
| `/sprint-close` | Sprint 关闭时 | 更新 `memory/databaseBaseline.md`（新增/变更表）、`memory/systemPatterns.md`（新 ADR） |

**调用的 skill**：
- `ux-logic-extractor` — 生成/更新需求
- `dev-logic-architect` — 生成/更新详细设计、API、数据库、architecture 三份文档
- `dev-execution-planner` — 生成/更新研发执行计划
- `code-verification-loop` — 验收检查，发现缺失设计时反馈回写

**不触发条件**：纯代码逻辑修复（配置错误、笔误、边界判断调整等）不触发回写，保持设计文档稳定性。

---

## 7. 问题修复流程（Bugfix Cycle）

### 7.1 Bugfix 记录规范

问题记录放在 `docs/bugfix/{version}/` 目录下（**版本级单层目录**，发现人体现在文件名 `bugfix-{YYYYMMDD}-{user}.md` 而非目录层，见 `06_版本与用户目录约定.md` 第 2.3 节）。文件命名格式：

```
bugfix-{YYYYMMDD}-{user}.md
（一天一人一份汇总）
例：docs/bugfix/V0.1.0/bugfix-20260508-alice.md
例：docs/bugfix/V0.1.0/bugfix-20260508-bob.md
```

### 7.2 Bugfix 文件格式

```markdown
# Bugfix {YYYYMMDD} - {user}

## Bug 清单

| 编号 | 时间 | Sprint | 模块 | 现象 | 严重 | 优先级 | 难易 | 状态 | Commit | 备注 |
| :-: | :- | :-: | :- | :- | :-: | :-: | :-: | :-: | :- | :- |
| B-{YYYYMMDD}-01 | YYYY-MM-DD | Sprint-{NNN} | {模块} | {问题现象} | P2 一般 | 高 | 简单 | Verified 已验证 | `abc123` | {备注} |
| B-{YYYYMMDD}-02 | YYYY-MM-DD | Sprint-{NNN} | {模块} | {问题现象} | P1 严重 | 高 | 中等 | Fixed 已修 | `def456` | {备注} |

### 字段说明
- **严重**：P0 阻塞 / P1 严重 / P2 一般 / P3 轻微
- **优先级**：高 / 中 / 低
- **难易**：简单 / 中等 / 困难
- **状态**：Open 待修 / In-Progress 修复中 / Fixed 已修 / Verified 已验证 / Closed 已关闭 / Reopened 回归
- **Sprint**：该 bug 归属的 Sprint 序号（可选，支持跨 Sprint 修复）

---

# B-{YYYYMMDD}-01: {问题标题}（Sprint-{NNN}）

## Bug 现象（用户原话）

> {用户反馈原文}

## 影响范围

- 端：{前端/后端/全栈}
- 页面：{涉及页面或模块}
- 功能：{涉及功能点}
- Sprint：Sprint-{NNN}

## Root Cause

{AI 分析的根本原因，含代码级定位}

## 改动文件

### `{文件路径}`
- 第 XX 行：{修改说明}

## 验证步骤

1. {步骤 1}
2. {步骤 2}
3. {预期结果}

## 部署提醒

- **前端**：{是否需要重新构建}
- **后端**：{是否需要重启}
- **数据库**：{是否需要执行 SQL}
- **Redis**：{是否需要清缓存}

## Commit

- Commit hash: `{hash}`
- 分支: `{branch}`
- 版本: `{version}`

---

# B-{YYYYMMDD}-02: {下一个 Bug 标题}（Sprint-{NNN}）

（同上结构，依次列出当天该用户处理的所有 Bug）
```

### 7.3 Bugfix 执行流程

```
人工发现问题
    │
    ▼
在 docs/bugfix/{version}/ 下创建 bugfix-{YYYYMMDD}-{user}.md
    │
    ▼
执行 /sprint-bugfix 命令（或手动指定）
    │
    ├── AI 读取 bugfix 记录（默认只扫描当前用户目录）
    ├── AI 分析问题根因
    ├── AI 修改代码
    ├── AI 回填修改范围和方案到 bugfix 文件
    └── AI 更新 memory/{version}/{user}/activeContext.md
```

---

## 8. 多人协作规范

### 8.1 Git 分支策略

```
main                              生产分支（每个版本发布后合并，打 tag）
  └── develop                     开发主干
        ├── sprint/sprint-001     Sprint 主分支
        │     ├── feat/T-001-user-login      功能分支（Task 编号，AIDP 无 User Story 层）
        │     ├── fix/BUG-20260304-1         缺陷修复分支
        │     └── ...
        └── docs/sprint-001-design           文档分支（按需）
```

版本发布时由 `/version` 命令打 tag（详见 `05_commands详细规范.md`）。

### 8.2 Memory 文件写权限分工

| 文件 | 作用域 | 写权限 | 写入时机 |
|------|--------|--------|---------|
| `memory/projectBrief.md` | 项目级 | PM（需 Review） | 仅项目方向重大调整时 |
| `memory/productContext.md` | 项目级 | PM | 每次需求变更时 |
| `memory/systemPatterns.md` | 项目级 | Architect（需 Review） | 每次重大技术决策时 |
| `memory/databaseBaseline.md` | 项目级 | Architect | 每次 Sprint 关闭时更新，设计前必读 |
| `memory/techContext.md` | 项目级 | Dev（直接追加） | 环境变更时，注明姓名+日期 |
| `memory/{version}/{user}/activeContext.md` | 用户私有 | 该用户（独占） | 实时更新，同版本其他人不得修改 |
| `memory/{version}/{user}/progress.md` | 用户私有 | 该用户 | 仅 /sprint-close 时写入 |
| `memory/{version}/{user}/sprints/*.md` | 用户私有 | 禁止修改 | 仅 /sprint-close 时由 PM 创建 |

> **跨用户可见性**：不同用户可以**读取**其他用户的 `memory/{version}/{user}/` 了解协作者进度，但**不得修改**。
> 跨用户要同步的信息，走 `memory/systemPatterns.md`（项目级 ADR）或项目看板。

### 8.3 并行子 Agent 工作流

需要多角色并行时，用 **`Agent` 工具**按 `{{AIDP_HOME}}/agents/*.md` 的角色指令派独立子 Agent，
用 **`TodoWrite`** 维护任务清单与依赖。⛔ **不存在 `TeamCreate` / `TaskCreate` 这类工具**——
照它们写的流程一步都执行不了。

⛔ **并行不等于绕开命令**：各角色的产出仍必须经 `/sprint-*` 的既定门（约定 22 台账、
`version-auditor` 审计、`code-verification-loop` 验收）。
绕开命令直接让子 Agent 交付，等于同时绕掉上述全部质量门。

```
用户 / 主循环
    │
    ├── TodoWrite 建任务清单（架构设计 → 前后端并行 → 集成验收）
    ├── Agent 派 architect 子 Agent（读 {{AIDP_HOME}}/agents/architect.md）→ 完成详细设计
    ├── Agent 并行派 frontend / backend 子 Agent → 各自开发
    └── 回 /sprint-test 走验收门 → /sprint-bugfix → /sprint-close
```

---

## 9. 防混乱机制

### 9.1 会话开始标准提示词

每次启动 AI Agent 会话，第一条消息固定发送：

```
请按顺序读取以下文件，然后告诉我当前项目状态和建议的下一步行动：
1. AGENTS.md
2. memory/{version}/{user}/activeContext.md   （{version}、{user} 从项目记忆文件当前状态读出；读不到时向我确认）
3. memory/{version}/{user}/progress.md
```

### 9.2 混乱预防规则

| 风险 | 预防措施 |
|------|---------|
| AI 忘记项目背景 | 每次会话强制读取项目记忆文件（AGENTS.md / CLAUDE.md）+ activeContext.md |
| 多人修改同一文件冲突 | L3/L4 memory 按 `{version}/{user}/` 隔离；L1/L2 遵循写权限分工 + 强制 Review |
| **多版本并行时目录互相覆盖** | ★ 所有迭代产出按版本隔离；仅 bugfix / implementation / memory 三类再叠 `{user}/` 双层（见 06_版本与用户目录约定.md §2.2 / §2.3）|
| Sprint 范围蔓延 | 01_研发需求.md 有明确"排除项"章节 |
| 架构决策前后矛盾 | 所有决策记录在 `memory/systemPatterns.md`（项目级，不分版本），新决策须引用旧 ADR |
| 文档与代码不同步 | /memory-sync 在每个功能完成后立即执行 |
| 历史信息丢失 | Sprint 关闭时强制归档，历史记忆只追加不删除 |
| bugfix 无法追溯 | `docs/bugfix/{version}/` 下记录完整的问题→分析→修复→验证闭环 |
| 约束文档被忽略 | `docs/architecture/` 在项目记忆文件中列为必读清单 |
| 跨迭代数据库表重复 | ★ Architect 设计前必读 `memory/databaseBaseline.md`（项目级），新表必须先检查是否已存在 |
| 前端公共组件重复 | ★ Frontend Agent 开发前必须检查已有公共组件，禁止跨页面重复实现布局/导航 |
| UI 样式偏差 | ★ 高保真原型（`docs/prototype/{version}/mockup/`）优先于原型代码作为视觉基准；无高保真时走约定 4 的 4 情形决策，**仅情形 D（用户显式选）**才生成 |

### 9.3 定期健康检查

每两个 Sprint 执行一次 `/health-check` 命令，检查：

1. systemPatterns.md 中技术栈是否与实际代码一致
2. progress.md 功能完成状态是否准确
3. 是否有未记录的 ADR
4. techContext.md 启动命令是否仍然有效
5. 技术债务总数是否超过警戒线
6. bugfix 记录是否全部归档闭环

---

## 10. Skills 扩展体系

### 10.1 Skills 概述

Skills 是可复用的能力模块，契约定义放在 `{{AIDP_HOME}}/skills/` —— 它同时就是各 Agent 的原生发现位（`.claude/skills/` 或 `.agents/skills/`），运行根降层后不再有「真源一处、入口另一处」两层。

### 10.2 常见能力诉求 → 对应落点

> 完整 SKILL 清单见 `AGENTS.md`「本项目使用的 Skills」。

| 能力诉求 | 落点 |
|---------|------|
| 前端页面自动化功能测试 | `/sprint-aiauto-test`（chrome-devtools-mcp 浏览器仿真测试） |
| 代码质量自动审查 | `code-verification-loop`（维度 0 静态基线门 + 15 维度验收） |
| 数据库迁移脚本生成 | `dev-logic-architect`（数据库设计 + SQL 生成）+ `/sprint-design` |
| API Mock 服务 | 第三方接口临时 Mock 协议（`THIRD_PARTY_MOCK` 走前端拦截器 / 后端 `@Profile("mock")` 运行时开关；`DEV_MOCK` 走构建期裁掉，见约定 26 的分流） |

### 10.3 自定义 Skills 集成

Skills 文件格式遵循通用 Agent Skill 规范，契约放在 `{{AIDP_HOME}}/skills/{skill-name}/SKILL.md`。**文件顶部必须有 YAML frontmatter**（`name` + `description`）——Agent 靠它索引与匹配触发，缺 frontmatter 的 skill 不会被加载：

```markdown
---
name: {skill-name}
description: {一句话说明本 Skill 做什么 + 在什么场景/关键词下触发；描述越具体触发越准}
---

# {skill-name}

## 触发条件
{何时触发此 Skill}

## 输入
{Skill 需要的输入}

## 执行步骤
{Skill 的执行逻辑}

## 输出
{Skill 的产出}
```

---

## 附录：快速参考卡

### 命令速查表

> 速查用；命令清单单一信源见 [`05_commands详细规范.md`](./05_commands详细规范.md) §2。

| 类别 | 命令 | 用途 |
|------|------|------|
| **初始化** | `/sprint-init` | 全量初始化（一次性） |
| | `/sprint-init-design` | 初始化前半段（生成记忆文件） |
| | `/sprint-init-complete` | 初始化后半段（审核后完成） |
| **版本规划** | `/version V0.1.0 "M1 MVP"` | 版本管理：规划（串联下方 4 个）/ 发布打 tag |
| | `/sprint-requirements` | 生成版本需求文档（调用 ux-logic-extractor） |
| | `/sprint-design` | 生成详细设计（调用 dev-logic-architect） |
| | `/sprint-plan` | 生成研发执行计划（调用 dev-execution-planner） |
| | `/sprint-selftest` | 生成研发自测（调用 dev-manual-testcase） |
| **Sprint 执行** | `/sprint-batch [范围]` | ★ 批量执行多个 Sprint |
| | `/sprint-full {NNN}` | 单 Sprint 一键（start→dev→test→bugfix→close） |
| | `/sprint-start {NNN}` | 启动单个 Sprint |
| | `/sprint-dev [backend\|frontend]` | 开发阶段（TDD + 并行） |
| | `/sprint-test` | 测试阶段（code-verification-loop） |
| | `/sprint-bugfix [sprint-NNN]` | 修复 bug（systematic-debugging） |
| | `/sprint-close {NNN}` | 关闭归档 |
| **7×24 全自动** | `/sprint-autopilot` | ★ 开发链路编排器（操作系统调度 `aidp_scheduler.py`，默认每 10m 一轮） |
| | `/sprint-aiauto-test` | ★ AI 自动化测试链路（操作系统调度 `aidp_scheduler.py`，默认每 5m 一轮） |
| **辅助** | `/memory-sync` | 同步记忆 |
| | `/health-check` | 健康检查 |

### 新项目启动

```bash
# 方式A：全量初始化
/sprint-init

# 方式B：分步初始化（推荐，支持人工审核）
/sprint-init-design          # 生成 5 个记忆文件
# ... 审核 memory/ 下的文件 ...
/sprint-init-complete        # 完成初始化
```

### 新版本迭代（推荐流程）

```bash
# ============ 阶段 A：版本规划（一次性） ============
/version V0.1.0 "M1 MVP"
# 内部会自动串联调用：
#   /sprint-requirements  → docs/requirements/V0.1.0/研发需求/01_研发需求.md
#   /sprint-design        → docs/design/detail/V0.1.0/*.md + SQL
#   /sprint-plan          → docs/plans/V0.1.0/01_研发执行计划.md
#   /sprint-selftest      → docs/testing/V0.1.0/研发自测/（方案+用例+测试环境与账号）
# ... 人工审核规划文档（可选）...

# ============ 阶段 B：Sprint 执行（按需选择模式）============

# 模式 1：批量执行（★ 推荐首次全跑规划好的 Sprint）
/sprint-batch               # 跑完所有已规划的 Sprint
/sprint-batch 001-003       # 只跑前 3 个
/sprint-batch skip-bugfix   # 所有 bug 留待最后统一修

# 模式 2A：单 Sprint（按计划执行）
/sprint-full 001
/sprint-full 002

# 模式 2B：★ 自动累进 — 首轮完成后继续新增功能
/sprint-full "新增用户导出功能"         # 自动创建 Sprint-006 并执行完整流程
/sprint-full "修复批量导入逻辑"          # 自动创建 Sprint-007 并执行完整流程
# 内部自动：
# - 扫描已有 Sprint，序号累进
# - 追加增量到 研发需求 / 详细设计 / 接口设计 / 数据库设计
# - 追加到 研发执行计划
# - 执行 start → dev → test → bugfix → close

# 模式 2C：★ 单独用 /sprint-dev 或 /sprint-bugfix 入口（效果等同）
/sprint-dev "新增用户导出功能"          # 同 /sprint-full，自动累进
/sprint-bugfix "修复批量导入逻辑"       # 同 /sprint-full，自动累进

# 模式 3：分步执行（严格审核每步）
/sprint-start 001
/sprint-dev                 # 或 /sprint-dev backend + /sprint-dev frontend
/sprint-test
/sprint-bugfix sprint-001
/sprint-close 001

# ============ 独立 bug 修复（任何时候都可用）============
# 在 docs/bugfix/{version}/bugfix-{YYYYMMDD}-{user}.md 添加 bug 表格和详情
/sprint-bugfix                     # ★ 独立使用，无需 Sprint 依赖
/sprint-bugfix sprint-003          # 按 Sprint 过滤

# ============ 阶段 C：发布 ============
/version V0.1.0             # 打 tag 发布
```

### 日常开发规范

```bash
# 每次新会话开始（{version} 和 {user} 按 06_版本与用户目录约定.md 流程解析）
"请按顺序读取 AGENTS.md、memory/{version}/{user}/activeContext.md、memory/{version}/{user}/progress.md"

# 完成一个功能后
/memory-sync

# 修复问题
/sprint-bugfix sprint-001

# 每天结束时
/memory-sync
```

### 版本管理

```bash
/version V0.1.0 "M1 MVP"   # 规划新版本
/version V0.1.0            # 发布该版本（所有 Sprint 关闭后，自动打 tag）
```

---

*AIDP — 基于 AI 编码 Agent Team + Skills 生态设计*
*支持：多版本并行 | 多人协作 | 批量执行 | 自动累进 | 独立 bug 修复 | Agent Team 并行开发*
