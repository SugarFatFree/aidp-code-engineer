# aidp-code-engineer

> **AIDP（AI-Driven Iterative Development Paradigm）代码工程师模板** —— 一套通用、开源的"AI 驱动迭代开发"工程范式：
> **版本规划 → Sprint 执行 → 7×24 无人值守 autopilot → AI 自动化测试 → 发布归档**，全程由 AI 编码 Agent 按结构化文档与记忆系统推进。
>
> 兼容 **Claude Code**、**Codex**、**DeepSeek Harness**。

## ✨ 特性

- **文档驱动的版本规划**：`/version` 一次产齐研发需求、详细设计、执行计划、研发自测用例，并经独立审计后才开工。
- **Sprint 流水线**：`/sprint-batch` 一次跑完计划内全部 Sprint；`/sprint-dev`、`/sprint-bugfix` 处理增量功能与零散缺陷。
- **7×24 无人值守**：`/sprint-autopilot` 开发链路 + `/sprint-aiauto-test` 测试链路两条循环并行，监听 PRD → 规划 → 开发 → 部署 → 浏览器仿真测试 → 自动修复复测。
- **AI 自动化测试**：基于 chrome-devtools-mcp 驱动真实浏览器，登录、走查、断言、截图，产出不可变的测试报告。
- **AI 记忆系统**：`memory/` 分层记忆（项目级 / 版本级 / 用户级），跨会话延续上下文。
- **发布双轨基线**：发布时成对产出"增量升级"与"全量从零搭建"两套部署基线。
- **CICD 与通知**：可适配的 CICD 部署监听（默认 GitHub Actions，另支持 GitLab CI / Jenkins / 自定义命令）；里程碑通知推送到飞书 / 钉钉 / 企业微信。
- **提交前门禁**：`commit_gate.py` 在每次提交前检查文档级联台账与 CICD 推送欠账，防止"代码与文档两张皮"。

## 🚀 快速开始

### 1. 前置条件

- Git 可选；非 Git 目录也可 init / migrate / upgrade（不会自动 `git init`），但提交、推送、tag、CICD 与正式发布不可用。
- Python ≥ 3.9
- 任一 AI 编码 Agent：Claude Code / Codex / DeepSeek Harness
- 可选：[GitHub CLI `gh`](https://cli.github.com/)（CICD 监听与 Issue 读取）、Node.js（chrome-devtools-mcp）

### 2. 安装脚手架 skill

脚手架 skill `aidp-code-engineer` 位于本仓库 [`.aidp/skills/aidp-code-engineer/`](.aidp/skills/aidp-code-engineer/)。把它复制到目标项目中你所用 Agent 的 skills 目录：

```bash
git clone https://github.com/SugarFatFree/aidp-code-engineer.git
cd <你的项目>

# Claude Code
mkdir -p .claude/skills && cp -r ../aidp-code-engineer/.aidp/skills/aidp-code-engineer .claude/skills/

# Codex
mkdir -p .codex .agents/skills && cp -r ../aidp-code-engineer/.aidp/skills/aidp-code-engineer .agents/skills/

# DeepSeek Harness（与 Codex 共用 .agents/skills）
mkdir -p .dsh .agents/skills && cp -r ../aidp-code-engineer/.aidp/skills/aidp-code-engineer .agents/skills/
```

### 3. 初始化项目

在目标项目根目录启动 Agent，调用脚手架：

```text
/aidp-code-engineer init --version V0.1.0
```

脚手架还支持 `migrate`（已有项目改建）与 `upgrade`（旧版 AIDP 升级）。执行完成后会自动校验目录完整性；没有 Git 用户名时用 `--user NAME` 指定开发者标识，脚手架不会自动创建 Git 仓库。

### 4. Agent 判定与适配层

| Agent | 判定依据（项目根，可并存） | SKILL 入口 | AIDP 命令入口 | 项目记忆文件 |
|-------|---------|-----------|-------------|-------------|
| Claude Code | `.claude/`（都没有时缺省） | `.claude/skills/` | `.claude/commands/`，`/sprint-dev` | `CLAUDE.md` |
| Codex | `.codex/` | `.agents/skills/` | `.codex/skills/aidp/`，`$sprint-dev` | `AGENTS.md` |
| DeepSeek Harness | `.dsh/` | `.agents/skills/` | `.dsh/commands/`，`/sprint-dev` | `AGENTS.md` |

- 可用环境变量 `AIDP_AGENT=claude|codex|dsh` 显式覆盖自动判定。
- 本模板仓库的 `.aidp/` **仅是维护源**，不在下游项目根创建 `.aidp/`。下游仅 Claude Code 时运行真源为 `.claude/aidp/`；使用 Codex 或 DeepSeek Harness（含多 Agent 并存）时共享真源为 `.agents/aidp/`，Claude Code 从 `.claude/aidp/` 读取装配副本。下发契约中的 `{{AIDP_HOME}}` 在安装时渲染为运行路径。
- **命令与 SKILL 在源头分开**：AIDP 命令只在 `{{AIDP_HOME}}/commands/`，公共 SKILL 契约只在 `{{AIDP_HOME}}/skills/`，模板仓库对应目录位于 `.aidp/`。`agent_sync.py` 分别生成 Claude Code 命令文件、Codex 官方发现根 `.codex/skills/aidp/` 下的显式调用命令 SKILL、DeepSeek Harness 命令文件；命令参数正文保持 `$ARGUMENTS` 语义不变。Codex 命令正文明确串联 `/foo args` 时，确定性读取 `{{AIDP_HOME}}/commands/foo.md` 并把 `args` 原样传为子命令 `$ARGUMENTS`，未知命令 fail closed。
- **插件**：模板 `.aidp/plugins/` 随仓库分发浏览器插件（内置 `chrome-devtools-mcp`：浏览器自动化 MCP + 配套调试 SKILL，Apache-2.0）。Claude Code 以项目级插件启用，MCP 工具名使用插件命名空间 `mcp__plugin_chrome-devtools-mcp_chrome-devtools__*`；Codex / DeepSeek Harness 的插件 SKILL 共用 `.agents/skills/chrome-devtools-mcp/skills/`；MCP 分别写入 `.codex/config.toml`、`.dsh/mcp.json`。
- **适配入口不入库**：`.claude/commands|skills|plugins`、`.codex/skills/aidp`、`.codex/skills`、`.dsh/commands`、`.agents/skills` 下的生成入口由 `python3 {{AIDP_HOME}}/scripts/agent_sync.py` 维护并自动写入 `.gitignore` 托管块；clone 后先跑一次该命令（脚手架 init / migrate / upgrade 会自动执行）。
- 同时使用多种 Agent 时，`AGENTS.md` 为正文，`CLAUDE.md` 仅引用它（`@AGENTS.md`）。模板仓库查询记忆文件用 `python3 .aidp/scripts/agent_env.py memory-file`；下游改用 `python3 {{AIDP_HOME}}/scripts/agent_env.py memory-file`。

**非 Git 能力边界**：`vcs_mode=none` 时仍可安装运行契约、规划、开发、本地测试及本地归档；Git diff / commit / push / tag 与依赖 commit SHA 的 CICD 监听均不适用，不能以跳过这些步骤冒充发布成功。需要正式发布时先由项目负责人明确建立并配置 Git 仓库，再复核发布门禁；脚手架不会自动 `git init`。

## 📦 目录结构

```
<project>/
├── {{AIDP_HOME}}/        # 运行真源：仅 Claude → .claude/aidp；有 Codex / DSH → .agents/aidp
│   ├── commands/          #   命令定义（/version、/sprint-* 等）
│   ├── agents/            #   角色 Agent（architect / frontend / backend / qa / ui …）
│   ├── flows/             #   命令分片流程
│   ├── rules/ reference/  #   规则与约定细则
│   ├── skills/            #   Skills（含脚手架 aidp-code-engineer）
│   ├── scripts/           #   确定性脚本（commit_gate / cicd_watch / notify / baseline_edit …）
│   ├── hooks/             #   Hook（autopilot Stop 护栏）
│   └── templates/         #   报告 / 部署模板
├── docs/                  # 文档体系（需求 / 设计 / 计划 / 测试 / 原型 / 部署 / 报告 / 审计 …）
│   └── init/              #   AIDP 范式文档 00~06
├── memory/                # AI 记忆系统 + 项目配置 aidp-config.yaml
├── code/                  # 业务代码（code/frontend/{子项目}、code/backend/{子项目}）
├── .github/               # GitHub Actions 工作流（使用其他 CICD 平台时按平台约定放置流水线定义）
├── AGENTS.md              # 项目记忆文件（Claude Code 下为 CLAUDE.md）
└── README.md
```

文档体系逐目录说明见 [docs/README.md](docs/README.md)，路径权威见 [docs/init/06_版本与用户目录约定.md](docs/init/06_版本与用户目录约定.md)。

## 🧭 命令一览

| 类别 | 命令 | 说明 |
|------|------|------|
| 初始化 | `/sprint-init` · `/sprint-init-design` · `/sprint-init-complete` | 项目初始化、初始设计、初始化收尾 |
| 版本规划 | `/version V0.1.0 "M1"` | 串联 `/sprint-requirements` → `/sprint-design` → `/sprint-plan` → `/sprint-selftest`，并负责发布 |
| Sprint 执行 | `/sprint-batch` | 一次跑完执行计划内全部 Sprint（末段部署 + AI 测试） |
| | `/sprint-full NNN` | 单 Sprint 一条龙 |
| | `/sprint-start` · `/sprint-dev` · `/sprint-test` · `/sprint-close` | 分步执行 |
| 增量 | `/sprint-dev "<描述>"` · `/sprint-bugfix ["<描述>"]` | 新增功能 / 修复缺陷 |
| 7×24 | `python3 {{AIDP_HOME}}/scripts/aidp_scheduler.py install`（调度 `/sprint-autopilot` + `/sprint-aiauto-test`）| 全自动开发链路 / 全自动测试链路 |
| 辅助 | `/memory-sync` · `/health-check` | 记忆同步 / 项目体检 |

> 下表以 Claude Code / DeepSeek Harness 的 `/命令` 写法展示；Codex 使用同名 `$命令`（例如 `$sprint-dev`）。完整用法见 [docs/init/05_commands详细规范.md](docs/init/05_commands详细规范.md)。

## 🌙 7×24 无人值守

开发链路（`/sprint-autopilot`）与测试链路（`/sprint-aiauto-test`）**必须同时运行**才是完整闭环，二者通过 `memory/.sprint-autopilot-baseline.json` 共享版本状态。首次直接调用任一命令会进入配置向导。

**推荐：操作系统调度**（Claude Code / Codex / DeepSeek Harness 通用）：

```bash
python3 {{AIDP_HOME}}/scripts/aidp_scheduler.py install [--agent claude|codex|dsh]   # 两条链路各装一个用户级定时任务（默认 10m / 5m）
python3 {{AIDP_HOME}}/scripts/aidp_scheduler.py status                               # 定时任务 + 两条链路心跳
python3 {{AIDP_HOME}}/scripts/aidp_scheduler.py uninstall
```

- Linux 用 systemd --user timer（无 systemd 时 crontab）、macOS 用 launchd、Windows 输出 `schtasks` 命令；每个任务调用 `{{AIDP_HOME}}/scripts/agent_loop.sh --once <命令> --unattended`，自动补 `--no-loop`、flock 互斥、日志落 `memory/.aidp/logs/`。
- Codex 以 `$sprint-autopilot …` 调用命令，DeepSeek Harness 以 `/sprint-autopilot …` 调用；DeepSeek Harness 的非交互执行命令需在 `memory/aidp-config.yaml` 的 `scheduler.exec.dsh` 配置。
- 任一链路心跳中断、任何冻结都会写本地告警台账 `memory/.aidp/alerts.jsonl`，配置了通知渠道时同时推送。
- 非交互执行需预授权工具权限，详见 [`.aidp/reference/agent-tools.md`](.aidp/reference/agent-tools.md) 第三节。

**Claude Code 会话内短期使用**（会话级：关闭即停、7 天过期、空闲才触发、同会话两条串行）：

```text
/loop 10m /sprint-autopilot --unattended
/loop 5m  /sprint-aiauto-test --unattended
```

## 🔔 通知渠道

里程碑通知由 `{{AIDP_HOME}}/scripts/notify.py` 发送，在 `memory/aidp-config.yaml` 的 `notify` 段配置，按顺序尝试、成功即停：

```yaml
notify:
  enabled: true
  fallback: true
  channels:
    - {type: feishu,   webhook_env: AIDP_FEISHU_WEBHOOK,   secret_env: AIDP_FEISHU_SECRET}    # 飞书自定义机器人
    - {type: dingtalk, webhook_env: AIDP_DINGTALK_WEBHOOK, secret_env: AIDP_DINGTALK_SECRET}  # 钉钉机器人
    - {type: wecom,    webhook_env: AIDP_WECOM_WEBHOOK}                                       # 企业微信机器人
```

- 还支持 `lark-cli`（飞书 CLI）与 `command`（自定义命令，从 stdin 读取 JSON）。
- ⛔ webhook 地址与密钥只经环境变量引用，**不要明文写入仓库**。
- 未配置任何渠道时播报节点静默跳过，不阻断链路。

## ⚙️ CICD（多提供方，默认 GitHub Actions）

推送正式代码后，由 `{{AIDP_HOME}}/scripts/cicd_watch.py` 按 commit 锁定本次流水线运行、轮询至终态、失败自动重试（上限 `max_retries`），再跑部署就绪探针。平台差异收在 `{{AIDP_HOME}}/scripts/cicd_providers.py`，在 `memory/aidp-config.yaml` 的 `cicd` 段选择提供方：

| `provider` | 平台 | `pipelines.<env>` 的含义 | 依赖 / 凭据 |
|------|------|------|------|
| `github-actions`（默认） | GitHub Actions | workflow 文件名（如 `deploy-test.yml`） | `gh` CLI 已登录 |
| `gitlab-ci` | GitLab CI/CD（含自建） | 分支名（可留空） | `cicd.gitlab-ci.url` / `project`，令牌经 `token_env` |
| `jenkins` | Jenkins | Job 路径（如 `team/deploy-test`） | `cicd.jenkins.url`，账号 / API Token 经 `user_env` / `token_env` |
| `command` | 任意平台（Gitee、Gitea、自建平台等） | 原样代入命令模板的 `{pipeline}` | `cicd.command.<动作>` 命令模板 |
| `none` | 不接入 CICD | — | — |

**GitHub Actions（默认）**

```yaml
cicd:
  provider: github-actions
  auto_trigger: true      # 无人值守下允许自动触发 / 重试
  max_retries: 3
  pipelines:
    dev: deploy-dev.yml
    test: deploy-test.yml
```

**GitLab CI**

```yaml
cicd:
  provider: gitlab-ci
  pipelines:
    test: develop         # 触发与过滤用的分支名；留空 = 不按分支过滤
  gitlab-ci:
    url: https://gitlab.example.com
    project: group/name
    token_env: AIDP_GITLAB_TOKEN
```

**Jenkins**

```yaml
cicd:
  provider: jenkins
  pipelines:
    test: team/deploy-test
  jenkins:
    url: https://jenkins.example.com
    user_env: AIDP_JENKINS_USER
    token_env: AIDP_JENKINS_TOKEN
```

**自定义命令（任意平台）**

```yaml
cicd:
  provider: command
  pipelines:
    test: deploy-test
  command:
    check: "mycli whoami"
    list: "mycli runs --pipeline {pipeline} --commit {commit} --limit {limit} --json"
    view: "mycli run {run_id} --json"
    trigger: "mycli trigger {pipeline} --ref {ref} --json"
    retry: "mycli rerun {run_id} --json"
```

`list` 输出 JSON 数组、`view` 输出 JSON 对象（字段 `id` / `status` / `commit` / `ref` / `url` / `created_at`），`trigger` / `retry` 输出 `{"run_id": "..."}` 或空。

```bash
python3 {{AIDP_HOME}}/scripts/cicd_watch.py --mode watch   --commit <sha> --env test    # 探测 + 轮询至终态
python3 {{AIDP_HOME}}/scripts/cicd_watch.py --mode trigger --env test --ref <branch>    # 主动触发
python3 {{AIDP_HOME}}/scripts/cicd_watch.py --mode retry   --env test --run-id <id>     # 重试失败的运行
python3 {{AIDP_HOME}}/scripts/cicd_watch.py --selftest                                  # 离线自测
```

- ⛔ 令牌、密码只经环境变量引用，**不要明文写入仓库**。
- `provider: none`、未配置流水线、或提供方 CLI / 凭据不可用时，只推送、不监听（退出码 3），不阻断链路。
- 流水线定义模板见 `.aidp/templates/cicd/`（`github-actions/deploy.yml`、`gitlab-ci/.gitlab-ci.yml`、`jenkins/Jenkinsfile`）。

## 🧪 AI 自动化测试前置

`/sprint-aiauto-test` 依赖 chrome-devtools-mcp。模板插件位于 `.aidp/plugins/chrome-devtools-mcp/`，下游运行路径为 `{{AIDP_HOME}}/plugins/chrome-devtools-mcp/`；跑 `python3 {{AIDP_HOME}}/scripts/agent_sync.py`（脚手架 init / migrate / upgrade 会自动跑）即按当前 Agent 生成项目级入口；本机需要 Node.js（`npx`）。Codex 只在项目被标记为 trusted 后加载项目级 `.codex/` 配置。选择 DeepSeek Harness 执行 init 时，脚手架会尝试安装 `github:SugarFatFree/dsh-agent-extension`；安装失败会给出 WARN 与重试命令，不阻断项目文件生成。

## 📚 文档

| 文档 | 说明 |
|------|------|
| [docs/init/README.md](docs/init/README.md) | AIDP 范式使用指南 |
| [docs/init/00_AIDP范式主文档.md](docs/init/00_AIDP范式主文档.md) | 范式骨架 |
| [docs/README.md](docs/README.md) | 文档体系导航 |
| [.aidp/AIDP-AGENTS.md](.aidp/AIDP-AGENTS.md) | 下游项目记忆正文（核心约定 1–41） |
| [AGENTS.md](AGENTS.md) | 本模板仓库的维护记忆 |
| [设计目标.md](设计目标.md) | 主要命令的设计目标基线 |

## 🤝 贡献

提交遵循 [Conventional Commits](https://www.conventionalcommits.org/)（`feat:` / `fix:` / `docs:` / `refactor:` / `test:` / `chore:`），一次提交只做一件事。

## 📄 许可证

[MIT](LICENSE)
