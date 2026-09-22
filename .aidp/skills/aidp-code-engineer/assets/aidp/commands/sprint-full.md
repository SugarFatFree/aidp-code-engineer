# /sprint-full — Sprint 一键执行（含自动累进）

你正在执行 `/sprint-full` 命令，完成单个 Sprint 的完整闭环：启动 → 开发 → 测试 → 修复 → 关闭。

> 🔀 **与 `/sprint-batch` 的边界**：本命令跑**单个** Sprint；要连续跑完整个版本的多个 Sprint 用 `/sprint-batch`（它内部循环调用本命令）。
> 🔀 **与 `/sprint-dev` / `/sprint-bugfix` 的边界（模式 B 累进时）**：三者都能"传一句描述→累进新 Sprint"，区别在**闭环范围与意图**——`/sprint-dev "<新功能>"` = 累进 + 开发，**默认亦串联 test→bugfix→close**（传 `skip-test` 才只开发）；`/sprint-bugfix "<较大 bug>"` = 缺陷意图专用入口（走 bugfix skill + 系统化调试）；**本命令 = 累进 + 完整闭环 start→dev→test→bugfix→close**，适合"要求一次跑到验收关闭"的新功能。**bug 修复优先用 `/sprint-bugfix`**（意图匹配、缺陷登记/复现更完整），不建议用本命令的模式 B 顶替。

**★ 本命令支持两种模式**：
- **模式 A（按计划执行）**：`/sprint-full {NNN}` — 执行 `01_研发执行计划.md` 中已规划的 Sprint
- **模式 B（自动累进新增）**：`/sprint-full "<目标描述>"` — 创建新 Sprint，序号自动累进，用于首轮 Sprint 全部完成后继续迭代

**★ 本命令是编排器**：按顺序调用子命令 `/sprint-start` → `/sprint-dev` → `/sprint-test` → `/sprint-bugfix` → `/sprint-close`。

参数：$ARGUMENTS
- `/sprint-full 001`                        — 模式 A：执行已规划的 Sprint-001
- `/sprint-full "新增用户导出功能"`          — 模式 B：自动创建新 Sprint 并执行
- `/sprint-full 002 skip-bugfix`            — 跳过 bugfix 循环
- `/sprint-full "xxx" skip-bugfix`          — 模式 B + 跳过 bugfix 循环
- `--from-batch`                             — 批量子任务标志（由 `/sprint-batch` 或 `/sprint-autopilot` 逐 tick 单 Sprint 路径隐式注入）：① 输出切紧凑模式，抑制规则详见下方「`--from-batch` 输出抑制规则」段；② **必须原样透传给 Phase 2/3/4/5 的子命令**——子命令据此**不弹 `AskUserQuestion`**：带 `--unattended` 时按预声明 / 保守默认；否则把需要用户裁决的内容决策门作为「⏸ 待裁决：<门名> / <选项> / <推荐>」返回，⛔ 不自行拍板（交互式由 `/sprint-batch` 主循环代问后续派，见其 Step 3）
- `--unattended`                             — 无人值守：内部决策门改为消费 PRD 预声明、**绝不弹 `AskUserQuestion`**；由 `/sprint-batch`·`/sprint-autopilot` 必传下来（本文件下方多处消费它，必须登记在本参数表内）
- `--stop-on-blocker`                        — 遇阻塞项即停并回传，不继续后续阶段（`/sprint-batch` 的合法停顿来源之一）

## `--from-batch` 输出抑制规则

当参数含 `--from-batch` 时，本命令是 `/sprint-batch` 循环体内的子任务，**单 Sprint 完成 ≠ 整个用户任务结束**。为避免 Claude 把 Phase 5 末尾的"📌 下一步"段落渲染出来后误以为命令到此结束、停止循环：

- ✅ **必须输出**：一行紧凑摘要 `▶ Sprint-{NNN} ✅ 完成（{N} 接口 / {N} 页面 / bugfix {M} 轮 / 待修 {K}）` 或对应软/硬失败状态行
- ❌ **必须抑制**：本文档「最终输出」段中的「📌 下一步：`/sprint-full {NNN+1}` / `/sprint-full "<新功能描述>"` / `/sprint-bugfix`」整段（含「模式 A 输出」「模式 B 输出」两份），不要打印
- ❌ **必须抑制**："各阶段摘要 / 产出文件 / 增量追加的文件"等冗长清单，不要打印
- 控制权立即返还 `/sprint-batch` 由它继续循环下一个 NNN

> 不带 `--from-batch`（用户直接调 `/sprint-full {NNN}`）→ 保持原"最终输出"完整段落不变。

## 前置流程

按 `docs/init/06_版本与用户目录约定.md`：
1. **{version}** ← 项目记忆文件（路径经 `python3 {{AIDP_HOME}}/scripts/agent_env.py memory-file` 取：`AGENTS.md`，只用 Claude Code 时为 `CLAUDE.md`）「当前状态.当前版本」
2. **{user}** ← `git config user.name`

## 前置检查

1. 确认版本规划文档已生成：
   - `ls docs/requirements/{version}/研发需求/{01_研发需求,00_索引,00_研发需求}.md 2>/dev/null` 任一命中即可（**不硬编码裸名**——multi 模式按系统拆分时 `01_研发需求.md` 本就不存在，硬判会把合规项目误判缺失而错误停止）
   - **详细设计**：`ls docs/design/detail/{version}/*.md` 有内容主文档即可（★ **用 glob 探测、兼容约定 14 三态**——拆分态 `00_索引.md`+`01_详细设计.md`… / 单份态 `00_详细设计.md` / 历史存量裸名 `详细设计.md`；**不硬编码裸名**，否则拆分态项目会被误判缺失而错误停止）
   <!-- dup-check: ignore 前置检查清单需各命令自包含，读者不应为一行 glob 跳转 -->
   - 研发执行计划：`ls docs/plans/{version}/{01_研发执行计划,00_索引,00_研发执行计划}.md docs/plans/{version}/0[0-9]_M*研发执行计划.md docs/plans/{version}/NN_研发执行计划-*.md 2>/dev/null` 任一命中即可（**不硬编码裸名**，理由同上一行研发需求；合法布局见 `/sprint-plan` Step 1「输出」）
   - 任一缺失 → **停止执行**，提示先执行 `/version {version} "{里程碑}"`
2. 读取 `memory/{version}/{user}/activeContext.md`：
   - 如有进行中的 Sprint → **停止执行**并要求先 `/sprint-close`（与独立 `/sprint-start` 同档——约定 9 是硬停不是提示）

## 参数解析

### 判断是模式 A 还是模式 B

```
if 参数第一项是纯数字（如 "001" / "2" / "042"）:
    → 模式 A：Sprint 编号 = 该数字
else if 参数第一项是带引号的字符串或自然语言:
    → 模式 B：需要自动累进 Sprint 序号
    → 新 Sprint 描述 = 该字符串
else:
    → 错误：提示正确格式
```

---

## 模式 A：执行已规划的 Sprint

### Phase 0A：读取 Sprint 范围

从 `docs/plans/{version}/01_研发执行计划.md` 读取指定 Sprint 的任务范围和目标。

---

## 模式 B：自动累进新增 Sprint

### Phase 0B.0：★ 版本落点决策门（累进前置，最先跑，先于任何持久副作用）

> ⛔ **本门之前还须先过约定 9「未关闭 Sprint 不得开新」**——`/sprint-start` 的硬停排在
> Phase 1，而 0B.1 取号 / 0B.2 产 6 类增量文档**都排在它之前**：
> 存在未关闭 Sprint 时，一条龙会先落一批持久副作用才被子命令拦下，
> 而独立分步执行时这些副作用根本不会发生。故本命令**进入 Phase 0B 之前**先自检未关闭 Sprint，
> 命中即**停止执行**、要求先 `/sprint-close`——与本 Phase 自己写的「先于任何持久副作用」同一条原则。

> **同 `/sprint-dev` 分支 B「Phase 0B.0 版本落点决策门」——单一信源见该处，本处不复述判定逻辑（约定 21）**。要点：若「当前版本」**已发布**（有 release tag / `progress.md`·版本更新日志标「✅ 已发布」）且未开始新版本规划，**累进前（且先于任何 `mkdir {新版本}` 等持久副作用）必须让用户三选一**——**① 落回已发布版本 re-release**（⚠️ 会强制移动已推送 tag，若已被他人/CI/制品库消费有实际风险）**② 新开 patch 版本 `{x.y.z+1}`（推荐默认、不动 tag、风险最低）③ 新开 minor 版本 `{x.y+1.0}`**；**patch/minor 版本号语义由用户定、执行体不自裁**（命令可给推荐+理由）；**绝不静默往已发布版本累进、绝不自行裁量版本号、绝不决策前建目录**（核心约定 2「自动累进仅适用于当前版本未发布时」）。`--unattended` 罕见命中→**保守默认新开 patch**（不动 tag）+ baseline `decidable_skips` 留痕（落点 = `builds[current_build]`，无 build 才回落版本级），与 `/sprint-dev` Phase 0B.0 同口径。`RELEASED` 为空（当前版本未发布，如已在新版本迭代中）→ 跳过本门，直接进 Phase 0B.1。

### Phase 0B.1：计算新 Sprint 序号

```bash
# ★ 取号一律走脚本，【绝不】自己 glob 当前版本目录（见下方 Why）
NEXT=$(python3 {{AIDP_HOME}}/scripts/check_sprint_numbering.py next)   # 形如 004
```

> ⛔ **Sprint 编号是【项目全局流水号】，跨版本连续自增、不随版本重置**（`06_版本与用户目录约定.md` §3.3）。
> ⛔ 扫描路径**不得带 `{version}` 限定**（带了新版本目录天然为空 → MAX=0 → 又从 `sprint-001` 起）。
> 脚本 `next` 子命令**跨全部版本**扫 `memory/*/*/sprints/` + `docs/plans/*/…研发执行计划.md` 取 MAX+1。

### Phase 0B.2：★ 自动文档增量流（与 `/sprint-dev` Phase 0B.1.1 同一机制，产 `NN_<业务主题>.md`）

模式 B 的累进文档生成**复用 `/sprint-dev` Phase 0B.1.1「自动文档增量流」的同一套机制**（单一信源，不另立分叉、不内联追加主文档正文）——把用户口述描述转化为**独立补充文档** `NN_<业务主题>.md`，6 类文档**共享同一 NN**、逐级级联，符合约定 15（补充命名）+ 约定 22（上游级联）：

**完整步骤（记口述 → L1 需求 → L2 设计 → L3 计划 → L4 用例 → 刷 `00_索引.md` → 完成报告，含各步的输入 / 路径占位符显式传参 / `--unattended` 透传 / 跳过条件）以 `/sprint-dev` Phase 0B.1.1 为单一信源**，⛔ 本命令按约定 21 不复述、不改判定。

> ★ **约定 22 铁律**：模式 B 累进新 Sprint 触发「需求漏项 / 功能点增删」→ 必级联 **L1 需求 → L2 设计 → L3 计划 → L4 研发自测用例**，不可只补前三级而漏 L4。**完整步骤（输入 / 路径占位符显式传参 / 跳过条件等）以 `/sprint-dev` Phase 0B.1.1 为单一信源**，本命令按约定 21 不复述、不改判定，仅在此声明模式 B 与其共用同一机制——累进产出统一为独立的 `NN_<业务主题>.md`，不内联追加进主文档正文。

---

### Phase 0B.3：★ 口述追加 / 口径反转清算门（模式 B 专属，约定 34 ⑥）

> 与 Phase 0B.2 **对称**：模式 B 的口述描述可能不是「追加」而是**推翻**本版已写入文档的既有结论
> （口径反向 / 白名单方向调转 / 默认值·状态机·权限范围改写）。**单一信源见 `/sprint-dev` Phase 0B.1.3**，
> 本步只做编排触发、不复述判定（约定 21）。
> ⛔ **不能靠 Phase 0B.2 兜住**：0B.2 指向的是 `/sprint-dev` Phase 0B.1.1（自动文档增量流），
> 它做的是**追加**；反转要做的是**逐条清算失效结论 + 显式作废标记**，两者处理方式不同、缺一不可。
> **完成判据（照搬其三项，缺任一不得进入 Phase 2）**：① 已判定「追加 vs 反转」；
> ② 若为反转，所有引用旧结论的落点（需求条目 / ADR / 用例断言 / 反向断言式子 / 铁律 / 代码 `REQ-XXX` 注释）
> 已逐条清算并加显式作废标记；③ 已回答「旧口径下判定为安全的设计，在新口径下是否仍然安全」。

## 阶段检查点协议（模式 A 和 B 通用）

每个阶段完成后输出简要状态。遇到阻塞性问题立即停止并报告。

## Phase 序列（模式 A / B 共用；与上方 `Phase 0A`/`Phase 0B.*` 同级，同属一条 Phase 序列）

### Phase 1：启动 Sprint

```
执行：/sprint-start {NNN} [--unattended]（无人值守时透传）
```

子命令读取需求和设计文档（模式 B 读取刚追加的增量章节），更新 activeContext。

```
▶ Phase 1 完成：Sprint-{NNN} 已启动
  - Sprint 目标：{目标}
  - 功能范围：{N} 个模块
  - 模式：{A 按计划 / B 自动累进}
```

### Phase 2：开发

```
执行：/sprint-dev {NNN} skip-test --cascade-now [--from-batch] [--unattended]  ★ `--cascade-now` 不可省：本命令同轮跑 test 与 close，而约定 22 的收口点**不含 `/sprint-close`**——台账详规自己点名这是「残余空档」且规避方式就是该 flag；不传则当天开发当天关闭的 Sprint，其 L4 用例要到次日首次提交才成文
# ★ 必传 skip-test：本命令是编排器，test/bugfix/close 由下方 Phase 3/4/5 统一负责；
#   若不传 skip-test，/sprint-dev 会自行串联 test→bugfix→close（其默认行为），与本命令 Phase 3/4/5 重复执行整条链。
# ★ --unattended（由 /sprint-batch 透传）时必传，令 /sprint-dev 的 UI C/D 门与约定22 级联门消费 PRD autopilot_decisions 预声明、不弹窗（autopilot 7×24 兜底）
```

（`/sprint-dev` 内部使用 `superpowers:test-driven-development` + `superpowers:subagent-driven-development`，本命令不另行调用。）

```
▶ Phase 2 完成：代码已实现
  - 后端：{N} 个接口（编译验证移至 Phase 3 验收，仅改动侧 + 资源受限）
  - 前端：{N} 个页面（前端校验（lint + 类型检查，不打包）移至 Phase 3 验收，仅改动侧 + 资源受限）
```

### Phase 3：测试

```
执行：/sprint-test {NNN} [--from-batch] [--unattended]
```

（`/sprint-test` 内部以仅验收模式使用 `code-verification-loop` + 可选 `api-tester`，本命令不另行调用。）前端浏览器仿真测试在部署后走独立命令 `/sprint-aiauto-test`（chrome-devtools-mcp，默认无头），不在本阶段。
发现的 bug 写入 `docs/bugfix/{version}/bugfix-{今日}-{user}.md`。

```
▶ Phase 3 完成：测试已执行
  - code-verification-loop：各维度 Pass/Fail + Critical {N} / Important {N}
  - 新增 bug：{N} 个
```

### Phase 4：Bugfix 循环

**如果 Phase 3 发现了 bug**（且参数不含 `skip-bugfix`）：

```
do {
  /sprint-bugfix sprint-{NNN} [--from-batch] [--unattended]   # 修复本 Sprint 相关的 bug
  /sprint-test {NNN} [--from-batch] [--unattended]            # 回归验收
} while (仍有未修复 && 循环次数 < 5)
```

终止：
- ✅ 全部 Fixed/Verified → 进入 Phase 5
- ⚠️ 循环 5 次超限 → **默认**：标记本 Sprint 为"⚠️ 软失败：bugfix 循环超限"，**继续进入 Phase 5 关闭 Sprint**（未修 bug 留在 `bugfix-*-{user}.md` 状态为「待修复」交给批量末段人工处理）；遇阻即停模式（参数 `--stop-on-blocker` 或 `/sprint-batch` 显式 stop-on-blocker 传入）→ 停止等待人工
- `skip-bugfix` → 跳过，bug 留待后续 `/sprint-bugfix` 处理

```
▶ Phase 4 完成：Bugfix 循环
  - 循环轮次：{M}
  - 修复 bug：{N}
```

### Phase 5：关闭 Sprint

```
执行：/sprint-close {NNN} [--from-batch] [--unattended]
# ★ `--from-batch` 与 `--stop-on-blocker` 同族，本命令带则**必须原样透传**：
#   它的语义是「我在批量循环体内、别停下来问人」。少转发这一个参数，
#   交互式 `/sprint-batch`（常规用法，7×24 才必带 --unattended）跑 N 个 Sprint
#   就会在每个 Sprint 末尾的验收门各停一次、共问 N 次 —— 与批量执行的目标
#   「计划里的全部 Sprint 一次跑完，中途不问人」正相反。
#   三段各自都合理（batch 传了、close 也按参数判了），断点恰在中间这一层。
```

记录本 Sprint 验收结论（并入 AI执行报告 / progress.md，不单独出验收报告文件）、归档、更新 progress.md 和 databaseBaseline.md（如模式 B 有新表）。

```
▶ Phase 5 完成：Sprint-{NNN} 已归档
```

---

## 最终输出

> ⚠️ **本段输出受 `--from-batch` 抑制规则约束**（权威定义见顶部「`--from-batch` 输出抑制规则」段）：含 `--from-batch` → 跳过下方「模式 A 输出」「模式 B 输出」，仅输出一行紧凑摘要后 return；不含 → 按下方完整段落输出"📌 下一步"等指引。

### 模式 A 输出（仅在**不含** `--from-batch` 时输出）

```
🎉 /sprint-full {NNN} 完成（按计划执行）

各阶段摘要：
  Phase 1-5：✅ 完成

📋 产出文件：
- docs/testing/{version}/sprint-{NNN}/
- docs/bugfix/{version}/bugfix-*-{user}.md（如有新 bug）
- memory/{version}/{user}/sprints/sprint-{NNN}.md

📌 下一步：
- /sprint-full {NNN+1}          → 继续执行下一个已规划的 Sprint
- /sprint-full "<新功能描述>"    → 自动累进新增 Sprint（模式 B）
- /sprint-bugfix                        → 单独处理待修复的 bug
```

### 模式 B 输出（自动累进；仅在**不含** `--from-batch` 时输出）

```
🎉 /sprint-full "{描述}" 完成（自动累进 Sprint-{新NNN}）

📋 增量追加的文件（★ 模式 B 新增；统一产**独立 `NN_<业务主题>.md`**、6 类共享同一 NN、不内联主文档正文，机制见 Phase 0B.2）：
- docs/requirements/{version}/产品提供/口述补充-{YYYYMMDD-HHMM}.md（口述记录）
- docs/requirements/{version}/研发需求/NN_<业务主题>.md（研发需求增量）
- docs/design/detail/{version}/NN_<业务主题>.md（详细设计 / 接口 / 数据库增量，按拆分态目录续编 NN）
- docs/deployment/{version}/sql/增量/{NN}_<中文名>.sql（新增 DDL/ALTER 文件，如有；序号续当前版本最大序号 +1）
- docs/plans/{version}/NN_<业务主题>.md（研发执行计划增量）
- docs/testing/{version}/研发自测/NN_<业务主题>.md（研发自测用例增量，L4 约定 22）
- 各目录 `00_索引.md` 各追加一行（类型=补充 + 生成时间，指向本轮 `NN_<业务主题>.md`）

各阶段摘要：
  Phase 0B：✅ 增量文档已追加
  Phase 1-5：✅ 完成

📋 Sprint 产出：
- docs/testing/{version}/sprint-{新NNN}/
- memory/{version}/{user}/sprints/sprint-{新NNN}.md

📌 下一步：
- /sprint-full "<下个目标>"     → 继续新增功能/修复
- /sprint-bugfix                       → 单独处理 bug（无需新 Sprint）
- /version {version}            → 本版本全部完成后发布
```

---

## 使用示例

```bash
# 场景 1：按计划执行
/version V0.1.0 "M1 MVP"       # 规划 5 个 Sprint
/sprint-batch                   # 批量执行完
# ... 人工验证 ...

# 场景 2：新增功能（自动累进 Sprint-006）
/sprint-full "新增用户导出功能"

# 场景 3：修复较大的功能性 bug → ⛔ 不用本命令，走 /sprint-bugfix 方式 C
#   （缺陷意图专用入口：bugfix skill + 系统化调试 + 缺陷登记/复现，本命令都没有）
/sprint-bugfix "修复批量导入重复校验逻辑错误"

# 场景 4：零散的 bug（不需要新 Sprint）
# 先在 docs/bugfix/{version}/bugfix-{今日}-{user}.md 记录 bug
/sprint-bugfix                         # 直接修复，归属当前最近的 Sprint

# 场景 5：只修指定 Sprint 的 bug
/sprint-bugfix sprint-002

# 场景 6：所有工作完成，发布
/version V0.1.0
```

## 模式选择建议

| 场景 | 推荐方式 |
|------|---------|
| 规划阶段确定的 Sprint | `/sprint-full {NNN}` 或 `/sprint-batch` |
| 首轮 Sprint 全部完成，继续新增功能 | `/sprint-full "<描述>"` 自动累进 |
| 简单 bug 修复（单文件/配置调整） | 直接 `/sprint-bugfix`，无需新 Sprint |
| 较大的功能性 bug（含设计变更） | `/sprint-bugfix "修复 xxx"` 方式 C 自动累进（**不用本命令**，见文首边界声明）|
| 需要严格审核每步 | 分步执行 `/sprint-start` → ... → `/sprint-close` |
