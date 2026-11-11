# /sprint-bugfix — 问题修复（独立可用；默认 light，formal 父编排才累进）

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
CONTEXT_RESULT=$(python3 {{AIDP_HOME}}/scripts/entry_context.py resolve --root . --entry sprint-bugfix \
  "${CONTEXT_ARGS[@]}" --json) || exit $?
EXECUTION_CONTEXT=$(printf '%s' "$CONTEXT_RESULT" | python3 -c 'import json,sys; print(json.load(sys.stdin)["execution_context"])') || exit $?
# 消费 resolve 返回的 execution_context 为 EXECUTION_CONTEXT，再路由。
python3 {{AIDP_HOME}}/scripts/entry_context.py route --root . --entry sprint-bugfix \
  --execution-context "$EXECUTION_CONTEXT" --phase repair --json
```

返回 `route=light` → 执行该片的 **repair** 能力，然后 **return**；不进入下文任何 Sprint 取号、卡片、activeContext、started、报告路径或归档步骤。返回 `route=formal` 才执行下文正式身份门；可选动作仍按 actions 筛选，未授权为 NOT_REQUESTED。任何子命令/修复/重试/续跑均保留原参数并显式附 `--execution-context "$EXECUTION_CONTEXT"`；不能只传 `--unattended`/`--from-batch` 而丢身份。

独立修复默认 `implement+static+related-test`，完成实现后自动 `/sprint-test --execution-context "$EXECUTION_CONTEXT" [--unattended]` → 必要修复/复验 → 终端。父编排 `skip-test` 只把测试交回父流程；用户真实 skip 记受限结果，不假报完整通过。

## formal 流程

你正在执行 `/sprint-bugfix` 命令。

**formal 分支支持三种调用方式**（独立普通描述已在 light 路由返回，不执行本段方式 C）
- **方式 A（被编排器调用）**：`/sprint-full` / `/sprint-batch` 内部的 bugfix 循环调用（执行体复用方式 B 全流程，不新开 Sprint）
- **方式 B（独立修复已记录的 bug）**：仅处理本次明确指定的缺陷文件/编号/业务范围；历史待办只作输入，不全部接管
- **方式 C（formal 自动累进新 Sprint）**：正式父编排明确要求累进，按描述创建新 Sprint 修复涉及设计变更的 bug，串联 test → 再 bugfix → close；普通 light 描述不进入此分支

> 🔀 **术语对照**：本命令的「方式 A/B/C」是**调用方式**分叉（A 被编排器调用 / B 独立修复已记录 bug / C formal 累进新 Sprint），Phase 0C.* 是方式 C 的前置层（对应 `/sprint-dev` 分支 B 的 Phase 0B.*）。累进新 Sprint 这一概念在三个命令里各有命名：本命令方式 C ≈ `/sprint-dev` 分支 B ≈ `/sprint-full` 模式 B；各命令内部命名自洽，勿跨命令按字母对号入座（本命令方式 A/B 与它们的 A/B 含义不同）。

**★ 本命令是编排器**：调用 `bugfix` skill（调用约定见 `{{AIDP_HOME}}/reference/skills.md`「bugfix SKILL 调用约定」）；涉及完整流程时串联 `/sprint-start` / `/sprint-test` / `/sprint-close`。

## 与 skill 的关系

- **`{{AIDP_HOME}}/commands/sprint-bugfix.md`**（本文件）：用户输入 `/sprint-bugfix` 时 Claude Code 读取的**斜杠命令**
- **`{{AIDP_HOME}}/skills/bugfix/SKILL.md`**：Claude 内部通过 `Skill` 工具调用的**技能**，由本命令在执行步骤中调用
- 两者分别定位不同：前者是入口，后者是实现细节

参数：$ARGUMENTS
- `/sprint-bugfix` — 方式 B：修复本次用户明确的缺陷范围；范围缺失先澄清目标，不扫描接管全部历史缺陷
- `/sprint-bugfix sprint-001` — 方式 B：只修复归属 Sprint-001 的 bug
- `/sprint-bugfix bugfix-20260509-alice.md` — 方式 B：仅处理指定文件
- `/sprint-bugfix "修复批量导入重复校验错误"` — 独立调用默认 light；只有明确 formal 上下文才按本段方式 B/C 分流，设计变更不自动升级身份
- `/sprint-bugfix "<描述>" --minor` — 强制方式 B（零散修复，不新开 Sprint）
- `/sprint-bugfix "<描述>" --accrue` — 强制方式 C（累进新 Sprint，跳过语义判定）
- `/sprint-bugfix "<描述>" skip-test` — 跳过后续 test/close 串联
- `--cascade-now` / `--dev-scale=S|M|L` — 显式要求原样透传开发入口，不默认强制级联。
- `--aiauto-test-required` / `--skip-aiauto-test` — 实测意图透传，required 优先，不以被编排自动恢复已取消实测。
- `--unattended` — 无人值守：所有决策门按下文规则**自动判定**，不弹 `AskUserQuestion`；由 `/sprint-batch` → `/sprint-full` → 本命令逐层透传（漏传即在版本落点决策门挂起）
- `--from-batch` — 批量子任务标志（由 `/sprint-full` 透传）：本命令不弹 `AskUserQuestion`，内容决策门按「⏸ 待裁决」返回上层（语义单一信源 = `/sprint-full` 参数表）

## 前置流程

**工作分支先决条件**：按 `{{AIDP_HOME}}/reference/agent-tools.md`「工作分支：首次选择、项目内沿用」读取项目 `development.branch_policy`。独立修复未选时只由主流程询问并保存一次；验收内修复、方式 A 或同任务续跑继承 `task_branch`，不因新增 BUG、调用 bugfix SKILL 或开始修复轮次另建分支。无人值守缺选择返回 `needs-choice`，不代选；无 Git 跳过。

按 `docs/init/06_版本与用户目录约定.md`：
1. **{version}** ← 项目记忆文件（路径经 `python3 {{AIDP_HOME}}/scripts/agent_env.py memory-file` 取：`AGENTS.md`，只用 Claude Code 时为 `CLAUDE.md`）「当前状态.当前版本」
2. **{user}** ← `python3 {{AIDP_HOME}}/scripts/vcs.py user`（唯一解析实现：显式 → 本地 Git 身份 → `AIDP_USER` → OS 用户；⛔ 别自己拼 `git config user.name`，无 Git 项目上会解析出另一个身份）
3. bug 扫描范围（**两类来源并集**；用户主动提及 GitHub Issue 时叠加第三类）：
   - `docs/bugfix/{version}/bugfix-*-{user}.md`（零散 bug 文件，传统来源）
   - `docs/testing/{version}/研发自测/**/*.md`（当前布局主集）/ `docs/testing/{version}/正式用例/**/*.md` / `docs/testing/{version}/研发自测.md`（旧扁平布局兜底）**末尾的「问题汇总清单」表**中状态为「待修复」的行（按 glob 汇总所有分册 + 测试人员用例）。**研发自测 / 测试人员发现的 bug 默认走这条**，不必每个 bug 都另起 bugfix-*.md
   - **★ GitHub Issue 缺陷（可选，仅用户主动提及 GitHub Issue 时，约定 31.3）**：用 `gh issue list` / `gh issue view <编号>` 拉取 → **先预读、理解每条缺陷语义、确认缺陷确实存在/可复现，再进入修复**；缺陷为人工填充不可盲信标题直接改。未安装或未登录 `gh` 时终端提示后跳过。

**授权前置**：本段修复仅适用于 implement 已授权的当前 scope；review/test-only 只回传发现。工具/环境失败保留原分类，不能一概开业务 BUG；重试与预算遵守 `light-context.md`。

## ★ 缺陷处置默认决策纪律（先于任何"挂起等人"——堵"边界模糊就问人"）

> ⛔ **本段是 `/sprint-bugfix`（及 `/sprint-dev`、`/sprint-autopilot` 修复类改动）"该怎么修"的单一信源**，其他命令引用、不复述（约定 21）。核心：**绝大多数缺陷都有明确最佳实践、默认直接修、不问人**；"询问用户"收窄为「⛔ 统一决策纪律」正向判据（真正的产品取舍 / 对外 tag 承诺 / 高回退成本 / 持久目录）下的**例外**。现有对 Mock（约定 26 P0/P1/P2）、UI 基准（约定 4 情形 A-D）、版本落点（约定 2 三选一）、死代码（约定 29 A/B/C）都给了默认值，唯"缺陷怎么修"缺默认值 → 边界模糊就问人 → 本段补齐。

### 核心判据（三分，拿不准有默认方向）

只分「要什么」等人 / 「写错了」当场改时，边界模糊处缺默认值 → 保守挂起 → 无谓阻塞。故**先问一句**：

> **「不做这个修复，当前行为是不是错的？」**
> - **是（当前行为错误）** → 属"写错了"，**当场改、不问**。
> - **否，只是可以更好** → 纯优化，记录不修理由或后续建议，不为优化阻塞本轮；确需在两个合理行为/产品口径间选择才按下方正向白名单等待裁决。
> - **拿不准属哪档** → 先收集当前 scope 内证据区分工具/环境/业务失败，已证实业务错误且 implement 已授权才改——"失败被伪装成成功""错误被吞掉"这类缺陷每多存在一天就多误导用户一天；挂起等人的代价是**确定的**（阻塞到人醒），修错的代价**可控**（git 可回退）。

### 缺陷类型 → 默认处置映射表（命中即按默认处置直接修、无需询问）

| 缺陷类型 | 默认处置（无需询问） | 仅当…才需要问 |
|---|---|---|
| **失败被呈现成成功/空**（HTTP 200 + "操作成功" + 空数据；前端把 error 渲染成空态） | 直接报错：后端返明确业务码 + 面向用户中文消息；前端**原样呈现后端 message**，不得替换成"暂无数据" | 几乎不需要 |
| **上游/依赖不可达** | 直接返回错误，文案 `「{上游中文名}服务无法连接，请稍后再试」`——服务名**必须是用户看得懂的中文**，不得用 `ORD` / `xxx-center` 等系统代号 | 某接口确需降级（如字典类）→ 在该接口处注明理由，不必全局请示 |
| **上游已交付更优接口/契约变更** | **以上游为准跟进**（上游是契约权威方，其优化即应跟进） | 切换会破坏已交付功能 / 需数据迁移时 |
| **安全判据 fail-open**（"取不到"当"没有"、"解析失败"当"无关联"） | 改 **fail-closed**：宁可报错，不可给出看似正常的错误答案 | 不需要 |
| **口径/单位/默认值需产品定义**（统计范围 / 计费规则等） | —（这才是真正的"要什么"） | **必须问**（属约定 22 第三类语义/口径变更、约定 33 口径） |
| **涉及版本号 / tag / 持久目录等对外承诺** | — | **必须问**（约定 2「版本落点决策门」已覆盖） |

### ⛔ 「必须问」的正向白名单（**反向清单**：不在单里就一律默认修）

> 上表的"必须问"两行 + 核心判据那句问话，都要执行体**自己判断**"这算不算真正的产品取舍"——
> 而"算不算"本身就是可以被解释的，于是"保险起见问一下"成了免费逃逸口（下游实证：两条缺陷
> 里只有一条真需要产品输入，执行体用"需要产品决策"一句话**同时盖住了两条**，另一条纯技术缺陷
> 就此挂起等人）。故把判据翻成**白名单**：**满足下列任意一条才可归「必须问」，四条都不满足 → 一律默认修。**

1. 修复需要**新增或修改用户可见文案**，且文案内容**无既有规范可循**（已有同类文案可对齐的 → 对齐，不算）；
2. 修复需要在**两种都合理的行为**之间做选择（如失败时该重试还是该报错），且两者对用户的承诺不同；
3. 修复会**改变已上线功能的既有口径**，影响存量用户的认知（属约定 22 第三类语义变更 / 约定 34 口径反转）；
4. 修复涉及**金额 / 权限 / 数据可见范围**的判定规则变更。

> **★ 归「必须问」时必须同时写出「具体要产品回答什么」**（一句话、可被回答的问句），
> ⛔ 空泛的"需要产品确认"不接受。**写不出那个问句，就是这条其实不需要产品输入的证据** ——
> 此时按默认处置直接修。无人值守链路里这条落成结构化字段（`pending_clarifications[].question`），
> 由收尾门校验，见 `{{AIDP_HOME}}/flows/sprint-aiauto-test/phase-3-3b.md`。

> 表未穷举：新类型按「一、核心判据」归档——问一句"当前行为是不是错的"，是→默认修、否→记录纯优化不修理由；只有真实产品取舍才待裁决。
> **★ 编码期正确写法（前移、防这类缺陷从源头发生）单一信源 = `{{AIDP_HOME}}/rules/code.md`「错误契约与失败可见性 + fail-closed + 上游契约权威」**（约定 23 姊妹条）：本表管"发现了默认怎么修"（处置层），code.md 管"写代码时就该长什么样"（编码层），互补不重复（约定 21）。修复时按 code.md 的正确写法改。

### 批量挂起的成本意识（无人值守尤重）

一次性向用户抛出 **≥2 个待拍板事项前，逐条自检**：这条是否**真的**需要人定（命中表中"必须问"两行 / 满足统一决策纪律正向判据）？**任一条的答案是"其实默认就该这么做"→ 不得放进询问清单、直接按默认处置修**。无人值守场景，挂起的成本是"整轮停摆到人醒"，**远高于**按默认值推进后被纠正的成本（git 可回退）。

> **★ 修复期运行时验证纪律 = 约定 35（详规 `{{AIDP_HOME}}/rules/code.md`，约定 21 不复述）**：验证修复**默认静态验证与当前任务相关单测**；**绝不为"看看修好没 / 验证运行时"擅自启动前后端服务或跑完整构建**——需运行时/浏览器验证走 **(a) 已部署环境 / (b) 用户已运行服务（先探端口、有则复用绝不另起）/ (c) 都无先 `AskUserQuestion` 由用户启动**（唯一例外 = `deployment.mode=local` 授权）。

## 参数解析与路径分支

```
判断参数第一项（★ 先判调用来源：由 /sprint-full · /sprint-batch 内部 bugfix 循环调起 → 方式 A）：
  - 空                              → 方式 B：先澄清本次目标；有核实清单（BUG ID / 文件）才按清单修，⛔ 不扫描接管全部历史待修
  - sprint-{NNN}                     → 方式 B：按 Sprint 过滤
  - bugfix-*.md                      → 方式 B：指定文件
  - 字符串（"xxx"）                   → 先做**规模语义判定**（见下），再定 方式 B / 方式 C
```

> ⛔ **字符串参数不是"一律累进新 Sprint"**——纯按语法分流会让**口述任何一个小 bug 都新开 Sprint**，
> 与约定 3「零散 bug 独立修复、**无需新 Sprint**」和意图路由表「**较大** bug 才自动累进」直接矛盾，
> 还会连带撞上 Phase 0C.0 的版本落点门。判据（与本命令 `方式 C` 的适用场景同源）：
>
> | 口述内容 | 走哪条 |
> |---|---|
> | 需要**新增接口 / 改表结构 / 调整架构设计**（即会产生设计增量） | **方式 C**：累进新 Sprint + 走 Phase 0C.1 的四类增量文档 |
> | 文案、样式、边界判断、空指针、拼写、日志级别等**不动设计**的零散修复 | **方式 B**：就地修 + 记 `docs/bugfix/{version}/` 表格行，**不新开 Sprint** |
>
> - **判不准时从严按方式 C**（宁可多留一份设计增量，也不要让设计漂移无痕）。
> - **显式覆盖**：`--minor` 强制走方式 B、`--accrue` 强制走方式 C，跳过语义判定。
> - `--unattended` 下同样按上表自动判定，**不得**为此弹 `AskUserQuestion`。

---

## 方式 A：被编排器调用（`/sprint-full` · `/sprint-batch` 内部 bugfix 循环）

**适用场景**：本命令不由用户直接输入，而是被 `/sprint-full` / `/sprint-batch` 的 bugfix 循环调起，用于消化当前 Sprint 测试阶段产出的缺陷。

**执行规则**：

- **不新开 Sprint、不做累进**——编排器已持有当前 Sprint 上下文，本方式只在其内闭环修复；需要累进的较大 bug 由编排器自行决定是否改走方式 C。
- **执行体 = 方式 B 全流程**：编排器传入的参数（`sprint-{NNN}` 过滤 / 空）落到方式 B 的参数分支，按方式 B 的骨架表 + `{{AIDP_HOME}}/flows/sprint-bugfix/mode-b.md` 逐项执行。
- **零询问**：编排器上下文（尤其 `/sprint-batch` 连跑、`/sprint-autopilot` 无人值守）下不弹 `AskUserQuestion`，一律按上方「缺陷处置默认决策纪律」的默认处置直接修。
- **收口**：只接管未闭环项，复用原问题 ID/证据；已修项带真实 SHA 或尚未提交写树 hash，挂起原因与不修理由分列。定向测试后回传编排器，由已有验收会话完成 reviewer 差量复核和集中 Sprint 单测，不重复完整 `/sprint-test` / CVL。

---

## 方式 B：独立修复已记录的 bug（★ 最常用）

> **关键规则**：无需依赖任何 Sprint 流程——扫描当前用户 bug 文件（来源 A `docs/bugfix/{version}/bugfix-*-{user}.md` + 来源 B `docs/testing/{version}/研发自测·正式用例` 末尾「问题汇总清单」待修行）先落成 `docs/bugfix/` 条目（SKILL 唯一输入面）再调 SKILL 修复（先定根因再改码）、回填、编译校验，状态 待修→已修。**契约边界（约定 21）**：bugfix SKILL 是修复流程单一信源，命令端只做来源落条目 + 状态回填 + 项目级专项检查（路径/URL/proxy、部署监听、设计回写），不复述、不改写 SKILL 内部步骤。

**骨架表（详见 flow 文件，逐项执行不得略过）**：

| 步骤 | 做什么 | 关键约束 |
|------|--------|---------|
| 前置准备 | 读 systemPatterns/techContext/architecture + 详细设计/事实清单/对外开放接口 | bug 涉路径/URL/404 必精读「路径消费者点」表；对外接口修复红线禁引 Session/Cookie/JWT |
| Step 0 | ⛔ 口述 bug + 来源 B 清单待修行先落 `bugfix-{date}-{user}.md` 条目（带来源回链），**不得跳过直接改代码** | 去重仅回链 / exact match，不做语义模糊判断 |
| Step 1 | 调 `bugfix` skill（参数 `sprint-{NNN}` / 文件名，prompt 带本次核实的 BUG ID 清单；空参数无清单 → 澄清 / 返回缺口），附路径/URL/proxy + 配置 + 部署台账专项 | 路径类修完单点须巡检同表其他消费者点 |
| Step 2 | 推送分类与监听（约定 31.5） | 正式代码变更 push 后必走 CICD 监听 + 就绪探针 |
| Step 3 | 回填状态 / Commit / 证据或报告链接（bugfix 记录 + 来源 B 清单行，不删行） | 根因权威落点随 `report_mode`：formal 默认 `file` = SKILL 报告；`evidence-only` = 当前 execution context JSON |
| Step 4 | 编译（后端）/ 前端校验（lint+类型检查不打包） | 仅改动侧 + 资源受限 |
| Step 5 | 自动回写设计文档（约定 22 级联；经 `--ledger-cascade` **就地改内容主文档正文**，⛔ 不新建 `NN_` 分册） | 纯逻辑修复不触发 |
| Step 5.1 | ★ 累进产物审计（Step 5 产出四类文档任一份 → 派 version-auditor 子 Agent，⛔ 不得省）| `scope=incremental`，审 C-4/C-5/F/G/H 五项 |
| Step 5.5 | P0/P1 缺陷反哺一条 `[回归]` 用例（约定 33） | 走 `/sprint-selftest --ledger-cascade [--unattended]` 就地追加（不新建 `NN_`），用例↔缺陷双向关联 |
| Step 6 | 更新 `activeContext.md` 待处理 Bugfix 区 | — |

**进入本段第一动作 = Read `{{AIDP_HOME}}/flows/sprint-bugfix/mode-b.md`**，以该文件为权威逐项执行。

---

## 方式 C：自动累进新 Sprint（较大 bug 或涉及设计变更）

**适用场景**：bug 需要新增接口、修改表结构、调整架构设计等，不适合直接改代码了事。

### Phase 0C.00：★ 约定 9 前置门（⛔ 最先跑，先于版本落点门与任何取号动作）

> 存在**未关闭 Sprint** 时**立即停下**要求先 `/sprint-close`，⛔ 不得继续。先于版本落点门：若先在落点门选了「新开 patch / minor」
> 再被本门拦下，新版本目录已建、旧 Sprint 成为跨版本孤儿。判据与话术同 `/sprint-dev` Phase 0B.00。

```bash
python3 {{AIDP_HOME}}/scripts/check_open_sprints.py --version {version} --scope started --json
OPEN_RC=$?        # 0=无已启动未关闭轮次→继续；1=有→立即停下、先 /sprint-close；2=状态读错→停止并修复输入
```

> **判据单一信源 = `check_open_sprints.py`**（开工门检查跨用户的已启动记录与显式当前状态，扣除同时具备同行 ✅ 与 `sprints/sprint-NNN.md` 归档文件的关闭记录；**尚未开工的计划不阻断启动**）。
> ⛔ 不自行裁量、不记告警后继续 —— 本门漏判的方向是**放行**，而放行的代价是上面那段写的孤儿产物。

### Phase 0C.0：★ 版本落点决策门（累进前置，先于任何持久副作用）

> **同 `/sprint-dev` 分支 B「Phase 0B.0 版本落点决策门」**：当前版本已发布且未开始新版本规划时，**先弹版本落点门再动任何持久副作用**——三选一（re-release / 新 patch / 新 minor）与各自的 tag 影响、无人值守保守默认，**单一信源见 `/sprint-dev` Phase 0B.0，本处不复述**（约定 21）。<!-- dup-check: ignore 已改为指针，此行是指针本身 -->

### Phase 0C.1：缺陷归口与契约委派

先 Read `{{AIDP_HOME}}/flows/sprint-dev/incremental-contract.md`。主流程把现象、复现步骤、根因证据、期望行为和来源回链落入当前版本 bugfix 记录；新增 BUG 用 `python3 {{AIDP_HOME}}/scripts/alloc_id.py --kind BUG --count 1 --owner orchestrator --version {version} --scope bugs` 原子取号，已有 BUG 复用。不自行 grep 最大值；编号接口不可用保留待登记工作单并停在该门。

**方式 C 不自行重复四层前置**：编号、契约卡、S/M/L 判档、反转清算、文档成文和汇合统一委派 Phase 1 的 `/sprint-dev` 新协议。S 攒批、M 代码/docs 并行后完整汇合、L 先文档，不能因“bugfix”强制全部走 L。已完成的版本落点决策连同缺陷记录、具体修复约束透传，入口不重复决策、不先建新 Sprint 目录。四族同事件复用 C 号与正式用例 required 门仍按权威流程。

### Phase 0C.2：启动由开发入口承担

本层不另调 `/sprint-start`，由 Phase 1 在契约放行后启动并回传真实 `{新NNN}`，避免重复取号或重置上下文。

### Phase 1：开发修复

```
执行：/sprint-dev "{描述}" --execution-context "$EXECUTION_CONTEXT" skip-test [--cascade-now] [--from-batch] [--unattended]
```

透传 BUG ID/根因证据与具体修复工作单，由原开发入口编排实现者在新 Sprint 内完成修复；**不整体调用 bugfix SKILL**（其流程会自行修码并写报告，与开发入口双写同一写集），只沿用其根因纪律——先定根因再改码、证据未确认不动代码（SKILL Step 2.2b / Step 3）；不让两组 Agent 同时改同一写集。`skip-test` 必传以抑制开发入口自带的后续串联，test/close 由本层接管；`--cascade-now` 仅已有显式要求才传，`--dev-scale` 及实测 required/skip 意图同样透传。M 的 docs 与契约 reviewer 汇合必须通过，skip-test 不省汇合门。

### Phase 2：测试

先消费 Phase 1 开发入口回传的真实 `{新NNN}` 与子 `execution_context`，将后者作为本轮 `EXECUTION_CONTEXT`；若开发入口从版本父 fork 了子任务，此处不能继续拿父路径测试/关闭，也不能覆盖 autopilot 版本节点的父路径。缺回传即返回未完成。

```
执行：/sprint-test {新NNN} --execution-context "$EXECUTION_CONTEXT" [--from-batch] [--unattended]（实测意图同样原样透传；只做一次完整 CVL，原实现者当轮闭环）
```

### Phase 3：只接管未闭环项

`/sprint-test` 已负责当轮原实现者修复与差量复核。本层不重复完整验收、不重修已闭环 BUG；仅对其返回的可修复残项恢复原实现者，必要时方式 B 接管同一 Sprint/BUG，随后 `/sprint-test {新NNN} --execution-context "$EXECUTION_CONTEXT" --resume-acceptance [--from-batch] [--unattended]` 续接定向复核与最终 Sprint 单测收敛。共用验收的修复轮次，累计连续 5 轮失败即返回未闭环项（本命令层自设上限，与 CVL `mode=loop` 的轮次无关），不另起五轮完整验收。

产品/版本/破坏性/环境待决保持具体原因并返回上层，不能静默关闭。所有下游继续原样透传 `--unattended` / `--from-batch` 和实测意图；没有可信原始质量证据时回验收补齐，不宣称 CVL 增量模式。

### Phase 4：关闭

```
执行：/sprint-close {新NNN} --execution-context "$EXECUTION_CONTEXT" [--from-batch] [--unattended]（仅验收已闭环、证据可信时；否则返回 closed:false 并保留上下文）
```

**跳过串联**：参数含 `skip-test` → 只做 Phase 0C + 开发，不自动 test/close。

---

## 输出

### 方式 B 输出

```
✅ /sprint-bugfix 完成（{version} / {user}）

处理结果（位于 docs/bugfix/{version}/bugfix-*-{user}.md）：
- B-{YYYYMMDD}-01: ✅ 已修复 — {问题标题}
  根因：{当前任务机器修复证据路径与问题ID}
  修改文件：{文件列表}
  Commit: `abc123`
- B-{YYYYMMDD}-02: ✅ 已修复 — {问题标题}
- B-{YYYYMMDD}-03: ⚠️ 需要确认 — {原因}

编译（后端）/ 前端校验（lint + 类型检查，不打包）：✅ 通过（仅改动侧 + 资源受限）

📌 下一步：
1. /sprint-test → 执行回归测试验证修复效果
2. /memory-sync → 同步记忆文件
```

### 方式 C 输出

```
🎉 /sprint-bugfix "{描述}" 完成（formal 累进 Sprint-{新NNN}）

📋 本轮产物（按 S/M/L 实际状态列出，不把延期写成已完成）：
- BUG 记录与来源回链
- docs/design/detail/{version}/_sprint-{新NNN}-契约卡.md
- {已成文的需求/设计/计划/适用用例与 SQL 的真实路径}
- {四族待成文义务与正式用例 required/deferred 状态}

各阶段摘要：
  Phase 0C：{契约分档、缺陷登记与汇合证据}
  Phase 1-4：✅ 完成

📋 Sprint 产出：
- docs/testing/{version}/sprint-{新NNN}/
- memory/{version}/{user}/sprints/sprint-{新NNN}.md

📌 下一步：
- /sprint-bugfix → 继续处理零散 bug
- /sprint-dev "<新功能>" → 继续新增功能
- /version {version} → 发布
```

---

## 使用示例

```bash
# 场景 1：被编排器调用（/sprint-full 内部）
# 自动触发，无需用户手动

# 场景 2：★ 独立修复已记录的零散 bug（最常用）
# 先在 docs/bugfix/V0.1.0/bugfix-20260509-alice.md 添加 bug 表格行
/sprint-bugfix                            # 空参数：先澄清要修哪些 bug（或由调用方 / 核实清单限定），不自动全扫

# 场景 3：按 Sprint 过滤
/sprint-bugfix sprint-003                 # 只修 Sprint-003 相关的 bug

# 场景 4：指定文件
/sprint-bugfix bugfix-20260509-alice.md

# 场景 5：★ 较大 bug，需要新 Sprint + 设计变更
/sprint-bugfix "修复批量导入重复校验逻辑，需新增唯一约束和查重接口"
# 仅 formal 父编排下：累进 Sprint-007 → 追加设计 → 开发 → 测试 → 关闭（独立无上下文的描述为 light，不新开 Sprint）

# 场景 6：方式 C + 跳过后续串联
/sprint-bugfix "重构认证模块修复会话泄漏" skip-test
# 只追加设计并开发，不自动测试/关闭
```

## 方式选择决策

| Bug 类型 | 推荐方式 |
|---------|---------|
| 配置错误、单文件修复、笔误 | 方式 B：`/sprint-bugfix` |
| 跨多文件的逻辑 bug | 方式 B |
| 需要新增字段/表/接口才能修 | 方式 C：`/sprint-bugfix "<描述>"` |
| 需要架构调整才能修 | 方式 C |
| 修复方案还不明确，先分析 | 方式 B（Claude 会分析后给方案）|

> ★ **若本命令触发 `git commit`**（自动提交场景）：按**约定 24** 走提交前门禁——每次 commit 前跑 `python3 {{AIDP_HOME}}/scripts/commit_gate.py --quiet` 读 JSON，退出码 3/4 = 本轮结束前有义务未落地（约定 22 台账积压 / CICD 推送欠账），**不是禁止 commit**；判定字段与处置的单一信源 = 约定 24，本命令按约定 21 只做编排触发、不复述。<!-- dup-check: ignore 已改为指针，此行是指针本身 -->
