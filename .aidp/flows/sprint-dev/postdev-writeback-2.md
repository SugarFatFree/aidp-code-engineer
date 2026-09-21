# sprint-dev · 开发完成后回写详情（分片 2/3 · Step X.0–X.7）

> **【分片 2/3 · postdev-writeback 二次切分】** 本片是 `/sprint-dev` 命令「开发完成后：自动回写需求 + 设计文档」段的中段，覆盖 **Step X.0（研发需求回写）/ X.2（详细设计）/ X.3（研发执行计划）/ X.4（memory）/ X.5（SQL 脚本）/ X.6（事实清单）/ X.7（配置项清单，约定 25）**。前片 `postdev-writeback-1.md`（Step X.0.0 级联检测），后片 `postdev-writeback-3.md`（Step X.8 部署流程）。进入回写段须按序 Read 全 3 片、以本文件为准逐项执行、不得略过任一 Step。

---

#### Step X.0：研发需求回写

> ⛔⛔ **本步（X.0）及 X.2 / X.3 的四级级联【仅在收口点或 `--cascade-now` 下执行】**——
> 约定 22 默认走**攒批**：`postdev-writeback-1.md` 步骤 3.8 把变更记入
> **受影响各族的增量册**（四族落点见 `{{AIDP_HOME}}/reference/开发期族增量.md`）后**直接跳到 Step X.4**，本步整段跳过。
> 判定与收口规则单一信源 = `{{AIDP_HOME}}/reference/开发期族增量.md`。
>
> ⛔ 下方各步写的「自动触发 L1/L2/L3/L4」「随后自动级联」**只描述收口时的动作**，
> **不是默认路径**。攒批下照此执行 = 写完台账又把四级跑一遍：攒批收益归零、还多一份台账，
> 且级联发生在**没有合并同类项 / 没有失效消解 / 没有按合并后总量重判档位**的错误时机。


> 编号说明：本回写段编号为 X.0 / X.2 / X.3 / X.4–X.7 + X.8（部署流程 SOP，检测驱动独立段；需求与设计分列 X.0 与 X.2，**无 X.1**）；编号保持稳定不重排，避免下游引用漂移。

仅当 Step X.0.0 影响清单含「需求漏项」类（L1 触发条件）时执行；由 X.0.0 自动驱动，下方步骤为执行细则：

1. （X.0.0 已完成扫描）从影响清单提取"非计划内功能点"（临时加的按钮 / 新增的导出选项 / PRD 没提的边界场景处理等）
2. 写 `docs/requirements/{version}/产品提供/sprint-{NNN}-开发期补充-{YYYYMMDD}.md`（标注"来源：sprint-{NNN} 开发期回溯"）
> ⛔ **本段（X.0.0 驱动的即时级联 = `--cascade-now`）四级一律传 `--ledger-cascade`，⛔ 不传 `--supplement={NN}`**：
> 这里回填的是**开发期代码变更**，收口时**直接写进各族内容主文档正文**
> ⛔ 不新建分册、不占 `NN_` 序号（那是产品侧 PRD/原型变更与口述累进的命名空间）。
> `--supplement={NN}` 留给 **Phase 0B.1.1 口述累进**与产品侧 PRD/原型变更——那是产品会去读的交付物。
> 两条路径**不共享 NN 锚定**：本段无需锚定 NN。落盘规则详见 `{{AIDP_HOME}}/reference/开发期族增量.md`「收口执行要点」第 3 条。

3. **自动触发 L1 — 研发需求**：经 `/sprint-requirements {version} --ledger-cascade [--unattended]` 编排（**研发需求唯一入口**，内部以增量 prompt 驱动 `ux-logic-extractor`；★ **不直调 SKILL**——直调会跳过命令端的落盘归一 / 多系统拆分 / 头部元数据表 / AIDP 硬规范回检）→ **就地改** `docs/requirements/{version}/研发需求/01_研发需求.md`
4. **自动触发 L2 — 详细设计**：`/sprint-design --ledger-cascade [--unattended]`：通过 Step 0.6.4.7 全扫代码现状 + Step 0.3 四象限对比，本批新增项会自动落入象限 ③「代码超前-补写」，由 dev-logic-architect 产出正文 → **就地改** `docs/design/detail/{version}/` 的 `01_详细设计.md`·`02_数据库设计.md`·`03_接口设计.md`（按实际范围）
5. **自动触发 L3 — 研发执行计划**：`/sprint-plan --ledger-cascade [--unattended]` → **就地改** `docs/plans/{version}/01_研发执行计划.md`（新增任务条目 / 工时调整 / 拆分调整）
6. **自动触发 L4 — 研发自测用例**：`/sprint-selftest --ledger-cascade [--unattended]`（研发自测唯一入口，内部经 `dev-manual-testcase` 增量）→ **就地改** `docs/testing/{version}/研发自测/` 既有用例册；输入：本轮各族增量 + 既存 `docs/testing/{version}/研发自测/` 下自测方案与用例文件 + `code/` 实际代码；本批新增的"非计划内功能点"必须覆盖到用例

> 分支 A（Sprint 末尾回头补文档）与分支 B（Sprint 开始前先文档后开发）的关系见 `postdev-writeback-1.md` Step X.0.0「与 Phase 0B.1.1 的关系」段；两者收敛到同一套补充文档体系。

#### Step X.2：调用 dev-logic-architect skill 更新设计（由 Step X.0.0 自动驱动；走 `/sprint-design --ledger-cascade [--unattended]` 编排）

仅当 Step X.0.0 影响清单含「设计层变更」（L2 触发条件）且 L1 未触发（即不需要研发需求补充，仅需设计层补充）时执行：

```
输入：
- Step X.0.0 影响清单文件（sprint-{NNN}-upstream-impact-*.md）的 L2 条目
- 原 docs/design/detail/{version}/ 下 `*详细设计.md` + `*接口设计.md` + `*数据库设计.md`（glob 兼容 `01_/02_/03_` 前缀名与历史裸名）
- code/ 实际代码现状（含本 Sprint 改动）

输出：dev-logic-architect（增量 prompt 驱动）产出正文，命令端按 `--ledger-cascade` 追加进
- docs/design/detail/{version}/ 的 `01_详细设计.md`·`02_数据库设计.md`·`03_接口设计.md`（按实际范围就地改）

随后自动级联 L3（研发执行计划补充，如任务受影响）+ L4（自测用例补充）。
```

#### Step X.3：调用 /sprint-plan --ledger-cascade [--unattended] 更新研发执行计划（由 Step X.0.0 自动驱动）

仅当 Step X.0.0 影响清单含「计划层变更」（L3 触发条件）时执行——含 ① L1/L2 触发自动级联到 L3 / ② 仅计划层变更（如 Sprint 拆分调整 / 工时实际偏差 >50%）：

```
命令：/sprint-plan --ledger-cascade [--unattended]   # 本命令带 --unattended 时必透传

输入：
- `01_研发需求.md` 本轮改动处（如 L1 触发）
- `01_详细设计.md` 等本轮改动处（如 L2 触发）
- 原 docs/plans/{version}/01_研发执行计划.md
- Step X.0.0 影响清单的 L3 条目（含工时偏差 / 拆分变更 / 新任务）

输出：docs/plans/{version}/01_研发执行计划.md 就地改（新增任务 / 取消任务 / 时间调整）

随后自动级联 L4（自测用例补充）。
```

#### Step X.4：更新项目级 memory（如涉及架构级变更）

- 新增/变更表 → `memory/databaseBaseline.md`
- 新架构决策 → 追加 ADR 到 `memory/systemPatterns.md`
- 新技术栈 → 更新 `memory/techContext.md` + `docs/architecture/技术选型.md`

#### Step X.5：更新 SQL 脚本

如新增/变更表，按 SKILL 命名规范（中文 + 两位数字序号前缀；`99_回滚脚本.sql` 序号保留）新增到 `docs/deployment/{version}/sql/增量/{NN}_<中文名>.sql`，序号续在当前版本最大序号 +1（详见 `/sprint-design` Step 3）。

#### Step X.6：★ 更新*事实清单.md（如涉及配置事实变更）

如本 Sprint 改动了 `application.yml` / `application.properties` / `vite.config.*` / nginx 等**真实运行时配置**（context-path / 端口 / proxy / API 前缀 / 健康检查路径），必须：

1. 在 `docs/design/detail/{version}/*事实清单.md` 主表对应行更新「新值」列
2. 在「⚠️ 本次变更」表追加一行（项 / 旧值 / 新值 / 理由 / **已联动消费者点（必填）** / Sprint-{NNN}）
3. **遍历事实清单「路径消费者点」表**，逐一确认本变更涉及的消费者是否已同步修改：
   - 前端 axios baseURL / URL 守卫 / SSE / WS / dev proxy / .env*（所有 profile）/ router base
   - 后端 CORS / 跳转 URL / 接口设计.md / 数据库 / Redis key 前缀（如复用 base 作为命名空间）
   - Nginx / Docker / K8s
4. 如某消费者点本次确实无需联动 → 在「已联动消费者点」列以括号注明"无需联动 — 原因 XXX"
5. 漏改的消费者点常导致下次"双前缀 404 / SSE 走错地址 / nginx 反代失效"等级联事故 —— 提交前用 `git diff --name-only` 与事实清单「路径消费者点」表对账，缺项要么补改要么注明"无需联动"
6. **★ 消费者点集合是"会变大"的、不止 base 改动才动本表**：Phase 1.3 Step 1「请求通道单一判据 + 消费者点登记门」在**新增请求通道**（新 composable / 工具 / `fetch`·`EventSource`·`WebSocket`）时就要往「路径消费者点」表**补登记新行**——本 Step X.6 管的是 base/context-path **改动时的联动**，二者互补。集合悄悄变大而无人登记，会让下次 base 变更漏掉新通道（双前缀 404 温床）。

#### Step X.7：★ 维护配置项清单

**核心原则（约定 25 配置文件分层落地）**：
- **真实配置文件是权威**（`code/.../application.yml` / `env/.env` / `nginx.conf` 等），git 跟踪即可，不在 .md 重复
- **★ 配置项清单.md 是【增量轨】文档，只回答一件事：本版新增了什么配置、删除了什么配置**（约定 37.2）。**判定依据 / 背景论述 / 各环境对照 / 执行建议 / 风险评估一律不进本文件**——它们归 `全量/00_索引.md`，本文件最多一行指向（约定 25 不双写）。
  - **⛔ 只用代码块，不做「代码块 + 下方表格」两处对照**：同一条变更写两遍必然漂移，且真正要看的被淹没。**注释直接写进代码块**（YAML 用 `#`、properties 用 `#`、conf 按各自语法），**行内注释 ≤20 字符**。
  - **⛔ 承载方式 / 配置文件全量索引 / 敏感项 checklist / 历史迁移 不由本文件承载**——它们是**常驻信息**而非本版增量，放在增量文档里属错位、开发期手工维护必然落后。由发布期约定 37 的 `全量/00_索引.md` 从**真实环境只读采集**重建。本版新增的敏感项在增量代码块里用 `# 必填·敏感` 标一下即可，发布期自动汇总。
  - 实测收益（下游回流）：6 份增量文档 414 行 → 168 行（-59%），信息零丢失。
- **禁止**：① 在 .md 复抄整个配置文件（再大也别贴）；② 维护 key → 示例值的全量大表（已被代码文件本身覆盖）；③ 创建 `.env.example` / `application.example.yml` 等示例副本文件（真实文件 + 差异片段已足够，示例副本会双信源歧义）
- **★ 分层也约束两份 .md 之间（部署流程 vs 配置项清单，Step X.8 联动）**：约定 25「同一份信息只在一处维护」不仅管"配置文件 vs .md"，也管 `部署流程/部署流程.md` 与 `配置文件/增量/配置项清单.md` **两份 .md 之间不得双写配置项内容**——**配置项明细/后果/敏感项加固归本清单**；**部署流程只声明"是否需要改 + 指向本清单"**（全部有默认值 → 一句"默认即可，见清单"；确有必填 → 只列 key 名、后果归清单）。分工口诀：**流程文档讲怎么做，清单讲配什么**。

**触发条件**：本 Sprint 改动了任一配置文件（git diff 命中以下任一）**或新增/修改了代码内动态配置注入**：
- 后端 Spring：`code/**/application*.{yml,yaml,properties}` / `code/**/bootstrap*.{yml,yaml,properties}`
- 后端其他：`code/**/{config,settings}.{json,toml,ini,py}`
- 前端：`code/**/.env*` / `code/**/vite.config.*` 中可配置常量段
- 全局：`env/.env*`
- 部署：`docs/deployment/{version}/**/*.{conf,yaml,yml}`（nginx / docker-compose / k8s 等）
- **★ 代码内动态配置注入（不改配置文件也触发 — 堵"@Value 默认值内联在注解里、application.yml 不动就漏登记"的口子）**：本 Sprint 的代码 diff 新增/修改了**由配置中心（Nacos/Apollo/…）或环境注入的可配置属性**，即使 `application.yml`/`.env` 未变也触发。识别信号（按项目技术栈取等价）：
  - Spring：`@Value("${xxx:默认值}")` / `@ConfigurationProperties(prefix=...)` 绑定类的新字段 / `@Scheduled(cron="${xxx}")`（**可配置定时器**：cron 表达式、`enabled` 开关、jitter 等由 `${}` 注入的属性都算）/ `@RefreshScope` 标注的可变配置 Bean（约定 27 联动）
  - 其他栈等价：从环境变量 / 配置服务读取的运行时可配置项（`os.getenv` / `config.get` / `process.env` 注入且有默认值的键）
  - **★ 约定 27 ⟷ 约定 25 联动**：`code-verification-loop` 维度 4 / 本步识别到"注入配置中心可变 key"（约定 27 热刷新回检面）后，**必须同步把该 key 登记进配置项清单**（约定 25），二者是同一份可变配置的"代码热刷新能力"与"运维登记"两面，不得只做其一。登记内容含：key 名 / 默认值 / 配置中心 data-id（如有）/ **是否需重启生效**（如 `@Scheduled` 的 cron 改动通常需重启或依赖 `@RefreshScope`+任务重注册，务必标注）/ 承载方式。

**输出文件**：`docs/deployment/{version}/配置文件/增量/配置项清单.md`（迁配置中心后变体名 `配置项清单-{中心}.md`）。配置文件类（清单 + nginx/docker-compose/k8s 等真实部署配置文件）统一归 `配置文件/` 子目录，`docs/deployment/{version}/` 根留给其他部署信息（上线步骤 / URL 指南 / 发布说明等）。

**首版判定**（用通配兼容已迁配置中心的变体名）：

```bash
ls docs/deployment/{version}/配置文件/增量/配置项清单*.md 2>/dev/null
```

无匹配 → 首次创建；有匹配 → 增量更新。

> ★ **部署流程 SOP + SQL执行台账独立为 Step X.8（检测驱动，不受本 Step X.7「配置文件被改动」触发门约束）**——⛔ 部署流程维护**不得**嵌在本步内：那样"只新增 SQL / 只加部署后回填接口 / 只需重启、零配置文件改动"时本步不进入，部署流程首版判定永远够不到（典型形态：「多个 SQL + 重启 + 回填接口、零配置改动」的版本零产出）。故独立为 **Step X.8**、触发源为**部署侧实质变更检测**（照搬约定 6 SQL 自动应用的检测驱动范式），见 `postdev-writeback-3.md` Step X.8。

**文件结构（3 段，落 `docs/deployment/{version}/配置文件/增量/配置项清单.md`）**：

| # | 章节 | 内容 |
|---|------|------|
| 1 | 新增配置 | 按 dataId / 文件分组的代码块，**只列本版新增的项**；行内 `#` 注释 ≤20 字符（写"是什么/必配可选"，不写论证）|
| 2 | 删除配置 | 同为代码块，**用缩进表达删除粒度**（整段删 / 单键删 / 整棵子树删）+ ≤20 字符理由 |
| 3 | 运行时配置文件变更 | nginx / docker-compose / k8s 的**改动片段**（约定 37.2）：片段代码块 + 插在哪个 server/location 块 + 生效动作（`nginx -s reload` / 重启）。**绝不放整份文件** |

> 文件头两行导览：「本文件只讲本版**改了什么**；判定依据 / 各环境对照 / 敏感项完整清单见 `../全量/00_索引.md`」。**每段为空也要留标题写"无"**（零变更是合法结论，但要显式成文）。

**★ 删除段的缩进粒度示例**（平铺成表格会丢掉这层信息）：

```yaml
auth:                   # 整段删 · 无消费
sso:
  platform-org-id:      # 单键删 · 无消费
ec:
  v06-ops:              # 整棵子树删 · Mock 残留
```

> `sso.platform-org-id` 只删一个键，**绝不能把整个 `sso` 段删掉**（那段全是认证必配项）——这正是缩进不可省的原因。共享 dataId 的删除需与其它系统会签，用 `# 需会签` 标注。

**首次创建 / 增量更新（同一套动作，幂等）**：

0. **先建目录**：`mkdir -p docs/deployment/{version}/配置文件/增量`
1. 取本 Sprint 的配置 diff（`git diff` 命中「触发条件」列出的文件 + 代码内动态配置注入新增的 key）
2. 新增项 → 追加进「1. 新增配置」对应分组代码块；删除项 → 追加进「2. 删除配置」，**按上面的缩进粒度写**
3. nginx/compose/k8s 有改动 → 追加进「3. 运行时配置文件变更」（片段 + 位置 + 生效动作）
4. **敏感项不另起段**，在新增代码块里对应行标 `# 必填·敏感`（发布期由 `全量/00_索引.md` 汇总成上线 checklist）
5. **⛔ 不要把判定依据 / 为什么改 / 各环境值对照写进来**——那属 `全量/00_索引.md`；本文件只需 key 名 + 归属 + ≤20 字符注释
6. 如本变化也在 Step X.6 事实清单（路径/端口类）记录过 → 事实清单是设计/开发视角、本清单是运维视角，**两者并存不去重**（各记各的，不互相复述内容）

**配置中心迁移操作**（用户手动触发，**不由命令自动判断**）：
1. `git mv docs/deployment/{version}/配置文件/增量/配置项清单.md docs/deployment/{version}/配置文件/增量/配置项清单-{中心}.md`（如 `配置项清单-nacos.md`）
2. 该迁移属**约定 37 全量轨**的承载变化：按 `{{AIDP_HOME}}/reference/约定细则-5.md` 更新 `配置文件/全量/00_索引.md`
   （承载方式 / 文件索引 / 敏感项 checklist / 历史迁移四段均在那里）。
   ⛔ **不要**在本文件产出的「配置项清单」里改这四段 —— 上方 3 段结构里根本没有它们（此前这几步要求
   `Edit「1. 配置承载方式」表`/`「2. 配置文件索引」表`/`「5. 历史迁移」段`，那四个章节已被明令移除，
   照做会凭空造回被删掉的结构）。
3. 本文件的「配置项清单」只需按增量轨口径记录本版改了什么（纯代码块 + 行内注释），路径写成新的承载形态。
4. 下次 /sprint-dev Step X.7 「首版判定」用通配 `ls 配置项清单*.md` 已自动适配新文件名，无需改命令本身

