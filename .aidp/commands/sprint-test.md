# /sprint-test — 测试阶段（含验收循环）

你正在执行 `/sprint-test` 命令，为当前 Sprint 执行测试和验收检查。

**★ 本命令是 skill 编排器**：核心调用 `code-verification-loop` skill（**仅验收模式 `mode=verify-only`**：开发已由 `/sprint-dev` 完成，本命令只验收、不修复，问题清单交 `/sprint-bugfix`）和 `superpowers:verification-before-completion`（完成前验证）；并按需经 `/sprint-selftest`（用例缺失时补齐研发自测，唯一入口）/ `api-tester`（后端接口测试，可选）。

参数：$ARGUMENTS（可选，Sprint 编号。如省略，从 activeContext 中读取当前 Sprint）

| 参数 | 作用 |
|------|------|
| `--unattended` | **无人值守上下文标记**（`/sprint-full` 逐层透传而来）：① 本命令自身任何决策门**不弹 `AskUserQuestion`**；② **必须向下透传**给 `/sprint-selftest` 与 `/sprint-bugfix`——`/sprint-selftest` 内部的 `dev-manual-testcase` SKILL 有「生成用例前必须主动询问方案 8 项 + 5 组连接信息」的强制第零步，不透传即在此挂死；③ **派 `code-verification-loop` 验收子 Agent 时把无人值守上下文写进 prompt**（需要人工裁决的节点记录结论 + 标注待人工确认后返回）|
| `--from-batch` | 批量子任务标志（由 `/sprint-full` 透传）：本命令不弹 `AskUserQuestion`，内容决策门按「⏸ 待裁决」返回上层（语义单一信源 = `/sprint-full` 参数表） |

## 前置流程

**VCS 能力分流**：从 `{{AIDP_HOME}}/scripts/vcs.py` 的 `detect_mode(Path.cwd())` 读取 `vcs_mode=git|none`，用 `developer_identity(Path.cwd())` 取得 `{user}`；向 `code-verification-loop` 验收子 Agent 透传模式。`vcs_mode=none` 时继续本地用例、代码静态检查与验收，Git-only diff/commit/push/CICD 检查逐项记 `unsupported:vcs-disabled`（不是 passed，也不折算为全绿）；不能用 Git 差异判定测试范围时以 Sprint 计划与 `activeContext.md` 的本地文件清单为依据。Git 模式保持原有验收语义。

按 `docs/init/06_版本与用户目录约定.md`：
1. **{version}** ← 项目记忆文件（路径经 `python3 {{AIDP_HOME}}/scripts/agent_env.py memory-file` 取：`AGENTS.md`，只用 Claude Code 时为 `CLAUDE.md`）「当前状态.当前版本」
2. **{user}** ← `git config user.name`
3. **{NNN}** ← 从参数或 activeContext 读取

## 前置检查

1. 读取 `memory/{version}/{user}/activeContext.md` 获取当前 Sprint 编号和范围
2. 确认需求文档存在：`ls docs/requirements/{version}/研发需求/{01_研发需求,00_索引,00_研发需求}.md 2>/dev/null` 任一命中即可（**不硬编码裸名**——multi 模式按系统拆分时 `01_研发需求.md` 本就不存在，硬判会把合规项目误判缺失而错误停止）
3. 确认设计文档存在：`docs/design/detail/{version}/`（glob 加载 `01_详细设计.md`/`02_数据库设计.md`/`03_接口设计.md`，历史裸名 `接口设计.md` 兼容）
4. 确认代码已实现（前端校验（lint + 类型检查，不打包）：Step 2 派出的 `code-verification-loop` **维度 0 静态基线门**已作前置门跑过一次；**后端编译不在维度 0 内**〔理由见 Step 7〕，仅在本命令 Step 7 收敛，且仅本 Sprint 改动侧 + 资源受限）

## 执行步骤

### Step 1：QA Agent 补全 Sprint 范围 + 接口/性能/兼容性用例

读取 `{{AIDP_HOME}}/agents/qa.md` 获取角色定义。

**前置：先 Read 已生成的用例（测试人员为主 + 研发自测查漏补充）**

**★ 用例来源优先级解析**（与 `/sprint-aiauto-test` Phase 2.0 同一套铁律）：

```bash
V="docs/testing/{version}"

# A. 测试人员提供的用例：正式用例/ 下排除环境配置与待澄清清单
TEST_TEAM_CASES=$(find "$V/正式用例" "$V/测试验收" "$V/测试执行" -maxdepth 1 -name "*.md" \
  -not -name "_*" \
  -not -name "01_测试环境与账号.md" \
  -not -name "00*" \
  -not -name "99*" \
  -not -name "README.md" 2>/dev/null | sort)
# ⛔ `00*` 必须排除（索引不是用例）：目录只剩 00_索引.md 时会被判「用例存在」→ SOURCE_MODE
#    误落「测试人员为主」，有内容的研发自测用例反被降级成补集。口径同 phase-2-1.md / step-6.md。

# B. 研发自测用例：研发自测/ 子目录或单文件
DEV_CASES=$(find "$V/研发自测" -maxdepth 2 -name "*.md" -not -name "_*" -not -name "99_*" -not -name "01_测试环境与账号.md" -not -name "01_研发自测方案.md" -not -name "00_研发自测方案.md" -not -name "00_索引.md" -not -name "README.md" 2>/dev/null | sort)
[ -z "$DEV_CASES" ] && [ -f "$V/研发自测.md" ] && DEV_CASES="$V/研发自测.md"

if [ -n "$TEST_TEAM_CASES" ]; then
  PRIMARY="$TEST_TEAM_CASES"; SUPPLEMENT="$DEV_CASES"
  SOURCE_MODE="测试人员为主 + 研发自测查漏补充"
elif [ -n "$DEV_CASES" ]; then
  PRIMARY="$DEV_CASES"; SUPPLEMENT=""
  SOURCE_MODE="研发自测兜底"
else
  PRIMARY=""; SUPPLEMENT=""
  SOURCE_MODE="两类用例均缺失"
fi
```

> 本步骤 **不重新设计**已有用例，仅做两件事（Sprint 范围裁切 + 补充 dev-manual-testcase 不写的维度）。

**★ 用例缺失时不中断**：

```bash
if [ -z "$PRIMARY" ]; then
  echo "⚠️ 正式用例/ 和 研发自测/ 均无用例"
  echo "→ 当前命令经 /sprint-selftest 补齐研发自测方案 + 自测用例（不中断 /sprint-test 流程）"
  # Claude 直接调用命令 /sprint-selftest {version}（研发自测唯一入口）：其内部调 dev-manual-testcase 生成
  #   + 落盘核验 + 目录归一 + 测试环境与账号，命令端不自行重复归一/传占位符逻辑（单一信源，约定 21）
fi
```

**Claude 行动指引**：若上述 if 命中，**立即在当前 sprint-test 会话中调用命令 `/sprint-selftest {version} [--unattended]`**（研发自测唯一入口；⛔ 本命令带 `--unattended` 时**必须透传**，否则 SKILL 的强制询问第零步会在无人可答处挂死）补齐用例，然后继续 Step 1 之后的"Sprint 范围裁切 + 补充用例维度"流程；**不要**让用户去单独跑 `/version`。

**1. Sprint 范围裁切**：从 `研发自测/` 下用例文档中**抽取**本 Sprint（按 `01_研发执行计划.md` 中 Sprint-{NNN} 行的功能范围）涉及的测试套件，汇总到 `sprint-{NNN}-testcases.md` 的「人工自测套件清单」段（仅链接 + 序号，不复制正文）

**2. 补充 dev-manual-testcase 不写的用例维度**：人工自测（界面操作）+ 业务层边界值由 `dev-manual-testcase` 产出（覆盖范围以该 SKILL 为准），**本步不重复**，仅补它不写的以下维度——

| QA Agent 在 testcases.md 补充的维度 | 说明 |
|------|------|
| 接口契约用例 | curl / 请求体 / 响应断言 |
| 对外开放接口安全用例 | 见下方 5 项（`*对外开放接口.md` 存在则必补；⛔ glob 匹配，新项目产 `04_` 前缀）|
| 性能 / 并发 / 限流 | 阈值与降级行为 |
| 浏览器兼容 / 响应式布局 | 多分辨率 / 多浏览器 |
| 边界值 / 异常输入（接口层） | HTTP 状态码 / 错误码（业务层边界已由 dev-manual-testcase 覆盖）|

**对外开放接口安全用例**（`ls docs/design/detail/{version}/*对外开放接口.md 2>/dev/null` 有命中则**必须补**；⛔ **必须 glob、不得只认裸名**——`/sprint-design` 已规定新生成一律 `NN_` 前缀（如 `04_对外开放接口.md`），只判裸名会让**所有新项目**判「不存在」→ 免登录/限流/幂等/重放/审计 5 项安全用例静默不补，失效方向是全绿）：
①免登录路径下未带 Session/Cookie 调用应成功；②超限流 100 QPS 返回 429；③写操作幂等键重复请求返回首次结果；④认证版本（如有）签名错误/时间戳过期/Nonce 重放各对应错误码；⑤审计日志写入校验。**本地 MD 始终为权威**（`openapi.yaml` 仅为其派生副本）。

**测试 URL 构造规则**：`docs/design/detail/{version}/*事实清单.md`（如存在）— 测试 URL **以"事实清单 base + 接口设计 endpoint"拼接**（接口设计已在 /sprint-design Step 1.6 与事实清单对齐）；对外接口用 base = 事实清单「对外开放接口 base」表的值

**输入**：
- `docs/requirements/{version}/研发需求/` — 验收标准溯源
- `docs/design/detail/{version}/03_接口设计.md`（历史裸名 `接口设计.md` 兼容）+ `*对外开放接口.md`（如存在）— 接口契约
- `docs/design/detail/{version}/*事实清单.md`（如存在）— base 拼接
- `docs/plans/{version}/01_研发执行计划.md` — Sprint 范围

**输出**：`docs/testing/{version}/sprint-{NNN}/sprint-{NNN}-testcases.md`（仅含接口/性能/兼容性/对外安全 4 类补充用例 + 人工自测套件清单的链接索引）

### Step 2：调用 code-verification-loop skill（★ 核心）

> ★ **WebMCP 条件启用入参**（默认不传；绝大多数项目无此段）：`code-verification-loop` 的**维度 9（WebMCP 前端能力实现合规）**是**入参门控**、
> 且 SKILL 明令**不自行探测是否启用**——**命令端不传 = 该维度永不启用**，启用了该能力的项目会
> 静默漏掉这一层质量门。故调 SKILL 前先取判定（启用判定的唯一实现，⛔ 不要自己 grep PRD）：
>
> ```bash
> python3 {{AIDP_HOME}}/scripts/check_webmcp.py --detect --json    # → enabled / entry_symbols
> ```
>
> ★ **临时 Mock 协议入参（`--third-party-mode`，同属入参门控，⛔ 别漏）**：维度 2A 的
> `scan_mock_data.py` 默认对**一切 mock 零容忍**；只有加上 `--third-party-mode`，带
> `THIRD_PARTY_MOCK` **或 `DEV_MOCK`** 标注块的代码才会从 2A 豁免、转交维度 2B 做协议核验。
>
> **⛔ 漏传的失效方向是【假红】**：合规写法（按 `dev-execution-planner` 情况 1 写的 dev 拦截器 /
> MSW）会被 2A 判 Critical + exit 1，而作者**无从修**——照报错去掉守卫就等于把 dev mock 打进生产包。
> 实测：同一份合规 `DEV_MOCK` 文件，不带旗标 1 命中、带旗标 0 命中。
>
> **何时传**：项目存在**第三方平台接口对接**，**或**前端用了 `DEV_MOCK` 拦截 —— 两者任一即传。
> 判定不必猜，扫一眼就有答案：
>
> ```bash
> grep -rlE 'THIRD_PARTY_MOCK|DEV_MOCK' code/ 2>/dev/null | head -1   # 有输出即需要传
> ```
>
> ⚠️ **豁免要"买"得到**：只有**字段完整**的标注块才享受 2A 豁免（`THIRD_PARTY_MOCK` 六字段 /
> `DEV_MOCK` 三字段 `since`·`owner`·`REMOVE_WHEN`）；缺字段由 2B 判 Critical，⛔ 不存在
> "写个裸标记就能关掉 2A"这条后门。判据与字段集以 `code-verification-loop` SKILL 为单一信源，本处不复制。

> `enabled: true` → 随 prompt 传 `webmcp_enabled: true` + `webmcp_entry_symbols: <脚本返回的数组原样>`
> （⚠️ 后者**不可省略也不可写死**：挂载位置已迁移过一次、规范仍在演进，上游缺该入参会直接报错而非猜默认值）；
> `enabled: false` → **什么都不传**，不提、不留位置。


> ★ **独立子 Agent 派发（隔离上下文，不占 /sprint-test 主对话）**：`code-verification-loop` SKILL 已声明「作为更大编排流程的一环被调用时，应把**整个验收循环**作为一个独立子 Agent 派发」——其扫描脚本（`scan_mock_data.py` / `scan_third_party_mock_antipatterns.py` 等）+ 多维度核验都在验收子 Agent 自身上下文内跑，主流程**只接收精简结构化报告**（各维度 Pass/Fail + 阻塞项 file:line + 修复建议），脚本 stdout 不污染主上下文。因此本步**不在主对话直接用 `Skill` 工具调**，而是用 `Agent` 工具派一个子 Agent，prompt 为「用 Skill 工具调 `code-verification-loop`，**把下方『调用参数』与『额外提示』两段的全部内容逐项传全**，跑完只回传精简验收结论」。⛔ **别把模板句写成「传入代码/设计/接口路径」**：那会漏掉同步骤要求的 `--third-party-mode` 门控旗标、`webmcp_enabled`/`webmcp_entry_symbols`、被测项目根、被验收版本号——漏传的失效方向全是「维度静默落不适用」或「合规代码被判假红」，而不是报错。与 `/sprint-design` Step 1.6 子 Agent 派发同款。

> ⛔ **`--unattended` / `--from-batch` 时 prompt 显式带上非交互上下文**（「任何需要用户裁决的节点一律不询问：记录结论 + 标注待人工确认后返回」）——子 Agent 里无人可答，主流程只会看到「子 Agent 未返回」。

派发的子 Agent 内部以 `Skill` 工具调用 `code-verification-loop`。**skill 内置多维度独立 Agent 检查 + 分级处理（级别以 SKILL 为单一信源）+ 每轮留痕**；命令端按约定 21 不复述维度内容与级别名，只负责传入参数 + 接收验收报告。维度索引见 `{{AIDP_HOME}}/skills/code-verification-loop/SKILL.md`，各维度细则见其 `references/dimension-*.md`，第三方 mock 协议见 `references/third-party-mock-protocol.md`（SKILL 单一信源）。

> 开发期更早的"复杂度+复用"自检由 Frontend Agent Step 4.5 / Backend Agent Step 7.5 承担（作为更早的自检关口，不取代 SKILL 兜底）。

**调用参数**（按 SKILL 输入要求传入）：
- **运行模式**：`mode=verify-only`——并在任务描述里写明「代码已由 `/sprint-dev` 完成（跳过 Step 1 开发）；只验收、不修复，问题清单交 `/sprint-bugfix`」。⛔ 不传即 SKILL 默认 `loop`：会重跑开发（Step 1）并自带最多 5 轮修复，与本命令 → `/sprint-bugfix` 的修复路径重叠（`/sprint-full` 外层还有一层 bugfix 循环）
- **代码路径**：`code/`（按本项目实际单/多前后端组织取根目录或子项目目录）
- **设计文档路径**：`docs/design/detail/{version}/`（含本目录下全部分册）
- **接口文档路径**：`docs/design/detail/{version}/03_接口设计.md`（历史裸名 `接口设计.md` 兼容）；如做了拆分则传 `docs/design/detail/{version}/` 让 skill 按 glob 加载
- **被测项目根**：仓库根（`.`）——供 SKILL 的**三个外部脚本门控维度**定位被测项目侧脚本：
  - **维度 10「UI 还原度确定性检查」** → `<被测项目根>/{{AIDP_HOME}}/scripts/check_ui_fidelity.py`
  - **维度 12「上游调用日志可见性与脱敏」** → `<被测项目根>/{{AIDP_HOME}}/scripts/check_upstream_call_log.py`
  - **维度 13「实现偏离设计」** → `<被测项目根>/{{AIDP_HOME}}/scripts/check_design_anchor.py`
  三个脚本都由 AIDP 脚手架经 `ensure_root_scripts` 下发到**被测项目侧**（不在 SKILL 内、不受版本门控），本仓均已下发；⛔ **不传或传错 → 对应维度落到「不适用（未下发）」档**——维度 10 里**约定39-R10「导出只导当前页」是零豁免的 Critical**、维度 12 里 **C1 零日志 / C2 成功路径不可见也是 Critical**，等于静默放过硬门。（同一个根路径三维共用，传一次即可。）
- **被验收版本号**：`{version}`（如 `V0.14.0`）——**维度 13 专用且必填**。它比维度 10/12 多这一个参数，SKILL 侧明令「值由调用方传入，⛔ 不得自拟或省略；取不到就按『不适用（未取到 `--version` 值）』留行」。⚠️ **漏传不会报错、只会让维度 13 恒落「不适用」**：脚本缺 `--version` 值时 argparse 直接 `exit 2`（用法错），而 SKILL 对 exit 2 的处置是「修正参数后重跑」——既不计过也不计不过，报告里两侧都不留痕。故本行与上一行是**两个独立参数**，不要合并、不要省略。

**额外提示**（命令端补充给 skill 的上下文）：
- 任务描述：本次验收的 Sprint 编号 + 功能范围（来自 `01_研发执行计划.md` 中 Sprint-{NNN} 行）
- 推荐附加输入：
  - PRD（用于三方冲突裁决的样式/文案/业务规则裁决）：`docs/requirements/{version}/研发需求/`
  - 迭代执行计划（任务清单）：`docs/plans/{version}/01_研发执行计划.md`
- **★ 规划期基线类文档（约定 33 强制传入，供 SKILL「PRD↔实现」直接比对 + 视觉还原 L1 + 内容完整性核对消费）**——把下列路径显式作输入传给 SKILL，笼统标注"以这些基线为准回检实现有无漏项/漏列/偏离"（约定 21 只传路径、不复述 SKILL 维度）：
  - **PRD 原文（产品提供）**：`docs/requirements/{version}/产品提供/*.md`（作**独立比对基准**，供「PRD↔实现」直接比对维度回检"实现里到底有没有这个按钮/这一列"，绕过设计文档同源污染）
  - **原型内容基线**：`docs/design/detail/{version}/NN_原型内容基线.md`（内容完整性逐页核对：原型有/实现无或行为不符/未标处置 → Critical）
  - **设计令牌**：`docs/design/detail/{version}/NN_设计令牌.md`（如存在，视觉还原 L1 强校验基准）
  - **字段处置对照表**：研发需求内「原型字段 → 处置」对照表（字段/列对账：漏列/未确认增列均违规）
  - **表 E 语义变更→派生展示物影响清单 / 表 F 历史需求作废清单**：研发需求内（约定 22 第三类 / 约定 34）——供 SKILL 维度 4「代码质量检查」的「文案与数据口径一致性」子行以表 E「变更前语义」为旧口径字样清单 grep 残留、以表 F「作废」项的 REQ 编号扫失效注释是否已标注
  - **文案落点表**：`docs/design/detail/{version}/` 详细设计内——供上述维度定位改了口径的说明文案落点、缩小旧口径残留核对范围
  - **统计指标口径表**：`docs/design/detail/{version}/` 详细设计内（`dev-logic-architect` 核心原则 25 / 检查项 34 产出的 8 列表）——供 SKILL **维度 11 / 约定39-R12「同一指标跨页面必须同源」**以其第 8 列「权威取数口径」为基准逐指标核对实现取数点；缺表时 SKILL 回退纯结构判断并把「设计缺口径表」报 Important，**不静默放过**
  - **上游调用日志与脱敏声明表**：`docs/design/detail/{version}/` 详细设计内（`dev-logic-architect` 检查项 35 产出的 6 列表；⛔ **本处不复制列定义**——列名以 SKILL + 其硬门 `check_upstream_call_log_spec.py::REQUIRED_COLUMNS` 为准，复制过一次就会在上游调整列名时静默漂移）——供 SKILL **维度 12「上游调用日志可见性与脱敏」**：12.1 以其第 5 列「脱敏字段清单」为基准、12.2 以第 6 列「二进制/大对象降级说明」为基准**逐行核对**；缺表时 SKILL 回退纯代码判断（只能靠命名特征猜哪些字段算敏感）并把「设计缺声明表」报 Important，**不静默放过**（约定 40）
  - > 上述消费机制以 `code-verification-loop` SKILL 为单一信源；命令端只保证把基线路径交出去（约定 33 命令层责任），由 SKILL 的「产品 PRD 原文 ⟷ 实现 条目对账」+ 维度 4「代码质量检查」的「文案与数据口径一致性」子行消费（已落地，见其 SKILL.md）。
  - **★ 维度 4「代码质量检查」之「文案与数据口径一致性」子行的作用域（约定 34 ⑤ 边界，dev/test 期铁律）**：只核**当前版本交付物**——当前 `code/` + `docs/design/detail/{version}/` 当前版本设计 + 当前版本页面文案 + 表 E「变更前语义」清单；**绝不扫 `docs/design/detail/全量/`（`/version` 正式发布产物）与 `{prev-version}` 历史全量设计**。dev/test 期这些全量/历史文档仍是"上一次正式发布"的旧口径 = **预期正常态**（发布期 Step 3.3.11 重算），**不报缺陷、不提议处理、不主动询问"全量旧口径要不要处理"**（那是越界，留发布期）。

**★ 项目级步骤（不进 SKILL 入参）—— 业务计数声明表的全库回扫**：

```bash
python3 {{AIDP_HOME}}/scripts/check_count_claims.py --project-claims "docs/design/detail/{version}/"
```

⚠️ **它刻意【不】列进上面那张「传给 SKILL 的基线」清单**：`code-verification-loop` 全目录对
「业务计数声明表 / 声明名 / 散落面 / 检查项 36」零命中——**该 SKILL 侧没有任何维度会看这张表**。
把它写成「路径交给 SKILL 消费」会凭空造出一个消费者，让约定 33 的「必须有消费者」核验面
自己骗自己（对照：统计指标口径表 → 维度 11、上游调用日志表 → 维度 12，那两条在 SKILL 的
输入表里都有真实条目）。本表的测试期消费者**就是上面这条 bash**，单一信源见
`{{AIDP_HOME}}/reference/约定细则-3.md` 约定 33 的基线→消费者映射。

⚠️ **为什么测试期必须再跑一次**：规划期 `/sprint-design` 已跑过一次，但核心原则 28 要堵的
失效形态是**后续迭代造成的过期**——「某次迭代加到第 9 种，枚举类改了、页面自动跟着变了，
那几处文案一个都不会变」。规划期那一次**在结构上看不到 `/sprint-dev` 之后引入的漂移**：
表产出 → 机器门校结构 → 扫一次 → 此后再不复看 = 约定 33 明令禁止的「产出即沉睡」。
表不存在 → 整段跳过（不报错、不阻断）；有表则按其「散落面」正则列出候选，**一律 WARN、判定权在人**。

- 仅验收模式单轮返回：结论（通过 / 不通过）+ 各维度 Pass / Fail / 不适用 + 按严重度排序的问题清单（严重度 / 维度 / 文件:行 / 证据 / 修复建议）

**与 AIDP 的衔接**：
- skill 报告的 Critical 问题（及 SKILL 标注须回修的 Important）→ 命令端逐条转写为 bug 记录追加到 `docs/bugfix/{version}/bugfix-{YYYYMMDD}-{user}.md`（「来源」列写 `code-verification-loop 维度 N`），后续由 `/sprint-bugfix` 处理；⛔ 本命令不修代码
- skill 验收通过 → 命令端把通过结论写入 `docs/testing/{version}/sprint-{NNN}/`，进入 `/sprint-close`

### Step 2.5：★ 研发自测用例预判断

`/version` 阶段已通过 `dev-manual-testcase` skill 在 `docs/testing/{version}/研发自测/` 下生成自测方案 + 用例（兼容历史单文件 `研发自测.md`）。本步骤**不重新生成、不自动执行**，仅做"研发自测前的可行性预判断"——用例的真实执行由研发自行按文档完成（或挂接 chrome-devtools-mcp（推荐，仅 Web 项目）/ Playwright / OpenClaw 等 AI 浏览器工具；端到端浏览器实测见 `/sprint-aiauto-test`）。

**预判断动作**（命令端逐项校验，不阻塞流程，结果写入测试报告的「研发自测准入预检」段）：

1. **存在性**：`docs/testing/{version}/研发自测/` 子目录下用例文档（`02_全量自测用例.md` / `02_自测用例-总览.md` 之一；旧锚布局 `01_全量自测用例.md` / `01_自测用例-总览.md` grandfather 兼容）必须存在（兼容历史单文件 `研发自测.md`）。**通常 Step 1 已在缺用例时自动经 `/sprint-selftest` 补跑生成**，故此处一般已存在；**仅当 Step 1 自动生成被跳过/失败仍缺**时 → 提示用户重跑 `/sprint-selftest {version}`（研发自测唯一入口；**不要**直调 `dev-manual-testcase` SKILL——直调会跳过落盘核验 / 目录归一 / 测试环境与账号生成，产物落到 SKILL 默认目录）
2. **测试套件清单提取**：grep 出全部 `### 套件 SUITE-`（规范形态）/ `### 测试套件 TS-`（历史兼容）标题（**正则以 auto-test-runner SKILL `references/usecase-format.md`「标题形态契约」为单一信源**，此处内嵌的 `^#{2,4}\s*(?:测试)?套件\s+(SUITE|TS)-` 仅作粗计、与 SKILL 不一致时以 SKILL 为准）与套件级前置条件，输出"本版本需研发自测的套件清单"
3. **环境准入预检**：抽取套件级前置条件中的"测试账号 / 测试数据 / 接口可用 / 前置依赖"四类要求，逐项对照当前环境做轻量探测：
   - 测试账号 → 读 `docs/testing/{version}/研发自测/01_测试环境与账号.md`（或用例文档"测试账号"段）；如含 SSO 统一认证/单点登录 → 提示用户准备
   - 接口可用 → 用 `*事实清单.md` 的 base + 本 Sprint 涉及的端点 → curl `/<health>` 或 `/actuator/health` 做轻量探活（**仅探活，不执行用例**）
   - 前置依赖 → 检查 Redis / MQ / 第三方系统是否在事实清单的"反代/部署"表中已记录
4. **完备性回顾**：核用例文档末尾的「用例统计摘要」章节（`dev-manual-testcase` 产出，SKILL 单一信源；文档头部**无**覆盖率百分比行，不要去核它）——摘要缺失或合计行与实际用例数不符即标红，提示研发重跑 `/sprint-selftest {version}` 回补。判定口径与阈值以 SKILL 及其 `scripts/check_case_stats.py` 退出码为准
5. **不执行用例**：本命令**绝不**自动逐步执行人工自测用例（即便 AI 浏览器可达）—— 由研发自行决定何时跑、跑多少。命令仅输出"请按 `docs/testing/{version}/研发自测/` 下用例文档逐套件执行"的提示
6. **★ 问题记录优先原则**：执行者遵循 `dev-manual-testcase` 的**「问题记录优先」核心原则**（发现 Bug 不立即中断 → 记录后续测完 → 批量交 `/sprint-bugfix`；三步通则与严重度定义为 SKILL 单一信源，命令端不复述、按名引用不写死编号）。**项目级落点（命令端补充）**：失败用例填入「研发自测/02_自测用例-总览.md（多文件）/ 02_全量自测用例.md（单文件）/ 旧锚 01_ 用例 / 历史 研发自测.md」末尾 skill 预生成的「问题汇总清单」表（每个 ❌ 不通过一行）；全部测完再 `/sprint-bugfix sprint-{NNN}` 批量修复。命令端必须**在终端输出本提示**并写入 sprint-{NNN}-test-report.md 头部「执行规则」段。

**输出**：把预判结果追加到 `docs/testing/{version}/sprint-{NNN}/sprint-{NNN}-test-report.md`「研发自测准入预检」章节（健康探测命令 + 命中/未命中清单 + 执行规则提示）。

### Step 3：在线接口附加观察（后端接口自动测试，可选）

**验收边界**：Step 2 的静态核验与 Step 7 的编译/类型检查形成 `/sprint-test` 验收结论；本步的健康探测、`api-tester` 和接口字段级对齐只在已有服务可用时追加运行时观察。在线成功不得覆盖静态失败，在线失败或环境缺席也不得改变静态验收结论、触发本命令的静态 Critical 回修；发现实际运行缺陷时另记待处理问题，由部署/浏览器实测链路复验。

如果后端是 Spring Boot 项目，**且本地或 Agent 环境中可用** `api-tester` skill（后端接口自动测试 skill，可选），使用 `Skill` 工具调用：

> ⛔ **约定 35 守卫（本步唯一会触及运行时的地方，缺它则本步字面违反"验收循环不启动任何服务"）**：
> **只对【已在运行】的服务发只读探测，绝不自起服务**。进本步前先探活：
> ```bash
> curl -sf -m 3 -o /dev/null "${BACKEND_BASE_URL}/actuator/health" || \
>   { echo "⏭️ 后端未就绪 → 整步跳过（⛔ 不得为跑接口测试而启动服务，约定 35 ①）"; SKIP_API_TEST=1; }
> ```
> - 探活失败 → **整步跳过**，在 `docs/testing/{version}/sprint-{NNN}/sprint-{NNN}-test-report.md`「在线接口观察」段标「接口测试未执行：环境未就绪」，**不阻断**静态验收；
> - ⛔ **禁止**在本步 `mvn spring-boot:run` / `docker compose up` / 任何形式拉起被测服务；
> - 只读探测（GET / 幂等查询）可发，**写操作接口**须由用例显式标注为可测才发。
>
> **边界澄清**：约定 35 禁的是「**为验证而启动服务**」，不是「禁止访问已就绪环境」——
> 对一个别人已经起好的环境发只读请求不算"启动服务"。

**★ 接口字段级契约对齐（`dev-logic-architect` 检查项 25 的测试期消费者；规划期无运行环境、恒 N/A）**：探活成功（`SKIP_API_TEST` 未置位）时**必跑**，与 `api-tester` 是否可用无关：

```bash
[ "${SKIP_API_TEST:-0}" = 1 ] || python3 {{AIDP_HOME}}/skills/dev-logic-architect/scripts/check_api_contract_alignment.py \
  "$(ls docs/design/detail/{version}/*接口设计.md | head -1)" \
  "$(ls docs/requirements/{version}/研发需求/01_研发需求.md docs/requirements/{version}/研发需求/0?_*.md 2>/dev/null | head -1)" \
  "$BACKEND_BASE_URL" --json > docs/testing/{version}/sprint-{NNN}/sprint-{NNN}-api-contract.json
```

结果（只读 GET 探测、report-only）汇入 test-report「在线接口观察」；不一致项另记运行时问题供后续复验，不作为静态验收 Critical，也不改变 Step 2 的结论。探活失败 → 标「接口契约对齐未执行：环境未就绪」。

```
扫描 Controller 和 DTO → 生成 curl 测试命令 → 执行测试 → 写入 api_test_report.md

输出合并到：docs/testing/{version}/sprint-{NNN}/sprint-{NNN}-api-test-report.md
```

### Step 4：前端浏览器仿真功能测试 → 走 `/sprint-aiauto-test`（不在本命令内）

> ⚠️ **前端「浏览器仿真功能测试」由独立命令 `/sprint-aiauto-test`**（当前工具 `chrome-devtools-mcp`，**默认无头 `--headless=new`**）在**部署完成后**承担；`/sprint-test` 本阶段的验收结论只由**静态扫描**（`code-verification-loop`）与静态编译/类型检查决定；可选 `api-tester` 仅提供独立在线观察。

- 本 Sprint 若需浏览器实测：部署完成后按下列**入口判据**选命令（账号/环境/渲染模式等连接信息见 `docs/testing/{version}/研发自测/01_测试环境与账号.md`）：
  1. 查 baseline `memory/.sprint-autopilot-baseline.json` 里本 `{version}` 是否属 **autopilot 体系**——判据 = `current_build` 存在，**或** `versions.{version}` 存在**且** `versions.{version}.source != "sprint-batch"`（`source="sprint-batch"` 是 `/sprint-batch` Step 6.4 自己的预写痕迹，不算 autopilot 体系，否则每次重跑都被弹回）；
  2. 查本 build 的 **AI执行报告**是否已存在；
  3. **属 autopilot 体系 且 本 build AI执行报告缺失** → **改走 `/sprint-autopilot --skip-dev`**（test-only 入口，走子流程 R 产出 AI执行报告后由它委派浏览器实测）；**严禁**在 AI执行报告缺失下直达 `/sprint-aiauto-test` 手驱浏览器；
  4. **不属 autopilot 体系**（真正 standalone / `source="sprint-batch"`）**或 AI执行报告已在** → 直接 `/sprint-aiauto-test --once`。
  > 口径单一信源 = 项目记忆文件（AGENTS.md / CLAUDE.md）「AI 测试入口前置规则」：**实测前必有 AI执行报告**；其中"属不属 autopilot 体系"的判据细则单一信源 = `{{AIDP_HOME}}/flows/sprint-batch/step-6b.md` Step 6.4 入口判据（⛔ 不是 `step-6.md`，那里只剩一句转发指针）。⛔ 本命令**自身不驱动浏览器、也不调 `/sprint-aiauto-test`**（全文无该调用），故不存在「链内豁免」一说——⛔ 不得据此误以为 `/sprint-test` 可以自行开浏览器实测。
- 浏览器仿真测试报告（HTML）由 `/sprint-aiauto-test` 落 `docs/reports/{version}/AI测试报告/`（路径以 `/sprint-aiauto-test` 为单一信源），本命令不生成 e2e 报告。
- 浏览器测试统一走 `chrome-devtools-mcp` / `/sprint-aiauto-test`。

### Step 5：生成测试报告

**输出**：`docs/testing/{version}/sprint-{NNN}/sprint-{NNN}-test-report.md`

内容包含：
- 测试范围和回归范围
- 测试用例统计（总数/通过/失败/阻塞/不适用）
- 静态验收子报告汇总（code-verification-loop）；在线接口观察（如有 api-tester / 接口字段级对齐）单列，不计入静态验收结论；前端浏览器仿真测试报告（HTML）由 `/sprint-aiauto-test` 落 `docs/reports/{version}/AI测试报告/`
- 缺陷统计
- **研发自测问题汇总清单引用**：仅写**跳转链接 + 状态计数摘要**（如「待修复 P0=N₁ / P1=N₂ / P2=N₃ / P3=N₄；已修复 M；已验证 K」），**不嵌入清单全文**（避免与原清单双倍维护）；指向 `docs/testing/{version}/研发自测/` 下用例文档末尾的「问题汇总清单」表（按 glob 汇总所有分册的清单计数）；下游 `/sprint-bugfix` 会从该清单批量读取「待修复」行
- 静态验收结论：✅ 建议进入部署实测 / ⚠️ 有条件进入实测 / ❌ 静态验收不通过；**在线结果不参与静态验收结论**，最终发布仍须独立通过部署与浏览器实测门

### Step 6：Bugfix 验证（回归测试）

回归范围两类来源（**新轮 sprint-bugfix 跑完后再回来**）：

1. **docs/bugfix/{version}/ 下状态为「已修复」的零散 bug**：按 bug 复现步骤与修复报告静态复核、检查回归面，更新「验证结果」（静态复核结论 + 待人工执行项）
2. **「研发自测 末尾的问题汇总清单」中状态从「待修复」→「已修复」的行**（扫描 `docs/testing/{version}/研发自测.md` / `docs/testing/{version}/研发自测/**/*.md` 的清单段；如有测试人员用例则同时扫 `docs/testing/{version}/正式用例/*.md`）：用对应 `用例 ID` 在用例文件里反查该用例的执行步骤，对照修复 diff **静态复核**（修复是否覆盖复现步骤涉及的代码路径）；复核通过 → 该行标「已修复·待人工验证」并在 test-report 列出需研发执行的用例 ID（⛔ 本命令不执行用例，同 Step 2.5 第 5 条）；研发执行通过后再改「已验证」，失败 → 改「修复未通过，需返工」

### Step 7：完成前验证

调用 `superpowers:verification-before-completion`：
- 确认待人工执行的用例清单已列入测试报告（⛔ 本命令不执行用例）
- 确认测试报告已生成
- 确认 bug 记录完整
- ★ **确认本 Sprint 改动侧编译/前端校验通过（Step 6 bugfix 之后的【复验收敛点】）**：⚠️ **前端**部分不再是「唯一收敛点」——`code-verification-loop` 已把 `npx --no-install vue-tsc/tsc --noEmit` + `npx --no-install eslint <改动文件>`（**error 阻断、warning 不阻断**）立为**维度 0 静态基线门**（前置、不计入 14 维度；⛔ **判级与豁免以 SKILL 的 `references/dimension-0-2-baseline-mock.md` 为准、命令端不复述**——那里明写「首轮记录存量错误数作基线、只对增量判 Critical」与「工具未安装标跳过、不得升级为全量 build」，抄成「非零即 Critical」会让接手存量项目的第一轮 100% 阻塞），Step 2 的验收子 Agent 里已跑过一遍。⛔ **但后端编译不在维度 0 内**（该 SKILL 明确不做 `mvn compile`）：它会跑到 `generate-resources` 相，而 `frontend-maven-plugin` 官方默认就绑在那，于是一条写着「只编译不打包」的命令可以真的触发 `npm run build`（直接违反约定 35 ②）。故**后端编译在本步是唯一收敛点**；前端部分本步是 **Step 6 bugfix 之后的复验点**——修完的改动需要再过一次回检，删了就没人管。**仅处理本 Sprint 实际改动的一侧**——改了前端才校验前端（**lint + 类型检查，不打包**）、改了后端才编后端，**未改动的一侧不处理**；执行走**资源受限方式**（`nice` + 限并发 worker/线程，可选 `taskset/cpulimit` 硬顶核数，避免 CPU 打满），配方见 `agents/backend.md`「Step 7: 编译验证」/ `agents/frontend.md`「Step 4: 前端验收校验」。**前端验收期不跑完整打包**（打包 = bundle+压缩，CPU 杀手且验收不需要产物），部署打包由使用者按需自行执行。编译/前端校验失败 → 按硬失败回 `/sprint-bugfix`

### Step 8：更新状态

更新 `memory/{version}/{user}/activeContext.md`：
- 在「子迭代记录」中追加测试阶段的 Round 记录
- 在「待处理 Bugfix」中列出新发现的问题
- 更新「当前工作焦点」

## 输出

```
✅ /sprint-test 完成（{version} / Sprint-{NNN} 测试阶段）

📋 生成的文件：
- docs/testing/{version}/sprint-{NNN}/sprint-{NNN}-testcases.md
- docs/testing/{version}/sprint-{NNN}/sprint-{NNN}-test-report.md
- docs/testing/{version}/sprint-{NNN}/sprint-{NNN}-api-test-report.md（如执行 api-tester）
- 前端浏览器仿真测试报告（HTML）→ 由 `/sprint-aiauto-test` 落 `docs/reports/{version}/AI测试报告/`（部署后单独跑）

测试结果：
- 总用例数：{N}
- 通过：{N} ✅
- 失败：{N} ❌
- 新增缺陷：{N} 个

code-verification-loop 验收结果：
  - 各维度结论：{逐维度 ✅/❌，维度清单以 SKILL 回传的结构化报告为准，命令端不硬编码维度子集}
  - 总体评级：{✅ 通过 / ❌ 需修复}

{如有缺陷}
缺陷清单（均位于 docs/bugfix/{version}/）：
- bugfix-{YYYYMMDD}-{user}.md — {问题标题} — P{X}

📌 下一步：
1. /sprint-bugfix sprint-{NNN} → 修复发现的问题
2. /sprint-test → 修复后再次执行测试（回归验证）
3. /sprint-close {NNN} → 所有测试通过后关闭 Sprint
```
