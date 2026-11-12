# 命令、角色与技能路由

formal 按需读取本索引；light 由 `{{AIDP_HOME}}/reference/light-entry.md` 分派，只加载受影响的 rules，不加载本清单或完整 Sprint 协议。角色与 SKILL 的执行细则仍由各自文件维护。

## ★ 多 Agent 兼容（Claude Code / Codex / DeepSeek Harness）

- **运行目录**：本项目的 AIDP 真源为 `各 Agent 的运行根/` —— 即 Agent 自己的目录，契约平铺其下；模板仓库的 `.aidp` 目录是维护源，**下游项目根没有这个目录**。Claude Code 与其他 Agent 并存时从 `.claude/` 的装配副本读取。  <!-- runtime-path-ignore: 指 Agent 自身目录这一概念，非运行契约路径，两包均保持原样 -->
- **无 Git 分流**：先读取脚手架返回的 `vcs_mode=git|none`；`none` 仍可规划、开发、本地测试和本地归档，Git 提交、推送、tag、CICD 监听不可假定成功，正式发布必须 fail closed、不得宣布已发布。是否建立 Git 仓库由用户决定，不自动 `git init`。

- **单一信源 = `{{AIDP_HOME}}/`**：命令、角色、规则、流程、脚本、hook、模板、SKILL、插件在此维护并入库。`agent_sync.py` 生成其他 Agent 的装配副本、指针入口和配置，生成物不手改，是否忽略以根 `.gitignore` 托管块为准；不能把运行真源一并忽略。具体目录所有权见 `{{AIDP_HOME}}/reference/agent-tools.md`，clone 后运行 `python3 {{AIDP_HOME}}/scripts/agent_sync.py` 恢复适配入口。
- **命令与 SKILL 分离**：AIDP 命令只放 `各 Agent 的运行根/commands/`，公共 SKILL 只放 `各 Agent 的运行根/skills/`，插件只放 `各 Agent 的运行根/plugins/`。Claude Code 使用 `.claude/commands/<命令>.md`（`/<命令>`）；Codex 使用官方发现根 `.codex/skills/aidp/<命令>/SKILL.md`（`$<命令>`，只允许用户显式调用；该文件是**指针入口**，权威正文仍在 `各 Agent 的运行根/commands/<命令>.md`，执行第一动作即 Read 它）；DeepSeek Harness 使用 `.dsh/commands/<命令>.md`（`/<命令>`）。Codex 与 DeepSeek Harness 共用 `.agents/skills/` 中的公共 SKILL，命令参数均保持 `$ARGUMENTS` 语义。Codex 命令正文遇到明确的 `/foo args` 串联时，确定性读取 `各 Agent 的运行根/commands/foo.md`，把 `args` 原样作为子命令 `$ARGUMENTS` 在当前执行链内联执行；文件不存在或无法唯一映射时 fail closed。<!-- runtime-path-ignore: 适配位对照，必须逐字写出各 Agent 的目录 -->
- **当前 Agent 判定**：`python3 各 Agent 的运行根/scripts/agent_env.py detect`——`AIDP_AGENT` 环境变量优先，其次项目根存在 `.codex/` → Codex、`.dsh/` → DeepSeek Harness、`.claude/` → Claude Code（可并存）。  <!-- runtime-path-ignore: 指 Agent 自身目录这一概念，非运行契约路径，两包均保持原样 -->
- **项目记忆文件**：只用 Claude Code 时为 `CLAUDE.md`；Codex / DeepSeek Harness 为 `AGENTS.md`；并存时正文在 `AGENTS.md`、`CLAUDE.md` 仅一行 `@AGENTS.md`。脚本一律经 `agent_env.py memory-file` 取路径。
- **工具名**：文档以 Claude Code 工具名书写（`AskUserQuestion` / `Agent` / `Skill` / `TodoWrite` / `/loop` 等），在其他 Agent 下按 **`{{AIDP_HOME}}/reference/agent-tools.md`** 换成等价能力，语义不变。

---

## ★ 常用命令速查

> 完整实操示例（各 flag / 7×24 详细前置 / 分阶段示例）见 **`{{AIDP_HOME}}/reference/命令速查.md`**（按需 Read）；本节只列入口 + 关键警示。自然语言自动路由见下方「Sprint 命令清单 + 意图路由」。

- **版本规划**：`/version V0.1.0 "M1"`（内部串 requirements→design→plan→selftest）
- **日常轻量任务**：自然语言或 `/sprint-dev "<描述>"`、`/sprint-bugfix ["<描述>"]` 默认 light；**正式 Sprint 执行**：`/sprint-full NNN`、`/sprint-batch`（公开 development 组合；部署/实测另按授权）
- **单Sprint/分步/辅助**：`/sprint-full NNN` · `/sprint-start;/sprint-dev;/sprint-test;/sprint-close` · `/memory-sync` · `/health-check`
- **7×24 全自动（★ 开发 + 测试两条链路必须同时运行才是完整闭环）**：`python3 {{AIDP_HOME}}/scripts/aidp_scheduler.py install`（OS 调度，三种 Agent 通用）/ `status`；只跑开发链路则浏览器实测永不自动开始；headless 裸 `--once` 须叠 `--unattended`。`/loop` 用法、前置（`notify` / chrome-mcp / `autopilot_decisions` / `cicd.*`）与告警台账详见 `{{AIDP_HOME}}/reference/命令速查.md`「阶段 C」。

## ★ Sprint 命令清单 + 意图路由

> **核心规则**：自动命令路由保留，但**选择能力与确定 light/formal 身份分开**。普通自然语言默认 light，可复用 start/dev/test/bugfix/close；明确 Sprint 或 version/full/batch/autopilot 才为 formal。先 resolve/route 按父策略筛选动作，再进入适用分支；复杂度、已有 activeContext 或历史计划不能升级身份或授权。需求含糊只澄清具体目标，不询问是否要创建 Sprint。

### 一、Sprint 命令全清单（16 个）

| 命令 | 用途 | 触发时机 |
|------|------|---------|
| `/sprint-init` | 项目全量初始化（生命周期仅 1 次）| 首次接入 AIDP |
| `/sprint-init-design` + `/sprint-init-complete` | 初始化分步模式（前/后半段）| 严格人工审核 |
| `/sprint-requirements` | 产品 PRD → 研发需求 | 版本规划期；通常 `/version` 内部调用 |
| `/sprint-design` | 详细设计 / 接口 / 数据库 / 对外接口 / 集成对接 | 版本规划期；通常 `/version` 内部调用 |
| `/sprint-plan` | 研发执行计划（Task 拆分 + 排期）| 版本规划期；通常 `/version` 内部调用 |
| `/sprint-selftest` | 研发自测方案 + 人工自测用例 + 测试环境与账号（调 dev-manual-testcase）| 版本规划期；通常 `/version`（Step 2.4.3.5）内部调用；缺自测时可单独补跑 |
| `/sprint-start` | 准备当前任务；formal 才启动 Sprint | 进入开发前 |
| `/sprint-dev` | 开发阶段（前/后端；默认 light，formal 支持累进）| 日常开发 |
| `/sprint-test` | 当前 task / 单 Sprint 相关测试、必要修复复验；已授权静态/审查/CVL同范围，不带浏览器或全版本 | 开发/修复后自动调用 |
| `/sprint-bugfix` | Bug 修复（默认 light；formal 按明确 Sprint 范围修复）| 测试发现或独立修复 |
| `/sprint-close` | 收束任务；formal 才关闭并归档 Sprint | 验收通过后 |
| `/sprint-full` | 单 Sprint 完整闭环：start→dev→test→bugfix→close | 一键跑完单 Sprint |
| `/sprint-batch` | 批量执行研发执行计划的多个 Sprint；末段 Step 6 仅在父级部署 / 实测授权时才衔接 `/sprint-aiauto-test --once`（缺授权不询问），失败用例回写「问题汇总清单」交 `/sprint-bugfix` | 跑完所有 Sprint |
| `/sprint-autopilot` ★ | **开发链路编排器**：扫 `docs/requirements/` 识别最近一对，分别串 `/version --no-tag` 和 `/version + /sprint-batch`；触发部署但不跑 chrome（**例外 P0-4**：交互式【单次】调用没有第二条 loop 承担时，autopilot 自跑一次 `/sprint-aiauto-test --once --unattended`）；经 `notify.py` 发里程碑通知 | 7×24 用 `/loop 10m`；直接调用走配置向导 |
| `/sprint-aiauto-test` ★ | **AI 自动化测试链路**（浏览器端：默认本地 CLI，显式声明才走远程 MCP）：独立仅明确目标实测；仅真实 autopilot 委派且 version/build/验收基线/完整用例清单齐备才当前版本全量；共享 baseline | 7×24 用 `/loop 5m`；单次 `--once`（不传版本号）；兜底 `--target V0.X.X` |

### 二、意图路由（自然语言 → sprint-* 命令）

规划类行仅在用户明确要求对应正式规划产物时适用；普通任务里“设计一个接口”“拆一下实现步骤”仍在 light 任务内复用相关角色，不自动生成版本规划或 Sprint 文档。表内 start/dev/test/bugfix/close 先按执行上下文分流，不能把能力关键词当正式身份。

| 关键词 / 表达 | 路由到 |
|--------------|------|
| "初始化项目"、"接入 AIDP"、"第一次跑"、"建立 AIDP 范式" | `/sprint-init`（或分步 design + complete）|
| "整理需求"、"PRD 转研发需求"、"分析需求"、"功能规格" | `/sprint-requirements` |
| "设计接口/数据库/详细设计"、"出技术方案"、"做架构"、"出 DDL"、"对外开放/集成接口设计" | `/sprint-design` |
| "拆任务"、"研发执行计划"、"任务排期"、"Sprint 划分"、"出开发计划" | `/sprint-plan` |
| "生成研发自测"、"生成自测用例"、"出自测方案"、"补研发自测"、"测试用例生成"、"配测试环境与账号" | `/sprint-selftest` |
| "把这个环境/账号记一下"、"补录测试账号"、"存下这个库连接"、"记录环境地址" | `/sprint-selftest --capture`（约定 38）★ 用户**随口给出**地址/账号时**无需等这句话**，按约定 38 当轮自动归档 |
| "开始 Sprint-NNN"、"启动 sprint" | `/sprint-start`（formal；明确编号） |
| "开发 XXX"、"新增 XXX"、"实现 XXX 模块"、"加个 XXX 按钮"、"前/后端实现" | `/sprint-dev`（默认 light，保留用户描述）|
| "跑相关测试"、"测试 XXX" | `/sprint-test` 能力路由，仅 related-test，不借显式命令组合 |
| "code review"、"代码审查" | reviewer 能力路由，仅 review，不附带 unit/CVL/文档 |
| "修个 bug"、"修复 XXX 问题"、"问题处理"、"页面打不开"（描述具体问题）| `/sprint-bugfix [描述]`（默认 light，复杂度不改变身份）|
| "关闭 Sprint"、"Sprint 完事了" | `/sprint-close`（formal）；普通任务的"收尾"复用 close（light） |
| "Sprint-NNN 一条龙"、"一键跑完 Sprint-NNN" | `/sprint-full [NNN]` |
| "跑所有 Sprint"、"批量执行"、"按计划全跑"、"一键所有 Sprint" | `/sprint-batch` |
| "无人值守"、"全自动开发"、"24 小时跑"、"autopilot"、"7×24"、"挂着自动开发" | `/sprint-autopilot`（无需传版本号）|
| "chrome 测试/实测"、"浏览器/仿真/UAT/页面测试"、"部署后测试"、"账号登录测" | 复用 `/sprint-aiauto-test` 的目标实测能力，保留 live-tests 范围，独立调用不取得 full-regression；仅真实autopilot委派当前版本完整清单才可全量 |
| "跑一下流水线"、"执行 CICD"、"触发构建部署"、"重新部署"、"部署到测试/研发环境" | **不新增命令**：先 `aidp_config.py cicd-enabled`（退出 0=已启用）。未启用 → 推送只有 `git push`，不跑脚本、不落盘；已启用 → 推送前只读分类 `classify_push.py --root . [--base-ref R --head H]`（不落盘，commit 现场 `git rev-parse HEAD`/`git ls-remote` 取得）：无正式代码变更时仍校验 push 成功但跳过远端 CICD/监听/就绪探针，分类失败按正式代码路径 fail-closed；正式代码变更经 CICD（`cicd.provider`，默认 GitHub Actions；push 自动触发，或 `cicd_watch.py --mode trigger` 主动触发）后由 `cicd_watch.py` 只读监听终态；主动 trigger/retry 与就绪探针先过本片执行策略的 deploy 门 |

> ★ **AI 测试入口前置规则**：路由到 `/sprint-aiauto-test` 前，若被测版本属 autopilot 体系（`current_build` 存在，或 `versions.{version}` 存在且 `source != "sprint-batch"`；判据单一信源 `{{AIDP_HOME}}/flows/sprint-batch/step-6b.md` Step 6.4）且本 build AI执行报告缺失 → **必须先经 `/sprint-autopilot --skip-dev` 产出报告骨架**，严禁直接手驱浏览器；仅真正 standalone（无 baseline 记录）才直达。口径：**实测前必有 AI执行报告**；autopilot 链内 `/sprint-batch` Step 6 豁免，全文见 `{{AIDP_HOME}}/reference/命令速查.md`「AI 测试入口前置规则」。

### 三、路由判定流程

1. **先继承身份**：嵌套、重试、验收内修复与续跑必须传原 `--execution-context`，原 `$ARGUMENTS` 保留；缺失时不能从 activeContext 猜父任务。
2. **新任务选择能力**：斜杠命令读取对应正文；自然语言按上表自动路由。"进入开发"、"开发并测试 XXX"、"修复接口"、"收尾"默认 light，只执行已授权能力，不因命令名含 sprint 升级身份或授权。
3. **确定身份**：明确 `Sprint-NNN`/Sprint 执行意图时走 formal，编号不明只澄清目标编号，不自动认领最早计划；版本规划/发布与 full/batch/autopilot 为 formal。普通任务即使仓库已有 active Sprint 也仍 light。
4. **先分流再过门**：各入口先执行 `entry_context.py resolve/route`。light 读取 `flows/sprint-dev/light-context.md`、执行对应轻量能力后 **return**；formal 才进入下文 Sprint 取号、契约、activeContext、归档门。formal 不等于 heavy 授权；同样只执行 allowed_actions，未启用检查记 NOT_REQUESTED。

---

## Agent 激活路由

| 当前任务 | 激活 Agent | 指令文件 |
|---------|-----------|---------|
| 需求分析 | PM Agent | `{{AIDP_HOME}}/agents/pm.md` |
| 系统设计 | Architect Agent | `{{AIDP_HOME}}/agents/architect.md` |
| UI 规范与原型分析 | UI Agent | `{{AIDP_HOME}}/agents/ui.md` |
| 前端开发 | Frontend Agent | `{{AIDP_HOME}}/agents/frontend.md` |
| 后端开发 | Backend Agent | `{{AIDP_HOME}}/agents/backend.md` |
| 测试执行 | QA Agent | `{{AIDP_HOME}}/agents/qa.md` |
| 代码审查 | Reviewer Agent | `{{AIDP_HOME}}/agents/reviewer.md` |
| ★ 范式合规检查 | AIDP-Compliance Agent | `{{AIDP_HOME}}/agents/aidp-compliance.md`（脚手架 init/migrate/upgrade 末尾自动激活；包住 `verify.py` 全部检查 + 4 个语义维度（维度 4「目标↔实现背离」仅当仓库根有 `设计目标.md` 时启用，无则 INFO 跳过））|
| ★ 版本规划产物审计 | Version-Auditor Agent | `{{AIDP_HOME}}/agents/version-auditor.md`（`/version` Step 2.4.7 强制激活；独立子 Agent 隔离上下文；8 项审计 A 存在性/B 边界/C 覆盖完整性（含 C-4 PRD 行级原子条目→研发需求、C-5 研发需求字段→详细设计 反向覆盖，Critical 硬门）/D 增量一致性/E 引用链/F 原型覆盖度（Critical 硬门）/G 语义变更派生完整性（约定 22 第三类触发，Critical 硬门）/H 跨版本需求作废完整性（约定 34）；产出 `docs/audit/{version}/`；唯一跳过 = `--skip-audit`，**且仅当 `trigger=version`**；autopilot Phase 3.3 的 build 终审无跳过路径）|
| ★ SKILL 移交维度审计 | QR-Handoff-Auditor Agent | `{{AIDP_HOME}}/agents/qr-handoff-auditor.md`（`/version --qr-level` 非 full 时，Step 2.4.7 与 Version-Auditor 同轮并行；每份移交清单一个实例） |

> ⚠️ **派 Agent 前先读 `{{AIDP_HOME}}/agents/README.md`**：上表这几份是**角色指令文件**，不是 Claude Code 原生的注册式 `subagent_type` —— `Agent({subagent_type: "backend"})` 调不起它们，而误用的失败形态是**静默的**（派出去一个没读过角色文件的通用子 Agent，它照样会交出一份看着像模像样的结果）。

---

## ★ 命令 vs Skill 关系说明

| 类型 | 位置 | 触发 | 作用 |
|------|------|---------|------|
| **斜杠命令** | `{{AIDP_HOME}}/commands/*.md` | 用户输入 `/xxx` | 用户入口，高层编排器 |
| **技能（Skill）** | `{{AIDP_HOME}}/skills/*/SKILL.md` | Claude 内部用 `Skill` 工具调用 | 底层实现细节 |

典型链：`/sprint-bugfix`（命令编排器）→ 内部调 `bugfix` skill + `superpowers:systematic-debugging`。同名 `bugfix` 命令与 skill 作用域不同、不冲突（前者用户入口、后者执行时内部工具）。

---

## 本项目使用的 Skills

> 各 SKILL **详细用途**见 **`{{AIDP_HOME}}/reference/skills.md`**（按需 Read）+ 各 `SKILL.md`（单一信源，约定 21）；本节只列「skill → 被谁调用」供路由。生成新业务编号前须 Read 该参考的「编号与执行证据的调用层协议」，通过 `alloc_id.py` 预留号段并传给执行方，禁止并发自行取最大号加一。

| Skill | 被谁调用 |
|-------|---------|
| `ux-logic-extractor` | `/sprint-requirements`（累进经 `--supplement` / `--ledger-cascade` 同一入口） |
| `dev-logic-architect` | `/sprint-design`（累进同上）；开发期预检直调其脚本见 `/sprint-dev` |
| `dev-execution-planner` | `/sprint-plan`（累进同上） |
| `dev-manual-testcase` ★ | `/sprint-selftest`（研发自测唯一生产入口）；其他命令一律经它转调（全量 / `--supplement` / `--ledger-cascade`）、不直调 SKILL |
| `auto-test-runner` ★ | `/sprint-aiauto-test` Phase 2 执行内核 |
| `code-verification-loop` | `/sprint-test`（仅验收模式）；开发期预检直调其脚本：`/sprint-dev`、Frontend/Backend Agent |
| `bugfix` | `/sprint-bugfix` |
| `notify.py`（脚本，非 skill）★ | `/sprint-autopilot`·`/sprint-aiauto-test` 里程碑通知（约定 32，渠道按 `memory/aidp-config.yaml` `notify.channels`）|
| `aidp-code-engineer` | 脚手架 init/migrate/upgrade |
| `superpowers:*`（tdd/debugging/verification）| `/sprint-dev`（tdd/verification）·`bugfix` SKILL（debugging）·`/sprint-batch`、`/sprint-test`、`/sprint-bugfix` 方式 B（verification）。并行开发由 AIDP 按写集隔离编排，不调用串行 `subagent-driven-development`；`executing-plans` 不用于零询问的 `/sprint-batch` 顶层循环 |

> 外部可选：`api-tester` 等（未装即跳过）；浏览器实测驱动 `chrome-devtools-mcp` 随仓库分发于 `各 Agent 的运行根/plugins/chrome-devtools-mcp/`：Claude Code 使用完整项目插件，Codex / DeepSeek Harness 共用 `.agents/skills/chrome-devtools-mcp/skills/`，MCP 分别写入 `.codex/config.toml` / `.dsh/mcp.json`（见 `各 Agent 的运行根/reference/skills.md`）。<!-- runtime-path-ignore: 适配位对照，必须逐字写出各 Agent 的目录 -->

## 初始化输入文件清单

> 完整的输入/产物路径清单（PRD / 研发需求 / 架构 / 设计 / 原型 / 部署资产 / 报告模板 / AI 报告目录等）见 **`{{AIDP_HOME}}/reference/初始化与文档索引.md`**（按需 Read）；路径权威 = `docs/init/06_版本与用户目录约定.md`。

## AIDP 范式文档索引

> AIDP 范式文档（`docs/init/00`~`06`）索引见 **`{{AIDP_HOME}}/reference/初始化与文档索引.md`**（按需 Read）；`06_版本与用户目录约定.md` 为路径权威。

---
