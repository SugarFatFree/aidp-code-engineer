> AIDP 查阅型资料分片（非 @import、不常驻、按需 Read）；总纲见项目记忆文件 `AGENTS.md`（Claude Code 下为 `CLAUDE.md`）的同名段。

## 本项目使用的 Skills

> 按约定 21，下表只给**一句话用途 + 被谁调用**；各 SKILL 的维度/原则/检查细则是单一信源，详见对应 `SKILL.md`，不在此复述。模板 `.aidp` 中的 skills 仅用于维护，下游公共 SKILL 从 `.agents/skills/`（Codex / DSH）或 `.claude/skills/`（Claude）调用，契约真源在 `{{AIDP_HOME}}/skills/`。

### 本项目自带的 Skills（`{{AIDP_HOME}}/skills/`；**可改性以约定 16 为准**——全部由 AIDP 模板仓库维护、在模板仓库内可直接改，下游项目内不应直接改）

| Skill | 用途 | 被谁调用 |
|-------|------|---------|
| `ux-logic-extractor` | PRD 研发需求生成（模式 A 逆向 / B 融合）| `/sprint-requirements`（累进经 `--supplement` / `--ledger-cascade` 同一入口）|
| `dev-logic-architect` | 详细设计 / 接口 / 数据库生成 | `/sprint-design`（累进同上）；开发期预检直调其脚本见 `/sprint-dev` |
| `dev-execution-planner` | 研发执行计划生成 | `/sprint-plan`（累进同上）|
| `dev-manual-testcase` ★ | 研发自测方案 + 人工自测用例生成（AI 浏览器自动化推荐 chrome-devtools-mcp）| `/sprint-selftest`（版本规划期研发自测唯一生产入口，`/version` Step 2.4.3.5 调）+ `/sprint-test` 预判断/用例补跑（**走 `/sprint-selftest`，⛔ 不直调 SKILL**）+ 累进 L4 增量与级联（走 `/sprint-selftest --supplement` / `--ledger-cascade`）|
| `auto-test-runner` ★ | 端无关自动化测试执行器（分模块批量 / 执行模式分级 / 感知-执行-校验-决策闭环 / 断点续跑 / 固定报告结构；驱动可插拔 Web·小程序·APP·桌面，消费 `dev-manual-testcase` 标准用例）| `/sprint-aiauto-test` Phase 2 委派执行内核（命令只做环境准备 + 运行时错误升级 + 报告 finalize + 里程碑通知，执行方法论不复述）|
| `code-verification-loop` | 代码验收循环（多维度核验，维度清单以 SKILL.md 为单一信源；`mode=verify-only` 仅验收）| `/sprint-test`（仅验收模式）；开发期预检直调其脚本：`/sprint-dev`、Frontend/Backend Agent |
| `bugfix` | Bug 修复流程 | `/sprint-bugfix` |
| `aidp-code-engineer` | 项目 AIDP 范式脚手架（init/migrate/upgrade）| 按需手动 |

### 配套脚本（非 skill）

| 脚本 | 用途 | 被谁调用 |
|-------|------|---------|
| `{{AIDP_HOME}}/scripts/notify.py` ★ | 里程碑通知发送（`--auto` 按 `memory/aidp-config.yaml` 的 `notify.channels` 依次尝试飞书 webhook / lark-cli / 钉钉 / 企业微信 / 自定义命令，成功即停；未配置渠道退出码 3 = 静默跳过；单一信源见约定 32）| `/sprint-autopilot` + `/sprint-aiauto-test` 里程碑通知 |
| `{{AIDP_HOME}}/scripts/cicd_watch.py` | CICD 流水线监听与触发 / 重试（`--mode` watch / detect / poll / trigger / retry；平台 = `cicd.provider`，默认 GitHub Actions，适配层 `cicd_providers.py`；单一信源见约定 31.5）| `/sprint-autopilot` 部署阶段、链外 push 后监听 |

### 随仓库分发的插件

| 名称 | 用途 | 安装 |
|------|------|------|
| `chrome-devtools-mcp`（插件） | 浏览器实测驱动 MCP + 6 份配套调试 SKILL（`/sprint-aiauto-test`、`dev-manual-testcase` 推荐）| 随仓库分发于 `{{AIDP_HOME}}/plugins/chrome-devtools-mcp/`（Apache-2.0）：Claude Code 使用 `.claude/plugins/` 完整项目插件（工具名 `mcp__plugin_chrome-devtools-mcp_chrome-devtools__*`）；Codex / DeepSeek Harness 共用 `.agents/skills/chrome-devtools-mcp/skills/`，MCP 分别写入 `.codex/config.toml` / `.dsh/mcp.json` |

### Superpowers 插件 Skills（★ 全局内置插件，非项目 vendored）

> 📍 **安装位置在【用户级全局】，不在项目里**——Claude Code 下来自 `claude-plugins-official` 市场，
> 落点 `~/.claude/plugins/cache/claude-plugins-official/superpowers`；其他 Agent 未装时按下表回落。
>
> ⚠️ **不能据「项目 `.claude/plugins/` 里没有」判它未安装**：项目级 `.claude/plugins/` 与项目
> `settings.json` 的 `enabledPlugins` **本来就不会列全局插件**。
> **要判可用性就直接看 Skill 工具的可用清单**，那才是运行时事实。

| Skill | 用途 | 被谁调用 | 未装时的回落 |
|-------|------|---------|---------|
| `superpowers:test-driven-development` | TDD 开发方法 | `/sprint-dev`（`/sprint-full` 经其调用）| 手工守 TDD 纪律：先写测试再写实现 |
| `superpowers:subagent-driven-development` | 并行 subagent 开发 | `/sprint-dev`（`/sprint-full` 经其调用）| 串行实现（慢但等价） |
| `superpowers:systematic-debugging` | 系统化调试 | `bugfix` SKILL 根因定位（经 `/sprint-bugfix`）| 按 `bugfix` SKILL Step 3 手工定位：复现 → 根因 → 最小修复 → 回归 |
| `superpowers:executing-plans` | 计划执行 | `/sprint-batch` | 普通循环（本就仅作循环脚手架） |
| `superpowers:verification-before-completion` | 完成前验证 | `/sprint-dev`、`/sprint-test`、`/sprint-batch`、`/sprint-bugfix` 方式 B | 走该命令自身的输出前硬门 |

> **外部市场可选 Skills**（非自带，未装则跳过）：`api-tester`（Spring Boot 后端接口测试，由 `/sprint-test` / `/sprint-full` 在"环境可用"前提下条件调用）等；命令端以"可选/且可用"保护调用，缺失即跳过。
