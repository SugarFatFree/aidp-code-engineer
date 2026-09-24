# {项目名称} — 自动化测试执行报告

> 结构固定,不得裁剪章节。**二、测试结果汇总**章(2.1~2.7)由 `python3 <SKILL_DIR>/scripts/gen_report.py <round目录> --md` 聚合填充;**一、概况**与**三、结论**由子 Agent 撰写(脚本不产出这两章)。
> ⚠️ **「由子 Agent 撰写」≠「可以凭判断填」:** 概况里加粗的**环境事实行**（判据 = `assets/env-facts-schema.json` 里配了 `XSource` 的全部字段，**别在这里写死条数**——字段会增，写死必腐化）是**照抄** `round-{M}/env-facts.json` 的机械动作,不是判断性内容;真正属判断性的是三、结论与概况其余行。

## 一、测试概况

| 项 | 内容 | 来源 |
| :- | :- | :- |
| 项目名 | {项目名称} | — |
| 版本 / Build / 轮次 | V{x} / build-{N} / round-{M} | — |
| 被测端 + 驱动 | {端} / {driver 实际取值,见结果 JSON 的 driver 字段} | — |
| 测试类型 | 全量 / 增量 | — |
| 测试范围 | {模块清单} | — |
| 依据 | 用例来源 `{路径}`;自测方案 `{路径}`（若有） | — |
| 执行方式 | 无人值守自动化(auto-test-runner) | — |
| 执行起止 | {开始时间} ~ {结束时间} | — |
| **渲染模式** | {照抄 env-facts.json 的 renderMode} | {照抄 renderModeSource} |
| **浏览器/客户端版本** | {照抄 browserVersion} | {照抄 browserVersionSource} |
| **viewport** | {照抄 viewport} | {照抄 viewportSource} |
| **是否复用已有实例** | {照抄 reusedInstance} | {照抄 reusedInstanceSource} |
| **被测 URL** | {照抄 testUrl} | {照抄 testUrlSource} |
| **登录角色** | {照抄 loginRole} | {照抄 loginRoleSource} |
| **执行路径** | {照抄 executionPath:subagent / inline / subagent→inline} | {照抄 executionPathSource} |
| **数据源归属** | {照抄 datasourceOwnership:verified / mismatched / unverified / not-applicable} | {照抄 datasourceOwnershipSource} |

> **★加粗的八行是「环境事实类」字段,唯一数据源是 `round-{M}/env-facts.json`(环境准备阶段取证落盘)。值与「来源」列都**逐行照抄**该文件,不得改写、不得省略、不得填模板默认或意图推断值**;取不到的照写「未取到(原因)」。**这八行的「来源」列必须落五类枚举**(见 `references/execution-methodology.md` 第十节 10.2),上面这些非加粗行不是环境事实、来源列填 `—` 即可。⚠️ **「被测端 + 驱动」行的 driver 取值虽照抄结果 JSON,但它在 `env-facts.json` 里同样是带 `driverSource` 的事实字段**——两处须一致,冲突以 `env-facts.json` 为准。
> 之所以单列这八行:**执行环境与报告所写不符时,后续复现和排障会整体走偏**(例如实际只能以某种渲染模式运行,报告却照模板填了另一种)。
> 校验:`python3 <SKILL_DIR>/scripts/check_env_facts.py <round目录>/env-facts.json --report <本报告.md>`。

## 二、测试结果汇总

### 2.1 汇总数据

| 用例总数 | 可计算总数 | 执行数 | Pass | Fail | Block | N/A | 通过率 | 自动化率 | 自动化覆盖率 | 自动化成功率 |
| :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: |
| N | N-na | N-na | n | n | n | na | N% | N% | N% | N% |

> **N/A 不适用:** `na` 表示本场景不存在该模板项、永久不测,必须有理由;不计入通过率分子与分母。通过率=Pass/(总数−N/A);自动化率=(Pass+Fail)/(总数−N/A);**自动化覆盖率**=(可计算总数−block(driver-missing))/可计算总数;**自动化成功率**=(Pass+Fail)/(可计算总数−block(driver-missing))。`skip` 与 `block` 仍保留各自语义,不得用 N/A 替代。

### 2.2 各模块通过情况

| 模块 | 用例数 | Pass | Fail | Block | N/A | 通过率 |
| :- | :-: | :-: | :-: | :-: | :-: | :-: |
| {模块A} | … | … | … | … | … | …% |

### 2.3 缺陷列表

| 缺陷编号 | 等级 | 类别 | 所属模块 | 问题详情 | 证据路径 | 关联用例 |
| :- | :-: | :- | :- | :- | :- | :- |
| BUG-001 | Critical | 产品缺陷 | {模块} | {回归/PRD存在性/文案一致性 用例族失败,锁 Critical} | {evidence 路径} | {TC-ID} |
| BUG-002 | P1 | 产品缺陷 | {模块} | {失败现象} | {evidence 路径} | {TC-ID} |
| ENV-001 | — | 环境问题 | {模块} | 驱动缺失(driver-missing),该端跳过 | — | {TC-ID} |

> **分级口径(见 `references/report-format.md` §2.3):** **`[回归]`(`is_regression`)/`[PRD存在性]`/`[文案一致性]` 用例族失败一律锁 Critical(覆盖优先级映射、不许降级,**环境类 block_reason 除外**)**;其余 fail 按用例优先级映射 P0→P1/P1→P2/P2→P3;block(重试到顶)→ P2/P3 **待验证**;**环境类 `block_reason`**(driver-missing / driver-hung / precondition-unmet / network-error / env-unavailable / account-invalid)→ 编号 `ENV-xxx`、**环境问题、不计产品缺陷**;同用例 error+fail **只计一条**。**故缺陷数 ≠ fail+block 数**。

### 2.4 用例执行明细

| 用例编号 | 名称 | 优先级 | 模式 | 结果 | 失败原因 | 关联缺陷 | 证据 |
| :- | :- | :-: | :-: | :-: | :- | :- | :- |
| TC-USER-001 | 新增用户成功 | P0 | verified | ✅Pass | — | — | round-1/evidence/TC-USER-001-step5.webp |
| TC-MOBILE-002 | 移动端列表加载 | P1 | verified | ✅Pass | — | — | round-1/evidence/TC-MOBILE-002-step2.png |

> 证据列原样透传 `results/*.json` 的 `evidence[].artifact`,允许同一轮混合 `.webp/.png/.jpg/.jpeg`;不得按 TC-ID 补扩展名,同一截图只登记一种实际格式。

### 2.5 self-heal 失败复测追溯(仅有 self-heal 触发时出现;否则整段省略)

> 触发状态恢复重试的用例记录 根因 / 恢复动作 + observe 检验 / 复测结论;`still-fail-block` 的同时归入 §3.2 遗留风险。

| 用例编号 | 结果 | 根因(cause) | 恢复动作 + observe 检验(recovery) | 复测结论(outcome) |
| :- | :-: | :- | :- | :-: |
| TC-ORDER-005 | ✅Pass | 网络超时致按钮无响应 | 回起始页+重新登录 → 登录态/列表计数核对通过 | recovered-pass |

### 2.6 自由巡检(仅 free_scan 开启且有巡检项时出现;否则整段省略)

> 对「菜单可达、但本轮用例未覆盖」的 N 个页面逐个导航并拉运行时错误,共发现 X 条。
> **不计入用例统计、不进缺陷列表** —— 巡检项没有断言,混入会稀释通过率与「P0 100%」准则。
> 这里的发现是**线索**:需人工确认后再转 bug,或补成正式用例进下一轮。

| 页面 | 导航结果 | 运行时错误数 | 最高级别 | 摘要 |
| :- | :-: | :-: | :-: | :- |
| 角色管理 | ✅Pass | 2 | P1 | GET /api/role/list 500; Uncaught TypeError … |
| 已达巡检上限,以下页面未巡检 | ⚠️Block | 0 | — | free_scan_max_pages=20 已用尽,跳过 7 个页面:… |

### 2.7 耗时分布(由 `gen_report.py` 产出;⛔ 不得裁剪)

> 已采集 N 条,合计 X;**另有 M 条未采集耗时**(其真实耗时不在下表内,⛔ 不要把本表合计当作全轮执行时长)。
> ⚠️ **一条都没采集时不留空表**,而是照脚本输出写「本轮 N 条用例全部未采集单条耗时」——
> **空表会被读成「都很快」,而事实是「没测量」**。

| # | 用例 | 套件 | 结果 | 耗时 | 占已采集合计 |
| :-: | :- | :- | :-: | -: | -: |
| 1 | TC-PXY-F01 | SUITE-PROXY | ✅Pass | 36.8min | 25.0% |

> **execution_mode 分布**:direct=N / verified=N / self-heal=N;**实际触发自愈 K 次**。
> ⚠️ `execution_mode=self-heal` 表示「**具备**自愈能力」,**不表示「实际自愈了」**——两个数必须并排看
> (实证曾把「43 条 self-heal」读成「43 条在重跑」,而实际只重试过 1 次)。
>
> **执行机制分布**(仅当出现非 `dom` 值时输出):`dom` / `webmcp` / `mixed`。
> ⚠️ 视觉还原度类用例的 `mechanism` **不得为 `webmcp`**(`check_result.py` C14 判 Critical),
> 判据见 [`../references/execution-methodology.md`](../references/execution-methodology.md) 一·补三。

## 三、结论

### 3.1 是否具备上线条件

{据通过准则给出明确结论:具备 / 不具备 + 阻断项清单}

### 3.2 遗留风险

| 风险描述 | 等级 | 建议 |
| :- | :-: | :- |
| {风险} | 高/中/低 | {建议} |

> 所有 block / 未自愈项归入此处。

### 3.3 改进建议

- {用例 / 环境 / 驱动 / 自愈策略等改进项}
