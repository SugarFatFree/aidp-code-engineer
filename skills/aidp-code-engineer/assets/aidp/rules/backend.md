---
name: aidp-backend-rules
description: AIDP 约定 27（配置中心动态配置热刷新）详规 + 后端 DI 依赖可解析性静态检查（编译查不出、启动期爆炸的那一半）+ 约定 40 实现侧（上游调用日志挂载点与响应体重复读的坑）+ 前端可选能力开关的服务端一侧（WebMCP L2，未启用则不适用）；编辑后端代码时加载
paths:
  - "code/backend/**"
  - "code/server/**"
  - "server/**"
---

# 后端代码向约定详规（编辑 `code/backend/**` 时自动加载）

> 本文件是 **约定 27（配置中心动态配置热刷新）**、**前端可选能力开关的服务端一侧**、**后端 DI 依赖可解析性静态检查（约定 35 姊妹条：开发期只静态验证的差集补齐）** 与 **约定 40 实现侧（上游调用日志的接线点与必踩的坑）** 的**单一信源详规**（四段，与本文件 frontmatter `description` 及 `{{AIDP_HOME}}/rules/README.md` 表格一致）。项目记忆文件（AGENTS.md / CLAUDE.md）核心约定段只保留约定 27 的一行索引锚点，锚点编号不变、「见约定 27」仍解析。
> 约定 27 之外，后端还须遵守 `{{AIDP_HOME}}/rules/code.md`（全代码通用：注释 17 / 目录 18 / README 19 / 复杂度 20 / DB 约束 23 后端侧 / **错误契约与失败可见性 + fail-closed + 上游契约权威（约定 23 姊妹条，后端是主战场：失败返业务码+中文 message 不伪装成 200 空数据、上游不可达用中文服务名报错、安全 fail-closed）** / Mock 26 后端侧 / 组件复用 28 / 死代码 29 / **运行时验证纪律 35**〔不擅自起服务、不完整构建——对后端同样适用〕/ **通用还原度规则集 39** / **上游调用日志 40**〔本文件另有实现侧详规〕）。

## 约定 27 — 配置中心动态配置热刷新（仅用配置中心的项目适用）

用配置中心（如 Nacos/Apollo/Consul/Spring Cloud Config）时，读取动态配置的组件必须支持**运行时热刷新**（配置变更无需重启即生效），按所用框架机制实现（如 Spring Boot `@RefreshScope`）。

- **必加**：注入配置中心**可变**配置的组件（连接池/限流阈值/开关/第三方地址密钥等），如 Spring `@Value`/`@ConfigurationProperties` 绑定类、依赖动态配置的 Bean
- **不需要**：仅注入启动期固定配置（数据源 URL/端口）、纯逻辑类、服务发现客户端
- **注意**：热刷新通常会重建组件实例，长生命周期持有者需避免缓存旧引用（如 Spring 用 `ObjectProvider` 或每次 get）
- **本文件即约定 27 的详规单一信源**（⛔ 不要再把读者弹去 `agents/backend.md` —— 那是副本）；回检 = `code-verification-loop` 维度 4 扫"注入配置中心可变 key 但未声明热刷新"。

## 客户端能力开关的服务端一侧（★ 可选，仅当项目启用了客户端应用 MCP 等可选能力时适用）

> **先判定，判定为否就没有本节**：`python3 {{AIDP_HOME}}/scripts/check_webmcp.py --detect --json` 判
> `enabled: false`（默认、绝大多数项目）→ **整节不适用**，不新增任何字段、接口、告警。
> 前端侧详规单一信源 = WebMCP 可选规则（本节只写**后端该做什么**，不复述前端规则）。该规则**默认不安装**：权威模板位 `{{AIDP_HOME}}/templates/optional-rules/webmcp.md`，启用后经 `python3 {{AIDP_HOME}}/scripts/check_webmcp.py --install-rule` 装到 `{{AIDP_HOME}}/rules/webmcp.md`。<!-- ssp-check: ignore 这里的 rules/webmcp.md 是安装【目标位】，默认不存在正是设计（可选规则未启用即一字节不加载）-->
> ⚠️ 该详规**按需安装**：默认不在 `rules/` 下、模板位在 `{{AIDP_HOME}}/templates/optional-rules/webmcp.md`，
> 由启用的项目跑 `check_webmcp.py --install-rule` 装过去。

启用后，后端须为该能力提供一个**运行时可开关的服务端标志**（三层 AND 模型的 **L2** 层，
另两层是浏览器能力 L1 与使用者页面开关 L3）：

- **⛔ 不新造接口**：挂到项目**已有的**前端配置下发 / bootstrap / 站点信息接口上，**多加一个布尔字段**即可。
  确实没有此类接口时才新增，且须走**约定 22** 级联。⛔ 不新增表、不新增错误码。
- **⛔ 必须运行时可变**：改配置后**无需重新构建前端、无需重新发版**即生效。
  用配置中心的项目**须支持热刷新**（见上方约定 27）。
  ⛔ **禁止用构建期常量 / 环境专属守卫**（如 `@Profile("dev")`）实现——那会让这个开关要么**关不掉**、
  要么**要重新发版才能开**，等于没有开关。这与**约定 26**「Mock 必须由运行时开关控制、禁构建期守卫」同源。
- **字段命名跟随项目既有配置命名习惯**，不强制统一名称。
- **默认值取「关」**：该能力扩大前端攻击面（页面把自身操作面暴露给任何能在本页执行 JS 的主体），
  默认关比默认开安全。若项目场景更看重可用性（纯内网、当常规功能用）**可反转为默认开**，
  但**必须在设计文档里显式记录这个决定及其理由，不得默默反转**。
- **后端不负责前端的降级表现**：前端取不到该字段时按 fail-closed + 缓存处理（详见 `rules/webmcp.md` §2.2），
  后端只需保证**字段缺失时不报错、老版本后端不影响新版本前端**。

## 约定 35 姊妹条 — 后端 DI 依赖可解析性静态检查（Spring/Java 适用 — 编译查不出、启动期才炸的那一半）

**动机（AIDP 差集补齐）**：AIDP 正确地把「完整生产构建」排除在开发期之外（开发期只做类型/语法检查，约定 16 甚至把「完整构建当例行命令」判为需清除的冲突项）。但这带来一个副作用——**`mvn compile` 能覆盖的错误集合 ⊊ 部署前应拦截的错误集合**。差集里最高频、代价最大的一类是 **DI 依赖不可解析**：类型存在、import 正确、语法合法（编译必过），却在 Spring 容器**启动期**才炸（`required a bean of type ... that could not be found`）。它的反馈周期是「提交 → 推送 → CICD → 部署 → 启动失败」十几分钟起、还污染部署记录；在 `/sprint-batch`·`/sprint-autopilot` 无人值守批量场景下，一个 DI 错误会让整批 Sprint 的部署验证全部空转——而它本可以在开发阶段被一条 grep 拦下。

**这是纯静态检查**（grep 级文本分析），**不编译、不打包、不起服务、不起 Spring 容器**，成本与现有 grep 类检查同量级，完全符合「开发期只做轻量校验」。

**覆盖三类「编译无感、启动期爆炸」问题**：

1. **DI bean 不可解析**：对本次变更类的注入点（`@Autowired`/`@Resource`/`@Inject` 字段、`@RequiredArgsConstructor`+`private final` 构造注入、显式构造参数、setter 注入），提取注入类型 `T`，在全仓判定是否存在 bean 来源——三类来源命中任一即可解析：
   - **项目内组件**：`T` 的定义类带 `@Service`/`@Component`/`@Repository`/`@Controller`/`@RestController`/`@Configuration`/`@Mapper`/`@FeignClient`/`@Aspect` 或 `@ConfigurationProperties`（含 `@EnableConfigurationProperties(T.class)` 注册）；`T` 是接口/父类时，其带注解实现类 `implements/extends T` 也算来源；`@MapperScan` 约定下仓内 `*Mapper`/`*Dao` 接口视为已注册
   - **显式 `@Bean`**：全仓存在返回类型为 `T` 的 `@Bean` 方法
   - **框架自动配置**：命中白名单（`StringRedisTemplate`/`RedisTemplate`/`ObjectMapper`/`DataSource`/`JdbcTemplate`/`JavaMailSender`/`ElasticsearchOperations`/… 等 starter 自动装配 bean）
2. **多 bean 无 `@Qualifier`**：注入类型有 ≥2 个候选 bean 且注入点未加 `@Qualifier`/未有 `@Primary` 消歧 → 启动期 `NoUniqueBeanDefinitionException` **风险**（Spring 会先按字段名匹配 beanName 兜底，故判 **Warn** 而非 Critical）
3. **`@Value` 键缺失**：`@Value("${key}")` 无默认值、且 `application*.yml`/`.properties`（relaxed binding：忽略 `-`/`_`/大小写）与 `docs/deployment/*/配置文件/增量/配置项清单.md` 均无该键 → 启动期占位符解析失败

**severity 口径（高精度优先，避免噪音误阻断）**：
- **Critical**（近乎确定不可解析）：① 框架不自动装配的常见误注入类型（`RestTemplate`/`WebClient`/`OkHttpClient`/`HttpClient` 等——本项目既有惯例是构造函数内 `new RestTemplate()`，误写成注入即必炸）；② 仓内已定义为**具体类**却无组件注解/`@Bean`/`@ConfigurationProperties`；③ `@Value` 键确缺无默认值
- **Warn**（静态无法确证、容忍跨模块/外部 starter）：接口/抽象类无带注解实现、多 bean 无消歧、全仓无来源但可能来自未扫描模块

**「同类型既有惯例」提示（最有用的一行）**：命中 DI 不可解析时，脚本 grep `new T(` 的现有位置一并给出——不只说「找不到 bean」，还告诉你**这个项目里同类型是怎么用的**，把一次告警直接变成一次修复。

**落地**：确定性静态分析，Spring/Java 探测、非 Java 项目静默跳过。回检三处——① **主检测点** = `code-verification-loop` 维度 6「DI 依赖可解析性」（测试期，Critical 命中回 `/sprint-bugfix`）② **开发期前置门** = `/sprint-dev` 后端阶段静态门（`--changed-only`，与 `mvn compile`「编译查不出的那一半」并列，早于 CICD 拦下）③ 本详规写动机与判定口径。命令端只编排调脚本、不复述判定逻辑（约定 21）。

> ★ **唯一实现 = `{{AIDP_HOME}}/skills/code-verification-loop/scripts/check_di_resolvability.py`**（CVL SKILL 内置），①主检测点与②开发期前置门**共用同一个脚本**，不存在第二份。
> CLI：`<code_dir> [--changed-only [--base <ref>]] [--json] [--strict] [--config-keys-file <f>]`；退出码 `0`=通过/不适用 · `1`=有 Critical · `2`=入参或环境错（目录不存在等，修参数重跑、**不算违规**）**或 `--json.unreadable_files` 非空**（有 `.java` 读不出：权限 / 断链符号链接 → **本维度结论不可信**，须修好文件后重跑，⛔ 不得按「不算违规」略过）。
> - **没有 `--gate`，也不要加**：该脚本默认即「有 Critical → exit 1」。不提供 `--gate`：「默认恒 exit 0、须显式加参数才闸」等于一个忘加就静默放行的假绿开关。传了会被 argparse 拒绝（exit 2）。
> - 纯前端项目没有 `code/backend` 时脚本返回 **exit 2（入参/环境错，不算违规）**；需免噪音用 `if [ -d code/backend ]; then … ; fi`。⛔ **不要写 `[ -d … ] && …`**——那会让整条复合命令返回 rc=1，被按「1=有 Critical」读成违规，比 exit 2 严格更坏。
> - 判定口径变更 → 在模板仓库修改该 SKILL 脚本并同步 bundle（约定 16）；下游项目不直接改它、也不改其脚手架副本。
>
> ⛔ **不得在项目侧 `{{AIDP_HOME}}/scripts/` 重建一份 `check_di_resolvability.py` 副本**：两套口径必然漂移。项目侧副本有三类静默漏检——**未跟踪的新文件不纳入增量范围**（而新建的类正是 DI 问题最高发来源，等于对头号场景失明）、非 ASCII 路径被丢弃、路径不存在返回 0 假绿。需要调整判定口径 → 在模板仓库改 SKILL 脚本（约定 16）。

## 约定 40 实现侧 — 上游调用日志的接线点与必踩的坑（后端）

> 规则正文（必打字段 / 级别 / 脱敏 / 二进制降级 / 例外）以 `{{AIDP_HOME}}/rules/code.md` 约定 40 为**单一信源**，本节不复述。
> 这里只放**后端才需要知道的接线细节**——放在这份按需加载的分片里，纯前端 / 非 JVM 项目一个字节都不必读。

### 挂载点（按所用客户端选一处，一次接线全局生效）

| 客户端 | 挂载点 |
|---|---|
| `RestTemplate` | `ClientHttpRequestInterceptor` |
| `WebClient` | `ExchangeFilterFunction` |
| OkHttp | `Interceptor` |
| Feign | 自定义 `feign.Logger`（**接口本身不写日志**，故机器门对 Feign 接口整体排除）|
| **JDK `HttpClient`**（`java.net.http`）| **没有拦截器 SPI** —— 只能包一层发送helper，所有调用走它 |
| 非 HTTP SDK（对象存储 / 短信 SDK 等）| 薄封装层统一打点；**HTTP 拦截器覆盖不到它们**，机器门也刻意不为其抵扣 |

### ⛔ 必踩的坑：挂了拦截器，业务侧读不到响应体了

`SimpleClientHttpRequestFactory`（JDK 原生连接）**不支持响应体重复读**。
在它上面挂拦截器打响应体，会把流读空，业务侧再读就是空——**表现为"加了日志之后功能坏了"**，
极容易被误判成拦截器方案本身不可行而回退到"每个 client 手写两行 log"。

**解法**：换 `BufferingClientHttpRequestFactory` 包装，或改用 `HttpComponentsClientHttpRequestFactory`。

```java
RestTemplate rt = new RestTemplate(
        new BufferingClientHttpRequestFactory(new SimpleClientHttpRequestFactory()));
rt.getInterceptors().add(new UpstreamCallLoggingInterceptor());
```

### 拦截器抵扣的边界（机器门口径，避免误解为"挂了就全免"）

`check_upstream_call_log.py` 只在**同一文件内**检测到拦截器注册时抵扣该文件的 C1/C2，且**只抵扣 HTTP 类机制**。
刻意不做全局抵扣：真实样本里拦截器是某个 Service 的**内部私有类、只挂在它自己的那个 `RestTemplate` 上**，
全局抵扣会让隔壁真正零日志的客户端被静默放过——那正是本条要抓的东西。

> 参考实现骨架（配对 traceId + 截断 + 脱敏 + 二进制降级四项能力）见 `{{AIDP_HOME}}/reference/上游调用日志参考实现.md`。
