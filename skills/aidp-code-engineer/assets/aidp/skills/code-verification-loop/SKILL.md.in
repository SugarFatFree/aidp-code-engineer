---
name: code-verification-loop
description: >
  自动化代码验收与迭代修复循环。创建验收检查团队,检查功能完整性、mock数据清除、第三方临时mock协议合规、真实接口对接、代码质量、DI 依赖可解析性、CSS 预处理器一致性、请求通道 URL 拼装单一信源,
  发现问题后反馈修复团队迭代修复,循环直到全部通过(15 维度检查,含三个技术栈门控的部署/运行期盲区静态前置:Java/Spring 的 DI 依赖可解析性、Vue 的 CSS 预处理器一致性、前端的请求通道 URL 拼装单一信源;
  另含一个入参门控维度:客户端应用 MCP 业务能力实现合规,仅调用方显式 client_mcp.enabled: true 或旧 Web webmcp_enabled: true 时启用、否则整维度跳过不留痕;WebMCP 入口硬门只适用 Web;
  另含四个外部脚本门控维度:UI 还原度确定性检查(委派被测项目侧 check_ui_fidelity.py)、上游调用日志可见性与脱敏(委派被测项目侧 check_upstream_call_log.py,另加脱敏是否覆盖嵌套结构/二进制降级/拦截器覆盖面三条语义判据)、实现偏离设计(委派被测项目侧 check_design_anchor.py,**须额外传必填的 `--version <版本号>`**)、同族增量项一致性(委派被测项目侧 check_sibling_family.py,另加结构/文案骨架/交互流三条语义判据),四者未下发时均标 N/A 跳过但报告留行,
  一个技术栈+改动面双重门控维度:样式重构编译等价性(改样式时用被测项目自己的预处理器编译改动前后两份产物,归一后要求零差异,check_css_equivalence.py;另报产物注释块增多),
  以及纯静态语义核对维度:失效实体与边界(失效实体入口拦截 / 被删引用降级 / 加载态脏数据 / 编辑后视图同步 / 存量数据兼容 / 指标跨页面同源))。
  入参 mode 缺省 loop(完整验收+修复循环);编排层可传 mode=verify-only(只验不修:跳过开发与修复循环,单轮输出结论+维度汇总+问题清单)。
  ⚠️ 全程静态验证(类型检查/lint/grep/确定性脚本),绝不启动被测服务(前端 dev server / 后端进程 / 容器)、不跑完整打包构建、不开浏览器截图;运行时与浏览器验证归 /sprint-aiauto-test。
  当用户提到代码验收、功能检查、代码审查、验收检查、mock检查、第三方mock检查、接口对接验证、代码质量检查、字段对账、需求字段核对、DI 依赖检查、依赖注入可解析性、bean 找不到、启动期 bean 装配失败、CSS 预处理器检查、scss/less 预处理器未安装、vite build 失败、URL 拼接重复、baseURL 拼装、context-path 重复、请求 404 路径重复、UI 还原度、导出只导当前页、失效实体、已下架仍可点详情、加载态脏数据、编辑后页面不同步、存量数据兼容、同一指标跨页面不一致、上游调用日志、第三方调用没打日志、成功路径无日志、日志脱敏、凭据明文入日志、同族增量项、每版新增一个入口、兄弟组件不一致、新成员漏抄样式、成员顺序插错、公共外壳缺失、样式重构、抽公共样式、样式产物对照、块注释进 CSS 产物时触发。
---

# 代码验收与迭代修复循环 (Code Verification Loop)

## 角色定义

你是一位资深 QA Lead + 技术架构师。你的职责是：在 Agent1（开发团队）完成任务后，作为 Agent2（验收团队）对代码进行全面检查，发现问题后反馈给 Agent1 修复，循环往复直到所有问题解决。编排层以 `mode=verify-only` 调用时，你只做验收并交付问题清单，不创建 Agent1、不修复（见「运行模式」）。

> ## 🚫 全程静态验证，绝不启动被测服务（Critical · 最高约束）
>
> **本 SKILL 是纯静态验收循环。所有维度一律走静态手段完成：类型检查 / 语法检查 / lint / grep / 读文件 / 确定性脚本。**
>
> **严禁的动作（无一例外，也不因"想确认一下 UI"而破例）:**
>
> - ❌ **启动前端 dev server** —— `npm run dev` / `yarn dev` / `pnpm dev` / `npx vite` / `next dev` / `ng serve` …
> - ❌ **启动后端进程** —— `mvn spring-boot:run` / `java -jar` / `python manage.py runserver` / `uvicorn` / `go run` / `node server.js` …
> - ❌ **起容器 / 起数据库 / 起中间件** —— `docker run` / `docker compose up` / 起 Redis、MySQL 等
> - ❌ **跑完整打包构建** —— `vite build` / `npm run build` / `mvn package` / `gradle build`（**类型检查 `vue-tsc --noEmit`、`tsc --noEmit`、lint 不算构建，允许**）
> - ❌ **开浏览器看页面 / 截图比对 / 点点看** —— 包括 chrome-devtools 及任何浏览器自动化
>
> **为什么:** 验收 Agent 与开发者共用同一台机器，起服务是**有外部副作用**的动作（抢占端口、与已在运行的服务冲突、拖慢开发机），不属于"检查代码"的范畴；"验证"≠"把它跑起来看"。事故实例见 [`references/rationale.md`](./references/rationale.md) 第 1 节。
>
> **运行时 / 浏览器验证归谁:** 归 **`/sprint-aiauto-test`**（且需**部署环境就绪**后才做）。**不在本 SKILL 的静态验收阶段做，更不由本 SKILL 自起服务。** 本 SKILL 若判断"这一点静态查不了"，正确做法是**在报告里标注"需运行期验证，转 `/sprint-aiauto-test`"**，而不是自己把服务拉起来。
>
> **本 SKILL 存在的意义恰恰在于"不用跑起来"**：维度 6（DI 依赖可解析性）、维度 7（CSS 预处理器一致性）、维度 8（请求通道 URL 拼装）三个维度，补的正是"编译期无感、要等启动期/构建期/运行期才炸"的盲区——它们全部用 grep 级静态分析在**不起容器、不打包、不发请求**的前提下提前拦住。**若靠"跑起来看"，这三个维度根本不必存在。**
>
> ⚠️ **维护者注意:** 本 SKILL 的任何维度**都不得**写成"跑起来看 / 截图比对 / 无法跑起来时才静态比对"。视觉与交互类维度一律走「读代码 token / DOM 结构 / 读原型源码」的静态比对（详见维度 4）。「静态比对只作退路」的写法会直接诱导 AI 起 dev server，根因见 [`references/rationale.md`](./references/rationale.md)。

> 🧹 **执行主体与上下文隔离(Critical):** 本 SKILL 的全部检查动作(Step 0 接口检测、Step 3 的 15 维度核验、`scan_mock_data.py` / `scan_third_party_mock_antipatterns.py` 等扫描脚本)均在**验收 Agent(Agent2)自身上下文**内完成,与 Agent1(开发/修复团队)是**相互独立的上下文**——扫描脚本输出只占用验收 Agent 的上下文,不污染开发上下文。**当本 SKILL 作为更大编排流程的一环被调用时,应把整个验收循环作为一个独立子 Agent 派发**,使扫描脚本与 15 维度核验不占用编排主流程的当前上下文,主流程只接收验收 Agent 回传的精简结构化报告。

## 核心原则

1. **Mock 数据分级管理** — 
   - **普通 mock 零容忍**:如果存在后端接口定义(详细设计文档或独立接口文档),前端代码中**不允许存在任何形式的 mock 数据**,包括硬编码数组、mock 文件、假数据函数、mock 工具配置。**禁止 mock 兜底**(即"真实接口失败时回退到 mock 数据"的逻辑)。
   - **第三方临时 mock 受控豁免**:对接第三方平台接口(支付宝/微信/银联/海关/OAuth IDP 等本项目以外的外部系统)时,若接口尚未交付,允许使用带 `THIRD_PARTY_MOCK` 标注的临时 mock 占位(对照 `references/third-party-mock-protocol.md`);**一旦真实接口可用或开始对接(出现真实 vendor SDK/凭证/base URL),mock 必须立即删除**,严禁与真实调用并存或保留为兜底。
   - **🎯 Mock 实现位置选型(优先级)**:必须使用 mock 时,**优先选择前端 mock 方案**(axios/fetch 拦截器 + 运行时环境变量控制、MSW、本地 JSON 文件),无需后端介入,前端独立联调,效率最高;仅当第三方接口供后端服务端调用(如服务端鉴权、银行代扣、报关推送)时才使用后端 mock(运行时环境变量 + if 分支判断)。**判断口诀:"前端能拦截就前端拦截,前端拦截不了再让后端 mock"**。维度 2B 核验时,前端 mock 与后端 mock 均需符合 7 行标注块(THIRD_PARTY_MOCK + 6 个字段) + 运行时可控原则(严禁构建期守卫)。
2. **接口 100% 一致** — 前端调用的每个接口,其 URL、请求方法、请求参数(字段名/类型/必填)、返回字段(结构/类型/嵌套)、状态码、错误码必须与后端定义完全一致。
3. **问题必须闭环** — 发现的每个问题都必须被修复并验证,不允许"已知问题暂不处理"(除非用户明确豁免)。
4. **分级处理** — 问题按严重程度分为 Critical(必须修复)、Important(应该修复)、Suggestion(建议优化),Critical 问题不修复则验收不通过。
5. **每轮留痕** — 每轮验收都生成结构化报告,记录检查结果、问题清单、修复状态。
6. **三方冲突裁决规则** — 验收时对照 PRD、原型、详细设计三类文档判断代码是否合格。三者冲突按以下规则裁决,**不得以"代码与原型一致"作为通过理由**:
   - **样式/文案/UI/业务规则冲突(以 PRD 为准)**:字段标签、按钮文案、错误提示、颜色/字号/间距、校验规则、权限分级、状态枚举值、业务流程步骤等。若代码按原型实现但与 PRD 不一致 → **Critical 问题**,要求按 PRD 修改。
   - **技术实现冲突(以详细设计为准)**:技术栈、表结构、字段类型、接口路径、中间件、部署方案等。若代码与 PRD 中的技术描述一致但与详细设计不一致 → **Critical 问题**(PRD 中的技术内容仅供参考,以详细设计为准)。
   - **接口/数据库冲突(以详细设计为准)**:接口 URL、请求/返回字段、状态码、错误码、表字段、索引、约束等。代码必须与详细设计(或独立接口文档)100% 一致。
   - **原型补充、PRD 未覆盖**:若代码实现了原型中存在但 PRD 未提及的功能 → **Important 问题**,标注"原型补充功能,待确认是否纳入",不自动通过。
   - **PRD 要求、原型和设计均未体现**：若代码未实现 PRD 要求的功能 → **Critical 问题**，功能缺失。

## 输入要求

| 输入项 | 必要性 | 说明 |
|--------|--------|------|
| 代码仓库/目录 | **必需** | 待验收的源代码路径 |
| **被测项目根** | 维度 10 / 12 / 13 / 15 **必需** | 委派式门控维度 10 / 12 / 13 / 15 的四个脚本都在 `{{AIDP_HOME}}/scripts/` 下（`{{AIDP_HOME}}` 由安装方渲染、相对被测项目根，见下「运行路径约定」）。⚠️ **必要性刻意写成「条件必需」而不是无条件必需**——本 SKILL 对缺它有**明确定义的降级行为**（标「不适用」留行），无条件必需的语义是「没有就跑不了」，与该降级行为自相矛盾；除这四个委派式维度外的其余维度确实不需要它（⛔ 此处刻意不写「其余 N 个」——维度一增删这个数就腐化）。这一格是**对调用方契约的要求**（每次都该传），不是本 SKILL 的启动前置。⚠️ **它常常不等于上一行**——AIDP 项目里源码在 `code/backend/<子项目>/`，而脚手架下发到仓库根，**只传源码目录会让这四个维度全部落「不适用」**。而那里面含**零豁免的 Critical**（约定39-R10 导出只导当前页、约定40 的 C1/C2），失效方向是**全绿**。调用方未传时**不得自行推断**，按「不适用（未取到被测项目根）」标注留行并在报告里点名要它 |
| **验收版本号** | 维度 13 **必需** | 形如 `V0.14.0`，`check_design_anchor.py --version <值>` 的实参，**由调用方脚手架契约传入**。⚠️ 维度 10 / 12 都不需要这个参数，**只有 13 需要**——照那两个的经验漏传会被 argparse 判用法错、落 `exit 2`，而 `exit 2` 按约定是「入参错、修正后重跑」，于是该维度既不算过也不算不过。⛔ 不得自拟或猜一个版本号把脚本跑绿 |
| 任务描述 | **必需** | 本次开发/修复的目标（PRD 功规点、Bug 描述、迭代任务） |
| 详细设计文档 | 推荐 | 含接口定义、数据库设计（来自 dev-logic-architect） |
| 接口文档 | 推荐 | Swagger/OpenAPI/Apifox 导出文件、接口 Markdown |
| 研发执行计划 | 推荐 | 来自 dev-execution-planner 的任务清单 |
| **产品原始 PRD 原文** | 可选（**有则强制消费**） | **产品端交付的原始需求文档全文**，路径 `docs/requirements/{version}/产品提供/*.md`（或用户指定路径）。与「任务描述内的 PRD 功规点」「ux-logic-extractor 加工后的研发需求文档」均**不同层**——它是尚未经 AIDP 任何加工的产品原文。提供后，维度 1 与维度 4 以之为**独立基准**做条目级/字段级回检，专防「ux 提取阶段就把 PRD 条目漏掉」的同源污染（见维度 1「产品 PRD 原文条目级存在性回检」、维度 4「产品 PRD 原文 ⟷ 实现 条目对账」档） |
| 原型内容基线 | 可选 | AIDP 逐页「可见元素 + 操作逻辑/交互流 → 处置」产物，路径 `docs/design/detail/{version}/NN_原型内容基线.md`（兼容历史裸名 `docs/design/{version}/原型内容基线.md`）。已被维度 4「内容 + 操作逻辑完整性」正文按路径消费、此处补登为独立输入行以与实际消费一致；无则回退直接读原型 `code/` |
| 设计令牌 | 可选 | AIDP 视觉基准产物，路径 `docs/design/detail/{version}/NN_设计令牌.md`（兼容历史裸名 `docs/design/{version}/设计令牌.md`）。已被维度 4「视觉还原度」正文消费、此处补登；无则回退直接从原型 `code/` 提取 token |
| 字段处置对照表 | 可选 | ux-logic-extractor 研发需求文档的「需求字段 → 处置」对照表（处置 ∈ 保留/裁剪/前端计算还原/请第三方补）。已被维度 4「字段/列对账」正文消费为对账单一信源、此处补登 |
| **语义变更影响清单（表 E）** | 可选（**有则强制消费**） | ux-logic-extractor 产出的「表 E：语义变更 → 派生展示物影响清单」（列 `变更项｜变更前语义｜变更后语义｜受影响展示物｜处置｜新文案`）。本版改了口径/语义的展示位登记在此。维度 4「文案与数据口径一致性」子行以表 E 中**处置=改写**行的「变更前语义」为旧口径字样清单，grep 代码里改了口径的说明文案是否仍残留旧表述 |
| **历史需求作废清单（表 F）** | 可选（**有则强制消费**） | ux-logic-extractor 产出的「表 F：历史需求作废清单」（列 `历史版本｜需求编号｜原结论｜本版处置｜理由`，「本版处置」取值 ∈ {沿用/作废/修订}）。维度 4「文案与数据口径一致性」子行以表 F 中**本版处置=作废**行的「需求编号」为作废 REQ 清单，扫码注释引用这些编号处是否已标注「该需求已于 {version} 作废」 |
| **上游调用日志与脱敏声明表** | 可选（**有则强制消费**） | `dev-logic-architect` 检查项 35 产出的 6 列表（`上游中文名｜完整 URL｜请求段必打字段｜响应段必打字段｜脱敏字段清单｜二进制/大对象降级说明`）。**维度 12 的 12.1 以其第 5 列「脱敏字段清单」为基准、12.2 以第 6 列「二进制/大对象降级说明」为基准**逐行核对；无该表时回退纯代码判断，并把「设计缺声明表」报为 🟡 Important、**不静默放过** |
| **统计指标口径表** | 可选（**有则强制消费**） | `dev-logic-architect` 详细设计产出的 8 列表（`指标/字段｜展示位(全部)｜单位｜小数精度｜时间窗｜统计范围｜取数粒度｜权威取数口径`）。**维度 11 / 约定39-R12「同一指标跨页面必须同源」以其第 8 列「权威取数口径」为基准**，逐指标核对实现取数点是否等于表里声明的权威口径；无该表时回退纯 grep 结构判断，并把「设计缺口径表」报为 🟡 Important、**不静默放过** |
| **文案落点表** | 可选 | dev-logic-architect 产出的「文案落点表」（说明性文案 → 代码落点）。提供后维度 4「文案与数据口径一致性」子行据其定位改了口径的展示位说明文案的具体落点，缩小旧口径残留的核对范围 |
| `client_mcp` | 可选（默认关闭） | 调用方显式声明的**应用业务工具**能力,含客户端类型/实现形态/来源/工具清单;为 false 或未传且旧 Web 未启用 → 维度 9 不留行。Chrome/Appium 的**测试驱动** MCP 不构成启用证据;本 SKILL 不自行探测 |
| `webmcp_enabled` / `webmcp.enabled` | Web 旧入参（缺省 false） | 任一为 `true` 只兼容归一为 Web+WebMCP;两旧别名或与 `client_mcp` 的客户端/启停/形态冲突须明确报错,不得静默覆盖 |
| `webmcp_entry_symbols` | **仅** Web+WebMCP 时必需 | 该项目**实测**的能力入口标识符（数组），供维度 9 定位扫描点。⚠️ **挂载位置已迁移过一次、规范仍在演进，不得写死进脚本或文档**；缺该入参时硬门脚本**报入参错（exit 2）而不是猜默认值**——猜错的方向是「扫不到 → 0 命中 → 假绿」 |
| **`mode`** | 可选（缺省 = `loop`） | **运行模式开关**，取值 `loop` / `verify-only`，由调用方传入。`loop` = 独立调用时的完整循环（Step 1 开发 → Step 3 验收 → Step 5 修复，最多 5 轮）；`verify-only` = **仅验收**，见下方「运行模式」。⛔ 本 SKILL 不自行推断模式——调用方未传即按 `loop`；**非缺省值只由编排层传入，独立调用不自行切换**；**取值不在这两者之内（含大小写变体、空串）一律报错停止**：`mode 取值非法：<值>（只允许 loop / verify-only）`，⛔ 不回落 `loop`、不猜 |

> 详细设计文档和接口文档**至少提供一个**，否则跳过接口对接检查，仅执行功能完整性和代码质量检查。
>
> **产品原始 PRD 原文为可选输入，但一旦提供即强制消费**：维度 1 与维度 4 均须以之为独立基准做上溯回检，**绕过 AIDP 下游加工产物（详细设计、ux 研发需求文档）直连产品端原文**，专防同源污染。

### 运行模式（`mode`）

| 模式 | 适用 | 执行的步骤 | 修复职责 |
| :- | :- | :- | :- |
| `loop`（缺省） | **独立调用**：用户直接要求「开发 + 验收 + 迭代修复」 | Step 0 → 1 → 2 → 3 → 4 →（不通过）5 → 3 … | 本 SKILL 内 Agent1 修复，最多 5 轮 |
| `verify-only` | **编排调用**：代码已由上游开发命令完成，修复另有归口（如 AIDP 的 `/sprint-test` → 问题交 `/sprint-bugfix`） | Step 0 → 3 → 4，**跳过 Step 1 / Step 2 / Step 5** | **本 SKILL 不修复、不创建或唤醒 Agent1、不改任何源码**；只交付验收结论 + 结构化问题清单 |

- **未知 `mode` 值**：取值不是 `loop` / `verify-only` → 立即报错停止（`mode 取值非法：<值>`），⛔ 不回落缺省值、不按「最像的那个」执行。

`verify-only` 的输出契约（供调用方转写 bug 记录）：
- 结论：`通过` / `不通过`。**判据：问题清单里无 Critical 且无 Important 才判 `通过`**（与 `loop` 的循环终止条件同口径；Suggestion 不影响结论）。维度 0 未过即 `不通过`，**但 verify-only 下仍跑完其余维度**（单轮交付完整清单，不像 `loop` 那样短路回 Agent1）；
- 各维度 `Pass` / `Fail` / `不适用` / `未执行（原因）` 汇总表：`不适用` = 门控跳过（写原因，不影响结论；留行口径同 Step 4——门控跳过的维度仍留行，入参门控的维度 9 未启用不留行）；`未执行（原因）` = 本应执行却确实执行不了（工具链报错、基线无效等，基线无效一律写「基线无效，本项未核验」）——**不计 Fail、但绝不计入通过**：每个此类行同时在问题清单列一条 `严重度=Important`、`问题=本项未核验`、`证据`=原因的条目，因而结论必为 `不通过`；
- **基线一律取改动前**：维度 0 类型检查的存量基线（及维度 4 / 7 / 8 / 14 的一切基线对照）取调用方给出的**改动前基线 ref**（未给时取 `git merge-base HEAD <主干分支>`）；⛔ 不得以本轮自身的错误数作基线——verify-only 时代码已改完，「首轮即基线」会把本次引入的错误吞成存量。取不到改动前基线 → 该项「基线无效，本项未核验」；
- 问题清单：每条含 **`严重度`（Critical / Important / Suggestion）· `维度编号` · 位置（`文件:行`）· `问题` · `证据` · `修复建议`**，按严重度排序（Critical → Important → Suggestion）；
- 不输出「请 Agent1 修复」类指令，跳过 Step 1/2，**不进入修复循环**，单轮即结束。
- 其余规则（全程静态、维度判据、门控与留行口径、默认不落盘）与 `loop` 完全一致。

---

## 运行路径约定（`{{AIDP_HOME}}`）

> **运行路径约定 `{{AIDP_HOME}}`**:本 SKILL 随 AIDP 安装时,安装方把 `{{AIDP_HOME}}` **渲染**为实际运行根——
> 仅 Claude Code 时为 `.claude`,共享运行根(Codex / DSH,含与 Claude 并存)时为 `.agents`;路径一律相对被测项目根。
> SKILL 自身**不探测**运行根,看到 `{{AIDP_HOME}}/scripts/x.py` 就是安装后的 `<被测项目根>/<运行根>/scripts/x.py`;
> 正文命令一律以**被测项目根为工作目录**执行,⛔ 不另拼 `<被测项目根>/` 前缀、也不去猜其它目录名。
>
> | 工具链 | 运行根 | <!-- runtime-path-ignore: 对照表须逐字写出两个运行根 -->
> | :- | :- |
> | 仅 Claude Code | `.claude/` |
> | Codex / DSH(含与 Claude 并存) | `.agents/` |

---

## ⚠️ 技术栈细则按需加载（重要）

本文件只写**跨技术栈通用**的判据（维度划分、severity 定义、三方冲突裁决、字段对账口径、闭环规则）；**语言/框架专有的审计细则拆在 `references/stack-*.md`**。

**验收 Agent 必须先探测被测项目实际技术栈，只加载命中的那 1~2 份**，不要全量读——避免把 Java、Vue、React、Node、Go、Python 的规则一次性全灌进上下文。

| 探测信号（任一命中） | 加载 |
| :- | :- |
| `*.java` + `pom.xml` / `build.gradle` | `references/stack-java-spring.md` |
| `*.vue`，或 `package.json` 依赖含 `vue` | `references/stack-vue.md` |
| `*.jsx` / `*.tsx`，或 `package.json` 依赖含 `react` | `references/stack-react.md` |
| `package.json` 依赖含 `express` / `koa` / `@nestjs/core` | `references/stack-nodejs.md` |
| `go.mod` | `references/stack-go.md` |
| `requirements.txt` / `pyproject.toml` + `*.py` | `references/stack-python.md` |

- 前后端分离项目通常**同时命中 1 个后端栈 + 1 个前端栈**，两份都加载。
- **都未命中** → 只按本文件的通用判据验收，技术栈门控型维度（维度 6 / 维度 7 / 维度 8）整维度跳过。
- 探测命令与各文件覆盖范围详见 `references/stack-index.md`。

> ⚠️ **维度 9 由调用方显式的应用业务能力声明门控,不由技术栈或测试驱动门控。** `client_mcp.enabled`/旧 Web `webmcp_enabled` 均未启用时整维度不留行;非 Web 声明已实现时语义静态核对照跑,但不跑 Web 入口脚本。⛔ 不 grep PRD/代码/驱动配置推断启用。

---

## 执行流程

```dot
digraph verification_loop {
    rankdir=TB;
    node [shape=box, style=rounded];

    start [label="用户触发验收", shape=ellipse];
    detect [label="Step 0: 检测接口文档"];
    create_a1 [label="Step 1: 创建/唤醒 Agent1\n执行开发任务"];
    wait_a1 [label="Step 2: 等待 Agent1 完成"];
    check [label="Step 3: Agent2 执行 维度 0 + 15 维度检查\n(本 Skill 的核心)"];
    decide [shape=diamond, label="全部通过?"];
    report_pass [label="Step 4a: 生成验收报告\n+ 优化建议 + 风险识别"];
    report_fail [label="Step 4b: 生成问题清单"];
    feedback [label="Step 5: 反馈给 Agent1"];
    fix [label="Agent1 修复问题"];
    done [label="验收完成", shape=ellipse];

    start -> detect;
    detect -> create_a1 [label="mode=loop"];
    detect -> check [label="mode=verify-only\n(跳过 Step 1/2)"];
    create_a1 -> wait_a1;
    wait_a1 -> check;
    check -> decide;
    decide -> report_pass [label="是"];
    decide -> report_fail [label="否"];
    report_fail -> done [label="mode=verify-only\n(单轮结束，问题清单交调用方)"];
    report_fail -> feedback [label="mode=loop"];
    feedback -> fix;
    fix -> check [label="重新验收"];
    report_pass -> done;
}
```

### Step 0: 接口文档检测（自动执行）

扫描用户提供的输入,判断是否存在后端接口定义:

| 检测目标 | 判定依据 |
|---------|---------|
| 详细设计文档中的接口定义 | 包含 API 契约、Controller 定义、接口列表、Method + Path |
| 独立接口文档 | Swagger/OpenAPI JSON/YAML、Apifox 导出、接口 Markdown |
| 项目中的接口定义 | `swagger.json`、`openapi.yaml`、后端 Controller 源码 |
| 第三方平台接口对接 | PRD/详细设计 Module E 登记"等待第三方接口交付"或代码中出现 `THIRD_PARTY_MOCK` 标注 |

**检测结果决定后续检查范围:**
- **存在接口定义** → 启用全部 15 维度检查(含维度 2A Mock 清除 + 维度 3 接口对接)
- **存在第三方平台接口对接** → 额外启用维度 2B 第三方临时 mock 协议核验，**且维度 2A 的 `scan_mock_data.py` 必须加 `--third-party-mode`**（否则合规的 2B mock 会被 2A 误判为 Critical）
- **不存在接口定义** → 仅执行维度 1(功能完整性)+ 维度 4(代码质量)+ 维度 5(技术债)+ 维度 6(DI 依赖可解析性)+ 维度 7(CSS 预处理器一致性)+ 维度 8(请求通道 URL 拼装)。**维度 9 由显式 `client_mcp`/旧 Web `webmcp_enabled` 独立门控,与本行不互斥**——即便本次没有自研接口定义,已声明应用业务工具仍须核实现有服务/桥接或 Web 页内实现(与下句维度 2B 同款)。**维度 2B 是否启用由上一行独立判定，与本行不互斥**——没有自研接口定义但对接了第三方平台时，2B 照常要跑。**维度 10 / 维度 11 / 维度 12 / 维度 13 与接口定义存在与否无关，与本行同样不互斥**——维度 10 由**被测项目是否下发 `check_ui_fidelity.py`** 独立门控、维度 12 由**是否下发 `check_upstream_call_log.py` + 是否 JVM 栈**双重门控、维度 13 由**是否下发 `check_design_anchor.py` + 调用方是否传了 `--version` 值**双重门控（三者未下发时均标「不适用」跳过但**报告仍留行**），维度 11 是纯静态语义核对（失效实体入口拦截 / 被删引用降级 / 加载态脏数据 / 编辑后视图同步 / 存量数据兼容 / 指标跨页面同源，六条都与有没有接口文档无关），**四者照常执行**
- **技术栈门控(维度 6 / 维度 7 / 维度 8)** → 三者各自独立门控:维度 6 仅对 Java/Spring 生效(扫不到后端 `.java` 即**整维度跳过**)、维度 7 仅对 Vue 生效(扫不到 `.vue` 即**整维度跳过**)、维度 8 对**任意前端**生效(扫不到**任何前端源码**即**整维度跳过**;扩展名完整清单以维度 8「扫描范围」行为准,别照记忆写半截);跳过均不计入通过/不通过,不影响其它技术栈的验收结论
- **外部脚本门控(维度 10 / 维度 12 / 维度 13)** → 被测项目未随脚手架下发 `{{AIDP_HOME}}/scripts/check_ui_fidelity.py`(维度 10)/ `check_upstream_call_log.py`(维度 12)/ `check_design_anchor.py`(维度 13) 时标「不适用(未下发)」跳过、**不硬失败,但报告里仍留行**(⚠️ 与维度 9 的「连行都不留」刻意不同——留行才能让阅读者知道「这一档没跑过」);**退出码 2 是入参/环境错、不是维度违规**。维度 12 另叠一层**技术栈门控**:脚本只扫 `.java`/`.kt`,非 JVM 项目 `outbound_files: 0` → 同样标「不适用」跳过、仍留行;维度 13 另叠一层**入参门控**:调用方未传「验收版本号」时同样标「不适用(未取到 `--version` 值)」跳过、仍留行,⛔ 不得自拟版本号。⚠️ **这三个维度都以「被测项目根」为脚本查找基准,不是「代码仓库/目录」**——AIDP 项目里两者常不是同一个目录,传错即三档一起静默落 N/A(见「输入要求」表)

---

### Step 1: 创建/唤醒 Agent1 执行团队

> `mode=verify-only` 时跳过 Step 1 与 Step 2，直接进入 Step 3。

根据用户提供的任务描述，创建 Agent1 团队执行开发任务：

- 如果用户已有执行计划（来自 dev-execution-planner），直接按计划执行
- 如果用户描述的是 Bug 修复，Agent1 定位并修复问题
- 如果用户描述的是功能开发，Agent1 按需求实现功能
- Agent1 完成后，向主流程报告完成状态

### Step 2: 等待 Agent1 完成

等待 Agent1 报告任务完成。收到完成信号后，进入 Step 3。

### Step 3: Agent2 执行 维度 0（前置）+ 15 维度检查

> 两种 `mode` 的检查内容完全相同；`mode=verify-only` 只执行本步一轮，维度 0 未过时**仍跑完其余维度**再进入 Step 4 出「不通过」。

> 📂 **本节只留每个维度的强制结论**（判据要点、Critical/Important 档、门控方式、机器门命令一行）；
> Why、判据全文、正反例、实测故事、维护者注记、完整命令块按维度组外置在 `references/flow-dims-*.md`，
> **执行到哪个维度就 Read 对应分片**（见文末「分片索引」）。⚠️ **外置的是「怎么做」，不是「强制度」**——
> 下面每条结论照样是硬要求，分片里的判据全文同样必须照做。

#### 维度 0: 静态基线门（**前置，不计入 15 维度**）

- **必须做、且前置**：TypeScript/Vue 跑 `npx --no-install vue-tsc --noEmit`（或 `tsc --noEmit`）、有 eslint 配置跑 `npx --no-install eslint <本次改动文件>`；类型检查非零退出 / eslint **error** = 🔴 Critical，warning 记录不阻断。**`mode=loop` 非零即直接回 Agent1 修复，不往下走 15 维度；`mode=verify-only` 记 Critical 后仍跑完其余维度。**
- ⚠️ `npx` **必须带 `--no-install`**（裸 `npx` 会联网装包，违反最高约束）；工具缺失标「⏭️ 跳过（工具缺失：<原因>）」，⛔ 不得升级为全量 build、不得改用裸 `npx`。
- ⚠️ **Java 侧刻意不做**，⛔ 别"顺手补上" `mvn compile`（lifecycle 会触发 `frontend-maven-plugin` 等插件、联网、落产物）；Java 装配类问题归维度 6。
- **存量不卡本轮**：eslint 只跑改动文件；`tsc --noEmit` 的存量错误数**一律取改动前代码**作基线（`loop` 在 Agent1 动手前取；`verify-only` 按改动前基线 ref 取），只对增量判 Critical；取不到改动前基线写「基线无效，本项未核验」，⛔ 不得退回「以本轮错误数作基线」。
- 判据全文 → [`references/flow-dims-core.md`](./references/flow-dims-core.md)「维度 0」。

---

这是本 Skill 的核心。按以下 15 个维度逐项检查（维度 2 拆 2A/2B 两档；维度 6、7、8 为**技术栈**门控——维度 6 扫不到 Java/Spring 源码、维度 7 扫不到 `.vue`、维度 8 扫不到任何前端源码，即各自整维度跳过；**维度 9 为入参门控**——`client_mcp.enabled` 与旧 Web `webmcp_enabled` 都非 true 才整维度跳过且**连行都不留**;Web 机器叶子只在 Web+WebMCP 时跑,见该维度门控表；**维度 10 / 维度 12 / 维度 13 / 维度 15 为外部脚本门控**——被测项目未随脚手架下发 `check_ui_fidelity.py`（维度 10）/ `check_upstream_call_log.py`（维度 12）/ `check_design_anchor.py`（维度 13）/ `check_sibling_family.py`（维度 15）时标「不适用」跳过、**报告里仍留行**，不硬失败；⚠️ **维度 15 的脚本缺失只关掉它的机器半场，15.1~15.3 的语义核对照跑**；维度 12 另受技术栈门控，非 JVM 栈同样标「不适用」；维度 13 的脚本另需必填 `--version <版本号>`，见该维度；**维度 14 为技术栈 + 改动面双重门控**——本次没动样式、或扫不到前端样式源码、或预处理器未安装，即标「不适用」跳过、**报告仍留行**）：

> **先过维度 0 静态基线门**（上方，不计入 15 维度计数）。

**⚠️ 基线对照的有效性判定（跨维度通用铁律，维度 4 / 7 / 8 / 14 一体适用）：** 凡「改动前 vs 改动后」的基线对照（`--baseline-root` / `git show HEAD:<file>` / `git stash` / lint 同文件集基线），**比较之前必须先判定基线那一次真的跑起来了**。基线结果为空、输出行数与预期量级不符、出现「路径不存在 / command not found / 未执行 / Traceback」类信号 → ⛔ **拒绝比较、按 `exit 2` 返回、绝不给出差值**，报告写「**基线无效，本项未核验**」，**不是**「通过」。判定表与 `check_css_equivalence.py` 内建的「两条半」→ [`references/flow-dims-core.md`](./references/flow-dims-core.md)「基线对照的有效性判定」。

#### 维度 1: 功能完整性检查

- 对照任务描述/PRD 功规点、研发执行计划验收标准逐项核验；Bug 场景按原始路径复核；查边界条件（空数据/超长/并发/权限）。
- **三方文档一致性**按核心原则 6 裁决：文案/规则/枚举/流程以 PRD 为准（⛔ 不以「与原型一致」作通过理由）、接口/表结构/技术栈以详细设计为准；PRD 要求未实现 = 🔴 Critical；原型有 PRD 无 = 🟡 Important「原型补充功能，待确认」。
- **产品 PRD 原文条目级存在性回检（🔴 Critical，有产品 PRD 原文输入时强制）**：绕过详细设计与 ux 研发需求文档，直连产品原文逐条回检按钮/列/操作/规则是否存在，逐条标注产品 PRD 条目号；原文有、实现无 = Critical 漏项。
- 检查方法与输出格式 → [`references/flow-dims-core.md`](./references/flow-dims-core.md)「维度 1」。

#### 维度 2A: Mock 数据清除检查(普通 mock 零容忍)

- **适用**：存在接口定义时必检。硬编码假数据数组 / mock 目录 / API 层返回假数据 / Mock.js·MSW·json-server 配置 / 组件内模拟接口返回的静态对象（人工核验）/ **mock 兜底逻辑** = 🔴 Critical；`TODO: 替换为真实接口` 类注释 = 🟡 Important。
- 机器门：`python3 <SKILL_DIR>/scripts/scan_mock_data.py src/ --json`；⚠️ **项目有第三方对接或前端用了 `DEV_MOCK` 时必须加 `--third-party-mode`**（否则合规的 2B mock 被判 2A Critical）；只有字段完整的 `DEV_MOCK` 块才买得到豁免。
- 2A 与 2B 两个脚本**都要跑**、互为兜底，不是二选一。
- 检查清单、全部命令与备用 grep → [`references/flow-dims-core.md`](./references/flow-dims-core.md)「维度 2A」。

#### 维度 2B: 第三方临时 Mock 协议核验 + 全生命周期状态检查

- **适用**：对接第三方平台接口（本项目以外的外部系统）；没有任何标记的 mock 不归 2B，归 2A。
- **按标记分流、⛔ 不混用**：`THIRD_PARTY_MOCK`（第三方未交付）**必须运行时开关**，构建期守卫 = 🔴 Critical，必填 vendor/api/since/expected_ready/owner/REMOVE_WHEN；`DEV_MOCK`（同项目后端未部署）**应当构建期裁掉**，必填 since/owner/REMOVE_WHEN，用了运行时开关反而提示 🟡 Important。
- 🔴 Critical：标注字段缺失 / 构建期守卫（反模式 1）/ 真实 vendor SDK·base URL·凭证已出现而 mock 仍在（反模式 2，含开关、fixture、拦截分支残留）/ mock 被用作兜底 / `expected_ready` 过期超 14 天；🟡 Important：合规待 follow-up、前端可拦截却用后端 mock。
- 机器门：`python3 <SKILL_DIR>/scripts/scan_third_party_mock_antipatterns.py <代码目录> --json`（后端凭证脚本不覆盖，须人工 grep）；标注协议见 `references/third-party-mock-protocol.md`。
- 标注块示例、检查清单 2B.1~2B.8、对接信号、各栈反模式加载表 → [`references/flow-dims-core.md`](./references/flow-dims-core.md)「维度 2B」。

#### 维度 3: 真实接口对接检查（存在接口定义时必检）

- 逐接口比对 7 项（项 ≠ 维度）：3.1 URL（**含后端 context-path**）/ 3.2 方法 / 3.3 参数 / 3.4 返回字段 = 🔴 Critical；3.5 状态码 / 3.6 错误处理 = 🟡 Important，但 **3.6 第三方业务错误被吞/替换成通用文案 = 🔴 Critical**（系统/基础设施错误走通用兜底合规）。
- **3.7 出参字段变更消费点穷举（条件触发·🔴 Critical）**：出参结构变更时列出全部消费点逐点核对，**重点查绕过封装按 `dataIndex`/下标回原数组的旁路**（ECharts `formatter`、`rawList[i]`）。3.6 / 3.7 为语义判定、脚本不覆盖。
- 各栈 context-path 位置见对应 `stack-*.md`「维度 3」节；检查步骤、业务错误 vs 系统错误口径、输出格式、常见问题模式 → [`references/flow-dims-core.md`](./references/flow-dims-core.md)「维度 3」。

#### 维度 4: 代码质量检查

- **视觉还原两支柱（字段一致性 ⊕ 样式一致性）+ 对齐原型三层（视觉 + 内容 + 操作逻辑）**；视觉基准（高保真 mockup 或原型 `code/` + 设计令牌）同等强校验，⛔ 不因只有原型而放松；唯一合规偏离是**叶子组件替换白名单**（只放行"换载体"、不放行"改结果"，主题 token / 布局度量仍须取自原型体系）。
- ⚠️ 视觉与交互类回检**一律纯静态**（读样式 token / DOM 结构 / 原型源码对读），⛔ 不得写成或做成「跑起来截图比对」；静态判不了的标注转 `/sprint-aiauto-test`。
- 各检查行档位（全文与判据见分片）：

| 档位 | 检查行 |
| :- | :- |
| 🔴 Critical | 安全隐患 / 金额字段类型守恒 / 缓存代码与设计一致性（设计未授权严禁加缓存）/ 字段/列对账（未登记差异）/ 字段集与设计双向比对（设计有实现无）/ 产品 PRD 原文 ⟷ 实现 条目对账 / 视觉还原度 L1 / 内容 + 操作逻辑完整性 / 文案与数据口径一致性 / 死代码/死引用残留 / HTTP 客户端配置硬编码 / 审计字段填充溯源 / 用户自我保护校验 / **错误契约与失败可见性**（①成功响应表达失败 ②前端吞错渲染空态 ③fail-open；只判「失败分支内」，合法业务空集合不在覆盖面） |
| 🟡 Important（可按条件升 Critical） | 命名规范 / 错误处理（本地异常提示）/ 类型安全 / 性能问题 / 金额 JSON 序列化 / 注释完备性（A 档裸代码升 Critical）/ 文件复杂度 + 复用封装（单文件软阈值 Java·Go ≤500、Vue·React 组件 ≤300、TS/JS ≤400、Python ≤600，超 2 倍或单方法 >50 行或 3+ 次裸重复未抽升 Critical）/ DB 约束前置校验（NOT NULL·UNIQUE·外键缺校验升 Critical）/ 配置中心热刷新漏标 / 新增依赖越界基线（未评估第三方依赖升 Critical）/ 错误契约第④类（上游改字段静默取默认值）/ 视觉还原度 L2 / 四条「UI 公共化」子行（重复样式声明块 / 公共单元被就地覆盖 / 「抄自」类注释 / `SYNC-WITH:` 标记进技术债） |

- 机器门：`check_file_complexity.py <代码目录>`（**硬门**，超 2 倍阈值/单方法 >50 行 exit 1）；`scan_cache_usage.py` / `scan_code_conventions.py`（`http-hardcode`/`refresh-scope`/`dead-ref`/`dep-baseline`/`audit-fill`）/ `scan_field_columns.py` / `scan_design_field_inventory.py` / `scan_stale_copy.py` 为**采集脚本、退出码恒 0**，结论由验收 Agent 比对设计/基线给出。「错误契约与失败可见性」**刻意不配脚本**。
- 白名单判定要点、逐行判据全文、脚本参数、UI 公共化来由、与维度 3.6/5 的职责边界 → [`references/flow-dims-quality.md`](./references/flow-dims-quality.md)「维度 4」。

#### 维度 5: 技术债与风险识别

- 输出 TODO/FIXME/HACK、硬编码配置、过时依赖、架构耦合、性能瓶颈清单 + 处理建议；非阻断。⚠️ 对外 HTTP 端点/凭证硬编码归维度 4（Critical），不降级到本维度。表格 → [`references/flow-dims-quality.md`](./references/flow-dims-quality.md)「维度 5」。

#### 维度 6: DI 依赖可解析性（技术栈门控·Java/Spring）

- **门控**：扫不到 `.java` 即整维度跳过（不计入通过/不通过）。纯 grep 级静态分析，⛔ 不编译不打包不起容器。
- **判定**：注入类型 T 三源命中任一即可解析（项目内组件注册 / 显式 `@Bean` / 框架自动装配白名单）。**精度优先、零误阻断**：Critical 只给近乎确定不可解析的少数几类，多候选无消歧 / 接口无实现 / 全仓无来源一律 Warn。命中时**必须给出本项目同类型现有用法**（grep `new T(`）。
- 机器门：`python3 <SKILL_DIR>/scripts/check_di_resolvability.py <代码目录> --json`（细则见 `references/stack-java-spring.md` §一）。
- 口径表、各栈落地状态、边界 → [`references/flow-dims-static-gates.md`](./references/flow-dims-static-gates.md)「维度 6」。

#### 维度 7: CSS 预处理器一致性（技术栈门控·Vue）

- **门控**：扫不到 `.vue` 即整维度跳过。逐个 `<style lang="X">` 查所需包是否在**就近向上一路合并到 git 根**的 `package.json` 已声明：未声明 = 🔴 Critical（CI 构建必失败）；与全库众数 lang 不一致的孤例 = 🟡 Warn。`@import`/`@use` 路径不在覆盖内。
- 机器门：`python3 <SKILL_DIR>/scripts/check_vue_style_preprocessor.py <改动的 .vue 列表> --json`，**判过没过读 `gate_passed`**；退出码 0/1/2。
- JSON 字段清单与语义（**本维度脚本接口事实的单一信源**）、覆盖边界、边界 → [`references/flow-dims-static-gates.md`](./references/flow-dims-static-gates.md)「维度 7」。

#### 维度 8: 请求通道 URL 拼装单一信源（技术栈门控·前端）

- **门控**：扫不到任何前端源码即整维度跳过；**不限 Vue**（React / 原生 TS / Node 服务端同样适用）。**扫描范围**：前端源码 `.ts/.js/.mjs/.cjs/.mts/.cts/.tsx/.jsx/.vue`（`.vue` 只看 `<script>` 块），默认排除 `node_modules`/`dist`、`*.min.js`/`*.d.ts`、`*.config.ts|js`。
- **判定**：不判拼得对不对，只判**这条判据有几份实现**——计入的自拼点（base 拼装形态 **且** 所在文件有请求发起点）散落 **≥2 个文件 = 🔴 Critical**，1 个文件放行并报为单一信源；`--changed` 下存量降 Warn，`--allow` 下信源之外一处都不许有。
- 机器门：`python3 <SKILL_DIR>/scripts/check_request_channel_url.py <前端目录> --changed <本次改动文件...> --json`，判过没过读 `gate_passed`；`--changed` 路径全不存在 → exit 2（安全失败）。
- 判定口径全表、JSON 字段（**本维度脚本接口事实的单一信源**）、覆盖边界、与维度 3/4/5 的边界 → [`references/flow-dims-static-gates.md`](./references/flow-dims-static-gates.md)「维度 8」。

#### 维度 9: 客户端应用 MCP 业务能力实现合规（**条件启用**·WebMCP 为 Web 专项）

- **入参门控**：仅调用方显式 `client_mcp.enabled: true` 或旧 Web `webmcp_enabled: true`（`client_mcp` 默认关闭；旧别名 `webmcp.enabled` 同义）时启用；均未启用 → 整维度不告警、**报告不留行**；声明冲突须报错。⛔ **严禁自行探测**——不 grep PRD/代码，也不据 Chrome/Appium **测试驱动** MCP 推断应用已提供业务工具。
- **通用静态半场（已声明端均查）**：必读 [`references/flow-client-mcp.md`](./references/flow-client-mcp.md)；9.4 写操作未绕开业务既有通道 / 9.5 敏感字段不经工具通道外泄（含脱敏片段）/ 9.6 可调用对象白名单 = 🔴 Critical，端无关。
- **Web 专项（仅 Web+WebMCP）**：9.1 单一适配层（入口标识符命中文件数 == 1，注释也算）/ 9.2 无「先登记后撤销」、出现 `unregisterTool` 即 Critical = 🔴；9.3 错误契约无死文案 = 🟡。机器门 `python3 <SKILL_DIR>/scripts/check_webmcp_adapter.py <前端源码目录> --entry-symbols <符号...> --json`（未传 `--entry-symbols` 即 exit 2，⛔ 不猜默认值；判据全文见 [`references/flow-webmcp.md`](./references/flow-webmcp.md)）。**脚本全绿 ≠ 维度 9 通过**。
- 门控表、检查表、命令块、概念前提 → [`references/flow-dims-delegated.md`](./references/flow-dims-delegated.md)「维度 9」。

#### 维度 10: UI 还原度确定性检查（委派外部脚本·约定39-R2/R3/R10）

- **外部脚本门控**：`python3 {{AIDP_HOME}}/scripts/check_ui_fidelity.py --json`；未下发标「不适用」**报告仍留行**；`exit 2` 是入参/环境错、不是维度违规。⛔ **本 SKILL 不得再写一份同判据实现，也不许把脚本拷进来。**
- 约定39-R10 导出方法体内透传分页参数（导出只导当前页）= 🔴 Critical **零豁免**；约定39-R3 截断无 tooltip / 约定39-R2 状态标签颜色字面量常量 = 🟡 Important，可就近 `fidelity-ignore: <规则号> <原因>`，只写规则号不写原因报 Important。编号一律写全称 `约定39-RNN`。
- 详情 → [`references/flow-dims-delegated.md`](./references/flow-dims-delegated.md)「维度 10」+ [`references/flow-ui-fidelity.md`](./references/flow-ui-fidelity.md)。

#### 维度 11: 失效实体与边界（语义核对·约定39-R5~R9 + 约定39-R12）

- 纯静态语义核对、与接口定义存在与否无关，六条均 🔴：约定39-R5 失效实体入口隐藏或禁用（⛔ 不接受「点了才报错」）/ 约定39-R6 被删引用降级可读展示 / 约定39-R7 加载未完成不渲染脏数据 / 约定39-R8 编辑成功后当前视图（含跨组件）自动同步 / 约定39-R9 存量数据兼容 / 约定39-R12 同一指标跨页面同源（取数点散落 ≥2 文件高危）。
- 约定39-R12 以上游「统计指标口径表」第 8 列为基准，无表时回退 grep 并报「设计缺口径表」🟡 Important、不静默放过；本轮无对应场景须标「不适用 + 理由」，⛔ 不得省略。
- 详情 → [`references/flow-dims-delegated.md`](./references/flow-dims-delegated.md)「维度 11」+ [`references/flow-ui-fidelity.md`](./references/flow-ui-fidelity.md)。

#### 维度 12: 上游调用日志可见性与脱敏（委派外部脚本 + 语义半场·约定40）

- **双重门控**：脚本 `python3 {{AIDP_HOME}}/scripts/check_upstream_call_log.py --json` 未下发、或非 JVM 栈（`outbound_files: 0`）→ 标「不适用」**仍留行**；`exit 2` 不是维度违规。⛔ 不得另写一份 C1–I3 实现，⛔ 不复述脚本内部口径（以 `--json` 实际输出为准）。
- **全程静态**：查代码里的日志语句，⛔ 不是把服务跑起来看日志。C1 出站零日志 / C2 成功路径不可见 = 🔴；I1/I2/I3 = 🟡。**「成功路径必须可见」是核心，别弱化成「有日志就行」。**
- 语义半场三条均 🔴：12.1 脱敏覆盖嵌套结构（发生在序列化环节）/ 12.2 二进制只打元信息 / 12.3 拦截器覆盖全部出站客户端（差集逐个点名，抵扣以 `waived` 为准）。上游「上游调用日志与脱敏声明表」有则强制消费，无表报 🟡 Important。
- 详情 → [`references/flow-dims-delegated.md`](./references/flow-dims-delegated.md)「维度 12」。

#### 维度 13: 实现偏离设计（委派外部脚本·设计锚点落点）

- 机器门：`python3 {{AIDP_HOME}}/scripts/check_design_anchor.py --version <版本号> --json`——⚠️ **比维度 10/12 多一个必填带值参数 `--version`**，值由调用方传入，⛔ 不得自拟或省略；取不到 / 脚本未下发 → 标「不适用」仍留行；首次调用前先跑 `--help` 核对参数。
- **判 🟡 Important 不判 Critical**：设计点名的字段/常量/取数锚点须在源码有落点（命名只放宽前边界、不放宽后边界）；每个未落点锚点三选一处置并写明理由（改代码 / 改设计并级联更新 / `design-anchor-ignore: <理由>`，理由必填）。
- 详情 → [`references/flow-dims-delegated.md`](./references/flow-dims-delegated.md)「维度 13」。

#### 维度 14: 样式重构编译等价性对照（技术栈门控·改动了样式时才触发）

- **双重门控**：本次没动样式 / 扫不到样式源码 / 预处理器未安装 → 标「不适用」**仍留行**（跳过由调用方在调脚本前判定，脚本自身无 N/A 分支）。
- **判定**：用**被测项目自己的**编译器（⛔ 不联网装）把改动前后样式段各编译一次，归一后要求**零差异**；仍有差异 = 🔴 Critical，除非逐条被本次改动意图解释并写进报告；仅顺序变化 / 产物注释块增多 = 🟡 Important。基线须先过「基线有效性判定」。
- 机器门：`python3 <SKILL_DIR>/scripts/check_css_equivalence.py /tmp/old.css /tmp/new.css --json`（0 等价 / 1 有差异 / 2 入参或基线无效）。
- 配套判据：公共样式文档注释用 `//`、⛔ 不用 `/* */`；前端最低静态验证组合 = 类型检查（**带阳性对照**）+ lint（同文件集基线）+ 预处理器编译（改样式时），缺一不可。
- 编译命令示例、实证、边界 → [`references/flow-dims-static-gates.md`](./references/flow-dims-static-gates.md)「维度 14」。

#### 维度 15: 同族增量项一致性（委派外部脚本 + 语义半场·被测项目 约定 20）

- **★ 判据是「有没有兄弟」，不是「我写了几遍」**：家族已有同构成员 ≥2 即适用，哪怕本次只新增 1 个。命中本维度时维度 4 的「3 次以下禁止抽」不适用；无家族声明的偶然相似仍按维度 4 判。
- 机器门：`python3 {{AIDP_HOME}}/scripts/check_sibling_family.py --json`（F0 声明漂移 / F1 成员自带外壳 / F2 成员未登记 = 🔴；F3 / F4 = 🟡）；⛔ 不复述、不重写判据（以脚本与被测项目约定 20 为单一信源）。未下发 → 标「不适用」**仍留行**，**只关掉机器半场，语义半场照跑**。
- 语义半场：15.1 结构骨架一致 / 15.2 文案骨架一致 = 🟡；15.3 交互流一致（最高频：其他成员都有二次确认、新成员直接执行）= 🔴。⛔ **只约束外壳与骨架、不约束内容**。上游「同族增量项声明表」有则强制消费，无表报 🟡 Important。
- 详情 → [`references/flow-dims-delegated.md`](./references/flow-dims-delegated.md)「维度 15」。

---

### Step 4: 生成验收结果

根据 维度 0（静态基线门）+ 15 维度检查结果，生成以下之一（**维度 0 未过时结论即「不通过」**；`mode=loop` 可不填后 15 维度，`mode=verify-only` 仍须填完）：

**4a. 验收通过** → 在响应中以表格形式呈现验收结果，包含：
- 各维度检查结果汇总（表格）
- 优化建议（列表，非阻塞性改进项）
- 技术风险识别（列表）
- 技术债清单（列表）

**4b. 验收不通过** → 在响应中以结构化格式呈现问题清单，包含：
- 问题汇总（按严重级别统计）
- 每个问题的详细描述（位置、代码片段、修复建议）
- 修复优先级指引

`mode=verify-only` 时只输出结论 + 各维度汇总表 + 问题清单（按「运行模式」的输出契约），不写「请 Agent1 修复」。

**文档持久化规则：**
- **默认不生成文档**：验收结果仅在响应中呈现，不保存到文件
- **用户明确要求时才生成文档**：当用户说"生成验收报告"、"保存验收结果"、"输出文档"时，才使用 `assets/verification-report.md` 或 `assets/issue-list.md` 模板生成 Markdown 文件并保存到 `docs/verification/` 目录

**输出格式：** ⛔ **本节不内联报告示例**——同一份模板两处维护必然漂移（根因见 [`references/rationale.md`](./references/rationale.md)）。
响应内呈现与落盘一律以 [`assets/verification-report.md`](./assets/verification-report.md)（通过/总报告）
与 [`assets/issue-list.md`](./assets/issue-list.md)（不通过/问题清单）为**单一信源**，要点：

- **章节编号照模板、不顺延**（⚠️ 章节号 ≠ 维度号，对应关系见模板各节标题括号）：`0` 静态基线门 → `1`~`13` 各章 →
  `4b`（维度 13）/ `6b`（维度 14）/ `10b`（维度 15）这类插入编号是刻意的，引用方按编号引用；
  **条件启用的维度 9 排在最后一节**，未启用时整节删除、不留编号空洞。
- **门控维度的留行口径不同**：技术栈 / 外部脚本 / 改动面门控的维度跳过时**仍留行**写「不适用 + 原因」；
  只有入参门控的维度 9 **连行都不留**。
- **维度 0 未过即「不通过」**：`mode=loop` 不必填后续维度；`mode=verify-only` 仍须跑完并填完其余维度。
- **不通过时**每个问题写清：维度号、位置（文件:行）、代码片段、修复建议、严重级别（Critical / Important / Suggestion），
  并按 Critical → Important → Suggestion 给出修复优先级。

### Step 5: 反馈与修复循环

> `mode=verify-only` 时**不执行本步**：Step 4 输出问题清单后即结束，修复由调用方归口处理。

`mode=loop` 验收不通过时：
1. 将问题清单发送给 Agent1
2. Agent1 按优先级修复（先 Critical → 再 Important → 最后 Suggestion）
3. Agent1 修复完成后，返回 Step 3 重新验收
4. **循环终止条件**：所有 Critical 和 Important 问题已修复（Suggestion 可由用户决定是否修复）
5. **最大循环次数**：默认 5 轮。超过 5 轮仍未通过，暂停并向用户报告，由用户决定是否继续

---

## 约束条件

0. **🚫 全程静态、绝不启动被测服务（Critical，最高约束）**：不起前端 dev server、不起后端进程、不起容器/DB/中间件、不跑完整打包构建、不开浏览器截图。允许类型检查（`vue-tsc --noEmit` / `tsc --noEmit`）、lint、grep 与确定性脚本。运行时/浏览器验证归 `/sprint-aiauto-test`（需部署环境就绪），静态查不了的**在报告里标注转交**，不得自行拉起服务。完整说明见文首「角色定义」下的同名章节
1. **零 Mock 容忍**：存在接口定义时，前端代码中不允许任何形式的 mock 数据残留，包括 mock 兜底逻辑
2. **接口一致性**：前端接口调用必须与后端定义 100% 一致（URL、方法、参数、返回、状态码、错误码）
3. **问题分级**：所有问题必须标注 Critical/Important/Suggestion 级别
4. **默认不生成文档**：验收结果在响应中以表格形式呈现，除非用户明确要求"生成报告"、"保存文档"
5. **修复闭环**：Critical 问题必须修复，不允许跳过（`mode=loop` 由本 SKILL 的 Agent1 修复；`mode=verify-only` 由调用方归口修复，本 SKILL 只保证问题清单完整）
6. **最大循环**：`mode=loop` 默认 5 轮，超过后暂停请示用户；`mode=verify-only` 恒为单轮
7. **不改需求**：验收过程中不修改需求或设计，只检查实现是否符合设计
8. **运行模式**：`mode` 缺省 `loop`；**非缺省值只由编排层传入，独立调用不自行切换**

## 输出规范

**默认输出方式：** 在响应中以 Markdown 表格和列表形式呈现验收结果，不生成文件

**文档持久化（可选）：** 仅当用户明确要求时，才生成以下文件：
- 验收报告保存路径：`docs/verification/{功能名称}_验收报告_第{N}轮.md`
- 问题清单保存路径：`docs/verification/{功能名称}_问题清单_第{N}轮.md`

## 与其他 Skill 的协作

```
PRD → dev-logic-architect（详细设计，含接口定义）
    → dev-execution-planner（任务拆解）
    → Agent1 执行开发
    → code-verification-loop（本 Skill：验收检查）
    → 通过 → 交付
    → 不通过 → Agent1 修复 → 再验收
```

## 分片索引

| 文件 | 内容 | 什么时候读 |
| :- | :- | :- |
| [`references/flow-dims-core.md`](./references/flow-dims-core.md) | 维度 0 静态基线门 + 基线有效性判定 + 维度 1 / 2A / 2B / 3 判据全文、命令块、输出格式 | 每轮 Step 3 开始时（维度 0 前置）；执行维度 1~3 时 |
| [`references/flow-dims-quality.md`](./references/flow-dims-quality.md) | 维度 4 代码质量（视觉还原两支柱、叶子组件白名单、全部检查行、回检脚本一览、UI 公共化来由、职责边界）+ 维度 5 | 执行维度 4 / 5 时 |
| [`references/flow-dims-static-gates.md`](./references/flow-dims-static-gates.md) | 技术栈门控维度 6 / 7 / 8 / 14：口径表、硬门命令、JSON 字段（维度 7/8 脚本接口事实的单一信源）、覆盖边界 | 门控命中、执行对应维度时 |
| [`references/flow-dims-delegated.md`](./references/flow-dims-delegated.md) | 维度 9 门控表与检查表、维度 10 / 11 / 12 / 13 / 15 委派脚本命令、语义半场、上游契约与边界 | 维度 9 启用时；执行维度 10~13、15 时 |
| [`references/flow-client-mcp.md`](./references/flow-client-mcp.md) | 维度 9 通用静态半场（应用自有服务/桥接、身份与权限、写确认、审计日志） | 维度 9 启用时 |
| [`references/flow-webmcp.md`](./references/flow-webmcp.md) | 维度 9 Web 专项判据与 `check_webmcp_adapter.py` 字段清单 | 仅 Web+WebMCP 时 |
| [`references/flow-ui-fidelity.md`](./references/flow-ui-fidelity.md) | 维度 10 / 11 判据全文（约定39） | 执行维度 10 / 11 时 |
| [`references/third-party-mock-protocol.md`](./references/third-party-mock-protocol.md) | 第三方临时 mock 标注协议 | 执行维度 2A / 2B 时 |
| `references/stack-index.md` + `references/stack-*.md` | 技术栈探测规则与各栈审计细则 | 探测栈后只加载命中的 1~2 份 |
| [`references/rationale.md`](./references/rationale.md) | 维护者说明：全程静态、不内联报告示例、`mode`、`{{AIDP_HOME}}` 等约定的根因 | 维护本 SKILL 时；执行验收时不必读 |
