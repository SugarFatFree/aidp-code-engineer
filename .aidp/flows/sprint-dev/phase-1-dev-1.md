> **【分片 1/2 · phase-1-dev 二次切分】** 本片覆盖 **Phase 1.0pre（activeContext Sprint 编号置位）/ 1.1（确定开发范围）/ 1.1.5（`code/{side}/{子项目}/` 目录门，约定 18）/ 1.2（后端开发，含 Step 1 开发期 SQL 自动应用，约定 6）**。后片 `phase-1-dev-2.md` 覆盖 Phase 1.3（前端开发）/ 1.4（并行开发）。两片顺序拼合 = 原 `phase-1-dev` 全文，进入 Phase 1 须按序 Read 两片、不得只读单片。

# sprint-dev · Phase 1 开发执行详情（1.0–1.4）

> 本文件是 `/sprint-dev` 命令 **Phase 1 开发执行**（分支 A/B 共用）详情的**第 1/2 片**（⛔ 本片不含 Phase 1 开发执行 全部子步——后续子步在 `-2`…`-2` 分片，按进度依次 Read，勿读完本片即认为已覆盖全段），由命令主体（`{{AIDP_HOME}}/commands/sprint-dev.md`）在**进入 Phase 1 开发时用 Read 工具按需加载**——把这近 180 行从"每次调用整体入上下文"改为"走到开发段才载"，降低"lost in the middle"式漏步。命令主体只保留 Phase 1 的**骨架表 + 硬门一句提醒 + 指向本文件的指针**。
>
> ⚠️ **权威性**：进入 Phase 1 开发后，**以本文件为准逐项执行**，不得凭命令主体骨架或记忆略过任一子步骤（尤其 Phase 1.2 Step 1「开发期 SQL 自动应用」约定 6 + Phase 1.1.5「code/{side}/{子项目}/ 目录」约定 18）。
> ⚠️ **维护**：本文件与命令主体同属 template 自有、随脚手架下发；本 Phase 1 段已二次切分为 `phase-1-dev-1/-2.md` 两片，改动后同步各自 bundle 副本 `assets/aidp/flows/sprint-dev/`。理据/根因见同目录 `rationale.md`。

---

## Phase 1 开发执行（两种分支共用 — 下设 Phase 1.0pre~1.4）

> 本段是「Phase 1：开发」的展开（分支 A/B 共用）。`### 步骤 N` 是开发执行的子步骤，与回写段（`postdev-writeback-*.md`）的 `Step X.0~X.7` 体系视觉分级一致。

### Phase 1.0pre：activeContext 当前 Sprint 编号置位/校验（★ caller-agnostic + 幂等）

> ⛔ 现实：**batch / autopilot 路径常绕过 `/sprint-start`**。
> 而 activeContext 的「当前 Sprint 编号」**全仓只有 `/sprint-start` Step 2 一处写**
> （`/sprint-dev` 的回写段只追加 Round / 已完成 / 工作焦点，不置编号）——绕过时 activeContext 会停在上一个 Sprint。
> 后果不止"状态不准"：分支 A 用它取 `SPRINT_NNN` 来定**开发范围**与**死代码扫描范围**，
> 陈旧编号 = 照着上一个 Sprint 开发。

- **有入参 `{NNN}`**（`/sprint-dev NNN` / batch / full / autopilot 委派）：与 activeContext 现值比对
  —— 一致则跳过；不一致或缺失则**就地置为入参值**并记一行来源（幂等，重复执行结果相同）。
- **无入参**（裸 `/sprint-dev` 或自然语言触发）：activeContext 现值即权威；若该值也缺失，
  取研发执行计划中**最早一个未关闭 Sprint**（口径同 `plan_sprints.py`）置入。
- ⛔ **不得静默沿用一个与本次开发范围不符的编号**——校验不通过即置位，置不出来才停。

### Phase 1.1：确定开发范围

根据 $ARGUMENTS 判断：
- 含 "frontend" → 仅执行前端开发
- 含 "backend" → 仅执行后端开发
- 其他（空/"all"）→ 先后端，后前端

### Phase 1.1.5：★ 确认/创建 `code/{side}/{子项目}/` 目录（约定 18 铁律，首次写码前必过）

> 约定 18 铁律：`code/frontend/`、`code/backend/` 是**父目录**，其下**必须再有一层 `{子项目}` 目录**，源码根标志（`src/`、`pom.xml`、`build.gradle*`、`package.json`、`go.mod` 等）**只能落在 `code/{side}/{子项目}/` 下**——**即便单项目也必须有这一层，严禁把 `src/` 直接写进 `code/backend`/`code/frontend` 根**。本门在**首次为某端写代码前**确保 `{子项目}` 目录已就位。

对本 Sprint 将要开发的**每个端**（backend / frontend，按 Phase 1.1 范围）执行：

1. **探测既有子项目**：`ls -d code/{side}/*/ 2>/dev/null`（排除 `.gitkeep`）。
   - **已存在恰好一个 `{子项目}/`** → 复用它，写码全部落其下，跳过下面 2~3。
   - **已存在多个** → 按详细设计/事实清单里本 Sprint 归属的子项目名选定（多项目场景）。
   - **不存在任何 `{子项目}/`（只有父目录 + `.gitkeep`，greenfield 首次写码）** → 进入 2。
2. **确定 `{子项目}名`**（约定 18「用户确认门」）：
   - **优先读基线**：`docs/architecture/技术选型.md`「运行时端点契约」段 / `docs/design/detail/{version}/*事实清单.md`（`/sprint-design` Step 0.5.5 已确认的前后端 `{子项目}名`）→ 有则**直接采用、不再问**。
   - **基线缺失（未经 Step 0.5.5，如直接 `/sprint-dev` 累进）**：**交互式**用 `AskUserQuestion` 确认——推荐默认 `<项目名>-{side}`（`<项目名>` 取 `memory/aidp-config.yaml` 的 `project.name` / git 仓库名，如 `demo-backend` / `demo-frontend`），用户可改；**无人值守（`--unattended`）**取 PRD `autopilot_decisions.deployment` 里的子项目名，缺失则用推荐默认 + WARN 留痕（不挂起）。**严禁静默把 `src/` 直放父目录跳过本门**。
3. **创建目录 + 回写基线**：`mkdir -p code/{side}/{子项目}/`；若 `code/{side}/.gitkeep` 存在则 `git rm` 之（父目录已非空）。确认的 `{子项目}名` 若来自本门（基线未记录）→ 回写 `docs/architecture/技术选型.md`「运行时端点契约」段 + `*事实清单.md`，供后续 Sprint / aiauto-test / 部署复用。
4. **README 落位（约定 19）**：本端 README 落 `code/{side}/{子项目}/README.md`（**不是** `code/{side}/README.md`）——由 Phase 1.2/1.3 的 Backend/Frontend Agent 首次写码时生成。

> ★ 之后 Phase 1.2/1.3 的**所有**写码、路径、编译、grep 一律在 `code/{side}/{子项目}/` 下进行；backend/frontend Agent 白名单本就是 `code/{side}/{子项目}/`（见 `agents/backend.md`·`frontend.md`）。

### Phase 1.2：后端开发（如在范围内）

读取 `{{AIDP_HOME}}/agents/backend.md` 获取角色定义，执行"开发顺序"工作流程。

#### 输入文件（必须全部读取）

项目级：
1. `memory/techContext.md` — 技术栈和脚手架结构
2. `memory/systemPatterns.md` — 架构规范和禁止事项
3. `memory/databaseBaseline.md` — ★ 已有数据库表基线（避免重复建表）
4. `docs/architecture/` — 全目录：全局架构约束三件套 + 可选架构设计文档（单/多文档，兼容存量）
5. `docs/references/{version}/`（本版本对外需求 + 对方资料）+ `docs/references/`（跨版本通用全接口文档）— 第三方接口文档（如涉及；版本专属归 `{version}/`、通用归根，见 06 §2.6）
6. `code/` — 已有脚手架代码
7. `env/.env` — 环境配置

迭代级（★ **用 glob 一次读全设计目录，不硬编码裸名**——兼容约定 14 三态：拆分态 `00_索引.md`+`01_详细设计.md`/`02_数据库设计.md`/`03_接口设计.md`… / 单份态 `00_<专题>.md` / 历史存量裸名 `详细设计.md` 等；否则拆分态主文档读不到）：
8. `docs/design/detail/{version}/*.md` — **全目录读取**（含详细设计 / 接口设计 / 数据库设计 / 对外开放接口 / 集成对接 / 事实清单等全部专题主文档；先读 `00_索引.md`（如有）掌握分册结构再逐份读）
9. 其中 **对外开放接口**（专题主文档，如 `04_对外开放接口.md` 或裸名 `对外开放接口.md`，★ 如存在）— 实现时**严禁**引入 Session/Cookie/JWT 依赖；路径前缀按事实清单「对外开放接口 base」走；写操作必须实现幂等键校验 + 限流 + 审计日志，按文档 9 项规范落地。**本地 MD 始终为权威**——同目录的 `openapi.yaml`（如存在）只是派生的机读副本，详细接口定义以本地 MD 正文为准，直接读即可
10. 其中 **事实清单**（`*事实清单.md`，★ 如存在 — 端口/context-path/API 前缀/proxy 的硬约束，与 `application.yml` / `vite.config` 对齐）

#### 开发步骤

```
Step 0: ★ 读取*事实清单.md（如存在）—— 后续所有路径/端口操作必须与之一致；
        如本 Sprint 主动改 context-path/端口，须在事实清单的「⚠️ 本次变更」表里有声明
Step 1: ★ 应用数据库 SQL 到开发库（自动执行 · 检测驱动 · 幂等 · 不静默跳过 — 见约定 6）
        —— 触发：`docs/deployment/{version}/sql/增量/` 下存在 `01_*.sql`~`98_*.sql`（跳过 `99_回滚脚本.sql`）即执行（**兼容 legacy `code/sql/{version}/`**——存量未搬迁项目 grandfather 识别，二者取存在者）；无 SQL 文件则跳过本步。
           ★ **检测驱动、不依赖研发执行计划是否显式列 SQL 任务**（根治「计划没提 SQL → sprint-batch 全量开发没执行 → 部署后表缺失报错」）。
        —— DB 连接来源：读后端 `application.yml`（若指定 profile 则读生效的 `application-{profile}.yml`）的 datasource
           （`spring.datasource.url` → host/port/库名，`username`/`password`；其它技术栈取等价 datasource 配置）解析连接。
           解析不到 datasource → **WARN「无法确定开发库连接、SQL 未应用」+ 标为部署阻断风险**，提示用户在 application.yml 配好 datasource 后重跑，**不静默跳过、不当作已执行**。
        —— 执行（本地/可直连）：按两位序号自然顺序对开发库执行每个 SQL 文件（用对应 DB 客户端，如
           `mysql -h <host> -P <port> -u <user> -p<pwd> <库名> < docs/deployment/{version}/sql/增量/NN_xxx.sql`），
           遇错即停并报出错文件 + 报错信息（不吞错继续）；DB 不可达 / 无客户端 → 同上 WARN + 部署阻断风险标记。
        —— ★ 幂等（只应用本版本尚未应用过的 SQL）：已应用清单 `memory/{version}/{user}/.applied-sql.json`
           （记 {文件名, 应用时间, SQL 内容 sha256}）；已在清单且 sha 未变 → 跳过；SQL 文件内容变更（sha 变）→ 重跑该文件。
           配合设计期 `CREATE TABLE IF NOT EXISTS` / `INSERT ... ON DUPLICATE KEY UPDATE`（约定 23）双重防重复。
        —— 收尾：应用成功后把新增/变更的表结构同步回写 `memory/databaseBaseline.md`（约定 6）+ 刷新 `.applied-sql.json`。
        —— 无人值守（--unattended）：DB 不可达/连接缺失 → 记 baseline + 终端 WARN + #4 提示「SQL 未应用、部署将报错」，
           不阻塞其它开发步骤，但**该风险必须在开发汇总里显式呈现**（避免部署后表缺失被静默）。
Step 2: 创建模块骨架（参照已有模块）
Step 3: 创建数据模型（Entity/Model/PO）
Step 4: 创建 DTO（含校验注解）
Step 5: 使用 TDD 逐个实现 API（superpowers:test-driven-development）
Step 6: 配置一致性核对（★ 不在此逐任务编译）；grep 本 Sprint 改动的
        application.yml / vite.config / nginx.conf，确认 context-path / 端口 / proxy
        仍与事实清单一致（无需启动服务）。编译验证已收敛到验收（/sprint-test），
        仅改动侧 + 资源受限执行，见 agents/backend.md「Step 7」
Step 7: ★ DI 依赖可解析性静态门（纯 grep 级、不编译/不打包/不起服务——补「编译查不出、
        启动期才炸」的那一半，见 rules/backend.md）：
        ```bash
        # 唯一实现 = CVL SKILL 脚本；参数、退出码（含 exit 2 与 unreadable_files）口径见 rules/backend.md「DI 依赖可解析性」段
        if [ -d code/backend ]; then
          python3 {{AIDP_HOME}}/skills/code-verification-loop/scripts/check_di_resolvability.py \
            code/backend --changed-only --json
        else
          echo "跳过：无 code/backend（纯前端项目），不算违规"
        fi
        ```
        —— Critical：记入本 Sprint「问题汇总清单」交 /sprint-bugfix 修（提示语含「同类型既有惯例」修法）；Warn：汇总提示不阻断。
Step 7bis: ★ 注释比例反向门（约定 17 的**另一侧**；纯静态）：
        ```bash
        python3 {{AIDP_HOME}}/scripts/check_comment_ratio.py --json   # 无 code/ 自报跳过并返回 0
        ```
        —— 约定 17 的回检**两个方向都要有**：只查"写少了"时，过度注释零成本、零反馈信号。
           本门判 `注释行/代码行 > 1.0 且未命中 A 档特征` = **Important，不阻断**。
           A 档（判据/口径/状态机/并发/安全…）与契约型注释（JSDoc `@typedef/@param` 等、
           类型声明文件）**自动豁免** —— ⛔ 本门不是"少写注释"的许可，它只砍 B/C 档的同义反复。
           确需保留就地写 `comment-ratio-ignore: <原因>`（原因必填）。

Step 8: ★ 上游调用日志静态门（约定 40；同样纯静态、不起服务）：
        ```bash
        python3 {{AIDP_HOME}}/scripts/check_upstream_call_log.py --json   # 无 code/ 时脚本自身打印「跳过」并返回 0，⛔ 别加 `[ -d code ] &&` 守卫：无 code/ 时整条复合命令 rc=1，会被按下面的「1=有 Critical」误读成违规
        ```
        —— C1 出站调用类零日志 / C2 成功路径不可见（日志全为 warn/error）= **Critical**，
           I1 无 URL / I2 只有 debug / I3 疑似凭据明文 = Important。判定口径单一信源 =
           该脚本 + rules/code.md 约定 40，命令端只编排不复述（约定 21）。
        —— **本 Step 只在本 Sprint 新增/改动了出站调用（第三方 HTTP / RPC / 对象存储 /
           短信邮件网关等）时才需关注结论**；未触碰出站调用时脚本会输出
           `outbound_files: 0` 或结论不变，直接过。
        —— 退出码：`0`=无 Critical · `1`=有 Critical · `2`=入参错（修参数重跑、不算违规）。
           Critical 当场修（补请求段/响应段日志或薄封装打点，骨架见
           `{{AIDP_HOME}}/reference/上游调用日志参考实现.md`）；Important 逐条判断是真问题
           还是加 `upstream-log-ignore: <检查号> <原因>`（**原因必须写**）。
        —— ⛔ **I3（疑似凭据明文）不得靠"少打日志"绕过**：约定 40 要的是「打全 + 脱敏」，
           不是「怕泄漏所以不打」——后者会把成功路径重新变成不可观测。
```

#### 核心原则
- 接口 URL、参数、响应必须与 API 设计文档完全一致
- **路径/端口/proxy 必须与 `*事实清单.md` 一致**（如存在）；冲突时**改设计不改代码**，除非事实清单的「⚠️ 本次变更」已声明
- 模块结构、分层、命名必须与已有脚手架代码一致
- 所有代码必须符合架构约束文档的要求
- **★ 代码注释强制规范**：按 CLAUDE.md 约定 17 执行（类/方法/字段文档注释 + 关键代码段注释，覆盖 Claude 默认"无注释"原则）；Sprint 测试阶段 `code-verification-loop` 回检注释完备性

