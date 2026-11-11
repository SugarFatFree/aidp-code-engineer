> 本片仅供 formal。先按 `{{AIDP_HOME}}/flows/sprint-dev/light-context.md` 核父身份；light 返回对应能力分支，不执行本片。

# sprint-dev · 开发完成后回写详情（分片 2/3 · Step X.0–X.7）

> **【分片 2/3 · postdev-writeback 二次切分】** 本片是 `/sprint-dev` 命令「开发完成后：自动回写需求 + 设计文档」段的中段，覆盖 **Step X.0（研发需求回写）/ X.2（详细设计）/ X.3（研发执行计划）/ X.4（memory）/ X.5（SQL 脚本）/ X.6（事实清单）/ X.7（配置项清单，约定 25）**。前片 `postdev-writeback-1.md`（Step X.0.0 级联检测），后片 `postdev-writeback-3.md`（Step X.8 部署流程）。进入回写段须按序 Read 全 3 片、以本文件为准逐项执行、不得略过任一 Step。

---

#### Step X.0：研发需求回写

未在route.authorized_actions中的document记NOT_REQUESTED并跳过本环节；已授权分支先执行，再按light-context预留实际资源：

```bash
EXECUTION_CONTEXT="${EXECUTION_CONTEXT:?必须从父任务入参重绑真实上下文路径}"
python3 {{AIDP_HOME}}/scripts/execution_policy.py require-action --root . \
  --execution-context "$EXECUTION_CONTEXT" --action document || exit $?
```


> ⛔⛔ **X.0/X.2/X.3级联仅在document已授权且到收口点或显式cascade-now时执行**——
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

3. **自动触发 L1 — 研发需求**：经 `/sprint-requirements {version} --execution-context "$EXECUTION_CONTEXT" --ledger-cascade [--unattended]` 编排（**研发需求唯一入口**，内部以增量 prompt 驱动 `ux-logic-extractor`；★ **不直调 SKILL**——直调会跳过命令端的落盘归一 / 多系统拆分 / 头部元数据表 / AIDP 硬规范回检）→ **就地改** `docs/requirements/{version}/研发需求/01_研发需求.md`
4. **自动触发 L2 — 详细设计**：`/sprint-design --execution-context "$EXECUTION_CONTEXT" --ledger-cascade [--unattended]`：通过 Step 0.6.4.7 全扫代码现状 + Step 0.3 四象限对比，本批新增项会自动落入象限 ③「代码超前-补写」，由 dev-logic-architect 产出正文 → **就地改** `docs/design/detail/{version}/` 的 `01_详细设计.md`·`02_数据库设计.md`·`03_接口设计.md`（按实际范围）
5. **自动触发 L3 — 研发执行计划**：`/sprint-plan --execution-context "$EXECUTION_CONTEXT" --ledger-cascade [--unattended]` → **就地改** `docs/plans/{version}/01_研发执行计划.md`（新增任务条目 / 工时调整 / 拆分调整）
6. **自动触发 L4 — 研发自测用例**：`/sprint-selftest --execution-context "$EXECUTION_CONTEXT" --ledger-cascade [--unattended]`（研发自测唯一入口，内部经 `dev-manual-testcase` 增量）→ **就地改** `docs/testing/{version}/研发自测/` 既有用例册；输入：本轮各族增量 + 既存 `docs/testing/{version}/研发自测/` 下自测方案与用例文件 + `code/` 实际代码；本批新增的"非计划内功能点"必须覆盖到用例

> 分支 A/B 的分档与成文时机统一见 `incremental-contract.md`：S 契约＋台账，M 契约先行、docs 并行后汇合，L 先完整文档。X.0.0 只收新漂移，不重复已成文内容；正式补充与既有主文档级联分开核落点。

#### Step X.2：调用 dev-logic-architect skill 更新设计（由 Step X.0.0 自动驱动；走 `/sprint-design --execution-context "$EXECUTION_CONTEXT" --ledger-cascade [--unattended]` 编排）

仅document已授权且Step X.0.0影响清单含「设计层变更」（L2 触发条件）且 L1 未触发（即不需要研发需求补充，仅需设计层补充）时执行：

```
输入：
- Step X.0.0 影响清单文件（sprint-{NNN}-upstream-impact-*.md）的 L2 条目
- 原 docs/design/detail/{version}/ 下 `*详细设计.md` + `*接口设计.md` + `*数据库设计.md`（glob 兼容 `01_/02_/03_` 前缀名与历史裸名）
- code/ 实际代码现状（含本 Sprint 改动）

输出：dev-logic-architect（增量 prompt 驱动）产出正文，命令端按 `--ledger-cascade` 追加进
- docs/design/detail/{version}/ 的 `01_详细设计.md`·`02_数据库设计.md`·`03_接口设计.md`（按实际范围就地改）

随后自动级联 L3（研发执行计划补充，如任务受影响）+ L4（自测用例补充）。
```

#### Step X.3：调用 /sprint-plan --execution-context "$EXECUTION_CONTEXT" --ledger-cascade [--unattended] 更新研发执行计划（由 Step X.0.0 自动驱动）

仅document已授权且Step X.0.0影响清单含「计划层变更」（L3 触发条件）时执行——含 ① L1/L2 触发自动级联到 L3 / ② 仅计划层变更（如 Sprint 拆分调整 / 工时实际偏差 >50%）：

```
命令：/sprint-plan --execution-context "$EXECUTION_CONTEXT" --ledger-cascade [--unattended]   # 本命令带 --unattended 时必透传

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

1. document已授权时更新事实清单主表；未授权则登记当前事实漂移短行，不新增整册
2. 在「⚠️ 本次变更」表追加一行（项 / 旧值 / 新值 / 理由 / **已联动消费者点（必填）** / Sprint-{NNN}）
3. **遍历事实清单「路径消费者点」表**，逐一确认本变更涉及的消费者是否已同步修改：
   - 前端 axios baseURL / URL 守卫 / SSE / WS / dev proxy / .env*（所有 profile）/ router base
   - 后端 CORS / 跳转 URL / 接口设计.md / 数据库 / Redis key 前缀（如复用 base 作为命名空间）
   - Nginx / Docker / K8s
4. 如某消费者点本次确实无需联动 → 在「已联动消费者点」列以括号注明"无需联动 — 原因 XXX"
5. 漏改的消费者点常导致下次"双前缀 404 / SSE 走错地址 / nginx 反代失效"等级联事故 —— `vcs_mode=git` 提交前用 `git diff --name-only`；`vcs_mode=none` 用 X.0.0 的本地 sha256 变更清单与事实清单「路径消费者点」表对账，缺项要么补改要么注明"无需联动"
6. **★ 消费者点集合是"会变大"的、不止 base 改动才动本表**：Phase 1.3 Step 1「请求通道单一判据 + 消费者点登记门」在**新增请求通道**（新 composable / 工具 / `fetch`·`EventSource`·`WebSocket`）时就要往「路径消费者点」表**补登记新行**——本 Step X.6 管的是 base/context-path **改动时的联动**，二者互补。集合悄悄变大而无人登记，会让下次 base 变更漏掉新通道（双前缀 404 温床）。

#### Step X.7：配置操作变化登记

运行时配置原文件是权威，不复抄完整配置、不创建示例副本。日常 dev / bugfix 不生成部署 Markdown；本任务涉及配置文件或代码内动态配置注入时，把改动文件引用交 Step X.8 记入既有 `deployment_doc_pending`。变化来源：`vcs_mode=git` 取 git diff；`vcs_mode=none` 用 `sprint-{NNN}-local-before.json` 与 X.0.0 的 `sprint-{NNN}-local-changes.json` 逐文件 `sha256` 前后态判定增删改，快照缺失记 `evidence-missing`，⛔ 不得把空 Git diff 当作「无配置变更」。核对范围只取当前任务的实际变化；无可信前态就注明缺口，不扩大成全版配置审计。

版本规划/正式发布集中校准时，按 `{{AIDP_HOME}}/reference/部署操作约定.md` 合并到 `docs/deployment/{version}/配置文件/增量/配置项清单.md`（配置中心变体沿现有文件）：

- 只列本版新增、修改、删除配置，按权威文件/dataId 给出必要片段和短注释；无变更在既有操作说明简注，不造空清单。
- nginx/compose/k8s 只给改动片段、插入位置与生效命令，不贴整份文件。
- 动态注入 key 同样纳入本次变化（如 `@Value` / 配置绑定 / 可配置定时器）；给出必配与是否需重启，不补历史欠项。
- 删除按原缩进粒度标明单 key/整段，不能误删父配置块；秘密值不进 Markdown。
- 部署流程只引用该清单，不双写配置内容；发布期真实配置全量文件仍按约定 37 维护。

