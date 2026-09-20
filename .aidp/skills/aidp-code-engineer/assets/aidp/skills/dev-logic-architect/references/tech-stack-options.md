# Tech Stack Options（技术选型选项表）

> 本文件隶属于 `dev-logic-architect` SKILL，供 SKILL.md 的 Phase 1（技术边界确认）阶段引用。
> 上级文档：`../SKILL.md`
>
> **使用说明：** Agent 执行 Phase 1 时必须读取本文件，按 Step 1 → Step 6 顺序向用户展示选项并收集选择，最终按"确认汇总"模板汇总。
>
> **⚠️ Phase 1 四条铁律（对应 SKILL.md 核心原则 4「用户主权」，执行 Agent 不得图省事跳步或推断）：**
> 1. **禁止推断/静默补全** — 凡要写进详细设计的每一项技术（ORM / 连接池 / 序列化 / 后端 WS·SSE 服务端 / HTTP 客户端 / 数据库 / 缓存 / MQ 等），用户没显式选过的，必须先作为 ⭐ 推荐项弹出确认/改选，**严禁从已选语言/框架/原型静默采用**。
> 2. **打包项透明化** — 见 Step 3「⚠️ 打包项透明化」：打包项隐含子决策（ORM/构建工具）必须回显确认，未覆盖的配套维度（连接池/序列化/后端实时通信服务端）必须补充独立询问。
> 3. **数据库必确认** — 见 Step 4：数据库始终执行、由用户确认，不得跳过或从框架默认推断。
> 4. **完成门（唯一闸门）** — 全部适用 Step 收集完 + 「确认汇总」经用户 accept 之前，禁止输出"技术栈确定/已定"、禁止进入 Phase 2 生成设计。

---

## Step 1: 开发范畴 (Scope)（1 次选择）

根据 Phase 0 的终端分析结果，动态展示选项：

**当原型为 Web 端时：**

| 选项 | 范畴 | 说明 |
|------|------|------|
| A | 仅前端 (Web) | 只涉及 Web UI 层 |
| B | 仅后端 | 只涉及 API 服务、数据库 |
| C | 全栈 (Web) | Web 前端 + 后端 |

**当原型包含移动端时（额外展示）：**

| 选项 | 范畴 | 说明 |
|------|------|------|
| D | 仅移动端 | 只涉及移动端 App / 小程序 |
| E | 全栈 (Web + 移动端) | Web 前端 + 移动端 + 后端 |
| F | 移动端 + 后端 | 移动端 + 后端（无 Web） |

---

## Step 2: 客户端技术栈（当 Scope 包含客户端时）（2 次选择）

根据终端类型展示对应的技术组合。

### 选择 1：客户端技术组合

**Web 前端组合：**

| 选项 | 组合名称 | 包含内容 |
|------|---------|---------|
| A | Vue 3 + Element Plus | JS + Vue 3 + Element Plus + Pinia + Sass/SCSS + Vite |
| B | Vue 3 + Ant Design Vue | JS + Vue 3 + Ant Design Vue + Pinia + Less + Vite |
| C | Vue 3 + Naive UI | TS + Vue 3 + Naive UI + Pinia + Tailwind CSS + Vite |
| D | Vue 3 + Arco Design | TS + Vue 3 + Arco Design Vue + Pinia + Less + Vite |
| E | React + Ant Design | TS + React 18 + Ant Design + Zustand + Less + Vite |
| F | React + MUI | TS + React 18 + MUI + Redux Toolkit + CSS Modules + Vite |
| G | React + Shadcn/ui | TS + React 18 + Shadcn/ui + Zustand + Tailwind CSS + Vite |
| H | Next.js 全栈 | TS + Next.js + Shadcn/ui + Zustand + Tailwind CSS + Next内置 |
| I | Nuxt 3 全栈 | TS + Nuxt 3 + Element Plus + Pinia + Tailwind CSS + Nuxt内置 |
| J | Angular + Material | TS + Angular + Angular Material + NgRx + Sass + Angular CLI |
| K | 自定义组合 | 请分别指定：语言、框架、UI组件库、状态管理、CSS方案、构建工具 |

**移动端组合（仅当终端包含移动端时展示）：**

| 选项 | 组合名称 | 包含内容 | 适用平台 |
|------|---------|---------|---------|
| M1 | Flutter + Material | Dart + Flutter + Material Design + Riverpod + Flutter CLI | Android / iOS / HarmonyOS |
| M2 | uni-app + Vue | JS/TS + uni-app + uni-ui + Vuex/Pinia + HBuilderX | Android / iOS / 微信小程序 / H5 |
| M3 | React Native + Paper | TS + React Native + React Native Paper + Zustand + Expo | Android / iOS |
| M4 | 微信小程序原生 | JS/TS + 微信小程序原生框架 + Vant Weapp | 微信小程序 |
| M5 | Taro + React | TS + Taro + NutUI + Zustand | 微信小程序 / H5 / React Native |
| M6 | Android 原生 | Kotlin + Jetpack Compose + Hilt + Gradle | Android |
| M7 | iOS 原生 | Swift + SwiftUI + Combine + SPM | iOS |
| M8 | HarmonyOS 原生 | ArkTS + ArkUI + Stage Model + DevEco Studio | HarmonyOS NEXT |
| M9 | 自定义组合 | 请分别指定 | — |

> 如果 Scope 同时包含 Web 和移动端，需分别选择 Web 组合和移动端组合（仍为 1 次选择，格式：`Web: A + 移动端: M2`）。

### 选择 2：客户端通用能力（可多选）

| 选项 | 能力 | 推荐技术 |
|------|------|---------|
| A | 国际化 (i18n) | vue-i18n / react-intl / flutter_intl |
| B | 图表可视化 | ECharts |
| C | 富文本编辑器 | WangEditor |
| D | 文件上传 | vue-upload-component（分片+断点续传） |
| E | WebSocket 实时通信 | socket.io-client |
| F | 微前端 | qiankun |
| G | PWA 支持 | vite-plugin-pwa |
| H | SSR/SSG | Nuxt 3 / Next.js |
| I | 暗黑模式 | Element Plus 内置 / CSS 变量方案 |
| J | 表单引擎 | form-create |
| K | 拖拽功能 | VueDraggablePlus |
| L | PDF 预览/导出 | vue-pdf-embed + jsPDF |
| M | Excel 导入/导出 | ExcelJS |
| N | 地图 | 高德地图 / Mapbox |
| O | 视频播放 | video.js / DPlayer |
| P | 扫码/摄像头 | html5-qrcode（Web）/ 原生相机（移动端） |
| Q | 消息推送 | 极光推送 / Firebase FCM（移动端） |
| R | 无需额外能力 | — |
| S | 其他 | 请说明 |

---

## Step 3: 后端技术栈（当 Scope 包含后端时）（3 次选择）

### 选择 1：后端核心组合

| 选项 | 组合名称 | 包含内容 |
|------|---------|---------|
| A | Spring Boot 标准版 | Java + Spring Boot 3 + MyBatis-Plus + Maven |
| B | Spring Boot + JPA | Java + Spring Boot 3 + JPA/Hibernate + Maven |
| C | Spring Cloud 微服务 | Java + Spring Cloud + MyBatis-Plus + Maven |
| D | Go + Gin | Go + Gin + GORM + Go Modules |
| E | Go-Zero 微服务 | Go + Go-Zero + Ent + Go Modules |
| F | Python + FastAPI | Python + FastAPI + SQLAlchemy + Poetry |
| G | Python + Django | Python + Django + Django ORM + pip |
| H | Node.js + NestJS | TypeScript + NestJS + Prisma + pnpm |
| I | Node.js + Express | TypeScript + Express + TypeORM + pnpm |
| J | Kotlin + Ktor | Kotlin + Ktor + Exposed + Gradle |
| K | .NET Core | C# + ASP.NET Core + EF Core + dotnet CLI |
| L | 自定义组合 | 请分别指定：语言、框架、ORM、构建工具 |

> **⚠️ 打包项透明化（防"选一个 = 一揽子被决定"，对应核心原则 4 ②）：** 上表每个选项把「语言 + 框架 + ORM + 构建工具」打包进一个标签，用户选一个 ≠ 后端栈全定。选定打包项后 Agent **必须**：
> - **① 回显隐含子决策让用户确认/改选** — 把该打包项隐含的 **ORM、构建工具**显式列出（如选 J `Kotlin + Ktor` → ORM=Exposed、构建=Gradle），标 ⭐ 为默认推荐，明确告知"可改选"，而非静默写死；
> - **② 补询打包项未覆盖、但本设计确需的配套维度** — 至少覆盖 **连接池、序列化方案、后端 WebSocket/SSE 服务端支持**三项（HTTP 客户端已由本 Step 选择 3 单独确认），每项以 ⭐ 推荐 + 备选形式让用户拍板，**严禁从框架默认静默补全**。常见默认（仅作 ⭐ 推荐起点，须经用户确认）：
>
> | 打包项 | ORM（可改） | 构建工具 | 连接池 ⭐ | 序列化 ⭐ | 后端 WS/SSE 服务端 ⭐ |
> |------|-----------|---------|----------|----------|---------------------|
> | A/B/C Spring Boot 系 | MyBatis-Plus / JPA | Maven | HikariCP | Jackson | Spring WebSocket / SSE(`SseEmitter`) |
> | D/E Go 系 | GORM / Ent | Go Modules | database/sql 连接池(内置) | encoding/json | gorilla/websocket / SSE(`http.Flusher`) |
> | F/G Python 系 | SQLAlchemy / Django ORM | Poetry / pip | SQLAlchemy pool / DB 连接池 | pydantic / DRF serializer | websockets / starlette SSE |
> | H/I Node 系 | Prisma / TypeORM | pnpm | 驱动内置连接池 | class-transformer / JSON | ws / socket.io / SSE |
> | J Kotlin + Ktor | Exposed | Gradle | HikariCP | kotlinx.serialization | Ktor WebSockets / SSE |
> | K .NET | EF Core | dotnet CLI | 驱动内置连接池 | System.Text.Json | SignalR / SSE |
> | L 自定义 | 用户指定 | 用户指定 | 逐项询问 | 逐项询问 | 逐项询问 |
>
> - **③ 若本设计不需要某配套维度**（如无实时通信需求则无需 WS/SSE 服务端），Agent 应说明"本项目无此需求，不引入"并让用户确认，而非静默省略或静默引入。
> - 选 **L 自定义组合**时，语言/框架/ORM/构建/连接池/序列化/实时通信须**逐维度问全**，无默认可套。

### 选择 2：后端通用能力（可多选）

| 选项 | 能力 | 推荐技术 |
|------|------|---------|
| A | 文件存储 | MinIO |
| B | 全文搜索 | Elasticsearch 8 |
| C | 定时任务 | XXL-Job |
| D | 分布式事务 | Seata |
| E | 日志收集 | ELK (Elasticsearch + Logstash + Kibana) |
| F | 链路追踪 | SkyWalking |
| G | 限流熔断 | Sentinel |
| H | 配置中心 | Nacos |
| I | 服务注册发现 | Nacos |
| J | 网关 | Spring Cloud Gateway |
| K | 短信通知 | 阿里云短信 SDK |
| L | 邮件通知 | Spring Boot Mail |
| M | 导入导出 | EasyExcel |
| N | 工作流引擎 | Flowable |
| O | 数据权限 | 自研行级/列级拦截器 |
| P | 操作日志审计 | 自研 AOP 切面 |
| Q | 无需额外能力 | — |
| R | 其他 | 请说明 |

### 选择 3：HTTP 客户端 / 服务间调用方案

**用途**：后端发起外部 HTTP 请求(对接第三方接口、调用其他微服务、聚合远程数据等)。**根据 Step 3 选择 1 选定的后端语言,Agent 仅展示对应语言的选项**;若选 1 为"自定义组合",则全部展示。

> 📎 **落地引用**:用户选定后,Agent 必须在详细设计中按以下两个章节落地。模板与示例参见 `output-module-examples.md`:
> - **A.2 基础框架配置 > HTTP 客户端落地** — Bean 初始化示例 + `application.yml`/`.env` 配置块 + `${ENV_VAR}` 占位符规范
> - **B.7 外部依赖与集成方案** — 每个第三方集成必须标注所选 HTTP 客户端 + 服务发现集成方式 + 配置文件位置

#### Java 系(Spring Boot / Spring Cloud)

| 选项 | 方案 | 说明 |
|------|------|------|
| J-A | **OpenFeign** | ⭐ **默认推荐**。声明式 HTTP 客户端,与 Spring Cloud 生态深度集成,支持与 Nacos 服务注册发现/Sentinel 熔断/Ribbon 负载均衡组合;也可通过 `@FeignClient(url = "...")` 直接指定 IP 端口或读取配置文件调用,适用于微服务和单体场景 |
| J-B | OkHttp | 轻量同步 HTTP 客户端,API 简洁,连接池/拦截器机制成熟,适合纯 HTTP 调用无服务发现需求 |
| J-C | Spring WebFlux WebClient | 响应式非阻塞客户端,适合高并发/流式场景(SSE/大文件流) |
| J-D | RestTemplate | Spring 经典同步客户端,Spring 5.0 起进入维护模式但仍广泛使用,适合简单同步调用 |
| J-E | RestClient (Spring 6+) | Spring 6 / Spring Boot 3.2+ 新增的同步客户端,API 设计取代 RestTemplate(流式调用),响应式版为 WebClient |
| J-F | @HttpExchange (Spring 6+) | Spring 6 声明式 HTTP 接口,通过 `HttpServiceProxyFactory` 绑定 RestClient/WebClient,无 Spring Cloud 依赖即可获得类 Feign 体验 |
| J-G | Apache HttpClient 5 | 老牌 HTTP 客户端,功能全面,定制化能力强,适合需要精细控制 HTTP 协议的场景 |
| J-H | Retrofit | Square 出品的声明式客户端,Android 同源,API 风格类似 Feign 但无 Spring Cloud 集成 |
| J-I | 其他 | 请说明 |

#### Go 系(Gin / Go-Zero / Echo / Fiber)

| 选项 | 方案 | 说明 |
|------|------|------|
| G-A | **net/http(标准库)** | ⭐ **默认推荐**。Go 标准库自带,零依赖,性能优秀;配合 `httputil.ReverseProxy` 可做反向代理 |
| G-B | go-resty/resty | 链式 API 风格的 HTTP 客户端,封装了重试/超时/中间件,使用便捷 |
| G-C | go-zero zrpc + httpx | Go-Zero 微服务框架内置 HTTP/RPC 客户端,与服务发现(etcd/consul)深度集成 |
| G-D | hashicorp/go-retryablehttp | 自带重试机制,适合对稳定性要求高的场景 |
| G-E | imroc/req | 易用的 HTTP 客户端库,DevOps/调试场景流行 |
| G-F | 其他 | 请说明 |

#### Python 系(FastAPI / Django / Flask)

| 选项 | 方案 | 说明 |
|------|------|------|
| P-A | **httpx** | ⭐ **默认推荐**。同时支持同步/异步,API 类似 requests,FastAPI 异步生态首选 |
| P-B | requests | 老牌同步 HTTP 客户端,API 简洁,适合脚本和 Django 同步场景 |
| P-C | aiohttp | 纯异步 HTTP 客户端/服务端,适合高并发异步爬虫和后端聚合 |
| P-D | urllib3 | 底层 HTTP 库,requests/httpx 的依赖,直接使用场景较少 |
| P-E | 其他 | 请说明 |

#### Node.js 系(NestJS / Express / Koa)

| 选项 | 方案 | 说明 |
|------|------|------|
| N-A | **axios** | ⭐ **默认推荐**。前后端通用,Promise API,拦截器/超时/取消机制完善;NestJS 内置 `@nestjs/axios` 模块 |
| N-B | 原生 fetch (Node 18+) | Node 18+ 内置 Fetch API,无需依赖,适合简单调用 |
| N-C | got | TypeScript 友好,流式 API,功能丰富,Sindre Sorhus 维护 |
| N-D | undici | Node.js 官方实验性 HTTP 客户端,性能最优,fetch 底层实现 |
| N-E | node-fetch | fetch API 的 Node 实现,广泛兼容旧版 Node |
| N-F | 其他 | 请说明 |

#### .NET 系

| 选项 | 方案 | 说明 |
|------|------|------|
| NET-A | **HttpClient + IHttpClientFactory** | ⭐ **默认推荐**。.NET Core 内置,IHttpClientFactory 解决了 socket 耗尽问题,推荐通过依赖注入使用 |
| NET-B | RestSharp | 高级封装,链式 API,序列化便捷 |
| NET-C | Refit | 声明式客户端,接口定义即调用,类似 Java OpenFeign |
| NET-D | Flurl.Http | 流式 API 风格,易读性高 |
| NET-E | 其他 | 请说明 |

#### Kotlin 系(Ktor / Spring Boot Kotlin)

| 选项 | 方案 | 说明 |
|------|------|------|
| K-A | **Ktor Client** | ⭐ **默认推荐**(Ktor 项目)。原生协程支持,多引擎(CIO/OkHttp/Apache),与 Ktor 服务端共享序列化配置 |
| K-B | OpenFeign | (Spring Boot Kotlin 项目)同 Java 默认推荐 |
| K-C | OkHttp + 协程扩展 | 复用 Java 生态,通过 retrofit2-kotlin-coroutines 添加协程支持 |
| K-D | 其他 | 请说明 |

> **配置文件支持(强制声明)**：所选方案必须在详细设计 A.2 基础框架配置章节中明确以下内容,**严禁**硬编码到代码中：
> - 第三方目标服务的 base URL / IP / 端口 / 超时配置 → 写入 `application.yml`(Java/Kotlin) / `config.yaml`(Go) / `.env`(Python/Node) / `appsettings.json`(.NET);敏感凭证使用占位符 `${ENV_VAR}` 引用环境变量
> - 与服务注册发现(Nacos/Eureka/Consul/etcd)集成时,声明服务名 + 命名空间 + 分组,直接通过服务名调用,无需写死 IP
> - 默认超时(连接/读写)、重试次数、熔断阈值在配置文件中可调,不写死在代码

---

## Step 4: 数据与中间件（3 次选择，每次选一个维度）

每次选择只选**一个维度**，不要混合。

### 选择 1：数据库

| 选项 | 数据库 | 说明 |
|------|--------|------|
| A | 达梦 (DM8) | ⭐ 国产数据库，信创项目推荐 |
| B | MySQL 8 | 开源主流 |
| C | PostgreSQL | 功能丰富，支持 JSON/GIS |
| D | 人大金仓 (KingbaseES) | 国产数据库，兼容 PostgreSQL |
| E | Oracle | 企业级商业数据库 |
| F | SQL Server | 微软生态 |
| G | TiDB / OceanBase | 分布式数据库 |
| H | SQLite | 嵌入式轻量（移动端本地存储） |
| I | 其他 | 请说明 |

> **⚠️ 数据库必确认（对应核心原则 4，禁跳过/禁框架默认推断）：** 本选择**始终执行、由用户显式确认**，**严禁**因"选了后端框架"就跳过、或从框架默认静默推断数据库（如 Ktor→PostgreSQL、Spring Boot→MySQL、Go-Zero→MySQL）。可用 ⭐ 标推荐（信创项目优先达梦/人大金仓），但落选须由用户拍板。

### 选择 2：缓存方案

> ⚠️ **用户确认必读(对应 dev-logic-architect SKILL 核心原则 17):** 缓存机制属于架构级决策(影响数据一致性、运维成本、雪崩风险),**默认推荐"D 不需要缓存"**。除非用户明确要求引入缓存,**Agent 严禁自作主张选择 A/B/C/E**;若用户犹豫,Agent 应说明缓存利弊并等待用户明确表态后再选。一旦用户选择 A/B/C/E,详细设计 A.2 必须生成「缓存方案」子章节(含 Key 命名规范 / TTL / 一致性策略 / 防护机制 / 监控指标),否则被检查项 23 拦截。

| 选项 | 方案 | 说明 |
|------|------|------|
| A | Redis | 主流分布式缓存(用户主动要求时推荐) |
| B | Redis Cluster | Redis 集群模式,高可用(高并发/数据量大场景,用户主动要求) |
| C | Caffeine | JVM 本地缓存,高性能(单机或低一致性要求场景,用户主动要求) |
| D | 不需要缓存 | ⭐ **默认推荐**,业务无明确性能瓶颈时优先选 |
| E | 多级缓存(Caffeine + Redis) | 本地 + 分布式两级,复杂度高(用户主动要求且能接受运维成本) |
| F | 其他(EhCache / Memcached / Hazelcast 等) | 请说明并提供选型理由 |

### 选择 3：消息队列

| 选项 | 方案 | 说明 |
|------|------|------|
| A | 不需要消息队列 | ⭐ 中小项目推荐 |
| B | RabbitMQ | 轻量可靠，适合中小规模 |
| C | Apache Kafka | 高吞吐，大数据/日志场景 |
| D | RocketMQ | 阿里出品，事务消息好 |
| E | Redis Stream | 轻量消息队列 |
| F | 其他 | 请说明 |

---

## Step 5: 认证、文档与架构（3 次选择，每次选一个维度）

### 选择 1：认证鉴权

| 选项 | 方案 | 说明 |
|------|------|------|
| A | JWT 自研 | 无状态 Token 认证 |
| B | Spring Security + JWT | Java 安全框架集成 |
| C | Sa-Token | 国产轻量权限认证框架 |
| D | OAuth 2.0 / OIDC | ⭐ 标准授权协议(含企业 SSO 统一认证接入) |
| E | CAS 单点登录 | 中心化认证 |
| F | Keycloak | 开源身份管理 |
| G | 其他 | 请说明 |

### 选择 2：API 文档

| 选项 | 方案 | 说明 |
|------|------|------|
| A | Knife4j | ⭐ Swagger 增强 UI（Java 项目推荐） |
| B | Swagger / SpringDoc | OpenAPI 规范 |
| C | Apifox / Postman | 独立 API 管理工具 |
| D | 手写文档 (Markdown) | — |
| E | 其他 | 请说明 |

> 注：Knife4j 仅适用于 Java 项目。非 Java 后端自动调整推荐为 B（Swagger）或 C（Apifox）。

### 选择 3：架构规范

| 选项 | 架构模式 | API 风格 | 复杂度 | 适用场景 |
|------|---------|---------|--------|---------|
| A | 分层架构 (Controller-Service-Repository) | RESTful | 低 | ⭐ 中小型项目，快速交付 |
| B | 分层架构 | GraphQL | 低 | 前端查询灵活 |
| C | DDD 领域驱动设计 | RESTful | 高 | 大型复杂业务，长期演进 |
| D | DDD 领域驱动设计 | gRPC + RESTful | 高 | 微服务，内部gRPC对外REST |
| E | 六边形架构 | RESTful | 中 | 外部组件频繁更换 |
| F | Clean Architecture | RESTful | 中 | 注重可测试性 |
| G | 自定义 | — | — | 请说明 |

---

## Step 6: 服务配置与模块划分（动态步骤，根据 Scope 调整）

本步骤根据 Step 1 选择的开发范畴动态调整，最多 3 次选择。

### 选择 1：前端服务名称（当 Scope 包含前端时）

前端访问地址格式：`http://{ip}:{port}/{前端服务名称}/{页面路由}`

**请指定前端服务名称**（或从推荐中选择）：

根据 PRD 和原型分析，推荐以下服务名称（示例）：
- 若为管理后台：`admin`、`console`、`management`
- 若为用户端：`portal`、`app`、`web`
- 若为特定业务：根据业务名称推荐（如 `ai-platform`、`order-system`）

**要求：**
- 服务名称使用小写字母和连字符（kebab-case）
- 不能与后端服务名称重复
- 建议长度 3-20 字符

### 选择 2：后端服务名称（当 Scope 包含后端时）

后端访问地址格式：`http://{ip}:{port}/{后端服务名称}/{接口路径}`

**请指定后端服务名称**（或从推荐中选择）：

根据 PRD 和后端技术栈，推荐以下服务名称（示例）：
- 单体应用：`api`、`service`、`server`
- 特定业务：根据业务名称推荐（如 `ai-service`、`order-api`）
- 微服务：根据服务职责推荐（如 `user-service`、`product-service`）

**要求：**
- 服务名称使用小写字母和连字符（kebab-case）
- 不能与前端服务名称重复
- 建议长度 3-20 字符

**接口路径说明：**
- 默认不使用 `/api/v1` 等版本号前缀
- 接口路径直接跟在服务名称后：`/{后端服务名称}/{资源路径}`
- 示例：`http://192.0.2.100:9090/order-api/user/login`（服务名 `order-api`，接口路径 `user/login`；**勿把服务名取成 `api` 致出现 `/api/` 前缀,违反核心原则 7**)

### 选择 3：后端模块划分（仅当后端为微服务或多模块时）

**判断依据：**
- Step 3 选择了 Spring Cloud 微服务、Go-Zero 微服务
- 或用户明确表示项目为多模块结构（如 Maven 多 module）

**请确认后端模块划分方案：**

根据 PRD 功能分析，推荐以下模块划分（示例）：

| 模块名称 | 模块职责 | 包含功能 |
|---------|---------|---------|
| user-service | 用户管理 | 用户注册、登录、权限、个人信息 |
| order-service | 订单管理 | 订单创建、支付、查询、退款 |
| product-service | 商品管理 | 商品上架、库存、分类、搜索 |
| common | 公共模块 | 工具类、通用配置、基础实体 |

**要求：**
- 模块名称使用小写字母和连字符（kebab-case）
- 每个模块职责清晰，避免功能交叉
- 公共模块（common/shared）用于存放通用代码
- 用户可以调整模块名称、合并或拆分模块

**输出格式：**
用户确认后，以表格形式呈现最终的模块划分方案，包含：
- 模块名称
- 模块职责（一句话）
- 包含的主要功能点（对应 PRD 功规点编号）
- 对外接口路径前缀（如 `/user`、`/order`）

---

## 确认汇总

所有选项确认完毕后，以表格形式汇总用户的全部选择，请用户做最终确认：

```
## 技术选型汇总确认

| 维度 | 用户选择 |
|------|---------|
| 开发范畴 | ... |
| Web 前端组合 | 语言 + 框架 + UI组件库 + 状态管理 + CSS + 构建工具 |
| 移动端组合 | （如有）语言 + 框架 + UI + 状态管理 + 构建工具 |
| 客户端通用能力 | ... |
| 后端组合 | 语言 + 框架 + ORM + 构建工具（**ORM/构建工具须为回显确认值，非静默默认**） |
| 连接池 | （后端必填）方案名称（用户已确认，非框架默认静默采用） |
| 序列化方案 | （后端必填）方案名称（用户已确认） |
| 后端实时通信服务端 | （后端）WebSocket/SSE 服务端方案，或"本项目无实时通信需求，不引入"（用户已确认） |
| 后端通用能力 | ... |
| HTTP 客户端 / 服务间调用 | （后端必填）方案名称 + 是否结合服务注册发现 |
| 数据库 | ... |
| 缓存 | ... |
| 消息队列 | ... |
| 认证鉴权 | ... |
| API 文档 | ... |
| 架构规范 | 架构模式 + API 风格 |
| 前端服务名称 | （如有）服务名称 + 完整访问地址示例 |
| 后端服务名称 | （如有）服务名称 + 完整访问地址示例 |
| 后端模块划分 | （如有微服务/多模块）模块列表 + 职责 + 接口前缀 |

请确认以上选择是否正确，或告诉我需要调整的项。
```

> **⚠️ 完成门（唯一闸门，对应核心原则 4 ③）：** 本「确认汇总」经用户**最终 accept** 之前，Agent **禁止**输出"技术栈确定 / 技术栈已定"之类结论、**禁止**进入 Phase 2 生成设计。用户改选某项后须重出汇总再确认。「确认汇总」通过是进入设计的**唯一闸门**，不得以"默认继续""先生成再调整"绕过。

---

## 交互轮次总结

| 步骤 | 选择次数 | 选择内容 |
|------|---------|---------|
| Step 1 | 1 次 | 开发范畴 |
| Step 2 | 2 次 | 客户端技术组合 + 客户端通用能力 |
| Step 3 | 3 次（+ 打包项透明化确认） | 后端核心组合（选完须回显隐含 ORM/构建工具确认 + 补询连接池/序列化/后端实时通信服务端）+ 后端通用能力 + HTTP 客户端 |
| Step 4 | 3 次 | 数据库 + 缓存 + 消息队列 |
| Step 5 | 3 次 | 认证鉴权 + API文档 + 架构规范 |
| Step 6 | 最多 3 次 | 前端服务名称 + 后端服务名称 + 后端模块划分（动态） |
| 汇总确认 | 1 次 | 最终确认 |

全栈项目最多 **6 步 15 次选择 + 1 次确认**，每步最多 3 次，每次只选一个维度。其中 Step 3 选定后端核心组合后，额外附带「打包项透明化」环节（回显 ORM/构建工具 + 补询连接池/序列化/后端实时通信服务端），属组合确认的配套动作，不静默采用框架默认（见 Step 3「⚠️ 打包项透明化」）。
