> 本片仅供 formal。先按 `{{AIDP_HOME}}/flows/sprint-dev/light-context.md` 核父身份；light 返回对应能力分支，不执行本片。

# sprint-dev · 日常累进契约与并行汇合

> 本片是 `/sprint-dev`、`/sprint-start`、`/sprint-full`、`/sprint-bugfix` 累进路径与 `/sprint-test` 前置汇合的共同权威。先读本片再准备/消费契约。约定 22/24/31.5/34/35/38/41、版本落点及未关闭 Sprint 门继续适用；本片不授权浏览器实测、部署、完整构建或铸 build。

**动作前置**：按 `light-context.md` 的父策略围栏执行本片；document/review/related-test/full-cvl/docs-audit 各自获授权才派发。正式身份和风险档位不授予这些动作。

## 契约卡放行

1. 主流程先按 `{{AIDP_HOME}}/reference/agent-tools.md` 读取项目工作分支偏好，继承或一次性确定 `task_branch`，不为子任务另建分支；再完成既有版本落点与未关闭 Sprint 门，取得全局 Sprint 号，保存口述原文到 `docs/requirements/{version}/产品提供/口述补充-{YYYYMMDD-HHMM}.md`。**先判档、后生成正式文档**，不为判档先跑完整需求 SKILL。
2. 主流程创建 `docs/design/detail/{version}/_sprint-{NNN}-契约卡.md`，唯一写者是主流程。卡是本轮开发规格，不是假装已生成的正式设计/用例，不登记进 `00_索引.md`；正式文档发现型 glob 仍排除 `_*`，开发与验收显式读取卡。
3. **规模同源评估**：开发前与开发后都执行下面命令，冻结同一执行上下文。`DEVELOPMENT_FACTS_JSON` 来自实际需求/页面/API/语义/配置/架构/破坏性事实；pre 填预计值，post 填实际值，不复写 since。

```bash
EXECUTION_CONTEXT="${EXECUTION_CONTEXT:?必须继承冻结任务路径}"
DEVELOPMENT_FACTS_JSON="${DEVELOPMENT_FACTS_JSON:?从本轮计划或实际业务事实生成JSON}"
python3 {{AIDP_HOME}}/scripts/development_scope.py --root . \
  --execution-context "$EXECUTION_CONTEXT" --facts-json "$DEVELOPMENT_FACTS_JSON" --json
```

4. 消费 `risk_tier` 作为 `dev_scale.tier`，保存 `complexity`、`cost`、`sql_evidence`、`ddl_unknown`、`impact_check_required`；`sup_scale.tier` 同步该值并保留原 REQ/PAGE/第三方字段。成本按文件数独立展示，>10 文件不直接抬 L；兼容 ALTER、新表、破坏性与 SQL unknown 分开。unknown 要核影响，不推断无 DDL、不自动启动全套流程。`--dev-scale` 仅表达承载偏好，不绕过已证实的风险/授权门。正式生成传 `--scale={档位}`；无 document 授权只记录事实和最小必要规格，不强制生成六册。


**机器可读身份与放行块**：契约卡必须恰有一个 fenced `aidp-contract` 块，块内是严格 JSON（无注释、无重复键）；示例值按本轮替换：

```aidp-contract
{"version":"V1.2.0","sprint":"001","owner":"alice","contract_revision":1,"dev_scale":"M","approved_revision":1,"status":"approved"}
```

`owner` 是 `developer_identity` 的开发者身份，不是 worker 名；`sprint` 是三位数字字符串；修订是正整数（不能为布尔）；`dev_scale` 是 S/M/L 字符串。主流程完成本节规格与反转门后才写 `status=approved` 且 `approved_revision=contract_revision`。规格修订先递增 `contract_revision`、设 `status=draft` 与 `approved_revision=null`，重新过门后再放行。approved 只证明开发前契约通过，不代表 M 文档已汇合或验收通过。

`/sprint-start` 启动前核块的 version/sprint/owner 与本轮一致；写 activeContext 时明确 `contract_path` 与 `contract_revision: <正整数>`。`/sprint-full` 的 `--resume` 契约恢复路径还须核唯一 active、同用户/版本/Sprint、activeContext 修订等于卡修订且当前修订已批准。缺块、多块、坏 JSON、字段非法或任何身份/修订不符都不能仅凭 exists 放行；存量正式计划路径保持其原证据校验，不把无卡推成契约已批准。

契约卡字段（适用项填实；不适用写理由，不留空）：

| 区域 | 必填内容 |
|---|---|
| 身份与状态 | version、Sprint、owner、contract_revision、dev_scale、口述来源可点击链接；Git 模式的本 Sprint 改动前基线 ref，非 Git 使用既有 local-before 快照并标 `unsupported:vcs-disabled` |
| 需求与验收 | REQ 编号、要实现的行为、AC、排除项、影响范围；沿用既有 REQ 身份，不用局部重号覆盖旧需求 |
| 接口契约 | method/path、请求/响应字段与类型、错误码与文案、鉴权/权限、兼容性；无接口变更也明确写出 |
| DDL | 新表/ALTER/删除与迁移回滚影响、SQL 最终路径；无 DDL 明记无；DB 写授权仍服从约定 38 |
| 决策与受影响结论 | 方案取舍；旧结论→新结论、具体落点、失效/改写/不受影响；口径反转必须回答旧安全结论是否仍成立并当轮补守卫 |
| 执行工作单 | 每个 Task 的 REQ/步骤/AC/依赖、owner、具体 write_set/create_dirs；工作单回传落点由主流程分配，开发者只写自己的文件 |
| 用例义务 | `check_case_ledger_pending.py --prepare` 的 required/deferred 真实读数、正式用例路径或延期原因；契约 AC 不能冒充正式实测用例 |
| test_plan | 保留每套 `cwd`、`env_id`、`inputs`、开发用 `targeted_argv`；新增 `unit_runners`（每个模块的 `cwd/suffixes/argv/env_id/inputs`，字段及选择器规则见 `/sprint-test` Step 2.6）。`/sprint-test` 与部署前复用同一 `unit_runners` 推导结果。版本全量只供真实 autopilot 委派的 `/sprint-aiauto-test`，必须冻结当前版本完整验收清单、必要依赖与带显式选择器的 runners，不能回落 `full_argv` 全仓发现；计划与部署 commit 校验格式见 `{{AIDP_HOME}}/flows/sprint-aiauto-test/phase-2-unit.md`。命令全部取自项目已有测试配置，不造占位命令 |
| 时点 | 开始、契约放行、各分支结束、汇合、验收、可部署时间；卡在验收测试前冻结，验收/可部署时点及 run_id 写独立报告，不回写卡触发自我失效。阻塞契约卡目标≤10分钟，同类 M 全栈无 DDL 回放从口述到可部署目标≤70分钟（现状140分钟的50%）。仅用于定位耗时，不能因超时绕授权或硬门；未做业务回放不得宣称实证，缺证据不编造时间 |
| 汇合证据 | contract_revision、实际文件清单、docs状态与正式产物路径、reviewer契约一致性结果、测试账本证据；未完成项和缺失原因不能删 |

**放行矩阵**：

| 档位 | 开发前 | 开发期间 | 进入 sprint-test 前 |
|---|---|---|---|
| S | 契约字段完整、反转门通过、受影响四族义务已登记 | 代码按契约实现；默认不启动完整文档生成 | 契约与实现汇合；正式文档可继续攒批；required=true 的用例必须先补齐，否则不得声称用例齐备 |
| M | 契约字段完整、接口/DDL/决策已明确、反转门通过、受影响义务已登记 | 代码按写集并行；document 已授权才派 docs 成文 | 已请求的文档/检查按当前修订汇合；未请求项 NOT_REQUESTED，不能伪报成文或阻断单纯开发 |
| L | 已知新表/破坏性/架构事实及必要安全决策先明确；document 已授权时先过正式文档门 | 在已授权范围内开发；真实缺失的业务或安全事实才阻塞 | 验证已要求的交付物与原安全门，不能以 L 自动加 heavy 检查 |

`skip-doc-sync` 不能跳过契约、反转与义务登记；已授权 M/L 文档完成门不能靠该 flag 变成成功；未授权成文记 NOT_REQUESTED。`--cascade-now` 保留为用户/父链显式要求的立即级联，不因同轮 test→close 自动置上。用例是否必须生成由真实实测意图判定，不能为了省文档把 required 改为 false。

## 写集派发

AIDP 主流程直接使用 Agent 工具编排，不调用 `superpowers:subagent-driven-development`。每个派单 prompt 必须先带父 `execution_context/revision/action/execution_budget/input_hash`，再带：`owner`、`contract_path`、`contract_revision`、`dev_scale`、`cascade_mode`、具体 `write_set`（含新增/删除/测试/锁文件）、`create_dirs`、`dependencies`、专属工作单路径、验证范围、Git 权限及已确定的 `branch_policy/task_branch`。**写集无交集**且依赖已交付才并行；未知冲突按有冲突处理，公共配置/生成物有交集改为串行，不能只给目录标签。

- backend/frontend 只写各自代码白名单与工作单；docs Agent 独占分配给它的正式文档写集，按 `sprint-requirements`→`sprint-design`→`sprint-plan`→适用的 `sprint-selftest` 调用，保留每个命令回检。DDL SQL/共享类型等生成物也必须指定唯一写者；backend 消费 SQL 的 Task 须等待 SQL 文件交付，其余独立 Task 可继续，不能因文件尚未生成就记“无 SQL”。**文档生成内部不能并行读写尚未交付的计划**；增量自测不使用仅 fresh 规划支持的 `plan_ref_mode=deferred`。
- 成文配方里的 `check_case_ledger_pending.py --prepare/--complete`、编号预留与 baseline 更新由主流程执行后把读数交 docs；docs 调用的子命令/SKILL若涉及共享状态或 Git，先回报主流程代办，不越过白名单。
- 卡、四族台账、memory、baseline 及 Git index/commit/push **由主流程统一处理**。代码 Agent 检出契约偏差只写各自工作单回传，不改共享台账/文档、不自行重分配编号。docs 的回检子 Agent 只读，修订交 docs 原 Agent；若确需代写，由 docs 释放相应写集后串行交接。
- 主流程确认偏差后修订契约，再重派受影响 Task；旧修订完成回传不能算当前修订通过。口径反转仍执行 Phase 0B.1.3，显式作废旧结论，不能静默覆盖。
- 主流程合并工作单后用 `python3 {{AIDP_HOME}}/scripts/alloc_id.py --kind C --count 5 --owner orchestrator --version {version} --scope changes` 原子预留本批连续编号（`5` 按真实条数替换）；一次变更跨族复用同号，**禁止 grep 最大号自行分配**。读最新台账后由主流程串行写入受影响各族，禁止多个 Agent 并发整文件追加。分配失败停止登记并保留工作单，不能自造编号。
- 默认编排者是唯一 Git 写者，**子 Agent 不自行提交或关闭 Sprint**。用户显式授权 worker 提交时，主流程先暂停其它 Git 写者，串行交接索引所有权和白名单，worker 完成后交回；绝不多人同时 `git add/commit`。主流程汇合后按全部合法写集并集运行 `python3 {{AIDP_HOME}}/scripts/commit_gate.py --quiet --execution-context "$EXECUTION_CONTEXT" --owner orchestrator --allow-path '<具体路径>' --allow-path '<获准目录>/**'`（按并集重复 `--allow-path`，仅精确路径或 `dir/**`）；暂存区外路径 WARN 必须核对归属，不擅自 reset 他人暂存。每次提交先require_action(commit)，再读完整gate JSON；exit5/NOT_AUTHORIZED立即禁止提交，台账欠账不触发自动整套级联。

## 开发与文档汇合

1. 等待各 Agent 实际回传，核对当前契约修订、Task/AC、实际写集、必要静态验证和所有偏差工作单；失败/超时/缺证据不能等同完成。document 已授权的 M 才等 docs 成文；`skip-test` 不取消已授权文档义务，未请求文档无需补齐。S 未要求立即成文时维持四族短行欠账。
2. M 设计/接口默认合册并引用契约卡章节，**调用层将任务档位与输出布局分开**：经 `/sprint-design --scale=M --compact-contract=<契约卡路径> [--unattended]`，内部使用上游已有“目标产出：1 册合并设计”的自然语言能力及 `scale=S` 输出布局；记录 `dev_scale=M / design_output_scale=S`。上游 `scale=M` 原生是三册，不能谎称它支持一册。完整接口/DDL内容、溯源、Critical、机器门和强制专题均不删；有强制独立专题时保留该专题并说明。索引登记真实合册章节。所有消费者显式读取契约与合册，不能只传不存在的 `03_接口设计.md`。
3. 正式补充文档用 `--supplement`；消化既有族台账用 `--ledger-cascade`，由调用层负责把已核验内容合入既有主文档。两者作用域分开，不让新增补充册冒充级联落点；成功落地的义务才能清条，未生成用例继续保留。沿用现有设计/计划/用例回检和增量文档审计，**同修订同产物证据只汇总一次**，不新增审计。
4. **删除 Task 级双完整审查**。实现者保留必要静态自检；related-test 获授权才执行 TDD；review 获授权才派一次独立只读 reviewer 做**契约一致性审查**（Task/REQ/AC、接口、DDL、决策及受影响结论，原检查项不取消）。问题交原实现/docs Agent 修复，再查问题和新 diff；full-cvl 获授权时由 `/sprint-test` 做一次完整质量检查；该次 CVL 可作为 review 证据，无需另跑完整 reviewer，之后只复核 delta。
5. related-test 获授权时开发期执行 TDD 与相关定向验证（`test_ledger.py run --scope targeted`）；汇合、修复收敛及部署前仅在 related-test 已授权时消费 `/sprint-test` Step 2.6 / Step 7 的 Sprint 单测协议与范围证据，**targeted 与 sprint 互不替代**，失败、工具不可用、未执行不能算通过；范围推导与执行协议只在该命令定义。
6. 主流程在卡的“汇合证据”登记上述结果。`/sprint-test` 独立调用也先核此门；已要求而未完成时恢复对应任务；未授权 docs/review 为 NOT_REQUESTED，不擅自恢复。卡无正式用例时明确 deferred；显式实测入口必须补齐正式用例和用例族门后再执行。

## 验收后差量

`/sprint-test` 负责保留一次 CVL 原始完整结果及修复后的复核证据；错误性 Suggestion 保留发现；implement 已授权才按 bugfix 纪律登记 BUG、交原实现 Agent 修复，不能仅因等级是 Suggestion 挂起。只有产品口径/对外承诺未定才待裁决；工具/基线未核验不能改成代码 BUG。CVL 的 `verify-only` 自身不修复、不支持伪造的增量模式，修复调度归 AIDP。

`/sprint-close` 消费本轮验收证据，按授权只核验收后 diff；无有效验收证据或差异无法判定时不能宣称零变化。变动涉及契约则先修订并回相关门，修复与差量复核结果单独留痕，不能覆盖原 CVL 不通过结论。约定 22 义务登记、关闭记录与 Sprint 归档继续保留。
