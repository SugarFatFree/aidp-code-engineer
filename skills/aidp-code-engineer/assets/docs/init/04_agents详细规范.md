# 04 — Agents 详细规范

> **文档定位**：本文档是 Agent 角色体系的**总览和索引**。
> 下游 Agent 指令位于 `{{AIDP_HOME}}/agents/`，AI Agent 运行时从该目录读取（仅 Claude 为 `.claude/`，有 Codex / DSH 为 `.agents/`）。下方链接指向下游已安装的运行目录；模板仓库中的维护源位于 `.aidp/agents/`。
> 本文档**不再重复** Agent 内部细节，仅提供角色职责、协作关系、调用规则的全局视图。

---

## 目录

- [1. Agent 角色体系](#1-agent-角色体系)
- [2. 各 Agent 职责边界](#2-各-agent-职责边界)
- [3. Agent 激活规则](#3-agent-激活规则)
- [4. Agent 协作流程](#4-agent-协作流程)
- [5. Agent 文件索引](#5-agent-文件索引)
- [6. 路径规则](#6-路径规则)

---

## 1. Agent 角色体系

AIDP 定义了 **7 个业务 Agent + 1 个合规 Agent + 1 个版本规划产物审计 Agent（共 9 个）**，每个角色专职一类工作，通过文档交接（不靠对话）协作：

```
PM Agent         需求管理者
  ↓
Architect Agent  架构设计者
  ↓
┌─────────────────┬──────────────────┐
│                 │                  │
UI Agent         Backend Agent      Frontend Agent
视觉规范         后端实现            前端实现
└─────────────────┴──────────────────┘
  ↓
QA Agent         质量守门人
  ↓
Reviewer Agent   代码审查
                                ←── AIDP-Compliance Agent（脚手架末尾 / 手动激活，跨阶段独立运行）
                                ←── Version-Auditor Agent（/version Step 2.4.7 强制激活，审计版本规划产物，独立子 Agent 隔离上下文）
```

## 2. 各 Agent 职责边界

| Agent | 职责 | 主要输入 | 主要输出 | 指令文件 |
|-------|------|---------|---------|---------|
| **PM** | 需求分析、需求拆分（EPIC/Task）、验收结论、Sprint 生命周期管理 | PRD、业务需求 | 需求文档、验收结论（并入 AI执行报告/progress）、activeContext/progress | [`pm.md`](../../{{AIDP_HOME}}/agents/pm.md) |
| **Architect** | 系统设计、技术决策、ADR、详细设计、数据库基线 | 需求、`docs/architecture/`（架构约束 + 可选架构设计文档，全目录）、脚手架、databaseBaseline | 详细设计、API 设计、DB 设计、SQL、ADR | [`architect.md`](../../{{AIDP_HOME}}/agents/architect.md) |
| **UI** | 视觉规范、高保真原型生成、组件映射 | PRD、UI 原型代码、UI 规范约束 | UI 规范、组件映射、`docs/prototype/{version}/mockup/` 原型 | [`ui.md`](../../{{AIDP_HOME}}/agents/ui.md) |
| **Frontend** | 前端代码实现、公共组件、API 调用层 | 详细设计、UI 规范、高保真原型、脚手架 | 前端代码（TDD + 复用公共组件） | [`frontend.md`](../../{{AIDP_HOME}}/agents/frontend.md) |
| **Backend** | 后端代码实现、API、数据库 | API 设计、DB 设计、脚手架 | 后端代码（TDD + 分层结构） | [`backend.md`](../../{{AIDP_HOME}}/agents/backend.md) |
| **QA** | 测试用例设计与执行、Bugfix 验证、回归测试 | 需求、验收标准、代码、bugfix 记录 | 测试用例、测试报告、bug 记录 | [`qa.md`](../../{{AIDP_HOME}}/agents/qa.md) |
| **Reviewer** | 代码质量审查、安全性、规范性、UI 一致性 | 代码、设计文档、约束文档 | 审查报告、合并决策 | [`reviewer.md`](../../{{AIDP_HOME}}/agents/reviewer.md) |
| **AIDP-Compliance** ★ | 范式合规检查（包住 verify.py 全部脚本 + 4 个语义维度：模板残留、事实清单 ↔ 代码、引用三角、目标 ↔ 实现背离〔仅当仓库根有 `设计目标.md` 时启用，无则 INFO 跳过〕） | verify.py stdout、memory/、项目记忆文件（AGENTS.md / CLAUDE.md）、code/ 配置、事实清单 | 统一合规报告（终端 + 必要时 `docs/audit/合规检查-{YYYYMMDD}.md`） | [`aidp-compliance.md`](../../{{AIDP_HOME}}/agents/aidp-compliance.md) |
| **Version-Auditor** ★ | 版本规划产物全量审计（8 项：A 存在性 / B 边界 / C 覆盖完整性 / D 增量一致性 / E 引用链 / F 原型覆盖度（Critical 硬门）/ G 语义变更派生完整性（约定 22 第三类，Critical 硬门）/ H 跨版本需求作废完整性（约定 34）） | 版本规划产物（requirements / design / plans / testing 等） | 审计报告 `docs/audit/{version}/version-output-audit-*.md` | [`version-auditor.md`](../../{{AIDP_HOME}}/agents/version-auditor.md) |

## 3. Agent 激活规则

### 3.1 命令/Skill 式激活

大部分场景下 Agent 由命令或 skill 自动激活：

| 触发点 | 激活的 Agent |
|--------|-------------|
| `/sprint-init` / `/sprint-init-design` | PM → Architect → UI |
| `/version` / `/sprint-requirements` | PM |
| `/version` Step 2.4.7（版本规划产物落盘后，强制） | Version-Auditor |
| `/sprint-design` | Architect + UI |
| `/sprint-dev` | Backend + Frontend（并行） |
| `/sprint-test` | QA |
| `/sprint-bugfix` | Backend / Frontend（按归属） |
| `/sprint-close` | PM |
| `aidp-code-engineer` skill（init / migrate / upgrade 末尾） | AIDP-Compliance |

### 3.2 手动激活

如需精细控制，手动激活单个 Agent：

```
请读取 {{AIDP_HOME}}/agents/frontend.md 并按照其中的指令工作。
当前任务是开发 Sprint-001 的前端部分。
```

### 3.3 多 Agent 并行激活

多 Agent 并行时，用 **`Agent` 工具**派独立子 Agent（每个子 Agent 自行 Read 对应角色文件），用 **`TodoWrite`** 维护任务与依赖。⛔ **没有 `TeamCreate` / `TaskCreate` 这类工具**，别照字面找：

```
创建 Agent Team sprint-001，角色包括：
- architect：负责详细设计
- backend-dev：后端实现（读取 {{AIDP_HOME}}/agents/backend.md）
- frontend-dev：前端实现（读取 {{AIDP_HOME}}/agents/frontend.md）
- qa-validator：集成验收

任务依赖：backend-dev + frontend-dev 并行 → qa-validator
```

## 4. Agent 协作流程

### 4.1 标准协作链

```
PM（生成需求 01_研发需求.md）
  ↓ 交接物：需求文档
Architect（生成 00_索引.md + 01_详细设计.md / 02_数据库设计.md / 03_接口设计.md + SQL）
  ↓ 交接物：设计文档
UI（生成 UI 规范 + 高保真原型）
  ↓ 交接物：docs/architecture/UI规范约束.md + mockup/
Backend + Frontend（并行实现代码）
  ↓ 交接物：代码 + 单元测试
QA（设计测试用例 + 执行 + 发现 bug）
  ↓ 交接物：测试报告 + bug 记录
Backend / Frontend（修复 bug）
  ↓ 交接物：修复代码
QA（回归验证）
  ↓ 交接物：验收确认
PM（记录验收结论 + 归档）
```

### 4.2 写权限分工

各 Agent 的写权限严格隔离，避免冲突。详见各 Agent 文件的"管辖的文件（写权限白名单）"章节。

核心原则：
- **Architect** 独占 `docs/design/detail/{version}/` + `docs/deployment/{version}/sql/增量/` + `memory/systemPatterns.md` + `memory/techContext.md` + `memory/databaseBaseline.md`
- **PM** 独占 `docs/requirements/` + `memory/projectBrief.md` + `memory/productContext.md` + `memory/{version}/{user}/activeContext.md` + `progress.md` + `sprints/` + `AGENTS.md`
- **UI** 独占 `docs/prototype/{version}/mockup/` + `docs/architecture/UI规范约束.md`
- **Backend** 独占 `code/backend/{子项目}/` 下的后端源代码 + `docs/bugfix/` 下的后端 bug 填写（目录结构与旧扁平 `code/server/` 兼容口径详见 `06_版本与用户目录约定.md` §2.5.5）
- **Frontend** 独占 `code/frontend/{子项目}/` 下的前端源代码 + `docs/bugfix/` 下的前端 bug 填写（目录结构与旧扁平 `code/web/` 兼容口径详见 `06_版本与用户目录约定.md` §2.5.5）
- **QA** 独占 `docs/testing/` + `docs/bugfix/` 下的 bug 发现与验证字段
- **Reviewer** 独占 `docs/reports/{version}/` 走查报告（`review-*.md`）
- **AIDP-Compliance** 仅可写 `docs/audit/合规检查-{YYYYMMDD}.md`，**禁止**修改任何 memory/、code/、docs/ 下其他文件（仅做读取 + 报告）

### 4.3 跨 Agent 红线

所有 Agent 都禁止：
- 修改已归档的 Sprint 文件（`memory/{version}/{user}/sprints/sprint-{NNN}.md`）
- 修改不属于自己职责范围的文件
- 修改 `docs/init/` 下的 AIDP 范式文档

详细红线见各 Agent 文件的"红线与禁止行为"章节。

## 5. Agent 文件索引

下游 Agent 指令文件位于 `{{AIDP_HOME}}/agents/` 下；下方链接指向已安装的运行目录供查阅：

| 文件 | 核心章节 |
|------|---------|
| [`{{AIDP_HOME}}/agents/pm.md`](../../{{AIDP_HOME}}/agents/pm.md) | 身份定义 / 会话启动清单 / 核心工作流程 / 输出格式 / 红线 / 完成标准 |
| [`{{AIDP_HOME}}/agents/architect.md`](../../{{AIDP_HOME}}/agents/architect.md) | 同上 |
| [`{{AIDP_HOME}}/agents/ui.md`](../../{{AIDP_HOME}}/agents/ui.md) | 同上 + 高保真原型生成流程 |
| [`{{AIDP_HOME}}/agents/frontend.md`](../../{{AIDP_HOME}}/agents/frontend.md) | 同上 + 视觉情形 A/B/C/D 判定（含 UI 设计规范维度）+ 真实 API 唯一交付/临时 Mock 清理规则 |
| [`{{AIDP_HOME}}/agents/backend.md`](../../{{AIDP_HOME}}/agents/backend.md) | 同上 + TDD 开发顺序 |
| [`{{AIDP_HOME}}/agents/qa.md`](../../{{AIDP_HOME}}/agents/qa.md) | 同上 + 测试用例设计维度 |
| [`{{AIDP_HOME}}/agents/reviewer.md`](../../{{AIDP_HOME}}/agents/reviewer.md) | 同上 + 审查维度矩阵 |
| [`{{AIDP_HOME}}/agents/aidp-compliance.md`](../../{{AIDP_HOME}}/agents/aidp-compliance.md) | 同上 + 包住 verify.py + 4 个语义维度（第 4 维「目标 ↔ 实现背离」仅当仓库根有 `设计目标.md` 时启用）+ 红线：禁止修改任何项目文件 |
| [`{{AIDP_HOME}}/agents/version-auditor.md`](../../{{AIDP_HOME}}/agents/version-auditor.md) | 同上 + 版本规划产物 8 项审计（A 存在性 / B 边界 / C 覆盖完整性 / D 增量一致性 / E 引用链 / F 原型覆盖度（Critical 硬门）/ G 语义变更派生完整性（约定 22 第三类，Critical 硬门）/ H 跨版本需求作废完整性（约定 34））+ 红线：只读审计、只写 `docs/audit/{version}/` 报告 |

**维护原则**：
- 本文档只维护全局视图（职责、协作、激活规则）
- 具体 Agent 的执行细节都在下游 `{{AIDP_HOME}}/agents/` 下，不在本文档重复
- 修改通用 Agent 行为时，回到模板仓库 `.aidp/agents/` 修改并经脚手架同步，不直接修改下游契约

## 6. 路径规则

所有 Agent 遵循 `06_版本与用户目录约定.md` 的路径规则。当 Agent 文件中出现 `{version}` / `{user}` 占位符时，按该文档第 4 节的路径解析算法展开。

---
