# THIRD_PARTY_MOCK 第三方临时 Mock 标注协议

> 本规范隶属于 `code-verification-loop` SKILL，供维度 2B 第三方临时 mock 协议核验使用。
> 上级:`../SKILL.md`
>
> **协议内容说明:** 本协议定义的标注规范与 `dev-logic-architect` SKILL.md 核心原则 14 保持一致。其他 SKILL 通过引用核心原则 14 间接获得协议规范。
>
> **目的:** 在第三方平台接口尚未交付时,允许前端/后端使用临时 mock 数据保持开发联调;一旦真实接口可用,mock 必须立即删除,严禁与真实调用并存或保留为兜底。

---

## 一、适用边界

**✅ 允许临时使用 mock 的唯一场景:**

- 对接的接口由 **本项目以外的第三方平台**(如支付宝、微信、企业微信、银联、海关、统一身份认证、其他公司 SaaS)提供
- 该接口在当前研发周期内 **尚未交付**(未提供 base URL / 未提供凭证 / 未开放联调环境 / 未交付接口契约稳定版)
- 已在 PRD 或详细设计的 Module E 待澄清清单中登记"等待第三方交付"

**❌ 严禁使用 mock 的场景:**

- 同项目内的后端接口(应通过 Phase 任务依赖关系等待后端实现,而非 mock;若前端必须本地调试,**优先采用前端拦截器 mock**,严禁让后端写一次性假数据接口)
  - ⚠️ **这一条不是"不许 mock",而是"换一种 mock、换一套守卫"**:同项目后端未部署时用的是 **`DEV_MOCK`** 标记,
    它与本协议的 `THIRD_PARTY_MOCK` **守卫策略相反** —— `DEV_MOCK` **应当被构建期裁掉**
    (`import.meta.env.DEV` / MSW 仅 dev 注册),绝不能进生产;而 `THIRD_PARTY_MOCK` **必须运行时开关**,
    因为它要活到 UAT/Demo。**扫描器的「构建期守卫 = Critical」只对 `THIRD_PARTY_MOCK` 成立。**
  - `DEV_MOCK` 的必填字段只有三个:`since` / `owner` / `REMOVE_WHEN`(同项目内没有"厂商 / 对方接口 /
    对方交付日"这三个概念),字段缺失同样判 🔴 Critical;`since` 计龄超阈值判 🟡 Important。
    标记定义与推荐写法的单一信源在 `dev-execution-planner/references/flow-edge-cases.md` 情况 1。
- 第三方接口已交付且开始对接(任何已开始对接的接口,不允许保留 mock 兜底)
- "为了测试通过/演示通过"而临时造数(走真实接口 + 测试账号即可)
- "接口偶尔抖动" / "接口偶尔失败" 而做的 mock 兜底(应走标准错误处理,不臆造兜底)

## 一·B、Mock 实现位置选型(优先级降序)

**核心原则:必须使用 mock 时,优先选择前端 mock 方案,后端介入越少越好。**

| 优先级 | 方案 | 实现位置 | 适用场景 | 优劣势 |
|:-:|:-|:-|:-|:-|
| **P0(首选)** | **前端 mock** | 前端代码(axios 拦截器 / fetch 拦截 / MSW Service Worker / 本地 JSON 文件)，**运行时环境变量控制**（`VITE_THIRD_PARTY_MOCK_ENABLED`） | 第三方接口仅供前端调用(OAuth 登录回调、地图 SDK、支付收银台、用户授权页跳转) | ✅ 无需后端介入,前端独立联调<br>✅ 不污染后端代码仓<br>✅ 切真实接口只需关闭前端拦截,后端零改动<br>✅ 团队协作效率最高,缩短跨角色等待<br>✅ 打包后仍可在 UAT/Demo 环境启用 mock |
| P1(次选) | 后端 mock | 后端代码(mock 实现类 / 接口桩函数)，**运行时环境变量控制**（`THIRD_PARTY_MOCK_ENABLED` + 运行时判断） | 第三方接口供后端服务端调用(服务端鉴权、银行代扣、报关推送、回调签名验证) | ⚠️ 需后端开发介入<br>⚠️ 污染后端仓库<br>⚠️ 切真实接口需后端代码改动<br>✅ 运行时可控，部署后可启用/禁用 |
| P2(最后) | 中间件 mock | 独立 mock 服务器(json-server / Mockoon / WireMock standalone) | 前后端都需调用且接口复杂,需团队共享 | ⚠️ 需额外维护 mock 服务<br>⚠️ 部署成本高,仅适合长期未交付的关键接口 |

**判断口诀:**
- "前端能拦截就前端拦截,前端拦截不了再让后端 mock" — 大幅减少跨角色沟通成本
- "Mock 是临时占位,不是正式实现" — 不要为 mock 投入超过真实对接成本 30% 的工时
- "必须运行时可控,严禁构建期守卫" — UAT/Demo 环境部署后必须能通过环境变量启用 mock

**Why 前端优先:**
1. **前端独立联调,不阻塞团队**:第三方接口仅前端调用的场景,前端拦截后即可独立推进,后端无需为此分心
2. **不污染后端代码仓**:后端 mock 实现常被遗忘清理,污染主线代码
3. **切真实接口零成本**:前端只需删除拦截块,后端不需要改任何代码
4. **减少跨角色沟通**:前端不需要催后端写假数据接口,后端不需要解释"为什么写了又删"

**前端 mock 的代码示例(THIRD_PARTY_MOCK 标注块仍必填):**

```typescript
// src/mocks/third-party-interceptor.ts
import axios from 'axios';

if (import.meta.env.VITE_THIRD_PARTY_MOCK_ENABLED === 'true') {
  axios.interceptors.request.use((config) => {
    if (config.url?.includes('/alipay/trade/refund')) {
      // THIRD_PARTY_MOCK: 支付宝退款接口未交付,前端拦截器占位
      // vendor: 支付宝
      // api: POST /alipay/trade/refund
      // since: 2026-05-26
      // expected_ready: 2026-12-15
      // owner: FE-张三
      // REMOVE_WHEN: 真实接口可调通后立即删除本拦截块
      return Promise.reject({
        __mock__: true,
        data: { code: 0, refund_id: 'mock_' + Date.now() },
      });
    }
    return config;
  });
}
```

## 一·C、并行动作:向第三方"提需求"——🔒 只提业务诉求,不规定其契约形态(Critical)

> **核心原则「对外提需求 = 业务诉求;对内做设计 = 可定契约」。** 第三方未交付时,我方一边用临时 mock 解阻塞,一边要向第三方"提需求"催交付。**提给第三方的需求只描述业务诉求,绝不规定/推荐对方的契约形态**——接口地址、字段命名、Method、响应结构(`{code,data,message}` 之类)、鉴权、协议都是**对方系统的设计权**,我方规定即越界(不专业、污染对方契约、引发后续不一致)。

- **提给第三方的需求只写 7 项(业务诉求导向)**:① 业务场景/目的;② **对应第三方功能位置**(这些数据对应对方系统自己的哪个菜单/功能页,如"对应订单中心 结算管理→账单明细",让对方一眼对上是开放哪个**现有功能**——指向对方已有功能,**不规定其 URL/字段**);③ 需要的业务数据项(用**业务含义**表述,如"账期/应付金额/结算状态",**不写字段名**);④ 查询/筛选维度(**业务维度**);⑤ 数据范围与隔离(如"按企业隔离,仅返回本企业数据");⑥ 非功能诉求(分页、可外部调用、时效/SLA、调用量);⑦ **明确声明**:接口地址、字段命名、鉴权、协议等技术细节由对方按其规范自定,交付后提供联调环境 + 接口说明。
- **允许引用对方"已存在"能力作上下文**(基于读对方源码的事实,如"据了解你们已有 XX 内部能力"),但**不得据此替对方拟新接口的路径/字段**。
- **边界**:本约束只针对"提给第三方系统的需求";**我方系统内部**新建的接口(Controller/Service/前端 API)照常在详细设计里规定路径与字段——那是对内设计权,不受此约束。
- **mock 占位 ≠ 对方契约**:我方临时 mock 内部用什么字段/结构是我方实现细节,**不得**把这套 mock 字段/路径当作"第三方应实现的契约"反向塞给第三方;一旦对方按其规范交付真实接口,以**对方契约**为准改造我方调用与 mock 删除。

## 二、标注关键词

**统一关键词:** `THIRD_PARTY_MOCK`(全大写下划线)

**为何选这个关键词:**
- 全大写易于 grep / IDE 高亮识别
- 与现有 `TODO` / `FIXME` / `HACK` 注释风格一致
- 唯一关键字便于脚本机器化扫描(无歧义)
- 显式包含 `THIRD_PARTY` 区别于普通本项目内 mock(普通 mock 仍零容忍)

## 三、标注块结构(必填字段)

每个 THIRD_PARTY_MOCK 必须有完整的标注块,放在 mock 函数/常量/文件头部紧贴声明处。**标注块包含 7 行，每个字段独占一行，前缀为对应注释符**。

### 通用结构

```
{注释符} THIRD_PARTY_MOCK: {一句话说明}
{注释符} vendor: {第三方供应商名称,如:支付宝 / 微信支付 / 企业微信 / 银联 / 海关总署 / OAuth-IDP}
{注释符} api: {对接的接口路径或方法,如:POST /alipay/trade/refund 或 AlipayClient.tradeRefund}
{注释符} since: {开始使用 mock 的日期,YYYY-MM-DD}
{注释符} expected_ready: {第三方预计交付的日期,YYYY-MM-DD;未知填 UNKNOWN}
{注释符} owner: {负责人,如:PM-张三 / FE-李四 / BE-王五}
{注释符} REMOVE_WHEN: 真实接口可调通后立即删除本{函数/常量/文件},禁止保留为兜底
```

### TypeScript / JavaScript / Vue / TSX 示例

```typescript
// THIRD_PARTY_MOCK: 支付宝退款接口未交付,占位以解阻塞前端调试
// vendor: 支付宝
// api: POST /alipay/trade/refund
// since: 2026-01-15
// expected_ready: 2026-09-01
// owner: PM-张三
// REMOVE_WHEN: 真实接口可调通后立即删除本函数,禁止保留为兜底
export async function mockAlipayRefund(orderId: string) {
  return { success: true, refundId: 'MOCK_RF_' + orderId, amount: 0 };
}
```

### Java / Spring Boot 示例

```java
/**
 * THIRD_PARTY_MOCK: 海关总署单一窗口报关查询接口未交付,占位以解阻塞测试环境
 * vendor: 海关总署
 * api: POST /singlewindow/customs/query
 * since: 2026-01-15
 * expected_ready: UNKNOWN
 * owner: BE-王五
 * REMOVE_WHEN: 真实接口可调通后立即删除本类,禁止保留为兜底
 */
@Component
public class CustomsQueryClient {

    @Value("${third-party.mock.enabled:false}")
    private boolean mockEnabled;

    @Autowired
    private CustomsApiClient realClient;

    public CustomsQueryResp query(CustomsQueryReq req) {
        if (mockEnabled) {
            // THIRD_PARTY_MOCK 占位逻辑
            return CustomsQueryResp.builder()
                .status("PASS")
                .customsNo("MOCK_" + System.currentTimeMillis())
                .build();
        }
        // 真实接口调用
        return realClient.query(req);
    }
}
```

配置文件 `application.yml`:
```yaml
third-party:
  mock:
    enabled: ${THIRD_PARTY_MOCK_ENABLED:false}  # 运行时环境变量控制
```

### Python 示例

```python
import os

def idp_token_exchange(code: str) -> dict:
    """OAuth IDP token exchange"""
    mock_enabled = os.getenv("THIRD_PARTY_MOCK_ENABLED", "false").lower() == "true"

    if mock_enabled:
        # THIRD_PARTY_MOCK: OAuth IDP 用户授权接口未交付,占位以解阻塞登录联调
        # vendor: 集团统一身份认证 IDP
        # api: POST /idp/oauth2/token
        # since: 2026-06-15
        # expected_ready: 2026-12-15
        # owner: BE-王五
        # REMOVE_WHEN: 真实接口可调通后立即删除本分支,禁止保留为兜底
        return {"access_token": "MOCK_AT_" + code, "expires_in": 3600}

    # 真实接口调用
    response = httpx.post(
        f"{settings.IDP_BASE_URL}/oauth2/token",
        json={"code": code}
    )
    return response.json()
```

## 四、生命周期与删除时机

```
┌─────────────────┐      ┌──────────────────┐      ┌──────────────────┐
│  第三方接口      │      │  开始对接        │      │  对接完成         │
│  未交付         │ ───→ │  (有真实 client)  │ ───→ │  (mock 已删除)    │
│  允许 mock      │      │  必须删除 mock    │      │  零 mock          │
└─────────────────┘      └──────────────────┘      └──────────────────┘
   合规(标注完整)         🔴 Critical 违规         合规
```

**关键判定规则:**

| # | 状态 | 严重级 | 判定条件 |
| :- | :- | :-: | :- |
| 1 | mock 存在,标注完整,无真实 client 引用 | 🟡 Important | 视为合规但下次 Review 必 follow-up;若 `expected_ready` 过期**超过 14 天**,升 🔴 Critical(与第 5 行、脚本默认 `--max-overdue-days=14` 一致) |
| 2 | mock 存在,真实 client 已被代码引用 | 🔴 Critical | 已进入对接阶段,mock 必须删除,禁止并存 |
| 3 | mock 存在,catch / `\|\|` / fallback 中调 mock | 🔴 Critical | mock 兜底,任何场景禁止 |
| 4 | mock 存在,标注块缺失或必填字段不全 | 🔴 Critical | 标注协议违规 |
| 5 | mock 存在,`expected_ready` 已过且当前日期超过 14 天 | 🔴 Critical | 长期挂账,要么催第三方,要么删 mock 改走 Module E 暂行方案 |
| 6 | 找不到 mock 关键词但代码硬编码假数据(无 `THIRD_PARTY_MOCK` 标注) | 🔴 Critical | 普通 mock 零容忍 |

## 五、"已开始对接"的判定

"真实 client 已被引用"通过以下信号判定:

1. **vendor SDK 引用**:`import { AlipayClient } from '@alipay/sdk'` / `import com.alipay.api.*`(✅ 脚本覆盖)
2. **真实 base URL 配置(后端)**:`alipay.base.url=https://openapi.alipay.com` 出现在 `application.yml` / `*.properties`(非 mock 占位)(✅ **脚本覆盖**:保守认厂商生产域名 + `base-url` 真实 https,排除 localhost/sandbox/mock/占位)
3. **真实凭证配置(后端)**:`alipay.app.id=2025xxx` / `alipay.private.key=` 已配置(非 `MOCK_` / `TODO` 占位)(⚠️ **脚本不覆盖,需人工 grep**;凭证误报风险高,刻意不自动判)
4. **客户端实例化代码**:`new AlipayClient(...)` / `RestTemplate/FeignClient + alipay`(✅ 脚本覆盖)
5. **前端 baseURL 切换到真实地址**:`.env.*` 中 `VITE_API_BASE_URL` / `REACT_APP_API_BASE_URL` / `API_BASE_URL` 从 `http://localhost:*` / `http://127.0.0.1:*` / `http://mock.*` 切换到真实域名(✅ 脚本覆盖)

> **脚本覆盖边界(避免误判已查):** `scan_third_party_mock_antipatterns.py` 自动检测信号 **1 / 2 / 4 / 5**(vendor SDK import、后端配置真实 base URL「`.yml`/`.properties`,保守认厂商生产域名 + `base-url` 真实 https」、`new XxxClient`/RestTemplate/Feign、前端 `.env` baseURL);**仅信号 3(后端凭证 `app.id`/`private.key`)脚本不实现(误报风险高),必须人工 grep `application.yml`/`*.properties` 核验**。

**任一信号命中 + mock 存在 → 🔴 Critical(并存)**。

## 六、合规清单(每个 mock 都需逐项核对)

- [ ] 关键词为 `THIRD_PARTY_MOCK`(全大写下划线)
- [ ] 标注块 7 行齐全且每行独立(THIRD_PARTY_MOCK / vendor / api / since / expected_ready / owner / REMOVE_WHEN)
- [ ] mock 与真实 client 不并存(否则立即删除 mock)
- [ ] 不在 catch / `||` / fallback / `try { real() } catch { mock() }` 路径中调用
- [ ] `expected_ready` 不晚于当前日期 + 14 天(与生命周期表第 5 行及脚本默认 `--max-overdue-days=14` 一致;超期需催第三方或转 Module E 暂行方案)
- [ ] **Mock 实现必须是运行时可控的（环境变量 `VITE_THIRD_PARTY_MOCK_ENABLED` / `THIRD_PARTY_MOCK_ENABLED` 控制），严禁使用构建期守卫（`import.meta.env.DEV` / `@Profile("dev")` / `process.env.NODE_ENV === 'development'`）导致部署后失效**
- [ ] mock 文件 / 函数 / 类的命名带 `mock` / `Mock` 前缀,便于一眼识别
- [ ] 已在 PRD / 详细设计 Module E 登记"等待第三方交付:vendor / api / expected_ready"
- [ ] 真实接口对接任务已在执行计划中独立成 Task,验收标准包含"删除 THIRD_PARTY_MOCK 代码"

## 七、跨 SKILL 触点

| 阶段 | SKILL | 落地点 |
| :- | :- | :- |
| 详设 | `dev-logic-architect` | Module A 接口表加"交付状态"列;Module E 登记第三方接口预计交付时间;向第三方提需求时遵循本规范第「一·C」节——只写业务诉求,不规定对方契约形态 |
| 任务规划 | `dev-execution-planner` | 边界情况"第三方平台接口未交付";第三方对接任务验收标准强制"删除 THIRD_PARTY_MOCK" |
| 编码 | (开发遵循) | 严格按本规范第三~五节标注 |
| 验收 | `code-verification-loop` | 维度 2B 第三方临时 mock 状态核验,脚本辅助:`scan_third_party_mock_antipatterns.py` |
| 测试 | `dev-manual-testcase` | 涉及第三方接口未交付的用例标注"待第三方接口到位后执行";不得作为正式回归用例 |
