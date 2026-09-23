# /sprint-init-design — 初始化前半段（分步模式）

你正在执行 `/sprint-init-design` 命令，这是项目初始化的前半段。

此命令执行 Phase 0（确定性骨架产出）+ Phase 1（PM Agent）+ Phase 2（Architect Agent），生成 5 个核心记忆文件（均为项目级）。
完成后用户可以人工审核和修改这些文件，然后执行 `/sprint-init-complete` 完成初始化。

## 前置流程

与 `/sprint-init` 一致：
1. **{version}**：询问用户项目起始版本号（建议 `V0.0.1` 或 `V0.1.0`）。
2. **{user}**：`git config user.name`。
3. 本阶段不生成迭代级 memory 的**内容**（L3）——⛔ 注意措辞：**目录**由 Phase 0 的脚手架统一建出（清单单一信源 `scaffold_lib.py::skeleton_dirs`）（含 `memory/{version}/{user}/sprints`），本阶段只是不往里写内容，仅保留 {version}/{user} 供 `/sprint-init-complete` 使用；建议写入 `AGENTS.md` 草稿的「当前状态」以便下一步复用。

## 前置检查

1. 确认 `docs/init/` 目录存在（AIDP 范式文档，应含 00-07）
2. 确认 `docs/requirements/PRD-*.md` 存在（**可选，无也能初始化** — 与全量 `/sprint-init` 一致；缺 PRD 时按空模板骨架初始化、待后续补）
3. 检查 `memory/` 目录是否已存在（如已存在，警告用户并确认是否覆盖）

`docs/init/` 缺失才停止执行并提示用户补充（PRD 缺失不阻塞）。

## Phase 0：★ 确定性骨架产出（与 `/sprint-init` 同一步，⛔ 不靠"记得手工建"）

```bash
python3 {{AIDP_HOME}}/skills/aidp-code-engineer/scripts/scaffold.py . --version {version} --user {user}
```

目录骨架 / 契约文件 / 工具脚本一律由脚手架产出（`{{AIDP_HOME}}/scripts/`、`.claude/settings.json`、
契约面、docs/memory 版本化骨架、`.gitignore` 规则）；本命令只产**语义内容**。
理由与漏跑后果见 `/sprint-init` Phase 0（同一段，勿在此复述细则）。已有文件不覆盖，可重复执行。

## Phase 1：PM Agent — 项目认知建立

读取 `{{AIDP_HOME}}/agents/pm.md` 获取角色定义。

**Step 1.1：创建项目级 memory 目录**

```bash
mkdir -p memory
```
（目录由 Phase 0 脚手架建出；**内容**暂不生成，交由 `/sprint-init-complete` 处理）

**Step 1.2：生成 memory/projectBrief.md**（项目级）

读取 `docs/requirements/PRD-*.md`（含 `docs/requirements/{version}/产品提供/*.md`），提取项目核心信息。

⛔ **无 PRD 时不得停**：本命令开头已声明 PRD 可选，且全量 `/sprint-init` 有兜底（「如无 PRD，生成空模板占位」）——两条初始化路径产物必须等价。此处同样：**无 PRD 则生成空模板占位**，在文件头标注「待产品补充 PRD 后经 `/sprint-requirements` 回填」。
模板参考 `docs/init/03_memory文件详细规范.md` 第 1 节。

**Step 1.3：生成 memory/productContext.md**（项目级）

分析 PRD 中的功能列表和用户旅程，生成产品上下文；**无 PRD 时同样生成空模板占位**（口径同上）。
模板参考 `docs/init/03_memory文件详细规范.md` 第 2 节。

## Phase 2：Architect Agent — 技术认知建立

读取 `{{AIDP_HOME}}/agents/architect.md` 获取角色定义。

**Step 2.1：分析现有代码和配置**

读取以下内容（存在的都要读）：
- `docs/architecture/`（约束文档）
- `docs/references/`（第三方接口文档，如有）
- `code/`（脚手架关键文件）
- `env/.env`（环境配置）

**Step 2.2：生成 memory/systemPatterns.md**（项目级）

从脚手架代码和约束文档中提取：技术选型总览、系统架构概述、代码规范约定、关键约束、禁止事项、初始 ADR。
模板参考 `docs/init/03_memory文件详细规范.md` 第 3 节。

**Step 2.3：生成 memory/techContext.md**（项目级）

从脚手架代码和 env 中提取：项目代码结构、运行环境要求、快速启动命令、环境变量、外部服务依赖、脚手架参考路径。
模板参考 `docs/init/03_memory文件详细规范.md` 第 4 节。

**Step 2.4：生成 memory/databaseBaseline.md**（项目级）

- 如已有数据库表（从脚手架代码或 SQL 脚本中检测），记录到基线
- 如为全新项目，创建空基线文件（表清单为空，全局约定已填写）
- 填写全局约定（数据库类型、Schema、表名前缀等）
- 模板参考 `docs/init/03_memory文件详细规范.md` 第 5 节（`memory/databaseBaseline.md`）

## 输出

```
✅ /sprint-init-design 完成（初始化前半段）

确定的上下文：
- 起始版本：{version}（已记录，待 /sprint-init-complete 创建 memory 子目录）
- 当前开发者：{user}

生成文件（均为项目级）：
- memory/projectBrief.md ✅ — 项目简介（北极星文件）
- memory/productContext.md ✅ — 产品上下文
- memory/systemPatterns.md ✅ — 架构决策记录
- memory/techContext.md ✅ — 技术上下文
- memory/databaseBaseline.md ✅ — 数据库基线

📋 请审核以上 5 个文件，可根据需要修改内容。

📌 审核完成后，执行 /sprint-init-complete 完成初始化。
```

## 重要提示

- ❌ 不要生成 memory/{version}/{user}/activeContext.md、memory/{version}/{user}/progress.md 或 AGENTS.md
- 这些文件由 `/sprint-init-complete` 在人工审核后生成
- ✅ 会生成 memory/databaseBaseline.md（与 systemPatterns/techContext 一起供审核）
