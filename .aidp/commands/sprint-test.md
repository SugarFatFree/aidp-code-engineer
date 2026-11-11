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

**步骤选择表**：Step 1/2.5 只读取已有本任务用例；新用例成文须 document。Step 2 须 full-cvl，只有 review 时直接用 reviewer 能力后返回；Step 2.6/7 的单测围栏须 related-test；Step 3/4 不执行在线/浏览器动作；独立明确实测走既有 aiauto 入口。Step 5 默认终端与机器证据，不生成日常报告 Markdown。未启用项写 NOT_REQUESTED，不列欠账或 PASS。


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
3. **{NNN}** ← 仅冻结 execution context 中明确绑定的 Sprint；activeContext 只校验同一身份，不作为取号来源

## 前置检查

第一动作 Read `{{AIDP_HOME}}/flows/sprint-dev/incremental-contract.md`，再显式 Read `docs/design/detail/{version}/_sprint-{NNN}-契约卡.md` 和 `memory/{version}/{user}/activeContext.md`。契约卡不走排除 `_*` 的正式文档 glob；既有计划内 Sprint 无卡时保持完整需求/设计/计划门，不得借缺卡降为 S；采用新累进协议却缺卡 → 返回开发补卡，不猜档位。

- **M（document 已授权时）**：检查完整需求、设计、计划及适用用例的真实内容与原有回检；汇合证据必须含当前 `contract_revision`、实际写集、docs路径、docs 完成状态与已授权 review 的真实结果；未授权 review 为 NOT_REQUESTED。任一缺失、仍运行、旧修订或路径仅占位 → 恢复缺失 docs/实现任务，重新汇合通过后才进入 CVL。
- **S**：契约完整、实现与契约一致、受影响四族待成文义务已登记即可进入静态验收；正式正文允许攒批。不得把契约 AC 冒充正式实测用例，不为本次静态验收强启完整文档生成。
- **L / 旧流程**：保留先完整文档、再代码的原有门；需求按 `docs/requirements/{version}/研发需求/{01_研发需求,00_索引,00_研发需求}.md` 兼容布局读取，设计/计划按索引实际路径读，不能只认裸名或硬编码 `03_接口设计.md`。
- 新协议各档均核当前契约修订与实际写集；review 获授权才核 reviewer 结果；变更越过契约/涉及破坏性、版本承诺或部署授权 → 回原安全门，分档不提供豁免。

**正式用例门独立于静态验收**：消费契约卡中 `check_case_ledger_pending.py --prepare` 的真实 required/deferred 读数及外层实测意图，得到 `CASE_REQUIRED=1|0`。有 `--aiauto-test-required` 时必须 required=true；`--skip-aiauto-test` 不能覆盖 required。缺读数先按原调用上下文执行该脚本 prepare，不默认 false。required=true 且用例缺失/用例族事实义务未清 → document 已授权才经 `/sprint-selftest` 补齐并通过 `python3 {{AIDP_HOME}}/scripts/check_case_ledger_pending.py --version {version} --json` 再放行；required=false 可保留 deferred，但报告必须明确实测未完成。Step 1 与 Step 2.5 同样消费该读数。

**测试计划输入**：消费契约卡 `test_plan` 的 `cwd`、`targeted_argv`、`unit_runners`、`env_id`、`inputs` 与授权边界。本 Sprint 单元测试由 `test_scope.py` 从真实改动推导（见 Step 2.6），不读取 `full_argv`，也不以缺清单为由发现全仓测试；related-test 已授权但缺运行器则返回 TOOL_ERROR 与配置缺口，不用 `true` / `echo` / 空命令冒充测试。旧计划内无卡时据现有项目测试配置记录等价运行器。报告逐套列出实际字段与 run_id。

**命令测试账本**：所有命令型验证经 `test_ledger.py` 包装，原 argv 原样传入。开发/修复用 `--scope targeted`；本 Sprint 验收的单测由 `test_scope.py` 推导后经 `run-scope` 逐套记账（`--scope sprint`）。同树、命令、scope、环境及 inputs 的 PASS 复用，targeted 与 sprint 互不替代；环境标识 `TEST_ENV_ID` 来自实际工具链/外部状态，变化则换值，不得硬编码假稳定环境。本命令不启动服务、不打包、不做浏览器实测。只要输入变更就重新计算账本，禁止凭上一次文本“通过”跳过。

## 执行步骤

### Step 1：当前 Sprint 用例与验收范围

读取 `{{AIDP_HOME}}/agents/qa.md`，只核冻结起点、write_set、当前 Sprint 任务/AC 与必要依赖。已有正式用例按 REQ/API/PAGE/用例 ID 精确裁切；不发现或执行全版本、历史回归全集。缺失测试映射交 Step 2.6，如实阻塞，不借此生成整套方案。已授权 document 且存在本任务正式用例义务时，经 `/sprint-selftest {version} --execution-context "$EXECUTION_CONTEXT" [--unattended]` 只补受影响条目；它不能扩大本轮测试范围。formal 保留原规格和归档，日常不另建 testcases/report Markdown。

接口/权限/并发/边界需求仅在本任务涉及时核对；实际在线执行另走明确目标实测。URL 按事实清单 base + 接口 endpoint；不为本命令启动服务。裁切清单、选择依据与未覆盖项记录机器 JSON，后续 Step 2/2.6 使用相同范围。

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


> ★ **独立子 Agent 派发（隔离上下文，不占 /sprint-test 主对话）**：`code-verification-loop` SKILL 已声明「作为更大编排流程的一环被调用时，应把**整个验收循环**作为一个独立子 Agent 派发」——其扫描脚本（`scan_mock_data.py` / `scan_third_party_mock_antipatterns.py` 等）+ 多维度核验都在验收子 Agent 自身上下文内跑，主流程**只接收精简结构化报告**（各维度 Pass / Fail / 不适用 / 未核验（原因）+ 全部发现的唯一问题编号、严重度、`loop 推进`、file:line、证据与修复建议；不得只回传阻塞项或过滤非阻断 Important），脚本 stdout 不污染主上下文。因此本步**不在主对话直接用 `Skill` 工具调**，而是用 `Agent` 工具派一个子 Agent，prompt 为「用 Skill 工具调 `code-verification-loop`，**把下方『调用参数』与『额外提示』两段的全部内容逐项传全**，跑完只回传精简验收结论」。⛔ **别把模板句写成「传入代码/设计/接口路径」**：那会漏掉同步骤要求的 `--third-party-mode` 门控旗标、`webmcp_enabled`/`webmcp_entry_symbols`、`scope_files`/`scope_ids`、被测项目根——漏传的失效方向全是「维度静默落不适用」或「合规代码被判假红」，而不是报错。与 `/sprint-design` Step 1.6 子 Agent 派发同款。

> ⛔ **`--unattended` / `--from-batch` 时 prompt 显式带上非交互上下文**（「任何需要用户裁决的节点一律不询问：记录结论 + 标注待人工确认后返回」）——子 Agent 里无人可答，主流程只会看到「子 Agent 未返回」。

派发的子 Agent 内部以 `Skill` 工具调用 `code-verification-loop`。**skill 内置多维度独立 Agent 检查 + 分级处理（级别以 SKILL 为单一信源）+ 每轮留痕**；命令端按约定 21 不复述维度内容与级别名，只负责传入参数 + 接收验收报告。维度索引见 `{{AIDP_HOME}}/skills/code-verification-loop/SKILL.md`，各维度细则见其 `references/flow-dims-*.md`（`flow-dims-core` / `flow-dims-static-gates` / `flow-dims-quality` / `flow-dims-delegated`），第三方 mock 协议见 `references/third-party-mock-protocol.md`（SKILL 单一信源）。

> 开发期更早的"复杂度+复用"自检由 Frontend Agent Step 4.5 / Backend Agent Step 7.5 承担（作为更早的自检关口，不取代 SKILL 兜底）。

**作用域硬门**：full/batch/autopilot 调用也只当前 task/单 Sprint，CVL 一律走**范围模式**：必传 `scope_files`（当前 task/Sprint 的精确文件清单，相对代码仓库根，含必要依赖）与 `scope_ids`（本任务 REQ/API/PAGE/用例 ID），额外设计/PRD 路径仅作关联证据。范围模式下所有维度只覆盖清单；外部脚本维度 10/12/13/15 不支持文件级范围，上游返回 `未核验（scope-unsupported）`，脚本未下发返回 `未核验（工具缺失）`，均不回退全项目扫描。不启动浏览器、不全量回归；范围模式只返回结构化结果，不落盘 CVL 报告。

**调用参数**（按 SKILL 输入要求传入）：
- **运行模式**：`mode=verify-only`——任务描述写明「代码与文档已按档位汇合；只验收、不修复，单轮完整问题清单交调用方」。CVL **不支持 delta 参数**，不构造 `mode=delta` 或虚构开关。只做这一次完整质量审查；修复后由调用层 reviewer 查问题与新增 diff，**不得宣称 CVL 二次完整通过**。其命令型检查同样经测试账本复用，不能用账本替代语义质量审查。
- **代码路径（`scope_files`）**：当前 task/单 Sprint 写集及必要依赖的精确文件清单，不传 `code/`、项目根或全版本目录；`scope_ids` 同步传本任务需求/接口/页面/用例 ID。
- **设计文档路径**：`docs/design/detail/{version}/` 下真实正式产物，并显式附 `docs/design/detail/{version}/_sprint-{NNN}-契约卡.md` 与 `contract_revision`。S 未成文部分以契约卡为本轮规格、四族台账为待成文义务，明确告诉 CVL 不把预期延期误报成“正式文档已齐备”；SKILL 自身判据和原结论保持原样。
- **接口文档路径**：按契约卡 docs路径/`00_索引.md` 指向的真实接口章节；M 合册直接传合册与契约接口章节，不传不存在的 `03_接口设计.md`。旧布局兼容 `03_接口设计.md` / `接口设计.md`，多分册则传目录与明确文件清单。
- **被测项目根**：仓库根（`.`），仅用于定位 `{{AIDP_HOME}}/scripts/` 下四个外部脚本维度（10 `check_ui_fidelity.py` / 12 `check_upstream_call_log.py` / 13 `check_design_anchor.py` / 15 `check_sibling_family.py`）。范围模式下这些维度按上游规则落「未核验（scope-unsupported / 工具缺失）」，不扫全项目，不是代码缺陷；真正适用的机器半场由调用层按任务文件清单另行只读核对并留证据。
  - **维度 10「UI 还原度确定性检查」** → `<被测项目根>/{{AIDP_HOME}}/scripts/check_ui_fidelity.py`
  - **维度 12「上游调用日志可见性与脱敏」** → `<被测项目根>/{{AIDP_HOME}}/scripts/check_upstream_call_log.py`
  - **维度 13「实现偏离设计」** → `<被测项目根>/{{AIDP_HOME}}/scripts/check_design_anchor.py`
  - **维度 15「同族增量项一致性」** → `<被测项目根>/{{AIDP_HOME}}/scripts/check_sibling_family.py`

- **被验收版本号**：仅**版本级**调用（不传 `scope_files`）的维度 13 才必需传 `{version}`；本命令的范围模式不要求，仍把 `{version}` 写进任务描述便于回链。


- **改动前基线 ref**（SKILL `verify-only` 输出契约明令：维度 0 类型检查的存量基线及维度 4 / 7 / 8 / 14 的一切基线对照**一律取改动前**；未给时 SKILL 回落 `git merge-base HEAD <主干分支>`——**主干开发时 merge-base 就是 `HEAD`**，本次改动被整批吞成「存量」，方向是假绿。故本参数**必须显式传**，⛔ 不得省略交给 SKILL 回落）：
  - `vcs_mode=git`：传**本 Sprint 起点 commit**（`/sprint-dev` 动手前的 HEAD，与 `flows/sprint-dev/postdev-writeback-1.md` X.0.0 变更检测用的 `{sprint-start-sha}` 同一值）。先读取契约卡保存的改动前基线 ref，验证它确为本 Sprint 起点；旧流程无卡时按序解析、取到即停：① 上游编排（`/sprint-full` 等）显式透传的起点 commit；② 本 Sprint 改动全部仍在工作区未提交（本 Sprint 无已提交 commit）→ `HEAD`；③ 当前在特性分支 → `git merge-base HEAD <主干分支>`，**仅当结果 ≠ `HEAD` 才有效**；④ 以上皆不成立 → 按下方「取不到」处置。⛔ 不得用 `HEAD~1` 顶替（多 commit 的 Sprint 会漏掉前面的改动）、⛔ 不得凭感觉挑一个 commit。
  - `vcs_mode=none`：无可检出的改动前代码（`sprint-{NNN}-local-before.json` 只有 sha256、不含旧内容，跑不了改动前的类型检查）→ 一律按「取不到」处置。
  - **取不到时**：prompt 里显式写「改动前基线 ref：无（取不到；⛔ 不得回落 merge-base / 本轮首跑错误数）」，由 SKILL 按其契约把依赖基线的项落「**基线无效，本项未核验**」（`未核验（原因）` 行 + 一条 `Important`「本项未核验」→ 结论 `不通过`）。命令端处置：该类条目**不是代码缺陷**，⛔ 不转写 bugfix（`/sprint-bugfix` 无从修复，只会空转）；在测试报告列为**待人工核验项**（`vcs_mode=none` 记 `unsupported:vcs-disabled`，`git` 模式记「基线无效：未取到 Sprint 起点 commit」），⛔ 不折算为通过、不私自改判 SKILL 结论。**无人值守 / 编排调用必须向上游返回「存在未核验维度 / 不通过」失败信号，附基线缺失或工具环境原因，交上游按失败计数熔断；不能只挂一条待办后返回成功、不能自动制造基线。交互式才列待人工核验项**。

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
  - **★ 维度 4「代码质量检查」之「文案与数据口径一致性」子行的作用域（约定 34 ⑤ 边界，dev/test 期铁律）**：只核**当前 task/单 Sprint 交付物及必要依赖**——当前写集中的代码/设计章节/页面文案 + 与该任务相关的表 E 条目；**绝不扫 `docs/design/detail/全量/`（`/version` 正式发布产物）与 `{prev-version}` 历史全量设计**。dev/test 期这些全量/历史文档仍是"上一次正式发布"的旧口径 = **预期正常态**（发布期 Step 3.3.11 重算），**不报缺陷、不提议处理、不主动询问"全量旧口径要不要处理"**（那是越界，留发布期）。

**业务计数声明核对**：仅核当前任务触达的声明及对应代码/文案。`check_count_claims.py --project-claims` 的目录扫描不能直接作为全库回扫入口；只有真实接口支持同范围才执行，否则沿具体声明人工只读核对并保留证据；不能把未执行脚本称脚本通过。

- 仅验收模式单轮返回：结论（通过 / 不通过）+ 各维度 Pass / Fail / 不适用 / 未核验（原因）；存在任一未核验维度时结论须写「存在未核验维度」，不得写全部通过；`未核验` ≠ 通过、≠ 代码缺陷（不转 bugfix）+ 完整问题清单（唯一问题编号 / 严重度 / `loop 推进` / 维度 / 文件:行 / 问题 / 证据 / 修复建议）；按 SKILL 输出契约汇总，非阻断 Important 不得省略，同一问题按编号去重，不把详情和建议中的引用重复计数。

**与 AIDP 的衔接**：
- **验收结论以 SKILL 返回的结论字段（`通过` / `不通过`）为准**，⛔ 命令端不按 `loop 推进` 自行重判、也不改判。严重度、推进标记和验收结论的关系以 SKILL.md「严重度与 loop 推进」为单一信源；**仅非阻断 Important 仍按 SKILL 返回的 `不通过` 交接**，不能把 loop 可收尾解释为验收通过。**登记 bug 与是否阻断是两件事**：转写时保留唯一问题编号、原严重度、`loop 推进` 与证据，以下完整转写要求不改变 SKILL 返回结论。
- **Critical 与 Important 一律**保留完整发现，代码缺陷逐条登记 BUG；`问题=本项未核验` 且原因为基线/工具不可用 → 保留失败信号和原因，不转代码 BUG。登记时保留唯一问题编号、原严重度、`loop 推进`、file:line、证据与来源回链，非阻断不等于可删除。
- **处置三分**（依据 `/sprint-bugfix`「缺陷处置默认决策纪律」，不调用该命令）：① 当前行为错误，包括**错误性 Suggestion** → 原实现 Agent 当轮修复；② 纯优化、当前行为正确 → 记录不修理由/可选后续建议，不扩范围；③ 产品口径或对外承诺未定 → 记录具体待回答问题、挂起原因与影响，按原授权门返回。工具/基线未核验单列，不用“产品待确认”包住技术缺陷。
- 主流程先用 `python3 {{AIDP_HOME}}/scripts/alloc_id.py --kind BUG --count 1 --owner orchestrator --version {version} --scope bugs` 原子预留 BUG ID，再串行追加 `docs/bugfix/{version}/bugfix-{YYYYMMDD}-{user}.md`；同一 CVL 问题回链已有记录则复用 ID。编号器不可用 → 保留待登记工作单并报阻塞，不自行 grep 最大值或编造编号。子 Agent 不并发写共享记录/卡/memory，不擅自提交。
- 原始 CVL 结论写入报告后保留不变；即使原结果 `通过`，错误性 Suggestion 仍须进入 Step 6。调用层修复后的验收结论另列，全部证据收敛才登记 review baseline 并交 close，不能直接用首轮 CVL 通过跳过后续验证。

### Step 2.5：正式用例适用性

只复核 Step 1 裁切出的当前任务用例，不重扫全版用例册。人工/浏览器用例保留“未实测”；存在性不代表通过。`CASE_REQUIRED` 的文档义务与相关单测独立，不能把正式用例 deferred 解释为单测不执行。纯文档不适用必须给具体文件与没有可测行为的依据；代码/运行配置变化却没有测试映射属于未核验。

### Step 2.6：本 Sprint 单元测试（范围与执行协议唯一信源）

输入固定为 execution context 的起点到当前树的实际改动（包含提交、暂存、未暂存、新文件、删除），按本 task/单 Sprint `write_set` 归属裁切，再加入验收依赖。其它并行任务和历史改动不纳入。起点与 Step 2 及 postdev-writeback X.0.0 相同；不能只用修复前 HEAD 取代 Sprint 起点。

`test_plan.unit_runners` 是 JSON 数组：每项含项目相对 `cwd`、测试后缀 `suffixes`、原始 `argv` 模板、`env_id` 和 root 相对的 `inputs`。按实际项目配置登记；例如 Python runner 可为 `{"cwd":"code/backend","suffixes":[".py"],"argv":["python3","-m","pytest","{tests}"],"env_id":"python-project","inputs":["code/backend/pyproject.toml"]}`（路径与参数须换为真实项目值）。

- `mode=named` 默认按模块目录及命名映射：改动测试自身、Java `FooTest`、前端 `foo.spec.*` / `foo.test.*`、Python `tests/test_x.py`；argv 必须含独立 `{tests}` 或类名选择器 `{test_classes}`，禁止无选择器的命令。路径转换为 runner 的 cwd 相对路径，同名模块不得串选。
- `batch` 明确表示运行器能否合批；默认仅已知安全的 pytest/unittest/Jest/Vitest/Maven 选择器合批，`python {tests}` 仍逐文件。`resources` 映射真实资源到 consumer/test（如 `{"config/x.yaml":["src/consumer.py","tests/test_x.py"]}`）；JSON/YAML/SQL 变化不得丢弃。消费 `selection.proven/conservative/unanalysable` 与 dependencies 原因，未分析不冒充覆盖。
- 项目已使用框架 related 能力时，登记 `mode=related`，通过 `{sources}` 向已有 Jest `--findRelatedTests` / Vitest `related` 命令传入源码范围；实际命令仍来自项目测试配置。
- 主流程按 Step 7 的 **acceptance-sprint-unit** 围栏推导并执行。`test_scope.py` 输出映射、运行 argv、未匹配项与 `scope_hash`；`run-scope` 从 Git 和写集重新推导核对，不信任手改的清单。测试命令由脚本消费，不让执行体临时挑选。
- `FAIL`：先区分业务断言与工具/运行器失败；仅已证实业务错误登记 BUG，且 implement 已授权才交 Step 6。`UNVERIFIED`：工具缺失、超时、输入或运行器缺失逐项记「未核验（原因）」+ Important「本项未核验」，不当代码 BUG、不算通过。
- 无 runner、无对应测试或部分覆盖均 `UNVERIFIED`，逐项说明覆盖缺口，阻塞完整通过；不能记 PASS/NOT_REQUESTED。仅确无可测行为才 `NOT_APPLICABLE`，机器 `applicability` 必须含具体 `reason/paths`；纯文档不能只凭扩展名判定。
- 同 revision、同树、命令、环境与 inputs 的真实 hash 匹配才复用 PASS。命名映射只是选测种子，不能证明测试独立：跨树继承还须校验本地传递依赖，跨模块共享源码同样参与；动态或无法解析的依赖保守补测并记录原因。未受影响项才可继承原证据，报告标明来源、依赖清单与判据，不冒充本树重新执行。共同输入/环境变化使相关证据失效。

无 Git / 起点无效时如实记「本项未核验」，延续 Step 2 的基线缺失处置，不构造起点或回落扩大范围。Step 5 报告必须包含每个改动→测试映射、实际 argv/cwd/env_id、通过/失败/未执行及原因、无对应单测清单、范围 hash 与 run_id。

### Step 3：在线接口测试边界

在线结果不参与静态验收结论；最终发布仍须独立通过部署与浏览器实测门。本命令不调用 `api-tester`、不发在线测试请求。即使父 autopilot 含 live-tests，也只消费当前开发测试范围；明确目标实测经独立 `/sprint-aiauto-test`，不得把父版本动作下放当前 Sprint。

### Step 4：浏览器测试边界

不驱动浏览器、不顺带整版验收。独立明确实测按项目记忆“AI 测试入口前置规则”路由；缺 AI执行报告时沿既有 `/sprint-autopilot --skip-dev` 受限交接，不附带开发、提交、推送或部署。只有真实 autopilot 委派、version/build/验收基线/完整清单齐备才做当前版本全量，详见 `flows/sprint-aiauto-test/phase-2-unit.md`。

### Step 5：真实结果与终端输出

日常不生成 `sprint-*-test-report.md` / `api_test_report.md`。在原 execution context 目录保留机器 JSON/日志：本 task/单 Sprint 的改动→测试映射、scope_hash、argv/cwd/env_id、run_ids、复用来源、静态/审查适用结论、失败/缺工具/覆盖缺口及证据。formal 原规格和归档照常；用户明确要求报告才另写。

终端区分 task/Sprint/version 通过与 `NOT_APPLICABLE`、未执行、FAIL、阻塞；通过当前 Sprint 不代表版本通过。审查缺陷与纯优化分别保留，测试/静态通过不代替未实测结果。

### Step 6：原实现者当轮修复与差量复核

1. 按 Step 2 的 BUG ID、根因/复现证据与具体写集，把错误交回**原实现 Agent**；docs 问题交原 docs Agent。仅 implement 获授权才修复，related-test 获授权才写/跑复现测试；否则只回传具体发现；不新起 `/sprint-bugfix`，不把 CVL 切回 loop。原 Agent 已结束可恢复其上下文；确实不可恢复时主流程记录原因并显式移交原工作单、契约与写集，不能重开 Sprint。契约变更先修订 `contract_revision`，重新过受影响的分档汇合/授权门。
2. 修复后重新消费 Step 2.6 的完整范围并执行 Step 7 围栏；脚本只补跑受影响运行项，未变证据可追溯复用。主流程串行回填 BUG 状态、修复文件与实际 `run_id/status/reused`；不能用实现者随意选的 targeted PASS 替代 Sprint 范围证据。
3. review 已授权时，独立只读 reviewer 复核**原问题 + 修复新增 diff + 受影响契约/调用点**，保留修订、实际写集、复核判据、证据与结论。它是调用层差量复核，不是 CVL 的第二次完整验收。原问题未覆盖、回归失败或新错误 → 返回原实现 Agent；每轮定向验证，不每轮全量。同根因同 inputs 无变化立即停止重试；父预算耗尽或真实授权/环境阻塞 → 返回具体事实与已授权 scope，不能标通过。
4. 全部修复汇合后，Step 7 对全部推导单测重新 `run-scope`（同树复用、树变则补跑）；收敛后再取当前树的结果。原始 CVL、每轮差量结果和最终验收结论分别留存；非阻断 Important 未解决也不得被命令端改成通过。
5. 来自外部 bugfix 的「已修复」记录及用例清单按复现路径核对 diff；人工/浏览器用例只标「已修复·待人工验证」，真实执行通过后才可标「已验证」，不把静态结果冒充实测。

**报告处置必须完整**：已修项写 BUG/CVL 回链、原严重度、修复证据和验证范围；已提交写真实 commit SHA，**尚未提交**写“尚未提交 + 账本 `after_hash` 写树证据”，不得伪造 SHA 或用旧 HEAD 冒充本轮修复提交。挂起写具体原因/缺什么/影响；纯优化与非缺陷写不修理由及依据。三类都保留原发现，不把低等级错误藏到建议里。

### Step 7：完成前验证

调用 `superpowers:verification-before-completion`：
- 确认人工/浏览器用例如实标未实测；本命令只执行当前 task/单 Sprint 单测
- 确认机器证据与终端结果完整；无需日常报告 Markdown
- 确认 bug 记录完整
- **本 Sprint 改动侧的完整命令集集中收敛**：前端 lint + 类型检查，不打包；后端编译按 `agents/backend.md`「Step 7: 编译验证」规避会触发前端打包的 lifecycle，不能把 CVL 维度 0 当作后端已编译。仅改动侧、资源受限，保留 `npx --no-install`、改动前基线及原判级。非零退出先分类：代码错误回 Step 6 原实现者，工具/基线不可用记「未核验（原因）」+ Important「本项未核验」，不交代码 bugfix、不记通过。

Step 2.6、修复后、收敛和部署前共用下面围栏。每次依据当前树重新推导并按账本复用或补跑，随后 `verify` 校验完整范围的最新证据；零对应测试也属未核验，除有具体依据的 NOT_APPLICABLE；任一实际失败或未核验不能被其它 PASS 抵消。`SINCE`、`UNIT_RUNNERS_JSON`、`WRITE_SET` 与 `TEST_ENV_ID` 每次从冻结的契约或旧项目等价计划读取，不能换更轻的运行器制造命中。

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

`RUN_SET_FILE` 末行给出 `status/scope_hash/run_ids`。`verify` 必须确认当前完整范围证据有效；无对应单测为 `UNVERIFIED` 并阻塞完整通过，`FAIL` 回 Step 6，未执行/超时记 Important「本项未核验」。部署前只复用已授权的本协议证据，不新增测试、不重跑 CVL；若验收后出现语义改动，仍由 reviewer 查新增 diff。

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
  --report "${REVIEW_EVIDENCE:-docs/testing/{version}/sprint-{NNN}/sprint-{NNN}-test-report.md}" \
  --input "docs/testing/{version}/sprint-{NNN}/sprint-{NNN}-unit-scope.json" \
  --input "docs/design/detail/{version}/_sprint-{NNN}-契约卡.md" \
  --input "docs/design/detail/{version}/"
```

`REVIEW_EVIDENCE` 指向本轮真实审查证据（日常为 execution context 内机器 JSON；仅用户要求时才为 Markdown 报告），默认路径只是兼容占位，不要求日常生成该 Markdown。登记前按实际审查范围追加需求/计划/受影响四族台账等 `--input`。报告中真实修复 SHA / 尚未提交 after_hash、各套运行器与 run_id 填完、最终落盘后才 record-review；之后不得为补 SHA 改写已绑定报告。登记失败保留旧证据、返回验收未完成，不交 close。


### Step 8：更新状态

更新 `memory/{version}/{user}/activeContext.md`：
- 在「子迭代记录」中追加测试阶段的 Round 记录
- 在「待处理 Bugfix」中列出新发现的问题
- 更新「当前工作焦点」

## 输出

```
✅ /sprint-test 完成（{version} / Sprint-{NNN} 测试阶段）

📋 机器证据：当前 execution context 的 scope/run-set/审查 JSON（日常不生成测试报告 Markdown）

测试结果：
- 总用例数：{N}
- 通过：{N} ✅
- 失败：{N} ❌
- 新增缺陷：{N} 个

code-verification-loop 验收结果：
  - 各维度结论：{逐维度 Pass / Fail / 不适用 / 未核验（原因），以 SKILL 完整结构化报告为准}
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
