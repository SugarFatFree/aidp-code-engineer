# Agent 工具名映射

> AIDP 的命令、流程分片、角色文件以 Claude Code 的工具名书写（它们最具体、最容易检索）。
> 在 Codex 或 DeepSeek Harness 下执行时，按本表换成等价能力——**语义不变，只换手段**。
> 当前 Agent 由 `python3 .aidp/scripts/agent_env.py detect` 判定。

## 一、判定与记忆文件

| 项 | Claude Code | Codex | DeepSeek Harness |
|----|-------------|-------|------------------|
| 判定依据（项目根） | `.claude/` | `.codex/` | `.dsh/` |
| 项目记忆文件 | `CLAUDE.md`（与其他 Agent 并存时为 `@AGENTS.md` 薄壳） | `AGENTS.md` | `AGENTS.md` |
| SKILL 目录 | `.claude/skills/` | `.agents/skills/` | `.agents/skills/`（与 Codex 共用） |
| AIDP 命令入口 | `/sprint-dev …`（`.claude/commands/`） | `$sprint-dev …`（`.codex/skills/aidp/`，仅显式调用） | `/sprint-dev …`（`.dsh/commands/`） |
| 插件（`.aidp/plugins/`） | `.claude/plugins/<name>/` + settings 登记 marketplace 并启用 | 插件 SKILL 位于 `.codex/skills/<name>/skills/`，MCP 合并到 `.codex/config.toml` | 插件 SKILL 位于 `.agents/skills/`，MCP 汇总到 `.dsh/mcp.json` |
| Stop hook | `.claude/settings.json` | `.codex/hooks.json`（`config.toml` 需 `codex_hooks = true`） | `.dsh/hooks.json`，由 hooks 插件加载 |

入口全部由 `python3 .aidp/scripts/agent_sync.py` 生成（不入库，登记在 `.gitignore` 托管块）；命令只在 `.aidp/commands/`、公共 SKILL 只在 `.aidp/skills/`、插件只在 `.aidp/plugins/`。Codex 命令位于官方发现根 `.codex/skills/aidp/`，带 `disable-model-invocation: true` 与 `agents/openai.yaml` 的 `allow_implicit_invocation: false`。其正文明确串联 `/foo args` 时，读取 `.aidp/commands/foo.md`，把 `args` 原样作为 `$ARGUMENTS` 内联执行；未知命令或无法唯一映射时 fail closed。`AIDP_AGENT=codex,claude` 环境变量可覆盖自动判定。

## 二、工具名

| 文中写法 | 语义 | Codex / DeepSeek Harness 下的做法 |
|---------|------|-----------------------------------|
| `Read` / `Write` / `Edit` / `Glob` / `Grep` | 读写与检索文件 | 使用当前 Agent 的文件读写与检索工具，或等价 shell 命令 |
| `Bash` | 执行 shell 命令 | 使用当前 Agent 的 shell 执行工具 |
| `Skill` 工具调用 `<name>` | 加载并执行一个 SKILL | 按名称调用同名 SKILL；无法调用时直接读 SKILL 目录下的 `SKILL.md` 并按其执行 |
| `AskUserQuestion` | 向人发起选择题并等待回答 | 以编号选项的形式直接向用户提问并等待回复；**无人值守（`--unattended`）下一律不提问**，按命令文档给出的默认决策继续 |
| `Agent`（子 Agent，含 `run_in_background`） | 在隔离上下文里执行一段既定工作 | 使用当前 Agent 的子 Agent / 并行任务能力；不支持时在主会话内**按同一份 prompt 顺序执行**，并在完成摘要里说明上下文代价（约定 36 降级阶梯）。⛔ 不支持子 Agent 不是跳过质量门的理由 |
| `TodoWrite` / 任务清单 | 跟踪多步骤进度 | 使用当前 Agent 的计划/清单能力；没有则在回复里维护一份 Markdown 清单 |
| `WebFetch` / `WebSearch` | 联网读取 | 使用当前 Agent 的联网能力；不可用时记为「未取到」，⛔ 不编造 |
| `$ARGUMENTS` | 命令参数 | 调用当前 Agent 的命令入口时附带的文字 |
| `$CLAUDE_PROJECT_DIR` | 项目根目录 | `git rev-parse --show-toplevel` |
| chrome-devtools MCP 工具（`mcp__chrome-devtools__*`） | 浏览器自动化 | 插件 `.aidp/plugins/chrome-devtools-mcp/` 由 `agent_sync.py` 为各 Agent 装配后使用同名工具（Claude Code 插件形态工具名为 `mcp__plugin_chrome-devtools-mcp_chrome-devtools__*`）|

## 三、7×24 无人值守（操作系统调度为主）

两条链路（开发链路 `sprint-autopilot` + 测试链路 `sprint-aiauto-test`）必须**同时**运行才是完整的开发 + 测试闭环；二者通过 `memory/.sprint-autopilot-baseline.json` 交接，与使用哪个 Agent 无关。

**推荐形态 = 操作系统调度双进程**（三种 Agent 通用）：

```bash
python3 .aidp/scripts/aidp_scheduler.py install [--agent claude|codex|dsh] [--dev-interval 10m] [--test-interval 5m]
python3 .aidp/scripts/aidp_scheduler.py status       # 定时任务是否已装 + 两条链路心跳
python3 .aidp/scripts/aidp_scheduler.py uninstall
```

- 为两条链路各装一个用户级定时任务（Linux：systemd --user timer，无 systemd 用户实例时用 crontab；macOS：launchd；Windows：输出 `schtasks` 命令手工执行），每个任务调用 `.aidp/scripts/agent_loop.sh --once <命令> --unattended`。两条链路是两个独立进程，互不阻塞。
- `agent_loop.sh` 每轮：自动补 `--unattended --no-loop`；导出 `AIDP_TICK_COMMAND=<命令>`（Stop 护栏据此只拦 autopilot tick）与 `ARGUMENTS`；flock 互斥（上一轮未结束则跳过）；加载可选的 `~/.config/aidp/env`（通知 webhook、CICD 令牌等凭据环境变量写这里，不进仓库、不进定时任务定义）；日志落 `memory/.aidp/logs/<命令>.log`；开跑前执行 `aidp_scheduler.py watchdog`——任一链路超过 `scheduler.stale_cycles × 周期` 无心跳（且未在执行中）即写本地告警台账 `memory/.aidp/alerts.jsonl` 并发里程碑通知。
- 周期、Agent、执行命令模板取 `memory/aidp-config.yaml` 的 `scheduler` 段；Linux 注销后仍要运行需执行一次 `loginctl enable-linger "$USER"`。

**各 Agent 的非交互执行前置**（执行命令模板优先级：`AIDP_AGENT_EXEC` 环境变量 > `scheduler.exec.<agent>` > 内置默认；⚠️ 各 CLI 参数以所用版本官方文档为准）：

| Agent | 提示词 | 内置默认执行命令 | 必须的前置 |
|-------|--------|------------------|-----------|
| Claude Code | `/sprint-autopilot --unattended --no-loop` | `claude -p --permission-mode acceptEdits {prompt}` | headless 模式下未预授权的工具调用会被拒绝：在 `.claude/settings.json` 的 `permissions.allow` 放行命令所需的 `Bash` / `Agent` / MCP 工具等；或自行改用更宽的权限模式（放宽权限的取舍由项目负责人决定）|
| Codex | `$sprint-autopilot --unattended --no-loop` | `codex exec --sandbox workspace-write {prompt}` | 需可写工作区沙箱才能改文件、提交；推送与访问 CICD 需网络权限（按 Codex 沙箱配置放行）；项目须被 Codex 标记为受信任（trust）才会加载 `.codex/hooks.json`（Stop 护栏）与 `.codex/config.toml` 中的 MCP 配置 |
| DeepSeek Harness | `/sprint-autopilot --unattended --no-loop` | 无内置默认 | 在 `scheduler.exec.dsh`（或 `AIDP_AGENT_EXEC`）填入 DSH 的非交互执行命令，写法按 DSH 当前版本官方文档确认；init 会尝试安装 `dsh-plugin-commands@latest`；`.dsh/hooks.json` 由 hooks 插件加载、`.dsh/mcp.json` 需在 DSH 的 MCP 配置中启用 |

**Claude Code 会话内 `/loop`（交互式短期用法）**：

```text
/loop 10m /sprint-autopilot --unattended
/loop 5m  /sprint-aiauto-test --unattended
```

`/loop` 是**会话级**定时任务：会话关闭即停；定时任务 **7 天后自动过期**；只在会话空闲的轮次之间触发，同一会话里挂两条时**实际串行**（长 tick 期间另一条被推迟）。适合临时观察、演示；7×24 用上面的操作系统调度。
