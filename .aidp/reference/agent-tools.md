# Agent 工具名映射

> AIDP 的命令、流程分片、角色文件以 Claude Code 的工具名书写（它们最具体、最容易检索）。
> 在 Codex 或 DeepSeek Harness 下执行时，按本表换成等价能力——**语义不变，只换手段**。
> 当前 Agent 由 `python3 {{AIDP_HOME}}/scripts/agent_env.py detect` 判定。

## 一、判定与记忆文件

| 项 | Claude Code | Codex | DeepSeek Harness |
|----|-------------|-------|------------------|
| 判定依据（项目根） | `.claude/` | `.codex/` | `.dsh/` |  <!-- runtime-path-ignore: 指 Agent 自身目录这一概念，非运行契约路径，两包均保持原样 -->
| 运行契约真源 | 当前 Agent 的 `{{AIDP_HOME}}/` 渲染副本 | 当前 Agent 的 `{{AIDP_HOME}}/` 共享运行包 | 当前 Agent 的 `{{AIDP_HOME}}/` 共享运行包 |
| 项目记忆文件 | `CLAUDE.md`（与其他 Agent 并存时为 `@AGENTS.md` 薄壳） | `AGENTS.md` | `AGENTS.md` |
| SKILL 目录 | `.claude/skills/` | `.agents/skills/` | `.agents/skills/`（与 Codex 共用） |<!-- runtime-path-ignore: 适配位对照，必须逐字写出各 Agent 的目录 -->
| AIDP 命令入口 | `/sprint-dev …`（`.claude/commands/`） | `$sprint-dev …`（`.codex/skills/aidp/`，仅显式调用） | `/sprint-dev …`（`.dsh/commands/`） |<!-- runtime-path-ignore: 适配位对照，必须逐字写出各 Agent 的目录 -->
| 插件（`各 Agent 的运行根/plugins/`） | `.claude/plugins/<name>/` + settings 登记 marketplace 并启用 | 嵌套 SKILL 位于 `.agents/skills/<name>/skills/`，MCP 合并到 `.codex/config.toml` | 嵌套 SKILL 与 Codex 共用 `.agents/skills/<name>/skills/`，MCP 汇总到 `.dsh/mcp.json` |<!-- runtime-path-ignore: 适配位对照，必须逐字写出各 Agent 的目录 -->
| Stop hook | `.claude/settings.json` | `.codex/hooks.json`（`config.toml` 需 `codex_hooks = true`） | `.dsh/hooks.json`，由 hooks 插件加载 |
| PreToolUse hook | `.claude/settings.json`（`hooks.PreToolUse`） | `.codex/hooks.json`（`hooks.PreToolUse`，同上开关） | **未证实，不装配**——见第五节替代手段 |

模板仓库的 `.aidp` 仅供维护，下游根目录没有该源码目录；以下 `{{AIDP_HOME}}` 是安装后解析的运行目录。**生成入口**由 `python3 {{AIDP_HOME}}/scripts/agent_sync.py` 生成（不入库，登记在 `.gitignore` 托管块）；⛔ 与运行真源**同址**的那些不算生成入口——运行根降层后 Claude Code 的 `commands/` `skills/` `plugins/` 就是契约本体、必须入库，`agent_sync.py` 判定 identity 后整体跳过它们；命令只在 `{{AIDP_HOME}}/commands/`、公共 SKILL 只在 `{{AIDP_HOME}}/skills/`、插件只在 `{{AIDP_HOME}}/plugins/`。Codex 命令位于官方发现根 `.codex/skills/aidp/`，带 `disable-model-invocation: true` 与 `agents/openai.yaml` 的 `allow_implicit_invocation: false`。该入口**不内联命令正文**，只声明「第一动作 = Read `{{AIDP_HOME}}/commands/<命令>.md`」；正文明确串联 `/foo args` 时同法读取 `{{AIDP_HOME}}/commands/foo.md`，把 `args` 原样作为 `$ARGUMENTS` 内联执行；未知命令或无法唯一映射时 fail closed。`AIDP_AGENT=codex,claude` 环境变量可覆盖自动判定。

### 执行策略

工具可用性不代表任务授权。开发/测试派发与脚本先执行 `{{AIDP_HOME}}/flows/sprint-dev/light-context.md` 围栏；子Agent继承父action/budget/真实inputs hash，缺源旧配置不作grant。普通提交/推送/部署按用户真实请求执行既有入口，不为交付创建 context/grant/回执文件；普通 push 按约定31.5独立只读观察，CICD none/有效流水线为空不观察，启用时不需 version/context、不写 baseline。autopilot 自有交付仍继承父授权及预算。调度安装另需用户明确授权。

### rules 路径限定加载：仅 Claude Code 原生成立

`{{AIDP_HOME}}/rules/*.md` 顶部的 `paths:` frontmatter 由 **Claude Code** 原生解释：编辑匹配路径的文件时才把该规则全文装入上下文。**Codex / DeepSeek Harness 没有对应的路径触发加载机制**，`agent_sync.py` 也不为 rules 生成指针或加载器（它只生成命令入口、SKILL / 插件装配与 Stop hook），规则文件仅作为共享运行包里的普通文件存在。因此在这两类 Agent 下，**执行体须在编辑对应路径的代码前显式 Read 对应规则**（语义不变，只换成手动触发）：

| 将要编辑的路径 | 先 Read |
|---|---|
| `code/frontend/**`、`code/web/**`、`web/**` | `{{AIDP_HOME}}/rules/frontend.md` + `{{AIDP_HOME}}/rules/code.md` |
| `code/backend/**`、`code/server/**`、`server/**` | `{{AIDP_HOME}}/rules/backend.md` + `{{AIDP_HOME}}/rules/code.md` |
| 其余 `code/**` | `{{AIDP_HOME}}/rules/code.md` |

已启用的可选规则（如 `client-mcp.md`、`webmcp.md`）同理按其 frontmatter 的 `paths:` 手动 Read。派发子 Agent 编码时，派单简报同样要求其先读上表对应规则。

## 二、工具名与工作分支偏好

| 文中写法 | 语义 | Codex / DeepSeek Harness 下的做法 |
|---------|------|-----------------------------------|
| `Read` / `Write` / `Edit` / `Glob` / `Grep` | 读写与检索文件 | 使用当前 Agent 的文件读写与检索工具，或等价 shell 命令 |
| `Bash` | 执行 shell 命令 | 使用当前 Agent 的 shell 执行工具 |
| `Skill` 工具调用 `<name>` | 加载并执行一个 SKILL | 按名称调用同名 SKILL；无法调用时直接读 SKILL 目录下的 `SKILL.md` 并按其执行 |
| `AskUserQuestion` | 向人发起选择题并等待回答 | 以编号选项的形式直接向用户提问并等待回复；**无人值守（`--unattended`）下一律不提问**，按命令文档给出的默认决策继续 |
| `Agent`（子 Agent，含 `run_in_background`） | 在隔离上下文里执行一段既定工作 | 在父action/budget内使用宿主允许的子Agent能力；无法派发时保留原因，可内联同授权工作，不自动增加审查或任务 |
| `TodoWrite` / 任务清单 | 跟踪多步骤进度 | 使用当前 Agent 的计划/清单能力；没有则在回复里维护一份 Markdown 清单 |
| `WebFetch` / `WebSearch` | 联网读取 | 使用当前 Agent 的联网能力；不可用时记为「未取到」，⛔ 不编造 |
| `$ARGUMENTS` | 命令参数 | 调用当前 Agent 的命令入口时附带的文字 |
| `$CLAUDE_PROJECT_DIR` | 项目根目录 | 优先用宿主提供的项目根变量；有 Git 时可用 `git rev-parse --show-toplevel`，非 Git 时从当前工作目录解析项目根 |
| chrome-devtools MCP 工具（`mcp__chrome-devtools__*`） | 浏览器自动化 | 插件 `{{AIDP_HOME}}/plugins/chrome-devtools-mcp/` 由 `agent_sync.py` 为各 Agent 装配后使用同名工具（Claude Code 插件形态工具名为 `mcp__plugin_chrome-devtools-mcp_chrome-devtools__*`）|

### 工作分支：首次选择、项目内沿用

需求修改、漏洞修复、自然语言直接改码与外部 SKILL 都遵守同一偏好。**修改前**由最外层执行体读取：

```bash
python3 {{AIDP_HOME}}/scripts/aidp_config.py branch-policy
```

- Git 项目 `needs_choice=true`（exit 3）且没有用户明确选择或既有项目指令可沿用 → 主流程只问一次固定两项：① **直接修改当前分支**；② **每个独立任务新建工作分支**。得到明确答复后才保存，未答复不取默认值。已设置 `current` / `new` 后直接沿用，不因换 Sprint、命令、Agent、会话或升级重复询问。用户主动修改偏好时才更新。
- 保存选择：`python3 {{AIDP_HOME}}/scripts/aidp_config.py set development.branch_policy current` 或将末值换为 `new`。只有真实选择才写入；文件损坏/非法值（exit 2）应修复，不得当作缺省重置。项目选择存在 `memory/aidp-config.yaml`，不另写第二份个人记忆取代它。
- 无 Git → `not-applicable`，不问、不建仓。无人值守/子 Agent 不自行代选：优先继承父任务已核实的策略与分支；缺选择则返回 `needs-choice`，父编排按已有配置缺失处置记录并停止修改，不能假填 `current` 或每 tick 弹窗。脚手架可先安装，业务修改必须等选择完成。

| 已选策略 | 修改行为 |
|---|---|
| `current` | 沿用任务开始时所在分支，包括 main/master；不自动新建、切换分支或 worktree。已在特性分支就沿用它，不自动退回主干。 |
| `new` | 最外层主流程在独立任务开始时创建一次分支，完成一次需求及其中的修复、复验均沿用。记录任务标识、起点与分支名到既有 activeContext/任务记录；续跑先核对该记录，子命令和子 Agent 继承，不按文件、BUG 或修复轮次重复创建。 |

创建前检查当前 HEAD、工作区与已有任务记录；脏树、detached HEAD、同名但归属不明或切换失败时停止分支动作并说明，不自动 stash/reset/丢改动、不从另一个任务分支继续派生。正常命名按任务用 `feat/<task>` 或 `fix/<task>`，先校验合法性；不得强制移动已有分支。用户本轮指定的分支/临时策略优先，只有用户要求“以后都这样”才改永久偏好。

派单简报传 `branch_policy`、`task_branch` 与任务标识。外部 Superpowers 的默认 worktree/功能分支/主分支限制不替代用户已选策略；创建 worktree 仍需单独授权。策略不授权 commit、push、合并、删分支或部署。autopilot 开发链在选定工作分支上持续推进、跨 tick 不另建；部署源对齐与 `/version` 发布分支是独立授权，不得拿部署源不一致当理由悄悄改项目偏好或切走当前分支。

## 三、7×24 无人值守（操作系统调度为主）

**非 Git 能力矩阵**：`vcs_mode=none` 可安装、规划、开发、按显式文件运行本地测试和本地归档；自动 `test_scope.py` / `light_task.py select/all` 需要有效 Git commit，无 Git 时自动范围及相关测试证据链记 `UNVERIFIED / unsupported:vcs-disabled`，不能宣称完整开发测试闭环。Git diff / commit / push / tag、基于 commit SHA 的 CICD 监听及正式发布不可用。不可用步骤标记 `unsupported:vcs-disabled` 或明确阻断，不得报告为通过或宣布已发布；脚手架不自动 `git init`。`/sprint-test` 的 CVL 改动前基线（`baseline_ref=none`）在非 Git 下无法取得：无人值守仅「基线依赖项」未核验时按 `unsupported:vcs-disabled` 降级放行并通知一次、不计失败，口径见 `commands/sprint-test.md`。

两条链路（开发链路 `sprint-autopilot` + 测试链路 `sprint-aiauto-test`）必须**同时**运行才是完整的开发 + 测试闭环；二者通过 `memory/.sprint-autopilot-baseline.json` 交接，与使用哪个 Agent 无关。

**推荐形态 = 操作系统调度双进程**（三种 Agent 通用）：

```bash
python3 {{AIDP_HOME}}/scripts/aidp_scheduler.py install [--agent claude|codex|dsh] [--dev-interval 10m] [--test-interval 5m]
python3 {{AIDP_HOME}}/scripts/aidp_scheduler.py status       # 定时任务是否已装 + 两条链路心跳
python3 {{AIDP_HOME}}/scripts/aidp_scheduler.py uninstall
```

- 为开发、测试链路各装一个用户级定时任务，并加装第三条独立 watchdog 巡检任务（Linux：systemd --user timer，无 systemd 用户实例时用 crontab；macOS：launchd；Windows：输出 `schtasks` 命令手工执行）。两条链路经 `{{AIDP_HOME}}/scripts/agent_loop.sh --once <命令> --unattended` 独立运行，watchdog 即使两者从未启动也能在宽限期后告警。
- `agent_loop.sh` 每轮：自动补 `--unattended --no-loop`；导出 `AIDP_TICK_COMMAND=<命令>`（Stop 护栏据此只拦 autopilot tick）与 `ARGUMENTS`；flock 互斥（上一轮未结束则跳过）；加载可选的 `~/.config/aidp/env`（通知 webhook、CICD 令牌等凭据环境变量写这里，不进仓库、不进定时任务定义）；日志落 `memory/.aidp/logs/<命令>.log`；开跑前执行 `aidp_scheduler.py watchdog`——任一链路超过 `scheduler.stale_cycles × 周期` 无心跳（且未在执行中）即写本地告警台账 `memory/.aidp/alerts.jsonl` 并发里程碑通知。
- 周期、Agent、执行命令模板取 `memory/aidp-config.yaml` 的 `scheduler` 段；Linux 注销后仍要运行需执行一次 `loginctl enable-linger "$USER"`。

**各 Agent 的非交互执行前置**（执行命令模板优先级：`AIDP_AGENT_EXEC` 环境变量 > `scheduler.exec.<agent>` > 内置默认；⚠️ 各 CLI 参数以所用版本官方文档为准）：

| Agent | 提示词 | 内置默认执行命令 | 必须的前置 |
|-------|--------|------------------|-----------|
| Claude Code | `/sprint-autopilot --unattended --no-loop` | `claude -p --permission-mode acceptEdits {prompt}` | headless 模式下未预授权的工具调用会被拒绝：在 `.claude/settings.json` 的 `permissions.allow` 放行命令所需的 `Bash` / `Agent` / MCP 工具等；或自行改用更宽的权限模式（放宽权限的取舍由项目负责人决定）|
| Codex | `$sprint-autopilot --unattended --no-loop` | `codex exec --sandbox workspace-write {prompt}` | 需可写工作区沙箱才能改文件、提交；推送与访问 CICD 需网络权限（按 Codex 沙箱配置放行）；项目须被 Codex 标记为受信任（trust）才会加载 `.codex/hooks.json`（Stop 护栏）与 `.codex/config.toml` 中的 MCP 配置 |
| DeepSeek Harness | `/sprint-autopilot --unattended --no-loop` | 无内置默认 | 在 `scheduler.exec.dsh`（或 `AIDP_AGENT_EXEC`）填入 DSH 的非交互执行命令，写法按 DSH 当前版本官方文档确认；init 会尝试安装 `github:SugarFatFree/dsh-agent-extension`；`.dsh/hooks.json` 由 hooks 扩展加载、`.dsh/mcp.json` 需在 DSH 的 MCP 配置中启用 |

**Claude Code 会话内 `/loop`（交互式短期用法）**：

```text
/loop 10m /sprint-autopilot --unattended --no-loop
/loop 5m  /sprint-aiauto-test --unattended --no-loop
```

`/loop` 是**会话级**定时任务：会话关闭即停；定时任务 **7 天后自动过期**；只在会话空闲的轮次之间触发，同一会话里挂两条时**实际串行**（长 tick 期间另一条被推迟）。适合临时观察、演示；7×24 用上面的操作系统调度。

### tick 占位收尾（两条链路共用）

直接调用与会话内 `/loop` 在 Phase 0 `begin` 取得持久占位，直到**整轮命令返回**才释放；占位跨 Bash 工具调用存在，不依赖短命 Python 的 fd 或进程猜测。OS tick 的整轮 flock 则由 `agent_loop.sh` 持有，Agent/后台服务不继承锁 fd。两种入口共享准入门，同一链路不得并发。

- `begin` / `parse` 输出的本轮 token 必须保留在当前执行上下文。重新解析参数时沿用 `--lock-token` 原值，不能重跑 begin 或从他人的锁记录取 token 接管。
- **所有返回路径**（正常完成、无变化、配置等待、失败、冻结、yield）在全部动作结束后、回复用户或返回父命令**之前**执行：`python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py finish --command autopilot --lock-token <本轮token>`；测试链路的 `--command` 改为 `aiauto-test`。占位取得失败时不释放；token 为 `agent_loop` 时由 wrapper 自动释放，不调用 finish。
- 不能在单个 Bash 的 `EXIT` trap 中提前释放，不能把 token 当 shell 跨工具持久变量。finish 失败必须报错，不能假称已释放。
- 中断遗留占位**不会超时自动释放**（原 tick 可能还在修改文件）；watchdog 对超期占位告警，包括尚无首次心跳的情况。确认原 tick 已停止后才用其原 token finish。**禁止删除锁文件**，否则旧 fd 与新 inode 会形成两把锁。
- 硬超时的每次退出都持久写 `alerts.jsonl` 和连续计数，连续达阈通知；两条链路的计数锁内更新。前台循环的单轮失败不终止守护。无 flock / timeout 时分别回退 Python fcntl / 超时执行器；没有互斥能力则拒绝执行。
- 安装预检只检查现有配置，不修改 `permissions`，不注入权限绕过开关。细粒度 allow 不能证明整轮 Bash/Agent/MCP 均被授权，需按项目实际工具核验。

## 四、Python 解释器（跨平台）

本仓库全部示例统一写 `python3`。**Windows 上通常没有 `python3` 这个名字**（只有 `python`，或 Windows 启动器 `py`），照抄会得到「不是内部或外部命令」。

**执行前先探测，取第一个可用的**：

```bash
# POSIX：python3 → python
command -v python3 >/dev/null && PY=python3 || PY=python
```

```powershell
# Windows PowerShell：python → py -3
$PY = if (Get-Command python -EA SilentlyContinue) { "python" } else { "py -3" }
```

然后把文档里的 `python3 …` 读作 `$PY …`。

- ⛔ **不要去改文档里的 `python3` 字面量**：它同时是 `check_cli_invocation.py` 的识别形状（现巡检数千处调用），改写等于把那道门连根拔掉。
- ✅ **脚本内部起子进程一律用 `sys.executable`**，不受本节影响——当前实现已全部如此，`aidp_scheduler.py` 生成的 systemd / cron / launchd / schtasks 四类定时任务也都由它派生。

## 五、PreToolUse hook：三端支持矩阵与替代手段

`{{AIDP_HOME}}/hooks/pretool-guard.py` 是单一 PreToolUse hook，做两项机器强制：**入口协议不可跳过**（改 `code/**` 前须已 `entry_context.py resolve` 且已读 `aidp_config.py branch-policy`，判定见 `scripts/entry_gate.py`）与**测试范围**（Bash 命令交 `scripts/test_command_guard.py`：无参 / 目录 / 全量测试命令、`git stash` 一律拒绝）。结论按官方文档查证（2026-11-12 核对），**未证实的不当作已支持**：

| 项 | Claude Code | Codex | DeepSeek Harness |
|----|-------------|-------|------------------|
| 支持 PreToolUse | ✅ 官方支持 | ✅ 官方支持（`hooks` 特性默认可用，`codex_hooks` 为已弃用别名，`agent_sync.py` 仍写入它以兼容旧版本） | ⚠️ **未证实**：未见 DSH 官方统一的 `.dsh/hooks.json` PreToolUse 契约；生态里有多个第三方 hooks 插件（Claude Code 方言桥接、Codex 方言桥接、自有 schema），配置文件位置与 schema 各不相同 |
| 配置位置 | `.claude/settings.json` → `hooks.PreToolUse[]` | `.codex/hooks.json`（或 `config.toml` 的 `[hooks]` 表）→ `hooks.PreToolUse[]` | 不装配（`agent_sync.py` 在输出 `notes` 说明） |
| matcher | 区分大小写的工具名正则 / `\|` 列表；本仓写 `Bash\|Edit\|Write\|MultiEdit\|NotebookEdit` | 工具名正则；Shell 命令按 `Bash`，文件编辑经 `apply_patch`，matcher 可写 `apply_patch` / `Edit` / `Write`；本仓兼容写 `Bash\|shell\|shell_command\|exec_command\|local_shell\|apply_patch\|Edit\|Write` | — |
| stdin JSON | `tool_name`、`tool_input`（Bash 为 `command`；Edit / Write / MultiEdit 为 `file_path`；NotebookEdit 为 `notebook_path`）、`cwd` | `tool_name`（`Bash` / `apply_patch` / MCP 名）、`tool_input.command`（Bash 可为字符串或 argv 数组；原生 shell 输入兼容 `cmd`、`workdir/cwd`；`apply_patch` 为补丁文本，hook 解析 `*** Add/Update/Delete File:`、`*** Move to:` 头取路径）、`cwd`、`turn_id` | — |
| 阻断协议 | `exit 2` + stderr，或 exit 0 + `hookSpecificOutput.permissionDecision="deny"` + `permissionDecisionReason`；deny 在 bypass 权限模式下同样生效 | 同左（另接受旧式 `{"decision":"block"}`）；`permissionDecision="ask"` **解析但不支持**，故无人值守下也不依赖它 | — |
| 项目根 | 注入 `CLAUDE_PROJECT_DIR` | 无项目根变量，hook 命令用 `${PWD}`，脚本回落 `cwd` / git 根 | — |
| 覆盖边界 | Edit 与可识别 Bash 写入统一入口校验；动态写目标拒绝并提示拆分。任意外部程序/脚本正文不做完整解释，不是安全沙箱 | 同左；官方明确托管工具、部分专用工具路径不触发 hook。项目级 hooks 须 **trust** 后才加载，新增或改动需在 `/hooks` 评审信任才运行 | — |

本 hook 使用 `exit 2` + stderr；`--agent codex` 额外输出 deny JSON。目标工具的坏输入、缺模块或内部失败均拒绝并记录 `decision: deny`，不把测试校验失败当成放行。

入口门由 `entry_guard.enabled` / `memory/.entry-guard-off` 控制；测试门由独立默认开启的 `test_guard.enabled` / `memory/.test-guard-off` 控制，关闭任何一门不影响另一门。旧 `memory/.pretool-guard-off` 仅兼容为入口关闭，迁移为 `.entry-guard-off` 后删除旧文件，恢复入口时亦须清除旧文件。

入口必须绑定当前任务：显式 `AIDP_EXECUTION_CONTEXT`，或 `entry_gate.py bind --execution-context ...` 写出的任务标记；不扫描其他 active context，错误指向不回退。校验根、身份、active 状态、新鲜期、implement 与 write_set；formal/tick 同样要求已读 branch-policy。宿主 `session_id` 存在时仅接受该 session 的绑定，提示会给出实际 `--session-id`；没有标识时通用任务标记仅支持串行项目任务，不宣称会话隔离。

Bash 解析覆盖常见 sed 原地写、输出重定向、tee、cp/mv/install/rm、cd/常量变量和可识别 bash/python `-c` 包装；纯读和入口 JSON 解析保持可用。窄兼容同一运行安装的 `autopilot_tick_flags.py --shell` 单个命令替换 eval 引导（可选 `--command autopilot|aiauto-test`），不执行脚本来推断安全、不泛化为任意 eval。固定元数据输出后的失败退出、只读 JSON 的 here-string 作为正常数据流处理，真正动态写入仍明确拒绝并提示先走入口、拆分命令。精确条件与迁移步骤见 `{{AIDP_HOME}}/hooks/README.md`。

### 不支持 / 未证实的端：替代手段（语义不变，只换手段）

hook 不可用时，这两项约束退回「命令入口 + 脚本强制」，不得因此跳过：

1. **测试范围**：一律经 `python3 {{AIDP_HOME}}/scripts/test_command_guard.py wrap -- <命令>`（或 `light_task.py` 单一入口，它内部走 wrap）执行测试 / ruff 等命令；先 `select_related_tests.py` 取相关测试白名单，只传显式文件。后台跑法用 `wrap --background --log FILE`，结束读 `FILE.exit`。需要「改动前基线对照」时用 `test_baseline.py` 的已知失败基线或 `git worktree`，⛔ 不用 `git stash`。
2. **入口协议**：命令正文已要求先 `entry_context.py resolve`、先读 `branch-policy`；hook 缺席的端上，改 `code/**` 之前执行体须先运行 `python3 {{AIDP_HOME}}/scripts/entry_gate.py check --root . --target <拟改文件>`，退出 2 就按提示补步骤，不得继续编辑。派发子 Agent 时把这条写进派单简报。
3. **兜底**：Stop hook（`autopilot-stop-guard.py`）与收尾核验（`entry_context.py check` / `complete`、`test_ledger.py`）在结束前核对证据；未走入口协议或超范围测试的产物在此处判缺，而不是静默通过。
4. **DeepSeek Harness 若装了某款 hooks 插件**：可由项目负责人按该插件文档自行把同一脚本接成 PreToolUse（仅在该插件明确兼容本脚本的 stdin 与 exit 2 协议后；没有验证则不宣称可用）；确认官方契约后再改 `agent_sync.py::PRETOOL_MATCHER` 纳入自动装配，未确认前保持不写。

### 查证来源

- Claude Code：Hooks reference（<https://code.claude.com/docs/en/hooks>）。本次抓取该页被网络阻断，PreToolUse 的 matcher / stdin 字段 / `exit 2` 与 `permissionDecision` 阻断协议、`CLAUDE_PROJECT_DIR` 取自对该页内容的检索摘要及社区引用实例（<https://dev.to/fewparts/how-to-stop-a-claude-code-agent-writing-outside-a-directory-253p>），升级 Claude Code 版本后以官方页为准复核。
- Codex：Hooks（<https://developers.openai.com/codex/hooks>），本次直接抓取并核对：PreToolUse 的 Tool coverage（Bash、`apply_patch`、MCP、其他本地函数工具；托管工具不覆盖）、matcher 别名、`tool_input.command`、deny / `exit 2` 协议、`ask` 未支持、`hooks` 特性键与 `codex_hooks` 弃用别名、项目 hooks 的 trust 要求。
- DeepSeek Harness：<https://github.com/SugarFatFree/dsh-agent-extension>（只含命令 / SKILL / 路径规则，无 hooks）；生态内第三方 hooks 插件与桥接信息仅来自搜索摘要（如 <https://github.com/JohnXu22786/hooks-adapter>），官方页面抓取被网络阻断，结论标「未证实」。
