# 维度 0（静态基线门）+ 基线有效性铁律 + 维度 1 / 2A / 2B / 3 判据全文

> 文中「核心原则 N」「最高约束」「输入要求」「Step N」「分片索引」均指 [`../SKILL.md`](../SKILL.md) 的同名章节；各维度的**强制结论**（档位、门控、机器门命令）在骨架里，本文件是它们的「怎么做」全文，**外置的是方法、不是强制度**。

#### 维度 0: 静态基线门（**前置，不计入 15 维度**）

> **为什么必须前置：** 本 SKILL 的整个立论是「静态能拦的就静态拦下、别等部署期」——维度 6/7/8
> 三个盲区维度正是这么来的。而**类型检查与 lint 是最廉价、最确定、且本 SKILL 明文允许**的静态手段
> （见最高约束第 0 条的豁免项），此前却只出现在「允许做什么」的白名单与「lint 拦不住所以要维度 7/8」
> 的反面论证里，**从无一处是「必须做什么」**。结果是：一个带编译错误 / 类型错误的分支可以通过全部
> 计数维度（总数以 [`../SKILL.md`](../SKILL.md) 维度标题编号最大值为准，⛔ 不在此写死）。这是立论与检查项之间的直接落差，故补为前置门。

| 项目类型 | 命令 | 判定 |
| :- | :- | :- |
| TypeScript / Vue | `npx --no-install vue-tsc --noEmit`（Vue）或 `npx --no-install tsc --noEmit` | 非零退出 = 🔴 Critical |
| 有 eslint 配置 | `npx --no-install eslint <本次改动文件>` | **error** = 🔴 Critical；warning = 🟡 记录不阻断 |
| Java / Spring | **本档不做**（理由见下） | — |

- **`mode=loop`：非零退出即直接回 Agent1 修复，不必往下走 15 维度**——省 token 也省循环轮次。
  **`mode=verify-only`：记 🔴 Critical 后仍跑完其余维度**——它只有一轮、修复归调用方，短路会让调用方拿到一份残缺清单、修完再验又冒出一批。
- ⚠️ **`npx` 必须带 `--no-install`**（npm 7+ 亦可写 `npx --no`）：裸 `npx` 的语义是
  "Run a command from a local or **remote** npm package"——包不在本地时它会**去 registry 下载**，
  且非 TTY 环境（Agent 的 bash 正是）不弹确认、直接装。那样下面「工具缺失则跳过」这条分支
  **永远走不到**，而"联网装包"正是本 SKILL 最高约束要排除的外部副作用。
  也可直接用 `./node_modules/.bin/tsc`，效果相同。
- ⚠️ **Java 侧刻意不做，别"顺手补上" `mvn compile`**：它看起来只是编译，实际会跑完
  validate → initialize → **generate-sources → process-sources → generate-resources** → compile
  整条 lifecycle，**绑定在这些相上的插件全部执行**——最常见的 `frontend-maven-plugin` 官方默认
  就绑在 `generate-resources`，于是 `mvn compile` 会真的去跑 `npm install` + `npm run build`，
  即一条写着"只编译不打包"的命令可以直接触发 [`../SKILL.md`](../SKILL.md) 最高约束明文严禁的 `npm run build`；无 `-o` 时它还必然
  联网拉依赖、向 `target/` 落 `.class` 产物。Java 的装配类问题由**维度 6**（纯 grep、零构建）覆盖，
  编译期错误交 CI，**不在本档处理**。
- ⚠️ **本档只用最高约束白名单里明列的手段**（`vue-tsc --noEmit` / `tsc --noEmit` / lint），
  不得自行扩充。**严禁**升级为 `pnpm build` / `vite build` / `mvn package`。
- **存量不卡本轮**（与维度 6「精度优先零误阻断」、维度 8「存量技术债不该卡本轮验收」同口径）：
  eslint 只跑**本次改动文件**且 warning 不阻断；`tsc --noEmit` 无法只查改动文件，
  **以改动前代码的错误数作存量基线，只对增量判 Critical**——否则接手一个有历史类型错误的项目会 100% 阻塞，
  且问题与本次改动无关，Agent1 会被派去修不属于本任务的存量代码。
  ⚠️ **基线一律取改动前**：`mode=loop` 在 Step 1（Agent1 动手）之前跑一次即是；`mode=verify-only` 时代码已改完，
  须对**改动前基线 ref**（调用方给出；未给时取 `git merge-base HEAD <主干分支>`）跑同一命令——如在临时
  `git worktree` 检出该 ref、复用被测项目已有的 `node_modules`（⛔ 不联网装）。⛔ **不得以「本轮首次跑出的错误数」作基线**：
  那会把本次引入的类型错误整批吞成「存量」，方向是假绿。取不到改动前基线（无 git / 无基线 ref / 基线那次没跑起来）
  → 本项写「**基线无效，本项未核验**」（判定见下「基线对照的有效性判定」），⛔ 不得给出增量结论。
- 工具未安装时（`--no-install` 下会直接失败）标「⏭️ 跳过（工具缺失：<原因>）」并在报告写明，
  **不得**因此升级为全量 build、也不得改用会联网安装的裸 `npx`。


---

**⚠️ 基线对照的有效性判定（跨维度通用铁律，维度 4 / 7 / 8 / 14 一体适用）**

本 SKILL 多处用「改动前 vs 改动后」的基线对照（`--baseline-root`、`git show HEAD:<file>`、
`git stash` 取基线、lint 同文件集基线…）。**做比较之前，必须先判定「基线那一次真的跑起来了」。**

> **🛡️ 真实失效：** 用 `git stash` 取基线时，把验证依赖的**未跟踪配置文件**一起带走了，
> **基线那次实际没有执行**，却产出了一个看似正常的基线结果——差点把假的「错误变少了」
> 当成好消息接受。**这类失效的形态与本 SKILL 反复强调的「0 命中假绿」完全同源**：
> 没跑出来和跑出来啥事没有，在结果里长得一模一样。

**判定与处置（不可裁剪）：**

| 信号 | 处置 |
| :- | :- |
| 基线结果**空**（0 字节 / 只有空白 / 0 行输出） | ⛔ **拒绝比较** |
| 输出行数与预期**量级不符**（如平时几百行、这次 3 行） | ⛔ **拒绝比较** |
| 出现「路径不存在 / command not found / 未执行 / Traceback」类信号 | ⛔ **拒绝比较** |

拒绝比较时**按 `exit 2`（入参/环境错）返回**，⛔ **绝不给出一个差值**。
⚠️ 报告里必须写成「**基线无效，本项未核验**」，**不是**「通过」——
`exit 2` 的语义是「修好再跑」，把它当 0 处理就等于把这一档静默跳过了
（与维度 10 / 12 / 13 的「`exit 2` 是入参/环境错、不计维度失败」是同一条约定，
但**那里说的是不计失败，不是算通过**）。

`scripts/check_css_equivalence.py` 内建了其中**两条半**：空基线、**开头几行**出现编译/命令报错、
以及「整份产物一个 `{` 都没有」（→ `exit 2` 并打印原因）。
⚠️ **「行数量级不符」那条脚本做不了**（它不知道"平时几百行"是多少），仍由 Agent 按上表人工判；
⚠️ 报错信号**只查开头几行的行首**，⛔ 不要改成全文子串匹配——实测那样会把
`.error:hover{…}` 这种再普通不过的 CSS 选择器判成「无效基线」，
而 `exit 2` 的语义是「修好再来」、调用方无从修，整个维度就**静默消失**了；
其它基线对照场景由 Agent 按上表**先判后比**。


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
# ⚠️ **DEV_MOCK 同样豁免**(不只 THIRD_PARTY_MOCK):否则 planner 推荐的两种 dev mock 写法
#    (axios 拦截器 / MSW)会在 2A 被判 Critical(根因见 rationale.md 第 6 节)。
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

---

#### 维度 3: 真实接口对接检查（存在接口定义时必检）

**检查方法：**
1. 从详细设计文档/接口文档中提取所有接口定义
2. 在前端代码中找到对应的 API 调用
3. 逐项比对以下 **7 项**（其中 3.7 为**条件触发项**——仅当接口出参字段结构发生变更时才适用）

> ⚠️ **这 7 项是「维度 3 内部的比对项」，不是 SKILL 的维度总数**。为免混淆，本节一律称「项」不称「维度」。
> ⛔ **这里刻意不写维度总数**：本句的职责就是消除「7 项 vs 维度总数」的混淆，写死数字必腐化。维度总数**以 [`../SKILL.md`](../SKILL.md) 维度标题的编号最大值为准**——⚠️ **不是数标题条数**（「维度 0」是不计入的前置门，`2A`/`2B` 是同属维度 2 的拆分子项，数标题会多算），⛔ 别把「数标题」写成核对方法。

**检查清单：**

| 序号 | 比对项 | 检查内容 | 严重级别 |
|------|---------|---------|---------|
| 3.1 | **URL 路径** | baseURL + context-path + 路径是否与后端一致，路径参数占位符是否正确（如 `/user/${id}` vs `/user/{id}`）。**重点检查后端是否配置了 context-path**（如 Spring Boot 的 `server.servlet.context-path`），前端 baseURL 必须包含此前缀 | 🔴 Critical |
| 3.2 | **请求方法** | GET/POST/PUT/DELETE/PATCH 是否与后端定义一致 | 🔴 Critical |
| 3.3 | **请求参数** | Headers（Content-Type、Authorization）、Path Params、Query Params、Request Body 的字段名、类型、必填项是否一致 | 🔴 Critical |
| 3.4 | **返回结果字段** | 成功响应的数据结构（字段名、类型、嵌套层级）、分页结构（total/list/pageNum/pageSize）、枚举值映射 | 🔴 Critical |
| 3.5 | **返回状态码** | HTTP 状态码（200/201/400/401/403/404/500）是否正确处理，是否有遗漏 | 🟡 Important |
| 3.6 | **错误处理**（含第三方业务错误透传） | 业务错误码映射、错误信息展示方式（Toast/Message/Dialog）、网络异常/超时/服务不可用的处理；**★第三方业务错误透传**：调第三方接口时第三方返回的业务错误须原样透传前端，被吞掉/替换成通用文案 → 🔴 Critical（详见下方 3.6 详细说明） | 🟡 Important（第三方业务错误被吞/替换升 🔴 Critical） |
| 3.7 | **出参字段变更消费点穷举** | 接口出参字段结构变更（如 `value` 拆为双字段、字段增/改/删）时,必须列出该接口数据在前端的**全部消费点**并逐点核对字段已适配;**重点含绕过框架封装、按 `dataIndex`/数组下标回原始数据取值的旁路**（如 ECharts tooltip `formatter`、`params.dataIndex` 回原数组、`rawList[i]` 直取）——主渲染路径经框架封装改对了,旁路不会自动跟着改。漏改任一消费点 → 🔴 Critical（详见下方 3.7 详细说明） | 🔴 Critical（漏改任一消费点） |

**3.1 URL 路径检查详细说明：**

后端接口的完整 URL 结构：`http://{host}:{port}/{context-path}/{接口路径}`

**检查步骤：**

1. **检测后端 context-path 配置**：各框架的前缀配置位置见对应技术栈文件的「维度 3」节——`references/stack-java-spring.md`（Spring Boot `server.servlet.context-path`）/ `stack-nodejs.md`（Express·Koa·NestJS）/ `stack-go.md`（Gin·Echo·Fiber·Go-Zero，**注意嵌套 Group 前缀累加**）/ `stack-python.md`（FastAPI·Django·Flask，**注意嵌套 router 前缀叠加**）。其他框架：查找路由注册时的全局前缀配置

2. **验证前端 baseURL 配置**：
   - 检查前端 API 配置文件（如 `src/config/api.ts`、`src/utils/request.ts`、`.env` 文件）
   - 确认 `baseURL` 或 `API_BASE_URL` 是否包含后端的 context-path
   - 示例：
     ```typescript
     // ❌ 错误：后端配置了 context-path=/api，前端未包含
     const baseURL = 'http://localhost:8080'
     
     // ✅ 正确：前端 baseURL 包含后端 context-path
     const baseURL = 'http://localhost:8080/api'
     ```

3. **验证接口调用路径**：
   - 前端实际请求：`baseURL + 接口路径`
   - 后端实际监听：`context-path + Controller 路径 + 方法路径`
   - 两者必须完全一致

**3.6 错误处理检查详细说明（★第三方业务错误透传，Critical）：**

当被检代码**调用第三方系统接口**（本项目以外的外部系统：其他业务系统、支付、银行、海关、OAuth IDP 等），且第三方返回**业务错误**时，本系统必须把第三方的业务错误**透传给前端**，不得吞掉或替换成无信息量的通用文案。

**业务错误 vs 系统错误（区分口径）：**

| 分类 | 特征 | 处置 |
| :- | :- | :- |
| **第三方业务错误** | 第三方响应体是结构化业务失败：含业务码 + **面向最终用户、有指导意义的 message**（如 `{success:false, code:40001, message:"个人积分余额不足"}`） | **必须透传**：把第三方业务码/文案原样（或语义等价地）返回前端，让用户知道真实失败原因与下一步动作 |
| **第三方系统/基础设施错误** | 超时、连接失败、5xx、网关错误、响应体无法解析、无结构化业务体 | **通用兜底**：返回"服务暂时不可用，请稍后重试"等通用文案，避免向前端泄露内部细节/堆栈 |

**反模式（🔴 Critical）：** 代码拿到第三方业务错误（日志里已见 `code=40001 个人积分余额不足`），却在 catch / 异常映射层 / 全局异常处理器把它替换成自定义通用码+文案（如 `code=42902 "积分操作失败，请稍后重试"`）再抛给前端——用户看不到"余额不足"这一真实且可指导操作的原因，是不应有的信息丢失。

**检查方法（语义判定，脚本不覆盖）：**
1. 定位对第三方 client 的调用点（如 `*Client`、OpenFeign、httpx/axios 调外部 base URL）及其 catch / 异常映射 / 全局异常处理器（`GlobalExceptionHandler` 等）。
2. 核对第三方返回业务错误（`success:false` + 业务 code + 用户向 message）时，透传链是否完整：**第三方 message 是否原样/语义等价地到达前端**，而非被替换为固定常量文案。
3. 发现"第三方业务错误被吞/替换成通用文案"→ 🔴 Critical；系统/基础设施错误走通用兜底 → ✅ 合规。

**3.7 出参字段变更消费点穷举检查详细说明（语义判定，脚本难可靠覆盖）：**

当接口**出参字段结构发生变更**（字段增/改/删，或单字段拆成双字段，如原 `value` 拆为 `{planValue, actualValue}`）时，同一份接口原始数据在前端常被**多个消费点**读取——主渲染路径改对了，旁路（尤其绕过框架封装、按数组下标回原始数据取值的那类）**不会自动跟着改**，极易漏改。

**① 触发条件：** 接口出参字段增/改/删/拆（结构性变更），且前端存在对该接口返回数据的读取。字段结构未变、仅取值变化不触发本项。

**② 穷举方法：**
1. 以**变更后的字段名** + **该接口数据在前端的数据源变量名**（如 `chartData`、`rawList`、`resp.data.records`）全局 grep，定位所有读取点；
2. 把读取点分两类逐点核对：
   - **主渲染路径（经框架封装）**：如组件 props、v-for、图表 `series.data` 映射等，走封装后字段访问；
   - **旁路（直取 index / 原数组）**：如 ECharts tooltip `formatter` 里用 `params.dataIndex` 回原数组取 `rawList[idx].value`、手写 `list[i]` 直取、事件回调里按下标回原始数据等——**这类是漏改高发区**，重点排查；
3. 每个消费点都核对：是否已改用变更后的字段（不再读已删/已改的旧字段）。

**③ 判定：** 任一消费点仍读旧字段结构（主路径或旁路皆然）→ 🔴 Critical；全部消费点均已适配 → ✅ 合规。

**处置口径说明：** 本项为**语义判定，脚本难可靠覆盖**（消费点尤其旁路的识别依赖对数据流的理解，与 3.6「第三方业务错误透传」同为脚本不覆盖、由 Agent 语义核验的检查项）。

**输出格式：**
```
| 接口名称 | Method + URL | 3.1 URL | 3.2 方法 | 3.3 参数 | 3.4 返回 | 3.5 状态码 | 3.6 错误 | 结果 |
|---------|-------------|---------|---------|---------|---------|----------|---------|------|
| 用户列表 | GET /api/user/list | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ 通过 |
| 创建用户 | POST /api/user | ✅ | ✅ | ❌ userName→username | ✅ | ⚠️ 缺403 | ⚠️ 缺超时 | ❌ 不通过 |
```

> **3.7 出参字段变更消费点穷举**为条件触发项（仅当接口出参字段结构变更时适用）、且为语义判定，不在上表逐接口列内；触发时单列一段说明：列出变更接口 + 其前端全部消费点（含旁路） + 每点是否已适配的逐点核对结论。

**常见问题模式（重点关注）：**
- **context-path 缺失**：后端配置了 `context-path=/api`，前端 baseURL 为 `http://localhost:8080`，导致请求 404
- **context-path 重复**：前端 baseURL 为 `http://localhost:8080/api`，接口调用时又拼接了 `/api/user/list`，导致重复前缀 `/api/api/user/list`
- **环境不一致**：开发环境和生产环境的 context-path 不一致，前端未做环境区分配置
- 字段名大小写不一致（`userName` vs `username`、`pageNum` vs `page`）
- 分页结构不一致（后端返回 `{total, records}` 前端期望 `{total, list}`）
- 枚举值不一致（后端返回 `"ACTIVE"` 前端期望 `1`）
- 嵌套结构层级不一致（后端 `data.user.name` 前端 `data.name`）
- Content-Type 不匹配（后端期望 `application/json` 前端发送 `multipart/form-data`）

---
