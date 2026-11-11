# 执行上下文、动作授权与轻量能力

本片是**执行策略单一信源**与 light 配方。formal 保留编号、开工、规格、归档，不扩大动作授权；light 不建 Sprint/卡片/审批文档。各入口先按本片选步骤；可选未请求为 NOT_REQUESTED，不是欠账或 PASS。

## 业务目标与动作模型

目标写可核验的业务结果，不以脚本名、文件数或流程层数替代。普通开发/修复默认 `implement + static + related-test`，自动进入 `/sprint-test` → 必要修复/复验 → 终端结果，无需另问是否跑单测。仅本轮真实明确的只分析、只修改或 skip 请求可收窄；不能以 static-only 宣称开发完整完成。下表公开组合须本轮显式调用；自然路由/嵌套/formal不借组合。

| 用户意图 / 公开入口 | 动作范围 | 不自动追加 |
|---|---|---|
| 普通开发、修复；独立 `/sprint-dev` / `/sprint-bugfix` | `implement`、`static`、`related-test` | review、CVL、正式成文、浏览器、全版本 |
| “跑相关测试” | `related-test`；保留父任务已有动作 | full regression、CVL、审查 |
| “代码审查” | `task_scope=review`，仅 `review` | 实现修复、unit、CVL、文档、另跑静态命令 |
| 显式 `/sprint-test` | `static`、`related-test`、`review`、`full-cvl` | 修复实现、文档、live、全回归；review 消费本次 CVL 的审查证据，不另叠一次完整审查 |
| 显式 `/sprint-full`、`/sprint-batch` | development 组合：`implement`、`static`、`related-test`、`review`、`full-cvl`、`document`、`docs-audit` | commit、push、deploy、live、full regression |
| 显式四个文档生成命令 | document+static；含依赖最低生成自检，QR适配见 `reference/SKILL编排层接入.md` | 非Critical语义QR、独立docs-audit |
| 显式 `/version` 规划 | `document`、`static`、`docs-audit` | 发布、提交、部署、代码测试；保留 `--repair-planning`、`--fast` 及已有 QR 缓存 |
| 独立 `/sprint-aiauto-test` / 明确浏览器实测 | 仅明确目标的 `static`、`live-tests`；自然语言浏览器/页面请求只授权所指页面或流程的 live-tests，不借用 autopilot 版本全量组合 | 全版本、开发修复、提交、推送、部署 |
| 显式 autopilot 执行 | 真实来源的 development+commit/push/deploy/live-tests；仅真实委派 aiauto 且当前版本清单完整才 full-regression | test-only/`--skip-dev` 不含 implement/commit/push/deploy；裸向导不执行，不安装调度 |
| “提交、推送、部署” | 在已有任务上分别增加 `commit`、`push`、`deploy` | 迁移演练、部署工具开发、重新回归/审计 |

动作键：`implement/static/document/related-test/review/full-cvl/docs-audit/full-regression/migration-rehearsal/deployment-tool-development/commit/push/deploy/live-tests/equivalent-evidence`。`verification_level` 仅为派生摘要。部署授权包含按用户频率策略执行或复用的既有备份、已授权迁移、现成工具与就绪检查；不能以迁移/快照另造备份例外。DB目标及不可逆操作仍守原门。push 只允许观察由本次 push 自动触发的流水线；主动 trigger/retry 必须有 `deploy`。旧 `auto_trigger=true`、机器可用或模板“所有者常驻授权”不构成 grant。

`authorization_source` 保留真实 request_id、原文/命令与显式持久选择；模板true不当grant。已授权直接做，未请求可选项跳过；缺事实报缺口。

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
POLICY_ARGS=("${POLICY_ARGS[@]}")  # 当前入口原样传入
python3 {{AIDP_HOME}}/scripts/entry_context.py resolve --root . \
  --entry sprint-dev --version "{version}" \
  --write-set "{实际写集路径}" --acceptance "{本轮可核验业务结果}" \
  "${POLICY_ARGS[@]}" --json
```

`authorization_source` 的 `text/request_id` 取真实请求；限制用 `restriction=analysis-only|modify-only|skip-verification` 或 `skip_actions:["related-test"]`，持久 policy 还须 `user_selected`。`source.options` 只记真实选项。父 full/batch 内部 `skip-test` 只是把测试交外层，不生成用户跳过依据；显式用户 skip 才限制完成，记 `SKIPPED_BY_REQUEST/LIMITED`，不称完整开发通过。

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
EXECUTION_CONTEXT="${EXECUTION_CONTEXT:?当前任务}"
AUTHORIZATION_SOURCE_JSON="${AUTHORIZATION_SOURCE_JSON:?本轮真实请求}"
python3 {{AIDP_HOME}}/scripts/entry_context.py revise --root . \
  --execution-context "$EXECUTION_CONTEXT" --grant "{本次新增动作}" \
  --authorization-source "$AUTHORIZATION_SOURCE_JSON" --json
# 当前工作写集用 --replace-write-set 配合完整 --write-set 清单细化；保留原授权/历史/已用预算。
# 预算收窄或已获准扩大才用 --execution-budget JSON；不为换范围重建任务。
```

formal同Sprint复用路径；批次只在派发点fork，重试复用子路径。full 无号上下文经原契约门取得真实 Sprint 号后 `bind-sprint`；版本父用 fork，不被子覆盖。两者均继承父授权与共享预算，不能升级权限；light 禁止借此变 formal。

Sprint派发的实际fork围栏见 `/sprint-batch` Step3：重复allow-action仅传父授权∩development，版本交付留父、预算共享；bind-sprint不带allow-action。

## 执行围栏、预算与失败

所有实际动作先核父action并预留资源，包装器已预留则不重复。直接工具/Agent按下方配方；prompt带context/revision/action/剩余budget/真实输入hash/写集/业务验收，并行写集不交叉，共享状态主流程串行写。

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

RESOURCE取scanned_files/selected_tests/processes/agents/retries/elapsed_seconds。scanned_files计内容读取次数；static/run-scope已预留的不重复扣费。monotonic计真实耗时，仅未使用预留可返。预算跨tick保留；超额按verification-inputs核范围/缓存/缺口。

FAIL/TOOL_ERROR/ENV_UNAVAILABLE/UNVERIFIED/NOT_REQUESTED分别保留，不把scope错误都开BUG。同根因同inputs停止retry；变化只复验delta且受预算限制。equivalent-evidence须显式授权并保留原错误。规划QR同revision/inputs真实hash匹配才复用，不建第二清单。

## prepare / dev / repair

1. prepare 读用户需求、相关代码和既有基线；light 不认领已有 Sprint、不重置 activeContext/progress、不写 started，准备完返回。
2. dev/repair 按实际范围复用 backend/frontend 与 rules，完成实现、必要静态检查后自动调用 `/sprint-test --execution-context "$EXECUTION_CONTEXT" [--unattended]`，执行本片 test 能力；真实失败交原实现者修复并复验（调 `bugfix` SKILL 传 `report_mode=evidence-only`，见 `reference/skills.md`），随后 close 终端收口。保留同 task/起点/写集；不借子入口加 review/CVL/文档，无需单测确认；review/test-only 只回传发现。
3. 规模预判与完成复核使用同一 `development_scope.py`、同一冻结上下文；risk/complexity/cost 独立，文件数只表示成本、不判 L。风险提示不授予迁移、文档或 heavy 检查：

```bash
EXECUTION_CONTEXT="${EXECUTION_CONTEXT:?必须继承冻结任务路径}"
DEVELOPMENT_FACTS_JSON="${DEVELOPMENT_FACTS_JSON:?从本轮计划或实际业务事实生成JSON}"
python3 {{AIDP_HOME}}/scripts/development_scope.py --root . \
  --execution-context "$EXECUTION_CONTEXT" --facts-json "$DEVELOPMENT_FACTS_JSON" --json
```

`DEVELOPMENT_FACTS_JSON` 是真实 REQ/PAGE/API、语义、配置、架构及破坏性事实；pre 预计、post 实际。消费 `risk_tier/complexity/cost/has_ddl/has_new_table/has_destructive/ddl_unknown/sql_evidence/impact_check_required/scope`。缺基线或 SQL unknown 记需影响核查，不推断无 DDL、不自动转 L。formal 见 `incremental-contract.md`。

4. 仅主流程给实际受影响的族经 `alloc_id.py --kind C --count {真实条数} --owner orchestrator --version {version} --scope changes` 取号并串行登记短行，跨族复用 C 号、light 行尾带真实 task_id。无影响不建空册，未要求 tests/review 不登记流程欠账。已确认文档漂移可攒批，不因 test/close 开整套级联；正式成文须 `document`，审计须 `docs-audit`。
5. 用例族实际受影响且未安排实测时，调用 `check_case_ledger_pending.py --root . --version "{version}" --execution-context "$EXECUTION_CONTEXT" --defer --reason "{实际原因}" --json` 保留事实义务；无影响不默认 defer。已授权 live 的正式用例准备经既有入口、受父策略限制；静态 PASS 不冒充用例生成或实测。light 不铸 build、默认不部署。

## static：按项目工具链验证

先 Read `{{AIDP_HOME}}/flows/sprint-dev/verification-inputs.md`，执行其中的只读 `plan-validation`，再按实际项目配置选择检查。该片统一定义输入细化、真实读取成本、缓存与结果摘要；不从旧宽目录展开无关文件，不以哈希代替验证。消费实际命令产出的 `evidence_file`，缺工具/失败/未执行如实保留。普通static不创建unit-scope、run-set或review报告；单测另按授权进入下节。

## test：只执行授权分支

`related-test` 才生成 scope 和运行单测。真实运行器来自项目 `unit_runners` 的 `cwd/argv/inputs/env_id`；`since/write_set` 来自父上下文。命名或 related 选择器沿用 `/sprint-test` Step 2.6。JSON/YAML/SQL变更无映射须记未核验。

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

light 为 task，formal 为单 Sprint；full/batch/autopilot 开发子任务也守同一边界。static/review/CVL 若执行，仅该写集及必要依赖，不随带浏览器或全版本。缺测试/runner、未覆盖项、工具缺失均 `UNVERIFIED` 并阻塞通过；纯文档须 `applicability={status:NOT_APPLICABLE,reason:具体依据,paths:[实际文件]}`，不能仅凭后缀或空集合判不适用。修复只补失效项，同内容证据复用，最终核完整当前 scope。

`review` 分支读 `agents/reviewer.md`，只读核本轮 diff 与验收标准，报告自动写上下文目录；不生成 unit-scope、不顺带 CVL/文档。`full-cvl` 另获授权时按 `/sprint-test` Step 2 做一次 verify-only，review 消费这次证据及差量发现，不额外叠完整轮。独立审查保留 schema、kind=code-review、`execution_context=entry_context.evidence_identity(ctx)`、覆盖当前write_set的具体文件→SHA256 inputs映射、reviewer/checks/findings与证据。每项检查保留kind/status及非空evidence路径数组；未核验/FAIL不填PASS。只读可结束并保留FAIL；Minor/Suggestion纯改进有reason/evidence可accepted，错误不得借此放行。

同时有 related-test+review 且本轮真实质量检查完成时，才用既有 `test_ledger.py record-review` 绑定 scope/hash、全部 run_ids 和真实报告；review-only 使用 `--review-evidence` 完成，不依赖测试账本。所有错误性发现保留原等级与状态；改进建议可附不修原因，不能为通过而删发现或把工具失败转 BUG。

## close：验证就绪与整任务完成

先check验证，读quality_verdict、ready_for_release、pending_actions；ready不等于交付完成。纯review/test可结束但质量FAIL/UNVERIFIED，不擅修。交付以ready_for_release准入，继续已有授权，不重问/重跑有效证据。

默认开发先执行以下 `check`；交付回执齐备后以同一证据改用 `complete`。每个独立围栏重新从当前任务机器结果构造参数，不依赖前一Bash的变量：

<!-- light-completion -->
```bash
EXECUTION_CONTEXT="${EXECUTION_CONTEXT:?当前任务路径}"
STATIC_EVIDENCE="${STATIC_EVIDENCE:?static实际evidence_file}"
TEST_ENV_ID="${TEST_ENV_ID:?本轮真实环境标识}"
CTX_DIR=$(dirname "$EXECUTION_CONTEXT")
SCOPE_FILE="$CTX_DIR/unit-scope.json"
RUN_SET_FILE="$CTX_DIR/run-set.json"
SCOPE_HASH=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["scope_hash"])' "$SCOPE_FILE") || exit $?
RUN_IDS=$(python3 -c 'import json,sys; print(*json.loads(open(sys.argv[1]).readlines()[-1])["run_ids"])' "$RUN_SET_FILE") || exit $?
RUN_ARGS=()
for R in $RUN_IDS; do RUN_ARGS+=(--run-id "$R"); done
python3 {{AIDP_HOME}}/scripts/entry_context.py check --root . \
  --execution-context "$EXECUTION_CONTEXT" --static-evidence "$STATIC_EVIDENCE" \
  --scope-file "$SCOPE_FILE" --scope-hash "$SCOPE_HASH" --env-id "$TEST_ENV_ID" "${RUN_ARGS[@]}" --json
```

只有真实限制source取消related-test才不传scope；纯文档NOT_APPLICABLE仍传其scope依据。review-only传review-evidence；full-cvl/docs-audit/live-tests等追加真实action-evidence。未要求的检查不造空报告，不把未请求项列pending。

**已授权交付**：只做尚未完成的commit→push→deploy，每步核动作/预算；commit用带context的commit_gate（exit5禁止），push/deploy按约定31.5。真实成功回执用 `--action-evidence "commit=<回执路径>"`（push/deploy同形）传check/complete；无交付grant不传回执。不能用AUTHORIZED代替实际argv/result或提供方receipt，不重放已成功动作，不为日志写部署Markdown/追加提交，不因仅SHA变化全重验。缺回执返回PENDING_ACTIONS，继续父任务。formal继续原关闭归档门，complete不替代正式关闭；受限请求可action_completed，仍非development_completed。

full-regression仅真实autopilot经 `fork-test-build --manifest` 委派的当前version/build；清单与基线缺失阻塞，禁止project-wide/system-wide/历史全集和缺清单fallback。真实调用见 `flows/sprint-aiauto-test/phase-2-unit.md`。full-evidence逐run核环境/inputs、完整当前版本测试及必要依赖，不用相关scope冒充。

review已授权且有审查基线才review-delta，可信零diff复用；变化只补失效项。真实只分析/只修改/skip受限返回，不冒充完整开发通过。等价证据仅在equivalent-evidence显式授权下走entry_context equivalent，传原original-run-id、env-id、review-evidence及适用ledger-root；仅脚本支持的原TOOL_ERROR且实际exit0/当前输入一致情形可用。check/complete消费独立equivalent-evidence JSON，保留原失败，业务FAIL不替代。

**终端收口**消费 `completed/action_completed/development_completed/quality_verdict/finalization_status`，标明 task/Sprint/version 范围，分别列 PASS、具体不适用、未执行、FAIL、阻塞；LIMITED/跳过非完整开发通过。日常不写报告 Markdown，自动 JSON/日志留原证据目录；formal保原规格与归档。light不创建Sprint、编号、卡片、成套文档、不认领历史Sprint或铸build。
