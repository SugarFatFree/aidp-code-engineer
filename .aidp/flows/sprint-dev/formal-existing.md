# /sprint-dev — 分支 A，Phase 0A / 0A.5

> 本片覆盖：分支 A，Phase 0A / 0A.5。入口与阶段映射见 `{{AIDP_HOME}}/commands/sprint-dev.md`；仅在该阶段适用时 Read，原参数与 `EXECUTION_CONTEXT` 原样继承。

## 分支 A：开发已有 Sprint

### Phase 0A：读取上下文

1. 读取 `memory/{version}/{user}/activeContext.md` 获取当前 Sprint 编号（⛔ 该值由 Phase 1.0pre 置位/校验后才可信——batch/autopilot 常绕过 `/sprint-start`，裸读会拿到上一个 Sprint 的编号，进而定错开发范围与死代码扫描范围）
2. 确认设计文档存在（★ **用 glob 探测、兼容约定 14 三态命名**，不硬编码裸名——否则拆分态项目 `01_详细设计.md`/`02_数据库设计.md`/`03_接口设计.md` 会被误判"缺文档"而错误中止）：
   - **详细设计**：`ls docs/design/detail/{version}/{00_索引,00_详细设计,01_详细设计,详细设计}.md 2>/dev/null` 任一命中即视为存在（拆分态 `00_索引.md`/`01_详细设计.md` / 单份态 `00_详细设计.md` / 历史存量裸名 `详细设计.md`）
   - **数据库设计 / 接口设计**：同理各按 `{00_数据库设计,02_数据库设计,数据库设计}.md` / `{00_接口设计,03_接口设计,接口设计}.md` glob 探测（拆分态序号不固定，最稳做法 = 直接 `ls docs/design/detail/{version}/*.md` 看是否有内容主文档）
   - `对外开放接口.md`（★ 如本版本有对外开放接口；缺失但 PRD 含对外接口需求 → 提示先跑 `/sprint-design` 补齐）

如果设计目录 `docs/design/detail/{version}/` 无任何内容主文档（`*.md` 仅有 `00_索引`/`99_待澄清` 管家文件或全空），停止并提示用户先执行 `/version` 进行版本规划。

3. **★ GitHub Issue 缺陷读取（可选，仅用户主动提及 GitHub Issue 时，约定 31.3）**：用 `gh issue list` / `gh issue view <编号>` 拉取 → **先预读、理解每条缺陷语义、确认缺陷确实存在/可复现，再纳入本次开发/修复**；缺陷为人工填充不可盲信标题。未主动提及时跳过，不强制拉取；未安装或未登录 `gh` 时终端提示后跳过。

### Phase 0A.5：★ 历史死代码扫描与处置决策门

> **目的**：写码前核实历史同名/同语义实现的可达性与引用。**删除判据唯一信源 = `{{AIDP_HOME}}/rules/code.md` 约定 29「删除证据门」**；Frontend/Backend Agent 的 grep 只提供候选线索，零命中、扫描错误或“重构”字样都不授权删除。只有证据门确认的 B 清单才执行删除，未知一律保留。

**1. 识别本 Sprint 涉及的功能板块**（从设计/需求/计划读取）：

```bash
# 从研发需求 / 详细设计 / 研发执行计划提取本 Sprint 要做的板块/页面/接口名清单
SPRINT_NNN=$(cat memory/{version}/{user}/activeContext.md | grep "当前 Sprint" | awk -F: '{print $2}' | tr -d ' ')
grep -A 50 "Sprint-${SPRINT_NNN}" docs/plans/{version}/01_研发执行计划.md \
  | grep -E "新增|实现|开发|重做|重构" \
  | head -30
# 输出疑似涉及的"业务关键词"清单（如：用户管理、订单导出、报表中心）
```

**2. 收集候选并逐文件核实证据**：读取 Frontend/Backend Agent 核心原则 11 的扫描线索，再按约定 29 核对可达入口、存活引用、动态/外部消费者与连带文件。扫描只完成一部分时不得把未核部分填“无”。

输出 `memory/{version}/{user}/sprints/sprint-{NNN}-deadcode-scan-{YYYYMMDD-HHMM}.md`，删除前必须填写下表（证据列写具体文件:行或调用契约位置）：

| 候选文件 | 本 Sprint 重做依据 | 可达入口证据 | 存活引用/动态消费者证据 | 连带文件独占依据 | 未核项 | 处置 |
|---|---|---|---|---|---|---|
| 每个候选各一行 | 需求/Task 位置 | 有/已证实无/未知 + 证据 | 有/已证实无/未知 + 证据 | 逐文件依据或不删除连带文件 | 必须列全，无则写无 | 按约定 29 判 A/B/C/保留待核 |

详情页无菜单但仍有路由 → 不能判 B；动态 import/自动注册尚未查清 → 保留待核；仍在用且明确重构 → C；仅在全部删除证据充分且明确重做时 → B。

**3. 决策门**（按 3 类处置规则）：

| 情形 | 默认行为 | 是否弹 AskUserQuestion |
|------|---------|----------------------|
| **A 仍在用 + 增量增强** | 按约定 28 复用，正常往下写 | 否 |
| **B 删除证据充分 + 明确重做** | `vcs_mode=git` 用 `git rm`；`vcs_mode=none` 逐项 `Path.unlink()` 删除证据清单内的文件。连带文件逐项证明独占，未证明的不删；数据库按下方 Step 4 单独核验 | 否 |
| **C 仍在用 + 需求重构（优先于 B）** | 弹 `AskUserQuestion`：「① 并存切流量（推荐）/ ② 直接替换 / ③ 单写新版保留旧版」三选一 | **是** |
| **保留待核** | 保留未知文件及关联资源，记录未核项；继续不依赖删除的工作，无法推进时返回有原因的失败信号 | 无人值守不询问、不自动删除 |

★ **删除执行门**：只有已填齐扫描记录且通过约定 29 证据门的 B 文件，才在 Phase 0A.5 内删除并复核结果。证据不足不能为了完成本步骤而扩大删除范围；删除失败不得声称已经清理。

★ **情形 C 的 `--unattended` 降级（无人值守不挂死）**：`/loop` 无人值守（带 `--unattended`）下情形 C **不弹 `AskUserQuestion`**——优先消费 PRD `autopilot_decisions` 死代码处置预声明；无预声明则取**保守默认「① 并存切流量」**（新版并存 → 切流量 → 旧版留待人工删除，最不破坏现网），并在终端 + autopilot #4 里程碑通知 WARN「死代码情形 C 走无人值守默认①，旧版删除待人工复核」，**绝不挂起等待**。仅交互式（无 `--unattended`）才弹三选一。

**4. 表数据安全检查**（情形 B 涉及后端 Entity / Mapper 删除时必跑）：

读取 `memory/databaseBaseline.md`、本版建表/应用台账及目标环境的只读元数据，核实表归属、消费者与数据状态。**基线未登记不等于表不存在或无生产数据**；取不到实际证据时保留表及关联资源、登记待核，不能生成或执行 DROP。

有存量数据/存活消费者时按 C 的兼容策略处理。即使已证实表无存量数据，删除或回滚 SQL 也须有本版部署/回滚授权与明确适用条件，不能因删除 Entity/Mapper 自动补 DROP。交互式缺失关键依据时集中询问；`--unattended`／`--from-batch` 按调用方待裁决或失败协议返回，不挂起、不猜空库。

**5. 留档**：
- 扫描清单：`memory/{version}/{user}/sprints/sprint-{NNN}-deadcode-scan-*.md`
- 删除清单：追加到 `docs/design/detail/{version}/*事实清单.md`「死代码删除清单」段
- Sprint 归档：完成后由 `/sprint-close` 把删除清单汇总到 `sprint-{NNN}.md`「死代码清理」段
- **不写 ADR**（按约定 29 — 删除死代码是清理工作非架构决策）

**6. 跳过条件**：
- 全部扫描结果归类为 A（无死代码） → 终端打印「✅ 无死代码识别，跳过 Phase 0A.5 删除动作」直接进入开发执行步骤
- `--skip-deadcode-scan` 旗标（仅用于已知本 Sprint 全是绿地新建的场景；不推荐常态使用）

**7. 与 Step X.0.0 上游级联同步的协作**：
- Phase 0A.5 的"删除旧文件"事件不属于"上游文档变更"，**不触发** Step X.0.0 上游级联
- 但删除清单必须写入 `*事实清单.md` 让下一个 Sprint 的 Phase 0A 能读到"该模块已重做"基线信息

> 分支 A 的 Phase 0A* 跑完后直接转入 `{{AIDP_HOME}}/flows/sprint-dev/formal-development.md`「Phase 序列（分支 A / B 共用）」，不进入分支 B。

---


本分支完成后 Read `{{AIDP_HOME}}/flows/sprint-dev/formal-development.md`，不读取分支 B。
