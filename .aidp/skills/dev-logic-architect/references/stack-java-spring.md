# Java / Spring 设计落地细则

> 技术栈选定为 Java/Spring（或既有项目探测到 `*.java` + `pom.xml`/`build.gradle`）时加载。跨技术栈的通用原则见 `../SKILL.md`，选型候选见 `tech-stack-options.md`（选型期全量看），此处只写**选定后**的 Java/Spring 专有落地写法。

---

## 一、核心原则 16：HTTP 客户端配置驱动 —— Java 落地

### 1.1 场景选型（已在 Step 3 选择 3 选定客户端后，按部署形态落地）

| 场景 | 落地方式 |
| :- | :- |
| **Java + Spring Cloud 微服务** | OpenFeign + Nacos Discovery，通过 `@FeignClient(name = "user-service")` **走服务发现**（不写 IP/端口）；非 Spring Cloud 场景可选 OkHttp / RestClient / `@HttpExchange`，直连配置文件 base URL |
| **Java + 单体应用** | OpenFeign 也支持 `@FeignClient(name = "alipayClient", url = "${third-party.alipay.base-url}")` **直连第三方 base URL**，无需引入 Spring Cloud |

### 1.2 A.2「HTTP 客户端落地」子章节必须给出

1. **Bean / Client 初始化示例**（如 `@FeignClient` 接口声明、`RestClient.Builder` Bean 配置）
2. **`application.yml` 配置块**，所有可变项走 `${ENV_VAR}` 占位符：

```yaml
third-party:
  alipay:
    base-url: ${ALIPAY_BASE_URL}
    app-id: ${ALIPAY_APP_ID}
    connect-timeout: ${ALIPAY_CONNECT_TIMEOUT:3000}
    read-timeout: ${ALIPAY_READ_TIMEOUT:10000}
```

3. **D.3 依赖列表对齐**：所选客户端的 Maven/Gradle 依赖必须列出（如 OpenFeign 列 `spring-cloud-starter-openfeign`）。

### 1.3 严禁的写法

```java
// ❌ 硬编码 base URL / IP / 端口
@FeignClient(name = "x", url = "http://192.0.2.100:8080")
// ❌ 凭证明文
private static final String APP_ID = "2021004100000000";
```

> 配置项强制走配置：第三方 base URL / IP / 端口、API Key / Secret / 私钥、连接超时 / 读超时 / 重试次数 / 熔断阈值、mock 与降级开关。

### 1.4 失败返回契约（Critical·跨栈原则的 Java 落地）

同一调用链的失败返回必须**三选一并全链路统一**：抛异常 / 带 `_error` 标记 / `Optional`·空。**严禁**「吞异常返裸空（`new HashMap<>()`）」与「带 `_error` 标记」两种失败风格混用——会让系统故障被静默降级为空数据，且调用方无法区分于业务真空。

```java
// ❌ 吞异常返裸空：调用方以为"没数据"，实际是下游挂了
catch (Exception e) { log.error("...", e); return new HashMap<>(); }

// ✅ 抛异常（推荐，交由全局异常处理器统一转错误码）
catch (FeignException e) { throw new ThirdPartyException("ALIPAY_UNAVAILABLE", e); }
// ✅ 或显式错误态，调用方可判别
return Result.partial(data, "ALIPAY_TIMEOUT");
```

---

## 二、检查项 11：字典/枚举强制生成枚举类 —— Java 侧

A.4 中**每一个**字典/枚举条目，Java 侧必须声明：

| 项 | Java 取值 |
| :- | :- |
| 后端枚举类名 | PascalCase + `Enum` 后缀，如 `OrderStatusEnum`、`PaymentMethodEnum` |
| 后端枚举类文件路径 | `src/main/java/com/{project}/enums/OrderStatusEnum.java` |
| 数据库映射方式 | MyBatis `TypeHandler` / JPA `@Convert`（二选一，须显式声明） |
| Mapper/ORM 引用 | MyBatis `OrderStatusEnumTypeHandler` / JPA `OrderStatusConverter` |

每个枚举常量含 `code` / `label` / `description` 三个必备字段（状态类追加 `color`），常量名 `UPPER_SNAKE_CASE`。A.3 数据表中枚举字段的 `COMMENT` 须引用对应枚举类（如 `参考 OrderStatusEnum`）。

> **不允许例外**：即便枚举只有 2 个候选值（如 `启用/停用`），也必须生成枚举类，**严禁**业务代码中以裸字符串/裸数字硬编码。前端侧枚举定义见 `stack-vue.md` / `stack-react.md`，二者的 code/label 必须一致。

---

## 三、包组织规范（Java / Spring Boot 项目）

项目结构采用「**分层优先**」的包组织方式：

```
com.{company}.{project}
├── controller/     ├── service/  (+ impl/)
├── mapper/ 或 repository/        ├── entity/ 或 domain/
├── dto/  ├── vo/    ├── enums/   ├── config/  ├── common/
```

设计文档须在 A.1/A.2 明确该结构，避免各模块各自为政。

---

## 四、配置文件位置与历史沿用

- Spring Boot 项目配置文件**优先使用 `src/main/resources/`**（`application.yml` / `application-{profile}.yml`）。
- 对既有项目做设计时，历史目录探测优先级：含版本号子目录 > 文件数最多的目录；无历史时默认建议 `src/main/resources/`。

---

## 五、核心原则 14：后端第三方 mock 的运行时可控

```java
// ❌ 构建期隔离：prod profile 部署后 mock 类不加载
@Service @Profile("dev")
public class AlipayServiceMockImpl implements AlipayService { ... }

// ✅ 运行时配置开关
@Value("${third-party.mock.enabled}")
private boolean mockEnabled;
```

同类反模式：`@Profile("!prod")`、`#if DEBUG`、**Maven Profile 条件编译**。设计 B.7 须为每个未交付的第三方接口标注 mock 位置；**P0 前端 mock 首选**（第三方接口仅供前端调用时），**P1 后端 mock 次选**（仅当接口供后端服务端调用，如服务端鉴权、银行代扣、报关推送）。

---

## 六、核心原则 22：审计字段填充机制（Java 落地）

业务实体表审计四件套（`create_by`/`create_time`/`update_by`/`update_time`）取**当前登录操作人 + 当前时间**，**禁写死 `"system"`**。设计须**显式声明填充机制与操作人来源**：

| 填充机制 | 声明内容 |
| :- | :- |
| MyBatis-Plus | 实现 `MetaObjectHandler`，操作人取自 `SecurityContext` / JWT `sub`（须写明取哪个） |
| JPA | `@CreatedBy`/`@LastModifiedBy` + `AuditorAware<String>` 实现类 |
| 手动 Service 层填充 | 写明在哪一层统一填充 |

> ⚠️ **逻辑删除必须同步 `update_by`/`update_time`**：MyBatis-Plus `@TableLogic` 默认删除与自定义 UPDATE 语句会**绕过**自动填充，是高频漏点，设计须显式说明如何补。

---

## 核心原则 24：并发加锁选型 —— Java 落地

| 档位 | Java 写法 | 适用 |
| :-: | :- | :- |
| **P0 进程内锁（首选）** | `synchronized` 方法/块；`ReentrantLock`（可中断/超时 `tryLock(t)`）；`ReentrantReadWriteLock`（读多写少）；`StampedLock`（乐观读） | 竞争只在**单 JVM 进程内** |
| **P1 Redis 分布式锁** | Redisson `RLock`（`tryLock(waitTime, leaseTime, unit)`，**自带看门狗续期**，推荐）；或 `StringRedisTemplate` 执行 `SET key val NX PX ttl` + Lua 校验 owner 释放 | 多实例/多副本部署、跨进程或跨服务竞争。**须写明为何 P0 不够** |
| **P2 数据库级锁** | `SELECT ... FOR UPDATE`（MyBatis/JPA `@Lock(PESSIMISTIC_WRITE)`）、`LOCK TABLES`、`GET_LOCK()` | ⚠️ **默认不可用，必须人为确认**（见检查项 32） |

- **严禁两步加锁**：`setIfAbsent(k,v)` 后再 `expire(k,t)` —— 中间崩溃即永久死锁。必须 `setIfAbsent(k, v, ttl, unit)` 单次原子调用，或直接用 Redisson。
- **严禁 `synchronized` 跨实例当分布式锁用**：多副本部署下它只锁住本 JVM，是典型误用。
- **锁与事务边界**：`@Transactional` 方法上加 `synchronized` **无效防并发**——锁在事务提交**前**释放，其它线程读到旧数据。须把锁提到事务外层（锁 → 开事务 → 提交 → 解锁）。
- **乐观锁不算锁**：MyBatis-Plus `@Version` / JPA `@Version` + CAS 重试属无锁并发控制，不受 P2 约束、仍推荐。

---

## 七、本栈不适用

前端枚举定义方式、前端 mock 环境变量写法见 `stack-vue.md` / `stack-react.md`；DB 方言约束见 `stack-db-mysql.md`（若选型为 MySQL 系）。
