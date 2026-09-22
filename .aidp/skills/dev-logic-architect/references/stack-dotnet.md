# .NET 设计落地细则

> 技术栈选定为 .NET（或探测到 `*.csproj` / `*.sln`）时加载。跨技术栈通用原则见 `../SKILL.md`，选型候选见 `tech-stack-options.md`。

---

## 一、核心原则 16：HTTP 客户端配置驱动 —— .NET 落地

| 场景 | 落地方式 |
| :- | :- |
| **HTTP 调用** | 统一 `IHttpClientFactory` **工厂模式**（`services.AddHttpClient<T>()`）——**避免 socket 耗尽**，这是 .NET 侧的硬要求，不是风格偏好 |
| **gRPC 调用** | `Grpc.Net.Client`，channel 从 `appsettings.json` 注入，认证凭证用 `${ENV_VAR}` |

```csharp
// ❌ 严禁：既硬编码又每次 new HttpClient（socket 耗尽）
client.BaseAddress = new Uri("http://192.0.2.100:8080");
// ✅ 工厂 + 配置驱动
services.AddHttpClient<IAlipayClient, AlipayClient>(c =>
    c.BaseAddress = new Uri(config["ThirdParty:Alipay:BaseUrl"]));
```

D.3 依赖列表须列出所选客户端包。

### 失败返回契约（Critical）

三选一并全链路统一。**严禁** `catch { return new List<T>(); }` 把故障静默降级为空集合；推荐抛自定义异常交由中间件统一转错误码。

---

## 二、检查项 11：字典/枚举 —— .NET 侧

`public enum OrderStatus { ... }` + `[Description]` 特性或伴生 `EnumMeta` 承载 code/label/description；文件路径 `Enums/OrderStatus.cs`。数据库映射：EF Core `HasConversion<int>()` 或 `EnumToStringConverter`。

常量名 `PascalCase`（.NET 惯例，须在设计中显式声明并全项目统一）；code/label 须与前端一致。

---

## 三、配置文件位置

`appsettings.json` + `appsettings.{Environment}.json`；密钥走环境变量 / User Secrets，**严禁提交**。

---

## 四、后端第三方 mock 的运行时可控

```csharp
// ❌ #if DEBUG 构建期隔离
// ✅ 运行时配置开关
if (config.GetValue<bool>("ThirdParty:Mock:Enabled")) { return mockData; }
```

---

## 核心原则 24：并发加锁选型 —— .NET 落地

- **P0 进程内锁（首选）**：同步临界区用 `lock (obj)`（即 `Monitor`）；**异步临界区用 `SemaphoreSlim.WaitAsync()`**。⚠️ **`lock` 块内严禁 `await`**（C# 语法层面即禁止），异步场景一律 `SemaphoreSlim`；`ReaderWriterLockSlim` 用于读多写少。
- **P1 Redis 分布式锁**：`StackExchange.Redis` 的 `LockTakeAsync(key, token, ttl)` / `LockReleaseAsync`（内置 token 校验，**推荐**）；或 `RedLock.net`（自带续期）。
- **P2 数据库级锁**：`SELECT ... FOR UPDATE` / SQL Server `sp_getapplock` / EF Core 原生 SQL 悲观锁。⚠️ **默认不可用，必须人为确认**（见检查项 32）。
- **乐观锁不算锁**：EF Core `[Timestamp]` / `IsConcurrencyToken()` 属无锁并发控制，不受 P2 约束、仍推荐。

---

## 五、本栈不适用

`@Profile`/`@RefreshScope`/MyBatis TypeHandler 为 Spring 生态概念。前端侧见 `stack-vue.md` / `stack-react.md`。
