<!--
  {{project}} 项目记忆正文（AIDP 范式）。规范随脚手架升级；当前状态与项目自定义保留。
-->

# {{project}}

**{{project}}** 使用 AIDP 范式。项目背景见 `memory/projectBrief.md`；本文件只常驻身份分流、安全边界与项目状态。

## 会话入口与按需加载

- 普通自然语言开发/修复默认 **light**；仓库存在 active Sprint、任务复杂、文件多、复用 `/sprint-dev` 或 `/sprint-bugfix` 都不改变身份。明确 Sprint 或 `/version`、`/sprint-full`、`/sprint-batch`、`/sprint-autopilot` 才走 **formal**。
- **light 只读 `{{AIDP_HOME}}/reference/light-entry.md` 与受影响的 `rules/*.md`**；项目文件与基线按实际需要读取。不要预读完整动作协议、Sprint 流程、核心约定全文、角色/Skills 清单；不要创建或认领 Sprint、读取旧 activeContext 当作当前任务、生成正式归档。
- **formal 才读完整协议**：`{{AIDP_HOME}}/flows/sprint-dev/light-context.md`、`{{AIDP_HOME}}/reference/core-conventions.md`，再按 `{{AIDP_HOME}}/reference/task-routing.md` 读取选定命令/流程。正式 Sprint 才读 `memory/{version}/{user}/activeContext.md` 与 `progress.md`。
- 续跑、嵌套调用、子 Agent 继承父任务的 `--execution-context`、revision、action、budget、真实输入 hash 与写集，不从历史计划猜父任务。命令名、模板默认值、工具可用性都不是授权；formal 也不增加授权。
- 读当前版本与开发者身份；缺身份用 `python3 {{AIDP_HOME}}/scripts/vcs.py user` 解析。light 不要求先做版本规划；确需新版本落点时由用户决定。

## 执行授权与派发

- 普通开发/修复默认 implement + static + related-test，完成相关测试及必要修复复验后输出结果；用户明确只分析/只修改/skip 时遵守限制。额外审查、全量回归、实测、文档按请求执行，未请求项记 NOT_REQUESTED，不算 PASS 或欠账。
- 不擅自启动前后端服务、不执行完整打包构建；两项分别须用户明确要求。默认静态验证和当前任务相关测试。已有文件只修本次引入的问题，格式化 autofix 仅用于本次新建文件。
- 提交、推送、发布、部署、破坏性/不可逆写与 DB 操作保留各自授权边界。生产/UAT 凭据不明文入库；实际凭据使用私有文件或环境变量，日志必须脱敏。未知的数据写权限按只读处理。
- 用户要求“提交推送并部署”默认仅做 git commit、git push、项目现有部署脚本；不为此新建任务上下文、记录、备份或部署后核验。每次 commit 前运行 `python3 {{AIDP_HOME}}/scripts/commit_gate.py --quiet` 并读取 JSON；欠账退出码 3/4 不阻止 commit，按实际成因处理，不借机扩大任务。
- 无 Git 可开发、显式文件本地测试和本地归档；自动范围/证据链需有效 commit，记 `UNVERIFIED / unsupported:vcs-disabled`，不称完整闭环或发布，不自动 `git init`。失败、跳过、环境不可用如实区分，同输入工具失败不空转。
- 先读既有设计/代码再实现，架构、数据库、接口约束持续适用；引入实质变更只在实际受影响的族记增量，不建空册或替代审批文档。用户显式需求与分支选择不能被外部 SKILL 默认流程覆盖。

## 工作分支偏好

最外层修改前读取 `python3 {{AIDP_HOME}}/scripts/aidp_config.py branch-policy`。Git 项目未选择时只询问一次“直接当前分支 / 每个独立任务新建分支”，保存到 `memory/aidp-config.yaml` 的 `development.branch_policy`；无 Git 不询问。`current` 包括 main/master；`new` 只在任务开始创建一次。嵌套、子 Agent、复验和续跑共用分支，不自行建 worktree。未选择的无人值守任务返回配置缺失。完整处理见 `{{AIDP_HOME}}/reference/agent-tools.md`。

## 语言与沟通偏好

- 开发者母语**中文**；反馈、解释、计划、总结、追问、报告与错误说明优先中文。
- 代码、命令、日志、API 字段、配置键、SQL、第三方专有名词保持原文。

## 当前状态

> 此区域由 `/memory-sync`、`/version`、`/sprint-*` 定点更新，只写状态短行与证据链接。「整体进度」至多最近 2 个 Sprint 摘要，早期记录先移交 `progress.md`，不删历史关闭证据或未决项。

- **当前版本**：{{version}}
- **当前开发者**：{{user}}
- **当前 Sprint**：无活跃 Sprint（项目初始化阶段）
- **Sprint 目标**：-
- **整体进度**：0%（版本规划待启动）
- **最后更新**：{{date}}

---

## 核心约定与运行目录

核心约定 1–41 完整正文及稳定编号只维护于 `{{AIDP_HOME}}/reference/core-conventions.md`；细则仍在它指向的 rules/reference 文件。formal 读完整协议；light 不因「必须遵守」字样加载完整协议，代码规则按受影响文件读取：通用 `rules/code.md`、前端 `rules/frontend.md`、后端 `rules/backend.md`。

运行真源为 `{{AIDP_HOME}}/`。仅 Claude Code 使用 `.claude/`；Codex / DeepSeek Harness（含并存）使用 `.agents/`，Claude Code 读取装配副本。命令在 `commands/`、技能在 `skills/`，适配入口由 `agent_sync.py` 生成，不手改生成物。项目记忆落点通过 `agent_env.py memory-file` 查询；并存时 `AGENTS.md` 为正文、`CLAUDE.md` 为 `@AGENTS.md` 薄壳。 <!-- runtime-path-ignore: 适配位对照，必须逐字写出各 Agent 的目录 -->

完整命令/意图/角色/Skills 路由见 `{{AIDP_HOME}}/reference/task-routing.md`；工具适配与目录所有权见 `{{AIDP_HOME}}/reference/agent-tools.md`；初始化输入与范式文档索引见 `{{AIDP_HOME}}/reference/初始化与文档索引.md`。这些都是按需入口，不是会话必读清单。正式派角色前先读 `{{AIDP_HOME}}/agents/README.md`，角色文件不是原生 `subagent_type`。

## 项目自定义

<!-- AIDP:PROJECT-CUSTOM 本段由项目团队维护：项目特有的约定、命令、注意事项写在这里；脚手架升级时原样保留。与上方 AIDP 约定冲突时以 AIDP 约定为准。 -->
