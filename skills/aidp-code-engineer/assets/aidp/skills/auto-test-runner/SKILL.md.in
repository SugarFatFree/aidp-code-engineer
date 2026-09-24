---
name: auto-test-runner
description: >
  端无关的自动化测试执行器。把「AI 驱动的自动化测试执行」逻辑沉淀为单一信源,分两层:
  ① 通用执行方法论层(端无关)——分模块批量调度、执行模式分级、感知-执行-校验-决策闭环、失败分级不中断、进度断点恢复(tasks.md 状态机)、证据取证、报告汇总;
  ② 驱动适配层(端相关、可插拔)——按被测客户端类型选择自动化驱动(Web:chrome-devtools-mcp/Playwright;小程序:miniprogram-automator;移动 APP:Appium/UIAutomator2/XCUITest;桌面:Playwright-Electron/WinAppDriver),统一抽象「定位元素/执行动作/读取页面状态/截图取证」四个原子能力,方法论层只依赖这四个抽象、不感知具体端。
  环境准备阶段做一次「运行环境取证」产出环境事实对象(判据 = assets/env-facts-schema.json 里配了 XSource 的全部字段,逐字段带来源标注;不写死条数,字段会增),作为报告概况段的唯一数据源——取不到写 null+未取到(原因),严禁模板默认或意图推断。
  输入对接 dev-manual-testcase 生成的标准自测用例;报告输出固定结构(概况/汇总/各模块/缺陷列表/明细/结论)。
  7×24 无人值守:所有信息开始前一次性取齐,执行全程不中途等人,遇不可自愈的阻塞标 block、记录证据、继续跑完剩余用例。
  执行与报告产出后强制执行 8 维度独立 Agent 检查(三组:两层解耦类 1-2 / 执行完整性类 3-6 / 产出规范类 7-8;哪些是 Critical、哪些不可豁免一律以 quality-review-checklist.md 里的 `Critical` 标记为准,此处不另列名单)。
  当用户提到自动化测试执行、批量跑用例、无人值守测试、UI 自动化执行、跨端测试执行、chrome-devtools 执行用例、Appium/小程序自动化执行、测试执行报告时触发。
---

由调用方入参门控的可选能力(当前:`client_mcp` 之于**应用业务工具**、`webmcp_enabled`/`webmcp.enabled` 之于 **Web 叶子**),**未启用时整段不适用**:run-context 不写相关字段、报告不留相关位置、不产生告警、不占篇幅。**⛔ 本 skill 不自行探测是否启用**(判定散落多处必然漂移,一处判错就给未启用项目凭空长出 block 项与报告位)。⛔ 驱动版本不足时**不得静默降级为「就当没有该能力」**——标 block + 证据,否则这一整类用例会全绿式消失、报告看不出漏测。
> **(仅 Web 叶子)WebMCP 驱动版本校验:** 旧 `webmcp_enabled: true` 或新 `client_mcp.enabled: true` 且 Web+WebMCP 时,探测命令加
**运行真实性前置:** 实际认证实例/账号角色 + 登录后的项目自身受保护接口 + 前端部署指纹须先取证,故障注入能力只对依赖它的用例前置核验;结果写 `runtime_preflight` 的逐项来源/时间/证据。失效时受影响用例 block 并继续其余用例,首页 200 / 单测 / 相似浏览器场景均不是 pass 证据。项目声明启用 WebMCP 时还要区分入口、**本页注册**和该用例实际工具调用;零注册的专项用例 block,普通业务可如实记 DOM/CDP 回退。`tasks_state.py` 的 init/update 使用独占锁+原子替换防**并发写入**丢状态,锁失败返回环境错误,不得手写状态覆盖他人更新。细则见 [`references/execution-methodology.md`](./references/execution-methodology.md)「运行真实性前置」和 [`references/driver-web-webmcp.md`](./references/driver-web-webmcp.md)。

# 自动化测试执行器 (Auto Test Runner)

## 角色定义

你是一位**自动化测试执行调度官**。你的职责是:读取 `dev-manual-testcase` skill 生成的标准自测用例,按**通用执行方法论**分模块批量调度执行,通过**可插拔的驱动适配层**驱动具体客户端(Web/小程序/移动/桌面),把每条用例判定为 pass/fail/block,断点可续跑,最后汇总成固定结构的测试报告。

**核心设计:两层分离。**

```
┌─────────────────────────────────────────────────────────────┐
│  通用执行方法论层(端无关 · 本 skill 的稳定内核)               │
│  分模块批量调度 · 执行模式分级 · 感知-执行-校验-决策闭环 ·     │
│  失败分级不中断 · 进度断点恢复 · 证据取证 · 报告汇总           │
│         ▲ 只依赖下面四个原子能力抽象,不感知具体端 ▲           │
├─────────────────────────────────────────────────────────────┤
│  驱动适配层(端相关 · 可插拔)                                  │
│  四原子能力:locate(定位) / act(动作) / observe(读状态) / capture(取证) │
│  Web ┆ 小程序 ┆ 移动 APP ┆ 桌面  —— 能力探测 + 优雅降级        │
└─────────────────────────────────────────────────────────────┘
```

- **方法论层**(端无关):所有端**共用同一套**调度、闭环、失败处理、断点、报告逻辑。详见 [`references/execution-methodology.md`](./references/execution-methodology.md)。
- **驱动适配层**(端相关、可插拔):按被测端选驱动,只需实现四个原子能力。详见 [`references/driver-adapters.md`](./references/driver-adapters.md)（端无关契约 + 探测降级 + 加载索引）；**各端专有细则按被测端加载 `references/driver-<端>.md`，勿全量读**。

> **单一信源边界:** 执行方法论沉淀在本 skill 内。下游命令端只负责**编排调用、传入上下文**(用例路径 / 被测端 / 环境地址 / 账号 / 驱动选择),**不复述执行细节**。

---

## ⚠️ 无人值守流畅性硬要求(Critical,最高约束)

**本 skill 会被 7×24 无人值守链路调用,执行全程严禁中途停下来等人工输入 / 确认。**

1. **信息一次性前置取齐**:执行开始前,通过「第零步:运行上下文对齐」把所有必需信息(用例路径、被测端类型、驱动选择、环境地址、各角色账号、前置数据、单步超时上限、证据归档目录)**一次性取齐并落盘到 run-context**。缺失项按占位登记但**不中途追问**。
2. **遇阻塞不挂起**:任何用例遇到无法自愈的阻塞(元素不存在、驱动不可用、前置不满足),**标 `block` + 记录证据 + 继续下一条**,绝不半途挂起等人。
3. **兜底判定有上限**:单操作重试有次数上限、单步等待有超时上限、功能入口探测有总时长上限(见方法论「失败分级不中断」),到顶即判定,不无限等待。
   - **★但「驱动整体卡死」不该靠逐条耗尽超时来发现**:那样既救不活也拖慢整批(实测一次无人值守跑中驱动卡死两次,一次空等到超时上限、一次靠人工重启才救回)。故 `block` 之前多一层**健康探测 + `resetSession` 自愈 + 断点续跑**,连续 3 次自愈失败才落定 `block(driver-hung)`。自愈**只重置运行态**(驱动/会话/登录/前置数据),**绝不碰业务代码**——与第 6 条红线同源。
4. **框架脚本调用失败也降级、绝不空转**:`tasks_state.py` / `gen_report.py` / `detect_drivers.py` 等**框架脚本自身**参数踩坑 / 调用失败时,**最多重试 2 次**(先 `--help` 校正参数),仍失败**立即降级到手动等价操作**——tasks.md 可**手写状态记号** `[ ]/[>]/[√]/[!]`、gen_report 失败可**手动按 `results/*.json` 聚合**成报告、detect 失败可**人工判定端可用性**——把降级动作**记入报告「遗留风险/改进建议」**,**绝不反复试错空转卡死**。框架自身失败与用例级失败同规格:重试上限 → 降级 → 记录 → 继续(详见方法论「失败分级不中断」)。
5. **最后统一汇总**:所有阻塞 / 失败在报告的「缺陷列表 + 遗留风险」里统一呈现,由人事后处置,而非执行中打断。
6. **★测试执行内绝不修改业务代码、绝不修复缺陷(红线)**:执行内核只做「判定 + 记录」,发现缺陷只【记录进 problem/缺陷汇总清单、标 `block`/`fail`、继续测完剩余用例】,**绝不中断本 build 去改被测业务代码/配置/表结构绕过缺陷**,修复交外层 bugfix 流程。self-heal 的「恢复」仅限会话/登录/前置数据等运行态,**不触碰业务代码**(细则见方法论「失败分级不中断 → 共同铁律」)。

> 与人工可交互的 dev-manual-testcase(第零步会主动询问)不同,本 skill 是**无人值守执行端**:一切询问前移到编排层,执行内核只跑不问。

---

## 输入与前置

| 输入项 | 必要性 | 说明 |
| :- | :- | :- |
| **标准自测用例** | **必需** | dev-manual-testcase 产出的用例(套件 `SUITE-*`,兼容 `测试套件`/`TS-` 形态 / 用例 `TC-*` / 优先级 P0/P1/P2 / 类型 / 四要素步骤表)。单文件或多文件目录均可 |
| **被测端类型** | **必需** | Web 浏览器 / 微信·各厂小程序 / 移动 APP(Android·iOS)/ 桌面客户端。决定加载哪个驱动适配器 |
| **环境地址 + 账号** | **必需** | 被测应用入口(URL / 小程序 appid / APP 包名 / 桌面可执行路径)、各角色账号密码 |
| **驱动选择** | 推荐 | 同一端可有多个驱动(如 Web 的 chrome-devtools-mcp 或 Playwright);不指定则由能力探测自动择优 |
| 研发自测方案 | 可选 | 若用例配套了 `01_研发自测方案.md`(历史旧锚 `00_研发自测方案.md` 亦可),读取其通过准则、证据要求 |
| 前置数据 | 可选 | 用例依赖的已有数据准备说明;若用例带「前置探测」结构化字段,先在浏览器前按 `ED-NNN` 归组批量只读探测;若用例带「前置数据编排」段,再按 run-context 联动的关联系统入口+账号+`datasource` 造/删数(DB 途径经 DB 断言驱动 SQL,或第二隔离会话 UI),缺省则仅只读、不主动造删数 |
| 环境探针档案 | 可选 | 上一轮环境观测事实(驱动通道限制 / 鉴权头形态 / 未登录真实响应 / 三类取证可用性 / 元素定位方式 / 已知需重试项);仅作启动前提示与预热,非权威契约,与本轮观测冲突时以本轮为准 |
| `client_mcp` | 可选(默认关闭) | **被测应用主动暴露业务工具**的显式声明,含客户端类型/实现形态/来源/工具清单及 Schema;未传不探测、不产专项用例或报告行。与 Chrome/Appium/小程序**测试驱动 MCP** 分轴,仅已证实应用自有服务/桥接可触发非 Web 能力。细则见 [`references/driver-client-mcp.md`](./references/driver-client-mcp.md) |
| `webmcp_enabled` / `webmcp.enabled` | 可选(旧 Web 兼容) | 任一 `true` 只表示 Web+WebMCP;两旧别名冲突须报错,仍由调用方提供 `webmcp_entry_symbols`/`webmcp_launch_command` 且只在 Web 分支消费;与 `client_mcp` 客户端/启停/形态冲突须明确报错,不静默覆盖。不传/false 且新声明未启用时整段不留痕;⛔ 本 skill 不自行探测。Web 叶子见 [`references/driver-web-webmcp.md`](./references/driver-web-webmcp.md) |
| `webmcp_enabled` | 可选(默认 `false`) | **条件启用能力的唯一开关**,由编排层显式传入。为 `false` 或未传 → WebMCP 工具调用整段不适用(run-context 不写相关字段、报告不留位置、不产生告警)。传 `true` 时另需 `webmcp_entry_symbols`(能力入口标识符,**写死必过期**)与 `webmcp_launch_command`(带参浏览器完整启动命令,**自拟无法复现**)。⛔ **本 skill 不自行探测是否启用**;细则见 [`references/driver-web-webmcp.md`](./references/driver-web-webmcp.md)。⚠️ 本行是**输入契约**、不是「报告留位置」,与「未启用不留痕」铁律不冲突——否则调用方无处可传、执行 Agent 无处可读,而细则又只在启用后才加载,闭环断在入口 |
| DB datasource | 可选 | `[双源对账]` 用例数据真值对账 / SQL 造删数所需的 DB 连接(会话已连 DB MCP 或 run-context `datasource`),**须带 `environment` 环境标识**;缺省时该类用例走 UI 断言或标 block(precondition-unmet),不影响其余用例。**执行期必须先过「数据源归属校验」**(方法论第十一节),不通过则该驱动整体停用 |

**用例格式对接(硬契约):** 严格对接 dev-manual-testcase 的输出约定——按 `### 套件 SUITE-*` 分模块(**兼容形态** `测试套件` 前置词与 `TS-` 编号前缀,四种组合均须识别),`#### / ##### 用例 TC-*` 为最小执行单元(**「用例」二字可省略**),`> **优先级**: P0 | **类型**: 正向 | **反向**: 否 | **覆盖**: F4` 字段行,四要素步骤表(操作动作/操作对象/操作数据/预期现象)。执行时按 TC-ID 现查用例详情,tasks.md 只存 ID + 名称。**完整解析契约**(目录结构/单多文件/SUITE·TC 命名/字段→模式判定/四要素→四原子能力映射)见 [`references/usecase-format.md`](./references/usecase-format.md)。

---

## 执行流程(方法论层,端无关)

> 完整规则见 [`references/execution-methodology.md`](./references/execution-methodology.md);本节为主干,四阶段 + 两个前置阶段(前置数据面探测、驱动连接后的环境准备)。

### 第零步:运行上下文对齐(一次性取齐,落盘 run-context)

执行前把所有必需信息落盘到 `{测试产物目录}/run-context.md`(模板 [`assets/run-context-template.md`](./assets/run-context-template.md)):被测端类型、驱动选择、环境地址、各角色账号、前置数据、**单步等待上限(默认每步 ≤3s / 首开 ≤30s)**、证据归档目录、通过准则。**缺失项标 `{待编排层传入}` 占位并登记,但不中途追问**(无人值守硬要求)。

> **(可选)预置「关键元素定位方式 + 常用测试数据」段(执行前一次性预置·执行中只读):** run-context 可按 页面/模块 预置**稳定语义定位符**(可见文案/角色+名称,禁选择器) + 业务常量(字段最大长度/关键枚举),`locate` 先查此段命中即用、未命中再退回 observe 现场探测,降重复探测抖动与 token。来源建议取自 **dev-manual-testcase 的自测方案/用例**已声明的文案与长度,避免臆造。**该段可选,缺省时行为与现状完全一致**(全程现场探测),与「当前页面/会话状态(动态更新)」区严格区分。

**★环境能力前置一次性预判(`EC-NNN`,2026-09-10 新增):** 除驱动外,**本轮环境提供了哪些能力**
(部署形态 / 服务端日志通道 / 靶场资产 / 项目数据形态)也在第零步一次性探明,与用例册声明的
`EC-NNN` 做**集合运算**,开跑前直接分出「可执行集 / 前置不满足集」;后者**一条都不进浏览器**,
直接落 `block(precondition-unmet)` 并写明缺什么。
> **立论:** 实测两轮 116 条里 **41 条(35%)因前置不满足被 block,且全部是逐条执行到前置检查才发现的** ——
> 每条白走一遍「导航 → 等待 → 探测 → 判定」,耗时全落在执行跨度里。**这与驱动缺失时整体标
> `block(driver-missing)` 而不逐条试是同一思路的推广**:一次性判出来的 41 个 block 与逐条试出来的结论完全相同。
> ⚠️ 三条不可退让(未识别能力标识须回落旧流程而**非**静默当满足或当缺位 / 无声明 = 无前置 /
> 探测本身失败标 `env-unavailable` 而**不得**转成「能力不具备」)与判据全文见
> [`references/execution-methodology.md`](./references/execution-methodology.md) 一·补·补。

**驱动能力探测:** 运行 `python3 <SKILL_DIR>/scripts/detect_drivers.py <端类型> --json`(端类型为位置参数 `web`/`miniprogram`/`mobile`/`desktop`/`all`)探测目标端驱动是否就绪;不可用则在 run-context 标 `驱动缺失` 并**优雅降级**——该端用例整体标 `block(driver-missing)`,不硬失败、不挂起。

> **(条件启用)WebMCP 驱动版本校验:** **仅当**调用方传入 `webmcp_enabled: true` 时,探测命令加
> `--webmcp`(`python3 <SKILL_DIR>/scripts/detect_drivers.py web --webmcp --json`),校验
> `chrome-devtools-mcp` **≥ 1.8.0**(该版本起才具备列出页面 WebMCP 工具的能力)。**不加该参数时
> 输出里完全没有 `webmcp` 段**(不占位、不留空)。
>
> **Web 叶子门控:** 旧 `webmcp_enabled: true` 或新 `client_mcp.enabled: true` 且 client=web/shape=webmcp 才加载本段。两者均未启用时不写 run-context/报告位置;非 Web 应用 MCP 启用时通用半场仍运行、但**本 Web 叶子不适用**。⛔ 不自行探测启用。另两个 Web 入参
> **应用 MCP 业务工具**先按 [`references/driver-client-mcp.md`](./references/driver-client-mcp.md) 核项目声明、入口实连、本应用实例注册、该用例实际调用四态及各自来源;`driver=cli|appium|mcp-remote` 只表示**测试驱动**,不证明应用调用业务工具。无已证实服务/桥接的非 Web 客户端写「不支持/未提供」或未取到,专项用例 block、普通 UI 照跑;UI 四原子能力不变。
>
> - 版本不足 → 给升级命令 `npm i chrome-devtools-mcp@latest -g`,相关用例标 **`block(webmcp-driver-too-old)`**;
>   版本**取不到** → **fail-closed** 标 `block(webmcp-driver-version-unknown)`(确认不了达标就不能声称可用)。
> - ⛔ **不要静默降级为「就当没有 WebMCP」**——那会让这一整类用例**全绿式消失**、报告看不出漏测;
>   标 block 才会把缺口如实留在「缺陷列表 + 遗留风险」里。与本 skill「事实取不到写『未取到(原因)』、
>   不写像样的默认值」是同一条纪律。
> - **绝不因此终止整轮、绝不挂起**(无人值守硬要求),其余用例照跑。
> - ⚠️ **版本结论不影响本命令退出码**:退出码只表达「该端有没有驱动可用」,版本不足 ≠ 驱动缺失
>   (web 端照样能跑非 WebMCP 用例)。结论读 `webmcp.satisfied` / `webmcp.block_reason`。
>
> **⛔ 本 skill 不自行探测是否启用**(不 grep 用例、不扫被测站点):判定散落多处必然漂移,一处判错
> 就给未启用项目凭空长出 block 项与报告位。判定权归调用方,门控与端专有细则见
> [`references/driver-web-webmcp.md`](./references/driver-web-webmcp.md)。

> ⚠️ **web 端不因 detect_drivers 的 npm 探测为空就 block:** web 主驱动是 **chrome-devtools MCP 插件工具**(属**运行时能力、本脚本探不到**;具体工具名属端专有,只在 `references/driver-web.md` 适配层出现)。只要**会话已挂载 chrome-devtools MCP 工具**,或**本机装有 Chrome/Chromium**,即视 web 可用。**仅当「MCP 工具未挂载 且 本机无 Chrome 且 无 npm 驱动」三者皆空时才 block web**,否则会把唯一真能跑的端误杀。detect_drivers 已对 web 按「npm 包 或 本机 Chrome 任一即可用」放宽,并在输出 `hint` 里说明 MCP 工具属运行时能力。

### 第一步:准备(prepare)——定轮次 + 建 tasks.md 状态机

1. **定轮次**:扫 `{产物目录}/build-{N}/` 已有 `round-*`,取最大号 +1 建新轮次目录 `round-{M}/`;旧轮次完整保留。断点续跑时复用当前轮次、不新建。
   - **★定 build vs 定 round(先分清再定轮次)**:
     - **build 递增 → 全新 tasks.md 全量重跑**:上一 build 的缺陷经**外层 bugfix 修复后**要重新回归时,建**新 `build-{N+1}`**,用 `tasks_state.py init` **重建全新 tasks.md、全部 `[ ]`**,**全量重跑**——不继承上一 build 的任何 `[√]`,不 `resume` 跨 build,不只跑被修用例(只复验被修会漏同源缺陷)。
     - **round 递增 → 同 build 内 self-heal 复测**:同一 build 内针对 flaky / 集成链路等环境波动用例的重试(见执行模式分级 self-heal),复用本 build 上下文,**非跨 build 回归**。
     - 即:**self-heal 复测锁 round 级 / 同 build,新回归轮锁 build 级 / 全量**,两者边界不得混用。
2. **建 tasks.md**:解析用例文档,按模块(套件)分组写 `round-{M}/tasks.md`(模板 [`assets/tasks-template.md`](./assets/tasks-template.md)),每条用例一行、初始状态 `[ ]`。

   **★完整命令行(照抄即可,勿臆造参数名):**

   ```bash
   # 建 tasks.md:第一个入参是「用例文件或目录」,-o 给输出路径(不给则打印到 stdout)
   python3 <SKILL_DIR>/scripts/tasks_state.py init <用例文件或目录> -o <round目录>/tasks.md
   # (可选)执行选集:--select all(默认) | smoke(P0) | regression([回归] 标记)
   python3 <SKILL_DIR>/scripts/tasks_state.py init <用例目录> -o <round目录>/tasks.md --select smoke
   # 改状态(批量):tasks.md 路径为第一个入参
   python3 <SKILL_DIR>/scripts/tasks_state.py update <round目录>/tasks.md --id TC-001 TC-002 --state running
   # 统计各态(有 [ ]/[>] 残留退出码 1)/ 列待续跑项
   python3 <SKILL_DIR>/scripts/tasks_state.py scan   <round目录>/tasks.md --json
   python3 <SKILL_DIR>/scripts/tasks_state.py resume <round目录>/tasks.md --json
   ```

   > **执行选集(深度维度)** —— `--select smoke|regression|all`。**刻意不引入 smoke/regression/release 三值新标签**:上游 dev-manual-testcase 的 `test-design-methodology.md` 已把 **P0 定义为「核心功能正向(冒烟)」**,`[回归]` 标记也早已存在并透传为 `is_regression`。再造一套平行标签只会让同一件事有两个信源、互相漂移,故直接复用既有数据、只在执行侧过滤。
   > **未标注优先级的用例在 `smoke` 下一律保留**(宁可多跑不可漏),并在输出如实报 `unlabeled_kept` 条数 —— 静默丢弃会让选集覆盖面无声缩水。

   > ⚠️ **参数名照抄,别按语义直觉自造。** 四个子命令的主入参**既可写位置参数、也可写同名具名参数**(`init --source …` / `update|scan|resume --tasks …`),二者等价;但 `--usecase` / `--round-dir` 这类**自造名不存在**,会直接 `unrecognized arguments`。缺参时脚本打印用法而非裸报错。`--state` 取值:`todo`/`running`/`done`/`block`。
3. **初始化 run-context 的「当前页面/会话状态」区**,供感知链复用。

### 第二步前置阶段:前置数据面探测(precondition probe)——解析后、驱动浏览器前

读取已解析用例中的结构化「前置探测」项,按 `ED-NNN` 去重归组,对每个前置项调用一次只读接口或数据面查询。探测必须显式区分 `success=false` / 非 2xx 与合法空结果:调用失败要记录探测错误并退出非零或返回明确错误态,不得转换成 `count=0`。前置不满足的关联用例直接写结果 `block(precondition-unmet)`,detail 原样使用用例声明的缺位短语,**不连接或驱动浏览器**;探测失败本身则标 `block(network-error)` / `block(env-unavailable)`并注明探测错误,不得把关联用例伪装成前置缺位。只有探测满足的用例才进入后续驱动连接和感知-执行-校验-决策闭环。

该阶段仍遵守探测类断言的方向、特异性和阳性对照分档纪律;具体数据面调用由适配器/编排层提供,方法论层不写端专有 API。详细规则见 `references/execution-methodology.md`「前置数据面探测」。

### 第二步:分模块批量执行(execute)——每模块一个执行子 Agent

**这是降 token 的核心:每个模块启动一个执行子 Agent,在其内部串行执行本模块全部用例,共享同一会话/一次登录**(实测相比逐条调度降 token ~3.6×)。

> ⚠️ **执行子 Agent 无 Skill 工具,必须用 `Read` 读方法论文件(标准姿势,不可省):** 通过 Task/Agent 工具派生的子 Agent **拿不到 Skill 工具**(即便 `tools:*` 也没有——Skill 是主循环级能力),因此**子 Agent 加载不了本 skill、拿不到方法论**,若不喂路径会变成"不知道怎么测"的空白 Agent。所以**主 Agent 派执行子 Agent 时,必须在 Task prompt 里要求子 Agent 先用 `Read` 工具读**:
> - `<本 skill 安装目录>/SKILL.md` + `<本 skill 安装目录>/references/execution-methodology.md`(拿完整执行方法论);
> - 以及本模块要用到的 `references/driver-adapters.md`(端无关契约/探测降级/端文件索引) **+ 被测端对应的 `references/driver-<端>.md`(该端四能力映射与样例,只读命中的那一份)**、`references/usecase-format.md`(解析用例);
> - **读完再用驱动(如 chrome-devtools MCP 插件工具)执行**。
>
> 主 Agent 只在 prompt 里传**「方法论文件路径 + 本模块用例文件路径 + run-context.md 路径」**,**不把方法论正文塞进 prompt**——既让子 Agent 拿到完整方法论,又不牺牲降 token(正文由子 Agent 自行 Read,不占主上下文/prompt)。

对每个模块:

1. 批量前把整模块用例状态 `[ ] → [>]`(`tasks_state.py update`)。
2. 执行子 Agent 内,对每条用例走**感知-执行-校验-决策闭环**(见下),并按**执行模式分级**(见下)决定取证强度与自愈策略。
3. **只在模块开头走一次入口流程**(打开端 → 登录 → 进工作台),模块内用例通过导航切换连续执行,**不重复登录**。
4. 每条用例执行完写结果 JSON(`round-{M}/results/{TC-ID}.json`,schema 见 [`assets/result-schema.json`](./assets/result-schema.json)),并据结果把状态 `[>] → [√]`(pass)或 `[>] → [!]`(fail/block/na);`na` 必须带不适用理由,且不等同于本轮跳过。
   > **★形状校验(模块收尾跑一次即可):** `python3 <SKILL_DIR>/scripts/check_result.py <round目录>/results/ --require-runtime-preflight --json`(旧 Web `webmcp_enabled: true`（或 `webmcp.enabled: true`）、或 `client_mcp.enabled: true` 且客户端=Web、实现形态=WebMCP 时再加 `--webmcp-enabled`,不得自行猜测;⛔ 只认旧 flag 会让只传 `client_mcp` 的 Web 项目永不开启本轮门;历史结果复核不带新参数)。`evidence` / `runtimeErrors` **必须是对象数组**(`evidence` 元素含 `artifact`),写成字符串数组会让证据路径与运行时错误统计失真;`block_reason` 必须落枚举——**环境类阻塞漏标枚举会被误计成产品缺陷**。校验失败按无人值守规则处理(记录 + 继续),不挂起。
   > **★形状校验(模块收尾跑一次即可):** `python3 <SKILL_DIR>/scripts/check_result.py <round目录>/results/ --json`。`evidence` / `runtimeErrors` **必须是对象数组**(`evidence` 元素含 `artifact`),写成字符串数组会让证据路径与运行时错误统计失真;`block_reason` 必须落枚举——**环境类阻塞漏标枚举会被误计成产品缺陷**。校验失败按无人值守规则处理(记录 + 继续),不挂起。
5. 更新 run-context「当前页面/会话状态」,供下一条用例感知复用。
6. **存活心跳**:run-context「三、执行参数」给了 `heartbeat_cmd` 时,**每完成一个模块(及模块内每 10 条用例)执行一次**该命令(失败忽略、不阻断)。编排层据此区分「测试链路仍在跑长批次」与「测试链路已掉线」;未提供则跳过。

### 第三步:断点补齐(checker)——安全检查点

批量执行后,**独立**扫 tasks.md:收集残留的 `[ ]`(待执行,可能遗漏)、`[>]`(执行中断)→ 补充执行,直至全部落定为 `[√]` 或 `[!]`,无 `[ ]`/`[>]` 残留。**报告必须在本检查点之后生成。** 中断后重跑时,本步即断点续跑入口——已 `[√]` 跳过,`[ ]`/`[>]` 续跑。

### 第三步·补:自由巡检(free scan,可选 · 默认关)

run-context `free_scan: true` 时,在**全部模块用例跑完之后、报告生成之前**跑一轮:用 `observe` 读导航结构得到可达入口清单,减去执行过程中累积的已覆盖页面,对差集逐个导航 + 拉运行时错误。

- **补的是什么缝**:用例集永远无法穷举页面。菜单点得到、但本轮没有任何用例覆盖的页面,其接口 500 / JS 报错**当前完全测不出**——运行时错误捕获只在用例执行后触发,没有用例就没有触发点。
- **不是"每个模块跑完之后"**:那时已覆盖集合还不完整,会把后面模块正要测的页面误判为未覆盖。
- 结果写 `results/`,**必须带 `entry_kind: "free-scan"`**,`case_id` 用 `运行时-<页面>`。
- ⚠️ **巡检项不计入用例统计、不进缺陷列表**,单列报告 §2.6 —— 它没有断言,混进 `total` 会让"巡检页越多通过率越好看",方向恰好是反的。漏标 `entry_kind` 时 `check_result.py` 报 Important。
- 上限 `free_scan_max_pages`(默认 20),超出**不静默截断**:单写一条 block 巡检项列明被跳过的页面。

细则见 [`references/execution-methodology.md`](./references/execution-methodology.md) 第十二节。

### 第四步:报告汇总(report)——固定结构输出

聚合 `results/*.json` 生成固定结构报告(模板 [`assets/report-template.md`](./assets/report-template.md),细则 [`references/report-format.md`](./references/report-format.md)):**一、测试概况 / 二、测试结果汇总(汇总数据·各模块通过情况·缺陷列表·用例执行明细)/ 三、结论(上线条件·遗留风险·改进建议)**。

> **★报告里的事实字段一律要有来源,不许模板默认(通则):** 「一、测试概况」的**环境事实类**字段取自环境准备阶段落盘的 `round-{M}/env-facts.json`(闭环步骤 0),**逐字段带来源标注**;「二、汇总」的**统计类**字段取自 `results/*.json` 经 `gen_report.py` 聚合,**人不手工计数、不照抄模板示例数字**。两类共同红线:**没有实测支撑的值写「未取到 + 原因」,不写一个像样的默认值。**可用 `python3 <SKILL_DIR>/scripts/gen_report.py <round目录> --md` 聚合。**注意:该脚本只产出「二、测试结果汇总」章(2.1~2.7,其中 2.5 self-heal 追溯 / 2.6 自由巡检为可选节、无数据时不输出;**2.7 耗时分布不是可选节** —— 一条都没采集时打「本轮 N 条全部未采集」而**不是留空表**,空表会被读成「都很快」),「一、测试概况」与「三、结论」须由报告子 Agent 按模板补写**——直接把脚本输出当完整报告交付会缺章节、违反质量维度 7。

---

## 执行模式分级(端无关,按用例优先级/类型自动选)

方法论层据用例**优先级/类型自动选模式**,三级**以「取证强度 + 自愈策略」区分,而非是否执行**:

| 模式 | 触发条件(按序判定) | 行为 |
| :- | :- | :- |
| **失败自愈(self-heal)** | 用例类型含「集成/跨模块」**或** 存在上一轮结果为 `fail`/`block`(失败复测) | 执行 + 强制取证 + **失败时恢复状态后重试**(如重新登录/回到起始页/重建前置数据再跑一遍);仍失败才标 block。用于最易受环境波动影响的用例 |
| **强制取证(verified)** | 优先级 **P0 / P1**(核心 + 重要功能) | 执行 + **每个 pass 判定必须有可观测证据**(截图 / 关键元素文本 / 列表计数)。「没有证据的 pass 等同未验证」,不能仅凭页面正常加载判 pass |
| **直接执行(direct)** | 优先级 **P2** 及其他(兜底默认) | 标准执行,失败记录即可;pass 至少留一条轻量事实,不要求完整截图 |

判定顺序:先看是否 self-heal(集成/失败复测)→ 否则 P0/P1 走 verified → 否则 direct。

---

## 感知-执行-校验-决策闭环(端无关,单条用例)

每条用例 = 感知/执行/校验/(运行时错误捕获)/决策阶段,**全程只调用驱动适配层的四原子能力,不写任何端专有 API**:

> **前置:环境准备(★不在本闭环内,频次也不同)。** 驱动连接后、首条用例前另有三件事,**频次务必分清**——
> - **实例归属防呆:每个执行子 Agent 连上驱动后各做一次**(每模块一个子 Agent、每次连接都可能连错实例);
> - **运行环境取证:每轮一次(首模块)**,产出 `round-{M}/env-facts.json`(形状见 [`assets/env-facts-schema.json`](./assets/env-facts-schema.json)),作为报告「一、测试概况」段的**唯一数据源**;后续模块复用,不重复取证。
> - **★数据源归属校验:每轮一次**,仅当配了 `datasource` 且本轮有 `[双源对账]` 用例或 SQL 造删数时做。**配了 DB 连接 ≠ 它就是被测环境的库**——用错库的对账**比不对账更危险**(SQL 值与页面值本就不该相等,结论要么假性全红误报一批缺陷、要么凑巧全绿漏掉真缺陷,而 `match` 看上去笃定)。三级探针(环境标识 → 环境指纹 → 端到端回读)、四态结论与降级处置见 [`references/execution-methodology.md`](./references/execution-methodology.md) 第十一节;**结论不是 `verified` 时,报告里不得出现任何基于该库的 `db_assertion.match` 结论**。
>
> 取证走 `observe` 的**运行环境通道**(端无关,**不新增第五个原子能力**)。三条铁律:**取不到不许编**(写 `null` + `未取到(原因)`,严禁回落模板默认或"看起来合理"的推断值)、**每个事实字段配套 `XSource` 来源标注**、**复用已有实例时命令传参不生效、必须以运行探测为准**。判据会随被测端版本漂移,**须实测复核后写进 `references/driver-<端>.md`**。
>
> **★`XSource` 只能取这五类前缀(整串形态 `前缀` 或 `前缀(说明)`,硬门按整串匹配):**
>
> | 前缀 | 何时用 | 括号 |
> | :- | :- | :-: |
> | `显式指定` | 编排层/run-context 传入 **且已确认 `reusedInstance=false`** | 可不带 |
> | `复用已有实例(来源)` | 连到已存在的实例,传参不生效 | **必带** |
> | `无头不可用降级(原因)` | 显式降级 | **必带** |
> | `运行取证(方法)` | 执行期实测,写明用什么信号测出来的 | **必带** |
> | `未取到(原因)` | 实测取不到 → **值必须为 `null`** | **必带** |
>
> 三条配套硬规则:① **除「显式指定」外一律必须带 `(说明)`**;② **`未取到` 与值为 `null` 互为充要条件**——写了 `未取到` 值就必须是 `null`,值是 `null` 来源就必须写 `未取到`;③ **「运行配置」不是第六类**,驱动能直接返回运行配置时那是最权威的**取证方法**,来源仍写 `运行取证(驱动运行配置:…)`。**完整字段清单、判定顺序、硬门口径的细则以 [`references/execution-methodology.md`](./references/execution-methodology.md) 第十节为准**(与 [`assets/env-facts-schema.json`](./assets/env-facts-schema.json) 的 `$sourceEnum` 同源);硬门 `scripts/check_env_facts.py`。

1. **感知(observe)**:读当前页面/会话状态,判断前置是否已满足(不满足才导航/登录)。
2. **执行(act)**:按用例四要素步骤,逐步 `locate` 目标元素 → `act` 执行动作(点击/输入/选择/滑动/上传/返回…)+ 操作数据。
3. **校验(assert)**:每步操作后 `observe` 读结果,与用例「预期现象」比对断言;verified/self-heal 模式 `capture` 取证。用例步骤带 `断言:` 行时优先按语义断言做确定化判定(DSL 见 usecase-format.md 第六节)。**★值级断言硬约束(不限 P0/P1):** 涉及**数值/状态/权限**的用例必须带值级断言,**严禁把「页面加载成功/无 console error/元素存在」当作唯一 pass 判据**;`[双源对账]` 用例的值由 DB 断言驱动对账 SQL 真值(`db_assertion.match`)。
4. **运行时错误捕获(★每条用例执行后必做)**:无论 pass/fail/block,通过 `observe` 的运行时错误通道(console/network,端相关·可选)拉一次 console + network 请求,把 console 报错 / network 非 2xx / 页面级错误 UI 写入结果 JSON 的 `runtimeErrors`。**pass 用例也要拉**(页面能用但后台有 500/JS 报错时供下游升级 bug)。详见 [`references/execution-methodology.md`](./references/execution-methodology.md) 第三节步骤 4。
5. **决策(decide)**:
   - 关键预期验证失败 → 立即判 `fail`(不重试)。
   - 单操作连续失败达重试上限(默认 3 次)→ 判 `block` + 记录证据。
   - **★驱动进程级无响应(与元素级失败区分开)→ 先自愈,别逐条耗尽**:连续多次原子调用全超时**且**一次轻量探活(`observe` 的 `driverAlive` 通道)也无回应 → 判驱动卡死 → `act(—, 'resetSession')` 重建驱动 → 恢复登录 → 断点续跑;**连续 `driver_heal_retry_limit`(默认 3)次自愈都失败**才判 `block(driver-hung)` + 证据。单元素 `locate` 失败**不走这条**,仍按上一条重试。细则见 [`references/execution-methodology.md`](./references/execution-methodology.md) 第四节。
   - 全部预期通过 → 判 `pass`。
   - self-heal 模式失败时先执行「状态恢复 → 重试一遍」再落定。

---

## 驱动适配层:四原子能力抽象(可插拔)

方法论层**只依赖以下四个端无关原子能力**;每个被测端提供一个适配器实现它们。契约与各端映射详见 [`references/driver-adapters.md`](./references/driver-adapters.md)（端无关契约 + 探测降级 + 加载索引）；**各端专有细则按被测端加载 `references/driver-<端>.md`，勿全量读**。

| 原子能力 | 端无关语义 | 输入 → 输出 |
| :- | :- | :- |
| **locate(定位元素)** | 用**语义定位符**(可见文案 / 角色+名称 / label,非底层选择器)定位元素 | `语义定位符` → `元素句柄` |
| **act(执行动作)** | 执行一个**端无关动作词**(tap/input/select/swipe/scroll/back/upload/dialog/waitFor) | `(句柄, 动作词, 数据)` → `操作结果` |
| **observe(读取页面状态)** | 读当前结构化页面/会话状态(当前页/标题/可见元素/文本/计数/登录态);另有两条**可选、端相关**的附加通道:**运行时错误通道**(console/network)与**运行环境通道**(env,供环境准备阶段的运行环境取证) | `()` → `结构化状态` |
| **capture(截图取证)** | 每次只归档一张实际截图;快照/控件树由 `observe` 单独提供,不与截图打成双格式副本 | `(标签)` → `实际证据路径` |
| **capture(截图取证)** | 产出可归档证据(Web:截图+快照;移动/桌面:截图+控件树;小程序:截图) | `()` → `证据产物路径` |

**适配器矩阵(至少覆盖四端;★成熟度标注,下游据此判各端可用程度,勿误以为四端等价可跑):**

| 被测端 | 成熟度 | 可插拔驱动 | 适配器 reference |
| :- | :- | :- | :- |
| **Web 浏览器** | **已验证(主场景,MCP 插件工具)** | chrome-devtools-mcp(推荐)/ Playwright | [`driver-web.md`](./references/driver-web.md) |
| **移动 APP(Android/iOS)** | **部分(Appium 伪代码,未端到端验证)** | Appium / UIAutomator2 / XCUITest | [`driver-mobile.md`](./references/driver-mobile.md) |
| **微信 / 各厂小程序** | **预留未验证** | miniprogram-automator 等 | [`driver-miniprogram.md`](./references/driver-miniprogram.md) |
| **桌面客户端** | **预留未验证** | Playwright-Electron / WinAppDriver 等 | [`driver-desktop.md`](./references/driver-desktop.md) |

> **能力探测 + 优雅降级(Critical):** 加载适配器前用 `scripts/detect_drivers.py` 探测该端驱动是否可用;**不可用时明确报缺失并跳过(标 block(driver-missing)),不硬失败、不挂起**。新增端只需实现四原子能力,方法论层零改动。

> **★(条件启用)Web 适配器的可选第五能力 `invoke`——WebMCP 工具调用:**
>
> ⚠️ **维护者注意:本段落在 `check_layer_isolation.py` 的豁免区内**(所在章节标题命中
> `ADAPTER_HEADINGS`,整节跳过扫描)。**端专有 API 一律写进 `driver-web-webmcp.md`,不要写在这里**
> ——写了不会被硬门拦下,而这正是「方法论层零端专有 API」这条 Critical 的盲区所在。
>
> **WebMCP 不是第五个「端」**,而是 **Web 适配器的一项可选补充能力 `invoke`**(列出 / 调用页面登记
> 的工具),仍在浏览器里、仍经同一个 Web 驱动;端专有调用约定只落
> [`references/driver-web-webmcp.md`](./references/driver-web-webmcp.md),**方法论层零改动**。
> 探测不到时**优雅降级**(相关用例标 block,其余照跑);其它端**本端不适用**、须明写不留空。
>
> **门控(硬前提):** 仅 `webmcp_enabled: true` 时启用。**为 `false` 或未传 → 整段跳过**:run-context
> 不写相关字段、报告不留位置、不产生告警。**⛔ 本 skill 不自行探测是否启用。** 另两个入参
> `webmcp_entry_symbols` / `webmcp_launch_command` 同样由调用方传入、**不得写死**。
>
> **启用时必读该适配层文件**——两条调用路径的区分、驱动版本门、两个浏览器开关与 origin 三段精确
> 匹配、连接后自检、与 CDP 的分工、报告纪律,判据全文都在那里,**只读本段做不对**。

> **★DB 断言驱动(数据真值对账 · 可插拔 assertion driver,与 UI 四能力并列):** 除四个 UI 原子能力外,驱动适配层另设一个**可插拔的 DB 断言驱动**,专供 `[双源对账]` 用例执行期把**页面取值 ⟷ 数据库真值**对账(执行用例给出的等价 SQL,复用会话已连 DB MCP 或 run-context `datasource`)。**两层解耦不受影响:方法论层只声明抽象需求「值级断言/数据真值对账」,具体 SQL/DB MCP 调用只落在 [`references/driver-db-assertion.md`](./references/driver-db-assertion.md) 适配层。** 结果写入 `db_assertion`,`match=false` 判 fail。前置数据编排的 SQL 造删数途径复用同一驱动。

---

## 进度断点恢复(tasks.md 状态机)

`round-{M}/tasks.md` 是断点续跑的单一进度真相,4 态状态机:

| 标记 | 含义 | 流转 |
| :-: | :- | :- |
| `[ ]` | 待执行 | 批量执行前整模块 `[ ]→[>]` |
| `[>]` | 执行中 | 执行完据结果 → `[√]` 或 `[!]` |
| `[√]` | 已完成(pass) | 终态;**同 build 内**续跑时跳过 |
| `[!]` | 阻塞/失败(fail/block) | 终态;**同 build 内**下一 round 的 self-heal 复测入口(非跨 build) |

- **持久化**:状态写盘 tasks.md,详细用例内容按 TC-ID 现查,tasks.md 只存 ID+名称,降载。
- **续跑**:中断后重跑,`python3 <SKILL_DIR>/scripts/tasks_state.py resume` 扫出所有 `[ ]`/`[>]` 续跑,已 `[√]` 跳过,**不从头重来**。
- **★resume/`[√]`-跳过的作用域仅「同一 build 内中断恢复」(硬边界):** `resume` 与「已 `[√]` 跳过」只用于**同一 `build-{N}` 内**执行被中断后的续跑;`[!]`→ self-heal 复测入口也只在**同 build 内的下一 round**,是「只复验失败用例」的窄口径复测,**不得跨 build 沿用**(跨 build 只复验被修用例会漏同源缺陷)。
- **★跨 build 边界 = 新回归轮,全量重跑:** 新 `build-{N+1}`(上一 build 缺陷经外层 bugfix 修复后的新回归)**必须 `init` 全新 tasks.md、全部用例回初始态 `[ ]`、全量重跑**,**绝不沿用上一 build 的 `[√]`、绝不 `resume` 跨 build、绝不只跑被修用例**——只复验被修用例会漏同源缺陷(如修完 P0 只验那条、漏同根因的 P1)。
- **补齐遗漏**:第三步 checker 确保无 `[ ]`/`[>]` 残留才允许出报告。

---

## 证据取证(可插拔,端相关强度)

- **取证时机**:登录 / 提交 / 状态变化 / 断言通过或失败 / 报错——这些关键步骤 `capture` 取证。
- **强度按模式**:direct 的 pass 至少记录一条轻量事实(实际值/命中文案/列表计数/产物路径),不要求截图;verified/self-heal 每个 pass 都要完整证据。
- **端相关产物**:每次 `capture` 只归档一张截图;Web 的无障碍树/DOM 快照、移动/桌面的控件树由 `observe` 单独提供,需要留痕时作为独立 evidence 条目,不与同一截图生成多格式副本。**capture 接口统一,截图扩展名由适配器决定**。
- **单产物 + 真实路径契约**:`capture(标签) → 实际证据路径`;每次 capture 只生成一种实际可用格式,失败时不创建空文件、不伪造 artifact。调用方只把返回值原样写入 `results/*.json` 的 `evidence[].artifact`,严禁按 TC-ID 自行补 `.png` / `.webp`。截图兼容 `.webp/.png/.jpg/.jpeg`,JPEG 仅作已有驱动兼容,不作 UI 默认格式。
- **归档**:`round-{M}/evidence/{TC-ID}-step{步骤号}.{ext}`;缺证据的 verified pass 视为未验证,格式变化不降低 verified / self-heal 的取证强度。
- **端相关产物**:Web 出「截图 + 无障碍树/DOM 快照」;移动/桌面出「截图 + 控件树」;小程序出「截图」。**capture 接口统一,产物形态由适配器决定**。
- **归档**:`round-{M}/evidence/{TC-ID}-{步骤号}.{png|json}`;结果 JSON 的 `evidence` 字段记录关键证据摘要 + 产物路径。缺证据的 verified pass 视为未验证。

---

## 脚本(scripts/,Python 3.8+ 标准库,支持 --json)

| 脚本 | 用途 |
| :- | :- |
| `tasks_state.py` | tasks.md 状态机:`init`(建)/ `update`(改状态)/ `scan`(统计各态)/ `resume`(列续跑项);断点续跑内核。另有 `selftest`:校验套件/用例标题形态**与 `--select` 优先级形态**识别未被收窄(改解析正则后必跑,收窄 = 静默漏跑);**`init --select all|smoke|regression` 执行选集**(复用既有 P0 与 `[回归]`,不新增标签;子集 tasks.md 头部写留痕行;`regression` 禁用于新 build 回归轮) |
| `detect_drivers.py` | 驱动能力探测:按端类型探测驱动是否就绪,输出可用/缺失 + 降级建议(优雅降级依据)。**`--webmcp`(条件启用)** 额外校验 WebMCP 工具列出与调用所需的 `chrome-devtools-mcp` ≥ 1.8.0,输出 `webmcp.{detected_version,version_source,satisfied,block_reason}`;**不加该参数时输出里没有 `webmcp` 段**,且**版本结论不影响退出码**(版本不足 ≠ 驱动缺失) |
| `gen_report.py` | 从 `results/*.json` 聚合生成固定结构报告 + 统计(总数/pass/fail/block/**na**/通过率(分母排除 na)/**自动化率 + 自动化覆盖率·成功率(按 block_reason 细分,driver-missing=0 时与旧口径一致)**/各模块;**缺陷分级先判用例族——`[回归]`(`is_regression`)/`[PRD存在性]`/`[文案一致性]` 失败锁 Critical,覆盖优先级映射(**环境类 block_reason 除外**)**;聚合 self-heal 失败复测追溯 `self_heal_trace`;校验无证据的 verified pass) |
| `check_result.py` | **结果 JSON 落盘前校验**:形状(`evidence`/`runtimeErrors` 必须是**对象数组**,元素含 `artifact` / `type`+`message`+`severity`)、artifact 必须是当前 `round/evidence` 内的相对路径（禁绝对路径/`..`/旧轮次，results/结果 JSON/round/evidence 根均不得是符号链接）、实际文件存在且非 0 字节、截图扩展名兼容集(`.webp/.png/.jpg/.jpeg`)与最小容器结构校验、截图文件名须绑定当前 case_id/step、同一截图跨字段/递归磁盘索引禁止多格式副本（后缀大小写/符号链接不绕过）、`status` 枚举(含 `na`)、`na` 理由、`block_reason` 枚举、verified/self-heal 的 pass 是否有证据、`self_heal_applied` ⟷ `self_heal_trace`、`db_assertion` 结构与「match=false 必判 fail」。`assets/result-schema.json` 是**示例而非可校验 Schema**,机器约束由本脚本承载;校验 `entry_kind` 枚举与**漏标巡检项**;`target` 支持多路径(跨轮次 glob),某个 target 空匹配会报 Important 防「少校验一整轮却显示通过」 |
| `check_result.py` | **结果 JSON 落盘前校验**:形状(`evidence`/`runtimeErrors` 必须是**对象数组**,元素含 `artifact` / `type`+`message`+`severity`)、`status` 枚举(含 `na`)、`na` 理由、`block_reason` 枚举、verified/self-heal 的 pass 是否有证据、`self_heal_applied` ⟷ `self_heal_trace`、`db_assertion` 结构与「match=false 必判 fail」。`assets/result-schema.json` 是**示例而非可校验 Schema**,机器约束由本脚本承载;校验 `entry_kind` 枚举与**漏标巡检项**;`target` 支持多路径(跨轮次 glob),某个 target 空匹配会报 Important 防「少校验一整轮却显示通过」 |
| `check_layer_isolation.py` | 两层解耦检查:扫方法论层是否泄漏端专有 API(质量维度 1) |
| `check_env_facts.py` | 运行环境事实取证校验(**判据口径以 `references/execution-methodology.md` 第十节为单一信源**):必备字段齐全且类型合契约 / 事实字段与 `XSource` **双向成对** / 来源落五类枚举且形态合法 / `null` 与「未取到」互为充要条件 / 无模板占位残留 / `reusedInstance` 为 true 或未取到时渲染模式不得声称「显式指定」;带 `--report` 时**在「一、测试概况」章节范围内**核对报告与取证事实一致。**新增事实字段自动纳管**(除 `$`/`_` 开头与元数据白名单外,任何字段都要求配套 `XSource`),无需改脚本 |

---

## 与其他 SKILL 的协作

```
dev-manual-testcase(生成标准自测用例 + 自测方案)
              │  产出 SUITE-*/TC-* 用例
              ▼
       auto-test-runner(本 skill:端无关批量执行 → 报告)
              │  按被测端选驱动适配器,无人值守跑完
              ▼
     固定结构测试报告(概况/汇总/各模块/缺陷/明细/结论)
```

- **上游**:输入严格对接 dev-manual-testcase 的用例格式,不自造用例。
- **下游命令端**:只编排调用(传用例路径/被测端/环境/账号/驱动选择),不复述执行细节——执行方法论以本 skill 为单一信源。

---

## Post-Execution Quality Review(执行后质量检查)

执行与报告产出后,由**独立子 Agent**执行质量检查(维度清单见 [`references/quality-review-checklist.md`](./references/quality-review-checklist.md)),核验:两层未耦合(方法论层无端专有 API)、tasks.md 无 `[ ]`/`[>]` 残留、verified 用例证据齐全、direct pass 至少有轻量事实且缺失项被单列、报告章节完整(3 大章 · 6 个必备内容块)、**概况的环境事实字段来自取证且逐字段带来源标注(非模板默认)**、block 项均有证据与原因、无人值守全程未挂起。**主流程禁止在当前上下文内联跑检查**,派独立子 Agent 回传精简报告。

---

## 约束

> **本节 11 条约束是可被机器校验的编号契约**：形态固定为 `### 约束 N：<标题>`，与
> `references/quality-review-checklist.md` 的 `#### 维度 N:` 同构。下游按「约束 N」引用本节时，
> **引用处必须同时带上该约束的标题关键词**——只写编号无法校验新鲜度：编号在增删条目时会整体位移，
> 而位移后的错误引用两侧都仍"在范围内"，任何越界检查都发现不了（实测下游确实出现过
> 引用第 9 条、实指第 10 条的错位，长期无人告警）。带上标题后，编号与标题对不上即可被抓。
> 引用侧由 `{{AIDP_HOME}}/scripts/check_skill_ref_freshness.py` 机检(编号须在本 SKILL 内存在)。

### 约束 1：两层分离

方法论层严禁出现任何端专有 API(如 `browser_click`/`driver.find_element`);一切端操作走四原子能力抽象。

### 约束 2：无人值守不挂起

执行全程不等人;阻塞标 block + 证据 + 继续。
- **★测试执行内绝不修改业务代码、绝不修复缺陷(红线)** — 执行内核只「判定 + 记录」:缺陷记入 problem/缺陷汇总清单 + 标 block/fail + 继续测完,绝不改被测业务代码/配置/表结构绕过缺陷,修复交外层 bugfix 流程;self-heal「恢复」仅限会话/登录/前置数据运行态,不碰业务代码。

### 约束 3：会话复用降 token

分模块批量、模块内串行、一次登录共享会话,禁止逐条重登录。

### 约束 4：断点可续跑

tasks.md 4 态状态机持久化;续跑跳过 `[√]`,不从头重来。

### 约束 5：报告结构固定

概况 / 汇总(数据·各模块·缺陷列表·执行明细)/ 结论(上线条件·遗留风险·改进建议),不得裁剪章节。

### 约束 6：优雅降级

驱动不可用报缺失 + 跳过,不硬失败。

### 约束 7：单一信源

执行方法论沉淀于本 skill;下游命令端只编排、不复述。**「运行环境取证」的判定逻辑同样以本 skill 为单一信源,命令端只消费 `env-facts.json`、不复述判定规则。**

### 约束 8：输入对接标准

用例严格对接 dev-manual-testcase 输出格式。

### 约束 9：条件启用能力不留痕

由调用方入参门控的可选能力(当前:`webmcp_enabled` 之于 WebMCP 工具调用),**未启用时整段不适用**:run-context 不写相关字段、报告不留相关位置、不产生告警、不占篇幅。**⛔ 本 skill 不自行探测是否启用**(判定散落多处必然漂移,一处判错就给未启用项目凭空长出 block 项与报告位)。⛔ 驱动版本不足时**不得静默降级为「就当没有该能力」**——标 block + 证据,否则这一整类用例会全绿式消失、报告看不出漏测。

### 约束 10：事实字段可溯源、禁模板默认

报告里的**环境事实类**(渲染模式/浏览器版本/viewport/是否复用已有实例/被测 URL/登录角色)与**统计类**(总数/Pass/Fail/Block/各类率)字段,一律逐个确认来源是**实测取证/脚本聚合**而非模板默认或意图推断;取不到写 `null` + `未取到(原因)`,**绝不伪造**。硬门:`check_env_facts.py`。

### 约束 11：单条耗时必须采集，WebMCP 必须分层

**耗时**：每条用例结果 JSON 必须带 `started_at` / `finished_at` / `elapsed_ms` 三件套，
`gen_report.py` 据此产出「§2.7 耗时分布」。⚠️ **没有单条耗时，任何优化都无法验证是否生效** ——
没有单条耗时，「一条用例占整轮 25%」这类结论只能靠 evidence 文件 mtime 手工反推，
而那**只对产出了多个 evidence 的用例有效**，非常容易整条漏掉。
⚠️ 报告出现 `execution_mode` 分布时**必须同时给出实际触发自愈次数** ——
`execution_mode=self-heal` 是「**具备**自愈能力」，不是「实际自愈了」（实证：43 条 self-heal vs 实际重试 1 次，
调优方向当场被带偏）。

**WebMCP 分层**：状态准备 / 数据构造 / 非视觉断言**可走** WebMCP 工具调用；
**视觉还原度 / 布局 / 样式必须 DOM + 截图**，⛔ 一刀切两个方向都会出事，
而「用过头」比「不敢用」危险得多——**它会产出一份全绿而无效的报告**。判据全文见
[`references/execution-methodology.md`](./references/execution-methodology.md) 一·补三。

⚠️ **「非执行开销」这类差值不能直接当作可优化的开销**（实证提醒）：
`总耗时 − evidence 首尾跨度` 把报告生成、终审、文档级联这些**交付物本身**也算了进去。
在单条 `elapsed_ms` 落地之前，针对「开销」的任何优化都无法验证是否生效 —— **先做计时，再谈开销**。
