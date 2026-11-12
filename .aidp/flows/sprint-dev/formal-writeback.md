# /sprint-dev — A/B 共用 Step X 回写，保留原回写子片调用

> 本片覆盖：A/B 共用 Step X 回写，保留原回写子片调用。入口与阶段映射见 `{{AIDP_HOME}}/commands/sprint-dev.md`；仅在该阶段适用时 Read，原参数与 `EXECUTION_CONTEXT` 原样继承。

### ★ 开发完成后：自动回写需求 + 设计文档（含研发需求回写）

> ⚠️ 关键规则一句提醒：**Step X.0.0 是约定 22「上游文档级联同步」的统一入口**——开发引入超出既存文档范围的实质变更（新增接口/表/业务规则/页面/功能点、原型字段被覆盖/裁剪、Mock→真实、语义·口径·范围变更）时必须按 4 级触发（研发需求→详细设计→研发执行计划→研发自测用例）自动级联，**禁止绕过它直接调单一 SKILL 补单层**；部署文档日常不触碰，仅版本规划/正式发布集中校准。

> ⛔⛔ **详细步骤已外置为 3 个分片、进入本回写段的【第一动作】= 按需加载**：Step X.0.0–X.6 与收口的完整步骤在 `{{AIDP_HOME}}/flows/sprint-dev/` 下 **3 个分片**，**进入本段第一动作 = 按序 Read 三片**、逐项执行：
> 1. **`{{AIDP_HOME}}/flows/sprint-dev/postdev-writeback-1.md`** — Step X.0.0（上游文档级联同步检测）
> 2. **`{{AIDP_HOME}}/flows/sprint-dev/postdev-writeback-2.md`** — Step X.0 / X.2 / X.3 / X.4 / X.5 / X.6
> 3. **`{{AIDP_HOME}}/flows/sprint-dev/postdev-writeback-3.md`** — **累进路径的产物审计收口**
>
> 下方骨架仅供定位，**权威判定与触发条件一律以分片 flow 文件为准，绝不凭本骨架或记忆略过任一 Step，也不得只读其中一片**。

**触发条件（详见 flow 文件）**：开发引入 新增/改接口 · 新增表/改表结构/新增字段 · 新增公共组件/页面/模块 · 新增外部依赖 · 调整 context-path/端口/proxy/API 前缀（配置事实）· 开发期发现"需求漏项" 任一即触发回写。

**回写步骤骨架（详见 `postdev-writeback-1.md` + `-2.md` + `-3.md`）**：

| Step | 作用（一句话） |
|---|---|
| **X.0.0** | ★ 上游文档级联同步检测（约定 22 统一入口，4 级触发 + 默认攒批入台账；**仅破坏性变更弹确认门**——document 已授权才执行成文，未授权保持事实登记）|
| **X.0** | 研发需求回写（含开发期需求漏项）|
| **X.2** | 调 dev-logic-architect 更新设计（走 `/sprint-design --ledger-cascade [--unattended]` 编排；⛔ **不是 `--supplement={NN}`** —— 本段是约定 22 收口级联，就地改主文档、不新建分册，落点门会判 exit 1）|
| **X.3** | 调 `/sprint-plan --ledger-cascade [--unattended]` 更新研发执行计划（⛔ 同上，不是 `--supplement`）|
| **X.4** | 更新项目级 memory（架构级变更时）|
| **X.5** | 更新 SQL 脚本 |
| **X.6** | ★ 更新 *事实清单.md（配置事实变更时）|
| **收口** | ★ 累进路径的产物审计（docs-audit 已授权且新内容未被同 hash 证据覆盖 → 派 version-auditor）|

> 收口：回写段完成 → 进入 `formal-completion.md` 的「完成前验证」。**执行前务必已按序 Read `postdev-writeback-1.md` + `-2.md` + `-3.md` 并按其逐项完成，不能只看本表。**

---


回写完成后 Read `{{AIDP_HOME}}/flows/sprint-dev/formal-completion.md`。
