# Kotlin 设计落地细则（Ktor / Spring Boot Kotlin）

> 技术栈选定为 Kotlin（或探测到 `*.kt` + `build.gradle.kts`）时加载。跨技术栈通用原则见 `../SKILL.md`，选型候选见 `tech-stack-options.md`。

---

## 一、核心原则 16：HTTP 客户端配置驱动 —— Kotlin 落地

| 场景 | 落地方式 |
| :- | :- |
| **Ktor 项目** | Ktor Client（原生协程，多引擎 CIO/OkHttp/Apache），与 Ktor 服务端共享序列化配置 |
| **Spring Boot Kotlin 项目** | **同 Java 路径**（OpenFeign 等），落地细则见 `stack-java-spring.md` §一 |

```kotlin
// ✅ 配置驱动（Ktor）
val client = HttpClient(CIO) {
    defaultRequest { url(config.property("thirdParty.alipay.baseUrl").getString()) }
    install(HttpTimeout) { requestTimeoutMillis = config.timeoutMs }
}
```

配置写 `application.conf`（Ktor HOCON）或 `application.yml`（Spring Boot Kotlin）；**严禁**硬编码 base URL / 凭证。

### 失败返回契约（Critical）

三选一并全链路统一。Kotlin 可用 `Result<T>` / sealed class 表达失败态；**严禁** `runCatching { }.getOrDefault(emptyList())` 把故障静默降级为空集合。

---

## 二、检查项 11：字典/枚举 —— Kotlin 侧

`enum class OrderStatus(val code: Int, val label: String, val description: String)`，文件路径 `src/main/kotlin/com/{project}/enums/OrderStatus.kt`。数据库映射：Spring Boot Kotlin 走 JPA `@Convert` / MyBatis `TypeHandler`（同 Java）；Exposed 用 `enumerationByName`。

常量名 `UPPER_SNAKE_CASE`；code/label 须与前端一致。

---

## 三、其余项

包组织规范、配置文件位置、后端 mock 运行时开关、审计字段填充机制——**Spring Boot Kotlin 项目一律沿用 `stack-java-spring.md` 的对应章节**；Ktor 项目按 Ktor 惯例在 A.1 明确模块划分。

---

## 核心原则 24：并发加锁选型 —— Kotlin 落地

- **P0 进程内锁（首选）**：协程场景用 `kotlinx.coroutines.sync.Mutex`（`mutex.withLock { }`，**挂起而不阻塞线程**）；阻塞线程场景沿用 Java 的 `ReentrantLock`。⚠️ **协程内严禁用 `synchronized`/`ReentrantLock`**——会阻塞整个调度线程，且在挂起点持锁易死锁。
- **P1 Redis 分布式锁**：Spring Boot Kotlin 走 Java 侧 Redisson `RLock`（见 `stack-java-spring.md` 同节）；Ktor 无内置方案，用 Lettuce 协程 API 执行 `SET key val NX PX ttl` + Lua 校验 owner 释放。
- **P2 数据库级锁**：同 Java 侧，⚠️ **默认不可用，必须人为确认**（见检查项 32）。
- 其余判据（严禁两步加锁、锁与事务边界、乐观锁不算锁）与 Java 侧一致，不重复。
