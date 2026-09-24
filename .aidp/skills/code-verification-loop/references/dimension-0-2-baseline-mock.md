# code-verification-loop · 维度 0（静态基线门）· 维度 1（功能完整性）· 维度 2A / 2B（Mock）

> 本文件是 `SKILL.md` 的按需加载分片：执行到对应维度 / 步骤时 Read。通用判据（严重度定义、三方冲突裁决、最高约束「全程静态」、基线对照有效性铁律）以 `SKILL.md` 为准，本文件不重复。

#### 维度 0: 静态基线门（**前置，不计入 15 维度**）

> **为什么必须前置：** 本 SKILL 的整个立论是「静态能拦的就静态拦下、别等部署期」——维度 6/7/8
> 三个盲区维度正是这么来的。而**类型检查与 lint 是最廉价、最确定、且本 SKILL 明文允许**的静态手段
> （见最高约束第 0 条的豁免项）。若它只停留在「允许做什么」而不是「必须做什么」，一个带编译错误 / 类型错误的
> 分支就可以通过全部 15 个维度——立论与检查项之间出现直接落差，故设为前置门。

| 项目类型 | 命令 | 判定 |
| :- | :- | :- |
| TypeScript / Vue | `npx --no-install vue-tsc --noEmit`（Vue）或 `npx --no-install tsc --noEmit` | 非零退出 = 🔴 Critical |
| 有 eslint 配置 | `npx --no-install eslint <本次改动文件>` | **error** = 🔴 Critical；warning = 🟡 记录不阻断 |
| Java / Spring | **本档不做**（理由见下） | — |

- **非零退出即直接回 Agent1 修复，不必往下走 15 维度**——省 token 也省循环轮次。
- ⚠️ **`npx` 必须带 `--no-install`**（npm 7+ 亦可写 `npx --no`）：裸 `npx` 的语义是
  "Run a command from a local or **remote** npm package"——包不在本地时它会**去 registry 下载**，
  且非 TTY 环境（Agent 的 bash 正是）不弹确认、直接装。那样下面「工具缺失则跳过」这条分支
  **永远走不到**，而"联网装包"正是本 SKILL 最高约束要排除的外部副作用。
  也可直接用 `./node_modules/.bin/tsc`，效果相同。
- ⚠️ **Java 侧刻意不做，别"顺手补上" `mvn compile`**：它看起来只是编译，实际会跑完
  validate → initialize → **generate-sources → process-sources → generate-resources** → compile
  整条 lifecycle，**绑定在这些相上的插件全部执行**——最常见的 `frontend-maven-plugin` 官方默认
  就绑在 `generate-resources`，于是 `mvn compile` 会真的去跑 `npm install` + `npm run build`，
  即一条写着"只编译不打包"的命令可以直接触发 `SKILL.md` 最高约束明文严禁的 `npm run build`；无 `-o` 时它还必然
  联网拉依赖、向 `target/` 落 `.class` 产物。Java 的装配类问题由**维度 6**（纯 grep、零构建）覆盖，
  编译期错误交 CI，**不在本档处理**。
- ⚠️ **本档只用最高约束白名单里明列的手段**（`vue-tsc --noEmit` / `tsc --noEmit` / lint），
  不得自行扩充。**严禁**升级为 `pnpm build` / `vite build` / `mvn package`。
- **存量不卡本轮**（与维度 6「精度优先零误阻断」、维度 8「存量技术债不该卡本轮验收」同口径）：
  eslint 只跑**本次改动文件**且 warning 不阻断；`tsc --noEmit` 无法只查改动文件，
  **首轮记录存量错误数作基线，只对增量判 Critical**——否则接手一个有历史类型错误的项目会 100% 阻塞，
  且问题与本次改动无关，Agent1 会被派去修不属于本任务的存量代码。
- 工具未安装时（`--no-install` 下会直接失败）标「⏭️ 跳过（工具缺失：<原因>）」并在报告写明，
  **不得**因此升级为全量 build、也不得改用会联网安装的裸 `npx`。

---

#### 维度 1: 功能完整性检查

**检查方法：**
1. 对照任务描述/PRD 功规点，逐项验证功能是否实现
2. 对照研发执行计划（如有），检查每个 Task 的验收标准是否满足
3. Bug 修复场景：复现原始问题路径，验证是否真正解决
4. 检查边界条件：空数据、超长输入、并发操作、权限控制
5. **三方文档一致性检查**：对照 PRD、原型、详细设计三类文档交叉核验代码实现，按"三方冲突裁决规则"（见核心原则第 6 条）判定：
   - 字段标签、按钮文案、错误提示、校验规则、枚举值、权限分级、业务流程步骤 → 与 **PRD** 比对（冲突以 PRD 为准，即使代码与原型一致）
   - 接口 URL、请求/返回字段、表结构、字段类型、技术栈 → 与**详细设计**比对（冲突以详细设计为准，即使代码与 PRD 中技术描述一致）
   - 代码实现了原型有但 PRD 未提及的功能 → 标注 Important"原型补充功能，待确认"
   - PRD 要求但代码未实现的功能 → 标注 Critical"功能缺失"
6. **产品 PRD 原文条目级存在性回检（Critical，有产品 PRD 输入时强制）**：**以「产品原始 PRD 原文」（`docs/requirements/{version}/产品提供/*.md`）为独立基准**，逐条回检「实现里到底有没有这个按钮 / 这一列 / 这个操作 / 这条规则」，**绕过详细设计 + ux-logic-extractor 研发需求文档两层加工产物、直连产品端原文**，正文引用产品 PRD 的条目号/章节号。上述第 1~5 项的一致性核验均以「任务描述内的 PRD 功规点」或 AIDP 加工产物为基准，若 ux 提取阶段就把某条 PRD 条目整条漏掉，那些基准里根本不含该条、无从发现——本项即补这层**同源污染**防线：命中「产品 PRD 原文有、实现无」→ **Critical 功能缺失/漏项**，回修复团队（Agent1）。判定时须逐条标注对应的产品 PRD 条目号，未提供产品 PRD 原文时本项跳过（不降低其余检查）。

**输出格式：**
```
| 功能点/Bug | 状态 | 说明 |
|-----------|------|------|
| 用户列表分页 | ✅ 通过 | 分页参数正确传递，数据正确展示 |
| 用户创建表单 | ❌ 未通过 | 手机号校验缺失，允许非法格式 |
| 用户状态枚举 | ❌ 未通过 | 代码实现为"启用/停用/待审核"（与原型一致），但 PRD 定义为"启用/停用"两种 → 按 PRD 修改 |
```

---

#### 维度 2A: Mock 数据清除检查(普通 mock 零容忍)

**适用场景:** 存在接口定义时必检(详细设计或独立接口文档中已定义后端接口)

**扫描范围:** 前端项目的 `src/` 目录(或用户指定的前端代码目录)

**检查清单:**

| 序号 | 检查项 | 扫描方式 | 严重级别 |
|------|--------|---------|---------|
| 2A.1 | 组件内硬编码的静态数组(`const data = [...]`、`const list = [...]`、`mockData`、`fakeList`) | `grep -rn` 关键词扫描 | 🔴 Critical |
| 2A.2 | `mock/`、`mocks/`、`__mocks__/` 目录下的 mock 文件 | `find` 目录扫描 | 🔴 Critical |
| 2A.3 | API 层中返回假数据的函数(`return Promise.resolve(fakeData)`、`return { data: [...] }`) | `grep -rn` 扫描 API 目录 | 🔴 Critical |
| 2A.4 | Mock.js、MSW、json-server 等 mock 工具的配置和调用 | `grep -rn` 工具关键词 | 🔴 Critical |
| 2A.5 | 组件 `data()` / `setup()` / `ref()` 中用于模拟接口返回的静态对象 | 逐文件审查(**脚本不覆盖,人工核验**) | 🔴 Critical |
| 2A.6 | `// TODO: 替换为真实接口`、`// FIXME: mock` 等注释标记 | `grep -rn` 注释扫描 | 🟡 Important |
| 2A.7 | **Mock 兜底逻辑**:`catch` 块中回退到假数据、`\|\|` 运算符后接静态数组 | `scan_mock_data.py` 覆盖常见 `catch(...)=>[ ` / `catch{...=[ ` / `\|\| [{` 模式;复杂兜底分支需逐文件人工核验 | 🔴 Critical |

**扫描命令:**

```bash
# 完整扫描(文本输出)
python3 <SKILL_DIR>/scripts/scan_mock_data.py src/

# JSON 格式输出(供 Agent 解析)
python3 <SKILL_DIR>/scripts/scan_mock_data.py src/ --json

# 严格模式(任何问题都返回非零退出码)
python3 <SKILL_DIR>/scripts/scan_mock_data.py src/ --strict

# ⚠️【项目存在第三方平台接口对接、**或**前端用了 DEV_MOCK 拦截时必须加此旗标】
# 把带 THIRD_PARTY_MOCK **或 DEV_MOCK** 标注块的代码从 2A「零容忍」中豁免、转交维度 2B 协议核验。
# 漏加会把**完全合规的 2B mock** 判成 2A Critical + exit 1,验收循环把合规代码打回"修复"
# —— 等于 2B 整档被 2A 顶掉,正是 2B 豁免协议要防的事。
# ⚠️ **DEV_MOCK 与 THIRD_PARTY_MOCK 同样豁免** —— 否则 planner 情况 1 的两种 ✅ 推荐写法
#    (axios 拦截器 / MSW)会在 2A 被判 Critical + exit 1,即「照着示例写反被扫描器判 Critical」。
# ⚠️ **只有字段完整(since/owner/REMOVE_WHEN)的 DEV_MOCK 块才买得到豁免** ——
#    否则「写个裸标记就能关掉 2A」会变成后门;缺字段本身由 2B 判 Critical。
# ⚠️ DEV_MOCK 的豁免**不受「真实 vendor SDK 并存」条件影响** —— 那个条件讲的是
#    「第三方真实 SDK 已经接上了」,与同项目后端部署与否毫无关系。
python3 <SKILL_DIR>/scripts/scan_mock_data.py src/ --third-party-mode --json
```

> **2A 与 2B 的脚本分工**(别以为二选一,两个都要跑)：
> `scan_mock_data.py --third-party-mode` 管**2A 侧的豁免**与标注块字段完整性；
> `scan_third_party_mock_antipatterns.py` 管**2B 侧的反模式 1/2 与真实对接信号**。二者字段校验有重叠是刻意的(互为兜底)。

备用 Shell 命令(仅 Linux/macOS):
```bash
# 2A.1 硬编码假数据
grep -rn "mockData\|fakeData\|mockList\|fakeList\|demoData\|testData\|sampleData" src/ --include="*.vue" --include="*.ts" --include="*.js" --include="*.tsx" --include="*.jsx"

# 2A.2 mock 目录
find src/ -type d \( -name "mock" -o -name "mocks" -o -name "__mocks__" -o -name "fake" \)

# 2A.4 mock 工具
grep -rn "Mock\.mock\|setupWorker\|setupServer\|json-server\|mockjs\|better-mock" src/ package.json

# 2A.6 TODO/FIXME 注释
grep -rn "TODO.*接口\|TODO.*mock\|TODO.*真实\|FIXME.*mock\|FIXME.*假\|HACK.*mock" src/
```

---

#### 维度 2B: 第三方临时 Mock 协议核验 + 全生命周期状态检查

**适用场景:** 项目对接第三方平台接口（支付宝/微信/银联/海关/OAuth IDP 等本项目以外的外部系统）

**核心规则:**
1. 第三方接口未交付时允许临时使用 mock 占位；一旦真实接口可用或开始对接，mock 必须立即删除，严禁与真实调用并存或保留为兜底
2. **Mock 实现必须是运行时可控的**（环境变量开关），严禁使用构建期守卫导致部署后失效
3. 真实接口对接完成后，mock 代码必须彻底清理（拦截逻辑/fixture/开关配置）

> **⚠️ Mock 守卫策略按标记分流，⛔ 不要混用（两个 SKILL 同一口径，各持一份副本）：**
> **`THIRD_PARTY_MOCK`**（第三方未交付）**必须运行时开关**——它要活到 UAT/Demo，构建期守卫会让它部署后失效；
> **`DEV_MOCK`**（同项目后端未部署）**应当构建期裁掉**——它绝不能进生产，`import.meta.env.DEV` 这类守卫正是要求的合规形态。
> **扫描器的「构建期守卫 = Critical」只对 `THIRD_PARTY_MOCK` 成立**；对 `DEV_MOCK` 反过来判——用了运行时开关才提示（那意味着它在生产有机会被打开）。
> 标记定义与推荐写法的单一信源在 `dev-execution-planner/references/flow-edge-cases.md` 情况 0 / 情况 1。
>
> | 标记 | 场景 | 守卫期望 | 必填字段 | 字段缺失 | 计龄超阈 |
> | :- | :- | :- | :- | :-: | :-: |
> | `THIRD_PARTY_MOCK` | 第三方未交付 | **运行时开关** | vendor / api / since / expected_ready / owner / REMOVE_WHEN | 🔴 Critical | 🔴 Critical（`expected_ready`） |
> | `DEV_MOCK` | 同项目后端未部署 | **构建期裁掉** | since / owner / REMOVE_WHEN | 🔴 Critical | 🟡 Important（`since` 计龄） |
>
> ⚠️ **没有任何标记的 mock 不归维度 2B 管**——那由维度 2A 的 `scan_mock_data.py`（普通 mock 零容忍）承担。
> 2B 管的是「**已声明**的临时 mock 合不合协议」。

**标注协议:** 对照 `references/third-party-mock-protocol.md`，每个第三方临时 mock 必须带完整标注块：

```typescript
// THIRD_PARTY_MOCK: {一句话说明}
// vendor: {第三方供应商名称}
// api: {对接的接口路径或方法}
// since: {开始使用 mock 的日期，YYYY-MM-DD}
// expected_ready: {第三方预计交付的日期，YYYY-MM-DD；未知填 UNKNOWN}
// owner: {负责人}
// REMOVE_WHEN: 真实接口可调通后立即删除本{函数/常量/文件}，禁止保留为兜底
export async function mockAlipayRefund(orderId: string) { ... }
```

**检查清单:**

| 序号 | 检查项 | 判定条件 | 严重级别 |
|------|--------|---------|---------|
| 2B.1 | 标注块必填字段完整性 | 缺失 `vendor` / `api` / `since` / `expected_ready` / `owner` / `REMOVE_WHEN` 任一字段 | 🔴 Critical |
| **2B.2** | **Mock 运行时可控性（反模式 1：构建期裁掉）** | **前端 mock 使用 `import.meta.env.DEV` / `process.env.NODE_ENV === 'development'` 等构建期守卫 → 打包后被 tree-shake 裁掉，UAT/Demo 环境部署后 mock 不可用**<br>**后端 mock 使用 `@Profile("dev")` / `@Profile("!prod")` / `#if DEBUG` 等构建期隔离 → 用 prod profile 部署后 mock 类不加载** | 🔴 Critical |
| 2B.3 | mock 与真实 client 并存（反模式 2：真实对接后残留） | 代码仓已出现真实 vendor SDK 引用 / base URL 配置 / 凭证配置 / `new XxxClient(...)`，但 mock 代码仍存在 | 🔴 Critical |
| 2B.4 | mock 兜底逻辑 | mock 函数在 `catch` / `\|\|` / fallback 路径中被调用 | 🔴 Critical |
| 2B.5 | 过期未删除 | `expected_ready` 已过期超过 14 天 | 🔴 Critical |
| **2B.6** | **真实对接后残留检查（反模式 2 增强）** | **`.env.*` 文件中 baseURL 已切换到真实地址（非 localhost/127.0.0.1/mock），但以下残留仍存在：**<br>- Mock 开关变量仍为 `true`（如 `VITE_THIRD_PARTY_MOCK_ENABLED=true`）<br>- Mock fixture 文件仍存在（`src/mocks/fixtures/*.json` / `*MockData.java`）<br>- Mock 拦截逻辑仍在代码中（if 分支/拦截器未删除）| 🔴 Critical |
| 2B.7 | 合规但待 follow-up | 标注完整且无真实 client，mock 实现为运行时可控，但下次 Review 必查进度 | 🟡 Important |
| 2B.8 | Mock 实现位置选型不当（**人工核验为主,脚本不覆盖**） | 第三方接口仅供前端调用（OAuth 回调/收银台/SDK 跳转等），却采用后端 mock 实现（违反核心原则 1 的"前端能拦截就前端拦截"选型优先级）。判定:对照该接口是否只在前端发起调用——是则后端不应有其 mock 占位 | 🟡 Important |

**"已开始对接"判定信号（任一命中即视为并存）:**

- vendor SDK 引用：`import { AlipayClient } from '@alipay/sdk'` / `import com.alipay.api.*`（✅ 脚本覆盖）
- 真实 base URL 配置（后端）：`alipay.base.url=https://openapi.alipay.com`（非 mock 占位）（✅ **脚本覆盖**:保守认厂商生产域名 + `base-url` 真实 https,排除 localhost/sandbox/mock/占位）
- 真实凭证配置（后端）：`alipay.app.id=2025xxx` / `alipay.private.key=`（非 `MOCK_` / `TODO` 占位）（⚠️ **脚本不覆盖,需人工 grep**;凭证误报风险高,刻意不自动判）
- 客户端实例化代码：`new AlipayClient(...)` / `RestTemplate/FeignClient + alipay`（✅ 脚本覆盖）
- **前端 baseURL 切换到真实地址**：`.env.*` 中 `VITE_API_BASE_URL` / `REACT_APP_API_BASE_URL` / `API_BASE_URL` 从 `http://localhost:*` / `http://127.0.0.1:*` / `http://mock.*` 切换到真实域名（✅ 脚本覆盖）

> **脚本覆盖边界(避免误判已查):** `scan_third_party_mock_antipatterns.py` 自动检测 vendor SDK / 后端配置真实 base URL（`.yml`/`.properties`,保守认厂商生产域名 + `base-url` 真实 https）/ `new XxxClient`+RestTemplate/Feign / 前端 `.env` baseURL;**仅后端凭证(`app.id`/`private.key`)脚本不实现(误报风险高),须人工 grep `application.yml`/`*.properties`**。

**反模式 1 扫描（构建期裁掉）：**

**通用判据**：mock 的启用与否**必须运行时可控**（部署后改环境变量/配置即可切换），**严禁任何构建期守卫/构建期隔离**——它们在 production 打包时被整段裁掉或不加载，导致 UAT/Demo 环境部署后 mock 根本不可用，而那恰恰是最需要 mock 的环境。命中 → 🔴 Critical。

**⚠️ 各栈的具体反模式写法与正确写法（代码示例）按需加载**：

| 被测技术栈 | 加载 | 该栈典型构建期反模式 |
| :- | :- | :- |
| 前端 Vue | `references/stack-vue.md` §1.1 | `import.meta.env.DEV` / `process.env.NODE_ENV === 'development'` |
| 前端 React | `references/stack-react.md` §1.1 | 同上，另有 CRA `REACT_APP_*` / Next `NEXT_PUBLIC_*` **构建时静态替换**陷阱 |
| Java / Spring | `references/stack-java-spring.md` §4.1 | `@Profile("dev")` / `@Profile("!prod")` / `#if DEBUG` |
| Node.js | `references/stack-nodejs.md` §三 | `NODE_ENV` 判断、`@Module` 条件装配裁掉 mock provider |

**反模式 2 扫描（真实对接后残留）：**

**残留检查通用判据**：一旦第三方 base URL 已从 mock/sandbox 切到**真实地址**，即视为「开始真实对接」，此时 mock 开关、fixture 文件、拦截分支、`THIRD_PARTY_MOCK` 标注块**必须全部删除**，严禁与真实调用并存或保留为兜底 → 残留即 🔴 Critical。

`scan_third_party_mock_antipatterns.py` 已能自动扫：vendor SDK 引用 / 后端配置（`.yml`/`.properties`）的真实 base-url 信号 / `new XxxClient`+RestTemplate/Feign / 前端 `.env` baseURL；**后端凭证（`app.id`/`private.key`）脚本不实现（误报风险高），须人工 grep**。

**⚠️ 各栈的残留清单（查哪些文件、哪些变量名）按需加载**：`references/stack-vue.md` §1.2（`VITE_*` 开关、`src/mocks/fixtures/*.json`、拦截器分支）/ `stack-react.md` §1.2（另含 **MSW 的 `worker.start()` 调用点**——只删 handler 不删 start，Service Worker 仍会注册）/ `stack-java-spring.md` §4.2（`third-party.mock.enabled`、`*MockData.java`、`if(mockEnabled)` 分支、后端凭证）/ `stack-nodejs.md` §三。
