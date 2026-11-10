# /sprint-test — 测试阶段（含验收循环）

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
CONTEXT_RESULT=$(python3 {{AIDP_HOME}}/scripts/entry_context.py resolve --root . --entry sprint-test \
  "${CONTEXT_ARGS[@]}" --json) || exit $?
EXECUTION_CONTEXT=$(printf '%s' "$CONTEXT_RESULT" | python3 -c 'import json,sys; print(json.load(sys.stdin)["execution_context"])') || exit $?
# 消费 resolve 返回的 execution_context 为 EXECUTION_CONTEXT，再路由。
python3 {{AIDP_HOME}}/scripts/entry_context.py route --root . --entry sprint-test \
  --execution-context "$EXECUTION_CONTEXT" --phase test --json
```

返回 `route=light` → 执行该片的 **test** 能力，然后 **return**；不进入下文任何 Sprint 取号、卡片、activeContext、started、报告路径或归档步骤。返回 `route=formal` 才执行下文正式身份门；可选动作仍按 actions 筛选，未授权为 NOT_REQUESTED。任何子命令/修复/重试/续跑均保留原参数并显式附 `--execution-context "$EXECUTION_CONTEXT"`；不能只传 `--unattended`/`--from-batch` 而丢身份。

## formal 流程

你正在执行 `/sprint-test` 命令，为当前 Sprint 执行测试和验收检查。

**公开职责**：用户显式 `/sprint-test` 请求 static+related-test+review+full-cvl；嵌套/自然路由仅继承父授权。review 使用本次 CVL 真实证据，不额外叠完整轮。test-only 不取得 implement/document/live 权限；问题留证据，父已授权实现才交原实现者修复。策略与预算见 `light-context.md`。

**步骤选择表**：Step 1/2.5 只读取已有本任务用例；新用例成文须 document。Step 2 须 full-cvl，只有 review 时直接用 reviewer 能力后返回；Step 2.6/7 的单测围栏须 related-test；Step 3/4 的在线动作须 live-tests。Step 5 自动记录本轮真实结果不代表授权生成整套文档。未启用项写 NOT_REQUESTED，不列欠账或 PASS。


参数：$ARGUMENTS（可选，Sprint 编号。如省略，仅继承父上下文；不从 activeContext 认领新任务）

| 参数 | 作用 |
|------|------|
| `--unattended` | **无人值守上下文标记**（`/sprint-full` 逐层透传而来）：① 本命令自身任何决策门**不弹 `AskUserQuestion`**；② **必须向下透传**给 `/sprint-selftest` 与原实现 Agent——`/sprint-selftest` 内部的 `dev-manual-testcase` SKILL 有「生成用例前必须主动询问方案 8 项 + 5 组连接信息」的强制第零步，不透传即在此挂死；③ **派 `code-verification-loop` 验收子 Agent 时把无人值守上下文写进 prompt**（需要人工裁决的节点记录结论 + 标注待人工确认后返回）|
| `--from-batch` | 批量子任务标志（由 `/sprint-full` 透传）：本命令不弹 `AskUserQuestion`，内容决策门按「⏸ 待裁决」返回上层（语义单一信源 = `/sprint-full` 参数表） |
| `--aiauto-test-required` / `--skip-aiauto-test` | 原样消费外层实测意图；required 优先，不据 `--from-batch` 猜实测。 |
| `--resume-acceptance` | 恢复同版本同 Sprint 未闭环验收。先校验原始完整 CVL 报告、修订、实际写集及修复证据；可信则从 Step 6 差量闭环继续，不重新完整 CVL；缺可信原始质量证据则回 Step 2 完整验收，不能冒充增量。 |

## 前置流程

**VCS 能力分流**：从 `{{AIDP_HOME}}/scripts/vcs.py` 的 `detect_mode(Path.cwd())` 读取 `vcs_mode=git|none`，用 `developer_identity(Path.cwd())` 取得 `{user}`；向 `code-verification-loop` 验收子 Agent 透传模式。`vcs_mode=none` 时继续本地用例、代码静态检查与验收，Git-only diff/commit/push/CICD 检查逐项记 `unsupported:vcs-disabled`（不是 passed，也不折算为全绿）；不能用 Git 差异判定测试范围时以 Sprint 计划与 `activeContext.md` 的本地文件清单为依据。Git 模式保持原有验收语义。

按 `docs/init/06_版本与用户目录约定.md`：
1. **{version}** ← 项目记忆文件（路径经 `python3 {{AIDP_HOME}}/scripts/agent_env.py memory-file` 取：`AGENTS.md`，只用 Claude Code 时为 `CLAUDE.md`）「当前状态.当前版本」
2. **{user}** ← `python3 {{AIDP_HOME}}/scripts/vcs.py user`（唯一解析实现：显式 → 本地 Git 身份 → `AIDP_USER` → OS 用户；⛔ 别自己拼 `git config user.name`，无 Git 项目上会解析出另一个身份）
3. **{NNN}** ← 从参数或 activeContext 读取

## 前置检查

第一动作 Read `{{AIDP_HOME}}/flows/sprint-dev/incremental-contract.md`，再显式 Read `docs/design/detail/{version}/_sprint-{NNN}-契约卡.md` 和 `memory/{version}/{user}/activeContext.md`。契约卡不走排除 `_*` 的正式文档 glob；既有计划内 Sprint 无卡时保持完整需求/设计/计划门，不得借缺卡降为 S；采用新累进协议却缺卡 → 返回开发补卡，不猜档位。

- **M（document 已授权时）**：检查完整需求、设计、计划及适用用例的真实内容与原有回检；汇合证据必须含当前 `contract_revision`、实际写集、docs路径、docs 完成状态与已授权 review 的真实结果；未授权 review 为 NOT_REQUESTED。任一缺失、仍运行、旧修订或路径仅占位 → 恢复缺失 docs/实现任务，重新汇合通过后才进入 CVL。
- **S**：契约完整、实现与契约一致、受影响四族待成文义务已登记即可进入静态验收；正式正文允许攒批。不得把契约 AC 冒充正式实测用例，不为本次静态验收强启完整文档生成。
- **L / 旧流程**：保留先完整文档、再代码的原有门；需求按 `docs/requirements/{version}/研发需求/{01_研发需求,00_索引,00_研发需求}.md` 兼容布局读取，设计/计划按索引实际路径读，不能只认裸名或硬编码 `03_接口设计.md`。
- 新协议各档均核当前契约修订与实际写集；review 获授权才核 reviewer 结果；变更越过契约/涉及破坏性、版本承诺或部署授权 → 回原安全门，分档不提供豁免。

**正式用例门独立于静态验收**：消费契约卡中 `check_case_ledger_pending.py --prepare` 的真实 required/deferred 读数及外层实测意图，得到 `CASE_REQUIRED=1|0`。有 `--aiauto-test-required` 时必须 required=true；`--skip-aiauto-test` 不能覆盖 required。缺读数先按原调用上下文执行该脚本 prepare，不默认 false。required=true 且用例缺失/用例族事实义务未清 → document 已授权才经 `/sprint-selftest` 补齐并通过 `python3 {{AIDP_HOME}}/scripts/check_case_ledger_pending.py --version {version} --json` 再放行；required=false 可保留 deferred，但报告必须明确实测未完成。Step 1 与 Step 2.5 同样消费该读数。

**测试计划输入**：消费契约卡 `test_plan` 的 `cwd`、`targeted_argv`、`unit_runners`、`env_id`、`inputs` 与授权边界。本 Sprint 单元测试由 `test_scope.py` 从真实改动推导（见 Step 2.6），⛔ 不读取 `full_argv`（它只属于 `/sprint-aiauto-test` 全量单测）；related-test 已授权但缺运行器则返回 TOOL_ERROR 与配置缺口，不用 `true` / `echo` / 空命令冒充测试。旧计划内无卡时据现有项目测试配置记录等价运行器。报告逐套列出实际字段与 run_id。

**命令测试账本**：所有命令型验证经 `test_ledger.py` 包装，原 argv 原样传入。开发/修复用 `--scope targeted`；本 Sprint 验收的单测由 `test_scope.py` 推导后经 `run-scope` 逐套记账（`--scope sprint`）。同树、命令、scope、环境及 inputs 的 PASS 复用，targeted 与 sprint 互不替代；环境标识 `TEST_ENV_ID` 来自实际工具链/外部状态，变化则换值，不得硬编码假稳定环境。本命令不启动服务、不打包、不做浏览器实测。只要输入变更就重新计算账本，禁止凭上一次文本“通过”跳过。

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
if [ -z "$PRIMARY" ] && [ "$CASE_REQUIRED" = 1 ]; then
  echo "⚠️ 正式用例/ 和 研发自测/ 均无用例"
  echo "→ 当前命令经 /sprint-selftest 补齐研发自测方案 + 自测用例（不中断 /sprint-test 流程）"
  # Claude 直接调用命令 /sprint-selftest {version}（研发自测唯一入口）：其内部调 dev-manual-testcase 生成
  #   + 落盘核验 + 目录归一 + 测试环境与账号，命令端不自行重复归一/传占位符逻辑（单一信源，约定 21）
fi
```

**Claude 行动指引**：若上述 if 命中，**立即在当前 sprint-test 会话中调用命令 `/sprint-selftest {version} [--unattended]`**（研发自测唯一入口；⛔ 本命令带 `--unattended` 时**必须透传**，否则 SKILL 的强制询问第零步会在无人可答处挂死）补齐用例，然后继续 Step 1 之后的"Sprint 范围裁切 + 补充用例维度"流程；**不要**让用户去单独跑 `/version`。

**required=false 的静态轮次**：不触发上面的补齐调用。已有用例可裁切；无正式用例时只按契约 AC 做静态核对，报告记 deferred 与四族义务，不伪造用例统计。Step 2.5 缺正式用例时同样记录延期，不改成强制生成。后续实测仍先过正式用例门。

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

先消费route结果；full-cvl未授权则NOT_REQUESTED并跳到下一适用步骤，已授权分支执行：

```bash
EXECUTION_CONTEXT="${EXECUTION_CONTEXT:?从父入参重绑}"
python3 {{AIDP_HOME}}/scripts/execution_policy.py require-action --root . \
  --execution-context "$EXECUTION_CONTEXT" --action full-cvl || exit $?
```

派发/执行前按light-context预留父预算，prompt带同revision/action/inputs hash，不重新grant。


> ★ **客户端应用 MCP 条件启用入参**（默认不传；绝大多数项目无此段）：`code-verification-loop` 的
> **维度 9**（标题以 SKILL 为准）是**入参门控**、且 SKILL 明令**不自行探测是否启用**——
> **命令端不传 = 该维度永不启用**，启用了该能力的项目会静默漏掉这一层质量门。
> ⚠️ 该能力**是跨端的**（Web / 小程序 / 移动 / 桌面），**WebMCP 只是它的 Web 端实现**：
> 只按 WebMCP 判，非 Web 项目恒得 `enabled: false`，而 SKILL 侧「非 Web 已声明即通用半场照跑」
> 那一半就永远不会执行——**失效方向是全绿**。故调 SKILL 前取**两级**判定：
>
> ```bash
> python3 {{AIDP_HOME}}/scripts/check_client_mcp.py --version "{version}" --detect --json  # 跨端判定唯一实现
> #   → declared / capability_state / client_type / implementation
> python3 {{AIDP_HOME}}/scripts/check_webmcp.py --version "{version}" --detect --json      # 仅 Web 叶子的专有事实
> #   → enabled / entry_symbols（client_type=web 且 implementation=webmcp 时才需要）
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

> `check_client_mcp.py` 的 `enabled: true` → 随 prompt 原样传 **`client_mcp`** 对象：
> **保留 `enabled`**（SKILL 门控读此键，检测器保证它与 `declared` 同值），以及
> `client_type` / `implementation` / `capability_state` / `source` 等检测事实；
> `declared-unimplemented` → 报告列前置缺失，不伪造 `enabled: true`；检测退出 2（声明冲突/非法值）须先修正声明，⛔ 不冒充未启用；
> **另**当 `client_type=web` 且 `implementation=webmcp` 时**再加**传 `webmcp_enabled: true`
> + `webmcp_entry_symbols: <check_webmcp.py 返回的数组原样>`（⚠️ 后者**不可省略也不可写死**：挂载位置已迁移过一次、
> 规范仍在演进，上游缺该入参会直接报错而非猜默认值）。
> 两者均未声明 → **什么都不传**，不提、不留位置。
> ⛔ **非 Web 项目不要传 `webmcp_*`**：它们只是 Web 适配输入，传过去不会为非 Web 创建入口，
> 只会让 SKILL 把客户端判成 web（新旧声明冲突时 SKILL 侧须报错，⛔ 不静默覆盖）。


> ★ **独立子 Agent 派发（隔离上下文，不占 /sprint-test 主对话）**：`code-verification-loop` SKILL 已声明「作为更大编排流程的一环被调用时，应把**整个验收循环**作为一个独立子 Agent 派发」——其扫描脚本（`scan_mock_data.py` / `scan_third_party_mock_antipatterns.py` 等）+ 多维度核验都在验收子 Agent 自身上下文内跑，主流程**只接收精简结构化报告**（各维度 Pass / Fail / 不适用 / 未执行（原因）+ 全部发现的唯一问题编号、严重度、`loop 推进`、file:line、证据与修复建议；不得只回传阻塞项或过滤非阻断 Important），脚本 stdout 不污染主上下文。因此本步**不在主对话直接用 `Skill` 工具调**，而是用 `Agent` 工具派一个子 Agent，prompt 为「用 Skill 工具调 `code-verification-loop`，**把下方『调用参数』与『额外提示』两段的全部内容逐项传全**，跑完只回传精简验收结论」。⛔ **别把模板句写成「传入代码/设计/接口路径」**：那会漏掉同步骤要求的 `--third-party-mode` 门控旗标、`webmcp_enabled`/`webmcp_entry_symbols`、被测项目根、被验收版本号——漏传的失效方向全是「维度静默落不适用」或「合规代码被判假红」，而不是报错。与 `/sprint-design` Step 1.6 子 Agent 派发同款。

> ⛔ **`--unattended` / `--from-batch` 时 prompt 显式带上非交互上下文**（「任何需要用户裁决的节点一律不询问：记录结论 + 标注待人工确认后返回」）——子 Agent 里无人可答，主流程只会看到「子 Agent 未返回」。

派发的子 Agent 内部以 `Skill` 工具调用 `code-verification-loop`。**skill 内置多维度独立 Agent 检查 + 分级处理（级别以 SKILL 为单一信源）+ 每轮留痕**；命令端按约定 21 不复述维度内容与级别名，只负责传入参数 + 接收验收报告。维度索引见 `{{AIDP_HOME}}/skills/code-verification-loop/SKILL.md`，各维度细则见其 `references/flow-dims-*.md`（`flow-dims-core` / `flow-dims-static-gates` / `flow-dims-quality` / `flow-dims-delegated`），第三方 mock 协议见 `references/third-party-mock-protocol.md`（SKILL 单一信源）。

> 开发期更早的"复杂度+复用"自检由 Frontend Agent Step 4.5 / Backend Agent Step 7.5 承担（作为更早的自检关口，不取代 SKILL 兜底）。

**调用参数**（按 SKILL 输入要求传入）：
- **运行模式**：`mode=verify-only`——任务描述写明「代码与文档已按档位汇合；只验收、不修复，单轮完整问题清单交调用方」。CVL **不支持 delta 参数**，不构造 `mode=delta` 或虚构开关。只做这一次完整质量审查；修复后由调用层 reviewer 查问题与新增 diff，**不得宣称 CVL 二次完整通过**。其命令型检查同样经测试账本复用，不能用账本替代语义质量审查。
- **代码路径**：`code/`（按本项目实际单/多前后端组织取根目录或子项目目录）
- **设计文档路径**：`docs/design/detail/{version}/` 下真实正式产物，并显式附 `docs/design/detail/{version}/_sprint-{NNN}-契约卡.md` 与 `contract_revision`。S 未成文部分以契约卡为本轮规格、四族台账为待成文义务，明确告诉 CVL 不把预期延期误报成“正式文档已齐备”；SKILL 自身判据和原结论保持原样。
- **接口文档路径**：按契约卡 docs路径/`00_索引.md` 指向的真实接口章节；M 合册直接传合册与契约接口章节，不传不存在的 `03_接口设计.md`。旧布局兼容 `03_接口设计.md` / `接口设计.md`，多分册则传目录与明确文件清单。
- **被测项目根**：仓库根（`.`）——供 SKILL 的**四个外部脚本门控维度**定位被测项目侧脚本：
  - **维度 10「UI 还原度确定性检查」** → `<被测项目根>/{{AIDP_HOME}}/scripts/check_ui_fidelity.py`
  - **维度 12「上游调用日志可见性与脱敏」** → `<被测项目根>/{{AIDP_HOME}}/scripts/check_upstream_call_log.py`
  - **维度 13「实现偏离设计」** → `<被测项目根>/{{AIDP_HOME}}/scripts/check_design_anchor.py`
  - **维度 15「同族增量项一致性」** → `<被测项目根>/{{AIDP_HOME}}/scripts/check_sibling_family.py`
  四个脚本都由 AIDP 脚手架经 `ensure_root_scripts` 下发到**被测项目侧**（不在 SKILL 内、不受版本门控），本仓均已下发；⛔ **不传或传错 → 对应维度落到「不适用（未下发）」档**——维度 10 里**约定39-R10「导出只导当前页」是零豁免的 Critical**、维度 12 里 **C1 零日志 / C2 成功路径不可见也是 Critical**，等于静默放过硬门；维度 15 里 **F2「成员未登记」也是 Critical**，漏传只关掉它的机器半场（15.1~15.3 语义核对仍照跑）。（同一个根路径四维共用，传一次即可。）
- **被验收版本号**：`{version}`（如 `V0.14.0`）——**维度 13 专用且必填**。它比维度 10/12 多这一个参数，SKILL 侧明令「值由调用方传入，⛔ 不得自拟或省略；取不到就按『不适用（未取到 `--version` 值）』留行」。⚠️ **漏传不会报错、只会让维度 13 恒落「不适用」**：脚本缺 `--version` 值时 argparse 直接 `exit 2`（用法错），而 SKILL 对 exit 2 的处置是「修正参数后重跑」——既不计过也不计不过，报告里两侧都不留痕。故本行与上一行是**两个独立参数**，不要合并、不要省略。

- **改动前基线 ref**（SKILL `verify-only` 输出契约明令：维度 0 类型检查的存量基线及维度 4 / 7 / 8 / 14 的一切基线对照**一律取改动前**；未给时 SKILL 回落 `git merge-base HEAD <主干分支>`——**主干开发时 merge-base 就是 `HEAD`**，本次改动被整批吞成「存量」，方向是假绿。故本参数**必须显式传**，⛔ 不得省略交给 SKILL 回落）：
  - `vcs_mode=git`：传**本 Sprint 起点 commit**（`/sprint-dev` 动手前的 HEAD，与 `flows/sprint-dev/postdev-writeback-1.md` X.0.0 变更检测用的 `{sprint-start-sha}` 同一值）。先读取契约卡保存的改动前基线 ref，验证它确为本 Sprint 起点；旧流程无卡时按序解析、取到即停：① 上游编排（`/sprint-full` 等）显式透传的起点 commit；② 本 Sprint 改动全部仍在工作区未提交（本 Sprint 无已提交 commit）→ `HEAD`；③ 当前在特性分支 → `git merge-base HEAD <主干分支>`，**仅当结果 ≠ `HEAD` 才有效**；④ 以上皆不成立 → 按下方「取不到」处置。⛔ 不得用 `HEAD~1` 顶替（多 commit 的 Sprint 会漏掉前面的改动）、⛔ 不得凭感觉挑一个 commit。
  - `vcs_mode=none`：无可检出的改动前代码（`sprint-{NNN}-local-before.json` 只有 sha256、不含旧内容，跑不了改动前的类型检查）→ 一律按「取不到」处置。
  - **取不到时**：prompt 里显式写「改动前基线 ref：无（取不到；⛔ 不得回落 merge-base / 本轮首跑错误数）」，由 SKILL 按其契约把依赖基线的项落「**基线无效，本项未核验**」（`未执行（原因）` 行 + 一条 `Important`「本项未核验」→ 结论 `不通过`）。命令端处置：该类条目**不是代码缺陷**，⛔ 不转写 bugfix（`/sprint-bugfix` 无从修复，只会空转）；在测试报告列为**待人工核验项**（`vcs_mode=none` 记 `unsupported:vcs-disabled`，`git` 模式记「基线无效：未取到 Sprint 起点 commit」），⛔ 不折算为通过、不私自改判 SKILL 结论。**无人值守 / 编排调用必须向上游返回「不通过 / 未核验」失败信号，附基线缺失或工具环境原因，交上游按失败计数熔断；不能只挂一条待办后返回成功、不能自动制造基线。交互式才列待人工核验项**。

**额外提示**（命令端补充给 skill 的上下文）：
- 任务描述：本次验收的 Sprint 编号 + 功能范围（来自 `01_研发执行计划.md` 中 Sprint-{NNN} 行）
- 推荐附加输入：
  - PRD（用于三方冲突裁决的样式/文案/业务规则裁决）：`docs/requirements/{version}/研发需求/`
  - 迭代执行计划（任务清单）：`docs/plans/{version}/01_研发执行计划.md`
  - **同族增量项声明表**（`dev-logic-architect` 检查项 41 的 5 列表，在 `docs/design/detail/{version}/` 内）：维度 15 的基准表——第 2 列即 F1/F4 的比对对象、第 4~5 列即 F2/F3 的比对对象；上游没产出时 SKILL 侧回退纯代码判断并报 🟡「设计缺声明表」，⛔ 不静默放过
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

- 仅验收模式单轮返回：结论（通过 / 不通过）+ 各维度 Pass / Fail / 不适用 / 未执行（原因）+ 完整问题清单（唯一问题编号 / 严重度 / `loop 推进` / 维度 / 文件:行 / 问题 / 证据 / 修复建议）；按 SKILL 输出契约汇总，非阻断 Important 不得省略，同一问题按编号去重，不把详情和建议中的引用重复计数。

**与 AIDP 的衔接**：
- **验收结论以 SKILL 返回的结论字段（`通过` / `不通过`）为准**，⛔ 命令端不按 `loop 推进` 自行重判、也不改判。严重度、推进标记和验收结论的关系以 SKILL.md「严重度与 loop 推进」为单一信源；**仅非阻断 Important 仍按 SKILL 返回的 `不通过` 交接**，不能把 loop 可收尾解释为验收通过。**登记 bug 与是否阻断是两件事**：转写时保留唯一问题编号、原严重度、`loop 推进` 与证据，以下完整转写要求不改变 SKILL 返回结论。
- **Critical 与 Important 一律**保留完整发现，代码缺陷逐条登记 BUG；`问题=本项未核验` 且原因为基线/工具不可用 → 保留失败信号和原因，不转代码 BUG。登记时保留唯一问题编号、原严重度、`loop 推进`、file:line、证据与来源回链，非阻断不等于可删除。
- **处置三分**（依据 `/sprint-bugfix`「缺陷处置默认决策纪律」，不调用该命令）：① 当前行为错误，包括**错误性 Suggestion** → 原实现 Agent 当轮修复；② 纯优化、当前行为正确 → 记录不修理由/可选后续建议，不扩范围；③ 产品口径或对外承诺未定 → 记录具体待回答问题、挂起原因与影响，按原授权门返回。工具/基线未核验单列，不用“产品待确认”包住技术缺陷。
- 主流程先用 `python3 {{AIDP_HOME}}/scripts/alloc_id.py --kind BUG --count 1 --owner orchestrator --version {version} --scope bugs` 原子预留 BUG ID，再串行追加 `docs/bugfix/{version}/bugfix-{YYYYMMDD}-{user}.md`；同一 CVL 问题回链已有记录则复用 ID。编号器不可用 → 保留待登记工作单并报阻塞，不自行 grep 最大值或编造编号。子 Agent 不并发写共享记录/卡/memory，不擅自提交。
- 原始 CVL 结论写入报告后保留不变；即使原结果 `通过`，错误性 Suggestion 仍须进入 Step 6。调用层修复后的验收结论另列，全部证据收敛才登记 review baseline 并交 close，不能直接用首轮 CVL 通过跳过后续验证。

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

### Step 2.6：本 Sprint 单元测试（范围与执行协议唯一信源）

输入固定为本 Sprint `sprint-start-sha` 到当前树的实际改动（包含提交、暂存、未暂存、新文件、删除）与契约 `write_set` 的并集。起点与 Step 2 及 postdev-writeback X.0.0 相同；不能只用修复前 HEAD 取代 Sprint 起点。

`test_plan.unit_runners` 是 JSON 数组：每项含项目相对 `cwd`、测试后缀 `suffixes`、原始 `argv` 模板、`env_id` 和 root 相对的 `inputs`。按实际项目配置登记；例如 Python runner 可为 `{"cwd":"code/backend","suffixes":[".py"],"argv":["python3","-m","pytest","{tests}"],"env_id":"python-project","inputs":["code/backend/pyproject.toml"]}`（路径与参数须换为真实项目值）。

- `mode=named` 默认按模块目录及命名映射：改动测试自身、Java `FooTest`、前端 `foo.spec.*` / `foo.test.*`、Python `tests/test_x.py`；argv 必须含独立 `{tests}` 或类名选择器 `{test_classes}`，禁止无选择器的命令。路径转换为 runner 的 cwd 相对路径，同名模块不得串选。
- `batch` 明确表示运行器能否合批；默认仅已知安全的 pytest/unittest/Jest/Vitest/Maven 选择器合批，`python {tests}` 仍逐文件。`resources` 映射真实资源到 consumer/test（如 `{"config/x.yaml":["src/consumer.py","tests/test_x.py"]}`）；JSON/YAML/SQL 变化不得丢弃。消费 `selection.proven/conservative/unanalysable` 与 dependencies 原因，未分析不冒充覆盖。
- 项目已使用框架 related 能力时，登记 `mode=related`，通过 `{sources}` 向已有 Jest `--findRelatedTests` / Vitest `related` 命令传入源码范围；实际命令仍来自项目测试配置。
- 主流程按 Step 7 的 **acceptance-sprint-unit** 围栏推导并执行。`test_scope.py` 输出映射、运行 argv、未匹配项与 `scope_hash`；`run-scope` 从 Git 和写集重新推导核对，不信任手改的清单。测试命令由脚本消费，不让执行体临时挑选。
- `FAIL`：先区分业务断言与工具/运行器失败；仅已证实业务错误登记 BUG，且 implement 已授权才交 Step 6。`UNVERIFIED`：工具缺失、超时、输入或运行器缺失逐项记「未执行（原因）」+ Important「本项未核验」，不当代码 BUG、不算通过。
- `PARTIAL` / `EMPTY`：部分/全部源码无对应测试，逐个源码列「无对应单测」（Minor），不伪造 PASS/run_id，不以此新增人工确认门；仍完成 CVL 与改动侧编译校验。
- 同 revision、同树、命令、环境与 inputs 的真实 hash 匹配才复用 PASS。命名映射只是选测种子，不能证明测试独立：跨树继承还须校验本地传递依赖，跨模块共享源码同样参与；动态或无法解析的依赖保守补测并记录原因。未受影响项才可继承原证据，报告标明来源、依赖清单与判据，不冒充本树重新执行。共同输入/环境变化使相关证据失效。

无 Git / 起点无效时如实记「本项未核验」，延续 Step 2 的基线缺失处置，不构造起点或回落扩大范围。Step 5 报告必须包含每个改动→测试映射、实际 argv/cwd/env_id、通过/失败/未执行及原因、无对应单测清单、范围 hash 与 run_id。

### Step 3：在线接口附加观察（后端接口自动测试，可选）

先消费route结果；live-tests未授权则NOT_REQUESTED并跳到下一适用步骤，已授权分支执行：

```bash
EXECUTION_CONTEXT="${EXECUTION_CONTEXT:?从父入参重绑}"
python3 {{AIDP_HOME}}/scripts/execution_policy.py require-action --root . \
  --execution-context "$EXECUTION_CONTEXT" --action live-tests || exit $?
```

派发/执行前按light-context预留父预算，prompt带同revision/action/inputs hash，不重新grant。


**验收边界**：Step 2 的静态核验、Step 2.6 的 Sprint 单测与 Step 7 的编译/类型检查形成 `/sprint-test` 验收结论；本步的健康探测、`api-tester` 和接口字段级对齐只在已有服务可用时追加运行时观察。在线成功不得覆盖静态失败，在线失败或环境缺席也不得改变静态验收结论、触发本命令的静态 Critical 回修；发现实际运行缺陷时另记待处理问题，由部署/浏览器实测链路复验。

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

> ⚠️ **前端「浏览器仿真功能测试」由独立命令 `/sprint-aiauto-test`**（chrome-devtools 套件，**默认走本地 CLI 无头 `--headless=new`**，远程 MCP 须显式声明）在**部署完成后**承担；`/sprint-test` 本阶段的验收结论由**静态扫描**（`code-verification-loop`）、Sprint 单测与静态编译/类型检查决定；可选 `api-tester` 仅提供独立在线观察。

- 本 Sprint 若需浏览器实测：部署完成后按下列**入口判据**选命令（账号/环境/渲染模式等连接信息见 `docs/testing/{version}/研发自测/01_测试环境与账号.md`）：
  1. 查 baseline `memory/.sprint-autopilot-baseline.json` 里本 `{version}` 是否属 **autopilot 体系**——判据 = `current_build` 存在，**或** `versions.{version}` 存在**且** `versions.{version}.source != "sprint-batch"`（`source="sprint-batch"` 是 `/sprint-batch` Step 6.4 自己的预写痕迹，不算 autopilot 体系，否则每次重跑都被弹回）；
  2. 查本 build 的 **AI执行报告**是否已存在；
  3. **属 autopilot 体系 且 本 build AI执行报告缺失** → **改走 `/sprint-autopilot --skip-dev`**（test-only 入口，走子流程 R 产出 AI执行报告后由它委派浏览器实测）；**严禁**在 AI执行报告缺失下直达 `/sprint-aiauto-test` 手驱浏览器；
  4. **不属 autopilot 体系**（真正 standalone / `source="sprint-batch"`）**或 AI执行报告已在** → 直接 `/sprint-aiauto-test --once`。
  > 口径单一信源 = 项目记忆文件（AGENTS.md / CLAUDE.md）「AI 测试入口前置规则」：**实测前必有 AI执行报告**；其中"属不属 autopilot 体系"的判据细则单一信源 = `{{AIDP_HOME}}/flows/sprint-batch/step-6b.md` Step 6.4 入口判据（⛔ 不是 `step-6.md`，那里只剩一句转发指针）。⛔ 本命令**不在自身执行链内内联驱动浏览器**（浏览器实测一律交给上列入口所指向的命令），故不存在「链内豁免」一说——⛔ 不得据此误以为 `/sprint-test` 可以自行开浏览器实测。
- 浏览器仿真测试报告（HTML）由 `/sprint-aiauto-test` 落 `docs/reports/{version}/AI测试报告/`（路径以 `/sprint-aiauto-test` 为单一信源），本命令不生成 e2e 报告。
- 浏览器测试统一走 `/sprint-aiauto-test`（默认本地 `chrome-devtools-cli`，远程 MCP 须显式声明；⛔ 不要按工具名假定必须走 MCP）。

### Step 5：生成测试报告

**输出**：`docs/testing/{version}/sprint-{NNN}/sprint-{NNN}-test-report.md`

内容包含：
- 测试范围和回归范围；Step 2.6 的改动→测试映射、范围 hash、实际命令、run_id 与未执行原因
- 测试用例统计（总数/通过/失败/阻塞/不适用）
- 静态验收子报告汇总（code-verification-loop）；在线接口观察（如有 api-tester / 接口字段级对齐）单列，不计入静态验收结论；前端浏览器仿真测试报告（HTML）由 `/sprint-aiauto-test` 落 `docs/reports/{version}/AI测试报告/`
- 缺陷统计
- **研发自测问题汇总清单引用**：仅写**跳转链接 + 状态计数摘要**（如「待修复 P0=N₁ / P1=N₂ / P2=N₃ / P3=N₄；已修复 M；已验证 K」），**不嵌入清单全文**（避免与原清单双倍维护）；指向 `docs/testing/{version}/研发自测/` 下用例文档末尾的「问题汇总清单」表（按 glob 汇总所有分册的清单计数）；下游 `/sprint-bugfix` 会从该清单批量读取「待修复」行
- 静态验收结论：✅ 建议进入部署实测 / ⚠️ 有条件进入实测 / ❌ 静态验收不通过；**在线结果不参与静态验收结论**，最终发布仍须独立通过部署与浏览器实测门

### Step 6：原实现者当轮修复与差量复核

1. 按 Step 2 的 BUG ID、根因/复现证据与具体写集，把错误交回**原实现 Agent**；docs 问题交原 docs Agent。仅 implement 获授权才修复，related-test 获授权才写/跑复现测试；否则只回传具体发现；不新起 `/sprint-bugfix`，不把 CVL 切回 loop。原 Agent 已结束可恢复其上下文；确实不可恢复时主流程记录原因并显式移交原工作单、契约与写集，不能重开 Sprint。契约变更先修订 `contract_revision`，重新过受影响的分档汇合/授权门。
2. 修复后重新消费 Step 2.6 的完整范围并执行 Step 7 围栏；脚本只补跑受影响运行项，未变证据可追溯复用。主流程串行回填 BUG 状态、修复文件与实际 `run_id/status/reused`；不能用实现者随意选的 targeted PASS 替代 Sprint 范围证据。
3. 独立只读 reviewer 复核**原问题 + 修复新增 diff + 受影响契约/调用点**，保留修订、实际写集、复核判据、证据与结论。它是调用层差量复核，不是 CVL 的第二次完整验收。原问题未覆盖、回归失败或新错误 → 返回原实现 Agent；每轮定向验证，不每轮全量。同根因同 inputs 无变化立即停止重试；父预算耗尽或真实授权/环境阻塞 → 返回具体事实与已授权 scope，不能标通过。
4. 全部修复汇合后，Step 7 对全部推导单测重新 `run-scope`（同树复用、树变则补跑）；收敛后再取当前树的结果。原始 CVL、每轮差量结果和最终验收结论分别留存；非阻断 Important 未解决也不得被命令端改成通过。
5. 来自外部 bugfix 的「已修复」记录及用例清单按复现路径核对 diff；人工/浏览器用例只标「已修复·待人工验证」，真实执行通过后才可标「已验证」，不把静态结果冒充实测。

**报告处置必须完整**：已修项写 BUG/CVL 回链、原严重度、修复证据和验证范围；已提交写真实 commit SHA，**尚未提交**写“尚未提交 + 账本 `after_hash` 写树证据”，不得伪造 SHA 或用旧 HEAD 冒充本轮修复提交。挂起写具体原因/缺什么/影响；纯优化与非缺陷写不修理由及依据。三类都保留原发现，不把低等级错误藏到建议里。

### Step 7：完成前验证

调用 `superpowers:verification-before-completion`：
- 确认待人工执行的用例清单已列入测试报告（本命令只执行 Sprint 单测，不代做人工/浏览器用例）
- 确认测试报告已生成
- 确认 bug 记录完整
- **本 Sprint 改动侧的完整命令集集中收敛**：前端 lint + 类型检查，不打包；后端编译按 `agents/backend.md`「Step 7: 编译验证」规避会触发前端打包的 lifecycle，不能把 CVL 维度 0 当作后端已编译。仅改动侧、资源受限，保留 `npx --no-install`、改动前基线及原判级。非零退出先分类：代码错误回 Step 6 原实现者，工具/基线不可用记「未执行（原因）」+ Important「本项未核验」，不交代码 bugfix、不记通过。

Step 2.6、修复后、收敛和部署前共用下面围栏。每次依据当前树重新推导并按账本复用或补跑，随后 `verify` 校验完整范围的最新证据；零对应单测只记 Minor，任一实际失败或未核验均不能被其它 PASS 抵消。`SINCE`、`UNIT_RUNNERS_JSON`、`WRITE_SET` 与 `TEST_ENV_ID` 每次从冻结的契约或旧项目等价计划读取，不能换更轻的运行器制造命中。

<!-- acceptance-sprint-unit -->
```bash
EXECUTION_CONTEXT="${EXECUTION_CONTEXT:?从父入参重绑}"
python3 {{AIDP_HOME}}/scripts/execution_policy.py require-action --root . \
  --execution-context "$EXECUTION_CONTEXT" --action related-test || exit $?
# 运行产物落本 Sprint 测试目录（docs/ 不计入账本树指纹），⛔ 不落仓库根：否则输出会改变树指纹，使刚得到的 PASS 立即过期
RUN_SET_FILE="docs/testing/{version}/sprint-{NNN}/sprint-{NNN}-run-set.json"; mkdir -p "$(dirname "$RUN_SET_FILE")"
SCOPE_ARGS=(); for W in "${WRITE_SET[@]}"; do SCOPE_ARGS+=(--write-set "$W"); done
python3 {{AIDP_HOME}}/scripts/test_scope.py --root . --execution-context "$EXECUTION_CONTEXT" --since "$SINCE" \
  --runners-json "$UNIT_RUNNERS_JSON" "${SCOPE_ARGS[@]}" --json \
  > "docs/testing/{version}/sprint-{NNN}/sprint-{NNN}-unit-scope.json" || exit $?
python3 {{AIDP_HOME}}/scripts/test_ledger.py run-scope --root . --execution-context "$EXECUTION_CONTEXT" \
  --scope-file "docs/testing/{version}/sprint-{NNN}/sprint-{NNN}-unit-scope.json" \
  --env-id "$TEST_ENV_ID" --input "docs/design/detail/{version}/_sprint-{NNN}-契约卡.md" \
  > "$RUN_SET_FILE" || exit $?
SCOPE_HASH=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["scope_hash"])' "docs/testing/{version}/sprint-{NNN}/sprint-{NNN}-unit-scope.json") || exit $?
RUN_IDS=$(python3 -c 'import json,sys;print(*json.loads(open(sys.argv[1]).readlines()[-1])["run_ids"])' "$RUN_SET_FILE") || exit $?
RUN_ARGS=()
for R in $RUN_IDS; do RUN_ARGS+=(--run-id "$R"); done
python3 {{AIDP_HOME}}/scripts/test_ledger.py verify --root . --execution-context "$EXECUTION_CONTEXT" --env-id "$TEST_ENV_ID" "${RUN_ARGS[@]}" \
  --scope-file "docs/testing/{version}/sprint-{NNN}/sprint-{NNN}-unit-scope.json" --scope-hash "$SCOPE_HASH"
```

`RUN_SET_FILE` 末行给出 `status/scope_hash/run_ids`。`verify` 必须确认当前完整范围证据有效；`EMPTY` 如实记录无对应单测而允许审查登记，`FAIL` 回 Step 6，未执行/超时记 Important「本项未核验」。部署前只复用已授权的本协议证据，不新增测试、不重跑 CVL；若验收后出现语义改动，仍由 reviewer 查新增 diff。

**测试 PASS 不代表审查完成**。一次真实完整 CVL 及必要的差量 reviewer 已完成、所有错误闭环、报告非空且结论可进入关闭，才执行下面的显式登记；related-test或review未授权时不进入该围栏，按light-context仅消费所需证据。将全部 run_id 登记到同一审查，逐个 `--run-id` 传入，不能只登记最后一套。报告保留原 CVL 结果、各差量证据与调用层最终结论，不改写原始不通过。

<!-- acceptance-record-review -->
```bash
EXECUTION_CONTEXT="${EXECUTION_CONTEXT:?从父入参重绑}"
python3 {{AIDP_HOME}}/scripts/execution_policy.py require-action --root . \
  --execution-context "$EXECUTION_CONTEXT" --action review || exit $?
RUN_SET_FILE="docs/testing/{version}/sprint-{NNN}/sprint-{NNN}-run-set.json"  # 与上一围栏同一路径（每个围栏独立，须重新定义）
SCOPE_HASH=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["scope_hash"])' "docs/testing/{version}/sprint-{NNN}/sprint-{NNN}-unit-scope.json") || exit $?
RUN_ARGS=(); for R in $(python3 -c 'import json,sys; print(" ".join(json.loads(sys.stdin.read().strip().splitlines()[-1])["run_ids"]))' < "$RUN_SET_FILE"); do RUN_ARGS+=(--run-id "$R"); done
python3 {{AIDP_HOME}}/scripts/test_ledger.py record-review --root . --execution-context "$EXECUTION_CONTEXT" \
  --name "{version}-sprint-{NNN}" --env-id "$TEST_ENV_ID" "${RUN_ARGS[@]}" \
  --scope-file "docs/testing/{version}/sprint-{NNN}/sprint-{NNN}-unit-scope.json" --scope-hash "$SCOPE_HASH" \
  --report "docs/testing/{version}/sprint-{NNN}/sprint-{NNN}-test-report.md" \
  --input "docs/testing/{version}/sprint-{NNN}/sprint-{NNN}-unit-scope.json" \
  --input "docs/design/detail/{version}/_sprint-{NNN}-契约卡.md" \
  --input "docs/design/detail/{version}/"
```

登记前按实际审查范围追加需求/计划/受影响四族台账等 `--input`。报告中真实修复 SHA / 尚未提交 after_hash、各套运行器与 run_id 填完、最终落盘后才 record-review；之后不得为补 SHA 改写已绑定报告。登记失败保留旧证据、返回验收未完成，不交 close。


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
  - 各维度结论：{逐维度 Pass / Fail / 不适用 / 未执行（原因），以 SKILL 完整结构化报告为准}
  - 总体结论：{通过 / 不通过，原样取 SKILL 返回结论}
  - 问题清单：{唯一问题编号、严重度、loop 推进与修复归口；非阻断 Important 同样列出}
  - 未核验与交接：{基线/工具环境原因；无人值守返回失败信号，交互式列待核验，不转成代码 bug}

{如有缺陷}
缺陷清单（均位于 docs/bugfix/{version}/）：
- bugfix-{YYYYMMDD}-{user}.md — {问题标题} — P{X}

调用层闭环：{已修 + 真实 SHA/尚未提交写树 hash；挂起原因；不修理由}
差量复核：{reviewer / contract_revision / 实际写集 / 证据}
测试与审查基线：{Sprint 单测 run_id 列表 / 运行器 / reused / env-id / review 名称}

📌 下一步：
- 所有必需证据通过 → /sprint-close {NNN}
- 有未闭环项 → 返回原实现者继续定向修复；外层恢复时 /sprint-test {NNN} --resume-acceptance
- 环境/产品待决 → 回传具体原因，不冒充通过或默认重跑完整验收
```
