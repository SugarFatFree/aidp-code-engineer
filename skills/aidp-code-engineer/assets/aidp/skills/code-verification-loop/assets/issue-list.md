# 代码验收问题清单

> 验收时间：{日期}
> 验收范围：{功能/模块名称}
> 验收轮次：第 {N} 轮
> 验收结果：❌ 不通过
> 输入文档：{列出使用的 PRD、设计文档、接口文档}

---

## 问题汇总

- 🔴 Critical（必须修复）：{X} 项
- 🟡 Important（应该修复）：{Y} 项
- 🔵 Suggestion（建议优化）：{Z} 项

**本轮验收不通过原因：** 存在 {X} 项 Critical 问题未修复。

---

## 🔴 Critical 问题

### 问题 {N}: {问题标题}

**位置：** `{文件路径}:{行号}`

**问题描述：** {详细描述问题}

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

**位置：** `{文件路径}:{行号}`

**问题描述：** {详细描述问题}

**修复建议：** {具体的修复步骤}

---

## 🔵 Suggestion

### 建议 {N}: {建议标题}

**位置：** `{文件路径}:{行号}`

**优化建议：** {具体的优化建议}

**预期收益：** {优化后的预期收益}

---

## 修复指引

请 Agent1 按以下优先级修复问题：

1. **优先修复所有 🔴 Critical 问题**（必须修复，否则验收不通过）
2. **其次修复 🟡 Important 问题**（应该修复，影响代码质量）
3. **最后考虑 🔵 Suggestion**（可选，由用户决定是否修复）

修复完成后，请重新提交验收。

---

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

> 判据脚本由 AIDP 脚手架下发到**被测项目侧** `<被测项目根>/{{AIDP_HOME}}/scripts/check_ui_fidelity.py`；
> ⛔ 本 SKILL 不写第二份同判据实现。脚本未下发时标「不适用」跳过、**报告仍留行**，
> 但仍须对 R10 做一次人工 grep 兜底（它零豁免、判据纯词法）。

| 规则 | 典型问题 | 修复方向 |
| :- | :- | :- |
| **约定39-R10（🔴 零豁免）** | 导出方法体内透传 `pageNo`/`pageSize`/`PageHelper`/`Pageable`/`limit` —— 用户点「导出」却只导当前页 | 导出走独立的**全量查询**路径，不复用分页查询；真需要「只导当前页」必须是显式的另一个按钮 |
| 约定39-R3（🟡） | 文本截断（`ellipsis`/`line-clamp`/`truncate`）而同节点或父节点无 `title`/tooltip | 补 `title` 或 tooltip；确属装饰性文案时就近声明 `fidelity-ignore: R3 <原因>`（**只写规则号不写原因须报 Important**） |
| 约定39-R2（🟡） | 状态标签内容随数据变化，但 `type`/`color` 是字面量常量 —— 状态变了颜色不变 | 颜色随状态映射（枚举 → type/color 表），不写死 |

### 失效实体与边界（维度 11·约定39-R5~R9 + R12）

> 六条**机器检不了**，须验收 Agent **静态读代码**核对；某条本轮确无对应场景时标
> 「⏭️ 不适用 + 一句话理由」，**不得直接省略**（省略与「查过且通过」在报告里长得一样）。

| 规则 | 典型问题（下游真实缺陷） | 修复方向 |
| :- | :- | :- |
| R5 失效实体入口拦截 | 已下架产品仍可点详情并跳转成功 | 渲染处按 `status`/`isDeleted`/`expireTime` `v-if` 隐藏或 `disabled`；⛔ 不接受「按钮还在、点了报错」 |
| R6 被删引用降级展示 | 已删除商品展示商品**编码**而非名称 | 存快照名字段或显式展示「已删除的 XX」；⛔ 不裸露 code/ID/空值 |
| R7 加载态不渲染脏数据 | 套餐选择页加载中展示 14 个选项、加载完只剩 3 个 | 初始值置空 + `v-if="!loading"` 守卫 / 骨架屏。口诀：**未取到配置先隐藏** |
| R8 编辑后视图自动同步 | 部门名称编辑后页面不同步 | 成功回调里刷新列表 / 回写 store；注意**跨组件**（详情改了列表没刷） |
| R9 存量数据兼容 | 对「旧数据」点编辑直接报错 | 新必填给 `DEFAULT` + 迁移脚本 + 读取侧兜底；收窄枚举时老值走到哪个分支要写清 |
| R12 同一指标跨页面同源 | 总览页 / 订单管理页 / 销售报表页的订单量三者不一致 | 收敛到详细设计「统计指标口径表」第 8 列声明的**权威取数口径**。口诀：**判据全站唯一化** |

### 第三方临时 mock 反模式（维度 2B）

**问题模式：** 构建期守卫（前端 `import.meta.env.DEV` / `process.env.NODE_ENV==='development'`；后端 `@Profile("dev")` / `#if DEBUG`）
**修复方式：** 改为运行时环境变量开关（`import.meta.env.VITE_THIRD_PARTY_MOCK_ENABLED==='true'` / `@Value("${third-party.mock.enabled}")`），确保 UAT/Demo 打包部署后仍可切换，不被 tree-shake 裁掉

**问题模式：** 真实对接后残留（`.env.*` baseURL 已切真实地址 / 已引入真实 vendor SDK / `new XxxClient(...)`，但 mock 开关仍为 true、fixture 文件或拦截 if 分支未删）
**修复方式：** 真实接口一旦可调通，立即删除全部 THIRD_PARTY_MOCK 标注块、mock fixture、拦截逻辑与开关变量，禁止与真实调用并存或保留为兜底

**问题模式：** THIRD_PARTY_MOCK 标注块缺必填字段（vendor/api/since/expected_ready/owner/REMOVE_WHEN 任一缺失）或 `expected_ready` 已过期超 14 天
**修复方式：** 补全 7 行标注块；过期则催第三方交付或转设计 Module E 暂行方案后删除 mock（详见 `../references/third-party-mock-protocol.md`）

---

## 附录：扫描命令

以下脚本可用于自查（均跨平台 Python，支持 Linux/macOS/Windows）。其中 **6 个为硬门禁脚本**（Critical 命中即返回非零退出码）：`scan_mock_data.py`、`scan_third_party_mock_antipatterns.py`、`check_file_complexity.py`（单文件超 2 倍阈值 / 单方法 > 50 行直接判 Critical）、`check_di_resolvability.py`（DI 不可解析 Critical 即返回 1；非 Java 项目跳过返 0）、`check_vue_style_preprocessor.py`（`<style lang>` 所需预处理器未声明即返回 1；非 Vue 项目跳过返 0）、`check_request_channel_url.py`（base 拼装判据平行实现即返回 1；扫不到前端源码跳过返 0）；**其余 5 个为采集脚本**（`scan_cache_usage.py` / `scan_code_conventions.py` / `scan_field_columns.py` / `scan_design_field_inventory.py` / `scan_stale_copy.py`）只采集命中点、不判错、退出码恒 0（`scan_stale_copy.py` 加 `--strict` 时有命中返 1），违规由验收 Agent 比对设计/基线后判定：

```bash
# 维度 2A 普通 mock 零容忍 + 维度 2B THIRD_PARTY_MOCK 标注核验
python3 <SKILL_DIR>/scripts/scan_mock_data.py src/ [--json] [--strict] [--third-party-mode]
# 维度 2B 第三方临时 mock 全生命周期 / 反模式（构建期守卫 / 真实对接后残留）
python3 <SKILL_DIR>/scripts/scan_third_party_mock_antipatterns.py src/ [--json] [--strict]
# 维度 4 缓存使用点采集（与设计 A.2「缓存方案」双向比对）
python3 <SKILL_DIR>/scripts/scan_cache_usage.py src/ [--json]
# 维度 4 文件复杂度 + 单方法行数
python3 <SKILL_DIR>/scripts/check_file_complexity.py src/ [--json] [--strict]
# 维度 4 源码静态约定合集（http-hardcode / refresh-scope / dead-ref / dep-baseline / audit-fill）
python3 <SKILL_DIR>/scripts/scan_code_conventions.py src/ [--checks http-hardcode,refresh-scope,dead-ref,dep-baseline,audit-fill] [--base <ref>] [--json]
# 维度 4 字段/列对账采集（视觉还原支柱① 字段一致性；采表格列/表单字段集合，以展示语义名再与「需求字段→处置」对照表逐项比对）
python3 <SKILL_DIR>/scripts/scan_field_columns.py src/ [--json]
# 维度 4 字段集与设计双向比对·设计侧采集（采详细设计「字段实现清单」表，与 scan_field_columns 实现侧集合双向比对）
python3 <SKILL_DIR>/scripts/scan_design_field_inventory.py <详细设计目录> [--json]
# 维度 4 文案与数据口径一致性（旧口径残留 + 作废 REQ 编号注释未标失效；清单取自 ux 表 E/表 F）
python3 <SKILL_DIR>/scripts/scan_stale_copy.py src/ --stale-phrases-file <旧口径字样> --stale-reqs-file <作废REQ编号> [--json] [--strict]
# 维度 6 DI 依赖可解析性（Java/Spring 专用硬门；不编译不起容器，扫不到 .java 则整维度跳过）
python3 <SKILL_DIR>/scripts/check_di_resolvability.py <代码目录> [--json] [--strict] [--config-keys-file <配置项清单>]

# 维度 7 CSS 预处理器一致性（Vue 专用硬门；纯静态零构建，扫不到 .vue 则整维度跳过）
python3 <SKILL_DIR>/scripts/check_vue_style_preprocessor.py <改动的 .vue 或前端目录> [--json] [--strict] [--baseline-root <众数基线根>]

# 维度 8 请求通道 URL 拼装单一信源（前端专属硬门；纯静态零执行，扫不到前端源码则整维度跳过）
python3 <SKILL_DIR>/scripts/check_request_channel_url.py <前端目录> --changed <本次改动的文件...> [--allow <单一信源glob>] [--json] [--strict]

# 维度 10 — UI 还原度确定性检查（脚本在**被测项目侧**，不在本 SKILL）
python3 <被测项目根>/{{AIDP_HOME}}/scripts/check_ui_fidelity.py --json
# 维度 12 — 上游调用日志可见性与脱敏（脚本在**被测项目侧**；只扫 .java/.kt，非 JVM 栈 outbound_files=0 即标不适用）
python3 <被测项目根>/{{AIDP_HOME}}/scripts/check_upstream_call_log.py --json
# 维度 13 — 实现偏离设计（脚本在**被测项目侧**；⚠️ --version 必填带值，漏传落 exit 2 = 这一档静默没跑）
python3 <被测项目根>/{{AIDP_HOME}}/scripts/check_design_anchor.py --version <版本号> --json

# 备用 Shell 命令（仅 Linux/macOS）
grep -rn "mockData\|fakeData\|mockList\|fakeList" src/ --include="*.vue" --include="*.ts" --include="*.js"
find src/ -type d \( -name "mock" -o -name "mocks" -o -name "__mocks__" \)
grep -rn "Mock.mock\|setupWorker\|json-server" src/
grep -rn "TODO.*接口\|FIXME.*mock" src/
```
