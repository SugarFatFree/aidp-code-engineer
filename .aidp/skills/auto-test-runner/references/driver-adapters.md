# 驱动适配层(端相关 · 可插拔)

> 本文件是驱动适配层的**端无关信源与加载索引**(四原子能力契约 / 能力探测降级 / 扩展新端 SOP);**各端专有细则在同目录 `driver-<端>.md`**。**方法论层只依赖四个端无关原子能力,不感知具体端;** 每个被测端提供一个适配器实现这四个能力。新增端 = 新增一个 `driver-<端>.md`,方法论层零改动。

---

## ⚠️ 端专有细则按需加载（重要）

本文件只保留**端无关**内容：四原子能力契约、能力探测与优雅降级、扩展新端 SOP。**各端的驱动矩阵、适配器实现样例、端专有 API 调用**拆在同目录 `driver-<端>.md`，**按被测客户端类型只加载命中的那一份**，不要全量读。

| 被测客户端 | 加载 | 成熟度 |
| :- | :- | :- |
| Web 浏览器（chrome-devtools / Playwright） | `driver-web.md` | 已验证（主场景） |
| 微信 / 各厂小程序（miniprogram-automator） | `driver-miniprogram.md` | 预留未验证 |
| 移动 APP（Appium / UIAutomator2 / XCUITest） | `driver-mobile.md` | 部分（伪代码，未端到端验证） |
| 桌面客户端（Playwright-Electron / WinAppDriver） | `driver-desktop.md` | 预留未验证 |
| **DB 断言驱动**（`[双源对账]` 用例，可插拔） | `driver-db-assertion.md` | 与被测端正交，需要时**额外**加载 |
| **应用 MCP 业务工具**（独立于测试驱动的条件能力） | `driver-client-mcp.md` | 调用方显式 `client_mcp.enabled: true` 或旧 Web 显式启用才加载;**不是第五个 UI 原子能力**,驱动用 MCP 协议不构成应用能力证据 |
| **WebMCP 工具调用**（仅 Web 适配叶子） | `driver-web-webmcp.md` | **不是第五个端**;只在 Web+WebMCP 声明时额外加载,secure context/Chrome 前提不扩散到非 Web |
| **WebMCP 工具调用**（Web 适配器的可选补充能力 `invoke`，**条件启用**） | `driver-web-webmcp.md` | **不是第五个端**——仍在浏览器里、仍经同一个 Web 驱动；**仅**调用方传入 `webmcp_enabled: true` 时**额外**加载，否则整份不适用 |

> ⚠️ **维度 1-2 Critical「方法论层零端专有 API」的落点**：端专有 API（`mcp__chrome-devtools__*`、`miniprogram-automator`、Appium `driver.*`、SQL/DB MCP 调用等）**只允许出现在 `driver-*.md` 适配层文件内**；`SKILL.md`、`execution-methodology.md` 与本文件的端无关部分**一律不得出现**。拆分后这条约束的检查边界更清晰：`check_layer_isolation.py` 扫方法论层文件即可。

---

## 一、四原子能力契约(端无关抽象)

所有适配器必须实现下列四个能力,签名与语义统一;**方法论层只调这四个,严禁直接写端专有 API**。

| 能力 | 签名(语义) | 输入 | 输出 | 说明 |
| :- | :- | :- | :- | :- |
| **locate** | `locate(语义定位符) → 句柄` | 可见文案 / 角色+名称 / label(**非底层选择器**) | 元素句柄(端内部引用) | 定位优先用页面可见语义,保证用例端无关。定位不到返回空句柄(交由 act 触发失败分级) |
| **act** | `act(句柄, 动作词, 数据?) → 结果` | 句柄 + 端无关动作词 + 可选数据 | 操作结果(成功/失败 + 增量状态) | 动作词枚举见下;数据为输入文本/选项/文件名等 |
| **observe** | `observe() → 结构化状态` | — | `{当前页, 标题, 可见元素[], 关键文本, 列表计数, 登录态, (可选) console[], network[], env{}, driverAlive}` | 读当前页面/会话状态,支持感知链与断言。**三条可选、端相关的附加通道**:① **运行时错误通道(console/network)**——Web 端可拉 console 消息 + network 请求(供 `runtimeErrors` 捕获,见 execution-methodology 第三节步骤 4);② **运行环境通道(env)**——见下;③ **健康探活通道(`driverAlive`)**——见下。三通道若某端驱动不提供,均返回空/`null`、相应字段留空(优雅降级,不因缺通道失败) |
| **capture** | `capture(标签) → 实际证据路径` | 证据标签(如 `TC-001-step3`) | 实际生成且可读取的一张截图路径 | 每次只归档一张实际截图,扩展名由适配器决定;快照/控件树归 `observe`,接口统一 |

**capture 端无关硬契约:** 每次 capture 只生成一种实际可用的证据格式,不得为统一扩展名转码或同时保留 WebP+PNG 双份截图;返回值必须是本次真实生成的 artifact 路径,截图失败时不得创建空文件或伪造路径。调用方只把该返回值写进 `results/*.json` 的 `evidence[].artifact`,不得按 TC-ID 自行补 `.png` / `.webp`;扩展名由适配器决定。

**端无关动作词枚举(act 的第二参数):**

| 动作词 | 语义 | Web 例 | 移动例 | 小程序例 | 桌面例 |
| :- | :- | :- | :- | :- | :- |
| `tap` | 点击/轻触 | click | tap | tap | click |
| `input` | 输入文本 | fill/type | send_keys | input | type |
| `select` | 选择选项 | selectOption | picker | picker | select |
| `swipe`/`scroll` | 滑动/滚动 | scroll | swipe | scrollTo | scroll |
| `back` | 返回 | goBack | back | navigateBack | back |
| `upload` | 上传文件 | setInputFiles | pushFile+选择 | chooseImage mock | file dialog |
| `dialog` | 处理弹窗 | handleDialog | alert accept | (系统弹窗) | dialog |
| `waitFor` | 等待条件/元素 | waitForSelector | wait until | waitFor | waitFor |
| `resetSession` | **重建干净会话**(清空登录态,供跨角色轮测换账号) | 见 `driver-web.md`「多角色轮测」 | 清应用数据/重装会话 | 重启小程序上下文 | 重启应用实例 |

> **★`resetSession` 是可选、端相关的动作词(不是第五个原子能力)。** 它仍走 `act`,句柄传空:`act(—, 'resetSession')`。加它的原因:多角色轮测里「换账号」不是随便点个退出就行——**会话可能藏在驱动实例级、清不掉**,而各端的正确姿势差异极大(见各 `driver-<端>.md`)。**每端须声明本动作词的落地方式,或明确写「本端不适用」**;**不提供 = 优雅降级**:跨角色套件退回「UI 点退出登录 + `observe` 验证登录态已清空」,验证不过则标 `block(precondition-unmet)`,不硬失败、不挂起。
>
> **★同一个 `resetSession` 服务两个场景,别拆成两个能力:** ① **换账号**(跨角色套件边界,见 `execution-methodology.md` 第一节);② **驱动卡死自愈**(健康探测判定驱动进程级无响应后重建,见第四节)。两者要的都是「把驱动/会话恢复到干净可用态」,只是触发条件不同;**适配层只需实现一次**。区别仅在自愈场景下重建的粒度通常更彻底(连驱动进程一起重启),各端在 `driver-<端>.md` 里就地说明即可。

**★observe 的运行环境通道(env,可选 · 端相关):**

供**运行环境取证**原子步骤使用(方法论侧见 [`execution-methodology.md`](./execution-methodology.md) 第十节),在驱动连接后、首条用例前调用一次,返回本次运行的**环境事实**:

| 端无关信号 | 语义 | 说明 |
| :- | :- | :- |
| `runConfig` | 驱动**本次运行配置**(启动参数/运行时配置),**若该端驱动能直接返回则为权威信源** | 拿不到返回空,不伪造 |
| `renderSignals` | 运行时**渲染形态信号**(是否无头等),供交叉判定 | 具体读哪个属性属端专有 |
| `automationSignals` | 运行时**自动化驱动标识** | 只证「被自动化驱动」,**不足以判渲染模式** |
| `viewportSize` | **视口**尺寸(非窗口外框尺寸) | 二者语义不同,勿混 |
| `instanceOwnership` | 当前实例已有的页面/会话集合 | 与「实例归属防呆」**共用同一次读取**,判 `reusedInstance` |

- **每端须声明本通道**:实现了哪些信号、各信号在**当前版本下是否仍然有效**(判据会随被测端版本漂移,须实测复核),或明确写「本端不适用」。**不得留空**——留空会被读成"忘了写",而不是"不适用"。
- **端专有落地**(读什么属性、调什么命令、实测结论)只写进对应 `driver-<端>.md`;本文件与方法论层只出现上表的端无关信号名。
- **不提供本通道 = 优雅降级**:相应事实字段写 `null` + `未取到(驱动不提供该通道)`,不判失败。

**★observe 的健康探活通道(`driverAlive`,可选 · 端相关):**

供**驱动健康探测**使用(方法论侧见 [`execution-methodology.md`](./execution-methodology.md) 第四节「驱动健康探测 + 自愈重启」),用于把**驱动进程级卡死**与**单元素定位失败**区分开——前者要自愈重建,后者只该走常规重试。

| 端无关信号 | 语义 | 说明 |
| :- | :- | :- |
| `driverAlive` | 驱动**进程/服务是否还在响应**(`true`/`false`/`null`=本端不提供) | 用**一次轻量、不依赖页面内容**的调用探活(如读驱动状态、列会话/页面),**不要**用业务页面元素判活——页面渲染不出来不等于驱动死了 |

- **必须轻量且有独立超时**:探活本身要能在 `driver_health_timeout_s`(默认 15s)内给结论,否则探活自己也卡住就失去意义。
- **`null` = 本端不提供** → 该端**声明「本端不适用」并退回旧路径**(逐条超时→`block`),不判失败。
- **端专有落地**(用什么命令探活、`resetSession` 怎么重建)只写进 `driver-<端>.md`;本文件与方法论层只出现 `driverAlive` 这个端无关信号名。

> **合并设计:** Web/桌面驱动的 `locate` 与 `observe` 往往共用「一次快照返回值」(快照里既有元素句柄 ref 又有页面状态);移动/小程序则分别调 find_element 与 page_source。适配器内部如何实现由各端决定,对方法论层透明。

---

## 二、各端适配器文件一览(适配器矩阵已按端拆分)

> 各端的「驱动矩阵 + 四能力映射 + 适配器样例 + 端专有 API」原本集中在本文件的「适配器矩阵」节,现已**按端拆分**到下列文件;本节只作内容索引,加载优先级见上方「按需加载」表。

| 文件 | 内容 |
| :- | :- |
| `driver-web.md` | Web 驱动矩阵（chrome-devtools-cli / mcp-remote / 插件回退）、四能力映射、Playwright 风格适配器样例、**本地独立实例 ↔ 共享/远程实例硬边界**、**执行前防呆（连错共享实例拦截）**、**运行环境取证（env 通道落地 + 实测证否表：哪条判据当前还成立）** |
| `driver-miniprogram.md` | 小程序驱动矩阵、四能力映射、**env 通道声明（渲染模式本端不适用）** |
| `driver-mobile.md` | 移动端驱动矩阵、四能力映射、Appium 风格适配器样例、**env 通道声明（渲染模式本端不适用）** |
| `driver-desktop.md` | 桌面客户端驱动矩阵、四能力映射、**env 通道声明（GUI 应用恒有头）** |
| `driver-db-assertion.md` | DB 断言驱动能力契约、四能力映射（项目自行配置的数据库 MCP `<db-mcp>` 为例）、对账示例、成熟度与降级。**它不是被测端**，不适用 env 通道声明要求 |
| `driver-web-webmcp.md` | **条件启用**：WebMCP 工具调用（Web 适配器可选能力 `invoke`）——驱动版本要求（≥1.8.0）、两个作用域不同的浏览器开关与 origin 三段精确匹配、连接后两行自检、调用约定（异步列出 / 两个参数形态 / 原型上没有 unregister）、与 CDP 的分工、报告纪律。**它不是被测端**，不适用 env 通道声明要求；未启用时整份不加载 |

---

## 三、能力探测 + 优雅降级(Critical)

**加载适配器前必须探测该端驱动是否就绪;不可用时明确报缺失并跳过,严禁硬失败、严禁挂起等人。**

- **探测**:`python3 <SKILL_DIR>/scripts/detect_drivers.py <web|miniprogram|mobile|desktop|all> --json`(端类型为**位置参数**)。脚本按端探测对应驱动的可用性(命令/包/服务/端点),输出 `available` / `drivers[]` + `hint`(如何补齐)。
  - **★通用例外(不可据"包未装"就 block):** 某端主驱动若是**会话运行时挂载的 MCP 工具**(本脚本探不到,典型即 web 的 chrome-devtools MCP),不得只因 npm/包探测为空就 block 该端。web 的具体放宽口径与工具名见 `driver-web.md`;通用原则:**只有该端全部可用性信号(运行时 MCP 工具 / 本机应用 / 包驱动)皆空时才 block**,否则会误杀真能跑的端。
- **降级策略**:
  - 目标端驱动**可用** → 正常加载适配器执行。
  - 目标端驱动**缺失** → run-context 标 `驱动缺失`,该端全部用例整体标 `block(driver-missing)` + 在 error 记「缺失驱动 + 补齐建议」,**继续跑其它可执行部分**(如混合项目的另一端),最后在报告缺陷列表统一呈现。
  - **同端多驱动**:首选 unavailable 时自动尝试次选(如本地 CLI 缺失 → 试同机的另一本地驱动);全不可用才降级 block。
    - ⚠️ **「本机独立实例」↔「共享/远程实例」硬边界(端无关口径,不可自动互顶)**:同一端的多个驱动若分属**驱动本机独立实例**与**连共享/远程实例**两类,**二者不是等价次选**——静默从前者降级到后者会连上他人/共享会话,造成串测污染与他人数据被改。规则:
      1. **禁静默降级**:缺首选时**不得**自动切到连共享/远程实例的驱动;
      2. **先诊断修复**(命令名/PATH/端点配置等)力争回落首选;
      3. 短期修不了时,可**显式声明**降级到另一个**本机独立实例**驱动(合法 last-resort),仍无路才人工介入;
      4. **driver 字段须如实记录实际所用驱动**,严禁静默切换、严禁用了降级驱动却填首选值;
      5. `detect_drivers.py <端>` 对「仅共享/远程变体可用、本机独立驱动缺失」返回 `manual_confirm_required=true`(需人工确认、非自动可用),据此按 1~4 处理。
    - **端专有落地**(各类驱动的具体命令/工具名、driver 字段取值枚举、诊断修复步骤)见对应 `driver-<端>.md`;Web 端见 `driver-web.md`「三·补一:本地 CLI ↔ 共享/远程 MCP 变体硬边界」。
- **混合项目**(如 iOS APP + Web 后台):按用例所属端分别探测 + 加载对应适配器,某端缺失只跳过该端,不影响另一端。

---

## 四、扩展新端(SOP)

1. **新建 `driver-<端>.md`**,声明该端驱动矩阵 + 四能力映射 + 前置 + 成熟度 + **observe 运行环境通道(env)各信号的实现与实测有效性,或明确「本端不适用」**;并在本文件顶部「按需加载」表与「二、各端适配器文件一览」各登记一行。
2. 在 `detect_drivers.py` 增加该端探测分支(命令/包/服务检测)。
3. **方法论层零改动**——只要新适配器实现了 locate/act/observe/capture 四能力,批量调度/模式分级/闭环/失败分级/断点/报告全部自动复用。
4. **端专有 API 只写进新建的 `driver-<端>.md`**;`SKILL.md`/`execution-methodology.md`/`report-format.md`/`usecase-format.md` 一律零改动,改完跑 `python3 <SKILL_DIR>/scripts/check_layer_isolation.py <SKILL_DIR>` 自检。

| `driver-client-mcp.md` | **条件启用**：应用自有 MCP 业务工具四态取证与测试驱动严格分轴,各端只依据已证实实现适配;无实现明确未提供 |
| `driver-web-webmcp.md` | **仅 Web 条件启用**：WebMCP 工具调用（Web 适配器可选能力 `invoke`）——驱动版本要求（≥1.8.0）、两个作用域不同的浏览器开关与 origin 三段精确匹配、连接后两行自检、调用约定（异步列出 / 两个参数形态 / 原型上没有 unregister）、与 CDP 的分工、报告纪律。**它不是被测端**，不适用 env 通道声明要求；未启用时整份不加载 |
