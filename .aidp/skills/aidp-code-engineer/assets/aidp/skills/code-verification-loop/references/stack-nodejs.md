# Node.js 后端审计细则（Express / Koa / NestJS）

> 探测命中 `package.json` 依赖含 `express` / `koa` / `@nestjs/core` 时加载本文件。跨技术栈的通用判据见 `../SKILL.md`。

---

## 一、维度 3：context-path（路由全局前缀）检测

| 框架 | 前缀配置位置 |
| :- | :- |
| Express | `app.use('/prefix', router)`；或 `app.set('basePath', '/prefix')` |
| Koa | `new Router({ prefix: '/prefix' })` |
| NestJS | `app.setGlobalPrefix('api')`（`main.ts`） |

检出前缀后，须核对前端 `baseURL` 是否包含它——否则按接口文档直调 404。前端侧判据见 `stack-vue.md` / `stack-react.md`。

---

## 二、维度 4：依赖越界基线（`package.json`）

```bash
python3 <SKILL_DIR>/scripts/scan_code_conventions.py <代码目录> --checks dep-baseline [--base <ref>]
```

取 `git diff <base>` 新增 import **+ untracked 新文件的全部 import**（新建文件是新增依赖最常见来源，`git diff` 看不到，脚本已用 `git ls-files --others` 补扫），与 `package.json` 的 `dependencies`/`devDependencies` 比对顶层包。

- 脚本**已排除** Node 内置模块与 `@/`、`~/` 路径别名，**本栈是脚本覆盖度最好的一栈**（不像 Java/Go 需人工核对）。
- 命中即越界 → 补进清单（经评估）或移除 → 🟡 Important；**引入未评估的第三方/重型依赖升 🔴 Critical**。
- ⚠️ **`devDependencies` 陷阱**：运行时代码 import 了只声明在 `devDependencies` 的包 → 生产环境 `npm ci --omit=dev` 后启动即 `MODULE_NOT_FOUND`。这类「编译/本地跑得通、生产启动炸」的问题与 Java 的 DI 不可解析同源，命中判 🔴 Critical。

---

## 三、维度 2B：后端 mock 运行时开关（Node 写法）

```javascript
// ❌ 错误：构建期/启动期常量判断，打包或部署后不可切换
if (process.env.NODE_ENV === 'development') { return mockData; }

// ✅ 正确：运行时读取专用开关（可由部署环境变量控制，与 NODE_ENV 解耦）
const mockEnabled = process.env.THIRD_PARTY_MOCK_ENABLED === 'true';
if (mockEnabled) { return mockData; }
return realClient.refund(request);
```

NestJS 项目用 `ConfigService.get('thirdParty.mock.enabled')` 读取；**严禁**用 `@Module` 条件装配在构建期把 mock provider 裁掉（等价于 Spring 的 `@Profile("dev")` 反模式）。

真实对接后残留检查：`.env.production` 的第三方 base URL 已切真实地址后，须扫 mock 开关、fixture 文件（`__mocks__/*.json`）、拦截分支、`THIRD_PARTY_MOCK` 标注块是否残留。

---

## 四、维度 4：单文件行数阈值

TS/JS 普通模块 ≤ 400 行（不含 import + 注释），超阈值告警、2 倍升 Critical；单方法/函数 ≤ 50 行硬阈值。

```bash
python3 <SKILL_DIR>/scripts/check_file_complexity.py <代码目录>
```

---

## 五、本栈不适用的检查项

维度 6「DI 依赖可解析性」为 Java/Spring 专属、维度 7「CSS 预处理器一致性」为 Vue 专属，**Node.js 服务端此二维度均整维度跳过**（若同仓含 Vue 前端，维度 7 对那部分 `.vue` 仍生效）。

> ⚠️ **维度 8「请求通道 URL 拼装」不在跳过之列**：它扫的是 `.ts`/`.js`/`.mjs`/`.cjs` 等任意前端源码（完整清单见 `dimension-6-9-stack-gated.md` 维度 8「扫描范围」），判据（base 拼装判据是否只有一处实现）与运行在浏览器还是 Node 无关。Node 服务端调下游服务时同样会出现「多处各自拼 base」——**该维度照常执行**，见 `dimension-6-9-stack-gated.md` 维度 8。

> 📌 **注**：NestJS 有自己的 DI 容器，「provider 未在 `@Module.providers` 注册却被 `constructor` 注入」会在启动期报 `Nest can't resolve dependencies of the XxxService`——**与维度 6 拦的是同一类错误**。但本 SKILL 当前只落地了 Java/Spring 的静态检查脚本（`check_di_resolvability.py` 仅扫 `.java`），NestJS 侧**暂无脚本覆盖**，建议验收 Agent 人工扫一眼 `@Module` 的 `providers`/`imports` 与各 `constructor` 注入项是否对得上。**这是非阻断提醒、不是该维度的通过条件**——维度 6 对 Node 项目在门控上已整维度跳过，不计入通过/不通过。此处显式记录该缺口，只为避免被误读为「Node 项目不存在这类问题」。

金额字段类型守恒：JS `number` 超过 2^53 会丢精度，**金额建议用 `string` 或 `BigInt` 传输**，与设计 A.3 的 `BIGINT` 对齐；具体阈值判据见 `dimension-4-5-quality-debt.md` 维度 4。
