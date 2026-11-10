> 本片仅供 formal。先按 `{{AIDP_HOME}}/flows/sprint-dev/light-context.md` 核父身份；light 返回对应能力分支，不执行本片。

# sprint-dev · 开发完成后回写详情（分片 3/3 · Step X.8）

> **【分片 3/3 · postdev-writeback 二次切分】** 本片是 `/sprint-dev` 命令「开发完成后回写」段的收尾，覆盖 **Step X.8（部署流程 SOP + SQL执行台账，检测驱动、独立于配置变更，约定 25）**。前两片：`postdev-writeback-1.md`（Step X.0.0 级联检测）、`postdev-writeback-2.md`（Step X.0–X.7）。以本文件为准逐项执行、不得略过。

---

#### Step X.8：★ 部署流程 SOP + SQL执行台账（检测驱动，独立于配置变更）

先按 `light-context.md` 核 document 与父 budget；仅有 deploy 时消费现成 SOP、执行必要备份/已授权迁移/就绪，不借本段开发工具。真实不兼容只回传最小变更与成本；没有 deployment-tool-development grant 不新写 controller。

> `vcs_mode=none` 时下面两处 Git diff 均记 `unsupported:vcs-disabled`，不得把空 diff 当「无变更」；部署变更检测改用本 Sprint `activeContext.md` 涉及文件、SQL 与配置清单，本地规划产物按该清单派增量审计。无法得到可信文件清单时返回范围未核验原因，不自动扩大审计。`git` 模式仍按原 diff 范围执行。

> **为何独立成步**：部署流程文档的实际变更源（新增 SQL / 部署后回填接口 / 需重启）**远宽于** Step X.7 的「配置文件被改动」触发面。若嵌套在 X.7 内，则"只加 SQL、零配置改动"时永远不生成（下游 V0.10 根因）。故本步**独立**、**触发源 = 部署侧实质变更检测**（照搬约定 6「检测 `sql/增量/` 下有无脚本即执行、不依赖研发执行计划是否列 SQL 任务」的检测驱动范式），**与是否改配置、研发执行计划是否列了『写部署文档』任务全部无关**。

**★ 触发（检测驱动，无条件先检测；命中任一即"本版有部署侧变更"）**——命令端跑一次轻量检测：

```bash
V={version}
DEPLOY_CHANGE=0
# ① SQL：docs/deployment/{V}/sql/增量/ 下有 NN_*.sql（跳过 99_回滚脚本.sql）
#    暂存位兜底须含 SKILL 原生形态 `code/sql/v{版本}/`（小写 v）——只扫无 v 路径会漏掉它，
#    而漏扫与本轮确实没有 SQL 在结果上同形。
ls docs/deployment/$V/sql/增量/[0-9][0-9]_*.sql 2>/dev/null | grep -qv '99_' && DEPLOY_CHANGE=1
for _c in "code/sql/v${V#V}" "code/sql/v$V" "code/sql/$V"; do
  [ -d "$_c" ] && ls "$_c"/[0-9][0-9]_*.sql 2>/dev/null | grep -qv '99_' && DEPLOY_CHANGE=1
done
# ② 配置项清单本版有实质内容（Step X.7 已产出）——锚点用 3 段标题，不用「本版本变更」表名
grep -ql "新增配置\|删除配置\|运行时配置文件变更" docs/deployment/$V/配置文件/增量/配置项清单*.md 2>/dev/null && DEPLOY_CHANGE=1
# ③ 本 Sprint 代码 diff 含"部署后必须执行"信号：数据初始化/回填接口、数据迁移脚本、定时任务、context-path/启动参数变更、新增中间件/第三方依赖、判定需重启/重新构建
#    识别信号（按技术栈取等价）：init/rebuild/migrate/backfill 类接口路径、@Scheduled 新增、server.servlet.context-path 变更、新增 pom/package 依赖中间件（redis/mq/es…）
# 本任务变化路径取 development_scope.py 的 scope；只核该范围的部署信号，不用 HEAD~1。
```

> `DEPLOY_CHANGE=1` = 本版有部署侧变更 → **必须维护** `部署流程.md` + `SQL执行台账.md`；`=0`（纯前端样式/纯逻辑修复、无任何部署侧变更）→ 跳过本步。**检测由命令端做，不依赖研发执行计划是否列任务**。

**A) 部署流程 `docs/deployment/{version}/部署流程/部署流程.md`（给部署执行者的操作手册，固定文件名）**：
- **定位**：面向**部署执行者**的操作手册（不是给开发者的设计说明）——每句都应回答"下一步敲什么命令 / 点什么"；解释"为什么这么设计 / 机制怎么实现"（去重表/sha256/迁移原理/历史背景）**一律不进本文档**（归详细设计或删）。与 `{version}-deployment-checklist.md`（运维手工的前置/回滚/灰度/监控）分工，**不复述配置细节**（指向 `配置文件/增量/配置项清单.md`）、**不复述 SQL 内容**（指向 `sql/增量/` 与台账）。
- **★ 无条件 bootstrap-if-missing**：`DEPLOY_CHANGE=1` 且（`部署流程.md` 缺失 **或** 仅剩模板占位符未实值化）→ `mkdir -p docs/deployment/{version}/部署流程/` 并**从模板 `{{AIDP_HOME}}/templates/deployment/部署流程.md` 复制**（模板即 8 章骨架 `〇选形态/一打包/二部署/三中间件配置/四配置项/五验证/六排障/七回滚`，每章带生成指引注释 + 预期篇幅），填充占位符（`{version}`/`{prev-version}` + 各章实值）；已存在有效文件 → 增量更新对应章节（本版新增 init 接口 / 新形态 / 新中间件差异则补进对应章）。**"无文件则生成"不挂任何条件触发的增量步骤内**——检测到部署变更即 bootstrap。
- **★ 生成约束（三条，随模板注释同源、命令端强制落地）**：
  1. **多形态成套**：检测本版部署形态数 N（`docs/deployment/{version}/` 下部署资产 / PRD `autopilot_decisions.deployment` / 打包脚本判断），**N 种形态就产 N 套「打包」+「中间件配置」，缺一不可**；多形态共用一套构建命令时**明确写"构建命令相同、区别只在取用哪些产物"**（避免误以为要维护多条构建链路）。「打包」章须给**产物完整路径 + 文件名 + 解压后内部结构**（如"解压后直接是 bin/+lib/，无顶层目录"）；「中间件配置」须**内嵌完整可复制配置**（每形态各一份）+ 标注形态间差异，外部 `配置文件/` example 作补充**不作替代**。
  2. **自动化环节压缩**：凡应用/框架**自动完成**的环节（启动期自动建表/自动迁移/自动初始化）**只写一句结论 + 幂等性说明**，**禁止**展开人工执行步骤、**禁止**写实现机制（去重表/sha256）。反例（禁）：把"启动期自动迁移、无需人工"当成"第一步 执行 SQL"来写；正例：「SQL 无需人工干预——建表与升级由应用启动时自动完成（幂等，重复启动不重复执行）；`sql/增量/` 仅权威副本供核对」。仅**确需人工执行 SQL** 时才展开步骤。
  3. **配置项不双写（约定 25 延伸）**：「四、配置项」章**不重复**配置项内容，只声明"是否需要改"——全部有默认值 → 一句「配置保持默认即可，需按环境调整见 `../配置文件/增量/配置项清单.md`」；确有必填项 → **只列 key 名、不解释后果**（后果 + 敏感项加固归 `配置项清单.md`）。**部署流程 与 配置项清单 两份 .md 之间不得双写**（同一信息只在一处维护）。
- **精炼铁律**：验证/排障两章一律"可复制命令 + 表格"不写散文；初始化接口/数据迁移**无则删该行 / 填"无"**、不臆造；各章超出模板注释标的预期篇幅多为掺入了设计说明 → 回头精简。

**B) SQL执行台账 `docs/deployment/{version}/部署流程/SQL执行台账.md`（固定文件名，★ 团队共享入库）**：
- **用途**：记录**各环境** SQL 执行状态（开发/演示/生产分列），弥补约定 6 的 `.applied-sql.json` 只覆盖开发库且为 per-user memory、不入部署文档、不覆盖其它环境的空白。
- **首版**：`DEPLOY_CHANGE=1` 且台账缺失 → 从模板 `{{AIDP_HOME}}/templates/deployment/SQL执行台账.md` 复制，按 `sql/增量/` 下实际脚本逐行建表（脚本名 × 环境列）。
- **★ 与约定 6 联动登记开发库列**：Step 1（后端开发）按约定 6 把 SQL 自动应用到开发库成功后，**除写 `.applied-sql.json` 外，同步在台账「开发库」列登记**（状态 ✅ / 影响行数 / 执行时间；no-op 记原因）；**演示/生产列留 `待部署` 占位**，待各环境部署时补——让台账**从开发第一天就存在**、非等到生产部署才临时手搓。
- **团队共享**：台账是跨人协作的部署产物，**入库共享**（区别于 per-user `memory/{version}/{user}/.applied-sql.json`）。

**C) ★ 反静默失败（约定 6 同款「部署阻断风险」告警，禁止静默跳过）**：`DEPLOY_CHANGE=1` 但出现下列任一 → **WARN + 标「部署阻断风险：部署流程文档缺失/未覆盖本版部署变更」**，绝不静默继续：
- 模板 `{{AIDP_HOME}}/templates/deployment/部署流程.md` 或 `SQL执行台账.md` **不存在**（脚手架分发异常，提示重跑 upgrade）；
- 生成/写入失败；
- 检测到部署侧变更（`DEPLOY_CHANGE=1`）却最终无 `部署流程.md`（或仅占位符）。
- **无人值守**（`--unattended`）：把该 WARN 记入 baseline（`versions.{V}.deploy_docs_missing=true`）+ autopilot **#4 提示**，不弹窗、不阻塞，但留痕，供部署前置门（`/sprint-batch` Step 6 / `/sprint-autopilot` Phase 3.2.1）拦截。

**D) 固定命名契约 + 索引**：本版部署产物按固定角色名落位（**不套约定 15 的 `NN_` 分册编号**——部署产物是固定角色而非分册）：`部署流程/部署流程.md`、`部署流程/SQL执行台账.md`、`配置文件/增量/配置项清单.md`、`sql/增量/NN_*.sql`（+ 发布期 `sql/全量/`、`配置文件/全量/`，约定 37）。版本根 `docs/deployment/{version}/README.md`（双轨场景导航）由发布期产出，开发期不维护；各产物按**固定路径**定位、不做模糊匹配。命名契约单一信源见 `06_版本与用户目录约定.md` §2.5.4。


---

## ★ 累进路径的产物审计（补「Critical 硬门只挂在 `/version` 链内」这个贯穿性缺口）

本条规则本身就是「**两条分支都算**」——PRD 驱动的规划期产物与开发期累进产物，
质量要求相同。但 `version-auditor` 的八项审计（C-4/C-5、F、G 为 Critical 硬门）**只在 `/version` Step 2.4.7 激活**；
`/sprint-dev "<描述>"` 累进、`--supplement`、`/sprint-full` 模式 B、`/sprint-bugfix` 方式 C
这四条路径产出的是**同一批四类文档**，却**一次都不经过它**。

后果不是"审计弱一点"，而是这些判据在累进路径上**完全不存在**：
PRD 行级原子条目 → 研发需求（C-4）、研发需求字段 → 详细设计（C-5）、原型覆盖度（F）、
语义变更派生完整性（G）、跨版本需求作废（H）——**五项 Critical 全部落空**。

### 收口点：本轮正式文档汇合后复用一次增量审计

先消费route结果；docs-audit未授权则NOT_REQUESTED并跳到下一适用步骤，已授权分支执行：

```bash
EXECUTION_CONTEXT="${EXECUTION_CONTEXT:?从父入参重绑}"
python3 {{AIDP_HOME}}/scripts/execution_policy.py require-action --root . \
  --execution-context "$EXECUTION_CONTEXT" --action docs-audit || exit $?
```

派发/执行前按light-context预留父预算，prompt带同revision/action/inputs hash，不重新grant。


**先核 docs-audit 授权与预算，再 Read `{{AIDP_HOME}}/flows/sprint-dev/incremental-contract.md`“开发与文档汇合”**。S 仅契约卡/口述原文/族台账时没有正式成文产物，不触发本段；M 等 docs 完成且修订匹配后在汇合点执行，L/显式成文沿用本段。相同契约修订、inputs 与真实内容 hash 匹配的已有规划 QR/审计证据可复用，不因回写、汇合各跑一次；有新差异只补相关条目。以下审计是既有文档审计，不能替代汇合 reviewer 契约检查或 test 的 CVL，也不新增审计层。

```bash
# ⛔ `VERSION` 在 /sprint-dev 全链路无赋值方：取空后四个 `-- <path>` 退化成整目录比对，
#    `CHANGED` 几乎恒非空 ⇒ 每次回写都白派一轮 version-auditor 子 Agent（方向 fail-safe，
#    但判据失真、无人值守下纯烧成本）。真源 = baseline。
VERSION=$(python3 {{AIDP_HOME}}/scripts/baseline_edit.py current-version 2>/dev/null)
[ -n "$VERSION" ] || { echo "⛔ 取不到当前版本号 → 无法界定审计范围，⛔ 不得静默跳过本收口点"; exit 1; }
# 判据：主流程按本轮实际写集核正式需求/设计/计划/用例产物。
# 已提交、暂存、未暂存、未跟踪文件均需覆盖；排除口述原文、契约卡、族台账和仅状态记录。
# BASE_REF 使用契约记录的本 Sprint 改动前基线；无可信基线时按实际工作单核对，不以空 diff 跳过。
# CHANGED 由上述核对填本轮正式产物清单；M 未收齐 docs 回传不能填写“无变化”。
```

docs-audit 已授权、预算已预留且本轮正式产物清单非空、内容发生变化 → 用 `Agent({run_in_background:false})` 派 **version-auditor 子 Agent**
（独立上下文，`{{AIDP_HOME}}/agents/version-auditor.md`），并在派单简报里显式声明：

| 传给它 | 值 |
| :- | :- |
| 父执行策略 | `execution_context/revision/action=docs-audit/execution_budget/input_hash`，不能自加任务 |
| `scope` | `incremental`（⛔ **只审本轮改动涉及的条目**，不重跑全版全量——那会让每次口述累进都付一次规划期审计的成本）|
| `changed_files` | 主流程核对后的本轮实际正式产物清单（含未提交/未跟踪产物） |
| `trigger` | **`accretion`（★ 必传）** —— ⛔ 漏传即落回缺省 `version`，而 `version` 下 Agent 按
**规划期日期路径**写盘、忽略下面的 `output_path`：同一天先跑过 `/version` 规划审计的话，
这份累进报告会把整份规划审计**静默覆盖**掉 |
| `output_path` | `docs/audit/{version}/incremental-audit-{YYYYMMDD-HHMM}.md`（带时分 → 同日多次累进互不覆盖）|
| 审计项 | **C-4 / C-5 / F / G / H 五项**（A 存在性、B 边界、D 增量一致性、E 引用链归 `/version` 全量轮；本轮只补"规划期硬门在累进路径上完全缺席"的那五项）|

- **Critical → 已授权 document 才回原产出者补齐，只重验变化项；同根因同 inputs 无变化停止 retry**，与 `/version` Step 2.4.7 同处置。
- **⛔ 无人值守不得跳过**：`--unattended` 下 Critical 走 `pending_clarifications` 登记 +
  `needs_human` 上浮，**不是静默放行**（约定 36：审计子 Agent 是命令既定职责的一部分）。
- **未授权为 NOT_REQUESTED，不启动此段也不登记审计欠账；已授权时按原质量门执行**：`--skip-audit` 是 `/version` 的内部开关、**本命令根本没有这个 flag**，`trigger=accretion` 下 Agent 侧也不认它（判据见 `agents/version-auditor.md`「唯一跳过…仅当 `trigger=version`」）。口述累进正是「规划期硬门完全缺席」的那条路径，给它开跳过等于本门白设。

<!-- flowvar-check: allow AUDIT_CRITICAL -->
<!-- flowvar-check: allow UNATTENDED -->

```bash
# ★ 「needs_human 上浮」必须是**可执行语句**：只写在散文里 = Critical 在无人值守下既没人看见、
#   也不落进 `jq '.versions[]|select(.needs_human==true)'` 这个外部巡检唯一能抓到的视图。
# ★ 两个变量由**执行体据审计子 Agent 回传就地填字面量**（同 phase-0-1 的 IS_LOOP_CONTEXT 范式）：
AUDIT_CRITICAL=0   # ← 审计回传含 Critical 则改 1
UNATTENDED=0       # ← 本次调用带 --unattended 则改 1
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell)"
V="${TARGET_VERSION:-$(python3 {{AIDP_HOME}}/scripts/baseline_edit.py current-version 2>/dev/null)}"
[ -n "$V" ] || { echo "⛔ 取不到版本号（TARGET_VERSION 空且 current-version 无解）→ 本块无法执行，⛔ 不得静默跳过：请显式传版本或先落 baseline"; exit 1; }
BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py"
if [ "$AUDIT_CRITICAL" = "1" ] && [ "$UNATTENDED" = "1" ]; then
  # 冻结四件套 + #4 一次做完。`--freeze-now` = 熔断条件（审计 Critical）已成立、一次即冻，
  # ⛔ 不走 streak：给它塞计数会在巡检里长出一串永不清零、也不是真判据的假计数。
  # ⛔ 「发 #4」必须由这一行真的发出去 —— 只写四件套 = 停得住但停不响，通知渠道零消息。
  python3 {{AIDP_HOME}}/scripts/autopilot_fail_handle.py --version "$V" --freeze-now \
    --phase audit-critical --reason audit-critical \
    --why "增量审计检出 Critical（C-4/C-5/F/G/H），无人值守不得静默放行，请人工裁决后重跑"
fi
```

> **Why 放在这里而不是各命令各写一遍**：上述四条累进路径最终都汇到本段回写，在此收口一处即可覆盖。
>
> ⚠️ **但"一处覆盖全部"只对经过 `/sprint-dev` 的路径成立**，而**第五条路径已经存在**：
> `/sprint-bugfix` **方式 B**（及以它为执行体的方式 A）产出同样的三类文档，却**全程不调用
> `/sprint-dev`**，永远到不了本段。故 `flows/sprint-bugfix/mode-b.md` Step 5 末尾**另挂一份
> 同规格的收口**（同 `scope=incremental` / 同五项 / 同无人值守处置），⛔ 两处必须同步改。
> 方式 A 以方式 B 全流程为执行体，即 `/sprint-batch` → `/sprint-full` 的 bugfix 循环走的就是它
> ——无人值守主链的常态，漏掉它等于这道门在最常跑的那条路上不存在。
