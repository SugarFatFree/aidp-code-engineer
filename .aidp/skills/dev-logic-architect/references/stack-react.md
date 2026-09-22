# 前端 React 设计落地细则

> 技术栈选定为 React（或探测到 `*.jsx`/`*.tsx` / `package.json` 依赖含 `react`）时加载。跨技术栈通用原则见 `../SKILL.md`，选型候选见 `tech-stack-options.md`。

---

## 一、检查项 11：字典/枚举 —— 前端 React 侧

| 项 | 取值 |
| :- | :- |
| 前端枚举/常量类名 | PascalCase，如 `OrderStatus` |
| 文件路径 | `src/enums/orderStatus.ts` 或 `src/constants/enums/order-status.ts`（**设计须二选一并全项目统一**） |
| 定义方式 | TypeScript `enum` 或 `as const` 字面量联合类型（**须显式声明选哪种**） |

```typescript
export const ORDER_STATUS = { PENDING: 1, PAID: 2 } as const;
export type OrderStatus = typeof ORDER_STATUS[keyof typeof ORDER_STATUS];
```

**⚠️ 前后端一致性（Critical）**：同一枚举的 `code`/`label` 在前后端必须一致，严禁各自定义取值不同。每个常量含 `code`/`label`/`description`（状态类追加 `color`，供 Antd `Tag` 着色）。即便只有 2 个候选值也必须定义。后端侧定义见对应后端栈文件。

---

## 二、核心原则 14：前端第三方 mock 的运行时可控

```tsx
// ❌ 构建期裁掉
if (process.env.NODE_ENV === 'development') { /* mock */ }
if (import.meta.env.DEV) { /* mock */ }

// ✅ 运行时开关
// Vite: import.meta.env.VITE_THIRD_PARTY_MOCK_ENABLED === 'true'
// CRA:  process.env.REACT_APP_THIRD_PARTY_MOCK_ENABLED === 'true'
```

> ⚠️ **React 特有陷阱**：CRA 的 `REACT_APP_*` 与 Next.js 的 `NEXT_PUBLIC_*` 在**构建时**被静态替换进产物——它们**只能在构建时确定值**。若设计要求「部署后改环境变量即可切换 mock」，必须改为**运行时注入**（启动时 fetch `/config.json`，或读 `window.__RUNTIME_CONFIG__`），设计 A.2 须写明采用哪种。

设计 B.7 须为每个未交付的第三方接口标注 mock 位置，**P0 前端 mock 首选**（可用 MSW / axios 拦截器）。

---

## 三、A.2 前端基础框架配置须落地

- **主题/设计令牌**：`src/styles/theme.ts` / `tailwind.config.*` / Antd `ConfigProvider theme={{ token }}`，主色与语义色取自设计令牌而非组件库默认蓝。
- **请求层**：`src/utils/request.ts` 的 `baseURL` 取自环境变量，且**必须包含后端 context-path**。

---

## 四、本栈不适用

HTTP 客户端选型（核心原则 16）针对后端发起外部请求，前端不适用；`@Profile`/`@RefreshScope`/ORM 映射为后端概念；DB 方言见 `stack-db-mysql.md`。

---

## 核心原则 24：并发加锁 —— 本栈不适用

同 Vue 侧：浏览器端无服务端并发临界区，**不适用** P0/P1/P2 加锁选型。前端"防重复提交"（按钮禁用 / 请求去重 / `AbortController` 取消在途请求）属交互与请求层约束，**不能替代后端加锁**。
