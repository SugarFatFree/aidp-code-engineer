---
name: aidp-code-engineer
description: AIDP 范式项目脚手架。把空项目初始化（init）、把已有非 AIDP 项目改建（migrate）、把本脚手架的旧版本项目升级（upgrade）为 AIDP 范式项目；按项目使用的 AI 编码 Agent（Claude Code / Codex / DeepSeek Harness）装配入口，执行后校验结构完整性。当用户要求初始化 AIDP 项目、接入 AIDP、改建为 AIDP 结构、升级 AIDP 脚手架时使用。
argument-hint: "[init|migrate|upgrade] [--version V0.1.0] [--user NAME] [--agent claude|codex|dsh] [--adapter-mode link|copy] [--name-cn 中文名] [--force]"
user-invocable: true
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Agent, AskUserQuestion
---

# /aidp-code-engineer — AIDP 范式项目脚手架

> 本文以 Claude Code 工具名书写（`AskUserQuestion` / `Agent` / `Bash` 等）；在 Codex 或 DeepSeek Harness 下按目标项目 `{{AIDP_HOME}}/reference/agent-tools.md` 换成等价能力。

## 触发条件

- 空仓库要按 AIDP 范式起步 → `init`
- 已有代码 / 文档、尚未接入 AIDP 的项目要改建 → `migrate`
- 已由本脚手架初始化的项目要升级到当前脚手架版本（`assets/SCAFFOLD_VERSION`）→ `upgrade`
- 未指定模式时自动判定（见 Phase 0）

## 参数

`$ARGUMENTS`：

| 参数 | 含义 |
|------|------|
| `init` / `migrate` / `upgrade` | 执行模式；缺省自动判定 |
| `--version V0.1.0` | 项目业务版本号（迭代目录名）；缺省读项目记忆文件「当前版本」，再无则询问，默认 `V0.1.0` |
| `--user NAME` | 开发者标识；缺省取 `git config user.name` |
| `--agent claude\|codex\|dsh` | 项目根没有任何 Agent 标记目录时装配哪些 Agent，可逗号多选 |
| `--adapter-mode link\|copy` | 入口装配方式；Windows 默认 `copy`，其他默认 `link` |
| `--name-cn 中文名` | 项目中文名，写入 `memory/aidp-config.yaml` 的 `project.name_cn` |
| `--force` | 无视版本门控，覆盖全部契约文件（已填写的用户填充型契约仍受保护） |

其余脚本参数（`--keep-backups` / `--keep-days` / `--no-agent-sync` / `--json`）见 `scaffold.py --help`。

## 前置条件

1. 目标目录可以不是 Git 仓库；探测输出 `vcs_mode=git|none`，`none` 不自动执行 `git init`，Git 提交、推送、tag、CICD 与正式发布能力不可用。
2. 能取得开发者标识：有 Git 配置时取 `git config user.name`（仅字母、数字、`_ . -`），否则向用户要一个传给 `--user`。
3. Python 3.8+（脚本只用标准库）。
4. 目标项目不是 AIDP 模板仓库本身（脚本会拒绝）。

## 资源位置

`{SKILL_DIR}` = 本 SKILL 所在目录（模板仓库为 `.aidp/skills/aidp-code-engineer/`；安装后契约在 `{{AIDP_HOME}}/skills/aidp-code-engineer/`，Agent 可发现入口在 `.claude/skills/` 或 `.agents/skills/`）。模板 `.aidp/` 只作维护源，目标项目根不创建 `.aidp/`。仅 Claude Code 时 `{{AIDP_HOME}}=.claude/aidp`；有 Codex / DeepSeek Harness 时 `{{AIDP_HOME}}=.agents/aidp`，Claude Code 并存时使用 `.claude/aidp` 装配副本。

```
{SKILL_DIR}/
├── SKILL.md
├── scripts/
│   ├── scaffold.py          # 主入口：--detect 探测 / 三模式执行
│   ├── migrate.py           # 代码单元与文档扫描、PRD/原型归位、已有记忆文件内容保全
│   ├── verify.py            # 确定性结构检查（aidp-compliance Agent 包住它）
│   ├── finalize_upgrade.py  # 语义改写队列清空后收口版本戳
│   ├── scaffold_marker.py   # memory/aidp-config.yaml 的 scaffold.version / pending 读写
│   ├── scaffold_lib.py      # 目录骨架、契约目录、gitignore 托管区、备份策略等共享定义
│   ├── reverse_generate.py  # 从已有代码反向生成 docs/architecture/技术选型.md
│   ├── mirror_to_bundle.py  # 模板维护：本体 → assets/ 单向镜像
│   ├── sync_memory_md.py    # 模板维护：.aidp/AIDP-AGENTS.md（下发记忆源）→ assets/AGENTS.md.tpl
│   ├── bump_version.py      # 模板维护：提升范式版本号
│   └── tests/               # 模板回归单测（python3 -m unittest；不随安装下发）
├── references/
│   └── autopilot/output-examples.md
├── sources/                 # 模板维护：下游根文件与项目级 memory 模板的真源（→ assets/root、assets/memory；不随安装下发）
└── assets/                  # 全部由 mirror_to_bundle.py 派生，不手改
    ├── aidp/                # → 目标项目 {{AIDP_HOME}}/（受版本门控目录见 scaffold_lib.py::GATED_DIRS，另有 scripts）
    ├── docs/                # → docs/ 结构性 README、docs/init、docs/architecture 约束骨架
    ├── memory/              # → memory/README.md 与项目级 memory 模板（*.md.tpl）
    ├── root/                # README.md.tpl / gitignore.tpl / env.tpl
    ├── AGENTS.md.tpl        # 项目记忆文件模板（{{project}} {{user}} {{version}} {{date}}）
    ├── aidp-config.yaml.tpl # memory/aidp-config.yaml 模板
    ├── SCAFFOLD_VERSION     # 本脚手架范式版本
    └── CONTRACT_MANIFEST.json  # 受版本门控契约文件的 sha256 指纹
```

## 执行流程

### Phase 0：探测与确认（三模式共用）

1. 探测：

   ```bash
   python3 {SKILL_DIR}/scripts/scaffold.py <项目根> --detect
   ```

   输出 JSON：`mode`（已安装 `.claude/aidp/` 或 `.agents/aidp/` → upgrade；未安装但有代码 → migrate；否则 init）、`user`、`version_guess`、`agents.markers`、`scaffold`（脚手架版本 / 项目版本 / pending / 队列条数）、`memory_files`、`code_units`、`docs`、`inputs`（根目录 PRD / 原型）。

2. 确定模式：`$ARGUMENTS` 显式给出则用之；否则用探测结果，并用 `AskUserQuestion` 向用户确认（可切换）。
3. 确定 `{version}`：`--version` → `version_guess` → 询问（默认 `V0.1.0`，格式 `V主.次[.修订]`）。
4. 确定 Agent：
   - `agents.markers` 非空（项目根已有 `.claude/` `.codex/` `.dsh/` 之一或多者）→ 按其装配，不再询问；
   - 否则取 `--agent`；再无则取环境变量 `AIDP_AGENT`；再无则用 `AskUserQuestion` 询问（可多选：Claude Code / Codex / DeepSeek Harness）；无人值守时默认 claude。
   - 脚本会创建对应标记目录。以后要追加 Agent：先创建其标记目录，再跑 `upgrade`。
5. 适配层方式：Windows 默认 `copy`，其他默认 `link`（符号链接）；用户要求时传 `--adapter-mode copy|link`。

### Mode 1：init（空项目）

1. **产品输入归位**（`inputs.prd` / `inputs.prototype` 非空时）：用 `AskUserQuestion` 列出命中项与目标——PRD → `docs/requirements/{version}/产品提供/`，原型目录 → `docs/prototype/{version}/code/`（以图片 / PDF / 设计源为主则 `mockup/`）；用户可逐项剔除、选移动或复制。确认后在执行脚手架**之后**运行：

   ```bash
   python3 {SKILL_DIR}/scripts/migrate.py place-inputs <项目根> --version {version} [--only 名称1,名称2] [--copy]
   ```

2. **执行脚手架**：

   ```bash
   python3 {SKILL_DIR}/scripts/scaffold.py <项目根> --mode init --version {version} --agent {agents} [--adapter-mode link|copy]
   ```

   脚本确定性完成：目录骨架与 `.gitkeep` → `{{AIDP_HOME}}/` 全部契约 → 脚手架自身安装 → `docs/init` 范式文档、`docs/**/README.md`、`docs/architecture/` 三份约束骨架 → `memory/aidp-config.yaml`、`memory/README.md`、5 份项目级 memory → 根 `README.md`、`env/.env`、`.gitignore` 托管区 → 项目记忆文件 → 导航 README → 写 `scaffold.version` → `agent_sync.py` 装配入口与 Stop hook。

3. **项目记忆文件形态**（由 `agent_sync.py` 保证）：只有 Claude Code → `CLAUDE.md`；否则正文在 `AGENTS.md`，与 Claude Code 并存时 `CLAUDE.md` 为一行 `@AGENTS.md`。项目根原有的 CLAUDE.md / AGENTS.md 内容会并入「项目自定义」段并进入语义改写队列（处理方式同 Mode 2 第 4 步）。

4. **业务信息填充**（`docs/requirements/{version}/` 下已有 PRD 时）：读 PRD 的业务层内容，填写 `memory/projectBrief.md`、`memory/productContext.md` 与根 `README.md` 的项目简介；技术层 memory（`techContext.md`）留给 `/sprint-design`。无 PRD 保留模板占位。

5. **项目中文名**：询问或从 PRD 取，写入 `memory/aidp-config.yaml` 的 `project.name_cn`（也可在第 2 步用 `--name-cn` 传入）。

6. 执行「验证」章节。

### Mode 2：migrate（已有非 AIDP 项目改建）

1. **扫描汇报**：基于 Phase 0 探测结果向用户汇报——
   - `code_units`：每个代码单元的 `path`、`side`、`suggested`（`code/frontend|backend/{子项目}`）、`command`（有 Git 时建议的 `git mv`；无 Git 时仅提出移动建议，不执行 Git 命令）；
   - `docs`：非标准文档目录与建议落点；
   - `memory_files`：已有记忆文件（其内容将保全）；
   - `inputs`：根目录 PRD / 原型。
2. **确认门**（`AskUserQuestion`）：
   - 代码目录：默认**保持原位**；用户明确选择迁入时，有 Git 才逐个执行 `command` 里的 `git mv`；非 Git 需另行征得移动授权并使用普通文件操作。同步修正构建脚本 / CI 中的路径。保持原位时，在 `memory/techContext.md`「项目代码结构」写明实际路径。
   - 非标准 docs 目录：迁入建议落点或保留；有 Git 时按用户选择执行 `git mv`，非 Git 时按授权使用普通文件操作。
   - PRD / 原型：同 Mode 1 第 1 步。
3. **执行脚手架**：

   ```bash
   python3 {SKILL_DIR}/scripts/scaffold.py <项目根> --mode migrate --version {version} --agent {agents}
   ```

   与 init 的差异：先备份将被触及的文件到 `.aidp-backup-<时间戳>/`；已存在的根 `README.md`、非 AIDP 形态的 `docs/**/README.md` 与 `memory/README.md` 保留原文；`code/` 下已有自定义代码目录时不补建 `code/frontend|backend`；原有 CLAUDE.md / AGENTS.md 的非 AIDP 内容并入新记忆文件「项目自定义」段并进入语义改写队列复核。

4. **处理语义改写队列**（`.aidp-rewrite-queue.txt`，脚本输出 `pending: true` 时必做）。每行 `<目标路径>\t<新版模板路径>\t<入队时目标文件 sha256>`（两个路径都是仓库相对路径），逐条：
   1. `Read` 目标文件与新版模板（模板占位符按本项目实际值理解）；
   2. 以模板的结构、术语、路径、命令名为准改写目标文件，保留项目自有内容：已填写的 `{{AIDP_HOME}}/reference/子Agent必读.md` 条目、项目补充进 `docs/**/README.md` / `memory/README.md` 的内容；改建时并入记忆文件「项目自定义」段的原文；
   3. 「项目自定义」段去重，删掉与 AIDP 正文重复的规则；与 AIDP 约定冲突的项（典型：把完整构建 `pnpm build` / `mvn package` 或启动服务列为开发期常用命令，违反约定 35）用 `AskUserQuestion` 逐项交用户裁决，推荐删除或改为部署期限定；无法提问时保留原文并在输出中列出冲突项；
   4. `Write` 覆盖。⛔ 不要手工删除队列文件。全部处理完后：

   ```bash
   python3 {SKILL_DIR}/scripts/finalize_upgrade.py --root <项目根> [--accept <确认无需改动的目标路径> …]
   ```

   它逐条核验目标文件在入队后已被改写（未改动的条目须用 `--accept` 显式确认），通过后把 `scaffold.pending` 提升为 `scaffold.version`、把指纹台账推进到新版骨架、删除队列文件；队列文件缺失而 `scaffold.pending` 仍在时拒绝收口（重跑 `scaffold.py --mode upgrade` 重新生成队列）。

5. **反向生成技术选型**（已有代码时）：

   ```bash
   python3 {SKILL_DIR}/scripts/reverse_generate.py <项目根>
   ```

   只在 `docs/architecture/技术选型.md` 仍是模板时生成；排除 `docs/prototype/`、备份与依赖目录。生成后请用户复核选型理由。

6. **memory 增量补充**：`memory/*.md` 仍是模板时，从 README、`package.json`、`pom.xml`、已有 SQL 提取信息填充 `projectBrief.md`、`techContext.md`、`databaseBaseline.md`；已有真实内容一律不改。
7. 执行「验证」章节。

### Mode 3：upgrade（本脚手架旧版本项目升级）

1. **读取状态**：Phase 0 的 `scaffold.project_version`、`scaffold.pending`、`scaffold.rewrite_queue`。上一轮队列未清空时，先完成 Mode 2 第 4 步再升级。
2. **执行脚手架**：

   ```bash
   python3 {SKILL_DIR}/scripts/scaffold.py <项目根> --mode upgrade [--version {version}] [--force]
   ```

   契约处置由版本门控决定（输出 `contract_decision`）：

   | 项目 `scaffold.version` vs 脚手架版本 | 处置 |
   |---|---|
   | 缺失，或低于脚手架版本，或 `--force` | `overwrite`：先备份，受版本门控目录（`scaffold_lib.py::GATED_DIRS`）全部覆盖到新版 |
   | 相等，且有 pending 或未清空队列 | `overwrite`：重跑完整同步 |
   | 相等 | `fill`：只补缺失文件，不改已有正文 |
   | 高于脚手架版本 | `protect`：不动契约，提示换用新版脚手架 |

   任何处置下都执行：`{{AIDP_HOME}}/scripts/` 字节不同即覆盖；脚手架自身重新安装；`docs/init` 刷新；`memory/aidp-config.yaml` 只补缺失配置段；项目级 memory 里残留的占位符只替换占位符本身；`.gitignore` 托管区（`# >>> AIDP-GITIGNORE-MANAGED` 标记之间）整块刷新、区外规则不动；`agent_sync.py` 重新装配。覆盖任何已有文件前都先备份到 `.aidp-backup-<时间戳>/`（输出 `backup`）。

   保护规则：
   - **本地改过的契约**：`overwrite` 时按上一版安装的 `CONTRACT_MANIFEST.json` 指纹比对，项目改过又被新版覆盖的文件逐个列在输出 `local_overwritten` 与警告里（附备份目录），向用户转述；
   - **用户填充型契约**（`{{AIDP_HOME}}/reference/子Agent必读.md`）与**结构性 README**（`docs/**/README.md`、`memory/README.md`）：依据 `.aidp-user-fillable.json` 指纹台账判定——未改过则刷新；改过且新版骨架有变化则不覆盖、进入语义改写队列；新版骨架与上次合并的一致则不动；
   - **项目记忆文件**：`overwrite` 时由脚本按锚点确定性合并——「项目自定义」段之前取新模板正文，「当前状态」段保留项目的版本 / 开发者 / Sprint / 目标 / 进度 / 最后更新等字段值，「项目自定义」段原样保留；不进语义改写队列；
   - **项目私有 SKILL**（`{{AIDP_HOME}}/skills/` 下脚手架没有的目录）：不触碰；
   - **孤儿契约**（项目里有、当前脚手架已没有的契约文件）：输出 `orphans` 清单，只报告不删除——向用户列出，确认后再删。
3. **处理语义改写队列并收口**：同 Mode 2 第 4 步。
4. **备份清理**：脚本按「最近 1 个 ∪ 7 天内」保留 `.aidp-backup-*`（`--keep-backups N` / `--keep-days N` 调整，`--keep-backups 0` 不清理）；输出里超出阈值会提示手工删除。
5. 执行「验证」章节。

## 多 Agent 说明

- 单一信源是目标项目的 `{{AIDP_HOME}}/`（仅 Claude 为 `.claude/aidp/`；有 Codex / DSH 为 `.agents/aidp/`）；模板 `.aidp/` 不下发到项目根；Claude Code 的 `.claude/commands|skills|plugins`、Codex 的 `.codex/skills/aidp` / `.codex/skills`、DeepSeek Harness 的 `.dsh/commands`、共用 `.agents/skills` 及各 Agent hook / MCP 配置均由 `python3 {{AIDP_HOME}}/scripts/agent_sync.py` 生成，不手改。
- 装配方式：`link` 用相对符号链接，`copy` 为实体副本（不支持符号链接的环境）；改了下游 `{{AIDP_HOME}}/` 后重跑 `agent_sync.py` 即可同步（模板契约须在模板仓库修改并由脚手架升级）。
- 记忆文件形态切换（例如后来加入 Codex）由 `agent_sync.py` 搬迁正文，不丢内容。
- 命令入口：Claude Code 为 `.claude/commands` + `/命令`，Codex 为官方发现根 `.codex/skills/aidp` + `$命令`，DeepSeek Harness 为 `.dsh/commands` + `/命令`。Codex 命令 SKILL 内联执行原始正文明确串联的 `/foo args`：读取 `{{AIDP_HOME}}/commands/foo.md`，把 `args` 原样传为 `$ARGUMENTS`；未知命令 fail closed。
- 浏览器自动化插件 `chrome-devtools-mcp` 的模板真源在 `.aidp/plugins/`、下游运行契约在 `{{AIDP_HOME}}/plugins/`：Claude Code 登记完整项目插件；Codex / DeepSeek Harness 将插件 SKILL 装配进共享 `.agents/skills/chrome-devtools-mcp/skills/`，MCP 分别合并到 `.codex/config.toml` / `.dsh/mcp.json`。本机需要 Node.js（`npx`），Codex 需项目 trust；DSH init 会尝试安装 `github:SugarFatFree/dsh-agent-extension`，失败时报告 WARN 和重试命令。
- 命令、工具名、定时循环在各 Agent 下的写法见 `{{AIDP_HOME}}/reference/agent-tools.md`。

## 验证

非 Git 项目也须运行结构与内容校验；依赖 Git 的检查只能标注不适用，不得视为通过。`vcs_mode=none` 的能力矩阵：init / migrate / upgrade、规划、开发、本地测试、本地归档可运行；提交、推送、tag、commit SHA 关联的 CICD 和正式发布不可用。正式发布 fail closed，不得宣布已发布，且不得自动 `git init`。

每个模式末尾执行，按 `{{AIDP_HOME}}/agents/aidp-compliance.md` 的工作流激活合规检查（`Read` 该角色文件后按其步骤执行，不是内置子 Agent 类型）。它的第一步是：

```bash
python3 {SKILL_DIR}/scripts/verify.py <项目根> {version} {user} --read-only
```

`verify.py` 输出 ✅ FIXED / ❌ ERROR / ⚠️ WARN / ℹ️ INFO 四段，退出码 0 = 无 ERROR。检查项：

| 类别 | 内容 |
|------|------|
| 结构 | 目录骨架（含版本级目录）；关键脚本、hook、合规 Agent、`docs/init` 八份范式文档、memory 与 docs 骨架文件存在 |
| 多 Agent | 项目记忆文件形态与 `agent_env.py` 判定一致、必需区域齐全；`agent_sync.py --check` 无漂移 |
| 同步 | `docs/init` 与脚手架一致；契约文件与 `CONTRACT_MANIFEST.json` 逐文件比对、孤儿契约；项目脚手架版本是否落后 |
| 约定 | 代码目录 `code/frontend\|backend/{子项目}` 中间层；README 三档策略（约定 19）；部署双轨布局与 SQL 版本落位（约定 37 / 11）；部署文档齐备 |
| 安全与卫生 | 运行时产物入库策略、凭证文件未入库、`.gitignore` 托管区为最新、占位符已替换、备份目录体积、语义改写队列与 pending 已收口、「项目自定义」段与约定 35 冲突 |
| 契约正文守卫 | flow 分片体积、锚点、单一信源指针、WebMCP、术语、约定 30 正文、shell 围栏、计数声明、幽灵旗标等，委派 `{{AIDP_HOME}}/scripts/check_*.py`；仓库根有 `设计目标.md` 时加设计目标棘轮（`--no-guards` 跳过本类） |

合规 Agent 在脚本结果之上追加语义维度（模板残留与 memory 真填充、事实清单 ↔ 代码配置、命令-SKILL-Agent 引用三角、设计目标背离），输出统一报告；报告不阻断流程，ERROR 交用户决定。

## 输出

```
🎉 AIDP 项目{初始化|改建|升级}完成（脚手架 {SCAFFOLD_VERSION}）

📋 项目：{project}（{project_cn}） · 版本 {version} · 开发者 {user} · 模式 {mode}
🤖 Agent：{agents}（{link|copy}）· 项目记忆文件：{CLAUDE.md|AGENTS.md}
📁 契约处置：{overwrite|fill|protect} · 新建 {n} · 更新 {n} · 语义改写 {n} 条（{已收口|待处理}）
⚠️ 孤儿契约 / 冲突项 / 备份提示：{列表或「无」}
✅ 合规检查：ERROR {n} · WARN {n}

🔄 请重启当前 AI 编码 Agent（或新开会话），新装的命令、SKILL、角色与 hook 在会话启动时加载。

📌 下一步（重启后）：
- 核对 memory/projectBrief.md、memory/productContext.md、README.md 的业务介绍
- PRD 放入 docs/requirements/{version}/产品提供/，原型放入 docs/prototype/{version}/code|mockup/
- 执行 /version {version} "M1" 开始版本规划
```

## 注意事项

1. **已有代码不动**：脚本从不移动代码；迁入 `code/frontend|backend/{子项目}` 只在用户确认后由 Agent 执行（有 Git 时用 `git mv`，无 Git 时用普通文件操作）。
2. **内容零丢失**：已有记忆文件并入「项目自定义」段；memory 与 `docs/architecture` 已有真实内容不覆盖；覆盖任何已有文件前自动备份到 `.aidp-backup-*`。
3. **队列必须收口**：`.aidp-rewrite-queue.txt` 入库、团队可见（路径均为仓库相对路径）；未收口时 `verify.py` 报 ERROR、下次运行会重做完整同步；收口只走 `finalize_upgrade.py`。
4. **幂等**：同版本重复执行只补缺失文件，不产生多余改动。
5. **结束必须提示重启 Agent**：命令、SKILL、hook 只在会话启动时加载。
6. **下游不改契约**：`{{AIDP_HOME}}/` 契约文件由本脚手架维护，项目特有规则写在项目记忆文件「项目自定义」段或 `code/{子项目}/` 下的项目说明（约定 16）。

## 模板维护（仅在 AIDP 模板仓库内）

改动模板仓库的 `.aidp/`、`.aidp/AIDP-AGENTS.md`、`docs/init`、`docs/**/README.md`、`docs/architecture/` 三份约束骨架、`memory/README.md`、`memory/aidp-config.yaml` 或本 skill 的 `sources/` 后：

```bash
python3 .aidp/skills/aidp-code-engineer/scripts/mirror_to_bundle.py                  # 本体 → assets/（含 AGENTS.md.tpl、SCAFFOLD_VERSION、CONTRACT_MANIFEST.json）
python3 .aidp/skills/aidp-code-engineer/scripts/verify.py . --template --read-only   # 模板自检（含 mirror --check、sync_memory_md --check、gitignore.tpl 覆盖）
python3 -m unittest discover -s .aidp/skills/aidp-code-engineer/scripts/tests
```

只在用户明确要求时提升范式版本：`python3 .aidp/skills/aidp-code-engineer/scripts/bump_version.py V1.0.1`（改写 `版本变更历史.md`「当前范式版本」并在内部重跑 `mirror_to_bundle.py` 派生 `SCAFFOLD_VERSION` 与 `CONTRACT_MANIFEST.json`），再跑上面的模板自检，由人补写变更记录。
