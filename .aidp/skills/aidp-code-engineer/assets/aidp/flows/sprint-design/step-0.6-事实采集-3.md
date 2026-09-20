# sprint-design · Step 0.6 事实采集 — 分片 3/共3（事实清单整理 + skill 硬约束）

> 本片承接 `step-0.6-事实采集-2.md`。**本片覆盖范围**：Step 0.6.5（整理事实清单，含 `docs/design/detail/{version}/事实清单.md` 完整模板）+ Step 0.6.6（传递给 skill 时的硬约束——代码事实优先）。
>
> ⚠️ **权威性**：进入本段后以本文件为准逐项执行，不得凭命令主体骨架或记忆略过任一子步骤。
> ⚠️ **维护**：本文件与命令主体同属 template 自有、随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-design/step-0.6-事实采集-3.md`。理据/根因见同目录 `rationale.md`。

---

**Step 0.6.5：整理事实清单**

把采集结果归纳为一份「事实清单」（**保存到 `docs/design/detail/{version}/事实清单.md`** 作为本次设计的引用基线，并在 Step 1 调用 skill 时显式作为提示传入）：

```markdown
# 后端/前端/部署 事实清单（{version}）

> 本文件由 /sprint-design Step 0.6 从 code/ + docs/deployment/{version}/ 自动提取，
> 接口设计.md / 详细设计.md 必须以本清单为准；如清单与设计冲突，**改设计不改代码**，
> 除非本次 Sprint 显式要求改 context-path / 改端口（必须在头部「⚠️ 本次变更」中声明，
> 否则 Step 1.6 路径回检会暂停并要求人工裁决）。

## 后端服务

| 服务 | 框架 | 端口 | context-path | API 前缀 | 完整 base | 来源 |
|------|------|------|--------------|---------|----------|------|
| <服务名> | <框架> | <端口> | <从 application.yml 读> | <从 @RequestMapping 读> | <两者拼接> | `code/<服务子目录>/src/main/resources/application.yml` + `<Controller.java>` |

## 前端项目

| 项目 | 框架 | dev 端口 | dev proxy | 生产 base | 运行时 API 地址 | 来源 |
|------|------|---------|-----------|----------|----------------|------|
| <项目名> | <框架> | <端口> | <proxy 映射> | <publicPath/base> | <从 .env / vite.config 读> | `code/<前端子目录>/vite.config.ts` + `.env.development` |

## 反代/部署

| 环境 | 入口 | 映射 | 来源 |
|------|------|------|------|
| <env> | <hostname/IP> | <`/xxx/ → service:port`> | `docs/deployment/{version}/配置文件/全量/<nginx.conf>` |

## 对外开放接口 base（★ 当 Step 0.4.5 判定 HAS_OPEN_API=true 时必出此节，false 时省略）

> 对外接口必须与**内部接口路径明确区分**（dev-logic-architect skill 强制规范）。本节列出本项目对外接口的 base 前缀事实。

| 服务 | 对外接口 base 前缀 | 鉴权方式 | 默认推荐 | 来源 |
|------|------------------|---------|---------|------|
| <服务名> | <从代码/部署提取，如 `/api/open/v1/`> | 无认证 / API Key+HMAC 签名 / OAuth 2.0 | `/api/open/v1/` + 无认证 | <Controller / nginx / PRD 指定> |

> 命令端在调用 skill 前必须确认本表已填实际值；若代码尚未实现对外接口（首版），按 PRD 推导一个合理 base 前缀写入并加注「（设计期默认值，由 /sprint-dev 落地）」。

## 代码现状清单（★ 由 Step 0.6.4.7 全扫 code/ 自动提取；Step 0.3 四象限对比的"代码已实现"列源头）

> 本节是**代码即事实**的具象化。象限 ③「代码超前」的判定依据全靠这张清单。如 PRD 没提的接口/表/页面在本清单出现，说明历史 sprint-dev 累进未走完整文档增量流——/sprint-design 本轮必须把这些"超前实现"反向追写到设计文档（标注 commit hash 来源）。

### 后端 API 端点

| Method | Path | 简述 | 文件:行号 | 是否在 PRD | 处理决策 |
|--------|------|------|----------|----------|---------|
| GET | <从代码扫> | <Controller 类注释> | `code/backend/{后端项目}/src/.../XxxController.java:42` | ✓/✗ | 保持/新增/代码超前/不存在 |

### 后端数据库表

| 表名 | 主要字段 | 来源 SQL | 是否在 PRD | 处理决策 |
|------|---------|---------|----------|---------|
| <表名> | <字段摘要> | `docs/deployment/<version>/sql/增量/<file>.sql:N` 或 Entity 类路径 | ✓/✗ | 保持/新增/代码超前/不存在 |

### 前端路由

| Path | Name | 对应 View | 是否在 PRD | 处理决策 |
|------|------|-----------|----------|---------|
| <路由路径> | <name> | `code/frontend/{前端项目}/src/views/<file>.vue` | ✓/✗ | 保持/新增/代码超前/不存在 |

### 前端页面

| 页面标题 | 文件 | 是否在 PRD | 处理决策 |
|---------|------|----------|---------|
| <标题> | `code/frontend/{前端项目}/src/views/<file>.vue` | ✓/✗ | 保持/新增/代码超前/不存在 |

### 配置文件（仅列文件，不展开 key — 权威清单见 `docs/deployment/{version}/配置文件/增量/配置项清单.md`，由 /sprint-dev Step X.7 维护）

| 文件路径 | 用途 |
|---------|------|
| `code/backend/{后端项目}/src/main/resources/application.yml` | 后端 Spring 主配置 |
| `env/.env` | 全局环境变量 |
| `code/frontend/{前端项目}/.env.development` | 前端 dev 环境变量 |
| `docs/deployment/{version}/配置文件/全量/nginx.conf` | 反代配置 |

## 路径消费者点（★ 修改 base/context-path 时必须同步审视）

> 由 Step 0.6.4.5 扫描得出。这里列出代码里**所有读取/判定 base 的位置**——base 变更必须同步修改这些点，否则会出现"前端发请求被守卫误判为相对路径 → axios 再前缀一次 → 双前缀 404"等级联事故。

> 下表的"文件:行号"、"用法摘要"由 Step 0.6.4.5 实际扫描填入；未命中的类整行写"无"。

| 类 | 文件:行号 | 当前用法摘要 | 风险点 |
|----|----------|------------|-------|
| 前端 axios baseURL | `<实扫填>` | `axios.create({ baseURL: <env 变量> })` | 改 base → 必同步 `.env*` |
| 前端 URL 守卫（**反逻辑高发**） | `<实扫填>` | `<实扫填，如 url.startsWith(...) 且含 !startsWith(baseURL) 子条件 → 重点标⚠️>` | 当 url 恰以 baseURL 开头时含 `!` 子条件的守卫会反逻辑失效 → axios 再前缀一次 |
| 前端 SSE/WebSocket | `<实扫填>` | 独立 URL 拼接（不走 axios） | 与 axios 守卫不同步是常见漏修点 |
| 前端 dev proxy | `<实扫填，如 vite.config.ts:N>` | `/<api 路径> → http://<host>:<port>/<base>` | 改 base → 必同步 proxy.target |
| 前端 env | `<实扫填，如 .env.development>` | `VITE_API_BASE_URL=<base>` | 改 base → 必同步全部 `.env*` profile（注意 dev/prod 故意不同时不算反模式）|
| 前端 router base | `<实扫填>` | `createWebHistory('<base>/')` | 改 base → 静态资源路径连带变 |
| Nginx | `<实扫填，如 docs/deployment/{version}/配置文件/全量/<nginx.conf>:N>` | `location <base>/ { proxy_pass ...; }` | 改 base → nginx 必同步，否则反代 404 |
| 后端 CORS / 跳转 | `<实扫填，如 CorsConfig.java:N>` | `allowedOrigins(...)` | 改前端域名/端口 → CORS 跟随 |

> **★ 反模式提示**（Claude 写守卫时必须避免）：
> - 不要写 `url.startsWith('<base>/') && !url.startsWith(baseURL)` 这种**含 `!` 子条件**的"以 base 为前缀视为绝对路径"判定 —— 当 url 恰以 baseURL 开头时反逻辑会失败（典型「base 变更后双前缀 404」事故）
> - 推荐写法：**绝对外链判定只看协议**（`/^https?:\/\//.test(url)` 或 `url.startsWith('//')`），项目内一律视为相对让 axios 处理 baseURL；如确实要"跳过 baseURL"的内部绝对路径，**显式约定一个不与 baseURL 重叠的前缀**（如 `/__abs/`）或在调用点用 axios `baseURL: ''` 临时覆盖

## ⚠️ 本次变更（如有）

| 项 | 旧值 | 新值 | 理由 | 已联动消费者点（必填） |
|----|------|------|------|-------------------|

（无变更写"无"；有变更必须说明——这一行会被 Step 1.6 路径回检识别为"允许的路径变更"。**「已联动消费者点」列必须列出本次变更已同步修改的所有上表条目，逐一勾选 / 列文件:行号**；遗漏的消费者点 = 潜在级联事故）
```

**Step 0.6.6：传递给 skill 时的硬约束**

在 Step 1 调用 dev-logic-architect 的 prompt 里，**明文写入**：

```
【硬约束 — 代码事实优先】
本次接口设计/详细设计中出现的所有端口、context-path、API 前缀、proxy 路径、
部署上下文 必须与 docs/design/detail/{version}/*事实清单.md 一致。

禁止动作：
- 凭印象编造 服务路径前缀 / context-path（如代码用 `/server/` 却写成 `/portal/`）
- 把已经在代码里定下的 context-path 改写成"更好看"的版本
- 在没有读 application.yml / vite.config 的情况下写任何具体的 base 路径

允许动作：
- 在事实清单的 base 上**新增 endpoint 后缀**（如 `/api/v1/user/list`）—— 这是设计的正常职责
- 如设计确实需要改 context-path / 端口等"base 级"事实 → 必须在 `*事实清单.md` 的
  「⚠️ 本次变更」表显式声明，并在 接口设计.md 用 🔄 标记出来
```

