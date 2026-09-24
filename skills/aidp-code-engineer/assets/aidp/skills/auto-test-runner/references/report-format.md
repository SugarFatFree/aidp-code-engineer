# 报告格式(固定结构,单一信源)

> 报告输出结构**固定**、不得裁剪章节。下游要求:概况 / 汇总(数据·各模块·缺陷列表·执行明细)/ 结论(上线条件·遗留风险·改进建议)。模板见 [`../assets/report-template.md`](../assets/report-template.md),聚合脚本 `scripts/gen_report.py`。

---

## 一、结果 JSON schema(单条用例)

每条用例执行后写 `round-{M}/results/{TC-ID}.json`(示例 [`../assets/result-schema.json`](../assets/result-schema.json)):

| 字段 | 类型 | 必填 | 说明 |
| :- | :- | :-: | :- |
| `case_id` | string | ✅ | 用例 ID(TC-*);自由巡检项形如 `运行时-<页面>` |
| `entry_kind` | string | — | ★条目类型,缺省 `"case"`(普通用例)。枚举:`case` / `free-scan`。**`free-scan` = 自由巡检项**(`free_scan: true` 时对「菜单可达但未被用例覆盖」的页面导航取错,见 [`execution-methodology.md`](./execution-methodology.md) 第十二节)。⚠️ **巡检项不计入用例统计、不进缺陷列表**——它没有断言,混进 `total` 会让"巡检页越多通过率越好看";漏标时 `check_result.py` 报 Important。**巡检项豁免 `suite` / `priority` / `execution_mode` 三个必填**(它不属任何套件、没有优先级、也没有执行模式分级);⚠️ 切勿给巡检项填 `execution_mode:"verified"`,否则 pass 且无 evidence 会触发 C4 Critical |
| `suite` | string | ✅ | 所属套件/模块 |
| `test_name` | string | ✅ | 用例名称 |
| `priority` | string | ✅ | P0/P1/P2 |
| `client` | string | ✅ | 被测端(web/miniprogram/mobile/desktop) |
| `driver` | string | ✅ | 实际使用的驱动。**Web 端取值枚举:`cli`(本地 `chrome-devtools` 命令、驱动本机独立 Chrome)/ `mcp-remote`(异机自注册的远程 MCP 变体)/ `mcp-plugin-fallback`(插件自起隔离实例变体,CLI 缺失时的 last-resort)/ `manual`(人工介入)**——须如实反映实际驱动,严禁静默切换或用了 plugin 却填 `cli`;各变体对应的**具体 MCP 工具名见 [`driver-web.md`](./driver-web.md)**(端专有工具名只在适配层出现,方法论层不写);其它端如 `appium`/`miniprogram-automator`/… |
| `execution_mode` | string | ✅ | direct / verified / self-heal |
| `status` | string | ✅ | pass / fail / block / **na**。`na` 表示本场景永久不适用,不是本轮跳过或环境阻塞;显式 `na` 必须同时提供非空 `note` / `na_reason` / `error` 之一作为理由。 |
| `is_reverse` | bool | ✅ | 是否反向用例(取自上游用例「反向」字段,是=true)。**含 `[反向-残留]` 用例**——由「不存在文本"X"」DSL 承载,元素仍存在则 fail |
| `is_regression` | bool | — | ★是否回归用例(上游 `[回归]` 标记,是=true)。**为 true 时失败一律锁 Critical**(见 §2.3 + gen_report 用例族锁定);缺省 false,行为与旧版本一致 |
| `related_defect_id` | string\|null | — | ★回归用例关联的缺陷 ID(上游 `关联缺陷: {缺陷ID}` 字段);非回归用例为 null |
| `db_assertion` | object\|null | — | ★`[双源对账]` 用例的数据真值对账结果,由**驱动适配层 DB 断言驱动**(见 [`driver-db-assertion.md`](./driver-db-assertion.md))产出:`{pageValue(页面取值), sqlValue(等价 SQL 取回的 DB 真值), match(是否一致)}`。`match=false` → 该用例判 fail。非双源对账用例为 null |
| `precondition_probe` | object\|null | — | ★浏览器前 `ED-NNN` 前置探测结果:`{id, status, detail, evidence}`。`status`=`satisfied` / `unmet` / `probe-error`;关联前置不满足时用例必须 `block_reason=precondition-unmet`,detail 使用声明的缺位短语;探测调用失败时不得伪装成 `unmet`,应记录 `probe-error` 并按网络/环境错误归因 |
| `block_reason` | string\|null | ✅ | 仅 status=block 时非空。枚举:`retry-exhausted` / `driver-missing` / `driver-hung` / `precondition-unmet` / `network-error` / `env-unavailable` / `account-invalid` /(**条件启用**)`webmcp-driver-too-old` / `webmcp-driver-version-unknown`。**缺陷分级与去重按此枚举,不靠 error 文本 grep**;**除 `retry-exhausted` 外均属环境类**(见 §2.3) |
| `is_environment_issue` | bool\|null | 可选 | 执行方显式标注本次阻塞是否属环境问题,**优先级高于 `block_reason` 枚举推断**;缺省 null → 回落枚举判定(向后兼容)。仅 status=block 生效 |
| `error` | string\|null | ✅ | pass 时 null;fail/block 记详细原因 |
| `evidence` | array | ✅ | 证据条目 `[{step, summary, artifact}]`;`artifact` 必须是 capture 实际生成的当前 `round/evidence` 相对路径（evidence 根不得是符号链接）,文件存在且非 0 字节;截图允许 `.webp/.png/.jpg/.jpeg` 且最小容器结构须匹配,新截图文件名须匹配 `{case_id}-step{step}`（历史 `{case_id}-{step}` / `{case_id}_步骤{step}` 兼容告警）,同一截图只登记一种格式,调用方不得按 TC-ID 猜扩展名;verified/self-heal 的 pass 必须有完整证据,direct 的 pass 至少有一条轻量事实(实际值/命中文案/列表计数/产物路径),不要求截图类型 |
| `runtimeErrors` | array | ✅ | ★运行时错误全程捕获(**P3 告警类受 run-context `capture_warnings` 控制、默认关;P1/P2 恒记录** —— 故 P3 缺失不等于采集不全,勿据此判「采集不完整」),`[{type, message, detail, severity, artifact}]`;`type`=console\|network\|pageError,`detail`=`METHOD PATH 状态码` 或 console 首行,`severity`=P1\|P2\|P3。**每条用例执行后附带拉一次 console/network 写入**;pass 用例也可能非空 |
| `retries` | int | ✅ | 实际重试次数 |
| `self_heal_applied` | bool | — | self-heal 模式是否触发过状态恢复重试 |
| `self_heal_trace` | object\|null | — | ★可选,失败复测追溯。仅 `self_heal_applied=true` 时非空,含 `cause`(失败根因)/ `recovery`(恢复动作 + observe 恢复检验结果)/ `outcome`(枚举 `recovered-pass` / `still-fail-block`)。缺省或 null 时报告行为与旧版本一致 |
| `self_heal_attempts` | int | — | ★**实际触发自愈的次数**(缺省 0)。⚠️ 与 `execution_mode` **不是一回事**:`execution_mode=self-heal` 只表示「**具备**」自愈能力,不表示「**实际自愈了**」(实证:43 条 self-heal vs 实际重试 1 次)。报告出现 `execution_mode` 分布时**必须并排给出本字段合计**;`check_result.py` I11 在 `self-heal` 且 `retries=0` 且本字段为 0 时提醒 |
| `started_at` | string | ✅ | ★**单条耗时三件套之一**,ISO-8601 带时区。**没有单条耗时,任何耗时优化都无法验证是否生效**(实证:一条用例占整轮 25%,此前只能靠 evidence 文件 mtime 反推、少产一个证据文件就整条漏掉)。缺失由 `check_result.py` **I8 判 Important**(不判 Critical 是因为存量一条都没有,判死会让整个校验被绕过) |
| `finished_at` | string | ✅ | ★同上,ISO-8601 带时区 |
| `elapsed_ms` | int | ✅ | ★同上,整数毫秒。与 `finished_at−started_at` 相差 > 2s 由 **I9** 告警(两者不是同一次计时);与旧字段 `duration_ms` 并存且不等由 **I10** 告警。`gen_report.py` 据本字段产出 **§2.7 耗时分布** |
| `duration_ms` | int | — | 旧字段,与 `elapsed_ms` **同义**,仅为兼容存量结果保留(聚合时 `elapsed_ms` 优先、缺失才回落它)。**新结果一律填 `elapsed_ms`**,两者都写且不等会被 I10 判不可信 |
| `mechanism` | string | — | ★本条用例的**主要执行机制**,枚举 `dom`(缺省)/ `webmcp` / `app-mcp`(应用自有业务工具)/ `mixed`。⚠️⚠️ **`[还原度]` 及一切视觉/布局/样式断言禁止填 `webmcp`** —— WebMCP 读的是页面**声明的能力**、不是**渲染结果**,用它验还原度会让渲染层缺陷 **100% 漏测且全绿**(`check_result.py` **C14 判 Critical**;`mixed` = 状态准备走 WebMCP、断言走 DOM,**是被鼓励的形态,不判**)。枚举外取值由 **C15** 判 Critical。判据全文见 [`execution-methodology.md`](./execution-methodology.md) 一·补三「WebMCP 分层铁律」。⚠️ **未填 ≠ 已确认是 dom**:`gen_report.py` 把未填的单列成 `未声明` 一档、**不并进 `dom`**(并进去等于替执行方断言「这条走的是 DOM」);`webmcp_enabled: true` 的轮次**必须逐条如实填**,否则 C14 够不着、这一档等于没测 |

**status 语义**:`pass` 全部预期通过;`fail` 关键预期验证失败;`block` 重试到顶仍失败 / 前置不满足 / 驱动缺失 / 网络不可用——**具体原因由 `block_reason` 枚举承载**(不再靠 error 文本判定)。浏览器前前置探测产生的 `precondition_probe.status=unmet` 才能使用 `precondition-unmet`;`probe-error` 必须按网络/环境错误归因,不得伪装成数据缺位。

> **客户端故障注入结果留痕:** 使用客户端初始化脚本注入的用例,结果 `error`/`evidence` 必须记录注入类型、命中端点、失败/延迟参数及「全端点 `200 + 空数据`」阳性对照结果。阳性对照缺失或注入未生效时不得判通过。

> **★值级断言硬约束(判 pass 的前提,不限 P0/P1):** 凡涉及**数值 / 状态 / 权限**的用例,判 `pass` 必须基于**值级断言**(列表行数=N / 字段值 / 状态迁移 / 权限入口可见性等确定化比对);**严禁把「页面加载成功 / 无 console error / 元素存在」当作业务用例的唯一 pass 判据**。`[双源对账]` 用例的值由 DB 断言驱动对账 SQL 真值(`db_assertion.match=true` 才算过)。细则见 execution-methodology.md「值级断言硬约束」。

**★运行时错误(runtimeErrors)为什么独立于 error**:`error` 只描述"执行本身异常(元素找不到/驱动挂)";`runtimeErrors` 捕获"页面/接口的后台错误"(console 报错、network 非 2xx、页面级错误 UI),**即便用例功能 pass 也可能存在**。下游 `/sprint-aiauto-test` 的「运行时错误全程捕获→升级 bug→回写问题汇总清单」直接消费本字段,无需命令端二次扫描。

---

## 一·补、运行环境事实 schema(`round-{M}/env-facts.json`)

环境准备阶段取证一次落盘(`round-{M}/env-facts.json`,与用例结果的 `round-{M}/results/` 平级),是报告「一、测试概况」**环境事实类字段的唯一数据源**。

📌 **单一信源:字段清单、类型契约、五类来源枚举、三条铁律、判定顺序、硬门口径一律以 [`execution-methodology.md`](./execution-methodology.md) 第十节为准,本文件不复制。** 示例对象见 [`../assets/env-facts-schema.json`](../assets/env-facts-schema.json)。

本文件只补充**与报告的接口**这一点:

- 概况的环境事实行（**判据 = `assets/env-facts-schema.json` 里配了 `XSource` 的全部字段**，当前含渲染模式 / 浏览器版本 / viewport / 是否复用已有实例 / 被测 URL / 登录角色 / driver / 执行路径 / 数据源环境 / 数据源归属；schema 是单一信源，`check_env_facts.py` 的 `REQUIRED_FACTS` 与之同步，此处不写死条数）**逐行照抄** `env-facts.json` 的值与 `XSource`,不得改写、不得省略、不得填模板默认;取不到的写「未取到(原因)」。
- 核对命令:`python3 <SKILL_DIR>/scripts/check_env_facts.py <round目录>/env-facts.json --report <报告.md>`。

---

## 二、报告固定章节结构

### 一、测试概况

项目名 / 版本 / Build+轮次 / 被测端 + 驱动 / 测试类型(全量·增量)/ 测试范围 / 依据(用例来源、自测方案)/ 执行方式(无人值守自动化)/ 执行起止时间,**外加取自 `env-facts.json` 的环境事实行:渲染模式 / 浏览器版本 / viewport / 是否复用已有实例 / 被测 URL / 登录角色**。

> **★环境事实行必须逐个带「来源」列,禁模板默认(Critical):** 这些字段一律取自 `round-{M}/env-facts.json`,**不得由意图推断或模板默认填充**——典型翻车是**没有图形界面的远程机器上只能无头运行,报告却恒填「有头」**。取不到的字段照写「未取到(原因)」,不填一个看起来合理的值。口径见「一·补」,校验见其中的命令。

### 二、测试结果汇总

- **2.1 汇总数据**:用例总数 / 可计算总数(总数−N/A) / 执行数 / Pass / Fail / Block / **N/A** / **通过率(Pass/可计算总数)** / 自动化用例数(Pass+Fail)/ **自动化率 auto_rate=(Pass+Fail)/可计算总数** / **自动化覆盖率 autoCoverRate** / **自动化成功率 autoSuccessRate** / 总耗时 /(可选)Token 统计(总 token、总工具调用、平均每条 token)。`na` 不计入通过率和自动化比例分母,报告单列「不适用 N 条」；direct pass 缺轻量事实时另单列「无依据的 direct pass N 条」,不改变通过率。
  > **★自动化率按 block_reason 细分(新增两派生指标,旧 `auto_rate` 口径不变):** `driver-missing` 是环境问题(端未装驱动),不该与真跑失败的 block 一样拉低指标,故新增两个据**已有 `block_reason` 枚举**派生的指标:
  > - **自动化覆盖率 `autoCoverRate` = (总数 − block(driver-missing)) / 总数** —— 实际"能尝试"的比例(排除环境未装驱动而整体跳过的用例)。
  > - **自动化成功率 `autoSuccessRate` = (Pass+Fail) / (总数 − block(driver-missing))** —— 能尝试的用例里跑到真实结论(pass/fail)的比例。
  > - 保留旧 **`auto_rate` = (Pass+Fail)/总数** 兼容。**向后兼容性质:当 `driver-missing=0` 时,分母 `总数 − 0 = 总数`,`autoCoverRate=1`、`autoSuccessRate` 数值与旧 `auto_rate` 完全一致**——新指标只在存在 driver-missing 时才与旧口径分化,不改变既有报告数值。两个新指标由 `gen_report.py` 从 `results/*.json` 的 `block_reason` 枚举派生,无需新数据。
- **2.2 各模块通过情况**:表格,每模块 用例数 / Pass / Fail / Block / 通过率。
- **2.3 缺陷列表**:表格,`缺陷编号 | 等级 | 类别 | 所属模块 | 问题详情 | 证据路径 | 关联用例`。缺陷等级由**用例结果 + 优先级按下表映射**,而非直接等同 fail/block 数:

  | 用例结果 | 缺陷等级映射 | 类别 |
  | :- | :- | :- |
  | **`block`(环境类 `block_reason`)或显式 `is_environment_issue=true`** | **不计产品缺陷**(编号 `ENV-NNN`,**优先级最高、先于下面所有行**) | 环境问题(单列) |
  | **`[回归]` / `[PRD存在性]` / `[文案一致性]` 用例族失败**(fail,或**非环境类**的 block) | **Critical**(**用例族锁定,覆盖下方优先级映射,不许降级为 Important/P1…**) | 产品缺陷 |
  | `fail`(P0 用例) | **P1** 产品缺陷 | 产品缺陷 |
  | `fail`(P1 用例) | **P2** 产品缺陷 | 产品缺陷 |
  | `fail`(P2 用例) | **P3** 产品缺陷 | 产品缺陷 |
  | `block`(`block_reason`=retry-exhausted,**非环境类**) | **P2/P3 待验证**(标「待验证」,可能是产品缺陷也可能是用例问题) | 待验证 |
  | fail/block 用例携带的 `runtimeErrors` | **折进该用例的单条缺陷,不另计**(同用例只计一条) | 同上 |
  | **pass 用例携带的 `runtimeErrors`** | 按各条 `severity`(P1/P2/P3)**单列为「运行时错误」发现项**(RT-NNN),供下游升级 bug | 运行时错误 |

  > **★环境类 block 一律不计产品缺陷(优先级最高,先于用例族锁定):** 环境类 `block_reason` 集合 = **`driver-missing` / `driver-hung` / `precondition-unmet` / `network-error` / `env-unavailable` / `account-invalid`**(单一信源 `gen_report.ENV_BLOCK_REASONS`),命中即判「环境问题」、编号 `ENV-NNN`、**不计产品缺陷、不锁 Critical**——即便是回归/PRD存在性/文案一致性用例族,**环境没起来也不是产品缺陷**(锁 Critical 只对"真跑起来了但结果不对"有意义)。执行方可用**显式布尔 `is_environment_issue`** 覆盖枚举推断(枚举归不了类的环境阻塞用它)。
  > ⚠️ **`retry-exhausted` 刻意不在环境类集合内**:"单操作重试到顶"既可能是环境抖动,也可能是页面根本没渲染出来这种真缺陷,保守留在「待验证」侧由人复核。
  > ⚠️ **本条来自实测**:一轮 32 条用例全部 `block(precondition-unmet)`(前置环境未就绪),旧口径下 `is_product_defect=True` → 报告显示「**产品缺陷 32 条**」并编号成 `BUG-xxx`,把纯环境阻塞误报成 32 个产品 bug,还会污染下游「缺陷→升级 bug→回写问题汇总清单」链路。**勿改回「只有 driver-missing 算环境问题」。**
  > **★用例族锁定 Critical(次高,先于优先级映射):** `is_regression=true`(`[回归]`)、`[PRD存在性]` 或 `[文案一致性]` 用例族一旦失败(fail / **非环境类**的 block),缺陷等级**一律锁 Critical**,**覆盖**"按用例优先级 P0→P1/P1→P2/P2→P3"的常规映射——即便用例本身是 P2,这三类用例族失败也判 Critical、不许降级。`[文案一致性]` 锁 Critical 的理由:语义/口径变更后旧文案残留(反向断言"不存在文本X"命中)或新语义未落地,直接误导对账,是确定性产品缺陷。`driver-missing` 是环境问题(非真失败),不在锁定范围。`gen_report.py` 在 `FAIL_LEVEL` 映射前先判用例族标记(`is_regression` / `[PRD存在性]` / `[文案一致性]`),命中即锁 Critical。
  > **分级依据 `block_reason` 枚举,不再 grep error 文本**;**缺陷数 ≠ fail+block 数**:环境类 block 不计产品缺陷、同用例 error+runtimeErrors 去重,pass 用例的运行时错误另列 RT-NNN,故缺陷列表口径与原始 fail/block 数不同——报告须据此口径。
- **2.4 用例执行明细**:表格,`用例编号 | 名称 | 优先级 | 模式 | 结果(✅Pass/❌Fail/⚠️Block) | 失败原因 | 关联缺陷 | 证据`。
  > **★self-heal 用例展示 `self_heal_trace`:** 携带 `self_heal_trace` 的用例(`self_heal_applied=true`),在「失败原因」或备注列附 `cause` / `outcome`(如"网络超时→recovered-pass"),让报告能回答"这条为什么恢复/仍失败";`still-fail-block` 的 trace 同时归入 §3.2 遗留风险。无 `self_heal_trace`(非 self-heal 用例)时明细展示与旧版本一致。
- **2.5 self-heal 失败复测追溯(可选节)**:表格,`用例编号 | 结果 | 根因(cause) | 恢复动作 + observe 检验(recovery) | 复测结论(outcome)`。**仅在存在 `self_heal_trace` 时输出**,缺省整节不出。
- **2.6 自由巡检(可选节)**:表格,`页面 | 导航结果 | 运行时错误数 | 最高级别 | 摘要`。**仅在 `free_scan: true` 且产生了 `entry_kind:"free-scan"` 结果项时输出**,缺省整节不出。
  > **★巡检项不计入用例统计、不进缺陷列表。** 它是对「菜单可达但本轮用例未覆盖」页面的探索性导航,**没有断言** —— 混进 `total` 会让"巡检页越多通过率越好看",方向恰好是反的。`gen_report.split_entries` 按 `entry_kind` 分流;漏标时 `check_result.py` 报 Important(`free_scan_unmarked`)。巡检发现是**线索**,需人工确认后转 bug 或补成正式用例进下一轮。细则见 [`execution-methodology.md`](./execution-methodology.md) 第十二节。

### 三、结论

- **3.1 是否具备上线条件**:据通过准则(默认 P0=100% / P1≥95% / P2≥80%)给出明确结论(具备 / 不具备 + 阻断项)。**若存在 `block(driver-missing)`,据其占比提示"N 条因环境未装驱动未测,非产品问题",并参考 `autoCoverRate`/`autoSuccessRate` 区分"没跑到"与"跑了没过",避免把环境问题误判为产品阻断。**
- **3.2 遗留风险**:表格,`风险描述 | 等级(高/中/低) | 建议`。所有 block/未自愈项归入此处。**self-heal 用例 `outcome=still-fail-block` 的,风险描述附其 `self_heal_trace` 的 `cause`(根因)与恢复检验未通过点**,便于人事后定位(为何恢复无效)。
- **3.3 改进建议**:用例、环境、驱动、自愈策略等改进项。

---

## 三、统计口径

- **通过率** = Pass / 用例总数。
- **自动化率 auto_rate** = (Pass + Fail) / 用例总数(block 一视同仁视为未自动化完成)。**口径保留不变(向后兼容)**。
- **自动化覆盖率 autoCoverRate** = (用例总数 − block(driver-missing)) / 用例总数 —— 剔除"环境未装驱动整体跳过"的用例,反映实际"能尝试"比例。
- **自动化成功率 autoSuccessRate** = (Pass + Fail) / (用例总数 − block(driver-missing)) —— 能尝试的用例里跑到真实结论(pass/fail)的比例。
  > **向后兼容:`driver-missing=0` 时,`autoCoverRate=1`、`autoSuccessRate` 与旧 `auto_rate` 数值完全一致**;仅当存在 driver-missing 才与旧口径分化。两派生指标据**已有 `block_reason` 枚举**计算(无需新数据),旧 `auto_rate` 继续输出。
- **各模块通过情况**按 suite 分组统计。
- **自由巡检项一律不参与上述任何统计**:`entry_kind:"free-scan"` 的结果项在聚合入口即被 `split_entries` 分流,不进 `total`、通过率、自动化率、各模块通过情况与缺陷列表,单列 §2.6。通过准则(P0=100% / P1≥95% / P2≥80%)同样只对用例生效。
- 统计由 `gen_report.py` 从 `results/*.json` 聚合,人不手工计数。

> **★事实字段来源通则(环境事实类 + 统计类同一口径):** 报告里凡「事实类」字段都要能回答**这个值是怎么来的**——**统计类**来自 `results/*.json` 经 `gen_report.py` 聚合(不手工计数、不照抄模板示例数字),**环境事实类**来自 `env-facts.json` 的运行取证(逐字段带来源标注)。**共同红线:没有实测支撑的值一律写「未取到 + 原因」,不写一个像样的默认值。** 细则见 [`execution-methodology.md`](./execution-methodology.md) 第十节 10.5。

---

## 四、TestNotes(执行记录,可选副产)

除正式报告外可产 `TestNotes.md`(执行记录:用例执行记录表 + 执行汇总 + 失败详情 + Token 消耗表),作为执行流水留痕,供复核与追溯;正式结论仍以「测试报告」三章为准。

---

## 五、与 AI 执行报告(autopilot)对账的数据模型映射

下游 autopilot 链路维护一份 `data/{BUILD}.js` 的 `testSummary`,供回填对账。本 skill 的 `results/*.json` 聚合(`gen_report.py --json`)与之字段映射如下,**保证执行结果可被 autopilot 回填、不重算**:

| 本 skill(gen_report 聚合 / results 字段) | → autopilot `data/{BUILD}.js` `testSummary` | 说明 |
| :- | :- | :- |
| `total`(用例总数) | `testSummary.total` | 直接映射 |
| `counts.pass` | `testSummary.passed` | Pass 数 |
| `counts.fail` | `testSummary.failed` | Fail 数 |
| `counts.block` | `testSummary.blocked` | Block 数(含 driver-missing) |
| `pass_rate`(Pass/总数) | `testSummary.passRate` | 通过率,小数或百分比按 autopilot 口径 |
| `auto_rate`((Pass+Fail)/总数) | `testSummary.autoRate` | 自动化率(可选) |
| `auto_cover_rate`((总数−driver-missing)/总数) | `testSummary.autoCoverRate` | 自动化覆盖率(**可选,缺省不破坏 autopilot 对账**;driver-missing=0 时=1) |
| `auto_success_rate`((Pass+Fail)/(总数−driver-missing)) | `testSummary.autoSuccessRate` | 自动化成功率(**可选,缺省不破坏对账**;driver-missing=0 时=auto_rate) |
| 执行结束时间(run-context / build 元信息) | `testSummary.timestamp` | 时间戳;本 skill 脚本不产生时间(禁 Date.now),由编排层在回填时打戳 |
| `modules[*]`(各模块统计) | `testSummary.byModule[*]` | 各模块 total/pass/fail/block/通过率 |
| `defects[*]`(缺陷列表,已按 §2.3 分级去重) | `testSummary.defects[*]` | driver-missing 不计产品缺陷、同用例 error+fail 去重后的口径 |
| `runtime_findings[*]`(pass 用例携带的运行时错误) | `testSummary.runtimeErrors[*]` | 供「运行时错误→升级 bug→回写问题汇总清单」直接消费 |

- **对账口径一致性**:`testSummary.passed + failed + blocked == total`;缺陷数走 §2.3 分级映射口径(≠ fail+block 原始数)。
- **单向数据流**:本 skill 产出 `results/*.json` → `gen_report.py` 聚合 → 编排层回填 autopilot `data/{BUILD}.js`;本 skill 不直接写 autopilot 文件(职责隔离)。

### 2.7 耗时分布(2026-09-10 新增,由 `gen_report.py` 产出)

**数据源:** 每条结果 JSON 的 `started_at` / `finished_at` / `elapsed_ms` 三件套
(旧字段 `duration_ms` 兼容回落)。**列:** `# | 用例 | 套件 | 结果 | 耗时 | 占已采集合计`,只列最长 10 条。

⚠️ **本节存在的全部理由(实测依据):** 两轮 116 条里 **`TC-PXY-F01` 一条占整轮总时长 25%(36.8 min)**,
而这个结论此前只能靠**三个 evidence 文件的 mtime 跨度手工反推** —— 只要那条用例少产一个证据文件,
它就**整条漏掉**。**没有单条耗时,任何优化都无法验证是否生效。**

⚠️ **无耗时数据时不输出空表**,而是打一行「本轮 N 条全部未采集」——**空表会被读成「都很快」**。
⚠️ 有未采集条目时,表头注明「⛔ 不要把本表合计当作全轮执行时长」。

**同节附两行语义纠偏(必读):**

- **`execution_mode` 分布必须与「实际触发自愈次数」并排给出。** `execution_mode=self-heal` 表示
  「**具备**自愈能力」,**不表示「实际自愈了」**——实测中曾把「43 条 self-heal」读成「43 条在重跑」,
  而实际只重试过 **1** 次,调优方向当场被带偏。
- **执行机制分布(`dom` / `webmcp` / `app-mcp` / `mixed` / `未声明`)**:仅当出现非 `dom` 值时输出。
  ⚠️ **`未声明` 是独立的一档、⛔ 不并进 `dom`** —— 结果 JSON 没填 `mechanism` 时报告写 `dom=N`
  等于替执行方断言「这条走的是 DOM」,而事实是**没人填过这一格**(与约束 10「事实字段可溯源、
  禁模板默认」冲突);方向是假绿:真用 WebMCP 验了还原度、却没填 `mechanism` 的那条,C14 够不着、
  报告上也看不出来。
  ⚠️ 视觉还原度类用例的 `mechanism` **不得为 `webmcp`**(`check_result.py` C14 判 Critical),
  判据见 `execution-methodology.md` 一·补三「WebMCP 分层铁律」。

> ⚠️ **「非执行开销」这类差值不能直接当作可优化的开销**:`总耗时 − evidence 首尾跨度` 把报告生成、
> 终审、文档级联这些**交付物本身**也算了进去。**先做计时,再谈开销。**
