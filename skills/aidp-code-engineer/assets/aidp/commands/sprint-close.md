# /sprint-close — Sprint 关闭与归档

你正在执行 `/sprint-close` 命令，关闭并归档当前 Sprint。

参数：$ARGUMENTS（Sprint 编号）
格式示例：`/sprint-close 001`

| 参数 | 作用 |
|------|------|
| `--unattended` | **无人值守上下文标记**（由 `/sprint-full` → `/sprint-batch` → `/sprint-autopilot` 逐层透传）：Step 1 的验收状态**不询问用户**，改按下方「无人值守验收派生」机械推导。**⛔ 绝不弹 `AskUserQuestion`** |

如未提供编号，从 `memory/{version}/{user}/activeContext.md` 中读取当前 Sprint 编号。

## 前置流程

**VCS 能力分流**：`{{AIDP_HOME}}/scripts/vcs.py` 的 `detect_mode(Path.cwd())` 给出 `vcs_mode=git|none`，`developer_identity(Path.cwd())` 给出 `{user}`。`vcs_mode=none` 时 Step 1–5 本地验收结论、走查、Sprint 归档与 memory 更新仍可完成；缺 Git 差异时使用 `activeContext.md` 的涉及文件清单作为走查范围。Git-only commit/push/发布交接标 `unsupported:vcs-disabled`，不是 passed；Sprint 本地归档完成不等于版本发布完成，也不得提示已推送或已发布。Git 模式沿用原流程。

按 `docs/init/06_版本与用户目录约定.md`：
1. **{version}** ← 项目记忆文件（路径经 `python3 {{AIDP_HOME}}/scripts/agent_env.py memory-file` 取：`AGENTS.md`，只用 Claude Code 时为 `CLAUDE.md`）「当前状态.当前版本」
2. **{user}** ← `git config user.name`
3. 路径展开见 05_commands详细规范.md。

## 角色：PM Agent

读取 `{{AIDP_HOME}}/agents/pm.md` 获取角色定义，执行"流程 C：Sprint 关闭（/sprint-close）"。

## Step 1：收集关闭信息

读取以下文件：
- `memory/{version}/{user}/activeContext.md` — 当前 Sprint 状态
- `docs/requirements/{version}/` — Sprint 需求
- `docs/testing/{version}/sprint-{NNN}/` — 测试结果（如有）
- `docs/bugfix/{version}/` — Bugfix 记录（如有）

如果用户未提供验收结果，询问每个功能的验收状态：
- ✅ 验收通过
- ⚠️ 部分通过（说明原因）
- ❌ 未通过（说明原因/移入下期）

> ⛔⛔ **无人值守验收派生（带 `--unattended` **或** `--from-batch` 时替代上面的询问，绝不弹窗）**
> —— 后者的语义就是「我在 `/sprint-batch` 的循环体内」，停下来问人同样违反零询问连跑铁律：本门是**每个 Sprint
> 都会撞一次**的关口——`/sprint-batch` → `/sprint-full` → 本命令，跑 N 个 Sprint 就打断 N 次，
> 且每次都恰好落在 Sprint 边界上。它同时违反 `/sprint-batch`「零询问连跑铁律」与
> `/sprint-autopilot`「一次下达 = 做完全流程」，更要命的是：被委派的单 Sprint 子 Agent
> **按「委派安全铁律」根本不能 `AskUserQuestion`**，走到这里既问不了、又没有文档化默认，只能自行发挥。
>
> **验收结论本轮其实已经产出过**，不需要再问人——按下列**确定性优先级**机械推导：
>
> | 序 | 数据源 | 推导 |
> |---|---|---|
> | ① | `docs/testing/{version}/sprint-{NNN}/*-test-report.md` 各功能用例结果 | 全通过 → ✅；有失败 → ⚠️ |
> | ② | 本 Sprint「问题汇总清单」/ `docs/bugfix/{version}/` 未闭环缺陷 | 有未闭环 → ⚠️（附缺陷编号） |
> | ③ | ①②均无数据（如静态-only 轮） | ⚠️ 部分通过 + 注明「无测试证据，按未验证归档」 |
>
> **⛔ 一律不判 ❌「移入下期」**——那是范围决策、属用户职权，无人值守不得代行；确需移出本期
> 由用户事后决定。**⛔ 也不得因推导不出而挂起**：走 ③ 归档并在 `progress.md` 留痕即可。

## Step 2：记录验收结论（不单独出验收报告文件）

验收结论**不单独生成 `验收报告.md`**——其内容由无人值守强制产出的 **AI执行报告** 覆盖（`docs/reports/{version}/AI执行报告/`「需求功能」段承载每功能验收状态、「风险与建议」段承载 Sprint 回顾）。本步只把 Step 1 收集的验收结论**落进 progress.md + Sprint 归档**，不写独立文件：

- 每功能验收状态（✅ 通过 / ⚠️ 部分通过 / ❌ 移入下期）→ 写入 `memory/{version}/{user}/progress.md`「功能模块完成状态」（Step 4 统一更新）
- Sprint 回顾（经验教训）+ 遗留事项 → 随 activeContext 归档进 `memory/{version}/{user}/sprints/sprint-{NNN}.md`（Step 3）
- 手动分步流（无 autopilot、无 AI执行报告）下，progress.md + Sprint 归档即本 Sprint 验收结论的单一记录

## Step 2.5：★ Reviewer Agent 代码走查

读取 `{{AIDP_HOME}}/agents/reviewer.md` 获取 Reviewer Agent 角色定义，对本 Sprint 的代码与设计进行最终走查：

**走查范围**：
- 本 Sprint 涉及的源代码（参考 `memory/{version}/{user}/activeContext.md` 的「本次涉及文件」清单）
- 对照 `docs/design/detail/{version}/` 设计文档目录下全部分册检查实现一致性
- 对照 `docs/architecture/` 检查架构约束符合性
- 对照 `memory/systemPatterns.md` 检查代码规范符合性

**走查维度**：详见 `{{AIDP_HOME}}/agents/reviewer.md` 流程 A（reviewer Agent 为单一信源，命令端不复述具体维度清单）

**输出**（按 `06_版本与用户目录约定.md` §2.2.2 命名）：
- 个人级走查报告：`docs/reports/{version}/review-{user}.md`（若已存在则在文末追加 Sprint 章节）
- 总体结论：✅ 建议合并 / ⚠️ 小问题修复后合并 / ❌ 需要重大修改
- 若发现新 bug → 追加到 `docs/bugfix/{version}/bugfix-{YYYYMMDD}-{user}.md`

**跳过条件**：
- 本 Sprint 仅为文档变更、无代码改动
- 或本项目明确禁用走查环节（在 `memory/projectBrief.md` 中标注）

### Step 2.5.1：★ 实现偏离设计门（机器前置，先跑再走查）

```bash
python3 {{AIDP_HOME}}/scripts/check_design_anchor.py --version {version}   # 0 通过 / 1 Important（或 fail-closed）/ 2 用法错
```

把详细设计里**点名过的字段与常量**逐个到源码里找落点。它专抓一类在本方代码里
**完全看不出问题**的偏离——编译过、类型检查过、界面完整、不报错，但换了个数据来源，
上线后整个功能的每一行都是错值（典型形态：设计写「取 `channel=X` 渠道订单的
`userId`」，实现做成「用 `createBy` 反推」，直到上游反馈才发现）。

- **Important、不是 Critical**：找不到落点不等于错，可能是设计过时。要的是**给出交代**：
  ① 改代码 ② 改设计（并按约定 22 级联）③ 在设计那一行写 `design-anchor-ignore: <理由>`（理由必填）。
- 结果**并入下方 Reviewer 走查报告**（`agents/reviewer.md` 模板的「必须修改 / 建议修改」段），不另出文件。
- 无设计文档 / 无源码 → `[SKIP]` exit 0，不阻塞。

## Step 3：归档 activeContext

> ⛔ **记录取舍与篇幅（约定 9；详规 `{{AIDP_HOME}}/reference/约定细则-5.md` 41.5）**：归档只记
> **事后查不到的判断与取舍**（为什么选这个方案、放弃了什么、留下什么已知失准点）——
> ⛔ 不记 git log 查得到的、文档里已有的、下一轮会重算的。建议上限：**口述累进 ≤40 行 /
> 计划内 Sprint ≤80 行 / 含口径反转 ≤120 行**（超出不阻断，但须自问「这些是不是事后查得到的」）。
> ⛔ 别把 `activeContext.md` 原样整份拷过来当归档——那正是「下一轮会重算的东西」的大头。

将 `memory/{version}/{user}/activeContext.md` 内容**按上述取舍裁剪后**复制到 `memory/{version}/{user}/sprints/sprint-{NNN}.md`。

在文件头部添加归档标记：
```
# Sprint-{NNN} 历史记录（已归档）

> 版本 / 开发者：{version} / {user}
> 归档时间：{当前时间}
> ⚠️ 此文件为只读历史记录，禁止修改
```

## Step 3.5：★ 约定 22 义务登记门（归档里写下的级联义务必须同轮落台账）

```bash
python3 {{AIDP_HOME}}/scripts/check_cascade_obligation.py --version {version} --sprint {NNN}
# 0 通过 / 2 有未登记义务 / 1 fail-closed
```

**为什么必须有这一步**：约定 22 的**机器可扫载体**是四族 `_开发期{族}增量.md`，
而它在上一批级联完成后按规定被删除。若 Sprint 后半段又产生实现期订正、执行体把
「以下四条须按约定 22 回灌」写进**归档 markdown** 却没重建台账，则：收口点扫台账
→ 无待级联 → 不派单；终态门扫台账 → 文件不存在 → 合法终态 → 放行。**义务只活在散文里**，
一直到 build 终审才被 `version-auditor` 判 Critical。该同型问题在实际项目中**连续三个版本复发**。

- **门失败时的处置**：把这些义务**同轮**写进对应族的增量册（骨架 `{{AIDP_HOME}}/templates/_开发期族增量.md`；
  ⛔ 台账被删只表示「当前批已清空」，不表示本版不再需要它——它是 append-only 的活文件，
  新订正须重建），或当场级联完并在归档那一行标「已级联」。
- **本门只断言载体存在**，不做「归档第 N 条 ↔ 台账第 M 条」逐条映射（多条订正常被合并成
  一条台账条目，逐条映射会产出假阳性、最终被加豁免绕过）。归档里的义务原文由脚本逐条打印，
  覆盖是否完整由执行体对照自查。
- **判定自省（写进归档模板的一句话）**：**「收尾门/审计能不能靠脚本发现这条义务？不能 → 它还没被登记。」**

## Step 4：更新 memory/{version}/{user}/progress.md

- Sprint 状态改为「✅ 完成」
- 更新功能模块完成状态
- 追加 Bugfix 统计
- 追加技术债务（如有）

## Step 5：更新 memory/systemPatterns.md（项目级）

将 activeContext 中「关键决策」区域的内容正式追加为 ADR（如有新决策）。
此文件为项目级单一真源，不带版本/用户前缀。

## Step 5.1：★ 收口「子 Agent 必读」踩坑清单（项目级）

扫一遍本轮新踩的坑是否已登记进 `{{AIDP_HOME}}/reference/子Agent必读.md` —— 该文件自称「由开发期持续累积」
并把 `/sprint-close` 列为维护时机，本步即该维护时机的落点。

- **判据**：本轮 `/sprint-bugfix` 修过的缺陷、开发中绕过的环境/技术栈陷阱、子 Agent 反复问到的同一件事
  → 各自应在该文件对应段落有一条。已在则跳过，缺则**当轮补上**（别等"以后整理"）。
- **同时清理过期条目**：环境/技术栈已变更的坑要删——过期的坑会把子 Agent 引向错误做法，比没有更糟。
- **无新增即跳过**，不产生空动作、不写占位。

> ⛔ 该文件是**用户填充型契约**：脚手架只发骨架，填过之后升级不再覆盖（`scaffold.py` 按占位符判定）。
> 所以内容丢不丢，取决于本步有没有真的往里写。

## Step 5.2：★ 更新 memory/databaseBaseline.md（项目级）

读取本次 Sprint 的数据库设计文档（`docs/design/detail/{version}/02_数据库设计.md`；裸名 `数据库设计.md` 为历史兼容，按 glob `*数据库设计.md` 匹配即可）：
- 将本次新增的表追加到「已有表清单」
- 将本次变更的表更新到「已有表清单」（标注最后变更 Sprint）
- 在「变更历史」中追加本次 Sprint 的记录
- 更新「表关系概览」（如有变化）

## Step 6：重置 memory/{version}/{user}/activeContext.md

清空并设为等待下一个 Sprint 的状态。保留「当前上下文」的 `{version}` 和 `{user}` 字段。

## Step 7：更新项目记忆文件

路径经 `python3 {{AIDP_HOME}}/scripts/agent_env.py memory-file` 取（⛔ 不写死 `AGENTS.md`），定点更新「当前状态」为：
- 当前版本：{version}（保持）
- 当前开发者：{user}（保持）
- 当前 Sprint：Sprint-{NNN} 已关闭，等待 Sprint-{NNN+1}

## Step 8：输出关闭报告

```
✅ Sprint-{NNN} 已关闭（{version} / {user}）

验收摘要：
- 完成：{N} 个功能
- 部分完成：{N} 个
- 移入下期：{N} 个
- Bugfix：提出 {N} / 修复 {N} / 待修复 {N}

📋 生成/更新的文件：
- memory/{version}/{user}/sprints/sprint-{NNN}.md（归档）
- memory/{version}/{user}/progress.md（已更新）
- memory/systemPatterns.md（项目级，如有新 ADR）
- memory/databaseBaseline.md（项目级，★ 已更新，新增/变更表已同步）
- memory/{version}/{user}/activeContext.md（已重置）
- AGENTS.md（已更新）

📌 下一步：
  /sprint-start {NNN+1} [--unattended]（无人值守时透传）→ 开始下一个 Sprint（Sprint 目标自动取自 01_研发执行计划.md，不传第二参数）
  /version {version}            → 本版本全部 Sprint 完成后发布（打 tag）
```
