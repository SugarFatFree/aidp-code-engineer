# 边界情况处理(含「情况 0:第三方未交付」)

> 本文件是 `SKILL.md` 的边界情况分片,按需 Read。**「情况 0:第三方未交付」是本文件的重点**——它决定第三方未就绪时 Task 怎么拆、mock 怎么标、后续怎么摘。

## 边界情况处理

### 情况 0:第三方平台接口未交付

若项目需对接第三方平台接口（支付宝/微信/银联/海关/OAuth IDP 等本项目以外的外部系统），但第三方接口在当前研发周期内尚未交付（未提供 base URL / 未提供凭证 / 未开放联调环境 / 未交付接口契约稳定版），应遵循以下策略：

> ⚠️ **本节后续的「Task 拆分示例（前端/后端 mock）」演示 Task 内容要素,不是最终交付格式。** 落地时每个 Task **必须**封装为独立的「**AI 执行指令**」代码块(见本文「第二步 > 🛡️ AI 执行指令四件套」+ `references/quality-review-checklist.md` 维度 4 / 维度 14b 与 `references/iteration-plan-sample.md`),**严禁仅用"执行步骤 1/2/3"序号列表直接交付**。

**🎯 Mock 方案选型优先级(Critical):**

| 优先级 | 方案 | 实现位置 | 适用场景 | 优劣势 |
|:-:|:-|:-|:-|:-|
| **P0(首选)** | **前端 mock** | 前端代码（axios/fetch 拦截器 + 运行时环境变量 + 独立 fixture 文件） | 第三方接口仅供前端调用（如 OAuth 登录回调、地图 SDK、支付收银台） | ✅ 无需后端介入，前端独立联调<br>✅ 不污染后端仓库<br>✅ 切真实接口只需关闭前端环境变量，后端零改动<br>✅ 团队协作效率最高<br>✅ 运行时可控，UAT/Demo 环境可启用 |
| P1(次选) | 后端 mock | 后端代码（统一 mock 端点 + 运行时配置开关 + if 分支） | 第三方接口供后端调用（如服务端鉴权、银行代扣、报关推送） | ⚠️ 需后端开发介入<br>⚠️ 增加后端代码复杂度<br>⚠️ 切真实接口需后端修改配置 |
| P2(最后) | 中间件 mock | 独立 mock 服务器（json-server / Mockoon / WireMock standalone） | 前后端都需调用且接口复杂、需团队共享 | ⚠️ 需额外维护 mock 服务<br>⚠️ 部署成本高，适合长期未交付的关键接口 |

**判断口诀:**
- "前端能拦截就前端拦截，前端拦截不了再让后端 mock" — 大幅减少跨角色沟通成本
- "Mock 必须运行时可控，不能构建期裁掉" — UAT/Demo 环境部署后仍需启用 mock
- "Mock 是临时占位，不是正式实现" — 不要为 mock 投入超过真实对接成本 30% 的工时

**⚠️ Mock 实现方式强制约束（对应 dev-logic-architect 核心原则 14）：**

**✅ 正确做法：运行时可控（必须）**
- 前端：环境变量开关 `VITE_THIRD_PARTY_MOCK_ENABLED=true/false` + 运行时 if 判断
- 后端：配置文件 `third-party.mock.enabled=${THIRD_PARTY_MOCK_ENABLED:false}` + `@Value` 注入 + 运行时 if 分支
- **关键特征**：打包后 mock 代码仍保留在产物中，部署时通过修改环境变量即可启用/禁用

**❌ 错误做法：构建期守卫（严禁）**
- ❌ 前端：`if (import.meta.env.DEV)` / `if (process.env.NODE_ENV === 'development')` → 打包时被 tree-shake 裁掉，UAT/Demo 环境部署后 mock 不可用
- ❌ 后端：`@Profile("dev")` / `@Profile("!prod")` → 用 prod profile 部署时类不加载，mock 失效
- **Why 错误**：UAT/Demo 环境需要部署后启用 mock 展示功能，构建期守卫在打包/编译时就被移除，部署后无法启用

**前端 mock 的标准实现方式（推荐，P0 优先）:**

**Task 拆分示例（前端 mock）:**
```markdown
#### Task 4.1: 支付宝退款接口前端 Mock 占位（待第三方交付）

**背景:** 支付宝退款接口预计 2026-06-15 交付，前端需独立联调退款流程。

**执行步骤:**
1. 配置环境变量开关
   - `.env.development` 中设置 `VITE_THIRD_PARTY_MOCK_ENABLED=true`
   - `.env.production` 中设置 `VITE_THIRD_PARTY_MOCK_ENABLED=false`（UAT/Demo 环境部署时可手动改为 true）
2. 创建 Mock 数据 fixture 文件 `src/mocks/fixtures/alipayRefund.json`
3. 在 `src/utils/request.ts` 拦截器中添加运行时判断逻辑：
   - 读取 `import.meta.env.VITE_THIRD_PARTY_MOCK_ENABLED`（运行时判断，不使用 DEV）
   - 匹配 `/alipay/trade/refund` 请求时返回 fixture 数据
   - 添加 THIRD_PARTY_MOCK 标注块（7 行：THIRD_PARTY_MOCK + 6 个必填字段）
4. 前端页面调用退款接口，验证 mock 数据流转正常

**验收标准:**
- ✅ 开发环境（`VITE_THIRD_PARTY_MOCK_ENABLED=true`）调用退款接口返回 mock 数据
- ✅ Mock 实现使用运行时环境变量判断（`import.meta.env.VITE_THIRD_PARTY_MOCK_ENABLED`），未使用构建期守卫（`import.meta.env.DEV`）
- ✅ 前端打包后，修改环境变量为 `true` 可在部署环境启用 mock
- ✅ THIRD_PARTY_MOCK 标注块包含 7 行（THIRD_PARTY_MOCK + vendor/api/since/expected_ready/owner/REMOVE_WHEN）
- ✅ 代码中无真实支付宝 SDK / 凭证 / base URL 与 mock 并存
- ✅ Mock fixture 文件独立存放（`src/mocks/fixtures/`），易于定位删除

**依赖:** 无（前端独立实现）

**待交付后清理（Task X.X）:** 支付宝真实接口交付后，删除拦截逻辑、fixture 文件，关闭环境变量开关
```

**代码实现示例（运行时可控）:**

```typescript
// src/utils/request.ts
import axios from 'axios';
import alipayRefundMock from '@/mocks/fixtures/alipayRefund.json';

const request = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  timeout: 10000
});

// THIRD_PARTY_MOCK: 支付宝退款接口未交付
// vendor: 支付宝
// api: POST /alipay/trade/refund
// since: 2026-05-26
// expected_ready: 2026-06-15
// owner: FE-张三
// REMOVE_WHEN: 真实接口可调通后立即删除本拦截逻辑，禁止保留为兜底
request.interceptors.request.use((config) => {
  // ✅ 正确：运行时判断环境变量（打包后保留此逻辑）
  const mockEnabled = import.meta.env.VITE_THIRD_PARTY_MOCK_ENABLED === 'true';
  
  if (mockEnabled && config.url?.includes('/alipay/trade/refund')) {
    console.warn('[DEV] 使用 Mock 数据拦截: /alipay/trade/refund');
    return Promise.reject({
      config,
      response: { data: alipayRefundMock, status: 200 },
      isMockResponse: true
    });
  }
  
  return config;
});

request.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.isMockResponse) {
      return Promise.resolve(error.response);
    }
    return Promise.reject(error);
  }
);

export default request;
```

**后端 mock 的实现方式（仅在前端方案不可行时使用，P1）:**

**Task 拆分示例（后端 mock）:**
```markdown
#### Task 2.3: 海关报关推送接口后端 Mock 占位（待第三方交付）

**背景:** 海关总署报关推送接口预计 2026-06-30 交付，后端服务需独立测试报关流程。

**执行步骤:**
1. 配置环境变量开关
   - `application.yml` 添加 `third-party.mock.enabled: ${THIRD_PARTY_MOCK_ENABLED:false}`
   - `application-dev.yml` 覆盖为 `third-party.mock.enabled: true`
2. 创建 Mock 数据类 `CustomsDeclareResponseMock.java`（独立文件，易于删除）
3. 在服务类 `CustomsDeclareServiceImpl.java` 中：
   - 注入 `@Value("${third-party.mock.enabled}") boolean mockEnabled`
   - 运行时 `if (mockEnabled)` 分支返回 mock 数据
   - 添加 THIRD_PARTY_MOCK 标注块（7 行：THIRD_PARTY_MOCK + 6 个必填字段）
4. 单元测试覆盖 mock 开关启用/禁用两种场景

**验收标准:**
- ✅ 开发环境（`third-party.mock.enabled=true`）调用报关接口返回 mock 数据
- ✅ Mock 实现使用运行时配置开关（`@Value` + if 分支），未使用构建期 Profile（`@Profile("dev")`）
- ✅ 部署后修改环境变量 `THIRD_PARTY_MOCK_ENABLED=true` 可在任意环境启用 mock
- ✅ THIRD_PARTY_MOCK 标注块包含 7 行（THIRD_PARTY_MOCK + 6 个必填字段）
- ✅ 代码中无真实海关 SDK / 凭证 / base URL 与 mock 并存

**依赖:** Task 1.2 基础配置完成

**待交付后清理（Task X.X）:** 海关真实接口交付后，删除 mock 数据类、if 分支，移除配置项
```

**代码实现示例（运行时可控）:**

```java
// com.project.service.impl.CustomsDeclareServiceImpl.java
package com.project.service.impl;

import com.project.mocks.CustomsDeclareResponseMock;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class CustomsDeclareServiceImpl implements CustomsDeclareService {
    
    // ✅ 正确：运行时注入配置（任意环境可通过环境变量切换）
    @Value("${third-party.mock.enabled}")
    private boolean mockEnabled;
    
    @Autowired
    private CustomsApiClient customsApiClient;
    
    @Override
    public DeclareResponse submitDeclaration(DeclareRequest request) {
        // THIRD_PARTY_MOCK: 海关总署报关推送接口未交付
        // vendor: 海关总署单一窗口
        // api: POST /customs/declare
        // since: 2026-05-26
        // expected_ready: 2026-06-30
        // owner: BE-李四
        // REMOVE_WHEN: 真实接口可调通后立即删除 if (mockEnabled) 分支和 CustomsDeclareResponseMock 类
        if (mockEnabled) {
            log.warn("[DEV] 使用 Mock 数据: 海关报关推送接口");
            return CustomsDeclareResponseMock.buildSuccess(request.getDeclarationNo());
        }
        
        // 真实调用
        return customsApiClient.declare(request);
    }
}
```

1. **详细设计 Module E 登记**:在详细设计的 Module E 待澄清清单中登记"等待第三方接口交付:vendor={供应商} / api={接口路径} / expected_ready={预计交付日期} / mock 位置=前端|后端|中间件"
2. **Phase 3/4 任务拆解时——强制拆分为 5 个独立 Task（Critical）**:
   
   为每个第三方接口对接创建以下**独立、不可合并**的任务链：
   
   **Task X.1: Mock 开关配置**
   - 内容：添加环境变量声明（`.env.development` / `application.yml`）
   - 验收：配置文件中存在 mock 开关，默认值正确（dev=true, prod=false）
   
   **Task X.2: Mock 实现代码**
   - 内容：
     - 前端：拦截器 + 运行时 if 判断（`import.meta.env.VITE_THIRD_PARTY_MOCK_ENABLED`）
     - 后端：服务类 + 运行时 if 分支（`@Value` + `if (mockEnabled)`）
   - 验收：Mock 使用运行时可控方式（非构建期守卫），THIRD_PARTY_MOCK 标注块完整
   
   **Task X.3: Mock 数据 Fixture**
   - 内容：
     - 前端：独立 JSON 文件（`src/mocks/fixtures/{vendor}{api}.json`）
     - 后端：独立 Java 类（`com.project.mocks.{Vendor}{Api}MockData.java`）
   - 验收：Fixture 独立存放，不散落在业务组件中
   
   **Task X.4: 真实接口对接**
   - 前置依赖：第三方接口交付
   - 内容：切换到真实接口调用，验证联调通过
   - 验收：真实接口可正常调用，返回预期数据
   
   **Task X.5: Mock 清理验证**
   - 前置依赖：Task X.4 完成
   - 内容：
     - 删除 Task X.2 的拦截逻辑 / if 分支
     - 删除 Task X.3 的 Fixture 文件 / Mock 数据类
     - 关闭或删除 Task X.1 的环境变量开关
     - 运行 `python3 <SKILL_DIR>/scripts/scan_mock_data.py <代码目录> --third-party-mode`(项目若自有 mock 残留检查命令,如 `npm run check-mock-residue`,可一并运行)
   - 验收：
     - ✅ 代码中无 `THIRD_PARTY_MOCK` 标注块残留
     - ✅ Mock Fixture 文件已删除
     - ✅ 环境变量开关已禁用或删除
     - ✅ 扫描脚本输出"无残留"
   
   **Why 强制拆分 5 个 Task:**
   - 开关/实现/数据分离 → 清理时精准定位，不会漏删
   - Task X.5 显式列入研发执行计划 → 开发者不会忘记清理
   - 结构化任务 → 与 `code-verification-loop` 扫描规则对齐，验收阶段不返工
   
   **优先采用前端 mock 方案**：
   - Phase 4 前端任务直接落 Task X.1~X.3（前端实现）
   - Phase 3 后端无需创建 Task X.1~X.3（节省后端工时）
   - 仅当第三方接口供后端服务端调用时，才在 Phase 3 创建后端 mock 任务

3. **临时 mock 标注协议**:允许使用带 `THIRD_PARTY_MOCK` 标注的临时 mock 占位，标注块必须包含完整的 7 行（THIRD_PARTY_MOCK 标识 + 6 个必填字段，每行独占）：
   ```typescript
   // THIRD_PARTY_MOCK: {一句话说明}
   // vendor: {第三方供应商名称，如：支付宝 / 微信支付 / 企业微信 / 海关总署 / OAuth-IDP}
   // api: {对接的接口路径或方法，如：POST /alipay/trade/refund}
   // since: {开始使用 mock 的日期，YYYY-MM-DD}
   // expected_ready: {第三方预计交付的日期，YYYY-MM-DD；未知填 UNKNOWN}
   // owner: {负责人，如：PM-张三 / FE-李四 / BE-王五}
   // REMOVE_WHEN: 真实接口可调通后立即删除本{函数/常量/文件}，禁止保留为兜底
   export async function mockAlipayRefund(orderId: string) { ... }
   ```
   **关键判定规则：**
   - mock 与真实 vendor SDK / 凭证 / base URL 并存 → 🔴 Critical
   - mock 在 catch / `||` / fallback 路径中被调用 → 🔴 Critical
   - `expected_ready` 已过期超过 14 天 → 🔴 Critical
   - 标注块缺必填字段任一 → 🔴 Critical
   - **Mock 使用构建期守卫（`import.meta.env.DEV` / `@Profile("dev")`）** → 🔴 Critical

4. **Phase 5 验收任务**:Mock 残留扫描任务必须启用 `--third-party-mode`，核验：
   - 标注块必填字段完整性
   - mock 与真实 vendor client（SDK/凭证/base URL）不并存
   - mock 不在 catch/fallback 路径中被调用
   - expected_ready 未过期超过 14 天
   - **Mock 实现方式为运行时可控（非构建期守卫）**

5. **依赖关系**:第三方接口对接任务（Task X.4）标记为"外部依赖"，不阻塞其他 Phase 任务，但清理任务（Task X.5）必须在最终验收前完成

6. **严禁 mock 兜底**:一旦真实接口可用或开始对接（代码中出现真实 vendor SDK 引用/凭证配置/base URL），mock 必须立即删除，严禁与真实调用并存或保留为兜底

**与情况 1 的区别:**
- 情况 1（同项目后端接口尚未部署）:不允许 mock，通过 Phase 任务依赖关系等待后端实现
- 情况 0（第三方平台接口未交付）:允许带 `THIRD_PARTY_MOCK` 标注的临时 mock，但一旦真实接口可用必须立即删除

**下游协作:**
- `dev-logic-architect`: 核心原则 14「第三方接口临时 Mock 运行时可控原则」，A.2 章节「第三方接口临时 Mock 实现规范」
- `code-verification-loop`: 维度 2B 第三方临时 mock 协议核验，**新增反模式检查：构建期裁掉（DEV guard / @Profile）、真实对接后残留**
- `dev-manual-testcase`: 涉及未交付接口的用例标 `[待第三方交付]`，**测试场景需覆盖 Mock 全生命周期（开发用 mock/真实、部署用 mock、真实对接后清理验证）**

### 情况 1:接口已定义但后端尚未部署

若详细设计或接口文档中已定义后端接口,但后端服务尚未部署到可访问环境(如本地开发、测试环境),前端开发应遵循以下策略:

**🎯 临时调试 Mock 方案选型(必读):**

**核心原则:同项目后端接口未部署 ≠ 接口未定义。** 既然接口契约已明确(URL、参数、返回结构),前端可基于契约自行 mock,**完全无需要求后端先搭一个返回假数据的临时实现**。

| 优先级 | 方案 | 实现位置 | 评价 |
|:-:|:-|:-|:-|
| **P0(强烈推荐)** | **前端拦截器 mock** | 前端 axios/fetch 拦截器,基于接口契约返回假数据 | ✅ 前端独立调试,不阻塞后端正式开发<br>✅ 后端无需写一次性废弃代码<br>✅ 切真实接口只需关闭前端拦截 |
| P1 | MSW(Mock Service Worker) | 前端 Service Worker 拦截网络请求 | ✅ 不污染业务代码,生产构建自动剔除<br>⚠️ 需配置 Service Worker |
| P2 | 本地 mock 服务器 | json-server / Mockoon 独立部署 | ⚠️ 需团队约定共享地址<br>⚠️ 适合多前端开发者并行场景 |
| ❌ **不推荐** | 要求后端先写假数据接口 | 后端临时返回硬编码假数据 | ❌ 后端做无用功,占用正式开发工时<br>❌ 假数据接口容易遗忘清理,污染代码仓 |

**判断口诀:** "前端不要催后端写假数据,前端自己拦截器搞定" — 这是同项目后端未部署场景下提升团队效率的关键。

1. **Phase 4 任务拆解时**:仍然要求最终删除 mock 数据,但执行步骤中标注"前端 mock 拦截调试,等待后端接口部署后切真实接口联调"
2. **验收标准调整**:将"联调后端真实接口通过"改为"前端 mock 拦截已移除,接口调用代码完整,等待后端部署后联调"
3. **依赖关系**:前端任务依赖对应的 Phase 3 后端接口任务完成,但**前端不阻塞**(可基于契约 mock 联调推进)
4. **临时方案(优先前端,严禁后端代写)**:

   **✅ 推荐 — 前端 axios 拦截器(最简单):**
   ```typescript
   // src/mocks/dev-interceptor.ts
   if (import.meta.env.DEV) {
     axios.interceptors.request.use((config) => {
       if (config.url === '/api/user/list') {
         // DEV_MOCK: 后端 GET /user/list 接口未部署
         // since: 2026-05-26
         // owner: FE-张三
         // REMOVE_WHEN: 后端接口部署到 dev 环境后立即删除本拦截块
         return Promise.reject({ __mock__: true, data: { code: 0, list: [...] } });
       }
       return config;
     });
   }
   ```

   **✅ 推荐 — MSW(适合需要拦截多个接口的场景):**
   ```typescript
   // src/mocks/handlers.ts(生产构建自动剔除)
   import { rest } from 'msw';
   // DEV_MOCK: 后端 GET /user/list 接口未部署
   // since: 2026-05-26
   // owner: FE-张三
   // REMOVE_WHEN: 后端接口部署到 dev 环境后立即删除本文件与 setupWorker 调用
   export const handlers = [
     rest.get('/api/user/list', (req, res, ctx) => {
       return res(ctx.json({ code: 0, list: [...] }));
     }),
   ];
   ```

   **❌ 严禁 — 让后端写假数据接口:**
   ```java
   // ❌ 反模式:后端写一次性假数据接口,污染代码仓
   @GetMapping("/user/list")
   public Result list() {
     return Result.ok(Arrays.asList(new User("张三"), new User("李四")));  // ❌ 临时假数据
   }
   ```

   **共同要求:**
   - 在代码注释中明确标注"DEV_MOCK,生产环境自动禁用"+ 移除条件(REMOVE_WHEN)
   - 使用环境变量控制 mock 开关(如 `if (import.meta.env.DEV) { setupMockServer() }`)
   - 在 Phase 5 的 Mock 残留扫描任务中验证生产构建不包含 mock 代码
   - **⚠️ 情况 1 与情况 0(第三方未交付)的 mock 守卫策略相反,不要混用**:情况 1 是**同项目本地 dev 调试 mock**,本就应在生产构建被 tree-shake 剔除,故用 `import.meta.env.DEV` 构建期守卫**正确**;而情况 0 的 `THIRD_PARTY_MOCK` 需在 UAT/Demo 部署后仍运行时可控,**严禁**构建期守卫(否则部署后失效,详见情况 0 与 dev-logic-architect 核心原则 14)
   - **⚠️ 扫描器的严重度也按标记分流,别拿情况 0 的结论套情况 1**:`code-verification-loop` 维度 2B 的
     `scan_third_party_mock_antipatterns.py` 里「构建期守卫 = 🔴 Critical」**只对 `THIRD_PARTY_MOCK` 成立**;
     对 `DEV_MOCK` 它反过来判 —— **用了运行时开关才提示**(🟡 Important,那意味着这个 dev mock 在生产
     有机会被打开)。`dev-logic-architect` 的 `check_third_party_mock_runtime.py`(核心原则 14)同口径:
     设计文档里**只含 `DEV_MOCK` 标注的代码块**不查构建期守卫。
   - **`DEV_MOCK` 标注块的三个必填字段是机器可读的硬要求**:`since` / `owner` / `REMOVE_WHEN`,缺任一判 🔴 Critical;
     `since` 计龄超阈值(默认 14 天)判 🟡 Important(后端接口大概率早已部署,该清了)。
     ⚠️ **无字段块的裸标记等于没标** —— 「没写字段块」与「压根没写标记」在扫描面上完全同形,任何机器门都认不出来。

### 情况 2:接口文档不完整或与设计方案冲突

若接口文档与详细设计方案中的接口定义存在冲突(如路径不一致、字段缺失),应:

1. 在 `⚠️ 一致性问题` 章节中列出所有冲突项
2. 与用户确认以哪份文档为准
3. 任务拆解时统一使用确认后的接口定义
4. 在输出计划的开头明确标注"接口定义以 {文档名称} 为准"

---
