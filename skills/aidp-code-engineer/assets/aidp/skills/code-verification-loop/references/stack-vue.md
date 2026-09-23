# 前端 Vue 审计细则

> 探测命中 `*.vue` 或 `package.json` 依赖含 `vue` 时加载本文件。跨技术栈的通用判据见 `../SKILL.md`，此处只写 Vue（含 Vite / Element Plus）专有部分。

---

## 一、维度 2B：前端第三方 mock 的技术栈专有反模式

### 1.1 构建期守卫（反模式 1·🔴 Critical）

```typescript
// ❌ 错误：使用 DEV 构建期守卫，打包后被裁掉
if (import.meta.env.DEV && config.url?.includes('/alipay/trade/refund')) {
  // 这段代码在 production 构建时会被 Vite tree-shake 完全删除
}

// ❌ 错误：使用 NODE_ENV 构建期判断
if (process.env.NODE_ENV === 'development') {
  // 同样会被 Webpack/Vite 在 production mode 裁掉
}

// ✅ 正确：运行时环境变量判断
const mockEnabled = import.meta.env.VITE_THIRD_PARTY_MOCK_ENABLED === 'true';
if (mockEnabled && config.url?.includes('/alipay/trade/refund')) {
  // 打包后此逻辑仍保留，部署时修改环境变量即可切换
}
```

> **为什么是 Critical**：构建期守卫在 production 打包时被 tree-shake 整段删除，UAT/Demo 环境部署后 mock 根本不可用——而这恰恰是最需要 mock 的环境。

### 1.2 真实对接后残留检查（反模式 2）

1. 检查 `.env.production` 或部署配置中的 `VITE_API_BASE_URL`（或类似变量）
2. 若已切换到真实地址（非 `http://localhost:*` / `http://127.0.0.1:*`），扫描以下残留：
   - Mock 开关变量：`VITE_THIRD_PARTY_MOCK_ENABLED=true` 仍存在
   - Mock fixture 文件：`src/mocks/fixtures/*.json` 仍存在
   - Mock 拦截逻辑：拦截器中 `if (mockEnabled && ...)` 分支未删除
   - `THIRD_PARTY_MOCK` 标注块仍在代码中

### 1.3 Mock 实现位置选型

必须使用 mock 时**优先前端方案**（axios/fetch 拦截器 + 运行时环境变量控制、MSW、本地 JSON 文件），无需后端介入、前端独立联调、效率最高。判断口诀：**「前端能拦截就前端拦截，前端拦截不了再让后端 mock」**。

---

## 二、维度 4：Vue 专有检查项

### 2.1 叶子组件替换白名单（约定 28 实现选型层）

情形 B/C 下前端【样式·内容·操作逻辑】三层须尽量 100% 还原原型 `code/`，**唯一允许的偏离**是把原型里的**内部原子/叶子小组件**替换成项目已有技术栈的等价组件——典型即**原型 Antd 叶子件 → 项目 Element Plus 等价件**（`a-tag` → `el-tag`、`a-select` → `el-select`、`a-date-picker` → `el-date-picker`、`a-table` → `el-table`、`a-pagination` → `el-pagination` 等）。

**白名单**（内部原子/叶子小组件 = 实现载体类 + 普通叶子件）：Layout 布局 / Container 布局容器 / Color 色彩 / Link 文字链接 / 单选框 / 多选框 / 下拉选择 / 日期时间选择器 / 进度条 / Tab 页 / Tag / Icon 图标 / 消息提醒 / 计数器 / 开关 / 滑块 / 上传 / 表单 / 列表 / 表格 / 分页 / Alert / Loading / MessageBox 弹框 / Message 消息提示 / NavMenu 导航菜单 / Card 卡片 等同类叶子小组件。

**★ 实现载体类（Layout / Container / Color / Link）入白名单的判定要点——只放行「换载体」、不放行「改结果」：**
- ✅ **合规**：用项目的 `el-container`/`el-row`/`el-col`/`el-link`/项目色彩变量机制去**实现**原型的布局与配色（换的是**载体**，不是**结果**）
- 🔴 **仍判 Critical**：借「Layout/Container 进白名单」把**栅格划分 / 版心宽度 / 模块位置**改成组件库默认或偏离原型；借「Color 进白名单」把**主色 / 语义色的具体值**改成 Element Plus 默认色

**命中白名单仍须过两条硬约束，任一不满足 = 🔴 Critical**：
1. **主题 token / 布局度量取自 L1 原型体系**（主色/语义色**具体值** + 栅格划分/版心宽度/模块位置均来自设计令牌 + 全局主题 + 原型，而非组件库默认观感）
2. **操作逻辑/交互行为与原型一致**（换的是组件实现、不是行为；借「换组件」简化或改流程 = Critical）

**判定速查**：命中白名单 + 两约束满足 → 合规（内部样式差异 L2/Important 不阻塞）；命中白名单但主题 token / 布局度量或操作逻辑不符 → 🔴 Critical；白名单之外的结构/布局/视觉体系（L1）/内容/操作逻辑偏离且未标裁剪/延期/改为X → 🔴 Critical。

### 2.2 视觉基准与主题文件路径（Vue 项目）

无高保真、对齐产品原型（AIDP 情形 B/C）时，视觉基准 = 设计令牌 + **前端全局主题文件** + 原型 `code/`。Vue 项目的主题文件通常在：

```
src/theme/variables.scss    src/styles/element/index.scss    tailwind.config.*
```

**反模式专项（🔴 Critical）**：页面散落**硬编码色值/尺寸**而非引用主题变量；或**主题文件仍是 Element Plus 默认主题未按原型覆写**。

### 2.3 字段/列采集（Vue SFC）

```bash
python3 <SKILL_DIR>/scripts/scan_field_columns.py <前端目录>
```

采集 `el-table-column` 的 `label`、`el-form-item` 的 `label`、以及 `columns` 数组配置项的 `label`/`title`。**对账主键是展示语义名（`label`/`title`），不是代码级 `prop`**——`prop` 仅作辅助参考。

### 2.4 单文件行数阈值（Vue SFC）

**Vue SFC ≤ 300 行**（不含 import + 注释），超阈值告警、2 倍阈值升 Critical；**单方法/函数 ≤ 50 行**为硬阈值。逻辑复用优先抽 **Composable**（`composables/useXxx.ts`），跨页面复用提升到 `src/composables/` 或 `src/utils/`。

```bash
python3 <SKILL_DIR>/scripts/check_file_complexity.py <代码目录>
```

---

## 三、维度 3：前端 baseURL 与 context-path 拼接

检查前端 API 配置（`src/config/api.ts`、`src/utils/request.ts`、`.env*`），确认 `baseURL` / `VITE_API_BASE_URL` 是否包含后端的 context-path：

```typescript
// ❌ 错误：后端配置了 context-path=/api，前端未包含
const baseURL = 'http://localhost:8080'

// ✅ 正确
const baseURL = 'http://localhost:8080/api'
```

后端 context-path 的检测方式见对应后端栈文件（`stack-java-spring.md` / `stack-nodejs.md` / `stack-go.md` / `stack-python.md`）。

---

## 四、维度 7：CSS 预处理器一致性（本栈专属硬门）

> **本 SKILL 唯一的 Vue 专属门控维度**，与 Java/Spring 的维度 6 对称：都是「静态可查、但编译/lint 期完全无感、非要到部署期才炸」的结构性盲区。

### 4.1 为什么 lint 与类型检查拦不住

`vue-tsc --noEmit` 只做类型检查、`eslint` 只解析 `<template>` 与 `<script>`——**两者都不编译 `.vue` 的 `<style>` 块**。于是这一整类问题在开发期轻量验证里 **100% 静默通过**：

- `<style lang="scss">` 但项目只装了 `less` → CI `vite build` 报 `loadSassPackage` 失败
- `lang` 拼错（`sccs`）→ 同上
- `@import` / `@use` 路径错 → 同上

**不要为此把完整构建塞进开发期**——「开发期只做轻量验证」这条规定是对的。本检查纯静态、零构建、零安装，成本与一次 grep 同量级，正好补这道缝。

> ⚠️ **本维度的覆盖边界（别当已查）**：硬门脚本只回答**一件事**——`<style lang>` 声明的预处理器**有没有被 `package.json` 声明**。上面第 3 条 `@import` / `@use` **路径**是否存在**不在脚本覆盖内**（路径别名 `@/`、`~`、`includePaths`、sass partial `_x.scss` 的省略规则叠加后，静态解析误报率高，得不偿失），改动涉及新增 `@import`/`@use` 时须由验收 Agent **人工核对被引文件确实存在**。第 2 条 `lang` 拼错落在「其它未知值 = 🟡 Warn」一档（见 4.2）——**Warn 不阻断**，需人工看一眼，别因为脚本 exit 0 就认为拼写没问题。

### 4.2 判定表

| lang | 所需 npm 包（命中任一即算已声明） | 未声明 |
| :- | :- | :-: |
| `scss` / `sass` | `sass` \| `sass-embedded` \| `node-sass` | 🔴 Critical |
| `less` | `less` | 🔴 Critical |
| `styl` / `stylus` | `stylus` | 🔴 Critical |
| 无 `lang` / `css` / `postcss` | —（原生 CSS，PostCSS 随 Vite 内置） | 不参与判定 |
| 其它未知值 | — | 🟡 Warn（人工确认，自定义预处理器合法） |

**依赖查找必须一路向上合并到 git 根**：monorepo 常把 `sass`/`less` 提到根 `package.json`（依赖提升），只看子包那份会误报一片。

**孤例判定（🟡 Warn）**：预处理器已声明、但该文件 `lang` 与**全库众数**不一致（如 39 处 `scss` 里冒出 2 处 `less`）。不判 Critical——一个项目同时装两种并各用各的完全合法；但孤例多半是从别处拷代码带过来的，值得看一眼。

### 4.3 硬门脚本

```bash
# 只查本次改动的文件（推荐）
python3 <SKILL_DIR>/scripts/check_vue_style_preprocessor.py <改动的 .vue 列表> --json
# 首次接管存量项目时全量扫
python3 <SKILL_DIR>/scripts/check_vue_style_preprocessor.py <前端目录>
```

零依赖纯标准库。

> 📌 **脚本接口事实（JSON 字段清单、`passed`/`gate_passed`/`skipped` 语义、退出码、实测数字）一律以 `dimension-6-9-stack-gated.md` 维度 7 为单一信源，本文件不复制。**
> 与维度 8 同一条规则：这些会随脚本改动，抄在各栈文件里必然漂移。

**本节只写 Vue SFC 专有的误报控制**（🔴 是阻塞级，误报直接卡发布，故按精度优先处理）：只认 **SFC 顶层块**——HTML 注释里的 `<!-- <style lang="scss"> -->`、`<script>` 字符串里的 `'<style lang="scss">'`、`<template>` 体内（含嵌套 `<template #slot>` 之后）的 `<style>` 标签一律不参与判定；属性按 token 切分而非整串正则，故 `<style data-x="lang=scss">`、`<style data-lang="scss" lang="less">` 不会误读 lang。

---

## 五、维度 8：请求通道 URL 拼装单一信源

> ⚠️ **本维度不是 Vue 专属**——判据对 React / 原生 TS 前端完全一致（见 `stack-react.md` §四）。此处写 Vue 侧落地形态，判据本体见 `dimension-6-9-stack-gated.md` 维度 8。

### 5.1 与 §三 的关系（同一道缝的两半，别搞混）

| | 管什么 | 归属 |
| :- | :- | :- |
| **§三** | base **该不该**含 context-path —— **配置值**对不对 | 维度 3 |
| **本节** | 「谁拼 base、谁不拼」这条判据**有几份实现** —— **结构**对不对 | 维度 8 |

两者正是同一个 bug 的两半：`baseURL` 含 context-path（§三判它对），接口常量 `/demo-app/ai/...` 也含 context-path，于是**谁该绕过 base 必须由单一信源统一决定**；一旦有第二份实现，两边迟早各自表述 → `/demo-app/demo-app/ai/...` → 404。

### 5.2 Vue 侧的典型形态

```typescript
// ✅ 唯一合法位置：URL 解析单一信源
// src/utils/apiUrl.ts
const base = import.meta.env.VITE_API_BASE_URL
export function resolveApiUrl(url: string) {
  if (/^https?:\/\//.test(url)) return url
  if (url.startsWith('/demo-app')) return url   // 已含 context-path，绕过 base
  return `${base}${url}`
}

// ❌ 第二份实现：新写的 SSE 封装自己又拼了一遍
export async function runSseTask(url: string) {
  const full = `${import.meta.env.VITE_API_BASE_URL}${url}`   // 🔴 维度 8 命中
  return (await fetch(full, { method: 'POST' })).body!.getReader()
}
```

**修法**：把 base 拼装收敛到唯一的 `resolveApiUrl(url)`，`fetch` / `EventSource` / `axios` / SSE 封装一律经它取 URL；「已含 context-path 的绝对路径要绕过 base」这条判断**只写在它里面**。

### 5.3 Vue 侧的合法非命中形态（不该报）

以下三种都会出现 base 拼装字样，但**不属请求通道**，脚本靠「所在文件是否有请求发起点」把它们挡在门外——**验收 Agent 人工核对时同样别把它们当问题**：

```javascript
window.location.href = `${conf.baseUrl}/sso/logout`   // 页面跳转，非请求
const http$ = new HttpClient(config.baseUrl)          // 传参给客户端，未自拼
const url = resolvePath(baseUrl, element.url)         // 函数式传参，未自拼
```

`.vue` 文件**只扫 `<script>` 块**——`<template>` 里用 `` `${baseUrl}/doc` `` 拼 `:href` 属于链接渲染、不是请求通道。

### 5.4 硬门脚本

```bash
# 验收本次改动（推荐）
python3 <SKILL_DIR>/scripts/check_request_channel_url.py <前端目录> --changed <本次改动的文件...> --json
# 已明确单一信源时收紧口径
python3 <SKILL_DIR>/scripts/check_request_channel_url.py <前端目录> --allow 'src/utils/apiUrl.ts'
```

> 📌 **脚本接口事实（JSON 字段语义、退出码、两条安全失败、`--allow`/`--changed` 优先级、实测数字）一律以 `dimension-6-9-stack-gated.md` 维度 8 为单一信源，本文件不复制。**
> 这些会随脚本改动，抄在各栈文件里必然漂移（例如 `single_source` 语义），故只在维度 8 细则一处维护。

**本栈唯一需要额外记住的一点**：`.vue` **只扫 `<script>` 块**（理由与 `<template>` 的 `:href` 例子见 5.3）。

---

## 六、本栈不适用的检查项

维度 6「DI 依赖可解析性」为 Java/Spring 专属，**Vue 项目整维度跳过**；后端专有的金额类型守恒、DB 约束前置校验、`@RefreshScope`、审计字段填充等同样不适用。
