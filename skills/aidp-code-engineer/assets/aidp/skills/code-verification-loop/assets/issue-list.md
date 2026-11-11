# 代码验收问题清单

> 验收时间：{日期}
> 验收范围：{功能/模块名称}
> 验收轮次：第 {N} 轮（`mode=verify-only` 恒为单轮）
> 运行模式：{`loop` / `verify-only`}
> 验收结果：❌ 不通过
> 输入文档：{列出使用的 PRD、设计文档、接口文档}

---

## 发现汇总与判定

按 [`../SKILL.md`](../SKILL.md)「严重度与 loop 推进」填写。所有发现按唯一问题编号进入下表（Critical → Important → Suggestion）；详情、优化建议和技术债引用该编号，不重复计数。`loop 推进` 只填阻断/非阻断，非阻断只控制 loop 推进、不触发自动修复，不改变严重度与验收结论。

统计：Critical={C}；Important={I}（阻断={Ib}，非阻断={In}）；Suggestion={S}。
Important 总数 = 阻断 Important + 非阻断 Important；loop 阻断项总数 = Critical + 阻断 Important。

| 编号 | 严重度 | loop 推进 | 维度 | 位置（文件:行） | 问题 | 证据 | 修复建议 |
| :- | :- | :- | :- | :- | :- | :- | :- |
| {问题编号} | {Critical / Important / Suggestion} | {阻断 / 非阻断} | {维度编号} | {文件:行} | {问题} | {命令与结果/源码/设计依据} | {建议} |

| 维度 | 结论 | Critical | Important（阻断） | Important（非阻断） | Suggestion | 问题编号/依据 |
| :- | :- | :- | :- | :- | :- | :- |
| {维度编号} | {Pass / Fail / 不适用 / 未核验（原因）} | {C} | {Ib} | {In} | {S} | {问题编号或核验依据} |

逐维度填完（留行规则同 SKILL）：已执行维度存在 Critical 或 Important（含非阻断）即 Fail，只有 Suggestion 可记 Pass；未执行不计 Pass/Fail，并按 SKILL 登记 Important「本项未核验」。不适用写原因，不能用来隐藏 L2。

**总体结论：不通过。** 无 Critical 且无 Important 才通过（含非阻断 Important）；仅 L2 也不能判通过。
**本轮原因：** {对应问题编号、严重度和数量；未核验项写原因}。
**loop 推进：** {仍有阻断项→修复 / 仅非阻断项→可收尾但验收不通过}；`verify-only` 单轮结束，清单交调用方。

两组完整对账示例见本模板「输出示例」，生成报告时删除示例、替换为真实结果。

---

## 🔴 Critical 问题

### 问题 {N}: {问题标题}

**维度：** {维度编号}

**问题编号与 loop 推进：** {沿用发现汇总编号；Critical=阻断；Important 按判据填阻断/非阻断；Suggestion=非阻断}

**位置：** `{文件路径}:{行号}`

**问题描述：** {详细描述问题}

**证据：** {命中的命令与退出码 / `--json` 字段 / grep 命中行 / 对照的设计条目——能让调用方复核的原始依据}

**代码片段：**
```{语言}
{有问题的代码片段}
```

**后端定义（如适用）：**
```
{后端接口定义或设计文档摘录}
```

**修复建议：** {具体的修复步骤}

**验证方式：** {如何验证修复是否正确}

---

## 🟡 Important 问题

### 问题 {N}: {问题标题}

**维度：** {维度编号}

**问题编号与 loop 推进：** {沿用发现汇总编号；Critical=阻断；Important 按判据填阻断/非阻断；Suggestion=非阻断}

**位置：** `{文件路径}:{行号}`

**问题描述：** {详细描述问题}

**证据：** {命中的命令与退出码 / grep 命中行 / 对照的设计条目}

**修复建议：** {具体的修复步骤}

---

## 🔵 Suggestion

### 建议 {N}: {建议标题}

**维度：** {维度编号}

**问题编号与 loop 推进：** {沿用发现汇总编号；Critical=阻断；Important 按判据填阻断/非阻断；Suggestion=非阻断}

**位置：** `{文件路径}:{行号}`

**证据：** {依据}

**优化建议：** {具体的优化建议}

**预期收益：** {优化后的预期收益}

---

## 修复指引（仅 `mode=loop`；`mode=verify-only` 时整节删除，改用下方「修复优先级」）

请 Agent1 按以下优先级修复问题：

1. **优先修复所有 🔴 Critical 问题**（必须修复，否则验收不通过）
2. **其次修复阻断 Important 问题**；非阻断 Important 留在清单中，不触发自动修复；收尾不等于验收通过
3. **最后考虑 Suggestion**（可选，由用户决定是否修复）

修复完成后，请重新提交验收；若本轮仅剩非阻断 Important，可收尾并交代后续处置，但维度仍 Fail、总体仍不通过。

## 修复优先级（仅 `mode=verify-only`；`mode=loop` 时整节删除）

问题已按 🔴 Critical → 🟡 Important → 🔵 Suggestion 排序。本 SKILL 不修复、不创建 Agent1，修复由调用方归口处理。

---

## 输出示例

以下是输出形态示例，位置与证据均为示意；实际验收须替换为实测结果。两例只展开有发现的维度，其余维度仍须逐行登记，不能由例子推断通过。例子与生产规则的唯一入口在 SKILL「严重度与 loop 推进」。

### 混合发现示例

| 编号 | 严重度 | loop 推进 | 维度 | 位置（文件:行） | 问题 | 证据 | 修复建议 |
| :- | :- | :- | :- | :- | :- | :- | :- |
| C-1 | Critical | 阻断 | 4 | src/theme.scss:12 | 主色未取原型 token，属 L1 | 原型 primary=#315efb，实现=#409eff | 对齐原型主题变量 |
| I-1 | Important | 阻断 | 3 | src/api/order.ts:24 | 状态码处理与接口契约不符 | 设计约定 409，实现只判 400 | 按契约处理状态码 |
| I-2 | Important | 非阻断 | 4 | src/Hint.vue:40 | L2 叶子组件内部动画时长偏差 | token/布局/行为一致，内部动画 160ms 对 180ms | 后续对齐动画时长 |
| S-1 | Suggestion | 非阻断 | 5 | src/format.ts:8 | 常量可提取以改善可读性 | 多个纯展示分支重复字面常量 | 择机提取命名常量 |

统计：Critical=1；Important=2（阻断=1，非阻断=1）；Suggestion=1。

| 维度 | 结论 | Critical | Important（阻断） | Important（非阻断） | Suggestion | 问题编号/依据 |
| :- | :- | :- | :- | :- | :- | :- |
| 3 | Fail | 0 | 1 | 0 | 0 | I-1 |
| 4 | Fail | 1 | 0 | 1 | 0 | C-1、I-2 |
| 5 | Pass | 0 | 0 | 0 | 1 | S-1 |

verify-only 总体结论：不通过；单轮结束，问题交调用方。
loop 总体结论：不通过；阻断项=2（C-1、I-1），非阻断 Important=1（I-2）。
loop 推进：继续修复阻断项。

### 仅 L2 的边界示例

| 编号 | 严重度 | loop 推进 | 维度 | 位置（文件:行） | 问题 | 证据 | 修复建议 |
| :- | :- | :- | :- | :- | :- | :- | :- |
| I-1 | Important | 非阻断 | 4 | src/Hint.vue:40 | L2 叶子组件内部动画时长偏差 | token/布局/行为一致，内部动画 160ms 对 180ms | 后续对齐动画时长 |

统计：Critical=0；Important=1（阻断=0，非阻断=1）；Suggestion=0。

| 维度 | 结论 | Critical | Important（阻断） | Important（非阻断） | Suggestion | 问题编号/依据 |
| :- | :- | :- | :- | :- | :- | :- |
| 4 | Fail | 0 | 0 | 1 | 0 | I-1 |

verify-only 总体结论：不通过；单轮结束，问题交调用方。
loop 推进：可收尾，不触发自动修复；总体结论仍为不通过。
I-1 保留在 Important 清单并交代后续处置；两种模式维度 4 均为 Fail。不得因为“非阻断”把 Important 计成 0、改成 Suggestion、只列优化建议，或把维度/总体标成通过。

## 常见问题参考

### Mock 数据清除

**问题模式：** 组件中硬编码了 `mockData` 数组
**修复方式：** 删除 `mockData`，调用真实 API 函数

**问题模式：** API 层返回假数据 `return Promise.resolve(fakeData)`
**修复方式：** 删除假数据函数，调用真实后端接口

**问题模式：** catch 块中回退到 mock 数据
**修复方式：** 删除 mock 兜底逻辑，统一使用错误提示

### 接口对接不一致

**问题模式：** 字段名大小写不一致（`userName` vs `username`）
**修复方式：** 统一为后端定义的字段名

**问题模式：** 分页结构不一致（后端 `{total, records}` 前端期望 `{total, list}`）
**修复方式：** 前端适配后端返回结构，或在 API 层做字段映射

**问题模式：** 枚举值不一致（后端 `"ACTIVE"` 前端期望 `1`）
**修复方式：** 前端使用后端定义的枚举值，或在 API 层做映射

### 字段/列对账（视觉还原支柱① 字段一致性）

**问题模式：** 实现可见列的展示名(语义)相比需求字段清单(语义)**缺列/多列/改名/换序**，且该差异未在研发需求的「需求字段→处置」对照表登记
**修复方式：** 补齐/对齐到需求字段清单(语义)（保持展示语义名与顺序，对账口径为展示名而非代码级 prop/dataIndex）；若确为有意裁剪/前端计算还原/请第三方补，则回溯到 ux-logic-extractor 在「需求字段→处置」对照表登记处置后再放行（已登记裁剪不阻塞）。对齐 AIDP 约定 4（字段裁剪三件套）/ 约定 22（需求字段(语义)⟷接口字段漂移）

### DI 依赖不可解析（维度 6·Java/Spring）

**问题模式：** `@Autowired`（或 `@RequiredArgsConstructor` + `private final`）注入了**框架不自动装配**的类型——`RestTemplate` / `WebClient` / `OkHttpClient` / `HttpClient` / `RestClient`（Spring Boot 只自动装配它们的 `Builder`，不装配本体），全仓也没有对应 `@Bean`
**修复方式：** 先 grep `new T(` 看**本项目同类型既有用法**——若既有全是构造自建，照此改为 `new RestTemplate()`；若确需注入，在 `@Configuration` 类里补 `@Bean` 声明。**编译期无感，容器启动直接 `APPLICATION FAILED TO START: required a bean of type 'X' that could not be found`**

**问题模式：** 注入的类型在仓内**已定义为具体类**，却没有 `@Service`/`@Component`/`@Repository`/`@Configuration` 等组件注解，也无 `@Bean`/`@ConfigurationProperties`
**修复方式：** 给该类补组件注解，或在配置类里补 `@Bean` 工厂方法；若它本就不该是 bean（纯工具类/值对象），改为直接 `new` 或静态方法调用

**问题模式：** `@Value("${key}")` 无默认值，且 `application*`/`bootstrap*`（yml/properties）与配置项清单文档中均无该键
**修复方式：** 补配置项，或给占位符加默认值 `@Value("${key:默认值}")`。**启动期报 `IllegalArgumentException: Could not resolve placeholder`**

**问题模式（🟡 Warn·不阻断）：** 注入类型有 ≥2 个候选 bean 且未 `@Qualifier`/`@Primary`
**修复方式：** 加 `@Qualifier("beanName")` 或给首选实现加 `@Primary`。**不判 Critical**——Spring 会先按字段名匹配 beanName 兜底，静态无法判死，由验收 Agent 结合上下文确认

### CSS 预处理器未声明（维度 7·Vue）

**问题模式：** 新增 SFC 写了 `<style scoped lang="scss">`，但 `package.json` 只声明了 `less`（全库其余 `.vue` 也都是 `lang="less"`）
**修复方式：** 二选一——把 `lang` 改成全库在用的那种（推荐，除非确有理由引第二种预处理器），或在 `devDependencies` 补 `sass`。**`vue-tsc --noEmit` 与 `eslint` 都不编译 `<style>` 块，开发期轻量验证 100% 全绿，只有 CI `vite build` 才报 `loadSassPackage` 失败** —— 必漏到 CI，且反馈周期是「提交 → 推送 → 构建失败」

**问题模式：** `lang` 拼错（`sccs` / `scc` / `stylus` 写成 `styles`）
**修复方式：** 改正。脚本对不认识的 lang 报 🟡 Warn 提示人工确认，不擅自判死（自定义预处理器是合法的）

**问题模式（🟡 Warn·不阻断）：** 预处理器已声明，但该文件的 `lang` 与全库众数不一致（如 39 处 scss 里冒出 2 处 less）
**修复方式：** 确认是否有意为之。**不判 Critical**——一个项目同时装 sass 与 less 并各用各的完全合法，静态无法判死；但孤例多半是从别处拷代码带过来的，值得看一眼

### 请求通道 URL 拼装平行实现（维度 8·前端）

**问题模式：** 新增的请求封装（SSE / WebSocket / 新 hook / 新 service）**自己又拼了一遍 base**——`` `${import.meta.env.VITE_API_BASE_URL}${url}` `` 或 `base + url`，而项目里已有 `resolveApiUrl` / `http.ts` 在做同一判断（注释常写着 `must bypass baseURL to avoid doubling`）。接口常量若本就含 context-path（`/demo-app/ai/...`），再拼一次 base → 请求打到 `/demo-app/demo-app/ai/...` → **404**
**修复方式：** 把 base 拼装**收敛到唯一的 URL 解析函数**，新写的请求发起点一律经它取 URL；「已含 context-path 的绝对路径要绕过 base」这条判断**只写在它里面**。**别在新文件里再补一份判断**——那正是本问题的成因，不是修复。`vue-tsc`/`eslint`/类型检查**全绿**，只有真实发请求才暴露

**问题模式（🟡 Warn·不阻断）：** 平行实现是**存量**的（本次改动未触碰）
**修复方式：** 登记为技术债、择机收敛，**不阻断本轮验收**——传 `--changed <本次改动文件>` 后脚本自动这样分档。反之，只要本次改动**新增**了一处平行拼装，即判 🔴 Critical

> **别与维度 3 搞混**：`baseURL` **该不该**含 context-path 是维度 3（配置值对不对）；**这条判据有几份实现**才是维度 8（结构对不对）。同一处问题按其一登记，不重复计。

### UI 还原度违规（维度 10·约定39-R2/R3/R10）

> 判据脚本由 AIDP 脚手架下发到**被测项目侧** `{{AIDP_HOME}}/scripts/check_ui_fidelity.py`（`{{AIDP_HOME}}` 由安装方渲染、相对被测项目根，见 [`../SKILL.md`](../SKILL.md)「运行路径约定」）；
> ⛔ 本 SKILL 不写第二份同判据实现。脚本未下发时标「未核验（工具缺失）」、**报告仍留行**，
> 但仍须对 R10 做一次人工 grep 兜底（它零豁免、判据纯词法）。

| 规则 | 典型问题 | 修复方向 |
| :- | :- | :- |
| **约定39-R10（🔴 零豁免）** | 导出方法体内透传 `pageNo`/`pageSize`/`PageHelper`/`Pageable`/`limit` —— 用户点「导出」却只导当前页 | 导出走独立的**全量查询**路径，不复用分页查询；真需要「只导当前页」必须是显式的另一个按钮 |
| 约定39-R3（🟡） | 文本截断（`ellipsis`/`line-clamp`/`truncate`）而同节点或父节点无 `title`/tooltip | 补 `title` 或 tooltip；确属装饰性文案时就近声明 `fidelity-ignore: R3 <原因>`（**只写规则号不写原因须报 Important**） |
| 约定39-R2（🟡） | 状态标签内容随数据变化，但 `type`/`color` 是字面量常量 —— 状态变了颜色不变 | 颜色随状态映射（枚举 → type/color 表），不写死 |

### 失效实体与边界（维度 11·约定39-R5~R9 + 约定39-R12）

> 六条**机器检不了**，须验收 Agent **静态读代码**核对；某条本轮确无对应场景时标
> 「⏭️ 不适用 + 一句话理由」，**不得直接省略**（省略与「查过且通过」在报告里长得一样）。

| 规则 | 典型问题（实际项目中出现过的缺陷） | 修复方向 |
| :- | :- | :- |
| 约定39-R5 失效实体入口拦截 | 已下架产品仍可点详情并跳转成功 | 渲染处按 `status`/`isDeleted`/`expireTime` `v-if` 隐藏或 `disabled`；⛔ 不接受「按钮还在、点了报错」 |
| 约定39-R6 被删引用降级展示 | 已删除课程展示课程**编码**而非名称 | 存快照名字段或显式展示「已删除的 XX」；⛔ 不裸露 code/ID/空值 |
| 约定39-R7 加载态不渲染脏数据 | 开通页加载中展示 14 个模型、加载完只剩 3 个 | 初始值置空 + `v-if="!loading"` 守卫 / 骨架屏。口诀：**未取到配置先隐藏** |
| 约定39-R8 编辑后视图自动同步 | 部门名称编辑后页面不同步 | 成功回调里刷新列表 / 回写 store；注意**跨组件**（详情改了列表没刷） |
| 约定39-R9 存量数据兼容 | 智能体点「旧数据」开通直接报错 | 新必填给 `DEFAULT` + 迁移脚本 + 读取侧兜底；收窄枚举时老值走到哪个分支要写清 |
| 约定39-R12 同一指标跨页面同源 | 总览页 / 模型管理页 / 用量监控页的 token 调用量三者不一致 | 收敛到详细设计「统计指标口径表」第 8 列声明的**权威取数口径**。口诀：**判据全站唯一化** |

### 第三方临时 mock 反模式（维度 2B）

**问题模式：** 构建期守卫（前端 `import.meta.env.DEV` / `process.env.NODE_ENV==='development'`；后端 `@Profile("dev")` / `#if DEBUG`）
**修复方式：** 改为运行时环境变量开关（`import.meta.env.VITE_THIRD_PARTY_MOCK_ENABLED==='true'` / `@Value("${third-party.mock.enabled}")`），确保 UAT/Demo 打包部署后仍可切换，不被 tree-shake 裁掉

**问题模式：** 真实对接后残留（`.env.*` baseURL 已切真实地址 / 已引入真实 vendor SDK / `new XxxClient(...)`，但 mock 开关仍为 true、fixture 文件或拦截 if 分支未删）
**修复方式：** 真实接口一旦可调通，立即删除全部 THIRD_PARTY_MOCK 标注块、mock fixture、拦截逻辑与开关变量，禁止与真实调用并存或保留为兜底

**问题模式：** THIRD_PARTY_MOCK 标注块缺必填字段（vendor/api/since/expected_ready/owner/REMOVE_WHEN 任一缺失）或 `expected_ready` 已过期超 14 天
**修复方式：** 补全 7 行标注块；过期则催第三方交付或转设计 Module E 暂行方案后删除 mock（详见 `../references/third-party-mock-protocol.md`）

---

## 附录：扫描命令

⛔ **本模板不维护第二份脚本清单** —— **同一份清单两处维护必然漂移**。

自查命令、参数、退出码与 `--json` 字段**一律以 [`../SKILL.md`](../SKILL.md) 各维度小节的机器门命令 + `references/flow-dims-*.md` 各维度命令块为单一信源**
（维度 0 静态基线门起逐维度列出；被测项目侧委派脚本见各「外部脚本门控」维度）。
填本清单时只需在每个问题的「检测方式」里写明**用的是哪个维度的哪条命令**及其退出码。
