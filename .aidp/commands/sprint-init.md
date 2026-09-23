# /sprint-init — 项目全量初始化

你正在执行 `/sprint-init` 命令，进行项目全量初始化。此命令在整个项目生命周期中只执行一次。

**★ 定位**：
- 生成 **memory 骨架**（项目级 L1/L2 文件 + 迭代级 L3/L4 目录）
- 生成 **docs/architecture/ 空模板**（架构约束/技术选型/UI 规范约束）
- 生成 **AGENTS.md** 主入口

**★ 初始化后续**：用户执行 `/version V0.1.0 "M1 MVP"` 时，`/sprint-design` 会动态填充 architecture 文档的真实内容。

## 前置流程

1. **{version}**：询问用户起始版本号（建议 `V0.0.1` 或 `V0.1.0`）
2. **{user}**：执行 `git config user.name`；非法/为空则询问用户短标识
3. 路径展开：项目级 memory 在 `memory/` 根；迭代级 memory 在 `memory/{version}/{user}/`

## 前置检查

1. 确认 `docs/init/` 目录存在（AIDP 范式文档，应含 00-06 共 7 个主文件）
2. 确认 `docs/requirements/PRD-*.md` 存在（可选，无也能初始化）
3. 检查 `memory/` 目录是否已存在（如已存在，警告用户并确认是否覆盖）

## Phase 0：★ 确定性骨架产出（先跑脚手架，⛔ 不靠"记得手工建"）

本命令的 Phase 1/2 产出的是**语义内容**（项目认知、架构约束、技术选型），而**目录骨架 /
契约文件 / 工具脚本**是确定性的，必须由脚手架脚本产出：

```bash
python3 {{AIDP_HOME}}/skills/aidp-code-engineer/scripts/scaffold.py . --detect          # 先探测模式（init / migrate / upgrade）
python3 {{AIDP_HOME}}/skills/aidp-code-engineer/scripts/scaffold.py . --version {version} --user {user}   # 模式默认 auto；需指定时加 --mode <mode> --agent <agents>
```

它负责（本命令**不重复实现、也不用 `mkdir -p` + `touch` 手搓**）：`{{AIDP_HOME}}/scripts/`（约定 24 要求每次
commit 前跑的 `commit_gate.py` 就在其中）、`.claude/settings.json`（Claude Code 适配层配置）、
`{{AIDP_HOME}}/{agents,commands,rules,flows,reference,hooks,templates}` 契约面、`docs/` 与 `memory/`
版本化骨架（含 `memory/aidp-config.yaml`）、`.gitignore` 规则。

> ⚠️ **漏跑这一步的后果不是"少几个空目录"**：项目记忆文件（AGENTS.md / CLAUDE.md）的意图路由把「初始化项目 /
> 接入 AIDP / 第一次跑」全部指向本命令，走这条路的项目跑完会**缺 `{{AIDP_HOME}}/scripts/` 与
> `memory/aidp-config.yaml`**——约定 24 的 commit 前门禁与约定 32 的里程碑通知装配双双落空，
> 而这些缺失只能靠事后 `verify.py` 报错 + 人工补。两条初始化路径（本命令 / 脚手架）
> 在本步交汇。
>
> 已由脚手架建好的文件**一律不覆盖**（create-if-missing 语义），故本步可重复执行。

## Phase 1：PM Agent — 项目认知建立

读取 `{{AIDP_HOME}}/agents/pm.md` 获取角色定义。

**Step 1.1：创建目录结构**

```bash
# ⛔ 目录骨架不在本步手搓：Phase 0 的脚手架已确定性建出全部目录（手搓块是第二份骨架真相、必然漂移）。
#    骨架缺 docs/requirements/{version}/研发需求 会让 /sprint-start 前置门直接以"需求文档不存在"停止。
#    ★ 目录清单单一信源 = scaffold_lib.py::skeleton_dirs（约定 21）。本步只做核验：
python3 {{AIDP_HOME}}/skills/aidp-code-engineer/scripts/verify.py . {version} {user} 2>&1 | grep -E "\[ERROR\].*(目录|directory)" && {
  echo "❌ Phase 0 骨架不完整——回到 Phase 0 重跑 scaffold.py，⛔ 不要在此手工 mkdir 补"; exit 1
}
echo "✅ 目录骨架核验通过（由 Phase 0 脚手架产出）"
```

**Step 1.2：生成 memory/projectBrief.md**（项目级）

读取 `docs/requirements/PRD-*.md`（如有），提取项目核心信息。
如无 PRD，生成空模板占位。
模板参考 `docs/init/03_memory文件详细规范.md` 第 1 节。

**Step 1.3：生成 memory/productContext.md**（项目级）

分析 PRD 中的功能列表和用户旅程（如有），生成产品上下文。
如无 PRD，生成空模板占位。

## Phase 2：Architect Agent — 技术认知建立

读取 `{{AIDP_HOME}}/agents/architect.md` 获取角色定义。

**Step 2.1：生成 docs/architecture/ 空模板**

**仅当对应文件不存在时**才创建空模板（create-if-missing，同 `/sprint-init-complete` Step 4.1；后续由 `/sprint-design` 根据实际设计动态填充）——⛔ **已存在则原样保留、只列跳过清单**：无条件创建会覆盖掉 `migrate.py` 从 bundle 拷入的带模板头版本，此后 `_refresh_arch_header` 因判据（模板头标记）丢失而永久判「疑似手写覆盖」、只落一行 WARN，该项目再也收不到填写规范更新；已有真实团队约束但尚无 `memory/` 的项目也会被静默抹掉：

**`docs/architecture/架构约束.md`**：
```markdown
# 架构约束

> ⚠️ 此文件为空模板，由项目初始化时创建。
> 后续每次 `/sprint-design` 执行时会根据实际设计动态更新/追加内容。
> 人工可随时直接编辑此文件补充团队约束（如强制规范）。

## 分层架构约束
（待 /sprint-design 生成或人工补充）

## 命名规范约束
（待 /sprint-design 生成或人工补充）

## 安全约束
（待 /sprint-design 生成或人工补充）

## 性能约束
（待 /sprint-design 生成或人工补充）

## 禁止事项（反模式）
（待 /sprint-design 生成或人工补充）

## 变更历史

| 时间 | 变更人 | 变更内容 | 关联 Sprint |
|------|--------|---------|-------------|
| YYYY-MM-DD | {user} | 初始化创建空模板 | - |
```

**`docs/architecture/技术选型.md`**：
```markdown
# 技术选型

> ⚠️ 此文件为空模板。由 `/sprint-design` 调用 `dev-logic-architect` skill 时，
> 根据生成的详细设计动态填充/追加。

## 技术栈总览

| 层级 | 技术 | 版本 | 选型理由 | 关联 Sprint |
|------|------|------|---------|-------------|
| 前端框架 | - | - | - | - |
| UI 组件库 | - | - | - | - |
| 后端框架 | - | - | - | - |
| ORM / 数据访问 | - | - | - | - |
| 主数据库 | - | - | - | - |
| 缓存 | - | - | - | - |
| 构建工具 | - | - | - | - |
| 第三方服务 | - | - | - | - |

## 选型决策记录

（由 `/sprint-design` 追加每次 Sprint 引入的新技术决策）

## 变更历史

| 时间 | 变更人 | 变更内容 | 关联 Sprint |
|------|--------|---------|-------------|
| YYYY-MM-DD | {user} | 初始化创建空模板 | - |
```

**`docs/architecture/UI规范约束.md`**：
```markdown
# UI 规范约束

> ⚠️ 此文件为空模板。由 UI Agent 在 `/sprint-design` 时根据原型分析动态填充。

## 品牌色彩体系

（待填充：主色、辅色、背景色、文字色）

## 字体规范

（待填充：字号、字重、行高）

## 间距与圆角

（待填充）

## 组件样式规范

（待填充：按钮、表格、卡片、表单）

## 布局规范

（待填充：页面宽度、栅格系统、侧边栏宽度）

## 响应式断点

（待填充）

## 变更历史

| 时间 | 变更人 | 变更内容 | 关联 Sprint |
|------|--------|---------|-------------|
| YYYY-MM-DD | {user} | 初始化创建空模板 | - |
```

**Step 2.2：生成 memory/systemPatterns.md**（项目级）

从脚手架代码和约束文档中提取：技术选型总览、系统架构概述、代码规范约定、关键约束、禁止事项、初始 ADR。
如无脚手架，生成空模板占位。
模板参考 `docs/init/03_memory文件详细规范.md` 第 3 节。

**Step 2.3：生成 memory/techContext.md**（项目级）

从脚手架代码和 env 中提取：项目代码结构、运行环境要求、快速启动命令、环境变量、外部服务依赖、脚手架参考路径。
如无脚手架，生成空模板占位。

**Step 2.4：生成 memory/databaseBaseline.md**（项目级）

- 如已有数据库表（从脚手架代码或 SQL 脚本中检测），记录到基线
- 如为全新项目，创建空基线文件（表清单为空）
- 填写全局约定（数据库类型、Schema、表名前缀等）

## Phase 3：UI Agent — 原型认知建立（可选）

如 `docs/prototype/{version}/code/` 存在原型代码：
- 逐文件分析 UI 原型代码
- 提取视觉特征回填 `docs/architecture/UI规范约束.md` 的初版

如无原型代码，跳过。

## Phase 4：PM Agent — 完成初始化

**Step 4.1：生成 memory/{version}/{user}/activeContext.md**（迭代级）

初始状态：项目已初始化，等待 `/version` 版本规划。
头部「当前上下文」填入 `{version}` 和 `{user}`。

**Step 4.2：生成 memory/{version}/{user}/progress.md**（迭代级）

初始状态全部为"⏳ 未开始"。
「版本历史」表格追加：`| {version} | - | M0 初始化 | - | 🚧 开发中 | - |`

**Step 4.3：回填 AGENTS.md 的「当前状态」区**

⛔ **本文件不由本步生成**：Phase 0 的 `scaffold.py::sync_memory_file` 已 create-if-missing 从
`AGENTS.md.tpl` 渲染出完整文件（核心约定 + Agent 路由 + reference/rules 指针）。照字面"生成"
= 用手写近似版覆盖它，让主入口失去确定性生产者。路径经 `python3 {{AIDP_HOME}}/scripts/agent_env.py memory-file` 取（只用 Claude Code 时为 `CLAUDE.md`）。

本步**只定点回填**「当前状态」区的 `{version}` / `{user}` 两个字段，⛔ 不重写正文任何其他部分。

## 输出

```
🎉 项目初始化完成！版本：{version} / 开发者：{user}

📁 生成的目录骨架：
- memory/（项目级 5 个文件 + 迭代级 {version}/{user}/）
- docs/architecture/（3 个空模板：架构约束 / 技术选型 / UI规范约束）
- docs/requirements/{version}/ ~ docs/implementation/{version}/{user}/
- docs/prototype/{version}/（code + mockup）
- docs/deployment/{version}/sql/增量/ （SQL 部署资产，按版本目录组织：`{NN}_<中文名>.sql`；上游 SKILL 暂存 code/sql/ → 命令端搬迁；详见 /sprint-design Step 3）

📋 生成的空模板文件：
- memory/projectBrief.md / productContext.md（待 PRD 补充）
- memory/systemPatterns.md / techContext.md / databaseBaseline.md（待脚手架分析）
- docs/architecture/架构约束.md（待 /sprint-design 填充）
- docs/architecture/技术选型.md（待 /sprint-design 填充）
- docs/architecture/UI规范约束.md（待 UI Agent 填充）
- memory/{version}/{user}/activeContext.md / progress.md

> `AGENTS.md` **不在本清单内**——它由 Phase 0 `scaffold.py::sync_memory_file` 产出（非空模板），本命令只回填「当前状态」区。

📌 下一步：
★ 执行 /version {version} "M1 MVP" 开始版本规划
  该命令会：
  1. /sprint-requirements → 生成版本需求（调用 ux-logic-extractor）
  2. /sprint-design       → 生成详细设计 + 动态更新 architecture（调用 dev-logic-architect）
  3. /sprint-plan         → 生成研发执行计划（调用 dev-execution-planner）
  4. /sprint-selftest     → 生成研发自测方案 + 自测用例 + 测试环境与账号（调用 dev-manual-testcase）

然后即可使用三个★常用入口：
- /sprint-batch                       批量执行所有 Sprint
- /sprint-dev "<新功能描述>"          自动累进新 Sprint
- /sprint-bugfix                       修复已记录的 bug
```
