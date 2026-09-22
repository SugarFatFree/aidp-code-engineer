# /sprint-bugfix — 问题修复（独立可用，支持自动累进）

你正在执行 `/sprint-bugfix` 命令。

**★ 本命令支持三种调用方式**
- **方式 A（被编排器调用）**：`/sprint-full` / `/sprint-batch` 内部的 bugfix 循环调用（执行体复用方式 B 全流程，不新开 Sprint）
- **方式 B（独立修复已记录的 bug）**：扫描 `docs/bugfix/{version}/` 下待修复的 bug 文件直接修复
- **方式 C（自动累进新 Sprint）**：用户传入描述，自动累进创建新 Sprint 修复较大的 bug（涉及设计变更），串联 test → 再 bugfix → close

> 🔀 **术语对照**：本命令的「方式 A/B/C」是**调用方式**分叉，与 `/sprint-dev`「分支 A（按计划）/ B（口述累进）」、`/sprint-full`「模式 A（按计划）/ B（自动累进）」不是同一组；本命令方式 C ≈ 那两者的 B（累进新 Sprint）。

**★ 本命令是编排器**：调用 `bugfix` skill（其根因定位方法论为 `superpowers:systematic-debugging`，由 SKILL 内部使用）；涉及完整流程时串联 `/sprint-start` / `/sprint-test` / `/sprint-close`。

## 与 skill 的关系

- **`{{AIDP_HOME}}/commands/sprint-bugfix.md`**（本文件）：用户输入 `/sprint-bugfix` 时 Claude Code 读取的**斜杠命令**
- **`{{AIDP_HOME}}/skills/bugfix/SKILL.md`**：Claude 内部通过 `Skill` 工具调用的**技能**，由本命令在执行步骤中调用
- 两者分别定位不同：前者是入口，后者是实现细节

参数：$ARGUMENTS
- `/sprint-bugfix` — 方式 B：修复 `docs/bugfix/{version}/` 下当前用户所有待修复 bug
- `/sprint-bugfix sprint-001` — 方式 B：只修复归属 Sprint-001 的 bug
- `/sprint-bugfix bugfix-20260509-alice.md` — 方式 B：仅处理指定文件
- `/sprint-bugfix "修复批量导入重复校验错误"` — 按**规模语义判定**分流：涉设计变更（新增接口/改表/调架构）→ ★ 方式 C 自动累进新 Sprint；不动设计的零散修复 → 方式 B 就地修
- `/sprint-bugfix "<描述>" --minor` — 强制方式 B（零散修复，不新开 Sprint）
- `/sprint-bugfix "<描述>" --accrue` — 强制方式 C（累进新 Sprint，跳过语义判定）
- `/sprint-bugfix "<描述>" skip-test` — 跳过后续 test/close 串联
- `--unattended` — 无人值守：所有决策门按下文规则**自动判定**，不弹 `AskUserQuestion`；由 `/sprint-batch` → `/sprint-full` → 本命令逐层透传（漏传即在版本落点决策门挂起）
- `--from-batch` — 批量子任务标志（由 `/sprint-full` 透传）：本命令不弹 `AskUserQuestion`，内容决策门按「⏸ 待裁决」返回上层（语义单一信源 = `/sprint-full` 参数表）

## 前置流程

按 `docs/init/06_版本与用户目录约定.md`：
1. **{version}** ← 项目记忆文件（路径经 `python3 {{AIDP_HOME}}/scripts/agent_env.py memory-file` 取：`AGENTS.md`，只用 Claude Code 时为 `CLAUDE.md`）「当前状态.当前版本」
2. **{user}** ← `git config user.name`
3. bug 扫描范围（**两类来源并集**；用户主动提及 GitHub Issue 时叠加第三类）：
   - `docs/bugfix/{version}/bugfix-*-{user}.md`（零散 bug 文件，传统来源）
   - `docs/testing/{version}/研发自测/**/*.md`（当前布局主集）/ `docs/testing/{version}/正式用例/**/*.md` / `docs/testing/{version}/研发自测.md`（旧扁平布局兜底）**末尾的「问题汇总清单」表**中状态为「待修复」的行（按 glob 汇总所有分册 + 测试人员用例）。**研发自测 / 测试人员发现的 bug 默认走这条**，不必每个 bug 都另起 bugfix-*.md
   - **★ GitHub Issue 缺陷（可选，仅用户主动提及 GitHub Issue 时，约定 31.3）**：用 `gh issue list` / `gh issue view <编号>` 拉取 → **先预读、理解每条缺陷语义、确认缺陷确实存在/可复现，再进入修复**；缺陷为人工填充不可盲信标题直接改。未安装或未登录 `gh` 时终端提示后跳过。

## ★ 缺陷处置默认决策纪律（先于任何"挂起等人"——堵"边界模糊就问人"）

> ⛔ **本段是 `/sprint-bugfix`（及 `/sprint-dev`、`/sprint-autopilot` 修复类改动）"该怎么修"的单一信源**，其他命令引用、不复述（约定 21）。核心：**绝大多数缺陷都有明确最佳实践、默认直接修、不问人**；"询问用户"收窄为「⛔ 统一决策纪律」正向判据（真正的产品取舍 / 对外 tag 承诺 / 高回退成本 / 持久目录）下的**例外**。现有对 Mock（约定 26 P0/P1/P2）、UI 基准（约定 4 情形 A-D）、版本落点（约定 2 三选一）、死代码（约定 29 A/B/C）都给了默认值，唯"缺陷怎么修"缺默认值 → 边界模糊就问人 → 本段补齐。

### 核心判据（三分，拿不准有默认方向）

只分「要什么」等人 / 「写错了」当场改时，边界模糊处缺默认值 → 保守挂起 → 无谓阻塞。故**先问一句**：

> **「不做这个修复，当前行为是不是错的？」**
> - **是（当前行为错误）** → 属"写错了"，**当场改、不问**。
> - **否，只是可以更好** → 属"要什么"（真正的产品/架构取舍），**等人**。
> - **拿不准属哪档** → ⚠️ **默认当场改**——"失败被伪装成成功""错误被吞掉"这类缺陷每多存在一天就多误导用户一天；挂起等人的代价是**确定的**（阻塞到人醒），修错的代价**可控**（git 可回退）。

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

> 表未穷举：新类型按「一、核心判据」归档——问一句"当前行为是不是错的"，是→默认修、否→问人。
> **★ 编码期正确写法（前移、防这类缺陷从源头发生）单一信源 = `{{AIDP_HOME}}/rules/code.md`「错误契约与失败可见性 + fail-closed + 上游契约权威」**（约定 23 姊妹条）：本表管"发现了默认怎么修"（处置层），code.md 管"写代码时就该长什么样"（编码层），互补不重复（约定 21）。修复时按 code.md 的正确写法改。

### 批量挂起的成本意识（无人值守尤重）

一次性向用户抛出 **≥2 个待拍板事项前，逐条自检**：这条是否**真的**需要人定（命中表中"必须问"两行 / 满足统一决策纪律正向判据）？**任一条的答案是"其实默认就该这么做"→ 不得放进询问清单、直接按默认处置修**。无人值守场景，挂起的成本是"整轮停摆到人醒"，**远高于**按默认值推进后被纠正的成本（git 可回退）。

> **★ 修复期运行时验证纪律 = 约定 35（详规 `{{AIDP_HOME}}/rules/code.md`，约定 21 不复述）**：验证修复**默认只静态验证**；**绝不为"看看修好没 / 验证运行时"擅自启动前后端服务或跑完整构建**——需运行时/浏览器验证走 **(a) 已部署环境 / (b) 用户已运行服务（先探端口、有则复用绝不另起）/ (c) 都无先 `AskUserQuestion` 由用户启动**（唯一例外 = `deployment.mode=local` 授权）。

## 参数解析与路径分支

```
判断参数第一项（★ 先判调用来源：由 /sprint-full · /sprint-batch 内部 bugfix 循环调起 → 方式 A）：
  - 空                              → 方式 B：修复所有待修复 bug
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
- **收口**：修完把结果回填给编排器（已修 / 未修 + 原因），由编排器决定是否再跑一轮回归。

---

## 方式 B：独立修复已记录的 bug（★ 最常用）

> **关键规则**：无需依赖任何 Sprint 流程——扫描当前用户 bug 文件（来源 A `docs/bugfix/{version}/bugfix-*-{user}.md` + 来源 B `docs/testing/{version}/研发自测·正式用例` 末尾「问题汇总清单」待修行）先落成 `docs/bugfix/` 条目（SKILL 唯一输入面）再调 SKILL 修复（先定根因再改码）、回填、编译校验，状态 待修→已修。**契约边界（约定 21）**：bugfix SKILL 是修复流程单一信源，命令端只做来源落条目 + 状态回填 + 项目级专项检查（路径/URL/proxy、部署监听、设计回写），不复述、不改写 SKILL 内部步骤。

**骨架表（详见 flow 文件，逐项执行不得略过）**：

| 步骤 | 做什么 | 关键约束 |
|------|--------|---------|
| 前置准备 | 读 systemPatterns/techContext/architecture + 详细设计/事实清单/对外开放接口 | bug 涉路径/URL/404 必精读「路径消费者点」表；对外接口修复红线禁引 Session/Cookie/JWT |
| Step 0 | ⛔ 口述 bug + 来源 B 清单待修行先落 `bugfix-{date}-{user}.md` 条目（带来源回链），**不得跳过直接改代码** | 去重仅回链 / exact match，不做语义模糊判断 |
| Step 1 | 调 `bugfix` skill（参数 `sprint-{NNN}` / 文件名 / 空=零散模式），prompt 附路径/URL/proxy + 配置 + 部署台账专项 | 路径类修完单点须巡检同表其他消费者点 |
| Step 2 | 推送分类与监听（约定 31.5） | 正式代码变更 push 后必走 CICD 监听 + 就绪探针 |
| Step 3 | 回填状态 / Commit / 修复报告链接（bugfix 记录 + 来源 B 清单行，不删行） | 根因权威落点 = SKILL 的 `-report.md`，⛔ 不复写 |
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

### Phase 0C.0：★ 版本落点决策门（累进前置，先于任何持久副作用）

> **同 `/sprint-dev` 分支 B「Phase 0B.0 版本落点决策门」**：当前版本已发布且未开始新版本规划时，**先弹版本落点门再动任何持久副作用**——三选一（re-release / 新 patch / 新 minor）与各自的 tag 影响、无人值守保守默认，**单一信源见 `/sprint-dev` Phase 0B.0，本处不复述**（约定 21）。<!-- dup-check: ignore 已改为指针，此行是指针本身 -->

### Phase 0C.1：累进 Sprint 序号 + 追加增量文档

Sprint 序号计算复用 `/sprint-full` Phase 0B.1 —— ⛔ 取号一律 `python3 {{AIDP_HOME}}/scripts/check_sprint_numbering.py next`（**跨全部版本**扫 MAX+1），绝不自己 glob 当前版本目录（那会让新版本又从 001 起）；**增量产物与 `/sprint-dev`·`/sprint-full` 完全同款**：

> ★ **两条落点路径，按入口分流，⛔ 不可混用**：
> - **约定 22 攒批级联**（`--ledger-cascade`，方式 B-2 的 Step 5、由收口点驱动）→ **就地改内容主文档正文**，⛔ **不新建 `NN_` 分册**（`check_cascade_landing.py` 见到新建 NN_ 即 exit 1）。这是 bug 修复触发上游文档同步时的**默认路径**。
> - **产品侧 PRD/原型变更的增量分册**（`--supplement={NN}`）→ 落 `NN_<业务主题>.md`、不改主文档正文。下方第 2~6 条描述的正是这条路径。
>
> ⛔ 下文「不写回主文档正文」只约束 `--supplement` 这一条，**不适用于 `--ledger-cascade`**——`dev-logic-architect` 的增量约定明写「统一 `NN_<业务主题>.md` … 增量身份靠产物头部回链 + `00_索引.md` 追加一行体现，**且不改内容主文档正文**」，命令端无权覆盖 SKILL 自己的产物契约（约定 21）。成因见 `{{AIDP_HOME}}/flows/sprint-bugfix/rationale.md`「设计增量为何不写回主文档」。
> **溯源不因此变弱**：`00_索引.md` 记「类型=补充 + 生成时间」，增量文档头部三类回链（专职索引 / 本轮输入来源 / 同轮其他层补充）指回主文档，比内联追加更可审计。

0. 约定 9 前置门已在 Phase 0C.00 执行（⛔ 不得挪到取号之后）。
1. 新编号 = `python3 {{AIDP_HOME}}/scripts/check_sprint_numbering.py next`（跨版本连续，同 `/sprint-full` Phase 0B.1）
1bis. **★ 档位判定（`--scale` 的唯一生产者）**：下面第 3 / 5 / 6 步都消费 `--scale={档位}`，⛔ 不判就传不出去、
   三个下游 SKILL 全部缺省回退 **L 档全套**（正文一行不省，等于白判）。判据**复用 `/sprint-dev` Phase 0B.1.1 步骤 2.5**
   （`REQ_COUNT` / `PAGE_COUNT` / `HAS_DDL` / `HAS_API` / `HAS_CONFIG` / `THIRD_PARTY` 四值 + S 语义子档），此处不复述；
   结果落 baseline `versions.{V}.sprints.{新NNN}.sup_scale`，并打印 `📐 档位：{S|M|L}`。
2. **研发需求增量**：经 `/sprint-requirements {version} --supplement={NN} [--unattended]` 编排 → `NN_<业务主题>.md`（**不直调 SKILL**——直调会跳过命令端的落盘归一 / 多系统拆分 / 头部元数据表 / AIDP 硬规范回检）
3. **设计增量**：经 `/sprint-design {version} --supplement={NN} --scale={档位} [--unattended]` 编排（内部以增量 prompt 驱动 `dev-logic-architect` 做根因分析 + 派生设计）→ 详细设计 / 接口设计 / 数据库设计的 `NN_<业务主题>.md`
4. 新增 SQL 文件 `docs/deployment/{version}/sql/增量/{NN}_<中文名>.sql`（按 SKILL 命名规范）
5. **研发执行计划增量**：经 `/sprint-plan {version} --supplement={NN} --scale={档位} [--unattended]` 编排 → `docs/plans/{version}/NN_<业务主题>.md`（⛔ 不是追加进 `01_研发执行计划.md`；也**不能**挂在 `/sprint-design` 上——它不产计划）
6. **★ 研发自测用例增量（L4，⛔ 不得跳过）**：经 `/sprint-selftest {version} --supplement={NN} --scale={档位} [--unattended]` 编排
   （研发自测唯一入口，内部 `dev-manual-testcase` 增量）→ `docs/testing/{version}/研发自测/NN_<业务主题>.md`。
   ⛔ `/sprint-full` Phase 0B.2 要求「必级联 L1→L2→L3→**L4**」，
   漏它即命中约定 22 的典型漏项「只补了详细设计、把需求与自测用例留在旧口径」，且 bug 修复恰是最该产回归用例的场景。
   纯技术内部调整（未触达任何用户可见功能）可标 N/A + 写明判据。
7. **各目录 `00_索引.md` 登记**：上述已生成的增量在对应目录 `00_索引.md` 各追加一行（类型=补充 + 生成时间）。

### Phase 0C.2：启动新 Sprint

```
执行：/sprint-start {新NNN} [--unattended]（无人值守时透传）
```

### Phase 1：开发修复

```
执行：`/sprint-dev {新NNN} skip-test [--unattended]`（开发已启动的 Sprint-{新NNN}；★ 必须显式传 `skip-test` 抑制 `/sprint-dev` 自带的 test→bugfix→close 串联，否则会与本命令 Phase 2-4 重复跑测试；后续 test/close 由本命令 Phase 2-4 接管。★ 本命令被 autopilot 增量路径以 `--unattended` 调起时**必透传** `--unattended`，令 `/sprint-dev` 的 UI 门/约定22 门消费 PRD 预声明、不弹窗）
```

### Phase 2：测试

```
执行：/sprint-test [--unattended]（★ 本命令带 --unattended 时必透传，否则下游弹门挂死）
```

### Phase 3：Bugfix 循环（回归中发现新 bug 时）

```
do {
  /sprint-bugfix sprint-{新NNN} [--unattended]      # 方式 B
  /sprint-test [--unattended]
} while (仍有未修复 && 循环次数 < 5)
```
★ 循环内两条**同样必透传** `--unattended`（与 Phase 1/2/4 同款，无例外）：本循环里的 `/sprint-test` 若遇用例缺失会调 `/sprint-selftest`，进而在 `dev-manual-testcase` 的强制询问第零步挂死——**无人值守链最深、最难察觉的一处停摆点**。

### Phase 4：关闭

```
执行：/sprint-close {新NNN} [--unattended]（★ 同上必透传；close 的机械推导验收只认该 flag）
```

**跳过串联**：参数含 `skip-test` → 只做 Phase 0C + 开发，不自动 test/close。

---

## 输出

### 方式 B 输出

```
✅ /sprint-bugfix 完成（{version} / {user}）

处理结果（位于 docs/bugfix/{version}/bugfix-*-{user}.md）：
- B-{YYYYMMDD}-01: ✅ 已修复 — {问题标题}
  根因：{见 SKILL 修复报告对应小节}
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
🎉 /sprint-bugfix "{描述}" 完成（自动累进 Sprint-{新NNN}）

📋 本轮增量产物（统一 `NN_<业务主题>.md`，不改内容主文档正文）：
- docs/requirements/{version}/研发需求/NN_<业务主题>.md（研发需求增量）
- docs/design/detail/{version}/NN_<业务主题>.md（详细设计 / 接口设计 / 数据库设计增量，按需）
- docs/deployment/{version}/sql/增量/{NN}_<中文名>.sql（新增 DDL/ALTER 文件，如有；序号续当前版本最大序号 +1）
- docs/plans/{version}/NN_<业务主题>.md（研发执行计划增量）
- 各目录 00_索引.md：各追加一行（类型=补充 + 生成时间）

各阶段摘要：
  Phase 0C：✅ 增量文档已产出并登记
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
/sprint-bugfix                            # 修复所有待修复 bug

# 场景 3：按 Sprint 过滤
/sprint-bugfix sprint-003                 # 只修 Sprint-003 相关的 bug

# 场景 4：指定文件
/sprint-bugfix bugfix-20260509-alice.md

# 场景 5：★ 较大 bug，需要新 Sprint + 设计变更
/sprint-bugfix "修复批量导入重复校验逻辑，需新增唯一约束和查重接口"
# 自动：累进 Sprint-007 → 追加设计 → 开发 → 测试 → 关闭

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
