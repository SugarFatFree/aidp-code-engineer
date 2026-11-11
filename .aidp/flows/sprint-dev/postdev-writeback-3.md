> 本片仅供 formal。先按 `{{AIDP_HOME}}/flows/sprint-dev/light-context.md` 核父身份；light 只使用适用能力。

# sprint-dev · 开发完成后回写详情（分片 3/3 · Step X.8）

#### Step X.8：部署操作变更留待集中同步

日常 dev / bugfix / 链外任务 / 部署不自动新增或更新部署 Markdown，不为部署日志另做 commit/push。只核本任务变化的 SQL、配置、启动参数、初始化/迁移接口、服务与中间件；历史债务不纳入。沿用当前 execution context，不因 commit/push/deploy 新请求追加测试、CVL、全回归、迁移演练、多 Agent、计划卡或新工具开发。正式 aiauto 报告和已授权的两路测试链职责不变。

有实际操作变化时，把权威文件/现成运行记录引用记到既有 baseline 的 `deployment_doc_pending.{version}`，不复制配置正文或生成报告。无变化不写：

<!-- flowvar-check: allow DEPLOY_REF -->

```bash
# VERSION、DEPLOY_REF 从本任务现有上下文重绑；DEPLOY_REF 是实际变化文件或运行记录引用。
VERSION="${VERSION:?从当前执行上下文重绑版本，不读历史Sprint}"
python3 {{AIDP_HOME}}/scripts/deployment_ops.py note --version "${VERSION:?}" --ref "${DEPLOY_REF:?}"
```

部署执行只消费现有操作指引和上述待同步引用。入口缺失时按已知真实脚本/配置判定最小前提缺口，不回调开发链补文档，不把“未写 Markdown”变成部署失败。备份按 `{{AIDP_HOME}}/reference/部署操作约定.md` 统一频率核对；不因 schema 迁移增加副本，不自动恢复旧数据。未配置 CI/pipeline 使用现有轻量出口，一次说明原因，不循环探测。

版本规划与正式发布才读取该待办并按 `{{AIDP_HOME}}/reference/部署操作约定.md` 集中合并必要操作指引；用户明确要求额外报告时才另产。合并成功后仅结清实际覆盖的引用，失败保留。

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
