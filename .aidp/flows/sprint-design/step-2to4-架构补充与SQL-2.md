# sprint-design · Step 2–4 详情 — 分片 2/共2（生成 SQL 脚本 + 动态更新 architecture）

> 本片承接 `step-2to4-架构补充与SQL-1.md`。**本片覆盖范围**：Step 3（生成 SQL 脚本，含 3.0 提取前版风格规则 / 3.1 生成本版 SQL 文件）+ Step 4（动态更新 `docs/architecture/`，含 4.1 技术选型 / 4.2 架构约束 / 4.3 同步 systemPatterns）。
>
> ⚠️ **权威性**：进入本段后以本文件为准逐项执行，不得凭命令主体骨架或记忆略过任一子步骤。
> ⚠️ **维护**：本文件与命令主体同属 template 自有、随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-design/step-2to4-架构补充与SQL-2.md`。理据/根因见同目录 `rationale.md`。

---

### Step 3：生成 SQL 脚本

路径：`docs/deployment/{version}/sql/增量/`（AIDP 项目级父约束，按版本隔离）；文件命名跟随 `dev-logic-architect` SKILL Module D + `dev-execution-planner` SKILL DDL Task 规范——**中文名 + 两位数字序号前缀**（`{NN}_<中文名>.sql`），DDL/DML 同一序号空间按执行顺序混排（不按文件类型分组），`99_回滚脚本.sql` 序号固定保留给本版本回滚。示例：`01_用户表DDL.sql` / `02_订单表DDL.sql` / `03_订单状态字典初始化.sql` / `99_回滚脚本.sql`。详细规则按 CLAUDE.md 约定 21 查 SKILL，命令端不复述。SKILL 已启用路径占位符自动发现（`{SQL脚本目录}` 等），AIDP 占位符↔项目路径映射见 `docs/init/06_版本与用户目录约定.md` §2.5.7。

#### Step 3.0：★ 历史 SQL 风格归纳（单一信源 = `dev-logic-architect` 核心原则 12 / 检查项 18）

历史风格沿用的扫描面、维度与「历史风格本身不统一时取谁」的裁决**一律以 SKILL 为准**（约定 21，命令端不另列维度表与裁决规则）。命令端只跑确定性归纳，把结果作为 Step 3.1 的输入：

```bash
python3 {{AIDP_HOME}}/skills/dev-logic-architect/scripts/check_sql_style_consistency.py . "docs/design/detail/{version}/" --history-only --json
```

- 有历史 SQL → 把归纳结果（含样本来源文件）随 prompt 传给 Architect Agent / `dev-logic-architect`；脚本报历史风格分裂时，按 SKILL 口径取基线并在设计文档里标注理由。
- 无历史 SQL（首版 / 只画表未落 SQL）→ 脚本自判跳过；本版自行确立风格基线，并在 `数据库设计.md` 中显式声明，便于后续版本继承。

#### Step 3.1：生成本版 SQL 文件

1. **只写本版新增 / 变更**（约定 37 增量轨 + SKILL Module D「不累积历史版本 SQL」）：按 SKILL 命名规范写入 `docs/deployment/{version}/sql/增量/{NN}_<中文名>.sql`，**`NN_` 从 `01` 起**（DDL/DML 同一序号空间按执行顺序混排），文件首部注释标明 `-- {version}: 新增表 / 变更字段`。⛔ **不复制前版 `sql/增量/` 下任何文件**——前版 SQL 只作 Step 3.0 的风格采样源；复制基线由 SQL 版本隔离门（`check_sql_version_isolation.py` 两轨布局 V2）判 Critical。
2. **新增/变更 DDL 遵循 Step 3.0 的风格归纳结果**。
3. `99_回滚脚本.sql` 序号固定保留给本版本回滚（只含本版变更的回滚）。
4. 本版无 DDL/DML 变更 → 不产空占位文件（N3 空占位判违规）；全量建库脚本属约定 37 全量轨，由 `/version` 发布期产出，⛔ 不在本步生成。
5. **DDL 幂等性硬要求**：所有 CREATE/ALTER 包含 `IF NOT EXISTS` / `IF EXISTS` 判断（SKILL「Module D 版本归档完整性」维度内置核验）。

**所有 .sql 文件统一要求**：建表语句完整可执行 / 索引齐全 / 初始化数据（如有）独立成块 / 兼容项目实际使用的数据库（MySQL/PostgreSQL/达梦 等）。

**★ Step 3.2：SQL 落位到 `docs/deployment/{version}/sql/增量/` + 版本落位一致性防护（两阶段：SKILL 暂存 → 命令端 git mv 归位；堵"补充/增量 SQL 落错版本目录、文件头版本≠目录版本"）**：

> **两阶段落位机制（约定 21：上游 SKILL 只能暂存、最终位置由命令端搬迁）**：AIDP 的 SQL 最终落 `docs/deployment/{version}/sql/增量/`（部署资产）。但上游 `dev-logic-architect` SKILL（职责边界：SKILL 不感知 AIDP 部署目录布局）**原生**把 SQL 生成到 **`{SQL脚本目录}/v{版本号}/`（★ 带 `v` 前缀，SKILL「SQL 版本严格隔离铁律」硬约定，如 `code/sql/v0.2.0/`）**——`{SQL脚本目录}` 经 §2.5.7 映射为 **`code/sql/`（暂存位）**，SKILL 自行在其后追加 `/v{版本号}/`、无法表达"版本在 sql 之前"的目标层级。故**命令端在 SKILL 返回后确定性 `git mv` 把暂存产物搬迁到最终位置**，SKILL 无需改动。**★ 扫描防御式双模式**：命令端搬迁扫描**同时覆盖** `code/sql/v*/`（SKILL 实际输出，含各种 `v` 前缀写法）**与** legacy `code/sql/{version}/`（无 v，历史/兼容），以任一命中的本轮 `.sql` 为搬迁源，避免"glob 只写无 v 路径 → SKILL 的 v 前缀产物匹配不到 → SQL 静默不归位"的功能性断链。
> **根因（沿用）**：补充/增量模式下，SKILL 若"扫描既有目录推断路径"会复用上一版本目录，导致本轮 SQL 落进旧版本目录、文件头版本与目录版本打架。命令端**显式钉死版本、SKILL 返回后确定性校验纠正 + 搬迁**，不依赖 SKILL 自行推断。

1. **调 SKILL 前**：`mkdir -p "docs/deployment/{version}/sql/增量"`（**无条件预建本次迭代版本的最终 SQL 目录**，哪怕本轮暂无 SQL 也先建，避免惰性创建缺目录）；传参 `{SQL脚本目录}=code/sql/`（暂存位，§2.5.7），并**显式钉死** `{version}`=前置流程解析的**当前迭代版本**（不是 `{prev-version}`），要求文件头版本注释一律写 `{version}`、**禁止 SKILL 把本轮产物写进 `{prev-version}` 目录**。
2. **SKILL 返回后（确定性 搬迁 + 校验 + 纠正）**：
   ```bash
   # ★ 防御式双模式：SKILL 实际把 SQL 生成到带 v 前缀的 code/sql/v{版本号}/（如 code/sql/v0.2.0/），
   #   历史/兼容也可能落无 v 的 code/sql/{version}/。以下扫描【两种都覆盖】，避免只写无 v 路径漏搬。
   #   STAGE_DIRS = 本轮所有可能的 SQL 暂存目录（v 前缀 glob + 无 v 精确 + 上一版本目录）
   STAGE_DIRS="code/sql/v* code/sql/{version} code/sql/{prev-version} code/sql/v{prev-version}"
   # ① 版本落位提示：本轮新增/改动 SQL 若落进上一版本目录（v{prev} 或 {prev}）→ 一并纳入下方搬迁、并 WARN
   git status --porcelain -- code/sql/{prev-version}/ code/sql/v{prev-version}/ 2>/dev/null | grep -E '\.sql$' && \
     echo "⚠️ 本轮 SQL 落入上一版本暂存目录 → 将随搬迁归位到 docs/deployment/{version}/sql/增量/"
   # ② ★ 搬迁到最终位置（Option A 核心）：把本轮 SKILL 暂存产物（任一 STAGE_DIRS 命中的 *.sql）→ docs/deployment/{version}/sql/增量/
   #    只搬本轮新增/变更文件（git status 挑），不动 Step 3.1 继承来的历史文件；dedup 同名
   for f in $(git status --porcelain -- $STAGE_DIRS 2>/dev/null | grep -E '\.sql$' | sed 's/^...//' | sort -u); do
     [ -f "$f" ] && git mv -k "$f" "docs/deployment/{version}/sql/增量/$(basename "$f")"
   done
   # 清理搬空后的暂存目录（v 前缀 + 无 v 都试）
   for d in code/sql/v{版本号} code/sql/v{version} code/sql/{version}; do
     [ -d "$d" ] && rmdir --ignore-fail-on-non-empty "$d" 2>/dev/null || true
   done
   # ③ 文件头版本号 ≠ 目录版本 → 以目录版本为准修正（搬迁后在最终位置校验）
   for f in docs/deployment/{version}/sql/增量/*.sql; do
     head -8 "$f" | grep -oE 'V[0-9]+\.[0-9]+(\.[0-9]+)?' | grep -qxF "{version}" || \
       [ -z "$(head -8 "$f" | grep -oE 'V[0-9]+\.[0-9]+(\.[0-9]+)?')" ] || \
       echo "⚠️ $f 文件头版本号与目录版本 {version} 不一致 → 需修正文件头为 {version}"
   done
   ```
3. **④ 回写设计文档 SQL 引用路径（搬迁配套）**：SKILL 生成的详细设计/数据库设计正文（Module D 交付物清单、数据表来源 SQL 路径等）里若引用了暂存位 SQL 路径（`code/sql/v{版本号}/*.sql` 带 v 前缀，或历史无 v 的 `code/sql/{version}/*.sql`），命令端**同步 Edit 回写为最终位置 `docs/deployment/{version}/sql/增量/*.sql`**，避免"SQL 已搬走、设计文档仍指暂存位"的断链。
   命中任一 ⚠️ → 命令端**自动 `git mv` 归位/搬迁 + Edit 修正文件头与文档引用**（使"文件头版本 == 所在目录版本 == 本次迭代版本"三者恒一致、且 SQL 落最终 `docs/deployment/{version}/sql/增量/`），终端 WARN 记录纠正动作、**不静默放过**。继承的历史文件（Step 3.1 从 `{prev-version}` 复制来、头部标旧版本）不在校验/搬迁范围——只处理**本轮新增/变更**的 SQL。

### Step 4：★ 动态更新 docs/architecture/

**关键原则**：architecture 三份文档是**累积的全局约束**。处理逻辑取决于 Step 2 的三态判定结果：

- **有效约束**（Step 2 判定为"有效"）→ 本次设计已遵循其约束，仅在本次设计引入新技术/新约束时**增量追加**
- **空/模板/过期**（Step 2 判定为"空"或"过期"）→ 从本次详细设计**反向填充**完整内容

#### Step 4.1：更新技术选型.md

读取 `docs/architecture/技术选型.md`：

> ★ **保留「运行时端点契约」段**：若本文件已有 Step 0.5.5 写入的「运行时端点契约」段（端口/context-path/前缀/`{子项目}名`/根包名/部署 URL），本步**只校对一致、不覆盖不删除**（它是用户已确认的权威基线）；发现设计与该段冲突 → 以该段为准回写设计，不反向改契约。

**情况 A — 空/模板/过期（反向填充）**：
从本次详细设计中提取完整技术栈，生成「技术栈总览」表格 + 「选型决策记录」章节 + 「变更历史」。
- **★ 若架构设计文档存在**：优先据架构设计中的技术选型意图派生，再叠加本次详细设计的增量。

**情况 B — 有效约束（增量追加）**：
如 `dev-logic-architect` 生成的设计引入了新技术（框架/组件库/第三方服务/缓存/消息队列等）：

1. 在「技术栈总览」表格追加新技术行，标注 `关联 Sprint`
2. 在「选型决策记录」章节追加决策（背景 / 方案对比 / 决策 / 影响）
3. 「变更历史」表追加一行

#### Step 4.2：更新架构约束.md

**情况 A — 空/模板/过期（反向填充）**：
从本次详细设计中提取架构级约束（分层规则、命名规范、安全策略、性能要求等），生成完整的架构约束文档。
- **★ 若架构设计文档存在**（`架构设计.md` 或 `架构设计/`）：**优先据架构设计派生约束条目**（提取其分层/技术选型/命名/安全/性能等设计意图，转写为强约束），再叠加本次详细设计的增量——即"仅有架构设计、缺架构约束"时也能补出一份完整的 `架构约束.md`，全局约束基线不缺失。

**情况 B — 有效约束（增量追加）**：
如设计中产生了新的架构级约束（分层/命名/安全/性能等）：

1. 在对应章节追加约束条目，标注来源 Sprint
2. 「变更历史」表追加一行

例：本次 Sprint 引入 Redis 缓存 → 在「性能约束」追加「热点数据必须走 Redis，TTL ≥ 5 分钟」

#### Step 4.3：同步到 memory/systemPatterns.md

如有新 ADR，追加到 `memory/systemPatterns.md`（项目级，跨版本累积）。

