# Java / Spring 审计细则

> 探测命中 `*.java` + `pom.xml`/`build.gradle` 时加载本文件。跨技术栈的通用判据（维度划分、severity 定义、三方冲突裁决）见 `../SKILL.md`，此处只写 Java/Spring 专有部分。

---

## 一、维度 6：DI 依赖可解析性（本栈专属·完整细则）

> 🎯 **补的是一个结构性盲区**：维度 1~5 没有任何一项覆盖**「编译期完全无感、只在 Spring 容器启动期才解析」**的错误。最典型：新类写 `@Autowired private RestTemplate restTemplate;`，但全项目没有任何 `RestTemplate` 的 `@Bean`（既有用法都是构造函数里 `new RestTemplate()`）——`mvn compile` **必过**，容器启动直接 `APPLICATION FAILED TO START: Field restTemplate ... required a bean of type 'RestTemplate' that could not be found`。反馈周期是「提交 → 推送 → CICD → 部署 → 启动失败」**十几分钟起**，还污染部署记录；无人值守批量场景下**一个 DI 错误让整批 Sprint 部署验证空转**。而它本可被一条 grep 静态拦下。
>
> 🪶 **关键前提——这是纯文本静态分析（grep 级）**：**不编译、不打包、不起服务、不起 Spring 容器**，成本与维度 4 现有 grep 类检查同量级，完全符合「开发期只做轻量校验」的定位。

### 1.1 检查对象

本次变更类的注入点——`@Autowired`/`@Resource`/`@Inject` 字段、`@RequiredArgsConstructor` + `private final` 构造注入、显式构造参数、setter 注入——提取注入类型 T。

### 1.2 可解析性判定（三源命中任一即可解析）

| # | bean 来源 | 判定依据 |
| :-: | :- | :- |
| 1 | **项目内组件** | T 的定义类带 `@Service`/`@Component`/`@Repository`/`@Controller`/`@RestController`/`@Configuration`/`@Mapper`/`@FeignClient`/`@Aspect` 或 `@ConfigurationProperties`（含 `@EnableConfigurationProperties(T.class)` 注册）；**T 是接口/父类时，其带注解的实现（`implements`/`extends` T）也算来源**；`@MapperScan` 约定下 `*Mapper`/`*Dao` 接口视为已注册 |
| 2 | **显式 `@Bean`** | 全仓存在返回类型为 T 的 `@Bean` 方法 |
| 3 | **框架自动配置** | 命中白名单（`StringRedisTemplate`/`RedisTemplate`/`ObjectMapper`/`DataSource`/`JdbcTemplate`/`JavaMailSender`/`ElasticsearchOperations`/`ApplicationContext`/`Environment` 等 starter 自动装配 bean） |

### 1.3 一并覆盖两类近亲（同样编译无感、启动期爆炸、纯静态可检）

- **多 bean 无 `@Qualifier`**：注入类型有 ≥2 个候选且未 `@Qualifier`/`@Primary` → `NoUniqueBeanDefinitionException` 风险
- **`@Value` 键缺失**：`@Value("${key}")` 无默认值，且 `application*`/`bootstrap*`（yml/properties，**relaxed binding**：忽略 `-`/`_`/大小写）与配置项清单文档中均无该键 → 占位符解析失败

### 1.4 severity 口径（★ 精度优先，务必避免噪音误阻断——这是本维度成败关键）

| 级别 | 命中条件 |
| :- | :- |
| 🔴 **Critical**（近乎确定不可解析） | ① **框架不自动装配的常见误注入类型**（`RestTemplate`/`WebClient`/`OkHttpClient`/`HttpClient`/`RestClient`——Boot 只装配它们的 `Builder`，不装配本体）；② 仓内**已定义为【具体类】**却无组件注解/`@Bean`/`@ConfigurationProperties`；③ `@Value` 键确缺且无默认值 |
| 🟡 **Warn**（静态无法确证，容忍跨模块/外部 starter） | 接口或抽象类无带注解实现；**多 bean 无 `@Qualifier`**（Spring 会先按**字段名匹配 beanName** 兜底，不能判死）；全仓无来源但可能来自未扫描模块 |

> ⚠️ **不得把「多 bean / 接口无实现」判 Critical**——会误报一片、噪音淹没真问题。经验数据：真实已部署 Spring 代码库用本口径实测 **236 文件的项目 = 0 Critical / 4 Warn；1334 文件的项目 = 0 Critical / 33 Warn**（零误阻断）。

### 1.5 ★ 提示语要求（最有用的一行）

命中 DI 不可解析时，**必须一并 grep `new T(` 的现有位置给出**——不只说「找不到 bean」，还告诉开发者**这个项目里同类型是怎么用的**，把一次告警直接变成一次修复：

```
❌ DI 依赖不可解析：CucKopRoleService.restTemplate (RestTemplate) —— 全仓未找到 @Bean/组件注解。
   本项目既有 4 处均为构造自建：CucManagementService:122 / CucHttpClient:57 / ...
   建议照此改为 new RestTemplate()，而非 @Autowired 注入。
```

### 1.6 回检脚本

```bash
# 验收期（默认）：全量扫描，本维度的主检测点
python3 <SKILL_DIR>/scripts/check_di_resolvability.py <代码目录> [--json] [--strict] [--config-keys-file <配置项清单>]

# 开发期前置门：只报告本次 git 变更文件里的注入点，写码当场拦下
python3 <SKILL_DIR>/scripts/check_di_resolvability.py <代码目录> --changed-only [--base origin/develop]
```

- 与维度 4 的采集型脚本不同，**本脚本是机器可判的硬门**：有 Critical 即退出码 **1**（`--strict` 时 Warn 也返回 1）；无 Critical / 非 Java 项目返回 **0**；目录不存在返回 **2**。
- `--config-keys-file` 可选：把「配置项清单文档」里的 key 逐行喂进来，避免配置在文档而未落 yml 的 `@Value` 被误判缺失。
- **Warn 项不阻断验收**，但须由验收 Agent 结合跨模块上下文人工确认后在报告中登记。
- **`--changed-only` 增量快筛**：只收窄「报告范围」，**bean 索引照旧全仓解析**。这条不可省 —— 否则新写的 `@Autowired Foo foo` 会因为 `FooImpl` 这次没改动而被误判「无来源」，增量模式就成了误报机器。实测 fixture（新建 `Bar.java` 注入 `RestTemplate` + `Foo`，`FooImpl` 已提交未改动）：`--changed-only` 正确只报 `RestTemplate`、`Foo` 不误报。未跟踪的新文件一律纳入（新建 Java 类正是 DI 问题最高发来源）。边界行为：`--base` 写错的 ref、或传成路径（会被 git 当 pathspec 静默接受）判入参错 **2**；`--base` 不配 `--changed-only` 单独使用同样判 **2**；**零提交的新仓**（默认 `HEAD` 不存在）降级为「仅扫未跟踪新文件」而非顶回 2；非 git 仓库 stderr 告警后退回全量（更严的一侧）；子模块内的变更显式告警（顶层 `--name-only` 只给 gitlink 目录名，不告警就等于静默漏扫）。
- **刻意不提供 `--gate`**：本脚本默认就是「有 Critical → exit 1」，无须开关；「默认恒 exit 0、须显式 `--gate` 才闸」的设计与全仓退出码约定冲突，等于留一个「忘加参数就静默放行」的假绿开关。确需「只看不闸」用 `--json` 读 `stats.critical` 自行决定。

### 1.7 常见问题模式与修复

| 问题模式 | 修复方式 |
| :- | :- |
| 注入了框架**不自动装配**的类型（`RestTemplate`/`WebClient`/`OkHttpClient`/`HttpClient`/`RestClient`），全仓无 `@Bean` | 先 grep `new T(` 看**本项目同类型既有用法**——既有全是构造自建就照此改；确需注入则在 `@Configuration` 类补 `@Bean` |
| 注入类型在仓内**已定义为具体类**，却无组件注解、无 `@Bean`/`@ConfigurationProperties` | 补组件注解，或在配置类补 `@Bean` 工厂方法；若它本就不该是 bean（纯工具类/值对象），改为直接 `new` 或静态方法 |
| `@Value("${key}")` 无默认值且配置查无此键 | 补配置项，或加默认值 `@Value("${key:默认值}")`。**启动期报 `IllegalArgumentException: Could not resolve placeholder`** |
| 🟡 注入类型有 ≥2 个候选且未 `@Qualifier`/`@Primary` | 加 `@Qualifier("beanName")` 或给首选实现加 `@Primary`。**不判 Critical**——Spring 先按字段名匹配 beanName 兜底，静态无法判死 |

### 1.8 与其它维度的边界（不重复登记）

本维度只管**「容器能否装配起来」**这一启动期语义；维度 4「新增依赖/import 越界基线」管**依赖清单登记**、维度 4「配置中心热刷新漏标」管 `@RefreshScope`、维度 5 管技术债，三者与本维度正交。同一处问题只在本维度登记。

---

## 二、维度 4：Java/Spring 专有检查行

### 2.1 金额字段类型守恒（🔴 Critical）

若详细设计 A.3 金额字段为 `BIGINT`，Entity/DTO 必须用 `Long`，**严禁 `BigDecimal`/`double`/`float`**；已有项目沿用现有约定则不判违规。

**金额 JSON 序列化（🟡 Important）**：常规金额可用 `integer`；若可能超过 JS Number 安全上限（2^53）或使用 0 位小数货币（JPY/KRW/VND 等大数值），必须用 `string` 传输：

```java
@JsonSerialize(using = ToStringSerializer.class)
private Long amount;
```

### 2.2 DB 约束前置校验遵守（🟡 Important，NOT NULL/UNIQUE/外键缺校验升 🔴 Critical）

详细设计 A.3 表结构里的 DB 约束，Controller/Service 必须有对应前置校验，不能只靠数据库兜底（报 500 给用户、错误信息泄露表结构）。逐约束核对：

| DB 约束 | 对应前置校验 |
| :- | :- |
| `NOT NULL` | DTO 字段有 `@NotNull`/`@NotBlank`，或 Service 入参非空校验 |
| `length=N` / `varchar(N)` | `@Size(max=N)` / `@Length` |
| `UNIQUE` | 写入前先查重并给业务错误码 |
| 外键 | 关联存在性校验 |
| `CHECK` / 枚举列 | 取值范围 / 枚举校验 |

```bash
grep -rn "@NotNull\|@NotBlank\|@Size\|@Length\|@Valid\|@Pattern" <后端目录>
```

采集已有校验注解后，与设计 A.3 约束清单逐条比对**缺口**。**需设计 A.3 约束清单作输入，脚本不独立判定。**

### 2.3 配置中心热刷新漏标（🟡 Important）

`@Value` 注入了配置中心可变 key，但所在类无 `@RefreshScope` → Nacos/Apollo/Config 改值后不热刷新，改配置不生效仍需重启（违背配置中心初衷）。

```bash
python3 <SKILL_DIR>/scripts/scan_code_conventions.py <代码目录> --checks refresh-scope
```

扫 Java/Kotlin 中含 `@Value("${...}")` 但无 `@RefreshScope`、且非 `@ConfigurationProperties` 的类。Agent 据 key 语义判定：**运行时可变 key**（开关/阈值/限流/超时/降级配置等）漏标 → Important（要求加 `@RefreshScope` 或迁 `@ConfigurationProperties`）；启动期一次性读取的常量 key（服务名/固定路径）可豁免。

### 2.4 审计字段填充溯源（🔴 Critical）

审计字段（`create_by`/`create_time`/`update_by`/`update_time`）必须取当前登录操作人 + 当前时间，**严禁把 `create_by`/`update_by` 写死为字符串 `"system"`**；**逻辑删除必须同步更新 `update_by`/`update_time`**（对应 dev-logic-architect 核心原则 22）。

```bash
python3 <SKILL_DIR>/scripts/scan_code_conventions.py <代码目录> --checks audit-fill
```

采集两类命中：① **写死审计人**——审计人字段 / `setCreateBy` / `setUpdateBy` 同行出现写死常量字面量（`"system"`/`"admin"` 等）；② **逻辑删除漏同步修改人**——逻辑删除写点（`setDeleted(1)` / `deleted=1` / `@TableLogic`）邻近（±5 行）未见 `update_by`/`update_time` 同步信号。

> ⚠️ **`@TableLogic` 默认删除 / 自定义 UPDATE 会绕过 ORM 自动填充**，是高频漏点。
> **Agent 需排除**：定时任务/数据初始化/无登录态且已显式标注的 `system` 场景、逻辑删除已由拦截器统一同步修改人的情况。

### 2.5 新增依赖越界基线（Java 部分·需人工核对）

```bash
python3 <SKILL_DIR>/scripts/scan_code_conventions.py <代码目录> --checks dep-baseline [--base <ref>]
```

⚠️ **Java/Go 的 `import` ↔ Maven artifact 映射无法离线可靠完成，脚本不覆盖**——须 Agent 据 `pom.xml`/`build.gradle` 人工核对新增 import 的顶层包是否已声明在依赖清单。命中即越界 → 要么补进清单（经评估）要么移除 → 🟡 Important（引入未评估的第三方/重型依赖升 🔴 Critical）。

### 2.6 用户自我保护校验（🔴 Critical·纯语义核验）

用户删除/禁用/角色撤销接口，必须以**当前登录态身份（JWT `sub` / `SecurityContext`，不取前端传入的"当前用户 id"）**为基准，拦截「目标 id == 当前操作人」的三类自伤操作：① 删除自己；② 禁用/锁定/冻结自己；③ 撤销/降级自己赖以管理的角色/权限（尤其最后一个管理员）。

**无脚本**（判定依赖"目标 id vs 当前用户"的比较语义，正则难可靠识别），由 Agent 阅读用户管理相关 Controller/Service 确认存在该守卫。命中「能删除/禁用/降权自己」→ Critical；仅前端按钮置灰、后端无校验 → Critical（前端不可替代后端）。

---

## 三、维度 3：context-path 检测（Spring Boot）

检查 `application.yml` / `application.properties` 中的 `server.servlet.context-path`：

```yaml
server:
  servlet:
    context-path: /api
```

配置了 context-path 时，前端 `baseURL` 必须包含该前缀，否则按文档直调 404。前端侧判据见 `stack-vue.md` / `stack-react.md`。

---

## 四、维度 2B：后端第三方 mock 的技术栈专有反模式

### 4.1 构建期隔离（反模式 1·🔴 Critical）

```java
// ❌ 错误：使用 @Profile("dev") 构建期隔离
@Service
@Profile("dev")  // prod profile 部署时此类不加载
public class AlipayServiceMockImpl implements AlipayService { ... }

// ✅ 正确：运行时配置开关
@Service
public class AlipayServiceImpl implements AlipayService {
    @Value("${third-party.mock.enabled}")
    private boolean mockEnabled;  // 运行时注入，任意环境可切换

    public RefundResponse refund(RefundRequest request) {
        if (mockEnabled) { return mockData; }
        return realClient.refund(request);
    }
}
```

同类构建期隔离反模式还有 `@Profile("!prod")`、`#if DEBUG`——一律 Critical，须改为运行时环境变量/配置开关，确保 UAT/Demo 打包部署后仍可切换。

### 4.2 真实对接后残留检查（反模式 2·⚠️ 部分人工核验）

`scan_third_party_mock_antipatterns.py` 已能扫后端配置（`.yml`/`.properties`）的**真实 base-url 信号**（对接信号 2，命中即与 mock 并存升 Critical）；但以下后端残留仍需人工 grep：

1. 检查 `application.yml` 或部署配置中的第三方 base URL（如 `third-party.alipay.base-url`）
2. 若已切换到真实地址（非 `http://localhost:*` / `https://sandbox.*`），扫描以下残留：
   - Mock 开关配置：`third-party.mock.enabled=true` 仍存在
   - Mock 数据类：`*MockData.java` 仍存在
   - Mock 分支：`if (mockEnabled)` 未删除
   - 后端凭证：`app.id` / `private.key`（**脚本不实现，误报风险高，须人工 grep**）

---

## 五、本栈不适用的检查项

- **前端专有项**（叶子组件替换白名单、Vite/webpack 构建期守卫、表格列/表单项采集）→ 见 `stack-vue.md` / `stack-react.md`，本栈不适用。
- **维度 7「CSS 预处理器一致性」（Vue 专属）与维度 8「请求通道 URL 拼装」（前端专属）** → 纯 Java/Spring 后端两者均**整维度跳过**；前后端同仓时，两者对前端那部分目录仍生效，由前端栈文件承接（维度 8 见 `stack-vue.md` §五 / `stack-react.md` §四）。
- **单文件行数阈值**：Java/Kotlin ≤ 500 行（不含 import + 注释），单方法 ≤ 50 行为硬阈值——判据本身跨栈通用，见 `dimension-4-5-quality-debt.md` 维度 4「文件复杂度 + 复用封装」行，此处只记本栈阈值取值。
