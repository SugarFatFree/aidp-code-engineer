# 技术栈审计细则 · 按需加载索引

> **为什么拆**：本 SKILL 的**跨技术栈通用判据**（维度划分、severity 分级、三方冲突裁决、字段对账口径等）写在 `SKILL.md`；**语言/框架专有的审计细则**拆在本目录 `stack-*.md`。验收 Agent **先探测被测项目实际技术栈，只加载命中的那 1~2 份**，不要全量读——避免一次性把 Java、Vue、Go、Python 的规则全灌进上下文。

## 第一步：探测技术栈

在被测代码目录执行（命中即认定，可多命中——前后端分离项目通常同时命中 1 个后端栈 + 1 个前端栈）：

| 探测信号（任一命中） | 判定技术栈 | 加载文件 |
| :- | :- | :- |
| 存在 `*.java` + `pom.xml` / `build.gradle` | Java / Spring | `stack-java-spring.md` |
| 存在 `*.vue`，或 `package.json` 依赖含 `vue` | 前端 Vue | `stack-vue.md` |
| 存在 `*.jsx` / `*.tsx`，或 `package.json` 依赖含 `react` | 前端 React | `stack-react.md` |
| `package.json` 依赖含 `express` / `koa` / `@nestjs/core` | Node.js 后端 | `stack-nodejs.md` |
| 存在 `go.mod` | Go | `stack-go.md` |
| 存在 `requirements.txt` / `pyproject.toml` + `*.py` | Python | `stack-python.md` |

**都未命中** → 只按 `SKILL.md` 的跨栈通用判据验收，不加载任何 `stack-*.md`；技术栈门控型维度（维度 6 DI 依赖可解析性 / 维度 7 CSS 预处理器一致性 / 维度 8 请求通道 URL 拼装）整维度跳过。

> ⚠️ **三个门控维度的门控条件互不相同，别混为一谈**：维度 6 认 `.java`、维度 7 认 `.vue`、**维度 8 认任意前端源码**（`.ts`/`.js`/`.vue`/`.tsx`/`.jsx` 等，**扩展名完整清单以 `dimension-6-9-stack-gated.md` 维度 8「扫描范围」为准**，别照记忆写半截判「不适用」）。所以一个 React 项目会跳过维度 6、7 而**照常执行维度 8**；**Node 服务端同样只跳过 6、7 而执行 8**（源码本身就是 `.ts/.js`，调下游服务一样会「多处各自拼 base」）；只有 Java·Go·Python 这类**无前端源码**的后端才三个都跳过。

```bash
# 一次探测（在被测代码目录跑）
ls pom.xml build.gradle go.mod requirements.txt pyproject.toml package.json 2>/dev/null
find . -name "*.java" -not -path "*/target/*" | head -1
find . -name "*.vue" -o -name "*.tsx" | grep -v node_modules | head -3
grep -E '"(vue|react|express|koa|@nestjs/core)"' package.json 2>/dev/null
```

## 第二步：各文件覆盖什么

| 文件 | 覆盖的维度/检查项 |
| :- | :- |
| `stack-java-spring.md` | **维度 6 DI 依赖可解析性全部细则**（三个技术栈门控维度之一，本维度为 Java/Spring 专属）；维度 4 的金额字段类型守恒 / DB 约束前置校验注解 / 配置中心热刷新 `@RefreshScope` / 审计字段填充 / 依赖基线（Maven·Gradle）；维度 3 context-path（Spring Boot）；维度 2B 后端 mock 的 `@Profile` 构建期隔离反模式与后端残留检查 |
| `stack-vue.md` | **维度 7 CSS 预处理器一致性的 Vue 侧细则**（本 SKILL 的 Vue 专属门控维度，配硬门脚本 `check_vue_style_preprocessor.py`；判定表 / 孤例 / 误报控制在此，**脚本接口事实与实测数字见 `dimension-6-9-stack-gated.md` 维度 7 单一信源**）；**§五 维度 8 请求通道 URL 拼装的 Vue 侧落地**（配硬门脚本 `check_request_channel_url.py`，判据本体跨栈通用、见 `SKILL.md`）；维度 2B 前端 mock 的 Vite 构建期守卫反模式与前端残留检查；维度 4 叶子组件替换白名单（Element Plus 等价件）、字段/列采集的 Vue SFC 细节、单文件行数阈值；维度 3 前端 baseURL 与 context-path 拼接 |
| `stack-react.md` | 同 `stack-vue.md` 的对应项，按 React / Antd / webpack·Vite + `process.env` 视角给判据；**§四 维度 8 请求通道 URL 拼装的 React 侧落地**（与 Vue 共用同一脚本与判据——本维度不依赖 SFC 机制，React 项目不跳过） |
| `stack-nodejs.md` | 维度 3 context-path（Express / Koa / NestJS 路由前缀）；维度 4 依赖基线（`package.json`）；维度 2B 后端 mock 运行时开关写法；**§五 记录维度 6 在 NestJS 侧的同类问题与脚本缺口（人工核对 `@Module.providers`），并点明维度 8「不在跳过之列」**（Node 服务端源码本身就是 `.ts/.js`，同一脚本同一判据照常执行） |
| `stack-go.md` | 维度 3 context-path（Gin `router.Group`）；维度 4 依赖基线（`go.mod`，脚本不覆盖需人工核对）、金额字段类型守恒（`int64`） |
| `stack-python.md` | 维度 3 context-path（FastAPI `APIRouter(prefix=)` / Django `urls.py`）；维度 4 依赖基线（`requirements.txt` / `pyproject.toml`）、金额字段类型守恒；**§三 记录维度 6 在 FastAPI `Depends()` / Django `INSTALLED_APPS` 侧的同类问题与脚本缺口（人工核对）** |

## 约束

- 各 `stack-*.md` **只写该技术栈专有的判据、反模式与命令**，不重复 `SKILL.md` 的通用口径（severity 定义、三方冲突裁决、闭环规则）。
- 遇到某栈**无对应规则**的检查项，该文件明确写「本栈不适用」而非留空，避免 Agent 误以为漏写。
- 本目录文件**不得跨 SKILL 引用**（每个 SKILL 自包含，允许各自有重复内容）。
