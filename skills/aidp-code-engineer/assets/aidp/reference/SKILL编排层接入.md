# SKILL 编排层接入（版本规划四个子命令的共用契约）

> **谁读**：`/sprint-requirements` · `/sprint-design` · `/sprint-plan` · `/sprint-selftest` 在调用生成能力前读；
> `/version` 规划链在传这些入参前读。单独调用同样按父授权确定QR档位，不把缺参数解释成自动full。
>
> 协议本身归 SKILL：各 SKILL 的 `references/flow-orchestration.md`（四份内容相同）与
> `dev-manual-testcase/references/flow-scale-control.md`。本文只写**命令端要做的事**，⛔ 不复述 SKILL 判据。

## 一、入参只由编排层传

| 命令 flag | 传给 SKILL 的入参 | 谁传 |
| :- | :- | :- |
| `--qr-level=scripts\|critical\|full` | `qr_level` | AIDP生成调用层按下方父策略选择；version保留已有critical/fast配方|
| `/sprint-selftest --prd-presence-table=<路径>` | `prd_presence_mode=table` + `prd_presence_table` | `/version` Step 2.4.3.5：`prd_presence_table.py` 生成了对账表时 |
| `/sprint-selftest --module-case-cap=N` | `module_case_cap` | `/version` Step 2.4.3.5：L 档传 30 |
| `/sprint-selftest --matrix-scope=p0` | `matrix_scope` | `/version` Step 2.4.3.5：L 档传 |
| `/sprint-selftest --module-kind=…` | `module_kind` | `/version` Step 2.4.3.5：恒传，缺省 `auto`（SKILL 读详细设计「模块类型」，缺字段按页面模板）|
| `/sprint-selftest --plan-ref-mode=deferred` | `plan_ref_mode` | `/version` Step 2.4.3.5：仅 fresh 模式与 `/sprint-plan` 并行时 |

- `qr_level` 必须由下方调用层显式计算并传给SKILL，不能遗漏而回落full；其余规模入参仍只透传实际收到的值，不自行补默认。

### 文档生成的授权与最小QR

动作来源、预算与grant revision按 `{{AIDP_HOME}}/flows/sprint-dev/light-context.md`；本节只定义四个生成入口的调用适配。微小文档编辑直接复用必要编辑能力，不机械调用整套生成SKILL。显式生成职责包括依赖无法拆开的最低质量自检：四Skill的scripts档仍跑全部机器门及不可关闭Critical语义，不能宣称“纯脚本/关闭全部QR”，不编none档。

入口先建立/继承真实execution_context；以下围栏在每次Skill调用前执行。REQUESTED_QR_LEVEL来自本次或父入口实际参数，缺省空；没有document授权时整段NOT_REQUESTED返回，不创建目录或生成产物。

```bash
EXECUTION_CONTEXT="${EXECUTION_CONTEXT:?生成入口必须传父上下文}"
REQUESTED_QR_LEVEL="${REQUESTED_QR_LEVEL:-}"
QR_ROUTE=$(python3 {{AIDP_HOME}}/scripts/entry_context.py route --root . \
  --execution-context "$EXECUTION_CONTEXT" --phase route --json) || exit $?
python3 {{AIDP_HOME}}/scripts/execution_policy.py require-action --root . \
  --execution-context "$EXECUTION_CONTEXT" --action document || exit $?
DOCS_AUDIT_ALLOWED=$(printf '%s' "$QR_ROUTE" | python3 -c 'import json,sys; print(int("docs-audit" in json.load(sys.stdin)["authorized_actions"]))') || exit $?
QR_LEVEL=scripts
if [ "$DOCS_AUDIT_ALLOWED" = 1 ]; then QR_LEVEL="${REQUESTED_QR_LEVEL:-critical}"; fi
case "$QR_LEVEL" in scripts|critical|full) ;; *) exit 2 ;; esac
printf 'qr_level=%s\n' "$QR_LEVEL"
```

调用prompt必须带 `qr_level=$QR_LEVEL`、父context/revision/action/budget及真实输入hash；每个新Agent先按light-context预留agents预算。SKILL返回按本节原parse-handoff解析，保留既有索引移交块与真实未审事实，不另造清单。没有docs-audit时，非Critical语义/独立审计为NOT_REQUESTED，不登记成本轮欠账、不立即派qr-handoff-auditor，不以清块为由补审。若用户仅要求编辑而不能承担依赖最低生成校验，继续必要编辑能力，不谎称完整生成已通过。

**落盘后复核去重**：机器门及不可关闭Critical属于所请求生成的最低自检，优先复用同revision/inputs真实hash的既有证据；缺证据/产物改动时仅补失效项。额外代码侧report-only巡检、非Critical语义复核、version-auditor/qr-handoff-auditor须docs-audit，未授权跳过，不以生成后处理名义另叠完整QR。每次派Agent前require_action(document或docs-audit按真实职责)并预留父agents预算，工具失败不自动换一套审计求绿。

有docs-audit的公开/version组合、显式qr-level与fast保留原职责：fast明确延期的检查仍按原收口处理。缓存只复用同revision/inputs真实hash证据；修复只delta，不能因为再进生成子入口叠一轮完整QR。

- `dev-manual-testcase` 的这些入参（`prd_presence_*` / `module_case_cap` / `matrix_scope` / `module_kind` / `plan_ref_mode`）**只改产物写法与体量**，不放松 PRD 功规点 100% 覆盖、上游溯源、字段核对、
  反向占比 ≥40%、P0/P1 覆盖（见该 SKILL `flow-scale-control.md` 开头）。命令端回检 `check_case_stats.py` 时
  **带同样的参数**（`--scale L --module-case-cap N`、`--prd-presence-table <路径>`），否则 SKILL 内外两次判定口径不一。

## 二、四个命令对应的 SKILL 与产物索引

| 命令 | SKILL | 移交清单所在的 `00_索引.md` |
| :- | :- | :- |
| `/sprint-requirements` | `ux-logic-extractor` | `docs/requirements/{version}/研发需求/00_索引.md` |
| `/sprint-design` | `dev-logic-architect` | `docs/design/detail/{version}/00_索引.md` |
| `/sprint-plan` | `dev-execution-planner` | `docs/plans/{version}/00_索引.md` |
| `/sprint-selftest` | `dev-manual-testcase` | `docs/testing/{version}/研发自测/00_索引.md` |

## 三、调用时与返回后

1. **调用时**：始终传上方实际得出的 `qr_level=$QR_LEVEL`，不按未带flag省略；档位不能给父任务新增docs-audit权限。
2. **SKILL 执行中**：SKILL 每输出一行 `[AIDP-STAGE] {...}`，按 `/version` Step 2.3.9 当下执行
   `aidp_run_metrics.py ... stage --line '<该行>'` 落盘（计量失败只告警）。
3. **返回后，第一件事**——校验移交清单（档位必须与派发时一致）：

   ```bash
   QO="python3 {{AIDP_HOME}}/skills/<SKILL>/scripts/qr_orchestration.py"
   $QO parse-handoff <上表的 00_索引.md> --expect-level <档位>
   ```

   | 退出码 | 含义 | 处置 |
   | :-: | :- | :- |
   | 0 | 清单与 SKILL checklist 推导结果逐项一致（`full` 档 = 确认无残留块） | 继续 |
   | 1 | 少登记 / 多登记 / 字段被改 / 把 Critical 维度移交 / 位置不对 | **本步未完成**：按该命令既有的「SKILL 产物不合格」处置（交互式停下报出；无人值守按失败处置交熔断） |
   | 2 | SKILL 自身契约坏了（checklist 缺等级列等） | 同上，并在报告里写明是 SKILL 契约问题 |

   ⛔ 不得因为「SKILL 自己说 QR 通过了」就跳过本校验：移交清单写不全时，被漏登记的维度既没被
   SKILL 审、也不会被统一审计接手——两头落空，而产物看起来一切正常。
4. **移交的维度不是「审过了」**：仅docs-audit已授权时由 `/version` Step 2.4.7 的 qr-handoff-auditor 接手，与 version-auditor 并行；
   审计通过后由主流程清掉清单块（见 `{{AIDP_HOME}}/agents/qr-handoff-auditor.md`）。子命令**单独**带 `--qr-level` 调用时，
   清单保留真实未审事实；本轮未授权审计记NOT_REQUESTED，不能推成本轮待办。已授权的fast延期仍为待统一审计，不得手工删除冒充通过。

## 四、QR 变更范围裁剪（`qr_delta_scope`）接线（`/sprint-requirements` · `/sprint-design` · `/sprint-plan` 共用）

> 三个命令各自只留一行引用本节；`/sprint-selftest` 的 `dev-manual-testcase` 有自己的 `qr_mode`（见其命令 Step 1），不适用本节。

`ux-logic-extractor` / `dev-logic-architect` / `dev-execution-planner` 的质量检查按本轮变更范围裁剪，**唯一入参 = `qr_delta_scope`（可选，不传 = 全量）**。⛔ 命令端**不得自造 `qr_mode`**——这三个 SKILL 从未定义它（`qr_mode` 是 `dev-manual-testcase` 独有概念），凭空传等于修改 SKILL 契约（约定 21）且被静默忽略。

- **全量生成**（首次规划 / 主文档重生成）→ **不传 `qr_delta_scope`**。
- **增量补充**（`--supplement={NN}`，或 `/sprint-dev` 口述累进经本命令补充；⛔ `/version` 自身没有 `--supplement` flag，是它检出 PRD/原型变更后派发本命令并传入）→ 传 `qr_delta_scope = <本轮 NN_<业务主题>.md 的专题名 / 章节清单>`。
- ⛔ **只裁「语义核对」的范围，机器门一律全量跑**（SKILL 明文：标「全量」档的维度不接受裁剪——它们的失效形态正是「新增这一处与旧的那些不一致」，只看增量内部一个都发现不了）。算不出 Δ 如实记录范围未知，在有效 `QR_LEVEL` 的必要校验内保守核对，不扩为 full 或独立 docs-audit。
- `/sprint-design` 另有一条：命中「语义/口径/单位/默认值/状态机/权限范围变更（无新增实体）」或跨版本作废判定的项，其受影响专题**强制并入 Δ**（即便无文件命中）；变更落在跨专题共享单元（公共基础设施 / 基类实体 / 共享 DTO / 全局配置）→ 把所有引用该单元的专题并入 Δ。

## 五、客户端应用 MCP（`client_mcp`）判定与传参（各命令只留一行引用本节）

> **为什么必须由命令端传**：下表各 SKILL 对该能力是**入参门控**，且 SKILL 明令**不自行探测是否启用**——**命令端不传 = 该维度 / 用例族永不启用**，启用了该能力的项目静默漏掉这一层，没有任何报错。
> 能力**跨端**（Web / 小程序 / 移动 / 桌面），**WebMCP 只是 Web 端实现**：只按 `check_webmcp.py` 判，非 Web 项目恒得 `enabled: false`，SKILL 侧「非 Web 已声明即通用半场照跑」那一半永不执行——**失效方向是全绿**。故一律取**两级**判定：

```bash
python3 {{AIDP_HOME}}/scripts/check_client_mcp.py --version "{version}" --detect --json   # ① 跨端判定唯一实现（⛔ 不自己 grep PRD）
#   → enabled / declared / capability_state / client_type / implementation / source
python3 {{AIDP_HOME}}/scripts/check_webmcp.py --version "{version}" --detect --json       # ② 仅 client_type=web 且 implementation=webmcp 时才跑
#   → enabled / entry_symbols / launch_command（Web 叶子专有事实）
```

1. ① `enabled: true` → 随 prompt **原样**传整个 `client_mcp` 对象（保留 `enabled`，它与 `declared` 同值，以及 `client_type` / `implementation` / `capability_state` / `source` 等检测事实）。两级均未声明 → **什么都不传**，不提、不留位置。
2. `declared-unimplemented` → 报告列前置缺失，⛔ 不伪造 `enabled: true`；检测退出 2（声明冲突 / 非法值）→ 先修正声明，⛔ 不冒充未启用（无人值守返回失败信号）。
3. 仅当 `client_type=web` 且 `implementation=webmcp` 才跑 ② 并补传下表「Web 叶子入参」；⛔ 非 Web **不传 `webmcp_*`**——它们只是 Web 适配输入，传过去不会为非 Web 创建入口，只会让 SKILL 把客户端判成 web（新旧声明冲突 SKILL 侧须报错，⛔ 不静默覆盖）。`webmcp_entry_symbols` / `webmcp_launch_command` **不可省略也不可写死、不要自拟**：挂载位置已迁移过一次、规范仍在演进，缺该入参 SKILL 直接报错而非猜默认值。

| 命令 → SKILL | 门控处 | 传 `client_mcp` | Web 叶子另传 |
| :- | :- | :-: | :- |
| `/sprint-requirements` → `ux-logic-extractor` | PRD 层「客户端 MCP 业务能力」登记与 QR | ✅ | 不传（`webmcp_*` 只交 Web 适配层，ux 不消费） |
| `/sprint-plan` → `dev-execution-planner` | Task 层按已证实应用自有工具拆必要 Task | ✅ | 不传（同上） |
| `/sprint-design` → `dev-logic-architect` | 检查项 33 | ✅ | `webmcp_enabled: true` + `webmcp_entry_symbols` + `webmcp_launch_command` |
| `/sprint-selftest` → `dev-manual-testcase` | 通用 `[应用MCP]` 用例族 / 维度 20 | ✅ | `webmcp_enabled: true` + `webmcp_launch_command` + `webmcp_entry_symbols`（另生成 Web 双窗口两类套件，未启用态套件优先级不低于已启用态） |
| `/sprint-test` → `code-verification-loop` | 维度 9（标题以 SKILL 为准） | ✅ | `webmcp_enabled: true` + `webmcp_entry_symbols` |
| `/sprint-aiauto-test` → `auto-test-runner` | 经 run-context，不随 prompt | 见 `flows/sprint-aiauto-test/phase-0-8.md` | 同该片（本表不复述） |

> 新增调用方入参名以**目标 SKILL 的输入表**为准；本表与 SKILL 不一致时以 SKILL 为准并回改本表。上游 PRD 头部的声明位置与旧别名归一规则归 `check_client_mcp.py` 文档头与 `{{AIDP_HOME}}/templates/optional-rules/` 下的可选详规，本节不复述。

## 六、无人值守下的「技术边界已预确认」上下文（仅 `/sprint-design` → `dev-logic-architect`）

`dev-logic-architect` Phase 1「技术边界确认」是强交互闸门：逐维度向用户确认、数据库必确认、**严禁**从框架/原型推断、确认汇总经用户 accept 前不得进入 Phase 2。子 Agent 没有 `AskUserQuestion`，所以无人值守下编排层必须**供给**而不是等待或推断：

| 步骤 | 做什么 |
| :- | :- |
| 供给来源（唯一实现 `autopilot_tech_boundary.py`） | PRD `autopilot_decisions.tech_boundary`（至少 `backend` + `database`，无则显式 `none`）；PRD 缺的维度由 `docs/architecture/技术选型.md`「技术栈总览」已填行**按维度**补（PRD 同名维度优先；表按表头列名取值，兼容 7 列总览表与 `/sprint-init` 的 `层级｜技术｜版本` 表，`主数据库` 行计入 database）。⛔ 不从框架/原型/既有代码推断 |
| 前置门 | `/sprint-autopilot` Phase 0.6 第 2bis 步：本 tick **会调 `/sprint-design`**（无 `--skip-dev` / `--no-planning`，设计目录无 `.md` 或带 `--force-replan`）而两源皆无 → 冻结 `prd-missing`，不进 `/sprint-design`；脚本 rc≥2（自身故障）只告警、不冻结 |
| 传入方式 | `autopilot_tech_boundary.py --version {version} --prd-root {prd_root} --summary` 的输出原样并入调用 prompt，对应 SKILL 入参 `tech_boundary_preconfirmed`（清单内维度直接采用；清单外维度由 SKILL 登记 `99_待澄清问题清单.md` 的 D-NNN 占位 `{待用户填写: <维度>}`，不推断） |
| 占位处置 | 规划之后 `/sprint-autopilot` Phase 3.1ter 以 `autopilot_design_placeholders.py` 扫设计里的 `{待用户填写}`：无人值守命中 → 冻结 `prd-missing`（补 PRD `tech_boundary` 后 `--force-replan`，或就地替换占位后自动解冻）；交互式只告警。`/sprint-plan` 只告知、不阻断 |
| 数据库方言 | 同一输出带 `db_dialect`（SKILL 入参；达梦 → `dameng`，未识别不传）。交互式 `/sprint-design` 同样传：取 `aidp_config.py sql-db-flag`（`dm`/`dameng`/`达梦*` → `dameng`，其余为空 = 不传；SKILL 脚本 `--db` / `--sql-db` 只有 `dameng` 有专项规则）。SKILL 返回后 `autopilot_tech_boundary.py --write-dialect` 把用户已确认的达梦回写 `project.sql_dialect`（仅其为空时、幂等），使后续 CVL / SQL 扫描能带 `--sql-db dameng` |

边界：这是编排层对 SKILL「用户主权」的**供给**，不是绕过——清单全部来自用户已落盘的声明；SKILL 仍要求提问（未识别入参）按失败信号交上游熔断，不得由本层替它补栈。
