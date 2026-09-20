<!-- 二次切分 · phase-2 片2/2：覆盖 2.0.5 委派auto-test-runner / 2.1 登录测试循环 / 2.2 浏览器调用 / 2.3 skip-login / 2.4 运行时错误捕获-->
# /sprint-aiauto-test · 执行分片 分片 [2/2]（2.0.5 委派auto-test-runner / 2.1 登录测试循环 / 2.2 浏览器调用 / 2.3 skip-login / 2）

> ⚠️ **权威性**：以本文件为准逐项执行，不得凭命令主体骨架或记忆略过任一子步骤 / 硬门。
> ⚠️ **维护**：随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-aiauto-test/phase-2-2.md`。理据见同目录 `rationale.md`。

### 2.0.5 组装 run-context + 派测试执行子 Agent（★ 执行内核入口）

Phase 0 已备齐环境（DRIVER / URL / 账号 / 等待时长 / BUILD），Phase 2.0 已选定用例集（`PRIMARY_CASES` + `SUPPLEMENT_UNIQUE`，已剔除远程延后集）。此处组装 `auto-test-runner` 的 run-context，**按模块（= 套件）各派一个「测试执行子 Agent」**（`Agent`/Task 工具）：

> ⛔ **派子 Agent、不 `Skill`-invoke**：执行子 Agent **拿不到 Skill 工具**（即便 `tools:*` 也没有），主 Agent 必须在 Task prompt 里要求子 Agent 先用 `Read` 读方法论。理据见 `rationale.md`。
>
> **子 Agent prompt 必含的路径清单（只给路径、不贴正文）**：
> - `.aidp/skills/auto-test-runner/SKILL.md` + `references/execution-methodology.md`（完整执行方法论）
> - `references/driver-adapters.md` + 被测端对应的 `references/driver-<端>.md`（本命令为 Web 端）+ `references/usecase-format.md`（解析用例）
> - 本模块用例文件路径 + run-context 文件路径
> - 要求：**读完再驱动浏览器执行**；跑完回传 compact `{module,total,pass,fail,block,evidence_dir,defects[]}`
> - **复测轮（`retest_of` 非空）追加**：prompt 必须附**上一 build 的 block 用例清单（含各自原因）**，
>   要求逐条给出三选一并写进 `note`：仍 block（原因不变）/ 仍 block（原因变更，须说明）/ 已解锁→实际结果。
>   ⛔ 照抄 = 未复评（收尾门 3q 拦缺席与空 `note`）。理据见 `rationale.md`。
> - **执行选集**：`SELECT_MODE != all` 时，prompt 要求子 Agent 建 tasks.md 时带选集参数——
>   `python3 .aidp/skills/auto-test-runner/scripts/tasks_state.py init <用例源> -o <tasks.md> --select $SELECT_MODE`。
>   ⚠️ `select` **不是 run-context 字段**（SKILL 侧仅 `tasks_state.py init` 的 CLI 参数），必须经 prompt 传；
>   脚本会自动在 tasks.md 头部写「本轮为子集」告示 +「准则仅对子集成立、新 build 回归轮禁用选集」提醒。

| run-context 字段 | 本命令传入值 | 来源 |
|---|---|---|
| 被测端类型 | `web` | Phase 0.0.6 Step 1 判定 IS_FRONTEND_WEB（本命令仅测 Web 浏览器项目）|
| 驱动选择 | `chrome-devtools-mcp`（本地 `cli` / 远程 `mcp`，前缀按 Phase 0.1）| Phase 0.1 定的 DRIVER |
| 环境地址 | 部署 URL | Phase 0.3 |
| 账号（各角色）| `$TEST_ROLES` 用户名/密码（密码不进日志）| Phase 0.4 |
| 用例来源 | `PRIMARY_CASES` + `SUPPLEMENT_UNIQUE`（+ 跨版本 `[回归]` 用例，见 Phase 2.0）| Phase 2.0 |
| `free_scan` | `--free-scan` 给出则 `true`，否则 `false`（默认关）| 本命令 flag |
| `free_scan_max_pages` | 不传（用 SKILL 缺省 20）；确需调整时随 `--free-scan` 一并给出 | 本命令 flag |
| `capture_warnings` | `--capture-warnings` 给出则 `true`，否则 `false`（默认关）| 本命令 flag |
| 执行选集 `SELECT_MODE` | `--select` 给出则该值，否则 `all`；**无人值守 / 编排链内调用 / 新 build 回归轮一律强制 `all`**（见命令主体注意事项 6bis）| 本命令 flag |
| ★ DB 连接（约定 33 缺口 3）| 「测试环境与账号」§五 DB 连接段的 datasource / DB MCP 名 **+ `environment`（SKILL 明令必填、禁留空；缺则填 `{待用户填写}` 并在报告点名）**——⛔ 漏传不报错，只让归属落 `unverified`、`[双源对账]` 用例整批降级 （缺则回退后端 `application.yml` 生效 profile）| Phase 0.0.5 读配置 |
| ★ 跨系统前置数据（约定 33 缺口 4）| 「测试环境与账号」§三/§四的**联动系统**入口 + 账号 + §五对应 DB | Phase 0.0.5 读配置 |
| 存活心跳 `heartbeat_cmd` | `python3 .aidp/scripts/baseline_edit.py set aiauto_test_heartbeat_at @now` | ★ 长批次续写测试链路心跳（开发链路据此判「测试链路存活」）；主 Agent 每收回一个执行子 Agent 也执行一次 |
| 单步等待上限 | 每步 `${OP_TIMEOUT}s` / 首开 `${NAV_TIMEOUT}s` | Phase 0.0.6 用户确认 / 无人值守默认值（见 2.2.1）|
| 测试产物目录 | `docs/reports/${TARGET_VERSION}/AI测试报告/` | skill 在此下按其契约自建 `build-${BUILD}/round-{M}/`（含 tasks.md / results/ / evidence/）；BUILD 由 Phase 0.2 读 |
| 证据归档目录 | **不覆盖，由 skill 按契约派生** = `build-${BUILD}/round-{M}/evidence/{TC-ID}-{step}.png` | ★ 尊重 auto-test-runner 落盘契约（约定 21，命令端不强加扁平/role 路径）；命令端 Phase 3.2.5 再从此处**消费/归集** skill 截图到报告 `screenshots/${BUILD}/` 供 SPA 渲染 |
| 通过准则 | 取研发自测方案；缺则用 auto-test-runner skill 默认通过准则（阈值以 skill `references/report-format.md` 为单一信源，命令端不复述）| Phase 2.0 用例配套方案 |

> ★ **约定 33 配套边界（约定 21）**：命令端只负责把「DB 连接 / 跨系统前置数据」作为 run-context 参数**交给** auto-test-runner；**用起来**（DB 断言、前置段执行）以 auto-test-runner SKILL 为单一信源（`result-schema` 的 `db_assertion` 字段），命令端不复述、不实现。

派单后（主 Agent **每收回一个执行子 Agent 即执行一次 `python3 .aidp/scripts/baseline_edit.py set aiauto_test_heartbeat_at @now`**，长批次期间心跳不陈旧）各执行子 Agent 按 auto-test-runner 执行流程（第零步~第四步）分模块批量跑完、断点可续、实时打印进度（见 2.2.2），产出每条用例 `results/{TC-ID}.json`（`status`=pass/fail/block/**na** + `evidence` 截图摘要+路径）+ `tasks.md` 进度 + 固定结构报告。命令端**等 skill 跑完**再进 2.4（运行时错误后处理）+ Phase 3（AI测试报告 HTML）。

> ★ **无人值守一致**：auto-test-runner 执行不中途等人、阻塞标 block 继续；run-context 缺失项由 Phase 0 一次性收全（0.0.6），委派时不再追问。
> ✅ **运行时错误对接已就绪**：`result-schema.json` 的 `runtimeErrors[]` 必填 `type`/`message`/`severity`，命令端只消费、不重算。字段全表见 `rationale.md`「运行时错误对接」。

### 2.1 登录 → 测试 → 登出循环（★ skill 内部行为示意 — 命令端不手写直驱，实际由 auto-test-runner 执行）

> ⛔ **命令端不手写这些动作**：登录 / 跑用例 / 截图 / 拉运行时错误全部由 auto-test-runner 执行（约定 21），命令端只在 2.0.5 传 run-context、跑完消费产物；下述仅为理解，非待执行脚本。

skill 在 Web 端的行为概要（详见 auto-test-runner `references/execution-methodology.md` + `driver-adapters.md`）：
- **每模块开头登录一次**（按各角色账号），模块内用例通过导航切换连续执行、**不重复登录**（会话复用降 token）；登录失败该模块整体标 block，不挂起。
- **每条用例走感知-执行-校验-决策闭环**：`observe` 读页面态 → `act` 按用例四要素步骤操作（含等待，单步上限取 run-context 的 `OP_TIMEOUT`/`NAV_TIMEOUT`）→ `assert` 比对预期 → 决策 pass/fail/block。
- **关键步骤 `capture` 取证**（登录/提交/状态变化/断言/报错）：**无头下截图是唯一执行证据**；证据按 skill 契约落 `build-${BUILD}/round-{M}/evidence/{TC-ID}-{step}.png`（命令端 Phase 3.2.5 再归集到报告 `screenshots/${BUILD}/`）。
- **每条用例执行后附带拉一次 console/network**，写入 `results/{TC-ID}.json` 的 `runtimeErrors[]`（pass 用例也拉——页面能用但后台有 500/JS 报错供下游升级 bug）；命令端 Phase 2.4 直接消费该字段。
> ✅ **「自由巡检」已由 auto-test-runner 支持**（run-context `free_scan`，默认关）：全部模块用例跑完后，对「菜单可达但本轮无用例覆盖」的页面逐个导航 + 拉运行时错误。命令端经 `--free-scan` 开启，**不自行实现**（约定 21）。
> 巡检项在 `results/` 里以 `entry_kind="free-scan"` + `case_id` 前缀 `运行时-` 落盘（`check_result.py` 校验二者一致）；页数超 `free_scan_max_pages`（默认 20）时 SKILL **不静默截断**，单写一条 block 巡检项列明被跳过页面——它同属巡检项，**不自动写入问题汇总清单**，只作为待确认项记入 AI 测试报告 §2.6 并在 #F 通知中列出（见 2.4），否则「巡检过了」名不副实。

### 2.2 chrome-devtools-mcp 调用（★ skill 内部行为示意 — 由 auto-test-runner「Web 端驱动适配器」执行）

> ⛔ **命令端不直驱**：以下工具由 auto-test-runner 的 Web 驱动适配器内部调用（约定 21），列出仅供理解。

MCP tool 调用（下列工具名以 `mcp__chrome-devtools__*` 占位；**远程 `DRIVER=mcp-remote` 下前缀按 0.1.1.4 实为 `mcp__chrome-{git_user}__*`**，本地 `DRIVER=cli` 走 chrome-devtools-cli 详见 SKILL）：
- `mcp__chrome-devtools__navigate_page(url)`
- `mcp__chrome-devtools__fill(uid, value)` / `fill_form(elements)`
- `mcp__chrome-devtools__click(uid)`
- `mcp__chrome-devtools__wait_for(text/selector)`
- `mcp__chrome-devtools__take_screenshot(...)` / `take_snapshot()`（取 DOM 快照拿元素 uid）
- `mcp__chrome-devtools__evaluate_script(function)`

以上为 chrome-devtools-mcp 当前真实工具名示例；具体 tool 名/签名仍因 MCP server 版本而异，命令端不强约束、**以 MCP server 文档为准**。

#### 2.2.1 ★ 浏览器操作等待时长约束（强制 — 按 Phase 0.0.6 与用户确认的值执行）

> 🔗 **作为 run-context 参数传入 auto-test-runner**：下述 `NAV_TIMEOUT`/`OP_TIMEOUT` 两档值经 2.0.5 的「单步等待上限」传给 skill，由 skill 在感知-执行-校验闭环里对每个驱动调用施加；命令端只负责把用户确认值传入、不自己驱动浏览器。

> ⛔ chrome-devtools-mcp 默认等待（导航 10s / 一般 5s）对本场景偏长。驱动浏览器时**每个 MCP 调用必须显式传 `timeout`**，**禁止用默认 / 禁止传 0**：
>
> - **值来源（强制）**：`NAV_TIMEOUT`（首次打开·导航类）/ `OP_TIMEOUT`（其余操作）由 **Phase 0.0.6 Step 5 与用户确认后**写入 `$TESTPLAN`「五、浏览器操作等待时长」行（Phase 2.1 开头读取）；**默认 NAV=30s / OP=3s**：交互式须经确认（无该行回 0.0.6 收集）；无人值守直接采用 0.0.6 写入的「默认值、未经人工确认」并在报告标注。

| 操作类别 | timeout | 适用 MCP 调用 |
|---------|---------|-------------|
| **首次打开 / 页面导航**（含登录后等跳转、登出跳转、自由巡检 navigate）| `${NAV_TIMEOUT}s`（默认 30）| `navigate` / `new_page` / 登录后等 success_indicator |
| **其余所有操作**（等元素 / 点击 / 填表 / 断言 / 截图前等稳定 / evaluate / 拉 console·network）| `${OP_TIMEOUT}s`（默认 3）| `waitForSelector` / `click` / `fill` / `screenshot` / `evaluate` / `list_console_messages` / `list_network_requests` |

> 说明：① 两档均为**上限**——页面稳定即返回，不空等满；② 某 tool 不支持 `timeout` 入参 → 用其"等待条件 + 轮询间隔"等价封装，间隔仍按两档；③ 超时即判该步失败并按 Phase 2.4 记运行时错误。两档取值缘由与"超时本身即缺陷信号"见 `rationale.md`。

#### 2.2.2 ★ 实时终端日志 + 用例进度展示（强制）

> AI 自动化测试必须**实时**把执行过程打印到终端，便于人盯进度、即时定位卡点；**禁止**"闷头跑完才一次性出结果"。

- **每个 MCP 操作实时打印一行**：`[角色] [HH:MM:SS] <动作>(navigate / fill / click / wait / screenshot / capture) <目标(url 或 selector)> → <结果 + 耗时>`；超时 / 失败用 `❌` 标注，正常 `✓`。
- **用例模式必须展示进度 `<当前>/<总数>`**：总数 = 本角色加载的用例数 `TOTAL`（Phase 2.0 加载用例时得出）；每条用例**开始**打 `⏳ [角色] 进度 5/98 — T-005 <标题> … 开始`、**结束**打 `✅/❌ [角色] 进度 5/98 — T-005 <pass/fail>（耗时 Ns）`。多角色时每个角色各自从 1 计到该角色 `TOTAL`，角色切换时先打印该角色用例总数。
- **关键节点也打印**：登录开始/成功、自由巡检每页、登出、Phase 3 报告落盘路径 + 截图张数。
- `--skip-login` / 无用例（纯自由巡检）模式：无 `i/N` 进度，但仍**逐操作 + 逐页面**实时打印。
- 终端日志**绝不打印明文密码**（同 Phase 0 安全约束，统一显示 `<password hidden>`）。

### 2.3 `--skip-login` 模式

经 run-context 告知 auto-test-runner「跳过登录流程」：本轮测试用例必须是「无需登录」类型（登录页 / 注册页 / 公开介绍页等），skill 直接进入用例执行、不走登录态准备。

### 2.4 ★ 运行时错误全程捕获与 bug 记录（不在用例里也要记）

> 🔗 **捕获归 skill、升级 bug 归命令**：运行时错误的**捕获**由 auto-test-runner 在闭环内完成、写入 `results/{TC-ID}.json` 的 `runtimeErrors[]`；命令端**直接读该数组**做 AIDP 特有后处理（升级 bug → 回写清单 `R-NNN` → #R 通知语义），不自己拉 console/network。

> ⚠️ **核心原则**：AI 自动化仿真测试**不只验证用例断言**。只要测试过程中页面出现**运行时错误**（接口报错 / JS 异常 / 错误 UI），**无论该错误是否属于某条测试用例、无论关联用例的断言是否通过**，都必须记为 bug（"用例没覆盖到 → 不记 bug" 是错的，理据见 `rationale.md`）。

**捕获时机（skill 闭环内执行）**：① 每条用例执行后 ② 登录 / 登出过程——由 auto-test-runner 在这些时机拉 console/network 写入 `runtimeErrors[]`（无用例覆盖页面由 `--free-scan` 覆盖，见 2.1）。

**捕获内容 + 严重度判定口径（★ 单一信源在 SKILL，命令端不复述、不重算）**：`runtimeErrors[].type`（`console` / `network` / `pageError`）的识别条件与 `runtimeErrors[].severity`（P1 / P2 / P3）的分级判据，**一律以 auto-test-runner SKILL `references/execution-methodology.md` 第三节步骤 4「运行时错误捕获」为准**。命令端**直接消费 skill 写入的 `severity` 值**做后续升级 bug，不在本文件另立一套阈值（约定 21）。

**归因 + 去重**：
- 每条运行时错误：**类别/详情/严重度/截图直接取自 skill `runtimeErrors[]`**（`type` / **`message`** / `severity` / `artifact`；**消费点一律读 required 字段 `message`**）；**命令端补充** AIDP 特有的 `触发用例 ID`（取该 result 的 `case_id`，登录类填 `运行时-<页面>`）+ `关联功能`（按 `message` 里的接口 PATH 反查研发需求 REQ 编号，查不到填「待定位」）
- 去重键 = `错误类别 + 归一后的接口 PATH（去掉 query / 路径中的 id 等可变段）或 console 错误首行`；同一错误在多个用例 / 页面重复 → 合并为一条，记 `出现次数` + 列出全部触发点
- **预期内错误排除**：权限测试用例（如"普通用户访问管理页应被拒"）预期的 401/403/无权限提示**不算 bug** —— 这类用例必须在用例正文显式标注 `预期错误: 401`（或 `预期错误: 无权限`），命令端据此排除；**未标注的 4xx/5xx 一律记 bug**

> ★ **`free_scan` 开启时的巡检项：单列、不自动升级 bug（口径以 SKILL 为准，命令端不得加码）**
> `entry_kind="free-scan"`、`case_id` 前缀 `运行时-`。SKILL 的处置是三条：
> ① **不计入用例统计**（`total` / 通过率 / 自动化率 / 各模块通过情况一律不含，`gen_report.split_entries` 分流）；
> ② **不进缺陷列表、不自动记 bug**，单列报告 **§2.6 自由巡检**（表：页面 / 导航结果 / 运行时错误数 / 最高级别 / 摘要），**由人确认后**再转 bug 或补成正式用例进下一轮；
> ③ **通过准则不受影响**（P0=100% / P1≥95% / P2≥80% 只对用例生效）。
> 
> **命令端据此的行为**：Phase 2.4 的 `R-NNN` 升级链路**只消费普通用例（`entry_kind` 缺省/`case`）的 `runtimeErrors[]`**，**不把巡检项自动写进「问题汇总清单」**（理据见 `rationale.md`）。巡检结果去向 = 报告 §2.6 + #R/#F 里程碑通知提一句，由人决定是否转 bug。
> **超限 block 项**（`运行时-<已达巡检上限>`）同属巡检项、同样**不自动写入问题汇总清单**：作为待确认项落 §2.6、在 #F 通知中列出，报告须如实写出「巡检未覆盖 N 页」。

**升级为 bug（核心动作）**：
1. 即便触发用例断言 **PASS**，只要捕获到运行时错误 → 该用例在报告里标 `✅ 通过（但有运行时错误 → 见问题汇总 ②）`，并把运行时错误写入 Phase 3「问题汇总（待 sprint-bugfix）」的「**② 运行时错误（非用例断言）**」分类
2. 运行时错误 bug 与「用例失败」bug **分两类**写入问题汇总（「来源」列区分），**都**让 `/sprint-bugfix` 接力修复
3. **全 PASS 但有运行时错误**的场景：里程碑通知 #R **不报「全通过 ✅」**，改报「⚠️ N 用例通过但捕获 M 个运行时错误（已记 bug）」
4. 问题汇总 ② 的每条运行时错误**回写到** `docs/testing/{TARGET_VERSION}/研发自测/` 主用例文档（或 `正式用例/` 测试人员用例）末尾的「问题汇总清单」表，让 `/sprint-bugfix` 扫描时一并拾取（与 `/sprint-batch` Step 6 回写口径一致）：
   - **沿用清单既有 6 列结构**（序号 / 用例 ID / 问题描述 / 严重程度 / 复现步骤 / 状态），**不新增列**（清单由 dev-manual-testcase SKILL 生成，按约定 21 命令端不改其表结构）
    - 列映射：**序号 = `R-NNN`**（`R-` 前缀 = chrome 运行时错误，与失败用例 `C-NNN`、零散 bug 各自独立编号，互不复用）。完整列映射见 `rationale.md`「运行时错误写入缺陷清单」。
   - **幂等**：回写前先 grep 清单是否已有同去重键的 `R-` 行（按归一接口 PATH / console 首行）→ 已存在则跳过，避免 /loop 重复跑产生重复行
   - **职责边界（★ 按调用方分流，⛔ 不是"C-NNN 一律归 sprint-batch"）**：`R-NNN` 运行时错误恒由本链路写。
     `C-NNN` 失败用例的归属**取决于本轮是否真有 sprint-batch Step 6.5 在跑**：
     - **由 `/sprint-batch` Step 6 调起** → C-NNN 归 Step 6.5 写，本链路不写（两类前缀隔离不双写）。
     - **★ 其余一切路径（7×24 双 loop 的独立 `/sprint-aiauto-test` / 链外直达 / standalone）→ 本链路
       自己写 `C-NNN`**。⛔ 这条不能省：autopilot 链内**恒传 `--skip-aiauto-test`**，Step 6 整段跳过、
       6.5 从不执行；若仍按"C-NNN 归 sprint-batch"，则 **7×24 常态下失败用例永远没有写入方** ——
       `/sprint-bugfix` 读问题汇总清单读到空 → 自动修复循环空转 3 轮 → 按 retest-cap 冻结，
       而冻结原因与真因（失败用例根本没被登记）毫无关系。
     - 写法与 `R-NNN` 完全同构：沿用清单既有 6 列、不新增列、同款 grep 幂等（去重键 = 用例 ID）。

