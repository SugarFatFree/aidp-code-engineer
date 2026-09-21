# /sprint-design — 详细设计生成

你正在执行 `/sprint-design` 命令，为当前版本生成详细设计文档。

**★ 本命令是 skill 编排器**：调用 `dev-logic-architect` skill 生成详细设计方案（技术架构、接口定义、数据库设计、测试方案）。

> 🚨 **完成门槛硬约束（必读，违反等同未完成）**
>
> 完成判定见下方 [§★ 输出前硬门](#-输出前硬门回检清单--三合一回写校验不可跳过) — 命令收尾时必须真实跑完该区的回检清单 + 三合一回写校验脚本（基线 + ADR + 金额字段），退出码为 `0` 且看到 `✅ 基线 + ADR + 金额字段 三合一回写校验通过` 字样才算完成。

参数：$ARGUMENTS（可选）
- 第 1 位：版本号（如省略，从 AGENTS.md 当前状态读取）
- `--supplement={NN}`：★ 补充模式 — 产品在版本开发中途更新了 PRD **或原型**，由 `/version` 检测变更后传入；本命令产出详细设计 / 接口设计 / 数据库设计的增量 `NN_<业务主题>.md`（约定 15 统一命名，文件名不带"补充"字眼、补充身份记入 `00_索引.md`，按实际有变更的范围）而非覆盖主文档；详见下方「补充模式」段
- `--ledger-cascade`：★ 约定 22 级联落盘 — 由攒批收口子 Agent / `--cascade-now` 即时级联调用；**就地改** `docs/design/detail/{version}/` 的 `01_详细设计.md`·`02_数据库设计.md`·`03_接口设计.md` 正文（按实际范围） + 刷该目录 `00_索引.md` 生成时间；⛔ **不新建任何分册**（`NN_<业务主题>.md` 是产品侧 PRD/原型变更与口述累进的命名空间），⛔ 不产任何中转增量册；与 `--supplement={NN}` 互斥；详见下方「补充模式」段
- `--scale=S|M|L`（可选）：需求规模档位，透传给 `dev-logic-architect` SKILL（缺省回退 L 现状全套）。由 `/version` Step 2.4.1.5 自动判档时自动带入；直接调用可手动指定。调 SKILL 时随 prompt 传入 `scale=<档位>`
<!-- dup-check: ignore 四个规划子命令各需在自己参数表里声明，刻意的四份、非漂移 -->
- `--unattended`（可选）：★ **无人值守上下文标记**（由 `/version`·`/sprint-autopilot`·`/sprint-test` 等上游透传）——本命令内**一切 `AskUserQuestion` 与"暂停待用户裁决"一律不弹**，改按下方各门的确定性默认自动推进并留痕；**绝不静默跳过质量门**，只是把"问人"换成"按保守默认走 + 记录"。⛔ 上游传了而本命令不认，flag 会被静默丢弃、在无人值守链里挂死。
  - 本命令的门：Step 0.5.5 工程结构/运行时端点契约确认门、Step 0.6 事实采集缺项询问 → 无人值守下的取值口径**单一信源 = `flows/sprint-design/step-0.6-事实采集-1.md`**（本处不复述、不自带默认；⛔ 两处各写一套默认值时，"这条链会不会熔断"会取决于执行体先读到哪一份）。
  - **★ Step 1.6 路径 base 回检不匹配** → 无人值守**既不暂停、也不放行**：写「⚠️ 路径回检告警」表后**返回失败信号交上游熔断**（口径同 `/sprint-plan`）。
    ⛔ 该门交互式的两个处置（改设计对齐代码 / 声明改代码意图后重跑）**都只有人能选**；不给确定性默认时，无人值守只剩两条烂路——
    **停在此处等一个永不到来的回答**（`/loop` 每轮撞同一处、无 streak 无冻结），或**当告警记一行继续落盘**（把带错 base 的接口设计放进开发）。
    ⚠️ greenfield 首版必命中：Step 0.6 让事实清单 base 落 `<待确认>`，而任何真实 base 都 ≠ `<待确认>`。
  - **★ Step 1.6.5 联动修改** → 无人值守**自动补齐联动改动并留痕**，不询问。
  - **★ 缓存 / 锁策略两道确认门**（`check_cache_user_confirmed` / `check_lock_strategy`）→ 无人值守**取保守默认**（不启用缓存 / 用最严格锁）+ **登记进 `99_待澄清问题清单.md`**，不阻塞、不静默采用激进值。
- `--has-open-api`（可选）：强制开启对外开放接口设计（PRD 写法隐晦、机械信号未命中时手动指定）；详见 Step 1.6 前的信号识别段

## 前置流程

按 `docs/init/06_版本与用户目录约定.md`：
1. **{version}** ← `AGENTS.md`「当前状态.当前版本」，读不到则询问。
2. **{user}** ← `git config user.name`

## 前置检查

1. 确认需求文档已存在：`ls docs/requirements/{version}/研发需求/{01_研发需求,00_索引,00_研发需求}.md 2>/dev/null` 任一命中即可（拆分态 `00_索引.md`+`01_研发需求.md` / 历史裸 `00_研发需求.md` 兼容）
   - 若不存在 → **停止执行**，提示"需求文档不存在，请先执行 /sprint-requirements"
2. 确认设计目录存在：`docs/design/detail/{version}/`（由 `/version` 创建）
3. Architect Agent 必读：`memory/databaseBaseline.md`、`memory/systemPatterns.md`、`docs/architecture/`

## 执行步骤

### Step 0：★ 跨版本对比 — 识别增量

本命令的核心定位是**为当前版本生成增量设计**，而不是从零重建。执行前必须先确定相对哪个"前一版本"做增量。

#### Step 0.1：定位前一版本

按以下规则识别 `{prev-version}`：

1. 扫描 `docs/design/detail/` 下的所有版本目录，过滤掉 `{version}` 本身；**并跳过 `全量/` 目录**（`docs/design/detail/全量/` 是 `/version` 正式发布生成的**跨版本全量详细设计**，非 `V*` 版本目录，不参与前版基线识别）
2. 按版本号语义排序，取**版本号小于 `{version}` 的最大版本**作为前一版本
3. 该前一版本目录下必须存在**详细设计文档**（用 glob 探测，兼容三态：拆分态 `00_索引.md` / 单份态 `00_详细设计.md` / 历史存量并列态裸名 `详细设计.md` / 拆分分册 `01_详细设计.md`——`ls docs/design/detail/{prev-version}/{00_索引,00_详细设计,详细设计,01_详细设计}.md 2>/dev/null` 任一命中即视为有前一版本），否则视为无前一版本

例：当前 `{version}=V0.2.0`，已有 `V0.1.0` 和 `V0.1.1` → `{prev-version}=V0.1.1`

#### Step 0.2：读取前一版本的设计基线

如 `{prev-version}` 存在：

- 读取前一版本设计目录**全部分册**：`docs/design/detail/{prev-version}/*.md`（用 glob 一次读全，**不依赖固定文件名**——兼容拆分态 `00_索引.md`+`01_详细设计.md`/`02_数据库设计.md`/`03_接口设计.md`/… 与历史存量并列态裸名 `详细设计.md`/`数据库设计.md`/`接口设计.md`）
- 读取 `memory/databaseBaseline.md`（项目级，跨版本累积，已包含所有历史表）
- 读取 `memory/systemPatterns.md`（项目级，累积 ADR）

如**无** `{prev-version}`（本版本是首版）：

- 跳过 Step 0，按完整设计模式执行
- 在输出末尾标注"首版完整设计"

#### Step 0.3：四象限对比 — PRD 要求 × 代码已实现（代码作为最终事实源）

> **核心契约**：最终产物是代码。**对比基线 = 前一版本设计 ∪ 当前 `code/` 现状**（双基线），不能只比前版本设计——否则会漏掉"代码已改但文档没动"的事实漂移。代码现状清单由 Step 0.6.4.7 扫得，先跑那步再回到这里。

读取 `docs/requirements/{version}/研发需求/01_研发需求.md`（历史裸 `00_研发需求.md` 兼容；PRD 要求源），与 Step 0.6.4.7 的「代码现状清单」做**四象限对比**，按维度（模块/页面 × API 接口 × 数据库表/字段 × 外部依赖）逐项分类：

| 象限 | PRD 要求 | 代码已实现 | 处理 |
|------|---------|----------|------|
| ① 保持 | ✓ | ✓ | 仅复用引用，不重复设计内容 |
| ② **新增** | ✓ | ✗ | 设计文档给出完整设计（接口/表/页面），下游 /sprint-dev 落地 |
| ③ **代码超前**（关键！）| ✗ | ✓ | **设计文档补写一段记录该实现**——而不是要求代码回退！代码是事实，设计追平。在补写段标注「💡 代码已实现于 commit:<hash>，本次设计回溯」 |
| ④ 不存在 | ✗ | ✗ | 忽略 |

**为什么有 ③**：开发中产品口述新功能、研发用 `/sprint-dev "<描述>"` 直接开发（详见 sprint-dev.md 分支 B 的 Phase 0B.1.1）——这种场景下代码已有功能但设计文档可能未同步（如 sprint-dev 的 Step X 回写失败 / 用户跳过了文档同步）。/sprint-design 重跑时**必须主动追平**，不能装看不见。

#### Step 0.4：传递增量上下文给 dev-logic-architect

在 Step 1 调用 skill 时，将四象限变更清单 + 前一版本设计文件 + 当前代码现状清单**一并**作为输入，明确要求 skill：
- 象限 ① → 生成引用条目（指向 `{prev-version}` 对应章节）
- 象限 ② → 完整新设计
- 象限 ③ → "代码回溯补写"段，标注 commit hash + 文件来源（如 `code/backend/{后端项目}/src/.../XxxController.java:42`）；接口签名 / 表字段 / 页面结构以**当前代码**为准
- 象限 ④ → 不出现在输出

#### Step 0.4.5：★ 识别"对外开放接口"信号（配合 dev-logic-architect 强制规范）

在 Step 1 调用 skill 之前，命令端必须扫描以下来源判定本版本**是否涉及对外开放接口**（供第三方系统/外部租户调用），并设置标志位 `HAS_OPEN_API ∈ {true, false}` 传给 skill：

**扫描范围**：
- `docs/requirements/{version}/产品提供/**/*.md`（PRD 原始文档）
- `docs/requirements/{version}/研发需求/**/*.md`（已生成的研发需求）
- `docs/requirements/PRD-*.md`（项目级 PRD 兜底）
- 前一版本设计（如 `{prev-version}` 存在）：`docs/design/detail/{prev-version}/对外开放接口.md`、`接口设计.md`

**判定信号**（任一命中即 `HAS_OPEN_API=true`）：

| 类别 | 关键词正则（grep -iEn） |
|------|----------------------|
| 中文术语 | `对外开放接口\|对外接口\|开放接口\|开放平台\|开放 API\|第三方系统调用\|第三方调用\|外部系统集成\|对外暴露` |
| 英文术语 | `Open API\|OpenAPI\|external API\|public API\|third-party (call\|integration)` |
| 路径前缀线索 | `/(api/)?open/\|/external/\|/public/v` |
| 前版设计存在 | `ls docs/design/detail/{prev-version}/*对外开放接口.md` 有命中 → 本版本默认也需要（⛔ glob：本命令规定新生成为 `NN_` 前缀，只认裸名会让信号在版本间必然自灭） |

**输出**：把 `HAS_OPEN_API` 与命中证据（文件:行号 + 匹配片段）记入命令端上下文，供后续 Step 0.6（事实采集 — 额外列出对外接口 base 前缀）+ Step 1（调 skill 的 prompt）+ Step 1.5（落盘文件名）+ Step 1.7（对外接口规范回检）使用。

> 该信号是**机械识别**，命中即触发 skill 拆分；若 PRD 写法隐晦未命中，用户也可在 Step 1 调用前手动 `--has-open-api` 强制开启（命令端识别参数）。

#### Step 0.4.6：★ 识别"需第三方提供接口"信号（配合 dev-logic-architect 职责边界强制规范）

在 Step 1 调用 skill 之前，命令端必须扫描以下来源判定本版本**是否需要调用第三方系统提供的接口**（即我方作为消费方，需第三方出文档），并设置标志位 `HAS_THIRD_PARTY_DEP ∈ {true, false}` 传给 skill：

**扫描范围**（同 Step 0.4.5）。

**判定信号**（任一命中即 `HAS_THIRD_PARTY_DEP=true`）：

| 类别 | 关键词正则（grep -iEn） |
|------|----------------------|
| 中文术语 | `调用第三方\|第三方接口\|三方接口\|外部接口\|外部系统提供\|接入第三方\|对接第三方\|集成对接\|外部依赖\|需要?第三方提供\|需要?[^，。、\s]{1,12}(系统\|平台\|服务)提供` |
| 英文术语 | `third-party API\|external integration\|call (an?\\s+)?external\|integrate (with\\s+)?\\w+ (system\\|service\\|API)` |
| 前版设计存在 | `ls docs/design/detail/{prev-version}/*集成对接.md` 有命中 → 本版本默认仍需要（⛔ glob，同上）|

**输出**：把 `HAS_THIRD_PARTY_DEP` 与命中证据记入命令端上下文，供后续 Step 1（调 skill 的 prompt）+ Step 1.5（落盘文件名）+ Step 1.7.5（第三方接口清单回检）使用。

> 与 Step 0.4.5 的区别：0.4.5 是**我方对外开放**（我方写接口给第三方调用），0.4.6 是**我方消费第三方**（第三方写接口给我方调用），两者方向相反，可同时为 true。

#### Step 0.5：写入版本基线引用

在本版本 `01_详细设计.md` 文件头部追加「基线引用」章节（★ 链接指向前一版本**导航锚 `00_索引.md`**，避免裸名 `详细设计.md` 断链——前版现携 `01_详细设计.md`/`02_数据库设计.md`/`03_接口设计.md` + `00_索引.md`，约定 14/15）：

```markdown
## 基线引用

本版本相对前一版本 **{prev-version}** 增量设计。

- 前一版本设计基线：见 [前一版本设计索引](../{prev-version}/00_索引.md)（从中导航到该版 `01_详细设计.md` / `02_数据库设计.md` / `03_接口设计.md`）
- 本版本变更清单：见下方第 1 节「变更范围概述」
- 未列出的模块/接口/表，视为**完全复用**前一版本的设计，不重复定义
```


#### Step 0.5.5 + Step 0.6：★ 工程结构/运行时端点契约确认门 + 后端/前端事实采集（代码为唯一信源）

> ⚠️ 关键规则：进入 `接口设计.md`/`详细设计.md` 的端口 / context-path / API 前缀 / proxy 等"真实事实"一律从 `code/` 实配读取、**禁凭印象推断**；greenfield/首版无代码时先过端点契约确认门（用户主权，给推荐默认但不静默采用）并 seed 进事实清单，事实来源即该确认值而非 AI 现编。

| 子步骤 | 职责（骨架） |
|--------|------|
| 0.5.5 | 工程结构 + 运行时端点契约确认门（greenfield/首版必过；AskUserQuestion 一次收全端口/context-path/`{子项目}名`等，落盘技术选型/配置项清单/事实清单 seed/PRD deployment；与约定 18 `{子项目}名` 确认门合一）|
| 0.6.1–0.6.4 | 判断是否采集 + 按框架扫后端/前端/部署反代事实 |
| 0.6.4.5 | 扫"路径消费者点"（base 变更级联清单，反逻辑守卫高发区）|
| 0.6.4.7 | 全扫 code/ 代码现状清单（Step 0.3 四象限"代码已实现"列源头）|
| 0.6.4.8 | 关联项目源码事实采集（跨项目复用识别；路径存 Claude 长期记忆、绝不入 git）|
| 0.6.5 | 整理事实清单 → `docs/design/detail/{version}/事实清单.md`（含事实清单模板全文）|
| 0.6.6 | 传 skill 硬约束（代码事实优先，禁编造 base/context-path）|

**进入本段第一动作 = 按序 Read 以下 3 个分片**，逐项执行、绝不凭骨架或记忆略过子步骤：
- `{{AIDP_HOME}}/flows/sprint-design/step-0.6-事实采集-1.md`（Step 0.5.5 端点契约确认门 + Step 0.6 事实采集 0.6.1~0.6.4.5 扫描后端/前端/部署/路径消费者点）
- `{{AIDP_HOME}}/flows/sprint-design/step-0.6-事实采集-2.md`（Step 0.6.4.7 代码现状清单 + Step 0.6.4.8 关联项目采集）
- `{{AIDP_HOME}}/flows/sprint-design/step-0.6-事实采集-3.md`（Step 0.6.5 事实清单模板 + Step 0.6.6 传 skill 硬约束）

#### Step 0.7：★ 原型内容基线 + 设计令牌前置产出（有原型必产，**必须早于 Step 1**）

> ⛔ **时序铁律**：这两份是 Step 1 调 `dev-logic-architect` 的**上游输入**（要求详设/接口/数据库覆盖到基线每个"实现"项），**必须在 Step 1 之前产出**——放在 Step 5 产出会造成"消费点早于生产点"、Step 1 拿不到基线，Step 5 再补也已经晚了。

如果 `docs/prototype/{version}/code/` 存在原型代码 → **此处**读取 `{{AIDP_HOME}}/agents/ui.md`，跑 UI Agent 流程 A 的 **Step 0（4 情形决策门，约定 4 的 C/D 须用户显式选）** → **Step 1.5（原型内容基线）** → **Step 4（设计令牌，情形 B/C）**，产出：

> ⛔ **Step 0 不可跳过**：它是约定 4「情形 C/D 由用户显式选」的**唯一触发点**。跳过它 → 视觉基准来源无人裁定，只能靠 Frontend Agent 在开发期兜底追问（`agents/frontend.md` 明确那是异常路径），且情形 D 的高保真生成会失去授权依据。

- `docs/design/detail/{version}/NN_原型内容基线.md`
- `docs/design/detail/{version}/NN_设计令牌.md`（情形 B/C）

**完整规则**（逐页穷举口径 / 处置四态 / 决策门显式化 / 序号归一 / `00_索引.md` 留痕 / version-auditor F 回检）见下方 **Step 5.0**——本步只负责**把产出时机提到 Step 1 之前**，不复制其规则。无原型则跳过本步（Step 1 调用参数中对应两项标 N/A）。

Step 5 之后只做 **UI 规范其余部分**（流程 A 的 Step 2~3）+ 对本步产物的**回填校正**（若 Step 1~4 期间原型有更新），不重复产出。

### Step 1：调用 dev-logic-architect skill

**★ 项目级补充 — 业务计数声明表的下游消费（喂进 SKILL prompt）**：
表本身按 `dev-logic-architect` **核心原则 28 / 检查项 36** 产出，**列名、列序、GFM 格式一律以 SKILL 为准**
（硬门 = 其 `scripts/check_count_claim_table.py`，`EXPECTED_COLS` **精确全等**比对，表头后**必须有** `| :- |`
分隔行）。⛔ **本处不复制列定义**——复制过一次就会在上游调整列名时静默漂移，照抄的设计表直接被判 C1 Critical
（本项目已实际发生过一次）。命令端只补 SKILL 没有的两件项目级事项：

1. **登记范围**：本版所有**会被文档反复引用的业务计数**（检测项数 / 支持格式数 / 角色数 / 状态机态数 …）。
2. **项目级回扫入口**：有了该表，`python3 {{AIDP_HOME}}/scripts/check_count_claims.py --project-claims docs/design/detail/{version}/`
   就能把散落面候选列全，人只需逐条判定哪些是「取值域全集」的合法留存、哪些是必须改的计数断言。
   **Why**：一次「固定 14 项 → 动态 13/14」的口径变化，实测散落约 25 处，全靠人肉 grep。

⚠️ **该表本身是「语义·口径变更」的典型载体**，它变了要按约定 22 级联。

**★ QR 变更范围裁剪协议接线（必须传，别让增量迭代付全量 QR 的代价）**：`dev-logic-architect` 的质量检查支持按本轮变更范围裁剪，**唯一入参 = `qr_delta_scope`（可选，不传 = 全量）**。⛔ 命令端**不得自造 `qr_mode`**——该 SKILL 从未定义它（`qr_mode` 是 `dev-manual-testcase` 独有概念），凭空传等于修改 SKILL 契约（违反约定 21）且被静默忽略。命令端按下面两条传：

- **全量生成**（首次规划 / 主文档重生成）→ **不传 `qr_delta_scope`**（SKILL 契约：不传 = 全量）。
- **增量补充**（`/version` 补充模式〔情况 B-2〕检出 PRD/原型变更后**派发本命令并传入** `--supplement={NN}`；⛔ `/version` 自身没有 `--supplement` flag，别照字面去敲）→ 传 `qr_delta_scope = <本轮 NN_<业务主题>.md 的专题名 / 章节清单>`。
- ⛔ **只裁「语义核对」的范围，机器门一律全量跑**（SKILL 明文，标「全量」档的维度不接受裁剪——它们的失效形态正是「新增这一处与旧的那些不一致」，只看增量内部一个都发现不了）。算不出 Δ 就退回全量并注明，**宁可多算一个专题、绝不漏传播一处语义**。命中「语义/口径/单位/默认值/状态机/权限范围变更（无新增实体）」或跨版本作废判定的项，其受影响专题**强制并入 Δ**（即便无文件命中）；变更落在跨专题共享单元（公共基础设施 / 基类实体 / 共享 DTO / 全局配置）→ 把所有引用该单元的专题并入 Δ。

使用 `Skill` 工具调用 `dev-logic-architect`，由 skill 自主完成详细设计生成 + 内置多维度独立 Agent 检查 + 多轮 Quality Review 阻塞完成判定。**SKILL 内规则为单一信源**，命令端按 AGENTS.md 约定 21 不复述、不修改，仅做编排和项目级补充。

> 详细规则查 `{{AIDP_HOME}}/skills/dev-logic-architect/SKILL.md`；命令端只负责：① 传参（PRD/原型/前版基线/变更清单/`HAS_OPEN_API`+`HAS_THIRD_PARTY_DEP` 信号）② Step 1.5 落盘文件名 override（项目级中文文件名约定）③ Step 1.6~1.7.5 + SKILL 脚本复核 + 1.8 落盘后回检（统一派子 Agent 执行，脚本清单以 SKILL Quality Review 为单一信源）。

**调用参数**（按 SKILL 输入要求传入 PRD / 原型 / 设计上下文路径）：
> ★ **WebMCP 条件启用入参**（默认不传；绝大多数项目无此段）：`dev-logic-architect` 的**检查项 33「WebMCP 前端能力设计完整性」**（上游称「检查项 N」，本文档余处简称维度 N）是**入参门控**、
> 且 SKILL 明令**不自行探测是否启用**——**命令端不传 = 该维度永不启用**，启用了该能力的项目会
> 静默漏掉这一层质量门。故调 SKILL 前先取判定（启用判定的唯一实现，⛔ 不要自己 grep PRD）：
>
> ```bash
> python3 {{AIDP_HOME}}/scripts/check_webmcp.py --detect --json    # → enabled / entry_symbols / launch_command
> ```
>
> `enabled: true` → 随 prompt 传 `webmcp_enabled: true` + `webmcp_entry_symbols: <脚本返回的数组原样>` + `webmcp_launch_command: <脚本返回的原样>`（⛔ 三个 SKILL 都明写「不要自拟」）
> （⚠️ 后者**不可省略也不可写死**：挂载位置已迁移过一次、规范仍在演进，上游缺该入参会直接报错而非猜默认值）；
> `enabled: false` → **什么都不传**，不提、不留位置。

- **PRD 路径**：`docs/requirements/{version}/研发需求/`（含 `01_研发需求.md`（历史裸 `00_研发需求.md` 兼容）或拆分的 `0?_*.md`）
- **原型路径**：
  - `docs/prototype/{version}/code/`（HTML 原型代码，如存在）
  - `docs/prototype/{version}/mockup/`（高保真原型，如存在）
- **★ 原型内容基线**（Step 0.7 产出，有原型必传）：`docs/design/detail/{version}/NN_原型内容基线.md` — 显式作为上下文传入，要求详设/接口/数据库覆盖到基线每个"实现"项的字段、状态与操作逻辑级（约定 4 / 33；命令端只传路径 + 笼统说明，不复述 SKILL 规则）
- **★ 设计令牌**（Step 0.7 产出，情形 B/C 有则传）：`docs/design/detail/{version}/NN_设计令牌.md`

**输出路径约定**（命令端通过 prompt 显式告诉 skill，覆盖 skill 默认 `docs/design/{项目名}/`）：
- **目标目录**：`docs/design/detail/{version}/`
- **基础骨架专题**（★ 下列为**专题逻辑名**，**取代** skill 默认单文件名 `01_{项目名}_详细设计方案_v{版本号}.md`（skill 现默认 `01_` 起、`00_` 让位专职索引）；**实际落盘文件名一律按下方「二态」加 `00_`/`NN_` 前缀**——严禁裸名，见 dev-logic-architect「严禁无前缀裸文件名」硬核项）：
  - 详细设计（模块结构 + 技术栈 + 公共组件，**必出**）
  - 数据库设计（如有数据库）
  - 接口设计（如有 API；★ 当 `HAS_OPEN_API=true` 时本专题**仅承载内部接口**，对外接口拆到独立专题「对外开放接口」）
  - 按需专题：对外开放接口（★ `HAS_OPEN_API=true` 时**必出**）/ 安全设计 / 缓存设计 / 集成对接 / 消息异步设计 / 部署架构 / 测试方案 / 性能设计
- **★ 新生成一律索引态（无论 1 份还是 ≥2 份内容主文档）**：采用简洁命名"**两位数字序号 + 中文专题名**"，**override** SKILL 默认词典——`00_` 槽位恒给专职索引 `00_索引.md`，内容主文档一律从 `01_` 起。完整示例：`00_索引.md` / `01_详细设计.md` / `02_数据库设计.md` / `03_接口设计.md` / `04_对外开放接口.md` / `05_集成对接.md` / `06_测试方案.md` / `07_安全设计.md` …；**严禁嵌套二级序号**（如旧 `02_A3_01_用户域数据表.md` ❌、`02_数据库设计_01_用户域.md` ❌），按业务域拆分时改用**顺延序号**（如 `02_用户域数据表.md` / `03_订单域数据表.md`，模块归属在主文档"文档结构与拆分说明"表中记录）
  - **单份内容亦走索引态**：即便只产 1 份专题主文档，也产出 `00_索引.md` + `01_<专题>.md`（与 dev-logic-architect SKILL「`00_索引.md` 为唯一导航锚、即便只产一份也产 `00_索引.md`+`01_`」及约定 14/15 一致）。

**额外提示（命令端通过 prompt 传给 skill 的项目级上下文，不复述 SKILL 内规则）**：
- ★ **前版基线 + 变更清单**（来自 Step 0.1 + 0.3）：定位到 `{prev-version}` 时把 `docs/design/detail/{prev-version}/` 全部分册作为基线传入，skill 仅产出"新增/变更/移除"；首版从零生成。这是项目级增量发布要求，非 SKILL 内置概念。
- ★ **`HAS_OPEN_API` 信号**（来自 Step 0.4.5）：把 `true/false` 显式传给 skill。`true` 时 skill 自动按 `references/flow-output-format.md`「对外接口文档强制要求」执行；命令端不复述条款，仅 override 落盘文件名为 `对外开放接口.md`（与 SKILL 拆分编号约定对齐）。
- ★ **`HAS_THIRD_PARTY_DEP` 信号**（来自 Step 0.4.6）：`true` 时 skill 自动按 `references/flow-output-format.md`「需第三方提供接口的强制要求」执行；命令端按产物性质**分两处 override 落盘**：
  - ① **我方内部对接设计**（如何调用对方已交付能力）→ `docs/design/detail/{version}/集成对接.md`（与其他详设同目录）；
  - ② ★ **「提给第三方的需求」**（请对方新建/补充接口的**对外业务诉求**）→ **`docs/references/{version}/`**（版本专属对外需求目录，与内部详设分离；结构与生命周期见 `06_版本与用户目录约定.md` §2.6）。该对外需求文档是 `01_研发需求.md` + 详设的**上游约束**，**必须**被二者「关联文档」引用（`/version` Step 2.4.6 引用链强制、`version-auditor` E 审计，缺失阻塞）。

**★ SKILL 路径占位符显式传参**：SKILL「路径占位符实施指南」会自动扫描项目目录，但首版/空项目场景可能扫描不到匹配目录而降级到 SKILL 通用默认值（`db/migrations/` 等）。命令端**显式传**以下 5 个占位符的 AIDP 实际路径，**禁止 SKILL 自动推断**——映射表权威在 `docs/init/06_版本与用户目录约定.md` §2.5.7：

| SKILL 占位符 | 显式传值 |
|--------------|---------|
| `{SQL脚本目录}` | `code/sql/`（**暂存位**——SKILL 原生生成到 **`code/sql/v{版本号}/{NN}_<中文名>.sql`（★ 带 `v` 前缀，dev-logic-architect SKILL 硬约定，见其「SQL 版本严格隔离铁律」）**，命令端 Step 3.2 再 `git mv` 搬迁到**最终位置** `docs/deployment/{version}/sql/增量/{NN}_<中文名>.sql`）|
| `{文档目录}` | `docs/design/detail/`（详细设计本身的落盘目录就是 `{version}/` 子目录下）|
| `{API文档目录}` | `docs/design/detail/`（AIDP 合并到设计目录，体现为 `接口设计.md` + `对外开放接口.md`）|
| `{测试文档目录}` | `docs/testing/`（Sprint 粒度按 `{version}/sprint-{NNN}/` 组织）|
| `{配置目录}` | `env/` + `docs/deployment/{version}/`（真实运行时 + 文档化清单分层；详见 AGENTS.md 约定 25）|

> SKILL.md 是单一信源（含「🔗 上游引用规则 L1-L3」/「拆分数量控制」/「字典/枚举三件套」/「不中断原则」/「对外接口文档强制要求」/「第三方接口职责边界」/「Mermaid ER + 禁 FK」/「货币金额整数化」/「历史 SQL 风格沿用」/「不臆造兜底」等所有规则）；命令端按 AGENTS.md 约定 21 不复述、不修改，仅传信号 + 路径 override + Step 1.6~1.7.5 +「SKILL 脚本兜底清单」 + 1.8 落盘后兜底回检。

> 命令端**仅在调用 prompt 中显式 override 输出路径/命名**——这是 skill 文档允许的"用户指定路径"机制，不构成对 skill 的修改。

**★ 项目级补充 — 信号传递（精简，按约定 21）**：

```
【项目级补充 — 信号传递】

本次调用是 /version 串联场景，**上游来源齐全**：
- 研发需求：docs/requirements/{version}/研发需求/*.md（Step 2.4.1 已产出）
- 原型代码：docs/prototype/{version}/code/（必读，含 .jsx/.vue/.html 等）
- 高保真原型：docs/prototype/{version}/mockup/（如存在则必读）
- 事实清单（如 code/ 已存在）：docs/design/detail/{version}/*事实清单.md

【信号】上游齐全 → 请走严格模式（不走"独立使用上游不全时"的宽松判定）。

SKILL 内置规则单一信源（命令端按约定 21 不复述，不写死行数/维度名）：三类元素段头部上游引用 + 上游溯源完备性，均由 SKILL 内置 QR 硬核回检 + 命令端 Step 1.8 兜底 bash grep（具体头部行数详见 SKILL.md）。
```

命令端把上述 prompt 作为「调用约束」原样追加到 SKILL 调用的 system prompt 末尾。SKILL QR 通过后，命令端在 Step 1.8 末尾再用 bash grep 兜底核验。

### Step 1.5：★ AIDP 产物落盘（命令级编排责任）

skill 返回融合后的设计内容（可能是单一长文，也可能是按主题分块的多段）。命令端把 skill 输出按 AIDP 产物约定**落盘到 `docs/design/detail/{version}/` 目录**：

| 约束 | 说明 |
|------|------|
| **目录位置** | 所有详细设计文档统一放 `docs/design/detail/{version}/` 下（命令端决定路径，skill 不知道）|
| **文件名** | 中文专题逻辑名（★ 实际落盘按下方「多份编号」行二态加 `00_`/`NN_` 前缀、**严禁裸名**）：详细设计 / 接口设计 / 对外开放接口（★ HAS_OPEN_API=true 必出）/ `数据库设计.md` / `安全设计.md` / `缓存设计.md` / `集成对接.md`（★ HAS_THIRD_PARTY_DEP=true 必出；我方**内部对接设计**。其中「提给第三方的需求」对外业务诉求**另落** `docs/references/{version}/`，不留本文件，见 06 §2.6 + 本命令 Step 1 `HAS_THIRD_PARTY_DEP` 信号）/ `消息异步设计.md` / `部署架构.md` / `测试方案.md` / `性能设计.md` 等 |
| **基础骨架（推荐）** | 至少 `详细设计.md`（模块结构 + 技术栈 + 公共组件）；有 API 则 `接口设计.md`（**仅内部接口**）；有对外接口则**单独**生成 `对外开放接口.md`，**不要塞回** `接口设计.md`；有数据库则 `数据库设计.md` |
| **专题扩展** | 按 skill 输出涵盖的主题按需追加专题（对外开放 / 安全 / 缓存 / 集成 / 消息 / 部署 / 测试 / 性能 …）|
| **编号（约定 15 强制，简洁命名 + 数量控制；★ `99_` 固定给待澄清问题清单）** | **★ 新生成一律索引态**（无论内容主文档 1 份还是 ≥2 份）：`00_索引.md` + `01_`~`98_` 内容主文档 + `99_待澄清问题清单.md`（`00_` 槽位恒给索引、`99_` 固定末位）。落盘校验按 dev-logic-architect `check_doc_split.py`（脚本仍识别**历史存量并列态**裸中文名与单份态 `00_<专题>.md` 并放行，但**新生成一律走索引态**、不产出裸名并列/单份态；判定、编号细则与 ❌ 反例见 SKILL，命令端不复述）。★ **命令端专属「代码事实基线」保留位**（SKILL 不感知）：`事实清单.md`（Step 0.6.5 生成）在索引态下由 Step 1.5.1 归一为 `98_事实清单.md`（紧挨 `99_待澄清` 前的保留高位）；下游一律用 glob `*事实清单.md` 定位|
| **拆分文件数回检（命令端落盘后核验）** | Step 1 prompt 已传入「拆分数量控制（Critical）」给 SKILL；落盘后命令端**额外做一次可执行回检**。★ **计数只算「内容主文档」，排除管家文件**——`00_索引.md`、`98_事实清单.md`、`99_待澄清问题清单.md`，以及规划期强制产出物 `NN_原型内容基线.md` / `NN_设计令牌.md`（它们由命令端 Step 5.0 强制产出、不是 SKILL 的设计分册；连它们一起数会让 S/M 档合规产出被误判碎片化而硬停）：<br>`CONTENT=$(ls docs/design/detail/{version}/*.md \| grep -vE '/(00_\|98_\|99_)' \| grep -vE '原型内容基线\|设计令牌')`；`FILES=$(echo "$CONTENT" \| wc -l)`；`MAX=$(wc -l $CONTENT \| sort -n \| tail -2 \| head -1 \| awk '{print $1}')`<br>① `FILES > 5 && MAX < 800` → ⚠️ 告警「碎片化风险」，提示合并相近模块；② 碎片判据（单册是否过小）**以 SKILL 的 `quality-review-checklist.md` 为准、由 QR 子 Agent 语义核验**——定义：内容子文档 **<150 行【且】<6KB**（⛔ 是「且」不是「或」：写成「或」会把 120 行 / 9KB 的紧凑表格册误判为碎片）。⚠️ **`dev-logic-architect` 的 `check_doc_split.py` 不含碎片检测**（ULE / DEP 的同名脚本才有），故本项**无机器门**、只走 QR；命令端不另立行数阈值、不据此硬停；③ 无碎片且 `FILES ≤ 5` → ✅ 通过 |
| **必有索引** | **一律生成 `00_索引.md`**（列出所有设计文档的标题/范围/对应 Sprint + 推荐阅读顺序 + 各文件生成时间 + 主/补充标识），各专题主文档编号为 `01_`~`98_`；**即便只产 1 份专题主文档也生成索引**（`00_索引.md` + `01_<专题>.md`），不再有"单份态无索引"|

> skill 内置「接口路径简洁 / 字段宽容（默认可空；**索引列强制 NOT NULL + DEFAULT 哨兵值**，见核心原则 8 强制例外）/ PRD 内容分层取舍」等核心原则（单一信源见 `dev-logic-architect` SKILL.md）——命令不复述、不重复要求（约定 21）。

> ⚠️ **优先级冲突时的裁决**：当 skill 默认与 Step 0.6 采集到的「事实清单」冲突时（例如 skill 倾向简洁路径但代码 `application.yml` 已有 `context-path: /xxx/server` + `@RequestMapping("/api/v1/...")`），**以事实清单为准**——除非「⚠️ 本次变更」表明本 Sprint 主动改路径。命令端在 Step 1.5 落盘前做一次自动回检（见 Step 1.6）。

#### Step 1.5.1：★ 事实清单编号归一

Step 1.5 落盘后，若详设目录进入**拆分编号模式**（已生成 `00_索引.md`），命令端必须把「代码事实基线」`事实清单.md` 归一到固定保留位 `98_事实清单.md`（紧挨 `99_待澄清问题清单.md` 前），避免在已编号目录里出现裸文件名（违反约定 15）：

```bash
DETAIL=docs/design/detail/{version}
if [ -f "$DETAIL/00_索引.md" ] && [ -f "$DETAIL/事实清单.md" ] && [ ! -e "$DETAIL/98_事实清单.md" ]; then
  git mv "$DETAIL/事实清单.md" "$DETAIL/98_事实清单.md"
  echo "✅ 事实清单已归一为 98_事实清单.md（拆分目录保留位）"
fi
# 单文件模式（无 00_索引.md）保持 事实清单.md 不加前缀，与约定 15「单文件不加前缀」一致
```

> ★ **`00_索引.md` 必须把 `98_事实清单.md` 列为「代码事实基线」条目**（标明它是 application.yml / 路由 / 跨项目接口的真值来源，设计以此为准）。
> ★ 下游消费者（`version` / `sprint-bugfix` / `sprint-test` / `sprint-dev` / 本命令 Step 1.6 回检）一律用 glob `*事实清单.md` 定位，兼容单文件 `事实清单.md` 与拆分 `98_事实清单.md` 两种形态。


### Step 1.6–1.8：★ 落盘后回检 — 统一派独立子 Agent 执行（Step 1.6 / 1.6.5 / 1.7 / 1.7.5 / 1.8 + SKILL 脚本复核）

> ⚠️ 关键规则：Step 1.6~1.7.5 静态核验 + SKILL 脚本复核全部并入**一个 general-purpose 子 Agent 统一执行**（隔离上下文、不占主对话）；子 Agent 回传任一**阻塞项** → 暂停后续 Step 2~6 等用户裁决；子 Agent 失效 → 命令端内联兜底跑同一组清单 + 脚本，**禁止静默放过**。

| 检查 | 触发 | 骨架 |
|------|------|------|
| SKILL 脚本复核 | 恒跑 | 按 `dev-logic-architect/references/flow-qr-dispatch.md` 落盘后硬核回检原样跑（触发条件 / 判级 / 须读 `--json` 的等级以 SKILL 为单一信源）+ 需代码根 / PRD 的补跑组（report-only）|
| Step 1.6 | 无条件 | 路径事实回检（base 强约束 / endpoint 弱约束；base 不匹配暂停）|
| Step 1.6.5 | 事实清单「⚠️ 本次变更」涉 base | 消费者级联校验（git diff 对账，未联动 P0 暂停）|
| Step 1.7 | HAS_OPEN_API=true | 对外开放接口 9 项规范回检（2/4/6 项不过必暂停）|
| Step 1.7.5 | HAS_THIRD_PARTY_DEP=true | 第三方职责边界 5 项回检（越俎代庖必暂停）|
| Step 1.8 | 无条件 | 上游溯源完整性 4 项（NN_ 前缀不过必暂停）|

**进入本段第一动作 = Read `{{AIDP_HOME}}/flows/sprint-design/step-1.6-落盘后回检.md`**（Step 1.6 / 1.6.5 + 派单方式 + SKILL 脚本复核 + 补跑组），**接着 Read `step-1.7-对外接口与溯源回检.md`**（Step 1.7 / 1.7.5 / 1.8，条件触发；由**同一个**子 Agent 一并执行、不另派）。逐项执行，绝不凭骨架或记忆略过子步骤。


### Step 2–4：Architect Agent 补充 + 生成 SQL 脚本 + 动态更新 docs/architecture/

> 📎 **子步锚点说明**：Step 2 / 3.0 / 3.1 / 3.2 / 4.1–4.3 **合并在本标题下、不各设独立标题**——本文档（及 `/version` 各 `planning-N.md`）正文里出现的 `Step 3.0`（前版 SQL 风格提取）、`Step 3.2`（SQL 两阶段落位）等引用，即指下方骨架表对应行 + 其 flow 分片内的同名子步，**不是缺失的标题**。

> ⚠️ 关键规则：Step 2 检查数据库基线/架构文档三态 + 注入「关联文档」表；Step 3 沿用历史 SQL 风格（不复制前版 SQL）+ **两阶段落位**（SKILL 暂存 `code/sql/v*` → 命令端 `git mv` 归位 `docs/deployment/{version}/sql/增量/`、文件头版本==目录版本==迭代版本三者一致）；Step 4 architecture 三份文档按三态反填/增量，且**保留 Step 0.5.5「运行时端点契约」段不覆盖**。

| Step | 骨架 |
|------|------|
| 2 | 数据库基线对比 + 架构文档全目录识别与约束三态判定 + 公共组件 + ADR + 关联文档表（共享模板 + 按类型微调）|
| 3.0 | 历史 SQL 风格归纳（`check_sql_style_consistency.py --history-only`，口径以 SKILL 核心原则 12 为准）|
| 3.1 | 生成本版 SQL（只写本版新增/变更、`NN_` 从 01 起、⛔ 不复制前版 + 风格统一 + DDL 幂等）|
| 3.2 | SQL 两阶段落位 + 版本落位一致性防护（双模式扫描 git mv 归位 + 文件头版本校正 + 设计引用回写）|
| 4.1/4.2/4.3 | 更新 技术选型.md / 架构约束.md / systemPatterns.md（有架构设计则优先据其派生约束）|

**进入本段第一动作 = 按序 Read 以下 2 个分片**，逐项执行、绝不凭骨架或记忆略过子步骤：
- `{{AIDP_HOME}}/flows/sprint-design/step-2to4-架构补充与SQL-1.md`（Step 2 Architect Agent 补充）
- `{{AIDP_HOME}}/flows/sprint-design/step-2to4-架构补充与SQL-2.md`（Step 3 生成 SQL 脚本 + Step 4 动态更新 docs/architecture/）

### Step 5：UI Agent 生成 UI 规范 + 原型内容基线 + 设计令牌（如有原型）

如果 `docs/prototype/{version}/code/` 存在原型代码，读取 `{{AIDP_HOME}}/agents/ui.md` 获取 UI Agent 角色定义，跑其流程 A（**Step 0~4**——Step 0 是约定 4 情形 C/D 用户确认门的唯一触发点，不可跳）。

#### Step 5.0：★ 原型内容基线 + 设计令牌两份规划期强制产出物（有原型必产，约定 4）

> ⏱️ **产出时机在 Step 0.7（早于 Step 1）**，本节是这两份产物的**规则单一信源**；到 Step 5 时若 Step 0.7 已产出，本节只做**回填校正**（原型期间有更新则刷新对应条目 + 重刷 `00_索引.md` 生成时间），不重复生成。

> 堵"规划期从原型转写时漏清点原型元素 → 设计本身就不全 → 开发系统性漏内容"的根因（下游反馈）。

- **`docs/design/detail/{version}/NN_原型内容基线.md`**（UI Agent 流程 A **Step 1.5**；**属详细设计目录，遵约定 14/15**——`NN` 实际续编序号、命令端归一时续编现存最大序号分配、**不写死**〔设计三态占 01-03 语义位，基线续编其后、典型 `04_`〕、实际序号见 `00_索引.md`）：逐页穷举原型全部可见元素与交互态 **+ 操作逻辑/交互流**（约定 4「对齐原型三层」的内容层 + 操作逻辑层）→ 每项标处置（`实现`默认〔行为照原型〕/ `裁剪`〔三件套留痕+产品确认〕/ `延期` / `改为 X`〔说明差异+确认〕）；消费原型 `DESIGN-MANIFEST.json`/`DESIGN-HANDOFF.md`（含 `flows`/`requiredStates`，若存在）。**这是研发需求/详细设计转写的全覆盖依据**——Step 1 调 `dev-logic-architect` 时**显式作为上下文传入**，要求详设/接口/数据库覆盖到该基线每个"实现"项的**字段、状态与操作逻辑级**（命令端只传上下文、不复述 SKILL 规则，约定 21）。
- **`docs/design/detail/{version}/NN_设计令牌.md`** + 全局主题文件（UI Agent 流程 A **Step 4**，情形 B/C；`NN_设计令牌.md` 属详细设计目录、`NN` 续编分配**不写死**、实际序号见 `00_索引.md`；主题文件属前端代码资产不进本目录）：见 Step 0.5.5 / 约定 4「设计令牌提取铁律」。
- **★ 归位详细设计 `00_索引.md`（强制留痕，约定 15）**：`原型内容基线.md` / `设计令牌.md` 是**详细设计目录 `docs/design/detail/{version}/` 的内容主文档**，命令端在调 UI Agent / `dev-logic-architect` 后**归一/维护该目录 `00_索引.md`**——**按约定 15 续编该目录现存最大序号给它们分配 `NN_` 前缀（不写死，典型 04/05）**，写入文件清单（含**生成时间** + **主标识** + 一句话范围〔标注"规划基线/前置输入"〕），并在**研发需求 `00_索引.md`** 的「关联/上游输入」段**交叉引用**它们（作开发与验收的强制上游输入）。
- **决策门显式化**：规划期若要对某原型板块/字段取舍 → `AskUserQuestion` 让用户显式选，**默认项恒为"实现"**，严禁命令端自行判"不做"（约定 4 规划期铁律）。
- **回检**：`version-auditor` F「原型覆盖度」以本基线为准审计（Critical 硬门，见 Step 2.4.7 / `version-auditor.md` F 段）——原型有、需求/设计无、未标裁剪 → 阻塞落盘。

#### Step 5.1：★ 动态更新 UI规范约束.md

UI Agent 从原型代码 + `docs/prototype/{version}/mockup/`（如有）中提取视觉规范（品牌色/字体/间距/组件样式/布局/响应式断点），追加到 `docs/architecture/UI规范约束.md` 对应章节（首次填充，后续增量）。

#### Step 5.2：生成 Sprint UI 规范

输出到 `docs/architecture/UI规范约束.md`（追加「组件映射清单」章节，与 Step 5.1 同一权威 UI 规范文档；UI 规范统一落 `docs/architecture/`）：
- 组件映射清单
- 如 `docs/prototype/{version}/mockup/` 无人工高保真图片，执行 UI Agent 流程 C 自动生成

### Step 6：更新 memory/techContext.md（技术上下文）

读取本次生成的详细设计文档和 `docs/architecture/技术选型.md`，按以下要点更新 `memory/techContext.md`（Claude 的技术记忆，帮助理解项目技术实现细节）：

**更新内容**： ① 项目代码结构（前后端位置 / 框架 / 构建工具 / 端口 / context-path）； ② 运行环境要求（JDK / Node.js / Maven / 数据库版本）； ③ 快速启动命令； ④ 环境变量说明； ⑤ 外部服务依赖（统一认证 / OSS / 第三方等）。

**更新逻辑**： 初始模板（含"示例占位"标记）→ 完整填充； 已有内容 → 增量追加新技术栈/依赖； 「变更历史」表追加一行记录本次更新。

详细模板结构参考 `memory/techContext.md` 自身的章节骨架。


### Step 6.5：★ 对外开放接口 OpenAPI 文档化（可选）

> ⚠️ 关键规则：**本地 `对外开放接口.md` 始终为权威版本**，`docs/design/detail/{version}/openapi.yaml`（OpenAPI 3.0.3）是由它派生的机读副本、随仓库入库；源 MD 的 SHA256 记在 `info.x-aidp-source`。状态判定（副本存在性 × 错误标记）后，首次生成 / 增量重新生成均**派子 Agent** 执行，失败写 `.aidp-openapi-sync-error.json` 让下次拦截。补充模式（`--supplement`）默认 skip 本 Step。

| 子步骤 | 骨架 |
|--------|------|
| 6.5.1 | 状态判定表（D 残留错误暂停 / B 首次 / C 增量）|
| 6.5.2–6.5.3 | 状态 B 首次：询问 + 派子 Agent 由 MD 生成 `openapi.yaml`（含完整派单 prompt 模板）|
| 6.5.4 | `openapi.yaml` 结构契约 + SHA256 算法（DRY 单一来源，派单 prompt 嵌入素材）|
| 6.5.5–6.5.6 | 状态 C 增量：主 Claude 自检源 MD SHA256 变化 → 询问 + 派子 Agent 覆盖式重新生成 |

**进入本段第一动作 = Read `{{AIDP_HOME}}/flows/sprint-design/step-6.5-对外接口在线化.md`**，逐项执行、绝不凭骨架或记忆略过子步骤。

### Step 7：更新状态

更新 `memory/{version}/{user}/activeContext.md`：
- 记录设计文档已生成
- 当前工作焦点：设计已完成，等待研发执行计划或开发


## ★ 输出前硬门：回检清单 + 三合一回写校验（不可跳过）

> 🛑 关键规则：跑完 Step 2~6 后**必须在此暂停** —— 先跑「A 回检清单」bash 块逐行填「🔍 输出前回检」表（11 项），再跑「B 三合一回写校验」脚本（基线 + ADR + 金额字段），**B 块退出码必须为 `0` 且看到 `✅ 基线 + ADR + 金额字段 三合一回写校验通过` 字样**才算完成；任一 Fail → 输出"❌ 回检未通过：缺失项 …"停下请用户裁决，禁用"基本通过""主要项通过"等模糊措辞绕过。**跳过本硬门 = 严重违规**。

| 段 | 骨架 |
|----|------|
| A 回检清单 | 11 项判定表（文件数+NN_前缀 / 拆分数量 / L1 头部 / 对外接口 / 第三方边界 / 字典枚举 / ER·FK·NOT NULL / 文本长度 / 待澄清清单 / L2·L3 溯源覆盖率 / 金额整数化）+ 逐项「🔍 输出前回检」输出格式 |
| B 三合一脚本 | 数据库基线回写 + ADR 回写 + 金额字段整数化（调 `check_money_field.py`）三段 bash，`exit 1` 即不允许标完成、须补写重跑到 0 |

**进入本段第一动作 = Read `{{AIDP_HOME}}/flows/sprint-design/step-输出前硬门.md`**，用 Bash 工具真实执行两个 bash 块、逐行填表，绝不凭骨架或记忆略过。

## 输出

```
✅ /sprint-design 完成（{version}）

📋 生成的文件：
- docs/design/detail/{version}/*详细设计.md（含公共组件清单；glob 兼容 `01_` 前缀名与历史裸名）
- docs/design/detail/{version}/*接口设计.md（**仅内部接口**；glob 兼容 `03_` 前缀名与历史裸名）
- docs/design/detail/{version}/对外开放接口.md（★ HAS_OPEN_API=true 必出 — 免登录 / 独立 base / 9 项规范回检；★ **本地始终为权威**）
- docs/design/detail/{version}/openapi.yaml（★ Step 6.5 选择生成时产出 — 由对外开放接口.md 派生的 OpenAPI 3.0.3 机读副本，`info.x-aidp-source` 记源 MD SHA256；后续 /sprint-design 自动检测 MD 变化并询问是否重新生成）
- docs/design/detail/{version}/*数据库设计.md（glob 兼容 `02_` 前缀名与历史裸名）
- docs/design/detail/{version}/*事实清单.md（★ 如 `code/` 下已有后端/前端 — 从 application.yml / vite.config / nginx.conf 等真实配置提取的端口/context-path/proxy 清单，设计文档以此为准；HAS_OPEN_API=true 时额外含「对外开放接口 base」表）
- docs/deployment/{version}/sql/增量/{NN}_<中文名>.sql（中文命名 + 两位数字序号前缀；DDL/DML 同一序号空间按执行顺序混排；`99_回滚脚本.sql` 序号保留；详细规则见 `dev-logic-architect` SKILL.md Module D 章节）
- docs/prototype/{version}/mockup/（★ 如自动生成高保真原型）

★ 拆分规则（约定 15）：上述各份默认为单文件；当内容超出建议阈值（详细设计 >10 模块 / 接口设计 >50 接口 / 数据库设计 >30 表）时，按业务模块或服务拆分为
  `01_xxx.md` / `02_xxx.md` / ...，并生成 `00_索引.md` 列出所有分册。详见
  `docs/init/02_迭代输入指导.md §10.4`。下游命令（sprint-dev / sprint-test）
  通过 glob `docs/.../{version}/0?_*.md` 读取全部分册。

★ **对外接口独立规则**（与 约定 15 正交）：当 `HAS_OPEN_API=true` 时，**无论接口数量多少**，对外接口都必须独立为 `对外开放接口.md`（或拆分后的 `0N_<对外域>.md` 分册），**禁止**塞回 `接口设计.md`。这是 `dev-logic-architect` skill 的强制规范，由 Step 1.7 回检。

🔄 已更新：
- memory/{version}/{user}/activeContext.md
- memory/systemPatterns.md（如有新 ADR，项目级）
- memory/databaseBaseline.md（★ 追加新增表）
- memory/techContext.md（★ 填充技术实现细节，项目级）

📌 下一步：
/sprint-plan → 生成研发执行计划
```

---

## 补充模式（`--supplement={NN}`）

当版本开发中途产品更新了 PRD **或原型**且需求侧已经产出研发需求增量（`NN_<业务主题>.md`，文件名不带"补充"字眼、补充身份记入 `00_索引.md`）时，由 `/version` 调用本命令并传入 `--supplement={NN}`。**fresh 模式（无此参数）保持原流程不变**。


### ★ 约定 22 级联落盘（`--ledger-cascade`，与 `--supplement={NN}` 互斥，同时传则报错）

由**约定 22 级联**调用时（攒批收口子 Agent / `--cascade-now` 即时级联）**必须**加 `--ledger-cascade`：**就地改内容主文档正文** `docs/design/detail/{version}/` 的 `01_详细设计.md`·`02_数据库设计.md`·`03_接口设计.md`（按实际范围），改完刷该目录 `00_索引.md` 生成时间（约定 15）。
⛔ 不新建 `NN_` 分册、不产中转增量册、不全量扫 `code/` 等落盘细则与内容产出方式，**单一信源 = `{{AIDP_HOME}}/reference/开发期族增量.md`「收口执行要点」第 2/3 条（L2 设计）**，本命令不复述。

### 输入差异
- **必读** `docs/requirements/{version}/研发需求/输入变更-{NN}.md`（含 PRD 与原型两类变更）
- **必读** 本轮研发需求增量 `docs/requirements/{version}/研发需求/NN_<业务主题>.md`（研发需求增量，文件名不带"补充"字眼）
- **必读** 原主文档：`01_详细设计.md` / `02_数据库设计.md` / `03_接口设计.md`（历史存量并列态裸名 `详细设计.md` / `数据库设计.md` / `接口设计.md` 兼容；基线，只读）
- **必读** `*事实清单.md`（如存在 — 含「路径消费者点」表 + 反模式提示）
- **必读**（如有原型变更）当前 `docs/prototype/{version}/code/` 与 `mockup/`，让 dev-logic-architect 重新对齐"公共组件清单 / 模块结构 / 页面流转"
- **传给 skill 的 prompt 必须显式说明**：「本次仅针对 PRD / 原型变更涉及的设计点产出增量；接口/表/字段未变的部分不重复；新增/变更条目标注对应的输入变更摘要小节 + 研发需求补充小节」

### 输出差异（按本轮实际是否有变更落盘对应文件）

★ **命名保持**：上游 dev-logic-architect SKILL 内部按"SKILL 默认产物路径"风格生成（SKILL 已禁"补充/追加"语义前缀，新风格输出纯 `NN_业务名.md`）；命令端在 SKILL 返回后**只做序号续编校正**（若 NN 与目录现存最大序号冲突则 `git mv` 归一到 `MAX+1`），**绝不回补"补充"字眼**（具体脚本见 `{{AIDP_HOME}}/flows/version/planning-4.md`（`version.md` Step 2.4.4 现仅是一行指针），本命令单独被调用时也跑同段脚本兜底）：

| 文档类型 | SKILL 默认产物路径（待归一） | 归一后路径（统一 `NN_<业务主题>.md`，文件名不带"补充"字眼） |
|---------|----------------------------|--------------------------|
| 详细设计 | `NN_业务名.md`（SKILL 现行新风格；旧 `详细设计-补充-{NN}.md` 仅历史残留兼容识别）| `docs/design/detail/{version}/NN_<业务主题>.md`（续编本目录最大序号 +1；多文件+前缀如 `01_详细设计.md`~`04_OPS对接接口清单.md` → `05_货币元积分.md`） |
| 接口设计 | `NN_业务名.md`（旧 `接口设计-补充-{NN}.md` 仅历史兼容）| 同上（与详细设计同目录，按序号连续续编） |
| 对外开放接口 | `NN_业务名.md`（如本轮有变；仅走 Step 1.7 对外接口规范回检；旧 `对外开放接口-补充-{NN}.md` 仅历史兼容）| 同上 |
| 数据库设计 | `NN_业务名.md`（如表/字段有变；旧 `数据库设计-补充-{NN}.md` 仅历史兼容）| 同上 |
| DDL SQL | `docs/deployment/{version}/sql/增量/{NN}_<中文名>.sql` | 单文件保留；遵循 Step 3.0 风格 + SKILL 命名规范；序号续当前最大 +1（SQL 不加"补充"关键字） |

- **业务主题**：① 用户调 `/sprint-design {version} --supplement={NN} "<主题>"` 显式传；② 从研发需求增量文档（路径如 `docs/requirements/{version}/研发需求/08_<主题>.md`）的文件名/头部解析；③ 兜底 `增量NN{NN}`
- 多文件+前缀场景：在归一后的增量文档头部第一段加「本补充信息」段：`> 共享编号 NN={NN} | 本目录续编序号 {NEXT} | 业务主题：{TOPIC}`
- 在目录 `00_索引.md` 登记该增量行（类型=补充 + 生成时间，**用归一后的真实路径**）

### 事实清单联动（重要）
- 如 base / context-path / 端口 / proxy 有变 → 更新事实清单的「⚠️ 本次变更」表 + 「已联动消费者点」列
- 触发 Step 1.6 路径回检（base 强约束）与 Step 1.6.5 消费者级联校验（git diff 与消费者点表对账，未联动列为 P0 告警暂停）
