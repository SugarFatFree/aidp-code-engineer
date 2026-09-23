# 05 — Commands 详细规范

> **文档定位**：本文档是斜杠命令体系的**总览和索引**。
> 下游命令定义位于 `{{AIDP_HOME}}/commands/`（仅 Claude 为 `.claude/aidp/`，有 Codex / DSH 为 `.agents/aidp/`），适配入口分别为 `.claude/commands/`、`.codex/skills/aidp/`、`.dsh/commands/`。下方 Markdown 链接指向下游已安装的命令定义；模板仓库中的维护源位于 `.aidp/commands/`。
> 本文档**不再重复**每个命令的内部细节，仅提供命令层次、执行模式、调用关系的全局视图。

---

## 目录

- [1. 命令分层架构](#1-命令分层架构)
- [2. 命令总览表](#2-命令总览表)
- [3. 四种执行模式](#3-四种执行模式)
- [4. 统一前置流程](#4-统一前置流程)
- [5. 命令 vs Skill 关系](#5-命令-vs-skill-关系)
- [6. 命令文件索引](#6-命令文件索引)

---

## 1. 命令分层架构

```
┌──────────────────────────────────────────────────────────┐
│ 初始化（一次性）                                           │
│   /sprint-init           全量初始化                        │
│   /sprint-init-design + /sprint-init-complete            │
├──────────────────────────────────────────────────────────┤
│ 版本规划期（/version 串联调用下方 4 个子命令）              │
│   /sprint-requirements   调用 ux-logic-extractor          │
│   /sprint-design         调用 dev-logic-architect         │
│   /sprint-plan           调用 dev-execution-planner       │
│   /sprint-selftest       调用 dev-manual-testcase         │
├──────────────────────────────────────────────────────────┤
│ Sprint 执行期（四种模式）                                  │
│                                                           │
│   模式 1 批量：       /sprint-batch                        │
│                       循环调用 /sprint-full               │
│                                                           │
│   模式 2A 按计划单跑： /sprint-full {NNN}                  │
│   模式 2B 自动累进：   /sprint-full "<描述>"               │
│                       串联 start → dev → test             │
│                       → bugfix → close                    │
│                                                           │
│   模式 3 分步：                                            │
│     /sprint-start {NNN}                                   │
│     /sprint-dev  或  /sprint-dev "<描述>"  （支持独立累进）│
│     /sprint-test                                          │
│     /sprint-bugfix  或  /sprint-bugfix "<描述>"           │
│     /sprint-close {NNN}                                   │
├──────────────────────────────────────────────────────────┤
│ 7×24 全自动（操作系统调度守护，双链路并行）                │
│   /sprint-autopilot   开发链路编排（PRD→/version→batch）   │
│   /sprint-aiauto-test chrome 浏览器仿真测试（部署后实测）  │
├──────────────────────────────────────────────────────────┤
│ 辅助                                                       │
│   /memory-sync    同步记忆                                 │
│   /health-check   健康检查                                 │
└──────────────────────────────────────────────────────────┘
```

## 2. 命令总览表

| 类别 | 命令 | 触发时机 | 调用的 skill | 命令文件 |
|------|------|---------|-------------|---------|
| **初始化** | `/sprint-init` | 项目初始化（一次性） | - | [`{{AIDP_HOME}}/commands/sprint-init.md`](../../{{AIDP_HOME}}/commands/sprint-init.md) |
| | `/sprint-init-design` | 分步初始化前半段 | - | [`{{AIDP_HOME}}/commands/sprint-init-design.md`](../../{{AIDP_HOME}}/commands/sprint-init-design.md) |
| | `/sprint-init-complete` | 分步初始化后半段 | - | [`{{AIDP_HOME}}/commands/sprint-init-complete.md`](../../{{AIDP_HOME}}/commands/sprint-init-complete.md) |
| **版本规划** | `/version [版本号] [里程碑]` | 新版本规划 / 版本发布 | 串联下方 4 个 | [`{{AIDP_HOME}}/commands/version.md`](../../{{AIDP_HOME}}/commands/version.md) |
| | `/sprint-requirements` | 生成需求文档 | `ux-logic-extractor` | [`{{AIDP_HOME}}/commands/sprint-requirements.md`](../../{{AIDP_HOME}}/commands/sprint-requirements.md) |
| | `/sprint-design` | 生成详细设计 + 动态更新 architecture | `dev-logic-architect` | [`{{AIDP_HOME}}/commands/sprint-design.md`](../../{{AIDP_HOME}}/commands/sprint-design.md) |
| | `/sprint-plan` | 生成研发执行计划 | `dev-execution-planner` | [`{{AIDP_HOME}}/commands/sprint-plan.md`](../../{{AIDP_HOME}}/commands/sprint-plan.md) |
| | `/sprint-selftest` | 生成研发自测（方案 + 自测用例 + 测试环境与账号） | `dev-manual-testcase` | [`{{AIDP_HOME}}/commands/sprint-selftest.md`](../../{{AIDP_HOME}}/commands/sprint-selftest.md) |
| **Sprint 执行** | `/sprint-batch [范围]` | 批量执行多个 Sprint | `superpowers:executing-plans` | [`{{AIDP_HOME}}/commands/sprint-batch.md`](../../{{AIDP_HOME}}/commands/sprint-batch.md) |
| | `/sprint-full {NNN}\|"<描述>"` | 单 Sprint 一键（支持按计划或自动累进） | 串联下方 5 个 | [`{{AIDP_HOME}}/commands/sprint-full.md`](../../{{AIDP_HOME}}/commands/sprint-full.md) |
| | `/sprint-start {NNN}` | 启动单个 Sprint | - | [`{{AIDP_HOME}}/commands/sprint-start.md`](../../{{AIDP_HOME}}/commands/sprint-start.md) |
| | `/sprint-dev [scope\|"描述"]` | 开发阶段（★ 支持独立累进） | `superpowers:test-driven-development` + `superpowers:subagent-driven-development` | [`{{AIDP_HOME}}/commands/sprint-dev.md`](../../{{AIDP_HOME}}/commands/sprint-dev.md) |
| | `/sprint-test` | 测试阶段（静态扫描 + 可选接口测试；**前端浏览器仿真不在本命令内**，走 `/sprint-aiauto-test`） | `code-verification-loop`（+ 外部可选 `api-tester`） | [`{{AIDP_HOME}}/commands/sprint-test.md`](../../{{AIDP_HOME}}/commands/sprint-test.md) |
| | `/sprint-bugfix [sprint-NNN\|bugfix-*.md\|"描述"]` | 问题修复（★ 支持独立使用 + 自动累进；可按 Sprint / 指定文件名 / 描述累进三种入参） | `bugfix` + `superpowers:systematic-debugging` | [`{{AIDP_HOME}}/commands/sprint-bugfix.md`](../../{{AIDP_HOME}}/commands/sprint-bugfix.md) |
| | `/sprint-close {NNN}` | Sprint 关闭 | - | [`{{AIDP_HOME}}/commands/sprint-close.md`](../../{{AIDP_HOME}}/commands/sprint-close.md) |
| **7×24 全自动** ★ | `/sprint-autopilot` | PRD 监听 → 自动开发链路编排（操作系统调度 `aidp_scheduler.py` 守护） | 串联 `/version` + `/sprint-batch` | [`{{AIDP_HOME}}/commands/sprint-autopilot.md`](../../{{AIDP_HOME}}/commands/sprint-autopilot.md) |
| | `/sprint-aiauto-test` | 部署后 chrome 浏览器仿真测试（操作系统调度 `aidp_scheduler.py` 守护） | `auto-test-runner`（执行内核）+ chrome-devtools-mcp（Web 驱动）；用例读已落盘的 `docs/testing/{version}/`（`正式用例/` 为主 + `研发自测/` 查漏补充），不直调用例生成 SKILL | [`{{AIDP_HOME}}/commands/sprint-aiauto-test.md`](../../{{AIDP_HOME}}/commands/sprint-aiauto-test.md) |
| **辅助** | `/memory-sync` | 记忆同步 | - | [`{{AIDP_HOME}}/commands/memory-sync.md`](../../{{AIDP_HOME}}/commands/memory-sync.md) |
| | `/health-check` | 健康检查 | - | [`{{AIDP_HOME}}/commands/health-check.md`](../../{{AIDP_HOME}}/commands/health-check.md) |

## 3. 四种执行模式

### 模式 1：批量执行（★ 首次全量跑推荐）

```bash
/version V0.1.0 "M1 MVP"    # 一次性生成所有规划文档
/sprint-batch               # 批量执行已规划的所有 Sprint
# ... 人工验证 ...
/sprint-bugfix              # 独立修复发现的零散 bug
/version V0.1.0             # 发布打 tag
```

### 模式 2A：单 Sprint（按计划）

```bash
/sprint-full 001            # 按 研发执行计划 执行 Sprint-001
/sprint-full 002
```

### 模式 2B：自动累进（★ 推荐新增功能/修复大 bug）

```bash
/sprint-full "新增用户导出功能"
# 等效入口：
/sprint-dev "新增用户导出功能"          # 开发视角
/sprint-bugfix "修复批量导入需新增接口"  # 修 bug 视角

# 自动：
# - 扫描已有 Sprint，新编号累进
# - 产出增量文档 NN_<业务主题>.md 到 研发需求/详细设计/接口设计/数据库设计（不改主文档正文，各目录 00_索引.md 登记）
# - 按约定 22 级联到 研发执行计划 + 研发自测用例（四级 L1→L2→L3→L4，漏 L4 即违规）
#   ★ 默认【攒批】：先按族记 _开发期{族}增量.md，由收口点清单批量级联（详见 reference/开发期族增量.md）；
#     需当轮成文用 --cascade-now
# - 执行 start → dev → test → bugfix → close
```

### 模式 3：分步执行（严格审核每步）

```bash
/sprint-start 001
/sprint-dev                 # 或 /sprint-dev backend / /sprint-dev frontend
/sprint-test
/sprint-bugfix sprint-001
/sprint-close 001
```

### 独立 bugfix（任何时候都可用）

```bash
# 在 docs/bugfix/{version}/bugfix-{今日}-{user}.md 添加 bug 表格行
/sprint-bugfix                   # 修复当前用户所有待修复 bug
/sprint-bugfix sprint-003        # 按 Sprint 过滤
```

## 4. 统一前置流程

> 除 `/sprint-init*` 和 `/version` 外，所有 Sprint 相关命令执行前都必须走此流程。
> 详见 `06_版本与用户目录约定.md` 第 4、6 节。

```
Step P0: 读取 AGENTS.md「当前状态」 → 得到 {version}
Step P1: git config user.name                → 得到 {user}
Step P2: 缺失/非法 → 按 06 文档第 6 节话术向用户追问
Step P3: 路径变量展开 → 按 06 文档第 2 节的路径模板使用
```

## 5. 命令 vs Skill 关系

| 类型 | 位置 | 触发方式 | 作用 |
|------|------|---------|------|
| **命令** | `{{AIDP_HOME}}/commands/*.md` | 用户输入 `/xxx` | 用户入口，高层编排器 |
| **技能 Skill** | `{{AIDP_HOME}}/skills/*/SKILL.md`（Agent 发现入口 `.claude/skills/` / `.agents/skills/`） | AI Agent 内部用 Skill 工具调用 | 底层实现细节 |

**典型调用关系**：
```
用户输入 /sprint-bugfix
    ↓
{{AIDP_HOME}}/commands/sprint-bugfix.md
    ↓ 内部调用 Skill 工具
{{AIDP_HOME}}/skills/bugfix/SKILL.md + superpowers:systematic-debugging
```

## 6. 命令文件索引

下游命令定义位于 `{{AIDP_HOME}}/commands/` 下，由各 Agent 的命令入口装配；模板维护源结构如下：

```
.aidp/commands/
├── sprint-init.md              项目全量初始化
├── sprint-init-design.md       分步初始化前半段
├── sprint-init-complete.md     分步初始化后半段
├── version.md                  版本管理（规划/发布）
├── sprint-requirements.md      生成需求（调用 ux-logic-extractor）
├── sprint-design.md            生成设计（调用 dev-logic-architect）+ 动态更新 architecture
├── sprint-plan.md              生成研发执行计划（调用 dev-execution-planner）
├── sprint-selftest.md          生成研发自测（调用 dev-manual-testcase）
├── sprint-batch.md             批量执行多 Sprint
├── sprint-full.md              单 Sprint 一键（支持按计划/自动累进）
├── sprint-start.md             启动 Sprint
├── sprint-dev.md               开发阶段（支持独立累进 + 自动回写设计）
├── sprint-test.md              测试阶段
├── sprint-bugfix.md            问题修复（支持独立累进 + 自动回写设计）
├── sprint-close.md             Sprint 关闭
├── sprint-autopilot.md         ★ 7×24 全自动开发编排器（操作系统调度 aidp_scheduler.py 守护）
├── sprint-aiauto-test.md       ★ chrome 浏览器仿真测试（操作系统调度 aidp_scheduler.py 守护）
├── memory-sync.md              记忆同步
└── health-check.md             健康检查
```

**维护原则**：
- 本文档只维护全局视图（分层、模式、前置流程、文件索引）
- 具体命令的执行细节在下游 `{{AIDP_HOME}}/commands/` 中，不在本文档重复
- 修改通用命令行为时，在模板仓库 `.aidp/commands/` 修改并经脚手架同步，不直接修改下游契约

---
