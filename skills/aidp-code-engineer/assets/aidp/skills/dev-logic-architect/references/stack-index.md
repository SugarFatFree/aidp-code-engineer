# 技术栈设计细则 · 按需加载索引

> **为什么拆**：本 SKILL 的**跨技术栈通用**设计原则（模块结构、字段对账、ER 与外键、缓存确认、上游溯源、审计字段语义等）写在 `SKILL.md`；**语言/框架专有的落地细则**（HTTP 客户端 Bean 写法、枚举类文件路径与 ORM 映射、mock 运行时开关写法、包组织规范、DB 方言约束）拆在本目录 `stack-*.md`。设计 Agent **选定技术栈后，只加载命中的那 1~2 份**，不要全量读。

## ⚠️ 与 `tech-stack-options.md` 的分工（重要，别搞反）

| 文件 | 阶段 | 加载方式 |
| :- | :- | :- |
| `tech-stack-options.md`（**选型表**） | **选型期**——用户尚未选定技术栈 | **必须全量加载**。此时无从"探测技术栈"，用户正是要看到全部候选才能选；按语言拆开会让选型无法进行 |
| 本目录 `stack-*.md`（**落地细则**） | **设计期**——技术栈已选定 | **按已选技术栈加载 1~2 份**，其余不读 |

> 换句话说：**选型表是"给用户看菜单"，落地细则是"照选定的菜做菜"**。前者不能拆、后者必须拆。

## 第一步：确定已选技术栈

优先取 **Step 3/Step 2 选型结果**（用户已确认的技术栈）；若是对既有项目做设计（沿用现有栈），按下表探测代码仓：

| 探测信号（任一命中） | 技术栈 | 加载文件 |
| :- | :- | :- |
| `*.java` + `pom.xml` / `build.gradle` | Java / Spring | `stack-java-spring.md`；**核心原则 24 并发加锁的 Java 落地**（`synchronized`/`ReentrantLock` → Redisson `RLock` → `FOR UPDATE`，含锁与 `@Transactional` 边界坑） |
| `*.kt` + `build.gradle.kts` | Kotlin | `stack-kotlin.md`；核心原则 24 协程 `Mutex`（禁在协程内用 `synchronized`） |
| `go.mod` | Go | `stack-go.md`；核心原则 24 `sync.Mutex`/`singleflight` 与自建看门狗续期 |
| `requirements.txt` / `pyproject.toml` + `*.py` | Python | `stack-python.md`；核心原则 24 `threading.Lock`/`asyncio.Lock`，**多 worker 部署下进程内锁失效**这一 Python 特有陷阱 |
| `package.json` 依赖含 `express`/`koa`/`@nestjs/core` | Node.js | `stack-nodejs.md`；核心原则 24 异步互斥（`async-mutex`）与 cluster/多副本下须升 P1 |
| `*.csproj` / `*.sln` | .NET | `stack-dotnet.md`；核心原则 24 `lock` vs `SemaphoreSlim`（异步临界区禁用 `lock`） |
| `*.vue`，或 `package.json` 依赖含 `vue` | 前端 Vue | `stack-vue.md`；核心原则 24 本栈不适用（前端防重复提交不能替代后端加锁） |
| `*.jsx`/`*.tsx`，或 `package.json` 依赖含 `react` | 前端 React | `stack-react.md`；核心原则 24 本栈不适用 |
| 选型/既有库为 MySQL 系 | MySQL 方言 | `stack-db-mysql.md`；**核心原则 24 的 P2 数据库级锁 MySQL 侧识别清单**（`FOR UPDATE`/`LOCK TABLES`/`GET_LOCK` 的锁定范围与典型坑，默认不可用须人为确认） |

前后端分离项目通常**同时命中 1 个后端栈 + 1 个前端栈 + 1 个 DB 方言**。

## 第二步：各文件覆盖什么

> 📌 **本表与各 `stack-*.md` 内的「检查项 N」「维度 N」一律指 `quality-review-checklist.md` 的编号（35 项）**，
> **不是** `SKILL.md` 作者侧工程自检清单的「自检 N」（27 项）。两者是不同清单、**编号不可换算**
> （偏移遍布 −16 ~ +8，还有一对多与多对一），换算一律查 `references/flow-self-check.md`「① 与 ② 不可换算」的映射表。
> 最常被误判的一处：各栈文件里的**检查项 11「字典/枚举」= `SKILL.md` 的自检 12**。

| 文件 | 覆盖内容 |
| :- | :- |
| `stack-java-spring.md` | 核心原则 16 HTTP 客户端落地（Spring Cloud 服务发现 / 单体直连）；检查项 11 枚举类的 Java 侧（类路径、MyBatis `TypeHandler` / JPA `@Convert`）；包组织规范（分层优先）；配置文件位置 `src/main/resources/`；核心原则 14 后端 mock 的 `@Profile` 构建期反模式；审计字段填充机制（MyBatis-Plus `MetaObjectHandler` 等） |
| `stack-kotlin.md` | HTTP 客户端（Ktor Client 协程 / Spring Boot Kotlin 走 Java 路径）；枚举与配置沿用 Java 侧约定的差异点 |
| `stack-go.md` | HTTP 客户端（Go-Zero zrpc+httpx 与 etcd/consul / Gin·Echo·Fiber 走 net/http+resty）；枚举常量组织方式；配置 `config.yaml` |
| `stack-python.md` | HTTP 客户端（FastAPI 异步首选 httpx / Django 同步用 requests）；枚举 `enum.Enum` 与 ORM 映射；配置 `.env` |
| `stack-nodejs.md` | HTTP 客户端（NestJS axios + ConfigService / Node 18+ 原生 fetch）；枚举 TS 侧定义；配置 `.env` |
| `stack-dotnet.md` | HTTP 客户端（`IHttpClientFactory` 工厂模式避免 socket 耗尽 / gRPC 走 `Grpc.Net.Client`）；配置 `appsettings.json` |
| `stack-vue.md` | 检查项 11 前端枚举（TS `enum` / `as const`）文件路径约定；核心原则 14 前端 mock 运行时环境变量写法（Vite） |
| `stack-react.md` | 同上，按 React / CRA·Next 环境变量视角 |
| `stack-db-mysql.md` | MySQL 方言专有约束：`NULL != NULL` 唯一索引语义、`utf8mb4` 下 `VARCHAR(N)` 按字符计、InnoDB 单行 65535 字节上限、`CHARACTER SET`/`COLLATE`/引擎沿用 |

## 约束

- 各 `stack-*.md` **只写该技术栈专有的落地写法与约束**，不重复 `SKILL.md` 的通用原则（为什么要配置驱动、字段对账口径、缓存需用户确认等）。
- 某栈无对应规则的项，明确写「本栈不适用」而非留空。
- 本目录文件**不得跨 SKILL 引用**（每个 SKILL 自包含，允许各自有重复内容）。
