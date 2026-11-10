# 执行上下文、动作授权与轻量能力

本片是所有入口的**执行策略单一信源**，同时承载 light 能力配方。策略与 light/formal 身份是两个维度：formal 保留编号、开工、规格、归档及质量证据完整性，但不自动增加测试、审查、文档、部署权限；light 不创建 Sprint、契约卡或替代审批文档。各命令/角色先执行本片，再按授权选择其步骤；未启用的步骤为 `NOT_REQUESTED`，既不是欠账，也不是 PASS。

## 业务目标与动作模型

只完成用户本轮要求的业务结果；目标写“谁在什么条件下得到什么结果”，不以脚本名、文件数或执行了几层流程替代目标。普通开发默认 `implement + static`。下表的组合仅由**本轮用户显式调用**授予；自然语言路由到同名入口、嵌套命令和 formal 身份均不得借用公开组合。

| 用户意图 / 公开入口 | 动作范围 | 不自动追加 |
|---|---|---|
| 普通开发、修复；独立 `/sprint-dev` / `/sprint-bugfix` | `implement`、`static` | tests、review、正式成文 |
| “跑相关测试” | `related-test`；保留父任务已有动作 | full regression、CVL、审查 |
| “代码审查” | `task_scope=review`，仅 `review` | 实现修复、unit、CVL、文档、另跑静态命令 |
| 显式 `/sprint-test` | `static`、`related-test`、`review`、`full-cvl` | 修复实现、文档、live、全回归；review 消费本次 CVL 的审查证据，不另叠一次完整审查 |
| 显式 `/sprint-full`、`/sprint-batch` | development 组合：`implement`、`static`、`related-test`、`review`、`full-cvl`、`document`、`docs-audit` | commit、push、deploy、live、full regression |
| 显式四个文档生成命令 | document+static；含依赖最低生成自检，QR适配见 `reference/SKILL编排层接入.md` | 非Critical语义QR、独立docs-audit |
| 显式 `/version` 规划 | `document`、`static`、`docs-audit` | 发布、提交、部署、代码测试；保留 `--repair-planning`、`--fast` 及已有 QR 缓存 |
| 显式 `/sprint-aiauto-test` | `static`、`live-tests`、`full-regression`；原两条测试职责并行 | 开发修复、提交、部署；自然浏览器请求只授权所指页面/流程，不借用全组合 |
| 显式 autopilot 执行 | 真实explicit-command来源公开development+commit/push/deploy/live-tests/full-regression；已有skip选项收窄 | 安装调度；自然路由/旧配置不能借组合，裸配置向导不执行 |
| “提交、推送、部署” | 在已有任务上分别增加 `commit`、`push`、`deploy` | 迁移演练、部署工具开发、重新回归/审计 |

动作统一使用 kebab-case：`implement/static/document/related-test/review/full-cvl/docs-audit/full-regression/migration-rehearsal/deployment-tool-development/commit/push/deploy/live-tests/equivalent-evidence`。`verification_level` 是这些动作的派生摘要，不是独立授权。部署授权包含直接必要的原部署备份、已授权迁移、现成工具执行与就绪检查；DB 目标及不可逆操作仍守原门。push 只允许观察由本次 push 自动触发的流水线；主动 trigger/retry 必须有 `deploy`。旧 `auto_trigger=true`、机器可用或模板“所有者常驻授权”不构成 grant。

`authorization_source` 只记录真实用户请求或显式选择的持久 policy，保留 request_id、原文/命令和选择证据。不能把模板默认 true 迁移成用户选择，不能伪造来源。已授权动作直接执行，不重复问；未要求的可选动作直接跳过，不逐项询问。缺少完成已授权结果所必需的事实时只返回具体缺口，不把旧 Sprint 收口工程装进新任务。

## 入口、继承与 grant revision

新普通任务默认 light；明确Sprint、version/full/batch/autopilot或真实显式aiauto为formal；自然browser仍light。先核版本归属与工作分支；不从 activeContext、历史计划或规模推断任务身份。`task_id` 由机器生成，`memory/.aidp/entry-contexts/<id>/` 仅存自动证据 JSON，不是新的人工任务卡。

各入口的 `POLICY_ARGS` 在**无父上下文时**按下列配方生成，参数逐项传 argv，不做 shell eval：

```bash
# AUTHORIZATION_SOURCE_JSON 来自本轮真实用户消息；普通开发无需额外grant。
AUTHORIZATION_SOURCE_JSON="${AUTHORIZATION_SOURCE_JSON:-}"
TASK_SCOPE="${TASK_SCOPE:-}"
GRANTED_ACTIONS=("${GRANTED_ACTIONS[@]}")
POLICY_ARGS=()
[ -z "$TASK_SCOPE" ] || POLICY_ARGS+=(--task-scope "$TASK_SCOPE")
# {"kind":"explicit-command","request_id":"实际请求标识","command":"/sprint-test"}
if [ -n "${AUTHORIZATION_SOURCE_JSON:-}" ]; then
  POLICY_ARGS+=(--authorization-source "$AUTHORIZATION_SOURCE_JSON")
fi
for A in "${GRANTED_ACTIONS[@]}"; do POLICY_ARGS+=(--grant "$A"); done
```

显式命令由source让脚本确定task_scope（test/aiauto为test，version为planning，full/batch为development），不强塞development覆盖。自然review必须显式TASK_SCOPE=review；自然单纯测试取test，其余按真实目标选取。新开发任务示例（参数按实际展开）：

```bash
python3 {{AIDP_HOME}}/scripts/entry_context.py resolve --root . \
  --entry sprint-dev --version "{version}" \
  --write-set "{实际写集路径}" --acceptance "{本轮可核验业务结果}" \
  "${POLICY_ARGS[@]}" --json
```

显式命令source.options只记用户真实选项；autopilot既有skip-deploy/skip-aiauto-test/skip-dev仅收窄公开动作，不表示持久授权或安装调度。

消费 stdout `execution_context` 为 `EXECUTION_CONTEXT`，保留 `mode/task_id/identity_hash/revision/since` 与 `task_scope/allowed_actions/verification_level/authorization_source/execution_budget`。同一任务嵌套、重试、压缩恢复只继承路径，不再传 source/grant；不能因 entry=test 重新授予权限。

```bash
EXECUTION_CONTEXT="${EXECUTION_CONTEXT:?入口必须传入机器上下文路径}"
python3 {{AIDP_HOME}}/scripts/entry_context.py resolve --root . \
  --entry "{实际子命令名}" --execution-context "$EXECUTION_CONTEXT" --json
python3 {{AIDP_HOME}}/scripts/entry_context.py route --root . \
  --entry "{实际子命令名}" --execution-context "$EXECUTION_CONTEXT" --phase "{当前阶段}" --json
```

phase 取 `prepare/dev/test/repair/close/route`。消费 `route/actions/authorized_actions/not_requested_actions`；只执行返回动作，不能按下文旧步骤补齐未授权检查。失败立即返回原因。同任务用户后续增加动作时，主流程通过 revise 增加 grant 并更新 revision；写集扩大同样 revise，不手改 JSON、不保留旧证据假装新修订已完成：

```bash
python3 {{AIDP_HOME}}/scripts/entry_context.py revise --root . \
  --execution-context "$EXECUTION_CONTEXT" --grant "{本次新增动作}" \
  --authorization-source "$AUTHORIZATION_SOURCE_JSON" --json
# 扩写集时重复 --write-set 传完整新写集；预算收窄/获准扩大用 --execution-budget JSON。
```

formal 同 Sprint 传同一路径；批次唯一派发点 `fork` 子任务，同父同 Sprint 重试复用子路径。full 无号上下文经原契约门取得真实 Sprint 号后 `bind-sprint`；版本父用 fork，不被子覆盖。两者均继承父授权与共享预算，不能升级权限；light 禁止借此变 formal。

Sprint派发的实际fork围栏见 `/sprint-batch` Step3：重复allow-action仅传父授权∩development，版本交付留父、预算共享；bind-sprint不带allow-action。

## 执行围栏、预算与失败

所有实际动作先核父action并预留资源，包装器已预留则不重复。直接工具/Agent按下方配方；prompt带context/revision/action/剩余budget/真实输入hash/写集/业务验收，派发不新增任务。并行写集不交叉，共享状态主流程串行写。

```bash
EXECUTION_CONTEXT="${EXECUTION_CONTEXT:?父路径}"
ACTION="${ACTION:?当前实际动作}"
RESOURCE="${RESOURCE:?本次实际消耗资源}"
COST="${COST:?预计数量或最长耗时}"
INPUT_HASH="${INPUT_HASH:?从本轮实际输入算得SHA256}"
python3 {{AIDP_HOME}}/scripts/execution_policy.py require-action --root . \
  --execution-context "$EXECUTION_CONTEXT" --action "$ACTION" || exit $?
RESERVATION_FILE=$(mktemp "$(dirname "$EXECUTION_CONTEXT")/reservation.XXXXXX.json") || exit $?
python3 {{AIDP_HOME}}/scripts/execution_policy.py reserve-budget --root . \
  --execution-context "$EXECUTION_CONTEXT" --action "$ACTION" \
  --resource "$RESOURCE" --cost "$COST" --input-hash "$INPUT_HASH" > "$RESERVATION_FILE" || exit $?
# 实际动作结束后据真实结果登记；不是用登记替代执行。
if [ "$RESOURCE" = elapsed_seconds ]; then
  RESERVATION_ID=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["reservation_id"])' "$RESERVATION_FILE") || exit $?
  ACTUAL_SECONDS="${ACTUAL_SECONDS:?执行体monotonic结束减开始的实际耗时}"
  python3 {{AIDP_HOME}}/scripts/execution_policy.py settle-elapsed --root . \
    --execution-context "$EXECUTION_CONTEXT" --reservation-id "$RESERVATION_ID" \
    --elapsed-seconds "$ACTUAL_SECONDS" --json || exit $?
fi
STATUS="${STATUS:?消费实际执行结果}"
ROOT_CAUSE="${ROOT_CAUSE:-}"
EVIDENCE_JSON="${EVIDENCE_JSON:?绑定真实输出与证据路径的JSON}"
python3 {{AIDP_HOME}}/scripts/execution_policy.py record-outcome --root . \
  --execution-context "$EXECUTION_CONTEXT" --action "$ACTION" \
  --status "$STATUS" --input-hash "$INPUT_HASH" \
  --root-cause "$ROOT_CAUSE" --evidence-json "$EVIDENCE_JSON"
```

RESOURCE取scanned_files/selected_tests/processes/agents/retries/elapsed_seconds，COST为数量或最大时限，timeout与预留一致。各资源先预留，动作只执行一次；耗时由执行体开始/结束的time.monotonic差值回传，排队/用户等待不算。保留reservation JSON供跨工具结算，异常未结束保守保留预留，不reset根。预算读resolve/route，跨tick不重置；INPUT_HASH必须由实际输入/命令/环境算SHA256。超额返回BUDGET_EXCEEDED，不扩预算或流程。

业务错误FAIL、工具TOOL_ERROR、环境ENV_UNAVAILABLE、证据不足UNVERIFIED、未请求NOT_REQUESTED分别保留。scope错误不一概开BUG；同根因同inputs不变停止retry，有变化只复验delta且受父预算限制。equivalent-evidence仅显式授权，保留原错误、不求绿。规划QR复用原缓存/移交；同revision/inputs必须真实hash匹配，不建第二清单。

## prepare / dev / repair

1. prepare 读用户需求、相关代码和既有基线；light 不认领已有 Sprint、不重置 activeContext/progress、不写 started，准备完返回。
2. dev/repair 按实际范围复用 backend/frontend 能力与适用 rules。默认完成实现和必要静态检查后即可收尾；TDD、定向测试、review、完整 CVL、文档仅在各自动作已授权时调用。修复保留原身份与起点，已授权实现范围内的真实错误交原实现者；review-only/test-only 只回传发现，不能自行修复。
3. 规模预判与完成复核使用同一 `development_scope.py`、同一冻结上下文；risk/complexity/cost 独立，文件数只表示成本，不能以 >10 files 判 L。风险提示不授予迁移、文档或 heavy 检查：

```bash
EXECUTION_CONTEXT="${EXECUTION_CONTEXT:?必须继承冻结任务路径}"
DEVELOPMENT_FACTS_JSON="${DEVELOPMENT_FACTS_JSON:?从本轮计划或实际业务事实生成JSON}"
python3 {{AIDP_HOME}}/scripts/development_scope.py --root . \
  --execution-context "$EXECUTION_CONTEXT" --facts-json "$DEVELOPMENT_FACTS_JSON" --json
```

`DEVELOPMENT_FACTS_JSON` 是真实 REQ/PAGE/API、语义、配置、架构及破坏性事实；pre 用预计事实，post 用实际事实。消费 `risk_tier/complexity/cost/has_ddl/has_new_table/has_destructive/ddl_unknown/sql_evidence/impact_check_required/scope`。缺基线或 SQL unknown 记需影响核查，不推断无 DDL、不自动转 L 全流程。formal 具体承载见 `incremental-contract.md`。

4. 仅主流程给实际受影响的族经 `alloc_id.py --kind C --count {真实条数} --owner orchestrator --version {version} --scope changes` 取号并串行登记短行，跨族复用 C 号、light 行尾带真实 task_id。无影响不建空册，未要求 tests/review 不登记流程欠账。已确认文档事实漂移可攒批，不因 test/close 开启整套级联；正式成文须 `document`，审计须 `docs-audit`。
5. 用例族实际受影响且未安排实测时，调用 `check_case_ledger_pending.py --root . --version "{version}" --execution-context "$EXECUTION_CONTEXT" --defer --reason "{实际原因}" --json` 保留事实义务；无影响不默认 defer。已授权 live 的正式用例准备经既有入口、受父策略限制；静态 PASS 不冒充用例生成或实测。light 不铸 build、默认不部署。

## static：默认开发可完成

选本任务真正必要的语法/类型/lint/确定性检查，从项目已有命令取 argv，不启动服务或完整打包。以下包装器执行命令并产真实机器证据，`--input` 可重复，必须用具体文件覆盖当前write_set，不能传目录占位：

```bash
python3 {{AIDP_HOME}}/scripts/entry_context.py static --root . \
  --execution-context "$EXECUTION_CONTEXT" --input "{实际文件}" --timeout 30 \
  -- {项目已有静态命令及真实参数}
```

消费返回 `evidence_file`，不是自己写一个 PASS。缺工具、失败、未执行分别如实登记，不能新增另一套审计求绿。`implement + static` 完成无需创建 unit-scope、run-set 或 review 报告。

## test：只执行授权分支

`related-test` 才生成 scope 和运行单测。真实运行器来自项目 `unit_runners` 的 `cwd/argv/inputs/env_id`；`since/write_set` 来自父上下文。命名或 related 选择器沿用 `/sprint-test` Step 2.6。资源变更 JSON/YAML/SQL 不能丢弃；无映射记未分析，不伪造全覆盖。

<!-- light-task-unit -->
```bash
EXECUTION_CONTEXT="${EXECUTION_CONTEXT:?入口必须传入机器上下文路径}"
UNIT_RUNNERS_JSON="${UNIT_RUNNERS_JSON:?读取项目实际测试运行器}"
TEST_ENV_ID="${TEST_ENV_ID:?提供真实环境标识}"
CTX_DIR=$(dirname "$EXECUTION_CONTEXT")
SCOPE_FILE="$CTX_DIR/unit-scope.json"
RUN_SET_FILE="$CTX_DIR/run-set.json"
python3 {{AIDP_HOME}}/scripts/test_scope.py --root . \
  --execution-context "$EXECUTION_CONTEXT" --runners-json "$UNIT_RUNNERS_JSON" --json \
  > "$SCOPE_FILE" || exit $?
python3 {{AIDP_HOME}}/scripts/test_ledger.py run-scope --root . \
  --execution-context "$EXECUTION_CONTEXT" --scope-file "$SCOPE_FILE" \
  --env-id "$TEST_ENV_ID" > "$RUN_SET_FILE" || exit $?
SCOPE_HASH=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["scope_hash"])' "$SCOPE_FILE") || exit $?
RUN_IDS=$(python3 -c 'import json,sys;print(*json.loads(open(sys.argv[1]).readlines()[-1])["run_ids"])' "$RUN_SET_FILE") || exit $?
RUN_ARGS=()
for R in $RUN_IDS; do
  RUN_ARGS+=(--run-id "$R")
done
python3 {{AIDP_HOME}}/scripts/test_ledger.py verify --root . \
  --execution-context "$EXECUTION_CONTEXT" --scope-file "$SCOPE_FILE" \
  --scope-hash "$SCOPE_HASH" --env-id "$TEST_ENV_ID" "${RUN_ARGS[@]}"
```

light 的 run-scope 为 task 范围；formal 为当前 Sprint 范围。原始输出保留，EMPTY/PARTIAL 如实列无对应单测，不造 PASS、不自动建全套测试。已授权修复仅补失效项，targeted 不能代替已要求的最终完整 scope。

`review` 分支读 `agents/reviewer.md`，只读核本轮 diff 与验收标准，报告自动写上下文目录；不生成 unit-scope、不顺带 CVL/文档。`full-cvl` 另获授权时按 `/sprint-test` Step 2 做一次 verify-only，review 消费这次证据及差量发现，不额外叠完整轮。独立审查保留 schema、kind=code-review、`execution_context=entry_context.evidence_identity(ctx)`、覆盖当前write_set的具体文件→SHA256 inputs映射、reviewer/checks/findings与证据。每项检查保留kind/status及非空evidence路径数组；未核验/FAIL不填PASS。只读可结束并保留FAIL；Minor/Suggestion纯改进有reason/evidence可accepted，错误不得借此放行。

同时有 related-test+review 且本轮真实质量检查完成时，才用既有 `test_ledger.py record-review` 绑定 scope/hash、全部 run_ids 和真实报告；review-only 使用 `--review-evidence` 完成，不依赖测试账本。所有错误性发现保留原等级与状态；改进建议可附不修原因，不能为通过而删发现或把工具失败转 BUG。

## close：验证就绪与整任务完成

先check验证，读quality_verdict、ready_for_release、pending_actions；ready不等于交付完成。纯review/test可结束但质量FAIL/UNVERIFIED，不擅修。交付以ready_for_release准入，继续已有授权，不重问/重跑有效证据。

<!-- light-completion -->
```bash
EXECUTION_CONTEXT="${EXECUTION_CONTEXT:?入口传入机器上下文路径}"
STATIC_EVIDENCE="${STATIC_EVIDENCE:?static实际返回的evidence_file}"
python3 {{AIDP_HOME}}/scripts/entry_context.py check --root . \
  --execution-context "$EXECUTION_CONTEXT" --static-evidence "$STATIC_EVIDENCE" --json
```

review-only改传review-evidence；related-test加scope-file/scope-hash/env-id及全部run-id；full-cvl/docs-audit/live-tests等附action-evidence。未要求的检查不造空报告。已要求动作仍有业务授权条件缺失才传pending-authorization的canonical action，具体原因记outcome，不把未请求项列pending。

**已授权交付**：按pending_actions执行commit→push→deploy中的实际请求；每步先过本片动作/预算围栏，commit另过带context的commit_gate（exit5硬禁止），push/deploy按约定31.5。真实失败保留原输出，不自行扩测试/审计或开新任务。每步成功生成独立回执JSON：schema=1、action、status=PASS、execution_context=evidence_identity(ctx)、覆盖当前写集的inputs哈希、checks（含kind/status及非空evidence）；另带实际argv与result{returncode:0,stdout,stderr}，或真实提供方receipt{status,id/url/sha/run_id之一}。receipt.status用真实committed/pushed/deployed等脚本支持值，AUTHORIZED不是已执行。

commit完成示例；push/deploy按实际成功回执追加同形action-evidence：

```bash
EXECUTION_CONTEXT="${EXECUTION_CONTEXT:?父路径}"
STATIC_EVIDENCE="${STATIC_EVIDENCE:?有效证据}"
COMMIT_RECEIPT="${COMMIT_RECEIPT:?实际成功回执路径}"
python3 {{AIDP_HOME}}/scripts/entry_context.py complete --root . \
  --execution-context "$EXECUTION_CONTEXT" --static-evidence "$STATIC_EVIDENCE" \
  --action-evidence "commit=$COMMIT_RECEIPT" --json
```

无交付grant的static-only用同complete命令但不传commit回执。缺已授权回执返回PENDING_ACTIONS，继续当前任务；不得把验证就绪当完成后return。formal使用check并在pending_actions清空、质量满足后继续原编号/关闭/归档门，complete不替代正式关闭。

full-regression用full-evidence与env-id：报告绑定evidence_identity、inputs哈希、action=full-regression、suite-inventory检查/证据、真实ledger_root、全部发现tests、各套name/run_id/command/cwd/tests；逐run核当前环境/输入的full PASS与全集覆盖，不用相关scope或任意shell冒充。

review已授权且有审查基线才review-delta，可信零diff复用；变化只补失效项。static-only不强迫回sprint-test。等价证据仅在equivalent-evidence显式授权下走entry_context equivalent，传原original-run-id、env-id、review-evidence及适用ledger-root；仅脚本支持的原TOOL_ERROR且实际exit0/当前输入一致情形可用。check/complete消费独立equivalent-evidence JSON，保留原失败，业务FAIL不替代。

**light仅在complete.completed=true后return**，汇报quality_verdict及实际交付结果。light不进入Sprint归档、progress/activeContext、自动级联或铸build；用户已要求的commit/push/deploy由上方交付分支完成，不受此身份限制。NOT_REQUESTED如实保留，不把旧Sprint工程塞入本任务。
