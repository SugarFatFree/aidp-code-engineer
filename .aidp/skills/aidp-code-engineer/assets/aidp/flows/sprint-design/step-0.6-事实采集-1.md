> 🧩 **分片 1/共3**｜**本片覆盖范围**：Step 0.5.5 工程结构 + 运行时端点契约确认门 + Step 0.6 事实采集的 0.6.1~0.6.4.5（判断是否采集 / 扫描后端·前端·部署反代事实 / 扫描"路径消费者点"）。续见同目录 `step-0.6-事实采集-2.md`（0.6.4.7 代码现状清单 · 0.6.4.8 关联项目采集）、`step-0.6-事实采集-3.md`（0.6.5 事实清单模板 · 0.6.6 skill 硬约束）。

# sprint-design · Step 0.5.5 + Step 0.6 详情（工程结构端点契约确认门 + 后端/前端事实采集）

> 本文件是 `/sprint-design` 命令 **Step 0.5.5 + Step 0.6** 详情的**首片**（⛔ 本片不含该段全部子步——其余在 `step-0.6-事实采集-2.md` / `-3.md`，按进度依次 Read，勿读完本片即认为已覆盖全段），由命令主体（`{{AIDP_HOME}}/commands/sprint-design.md`）在**进入该段时用 Read 工具按需加载**——把详细回检/兜底/模板从"每次调用整体入上下文"改为"走到该段才载"，降低"lost in the middle"式漏步。命令主体只保留该段的**骨架表 + Read 指针**。
>
> ⚠️ **权威性**：进入本段后，**以本文件为准逐项执行**，不得凭命令主体骨架或记忆略过任一子步骤。
> ⚠️ **维护**：本文件与命令主体同属 template 自有、随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-design/`。理据/根因见同目录 `rationale.md`。

---

#### Step 0.5.5：★ 工程结构 + 运行时端点契约确认门（greenfield/首版必过；用户主权）

> **为什么需要**：Step 0.6 事实采集"从 `code/` 读真实事实"仅在**已有代码**时成立；**greenfield/首版**（`code/{side}/` 下无任何配置/源码）没有可读的事实，端口 / context-path / 访问前缀 / 根包名 / `{子项目}名` 等**运行时契约**过去便由 AI 在详细设计里**自行拍板**、从不问用户——这与「用户主权」相悖。本门在 Step 0.6 之前把这些**运行时契约一次性交用户确认**（给推荐默认但不静默采用），作为下游 `application.yml`/`vite.config`/事实清单/配置项清单的**权威基线**，杜绝各处 AI 各自猜测。

- **触发判定**：扫 `code/frontend/`、`code/backend/`（含 `{子项目}/`）下是否已有运行时配置（`application.yml`/`application*.properties` / `vite.config.*` / `.env*` / `package.json`）。
  - **已有配置（存量项目）** → **跳过本门**，走 Step 0.6 从代码提取（代码为唯一信源，不反向问用户改既定值）。
  - **无配置（greenfield/首版，或本版本新增某端）** → **必过本门**。
- **收集方式（`AskUserQuestion`，一次性给全部推荐默认，逐项可改）**——**交互式必问、不静默采用默认**；无人值守（`--unattended`）则消费 PRD `autopilot_decisions.deployment` 预声明、缺失取推荐默认 + WARN 留痕：

  | 契约项 | 推荐默认 | 说明 |
  |---|---|---|
  | 后端 `{子项目}名` | `<项目名>-backend` | 约定 18 `{子项目}` 层；决定 `code/backend/{子项目}/`（`<项目名>` 取 `project.name`/git 仓库名）|
  | 前端 `{子项目}名` | `<项目名>-frontend` | 决定 `code/frontend/{子项目}/` |
  | 后端端口 | `8080` | `server.port`（等价配置项）|
  | 前端 dev 端口 | `5173` | Vite/构建工具 dev server 端口 |
  | 后端访问前缀 / context-path | `/<服务名>`（一般 == 后端 `{子项目}名` 或模块名）| `server.servlet.context-path` 等价 |
  | 是否带 API 版本前缀 | 否（如需则 `/api/v1`）| 影响接口 base 拼接 |
  | 后端根包名 / 模块名（如涉及）| `com.<org>.<服务名>` | 后端源码根包 |
  | 部署访问 URL | `http://<host>:<后端端口><context-path>` | autopilot/aiauto-test 访问基址 |

- **落盘（权威基线，三处 + 供 skill 消费）**：
  1. **`docs/architecture/技术选型.md`** 追加「运行时端点契约」段（权威基线；Step 4.1 更新技术选型时保留/校对本段）——若本项目用 `架构约束.md` 承载约束，同步在其「运行时/部署约束」段登记；
  2. **`docs/deployment/{version}/配置文件/增量/配置项清单.md`**（运维视角，约定 25）登记端口 / context-path / 前缀 / URL 等配置项 + 权威取值；
  3. **seed `docs/design/detail/{version}/*事实清单.md`**（模板结构见分片 `step-0.6-事实采集-3.md` 的 Step 0.6.5）——greenfield 无代码可提取时，用本门确认值**预填**事实清单的服务/前端表（来源列**按实际来源分支填**：交互式经用户确认 → `运行时端点契约确认门（用户确认，尚无代码）`；无人值守取 PRD 预声明 → `PRD autopilot_decisions（未经用户确认）`；取推荐默认 → `推荐默认（未经用户确认）`。⛔ 不得无条件盖「用户确认」戳——下游 Step 0.6.6 的硬约束会把它当**已确认事实**消费，而那个值可能根本没人看过），Step 0.6 便不再"无源可读"；
  4. **反映到 PRD 头部 `autopilot_decisions.deployment`**（若本项目走 autopilot：把 context-path/端口/访问 URL 写入该段，供 `/sprint-autopilot`·`/sprint-aiauto-test` 直接复用；已有则校对一致）；
  5. **Step 1 调 skill 时作为上下文显式传入**——dev-logic-architect 据此生成 `application.yml`/`vite.config` 设计与接口 base，**消费确认值、不再自行拍板端口/前缀**（命令端只传上下文，不复述 skill 内部规则，约定 21）。
- **与约定 18「`{子项目}名` 确认门」合一**：本门确认的前后端 `{子项目}名` 即约定 18 的 `{子项目}` 目录名；`/sprint-dev` 首次写码时据此建 `code/{side}/{子项目}/`（本门已确认则 sprint-dev 不再重复问；本门被跳过/未覆盖某端时 sprint-dev 兜底现场确认）。

#### Step 0.6：★ 后端/前端事实采集（代码为唯一信源）

**关键原则**：所有进入 `接口设计.md` / `详细设计.md` 的**端口 / context-path / API 前缀 / proxy 路径 / 部署上下文**等"真实事实"，必须从 `code/` 下的**实际配置文件和源码**里读取，**禁止 Claude 凭印象推断**（★ greenfield 无代码时，事实来源 = Step 0.5.5 已确认并 seed 进事实清单的「运行时端点契约」，而非 AI 现编）。

> 典型案例：Claude 把后端 context-path 写成 `/portal/`，但 `application.yml` 里实际是 `/server/`，导致前端 proxy 与文档对不上。

**Step 0.6.1：判断是否需要采集**
- 如 `code/` 下**有任何后端或前端项目**（任何框架）→ 必须执行 Step 0.6.2 ~ 0.6.4
- 如 `code/` 完全为空（真首版，连脚手架都没起）→ 跳过本步；本次设计落地后由 `/sprint-dev` 阶段产出代码，**届时代码必须以本次接口设计为准**

**Step 0.6.2：扫描后端事实**（按实际框架按需扫，未命中的不强求）

| 框架 | 关键文件 | 必采集项 |
|------|---------|---------|
| Spring Boot | `code/**/application.yml` / `application*.properties` / `application-*.yml` | `server.port` / `server.servlet.context-path` / `spring.application.name` / `management.endpoints.web.base-path` / 各 profile 的差异 |
| Spring Boot | `code/**/src/main/java/**/*Controller.java` | 类级 `@RequestMapping` / `@RestController` 前缀；方法级路径；HTTP 方法 |
| Node Express | `code/**/server.js` / `app.js` / `routes/**` | `app.use('/prefix', ...)`、`router.METHOD('/path', ...)` |
| NestJS | `code/**/*.controller.ts` | `@Controller('prefix')` + `@Get/@Post/...` |
| Python Flask | `code/**/*.py` | `Blueprint(url_prefix=...)`、`@app.route` / `@bp.route` |
| Python FastAPI | `code/**/*.py` | `APIRouter(prefix=...)` + `@router.METHOD(...)` |
| Python Django | `code/**/urls.py` | `urlpatterns` + 嵌套 `include` |
| Go Gin | `code/**/*.go` | `r.Group("/prefix")` + `r.METHOD("/path", ...)` |

**Step 0.6.3：扫描前端事实**

| 框架 | 关键文件 | 必采集项 |
|------|---------|---------|
| Vite | `code/**/vite.config.ts` / `vite.config.js` | `server.proxy` 的 `/xxx → target`；`server.port`；`base` 公共路径 |
| Vue CLI | `code/**/vue.config.js` | `devServer.proxy` 配置；`publicPath` |
| Next.js | `code/**/next.config.{js,mjs,ts}` | `rewrites/redirects`、`basePath`、`assetPrefix` |
| 通用 | `code/**/.env*` / `env/.env*` | `VITE_API_BASE_URL` / `NEXT_PUBLIC_API_URL` / `REACT_APP_API_URL` 等运行时 API 地址 |

**Step 0.6.4：扫描部署/反代事实**（如有）

| 来源 | 关键文件 | 必采集项 |
|------|---------|---------|
| Nginx | `docs/deployment/{version}/**/*.conf` / `code/**/nginx*.conf` | `location /xxx { proxy_pass ... }` 全部映射；`server_name` |
| Docker Compose | `docker-compose*.yml` / `docker-compose*.yaml` | 服务名、端口映射、网络别名 |
| K8s | `**/*deployment.yml` / `**/*deployment.yaml` / `**/*service.yml` / `**/*service.yaml` | service name、port、ingress 规则 |

**Step 0.6.4.5：扫描"路径消费者点"**（防级联事故）

仅记录 base 是什么还不够：base 变更会**级联打穿**多处使用它的代码。本步骤扫描代码里**所有读取/判定 base 的位置**，作为后续变更时的影响清单。

| 类 | 扫描位置（glob） | 抓取关键词 / 模式 |
|---|---|---|
| 前端 axios 配置 | `code/**/utils/request*.{ts,js}` ；`code/**/composables/http*.{ts,js}` ；`code/**/api/index*.{ts,js}` ；`code/**/lib/api*.{ts,js}` | `axios.create({ baseURL` / `import.meta.env.VITE_API_BASE_URL` / `process.env.NEXT_PUBLIC_API_URL` |
| **前端 URL 守卫**（★ 反逻辑高发区） | 上述同样文件 | `startsWith('/')` / `startsWith(baseURL` / `startsWith('http')` / `isAbsolute` / 正则 `^https?:` |
| 前端 SSE / WebSocket | `code/**/sse*.{ts,js}` ；`code/**/ws*.{ts,js}` ；含 `EventSource` / `new WebSocket(` 的任何文件 | URL 拼接逻辑（特别注意：SSE/WS 往往独立维护一份 URL 拼装，与 axios 守卫不同步是常见漏修点） |
| 前端 fetch / 原生 HTTP | `code/**/src/**/*.{ts,tsx,js,jsx,vue}`（仅 src，排除 node_modules/dist） | 含 `fetch(` 或 `new Request(` 的字符串模板 URL 拼接 — 它们**不走 axios baseURL** |
| 前端 router base | `code/**/router/index*.{ts,js}` ；`code/**/vue.config.*` ；`code/**/next.config.*` | `createWebHistory(` / `createRouter({ base` / `publicPath` |
| 前端 env | `code/**/.env*` | `VITE_API_BASE_URL` / `NEXT_PUBLIC_*` / `REACT_APP_*` |
| 后端跨域 / 跳转 | Spring Boot：`code/**/{CorsConfig,WebMvcConfig,SecurityConfig}*.java` ；Express：含 `cors(` 中间件注册的文件 ；FastAPI：含 `CORSMiddleware` 的文件 | `allowedOrigins` / `setAllowedHeaders` / 登录重定向 URL |
| Nginx | `docs/deployment/{version}/**/*.conf` ；`code/**/nginx*.conf` | `proxy_pass` / `rewrite` / `location` |
| Docker / K8s | `docker-compose*.{yml,yaml}` ；`**/*deployment.{yml,yaml}` ；`**/*service.{yml,yaml}` | service URL 内部引用 |

把每个命中点记录"文件:行号 — 用法摘要"，写入事实清单的「路径消费者点」表（模板见分片 `step-0.6-事实采集-3.md` 的 Step 0.6.5）。

