# /sprint-init-complete — 初始化后半段（分步模式）

你正在执行 `/sprint-init-complete` 命令，这是项目初始化的后半段。

此命令在用户审核完 `/sprint-init-design` 生成的记忆文件后执行，
完成 Phase 3（UI Agent）和 Phase 4（PM Agent），最终完成项目初始化。

## 前置流程

1. **{version}**：优先读取 `AGENTS.md` 草稿中的版本；否则询问用户（应与 `/sprint-init-design` 阶段保持一致）。
2. **{user}**：`git config user.name`。
3. 本阶段创建迭代级 memory 目录 `memory/{version}/{user}/` 与 docs 版本/用户目录骨架。

## 前置检查

验证以下项目级文件必须已存在（由 `/sprint-init-design` 生成）：
1. `memory/projectBrief.md`
2. `memory/productContext.md`
3. `memory/systemPatterns.md`
4. `memory/techContext.md`
5. `memory/databaseBaseline.md`

如果任何文件缺失，停止执行并提示用户先执行 `/sprint-init-design`。

### ★ Phase 0：脚手架契约装配（与全量 `/sprint-init` 同款，⛔ 不可省）

⛔ **只验上面 5 个 memory 文件是不够的**——那 5 个文件手工凑齐即可通过，而 `.aidp/scripts/`、
`.claude/settings.json`、`.aidp/{agents,commands,rules,flows,reference,templates}` 等契约面
全部由脚手架产出。跳过本 Phase 会得到一个"memory 齐、契约空"的项目，后续所有命令的确定性
脚本调用都会 `No such file`。

```bash
python3 .aidp/skills/aidp-code-engineer/scripts/scaffold.py . --version {version} --user {user}
```

产出物与幂等性同 `/sprint-init` Phase 0（create-if-missing，已存在一律不动）。

## Phase 3：UI Agent — 原型认知建立（可选）

如果 `docs/prototype/{version}/code/` 目录存在，读取 `.aidp/agents/ui.md` 获取角色定义：

- ★ 检查 `docs/prototype/{version}/mockup/` 是否有人工高保真图片
- 逐文件分析 UI 原型代码
- 生成组件映射清单（原型组件 → 项目技术栈组件）

如果 `docs/prototype/{version}/code/` 不存在，跳过此阶段。

## Phase 4：PM Agent — 完成初始化

读取 `.aidp/agents/pm.md` 获取角色定义。

**重要**：先重新读取用户可能已修改的 5 个项目级记忆文件（含 databaseBaseline.md），以确保后续生成的文件与审核后的内容一致。

**Step 4.1：创建迭代级目录骨架**

```bash
# ⛔ 目录骨架不在本步手搓：单一信源 = scaffold_lib.py::skeleton_dirs（约定 21），手搓块是第二份骨架真相、必然漂移。本步只核验：
python3 .aidp/skills/aidp-code-engineer/scripts/verify.py . {version} {user} 2>&1 | grep -E "\[ERROR\].*(目录|directory)" && {
  echo "❌ 骨架不完整——先跑下方 Phase 0 的 scaffold.py，⛔ 不要手工 mkdir 补"; exit 1
}
echo "✅ 目录骨架核验通过"
```

> ★ **架构约束模板补齐**：若 `docs/architecture/{架构约束,技术选型,UI规范约束}.md` 不存在，按 `/sprint-init` 同款生成空模板骨架（动态填充），保证分步 init 与全量 init 等价、`/sprint-design` 阶段有架构约束可读。

**Step 4.2：生成 memory/{version}/{user}/activeContext.md**

初始状态：项目已初始化，等待 Sprint-001。
头部「当前上下文」填入 {version} 和 {user}。
模板参考 `docs/init/03_memory文件详细规范.md` 第 6 节（`memory/{version}/{user}/activeContext.md`）。

**Step 4.3：生成 memory/{version}/{user}/progress.md**

从已审核的 `memory/productContext.md` 中提取功能模块，初始状态全部标记为「⏳ 未开始」。
「版本历史」表格追加一行：`| {version} | - | M0 初始化 | - | 🚧 开发中 | - |`
模板参考 `docs/init/03_memory文件详细规范.md` 第 7 节（`memory/{version}/{user}/progress.md`）。

**Step 4.4：回填 AGENTS.md 的「当前状态」区**

⛔ **本文件不由本步生成**：`scaffold.py::sync_memory_file` 已 create-if-missing 从 `AGENTS.md.tpl`
渲染出完整文件（路径经 `python3 .aidp/scripts/agent_env.py memory-file` 取）；本步**只定点回填**「当前状态」区的 `{version}` / `{user}`，⛔ 不重写正文。

（以下为该文件正文应含内容的说明，仅供核对、不作为重写依据）项目信息、Agent 路由表、可用命令列表（含 `/version`）、初始化输入文件清单、核心约定。
模板参考 `docs/init/03_memory文件详细规范.md` 第 9 节。

## 输出

```
🎉 项目初始化完成！版本：{version} / 开发者：{user}

生成文件清单：
memory/（项目级，Phase 1-2 已生成并审核）
  ├── projectBrief.md ✅
  ├── productContext.md ✅
  ├── systemPatterns.md ✅
  ├── techContext.md ✅
  └── databaseBaseline.md ✅

memory/{version}/{user}/（迭代级，本阶段生成）
  ├── activeContext.md ✅
  ├── progress.md ✅
  └── sprints/ ✅（空）

docs/{各 category}/{version}/ 骨架（implementation/memory 保留 {user} 层）：✅ 已创建
docs/prototype/{version}/mockup/、docs/deployment/{version}/ 骨架：✅ 已创建

AGENTS.md ✅

📌 下一步：
方式A（分步执行）：
  /version（版本规划） → 生成研发需求/设计/执行计划文档（可人工审核）
  /sprint-start 001 → 启动已规划的 Sprint-001
  /sprint-dev → 开发实现
  /sprint-test → 测试

方式B（全量执行）：
  /sprint-full 001 → 单 Sprint 一键（start→dev→test→bugfix→close）
```
