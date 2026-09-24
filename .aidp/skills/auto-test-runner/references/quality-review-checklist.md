# auto-test-runner 质量检查清单(8 维度)

**★(条件启用)WebMCP 达成路径如实标注核查(折入本维度 · 计数不变):** **仅当**旧 Web 显式启用或新 `client_mcp` 声明 Web+WebMCP 时核;否则只跳过本 Web 子项,非 Web 应用能力四态仍按通用项核,不核、不告警、**报告里不留位置**(⛔ 严禁自行探测是否启用)。启用时核:用了 **WebMCP 工具调用**达成的用例,其 `driver` 字段与证据须体现是**经 WebMCP** 而非**纯 CDP 模拟点击**,⛔ **不得混为一谈**——两者失败形态完全不同(工具调用失败 = 业务能力或契约问题;模拟点击失败 = 界面或定位问题),混记会让**缺陷归因整体走偏**。另核:因驱动版本不足/取不到而 block 的用例,其 `block_reason` 落 `webmcp-driver-too-old` / `webmcp-driver-version-unknown`,并出现在「缺陷列表 + 遗留风险」里。**不通过标志:** WebMCP 达成的用例证据只有截图、看不出走的哪条路径;或版本类 block 被静默降级成「就当没有 WebMCP」而在报告里**全绿式消失**。

**★报告两轴分列(折入本维度,条件启用):** 仅调用方 `client_mcp.enabled: true` 或旧 Web 显式启用时核;两类均未启用 → **不核、不告警、报告不留行**(门控铁律;⚠️ 漏门控会让未启用项目凭空多一行)。 报告中的 `driver`/测试驱动统计不等于应用工具调用;`application_mcp` 四态各有来源,未取到写未取到,不能从声明推入口、从入口推注册、从注册推调用。旧 Web `webmcp` 和新字段同存只算一份应用事实,冲突判不通过。

**★WebMCP 四项事实(折入本维度,仅 Web+WebMCP 入参启用时):** 四项事实分别登记、`driver=cli` 不等于 WebMCP、`registered_tools=0` 的专项用例须 block、路径 A 本页清单不得与路径 B 浏览器全量清单混作同一作用域、无调用证据的 `mechanism=webmcp|mixed` 判不通过。⚠️ **判据全文的单一信源是 [`driver-web-webmcp.md`](./driver-web-webmcp.md)**,本行只列「查什么」——⛔ 别把判据再抄一份回来:同一判据三处并存是本仓库登记的最高频漂移源。
**目标:** 报告含 一概况 / 二汇总(2.1 数据·2.2 各模块·2.3 缺陷列表·2.4 执行明细·2.7 耗时分布)/ 三结论(3.1 上线条件·3.2 遗留风险·3.3 改进建议),不缺章节;统计口径(通过率/自动化率)由脚本聚合、与明细一致。证据列须原样透传 `evidence[].artifact`,同一轮允许 WebP/PNG/JPEG 混合,不得按 TC-ID 推断扩展名。**注意 `gen_report.py --md` 只产出「二」章**,「一」「三」须按 [`../assets/report-template.md`](../assets/report-template.md) 由报告子 Agent 补写——**只交脚本输出即判本维度不通过**。
**自动化辅助:** `python3 <SKILL_DIR>/scripts/gen_report.py <round目录> --json` 输出 `verified_pass_without_evidence` 计数,非 0 即不通过,并输出 `direct_pass_without_evidence` 供报告单列;另跑 `python3 <SKILL_DIR>/scripts/check_result.py <round目录>/results/ --json` 校验**结果 JSON 形状与 artifact 真实性**(`evidence`/`runtimeErrors` 须为对象数组、元素含 `artifact` / `type`+`message`+`severity`,`artifact` 必须是当前 `round/evidence` 内的相对路径（禁绝对路径/`..`/旧轮次，且 evidence 根不得是符号链接）,非空时实际文件必须存在且非 0 字节;截图只允许 `.webp/.png/.jpg/.jpeg` 且最小容器结构须匹配扩展名（仅魔数的截断空壳不算）;results 目录/结果 JSON/round/evidence 根均不得是符号链接;新截图文件名须按 `{case_id}-step{step}` 与当前用例对应（历史 `{case_id}-{step}` / `{case_id}_步骤{step}` 兼容告警）;跨 `evidence`/`runtimeErrors` 的同一截图不得登记多格式副本,递归磁盘索引也不得残留未登记的同主干其它格式（含 `.PNG` 大小写、非兼容格式与符号链接变体）;`status` 含 `na` 且 `na` 有非空理由,`block_reason` 落枚举,`db_assertion.match=false` 必判 fail)。⚠️ **形状不对不只是不好看**:`evidence` 写成字符串数组曾直接崩掉整份报告聚合(已改为兼容解析 + 形状告警);**路径字符串非空也不等于有证据**——文件不存在仍判 Critical;`block_reason` 漏标枚举会让**纯环境阻塞被误计成产品缺陷**。`gen_report --json` 的 `shape_warnings` 非空时,须把这些告警写进报告「三、结论 → 遗留风险」。

**★应用 MCP 业务能力事实(折入本维度,条件启用):** 调用方 `client_mcp.enabled: true` 或旧 Web 显式启用时,`check_result.py` 逐项核 `application_mcp` 的项目声明/入口实连/当前应用实例注册/本用例真实调用及每态来源;测试驱动即使走 MCP 也不构成产品工具调用证据。非 Web 无证实的应用自有服务/桥接不得编入口;专项缺入口/工具 block、普通 UI 继续。Web 旧 `webmcp` 字段可兼容,新旧冲突须报错,Web 专项不重复执行一次通用判据。未启用时不增 QR 行,原 8 维不变。

**★运行真实性前置(折入本维度):** 本轮新结果运行 `check_result.py <results/> --require-runtime-preflight --json`;仅 旧 Web `webmcp_enabled: true`（或 `webmcp.enabled: true`）、或 `client_mcp.enabled: true` 且客户端=Web、实现形态=WebMCP 时追加 `--webmcp-enabled`（只约束 `client=web` 的结果,混合目录中的移动/小程序/桌面结果不因此假红）。`runtime_preflight.required` 应覆盖实际认证实例/角色、登录后的**项目受保护接口**、前端部署指纹,仅需故障注入的用例再覆盖注入能力;逐项有来源/时间/证据。受保护接口 401、OAuth2 失效、指纹不符或注入未生效不得记 pass,只 block 相关用例并继续其余。旧结果离线复核不带新开关,避免历史结果假红;QR 仍人工核对 required 是否少列了该用例实际依赖。
**★(条件启用)WebMCP `invoke` 能力归属核查(折入本维度 · 计数不变):** **仅当**旧 Web 显式启用或新 `client_mcp` 声明 Web+WebMCP 时核这一条;否则只跳过本 Web 子项(非 Web 通用应用能力仍须核),不核、不告警、**不在报告里留行**(⛔ 本 Agent 严禁自行探测是否启用)。启用时核:① **WebMCP 不被当成第五个「端」** —— 它是 **Web 适配器的可选补充能力 `invoke`**(列出/调用页面登记的工具),端专有调用约定只落 [`driver-web-webmcp.md`](./driver-web-webmcp.md),**方法论层零改动**;② 该文件已被 `driver-adapters.md` 索引登记;③ 其它端明写「本端不适用」而非留空;④ `detect_drivers.py --webmcp` 的版本校验存在且**不影响退出码**(版本不足 ≠ 驱动缺失);⑤ 版本不足/取不到时标 `block(webmcp-driver-too-old)` / `block(webmcp-driver-version-unknown)`,**⛔ 不得静默降级为「就当没有 WebMCP」**。**不通过标志:** 把 WebMCP 建成第五个端类型;端专有 API 写进方法论层(应被 `check_layer_isolation.py` 拦下,维度 1);版本不足被静默降级(这一整类用例会**全绿式消失**、报告看不出漏测);未启用时仍在 run-context 或报告里留了位置。
**★截图格式的两层归属核查(折入本维度):** 方法论层只声明 `capture(标签) → 实际证据路径`、每次 capture 只生成一种格式、扩展名由适配器决定,不得写死 WebP 参数;`driver-web.md` 才声明 Chrome DevTools MCP/CLI 优先 WebP quality=90、明确不支持时本次只生成 PNG,Playwright 保持原生 PNG且不转码;移动/小程序/桌面端保持各自原生 PNG。**不通过标志:** `quality=90`/`format=webp` 泄漏进方法论层;或引入 Pillow/Sharp/ImageMagick/cwebp 转码;或同一次 capture 留 WebP+PNG 双份。

> 执行与报告产出后,由**独立子 Agent**逐维核验。主流程禁止在当前上下文内联跑检查,派独立子 Agent 回传精简结构化报告(每维度通过/不通过 + 证据 + 修订建议),据报告决定重跑或修订,循环至通过或达轮次上限。

---

## 8 维度检查清单

> 分三组:**两层解耦类(维度 1-2)** + **执行完整性类(维度 3-6)** + **产出规范类(维度 7-8)**。

### 🧱 一、两层解耦类

#### 维度 1:方法论层零端专有 API(**Critical**)

**目标:** 方法论层(执行流程/模式分级/闭环/失败/断点/报告)只调四原子能力(locate/act/observe/capture),**严禁**出现任何端专有 API(如 `browser_click` / `driver.find_element` / `page.tap`)。

**不通过标志:** 方法论层文本或执行编排中直接出现端专有调用,未经四原子能力抽象。

**自动化辅助:** `python3 <SKILL_DIR>/scripts/check_layer_isolation.py <SKILL_DIR>` 扫方法论层文档是否泄漏端专有 API。

#### 维度 2:驱动适配层四能力完备(**Critical**)

**目标:** 每个声称支持的端,适配器都完整声明 locate/act/observe/capture 四能力映射 + 前置条件;能力探测分支存在。**且各端标注了成熟度**(Web=已验证/移动=部分/小程序=预留未验证/桌面=预留未验证),下游不误以为四端等价可跑。

**不通过标志:** 某端缺任一原子能力映射;或 detect_drivers 无该端探测分支;或适配器矩阵/`driver-adapters.md` 的端文件索引未标注各端成熟度;或某端的 `driver-<端>.md` 缺失/未被 `driver-adapters.md` 索引登记。

**★web 探测特例核查:** detect_drivers 对 web 须按「npm 包 或 本机 Chrome 任一即可用」放宽,且 `hint` 说明 chrome-devtools MCP 变体属运行时能力(脚本探不到);方法论「探测→block」须写明**仅三者(MCP 未挂载+无 Chrome+无 npm)皆空才 block web**,不因 npm 空探测误杀主场景。

**★web 端本地 CLI↔MCP 变体区分核查(折入本维度):** `driver-web.md` 须明确**本地 CLI = `chrome-devtools` 命令**(CLI 直调、同机、不读 `.mcp.json`、驱动本机独立 Chrome;`chrome-devtools-cli` 只是技能名、非命令/二进制)**与连共享/远程 Chrome 的 MCP 变体 `mcp__chrome-<git_user>__*` / 无后缀 `mcp__chrome-devtools__*`(注册 `chrome-<git_user>` 写 `.mcp.json`)不是等价次选**;detect_drivers(位置参数 `web`,即 `detect_drivers.py web`)输出须**区分就绪态**——`local_cli_available`(=cli 命令真能跑,唯一凭据,非「npm 包已装」)/ `npm_pkg_available`(仅远程 MCP 能力信号,独立、不并入 cli)/ `mcp_variant_registered`,并对「仅 MCP 变体可用、CLI 缺失」标 `manual_confirm_required=true`(需人工确认、非自动可用)+ 给同机场景「用 CLI、勿用 MCP 变体顶替」的 `boundary_advice`。**不通过标志:** driver-adapters 把两者当等价降级目标;或 detect_drivers 把「npm 包已装」等价判 cli 可用 / 探错命令名 `chrome-devtools-cli` / 未区分就绪态 / 「仅 MCP 变体、缺 CLI」被当自动可用。

**★observe 运行环境通道(env)各端声明核查(折入本维度):** 每个声称支持的端,其 `driver-<端>.md` 须声明 observe **运行环境通道**的五个端无关信号(`runConfig` / `renderSignals` / `automationSignals` / `viewportSize` / `instanceOwnership`)分别怎么落地,或**明确写「本端不适用」**(留空视为漏写、不视为不适用);端专有的取证方法(读什么属性、调什么命令)**只允许写在 `driver-<端>.md`**,方法论层与 `driver-adapters.md` 端无关部分只出现信号名。**判据有效性须实测复核**——已知反例:「窗口外框尺寸为 0 即无头」在新版本下已失效(见 [`driver-web.md`](./driver-web.md)「三·补三、Web 运行环境取证」的实测证否表),照抄失效判据会产出自信的错误结论。**适用范围:** 只针对**被测端**(web / miniprogram / mobile / desktop)。`driver-db-assertion.md` **不是被测端**(它是与被测端正交的可插拔断言驱动),不适用本条,缺 env 通道声明不算问题。

**不通过标志:** 某**被测端** env 通道整段缺失且未标「不适用」;或端专有取证方法写进了方法论层(应被 `check_layer_isolation.py` 拦下,维度 1);或写入的判据未经实测复核。

**★DB 断言驱动 + 前置数据编排的两层归属核查(折入本维度,Critical):** 「值级断言 / 数据真值对账」与「前置数据造删数」的**抽象需求**须落在方法论层(execution-methodology.md 的「值级断言硬约束」「不可视断言窄口径豁免」「第九节 前置数据编排」),而**具体 SQL / DB MCP 工具名只允许出现在 [`driver-db-assertion.md`](./driver-db-assertion.md) 适配层**;DB 断言驱动须声明其 `assertData(等价SQL, 页面取值)→{sqlValue,pageValue,match}` 能力 + 数据源来源(会话已连 DB MCP 或 run-context `datasource`)+ 缺数据源时降级 `block(precondition-unmet)`。前置数据编排须走 DB 驱动(SQL)或第二隔离会话(UI),编排后 observe/SQL 核对就绪、置不到判 `block(precondition-unmet)` 不带脏前置硬跑。**不通过标志:** 方法论层文档出现 SQL/`mcp__..._*` 端专有调用(应被 `check_layer_isolation.py` 拦下,维度 1);或 DB 断言驱动/前置编排缺就绪校验与降级;或把 DB 对账当默认全量断言(应仅 `[双源对账]` 用例窄口径启用)。

**★(条件启用)WebMCP `invoke` 能力归属核查(折入本维度 · 计数不变):** **仅当**调用方传入 `webmcp_enabled: true` 时核这一条;**为 false 或未传 → 整条不适用**,不核、不告警、**不在报告里留行**(⛔ 本 Agent 严禁自行探测是否启用)。启用时核:① **WebMCP 不被当成第五个「端」** —— 它是 **Web 适配器的可选补充能力 `invoke`**(列出/调用页面登记的工具),端专有调用约定只落 [`driver-web-webmcp.md`](./driver-web-webmcp.md),**方法论层零改动**;② 该文件已被 `driver-adapters.md` 索引登记;③ 其它端明写「本端不适用」而非留空;④ `detect_drivers.py --webmcp` 的版本校验存在且**不影响退出码**(版本不足 ≠ 驱动缺失);⑤ 版本不足/取不到时标 `block(webmcp-driver-too-old)` / `block(webmcp-driver-version-unknown)`,**⛔ 不得静默降级为「就当没有 WebMCP」**。**不通过标志:** 把 WebMCP 建成第五个端类型;端专有 API 写进方法论层(应被 `check_layer_isolation.py` 拦下,维度 1);版本不足被静默降级(这一整类用例会**全绿式消失**、报告看不出漏测);未启用时仍在 run-context 或报告里留了位置。

**★`resetSession` + `driverAlive` 声明核查(折入本维度 · 计数不变):** 各 `driver-<端>.md` 须声明 `resetSession`(换账号/清会话/卡死自愈,**两场景共用一套动作**)与 `driverAlive`(健康探活)的落地方式,或明写「本端不适用」;跨角色套件之间须有「重建干净会话 → `observe` 核对登录态已清空 → 登录新角色 → 核对角色 = 目标角色」四步留痕。**不通过标志:** 跨角色套件直接沿用上一角色会话、无角色核对(用错角色跑出的权限类结论全错且看上去正常)。

### 🔁 二、执行完整性类


#### 维度 3:进度状态机无残留(**Critical**)

**目标:** tasks.md 全部落定为 `[√]` 或 `[!]`,无 `[ ]`(待执行遗漏)/ `[>]`(执行中断)残留;报告在 checker 安全检查点之后生成。

**自动化辅助:** `python3 <SKILL_DIR>/scripts/tasks_state.py scan <tasks.md>`(残留 `[ ]`/`[>]` → 退出码 1)。

**★执行选集核查(折入本维度 · 计数不变):** 若本轮用 `tasks_state.py init --select smoke|regression` 只跑了子集,tasks.md 头部**必须有子集留痕行**(`> ⚠️ **本轮为子集**…`),且报告须据此说明「通过率与 P0=100% 准则仅对该子集成立」。**不通过标志:** ① 子集 tasks.md 无留痕行——`scan` 对子集恒报「无残留」、报告读者看不出只跑了一部分,**全绿的子集会被误读成全量通过**;② **新 build 回归轮用了 `--select`**(违反第五节跨 build 全量重跑硬边界,`regression` 尤其:那正是该硬边界要禁的「只复跑被修用例」)。

**★`--select` 解析未收窄:** 改过 `PRIORITY_RE` 后须跑 `python3 <SKILL_DIR>/scripts/tasks_state.py selftest`(含 7 条优先级形态断言)。收窄的表现是**静默漏跑**——P0 用例没进冒烟集,不报错、跑完还是绿的。

#### 维度 4:失败分级与不中断

**目标:** 每条 fail/block 有 error/证据;重试未超上限(≤3);全程未因失败挂起等人;所有等待/探测有硬上限。

**不通过标志:** 存在无原因的 fail/block;或执行日志显示中途停下等人工输入。

**★驱动卡死自愈核查(折入本维度):** 出现**驱动进程级无响应**时,须先走「健康探测(`driverAlive`)→ `resetSession` 重建 → 恢复登录 → `observe` 恢复检验 → 断点续跑」,**连续 `driver_heal_retry_limit`(默认 3)次自愈失败**才落定 `block(driver-hung)` + 证据(探活输出 / 重建返回 / 时间戳 / 重试次数)。**不通过标志:** 驱动卡死时每条用例各自把超时/重试耗尽后逐条 `block`(既救不活也拖慢整批);或未达自愈上限就直接 `block`;或把**单元素 `locate` 失败**误判成驱动卡死去重建驱动(两者必须区分);或自愈动作越界改了业务代码。**端相关降级:** 某端不提供 `driverAlive`/`resetSession` 时声明「本端不适用」并退回旧路径,不判不通过。

**★self-heal 失败反思核查(折入本维度):** 凡 `self_heal_applied=true`(触发过状态恢复重试)的用例,结果 JSON 应写非空 `self_heal_trace`(`cause` 根因 / `recovery` 恢复动作+observe 检验结果 / `outcome`∈`recovered-pass`|`still-fail-block`);`recovery` 的证据须来自 execution-methodology「observe 恢复检验清单」的可观测信号,不写不可视断言。**该字段可选:非 self-heal 用例省略或 null 不算问题**(缺省行为与旧版本一致)。**不通过标志:** self-heal 用例缺 `self_heal_trace` 或 `outcome` 非枚举值。

**★运行时错误捕获核查(折入本维度):** 每条用例执行后须通过 `observe` 的运行时错误通道拉一次 console/network,把 console 报错 / network 非 2xx / 页面级错误 UI 写入 `runtimeErrors`(pass 用例也拉);Web 端该通道齐备时不得整体缺该字段。**端相关降级:** 移动/桌面/小程序端若驱动不提供 console/network 通道,`runtimeErrors` 留空属正常(不判不通过)。**不通过标志:** Web 端用例集全体 `runtimeErrors` 字段缺失(未做捕获),或字段结构不符 `{type, message, detail, severity, artifact}`。

**★前置数据面探测核查(折入本维度):** 若用例含结构化 `前置探测`/`ED-NNN`,必须在浏览器连接前按 `ED-NNN` 去重批量探测;满足才进浏览器,不满足直接 `block(precondition-unmet)` 并使用声明的缺位 detail;探测调用失败/非 2xx 不得伪装成合法空结果或前置缺位,应记录 `probe-error` 并按网络/环境错误归因。报告或结果需能回查探测项、复用用例和证据。

**★客户端故障注入核查(折入本维度):** 使用故障/变慢/空响应注入时,只能验证前端呈现,不得改服务端配置、代码或业务数据;需要服务端真实状态的用例不能用注入替代。每组注入必须配「全端点 `200 + 空数据`」阳性对照,证明“元素 0 命中”不是页面未走到渲染路径;注入未生效或阳性对照缺失不得判通过。

#### 维度 5:证据取证按模式达标(**Critical**)

**目标:** verified / self-heal 模式的每条 pass 都有非空 `evidence`(截图/元素文本/计数);「没有证据的 pass」判不通过。direct 模式的 pass 也必须至少有一条轻量事实(`evidence` 含实际值、命中文案、列表计数或产物路径),不要求完整截图;缺失只报 Important,不阻断,报告单列「无依据的 direct pass」数量。

**自动化辅助:** `python3 <SKILL_DIR>/scripts/gen_report.py <round目录> --json` 输出 `verified_pass_without_evidence` 计数,非 0 即不通过,并输出 `direct_pass_without_evidence` 供报告单列;另跑 `python3 <SKILL_DIR>/scripts/check_result.py <round目录>/results/ --json` 校验**结果 JSON 形状**(`evidence`/`runtimeErrors` 须为对象数组、元素含 `artifact` / `type`+`message`+`severity`,`status` 含 `na` 且 `na` 有非空理由,`block_reason` 落枚举,`db_assertion.match=false` 必判 fail)。⚠️ **形状不对不只是不好看**:`evidence` 写成字符串数组曾直接崩掉整份报告聚合(已改为兼容解析 + 形状告警);`block_reason` 漏标枚举会让**纯环境阻塞被误计成产品缺陷**。`gen_report --json` 的 `shape_warnings` 非空时,须把这些告警写进报告「三、结论 → 遗留风险」。

**★环境类阻塞分类核查(折入本维度):** 报告 §2.3 的「产品缺陷」计数**不得包含纯环境阻塞**——环境类 `block_reason`(`driver-missing`/`driver-hung`/`precondition-unmet`/`network-error`/`env-unavailable`/`account-invalid`)或执行方显式 `is_environment_issue=true` 的用例应编号 `ENV-NNN`、归「环境问题」。**不通过标志:** 一批全 `block(precondition-unmet)` 的用例被编号成 `BUG-xxx` 计入产品缺陷。

#### 维度 6:优雅降级正确

**目标:** 驱动缺失时标 `block(driver-missing)` + 补齐建议 + 继续跑其它端,未硬失败、未挂起。

**★Web 本地 CLI↔MCP 变体硬边界不自动互顶核查(折入本维度):** 「同端多驱动」自动次选逻辑须写明该边界——**端无关口径落 `driver-adapters.md` 三、「同端多驱动」,Web 端专有细则落 [`driver-web.md`](./driver-web.md)「三·补一」**;须写明 Web 端本地 CLI(`chrome-devtools` 命令)缺失时**不得静默降级到连共享/远程 Chrome 的 MCP 变体**(`mcp__chrome-<git_user>__*` / 无后缀 `mcp__chrome-devtools__*`);须给可执行出路——先按「命令名探错 / npm 全局 bin 未在 PATH」诊断修复回落 cli,短期修不了时可**显式声明**降级到插件自起隔离实例 `mcp__plugin_chrome-devtools-mcp_chrome-devtools__*`(本机独立、非共享),且 driver 字段须如实取值 **`cli | mcp-remote | mcp-plugin-fallback | manual`**、严禁静默切换或用了 plugin 却填 `cli`;Playwright/本机 Chrome 仍是合法同机次选。**不通过标志:** 把连共享/远程实例的 MCP 变体当 CLI 缺失时的自动降级目标、未告警即静默连共享实例;或缺 CLI 时无可执行出路;或实际驱动与 driver 字段不符;或把 Web 专有的命令名/MCP 工具名写回 `driver-adapters.md` 端无关部分(应只留端无关口径)。

**★Web 驱动执行前「实例归属」防呆核查(折入本维度):** `driver-web.md`/execution-methodology.md 须写明 Web 驱动**连接后、跑用例前**读一次页面/标签集合,若出现非本任务测试 URL 的业务页/非目标标签(疑似连到共享/他人 Chrome)→ **告警并停下人工确认**,确认前不在该实例上执行用例。**端相关降级:** 移动/桌面/小程序端各自独立会话、无此风险时跳过属正常。**不通过标志:** 缺该防呆,或命中疑似共享实例仍静默继续执行。

### 📄 三、产出规范类

#### 维度 7:报告章节完整(**Critical**)

> **章节口径:** 顶层是 **3 大章**(一概况 / 二汇总 / 三结论),必备内容块共 **7 个**(概况 · 2.1 汇总数据 · 2.2 各模块 · 2.3 缺陷列表 · 2.4 执行明细 · **2.7 耗时分布** · 结论三小节)。历史上叫「六章节」指的是内容块数、**不是顶层标题数**——按顶层一级标题去核会得到假不通过。⚠️ **2.7 于 2026-09-10 加入必备集**(2.5 self-heal 追溯 / 2.6 自由巡检仍是可选节,无数据整段省略是正确的);**2.7 无耗时数据时也不得省略**,须照脚本输出写「本轮 N 条全部未采集」——**空表/缺节都会被读成「都很快」**,而事实是「没测量」。

**目标:** 报告含 一概况 / 二汇总(2.1 数据·2.2 各模块·2.3 缺陷列表·2.4 执行明细·2.7 耗时分布)/ 三结论(3.1 上线条件·3.2 遗留风险·3.3 改进建议),不缺章节;统计口径(通过率/自动化率)由脚本聚合、与明细一致。**注意 `gen_report.py --md` 只产出「二」章**,「一」「三」须按 [`../assets/report-template.md`](../assets/report-template.md) 由报告子 Agent 补写——**只交脚本输出即判本维度不通过**。

**★自动化率按 block_reason 细分核查(折入本维度):** 2.1 汇总数据除旧 `auto_rate`(=(Pass+Fail)/总数,口径保留)外,应含 **自动化覆盖率 `autoCoverRate`**=(总数−block(driver-missing))/总数、**自动化成功率 `autoSuccessRate`**=(Pass+Fail)/(总数−block(driver-missing)),由 `gen_report.py` 据已有 `block_reason` 枚举派生。**向后兼容:driver-missing=0 时三指标数值一致**(此时不视为缺失/异常)。**self-heal 追溯核查:** 有 self-heal 触发时,报告(2.5 或明细/遗留风险)应展示 `self_heal_trace` 的 cause/outcome;无 self-heal 触发时该段省略,与旧版本一致。**不通过标志:** 存在 driver-missing 却未给出两派生指标;或有 self-heal 触发却未在报告呈现 trace。

**★概况环境事实字段来源核查(折入本维度,Critical):** 「一、测试概况」的**环境事实类**字段(渲染模式 / 浏览器版本 / viewport / 是否复用已有实例 / 被测 URL / 登录角色)须**全部取自环境准备阶段落盘的 `round-{M}/env-facts.json`**,并**逐字段带来源标注**(五类枚举:显式指定 / 复用已有实例(来源) / 无头不可用降级(原因) / 运行取证(方法) / 未取到(原因));取不到的字段写「未取到(原因)」而非模板默认或推断值。**「复用已有实例」分支下命令传入参数不生效,渲染模式不得标「显式指定」。** 同一口径延伸到**统计类**字段:必须来自 `results/*.json` 经 `gen_report.py` 聚合,不手工计数、不照抄模板示例数字。

**★环境探针档案核查(折入本维度,可选):** 若 run-context 提供上一轮「环境探针档案」,只能将其作为启动前提示/预热,不得当作权威契约或直接生成 pass/fail/block;本轮实际观测与档案冲突时必须以本轮为准。档案应覆盖其声明的环境事实类别(驱动通道限制、鉴权头形态、未登录响应、三类取证可用性、元素定位方式、已知需重试项),并带来源轮次/证据;缺失档案不阻断执行。

**★数据源归属校验核查(折入本维度 · 计数不变):** 配了 `datasource` 且本轮有 `[双源对账]` 用例或 SQL 造删数时,`env-facts.json` 须有 `datasourceOwnership`(+`Source`)且结论为 `verified` 才允许出对账结论。**不通过标志:** 结论为 `mismatched`/`unverified`/缺失,报告里却仍出现基于该库的 `db_assertion.match` 结论(用错库的对账**比不做对账更危险**——结论要么假性全红要么凑巧全绿,且看上去笃定)。规则见 execution-methodology 第十一节。

**★(条件启用)WebMCP 达成路径如实标注核查(折入本维度 · 计数不变):** **仅当**调用方传入 `webmcp_enabled: true` 时核;**为 false 或未传 → 整条不适用**,不核、不告警、**报告里不留位置**(⛔ 严禁自行探测是否启用)。启用时核:用了 **WebMCP 工具调用**达成的用例,其 `driver` 字段与证据须体现是**经 WebMCP** 而非**纯 CDP 模拟点击**,⛔ **不得混为一谈**——两者失败形态完全不同(工具调用失败 = 业务能力或契约问题;模拟点击失败 = 界面或定位问题),混记会让**缺陷归因整体走偏**。另核:因驱动版本不足/取不到而 block 的用例,其 `block_reason` 落 `webmcp-driver-too-old` / `webmcp-driver-version-unknown`,并出现在「缺陷列表 + 遗留风险」里。**不通过标志:** WebMCP 达成的用例证据只有截图、看不出走的哪条路径;或版本类 block 被静默降级成「就当没有 WebMCP」而在报告里**全绿式消失**。

**自动化辅助:** `python3 <SKILL_DIR>/scripts/check_env_facts.py <round目录>/env-facts.json --report <报告.md> --json`(非 0 退出即不通过;`--strict` 把 warn 也计入)。**机检覆盖**:字段齐全与类型、事实字段⟷`XSource` 双向成对、来源枚举与形态、`null`⟺「未取到」、模板占位残留(值/来源/报告概况三处)、复用实例约束、概况渲染模式与「是否复用」行的一致性。

**★人工项(机检覆盖不到,须子 Agent 目视):** ① **run-context 第六节 ⟷ `env-facts.json` 逐字段一致**——run-context 该节是**只读镜像**,若有人手填了期望值冒充事实,脚本读不到该文件、发现不了,冲突一律以 `env-facts.json` 为准并判不通过;② 来源标注**说明文本是否名副其实**(如写「运行取证(读了 X 信号)」但该信号在当前版本已被证否)——硬门只查自洽,查不了内容造假。

**不通过标志:** 缺 `env-facts.json`(视为未取证);某事实字段缺来源标注或来源形态不合法;值为 null 却未写「未取到(原因)」(或反之——声明未取到却填了值);概况渲染模式与取证结果矛盾(**典型:无图形界面的远程机器只能无头运行,报告却写「有头」**);`reusedInstance` 为 true 或未取到却把渲染模式标为「显式指定」;概况残留模板占位;run-context 第六节与 `env-facts.json` 不一致。

**★自由巡检 §2.6 核查(折入本维度 · 计数不变):** `results/` 中存在 `entry_kind:"free-scan"` 条目时,报告**必须有 §2.6 自由巡检**;且 **§2.4 用例执行明细里不得出现巡检项**(它没有断言,冒充用例会让 2.4 行数 ≠ 2.1 用例总数、报告自相矛盾)。**不通过标志:** ① 有巡检结果却缺 §2.6;② 巡检项混进 §2.4 或缺陷列表;③ 巡检因 `free_scan_max_pages` 截断,却没有按第十二节 12.6 单写一条「已达巡检上限」的 block 巡检项列明被跳过页面(**静默截断会让「巡检过了」名不副实**)。⚠️ 2.5/2.6 均为**可选节**:无对应数据时整段省略是正确的,不得据此判缺章节。

**★`capture_warnings` 口径提醒(避免假不通过):** P3 告警类受 run-context `capture_warnings` 控制、**默认关**;P1/P2 恒记录。**`runtimeErrors` 里没有 P3 条目不等于采集不全**,不得据此判「运行时错误采集不完整」。

**★用例族失败锁 Critical 核查(折入本维度,Critical):** `[回归]`(`is_regression=true`)、`[PRD存在性]` 与 `[文案一致性]` 用例族失败(fail / **非环境类**的 block)时,§2.3 缺陷等级须**锁 Critical、覆盖优先级映射(P0→P1…)、不许降级为 Important**;`gen_report.py` 已在 `FAIL_LEVEL` 映射前判用例族(`is_regression` / `[PRD存在性]` / `[文案一致性]` / `type=回归` 标记),命中即锁 Critical(**环境类 block 除外——环境没起来不算产品缺陷**)。`[文案一致性]`(语义/口径变更后旧文案残留反向断言命中或新语义未落地)与前两族同级锁定。**不通过标志:** 回归/PRD存在性/文案一致性用例族失败仍按用例优先级降级(如 P2 失败判成 P3),未锁 Critical;或报告缺陷列表未体现该锁定。

#### 维度 8:输入对接标准用例格式

**目标:** 用例来源为 dev-manual-testcase 标准格式(套件 `SUITE-*`,兼容 `测试套件`/`TS-` 形态 / 用例 `TC-*`,「用例」二字可省 /优先级/类型/反向/覆盖/四要素),按 [`usecase-format.md`](./usecase-format.md) 契约解析、执行未自造用例;结果 JSON 字段齐全(见 report-format.md schema)。操作对象为语义文案时才可跨端 locate;若用例操作对象是 DOM/CSS 选择器/xpath 导致无法 locate,应标 block 并注明需上游修正,不臆造选择器。

**自动化辅助:** `python3 <SKILL_DIR>/scripts/tasks_state.py selftest` 校验本端套件/用例标题形态识别**未被收窄**(4 种套件前缀组合 + 「用例」二字可省,任一未识别即退出码 1)。⚠️ 解析端收窄的表现是**静默漏跑**——用例不进 tasks.md,报告里连「未执行」都不体现,跑完仍是全绿,故必须靠本自检而非人工复核;形态契约见 [`usecase-format.md`](./usecase-format.md) §二。

**★run-context 预置定位符段核查(折入本维度,可选):** 若 run-context 填了「关键元素定位方式 + 常用测试数据(执行前预置·只读)」段,须**只用语义定位符**(可见文案/角色+名称/label,**禁 DOM/CSS 选择器/xpath**),来源宜取自 dev-manual-testcase 自测方案/用例已声明的文案与长度;`locate` 应先查该段命中即用、未命中退回 observe。**该段可选:整段缺失时退回全程现场探测,行为与旧版本一致,不判不通过。不通过标志:** 预置段出现选择器/xpath/接口字段名。

**★语义断言契约核查(折入本维度):** 用例步骤带 `断言:`/`断言(反向):` 行时,执行侧须**优先按语义断言做确定化判定**(逐条映射到 observe 可观测信号),无断言行才回退自然语言「预期现象」由 AI 判定;断言 DSL 与执行侧映射见 [`usecase-format.md`](./usecase-format.md) 第六节(与 dev-manual-testcase 共享同一 DSL 契约,语法一致)。**不通过标志:** 带断言的步骤仍纯靠 AI 临场判定、未走确定化断言;或断言里出现 CSS/xpath/接口字段名(应只用页面可见语义文案)。

**★值级断言硬约束核查(折入本维度,Critical,不限 P0/P1):** 凡涉及**数值/状态/权限**的用例,判 `pass` 须基于值级断言(列表行数=N / 字段值 / 状态迁移 / 权限入口可见性 / `[双源对账]` 的 `db_assertion.match`);**严禁把「页面加载成功 / 无 console error / 元素存在」当作业务用例的唯一 pass 判据**,且不再限于 verified/self-heal。**不通过标志:** 数值/状态/权限用例仅凭页面加载或元素存在即判 pass、无值级断言支撑。

**★用例族标记透传核查(折入本维度):** 按文本标记识别并透传——`[回归]`+`关联缺陷` → `is_regression=true`/`related_defect_id`;`[双源对账]` → `db_assertion`;`[反向-残留]` 由既有「不存在文本"X"」DSL 承载、`is_reverse` 透传;`[文案一致性]` 反向用例同由该 DSL 承载、`is_reverse` 透传,且 `[文案一致性]` 字样须保留在 `test_name`/`type` 供 gen_report 判族锁 Critical(**术语对齐,不新增能力,勿误判缺失**)。**不通过标志:** 上游带这些标记却未在结果 JSON 透传对应字段;或把 `[反向-残留]`/`[文案一致性]` 当作缺失能力另建;或 `[文案一致性]` 标记文本未保留致 gen_report 判族失效。

---

## 循环终止条件

- **通过终止:** 8 维度均 ✅(无某端时该端维度 2 相关子项标 N/A);结果中出现 `na` 时须另核对理由非空、统计分母已排除且与 `pass/fail/block` 求和等于总数。
- **轮次上限:** 最多 3 轮。
- **不可豁免 = 凡标 `Critical` 的，一律不可豁免**(**判据就是标记本身,不另立名单**)。两类都算:
  ① **维度标题**标 `(**Critical**)` 的;② **折入子核查**在标题括号里标 `Critical` 的。
  **全集怎么枚举——就跑这一条,别凭记忆数**(作用域 = 本文件,`Critical` 标记只在这里权威):

  ```bash
  grep -nE '^#### 维度 [0-9]+.*\(\*\*Critical\*\*\)|^\*\*★[^:：]*折入本维度[^:：]*Critical' \
    <SKILL_DIR>/references/quality-review-checklist.md
  ```

  > **当前快照(2026-09-06 实跑该命令得 9 条,仅供对读、以实跑为准):**
  > 维度标题 5 条 = **维度 1 / 2 / 3 / 5 / 7**;折入子核查 4 条 =
  > 「DB 断言驱动 + 前置数据编排两层归属」(宿主维度 2)、「概况环境事实字段来源」
  > 「用例族失败锁 Critical」(宿主维度 7)、「值级断言硬约束」(宿主维度 8)。
  > ⚠️ **枚举只是快照,以标记为准。** 本条此前是一份**硬编码名单**「维度 1/3/5/7」,
  > 而维度 2 的标题从一开始就标着 `(**Critical**)` —— 两套清单双写、必然漂移,**它已经漂了**。
  > 增删 Critical 标记时不需要回来改这份枚举(改了更好),但**绝不能反过来拿这份枚举去否决标记**。
  > ⚠️ 由 ② 派生一条容易被忽略的结论:**维度 8 本身不标 Critical,但它折入的「值级断言硬约束」标 Critical**
  > —— 即「维度 8 整体可豁免」不成立,那一条子核查照样是阻断项。宿主维度的档位不向下传递给子核查。
  > ⚠️ **反方向同样不传递**:维度 1/2/3/5/7 标题虽是 Critical,其**未标 Critical 的子核查**不因此升档;
  > 但宿主维度整体要 ✅ 才算过,所以它们**照样得通过**——「不升 Critical」只影响缺陷定级,不给它们放行。
- **三类「本轮不核」互不等价,⛔ 别混用一个词打发过去:**
  | 形态 | 什么意思 | 报告怎么呈现 |
  | :- | :- | :- |
  | **N/A(范围判定)** | 本轮压根不测那个端 / 没有那类数据(维度 2 端子项、`§2.5`/`§2.6` 可选节) | **留行**,写明范围理由 |
  | **不适用(入参门控)** | 旧 Web 与新 Web+WebMCP 均未启用 → 仅两条 Web 叶子不适用;若非 Web `client_mcp.enabled=true`,通用核查照跑 | **不留行**(门控铁律,⛔ 严禁自行探测是否启用) |
  | **不适用(入参门控)** | `webmcp_enabled` 非 `true` → 两条 WebMCP 条件启用子核查**整条不适用** | **不留行**(门控铁律,⛔ 严禁自行探测是否启用) |
  | **可选子核查缺数据** | 标「可选」的子核查(环境探针档案 / run-context 预置定位符段)输入整段缺失 | 退回旧路径,**不判不通过** |
- **⚠️ 标 N/A ≠ 豁免。** 上表第一行的 N/A 是**范围判定**(本轮不测那个端),不是「查了没过、放它一马」。
  ⛔ 不得用 N/A 去消化一条真实不通过的 Critical 子项。第二、三行同理:门控与可选是**不该核**,
  不是**核了没过**——⛔ 都不得用来盖掉一条已经核出来的不通过。
- **阻塞完成:** 3 轮后仍有不通过项,禁止标记完成,输出最终报告 + 人工介入提示。

---

## 检查报告输出格式

```markdown
## 自动化执行质量检查报告
**检查对象:** {round 目录}
**检查轮次:** 第 N 轮
**总体结论:** ✅ 通过 / ❌ 不通过

| 维度 | 分组 | 状态 | 问题 | 修订建议 |
| :-: | :- | :-: | :- | :- |
| 1. 方法论层零端专有 API | 两层解耦 | … | … | … |
| … |
```

---

## 附:2026-09-10 新增的三条核查(折入既有维度,8 维度计数不变)

| # | 核查 | 折入维度 | 判据 |
| :-: | :- | :- | :- |
| a | **单条耗时三件套齐备** | 维度 7(报告章节完整) | 每条结果 JSON 有 `started_at`/`finished_at`/`elapsed_ms`;报告有 §2.7。⚠️ **缺失判 Important 不判 Critical**(存量一条都没有,判死会让整个校验被绕过),但**报告必须显式写「本轮未采集」**——⛔ 不得留空表,空表会被读成「都很快」 |
| b | **WebMCP 分层未被越界** | 维度 1-2(两层解耦)+ 维度 5(证据按模式达标) | 视觉还原度类用例的 `mechanism` **不得为 `webmcp`**(`check_result.py` C14 Critical);`mixed` 是被鼓励的形态、不判。⚠️ 这是**唯一会「静默变绿」的机制误用**——用 WebMCP 验还原度会让渲染层缺陷 100% 漏测且全绿 |
| c | **环境能力前置一次性预判** | 维度 3(状态机无残留)+ 维度 6(优雅降级) | 有 `EC-NNN` 声明时,第零步须做集合运算并在报告分出「可执行集 / 前置不满足集」;⚠️ **未识别的能力标识须回落旧流程**,⛔ 既不得静默当满足、也不得静默当缺位(后者是漏测,且报告显示 block、看上去很正常) |

> ⚠️ **三条都刻意不新增维度编号** —— 本 SKILL 的「8 维度」被多处引用,加编号会让既有映射整体位移
> (同 `{{AIDP_HOME}}/scripts/check_skill_ref_freshness.py`「约束引用新鲜度」要防的形态)。
