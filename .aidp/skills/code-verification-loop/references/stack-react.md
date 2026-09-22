# 前端 React 审计细则

> 探测命中 `*.jsx`/`*.tsx` 或 `package.json` 依赖含 `react` 时加载本文件。跨技术栈的通用判据见 `../SKILL.md`，此处只写 React（含 Vite / webpack / Antd）专有部分。

---

## 一、维度 2B：前端第三方 mock 的技术栈专有反模式

### 1.1 构建期守卫（反模式 1·🔴 Critical）

```tsx
// ❌ 错误：NODE_ENV 构建期判断，production 打包被 webpack/Vite 裁掉
if (process.env.NODE_ENV === 'development') { /* mock 拦截 */ }

// ❌ 错误：Vite 的 DEV 构建期守卫，同样会被 tree-shake
if (import.meta.env.DEV) { /* mock 拦截 */ }

// ✅ 正确：运行时环境变量判断
// CRA:  const mockEnabled = process.env.REACT_APP_THIRD_PARTY_MOCK_ENABLED === 'true'
// Vite: const mockEnabled = import.meta.env.VITE_THIRD_PARTY_MOCK_ENABLED === 'true'
if (mockEnabled && config.url?.includes('/alipay/trade/refund')) { /* ... */ }
```

> ⚠️ **React 项目的特有陷阱**：CRA 的 `REACT_APP_*` 与 Next.js 的 `NEXT_PUBLIC_*` 变量在**构建时**被静态替换进产物。这意味着它们**只能在构建时确定值**——若要求「部署后改环境变量即可切换 mock」，必须改为**运行时注入**（如启动时 fetch `/config.json`、或读 `window.__RUNTIME_CONFIG__`），否则与构建期守卫同样不可控，判 🔴 Critical。

### 1.2 真实对接后残留检查（反模式 2）

1. 检查 `.env.production` 中的 `REACT_APP_API_BASE_URL` / `VITE_API_BASE_URL` / `NEXT_PUBLIC_API_BASE_URL`
2. 若已切换到真实地址（非 `http://localhost:*` / `http://127.0.0.1:*`），扫描以下残留：
   - Mock 开关变量仍为 `true`
   - Mock fixture 文件：`src/mocks/*.json`、MSW 的 `src/mocks/handlers.ts` / `browser.ts` 仍被引入
   - Mock 拦截逻辑：axios interceptor 或 MSW handler 未删除
   - `THIRD_PARTY_MOCK` 标注块仍在代码中

> **MSW 专项**：用 MSW 时须确认 `worker.start()` 的调用点也已删除或被运行时开关包裹——只删 handler 不删 start，Service Worker 仍会注册。

### 1.3 Mock 实现位置选型

优先前端方案（axios/fetch 拦截器 + 运行时开关、**MSW**、本地 JSON），口诀「前端能拦截就前端拦截，前端拦截不了再让后端 mock」。

---

## 二、维度 4：React 专有检查项

### 2.1 叶子组件替换白名单（约定 28 实现选型层）

情形 B/C 下须尽量 100% 还原原型 `code/`，**唯一允许的偏离**是把原型里的**内部原子/叶子小组件**换成项目已有技术栈的等价件（如原型用的组件库 → 项目 Antd / MUI / shadcn 等价件）。

**白名单**：Layout 布局 / Container 布局容器 / Color 色彩 / Link 文字链接 / 单选框 / 多选框 / 下拉选择 / 日期时间选择器 / 进度条 / Tab 页 / Tag / Icon / 消息提醒 / 计数器 / 开关 / 滑块 / 上传 / 表单 / 列表 / 表格 / 分页 / Alert / Loading / Modal / message 提示 / 导航菜单 / Card 等同类叶子小组件。

**★ 只放行「换载体」、不放行「改结果」**：
- ✅ 合规：用 Antd `Layout`/`Row`/`Col`/`Typography.Link` 或项目色彩变量机制去**实现**原型的布局与配色
- 🔴 Critical：借白名单把**栅格划分 / 版心宽度 / 模块位置**改成组件库默认；借 Color 白名单把**主色 / 语义色具体值**改成 Antd 默认蓝

**两条硬约束**（任一不满足 = 🔴 Critical）：① 主题 token / 布局度量取自 L1 原型体系（非 `ConfigProvider` 默认 theme）；② 操作逻辑/交互行为与原型一致。

### 2.2 视觉基准与主题配置（React 项目）

主题文件通常在：

```
src/styles/theme.ts   tailwind.config.*   ConfigProvider theme={{ token: {...} }}
```

**反模式专项（🔴 Critical）**：页面散落硬编码色值/尺寸而非引用 token；或 `ConfigProvider` 仍是 Antd 默认 theme 未按原型覆写。

### 2.3 字段/列采集（React/TSX）

```bash
python3 <SKILL_DIR>/scripts/scan_field_columns.py <前端目录>
```

采集 `columns` 数组配置项的 `title`（Antd Table）、`Form.Item` 的 `label`。**对账主键是展示语义名（`title`/`label`），不是 `dataIndex`**——`dataIndex` 仅作辅助参考。

> ⚠️ **与维度 3.7 的强关联**：Antd Table 的 `render(text, record, index)` 与 ECharts `tooltip.formatter` 里按 `params.dataIndex` 回原数组取值的**旁路消费点**，是出参字段结构变更后最容易漏改的地方——见 `dimension-3-interface.md` 维度 3.7「出参字段变更消费点穷举」。

### 2.4 单文件行数阈值（React 组件）

**React 组件 ≤ 300 行**、TS/JS 普通模块 ≤ 400 行（均不含 import + 注释），超阈值告警、2 倍升 Critical；**单方法/函数 ≤ 50 行**硬阈值。逻辑复用优先抽 **Custom Hook**（`hooks/useXxx.ts`），跨页面复用提升到 `src/hooks/` 或 `src/utils/`。

---

## 三、维度 3：前端 baseURL 与 context-path 拼接

检查 `src/config/api.ts` / `src/utils/request.ts` / `.env*`，确认 `baseURL` 含后端 context-path：

```typescript
// ❌ 后端 context-path=/api，前端未包含
const baseURL = 'http://localhost:8080'
// ✅
const baseURL = 'http://localhost:8080/api'
```

后端 context-path 检测方式见对应后端栈文件。

---

## 四、维度 8：请求通道 URL 拼装单一信源（**React 同样适用**）

> ⚠️ 与维度 6/7 不同，**本维度不被 Vue 独占**——它查的是「把 base 拼到 URL 前面」这条判据有几份实现，与 SFC、`<style lang>`、DI 容器都无关，React 项目**照常生效、不跳过**。判据本体见 `dimension-6-9-stack-gated.md` 维度 8。

### 4.1 与 §三 的关系

§三（维度 3）管 **base 该不该含 context-path**（配置值对不对）；本节（维度 8）管**这条判据有几份实现**（结构对不对）。二者是同一个 bug 的两半：base 含 context-path、接口常量也含，谁绕过 base **必须由单一信源统一决定**，否则第二份实现迟早各写各的 → 路径重复 → 404。

### 4.2 React 侧的典型形态

```typescript
// ✅ 唯一合法位置：URL 解析单一信源（src/utils/apiUrl.ts）
const base = process.env.REACT_APP_API_BASE_URL   // CRA；Vite + React 则是 import.meta.env.VITE_*
export function resolveApiUrl(url: string) {
  if (/^https?:\/\//.test(url)) return url
  if (url.startsWith('/demo-app')) return url   // 已含 context-path，绕过 base
  return `${base}${url}`
}

// ❌ 第二份实现：hook 里自己又拼了一遍
export function useStream(url: string) {
  const full = process.env.REACT_APP_API_BASE_URL + url    // 🔴 维度 8 命中
  return fetch(full).then(r => r.body!.getReader())
}
```

**修法**：收敛到唯一的 `resolveApiUrl(url)`，`fetch` / `EventSource` / `axios` / SWR·React-Query 的 fetcher 一律经它取 URL。

### 4.3 React 侧的合法非命中形态（不该报）

`window.location.href = \`${base}/logout\``（页面跳转）、`new HttpClient(config.baseUrl)`（传参）、`resolvePath(base, url)`（函数式传参）都不算请求通道——脚本靠「所在文件是否有请求发起点」把它们挡在门外，人工核对时同样别当问题。

### 4.4 硬门脚本

```bash
python3 <SKILL_DIR>/scripts/check_request_channel_url.py <前端目录> --changed <本次改动的文件...> --json
```

与 Vue 侧**同一个脚本、同一套判据**（`.tsx`/`.jsx` 与 `.ts`/`.js` 一并扫，本维度不依赖 SFC 机制）。

> 📌 **脚本接口事实（JSON 字段语义、退出码、安全失败、`--allow`/`--changed` 优先级、实测数字）一律以 `dimension-6-9-stack-gated.md` 维度 8 为单一信源，本文件不复制**——抄在各栈文件里必然漂移。

---

## 五、本栈不适用的检查项

维度 6「DI 依赖可解析性」为 Java/Spring 专属、维度 7「CSS 预处理器一致性」为 Vue SFC 专属（React 无 `<style lang>` 机制，CSS-in-JS / CSS Modules 的预处理器由构建配置而非文件内声明决定），**React 项目此二维度整维度跳过**；后端专有的金额类型守恒、DB 约束前置校验、`@RefreshScope`、审计字段填充等同样不适用。**注意维度 8 不在此列——它对 React 生效**（见 §四）。
