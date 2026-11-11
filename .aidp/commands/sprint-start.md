# /sprint-start — Sprint 启动（执行模式）

## 执行身份与授权前置路由（先于本文其余动作）

先 Read `{{AIDP_HOME}}/flows/sprint-dev/light-context.md`。按原参数解析父上下文与显式 Sprint；历史计划和 activeContext 不决定本任务身份。

`POLICY_ARGS` 仅新任务按 `light-context.md`「入口、继承与 grant revision」生成；嵌套只继承，后文每个动作先过该片围栏。

```bash
# EXECUTION_CONTEXT 来自入参；EXPLICIT_SPRINT 仅来自用户明确的 Sprint，不读 activeContext 推导。
CONTEXT_ARGS=()
if [ -n "${EXECUTION_CONTEXT:-}" ]; then
  CONTEXT_ARGS+=(--execution-context "$EXECUTION_CONTEXT")
else
  CONTEXT_ARGS+=(--version "{version}" "${POLICY_ARGS[@]}")
  for W in "${TASK_WRITE_SET[@]}"; do CONTEXT_ARGS+=(--write-set "$W"); done
  for AC in "${TASK_ACCEPTANCE[@]}"; do CONTEXT_ARGS+=(--acceptance "$AC"); done
  [ -z "${EXPLICIT_SPRINT:-}" ] || CONTEXT_ARGS+=(--sprint "$EXPLICIT_SPRINT")
fi
CONTEXT_RESULT=$(python3 {{AIDP_HOME}}/scripts/entry_context.py resolve --root . --entry sprint-start \
  "${CONTEXT_ARGS[@]}" --json) || exit $?
EXECUTION_CONTEXT=$(printf '%s' "$CONTEXT_RESULT" | python3 -c 'import json,sys; print(json.load(sys.stdin)["execution_context"])') || exit $?
# 消费 resolve 返回的 execution_context 为 EXECUTION_CONTEXT，再路由。
python3 {{AIDP_HOME}}/scripts/entry_context.py route --root . --entry sprint-start \
  --execution-context "$EXECUTION_CONTEXT" --phase prepare --json
```

返回 `route=light` → 执行该片的 **prepare** 能力，然后 **return**；不进入下文任何 Sprint 取号、卡片、activeContext、started、报告路径或归档步骤。返回 `route=formal` 才执行下文正式身份门；可选动作仍按 actions 筛选，未授权为 NOT_REQUESTED。任何子命令/修复/重试/续跑均保留原参数并显式附 `--execution-context "$EXECUTION_CONTEXT"`；不能只传 `--unattended`/`--from-batch` 而丢身份。

## formal 流程

你正在执行 `/sprint-start` 命令，启动当前 Sprint 的执行。

**★**：普通计划路径读取既有需求/设计；日常 S/M 累进读取已放行契约卡及稳定基线。本命令只负责读取规格、更新状态、启动执行，不重复成文。

参数：$ARGUMENTS
请从参数中解析 Sprint 编号。
格式示例：`/sprint-start 001`

如果参数不完整，询问用户提供 Sprint 编号。

| 参数 | 说明 |
|------|------|
| `--unattended` | **无人值守上下文标记**（由 `/sprint-full` → `/sprint-batch` → `/sprint-autopilot` 逐层透传）：本命令全程**⛔ 绝不弹 `AskUserQuestion`**——参数不完整或前置检查不通过时直接输出原因并停止，交上层编排按失败信号处理。 |

## 前置流程

按 `docs/init/06_版本与用户目录约定.md`：
1. **{version}** ← 项目记忆文件（路径经 `python3 {{AIDP_HOME}}/scripts/agent_env.py memory-file` 取：`AGENTS.md`，只用 Claude Code 时为 `CLAUDE.md`）「当前状态.当前版本」
2. **{user}** ← `python3 {{AIDP_HOME}}/scripts/vcs.py user`（唯一解析实现：显式 → 本地 Git 身份 → `AIDP_USER` → OS 用户；⛔ 别自己拼 `git config user.name`，无 Git 项目上会解析出另一个身份）
3. 后续路径全部使用解析到的 `{version}` / `{user}`。

## 前置检查

**日常累进契约入口**：若调用方传来 `docs/design/detail/{version}/_sprint-{NNN}-契约卡.md`，先 Read `{{AIDP_HOME}}/flows/sprint-dev/incremental-contract.md`。解析其唯一 `aidp-contract` fenced JSON 块，按协议核 version/sprint/owner 与本轮一致、正整数修订、`status=approved` 且 `approved_revision=contract_revision`，不能仅凭文件存在放行；解析失败、重复块/键、身份不符或 draft 均停止契约路径。S/M 可从卡的 REQ/AC/Task/依赖取得本 Sprint 范围，以下需求/计划/设计前置项以“既存版本基线＋已放行契约”满足，不要求新 Task 已成正式计划；L 仍须正式文档硬门通过。未传卡或卡缺项时保持普通计划路径，不凭空生成替代规格；未关闭 Sprint 门与启动记录无论档位都执行。

1. ★ **确认无未关闭的 Sprint（约定 9 前置门；确定性判据，⛔ 不靠读 `activeContext.md` 自行裁量）**：

   ```bash
   python3 {{AIDP_HOME}}/scripts/check_open_sprints.py --version {version} --scope started --json
   OPEN_RC=$?
   ```
   - 退出码 `0` → 无已启动但未关闭的 Sprint → 继续步骤 2（未来计划不算在途）。
   - 退出码 `2` → 状态读取失败或参数错误，停止并修复输入；无人值守返回失败信号。
   - 退出码 `1` → **停止执行**，把输出里的 `open[]` 原样列给用户，提醒先 `/sprint-close` 收口。
     ⛔ **不得记一笔告警然后往下走** —— 那等于这道门不存在；也⛔ 不得以"看起来没在跑"为由放行。

   > **判据单一信源 = 该脚本的 `started` 范围**：跨用户读启动记录与存量显式当前状态，扣除同时具备同行 ✅ 与 `sprints/sprint-NNN.md` 归档文件的关闭记录。
   > 未开始的计划不阻断开工；交付收尾仍按全部计划检查。⛔ 不改回执行体只看自己 activeContext 的临场判断。
2. **确认需求文档已存在**：`ls docs/requirements/{version}/研发需求/{01_研发需求,00_索引,00_研发需求}.md 2>/dev/null` 任一命中即可（**不硬编码裸名**——multi 模式按系统拆分时 `01_研发需求.md` 本就不存在，硬判会把合规项目误判缺失而**错误停止执行**；口径同 `/sprint-design` 前置门）
   - 若不存在 → **停止执行**，提示"需求文档不存在，请先执行 /version 进行版本规划"
3. **确认研发执行计划已存在**：`ls docs/plans/{version}/{01_研发执行计划,00_索引,00_研发执行计划}.md docs/plans/{version}/NN_研发执行计划-*.md 2>/dev/null` 任一命中即可（**不硬编码裸名**——`/sprint-plan` 对多用户产 `NN_研发执行计划-{开发者}.md`、按内容量拆分产 `02_` 起分册，硬判会把这两类合规产出误判缺失而**错误停止执行**）
   - 若不存在 → **停止执行**，提示"研发执行计划不存在，请先执行 /sprint-plan 或 /version"
4. **确认设计文档已存在**：`docs/design/detail/{version}/`
   - 若不存在 → **停止执行**，提示"设计文档不存在，请先执行 /version 进行版本规划"

## Step 1：读取计划与需求（职责分离）

**Step 1.1 从研发执行计划获取本 Sprint 的"何时做"**

S/M 日常累进先从已放行契约卡的执行工作单取本轮 Task、目标、依赖和 AC；正式计划尚在生成时不得误读旧 Sprint。其它路径从 `docs/plans/{version}/00_索引.md` 定位执行计划正文（无索引的存量项目扫描该目录内容），包含主文档、人员/里程碑分册与 `NN_Phase*.md` 任务分册。在其中定位 `Sprint-{NNN}` 及其 Task，提取：
- **Sprint 目标**（一句话）
- **包含的功能模块列表**
- **开始 / 结束日期**与时间估算
- **任务分配**（如有）
- **依赖与风险**

**Step 1.2 从研发需求获取本 Sprint 的"做什么"**

读取 `docs/requirements/{version}/研发需求/01_研发需求.md`（或拆分后的 `0?_*.md`），按 Step 1.1 拿到的功能模块列表过滤，加载这些功能的：
- 功能描述
- 验收标准（AC）
- 排除项
- 依赖
- 增量需求章节（如 `增量需求：Sprint-{NNN}`，是追溯标记）

## Step 2：更新 memory/{version}/{user}/activeContext.md

重置并更新 activeContext（S/M 本轮字段来源为契约卡，以下正式计划/需求来源用于普通计划路径；显式写 `contract_path: <相对路径>`、`contract_revision: <与卡一致的正整数>`、dev_scale 和改动前基线引用；后续恢复只读核对，不重置上下文）：
- 当前 Sprint：Sprint-{NNN}
- Sprint 目标（**来源：`*研发执行计划*.md`（全部分册）**）
- 本次迭代范围 = 功能模块列表 + 各模块的验收标准（**来源：`*研发执行计划*.md`（全部分册） + 研发需求/01_研发需求.md 联合**）
- 开始 / 结束日期（**来源：`*研发执行计划*.md`（全部分册）**）
- 当前工作焦点：等待开发
- 子迭代记录：清空，准备记录新的 Round

## Step 3：更新项目记忆文件

路径经 `python3 {{AIDP_HOME}}/scripts/agent_env.py memory-file` 取（⛔ 不写死 `AGENTS.md`），定点更新「当前状态」区域：
- 当前 Sprint：Sprint-{NNN}
- 当前阶段：执行中

状态置位后登记确定性启动记录（写入失败即本步失败，无人值守交上层处理）：

```bash
python3 {{AIDP_HOME}}/scripts/check_open_sprints.py --version {version} --record-start {NNN} --user "{user}"
START_RC=$?
[ "$START_RC" = 0 ] || { echo "❌ Sprint 启动记录写入失败"; exit "$START_RC"; }
```

## 输出

```
✅ Sprint-{NNN} 已启动（执行模式）

版本 / 开发者：{version} / {user}
Sprint 目标：{来源：`*研发执行计划*.md`（全部分册）}
功能数量：{N} 个
开始 / 结束：{date} / {date}（来源：`*研发执行计划*.md`（全部分册））

📋 输入文档（已存在）：
- docs/plans/{version}/*研发执行计划*.md — Sprint 范围、目标、排期、任务分配（拆分态含多份）
- docs/requirements/{version}/研发需求/01_研发需求.md — 功能描述、验收标准

📋 设计文档（已存在）：
- docs/design/detail/{version}/*详细设计.md（glob 兼容 `01_详细设计.md` 与历史裸名）
- docs/design/detail/{version}/*接口设计.md（glob 兼容 `03_接口设计.md` 与历史裸名）
- docs/design/detail/{version}/*数据库设计.md（glob 兼容 `02_数据库设计.md` 与历史裸名）

🔄 已更新：
- memory/{version}/{user}/activeContext.md
- 项目记忆文件（AGENTS.md / CLAUDE.md）

📌 下一步：
/sprint-dev → 开始开发（前后端同时）
/sprint-dev backend → 仅后端开发
/sprint-dev frontend → 仅前端开发
```
