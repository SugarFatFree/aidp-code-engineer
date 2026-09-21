# Agent 原生运行包与非 Git 模式设计

## 1. 背景

当前模板仓库以 `.aidp/` 为维护真源，脚手架也把同一目录完整下发到目标项目。目标项目中的 Agent 适配目录只是链接或副本入口，命令、flows、角色、规则、脚本、hooks、模板、公共 SKILL 和插件仍依赖根 `.aidp/`。

这会带来两个问题：

1. 下游项目出现与所用 Agent 无关的根 `.aidp/`，不符合 Agent 原生目录边界。
2. 脚手架拒绝非 Git 目录，导致文档开发链和本地测试链无法在普通目录中使用。

本设计将模板维护真源与下游运行布局分离：模板仓库继续维护 `.aidp/`，下游只接收按 Agent 家族渲染的运行包，同时引入明确的无 Git 能力降级语义。

## 2. 目标与非目标

### 2.1 目标

- 新初始化项目根目录不再出现 `.aidp/`。
- Claude Code 的 AIDP 资产全部位于 `.claude/`。
- Codex 与 DSH 的公共 AIDP 资产位于 `.agents/`，各自命令和配置位于 `.codex/`、`.dsh/`。
- 模板仓库仍以 `.aidp/` 为唯一维护真源，不要求维护者同时编辑多个 Agent 目录。
- init、migrate、upgrade、verify 支持非 Git 项目。
- 非 Git 模式下，开发链中不依赖 Git 的部分可用；Git 相关步骤明确返回 unsupported，不伪装成成功。
- 旧下游项目可从根 `.aidp/` 原子迁移到 Agent 原生运行包，保护用户修改。

### 2.2 非目标

- 不为无 Git 项目模拟 commit、HEAD、branch、tag、push 或基于 SHA 的 CICD。
- 不自动执行 `git init`。
- 不把模板仓库自身的 `.aidp/` 真源迁走。
- 不把共享运行内核拆散并嵌入每个命令或 SKILL。
- 本轮不自行修改范式版本号。

## 3. 下游目录契约

### 3.1 Claude Code

Claude-only 项目：

```text
.claude/
├── aidp/
│   ├── agents/
│   ├── flows/
│   ├── hooks/
│   ├── reference/
│   ├── rules/
│   ├── scripts/
│   └── templates/
├── commands/
├── skills/
└── plugins/
```

- `.claude/aidp/` 是 Claude 渲染版只读运行内核。
- `.claude/commands/` 保存 Claude Code 原生命令。
- `.claude/skills/` 保存公共 SKILL 与脚手架 SKILL。
- `.claude/plugins/` 保存 Claude Code 项目级插件。

### 3.2 Codex 与 DSH

Codex-only、DSH-only 或 Codex+DSH 项目：

```text
.agents/
├── aidp/
│   ├── agents/
│   ├── flows/
│   ├── hooks/
│   ├── reference/
│   ├── rules/
│   ├── scripts/
│   └── templates/
└── skills/

.codex/
├── skills/aidp/<command>/
├── config.toml
└── hooks.json

.dsh/
├── commands/
├── hooks.json
└── mcp.json
```

- `.agents/aidp/` 是 Codex/DSH 共用的只读运行内核。
- `.agents/skills/` 保存公共 SKILL；DSH 也从这里发现插件 SKILL。
- `.codex/skills/aidp/` 保存 Codex 原生命令 SKILL。
- `.dsh/commands/` 保存 DSH 原生命令。

### 3.3 生成物形态

下游 Agent 入口和运行包统一使用受管实体文件或目录，不再使用指向根 `.aidp/` 的符号链接：

- `--adapter-mode copy` 保留为兼容参数，其行为即新默认行为。
- `--adapter-mode link` 在新布局中不再创建链接；迁移期接受该参数并报告已规范化为 managed-copy。
- verify 将符号链接视为非预期布局，迁移兼容入口除外。
- 所有生成目录都带受管 manifest，清理只依据 manifest 和受管标记。

这样可避免运行包删除后入口悬空，也使 Windows 与非 Git 项目行为一致。

### 3.4 多 Agent 项目

同时启用 Claude Code 与 Codex/DSH 时生成两份运行包：

```text
.claude/aidp/
.agents/aidp/
```

两份运行包都是脚手架受管派生物：

- 来源版本相同。
- 除运行根路径渲染结果外，规范化内容必须一致。
- 不承载可变业务状态。
- 项目可变状态继续只写根 `memory/`、`docs/`、`code/` 和其他业务目录。

## 4. 运行路径抽象

### 4.1 逻辑路径

引入逻辑运行根：

```text
AIDP_HOME=.claude/aidp   # Claude Code 运行包
AIDP_HOME=.agents/aidp   # Codex/DSH 运行包
```

`AIDP_HOME` 是契约概念，不要求用户长期配置环境变量。脚手架在生成文本入口时渲染目标路径，运行脚本则优先通过自身文件位置解析运行根。

### 4.2 文本契约

模板中会下发且需要引用运行内核的命令、flows、SKILL 和文档使用逻辑占位符：

```text
{{AIDP_HOME}}/scripts/...
{{AIDP_HOME}}/flows/...
{{AIDP_HOME}}/reference/...
```

脚手架必须：

1. 按目标运行包确定性替换占位符。
2. 校验生成物中不存在未解析 `{{AIDP_HOME}}`。
3. 校验新下游运行包中不存在非迁移语义的 `.aidp/` 路径。
4. 对需要保留旧目录迁移判断的代码使用显式 `LEGACY_AIDP_DIR = ".aidp"`，不得被渲染器替换。

### 4.3 Python 与 Shell

Python 脚本通过统一路径模块解析：

```python
runtime_root = Path(__file__).resolve().parents[1]
project_root = discover_project_root(runtime_root)
```

- 运行内核路径从脚本自身位置获得。
- 项目根不依赖 Git；通过受管标记文件和已知目录关系获得。
- 业务状态路径相对项目根解析。

Shell 脚本由脚手架渲染稳定的 `AIDP_HOME`，并允许环境变量显式覆盖以便测试：

```bash
AIDP_HOME="${AIDP_HOME:-.claude/aidp}"
```

或：

```bash
AIDP_HOME="${AIDP_HOME:-.agents/aidp}"
```

## 5. 运行包内容

下游运行包包含：

```text
agents/
flows/
hooks/
reference/
rules/
scripts/
templates/
```

以下内容不放入运行包：

- `commands/`：进入 Agent 原生命令目录。
- 公共 `skills/`：进入 `.claude/skills/` 或 `.agents/skills/`。
- `plugins/`：按 Agent 分别装配。
- `memory/`：模板项目测试或样例内容不下发。
- `scripts/tests/`：模板自有回归测试不下发。
- `aidp-code-engineer/assets/`：只存在于脚手架 SKILL 自身。

`aidp-code-engineer` 脚手架 SKILL 的安装位置：

```text
.claude/skills/aidp-code-engineer/   # Claude Code
.agents/skills/aidp-code-engineer/   # Codex/DSH
```

它携带升级所需的 bundle，不依赖根 `.aidp/`。

## 6. 脚手架生命周期

### 6.1 init

初始化顺序：

1. 解析目标 Agent 集合。
2. 检测 `vcs_mode`，但不要求 Git。
3. 预检所有目标 namespace、用户内容冲突和路径越界。
4. 生成临时运行包与 Agent 入口。
5. 渲染 `AIDP_HOME`。
6. 校验占位符、manifest、Agent 发现路径和运行脚本自检。
7. 原子替换目标目录。
8. 写入脚手架报告和项目状态。

新 init 不创建根 `.aidp/`。

### 6.2 migrate 与 upgrade

旧项目迁移顺序：

1. 识别根 `.aidp/` 和旧脚手架版本。
2. 根据旧 manifest 和当前文件摘要判断用户修改。
3. 对用户修改内容创建完整备份并逐项报告。
4. 在临时目录生成目标 Agent 运行包。
5. 校验新运行包及所有 Agent 入口。
6. 原子安装新运行包。
7. 只有在新运行包全部可用后删除旧根 `.aidp/`。
8. 任一步失败时保留旧 `.aidp/`，回滚新运行包，并写 WARN。

旧 `.aidp/` 本身是迁移来源，不直接作为新运行包继续使用。

### 6.3 Agent 集合变化

- 新增 Claude Code：生成 `.claude/aidp` 和 Claude 入口。
- 删除 Claude Code：只清理由脚手架管理的 `.claude/aidp` 与对应入口。
- 新增 Codex 或 DSH：生成或复用 `.agents/aidp`。
- 只有 Codex 与 DSH 都不启用时才清理受管 `.agents/aidp`。
- 用户自有 Agent 配置、SKILL、插件和命令目录继续受 fail-closed 保护。

## 7. Manifest 与漂移检测

运行包写入受管清单：

```json
{
  "schema": "aidp.runtime/v1",
  "version": "V1.0.0",
  "source": "claude|shared",
  "files": {
    "scripts/agent_sync.py": "sha256..."
  }
}
```

要求：

- manifest 位于运行包内部。
- 哈希基于渲染后的字节。
- 多 Agent 项目可将 `AIDP_HOME` 反向规范化后比较两份运行包。
- 用户修改受管文件时 upgrade 先备份并报告。
- 用户自有文件不进入受管清单，不被清理。

## 8. verify 行为

### 8.1 新项目

verify 根据启用 Agent 校验：

- Claude Code：`.claude/aidp`、commands、skills、plugins、hooks。
- Codex：`.agents/aidp`、`.agents/skills`、`.codex/skills/aidp`、config、hooks。
- DSH：`.agents/aidp`、`.agents/skills`、`.dsh/commands`、MCP、hooks。

新布局项目出现根 `.aidp/`：

- 没有迁移失败记录时为 ERROR。
- 有当前升级产生的明确迁移失败台账时为 WARN，并指出恢复动作。

### 8.2 多运行包一致性

同时存在 `.claude/aidp` 与 `.agents/aidp` 时：

- 版本必须一致。
- manifest 文件集合必须一致。
- 规范化 `AIDP_HOME` 后的内容必须一致。
- 任一运行包漂移都报 ERROR。

## 9. 非 Git 能力模式

### 9.1 检测与身份

新增统一能力字段：

```text
vcs_mode=git|none
```

检测：

- 当前项目确实位于 Git worktree 中时为 `git`。
- 其他情况为 `none`。
- Git 命令未安装、`.git` 不存在或 `git rev-parse` 失败均不阻止脚手架。

开发者标识优先级：

1. `--user`
2. Git 项目中的 `git config user.name`
3. `AIDP_USER`
4. 操作系统用户名

项目根由脚手架参数、运行包标记和目录关系确定，不依赖 `git rev-parse --show-toplevel`。

### 9.2 可用能力

`vcs_mode=none` 时继续支持：

- init、migrate、upgrade、verify
- 需求、设计、计划和开发文档
- 本地开发与研发自测
- AI 测试中不依赖提交差异的步骤
- 本地报告、通知和浏览器测试
- 不依赖 Git 的确定性检查

### 9.3 Git 相关能力

统一结构化结果：

```json
{
  "status": "unsupported",
  "reason": "vcs-disabled",
  "capability": "commit|push|tag|branch|diff|cicd-sha"
}
```

适用：

- commit/push/tag/branch
- 基于 HEAD 或 commit 的 diff
- 基于 Git 状态的提交门禁
- 基于 commit SHA 的 GitHub/GitLab CICD
- Git tag 发布和归档
- autopilot 的拉码、提交和推送阶段

行为规则：

- 只读或辅助检查返回 unsupported，退出码采用现有“能力不可用”语义 `3`。
- 编排器把 unsupported 渲染为 N/A 或 unsupported，不计为通过。
- 开发链跳过该能力并继续其他可用步骤。
- 发布、push、tag 等必须 Git 的动作 fail closed，最终状态不能标记发布成功。
- 本地代码变更本身不因无 Git 而阻断。

### 9.4 统一 VCS 适配层

新增集中模块，禁止各脚本自行猜测 Git：

```text
scripts/vcs.py
```

职责：

- `detect_mode(root)`
- `developer_identity(root, explicit_user)`
- `require_git(root, capability)`
- `unsupported(capability)`
- 安全执行只读 Git 命令

Git 依赖脚本逐步改为调用该模块，保证退出码、JSON 和错误信息一致。

## 10. 错误处理与原子性

- namespace 自身或祖先是 symlink/非目录时，在任何写入前 exit 2。
- 运行包渲染出现未知占位符时拒绝安装。
- 双运行包任一校验失败时不替换现有运行包。
- 旧 `.aidp/` 删除必须晚于新运行包完整验证。
- 非 Git 不属于错误，不产生 traceback；能力不可用使用结构化 unsupported。
- 需要 Git 的发布动作不得降级成假成功。
- 插件安装失败继续按现有 WARN 策略，不影响基础运行包生成。

## 11. 测试设计

### 11.1 运行布局

覆盖：

- Claude-only、Codex-only、DSH-only 和组合模式。
- 新 init 后根 `.aidp/` 不存在。
- 运行内核分别位于 `.claude/aidp`、`.agents/aidp`。
- 公共 SKILL、命令、插件和 hooks 位于正确 Agent 目录。
- 新布局统一生成受管实体副本；旧 `link` 参数被规范化为 managed-copy，不产生符号链接。
- namespace symlink 和路径越界零副作用。

### 11.2 渲染

覆盖：

- 所有 `{{AIDP_HOME}}` 被解析。
- 生成物没有非迁移语义 `.aidp/` 引用。
- Python 项目根解析不依赖 Git。
- Claude/shared 双运行包规范化后一致。
- 命令和编排子命令都指向正确运行包。

### 11.3 迁移升级

覆盖：

- 纯生成旧 `.aidp/` 成功迁移并删除。
- 用户修改旧契约先备份后迁移。
- 备份失败、新包校验失败、安装失败均保留旧目录并回滚。
- 多 Agent 新增、删除和组合变化。
- 同版本迁移入口可执行；目录契约迁移不依赖旧版本覆盖逻辑静默触发。

### 11.4 非 Git

覆盖：

- 空普通目录 init 成功。
- 无 `git` 可执行文件时 init 成功。
- migrate、upgrade、verify 可在非 Git 目录运行。
- 用户名四级回落。
- 文档开发链和本地测试链可用。
- Git 相关脚本统一返回 exit 3 和 `vcs-disabled`。
- 发布、tag、push 不会报告成功。
- Git 项目现有行为不回归。

## 12. 文档与兼容策略

需要同步：

- 根维护说明和下发记忆。
- README 和 `docs/init/`。
- Agent 工具、SKILL、命令速查与 hook 文档。
- 脚手架 init/migrate/upgrade/verify 文档。
- 非 Git 能力矩阵和 unsupported 语义。

生产正文只描述当前行为。旧 `.aidp` 仅在迁移代码、迁移测试和升级说明中出现。

## 13. 版本约束

本变更改变下游根目录结构、运行时路径、脚手架安装位置和非 Git 能力契约，属于破坏性目录契约变更。

当前请求未明确授权版本号自增，因此实现阶段不得执行 `bump_version.py`。完成后必须明确提示：

- 至少建议 bump minor。
- 同版本下游不会自动收到既有契约覆盖。
- 目录迁移需要明确的 upgrade/migrate 入口，不能依赖普通同版本覆盖。
