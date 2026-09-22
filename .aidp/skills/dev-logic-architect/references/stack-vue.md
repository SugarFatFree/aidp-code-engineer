# 前端 Vue 设计落地细则

> 技术栈选定为 Vue（或探测到 `*.vue` / `package.json` 依赖含 `vue`）时加载。跨技术栈通用原则见 `../SKILL.md`，选型候选见 `tech-stack-options.md`。

---

## 一、检查项 11：字典/枚举 —— 前端 Vue 侧

| 项 | 取值 |
| :- | :- |
| 前端枚举/常量类名 | PascalCase，如 `OrderStatus` |
| 文件路径 | `src/enums/orderStatus.ts` 或 `src/constants/enums/order-status.ts`（**设计须二选一并全项目统一**） |
| 定义方式 | TypeScript `enum` 或 `as const` 字面量联合类型（**须显式声明选哪种**） |

```typescript
// 方式 A：enum
export enum OrderStatus { PENDING = 1, PAID = 2 }
// 方式 B：as const（tree-shaking 友好，推荐用于纯前端常量）
export const ORDER_STATUS = { PENDING: 1, PAID: 2 } as const;
export type OrderStatus = typeof ORDER_STATUS[keyof typeof ORDER_STATUS];
```

**⚠️ 前后端一致性（Critical）**：同一枚举的 `code`/`label` 在前后端必须一致，**严禁前后端各自定义且取值不同**。每个枚举常量含 `code`/`label`/`description`（状态类追加 `color`，供 `el-tag` 等着色用）。即便只有 2 个候选值也必须定义枚举，严禁裸字符串/裸数字散落业务代码。后端侧定义见对应后端栈文件。

---

## 二、核心原则 14：前端第三方 mock 的运行时可控

```typescript
// ❌ 构建期裁掉：production 打包被 Vite tree-shake，UAT/Demo 部署后 mock 不可用
if (import.meta.env.DEV) { /* mock */ }
if (process.env.NODE_ENV === 'development') { /* mock */ }
// ❌ Vite/Webpack DefinePlugin 在构建期替换的常量同理

// ✅ 运行时环境变量
const mockEnabled = import.meta.env.VITE_THIRD_PARTY_MOCK_ENABLED === 'true';
```

设计 B.7 须为每个未交付的第三方接口标注 mock 位置。**P0 前端 mock 为首选**——第三方接口仅供前端调用时（OAuth 登录回调、地图、验证码等），前端 axios/fetch 拦截器 + 运行时环境变量即可，无需后端介入、前端独立联调。

---

## 三、A.2 前端基础框架配置须落地

- **主题/设计令牌**：全局主题文件路径（`src/theme/variables.scss` / `src/styles/element/index.scss` / `tailwind.config.*`），主色与语义色取自设计令牌而非组件库默认。
- **请求层**：`src/utils/request.ts` 的 `baseURL` 须取自 `.env` 的 `VITE_API_BASE_URL`，且**必须包含后端 context-path**（后端 context-path 配置位置见对应后端栈文件）。

---

## 四、本栈不适用

HTTP 客户端选型（核心原则 16）针对**后端发起外部请求**，前端不适用；`@Profile`/`@RefreshScope`/ORM 映射为后端概念；DB 方言约束见 `stack-db-mysql.md`。

---

## 核心原则 24：并发加锁 —— 本栈不适用

浏览器端无服务端并发临界区，**不适用** P0/P1/P2 加锁选型。前端侧的"防重复提交"用**按钮禁用 + 请求去重（同 key 在途请求合并/丢弃）**实现，属交互与请求层约束，**不能替代后端加锁**——后端仍须按核心原则 24 独立落档。
