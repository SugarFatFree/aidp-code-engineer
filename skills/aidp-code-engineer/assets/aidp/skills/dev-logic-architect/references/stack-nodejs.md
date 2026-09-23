# Node.js 设计落地细则（NestJS / Express / Koa）

> 技术栈选定为 Node.js 后端时加载。跨技术栈通用原则见 `../SKILL.md`，选型候选见 `tech-stack-options.md`。

---

## 一、核心原则 16：HTTP 客户端配置驱动 —— Node.js 落地

| 场景 | 落地方式 |
| :- | :- |
| **NestJS** | `@nestjs/axios` + `ConfigService` 注入 base URL / 超时，**不在代码里写字面量** |
| **Node 18+ 简单调用** | 原生 `fetch` 即可，配置同样从 `process.env` 读 |

```typescript
// ❌ 硬编码
const res = await axios.get('http://192.0.2.100:8080/api/x');
// ✅ 配置驱动
const baseURL = this.config.get<string>('thirdParty.alipay.baseUrl');
```

A.2 须给出 client 初始化示例 + `.env` 配置块；D.3 依赖列表列出所选客户端。

### 失败返回契约（Critical）

同一调用链失败返回三选一并全链路统一。**严禁** `catch { return [] }`——故障被静默降级为空数据。NestJS 推荐抛 `HttpException` 交由 `ExceptionFilter` 统一处理。

---

## 二、检查项 11：字典/枚举 —— Node/TS 侧

| 项 | 取值 |
| :- | :- |
| 定义方式 | TypeScript `enum` 或 `as const` 字面量联合类型（**须在设计中显式声明选哪种并全项目统一**） |
| 文件路径 | `src/enums/order-status.ts` |
| 数据库映射 | TypeORM `enum` 列类型 / Prisma `enum`；或应用层 code-label 转换 |

常量名 `UPPER_SNAKE_CASE`；code/label 须与前端一致（前后端同为 TS 时可考虑共享 types 包，设计须写明）。

---

## 三、配置文件位置

`.env` + `@nestjs/config`；密钥走环境变量，`.env` 不入库（提交 `.env.example`）。

---

## 四、后端第三方 mock 的运行时可控

```typescript
// ❌ 构建期条件装配：@Module 里按 NODE_ENV 决定 provider，打包后不可切换
// ✅ 运行时开关
const mockEnabled = this.config.get('thirdParty.mock.enabled') === true;
```

---

## 核心原则 24：并发加锁选型 —— Node.js 落地

- **P0 进程内锁（首选）**：Node 单线程事件循环内**无数据竞争**，但**存在异步交错**（`await` 之间状态可能被另一次请求改写）。故 P0 不是操作系统锁，而是**异步互斥**：`async-mutex` 的 `Mutex`/`Semaphore`，或自建 Promise 队列串行化临界区。
- **⚠️ 多进程/多实例是常态**：PM2 cluster、`node:cluster`、K8s 多副本下各进程独立，进程内互斥**跨进程无效**，须升 P1。判档时必须先确认部署形态。
- **P1 Redis 分布式锁**：`ioredis` 执行 `set(key, val, 'PX', ttl, 'NX')` **单次原子** + Lua 校验 owner 释放；或用 `redlock` 库（自带续期）。**严禁**先 `setnx` 再 `expire` 两步。
- **P2 数据库级锁**：`SELECT ... FOR UPDATE`（TypeORM `setLock('pessimistic_write')`、Prisma 走原生 SQL）。⚠️ **默认不可用，必须人为确认**（见检查项 32）。

---

## 五、本栈不适用

`@Profile`/`@RefreshScope`/MyBatis TypeHandler 为 Spring 生态概念。前端侧见 `stack-vue.md` / `stack-react.md`。
