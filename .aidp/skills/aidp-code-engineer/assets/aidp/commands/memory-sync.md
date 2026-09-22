# /memory-sync — 记忆同步

你正在执行 `/memory-sync` 命令，将当前会话中的进展同步到记忆文件。

## 前置流程

按 `docs/init/06_版本与用户目录约定.md`：
1. **{version}** ← 项目记忆文件（`python3 {{AIDP_HOME}}/scripts/agent_env.py memory-file` 取路径；下文记作 `AGENTS.md`）「当前状态.当前版本」
2. **{user}** ← `git config user.name`
3. 迭代级记忆文件全部位于 `memory/{version}/{user}/` 下；项目级记忆文件在 `memory/` 根。

## 触发时机

- ✅ 完成一个功能模块
- ✅ 完成一个开发阶段（如后端完成，前端开始前）
- ✅ 遇到阻塞问题
- ✅ 做出技术决策
- ✅ 修复 bugfix 后
- ✅ 每天工作结束时

## Step 0：写前快照（⛔ 任何写入之前）

```bash
python3 {{AIDP_HOME}}/scripts/check_memory_loss.py --snapshot
```

把受保护文件（项目级 memory 五件套 + 项目记忆文件 + `memory/{version}/{user}/{activeContext,progress}.md`）的**工作区现状**存为比对基线——未提交的手写内容也因此受保护。

## Step 1：扫描当前会话

回顾本次会话中的所有操作，识别：
- 已完成的工作
- 新的技术决策
- 遇到的问题/阻塞
- 环境变更
- Bugfix 修复结果

## Step 2：更新 memory/{version}/{user}/activeContext.md

读取并更新以下区域：
- **已完成工作**：追加本次完成项
- **当前工作焦点**：更新为下一步计划
- **关键决策**：追加新的技术决策
- **阻塞问题**：追加新阻塞 / 标记已解除的阻塞
- **子迭代记录**：追加 Round 记录
- **待处理 Bugfix**：更新状态

## Step 3：按需更新其他文件

> ⛔⛔ **本步一律「追加 / 定点改写」，绝不整段重写、绝不覆盖用户手写内容**（硬约束）。
> 下列文件是**项目级长期记忆**，其中相当一部分由人手写、且往往是仓库里唯一一份记录：
> `memory/projectBrief.md` / `productContext.md` / `systemPatterns.md` / `techContext.md` /
> `databaseBaseline.md`。**覆盖即永久丢失**——它们不像代码那样有第二处副本可对照。
>
> 三条可执行判据：
> 1. **只动本次会话真正涉及的那一段**：ADR 追加到「架构决策记录」段末尾、技术债追加到
>    「已知问题和技术债务」段末尾；⛔ 不重排、不合并、不"顺手优化"既有条目的措辞。
> 2. **「更新 `techContext.md`」= 改动那一条环境项，不是重写整份**。看到需要大范围改写时
>    停下来问用户，不要自行决定"这样写更好"。
> 3. **写前先读**：任何一份要改的文件——**memory 文件与 `AGENTS.md` 同等适用**（后者在下游是内联了全部核心约定的自包含单文件、最不可再生）——必须先 Read 全文再定点编辑，
>    ⛔ 不得凭对文件结构的印象直接 Write 整份。
>
> **★ Step 2、Step 3 全部写完后必跑（确定性落点，⛔ 不是「最好跑一下」）**：
>
> ```bash
> python3 {{AIDP_HOME}}/scripts/check_memory_loss.py
> ```
>
> 它拿工作区与 Step 0 的快照比（无快照时回落 `git HEAD`），覆盖 Step 2 的 `activeContext.md` / `progress.md`：**L1 段落消失 / L2 段落塌缩 ≥40% / L3 整份塌缩** 任一命中即 exit 1；通过后自动清理快照。
> 填掉 `（待填充）` 占位符**不算丢失**（那正是约定 8 要求的动作，按标题前缀匹配）。
> 报红即按提示从快照（`memory/.aidp/memory-snapshot/<文件>`）或 `git show HEAD:<文件>` 取回被吞的段落，⛔ 不得以「本次就是要精简」为由径直 commit。
>
> **Why**：「整段重写吞掉手写内容」与「本次确实没改那一段」在仓库里完全同形——
> 光靠纪律，失效时不可观测，所以必须有这道确定性检测。本步的动词是「追加」「更新」，
> 而「更新」在无约束时会被读成「重写」。

根据本次会话的内容，判断是否需要更新：

- **新技术决策** → 追加 ADR 到 `memory/systemPatterns.md`（项目级）
- **环境变更** → 更新 `memory/techContext.md`（项目级）
- **新技术债务** → 追加到 `memory/techContext.md` 的「已知问题和技术债务」章节（项目级）
- **本人模块进度变化** → 更新 `memory/{version}/{user}/progress.md`
- **主入口状态需刷新** → 更新 `AGENTS.md`「当前状态」区域

## Step 4：输出同步摘要

```
✅ /memory-sync 完成（{version} / {user}）

已同步：
  已完成：
    - {任务1} ✅
    - {任务2} ✅
  当前焦点：
    {下一步计划}
  更新的文件：
    - memory/{version}/{user}/activeContext.md ✅
    - memory/systemPatterns.md {✅/无变更}（项目级）
    - memory/techContext.md {✅/无变更}（项目级）
    - memory/{version}/{user}/progress.md {✅/无变更}
    - AGENTS.md {✅/无变更}
```
