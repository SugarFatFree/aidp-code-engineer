# 多 Agent 原生命令适配设计

## 1. 背景与目标

AIDP 当前以 `.aidp/commands/` 保存命令正文，以 `.aidp/skills/` 保存公共 SKILL。Claude Code 使用 `.claude/commands/` 原生命令；Codex 与 DeepSeek Harness（DSH）则共同依赖 `aidp-cmd` 路由 SKILL，把命令名和参数转发到 `.aidp/commands/<command>.md`。

Codex 已支持多层级 SKILL 目录，DSH 可通过 `dsh-plugin-commands` 读取项目级 `commands` 目录，因此 Codex 与 DSH 不再需要 `aidp-cmd` 中间路由。本设计将三种 Agent 改为各自的原生命令入口，同时保留 AIDP 契约的单一信源。

目标：

- `.aidp/skills/` 继续作为公共 SKILL 的唯一契约真源。
- `.aidp/commands/` 继续作为命令正文的唯一契约真源。
- 公共 SKILL 生成到根 `.agents/skills/`，Claude Code 另有 `.claude/skills/` 适配层。
- Claude Code、Codex、DSH 分别使用各自可识别的原生命令入口。
- 删除 `aidp-cmd` 的源文件、生成逻辑、校验逻辑及运行时依赖。
- init/migrate/upgrade 后适配层可重复生成、可校验、不会覆盖项目自有内容。

非目标：

- 不改变任何 AIDP 命令正文的业务流程。
- 不把 `.agents/skills/` 改成契约真源。
- 不为 DSH 插件实现自定义包管理器或插件版本锁定机制。
- 本次不自增范式版本号；版本号只在用户明确授权后通过 `bump_version.py` 修改。

## 2. 目录契约

### 2.1 单一信源

```text
.aidp/skills/<skill>/               # 公共 SKILL 契约真源
.aidp/commands/<command>.md         # 命令契约真源
```

`aidp-code-engineer` 仍位于 `.aidp/skills/aidp-code-engineer/`。模板到脚手架 bundle 的镜像与版本门控继续以 `.aidp/` 为输入，不从 Agent 适配目录反向读取。

### 2.2 生成的适配层

```text
.agents/skills/<skill>/             # Codex 与 DSH 共用的公共 SKILL

.claude/skills/<skill>/             # Claude Code 公共 SKILL
.claude/commands/<command>.md       # Claude Code 原生命令

.codex/aidp/skills/<command>/
└── SKILL.md                        # Codex 命令 SKILL

.dsh/commands/<command>.md          # DSH 原生命令

.claude/plugins/chrome-devtools-mcp/                    # Claude Code 项目级插件
.codex/skills/chrome-devtools-mcp/skills/<plugin-skill>/ # Codex 插件 SKILL 集合
.agents/skills/<plugin-skill>/                          # DSH 插件 SKILL
```

路径固定使用 `.codex/aidp/skills`；`aidp` 与项目名称一致。`chrome-devtools-mcp` 的插件 SKILL 在 Codex 与 DSH 组合项目中均指向同一份 `.aidp/plugins/chrome-devtools-mcp/skills/` 真源；Codex 按其发现优先级使用 `.codex/skills`，DSH 使用 `.agents/skills`。

适配层继续支持：

- `link` 模式：使用指向 `.aidp/` 真源的相对符号链接；需要生成包装内容的 Codex 命令 SKILL 除外。
- `copy` 模式：复制或生成完整文件，适用于不便使用符号链接的平台。
- `--check`：只比较预期状态，不写文件。
- 幂等：连续执行不会产生额外变更。
- 项目自有内容保护：仅清理可证明由 AIDP 生成的文件或目录。

## 3. 各 Agent 的装配行为

### 3.1 公共 SKILL

`agent_sync.py` 将 `.aidp/skills/` 中可下发的 SKILL 生成到 `.agents/skills/`。Claude Code 不读取 `.agents/skills/`，因此启用 Claude Code 时还要生成 `.claude/skills/`。

`aidp-cmd` 不再属于 SKILL 集合。公共 SKILL 的过滤、项目自有 SKILL 保护及插件 SKILL 装配维持现有边界。

### 3.2 Claude Code 命令

每个 `.aidp/commands/<command>.md` 直接链接或复制为 `.claude/commands/<command>.md`。调用形式保持：

```text
/<command> [参数]
```

### 3.3 Codex 命令

每个命令生成一个独立目录：

```text
.codex/aidp/skills/<command>/SKILL.md
```

`SKILL.md` 由确定性生成器构造：

1. `name` 等于命令文件名。
2. `description` 从命令文档首个 H1 提取；提取失败时使用稳定的通用描述。
3. 设置为仅允许用户显式调用，禁止隐式模型调用。
4. frontmatter 后原样附加 `.aidp/commands/<command>.md` 正文。
5. 正文中的 `$ARGUMENTS` 不改写，以保持参数语义。

调用形式：

```text
$<command> [参数]
```

Codex 命令 SKILL 是生成物，不进入 `.aidp/skills/`、契约 manifest 或公共 `.agents/skills/`。

### 3.4 DSH 命令

每个 `.aidp/commands/<command>.md` 直接链接或复制为 `.dsh/commands/<command>.md`。调用形式：

```text
/<command> [参数]
```

DSH 同时从 `.agents/skills/` 读取公共 SKILL。命令名与公共 SKILL 名不得冲突；`agent_sync.py` 在写入前执行硬校验，发现冲突时退出并列出名称，防止 DSH 静默选择错误入口。

### 3.5 `chrome-devtools-mcp` 插件

`.aidp/plugins/chrome-devtools-mcp/` 保持插件单一信源。它同时包含 Claude Code 插件清单、6 个调试 SKILL 和 `chrome-devtools` MCP server 声明，各 Agent 按自己的发现机制装配：

- Claude Code：保留完整项目级插件形态，链接或复制到 `.claude/plugins/chrome-devtools-mcp/`，并在 `.claude/settings.json` 登记本地 marketplace 和启用项。
- Codex：不再生成 `.agents/plugins` marketplace 包装。插件的 `skills/` 集合链接或复制到 `.codex/skills/chrome-devtools-mcp/skills/`；同时把 manifest 中的 MCP 声明确定性合并到项目 `.codex/config.toml`：

```toml
[mcp_servers.chrome-devtools]
command = "npx"
args = ["chrome-devtools-mcp@1.6.0"]
```

- DSH：插件内每个 SKILL 以原名称链接或复制到 `.agents/skills/<plugin-skill>/`，同时继续把 MCP 声明汇总到 `.dsh/mcp.json`。

Codex 同时启用 DSH 时也会扫描 `.agents/skills`，但 `.codex/skills` 的发现优先级更高；两处生成物必须指向同一真源并保持字节一致。插件 SKILL 与 AIDP 公共 SKILL 重名时 fail closed，不通过改名或静默覆盖规避冲突。

## 4. DSH 插件安装

脚手架 `init` 选择 DSH 时，在适配层生成前执行：

```bash
dsh plugin --profile web add dsh-plugin-commands@latest
```

约束：

- 只在 `init` 且目标 Agent 包含 DSH 时执行。
- `migrate` 与 `upgrade` 不主动安装或升级全局插件，避免无意改变用户环境。
- 不把 `dsh-plugin-commands` 放入 `.aidp/plugins/`，避免 Claude Code 与 Codex 错误装配 DSH 专属插件。
- `dsh` 不存在、进程启动失败或退出码非零时，脚手架继续生成项目文件，但输出显著 WARN，并在结果摘要中给出原始重试命令。
- 安装失败不伪装为成功；脚手架最终摘要必须表明 DSH 命令运行依赖尚未满足。
- 测试使用临时假命令，不访问网络、不修改真实 DSH 配置。

## 5. `aidp-cmd` 退役与升级迁移

### 5.1 模板仓库

删除：

- `.aidp/skills/aidp-cmd/`
- `agent_sync.py` 中路由正文生成器和 `--router-sync`、`--router-check`
- `verify.py` 中路由源一致性检查
- `FINGERPRINT_EXEMPT` 中的 `skills/aidp-cmd/`
- 仅服务路由 SKILL 的测试、文档和维护约定

### 5.2 下游项目清理

升级后的 `agent_sync.py` 必须清理旧适配入口：

- `.agents/skills/aidp-cmd`
- 其他由旧版适配器生成、且带 AIDP 生成标记的 `aidp-cmd` 入口

旧真源 `.aidp/skills/aidp-cmd/` 由于历史上不受契约指纹管理，采用保守迁移：

- 内容符合旧版生成特征时，删除该目录。
- 内容被用户修改或无法证明为生成物时，先备份到脚手架既有备份目录，报告具体路径，再删除旧入口。
- 不能证明来源且无法完成备份时，不删除并输出 WARN；但新适配层不得再次暴露该路由。

`agent_sync.py` 的普通清理只处理适配层；旧真源清理由脚手架 migrate/upgrade 阶段的确定性迁移函数负责。

## 6. 无人值守调用

`agent_loop.sh` 和调度器使用各 Agent 的原生调用形式：

```text
Claude Code: /<command> <args>
Codex:       $<command> <args>
DSH:         /<command> <args>
```

`ARGUMENTS` 继续由命令系统传入命令正文。脚本仍可 export `ARGUMENTS` 供兼容流程读取，但不再通过 `aidp-cmd` 做二次解析。

## 7. 校验与错误处理

### 7.1 `agent_sync.py`

- 按启用 Agent 独立生成或清理对应适配目录。
- `.agents/skills/` 在 Codex 或 DSH 任一启用时存在；二者都未启用时只清理由 AIDP 生成的入口。
- `--check` 覆盖 `.claude/skills`、`.claude/commands`、`.agents/skills`、`.codex/aidp/skills`、`.dsh/commands` 及插件适配目录。
- 命令与公共 SKILL 重名时 fail closed。
- 不删除没有 AIDP 生成标记的项目自有文件。

### 7.2 `verify.py`

适配模式探测加入 `.codex/aidp/skills` 和 `.dsh/commands`，避免 Codex-only 或 DSH-only 的 copy 模式被误判为 link。

模板模式不再校验路由源；下游模式通过 `agent_sync.py --check` 校验全部适配层。

### 7.3 `.gitignore`

继续由 `agent_sync.py` 维护 AIDP 托管块，只登记实际生成且未被现有目录规则覆盖的路径。不得用整目录规则覆盖用户可能维护的 `.codex/config.toml`、`.codex/hooks.json`、`.dsh/hooks.json` 等配置。

## 8. 测试设计

### 8.1 `agent_sync` 回归

覆盖：

- Claude、Codex、DSH 单独启用及任意组合。
- `link` 与 `copy` 模式。
- 公共 SKILL 同步到 `.agents/skills`，Claude 额外同步到 `.claude/skills`。
- Claude、Codex、DSH 三类命令生成路径与调用元数据。
- Codex frontmatter、H1 描述提取、命令正文逐字保真、`$ARGUMENTS` 保留。
- DSH 命令与 SKILL 重名时拒绝生成。
- 切换 Agent 后清理旧生成物，但保留项目自有文件。
- 旧 `.agents/skills/aidp-cmd` 被清理。
- `chrome-devtools-mcp` 分别装配为 Claude 项目级插件、Codex `.codex/skills` 集合和 DSH `.agents/skills` 集合。
- Codex `.codex/config.toml` 与 DSH `.dsh/mcp.json` 均保留 MCP server 声明，且不再生成 `.agents/plugins` marketplace。
- 插件 SKILL 与公共 SKILL 重名时拒绝生成。
- 幂等与 `--check` 漂移检测。

### 8.2 脚手架回归

覆盖：

- DSH init 成功调用指定插件安装命令。
- 非 DSH init 不调用安装命令。
- migrate/upgrade 不调用安装命令。
- `dsh` 缺失和安装失败时输出 WARN、保留非零安装结果、脚手架主流程完成。
- 旧路由真源的未修改、已修改、无法备份三类迁移路径。
- init/migrate/upgrade 后 `agent_sync.py --check` 通过。
- copy 模式能被 `verify.py` 正确识别。

### 8.3 全量门禁

实现完成后执行项目规定的同步与回归命令：

```bash
python3 .aidp/skills/aidp-code-engineer/scripts/sync_memory_md.py
python3 .aidp/skills/aidp-code-engineer/scripts/mirror_to_bundle.py
python3 .aidp/skills/aidp-code-engineer/scripts/verify.py . --template --read-only
bash .aidp/scripts/tests/run.sh
python3 -m unittest discover -s .aidp/skills/aidp-code-engineer/scripts/tests
python3 .aidp/scripts/check_code_symbol_refs.py
python3 .aidp/scripts/check_cli_invocation.py
python3 .aidp/scripts/check_private_markers.py
```

## 9. 文档同步

同步更新：

- 模板维护说明 `AGENTS.md`
- 下发记忆 `.aidp/AIDP-AGENTS.md`
- 根 `README.md`
- `.aidp/reference/agent-tools.md`、`.aidp/reference/skills.md` 与命令速查
- `.aidp/scripts/README.md`、`.aidp/hooks/README.md`
- 脚手架 SKILL 文档和 `docs/init/` 中的多 Agent 说明
- 无人值守调用示例

所有文档只描述当前行为，不保留“已移除”“旧版曾使用”等迁移叙述；历史迁移细节只存在于实现测试和本设计文档。

## 10. 验收标准

满足以下条件即实现完成：

1. 新项目中不存在 `aidp-cmd` 源文件或 Agent 入口。
2. 三种 Agent 均能通过自己的原生命令形式执行同一份 `.aidp/commands/` 契约。
3. Codex 和 DSH 均从 `.agents/skills/` 读取公共 SKILL，Claude Code 从 `.claude/skills/` 读取相同真源的适配层。
4. DSH init 会尝试安装 `dsh-plugin-commands@latest`，失败时结果可见且可恢复。
5. 旧项目升级不会静默覆盖项目自有文件，也不会继续暴露旧路由入口。
6. `chrome-devtools-mcp` 在 Claude Code 中保持完整项目级插件，在 Codex/DSH 中以各自原生 SKILL 路径可发现，且两者均有可用的 MCP server 配置。
7. `agent_sync.py --check`、模板 verify、脚手架单测和模板回归测试全部通过。
8. bundle 由同步脚本生成，未手工修改 `.aidp/skills/aidp-code-engineer/assets/`。

## 11. 版本约束

本变更会改变下游命令发现与调用行为，属于会下发的契约行为变更。当前请求未包含范式版本号自增授权，因此实现与本地提交保持现有版本不变。完成后应明确提示维护者：下游同版本升级不会获得已有契约覆盖，建议另行授权 bump 一个 patch 版本。
